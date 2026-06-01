import time
import random
import requests
from config import USER_AGENT, MAX_RETRIES, SCRAPER_TIMEOUT


class BaseScraper:
    def __init__(self, platform, rate_limit=3):
        self.platform = platform
        self.rate_limit = rate_limit
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._last_request = 0

    def _rate_limit_wait(self):
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            sleep_time = self.rate_limit - elapsed + random.uniform(0.5, 2)
            time.sleep(sleep_time)
        self._last_request = time.time()

    def _download_image(self, url, save_path):
        self._rate_limit_wait()
        resp = self.session.get(url, timeout=SCRAPER_TIMEOUT)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            f.write(resp.content)
        return save_path

    def search(self, keyword, date_from=None, date_to=None):
        raise NotImplementedError

    def get_post_reactions(self, post):
        raise NotImplementedError
