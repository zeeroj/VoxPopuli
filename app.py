import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import json
import time

from config import CANDIDATES, PLATFORMS
from database.db import init_db, get_db
from scraper.web_searcher import WebSearcher
from scraper.instagram_scraper import InstagramScraper
from scraper.post_fetcher import fetch_post_engagement, extract_date_from_text
from analyzer.face_matcher import FaceMatcher
from analyzer.reaction_analyzer import calculate_engagement, is_engagement_poll
from analyzer.aggregator import Aggregator
from utils.helpers import build_search_query, is_poll_post

st.set_page_config(
    page_title="ConsultBot Presidencial 2027",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

os.environ["STREAMLIT_SUPPRESS_TORCH_WARNING"] = "1"


@st.cache_resource
def init_system():
    init_db()
    db = get_db()
    for key, info in CANDIDATES.items():
        db.execute(
            "INSERT OR IGNORE INTO candidates (key, name, party, color) VALUES (?, ?, ?, ?)",
            (key, info["name"], info["party"], info["color"]),
        )
    db.commit()
    return db


@st.cache_resource
def get_face_matcher():
    fm = FaceMatcher()
    return fm


PLATFORM_ICONS = {
    "instagram": "📷",
    "facebook": "📘",
    "twitter": "🐦",
    "tiktok": "🎵",
    "reddit": "🤖",
    "youtube": "▶️",
    "threads": "🧵",
    "web": "🌐",
}


def run_search(keywords, date_from, date_to, progress_callback=None):
    db = get_db()
    cursor = db.execute(
        "INSERT INTO searches (keywords, date_from, date_to, status) VALUES (?, ?, ?, ?)",
        (keywords, str(date_from) if date_from else None,
         str(date_to) if date_to else None, "running"),
    )
    search_id = cursor.lastrowid
    db.commit()

    keyword_list = build_search_query(keywords)
    all_posts = []
    total_steps = len(keyword_list) * 3
    step = 0

    web_searcher = WebSearcher()
    ig_scraper = None
    if PLATFORMS.get("instagram", {}).get("enabled", True):
        ig_scraper = InstagramScraper()

    for kw in keyword_list:
        step += 1
        if progress_callback:
            progress_callback(
                f"🌐 Buscando en TODAS las redes: '{kw}' ({step}/{total_steps})",
                step / total_steps
            )

        web_results = web_searcher.search_all_platforms(
            kw,
            max_per_platform=PLATFORMS.get("instagram", {}).get("max_posts_per_search", 25)
        )
        for p in web_results:
            p["keyword"] = kw
        all_posts.extend(web_results)

        if ig_scraper:
            step += 1
            if progress_callback:
                progress_callback(
                    f"📷 Instagram directo: '{kw}' ({step}/{total_steps})",
                    step / total_steps
                )
            try:
                ig_posts = ig_scraper.search(
                    kw, date_from, date_to,
                    PLATFORMS["instagram"]["max_posts_per_search"]
                )
                for p in ig_posts:
                    p["platform"] = "instagram"
                    p["keyword"] = kw
                all_posts.extend(ig_posts)
            except Exception:
                pass

    seen = set()
    unique_posts = []
    for p in all_posts:
        key = (p.get("platform", "unknown"), p.get("post_id", str(id(p))))
        if key not in seen:
            seen.add(key)
            unique_posts.append(p)

    return search_id, unique_posts, web_searcher


def download_image_for_post(image_url):
    import tempfile
    import requests
    from config import USER_AGENT, SCRAPER_TIMEOUT
    if not image_url:
        return None
    try:
        resp = requests.get(image_url, timeout=SCRAPER_TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.write(resp.content)
        tmp.close()
        return tmp.name
    except Exception:
        return None


def save_and_analyze(search_id, all_posts, face_matcher, ws, progress_callback=None):
    db = get_db()
    total = len(all_posts)
    platforms_found = {}
    enriched_count = 0
    real_date_count = 0

    for i, post in enumerate(all_posts):
        pct = (i + 1) / total if total > 0 else 1
        platform = post.get("platform", "web")
        platforms_found[platform] = platforms_found.get(platform, 0) + 1

        if progress_callback and i % 5 == 0:
            platforms_str = ", ".join(
                f"{PLATFORM_ICONS.get(p, '')} {p}({c})"
                for p, c in sorted(platforms_found.items(), key=lambda x: -x[1])[:4]
            )
            progress_callback(
                f"Enriqueciendo {i+1}/{total} | real={enriched_count} fechas={real_date_count} | {platforms_str}",
                pct
            )

        enriched = ws.enrich_post(post)
        if enriched.get('likes') or enriched.get('comments_count') or enriched.get('shares'):
            enriched_count += 1
        if enriched.get('posted_at'):
            real_date_count += 1

        posted_at = enriched.get("posted_at") or None

        try:
            db.execute("""
                INSERT OR IGNORE INTO posts
                (search_id, platform, post_id, url, caption, image_url, posted_at, is_poll, poll_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                search_id, platform, str(enriched.get("post_id", ""))[:200],
                enriched.get("url", ""), enriched.get("caption", ""),
                enriched.get("image_url", None), posted_at,
                1 if is_poll_post(enriched.get("caption", "")) else 0,
                json.dumps(enriched.get("poll_results", {})) if enriched.get("poll_results") else None,
            ))
        except Exception:
            continue

        post_row = db.execute(
            "SELECT id FROM posts WHERE platform=? AND post_id=?",
            (platform, str(enriched.get("post_id", ""))[:200])
        ).fetchone()

        if not post_row:
            continue
        post_db_id = post_row["id"]

        reactions = enriched.get("reactions", {})
        if reactions:
            for rtype, rcount in reactions.items():
                try:
                    db.execute(
                        "INSERT OR IGNORE INTO reactions (post_id, reaction_type, count) VALUES (?, ?, ?)",
                        (post_db_id, str(rtype).lower(), int(rcount or 0)),
                    )
                except Exception:
                    pass

        likes = enriched.get("likes", 0)
        comments = enriched.get("comments_count", 0)
        if likes:
            try:
                db.execute(
                    "INSERT OR IGNORE INTO reactions (post_id, reaction_type, count) VALUES (?, ?, ?)",
                    (post_db_id, 'like', int(likes)),
                )
            except Exception:
                pass
        if comments:
            try:
                db.execute(
                    "INSERT OR IGNORE INTO reactions (post_id, reaction_type, count) VALUES (?, ?, ?)",
                    (post_db_id, 'comments', int(comments)),
                )
            except Exception:
                pass

        image_url = enriched.get("image_url")
        if image_url:
            tmp = download_image_for_post(image_url)
            if tmp:
                identifications = face_matcher.identify_person(tmp)
                if os.path.exists(tmp):
                    os.unlink(tmp)

                for ident in identifications:
                    db.execute("""
                        INSERT OR IGNORE INTO post_candidates
                        (post_id, candidate_key, confidence, detection_method)
                        VALUES (?, ?, ?, ?)
                    """, (post_db_id, ident["candidate_key"], ident["confidence"], "face_recognition"))

        caption = enriched.get("caption", "") or ""
        caption_lower = caption.lower()
        for candidate_key, info in CANDIDATES.items():
            terms_to_check = list(info.get("search_terms", []))
            terms_to_check.append(info["name"])
            for kw in info.get("keywords", []):
                terms_to_check.append(kw)
            terms_to_check = list(set(t.lower().replace("#", "") for t in terms_to_check))
            for term in terms_to_check:
                if term and term in caption_lower:
                    existing = db.execute(
                        "SELECT id FROM post_candidates WHERE post_id=? AND candidate_key=?",
                        (post_db_id, candidate_key)
                    ).fetchone()
                    if not existing:
                        db.execute("""
                            INSERT OR IGNORE INTO post_candidates
                            (post_id, candidate_key, confidence, detection_method)
                            VALUES (?, ?, ?, ?)
                        """, (post_db_id, candidate_key, 0.7, "text_match"))
                    break

    db.commit()
    db.execute("UPDATE searches SET status='completed' WHERE id=?", (search_id,))
    db.commit()


def main():
    db = init_system()
    face_matcher = get_face_matcher()

    st.title("🔍 ConsultBot Presidencial 2027")
    st.caption("Busca en TODAS las redes sociales — sin login, sin cookies, 100% publico")

    with st.sidebar:
        st.header("⚙️ Configuracion")

        st.subheader("Candidatos activos")
        selected_candidates = []
        for key, info in CANDIDATES.items():
            if st.checkbox(f"{info['name']} ({info['party']})", value=True, key=f"cand_{key}"):
                selected_candidates.append(key)

        st.divider()

        st.subheader("Plataformas a buscar")
        for platform_key, platform_conf in PLATFORMS.items():
            icon = PLATFORM_ICONS.get(platform_key, "")
            enabled = st.checkbox(
                f"{icon} {platform_key.title()}",
                value=platform_conf.get("enabled", True),
                key=f"plat_{platform_key}"
            )
            PLATFORMS[platform_key]["enabled"] = enabled

        st.divider()

        st.subheader("Reconocimiento Facial")
        if st.button("🔄 Descargar fotos de referencia"):
            with st.spinner("Buscando y descargando fotos de cada candidato..."):
                face_matcher.ensure_candidate_encodings()
            st.success("Modelo facial entrenado con exito")
            st.cache_resource.clear()

        st.divider()
        st.caption("🔓 Sin cookies. Sin login. Datos 100% publicos.")
        st.caption(f"Plataformas: {', '.join(p for p in PLATFORMS if PLATFORMS[p].get('enabled'))}")

    col1, col2, col3 = st.columns([4, 2, 2])
    with col1:
        keywords = st.text_input(
            "🔎 Keywords de busqueda",
            placeholder="milei, kicillof, bullrich, massa, macri...",
            help="Separa con comas. Busca en Instagram, Facebook, Twitter/X, TikTok, Reddit, YouTube."
        )
    with col2:
        date_from = st.date_input(
            "Desde",
            value=datetime.now() - timedelta(days=30),
            max_value=datetime.now(),
        )
    with col3:
        date_to = st.date_input(
            "Hasta",
            value=datetime.now(),
            max_value=datetime.now(),
        )

    search_clicked = st.button("🔍 Buscar y Analizar", type="primary", use_container_width=True)

    if "search_history" not in st.session_state:
        st.session_state.search_history = []
    if "current_result" not in st.session_state:
        st.session_state.current_result = None

    if search_clicked and keywords.strip():
        face_matcher.ensure_candidate_encodings()

        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_progress(msg, pct):
            status_text.text(msg)
            progress_bar.progress(min(pct, 1.0))

        with st.spinner("Buscando en todas las redes sociales..."):
            update_progress("🌐 Iniciando busqueda masiva...", 0.0)
            search_id, all_posts, ws = run_search(keywords, date_from, date_to, update_progress)

        platforms_count = {}
        for p in all_posts:
            plat = p.get("platform", "web")
            platforms_count[plat] = platforms_count.get(plat, 0) + 1
        platforms_str = " | ".join(
            f"{PLATFORM_ICONS.get(p, '')} {p}: {c}"
            for p, c in sorted(platforms_count.items())
        )
        st.info(f"Se encontraron **{len(all_posts)}** resultados. {platforms_str}")

        save_and_analyze(search_id, all_posts, face_matcher, ws, update_progress)

        aggregator = Aggregator()
        result = aggregator.get_search_results(search_id)

        progress_bar.progress(1.0)
        status_text.text("Analisis completado!")
        st.session_state.current_result = result
        st.session_state.search_history.append({
            "keywords": keywords,
            "date_from": str(date_from),
            "date_to": str(date_to),
            "result": result,
        })

    result = st.session_state.current_result

    if result:
        st.divider()
        st.header("📊 Resultados del Analisis")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Posts", result.get("total_posts_scraped", 0))
        with col2:
            st.metric("Encuestas Detectadas", result.get("total_poll_posts", 0))
        with col3:
            st.metric("Candidatos Encontrados", result.get("candidates_found", 0))
        with col4:
            top = result.get("top_candidate", "N/A")
            st.metric("Lider", top)

        real_dates = result.get("posts_with_real_dates", 0)
        total_posts = result.get("total_posts_scraped", 0)
        if total_posts > 0:
            st.caption(f"🔍 {real_dates}/{total_posts} posts con fecha real observada. "
                       f"Solo se usan datos extraidos directamente de cada URL.")

        st.divider()

        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.subheader("🏆 Ranking de Candidatos")
            rankings = result.get("candidate_rankings", [])
            if rankings:
                fig = go.Figure()
                names = [r["candidate_name"] for r in rankings[:10]]
                scores = [r["normalized_score"] for r in rankings[:10]]
                colors = [r["color"] for r in rankings[:10]]

                fig.add_trace(go.Bar(
                    y=names[::-1],
                    x=scores[::-1],
                    orientation='h',
                    marker_color=colors[::-1],
                    text=[f"{s}%" for s in scores[::-1]],
                    textposition='outside',
                    name="Engagement Score",
                ))

                fig.update_layout(
                    height=400,
                    margin=dict(l=0, r=80, t=0, b=0),
                    xaxis_title="Score Normalizado (%)",
                    showlegend=False,
                )
                st.plotly_chart(fig, use_container_width=True)

                st.subheader("📋 Detalle por candidato")
                detail_data = []
                for r in rankings[:10]:
                    detail_data.append({
                        "Candidato": r["candidate_name"],
                        "Partido": r["party"],
                        "Score": f"{r['normalized_score']}%",
                        "Posts Totales": r["total_posts"],
                        "Encuestas": r["poll_posts"],
                        "Reacciones": r["total_reactions"],
                        "FB": r.get("facebook_posts", 0),
                        "IG": r.get("instagram_posts", 0),
                    })
                st.dataframe(pd.DataFrame(detail_data), use_container_width=True, hide_index=True)
            else:
                st.info("Sin datos de ranking.")

        with col_right:
            st.subheader("📈 Tendencia Temporal")
            timeline = result.get("timeline", [])
            if timeline:
                tl_df = pd.DataFrame(timeline)
                if not tl_df.empty:
                    available_candidates = tl_df["candidate_name"].unique()
                    selected_tl = st.multiselect(
                        "Filtrar candidatos",
                        options=list(available_candidates),
                        default=list(available_candidates)[:5],
                        key="tl_filter",
                    )
                    filtered_tl = tl_df[tl_df["candidate_name"].isin(selected_tl)]
                    if not filtered_tl.empty:
                        fig2 = px.line(
                            filtered_tl,
                            x="date",
                            y="count",
                            color="candidate_name",
                            markers=True,
                            height=400,
                        )
                        fig2.update_layout(
                            margin=dict(l=0, r=0, t=0, b=0),
                            xaxis_title="Fecha",
                            yaxis_title="Menciones",
                            legend_title="",
                        )
                        st.plotly_chart(fig2, use_container_width=True)

            st.subheader("📱 Desglose por plataforma")
            platform_data = result.get("platform_breakdown", [])
            if platform_data:
                fig3 = px.pie(
                    pd.DataFrame(platform_data),
                    values="total_posts",
                    names="platform",
                    height=300,
                    hole=0.4,
                )
                fig3.update_layout(margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(fig3, use_container_width=True)

        st.divider()
        st.header("🧠 Conclusion")
        conclusion = result.get("conclusion", "")
        if conclusion:
            st.markdown(conclusion)

    if st.session_state.search_history:
        st.divider()
        st.subheader("📜 Historial de busquedas")
        for h in reversed(st.session_state.search_history[-5:]):
            with st.expander(f"Busqueda: {h['keywords']} ({h['date_from']} » {h['date_to']})"):
                r = h.get("result", {})
                if r.get("candidate_rankings"):
                    mini_df = pd.DataFrame(r["candidate_rankings"])[
                        ["candidate_name", "normalized_score", "total_posts", "poll_posts"]
                    ].head(5)
                    st.dataframe(mini_df, hide_index=True)
                else:
                    st.caption("Sin resultados.")


if __name__ == "__main__":
    main()
