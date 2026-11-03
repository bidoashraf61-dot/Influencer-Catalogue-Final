"""A Snapchat Spotlight's public numbers, read straight from its page.

On 2026-11-03 Snapchat moved its pages to a new format and every Snapchat actor on Apify started answering
"could not be read" (chronometrica, tri_angle, parseforge, alpha-scraper, omkar-cloud, codenest). The numbers are
still on the public page, inside the page's own data. A Snapchat capture run reads here for any post its actor left
without numbers, so the campaign keeps its Snapchat history while the actors catch up.
"""
import json
import re
import urllib.request

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', re.S)


def snap_id(url):
    m = re.search(r"/spotlight/([A-Za-z0-9_\-]{16,})", url or "")
    return m.group(1) if m else None


def read(url, timeout=20):
    """{url, views, likes, comments, shares, publishedAt, caption, thumbnailUrl} for one Spotlight link, shaped like an
    actor result so the capture reads it the same way; None when the page does not show that post."""
    sid = snap_id(url)
    if not sid:
        return None
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            page = r.read(3_000_000).decode("utf-8", "replace")
    except Exception:
        return None
    data = "".join(_decode(c) for c in _CHUNK.findall(page))
    at = data.find('"video":{"id":"%s"' % sid)
    if at < 0:
        return None
    try:
        v, _end = json.JSONDecoder().raw_decode(data, at + len('"video":'))
    except ValueError:
        return None
    nums = {k: v.get(src) for k, src in (("views", "viewCount"), ("likes", "likeCount"),
                                         ("comments", "commentCount"), ("shares", "shareCount"))}
    if all(n is None for n in nums.values()):
        return None
    caption = v.get("caption")
    return {"inputUrl": url, "url": url, "snapId": sid, "status": "ok", "source": "snapchat page",
            "publishedAt": v.get("uploadTimestampMs"), "caption": None if caption == "$undefined" else caption,
            "thumbnailUrl": v.get("posterUrl"), **nums}


def _decode(chunk):
    try:
        return json.loads('"%s"' % chunk)
    except ValueError:
        return ""
