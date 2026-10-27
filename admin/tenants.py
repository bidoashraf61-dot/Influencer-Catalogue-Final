"""Tenants: one table of every company, one editable page per company, and the request inbox.

Owners only — admins run the business, owners configure the platform.

A **company** is every `codes` account that signs in under the same flattened name ("Blue holding"
and "Blueholding" are one company; a passcode with no person behind it is grouped by its label).
The entitlements themselves are stored per account (`tenant_modules`, `tenant_settings`), because
every selection and campaign hangs off a `codes` row. The company view therefore shows a value when
all its accounts agree and "mixed" when they do not, and an edit on the company page is written to
every account in it, so the two views can never disagree for long.

Every change on a company page is written to `tenant_history` (who, when, the value before and
after) and to the security log, and can be put back from the History link on its own line.
"""
import json
import re

import db
import modules
import tenant_requests

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenant_history (
    id      INTEGER PRIMARY KEY,
    at      INTEGER NOT NULL,
    who     TEXT,
    company TEXT NOT NULL,                -- the flattened company key
    field   TEXT NOT NULL,                -- lvl:<module> | set:<key> | kam | role:<user>:<module>
    before  TEXT,
    after   TEXT
);
CREATE INDEX IF NOT EXISTS tenant_history_co ON tenant_history(company, field, id);
"""
_ready = False


def _conn():
    global _ready
    if not _ready:
        with db.connect() as c:
            c.executescript(SCHEMA)
        _ready = True
    return db.connect()


def _key(name):
    """What makes two spellings the same company."""
    return re.sub(r"[^a-z0-9]+", "", str(name or "").lower()) or "—"


# ------------------------------------------------------------------ the data --

def _groups():
    """[(company key, display name, [(code row, user row or None)])], alphabetical."""
    import portal
    out, names = {}, {}
    users = {}
    with db.connect() as conn:
        for u in conn.execute("SELECT * FROM users WHERE deleted_at IS NULL"):
            users.setdefault(u["code_id"], []).append(u)
    for c in db.list_codes():
        us = users.get(c["id"]) or [None]
        raw = next((u["company"] for u in us if u is not None and u["company"]), "") or c["label"]
        raw = re.sub(r"^Client:\s*", "", raw)
        k = _key(raw)
        names.setdefault(k, {}).setdefault(raw, 0)
        names[k][raw] += 1
        out.setdefault(k, []).extend((c, u) for u in us)
    rows = []
    for k, members in out.items():
        best = sorted(names[k].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        rows.append((k, best, members))
    rows.sort(key=lambda r: r[1].lower())
    return rows


def _balance(code_id):
    with db.connect() as conn:
        r = conn.execute("SELECT balance_after FROM credit_ledger WHERE code_id = ? ORDER BY id DESC LIMIT 1",
                         (code_id,)).fetchone()
    return int(r["balance_after"] or 0) if r else 0


def _agree(values):
    """The one value they share, or the string 'mixed'."""
    s = set(values)
    return s.pop() if len(s) == 1 else "mixed"


def _spend(cid):
    try:
        import competitors
        return competitors.spend_month(cid)
    except Exception:
        return 0.0


def companies():
    """One dict per company with everything the table shows."""
    stored, setn = modules.all_levels(), modules.all_settings()
    out = []
    for k, name, members in _groups():
        codes = {}
        people = []
        for c, u in members:
            codes[c["id"]] = c
            if u is not None:
                people.append(u)
        ids = sorted(codes)
        lv = {m["key"]: _agree((stored.get(i) or {}).get(m["key"], modules.DEFAULT) for i in ids)
              for m in modules.MODULES}
        lim = {f["key"]: _agree((setn.get(i) or {}).get(f["key"], "") for i in ids)
               for f in modules.LIMITS + modules.BRAND + modules.NOTES}
        if not lim["credits_month"] and people:
            lim["credits_month"] = _agree(u["monthly_credits"] if u["monthly_credits"] is not None else ""
                                          for u in people)
            lim["credits_month"] = "" if lim["credits_month"] is None else lim["credits_month"]
        last = max([codes[i]["last_used"] or 0 for i in ids] + [u["last_login_at"] or 0 for u in people] + [0])
        kams = sorted({(u["kam"] or "").strip() for u in people if (u["kam"] or "").strip()})
        live = [u for u in people if u["status"] == "active" and not codes[u["code_id"]]["revoked_at"]]
        if not people:
            status = "Passcode" if any(not c["revoked_at"] for c in codes.values()) else "Revoked"
        elif live:
            status = "Active"
        elif any(u["status"] == "pending" for u in people):
            status = "Pending"
        else:
            status = "Suspended"
        out.append({
            "key": k, "name": name, "ids": ids, "people": people, "accounts": len(ids), "levels": lv, "limits": lim,
            "credits": sum(_balance(i) for i in ids),
            "campaigns": sum(codes[i]["n_campaigns"] for i in ids),
            "selections": sum(codes[i]["n_selections"] for i in ids),
            "spend": round(sum(_spend(i) for i in ids), 2),
            "kam": ", ".join(kams), "last": last, "status": status,
        })
    return out


def company(k):
    for c in companies():
        if c["key"] == k:
            return c
    return None


# ----------------------------------------------------------------- the table --

def _cap_pill(used, cap, fmt="%d"):
    """'used / cap' with a warning past 80% and a red at the cap. No cap shows just the usage."""
    txt = fmt % used
    if cap in ("", None):
        return txt, "", used
    if cap == "mixed":
        return txt + " / mixed", "warn", used
    try:
        n = float(cap)
    except ValueError:
        return txt, "", used
    cls = "dead" if n and used >= n else ("warn" if n and used >= 0.8 * n else "")
    return txt + " / " + fmt % n, cls, used


def page_html(query=None):
    import views
    e, u = views.e, views.u
    query = query or {}
    cos = companies()
    pend = tenant_requests.pending_count()
    note = ""
    if query.get("ok"):
        note = "<div class='ok'>" + e(query.get("ok")) + "</div>"
    elif query.get("e"):
        note = "<div class='err'>" + e(query.get("e")) + "</div>"

    def mod_cell(c, m):
        lv = c["levels"][m["key"]]
        lab = "Mixed" if lv == "mixed" else modules.LEVEL_LABEL[lv].split(" ")[0]
        cls = {"off": "dead", "view": "own", "manage": "live", "mixed": "warn"}[lv]
        return "<td data-v='%s' data-m='%s'><span class='pill %s'>%s</span></td>" % (
            e(lv), e(m["key"] + ":" + lv), cls, e(lab))

    def cap_cell(label, used, cap, fmt="%d"):
        txt, cls, v = _cap_pill(used, cap, fmt)
        return "<td data-v='%s' data-l='%s'>%s</td>" % (
            v, e(label), ("<span class='pill %s'>%s</span>" % (cls, e(txt))) if cls else e(txt))

    rows = []
    for c in cos:
        L = c["limits"]
        st = {"Active": "live", "Pending": "warn", "Suspended": "dead", "Revoked": "dead", "Passcode": ""}[c["status"]]
        mods = " ".join(m["key"] + ":" + c["levels"][m["key"]] for m in modules.MODULES)
        rows.append(
            "<tr data-co='%s' data-st='%s' data-kam='%s' data-mods='%s' data-q='%s'>"
            "<th scope='row' data-v='%s'><a href='%s'><b>%s</b></a><div class='muted'>%d account%s</div></th>"
            "<td data-v='%s'><span class='pill %s'>%s</span></td>%s%s%s%s%s%s"
            "<td data-v='%d'>%d</td><td data-v='%s'>%s</td><td data-v='%d'>%s</td></tr>" % (
                e(c["key"]), e(c["status"]), e(c["kam"] or "—"), e(mods),
                e((c["name"] + " " + " ".join(p["email"] + " " + (p["name"] or "") for p in c["people"])).lower()),
                e(c["name"].lower()), e(u("/tenants/co?k=" + c["key"])), e(c["name"]), c["accounts"],
                "" if c["accounts"] == 1 else "s",
                e(c["status"]), st, e(c["status"]),
                "".join(mod_cell(c, m) for m in modules.MODULES),
                cap_cell("Seats", len(c["people"]), L["seats"]),
                cap_cell("AI credits left", c["credits"], L["credits_month"]),
                cap_cell("Campaigns", c["campaigns"], L["campaigns_max"]),
                cap_cell("Selections", c["selections"], L["selections_max"]),
                cap_cell("Collection $ this month", c["spend"], L["spend_month"], "%.2f"),
                len(c["people"]), len(c["people"]),
                e((c["kam"] or "").lower()), e(c["kam"] or "—"),
                c["last"] or 0, e(views.ts(c["last"]) if c["last"] else "—")))
    kams = sorted({k.strip() for c in cos for k in (c["kam"] or "").split(",") if k.strip()})
    mod_head = "".join("<th data-sort title='%s'>%s</th>" % (e(m["what"]), e(m["name"].replace("Helvi ", ""))) for m in modules.MODULES)
    mod_opts = "".join(
        "<option value='%s:off'>%s off</option><option value='%s:manage'>%s manage</option>"
        % (e(m["key"]), e(m["name"]), e(m["key"]), e(m["name"])) for m in modules.MODULES)
    counts = {"n": len(cos), "act": sum(1 for c in cos if c["status"] == "Active")}
    body = (
        "<div class='card'><div class='hd'><h2>Tenants</h2><div class='hd-acts'>"
        "<a class='btn small ghost' href='" + e(u("/tenants/requests")) + "'>Access requests"
        + (" <span class='badge'>%d</span>" % pend if pend else "") + "</a>"
        "<button type='button' class='btn small ghost' id='tn-csv'>Export CSV</button></div></div>" + note +
        "<p class='sec-desc'>%d companies, %d active. One row each; click a company to edit everything about it. "
        "HelloVoice staff always see everything, whatever is set here.</p>" % (counts["n"], counts["act"]) +
        "<div class='tn-bar'><input type='search' id='tn-q' placeholder='Search company, person, email' aria-label='Search'>"
        "<select id='tn-st' aria-label='Status'><option value=''>Any status</option><option>Active</option>"
        "<option>Pending</option><option>Suspended</option><option>Revoked</option><option>Passcode</option></select>"
        "<select id='tn-mod' aria-label='Module'><option value=''>Any modules</option>" + mod_opts + "</select>"
        "<select id='tn-kam' aria-label='KAM'><option value=''>Any KAM</option>"
        + "".join("<option>%s</option>" % e(k) for k in kams) + "</select>"
        "<span class='muted' id='tn-n'></span></div>"
        "<div class='tn-wrap'><table class='tbl tn' id='tn-t'><thead><tr><th data-sort>Company</th><th data-sort>Status</th>"
        + mod_head +
        "<th data-sort title='People on the account, against the seat limit'>Seats</th>"
        "<th data-sort title='Credits left now, against the monthly allowance'>AI credits</th>"
        "<th data-sort>Campaigns</th><th data-sort>Selections</th>"
        "<th data-sort title='What their collection runs cost Apify this month, against the cap'>Collection $</th>"
        "<th data-sort>People</th><th data-sort>KAM</th><th data-sort>Last active</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table></div></div>" + _TABLE_CSS + _TABLE_JS)
    return views.page("Tenants", body, "/tenants")


_TABLE_CSS = """<style>
.tn-bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 12px}
.tn-bar input,.tn-bar select{width:auto;min-height:36px;padding:4px 10px;border:1px solid var(--line-strong);border-radius:10px;font:inherit;background:#fff}
.tn-bar input{flex:1 1 220px;max-width:320px}
.tn-wrap{overflow-x:auto;margin:0 -4px}
table.tn{width:100%;border-collapse:collapse;font-size:var(--t-sm,13px)}
table.tn th,table.tn td{padding:8px 10px;text-align:left;white-space:nowrap;border-bottom:1px solid var(--line)}
table.tn thead th{position:sticky;top:0;background:#faf8f3;cursor:pointer;user-select:none;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--gray)}
table.tn thead th.s-asc::after{content:' ▲'}table.tn thead th.s-desc::after{content:' ▼'}
table.tn tbody th{text-align:left;font-weight:400;position:sticky;left:0;background:#fff;z-index:1}
table.tn tbody tr:hover td,table.tn tbody tr:hover th{background:#faf8f3}
table.tn td{font-variant-numeric:tabular-nums}
table.tn tbody th a{text-transform:none;letter-spacing:0;text-decoration:none;color:var(--ink)}
table.tn tbody th a:hover{text-decoration:underline}
</style>"""

_TABLE_JS = """<script>
(function(){
var t=document.getElementById('tn-t'),tb=t.tBodies[0],q=document.getElementById('tn-q'),
 st=document.getElementById('tn-st'),md=document.getElementById('tn-mod'),km=document.getElementById('tn-kam'),n=document.getElementById('tn-n');
function filt(){var s=q.value.trim().toLowerCase(),c=0;
 Array.prototype.forEach.call(tb.rows,function(r){
  var ok=(!s||r.dataset.q.indexOf(s)>-1)&&(!st.value||r.dataset.st===st.value)&&(!km.value||r.dataset.kam.split(', ').indexOf(km.value)>-1)
   &&(!md.value||(' '+r.dataset.mods+' ').indexOf(' '+md.value+' ')>-1);
  r.hidden=!ok;if(ok)c++;});
 n.textContent=c+' shown';}
[q,st,md,km].forEach(function(x){x.addEventListener('input',filt)});filt();
function val(r,i){var c=r.cells[i],v=c.dataset.v!==undefined?c.dataset.v:c.textContent;var f=parseFloat(v);return isNaN(f)||/[a-z]/i.test(v)?String(v).toLowerCase():f;}
Array.prototype.forEach.call(t.tHead.rows[0].cells,function(h,i){h.addEventListener('click',function(){
 var asc=!h.classList.contains('s-asc');Array.prototype.forEach.call(t.tHead.rows[0].cells,function(x){x.classList.remove('s-asc','s-desc')});
 h.classList.add(asc?'s-asc':'s-desc');
 var rs=Array.prototype.slice.call(tb.rows);rs.sort(function(a,b){var x=val(a,i),y=val(b,i);return (x<y?-1:x>y?1:0)*(asc?1:-1)});
 rs.forEach(function(r){tb.appendChild(r)});});});
document.getElementById('tn-csv').addEventListener('click',function(){
 var rows=[Array.prototype.map.call(t.tHead.rows[0].cells,function(h){return h.textContent.trim()})];
 Array.prototype.forEach.call(tb.rows,function(r){if(!r.hidden)rows.push(Array.prototype.map.call(r.cells,function(c){return c.textContent.replace(/\\s+/g,' ').trim()}))});
 var csv=rows.map(function(r){return r.map(function(v){return '"'+v.replace(/"/g,'""')+'"'}).join(',')}).join('\\n');
 var a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\\ufeff'+csv],{type:'text/csv'}));a.download='tenants.csv';a.click();});
})();
</script>"""


# --------------------------------------------------------------- company page --

def company_html(k, query=None):
    import views
    e, u = views.e, views.u
    query = query or {}
    c = company(k)
    if c is None:
        return views.page("Tenants", "<div class='card'><p>No such company. <a href='" + e(u("/tenants")) +
                          "'>Back to Tenants</a></p></div>", "/tenants")
    roles = modules.user_roles([p["id"] for p in c["people"]])

    def line(field, label, control, help_="", hist=True):
        return ("<div class='ln' data-f='%s'><div class='ln-l'><b>%s</b>%s</div><div class='ln-c'>%s"
                "<span class='ln-s muted' aria-live='polite'></span></div>%s<div class='ln-hp' hidden></div></div>" % (
                    e(field), e(label), ("<div class='muted'>" + e(help_) + "</div>") if help_ else "", control,
                    "<div class='ln-h'><button type='button' class='btn tiny ghost' data-hist>History</button></div>"
                    if hist else "<div class='ln-h'></div>"))

    def select(field, cur, opts):
        o = "".join("<option value='%s'%s>%s</option>" % (e(v), " selected" if v == cur else "", e(l)) for v, l in opts)
        if cur == "mixed":
            o = "<option value='mixed' selected disabled>Mixed across accounts</option>" + o
        return "<select data-set='%s'>%s</select>" % (e(field), o)

    def text(field, cur, ph="", kind="text"):
        v = "" if cur in (None, "mixed") else cur
        return ("<input data-set='%s' value='%s' placeholder='%s'%s>" % (
            e(field), e(v), e("mixed — type to set all" if cur == "mixed" else ph),
            " inputmode='numeric'" if kind == "int" else ""))

    mod_lines = "".join(
        line("lvl:" + m["key"], m["name"],
             select("lvl:" + m["key"], c["levels"][m["key"]], [(lv, modules.LEVEL_LABEL[lv]) for lv in modules.LEVELS]),
             m["what"]) for m in modules.MODULES)
    lim_lines = "".join(
        line("set:" + f["key"], f["label"], text("set:" + f["key"], c["limits"][f["key"]], _default_hint(f), f["kind"]),
             f["help"] + ("" if f["enforced"] else " Recorded, not enforced yet."))
        for f in modules.LIMITS)
    usage = ("<div class='muted ln-note'>Now: %d people · %d credits left · %d campaigns · %d selections · $%.2f collection this month</div>"
             % (len(c["people"]), c["credits"], c["campaigns"], c["selections"], c["spend"]))
    brand_lines = "".join(
        line("set:" + f["key"], f["label"], text("set:" + f["key"], c["limits"][f["key"]], "default"), f["help"])
        for f in modules.BRAND)
    kam_line = line("kam", "Key account manager", text("kam", c["kam"] if "," not in c["kam"] else "mixed", "none"),
                    "Who looks after this company. Written to every person on it.")
    notes_line = line("set:notes", "Notes", text("set:notes", c["limits"]["notes"], "Internal notes"),
                      "Internal. The client never sees this.")

    ppl = ""
    for p in c["people"]:
        cells = "".join(
            "<td data-l='%s'>%s</td>" % (e(m["name"]), select("role:%d:%s" % (p["id"], m["key"]),
                                                              roles.get((p["id"], m["key"]), "viewer"),
                                                              [(r, r.capitalize()) for r in modules.ROLES]))
            for m in modules.MODULES)
        ppl += ("<tr data-f='people'><td><b>%s</b><div class='muted'>%s</div></td><td>%s</td>%s"
                "<td><button type='button' class='btn tiny ghost' data-hist data-hf='role:%d'>History</button></td></tr>"
                % (e(p["name"] or p["email"]), e(p["email"]), e(p["status"]), cells, p["id"]))
    people = ("<table class='tbl'><thead><tr><th>Person</th><th>Status</th>" +
              "".join("<th>%s</th>" % e(m["name"]) for m in modules.MODULES) + "<th></th></tr></thead><tbody>" +
              (ppl or "<tr><td colspan='9' class='muted'>No one has signed up under this company yet.</td></tr>") +
              "</tbody></table><p class='muted'>Effective access is the lower of the company's level above and the person's role. "
              "A person with no role set reads as Viewer.</p>")
    pend = [r for r in tenant_requests.listing("pending") if r["code_id"] in c["ids"]]
    reqs = (("<p><a href='%s'><b>%d pending request%s</b></a> from this company.</p>"
             % (e(u("/tenants/requests?k=" + k)), len(pend), "" if len(pend) == 1 else "s")) if pend else "")
    note = ("<div class='ok'>" + e(query.get("ok")) + "</div>") if query.get("ok") else ""

    body = (
        "<div class='card'><div class='hd'><h2>" + e(c["name"]) + "</h2><div class='hd-acts'>"
        "<a class='btn small ghost' href='" + e(u("/tenants")) + "'>All tenants</a></div></div>" + note +
        "<p class='sec-desc'>%d account%s · status %s. Every change saves as you make it and is kept in History.</p>"
        % (c["accounts"], "" if c["accounts"] == 1 else "s", e(c["status"])) + reqs + "</div>"
        "<div class='card'><div class='hd'><h2>Modules</h2></div>" + mod_lines + "</div>"
        "<div class='card'><div class='hd'><h2>Limits and credits</h2></div><p class='sec-desc'>Empty means the platform default. "
        "A cap counts what they have now and refuses the next one.</p>" + usage + lim_lines + "</div>"
        "<div class='card'><div class='hd'><h2>Branding</h2></div>" + brand_lines + "</div>"
        "<div class='card'><div class='hd'><h2>People and roles</h2></div>" + kam_line + people + "</div>"
        "<div class='card'><div class='hd'><h2>Notes</h2></div>" + notes_line + "</div>"
        + _CO_CSS + "<script>var TN_K=" + json.dumps(k) + ",TN_B=" + json.dumps(views.BASE) + ";</script>" + _CO_JS)
    return views.page(c["name"], body, "/tenants")


def _default_hint(f):
    """What shows through an empty box: the platform default, in words."""
    if f["key"] == "credits_month":
        return str(db.setting("monthly_credits", 0) or 0)
    return "no limit" if f["kind"] == "int" else "default"


_CO_CSS = """<style>
.ln{display:grid;grid-template-columns:minmax(180px,1fr) minmax(220px,1.3fr) auto;gap:6px 16px;align-items:start;padding:11px 0;border-bottom:1px solid var(--line)}
.ln:last-child{border-bottom:0}
.ln-c{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.ln-c input,.ln-c select,.card td select{width:auto;min-height:36px;padding:4px 10px;border:1px solid var(--line-strong);border-radius:10px;font:inherit;background:#fff;min-width:0;max-width:100%}
.ln-c input{flex:1 1 180px}
.ln-s.ok-t{color:var(--green)}.ln-s.err-t{color:var(--red)}
.ln-hp{grid-column:1/-1;background:#faf8f3;border-radius:10px;padding:8px 12px;font-size:var(--t-sm,13px)}
.ln-hp[hidden]{display:none}
.ln-hp div{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:3px 0}
.ln-note{margin:0 0 6px}
@media(max-width:720px){.ln{grid-template-columns:1fr}.ln-c input,.ln-c select{width:100%}}
</style>"""

_CO_JS = """<script>
(function(){
function post(p,b){return fetch(TN_B+p,{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify(b)}).then(function(r){return r.json()})}
function msg(el,t,ok){var s=el.closest('.ln,tr').querySelector('.ln-s');if(!s){s=document.createElement('span');s.className='ln-s muted';el.parentNode.appendChild(s)}s.textContent=t;s.className='ln-s '+(ok?'ok-t':'err-t');}
function save(el,field,value){post('/tenants/set',{k:TN_K,field:field,value:value}).then(function(r){
 msg(el,r.ok?(r.changed?'Saved':'No change'):(r.error||'Not saved'),r.ok);if(r.ok&&r.value!==undefined&&el.tagName==='INPUT'&&document.activeElement!==el)el.value=r.value;
 }).catch(function(){msg(el,'Not saved — connection',false)});}
document.addEventListener('change',function(ev){var el=ev.target;if(el.dataset&&el.dataset.set)save(el,el.dataset.set,el.value);});
document.addEventListener('keydown',function(ev){if(ev.key==='Enter'&&ev.target.dataset&&ev.target.dataset.set){ev.preventDefault();ev.target.blur();}});
document.addEventListener('click',function(ev){
 var rb=ev.target.closest('[data-restore]');
 if(rb){post('/tenants/set',{k:TN_K,field:rb.dataset.field,value:rb.dataset.restore}).then(function(r){if(r.ok)location.reload();else alert(r.error||'Not restored')});return}
 var b=ev.target.closest('[data-hist]');if(!b)return;
 var ln=b.closest('.ln,tr'),f=b.dataset.hf||(ln.dataset.f),panel=ln.classList.contains('ln')?ln.querySelector('.ln-hp'):null;
 if(!panel){panel=ln.nextElementSibling&&ln.nextElementSibling.classList.contains('hp-row')?ln.nextElementSibling:null;
  if(!panel){var tr=document.createElement('tr');tr.className='hp-row';tr.innerHTML='<td colspan="9"><div class="ln-hp"></div></td>';ln.parentNode.insertBefore(tr,ln.nextSibling);panel=tr;}
  var inner=panel.querySelector('.ln-hp');panel=inner;}
 if(!panel.hidden&&panel.dataset.open){panel.hidden=true;panel.dataset.open='';if(panel.parentNode.classList&&panel.parentNode.parentNode.classList.contains('hp-row'))panel.closest('tr').remove();return}
 var pr=f==='people'||f.indexOf('role:')===0?ln.querySelectorAll('select[data-set]'):null,fields=[];
 if(f==='people'||!f)Array.prototype.forEach.call(ln.querySelectorAll('[data-set]'),function(x){fields.push(x.dataset.set)});else fields=[f];
 panel.hidden=false;panel.dataset.open='1';panel.textContent='Loading…';
 fetch(TN_B+'/tenants/hist?k='+encodeURIComponent(TN_K)+'&f='+encodeURIComponent(fields.join('|')),{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(rows){
  panel.textContent='';if(!rows.length){panel.textContent='No changes yet.';return}
  rows.forEach(function(h){var d=document.createElement('div');d.appendChild(document.createTextNode(h.at+' · '+h.who+' · '+(h.label||h.field)+': '+(h.before||'—')+' → '+(h.after||'—')+' '));
   var x=document.createElement('button');x.type='button';x.className='btn tiny ghost';x.textContent='Restore '+(h.before||'default');x.dataset.restore=h.before||'';x.dataset.field=h.field;d.appendChild(x);panel.appendChild(d)});});
});
})();
</script>"""


# -------------------------------------------------------------------- editing --

def _read(c, field):
    """The current value of one field for a company, as text ('mixed' when accounts differ)."""
    if field.startswith("lvl:"):
        return c["levels"].get(field[4:], "")
    if field.startswith("set:"):
        return c["limits"].get(field[4:], "")
    if field == "kam":
        return c["kam"]
    if field.startswith("role:"):
        _, uid, mod = field.split(":", 2)
        return modules.user_roles([int(uid)]).get((int(uid), mod), "viewer")
    return ""


def apply_edit(k, field, value, by, ip=None):
    """Set one field on every account of a company. Returns (ok, message, stored value, changed)."""
    import portal
    import team
    c = company(k)
    if c is None:
        return False, "No such company.", None, False
    value = (value if value is not None else "")
    value = str(value).strip()
    before = _read(c, field)
    if field.startswith("lvl:"):
        if field[4:] not in modules.BY_KEY or value not in modules.LEVELS:
            return False, "Not a valid level.", None, False
        if value == before:
            return True, "", value, False
        for cid in c["ids"]:
            modules.set_level(cid, field[4:], value, by)
    elif field.startswith("set:"):
        key = field[4:]
        if key not in modules.FIELDS:
            return False, "Unknown field.", None, False
        if modules.FIELDS[key]["kind"] == "int" and value and not value.isdigit():
            return False, "Whole numbers only.", None, False
        if value == ("" if before == "mixed" else before):
            return True, "", value, False
        for cid in c["ids"]:
            modules.set_value(cid, key, value, by)
        if key == "credits_month":
            for cid in c["ids"]:
                _apply_credits(cid, value)
    elif field == "kam":
        if value == before:
            return True, "", value, False
        for p in c["people"]:
            portal.update_profile(p["id"], kam=value)
    elif field.startswith("role:"):
        try:
            _, uid, mod = field.split(":", 2)
            uid = int(uid)
        except ValueError:
            return False, "Bad field.", None, False
        person = next((p for p in c["people"] if p["id"] == uid), None)
        if person is None or value not in modules.ROLES or mod not in modules.BY_KEY:
            return False, "Not a valid role.", None, False
        if value == before:
            return True, "", value, False
        if modules.set_role(uid, person["code_id"], mod, value) is None:
            return False, "Roles are not switched on yet.", None, False
    else:
        return False, "Unknown field.", None, False
    with _conn() as conn:
        conn.execute("INSERT INTO tenant_history (at, who, company, field, before, after) VALUES (?,?,?,?,?,?)",
                     (db.now(), by, k, field, before, value))
    team.log("tenant_config", by, "%s · %s · %s -> %s" % (c["name"], field, before or "default", value or "default"), ip)
    return True, "", value, True


def history_rows(k, fields, limit=30):
    import views
    fl = [f for f in (fields or "").split("|") if f]
    if not fl:
        return []
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM tenant_history WHERE company = ? AND field IN (%s) ORDER BY id DESC LIMIT ?"
                            % ",".join("?" * len(fl)), [k] + fl + [limit]).fetchall()
    return [{"at": views.ts(r["at"]), "who": r["who"] or "", "field": r["field"], "label": r["field"].split(":", 1)[-1],
             "before": r["before"], "after": r["after"]} for r in rows]


def _apply_credits(code_id, val):
    """Monthly credits are already a per-client field the refill reads (`users.monthly_credits`),
    so the panel writes there rather than growing a second allowance nobody enforces."""
    import portal
    u = portal.user_for_code(code_id)
    if u is None:
        return
    try:
        n = None if val in ("", "default", None) else max(0, int(val))
    except (TypeError, ValueError):
        return
    portal.update_profile(u["id"], monthly_credits=n)


# ---------------------------------------------------------------------- inbox --

def _describe(r):
    d = r["detail"]
    mod = modules.BY_KEY.get(r["module"] or d.get("module") or "", {}).get("name", r["module"] or "")
    if r["kind"] == "module":
        return "%s at level <b>%s</b>" % (mod, d.get("level") or "view")
    if r["kind"] == "role":
        return "Role <b>%s</b> in %s" % (d.get("role") or "editor", mod)
    f = modules.FIELDS.get(d.get("key") or "", {})
    return "%s raised to <b>%s</b>" % (f.get("label") or d.get("key") or "a limit", d.get("value", "?"))


def requests_html(query=None):
    import views
    e, u = views.e, views.u
    query = query or {}
    import portal
    names = {}
    for c in companies():
        for i in c["ids"]:
            names[i] = (c["name"], c["key"])
    with db.connect() as conn:
        em = {r["id"]: (r["name"] or r["email"]) for r in conn.execute("SELECT id, name, email FROM users")}
    only = query.get("k")

    def table(rows, pending):
        out = ""
        for r in rows:
            nm, ck = names.get(r["code_id"], ("Unknown", ""))
            if only and ck != only:
                continue
            d = r["detail"]
            ctl = ""
            if pending:
                dflt = d.get("value") if r["kind"] == "limit" else (d.get("level") if r["kind"] == "module" else d.get("role"))
                opts = ""
                if r["kind"] == "module":
                    opts = "<select name='value'>" + "".join("<option%s>%s</option>" % (" selected" if v == (dflt or "view") else "", v) for v in modules.LEVELS if v != "off") + "</select>"
                elif r["kind"] == "role":
                    opts = "<select name='value'>" + "".join("<option%s>%s</option>" % (" selected" if v == (dflt or "editor") else "", v) for v in modules.ROLES if v != "none") + "</select>"
                else:
                    opts = "<input name='value' value='%s' size='6' inputmode='numeric' aria-label='Value'>" % e(dflt if dflt is not None else "")
                ctl = ("<form method='post' action='%s' class='tn-dec'><input type='hidden' name='id' value='%d'>%s"
                       "<input name='reply' placeholder='Reply (optional)' size='16'>"
                       "<button class='btn tiny' name='do' value='approve'>Approve</button>"
                       "<button class='btn tiny ghost' name='do' value='decline'>Decline</button></form>"
                       % (e(u("/tenants/requests/decide")), r["id"], opts))
            else:
                ctl = "<span class='pill %s'>%s</span> <span class='muted'>%s · %s</span>" % (
                    "live" if r["status"] == "approved" else "dead", e(r["status"]), e(r["decided_by"] or ""),
                    e(views.ts(r["decided_at"])))
            out += ("<tr><td>%s<div class='muted'>%s</div></td><td>%s<div class='muted'>%s</div></td><td>%s</td><td>%s</td>"
                    "<td class='muted'>%s</td><td>%s</td></tr>" % (
                        ("<a href='%s'><b>%s</b></a>" % (e(u("/tenants/co?k=" + ck)), e(nm))) if ck else e(nm),
                        e(em.get(r["user_id"], "")), e(r["kind"].capitalize()), "", _describe(r), e(r["note"] or ""),
                        e(views.ts(r["created_at"])), ctl))
        return out

    pend, done = tenant_requests.listing("pending"), [r for r in tenant_requests.listing() if r["status"] != "pending"][:40]
    head = "<thead><tr><th>Company</th><th>Kind</th><th>Asked for</th><th>Note</th><th>When</th><th></th></tr></thead>"
    note = ("<div class='ok'>" + e(query.get("ok")) + "</div>") if query.get("ok") else (
        ("<div class='err'>" + e(query.get("e")) + "</div>") if query.get("e") else "")
    body = (
        "<div class='card'><div class='hd'><h2>Access requests</h2><div class='hd-acts'><a class='btn small ghost' href='"
        + e(u("/tenants")) + "'>All tenants</a></div></div>" + note +
        "<p class='sec-desc'>People asking for a module, a role or a higher limit. Approving applies the change to the company "
        "and writes it to its History; you can adjust the value first.</p>"
        "<table class='tbl'>" + head + "<tbody>" + (table(pend, True) or "<tr><td colspan='6' class='muted'>Nothing waiting.</td></tr>") +
        "</tbody></table></div>"
        "<div class='card'><div class='hd'><h2>Answered</h2></div><table class='tbl'>" + head + "<tbody>" +
        (table(done, False) or "<tr><td colspan='6' class='muted'>None yet.</td></tr>") + "</tbody></table></div>"
        "<style>.tn-dec{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:0}.tn-dec input,.tn-dec select{min-height:32px;padding:2px 8px;"
        "border:1px solid var(--line-strong);border-radius:8px;font:inherit}</style>")
    return views.page("Access requests", body, "/tenants")


def decide(rid, action, value, reply, by, ip=None):
    """Approve (apply it) or decline one request. Returns a sentence for the page."""
    r = tenant_requests.get(rid)
    if r is None or r["status"] != "pending":
        return False, "That request is no longer pending."
    ck = next((c["key"] for c in companies() if r["code_id"] in c["ids"]), None)
    if action == "decline":
        tenant_requests.close(rid, "declined", by, reply)
        return True, "Declined."
    if ck is None:
        return False, "The company no longer exists."
    d = r["detail"]
    mod = r["module"] or d.get("module")
    if r["kind"] == "module":
        ok, m, _, _ = apply_edit(ck, "lvl:" + (mod or ""), value or d.get("level") or "view", by, ip)
    elif r["kind"] == "role":
        if not r["user_id"]:
            return False, "This role request names no person."
        ok, m, _, _ = apply_edit(ck, "role:%d:%s" % (r["user_id"], mod), value or d.get("role") or "editor", by, ip)
    else:
        ok, m, _, _ = apply_edit(ck, "set:" + (d.get("key") or ""), value if value != "" else str(d.get("value", "")), by, ip)
    if not ok:
        return False, m or "Could not apply it."
    tenant_requests.close(rid, "approved", by, reply)
    return True, "Approved and applied."
