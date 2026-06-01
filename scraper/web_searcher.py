import time
import re
import random
from datetime import datetime
from urllib.parse import urlparse, quote_plus
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from config import USER_AGENT, SCRAPER_TIMEOUT, MAX_RETRIES

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
    "whatsapp.com": "whatsapp",
}

PLATFORM_SEARCH_MODIFIERS = {
    "instagram": "site:instagram.com",
    "facebook": "site:facebook.com",
    "twitter": "site:x.com OR site:twitter.com",
    "tiktok": "site:tiktok.com",
    "reddit": "site:reddit.com",
    "youtube": "site:youtube.com",
    "threads": "site:threads.net",
}


def detect_platform(url):
    if not url:
        return "unknown"
    try:
        domain = urlparse(url).netloc.lower()
        domain = domain.removeprefix("www.")
        for key, platform in SOCIAL_PLATFORMS.items():
            if key in domain:
                return platform
    except Exception:
        pass
    return "web"


def extract_post_id(url, platform):
    if not url:
        return None
    patterns = {
        "instagram": r"instagram\.com/(?:p|reel)/([^/?]+)",
        "facebook": r"facebook\.com/[^/]+/(?:posts|videos|photos)/([^/?]+)",
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
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        })
        self._last_request = 0

    def _rate_limit(self, min_seconds=2):
        elapsed = time.time() - self._last_request
        if elapsed < min_seconds:
            time.sleep(min_seconds - elapsed + random.uniform(0.3, 1.5))
        self._last_request = time.time()

    def search_all_platforms(self, keyword, max_per_platform=25):
        all_results = []
        platforms_to_search = ["instagram", "facebook", "twitter", "tiktok", "reddit", "youtube"]

        for platform in platforms_to_search:
            self._rate_limit()
            results = self._search_ddg(keyword, platform, max_per_platform)
            all_results.extend(results)

        self._rate_limit()
        general_results = self._search_ddg_general(keyword, max_results=15)
        all_results.extend(general_results)

        return all_results

    def _search_ddg(self, keyword, platform, max_results=25):
        results = []
        site_filter = PLATFORM_SEARCH_MODIFIERS.get(platform, "")
        query = f"{keyword} {site_filter} encuesta votacion elecciones 2027"
        query = query.strip()[:300]

        try:
            with DDGS() as ddgs:
                search_results = list(ddgs.text(query, max_results=max_results))
        except Exception:
            return results

        for r in search_results:
            url = r.get("href", "")
            if not url:
                continue
            detected_platform = detect_platform(url)
            if detected_platform == "unknown":
                detected_platform = "web"

            post_id = extract_post_id(url, detected_platform)
            date_str = r.get("date") or r.get("published")
            posted_at = None
            if date_str:
                try:
                    posted_at = datetime.fromisoformat(date_str.replace("Z", "+00:00")).isoformat()
                except Exception:
                    posted_at = date_str

            results.append({
                "post_id": post_id or url[:200],
                "platform": detected_platform,
                "url": url,
                "caption": (r.get("title", "") or "")[:1500] + "\n" + (r.get("body", "") or "")[:1500],
                "image_url": None,
                "posted_at": posted_at,
                "is_poll": False,
                "likes": 0,
                "comments_count": 0,
                "shares": 0,
                "reactions": {},
                "source": "web_search",
                "keyword": keyword,
            })

        return results

    def _search_ddg_general(self, keyword, max_results=15):
        results = []
        query = f"{keyword} encuesta votacion preferencia presidencial 2027 argentina redes sociales"
        query = query.strip()[:300]

        try:
            with DDGS() as ddgs:
                search_results = list(ddgs.text(query, max_results=max_results))
        except Exception:
            return results

        for r in search_results:
            url = r.get("href", "")
            if not url:
                continue
            detected_platform = detect_platform(url)
            if detected_platform == "unknown":
                detected_platform = "web"

            results.append({
                "post_id": extract_post_id(url, detected_platform) or url[:200],
                "platform": detected_platform,
                "url": url,
                "caption": (r.get("title", "") or "")[:1500] + "\n" + (r.get("body", "") or "")[:1500],
                "image_url": None,
                "posted_at": None,
                "is_poll": False,
                "likes": 0,
                "comments_count": 0,
                "shares": 0,
                "reactions": {},
                "source": "web_search",
                "keyword": keyword,
            })

        return results

    def fetch_page_social_data(self, url):
        self._rate_limit(4)
        try:
            resp = self.session.get(url, timeout=SCRAPER_TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            meta_tags = {}
            for meta in soup.find_all("meta"):
                prop = meta.get("property") or meta.get("name")
                content = meta.get("content", "")
                if prop:
                    meta_tags[prop.lower()] = content

            likes = 0
            comments = 0
            shares = 0
            for tag_text in [str(t) for t in soup.find_all(["span", "div", "meta", "a"])]:
                if not tag_text:
                    continue
                if "like" in tag_text.lower() or "me gusta" in tag_text.lower():
                    nums = re.findall(r'[\d,.]+[KMB]?', tag_text)
                    for n in nums:
                        likes = _parse_social_number(n) or likes

            image_url = meta_tags.get("og:image") or meta_tags.get("twitter:image")
            description = meta_tags.get("og:description") or meta_tags.get("description", "")
            title = meta_tags.get("og:title") or ""

            return {
                "likes": likes,
                "comments_count": comments,
                "shares": shares,
                "image_url": image_url,
                "caption": f"{title}\n{description}"[:2000],
                "meta_tags": meta_tags,
            }
        except Exception:
            return None


def _parse_social_number(text):
    if not text:
        return 0
    text = text.strip().replace(",", "").replace(".", "").upper()
    try:
        if text.endswith("K"):
            return int(float(text[:-1]) * 1_000)
        elif text.endswith("M"):
            return int(float(text[:-1]) * 1_000_000)
        elif text.endswith("B"):
            return int(float(text[:-1]) * 1_000_000_000)
        else:
            return int(text)
    except (ValueError, IndexError):
        return 0
