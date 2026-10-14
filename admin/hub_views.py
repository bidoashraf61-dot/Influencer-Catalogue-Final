"""Control Centre step 4 (item 101): one Clients page (company accounts and access codes together, with a side
panel per client) and one board for selections and campaigns (Draft -> Quote requested -> Quote ready -> Approved
-> Campaign live -> Completed). Lists come from the same scoped queries as the old pages, so a key account
manager still sees her own clients only. Every value goes through e()."""
import json
import urllib.parse

import db
import lifecycle
import portal
import ui
from views import ago, e, page, u

TEAM_DOMAINS = portal.SAMPLE_DOMAINS
STATUS = {"active": ("Active", "ok"), "pending": ("Waiting", "wait"), "suspended": ("Suspended", "off")}

CSS = ("<style>"
       ".hb-top{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:18px}"
       ".hb-top h1{font-family:'Bebas Neue',sans-serif;font-weight:400;font-size:clamp(38px,4.6vw,54px);line-height:.92;margin:0}"
       ".hb-top p{margin:8px 0 0;color:var(--gray);max-width:64ch}.hb-btns{display:flex;gap:8px;flex-wrap:wrap}"
       ".hb-bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:14px}"
       ".hb-seg{display:inline-flex;background:var(--white);border:1px solid var(--line-strong);border-radius:999px;padding:3px;gap:2px;flex-wrap:wrap}"
       ".hb-seg a{border-radius:999px;padding:7px 14px;font-weight:600;font-size:13px;text-decoration:none;color:var(--ink)}"
       ".hb-seg a[aria-current=true]{background:var(--ink)!important;color:var(--lime)!important;opacity:1}.hb-seg a b{margin-left:6px;opacity:.7}"
       ".hb-find{flex:1;min-width:220px;display:flex;align-items:center;gap:10px;background:var(--white);border:1px solid var(--line-strong);border-radius:999px;padding:0 16px;min-height:44px}"
       ".hb-find input{border:0;outline:0;flex:1;font:15px 'DM Sans',sans-serif;background:transparent;min-height:40px;padding:0}"
       ".hb-list{background:var(--white);border:1px solid var(--line);border-radius:18px}"
       ".hb-cl{display:grid;grid-template-columns:44px minmax(0,1.6fr) 120px 90px 150px 110px auto;gap:14px;align-items:center;padding:13px 18px;border-bottom:1px solid var(--line)}"
       ".hb-cl:last-child{border-bottom:0}.hb-cl.head{font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;padding:10px 18px}"
       ".hb-av{width:40px;height:40px;border-radius:12px;background:var(--linen);display:grid;place-items:center;font-family:'Bebas Neue',sans-serif;font-size:18px}"
       ".hb-who b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.hb-who span{display:block;font-size:13px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"
       ".hb-st{display:inline-flex;font-size:12.5px;font-weight:700;border-radius:999px;padding:3px 10px;white-space:nowrap}"
       ".hb-st.ok{background:var(--green-soft);color:var(--green)}.hb-st.wait{background:var(--amber-soft);color:var(--amber)}"
       ".hb-st.off{background:var(--red-soft);color:var(--red)}.hb-st.team{background:var(--blue-soft);color:var(--blue)}.hb-st.code{background:#ece9e3;color:var(--ink)}"
       ".hb-num{font-variant-numeric:tabular-nums}.hb-mut{color:var(--muted);font-size:13px}"
       ".hb-acts{display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap}.hb-acts form{margin:0}"
       ".hb-panel{position:fixed;top:0;right:0;bottom:0;width:min(470px,100%);background:var(--white);box-shadow:-24px 0 60px -24px rgba(0,0,0,.4);display:flex;flex-direction:column;z-index:60}"
       ".hb-ph{padding:18px 20px;border-bottom:1px solid var(--line);display:flex;gap:14px;align-items:center}"
       ".hb-ph h2{font-family:'Bebas Neue',sans-serif;font-weight:400;font-size:28px;line-height:1;margin:0}.hb-ph span{font-size:13px;color:var(--muted)}"
       ".hb-x{margin-left:auto;width:36px;height:36px;border-radius:50%;border:1px solid var(--line-strong);background:var(--white);display:grid;place-items:center;text-decoration:none;color:var(--ink);flex:none}"
       ".hb-pb{padding:18px 20px;overflow:auto;flex:1;display:flex;flex-direction:column;gap:16px}"
       ".hb-kv{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.hb-kv div{background:var(--paper);border-radius:12px;padding:10px 12px}"
       ".hb-kv b{display:block;font-family:'Bebas Neue',sans-serif;font-weight:400;font-size:26px;line-height:1}.hb-kv span{font-size:12px;color:var(--muted)}"
       ".hb-sec h3{margin:0 0 8px;font-size:12.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}"
       ".hb-mini{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 0;border-top:1px solid var(--line);font-size:14px}"
       ".hb-mini:first-of-type{border-top:0}.hb-mini a{color:var(--ink)}"
       ".hb-credit{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0}.hb-credit input{width:90px}"
       ".hb-pf{display:flex;gap:8px;flex-wrap:wrap;margin-top:auto;padding-top:8px}.hb-pf form{margin:0}"
       ".hb-board{display:grid;grid-template-columns:repeat(6,minmax(210px,1fr));gap:12px;overflow-x:auto;padding-bottom:10px}"
       ".hb-col{background:#ece8e1;border-radius:16px;padding:10px;min-height:360px}"
       ".hb-col h3{display:flex;justify-content:space-between;align-items:center;margin:4px 6px 10px;font-family:'Bebas Neue',sans-serif;font-weight:400;font-size:20px;line-height:1}"
       ".hb-col h3 i{font:700 12px 'DM Sans',sans-serif;font-style:normal;background:var(--white);border-radius:999px;padding:2px 8px}"
       ".hb-col.hot{background:var(--ink)}.hb-col.hot h3{color:#fff}.hb-col.hot h3 i{background:var(--lime)}"
       ".hb-card{background:var(--white);border-radius:12px;padding:12px;margin-bottom:8px;border:1px solid transparent;display:block;text-decoration:none;color:var(--ink)}"
       ".hb-card:hover{border-color:var(--ink)}.hb-card b{display:block;font-size:14px;line-height:1.3}"
       ".hb-card .c{font-size:12.5px;color:var(--muted);margin:2px 0 8px}.hb-card .r{display:flex;justify-content:space-between;gap:8px;font-size:12.5px}"
       ".hb-card .r em{font-style:normal;font-weight:700}.hb-card .nx{margin-top:8px;font-size:12px;font-weight:700;color:var(--amber)}.hb-card .nx.go{color:var(--green)}"
       ".hb-card .nx.calm{color:var(--muted);font-weight:600}.hb-more{display:block;text-align:center;font-size:13px;margin-top:6px}"
       ".hb-empty{font-size:13px;color:var(--muted);margin:6px}.hb-legend{font-size:13px;color:var(--muted);margin:10px 2px 0}"
       "@media (max-width:900px){.hb-cl{grid-template-columns:40px minmax(0,1fr) auto}.hb-cl .hs{display:none}.hb-cl.head{display:none}"
       ".hb-cl .hb-acts{grid-column:2/-1;justify-content:flex-start}}"
       "</style>")

_FIND_JS = ("<script>(function(){var q=document.getElementById('hb-q');if(!q)return;var items=[].slice.call(document.querySelectorAll('[data-find]'));"
            "q.addEventListener('input',function(){var v=q.value.trim().toLowerCase();items.forEach(function(x){x.hidden=!!v&&x.getAttribute('data-find').indexOf(v)<0;});});})();</script>")


def _ini(text):
    parts = [w for w in str(text or "?").replace("@", " ").split() if w[:1].isalnum()][:2]
    return "".join(w[0] for w in parts).upper() or "?"


def _is_team(email):
    return (email or "").rsplit("@", 1)[-1].lower() in TEAM_DOMAINS


def client_rows():
    """Company accounts and the access codes nobody's account owns, as one list (scoped for KAMs)."""
    users = portal.list_users()
    owned = {r["code_id"] for r in users if r["code_id"]}
    rows = []
    for r in users:
        team = _is_team(r["email"])
        lab, tone = STATUS.get(r["status"], (r["status"], "code"))
        if team and r["status"] == "active":
            lab, tone = "Team", "team"
        rows.append({"key": "u%d" % r["id"], "kind": "account", "id": r["id"], "code_id": r["code_id"],
                     "name": r["name"] or r["email"].split("@")[0], "company": r["company"] or "", "email": r["email"],
                     "status": r["status"], "label": lab, "tone": tone, "team": team, "kam": (r["kam"] if "kam" in r.keys() else "") or "",
                     "credits": r["credits"], "selections": r["selections"], "campaigns": r["campaigns"],
                     "seen": r["last_login_at"], "created": r["created_at"]})
    admin_id = db.admin_code_id()
    for c in db.list_codes():
        if c["id"] in owned or c["id"] == admin_id or c["archived_at"]:
            continue
        ok, why = db.code_state(c)
        rows.append({"key": "c%d" % c["id"], "kind": "code", "id": c["id"], "code_id": c["id"], "name": _clean_label(c["label"]) or "Access code",
                     "company": "", "email": "", "status": "active" if ok else "suspended", "label": "Access code" if ok else why.capitalize(),
                     "tone": "code" if ok else "off", "team": False, "kam": "", "credits": portal.balance(c["id"]),
                     "selections": c["n_selections"], "campaigns": c["n_campaigns"], "seen": c["last_used"], "created": c["created_at"],
                     "devices": c["devices"], "hint": c["hint"]})
    return rows


def _filter(rows, show):
    if show == "waiting":
        return [r for r in rows if r["status"] == "pending"]
    if show == "active":
        return [r for r in rows if r["status"] == "active" and not r["team"]]
    if show == "team":
        return [r for r in rows if r["team"]]
    if show == "suspended":
        return [r for r in rows if r["status"] == "suspended"]
    return rows


def clients_page(show="all", open_key=None, ok=None, err=None):
    rows = client_rows()
    rows.sort(key=lambda r: (r["status"] != "pending", r["team"], -(r["seen"] or r["created"] or 0)))
    counts = {k: len(_filter(rows, k)) for k in ("all", "waiting", "active", "team", "suspended")}
    show = show if show in counts else "all"
    seg = "".join("<a href='%s'%s>%s<b>%d</b></a>" % (u("/clients") + ("?show=" + k if k != "all" else ""), " aria-current='true'" if k == show else "", lab, counts[k])
                  for k, lab in (("all", "All"), ("waiting", "Waiting"), ("active", "Active"), ("team", "Team"), ("suspended", "Suspended")))
    hid = lambda n, v: "<input type='hidden' name='%s' value='%s'>" % (n, e(v))
    back = "/clients" + ("?show=" + show if show != "all" else "")
    items = ""
    for r in _filter(rows, show):
        sub = " · ".join(x for x in (r["company"], r["email"]) if x) if r["kind"] == "account" else "Access code · %d device%s" % (
            r["devices"], "" if r["devices"] == 1 else "s")
        if r["kam"]:
            sub += " · KAM: " + r["kam"]
        acts = ""
        if r["kind"] == "account" and r["status"] == "pending":
            acts += ("<form method='post' action='%s'>%s%s%s<button class='btn small lime'>Approve</button></form>" % (
                u("/portal/user/status"), hid("id", r["id"]), hid("status", "active"), hid("back", back)))
        open_href = u("/clients") + "?" + urllib.parse.urlencode(dict(([("show", show)] if show != "all" else []) + [("open", r["key"])]))
        acts += "<a class='btn small ghost' href='%s'>Open</a>" % open_href
        live = r["campaigns"] or 0
        items += ("<div class='hb-cl' data-find='%s'><div class='hb-av'>%s</div><div class='hb-who'><b>%s</b><span>%s</span></div>"
                  "<span><span class='hb-st %s'>%s</span></span><span class='hb-num hs'>%s</span><span class='hs'>%d · %d</span>"
                  "<span class='hs hb-mut'>%s</span><div class='hb-acts'>%s</div></div>") % (
            e((r["name"] + " " + r["company"] + " " + r["email"]).lower()), e(_ini(r["company"] or r["name"])), e(r["name"]), e(sub),
            r["tone"], e(r["label"]), e("{:,}".format(r["credits"])) if r["credits"] is not None else "—", r["selections"] or 0, live,
            e(ago(r["seen"])) if r["seen"] else "Never", acts)
    if not items:
        items = "<p class='hb-empty' style='padding:16px'>No clients here.</p>"
    head = ("<div class='hb-top'><div><h1>Clients</h1><p>Everyone who can open the catalogue, in one list: company accounts and access codes. "
            "Open a client to approve, add credits, see their selections and campaigns, or view the catalogue as them.</p></div>"
            "<div class='hb-btns'><a class='btn ghost' href='" + u("/codes") + "#new'>New access code</a>"
            "<a class='btn lime' href='" + u("/portal") + "?tab=settings'>Sign-up settings</a></div></div>")
    bar = ("<div class='hb-bar'><nav class='hb-seg' aria-label='Show'>" + seg + "</nav>"
           "<label class='hb-find'>" + ui.icon("search", 18) + "<input id='hb-q' placeholder='Find a client, company or email' aria-label='Find a client'></label></div>")
    table = ("<div class='hb-list'><div class='hb-cl head'><span></span><span>Client</span><span>Status</span><span class='hs'>Credits</span>"
             "<span class='hs'>Selections · campaigns</span><span class='hs'>Last seen</span><span></span></div>" + items + "</div>")
    panel = ""
    if open_key:
        r = next((x for x in rows if x["key"] == open_key), None)
        if r is not None:
            panel = _panel(r, back)
    banner = (("<div class='ok'>" + e(ok) + "</div>") if ok else "") + (("<div class='err'>" + e(err) + "</div>") if err else "")
    return page("Clients", CSS + head + banner + bar + table + panel + _FIND_JS, "/clients")


def _panel(r, back):
    hid = lambda n, v: "<input type='hidden' name='%s' value='%s'>" % (n, e(v))
    me = back + ("&" if "?" in back else "?") + "open=" + r["key"]
    with db.connect() as conn:
        sels = conn.execute("SELECT * FROM selections WHERE code_id = ? AND archived_at IS NULL AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT 8",
                            (r["code_id"],)).fetchall() if r["code_id"] else []
        dev = conn.execute("SELECT COUNT(*) FROM code_devices WHERE code_id = ?", (r["code_id"],)).fetchone()[0] if r["code_id"] else 0
        code = conn.execute("SELECT * FROM codes WHERE id = ?", (r["code_id"],)).fetchone() if r["code_id"] else None
    tone = {"draft": "", "requested": "wait", "ready": "wait", "approved": "ok", "live": "ok", "completed": "code"}
    from views import open_link
    sel_html = "".join("<div class='hb-mini'><a href='%s'>%s</a><span style='display:flex;gap:8px;align-items:center'>%s<span class='hb-st %s'>%s</span></span></div>" % (
        u("/selections/edit") + "?id=%d" % s["id"], e(s["name"]), open_link("selection", s["token"], "Client view", "hb-mut"), tone.get(ch["key"], ""), e(ch["label"]))
        for s in sels for ch in [lifecycle.chip(s)]) or "<p class='hb-mut' style='margin:0'>No selections yet.</p>"
    live = sum(1 for s in sels if lifecycle.chip(s)["key"] == "live")
    kv = ("<div class='hb-kv'><div><b>%s</b><span>AI credits</span></div><div><b>%d</b><span>selection%s</span></div><div><b>%d</b><span>campaign%s live</span></div></div>" % (
        "{:,}".format(r["credits"]) if r["credits"] is not None else "—", r["selections"] or 0, "" if (r["selections"] or 0) == 1 else "s", live, "" if live == 1 else "s"))
    credits = ""
    status_btns = ""
    if r["kind"] == "account":
        credits = ("<div class='hb-sec'><h3>Credits</h3><form method='post' action='%s' class='hb-credit'>%s%s%s"
                   "<input name='amount' type='number' value='20' aria-label='Credits to add'><button class='btn small lime'>Add credits</button>"
                   "<span class='hb-mut'>Use a minus number to take credits away. Asks you to confirm.</span></form></div>") % (
            u("/portal/user/credits"), hid("id", r["id"]), hid("reason", "Added from the Clients page"), hid("back", me))
        for st, lab, cls in (("active", "Approve" if r["status"] == "pending" else "Make active", "lime"), ("pending", "Hold", "ghost"),
                             ("suspended", "Suspend", "ghost danger")):
            if st != r["status"]:
                status_btns += ("<form method='post' action='%s'%s>%s%s%s<button class='btn small %s'>%s</button></form>") % (
                    u("/portal/user/status"), " onsubmit=\"return confirm('Suspend this client? They lose access at once.')\"" if st == "suspended" else "",
                    hid("id", r["id"]), hid("status", st), hid("back", me), cls, lab)
    access = "<div class='hb-sec'><h3>Access</h3>"
    if code is not None:
        ok_, why = db.code_state(code)
        access += "<div class='hb-mini'><span>Access code</span><span class='hb-mut'>…%s · %s · %d device%s</span></div>" % (
            e(code["hint"] or ""), "works" if ok_ else e(why), dev, "" if dev == 1 else "s")
    if r["kind"] == "account":
        access += "<div class='hb-mini'><span>Key account manager</span><span>%s</span></div>" % e(r["kam"] or "None")
        access += "<div class='hb-mini'><span>Joined</span><span class='hb-mut'>%s</span></div>" % e(ago(r["created"]))
    access += "<div class='hb-mini'><a href='%s'>%s</a><span class='hb-mut'>All details</span></div></div>" % (
        u("/portal/user") + "?id=%d" % r["id"] if r["kind"] == "account" else u("/codes") + "#c%d" % r["id"],
        "Open the full account page" if r["kind"] == "account" else "Manage this access code")
    preview = ("<form method='post' action='%s'>%s<button class='btn small'>View the catalogue as them</button></form>" % (
        u("/clients/preview"), hid("id", r["code_id"]))) if r["code_id"] else ""
    sub = " · ".join(x for x in (r["company"], r["email"]) if x) or "Access code"
    return ("<aside class='hb-panel' aria-label='Client'><div class='hb-ph'><div class='hb-av'>%s</div><div><h2>%s</h2><span>%s</span></div>"
            "<a class='hb-x' href='%s' aria-label='Close'>✕</a></div><div class='hb-pb'>"
            "<div><span class='hb-st %s'>%s</span></div>%s%s<div class='hb-sec'><h3>Selections</h3>%s</div>%s"
            "<div class='hb-pf'>%s%s</div></div></aside>"
            "<script>document.addEventListener('keydown',function(ev){if(ev.key==='Escape')location.href=%s;});</script>") % (
        e(_ini(r["company"] or r["name"])), e(r["name"]), e(sub), u(back), r["tone"], e(r["label"]), kv, credits, sel_html, access,
        preview, status_btns, json.dumps(u(back)))


# ------------------------------------------------------------------- board --

COLUMNS = [("draft", "Draft"), ("requested", "Quote requested"), ("ready", "Quote ready"), ("approved", "Approved"),
           ("live", "Campaign live"), ("completed", "Completed")]


def _clean_label(label):
    label = (label or "").strip()
    return label[len("Client: "):] if label.startswith("Client: ") else label


def _team_label(label):
    lab = (label or "").lower()
    return "admin preview" in lab or any(("@" + d) in lab for d in TEAM_DOMAINS)


def board_cards(team=False):
    """Every open selection on its lifecycle step, plus campaigns started without a selection (scoped for KAMs)."""
    import overview
    progress = {c["id"]: c for c in overview.live_campaigns()}
    cards = {k: [] for k, _ in COLUMNS}
    linked = set()
    for s in db.list_selections():
        if s["archived_at"] or ("deleted_at" in s.keys() and s["deleted_at"]):
            continue
        st = lifecycle.state_of(s)
        k = st["key"]
        n = len(json.loads(s["codes"] or "[]"))
        if not team and _team_label(s["code_label"]):
            continue                                   # the team's own tests stay out of the board unless asked
        client = _clean_label(s["code_label"]) or "No client yet"
        price = ("SAR {:,}".format(int(s["total_from"])) + ("–{:,}".format(int(s["total_to"])) if s["total_to"] and s["total_to"] != s["total_from"] else "")) \
            if s["total_from"] else "—"
        href = u("/selections/edit") + "?id=%d" % s["id"]
        when = st.get("requested_at") if k == "requested" else s["updated_at"]
        nxt, tone = "", ""
        if k == "draft":
            nxt = "Assign a client" if not s["code_id"] else ("Set prices" if not s["total_from"] else "Shared with the client")
            tone = "" if nxt != "Shared with the client" else "calm"
        elif k == "requested":
            nxt = "Price and send the quote"
        elif k == "ready":
            nxt, tone = "Waiting for the client", "calm"
        elif k == "approved":
            nxt, tone = "Start the campaign", "go"
        camp = st.get("campaign")
        for c in st.get("campaigns") or []:
            linked.add(c["id"])
        if k in ("live", "completed") and camp:
            cid = next((c["id"] for c in st["campaigns"] if c["token"] == camp["token"]), None)
            href = u("/campaigns/report") + "?id=%d" % cid if cid else href
            p = progress.get(cid)
            if k == "live" and p:
                gap = (p["planned"] or 0) - p["posts"]
                nxt, tone = ("%d post%s still to come" % (gap, "" if gap == 1 else "s"), "") if gap > 0 else ("Report", "go")
                price = "%d of %d posts" % (p["posts"], p["planned"] or p["posts"])
            else:
                nxt, tone = "Report", "go" if k == "live" else "calm"
        cards[k].append({"name": s["name"], "client": client, "n": n, "price": price, "next": nxt, "tone": tone, "href": href,
                         "when": when or 0, "find": (s["name"] + " " + client).lower()})
    for c in db.list_campaigns():
        if c["id"] in linked or ("archived_at" in c.keys() and c["archived_at"]):
            continue
        k = {"draft": "approved", "live": "live", "ended": "completed"}.get(c["status"])
        if not k:
            continue
        if not team and _team_label(c["code_label"] if "code_label" in c.keys() else ""):
            continue
        client = c["client"] or _clean_label(c["code_label"] if "code_label" in c.keys() else "") or "No client"
        p = progress.get(c["id"])
        nxt, tone, info = ("Finish setup", "", "%d creators" % (c["creators"] or 0)) if k == "approved" else ("Report", "go" if k == "live" else "calm", "")
        if p:
            gap = (p["planned"] or 0) - p["posts"]
            info = "%d of %d posts" % (p["posts"], p["planned"] or p["posts"])
            if gap > 0:
                nxt, tone = "%d post%s still to come" % (gap, "" if gap == 1 else "s"), ""
        href = u("/campaigns/edit") + "?id=%d" % c["id"] if k == "approved" else u("/campaigns/report") + "?id=%d" % c["id"]
        cards[k].append({"name": c["name"], "client": client, "n": c["creators"] or 0, "price": info or "Campaign", "next": nxt, "tone": tone,
                         "href": href, "when": c["updated_at"] or 0, "find": (c["name"] + " " + client).lower()})
    for k in cards:
        cards[k].sort(key=lambda x: -(x["when"] or 0))
    return cards


def board_page(ok=None, err=None, team=False):
    cards = board_cards(team)
    cols = ""
    for k, lab in COLUMNS:
        lst = cards[k]
        shown = lst[:12] if k == "completed" else lst
        html = "".join(
            "<a class='hb-card' href='%s' data-find='%s'><b>%s</b><div class='c'>%s%s</div><div class='r'><span>%s</span><em>%s</em></div>%s</a>" % (
                e(c["href"]), e(c["find"]), e(c["name"]), e(c["client"]), (" · " + e(ago(c["when"]))) if k == "requested" and c["when"] else "",
                "%d creator%s" % (c["n"], "" if c["n"] == 1 else "s"), e(c["price"]),
                ("<div class='nx %s'>%s</div>" % (c["tone"], e(c["next"]))) if c["next"] else "") for c in shown)
        if k == "completed" and len(lst) > 12:
            html += "<a class='hb-more' href='%s'>All %d completed</a>" % (u("/campaigns"), len(lst))
        cols += "<section class='hb-col%s' aria-label='%s'><h3>%s <i>%d</i></h3>%s</section>" % (
            " hot" if k == "requested" else "", e(lab), e(lab), len(lst), html or "<p class='hb-empty'>Nothing here.</p>")
    head = ("<div class='hb-top'><div><h1>Selections and campaigns</h1><p>Every shortlist from first draft to finished campaign. "
            "The black column is waiting for you. Open a card to price it, send the quote, or follow the campaign.</p></div>"
            "<div class='hb-btns'><nav class='hb-seg' aria-label='View'><a href='%s' aria-current='true'>Board</a><a href='%s'>List</a></nav>"
            "<a class='btn lime' href='%s#new'>New selection</a></div></div>") % (u("/work"), u("/selections"), u("/selections"))
    bar = ("<div class='hb-bar'><label class='hb-find'>" + ui.icon("search", 18)
           + "<input id='hb-q' placeholder='Find a selection, campaign or client' aria-label='Find'></label>"
           "<nav class='hb-seg' aria-label='Whose'><a href='" + u("/work") + "'" + ("" if team else " aria-current='true'") + ">Clients only</a>"
           "<a href='" + u("/work") + "?team=1'" + (" aria-current='true'" if team else "") + ">Include the team's tests</a></nav>"
           "<a class='btn ghost' href='" + u("/campaigns") + "'>All campaigns</a></div>")
    banner = (("<div class='ok'>" + e(ok) + "</div>") if ok else "") + (("<div class='err'>" + e(err) + "</div>") if err else "")
    legend = "<p class='hb-legend'>Cards move by themselves as the client requests and approves, and as you price, send, go live and end. Archived ones are in the List view.</p>"
    return page("Selections and campaigns", CSS + head + banner + bar + "<div class='hb-board'>" + cols + "</div>" + legend + _FIND_JS, "/work")
