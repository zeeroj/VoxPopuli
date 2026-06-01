import os
import tempfile
import instaloader
from datetime import datetime
from .base import BaseScraper
from utils.helpers import safe_get, parse_date, is_poll_post, extract_hashtags


class InstagramScraper(BaseScraper):
    def __init__(self):
        super().__init__("instagram", rate_limit=3)
        self.loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            max_connection_attempts=1,
        )
        self.loader.context.timeout = 30
        try:
            self._try_login()
        except Exception:
            pass

    def _try_login(self):
        username = os.environ.get("INSTAGRAM_USERNAME")
        password = os.environ.get("INSTAGRAM_PASSWORD")
        if username and password:
            try:
                self.loader.login(username, password)
                self._logged_in = True
                return
            except Exception:
                pass
        self._logged_in = False

    def search(self, keyword, date_from=None, date_to=None, max_posts=50):
        results = []
        date_from_dt = parse_date(date_from)
        date_to_dt = parse_date(date_to)

        search_terms = [keyword]
        if keyword.startswith("#"):
            search_terms.append(keyword[1:])

        for term in search_terms:
            try:
                posts_found = 0
                if term.startswith("#"):
                    term = term[1:]
                search_results = self.loader.get_hashtag_posts(term)
                for post in search_results:
                    if posts_found >= max_posts:
                        break
                    try:
                        post_date = post.date_utc
                        if date_from_dt and post_date < date_from_dt:
                            continue
                        if date_to_dt and post_date > date_to_dt:
                            continue

                        caption = post.caption or ""
                        post_data = {
                            "post_id": str(post.shortcode),
                            "url": f"https://instagram.com/p/{post.shortcode}",
                            "caption": caption[:2000],
                            "image_url": str(post.url) if post.url else None,
                            "posted_at": post_date.isoformat(),
                            "is_poll": is_poll_post(caption),
                            "likes": post.likes if hasattr(post, 'likes') else 0,
                            "comments_count": post.comments if hasattr(post, 'comments') else 0,
                            "reactions": self._extract_reactions(post),
                        }
                        results.append(post_data)
                        posts_found += 1
                    except Exception:
                        continue
            except Exception:
                continue

        return results

    def _extract_reactions(self, post):
        reactions = {}
        try:
            if hasattr(post, 'likes') and post.likes:
                reactions['like'] = post.likes
        except Exception:
            pass
        try:
            if hasattr(post, 'comments') and post.comments:
                reactions['comments'] = post.comments
        except Exception:
            pass
        return reactions

    def download_post_image(self, url):
        self._rate_limit_wait()
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        try:
            self._download_image(url, tmp.name)
            return tmp.name
        except Exception:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)
            return None
