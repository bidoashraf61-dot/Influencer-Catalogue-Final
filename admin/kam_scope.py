"""Key account managers see only their own clients (owner, 2026-10-11, programme item 82).

ONE rule, used everywhere:

    clients(who)  -> None        owners, admins and viewers: every client
                  -> frozenset   a key account manager (role "kam"): the client code ids that are hers

A client is hers when the company domain of the account maps to her in the ``domain_kam``
setting ({domain: kam email}, one KAM per domain), or when the account's ``users.kam`` names her
and its domain is not mapped to someone else. Shared access codes HelloVoice linked onto those
accounts (codelinks) come along, like they do for the client.

Admin requests set the scope for the thread (``begin``) so every list the admin draws
(db.list_selections, list_campaigns, list_codes, client_overview, list_requests,
analysis_requests, recent_events, request_pulse, portal.list_users, briefs, chats, credit
requests) is filtered at the source, and ``check`` refuses any route outside the KAM allow list
or naming an id of another client ("Not your client").
"""
import json
import threading

_t = threading.local()

NOT_YOURS = "Not your client"


# ------------------------------------------------------------------ who --

def _get(row, key):
    try:
        return row[key] if row is not None and key in row.keys() else None
    except AttributeError:
        return row.get(key) if isinstance(row, dict) else None


def is_kam(who):
    import team
    return who is not None and team.role_of(who) == "kam"


def _norm(v):
    return " ".join(str(v or "").split()).strip().lower()


def keys_for(email, name=None):
    """Every way users.kam may name this person: the email, the name, and "Name <email>"."""
    email = _norm(email)
    out = {k for k in (email, _norm(name)) if k}
    try:
        import notify
        for n, m in notify.kams():
            if _norm(m) == email and n:
                out.add(_norm(n))
                out.add(_norm("%s <%s>" % (n, m)))
    except Exception:
        pass
    return out


def names_kam(value, email, keys):
    v = _norm(value)
    if not v:
        return False
    if v in keys:
        return True
    return bool(email) and ("<" + email + ">") in v


def domain_map():
    """{domain: kam email}, lower-cased, from the ``domain_kam`` setting."""
    import db
    raw = db.setting("domain_kam") or {}
    if not isinstance(raw, dict):
        return {}
    return {_norm(k).lstrip("@"): _norm(v) for k, v in raw.items() if _norm(k) and _norm(v)}


def user_rows(email, name=None):
    """The portal accounts that are this KAM's clients (deleted accounts excluded)."""
    import db
    email = _norm(email)
    if not email:
        return []
    keys = keys_for(email, name)
    dmap = domain_map()
    mine_domains = {d for d, k in dmap.items() if k == email or names_kam(k, email, keys)}
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM users WHERE deleted_at IS NULL ORDER BY company, name, email").fetchall()
    out = []
    for u in rows:
        dom = _norm(u["domain"])
        if dom in mine_domains:
            out.append(u)
        elif dom not in dmap and names_kam(_get(u, "kam"), email, keys):
            out.append(u)
    return out


def clients(who):
    """None (= every client) for anyone but a key account manager; for a KAM the frozenset of
    client code ids that are hers. ``who`` is an admin row (session or admins table)."""
    if not is_kam(who):
        return None
    codes = {u["code_id"] for u in user_rows(_get(who, "email"), _get(who, "name")) if u["code_id"] is not None}
    if codes:
        import codelinks
        codes |= codelinks.linked_for(codes)
    return frozenset(int(c) for c in codes)


def admin_for_email(email):
    """The admin row behind a portal account's email, or None."""
    import db
    if not email:
        return None
    try:
        return db.admin_by_email(email)
    except Exception:
        return None


def creators(scope):
    """Creator codes in the selections and campaigns of these clients: the analyses a KAM may open."""
    import db
    if scope is None:
        return None
    ids = sorted(scope)
    if not ids:
        return frozenset()
    marks = ",".join("?" * len(ids))
    out = set()
    with db.connect() as conn:
        for r in conn.execute("SELECT codes FROM selections WHERE code_id IN (%s)" % marks, ids):
            try:
                out.update(json.loads(r["codes"] or "[]"))
            except ValueError:
                pass
        for r in conn.execute("SELECT c.code FROM campaign_creators c JOIN campaigns k ON k.id = c.campaign_id "
                              "WHERE k.code_id IN (%s)" % marks, ids):
            if r["code"]:
                out.add(r["code"])
    return frozenset(str(c).upper() for c in out)


# -------------------------------------------------------- thread scope --

def begin(scope):
    """Per admin request: None (everything) or the KAM's client code ids."""
    _t.scope = scope
    _t.creators = None


def end():
    _t.scope = None
    _t.creators = None


def current():
    return getattr(_t, "scope", None)


def current_creators():
    s = current()
    if s is None:
        return None
    if getattr(_t, "creators", None) is None:
        _t.creators = creators(s)
    return _t.creators


def allows(code_id, scope="__current__"):
    s = current() if scope == "__current__" else scope
    if s is None:
        return True
    try:
        return code_id is not None and int(code_id) in s
    except (TypeError, ValueError):
        return False


def keep(rows, key="code_id"):
    """Rows whose ``key`` is one of the current KAM's clients (all rows when unscoped)."""
    s = current()
    if s is None:
        return rows
    return [r for r in rows if allows(_get(r, key), s)]


# ------------------------------------------------------------ resolvers --

def _int(v):
    v = str(v if v is not None else "").strip()
    return int(v) if v.isdigit() else None


def _one(sql, args):
    import db
    with db.connect() as conn:
        r = conn.execute(sql, args).fetchone()
    return r[0] if r is not None else None


def selection_code(sid):
    """(found, code_id) for a selection id."""
    import db
    sel = db.selection(sid) if sid is not None else None
    return (sel is not None, sel["code_id"] if sel is not None else None)


def campaign_code(cid):
    """(found, code_id): the campaign's client, else the client of the selection it came from."""
    import db
    k = db.campaign(cid) if cid is not None else None
    if k is None:
        return False, None
    if k["code_id"] is not None:
        return True, k["code_id"]
    if k["selection_id"]:
        return True, selection_code(k["selection_id"])[1]
    return True, None


def evidence_code(pid):
    """(found, code_id) for a competitor evidence pack."""
    import evidence
    return evidence.pack_code(pid)


def user_code(uid):
    if uid is None:
        return False, None
    import db
    with db.connect() as conn:
        r = conn.execute("SELECT code_id FROM users WHERE id = ?", (uid,)).fetchone()
    return (r is not None, r["code_id"] if r is not None else None)


def _row_code(table, rid):
    if rid is None:
        return False, None
    import db
    with db.connect() as conn:
        r = conn.execute("SELECT code_id FROM %s WHERE id = ?" % table, (rid,)).fetchone()
    return (r is not None, r["code_id"] if r is not None else None)


def source_ok(src, scope):
    """A "selection:ID" or "campaign:ID" source param (analysis and planner pages)."""
    src = str(src or "").strip()
    if src.startswith("selection:"):
        return allows(selection_code(_int(src[10:]))[1], scope)
    if src.startswith("campaign:"):
        return allows(campaign_code(_int(src[9:]))[1], scope)
    return True


# ------------------------------------------------------------- the gate --

# GET pages a KAM opens with no client id in them (their lists are filtered at the source).
_GET_FREE = {"/", "/reauth", "/selections", "/campaigns", "/clients", "/clients/preview/exit", "/requests",
             "/api/pulse", "/api/search", "/codes", "/open-catalogue", "/roster", "/roster/export",
             "/roster/template.xlsx", "/roster/template", "/licences", "/analysis", "/analysis/find",
             "/analysis/template.xlsx", "/campaigns/thumb", "/campaigns/logo", "/calculator", "/ai",
             "/ai/history", "/selections/suggest", "/team", "/evidence"}
_GET_SELECTION = {"/selections/edit": "id", "/selections/fit": "id", "/campaigns/setup": "selection", "/portal/quote": "sel"}
_GET_CAMPAIGN = {"/campaigns/content", "/campaigns/report", "/campaigns/insights", "/campaigns/export.xlsx",
                 "/campaigns/export.csv", "/campaigns/insight-file", "/campaigns/links", "/campaigns/clicks.csv",
                 "/campaigns/edit"}
_PORTAL_TABS = {"accounts", "briefs", "chats"}

# POSTs with no client in them that a KAM may still make: herself, the copilot's read-only chat, creators.
_POST_FREE = {"/reauth", "/password", "/ai/chat", "/ai/dismiss", "/roster/save", "/roster/bulk", "/licences/save",
              "/licences/scan"}
_POST_SELECTION = {"/selections/save", "/selections/delete", "/selections/status", "/quote/ready", "/quote/withdraw"}
_POST_CAMPAIGN = {"/campaigns/save", "/campaigns/status", "/campaigns/delete", "/campaigns/link",
                  "/campaigns/content/add", "/campaigns/content/update", "/campaigns/content/bulk",
                  "/campaigns/content/pending", "/campaigns/insights/decide", "/campaigns/insights/upload",
                  "/campaigns/sync", "/campaigns/link/custom", "/campaigns/link/toggle", "/planner/apply",
                  "/calculator/save", "/calculator/results"}
_POST_CODE = {"/codes/revoke", "/codes/restore", "/codes/archive", "/codes/unarchive", "/codes/passcode",
              "/codes/rename", "/codes/limits", "/clients/preview"}
_POST_USER = {"/portal/user/status", "/portal/user/credits", "/portal/user/save"}


def check(scope, method, path, query=None, form=None):
    """None when the request may go ahead for this scope, else the reason (shown on a 403).
    ``scope`` None means unscoped (owner, admin, viewer): always None."""
    if scope is None:
        return None
    query = query or {}
    form = form or {}

    def code_ok(found_code):
        found, code_id = found_code
        return found and allows(code_id, scope)

    if method == "GET":
        if path == "/portal":
            return None if (query.get("tab") or "accounts") in _PORTAL_TABS else NOT_YOURS
        if path in _GET_FREE:
            if path == "/calculator" and query.get("id"):
                return None if code_ok(campaign_code(_int(query.get("id")))) else NOT_YOURS
            if path == "/analysis/find" and not source_ok(query.get("source"), scope):
                return NOT_YOURS
            return None
        if path in _GET_SELECTION:
            return None if code_ok(selection_code(_int(query.get(_GET_SELECTION[path])))) else NOT_YOURS
        if path in _GET_CAMPAIGN:
            return None if code_ok(campaign_code(_int(query.get("id")))) else NOT_YOURS
        if path == "/planner":
            if query.get("id") and not code_ok(campaign_code(_int(query.get("id")))):
                return NOT_YOURS
            return None if source_ok(query.get("source"), scope) else NOT_YOURS
        if path == "/portal/user":
            return None if code_ok(user_code(_int(query.get("id")))) else NOT_YOURS
        if path == "/evidence/view":
            return None if code_ok(evidence_code(_int(query.get("id")))) else NOT_YOURS
        if path == "/portal/chat":
            return None if code_ok(_row_code("chat_threads", _int(query.get("id")))) else NOT_YOURS
        if path == "/analysis/json":
            code = str(query.get("c") or "").strip().upper()
            return None if code and code in (creators(scope) or ()) else NOT_YOURS
        return NOT_YOURS

    # POST
    if path in _POST_FREE or path.startswith("/account/2fa/"):
        return None
    if path in _POST_SELECTION:
        if not code_ok(selection_code(_int(form.get("id")))):
            return NOT_YOURS
        return None
    if path in _POST_CAMPAIGN:
        if not code_ok(campaign_code(_int(form.get("id")))):
            return NOT_YOURS
        if path == "/campaigns/save" and (form.get("code_id") or "").strip() and not allows(_int(form.get("code_id")), scope):
            return NOT_YOURS
        return None
    if path in _POST_CODE:
        cid = _int(form.get("id"))
        return None if cid is not None and allows(cid, scope) else NOT_YOURS
    if path == "/codes/device/remove":
        return None if code_ok(_row_code("code_devices", _int(form.get("id")))) else NOT_YOURS
    if path in _POST_USER:
        return None if code_ok(user_code(_int(form.get("id")))) else NOT_YOURS
    if path == "/portal/credit-request":
        return None if code_ok(_row_code("credit_requests", _int(form.get("id")))) else NOT_YOURS
    if path == "/portal/code/credits":
        return None if allows(_int(form.get("code_id")), scope) else NOT_YOURS
    if path == "/archive":
        kind, rid = form.get("kind"), _int(form.get("id"))
        if kind == "client":
            return None if allows(rid, scope) else NOT_YOURS
        if kind == "selection":
            return None if code_ok(selection_code(rid)) else NOT_YOURS
        return NOT_YOURS
    if path == "/selections/new":
        # A KAM files every new selection under one of her clients, or she would lose sight of it:
        # from scratch with her client chosen, from her client's campaign, or from her client's request.
        mode = form.get("mode")
        if mode == "scratch":
            return None if allows(_int(form.get("code_id")), scope) else NOT_YOURS
        if mode == "from_campaign":
            return None if code_ok(campaign_code(_int(form.get("campaign")))) else NOT_YOURS
        if (form.get("request") or "").strip():
            return None if code_ok(_row_code("requests", _int(form.get("request")))) else NOT_YOURS
        return NOT_YOURS
    if path == "/campaigns/new":
        if not allows(_int(form.get("code_id")), scope):
            return NOT_YOURS
        if (form.get("selection") or "").strip() and not code_ok(selection_code(_int(form.get("selection")))):
            return NOT_YOURS
        return None
    if path == "/campaigns/setup":
        return None if code_ok(selection_code(_int(form.get("selection")))) else NOT_YOURS
    if path in ("/selections/assign", "/campaigns/assign"):
        found = selection_code(_int(form.get("id"))) if path == "/selections/assign" else campaign_code(_int(form.get("id")))
        if not code_ok(found) or not allows(_int(form.get("client")), scope):
            return NOT_YOURS
        return None
    if path.startswith("/evidence/"):
        # Competitor evidence: a pack of her client's, filed (if at all) under that client's selection.
        pid = _int(form.get("pack_id") or form.get("id"))
        if pid is not None:
            if not code_ok(evidence_code(pid)):
                return NOT_YOURS
        elif path != "/evidence/import" or not allows(_int(form.get("code_id")), scope):
            return NOT_YOURS
        sid = _int(form.get("selection_id"))
        if sid is not None and not code_ok(selection_code(sid)):
            return NOT_YOURS
        return None
    if path in ("/analysis/fulfil", "/analysis/handled"):
        return None if code_ok(_row_code("analysis_requests", _int(form.get("id")))) else NOT_YOURS
    if path == "/requests/handled":
        return None if code_ok(_row_code("requests", _int(form.get("id")))) else NOT_YOURS
    if path == "/analysis/save":
        code = str(form.get("code") or "").strip().upper()
        return None if code and code in (creators(scope) or ()) else NOT_YOURS
    if path in ("/analysis/template", "/analysis/find"):
        return None if source_ok(form.get("source"), scope) else NOT_YOURS
    return NOT_YOURS


# ------------------------------------------------------- domain -> KAM --

def set_domain_map(mapping, by=""):
    """Save {domain: kam email} and bring users.kam in line for every account on those domains.
    Returns (saved mapping, accounts updated)."""
    import db
    clean = {}
    for d, k in (mapping or {}).items():
        d, k = _norm(d).lstrip("@"), _norm(k)
        if d and k and "." in d and "@" in k:
            clean[d] = k
    db.set_setting("domain_kam", clean)
    n = 0
    with db.connect() as conn:
        for d, k in clean.items():
            n += conn.execute("UPDATE users SET kam = ? WHERE LOWER(domain) = ? AND deleted_at IS NULL "
                              "AND COALESCE(LOWER(kam), '') != ?", (k, d, k)).rowcount
    return clean, n


# -------------------------------------------------------- My clients --

def _counts_for(sel):
    import selstatus
    codes = json.loads(sel["codes"] or "[]")
    st = selstatus.of(sel["id"])
    n = {"creators": len(codes), "approved": 0, "rejected": 0, "review": 0, "unavailable": 0}
    for c in codes:
        s = (st.get(c) or {}).get("s", "review")
        if s in n:
            n[s] += 1
    return n


def my_clients(email, name=None, admin_base=""):
    """The portal "My clients" page: one card per client account of this KAM. No cost, margin or
    price ever leaves here (pricing stays in the admin)."""
    import db
    import lifecycle
    import metrics
    import portal
    out = []
    for u in user_rows(email, name):
        cid = u["code_id"]
        if cid is None:
            continue
        codes = {cid}
        try:
            import codelinks
            codes |= codelinks.linked_for({cid})
        except Exception:
            pass
        ids = sorted(codes)
        marks = ",".join("?" * len(ids))
        with db.connect() as conn:
            sels = conn.execute("SELECT * FROM selections WHERE code_id IN (%s) AND archived_at IS NULL AND deleted_at IS NULL "
                                "ORDER BY updated_at DESC LIMIT 30" % marks, ids).fetchall()
            camps = conn.execute("SELECT * FROM campaigns WHERE code_id IN (%s) ORDER BY "
                                 "CASE status WHEN 'live' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END, COALESCE(starts_at, 0) DESC, id DESC "
                                 "LIMIT 20" % marks, ids).fetchall()
            areq = conn.execute("SELECT a.id, a.code, a.platform, a.at, a.handled_at, r.name creator FROM analysis_requests a "
                                "LEFT JOIN creators r ON r.code = a.code WHERE a.code_id IN (%s) ORDER BY a.at DESC LIMIT 40" % marks,
                                ids).fetchall()
            chats = conn.execute("SELECT COUNT(*) FROM chat_threads t WHERE t.code_id = ? AND t.scope = 'client' "
                                 "AND EXISTS (SELECT 1 FROM chat_messages m WHERE m.thread_id = t.id)", (cid,)).fetchone()[0]
            handoffs = conn.execute("SELECT COUNT(*) FROM events WHERE code_id = ? AND kind = 'request' "
                                    "AND detail IN ('chat handoff', 'voice handoff')", (cid,)).fetchone()[0]
        selections = []
        for s in sels:
            selections.append({"name": s["name"], "token": s["token"], "updated_at": s["updated_at"],
                               "quote": lifecycle.chip(s), "counts": _counts_for(s),
                               "admin": admin_base + "/selections/edit?id=%d" % s["id"]})
        campaigns = []
        for k in camps:
            try:
                rep = metrics.report(k)
                t = rep["total"] if rep else {}
            except Exception:
                t = {}
            campaigns.append({"name": k["name"], "token": k["token"], "status": k["status"],
                              "starts_at": k["starts_at"], "ends_at": k["ends_at"],
                              "posts": t.get("delivered") or 0, "planned": t.get("planned") or 0,
                              "views": t.get("views") or 0,
                              "admin": admin_base + "/campaigns/edit?id=%d" % k["id"]})
        now = db.now()
        analyses = []
        for a in areq:
            done = a["handled_at"] is not None
            due = a["at"] + 86400 * (3 if time_weekday(a["at"]) == 3 else 1)   # 1 working day (Thu -> Sun)
            analyses.append({"code": a["code"], "name": a["creator"] or a["code"], "platform": a["platform"] or "",
                             "at": a["at"], "state": "delivered" if done else ("late" if now > due else "waiting"),
                             "due": due})
        out.append({
            "id": u["id"], "name": u["name"] or "", "email": u["email"], "company": u["company"] or "",
            "domain": u["domain"] or "", "status": u["status"],
            "last_login_at": u["last_login_at"], "credits": portal.balance(cid),
            "chats": chats, "handoffs": handoffs,
            "selections": selections, "campaigns": campaigns,
            "analyses": {"requested": len(analyses), "delivered": sum(1 for a in analyses if a["state"] == "delivered"),
                         "waiting": sum(1 for a in analyses if a["state"] != "delivered"),
                         "late": sum(1 for a in analyses if a["state"] == "late"), "items": analyses[:12]},
            "admin": admin_base + "/portal/user?id=%d" % u["id"],
        })
    return out


def time_weekday(ts):
    """0 = Monday ... 6 = Sunday, UTC (Riyadh's working week runs Sunday to Thursday)."""
    import time as _time
    return _time.gmtime(ts).tm_wday
