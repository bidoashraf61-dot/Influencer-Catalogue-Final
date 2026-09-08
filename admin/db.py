"""SQLite schema and queries for the catalogue admin.

One file, no ORM, no dependencies. The whole point of this service is that it
drops onto a server with nothing but Python 3 and starts working.

Every write goes through a function here rather than raw SQL at the call site,
so the shape of the data stays in one place.
"""

import calendar
import json
import secrets
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "catalogue.db"

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS admins (
  id            INTEGER PRIMARY KEY,
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at    INTEGER NOT NULL,
  last_login_at INTEGER
);

-- An access code is never stored in the clear: only its hash, the same way a
-- password is. A stolen database therefore does not hand over live codes.
CREATE TABLE IF NOT EXISTS codes (
  id          INTEGER PRIMARY KEY,
  code_hash   TEXT NOT NULL UNIQUE,
  hint        TEXT NOT NULL,            -- last 4 chars; all a pre-2026-09 row has
  code_plain  TEXT,                     -- the code itself, so it can be read back
  label       TEXT NOT NULL,            -- who it was issued to
  created_at  INTEGER NOT NULL,
  expires_at  INTEGER,                  -- NULL = no expiry
  revoked_at  INTEGER,
  max_uses    INTEGER,                  -- NULL = unlimited
  uses        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tiers (
  name        TEXT PRIMARY KEY,         -- "Micro". Also what creators.tier holds
  code        TEXT NOT NULL,            -- "MI", the middle of HV-MI-007
  price_from  INTEGER NOT NULL,
  price_to    INTEGER NOT NULL,
  reach       TEXT,                     -- "10K – 50K", shown on the ticker
  sort        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
  id         INTEGER PRIMARY KEY,
  code_id    INTEGER REFERENCES codes(id) ON DELETE SET NULL,
  kind       TEXT NOT NULL,             -- unlock_ok | unlock_fail | view | shortlist
  at         INTEGER NOT NULL,
  ip         TEXT,
  user_agent TEXT,
  detail     TEXT
);
CREATE INDEX IF NOT EXISTS events_at   ON events(at DESC);
CREATE INDEX IF NOT EXISTS events_code ON events(code_id);

CREATE TABLE IF NOT EXISTS creators (
  code      TEXT PRIMARY KEY,
  name      TEXT NOT NULL,
  handle    TEXT,
  platform  TEXT NOT NULL,
  followers INTEGER,
  city      TEXT,
  nationality TEXT,                     -- who the audience reads them as; not
                                        -- the same question as where they live
  tier      TEXT NOT NULL,
  interest  TEXT,
  photo     TEXT,
  profiles  TEXT,                       -- JSON [{platform, url}]: a creator is
                                        -- on several platforms, not one
  active    INTEGER NOT NULL DEFAULT 1,
  note      TEXT,
  sort      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS requests (
  id             INTEGER PRIMARY KEY,
  at             INTEGER NOT NULL,
  code_id        INTEGER REFERENCES codes(id) ON DELETE SET NULL,
  name           TEXT,
  company        TEXT,
  email          TEXT,
  phone          TEXT,
  selection_name TEXT,
  selection      TEXT NOT NULL,         -- JSON array of creator codes
  handled_at     INTEGER
);
CREATE INDEX IF NOT EXISTS requests_at ON requests(at DESC);

CREATE TABLE IF NOT EXISTS sessions (
  token      TEXT PRIMARY KEY,
  admin_id   INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init():
    with connect() as conn:
        conn.executescript(SCHEMA)
        migrate(conn)


def migrate(conn):
    """Columns added after a database was first created.

    executescript only creates tables that do not exist; an existing database
    keeps its original shape, so a new column has to be added explicitly. Each
    step is idempotent and checked against the live table rather than against a
    version number nobody remembers to bump.
    """
    have = {r["name"] for r in conn.execute("PRAGMA table_info(codes)")}
    if "code_plain" not in have:
        conn.execute("ALTER TABLE codes ADD COLUMN code_plain TEXT")

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(creators)")}
    if "nationality" not in cols:
        conn.execute("ALTER TABLE creators ADD COLUMN nationality TEXT")
    if "profiles" not in cols:
        conn.execute("ALTER TABLE creators ADD COLUMN profiles TEXT")
        # Backfill from the single platform+handle each creator had, so nobody
        # loses their link. It is the same URL the catalogue was already
        # guessing at render time; storing it is what makes it editable.
        for r in conn.execute("SELECT code, platform, handle FROM creators").fetchall():
            url = profile_url(r["platform"], r["handle"])
            if url:
                conn.execute("UPDATE creators SET profiles = ? WHERE code = ?",
                             (json.dumps([{"platform": r["platform"], "url": url}]),
                              r["code"]))
    seed_tiers(conn)


def now():
    return int(time.time())


# ------------------------------------------------------------------ admins --

def create_admin(email, password_hash):
    with connect() as conn:
        conn.execute(
            "INSERT INTO admins (email, password_hash, created_at) VALUES (?,?,?)",
            (email.strip().lower(), password_hash, now()),
        )


def admin_by_email(email):
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM admins WHERE email = ?", (email.strip().lower(),)
        ).fetchone()


def admin_count():
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) c FROM admins").fetchone()["c"]


def touch_admin_login(admin_id):
    with connect() as conn:
        conn.execute("UPDATE admins SET last_login_at = ? WHERE id = ?", (now(), admin_id))


def set_admin_password(admin_id, password_hash):
    with connect() as conn:
        conn.execute("UPDATE admins SET password_hash = ? WHERE id = ?", (password_hash, admin_id))


# ---------------------------------------------------------------- sessions --

def create_session(admin_id, ttl_seconds):
    token = secrets.token_urlsafe(32)
    with connect() as conn:
        conn.execute(
            "INSERT INTO sessions (token, admin_id, created_at, expires_at) VALUES (?,?,?,?)",
            (token, admin_id, now(), now() + ttl_seconds),
        )
    return token


def session(token):
    if not token:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT s.*, a.email FROM sessions s JOIN admins a ON a.id = s.admin_id "
            "WHERE s.token = ? AND s.expires_at > ?",
            (token, now()),
        ).fetchone()
    return row


def drop_session(token):
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def purge_expired_sessions():
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now(),))


# ------------------------------------------------------------------- codes --

def create_code(code_hash, hint, label, expires_at=None, max_uses=None, code_plain=None):
    """The code is stored as written as well as hashed.

    Hashing alone was the wrong call here, borrowed from passwords without the
    reason behind it. Passwords are hashed because people reuse them elsewhere,
    so a stolen database becomes a key to other services. Nobody reuses a
    catalogue share code, and anyone who can read this table can already read
    the creators table sitting beside it — the very thing the code unlocks. So
    the hash protected nothing, while "shown once, then gone forever" cost a
    real code every time someone closed the tab.

    The hash stays: it is what /api/unlock looks up, and it keeps working for
    every code issued before this column existed.
    """
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO codes (code_hash, hint, label, created_at, expires_at, max_uses, code_plain) "
            "VALUES (?,?,?,?,?,?,?)",
            (code_hash, hint, label, now(), expires_at, max_uses, code_plain),
        )
        return cur.lastrowid


def code_by_hash(code_hash):
    with connect() as conn:
        return conn.execute("SELECT * FROM codes WHERE code_hash = ?", (code_hash,)).fetchone()


def list_codes():
    with connect() as conn:
        return conn.execute(
            "SELECT c.*, "
            " (SELECT MAX(at) FROM events e WHERE e.code_id = c.id AND e.kind='unlock_ok') last_used "
            "FROM codes c ORDER BY c.created_at DESC"
        ).fetchall()


def revoke_code(code_id):
    with connect() as conn:
        conn.execute("UPDATE codes SET revoked_at = ? WHERE id = ?", (now(), code_id))


def bump_code_use(code_id):
    with connect() as conn:
        conn.execute("UPDATE codes SET uses = uses + 1 WHERE id = ?", (code_id,))


def code_state(row):
    """Why a code is or is not usable. Returns (ok, reason)."""
    if row is None:
        return False, "unknown"
    if row["revoked_at"]:
        return False, "revoked"
    if row["expires_at"] and row["expires_at"] < now():
        return False, "expired"
    if row["max_uses"] is not None and row["uses"] >= row["max_uses"]:
        return False, "exhausted"
    return True, "live"


# ------------------------------------------------------------------ events --

def log(kind, code_id=None, ip=None, user_agent=None, detail=None):
    with connect() as conn:
        conn.execute(
            "INSERT INTO events (code_id, kind, at, ip, user_agent, detail) VALUES (?,?,?,?,?,?)",
            (code_id, kind, now(), ip, (user_agent or "")[:300], detail),
        )


def recent_events(limit=200):
    with connect() as conn:
        return conn.execute(
            "SELECT e.*, c.label, c.hint FROM events e "
            "LEFT JOIN codes c ON c.id = e.code_id "
            "ORDER BY e.at DESC LIMIT ?",
            (limit,),
        ).fetchall()


def day_bounds(text, fallback):
    """A YYYY-MM-DD string as a UTC midnight timestamp, or the fallback.

    UTC because SQLite groups the daily chart with date(at,'unixepoch'), which
    is UTC — picking a local midnight here would put events in the wrong
    column at the edges of the range.
    """
    try:
        return int(calendar.timegm(time.strptime(text.strip(), "%Y-%m-%d")))
    except Exception:
        return fallback


def stats(days=30, start=None, end=None):
    """Everything the analytics page draws, in one pass.

    The window is an explicit [start, end) in seconds. `days` is kept for the
    dashboard, which only ever wants "recently"; the analytics page passes the
    two dates the user picked.

    Grouped so the page renders from data rather than computing anything: a
    view that does arithmetic is a view that quietly disagrees with the numbers
    beside it.
    """
    since = int(start) if start is not None else now() - days * 86400
    until = int(end) if end is not None else now() + 86400
    if until <= since:
        since, until = until - 86400, since + 86400
    with connect() as conn:
        def one(sql, args=()):
            return conn.execute(sql, args).fetchone()["c"]

        out = {"days": days}
        out["unlocks"] = one(
            "SELECT COUNT(*) c FROM events WHERE kind='unlock_ok' AND at >= ? AND at < ?", (since, until))
        out["failures"] = one(
            "SELECT COUNT(*) c FROM events WHERE kind='unlock_fail' AND at >= ? AND at < ?", (since, until))
        out["requests"] = one("SELECT COUNT(*) c FROM requests WHERE at >= ? AND at < ?", (since, until))
        out["shortlists"] = one(
            "SELECT COUNT(*) c FROM events WHERE kind='shortlist' AND at >= ? AND at < ?", (since, until))
        out["creators_touched"] = one(
            "SELECT COUNT(DISTINCT detail) c FROM events "
            "WHERE kind='shortlist' AND at >= ? AND at < ? AND detail IS NOT NULL", (since, until))
        out["live_codes"] = one(
            "SELECT COUNT(*) c FROM codes WHERE revoked_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > ?)", (now(),))

        # ---- funnel: how far each issued code actually got -----------------
        out["codes_total"] = one("SELECT COUNT(*) c FROM codes")
        out["codes_opened"] = one(
            "SELECT COUNT(DISTINCT code_id) c FROM events "
            "WHERE kind='unlock_ok' AND at >= ? AND at < ? AND code_id IS NOT NULL", (since, until))
        out["codes_shortlisted"] = one(
            "SELECT COUNT(DISTINCT code_id) c FROM events "
            "WHERE kind='shortlist' AND at >= ? AND at < ? AND code_id IS NOT NULL", (since, until))
        out["codes_requested"] = one(
            "SELECT COUNT(DISTINCT code_id) c FROM requests "
            "WHERE at >= ? AND at < ? AND code_id IS NOT NULL", (since, until))

        # ---- one row per client, so "did they engage" is one glance --------
        out["by_code"] = conn.execute(
            # max_uses and uses come along because code_state() reads them —
            # a partial SELECT here raised IndexError on the rendered page.
            "SELECT c.id, c.label, c.hint, c.revoked_at, c.expires_at,"
            " c.max_uses, c.uses,"
            " (SELECT COUNT(*) FROM events e WHERE e.code_id=c.id"
            "    AND e.kind='unlock_ok' AND e.at >= ? AND e.at < ?) opens,"
            " (SELECT COUNT(*) FROM events e WHERE e.code_id=c.id"
            "    AND e.kind='shortlist' AND e.at >= ? AND e.at < ?) shortlists,"
            " (SELECT COUNT(*) FROM requests r WHERE r.code_id=c.id AND r.at >= ? AND r.at < ?) requests,"
            " (SELECT MAX(e.at) FROM events e WHERE e.code_id=c.id"
            "    AND e.kind='unlock_ok' AND e.at >= ? AND e.at < ?) last "
            "FROM codes c ORDER BY opens DESC, c.created_at DESC",
            (since, until, since, until, since, until, since, until)).fetchall()

        # ---- daily activity, three series ---------------------------------
        ev = conn.execute(
            "SELECT date(at,'unixepoch') d,"
            " SUM(CASE WHEN kind='unlock_ok' THEN 1 ELSE 0 END) opens,"
            " SUM(CASE WHEN kind='shortlist' THEN 1 ELSE 0 END) shortlists "
            "FROM events WHERE at >= ? AND at < ? GROUP BY d", (since, until)).fetchall()
        rq = conn.execute(
            "SELECT date(at,'unixepoch') d, COUNT(*) n FROM requests "
            "WHERE at >= ? AND at < ? GROUP BY d", (since, until)).fetchall()
        by_day = {}
        for r in ev:
            by_day[r["d"]] = {"d": r["d"], "opens": r["opens"] or 0,
                              "shortlists": r["shortlists"] or 0, "requests": 0}
        for r in rq:
            row = by_day.setdefault(r["d"], {"d": r["d"], "opens": 0,
                                             "shortlists": 0, "requests": 0})
            row["requests"] = r["n"]
        # Fill the gaps across the chosen window. A chart that only plots days
        # something happened compresses a quiet fortnight into nothing and
        # reads as steady use.
        span = max(1, int((until - since) / 86400))
        series = []
        for i in range(span):
            key = time.strftime("%Y-%m-%d", time.gmtime(since + i * 86400))
            series.append(by_day.get(
                key, {"d": key, "opens": 0, "shortlists": 0, "requests": 0}))

        # Past a few months a daily bar is a hairline. Roll up to weeks so a
        # year-long range stays a chart rather than a smear.
        out["bucket"] = "day"
        if span > 120:
            out["bucket"] = "week"
            weeks = []
            for i in range(0, len(series), 7):
                chunk = series[i:i + 7]
                weeks.append({
                    "d": chunk[0]["d"],
                    "opens": sum(c["opens"] for c in chunk),
                    "shortlists": sum(c["shortlists"] for c in chunk),
                    "requests": sum(c["requests"] for c in chunk),
                })
            series = weeks
        out["by_day"] = series
        out["span_days"] = span
        out["start"] = since
        out["end"] = until

        # ---- which creators draw interest, with enough to recognise them ---
        out["top_creators"] = conn.execute(
            "SELECT e.detail code, COUNT(*) n, cr.name, cr.tier, cr.platform,"
            " cr.photo, cr.followers "
            "FROM events e LEFT JOIN creators cr ON cr.code = e.detail "
            "WHERE e.kind='shortlist' AND e.at >= ? AND e.at < ? AND e.detail IS NOT NULL "
            "GROUP BY e.detail ORDER BY n DESC, cr.followers DESC LIMIT 12",
            (since, until)).fetchall()

        # ---- what the shortlisting says about demand -----------------------
        out["by_tier"] = conn.execute(
            "SELECT cr.tier k, COUNT(*) n FROM events e "
            "JOIN creators cr ON cr.code = e.detail "
            "WHERE e.kind='shortlist' AND e.at >= ? AND e.at < ? GROUP BY cr.tier ORDER BY n DESC",
            (since, until)).fetchall()
        out["by_platform"] = conn.execute(
            "SELECT cr.platform k, COUNT(*) n FROM events e "
            "JOIN creators cr ON cr.code = e.detail "
            "WHERE e.kind='shortlist' AND e.at >= ? AND e.at < ? GROUP BY cr.platform ORDER BY n DESC",
            (since, until)).fetchall()

        # ---- why codes were refused ----------------------------------------
        out["fail_reasons"] = conn.execute(
            "SELECT COALESCE(detail,'unknown') k, COUNT(*) n FROM events "
            "WHERE kind='unlock_fail' AND at >= ? AND at < ? GROUP BY k ORDER BY n DESC",
            (since, until)).fetchall()
    return out


# A creator can serve more than one city — Riyadh and Jeddah is common for
# anyone who travels for shoots. Stored in the one `city` column as a joined
# string rather than a second table: it is a short list per creator, it has to
# survive a CSV round trip, and a join table would buy nothing but migrations.
CITY_SPLIT = ",;\u060c\u061b/"     # includes the Arabic comma and semicolon


def split_cities(text):
    """"Riyadh, Jeddah" -> ["Riyadh", "Jeddah"]. Order kept, duplicates dropped."""
    if not text:
        return []
    out, seen = [], set()
    buf = ""
    for ch in str(text):
        if ch in CITY_SPLIT:
            buf, part = "", buf.strip()
        else:
            buf += ch
            continue
        if part and part.lower() not in seen:
            seen.add(part.lower()); out.append(part)
    part = buf.strip()
    if part and part.lower() not in seen:
        out.append(part)
    return out


def join_cities(values):
    """The stored form. One place, so the form, the importer and the export
    cannot drift into three slightly different separators."""
    out, seen = [], set()
    for v in values or []:
        v = (v or "").strip()
        if v and v.lower() not in seen:
            seen.add(v.lower()); out.append(v)
    return ", ".join(out)


# The categories offered out of the box. The list a dashboard shows has to
# start somewhere; anything typed into "add" joins it from then on, so this is
# a starting point rather than a fixed vocabulary.
DEFAULT_INTERESTS = [
    "Skincare", "Hair Care", "Make-up", "Fragrance", "Beauty",
    "Fashion", "Lifestyle", "Food", "Fitness", "Wellness",
    "Travel", "Motherhood", "Home", "Tech", "Gaming", "Automotive",
    "Finance", "Education", "Entertainment", "Sports",
]


def known_interests():
    """The defaults plus everything already in use, most used first — so the
    list grows from real data instead of needing a code change."""
    counts = {}
    with connect() as conn:
        for r in conn.execute("SELECT interest FROM creators "
                              "WHERE interest IS NOT NULL AND interest != ''"):
            for one in split_cities(r["interest"]):
                counts[one] = counts.get(one, 0) + 1
    used = sorted(counts, key=lambda k: (-counts[k], k.lower()))
    lower = {x.lower() for x in used}
    return used + [x for x in DEFAULT_INTERESTS if x.lower() not in lower]


def known_nationalities():
    """Every nationality already on the roster, most used first — the options
    offered in the form, so the list grows from real data."""
    counts = {}
    with connect() as conn:
        for r in conn.execute("SELECT nationality FROM creators "
                              "WHERE nationality IS NOT NULL AND nationality != ''"):
            for one in split_cities(r["nationality"]):
                counts[one] = counts.get(one, 0) + 1
    return [c for c, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))]


def known_cities():
    """Every city already on the roster, most used first — the options offered
    in the form, so the list grows from real data instead of a hard-coded set."""
    counts = {}
    with connect() as conn:
        for r in conn.execute("SELECT city FROM creators WHERE city IS NOT NULL AND city != ''"):
            for city in split_cities(r["city"]):
                counts[city] = counts.get(city, 0) + 1
    return [c for c, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))]


def upsert_creator(c):
    with connect() as conn:
        conn.execute(
            "INSERT INTO creators (code,name,handle,platform,followers,city,"
            "nationality,tier,interest,photo,profiles,active,note,sort) "
            "VALUES (:code,:name,:handle,:platform,:followers,:city,"
            ":nationality,:tier,:interest,:photo,:profiles,:active,:note,:sort) "
            "ON CONFLICT(code) DO UPDATE SET "
            " name=excluded.name, handle=excluded.handle, platform=excluded.platform, "
            " followers=excluded.followers, city=excluded.city, "
             " nationality=excluded.nationality, tier=excluded.tier, "
            " interest=excluded.interest, photo=excluded.photo, "
             " profiles=excluded.profiles, active=excluded.active, "
            " note=excluded.note, sort=excluded.sort",
            c,
        )


# The four the roster shipped with. Only ever used to fill an empty table —
# once a tier is in the database, that row is the truth and this is history.
SEED_TIERS = [
    ("Nano",     "NA", 435,  870,  "Under 10K",   1),
    ("Micro",    "MI", 870,  1740, "10K – 50K",   2),
    ("Mid-Tier", "MD", 1450, 2900, "50K – 500K",  3),
    ("Macro",    "MC", 2175, 4350, "500K – 1M",   4),
]


def seed_tiers(conn=None):
    own = conn is None
    conn = conn or connect().__enter__()
    try:
        if conn.execute("SELECT COUNT(*) c FROM tiers").fetchone()["c"]:
            return
        conn.executemany(
            "INSERT INTO tiers (name,code,price_from,price_to,reach,sort) "
            "VALUES (?,?,?,?,?,?)", SEED_TIERS)
    finally:
        if own:
            conn.commit(); conn.close()


def list_tiers():
    with connect() as conn:
        return conn.execute("SELECT * FROM tiers ORDER BY sort, price_from").fetchall()


# The platforms the dashboard offers. A creator can be stored on something
# else; this is what the dropdown lists, not a constraint.
PLATFORMS = ["Instagram", "TikTok", "Snapchat", "YouTube", "X", "Facebook"]

PROFILE_PATTERNS = {
    "Instagram": "https://www.instagram.com/%s/",
    "TikTok": "https://www.tiktok.com/@%s",
    "Snapchat": "https://www.snapchat.com/add/%s",
    "YouTube": "https://www.youtube.com/@%s",
    "X": "https://x.com/%s",
    "Facebook": "https://www.facebook.com/%s",
}


def profile_url(platform, handle):
    """A full URL from a bare handle. Used to migrate the old rows, and to
    rescue a spreadsheet cell holding a username where a link was asked for."""
    handle = (handle or "").strip().lstrip("@")
    if not handle:
        return ""
    pattern = PROFILE_PATTERNS.get(platform)
    return (pattern % handle) if pattern else ""


def handle_from_url(url):
    """The username inside a profile link.

    Derived rather than typed now: the link is what is stored. Kept because
    photos are matched by handle and the export reads better with one.
    """
    text = (url or "").strip().rstrip("/")
    if not text:
        return ""
    text = text.split("?")[0].split("#")[0]
    return text.rsplit("/", 1)[-1].lstrip("@")


def as_count(value):
    """A follower count from whatever the form or the sheet supplied."""
    if value is None or value == "":
        return None
    text = str(value).replace(",", "").replace(" ", "").strip()
    return int(text) if text.isdigit() else None


def split_profiles(raw):
    """Stored JSON -> [{"platform", "url"}]. Never raises: a row written by an
    older version must not take the whole roster page down."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        platform = (item.get("platform") or "").strip()
        if url and platform:
            out.append({"platform": platform, "url": url,
                        "followers": as_count(item.get("followers"))})
    return out


def join_profiles(items):
    clean, seen = [], set()
    for item in items or []:
        url = (item.get("url") or "").strip()
        platform = (item.get("platform") or "").strip()
        if not url or not platform:
            continue
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url.lstrip("/")
        # Deduplicated by LINK, not by platform. A creator can run two
        # Instagram accounts — a personal one and a brand one, or English and
        # Arabic — and refusing the second was an assumption, not a rule. The
        # same link twice is still a slip.
        key = url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        clean.append({"platform": platform, "url": url,
                      "followers": as_count(item.get("followers"))})
    return json.dumps(clean, ensure_ascii=False) if clean else None


def total_followers(profiles):
    """Reach across every platform. Used when nobody typed a headline number:
    a creator on three platforms has a total, and asking for it twice invites
    the two to disagree."""
    counts = [p["followers"] for p in profiles if p.get("followers")]
    return sum(counts) if counts else None


def get_tier(name):
    # Not `tier`: next_code() takes a parameter of that name, and the shadowing
    # made the lookup inside it resolve to the string rather than the function.
    with connect() as conn:
        return conn.execute("SELECT * FROM tiers WHERE name = ?", (name,)).fetchone()


def tier_prices():
    """{name: (from, to)} — what prices a selection."""
    return {t["name"]: (t["price_from"], t["price_to"]) for t in list_tiers()}


def tier_names():
    return [t["name"] for t in list_tiers()]


def save_tier(name, code, price_from, price_to, reach=None, sort=0):
    with connect() as conn:
        conn.execute(
            "INSERT INTO tiers (name,code,price_from,price_to,reach,sort) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET "
            " code=excluded.code, price_from=excluded.price_from, "
            " price_to=excluded.price_to, reach=excluded.reach, sort=excluded.sort",
            (name, code, price_from, price_to, reach, sort))


def rename_tier(old, new):
    """Carries the creators across. A tier renamed out from under them would
    leave rows pointing at a tier that no longer exists, and those creators
    would price at nothing."""
    with connect() as conn:
        conn.execute("UPDATE tiers SET name = ? WHERE name = ?", (new, old))
        conn.execute("UPDATE creators SET tier = ? WHERE tier = ?", (new, old))


def delete_tier(name):
    """Refuses while creators still use it — returns how many, so the caller
    can say so rather than orphaning them."""
    with connect() as conn:
        used = conn.execute(
            "SELECT COUNT(*) c FROM creators WHERE tier = ?", (name,)).fetchone()["c"]
        if used:
            return used
        conn.execute("DELETE FROM tiers WHERE name = ?", (name,))
        return 0


def next_code(tier, prefix="HV"):
    """The next free code for a tier, e.g. HV-NA-029.

    Derived from what is already in the database rather than from a counter, so
    it stays correct after deletions, after an import, and if two people add a
    creator at once — the UNIQUE constraint on the primary key is the backstop,
    and the caller retries.
    """
    row = get_tier(tier)
    part = row["code"] if row else "XX"
    like = prefix + "-" + part + "-%"
    with connect() as conn:
        rows = conn.execute("SELECT code FROM creators WHERE code LIKE ?", (like,)).fetchall()
    highest = 0
    for r in rows:
        tail = r["code"].rsplit("-", 1)[-1]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return "%s-%s-%03d" % (prefix, part, highest + 1)


def list_creators(active_only=False):
    q = "SELECT * FROM creators"
    if active_only:
        q += " WHERE active = 1"
    q += " ORDER BY sort, code"
    with connect() as conn:
        return conn.execute(q).fetchall()


def creator(code):
    with connect() as conn:
        return conn.execute("SELECT * FROM creators WHERE code = ?", (code,)).fetchone()


def delete_creator(code):
    with connect() as conn:
        conn.execute("DELETE FROM creators WHERE code = ?", (code,))


# ---------------------------------------------------------------- requests --

def create_request(code_id, name, company, email, phone, selection_name, selection):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO requests (at, code_id, name, company, email, phone, selection_name, selection) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (now(), code_id, name, company, email, phone, selection_name, json.dumps(selection)),
        )
        return cur.lastrowid


def list_requests(limit=200):
    with connect() as conn:
        return conn.execute(
            "SELECT r.*, c.label code_label FROM requests r "
            "LEFT JOIN codes c ON c.id = r.code_id ORDER BY r.at DESC LIMIT ?",
            (limit,),
        ).fetchall()


def request(rid):
    with connect() as conn:
        return conn.execute(
            "SELECT r.*, c.label code_label FROM requests r "
            "LEFT JOIN codes c ON c.id = r.code_id WHERE r.id = ?", (rid,)
        ).fetchone()


def mark_handled(rid, handled=True):
    with connect() as conn:
        conn.execute("UPDATE requests SET handled_at = ? WHERE id = ?",
                     (now() if handled else None, rid))
