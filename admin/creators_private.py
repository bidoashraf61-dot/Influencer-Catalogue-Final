"""Private creators: a company's own creators, for a company that owns Helvi Track or Helvi Intelligence without
Helvi Selection (docs/SAAS-MODEL.md, owner 2026-10-28).

A private creator is a row in `creators` with `owner_code_id` set. Three things keep it private:

  1. It is stored with active = 0, and every roster list, count and search already reads active = 1 only, so it
     never reaches the roster, the roster counts, the AI shortlist or another company.
  2. A trigger makes that permanent whatever code path writes: a private creator cannot be made active, and its
     owner cannot be cleared, so it can never turn into a roster creator by accident.
  3. evidence.handle_index (the competitor study's "is this creator on our roster?") skips owned creators.

Track and the campaign reports reach a creator by its code (joins on code, no active filter), so they work on a
private creator exactly as on a roster one. The code is PV-<company>-<n>, which never collides with roster codes.
Imports of db are inside the functions so the parsing can be tested without a database.
"""
import json
import re

PLATFORMS = (("instagram.com", "Instagram"), ("tiktok.com", "TikTok"), ("snapchat.com", "Snapchat"),
             ("youtube.com", "YouTube"), ("youtu.be", "YouTube"), ("facebook.com", "Facebook"), ("fb.com", "Facebook"))
_NOT_HANDLES = {"p", "reel", "reels", "tv", "video", "watch", "channel", "c", "user", "explore", "stories", "share", "add",
                "spotlight", "profile.php", "pages", "people"}

SCHEMA_STEPS = (
    "CREATE INDEX IF NOT EXISTS creators_owner ON creators(owner_code_id)",
    """CREATE TRIGGER IF NOT EXISTS creators_private_insert BEFORE INSERT ON creators
       WHEN NEW.owner_code_id IS NOT NULL AND IFNULL(NEW.active, 0) != 0
       BEGIN SELECT RAISE(ABORT, 'a private creator stays off the roster'); END""",
    """CREATE TRIGGER IF NOT EXISTS creators_private_active BEFORE UPDATE ON creators
       WHEN NEW.owner_code_id IS NOT NULL AND IFNULL(NEW.active, 0) != 0
       BEGIN SELECT RAISE(ABORT, 'a private creator stays off the roster'); END""",
    """CREATE TRIGGER IF NOT EXISTS creators_private_owner BEFORE UPDATE OF owner_code_id ON creators
       WHEN OLD.owner_code_id IS NOT NULL AND NEW.owner_code_id IS NOT OLD.owner_code_id
       BEGIN SELECT RAISE(ABORT, 'a private creator cannot change owner or join the roster'); END""",
)
_ready = False


def parse_profile(url):
    """(platform, handle, clean_url) from a profile link, or None when it is not a profile of a known platform."""
    u = (url or "").strip()
    m = re.match(r"^https?://(?:www\.|m\.|web\.)?([^/?#]+)/?([^?#]*)", u, re.I)
    if not m:
        return None
    host, path = m.group(1).lower(), m.group(2)
    plat = next((p for d, p in PLATFORMS if host == d or host.endswith("." + d)), None)
    if plat is None:
        return None
    parts = [x for x in path.split("/") if x]
    handle = None
    if plat == "YouTube":
        for x in parts:
            if x.startswith("@"):
                handle = x[1:]
                break
        if handle is None and len(parts) >= 2 and parts[0] in ("c", "user", "channel"):
            handle = parts[1]
    elif plat == "Snapchat":
        if len(parts) >= 2 and parts[0] == "add":
            handle = parts[1]
        elif parts and parts[0].startswith("@"):
            handle = parts[0][1:]
    elif plat == "Facebook":
        if parts and parts[0].lower() not in _NOT_HANDLES:
            handle = parts[0]
    else:
        first = parts[0] if parts else ""
        if first and first.lower() not in _NOT_HANDLES:
            handle = first.lstrip("@")
    handle = (handle or "").strip().strip("/")
    if not re.match(r"^[A-Za-z0-9._\-]{2,60}$", handle):
        return None
    base = {"Instagram": "https://www.instagram.com/%s/", "TikTok": "https://www.tiktok.com/@%s",
            "Snapchat": "https://www.snapchat.com/add/%s", "YouTube": "https://www.youtube.com/@%s",
            "Facebook": "https://www.facebook.com/%s"}[plat]
    return plat, handle, base % handle


def ensure():
    """Add the owner column, its index and the three triggers. Safe to run on every start."""
    global _ready
    import db
    with db.connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(creators)")}
        if "owner_code_id" not in cols:
            conn.execute("ALTER TABLE creators ADD COLUMN owner_code_id INTEGER")
        for sql in SCHEMA_STEPS:
            conn.execute(sql)
    _ready = True


def _conn():
    import db
    if not _ready:
        ensure()
    return db.connect()


def add_by_handle(company_code_id, url, name=""):
    """Add a private creator from a profile link. Returns {ok, code, created, platform, handle} or {ok: False, message}.
    The same link added twice by one company returns the creator it already has."""
    import db
    parsed = parse_profile(url)
    if parsed is None:
        return {"ok": False, "message": "Paste the creator's profile link, for example https://www.instagram.com/name/"}
    plat, handle, clean = parsed
    company = int(company_code_id)
    with _conn() as conn:
        for r in conn.execute("SELECT code, platform, handle FROM creators WHERE owner_code_id = ?", (company,)):
            if (r["platform"] or "") == plat and (r["handle"] or "").lower().lstrip("@") == handle.lower():
                return {"ok": True, "code": r["code"], "created": False, "platform": plat, "handle": handle}
        n = conn.execute("SELECT COUNT(*) FROM creators WHERE owner_code_id = ?", (company,)).fetchone()[0] + 1
        code = "PV-%d-%d" % (company, n)
        while conn.execute("SELECT 1 FROM creators WHERE code = ?", (code,)).fetchone():
            n += 1
            code = "PV-%d-%d" % (company, n)
        t = db.now()
        # tier is required; the follower count is not known yet, so the smallest band until it is (db.tier_for_reach)
        conn.execute("INSERT INTO creators (code, name, handle, platform, followers, tier, active, note, sort, profiles, "
                     "updated_at, created_at, owner_code_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (code, (name or "").strip() or handle, handle, plat, None, "Nano", 0, "Private creator", 0,
                      json.dumps([{"platform": plat, "url": clean}]), t, t, company))
    _read_later(code)
    return {"ok": True, "code": code, "created": True, "platform": plat, "handle": handle}


def _read_later(code):
    """One profile read for the new creator (followers, name, picture), in the background, when the owner has turned
    it on (private_profile.py). Never lets a failed or refused read break adding the creator."""
    import threading

    def run():
        try:
            import private_profile
            ok, msg = private_profile.request_read(code)
            if not ok:
                print("private profile read not started for %s: %s" % (code, msg), flush=True)
        except Exception as exc:
            print("private profile read failed for %s: %r" % (code, exc), flush=True)
    threading.Thread(target=run, daemon=True).start()


def owner_of(code):
    """The company a creator belongs to, or None for a roster creator."""
    with _conn() as conn:
        r = conn.execute("SELECT owner_code_id FROM creators WHERE code = ?", (code,)).fetchone()
    return r["owner_code_id"] if r else None


def codes_of(company_code_id):
    with _conn() as conn:
        return [r["code"] for r in conn.execute("SELECT code FROM creators WHERE owner_code_id = ? ORDER BY code",
                                                (int(company_code_id),))]
