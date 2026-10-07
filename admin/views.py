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
import urllib.parse
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


LEGACY_CSS = """
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
/* Every page on one row: the header runs the full width, the links never
   wrap, and on a screen too narrow for them all the row scrolls sideways. */
header.top .wrap{max-width:none;padding:0 28px}
nav{display:flex;align-items:center;gap:18px;flex-wrap:nowrap;white-space:nowrap;
min-width:0;overflow-x:auto;scrollbar-width:none}
nav::-webkit-scrollbar{display:none}
nav a{display:inline-flex;align-items:center;padding:6px 0;margin:0;color:#fff;flex:none;
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
.pager{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:14px 0 4px}
.pager a,.pager .pgnow,.pager .pgoff{min-width:34px;height:34px;display:inline-grid;place-items:center;
  padding:0 10px;border-radius:999px;font-size:14px;text-decoration:none}
.pager a{border:1px solid var(--line);color:var(--ink)}
.pager a:hover{border-color:var(--ink)}
.pager .pgnow{background:var(--ink);color:#fff;font-weight:600}
.pager .muted{margin-right:8px}
.btn.lime{background:var(--lime);color:var(--ink);border-color:var(--lime)}
.btn.lime:hover{background:var(--ink);color:var(--lime);border-color:var(--ink)}
td.nowrap{white-space:nowrap}
tr.linkrow.is-off td{background:#f6f4f1}
tr.linkrow.is-off td:not(:last-child){opacity:.55}
tr.linkrow:target td{box-shadow:inset 0 2px 0 var(--ink),inset 0 -2px 0 var(--ink)}
a.to-roster{color:inherit;text-decoration:none;border-bottom:1px solid rgba(18,18,18,.25);
  display:inline-flex;align-items:center;gap:5px}
a.to-roster svg{opacity:.45}
a.to-roster:hover{border-bottom-color:var(--ink)}
a.to-roster:hover svg{opacity:1}
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
 header.top .wrap{gap:16px;padding:0 16px}
 nav{gap:14px}
 table,thead,tbody,tr,td,th{display:block}
 thead{display:none}
 td{border:0;padding:4px 0}
 tr{border-bottom:1px solid var(--line);padding:12px 0}
}
"""

import ui
CSS = ui.build_css(LEGACY_CSS)

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


PER_PAGE = 50


def page_slice(total, asked, per=PER_PAGE):
    """(page number, first index) for ?page=, kept inside the list."""
    pages = max(1, -(-total // per))
    n = int(asked) if str(asked or "").isdigit() and int(asked) > 0 else 1
    n = min(n, pages)
    return n, (n - 1) * per


def pager(total, page_no, path, per=PER_PAGE, **params):
    """1 2 3 … links under a long list; the other query parameters kept."""
    pages = max(1, -(-total // per))
    if pages <= 1:
        return ""
    window = sorted({1, pages} | {n for n in range(page_no - 2, page_no + 3) if 1 <= n <= pages})
    out, last = [], 0
    for n in window:
        if n - last > 1:
            out.append("<span class='pgoff'>…</span>")
        if n == page_no:
            out.append("<span class='pgnow'>" + str(n) + "</span>")
        else:
            out.append("<a href='" + u(path) + "?" + urlencode(page=(n if n > 1 else ""), **params) + "'>" + str(n) + "</a>")
        last = n
    first, end = (page_no - 1) * per + 1, min(page_no * per, total)
    return ("<div class='pager'><span class='muted'>" + str(first) + "–" + str(end) + " of " + str(total)
            + "</span>" + "".join(out) + "</div>")


def archive_button(kind, rid, archived):
    return ("<form method='post' action='" + u("/archive") + "' class='inline'>"
            "<input type='hidden' name='kind' value='" + kind + "'><input type='hidden' name='id' value='" + str(rid) + "'>"
            "<input type='hidden' name='on' value='" + ("0" if archived else "1") + "'>"
            "<button class='btn small ghost'>" + ("Unarchive" if archived else "Archive") + "</button></form>")


def archive_tabs(path, archived, n_archived, live_label):
    return ("<div class='row' style='gap:8px;margin:0 0 12px'>"
            "<a class='btn small" + (" ghost" if archived else "") + "' href='" + u(path) + "'>" + live_label + "</a>"
            "<a class='btn small" + ("" if archived else " ghost") + "' href='" + u(path) + "?archived=1'>Archived ("
            + str(n_archived) + ")</a></div>")


def roster_link(code, label):
    """A creator's name that opens their roster edit form, in a new tab so a
    half-filled campaign or selection form is not lost."""
    return ("<a class='to-roster' href='" + u("/roster") + "?" + urlencode(edit=code) + "#" + e(code)
            + "' target='_blank' rel='noopener' title='Edit " + e(code) + " on the roster'>"
            + e(label) + "<svg viewBox='0 0 24 24' width='13' height='13' fill='none' stroke='currentColor' "
            "stroke-width='2' stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'>"
            "<path d='M14 4l6 6M4 20l4-1 11-11-3-3L5 16z'/></svg></a>")


def u(path):
    return (BASE + path) if path.startswith("/") else path


def thumb_src(ref):
    """A post picture kept on our server ("file:<name>"), or a captured link."""
    if ref and str(ref).startswith("file:"):
        return u("/campaigns/thumb?n=" + urllib.parse.quote(str(ref)[5:]))
    return ref or ""


import threading
_user = threading.local()


def set_user(email):
    """Who is signed in, for the request being served (shown in the sidebar)."""
    _user.email = email or ""


def page(title, body, active=""):
    # Requests nobody has handled yet, counted on every page so a new one is
    # seen from wherever the admin happens to be. The page script keeps it
    # live afterwards.
    try:
        from db import request_pulse
        pulse = request_pulse()
    except Exception:
        pulse = {"open": 0, "latest": 0}
    payload = dict(pulse, api=u("/api/pulse"), requests=u("/requests"), analysis=u("/analysis"))
    return ui.shell(title, body + SCROLL_JS, active, u, NAME, pulse, payload, PULSE_JS,
                    getattr(_user, "email", ""))


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
        + '<main class="wrap login" style="max-width:400px;margin:12vh auto 0;padding:0 20px">'
        + '<img src="' + u("/static/logo.webp") + '" alt="HelloVoice" height="30" '
          'style="margin-bottom:22px">'
        + "<h1>" + e(NAME) + "</h1>"
        + "<p class='sub'>Selections, campaigns, creators and clients, in one place.</p>"
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
    """Home: what needs a person today, where everything stands, how the live
    campaigns are going, and how busy the catalogue has been."""
    import overview
    d = overview.home()
    q, pl = d["queue"], d["pipeline"]
    banner = ("<div class='ok'>" + e(message) + "</div>" if message else "") + ("<div class='err'>" + e(error) + "</div>" if error else "")

    # ---- needs you today
    if q:
        tone = {"alert": "var(--red)", "warn": "var(--amber)"}
        rows = "".join(
            "<li><span class='mark' style='background:%s;color:#fff'>%s</span><div class='what'><b>%s</b><span>%s</span></div>"
            "<a class='btn small%s' href='%s'>%s</a></li>" % (
                "var(--ink)" if t == "alert" else "#ece9e3", ui.icon(ic, 15), e(title), e(detail),
                " lime" if t == "alert" else " ghost", u(href), e(label))
            for ic, title, detail, href, label, t in q[:6])
        needs = "<ul class='todo'>" + rows + "</ul>"
    else:
        needs = ui.empty("check", "All clear", "Nothing is waiting for you. A good moment to add creators or prepare the next selection.",
                         "<a class='btn small' href='" + u("/selections") + "'>Prepare a selection</a>")

    # ---- start something (the three journeys)
    start = (
        "<div class='journeys'>"
        "<a class='jbtn primary' href='" + u("/selections") + "#new'><span>" + ui.icon("list", 20) + "</span><b>Quote a client</b><small>Build a selection, set prices, send the link</small></a>"
        "<a class='jbtn' href='" + u("/campaigns") + "#new'><span>" + ui.icon("flag", 20) + "</span><b>Start a campaign</b><small>From a booked selection, with goals and dates</small></a>"
        "<a class='jbtn' href='" + u("/roster") + "'><span>" + ui.icon("users", 20) + "</span><b>Add or fix creators</b><small>Profiles, photos, duplicates</small></a>"
        "<a class='jbtn' href='" + u("/analysis") + "'><span>" + ui.icon("profile", 20) + "</span><b>Import an analysis</b><small>Attach a report PDF to a creator</small></a>"
        "</div>")

    # ---- pipeline
    tot = max(1, pl["selections"] + pl["draft"] + pl["live"] + pl["ended"])
    seg = [("Selections", pl["selections"], "#b9b3a8", "/selections"), ("Draft campaigns", pl["draft"], "#e2780f", "/campaigns"),
           ("Live", pl["live"], "var(--green)", "/campaigns"), ("Ended", pl["ended"], "var(--ink)", "/campaigns")]
    stack = "<div class='stack' role='img' aria-label='Pipeline'>" + "".join(
        "<i style='width:%.1f%%;background:%s' title='%s: %d'></i>" % (n / float(tot) * 100, c, l, n) for l, n, c, _h in seg if n) + "</div>"
    legend = "<div class='pipe'>" + "".join(
        "<a href='%s'><i style='background:%s'></i><b>%d</b><span>%s</span></a>" % (u(h), c, n, l) for l, n, c, h in seg) + "</div>"

    # ---- live campaigns
    if d["live"]:
        items = ""
        for c in d["live"]:
            pct_t = int(round((c["elapsed"] or 0) * 100))
            pct_p = int(round(c["posts"] / float(c["planned"]) * 100)) if c["planned"] else 0
            items += (
                "<a class='lc' href='%s'><div><b>%s</b><span class='muted'>%s</span></div>"
                "<div class='lc-bars'><span>Time</span><span class='track'><i style='width:%d%%;background:var(--ink)'></i></span><em>%d%%</em>"
                "<span>Posts</span><span class='track'><i style='width:%d%%;background:var(--green)'></i></span><em>%d/%d</em></div></a>" % (
                    u("/campaigns/report") + "?id=%d" % c["id"], e(c["name"]), e(c["client"] or ""), pct_t, pct_t, pct_p, c["posts"], c["planned"] or c["posts"]))
        live = items
    else:
        live = ui.empty("flag", "No live campaigns", "When a campaign goes live it appears here with its progress.",
                        "<a class='btn small ghost' href='" + u("/campaigns") + "'>See campaigns</a>")

    # ---- activity
    nice = {"unlock_ok": "opened the catalogue", "view": "viewed a page", "shortlist": "shortlisted creators", "unlock_fail": "entered a wrong code",
            "request": "sent a quote request", "select": "shortlisted creators", "unlock": "opened the catalogue"}
    feed = "".join("<li><span>%s <b>%s</b></span><em>%s</em></li>" % (e(ev["label"] or "Someone"), e(nice.get(ev["kind"], ev["kind"])), ago(ev["at"]))
                   for ev in d["feed"]) or "<li class='muted'>Nothing yet.</li>"
    chart = ui.column_chart(d["series"], d["labels"], 110)
    tt = d["totals"]
    body = (
        ui.header("Home", ("%d thing%s need%s you today." % (len(q), "" if len(q) == 1 else "s", "s" if len(q) == 1 else "")) if q
                  else "All clear. Nothing is waiting for you.",
                  actions="<a class='btn lime' href='" + u("/open-catalogue") + "' target='_blank' rel='noopener'>"
                          + "Open catalogue as admin " + ui.icon("arrow", 16) + "</a>")
        + banner
        + "<div class='home-grid'><section class='card' aria-labelledby='h-needs'><div class='hd'><h2 id='h-needs'>Needs you today</h2>"
          "<span class='muted'>Most urgent first</span></div>" + needs + "</section>"
        + "<section class='card' aria-labelledby='h-start'><div class='hd'><h2 id='h-start'>Start something</h2></div>" + start + "</section></div>"
        + "<section class='card' aria-labelledby='h-pipe'><div class='hd'><h2 id='h-pipe'>Where everything stands</h2>"
          "<span class='muted'>" + str(tt["creators"]) + " active creators · " + str(tt["analysed"]) + " with a full analysis · " + str(tt["clients"]) + " live client codes</span></div>"
        + stack + legend + "</section>"
        + "<div class='home-grid even'><section class='card' aria-labelledby='h-live'><div class='hd'><h2 id='h-live'>Live campaigns</h2>"
          "<a href='" + u("/campaigns") + "'>All campaigns</a></div>" + live + "</section>"
        + "<section class='card' aria-labelledby='h-act'><div class='hd'><h2 id='h-act'>Catalogue activity</h2><span class='muted'>Last 14 days</span></div>"
        + chart + "<ul class='feed'>" + feed + "</ul></section></div>"
        + "<details class='card' id='account'><summary><b>Your account</b> <span class='muted'>· " + e(who["email"]) + " · change password</span></summary>"
          "<form method='post' action='" + u("/password") + "' style='margin-top:14px'><div class='row'>"
          "<div><label>Current password</label><input name='current' type='password' required></div>"
          "<div><label>New password</label><input name='new' type='password' required></div>"
          "</div><button class='btn'>Update password</button></form></details>"
    )
    return page("Home", body, "/")


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


def passcode_form(c, back):
    """Show and change the passcode a client types. Same form on the Access
    codes page and on a selection, both writing the one code row."""
    cid = str(c["id"])
    cur = (c["code_plain"] if "code_plain" in c.keys() else None) or ""
    return ("<form method='post' action='" + u("/codes/passcode") + "' class='row limits'>"
            "<input type='hidden' name='id' value='" + cid + "'><input type='hidden' name='back' value='" + e(back) + "'>"
            "<div style='flex:2'><label>Passcode the client types</label><input name='passcode' value='" + e(cur)
            + "' placeholder='at least 6 letters or numbers, with a number' autocomplete='off' required></div>"
            "<div style='align-self:end'><button class='btn small'>Change passcode</button></div></form>"
            "<p class='price-hint'>Changing it is instant. Selections and campaigns stay attached; "
            "anyone already inside stays inside, new visitors need the new one.</p>")


def code_manage(c, devices):
    """The panel under a code: its limits, and every device it opened on."""
    cid = str(c["id"])
    maxd = c["max_devices"] if "max_devices" in c.keys() else None
    form = (
        passcode_form(c, "/codes#code-" + cid)
        + "<form method='post' action='" + u("/codes/limits") + "' class='row limits'>"
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


def _client_tabs(current):
    return [(u("/clients"), "Clients", None, current == "clients"), (u("/codes"), "Access codes", None, current == "codes")]


def codes_page(codes, new_code=None, error=None, devices=(), message=None, lists=None):
    lists = lists or {}
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

    rows, arch_rows = [], []
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
        elif reason == "revoked":
            revoke = (
                "<form method='post' action='" + u("/codes/restore") + "' class='inline' onsubmit=\""
                + "return confirm('Restore this code? It works again at once.')\">"
                + "<input type='hidden' name='id' value='" + str(c["id"])
                + "'><button class='btn small'>Restore</button></form>"
            )
        if reason == "archived":
            revoke = (
                "<form method='post' action='" + u("/codes/unarchive") + "' class='inline'>"
                + "<input type='hidden' name='id' value='" + str(c["id"])
                + "'><button class='btn small'>Unarchive</button></form> "
                + "<form method='post' action='" + u("/codes/delete") + "' class='inline' onsubmit=\""
                + "return confirm('Delete this archived code for good? It cannot be restored.')\">"
                + "<input type='hidden' name='id' value='" + str(c["id"])
                + "'><button class='btn small danger'>Delete</button></form>"
            )
        elif not ok:
            revoke += (
                " <form method='post' action='" + u("/codes/archive") + "' class='inline' onsubmit=\""
                + "return confirm('Archive this code? It moves to the Archived list and stays off. "
                + "Selections and campaigns tied to it are not changed.')\">"
                + "<input type='hidden' name='id' value='" + str(c["id"])
                + "'><button class='btn small ghost'>Archive</button></form>"
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
        names = lists.get(c["id"], [])
        hay = " ".join([c["label"] or "", plain or "", c["hint"] or ""] + names).lower()
        listed = ("<br><span class='muted' style='font-size:12px'>" + e(", ".join(names[:3]))
                  + ("…" if len(names) > 3 else "") + "</span>") if names else ""
        (arch_rows if reason == "archived" else rows).append(
            "<tr class='code-row' data-q='" + e(hay) + "'><td><strong>" + e(c["label"]) + "</strong><br>" + shown + listed
            + "</td><td><span class='pill " + cls + "'>" + e(reason) + "</span></td>"
            + "<td>" + devs + "</td>"
            + "<td>" + used + "</td><td class='muted'>" + ts(c["expires_at"]) + "</td>"
            + "<td class='muted'>" + ago(c["last_used"]) + "</td>"
            + "<td class='right'>" + revoke + "</td></tr>"
            + "<tr class='manage-row' data-for='" + e(hay) + "'><td colspan='7'>" + manage + "</td></tr>"
        )
    body_rows = "".join(rows) or ("<tr><td colspan='7'>" + ui.empty("key", "No access codes yet", "Create one above. A client needs a code to open the catalogue.") + "</td></tr>")

    arch_html = ""
    if arch_rows:
        arch_html = ("<details class='card' id='archived-codes'><summary class='hd'><h2>Archived</h2>"
                     "<span class='muted'>" + str(len(arch_rows) // 2) + "</span></summary>"
                     "<p class='sec-desc'>Put away and switched off. Unarchive to bring one back, "
                     "or delete it for good once nothing is tied to it.</p>"
                     "<table><tbody>" + "".join(arch_rows) + "</tbody></table></details>")
    live_n = sum(1 for c in codes if code_state(c)[0])
    body = (
        ui.header("Access codes", "One passcode per client. It opens the catalogue and only that client's selections and campaigns. "
                  "Expiry and revoking work immediately.", crumbs=None,
                  actions="<a class='btn lime' href='#new-code'>" + ui.icon("plus", 16) + " New code</a>", tabs=_client_tabs("codes"))
        + banner
        + "<details class='card' id='new-code'" + ("" if codes else " open") + "><summary class='hd'><h2>Create a code</h2>"
          "<span class='muted'>" + str(live_n) + " live of " + str(len(codes) - len(arch_rows) // 2) + "</span></summary>"
          "<p class='sec-desc'>Give it to the client. They type it once on the catalogue and it remembers their device.</p>"
        + "<form method='post' action='" + u("/codes/new") + "'><div class='row'>"
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
        + "</div><button class='btn lime'>Create code</button></form></details>"
        + "<div class='card'><input id='code-search' type='search' autocomplete='off' "
          "placeholder='Search by company, list name or passcode' style='width:100%;margin-bottom:12px'>"
          "<p id='code-none' class='muted' style='display:none'>No code matches.</p>"
          "<table><thead><tr><th>Code</th><th>State</th><th>Devices</th><th>Uses</th>"
        + "<th>Expires</th><th>Last used</th><th></th></tr></thead><tbody>"
        + body_rows + "</tbody></table></div>" + arch_html
        + "<script>(function(){var i=document.getElementById('code-search');if(!i)return;"
          "i.addEventListener('input',function(){var q=i.value.trim().toLowerCase(),n=0;"
          "document.querySelectorAll('tr.code-row,tr.manage-row').forEach(function(r){"
          "var h=r.getAttribute('data-q')||r.getAttribute('data-for')||'';"
          "var on=!q||h.indexOf(q)>-1;r.style.display=on?'':'none';if(on&&q&&r.closest('#archived-codes'))r.closest('#archived-codes').open=true;"
          "if(on&&r.classList.contains('code-row'))n++;});"
          "document.getElementById('code-none').style.display=(q&&!n)?'':'none';});})();</script>"
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

    panels = {
        "overview": (
            "<div class='grid'>" + cards + "</div>"
            "<div class='card'><div class='hd'><h2>Activity</h2><span class='muted'>Opens, shortlists and quote requests per day</span></div>"
            "<div class='legend'><span><i style='background:#121212'></i>Opens</span>"
            "<span><i style='background:#b9d400'></i>Creators shortlisted</span>"
            "<span><i style='background:#ff691e;border-radius:999px'></i>Quote request</span></div>"
            + activity_chart(s["by_day"]) + "</div>"
            "<div class='card'><div class='hd'><h2>How far each code got</h2><span class='muted'>From opening the catalogue to asking for a quote</span></div>"
            + funnel(s) + "</div>"),
        "clients": (
            "<div class='card'><div class='hd'><h2>By client</h2><span class='muted'>Who is using their code, and how much</span></div>"
            "<table><thead><tr><th>Code</th><th>State</th><th>Opens</th><th>Shortlisted</th><th>Asked for a quote</th>"
            "<th class='right'>Last open</th></tr></thead><tbody>" + by_code + "</tbody></table></div>"),
        "creators": (
            "<div class='split'><div class='card'><div class='hd'><h2>What clients shortlist</h2></div>"
            "<p class='sec-desc'>The tiers and platforms clients pick most.</p>"
            "<p class='muted' style='font-size:13px;margin:0 0 6px'>By tier</p>" + rank(s["by_tier"])
            + "<p class='muted' style='font-size:13px;margin:16px 0 6px'>By platform</p>" + rank(s["by_platform"], "#b9d400") + "</div>"
            "<div class='card'><div class='hd'><h2>Most shortlisted creators</h2></div><table><thead><tr>"
            "<th></th><th>Creator</th><th></th><th class='right'>Times</th></tr></thead><tbody>" + top + "</tbody></table></div></div>"),
        "security": (
            "<div class='card'><div class='hd'><h2>Why codes were refused</h2><span class='muted'>Wrong, expired or full codes</span></div>"
            + rank(s["fail_reasons"], "#ee1515") + "</div>"
            "<div class='card'><div class='hd'><h2>Event log</h2><span class='muted'>Everything recorded in this period</span></div>"
            "<table><thead><tr><th>Event</th><th>Code</th><th>Detail</th><th>IP</th><th class='right'>When</th></tr></thead><tbody>"
            + log + "</tbody></table></div>"),
    }
    body = (
        ui.header("Analytics", "How clients use the catalogue: who opens it, what they shortlist, and where they stop. "
                  + e(pretty_day(s["start"])) + " – " + e(pretty_day(s["end"] - 86400)) + ".")
        + picker
        + ui.tabset("an", [("overview", "Overview", None), ("clients", "Clients", None), ("creators", "Creators", None),
                           ("security", "Refused & log", None)], panels)
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
        + "</form>" + delete_after + analysis_box(c)
    )


def analysis_box(c):
    """On a creator's edit form: their profile analysis — download a template
    already carrying their code, fill it, upload it back."""
    if c is None:
        return ""
    code = e(c["code"])
    return ("<div class='card' style='margin-top:12px;background:#f7f5f2'><label>Profile analysis</label>"
            "<p class='price-hint' style='margin:4px 0 10px'>The full analysis a client opens from this creator's "
            "card. Download the template (it already has " + code + " in it), fill what you have, and upload it. "
            "Every field is listed in Server Access/Catalogue Portal/CREATOR-ANALYSIS-PARAMETERS.md.</p>"
            "<div class='row' style='align-items:end'>"
            "<div><a class='btn small ghost' href='" + u("/analysis/template.xlsx") + "?code=" + code + "'>"
            "Download template for " + code + "</a></div>"
            "<form method='post' action='" + u("/analysis/upload") + "' enctype='multipart/form-data' "
            "class='row' style='align-items:end;margin:0'>"
            "<div><input type='file' name='file' accept='.xlsx' required></div>"
            "<div><button class='btn small'>Upload analysis</button></div></form>"
            "<div><a class='btn small ghost' href='" + u("/analysis") + "?q=" + code + "#edit'>Open the analysis</a></div>"
            "</div></div>")


def date_carry(dates):
    """The date-added filter, as hidden fields, so a save or delete returns
    to the same filtered view."""
    out = ""
    for name, value in zip(("from", "to"), dates or ("", "")):
        if value:
            out += "<input type='hidden' name='" + name + "' value='" + e(value) + "'>"
    return out


def duplicate_group_card(group):
    """One set of creators that look like the same person, with a Combine button
    on each: choosing one combines the others into it."""
    members = ""
    for c in group:
        others = [x["code"] for x in group if x["code"] != c["code"]]
        members += (
            "<div class='dup'><div class='dup-who'>"
            + ("<img class='tface' src='" + e(links.thumb(c["photo"])) + "' alt=''>" if c["photo"] else "<span class='tface none'>—</span>")
            + "<div><b>" + e(c["name"]) + "</b><br><code>" + e(c["code"]) + "</code> <span class='muted'>" + e(c["tier"] or "") + " · "
            + num(c["followers"]) + " followers · " + e(c["platform"] or "") + "</span></div></div>"
            "<form method='post' action='" + u("/roster/merge") + "' data-confirm='Combine the records into " + e(c["code"]) + "? Both are kept as one creator, nothing is lost.'>"
            "<input type='hidden' name='keep' value='" + e(c["code"]) + "'>"
            + "".join("<input type='hidden' name='drop' value='" + e(o) + "'>" for o in others)
            + "<button class='btn small lime'>" + ui.icon("merge", 15) + " Combine into this one</button></form></div>")
    return "<div class='card dups'>" + members + "</div>"


def roster_page(creators, error=None, message=None, cities=None, tiers=None,
                nationalities=None, interests=None, editing=None, q="",
                bands=None, page_no=1, pages=1, total=None, per_page=100,
                dates=("", ""), tab=None, dupes=None):
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
        lo, hi = lo or hi, hi or lo
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

    all_panel = (
        "<form class='rsearch' method='get' action='" + u("/roster") + "'>"
        "<input name='q' value='" + e(q) + "' placeholder='Search name, code, handle or city' autocomplete='off' aria-label='Search creators'>"
        "<label class='added'>Added from<input type='date' name='from' value='" + e(d_from) + "'></label>"
        "<label class='added'>to<input type='date' name='to' value='" + e(d_to) + "'></label>"
        "<button class='btn small'>Search</button>"
        + ("<a class='btn small ghost' href='" + u("/roster") + "'>Clear</a>" if filtered else "")
        + "<span class='muted' style='font-size:13px'>" + e(shown) + "</span>"
        "<a class='btn small ghost' style='margin-left:auto' href='" + u("/roster/export") + "'>" + ui.icon("download", 15) + " Export .csv</a></form>"
        + "<div class='card'><table><thead><tr><th></th><th>Code</th>"
        + "<th>Name</th><th>Platform</th><th>Followers</th><th>Tier</th><th>City</th>"
        + "<th></th></tr></thead><tbody>" + rows + "</tbody></table></div>" + pager)

    add_panel = (
        "<div class='card'><div class='hd'><h2>Add a creator</h2></div>"
        "<p class='sec-desc'>Paste their profile links and the followers fill the tier. Hidden creators stay in the database but never reach a client.</p>"
        + creator_form(None, cities, tier_names, interests, q, 1, price_bands, dates) + "</div>")

    import_panel = (
        "<div class='split'>"
        "<div class='card'><div class='hd'><h2>Import a spreadsheet</h2></div>"
        "<p class='sec-desc'>Add or update many creators at once.</p>"
        "<ul class='tick-list'><li>Start from the template so the headings match.</li>"
        "<li>A blank code is assigned for you; a code that already exists is updated, not duplicated.</li>"
        "<li><b>Nothing is saved unless every row is valid.</b> Wrong rows are named so you can fix them.</li></ul>"
        "<div style='display:flex;gap:8px;flex-wrap:wrap;margin:14px 0'>"
        "<a class='btn ghost small' href='" + u("/roster/template.xlsx") + "'>" + ui.icon("download", 15) + " Template (.xlsx, takes photos)</a>"
        "<a class='btn ghost small' href='" + u("/roster/template") + "'>CSV only</a></div>"
        "<form method='post' action='" + u("/roster/import") + "' enctype='multipart/form-data'>"
        "<label for='sheet'>Spreadsheet (.csv or .xlsx)</label><input id='sheet' type='file' name='sheet' accept='.csv,.xlsx,.xlsm,text/csv' required>"
        "<button class='btn lime' style='margin-top:12px'>" + ui.icon("upload", 16) + " Import</button></form>"
        "<details style='margin-top:14px'><summary class='muted'>Can photos travel with the sheet?</summary>"
        "<p class='price-hint'>Only in an .xlsx: insert each picture on its row in the <code>photo</code> column. A CSV cannot carry images. "
        "If the creators already exist, <b>Attach photos in bulk</b> is far quicker.</p></details></div>"
        "<div class='card'><div class='hd'><h2>Attach photos in bulk</h2></div>"
        "<p class='sec-desc'>Select a folder of images at once. Each file is matched to a creator by its filename.</p>"
        "<ul class='tick-list'><li>The person's name: <code>Noha Magdy.jpg</code></li><li>Their handle: <code>noha.mgdi.jpg</code></li>"
        "<li>Their code: <code>HV-MC-001.jpg</code></li></ul>"
        "<p class='price-hint'>Spaces, dashes and underscores count the same, and a browser's <code>(1)</code> is ignored. Files that match nothing are listed back, "
        "never dropped. A photo already on file is replaced.</p>"
        "<form method='post' action='" + u("/roster/photos") + "' enctype='multipart/form-data'>"
        "<label for='photos'>Images (select many)</label><input id='photos' type='file' name='photos' accept='image/*' multiple required>"
        "<button class='btn lime' style='margin-top:12px'>" + ui.icon("image", 16) + " Attach photos</button></form></div></div>")

    dupes = dupes or []
    if dupes:
        dgroups = "".join(duplicate_group_card(g) for g in dupes)
        dup_panel = ("<p class='sec-desc'>These creators share a profile link or handle, so they are probably one person. "
                     "They are combined into one creator, not thrown away: pick the record whose code stays, and every platform, profile link, analysis, "
                     "selection and campaign from the other is added to it (where both have an analysis for the same platform, the newer is kept). "
                     "Every merge can be undone from History.</p>" + dgroups)
    else:
        dup_panel = ui.empty("check", "No duplicates found", "Creators are checked by profile link and handle. Nothing looks doubled.")

    panels = {"all": all_panel, "add": add_panel, "import": import_panel,
              "tiers": tiers_section(tiers, used), "dupes": dup_panel}
    first = tab if tab in panels else "all"
    body = (
        suggestions
        + reach_script(bands or [], [t["name"] for t in tiers if not t["auto"]])
        + ui.header("Creators", "Everyone clients can pick from. Hidden creators stay in the database but never reach a client.",
                    actions="<a class='btn lime' href='#rt=add' data-go-tab='rt:add'>" + ui.icon("plus", 16) + " Add a creator</a>")
        + err
        + ui.tabset("rt", [("all", "Everyone", len(creators) if not filtered else None), ("add", "Add a creator", None),
                           ("import", "Import", None), ("tiers", "Tiers & pricing", None),
                           ("dupes", "Duplicates", len(dupes) if dupes else None)], panels, first=first)
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

    n_open = sum(1 for r in requests if not r["handled_at"])
    body = (
        ui.header("Quote requests", "A client picked creators in the catalogue and asked for a price. Each request shows the client's details and "
                  "every creator they chose, exactly as they saw them. Price it as a selection, then mark it handled.")
        + ("<div class='card'>" + ui.empty("inbox", "No requests yet", "When a client sends a shortlist from the catalogue it lands here.") + "</div>"
           if not requests else
           "<div class='stat-row'><div class='stat'><b>" + str(n_open) + "</b><span>Waiting for you</span></div>"
           "<div class='stat'><b>" + str(len(requests) - n_open) + "</b><span>Handled</span></div>"
           "<div class='stat'><b>" + str(len(requests)) + "</b><span>Total</span></div></div>" + body_cards)
    )
    return page("Quote requests", body, "/requests")


# ------------------------------------------------------------ selections --

def _money(lo, hi):
    if lo is None:
        return "—"
    return (format(lo, ",") if lo == hi else format(lo, ",") + " – " + format(hi, ",")) + " SAR"


def selection_link(sel, origin):
    """What the client is sent: just the token, about 40 characters. The page
    reads the name, creators and prices from the server by it. Older long links
    (#n=…&c=…&s=…) keep working."""
    return origin + "/selection/#s=" + sel["token"]


def selections_page(sels, error=None, message=None, origin="", archived=False, n_archived=0, page_no=1, total=0,
                    clients=None, currencies=None, camp_counts=None, interests=()):
    listed = total
    note = ""
    if error:
        note += "<div class='err'>" + e(error) + "</div>"
    if message:
        note += "<div class='ok'>" + e(message) + "</div>"
    rows = []
    camp_counts = camp_counts or {}
    for x in sels:
        n = len(json.loads(x["codes"] or "[]"))
        priced = bool(json.loads(x["prices"] or "{}")) or x["total_from"] is not None
        in_camp = camp_counts.get(x["id"], 0)
        total = _money(x["total_from"], x["total_to"]) if x["total_from"] is not None else "sum of creators"
        steps = [("Creators", n > 0), ("Prices", priced), ("Campaign", in_camp > 0)]
        prog = "<div class='mini-steps'>" + "".join(
            "<span class='%s' title='%s'>%s</span>" % ("on" if ok_ else "", lbl, ui.icon("check", 12) if ok_ else "") for lbl, ok_ in steps) + "</div>"
        nxt = ("Add creators" if not n else "Set prices" if not priced else "Start a campaign" if not in_camp else "In a campaign")
        client = ("<span class='pill own'>" + e(x["code_label"]) + "</span>" if ("code_label" in x.keys() and x["code_label"])
                  else "<span class='pill warn'>No client</span>")
        rows.append(
            "<tr><td><strong><a href='" + u("/selections/edit") + "?id=" + str(x["id"]) + "'>"
            + e(x["name"]) + "</a></strong>"
            + "</td><td>" + client + "</td><td>" + prog + "<span class='muted' style='font-size:12.5px'>Next: " + nxt + "</span></td><td>" + str(n)
            + "</td><td>" + total + "</td><td class='muted'>" + ago(x["updated_at"])
            + "</td><td class='right nowrap'><a class='btn small' href='" + u("/selections/edit") + "?id="
            + str(x["id"]) + "'>Open</a> " + archive_button("selection", x["id"], archived)
            + "<form method='post' action='" + u("/selections/delete") + "' class='inline' data-confirm=\"Delete "
            + e((x["name"] or "this selection").replace("'", "’")) + "? Its link stops working. You can restore it from History.\">"
            "<input type='hidden' name='id' value='" + str(x["id"]) + "'><button class='btn small danger'>Delete</button></form>"
            "</td></tr>")
    table = "".join(rows) or ("<tr><td colspan='6'>" + ui.empty("list", "No selections yet", "A selection appears here when a client shortlists creators on the catalogue, "
                              "or build one yourself.", "<a class='btn small lime' href='#new'>New selection</a>") + "</td></tr>")
    code_opts = "<option value=''>No client yet</option>" + "".join(
        "<option value='%d'>%s</option>" % (c["id"], e(c["label"])) for c in (clients or []))
    import fit as _fit_ns
    plat_opts = "<option value=''>Every platform they are on</option>" + "".join("<option value='%s'>%s only</option>" % (p_, p_) for p_ in PLATFORMS)
    cur_opts = "".join("<option>%s</option>" % c_ for c_ in (currencies or ["SAR"]))
    create = (
        "<details class='card' id='new'" + ("" if sels else " open") + "><summary class='hd'><h2>New selection</h2><span class='muted'>Build one, or open a client's</span></summary>"
        "<p class='sec-desc'>A selection is a priced shortlist for one client. Name it, choose the client, then add creators and prices.</p>"
        "<form method='post' action='" + u("/selections/new") + "'><input type='hidden' name='mode' value='scratch'><div class='row'>"
        "<div style='flex:2'><label for='ns-name'>Selection name (the client sees this)</label><input id='ns-name' name='name' required placeholder='e.g. Penduline: Mothers, Instagram'></div>"
        "<div><label for='ns-client'>Client</label><select id='ns-client' name='code_id'>" + code_opts + "</select></div>"
        "<div><label for='ns-plat'>Quoted for</label><select id='ns-plat' name='platform'>" + plat_opts + "</select></div>"
        "<div><label for='ns-cur'>Currency</label><select id='ns-cur' name='currency'>" + cur_opts + "</select></div></div>"
        "<div class='card' style='background:#f7f5f0;margin:14px 0'><strong>Who is this selection for?</strong>"
        "<div class='price-hint' style='margin:4px 0 8px'>Every creator gets a matching score against this, worked out from their analysis. You can change it any time on the selection's <b>Fit &amp; tags</b> tab.</div>"
        "<div class='row'><div><label for='ns-obj'>Campaign objective</label><select id='ns-obj' name='sel_objective'>" + "".join(
            "<option" + (" selected" if o_ == "Balanced" else "") + ">" + o_ + "</option>" for o_ in _fit_ns.OBJECTIVES) + "</select></div>"
        "<div><label for='ns-country'>Target country</label><select id='ns-country' name='t_country'>" + "".join(
            "<option value='" + k_ + "'>" + e(n_) + "</option>" for k_, n_ in _fit_ns.COUNTRIES) + "</select></div>"
        "<div><label for='ns-gender'>Audience gender</label><select id='ns-gender' name='t_gender'>" + "".join(
            "<option>" + g_ + "</option>" for g_ in _fit_ns.GENDERS) + "</select></div>"
        "<div><label for='ns-age'>Audience age</label><select id='ns-age' name='t_age'><option>Any</option>" + "".join(
            "<option>" + a_ + "</option>" for a_ in _fit_ns.AGE_BANDS) + "</select></div>"
        "<div style='flex:3'><label>Product categories (tick all that apply)</label><div class='vd-roles'>" + "".join(
            "<label class='tick'><input type='checkbox' name='t_category' value=\"" + e(i_) + "\"> <span>" + e(i_) + "</span></label>"
            for i_ in interests) + "</div></div></div></div>"
        "<button class='btn lime'>" + ui.icon("arrow", 16) + " Create and add creators</button></form>"
        "<details style='margin-top:16px'><summary class='muted'>Have a link a client sent? Open that selection instead</summary>"
        "<form method='post' action='" + u("/selections/new") + "' style='margin-top:10px'><div class='row'>"
        "<div style='flex:3'><label>Selection link</label><input name='link' required placeholder='https://influencer-catalogue.hellovoice.co.uk/selection/#n=…'></div>"
        "<div style='align-self:end'><button class='btn small'>Open it</button></div></div>"
        "<p class='price-hint'>A selection a client sent as a quote request is priced from <a href='" + u("/requests") + "'>Quote requests</a>.</p></form></details></details>")
    body = (
        ui.header("Selections", "A selection is a priced shortlist of creators for one client. Clients create them on the catalogue and they appear here by themselves; "
                  "you set the prices and the client's own link shows them at once.",
                  actions="<a class='btn lime' href='#new'>" + ui.icon("plus", 16) + " New selection</a>")
        + note + create
        + archive_tabs("/selections", archived, n_archived, "Selections")
        + "<div class='card'><table><thead><tr><th>Selection</th><th>Client</th><th>Progress</th><th>Creators</th><th>Total</th>"
        + "<th>Updated</th><th></th></tr></thead><tbody>" + table + "</tbody></table></div>"
        + pager(listed, page_no, "/selections", archived=("1" if archived else ""))
    )
    return page("Selections", body, "/selections")


def _live_score(live):
    """The matching score as the client sees it, with the reasons behind it."""
    if not live:
        return ""
    if live.get("score") is None:
        return "<div class='vd-live off'><span class='vd-stamp none'>—</span><div><b>Not scored yet</b><div class='muted'>" + e(live.get("note") or "") + "</div></div></div>"
    band = "g" if live["score"] >= 80 else "l" if live["score"] >= 60 else "a" if live["score"] >= 40 else "r"
    li = lambda items, cls: "".join("<li class='" + cls + "'>" + e(x) + "</li>" for x in items)
    return ("<div class='vd-live'><span class='vd-stamp " + band + "'>" + str(live["score"]) + "</span><div><b>" + e(live["tag"]) + "</b>"
            "<span class='muted'> · live, for " + e(live["objective"].lower()) + (" on " + e(live["platform"]) if live.get("platform") else "") + "</span>"
            "<ul class='vd-why'>" + li(live["strengths"], "g1") + li(live["watchouts"], "g-1") + "</ul></div></div>")


def _fit_card(code, c, shot, v, tags, fit_mod, client_tags=(), live=None):
    """One creator on the Fit & tags tab: who they are on the left, then the
    fit, the roles, the reason the client reads, and their tags, with room to type."""
    fits = "<option value=''>— no verdict —</option>" + "".join(
        "<option" + (" selected" if v.get("fit") == f else "") + ">" + e(f) + "</option>" for f in fit_mod.FITS)
    roles = v.get("roles") or []
    ticks = "".join("<label class='vd-role'><input type='checkbox' value=\"" + e(r) + "\"" + (" checked" if r in roles else "")
                    + "> <span>" + e(r) + "</span></label>" for r in fit_mod.ROLES)
    return ("<div class='vd-item'><input type='hidden' name='vcode' value=\"" + e(code) + "\">"
            "<div class='vd-who'>" + shot + "<div><b>" + e(c["name"]) + "</b><div class='muted'><code>" + e(code) + "</code> · " + e(c["tier"] or "") + "</div>"
            + _live_score(live)
            + "<button type='button' class='btn tiny ghost vd-suggest'>Copy into the fields →</button><div class='muted vd-note'></div></div></div>"
            "<div class='vd-main'>"
            "<div class='vd-line'><div><label>Fit</label><select name='fit' class='vd-fit'>" + fits + "</select></div>"
            "<div><label>Role in the campaign</label><div class='vd-roles'>" + ticks + "</div></div></div>"
            "<input type='hidden' name='roles' class='vd-roles-in' value=\"" + e(",".join(roles)) + "\">"
            "<label>Why — the client reads this</label>"
            "<input name='reason' class='vd-reason' value=\"" + e(v.get("reason") or "") + "\" maxlength='160' "
            "placeholder='e.g. Strong engagement and a mostly Saudi audience' autocomplete='off'>"
            "<label>Tags</label>"
            "<input name='tags' class='tag-in' value=\"" + e(", ".join(tags)) + "\" placeholder='e.g. Hero, Beauty — separate with commas' maxlength='200' autocomplete='off'>"
            + ("<div class='muted' style='margin-top:8px'>Added by the client: "
               + " ".join("<span class='pill'>" + e(t) + "</span>" for t in client_tags) + "</div>" if client_tags else "")
            + "</div></div>")


VERDICT_JS = r'''<style>
.vd-bar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:6px 0 10px}
.vd-list{display:grid;gap:14px;margin-top:12px}
.vd-item{display:grid;grid-template-columns:minmax(200px,260px) 1fr;gap:20px;padding:16px;border:1px solid var(--line,#e6e1d6);border-radius:14px;background:#fff}
.vd-who{display:flex;gap:12px;align-items:flex-start}.vd-who .btn{margin-top:8px}
.vd-main label{display:block;margin:10px 0 4px;font-size:13px;font-weight:600}
.vd-main select,.vd-main input[type=text],.vd-main input:not([type]){width:100%}
.vd-line{display:grid;grid-template-columns:minmax(180px,240px) 1fr;gap:16px;align-items:start}
.vd-line label{margin-top:0}
.vd-roles{display:flex;flex-wrap:wrap;gap:8px}
.vd-role{display:inline-flex!important;align-items:center;gap:6px;margin:0!important;padding:7px 14px;border:1px solid var(--line-strong,#cfc8b8);border-radius:999px;cursor:pointer;font-size:13px!important;font-weight:600}
.vd-role:has(input:checked){background:var(--ink,#121212);color:#e8ff76;border-color:var(--ink,#121212)}
.vd-role input{margin:0}
.vd-note{font-size:12px;margin-top:6px}
.vd-why{list-style:none;margin:8px 0 0;padding:0;font-size:12px;display:grid;gap:3px}
.vd-why li{padding:3px 8px;border-radius:8px;background:#f3f1eb}
.vd-why li.g1{background:#e7f7ed}.vd-why li.g-1{background:#fdeaea}
.vd-live{display:flex;gap:10px;align-items:flex-start;margin-top:10px;padding:10px;border-radius:12px;background:#f7f5f0}
.vd-stamp{flex:none;width:44px;height:44px;border-radius:50%;display:grid;place-items:center;font-weight:800;font-size:16px;color:#fff;background:#14884a}
.vd-stamp.l{background:#8a9a00;color:#fff}.vd-stamp.a{background:#d99a00}.vd-stamp.r{background:#d02424}.vd-stamp.none{background:#cfc8b8}
@media (max-width:1200px){.vd-line{grid-template-columns:1fr}}
@media (max-width:900px){.vd-item{grid-template-columns:1fr}}
</style>
<script>(function(){var base=%BASE%;
function row(el){return el.closest('.vd-item')}
function syncRoles(tr){var v=[].slice.call(tr.querySelectorAll('.vd-role input:checked')).map(function(i){return i.value});tr.querySelector('.vd-roles-in').value=v.join(',')}
document.addEventListener('change',function(e){var tr=e.target.closest&&e.target.closest('.vd-item');if(tr&&e.target.closest('.vd-role'))syncRoles(tr)});
function suggest(tr,done){var code=tr.querySelector('input[name=vcode]').value;var p=document.querySelector('select[name=platform]');p=p?p.value:'';var o=document.getElementById('vd-obj');o=o?o.value:'';function tv(i){var x=document.getElementById(i);return x?x.value:''}
 var note=tr.querySelector('.vd-note');note.textContent='Reading the analysis…';
 fetch(base+'/selections/suggest?code='+encodeURIComponent(code)+'&p='+encodeURIComponent(p)+'&o='+encodeURIComponent(o)+'&tc='+encodeURIComponent(tv('t-country'))+'&tg='+encodeURIComponent(tv('t-gender'))+'&ta='+encodeURIComponent(tv('t-age'))+'&tk='+encodeURIComponent([].slice.call(document.querySelectorAll('input[name=t_category]:checked')).map(function(i){return i.value}).join('|')),{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(d){
  if(d.fit!==undefined){var sel=tr.querySelector('.vd-fit');if(d.fit)sel.value=d.fit;
   tr.querySelectorAll('.vd-role input').forEach(function(i){i.checked=(d.roles||[]).indexOf(i.value)>=0});syncRoles(tr);
   if(d.reason)tr.querySelector('.vd-reason').value=d.reason}
  note.textContent=d.note||('Suggested for '+d.objective+' from the '+d.platform+' analysis — check it, then Save changes.');
  var old=tr.querySelector('.vd-why');if(old)old.remove();
  if(d.checks&&d.checks.length){var ul=document.createElement('ul');ul.className='vd-why';
   d.checks.forEach(function(c){var li=document.createElement('li');li.className='g'+c.grade;li.textContent=c.label+': '+c.value+'  ('+c.bench+')';ul.appendChild(li)});
   tr.querySelector('.vd-who > div').appendChild(ul)}
  if(done)done()}).catch(function(){note.textContent='Could not suggest.';if(done)done()})}
document.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('.vd-suggest');if(b){suggest(row(b))}});
var all=document.getElementById('vd-all');if(all)all.onclick=function(){var rows=[].slice.call(document.querySelectorAll('.vd-item'));
 var i=0;(function next(){if(i>=rows.length)return;suggest(rows[i++],next)})()}})();</script>'''.replace("%BASE%", """document.querySelector("form[action$='/selections/save']").getAttribute("action").replace(/\/selections\/save$/,"")""")


TAG_JS = r'''<script>(function(){var pool=document.getElementById('tag-pool');if(!pool)return;var last=null;
function esc(t){return String(t).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function all(){var s={};document.querySelectorAll('.tag-in').forEach(function(i){i.value.split(/[,;]+/).forEach(function(t){t=t.trim();if(t)s[t.toLowerCase()]=t})});return Object.keys(s).map(function(k){return s[k]}).sort()}
function draw(){var t=all();pool.innerHTML=t.length?'Tags in use: '+t.map(function(x){return '<a href="#" class="pill" data-t="'+esc(x)+'">'+esc(x)+'</a>'}).join(' '):'No tags yet — type some in a Tags box.'}
document.addEventListener('focusin',function(e){if(e.target.classList&&e.target.classList.contains('tag-in'))last=e.target});
document.addEventListener('input',function(e){if(e.target.classList&&e.target.classList.contains('tag-in'))draw()});
pool.addEventListener('click',function(e){var a=e.target.closest('a[data-t]');if(!a)return;e.preventDefault();if(!last)return;
var cur=last.value.split(/[,;]+/).map(function(x){return x.trim()}).filter(Boolean);var t=a.dataset.t;
if(cur.map(function(x){return x.toLowerCase()}).indexOf(t.toLowerCase())<0)cur.push(t);last.value=cur.join(', ');draw()});
draw()})();</script>'''


def selection_edit_page(sel, creators, bands, origin, error=None, message=None, campaigns=(), scores=None, interests=()):
    by = {c["code"]: c for c in creators}
    codes = json.loads(sel["codes"] or "[]")
    own = json.loads(sel["prices"] or "{}")
    keys = sel.keys()
    import fx
    usable = fx.rates()
    cur = (sel["currency"] if "currency" in keys else None) or "SAR"
    cur = cur if cur in usable else "SAR"
    conv = lambda v: fx.from_sar(v, cur)
    rate_c = float(usable.get(cur, 1.0)) if cur != "SAR" else 1.0
    step_c = {"USD": 5, "EGP": 50}.get(cur, 10)
    money_c = lambda lo, hi: "—" if lo is None else (
        (format(conv(lo), ",") if lo == hi else format(conv(lo), ",") + " – " + format(conv(hi), ",")) + " " + cur)
    costs = json.loads((sel["costs"] if "costs" in keys else None) or "{}")
    tags_of = json.loads((sel["tags"] if "tags" in keys else None) or "{}")
    verdicts_of = json.loads((sel["verdicts"] if "verdicts" in keys else None) or "{}")
    client_tags_of = json.loads((sel["client_tags"] if "client_tags" in keys else None) or "{}")
    import fit as _fit
    try:
        target_now = dict(_fit.DEFAULT_TARGET, **{k: v for k, v in json.loads((sel["target"] if "target" in keys else None) or "{}").items() if v})
    except ValueError:
        target_now = dict(_fit.DEFAULT_TARGET)
    import db as _db2
    obj_now = (sel["objective"] if "objective" in keys else None) or _fit.FROM_CAMPAIGN.get(_db2.selection_campaign_objective(sel["id"]) or "", "Balanced")
    margin = sel["margin"] if "margin" in keys else None
    margin_txt = "" if margin is None else ("%g" % margin)
    mmax = sel["margin_max"] if "margin_max" in keys else None
    margin_max_txt = "" if mmax is None else ("%g" % mmax)
    note = ""
    if error:
        note += "<div class='err'>" + e(error) + "</div>"
    if message:
        note += "<div class='ok'>" + e(message) + "</div>"

    lo_sum = hi_sum = 0
    rows = []
    fit_cards_l = []
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
        fit_cards_l.append(_fit_card(code, c, shot, verdicts_of.get(code) or {}, tags_of.get(code) or [], _fit, client_tags_of.get(code) or [], (scores or {}).get(code)))
        val = lambda i: format(conv(set_[i]), ",") if set_ else ""
        # The cost this selection was priced from, else the creator's last
        # known cost — a starting point the admin can change.
        cost = costs.get(code)
        if cost is None and "cost" in c.keys():
            cost = c["cost"]
        # Costs are kept in SAR but shown and typed in the selection's currency,
        # so the whole page speaks one currency.
        cost_txt = format(int(round(cost * rate_c)), ",") if cost is not None else ""
        rows.append(
            "<tr><td>" + shot + "</td><td><code>" + e(code) + "</code><br>" + roster_link(code, c["name"])
            + ("" if c["active"] else " <span class='pill dead'>hidden</span>")
            + "<input type='hidden' name='code' value='" + e(code) + "'></td>"
            + "<td>" + e(c["tier"]) + "<br><span class='muted'>" + num(c["followers"]) + "</span>"
            + "".join("<div class='acct'>" + e(a["platform"] or "") + " " + num(a["followers"])
                      + " · " + e(a["tier"] or "—") + "</div>"
                      for a in db_account_tiers(c) if a["followers"]) + "</td>"
            + "<td class='muted'>" + (money_c(*default) if default[0] is not None else "—")
        )
        rows[-1] += (
            "</td><td><input name='cost' value='" + cost_txt + "' placeholder='cost' inputmode='numeric'>"
            + "<div class='profit'></div></td>"
            + "<td><input name='p_from' value='" + val(0) + "' placeholder='from' inputmode='numeric'"
              + (" data-def='%d|%d'" % (default[0], default[1]) if default and default[0] is not None else "") + "></td>"
            + "<td><input name='p_to' value='" + val(1) + "' placeholder='to' inputmode='numeric'></td>"
            + "<td><label class='tick' title='Also save this price as the creator&#39;s price on the roster, so every later selection starts from it'>"
              "<input type='checkbox' name='default' value='" + e(code) + "'> make default</label>"
            + ("<div class='muted' style='font-size:12px'>roster now: " + money_c(c["price_from"], c["price_to"] or c["price_from"]) + "</div>"
               if ("price_from" in c.keys() and c["price_from"]) else "<div class='muted' style='font-size:12px'>roster: tier price</div>") + "</td>"
            + ""
            + "<td><label class='tick'><input type='checkbox' name='drop' value='" + e(code) + "'> remove</label></td></tr>")
    table = "".join(rows) or "<tr><td colspan='8' class='muted'>No creators yet — add some below.</td></tr>"
    fit_cards = "".join(fit_cards_l) or "<p class='muted'>No creators yet — add some on the Creators &amp; prices tab.</p>"
    missing = [c for c in codes if c not in by]
    link = selection_link(sel, origin)
    tf = "" if sel["total_from"] is None else format(conv(sel["total_from"]), ",")
    tt = "" if sel["total_to"] is None else format(conv(sel["total_to"]), ",")
    n_cr = len([c for c in codes if c in by])
    has_prices = bool(own) or sel["total_from"] is not None
    st_done = [n_cr > 0, has_prices, bool(sel["code_id"]) and n_cr > 0 and has_prices, bool(campaigns)]
    first_open = next((i for i, d_ in enumerate(st_done) if not d_), 3)
    stepper_html = ui.stepper([("Add creators", "done" if st_done[0] else ("now" if first_open == 0 else "todo")),
                               ("Set prices", "done" if st_done[1] else ("now" if first_open == 1 else "todo")),
                               ("Share with the client", "done" if st_done[2] else ("now" if first_open == 2 else "todo")),
                               ("Start a campaign", "done" if st_done[3] else ("now" if first_open == 3 else "todo"))])
    roster_list = "<datalist id='roster-list'>" + "".join(
        "<option value=\"%s (%s)\">" % (e(c["name"]), e(c["code"])) for c in creators if c["active"]) + "</datalist>"
    client_pill = ("<span class='pill own'>" + e(sel["code_label"]) + "</span>" if ("code_label" in sel.keys() and sel["code_label"])
                   else "<span class='pill warn'>No client assigned</span>")
    import db as _db
    _code = _db.get_code(sel["code_id"]) if sel["code_id"] else None
    pass_html = ("<div class='card'><div class='hd'><h2>Client passcode</h2></div>"
                 "<p class='sec-desc'>What the client types to open the link. It is the same passcode as on the Access codes page, "
                 "so changing it here changes it there.</p>"
                 + (passcode_form(_code, "/selections/edit?id=" + str(sel["id"]) + "#st=share") if _code is not None else
                    "<p class='muted'>No client is attached yet. Pick one under <a href='#st=details' data-go-tab='st:details'>Details</a>.</p>")
                 + "</div>")
    link_html = (
        "<div class='card'><div class='hd'><h2>Share with the client</h2></div>"
        "<p class='sec-desc'>Send this link. The client opens it with their passcode and sees these prices, never your costs or margins. "
        "A price change needs no new link; if you add or remove creators, send the link again.</p>"
        "<div class='sel-link'><input id='sel-url' value='" + e(link) + "' readonly aria-label='Selection link'>"
        "<button type='button' class='btn small lime' data-copy='#sel-url'>" + ui.icon("copy", 15) + " Copy link</button>"
        "<a class='btn small ghost' href='" + e(link) + "' target='_blank' rel='noopener'>Preview as the client</a></div></div>")
    campaign_html = campaign_start_card(sel, campaigns)
    body = (
        roster_list
        + ui.header(sel["name"], "A priced shortlist for one client: " + str(n_cr) + " creator" + ("" if n_cr == 1 else "s") + ". " + client_pill,
                    crumbs=[("Selections", u("/selections")), (sel["name"], None)],
                    actions="<button type='button' class='btn lime' data-go-tab='st:share'>" + ui.icon("send", 16) + " Share</button>")
        + note + stepper_html
        + "<div data-tabs='st'>" + ui.tab_nav("st", [("creators", "Creators & prices", n_cr), ("fit", "Fit & tags", (sum(1 for v in verdicts_of.values() if v) or None)), ("details", "Details", None),
                                                    ("share", "Share", None), ("campaign", "Campaign", len(campaigns) or None)])
        + "<form method='post' action='" + u("/selections/save") + "' enctype='multipart/form-data'>"
        + "<input type='hidden' name='id' value='" + str(sel["id"]) + "'>"
        + "<div class='panel' data-panel='creators'>"
+ "<div class='card'><div class='row'>"
          "<div style='display:flex;gap:10px'><div><label>Minimum margin (%)</label><div class='margin-box'>"
          "<input name='margin' id='sel-margin' data-cur='" + cur + "' data-rate='" + str(usable.get(cur, 1))
        + "' value='" + margin_txt + "' placeholder='e.g. 40' "
          "inputmode='decimal'></div></div>"
          "<div><label>Maximum margin (%)</label><div class='margin-box'>"
          "<input name='margin_max' id='sel-margin-max' value='" + margin_max_txt + "' placeholder='e.g. 70' inputmode='decimal'></div></div></div>"
          "<div class='price-hint'>Cost to us is what we pay the creator, with no profit in it. The client's price runs from "
          "<b>cost + minimum margin</b> (the lowest price that still covers our profit) up to <b>cost + maximum margin</b>, "
          "rounded up to the next " + str(step_c) + " " + cur + ". Leave the maximum empty for one price. "
          "You can type any creator's range, or the total, yourself. Internal only — the client sees only the range.</div></div>"
          "<div style='flex:2'><dl class='money-sum' id='sel-money'></dl></div>"
          "</div>"
        + "<div class='card'><table class='sel-table'><thead><tr><th></th><th>Creator</th><th>Tier</th>"
          "<th>Standard price</th><th>Cost to us (<span class='cur-lbl'>" + cur + "</span>)</th><th>Price for this client (<span class='cur-lbl'>" + cur + "</span>)</th><th></th><th>Creator's default</th><th></th>"
          "</tr></thead><tbody>"
        + table + "</tbody></table>"
        + ("<p class='err'>No longer in the roster, left out: " + e(", ".join(missing)) + "</p>" if missing else "")
        + "<p class='price-hint'>Type a creator's cost and their price is worked out from the "
          "margin above. With no cost, type the price yourself, or leave it empty to use the "
          "creator's standard price. One figure = a fixed price. The client never sees a price "
          "against a creator — these add up to the total they see, unless you type a total above. "
          "Type a creator's <b>cost</b> and their price follows the margin, or type the <b>price</b> yourself and the "
          "profit and margin are worked out for you. The totals fill themselves. A price typed here stays in <b>this selection only</b>. Tick <b>make default</b> to also save it "
          "as that creator's price on the roster, so every later selection starts from it. A cost is "
          "remembered for their next selection.</p>"
        + "<div class='row'><div style='flex:2'><label>Add creators (optional)</label>"
          "<input name='add' list='roster-list' placeholder='Type a creator\'s name or code…' autocomplete='off'>"
          "<div class='price-hint'>Pick from the list, or paste several codes separated by commas.</div></div></div>"
                + "</div></div>"
        + "<div class='panel' data-panel='fit' hidden><div class='card'><div class='hd'><h2>Fit &amp; tags</h2></div>"
          "<p class='sec-desc'>Tell the client whether each creator suits this campaign, and what part they play. "
          "The client sees the fit, the roles, your reason and the tags on each creator's card, and can filter the selection by them. "
          "Everything here belongs to this selection only.</p>"
          "<div class='vd-bar'><div><label style='display:block;font-weight:600;font-size:13px;margin-bottom:4px'>Judge fit for this objective</label>"
          "<select name='sel_objective' id='vd-obj'>" + "".join(
              "<option" + (" selected" if o_ == obj_now else "") + ">" + o_ + "</option>" for o_ in _fit.OBJECTIVES) + "</select></div>"
          "<button type='button' class='btn small' id='vd-all'>Suggest fit &amp; role for everyone</button> "
          "<span class='muted' style='flex:1;min-width:260px'>Suggestions weigh each creator's analysis against the benchmark ranges in Settings, "
          "their audience in KSA, their reach and our own past campaigns with them, for the objective chosen. "
          "Or ignore them and fill everything in by hand — nothing is shown to the client until you save.</span></div>"
          "<div class='card' style='background:#f7f5f0;margin:0 0 14px'><strong>Who this selection is for</strong>"
          "<div class='price-hint' style='margin:4px 0 8px'>The matching score on every card is measured against this and the objective above. It updates itself — no button to press.</div>"
          "<div class='row'><div><label>Target country</label><select name='t_country' id='t-country'>" + "".join(
              "<option value='" + k_ + "'" + (" selected" if k_ == target_now["country"] else "") + ">" + e(n_) + "</option>" for k_, n_ in _fit.COUNTRIES) + "</select></div>"
          "<div><label>Audience gender</label><select name='t_gender' id='t-gender'>" + "".join(
              "<option" + (" selected" if g_ == target_now["gender"] else "") + ">" + g_ + "</option>" for g_ in _fit.GENDERS) + "</select></div>"
          "<div><label>Audience age</label><select name='t_age' id='t-age'><option>Any</option>" + "".join(
              "<option" + (" selected" if a_ == target_now["age"] else "") + ">" + a_ + "</option>" for a_ in _fit.AGE_BANDS) + "</select></div>"
          "<div style='flex:3'><label>Product categories (tick all that apply)</label><div class='vd-roles' id='t-category'>" + "".join(
              "<label class='vd-role'><input type='checkbox' name='t_category' value=\"" + e(i_) + "\""
              + (" checked" if i_.lower() in [c_.lower() for c_ in str(target_now["category"]).split("|")] else "") + "> <span>" + e(i_) + "</span></label>"
              for i_ in interests) + "</div></div></div></div>"
          "<div class='price-hint' id='tag-pool' data-pool='" + e(json.dumps(sorted({t for v in tags_of.values() for t in v}, key=str.lower))) + "'></div>"
          "<div class='vd-list'>" + fit_cards + "</div>"
          "<p class='price-hint'>Tags are your own labels (Hero, Beauty, Backup…), separated by commas. Click a tag in <i>Tags in use</i> to add it to the box you last typed in. "
          "Remember to press <b>Save changes</b> below.</p></div></div>"
        + "<div class='panel' data-panel='details' hidden><div class='card'><div class='hd'><h2>Details</h2></div>"
          "<p class='sec-desc'>What the client sees, which platform is priced, the currency and the total.</p>"
+ "<div class='row'><div style='flex:2'><label>Selection name (the client sees this)</label>"
          "<input name='name' value='" + e(sel["name"]) + "' required></div>"
        + "<div><label>Quoted for</label><select name='platform'>"
        + "".join("<option value='" + e(v) + "'" + (" selected" if (sel["platform"] or "") == v else "")
                  + ">" + e(lbl) + "</option>"
                  for v, lbl in [("", "Every platform they are on")] + [(p, p + " only") for p in PLATFORMS])
        + "</select><div class='price-hint'>Pick one and each creator is tiered and priced on "
          "THAT account — a creator who is Mid-Tier on Instagram and Micro on TikTok is quoted "
          "as Micro for a TikTok campaign.</div></div>"
        + "<div><label>Currency</label><select name='currency' data-rates='" + e(json.dumps({k: v for k, v in usable.items()})) + "'>" + "".join(
            "<option value='" + c + "'" + (" selected" if c == cur else "") + ">" + c + " — " + fx.NAMES[c] + "</option>"
            for c in fx.CURRENCIES if c in usable) + "</select><div class='price-hint'>What this selection is "
          "quoted in. Prices below are typed in it; the client can switch to another enabled currency. "
          "Rates are set in <a href='" + u("/settings") + "#fx'>Settings</a>.</div></div>"
        + "<div><label>Total the client sees (<span class='cur-lbl'>" + cur + "</span>)</label><div style='display:flex;gap:6px'>"
          "<input name='total_from' value='" + tf + "' placeholder='from' inputmode='numeric'>"
          "<input name='total_to' value='" + tt + "' placeholder='to' inputmode='numeric'></div>"
          "<div class='price-hint'>Fills itself from the prices below as you type them (currently "
        + money_c(lo_sum, hi_sum) + "). Type your own figure to override it; clear it to follow the creators again.</div></div>"
        + "</div></div>"
                + "</div>"
        + "<div class='savebar'><button class='btn lime'>Save changes</button><span class='muted'>Prices, margins and details are saved together.</span></div></form>"
        + ui.panel("share", link_html + pass_html) + ui.panel("campaign", campaign_html)
        + "</div>"
        + "<details class='card' style='margin-top:24px'><summary class='muted'>Delete this selection</summary>"
        + "<form method='post' action='" + u("/selections/delete") + "' data-confirm='Delete this selection? Its link stops working. You can restore it from History.' style='margin-top:12px'>"
        + "<input type='hidden' name='id' value='" + str(sel["id"]) + "'>"
        + "<button class='btn small danger'>Delete selection</button></form></details>"
        + MARGIN_JS + TAG_JS + VERDICT_JS
    )
    return page(sel["name"] + " — Selection", body, "/selections")


# Live pricing on the selection page: typing a cost or the margin shows the
# client price and the profit at once. The server does the same sum on save
# (db.client_price), so what is shown here is what gets stored.
MARGIN_JS = """<script>
(function(){
  var m=document.getElementById('sel-margin'), mx=document.getElementById('sel-margin-max'), sum=document.getElementById('sel-money');
  if(!m||!sum) return;
  // Everything on this page is in the selection's currency: costs, prices,
  // profit and totals. (Stored in SAR underneath; the catalogue shows the
  // same numbers in whichever currency the client picks.)
  var rate=Number(m.getAttribute('data-rate'))||1, cur=m.getAttribute('data-cur')||'SAR';
  function stepOf(c){return c==='USD'?5:c==='EGP'?50:10;}
  var step=stepOf(cur);
  function n(v){v=String(v==null?'':v).replace(/[^0-9.]/g,'');return v===''?null:Number(v);}
  function num(x){return Math.round(x).toLocaleString('en-US');}
  function fmt(x){return num(x)+' '+cur;}
  function price(cost,mg){return Math.ceil(cost*(1+(mg||0)/100)/step)*step;}
  function sh(v){return rate===1?v:Math.round(v*rate/step)*step;}      // a SAR amount, shown in this currency
  var rows=[].slice.call(document.querySelectorAll('.sel-table tbody tr')).filter(function(r){
    return r.querySelector('input[name=cost]');});
  var tf=document.querySelector('input[name=total_from]'), tt=document.querySelector('input[name=total_to]');
  // The range from the two margins: [cost + minimum margin, cost + maximum margin].
  function autoRange(cost){
    var mg=n(m.value), mgx=mx?n(mx.value):null, lo=price(cost,mg);
    return [lo,(mgx!==null&&mgx>(mg||0))?price(cost,mgx):lo];
  }
  // A price range that differs from the automatic one was typed by hand; keep it.
  function detectManual(){
    rows.forEach(function(r){
      var cost=n(r.querySelector('input[name=cost]').value), lo=n(r.querySelector('input[name=p_from]').value), hi=n(r.querySelector('input[name=p_to]').value);
      if(cost!==null&&lo!==null){ var a=autoRange(cost); if(Math.abs(lo-a[0])>step||Math.abs((hi===null?lo:hi)-a[1])>step) r.dataset.manual='1'; }
    });
  }
  detectManual();
  var totalsSet=false;
  function rowPrice(r,mg){
    var c=r.querySelector('input[name=cost]'), lo=r.querySelector('input[name=p_from]'), hi=r.querySelector('input[name=p_to]');
    var cost=n(c.value), loV=n(lo.value), hiV=n(hi.value), manual=r.dataset.manual==='1';
    if(cost!==null&&!manual){
      var a=autoRange(cost);
      lo.value=num(a[0]); hi.value=num(a[1]); lo.dataset.auto=hi.dataset.auto='1';
      return {cost:cost,lo:a[0],hi:a[1],auto:true};
    }
    if(lo.dataset.auto&&cost===null){lo.value='';hi.value='';delete lo.dataset.auto;delete hi.dataset.auto;loV=hiV=null;}
    if(loV!==null||hiV!==null){
      var a=loV!==null?loV:hiV, b=hiV!==null?hiV:loV;
      return {cost:cost,lo:Math.min(a,b),hi:Math.max(a,b),manual:true};
    }
    var d=(lo.getAttribute('data-def')||'').split('|');          // standard price (SAR): counts toward the total
    if(d.length===2) return {cost:cost,lo:sh(Number(d[0])),hi:sh(Number(d[1])),standard:true};
    return {cost:cost,lo:null,hi:null};
  }
  function run(){
    var mg=n(m.value), tc=0, tpl=0, tph=0, tlo=0, thi=0, costed=0, counted=0;
    rows.forEach(function(r){
      var out=r.querySelector('.profit'), gone=r.querySelector('input[name=drop]').checked, x=rowPrice(r,mg);
      out.textContent='';
      if(x.lo!==null){
        if(x.cost!==null){
          var p1=x.lo-x.cost, p2=x.hi-x.cost, m1=x.cost?p1/x.cost*100:0, m2=x.cost?p2/x.cost*100:0;
          function sg(v){return (v>=0?'+':'')+num(v);}
          out.textContent=(p1===p2?sg(p1):sg(p1)+' to '+sg(p2))+' '+cur+' profit · '+(p1===p2?(Math.round(m1*10)/10):(Math.round(m1*10)/10)+'–'+(Math.round(m2*10)/10))+'% margin'+(x.manual?' (your price)':'');
          out.style.color=p1<0?'#c01010':'';
        } else if(x.standard) out.textContent='standard price';
      }
      if(gone) return;
      if(x.lo!==null){tlo+=x.lo;thi+=x.hi;counted++;}
      if(x.cost!==null&&x.lo!==null){tc+=x.cost;tpl+=x.lo;tph+=x.hi;costed++;}
    });
    var pl=tpl-tc, ph=tph-tc, ml=tc?pl/tc*100:0, mh=tc?ph/tc*100:0, same=Math.round(pl)===Math.round(ph);
    var priceTxt=counted?(thi>tlo?fmt(tlo)+' – '+fmt(thi):fmt(tlo)):'—';
    sum.innerHTML=(costed||counted)?(
      (costed?'<div><dt>Cost ('+costed+')</dt><dd>'+fmt(tc)+'</dd></div>':'')+
      '<div><dt>Client price ('+counted+')</dt><dd>'+priceTxt+'</dd></div>'+
      (costed?'<div><dt>Profit'+(same?'':' (min – max)')+'</dt><dd class="gain">'+(same?fmt(pl):fmt(pl)+' – '+fmt(ph))+'</dd></div>'+
        '<div><dt>Margin on cost</dt><dd class="gain">'+(same?(Math.round(ml*10)/10)+'%':(Math.round(ml*10)/10)+'% – '+(Math.round(mh*10)/10)+'%')+'</dd></div>':'')):
      '<div><dt>Profit</dt><dd class="muted" style="font-size:14px;font-weight:400">'+
      'Type a cost and a price against a creator to see it.</dd></div>';
    rows.forEach(function(r){var a=r.querySelector('input[name=p_from]'), z=r.querySelector('input[name=p_to]'); a.dataset.prev=a.value; z.dataset.prev=z.value;});
    // The total the client sees follows the prices, unless typed by hand.
    if(tf&&tt&&counted){
      if(!totalsSet){                                  // first run: a stored total that differs from the sum was typed
        var a0=n(tf.value);
        if(a0!==null&&Math.abs(a0-tlo)>step) tf.dataset.manual='1';
        totalsSet=true;
      }
      if(tf.dataset.manual!=='1'){tf.value=num(tlo);tt.value=num(thi);}
    }
  }
  function detectManual0(){}      // margins changed: rows that follow the margins simply follow them
  document.addEventListener('input',function(e){
    var t=e.target;
    if(t===m||t===mx||t.name==='cost'){ if(t===m||t===mx) detectManual0(); run(); }
    else if(t.name==='p_from'||t.name==='p_to'){
      var r=t.closest('tr'), cost=n(r.querySelector('input[name=cost]').value), pl=r.querySelector('input[name=p_from]'), ph=r.querySelector('input[name=p_to]');
      // When the two boxes held ONE price, typing in one makes a fixed price (the other follows).
      // When they held a range, typing in one box changes only that end.
      var single=(pl.dataset.prev!==undefined&&pl.dataset.prev===ph.dataset.prev);
      if(single&&t===pl&&ph.dataset.auto) ph.value=t.value;
      if(single&&t===ph&&pl.dataset.auto) pl.value=t.value;
      delete pl.dataset.auto; delete ph.dataset.auto;
      if(t.value==='') delete r.dataset.manual; else if(cost!==null) r.dataset.manual='1';
      run();
    } else if(t===tf||t===tt){
      if(tf.value===''&&tt.value==='') delete tf.dataset.manual; else tf.dataset.manual='1';
      run();
    }
  });
  // Changing the currency converts every figure on the page, so nothing is
  // silently re-read in the new currency when you save.
  var cs=document.querySelector('select[name=currency]');
  if(cs){
    var rates={}; try{rates=JSON.parse(cs.getAttribute('data-rates')||'{}');}catch(x){}
    cs.addEventListener('change',function(){
      var nc=cs.value, nr=Number(rates[nc]); if(!nr) return;
      var ns=stepOf(nc);
      [].slice.call(document.querySelectorAll('input[name=cost],input[name=p_from],input[name=p_to],input[name=total_from],input[name=total_to]')).forEach(function(i){
        var v=n(i.value); if(v===null) return;
        // the exact SAR figure is remembered, so switching back and forth loses nothing
        var sar=(i.dataset.shown===i.value&&i.dataset.sar)?parseFloat(i.dataset.sar):v/rate;
        i.value=num(i.name==='cost'?sar*nr:Math.round(sar*nr/ns)*ns);
        i.dataset.sar=String(sar); i.dataset.shown=i.value;
      });
      rate=nr; cur=nc; step=ns;
      m.setAttribute('data-rate',String(nr)); m.setAttribute('data-cur',nc);
      [].slice.call(document.querySelectorAll('.cur-lbl')).forEach(function(l){l.textContent=nc;});
      rows.forEach(function(r){delete r.dataset.manual;});
      detectManual();             // a price that is not cost + margins stays as typed
      totalsSet=true;                    // a total that follows the prices stays that way; a typed one stays typed
      run();
    });
  }
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


def status_button(k):
    """Go live / take offline, right on the campaigns list. Live is what puts
    the report in front of the client, under their passcode."""
    to, label, cls, ask = {
        "draft": ("live", "Go live", "btn small lime",
                  "Go live? The client sees this campaign's report on the catalogue under their passcode."),
        "live": ("draft", "Take offline", "btn small ghost",
                 "Take this campaign offline? The client stops seeing its report."),
        "ended": ("live", "Reopen", "btn small ghost", "Reopen this campaign as live?"),
    }.get(k["status"], ("live", "Go live", "btn small lime", "Go live?"))
    return ("<form method='post' action='" + u("/campaigns/status") + "' class='inline' "
            "onsubmit=\"return confirm('" + e(ask.replace("'", "’")) + "')\">"
            "<input type='hidden' name='id' value='" + str(k["id"]) + "'>"
            "<input type='hidden' name='status' value='" + to + "'>"
            "<button class='" + cls + "'>" + label + "</button></form> ")


def campaigns_page(camps, codes, error=None, message=None, selections=()):
    note = _notes(error, message)
    n_live = sum(1 for k in camps if k["status"] == "live")
    n_draft = sum(1 for k in camps if k["status"] == "draft")
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
            + "<td class='right nowrap'>" + status_button(k)
            + "<a class='btn small' href='" + u("/campaigns/edit") + "?id="
            + str(k["id"]) + "'>Open</a></td></tr>")
    sel_opts = "".join("<option value='" + str(x["id"]) + "'>" + e(x["name"])
                       + (" — " + e(x["code_label"]) if x["code_label"] else "") + "</option>" for x in selections)
    start = (
        "<div class='card'><div class='hd'><h2>Start a campaign</h2></div>"
        "<p class='sec-desc'>Two ways in. From a selection is quicker: its creators, costs and client passcode come across.</p>"
        "<div class='two'>"
        "<form method='post' action='" + u("/campaigns/new") + "' class='startbox'>"
        "<h3>From a selection</h3><label>Pick the booked selection</label>"
        "<select name='selection' required><option value=''>— choose —</option>" + sel_opts + "</select>"
        "<button class='btn lime'>" + ui.icon("plus", 15) + " Start from selection</button></form>"
        "<form method='post' action='" + u("/campaigns/new") + "' class='startbox'>"
        "<h3>Blank</h3><label>Campaign name</label><input name='name' required placeholder='e.g. SVR Sun Secure — Wave 4'>"
        "<div class='row'><div><label>Client (brand)</label><input name='client' placeholder='e.g. SVR'></div>"
        "<div><label>Passcode that sees it</label>" + code_select(codes, None) + "</div></div>"
        "<button class='btn'>" + ui.icon("plus", 15) + " Create blank campaign</button></form>"
        "</div></div>")
    table = (ui.empty("flag", "No campaigns yet", "Start one above. It stays a draft, invisible to the client, until you set it live.")
             if not camps else
             "<div class='stat-row'><div class='stat'><b>" + str(n_live) + "</b><span>Live</span></div>"
             "<div class='stat'><b>" + str(n_draft) + "</b><span>Drafts</span></div>"
             "<div class='stat'><b>" + str(len(camps)) + "</b><span>Total</span></div></div>"
             "<div class='card'><table><thead><tr><th>Campaign</th><th>Client</th><th>Status</th>"
             "<th>Dates</th><th>Creators</th><th>Updated</th><th></th></tr></thead><tbody>"
             + "".join(rows) + "</tbody></table></div>")
    body = (
        ui.header("Campaigns", "Creators booked for a client, the dates they post in and the rules that decide which posts count. "
                  "The client only views the report.",
                  crumbs=[("Work", None), ("Campaigns", None)],
                  actions="<a class='btn ghost' href='" + u("/planner") + "'>ROI planner</a>")
        + note + table + start)
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
               roster_link(code, c["name"]) + ("" if c["active"] else " <span class='pill dead'>hidden</span>"))
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
            + "<td><select name='pending_status' style='min-width:150px'>" + "".join(
                "<option value='" + e(v) + "'" + (" selected" if (c["pending_status"] if "pending_status" in c.keys() else None) == v else "")
                + ">" + e(v or "—") + "</option>" for v in [""] + __import__("db").PENDING_STATUSES) + "</select>"
            + "<input type='date' name='pending_date' value='" + e((c["pending_date"] if "pending_date" in c.keys() else "") or "")
            + "' title='When the next post is expected' style='margin-top:6px'></td>"
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
    w_now = metrics.campaign_weights(k) if obj_now == "custom" else None
    w_now = w_now or metrics.OBJECTIVES[obj_now][1]
    obj_opts = "".join(
        "<option value='" + key + "'" + (" selected" if key == obj_now else "") + ">" + e(label)
        + (" — " + e(metrics.TEMPLATE_NOTES.get(key, "")) if key != "custom" else " — set the four percentages yourself")
        + "</option>" for key, (label, w) in metrics.OBJECTIVES.items())
    obj_json = json.dumps({key: [round(x * 100, 1) for x in w] for key, (label, w) in metrics.OBJECTIVES.items() if key != "custom"})
    pct_in = lambda name, label, val, hint: ("<div><label>" + label + "</label><div class='margin-box'><input name='" + name
                                              + "' class='w-pct' inputmode='decimal' value='" + ("%g" % round(val * 100, 1)) + "'><span class='suffix'>%</span></div>"
                                              "<div class='price-hint'>" + hint + "</div></div>")
    weights_ui = ("<div class='row'>"
                  + pct_in("w_reach", "Views &amp; reach", w_now[0], "How many people saw it")
                  + pct_in("w_eng", "Engagement", w_now[1], "Likes and comments")
                  + pct_in("w_er", "Engagement rate", w_now[2], "Reactions per view")
                  + pct_in("w_clicks", "Link clicks", w_now[3], "Needs a tracked link")
                  + "</div><div class='price-hint' id='w-sum'></div>"
                  "<script>(function(){var T=" + obj_json + ",sel=document.querySelector('select[name=objective]'),"
                  "in_=[].slice.call(document.querySelectorAll('.w-pct')),sum=document.getElementById('w-sum');"
                  "function show(){var t=in_.reduce(function(a,i){return a+(parseFloat(i.value)||0)},0);"
                  "sum.textContent='Total '+(Math.round(t*10)/10)+'%'+(Math.abs(t-100)>0.05?' — it is scaled to 100% when you save, so the proportions are what count.':'');"
                  "sum.style.color=Math.abs(t-100)>0.05?'#b45309':''}"
                  "sel.addEventListener('change',function(){var v=T[sel.value];if(!v)return;in_.forEach(function(i,n){i.value=v[n]});show()});"
                  "in_.forEach(function(i){i.addEventListener('input',function(){sel.value='custom';show()})});show()})();</script>")
    tgt = lambda key, label, hint: ("<div><label>" + label + "</label><input name='target_" + key + "' inputmode='decimal' value='"
                                    + (("%g" % targets[key]) if key in targets else "") + "' placeholder='" + hint + "'></div>")

    def step(n, title, body, hint=""):
        return ("<section class='step'><h2><span class='step-n'>" + str(n) + "</span>" + title + "</h2>"
                + ("<p class='sub'>" + hint + "</p>" if hint else "") + "<div class='card'>" + body + "</div></section>")

    sync = ""
    if k["selection_id"]:
        # A button inside the save form that submits a separate form (below the
        # page's main form): <form> cannot nest, and a nested one used to close
        # the save form early, leaving the Save button with nothing to save.
        sync = "<button type='submit' form='camp-sync' class='btn small ghost'>Add creators added to the selection since</button>"
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
               "<th>Posts planned</th><th>Posts still to come</th><th>Fee to us (SAR)</th><th></th></tr></thead><tbody>" + table + "</tbody></table>"
               "<div class='row' style='margin-top:14px'><div style='flex:2'><label>Add creators by profile link or code</label>"
               "<textarea name='add' rows='3' placeholder='https://www.instagram.com/handle/\nhttps://www.tiktok.com/@handle\nHV-MC-005'></textarea>"
               "<div class='price-hint'>One per line, or separated by commas — Instagram, TikTok, Snapchat, "
               "YouTube or X links, @handles, or roster codes. Each is matched to the roster. A profile the "
               "roster has under another platform is added to that creator; one it does not have at all "
               "is added as a new creator, hidden from clients until you complete their details.</div></div>"
               "<div><label>Platform tracked</label><select name='platform'>" + plat_opts + "</select></div></div>",
               "Posts planned is what each creator is booked for; the report counts delivered against it. "
               "Each booked post not live yet shows on the client's report as a Pending card with the status "
               "and expected date you set here. Fees stay internal.")
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
               "<select name='objective'>" + obj_opts + "</select>"
               "<div class='price-hint'>Pick a template and it fills the four percentages below. Change any of them and the objective becomes Custom — "
               "the percentages are what scoring uses.</div></div></div>"
               + weights_ui
               + "<div class='card' style='background:#f7f5f0;margin:14px 0 6px;display:flex;gap:14px;align-items:center;flex-wrap:wrap'>"
                 "<div style='flex:1;min-width:240px'><strong>Set targets with the ROI calculator</strong>"
                 "<div class='price-hint'>Pick a template, enter the client's budget — it works out the minimum the budget must buy, "
                 "what the booked creators can safely deliver, and the benchmark the client sees.</div></div>"
                 "<a class='btn small' href='" + u("/calculator") + "?id=" + str(k["id"]) + "'>Open the calculator</a></div>"
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
        + ("<form id='camp-sync' method='post' action='" + u("/campaigns/sync") + "'><input type='hidden' name='id' value='" + str(k["id"]) + "'></form>"
           if k["selection_id"] else "")
        + "<form method='post' action='" + u("/campaigns/delete") + "' style='margin-top:24px' "
          "onsubmit=\"return confirm('Delete this campaign? Its report and links stop working.')\">"
          "<input type='hidden' name='id' value='" + str(k["id"]) + "'>"
          "<button class='btn small danger'>Delete campaign</button></form>"
    )
    return page(k["name"] + " — Campaign", body, "/campaigns")

CAMP_TABS = [("setup", "/campaigns/edit", "Setup", "Dates, creators, rules and the client passcode"),
             ("content", "/campaigns/content", "Content", "The posts creators published, and their daily numbers"),
             ("insights", "/campaigns/insights", "Insights", "Audience data creators send in"),
             ("links", "/campaigns/links", "Tracking links", "Link clicks, per creator"),
             ("plan", "/calculator", "Goals & ROI", "What the campaign should achieve"),
             ("report", "/campaigns/report", "Report", "What the client sees")]


def campaign_tabs(k, on):
    return ui.ptabs([(u(href) + "?id=" + str(k["id"]), label, None, key == on) for key, href, label, _d in CAMP_TABS])


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
            "<tr class='linkrow" + ("" if r["active"] else " is-off") + "' id='link-" + e(r["slug"])
            + "'><td><code>" + e(r["code"]) + "</code><br>" + e(names[r["code"]])
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
            + str(k["id"]) + "'><input type='hidden' name='slug' value='" + e(r["slug"]) + "'><button class='btn tiny"
            + (" ghost'>Switch off" if r["active"] else "'>Switch on") + "</button></form></td></tr>")
    table = "".join(items) or ("<tr><td colspan='4' class='muted'>No creators in this campaign yet — "
                               "add them on the Setup tab and each gets a link here.</td></tr>")
    body = (
        _head(k, "links") + note
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
    desc = next((d for key, _h, _l, d in CAMP_TABS if key == tab), "")
    act = ("<form method='post' action='" + u("/selections/new") + "'><input type='hidden' name='mode' value='from_campaign'>"
           "<input type='hidden' name='campaign' value='" + str(k["id"]) + "'>"
           "<button class='btn ghost' title='Make a priced selection from this campaign&#39;s creators'>"
           + ui.icon("list", 15) + " Selection from this campaign</button></form>") if tab == "setup" and not k["selection_id"] else ""
    return (ui.header(k["name"], desc + " &middot; " + status_pill(k["status"]),
                      crumbs=[("Campaigns", u("/campaigns")), (k["name"], None)], actions=act,
                      tabs=[(u(h) + "?id=" + str(k["id"]), l, None, key == tab) for key, h, l, _d in CAMP_TABS])
            + _notes(error, message))


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
        thumb = ("<img class='post-thumb' src='" + e(thumb_src(p["thumb"])) + "' alt='' loading='lazy' "
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
    # What the platform does not show publicly — to collect by hand.
    live = [p for p in posts if not p["hidden"] and p["section"] == "campaign"]
    hid = [p for p in live if p.get("likes_hidden")]
    no_reach = sum(1 for p in live if "reach" in (p.get("gaps") or []))
    no_ss = sum(1 for p in live if "shares" in (p.get("gaps") or []))
    todo = ""
    if live and (hid or no_reach or no_ss):
        todo = ("<div class='card' style='background:#fff8ec;border-color:#f3d9a8'><strong>Collect by hand</strong>"
                "<ul style='margin:8px 0 0;padding-left:18px;font-size:13px;line-height:1.6'>"
                + (("<li><strong>Likes hidden on %d posts</strong> — ask for the like count or insights: " % len(hid))
                   + ", ".join("<a href='" + e(p["url"]) + "' target='_blank' rel='noopener'>" + e(p.get("creator_name") or p["code"])
                               + "</a>" for p in hid) + ". Until then engagement there is comments only and they are left out of ER.</li>" if hid else "")
                + ("<li><strong>Real reach on %d posts</strong> — reels show plays, not unique people; reach is estimated "
                   "until the creator's insights are approved.</li>" % no_reach if no_reach else "")
                + ("<li><strong>Shares and saves on %d posts</strong> — not public; they come from insights.</li>" % no_ss if no_ss else "")
                + "</ul><p class='price-hint'>Ask creators for 30-day insights screenshots on the "
                  "<a href='" + u("/campaigns/insights") + "?id=" + str(k["id"]) + "'>Insights tab</a>, or type the numbers into a post with Edit.</p></div>")
    body = (
        _head(k, "content", error, message)
        + todo
        + "<div class='card'><table><thead><tr><th></th><th>Post</th><th>Counts as</th><th class='right'>Likes</th>"
          "<th class='right'>Views</th><th class='right'>Reach / impressions</th><th class='right'>ER</th><th></th>"
          "</tr></thead><tbody>" + table + "</tbody></table>"
        + "<p class='price-hint'>est. = estimated (see Settings for how); real = from the creator's own "
          "insights, approved on the Insights tab. ER for videos is engagement ÷ views.</p></div>"
        + _content_tools(k, members, posts, opts, plats, kinds)
    )
    return page(k["name"] + " — Content", body, "/campaigns")


def _content_tools(k, members, posts, opts, plats, kinds):
    import db as db_mod
    """Four ways to get posts and numbers in, on one screen."""
    cid = str(k["id"])
    posted = {}
    for p in posts:
        if not p["hidden"] and p["section"] == "campaign":
            posted[p["code"]] = posted.get(p["code"], 0) + 1
    rows = []
    for m in members:
        n, want = posted.get(m["cc_code"], 0), m["planned"] or 0
        if n and (not want or n >= want):
            pill = "<span class='pill live'>posted</span>"
        elif n:
            pill = "<span class='pill warn'>%d of %d posted</span>" % (n, want)
        else:
            pill = "<span class='pill dead'>not yet</span>"
        cur = m["pending_status"] if "pending_status" in m.keys() else None
        dt = (m["pending_date"] if "pending_date" in m.keys() else "") or ""
        opts_st = "".join("<option value='%s'%s>%s</option>" % (e(v), " selected" if cur == v else "", e(v or "—"))
                          for v in [""] + db_mod.PENDING_STATUSES)
        rows.append("<tr><td><strong>" + e(m["name"] or m["cc_code"]) + "</strong><br><span class='muted'>" + e(m["cc_code"])
                    + "</span><input type='hidden' name='code' value='" + e(m["cc_code"]) + "'></td><td>" + pill + "</td>"
                    "<td class='right'>" + str(n) + (" / " + str(want) if want else "") + "</td>"
                    "<td><select name='pending_status' aria-label='Where the next post is'>" + opts_st + "</select></td>"
                    "<td><input type='date' name='pending_date' value='" + e(dt) + "' aria-label='When the next post is expected'></td></tr>")
    status = (ui.empty("users", "No creators yet", "Add creators on the Setup tab first.") if not members else
              "<p class='sec-desc'>Who still owes a post, where it is, and when to expect it. Change the rows and press Save.</p>"
              "<form method='post' action='" + u("/campaigns/content/pending") + "'><input type='hidden' name='id' value='" + cid + "'>"
              "<table><thead><tr><th>Creator</th><th>Posting</th><th class='right'>Posts</th><th>Next post is</th><th>Expected on</th></tr></thead><tbody>"
              + "".join(rows) + "</tbody></table><button class='btn lime' style='margin-top:12px'>Save</button></form>")
    links = ("<p class='sec-desc'>Several posts from one creator at once. One link per line.</p>"
             "<form method='post' action='" + u("/campaigns/content/bulk") + "'>"
             "<input type='hidden' name='id' value='" + cid + "'><input type='hidden' name='do' value='links'>"
             "<div class='row'><div><label>Creator</label><select name='code' required>" + opts + "</select></div>"
             "<div><label>Platform</label><select name='platform'>" + plats + "</select></div>"
             "<div><label>Type</label><select name='kind'>" + kinds + "</select></div>"
             "<div><label>Posted on</label><input type='date' name='posted'></div></div>"
             "<label>Post links</label><textarea name='text' rows='6' required placeholder='https://www.instagram.com/reel/…&#10;https://www.instagram.com/p/…'></textarea>"
             "<button class='btn lime'>Add all</button></form>")
    numbers = ("<p class='sec-desc'>Today's numbers for many posts at once. One line per post: the post link, then likes, comments, views, shares, saves "
               "(commas, spaces or tabs between). Copy it straight from a spreadsheet. Leave numbers off to keep them as they are.</p>"
               "<form method='post' action='" + u("/campaigns/content/bulk") + "'>"
               "<input type='hidden' name='id' value='" + cid + "'><input type='hidden' name='do' value='numbers'>"
               "<textarea name='text' rows='7' required placeholder='https://www.instagram.com/reel/abc/  1200  45  18000  30  12'></textarea>"
               "<button class='btn lime'>Save numbers</button></form>")
    single = ("<form method='post' action='" + u("/campaigns/content/add") + "' class='card flat'>"
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
        + "</div><button class='btn'>Add post</button></form>")
    return ui.tabset("add", [("status", "Who has posted", None), ("links", "Paste links", None),
                             ("numbers", "Paste numbers", None), ("single", "One post, with caption", None)],
                     {"status": status, "links": links, "numbers": numbers, "single": single})


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
                  bm=None, fx_rates=None):
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
        ui.header("Settings", "Rates and keys that apply to the whole workspace: how earned media value is worked out, currencies and the capture token.", crumbs=[("System", None), ("Settings", None)])
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
        + fx_card(fx_rates or {})
    )
    return page("Settings", body, "/settings")


def fx_card(rates):
    """Fixed exchange rates for quoting selections in other currencies."""
    import fx
    saved = rates
    boxes = "".join(
        "<div><label>1 SAR = ? " + c + " <span class='muted'>(" + fx.NAMES[c] + ")</span></label>"
        "<input name='fx_" + c + "' inputmode='decimal' value='" + (("%g" % saved[c]) if saved.get(c) else "")
        + "' placeholder='" + (("%g" % fx.DEFAULTS[c]) if fx.DEFAULTS.get(c) else "not set — off") + "'></div>"
        for c in fx.CURRENCIES[1:])
    return ("<h2 id='fx'>Currencies</h2><form method='post' action='" + u("/settings/fx") + "' class='card'>"
            "<p class='sub'>Prices are kept in SAR. A selection can be quoted in another currency, and the "
            "client can switch between the ones set here, at these fixed rates. Leave a box empty to "
            "switch that currency off. AED and USD start from their official pegs (1 USD = 3.75 SAR = "
            "3.6725 AED); EGP floats, so it is off until you enter today's rate.</p>"
            "<div class='row'>" + boxes + "</div>"
            "<p class='price-hint'>Converted prices are rounded: SAR and AED to the nearest 10, USD to the "
            "nearest 5, EGP to the nearest 50.</p><button class='btn'>Save rates</button></form>")


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
    fake = "".join(line(label, "bm_" + key, bm[key])
                   for key, label in [("fake_followers", "Fake followers % of audience"),
                                      ("fake_likers", "Fake likers % of likes")])
    return ("<h2>Benchmarks</h2><div class='card'><p class='sub'>What the report calls good (green), moderate (amber) "
            "or low (red). These are industry guides; campaigns add their own targets on the Setup tab.</p>"
            "<table><thead><tr><th>Engagement rate % by tier</th><th>Good from</th><th>Moderate from</th></tr></thead><tbody>"
            + er_rows + other + "</tbody></table>"
            + "<p class='sub' style='margin-top:18px'>Fake shares work the other way round — lower is better. "
              "Good up to the first figure, moderate up to the second, above that high.</p>"
              "<table><thead><tr><th>Fake share</th><th>Good up to</th><th>Moderate up to</th></tr></thead><tbody>"
            + fake + "</tbody></table></div>")


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


def clients_page(overview, origin, archived=False, n_archived=0, page_no=1, total=0, ok=None):
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
            + (str(o["analysis_requests"]) + " analysis request(s)" if o["analysis_requests"] else "")
            + " " + archive_button("client", c["id"], archived) + "</div></div>"
            + "<div class='grid2' style='margin-top:12px'><div><label>Selections → campaigns</label><ul class='chain-list'>"
            + (sels or "<li class='muted'>No selections yet.</li>") + "</ul></div>"
            + "<div><label>All campaigns</label><ul class='chain-list'>" + (camps or "<li class='muted'>None yet.</li>")
            + "</ul></div></div></div>")
    body = (ui.header("Clients", "Each client is one passcode. Follow it from the shortlist they picked to the campaign it became "
                      "and the report they see. Every name links to the page that controls it.",
                      actions="<a class='btn lime' href='" + u("/codes") + "#new-code'>" + ui.icon("plus", 16) + " New client</a>",
                      tabs=_client_tabs("clients"))
            + ("<div class='ok'>" + e(ok) + "</div>" if ok else "")
            + archive_tabs("/clients", archived, n_archived, "Clients")
            + ("".join(cards) or ("<div class='card muted'>" + ("Nothing archived." if archived else
               "No clients yet — issue a passcode on Access codes.") + "</div>"))
            + pager(total, page_no, "/clients", 20, archived=("1" if archived else "")))
    return page("Clients", body, "/clients")


def _dropzone(zid, name, accept, multiple, label):
    """A file picker that also takes dropped files and lists what was chosen."""
    return ("<div class='dz' id='" + zid + "' style='border:2px dashed #c9c2b2;border-radius:10px;padding:22px;"
            "text-align:center;cursor:pointer;margin:8px 0 12px;background:#faf8f3'>"
            "<div class='dz-t'>" + e(label) + "</div><div class='muted dz-l' style='margin-top:6px'></div>"
            "<input type='file' name='" + name + "' accept='" + accept + "'" + (" multiple" if multiple else "")
            + " required style='position:absolute;left:-9999px'></div>"
            "<script>(function(){var z=document.getElementById('" + zid + "'),i=z.querySelector('input'),"
            "l=z.querySelector('.dz-l');function show(){var n=i.files.length;l.textContent=n?(n==1?i.files[0].name:n+' files chosen'):''}"
            "z.onclick=function(){i.click()};i.onchange=show;"
            "['dragenter','dragover'].forEach(function(ev){z.addEventListener(ev,function(x){x.preventDefault();z.style.background='#eef6d8'})});"
            "['dragleave','drop'].forEach(function(ev){z.addEventListener(ev,function(x){x.preventDefault();z.style.background='#faf8f3'})});"
            "z.addEventListener('drop',function(x){var f=x.dataTransfer.files;if(!f.length)return;i.files=f;show()});"
            "i.onclick=function(x){x.stopPropagation()};})();</script>")


_PICKER_JS = r"""(function(){
var B='%BASE%',$=function(i){return document.getElementById(i)};
var basket={},timer,last={all:[]};
function esc(t){return String(t==null?'':t).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function params(){var p=new URLSearchParams();p.set('q',$('pk-q').value);p.set('platform',$('pk-pl').value);p.set('ap',$('pk-ap').value);
 if($('pk-no').checked)p.set('nohave','1');if($('pk-src').value)p.set('source',$('pk-src').value);return p}
function search(){fetch(B+'/analysis/find?'+params()).then(function(r){return r.json()}).then(function(d){last=d;drawResults()})}
function drawResults(){var rows=last.items.map(function(c){
 return '<label class="pk-row"><input type="checkbox" data-c="'+esc(c.code)+'" data-n="'+esc(c.name)+'"'+(basket[c.code]?' checked':'')+'> <strong>'+esc(c.name)+'</strong> <span class="muted">'+(c.handle?'@'+esc(c.handle)+' · ':'')+esc(c.platform)+(c.followers?' · '+c.followers.toLocaleString():'')+'</span>'+(c.has&&c.has.length?' <span class="pill live">analysed: '+esc(c.has.join(', '))+'</span>':'')+'</label>'}).join('');
 $('pk-list').innerHTML=rows||'<div class="muted" style="padding:10px">No creators match.</div>';
 $('pk-count').textContent=last.total+' match'+(last.total==1?'':'es')+(last.total>last.items.length?' (showing '+last.items.length+')':'');
 $('pk-all').disabled=!last.total;$('pk-all').textContent='Add all '+last.total}
function drawBasket(){var k=Object.keys(basket);$('pk-n').textContent=k.length;
 $('pk-chips').innerHTML=k.slice(0,40).map(function(c){return '<span class="pk-chip">'+esc(basket[c])+' <a href="#" data-x="'+esc(c)+'">×</a></span>'}).join('')+(k.length>40?' <span class="muted">+'+(k.length-40)+' more</span>':'');
 $('pk-codes').value=k.join(',');$('pk-dl').disabled=!k.length}
$('pk-list').addEventListener('change',function(e){var t=e.target;if(t.dataset.c){if(t.checked)basket[t.dataset.c]=t.dataset.n;else delete basket[t.dataset.c];drawBasket()}});
$('pk-chips').addEventListener('click',function(e){var c=e.target.dataset.x;if(c){delete basket[c];drawBasket();drawResults();e.preventDefault()}});
$('pk-all').onclick=function(){last.all.forEach(function(r){basket[r[0]]=r[1]});drawBasket();drawResults()};
$('pk-clear').onclick=function(){basket={};drawBasket();drawResults()};
['pk-q'].forEach(function(i){$(i).oninput=function(){clearTimeout(timer);timer=setTimeout(search,250)}});
['pk-pl','pk-no','pk-src','pk-ap'].forEach(function(i){$(i).onchange=search});
$('pk-ap').addEventListener('change',function(){$('pk-apf').value=$('pk-ap').value});
$('pk-paste').onclick=function(){var b=new URLSearchParams();b.set('list',$('pk-list-in').value);
 fetch(B+'/analysis/find',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:b}).then(function(r){return r.json()}).then(function(d){
  d.all.forEach(function(r){basket[r[0]]=r[1]});drawBasket();
  $('pk-pmsg').textContent='Added '+d.all.length+(d.missing.length?'. Not recognised: '+d.missing.slice(0,8).join(', ')+(d.missing.length>8?' …':''):'.')})};
search();drawBasket()})();"""


def _creator_picker(sources, platforms):
    """Search the roster, tick creators (or add every match, or paste a list of
    handles / profile links / names), and download a sheet for exactly them."""
    return ("<style>.pk-list{max-height:280px;overflow:auto;border:1px solid #e6e1d6;border-radius:8px;background:#fff}"
            ".pk-row{display:block;padding:7px 10px;border-bottom:1px solid #f0ece2;cursor:pointer}"
            ".pk-chip{display:inline-block;background:#eef6d8;border-radius:12px;padding:2px 9px;margin:2px;font-size:12px}"
            ".pk-chip a{text-decoration:none;margin-left:4px}</style>"
            "<label>1 · Find the creators</label>"
            "<div class='row'><div style='flex:3'><input id='pk-q' placeholder='Search by name, @handle, code or city' autocomplete='off'></div>"
            "<div><select id='pk-pl'><option value=''>Any platform</option>"
            + "".join("<option>%s</option>" % e(p) for p in platforms) + "</select></div>"
            "<div><select id='pk-src'><option value=''>Whole roster</option>"
            + "".join("<option value='%s'>%s</option>" % (e(v), e(l)) for v, l in sources) + "</select></div></div>"
            "<div class='row' style='margin-top:8px'><div><label>Analysis for</label><select id='pk-ap'><option value=''>Each creator's main platform</option>"
            "<option>Instagram</option><option>TikTok</option><option>Snapchat</option><option>YouTube</option></select></div>"
            "<div style='align-self:flex-end'><label class='tick'><input type='checkbox' id='pk-no'> Only creators still without that analysis</label></div></div>"
            "<div class='muted' id='pk-count' style='margin:4px 0'></div><div class='pk-list' id='pk-list'></div>"
            "<div style='margin:8px 0'><button type='button' class='btn tiny ghost' id='pk-all'>Add all</button> "
            "<button type='button' class='btn tiny ghost' id='pk-clear'>Clear chosen</button></div>"
            "<details style='margin:8px 0'><summary>Or paste a list of handles, profile links or names</summary>"
            "<textarea id='pk-list-in' placeholder='One per line — @handle, instagram.com/handle, or a name' style='min-height:90px;margin-top:8px'></textarea>"
            "<button type='button' class='btn tiny ghost' id='pk-paste'>Add these</button> <span class='muted' id='pk-pmsg'></span></details>"
            "<form method='post' action='" + u("/analysis/template") + "'>"
            "<input type='hidden' name='source' value='codes'><input type='hidden' name='codes' id='pk-codes'><input type='hidden' name='platform' id='pk-apf'>"
            "<div style='margin:10px 0 4px'><strong id='pk-n'>0</strong> chosen <span id='pk-chips'></span></div>"
            "<button class='btn small' id='pk-dl' disabled>Download sheet for the chosen creators (.xlsx)</button> "
            "<a class='btn small ghost' href='" + u("/analysis/template.xlsx") + "'>Blank template</a></form>"
            "<script>" + _PICKER_JS.replace("%BASE%", BASE) + "</script>")


def analysis_review_page(kind, token, items, matched, creators, res, error=None, message=None):
    """Upload held until the admin says who each unrecognised name is."""
    opts = "".join("<option value=\"%s\">" % e(res.describe(c["code"])) for c in creators)
    what = "name in the spreadsheet" if kind == "xlsx" else "PDF file"
    rows = ""
    for i, (key, sug, pre) in enumerate(items):
        rows += ("<tr><td><input type='hidden' name='key_%d' value=\"%s\"><strong>%s</strong>%s</td><td>"
                 "<input name='pick_%d' list='rv-creators' value=\"%s\" placeholder='Type a name, handle or code — empty skips' "
                 "autocomplete='off' style='width:100%%'>%s</td></tr>") % (
            i, e(key), e(key), "" if kind == "xlsx" else "", i, e(pre),
            ("<div style='margin-top:6px;display:flex;flex-wrap:wrap;gap:6px;align-items:center'><span class='muted'>Click the right one:</span>" + "".join(
                "<a href='#' class='btn tiny ghost' onclick=\"this.closest('td').querySelector('input').value=this.dataset.v;return false\" "
                "data-v=\"%s\">%s</a>" % (e(x), e(x)) for x in sug) + "</div>") if sug else
            "<div class='muted' style='margin-top:4px'>No close match in the roster.</div>")
    lead = ("%d creator%s matched and ready. " % (matched, "" if matched == 1 else "s") if kind == "xlsx" else "")
    n = len(items)
    body = (ui.header("Who is this?", lead + "%d %s%s can't be matched on its own. Pick the creator, or leave it empty to skip."
                      % (n, what, "" if n == 1 else "s"),
                      crumbs=[("Library", None), ("Creator analysis", "/analysis"), ("Review", None)])
            + _notes(error, message)
            + "<form method='post' action='" + u("/analysis/review") + "' class='card'>"
              "<input type='hidden' name='t' value='" + e(token) + "'>"
              + ("<div class='row'><div><label>Platform of these reports</label>" + _plat_select("platform", "Read it from each report") + "</div></div>" if kind == "pdf" else "")
              + "<datalist id='rv-creators'>" + opts + "</datalist>"
              "<table><thead><tr><th>" + ("As written" if kind == "xlsx" else "File") + "</th><th>Creator</th></tr></thead><tbody>"
            + rows + "</tbody></table>"
              "<label style='display:block;margin:12px 0'><input type='checkbox' name='remember' value='1' checked> "
              "Remember these, so the same name is recognised next time</label>"
              "<div class='savebar'><button class='btn small'>Save</button> "
              "<a class='btn small ghost' href='" + u("/analysis") + "'>Cancel</a></div></form>")
    return page("Review upload", body, "/analysis")


def _plat_select(name="platform", first="Each creator's main platform", cid=None, selected=""):
    import analysis as _an
    return ("<select name='" + name + "'" + (" id='" + cid + "'" if cid else "") + "><option value=''>" + e(first) + "</option>"
            + "".join("<option" + (" selected" if p == selected else "") + ">" + p + "</option>" for p in _an.PLATFORMS[:4])
            + "</select>")


def analysis_page(creators, have, requests, origin, q="", error=None, message=None, page_no=1, sources=(), platform=""):
    """`have` is {code: {platform: saved at}}: an analysis belongs to one platform."""
    import analysis as _an
    main = lambda code: next((_an.creator_platforms(c)[0] for c in creators if c["code"] == code), "Instagram")
    open_reqs = [r for r in requests if not r["handled_at"]]
    req_rows = "".join(
        "<tr><td><code>" + e(r["code"]) + "</code> " + e(r["creator_name"] or "") + "</td><td><b>"
        + e(r["platform"] or main(r["code"])) + "</b></td><td>" + e(r["code_label"] or "—")
        + "</td><td class='muted'>" + ago(r["at"]) + "</td><td>"
        + ("<span class='pill live'>uploaded</span>" if (r["platform"] or main(r["code"])) in have.get(r["code"], {})
           else "<span class='pill warn'>waiting</span>")
        + "</td><td><form method='post' action='" + u("/analysis/handled") + "'><input type='hidden' name='id' value='"
        + str(r["id"]) + "'><button class='btn tiny ghost'>Mark handled</button></form></td></tr>" for r in open_reqs)
    term = (q or "").strip().lower()
    shown = [c for c in creators if not term or term in (c["code"] + " " + c["name"]).lower()]

    def plat_cells(c):
        mine = have.get(c["code"], {})
        plats = list(_an.creator_platforms(c)) + [p for p in mine if p not in _an.creator_platforms(c)]
        out = ""
        for p in plats:
            if p in mine:
                out += ("<span class='pill live'>" + e(p) + " · " + ago(mine[p]) + "</span> ")
            else:
                out += "<span class='pill'>" + e(p) + " · none</span> "
        return out

    def actions(c):
        mine = have.get(c["code"], {})
        plats = list(_an.creator_platforms(c)) + [p for p in mine if p not in _an.creator_platforms(c)]
        first = next((p for p in plats if p in mine), plats[0])
        return ("<a class='btn tiny ghost' href='" + e(origin + "/creator/#c=" + c["code"] + "&p=" + first) + "' target='_blank' rel='noopener'>Preview</a> "
                + "".join("<a class='btn tiny ghost' href='" + u("/analysis") + "?q=" + e(c["code"]) + "&p=" + p + "#edit'>"
                          + ("Edit " if p in mine else "Add ") + e(p) + "</a> " for p in plats))
    rows = "".join(
        "<tr><td><code>" + e(c["code"]) + "</code></td><td>" + e(c["name"]) + "</td><td>" + plat_cells(c) + "</td><td>"
        + actions(c) + "</td></tr>" for c in shown[(page_no - 1) * PER_PAGE:page_no * PER_PAGE])
    editor = ""
    if term and len(shown) == 1:
        c = shown[0]
        mine = have.get(c["code"], {})
        plats = list(_an.creator_platforms(c)) + [p for p in mine if p not in _an.creator_platforms(c)]
        cur = _an.canon_platform(platform) or next((p for p in plats if p in mine), plats[0])
        tabs_ = "".join("<a class='btn tiny " + ("" if p == cur else "ghost") + "' href='" + u("/analysis") + "?q=" + e(c["code"]) + "&p=" + p + "#edit'>"
                        + e(p) + ("" if p in mine else " (none)") + "</a> " for p in plats)
        editor = ("<h2 id='edit'>Edit " + e(c["code"]) + " — " + e(c["name"]) + "</h2><div style='margin:0 0 10px'>" + tabs_ + "</div>"
                  "<form method='post' action='" + u("/analysis/save") + "' class='card'><input type='hidden' name='code' value='" + e(c["code"]) + "'>"
                  "<input type='hidden' name='platform' value='" + e(cur) + "'>"
                  "<label>" + e(cur) + " analysis as JSON</label><textarea name='json' id='an-json' style='min-height:260px;font-family:ui-monospace,monospace;font-size:12px'></textarea>"
                  "<div class='savebar'><button class='btn small'>Save " + e(cur) + " analysis</button></div></form>"
                  "<script>fetch('" + u("/analysis/json") + "?c=" + e(c["code"]) + "&p=" + e(cur) + "').then(r=>r.text()).then(t=>{document.getElementById('an-json').value=t});</script>"
                  + ("<form method='post' action='" + u("/analysis/delete") + "' onsubmit=\"return confirm('Remove this analysis?')\">"
                     "<input type='hidden' name='code' value='" + e(c["code"]) + "'><input type='hidden' name='platform' value='" + e(cur) + "'>"
                     "<button class='btn small danger'>Remove " + e(cur) + " analysis</button></form>" if cur in mine else ""))
    body = (
        ui.header("Creator analysis", "Full profile analyses clients open from the catalogue and reports — one per platform. A platform without one shows a locked tab with Request analysis; requests land below.", crumbs=[("Library", None), ("Creator analysis", None)])
        + _notes(error, message)
        + "<div class='card' id='pdf'><div class='hd'><h2>Option A · Drop profile report PDFs</h2></div>"
          "<p class='sec-desc'>Drop one or many report PDFs. Each is read and saved as that creator's analysis for the platform the report is about "
          "(read from the report, or set below), with their photo and post covers. The creator is found from the handle in the file name "
          "(<code>report-handle-Oct-06-2026.pdf</code>), their profile links or a handle printed on the report; anything that cannot be matched "
          "comes up on a review screen where you pick the creator — nothing is refused.</p>"
          "<form method='post' action='" + u("/analysis/pdf") + "' enctype='multipart/form-data'>"
          + _dropzone("pdf-file", "file", "application/pdf,.pdf", True, "Drop PDF reports here or click to choose")
          + "<div class='row'><div><label>Platform of these reports</label>" + _plat_select("platform", "Read it from each report") + "</div>"
            "<div><label>Creator (only when uploading a single file)</label>"
            "<input name='code' list='an-creators' placeholder='Type a name, handle or code' autocomplete='off'></div></div>"
          "<datalist id='an-creators'>" + "".join("<option value=\"%s\">%s</option>" % (e(c["code"]), e(c["name"])) for c in creators) + "</datalist>"
          "<button class='btn lime'>" + ui.icon("upload", 15) + " Import</button></form></div>"
        + "<div class='card' id='prefilled'><div class='hd'><h2>Option B · Numbers in a spreadsheet</h2></div>"
          "<p class='sec-desc'>Step 1 — search and tick the creators you have numbers for (as many as you like), choose the platform, then download "
          "a sheet with them already filled in, so you never type a code. Step 2 — type the numbers and upload it. "
          "The creator is recognised from the code, <strong>@handle</strong>, profile link or name in the first column — "
          "or from the handle/link in the Overview row — and anything unclear is asked about before saving. "
          "A workbook can hold the same creator on several platforms: give each row its Platform.</p>"
          + _creator_picker(sources, sorted({c["platform"] for c in creators if c["platform"]}))
          + "<hr style='border:0;border-top:1px solid #e6e1d6;margin:16px 0'>"
          "<form method='post' action='" + u("/analysis/upload") + "' enctype='multipart/form-data'>"
          "<label>2 · Upload it filled in</label>"
          + _dropzone("xlsx-file", "file", ".xlsx", False, "Drop the filled-in workbook here or click to choose")
          + "<p class='price-hint'>Rows with only the creator filled in are ignored. Uploading a creator's platform again replaces "
            "that platform's analysis and closes its open requests.</p>"
            "<button class='btn small'>Upload analyses</button></form></div>"
        + "<h2>Requests from clients</h2><div class='card'><table><thead><tr><th>Creator</th><th>Platform</th><th>Client</th><th>Asked</th>"
          "<th>Status</th><th></th></tr></thead><tbody>" + (req_rows or "<tr><td colspan='6' class='muted'>No open requests.</td></tr>")
        + "</tbody></table></div>"
        + editor
        + "<h2>Creators</h2><form class='card' method='get' action='" + u("/analysis") + "'><div class='row'>"
          "<div style='flex:3'><input name='q' value='" + e(q) + "' placeholder='Search by code or name'></div>"
          "<div><button class='btn small'>Search</button></div></div></form>"
        + "<div class='card'><table><thead><tr><th>Code</th><th>Name</th><th>Analysis by platform</th><th></th></tr></thead><tbody>"
        + (rows or "<tr><td colspan='4' class='muted'>No creators match.</td></tr>") + "</tbody></table>"
        + pager(len(shown), page_no, "/analysis", q=q) + "</div>")
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


# Saving a form reloads the page; without this the admin lands at the top and
# scrolls back down to where they were, after every save. The position is
# kept for the same page only, for a minute, and a link to a #row wins.
SCROLL_JS = """<script>
(function(){
  var key = 'hv-scroll:' + location.pathname;
  document.addEventListener('submit', function(){
    try { sessionStorage.setItem(key, JSON.stringify({y: window.scrollY, t: Date.now()})); } catch (e) {}
  }, true);
  var saved = null;
  try { saved = JSON.parse(sessionStorage.getItem(key) || 'null'); sessionStorage.removeItem(key); } catch (e) {}
  if (!saved || Date.now() - saved.t > 60000 || location.hash) return;
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
  var go = function(){ window.scrollTo(0, saved.y); };
  if (document.readyState === 'complete') go(); else window.addEventListener('load', go);
  document.addEventListener('DOMContentLoaded', go);
})();
</script>"""


HISTORY_KINDS = [("", "Everything"), ("trash", "Trash (deleted)"), ("creator", "Creators"),
                 ("campaign", "Campaigns"), ("selection", "Selections"), ("code", "Access codes"),
                 ("tiers", "Tiers"), ("roster", "Roster imports")]


def history_page(rows, later, kind=None, q=None, message=None, error=None, page_no=1):
    note = ""
    if error:
        note += "<div class='err'>" + e(error) + "</div>"
    if message:
        note += "<div class='ok'>" + e(message) + "</div>"
    tabs = "".join(
        "<a class='btn small" + ("" if (kind or "") == v else " ghost") + "' href='" + u("/history")
        + ("?" + urlencode(kind=v) if v else "") + "'>" + e(l) + "</a>" for v, l in HISTORY_KINDS)
    verbs = {"created": "Created", "edited": "Edited", "deleted": "Deleted", "undo": "Undo"}
    out = []
    total = len(rows)
    for r in rows[(page_no - 1) * PER_PAGE:page_no * PER_PAGE]:
        done = r["undone_at"] is not None
        state = ("<span class='pill dead'>undone " + ago(r["undone_at"]) + "</span>") if done else ""
        n = later.get(r["id"], 0)
        warn = (" It will also take back " + str(n) + " later change" + ("" if n == 1 else "s")
                + " to the same item.") if n else ""
        btn = "" if done else (
            "<form method='post' action='" + u("/history/undo") + "' class='inline' onsubmit=\"return confirm('"
            + e(("Undo: " + (r["label"] or "") + "?" + warn).replace("'", "’")) + "')\">"
            "<input type='hidden' name='id' value='" + str(r["id"]) + "'>"
            "<input type='hidden' name='kind' value='" + e(kind or "") + "'>"
            "<button class='btn small" + ("" if r["action"] == "deleted" else " ghost") + "'>"
            + ("Restore" if r["action"] == "deleted" else "Redo" if r["action"] == "undo" else "Undo")
            + "</button></form>")
        out.append("<tr" + (" class='muted'" if done else "") + "><td class='muted'>" + ago(r["at"]) + "<br>"
                   + ts(r["at"]) + "</td><td><span class='pill " + ("dead" if r["action"] == "deleted" else "own")
                   + "'>" + e(verbs.get(r["action"], r["action"])) + "</span></td><td><strong>"
                   + e(r["label"] or r["entity"]) + "</strong> " + state + "<br><span class='muted'>"
                   + e(r["who"] or "") + "</span></td><td class='right'>" + btn + "</td></tr>")
    table = "".join(out) or "<tr><td colspan='4' class='muted'>Nothing here yet.</td></tr>"
    body = (
        ui.header("History & undo", "Every change made in the admin, newest first, kept for 90 days. Undo puts an item back exactly as it was before the change. An undo is listed too, so it can be taken back (redo).", crumbs=[("System", None), ("History & undo", None)])
        + note + "<div class='row' style='gap:8px;flex-wrap:wrap;margin:6px 0 14px'>" + tabs + "</div>"
        + "<form class='rsearch' method='get' action='" + u("/history") + "'>"
        + ("<input type='hidden' name='kind' value='" + e(kind) + "'>" if kind else "")
        + "<input name='q' value='" + e(q or "") + "' placeholder='Search by name or code' autocomplete='off'>"
        "<button class='btn small'>Search</button></form>"
        + "<div class='card'><table><thead><tr><th>When</th><th>What</th><th>Item</th><th></th></tr></thead><tbody>"
        + table + "</tbody></table></div>" + pager(total, page_no, "/history", kind=kind or "", q=q or ""))
    return page("History", body, "/history")


# ---------------------------------------------------------------- planner --

PLAN_LABEL = {"posts": "Posts", "views": "Views", "reach": "Reach", "engagement": "Engagement",
              "er": "Eng. rate % (of views)", "clicks": "Link clicks"}


def _fmt(key, v):
    if v is None:
        return "—"
    return ("%.2f%%" % v) if key == "er" else format(int(v), ",")


def planner_page(k, brief, plan, house, lib, error=None, message=None):
    """Goals & ROI: a brief in, the benchmark, the value floor for the budget,
    the safe and expected estimates and the targets to agree out. Works for
    a campaign (its booked creators) or on its own, for a pitch."""
    import plans
    q = (lambda key, d="": e(brief.get(key, d) if brief.get(key) is not None else d))
    opt = lambda items, cur: "".join("<option value='" + e(v) + "'" + (" selected" if v == cur else "") + ">"
                                     + e(l) + "</option>" for v, l in items)
    tpl_opts = "<option value=''>— none —</option>" + opt([(key, t["label"]) for key, t in plans.TEMPLATES.items()],
                                                          brief.get("template") or "")
    obj_opts = opt([("awareness", "Awareness"), ("engagement", "Engagement"), ("traffic", "Conversion (visits and sales)"),
                    ("balanced", "Balanced")], plan["objective"])
    plat_opts = opt([(p, p) for p in plans.PLATFORMS], plan["platform"])
    cat_opts = opt([(key, v[0]) for key, v in plans.CATEGORIES.items()], plan["category"])
    use_campaign = bool(k) and brief.get("source") != "tiers"
    tiers_in = "".join("<div><label>" + e(plans.TIER_LABEL[t]) + " — posts</label><input name='n_" + t
                       + "' inputmode='numeric' value='" + q("n_" + t) + "'" + (" disabled" if use_campaign else "")
                       + "></div>" for t in plans.TIERS)
    src = ""
    if k:
        src = ("<div class='ticks' style='margin:6px 0 10px'>"
               "<label class='tick'><input type='radio' name='source' value='campaign'" + (" checked" if use_campaign else "")
               + " onchange='this.form.submit()'><span>Use this campaign's booked creators</span></label>"
               "<label class='tick'><input type='radio' name='source' value='tiers'" + ("" if use_campaign else " checked")
               + " onchange='this.form.submit()'><span>Plan by posts per tier</span></label></div>")
    form = ("<form method='get' action='" + u("/planner") + "' class='card'>"
            + ("<input type='hidden' name='id' value='" + str(k["id"]) + "'>" if k else "")
            + "<div class='row'><div style='flex:2'><label>Start from a template</label><select name='template' "
              "onchange=\"this.form.querySelector('[name=apply_template]').value='1';this.form.submit()\">" + tpl_opts + "</select>"
              "<input type='hidden' name='apply_template' value=''></div>"
              "<div><label>Objective</label><select name='objective'>" + obj_opts + "</select></div>"
              "<div><label>Main platform</label><select name='platform'>" + plat_opts + "</select></div>"
              "<div><label>Product category</label><select name='category'>" + cat_opts + "</select></div></div>"
            + "<div class='row'><div><label>Client budget — what the client pays (SAR, before VAT)</label>"
              "<input name='budget' inputmode='numeric' value='" + q("budget") + "' placeholder='e.g. 25000'></div>"
              "<div><label>Tracked links</label><select name='links'>" + opt([("", "No affiliate links"), ("1", "Yes — each creator has a link")],
                                                                              "1" if plan["links"] else "") + "</select></div></div>"
            + src + "<div class='row'>" + tiers_in + "</div>"
            + "<button class='btn'>Calculate</button></form>")

    house_p = house.get(plan["platform"]) or {}
    bm = plan.get("benchmark") or {}
    def bench(key):
        if key == "views" and bm.get("view_rate"):
            return "%g–%g%% of followers per video" % tuple(bm["view_rate"])
        if key == "reach":
            return "≈ %d%% of views" % round((bm.get("reach_per_view") or 0.85) * 100)
        if key in ("engagement", "er") and bm.get("eng_rate"):
            return "%g–%g%% of views" % tuple(bm["eng_rate"])
        if key == "clicks" and bm.get("ctr"):
            return "%g–%g%% of views" % tuple(bm["ctr"])
        return ""
    def ours(key):
        if not house_p.get("posts"):
            return "<span class='muted'>no data yet</span>"
        if key == "views" and house_p.get("view_rate") is not None:
            return "%.1f%% of followers <span class='muted'>(%d videos)</span>" % (house_p["view_rate"], house_p["posts"])
        if key in ("engagement", "er") and house_p.get("eng_rate") is not None:
            return "%.2f%% of views" % house_p["eng_rate"]
        return "<span class='muted'>—</span>"
    est_s, est_x, fl, tgt = plan["estimate"]["safe"], plan["estimate"]["expected"], plan["floor"], plan["target"]
    rows = ""
    for key in ("posts", "views", "reach", "engagement", "er", "clicks"):
        if key not in tgt and key not in est_s:
            continue
        lead = key in plan["primary"]
        chk = next((c for c in plan["checks"] if c["key"] == key), None)
        flag = ""
        if chk:
            flag = (" <span class='pill live'>clears value</span>" if chk["ok"]
                    else " <span class='pill warn'>below value</span>")
        rows += ("<tr" + (" class='rec-lead'" if lead else "") + "><td><strong>" + e(PLAN_LABEL[key]) + "</strong>"
                 + (" <span class='pill own'>headline</span>" if lead else "") + "</td>"
                 + "<td class='right'>" + _fmt(key, fl.get(key)) + "</td>"
                 + "<td class='right'>" + _fmt(key, est_s.get(key)) + flag + "</td>"
                 + "<td class='right muted'>" + _fmt(key, est_x.get(key)) + "</td>"
                 + "<td class='right'><input form='apply' name='target_" + key + "' value='"
                 + e(tgt.get(key) if tgt.get(key) is not None else "") + "' inputmode='decimal' style='width:120px;text-align:right'></td>"
                 + "<td class='muted' style='font-size:12px'>" + bench(key) + "</td>"
                 + "<td style='font-size:12px'>" + ours(key) + "</td></tr>")
    roi = plan.get("roi") or {}
    roi_html = ""
    if roi:
        c = roi["ceilings"]
        def line(lbl, key):
            if not c.get(key) or roi["safe"].get(key) is None:
                return ""
            v = roi["safe"][key]
            gr = "live" if v <= c[key][1] else ("warn" if v <= c[key][0] else "dead")
            word = {"live": "strong value", "warn": "fair value", "dead": "poor value"}[gr]
            return ("<tr><td>" + lbl + "</td><td class='right'><strong>SAR %.2f</strong></td><td class='right muted'>SAR %.2f</td>"
                    "<td class='right muted'>≤ %g good · ≤ %g acceptable</td><td><span class='pill %s'>%s</span></td></tr>"
                    % (v, roi["expected"][key] or 0, c[key][1], c[key][0], gr, word))
        roi_html = ("<h2>Return on the budget</h2><div class='card'><table><thead><tr><th>Cost per result</th>"
                    "<th class='right'>At the safe estimate</th><th class='right'>At expected</th><th class='right'>Ceiling</th><th></th></tr></thead><tbody>"
                    + line("Per 1,000 views (CPM)", "cpm") + line("Per engagement", "cpe") + line("Per link click", "cpc")
                    + "</tbody></table><p class='price-hint'>The ceiling is the most a client should pay per result for the campaign "
                      "to be fair value. The value floor in the table above is the budget divided by that ceiling.</p></div>")
    tiers = plan.get("tiers") or {}
    tier_rows = "".join("<tr><td>" + e(plans.TIER_LABEL[t]) + "</td><td class='right'>" + str(tiers[t]["posts"])
                        + "</td><td class='right'>" + _fmt("views", tiers[t]["views"][0]) + "</td><td class='right muted'>"
                        + _fmt("views", tiers[t]["views"][1]) + "</td><td class='right'>" + _fmt("engagement", tiers[t]["engagement"][0])
                        + "</td></tr>" for t in plans.TIERS if t in tiers)
    saved = json.dumps(plan)
    apply = ""
    if k:
        apply = ("<form method='post' action='" + u("/planner/apply") + "' id='apply' class='savebar'>"
                 "<input type='hidden' name='id' value='" + str(k["id"]) + "'>"
                 "<input type='hidden' name='objective' value='" + e(plan["objective"]) + "'>"
                 "<input type='hidden' name='template' value='" + e(brief.get("template") or "") + "'>"
                 "<input type='hidden' name='plan' value='" + e(saved) + "'>"
                 "<button class='btn'>Save as this campaign's goals</button>"
                 "<span class='price-hint' style='margin-left:12px'>Saves the targets (edit any figure first), the objective "
                 "and the benchmark the client sees on Goals. The budget and costs stay internal.</span></form>")
    else:
        apply = "<form id='apply'></form><p class='price-hint'>Open the planner from a campaign to save these as its goals.</p>"
    notes = "".join("<li>" + e(n) + "</li>" for n in plan["notes"])
    lib_json = json.dumps(lib, indent=1, ensure_ascii=False)
    body = ((_head(k, "plan", error, message) if k else ui.header("ROI planner", "Price a pitch from a budget before a campaign exists.", crumbs=[("Insights", None), ("ROI planner", None)]) + _notes(error, message))
            + "<div class='card' style='background:#fff8ec;border-color:#f3d9a8'><strong>The ROI calculator is the main tool now.</strong> "
              "It does everything on this page and also measures real selections and campaigns. "
              "<a href='" + u("/calculator") + ("?id=" + str(k["id"]) if k else "") + "'>Open the calculator</a>. "
              "This older page stays for editing the <a href='#library'>benchmark library</a>.</div>"
            + "<p class='price-hint'>Brief in, numbers out. The target to agree is the <strong>minimum accepted</strong>: "
              "the lower of what the budget must buy to be fair value and what the creators can safely deliver — "
              "so we commit to it and beat it.</p>"
            + form
            + "<h2>Targets</h2><div class='card'><table><thead><tr><th>KPI</th><th class='right'>Value floor<br><small>budget ÷ ceiling</small></th>"
              "<th class='right'>Safe estimate</th><th class='right'>Expected</th><th class='right'>Target to agree</th>"
              "<th>Industry guide</th><th>HelloVoice past campaigns</th></tr></thead><tbody>" + rows + "</tbody></table>"
            + ("<ul class='price-hint' style='margin-top:10px'>" + notes + "</ul>" if notes else "") + "</div>"
            + apply + roi_html
            + ("<h2>By creator size</h2><div class='card'><table><thead><tr><th>Tier</th><th class='right'>Posts</th>"
               "<th class='right'>Views, safe</th><th class='right'>Views, expected</th><th class='right'>Engagement, safe</th></tr></thead><tbody>"
               + tier_rows + "</tbody></table></div>" if tier_rows else "")
            + "<h2>How the numbers are worked out</h2><div class='card price-hint' style='font-size:13px;line-height:1.6'>"
              "<p><strong>Views</strong> = each creator's followers × the view rate for their size (safe / expected) × posts. "
              "<strong>Reach</strong> = views × unique-viewer share. <strong>Engagement</strong> = views × engagement rate, "
              "adjusted for the product category. <strong>Clicks</strong> = views × click-through, only with tracked links.</p>"
              "<p><strong>Value floor</strong> = budget ÷ the most a client should pay per 1,000 views, per engagement or per click. "
              "<strong>Target</strong> = the lower of the floor and the safe estimate.</p>"
              "<p><strong>Creator score</strong> on the report (0–100) rewards the results each creator delivered, as a share of the best creator's result: "
              "awareness: views &amp; reach 70, engagement 20, clicks 10 · engagement: 20 / 70 / 10 · traffic: 20 / 20 / 60 · balanced: 45 / 35 / 20. "
              "With no tracking links the clicks part is dropped and the others scale up to 100. Nothing is compared with followers or outside benchmarks.</p></div>"
            + benchmark_refs()
            + "<details id='library' style='margin-top:20px'><summary><strong>Benchmark library</strong> — edit the guide ranges</summary>"
              "<form method='post' action='" + u("/planner/library") + "' class='card' style='margin-top:10px'>"
              + ("<input type='hidden' name='back' value='" + str(k["id"]) + "'>" if k else "")
              + "<p class='price-hint'>Per platform: view_rate and eng_rate per tier as [safe, expected] %; ctr [safe, expected] %; "
                "cpm, cpe, cpc as [acceptable, good] SAR ceilings; reach_per_view 0–1. Save with your own numbers once "
                "campaigns give us better ones.</p>"
              "<textarea name='library' rows='22' style='font-family:ui-monospace,monospace;font-size:12px'>" + e(lib_json) + "</textarea>"
              "<div class='savebar'><button class='btn small'>Save library</button>"
              "<button class='btn small ghost' name='reset' value='1'>Reset to defaults</button></div></form></details>")
    return page(("%s — Goals & ROI" % k["name"]) if k else "ROI planner", body, "/campaigns")


# ------------------------------------------------------------- calculator --

def benchmark_refs(open_=False):
    """'Where these numbers come from': published references per platform and
    the source links. Same list as the Benchmarks Pack's Sources page."""
    import plans
    cols = "".join("<div><h3>" + e(p) + "</h3><ul class='refs'>" + "".join("<li>" + e(r) + "</li>" for r in rs) + "</ul></div>"
                   for p, rs in plans.REFERENCES.items())
    srcs = "".join("<li><a href='" + e(url) + "' target='_blank' rel='noopener'>" + e(t) + "</a></li>" for t, url in plans.SOURCES)
    return ("<details class='card refbox'" + (" open" if open_ else "") + "><summary><strong>Where these numbers come from</strong>"
            " <span class='muted'>published references behind the guide ranges</span></summary>"
            "<p class='sec-desc'>The planning ranges are HelloVoice's own, set at the low end of these published reports for the Saudi market, "
            "and updated as our tracked campaigns add data. Every rate is a guide, not a promise.</p>"
            "<div class='refgrid'>" + cols + "</div><h3>Sources</h3><ol class='src'>" + srcs + "</ol></details>")


def objective_weights_card():
    """Reference: how each campaign objective weights the creator score. Read
    from metrics.OBJECTIVES so it can never drift from the real scoring."""
    import metrics
    rows = "".join("<tr><td><strong>" + e(lbl) + "</strong></td><td class='right'>%d%%</td><td class='right'>%d%%</td><td class='right'>%d%%</td></tr>"
                   % (round(w[0] * 100), round(w[1] * 100), round(w[3] * 100)) for lbl, w in [v for _, v in metrics.TEMPLATES])
    return ("<details class='card refbox'><summary><strong>How the campaign objective weights the score</strong>"
            " <span class='muted'>templates — editable per campaign</span></summary>"
            "<p class='sec-desc'>On the campaign's Setup page, pick an objective template and it fills in these percentages; change any of them to make it your own. "
            "They decide how much each result counts when creators are scored, each as a share of the best creator's result. Mixed campaign? Choose Balanced.</p>"
            "<table><thead><tr><th>Objective</th><th class='right'>Views &amp; reach</th><th class='right'>Engagement</th><th class='right'>Clicks</th></tr></thead><tbody>"
            + rows + "</tbody></table>"
            "<p class='price-hint'>No tracking links on the campaign? The clicks share is dropped and the other two scale up to 100%. "
            "Nothing is compared with followers or outside benchmarks.</p></details>")


def calculator_page(lib, sources=None, initial=None, ok=None, error=None):
    """The ROI calculator. Pick one or several campaign types and one or
    several platforms, type what the client pays (split between platforms),
    and read what result to accept. Everything is worked out in the browser
    from the benchmark library (editable on the ROI planner), so it can
    never disagree with it."""
    import plans
    data = json.dumps({"lib": lib, "tiers": plans.TIERS, "tierLabel": plans.TIER_LABEL, "followers": plans.TIER_FOLLOWERS,
                       "sources": sources or {"selections": [], "campaigns": []}, "initial": initial or "", "base": BASE,
                       "categories": {k: v[0] for k, v in plans.CATEGORIES.items()}},
                      ensure_ascii=False).replace("</", "<\\/")
    body = """
""" + _notes(error, ok) + ui.header("ROI calculator", "Pick campaign types and platforms, type what the client pays, and read the result to accept. Numbers come from the benchmark library.", crumbs=[("Insights", None), ("ROI calculator", None)], actions="<a class='btn ghost' href='" + u("/planner") + "#library'>Benchmark library</a>") + objective_weights_card() + benchmark_refs() + """
<style>
.cal-pills{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
.cal-pills button{font:inherit;font-weight:600;border:1px solid var(--line);background:#fff;border-radius:999px;padding:9px 18px;cursor:pointer;display:inline-flex;align-items:center;gap:8px}
.cal-pills button::before{content:"";width:14px;height:14px;border-radius:4px;border:1.5px solid #999;flex:none}
.cal-pills button[aria-pressed=true]{background:var(--ink,#121212);color:#e8ff76;border-color:var(--ink,#121212)}
.cal-pills button[aria-pressed=true]::before{background:#e8ff76 url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 14 14'%3E%3Cpath d='M3 7.5l2.6 2.6L11 4.5' fill='none' stroke='%23121212' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E") center/100% no-repeat;border-color:#e8ff76}
.cal-types button{padding:12px 22px;text-align:left;border-radius:16px}
.cal-types button span small{display:block;font-weight:400;font-size:12px;opacity:.75;margin-top:2px}
.cal-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start}
@media(max-width:900px){.cal-grid{grid-template-columns:1fr}}
.cal-h{display:flex;align-items:center;gap:10px;margin:0 0 4px;flex-wrap:wrap}
.cal-h h2{margin:0}
.cal-q{font-size:14px;margin:4px 0 12px}
.cal-meter{display:flex;height:16px;border-radius:999px;overflow:hidden;margin:2px 0 6px}
.cal-meter i{display:block}
.cal-r{background:#e5484d}.cal-a{background:#f2a33a}.cal-g{background:#1f9d55}
.cal-keys{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.cal-key{border-left:4px solid;border-radius:10px;padding:8px 10px}
.cal-key span{display:block;font-size:11px;letter-spacing:.08em;text-transform:uppercase;font-weight:700}
.cal-key b{font-size:22px;line-height:1.1;display:block;color:#121212}
.cal-key small{font-size:11px;color:#666}
.cal-key--r{background:#fdeeee;border-color:#e5484d;color:#9b1c1f}
.cal-key--a{background:#fff4e3;border-color:#f2a33a;color:#8a4f06}
.cal-key--g{background:#e7f6ec;border-color:#1f9d55;color:#136b39}
.cal-sign{display:inline-flex;align-items:flex-end;gap:2px;height:14px;margin-left:4px;cursor:help;vertical-align:middle}
.cal-sign i{display:block;width:4px;border-radius:1px;background:#d9d5cc}
.cal-sign i:nth-child(1){height:5px}.cal-sign i:nth-child(2){height:9px}.cal-sign i:nth-child(3){height:13px}
.cal-sign--2 i:nth-child(-n+2){background:#e2780f}.cal-sign--1 i:nth-child(1){background:#ee1515}
.cal-sign em{font-style:normal;font-size:11px;font-weight:700;margin-left:6px;color:#666;line-height:13px}
.cal-why{font-size:12px;color:#666;margin:8px 0 0}
.cal-note{background:#fff8ec;border:1px solid #f3d9a8;border-radius:12px;padding:10px 12px;font-size:13px;margin-top:10px}
.cal-out{font-size:15px;line-height:1.5;margin-top:10px}
.cal-out b{font-size:22px}
.cal-v{display:inline-block;font-weight:700;border-radius:999px;padding:4px 12px;font-size:13px}
.cal-v--g{background:#e7f6ec;color:#136b39}.cal-v--a{background:#fff4e3;color:#8a4f06}.cal-v--r{background:#fdeeee;color:#9b1c1f}
.cal-tier{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
@media(max-width:700px){.cal-tier{grid-template-columns:repeat(2,1fr)}}
.cal-money{position:relative}.cal-money input{padding-right:52px}.cal-money span{position:absolute;right:12px;top:50%;transform:translateY(-50%);color:#777;font-size:13px}
.cal-split{display:flex;flex-wrap:wrap;gap:12px;margin-top:6px}
.cal-split>div{background:#f6f4f0;border-radius:12px;padding:10px 12px;min-width:150px}
.cal-split label{margin:0 0 4px;font-size:12px}
.cal-split .cal-money input{padding:8px 34px 8px 10px}
.cal-split small{display:block;margin-top:4px;color:#666;font-size:12px}
table.cal-t{width:100%;border-collapse:collapse;font-size:14px;margin-top:6px}
table.cal-t th{text-align:right;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#666;font-weight:700;padding:6px 10px}
table.cal-t th:first-child,table.cal-t td:first-child{text-align:left}
table.cal-t td{padding:9px 10px;border-top:1px solid #eee;text-align:right}
table.cal-t td b{font-size:17px}
table.cal-t .ok{background:#fff8ec}table.cal-t .gr{background:#eef8f1}
table.cal-t tr.tot td{border-top:2px solid #121212;font-weight:700}
table.cal-t .grp th{text-align:center;border-bottom:1px solid #ddd}
.cal-foc{max-width:380px;margin:0 0 12px}
.cal-big{font-size:18px;line-height:1.5;margin:6px 0}
.cal-in .cal-inrow{display:flex;flex-wrap:wrap;gap:14px 32px;align-items:flex-start;margin-bottom:12px}
.cal-in label{margin-bottom:4px}
.cal-tabs{display:flex;flex-wrap:wrap;gap:4px;border-bottom:2px solid #121212;margin:20px 0 16px}
.cal-tabs button{font:inherit;font-weight:700;border:0;background:transparent;padding:10px 16px;border-radius:12px 12px 0 0;cursor:pointer;color:#555}
.cal-tabs button:hover{background:#efede8;color:#121212}
.cal-tabs button[aria-selected=true]{background:#121212;color:#e8ff76}
.cal-ov{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;align-items:stretch}
@media(max-width:1000px){.cal-ov{grid-template-columns:1fr}}
.cal-ov>.card{display:flex;flex-direction:column;margin:0}
.cal-ovh{display:flex;gap:12px;align-items:center;margin-bottom:12px}
.cal-ovh h2{margin:0;font-size:19px}.cal-ovh small{color:#666;font-size:12px}
.cal-num{width:34px;height:34px;border-radius:50%;background:#121212;color:#e8ff76;display:grid;place-items:center;font-weight:700;flex:none}
.cal-more{margin-top:auto;align-self:flex-start;border:0;background:#efede8;font:inherit;font-weight:700;font-size:13px;padding:7px 14px;border-radius:999px;cursor:pointer}
.cal-more:hover{background:#e8ff76}
.cal-ov .cal-row{display:flex;justify-content:space-between;align-items:baseline;gap:10px;padding:9px 0;border-top:1px solid #eee;font-size:14px}
.cal-ov .cal-row:first-child{border-top:0}
.cal-ov .cal-row b{font-size:19px}
.cal-ov .cal-row small{display:block;color:#666;font-size:11.5px}
.cal-bigchip{display:inline-block;font-size:22px;font-weight:800;border-radius:999px;padding:8px 20px;margin-bottom:8px}
.cal-st{display:inline-block;font-weight:700;border-radius:999px;padding:3px 11px;font-size:12.5px;white-space:nowrap}
.cal-st--g{background:#e7f6ec;color:#136b39}.cal-st--a{background:#fff4e3;color:#8a4f06}.cal-st--r{background:#fdeeee;color:#9b1c1f}.cal-st--n{background:#eef2f7;color:#445}
.cal-bigchip.cal-st--g{background:#1f9d55;color:#fff}.cal-bigchip.cal-st--a{background:#e2780f;color:#fff}.cal-bigchip.cal-st--r{background:#e0241f;color:#fff}
.cal-stgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px;margin-top:12px}
.cal-stc{border:1px solid #eee;border-radius:14px;padding:12px 14px;background:#fff;display:grid;gap:6px}
.cal-stc h3{margin:0;font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:#666}
.cal-stc .nums{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.cal-stc .nums b{font-size:24px}.cal-stc .nums small{color:#666}
.cal-stc .bar{height:8px;border-radius:999px;background:#efece6;overflow:hidden}
.cal-stc .bar i{display:block;height:100%;border-radius:999px}
.cal-stc p{margin:0;font-size:12.5px;color:#666}
.cal-goalrow{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:10px 0}
.cal-goalrow label{font-size:12px}
.cal-saved{background:#e7f6ec;border-radius:10px;padding:8px 12px;font-size:13px;margin:8px 0}
.cal-big b{font-size:26px}
.cal-line{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:baseline;padding:8px 0;border-top:1px solid #eee}
.cal-line:first-of-type{border-top:0}
.cal-line em{font-style:normal;font-weight:700;min-width:130px}
table.cal-c{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}
table.cal-c th{text-align:left;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#666;padding:6px 8px;font-weight:700}
table.cal-c td{padding:8px;border-top:1px solid #eee;vertical-align:top}
table.cal-c td.r,table.cal-c th.r{text-align:right}
table.cal-c input{width:58px;padding:5px 6px;text-align:center}
.cal-prob{display:inline-block;font-size:12px;border-radius:8px;padding:2px 8px;margin:0 4px 4px 0}
.cal-prob--bad{background:#fdeeee;color:#9b1c1f}.cal-prob--warn{background:#fff4e3;color:#8a4f06}.cal-prob--info{background:#eef2f7;color:#445}
.cal-sum{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin:10px 0}
.cal-sum>div{background:#f6f4f0;border-radius:12px;padding:10px 12px}
.cal-sum span{display:block;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#666;font-weight:700}
.cal-sum b{font-size:22px;display:block;line-height:1.2}
</style>

<div class='card cal-in'>
  <div class='cal-inrow'>
    <div><label>What does the client want?</label><div class='cal-pills cal-types' id='cal-type'></div></div>
    <div><label>Platforms</label><div class='cal-pills' id='cal-plat'></div></div>
  </div>
  <div class='cal-inrow'>
    <div><label for='cal-budget'>Client pays (SAR, before VAT)</label>
    <div class='cal-money' style='width:230px'><input id='cal-budget' inputmode='numeric' value='35000' autocomplete='off'><span>SAR</span></div></div>
    <div style='flex:1;min-width:280px;max-width:560px'><label for='cal-source'>Selection or campaign <span class='muted' style='font-weight:400'>(optional: uses its real creators)</span></label>
    <select id='cal-source'><option value=''>none: just type the numbers</option></select>
    <div class='price-hint' id='cal-source-hint'></div></div>
  </div>
  <div id='cal-split-box' hidden>
    <label>How is the budget split between platforms?</label>
    <div class='cal-split' id='cal-split'></div>
    <div class='price-hint' id='cal-split-hint'></div>
  </div>
  <div id='cal-warn'></div>
</div>

<div class='cal-tabs' id='cal-tabs' role='tablist'>
  <button type='button' role='tab' data-tab='overview' aria-selected='true'>Overview</button>
  <button type='button' role='tab' data-tab='buy' aria-selected='false'>What the budget buys</button>
  <button type='button' role='tab' data-tab='targets' aria-selected='false'>Targets</button>
  <button type='button' role='tab' data-tab='actual' aria-selected='false'>Actual vs target</button>
  <button type='button' role='tab' data-tab='creators' aria-selected='false'>Creators</button>
  <button type='button' role='tab' data-tab='adjust' aria-selected='false'>Adjust results</button>
  <button type='button' role='tab' data-tab='tools' aria-selected='false'>Tools</button>
</div>

<div class='cal-panel' id='tab-overview'>
  <div class='cal-ov'>
    <div class='card'><div class='cal-ovh'><span class='cal-num'>1</span><div><h2>What the budget buys</h2><small>ROI: the results a fair deal should bring</small></div></div><div id='cal-ov-buy'></div><button type='button' class='cal-more' data-go='buy'>Details →</button></div>
    <div class='card'><div class='cal-ovh'><span class='cal-num'>2</span><div><h2>What should be achieved</h2><small>The targets to agree with the client</small></div></div><div id='cal-ov-target'></div><button type='button' class='cal-more' data-go='targets'>Details →</button></div>
    <div class='card'><div class='cal-ovh'><span class='cal-num'>3</span><div><h2>Where we are</h2><small>Actual results against those targets</small></div></div><div id='cal-ov-actual'></div><button type='button' class='cal-more' data-go='actual'>Details →</button></div>
  </div>
</div>
<div class='cal-panel' id='tab-buy' hidden><div id='cal-accept'></div></div>
<div class='cal-panel' id='tab-targets' hidden><div id='cal-goals'></div></div>
<div class='cal-panel' id='tab-actual' hidden><div id='cal-actual'></div></div>
<div class='cal-panel' id='tab-creators' hidden><div id='cal-check'></div>
<details class='card' style='margin-top:16px'>
  <summary><strong>Test a different mix</strong>: how many posts from each size of creator?</summary>
  <p class='price-hint'>Works on the platform chosen under Tools.</p>
  <div class='cal-tier' id='cal-tiers'></div>
  <div class='cal-out' id='cal-creators-out'></div>
</details></div>
<div class='cal-panel' id='tab-adjust' hidden><div id='cal-results'></div></div>
<div class='cal-panel' id='tab-tools' hidden>
<div id='cal-focus-box' hidden class='card' style='margin-bottom:16px'>
  <label for='cal-focus'>The tools below work on one choice at a time. Which one?</label>
  <select id='cal-focus' class='cal-foc'></select>
</div>
<div class='cal-grid'>
  <div class='card'>
    <h2 style='margin-top:0'>What should this cost?</h2>
    <p class='price-hint' style='margin:0 0 10px'>The client asks for a result. What is a fair price for it?</p>
    <label id='cal-target-lbl' for='cal-target'></label><input id='cal-target' inputmode='numeric' placeholder='e.g. 500000' autocomplete='off'>
    <div class='cal-out' id='cal-target-out'></div>
  </div>
  <div class='card'>
    <h2 style='margin-top:0'>Did it pay off?</h2>
    <p class='price-hint' style='margin:0 0 10px'>Type the total the client paid and what the campaign actually got. It says if the client got fair value.</p>
    <div class='row'>
      <div><label for='cal-paid'>Client paid (SAR)</label><input id='cal-paid' inputmode='numeric' autocomplete='off' placeholder='same as above'></div>
    </div>
    <div class='row'>
      <div><label id='cal-got1-lbl' for='cal-got1'></label><input id='cal-got1' inputmode='numeric' autocomplete='off'></div>
      <div><label id='cal-got2-lbl' for='cal-got2'></label><input id='cal-got2' inputmode='numeric' autocomplete='off'></div>
    </div>
    <div class='cal-out' id='cal-got-out'></div>
  </div>
</div>
</div>
<script>
(function(){
  var D = """ + data + """;
  var LIB = D.lib, TIERS = D.tiers;
  var TYPES = {
    awareness: {name: 'Awareness', sub: 'Many people see the brand', main: 'views', also: 'reactions'},
    engagement: {name: 'Engagement', sub: 'People like, comment and trust', main: 'reactions', also: 'views'},
    conversion: {name: 'Conversion', sub: 'Visits and sales', main: 'clicks', also: 'views'}
  };
  var TYPE_KEYS = Object.keys(TYPES);
  var PLATS = ['Instagram', 'TikTok', 'Snapchat', 'YouTube'];
  var NAME = {views: 'Views', reactions: 'Likes + comments', clicks: 'Clicks'};
  var SIGN = {2: ['Estimated', 'Our judgement, kept below published averages, and checked on one Saudi campaign so far.'],
              1: ['Rough hint', 'Very little data behind it: a starting point only, not a promise.']};
  var S = {types: ['awareness'], plats: ['Instagram'], share: {}, focus: '', src: '', posts: {}};
  var SRC = D.sources || {selections: [], campaigns: []};
  function $(i){return document.getElementById(i);}
  function num(v){return Math.round(v).toLocaleString('en-US');}
  function nice(v){return v>=1e6?(v/1e6).toFixed(1).replace(/\\.0$/,'')+'M':v>=1e4?Math.round(v/1e3)+'K':v>=1000?(v/1e3).toFixed(1).replace(/\\.0$/,'')+'K':num(v);}
  function money(v){return v>=100?num(v):(Math.round(v*10)/10).toString();}
  function readEl(el){var v=parseFloat(String(el.value).replace(/[^0-9.]/g,''));return isNaN(v)||v<=0?null:v;}
  function read(id){return readEl($(id));}
  // On Snapchat there are no likes: engagement is judged on views instead.
  function mainKind(t, p){ var m = TYPES[t].main; return (p === 'Snapchat' && m === 'reactions') ? 'views' : m; }
  function alsoKind(t, p){ var T = TYPES[t]; if (mainKind(t, p) !== T.main) return null; return T.also === T.main ? null : T.also; }
  // ceilings: the most the client should pay per result, [acceptable, great]
  function ceil(p, kind){
    var P = LIB[p];
    if (kind === 'views') return [P.cpm[0] / 1000, P.cpm[1] / 1000];   // SAR per view
    if (kind === 'reactions') return [P.cpe[0], P.cpe[1]];
    return [P.cpc[0], P.cpc[1]];
  }
  function sign(kind){
    var n = kind === 'clicks' ? 1 : 2, t = SIGN[n];
    return '<span class="cal-sign cal-sign--' + n + '" title="' + t[1] + '"><i></i><i></i><i></i><em>' + t[0] + '</em></span>';
  }
  function why(kind){ return kind === 'clicks' ? SIGN[1][1] : SIGN[2][1]; }
  function results(p, kind, budget){ var c = ceil(p, kind); return {ok: budget / c[0], great: budget / c[1]}; }
  function meter(kind, r){
    var ok = r.ok, gr = r.great, top = gr * 1.3, w1 = ok / top * 100, w2 = (gr - ok) / top * 100, u = NAME[kind].toLowerCase();
    return '<div class="cal-meter"><i class="cal-r" style="width:' + w1 + '%"></i><i class="cal-a" style="width:' + w2 + '%"></i><i class="cal-g" style="flex:1"></i></div>'
      + '<div class="cal-keys"><div class="cal-key cal-key--r"><span>Not OK</span><b>under ' + nice(ok) + '</b><small>' + u + '</small></div>'
      + '<div class="cal-key cal-key--a"><span>Accepted</span><b>' + nice(ok) + ' – ' + nice(gr) + '</b><small>' + u + '</small></div>'
      + '<div class="cal-key cal-key--g"><span>Great</span><b>' + nice(gr) + '+</b><small>' + u + '</small></div></div>';
  }
  function card(p, kind, budget, main){
    return '<div class="card"' + (main ? ' style="border:2px solid #121212"' : '') + '><div class="cal-h"><span class="pill' + (main ? ' live' : '') + '">' + (main ? 'Main result' : 'Also check') + '</span><h2>' + NAME[kind] + '</h2>' + sign(kind) + '</div>'
      + '<p class="cal-q">For SAR ' + num(budget) + ', the client should get</p>' + meter(kind, results(p, kind, budget)) + '<p class="cal-why">' + why(kind) + '</p></div>';
  }
  function verdict(cost, c){ return cost <= c[1] ? ['Great', 'g'] : cost <= c[0] ? ['Accepted', 'a'] : ['Not OK', 'r']; }

  // The budget split: equal by default, editable; shares are always read as
  // proportions, so they need not add to exactly 100.
  function shares(){
    var n = S.plats.length, out = {}, tot = 0;
    S.plats.forEach(function(p){ var v = S.share[p]; if (v == null) v = 100 / n; out[p] = v; tot += v; });
    S.plats.forEach(function(p){ out[p] = tot ? out[p] / tot : 1 / n; });
    return out;
  }
  function split(budget){
    var sh = shares(), out = {};
    S.plats.forEach(function(p){ out[p] = budget * sh[p]; });
    return out;
  }
  function combos(){ var out = []; S.types.forEach(function(t){ S.plats.forEach(function(p){ out.push({t: t, p: p, id: t + '|' + p}); }); }); return out; }
  function focus(){ var c = combos(); return c.filter(function(x){ return x.id === S.focus; })[0] || c[0]; }

  function tableFor(t, budget){
    var amt = split(budget), T = TYPES[t], tot = {main: 0, mainG: 0, also: 0, alsoG: 0}, mk = T.main, ak = T.also, rows = '', skipped = [];
    S.plats.forEach(function(p){
      var m = mainKind(t, p), a = alsoKind(t, p);
      if (m !== mk) { // Snapchat engagement: judged on views, not added to likes + comments
        var r0 = results(p, m, amt[p]);
        skipped.push('<tr><td>' + p + ' <span class="muted">· judged on views</span></td><td>' + num(amt[p]) + '</td><td class="ok"><b>' + nice(r0.ok) + '</b> views</td><td class="gr"><b>' + nice(r0.great) + '</b> views</td><td class="muted" colspan="2">no likes on Snapchat</td></tr>');
        return;
      }
      var r = results(p, m, amt[p]); tot.main += r.ok; tot.mainG += r.great;
      var ra = a ? results(p, a, amt[p]) : null; if (ra) { tot.also += ra.ok; tot.alsoG += ra.great; }
      rows += '<tr><td>' + p + '</td><td>' + num(amt[p]) + '</td><td class="ok"><b>' + nice(r.ok) + '</b></td><td class="gr"><b>' + nice(r.great) + '</b></td>'
        + (a ? '<td class="ok">' + nice(ra.ok) + '</td><td class="gr">' + nice(ra.great) + '</td>' : '<td></td><td></td>') + '</tr>';
    });
    var counted = S.plats.filter(function(p){ return mainKind(t, p) === mk; }).length;
    var totalRow = counted > 1 ? '<tr class="tot"><td>Total</td><td>' + num(budget) + '</td><td class="ok">' + nice(tot.main) + '</td><td class="gr">' + nice(tot.mainG) + '</td>'
      + (ak && tot.also ? '<td class="ok">' + nice(tot.also) + '</td><td class="gr">' + nice(tot.alsoG) + '</td>' : '<td></td><td></td>') + '</tr>' : '';
    var lead = [mk].concat(counted ? [ak] : []);
    return '<div class="card" style="margin-bottom:16px"><div class="cal-h"><span class="pill live">' + T.name + '</span><h2>' + NAME[mk] + '</h2>' + sign(mk) + '</div>'
      + '<table class="cal-t"><thead><tr class="grp"><th></th><th></th><th colspan="2">Main: ' + NAME[mk] + '</th><th colspan="2">Also check: ' + (ak ? NAME[ak] : '—') + '</th></tr>'
      + '<tr><th>Platform</th><th>Budget (SAR)</th><th>Accept at least</th><th>Great is</th><th>Accept at least</th><th>Great is</th></tr></thead><tbody>'
      + rows + skipped.join('') + totalRow + '</tbody></table><p class="cal-why">' + why(mk) + (skipped.length ? ' Snapchat shows no likes, so it is judged on views and not added to the total.' : '') + '</p></div>';
  }

  function render(){
    var budget = read('cal-budget'), multiP = S.plats.length > 1, multi = multiP || S.types.length > 1;
    document.querySelectorAll('#cal-type button').forEach(function(b){ b.setAttribute('aria-pressed', S.types.indexOf(b.dataset.k) >= 0 ? 'true' : 'false'); });
    document.querySelectorAll('#cal-plat button').forEach(function(b){ b.setAttribute('aria-pressed', S.plats.indexOf(b.dataset.k) >= 0 ? 'true' : 'false'); });
    // split boxes
    $('cal-split-box').hidden = !multiP;
    if (multiP) {
      var amt = budget ? split(budget) : {}, sh = shares();
      $('cal-split').innerHTML = S.plats.map(function(p){
        return '<div><label for="cal-s-' + p + '">' + p + '</label><div class="cal-money"><input id="cal-s-' + p + '" data-p="' + p + '" inputmode="numeric" value="' + Math.round(sh[p] * 100) + '"><span>%</span></div><small>' + (budget ? 'SAR ' + num(amt[p]) : '') + '</small></div>';
      }).join('');
      $('cal-split-hint').textContent = 'Equal split by default. Change a number to shift budget; they are always read as proportions.';
    }
    $('cal-warn').innerHTML = (S.types.length > 1) ? '<div class="cal-note">Each type below is worked out on the <b>full</b> budget: the same posts count for all of them, you do not pay twice.</div>' : '';
    // what to accept
    if (!budget) { $('cal-accept').innerHTML = '<div class="card"><p class="price-hint">Type what the client pays to see the results.</p></div>'; }
    else if (!multi) {
      var t = S.types[0], p = S.plats[0], m = mainKind(t, p), a = alsoKind(t, p);
      var note = (p === 'Snapchat' && TYPES[t].main === 'reactions') ? '<div class="cal-note" style="margin-bottom:12px">Snapchat does not show likes or comments, so for Engagement on Snapchat we judge on <b>views</b>.</div>' : '';
      $('cal-accept').innerHTML = note + '<div class="cal-grid">' + card(p, m, budget, true) + (a ? card(p, a, budget, false) : '') + '</div>';
    } else { $('cal-accept').innerHTML = S.types.map(function(t){ return tableFor(t, budget); }).join(''); }
    // tool focus
    var cs = combos(); if (!cs.some(function(x){ return x.id === S.focus; })) S.focus = cs[0].id;
    $('cal-focus-box').hidden = cs.length < 2;
    $('cal-focus').innerHTML = cs.map(function(x){ return '<option value="' + x.id + '"' + (x.id === S.focus ? ' selected' : '') + '>' + TYPES[x.t].name + ' · ' + x.p + '</option>'; }).join('');
    var fc = focus(), chk = check(fc, budget ? (split(budget)[fc.p] || budget) : null);
    goals(fc, budget ? (split(budget)[fc.p] || budget) : null, chk);
    resultsCard(fc, budget ? (split(budget)[fc.p] || budget) : null, chk);
    overview(budget, chk, fc);
    tools(budget);
  }
  function tools(totalBudget){
    var f = focus(), m = mainKind(f.t, f.p), a = alsoKind(f.t, f.p), c = ceil(f.p, m);
    // what should this cost
    $('cal-target-lbl').textContent = 'The client wants this many ' + NAME[m].toLowerCase();
    var T = read('cal-target');
    $('cal-target-out').innerHTML = T ? 'Fair price: <b>up to SAR ' + num(T * c[0]) + '</b><br><span class="cal-v cal-v--g">Great deal at SAR ' + num(T * c[1]) + ' or less</span>' : '<span class="price-hint">Type a number to see the price.</span>';
    // did it pay off — on the total paid for this choice
    var paid = read('cal-paid') || (totalBudget ? (split(totalBudget)[f.p] || totalBudget) : null);
    var kinds = a ? [m, a] : [m];
    $('cal-got1-lbl').textContent = NAME[kinds[0]] + ' got';
    $('cal-got2-lbl').textContent = kinds[1] ? NAME[kinds[1]] + ' got' : '';
    $('cal-got2').parentNode.style.visibility = kinds[1] ? 'visible' : 'hidden';
    var out = '', ids = ['cal-got1', 'cal-got2'];
    kinds.forEach(function(k, i){
      var g = read(ids[i]); if (!g || !paid) return;
      var cc = ceil(f.p, k), cost = paid / g, v = verdict(cost, cc);
      var per = k === 'views' ? 'SAR ' + money(cost * 1000) + ' per 1,000 views' : 'SAR ' + money(cost) + ' per ' + (k === 'clicks' ? 'click' : 'like or comment');
      out += '<div style="margin-top:6px"><span class="cal-v cal-v--' + v[1] + '">' + v[0] + '</span> ' + NAME[k] + ': ' + per + '</div>';
    });
    $('cal-got-out').innerHTML = out || '<span class="price-hint">Type the results to see the verdict.</span>';
    creators(totalBudget ? (split(totalBudget)[f.p] || totalBudget) : null, f);
  }
  function creators(budget, f){
    var P = LIB[f.p], m = mainKind(f.t, f.p), v = [0, 0], e = [0, 0], k = [0, 0], n = 0;
    TIERS.forEach(function(t){
      var c = parseInt($('cal-t-' + t).value, 10) || 0; if (!c) return; n += c;
      for (var i = 0; i < 2; i++) { var views = D.followers[t] * P.view_rate[t][i] / 100 * c; v[i] += views; e[i] += views * P.eng_rate[t][i] / 100; k[i] += views * P.ctr[i] / 100; }
    });
    if (!n) { $('cal-creators-out').innerHTML = '<span class="price-hint">Enter how many posts to compare.</span>'; return; }
    var est = m === 'views' ? v : m === 'reactions' ? e : k, name = NAME[m].toLowerCase();
    var line = '<b>' + nice(est[0]) + ' – ' + nice(est[1]) + '</b> ' + name + ' from ' + n + (n === 1 ? ' post' : ' posts') + ' on ' + f.p + ' (usual – good result)';
    if (budget) {
      var ok = results(f.p, m, budget).ok, good = est[0] >= ok;
      line += '<br><span class="cal-v cal-v--' + (good ? 'g' : 'r') + '">' + (good ? 'They can deliver the accepted result' : 'Probably short of the accepted result') + '</span> '
        + 'Accepted for SAR ' + num(budget) + ' is ' + nice(ok) + '. ' + (good ? '' : 'Add more creators (small and medium ones give the most per riyal) or lower the price.');
    }
    $('cal-creators-out').innerHTML = line;
  }
  // ---- a selection or campaign, measured while it is being prepared ----
  function source(){
    if (!S.src) return null;
    var parts = S.src.split(':'), list = parts[0] === 's' ? SRC.selections : SRC.campaigns;
    var o = list.filter(function(x){ return String(x.id) === parts[1]; })[0];
    return o ? {kind: parts[0] === 's' ? 'selection' : 'campaign', o: o} : null;
  }
  function tierOf(f){ return f < 10000 ? 'nano' : f < 100000 ? 'micro' : f < 500000 ? 'mid' : f < 1000000 ? 'macro' : 'mega'; }
  // what one creator usually gets from one post, [usual, good], for this result
  function perPost(c, p, kind){
    var P = LIB[p], f = c.followers[p], fell = false;
    if (!f) { f = c.followers[c.platform]; fell = !!f; }
    if (!f) return {none: true};
    var t = tierOf(f), own = (p === 'Instagram' || c.platform === p) ? c.own : null, v, how = 'benchmark';
    if (own && own.views) { v = [own.views * 0.8, own.views]; how = 'own average'; }
    else v = [f * P.view_rate[t][0] / 100, f * P.view_rate[t][1] / 100];
    var r;
    if (kind === 'views') r = v;
    else if (kind === 'reactions') r = (own && own.eng != null) ? [own.eng * 0.8, own.eng] : [v[0] * P.eng_rate[t][0] / 100, v[1] * P.eng_rate[t][1] / 100];
    else r = [v[0] * P.ctr[0] / 100, v[1] * P.ctr[1] / 100];
    return {r: r, f: f, tier: t, fell: fell, how: (kind === 'views' || (own && own.eng != null)) ? how : 'benchmark', own: own};
  }
  function check(f, budget){
    var box = $('cal-check'), sc = source();
    if (!sc) { box.innerHTML = ''; return null; }
    var o = sc.o, p = f.p, m = mainKind(f.t, f.p), c = ceil(p, m), rows = '', tot = [0, 0], priced = 0, problems = {bad: 0, warn: 0}, flagged = [];
    var all = {views: [0, 0], reactions: [0, 0], clicks: [0, 0]}, postsN = 0;
    o.creators.forEach(function(cr){
      var n = S.posts[o.id + ':' + cr.code]; if (n == null) n = cr.posts || 1;
      var pp = perPost(cr, p, m), probs = [];
      if (pp.none) {
        probs.push(['bad', 'No follower number on file, so it cannot be estimated']);
        rows += '<tr><td><b>' + cr.name + '</b><br><small>' + cr.code + '</small></td><td colspan="6">' + probs.map(function(x){ return '<span class="cal-prob cal-prob--' + x[0] + '">' + x[1] + '</span>'; }).join('') + '</td></tr>';
        problems.bad++; flagged.push(cr.name); return;
      }
      var us = pp.r[0] * n, ug = pp.r[1] * n; tot[0] += us; tot[1] += ug; postsN += n;
      ['views', 'reactions', 'clicks'].forEach(function(kk){ var q = perPost(cr, p, kk); if (q.r) { all[kk][0] += q.r[0] * n; all[kk][1] += q.r[1] * n; } });
      var cost = (cr.price && us) ? cr.price / us : null, v = cost == null ? null : verdict(cost, c);
      if (cr.price) priced += cr.price;
      if (pp.fell) probs.push(['warn', 'No ' + p + ' account: using their main account']);
      if (v && v[1] === 'r') probs.push(['bad', 'Costs more per result than we should accept']);
      if (cr.own && cr.own.fake != null && cr.own.fake > 25) probs.push(['warn', 'Fake followers ' + Math.round(cr.own.fake) + '%']);
      if (cr.own && cr.own.likes_hidden && m === 'reactions') probs.push(['warn', 'Hides likes: engagement is understated']);
      if (!cr.price) probs.push(['info', 'No price on file']);
      if (!cr.own) probs.push(['info', 'No analysis uploaded: estimated from creators this size']);
      probs.forEach(function(x){ if (x[0] === 'bad') problems.bad++; else if (x[0] === 'warn') problems.warn++; });
      if (probs.some(function(x){ return x[0] !== 'info'; })) flagged.push(cr.name);
      var unit = m === 'views' ? 'SAR ' + money(cost * 1000) + ' / 1,000' : 'SAR ' + money(cost);
      rows += '<tr><td><b>' + cr.name + '</b><br><small>' + cr.code + ' · ' + nice(pp.f) + ' · ' + D.tierLabel[pp.tier].replace(/ \(.*/, '') + '</small></td>'
        + '<td class="r"><input type="number" min="0" step="1" data-posts="' + o.id + ':' + cr.code + '" value="' + n + '" aria-label="Posts"></td>'
        + '<td class="r">' + (cr.price ? num(cr.price) : '—') + '</td><td class="r">' + nice(pp.r[0] * n) + ' – ' + nice(pp.r[1] * n) + '<br><small>' + pp.how + '</small></td>'
        + '<td class="r">' + (cost == null ? '—' : unit) + '</td><td>' + (v ? '<span class="cal-v cal-v--' + v[1] + '">' + (v[0] === 'Not OK' ? 'Poor value' : v[0] === 'Accepted' ? 'Fair value' : 'Great value') + '</span>' : '') + '</td>'
        + '<td>' + probs.map(function(x){ return '<span class="cal-prob cal-prob--' + x[0] + '">' + x[1] + '</span>'; }).join('') + '</td></tr>';
    });
    var rs = budget ? results(p, m, budget) : null, vd = null;
    if (rs) vd = tot[0] >= rs.great ? ['Great', 'g', 'The creators comfortably deliver more than a great result.'] : tot[0] >= rs.ok ? ['Accepted', 'a', 'The creators can deliver the accepted result, even on an ordinary day.']
      : tot[1] >= rs.ok ? ['Borderline', 'a', 'Only a good day reaches the accepted result. Add creators or lower the price.'] : ['Short', 'r', 'These creators are unlikely to reach the accepted result for this price.'];
    var name = NAME[m].toLowerCase(), label = TYPES[f.t].name + ' · ' + p;
    var sumHtml = '<div class="cal-sum"><div><span>These creators usually get</span><b>' + nice(tot[0]) + '</b><small>' + name + ' (good day: ' + nice(tot[1]) + ')</small></div>'
      + (rs ? '<div><span>Accept at least</span><b>' + nice(rs.ok) + '</b><small>for SAR ' + num(budget) + '</small></div><div><span>Great is</span><b>' + nice(rs.great) + '+</b><small>' + name + '</small></div>' : '')
      + '<div><span>Problems found</span><b>' + (problems.bad + problems.warn) + '</b><small>' + problems.bad + ' serious · ' + problems.warn + ' to check</small></div></div>';
    var banner = vd ? '<div class="cal-big"><span class="cal-v cal-v--' + vd[1] + '" style="font-size:16px">' + vd[0] + '</span> ' + vd[2] + '</div>' : '<p class="price-hint">Type the client budget to compare.</p>';
    var priceNote = priced ? '<p class="price-hint">Prices: ' + (sc.kind === 'selection' ? 'what the client is quoted for each creator (middle of the range)' : 'our fee to each creator') + '. Total ' + num(priced) + ' SAR.</p>' : '';
    box.innerHTML = '<div class="card"><div class="cal-h"><span class="pill live">' + (sc.kind === 'selection' ? 'Selection' : 'Campaign') + '</span><h2>' + o.name + '</h2></div>'
      + '<p class="price-hint" style="margin:0">Measured on <b>' + label + '</b>. Change the posts per creator to see what happens.</p>' + banner + sumHtml
      + '<table class="cal-c"><thead><tr><th>Creator</th><th class="r">Posts</th><th class="r">Price (SAR)</th><th class="r">Usually gets</th><th class="r">Cost per result</th><th>Value</th><th>Problems</th></tr></thead><tbody>' + rows + '</tbody></table>'
      + priceNote + '</div>';
    return {vd: vd, tot: tot, problems: problems, flagged: flagged, rs: rs, name: o.name, kind: sc.kind, label: label, all: all, posts: postsN, campaign: sc.kind === 'campaign' ? o.id : (o.campaign || null), o: o};
  }
  // Goals: the minimum to agree for each KPI is the LOWER of what the budget
  // must buy to be fair value and what these creators can safely deliver.
  function rnd(v){ return v >= 100000 ? Math.round(v / 1000) * 1000 : v >= 1000 ? Math.round(v / 100) * 100 : Math.round(v); }
  function goals(f, budget, chk){
    var box = $('cal-goals'); S.vals = null;
    if (!chk || !chk.campaign) { box.innerHTML = chk ? '<div class="card"><h2 style="margin-top:0">Campaign goals</h2><p class="price-hint">This selection is not linked to a campaign yet. Link it on the campaign\\'s setup page (Selection it came from) to save goals.</p></div>' : ''; return; }
    var p = f.p, a = chk.all, camp = SRC.campaigns.filter(function(x){ return x.id === chk.campaign; })[0] || {};
    var cat = S.cat || camp.category || 'other', links = f.t === 'conversion', vals = {};
    if (budget) {
      var vf = budget / ceil(p, 'views')[0], v = Math.min(vf, a.views[0] || vf);
      vals.posts = chk.posts; vals.views = rnd(v); vals.reach = rnd(v * LIB[p].reach_per_view);
      if (p !== 'Snapchat') { var ef = budget / ceil(p, 'reactions')[0], e = Math.min(ef, a.reactions[0] || ef); vals.engagement = rnd(e); vals.er = Math.round(e / v * 10000) / 100; }
      if (links) { var cf = budget / ceil(p, 'clicks')[0]; vals.clicks = rnd(Math.min(cf, a.clicks[0] || cf)); }
    }
    S.vals = vals;
    var KEYS = [['posts', 'Posts'], ['views', 'Views'], ['reach', 'Reach'], ['engagement', 'Likes + comments'], ['er', 'Engagement rate %']].concat(links ? [['clicks', 'Clicks']] : []);
    var ed = S.goalEdit || {};
    var saved = camp.targets && Object.keys(camp.targets).length ? '<div class="cal-saved">Saved now: ' + Object.keys(camp.targets).map(function(k){ return k + ' ' + (k === 'er' ? camp.targets[k] + '%' : nice(camp.targets[k])); }).join(' · ') + '</div>' : '';
    box.innerHTML = '<div class="card"><div class="cal-h"><span class="pill live">Goals</span><h2>Save as this campaign\\'s goals</h2></div>'
      + '<p class="price-hint" style="margin:0">Filled with the <b>minimum to agree</b>: the lower of what the budget must buy and what these creators can safely deliver. Change any figure, then save. The client sees these on their dashboard.</p>' + saved
      + '<form method="post" action="' + D.base + '/calculator/save"><input type="hidden" name="id" value="' + chk.campaign + '"><input type="hidden" name="type" value="' + f.t + '"><input type="hidden" name="platform" value="' + p + '"><input type="hidden" name="budget" value="' + (budget || '') + '">'
      + '<div class="cal-goalrow">' + KEYS.map(function(k){ var v = ed[k[0]] != null ? ed[k[0]] : (vals[k[0]] != null ? vals[k[0]] : ''); return '<div><label for="cal-g-' + k[0] + '">' + k[1] + '</label><input id="cal-g-' + k[0] + '" name="target_' + k[0] + '" data-goal="' + k[0] + '" inputmode="decimal" value="' + v + '"></div>'; }).join('')
      + '<div><label for="cal-g-cat">Product category</label><select id="cal-g-cat" name="category">' + Object.keys(D.categories).map(function(k){ return '<option value="' + k + '"' + (k === cat ? ' selected' : '') + '>' + D.categories[k] + '</option>'; }).join('') + '</select></div></div>'
      + '<button class="btn">Save goals</button></form></div>';
  }
  function source0(v){ var parts = v.split(':'), list = parts[0] === 's' ? SRC.selections : SRC.campaigns; var o = list.filter(function(x){ return String(x.id) === parts[1]; })[0]; return o ? {kind: parts[0] === 's' ? 'selection' : 'campaign', o: o} : null; }
  // Results by hand: pick a template (built from the same benchmarks and
  // creators as everything above, so they match) and change any number.
  function resultsCard(f, budget, chk){
    var box = $('cal-results');
    if (!chk || !chk.campaign) { box.innerHTML = ''; return; }
    var p = f.p, a = chk.all, camp = SRC.campaigns.filter(function(x){ return x.id === chk.campaign; })[0] || {};
    var links = f.t === 'conversion', measured = camp.measured || {}, adj = camp.adjusted || {};
    function setFrom(views, eng, clicks, posts){
      var o = {posts: posts};
      o.views = rnd(views); o.reach = rnd(views * LIB[p].reach_per_view);
      if (p !== 'Snapchat') { o.engagement = rnd(eng); o.er = Math.round(eng / views * 10000) / 100; }
      if (links) o.clicks = rnd(clicks);
      return o;
    }
    var T = {};
    if (budget) {
      var vOk = budget / ceil(p, 'views')[0], vGr = budget / ceil(p, 'views')[1], eOk = budget / ceil(p, 'reactions')[0], eGr = budget / ceil(p, 'reactions')[1], cOk = budget / ceil(p, 'clicks')[0], cGr = budget / ceil(p, 'clicks')[1];
      T.accepted = ['Accepted: the minimum to promise', setFrom(vOk, eOk, cOk, chk.posts)];
      T.middle = ['Halfway: accepted to great', setFrom((vOk + vGr) / 2, (eOk + eGr) / 2, (cOk + cGr) / 2, chk.posts)];
      T.great = ['Great', setFrom(vGr, eGr, cGr, chk.posts)];
    }
    T.usual = ['What these creators usually get', setFrom(a.views[0], a.reactions[0], a.clicks[0], chk.posts)];
    T.good = ['What they get on a good day', setFrom(a.views[1], a.reactions[1], a.clicks[1], chk.posts)];
    S.templates = T;
    var KEYS = [['views', 'Views'], ['reach', 'Reach'], ['engagement', 'Likes + comments'], ['er', 'Engagement rate %']].concat(links ? [['clicks', 'Clicks']] : []);
    var ed = S.resEdit || {}, basis = S.resBasis || adj._basis || '';
    var now = Object.keys(adj).filter(function(k){ return k !== '_basis'; }).length ? '<div class="cal-saved">Shown to the client now (as estimates): ' + Object.keys(adj).filter(function(k){ return k !== '_basis'; }).map(function(k){ return k + ' ' + (k === 'er' ? adj[k] + '%' : nice(adj[k])); }).join(' · ') + (adj._basis ? ' · based on: ' + adj._basis : '') + '</div>' : '<p class="price-hint">No adjustments: the client sees the measured numbers.</p>';
    box.innerHTML = '<div class="card"><div class="cal-h"><span class="pill live">Results</span><h2>Adjust this campaign\\'s results by hand</h2></div>'
      + '<p class="price-hint" style="margin:0">Use when the platform hides a number or it has not arrived yet. Pick a template to fill the boxes, then change anything. The client sees these <b>marked as estimates</b>, never as measured.</p>' + now
      + '<div class="cal-pills" id="cal-tpl" style="margin:10px 0">' + Object.keys(T).map(function(k){ return '<button type="button" data-tpl="' + k + '" aria-pressed="' + (S.resBasisKey === k ? 'true' : 'false') + '">' + T[k][0] + '</button>'; }).join('') + '</div>'
      + '<form method="post" action="' + D.base + '/calculator/results"><input type="hidden" name="id" value="' + chk.campaign + '"><input type="hidden" name="basis" id="cal-r-basis" value="' + basis.replace(/"/g, '&quot;') + '">'
      + '<div class="cal-goalrow">' + KEYS.map(function(k){ var v = ed[k[0]] != null ? ed[k[0]] : (adj[k[0]] != null ? adj[k[0]] : ''); var m = measured[k[0]];
        return '<div><label for="cal-r-' + k[0] + '">' + k[1] + '</label><input id="cal-r-' + k[0] + '" name="r_' + k[0] + '" data-res="' + k[0] + '" inputmode="decimal" value="' + v + '"><small class="muted">measured now: ' + (m == null ? '—' : (k[0] === 'er' ? m + '%' : nice(m))) + '</small></div>'; }).join('') + '</div>'
      + '<button class="btn">Save results</button> <button class="btn ghost" name="do" value="clear" onclick="return confirm(\\'Go back to the measured numbers?\\')">Back to measured</button></form></div>';
  }
  function applySource(){
    var sc = source(); if (!sc) { $('cal-source-hint').textContent = 'Pick one and the calculator uses its real creators, their followers and prices.'; return; }
    var o = sc.o, plats = String(o.platform || '').split(/[,&+\/]/).map(function(x){ return x.trim(); }).filter(function(x){ return PLATS.indexOf(x) >= 0; }), plat = plats.join(' + ');
    if (!plats.length) { var cnt = {}; o.creators.forEach(function(c){ if (c.platform) cnt[c.platform] = (cnt[c.platform] || 0) + 1; }); var top = Object.keys(cnt).sort(function(a, b){ return cnt[b] - cnt[a]; })[0]; if (top && PLATS.indexOf(top) >= 0) { plats = [top]; plat = top; } }
    if (plats.length) { S.plats = plats; S.share = {}; }
    var hint = o.creators.length + ' creators';
    if (o.budget) { var mid = Math.round((o.budget[0] + o.budget[1]) / 2 / 100) * 100; $('cal-budget').value = mid;
      hint += ' · budget ' + (o.budget[0] === o.budget[1] ? num(o.budget[0]) : num(o.budget[0]) + ' – ' + num(o.budget[1])) + ' SAR' + (o.budgetFrom ? ' (from ' + o.budgetFrom + ')' : '') + ' put in the box above, change it if the client pays something else'; }
    else hint += ' · no budget on file: type what the client pays';
    $('cal-source-hint').textContent = hint + (plat ? ' · platform ' + plat : '');
  }
  // ---- overview: your three questions, side by side ----
  var SW = {g: ['On track', 'g'], a: ['Close', 'a'], r: ['Behind', 'r']};
  function st(cls, text){ return '<span class="cal-st cal-st--' + cls + '">' + text + '</span>'; }
  function perUnit(p, kind){ var c = ceil(p, kind); return kind === 'views' ? 'SAR ' + money(c[0] * 1000) + ' per 1,000 views' : 'SAR ' + money(c[0]) + ' per ' + (kind === 'clicks' ? 'click' : 'like or comment'); }
  // Actual results against the targets, one status per aspect. Needs a campaign.
  function statuses(f, budget, chk){
    if (!chk || !chk.campaign) return null;
    var camp = SRC.campaigns.filter(function(x){ return x.id === chk.campaign; })[0]; if (!camp) return null;
    var m = camp.measured || {}, adj = camp.adjusted || {}, T = (camp.targets && Object.keys(camp.targets).length) ? camp.targets : (S.vals || {}), saved = !!(camp.targets && Object.keys(camp.targets).length);
    var act = {}; ['posts', 'views', 'reach', 'engagement', 'er', 'clicks'].forEach(function(k){ act[k] = (k !== 'posts' && adj[k] != null) ? adj[k] : m[k]; });
    var now = Date.now() / 1000, el = 1;
    if (camp.starts && camp.ends && camp.ends > camp.starts) el = Math.max(0.15, Math.min(1, (now - camp.starts) / (camp.ends - camp.starts)));
    var NAMES = {posts: 'Posts live', views: 'Views', reach: 'Reach', engagement: 'Likes + comments', er: 'Engagement rate', clicks: 'Clicks'};
    var items = [];
    ['posts', 'views', 'reach', 'engagement', 'er', 'clicks'].forEach(function(k){
      var g = T[k]; if (!g || act[k] == null) return;
      var pct = act[k] / g * 100, ratio = k === 'er' ? act[k] / g : act[k] / (g * el), s = act[k] >= g ? ['Goal reached', 'g'] : ratio >= 1 ? ['On track', 'g'] : ratio >= 0.7 ? ['Close', 'a'] : ['Behind', 'r'];
      items.push({key: k, label: NAMES[k], goal: g, actual: act[k], pct: pct, status: s, kind: 'goal', est: adj[k] != null});
    });
    // value for money: at the pace so far, what will each result cost?
    var planned = chk.posts || 0, live = m.posts || 0, share = planned ? Math.min(1, live / planned) : 0, p = f.p;
    if (budget && share > 0) [['views', 'views', 'per 1,000 views'], ['reactions', 'engagement', 'per like or comment']].forEach(function(x){
      var got = act[x[1]]; if (!got) return; var proj = got / share, cost = budget / proj, c = ceil(p, x[0]), v = verdict(cost, c);
      var word = v[1] === 'g' ? ['Great value', 'g'] : v[1] === 'a' ? ['Fair value', 'a'] : ['Poor value', 'r'];
      items.push({key: 'val-' + x[0], label: 'Value: ' + (x[0] === 'views' ? 'views' : 'reactions'), kind: 'value', status: word,
        text: (x[0] === 'views' ? 'SAR ' + money(cost * 1000) : 'SAR ' + money(cost)) + ' ' + x[2] + ' at the end', limit: 'limit ' + perUnit(p, x[0]).replace('SAR ', 'SAR ')});
    });
    var probs = chk.problems.bad + chk.problems.warn;
    items.push({key: 'creators', label: 'Creators', kind: 'creators', status: probs === 0 ? ['No problems', 'g'] : probs <= 3 ? ['A few to check', 'a'] : ['Check them', 'r'], text: probs + ' problem' + (probs === 1 ? '' : 's') + ' found' + (chk.flagged.length ? ': ' + chk.flagged.slice(0, 3).join(', ') + (chk.flagged.length > 3 ? '…' : '') : '')});
    // The overall status judges the RESULTS against the goals, the same way the
    // client dashboard does (on track / close / behind). Value and creator
    // checks are shown beside it, so a creator problem cannot turn good
    // results red.
    var gi = items.filter(function(i){ return i.kind === 'goal'; }), pts = gi.reduce(function(a, i){ return a + (i.status[1] === 'g' ? 2 : i.status[1] === 'a' ? 1 : 0); }, 0) / (gi.length || 1);
    var overall = !gi.length ? ['No goals yet', 'a'] : pts >= 1.5 ? ['On track', 'g'] : pts >= 0.75 ? ['Close to target', 'a'] : ['Behind target', 'r'];
    return {items: items, overall: overall, saved: saved, camp: camp, elapsed: el, share: share};
  }
  function actualTab(sv, f){
    var box = $('cal-actual');
    if (!sv) { box.innerHTML = '<div class="card"><h2 style="margin-top:0">Actual vs target</h2><p class="price-hint">Pick a <b>campaign</b> (or a selection linked to one) above, and its real results are compared with the targets here, with a status for every aspect.</p>'
      + '<p class="price-hint">No campaign yet? Use <b>Tools → Did it pay off?</b> to type what a campaign got.</p></div>'; return; }
    var cards = sv.items.map(function(i){
      if (i.kind === 'goal') { var col = i.status[1] === 'g' ? '#1f9d55' : i.status[1] === 'a' ? '#e2780f' : '#e0241f';
        return '<div class="cal-stc"><h3>' + i.label + '</h3><div class="nums"><b>' + (i.key === 'er' ? i.actual + '%' : nice(i.actual)) + (i.est ? ' <small>est.</small>' : '') + '</b><small>goal ' + (i.key === 'er' ? i.goal + '%' : nice(i.goal)) + '</small></div>'
          + '<div class="bar"><i style="width:' + Math.min(100, i.pct) + '%;background:' + col + '"></i></div><div>' + st(i.status[1], i.status[0]) + ' <small class="muted">' + Math.round(i.pct) + '% of goal</small></div></div>'; }
      return '<div class="cal-stc"><h3>' + i.label + '</h3><div class="nums"><b style="font-size:17px">' + i.text.split(' at the end')[0] + '</b></div><div>' + st(i.status[1], i.status[0]) + '</div>' + (i.limit ? '<p>' + i.limit + (i.text.indexOf('at the end') > 0 ? ' · projected to the end' : '') + '</p>' : '') + '</div>';
    }).join('');
    box.innerHTML = '<div class="card"><div class="cal-h"><span class="cal-bigchip cal-st--' + sv.overall[1] + '">' + sv.overall[0] + '</span></div>'
      + '<p class="price-hint" style="margin:0">' + sv.camp.name + ' · goals: ' + (sv.saved ? 'the ones saved for this campaign' : 'suggested minimum (none saved yet)') + ' · ' + Math.round(sv.elapsed * 100) + '% of the time has passed · ' + (sv.camp.measured.posts || 0) + ' posts live'
      + (Object.keys(sv.camp.adjusted || {}).filter(function(k){ return k !== '_basis'; }).length ? ' · figures marked est. were adjusted by hand' : '') + '</p><div class="cal-stgrid">' + cards + '</div></div>';
  }
  function overview(budget, chk, f){
    var buy = '', tgt = '', act = '';
    if (!budget) buy = '<p class="price-hint">Type what the client pays.</p>';
    else {
      var amt = split(budget);
      S.types.forEach(function(t){
        var T = TYPES[t], mk = T.main, ok = 0, gr = 0, snap = false;
        S.plats.forEach(function(p){ if (mainKind(t, p) !== mk) { snap = true; return; } var r = results(p, mk, amt[p]); ok += r.ok; gr += r.great; });
        buy += '<div class="cal-row"><span><b>' + T.name + '</b><small>' + NAME[mk].toLowerCase() + (snap ? ' (Snapchat on views)' : '') + ' · ' + perUnit(S.plats[0], mk) + ' at most</small></span><span style="text-align:right">accept <b>' + nice(ok) + '</b><small>great ' + nice(gr) + '+</small></span></div>';
      });
    }
    var sv = statuses(f, budget, chk), camp = chk && chk.campaign ? SRC.campaigns.filter(function(x){ return x.id === chk.campaign; })[0] : null;
    var T2 = camp && camp.targets && Object.keys(camp.targets).length ? camp.targets : (S.vals || null), TN = {posts: 'Posts', views: 'Views', reach: 'Reach', engagement: 'Likes + comments', er: 'Engagement rate', clicks: 'Clicks'};
    if (T2) { var lbl = camp && camp.targets && Object.keys(camp.targets).length ? 'Agreed goals saved for this campaign' : 'Suggested minimum: the lower of the budget and what these creators can safely deliver';
      tgt = '<p class="price-hint" style="margin:0 0 4px">' + lbl + '</p>' + Object.keys(TN).filter(function(k){ return T2[k] != null; }).map(function(k){ return '<div class="cal-row"><span>' + TN[k] + '</span><b>' + (k === 'er' ? T2[k] + '%' : nice(T2[k])) + '</b></div>'; }).join(''); }
    else if (budget) { tgt = '<p class="price-hint" style="margin:0 0 4px">Minimum accepted for this budget. Pick a campaign to check what its creators can safely deliver.</p>' + buy; }
    else tgt = '<p class="price-hint">Type what the client pays.</p>';
    if (sv) act = '<div class="cal-bigchip cal-st--' + sv.overall[1] + '">' + sv.overall[0] + '</div>' + sv.items.slice(0, 7).map(function(i){ return '<div class="cal-row"><span>' + i.label + '</span>' + st(i.status[1], i.status[0]) + '</div>'; }).join('');
    else act = '<p class="price-hint">Pick a campaign above to compare its real results with the targets, aspect by aspect.</p>';
    $('cal-ov-buy').innerHTML = buy; $('cal-ov-target').innerHTML = tgt; $('cal-ov-actual').innerHTML = act;
    actualTab(sv, f);
  }
  function setTab(name){
    S.tab = name;
    document.querySelectorAll('#cal-tabs button').forEach(function(b){ b.setAttribute('aria-selected', b.dataset.tab === name ? 'true' : 'false'); });
    document.querySelectorAll('.cal-panel').forEach(function(p){ p.hidden = p.id !== 'tab-' + name; });
    try { sessionStorage.setItem('cal-tab', name); } catch (e) {}
  }
  function toggle(list, k){
    var i = list.indexOf(k);
    if (i >= 0) { if (list.length > 1) list.splice(i, 1); } else list.push(k);   // always at least one
  }
  // build the controls
  $('cal-type').innerHTML = TYPE_KEYS.map(function(k){ return '<button type="button" data-k="' + k + '" aria-pressed="false"><span>' + TYPES[k].name + '<small>' + TYPES[k].sub + '</small></span></button>'; }).join('');
  $('cal-plat').innerHTML = PLATS.map(function(p){ return '<button type="button" data-k="' + p + '" aria-pressed="false">' + p + '</button>'; }).join('');
  $('cal-tiers').innerHTML = TIERS.map(function(t){ return '<div><label for="cal-t-' + t + '">' + D.tierLabel[t] + '</label><input id="cal-t-' + t + '" inputmode="numeric" value="" placeholder="0"></div>'; }).join('');
  $('cal-type').addEventListener('click', function(e){ var b = e.target.closest('button'); if (b) { toggle(S.types, b.dataset.k); $('cal-got1').value = ''; $('cal-got2').value = ''; render(); } });
  $('cal-plat').addEventListener('click', function(e){ var b = e.target.closest('button'); if (b) { toggle(S.plats, b.dataset.k); S.share = {}; render(); } });
  var opt = '<option value="">— none: just type the numbers —</option>';
  if (SRC.selections.length) opt += '<optgroup label="Selections">' + SRC.selections.map(function(x){ return '<option value="s:' + x.id + '">' + x.name + ' (' + x.creators.length + ')</option>'; }).join('') + '</optgroup>';
  if (SRC.campaigns.length) opt += '<optgroup label="Campaigns">' + SRC.campaigns.map(function(x){ return '<option value="c:' + x.id + '">' + x.name + ' (' + x.creators.length + ')</option>'; }).join('') + '</optgroup>';
  $('cal-source').innerHTML = opt;
  $('cal-source').addEventListener('change', function(){ S.src = this.value; S.goalEdit = {}; S.cat = null; applySource(); render(); });
  if (D.initial && source0(D.initial)) { S.src = D.initial; $('cal-source').value = D.initial; var sc0 = source0(D.initial); var t0 = sc0.o.type; if (t0 && TYPES[t0]) S.types = [t0]; applySource(); }
  document.addEventListener('click', function(e){
    var b = e.target.closest && e.target.closest('[data-tpl]'); if (!b || !S.templates) return;
    var t = S.templates[b.dataset.tpl]; if (!t) return;
    S.resEdit = {}; Object.keys(t[1]).forEach(function(k){ if (k !== 'posts') S.resEdit[k] = t[1][k]; });
    S.resBasisKey = b.dataset.tpl; S.resBasis = t[0] + ' for ' + (focus() ? TYPES[focus().t].name + ' · ' + focus().p : '');
    render();
  });
  document.addEventListener('click', function(e){ var b = e.target.closest && e.target.closest('#cal-tabs button, [data-go]'); if (b) setTab(b.dataset.tab || b.dataset.go); });
  try { var t0 = sessionStorage.getItem('cal-tab'); if (t0 && document.getElementById('tab-' + t0)) setTab(t0); } catch (e) {}
  $('cal-focus').addEventListener('change', function(){ S.focus = this.value; $('cal-got1').value = ''; $('cal-got2').value = ''; render(); });
  document.addEventListener('input', function(e){
    var el = e.target;
    if (el.dataset && el.dataset.p) { S.share[el.dataset.p] = readEl(el) || 0; S.plats.forEach(function(p){ if (S.share[p] == null) S.share[p] = 100 / S.plats.length; });
      // refresh only the amounts so the box being typed in keeps focus
      var budget = read('cal-budget'), amt = budget ? split(budget) : {};
      document.querySelectorAll('#cal-split small').forEach(function(sm, i){ sm.textContent = budget ? 'SAR ' + num(amt[S.plats[i]]) : ''; });
      if (!budget) return;
      $('cal-accept').innerHTML = S.types.map(function(t){ return tableFor(t, budget); }).join(''); tools(budget); return; }
    if (el.dataset && el.dataset.res) { S.resEdit = S.resEdit || {}; S.resEdit[el.dataset.res] = el.value; return; }
    if (el.dataset && el.dataset.goal) { S.goalEdit = S.goalEdit || {}; S.goalEdit[el.dataset.goal] = el.value; return; }
    if (el.id === 'cal-g-cat') { S.cat = el.value; return; }
    if (el.dataset && el.dataset.posts) { S.posts[el.dataset.posts] = Math.max(0, parseInt(el.value, 10) || 0); var id = el.dataset.posts, pos = el.selectionStart; render();
      var back = document.querySelector('[data-posts="' + id + '"]'); if (back) { back.focus(); try { back.setSelectionRange(pos, pos); } catch (x) {} } return; }
    if (el.tagName === 'INPUT') render();
  });
  render();
})();
</script>"""
    return page("ROI calculator", body, "/calculator")
