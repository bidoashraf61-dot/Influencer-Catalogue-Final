"""Followers, name and photo for a private creator (docs/SAAS-MODEL.md, owner 2026-10-28).

A company that owns Helvi Track adds a creator by profile link (creators_private.add_by_handle). One Apify profile
read per new private creator fills in the follower count (so engagement rates mean something), the creator's name
and the profile picture. It is an ordinary Apify job, source "private:<company>", so the same brakes apply: the
global monthly budget, and the company's own monthly collection spend cap (competitors.spend_month counts these
runs). Switched on by the setting private_profile_read = "on"; off by default, so adding a creator spends nothing
until the owner turns it on.

Reading: Instagram uses the ig_profiles preset (about $0.003 a creator), TikTok tt_profiles. Other platforms have no
reader yet, so those creators keep their name and handle only.
"""
import json
import urllib.request

PRESETS = {"Instagram": "ig_profiles", "TikTok": "tt_profiles"}
_FOLLOWER_KEYS = ("followersCount", "followers", "followerCount", "follower_count", "subscriberCount", "subscribersCount")


def source(company):
    return "private:%d" % int(company)


def _num(v):
    try:
        return int(v) if v is not None and not isinstance(v, bool) and int(v) >= 0 else None
    except (TypeError, ValueError):
        return None


def extract(item):
    """{handle, followers, name, pic} from one profile result of either reader (any may be None)."""
    if not isinstance(item, dict):
        return {}
    meta = item.get("authorMeta") if isinstance(item.get("authorMeta"), dict) else {}
    handle = item.get("username") or item.get("uniqueId") or meta.get("name") or item.get("userName")
    followers = next((x for x in (_num(item.get(k)) for k in _FOLLOWER_KEYS) if x is not None), None)
    if followers is None:
        followers = _num(meta.get("fans"))
    name = item.get("fullName") or item.get("nickname") or meta.get("nickName") or item.get("name")
    pic = item.get("profilePicUrlHD") or item.get("profilePicUrl") or item.get("avatarLarger") or item.get("avatar") or meta.get("avatar")
    return {"handle": (str(handle).lower().lstrip("@") if handle else None), "followers": followers,
            "name": (str(name).strip()[:80] if name else None), "pic": pic if isinstance(pic, str) and pic.startswith("http") else None}


def enabled():
    import db
    return str(db.setting("private_profile_read", "off")).lower() == "on"


def unread_codes(company, platform):
    """Private creators of this company, on this platform, whose follower count has not been read."""
    import db
    with db.connect() as conn:
        return [r["code"] for r in conn.execute(
            "SELECT code FROM creators WHERE owner_code_id = ? AND platform = ? AND followers IS NULL ORDER BY code",
            (int(company), platform))]


def ensure_job(company, platform):
    """The company's profile-read job for this platform: made once, run on demand."""
    import apify
    key = PRESETS.get(platform)
    if key is None:
        return None
    src = source(company)
    for j in apify.list_jobs():
        if j["source"] == src and j["platform"] == platform and j["kind"] == "profiles":
            return j["id"]
    p = apify.PRESETS[key]
    return apify.save_job({"name": "Private creators · %s · company %d" % (platform, int(company)), "actor": p["actor"], "kind": "profiles",
                           "platform": platform, "source": src, "input": p["input"], "max_handles": "5",
                           "est_each": str(p["est"]), "schedule": "manual", "at_time": "", "weekday": "0"})


def request_read(code, force=False):
    """Start the profile read for one private creator. Returns (ok, message). Refuses, with the reason, when it is
    switched off, nothing is unread, the platform has no reader, or a spend limit would be passed."""
    import apify
    import competitors
    import db
    import modules
    if not force and not enabled():
        return False, "Reading private creators is switched off."
    with db.connect() as conn:
        c = conn.execute("SELECT code, platform, followers, owner_code_id FROM creators WHERE code = ? "
                         "AND owner_code_id IS NOT NULL", (code,)).fetchone()
    if c is None:
        return False, "Not a private creator."
    if c["followers"] is not None:
        return False, "Already read."
    company, platform = int(c["owner_code_id"]), c["platform"]
    if platform not in PRESETS:
        return False, "%s profiles are not read yet." % platform
    cap, used = modules.number(company, "spend_month"), competitors.spend_month(company)
    if cap is not None and used >= cap:
        return False, "This month's collection spend limit is reached."
    jid = ensure_job(company, platform)
    ok, msg = apify.start_job(jid, trigger="private")
    return ok, msg


def apply_item(company, item):
    """Write what one profile result says onto the company's matching private creator. Returns the code or None."""
    import db
    got = extract(item)
    if not got.get("handle"):
        return None
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM creators WHERE owner_code_id = ? AND lower(ltrim(handle, '@')) = ?",
                           (int(company), got["handle"])).fetchone()
        if row is None:
            return None
        f = got["followers"]
        profiles = row["profiles"]
        if f is not None:
            items = db.split_profiles(row["profiles"])
            if items:
                items[0]["followers"] = f
                profiles = db.join_profiles(items)
        conn.execute("UPDATE creators SET followers = COALESCE(?, followers), tier = COALESCE(?, tier), "
                     "name = CASE WHEN name = handle AND ? IS NOT NULL THEN ? ELSE name END, profiles = ?, updated_at = ? "
                     "WHERE code = ?", (f, db.tier_for_reach(f) if f else None, got["name"], got["name"], profiles, db.now(), row["code"]))
        code = row["code"]
    if got["pic"]:
        _photo(code, got["pic"])
    return code


def _photo(code, url):
    """Keep the profile picture on this server as <CODE>.jpg and point the creator at it. Never raises."""
    try:
        import db
        import links
        import uploads
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read(6 * 1024 * 1024 + 1)
        ok, _why = uploads.photo_bytes(data)
        if not ok:
            return
        name = uploads.write_photo(data, code, links.PHOTO_DIR)
        with db.connect() as conn:
            conn.execute("UPDATE creators SET photo = ? WHERE code = ?", (name, code))
    except Exception as exc:
        print("private profile photo failed:", repr(exc)[:160], flush=True)


def apply_run(run, job):
    """After a private profile run finishes: read its result and fill the creators in. Returns how many."""
    import apify
    src = (job["source"] or "")
    if not src.startswith("private:") or not src[8:].isdigit() or not run["dataset"]:
        return 0
    company = int(src[8:])
    items = apify.call("GET", "/datasets/%s/items" % run["dataset"], params={"format": "json", "clean": "1", "limit": "10"}, timeout=60)
    items = items if isinstance(items, list) else []
    return sum(1 for it in items if apply_item(company, it))
