"""SQLite schema and queries for the catalogue admin.

One file, no ORM, no dependencies. The whole point of this service is that it
drops onto a server with nothing but Python 3 and starts working.

Every write goes through a function here rather than raw SQL at the call site,
so the shape of the data stays in one place.
"""

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
  hint        TEXT NOT NULL,            -- last 4 chars, so the list is readable
  label       TEXT NOT NULL,            -- who it was issued to
  created_at  INTEGER NOT NULL,
  expires_at  INTEGER,                  -- NULL = no expiry
  revoked_at  INTEGER,
  max_uses    INTEGER,                  -- NULL = unlimited
  uses        INTEGER NOT NULL DEFAULT 0
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
  tier      TEXT NOT NULL,
  interest  TEXT,
  photo     TEXT,
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

def create_code(code_hash, hint, label, expires_at=None, max_uses=None):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO codes (code_hash, hint, label, created_at, expires_at, max_uses) "
            "VALUES (?,?,?,?,?,?)",
            (code_hash, hint, label, now(), expires_at, max_uses),
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


def stats(days=30):
    since = now() - days * 86400
    with connect() as conn:
        out = {}
        out["unlocks"] = conn.execute(
            "SELECT COUNT(*) c FROM events WHERE kind='unlock_ok' AND at > ?", (since,)
        ).fetchone()["c"]
        out["failures"] = conn.execute(
            "SELECT COUNT(*) c FROM events WHERE kind='unlock_fail' AND at > ?", (since,)
        ).fetchone()["c"]
        out["requests"] = conn.execute(
            "SELECT COUNT(*) c FROM requests WHERE at > ?", (since,)
        ).fetchone()["c"]
        out["live_codes"] = conn.execute(
            "SELECT COUNT(*) c FROM codes WHERE revoked_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > ?)", (now(),)
        ).fetchone()["c"]
        out["by_code"] = conn.execute(
            "SELECT c.label, c.hint, COUNT(e.id) n, MAX(e.at) last "
            "FROM codes c LEFT JOIN events e ON e.code_id = c.id AND e.kind='unlock_ok' AND e.at > ? "
            "GROUP BY c.id ORDER BY n DESC", (since,)
        ).fetchall()
        out["by_day"] = conn.execute(
            "SELECT date(at,'unixepoch') d, COUNT(*) n FROM events "
            "WHERE kind='unlock_ok' AND at > ? GROUP BY d ORDER BY d", (since,)
        ).fetchall()
        out["top_creators"] = conn.execute(
            "SELECT detail, COUNT(*) n FROM events WHERE kind='shortlist' AND at > ? "
            "GROUP BY detail ORDER BY n DESC LIMIT 15", (since,)
        ).fetchall()
    return out


# ---------------------------------------------------------------- creators --

def upsert_creator(c):
    with connect() as conn:
        conn.execute(
            "INSERT INTO creators (code,name,handle,platform,followers,city,tier,interest,photo,active,note,sort) "
            "VALUES (:code,:name,:handle,:platform,:followers,:city,:tier,:interest,:photo,:active,:note,:sort) "
            "ON CONFLICT(code) DO UPDATE SET "
            " name=excluded.name, handle=excluded.handle, platform=excluded.platform, "
            " followers=excluded.followers, city=excluded.city, tier=excluded.tier, "
            " interest=excluded.interest, photo=excluded.photo, active=excluded.active, "
            " note=excluded.note, sort=excluded.sort",
            c,
        )


TIER_CODE = {"Nano": "NA", "Micro": "MI", "Mid-Tier": "MD", "Macro": "MC"}


def next_code(tier, prefix="HV"):
    """The next free code for a tier, e.g. HV-NA-029.

    Derived from what is already in the database rather than from a counter, so
    it stays correct after deletions, after an import, and if two people add a
    creator at once — the UNIQUE constraint on the primary key is the backstop,
    and the caller retries.
    """
    part = TIER_CODE.get(tier, "XX")
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
