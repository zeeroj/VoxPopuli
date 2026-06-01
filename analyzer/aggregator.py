import pandas as pd
from datetime import datetime, timedelta
from database.db import get_db
from config import CANDIDATES


class Aggregator:
    def __init__(self):
        self.db = get_db()

    def get_search_results(self, search_id):
        query = """
            SELECT
                p.id, p.platform, p.post_id, p.url, p.caption,
                p.image_url, p.posted_at, p.scraped_at, p.is_poll,
                pc.candidate_key, pc.confidence, pc.detection_method,
                c.name as candidate_name, c.party as candidate_party,
                c.color as candidate_color
            FROM posts p
            LEFT JOIN post_candidates pc ON p.id = pc.post_id
            LEFT JOIN candidates c ON pc.candidate_key = c.key
            WHERE p.search_id = ?
            ORDER BY p.posted_at DESC
        """
        df = pd.read_sql_query(query, self.db, params=(search_id,))

        if df.empty:
            return self._empty_summary()

        df["posted_at"] = pd.to_datetime(df["posted_at"], errors="coerce")
        df["scraped_at"] = pd.to_datetime(df["scraped_at"], errors="coerce")
        df["posted_at"] = df["posted_at"].fillna(df["scraped_at"])
        df["posted_at"] = df["posted_at"].fillna(datetime.utcnow())

        return self._build_summary(df, search_id)

    def _build_summary(self, df, search_id):
        reactions_df = pd.read_sql_query(
            "SELECT post_id, reaction_type, count FROM reactions",
            self.db,
        )

        candidate_metrics = []
        for candidate_key, info in CANDIDATES.items():
            candidate_posts = df[df["candidate_key"] == candidate_key]

            post_ids = candidate_posts["id"].tolist()
            candidate_reactions = (
                reactions_df[reactions_df["post_id"].isin(post_ids)]
                if not reactions_df.empty
                else pd.DataFrame()
            )

            total_posts = len(candidate_posts)
            poll_posts = len(candidate_posts[candidate_posts["is_poll"] == 1])
            total_reactions = (
                int(candidate_reactions["count"].sum())
                if not candidate_reactions.empty
                else 0
            )
            avg_confidence = (
                round(candidate_posts["confidence"].mean(), 3)
                if total_posts > 0
                else 0.0
            )

            fb_posts = len(candidate_posts[candidate_posts["platform"] == "facebook"])
            ig_posts = len(candidate_posts[candidate_posts["platform"] == "instagram"])

            candidate_metrics.append({
                "candidate_key": candidate_key,
                "candidate_name": info["name"],
                "party": info["party"],
                "color": info["color"],
                "total_posts": total_posts,
                "poll_posts": poll_posts,
                "total_reactions": total_reactions,
                "avg_confidence": avg_confidence,
                "facebook_posts": fb_posts,
                "instagram_posts": ig_posts,
            })

        metrics_df = pd.DataFrame(candidate_metrics)
        metrics_df["engagement_score"] = (
            metrics_df["total_reactions"] * 0.5
            + metrics_df["poll_posts"] * 10
            + metrics_df["total_posts"] * 2
        )

        if not metrics_df.empty and metrics_df["engagement_score"].max() > 0:
            max_score = metrics_df["engagement_score"].max()
            metrics_df["normalized_score"] = (
                metrics_df["engagement_score"] / max_score * 100
            ).round(1)
        else:
            metrics_df["normalized_score"] = 0.0

        metrics_df = metrics_df.sort_values("normalized_score", ascending=False)

        platform_breakdown = (
            df.groupby("platform")
            .agg(
                total_posts=("id", "count"),
                poll_posts=("is_poll", "sum"),
                unique_candidates=("candidate_key", "nunique"),
            )
            .reset_index()
        )

        timeline = self._build_timeline(df)

        top_candidate = (
            metrics_df.iloc[0]["candidate_name"]
            if not metrics_df.empty
            else "Sin datos"
        )
        top_score = (
            metrics_df.iloc[0]["normalized_score"]
            if not metrics_df.empty
            else 0.0
        )

        return {
            "search_id": search_id,
            "total_posts_scraped": len(df),
            "total_poll_posts": int(df["is_poll"].sum()),
            "candidates_found": int(df["candidate_key"].nunique()),
            "platform_breakdown": platform_breakdown.to_dict("records"),
            "candidate_rankings": metrics_df.to_dict("records"),
            "timeline": timeline,
            "top_candidate": top_candidate,
            "top_score": top_score,
            "conclusion": self._generate_conclusion(metrics_df),
        }

    def _build_timeline(self, df):
        if df.empty:
            return []
        valid_dates = df["posted_at"].dropna()
        if valid_dates.empty:
            return []
        df["date"] = valid_dates.dt.date
        df = df.dropna(subset=["date"])
        timeline = (
            df.groupby(["date", "candidate_key"])
            .size()
            .reset_index(name="count")
        )
        timeline["candidate_name"] = timeline["candidate_key"].apply(
            lambda k: CANDIDATES.get(k, {}).get("name", k) if k else "Desconocido"
        )
        timeline["date"] = timeline["date"].astype(str)
        return timeline.sort_values("date").to_dict("records")

    def _generate_conclusion(self, metrics_df):
        if metrics_df.empty:
            return "No se encontraron datos suficientes para sacar una conclusión."

        top3 = metrics_df.head(3).to_dict("records")
        total_posts = metrics_df["total_posts"].sum()

        conclusion_parts = []
        conclusion_parts.append(f"Análisis basado en {int(total_posts)} posts recolectados.\n\n")

        conclusion_parts.append("**Ranking de engagement:**\n")
        for i, c in enumerate(top3, 1):
            conclusion_parts.append(
                f"{i}. **{c['candidate_name']}** ({c['party']}) — "
                f"Score: {c['normalized_score']}% | "
                f"{c['total_posts']} posts | "
                f"{c['poll_posts']} encuestas | "
                f"{c['total_reactions']} reacciones\n"
            )

        conclusion_parts.append(f"\n**Conclusión:** ")
        top = top3[0]
        if len(top3) > 1:
            gap = top['normalized_score'] - top3[1]['normalized_score']
            if gap > 20:
                conclusion_parts.append(
                    f"{top['candidate_name']} lidera con una ventaja significativa "
                    f"({gap:.0f}% más engagement)."
                )
            elif gap > 5:
                conclusion_parts.append(
                    f"{top['candidate_name']} lidera con ventaja moderada "
                    f"({gap:.0f}% más). {top3[1]['candidate_name']} le sigue de cerca."
                )
            else:
                conclusion_parts.append(
                    f"Competencia reñida entre {top['candidate_name']} y "
                    f"{top3[1]['candidate_name']} (diferencia de solo {gap:.0f}%)."
                )
        else:
            conclusion_parts.append(
                f"{top['candidate_name']} es el único candidato detectado en los datos."
            )

        conclusion_parts.append(
            f"\n\n*Datos recolectados con web scraping. Los resultados reflejan "
            f"tendencias en redes sociales, no una predicción electoral.*"
        )

        return "".join(conclusion_parts)

    def _empty_summary(self):
        return {
            "search_id": None,
            "total_posts_scraped": 0,
            "total_poll_posts": 0,
            "candidates_found": 0,
            "platform_breakdown": [],
            "candidate_rankings": [],
            "timeline": [],
            "top_candidate": "Sin datos",
            "top_score": 0.0,
            "conclusion": "No se encontraron datos. Intentá con otros keywords o rango de fechas.",
        }
