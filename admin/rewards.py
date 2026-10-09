"""Credits a client earns: finishing their profile, and bringing a colleague.

Profile (30 credits in all, once per account, never for a blank value):
    photo +2 · job title +2 · phone +3 · company logo +3 · brands +5 ·
    industry and markets +5 · everything filled +10
Invite a colleague: +20 to the inviter when the colleague's account is active and
they sign in for the first time. Same company email domain, at most 5 paid
invites per account, and an address is only ever paid for once.

The onboarding tour (phase C): +5 once, the first time an account finishes it.

Every reward is a credit-ledger line whose reason names the step and whose ref
("reward:<step>", "invite:<user id>") is what makes it once-only.
"""
import hashlib
import hmac
import json

import db
import portal

STEPS = [  # key, credits, label
    ("photo", 2, "Add your photo"),
    ("job_title", 2, "Add your job title"),
    ("phone", 3, "Add your phone number"),
    ("logo", 3, "Add your company logo"),
    ("brands", 5, "Add your brands and products"),
    ("industry_markets", 5, "Add your industry and markets"),
]
BONUS = 10
INVITE_CREDITS = 20
INVITE_MAX = 5
# What completion counts: the three from sign-up plus the seven above.
FIELDS = ("name", "email", "company", "photo", "job_title", "phone", "logo", "brands", "industry", "markets")

SCHEMA = """
CREATE TABLE IF NOT EXISTS invites (
    id INTEGER PRIMARY KEY,
    inviter_id INTEGER NOT NULL,         -- users.id
    email TEXT,                          -- who was invited (normalised), when known
    name TEXT,
    via TEXT NOT NULL DEFAULT 'form',    -- form | link
    at INTEGER NOT NULL,
    joined_id INTEGER,                   -- users.id of the colleague once they exist
    rewarded_at INTEGER
);
CREATE INDEX IF NOT EXISTS invites_email ON invites(email);
"""


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        for col in ("brands", "industry", "markets", "language", "tour"):
            if col not in cols:
                conn.execute("ALTER TABLE users ADD COLUMN %s TEXT" % col)


def _v(user, key):
    v = user[key] if key in user.keys() else None
    if key == "markets":
        try:
            v = [x for x in json.loads(v or "[]") if x]
        except ValueError:
            v = []
    return v if (v and (not isinstance(v, str) or v.strip())) else None


def filled(user):
    return {f: bool(_v(user, f)) for f in FIELDS}


def done(user, step):
    if step == "industry_markets":
        return bool(_v(user, "industry")) and bool(_v(user, "markets"))
    return bool(_v(user, step))


def _paid(conn, code_id, ref):
    return conn.execute("SELECT 1 FROM credit_ledger WHERE code_id = ? AND ref = ? AND delta > 0 LIMIT 1",
                        (code_id, ref)).fetchone() is not None


def completion(user):
    """Percent complete over the ten fields, and every step with its reward and state."""
    f = filled(user)
    with db.connect() as conn:
        paid = {r["ref"] for r in conn.execute("SELECT ref FROM credit_ledger WHERE code_id = ? AND ref LIKE 'reward:%' AND delta > 0",
                                               (user["code_id"],))}
    steps = [{"key": k, "credits": n, "label": label, "done": done(user, k), "paid": ("reward:" + k) in paid}
             for k, n, label in STEPS]
    pct = int(round(sum(f.values()) * 100.0 / len(FIELDS)))
    waiting = sum(s["credits"] for s in steps if not s["paid"]) + (0 if "reward:complete" in paid else BONUS)
    return {"pct": pct, "steps": steps, "bonus": BONUS, "bonus_paid": "reward:complete" in paid,
            "waiting": waiting, "fields": f,
            "missing": [{"key": s["key"], "label": s["label"]} for s in steps if not s["done"]]}


def check(user):
    """Pay every step this account has just completed and not been paid for. Returns
    [{key, credits, label}] for what was paid now (the page celebrates those)."""
    if user is None or user["status"] != "active" or not user["code_id"]:
        return []
    out = []
    todo = [(k, n, label) for k, n, label in STEPS if done(user, k)]
    if all(filled(user).values()):
        todo.append(("complete", BONUS, "Profile 100% complete"))
    for key, n, label in todo:
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if _paid(conn, user["code_id"], "reward:" + key):
                continue
            portal._post(conn, user["code_id"], n, "Profile reward: " + label, "reward:" + key, "system")
        out.append({"key": key, "credits": n, "label": label})
    return out


# --------------------------------------------------------------------- tour --
# The 3-minute tour Helvy offers after the first sign-in. The state is only what the
# page needs to decide whether to offer it again: None (never shown), "offered",
# "later", "started" or "done". The +5 is paid once per account, enforced by the
# ledger ref, however many times the tour is replayed.

TOUR_CREDITS = 5
TOUR_STATES = ("offered", "later", "started", "done")


def tour_state(user):
    return (user["tour"] if user is not None and "tour" in user.keys() else None) or None


def set_tour(user, state):
    if state not in TOUR_STATES or user is None:
        return tour_state(user)
    cur = tour_state(user)
    if cur == "done" and state != "done":
        return cur                                   # a replay never un-finishes it
    with db.connect() as conn:
        conn.execute("UPDATE users SET tour = ? WHERE id = ?", (state, user["id"]))
    return state


def tour_finished(user):
    """Mark the tour done and pay +5 the first time. Returns the credits paid now (0 or 5)."""
    if user is None or user["status"] != "active" or not user["code_id"]:
        return 0
    set_tour(user, "done")
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if _paid(conn, user["code_id"], "reward:tour"):
            return 0
        portal._post(conn, user["code_id"], TOUR_CREDITS, "Tour reward: finished the HELVY Connect tour", "reward:tour", "system")
    return TOUR_CREDITS


# ------------------------------------------------------------------ invites --

def link_token(uid, secret):
    sig = hmac.new(secret, ("invite:%d" % uid).encode(), hashlib.sha256).hexdigest()[:10]
    return "%d.%s" % (uid, sig)


def read_token(tok, secret):
    try:
        uid, sig = str(tok or "").split(".", 1)
        uid = int(uid)
    except ValueError:
        return None
    return uid if hmac.compare_digest(link_token(uid, secret), "%d.%s" % (uid, sig)) else None


def _domain(email):
    return str(email or "").rsplit("@", 1)[-1].lower()


def record(inviter, email, name="", via="form"):
    """Note that ``inviter`` invited ``email``. Only a colleague on the same company domain counts."""
    email = str(email or "").strip().lower()
    if not inviter or "@" not in email or _domain(email) != _domain(inviter["email"]) or email == inviter["email"]:
        return False
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM invites WHERE inviter_id = ? AND email = ?", (inviter["id"], email)).fetchone():
            return True
        conn.execute("INSERT INTO invites (inviter_id, email, name, via, at) VALUES (?,?,?,?,?)",
                     (inviter["id"], email, " ".join(str(name or "").split())[:120], via, db.now()))
    return True


def paid_count(inviter_id):
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM invites WHERE inviter_id = ? AND rewarded_at IS NOT NULL",
                            (inviter_id,)).fetchone()[0]


def summary(user, secret):
    with db.connect() as conn:
        rows = conn.execute("SELECT i.*, u.name joined_name FROM invites i LEFT JOIN users u ON u.id = i.joined_id "
                            "WHERE i.inviter_id = ? ORDER BY i.at DESC LIMIT 20", (user["id"],)).fetchall()
    paid = sum(1 for r in rows if r["rewarded_at"])
    return {"token": link_token(user["id"], secret), "credits": INVITE_CREDITS, "max": INVITE_MAX,
            "paid": paid, "left": max(0, INVITE_MAX - paid_count(user["id"])),
            "list": [{"email": r["email"], "name": r["joined_name"] or r["name"] or "", "joined": bool(r["joined_id"]),
                      "rewarded": bool(r["rewarded_at"]), "at": r["at"]} for r in rows]}


def first_sign_in(user):
    """The colleague is in for the first time: pay whoever invited them (once, if
    the rules allow) and tell their team. Returns the inviter row paid, or None."""
    import inbox
    email = user["email"]
    paid_inviter = None
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM invites WHERE email = ? ORDER BY at", (email,)).fetchall()
        ever = conn.execute("SELECT 1 FROM invites WHERE email = ? AND rewarded_at IS NOT NULL", (email,)).fetchone()
        conn.execute("UPDATE invites SET joined_id = ? WHERE email = ? AND joined_id IS NULL", (user["id"], email))
    if rows and not ever:
        for r in rows:
            inv = portal.user_by_id(r["inviter_id"])
            if inv is None or inv["status"] != "active" or inv["deleted_at"] or _domain(inv["email"]) != _domain(email):
                continue
            if paid_count(inv["id"]) >= INVITE_MAX:
                continue
            with db.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if _paid(conn, inv["code_id"], "invite:%d" % user["id"]):
                    break
                portal._post(conn, inv["code_id"], INVITE_CREDITS, "Invite reward: %s joined" % (user["name"] or email),
                             "invite:%d" % user["id"], "system")
                conn.execute("UPDATE invites SET rewarded_at = ? WHERE id = ?", (db.now(), r["id"]))
            paid_inviter = inv
            break
    team = inbox.for_codes([user["code_id"]], exclude_user=user["id"])
    if paid_inviter is not None and paid_inviter["id"] not in team:
        team.append(paid_inviter["id"])
    who = user["name"] or email
    for uid in team:
        body = ("You earned %d credits for the invite" % INVITE_CREDITS) if paid_inviter and uid == paid_inviter["id"] \
            else "You now see each other's selections"
        inbox.emit([uid], "colleague", "%s joined your team" % who, body=body, href="account/#account",
                   ref="joined:%d" % user["id"], once=True)
    return paid_inviter
