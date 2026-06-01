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


def generate_keyword_combinations():
    combos = set()
    poll_terms = [
        "encuesta presidencial 2027", "encuesta electoral argentina",
        "intencion voto 2027", "sondeo presidencial",
        "encuesta quien gana", "encuesta votacion",
        "preferencia electoral", "medicion presidencial",
        "encuesta reeleccion", "votacion 2027 presidente",
        "encuesta approval rating", "imagen positiva negativa",
        "balotaje encuesta", "encuesta vs",
        "presidential poll argentina 2027",
        "elecciones 2027 candidato",
        "scaneo electoral", "rechazo aprobacion",
    ]
    platform_terms = ["instagram", "facebook", "twitter", "reddit", "tiktok", "youtube"]

    for ck, info in CANDIDATES.items():
        name = info["name"]
        for pt in poll_terms:
            combos.add(f'"{name}" {pt}')
            combos.add(f'{name} {pt}')
        for ft in platform_terms:
            combos.add(f'{name} {ft}')
        for ck2, info2 in CANDIDATES.items():
            if ck >= ck2:
                continue
            combos.add(f'{info["name"]} vs {info2["name"]} encuesta')
            combos.add(f'"{info["name"]}" "{info2["name"]}" encuesta')

    combos.add("presidente argentino 2027 encuesta")
    combos.add("proximo presidente argentina 2027")
    combos.add("elecciones argentinas 2027 sondeo")
    return [c[:300] for c in combos]


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


def extract_reaction_poll_mapping(text):
    if not text:
        return None
    t = text.lower()
    reaction_kw = any(kw in t for kw in ["corazon", "corazón", "❤️", "love", "me encanta",
                                           "like", "me gusta", "👍", "reacciona", "reaccion"])
    poll_kw = any(kw in t for kw in ["si votas", "si apoyas", "para el que", "el que quiera",
                                      "vota con", "reacciona con", "poner like", "pone like",
                                      "poner corazon", "pone corazon", "quiere a", "elige con"])
    candidates_found = False
    for ck, info in CANDIDATES.items():
        for n in [info["name"].lower()] + [k.lower() for k in info.get("keywords", [])]:
            n = n.replace("#", "")
            if n and n in t:
                candidates_found = True
                break
        if candidates_found:
            break
    if reaction_kw and poll_kw and candidates_found:
        return {"detected": "reaction_poll", "candidates_found": True}
    return None


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
    t = text.lower()

    lp = [
        (r'(\d+[.,]?\d*)\s*[kKmM]?\s*(?:like|me\s*gusta|reacciones?|votos?)', 0),
        (r'(?:like|me\s*gusta|reacciones?|votos?)[:\s]*(\d+[.,]?\d*)\s*[kKmM]?', 0),
        (r'(\d{1,3}(?:[.,]\d{3})*\s*(?:like|me\s*gusta)s?)', 0),
    ]
    for pat, _ in lp:
        m = re.search(pat, t)
        if m:
            likes = _pc(m.group(1))
            break

    cp = [
        (r'(\d+[.,]?\d*)\s*[kKmM]?\s*(?:comentarios?|comments?|opiniones?)', 0),
        (r'(?:comentarios?|comments?)[:\s]*(\d+[.,]?\d*)\s*[kKmM]?', 0),
    ]
    for pat, _ in cp:
        m = re.search(pat, t)
        if m:
            comments = _pc(m.group(1))
            break

    sp = [
        (r'(\d+[.,]?\d*)\s*[kKmM]?\s*(?:compartidos?|shares?|retweets?)', 0),
        (r'(?:compartidos?|shares?)[:\s]*(\d+[.,]?\d*)\s*[kKmM]?', 0),
    ]
    for pat, _ in sp:
        m = re.search(pat, t)
        if m:
            shares = _pc(m.group(1))
            break

    return likes, comments, shares


def _pc(text):
    if not text:
        return 0
    s = str(text).replace(',', '').replace(' ', '').upper()
    try:
        if 'K' in s:
            return int(float(s.replace('K', '')) * 1000)
        if 'M' in s:
            return int(float(s.replace('M', '')) * 1_000_000)
        return int(float(s))
    except (ValueError, TypeError):
        return 0


class WebSearcher:
    def __init__(self):
        self._last_request = 0
        self._ddgs = DDGS()
        self._keyword_combos = list(generate_keyword_combinations())

    def _rl(self, ms=0.8):
        e = time.time() - self._last_request
        if e < ms:
            time.sleep(ms - e + random.uniform(0.05, 0.3))
        self._last_request = time.time()

    def search_all_platforms(self, max_per_query=6, max_total=2000):
        results = []
        seen = set()
        combos = list(self._keyword_combos)
        random.shuffle(combos)

        for q in combos:
            if len(results) >= max_total:
                break
            self._rl()
            try:
                sr = list(self._ddgs.text(q, max_results=max_per_query))
            except Exception:
                continue

            for r in sr:
                if len(results) >= max_total:
                    break
                url = r.get("href", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                plat = detect_platform(url)
                pid = extract_post_id(url, plat)
                title = r.get("title", "") or ""
                body = r.get("body", "") or ""
                caption = f"{title}\n{body}"[:2000]
                likes, comments, shares = extract_engagement_from_text(body)
                pp = extract_poll_percentages(title + " " + body)
                is_reaction_poll = bool(extract_reaction_poll_mapping(title + " " + body))

                results.append({
                    "post_id": str(pid),
                    "platform": plat or "web",
                    "url": url,
                    "caption": caption,
                    "image_url": None,
                    "posted_at": None,
                    "is_poll": bool(pp) or is_reaction_poll,
                    "likes": likes,
                    "comments_count": comments,
                    "shares": shares,
                    "reactions": {},
                    "poll_results": pp,
                    "poll_reactions": {"detected": True} if is_reaction_poll else None,
                    "source": "web_search",
                })
        return results

    def enrich_post(self, post):
        from scraper.post_fetcher import fetch_reddit_data, fetch_page_meta
        plat = post.get("platform")
        url = post.get("url")

        if plat == "reddit" and url:
            d = fetch_reddit_data(url)
            if d:
                post["likes"] = d.get("likes", 0)
                post["comments_count"] = d.get("comments_count", 0)
                if d.get("posted_at"):
                    post["posted_at"] = d["posted_at"]
                if d.get("image_url") and not post.get("image_url"):
                    post["image_url"] = d["image_url"]
                if d.get("caption"):
                    post["caption"] = d["caption"][:2000]

        if plat in ("facebook", "instagram", "twitter", "youtube", "web") and url:
            if not post.get("posted_at"):
                d = fetch_page_meta(url)
                if d:
                    if d.get("posted_at"):
                        post["posted_at"] = d["posted_at"]
                    if d.get("image_url") and not post.get("image_url"):
                        post["image_url"] = d["image_url"]
        return post
