"""The admin control hub on the profile (owner, 2026-10-18, programme item 129, phase 1).

A signed-in account whose email is an owner or admin login of the admin sees every company; a key
account manager sees her own (kam_scope). Each company opens to its people, and each person to their
selections and campaigns. From any row: open it, copy its link, set its KAM, share it with a client's
email. Moving an item to another client is phase 2.

    viewer(user)                       ("admin" | "kam" | None, admin row)
    companies(role, a)                 the light list: one row per company
    company(role, a, key)              one company's people with their selections and campaigns
    set_kam(role, a, kind, ref, email) kind: company | person | selection | campaign (admins only)
    share(role, a, kind, ref, email)   email invite to a selection or campaign (KAMs inside their scope)
    people_search(role, a, q)          accounts to move an item to (a KAM: her own clients)
    move(role, a, kind, ref, user_id, with_related, tell)   move a selection or campaign to another client
"""
import json

import db
import guard
import kam_scope
import notify
import team

FREE = "personal:"


def viewer(user):
    """(role, admin row) for a portal account, or (None, None)."""
    a = kam_scope.admin_for_email(user["email"]) if user is not None and user["email"] else None
    if a is None or a["disabled_at"]:
        return None, None
    r = team.role_of(a)
    return ("admin" if r in ("owner", "admin") else "kam" if r == "kam" else None), a


def _kam_name(email):
    email = (email or "").strip().lower()
    for n, m in notify.kams():
        if m == email:
            return n or m
    return email


def _kam_of_user(u, dmap):
    """The KAM an account answers to: its own users.kam, else its domain's mapping."""
    own = (u["kam"] if "kam" in u.keys() else None) or ""
    if own:
        a = notify.kam_address(own)
        return (a or own).lower()
    return dmap.get((u["domain"] or "").lower(), "")


def _key(u):
    d = (u["domain"] or "").lower()
    return (FREE + (u["email"] or "").lower()) if (not d or guard._matches(d, guard.FREE_DOMAINS)) else d


def _users(role, a):
    sc = kam_scope.clients(a) if role == "kam" else None
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM users WHERE deleted_at IS NULL ORDER BY company, name, email").fetchall()
    if sc is None:
        return rows, None
    keep = [u for u in rows if u["code_id"] is not None and int(u["code_id"]) in sc]
    return rows, (sc, keep)


def _items(code_ids):
    """{code_id: ([selection rows], [campaign rows])} for these client codes."""
    ids = [int(c) for c in code_ids if c is not None]
    out = {i: ([], []) for i in ids}
    if not ids:
        return out
    marks = ",".join("?" * len(ids))
    with db.connect() as conn:
        for s in conn.execute("SELECT id, token, name, codes, code_id, updated_at FROM selections WHERE code_id IN (%s) "
                              "AND archived_at IS NULL AND deleted_at IS NULL ORDER BY updated_at DESC" % marks, ids):
            out[s["code_id"]][0].append(s)
        for k in conn.execute("SELECT id, token, name, code_id, selection_id, status, starts_at, ends_at, origin FROM campaigns "
                              "WHERE code_id IN (%s) ORDER BY CASE status WHEN 'live' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END, "
                              "COALESCE(starts_at, 0) DESC, id DESC" % marks, ids):
            out[k["code_id"]][1].append(k)
    return out


def _handed(a):
    """Selections and campaigns the owner handed this KAM: ({id: row}, {id: row})."""
    import kam_scope as ks
    sc = ks.clients(a)
    sels, camps = {}, {}
    with db.connect() as conn:
        for i in sc.sel_ids:
            r = conn.execute("SELECT id, token, name, codes, code_id, updated_at FROM selections WHERE id = ? AND deleted_at IS NULL", (i,)).fetchone()
            if r:
                sels[i] = r
        for i in sc.camp_ids:
            r = conn.execute("SELECT id, token, name, code_id, selection_id, status, starts_at, ends_at, origin FROM campaigns WHERE id = ?", (i,)).fetchone()
            if r:
                camps[i] = r
    return sels, camps


def _sel_row(s, kam):
    import lifecycle
    try:
        n = len(json.loads(s["codes"] or "[]"))
    except ValueError:
        n = 0
    return {"id": s["id"], "token": s["token"], "name": s["name"], "creators": n, "updated_at": s["updated_at"],
            "status": lifecycle.chip(s), "kam": kam.get(("selection", s["id"]), ""),
            "link": "selection/#s=" + s["token"]}


def _camp_row(k, kam):
    return {"id": k["id"], "token": k["token"], "name": k["name"], "status": k["status"],
            "draft_by_client": bool(k["origin"] == "client" and k["status"] == "draft"),
            "starts_at": k["starts_at"], "ends_at": k["ends_at"], "has_selection": bool(k["selection_id"]),
            "kam": kam.get(("campaign", k["id"]), ""), "link": "campaign/dashboard/#t=" + k["token"]}


def _item_kams():
    with db.connect() as conn:
        return {(r["kind"], r["item_id"]): r["kam_email"] for r in conn.execute("SELECT kind, item_id, kam_email FROM item_kam")}


def _groups(role, a):
    """{key: {name, domain, users: [rows]}} plus the handed items outside her clients (KAM)."""
    allu, scoped = _users(role, a)
    users = allu if scoped is None else scoped[1]
    groups = {}
    for u in users:
        g = groups.setdefault(_key(u), {"users": [], "names": {}})
        g["users"].append(u)
        c = (u["company"] or "").strip()
        if c:
            g["names"][c] = g["names"].get(c, 0) + 1
    return groups, allu, scoped


def _name_of(key, g):
    if key.startswith(FREE):
        u = g["users"][0]
        return (u["company"] or u["name"] or u["email"] or "").strip() + " (personal email)"
    return max(g["names"], key=g["names"].get) if g["names"] else key


def companies(role, a):
    groups, allu, scoped = _groups(role, a)
    dmap = kam_scope.domain_map()
    kam = _item_kams()
    items = _items([u["code_id"] for g in groups.values() for u in g["users"]])
    rows = []
    for key, g in groups.items():
        sels = camps = live = 0
        for u in g["users"]:
            s, c = items.get(u["code_id"], ([], []))
            sels += len(s); camps += len(c); live += sum(1 for k in c if k["status"] == "live")
        k_email = "" if key.startswith(FREE) else dmap.get(key, "")
        rows.append({"key": key, "name": _name_of(key, g), "domain": "" if key.startswith(FREE) else key,
                     "kam": {"email": k_email, "name": _kam_name(k_email) if k_email else ""},
                     "people": len(g["users"]), "selections": sels, "campaigns": camps, "live": live})
    handed_n = 0
    if role == "kam":
        hs, hc = _handed(a)
        own = {u["code_id"] for g in groups.values() for u in g["users"]}
        handed_n = sum(1 for r in hs.values() if r["code_id"] not in own) + sum(1 for r in hc.values() if r["code_id"] not in own)
        if handed_n:
            rows.append({"key": "handed", "name": "Handed to you", "domain": "", "kam": {"email": "", "name": ""},
                         "people": 0, "selections": sum(1 for r in hs.values() if r["code_id"] not in own),
                         "campaigns": sum(1 for r in hc.values() if r["code_id"] not in own), "live": 0})
    rows.sort(key=lambda r: (r["key"] == "handed", r["name"].lower()))
    return {"companies": rows, "kams": [{"name": n, "email": m} for n, m in notify.kams()], "role": role}


def company(role, a, key):
    dmap = kam_scope.domain_map()
    kam = _item_kams()
    if key == "handed" and role == "kam":
        groups, _, _ = _groups(role, a)
        own = {u["code_id"] for g in groups.values() for u in g["users"]}
        hs, hc = _handed(a)
        with db.connect() as conn:
            owners = {r["code_id"]: r for r in conn.execute("SELECT * FROM users WHERE code_id IS NOT NULL")}
        people = {}
        for s in hs.values():
            if s["code_id"] in own:
                continue
            people.setdefault(s["code_id"], ([], []))[0].append(_sel_row(s, kam))
        for k in hc.values():
            if k["code_id"] in own:
                continue
            people.setdefault(k["code_id"], ([], []))[1].append(_camp_row(k, kam))
        out = []
        for cid, (ss, cc) in people.items():
            u = owners.get(cid)
            out.append({"id": u["id"] if u else None, "name": (u["name"] if u else "") or "Shared access code",
                        "email": (u["email"] if u else "") or "", "job_title": (u["job_title"] if u else "") or "",
                        "company": (u["company"] if u else "") or "", "kam": "", "last_login_at": u["last_login_at"] if u else None,
                        "selections": ss, "campaigns": cc})
        return {"key": key, "name": "Handed to you", "people": out}
    groups, _, _ = _groups(role, a)
    g = groups.get(key)
    if g is None:
        return None
    items = _items([u["code_id"] for u in g["users"]])
    hs, hc = ({}, {})
    out = []
    for u in sorted(g["users"], key=lambda r: ((r["name"] or r["email"] or "").lower())):
        s, c = items.get(u["code_id"], ([], []))
        out.append({"id": u["id"], "name": u["name"] or "", "email": u["email"], "job_title": u["job_title"] or "",
                    "company": u["company"] or "", "kam": _kam_of_user(u, dmap), "last_login_at": u["last_login_at"],
                    "status": u["status"], "selections": [_sel_row(x, kam) for x in s], "campaigns": [_camp_row(x, kam) for x in c]})
    k_email = "" if key.startswith(FREE) else dmap.get(key, "")
    return {"key": key, "name": _name_of(key, g), "domain": "" if key.startswith(FREE) else key,
            "kam": {"email": k_email, "name": _kam_name(k_email) if k_email else ""}, "people": out}


def _valid_kam(email):
    email = (email or "").strip().lower()
    return email if (not email or email in {m for _, m in notify.kams()}) else None


def set_kam(role, a, kind, ref, email, by=""):
    """Admins only. Returns (ok, message)."""
    if role != "admin":
        return False, "Only HelloVoice admins can change an account manager."
    k = _valid_kam(email)
    if k is None:
        return False, "Pick an account manager from the list."
    if kind == "company":
        dom = str(ref or "").strip().lower()
        if not dom or "." not in dom or dom.startswith(FREE):
            return False, "That company has no domain to map."
        dmap = dict(kam_scope.domain_map())
        if k:
            kam_scope.set_domain_map(dict(dmap, **{dom: k}), by)
        else:
            dmap.pop(dom, None)
            kam_scope.set_domain_map(dmap, by)
            with db.connect() as conn:
                conn.execute("UPDATE users SET kam = NULL WHERE LOWER(domain) = ? AND deleted_at IS NULL", (dom,))
        return True, ("%s now looks after %s." % (_kam_name(k), dom)) if k else "%s has no account manager now." % dom
    if kind == "person":
        import portal
        u = portal.user_by_id(int(ref)) if str(ref).isdigit() else None
        if u is None:
            return False, "That person no longer exists."
        with db.connect() as conn:
            conn.execute("UPDATE users SET kam = ? WHERE id = ?", (k or None, u["id"]))
        return True, ("%s now looks after %s." % (_kam_name(k), u["name"] or u["email"])) if k else "%s follows the company's account manager." % (u["name"] or u["email"])
    if kind in ("selection", "campaign"):
        import kam_items
        item, err = kam_items.assign(kind, int(ref), k, by)
        if err == "unknown":
            return False, "That item no longer exists."
        if err:
            return False, "Pick an account manager from the list."
        return True, ("Handed to %s. They have been told." % _kam_name(k)) if k else "Taken back from the account manager."
    return False, "Unknown target."


def share(role, a, kind, ref, email, by, by_name=""):
    """Invite an email to a selection or campaign. A KAM only inside her scope. Returns (ok, message, state)."""
    import access
    if kind == "selection":
        item = db.selection(int(ref)) if str(ref).isdigit() else None
        code = item["code_id"] if item is not None else None
    elif kind == "campaign":
        item = db.campaign(int(ref)) if str(ref).isdigit() else None
        code = kam_scope.campaign_code(item["id"])[1] if item is not None else None
    else:
        return False, "Unknown target.", None
    if item is None:
        return False, "That item no longer exists.", None
    if role == "kam":
        sc = kam_scope.clients(a)
        kam_scope.begin(sc)
        try:
            allowed = kam_scope.allows(kam_scope.selection_code(item["id"])[1] if kind == "selection" else kam_scope.campaign_code(item["id"])[1])
        finally:
            kam_scope.end()
        if not allowed:
            return False, "That belongs to a client you do not manage.", None
    state, err = (access.invite(item, email, by, by_name) if kind == "selection" else access.invite_campaign(item, email, by, by_name))
    msgs = {"email": "That does not look like an email address.", "self": "That is the owner: they already have it.",
            "limit": "That already has %d invited people." % access.MAX_INVITES,
            "no_selection": "This campaign has no selection yet. Link its selection first."}
    if err:
        return False, msgs.get(err, "Could not share."), None
    em = guard.normalise_email(email)
    return True, ("%s can now open and edit it." % em) if state == "granted" else "Invited. It opens for %s when they sign in with that email." % em, state


def people_search(role, a, q):
    """Accounts matching a name, email or company, for the Move picker. At most 15."""
    q = " ".join(str(q or "").lower().split())
    if len(q) < 2:
        return []
    allu, scoped = _users(role, a)
    rows = scoped[1] if scoped is not None else allu
    out = []
    for u in rows:
        hay = " ".join([(u["name"] or ""), (u["email"] or ""), (u["company"] or "")]).lower()
        if q in hay and u["code_id"] is not None and u["status"] == "active":
            out.append({"id": u["id"], "name": u["name"] or "", "email": u["email"], "company": u["company"] or "",
                        "domain": u["domain"] or ""})
        if len(out) >= 15:
            break
    return out


def move(role, a, kind, ref, user_id, with_related=True, tell=True):
    """Move a selection or campaign to another client account (item 129, phase 2). Admins: anywhere. A KAM: only
    an item of hers, to one of her own clients. Selection: its campaigns come too when ``with_related``;
    campaign: its selection comes too. Goes through assign.py, which writes History and rings the client's bell.
    Returns (ok, message)."""
    import assign
    import portal
    target = portal.user_by_id(int(user_id)) if str(user_id).isdigit() else None
    if target is None or target["code_id"] is None:
        return False, "Pick the client to move it to."
    if kind == "selection":
        item = db.selection(int(ref)) if str(ref).isdigit() else None
    elif kind == "campaign":
        item = db.campaign(int(ref)) if str(ref).isdigit() else None
    else:
        return False, "Unknown target."
    if item is None:
        return False, "That item no longer exists."
    if role == "kam":
        sc = kam_scope.clients(a)
        kam_scope.begin(sc)
        try:
            mine = kam_scope.allows(kam_scope.selection_code(item["id"])[1] if kind == "selection" else kam_scope.campaign_code(item["id"])[1])
            dest = kam_scope.allows(target["code_id"])
        finally:
            kam_scope.end()
        if not mine:
            return False, "That belongs to a client you do not manage."
        if not dest:
            return False, "You can only move it to one of your own clients."
    elif role != "admin":
        return False, "Not allowed."
    if kind == "selection":
        r = assign.assign_selection(item["id"], target["code_id"], move_campaigns=bool(with_related), tell=bool(tell), confirmed=True)
    else:
        r = assign.assign_campaign(item["id"], target["code_id"], with_selection=bool(with_related), tell=bool(tell), confirmed=True)
    if r["error"] or not r["ok"]:
        return False, r["error"] or "Could not move it."
    if r["noop"]:
        return True, "Nothing changed: it already belongs to %s." % r["to"]
    extra = (" Moved %d campaign%s with it." % (len(r["campaigns"]), "" if len(r["campaigns"]) == 1 else "s")) if r.get("campaigns") else ""
    return True, "Moved to %s.%s" % (r["to"], extra)
