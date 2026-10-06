"""Post thumbnails, kept on our own server.

A thumbnail URL read off Instagram or TikTok is signed and expires within
days, and the CDN refuses it from another site, so a report that links to it
shows grey tiles a week later. Each post's picture is therefore fetched once
and stored in admin/post_thumbs/ (client data: not in git), and the content
row points at it as "file:<name>". The report serves it through
/api/campaign-thumb, checked against the viewer's campaign.

Sources, no login needed:
  Instagram   https://www.instagram.com/p/<shortcode>/media/?size=l
  TikTok      oEmbed thumbnail_url
  YouTube     i.ytimg.com/vi/<id>/hqdefault.jpg
  anything    the page's og:image, then the thumb URL the capture sent
"""

import hashlib
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import db
import uploads

DIR = Path(__file__).resolve().parent / "post_thumbs"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
MAX = 4 * 1024 * 1024
_lock = threading.Lock()
_running = set()


def _get(url, timeout=15, ua=UA):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(MAX + 1)


def _image(url):
    try:
        data = _get(url)
    except Exception:
        return None
    kind = uploads.image_kind(data[:16])
    return (data, kind) if kind in ("jpg", "png", "webp") and len(data) <= MAX else None


def candidates(post_url, platform, hint=None):
    """Image URLs to try for one post, best first."""
    out = []
    u = (post_url or "").strip()
    p = (platform or "").lower()
    m = re.search(r"instagram\.com/(?:[^/]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)", u)
    if m:
        out.append("https://www.instagram.com/p/%s/media/?size=l" % m.group(1))
    if "tiktok.com" in u or p == "tiktok":
        try:
            j = json.loads(_get("https://www.tiktok.com/oembed?url=" + urllib.parse.quote(u, safe="")))
            if j.get("thumbnail_url"):
                out.append(j["thumbnail_url"])
        except Exception:
            pass
    m = re.search(r"(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([A-Za-z0-9_-]{6,})", u)
    if m:
        out.append("https://i.ytimg.com/vi/%s/hqdefault.jpg" % m.group(1))
    if not out and u.startswith("http"):
        try:
            html = _get(u, ua="facebookexternalhit/1.1").decode("utf-8", "replace")
            m = re.search(r'property="og:image"\s+content="([^"]+)"', html)
            if m:
                out.append(m.group(1).replace("&amp;", "&"))
        except Exception:
            pass
    if hint and str(hint).startswith("http"):
        out.append(hint)
    return out


def store(content_id, post_url, platform, hint=None):
    """Fetch and keep one post's picture. Returns the stored ref or None."""
    for url in candidates(post_url, platform, hint):
        got = _image(url)
        if not got:
            continue
        data, kind = got
        DIR.mkdir(exist_ok=True)
        name = "%d-%s.%s" % (content_id, hashlib.sha1(data).hexdigest()[:10], kind)
        (DIR / name).write_bytes(data)
        ref = "file:" + name
        with db.connect() as conn:
            old = conn.execute("SELECT thumb FROM content WHERE id = ?", (content_id,)).fetchone()
            conn.execute("UPDATE content SET thumb = ? WHERE id = ?", (ref, content_id))
        if old and old["thumb"] and str(old["thumb"]).startswith("file:") and old["thumb"] != ref:
            (DIR / Path(old["thumb"][5:]).name).unlink(missing_ok=True)
        return ref
    return None


def missing(cid):
    """Posts in a campaign whose picture is not stored here yet."""
    with db.connect() as conn:
        return conn.execute(
            "SELECT id, url, platform, thumb FROM content WHERE campaign_id = ? "
            "AND (thumb IS NULL OR thumb NOT LIKE 'file:%')", (cid,)).fetchall()


def fill(cid, force=False):
    """Fetch every missing picture for a campaign, one a second. Returns
    (stored, failed)."""
    rows = missing(cid)
    if force:
        with db.connect() as conn:
            rows = conn.execute("SELECT id, url, platform, thumb FROM content WHERE campaign_id = ?",
                                (cid,)).fetchall()
    ok = bad = 0
    for r in rows:
        hint = r["thumb"] if r["thumb"] and str(r["thumb"]).startswith("http") else None
        if store(r["id"], r["url"], r["platform"], hint):
            ok += 1
        else:
            bad += 1
        time.sleep(1.0)
    return ok, bad


def fill_later(cid):
    """fill() on a background thread, once at a time per campaign."""
    with _lock:
        if cid in _running:
            return False
        _running.add(cid)

    def run():
        try:
            fill(cid)
        finally:
            with _lock:
                _running.discard(cid)
    threading.Thread(target=run, daemon=True).start()
    return True


def path_of(ref):
    if not ref or not str(ref).startswith("file:"):
        return None
    f = DIR / Path(str(ref)[5:]).name
    return f if f.is_file() else None


if __name__ == "__main__":
    import sys
    cid = int(sys.argv[1])
    print(fill(cid, force="--force" in sys.argv))
