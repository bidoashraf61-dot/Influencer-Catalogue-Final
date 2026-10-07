"""Client accounts, one-time sign-in codes, AI credits, briefs and chat history.

Design in one paragraph. The catalogue already knows who is looking by the
``code_id`` in the signed ``hv_view`` ticket, and every client-owned thing
(selections, campaigns, events) hangs off that id. A signed-up client therefore
gets a **personal access-code row** that nobody ever types: sign-in with an
email OTP mints the same ticket the passcode flow does. Revoking that row in
the dashboard shuts the client out at once, device limits still apply, and
nothing else in the admin has to learn about "users". Credits are keyed by
``code_id`` too, so a guest passcode and a signed-up client are metered by one
mechanism.
"""
import hashlib
import hmac
import json
import secrets
import time

import db
import guard

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT, company TEXT, job_title TEXT, phone TEXT,
    domain TEXT,
    code_id INTEGER REFERENCES codes(id),
    status TEXT NOT NULL DEFAULT 'active',          -- active | pending | suspended
    created_at INTEGER NOT NULL,
    last_login_at INTEGER,
    signup_ip TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS users_code ON users(code_id);

CREATE TABLE IF NOT EXISTS otp (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    used_at INTEGER,
    ip TEXT
);
CREATE INDEX IF NOT EXISTS otp_email ON otp(email, created_at);

CREATE TABLE IF NOT EXISTS credit_ledger (
    id INTEGER PRIMARY KEY,
    code_id INTEGER NOT NULL,
    delta INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    reason TEXT NOT NULL,
    ref TEXT,
    actor TEXT,
    at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ledger_code ON credit_ledger(code_id, id);

CREATE TABLE IF NOT EXISTS briefs (
    id INTEGER PRIMARY KEY,
    code_id INTEGER NOT NULL,
    user_id INTEGER,
    selection_id INTEGER,
    source TEXT NOT NULL DEFAULT 'mcq',             -- mcq | text | chat
    answers TEXT NOT NULL DEFAULT '{}',
    summary TEXT,
    objective TEXT,
    target TEXT,
    result TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS briefs_code ON briefs(code_id, created_at);

CREATE TABLE IF NOT EXISTS ai_audit (
    id INTEGER PRIMARY KEY,
    at INTEGER NOT NULL,
    code_id INTEGER,
    kind TEXT NOT NULL,
    model TEXT,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    out_tokens INTEGER NOT NULL DEFAULT 0,
    credits INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    ok INTEGER NOT NULL DEFAULT 1,
    latency_ms INTEGER,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS ai_audit_at ON ai_audit(at);

CREATE TABLE IF NOT EXISTS chat_threads (
    id INTEGER PRIMARY KEY,
    code_id INTEGER,
    scope TEXT NOT NULL DEFAULT 'client',           -- client | admin
    owner TEXT,
    title TEXT,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY,
    thread_id INTEGER NOT NULL REFERENCES chat_threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                             -- user | model | tool
    content TEXT NOT NULL,
    meta TEXT,
    at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS chat_msgs ON chat_messages(thread_id, id);
"""

OTP_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 30

DEFAULT_COSTS = {"brief": 5, "parse": 1, "chat": 1, "search": 2}
DEFAULT_GUEST_CREDITS = 10
DEFAULT_SIGNUP_CREDITS = 50


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(ai_audit)")}
        if "cost_usd" not in cols:
            conn.execute("ALTER TABLE ai_audit ADD COLUMN cost_usd REAL NOT NULL DEFAULT 0")
        conn.execute("CREATE INDEX IF NOT EXISTS ai_audit_code ON ai_audit(code_id, at)")


# ----------------------------------------------------------------- settings --

def costs():
    got = db.setting("ai_costs", {}) or {}
    out = dict(DEFAULT_COSTS)
    for k, v in got.items():
        try:
            out[k] = max(0, int(v))
        except (TypeError, ValueError):
            pass
    return out


def guest_credits():
    try:
        return max(0, int(db.setting("guest_credits", DEFAULT_GUEST_CREDITS)))
    except (TypeError, ValueError):
        return DEFAULT_GUEST_CREDITS


def signup_credits():
    try:
        return max(0, int(db.setting("signup_credits", DEFAULT_SIGNUP_CREDITS)))
    except (TypeError, ValueError):
        return DEFAULT_SIGNUP_CREDITS


def signup_mode():
    # Default is approval: the roster is confidential, so a new company is let in by a person.
    m = db.setting("signup_mode", "approval")
    return m if m in ("open", "approval", "allowlist", "closed") else "approval"


def _list_setting(key):
    v = db.setting(key, []) or []
    if isinstance(v, str):
        v = [x for x in v.replace(",", "\n").split()]
    return [str(x).strip().lower() for x in v if str(x).strip()]


def domain_lists():
    return _list_setting("domain_allow"), _list_setting("domain_block")


# -------------------------------------------------------------------- email --

def check_email(raw):
    """(email, None) when this address may sign up, else ('', reason)."""
    allow, block = domain_lists()
    email, why = guard.company_email(raw, allow, block)
    if why:
        return "", why
    if user_by_email(email):
        return email, None                    # an existing client can always sign back in
    if signup_mode() == "closed":
        return "", "closed"
    if signup_mode() == "allowlist":
        domain = email.rsplit("@", 1)[1]
        if not guard._matches(domain, set(allow)):
            return "", "not_invited"
    return email, None


def _salt():
    s = db.setting("otp_salt")
    if not s:
        s = secrets.token_hex(24)
        db.set_setting("otp_salt", s)
    return s


def _otp_hash(email, code):
    return hashlib.sha256(("%s:%s:%s" % (_salt(), email, code)).encode()).hexdigest()


def new_otp(email, ip=None):
    """Create a sign-in code for ``email``. Returns ``(code, None)`` or
    ``(None, "wait")`` inside the resend cooldown. Older unused codes for the
    address stop working."""
    now = db.now()
    _salt()                      # created before the write lock below: a second writer would deadlock on it
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        last = conn.execute("SELECT created_at FROM otp WHERE email = ? ORDER BY id DESC LIMIT 1",
                            (email,)).fetchone()
        if last and now - last["created_at"] < OTP_RESEND_SECONDS:
            return None, "wait"
        # Earlier unexpired codes stay valid (the last 3): asking for a new one must not be a way
        # to knock a client's live code out. Older ones are retired.
        conn.execute("UPDATE otp SET used_at = ? WHERE email = ? AND used_at IS NULL AND id NOT IN "
                     "(SELECT id FROM otp WHERE email = ? AND used_at IS NULL ORDER BY id DESC LIMIT 2)", (now, email, email))
        code = "%06d" % secrets.randbelow(1000000)
        conn.execute("INSERT INTO otp (email, code_hash, created_at, expires_at, ip) VALUES (?,?,?,?,?)",
                     (email, _otp_hash(email, code), now, now + OTP_MINUTES * 60, ip))
        # Housekeeping: a week-old code is of no use to anyone.
        conn.execute("DELETE FROM otp WHERE created_at < ?", (now - 7 * 86400,))
    return code, None


def check_otp(email, code):
    """(True, None) when ``code`` is the live code for ``email`` (and uses it up),
    else (False, reason) with reason in invalid / expired / locked."""
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    now = db.now()
    _salt()
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("SELECT * FROM otp WHERE email = ? AND used_at IS NULL ORDER BY id DESC LIMIT 3",
                            (email,)).fetchall()
        if not rows:
            return False, "invalid"
        live = [r for r in rows if r["expires_at"] >= now]
        if not live:
            return False, "expired"
        open_ = [r for r in live if r["attempts"] < OTP_MAX_ATTEMPTS]
        if not open_:
            return False, "locked"
        match = None
        for r in open_:
            conn.execute("UPDATE otp SET attempts = attempts + 1 WHERE id = ?", (r["id"],))
            if len(code) == 6 and hmac.compare_digest(r["code_hash"], _otp_hash(email, code)):
                match = r
        if not match:
            return False, "invalid"
        conn.execute("UPDATE otp SET used_at = ? WHERE email = ? AND used_at IS NULL", (now, email))
    return True, None


# -------------------------------------------------------------------- users --

def user_by_email(email):
    with db.connect() as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", ((email or "").lower(),)).fetchone()


def user_by_id(uid):
    with db.connect() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def user_for_code(code_id):
    with db.connect() as conn:
        return conn.execute("SELECT * FROM users WHERE code_id = ?", (code_id,)).fetchone()


def list_users():
    with db.connect() as conn:
        return conn.execute(
            "SELECT u.*, "
            " (SELECT balance_after FROM credit_ledger l WHERE l.code_id = u.code_id ORDER BY l.id DESC LIMIT 1) AS credits, "
            " (SELECT COUNT(*) FROM selections s WHERE s.code_id = u.code_id) AS selections, "
            " (SELECT COUNT(*) FROM campaigns c WHERE c.code_id = u.code_id) AS campaigns, "
            " (SELECT COUNT(*) FROM briefs b WHERE b.code_id = u.code_id) AS briefs "
            "FROM users u ORDER BY u.created_at DESC").fetchall()


def create_user(email, name, company, job_title="", phone="", ip=None):
    """Make the account, its personal access-code row and its starting credits.
    Returns the user row. A pending account (approval mode) gets a revoked code and no
    credits until an admin activates it. Safe against a double submit: the second call
    returns the account the first one made."""
    import sqlite3
    email = email.lower()
    existing = user_by_email(email)
    if existing:
        return existing
    clean = lambda v, n: " ".join(str(v or "").split())[:n]
    status = "pending" if signup_mode() == "approval" else "active"
    token = secrets.token_hex(32)
    max_dev = db.setting("user_max_devices", 5)
    try:
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
                return user_by_email(email)
            cur = conn.execute(
                "INSERT INTO codes (code_hash, hint, label, created_at, max_devices, revoked_at) VALUES (?,?,?,?,?,?)",
                (hashlib.sha256(("hv-user:" + token).encode()).hexdigest(), "····", "Client: " + email, db.now(),
                 max_dev if isinstance(max_dev, int) and max_dev > 0 else 5, db.now() if status == "pending" else None))
            code_id = cur.lastrowid
            cur = conn.execute(
                "INSERT INTO users (email, name, company, job_title, phone, domain, code_id, status, created_at, signup_ip) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (email, clean(name, 120), clean(company, 160), clean(job_title, 120), clean(phone, 40),
                 email.rsplit("@", 1)[1], code_id, status, db.now(), ip))
            uid = cur.lastrowid
    except sqlite3.IntegrityError:
        return user_by_email(email)
    if status == "active":
        grant(code_id, signup_credits(), "Welcome credits", actor="system")
    return user_by_id(uid)


def signups_per_ip():
    """New accounts one network may create per day (stops welcome-credit farming)."""
    try:
        return max(1, int(db.setting("signups_per_ip_day", 3)))
    except (TypeError, ValueError):
        return 3


def signups_from(ip, hours=24):
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM users WHERE signup_ip = ? AND created_at >= ?",
                            (ip, db.now() - hours * 3600)).fetchone()[0]


def update_profile(uid, **fields):
    allowed = {"name": 120, "company": 160, "job_title": 120, "phone": 40, "notes": 500}
    sets, vals = [], []
    for k, n in allowed.items():
        if k in fields and fields[k] is not None:
            sets.append(k + " = ?")
            vals.append(" ".join(str(fields[k]).split())[:n])
    if sets:
        with db.connect() as conn:
            conn.execute("UPDATE users SET %s WHERE id = ?" % ", ".join(sets), vals + [uid])
    return user_by_id(uid)


def set_status(uid, status):
    """active / suspended / pending. Anything but active revokes the personal code, so the
    client is out on their next request. Activating lifts only that revocation (a code an
    admin revoked from the Codes page while the account was active stays revoked), and grants
    the welcome credits once."""
    assert status in ("active", "suspended", "pending")
    u = user_by_id(uid)
    if not u:
        return None
    with db.connect() as conn:
        conn.execute("UPDATE users SET status = ? WHERE id = ?", (status, uid))
        if status != "active":
            conn.execute("UPDATE codes SET revoked_at = COALESCE(revoked_at, ?) WHERE id = ?", (db.now(), u["code_id"]))
        elif u["status"] != "active":
            conn.execute("UPDATE codes SET revoked_at = NULL WHERE id = ?", (u["code_id"],))
        had = conn.execute("SELECT 1 FROM credit_ledger WHERE code_id = ? LIMIT 1", (u["code_id"],)).fetchone()
    if status == "active" and not had:
        grant(u["code_id"], signup_credits(), "Welcome credits", actor="system")
    return user_by_id(uid)


def touch_login(uid):
    with db.connect() as conn:
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (db.now(), uid))


# ------------------------------------------------------------------ credits --

def balance(code_id):
    with db.connect() as conn:
        r = conn.execute("SELECT balance_after FROM credit_ledger WHERE code_id = ? ORDER BY id DESC LIMIT 1",
                         (code_id,)).fetchone()
    return r["balance_after"] if r else 0


def _post(conn, code_id, delta, reason, ref, actor):
    r = conn.execute("SELECT balance_after FROM credit_ledger WHERE code_id = ? ORDER BY id DESC LIMIT 1",
                     (code_id,)).fetchone()
    bal = (r["balance_after"] if r else 0) + delta
    conn.execute("INSERT INTO credit_ledger (code_id, delta, balance_after, reason, ref, actor, at) "
                 "VALUES (?,?,?,?,?,?,?)", (code_id, delta, bal, reason, ref, actor, db.now()))
    return bal


def grant(code_id, n, reason, actor="", ref=""):
    n = int(n)
    if n == 0:
        return balance(code_id)
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        return _post(conn, code_id, n, reason[:120], ref, actor)


def ensure_allowance(code_id):
    """Guest passcodes get a small one-off allowance the first time they are
    metered. Signed-up clients and the admin preview have their own rules."""
    if code_id == db.admin_code_id() or user_for_code(code_id):
        return
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM credit_ledger WHERE code_id = ? LIMIT 1", (code_id,)).fetchone():
            return
        if guest_credits():
            _post(conn, code_id, guest_credits(), "Guest allowance", "", "system")


def spend(code_id, n, reason, ref=""):
    """Atomically take ``n`` credits. Returns ``(ok, balance)``; never goes negative."""
    n = int(n)
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        r = conn.execute("SELECT balance_after FROM credit_ledger WHERE code_id = ? ORDER BY id DESC LIMIT 1",
                         (code_id,)).fetchone()
        bal = r["balance_after"] if r else 0
        if bal < n:
            return False, bal
        return True, _post(conn, code_id, -n, reason[:120], ref, "")


def charge(code_id, kind, ref=""):
    """Take the configured price of an AI action. The admin preview is free.
    Returns ``(ok, cost, balance)``."""
    cost = costs().get(kind, 1)
    if code_id == db.admin_code_id():
        return True, 0, balance(code_id)
    ensure_allowance(code_id)
    ok, bal = spend(code_id, cost, "AI: " + kind, ref)
    return ok, cost, bal


def refund(code_id, n, reason, ref=""):
    if n and code_id != db.admin_code_id():
        grant(code_id, n, "Refund: " + reason, actor="system", ref=ref)


def ledger(code_id, limit=50):
    with db.connect() as conn:
        return conn.execute("SELECT * FROM credit_ledger WHERE code_id = ? ORDER BY id DESC LIMIT ?",
                            (code_id, limit)).fetchall()


# ------------------------------------------------------------------- briefs --

def save_brief(code_id, user_id, source, answers, summary, objective, target, selection_id=None, result=None):
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO briefs (code_id, user_id, selection_id, source, answers, summary, objective, target, result, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (code_id, user_id, selection_id, source, json.dumps(answers), summary, objective,
             json.dumps(target or {}), json.dumps(result) if result is not None else None, db.now()))
        return cur.lastrowid


def briefs_for(code_id=None, limit=50):
    with db.connect() as conn:
        if code_id is None:
            return conn.execute("SELECT * FROM briefs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return conn.execute("SELECT * FROM briefs WHERE code_id = ? ORDER BY id DESC LIMIT ?",
                            (code_id, limit)).fetchall()


def brief(bid):
    with db.connect() as conn:
        return conn.execute("SELECT * FROM briefs WHERE id = ?", (bid,)).fetchone()


# --------------------------------------------------------------------- chat --

def thread(code_id, scope="client", owner="", tid=None):
    """An existing thread of this owner, or a new one."""
    with db.connect() as conn:
        if tid:
            row = conn.execute("SELECT * FROM chat_threads WHERE id = ? AND scope = ? AND "
                               "COALESCE(code_id, 0) = COALESCE(?, 0) AND COALESCE(owner, '') = ?",
                               (tid, scope, code_id, owner)).fetchone()
            if row:
                return row
        cur = conn.execute("INSERT INTO chat_threads (code_id, scope, owner, created_at) VALUES (?,?,?,?)",
                           (code_id, scope, owner, db.now()))
        return conn.execute("SELECT * FROM chat_threads WHERE id = ?", (cur.lastrowid,)).fetchone()


def find_thread(code_id, scope, owner, tid):
    """An existing thread belonging to this owner, or None (never creates one)."""
    with db.connect() as conn:
        return conn.execute("SELECT * FROM chat_threads WHERE id = ? AND scope = ? AND "
                            "COALESCE(code_id, 0) = COALESCE(?, 0) AND COALESCE(owner, '') = ?",
                            (tid, scope, code_id, owner)).fetchone()


def add_message(tid, role, content, meta=None):
    with db.connect() as conn:
        conn.execute("INSERT INTO chat_messages (thread_id, role, content, meta, at) VALUES (?,?,?,?,?)",
                     (tid, role, content, json.dumps(meta) if meta else None, db.now()))


def messages(tid, limit=40):
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM chat_messages WHERE thread_id = ? ORDER BY id DESC LIMIT ?",
                            (tid, limit)).fetchall()
    return list(reversed(rows))


# ------------------------------------------------------------------ tickets --

def sign_ticket(secret, email, minutes=15):
    """Short-lived proof that ``email`` passed the OTP, used to finish the profile step."""
    import auth
    return auth.sign("otp:%s:%d" % (email, int(time.time()) + minutes * 60), secret)


def read_ticket(secret, ticket):
    import auth
    raw = auth.unsign(ticket or "", secret)
    if not raw or not raw.startswith("otp:"):
        return None
    _, rest = raw.split(":", 1)
    email, _, exp = rest.rpartition(":")
    return email if exp.isdigit() and int(exp) >= time.time() else None
