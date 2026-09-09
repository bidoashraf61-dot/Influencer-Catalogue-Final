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
import re
import time
from datetime import datetime, timezone

import links
from db import code_state, now, split_cities, split_profiles, PLATFORMS


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
.brand span{opacity:.55;font-weight:400;font-size:14px;white-space:nowrap}
.login img{filter:invert(1)}
nav a{display:inline-block;padding:6px 0;margin-right:20px;color:#fff;
text-decoration:none;opacity:.65;font-size:14px;border-bottom:2px solid transparent}
nav a:hover{opacity:1}
nav a.on{opacity:1;border-bottom-color:var(--lime)}
h1{font-size:26px;margin:32px 0 4px}
h2{font-size:17px;margin:32px 0 12px}
.sub{color:var(--gray);margin:0 0 24px}
/* the 7/30/90 range tabs; nav a.on is the top nav and does not reach here */
.sub a.on{color:var(--ink);font-weight:600;text-decoration:none;
background:var(--lime);padding:2px 9px;border-radius:999px}
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
.pager{display:flex;align-items:center;justify-content:center;gap:6px;flex-wrap:wrap;
  margin:18px 0 4px;font-size:14px}
.pager a,.pager .pgnow,.pager .pgoff{padding:7px 12px;border-radius:8px;line-height:1;
  text-decoration:none}
.pager a{color:var(--ink);border:1px solid var(--line)}
.pager a:hover{background:var(--white)}
.pager .pgnow{background:var(--ink);color:#fff;font-weight:600}
.pager .pgoff{color:var(--gray);opacity:.55}
.pager .pgnums{display:flex;gap:6px;flex-wrap:wrap;margin:0 6px}
.btn.danger{border-color:var(--red);color:var(--red);background:transparent}
.note{background:#fffbe6;border:1px solid #f0e2a8;border-radius:10px;padding:14px 16px;margin:16px 0}
.err{background:#fdeaea;border:1px solid #f5c2c2;border-radius:10px;padding:12px 16px;
margin:16px 0;color:#8a1a1a}
.ok{background:#e7f6ec;border:1px solid #b9e3c6;border-radius:10px;padding:12px 16px;
margin:16px 0;color:#14602b}
.reveal{font:20px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.08em;
background:var(--ink);color:var(--lime);padding:14px 18px;border-radius:10px;display:inline-block}
.copyrow{display:inline-flex;align-items:center;gap:8px;flex-wrap:wrap}
.code-full{font:14px ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.04em;
background:#f0f0ee;border:1px solid rgba(18,18,18,.12);border-radius:7px;
padding:4px 9px;user-select:all;white-space:nowrap}
.code-full.reveal{font-size:20px;letter-spacing:.08em;padding:14px 18px;border-radius:10px;
background:var(--ink);color:var(--lime);border-color:var(--ink)}
.btn.tiny{padding:4px 12px;font-size:12px}
/* --- analytics ------------------------------------------------------ */
.stat.hero b{font-size:38px}
.stat .ctx{display:block;color:var(--gray);font-size:12px;margin-top:6px}
.chart{width:100%;height:auto;display:block;overflow:visible}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:13px;color:var(--gray);
margin:0 0 14px}
.range{display:flex;gap:14px;align-items:end;flex-wrap:wrap;background:var(--white);
border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:0 0 24px}
.range input[type=date]{font:inherit;font-size:15px;padding:9px 12px;
border:1px solid var(--line);border-radius:9px;background:var(--white);
color:var(--ink);min-height:42px}
.range input[type=date]:focus{outline:none;border-color:var(--ink)}
.range label{margin-bottom:5px}
tr.editrow > td{background:#f6f5f3;border-bottom:2px solid var(--ink);
padding:18px 20px 24px;text-align:left}
tr.editrow form{max-width:1100px}
.rsearch{display:flex;gap:10px;align-items:center;margin:0 0 14px;flex-wrap:wrap}
.rsearch input{font:inherit;font-size:15px;padding:9px 13px;min-width:260px;
border:1px solid var(--line);border-radius:9px;background:var(--white)}
.rsearch input:focus{outline:none;border-color:var(--ink)}
.tier-row{display:grid;gap:12px;align-items:end;padding:12px 0;
border-bottom:1px solid var(--line);
grid-template-columns:minmax(110px,1.1fr) 70px 96px 96px minmax(96px,1fr) 100px 100px 58px auto}
.tier-row:last-of-type{border-bottom:0}
.tier-row input{font:inherit;font-size:15px;padding:9px 11px;width:100%;
border:1px solid var(--line);border-radius:9px;background:var(--white);
color:var(--ink);min-height:40px;box-sizing:border-box}
.tier-row input:focus{outline:none;border-color:var(--ink)}
.tier-act{display:flex;align-items:center;gap:6px;white-space:nowrap}
@media (max-width:900px){.tier-row{grid-template-columns:1fr 1fr}
.tier-act{grid-column:1/-1}}
.profiles{grid-column:1/-1}
.prow{display:grid;grid-template-columns:150px 1fr 130px;gap:10px;margin-bottom:8px}
.profiles>button{margin-top:2px}
.prow select,.prow input{font:inherit;font-size:15px;padding:9px 11px;width:100%;
border:1px solid var(--line);border-radius:9px;background:var(--white);
color:var(--ink);min-height:40px;box-sizing:border-box}
.prow select:focus,.prow input:focus{outline:none;border-color:var(--ink)}
@media (max-width:900px){.prow{grid-template-columns:150px 1fr}
.prow input[name=p_followers]{grid-column:2}}
@media (max-width:640px){.prow{grid-template-columns:1fr}
.prow input[name=p_followers]{grid-column:auto}}
.cities{grid-column:1/-1}
.ticks{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}
.tick{display:inline-flex;align-items:center;gap:7px;margin:0;padding:7px 13px;
border:1px solid var(--line);border-radius:999px;background:var(--white);
cursor:pointer;text-transform:none;letter-spacing:normal;font-size:14px;
min-height:38px}
.tick:hover{border-color:var(--ink)}
.tick input{margin:0;width:15px;height:15px;accent-color:var(--ink)}
.tick span{color:var(--ink);font-weight:500}
.tick:has(input:checked){background:var(--ink);border-color:var(--ink)}
.tick:has(input:checked) span{color:#fff}
.legend span{display:inline-flex;align-items:center;gap:7px}
.legend i{width:11px;height:11px;border-radius:3px;display:inline-block}
.hb{display:grid;grid-template-columns:minmax(90px,auto) 1fr auto;gap:12px;
align-items:center;padding:7px 0;font-size:14px}
.hb .track{background:#f1efec;border-radius:999px;height:9px;overflow:hidden}
.hb .fill{display:block;height:100%;border-radius:999px;background:var(--ink)}
.hb .n{font-variant-numeric:tabular-nums;color:var(--gray);min-width:56px;
text-align:right}
.funnel{display:grid;gap:2px}
.fstep{display:grid;grid-template-columns:minmax(120px,auto) 1fr;gap:14px;
align-items:center;padding:6px 0}
.fstep .bar{height:34px;border-radius:8px;background:var(--ink);color:#fff;
display:flex;align-items:center;padding:0 12px;font-size:14px;font-weight:600;
min-width:46px;white-space:nowrap}
.fstep .drop{color:rgba(255,255,255,.62);font-size:12px;margin-left:10px;
font-weight:400}
.tface{width:38px;height:38px;border-radius:9px;object-fit:cover;display:block;
background:#f1efec}
.tface.none{display:grid;place-items:center;color:var(--gray);font-size:11px}
.split{display:grid;gap:20px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.empty{color:var(--gray);font-size:14px;padding:10px 0}
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


BASE = ""

# The dashboard's name. It shows in the browser tab, beside the logo in the
# header, and on the sign-in page — one constant so those three cannot drift.
NAME = "Influencer Catalogue Admin"


def set_base(prefix):
    """Called once at startup. Every href and form action is written through
    `u()`, so the dashboard works at the domain root or under /admin without
    any other change."""
    global BASE
    BASE = prefix or ""


def urlencode(**kw):
    """Query string from the parts that actually have a value, so a link does
    not carry `edit=&q=` and read as if something is set."""
    import urllib.parse
    return urllib.parse.urlencode({k: v for k, v in kw.items() if v})


def u(path):
    return (BASE + path) if path.startswith("/") else path


def page(title, body, active=""):
    items = [("/", "Overview"), ("/codes", "Access codes"), ("/analytics", "Analytics"),
             ("/roster", "Roster"), ("/requests", "Requests")]
    nav = "".join(
        '<a href="' + u(href) + '"' + (' class="on"' if active == href else "") + ">" + label + "</a>"
        for href, label in items
    )
    return (
        HEAD
        + "<title>" + e(title) + " — " + e(NAME) + "</title>"
        + '<link rel="stylesheet" href="' + u("/static/admin.css") + '"></head><body>'
        + '<header class="top"><div class="wrap">'
        + '<a class="brand" href="' + u("/") + '"><img src="' + u("/static/logo.webp") + '" alt="HelloVoice" '
          'height="26"><span>' + e(NAME) + "</span></a>"
        + "<nav>" + nav + '<a href="' + u("/logout") + '">Sign out</a></nav>'
        + '</div></header><main class="wrap">' + body + "</main></body></html>"
    )


def simple(title, message):
    return page(title, "<h1>" + e(title) + "</h1><p class='sub'>" + e(message) + "</p>")


def login_page(error=None, base=None):
    if base is not None:
        set_base(base)
    err = "<div class='err'>Email or password not recognised.</div>" if error else ""
    return (
        HEAD
        + "<title>Sign in — " + e(NAME) + "</title>"
        + '<link rel="stylesheet" href="' + u("/static/admin.css") + '"></head><body>'
        + '<main class="wrap login">'
        + '<img src="' + u("/static/logo.webp") + '" alt="HelloVoice" height="30" '
          'style="margin-bottom:22px">'
        + "<h1>" + e(NAME) + "</h1>"
        + "<p class='sub'>Sign in to manage codes, roster and requests.</p>"
        + err
        + "<form method='post' action='" + u("/login") + "' class='card'>"
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
        + "<form method='post' action='" + u("/password") + "' class='card'><div class='row'>"
        + "<div><label>Current password</label><input name='current' type='password' required></div>"
        + "<div><label>New password</label><input name='new' type='password' required></div>"
        + "</div><button class='btn'>Update password</button></form>"
    )
    return page("Overview", body, "/")


def copyable(text, extra=""):
    """A code shown in full with a one-click copy.

    navigator.clipboard is unavailable outside a secure context, which includes
    plain-http localhost in some browsers, so the fallback selects the text and
    uses execCommand. Either way the click leaves the code selected, so ctrl-C
    works even if both are blocked.
    """
    value = e(text)
    js = (
        "var t=this.previousElementSibling,v=t.textContent.trim();"
        "var r=document.createRange();r.selectNodeContents(t);"
        "var s=getSelection();s.removeAllRanges();s.addRange(r);"
        "var b=this,done=function(){b.textContent='Copied';"
        "setTimeout(function(){b.textContent='Copy'},1600)};"
        "if(navigator.clipboard&&navigator.clipboard.writeText){"
        "navigator.clipboard.writeText(v).then(done,function(){"
        "try{document.execCommand('copy');done()}catch(e){b.textContent='Press Ctrl-C'}})"
        "}else{try{document.execCommand('copy');done()}catch(e){b.textContent='Press Ctrl-C'}}"
    )
    cls = ("code-full " + extra).strip()
    return ("<span class='copyrow'><code class='" + cls + "'>" + value + "</code>"
            "<button type='button' class='btn tiny ghost' onclick=\"" + js + "\">Copy</button>"
            "</span>")


def codes_page(codes, new_code=None, error=None):
    banner = ""
    if new_code:
        banner += (
            "<div class='note'><strong>New code.</strong> "
            "It is kept on this page, so you can come back for it."
            "<div style='margin-top:10px'>" + copyable(new_code, "reveal") + "</div></div>"
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
                "<form method='post' action='" + u("/codes/revoke") + "' class='inline' onsubmit=\""
                + confirm + "\"><input type='hidden' name='id' value='" + str(c["id"])
                + "'><button class='btn small danger'>Revoke</button></form>"
            )
        # Codes issued before code_plain existed are hashed and gone; the last
        # four characters are all that was ever kept of them.
        plain = c["code_plain"] if "code_plain" in c.keys() else None
        shown = (copyable(plain) if plain else
                 "<code title='Issued before codes were stored — cannot be shown'>"
                 "••••-" + e(c["hint"]) + "</code>")
        rows.append(
            "<tr><td><strong>" + e(c["label"]) + "</strong><br>" + shown
            + "</td><td><span class='pill " + cls + "'>" + e(reason) + "</span></td>"
            + "<td>" + used + "</td><td class='muted'>" + ts(c["expires_at"]) + "</td>"
            + "<td class='muted'>" + ago(c["last_used"]) + "</td>"
            + "<td class='right'>" + revoke + "</td></tr>"
        )
    body_rows = "".join(rows) or "<tr><td colspan='6' class='muted'>No codes yet.</td></tr>"

    body = (
        "<h1>Access codes</h1><p class='sub'>One code per client. Checked on the server, "
        "so expiry and revocation take effect immediately — not whenever a browser feels "
        "like it.</p>" + banner
        + "<form method='post' action='" + u("/codes/new") + "' class='card'><div class='row'>"
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


def pretty_day(ts):
    return time.strftime("%-d %b %Y", time.gmtime(ts))


def pct(part, whole):
    return int(round(part * 100.0 / whole)) if whole else 0


def hbar(label, n, peak, colour=None, sub=None):
    """One labelled horizontal bar. Everything on this page that is a ranking
    uses these rather than a bare number column — the shape of a distribution
    is the thing you actually want to see."""
    width = str(pct(n, peak) if peak else 0)
    style = ("background:" + colour + ";") if colour else ""
    left = e(label) + ("<br><span class='muted' style='font-size:12px'>"
                       + e(sub) + "</span>" if sub else "")
    return ("<div class='hb'><div>" + left + "</div>"
            "<div class='track'><i class='fill' style='width:" + width + "%;"
            + style + "'></i></div>"
            "<div class='n'>" + str(n) + "</div></div>")


def activity_chart(by_day):
    """Opens and shortlists per day, with requests marked above the column.

    Drawn as SVG rather than divs so it can carry a real y-axis and gridlines.
    The old version was a row of unlabelled bars: you could see that something
    happened, but not how much or when.
    """
    if not by_day:
        return "<p class='empty'>Nothing recorded yet.</p>"

    W, H = 900.0, 230.0
    L, R, T, B = 38.0, 8.0, 12.0, 26.0        # gutters
    plot_w, plot_h = W - L - R, H - T - B
    peak = max([max(d["opens"], d["shortlists"]) for d in by_day] + [1])
    # A round top makes the gridline labels whole numbers rather than 3.67
    step = 1
    while peak / float(step) > 4:
        step *= 2 if step < 4 else 5
    top = step * int((peak + step - 1) / step) or 1

    n = len(by_day)
    slot = plot_w / n
    bw = min(9.0, max(2.0, slot / 2.6))

    out = ['<svg class="chart" viewBox="0 0 900 230" role="img" '
           'aria-label="Opens and shortlists per day">']

    # gridlines + y labels
    lines = int(top / step)
    for i in range(lines + 1):
        v = step * i
        y = T + plot_h - (v / float(top)) * plot_h
        out.append('<line x1="' + str(L) + '" y1="' + str(round(y, 1))
                   + '" x2="' + str(W - R) + '" y2="' + str(round(y, 1))
                   + '" stroke="#e7e4df" stroke-width="1"/>')
        out.append('<text x="' + str(L - 8) + '" y="' + str(round(y + 4, 1))
                   + '" text-anchor="end" font-size="11" fill="#8a8a8a">'
                   + str(v) + "</text>")

    for i, d in enumerate(by_day):
        cx = L + slot * i + slot / 2.0
        for j, (key, colour) in enumerate((("opens", "#121212"),
                                           ("shortlists", "#b9d400"))):
            val = d[key]
            if not val:
                continue
            h = (val / float(top)) * plot_h
            x = cx - bw - 1 + j * (bw + 2)
            out.append('<rect x="' + str(round(x, 1)) + '" y="'
                       + str(round(T + plot_h - h, 1)) + '" width="' + str(round(bw, 1))
                       + '" height="' + str(round(h, 1)) + '" rx="2" fill="' + colour
                       + '"><title>' + e(d["d"]) + " — " + str(val) + " "
                       + key + "</title></rect>")
        if d["requests"]:
            out.append('<circle cx="' + str(round(cx, 1)) + '" cy="' + str(T + 4)
                       + '" r="4" fill="#ff691e"><title>' + e(d["d"]) + " — "
                       + str(d["requests"]) + " quote request(s)</title></circle>")

    # axis + a readable number of date labels
    out.append('<line x1="' + str(L) + '" y1="' + str(T + plot_h) + '" x2="'
               + str(W - R) + '" y2="' + str(T + plot_h)
               + '" stroke="#121212" stroke-width="1"/>')
    every = max(1, int(n / 8))
    for i, d in enumerate(by_day):
        if i % every and i != n - 1:
            continue
        out.append('<text x="' + str(round(L + slot * i + slot / 2.0, 1)) + '" y="'
                   + str(H - 8) + '" text-anchor="middle" font-size="11" '
                   'fill="#8a8a8a">' + e(d["d"][5:]) + "</text>")
    out.append("</svg>")
    return "".join(out)


def funnel(s):
    """Issued -> opened -> shortlisted -> requested, as codes not events.

    The headline counts say how much happened; this says how far it got. A
    catalogue opened forty times that produced no shortlist is a different
    problem from one nobody opened.
    """
    steps = [
        ("Codes issued", s["codes_total"], "Every code that exists"),
        ("Opened", s["codes_opened"], "Entered the code and saw the roster"),
        ("Shortlisted", s["codes_shortlisted"], "Picked at least one creator"),
        ("Requested a quote", s["codes_requested"], "Sent the form back"),
    ]
    top = max([n for _, n, _ in steps] + [1])
    out = ["<div class='funnel'>"]
    prev = None
    for label, n, why in steps:
        w = max(4, pct(n, top))
        drop = ""
        if prev is not None:
            drop = ("<span class='drop'>" + str(pct(n, prev)) + "% of previous</span>"
                    if prev else "<span class='drop'>—</span>")
        out.append("<div class='fstep'><div>" + e(label)
                   + "<br><span class='muted' style='font-size:12px'>" + e(why)
                   + "</span></div>"
                   "<div><div class='bar' style='width:" + str(w) + "%'>"
                   + str(n) + "</div></div></div>")
        if drop:
            out[-1] = out[-1].replace("</div></div></div>", drop + "</div></div></div>")
        prev = n
    out.append("</div>")
    return "".join(out)


def analytics_page(s, events):
    def rank(rows, colour=None, key="k"):
        if not rows:
            return "<p class='empty'>Nothing recorded yet.</p>"
        peak = max(r["n"] for r in rows) or 1
        return "".join(hbar(r[key] or "—", r["n"], peak, colour) for r in rows)

    # ---- headline -------------------------------------------------------
    conv = pct(s["codes_requested"], s["codes_opened"])
    kpis = [
        ("Opens", s["unlocks"], str(s["codes_opened"]) + " of " + str(s["codes_total"])
         + " codes used", "hero"),
        ("Creators shortlisted", s["shortlists"],
         str(s["creators_touched"]) + " different creators", ""),
        ("Quote requests", s["requests"],
         str(conv) + "% of opened codes asked", "hero" if s["requests"] else ""),
        ("Rejected attempts", s["failures"],
         "wrong, expired or revoked codes", ""),
        ("Live codes", s["live_codes"], "not revoked or expired", ""),
    ]
    cards = "".join(
        "<div class='stat " + cls + "'><b>" + str(v) + "</b><span>" + e(t)
        + "</span><span class='ctx'>" + e(note) + "</span></div>"
        for t, v, note, cls in kpis)

    # ---- per client -----------------------------------------------------
    rows = []
    for c in s["by_code"]:
        ok, reason = code_state(c)
        cls = "live" if ok else ("warn" if reason in ("expired", "exhausted") else "dead")
        got = ("<span class='pill live'>yes</span>" if c["requests"]
               else "<span class='muted'>—</span>")
        rows.append(
            "<tr><td><strong>" + e(c["label"]) + "</strong><br>"
            "<code class='muted' style='font-size:12px'>••••-" + e(c["hint"])
            + "</code></td>"
            "<td><span class='pill " + cls + "'>" + e(reason) + "</span></td>"
            "<td>" + str(c["opens"]) + "</td><td>" + str(c["shortlists"]) + "</td>"
            "<td>" + got + "</td>"
            "<td class='right muted'>" + ago(c["last"]) + "</td></tr>")
    by_code = "".join(rows) or "<tr><td colspan='6' class='muted'>No codes yet.</td></tr>"

    # ---- creators, recognisable ------------------------------------------
    peak = max([r["n"] for r in s["top_creators"]] + [1])
    faces = []
    for r in s["top_creators"]:
        if r["photo"]:
            shot = ("<img class='tface' src='" + u("/photo/")
                    + e(str(r["photo"]).split("?")[0]) + "' alt='' loading='lazy'>")
        else:
            shot = "<span class='tface none'>—</span>"
        who = e(r["name"] or r["code"])
        meta = " · ".join(x for x in (r["tier"], r["platform"]) if x)
        faces.append(
            "<tr><td style='width:46px'>" + shot + "</td>"
            "<td><strong>" + who + "</strong><br>"
            "<span class='muted' style='font-size:12px'><code>" + e(r["code"])
            + "</code>" + (" · " + e(meta) if meta else "") + "</span></td>"
            "<td style='width:45%'><div class='track' style='background:#f1efec;"
            "border-radius:999px;height:9px;overflow:hidden'>"
            "<i style='display:block;height:100%;border-radius:999px;"
            "background:#121212;width:" + str(pct(r["n"], peak)) + "%'></i></div></td>"
            "<td class='right'>" + str(r["n"]) + "</td></tr>")
    top = "".join(faces) or ("<tr><td colspan='4' class='muted'>No shortlisting "
                             "recorded yet.</td></tr>")

    # ---- event log --------------------------------------------------------
    tone = {"unlock_ok": "live", "request": "live", "shortlist": "",
            "unlock_fail": "dead", "admin_fail": "dead"}
    log = "".join(
        "<tr><td><span class='pill " + tone.get(ev["kind"], "") + "'>"
        + e(ev["kind"].replace("_", " ")) + "</span></td>"
        + "<td>" + e(ev["label"] or "—") + "</td>"
        + "<td class='muted'>" + e(ev["detail"] or "") + "</td>"
        + "<td class='muted'>" + e((ev["ip"] or "")[:24]) + "</td>"
        + "<td class='right muted'>" + ts(ev["at"]) + "</td></tr>"
        for ev in events
    ) or "<tr><td colspan='5' class='muted'>Nothing recorded yet.</td></tr>"

    # ---- the range picker -------------------------------------------------
    # Two native date inputs, so the browser supplies its own calendar and its
    # own locale — a hand-built one would be a lot of JavaScript to arrive at
    # something worse on a phone.
    d_from = time.strftime("%Y-%m-%d", time.gmtime(s["start"]))
    d_to = time.strftime("%Y-%m-%d", time.gmtime(s["end"] - 86400))
    today = time.strftime("%Y-%m-%d", time.gmtime())
    span = s["span_days"]
    picker = (
        "<form class='range' method='get' action='" + u("/analytics") + "'>"
        "<div><label for='from'>From</label>"
        "<input type='date' id='from' name='from' value='" + e(d_from)
        + "' max='" + today + "'></div>"
        "<div><label for='to'>To</label>"
        "<input type='date' id='to' name='to' value='" + e(d_to)
        + "' max='" + today + "'></div>"
        "<button class='btn'>Apply</button>"
        "<span class='muted' style='font-size:13px'>" + str(span)
        + (" day" if span == 1 else " days")
        + (", by week" if s["bucket"] == "week" else "") + "</span>"
        "</form>")

    body = (
        "<h1>Analytics</h1>"
        "<p class='sub'>" + e(pretty_day(s["start"])) + " – "
        + e(pretty_day(s["end"] - 86400)) + "</p>"
        + picker
        + "<div class='grid'>" + cards + "</div>"

        + "<h2>Activity</h2><div class='card'>"
        + "<div class='legend'>"
          "<span><i style='background:#121212'></i>Opens</span>"
          "<span><i style='background:#b9d400'></i>Creators shortlisted</span>"
          "<span><i style='background:#ff691e;border-radius:999px'></i>"
          "Quote request</span></div>"
        + activity_chart(s["by_day"]) + "</div>"

        + "<h2>How far each code got</h2><div class='card'>" + funnel(s) + "</div>"

        + "<div class='split'>"
        + "<div><h2>What clients shortlist</h2><div class='card'>"
        + "<p class='muted' style='font-size:13px;margin:0 0 6px'>By tier</p>"
        + rank(s["by_tier"]) 
        + "<p class='muted' style='font-size:13px;margin:16px 0 6px'>By platform</p>"
        + rank(s["by_platform"], "#b9d400") + "</div></div>"
        + "<div><h2>Why codes were refused</h2><div class='card'>"
        + rank(s["fail_reasons"], "#ee1515") + "</div></div>"
        + "</div>"

        + "<h2>By client</h2><div class='card'><table><thead><tr><th>Code</th>"
        + "<th>State</th><th>Opens</th><th>Shortlisted</th><th>Asked for a quote</th>"
        + "<th class='right'>Last open</th></tr></thead><tbody>" + by_code
        + "</tbody></table></div>"

        + "<h2>Most shortlisted creators</h2><div class='card'><table><thead><tr>"
        + "<th></th><th>Creator</th><th></th><th class='right'>Times</th></tr></thead>"
        + "<tbody>" + top + "</tbody></table></div>"

        + "<h2>Event log</h2><div class='card'><table><thead><tr>"
        + "<th>Event</th><th>Code</th><th>Detail</th><th>IP</th>"
        + "<th class='right'>When</th></tr></thead><tbody>" + log + "</tbody></table></div>"
    )
    return page("Analytics", body, "/analytics")


def tier_row(t, count):
    """One tier as an editable form. Editing in place rather than behind a
    modal because the whole point is comparing the bands against each other."""
    name = e(t["name"])
    ident = re.sub(r"[^A-Za-z0-9]", "", t["name"]) or "tier"
    people = (str(count) + (" creator" if count == 1 else " creators")) if count \
        else "no creators yet"
    delete = ""
    if not count:
        confirm = "return confirm('Remove the " + name + " tier?')"
        delete = ("<form method='post' action='" + u("/tiers/delete")
                  + "' class='inline' onsubmit=\"" + confirm + "\">"
                  "<input type='hidden' name='name' value='" + name + "'>"
                  "<button class='btn small ghost'>Remove</button></form>")
    else:
        delete = ("<span class='muted' style='font-size:12px'>in use</span>")

    return (
        "<form method='post' action='" + u("/tiers/save") + "' class='tier-row'>"
        "<input type='hidden' name='was' value='" + name + "'>"
        "<div><label for='n" + ident + "'>Tier</label>"
        "<input id='n" + ident + "' name='name' value='" + name + "' required></div>"
        "<div><label for='c" + ident + "'>Code</label>"
        "<input id='c" + ident + "' name='code' value='" + e(t["code"])
        + "' size='4' maxlength='4' required title='The middle of a creator code, "
          "e.g. the MI in HV-MI-007'></div>"
        "<div><label for='f" + ident + "'>Price from</label>"
        "<input id='f" + ident + "' name='price_from' value='" + str(t["price_from"])
        + "' inputmode='numeric' required></div>"
        "<div><label for='t" + ident + "'>Price to</label>"
        "<input id='t" + ident + "' name='price_to' value='" + str(t["price_to"])
        + "' inputmode='numeric' required></div>"
        "<div><label for='r" + ident + "'>Reach label</label>"
        "<input id='r" + ident + "' name='reach' value='" + e(t["reach"] or "")
        + "' placeholder='10K – 50K'></div>"
        "<div><label for='rf" + ident + "'>Reach from</label>"
        "<input id='rf" + ident + "' name='reach_from' value='"
        + (str(t["reach_from"]) if t["reach_from"] is not None else "")
        + "' inputmode='numeric' placeholder='10000'></div>"
        "<div><label for='rt" + ident + "'>Reach to</label>"
        "<input id='rt" + ident + "' name='reach_to' value='"
        + (str(t["reach_to"]) if t["reach_to"] is not None else "")
        + "' inputmode='numeric' placeholder='blank = no ceiling'></div>"
        "<div><label for='s" + ident + "'>Order</label>"
        "<input id='s" + ident + "' name='sort' value='" + str(t["sort"])
        + "' size='2'></div>"
        "<div class='tier-act'><button class='btn small'>Save</button>" + delete
        + "<span class='muted' style='font-size:12px;margin-left:8px'>" + people
        + "</span></div></form>")


def tiers_section(tiers, used):
    rows = "".join(tier_row(t, used.get(t["name"], 0)) for t in tiers) or (
        "<p class='muted'>No tiers yet — add the first one below.</p>")
    return (
        "<h2>Tiers &amp; pricing</h2><div class='card'>"
        "<p class='sub' style='margin-bottom:16px'>Every creator is priced by "
        "their tier — there is no price on a creator, so changing a band here "
        "re-prices everyone on it at once, on the cards, in the selection total "
        "and in the quote.</p>"
        "<p class='sub' style='margin-bottom:18px'><strong>Code</strong> is the "
        "middle of a creator code — the <code>MI</code> in <code>HV-MI-007</code> "
        "— and is used when the next code is assigned. <strong>Reach label</strong> "
        "is the text shown on the catalogue ticker; <strong>Reach from/to</strong> "
        "are that same band as numbers, and are what places a creator in a tier "
        "from their largest platform. Leave <em>Reach to</em> empty on the top "
        "tier so it has no ceiling. <strong>Order</strong> sets the order tiers "
        "appear in, smallest first.</p>"
        + rows
        + "<h3 style='margin:22px 0 10px;font-size:15px'>Add a tier</h3>"
        "<form method='post' action='" + u("/tiers/save") + "' class='tier-row'>"
        "<div><label>Tier</label><input name='name' placeholder='Mega' required></div>"
        "<div><label>Code</label><input name='code' placeholder='MG' size='4' "
        "maxlength='4' required></div>"
        "<div><label>Price from</label><input name='price_from' inputmode='numeric' "
        "required></div>"
        "<div><label>Price to</label><input name='price_to' inputmode='numeric' "
        "required></div>"
        "<div><label>Reach label</label><input name='reach' placeholder='1M+'></div>"
        "<div><label>Reach from</label><input name='reach_from' "
        "inputmode='numeric' placeholder='1000000'></div>"
        "<div><label>Reach to</label><input name='reach_to' "
        "inputmode='numeric' placeholder='blank = no ceiling'></div>"
        "<div><label>Order</label><input name='sort' value='5' size='2'></div>"
        "<div class='tier-act'><button class='btn'>Add tier</button></div>"
        "</form></div>")


def profile_field(c):
    """One row per platform the creator is on: which platform, and the link.

    A link, not a username. Profile URLs are not all one shape — an
    agency-managed account, a vanity path, a Facebook page id — and building a
    URL from a handle worked for Instagram and TikTok and nothing else.
    Pasting what is in the address bar always works.
    """
    rows = split_profiles(c["profiles"] if c is not None else None)
    # One blank row to start, and a button for the rest. Two fixed spares meant
    # a creator on four platforms had to be saved and reopened twice.
    slots = rows + [{"platform": "", "url": "", "followers": None}]

    out = []
    for row in slots:
        options = "<option value=''>—</option>" + "".join(
            "<option" + (" selected" if row["platform"] == p else "") + ">" + e(p)
            + "</option>" for p in PLATFORMS)
        # A platform this creator is on that is not in the list still shows.
        if row["platform"] and row["platform"] not in PLATFORMS:
            options += "<option selected>" + e(row["platform"]) + "</option>"
        out.append(
            "<div class='prow'>"
            "<select name='p_platform'>" + options + "</select>"
            "<input name='p_url' value='" + e(row["url"]) + "' "
            "placeholder='https://www.instagram.com/username' inputmode='url'>"
            "<input name='p_followers' value='"
            + (str(row["followers"]) if row.get("followers") else "")
            + "' placeholder='followers' inputmode='numeric'>"
            "</div>")

    # Clones the last row rather than carrying a template string: the row's
    # markup is written once, above, so the two cannot drift apart.
    add = (
        "var box=this.parentNode;"
        "var rows=box.querySelectorAll('.prow');"
        "var row=rows[rows.length-1].cloneNode(true);"
        "var f=row.querySelectorAll('input');"
        "for(var i=0;i<f.length;i++){f[i].value='';}"
        "row.querySelector('select').selectedIndex=0;"
        "box.insertBefore(row,this);"
        "row.querySelector('select').focus();")

    return ("<div class='row'><div class='profiles'>"
            "<label>Profiles</label>"
            "<div class='muted' style='margin:0 0 10px;font-size:13px'>Pick the "
            "platform, paste the full link, and put the followers on that "
            "profile. Add a row for each one — the same platform twice is fine "
            "if a creator runs two accounts. Clearing a row removes it. The "
            "Followers field below is the headline figure: leave it empty and "
            "it is the sum of these.</div>"
            + "".join(out)
            + "<button type='button' class='btn small ghost' onclick=\"" + add
            + "\">+ Add another profile</button>"
            "<div class='muted reach-note' style='margin-top:8px;font-size:13px'></div>"
            "</div></div>")


def interest_field(c, interests):
    """Interests as a multi-select, the same shape as the cities.

    A creator covers skincare AND hair care; one free-text box meant the same
    category arrived spelled three ways and the catalogue's Interest filter
    could never group anything.
    """
    chosen = split_cities(c["interest"] if c is not None else "")
    lower = [x.lower() for x in chosen]
    options = list(interests or [])
    for one in chosen:
        if one.lower() not in [o.lower() for o in options]:
            options.append(one)

    boxes = "".join(
        "<label class='tick'><input type='checkbox' name='interest' value='" + e(o) + "'"
        + (" checked" if o.lower() in lower else "") + "><span>" + e(o) + "</span></label>"
        for o in options) or "<span class='muted' style='font-size:13px'>None yet.</span>"

    return ("<div class='cities'><label>Interests</label>"
            "<div class='ticks'>" + boxes + "</div>"
            "<input name='interest_new' value='' placeholder='Add a category, or "
            "several separated by commas'></div>")


def city_field(c, cities):
    """Multi-select over the cities already in use, plus a box for new ones.

    A creator who works Riyadh and Jeddah is one creator, not two rows, and the
    catalogue counts them under both.
    """
    chosen = split_cities(c["city"] if c is not None else "")
    lower = [x.lower() for x in chosen]
    options = list(cities or [])
    # Anything on this creator that is not yet a known option still needs a
    # ticked box, or saving the form would silently drop it.
    for city in chosen:
        if city.lower() not in [o.lower() for o in options]:
            options.append(city)

    boxes = "".join(
        "<label class='tick'><input type='checkbox' name='city' value='" + e(o) + "'"
        + (" checked" if o.lower() in lower else "") + "><span>" + e(o) + "</span></label>"
        for o in options) or "<span class='muted' style='font-size:13px'>None yet.</span>"

    return ("<div class='cities'><label>City</label>"
            "<div class='ticks'>" + boxes + "</div>"
            "<input name='city_new' value='' placeholder='Add a city, or several "
            "separated by commas'></div>")


def reach_script(bands):
    """Sum the per-platform followers, and pick the tier from the largest one.

    The total is the sum because that is what "total reach" means. The TIER is
    not: a creator with 30K on each of four platforms has four Micro audiences,
    not one Macro one. Reach is how far a single post travels, and no post
    reaches the total — so the band is chosen by the biggest single platform.

    The bands are printed here from the database rather than hard-coded, so
    editing a tier's Reach from/to changes this immediately.
    """
    return ("<script>window.HV_BANDS=" + json.dumps(
        [{"name": name, "from": low, "to": high} for name, low, high in bands])
        + ";" + """
(function(){
  function num(el){ var v=(el.value||"").replace(/[^0-9]/g,""); return v?parseInt(v,10):0; }
  function tierFor(n){
    if(!n) return null;
    var bands=window.HV_BANDS||[], best=null;
    for(var i=0;i<bands.length;i++){
      var b=bands[i], lo=b.from||0;
      if(n>=lo && (b.to==null || n<b.to)) return b.name;
      if(n>=lo) best=b.name;              // above every band: the largest tier
    }
    return best;
  }
  function recalc(form){
    var rows=form.querySelectorAll(".prow"), total=0, biggest=0, any=false;
    for(var i=0;i<rows.length;i++){
      var f=rows[i].querySelector("input[name=p_followers]");
      var url=rows[i].querySelector("input[name=p_url]");
      if(!f||!url||!url.value.trim()) continue;
      var v=num(f);
      if(v>0){ any=true; total+=v; if(v>biggest) biggest=v; }
    }
    var headline=form.querySelector("input[name=followers]");
    if(headline && any){
      headline.value=total.toLocaleString("en-US");
      headline.setAttribute("data-auto","1");
    }
    var tier=form.querySelector("select[name=tier]");
    var want=tierFor(biggest);
    if(tier && want){
      for(var j=0;j<tier.options.length;j++){
        if(tier.options[j].value===want||tier.options[j].text===want){
          tier.selectedIndex=j; break;
        }
      }
    }
    var note=form.querySelector(".reach-note");
    if(note){
      note.textContent = any
        ? ("Total " + total.toLocaleString("en-US") +
           " across " + (biggest?("platforms; largest is " +
           biggest.toLocaleString("en-US") + ", so the tier is " + (want||"—")):"") + ".")
        : "";
    }
  }
  document.addEventListener("input", function(e){
    if(!e.target.name) return;
    if(e.target.name!=="p_followers" && e.target.name!=="p_url") return;
    var form=e.target.closest("form"); if(form) recalc(form);
  });
  // a row added by "+ Add another profile" is covered: the listener is on the
  // document, not on the inputs that existed when the page loaded.
})();
</script>""")


def creator_form(c, cities=None, tiers=None, interests=None, q="", page_no=1):
    """Add/edit form. `c` is None when adding a new creator.

    `cities` is every city already on the roster. Checkboxes rather than a
    <select multiple>: the options stay visible, there is no ctrl-click to
    explain, and it works on a phone where a multi-select becomes a modal list
    nobody can tell is multi-select.
    """
    def val(key, default=""):
        if c is not None and c[key] is not None:
            return e(c[key])
        return default

    tier_opts = "".join(
        "<option" + (" selected" if c is not None and c["tier"] == t else "") + ">"
        + e(t) + "</option>"
        for t in (tiers or ["Nano", "Micro", "Mid-Tier", "Macro"])
    )
    checked = "checked" if (c is None or c["active"]) else ""
    readonly = "readonly" if c is not None else ""
    action_label = "Save changes" if c is not None else "Add creator"

    # A thumbnail of what is currently set, so you can see before replacing.
    thumb = ""
    if c is not None and c["photo"]:
        thumb = ("<img class='thumb' src='" + u("/photo/") + "" + e(c["photo"].split("?")[0])
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

    # Delete used to be a <form> nested inside the save <form>. HTML forbids
    # that, so the browser dropped the inner tag and the Delete button became
    # an ordinary submit belonging to the SAVE form — clicking it saved the
    # creator instead. Verified: the row parsed to one form, action
    # /roster/save, with Delete attached to it.
    #
    # The delete form is a sibling now and the button reaches it through the
    # HTML5 `form` attribute, which is exactly what that attribute is for.
    delete_button = delete_after = ""
    if c is not None:
        ident = "del-" + re.sub(r"[^A-Za-z0-9]", "", c["code"])
        confirm = "return confirm('Delete " + e(c["code"]) + " permanently?')"
        delete_button = ("<button form='" + ident + "' class='btn small danger' "
                         "style='margin-left:8px'>Delete</button>")
        delete_after = (
            "<form id='" + ident + "' method='post' action='" + u("/roster/delete")
            + "' onsubmit=\"" + confirm + "\"><input type='hidden' name='code' value='"
            + e(c["code"]) + "'></form>")

    # Two things the form has to carry back with it. `q` is the search that was
    # running when the editor was opened, so the save can return to that same
    # view instead of the top of the unfiltered roster. `prev_updated` is what
    # this form was built from, so a save that would overwrite someone else's
    # newer edit can be refused instead of silently winning.
    try:
        stamp = str(c["updated_at"] or "") if c is not None else ""
    except (IndexError, KeyError):
        stamp = ""
    carried = "<input type='hidden' name='q' value='" + e(q or "") + "'>"
    carried += "<input type='hidden' name='page' value='" + e(str(page_no or 1)) + "'>"
    if stamp:
        carried += "<input type='hidden' name='prev_updated' value='" + e(stamp) + "'>"

    return (
        "<form method='post' action='" + u("/roster/save") + "' enctype='multipart/form-data' "
        "style='margin-top:12px'>"
        + carried
        + "<div class='row'>"
        + code_field
        + "<div><label>Name</label><input name='name' value='" + val("name") + "' required></div>"
        + "</div>"
        + profile_field(c)
        + "<div class='row'>"
        + "<div><label>Followers (total)</label><input name='followers' value='"
        + val("followers") + "' title='Filled in from the platforms above'></div>"
        + "<div><label>Tier</label><select name='tier'>" + tier_opts + "</select></div>"
        + city_field(c, cities)
        + "<div><label>Nationality</label><input name='nationality' value='"
        + val("nationality") + "' list='nationalities' placeholder='Saudi'></div>"
        + interest_field(c, interests)
        + "</div><div class='row'>"
        + "<div><label>Photo</label>" + photo_field + "</div>"
        + "<div><label>Sort</label><input name='sort' value='" + val("sort", "0") + "'></div>"
        + "<div><label>Note (internal)</label><input name='note' value='" + val("note") + "'></div>"
        + "<div><label>Visible</label><div style='padding-top:9px'>"
        + "<input type='checkbox' name='active' value='1' " + checked
        + " style='width:auto'> Show to clients</div></div></div>"
        + "<button class='btn'>" + action_label + "</button>" + delete_button
        + "</form>" + delete_after
    )


def roster_page(creators, error=None, message=None, cities=None, tiers=None,
                nationalities=None, interests=None, editing=None, q="",
                bands=None, page_no=1, pages=1, total=None, per_page=100):
    tiers = tiers or []
    tier_names = [t["name"] for t in tiers]
    used = {}
    for c in creators:
        used[c["tier"]] = used.get(c["tier"], 0) + 1
    err = ""
    if error:
        err += "<div class='err'>" + e(error) + "</div>"
    if message:
        err += "<div class='ok'>" + e(message) + "</div>"

    def row(c):
        hidden = "" if c["active"] else " <span class='pill dead'>hidden</span>"
        handle = "@" + c["handle"] if c["handle"] else "—"
        if c["photo"]:
            # Not u("/photo/"): that is this service, and 757 of them on one
            # page is what made saving slow. nginx resizes and serves these,
            # and checks the signature itself, so none of it reaches Python.
            shot = ("<img class='thumb sm' src='" + e(links.thumb(c["photo"]))
                    + "' alt='' width='44' height='44' loading='lazy' decoding='async'>")
        else:
            shot = "<span class='thumb sm none'>—</span>"
        open_now = (editing == c["code"])
        link = u("/roster") + "?" + urlencode(q=q, edit="" if open_now else c["code"])
        button = ("<a class='btn small" + ("" if open_now else " ghost") + "' href='"
                  + link + "#" + e(c["code"]) + "'>"
                  + ("Close" if open_now else "Edit") + "</a>")

        out = (
            "<tr id='" + e(c["code"]) + "'><td>" + shot + "</td><td><code>"
            + e(c["code"]) + "</code></td>"
            + "<td><strong>" + e(c["name"])
            + "</strong>" + hidden + "</td><td>" + e(c["platform"])
            + "<br><span class='muted'>" + e(handle) + "</span></td><td>"
            + num(c["followers"]) + "</td><td>" + e(c["tier"]) + "</td><td>"
            + e(", ".join(split_cities(c["city"])) or "—") + "</td>"
            + "<td class='right'>" + button + "</td></tr>")

        # The form gets a row of its own, spanning every column. It used to sit
        # inside the last <td> of an eight-column table, so it was squeezed into
        # whatever width that cell had — which is why the profile link box
        # collapsed to a sliver and the panel spilled past its edge.
        #
        # And it is rendered ONLY for the creator being edited. Building all of
        # them cost 1MB and 6,390 form controls at 162 creators; at 700 it was
        # 4.2MB and 27,600, which is the lag.
        if open_now:
            out += ("<tr class='editrow'><td colspan='8'>"
                    + creator_form(c, cities, tier_names, interests, q, page_no)
                    + "</td></tr>")
        return out

    rows = "".join(row(c) for c in creators) or (
        "<tr><td colspan='8' class='muted'>Roster is empty — import it with seed.py.</td></tr>")

    # How much of the roster this page is showing. It counts the whole result,
    # not the slice on screen — len(creators) is at most one page now, and
    # reporting that as the number of matches would be a lie.
    count = len(creators) if total is None else total
    first = (page_no - 1) * per_page + 1
    last = min(count, first + len(creators) - 1)
    if count == 0:
        shown = "No matches" if q else "Roster is empty"
    elif pages <= 1:
        shown = (str(count) + " match" + ("" if count == 1 else "es")) if q else (
            str(count) + " creator" + ("" if count == 1 else "s"))
    else:
        shown = ("Showing " + str(first) + "\u2013" + str(last) + " of " + str(count)
                 + (" matches" if q else " creators"))

    def page_link(n, label=None, disabled=False, current=False):
        if disabled:
            return "<span class='pgoff'>" + e(label or str(n)) + "</span>"
        if current:
            return "<span class='pgnow'>" + e(label or str(n)) + "</span>"
        href = u("/roster") + "?" + urlencode(q=q, page=(n if n > 1 else ""))
        return "<a href='" + href + "'>" + e(label or str(n)) + "</a>"

    if pages <= 1:
        pager = ""
    else:
        # First and last are always reachable, plus a window around where you
        # are; a roster of 5,000 would otherwise print fifty numbered links.
        window = sorted({1, pages} | {n for n in range(page_no - 2, page_no + 3)
                                      if 1 <= n <= pages})
        numbers, previous = [], 0
        for n in window:
            if previous and n > previous + 1:
                numbers.append("<span class='pgoff'>\u2026</span>")
            numbers.append(page_link(n, current=(n == page_no)))
            previous = n
        pager = ("<nav class='pager' aria-label='Roster pages'>"
                 + page_link(page_no - 1, "\u2190 Previous", disabled=(page_no <= 1))
                 + "<span class='pgnums'>" + "".join(numbers) + "</span>"
                 + page_link(page_no + 1, "Next \u2192", disabled=(page_no >= pages))
                 + "</nav>")

    # A datalist, not a select: nationality is free text, and offering what is
    # already in use stops "Saudi", "saudi" and "KSA" becoming three values.
    suggestions = ("<datalist id='nationalities'>" + "".join(
        "<option value='" + e(x) + "'>" for x in (nationalities or [])) + "</datalist>")

    body = (
        suggestions
        + reach_script(bands or [])
        + "<h1>Roster</h1><p class='sub'>" + str(len(creators))
        + " creators. Hidden ones stay in the database but never reach a client.</p>" + err
        + "<h2>Add a creator</h2><div class='card'>"
        + creator_form(None, cities, tier_names, interests, q) + "</div>"
        + "<h2>Import a spreadsheet</h2><div class='card'>"
        + "<p class='sub' style='margin-bottom:16px'>Add many creators at once. "
          "Start from the template so the headings match — a code left blank is "
          "assigned automatically, and a code that already exists is updated "
          "rather than duplicated. Photos are never lost on re-import.</p>"
        + "<p class='sub' style='margin-bottom:16px'><strong>Nothing is written "
          "unless every row is valid.</strong> If a tier or platform is wrong the "
          "whole file is rejected and the offending rows are named, so the roster "
          "is never left half updated.</p>"
        + "<p class='sub' style='margin-bottom:16px'><strong>Photos can travel "
          "with the sheet, but only in an .xlsx.</strong> A cell holds text, so "
          "a picture is not <em>in</em> one — Excel floats it over the sheet, and "
          "the row its top-left corner sits on is the creator it belongs to. "
          "Insert each picture on its row in the <code>photo</code> column. A CSV "
          "cannot carry an image at all.</p>"
        + "<p class='sub' style='margin-bottom:16px'>Worth it when you are "
          "building a roster from scratch and have the photos to hand. If the "
          "creators are already here and you just want to add or replace "
          "pictures, <em>Attach photos in bulk</em> below is far quicker than "
          "inserting them into Excel one at a time.</p>"
        + "<a class='btn ghost' href='" + u("/roster/template.xlsx")
        + "'>Download the template (.xlsx, takes photos)</a> "
        + "<a class='btn ghost' href='" + u("/roster/template") + "'>CSV only</a>"
        + "<form method='post' action='" + u("/roster/import") + "' enctype='multipart/form-data' "
          "style='margin-top:18px'>"
        + "<div class='row'><div><label>Spreadsheet (.csv or .xlsx)</label>"
        + "<input type='file' name='sheet' accept='.csv,.xlsx,.xlsm,text/csv' required></div>"
        + "<div style='align-self:end'><button class='btn'>Import</button></div></div>"
        + "<p class='muted' style='font-size:13px;margin:0'>Both formats are "
          "read by the server itself — nothing to install, and .xlsx works "
          "wherever this is deployed.</p></form></div>"
        + tiers_section(tiers, used)
        + "<h2>Attach photos in bulk</h2><div class='card'>"
        + "<p class='sub' style='margin-bottom:16px'>For creators who are "
          "already on the roster. Select a whole folder of images at once "
          "instead of opening each creator in turn — and unlike the "
          "spreadsheet route, nothing has to be inserted into Excel first. "
          "This is also how you replace a photo later without re-importing "
          "anything.</p>"
        + "<p class='sub' style='margin-bottom:10px'>Each file is matched to a "
          "creator by its <strong>filename</strong>, any of three ways — so in "
          "most cases you do not have to rename anything:</p>"
        + "<ul class='sub' style='margin:0 0 16px 18px'>"
          "<li>the person's name — <code>Noha Magdy.jpg</code>, "
          "<code>noha_magdy.jpg</code>, <code>NOHA-MAGDY.jpg</code></li>"
          "<li>their handle — <code>noha.mgdi.jpg</code></li>"
          "<li>the code — <code>HV-MC-001.jpg</code></li></ul>"
        + "<p class='sub' style='margin-bottom:16px'>Spaces, dashes and "
          "underscores are all treated the same, and a <code>(1)</code> the "
          "browser added to a second download is ignored. Anything matching "
          "nothing is listed back by name rather than dropped, and a name that "
          "fits two creators is skipped rather than guessed. The same 6MB and "
          "real-image checks apply as on a single upload.</p>"
        + "<form method='post' action='" + u("/roster/photos") + "' "
          "enctype='multipart/form-data'>"
        + "<div class='row'><div><label>Images (select many)</label>"
        + "<input type='file' name='photos' accept='image/*' multiple required></div>"
        + "<div style='align-self:end'><button class='btn'>Attach photos</button>"
          "</div></div>"
        + "<p class='muted' style='font-size:13px;margin:0'>A photo already on "
          "file is replaced by the one you upload for that creator.</p>"
        + "</form></div>"
        + "<h2>Everyone</h2>"
        + "<form class='rsearch' method='get' action='" + u("/roster") + "'>"
          "<input name='q' value='" + e(q) + "' placeholder='Search name, code, "
          "handle or city' autocomplete='off'>"
          "<button class='btn small'>Search</button>"
        + ("<a class='btn small ghost' href='" + u("/roster") + "'>Clear</a>" if q else "")
        + "<span class='muted' style='font-size:13px'>" + e(shown) + "</span></form>"
        + "<p class='sub' style='margin-bottom:12px'>Need the codes? "
          "<a href='" + u("/roster/export") + "'>Export the roster (.csv)</a> — "
          "every creator with their code, handle and whether a photo is on "
          "file. It is also a valid import file, so you can edit a column and "
          "upload it back.</p>"
        + "<div class='card'><table><thead><tr><th></th><th>Code</th>"
        + "<th>Name</th><th>Platform</th><th>Followers</th><th>Tier</th><th>City</th>"
        + "<th></th></tr></thead><tbody>" + rows + "</tbody></table></div>"
        + pager
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
            shot = ("<img class='thumb' src='" + u("/photo/") + "" + e(c["photo"].split("?")[0])
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
            "<form method='post' action='" + u("/requests/handled") + "' class='inline'>"
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
