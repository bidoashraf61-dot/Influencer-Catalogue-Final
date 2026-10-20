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
UNASSIGNED = "unassigned"      # items filed under team accounts or plain access codes: not a client yet
STAFF_DOMAINS = ("blueholding.co.uk", "hellovoice.co.uk")      # the owner and its team of account managers: never "clients"


def staff_domains():
    extra = db.setting("staff_domains") or []
    return {d.strip().lower() for d in list(STAFF_DOMAINS) + (extra if isinstance(extra, list) else []) if str(d).strip()}


def kam_options():
    """Who can be an account manager: the BlueHolding team's own accounts (the owner, HelloVoice, is not one), every
    KAM login in the admin, and anyone in the Settings "kams" list. [{name, email}], by name."""
    seen = {}
    team_domains = staff_domains() - {"hellovoice.co.uk"}
    with db.connect() as conn:
        for u in conn.execute("SELECT name, email, domain FROM users WHERE deleted_at IS NULL AND email IS NOT NULL"):
            if (u["domain"] or "").lower() in team_domains:
                seen[u["email"].lower()] = (u["name"] or "").strip()
        for r in conn.execute("SELECT name, email FROM admins WHERE role = 'kam' AND disabled_at IS NULL AND email LIKE '%@%'"):
            seen.setdefault(r["email"].lower(), (r["name"] or "").strip())
            if r["name"] and not seen[r["email"].lower()]:
                seen[r["email"].lower()] = r["name"]
    for n, m in notify.kams():
        seen.setdefault(m, (n or "").strip())
    return [{"name": n or m.split("@")[0], "email": m} for m, n in sorted(seen.items(), key=lambda kv: ((kv[1] or kv[0]).lower()))]


def viewer(user):
    """(role, admin row) for a portal account, or (None, None)."""
    a = kam_scope.admin_for_email(user["email"]) if user is not None and user["email"] else None
    if a is None or a["disabled_at"]:
        return None, None
    r = team.role_of(a)
    return ("admin" if r in ("owner", "admin") else "kam" if r == "kam" else None), a


def _kam_name(email):
    email = (email or "").strip().lower()
    for k in kam_options():
        if k["email"] == email:
            return k["name"] or email
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
            "starts_at": k["starts_at"], "ends_at": k["ends_at"], "has_selection": bool(k["selection_id"]), "selection_id": k["selection_id"],
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
        if (u["domain"] or "").lower() in staff_domains():
            continue                           # HelloVoice (the owner) and BlueHolding (the account managers) are not clients
        g = groups.setdefault(_key(u), {"users": [], "names": {}})
        g["users"].append(u)
        c = (u["company"] or "").strip()
        if c:
            g["names"][c] = g["names"].get(c, 0) + 1
    return groups, allu, scoped


def _unassigned_people():
    """Items filed under the team's own accounts or under plain access codes (no account behind them): shown so an
    admin can move them to the right client. Only entries that actually hold something."""
    kam = _item_kams()
    dmap = kam_scope.domain_map()
    with db.connect() as conn:
        allu = conn.execute("SELECT * FROM users WHERE deleted_at IS NULL").fetchall()
        user_codes = {u["code_id"] for u in allu if u["code_id"] is not None}
        loose_ids = [r[0] for r in conn.execute(
            "SELECT code_id FROM selections WHERE code_id IS NOT NULL AND deleted_at IS NULL AND archived_at IS NULL "
            "UNION SELECT code_id FROM campaigns WHERE code_id IS NOT NULL")]
        loose = {r["id"]: r for r in conn.execute("SELECT id, label FROM codes")} if loose_ids else {}
    staff = [u for u in allu if (u["domain"] or "").lower() in staff_domains() and u["code_id"] is not None]
    loose_codes = [i for i in loose_ids if i not in user_codes and i != db.admin_code_id() and i in loose]
    items = _items([u["code_id"] for u in staff] + loose_codes)
    out = []
    for u in sorted(staff, key=lambda r: ((r["name"] or r["email"] or "").lower())):
        s_, c_ = items.get(u["code_id"], ([], []))
        if s_ or c_:
            out.append({"id": u["id"], "name": u["name"] or u["email"], "email": u["email"], "job_title": u["job_title"] or "Team account",
                        "company": u["company"] or "", "kam": "", "last_login_at": u["last_login_at"], "status": u["status"], "staff": True,
                        "selections": [_sel_row(x, kam) for x in s_], "campaigns": [_camp_row(x, kam) for x in c_]})
    for cid in sorted(loose_codes):
        s_, c_ = items.get(cid, ([], []))
        if s_ or c_:
            lab = (loose[cid]["label"] or "").strip() or "Access code #%d" % cid
            kams = {kam.get(("selection", x["id"]), "") for x in s_} | {kam.get(("campaign", x["id"]), "") for x in c_}
            out.append({"id": None, "code_id": cid, "name": lab, "email": "", "job_title": "Plain access code (no account)", "company": "",
                        "kam": kams.pop() if len(kams) == 1 else "", "last_login_at": None, "status": "", "staff": True,
                        "selections": [_sel_row(x, kam) for x in s_], "campaigns": [_camp_row(x, kam) for x in c_]})
    return out


def unfiled_code_ids():
    """The client codes behind the "Not filed under a client" group: team accounts and plain codes that hold work."""
    allu = []
    with db.connect() as conn:
        allu = conn.execute("SELECT code_id, domain FROM users WHERE deleted_at IS NULL AND code_id IS NOT NULL").fetchall()
        used = {r[0] for r in conn.execute(
            "SELECT code_id FROM selections WHERE code_id IS NOT NULL AND deleted_at IS NULL AND archived_at IS NULL "
            "UNION SELECT code_id FROM campaigns WHERE code_id IS NOT NULL")}
    user_codes = {u["code_id"] for u in allu}
    staff = {u["code_id"] for u in allu if (u["domain"] or "").lower() in staff_domains()}
    return (staff | {i for i in used if i not in user_codes}) - {db.admin_code_id()}


def _name_of(key, g):
    if key.startswith(FREE):
        u = g["users"][0]
        return (u["company"] or u["name"] or u["email"] or "").strip() + " (personal email)"
    return max(g["names"], key=g["names"].get) if g["names"] else key


def companies(role, a):
    import peoplectl
    peoplectl.ensure()
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
                     "people": len(g["users"]), "selections": sels, "campaigns": camps, "live": live,
                     "waiting": sum(1 for u in g["users"] if peoplectl.state(u) == "waiting"),
                     "blocked": sum(1 for u in g["users"] if peoplectl.state(u) in ("held", "suspended"))})
    handed_n = 0
    if role == "kam":
        hs, hc = _handed(a)
        own = {u["code_id"] for g in groups.values() for u in g["users"]}
        handed_n = sum(1 for r in hs.values() if r["code_id"] not in own) + sum(1 for r in hc.values() if r["code_id"] not in own)
        if handed_n:
            rows.append({"key": "handed", "name": "Handed to you", "domain": "", "kam": {"email": "", "name": ""},
                         "people": 0, "selections": sum(1 for r in hs.values() if r["code_id"] not in own),
                         "campaigns": sum(1 for r in hc.values() if r["code_id"] not in own), "live": 0})
    if role == "kam":
        tw = [p for p in _unassigned_people() if p.get("staff") and p.get("id")]
        if tw:
            rows.append({"key": "team", "name": "BlueHolding team work", "domain": "", "kam": {"email": "", "name": ""},
                         "people": len(tw), "selections": sum(len(p["selections"]) for p in tw),
                         "campaigns": sum(len(p["campaigns"]) for p in tw),
                         "live": sum(1 for p in tw for k in p["campaigns"] if k["status"] == "live"),
                         "note": "Work filed under BlueHolding accounts. Pass any of it on to an account manager."})
    if role == "admin":
        un = _unassigned_people()
        if un:
            rows.append({"key": UNASSIGNED, "name": "Not filed under a client", "domain": "", "kam": {"email": "", "name": ""},
                         "people": len(un), "selections": sum(len(p["selections"]) for p in un),
                         "campaigns": sum(len(p["campaigns"]) for p in un),
                         "live": sum(1 for p in un for k in p["campaigns"] if k["status"] == "live"),
                         "note": "Filed under team accounts or plain access codes. Open one and Move it to its client."})
    rows.sort(key=lambda r: (r["key"] != UNASSIGNED, r["key"] == "handed", r["name"].lower()))
    return {"companies": rows, "kams": kam_options(), "role": role}


def company(role, a, key):
    import peoplectl, portal
    peoplectl.ensure()
    dmap = kam_scope.domain_map()
    kam = _item_kams()
    if key == "team" and role == "kam":
        return {"key": key, "name": "BlueHolding team work", "domain": "", "kam": {"email": "", "name": ""},
                "people": _annotate(role, a, [p for p in _unassigned_people() if p.get("staff") and p.get("id")])}
    if key == UNASSIGNED:
        return {"key": key, "name": "Not filed under a client", "domain": "", "kam": {"email": "", "name": ""},
                "people": _annotate(role, a, _unassigned_people())} if role == "admin" else None
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
        return {"key": key, "name": "Handed to you", "people": _annotate(role, a, out)}
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
                    "status": u["status"], "state": peoplectl.state(u), "can": peoplectl.allowed(role, a, u),
                    "credits": portal.balance(u["code_id"]) if u["code_id"] is not None else 0,
                    "selections": [_sel_row(x, kam) for x in s], "campaigns": [_camp_row(x, kam) for x in c]})
    k_email = "" if key.startswith(FREE) else dmap.get(key, "")
    return {"key": key, "name": _name_of(key, g), "domain": "" if key.startswith(FREE) else key,
            "kam": {"email": k_email, "name": _kam_name(k_email) if k_email else ""}, "people": _annotate(role, a, out)}


def _valid_kam(email):
    email = (email or "").strip().lower()
    return email if (not email or email in {k["email"] for k in kam_options()}) else None


def _staff_codes():
    with db.connect() as conn:
        return {r["code_id"] for r in conn.execute("SELECT code_id, domain FROM users WHERE code_id IS NOT NULL AND deleted_at IS NULL")
                if (r["domain"] or "").lower() in staff_domains()}


def _can_kam(role, a, code_id, current, staff=None):
    """May this viewer set the account manager of an item? Admins: any. A KAM: only an item filed under a BlueHolding team
    account (so she can pass team work on) or one handed to her."""
    if role == "admin":
        return True
    if role != "kam" or a is None:
        return False
    staff = _staff_codes() if staff is None else staff
    return code_id in staff or (current or "").lower() == (a["email"] or "").lower()


def _annotate(role, a, people):
    """Add can_kam to every selection and campaign row in these people blocks."""
    staff = _staff_codes() if role == "kam" else None
    codes = {}
    with db.connect() as conn:
        for kind, table in (("selection", "selections"), ("campaign", "campaigns")):
            for r in conn.execute("SELECT id, code_id FROM %s" % table):
                codes[(kind, r["id"])] = r["code_id"]
    for p in people:
        for kind, key in (("selection", "selections"), ("campaign", "campaigns")):
            for it in p.get(key, []):
                it["can_kam"] = _can_kam(role, a, codes.get((kind, it["id"])), it.get("kam"), staff)
                if kind == "campaign":
                    _stage(role, it)
    return _attach_packages(people)


def _stage(role, it):
    """The campaign's board stage (item 177): every row shows it; only an admin may change it or set Live / Unlive."""
    import board
    k = db.campaign(int(it["id"]))
    if k is not None:
        st = board.stage_of(k)
        it["stage"] = {"key": st, "label": board.LABEL[st]}
    it["can_stage"] = role == "admin"


def set_kam(role, a, kind, ref, email, by=""):
    """Admins anywhere; a KAM only on items under team accounts or handed to her. Returns (ok, message)."""
    if role == "kam" and kind in ("selection", "campaign") and str(ref).isdigit():
        item = db.selection(int(ref)) if kind == "selection" else db.campaign(int(ref))
        if item is None or not _can_kam(role, a, item["code_id"], db.kam_of_item(kind, item["id"])):
            return False, "You can only pass on work filed under BlueHolding team accounts or handed to you."
    elif role != "admin":
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


def share(role, a, kind, ref, email, by, by_name="", access_role="edit"):
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
    if kind == "campaign":
        return _share_campaign(item, email, by, by_name, access_role)
    state, err = access.invite(item, email, by, by_name)
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
        dom = (u["domain"] or "").lower()
        if dom == "hellovoice.co.uk":
            continue                                   # the owner's own account is not a place to file work
        if q in hay and u["code_id"] is not None and u["status"] == "active":
            team = dom in staff_domains()              # a BlueHolding account manager: file it under their name
            out.append({"id": u["id"], "code_id": u["code_id"], "kind": "team" if team else "account", "name": u["name"] or "", "email": u["email"],
                        "company": ("Team · " + (u["job_title"] or "BlueHolding")) if team else (u["company"] or ""), "domain": u["domain"] or ""})
        if len(out) >= 15:
            break
    if len(out) < 15:                                  # clients that only have a plain access code (no account)
        import assign
        for t in assign.targets():
            if t["kind"] == "code" and q in (t["label"] or "").lower():
                if role == "admin" or kam_scope.allows(t["id"], kam_scope.clients(a)):
                    out.append({"id": None, "code_id": t["id"], "kind": "code", "name": t["label"], "email": "", "company": "Access code", "domain": ""})
            if len(out) >= 15:
                break
    return out


def move(role, a, kind, ref, user_id, with_related=True, tell=True, to_code=None):
    """Move a selection or campaign to another client account (item 129, phase 2). Admins: anywhere. A KAM: only
    an item of hers, to one of her own clients. Selection: its campaigns come too when ``with_related``;
    campaign: its selection comes too. Goes through assign.py, which writes History and rings the client's bell.
    Returns (ok, message)."""
    import assign
    import portal
    target = portal.user_by_id(int(user_id)) if str(user_id).isdigit() else None
    if target is None and str(to_code or "").isdigit():
        code_row = db.get_code(int(to_code))              # a client that only has a plain access code
        if code_row is not None and portal.user_for_code(code_row["id"]) is None:
            target = {"code_id": code_row["id"], "domain": ""}
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
    ok, msg, _ = _move_package(kind, item, target["code_id"], tell)
    return ok, msg


def _move_package(kind, item, target_code, tell=True):
    """The move itself, with no permission check. A campaign is its whole package (owner, 2026-10-18): the campaign, its
    selection, every campaign made from that selection, its briefs and the quote request all move together.
    Returns (ok, message, old_code_id)."""
    import assign
    sel = item if kind == "selection" else (db.selection(item["selection_id"]) if item["selection_id"] else None)
    old = (sel["code_id"] if sel is not None else item["code_id"])
    if sel is not None:
        r = assign.assign_selection(sel["id"], target_code, move_campaigns=True, tell=bool(tell), confirmed=True)
    else:
        r = assign.assign_campaign(item["id"], target_code, with_selection=False, tell=bool(tell), confirmed=True)
    if r["error"] or not r["ok"]:
        return False, r["error"] or "Could not move it.", old
    briefs = 0
    if sel is not None:
        with db.connect() as conn:
            briefs = conn.execute("UPDATE briefs SET code_id = ? WHERE selection_id = ? AND code_id != ?",
                                  (target_code, sel["id"], target_code)).rowcount
            if sel["request_id"]:
                conn.execute("UPDATE requests SET code_id = ? WHERE id = ?", (target_code, sel["request_id"]))
    if r["noop"] and not briefs:
        return True, "Nothing changed: it already belongs to %s." % r["to"], old
    bits = []
    if sel is not None:
        bits.append("its selection")
    if r.get("campaigns"):
        bits.append("%d campaign%s" % (len(r["campaigns"]), "" if len(r["campaigns"]) == 1 else "s"))
    if briefs:
        bits.append("%d brief%s" % (briefs, "" if briefs == 1 else "s"))
    return True, "Moved to %s%s." % (r["to"], (" with " + ", ".join(bits)) if bits else ""), old


def _drop_empty_code(code_id, by=""):
    """After work leaves a plain access code (no account behind it), remove the code when nothing is tied to it any more.
    Archives then deletes it through History, so it can be restored. Returns its label when removed, else None."""
    import history
    import portal
    code = db.get_code(code_id) if code_id else None
    if code is None or code_id == db.admin_code_id() or portal.user_for_code(code_id) is not None:
        return None
    with db.connect() as conn:
        left = conn.execute("SELECT (SELECT COUNT(*) FROM selections WHERE code_id = ? AND deleted_at IS NULL) + "
                            "(SELECT COUNT(*) FROM campaigns WHERE code_id = ?)", (code_id, code_id)).fetchone()[0]
    if left:
        return None
    history.set_actor(by or "admin")
    with history.tracked("code", code_id, "Deleted access code %s (its work moved to an account manager)" % (code["label"] or "")):
        if not code["archived_at"]:
            db.archive_code(code_id)
        why = db.delete_code(code_id)
    return None if why else (code["label"] or "the access code")


def assign_kam(role, a, kind, ref, email, by="", tell=True):
    """Assign a KAM to a campaign or selection (owner, 2026-10-18): the whole package moves under that account manager's own
    account (their name, the BlueHolding domain) and an access code it came from is removed when it is left empty. They can
    then share it with their client. An account manager with no portal account yet only gets it handed to them (tagged).
    Admins: any. A KAM: only team-filed work or what was handed to her. Returns (ok, message)."""
    import portal
    k = _valid_kam(email)
    if not k:
        return False, "Pick an account manager from the list."
    item = None
    if kind == "selection":
        item = db.selection(int(ref)) if str(ref).isdigit() else None
    elif kind == "campaign":
        item = db.campaign(int(ref)) if str(ref).isdigit() else None
    else:
        return False, "Unknown target."
    if item is None:
        return False, "That item no longer exists."
    if role != "admin":
        if role != "kam" or not _can_kam(role, a, item["code_id"], db.kam_of_item(kind, item["id"])):
            return False, "You can only pass on work filed under BlueHolding team accounts or handed to you."
    target = portal.user_by_email(k)
    if target is None or target["code_id"] is None or target["status"] != "active":
        ok, msg = set_kam(role, a, kind, ref, k, by)           # no account to file it under: hand it over, tagged
        return ok, (msg + " They have no portal account yet, so it stays where it is.") if ok else msg
    ok, msg, old = _move_package(kind, item, target["code_id"], tell)
    if not ok:
        return False, msg
    # tag every selection and campaign of the package so the hub shows who holds it
    sel = item if kind == "selection" else (db.selection(item["selection_id"]) if item["selection_id"] else None)
    import kam_items
    if sel is not None:
        kam_items.assign("selection", sel["id"], k, by)
        for c in db.campaigns_for_selection(sel["id"]):
            kam_items.assign("campaign", c["id"], k, by)
    else:
        kam_items.assign("campaign", item["id"], k, by)
    gone = _drop_empty_code(old, by)
    return True, msg.replace("Moved to", "Assigned to %s: moved to" % _kam_name(k), 1) + ((" The access code “%s” was removed." % gone) if gone else "")


def delete(role, a, kind, ref, by="", with_selection=True):
    """Delete a campaign (item 129). Admins: any. A KAM: only a campaign inside her scope. History records it, so it can be
    brought back from History. Returns (ok, message)."""
    import history
    if kind == "selection":
        return _delete_selection(role, ref, by)
    if kind != "campaign":
        return False, "Only campaigns and selections can be deleted here."
    k = db.campaign(int(ref)) if str(ref).isdigit() else None
    if k is None:
        return False, "That campaign no longer exists."
    if role == "kam":
        sc = kam_scope.clients(a)
        kam_scope.begin(sc)
        try:
            ok = kam_scope.allows(kam_scope.campaign_code(k["id"])[1])
        finally:
            kam_scope.end()
        if not ok:
            return False, "That belongs to a client you do not manage."
    elif role != "admin":
        return False, "Not allowed."
    history.set_actor(by or "admin")
    sel = db.selection(k["selection_id"]) if k["selection_id"] else None
    with history.tracked("campaign", k["id"], "Deleted campaign " + (k["name"] or "")):
        db.delete_campaign(k["id"])
    tail = ""
    if with_selection and sel is not None:
        if db.campaigns_for_selection(sel["id"]):                 # another campaign still uses it: keep it
            tail = " (its selection stays: another campaign uses it)"
        else:
            import portal
            with history.tracked("selection", sel["id"], "Deleted selection " + (sel["name"] or "") + " (with its campaign)"):
                db.delete_selection(sel["id"])
            with db.connect() as conn:
                ids = [r[0] for r in conn.execute("SELECT id FROM briefs WHERE selection_id = ? AND deleted_at IS NULL", (sel["id"],))]
            n = sum(1 for bid in ids if portal.delete_brief(bid, db.admin_code_id()))
            tail = " with its selection" + ((" and %d brief%s" % (n, "" if n == 1 else "s")) if n else "")
    gone = _drop_empty_code(k["code_id"], by) if with_selection else None
    if gone:
        tail += " and the empty access code “%s”" % gone
    return True, "Deleted “%s”%s. You can bring it back from History." % (k["name"] or "the campaign", tail)


def _delete_selection(role, ref, by=""):
    """Delete a selection that has no campaign (admins only), with its briefs; an access code left empty goes too."""
    import history
    import portal
    if role != "admin":
        return False, "Only an admin can delete a selection here."
    sel = db.selection(int(ref)) if str(ref).isdigit() else None
    if sel is None:
        return False, "That selection no longer exists."
    if db.campaigns_for_selection(sel["id"]):
        return False, "A campaign uses this selection: delete the campaign instead."
    history.set_actor(by or "admin")
    code_id = sel["code_id"]
    with history.tracked("selection", sel["id"], "Deleted selection " + (sel["name"] or "")):
        db.delete_selection(sel["id"])
    with db.connect() as conn:
        ids = [r[0] for r in conn.execute("SELECT id FROM briefs WHERE selection_id = ? AND deleted_at IS NULL", (sel["id"],))]
    n = sum(1 for bid in ids if portal.delete_brief(bid, db.admin_code_id()))
    gone = _drop_empty_code(code_id, by)
    return True, "Deleted “%s”%s%s. You can bring it back from History." % (
        sel["name"] or "the selection", (" and %d brief%s" % (n, "" if n == 1 else "s")) if n else "",
        (" and the empty access code “%s”" % gone) if gone else "")


def _owner_label(code_id, users, codes):
    if code_id is None:
        return {"label": "Not filed under anyone", "kind": "none"}
    u = users.get(code_id)
    if u is not None:
        who = (u["name"] or u["email"] or "").strip()
        return {"label": who + ((" · " + u["company"]) if u["company"] else ""), "kind": "account",
                "staff": (u["domain"] or "").lower() in staff_domains()}
    c = codes.get(code_id)
    return {"label": ((c["label"] if c is not None else "") or "Access code #%s" % code_id) + " (access code)", "kind": "code"}


def campaigns(role, a, q="", offset=0, limit=40):
    """Every campaign, found by name, client, brand or owner (item 129): the flat list behind "All campaigns". Admins see all,
    even those filed under nobody; a KAM, her clients' plus what was handed to her. -> {total, items: [camp row + owner + selection]}"""
    q = " ".join(str(q or "").lower().split())
    kam = _item_kams()
    with db.connect() as conn:
        rows = conn.execute("SELECT k.id, k.token, k.name, k.client, k.code_id, k.selection_id, k.status, k.starts_at, k.ends_at, k.origin, k.updated_at, "
                            "s.name AS sel_name, s.code_id AS sel_code_id FROM campaigns k LEFT JOIN selections s ON s.id = k.selection_id "
                            "ORDER BY CASE k.status WHEN 'live' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END, k.updated_at DESC").fetchall()
        users = {u["code_id"]: u for u in conn.execute("SELECT * FROM users WHERE code_id IS NOT NULL")}
        codes = {c["id"]: c for c in conn.execute("SELECT id, label FROM codes")}
    if role == "kam":
        sc = kam_scope.clients(a)
        staff = _staff_codes()
        kam_scope.begin(sc)
        try:
            mine = kam_scope.keep_items(rows, "campaign", fallback="sel_code_id")
        finally:
            kam_scope.end()
        have = {r["id"] for r in mine}
        rows = mine + [r for r in rows if r["id"] not in have and r["code_id"] in staff]     # BlueHolding's own work is visible to the team
    out = []
    for r in rows:
        owner = _owner_label(r["code_id"], users, codes)
        row = _camp_row(r, kam)
        row.update({"owner": owner, "selection": r["sel_name"] or "", "client": r["client"] or ""})
        hay = " ".join([row["name"], row["client"], owner["label"], row["selection"]]).lower()
        if not q or q in hay:
            out.append(row)
    total = len(out)
    page = out[int(offset):int(offset) + int(limit)]
    _annotate(role, a, [{"campaigns": page}])
    return {"total": total, "items": page}


def _share_campaign(k, email, by, by_name, access_role):
    """Invite an email to a campaign's dashboard with a role: "view" (read the dashboard and report) or "edit" (also
    update it and invite others). Edit also opens the campaign's selection for them; view does not. One email."""
    import access
    import mailer
    em = guard.normalise_email(email)
    if not em:
        return False, "That does not look like an email address.", None
    role_ = "edit" if access_role == "edit" else "view"
    have = db.cinvites_for(k["id"])
    if len(have) >= access.MAX_INVITES and em not in {x["email"] for x in have}:
        return False, "That already has %d invited people." % access.MAX_INVITES, None
    new, changed = db.cinvite_add(k["id"], em, role_, by)
    sel = db.selection(k["selection_id"]) if k["selection_id"] else None
    if sel is not None and role_ == "edit":
        access.invite(sel, em, by, by_name, send=False)           # the selection comes with an editor, silently
    if changed and mailer.configured():
        try:
            mailer.send_access(em, "campaign dashboard", k["name"], by_name or "HelloVoice",
                               "view and edit" if role_ == "edit" else "view only",
                               "%s/campaign/dashboard/#t=%s" % (mailer.SITE, k["token"]))
        except Exception:
            pass
    what = "view and edit" if role_ == "edit" else "view only"
    return True, ("%s can now %s it." % (em, what)) if not new else "Invited %s (%s). It opens when they sign in with that email." % (em, what), "invited" if new else "granted"


def _package_ctx():
    """({selection ids used by a campaign}, {selection id: info}) for the merged campaign-and-selection cards."""
    import lifecycle
    with db.connect() as conn:
        used = {r[0] for r in conn.execute("SELECT DISTINCT selection_id FROM campaigns WHERE selection_id IS NOT NULL")}
        info = {}
        for r in conn.execute("SELECT id, token, name, codes, code_id, updated_at, request_id FROM selections WHERE id IN "
                              "(SELECT DISTINCT selection_id FROM campaigns WHERE selection_id IS NOT NULL) AND deleted_at IS NULL"):
            try:
                n = len(json.loads(r["codes"] or "[]"))
            except ValueError:
                n = 0
            info[r["id"]] = {"id": r["id"], "token": r["token"], "name": r["name"], "creators": n, "link": "selection/#s=" + r["token"],
                             "status": lifecycle.chip(r)}
    return used, info


def _attach_packages(people):
    """Mark selections that belong to a campaign, and put each campaign's selection on its card."""
    used, info = _package_ctx()
    for p in people:
        for sel in p.get("selections", []):
            sel["in_campaign"] = sel["id"] in used
        for c in p.get("campaigns", []):
            c["package"] = info.get(c.get("selection_id"))
    return people
