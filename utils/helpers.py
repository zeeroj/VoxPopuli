from datetime import datetime, timedelta
import re


def safe_get(d, key, default=None):
    if hasattr(d, 'get'):
        return d.get(key, default)
    try:
        return d[key]
    except (TypeError, KeyError, IndexError):
        return default


def parse_date(date_str):
    if not date_str:
        return None
    if isinstance(date_str, datetime):
        return date_str
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(str(date_str).strip(), fmt)
        except ValueError:
            continue
    return None


def is_poll_post(caption):
    if not caption:
        return False
    caption_lower = caption.lower()
    poll_keywords = [
        "votá", "vota", "vote", "votar", "votacion", "votación",
        "encuesta", "poll", "encuestar",
        "reaccioná", "reacciona", "reaction", "reaccionar",
        "like si", "corazón si", "me encanta si", "me divierte si",
        "compartí si", "compartir si",
        "dejá tu voto", "deja tu voto",
        "elegí", "elige", "elegir",
        "quién prefieren", "quien prefieren",
        "opiná", "opina", "opinar",
        "qué opinás", "que opinas",
        "a quién votarías", "a quien votarias",
        "quién gana", "quien gana",
    ]
    match_count = sum(1 for kw in poll_keywords if kw in caption_lower)
    return match_count >= 1


def extract_hashtags(text):
    if not text:
        return []
    return re.findall(r'#(\w+)', text)


def extract_mentions(text):
    if not text:
        return []
    return re.findall(r'@(\w+)', text)


def build_search_query(keywords, date_from=None, date_to=None):
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]
    return keywords
