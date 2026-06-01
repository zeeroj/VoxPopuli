from config import REACTION_MAP, ENGAGEMENT_WEIGHTS


def analyze_reactions(reactions_dict):
    if not reactions_dict:
        return {
            "total_raw": 0,
            "weighted_score": 0.0,
            "breakdown": {},
        }

    breakdown = {}
    total_weighted = 0.0
    total_raw = 0

    for reaction_type, count in reactions_dict.items():
        count_int = int(count) if count else 0
        if count_int <= 0:
            continue
        weight = REACTION_MAP.get(reaction_type, 1.0)
        key = reaction_type.lower().replace(" ", "_")
        breakdown[key] = {
            "count": count_int,
            "weight": weight,
            "weighted": count_int * weight,
        }
        total_raw += count_int
        total_weighted += count_int * weight

    return {
        "total_raw": total_raw,
        "weighted_score": round(total_weighted, 1),
        "breakdown": breakdown,
    }


def calculate_engagement(post_data):
    reactions_analysis = analyze_reactions(post_data.get("reactions", {}))

    likes = int(post_data.get("likes", 0) or 0)
    comments = int(post_data.get("comments_count", 0) or 0)
    shares = int(post_data.get("shares", 0) or 0)

    weighted_reactions = reactions_analysis.get("weighted_score", likes)
    if weighted_reactions == 0 and likes > 0:
        weighted_reactions = likes

    engagement = (
        weighted_reactions * ENGAGEMENT_WEIGHTS["reactions"]
        + comments * ENGAGEMENT_WEIGHTS["comments"]
        + shares * ENGAGEMENT_WEIGHTS["shares"]
    )

    return {
        "engagement_score": round(engagement, 1),
        "reactions": reactions_analysis,
        "comments": comments,
        "shares": shares,
        "likes": likes,
    }


def is_engagement_poll(post_data):
    caption = (post_data.get("caption") or "").lower()
    reactions = post_data.get("reactions", {}) or {}
    likes = int(post_data.get("likes", 0) or 0)
    comments = int(post_data.get("comments_count", 0) or 0)

    poll_score = 0
    poll_keywords = [
        "votá", "vota", "vote", "votar", "encuesta", "poll",
        "like si", "corazón si", "me encanta si", "me divierte si",
        "reaccioná", "reacciona", "compartí si", "opiná", "opina",
        "quién prefer", "quien prefer", "elegí", "elige",
        "dejá tu voto", "deja tu voto",
    ]
    for kw in poll_keywords:
        if kw in caption:
            poll_score += 1

    if likes > 100:
        poll_score += 0.5
    if comments > 20:
        poll_score += 0.5

    has_multiple_reactions = len(reactions) >= 2
    if has_multiple_reactions:
        poll_score += 1

    return poll_score >= 1
