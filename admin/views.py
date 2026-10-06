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
from db import (code_state, now, split_cities, split_profiles, price_of,
                account_tiers as db_account_tiers, PLATFORMS)


def e(v):
    return html.escape("" if v is None else str(v), quote=True)


def ts(value):
    if not value:
        return "—"
    # A date past what the calendar library can draw — an access code issued
    # to expire in ten million days — took the whole Access codes page down.
    try:
        return datetime.fromtimestamp(value, timezone.utc).strftime("%d %b %Y, %H:%M")
    except (ValueError, OverflowError, OSError):
        return "never (far future)"


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
input,select,textarea{width:100%;font:inherit;padding:10px 12px;border:1px solid var(--line);
border-radius:8px;background:var(--white);color:var(--ink)}
textarea{min-height:64px;resize:vertical}
input:focus,select:focus,textarea:focus{outline:2px solid var(--ink);outline-offset:-1px}
.rules{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.tabs{display:flex;gap:6px;margin:4px 0 20px;border-bottom:1px solid var(--line)}
.tabs a{padding:9px 14px;text-decoration:none;color:var(--gray);border-bottom:2px solid transparent;margin-bottom:-1px}
.tabs a.on{color:var(--ink);border-bottom-color:var(--ink);font-weight:600}
.kpis{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));margin-bottom:18px}
.kpis div{background:var(--white);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.kpis b{display:block;font-size:26px;line-height:1.1}
.kpis span{font-size:12px;color:var(--gray);text-transform:uppercase;letter-spacing:.06em}
.split{display:grid;gap:18px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
.linkrow input[readonly]{background:#f6f5f2}
.linkrow form{display:grid;gap:8px;grid-template-columns:1fr 1fr auto;align-items:end}
.post-thumb{width:56px;height:56px;border-radius:8px;object-fit:cover;background:#eee;display:block}
.est{font-size:11px;color:var(--gray);text-transform:uppercase;letter-spacing:.04em}
.real{font-size:11px;color:var(--green);text-transform:uppercase;letter-spacing:.04em}
.inline{display:inline}
.mini input{padding:5px 7px;font-size:13px;width:80px}
.shot{max-width:100%;max-height:420px;border:1px solid var(--line);border-radius:8px}
.grid2{display:grid;gap:18px;grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
.guide{border-color:var(--ink)}
.guide-head{margin-bottom:10px}
.guide-steps{display:flex;flex-wrap:wrap;gap:8px;list-style:none;padding:0;margin:0;counter-reset:g}
.guide-steps li{counter-increment:g;font-size:13px;padding:6px 12px;border-radius:999px;background:#f3f1ec;color:var(--gray)}
.guide-steps li::before{content:counter(g) "  ";font-weight:700}
.guide-steps li.ok{background:#e7f6ec;color:var(--green)}
.guide-steps li.ok::before{content:"\\2713  "}
.step h2{display:flex;align-items:center;gap:10px}
.step-n{display:inline-grid;place-items:center;width:28px;height:28px;border-radius:50%;background:var(--ink);color:#fff;font-size:14px}
.logo-grid{display:grid;gap:8px;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));max-height:280px;overflow:auto;padding:4px}
.logo-pick{display:flex;flex-direction:column;align-items:center;gap:6px;padding:10px;border:1px solid var(--line);border-radius:10px;cursor:pointer;text-transform:none;letter-spacing:0;font-size:11px;color:var(--gray);margin:0}
.logo-pick img{width:56px;height:56px;object-fit:contain}
.logo-pick:has(input:checked){border-color:var(--ink);box-shadow:0 0 0 2px var(--ink) inset;color:var(--ink)}
.logo-pick input{margin:0;width:auto}
.savebar{position:sticky;bottom:0;background:rgba(247,245,240,.95);padding:14px 0;display:flex;gap:10px;border-top:1px solid var(--line);margin-top:20px}
.steps-table input,.steps-table select{padding:7px 9px;font-size:14px}
.steps-table td{padding:6px 8px}
.rec-lead td{font-weight:600}
.chain{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:13px}
.chain .arrow{color:var(--gray)}
@media (max-width:820px){.grid2{grid-template-columns:1fr}}
.row{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));margin-bottom:14px}
.btn{display:inline-block;font:inherit;font-weight:600;padding:10px 20px;border-radius:999px;
border:1px solid var(--ink);background:var(--ink);color:#fff;cursor:pointer;text-decoration:none}
.btn:hover{opacity:.88}
.btn.ghost{background:transparent;color:var(--ink)}
.btn.small{padding:6px 14px;font-size:13px}
.badge{display:inline-block;min-width:18px;height:18px;padding:0 5px;margin-left:6px;border-radius:9px;
.badge[hidden]{display:none}
  background:var(--red);color:#fff;font-size:11px;font-weight:700;line-height:18px;text-align:center;
  vertical-align:1px}
.toast{position:fixed;right:18px;bottom:18px;z-index:50;max-width:360px;padding:14px 18px;border-radius:12px;
  background:var(--ink);color:#fff;box-shadow:0 10px 30px rgba(0,0,0,.25);font-size:14px}
.toast a{color:var(--lime);font-weight:600;text-decoration:none}
tr[id]{scroll-margin-top:90px}
tr.flash td{animation:flash 2.4s ease-out}
@keyframes flash{0%,35%{background:#fff7c2}100%{background:transparent}}
.price-hint{font-size:12px;color:var(--gray);margin-top:4px}
.pill.own{background:#eef6ff;color:#1d4ed8}
.stars{font-size:13px;color:#e0a500;letter-spacing:1px}
.stars .dim{color:#d8d2cc}
.acct{font-size:12px;color:var(--gray)}
.sel-table input{max-width:130px}
.rsearch .added{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--gray);
  margin:0;white-space:nowrap}
.rsearch .added input{width:auto;padding:8px 10px}
tr.manage-row td{padding-top:0;border-top:0}
details.manage summary{list-style:none;display:inline-block;cursor:pointer}
details.manage summary::-webkit-details-marker{display:none}
details.manage[open] summary{margin-bottom:12px}
.manage-body{background:#f7f5f2;border-radius:12px;padding:16px 18px}
.limits input{max-width:170px}
table.devices{margin-top:10px;font-size:14px}
.sel-table input[readonly]{background:#f3f1ee;color:var(--gray)}
.sel-table .profit{font-size:12px;color:#14884a;white-space:nowrap}
.margin-box{display:flex;align-items:center;gap:8px}
.margin-box input{max-width:110px}
.money-sum{display:flex;flex-wrap:wrap;gap:28px;margin:4px 0 0}
.money-sum div{min-width:120px}
.money-sum dt{font-size:12px;color:var(--gray);text-transform:uppercase;letter-spacing:.06em}
.money-sum dd{margin:2px 0 0;font-size:20px;font-weight:700}
.money-sum .gain{color:#14884a}
.sel-link{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.sel-link input{flex:1;min-width:260px;font-family:ui-monospace,Menlo,monospace;font-size:12px}
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
             ("/clients", "Clients"), ("/roster", "Roster"), ("/analysis", "Creator analysis"),
             ("/selections", "Selections"), ("/campaigns", "Campaigns"),
             ("/requests", "Requests"), ("/settings", "Settings")]
    # Requests nobody has handled yet, counted on every page so a new one is
    # seen from wherever the admin happens to be. The page script keeps it
    # live afterwards.
    try:
        from db import request_pulse
        pulse = request_pulse()
    except Exception:
        pulse = {"open": 0, "latest": 0}

    def badge(href):
        if href == "/analysis":
            n = pulse.get("a_open", 0)
            return ("<span class='badge' id='an-badge'" + ("" if n else " hidden") + ">"
                    + str(n) + "</span>")
        if href != "/requests":
            return ""
        n = pulse["open"]
        return ("<span class='badge' id='req-badge'" + ("" if n else " hidden") + ">"
                + str(n) + "</span>")
    nav = "".join(
        '<a href="' + u(href) + '"' + (' class="on"' if active == href else "") + ">" + label
        + badge(href) + "</a>"
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
        + '</div></header><main class="wrap">' + body + "</main>"
        + "<div class='toast' id='req-toast' role='status' hidden></div>"
        + "<script>window.HV_PULSE=" + json.dumps({"latest": pulse["latest"],
                                                    "company": pulse.get("company", ""),
                                                    "count": pulse.get("count", 0),
                                                    "api": u("/api/pulse"),
                                                    "requests": u("/requests"),
                                                    "a_latest": pulse.get("a_latest", 0),
                                                    "a_creator": pulse.get("a_creator", ""),
                                                    "a_client": pulse.get("a_client", ""),
                                                    "analysis": u("/analysis")})
        + ";" + PULSE_JS + "</script></body></html>"
    )


# Watches for new quote requests while any dashboard page is open: a count on
# the header, a note in the corner, a short chime, and a desktop notification
# when the browser allows one. The newest id already announced is remembered
# per browser, so a request is announced once rather than on every page.
PULSE_JS = """
(function(){
  var P=window.HV_PULSE, KEY='hv_seen_request', AKEY='hv_seen_analysis';
  var seen=+(localStorage.getItem(KEY)||0);
  if(!seen){ seen=P.latest; try{localStorage.setItem(KEY,seen);}catch(e){} }
  var aseen=+(localStorage.getItem(AKEY)||0);
  if(!aseen){ aseen=P.a_latest||0; try{localStorage.setItem(AKEY,aseen);}catch(e){} }
  function announce(msg, href){
    var t=document.getElementById('req-toast');
    if(t){ t.innerHTML=''; var a=document.createElement('a'); a.href=href;
           a.textContent=msg+' — open'; t.appendChild(a); t.hidden=false;
           clearTimeout(t._h); t._h=setTimeout(function(){t.hidden=true;},15000); }
    chime();
    if(window.Notification && Notification.permission==='granted'){
      try{ var n=new Notification('HelloVoice catalogue',{body:msg});
           n.onclick=function(){window.focus();location.href=href;}; }catch(e){}
    }
  }
  var base=document.title.replace(/^\\(\\d+\\)\\s*/,'');
  function chime(){
    try{
      var A=window.AudioContext||window.webkitAudioContext; if(!A) return;
      var c=new A(), t=c.currentTime;
      [880,1320].forEach(function(f,i){
        var o=c.createOscillator(), g=c.createGain();
        o.frequency.value=f; o.connect(g); g.connect(c.destination);
        g.gain.setValueAtTime(0.0001,t+i*0.18);
        g.gain.exponentialRampToValueAtTime(0.25,t+i*0.18+0.02);
        g.gain.exponentialRampToValueAtTime(0.0001,t+i*0.18+0.3);
        o.start(t+i*0.18); o.stop(t+i*0.18+0.32);
      });
    }catch(e){}
  }
  function show(d){
    var b=document.getElementById('req-badge');
    if(b){ b.textContent=d.open; b.hidden=!d.open; }
    var ab=document.getElementById('an-badge');
    if(ab && d.a_open!=null){ ab.textContent=d.a_open; ab.hidden=!d.a_open; }
    var total=(d.open||0)+(d.a_open||0);
    document.title=(total?'('+total+') ':'')+base;
    if(d.a_latest>aseen){
      aseen=d.a_latest; try{localStorage.setItem(AKEY,aseen);}catch(e){}
      announce('New analysis request'+(d.a_creator?' for '+d.a_creator:'')+(d.a_client?' from '+d.a_client:''), P.analysis);
    }
    if(d.latest>seen){
      seen=d.latest; try{localStorage.setItem(KEY,seen);}catch(e){}
      var msg='New quote request'+(d.company?' from '+d.company:'')+
              (d.count?' — '+d.count+' creator'+(d.count==1?'':'s'):'');
      var t=document.getElementById('req-toast');
      if(t){ t.innerHTML=''; var a=document.createElement('a'); a.href=P.requests;
             a.textContent=msg+' — open'; t.appendChild(a); t.hidden=false;
             clearTimeout(t._h); t._h=setTimeout(function(){t.hidden=true;},15000); }
      chime();
      if(window.Notification && Notification.permission==='granted'){
        try{ var n=new Notification('HelloVoice catalogue',{body:msg});
             n.onclick=function(){window.focus();location.href=P.requests;}; }catch(e){}
      }
    }
  }
  function poll(){
    fetch(P.api,{credentials:'same-origin'}).then(function(r){return r.ok?r.json():null;})
      .then(function(d){ if(d) show(d); }).catch(function(){});
  }
  // Browsers only allow the permission prompt and sound after a click.
  document.addEventListener('click',function once(){
    document.removeEventListener('click',once);
    if(window.Notification && Notification.permission==='default'){
      try{Notification.requestPermission();}catch(e){}
    }
  });
  show({open:+(document.getElementById('req-badge')||{}).textContent||0, latest:P.latest,
        company:P.company, count:P.count,
        a_open:+(document.getElementById('an-badge')||{}).textContent||0, a_latest:P.a_latest||0,
        a_creator:P.a_creator, a_client:P.a_client});
  setInterval(poll,20000);
  document.addEventListener('visibilitychange',function(){ if(!document.hidden) poll(); });
})();
"""


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


def device_name(ua):
    """'iPhone · Safari' from a user-agent string — enough to tell a
    client's phone from their laptop in the list."""
    ua = ua or ""
    kind = next((n for k, n in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
                                ("Macintosh", "Mac"), ("Windows", "Windows"), ("Linux", "Linux"))
                 if k in ua), "Unknown device")
    app = next((n for k, n in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"),
                               ("CriOS", "Chrome"), ("Chrome/", "Chrome"), ("Safari/", "Safari"))
                if k in ua), "")
    return kind + (" · " + app if app else "")


def _day(value):
    return time.strftime("%Y-%m-%d", time.gmtime(value)) if value else ""


def code_manage(c, devices):
    """The panel under a code: its limits, and every device it opened on."""
    cid = str(c["id"])
    maxd = c["max_devices"] if "max_devices" in c.keys() else None
    form = (
        "<form method='post' action='" + u("/codes/limits") + "' class='row limits'>"
        "<input type='hidden' name='id' value='" + cid + "'>"
        "<div><label>Max devices</label><input name='max_devices' type='number' min='1' "
        "value='" + (str(maxd) if maxd else "") + "' placeholder='no limit'></div>"
        "<div><label>Max uses</label><input name='max_uses' type='number' min='1' "
        "value='" + (str(c["max_uses"]) if c["max_uses"] else "") + "' placeholder='unlimited'></div>"
        "<div><label>Expires on</label><input name='expires' type='date' "
        "value='" + _day(c["expires_at"]) + "'></div>"
        "<div style='align-self:end'><button class='btn small'>Save limits</button></div></form>"
        "<p class='price-hint'>Max devices: how many phones or computers can open the catalogue "
        "with this code. A device already on the list always gets back in; a new one is refused "
        "once the list is full, and needs a new code or a slot freed below. Empty = no limit.</p>")
    if devices:
        rows = "".join(
            "<tr><td>" + e(device_name(d["user_agent"])) + "</td>"
            "<td class='muted'>" + e(d["ip"] or "—") + "</td>"
            "<td class='muted'>" + ago(d["first_at"]) + "</td>"
            "<td class='muted'>" + ago(d["last_at"]) + "</td>"
            "<td class='right'><form method='post' action='" + u("/codes/device/remove") + "' "
            "class='inline' onsubmit=\"return confirm('Remove this device? It loses access at "
            "once and its slot is freed.')\"><input type='hidden' name='id' value='" + str(d["id"])
            + "'><input type='hidden' name='code' value='" + cid + "'>"
            "<button class='btn small ghost'>Remove</button></form></td></tr>"
            for d in devices)
        listing = ("<table class='devices'><thead><tr><th>Device</th><th>IP address</th>"
                   "<th>First opened</th><th>Last seen</th><th></th></tr></thead><tbody>"
                   + rows + "</tbody></table>")
    else:
        listing = "<p class='muted'>Not opened on any device since device limits began.</p>"
    return form + listing


def codes_page(codes, new_code=None, error=None, devices=(), message=None):
    by_code = {}
    for d in devices or ():
        by_code.setdefault(d["code_id"], []).append(d)
    banner = ""
    if new_code:
        banner += (
            "<div class='note'><strong>New code.</strong> "
            "It is kept on this page, so you can come back for it."
            "<div style='margin-top:10px'>" + copyable(new_code, "reveal") + "</div></div>"
        )
    if error:
        banner += "<div class='err'>" + e(error) + "</div>"
    if message:
        banner += "<div class='ok'>" + e(message) + "</div>"

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
        maxd = c["max_devices"] if "max_devices" in c.keys() else None
        n = c["devices"] if "devices" in c.keys() else 0
        full = maxd is not None and n >= maxd
        devs = (str(n) + " / " + (str(maxd) if maxd else "no limit")
                + (" <span class='pill warn'>full</span>" if full and ok else ""))
        manage = ("<details id='code-" + str(c["id"]) + "' class='manage'><summary class='btn small ghost'>"
                  "Manage</summary><div class='manage-body'>"
                  + code_manage(c, by_code.get(c["id"], [])) + "</div></details>")
        rows.append(
            "<tr><td><strong>" + e(c["label"]) + "</strong><br>" + shown
            + "</td><td><span class='pill " + cls + "'>" + e(reason) + "</span></td>"
            + "<td>" + devs + "</td>"
            + "<td>" + used + "</td><td class='muted'>" + ts(c["expires_at"]) + "</td>"
            + "<td class='muted'>" + ago(c["last_used"]) + "</td>"
            + "<td class='right'>" + revoke + "</td></tr>"
            + "<tr class='manage-row'><td colspan='7'>" + manage + "</td></tr>"
        )
    body_rows = "".join(rows) or "<tr><td colspan='7' class='muted'>No codes yet.</td></tr>"

    body = (
        "<h1>Access codes</h1><p class='sub'>One code per client. Checked on the server, "
        "so expiry and revocation take effect immediately — not whenever a browser feels "
        "like it.</p>" + banner
        + "<form method='post' action='" + u("/codes/new") + "' class='card'><div class='row'>"
        + "<div><label>Issued to</label><input name='label' placeholder='Alpha Plus' required></div>"
        + "<div><label>Passcode (optional)</label><input name='custom' maxlength='40' "
          "placeholder='e.g. Alpha Plus122' autocomplete='off'>"
          "<div class='price-hint'>Leave empty to generate one. Case, spaces and dashes are ignored "
          "when a client types it.</div></div>"
        + "<div><label>Expires in (days)</label>"
          "<input name='days' type='number' min='1' max='3650' placeholder='empty = never'></div>"
        + "<div><label>Max uses</label>"
          "<input name='max_uses' type='number' min='1' placeholder='unlimited'></div>"
        + "<div><label>Max devices</label>"
          "<input name='max_devices' type='number' min='1' value='5' placeholder='no limit'>"
          "<div class='price-hint'>Phones or computers this code opens on. Passed to anyone "
          "else, it will not open. Empty = no limit.</div></div>"
        + "</div><button class='btn'>Create code</button></form>"
        + "<div class='card'><table><thead><tr><th>Code</th><th>State</th><th>Devices</th><th>Uses</th>"
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
            "mail_sent": "live", "mail_failed": "dead",
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
        "<div><label for='a" + ident + "'>By followers</label>"
        "<div style='padding-top:9px'><input id='a" + ident + "' type='checkbox' name='auto' value='1'"
        + (" checked" if t["auto"] else "")
        + " style='width:auto' title='On: creators are placed in this tier from their followers. "
          "Off: a category (like HCPs) you assign by hand, and nobody is moved out of it.'></div></div>"
        "<div class='tier-act'><button class='btn small'>Save</button>" + delete
        + "<span class='muted' style='font-size:12px;margin-left:8px'>" + people
        + "</span></div></form>")


def tiers_section(tiers, used):
    rows = "".join(tier_row(t, used.get(t["name"], 0)) for t in tiers) or (
        "<p class='muted'>No tiers yet — add the first one below.</p>")
    return (
        "<h2>Tiers &amp; pricing</h2><div class='card'>"
        "<p class='sub' style='margin-bottom:16px'>A creator is priced by their "
        "tier unless they have their own <em>price per video</em>, so changing a "
        "band here re-prices everyone on it who has no price of their own — in the "
        "selection total and in the quote.</p>"
        "<p class='sub' style='margin-bottom:16px'><strong>By followers</strong>: "
        "ticked, creators are placed in the tier from their largest platform. "
        "Unticked, the tier is a category — like <em>HCPs</em> — that you assign by "
        "hand; nobody is placed in it or moved out of it automatically. Every tier "
        "with creators in it appears as a filter on the catalogue.</p>"
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
        "<div><label>By followers</label><div style='padding-top:9px'>"
        "<input type='checkbox' name='auto' value='1' checked style='width:auto'></div></div>"
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


def reach_script(bands, manual=None):
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
        + ";window.HV_MANUAL=" + json.dumps(list(manual or []))
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
    // A creator filed under a category tier (HCPs) stays there.
    var keep=tier && (window.HV_MANUAL||[]).indexOf(tier.value)!==-1;
    if(tier && want && !keep){
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


def stars(n):
    """Five stars with n filled — how the rating reads at a glance."""
    n = int(n or 0)
    return ("<span class='stars' title='" + str(n) + " of 5'>"
            + "★" * n + "<span class='dim'>" + "☆" * (5 - n) + "</span></span>")


def rating_field(c):
    """Our own rating of a creator, 1 to 5. Internal: the catalogue never
    shows it, so it can say what an account manager would say out loud."""
    try:
        val = c["rating"] if c is not None else None
    except (IndexError, KeyError):
        val = None
    opts = "<option value=''>— not rated —</option>" + "".join(
        "<option value='" + str(i) + "'" + (" selected" if val == i else "") + ">"
        + "★" * i + "☆" * (5 - i) + "</option>" for i in range(1, 6))
    return ("<div><label>Rating (internal)</label><select name='rating'>" + opts
            + "</select><div class='price-hint'>Ours, not the client's — never "
              "shown on the catalogue.</div></div>")


def price_field(c, bands=None):
    """This creator's own rate per video. Left empty, the tier's band is what
    a selection uses — which is what every creator had before this existed."""
    def v(key):
        try:
            x = c[key] if c is not None else None
        except (IndexError, KeyError):
            x = None
        return "" if x is None else format(x, ",")
    band = ""
    if c is not None and bands and bands.get(c["tier"]):
        lo, hi = bands[c["tier"]]
        band = "Empty = tier price (" + format(lo, ",") + " – " + format(hi, ",") + " SAR)"
    else:
        band = "Empty = the tier's price range"
    return (
        "<div><label>Price per video (SAR)</label>"
        "<div style='display:flex;gap:6px'>"
        "<input name='price_from' value='" + v("price_from") + "' placeholder='from' inputmode='numeric'>"
        "<input name='price_to' value='" + v("price_to") + "' placeholder='to (optional)' inputmode='numeric'>"
        "</div><div class='price-hint'>" + e(band) + ". One figure = a fixed price.</div></div>"
    )


def creator_form(c, cities=None, tiers=None, interests=None, q="", page_no=1, bands=None,
                 dates=("", "")):
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
            + e(c["code"]) + "'><input type='hidden' name='q' value='" + e(q or "")
            + "'><input type='hidden' name='page' value='" + e(str(page_no or 1)) + "'>"
            + date_carry(dates) + "</form>")

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
    carried += date_carry(dates)
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
        + price_field(c, bands)
        + rating_field(c)
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


def date_carry(dates):
    """The date-added filter, as hidden fields, so a save or delete returns
    to the same filtered view."""
    out = ""
    for name, value in zip(("from", "to"), dates or ("", "")):
        if value:
            out += "<input type='hidden' name='" + name + "' value='" + e(value) + "'>"
    return out


def roster_page(creators, error=None, message=None, cities=None, tiers=None,
                nationalities=None, interests=None, editing=None, q="",
                bands=None, page_no=1, pages=1, total=None, per_page=100,
                dates=("", "")):
    d_from, d_to = dates or ("", "")
    filtered = bool(q or d_from or d_to)
    tiers = tiers or []
    tier_names = [t["name"] for t in tiers]
    price_bands = {t["name"]: (t["price_from"], t["price_to"]) for t in tiers}
    used = {}
    for c in creators:
        used[c["tier"]] = used.get(c["tier"], 0) + 1
    err = ""
    if error:
        err += "<div class='err'>" + e(error) + "</div>"
    if message:
        err += "<div class='ok'>" + e(message) + "</div>"

    def own_price(c):
        lo, hi = c["price_from"], c["price_to"]
        if not (lo or hi):
            return ""
        txt = format(lo, ",") if lo == hi else format(lo, ",") + "–" + format(hi, ",")
        return "<br><span class='pill own' title='Own price per video'>" + txt + " SAR</span>"

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
        # Close keeps the page it was opened on; it used to drop to page 1.
        link = u("/roster") + "?" + urlencode(
            q=q, **{"from": d_from, "to": d_to}, edit="" if open_now else c["code"],
            page=(page_no if open_now and page_no > 1 else ""))
        button = ("<a class='btn small" + ("" if open_now else " ghost") + "' href='"
                  + link + "#" + e(c["code"]) + "'>"
                  + ("Close" if open_now else "Edit") + "</a>")

        out = (
            "<tr id='" + e(c["code"]) + "'><td>" + shot + "</td><td><code>"
            + e(c["code"]) + "</code></td>"
            + "<td><strong>" + e(c["name"]) + "</strong>" + hidden
            + (("<br>" + stars(c["rating"])) if ("rating" in c.keys() and c["rating"]) else "")
            + "</td><td>" + e(c["platform"])
            + "<br><span class='muted'>" + e(handle) + "</span></td><td>"
            + num(c["followers"]) + "</td><td>" + e(c["tier"]) + own_price(c) + "</td><td>"
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
                    + creator_form(c, cities, tier_names, interests, q, page_no, price_bands,
                                   dates)
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
        href = u("/roster") + "?" + urlencode(q=q, **{"from": d_from, "to": d_to},
                                               page=(n if n > 1 else ""))
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
        + reach_script(bands or [], [t["name"] for t in tiers if not t["auto"]])
        + "<h1>Roster</h1><p class='sub'>" + str(len(creators))
        + " creators. Hidden ones stay in the database but never reach a client.</p>" + err
        + "<h2>Add a creator</h2><div class='card'>"
        + creator_form(None, cities, tier_names, interests, q, 1, price_bands, dates) + "</div>"
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
          "<label class='added'>Added from<input type='date' name='from' value='" + e(d_from) + "'></label>"
          "<label class='added'>to<input type='date' name='to' value='" + e(d_to) + "'></label>"
          "<button class='btn small'>Search</button>"
        + ("<a class='btn small ghost' href='" + u("/roster") + "'>Clear</a>" if filtered else "")
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
        + ROSTER_JS
    )
    return page("Roster", body, "/roster")


# After a save the page opens at the creator that was edited, and marks it,
# rather than at the top of the page with the row somewhere below.
ROSTER_JS = """<script>
(function(){
  var id=decodeURIComponent((location.hash||'').slice(1)); if(!id) return;
  // "near-CODE": a neighbour of a row that was just deleted. Scroll back to
  // that spot without marking the neighbour as if it had been edited.
  var near=id.indexOf('near-')===0; if(near) id=id.slice(5);
  var row=document.getElementById(id); if(!row) return;
  var go=function(){
    row.scrollIntoView({block:'center'});
    if(!near) row.classList.add('flash');
    var msg=document.querySelector('main .ok, main .err');
    if(msg && near){                     // keep "deleted" in view, not at the top
      var t=msg.cloneNode(true); t.className+=' toast'; t.style.cssText='position:fixed;left:50%;top:84px;'
        +'transform:translateX(-50%);bottom:auto;right:auto;z-index:60';
      document.body.appendChild(t); setTimeout(function(){t.remove();},4000);
    }
  };
  if(document.readyState==='complete') go(); else window.addEventListener('load',go);
})();
</script>"""


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
        t = price_of(c, tiers)
        if t:
            price = (format(t[0], ",") if t[0] == t[1]
                     else format(t[0], ",") + " – " + format(t[1], ",")) + " SAR"

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
            t = price_of(c, tiers)
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
            # Start a priced selection from exactly what this client picked.
            + " <form method='post' action='" + u("/selections/new") + "' class='inline'>"
            "<input type='hidden' name='request' value='" + str(r["id"]) + "'>"
            "<button class='btn small ghost'>Price &amp; send</button></form>"
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


# ------------------------------------------------------------ selections --

def _money(lo, hi):
    if lo is None:
        return "—"
    return (format(lo, ",") if lo == hi else format(lo, ",") + " – " + format(hi, ",")) + " SAR"


def selection_link(sel, origin):
    """What the client is sent. The page reads the creators and prices from
    the server by token; the name and codes ride along so the link still reads
    as a selection before anything has loaded."""
    from urllib.parse import quote
    codes = json.loads(sel["codes"] or "[]")
    return (origin + "/selection/#n=" + quote(sel["name"]) + "&c=" + ",".join(codes)
            + "&s=" + sel["token"])


def selections_page(sels, error=None, message=None, origin=""):
    note = ""
    if error:
        note += "<div class='err'>" + e(error) + "</div>"
    if message:
        note += "<div class='ok'>" + e(message) + "</div>"
    rows = []
    for x in sels:
        n = len(json.loads(x["codes"] or "[]"))
        total = _money(x["total_from"], x["total_to"]) if x["total_from"] is not None else "sum of creators"
        if x["request_id"]:
            src = "quote request #" + str(x["request_id"])
        elif ("code_label" in x.keys() and x["code_label"]):
            src = "built by " + e(x["code_label"])
        elif x["code_id"]:
            src = "built by a client"
        else:
            src = "pasted link"
        rows.append(
            "<tr><td><strong><a href='" + u("/selections/edit") + "?id=" + str(x["id"]) + "'>"
            + e(x["name"]) + "</a></strong><br><span class='muted'>from " + src + "</span>"
            + "</td><td>" + str(n) + "</td><td>" + total + "</td><td class='muted'>" + ago(x["updated_at"])
            + "</td><td class='right'><a class='btn small' href='" + u("/selections/edit") + "?id="
            + str(x["id"]) + "'>Adjust prices</a></td></tr>")
    table = "".join(rows) or ("<tr><td colspan='5' class='muted'>No selections yet. One appears "
                              "here as soon as a client names a shortlist on the catalogue.</td></tr>")
    body = (
        "<h1>Selections</h1><p class='sub'>Every shortlist a client names on the catalogue "
        "appears here by itself, ready to be priced — there is no link to paste. Adjust the "
        "prices and the client's own link shows them as soon as you save, and every later change "
        "too. A client who goes back and adds a creator updates the same selection; the total you "
        "typed is cleared then, because it was for a different shortlist.</p>"
        + note
        + "<form method='post' action='" + u("/selections/new") + "' class='card'><div class='row'>"
        + "<div style='flex:3'><label>Or paste a selection link</label><input name='link' required "
          "placeholder='https://influencer-catalogue.hellovoice.co.uk/selection/#n=…&amp;c=…'></div>"
        + "<div style='align-self:end'><button class='btn'>Adjust prices</button></div>"
        + "</div><p class='price-hint'>For a selection sent as a quote request, use "
          "<a href='" + u("/requests") + "'>Price &amp; send</a> on the Requests page instead.</p></form>"
        + "<div class='card'><table><thead><tr><th>Selection</th><th>Creators</th><th>Total</th>"
        + "<th>Updated</th><th></th></tr></thead><tbody>" + table + "</tbody></table></div>"
    )
    return page("Selections", body, "/selections")


def selection_edit_page(sel, creators, bands, origin, error=None, message=None, campaigns=()):
    by = {c["code"]: c for c in creators}
    codes = json.loads(sel["codes"] or "[]")
    own = json.loads(sel["prices"] or "{}")
    keys = sel.keys()
    costs = json.loads((sel["costs"] if "costs" in keys else None) or "{}")
    margin = sel["margin"] if "margin" in keys else None
    margin_txt = "" if margin is None else ("%g" % margin)
    note = ""
    if error:
        note += "<div class='err'>" + e(error) + "</div>"
    if message:
        note += "<div class='ok'>" + e(message) + "</div>"

    lo_sum = hi_sum = 0
    rows = []
    for code in codes:
        c = by.get(code)
        if c is None:
            continue
        default = price_of(c, bands) or (None, None)
        set_ = own.get(code)
        eff = set_ or default
        if eff and eff[0] is not None:
            lo_sum += eff[0]; hi_sum += eff[1]
        shot = ("<img class='thumb sm' src='" + e(links.thumb(c["photo"])) + "' alt='' width='44' height='44'>"
                if c["photo"] else "<span class='thumb sm none'>—</span>")
        val = lambda i: format(set_[i], ",") if set_ else ""
        # The cost this selection was priced from, else the creator's last
        # known cost — a starting point the admin can change.
        cost = costs.get(code)
        if cost is None and "cost" in c.keys():
            cost = c["cost"]
        cost_txt = format(cost, ",") if cost is not None else ""
        rows.append(
            "<tr><td>" + shot + "</td><td><code>" + e(code) + "</code><br>" + e(c["name"])
            + ("" if c["active"] else " <span class='pill dead'>hidden</span>")
            + "<input type='hidden' name='code' value='" + e(code) + "'></td>"
            + "<td>" + e(c["tier"]) + "<br><span class='muted'>" + num(c["followers"]) + "</span>"
            + "".join("<div class='acct'>" + e(a["platform"] or "") + " " + num(a["followers"])
                      + " · " + e(a["tier"] or "—") + "</div>"
                      for a in db_account_tiers(c) if a["followers"]) + "</td>"
            + "<td class='muted'>" + (_money(*default) if default[0] is not None else "—")
        )
        rows[-1] += (
            "</td><td><input name='cost' value='" + cost_txt + "' placeholder='cost' inputmode='numeric'>"
            + "<div class='profit'></div></td>"
            + "<td><input name='p_from' value='" + val(0) + "' placeholder='from' inputmode='numeric'></td>"
            + "<td><input name='p_to' value='" + val(1) + "' placeholder='to' inputmode='numeric'></td>"
            + "<td><label class='tick'><input type='checkbox' name='drop' value='" + e(code) + "'> remove</label></td></tr>")
    table = "".join(rows) or "<tr><td colspan='8' class='muted'>No creators yet — add some below.</td></tr>"
    missing = [c for c in codes if c not in by]
    link = selection_link(sel, origin)
    tf = "" if sel["total_from"] is None else format(sel["total_from"], ",")
    tt = "" if sel["total_to"] is None else format(sel["total_to"], ",")
    body = (
        "<p><a href='" + u("/selections") + "'>&larr; All selections</a></p>"
        + "<h1>" + e(sel["name"]) + "</h1>" + note
        + "<div class='card'><label>Link to send the client</label><div class='sel-link'>"
        + "<input id='sel-url' value='" + e(link) + "' readonly>"
        + "<button type='button' class='btn small' onclick=\"var i=document.getElementById('sel-url');"
          "i.select();navigator.clipboard&&navigator.clipboard.writeText(i.value);"
          "this.textContent='Copied'\">Copy link</button>"
        + "<a class='btn small ghost' href='" + e(link) + "' target='_blank' rel='noopener'>Preview</a></div>"
        + "<p class='price-hint'>The link the client already has shows these prices too, once saved, "
          "as long as the creators are the same — so a price change needs no new link. If you add or "
          "remove creators, send this link instead. The client opens it with their passcode.</p></div>"
        + "<form method='post' action='" + u("/selections/save") + "' enctype='multipart/form-data'>"
        + "<input type='hidden' name='id' value='" + str(sel["id"]) + "'>"
        + "<div class='card'><div class='row'>"
        + "<div style='flex:2'><label>Selection name (the client sees this)</label>"
          "<input name='name' value='" + e(sel["name"]) + "' required></div>"
        + "<div><label>Quoted for</label><select name='platform'>"
        + "".join("<option value='" + e(v) + "'" + (" selected" if (sel["platform"] or "") == v else "")
                  + ">" + e(lbl) + "</option>"
                  for v, lbl in [("", "Every platform they are on")] + [(p, p + " only") for p in PLATFORMS])
        + "</select><div class='price-hint'>Pick one and each creator is tiered and priced on "
          "THAT account — a creator who is Mid-Tier on Instagram and Micro on TikTok is quoted "
          "as Micro for a TikTok campaign.</div></div>"
        + "<div><label>Total the client sees (SAR)</label><div style='display:flex;gap:6px'>"
          "<input name='total_from' value='" + tf + "' placeholder='from' inputmode='numeric'>"
          "<input name='total_to' value='" + tt + "' placeholder='to' inputmode='numeric'></div>"
          "<div class='price-hint'>Empty = the sum of the creators below (currently "
        + _money(lo_sum, hi_sum) + ").</div></div>"
        + "</div></div>"
        + "<div class='card'><div class='row'>"
          "<div><label>Profit margin (%)</label><div class='margin-box'>"
          "<input name='margin' id='sel-margin' value='" + margin_txt + "' placeholder='e.g. 30' "
          "inputmode='decimal'></div>"
          "<div class='price-hint'>Added on top of each creator's cost. Client price = cost × "
          "(1 + margin), rounded up to the next 10 SAR. Internal only — the client never sees "
          "the cost or the margin.</div></div>"
          "<div style='flex:2'><dl class='money-sum' id='sel-money'></dl></div>"
          "</div></div>"
        + "<div class='card'><table class='sel-table'><thead><tr><th></th><th>Creator</th><th>Tier</th>"
          "<th>Standard price</th><th>Cost to us</th><th>Price for this client</th><th></th><th></th>"
          "</tr></thead><tbody>"
        + table + "</tbody></table>"
        + ("<p class='err'>No longer in the roster, left out: " + e(", ".join(missing)) + "</p>" if missing else "")
        + "<p class='price-hint'>Type a creator's cost and their price is worked out from the "
          "margin above. With no cost, type the price yourself, or leave it empty to use the "
          "creator's standard price. One figure = a fixed price. The client never sees a price "
          "against a creator — these add up to the total they see, unless you type a total above. "
          "A price set here becomes that creator's price on the roster as well, and a cost is "
          "remembered for their next selection.</p>"
        + "<div class='row'><div style='flex:2'><label>Add creators (optional)</label>"
          "<input name='add' placeholder='HV-MC-005, HV-MD-012 …'></div></div>"
        + "</div><button class='btn'>Save prices</button></form>"
        + "<form method='post' action='" + u("/selections/delete") + "' style='margin-top:14px' "
          "onsubmit=\"return confirm('Delete this selection? Its link stops working.')\">"
          "<input type='hidden' name='id' value='" + str(sel["id"]) + "'>"
          "<button class='btn small danger'>Delete selection</button></form>"
        + campaign_start_card(sel, campaigns)
        + MARGIN_JS
    )
    return page(sel["name"] + " — Selection", body, "/selections")


# Live pricing on the selection page: typing a cost or the margin shows the
# client price and the profit at once. The server does the same sum on save
# (db.client_price), so what is shown here is what gets stored.
MARGIN_JS = """<script>
(function(){
  var m=document.getElementById('sel-margin'), sum=document.getElementById('sel-money');
  if(!m||!sum) return;
  function n(v){v=String(v||'').replace(/[^0-9.]/g,'');return v===''?null:Number(v);}
  function fmt(x){return Math.round(x).toLocaleString('en-US')+' SAR';}
  function price(cost,mg){return Math.ceil(cost*(1+(mg||0)/100)/10)*10;}
  var rows=[].slice.call(document.querySelectorAll('.sel-table tbody tr')).filter(function(r){
    return r.querySelector('input[name=cost]');});
  function run(){
    var mg=n(m.value), tc=0, tp=0, priced=0;
    rows.forEach(function(r){
      var c=r.querySelector('input[name=cost]'), lo=r.querySelector('input[name=p_from]'),
          hi=r.querySelector('input[name=p_to]'), out=r.querySelector('.profit'),
          gone=r.querySelector('input[name=drop]').checked, cost=n(c.value);
      if(cost===null){
        if(lo.readOnly){lo.value='';hi.value='';}
        lo.readOnly=hi.readOnly=false; out.textContent=''; return;
      }
      var p=price(cost,mg);
      lo.value=hi.value=p.toLocaleString('en-US'); lo.readOnly=hi.readOnly=true;
      out.textContent='+'+fmt(p-cost)+' profit';
      if(!gone){tc+=cost;tp+=p;priced++;}
    });
    sum.innerHTML=priced?('<div><dt>Cost ('+priced+')</dt><dd>'+fmt(tc)+'</dd></div>'+
      '<div><dt>Client price</dt><dd>'+fmt(tp)+'</dd></div>'+
      '<div><dt>Profit</dt><dd class="gain">'+fmt(tp-tc)+'</dd></div>'):
      '<div><dt>Profit</dt><dd class="muted" style="font-size:14px;font-weight:400">'+
      'Type a cost against a creator to see it.</dd></div>';
  }
  document.addEventListener('input',function(e){
    if(e.target===m||e.target.name==='cost') run();});
  document.addEventListener('change',function(e){if(e.target.name==='drop') run();});
  run();
})();
</script>"""


# ---------------------------------------------------------------- campaigns --

STATUS_PILL = {"draft": "warn", "live": "live", "ended": ""}


def status_pill(status):
    return "<span class='pill " + STATUS_PILL.get(status, "") + "'>" + e(status) + "</span>"


def _date_value(value):
    """A timestamp as the YYYY-MM-DD a date input takes, in UTC like the
    timestamps themselves."""
    if not value:
        return ""
    return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%d")


def _dates(k):
    a, b = _date_value(k["starts_at"]), _date_value(k["ends_at"])
    if not a and not b:
        return "<span class='muted'>no dates</span>"
    return e(a or "?") + " → " + e(b or "?")


def campaign_start_card(sel, campaigns):
    """On a selection: turn it into a campaign, or open the ones already made
    from it. A second campaign from the same shortlist is allowed — a second
    wave is a new campaign — so the button is always there."""
    made = "".join(
        "<li><a href='" + u("/campaigns/edit") + "?id=" + str(k["id"]) + "'>" + e(k["name"])
        + "</a> " + status_pill(k["status"]) + "</li>" for k in campaigns)
    return (
        "<h2>Campaign</h2><div class='card'>"
        + ("<p>Campaigns started from this selection:</p><ul>" + made + "</ul>" if made else
           "<p class='muted'>Booked? Start a campaign from this selection. Its creators, client "
           "passcode, platform and costs are copied in; the campaign is a draft until you set it live.</p>")
        + "<form method='post' action='" + u("/campaigns/new") + "'>"
        + "<input type='hidden' name='selection' value='" + str(sel["id"]) + "'>"
        + "<button class='btn small'>" + ("Start another campaign" if made else "Start campaign")
        + "</button></form></div>")


def campaigns_page(camps, codes, error=None, message=None):
    note = ""
    if error:
        note += "<div class='err'>" + e(error) + "</div>"
    if message:
        note += "<div class='ok'>" + e(message) + "</div>"
    rows = []
    for k in camps:
        who = k["client"] or k["code_label"] or "—"
        src = ("from selection " + e(k["selection_name"])) if k["selection_name"] else "started blank"
        rows.append(
            "<tr><td><strong><a href='" + u("/campaigns/edit") + "?id=" + str(k["id"]) + "'>"
            + e(k["name"]) + "</a></strong><br><span class='muted'>" + src + "</span></td>"
            + "<td>" + e(who) + "</td><td>" + status_pill(k["status"]) + "</td>"
            + "<td>" + _dates(k) + "</td><td>" + str(k["creators"]) + "</td>"
            + "<td class='muted'>" + ago(k["updated_at"]) + "</td>"
            + "<td class='right'><a class='btn small' href='" + u("/campaigns/edit") + "?id="
            + str(k["id"]) + "'>Open</a></td></tr>")
    table = "".join(rows) or ("<tr><td colspan='7' class='muted'>No campaigns yet. Start one from a "
                              "selection, or create a blank one above.</td></tr>")
    body = (
        "<h1>Campaigns</h1><p class='sub'>Creators booked for a client, the dates they post in and "
        "the rules that decide which posts count. Everything is set here; the client only views "
        "the report. Start one from a booked <a href='" + u("/selections") + "'>selection</a> "
        "to copy its creators, passcode and costs, or create a blank one.</p>"
        + note
        + "<form method='post' action='" + u("/campaigns/new") + "' class='card'><div class='row'>"
        + "<div style='flex:2'><label>Campaign name</label><input name='name' required "
          "placeholder='e.g. SVR Sun Secure — Wave 4'></div>"
        + "<div><label>Client (brand)</label><input name='client' placeholder='e.g. SVR'></div>"
        + "<div><label>Passcode that sees it</label>" + code_select(codes, None) + "</div>"
        + "<div style='align-self:end'><button class='btn'>Create campaign</button></div>"
        + "</div></form>"
        + "<div class='card'><table><thead><tr><th>Campaign</th><th>Client</th><th>Status</th>"
        + "<th>Dates</th><th>Creators</th><th>Updated</th><th></th></tr></thead><tbody>"
        + table + "</tbody></table></div>"
    )
    return page("Campaigns", body, "/campaigns")


def code_select(codes, chosen):
    """The access codes a report can be shown to. Revoked and expired codes
    are left out unless already chosen, so an old choice is not silently lost."""
    opts = ["<option value=''>— none yet —</option>"]
    for c in codes:
        ok, why = code_state(c)
        if not ok and c["id"] != chosen:
            continue
        label = c["label"] + ("" if ok else " (" + why + ")")
        opts.append("<option value='" + str(c["id"]) + "'" + (" selected" if c["id"] == chosen else "")
                    + ">" + e(label) + "</option>")
    return "<select name='code_id'>" + "".join(opts) + "</select>"


def _rules_text(rules):
    return " ".join(rules["hashtags"] + rules["mentions"] + rules["keywords"])


def campaign_edit_page(k, members, codes, rules, selection=None, error=None, message=None,
                       logo_names=(), selections=(), rep=None):
    """Setup as six plain steps, top to bottom, with a checklist that says
    what is still missing. Every step saves with the one button at the end."""
    import metrics
    from db import campaign_targets, campaign_logos
    note = _notes(error, message)
    targets = campaign_targets(k)
    chosen_logos = campaign_logos(k)
    vis = metrics.visibility(k)

    checks = [("Client passcode chosen", bool(k["code_id"])),
              ("Dates set", bool(k["starts_at"] and k["ends_at"])),
              ("Creators added", bool(members)),
              ("Posts per creator planned", bool(members) and all(m["planned"] for m in members)),
              ("Hashtags / mentions to track", bool(rules["hashtags"] or rules["mentions"] or rules["keywords"])),
              ("Targets set", bool(targets)),
              ("Brand logo chosen", bool(chosen_logos)),
              ("Current step marked", any(x["state"] == "active" for x in __import__("db").campaign_steps(k))),
              ("Set live", k["status"] == "live")]
    done = sum(1 for _, ok in checks if ok)
    nxt = next((label for label, ok in checks if not ok), None)
    checklist = ("<div class='card guide'><div class='guide-head'><strong>Setup " + str(done) + " of "
                 + str(len(checks)) + " done</strong>"
                 + ("<span class='muted'> — next: " + e(nxt) + "</span>" if nxt else
                    "<span class='pill live'>ready</span>") + "</div><ol class='guide-steps'>"
                 + "".join("<li class='" + ("ok" if ok else "") + "'>" + e(label) + "</li>" for label, ok in checks)
                 + "</ol></div>")

    rows, total_cost = [], 0
    for c in members:
        code = c["cc_code"]
        gone = c["code"] is None
        shot = ("<img class='thumb sm' src='" + e(links.thumb(c["photo"])) + "' alt='' width='44' height='44'>"
                if not gone and c["photo"] else "<span class='thumb sm none'>—</span>")
        who = ("<span class='pill dead'>no longer in the roster</span>" if gone else
               e(c["name"]) + ("" if c["active"] else " <span class='pill dead'>hidden</span>"))
        accounts = "" if gone else ("".join(
            "<div class='acct'><a href='" + e(a["url"]) + "' target='_blank' rel='noopener'>"
            + e(a["platform"] or "link") + "</a> " + num(a["followers"]) + "</div>"
            for a in split_profiles(c["profiles"])
            if a.get("url") and (not k["platform"] or a["platform"] == k["platform"]))
            or "<span class='muted'>no " + e(k["platform"] or "") + " profile on file</span>")
        cost = c["campaign_cost"]
        total_cost += cost or 0
        rows.append(
            "<tr><td>" + shot + "</td><td><code>" + e(code) + "</code><br>" + who
            + "<input type='hidden' name='code' value='" + e(code) + "'></td><td>" + accounts + "</td>"
            + "<td><input name='planned' value='" + ("" if c["planned"] is None else str(c["planned"]))
            + "' placeholder='e.g. 2' inputmode='numeric' style='width:80px'></td>"
            + "<td><input name='cost' value='" + (format(cost, ",") if cost is not None else "")
            + "' placeholder='fee' inputmode='numeric'></td>"
            + "<td><label class='tick'><input type='checkbox' name='drop' value='" + e(code) + "'> remove</label></td></tr>")
    table = "".join(rows) or "<tr><td colspan='6' class='muted'>No creators yet — add some below.</td></tr>"

    status_opts = "".join("<option value='" + v + "'" + (" selected" if k["status"] == v else "") + ">" + l + "</option>"
                          for v, l in [("draft", "Draft — the client cannot see it"), ("live", "Live — captured every 24 hours"),
                                       ("ended", "Ended — kept for the client to read")])
    from db import campaign_steps
    state_lbl = [("pending", "Not started"), ("active", "In progress"), ("done", "Done")]
    step_rows = "".join(
        "<tr><td><label class='tick'><input type='checkbox' name='step_on_" + x["key"] + "' value='1'"
        + (" checked" if x["on"] else "") + "><span></span></label></td>"
        "<td><input name='step_label_" + x["key"] + "' value='" + e(x["label"]) + "'></td>"
        "<td><input type='date' name='step_start_" + x["key"] + "' value='" + e(x["start"] or "") + "'></td>"
        "<td><input type='date' name='step_end_" + x["key"] + "' value='" + e(x["end"] or "") + "'></td>"
        "<td><select name='step_state_" + x["key"] + "'>" + "".join(
            "<option value='" + v + "'" + (" selected" if x["state"] == v else "") + ">" + l + "</option>"
            for v, l in state_lbl) + "</select></td></tr>"
        for x in campaign_steps(k))
    plat_opts = "".join("<option value='" + e(v) + "'" + (" selected" if (k["platform"] or "") == v else "") + ">" + e(lbl)
                        + "</option>" for v, lbl in [("", "Every platform they are on")] + [(p, p + " only") for p in PLATFORMS])
    sel_opts = "<option value=''>— none —</option>" + "".join(
        "<option value='" + str(x["id"]) + "'" + (" selected" if k["selection_id"] == x["id"] else "") + ">"
        + e(x["name"]) + "</option>" for x in selections)
    chips = "".join("<span class='pill'>" + e(w) + "</span>" for w in rules["hashtags"] + rules["mentions"] + rules["keywords"])
    logo_ticks = "".join(
        "<label class='logo-pick'><input type='checkbox' name='logo' value='clients/" + e(n) + "'"
        + (" checked" if ("clients/" + n) in chosen_logos else "") + "><img src='/assets/clients/" + e(n)
        + "' alt='' loading='lazy'><span>" + e(n.rsplit(".", 1)[0].replace("-", " ")) + "</span></label>"
        for n in logo_names)
    uploaded = "".join(
        "<label class='logo-pick'><input type='checkbox' name='logo' value='" + e(x) + "' checked><img src='"
        + u("/campaigns/logo") + "?n=" + e(x.split("/", 1)[1]) + "' alt=''><span>uploaded</span></label>"
        for x in chosen_logos if x.startswith("upload/"))
    obj_now = metrics.objective_of(k)
    obj_opts = "".join(
        "<option value='" + key + "'" + (" selected" if key == obj_now else "") + ">" + e(label) + " — reach "
        + str(int(w[0] * 100)) + "% · engagement " + str(int(w[1] * 100)) + "% · eng. rate " + str(int(w[2] * 100))
        + "% · clicks " + str(int(w[3] * 100)) + "%</option>" for key, (label, w) in metrics.OBJECTIVES.items())
    tgt = lambda key, label, hint: ("<div><label>" + label + "</label><input name='target_" + key + "' inputmode='decimal' value='"
                                    + (("%g" % targets[key]) if key in targets else "") + "' placeholder='" + hint + "'></div>")

    def step(n, title, body, hint=""):
        return ("<section class='step'><h2><span class='step-n'>" + str(n) + "</span>" + title + "</h2>"
                + ("<p class='sub'>" + hint + "</p>" if hint else "") + "<div class='card'>" + body + "</div></section>")

    sync = ""
    if k["selection_id"]:
        sync = ("<form method='post' action='" + u("/campaigns/sync") + "' class='inline'>"
                "<input type='hidden' name='id' value='" + str(k["id"]) + "'>"
                "<button class='btn small ghost'>Add creators added to the selection since</button></form>")
    body = (
        _head(k, "setup") + note + checklist
        + "<form method='post' action='" + u("/campaigns/save") + "' enctype='multipart/form-data' id='camp-form'>"
        + "<input type='hidden' name='id' value='" + str(k["id"]) + "'>"
        + "<input type='hidden' name='updated_at' value='" + str(k["updated_at"]) + "'>"
        + step(1, "Client &amp; selection",
               "<div class='row'><div style='flex:2'><label>Campaign name (the client sees this)</label>"
               "<input name='name' value='" + e(k["name"]) + "' required></div>"
               "<div><label>Brand name</label><input name='client' value='" + e(k["client"] or "") + "' placeholder='e.g. SVR'></div></div>"
               "<div class='row'><div><label>Client passcode — who can open the report</label>" + code_select(codes, k["code_id"]) + "</div>"
               "<div><label>Selection it came from</label><select name='selection_id'>" + sel_opts + "</select></div></div>"
               + (("<p class='price-hint'>Linked to selection <a href='" + u("/selections/edit") + "?id=" + str(selection["id"]) + "'>"
                   + e(selection["name"]) + "</a>. </p>" + sync) if selection else
                  "<p class='price-hint'>Tip: start campaigns from a selection so its creators, passcode and costs come with it.</p>"),
               "Who the campaign is for. The passcode decides which client sees the report.")
        + step(2, "Dates &amp; status",
               "<div class='row'><div><label>First day</label><input type='date' name='starts' value='" + _date_value(k["starts_at"]) + "'></div>"
               "<div><label>Last day</label><input type='date' name='ends' value='" + _date_value(k["ends_at"]) + "'></div>"
               "<div><label>Visibility</label><select name='status'>" + status_opts + "</select></div></div>"
               "<label style='margin-top:6px'>Scope of work — the client follows these steps on the report</label>"
               "<table class='steps-table'><thead><tr><th>Show</th><th>Step</th><th>Starts</th><th>Ends</th><th>State</th></tr></thead>"
               "<tbody>" + step_rows + "</tbody></table>"
               "<div class='row' style='margin-top:12px'><div style='flex:2'><label>Status message for the client</label>"
               "<input name='status_note' maxlength='240' value='" + e(k["status_note"] or "")
               + "' placeholder='e.g. Shooting wraps Thursday; publishing starts 14 Oct'></div></div>",
               "Untick steps this campaign does not include. Mark the one under way as In progress — the client sees it highlighted.")
        + step(3, "Creators &amp; posts planned",
               "<table class='sel-table'><thead><tr><th></th><th>Creator</th><th>Accounts tracked</th>"
               "<th>Posts planned</th><th>Fee to us (SAR)</th><th></th></tr></thead><tbody>" + table + "</tbody></table>"
               "<div class='row' style='margin-top:14px'><div style='flex:2'><label>Add creators by code</label>"
               "<input name='add' placeholder='HV-MC-005, HV-MD-012 …'></div>"
               "<div><label>Platform tracked</label><select name='platform'>" + plat_opts + "</select></div></div>",
               "Posts planned is what each creator is booked for; the report counts delivered against it. Fees stay internal.")
        + step(4, "What counts as a campaign post",
               "<label>Hashtags, @mentions and keywords</label>"
               "<textarea name='rules' placeholder='#svr #suncare @svr_ksa sunscreen'>" + e(_rules_text(rules)) + "</textarea>"
               "<div class='rules'>" + chips + "</div>"
               "<div class='row' style='margin-top:14px'><div><label>Required disclosure</label>"
               "<input name='disclosure' value='" + e(" ".join(rules["disclosure"])) + "' placeholder='#ad #إعلان'></div>"
               "<div style='flex:2'><label>Affiliate link destination (optional)</label>"
               "<input name='destination' type='url' value='" + e(k["destination"] or "") + "' placeholder='https://brand-store…'></div></div>",
               "A post in the dates carrying any of these counts. Leave the destination empty if this campaign has no affiliate links.")
        + step(5, "Objective &amp; targets",
               "<div class='row'><div style='flex:3'><label>Campaign objective — decides how the leaderboard scores creators</label>"
               "<select name='objective'>" + obj_opts + "</select></div></div>"
               + recommend_card(metrics.recommend_targets(k))
               + "<label style='margin-top:16px'>Targets the client sees</label>"
               "<div class='row'>" + tgt("posts", "Posts", "e.g. 24") + tgt("views", "Views", "e.g. 500000")
               + tgt("reach", "Reach", "e.g. 300000") + tgt("engagement", "Engagement", "e.g. 20000")
               + tgt("er", "Avg ER %", "e.g. 3") + tgt("clicks", "Affiliate clicks", "e.g. 1500") + "</div>",
               "What the campaign should reach by its last day. The report shows progress and says whether it is on track. "
               "Tier benchmarks for ER and views live in Settings.")
        + step(6, "Client report look",
               "<label>Brand logos on the report</label><div class='logo-grid'>" + uploaded + logo_ticks + "</div>"
               "<div class='row' style='margin-top:12px'><div><label>Or upload a logo — PNG with a transparent background</label>"
               "<input type='file' name='logo_file' accept='image/*' multiple></div></div>"
               "<label style='margin-top:14px'>Sections the client sees</label><div class='ticks'>"
               + "".join("<label class='tick'><input type='checkbox' name='vis_" + key + "' value='1'" + (" checked" if vis[key] else "")
                         + "><span>" + lbl + "</span></label>" for key, lbl in
                         [("reach", "Reach &amp; impressions"), ("clicks", "Affiliate link clicks"),
                          ("all_content", "Posts outside the hashtags")])
               + "</div><p class='price-hint'>These apply to the dashboard and the full report. Costs, CPM, EMV, notes and ratings are never shown to the client.</p>")
        + "<h2>Internal</h2><div class='card'><div class='row'>"
        + "<div><label>Total cost to us (SAR)</label><input name='total_cost' value='"
        + (format(k["cost"], ",") if k["cost"] is not None else "") + "' inputmode='numeric'>"
          "<div class='price-hint'>Empty = the sum of the fees (" + format(total_cost, ",") + " SAR).</div></div>"
        + "<div style='flex:2'><label>Internal notes</label><textarea name='notes'>" + e(k["notes"] or "") + "</textarea></div>"
        + "</div><details><summary>EMV rates for this campaign (internal)</summary><div class='row' style='margin-top:10px'>"
        + "".join("<div><label>" + a_ + "</label><input name='emv_" + a_ + "' inputmode='decimal' value='"
                  + ((("%g" % json.loads(k["emv"]).get("*", {}).get(a_)) if (k["emv"] and json.loads(k["emv"]).get("*", {}).get(a_)) else ""))
                  + "' placeholder='default'></div>" for a_ in ["impressions", "views", "likes", "comments", "shares", "saves", "clicks"])
        + "</div></details></div>"
        + "<div class='savebar'><button class='btn'>Save campaign</button>"
          "<a class='btn ghost' href='" + u("/campaigns/report") + "?id=" + str(k["id"]) + "'>See the report</a></div></form>"
        + "<form method='post' action='" + u("/campaigns/delete") + "' style='margin-top:24px' "
          "onsubmit=\"return confirm('Delete this campaign? Its report and links stop working.')\">"
          "<input type='hidden' name='id' value='" + str(k["id"]) + "'>"
          "<button class='btn small danger'>Delete campaign</button></form>"
    )
    return page(k["name"] + " — Campaign", body, "/campaigns")

def campaign_tabs(k, on):
    tabs = [("setup", "/campaigns/edit", "Setup"), ("content", "/campaigns/content", "Content"),
            ("insights", "/campaigns/insights", "Insights"),
            ("links", "/campaigns/links", "Tracking links &amp; clicks"),
            ("report", "/campaigns/report", "Report")]
    return ("<nav class='tabs'>" + "".join(
        "<a href='" + u(href) + "?id=" + str(k["id"]) + "'" + (" class='on'" if key == on else "")
        + ">" + label + "</a>" for key, href, label in tabs) + "</nav>")


def link_gone():
    """What a visitor sees on a link that is off: plain, branded, no admin
    chrome and nothing about the campaign."""
    return (HEAD + "<title>Link not active</title><style>body{font-family:system-ui,sans-serif;"
            "background:#f7f5f0;color:#121212;display:grid;place-items:center;min-height:100vh;margin:0}"
            "main{max-width:420px;padding:24px;text-align:center}h1{font-size:22px}"
            "p{color:#6b6b6b}</style></head><body><main><h1>This link is not active</h1>"
            "<p>The page it pointed to is no longer available through this link.</p>"
            "</main></body></html>")


def _bars(rows, label=lambda r: r["k"], limit=12):
    if not rows:
        return "<p class='empty muted'>No clicks yet.</p>"
    peak = max(r["n"] for r in rows)
    return "".join(hbar(label(r), r["n"], peak) for r in rows[:limit])


def clicks_chart(by_day):
    """Clicks and unique visitors per day, drawn with the same SVG chart as
    the Analytics page so the two read alike."""
    if not by_day:
        return "<p class='empty muted'>No clicks yet.</p>"
    return activity_chart([{"d": d["d"], "opens": d["n"], "shortlists": d["u"], "requests": 0}
                           for d in by_day]).replace(
        "Opens and shortlists per day", "Clicks and unique visitors per day").replace(
        " opens</title>", " clicks</title>").replace(" shortlists</title>", " unique</title>") + (
        "<p class='muted' style='font-size:13px'><span style='color:#121212'>&#9632;</span> clicks &nbsp; "
        "<span style='color:#b9d400'>&#9632;</span> unique visitors</p>")


def campaign_links_page(k, rows, st, origin, has_geo, error=None, message=None):
    note = ""
    if error:
        note += "<div class='err'>" + e(error) + "</div>"
    if message:
        note += "<div class='ok'>" + e(message) + "</div>"
    if not k["destination"]:
        note += ("<div class='card muted'>No affiliate destination set — fine if this campaign has no links. "
                 "To use links, set the destination in step 4 on the <a href='" + u("/campaigns/edit")
                 + "?id=" + str(k["id"]) + "'>Setup</a> tab, or give a link its own below.</div>")
    names = {r["code"]: (r["creator_name"] or r["code"]) for r in rows}

    items = []
    for r in rows:
        url = origin + "/go/" + r["slug"]
        dest = r["destination"] or ""
        locked = r["hits"] > 0
        items.append(
            "<tr class='linkrow'><td><code>" + e(r["code"]) + "</code><br>" + e(names[r["code"]])
            + ("" if r["is_default"] else "<br><span class='pill own'>custom: " + e(r["label"] or "link") + "</span>")
            + ("" if r["active"] else " <span class='pill dead'>off</span>") + "</td>"
            + "<td><div class='sel-link'><input value='" + e(url) + "' readonly>"
            + "<button type='button' class='btn small' onclick=\"var i=this.previousSibling;i.select();"
              "navigator.clipboard&&navigator.clipboard.writeText(i.value);this.textContent='Copied'\">Copy</button></div>"
            + "<details><summary class='muted'>Change</summary>"
            + "<form method='post' action='" + u("/campaigns/link") + "'>"
            + "<input type='hidden' name='id' value='" + str(k["id"]) + "'>"
            + "<input type='hidden' name='slug' value='" + e(r["slug"]) + "'>"
            + "<div><label>Link name</label><input name='new_slug' value='" + e(r["slug"]) + "'"
            + (" readonly title='Already clicked — renaming would break it where it is posted'" if locked else "")
            + "></div><div><label>Send this creator's visitors to</label><input name='destination' "
              "type='url' value='" + e(dest) + "' placeholder='campaign default'></div>"
            + "<div><button class='btn small'>Save</button></div></form></details></td>"
            + "<td class='right'><strong>" + str(r["clicks"]) + "</strong></td>"
            + "<td class='right'>" + str(r["uniques"]) + "</td>"
            + "<td><form method='post' action='" + u("/campaigns/link/toggle") + "'><input type='hidden' name='id' value='"
            + str(k["id"]) + "'><input type='hidden' name='slug' value='" + e(r["slug"]) + "'><button class='btn tiny ghost'>"
            + ("Switch off" if r["active"] else "Switch on") + "</button></form></td></tr>")
    table = "".join(items) or ("<tr><td colspan='4' class='muted'>No creators in this campaign yet — "
                               "add them on the Setup tab and each gets a link here.</td></tr>")
    body = (
        "<p><a href='" + u("/campaigns") + "'>&larr; All campaigns</a></p>"
        + "<h1>" + e(k["name"]) + " " + status_pill(k["status"]) + "</h1>"
        + campaign_tabs(k, "links") + note
        + "<div class='kpis'>"
        + "<div><span>Clicks</span><b>" + format(st["clicks"], ",") + "</b></div>"
        + "<div><span>Unique visitors</span><b>" + format(st["uniques"], ",") + "</b></div>"
        + "<div><span>Creators with clicks</span><b>" + str(len(st["by_creator"])) + "</b></div>"
        + "<div><span>Last click</span><b style='font-size:16px'>" + (ago(st["last"]) if st["last"] else "—") + "</b></div>"
        + "</div>"
        + "<h2>Links</h2><div class='card'><p class='price-hint'>Each creator puts their own link in "
          "their bio, story link sticker or video description. A tap is counted, then the visitor is "
          "sent on with UTM tags (utm_source = the app, utm_campaign, utm_content = creator code) so the "
          "client's own analytics sees the same visitors. A link's name is fixed once it has been clicked.</p>"
        + "<table><thead><tr><th>Creator</th><th>Tracking link</th><th class='right'>Clicks</th>"
          "<th class='right'>Unique</th><th></th></tr></thead><tbody>" + table + "</tbody></table></div>"
        + custom_link_form(k, rows, names)
        + "<h2>Clicks over time</h2><div class='card'>" + clicks_chart(st["by_day"]) + "</div>"
        + "<div class='split'>"
        + "<div><h2>By creator</h2><div class='card'>" + _bars(st["by_creator"], lambda r: names.get(r["k"], r["k"])) + "</div></div>"
        + "<div><h2>By app</h2><div class='card'>" + _bars(st["by_app"]) + "</div></div>"
        + "<div><h2>By country</h2><div class='card'>" + _bars(st["by_country"])
        + ("" if has_geo else "<p class='price-hint'>Country lookup is not installed on this server yet "
           "(see docs/ADMIN.md §5b), so countries read Unknown.</p>")
        + "<p class='price-hint'>IP geolocation by <a href='https://db-ip.com' target='_blank' rel='noopener'>DB-IP</a>.</p></div></div>"
        + "<div><h2>By device</h2><div class='card'>" + _bars(st["by_device"]) + (_bars(st["by_os"]) if st["by_os"] else "") + "</div></div>"
        + "</div>"
        + "<p class='muted' style='margin-top:18px'>Unique = one device per link per day. Link previews and "
          "bots are recorded but not counted (" + str(st["bots"]) + " so far). "
          "<a href='" + u("/campaigns/clicks.csv") + "?id=" + str(k["id"]) + "'>Download every click (CSV)</a></p>"
    )
    return page(k["name"] + " — Links", body, "/campaigns")


# ------------------------------------------------------------- formatting --

def fmt(v, digits=0):
    if v is None:
        return "—"
    if digits:
        return format(v, ",." + str(digits) + "f")
    return format(int(round(v)), ",")


def fpct(v):
    return "—" if v is None else ("%.2f%%" % v)


def fsar(v):
    return "—" if v is None else fmt(v) + " SAR"


def _when(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%d %b %Y") if t else "—"


def _notes(error, message):
    out = ""
    if error:
        out += "<div class='err'>" + e(error) + "</div>"
    if message:
        out += "<div class='ok'>" + e(message) + "</div>"
    return out


def _head(k, tab, error=None, message=None):
    return ("<p><a href='" + u("/campaigns") + "'>&larr; All campaigns</a></p>"
            + "<h1>" + e(k["name"]) + " " + status_pill(k["status"]) + "</h1>"
            + campaign_tabs(k, tab) + _notes(error, message))


def client_report_card(k):
    import metrics
    vis = metrics.visibility(k)
    own = {}
    try:
        own = (json.loads(k["emv"]) if k["emv"] else {}).get("*", {})
    except (ValueError, AttributeError):
        own = {}
    boxes = "".join(
        "<label class='tick'><input type='checkbox' name='vis_" + key + "' value='1'"
        + (" checked" if vis[key] else "") + "><span>" + label + "</span></label>"
        for key, label in [("reach", "Reach &amp; impressions"), ("clicks", "Link clicks"),
                           ("emv", "EMV"), ("all_content", "Posts outside the rules (All content)")])
    rates = "".join(
        "<div><label>" + e(a) + " (SAR each)</label><input name='emv_" + a + "' inputmode='decimal' value='"
        + (("%g" % own[a]) if own.get(a) else "") + "' placeholder='default'></div>"
        for a in ["impressions", "views", "likes", "comments", "shares", "saves", "clicks"])
    return (
        "<h2>Client report</h2><div class='card'>"
        + "<label>What the client sees</label><div class='ticks'>" + boxes + "</div>"
        + "<div class='price-hint'>Cost, CPM and cost per click are never shown to the client.</div>"
        + "<details style='margin-top:12px'><summary>EMV rates for this campaign only</summary>"
        + "<div class='row' style='margin-top:10px'>" + rates + "</div>"
        + "<div class='price-hint'>Leave all empty to use the workspace rates on "
          "<a href='" + u("/settings") + "'>Settings</a>.</div></details></div>")


KIND_LABEL = {"post": "Post", "reel": "Reel", "story": "Story", "video": "Video", "short": "Short"}


def campaign_content_page(k, members, posts, error=None, message=None):
    opts = "".join("<option value='" + e(m["cc_code"]) + "'>" + e(m["cc_code"] + " — " + (m["name"] or ""))
                   + "</option>" for m in members)
    plats = "".join("<option" + (" selected" if (k["platform"] or "Instagram") == p else "") + ">"
                    + e(p) + "</option>" for p in PLATFORMS)
    kinds = "".join("<option value='" + v + "'>" + l + "</option>" for v, l in KIND_LABEL.items())
    rows = []
    for p in posts:
        thumb = ("<img class='post-thumb' src='" + e(p["thumb"]) + "' alt='' loading='lazy' "
                 "referrerpolicy='no-referrer' onerror=\"this.style.visibility='hidden'\">") if p["thumb"] else \
                "<span class='post-thumb'></span>"
        est = lambda real: "<span class='real'>real</span>" if real else "<span class='est'>est.</span>"
        flag = ""
        if p["disclosure_ok"] == 0:
            flag = " <span class='pill warn' title='None of the required disclosure tags'>no disclosure</span>"
        sec = ("<span class='pill live'>campaign</span>" if p["section"] == "campaign"
               else "<span class='pill'>all content</span>")
        if p["hidden"]:
            sec += " <span class='pill dead'>hidden</span>"
        cid = str(k["id"]); pid = str(p["id"])
        act = lambda what, label, extra="": (
            "<form class='inline' method='post' action='" + u("/campaigns/content/update") + "'>"
            "<input type='hidden' name='id' value='" + cid + "'><input type='hidden' name='content' value='" + pid + "'>"
            "<input type='hidden' name='do' value='" + what + "'><button class='btn tiny ghost'" + extra + ">"
            + label + "</button></form> ")
        actions = (act("other" if p["section"] == "campaign" else "campaign",
                       "Move to all content" if p["section"] == "campaign" else "Count it")
                   + act("unhide" if p["hidden"] else "hide", "Unhide" if p["hidden"] else "Hide")
                   + act("delete", "Delete", " onclick=\"return confirm('Delete this post and its history?')\""))
        edit = ("<details><summary class='muted'>Enter numbers</summary>"
                "<form method='post' action='" + u("/campaigns/content/update") + "' class='mini'>"
                "<input type='hidden' name='id' value='" + cid + "'><input type='hidden' name='content' value='" + pid + "'>"
                "<input type='hidden' name='do' value='metrics'>"
                + "".join("<input name='" + m + "' placeholder='" + m + "' inputmode='numeric' value='"
                          + ("" if p.get(m) is None else str(p[m])) + "'> " for m in ("likes", "comments", "views", "shares", "saves"))
                + "<button class='btn tiny'>Save today's numbers</button></form></details>")
        rows.append(
            "<tr><td>" + thumb + "</td><td><strong>" + e(p.get("creator_name") or p["code"]) + "</strong><br>"
            + "<span class='muted'>" + e(p["platform"]) + " · " + KIND_LABEL.get(p["kind"], p["kind"]) + " · "
            + _when(p["posted_at"]) + "</span><br><a href='" + e(p["url"]) + "' target='_blank' rel='noopener'>open post</a>"
            + "<div class='muted' style='max-width:340px;font-size:12px'>" + e((p["caption"] or "")[:160]) + "</div></td>"
            + "<td>" + sec + flag + "</td>"
            + "<td class='right'>" + fmt(p["likes"]) + "<br><span class='muted'>" + fmt(p["comments"]) + " comments</span></td>"
            + "<td class='right'>" + (fmt(p["views"]) if p["video"] else "—") + "</td>"
            + "<td class='right'>" + fmt(p["reach"]) + " " + est(p["reach_real"]) + "<br>"
            + ("" if p["video"] else fmt(p["impressions"]) + " imp. " + est(p["impressions_real"])) + "</td>"
            + "<td class='right'>" + fpct(p["er"] if not p["video"] else p["video_er"]) + "</td>"
            + "<td>" + actions + edit + "<span class='muted' style='font-size:12px'>numbers "
            + ago(p["metrics_at"]) + " · " + e(p["source"]) + "</span></td></tr>")
    table = "".join(rows) or ("<tr><td colspan='8' class='muted'>No posts yet. The capture job adds them "
                              "every 24 hours while the campaign is live, or add one below.</td></tr>")
    body = (
        _head(k, "content", error, message)
        + "<div class='card'><table><thead><tr><th></th><th>Post</th><th>Counts as</th><th class='right'>Likes</th>"
          "<th class='right'>Views</th><th class='right'>Reach / impressions</th><th class='right'>ER</th><th></th>"
          "</tr></thead><tbody>" + table + "</tbody></table>"
        + "<p class='price-hint'>est. = estimated (see Settings for how); real = from the creator's own "
          "insights, approved on the Insights tab. ER for videos is engagement ÷ views.</p></div>"
        + "<h2>Add a post by link</h2>"
        + "<form method='post' action='" + u("/campaigns/content/add") + "' class='card'>"
        + "<input type='hidden' name='id' value='" + str(k["id"]) + "'>"
        + "<div class='row'><div><label>Creator</label><select name='code' required>" + opts + "</select></div>"
        + "<div><label>Platform</label><select name='platform'>" + plats + "</select></div>"
        + "<div><label>Type</label><select name='kind'>" + kinds + "</select></div>"
        + "<div><label>Posted on</label><input type='date' name='posted'></div></div>"
        + "<div class='row'><div style='flex:3'><label>Post link</label><input name='url' type='url' required "
          "placeholder='https://www.instagram.com/p/…'></div></div>"
        + "<div class='row'><div style='flex:3'><label>Caption (decides whether it counts)</label>"
          "<textarea name='caption'></textarea></div></div>"
        + "<div class='row mini'>" + "".join("<div><label>" + m + "</label><input name='" + m + "' inputmode='numeric'></div>"
                                             for m in ("likes", "comments", "views", "shares", "saves"))
        + "</div><button class='btn'>Add post</button></form>"
    )
    return page(k["name"] + " — Content", body, "/campaigns")


def campaign_report_page(k, r, origin):
    t, inn = r["total"], r["internal"]
    link = origin + "/campaign/dashboard/#t=" + k["token"]
    full = origin + "/campaign/#t=" + k["token"]
    kp = lambda label, val, sub="": ("<div><span>" + label + "</span><b>" + val + "</b>"
                                     + ("<span>" + sub + "</span>" if sub else "") + "</div>")
    real = int(round(t["real_share"] * 100))
    crow = "".join(
        "<tr><td><code>" + e(c["code"]) + "</code> " + e(c["name"]) + "</td><td class='right'>" + str(c["posts"])
        + "</td><td class='right'>" + fmt(c["views"]) + "</td><td class='right'>" + fmt(c["reach"])
        + "</td><td class='right'>" + fmt(c["engagement"]) + "</td><td class='right'>" + fpct(c["er"])
        + "</td><td class='right'>" + fmt(c["clicks"]) + "</td><td class='right'>" + fsar(c["emv"])
        + "</td><td class='right'>" + fsar(c.get("cost")) + "</td><td class='right'>" + fsar(c.get("cpm"))
        + "</td></tr>" for c in r["creators"])
    body = (
        _head(k, "report")
        + "<div class='card'><label>Client's report link</label><div class='sel-link'>"
        + "<input id='rep-url' value='" + e(link) + "' readonly>"
        + "<button type='button' class='btn small' onclick=\"var i=document.getElementById('rep-url');i.select();"
          "navigator.clipboard&&navigator.clipboard.writeText(i.value);this.textContent='Copied'\">Copy link</button>"
        + "<a class='btn small ghost' href='" + e(link) + "' target='_blank' rel='noopener'>Open dashboard</a>"
        + "<a class='btn small ghost' href='" + e(full) + "' target='_blank' rel='noopener'>Open full report</a></div>"
        + "<p class='price-hint'>The link opens the campaign dashboard; the client can switch to the full report from it. They open it with their passcode"
        + ("" if k["code_id"] else " — <strong>no passcode is set on the Setup tab yet, so nobody can open it</strong>")
        + ". A draft campaign is not shown to the client.</p></div>"
        + "<h2>Results</h2><div class='kpis'>"
        + kp("Posts", fmt(t["posts"])) + kp("Views", fmt(t["views"])) + kp("Reach", fmt(t["reach"]), "%d%% real" % real)
        + kp("Impressions", fmt(t["impressions"])) + kp("Engagement", fmt(t["engagement"]))
        + kp("Avg ER", fpct(t["er"])) + kp("Video ER", fpct(t["video_er"])) + kp("Impressions ER", fpct(t["imp_er"]))
        + kp("Clicks", fmt(t["clicks"])) + kp("CTR", fpct(t["ctr"]))
        + kp("EMV", fsar(t["emv"]) if r["emv_set"] else "not set", "" if r["emv_set"] else "set rates in Settings")
        + "</div><h2>Internal</h2><div class='kpis'>"
        + kp("Cost", fsar(inn["cost"])) + kp("CPM", fsar(inn["cpm"])) + kp("Cost / engagement", fsar(inn["cpe"]) if inn["cpe"] is None else fmt(inn["cpe"], 2) + " SAR")
        + kp("Cost / click", fsar(inn["cpc"]) if inn["cpc"] is None else fmt(inn["cpc"], 2) + " SAR")
        + "</div><h2>By creator</h2><div class='card'><table><thead><tr><th>Creator</th><th class='right'>Posts</th>"
          "<th class='right'>Views</th><th class='right'>Reach</th><th class='right'>Engagement</th><th class='right'>ER</th>"
          "<th class='right'>Clicks</th><th class='right'>EMV</th><th class='right'>Fee</th><th class='right'>CPM</th>"
          "</tr></thead><tbody>" + (crow or "<tr><td colspan='10' class='muted'>No creators.</td></tr>")
        + "</tbody></table></div>"
        + "<p><a class='btn' href='" + u("/campaigns/export.xlsx") + "?id=" + str(k["id"]) + "'>Download workbook (Excel)</a> "
        + "<a class='btn ghost' href='" + u("/campaigns/export.csv") + "?id=" + str(k["id"]) + "'>Posts (CSV)</a></p>"
        + "<p class='muted'>CPM = cost ÷ (impressions + views) × 1,000. Counts only posts that match the rules "
          "and are not hidden.</p>"
    )
    return page(k["name"] + " — Report", body, "/campaigns")


def settings_page(rates, factors, token_set, runs, has_geo, new_token=None, error=None, message=None,
                  bm=None):
    own = (rates or {}).get("*", {})
    inputs = "".join(
        "<div><label>" + e(a) + " (SAR each)</label><input name='emv_" + a + "' inputmode='decimal' value='"
        + (("%g" % own[a]) if own.get(a) else "") + "'></div>"
        for a in ["impressions", "views", "likes", "comments", "shares", "saves", "clicks"])
    run_rows = "".join(
        "<tr><td>" + ts(r["at"]) + "</td><td>" + ("<span class='pill live'>ok</span>" if r["ok"] else "<span class='pill dead'>failed</span>")
        + "</td><td class='right'>" + fmt(r["posts"]) + "</td><td class='right'>" + fmt(r["insights"])
        + "</td><td class='muted' style='font-size:12px'>" + e((r["errors"] or "")[:300]) + "</td></tr>" for r in runs)
    token_box = ""
    if new_token:
        token_box = ("<div class='ok'>New capture token — copy it now, it is not shown again:"
                     + copyable(new_token) + "</div>")
    body = (
        "<h1>Settings</h1><p class='sub'>Campaign tracker settings for the whole workspace.</p>"
        + _notes(error, message) + token_box
        + "<form method='post' action='" + u("/settings/save") + "'>"
        + "<h2>EMV rates</h2><div class='card'><div class='row'>" + inputs + "</div>"
        + "<p class='price-hint'>Earned media value = each count × its rate, in SAR. Empty or 0 = not counted. "
          "With every rate empty EMV is not shown anywhere. A campaign can override these on its Setup tab. "
          "Agree the rates with the client before they see EMV.</p></div>"
        + "<h2>Estimates</h2><div class='card'><div class='row'>"
        + "<div><label>Reach per engagement (posts)</label><input name='reach_per_engagement' value='%g'></div>" % factors["reach_per_engagement"]
        + "<div><label>Story views ÷ followers</label><input name='story_view_rate' value='%g'></div>" % factors["story_view_rate"]
        + "<div><label>Impressions per reach (posts)</label><input name='impressions_per_reach' value='%g'></div>" % factors["impressions_per_reach"]
        + "</div><p class='price-hint'>Used only where the creator's own insights are not approved yet. "
          "Post reach = engagement × the first figure, never more than the creator's followers; "
          "story reach = followers × the second; impressions = reach × the third (stories: = reach). "
          "Video reach = its views.</p></div>"
        + benchmarks_card(bm)
        + "<button class='btn'>Save settings</button></form>"
        + "<h2>Capture job</h2><div class='card'>"
        + "<p>The scheduled Claude job on the team Mac signs in with this token. "
        + ("A token is set." if token_set else "<strong>No token yet — the capture job cannot connect.</strong>")
        + " See docs/CAPTURE-AGENT.md.</p>"
        + "<form method='post' action='" + u("/settings/token") + "' onsubmit=\"return confirm('Make a new token? The old one stops working at once.')\">"
        + "<button class='btn small'>" + ("Replace token" if token_set else "Create token") + "</button></form>"
        + "<table style='margin-top:14px'><thead><tr><th>Run</th><th></th><th class='right'>Posts</th>"
          "<th class='right'>Insights read</th><th>Errors</th></tr></thead><tbody>"
        + (run_rows or "<tr><td colspan='5' class='muted'>No capture runs yet.</td></tr>") + "</tbody></table></div>"
        + "<h2>Country lookup</h2><div class='card'><p>" + ("Installed." if has_geo else
          "Not installed — tracking-link countries read Unknown. See docs/ADMIN.md §5b.") + "</p></div>"
    )
    return page("Settings", body, "/settings")


def campaign_insights_page(k, items, members, content, origin, error=None, message=None):
    names = {m["cc_code"]: (m["name"] or m["cc_code"]) for m in members}
    by_code = {}
    for c in content:
        by_code.setdefault(c["code"], []).append(c)

    def post_opts(code, chosen):
        out = ["<option value=''>— which post? —</option>"]
        for c in by_code.get(code, []):
            label = KIND_LABEL.get(c["kind"], c["kind"]) + " · " + _when(c["posted_at"]) + " · " + c["url"][-38:]
            out.append("<option value='" + str(c["id"]) + "'" + (" selected" if c["id"] == chosen else "")
                       + ">" + e(label) + "</option>")
        return "".join(out)

    pill = {"pending": "<span class='pill warn'>waiting to be read</span>",
            "extracted": "<span class='pill own'>read — check and approve</span>",
            "approved": "<span class='pill live'>approved</span>",
            "rejected": "<span class='pill dead'>rejected</span>"}
    cards = []
    for i in items:
        files = json.loads(i["files"] or "[]")
        vals = {}
        for src in (i["extracted"], i["approved"]):
            try:
                vals.update(json.loads(src or "{}"))
            except ValueError:
                pass
        shots = "".join("<a href='" + u("/campaigns/insight-file") + "?id=" + str(k["id"]) + "&i=" + str(i["id"])
                        + "&n=" + e(n) + "' target='_blank'><img class='shot' src='" + u("/campaigns/insight-file")
                        + "?id=" + str(k["id"]) + "&i=" + str(i["id"]) + "&n=" + e(n) + "' alt='insight screenshot' "
                        "loading='lazy'></a>" for n in files)
        fields = "".join("<div><label>" + f.replace("_", " ") + "</label><input name='" + f + "' inputmode='numeric' value='"
                         + ("" if vals.get(f) is None else str(vals[f])) + "'></div>" for f in
                         ["reach", "impressions", "views", "likes", "comments", "shares", "saves",
                          "profile_visits", "link_clicks", "sticker_taps"])
        decided = i["status"] in ("approved", "rejected")
        cards.append(
            "<div class='card'><div class='grid2'><div>" + shots + "</div><div>"
            + "<p><strong>" + e(names.get(i["code"], i["code"])) + "</strong> " + pill.get(i["status"], "")
            + "<br><span class='muted'>uploaded " + ago(i["uploaded_at"]) + "</span>"
            + ("<br>Post they named: <a href='" + e(i["post_url"]) + "' target='_blank' rel='noopener'>"
               + e(i["post_url"][:60]) + "</a>" if i["post_url"] else "")
            + ("<br><em>" + e(i["note"]) + "</em>" if i["note"] else "") + "</p>"
            + "<form method='post' action='" + u("/campaigns/insights/decide") + "'>"
            + "<input type='hidden' name='id' value='" + str(k["id"]) + "'><input type='hidden' name='insight' value='"
            + str(i["id"]) + "'><label>Post</label><select name='post'>" + post_opts(i["code"], i["content_id"])
            + "</select><div class='row' style='margin-top:10px'>" + fields + "</div>"
            + "<button class='btn small' name='do' value='approve'>" + ("Approve again" if decided else "Approve")
            + "</button> <button class='btn small danger' name='do' value='reject'>Reject</button></form>"
            + "<p class='price-hint'>Check each number against the screenshot. Approved numbers replace the "
              "estimates on the client's report.</p></div></div></div>")
    up_links = "".join(
        "<tr><td><code>" + e(m["cc_code"]) + "</code> " + e(names[m["cc_code"]]) + "</td><td><div class='sel-link'>"
        "<input value='" + e(origin + "/insights/" + (m["insights_token"] or "")) + "' readonly>"
        "<button type='button' class='btn small' onclick=\"var i=this.previousSibling;i.select();"
        "navigator.clipboard&&navigator.clipboard.writeText(i.value);this.textContent='Copied'\">Copy</button></div></td></tr>"
        for m in members if m["insights_token"])
    copts = "".join("<option value='" + e(m["cc_code"]) + "'>" + e(m["cc_code"] + " — " + names[m["cc_code"]]) + "</option>"
                    for m in members)
    body = (
        _head(k, "insights", error, message)
        + "<p class='sub'>Creators upload screenshots of their own insights (reach, impressions, story views). "
          "The capture job reads the numbers; you check and approve. Until then the report uses estimates.</p>"
        + ("".join(cards) or "<div class='card muted'>No insight screenshots yet.</div>")
        + "<h2>Upload links for creators</h2><div class='card'><table><tbody>"
        + (up_links or "<tr><td class='muted'>No creators yet.</td></tr>") + "</tbody></table>"
        + "<p class='price-hint'>Send each creator their own link (WhatsApp is fine). No login; it works until "
          "30 days after the campaign ends and only for that creator's posts.</p></div>"
        + "<h2>Upload on a creator's behalf</h2>"
        + "<form method='post' action='" + u("/campaigns/insights/upload") + "' enctype='multipart/form-data' class='card'>"
        + "<input type='hidden' name='id' value='" + str(k["id"]) + "'><div class='row'>"
        + "<div><label>Creator</label><select name='code'>" + copts + "</select></div>"
        + "<div style='flex:2'><label>Screenshots</label><input type='file' name='shots' accept='image/*' multiple required></div>"
        + "</div><button class='btn small'>Upload</button></form>"
    )
    return page(k["name"] + " — Insights", body, "/campaigns")


def insights_upload_page(row, posts, sent, ok=None, error=None):
    """The creator's own page: plain, mobile-first, English and Arabic, in the
    catalogue's colours. It says nothing about other creators or the client's
    numbers."""
    opts = "".join("<option value='" + str(p["id"]) + "'>" + e(KIND_LABEL.get(p["kind"], p["kind"]) + " · "
                   + p["platform"] + " · " + _when(p["posted_at"])) + "</option>" for p in posts)
    msg = ""
    if ok:
        msg = "<p class='ok'>Thank you — received. &nbsp;·&nbsp; <span dir='rtl'>شكرًا، تم الاستلام.</span></p>"
    if error:
        msg = "<p class='err'>" + e(error) + "</p>"
    return (
        HEAD + "<title>Insights upload — HelloVoice</title><style>"
        "body{margin:0;background:#121212;color:#fff;font-family:system-ui,-apple-system,'Segoe UI',sans-serif}"
        "main{max-width:520px;margin:0 auto;padding:32px 18px 60px}"
        ".eyebrow{display:inline-block;background:#e8ff76;color:#121212;font-weight:700;letter-spacing:.12em;"
        "font-size:12px;padding:5px 14px;border-radius:999px;transform:rotate(-3deg)}"
        "h1{font-size:28px;margin:18px 0 6px}p{color:rgba(255,255,255,.72);line-height:1.6}"
        "label{display:block;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:rgba(255,255,255,.6);margin:18px 0 6px}"
        "select,input,textarea{width:100%;box-sizing:border-box;font:inherit;padding:12px 14px;border-radius:12px;"
        "border:1px solid rgba(255,255,255,.25);background:#1d1d1d;color:#fff}"
        "button{margin-top:22px;width:100%;font:inherit;font-weight:700;padding:15px;border:0;border-radius:999px;"
        "background:#e8ff76;color:#121212;cursor:pointer}"
        ".ok{background:#14884a;color:#fff;padding:12px 14px;border-radius:12px}"
        ".err{background:#ee1515;color:#fff;padding:12px 14px;border-radius:12px}"
        ".ar{direction:rtl;text-align:right;color:rgba(255,255,255,.6);font-size:14px}"
        "ul{color:rgba(255,255,255,.72);line-height:1.7;padding-left:18px}</style></head><body><main>"
        + "<span class='eyebrow'>HELLOVOICE</span><h1>Hi " + e(row["creator_name"] or "") + "</h1>"
        + "<p>Upload screenshots of your insights for <strong>" + e(row["campaign_name"]) + "</strong>.</p>"
        + "<p class='ar'>ارفع لقطات شاشة من إحصائيات المنشور (Insights) لهذه الحملة.</p>"
        + "<ul><li>Reach / accounts reached &amp; impressions</li><li>Story views, link / sticker taps</li>"
          "<li>Shares and saves</li></ul>"
        + msg
        + "<form method='post' enctype='multipart/form-data'>"
        + "<label>Which post · أي منشور</label><select name='post'>" + opts
        + "<option value=''>Another post (paste link below) · منشور آخر</option></select>"
        + "<label>Post link, if not listed · رابط المنشور</label><input name='url' type='url' placeholder='https://'>"
        + "<label>Screenshots (up to 6) · لقطات الشاشة</label><input type='file' name='shots' accept='image/*' multiple required>"
        + "<label>Note (optional) · ملاحظة</label><textarea name='note' rows='2'></textarea>"
        + "<button>Send · إرسال</button></form>"
        + ("<p style='margin-top:24px;font-size:13px'>Uploaded so far: " + str(sent) + "</p>" if sent else "")
        + "</main></body></html>")


def benchmarks_card(bm):
    if not bm:
        return ""
    import metrics
    def line(label, name, pair):
        return ("<tr><td>" + label + "</td><td><input name='" + name + "_good' value='" + ("%g" % pair[0])
                + "' inputmode='decimal'></td><td><input name='" + name + "_ok' value='" + ("%g" % pair[1])
                + "' inputmode='decimal'></td></tr>")
    er_rows = "".join(line(e(metrics.BAND_LABEL[b]), "bm_er_" + b, bm["er"][b])
                      for b in ["nano", "micro", "mid", "macro", "mega"])
    other = "".join(line(label, "bm_" + key, bm[key])
                    for key, label in [("video_er", "Video ER % (engagement ÷ views)"),
                                       ("view_rate", "Video views ÷ followers %"),
                                       ("story_rate", "Story reach ÷ followers %"), ("ctr", "Link click-through %")])
    return ("<h2>Benchmarks</h2><div class='card'><p class='sub'>What the report calls good (green), moderate (amber) "
            "or low (red). These are industry guides; campaigns add their own targets on the Setup tab.</p>"
            "<table><thead><tr><th>Engagement rate % by tier</th><th>Good from</th><th>Moderate from</th></tr></thead><tbody>"
            + er_rows + other + "</tbody></table></div>")


def custom_link_form(k, rows, names):
    codes = []
    for r in rows:
        if r["code"] not in codes:
            codes.append(r["code"])
    if not codes:
        return ""
    opts = "".join("<option value='" + e(c) + "'>" + e(c + " — " + names.get(c, c)) + "</option>" for c in codes)
    return ("<h2>Add a custom link</h2><form method='post' action='" + u("/campaigns/link/custom") + "' class='card'>"
            "<input type='hidden' name='id' value='" + str(k["id"]) + "'><div class='row'>"
            "<div><label>Creator</label><select name='code'>" + opts + "</select></div>"
            "<div><label>Link name (after /go/)</label><input name='slug' required placeholder='svr-noura-story'></div>"
            "<div><label>Purpose</label><input name='label' placeholder='e.g. Story swipe-up'></div>"
            "<div style='flex:2'><label>Sends people to</label><input name='destination' type='url' placeholder='https://… (empty = campaign destination)'></div>"
            "</div><button class='btn small'>Add link</button><p class='price-hint'>Same domain as the catalogue — "
            "nothing to buy or set up. Use one when a creator promotes two pages, or you want a story link counted "
            "apart from the bio link.</p></form>")


PHASE_LABEL = dict(__import__("db").PHASES)


def clients_page(overview, origin):
    """One card per client: their passcode, then the chain from shortlist to
    campaign to report, each a link into the page that controls it."""
    cards = []
    for o in overview:
        c = o["code"]
        ok, why = code_state(c)
        sels = "".join(
            "<li><a href='" + u("/selections/edit") + "?id=" + str(x["id"]) + "'>" + e(x["name"]) + "</a> "
            "<span class='muted'>" + str(len(json.loads(x["codes"] or "[]"))) + " creators</span>"
            + "".join(" <span class='arrow'>→</span> <a href='" + u("/campaigns/edit") + "?id=" + str(kk["id"]) + "'>"
                      + e(kk["name"]) + "</a> " + status_pill(kk["status"])
                      for kk in o["campaigns"] if kk["selection_id"] == x["id"]) + "</li>"
            for x in o["selections"])
        loose = [kk for kk in o["campaigns"] if not kk["selection_id"] or
                 kk["selection_id"] not in {x["id"] for x in o["selections"]}]
        camps = "".join(
            "<li><a href='" + u("/campaigns/edit") + "?id=" + str(kk["id"]) + "'>" + e(kk["name"]) + "</a> "
            + status_pill(kk["status"]) + " <span class='muted'>" + e(PHASE_LABEL.get(kk["phase"] or "", "")) + " · "
            + str(kk["creators"]) + " creators · " + str(kk["posts"]) + " posts</span> "
            + "<a class='btn tiny ghost' href='" + u("/campaigns/report") + "?id=" + str(kk["id"]) + "'>Report</a></li>"
            for kk in o["campaigns"])
        open_reqs = [r for r in o["requests"] if not r["handled_at"]]
        cards.append(
            "<div class='card'><div style='display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap'>"
            "<div><h3 style='margin:0'>" + e(c["label"]) + "</h3><span class='muted'>passcode · "
            + ("<span class='pill live'>active</span>" if ok else "<span class='pill dead'>" + e(why) + "</span>")
            + "</span></div><div class='muted' style='font-size:13px'>"
            + (str(len(open_reqs)) + " open quote request(s) · " if open_reqs else "")
            + (str(o["analysis_requests"]) + " analysis request(s)" if o["analysis_requests"] else "") + "</div></div>"
            + "<div class='grid2' style='margin-top:12px'><div><label>Selections → campaigns</label><ul class='chain-list'>"
            + (sels or "<li class='muted'>No selections yet.</li>") + "</ul></div>"
            + "<div><label>All campaigns</label><ul class='chain-list'>" + (camps or "<li class='muted'>None yet.</li>")
            + "</ul></div></div></div>")
    body = ("<h1>Clients</h1><p class='sub'>Each client is one passcode. Follow it from the shortlist they picked to the "
            "campaign it became and the report they see. Everything links to the page that controls it.</p>"
            + ("".join(cards) or "<div class='card muted'>No clients yet — issue a passcode on Access codes.</div>"))
    return page("Clients", body, "/clients")


def analysis_page(creators, have, requests, origin, q="", error=None, message=None):
    open_reqs = [r for r in requests if not r["handled_at"]]
    req_rows = "".join(
        "<tr><td><code>" + e(r["code"]) + "</code> " + e(r["creator_name"] or "") + "</td><td>" + e(r["code_label"] or "—")
        + "</td><td class='muted'>" + ago(r["at"]) + "</td><td>"
        + ("<span class='pill live'>uploaded</span>" if r["code"] in have else "<span class='pill warn'>waiting</span>")
        + "</td><td><form method='post' action='" + u("/analysis/handled") + "'><input type='hidden' name='id' value='"
        + str(r["id"]) + "'><button class='btn tiny ghost'>Mark handled</button></form></td></tr>" for r in open_reqs)
    term = (q or "").strip().lower()
    shown = [c for c in creators if not term or term in (c["code"] + " " + c["name"]).lower()]
    rows = "".join(
        "<tr><td><code>" + e(c["code"]) + "</code></td><td>" + e(c["name"]) + "</td><td>"
        + ("<span class='pill live'>full analysis · " + ago(have[c["code"]]) + "</span>" if c["code"] in have
           else "<span class='pill'>locked</span>") + "</td><td>"
        + "<a class='btn tiny ghost' href='" + e(origin + "/creator/#c=" + c["code"]) + "' target='_blank' rel='noopener'>Preview</a> "
        + ("<a class='btn tiny ghost' href='" + u("/analysis") + "?q=" + e(c["code"]) + "#edit'>Edit</a>")
        + "</td></tr>" for c in shown[:200])
    editor = ""
    if term and len(shown) == 1:
        c = shown[0]
        editor = ("<h2 id='edit'>Edit " + e(c["code"]) + " — " + e(c["name"]) + "</h2><form method='post' action='"
                  + u("/analysis/save") + "' class='card'><input type='hidden' name='code' value='" + e(c["code"]) + "'>"
                  "<label>Analysis as JSON</label><textarea name='json' id='an-json' style='min-height:260px;font-family:ui-monospace,monospace;font-size:12px'></textarea>"
                  "<div class='savebar'><button class='btn small'>Save analysis</button></div></form>"
                  "<script>fetch('" + u("/analysis/json") + "?c=" + e(c["code"]) + "').then(r=>r.text()).then(t=>{document.getElementById('an-json').value=t});</script>"
                  + ("<form method='post' action='" + u("/analysis/delete") + "' onsubmit=\"return confirm('Remove this analysis?')\">"
                     "<input type='hidden' name='code' value='" + e(c["code"]) + "'><button class='btn small danger'>Remove analysis</button></form>"
                     if c["code"] in have else ""))
    body = (
        "<h1>Creator analysis</h1><p class='sub'>Full profile analyses clients open from the catalogue and reports. "
        "A creator without one shows a locked page with <em>Request full analysis</em>; requests land below.</p>"
        + _notes(error, message)
        + "<div class='grid2'><div class='card'><h3 style='margin-top:0'>1 · Download the template</h3>"
          "<p class='muted'>One workbook, many creators, laid out like a Modash profile report: Overview, Audience "
          "(followers and likers), Growth, Posts, Brands (with logos), Hashtags &amp; mentions — every row starts with "
          "the creator code.</p>"
          "<a class='btn small' href='" + u("/analysis/template.xlsx") + "'>Download template (.xlsx)</a></div>"
        + "<form class='card' method='post' action='" + u("/analysis/upload") + "' enctype='multipart/form-data'>"
          "<h3 style='margin-top:0'>2 · Upload it filled in</h3><input type='file' name='file' accept='.xlsx' required>"
          "<p class='price-hint'>Uploading a creator again replaces their analysis and closes their open requests.</p>"
          "<button class='btn small'>Upload analyses</button></form></div>"
        + "<h2>Requests from clients</h2><div class='card'><table><thead><tr><th>Creator</th><th>Client</th><th>Asked</th>"
          "<th>Status</th><th></th></tr></thead><tbody>" + (req_rows or "<tr><td colspan='5' class='muted'>No open requests.</td></tr>")
        + "</tbody></table></div>"
        + editor
        + "<h2>Creators</h2><form class='card' method='get' action='" + u("/analysis") + "'><div class='row'>"
          "<div style='flex:3'><input name='q' value='" + e(q) + "' placeholder='Search by code or name'></div>"
          "<div><button class='btn small'>Search</button></div></div></form>"
        + "<div class='card'><table><thead><tr><th>Code</th><th>Name</th><th>Analysis</th><th></th></tr></thead><tbody>"
        + (rows or "<tr><td colspan='4' class='muted'>No creators match.</td></tr>") + "</tbody></table>"
        + ("<p class='muted'>Showing the first 200 — search to narrow.</p>" if len(shown) > 200 else "") + "</div>")
    return page("Creator analysis", body, "/analysis")


def recommend_card(rec):
    """Recommended targets for this campaign: a safe figure to promise the
    client and a stretch figure to aim for, with one click to use them."""
    if not rec["safe"]:
        return "<p class='price-hint'>" + e(" ".join(rec["notes"])) + "</p>"
    label = {"posts": "Posts", "views": "Views", "reach": "Reach", "engagement": "Engagement",
             "er": "Avg ER %", "clicks": "Affiliate clicks"}
    rows = ""
    for key in ["posts", "views", "reach", "engagement", "er", "clicks"]:
        if key not in rec["safe"] or rec["safe"][key] is None:
            continue
        lead = key in rec.get("primary", [])
        fmt_ = (lambda v: "%g%%" % v) if key == "er" else (lambda v: format(v, ","))
        rows += ("<tr" + (" class='rec-lead'" if lead else "") + "><td>" + label[key]
                 + (" <span class='pill live'>headline for " + e(rec["objective"]) + "</span>" if lead else "")
                 + "</td><td class='right'><strong>" + fmt_(rec["safe"][key]) + "</strong></td><td class='right muted'>"
                 + fmt_(rec["stretch"][key]) + "</td></tr>")
    data = json.dumps({k: v for k, v in rec["safe"].items() if v is not None})
    return ("<div class='rec card' style='background:#f7f5f0;margin:14px 0 6px'>"
            "<div style='display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:baseline'>"
            "<strong>Recommended targets</strong><button type='button' class='btn small' "
            "onclick='hvUseSafe(this)' data-safe='" + e(data) + "'>Use safe targets</button></div>"
            "<table style='margin-top:10px'><thead><tr><th>Target</th><th class='right'>Safe — promise this</th>"
            "<th class='right'>Stretch — aim for this</th></tr></thead><tbody>" + rows + "</tbody></table>"
            "<p class='price-hint'>Built from each creator's posts planned: safe uses the fair benchmark for their size "
            "(or 80% of their own averages when their full analysis is uploaded), stretch the strong benchmark (or 100%). "
            "Promise the safe figure; it leaves a margin. " + e(" ".join(rec["notes"])) + "</p>"
            "<script>function hvUseSafe(b){var d=JSON.parse(b.getAttribute('data-safe'));"
            "Object.keys(d).forEach(function(k){var i=document.querySelector('[name=target_'+k+']');if(i)i.value=d[k];});"
            "b.textContent='Filled — save to keep';}</script></div>")
