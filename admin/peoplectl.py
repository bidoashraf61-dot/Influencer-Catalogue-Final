"""Account controls on the profile's company page (item 209, slice b, 2026-10-21): approve, hold, reactivate,
suspend and change credits for a client's people, with the same logic as the admin's Client accounts page
(portal.set_status / portal.grant) and the same History + undo.

    who          approve / hold / reactivate        suspend / credits
    admin        any client                         any client, after a step-up code
    KAM          her own clients' people            not allowed (admin-only)

A held account is 'pending' with held_at set; a waiting sign-up is 'pending' without it. Only waiting
sign-ups are in the "Needs you" queue.
"""
import db

CREDIT_MAX = 1000
_ready = False


def ensure():
    global _ready
    if _ready:
        return
    with db.connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        if "held_at" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN held_at INTEGER")
    _ready = True


def state(u):
    """waiting | active | held | suspended for a users row."""
    ensure()
    s = u["status"]
    if s == "suspended":
        return "suspended"
    if s == "pending":
        return "held" if ("held_at" in u.keys() and u["held_at"]) else "waiting"
    return "active"


def allowed(role, a, u):
    """The actions this viewer may take on this person right now (for the buttons)."""
    st = state(u)
    out = []
    if st == "waiting":
        out += ["approve", "hold"]
    elif st == "held":
        out += ["reactivate"]
    elif st == "suspended":
        if role == "admin":
            out += ["reactivate"]
    elif st == "active":
        out += ["hold"]
    if role == "admin":
        if st in ("active", "held", "waiting"):
            out.append("suspend")
        out.append("credits")
    return out


def _mine(role, a, uid):
    import hub
    rows, scoped = hub._users(role, a)
    if scoped is None:
        return any(r["id"] == uid for r in rows)
    return any(r["id"] == uid for r in scoped[1])


def act(role, a, actor_user, uid, action, amount=None, reason="", stepup_open=False):
    """(status code, {ok, message, ...}). ``stepup_open`` = the actor's code window is open."""
    import history, portal
    ensure()
    u = portal.user_by_id(int(uid or 0))
    if u is None or ("deleted_at" in u.keys() and u["deleted_at"]):
        return 404, {"ok": False, "message": "That account is gone."}
    import hub
    if (u["domain"] or "").lower() in hub.staff_domains():
        return 400, {"ok": False, "message": "Team accounts are managed in People and access."}
    if not _mine(role, a, u["id"]):
        return 403, {"ok": False, "message": "Not one of your clients."}
    if action not in allowed(role, a, u):
        return 403 if action in ("suspend", "credits") and role != "admin" else 400, \
            {"ok": False, "message": "That is not available for this account right now." if role == "admin"
             else "Only an administrator can do that."}
    who = u["name"] or u["email"]
    history.set_actor(a["email"])
    if action in ("suspend", "credits") and not stepup_open:
        return 403, {"ok": False, "reason": "stepup", "message": "Confirm with an emailed code first."}
    if action == "credits":
        try:
            n = int(amount)
        except (TypeError, ValueError):
            n = 0
        if n == 0 or abs(n) > CREDIT_MAX:
            return 400, {"ok": False, "message": "Enter a number between 1 and %d, plus or minus." % CREDIT_MAX}
        why = (str(reason or "") or "Admin adjustment")[:100]
        bal = portal.grant(u["code_id"], n, why, actor=a["email"])
        if n > 0:
            portal.ring_added(u["code_id"], n)
        _log_credit(u, n, bal, a["email"])
        return 200, {"ok": True, "message": "%s now has %d credits." % (who, bal), "credits": bal}
    new = {"approve": "active", "reactivate": "active", "hold": "pending", "suspend": "suspended"}[action]
    label = {"approve": "Approved ", "reactivate": "Reactivated ", "hold": "Put on hold ", "suspend": "Suspended "}[action] + (u["email"] or who)
    with history.tracked("user", u["id"], label):
        portal.set_status(u["id"], new)
        with db.connect() as conn:
            conn.execute("UPDATE users SET held_at = ? WHERE id = ?", (db.now() if action == "hold" else None, u["id"]))
    msg = {"approve": "%s can sign in now.", "reactivate": "%s can sign in again.", "hold": "%s is on hold.",
           "suspend": "%s is suspended and signed out."}[action] % who
    return 200, {"ok": True, "message": msg, "state": state(portal.user_by_id(u["id"]))}


def _log_credit(u, n, bal, who):
    try:
        import team
        team.log("credits_changed", who, "%s %+d -> %d" % (u["email"], n, bal))
    except Exception:  # noqa: BLE001
        pass
