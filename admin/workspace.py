"""The client workspace: one company, its modules, and the people in it.

A **company** (tenant) is the `codes` row the root account signs in against. People who join it
are `users` rows with `company_code_id` set; everyone else has it NULL and is their own company.
So `tenant = COALESCE(company_code_id, code_id)`, and every limit, level and object that already
hangs off `code_id` keeps working for the company without a change.

    user_modules   one row per person per module: none | viewer | editor | admin
    module_requests  a person asks for a role (answered by the company's admin) or the company
                     asks for a module (answered by HelloVoice). `access_requests` is taken by
                     selection access, hence the name.

Effective access in a module = the lower of the company's level for it and the person's role:
`off` is nothing for everyone, `view` caps at viewer, `manage` leaves the role as it is. The root
account of a company is admin in every module the company has.
"""
import json
import secrets

import db
import modules
import portal

ROLES = ("none", "viewer", "editor", "admin")
RANK = {r: i for i, r in enumerate(ROLES)}
ROLE_HELP = {
    "none": "No access to this module.",
    "viewer": "Reads everything in the module.",
    "editor": "Adds and changes inside the module's limits.",
    "admin": "Also invites people and sets their roles in this module.",
}


MODS = [
    {"key": "helvi-selection", "name": "Helvi Selection", "short": "Selection",
     "what": "Browse the HelloVoice creator roster, build selections and shortlists, and request quotes.",
     "logo": None},
    {"key": "helvi-track", "name": "Helvi Track", "short": "Track",
     "what": "Track a campaign: posts, tracking links, insights and what people said.",
     "logo": "/assets/brand/modules/helvi-track-480.png"},
    {"key": "helvi-intelligence", "name": "Helvi Intelligence", "short": "Intelligence",
     "what": "Competitor evidence: which creators competitors used and how those posts did.",
     "logo": "/assets/brand/modules/helvi-intelligence-480.png"},
]
BY_KEY = {m["key"]: m for m in MODS}

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_modules (
    user_id    INTEGER NOT NULL,
    code_id    INTEGER NOT NULL,          -- the company
    module     TEXT NOT NULL,
    role       TEXT NOT NULL,             -- none | viewer | editor | admin
    changed_at INTEGER,
    changed_by TEXT,
    PRIMARY KEY (user_id, module)
);

CREATE TABLE IF NOT EXISTS workspace_prefs (
    code_id INTEGER NOT NULL,
    module  TEXT NOT NULL,                -- a module key, or "*" for the whole company
    key     TEXT NOT NULL,
    value   TEXT,
    PRIMARY KEY (code_id, module, key)
);
"""
PREFS = {"default_role": ("viewer", "editor"), "digest": ("on", "off"),
         # What the company's campaign reports may show (Helvi Track). Off hides it on every report of the
         # company; on leaves each campaign's own switch in charge (metrics.visibility).
         "show_clicks": ("on", "off"), "show_emv": ("on", "off"), "show_audience": ("on", "off"),
         "show_all_content": ("on", "off")}
REPORT_SHOWS = [("show_clicks", "clicks", "Clicks on tracking links"), ("show_emv", "emv", "Earned media value"),
                ("show_audience", "audience", "What people said"), ("show_all_content", "all_content", "Every post, not only the top ones")]


def report_hidden(tenant):
    """The report sections this company switched off: a set of metrics.visibility keys."""
    if not tenant:
        return set()
    try:
        with _c() as conn:
            rows = conn.execute("SELECT key FROM workspace_prefs WHERE code_id = ? AND module = 'helvi-track' "
                                "AND key LIKE 'show_%' AND value = 'off'", (int(tenant),)).fetchall()
    except Exception:
        return set()
    by = {k: v for k, v, _ in REPORT_SHOWS}
    return {by[r["key"]] for r in rows if r["key"] in by}
_ready = False


def init():
    global _ready
    with db.connect() as conn:
        um = {r["name"]: r["pk"] for r in conn.execute("PRAGMA table_info(user_modules)")}
        if um and "changed_at" not in um:
            # An early 4-column table (no key, no stamps) went live on 28 Oct: move it to the spec's shape,
            # rows kept, the newest row winning where a person had two for one module.
            conn.executescript("ALTER TABLE user_modules RENAME TO user_modules_v0;")
            conn.executescript(SCHEMA)
            conn.execute("INSERT OR REPLACE INTO user_modules (user_id, code_id, module, role) "
                         "SELECT user_id, code_id, module, role FROM user_modules_v0 ORDER BY rowid")
            conn.execute("DROP TABLE user_modules_v0")
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        if "company_code_id" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN company_code_id INTEGER")
    import tenant_requests
    with tenant_requests._conn():             # module_requests is theirs; make sure it exists before we read it
        pass
    _ready = True


def _c():
    if not _ready:
        init()
    return db.connect()


# ------------------------------------------------------------- who and what --

def tenant_of(user):
    return user["company_code_id"] if "company_code_id" in user.keys() and user["company_code_id"] else user["code_id"]


def is_root(user):
    return tenant_of(user) == user["code_id"]


def level(tenant, key):
    """The company's level for a module. Selection is not in the registry until the gate split lands."""
    return modules.level(tenant, key) if key in modules.BY_KEY else modules.DEFAULT


def role_of(user, key):
    """The person's own role, before the company's level caps it."""
    if is_root(user):
        return "admin"
    with _c() as conn:
        r = conn.execute("SELECT role FROM user_modules WHERE user_id = ? AND module = ?", (user["id"], key)).fetchone()
    return r["role"] if r and r["role"] in RANK else "none"


def effective(user, key):
    """Off is nothing for everyone. At `view` an editor reads only; an admin stays admin, because
    managing the company's own people is platform, not module data. Data writes are still refused
    below `manage` by tenant_api, whatever the role."""
    lvl = level(tenant_of(user), key)
    mine = role_of(user, key)
    if lvl == "off":
        return "none"
    if lvl == "view" and mine == "editor":
        return "viewer"
    return mine


def _users(tenant):
    with _c() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE (code_id = ? OR company_code_id = ?) AND deleted_at IS NULL "
            "ORDER BY (code_id = ?) DESC, created_at", (tenant, tenant, tenant)).fetchall()


def seats(tenant):
    used = sum(1 for u in _users(tenant) if u["status"] == "active")
    return used, modules.number(tenant, "seats")


def pref(tenant, key, module="*", default=None):
    with _c() as conn:
        r = conn.execute("SELECT value FROM workspace_prefs WHERE code_id = ? AND module = ? AND key = ?",
                         (tenant, module, key)).fetchone()
    return r["value"] if r else default


def set_pref(tenant, key, value, module="*"):
    if key not in PREFS or value not in PREFS[key]:
        return False
    with _c() as conn:
        conn.execute("INSERT INTO workspace_prefs (code_id, module, key, value) VALUES (?,?,?,?) "
                     "ON CONFLICT(code_id, module, key) DO UPDATE SET value = excluded.value",
                     (tenant, module, key, value))
    return True


# ------------------------------------------------------------------- people --

def people(tenant):
    out = []
    for u in _users(tenant):
        roles = {m["key"]: role_of(u, m["key"]) for m in MODS}
        out.append({"id": u["id"], "name": u["name"] or "", "email": u["email"], "owner": is_root(u),
                    "status": u["status"], "last_login": u["last_login_at"], "roles": roles})
    return out


def _may_admin(actor, key):
    return effective(actor, key) == "admin"


def invites_open(tenant):
    """Inviting colleagues waits until a colleague sees the company's data everywhere (the gate session's work).
    Setting `workspace_invites`: "all" opens it for everyone; otherwise a list of company code ids may invite."""
    v = db.setting("workspace_invites", [55])          # 55 = the QA company
    return v == "all" or (isinstance(v, list) and int(tenant) in [int(x) for x in v if str(x).isdigit()])


def invite(actor, email, name, roles):
    """(ok, message). The actor must be admin of every module they hand out."""
    tenant = tenant_of(actor)
    if not invites_open(tenant):
        return False, "Inviting colleagues opens soon. Until then your account manager can add them for you."
    roles = {k: r for k, r in (roles or {}).items() if k in BY_KEY and r in RANK and r != "none"}
    if not roles:
        return False, "Pick a role in at least one module."
    for k in roles:
        if not _may_admin(actor, k):
            return False, "You are not an admin of %s." % BY_KEY[k]["name"]
        if level(tenant, k) == "off":
            return False, "%s is not part of your account." % BY_KEY[k]["name"]
    email, why = portal.check_email(email)
    if why:
        return False, "That email cannot be used (%s)." % why
    used, cap = seats(tenant)
    if cap is not None and used >= cap:
        return False, "All %d seats are in use. Request more seats." % cap
    if portal.user_by_email(email):
        return False, "That person already has an HELVi account."
    u = portal.create_user(email, name, actor["company"] or "", ip=None)
    with _c() as conn:
        conn.execute("UPDATE users SET company_code_id = ?, kam = ? WHERE id = ?",
                     (tenant, actor["kam"] if "kam" in actor.keys() else None, u["id"]))
        for m in MODS:      # a row for every module, so "no row" never has to mean anything
            _write_role(conn, u["id"], tenant, m["key"], roles.get(m["key"], "none"), actor["email"])
    _history("invite", tenant, email, actor, None, roles)
    try:
        import mailer
        if mailer.configured():
            mailer.send(email, "%s invited you to HELVi Connect" % (actor["name"] or actor["email"]),
                        "%s added you to their HELVi Connect workspace.\n\nSign in with this email: https://influencer-catalogue.hellovoice.co.uk/workspace/\n"
                        "You will get a one-time code by email." % (actor["name"] or actor["email"]))
    except Exception:
        pass
    return True, "Invited. They sign in with a one-time code sent to %s." % email


def set_role(actor, user_id, key, role):
    tenant = tenant_of(actor)
    if key not in BY_KEY or role not in RANK:
        return False, "Unknown module or role."
    if not _may_admin(actor, key):
        return False, "Only a %s admin can change roles." % BY_KEY[key]["name"]
    t = portal.user_by_id(int(user_id)) if str(user_id).isdigit() else None
    if t is None or tenant_of(t) != tenant:
        return False, "That person is not on your account."
    if is_root(t):
        return False, "The account owner is always admin."
    if t["id"] == actor["id"] and RANK[role] < RANK["admin"] and _admins(tenant, key) <= 1:
        return False, "Keep at least one admin."
    before = role_of(t, key)
    with _c() as conn:
        _write_role(conn, t["id"], tenant, key, role, actor["email"])
    _history("role", tenant, t["email"], actor, {key: before}, {key: role})
    return True, "Saved."


def _write_role(conn, user_id, tenant, key, role, by=""):
    """Delete + insert, so it works whichever session's write reached the row first."""
    conn.execute("DELETE FROM user_modules WHERE user_id = ? AND module = ?", (int(user_id), key))
    conn.execute("INSERT INTO user_modules (user_id, code_id, module, role, changed_at, changed_by) VALUES (?,?,?,?,?,?)",
                 (int(user_id), int(tenant), key, role, db.now(), by or ""))


def _admins(tenant, key):
    return 1 + sum(1 for p in people(tenant) if not p["owner"] and p["status"] == "active" and p["roles"][key] == "admin")


def remove(actor, user_id):
    tenant = tenant_of(actor)
    t = portal.user_by_id(int(user_id)) if str(user_id).isdigit() else None
    if t is None or tenant_of(t) != tenant or is_root(t):
        return False, "That person cannot be removed."
    if not any(_may_admin(actor, m["key"]) for m in MODS):
        return False, "Only an admin can remove people."
    with _c() as conn:
        conn.execute("DELETE FROM user_modules WHERE user_id = ?", (t["id"],))
    portal.set_status(t["id"], "suspended")
    _history("remove", tenant, t["email"], actor, "active", "removed")
    return True, "Removed. Their seat is free."


# ----------------------------------------------------------------- requests --

def request(user, key, kind, note="", level=None, limit=None):
    """kind: role (answered by the company's admin), module or limit (answered by HelloVoice in the
    Tenants inbox). Filed through the same columns tenant_requests.file_request writes."""
    tenant = tenant_of(user)
    if key not in BY_KEY or kind not in ("role", "module", "limit"):
        return False, "Unknown request."
    note = " ".join(str(note or "").split())[:300]
    detail = {"module": key}
    if kind == "role":
        detail.update(role="viewer", user_id=user["id"])
    elif kind == "limit":
        key_ = str(limit or "")
        if key_ in modules.FIELDS:
            detail = {"key": key_}             # HelloVoice types the new value when approving
    elif kind == "module":
        # "Ask to manage your own" asks for manage; a locked module asks to have it at all (view).
        detail.update(level=level if level in ("view", "manage") else "view")
    import tenant_requests
    with _c() as conn:
        dup = conn.execute("SELECT 1 FROM module_requests WHERE code_id = ? AND user_id = ? AND module = ? AND kind = ? "
                           "AND status = 'pending'", (tenant, user["id"], key, kind)).fetchone() \
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'module_requests'").fetchone() else None
    if dup:
        return True, "Already requested. You will hear back."
    tenant_requests.file_request(tenant, user["id"], key, kind, note, detail)
    if kind != "role":
        try:
            import notify
            notify.send("signup", ["%s (%s) asked HelloVoice for %s: %s%s." % (
                user["name"] or user["email"], user["company"] or "no company", BY_KEY[key]["name"],
                {"module": "access to the module", "limit": "more capacity"}[kind], (" - " + note) if note else "")],
                kam=user["kam"] if "kam" in user.keys() else None)
        except Exception:
            pass
        return True, "Sent to HelloVoice. Your account manager will come back to you."
    return True, "Sent to your account admin."


def pending_roles(actor):
    """Role requests the actor may answer."""
    tenant = tenant_of(actor)
    out = []
    with _c() as conn:
        for r in conn.execute("SELECT * FROM module_requests WHERE code_id = ? AND kind = 'role' AND status = 'pending' "
                              "ORDER BY created_at", (tenant,)):
            if _may_admin(actor, r["module"]):
                u = portal.user_by_id(r["user_id"])
                out.append({"id": r["id"], "module": r["module"], "name": (u["name"] or u["email"]) if u else "?",
                            "email": u["email"] if u else "", "note": r["note"], "at": r["created_at"]})
    return out


def decide(actor, rid, approve):
    tenant = tenant_of(actor)
    with _c() as conn:
        r = conn.execute("SELECT * FROM module_requests WHERE id = ? AND code_id = ? AND kind = 'role' AND status = 'pending'",
                         (int(rid), tenant)).fetchone()
    if r is None or not _may_admin(actor, r["module"]):
        return False, "Not found."
    if approve:
        ok, msg = set_role(actor, r["user_id"], r["module"], pref(tenant, "default_role", r["module"], "viewer"))
        if not ok:
            return False, msg
    with _c() as conn:
        conn.execute("UPDATE module_requests SET status = ?, decided_by = ?, decided_at = ? WHERE id = ?",
                     ("approved" if approve else "declined", actor["email"], db.now(), r["id"]))
    return True, "Done."


def _history(action, tenant, who, actor, before, after):
    try:
        import history
        history.record("workspace_" + action, "workspace", tenant, who, before, after)
    except Exception:
        pass


# ------------------------------------------------------------------ payload --

LIMIT_OF = {"Seats": "seats", "Campaigns": "campaigns_max", "Selections": "selections_max",
            "Collections today": "captures_day", "Collection spend this month": "spend_month", "AI credits": "credits_month"}


def _meter(label, used, cap, unit=""):
    # `key` names the Tenants limit a "Request more" on this meter asks to raise.
    return {"label": label, "used": used, "cap": cap, "unit": unit, "key": LIMIT_OF.get(label)}


def _overview(tenant, user, key):
    """(meters, checklist, outputs) for one module. Counts only; nothing of another company."""
    used, cap = seats(tenant)
    meters = [_meter("Seats", used, cap)]
    checklist, outputs = [], []
    with _c() as conn:
        if key == "helvi-track":
            camps = conn.execute("SELECT token, name, client, status, starts_at, ends_at FROM campaigns WHERE code_id = ? "
                                 "ORDER BY updated_at DESC LIMIT 6", (tenant,)).fetchall()
            n = modules.count(tenant, "campaigns")
            posts = conn.execute("SELECT COUNT(*) n FROM content WHERE campaign_id IN (SELECT id FROM campaigns WHERE code_id = ?)",
                                 (tenant,)).fetchone()["n"]
            meters.append(_meter("Campaigns", n, modules.number(tenant, "campaigns_max")))
            outputs = [{"title": c["name"], "sub": (c["client"] or "") + " · " + c["status"],
                        "href": "/campaign/dashboard/?t=" + c["token"]} for c in camps]
            checklist = [("Start a campaign", n > 0), ("Get posts tracked", posts > 0), ("Invite your team", used > 1)]
        elif key == "helvi-intelligence":
            import competitors
            comps = competitors.listing(tenant)
            meters.append(_meter("Competitors", len(comps), 40))
            # The two caps a collection is refused on (tenant_api.collect), shown before they bite.
            try:
                meters.append(_meter("Collections today", competitors.runs_today(tenant), modules.number(tenant, "captures_day")))
                meters.append(_meter("Collection spend this month", round(competitors.spend_month(tenant), 2),
                                     modules.number(tenant, "spend_month"), "$"))
            except Exception:
                pass
            outputs = [{"title": c.get("name", ""), "sub": ("Last run " + str(c["last_run_at"])) if c.get("last_run_at") else "Not collected yet",
                        "href": ""} for c in comps[:6]]
            checklist = [("Name a competitor", len(comps) > 0), ("Run a first collection", any(c.get("last_run_at") for c in comps)),
                         ("Invite your team", used > 1)]
        else:
            sels = conn.execute("SELECT name, token, updated_at FROM selections WHERE code_id = ? AND archived_at IS NULL "
                                "ORDER BY updated_at DESC LIMIT 6", (tenant,)).fetchall()
            n = modules.count(tenant, "selections")
            meters.append(_meter("Selections", n, modules.number(tenant, "selections_max")))
            outputs = [{"title": s["name"] or "Selection", "sub": "Selection", "href": "/selection/?s=" + s["token"],
                        "token": s["token"]} for s in sels]
            checklist = [("Open the roster", True), ("Make a selection", n > 0), ("Invite your team", used > 1)]
    try:
        meters.append(_meter("AI credits", portal.balance(tenant) or 0, None))
    except Exception:
        pass
    return meters, [{"label": a, "done": bool(b)} for a, b in checklist], outputs


def payload(user, key=None):
    tenant = tenant_of(user)
    mods = []
    for m in MODS:
        lvl = level(tenant, m["key"])
        eff = effective(user, m["key"])
        # Until the gate split lands, "off" is the only way a company does not own a module.
        paused = lvl == "off" and hasattr(modules, "paused") and modules.paused(tenant, m["key"])
        state = ("paused" if paused else "locked") if lvl == "off" else ("norole" if eff == "none" else "open")
        mods.append({"key": m["key"], "name": m["name"], "short": m["short"], "what": m["what"], "logo": m["logo"],
                     "state": state, "level": lvl, "role": eff})
    first = next((m["key"] for m in mods if m["state"] == "open"), mods[0]["key"])
    key = key if key in BY_KEY else first
    cur = next(m for m in mods if m["key"] == key)
    out = {"ok": True, "me": {"id": user["id"], "name": user["name"] or "", "email": user["email"], "owner": is_root(user)},
           "company": user["company"] or "", "modules": mods, "current": key, "module": cur}
    if cur["state"] == "open":
        meters, checklist, outputs = _overview(tenant, user, key)
        out["overview"] = {"meters": meters, "checklist": checklist, "outputs": outputs}
        out["settings"] = {"default_role": pref(tenant, "default_role", key, "viewer"), "digest": pref(tenant, "digest", key, "on"),
                           "report": [{"key": k, "label": label, "value": pref(tenant, k, key, "on")} for k, _, label in REPORT_SHOWS]
                           if key == "helvi-track" else [],
                           "brand_name": modules.value(tenant, "brand_name", ""), "brand_colour": modules.value(tenant, "brand_colour", "")}
        out["limits"] = [{"key": f["key"], "label": f["label"], "value": modules.number(tenant, f["key"])}
                         for f in modules.LIMITS if f["key"] in ("seats", "campaigns_max", "selections_max", "spend_month", "credits_month")]
        if cur["role"] == "admin":
            out["team"] = {"invites": invites_open(tenant), "people": people(tenant), "pending": pending_roles(user), "seats": list(seats(tenant)),
                           "roles": [{"key": r, "help": ROLE_HELP[r]} for r in ROLES],
                           "modules": [{"key": m["key"], "name": m["short"], "on": level(tenant, m["key"]) != "off"} for m in MODS]}
    return out

