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

CREATE TABLE IF NOT EXISTS credit_requests (
    id INTEGER PRIMARY KEY,
    code_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    note TEXT,
    at INTEGER NOT NULL,
    handled_at INTEGER,
    granted INTEGER,
    handled_by TEXT
);

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

# "search" is the scored shortlist without AI text: free, so every client (access code included)
# can always get one. Written reasons, the brief reader and chat spend credits.
DEFAULT_COSTS = {"brief": 5, "parse": 1, "chat": 1, "search": 0, "replace": 2, "more": 3, "alike": 2}
# "Active campaign": AI is free for a client whose campaign is live, from its start date to
# 30 days after its end date (Phase C + D, 2026-10-09). Checked in charge(), so every AI action
# (brief, parse, chat, replacement, add-more, look-alike) follows the one rule.
ACTIVE_GRACE_DAYS = 30
LOW_CREDITS = 5                    # the bell warns when a balance drops below this
DEFAULT_GUEST_CREDITS = 10
DEFAULT_SIGNUP_CREDITS = 50


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(ai_audit)")}
        if "cost_usd" not in cols:
            conn.execute("ALTER TABLE ai_audit ADD COLUMN cost_usd REAL NOT NULL DEFAULT 0")
        conn.execute("CREATE INDEX IF NOT EXISTS ai_audit_code ON ai_audit(code_id, at)")
        ucols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        for col, ddl in (("kam", "TEXT"), ("monthly_credits", "INTEGER"), ("deleted_at", "INTEGER")):
            if col not in ucols:
                conn.execute("ALTER TABLE users ADD COLUMN %s %s" % (col, ddl))
    # Portal v3: profile page, bell, analysis gating, selection status, rewards (all additive).
    import account
    import aimore
    import codelinks
    import gating
    import inbox
    import rewards
    import roi
    import selstatus
    account.init()
    codelinks.init()
    roi.init()
    aimore.init()
    rewards.init()
    inbox.init()
    selstatus.init()
    gating.init()


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
    # Default is open: any company-domain address is let in at once (Bido, 2026-10-07).
    m = db.setting("signup_mode", "open")
    return m if m in ("open", "approval", "allowlist", "closed") else "open"


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
            "FROM users u WHERE u.deleted_at IS NULL ORDER BY u.created_at DESC").fetchall()


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
    try:
        import codelinks
        codelinks.claim(email, code_id)            # an access code HelloVoice invited this address to
    except Exception:
        pass
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


MARKETS = ("SA", "AE", "EG", "KW", "QA", "BH", "OM", "JO")
LANGUAGES = ("Arabic", "English", "Arabic and English")


def update_profile(uid, **fields):
    allowed = {"name": 120, "company": 160, "job_title": 120, "phone": 40, "notes": 500, "kam": 160,
               "brands": 300, "industry": 60}
    sets, vals = [], []
    for k, n in allowed.items():
        if k in fields and fields[k] is not None:
            sets.append(k + " = ?")
            vals.append(" ".join(str(fields[k]).split())[:n])
    if fields.get("markets") is not None:
        raw = fields["markets"]
        raw = raw if isinstance(raw, list) else str(raw).replace(",", " ").split()
        sets.append("markets = ?")
        vals.append(json.dumps([m for m in dict.fromkeys(str(x).strip().upper() for x in raw) if m in MARKETS]))
    if fields.get("language") is not None:
        sets.append("language = ?")
        vals.append(fields["language"] if fields["language"] in LANGUAGES else "")
    if "monthly_credits" in fields:
        v = fields["monthly_credits"]
        sets.append("monthly_credits = ?")
        vals.append(int(v) if str(v).strip().isdigit() else None)
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
        after = _post(conn, code_id, -n, reason[:120], ref, "")
    if after < LOW_CREDITS <= bal:
        _ring_low(code_id, after)
    return True, after


def _ring_low(code_id, left):
    import inbox
    u = user_for_code(code_id)
    if u is None or u["status"] != "active":
        return
    inbox.emit([u["id"]], "credits_low", "Credits running low",
               body="%d left. Request more, or finish your profile to earn some." % left,
               href="account/#credits", ref="low:" + inbox.today(), once=True)


def active_campaign(code_id):
    """The campaign that makes AI free for this viewer, or None: one of their (team's) campaigns,
    not a draft, from its start date until 30 days after its end date. A live campaign with no
    dates counts while it is live."""
    if code_id is None or code_id == db.admin_code_id():
        return None
    ids = sorted(team_codes(code_id))
    now = db.now()
    with db.connect() as conn:
        rows = conn.execute("SELECT id, name, status, starts_at, ends_at FROM campaigns WHERE code_id IN (%s) AND status != 'draft'"
                            % ",".join("?" * len(ids)), ids).fetchall()
    best = None
    for k in rows:
        start, end = k["starts_at"], k["ends_at"]
        if start is None and end is None:
            ok = k["status"] == "live"
            until = None
        else:
            until = (end or now) + ACTIVE_GRACE_DAYS * 86400 if end else None
            ok = (start is None or start <= now) and (until is None or now <= until) and not (end is None and k["status"] == "ended")
        if ok and (best is None or (until or 10 ** 12) > (best["until"] or 10 ** 12)):
            best = {"id": k["id"], "name": k["name"], "until": until}
    return best


def ai_free(code_id):
    """What the page shows instead of a price while AI is free: ``{"campaign", "until"}`` or None."""
    k = active_campaign(code_id)
    return {"campaign": k["name"], "until": k["until"]} if k else None


def price_of(code_id, kind):
    """What an AI action costs this viewer right now: 0 while they have an active campaign."""
    if code_id == db.admin_code_id() or active_campaign(code_id):
        return 0
    return costs().get(kind, 1)


def charge(code_id, kind, ref=""):
    """Take the configured price of an AI action. The admin preview is free, and so is every AI
    action for a client with an active campaign. Returns ``(ok, cost, balance)``."""
    cost = costs().get(kind, 1)
    if code_id == db.admin_code_id() or cost <= 0 or active_campaign(code_id):
        return True, 0, balance(code_id)            # free: nothing to record
    ensure_allowance(code_id)
    monthly_refill(code_id)
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


def find_thread_any(tid):
    with db.connect() as conn:
        return conn.execute("SELECT * FROM chat_threads WHERE id = ?", (tid,)).fetchone()


def threads(code_id=None, scope="client", limit=100):
    q = ("SELECT t.*, (SELECT COUNT(*) FROM chat_messages m WHERE m.thread_id = t.id) n, "
         "(SELECT MAX(at) FROM chat_messages m WHERE m.thread_id = t.id) last, "
         "(SELECT content FROM chat_messages m WHERE m.thread_id = t.id AND role = 'user' ORDER BY id LIMIT 1) first "
         "FROM chat_threads t WHERE scope = ?" + (" AND code_id = ?" if code_id is not None else "") + " ORDER BY last DESC LIMIT ?")
    with db.connect() as conn:
        return conn.execute(q, ((scope, code_id, limit) if code_id is not None else (scope, limit))).fetchall()


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


# -------------------------------------------------------------------- teams --

def team_codes(code_id):
    """The access-code ids whose selections and campaigns this viewer may see: their own, plus
    colleagues on the same company domain when team sharing is on. Personal domains (only possible
    through the allow list) never form a team."""
    import codelinks
    me = user_for_code(code_id)
    if not me:
        return {code_id}
    if not db.setting("team_sharing", True) or guard._matches(me["domain"] or "", guard.FREE_DOMAINS):
        return {code_id} | codelinks.linked_for({code_id})
    with db.connect() as conn:
        rows = conn.execute("SELECT code_id FROM users WHERE domain = ? AND status = 'active' AND deleted_at IS NULL",
                            (me["domain"],)).fetchall()
    mine = {r["code_id"] for r in rows} | {code_id}
    # Shared access codes HelloVoice moved onto these accounts: their selections and campaigns come along.
    return mine | codelinks.linked_for(mine)


def owns(reader, code_id):
    """True when ``reader`` owns things filed under ``code_id``: it is their own code, or a shared
    access code HelloVoice linked to their account (the code's selections became theirs)."""
    if reader is None or code_id is None:
        return False
    if int(reader) == int(code_id):
        return True
    if not user_for_code(reader):
        return False
    import codelinks
    return int(code_id) in codelinks.linked_for({int(reader)})


def teammates(code_id):
    me = user_for_code(code_id)
    if not me:
        return []
    ids = team_codes(code_id) - {code_id}
    if not ids:
        return []
    with db.connect() as conn:
        return conn.execute("SELECT id, name, job_title, email, code_id FROM users WHERE code_id IN (%s) ORDER BY name"
                            % ",".join("?" * len(ids)), list(ids)).fetchall()


# ---------------------------------------------------------- monthly credits --

def monthly_allowance(user):
    v = user["monthly_credits"] if user is not None and "monthly_credits" in user.keys() else None
    if v is None:
        v = db.setting("monthly_credits", 0)
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def monthly_refill(code_id):
    """Top a signed-up client back up to their monthly allowance, once per calendar month."""
    u = user_for_code(code_id)
    n = monthly_allowance(u)
    if not u or not n or u["status"] != "active":
        return
    t = time.gmtime()
    start = int(time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, 0))) - time.timezone
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM credit_ledger WHERE code_id = ? AND reason = 'Monthly credits' AND at >= ?",
                        (code_id, start)).fetchone():
            return
        r = conn.execute("SELECT balance_after FROM credit_ledger WHERE code_id = ? ORDER BY id DESC LIMIT 1", (code_id,)).fetchone()
        bal = r["balance_after"] if r else 0
        _post(conn, code_id, max(0, n - bal), "Monthly credits", time.strftime("%Y-%m", t), "system")
    if n - bal > 0:
        import inbox
        inbox.emit([u["id"]], "credits_monthly", "%d monthly credits added" % (n - bal),
                   body="Your balance tops up to %d on the 1st of each month" % n, href="account/#credits",
                   ref="monthly:" + time.strftime("%Y-%m", t), once=True)


def ring_added(code_id, n, why=""):
    """An admin added credits (a top-up, a request granted): the client's bell."""
    if n <= 0:
        return
    import inbox
    u = user_for_code(code_id)
    if u is None or u["status"] != "active":
        return
    inbox.emit([u["id"]], "credits_added", "%d credits added" % n, body=why or "Added by the HelloVoice team",
               href="account/#credits")


# ---------------------------------------------------------- credit requests --

def request_credits(code_id, amount, note):
    with db.connect() as conn:
        cur = conn.execute("INSERT INTO credit_requests (code_id, amount, note, at) VALUES (?,?,?,?)",
                           (code_id, amount, " ".join(str(note or "").split())[:300], db.now()))
        return cur.lastrowid


def open_credit_requests(code_id=None):
    with db.connect() as conn:
        if code_id is None:
            return conn.execute("SELECT r.*, u.email, u.company, u.id user_id FROM credit_requests r "
                                "LEFT JOIN users u ON u.code_id = r.code_id WHERE r.handled_at IS NULL ORDER BY r.id").fetchall()
        return conn.execute("SELECT * FROM credit_requests WHERE code_id = ? ORDER BY id DESC LIMIT 20", (code_id,)).fetchall()


def handle_credit_request(rid, grant_n, who):
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM credit_requests WHERE id = ? AND handled_at IS NULL", (rid,)).fetchone()
        if not r:
            return None
        conn.execute("UPDATE credit_requests SET handled_at = ?, granted = ?, handled_by = ? WHERE id = ?",
                     (db.now(), grant_n, who, rid))
    if grant_n:
        grant(r["code_id"], grant_n, "Top-up on request", actor=who, ref="request %d" % rid)
        ring_added(r["code_id"], grant_n, "Your request for more credits was granted")
    return r


# ------------------------------------------------------------- data rights --

def export(code_id):
    """Everything we hold that this client created or that is about them."""
    u = user_for_code(code_id)
    with db.connect() as conn:
        sels = [dict(r) for r in conn.execute("SELECT name, token, codes, created_at, updated_at FROM selections WHERE code_id = ?", (code_id,))]
        reqs = [dict(r) for r in conn.execute("SELECT at, name, company, email, phone, selection_name FROM requests WHERE code_id = ?", (code_id,))]
        threads = conn.execute("SELECT id FROM chat_threads WHERE code_id = ? AND scope = 'client'", (code_id,)).fetchall()
        chats = [{"role": m["role"], "text": m["content"], "at": m["at"]} for t in threads
                 for m in conn.execute("SELECT * FROM chat_messages WHERE thread_id = ? ORDER BY id", (t["id"],))]
    return {"exported_at": db.now(),
            "profile": {k: u[k] for k in ("email", "name", "company", "job_title", "phone", "created_at", "last_login_at")} if u else None,
            "credits": [dict(r) for r in ledger(code_id, 1000)],
            "briefs": [{"summary": b["summary"], "answers": json.loads(b["answers"] or "{}"), "at": b["created_at"]} for b in briefs_for(code_id, 1000)],
            "selections": sels, "quote_requests": reqs, "chat": chats}


def delete_account(uid):
    """Close the account and erase the personal data. Selections and quote requests stay as
    business records, without the person's details; the credit ledger stays for accounting."""
    u = user_by_id(uid)
    if not u:
        return False
    with db.connect() as conn:
        conn.execute("UPDATE codes SET revoked_at = COALESCE(revoked_at, ?), label = ? WHERE id = ?",
                     (db.now(), "Deleted client #%d" % uid, u["code_id"]))
        conn.execute("DELETE FROM code_devices WHERE code_id = ?", (u["code_id"],))
        conn.execute("DELETE FROM chat_messages WHERE thread_id IN (SELECT id FROM chat_threads WHERE code_id = ?)", (u["code_id"],))
        conn.execute("DELETE FROM chat_threads WHERE code_id = ?", (u["code_id"],))
        conn.execute("DELETE FROM otp WHERE email = ?", (u["email"],))
        conn.execute("UPDATE requests SET name = NULL, email = NULL, phone = NULL WHERE code_id = ?", (u["code_id"],))
        conn.execute("UPDATE briefs SET answers = json_remove(answers, '$.notes') WHERE code_id = ?", (u["code_id"],))
        conn.execute("UPDATE users SET email = ?, name = NULL, company = NULL, job_title = NULL, phone = NULL, notes = NULL, "
                     "signup_ip = NULL, status = 'suspended', deleted_at = ? WHERE id = ?",
                     ("deleted-%d@deleted.invalid" % uid, db.now(), uid))
    return True
