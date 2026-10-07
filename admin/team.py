"""Who may do what in the admin, and how they prove it is them.

* **Roles**, enforced on the server for every request:
  - owner  — everything, including the team and security settings
  - admin  — everything except managing the team
  - kam    — day-to-day client work (selections, campaigns, quotes, creators, clients);
             no system settings, API keys, pricing tiers, imports or deletes
  - viewer — read-only
  Admins created before roles existed are owners, so nobody loses access.
* **Two-step sign-in** (TOTP, RFC 6238) with any authenticator app. Optional per person; an owner
  can require it for some or all roles. A used code cannot be replayed.
* **Idle sign-out** and a **password re-check** (step-up) before keys, exports and team changes.
* A **security log** (sign-ins, failures, two-step changes, role changes, keys, exports) that is
  only ever appended to.
"""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time

import db

ROLES = ["owner", "admin", "kam", "viewer"]
ROLE_LABEL = {"owner": "Owner", "admin": "Admin", "kam": "Key account manager", "viewer": "Viewer"}
ROLE_HELP = {
    "owner": "Everything, including the team, roles and security settings.",
    "admin": "Everything except managing the team.",
    "kam": "Selections, campaigns, quotes, creators and clients. No system settings, API keys, tiers, imports or deletes.",
    "viewer": "Can look at everything except settings and keys; cannot change anything.",
}
REAUTH_SECONDS = 10 * 60
DEFAULT_IDLE_MINUTES = 120

SCHEMA = """
CREATE TABLE IF NOT EXISTS security_log (
    id INTEGER PRIMARY KEY,
    at INTEGER NOT NULL,
    actor TEXT,
    kind TEXT NOT NULL,
    detail TEXT,
    ip TEXT
);
CREATE INDEX IF NOT EXISTS security_log_at ON security_log(at);
"""


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        acols = {r["name"] for r in conn.execute("PRAGMA table_info(admins)")}
        for col, ddl in (("role", "TEXT"), ("name", "TEXT"), ("totp_secret", "TEXT"), ("totp_on", "INTEGER NOT NULL DEFAULT 0"),
                         ("totp_last", "INTEGER"), ("disabled_at", "INTEGER")):
            if col not in acols:
                conn.execute("ALTER TABLE admins ADD COLUMN %s %s" % (col, ddl))
        scols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)")}
        for col, ddl in (("last_seen", "INTEGER"), ("reauth_at", "INTEGER")):
            if col not in scols:
                conn.execute("ALTER TABLE sessions ADD COLUMN %s %s" % (col, ddl))


def role_of(who):
    r = (who["role"] if who is not None and "role" in who.keys() else None) or "owner"
    return r if r in ROLES else "viewer"


# ------------------------------------------------------------- permissions --

# Paths a KAM may never change (POST). Prefix match.
_KAM_DENY_POST = ("/settings", "/apis", "/portal/settings", "/portal/keys", "/tiers", "/roster/delete", "/roster/import",
                  "/roster/merge", "/roster/photos", "/team", "/planner/library", "/codes/delete",
                  "/portal/user/delete")
# Pages only owners and admins may open (GET). Prefix match; /portal?tab=settings handled separately.
_STAFF_ONLY_GET = ("/apis", "/settings")
# What a viewer may still POST: their own account and the read-only copilot chat.
_VIEWER_POST = ("/password", "/account/", "/ai/chat", "/reauth")


def can(who, method, path, query=None):
    """True when this admin's role allows the request. Every route goes through this."""
    role = role_of(who)
    query = query or {}
    if role == "owner":
        return True
    if path.startswith("/team") and method == "POST":
        return False                                     # only owners manage the team
    if role == "admin":
        return True
    if method == "GET":
        if any(path == p or path.startswith(p + "/") for p in _STAFF_ONLY_GET):
            return False
        if path == "/portal" and query.get("tab") == "settings":
            return False
        if path == "/portal/usage.csv":
            return False
        return True
    # POST
    if role == "viewer":
        return any(path.startswith(p) for p in _VIEWER_POST)
    if path == "/ai/confirm":
        return False                                     # copilot changes are confirmed by owners and admins
    return not any(path == p or path.startswith(p + "/") or path.startswith(p) for p in _KAM_DENY_POST)


# Actions that need the password typed again within the last 10 minutes.
STEP_UP_POST = ("/portal/keys", "/apis/token", "/settings/token", "/team/")
STEP_UP_GET = ("/roster/export", "/portal/usage.csv")


def needs_step_up(method, path):
    if method == "POST":
        return any(path.startswith(p) for p in STEP_UP_POST)
    return any(path.startswith(p) for p in STEP_UP_GET)


def fresh(who):
    r = who["reauth_at"] if "reauth_at" in who.keys() else None
    return bool(r) and db.now() - r < REAUTH_SECONDS


def mark_reauth(token):
    with db.connect() as conn:
        conn.execute("UPDATE sessions SET reauth_at = ? WHERE token = ?", (db.now(), token))


# ------------------------------------------------------------------ idling --

def idle_minutes():
    try:
        return max(5, min(24 * 60, int(db.setting("admin_idle_minutes", DEFAULT_IDLE_MINUTES))))
    except (TypeError, ValueError):
        return DEFAULT_IDLE_MINUTES


def check_idle(token, row):
    """None when the session has been idle too long (and is ended); else the row. Activity is
    written at most once a minute."""
    now = db.now()
    seen = (row["last_seen"] if "last_seen" in row.keys() else None) or row["created_at"]
    if now - seen > idle_minutes() * 60:
        db.drop_session(token)
        return None
    if now - seen > 60:
        with db.connect() as conn:
            conn.execute("UPDATE sessions SET last_seen = ? WHERE token = ?", (now, token))
    return row


# -------------------------------------------------------------------- TOTP --

def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret, counter):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    return "%06d" % ((struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % 1000000)


def totp_matches(secret, code, last=None, at=None):
    """The time step the code matches (allowing one step either side), or None. A step at or before
    ``last`` is refused, so the same code cannot be used twice."""
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != 6 or not secret:
        return None
    step = int((at or time.time()) // 30)
    for s in (step - 1, step, step + 1):
        if last is not None and s <= last:
            continue
        if hmac.compare_digest(_code(secret, s), code):
            return s
    return None


def otpauth_uri(secret, email):
    from urllib.parse import quote
    return "otpauth://totp/%s?secret=%s&issuer=%s&digits=6&period=30" % (
        quote("HelloVoice Admin:" + email), secret, quote("HelloVoice Admin"))


def set_totp(admin_id, secret, on):
    with db.connect() as conn:
        conn.execute("UPDATE admins SET totp_secret = ?, totp_on = ?, totp_last = NULL WHERE id = ?",
                     (secret if on else None, 1 if on else 0, admin_id))


def use_totp_step(admin_id, step):
    with db.connect() as conn:
        conn.execute("UPDATE admins SET totp_last = ? WHERE id = ?", (step, admin_id))


def required_roles():
    v = db.setting("require_2fa_roles", []) or []
    return [r for r in v if r in ROLES]


def must_use_2fa(admin_row):
    return role_of(admin_row) in required_roles()


# --------------------------------------------------------------------- team --

def admin_by_id(aid):
    with db.connect() as conn:
        return conn.execute("SELECT * FROM admins WHERE id = ?", (aid,)).fetchone()


def list_admins():
    with db.connect() as conn:
        return conn.execute(
            "SELECT a.*, (SELECT MAX(last_seen) FROM sessions s WHERE s.admin_id = a.id) AS active_at "
            "FROM admins a ORDER BY a.disabled_at IS NOT NULL, a.created_at").fetchall()


def owners_left(excluding=None):
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM admins WHERE COALESCE(role, 'owner') = 'owner' AND disabled_at IS NULL "
                            "AND id != COALESCE(?, -1)", (excluding,)).fetchone()[0]


def invite(email, name, role):
    """A new team member with a one-time password the owner passes on. Returns that password."""
    import auth
    email = (email or "").strip().lower()
    if "@" not in email or role not in ROLES:
        raise ValueError("Enter an email address and choose a role.")
    if db.admin_by_email(email):
        raise ValueError("That person is already on the team.")
    pw = "HV-" + secrets.token_urlsafe(9)
    with db.connect() as conn:
        conn.execute("INSERT INTO admins (email, password_hash, created_at, role, name) VALUES (?,?,?,?,?)",
                     (email, auth.hash_password(pw), db.now(), role, " ".join(str(name or "").split())[:80] or None))
    return pw


def set_role(aid, role):
    if role not in ROLES:
        raise ValueError("Unknown role.")
    a = admin_by_id(aid)
    if a is None:
        raise ValueError("No such person.")
    if role_of(a) == "owner" and role != "owner" and not owners_left(excluding=aid):
        raise ValueError("Keep at least one owner.")
    with db.connect() as conn:
        conn.execute("UPDATE admins SET role = ? WHERE id = ?", (role, aid))


def set_disabled(aid, off):
    a = admin_by_id(aid)
    if a is None:
        raise ValueError("No such person.")
    if off and role_of(a) == "owner" and not owners_left(excluding=aid):
        raise ValueError("Keep at least one owner.")
    with db.connect() as conn:
        conn.execute("UPDATE admins SET disabled_at = ? WHERE id = ?", (db.now() if off else None, aid))
        if off:
            conn.execute("DELETE FROM sessions WHERE admin_id = ?", (aid,))


def end_sessions(aid, keep=None):
    with db.connect() as conn:
        conn.execute("DELETE FROM sessions WHERE admin_id = ? AND token != COALESCE(?, '')", (aid, keep))


# ------------------------------------------------------------- security log --

def log(kind, actor="", detail="", ip=None):
    with db.connect() as conn:
        conn.execute("INSERT INTO security_log (at, actor, kind, detail, ip) VALUES (?,?,?,?,?)",
                     (db.now(), actor or "", kind, (detail or "")[:300], ip))


def recent_log(limit=200):
    with db.connect() as conn:
        return conn.execute("SELECT * FROM security_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
