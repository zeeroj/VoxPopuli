import re
import json
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from config import USER_AGENT, SCRAPER_TIMEOUT


def parse_relative_date(text):
    if not text:
        return None
    now = datetime.now()
    text = text.lower().strip()
    match = re.search(
        r'(\d+)\s*(segundo|minuto|hora|dia|día|semana|mes|año|year|month|week|day|hour|minute|second)s?\s*(?:ago|atr[áa]s|atras)?',
        text
    )
    if match:
        num = int(match.group(1))
        unit = match.group(2)
        unit_map = {
            'segundo': 'seconds', 'second': 'seconds',
            'minuto': 'minutes', 'minute': 'minutes',
            'hora': 'hours', 'hour': 'hours',
            'dia': 'days', 'día': 'days', 'day': 'days',
            'semana': 'weeks', 'week': 'weeks',
            'mes': 'months', 'month': 'months',
            'año': 'years', 'year': 'years',
        }
        delta_unit = unit_map.get(unit)
        if delta_unit:
            if delta_unit == 'months':
                num *= 30
                delta_unit = 'days'
            elif delta_unit == 'years':
                num *= 365
                delta_unit = 'days'
            return (now - timedelta(**{delta_unit: num})).isoformat()
    return None


MONTH_MAP = {
    'ene': 1, 'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'abr': 4,
    'may': 5, 'jun': 6, 'jul': 7, 'ago': 8, 'aug': 8, 'sep': 9, 'set': 9,
    'oct': 10, 'nov': 11, 'dic': 12, 'dec': 12
}


def extract_date_from_text(text):
    if not text:
        return None
    relative = parse_relative_date(text)
    if relative:
        return relative
    patterns = [
        r'(\w{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})',
        r'(\d{1,2})\s+de\s+(\w{3,9})\.?\s+de\s+(\d{4})',
        r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            g1, g2, g3 = match.group(1), match.group(2), match.group(3)
            if g1.isalpha():
                month = MONTH_MAP.get(g1.lower()[:3])
                if month is None: continue
                day, year = int(g2), int(g3)
            elif g2.isalpha():
                month = MONTH_MAP.get(g2.lower()[:3])
                if month is None: continue
                day, year = int(g1), int(g3)
            else:
                day, month, year = int(g1), int(g2), int(g3)
            if 1 <= month <= 12 and 1 <= day <= 31 and 2000 <= year <= 2030:
                return datetime(year, month, day).isoformat()
        except (ValueError, IndexError):
            continue
    return None


def fetch_reddit_data(url):
    if not url or 'reddit.com' not in url:
        return None
    json_url = url.rstrip('/') + '.json'
    headers = {'User-Agent': USER_AGENT}
    try:
        resp = requests.get(json_url, headers=headers, timeout=SCRAPER_TIMEOUT)
        if resp.status_code != 200:
            return None
        data = resp.json()
        post_data = data[0]['data']['children'][0]['data']
        created = datetime.fromtimestamp(post_data.get('created_utc', 0))
        return {
            'likes': post_data.get('score', 0),
            'comments_count': post_data.get('num_comments', 0),
            'shares': 0,
            'image_url': post_data.get('url', '') if not post_data.get('is_self', True) else None,
            'posted_at': created.isoformat(),
            'caption': ((post_data.get('title', '') or '') + '\n' + (post_data.get('selftext', '') or ''))[:2000],
            'reactions': {},
            'subreddit': post_data.get('subreddit', ''),
            'upvote_ratio': post_data.get('upvote_ratio', 0),
        }
    except Exception:
        return None


def fetch_reddit_comments(url):
    if not url or 'reddit.com' not in url:
        return None
    json_url = url.rstrip('/') + '.json'
    headers = {'User-Agent': USER_AGENT}
    try:
        resp = requests.get(json_url, headers=headers, timeout=SCRAPER_TIMEOUT)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if len(data) < 2:
            return None
        comments_data = data[1]['data']['children']
        comments = []
        for child in comments_data[:50]:
            if child['kind'] != 't1':
                continue
            cd = child['data']
            body = cd.get('body', '')
            if not body or body in ('[removed]', '[deleted]'):
                continue
            comments.append({
                'body': body[:500],
                'score': cd.get('score', 0),
                'author': cd.get('author', ''),
                'created_utc': cd.get('created_utc', 0),
            })
        return comments
    except Exception:
        return None


def analyze_comments_for_candidates(comments, candidate_config):
    if not comments or not candidate_config:
        return {}

    candidate_names = {}
    for ck, info in candidate_config.items():
        names = [info["name"].lower()]
        names.extend(k.lower() for k in info.get("keywords", []))
        names.extend(t.lower().replace("#", "") for t in info.get("search_terms", []))
        candidate_names[ck] = list(set(names))

    results = {}
    for comment in comments:
        body = comment.get('body', '').lower()
        score = comment.get('score', 0)
        for ck, names in candidate_names.items():
            for name in names:
                if name and name in body:
                    results.setdefault(ck, {"mentions": 0, "comment_scores": [], "sample_comments": []})
                    results[ck]["mentions"] += 1
                    results[ck]["comment_scores"].append(score)
                    if len(results[ck]["sample_comments"]) < 5:
                        results[ck]["sample_comments"].append(comment.get('body', '')[:200])
                    break
    return results


def fetch_page_meta(url):
    headers = {'User-Agent': USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=SCRAPER_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        posted_at = None
        description = ''
        image_url = None
        for meta in soup.find_all('meta'):
            prop = (meta.get('property') or meta.get('name') or '').lower()
            content = meta.get('content', '')
            if prop in ('article:published_time', 'og:published_time'):
                posted_at = content
            elif prop in ('og:description', 'description') and not description:
                description = content
            elif prop == 'og:image' and not image_url:
                image_url = content
        title_tag = soup.find('title')
        title = title_tag.get_text(strip=True) if title_tag else ''
        for time_tag in soup.find_all('time'):
            dt = time_tag.get('datetime')
            if dt:
                posted_at = posted_at or dt
                break
        return {
            'posted_at': posted_at,
            'caption': ((title or '') + '\n' + description).strip()[:2000],
            'image_url': image_url,
            'likes': 0,
            'comments_count': 0,
            'shares': 0,
            'reactions': {},
        }
    except Exception:
        return None
