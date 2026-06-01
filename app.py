import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
import os
import time

from config import CANDIDATES, PLATFORMS
from database.db import init_db, get_db
from scraper.web_searcher import WebSearcher
from scraper.post_fetcher import fetch_reddit_data
from analyzer.aggregator import Aggregator
from utils.helpers import is_poll_post

st.set_page_config(page_title="VoxPopuli 2027", page_icon="📊", layout="wide")
os.environ["STREAMLIT_SUPPRESS_TORCH_WARNING"] = "1"


@st.cache_resource
def init_system():
    init_db()
    db = get_db()
    for key, info in CANDIDATES.items():
        db.execute("INSERT OR IGNORE INTO candidates (key, name, party, color) VALUES (?, ?, ?, ?)",
                   (key, info["name"], info["party"], info["color"]))
    db.commit()
    return db


st.title("📊 VoxPopuli — Analisis Electoral 2027")
st.caption("Busca automaticamente en todo internet. Datos 100% publicos y verificables.")

init_system()

PLATFORM_ICONS = {
    "instagram": "📷", "facebook": "📘", "twitter": "🐦", "tiktok": "🎵",
    "reddit": "🤖", "youtube": "▶️", "threads": "🧵", "web": "🌐",
}

if "search_history" not in st.session_state:
    st.session_state.search_history = []
if "current_result" not in st.session_state:
    st.session_state.current_result = None
if "busy" not in st.session_state:
    st.session_state.busy = False

with st.sidebar:
    st.header("⚙️ Configuracion")
    max_results = st.slider("Resultados maximos", 200, 2000, 800, 100,
                            help="Mas resultados = mas datos pero tarda mas")
    if st.button("🔍 INICIAR BUSQUEDA MASIVA", type="primary", use_container_width=True):
        st.session_state.trigger_search = True
    st.divider()
    st.caption("**Como funciona:**")
    st.caption("1. Genera 50+ combinaciones de busqueda")
    st.caption("2. Busca en todo internet (DuckDuckGo)")
    st.caption("3. Extrae % y reacciones de cada resultado")
    st.caption("4. Scrapea Reddit API para engagement real")
    st.caption("5. Determina ganador por encuesta")
    st.caption("6. Muestra URLs verificables")

if st.session_state.get("trigger_search"):
    st.session_state.trigger_search = False
    st.session_state.busy = True

    ws = WebSearcher()
    progress_bar = st.progress(0, text="Buscando en internet...")
    status = st.empty()

    results = ws.search_all_platforms(max_per_query=6, max_total=max_results)
    total_found = len(results)
    status.text(f"Encontrados {total_found} resultados. Guardando en DB...")

    db = get_db()
    cursor = db.execute("INSERT INTO searches (keywords, status) VALUES ('auto-generada', 'running')")
    sid = cursor.lastrowid
    db.commit()

    saved = 0
    polls_with_pct = 0
    total_engagement = 0

    for i, post in enumerate(results):
        if i % 20 == 0 and i > 0:
            progress_bar.progress(min(i / max(total_found, 1), 0.7),
                                  text=f"Guardando {i}/{total_found}...")

        plat = post.get("platform", "web")
        posted_at = post.get("posted_at") or None
        poll_pcts = post.get("poll_results", {})

        if poll_pcts:
            polls_with_pct += 1

        try:
            db.execute("""
                INSERT OR IGNORE INTO posts
                (search_id, platform, post_id, url, caption, image_url, posted_at, is_poll, poll_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sid, plat, str(post.get("post_id", ""))[:200],
                post.get("url", ""), post.get("caption", ""),
                post.get("image_url", None), posted_at,
                1 if (is_poll_post(post.get("caption", "")) or poll_pcts) else 0,
                json.dumps(poll_pcts) if poll_pcts else None,
            ))
            saved += 1
        except Exception:
            continue

        post_row = db.execute("SELECT id FROM posts WHERE platform=? AND post_id=?",
                              (plat, str(post.get("post_id", ""))[:200])).fetchone()
        if not post_row:
            continue
        pid = post_row["id"]

        likes = post.get("likes", 0)
        comments = post.get("comments_count", 0)
        if likes:
            try:
                db.execute("INSERT OR IGNORE INTO reactions (post_id, reaction_type, count) VALUES (?, ?, ?)",
                           (pid, 'like', int(likes)))
                total_engagement += int(likes)
            except Exception:
                pass
        if comments:
            try:
                db.execute("INSERT OR IGNORE INTO reactions (post_id, reaction_type, count) VALUES (?, ?, ?)",
                           (pid, 'comments', int(comments)))
                total_engagement += int(comments)
            except Exception:
                pass

        caption = post.get("caption", "") or ""
        caption_lower = caption.lower()
        for ck, info in CANDIDATES.items():
            terms = list(set(t.lower().replace("#", "") for t in
                             (list(info.get("search_terms", [])) + [info["name"]] + list(info.get("keywords", [])))))
            for t in terms:
                if t and t in caption_lower:
                    db.execute("INSERT OR IGNORE INTO post_candidates (post_id, candidate_key, confidence, detection_method) VALUES (?, ?, ?, ?)",
                               (pid, ck, 0.7, "text_match"))
                    break

    db.commit()

    reddit_count = 0
    for i, post in enumerate(results):
        if post.get("platform") == "reddit":
            progress_bar.progress(0.8, text=f"Scrapeando Reddit {reddit_count+1}...")
            try:
                rd = fetch_reddit_data(post.get("url"))
                if rd:
                    pr = db.execute("SELECT id FROM posts WHERE platform='reddit' AND post_id=?",
                                    (str(post.get("post_id", ""))[:200])).fetchone()
                    if pr:
                        pid = pr["id"]
                        score = int(rd.get("likes", 0))
                        coms = int(rd.get("comments_count", 0))
                        if score:
                            db.execute("INSERT OR IGNORE INTO reactions (post_id, reaction_type, count) VALUES (?, ?, ?)",
                                       (pid, 'upvotes', score))
                        if coms:
                            db.execute("INSERT OR IGNORE INTO reactions (post_id, reaction_type, count) VALUES (?, ?, ?)",
                                       (pid, 'comments', coms))
                        if rd.get("posted_at"):
                            db.execute("UPDATE posts SET posted_at=? WHERE id=?", (rd["posted_at"], pid))
                        reddit_count += 1
            except Exception:
                pass
    db.commit()
    db.execute("UPDATE searches SET status='completed' WHERE id=?", (sid,))
    db.commit()

    progress_bar.progress(0.9, text="Analizando resultados...")
    agg = Aggregator()
    result = agg.get_search_results(sid)
    progress_bar.progress(1.0, text="Listo!")

    time.sleep(0.5)
    progress_bar.empty()
    st.session_state.current_result = result
    st.session_state.search_history.append({"result": result})
    st.session_state.busy = False
    st.rerun()

result = st.session_state.current_result

if result:
    total = result.get("total_posts", 0)
    polls = result.get("total_poll_posts", 0)
    cands = result.get("candidates_found", 0)
    top = result.get("top_candidate", "N/A")
    poll_details = result.get("poll_details", [])
    poll_wins = result.get("poll_wins", {})
    all_posts = result.get("all_posts", [])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Posts", total)
    c2.metric("Encuestas con %", polls)
    c3.metric("Candidatos", cands)
    c4.metric("Lider", top)

    st.caption(f"🔍 {len(poll_details)} encuestas con porcentajes extraidos | {len(all_posts)} posts con datos | "
               f"Todas las URLs son verificables.")

    if poll_wins:
        st.divider()
        st.header("🏆 Quien GANA en las Encuestas (con % reales)")
        cols = st.columns(min(len(poll_wins), 4))
        for i, (name, data) in enumerate(sorted(poll_wins.items(), key=lambda x: -x[1]["wins"])):
            with cols[i]:
                st.metric(name, f"Gana {data['wins']}/{data['total_polls']}",
                          delta=f"+{data['avg_margin']} pts promedio")

    if poll_details:
        st.divider()
        st.header("📋 Detalle de cada encuesta (URL + % + engagement + interpretacion)")
        for pd_ in poll_details:
            pcts = pd_.get("percentages", {})
            sorted_p = sorted(pcts.items(), key=lambda x: -x[1])
            pcts_str = "  |  ".join(f"**{n}**: {v}%" for n, v in sorted_p)

            label = f"{'🥇' if pd_['winner'] == top else '📊'} {pd_['winner']}: {pd_['winner_pct']}% — {pd_.get('caption', '')[:80]}"
            with st.expander(label):
                st.markdown(pcts_str)
                margin_str = f"(+{pd_['margin']} puntos sobre el segundo)"
                eng_str = ""
                eng_parts = []
                if pd_.get("likes"):
                    eng_parts.append(f"👍 {pd_['likes']} likes")
                if pd_.get("comments"):
                    eng_parts.append(f"💬 {pd_['comments']} comments")
                if eng_parts:
                    eng_str = " | ".join(eng_parts)

                st.markdown(f"**Interpretacion:** {pd_['winner']} "
                            f"{'GANO' if pd_['margin'] > 0 else 'EMPATO'} "
                            f"con {pd_['winner_pct']}% "
                            f"{margin_str if pd_['margin'] > 0 else ''}")
                if eng_str:
                    st.markdown(eng_str)
                st.markdown(f"📎 [{pd_.get('url', '')[:120]}]({pd_.get('url', '')})")

    if all_posts:
        st.divider()
        st.header("📎 TODOS los posts encontrados")
        st.caption(f"{len(all_posts)} posts unicos. Cada URL es cliqueable y verificable.")
        rows = all_posts[:300]
        show_df = pd.DataFrame([
            {
                "URL": r["url"],
                "Plat": r["platform"],
                "Candidato": r.get("candidate_name") or "—",
                "%": ", ".join(f"{k}: {v}%" for k, v in r.get("poll_results", {}).items()) if r.get("poll_results") else "—",
                "👍": r["likes"],
                "💬": r["comments"],
                "Ganador": r.get("winner") or "—",
                "Margen": f"+{r['margin']} pts" if r.get("margin") else "—",
            }
            for r in rows
        ])
        st.dataframe(
            show_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "URL": st.column_config.LinkColumn("URL", max_chars=60),
                "%": st.column_config.TextColumn("%", width="large"),
            },
        )

    st.divider()
    st.header("🧠 Conclusion")
    st.markdown(result.get("conclusion", ""))

    if st.session_state.search_history:
        st.divider()
        with st.expander("📜 Historial"):
            for h in st.session_state.search_history[-3:]:
                r = h.get("result", {})
                pw = r.get("poll_wins", {})
                if pw:
                    st.caption(" | ".join(f"{n}: {d['wins']}/{d['total_polls']}" for n, d in pw.items()))
                st.caption(f"{r.get('total_posts', 0)} posts | {len(r.get('poll_details', []))} encuestas")
