import time
import re
import random
import hashlib
from urllib.parse import urlparse
from ddgs import DDGS
from config import CANDIDATES

SOCIAL_PLATFORMS = {
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "fb.watch": "facebook",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "tiktok.com": "tiktok",
    "vm.tiktok.com": "tiktok",
    "reddit.com": "reddit",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "linkedin.com": "linkedin",
    "threads.net": "threads",
    "t.me": "telegram",
}

SEARCH_STRATEGIES = [
    '"{keyword}" encuesta presidencial 2027 porcentaje',
    '"{keyword}" intencion voto 2027',
    '"{keyword}" vs encuesta balotaje',
    '"{keyword}" sondeo elecciones argentina',
    '"{keyword}" encuesta quien gana',
    '"{keyword}" instagram facebook encuesta reacciones',
    '"{keyword}" reddit encuesta votacion',
    '"{keyword}" tiktok encuesta tendencia',
    '"{keyword}" twitter encuesta presidencial',
    '"{keyword}" youtube encuesta elecciones',
    '"{keyword}" encuesta gana pierde 2027',
    '"{keyword}" encuesta votacion likes comentarios',
    '"{keyword}" medicion encuesta presidencial',
    '"{keyword}" rechazo aprobacion encuesta 2027',
    '"{keyword}" scaneo intencion voto argentina',
]


def detect_platform(url):
    if not url:
        return None
    try:
        domain = urlparse(url).netloc.lower()
        domain = domain.removeprefix("www.")
        for key, platform in SOCIAL_PLATFORMS.items():
            if key in domain:
                return platform
    except Exception:
        pass
    return None


def extract_post_id(url, platform):
    if not url:
        return None
    patterns = {
        "instagram": r"instagram\.com/(?:p|reel)/([^/?&]+)",
        "facebook": r"facebook\.com/[^/]+/(?:posts|videos|photos|permalink\.php\?story_fbid=)([^/?&]+)",
        "twitter": r"(?:twitter\.com|x\.com)/\w+/status/(\d+)",
        "tiktok": r"tiktok\.com/@[\w.-]+/video/(\d+)",
        "reddit": r"reddit\.com/r/\w+/comments/(\w+)",
        "youtube": r"(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]+)",
    }
    pattern = patterns.get(platform)
    if not pattern:
        return hashlib.md5(url.encode()).hexdigest()[:16]
    match = re.search(pattern, url)
    return match.group(1) if match else hashlib.md5(url.encode()).hexdigest()[:16]


def extract_poll_percentages(text):
    if not text:
        return {}
    text_lower = text.lower()
    candidate_names = {}
    for ck, info in CANDIDATES.items():
        names = [info["name"].lower()]
        names.extend(k.lower() for k in info.get("keywords", []))
        names.extend(t.lower().replace("#", "") for t in info.get("search_terms", []))
        candidate_names[ck] = list(set(names))

    pct_pattern = r'(\d{1,3})[.,](\d{1,2})?\s*%'
    pct_matches = list(re.finditer(pct_pattern, text_lower))

    assigned_pcts = set()
    results = {}
    for ck, names in candidate_names.items():
        best_pct = None
        best_dist = float('inf')
        best_match_idx = None
        for name in names:
            for m in re.finditer(re.escape(name), text_lower):
                pos = m.start()
                for idx, pct_match in enumerate(pct_matches):
                    if idx in assigned_pcts:
                        continue
                    dist = abs(pct_match.start() - pos)
                    if dist < best_dist and dist < 400:
                        best_dist = dist
                        best_match_idx = idx
                        try:
                            whole = pct_match.group(1)
                            decimal = pct_match.group(2) or '0'
                            best_pct = float(f"{whole}.{decimal}")
                        except ValueError:
                            continue
        if best_pct is not None and best_match_idx is not None:
            results[ck] = best_pct
            assigned_pcts.add(best_match_idx)

    return results


def extract_engagement_from_text(text):
    if not text:
        return 0, 0, 0
    likes = 0
    comments = 0
    shares = 0
    text_lower = text.lower()

    like_patterns = [
        r'(\d+[.,]?\d*)\s*[kK]\s*(?:like|me\s*gusta|reacciones?)',
        r'(\d+[.,]?\d*)\s*[mM]\s*(?:like|me\s*gusta|reacciones?)',
        r'(?:like|me\s*gusta|reacciones?)[:\s]*(\d+[.,]?\d*)\s*[kKmM]?',
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:like|me\s*gusta)s?',
    ]
    for pat in like_patterns:
        m = re.search(pat, text_lower)
        if m:
            likes = _parse_social_count(m.group(1))
            break

    comment_patterns = [
        r'(\d+[.,]?\d*)\s*[kK]\s*(?:comentario|comment)',
        r'(\d+[.,]?\d*)\s*[mM]\s*(?:comentario|comment)',
        r'(?:comentario|comment)s?[:\s]*(\d+[.,]?\d*)\s*[kKmM]?',
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?)\s*(?:comentario|comment)s?',
    ]
    for pat in comment_patterns:
        m = re.search(pat, text_lower)
        if m:
            comments = _parse_social_count(m.group(1))
            break

    share_patterns = [
        r'(\d+[.,]?\d*)\s*[kK]\s*(?:compart|share|retweet|repost)',
        r'(?:compart|share|retweet|repost)s?[:\s]*(\d+[.,]?\d*)\s*[kKmM]?',
    ]
    for pat in share_patterns:
        m = re.search(pat, text_lower)
        if m:
            shares = _parse_social_count(m.group(1))
            break

    return likes, comments, shares


def _parse_social_count(text):
    if not text:
        return 0
    text = str(text).replace(',', '').replace(' ', '').upper()
    try:
        if 'K' in text:
            return int(float(text.replace('K', '')) * 1000)
        elif 'M' in text:
            return int(float(text.replace('M', '')) * 1_000_000)
        else:
            return int(float(text))
    except (ValueError, TypeError):
        return 0


class WebSearcher:
    def __init__(self):
        self._last_request = 0
        self._ddgs = DDGS()

    def _rate_limit(self, min_seconds=1.0):
        elapsed = time.time() - self._last_request
        if elapsed < min_seconds:
            time.sleep(min_seconds - elapsed + random.uniform(0.1, 0.6))
        self._last_request = time.time()

    def search_all_platforms(self, keyword, max_per_platform=25):
        all_results = []
        seen_urls = set()

        for strategy in SEARCH_STRATEGIES:
            query = strategy.format(keyword=keyword)[:300]
            self._rate_limit()

            try:
                search_results = list(self._ddgs.text(query, max_results=max_per_platform))
            except Exception:
                continue

            for r in search_results:
                url = r.get("href", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                platform = detect_platform(url)
                post_id = extract_post_id(url, platform)

                title = r.get("title", "") or ""
                body = r.get("body", "") or ""
                caption = f"{title}\n{body}"[:2000]

                likes, comments, shares = extract_engagement_from_text(body)

                results_entry = {
                    "post_id": str(post_id),
                    "platform": platform or "web",
                    "url": url,
                    "caption": caption,
                    "image_url": None,
                    "posted_at": None,
                    "is_poll": False,
                    "likes": likes,
                    "comments_count": comments,
                    "shares": shares,
                    "reactions": {"like": likes, "comments": comments} if likes or comments else {},
                    "poll_results": extract_poll_percentages(title + " " + body),
                    "source": "web_search",
                    "keyword": keyword,
                }

                all_results.append(results_entry)

        return all_results

    def enrich_post(self, post):
        from scraper.post_fetcher import fetch_reddit_data, fetch_page_meta
        platform = post.get("platform")
        url = post.get("url")

        if platform == "reddit" and url:
            data = fetch_reddit_data(url)
            if data:
                post["likes"] = data.get("likes", 0)
                post["comments_count"] = data.get("comments_count", 0)
                post["reactions"] = {"upvotes": data.get("likes", 0), "comments": data.get("comments_count", 0)}
                if data.get("posted_at"):
                    post["posted_at"] = data["posted_at"]
                if data.get("image_url") and not post.get("image_url"):
                    post["image_url"] = data["image_url"]
                if data.get("caption"):
                    post["caption"] = data["caption"][:2000]

        if platform in ("facebook", "instagram", "twitter", "youtube", "web") and url:
            if not post.get("posted_at") or post.get("likes", 0) == 0:
                data = fetch_page_meta(url)
                if data:
                    if data.get("posted_at") and not post.get("posted_at"):
                        post["posted_at"] = data["posted_at"]
                    if data.get("image_url") and not post.get("image_url"):
                        post["image_url"] = data["image_url"]

        return post
