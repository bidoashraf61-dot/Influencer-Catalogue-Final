"""Server-rendered dashboard pages.

Plain string concatenation rather than a templating engine — one less
dependency, and the whole UI stays readable in one sitting. Everything that
could come from a user or a client goes through `e()`; there is no path where
raw input reaches the page.

Written for Python 3.9, which allows neither backslashes nor nested same-type
quotes inside an f-string expression. Anything awkward is built into a local
variable first rather than inlined.
"""

import html
import json
from datetime import datetime, timezone

from db import code_state, now


def e(v):
    return html.escape("" if v is None else str(v), quote=True)


def ts(value):
    if not value:
        return "—"
    return datetime.fromtimestamp(value, timezone.utc).strftime("%d %b %Y, %H:%M")


def ago(value):
    if not value:
        return "never"
    s = now() - value
    if s < 60:
        return str(max(1, s)) + "s ago"
    if s < 3600:
        return str(s // 60) + "m ago"
    if s < 86400:
        return str(s // 3600) + "h ago"
    if s < 2592000:
        return str(s // 86400) + "d ago"
    return ts(value)


def num(value):
    return format(value, ",") if value else "—"


CSS = """
:root{--ink:#121212;--gray:#585858;--line:#e6e2de;--bg:#faf8f6;--white:#fff;
--lime:#e8ff76;--red:#ee1515;--green:#1a7f37;--amber:#b76e00}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
a{color:inherit}
.wrap{max-width:1180px;margin:0 auto;padding:0 24px}
header.top{background:var(--ink);color:#fff;padding:14px 0}
header.top .wrap{display:flex;align-items:center;gap:28px}
.brand{display:flex;align-items:center;gap:10px;margin-right:auto;
text-decoration:none;color:#fff}
.brand img{display:block;height:26px;width:auto}
.brand span{opacity:.55;font-weight:400;font-size:14px}
.login img{filter:invert(1)}
nav a{display:inline-block;padding:6px 0;margin-right:20px;color:#fff;
text-decoration:none;opacity:.65;font-size:14px;border-bottom:2px solid transparent}
nav a:hover{opacity:1}
nav a.on{opacity:1;border-bottom-color:var(--lime)}
h1{font-size:26px;margin:32px 0 4px}
h2{font-size:17px;margin:32px 0 12px}
.sub{color:var(--gray);margin:0 0 24px}
.grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));margin:24px 0}
.stat{background:var(--white);border:1px solid var(--line);border-radius:12px;padding:18px}
.stat b{display:block;font-size:30px;line-height:1.1;margin-bottom:2px}
.stat span{color:var(--gray);font-size:13px}
.card{background:var(--white);border:1px solid var(--line);border-radius:12px;
padding:22px;margin-bottom:20px}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;font-size:12px;letter-spacing:.06em;text-transform:uppercase;
color:var(--gray);font-weight:600;padding:0 10px 8px;border-bottom:1px solid var(--line)}
td{padding:11px 10px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:0}
code{font:13px ui-monospace,SFMono-Regular,Menlo,monospace;background:#f1efec;
padding:2px 6px;border-radius:5px}
.pill{display:inline-block;font-size:12px;padding:3px 10px;border-radius:999px;
background:#f1efec;color:var(--gray)}
.pill.live{background:#e7f6ec;color:var(--green)}
.pill.dead{background:#fdeaea;color:var(--red)}
.pill.warn{background:#fdf3e3;color:var(--amber)}
label{display:block;font-size:12px;letter-spacing:.06em;text-transform:uppercase;
color:var(--gray);margin:0 0 6px}
input,select{width:100%;font:inherit;padding:10px 12px;border:1px solid var(--line);
border-radius:8px;background:var(--white);color:var(--ink)}
input:focus,select:focus{outline:2px solid var(--ink);outline-offset:-1px}
.row{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));margin-bottom:14px}
.btn{display:inline-block;font:inherit;font-weight:600;padding:10px 20px;border-radius:999px;
border:1px solid var(--ink);background:var(--ink);color:#fff;cursor:pointer;text-decoration:none}
.btn:hover{opacity:.88}
.btn.ghost{background:transparent;color:var(--ink)}
.btn.small{padding:6px 14px;font-size:13px}
.btn.danger{border-color:var(--red);color:var(--red);background:transparent}
.note{background:#fffbe6;border:1px solid #f0e2a8;border-radius:10px;padding:14px 16px;margin:16px 0}
.err{background:#fdeaea;border:1px solid #f5c2c2;border-radius:10px;padding:12px 16px;
margin:16px 0;color:#8a1a1a}
.ok{background:#e7f6ec;border:1px solid #b9e3c6;border-radius:10px;padding:12px 16px;
margin:16px 0;color:#14602b}
.reveal{font:20px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.08em;
background:var(--ink);color:var(--lime);padding:14px 18px;border-radius:10px;display:inline-block}
.bars{display:flex;align-items:flex-end;gap:3px;height:90px;margin:8px 0 4px}
.bars div{flex:1;background:var(--ink);border-radius:3px 3px 0 0;min-height:2px}
.muted{color:var(--gray)}
.right{text-align:right}
form.inline{display:inline}
summary{list-style:none;cursor:pointer}
.login{max-width:380px;margin:14vh auto}
.thumb{display:block;width:74px;height:74px;object-fit:cover;border-radius:10px;
background:#eee;border:1px solid var(--line)}
.thumb.sm{width:44px;height:44px;border-radius:8px}
.thumb.none{display:grid;place-items:center;color:#bbb;font-size:13px}
.photo-pick{display:flex;align-items:center;gap:12px}
.photo-pick input[type=file]{font-size:13px;padding:7px}

/* request cards */
.req{background:var(--white);border:1px solid var(--line);border-radius:14px;
padding:22px;margin-bottom:18px}
.req.done{opacity:.62}
.req-head{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start;
padding-bottom:16px;border-bottom:1px solid var(--line);margin-bottom:18px}
.req-who h3{margin:0 0 4px;font-size:19px}
.req-who a{color:var(--gray);text-decoration:none}
.req-who a:hover{color:var(--ink)}
.req-meta{margin-left:auto;text-align:right;font-size:13px;color:var(--gray)}
.req-sum{display:flex;flex-wrap:wrap;gap:22px;margin:0 0 18px;font-size:13px}
.req-sum b{display:block;font-size:18px;color:var(--ink)}
.req-sum span{color:var(--gray)}
.picks{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(232px,1fr))}
.pick{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--white)}
.pick-top{display:flex;gap:12px;padding:12px}
.pick-top .thumb{width:62px;height:62px;flex:none}
.pick-id{min-width:0}
.pick-id code{font-size:11px;padding:1px 5px}
.pick-id strong{display:block;font-size:15px;margin:4px 0 2px;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pick-id a{font-size:12px;color:var(--gray)}
.pick dl{margin:0;padding:0 12px 12px;font-size:12.5px}
.pick dl div{display:flex;justify-content:space-between;gap:10px;
padding:5px 0;border-top:1px solid var(--line)}
.pick dt{color:var(--gray);margin:0}
.pick dd{margin:0;font-weight:600}
.pick .gone{padding:14px;color:var(--red);font-size:13px}
@media(max-width:700px){
 header.top .wrap{flex-wrap:wrap;gap:10px}
 nav a{margin-right:14px}
 table,thead,tbody,tr,td,th{display:block}
 thead{display:none}
 td{border:0;padding:4px 0}
 tr{border-bottom:1px solid var(--line);padding:12px 0}
}
"""

HEAD = (
    '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    '<meta name="robots" content="noindex,nofollow">'
)


def page(title, body, active=""):
    links = [("/", "Overview"), ("/codes", "Access codes"), ("/analytics", "Analytics"),
             ("/roster", "Roster"), ("/requests", "Requests")]
    nav = "".join(
        '<a href="' + href + '"' + (' class="on"' if active == href else "") + ">" + label + "</a>"
        for href, label in links
    )
    return (
        HEAD
        + "<title>" + e(title) + " — HelloVoice catalogue</title>"
        + '<link rel="stylesheet" href="/static/admin.css"></head><body>'
        + '<header class="top"><div class="wrap">'
        + '<a class="brand" href="/"><img src="/static/logo.webp" alt="HelloVoice" '
          'height="26"><span>catalogue admin</span></a>'
        + "<nav>" + nav + '<a href="/logout">Sign out</a></nav>'
        + '</div></header><main class="wrap">' + body + "</main></body></html>"
    )


def simple(title, message):
    return page(title, "<h1>" + e(title) + "</h1><p class='sub'>" + e(message) + "</p>")


def login_page(error=None):
    err = "<div class='err'>Email or password not recognised.</div>" if error else ""
    return (
        HEAD
        + "<title>Sign in — HelloVoice catalogue</title>"
        + '<link rel="stylesheet" href="/static/admin.css"></head><body>'
        + '<main class="wrap login">'
        + '<img src="/static/logo.webp" alt="HelloVoice" height="30" '
          'style="margin-bottom:22px">'
        + '<h1>Catalogue admin</h1>'
        + "<p class='sub'>Sign in to manage codes, roster and requests.</p>"
        + err
        + "<form method='post' action='/login' class='card'>"
        + "<div style='margin-bottom:14px'><label>Email</label>"
        + "<input name='email' type='email' required autofocus autocomplete='username'></div>"
        + "<div style='margin-bottom:18px'><label>Password</label>"
        + "<input name='password' type='password' required autocomplete='current-password'></div>"
        + "<button class='btn' style='width:100%'>Sign in</button></form>"
        + "</main></body></html>"
    )


def dashboard(s, events, who, message=None, error=None):
    rows = "".join(
        "<tr><td>" + e(ev["kind"]) + "</td><td>" + e(ev["label"] or "—") + "</td>"
        + "<td class='muted'>" + e(ev["detail"] or "") + "</td>"
        + "<td class='right muted'>" + ago(ev["at"]) + "</td></tr>"
        for ev in events
    ) or "<tr><td colspan='4' class='muted'>Nothing yet.</td></tr>"

    banner = ""
    if message:
        banner += "<div class='ok'>" + e(message) + "</div>"
    if error:
        banner += "<div class='err'>" + e(error) + "</div>"

    body = (
        "<h1>Overview</h1><p class='sub'>Signed in as " + e(who["email"]) + ". Last 30 days.</p>"
        + banner + "<div class='grid'>"
        + "<div class='stat'><b>" + str(s["unlocks"]) + "</b><span>Catalogue opens</span></div>"
        + "<div class='stat'><b>" + str(s["live_codes"]) + "</b><span>Live access codes</span></div>"
        + "<div class='stat'><b>" + str(s["requests"]) + "</b><span>Quote requests</span></div>"
        + "<div class='stat'><b>" + str(s["failures"]) + "</b><span>Rejected attempts</span></div>"
        + "</div><h2>Recent activity</h2><div class='card'><table><thead><tr>"
        + "<th>Event</th><th>Code</th><th>Detail</th><th class='right'>When</th>"
        + "</tr></thead><tbody>" + rows + "</tbody></table></div>"
        + "<h2>Change your password</h2>"
        + "<form method='post' action='/password' class='card'><div class='row'>"
        + "<div><label>Current password</label><input name='current' type='password' required></div>"
        + "<div><label>New password</label><input name='new' type='password' required></div>"
        + "</div><button class='btn'>Update password</button></form>"
    )
    return page("Overview", body, "/")


def codes_page(codes, new_code=None, error=None):
    banner = ""
    if new_code:
        banner += (
            "<div class='note'><strong>New code — copy it now.</strong> "
            "It is stored only as a hash, so this is the one time it can be shown."
            "<div style='margin-top:10px'><span class='reveal'>" + e(new_code)
            + "</span></div></div>"
        )
    if error:
        banner += "<div class='err'>" + e(error) + "</div>"

    rows = []
    for c in codes:
        ok, reason = code_state(c)
        cls = "live" if ok else ("warn" if reason in ("expired", "exhausted") else "dead")
        used = str(c["uses"]) + (" / " + str(c["max_uses"]) if c["max_uses"] else "")
        revoke = ""
        if ok:
            confirm = "return confirm('Revoke this code? Anyone using it loses access at once.')"
            revoke = (
                "<form method='post' action='/codes/revoke' class='inline' onsubmit=\""
                + confirm + "\"><input type='hidden' name='id' value='" + str(c["id"])
                + "'><button class='btn small danger'>Revoke</button></form>"
            )
        rows.append(
            "<tr><td><strong>" + e(c["label"]) + "</strong><br><code>••••-" + e(c["hint"])
            + "</code></td><td><span class='pill " + cls + "'>" + e(reason) + "</span></td>"
            + "<td>" + used + "</td><td class='muted'>" + ts(c["expires_at"]) + "</td>"
            + "<td class='muted'>" + ago(c["last_used"]) + "</td>"
            + "<td class='right'>" + revoke + "</td></tr>"
        )
    body_rows = "".join(rows) or "<tr><td colspan='6' class='muted'>No codes yet.</td></tr>"

    body = (
        "<h1>Access codes</h1><p class='sub'>One code per client. Checked on the server, "
        "so expiry and revocation take effect immediately — not whenever a browser feels "
        "like it.</p>" + banner
        + "<form method='post' action='/codes/new' class='card'><div class='row'>"
        + "<div><label>Issued to</label><input name='label' placeholder='Alpha Plus' required></div>"
        + "<div><label>Expires in (days)</label>"
          "<input name='days' type='number' min='1' placeholder='30'></div>"
        + "<div><label>Max uses</label>"
          "<input name='max_uses' type='number' min='1' placeholder='unlimited'></div>"
        + "</div><button class='btn'>Generate code</button></form>"
        + "<div class='card'><table><thead><tr><th>Code</th><th>State</th><th>Uses</th>"
        + "<th>Expires</th><th>Last used</th><th></th></tr></thead><tbody>"
        + body_rows + "</tbody></table></div>"
    )
    return page("Access codes", body, "/codes")


def analytics_page(s, events, days):
    counts = [d["n"] for d in s["by_day"]] or [1]
    peak = max(counts)
    bars = "".join(
        "<div style='height:" + str(max(2, int(d["n"] / peak * 88))) + "px' title='"
        + e(d["d"]) + ": " + str(d["n"]) + "'></div>"
        for d in s["by_day"]
    ) or "<div style='height:2px'></div>"

    by_code = "".join(
        "<tr><td>" + e(r["label"]) + " <code>••••-" + e(r["hint"]) + "</code></td><td>"
        + str(r["n"]) + "</td><td class='muted'>" + ago(r["last"]) + "</td></tr>"
        for r in s["by_code"]
    ) or "<tr><td colspan='3' class='muted'>No opens yet.</td></tr>"

    top = "".join(
        "<tr><td><code>" + e(r["detail"]) + "</code></td><td>" + str(r["n"]) + "</td></tr>"
        for r in s["top_creators"] if r["detail"]
    ) or "<tr><td colspan='2' class='muted'>No shortlisting recorded yet.</td></tr>"

    log = "".join(
        "<tr><td>" + e(ev["kind"]) + "</td><td>" + e(ev["label"] or "—") + "</td>"
        + "<td class='muted'>" + e(ev["detail"] or "") + "</td>"
        + "<td class='muted'>" + e((ev["ip"] or "")[:24]) + "</td>"
        + "<td class='right muted'>" + ts(ev["at"]) + "</td></tr>"
        for ev in events
    ) or "<tr><td colspan='5' class='muted'>Nothing recorded yet.</td></tr>"

    body = (
        "<h1>Analytics</h1><p class='sub'>Last " + str(days) + " days. "
        "<a href='/analytics?days=7'>7</a> · <a href='/analytics?days=30'>30</a> · "
        "<a href='/analytics?days=90'>90</a></p><div class='grid'>"
        + "<div class='stat'><b>" + str(s["unlocks"]) + "</b><span>Opens</span></div>"
        + "<div class='stat'><b>" + str(s["failures"]) + "</b><span>Rejected attempts</span></div>"
        + "<div class='stat'><b>" + str(s["requests"]) + "</b><span>Quote requests</span></div>"
        + "</div><h2>Opens per day</h2><div class='card'><div class='bars'>" + bars + "</div></div>"
        + "<h2>By code</h2><div class='card'><table><thead><tr><th>Code</th><th>Opens</th>"
        + "<th>Last</th></tr></thead><tbody>" + by_code + "</tbody></table></div>"
        + "<h2>Most shortlisted creators</h2><div class='card'><table><thead><tr>"
        + "<th>Creator</th><th>Times shortlisted</th></tr></thead><tbody>" + top
        + "</tbody></table></div><h2>Event log</h2><div class='card'><table><thead><tr>"
        + "<th>Event</th><th>Code</th><th>Detail</th><th>IP</th>"
        + "<th class='right'>When</th></tr></thead><tbody>" + log + "</tbody></table></div>"
    )
    return page("Analytics", body, "/analytics")


def creator_form(c):
    """Add/edit form. `c` is None when adding a new creator."""
    def val(key, default=""):
        if c is not None and c[key] is not None:
            return e(c[key])
        return default

    tier_opts = "".join(
        "<option" + (" selected" if c is not None and c["tier"] == t else "") + ">" + t + "</option>"
        for t in ("Nano", "Micro", "Mid-Tier", "Macro")
    )
    plat_opts = "".join(
        "<option" + (" selected" if c is not None and c["platform"] == p else "") + ">" + p + "</option>"
        for p in ("Instagram", "TikTok")
    )
    checked = "checked" if (c is None or c["active"]) else ""
    readonly = "readonly" if c is not None else ""
    action_label = "Save changes" if c is not None else "Add creator"

    # A thumbnail of what is currently set, so you can see before replacing.
    thumb = ""
    if c is not None and c["photo"]:
        thumb = ("<img class='thumb' src='/photo/" + e(c["photo"].split("?")[0])
                 + "' alt='' loading='lazy'>")
    photo_field = (
        "<div class='photo-pick'>" + thumb
        + "<input type='file' name='photo_file' accept='image/*'></div>"
        + "<input type='hidden' name='photo' value='" + val("photo") + "'>"
    )

    # Adding: the code is derived from the tier and what is already stored, so
    # it is never typed by hand and never collides.
    if c is not None:
        code_field = ("<div><label>Code</label><input name='code' value='" + val("code")
                      + "' readonly></div>")
    else:
        code_field = ("<div><label>Code</label><input value='assigned automatically' "
                      "disabled title='Derived from the tier and the existing roster'>"
                      "</div>")

    delete_form = ""
    if c is not None:
        confirm = "return confirm('Delete " + e(c["code"]) + " permanently?')"
        delete_form = (
            "<form method='post' action='/roster/delete' class='inline' onsubmit=\""
            + confirm + "\"><input type='hidden' name='code' value='" + e(c["code"])
            + "'><button class='btn small danger' style='margin-left:8px'>Delete</button></form>"
        )

    return (
        "<form method='post' action='/roster/save' enctype='multipart/form-data' "
        "style='margin-top:12px'><div class='row'>"
        + code_field
        + "<div><label>Name</label><input name='name' value='" + val("name") + "' required></div>"
        + "<div><label>Platform</label><select name='platform'>" + plat_opts + "</select></div>"
        + "<div><label>Handle</label><input name='handle' value='" + val("handle")
        + "' placeholder='no @'></div></div><div class='row'>"
        + "<div><label>Followers</label><input name='followers' value='" + val("followers") + "'></div>"
        + "<div><label>Tier</label><select name='tier'>" + tier_opts + "</select></div>"
        + "<div><label>City</label><input name='city' value='" + val("city") + "'></div>"
        + "<div><label>Interest</label><input name='interest' value='" + val("interest") + "'></div>"
        + "</div><div class='row'>"
        + "<div><label>Photo</label>" + photo_field + "</div>"
        + "<div><label>Sort</label><input name='sort' value='" + val("sort", "0") + "'></div>"
        + "<div><label>Note (internal)</label><input name='note' value='" + val("note") + "'></div>"
        + "<div><label>Visible</label><div style='padding-top:9px'>"
        + "<input type='checkbox' name='active' value='1' " + checked
        + " style='width:auto'> Show to clients</div></div></div>"
        + "<button class='btn'>" + action_label + "</button>" + delete_form + "</form>"
    )


def roster_page(creators, error=None, message=None):
    err = ""
    if error:
        err += "<div class='err'>" + e(error) + "</div>"
    if message:
        err += "<div class='ok'>" + e(message) + "</div>"

    def row(c):
        hidden = "" if c["active"] else " <span class='pill dead'>hidden</span>"
        handle = "@" + c["handle"] if c["handle"] else "—"
        if c["photo"]:
            shot = ("<img class='thumb sm' src='/photo/" + e(c["photo"].split("?")[0])
                    + "' alt='' loading='lazy'>")
        else:
            shot = "<span class='thumb sm none'>—</span>"
        return (
            "<tr><td>" + shot + "</td><td><code>" + e(c["code"]) + "</code></td>"
            + "<td><strong>" + e(c["name"])
            + "</strong>" + hidden + "</td><td>" + e(c["platform"])
            + "<br><span class='muted'>" + e(handle) + "</span></td><td>"
            + num(c["followers"]) + "</td><td>" + e(c["tier"]) + "</td><td>"
            + e(c["city"] or "—") + "</td><td class='right'><details>"
            + "<summary class='btn small ghost'>Edit</summary>" + creator_form(c)
            + "</details></td></tr>"
        )

    rows = "".join(row(c) for c in creators) or (
        "<tr><td colspan='8' class='muted'>Roster is empty — import it with seed.py.</td></tr>")

    body = (
        "<h1>Roster</h1><p class='sub'>" + str(len(creators))
        + " creators. Hidden ones stay in the database but never reach a client.</p>" + err
        + "<h2>Add a creator</h2><div class='card'>" + creator_form(None) + "</div>"
        + "<h2>Import a spreadsheet</h2><div class='card'>"
        + "<p class='sub' style='margin-bottom:16px'>Add many creators at once. "
          "Start from the template so the headings match — a code left blank is "
          "assigned automatically, and a code that already exists is updated "
          "rather than duplicated. Photos are never lost on re-import.</p>"
        + "<p class='sub' style='margin-bottom:16px'><strong>Nothing is written "
          "unless every row is valid.</strong> If a tier or platform is wrong the "
          "whole file is rejected and the offending rows are named, so the roster "
          "is never left half updated.</p>"
        + "<a class='btn ghost' href='/roster/template'>Download the template</a>"
        + "<form method='post' action='/roster/import' enctype='multipart/form-data' "
          "style='margin-top:18px'>"
        + "<div class='row'><div><label>Spreadsheet (.csv or .xlsx)</label>"
        + "<input type='file' name='sheet' accept='.csv,.xlsx,.xlsm,text/csv' required></div>"
        + "<div style='align-self:end'><button class='btn'>Import</button></div></div>"
        + "<p class='muted' style='font-size:13px;margin:0'>Excel files need "
          "openpyxl on the server; if it is missing you will be told to save as "
          "CSV rather than left guessing.</p></form></div>"
        + "<h2>Everyone</h2><div class='card'><table><thead><tr><th></th><th>Code</th>"
        + "<th>Name</th><th>Platform</th><th>Followers</th><th>Tier</th><th>City</th>"
        + "<th></th></tr></thead><tbody>" + rows + "</tbody></table></div>"
    )
    return page("Roster", body, "/roster")


def requests_page(requests, creators, tiers=None):
    """Each request as a card: who asked, and every creator they chose shown
    the way the client saw them — photo, handle, reach, tier, price."""
    by_code = {c["code"]: c for c in creators}
    tiers = tiers or {}

    def pick_card(code):
        c = by_code.get(code)
        if c is None:
            return ("<div class='pick'><div class='gone'><code>" + e(code)
                    + "</code><br>No longer in the roster.</div></div>")

        if c["photo"]:
            shot = ("<img class='thumb' src='/photo/" + e(c["photo"].split("?")[0])
                    + "' alt='' loading='lazy'>")
        else:
            shot = "<span class='thumb none'>—</span>"

        profile = ""
        if c["handle"]:
            base = ("https://www.instagram.com/" if c["platform"] == "Instagram"
                    else "https://www.tiktok.com/@")
            url = base + c["handle"] + ("/" if c["platform"] == "Instagram" else "")
            profile = ("<a href=\"" + e(url) + "\" target='_blank' rel='noopener'>@"
                       + e(c["handle"]) + "</a>")

        price = "—"
        t = tiers.get(c["tier"])
        if t:
            price = format(t[0], ",") + " – " + format(t[1], ",") + " SAR"

        rows = [("Followers", num(c["followers"])), ("Platform", e(c["platform"])),
                ("City", e(c["city"] or "—")), ("Tier", e(c["tier"])), ("Price", price)]
        if c["interest"]:
            rows.insert(3, ("Interest", e(c["interest"])))
        dl = "".join("<div><dt>" + k + "</dt><dd>" + v + "</dd></div>" for k, v in rows)

        hidden = "" if c["active"] else " <span class='pill dead'>hidden</span>"
        return (
            "<div class='pick'><div class='pick-top'>" + shot
            + "<div class='pick-id'><code>" + e(c["code"]) + "</code>"
            + "<strong>" + e(c["name"]) + hidden + "</strong>" + profile
            + "</div></div><dl>" + dl + "</dl></div>"
        )

    def card(r):
        try:
            picks = json.loads(r["selection"])
        except Exception:
            picks = []

        lo = hi = 0
        split = {}
        for code in picks:
            c = by_code.get(code)
            if not c:
                continue
            split[c["tier"]] = split.get(c["tier"], 0) + 1
            t = tiers.get(c["tier"])
            if t:
                lo += t[0]
                hi += t[1]
        total = (format(lo, ",") + " – " + format(hi, ",") + " SAR") if lo else "—"
        split_txt = ", ".join(k + " " + str(v) for k, v in sorted(split.items())) or "—"

        handled = bool(r["handled_at"])
        btn = (
            "<form method='post' action='/requests/handled' class='inline'>"
            "<input type='hidden' name='id' value='" + str(r["id"]) + "'>"
            "<input type='hidden' name='handled' value='" + ("0" if handled else "1") + "'>"
            "<button class='btn small" + (" ghost" if handled else "") + "'>"
            + ("Reopen" if handled else "Mark handled") + "</button></form>"
        )

        contact = []
        if r["email"]:
            contact.append("<a href=\"mailto:" + e(r["email"]) + "\">" + e(r["email"]) + "</a>")
        if r["phone"]:
            tel = "".join(ch for ch in r["phone"] if ch.isdigit() or ch == "+")
            contact.append("<a href=\"tel:" + e(tel) + "\">" + e(r["phone"]) + "</a>")

        flag = "<span class='pill'>handled</span> " if handled else ""
        return (
            "<div class='req" + (" done" if handled else "") + "'><div class='req-head'>"
            + "<div class='req-who'><h3>" + e(r["company"] or "—") + "</h3>"
            + "<div class='muted'>" + e(r["name"] or "") + "</div>"
            + "<div>" + " · ".join(contact) + "</div></div>"
            + "<div class='req-meta'>" + flag + btn
            + "<div style='margin-top:8px'>" + ts(r["at"]) + "</div>"
            + "<div>via <strong>" + e(r["code_label"] or "—") + "</strong></div></div></div>"
            + "<div class='req-sum'>"
            + "<div><b>" + str(len(picks)) + "</b><span>creators</span></div>"
            + "<div><b>" + total + "</b><span>indicative range</span></div>"
            + "<div><b>" + e(r["selection_name"] or "—") + "</b><span>selection</span></div>"
            + "<div><b>" + split_txt + "</b><span>tier split</span></div>"
            + "</div><div class='picks'>"
            + "".join(pick_card(code) for code in picks) + "</div></div>"
        )

    body_cards = "".join(card(r) for r in requests) or (
        "<div class='card muted'>No requests yet.</div>")

    body = (
        "<h1>Quote requests</h1><p class='sub'>" + str(len(requests))
        + " requests. Each shows the client's details and every creator they chose, "
          "exactly as they saw them.</p>" + body_cards
    )
    return page("Requests", body, "/requests")
