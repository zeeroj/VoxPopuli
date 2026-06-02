import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
import os
import time

from config import CANDIDATES, PLATFORMS
from database.db import init_db, get_db
from scraper.web_searcher import WebSearcher
from scraper.facebook_scraper import FacebookScraper
import scraper.post_fetcher as pf
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
    fb_cookies = os.path.exists(os.path.join("data", "cookies.txt"))
    if fb_cookies:
        st.caption("✅ **Facebook:** cookies detectadas")
    else:
        st.caption("❌ **Facebook:** sin cookies (solo datos publicos)")
        st.caption("   Exportá cookies.txt a data/cookies.txt para datos de FB")
    st.caption("**Como funciona:**")
    st.caption("1. Genera 513 combinaciones de busqueda")
    st.caption("2. Busca en internet (DuckDuckGo + Facebook si hay cookies)")
    st.caption("3. Extrae % de encuestas y reacciones reales")
    st.caption("4. Scrapea Reddit API + Facebook para engagement real")
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

    fb_scraper = FacebookScraper()
    if fb_scraper.is_authenticated():
        status.text("Cookies de Facebook detectadas. Buscando en Facebook...")
        for page in fb_scraper.get_known_political_pages():
            fb_posts = fb_scraper.get_page_posts(page, pages=2)
            for fp in fb_posts:
                results.append(fp)
            if len(fb_posts) > 0:
                break
        status.text(f"Encontrados {total_found} (+ FB) resultados. Guardando en DB...")
    else:
        status.text("Sin cookies de Facebook. Buscando solo datos publicos...")

    total_found = len(results)

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
        poll_rxs = post.get("poll_reactions", {})

        if poll_pcts or poll_rxs:
            polls_with_pct += 1

        try:
            db.execute("""
                INSERT OR IGNORE INTO posts
                (search_id, platform, post_id, url, caption, image_url, posted_at, is_poll, poll_data, poll_reactions)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sid, plat, str(post.get("post_id", ""))[:200],
                post.get("url", ""), post.get("caption", ""),
                post.get("image_url", None), posted_at,
                1 if (is_poll_post(post.get("caption", "")) or poll_pcts or poll_rxs) else 0,
                json.dumps(poll_pcts) if poll_pcts else None,
                json.dumps(poll_rxs) if poll_rxs else None,
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

        reactions = post.get("reactions", {})
        if reactions:
            for rtype, rcount in reactions.items():
                try:
                    db.execute("INSERT OR IGNORE INTO reactions (post_id, reaction_type, count) VALUES (?, ?, ?)",
                               (pid, str(rtype).lower(), int(rcount)))
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
                url = post.get("url")
                rd = pf.fetch_reddit_data(url)
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

                        comments = pf.fetch_reddit_comments(url)
                        if comments:
                            analysis = pf.analyze_comments_for_candidates(comments, CANDIDATES)
                            if analysis:
                                db.execute("UPDATE posts SET poll_reactions=? WHERE id=?",
                                           (json.dumps({"reddit_comments": analysis}), pid))
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
        head_to_head = result.get("head_to_head", 0)
        st.header(f"🏆 Quien GANA en las Encuestas (vs directo, {head_to_head} comparaciones)")
        st.caption("Solo se cuentan encuestas donde aparecen 2+ candidatos con %. Las menciones unicas no cuentan como victoria.")
        num_cols = min(len(poll_wins), 4)
        cols = st.columns(num_cols)
        for i, (name, data) in enumerate(sorted(poll_wins.items(), key=lambda x: -x[1]["wins"])):
            with cols[i % num_cols]:
                st.metric(name, f"Gana {data['wins']}/{data['total_polls']}",
                          delta=f"+{data['avg_margin']} pts promedio")

    if poll_details:
        st.divider()
        st.header("📋 Encuestas con porcentajes")
        for pd_ in poll_details:
            pcts = pd_.get("percentages", {})
            sorted_p = sorted(pcts.items(), key=lambda x: -x[1])
            pcts_str = "  |  ".join(f"**{n}**: {v}%" for n, v in sorted_p)

            label = f"{'🥇' if pd_['winner'] == top else '📊'} {pd_['winner']}: {pd_['winner_pct']}% — {pd_.get('caption', '')[:80]}"
            with st.expander(label):
                st.markdown(pcts_str)
                margin_str = f"(+{pd_['margin']} puntos sobre el segundo)"
                eng_parts = []
                if pd_.get("likes"):
                    eng_parts.append(f"👍 {pd_['likes']} likes")
                if pd_.get("comments"):
                    eng_parts.append(f"💬 {pd_['comments']} comments")
                eng_str = " | ".join(eng_parts) if eng_parts else ""

                st.markdown(f"**Interpretacion:** {pd_['winner']} "
                            f"{'GANO' if pd_['margin'] > 0 else 'EMPATO'} "
                            f"con {pd_['winner_pct']}% "
                            f"{margin_str if pd_['margin'] > 0 else ''}")
                if eng_str:
                    st.markdown(eng_str)
                st.markdown(f"📎 [{pd_.get('url', '')[:120]}]({pd_.get('url', '')})")

    reaction_polls = result.get("reaction_polls", [])
    if reaction_polls:
        st.divider()
        st.header("🎭 Reddit: Comentarios reales analizados")
        st.caption("Comentarios extraidos via Reddit JSON API. Se cuentan menciones a cada candidato en los comentarios.")
        for rp_ in reaction_polls[:20]:
            analysis = rp_.get("reddit_comments_analysis", {})
            if not analysis:
                continue
            rp_label = f"🤖 Reddit — {rp_.get('caption', '')[:80]}"
            with st.expander(rp_label):
                st.markdown(f"**Menciones en comentarios:**")
                for ck, data in sorted(analysis.items(), key=lambda x: -x[1].get("mentions", 0)):
                    cname = CANDIDATES.get(ck, {}).get("name", ck)
                    avg_score = round(sum(data.get("comment_scores", [])) / max(len(data.get("comment_scores", [])), 1), 1)
                    st.markdown(f"- **{cname}**: {data['mentions']} menciones | promedio +{avg_score} pts por comentario")
                    for sc in data.get("sample_comments", []):
                        st.caption(f"  > {sc[:120]}")
                st.markdown(f"📎 [{rp_.get('url', '')[:120]}]({rp_.get('url', '')})")

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
