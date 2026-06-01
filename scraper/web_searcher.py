import time
import re
import random
import hashlib
from urllib.parse import urlparse
from ddgs import DDGS
from config import CANDIDATES
from scraper.post_fetcher import extract_date_from_text, fetch_post_engagement

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
    "{keyword} encuesta votacion preferencia 2027 argentina",
    "{keyword} redes sociales reacciones",
    "{keyword} instagram encuesta",
    "{keyword} facebook votacion",
    "{keyword} twitter debate",
    "{keyword} tiktok tendencia",
    "{keyword} reddit argentina",
    "{keyword} elecciones presidenciales 2027",
    '"{keyword}" encuesta presidencial',
    "{keyword} sondeo intencion voto",
    "{keyword} encuesta quien gana 2027",
    "{keyword} balotaje presidencial",
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
        return url[:200]
    match = re.search(pattern, url)
    return match.group(1) if match else url[:200]


def extract_poll_percentages(text):
    if not text:
        return {}
    from config import CANDIDATES

    candidate_names = {}
    for ck, info in CANDIDATES.items():
        name = info["name"]
        candidate_names[ck] = [name.lower()]
        candidate_names[ck].extend(k.lower() for k in info.get("keywords", []))
        candidate_names[ck].extend(t.lower().replace("#", "") for t in info.get("search_terms", []))

    text_lower = text.lower()
    pct_pattern = r'(\d{1,3})[.,](\d{1,2})?\s*%'
    pct_matches = list(re.finditer(pct_pattern, text_lower))

    results = {}
    for ck, names in candidate_names.items():
        best_pct = None
        best_dist = float('inf')
        for name in names:
            name_positions = [m.start() for m in re.finditer(re.escape(name), text_lower)]
            if not name_positions:
                continue
            closest_name_pos = name_positions[0]
            for pct_match in pct_matches:
                dist = abs(pct_match.start() - closest_name_pos)
                if dist < best_dist and dist < 300:
                    best_dist = dist
                    try:
                        whole = pct_match.group(1)
                        decimal = pct_match.group(2) or '0'
                        best_pct = float(f"{whole}.{decimal}")
                    except ValueError:
                        continue
        if best_pct is not None:
            results[ck] = best_pct

    return results


class WebSearcher:
    def __init__(self):
        self._last_request = 0
        self._ddgs = DDGS()

    def _rate_limit(self, min_seconds=1.2):
        elapsed = time.time() - self._last_request
        if elapsed < min_seconds:
            time.sleep(min_seconds - elapsed + random.uniform(0.2, 0.8))
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
                post_id = extract_post_id(url, platform) if platform else hashlib.md5(url.encode()).hexdigest()[:16]

                title = r.get("title", "") or ""
                body = r.get("body", "") or ""
                caption = f"{title}\n{body}"[:2000]

                extracted_date = extract_date_from_text(body) or extract_date_from_text(title)

                results_entry = {
                    "post_id": str(post_id),
                    "platform": platform or "web",
                    "url": url,
                    "caption": caption,
                    "image_url": None,
                    "posted_at": extracted_date,
                    "is_poll": False,
                    "likes": 0,
                    "comments_count": 0,
                    "shares": 0,
                    "reactions": {},
                    "poll_results": extract_poll_percentages(title + " " + body),
                    "source": "web_search",
                    "keyword": keyword,
                    "_fetched": False,
                }

                all_results.append(results_entry)

        return all_results

    def enrich_post(self, post):
        if post.get("_fetched"):
            return post

        engagement_data = fetch_post_engagement(post.get("url"), post.get("platform"))
        if engagement_data:
            for key in ['likes', 'comments_count', 'shares', 'image_url', 'caption', 'reactions']:
                val = engagement_data.get(key)
                if val:
                    post[key] = val
            real_date = engagement_data.get('posted_at')
            if real_date:
                post['posted_at'] = real_date

        post['_fetched'] = True
        return post
