import pandas as pd
import json
from datetime import datetime, timedelta
from database.db import get_db
from config import CANDIDATES


class Aggregator:
    def __init__(self):
        self.db = get_db()

    def get_search_results(self, search_id):
        query = """
            SELECT p.id, p.platform, p.post_id, p.url, p.caption,
                   p.image_url, p.posted_at, p.scraped_at, p.is_poll,
                   p.poll_data, p.poll_reactions,
                   pc.candidate_key, pc.confidence, pc.detection_method,
                   c.name as candidate_name, c.party as candidate_party,
                   c.color as candidate_color
            FROM posts p
            LEFT JOIN post_candidates pc ON p.id = pc.post_id
            LEFT JOIN candidates c ON pc.candidate_key = c.key
            WHERE p.search_id = ?
            ORDER BY p.is_poll DESC, p.posted_at DESC
        """
        df = pd.read_sql_query(query, self.db, params=(search_id,))

        if df.empty:
            return self._empty()

        reactions_df = pd.read_sql_query(
            "SELECT post_id, reaction_type, count FROM reactions",
            self.db,
        )
        df["posted_at"] = pd.to_datetime(df["posted_at"], errors="coerce")
        df["scraped_at"] = pd.to_datetime(df["scraped_at"], errors="coerce")

        poll_rows = df[df["is_poll"] == 1].copy()
        all_posts_list = self._build_post_list(df, reactions_df)
        pct_polls, reaction_polls = self._analyze_polls(poll_rows, reactions_df)
        all_polls = pct_polls + reaction_polls
        rankings = self._rank_candidates(df, reactions_df)

        top = rankings[0]["candidate_name"] if rankings else "Sin datos"

        return {
            "search_id": search_id,
            "total_posts": len(df["id"].unique()),
            "total_poll_posts": int(poll_rows["id"].nunique()) if not poll_rows.empty else 0,
            "head_to_head": sum(1 for p in pct_polls if p.get("head_to_head")),
            "candidates_found": len(rankings),
            "all_posts": all_posts_list,
            "poll_details": pct_polls,
            "reaction_polls": reaction_polls,
            "poll_wins": self._summarize_wins(pct_polls),
            "top_candidate": top,
            "conclusion": self._conclusion(rankings, pct_polls, reaction_polls),
        }

    def _build_post_list(self, df, reactions_df):
        posts = []
        seen = set()
        for _, row in df.iterrows():
            pid = row["id"]
            if pid in seen:
                continue
            seen.add(pid)
            likes = 0
            comments = 0
            if not reactions_df.empty:
                rr = reactions_df[reactions_df["post_id"] == pid]
                likes = int(rr[rr["reaction_type"] == "like"]["count"].sum()) if not rr.empty else 0
                comments = int(rr[rr["reaction_type"] == "comments"]["count"].sum()) if not rr.empty else 0
            poll_data = row.get("poll_data")
            pcts = {}
            if poll_data and not pd.isna(poll_data):
                try:
                    pcts = json.loads(poll_data) if isinstance(poll_data, str) else poll_data
                except Exception:
                    pcts = {}
            winner = None
            margin = 0
            if pcts:
                sorted_p = sorted(pcts.items(), key=lambda x: -x[1])
                if sorted_p:
                    best_ck = sorted_p[0][0]
                    winner = CANDIDATES.get(best_ck, {}).get("name", best_ck)
                    if len(sorted_p) > 1:
                        margin = round(sorted_p[0][1] - sorted_p[1][1], 1)

            posts.append({
                "id": pid,
                "url": str(row.get("url", "")),
                "platform": str(row.get("platform", "web")),
                "caption": (str(row.get("caption", "")) or "")[:150],
                "poll_results": pcts,
                "winner": winner,
                "margin": margin,
                "likes": likes,
                "comments": comments,
                "is_poll": bool(row.get("is_poll", 0)),
                "candidate_name": row.get("candidate_name"),
                "posted_at": str(row.get("posted_at", ""))[:10],
            })
        return posts

    def _analyze_polls(self, poll_rows, reactions_df):
        pct_details = []
        reaction_details = []
        seen = set()

        for _, row in poll_rows.iterrows():
            pid = row["id"]
            if pid in seen:
                continue
            seen.add(pid)

            likes = 0
            comments = 0
            if not reactions_df.empty:
                rr = reactions_df[reactions_df["post_id"] == pid]
                likes = int(rr[rr["reaction_type"] == "like"]["count"].sum()) if not rr.empty else 0
                comments = int(rr[rr["reaction_type"] == "comments"]["count"].sum()) if not rr.empty else 0

            winner = None
            winner_pct = 0
            margin = 0
            num_candidates = 0
            pct_display = {}
            reddit_comments = {}

            poll_data = row.get("poll_data")
            if poll_data and not pd.isna(poll_data):
                try:
                    pcts = json.loads(poll_data) if isinstance(poll_data, str) else poll_data
                except Exception:
                    pcts = None
                if pcts:
                    sorted_items = sorted(pcts.items(), key=lambda x: -x[1])
                    best_ck = sorted_items[0][0]
                    num_candidates = len(sorted_items)
                    winner = CANDIDATES.get(best_ck, {}).get("name", best_ck) if num_candidates >= 2 else None
                    winner_pct = sorted_items[0][1]
                    margin = round(winner_pct - sorted_items[1][1], 1) if num_candidates > 1 else 0
                    pct_display = {}
                    for ck, pct in pcts.items():
                        pct_display[CANDIDATES.get(ck, {}).get("name", ck)] = pct

            rp = row.get("poll_reactions")
            if rp and not pd.isna(rp):
                try:
                    parsed = json.loads(rp) if isinstance(rp, str) else rp
                    if isinstance(parsed, dict) and "reddit_comments" in parsed:
                        reddit_comments = parsed["reddit_comments"]
                except Exception:
                    pass

            pct_details.append({
                "url": str(row.get("url", "")),
                "caption": str(row.get("caption", ""))[:200],
                "percentages": pct_display,
                "winner": winner,
                "winner_pct": winner_pct,
                "margin": margin,
                "likes": likes,
                "comments": comments,
                "type": "pct",
                "head_to_head": num_candidates >= 2,
                "reddit_comments_analysis": reddit_comments,
            })

        return pct_details, reaction_details

    def _summarize_wins(self, poll_details):
        wins = {}
        total_per_candidate = {}
        for pd_ in poll_details:
            w = pd_.get("winner")
            if not w or not pd_.get("head_to_head"):
                continue
            total_per_candidate[w] = total_per_candidate.get(w, 0) + 1
        for pd_ in poll_details:
            w = pd_.get("winner")
            if not w or not pd_.get("head_to_head"):
                continue
            wins.setdefault(w, {"wins": 0, "total_polls": total_per_candidate.get(w, 0), "margins": []})
            wins[w]["wins"] += 1
            wins[w]["margins"].append(pd_.get("margin", 0))
        for w in wins:
            ms = wins[w]["margins"]
            wins[w]["avg_margin"] = round(sum(ms) / len(ms), 1) if ms else 0.0
            del wins[w]["margins"]
        return wins

    def _rank_candidates(self, df, reactions_df):
        rankings = []
        for ck, info in CANDIDATES.items():
            cp = df[df["candidate_key"] == ck]
            total = len(cp["id"].unique())
            if total == 0:
                continue
            poll_ct = int(cp[cp["is_poll"] == 1]["id"].nunique())
            pids = cp["id"].unique().tolist()
            total_react = 0
            if not reactions_df.empty:
                total_react = int(reactions_df[reactions_df["post_id"].isin(pids)]["count"].sum())
            total_likes = 0
            if not reactions_df.empty:
                total_likes = int(reactions_df[(reactions_df["post_id"].isin(pids)) & (reactions_df["reaction_type"] == "like")]["count"].sum())
            rankings.append({
                "candidate_name": info["name"],
                "party": info["party"],
                "color": info["color"],
                "total_posts": total,
                "poll_posts": poll_ct,
                "total_likes": total_likes,
            })
        rankings.sort(key=lambda x: -x["total_posts"])
        max_score = max(r["total_posts"] for r in rankings) if rankings else 1
        for r in rankings:
            r["score"] = round(r["total_posts"] / max_score * 100, 1)
        return rankings

    def _conclusion(self, rankings, pct_polls, reaction_polls):
        if not rankings and not pct_polls and not reaction_polls:
            return "No se encontraron datos."

        lines = []
        total = sum(r["total_posts"] for r in rankings)
        lines.append(f"Analisis basado en {total} posts recolectados.\n")

        if pct_polls:
            wins = self._summarize_wins(pct_polls)
            lines.append("**Encuestas con porcentajes:**\n")
            for name, data in sorted(wins.items(), key=lambda x: -x[1]["wins"]):
                lines.append(
                    f"- **{name}**: gana en {data['wins']}/{data['total_polls']} "
                    f"({round(data['wins']/data['total_polls']*100)}%) "
                    f"| margen +{data['avg_margin']} pts\n"
                )

        if reaction_polls:
            comment_lines = []
            for rp_ in reaction_polls:
                analysis = rp_.get("reddit_comments_analysis", {})
                for ck, data in analysis.items():
                    cname = CANDIDATES.get(ck, {}).get("name", ck)
                    comment_lines.append((cname, data.get("mentions", 0)))
            if comment_lines:
                lines.append("\n**Analisis de comentarios en Reddit:**\n")
                by_candidate = {}
                for cname, mentions in comment_lines:
                    by_candidate[cname] = by_candidate.get(cname, 0) + mentions
                for cname, mentions in sorted(by_candidate.items(), key=lambda x: -x[1]):
                    lines.append(f"- **{cname}**: {mentions} menciones en comentarios\n")

        lines.append("\n**Presencia en plataformas:**\n")
        for r in rankings[:5]:
            lines.append(f"- {r['candidate_name']}: {r['total_posts']} posts, {r['poll_posts']} encuestas, {r['total_likes']} likes\n")

        lines.append("\n*Datos extraidos de fuentes publicas. Cada dato tiene URL verificable.*")
        return "".join(lines)

    def _empty(self):
        return {
            "search_id": None,
            "total_posts": 0,
            "total_poll_posts": 0,
            "head_to_head": 0,
            "candidates_found": 0,
            "all_posts": [],
            "poll_details": [],
            "reaction_polls": [],
            "poll_wins": {},
            "top_candidate": "Sin datos",
            "conclusion": "No se encontraron datos.",
        }
