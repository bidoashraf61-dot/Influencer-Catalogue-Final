"""What a pasted post link already says: the platform, the kind of post and, where the link names one, who posted it.

Adding a post by link used to need six answers. The link carries three of them, and the campaign's own creators
settle the fourth when the handle is in the link (TikTok, YouTube, X, Threads, Facebook, and Instagram links that
include the username). The numbers and the date come from the campaign's capture jobs, so nobody types them.
"""
import re
import urllib.parse
import urllib.request

_HOSTS = (("instagram.com", "Instagram"), ("tiktok.com", "TikTok"), ("snapchat.com", "Snapchat"),
          ("youtube.com", "YouTube"), ("youtu.be", "YouTube"), ("x.com", "X"), ("twitter.com", "X"),
          ("facebook.com", "Facebook"), ("fb.watch", "Facebook"), ("threads.net", "Threads"), ("threads.com", "Threads"))
_NOT_A_HANDLE = {"p", "reel", "reels", "tv", "stories", "explore", "share", "watch", "video", "videos", "shorts",
                 "spotlight", "add", "s", "i", "hashtag", "web", "t", "post", "posts", "story"}


def infer(url):
    """(platform, kind, handle) from a post link; each is None when the link does not say."""
    try:
        u = urllib.parse.urlparse((url or "").strip())
    except ValueError:
        return None, None, None
    host = (u.hostname or "").lower()
    plat = next((p for h, p in _HOSTS if host == h or host.endswith("." + h)), None)
    parts = [p for p in u.path.split("/") if p]
    low = [p.lower() for p in parts]
    kind = handle = None
    if plat == "Instagram":
        kind = "reel" if ("reel" in low or "reels" in low) else "story" if "stories" in low else "video" if "tv" in low else "post"
        if low[:1] == ["stories"] and len(parts) > 1:
            handle = parts[1]
        elif parts and low[0] not in _NOT_A_HANDLE:
            handle = parts[0]                                   # instagram.com/<user>/reel/<id>/
    elif plat == "TikTok":
        kind = "video"
        handle = next((p[1:] for p in parts if p.startswith("@")), None)
    elif plat == "YouTube":
        kind = "short" if "shorts" in low else "video"
        handle = next((p[1:] for p in parts if p.startswith("@")), None)
    elif plat == "Snapchat":
        kind = "story" if "story" in low or "stories" in low else "video"
        handle = next((p[1:] for p in parts if p.startswith("@")), None)
    elif plat == "X":
        kind = "post"
        handle = parts[0] if parts and low[0] not in _NOT_A_HANDLE else None
    elif plat == "Facebook":
        kind = "reel" if "reel" in low or "reels" in low else "video" if "videos" in low or "watch" in low else "post"
        handle = parts[0] if parts and low[0] not in _NOT_A_HANDLE and not parts[0].isdigit() else None
    elif plat == "Threads":
        kind = "post"
        handle = next((p[1:] for p in parts if p.startswith("@")), None)
    if handle and not re.fullmatch(r"[A-Za-z0-9._\-]{1,60}", handle):
        handle = None
    return plat, kind, (handle or "").lower() or None


def pick_creator(handle, members):
    """The campaign creator a link's handle belongs to. ``members`` is [(code, {platform: handle})]. One match, or None."""
    if not handle:
        return None
    hit = {code for code, hs in members if handle in {str(v).lower() for v in hs.values()}}
    return hit.pop() if len(hit) == 1 else None


_SHORT = ("vt.tiktok.com", "vm.tiktok.com", "www.tiktok.com/t/", "tiktok.com/t/", "instagram.com/share/", "www.instagram.com/share/",
          "fb.watch", "youtu.be", "snapchat.com/t/", "www.snapchat.com/t/")


def canonical(url):
    """The link the capture jobs can match: a share link followed to the post it points at (TikTok vt./vm. links, Instagram
    /share/ links), youtu.be/<id> written as a watch link, and tracking parameters dropped. Unchanged when it cannot be followed."""
    url = (url or "").strip()
    u = urllib.parse.urlparse(url)
    host = (u.hostname or "").lower()
    if host == "youtu.be" and u.path.strip("/"):
        return "https://www.youtube.com/watch?v=" + u.path.strip("/").split("/")[0]
    short = any((host + u.path).startswith(s) for s in _SHORT) or host in ("vt.tiktok.com", "vm.tiktok.com")
    if short:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/605 Safari/605"})
            with urllib.request.urlopen(req, timeout=8) as r:
                final = urllib.parse.urlparse(r.geturl())
            if (final.hostname or "") and final.path.strip("/") and "/t/" not in final.path:
                u = final
        except (OSError, ValueError):
            return url
    if any(h in (u.hostname or "") for h in ("instagram.com", "tiktok.com", "facebook.com", "x.com", "twitter.com", "threads")):
        return urllib.parse.urlunparse((u.scheme, u.netloc, u.path, "", "", ""))
    return urllib.parse.urlunparse(u)
