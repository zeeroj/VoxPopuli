import os
import tempfile
import json
import facebook_scraper as fb
from config import USER_AGENT
from utils.helpers import is_poll_post


FB_COOKIES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cookies.txt")


class FacebookScraper:
    def __init__(self):
        self._authenticated = False
        self._load_cookies()

    def _load_cookies(self):
        if os.path.exists(FB_COOKIES_PATH):
            try:
                jar = fb.parse_cookie_file(FB_COOKIES_PATH)
                fb.set_cookies(jar)
                fb.set_user_agent(USER_AGENT)
                self._authenticated = True
            except Exception as e:
                self._authenticated = False

    def is_authenticated(self):
        return self._authenticated

    def search_by_keyword(self, keyword, pages=5):
        if not self._authenticated:
            return []
        results = []
        try:
            posts = fb.get_posts_by_search(keyword, pages=pages)
            for post in posts:
                p = self._extract_post(post)
                if p:
                    p["keyword"] = keyword
                    results.append(p)
        except Exception:
            pass
        return results

    def get_page_posts(self, page_name, pages=3):
        if not self._authenticated:
            return []
        results = []
        try:
            posts = fb.get_posts(account=page_name, pages=pages)
            for post in posts:
                p = self._extract_post(post)
                if p:
                    results.append(p)
        except Exception:
            pass
        return results

    def get_post_data(self, url):
        if not self._authenticated:
            return None
        try:
            posts = list(fb.get_posts(post_urls=[url], pages=1))
            if posts:
                return self._extract_post(posts[0])
        except Exception:
            pass
        return None

    def _extract_post(self, post):
        if not post:
            return None
        text = post.get("text") or ""
        post_id = str(post.get("post_id", ""))
        url = post.get("post_url") or post.get("url", "")
        likes = int(post.get("likes", 0) or 0)
        comments = int(post.get("comments", 0) or 0)
        shares = int(post.get("shares", 0) or 0)
        reactions = post.get("reactions", {})
        time = post.get("time")
        posted_at = None
        if time:
            try:
                from datetime import datetime
                posted_at = datetime.fromtimestamp(time).isoformat()
            except Exception:
                pass

        return {
            "post_id": post_id,
            "platform": "facebook",
            "url": url,
            "caption": text[:2000],
            "image_url": post.get("image") or post.get("image_url"),
            "posted_at": posted_at,
            "is_poll": is_poll_post(text),
            "likes": likes,
            "comments_count": comments,
            "shares": shares,
            "reactions": reactions,
            "poll_results": {},
            "source": "facebook_scraper",
        }

    def get_known_political_pages(self):
        return [
            "A24com", "TNnoticias", "lanacion", "clarincom",
            "infobae", "pagina12", "cronica", "ambito",
            "perfil", "elcronistadiario",
        ]
