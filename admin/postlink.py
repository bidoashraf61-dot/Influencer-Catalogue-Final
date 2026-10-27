"""What a pasted post link already says: the platform, the kind of post and, where the link names one, who posted it.

Adding a post by link used to need six answers. The link carries three of them, and the campaign's own creators
settle the fourth when the handle is in the link (TikTok, YouTube, X, Threads, Facebook, and Instagram links that
include the username). The numbers and the date come from the campaign's capture jobs, so nobody types them.
"""
import re
import urllib.parse

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
