"""Admin -> App & alerts (HELVi Connect app, item 168): who has the app and alerts on,
the push composer, history and the automatic rules. Approved mockup:
Portal Programme/mockups/pwa/pwa-mockup.html (2026-10-19)."""
import json
import time

import db
import push
from ui import e, header, icon
from views import page, u

TABS = (("overview", "Overview"), ("send", "Send a push"), ("history", "History"), ("rules", "Automatic rules"))

CSS = """
<style>
.pa-figs{display:grid;grid-template-columns:repeat(5,1fr);background:var(--white);border:1px solid var(--line);border-radius:16px;margin-bottom:18px}
.pa-figs>div{padding:16px 18px;border-left:1px solid var(--line);min-width:0}
.pa-figs>div:first-child{border-left:0}
.pa-figs span{display:block;font-size:11.5px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--gray)}
.pa-figs b{display:block;font:400 40px/1.05 "Bebas Neue",Arial,sans-serif;font-variant-numeric:tabular-nums}
.pa-figs small{display:block;font-size:12.5px;color:var(--gray)}
.pa-figs small.up{color:var(--green)}
.pa-two{display:grid;grid-template-columns:1.25fr 1fr;gap:18px;margin-bottom:18px}
.pa-card{background:var(--white);border:1px solid var(--line);border-radius:16px;padding:18px 20px;min-width:0}
.pa-card h2{margin:0 0 2px;font:400 26px/1.05 "Bebas Neue",Arial,sans-serif;letter-spacing:.02em}
.pa-card>p.muted{margin:0 0 14px;font-size:13px}
.pa-fun{display:grid;gap:9px}
.pa-fr{display:grid;grid-template-columns:160px 1fr 96px;align-items:center;gap:12px;font-size:13.5px}
.pa-fr .bar{height:26px;border-radius:7px;background:var(--paper);overflow:hidden}
.pa-fr .bar i{display:block;height:100%;background:var(--ink);border-radius:7px;min-width:2px}
.pa-fr.hl .bar i{background:#b9d400}
.pa-fr b{font:400 22px/1 "Bebas Neue",Arial,sans-serif;text-align:right}
.pa-fr b small{font:600 11.5px "DM Sans",Arial,sans-serif;color:var(--gray);margin-left:5px}
.pa-split{display:flex;height:34px;border-radius:9px;overflow:hidden;margin:6px 0 12px;background:var(--paper)}
.pa-split i{display:grid;place-items:center;font:400 17px "Bebas Neue",Arial,sans-serif;letter-spacing:.04em;font-style:normal;min-width:0;overflow:hidden}
.pa-leg{display:grid;gap:8px;font-size:13.5px}
.pa-leg div{display:grid;grid-template-columns:14px 1fr auto auto;gap:10px;align-items:center}
.pa-leg s{width:12px;height:12px;border-radius:3px;display:block}
.pa-leg span{color:var(--gray);font-size:12.5px}
.pa-note{margin:14px 0 0;font-size:12.5px;color:var(--gray);border-top:1px solid var(--line);padding-top:12px}
.pa-tools{display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
.pa-tools input[type=search]{flex:1;min-width:200px;height:38px;border-radius:999px;border:1px solid var(--line-strong);padding:0 16px;font:inherit;background:var(--paper)}
.pa-tbl{width:100%;border-collapse:collapse;font-size:13.5px}
.pa-tbl th{text-align:left;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--gray);font-weight:700;padding:10px;border-bottom:1px solid var(--line-strong);background:#faf8f4;white-space:nowrap}
.pa-tbl td{padding:10px;border-bottom:1px solid var(--line);vertical-align:middle}
.pa-who{display:flex;align-items:center;gap:10px}
.pa-who i{width:30px;height:30px;border-radius:50%;background:var(--linen);display:grid;place-items:center;font:700 11px "DM Sans",Arial,sans-serif;font-style:normal;flex:none}
.pa-who b{display:block;white-space:nowrap}
.pa-who span{font-size:12px;color:var(--gray)}
.pa-scroll{overflow-x:auto}
.pa-mini{display:flex;gap:6px;align-items:center;font-size:12.5px;white-space:nowrap}
.pa-mini .b{width:64px;height:6px;border-radius:3px;background:var(--paper);overflow:hidden}
.pa-mini .b i{display:block;height:100%;background:var(--ink)}
.pa-dev{white-space:nowrap;font-size:13px}
.pa-tag{display:inline-block;font-size:11.5px;font-weight:700;border-radius:6px;padding:2px 8px;background:var(--paper);white-space:nowrap}
.pa-tag.auto{background:var(--lime)}
.pa-comp{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:22px;align-items:start}
.pa-f{margin-bottom:16px}
.pa-f>label,.pa-f>.lbl{display:flex;justify-content:space-between;font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--gray);margin-bottom:6px}
.pa-f>label span,.pa-f>.lbl span{letter-spacing:0;text-transform:none;font-weight:600}
.pa-f input[type=text],.pa-f input[type=url],.pa-f textarea,.pa-f select,.pa-f input[type=datetime-local],.pa-f input[type=number]{width:100%;background:var(--white);border:1px solid var(--line-strong);border-radius:12px;padding:11px 14px;font:inherit;font-size:15px}
.pa-f textarea{min-height:84px;resize:vertical}
.pa-f input:focus,.pa-f textarea:focus,.pa-f select:focus{outline:0;border-color:var(--ink);box-shadow:0 0 0 3px rgba(232,255,118,.9)}
.pa-seg{display:flex;flex-wrap:wrap;gap:6px}
.pa-seg label{cursor:pointer}
.pa-seg input{position:absolute;opacity:0;pointer-events:none}
.pa-seg span{height:38px;padding:0 16px;border-radius:999px;display:inline-flex;align-items:center;background:var(--white);box-shadow:inset 0 0 0 1px var(--line-strong);font-size:13.5px;font-weight:600}
.pa-seg input:checked+span{background:var(--ink);color:var(--lime);box-shadow:none}
.pa-seg input:focus-visible+span{outline:3px solid var(--ink);outline-offset:2px}
.pa-pick{margin-top:10px}
.pa-pick[hidden]{display:none}
.pa-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.pa-chips button{display:inline-flex;align-items:center;gap:8px;height:34px;padding:0 6px 0 12px;border-radius:999px;background:var(--linen);font:600 13px "DM Sans",Arial,sans-serif;border:0;cursor:pointer}
.pa-chips button i{width:22px;height:22px;border-radius:50%;background:rgba(18,18,18,.08);display:grid;place-items:center;font-style:normal;font-size:12px}
.pa-reach{margin-top:6px;background:var(--ink);color:#fff;border-radius:16px;padding:16px 18px;display:grid;grid-template-columns:auto 1fr;gap:4px 16px;align-items:center}
.pa-reach b{font:400 46px/1 "Bebas Neue",Arial,sans-serif;color:var(--lime);grid-row:span 2}
.pa-reach small{color:rgba(255,255,255,.7);font-size:12.5px}
.pa-when{display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.pa-when label.r{display:inline-flex;align-items:center;gap:8px;font-weight:600;cursor:pointer}
.pa-when input[type=datetime-local]{width:auto}
.pa-prev{background:var(--linen);border-radius:20px;padding:18px;position:sticky;top:16px}
.pa-prev h3{margin:0 0 10px;font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--gray)}
.pa-ios{background:rgba(255,255,255,.85);border-radius:22px;padding:12px 14px;display:grid;grid-template-columns:38px 1fr;gap:10px;margin-bottom:16px}
.pa-ios img{width:38px;height:38px;border-radius:9px}
.pa-ios .h{display:flex;justify-content:space-between;font-size:13px}
.pa-ios .h span{color:#666;font-size:12px}
.pa-ios .t,.pa-and .t{font-weight:700;font-size:14px;overflow-wrap:anywhere}
.pa-ios p,.pa-and p{margin:1px 0 0;font-size:13.5px;line-height:1.35;overflow-wrap:anywhere}
.pa-ios p{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.pa-and{background:#fff;border-radius:18px;padding:12px 14px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.pa-and .h{display:flex;align-items:center;gap:6px;color:#555;font-size:12px;margin-bottom:6px}
.pa-and .h img{width:16px;height:16px;border-radius:50%}
.pa-acts{display:flex;gap:10px;justify-content:flex-end;margin-top:22px;padding-top:18px;border-top:1px solid var(--line);flex-wrap:wrap}
.pa-rule{display:grid;grid-template-columns:1fr auto auto;gap:16px;align-items:center;padding:14px 0;border-top:1px solid var(--line)}
.pa-rule:first-of-type{border-top:0}
.pa-rule b{font-size:14.5px}
.pa-rule p{margin:2px 0 0;font-size:12.5px;color:var(--gray)}
.pa-rule .cnt{font:400 18px "Bebas Neue",Arial,sans-serif;color:var(--gray);letter-spacing:.03em;white-space:nowrap}
.pa-rule .opts{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}
.pa-rule .opts input{width:120px;height:34px;border-radius:9px;border:1px solid var(--line-strong);padding:0 10px;font:inherit}
.pa-tog{position:relative;width:46px;height:28px;flex:none}
.pa-tog input{position:absolute;opacity:0;width:100%;height:100%;margin:0;cursor:pointer;z-index:1}
.pa-tog span{position:absolute;inset:0;border-radius:14px;background:#d9d6cf;transition:background .2s}
.pa-tog span::after{content:"";position:absolute;top:4px;left:4px;width:20px;height:20px;border-radius:50%;background:#fff;transition:transform .2s cubic-bezier(.2,.8,.2,1)}
.pa-tog input:checked+span{background:var(--ink)}
.pa-tog input:checked+span::after{transform:translateX(18px);background:var(--lime)}
.pa-tog input:focus-visible+span{outline:3px solid var(--ink);outline-offset:2px}
.pa-flash{padding:12px 16px;border-radius:12px;margin-bottom:16px;font-weight:600}
.pa-flash.ok{background:var(--green-soft);color:var(--green)}
.pa-flash.err{background:var(--red-soft);color:var(--red)}
@media (max-width:1100px){.pa-figs{grid-template-columns:repeat(3,1fr)}.pa-figs>div:nth-child(4){border-left:0}.pa-two,.pa-comp{grid-template-columns:1fr}.pa-prev{position:static}}
@media (max-width:640px){.pa-figs{grid-template-columns:repeat(2,1fr)}.pa-figs>div{border-left:0;border-top:1px solid var(--line)}.pa-fr{grid-template-columns:110px 1fr 70px}}
</style>
"""


def _when(ts):
    if not ts:
        return "—"
    now = db.now()
    t = time.gmtime(ts + push.RIYADH)
    today = time.gmtime(now + push.RIYADH)
    hm = time.strftime("%H:%M", t)
    if t.tm_yday == today.tm_yday and t.tm_year == today.tm_year:
        return "Today " + hm
    if ts > now and ts - now < 7 * 86400:
        return time.strftime("%a %d %b ", t) + hm
    return time.strftime("%d %b ", t).lstrip("0") + hm


def _initials(name):
    parts = [p for p in str(name or "").replace("@", " ").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def _shell(tab, body, flash=None):
    tabs = [(u("/app-alerts?tab=" + k), label, None, k == tab) for k, label in TABS]
    head = header("App & alerts", "Who has the HELVi Connect app and alerts on, and every push it sends.",
                  actions='<a class="btn lime" href="%s">%s New push</a>' % (u("/app-alerts?tab=send"), icon("send", 16)),
                  tabs=tabs)
    fl = ""
    if flash:
        kind, msg = flash
        fl = '<div class="pa-flash %s" role="status">%s</div>' % ("ok" if kind == "ok" else "err", e(msg))
    return page("App & alerts", CSS + head + fl + body, "/app-alerts")


# --------------------------------------------------------------- overview --

STATE = {"on": ("live", "On"), "blocked": ("dead", "Blocked"), "cant": ("", "Can't receive"), "not_asked": ("warn", "Not asked yet")}
PLAT = {"ios": ("iPhone", "var(--ink)", "var(--lime)"), "android": ("Android", "#b9d400", "var(--ink)"),
        "desktop": ("Desktop", "var(--linen)", "var(--ink)")}


def overview_page(q="", flash=None):
    o = push.overview()
    pct = lambda a, b: ("%d%%" % round(100.0 * a / b)) if b else "—"  # noqa: E731
    figs = (
        ("Installed", o["installed"], ('<small class="up">+%d this week</small>' % o["new_week"]) if o["new_week"] else "<small>no new installs this week</small>"),
        ("Alerts on", o["on_people"], "<small>%d phone%s</small>" % (o["devices_on"], "" if o["devices_on"] == 1 else "s")),
        ("Blocked", o["blocked"], "<small>only phone settings can undo it</small>"),
        ("Delivered", pct(o["acked"], o["delivered"]) if o["delivered"] else "—", "<small>%d of %d pushes, 30 days</small>" % (o["acked"], o["sent"])),
        ("Opened", pct(o["clicked"], o["delivered"]) if o["delivered"] else "—", "<small>%d tap%s</small>" % (o["clicked"], "" if o["clicked"] == 1 else "s")),
    )
    out = '<div class="pa-figs">' + "".join('<div><span>%s</span><b>%s</b>%s</div>' % (e(a), e(b), c) for a, b, c in figs) + "</div>"
    top = max([n for _l, n in o["funnel"]] + [1])
    rows, prev = [], None
    for i, (label, n) in enumerate(o["funnel"]):
        share = ("<small>%s</small>" % pct(n, prev)) if prev is not None else ""
        rows.append('<div class="pa-fr%s"><span>%s</span><div class="bar"><i style="width:%.1f%%"></i></div><b>%d%s</b></div>'
                    % (" hl" if label == "Allowed alerts" else "", e(label), 100.0 * n / top, n, share))
        prev = n
    fun = ('<div class="pa-card"><h2>Opt-in funnel</h2><p class="muted">Phones that opened the portal; each step shows the share of the step before</p>'
           '<div class="pa-fun">%s</div></div>' % "".join(rows))
    plats = o["platforms"]
    total = sum(v["installed"] for v in plats.values()) or 0
    seg = "".join('<i style="width:%.2f%%;background:%s;color:%s">%s</i>' % (100.0 * plats[k]["installed"] / total, PLAT[k][1], PLAT[k][2],
                                                                              plats[k]["installed"])
                  for k in ("ios", "android", "desktop") if plats.get(k) and total)
    leg = "".join('<div><s style="background:%s"></s>%s<b>%d</b><span>%d alerts on</span></div>' % (
        PLAT[k][1], PLAT[k][0] + (" (iOS 16.4+)" if k == "ios" else ""), plats.get(k, {}).get("installed", 0), plats.get(k, {}).get("on", 0))
        for k in ("ios", "android", "desktop"))
    dev = ('<div class="pa-card"><h2>Devices</h2><p class="muted">Installed apps by phone</p><div class="pa-split">%s</div><div class="pa-leg">%s</div>%s</div>'
           % (seg, leg, ('<p class="pa-note">%d iPhone%s on iOS older than 16.4 cannot get pushes; they still see everything in Alerts.</p>'
                         % (o["old_ios"], "" if o["old_ios"] == 1 else "s")) if o["old_ios"] else
              '<p class="pa-note">iPhones get pushes only from the Home Screen app (iOS 16.4 or later).</p>'))
    out += '<div class="pa-two">%s%s</div>' % (fun, dev)

    ppl = push.people(q)
    trs = []
    for p in ppl:
        cls, lbl = STATE[p["state"]]
        devs = ", ".join(" · ".join(x for x in (PLAT.get(d[0], ("",))[0], d[1], d[2]) if x) for d in p["devices"][:3]) or "—"
        rate = ('<div class="pa-mini"><div class="b"><i style="width:%d%%"></i></div>%d%%</div>' % (
            round(100.0 * p["clicks"] / p["pushes"]), round(100.0 * p["clicks"] / p["pushes"]))) if p["pushes"] else "—"
        test = ""
        if p["subs"] and p["email"]:
            test = ('<form method="post" action="%s" style="margin:0"><input type="hidden" name="email" value="%s">'
                    '<button class="btn tiny ghost" type="submit">Test push</button></form>' % (u("/app-alerts/test"), e(p["email"])))
        trs.append('<tr><td><div class="pa-who"><i>%s</i><div><b>%s</b><span>%s</span></div></div></td><td>%s</td>'
                   '<td class="pa-dev">%s</td><td>%s</td><td>%s</td><td><span class="pill dot %s">%s%s</span></td><td>%d</td><td>%s</td><td>%s</td></tr>'
                   % (e(_initials(p["name"])), e(p["name"]), e(p["company"] or p["email"]), e(p["role"]), e(devs), _when(p["installed"]),
                      _when(p["last"]), cls, e(lbl), (" · %d" % p["subs"]) if p["subs"] > 1 else "", p["pushes"], rate, test))
    table = ('<div class="pa-scroll"><table class="pa-tbl"><thead><tr><th>Person</th><th>Role</th><th>Device</th><th>Installed</th>'
             '<th>Last opened</th><th>Alerts</th><th>Pushes</th><th>Opened</th><th></th></tr></thead><tbody>%s</tbody></table></div>'
             % ("".join(trs) or '<tr><td colspan="9" class="muted">Nobody has opened the app on a phone yet. As people visit, they appear here.</td></tr>'))
    out += ('<div class="pa-card"><h2>People</h2><p class="muted">Everyone who opened the portal with the app code, newest first. A person with two phones shows both.</p>'
            '<form class="pa-tools" method="get" action="%s"><input type="hidden" name="tab" value="overview">'
            '<input type="search" name="q" value="%s" placeholder="Search name, company or email" aria-label="Search people">'
            '<button class="btn small ghost" type="submit">Search</button></form>%s</div>' % (u("/app-alerts"), e(q), table))
    return _shell("overview", out, flash)


# ------------------------------------------------------------------- send --

DESTS = (("/account/#overview", "Home"), ("/", "Catalogue"), ("/account/#selections", "Selections"),
         ("/account/#campaigns", "Campaigns"), ("/account/#notifications", "Alerts"))


def _lists():
    with db.connect() as conn:
        users = conn.execute("SELECT id, name, email, company, domain FROM users WHERE status = 'active' AND deleted_at IS NULL "
                             "ORDER BY name COLLATE NOCASE").fetchall()
        staff = conn.execute("SELECT email, name, role FROM admins WHERE disabled_at IS NULL ORDER BY name COLLATE NOCASE").fetchall()
        camps = conn.execute("SELECT id, name, status, token FROM campaigns WHERE status IN ('live','draft','ended') "
                             "ORDER BY CASE status WHEN 'live' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END, id DESC LIMIT 200").fetchall()
    staff_emails = {s["email"].lower() for s in staff}
    clients = {}
    for r in users:
        dom = (r["domain"] or (r["email"] or "").split("@")[-1] or "").lower()
        if not dom or (r["email"] or "").lower() in staff_emails:
            continue
        c = clients.setdefault(dom, {"key": dom, "name": r["company"] or dom, "n": 0})
        c["n"] += 1
    return {"clients": sorted(clients.values(), key=lambda c: c["name"].lower()),
            "campaigns": [{"id": c["id"], "name": c["name"], "status": c["status"], "token": c["token"]} for c in camps],
            "people": [{"id": r["id"], "name": r["name"] or r["email"], "sub": r["company"] or r["email"]} for r in users]
            + [{"id": "s:" + s["email"], "name": s["name"] or s["email"], "sub": "HelloVoice · " + (s["role"] or "owner")} for s in staff]}


def send_page(flash=None, form=None):
    L = _lists()
    f = form or {}
    dest_opts = "".join('<option value="%s">%s</option>' % (e(v), e(l)) for v, l in DESTS)
    dest_opts += "".join('<option value="/campaign/#t=%s">Campaign report · %s</option>' % (e(c["token"]), e(c["name"]))
                         for c in L["campaigns"] if c["status"] in ("live", "ended") and c["token"])
    seg = "".join('<label><input type="radio" name="aud_type" value="%s"%s><span>%s</span></label>' % (
        k, " checked" if k == (f.get("aud_type") or "client") else "", lbl)
        for k, lbl in (("all", "Everyone"), ("role", "By role"), ("client", "Clients"), ("campaign", "A campaign's people"), ("people", "People")))
    roles = "".join('<label><input type="checkbox" name="role" value="%s"%s><span>%s</span></label>' % (
        k, " checked" if k == "client" else "", lbl) for k, lbl in (("client", "Clients"), ("kam", "KAMs"), ("admin", "Admins")))
    body = (
        '<form method="post" action="%(act)s" id="pa-form" class="pa-comp" novalidate>'
        '<div>'
        '<div class="pa-f"><label for="pa-title">Title <span id="pa-tc">0 / 50</span></label>'
        '<input type="text" id="pa-title" name="title" maxlength="50" required value="%(title)s" placeholder="Ramadan shortlists are open"></div>'
        '<div class="pa-f"><label for="pa-body">Message <span id="pa-bc">0 / 120</span></label>'
        '<textarea id="pa-body" name="body" maxlength="120" placeholder="One or two short sentences. Say what happened and what a tap opens.">%(body)s</textarea></div>'
        '<div class="pa-f"><label for="pa-dest">Opens <span>where a tap takes them</span></label>'
        '<select id="pa-dest" name="dest">%(dests)s<option value="custom">Another page (paste a link)…</option></select>'
        '<input type="url" id="pa-url" name="url" placeholder="https://influencer-catalogue.hellovoice.co.uk/..." style="margin-top:8px" hidden></div>'
        '<div class="pa-f"><div class="lbl">Who gets it</div><div class="pa-seg" role="radiogroup" aria-label="Audience">%(seg)s</div>'
        '<div class="pa-pick" data-for="role" hidden><div class="pa-seg">%(roles)s</div></div>'
        '<div class="pa-pick" data-for="client" hidden><input type="text" list="pa-dl-client" placeholder="Type a client company…" aria-label="Add a client"><div class="pa-chips"></div></div>'
        '<div class="pa-pick" data-for="campaign" hidden><input type="text" list="pa-dl-campaign" placeholder="Type a campaign…" aria-label="Add a campaign"><div class="pa-chips"></div></div>'
        '<div class="pa-pick" data-for="people" hidden><input type="text" list="pa-dl-people" placeholder="Type a name or email…" aria-label="Add a person"><div class="pa-chips"></div></div>'
        '<div class="pa-pick" data-for="kam" hidden style="margin-top:10px"><div class="pa-seg">'
        '<label><input type="radio" name="kam" value="1" checked><span>Clients + their KAM</span></label>'
        '<label><input type="radio" name="kam" value="0"><span>Clients only</span></label></div></div>'
        '<datalist id="pa-dl-client">%(dl_client)s</datalist><datalist id="pa-dl-campaign">%(dl_camp)s</datalist><datalist id="pa-dl-people">%(dl_people)s</datalist>'
        '</div>'
        '<div class="pa-reach" aria-live="polite"><b id="pa-r-n">0</b><span id="pa-r-t">Pick who gets it</span><small id="pa-r-s">&nbsp;</small></div>'
        '<div class="pa-f" style="margin-top:18px"><div class="lbl">When</div><div class="pa-when">'
        '<label class="r"><input type="radio" name="when" value="now" checked> Now</label>'
        '<label class="r"><input type="radio" name="when" value="later"> Schedule</label>'
        '<input type="datetime-local" name="send_at" id="pa-at" aria-label="Send at (Riyadh time)">'
        '<span class="muted" style="font-size:12.5px">Riyadh time. Quiet hours 23:00–08:00 are skipped automatically.</span></div></div>'
        '<input type="hidden" name="aud" id="pa-aud" value="{}">'
        '<div class="pa-acts"><button class="btn" type="submit" id="pa-go">Send push</button></div>'
        '</div>'
        '<aside class="pa-prev" aria-label="Preview"><h3>iPhone</h3>'
        '<div class="pa-ios"><img src="%(icon)s" alt=""><div><div class="h"><b>HELVi Connect</b><span>now</span></div><div class="t" data-p="t">Title</div><p data-p="b">Message</p></div></div>'
        '<h3>Android</h3><div class="pa-and"><div class="h"><img src="%(icon)s" alt="">HELVi Connect · now</div><div class="t" data-p="t">Title</div><p data-p="b">Message</p></div>'
        '<button class="btn ghost" type="submit" name="test" value="1" style="width:100%%;margin-top:16px" formnovalidate>Send a test to my phone</button>'
        '<p class="muted" style="font-size:12.5px;margin:10px 0 0">Every push also lands in the person\'s Alerts, so people without the app still see it.</p>'
        '</aside></form>'
    ) % {"act": u("/app-alerts/send"), "title": e(f.get("title", "")), "body": e(f.get("body", "")), "dests": dest_opts,
         "seg": seg, "roles": roles,
         "dl_client": "".join('<option value="%s" data-k="%s">%d people</option>' % (e(c["name"]), e(c["key"]), c["n"]) for c in L["clients"]),
         "dl_camp": "".join('<option value="%s" data-k="%d">%s</option>' % (e(c["name"]), c["id"], e(c["status"])) for c in L["campaigns"]),
         "dl_people": "".join('<option value="%s" data-k="%s">%s</option>' % (e(p["name"]), e(p["id"]), e(p["sub"])) for p in L["people"]),
         "icon": "/assets/app/icon-192.png"}
    js = """
<script>
(function(){
  var F=document.getElementById('pa-form'); if(!F) return;
  var T=F.title, B=F.body, sel={client:[],campaign:[],people:[]}, reachUrl=%s;
  function q(s,r){return (r||F).querySelector(s)} function qa(s,r){return [].slice.call((r||F).querySelectorAll(s))}
  function paint(){
    document.getElementById('pa-tc').textContent=T.value.length+' / 50';
    document.getElementById('pa-bc').textContent=B.value.length+' / 120';
    qa('[data-p=t]',document).forEach(function(x){x.textContent=T.value||'Title'});
    qa('[data-p=b]',document).forEach(function(x){x.textContent=B.value||'Message'});
  }
  function type(){var c=q('input[name=aud_type]:checked');return c?c.value:'client'}
  function aud(){
    var t=type(), a={type:t};
    if(t==='role') a.roles=qa('input[name=role]:checked').map(function(x){return x.value});
    if(t==='client') a.clients=sel.client.map(function(x){return x.k});
    if(t==='campaign') a.campaigns=sel.campaign.map(function(x){return +x.k});
    if(t==='people'){a.people=sel.people.filter(function(x){return String(x.k).indexOf('s:')!==0}).map(function(x){return +x.k});
      a.staff=sel.people.filter(function(x){return String(x.k).indexOf('s:')===0}).map(function(x){return String(x.k).slice(2)});}
    if(t==='client'||t==='campaign'){var k=q('input[name=kam]:checked'); a.kam=!k||k.value==='1';}
    return a;
  }
  var timer;
  function reach(){
    var a=aud(); document.getElementById('pa-aud').value=JSON.stringify(a);
    qa('.pa-pick').forEach(function(p){var f=p.getAttribute('data-for'); p.hidden=!(f===type()||(f==='kam'&&(type()==='client'||type()==='campaign')));});
    clearTimeout(timer); timer=setTimeout(function(){
      fetch(reachUrl+'?aud='+encodeURIComponent(JSON.stringify(a)),{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(r){
        document.getElementById('pa-r-n').textContent=r.push_people;
        document.getElementById('pa-r-t').textContent=(r.push_people===1?'person':'people')+' will get it as a push, on '+r.devices+' phone'+(r.devices===1?'':'s');
        document.getElementById('pa-r-s').textContent=r.bell_only?('+ '+r.bell_only+' more see it only in Alerts (no app, alerts off or blocked)'):(r.people?'Everyone chosen has alerts on':'Nobody chosen yet');
      }).catch(function(){});
    },200);
  }
  function chip(kind,item){
    var box=q('.pa-pick[data-for='+kind+'] .pa-chips'), b=document.createElement('button');
    b.type='button'; b.innerHTML=''; b.appendChild(document.createTextNode(item.v)); var i=document.createElement('i'); i.textContent='×'; i.setAttribute('aria-hidden','true'); b.appendChild(i);
    b.setAttribute('aria-label','Remove '+item.v);
    b.addEventListener('click',function(){sel[kind]=sel[kind].filter(function(x){return x!==item}); b.remove(); reach();});
    box.appendChild(b);
  }
  ['client','campaign','people'].forEach(function(kind){
    var inp=q('.pa-pick[data-for='+kind+'] input'), dl=document.getElementById('pa-dl-'+kind);
    function take(){
      var v=inp.value.trim(); if(!v) return;
      var o=[].slice.call(dl.options).filter(function(x){return x.value===v})[0]; if(!o) return;
      var k=o.getAttribute('data-k'); if(sel[kind].some(function(x){return x.k===k})){inp.value='';return}
      var it={k:k,v:v}; sel[kind].push(it); chip(kind,it); inp.value=''; reach();
    }
    inp.addEventListener('change',take); inp.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();take()}});
  });
  var dest=F.dest, url=F.url;
  dest.addEventListener('change',function(){url.hidden=dest.value!=='custom'; if(!url.hidden) url.focus()});
  F.addEventListener('change',function(e){if(e.target.name==='aud_type'||e.target.name==='role'||e.target.name==='kam') reach();
    if(e.target.name==='when'){document.getElementById('pa-go').textContent=e.target.value==='later'?'Schedule push':'Send push'}});
  document.getElementById('pa-at').addEventListener('focus',function(){q('input[name=when][value=later]').checked=true;document.getElementById('pa-go').textContent='Schedule push'});
  T.addEventListener('input',paint); B.addEventListener('input',paint);
  F.addEventListener('submit',function(e){
    document.getElementById('pa-aud').value=JSON.stringify(aud());
    var test=e.submitter&&e.submitter.name==='test';
    if(!T.value.trim()){e.preventDefault();T.focus();T.setCustomValidity('Give the push a title.');T.reportValidity();T.setCustomValidity('');return}
    if(!test){var n=+document.getElementById('pa-r-n').textContent;
      if(!confirm(n?('Send this push to '+n+' '+(n===1?'person':'people')+'?'):'Nobody chosen has alerts on. It will only appear in Alerts. Continue?')) e.preventDefault();}
  });
  paint(); reach();
})();
</script>""" % json.dumps(u("/app-alerts/reach"))
    return _shell("send", body + js, flash)


# ---------------------------------------------------------------- history --

def _aud_label(m):
    try:
        a = json.loads(m["audience"] or "{}")
    except ValueError:
        a = {}
    t = a.get("type")
    n = m["people"] or 0
    if m["source"] == "auto":
        return "%d %s" % (n, "person" if n == 1 else "people")
    if t == "test":
        return "Test · " + str(a.get("email", ""))
    lab = {"all": "Everyone", "role": "By role", "client": "%d client%s" % (len(a.get("clients") or []), "" if len(a.get("clients") or []) == 1 else "s"),
           "campaign": "Campaign people", "people": "Chosen people"}.get(t, "")
    return "%s · %d %s" % (lab, n, "person" if n == 1 else "people")


def history_page(flash=None):
    rows = push.history(120)
    trs = []
    for m in rows:
        if m["source"] == "auto":
            tag = '<span class="pa-tag auto">Auto · %s</span>' % e(push.RULE_LABELS.get(m["rule"], m["rule"] or "").split(" ")[0].lower())
        elif m["status"] == "scheduled":
            tag = '<span class="pa-tag">Scheduled</span>'
        else:
            tag = '<span class="pa-tag">%s</span>' % ("Test" if m["source"] == "test" else "Manual")
        when = _when(m["send_at"] if m["status"] == "scheduled" else (m["sent_at"] or m["created_at"]))
        rate = ('<div class="pa-mini"><div class="b"><i style="width:%d%%"></i></div>%d%%</div>' % (
            round(100.0 * m["clicks"] / m["ok"]), round(100.0 * m["clicks"] / m["ok"]))) if m["ok"] else "—"
        extra = ""
        if m["status"] == "scheduled":
            extra = ('<form method="post" action="%s" style="margin:0"><input type="hidden" name="id" value="%d">'
                     '<button class="btn tiny danger" type="submit">Cancel</button></form>' % (u("/app-alerts/cancel"), m["id"]))
        elif m["held"]:
            extra = '<span class="muted" style="font-size:12px">%d over the daily cap</span>' % m["held"]
        if m["status"] == "cancelled":
            extra = '<span class="muted" style="font-size:12px">Cancelled</span>'
        trs.append('<tr><td><b>%s</b><div class="muted" style="font-size:12.5px;max-width:52ch;white-space:normal">%s</div></td><td>%s</td>'
                   '<td>%s</td><td style="white-space:nowrap">%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                   % (e(m["title"]), e(m["body"] or ""), tag, e(_aud_label(m)), e(when),
                      ("%d / %d" % (m["ok"], m["tried"])) if m["tried"] else "—", rate, extra))
    body = ('<div class="pa-card"><h2>Pushes</h2><p class="muted">Manual and automatic, newest first. Delivered = accepted by Apple or Google; Opened = tapped.</p>'
            '<div class="pa-scroll"><table class="pa-tbl"><thead><tr><th>Push</th><th>Type</th><th>Audience</th><th>Sent</th><th>Delivered</th>'
            '<th>Opened</th><th></th></tr></thead><tbody>%s</tbody></table></div></div>'
            % ("".join(trs) or '<tr><td colspan="7" class="muted">No pushes yet.</td></tr>'))
    return _shell("history", body, flash)


# ------------------------------------------------------------------ rules --

def rules_page(flash=None):
    R = push.rules()
    counts = push.rule_counts()

    def tog(name, on, label):
        return ('<span class="pa-tog"><input type="checkbox" name="%s" value="1"%s aria-label="%s"><span></span></span>'
                % (name, " checked" if on else "", e(label)))

    def row(key, title, desc, opts=""):
        n = counts.get(key, 0)
        return ('<div class="pa-rule"><div><b>%s</b><p>%s</p>%s</div><span class="cnt">%d sent</span>%s</div>'
                % (e(title), e(desc), ('<div class="opts">%s</div>' % opts) if opts else "", n, tog(key, R.get(key), title)))

    steps = lambda k: ", ".join(str(x) for x in R[k])  # noqa: E731
    body = (
        '<form method="post" action="%s">' % u("/app-alerts/rules")
        + '<div class="pa-card" style="max-width:940px"><h2>Automatic pushes</h2>'
        '<p class="muted">Each rule can be switched off. Quiet hours and the daily cap apply to automatic pushes only; held pushes go when quiet hours end. Alerts always update at once.</p>'
        + '<div class="pa-rule"><div><b>All automatic pushes</b><p>Master switch. Off = only manual pushes go out.</p></div><span></span>%s</div>' % tog("on", R["on"], "All automatic pushes")
        + row("camp_status", "Campaign is live / ended / final report", "To the campaign's client people")
        + row("goals", "Goal reached", "Every campaign goal (posts, views, engagement, rate, clicks); one push per step",
              '<label>Steps (%%) <input type="text" name="goal_steps" value="%s"></label>' % e(steps("goal_steps")))
        + row("posts", "First post + new posts live", "First post on its own; later posts bundled",
              '<label>At most one every <input type="number" min="1" max="48" name="posts_gap_h" value="%d" style="width:70px"> hours</label>' % R["posts_gap_h"])
        + row("views", "Views passed", "Total campaign views, checked every 10 minutes",
              '<label>Thresholds <input type="text" name="view_steps" value="%s" style="width:300px"></label>' % e(steps("view_steps")))
        + row("bell", "Selections, analysis, quotes, credits", "Everything else the bell sends, as a push too")
        + row("team", "Team: briefs, quote requests, red-flag comments, milestones", "To KAMs and admins, the same events they get by email")
        + '<div class="pa-rule"><div><b>Limits</b><p>Riyadh time</p><div class="opts">'
          '<label>Quiet from <input type="number" min="0" max="23" name="quiet_a" value="%d" style="width:70px">:00</label>'
          '<label>to <input type="number" min="0" max="23" name="quiet_b" value="%d" style="width:70px">:00</label>'
          '<label>Max automatic pushes per person per day <input type="number" min="1" max="20" name="daily_max" value="%d" style="width:70px"></label>'
          '</div></div><span></span><span></span></div>' % (R["quiet"][0], R["quiet"][1], R["daily_max"])
        + '<div class="pa-acts"><button class="btn" type="submit">Save rules</button></div></div></form>'
        '<p class="muted" style="max-width:80ch;font-size:13px">People choose per group in Account → Notifications (the same switches as the bell) plus one "Phone alerts" switch. '
        'Pushes use standard Web Push with HelloVoice\'s own key (no Firebase): Android Chrome, Edge and Samsung, iPhone Home Screen apps on iOS 16.4+, and desktop browsers.</p>'
    )
    return _shell("rules", body, flash)


def parse_rules(form):
    def steps(v):
        out = []
        for x in str(v or "").replace(";", ",").split(","):
            x = x.strip().lower().replace(" ", "")
            mult = 1
            if x.endswith("k"):
                mult, x = 1000, x[:-1]
            elif x.endswith("m"):
                mult, x = 1000000, x[:-1]
            try:
                out.append(int(float(x) * mult))
            except ValueError:
                pass
        return out
    ch = {k: form.get(k) == "1" for k in ("on", "camp_status", "goals", "posts", "views", "bell", "team")}
    ch["goal_steps"] = [s for s in steps(form.get("goal_steps")) if 0 < s <= 1000]
    ch["view_steps"] = steps(form.get("view_steps"))
    ch["posts_gap_h"] = form.get("posts_gap_h")
    ch["daily_max"] = form.get("daily_max")
    ch["quiet"] = [form.get("quiet_a"), form.get("quiet_b")]
    return ch


def parse_send_at(value):
    """datetime-local in Riyadh time -> epoch."""
    try:
        t = time.strptime(str(value).strip()[:16], "%Y-%m-%dT%H:%M")
    except ValueError:
        return None
    import calendar
    return calendar.timegm(t) - push.RIYADH
