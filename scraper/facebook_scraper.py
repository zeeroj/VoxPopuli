import os
import tempfile
import time
import random
from datetime import datetime
from .base import BaseScraper
from utils.helpers import parse_date, is_poll_post, safe_get
from ddgs import DDGS
import requests

try:
    import facebook_scraper as fb
    FB_SCRAPER_AVAILABLE = True
except ImportError:
    FB_SCRAPER_AVAILABLE = False


class FacebookScraper(BaseScraper):
    def __init__(self):
        super().__init__("facebook", rate_limit=5)
        self._fb_available = FB_SCRAPER_AVAILABLE

    def search(self, keyword, date_from=None, date_to=None, max_posts=30):
        results = []
        date_from_dt = parse_date(date_from)
        date_to_dt = parse_date(date_to)

        if self._fb_available:
            try:
                posts = fb.search_posts(
                    keyword,
                    options={"allow_extra_requests": False, "posts_per_page": 10},
                    timeout=30,
                )
                count = 0
                for post in posts:
                    if count >= max_posts:
                        break
                    try:
                        post_text = post.get("text", "") or ""
                        post_time = post.get("time")
                        post_date = None
                        if post_time:
                            try:
                                post_date = datetime.fromtimestamp(post_time)
                            except Exception:
                                pass

                        if date_from_dt and post_date and post_date < date_from_dt:
                            continue
                        if date_to_dt and post_date and post_date > date_to_dt:
                            continue

                        post_data = {
                            "post_id": str(post.get("post_id", "")),
                            "url": post.get("post_url", ""),
                            "caption": post_text[:2000],
                            "image_url": post.get("image", None),
                            "posted_at": post_date.isoformat() if post_date else None,
                            "is_poll": is_poll_post(post_text),
                            "likes": safe_get(post, "likes", 0),
                            "comments_count": safe_get(post, "comments", 0),
                            "shares": safe_get(post, "shares", 0),
                            "reactions": post.get("reactions", {}),
                        }
                        results.append(post_data)
                        count += 1
                    except Exception:
                        continue
            except Exception:
                pass

        if not results:
            results = self._search_via_ddg(keyword, date_from_dt, date_to_dt, max_posts)

        return results

    def _search_via_ddg(self, keyword, date_from_dt, date_to_dt, max_posts):
        results = []
        query = f"{keyword} site:facebook.com encuesta votacion"
        try:
            with DDGS() as ddgs:
                search_results = list(ddgs.text(query, max_results=max_posts))
        except Exception:
            return results

        for r in search_results:
            url = r.get("href", "")
            if not url or "facebook.com" not in url:
                continue

            title = r.get("title", "") or ""
            body = r.get("body", "") or ""

            results.append({
                "post_id": url[:200],
                "url": url,
                "caption": f"{title}\n{body}"[:2000],
                "image_url": None,
                "posted_at": None,
                "is_poll": is_poll_post(title + " " + body),
                "likes": 0,
                "comments_count": 0,
                "shares": 0,
                "reactions": {},
            })

        return results

    def download_post_image(self, url):
        if not url:
            return None
        self._rate_limit_wait()
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        try:
            self._download_image(url, tmp.name)
            return tmp.name
        except Exception:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)
            return None
