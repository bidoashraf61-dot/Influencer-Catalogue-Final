"""The team's "Needs you" queue on the profile (item 209, slice a, 2026-10-21).

Everything waiting on HelloVoice, oldest first inside each group, scoped like the Companies hub:
an admin sees every client, a KAM her own clients and the items handed to her.

    sign-ups waiting for approval   users.status = 'pending'                act here: Approve
    overdue next steps              campaigns.next_due before today         open the board card
    quotes without a reply          requests.handled_at IS NULL             answered in the admin
    analysis requests               gating.inbox, state open                the profile's Analyses tab
    access requests                 access_requests.status = 'pending'      answered in the admin

The "accounts in the red" group joins with the Companies CRM (item 220).
"""
import db
import kam_scope

LIMIT = 6          # rows shown per group; the count is the whole group


def _scope(role, a):
    return None if role == "admin" else (kam_scope.clients(a) or frozenset())


def _mine(scope, code_id):
    return scope is None or (code_id is not None and int(code_id) in scope)


def _today_start():
    import time
    t = time.localtime(db.now())
    return int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1)))


def _signups(conn, scope, staff):
    out = []
    for u in conn.execute("SELECT id, email, name, company, job_title, domain, code_id, created_at FROM users "
                          "WHERE status = 'pending' AND deleted_at IS NULL ORDER BY created_at"):
        if (u["domain"] or "").lower() in staff:
            continue
        # A KAM's scope is her clients' codes; a brand-new sign-up on one of her domains counts as hers too.
        if scope is not None and not _mine(scope, u["code_id"]) and (u["domain"] or "").lower() not in _kam_domains(scope):
            continue
        who = " · ".join(x for x in (u["name"], u["job_title"]) if x) or u["email"]
        out.append({"id": u["id"], "title": who, "sub": " · ".join(x for x in (u["company"], u["email"]) if x),
                    "company": u["company"] or u["domain"] or "", "domain": u["domain"] or "", "at": u["created_at"],
                    "act": "approve"})
    return out


def _kam_domains(scope):
    email = getattr(scope, "email", "") or ""
    return {d for d, m in kam_scope.domain_map().items() if (m or "").lower() == email}


def _overdue(conn, scope):
    out = []
    for k in conn.execute("SELECT id, name, token, code_id, next_step, next_due FROM campaigns "
                          "WHERE next_due IS NOT NULL AND next_due < ? AND COALESCE(next_step, '') <> '' "
                          "AND status <> 'ended' ORDER BY next_due", (_today_start(),)):
        if scope is not None and not (_mine(scope, k["code_id"]) or k["id"] in (getattr(scope, "camp_ids", None) or ())):
            continue
        out.append({"id": k["id"], "title": k["next_step"], "sub": k["name"], "token": k["token"], "at": k["next_due"],
                    "company": _company(conn, k["code_id"]), "act": "board"})
    return out


def _quotes(conn, scope):
    out = []
    for r in conn.execute("SELECT id, at, code_id, name, company, selection_name, selection FROM requests "
                          "WHERE handled_at IS NULL ORDER BY at"):
        if not _mine(scope, r["code_id"]):
            continue
        try:
            import json
            n = len(json.loads(r["selection"] or "[]"))
        except ValueError:
            n = 0
        out.append({"id": r["id"], "title": " · ".join(x for x in (r["company"] or _company(conn, r["code_id"]), r["selection_name"]) if x)
                    + (", %d creators" % n if n else ""), "sub": "Asked by " + (r["name"] or "a client"), "at": r["at"],
                    "company": r["company"] or "", "act": "admin", "href": "/requests"})
    return out


def _access(conn, scope):
    out = []
    for r in conn.execute("SELECT a.id, a.at, a.code_id, a.email, a.name, a.company, s.name sel_name, s.code_id sel_code "
                          "FROM access_requests a LEFT JOIN selections s ON s.id = a.selection_id "
                          "WHERE a.status = 'pending' ORDER BY a.at"):
        if not _mine(scope, r["sel_code"]):
            continue
        out.append({"id": r["id"], "title": (r["name"] or r["email"] or "Someone") + " asks to open " + (r["sel_name"] or "a selection"),
                    "sub": " · ".join(x for x in (r["company"], r["email"]) if x), "at": r["at"],
                    "company": r["company"] or "", "act": "admin", "href": "/access-requests"})
    return out


def _analyses(scope):
    import gating
    out = []
    for r in gating.inbox(scope):
        if r["state"] != "open":
            continue
        out.append({"id": r["id"], "title": r["creator"] + " · requested by " + (r["user"] or "a client"),
                    "sub": r["client"], "at": r["at"], "company": r["client"], "act": "analyses"})
    out.sort(key=lambda x: x["at"] or 0)
    return out


def _company(conn, code_id):
    if code_id is None:
        return ""
    u = conn.execute("SELECT company, domain FROM users WHERE code_id = ? AND deleted_at IS NULL ORDER BY id LIMIT 1", (code_id,)).fetchone()
    if u:
        return u["company"] or u["domain"] or ""
    c = conn.execute("SELECT label FROM codes WHERE id = ?", (code_id,)).fetchone()
    return (c["label"] if c else "") or ""


GROUPS = [
    ("signups", "Sign-ups waiting for approval", "They can't open the catalogue until someone approves them"),
    ("overdue", "Overdue next steps", "From the campaign board"),
    ("quotes", "Quotes without a reply", "Requested from a selection; answered in the admin"),
    ("analyses", "Analysis requests", "Approve opens the analysis for the person who asked"),
    ("access", "Access requests", "Someone asked to open a selection; answered in the admin"),
]


def queue(role, a, mine_only=False):
    """{"groups": [...], "total": n, "mine": n} for a staff viewer (role 'admin' or 'kam')."""
    import hub
    scope = _scope(role, a)
    staff = hub.staff_domains()
    with db.connect() as conn:
        found = {"signups": _signups(conn, scope, staff), "overdue": _overdue(conn, scope),
                 "quotes": _quotes(conn, scope), "access": _access(conn, scope)}
    found["analyses"] = _analyses(scope)
    groups = []
    for key, title, hint in GROUPS:
        rows = found.get(key) or []
        if rows:
            groups.append({"key": key, "title": title, "hint": hint, "count": len(rows), "items": rows[:LIMIT]})
    return {"groups": groups, "total": sum(g["count"] for g in groups), "role": role}


def kpis(role, a):
    """The "This month" strip under the queue: live campaigns, open quotes, companies, credits used."""
    import hub
    scope = _scope(role, a)
    month = db.now() - 30 * 86400
    with db.connect() as conn:
        camps = [k for k in conn.execute("SELECT id, code_id FROM campaigns WHERE status = 'live'")
                 if scope is None or _mine(scope, k["code_id"]) or k["id"] in (getattr(scope, "camp_ids", None) or ())]
        quotes = [r for r in conn.execute("SELECT code_id FROM requests WHERE handled_at IS NULL") if _mine(scope, r["code_id"])]
        used = 0
        people = set()
        for r in conn.execute("SELECT code_id, delta FROM credit_ledger WHERE delta < 0 AND at >= ?", (month,)):
            if _mine(scope, r["code_id"]):
                used -= r["delta"]
                people.add(r["code_id"])
        waiting = len(_signups(conn, scope, hub.staff_domains()))
    comp = [c for c in hub.companies(role, a)["companies"] if c.get("domain")]
    return {"live": len(camps), "quotes": len(quotes), "companies": len(comp), "waiting": waiting,
            "credits_used": used, "credit_people": len(people)}


def approve(role, a, uid):
    """Approve a waiting sign-up from the queue (admins any, a KAM her own). (ok, message)."""
    import history, hub, portal
    u = portal.user_by_id(int(uid or 0))
    if u is None or ("deleted_at" in u.keys() and u["deleted_at"]):
        return False, "That sign-up is gone."
    if u["status"] != "pending":
        return False, "Already decided."
    scope = _scope(role, a)
    with db.connect() as conn:
        mine = any(x["id"] == u["id"] for x in _signups(conn, scope, hub.staff_domains()))
    if not mine:
        return False, "Not one of your clients."
    history.set_actor(a["email"])
    with history.tracked("user", u["id"], "Approved " + (u["email"] or "a sign-up")):
        portal.set_status(u["id"], "active")
    return True, (u["name"] or u["email"]) + " can sign in now."
