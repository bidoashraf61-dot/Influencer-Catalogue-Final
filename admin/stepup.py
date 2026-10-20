"""Step-up for sensitive profile actions (item 209, 2026-10-21): suspend an account, change credits,
push to many people. The team member asks for a fresh 6-digit code by email; a right code opens a
10-minute window for that person only. Codes reuse the sign-in code table under a "stepup:" key, so
a step-up code can never sign anyone in, and a sign-in code can never step anyone up.

    stepup.send(user)          -> (ok, reason)       reason: wait | mail
    stepup.verify(user, code)  -> (ok, reason)       reason: invalid | expired | locked
    stepup.active(user)        -> seconds left, 0 when closed
"""
import db
import portal

WINDOW = 10 * 60

SCHEMA = """
CREATE TABLE IF NOT EXISTS stepup_grants (
    user_id INTEGER PRIMARY KEY, until INTEGER NOT NULL, at INTEGER NOT NULL
);
"""
_ready = False


def _init():
    global _ready
    if not _ready:
        with db.connect() as conn:
            conn.executescript(SCHEMA)
        _ready = True


def _key(user):
    return "stepup:" + (user["email"] or "").lower()


def send(user, ip=None):
    import mailer
    code, why = portal.new_otp(_key(user), ip)
    if why:
        return False, why
    try:
        mailer.send(user["email"], "Your HELVi Connect confirmation code",
                    "Your confirmation code is %s.\n\nIt works for %d minutes and confirms one sensitive change "
                    "on the HELVi Connect profile (suspending an account, changing credits or a large push).\n\n"
                    "If you did not ask for it, ignore this email and tell the owner." % (code, portal.OTP_MINUTES))
    except Exception:  # noqa: BLE001 - any mail failure is the same answer for the person
        return False, "mail"
    _log(user, "stepup_sent")
    return True, None


def verify(user, code):
    _init()
    ok, why = portal.check_otp(_key(user), code)
    if not ok:
        _log(user, "stepup_failed")
        return False, why
    now = db.now()
    with db.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO stepup_grants (user_id, until, at) VALUES (?,?,?)", (user["id"], now + WINDOW, now))
    _log(user, "stepup_ok")
    return True, None


def active(user):
    _init()
    if user is None:
        return 0
    with db.connect() as conn:
        r = conn.execute("SELECT until FROM stepup_grants WHERE user_id = ?", (user["id"],)).fetchone()
    return max(0, (r["until"] - db.now())) if r else 0


def _log(user, event):
    """Into the admin's security log (team.py), when it is there."""
    try:
        import team
        team.log(event, user["email"], "profile")
    except Exception:  # noqa: BLE001 - the log is a record, never a reason to fail the action
        pass
