"""The admin's design system: tokens and styles, drawn icons, the app shell
(sidebar, top bar, command palette, help guides) and the small components
every page reuses (page header, tabs, stat, empty state, stepper, charts).

Operate surface: a person doing a task. Familiar patterns (left sidebar,
breadcrumbs, tabs, search), one text family (DM Sans), Bebas Neue only for the
page title and big numerals, ink / lime / linen from the HelloVoice brand,
and colour kept for state: lime marks the action and the current place,
green / amber / red are verdicts and nothing else.
"""

import html
import json
import re

FONTS = "/static/fonts"


def e(v):
    return html.escape("" if v is None else str(v), quote=True)


# --------------------------------------------------------------------- icons --
# One stroke style: 24px grid, 1.75px stroke, round caps and joins.
_ICONS = {
    "home": '<path d="M3.5 11.2 12 4l8.5 7.2"/><path d="M5.5 10v9.5h13V10"/><path d="M10 19.5v-5h4v5"/>',
    "list": '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 9h8M8 13h8M8 17h5"/>',
    "flag": '<path d="M5 21V4"/><path d="M5 5h11l-2 3.5L16 12H5"/>',
    "inbox": '<path d="M4 13.5 6.5 5h11L20 13.5"/><path d="M4 13.5V19h16v-5.5h-5l-1.2 2h-3.6L9 13.5z"/>',
    "users": '<circle cx="9" cy="8.5" r="3.3"/><path d="M3 20c.4-3.4 2.8-5.4 6-5.4s5.6 2 6 5.4"/><path d="M16 5.4a3.2 3.2 0 0 1 0 6.2M18 14.8c1.8.7 2.8 2.4 3 5.2"/>',
    "profile": '<circle cx="12" cy="8" r="3.4"/><path d="M5 20c.5-3.6 3.2-5.6 7-5.6s6.5 2 7 5.6"/><path d="M17 3.5l.7 1.5 1.6.2-1.2 1.1.3 1.6-1.4-.8-1.4.8.3-1.6-1.2-1.1 1.6-.2z"/>',
    "building": '<rect x="5" y="3.5" width="14" height="17" rx="2"/><path d="M9 8h2M13 8h2M9 12h2M13 12h2M10.5 20.5v-4h3v4"/>',
    "key": '<circle cx="8" cy="15" r="3.5"/><path d="M10.6 12.6 19 4.2M16 7.2l2.3 2.3M14 9.2l1.8 1.8"/>',
    "calc": '<rect x="5" y="3.5" width="14" height="17" rx="2.5"/><path d="M8.5 8h7M8.5 12.5h1M12 12.5h1M15.5 12.5h0M8.5 16.5h1M12 16.5h1M15.5 16.5h0"/>',
    "bars": '<path d="M5 20V10M10 20V5M15 20v-7M20 20V8"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 3.5v2.2M12 18.3v2.2M3.5 12h2.2M18.3 12h2.2M6 6l1.6 1.6M16.4 16.4 18 18M18 6l-1.6 1.6M7.6 16.4 6 18"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/>',
    "bell": '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2H4.5z"/><path d="M10 21h4"/>',
    "help": '<circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.6a2.5 2.5 0 1 1 3.4 2.3c-.7.3-1 .9-1 1.6"/><path d="M12 16.6h0"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "panel": '<rect x="3.5" y="4.5" width="17" height="15" rx="3"/><path d="M9.5 4.5v15"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "copy": '<rect x="8.5" y="8.5" width="11" height="11" rx="2.5"/><path d="M15.5 8.5V6A2.5 2.5 0 0 0 13 3.5H6A2.5 2.5 0 0 0 3.5 6v7A2.5 2.5 0 0 0 6 15.5h2.5"/>',
    "upload": '<path d="M12 16V5M7.5 9.5 12 5l4.5 4.5"/><path d="M5 15v3.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V15"/>',
    "alert": '<path d="M12 4 3.5 19h17z"/><path d="M12 10v4M12 16.8h0"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h0"/>',
    "merge": '<path d="M6 4v5a4 4 0 0 0 4 4h4a4 4 0 0 1 4 4v3"/><path d="M18 4v5a4 4 0 0 1-4 4"/><path d="m15.5 17.5 2.5 3 2.5-3"/>',
    "image": '<rect x="4" y="5" width="16" height="14" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="m5 17 4.5-4.5 3 3 2-2L19 17"/>',
    "target": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1"/>',
    "star": '<path d="m12 4 2.4 5 5.4.7-4 3.7 1 5.4L12 16.2 7.2 18.8l1-5.4-4-3.7 5.4-.7z"/>',
    "edit": '<path d="M5 19h3.5L19 8.5 15.5 5 5 15.5z"/><path d="m13.5 7 3.5 3.5"/>',
    "trash": '<path d="M5 7h14M10 7V4.5h4V7M7 7l.8 12.5h8.4L17 7"/>',
    "send": '<path d="M20.5 4 3.5 11l6 2.5L12 20z"/><path d="m9.5 13.5 11-9.5"/>',
    "download": '<path d="M12 5v11M7.5 11.5 12 16l4.5-4.5"/><path d="M5 19.5h14"/>',
    "refresh": '<path d="M19.5 12a7.5 7.5 0 0 1-13 5.1M4.5 12a7.5 7.5 0 0 1 13-5.1"/><path d="M17 3.5v4h-4M7 20.5v-4h4"/>',
}


def icon(name, size=18, cls=""):
    return ('<svg class="ic %s" width="%d" height="%d" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">%s</svg>'
            % (cls, size, size, _ICONS.get(name, "")))


# ---------------------------------------------------------------- navigation --
# Grouped by job, not by database table. (href, label, icon, badge, keywords)
# Nine top-level destinations, grouped by job (2026-10 revamp). Related pages sit one level down and
# open under their parent when you are in that section; every old URL still works.
NAV = [
    ("", [("/", "Home", "home", None)]),
    ("Work", [("/requests", "Quote requests", "inbox", "req"),
              ("/selections", "Selections", "list", None),
              ("/campaigns", "Campaigns", "flag", None)]),
    ("Library", [("/roster", "Creators", "users", None)]),
    ("Clients", [("/clients", "Clients", "building", None)]),
    ("Insights", [("/analytics", "Analytics", "bars", None),
                  ("/ai", "AI copilot", "star", None)]),
    ("System", [("/settings", "Settings", "gear", None)]),
]
CHILDREN = {
    "/roster": [("/analysis", "Creator analysis", "an")],
    "/clients": [("/portal", "Client portal", None), ("/codes", "Access codes", None)],
    "/analytics": [("/calculator", "ROI calculator", None)],
    "/settings": [("/apis", "APIs & keys", None), ("/history", "History & undo", None)],
}
PARENT = {c[0]: p for p, kids in CHILDREN.items() for c in kids}

# Which sidebar item a page belongs under, so sub-pages keep it highlighted.
SECTION_OF = {"/planner": "/calculator", "/clients": "/clients"}


def _active_item(active):
    active = SECTION_OF.get(active, active)
    top = PARENT.get(active, active)
    for group, items in NAV:
        for href, label, ic, badge in items:
            if href == top:
                if top != active:
                    child = next(c for c in CHILDREN[top] if c[0] == active)
                    return group, active, child[1]
                return group, href, label
    return "", active, ""


# --------------------------------------------------------------- help guides --
GUIDES = [
    ("Quote a client", "list", [
        ("Add the client", "Open <b>Clients</b>, create an access code. The client opens the catalogue with it.", "/clients"),
        ("Build a selection", "In <b>Selections</b>, start one, pick the client and platform, then add creators.", "/selections"),
        ("Set costs and margins", "Type what each creator charges. The price follows your minimum and maximum margin.", "/selections"),
        ("Send the link", "Copy the link from the selection and send it. The client sees prices, never your costs.", "/selections")]),
    ("Run a campaign", "flag", [
        ("Start from a selection", "On the selection, press <b>Start a campaign</b>. Creators, passcode and costs come along.", "/selections"),
        ("Set dates, rules and goals", "On the campaign Setup tab: dates, the hashtags that count, and the goals.", "/campaigns"),
        ("Go live", "Press <b>Go live</b>. Posts and numbers appear on the client's report once captured.", "/campaigns"),
        ("Collect insights", "Ask creators for insights; approving them replaces estimates with real numbers.", "/campaigns")]),
    ("Add or fix creators", "users", [
        ("Add a creator", "<b>Creators</b> → Add. Fill the profile links; followers decide the tier.", "/roster"),
        ("Upload an analysis", "<b>Creator analysis</b> → Import a report PDF and attach it to the creator.", "/analysis"),
        ("Merge duplicates", "<b>Creators</b> → Duplicates. Pick the one to keep; selections move across.", "/roster")]),
    ("Check a campaign's results", "bars", [
        ("Open the campaign report", "Campaign → <b>Report</b> shows what the client sees.", "/campaigns"),
        ("Compare with the goals", "The <b>ROI calculator</b> compares real results with targets, aspect by aspect.", "/calculator"),
        ("Adjust a number", "If a platform hides a number, adjust it by hand. The client sees it marked as an estimate.", "/calculator")]),
    ("Undo a mistake", "clock", [
        ("Open History", "Every change is listed with who made it.", "/history"),
        ("Press Undo", "The creator, selection or campaign goes back exactly as it was.", "/history")]),
]


def _guides_html(u):
    out = []
    for title, ic, steps in GUIDES:
        lis = "".join('<li><a href="%s"><b>%s</b><span>%s</span></a></li>' % (u(href), e(t), body)
                      for t, body, href in steps)
        out.append('<details class="guide-item"><summary>%s<span>%s</span></summary><ol>%s</ol></details>'
                   % (icon(ic, 18), e(title), lis))
    return "".join(out)


# -------------------------------------------------------------------- styles --
_NEW = r"""
@font-face{font-family:"DM Sans";src:url(__FONTS__/dmsans.ttf) format("truetype");font-weight:100 1000;font-display:swap}
@font-face{font-family:"Bebas Neue";src:url(__FONTS__/bebas.ttf) format("truetype");font-weight:400;font-display:swap}
:root{
  --ink:#121212;--ink-2:#1b1b1b;--ink-3:#2a2a2a;--paper:#f5f3ef;--bg:#f5f3ef;--white:#fff;--linen:#e9dcd2;--lime:#e8ff76;
  --gray:#5a5a58;--muted:#6e6d68;--line:rgba(18,18,18,.1);--line-strong:rgba(18,18,18,.2);
  --green:#14884a;--green-soft:#e7f6ec;--amber:#a85507;--amber-soft:#fff1e2;--red:#c01010;--red-soft:#fdeaea;--blue:#1d4ed8;--blue-soft:#eef2ff;
  --r-sm:8px;--r-md:12px;--r-lg:16px;--side:252px;--bar:60px;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:14.5px/1.55 "DM Sans",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit}
:focus-visible{outline:2px solid var(--ink);outline-offset:2px;border-radius:6px}
.skip{position:absolute;left:-999px;top:8px;background:var(--ink);color:#fff;padding:10px 16px;border-radius:999px;z-index:100}
.skip:focus{left:12px}
.app{display:grid;grid-template-columns:var(--side) minmax(0,1fr);min-height:100vh;transition:grid-template-columns .2s ease}
.app.is-collapsed{--side:68px}
/* ---- sidebar ---- */
.side{background:var(--ink);color:#fff;position:sticky;top:0;height:100vh;display:flex;flex-direction:column;padding:14px 12px;overflow-y:auto;overflow-x:hidden;z-index:40}
.side .logo{display:flex;align-items:center;padding:8px 10px 18px;text-decoration:none}
.side .logo img{height:23px;width:auto;display:block}
.nav-group{margin-top:10px}
.nav-title{font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:rgba(255,255,255,.5);padding:8px 10px 6px;white-space:nowrap}
.nav-item{display:flex;align-items:center;gap:12px;padding:9px 10px;border-radius:10px;color:rgba(255,255,255,.74);text-decoration:none;font-size:14px;font-weight:500;white-space:nowrap;position:relative}
.nav-item:hover{background:var(--ink-3);color:#fff}
.nav-item[aria-current=page]{background:var(--ink-3);color:#fff}
.nav-item[aria-current=page] .ic{color:var(--lime)}
.nav-item .ic{flex:none}
.nav-item .badge{margin-left:auto}
.views{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:-6px 0 14px}
.views .pill{text-decoration:none}.views .vx{border:0;background:transparent;cursor:pointer;color:var(--gray);font-size:16px;line-height:1;padding:0 6px 0 0;min-width:24px;min-height:24px}
.bulkbar{position:sticky;top:calc(var(--bar) + 8px);z-index:20;display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:10px 14px;margin:0 0 12px;background:var(--ink);color:#fff;border-radius:var(--r-md);box-shadow:0 10px 30px rgba(0,0,0,.2)}
.bulkbar select{min-height:36px;width:auto;max-width:260px}
.bulkbar .btn.ghost{color:#fff;border-color:rgba(255,255,255,.4)}
.rpick{display:inline-flex;margin:0 8px 0 0;vertical-align:middle}
@media (min-width:1001px){main table thead th{position:sticky;top:var(--bar);background:var(--white);z-index:2}}
.kpi-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.kpi{display:flex;flex-direction:column;gap:2px;padding:12px 14px;border:1px solid var(--line);border-radius:var(--r-md);text-decoration:none;color:var(--ink);background:var(--white)}
.kpi:hover{border-color:var(--ink)}
.kpi span{font-size:13px;color:var(--gray)}
.kpi b{font-family:"Bebas Neue",sans-serif;font-weight:400;font-size:32px;line-height:1.05;font-variant-numeric:tabular-nums}
.kpi em{font-style:normal;font-size:12.5px;color:var(--gray)}
.kpi em.up{color:var(--green)}.kpi em.down{color:var(--amber)}
.nav-item.nav-sub{padding:7px 10px 7px 41px;font-size:13.5px}
.nav-item.nav-sub[aria-current=page]{background:transparent;color:#fff;box-shadow:inset 2px 0 0 var(--lime)}
.nav-item[aria-current=true]{color:#fff}
.app.is-collapsed .nav-item.nav-sub{display:none}
.side-foot{margin-top:auto;padding-top:14px;border-top:1px solid rgba(255,255,255,.12);display:grid;gap:4px}
.side-me{display:flex;align-items:center;gap:10px;padding:8px 10px;color:rgba(255,255,255,.74);font-size:13px;min-width:0}
.side-me i{flex:none;width:30px;height:30px;border-radius:50%;background:var(--lime);color:var(--ink);font-style:normal;font-weight:700;display:grid;place-items:center}
.side-me span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.app.is-collapsed .nav-title,.app.is-collapsed .nav-item span.t,.app.is-collapsed .side-me span,.app.is-collapsed .nav-item .badge{display:none}
.app.is-collapsed .nav-item{justify-content:center}
.app.is-collapsed .nav-group{margin-top:4px}
.app.is-collapsed .side .logo img{height:18px;width:30px;object-fit:cover;object-position:left}
/* ---- top bar ---- */
.main{min-width:0;display:flex;flex-direction:column}
.bar{height:var(--bar);background:var(--white);border-bottom:1px solid var(--line);display:flex;align-items:center;gap:10px;padding:0 24px;position:sticky;top:0;z-index:30}
.bar .iconbtn{width:38px;height:38px;border-radius:10px;border:0;background:transparent;color:var(--ink);display:grid;place-items:center;cursor:pointer;position:relative;text-decoration:none}
.bar .iconbtn:hover{background:#efede8}
.bar .iconbtn .badge{position:absolute;top:2px;right:0}
.crumbs{display:flex;align-items:center;gap:8px;font-size:13.5px;color:var(--gray);min-width:0;white-space:nowrap}
.crumbs a{text-decoration:none;color:var(--gray)}
.crumbs a:hover{color:var(--ink);text-decoration:underline}
.crumbs b{font-weight:600;color:var(--ink)}
.crumbs i{font-style:normal;color:var(--muted)}
.bar .grow{flex:1}
.search-btn{display:flex;align-items:center;gap:10px;height:38px;min-width:240px;padding:0 12px;border-radius:999px;border:1px solid var(--line-strong);background:var(--paper);color:var(--gray);font:inherit;font-size:13.5px;cursor:pointer}
.search-btn:hover{border-color:var(--ink);color:var(--ink)}
.search-btn kbd{margin-left:auto;font:600 11px "DM Sans",sans-serif;background:var(--white);border:1px solid var(--line);border-radius:6px;padding:2px 6px;color:var(--gray)}
.page{padding:26px 32px 96px;max-width:1320px;width:100%}
/* ---- page header ---- */
.ph{display:flex;flex-wrap:wrap;gap:16px 28px;align-items:flex-end;justify-content:space-between;margin:2px 0 4px}
.ph h1{font:400 40px/1 "Bebas Neue",Arial,sans-serif;letter-spacing:.02em;margin:6px 0 8px}
.ph .desc{margin:0;color:var(--gray);max-width:72ch;font-size:15px}
.ph-actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.ptabs{display:flex;gap:2px;border-bottom:1px solid var(--line);margin:18px 0 22px;overflow-x:auto;scrollbar-width:none}
.ptabs::-webkit-scrollbar{display:none}
.ptabs a,.ptabs button{display:inline-flex;align-items:center;gap:8px;padding:11px 16px;text-decoration:none;color:var(--gray);font:inherit;font-weight:600;font-size:14px;border:0;background:transparent;border-bottom:2px solid transparent;margin-bottom:-1px;white-space:nowrap;cursor:pointer}
.ptabs a:hover,.ptabs button:hover{color:var(--ink);background:rgba(18,18,18,.04);border-radius:8px 8px 0 0}
.ptabs [aria-current=page],.ptabs [aria-selected=true]{color:var(--ink);border-bottom-color:var(--ink)}
.ptabs .n{font-size:12px;background:#ebe8e2;border-radius:999px;padding:1px 8px;color:var(--gray)}
.ptabs [aria-current=page] .n,.ptabs [aria-selected=true] .n{background:var(--ink);color:var(--lime)}
.panel[hidden]{display:none}
.sec-desc{color:var(--gray);margin:-6px 0 14px;max-width:70ch}
/* ---- surfaces ---- */
.card{background:var(--white);border:1px solid var(--line);border-radius:var(--r-lg);padding:22px;margin-bottom:20px}
.card>h2:first-child,.card>.hd:first-child h2{margin-top:0}
.hd{display:flex;flex-wrap:wrap;gap:6px 16px;align-items:baseline;justify-content:space-between;margin:0 0 12px}
.hd h2{margin:0}
h2{font-size:18px;line-height:1.3;margin:30px 0 12px;font-weight:700}
h3{font-size:15px;margin:18px 0 8px}
.sub{color:var(--gray);margin:0 0 22px;font-size:15px}
.muted{color:var(--gray)}
.stat,.kpis>div{background:var(--white);border:1px solid var(--line);border-radius:var(--r-md);padding:16px 18px}
.stat b,.kpis b{display:block;font:400 38px/1 "Bebas Neue",Arial,sans-serif;letter-spacing:.02em;margin-bottom:4px}
.stat span,.kpis span{color:var(--gray);font-size:13px;text-transform:none;letter-spacing:0}
/* ---- controls ---- */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:40px;font:inherit;font-weight:600;font-size:14px;padding:8px 20px;border-radius:999px;border:1px solid var(--ink);background:var(--ink);color:#fff;cursor:pointer;text-decoration:none;transition:background .15s ease,color .15s ease,border-color .15s ease}
.btn:hover{background:#000;opacity:1}
.btn.lime{background:var(--lime);border-color:var(--lime);color:var(--ink)}
.btn.lime:hover{background:var(--ink);border-color:var(--ink);color:var(--lime)}
.btn.ghost{background:transparent;color:var(--ink);border-color:var(--line-strong)}
.btn.ghost:hover{border-color:var(--ink);background:#fff}
.btn.small{min-height:32px;padding:4px 14px;font-size:13px}
.btn.tiny{min-height:26px;padding:2px 11px;font-size:12px}
.btn.danger{border-color:var(--red);color:var(--red);background:transparent}
.btn.danger:hover{background:var(--red);color:#fff}
.btn[disabled]{opacity:.45;cursor:not-allowed}
input,select,textarea{width:100%;font:inherit;font-size:14.5px;min-height:40px;padding:8px 12px;border:1px solid var(--line-strong);border-radius:10px;background:var(--white);color:var(--ink)}
textarea{min-height:76px;resize:vertical}
input:focus,select:focus,textarea:focus{outline:2px solid var(--ink);outline-offset:1px;border-color:var(--ink)}
input[type=checkbox],input[type=radio]{width:auto;min-height:0;accent-color:var(--ink)}
input::placeholder{color:#9a9893}
label{display:block;font-size:12.5px;font-weight:600;letter-spacing:0;text-transform:none;color:var(--gray);margin:0 0 6px}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px;background:#ece9e3;color:var(--gray);white-space:nowrap}
.pill.live{background:var(--green-soft);color:var(--green)}
.pill.dead{background:var(--red-soft);color:var(--red)}
.pill.warn{background:var(--amber-soft);color:var(--amber)}
.pill.own{background:var(--blue-soft);color:var(--blue)}
.pill.dot::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.badge{display:inline-flex;align-items:center;justify-content:center;min-width:19px;height:19px;padding:0 6px;border-radius:10px;background:var(--red);color:#fff;font-size:11px;font-weight:700}
.badge[hidden]{display:none}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--gray);padding:0 12px 10px;border-bottom:1px solid var(--line-strong);white-space:nowrap}
td{padding:12px;border-bottom:1px solid var(--line);vertical-align:middle}
tbody tr:hover td{background:#faf9f6}
tr:last-child td{border-bottom:0}
code{font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace;background:#efece6;padding:2px 6px;border-radius:6px}
.note,.err,.ok{display:flex;gap:10px;align-items:flex-start;border-radius:12px;padding:13px 16px;margin:0 0 18px;border:1px solid}
.note{background:#fffaf0;border-color:#f0dfb4}
.err{background:var(--red-soft);border-color:#f3bcbc;color:#8a1212}
.ok{background:var(--green-soft);border-color:#b6e0c4;color:#0f5f31}
.price-hint{font-size:12.5px;color:var(--gray);margin-top:5px}
.tabs{display:flex;gap:2px;margin:6px 0 20px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.tabs a{padding:10px 15px;text-decoration:none;color:var(--gray);font-weight:600;border-bottom:2px solid transparent;margin-bottom:-1px}
.tabs a:hover{color:var(--ink)}
.tabs a.on{color:var(--ink);border-bottom-color:var(--ink)}
.savebar{position:sticky;bottom:0;z-index:20;background:rgba(245,243,239,.94);backdrop-filter:blur(6px);padding:14px 0;display:flex;gap:10px;border-top:1px solid var(--line-strong);margin-top:24px}
.toast{position:fixed;right:20px;bottom:20px;z-index:80;max-width:380px;padding:14px 18px;border-radius:14px;background:var(--ink);color:#fff;box-shadow:0 12px 32px rgba(0,0,0,.28);font-size:14px}
.toast a{color:var(--lime);font-weight:600;text-decoration:none}
/* ---- stepper / checklist / empty ---- */
.stepper{display:flex;flex-wrap:wrap;gap:6px 0;list-style:none;margin:0 0 22px;padding:0;counter-reset:s}
.stepper li{display:flex;align-items:center;gap:10px;font-weight:600;font-size:13.5px;color:var(--gray);padding-right:14px}
.stepper li:not(:last-child)::after{content:"";width:34px;height:2px;background:var(--line-strong);margin-left:4px;border-radius:2px}
.stepper .dot{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;background:#ece9e3;color:var(--gray);font-size:13px;flex:none}
.stepper li.done .dot{background:var(--green);color:#fff}
.stepper li.now .dot{background:var(--ink);color:var(--lime)}
.stepper li.now{color:var(--ink)}
.stepper li.done:not(:last-child)::after{background:var(--green)}
.todo{list-style:none;margin:0;padding:0}
.todo li{display:flex;align-items:center;gap:14px;padding:13px 0;border-top:1px solid var(--line)}
.todo li:first-child{border-top:0}
.todo .mark{flex:none;width:26px;height:26px;border-radius:50%;display:grid;place-items:center;background:#ece9e3;color:var(--gray)}
.todo li.done .mark{background:var(--green);color:#fff}
.todo .what{flex:1;min-width:0}
.todo .what b{display:block}
.todo .what span{color:var(--gray);font-size:13px}
.todo li.done .what b{color:var(--gray);text-decoration:line-through;text-decoration-thickness:1px}
.empty-state{display:grid;justify-items:center;text-align:center;gap:8px;padding:44px 20px;color:var(--gray)}
.empty-state .ei{width:54px;height:54px;border-radius:50%;background:var(--linen);color:var(--ink);display:grid;place-items:center;margin-bottom:6px}
.empty-state h3{margin:0;color:var(--ink);font-size:17px}
.empty-state p{margin:0 0 8px;max-width:48ch}
/* ---- charts ---- */
.bar-chart{width:100%;height:auto;display:block}
.bar-chart .bg{fill:#ece9e3}
.hbar{display:grid;grid-template-columns:minmax(110px,190px) 1fr auto;gap:12px;align-items:center;padding:7px 0;font-size:14px}
.hbar .track{height:10px;border-radius:999px;background:#ece9e3;overflow:hidden}
.hbar .fill{display:block;height:100%;border-radius:999px;background:var(--ink)}
.hbar .n{font-variant-numeric:tabular-nums;color:var(--gray);min-width:44px;text-align:right}
.stack{display:flex;height:14px;border-radius:999px;overflow:hidden;background:#ece9e3}
.stack i{display:block;height:100%}
/* ---- command palette + help ---- */
dialog#pal{border:0;padding:0;border-radius:18px;width:min(640px,calc(100vw - 32px));margin:12vh auto auto;box-shadow:0 30px 80px rgba(0,0,0,.35);background:var(--white);color:var(--ink)}
dialog#pal::backdrop{background:rgba(18,18,18,.5)}
.pal-in{display:flex;align-items:center;gap:12px;padding:16px 18px;border-bottom:1px solid var(--line)}
.pal-in input{border:0;min-height:30px;padding:0;font-size:16px;outline:none}
.pal-list{list-style:none;margin:0;padding:8px;max-height:52vh;overflow:auto}
.pal-list li a{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:10px;text-decoration:none}
.pal-list li a small{color:var(--gray);margin-left:auto}
.pal-list li a[aria-selected=true],.pal-list li a:hover{background:#f1efea}
.pal-list h4{margin:10px 12px 4px;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.pal-foot{padding:10px 18px;border-top:1px solid var(--line);font-size:12px;color:var(--gray)}
aside#help{position:fixed;top:0;right:0;bottom:0;width:min(440px,100vw);background:var(--white);border-left:1px solid var(--line-strong);box-shadow:-18px 0 50px rgba(0,0,0,.16);z-index:70;display:flex;flex-direction:column;transform:translateX(105%);transition:transform .22s ease;visibility:hidden}
aside#help.open{transform:none;visibility:visible}
aside#help header{display:flex;justify-content:space-between;align-items:center;padding:18px 20px;border-bottom:1px solid var(--line)}
aside#help header h2{margin:0;font-size:18px}
aside#help .body{padding:8px 16px 28px;overflow:auto}
.guide-item{border-bottom:1px solid var(--line)}
.guide-item summary{display:flex;align-items:center;gap:12px;padding:15px 6px;cursor:pointer;font-weight:700;list-style:none}
.guide-item summary::-webkit-details-marker{display:none}
.guide-item ol{margin:0 0 14px;padding:0 0 0 6px;list-style:none;display:grid;gap:4px}
.guide-item ol a{display:grid;gap:2px;padding:10px 12px;border-radius:10px;text-decoration:none;background:#f7f5f1}
.guide-item ol a:hover{background:#efece5}
.guide-item ol span{color:var(--gray);font-size:13px}
/* ---- home ---- */
.home-grid{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(280px,1fr);gap:20px;align-items:start}
.home-grid.even{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
@media(max-width:1100px){.home-grid,.home-grid.even{grid-template-columns:1fr}}
.journeys{display:grid;gap:8px}
.jbtn{display:grid;grid-template-columns:auto 1fr;grid-template-rows:auto auto;column-gap:14px;align-items:center;padding:13px 16px;border-radius:14px;border:1px solid var(--line-strong);text-decoration:none;background:var(--white)}
.jbtn span{grid-row:1/3;width:40px;height:40px;border-radius:12px;background:var(--linen);display:grid;place-items:center}
.jbtn b{font-size:15px}
.jbtn small{color:var(--gray);font-size:12.5px}
.jbtn:hover{border-color:var(--ink)}
.jbtn.primary{background:var(--lime);border-color:var(--lime)}
.jbtn.primary span{background:var(--ink);color:var(--lime)}
.jbtn.primary:hover{background:var(--ink);border-color:var(--ink);color:#fff}
.jbtn.primary:hover small{color:rgba(255,255,255,.7)}
.pipe{display:flex;flex-wrap:wrap;gap:8px 28px;margin-top:16px}
.pipe a{display:flex;align-items:center;gap:9px;text-decoration:none}
.pipe i{width:11px;height:11px;border-radius:3px}
.pipe b{font:400 28px/1 "Bebas Neue",Arial,sans-serif}
.pipe span{color:var(--gray)}
.lc{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.2fr);gap:16px;align-items:center;padding:14px 0;border-top:1px solid var(--line);text-decoration:none}
.lc:first-of-type{border-top:0}
.lc b{display:block}
.lc-bars{display:grid;grid-template-columns:auto 1fr auto;gap:6px 10px;align-items:center;font-size:12.5px;color:var(--gray)}
.lc-bars .track{height:8px;border-radius:999px;background:#ece9e3;overflow:hidden}
.lc-bars .track i{display:block;height:100%;border-radius:999px}
.lc-bars em{font-style:normal;font-variant-numeric:tabular-nums;color:var(--ink);font-weight:600;min-width:38px;text-align:right}
.feed{list-style:none;margin:14px 0 0;padding:0}
.feed li{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-top:1px solid var(--line);font-size:13.5px}
.feed em{font-style:normal;color:var(--muted);white-space:nowrap}
details.card summary{cursor:pointer;list-style:none}
details.card summary::-webkit-details-marker{display:none}
.tick-list{list-style:none;margin:0 0 4px;padding:0;display:grid;gap:8px}
.tick-list li{position:relative;padding-left:26px}
.tick-list li::before{content:"";position:absolute;left:0;top:5px;width:14px;height:14px;border-radius:50%;background:var(--green-soft) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 14 14'%3E%3Cpath d='m3.5 7.3 2.2 2.2 4.8-4.8' fill='none' stroke='%2314884a' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") center/100% no-repeat}
.dups{padding:6px 18px}
.dup{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;padding:14px 0;border-top:1px solid var(--line)}
.dup:first-child{border-top:0}
.dup-who{display:flex;align-items:center;gap:12px}
.mini-steps{display:flex;gap:5px;margin-bottom:4px}
.mini-steps span{width:20px;height:20px;border-radius:50%;background:#ece9e3;display:grid;place-items:center;color:#fff}
.mini-steps span.on{background:var(--green)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.startbox{border:1px solid var(--line);border-radius:12px;padding:16px;display:flex;flex-direction:column;gap:10px;background:var(--surface-2,transparent)}
.startbox h3{margin:0;font-size:15px}
@media(max-width:760px){.two{grid-template-columns:1fr}}
.inline-add{display:flex;gap:8px;align-items:center}.inline-add input{min-width:220px;flex:1}
.card.flat{border:0;box-shadow:none;padding:0;background:transparent}
.refbox summary{cursor:pointer}.refgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px 24px}.refbox h3{font-size:14px;margin:14px 0 6px}.refbox ul.refs,.refbox ol.src{margin:0;padding-left:18px;font-size:13px;line-height:1.55}
.stat-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:20px}
/* ---- small screens ---- */
.scrim{display:none}
@media (max-width:1000px){
  .app{grid-template-columns:1fr}
  .side{position:fixed;left:0;top:0;width:276px;transform:translateX(-102%);transition:transform .22s ease;box-shadow:20px 0 60px rgba(0,0,0,.35)}
  .app.nav-open .side{transform:none}
  .app.nav-open .scrim{display:block;position:fixed;inset:0;background:rgba(18,18,18,.45);z-index:35}
  .page{padding:20px 16px 90px}
  .bar{padding:0 12px}
  .bar .crumbs{overflow:hidden;text-overflow:ellipsis;flex:0 1 auto}
  .bar .search-btn,.bar .iconbtn{flex:none}
  .bar .grow{flex:1 1 0;min-width:0}
  .search-btn{min-width:0;flex:none;width:38px;padding:0;justify-content:center}
  .search-btn span,.search-btn kbd{display:none}
  .card{overflow-x:auto}
  .ph h1{font-size:34px}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
@media print{.side,.bar,#help,.savebar,#ai-panel{display:none!important}.app{display:block}.page{padding:0}}
/* ---- 2026-10 revamp: reach, read, act ---- */
input[type=checkbox],input[type=radio]{width:18px;height:18px;accent-color:var(--ink)}
@media (pointer:coarse){
  .btn.small,.btn.tiny{min-height:40px;padding:6px 14px}
  input[type=checkbox],input[type=radio]{width:24px;height:24px}
  td a:not(.btn),.crumbs a{display:inline-block;padding:6px 0}
  .iconbtn{min-width:44px;min-height:44px}
}
th.sortable{padding:0}
th.sortable button{all:unset;box-sizing:border-box;display:flex;align-items:center;gap:6px;width:100%;padding:0 12px 10px;cursor:pointer;font:inherit;letter-spacing:inherit;text-transform:inherit;color:inherit}
th.sortable button:focus-visible{outline:2px solid var(--ink);outline-offset:-2px;border-radius:4px}
th.sortable button::after{content:"↕";opacity:.35;font-size:11px}
th.sortable[aria-sort=ascending] button::after{content:"↑";opacity:1}
th.sortable[aria-sort=descending] button::after{content:"↓";opacity:1}
.ai-btn{display:inline-flex;align-items:center;gap:8px;height:38px;padding:0 14px;border-radius:999px;border:1px solid var(--ink);background:var(--ink);color:var(--lime);font:inherit;font-weight:600;font-size:13.5px;cursor:pointer}
.ai-btn:hover{background:#000}
#ai-panel{position:fixed;top:0;right:0;bottom:0;width:min(460px,100vw);background:var(--white);box-shadow:-20px 0 60px rgba(0,0,0,.25);z-index:60;display:flex;flex-direction:column;transform:translateX(105%);transition:transform .2s ease;visibility:hidden}
#ai-panel.open{transform:none;visibility:visible}
#ai-panel header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--line)}
#ai-panel header h2{margin:0;font-size:16px}
#ai-panel iframe{flex:1;border:0;width:100%}
.kbd-help{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;font-size:13.5px;margin:8px 6px}
.kbd-help kbd{font:600 12px "DM Sans",sans-serif;background:var(--paper);border:1px solid var(--line-strong);border-radius:6px;padding:2px 7px}
@media (max-width:1000px){.ai-btn span{display:none}.ai-btn{width:38px;padding:0;justify-content:center}}
@media (max-width:700px){
  table.roster-t tr:not(.editrow){display:block;position:relative;padding:12px 56px 12px 58px;min-height:68px;border-bottom:1px solid var(--line)}
  table.roster-t tr:not(.editrow) td{display:inline;padding:0;border:0;font-size:13px}
  table.roster-t tr:not(.editrow) td:nth-child(1){position:absolute;left:0;top:12px}
  table.roster-t tr:not(.editrow) td:nth-child(1) img,table.roster-t tr:not(.editrow) td:nth-child(1) .shot{width:46px!important;height:46px!important;border-radius:10px;object-fit:cover}
  table.roster-t tr:not(.editrow) td:nth-child(2){display:block}
  table.roster-t tr:not(.editrow) td:nth-child(3){display:block;font-size:15px}
  table.roster-t tr:not(.editrow) td:nth-child(n+4):nth-child(-n+6)::after{content:" · ";color:var(--muted)}
  table.roster-t tr:not(.editrow) td:nth-child(4) br{display:none}
  table.roster-t tr:not(.editrow) td:last-child{position:absolute;right:0;top:12px}
}
"""


def _filter_legacy(css):
    """The previous stylesheet, minus the rules that belonged to the old top
    bar and page frame (the new shell owns those). Everything else keeps working
    for the page bodies that have not been rebuilt yet."""
    drop = re.compile(r"^(:root|\*|html|body|a|header\.top|\.brand|\.login|nav|\.wrap|h1|h2|\.sub|\.toast|\.badge|"
                      r"\.btn|\.pill|\.card|label|input|textarea|select|th|td|table|code|\.tabs|\.stat|\.kpis|"
                      r"\.savebar|\.note|\.err|\.ok|\.price-hint|tr:last-child|input:focus)")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    # split into top-level blocks
    blocks, start, depth = [], 0, 0
    for idx, ch in enumerate(css):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blocks.append(css[start:idx + 1])
                start = idx + 1
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        if b.startswith("@media") or b.startswith("@keyframes"):
            # the old frame's rules inside media queries go too
            b = re.sub(r"header\.top[^{}]*\{[^}]*\}|(?<![\w.#-])nav[^{}]*\{[^}]*\}|\.wrap[^{}]*\{[^}]*\}", "", b)
            out.append(b)
            continue
        selector = b.split("{", 1)[0].strip()
        first = selector.split(",")[0].strip()
        if drop.match(first) and not first.startswith(("nav a", ".brand span")):
            continue
        out.append(b)
    return "\n".join(out)


def build_css(legacy):
    new = _NEW.replace("__FONTS__", FONTS)
    return new.split("/* ---- sidebar ---- */")[0] + _filter_legacy(legacy) + "\n/* ---- sidebar ---- */" + \
        new.split("/* ---- sidebar ---- */", 1)[1]


# --------------------------------------------------------------- components --
def header(title, desc="", crumbs=None, actions="", tabs=None):
    """Page header: title, one-line description, primary actions, tabs.
    crumbs: [(label, href or None)]. tabs: [(href, label, count, current)]."""
    out = ""
    if crumbs:
        parts = []
        for label, href in crumbs:
            parts.append('<a href="%s">%s</a>' % (e(href), e(label)) if href else "<b>%s</b>" % e(label))
        out += '<nav class="crumbs" aria-label="Breadcrumb" style="margin:0 0 8px">%s</nav>' % " <i>/</i> ".join(parts)
    out += '<div class="ph"><div><h1>%s</h1>%s</div>%s</div>' % (
        e(title), '<p class="desc">%s</p>' % desc if desc else "",
        '<div class="ph-actions">%s</div>' % actions if actions else "")
    if tabs:
        out += ptabs(tabs)
    return out


def ptabs(tabs):
    items = []
    for href, label, count, current in tabs:
        n = '<span class="n">%s</span>' % e(count) if count not in (None, "") else ""
        items.append('<a href="%s"%s>%s%s</a>' % (e(href), ' aria-current="page"' if current else "", e(label), n))
    return '<nav class="ptabs" aria-label="Sections">%s</nav>' % "".join(items)


def tabset(tid, tabs, panels, first=None):
    """In-page tabs: all panels live in one form or page, the tab hides the
    others. tabs: [(key, label, count)]; panels: {key: html}."""
    first = first or tabs[0][0]
    bar = "".join('<button type="button" role="tab" data-tab="%s" aria-selected="%s">%s%s</button>' % (
        e(k), "true" if k == first else "false", e(lbl),
        '<span class="n">%s</span>' % e(c) if c not in (None, "") else "") for k, lbl, c in tabs)
    body = "".join('<div class="panel" data-panel="%s"%s>%s</div>' % (e(k), "" if k == first else " hidden", panels.get(k, ""))
                   for k, _l, _c in tabs)
    return '<div data-tabs="%s"><nav class="ptabs" role="tablist">%s</nav>%s</div>' % (e(tid), bar, body)


def tab_nav(tid, tabs, first=None):
    """Just the tab bar, for pages whose panels are not contiguous (a form
    wraps some of them). Pair with panel()."""
    first = first or tabs[0][0]
    bar = "".join('<button type="button" role="tab" data-tab="%s" aria-selected="%s">%s%s</button>' % (
        e(k), "true" if k == first else "false", e(lbl),
        '<span class="n">%s</span>' % e(c) if c not in (None, "") else "") for k, lbl, c in tabs)
    return '<nav class="ptabs" role="tablist">%s</nav>' % bar


def panel(key, html_, first=None, open_=False):
    return '<div class="panel" data-panel="%s"%s>%s</div>' % (e(key), "" if open_ else " hidden", html_)


def empty(ic, title, text, action=""):
    return ('<div class="empty-state"><span class="ei">%s</span><h3>%s</h3><p>%s</p>%s</div>'
            % (icon(ic, 24), e(title), text, action))


def stepper(steps):
    """steps: [(label, state)] with state 'done' | 'now' | 'todo'."""
    lis = []
    for i, (label, st) in enumerate(steps, 1):
        dot = icon("check", 15) if st == "done" else str(i)
        lis.append('<li class="%s"><span class="dot">%s</span>%s</li>' % (st, dot, e(label)))
    return '<ol class="stepper" aria-label="Progress">%s</ol>' % "".join(lis)


def hbars(rows, color="var(--ink)"):
    """rows: [(label, value, display)] -> horizontal bars scaled to the largest."""
    peak = max([v for _l, v, _d in rows] + [1])
    return "".join('<div class="hbar"><span>%s</span><span class="track"><i class="fill" style="width:%.1f%%;background:%s"></i></span>'
                   '<span class="n">%s</span></div>' % (e(l), v / float(peak) * 100, color, e(d)) for l, v, d in rows)


def column_chart(values, labels=None, height=120, color="#121212"):
    """Small column chart for a series (events per day...)."""
    n = len(values) or 1
    peak = max(values + [1])
    w, gap = 640.0, 4.0
    bw = (w - gap * (n - 1)) / n
    bars = ""
    for i, v in enumerate(values):
        h = max(2.0, v / float(peak) * (height - 22))
        x = i * (bw + gap)
        bars += '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="%s"><title>%s: %s</title></rect>' % (
            x, height - 18 - h, bw, h, color, e(labels[i]) if labels else i + 1, v)
    ticks = ""
    if labels:
        for i in (0, n // 2, n - 1):
            ticks += '<text x="%.1f" y="%d" font-size="11" fill="#8a8984" text-anchor="%s">%s</text>' % (
                i * (bw + gap) + (bw / 2 if 0 < i < n - 1 else 0 if i == 0 else bw), height - 3,
                "middle" if 0 < i < n - 1 else ("start" if i == 0 else "end"), e(labels[i]))
    return '<svg class="bar-chart" viewBox="0 0 %d %d" role="img" aria-label="Chart">%s%s</svg>' % (w, height, bars, ticks)


# ----------------------------------------------------------------------- shell --
_JS = r"""
(function(){
  var app=document.querySelector('.app'), $=function(s,r){return (r||document).querySelector(s)}, $$=function(s,r){return [].slice.call((r||document).querySelectorAll(s))};
  // sidebar: collapse on desktop, drawer on small screens
  try{ if(localStorage.getItem('hv_side')==='1') app.classList.add('is-collapsed'); }catch(e){}
  var sb=$('#side-toggle'); if(sb) sb.addEventListener('click',function(){
    if(window.innerWidth<=1000){ app.classList.toggle('nav-open'); return; }
    app.classList.toggle('is-collapsed'); try{ localStorage.setItem('hv_side',app.classList.contains('is-collapsed')?'1':'0'); }catch(e){} });
  var sc=$('.scrim'); if(sc) sc.addEventListener('click',function(){app.classList.remove('nav-open');});
  // in-page tabs
  $$('[data-tabs]').forEach(function(box){
    var tabs=$$('[data-tab]',box), panels=$$('[data-panel]',box);
    function show(k,push){ tabs.forEach(function(t){t.setAttribute('aria-selected',t.dataset.tab===k?'true':'false');});
      panels.forEach(function(p){p.hidden=p.dataset.panel!==k;}); if(push){ try{history.replaceState(null,'','#'+box.dataset.tabs+'='+k);}catch(e){} } }
    tabs.forEach(function(t){t.addEventListener('click',function(){show(t.dataset.tab,true);});});
    var m=(location.hash||'').match(new RegExp('[#&]'+box.dataset.tabs+'=([a-z0-9_-]+)'));
    if(m && tabs.some(function(t){return t.dataset.tab===m[1];})) show(m[1],false);
    box.addEventListener('hv-show',function(ev){show(ev.detail,true);});
  });
  $$('[data-go-tab]').forEach(function(b){b.addEventListener('click',function(ev){ev.preventDefault();
    var box=$('[data-tabs="'+b.dataset.goTab.split(':')[0]+'"]'); if(box) box.dispatchEvent(new CustomEvent('hv-show',{detail:b.dataset.goTab.split(':')[1]}));
    window.scrollTo({top:0,behavior:'smooth'});});});
  // copy buttons
  $$('[data-copy]').forEach(function(b){b.addEventListener('click',function(){var t=$(b.dataset.copy); if(!t) return;
    var v=t.value||t.textContent; (navigator.clipboard?navigator.clipboard.writeText(v):Promise.reject()).then(function(){toast('Copied');},function(){t.select&&t.select();});});});
  // confirm before destructive forms
  $$('form[data-confirm]').forEach(function(f){f.addEventListener('submit',function(ev){if(!confirm(f.dataset.confirm)) ev.preventDefault();});});
  // toast
  var tt=$('#hv-toast'); window.hvToast=toast; function toast(msg){ if(!tt) return; tt.textContent=msg; tt.hidden=false; clearTimeout(tt._h); tt._h=setTimeout(function(){tt.hidden=true;},2600); }
  // help drawer
  var help=$('#help'), hb=$('#help-toggle');
  function setHelp(o){ help.classList.toggle('open',o); if(hb) hb.setAttribute('aria-expanded',o?'true':'false'); if(o){ var s=$('summary',help); s&&s.focus(); } }
  if(hb) hb.addEventListener('click',function(){setHelp(!help.classList.contains('open'));});
  $('#help-close')&&$('#help-close').addEventListener('click',function(){setHelp(false);});
  // command palette
  var pal=$('#pal'), inp=$('#pal-q'), list=$('#pal-list'), sel=0, items=[], timer=null, base=window.HV_SEARCH||'';
  var PAGES=window.HV_PAGES||[];
  function render(groups){ items=[]; var h=''; groups.forEach(function(g){ if(!g.items.length) return; h+='<h4>'+g.title+'</h4>';
      g.items.forEach(function(it){ items.push(it); h+='<li><a href="'+it.href+'" data-i="'+(items.length-1)+'"><span>'+it.label+'</span><small>'+(it.hint||'')+'</small></a></li>'; }); });
    list.innerHTML=h||'<li style="padding:18px;color:#5a5a58">Nothing found. Try a creator name, a client or a page.</li>'; sel=0; mark(); }
  function mark(){ $$('#pal-list a').forEach(function(a,i){a.setAttribute('aria-selected',i===sel?'true':'false');}); var a=$$('#pal-list a')[sel]; a&&a.scrollIntoView({block:'nearest'}); }
  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function pages(q){ q=q.toLowerCase(); return PAGES.filter(function(p){return !q||(p.label+' '+(p.kw||'')).toLowerCase().indexOf(q)>=0;}).slice(0,8).map(function(p){return {href:p.href,label:esc(p.label),hint:p.hint||'Page'};}); }
  function search(q){ var pg=pages(q); render([{title:'Go to',items:pg}]);
    if(q.length<2) return; clearTimeout(timer); timer=setTimeout(function(){ fetch(base+'?q='+encodeURIComponent(q),{credentials:'same-origin'}).then(function(r){return r.json();}).then(function(d){
      if(inp.value!==q) return; render([{title:'Go to',items:pg}].concat(['creators','selections','campaigns','clients'].map(function(k){return {title:k.charAt(0).toUpperCase()+k.slice(1),items:(d[k]||[]).map(function(x){return {href:x.href,label:esc(x.label),hint:esc(x.hint||'')};})};}))); }).catch(function(){}); },160); }
  function openPal(){ if(!pal.open) pal.showModal(); inp.value=''; search(''); inp.focus(); }
  $$('[data-open-search]').forEach(function(b){b.addEventListener('click',openPal);});
  document.addEventListener('keydown',function(ev){ var tag=(ev.target.tagName||'').toLowerCase(), typing=tag==='input'||tag==='textarea'||tag==='select'||ev.target.isContentEditable;
    if((ev.metaKey||ev.ctrlKey)&&ev.key.toLowerCase()==='k'){ev.preventDefault(); openPal();}
    else if(ev.key==='/'&&!typing){ev.preventDefault(); openPal();}
    else if(ev.key==='Escape'){ help&&help.classList.contains('open')&&setHelp(false); app.classList.remove('nav-open'); } });
  if(inp){ inp.addEventListener('input',function(){search(inp.value.trim());});
    inp.addEventListener('keydown',function(ev){ var n=items.length; if(ev.key==='ArrowDown'){ev.preventDefault(); sel=Math.min(n-1,sel+1); mark();} else if(ev.key==='ArrowUp'){ev.preventDefault(); sel=Math.max(0,sel-1); mark();}
      else if(ev.key==='Enter'&&items[sel]){ev.preventDefault(); location.href=items[sel].href;} }); }
  if(pal) pal.addEventListener('click',function(ev){ if(ev.target===pal) pal.close(); });
})();
"""


def shell(title, body, active, u, name, pulse, pulse_payload, pulse_js, user_email=""):
    """The whole page: sidebar, top bar, content, palette, help, scripts."""
    group, a_href, a_label = _active_item(active)

    def badge(key):
        if key == "req":
            n = pulse.get("open", 0)
            return '<span class="badge" id="req-badge"%s>%s</span>' % ("" if n else " hidden", n)
        if key == "an":
            n = pulse.get("a_open", 0)
            return '<span class="badge" id="an-badge"%s>%s</span>' % ("" if n else " hidden", n)
        return ""

    nav = ""
    open_parent = PARENT.get(a_href, a_href)
    for gname, items in NAV:
        links = ""
        for href, label, ic, bk in items:
            kids = CHILDREN.get(href, [])
            in_family = open_parent == href
            links += '<a class="nav-item" href="%s"%s title="%s">%s<span class="t">%s</span>%s</a>' % (
                u(href), ' aria-current="page"' if href == a_href else (' aria-current="true"' if in_family and kids else ""),
                e(label), icon(ic, 19), e(label), badge(bk) if not (kids and not in_family) else
                "".join(badge(k[2]) for k in kids if k[2]) + badge(bk))
            if kids and in_family:
                links += "".join('<a class="nav-item nav-sub" href="%s"%s>%s<span class="t">%s</span>%s</a>' % (
                    u(ch), ' aria-current="page"' if ch == a_href else "", "", e(cl), badge(cb)) for ch, cl, cb in kids)
        nav += '<div class="nav-group">%s%s</div>' % ('<div class="nav-title">%s</div>' % e(gname) if gname else "", links)

    bell_n = pulse.get("open", 0) + pulse.get("a_open", 0)
    pages_js = json.dumps([{"href": u(h), "label": l, "hint": g or "Home", "kw": ""} for g, its in NAV for h, l, _i, _b in its]
                          + [{"href": u(c[0]), "label": c[1], "hint": "Go to", "kw": ""} for kids in CHILDREN.values() for c in kids]
                          + [{"href": u("/selections"), "label": "New selection", "hint": "Create", "kw": "quote create add"},
                             {"href": u("/campaigns"), "label": "New campaign", "hint": "Create", "kw": "start create add"},
                             {"href": u("/roster"), "label": "Add a creator", "hint": "Create", "kw": "new influencer"},
                             {"href": u("/analysis"), "label": "Import an analysis report", "hint": "Create", "kw": "pdf upload modash"},
                             {"href": u("/roster") + "?tab=duplicates", "label": "Merge duplicate creators", "hint": "Fix", "kw": "dedupe"}])
    crumb = ('<nav class="crumbs" aria-label="Breadcrumb"><a href="%s">Home</a>%s</nav>' % (
        u("/"), (' <i>/</i> <span>%s</span> <i>/</i> <b>%s</b>' % (e(group), e(a_label)) if group and a_label else
                 (' <i>/</i> <b>%s</b>' % e(a_label) if a_label and a_href != "/" else ""))))
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="robots" content="noindex,nofollow">'
        '<meta name="theme-color" content="#121212"><meta name="apple-mobile-web-app-capable" content="yes">'
        '<meta name="apple-mobile-web-app-title" content="HV Admin"><meta name="apple-mobile-web-app-status-bar-style" content="black">'
        '<link rel="manifest" href="' + u("/manifest.webmanifest") + '"><link rel="apple-touch-icon" href="' + u("/static/icon-180.png") + '">'
        '<link rel="icon" href="' + u("/static/icon-32.png") + '">'
        "<title>" + e(title) + " — " + e(name) + '</title><link rel="stylesheet" href="' + u("/static/admin.css") + '"></head><body>'
        '<a class="skip" href="#main">Skip to content</a>'
        '<div class="app"><aside class="side" aria-label="Main">'
        '<a class="logo" href="' + u("/") + '"><img src="' + u("/static/logo-knockout.webp") + '" alt="HelloVoice" height="23"></a>'
        '<nav aria-label="Sections">' + nav + '</nav>'
        '<div class="side-foot"><div class="side-me"><i>' + e((user_email or "A")[:1].upper()) + '</i><span>' + e(user_email or "Admin") + '</span></div>'
        '<a class="nav-item" href="' + u("/logout") + '" title="Sign out">' + icon("arrow", 19) + '<span class="t">Sign out</span></a></div>'
        '</aside><div class="scrim"></div>'
        '<div class="main"><header class="bar">'
        '<button class="iconbtn" id="side-toggle" type="button" aria-label="Toggle sidebar">' + icon("panel", 20) + '</button>'
        + crumb +
        '<span class="grow"></span>'
        '<button class="ai-btn" type="button" id="ai-toggle" aria-controls="ai-panel" aria-expanded="false" title="AI copilot (press A)">'
        + icon("star", 16) + '<span>Ask AI</span></button>'
        '<button class="search-btn" type="button" data-open-search aria-label="Search">' + icon("search", 17) + '<span>Search creators, selections…</span><kbd>⌘K</kbd></button>'
        '<a class="iconbtn" href="' + u("/requests") + '" aria-label="Inbox">' + icon("bell", 20)
        + ('<span class="badge">%d</span>' % bell_n if bell_n else "") + '</a>'
        '<button class="iconbtn" id="help-toggle" type="button" aria-label="Guides" aria-expanded="false" aria-controls="help">' + icon("help", 20) + '</button>'
        '</header><main class="page" id="main">' + body + '</main></div></div>'
        '<dialog id="pal" aria-label="Search"><div class="pal-in">' + icon("search", 20) + '<input id="pal-q" type="search" placeholder="Search creators, selections, campaigns, clients, pages…" autocomplete="off"></div>'
        '<ul class="pal-list" id="pal-list"></ul><div class="pal-foot">↑↓ to move · Enter to open · Esc to close · <b>/</b> search · <b>A</b> AI copilot · <b>?</b> shortcuts</div></dialog>'
        '<aside id="help" aria-label="Guides"><header><h2>How do I…?</h2><button class="iconbtn" id="help-close" type="button" aria-label="Close guides" style="border:0;background:transparent;cursor:pointer">'
        + icon("plus", 20, "x") + '</button></header><div class="body"><p class="muted" style="margin:8px 6px 4px">Step by step, for anything you do here. Every change can be undone from History.</p>'
        + _guides_html(u) + _SHORTCUTS_HTML + '</div></aside>'
        '<aside id="ai-panel" aria-label="AI copilot" data-src="' + u("/ai?embed=1") + '"><header><h2>AI copilot</h2>'
        '<span><a class="btn small ghost" href="' + u("/ai") + '">Full page</a> <button class="iconbtn" id="ai-close" type="button" aria-label="Close AI copilot">'
        + icon("plus", 20, "x") + '</button></span></header></aside>'
        "<div class='toast' id='req-toast' role='status' hidden></div><div class='toast' id='hv-toast' role='status' hidden></div>"
        '<style>aside#help .x,#ai-panel .x{transform:rotate(45deg)}</style>'
        "<script>window.HV_SEARCH=" + json.dumps(u("/api/search")) + ";window.HV_PAGES=" + pages_js
        + ";window.HV_PULSE=" + json.dumps(pulse_payload) + ";</script>"
        "<script>" + _RECENT_JS + "</script><script>" + _JS + "</script><script>" + _JS_REVAMP + "</script><script>" + pulse_js + "</script></body></html>"
    )


_SHORTCUTS_HTML = (
    '<details style="margin:14px 6px 0"><summary><b>Keyboard shortcuts</b></summary><div class="kbd-help">'
    '<kbd>/</kbd><span>Search anything</span><kbd>⌘K</kbd><span>Search anything</span><kbd>A</kbd><span>Open the AI copilot</span>'
    '<kbd>G H</kbd><span>Home</span><kbd>G S</kbd><span>Selections</span><kbd>G C</kbd><span>Campaigns</span>'
    '<kbd>G R</kbd><span>Creators</span><kbd>G Q</kbd><span>Quote requests</span><kbd>G P</kbd><span>Client portal</span>'
    '<kbd>?</kbd><span>These guides</span><kbd>Esc</kbd><span>Close panels</span></div></details>')

# Recently opened pages go to the top of the search palette (this browser only).
_RECENT_JS = r"""
(function(){ try{
  var KEY='hv_recent', here={href:location.pathname+location.search,label:document.title.split(' — ')[0],hint:'Recent',kw:''};
  var list=JSON.parse(localStorage.getItem(KEY)||'[]').filter(function(x){return x.href!==here.href;});
  if(!/\/(login|logout)/.test(here.href)) { list.unshift(here); localStorage.setItem(KEY, JSON.stringify(list.slice(0,8))); }
  window.HV_PAGES=list.slice(1,6).concat(window.HV_PAGES||[]);
}catch(e){} })();
"""

_JS_REVAMP = r"""
(function(){
  var $=function(s,r){return (r||document).querySelector(s)}, $$=function(s,r){return [].slice.call((r||document).querySelectorAll(s))};
  // 1. Every field has a name a screen reader can say: tie each bare <label> to the field after it,
  //    and name fields that only have a placeholder.
  var n=0;
  $$('label:not([for])').forEach(function(l){
    if(l.querySelector('input,select,textarea')) return;
    var f=l.nextElementSibling;
    while(f && !/^(INPUT|SELECT|TEXTAREA)$/.test(f.tagName)){ var inner=f.querySelector&&f.querySelector('input:not([type=hidden]),select,textarea'); if(inner&&!f.matches('label')){f=inner;break;} f=f.nextElementSibling===null?null:f.nextElementSibling; if(f&&f.tagName==='LABEL'){f=null;} }
    if(!f || f.type==='hidden') return;
    if(!f.id) f.id='fld-'+(++n);
    l.setAttribute('for', f.id);
  });
  $$('input:not([type=hidden]),select,textarea').forEach(function(f){
    if(f.labels&&f.labels.length) return;
    if(f.getAttribute('aria-label')||f.getAttribute('aria-labelledby')) return;
    var t=f.getAttribute('placeholder')||f.getAttribute('title')||f.getAttribute('name');
    if(t) f.setAttribute('aria-label', t.replace(/[_-]/g,' '));
  });
  // 2. Sort any list table by a column header click (tables with expandable edit rows are left alone).
  function key(td){ var t=(td.getAttribute('data-sort')||td.textContent||'').trim();
    var m=t.replace(/,/g,'').match(/^(-?\d+(?:\.\d+)?)\s*([KkMm%])?/);
    if(m){ var v=parseFloat(m[1]); if(/[Kk]/.test(m[2]||'')) v*=1e3; if(/[Mm]/.test(m[2]||'')) v*=1e6; return {n:v}; }
    var d=Date.parse(t); if(!isNaN(d) && /\d{4}|\d{1,2} [A-Z][a-z]{2}/.test(t)) return {n:d};
    return {s:t.toLowerCase()}; }
  $$('main table').forEach(function(tb){
    var head=tb.tHead, body=tb.tBodies[0]; if(!head||!body||tb.hasAttribute('data-nosort')) return;
    var rows=[].slice.call(body.rows); if(rows.length<3) return;
    if(rows.some(function(r){return r.querySelector('td[colspan]');})) return;
    var ths=[].slice.call(head.rows[head.rows.length-1].cells);
    ths.forEach(function(th,i){ var label=th.textContent.trim(); if(!label||th.querySelector('input,button,a')) return;
      th.classList.add('sortable'); th.setAttribute('aria-sort','none');
      var b=document.createElement('button'); b.type='button'; b.textContent=label; b.setAttribute('aria-label','Sort by '+label); th.textContent=''; th.appendChild(b);
      b.addEventListener('click',function(){
        var dir=th.getAttribute('aria-sort')==='ascending'?-1:1;
        ths.forEach(function(o){ if(o.classList.contains('sortable')) o.setAttribute('aria-sort','none'); });
        th.setAttribute('aria-sort', dir===1?'ascending':'descending');
        var rs=[].slice.call(body.rows);
        rs.sort(function(a,b2){ var x=key(a.cells[i]||a), y=key(b2.cells[i]||b2);
          if(x.n!==undefined&&y.n!==undefined) return (x.n-y.n)*dir;
          if(x.n!==undefined) return -1; if(y.n!==undefined) return 1;
          return (x.s||'').localeCompare(y.s||'')*dir; });
        rs.forEach(function(r){body.appendChild(r);});
      });
    });
  });
  // 2b. My views: save the filters in the address bar under a name, per page, in this browser.
  (function(){ var ph=$('main .ph'); if(!ph) return; var KEY='hv_views', path=location.pathname, all={};
    try{ all=JSON.parse(localStorage.getItem(KEY)||'{}'); }catch(e){}
    var mine=all[path]||[], q=location.search.replace(/[?&](ok|e)=[^&]*/g,'').replace(/^&/,'?');
    if(!mine.length && (!q||q==='?')) return;
    var bar=document.createElement('div'); bar.className='views'; bar.setAttribute('aria-label','My views');
    function save(){ try{ all[path]=mine; localStorage.setItem(KEY, JSON.stringify(all)); }catch(e){} }
    function draw(){ bar.innerHTML='';
      if(mine.length){ var t=document.createElement('span'); t.className='muted'; t.textContent='My views:'; bar.appendChild(t); }
      mine.forEach(function(v,i){ var a=document.createElement('a'); a.className='pill'; a.href=path+v.q; a.textContent=v.name; bar.appendChild(a);
        var x=document.createElement('button'); x.type='button'; x.className='vx'; x.setAttribute('aria-label','Remove view '+v.name); x.textContent='×';
        x.onclick=function(){ mine.splice(i,1); save(); draw(); }; bar.appendChild(x); });
      if(q && q!=='?' && !mine.some(function(v){return v.q===q;})){ var b=document.createElement('button'); b.type='button'; b.className='btn tiny ghost'; b.textContent='Save this view';
        b.onclick=function(){ var n=prompt('Name this view'); if(!n) return; mine.push({name:n.slice(0,40),q:q}); save(); draw(); }; bar.appendChild(b); } }
    draw(); ph.insertAdjacentElement('afterend', bar);
  })();
  // 3. The AI copilot opens beside any page.
  var panel=$('#ai-panel'), tog=$('#ai-toggle'), frame=null;
  function setAI(o){ if(!panel) return;
    if(o && !frame){ frame=document.createElement('iframe'); frame.title='AI copilot'; frame.src=panel.getAttribute('data-src'); panel.appendChild(frame); }
    panel.classList.toggle('open',o); if(tog) tog.setAttribute('aria-expanded',o?'true':'false');
    if(o&&frame){ setTimeout(function(){ try{ var t=frame.contentDocument.getElementById('cp-text'); t&&t.focus(); }catch(e){} },300); } }
  if(tog) tog.addEventListener('click',function(){ setAI(!panel.classList.contains('open')); });
  var ac=$('#ai-close'); if(ac) ac.addEventListener('click',function(){ setAI(false); });
  // 4. Shortcuts: A = AI, ? = guides, G then a letter = go to a section.
  var go={h:'/',s:'/selections',c:'/campaigns',r:'/roster',q:'/requests',p:'/portal',a:'/analytics'}, base=(document.querySelector('.logo')||{}).getAttribute? document.querySelector('.logo').getAttribute('href').replace(/\/$/,''):'';
  var gArmed=0;
  document.addEventListener('keydown',function(ev){
    var tag=(ev.target.tagName||'').toLowerCase(); if(tag==='input'||tag==='textarea'||tag==='select'||ev.target.isContentEditable||ev.metaKey||ev.ctrlKey||ev.altKey) return;
    var k=ev.key.toLowerCase();
    if(ev.key==='Escape'){ setAI(false); return; }
    if(gArmed && go[k]){ ev.preventDefault(); location.href=base+(go[k]==='/'?'/':go[k]); return; }
    gArmed=0;
    if(k==='g'){ gArmed=1; setTimeout(function(){gArmed=0;},1200); return; }
    if(k==='a'){ ev.preventDefault(); setAI(true); }
    if(ev.key==='?'){ ev.preventDefault(); var hb=$('#help-toggle'); hb&&hb.click(); }
  });
})();
"""
