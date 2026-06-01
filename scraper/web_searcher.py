import time
import re
import random
from datetime import datetime
from urllib.parse import urlparse
from ddgs import DDGS
from config import USER_AGENT, SCRAPER_TIMEOUT

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


class WebSearcher:
    def __init__(self):
        self._last_request = 0
        self._ddgs = DDGS()

    def _rate_limit(self, min_seconds=1.5):
        elapsed = time.time() - self._last_request
        if elapsed < min_seconds:
            time.sleep(min_seconds - elapsed + random.uniform(0.2, 1.0))
        self._last_request = time.time()

    def search_all_platforms(self, keyword, max_per_platform=30):
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
                post_id = extract_post_id(url, platform) if platform else url[:200]

                title = r.get("title", "") or ""
                body = r.get("body", "") or ""
                caption = f"{title}\n{body}"[:2000]

                results_entry = {
                    "post_id": str(post_id),
                    "platform": platform or "web",
                    "url": url,
                    "caption": caption,
                    "image_url": None,
                    "posted_at": None,
                    "is_poll": False,
                    "likes": 0,
                    "comments_count": 0,
                    "shares": 0,
                    "reactions": {},
                    "source": "web_search",
                    "keyword": keyword,
                }

                all_results.append(results_entry)

        return all_results
