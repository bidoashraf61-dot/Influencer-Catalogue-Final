"""Profiles learnt from campaign posts (item 216, owner 2026-10-21).

A creator booked for Instagram often pushes the same video to TikTok, YouTube or Facebook, and the team adds
those posts to the campaign. When the roster has no profile for the creator on that platform, the campaign
cannot show their followers there, grade them or capture them on their own. The post itself names its author:
the capture keeps each actor's raw result (profile_raw, code "post:<content id>"), and a TikTok link carries the
handle. This module reads that, and adds the missing profile (platform, link, followers) to the creator, with a
History record so it can be undone, plus a dated follower snapshot.

    gaps()           what is missing, and what the stored results already say (no network, no spend)
    fill(rows)       add the profiles found; returns what was added
    learn(...)       the capture's hook: one post just read, add its author's profile when the creator lacks it
"""
import json
import re

import db

# The demo campaign holds dummy posts (owner, 2026-10-20): never learnt from.
DEMO_MARK = "(demo)"

_TT_LINK = re.compile(r"tiktok\.com/@([A-Za-z0-9._]{2,40})", re.I)
_SC_LINK = re.compile(r"snapchat\.com/(?:add/|@)([A-Za-z0-9._\-]{2,40})", re.I)
_YT_HANDLE = re.compile(r"youtube\.com/(@[A-Za-z0-9._\-]{2,60}|channel/UC[A-Za-z0-9_\-]{20,})", re.I)


def _n(v):
    try:
        n = int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _s(v):
    v = "" if v is None else str(v).strip()
    return "" if v.lower() in ("none", "null") else v


def author(platform, item, post_url=""):
    """{handle, url, followers, photo, id} for the account that published one post, from the actor's result
    and the post link. Missing parts are None; None when nothing usable is there."""
    item = item if isinstance(item, dict) else {}
    out = {"handle": None, "url": None, "followers": None, "photo": None, "id": None}
    if platform == "TikTok":
        cr = item.get("creator") if isinstance(item.get("creator"), dict) else {}
        am = item.get("authorMeta") if isinstance(item.get("authorMeta"), dict) else {}
        h = _s(cr.get("username") or cr.get("uniqueId") or am.get("name") or am.get("uniqueId"))
        if not h:
            m = _TT_LINK.search(post_url or "")
            h = m.group(1) if m else ""
        if h:
            out.update(handle=h.lstrip("@"), url="https://www.tiktok.com/@%s" % h.lstrip("@"))
        out["followers"] = _n(cr.get("followerCount") or cr.get("followers") or am.get("fans"))
        out["photo"] = _s(cr.get("avatarUrl") or am.get("avatar")) or None
        out["id"] = _s(cr.get("id") or am.get("id")) or None
    elif platform == "YouTube":
        u = _s(item.get("channel_url") or item.get("channelUrl") or item.get("uploader_url"))
        m = _YT_HANDLE.search(u)
        if m:
            out.update(handle=m.group(1), url="https://www.youtube.com/%s" % m.group(1))
        out["followers"] = _n(item.get("channel_follower_count") or item.get("subscriberCount") or item.get("numberOfSubscribers"))
        out["id"] = _s(item.get("channel_id") or item.get("channelId")) or None
        out["photo"] = _s(item.get("channel_avatar") or item.get("channelAvatar")) or None
    elif platform == "Instagram":
        ow = item.get("owner") if isinstance(item.get("owner"), dict) else {}
        h = _s(item.get("ownerUsername") or ow.get("username"))
        if h:
            out.update(handle=h, url="https://www.instagram.com/%s/" % h)
        out["followers"] = _n(ow.get("followersCount") or ow.get("followers") or item.get("ownerFollowers"))
        out["photo"] = _s(ow.get("profilePicUrl") or ow.get("profile_pic_url")) or None
        out["id"] = _s(item.get("ownerId") or ow.get("id")) or None
    elif platform == "Facebook":
        u = _s(item.get("authorUrl") or item.get("pageUrl") or item.get("ownerUrl"))
        slug = _s(item.get("pageName"))
        if u.lower().startswith("http") and "facebook.com" in u.lower() and "/share/" not in u.lower():
            out.update(handle=_s(item.get("authorName") or slug) or None, url=u)
        elif re.fullmatch(r"[A-Za-z0-9.]{5,60}", slug):
            # apify/facebook-posts-scraper on a share link: no author, but pageName is the page's own address
            out.update(handle=slug, url="https://www.facebook.com/%s" % slug)
        out["followers"] = _n(item.get("authorFollowers") or item.get("pageFollowers") or item.get("followers"))
        out["id"] = _s(item.get("authorId") or item.get("pageId")) or None
    elif platform == "Snapchat":
        h = _s(item.get("username") or item.get("creatorUsername"))
        if not h:
            m = _SC_LINK.search(post_url or "")
            h = m.group(1) if m else ""
        if h:
            out.update(handle=h, url="https://www.snapchat.com/add/%s" % h)
        out["followers"] = _n(item.get("subscriberCount") or item.get("followers"))
    if not out["url"]:
        return None
    return out


def _has(creator, platform):
    if (creator["platform"] or "").strip().lower() == platform.lower():
        return True
    return any(p["platform"].lower() == platform.lower() for p in db.split_profiles(creator["profiles"]))


def _owner_of(conn, url):
    """The other creator whose profile already carries this link, if one does."""
    key = url.rstrip("/").lower()
    for r in conn.execute("SELECT code, profiles FROM creators WHERE profiles LIKE ?", ("%" + key.split("//")[-1] + "%",)):
        if any((p["url"] or "").rstrip("/").lower() == key for p in db.split_profiles(r["profiles"])):
            return r["code"]
    return None


def gaps(conn=None):
    """Every (creator, platform) where a campaign post sits on a platform the creator has no profile for.
    [{code, platform, posts, campaigns, found, source}]; found = author() from the newest stored capture or the
    link, source = "capture" | "link" | None (needs a fetch). Dummy posts of the demo campaign are left out."""
    if conn is None:
        with db.connect() as own:
            return gaps(own)
    creators = {r["code"]: r for r in conn.execute("SELECT code, platform, profiles FROM creators")}
    rows = conn.execute("SELECT c.id, c.code, c.platform, c.url, c.campaign_id FROM content c JOIN campaigns k ON k.id = c.campaign_id "
                        "WHERE c.hidden = 0 AND COALESCE(k.client, '') NOT LIKE ? ORDER BY c.id DESC", ("%" + DEMO_MARK + "%",)).fetchall()
    by = {}
    for r in rows:
        cr = creators.get(r["code"])
        if cr is None or _has(cr, r["platform"]):
            continue
        g = by.setdefault((r["code"], r["platform"]), {"code": r["code"], "platform": r["platform"], "posts": [],
                                                        "campaigns": set(), "found": None, "source": None})
        g["posts"].append(r["id"])
        g["campaigns"].add(r["campaign_id"])
        if g["found"] and g["source"] == "capture":
            continue
        raw = conn.execute("SELECT data FROM profile_raw WHERE code = ? ORDER BY at DESC LIMIT 1", ("post:%d" % r["id"],)).fetchone()
        item = {}
        if raw is not None:
            try:
                item = json.loads(raw["data"])
            except ValueError:
                item = {}
        a = author(r["platform"], item, r["url"])
        if a and (g["found"] is None or (raw is not None and a.get("followers"))):
            g["found"], g["source"] = a, ("capture" if raw is not None and (a.get("followers") or a.get("id")) else "link")
    out = []
    for g in by.values():
        g["campaigns"] = sorted(g["campaigns"])
        out.append(g)
    return sorted(out, key=lambda g: (g["code"], g["platform"]))


def add(conn, code, platform, a, why="campaign posts"):
    """Add one profile to a creator, recorded in History. False when the creator already has the platform,
    the link is another creator's, or there is nothing to add."""
    import history
    if not a or not a.get("url"):
        return False
    cr = conn.execute("SELECT * FROM creators WHERE code = ?", (code,)).fetchone()
    if cr is None or _has(cr, platform):
        return False
    other = _owner_of(conn, a["url"])
    if other and other != code:
        return False
    before = history.snapshot("creator", code, conn)
    items = db.split_profiles(cr["profiles"]) + [{"platform": platform, "url": a["url"], "followers": a.get("followers")}]
    conn.execute("UPDATE creators SET profiles = ? WHERE code = ?", (db.join_profiles(items), code))
    if a.get("followers") and conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'profile_snapshots'").fetchone():
        conn.execute("INSERT INTO profile_snapshots (code,platform,handle,at,followers,following,posts,verified,run_id) "
                     "VALUES (?,?,?,?,?,?,?,?,?)", (code, platform, a.get("handle") or a["url"], db.now(), a["followers"],
                                                    None, None, None, None))
    history.record("edited", "creator", code, "Added %s profile to %s from %s" % (platform, code, why),
                   before, history.snapshot("creator", code, conn), conn)
    return True


def fill(rows, conn=None):
    """Add the profiles gaps() found. Returns [(code, platform)] added."""
    if conn is None:
        with db.connect() as own:
            return fill(rows, own)
    done = []
    for g in rows:
        if g.get("found") and add(conn, g["code"], g["platform"], g["found"]):
            done.append((g["code"], g["platform"]))
    return done


def auto_on():
    """The capture adds a missing profile on its own unless the owner turned it off."""
    return db.setting("post_profiles_auto", True) is not False


def learn(conn, content_id, platform, item):
    """Capture hook: one post's result just came in. Adds its author's profile when the creator has none on
    that platform. Never raises; the capture must not fail on this."""
    try:
        if not auto_on():
            return False
        row = conn.execute("SELECT c.code, c.url, k.client FROM content c JOIN campaigns k ON k.id = c.campaign_id WHERE c.id = ?",
                           (int(content_id),)).fetchone()
        if row is None or DEMO_MARK in (row["client"] or ""):
            return False
        return add(conn, row["code"], platform, author(platform, item, row["url"]), "a captured campaign post")
    except Exception:
        return False
