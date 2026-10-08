"""Admin pages for the client portal: accounts, briefs, AI usage, settings, and the copilot.

Server-rendered like the rest of the dashboard: every value goes through ``e()``,
every change is a plain form posting to ``/portal/...``.
"""
import json
import time

import db
import gemini
import mailer
import notify
import portal
import ui
import views
from views import ago, e, page, ts, u

TABS = [("accounts", "Client accounts"), ("codes", "Access codes → accounts"), ("briefs", "Briefs"), ("chats", "Chats"),
        ("usage", "Usage & cost"), ("settings", "Settings & keys")]


def _banner(ok, err):
    return (("<div class='ok'>" + e(ok) + "</div>") if ok else "") + (("<div class='err'>" + e(err) + "</div>") if err else "")


def _tabs(current):
    return [(u("/portal?tab=" + k), label, None, k == current) for k, label in TABS]


def _stat(label, value, sub=""):
    return ("<div class='stat'><span class='k'>%s</span><b class='v'>%s</b>%s</div>"
            % (e(label), e(value), ("<span class='muted'>" + e(sub) + "</span>") if sub else ""))


STAT_CSS = ("<style>.pstats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:0 0 18px}"
            ".pstats .stat{background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px 16px;display:flex;flex-direction:column;gap:2px}"
            ".pstats .k{font-size:var(--t-xs,12px);color:var(--gray);text-transform:uppercase;letter-spacing:.06em}"
            ".pstats .v{font-size:var(--t-xl,28px);font-family:'Bebas Neue',sans-serif;letter-spacing:.02em}"
            ".fgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}"
            "textarea.mono{font-family:ui-monospace,monospace;font-size:var(--t-sm,13px);min-height:90px;width:100%}</style>")


def _status_pill(s):
    cls = {"active": "live", "pending": "warn", "suspended": "dead"}.get(s, "")
    return "<span class='pill %s'>%s</span>" % (cls, e(s))


# ---------------------------------------------------------------- accounts --

def _accounts_tab():
    users = portal.list_users()
    week = db.now() - 7 * 86400
    pending = [x for x in users if x["status"] == "pending"]
    outstanding = sum((x["credits"] or 0) for x in users)
    month = db.now() - 30 * 86400
    with db.connect() as conn:
        one = lambda q, a=(): conn.execute(q, a).fetchone()[0] or 0
        f_signups = one("SELECT COUNT(*) FROM users WHERE created_at >= ? AND deleted_at IS NULL", (month,))
        f_active = one("SELECT COUNT(*) FROM users WHERE last_login_at >= ? AND deleted_at IS NULL", (month,))
        f_briefs = one("SELECT COUNT(DISTINCT code_id) FROM briefs WHERE created_at >= ?", (month,))
        f_sel = one("SELECT COUNT(DISTINCT s.code_id) FROM selections s JOIN users u ON u.code_id = s.code_id WHERE s.created_at >= ?", (month,))
        f_quote = one("SELECT COUNT(DISTINCT r.code_id) FROM requests r JOIN users u ON u.code_id = r.code_id WHERE r.at >= ?", (month,))
    def step(label, n, base):
        return ("<div class='stat'><span class='k'>%s</span><b class='v'>%d</b><span class='muted'>%s</span></div>"
                % (e(label), n, ("%d%% of sign-ins" % round(n * 100 / base)) if base else "&nbsp;"))
    funnel = ("<div class='card'><h2>Last 30 days</h2><p class='sec-desc'>Clients at each step. A client counts once per step.</p>"
              "<div class='pstats' style='margin:0'>" + step("Signed up", f_signups, 0) + step("Signed in", f_active, 0)
              + step("Wrote a brief", f_briefs, f_active) + step("Saved a selection", f_sel, f_active)
              + step("Asked for a quote", f_quote, f_active) + "</div></div>")
    reqs = portal.open_credit_requests()
    req_html = ""
    if reqs:
        req_html = ("<div class='card'><h2>Credit requests</h2><table><tbody>" + "".join(
            "<tr><td><strong>%s</strong><br><span class='muted'>%s · %s</span></td><td>%d credits</td><td>%s</td><td class='right'>"
            "<form method='post' action='%s' class='inline'><input type='hidden' name='id' value='%d'><input type='hidden' name='back' value='/portal'>"
            "<input type='number' name='grant' value='%d' min='1' style='width:90px'> <button class='btn small lime' name='action' value='grant'>Grant</button> "
            "<button class='btn small ghost' name='action' value='decline'>Decline</button></form></td></tr>"
            % (e(r["company"] or r["email"] or "Access code #%d" % r["code_id"]), e(r["email"] or ""), e(ago(r["at"])), r["amount"],
               e(r["note"] or ""), u("/portal/credit-request"), r["id"], r["amount"]) for r in reqs) + "</tbody></table></div>")
    stats = ("<div class='pstats'>" + _stat("Clients", len(users))
             + (_stat("Awaiting approval", len(pending)) if portal.signup_mode() == "approval" or pending else "")
             + _stat("Joined this week", sum(1 for x in users if x["created_at"] >= week))
             + _stat("Credits outstanding", outstanding) + "</div>")
    spend = {r["code_id"]: r["usd"] for r in consumption(gemini.month_start())}
    rows = []
    for x in users:
        approve = ""
        if x["status"] == "pending":
            approve = ("<form method='post' action='" + u("/portal/user/status") + "' class='inline'><input type='hidden' name='id' value='%d'>"
                       "<input type='hidden' name='status' value='active'><input type='hidden' name='back' value='/portal'>"
                       "<button class='btn small lime'>Approve</button></form> " % x["id"])
        rows.append(
            "<tr><td><strong>%s</strong><br><span class='muted'>%s · %s</span></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class='muted'>%s</td>"
            "<td class='right'>%s<a class='btn small ghost' href='%s'>Manage</a></td></tr>"
            % (e(x["name"] or "—"), e(x["company"] or "—"), e(x["email"]), e(x["kam"] or "—"), _status_pill(x["status"]),
               e(x["credits"] if x["credits"] is not None else 0), usd(spend.get(x["code_id"], 0)), e(x["selections"]), e(x["briefs"]),
               e(ago(x["last_login_at"]) if x["last_login_at"] else "never"), approve, u("/portal/user?id=%d" % x["id"])))
    table = ("<table><thead><tr><th>Client</th><th>KAM</th><th>Status</th><th>Credits</th><th>AI cost (month)</th><th>Selections</th><th>Briefs</th><th>Last in</th><th></th></tr></thead><tbody>"
             + ("".join(rows) or "<tr><td colspan='9'>" + ui.empty("users", "No sign-ups yet",
                "Clients appear here when they sign in with a company email on the catalogue.") + "</td></tr>") + "</tbody></table>")
    return stats + req_html + funnel + "<div class='card'>" + table + "</div>"


def _briefs_tab():
    rows = []
    for b in portal.briefs_for(None, 100):
        usr = portal.user_for_code(b["code_id"])
        who = (usr["company"] or usr["email"]) if usr else "Guest code #%d" % b["code_id"]
        rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class='muted'>%s</td></tr>"
                    % (e(who), e(b["summary"]), e(b["objective"] or ""),
                       ("selection #%d" % b["selection_id"]) if b["selection_id"] else "—", e(ago(b["created_at"]))))
    return ("<div class='card'><p class='sec-desc'>Every brief a client answered. The selection it produced is on the Selections page, "
            "already scored against the brief.</p><table><thead><tr><th>Client</th><th>Brief</th><th>Objective</th><th>Result</th><th>When</th></tr></thead><tbody>"
            + ("".join(rows) or "<tr><td colspan='5'>" + ui.empty("list", "No briefs yet", "They appear when a client uses Find creators.") + "</td></tr>")
            + "</tbody></table></div>")


def _chats_tab():
    users = {x["code_id"]: x for x in portal.list_users()}
    rows = []
    for t in portal.threads(None, "client", 200):
        if not t["n"]:
            continue
        x = users.get(t["code_id"])
        who = ("%s · %s" % (x["company"] or "—", x["email"])) if x else "Access code #%s" % t["code_id"]
        rows.append("<tr><td>%s</td><td>%s</td><td>%d</td><td class='muted'>%s</td><td class='right'><a class='btn small ghost' href='%s'>Read</a></td></tr>"
                    % (e(who), e((t["first"] or "")[:90]), t["n"], e(ago(t["last"])), u("/portal/chat?id=%d" % t["id"])))
    return ("<div class='card'><p class='sec-desc'>What clients ask the assistant. Useful for spotting demand, gaps in the roster, "
            "and questions to answer on the website.</p><table><thead><tr><th>Client</th><th>Opened with</th><th>Messages</th><th>Last</th><th></th></tr></thead><tbody>"
            + ("".join(rows) or "<tr><td colspan='5'>" + ui.empty("list", "No conversations yet", "They appear when clients use Ask.") + "</td></tr>")
            + "</tbody></table></div>")


def chat_page(th):
    x = portal.user_for_code(th["code_id"]) if th["code_id"] else None
    who = ("%s · %s" % (x["company"] or "—", x["email"])) if x else ("Admin copilot · %s" % th["owner"] if th["scope"] == "admin" else "Access code #%s" % th["code_id"])
    msgs = "".join("<div style='margin:0 0 12px;max-width:80%%;%s'><div class='muted' style='font-size:var(--t-xs,12px)'>%s · %s</div>"
                   "<div style='white-space:pre-wrap;background:%s;color:%s;padding:10px 14px;border-radius:14px'>%s</div></div>"
                   % ("margin-left:auto" if m["role"] == "user" else "", "Client" if m["role"] == "user" else "Assistant", e(ago(m["at"])),
                      "var(--ink)" if m["role"] == "user" else "#f3f1ec", "#fff" if m["role"] == "user" else "inherit", e(m["content"]))
                   for m in portal.messages(th["id"], 500))
    return page("Conversation", ui.header("Conversation", e(who), crumbs=[("Client portal", u("/portal?tab=chats")), ("Conversation", None)])
                + "<div class='card' style='display:flex;flex-direction:column'>" + (msgs or "<p class='muted'>Empty.</p>") + "</div>", "/portal")


def quote_page(sel, origin):
    """A printable quotation from a selection and its brief (the browser's Print → Save as PDF)."""
    import fx
    codes = json.loads(sel["codes"] or "[]")
    own = json.loads(sel["prices"] or "{}")
    bands = db.tier_prices()
    rows = {c["code"]: c for c in db.list_creators() if c["code"] in set(codes)}
    with db.connect() as conn:
        b = conn.execute("SELECT * FROM briefs WHERE selection_id = ? ORDER BY id DESC LIMIT 1", (sel["id"],)).fetchone()
    owner = portal.user_for_code(sel["code_id"]) if sel["code_id"] else None
    lines, lo_t, hi_t = [], 0, 0
    for i, code in enumerate(codes, 1):
        c = rows.get(code)
        if c is None:
            continue
        p = own.get(code)
        lo, hi = (p, p) if isinstance(p, (int, float)) else (tuple(p) if isinstance(p, list) and len(p) == 2 else (db.price_for(c, bands, sel["platform"]) or (0, 0)))
        lo_t += lo or 0; hi_t += hi or 0
        lines.append("<tr><td>%d</td><td><strong>%s</strong><br><span class='muted'>%s</span></td><td>%s</td><td>%s</td><td>%s</td><td class='right'>%s</td></tr>" % (
            i, e(c["name"]), e(code), e(c["platform"]), ui.compact(c["followers"] or 0), e(c["tier"]),
            ui.sar_range(lo, hi) if lo else "On request"))
    total_from = sel["total_from"] or lo_t
    total_to = sel["total_to"] or hi_t
    rng = lambda a, z: ui.sar_range(a, z)
    vat = lambda a, z: rng(a * 1.15, z * 1.15)
    css = ("<style>@media print{.sidebar,.topbar,.no-print,nav,header.app-top{display:none!important}main,.main{margin:0!important;padding:0!important}"
           ".card{border:0!important;box-shadow:none!important}} .q-h{display:flex;justify-content:space-between;align-items:flex-start;gap:20px}"
           ".q-h h1{font-family:'Bebas Neue',sans-serif;font-size:var(--t-2xl,38px);margin:0;letter-spacing:.02em} .q-tot td{font-weight:600}</style>")
    body = (css + "<div class='no-print' style='margin-bottom:14px'><button class='btn lime' onclick='window.print()'>Print / save as PDF</button></div>"
            "<div class='card'><div class='q-h'><div><h1>Quotation</h1><p class='muted'>%s · Ref Q-%d-%s</p></div>"
            "<div style='text-align:right'><strong>HelloVoice</strong><br><span class='muted'>Al-Olaya, Riyadh<br>info@hellovoice.co.uk · +966 11 463 4518</span></div></div>"
            % (e(time.strftime("%d %b %Y")), sel["id"], time.strftime("%y%m"))
            + "<p><strong>Prepared for:</strong> %s</p>" % e((owner["company"] + " · " + (owner["name"] or "")) if owner else (sel["name"]))
            + ("<p><strong>Brief:</strong> %s</p>" % e(b["summary"]) if b else "")
            + "<p><strong>Selection:</strong> %s (%d creators)</p>" % (e(sel["name"]), len(lines))
            + "<table><thead><tr><th>#</th><th>Creator</th><th>Platform</th><th>Followers</th><th>Tier</th><th class='right'>Fee (per video)</th></tr></thead><tbody>"
            + "".join(lines)
            + "<tr class='q-tot'><td colspan='5'>Total before VAT</td><td class='right'>%s</td></tr>" % rng(total_from, total_to)
            + "<tr class='q-tot'><td colspan='5'>Total incl. 15%% VAT</td><td class='right'>%s</td></tr></tbody></table>" % vat(total_from, total_to)
            + "<p class='muted' style='margin-top:18px'>Prices in SAR, valid 30 days, subject to creator availability on booking. "
              "Includes casting, briefing, compliance review and post-campaign reporting. Usage rights beyond 30 days are quoted separately.</p></div>")
    return page("Quotation — " + sel["name"], body, "/selections")


def usd(v):
    v = float(v or 0)
    return "$%.2f" % v if v >= 0.995 or v == 0 else "$%.3f" % v if v >= 0.0095 else "$%.4f" % v


def account_label(code_id, users_by_code, codes_by_id):
    if code_id is None:
        return "Platform (sign-in emails, admin copilot)", None
    u = users_by_code.get(code_id)
    if u:
        return "%s · %s" % (u["company"] or "—", u["email"]), u["id"]
    c = codes_by_id.get(code_id)
    if c is not None and c["label"] == db.ADMIN_LABEL:
        return "Admin preview", None
    return "Access code: %s" % (c["label"] if c is not None else "#%s" % code_id), None


def consumption(since=None, until=None):
    """[(code_id, calls, failed, tokens, usd, credits)] per account, biggest spend first."""
    q = ("SELECT code_id, COUNT(*) calls, SUM(1 - ok) failed, SUM(prompt_tokens + out_tokens) tok, SUM(cost_usd) usd, "
         "SUM(credits) cr FROM ai_audit WHERE at >= ? AND at < ? GROUP BY code_id ORDER BY usd DESC")
    with db.connect() as conn:
        return conn.execute(q, (since or 0, until or db.now() + 86400)).fetchall()


def _usage_tab():
    import calendar
    used, cap = gemini.tokens_this_month(), gemini.monthly_cap()
    since, now = gemini.month_start(), db.now()
    t = time.gmtime(now)
    days_in = calendar.monthrange(t.tm_year, t.tm_mon)[1]
    elapsed = max(1.0, (now - since) / 86400.0)
    with db.connect() as conn:
        one = lambda q, a=(): conn.execute(q, a).fetchone()[0] or 0
        month_usd = one("SELECT SUM(cost_usd) FROM ai_audit WHERE at >= ?", (since,))
        today_usd = one("SELECT SUM(cost_usd) FROM ai_audit WHERE at >= ?", (now - now % 86400,))
        d30_usd = one("SELECT SUM(cost_usd) FROM ai_audit WHERE at >= ?", (now - 30 * 86400,))
        all_usd = one("SELECT SUM(cost_usd) FROM ai_audit")
        by_kind = conn.execute("SELECT kind, COUNT(*) n, SUM(ok) good, SUM(prompt_tokens+out_tokens) tok, SUM(cost_usd) usd "
                               "FROM ai_audit WHERE at >= ? GROUP BY kind ORDER BY usd DESC", (since,)).fetchall()
        by_model = conn.execute("SELECT model, COUNT(*) n, SUM(prompt_tokens) pin, SUM(out_tokens) pout, SUM(cost_usd) usd "
                                "FROM ai_audit WHERE at >= ? GROUP BY model ORDER BY usd DESC", (since,)).fetchall()
        daily = conn.execute("SELECT (at / 86400) d, SUM(cost_usd) usd FROM ai_audit WHERE at >= ? GROUP BY d ORDER BY d",
                             (now - 29 * 86400,)).fetchall()
        recent = conn.execute("SELECT a.*, u.email FROM ai_audit a LEFT JOIN users u ON u.code_id = a.code_id "
                              "ORDER BY a.id DESC LIMIT 25").fetchall()
        spent = one("SELECT -SUM(delta) FROM credit_ledger WHERE delta < 0 AND at >= ?", (since,))
        granted = one("SELECT SUM(delta) FROM credit_ledger WHERE delta > 0 AND at >= ?", (since,))
        codes = {r["id"]: r for r in conn.execute("SELECT id, label FROM codes").fetchall()}
    users = {u["code_id"]: u for u in portal.list_users()}
    ucap = gemini.monthly_usd_cap()
    projected = month_usd / elapsed * days_in
    stats = ("<div class='pstats'>"
             + _stat("Spent this month", usd(month_usd), ("of %s budget · %d%%" % (usd(ucap), round(month_usd * 100 / ucap))) if ucap > 0 else "no budget set")
             + _stat("Projected month end", usd(projected), "at the current pace")
             + _stat("Today", usd(today_usd), "last 30 days %s" % usd(d30_usd))
             + _stat("All time", usd(all_usd), "{:,} tokens this month".format(used))
             + _stat("Cost per credit", usd(month_usd / spent) if spent else "—", "%d credits spent, %d granted" % (spent, granted))
             + "</div>")
    if ucap > 0 and projected > ucap:
        stats += "<div class='note'>At this pace the month ends near %s, over the %s budget. AI stops for everyone when the budget is reached; raise it in Settings &amp; keys.</div>" % (usd(projected), usd(ucap))

    days = {int(r["d"]): r["usd"] or 0 for r in daily}
    first = (now - 29 * 86400) // 86400
    # hbars scales against at least 1, so feed it hundredths of a cent: a $0.03 day still shows a bar
    bars = ui.hbars([(time.strftime("%d %b", time.gmtime(d * 86400)), days.get(d, 0) * 10000, usd(days.get(d, 0)))
                     for d in range(first, now // 86400 + 1)], "var(--ink)")

    acct = consumption(since)
    acct_all = {r["code_id"]: r for r in consumption()}
    acct_rows = []
    for r in acct:
        label, uid = account_label(r["code_id"], users, codes)
        name = ("<a href='%s'>%s</a>" % (u("/portal/user?id=%d" % uid), e(label))) if uid else e(label)
        allr = acct_all.get(r["code_id"])
        acct_rows.append("<tr><td>%s</td><td>%d</td><td>%s</td><td>%s</td><td><strong>%s</strong></td><td class='muted'>%s</td></tr>" % (
            name, r["calls"], "{:,}".format(r["tok"] or 0), r["cr"] or 0, usd(r["usd"]), usd(allr["usd"] if allr else 0)))

    kind_names = {"brief": "AI shortlist reasons", "parse": "Reading a brief", "chat": "Client chat", "copilot": "Admin copilot",
                  "email": "Sign-in emails", "selftest": "Self test"}
    kind_rows = "".join("<tr><td>%s</td><td>%d</td><td>%d</td><td>%s</td><td><strong>%s</strong></td></tr>" % (
        e(kind_names.get(r["kind"], r["kind"])), r["n"], r["good"] or 0, "{:,}".format(r["tok"] or 0), usd(r["usd"])) for r in by_kind)
    model_rows = "".join("<tr><td>%s</td><td>%d</td><td>%s</td><td>%s</td><td><strong>%s</strong></td></tr>" % (
        e(r["model"] or "—"), r["n"], "{:,}".format(r["pin"] or 0), "{:,}".format(r["pout"] or 0), usd(r["usd"])) for r in by_model)

    def who(r):
        return r["email"] or ("code #%s" % r["code_id"] if r["code_id"] else "platform")
    recent_rows = "".join(
        "<tr><td class='muted'>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class='muted'>%s</td></tr>" % (
            e(ago(r["at"])), e(kind_names.get(r["kind"], r["kind"])), e(who(r)), "ok" if r["ok"] else "<span class='pill dead'>failed</span>",
            "{:,}".format((r["prompt_tokens"] or 0) + (r["out_tokens"] or 0)), usd(r["cost_usd"]),
            e(" · ".join(x for x in (("%s ms" % r["latency_ms"]) if r["latency_ms"] else "", r["model"] or "", r["detail"] or "") if x)))
        for r in recent)
    empty = lambda n, t: "<tr><td colspan='%d' class='muted'>%s</td></tr>" % (n, t)
    return (stats
            + "<div class='card'><div class='hd' style='display:flex;justify-content:space-between;align-items:center'><h2>Consumption per account, this month</h2>"
              "<a class='btn small ghost' href='%s'>Download CSV</a></div>" % u("/portal/usage.csv")
            + "<table><thead><tr><th>Account</th><th>Calls</th><th>Tokens</th><th>Credits</th><th>Cost</th><th>All time</th></tr></thead><tbody>"
            + ("".join(acct_rows) or empty(6, "No usage yet this month.")) + "</tbody></table></div>"
            + "<div class='card'><h2>Last 30 days</h2>" + bars + "</div>"
            + "<div class='fgrid'><div class='card'><h2>By action</h2><table><thead><tr><th>Action</th><th>Calls</th><th>OK</th><th>Tokens</th><th>Cost</th></tr></thead><tbody>"
            + (kind_rows or empty(5, "Nothing yet.")) + "</tbody></table></div>"
            + "<div class='card'><h2>By model</h2><table><thead><tr><th>Model</th><th>Calls</th><th>In</th><th>Out</th><th>Cost</th></tr></thead><tbody>"
            + (model_rows or empty(5, "Nothing yet.")) + "</tbody></table></div></div>"
            + "<div class='card'><h2>Latest calls</h2><table><thead><tr><th>When</th><th>Action</th><th>Who</th><th>Result</th><th>Tokens</th><th>Cost</th><th>ms / note</th></tr></thead><tbody>"
            + (recent_rows or empty(7, "Nothing yet.")) + "</tbody></table></div>")


def usage_csv():
    """Every account's consumption, by month, for the finance side."""
    import csv, io
    with db.connect() as conn:
        rows = conn.execute("SELECT strftime('%Y-%m', at, 'unixepoch') month, code_id, kind, COUNT(*) calls, "
                            "SUM(prompt_tokens) pin, SUM(out_tokens) pout, SUM(credits) cr, SUM(cost_usd) usd "
                            "FROM ai_audit GROUP BY month, code_id, kind ORDER BY month DESC, usd DESC").fetchall()
        codes = {r["id"]: r for r in conn.execute("SELECT id, label FROM codes").fetchall()}
    users = {x["code_id"]: x for x in portal.list_users()}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["month", "account", "action", "calls", "input_tokens", "output_tokens", "credits", "cost_usd"])
    for r in rows:
        w.writerow([r["month"], account_label(r["code_id"], users, codes)[0], r["kind"], r["calls"], r["pin"] or 0,
                    r["pout"] or 0, r["cr"] or 0, "%.6f" % (r["usd"] or 0)])
    return buf.getvalue()


def _settings_tab():
    allow, block = portal.domain_lists()
    costs = portal.costs()
    mode = portal.signup_mode()
    opts = "".join("<option value='%s'%s>%s</option>" % (k, " selected" if k == mode else "", lbl) for k, lbl in (
        ("open", "Open — any company email can sign up"), ("approval", "Approval — I approve each new client"),
        ("allowlist", "Invite only — only allow-listed domains"), ("closed", "Closed — no new sign-ups")))
    cost_inputs = "".join("<div><label>%s</label><input type='number' min='0' max='1000' name='cost_%s' value='%d'></div>"
                          % (lbl, k, costs[k]) for k, lbl in (("brief", "AI shortlist with reasons"), ("search", "Shortlist without AI text (0 = free)"),
                                                              ("parse", "Read a free-text brief"), ("chat", "Chat message"),
                                                              ("replace", "Find a replacement (selection)"), ("more", "Add more like these (selection)"),
                                                              ("alike", "Creators like this (selection)")))

    def key_card(which, title, mod, help_):
        hint = mod.key_hint()
        return ("<div class='card'><h2>%s</h2><p class='sec-desc'>%s The key stays on the server in a private file and is never shown again, only its last four characters.</p>%s"
                "<form method='post' action='%s' autocomplete='off'><input type='hidden' name='which' value='%s'><input type='hidden' name='back' value='/portal?tab=settings'>"
                "<label>%s</label><input type='password' name='key' autocomplete='off' placeholder='Paste the key' required> "
                "<button class='btn lime' name='action' value='save'>Save key</button></form>%s</div>"
                % (e(title), help_, ("<p>Saved key: <code>%s</code></p>" % e(hint)) if hint else "<p class='muted'>No key saved.</p>",
                   u("/portal/keys"), which, "Replace key" if hint else "API key",
                   ("<form method='post' action='%s' class='inline' style='margin-top:10px'><input type='hidden' name='which' value='%s'>"
                    "<input type='hidden' name='back' value='/portal?tab=settings'><button class='btn small danger' name='action' value='clear' "
                    "data-confirm-title='Remove this key?' data-confirm='The features that use it switch off until a new key is saved.' data-confirm-ok='Remove key'>Remove key</button></form>" % (u("/portal/keys"), which)) if hint else ""))

    form = (
        "<form method='post' action='%s'><input type='hidden' name='back' value='/portal?tab=settings'>" % u("/portal/settings")
        + "<div class='card'><h2>Sign-up</h2><p class='sec-desc'>Clients sign in with a one-time code sent to a company email. "
          "Personal providers (Gmail, Outlook, iCloud…) are always refused unless you allow-list that exact domain.</p>"
          "<div class='fgrid'><div><label>Who can sign up</label><select name='signup_mode'>" + opts + "</select></div>"
          "<div><label>Welcome credits</label><input type='number' min='0' name='signup_credits' value='%d'></div>" % portal.signup_credits()
        + "<div><label>Guest passcode allowance</label><input type='number' min='0' name='guest_credits' value='%d'>"
          "<div class='price-hint'>One-off credits for clients still using an access code.</div></div>" % portal.guest_credits()
        + "<div><label>New accounts per network per day</label><input type='number' min='1' max='1000' name='signups_per_ip_day' value='%d'>"
          "<div class='price-hint'>Stops one person farming welcome credits.</div></div>" % portal.signups_per_ip()
        + "<div><label>Devices per account</label><input type='number' min='1' max='50' name='user_max_devices' value='%s'></div></div>"
          % e(db.setting("user_max_devices", 5))
        + "<div class='fgrid' style='margin-top:14px'><div><label>Allow-listed domains</label><textarea class='mono' name='domain_allow' placeholder='one per line'>%s</textarea></div>"
          % e("\n".join(allow))
        + "<div><label>Blocked domains</label><textarea class='mono' name='domain_block' placeholder='one per line'>%s</textarea></div></div></div>" % e("\n".join(block))
        + "<div class='card'><h2>Team &amp; notifications</h2><div class='fgrid'>"
          "<div><label>Email the team about</label><p class='muted' style='margin:4px 0 8px'>New clients, briefs, quote requests and credit requests. "
          "The client's KAM is emailed first when one is set.</p><textarea class='mono' name='notify_emails' rows='3' placeholder='sales@hellovoice.co.uk'>%s</textarea></div>"
          % e("\n".join(notify.recipients()))
        + "<div><label>Key account managers</label><p class='muted' style='margin:4px 0 8px'>One per line: Name &lt;email&gt;. Assign them on each client's page.</p>"
          "<textarea class='mono' name='kams' rows='3' placeholder='Marwa Mahmoud &lt;marwa@hellovoice.co.uk&gt;'>%s</textarea></div>"
          % e("\n".join("%s <%s>" % k for k in notify.kams()))
        + "<div><label>Colleagues share selections</label><label style='display:flex;gap:8px;align-items:center;font-weight:400'>"
          "<input type='checkbox' name='team_sharing'%s> People on the same company domain see each other's selections and campaigns</label></div></div></div>"
          % (" checked" if db.setting("team_sharing", True) else "")
        + "<div class='card'><h2>AI credits</h2><p class='sec-desc'>What each action costs a client. A failed AI call is refunded automatically. The admin is never charged.</p>"
          "<div class='fgrid'>" + cost_inputs
        + "<div><label>Monthly credits per client</label><input type='number' min='0' name='monthly_credits' value='%s'>"
          "<div class='price-hint'>Each month a client is topped back up to this. 0 = off. A client's own page can override it.</div></div>"
          % e(db.setting("monthly_credits", 0) or 0) + "</div></div>"
        + "<div class='card'><h2>AI &amp; email</h2><div class='fgrid'>"
          "<div><label>Gemini model</label><input name='gemini_model' value='%s'><div class='price-hint'>Default %s. If a model is retired the next one in line is tried automatically.</div></div>" % (e(gemini.model()), e(gemini.DEFAULT_MODEL))
        + "<div><label>Monthly token ceiling</label><input type='number' min='10000' name='ai_monthly_tokens' value='%d'>"
          "<div class='price-hint'>AI stops for everyone when this is reached.</div></div>" % gemini.monthly_cap()
        + "<div><label>Monthly AI budget (USD)</label><input type='number' min='0' step='1' name='ai_monthly_usd' value='%g'>"
          "<div class='price-hint'>AI stops for everyone when it is reached. 0 = no limit.</div></div>" % gemini.monthly_usd_cap()
        + "<div><label>Copilot model</label><input name='copilot_model' value='%s' placeholder='same as above'>"
          "<div class='price-hint'>A stronger model for your own analysis, e.g. gemini-3.1-pro-preview. Clients keep the main model.</div></div>"
          % e(db.setting("copilot_model", "") or "")
        + "<div><label>Cost per email (USD)</label><input type='number' min='0' step='0.0001' name='email_cost_usd' value='%g'></div>" % mailer.email_cost()
        + "<div><label>Send email from</label><input name='mail_from' value='%s'><div class='price-hint'>Its domain must be verified in Resend.</div></div></div>" % e(mailer.sender())
        + "<label style='margin-top:14px'>Model prices, USD per 1M tokens (model, input, output — one per line)</label>"
          "<textarea class='mono' name='ai_prices' rows='5'>%s</textarea>"
          "<div class='price-hint'>From Google's price list on 7 Oct 2026. gemini-3.8-flash is a launch price until 31 Dec 2026: check it in January. "
          "Each call stores its cost when it happens, so changing a price never rewrites past spend.</div>"
          % e("\n".join("%s %g %g" % (m, p[0], p[1]) for m, p in sorted(gemini.prices().items())))
        + "<label style='margin-top:14px'>What the assistant knows about HelloVoice</label>"
          "<textarea class='mono' name='kb_text' rows='6'>%s</textarea>" % e(db.setting("kb_text", None) or __import__("assistant").DEFAULT_KB)
        + "<label style='margin-top:14px'>Campaigns Helvy may name as case studies (campaign IDs, comma-separated)</label>"
          "<input name='case_study_campaigns' value='%s' placeholder='e.g. 12, 15'>"
          "<div class='price-hint'>Only for clients who approved being named. Every other campaign is used anonymised and in aggregate only. "
          "All AI is free for a client while a campaign of theirs runs (start date to end date + 30 days).</div></div>"
          % e(", ".join(str(x) for x in (db.setting("case_study_campaigns", []) or [])))
        + "<button class='btn lime'>Save settings</button></form>")
    keys = (key_card("gemini", "Gemini API key", gemini, "Powers the shortlist reasons, the chat and the copilot.")
            + graph_card() + smtp_card() + key_card("mail", "Email (Resend) API key — alternative", mailer,
                                     "Only needed if you do not use a company mailbox above."))
    return form + "<div style='margin-top:20px'>" + keys + "</div>"


def graph_card():
    hint = mailer.graph_hint()
    back = "<input type='hidden' name='back' value='/portal?tab=settings'><input type='hidden' name='which' value='graph'>"
    return ("<div class='card'><h2>Email: shared mailbox (Microsoft 365, recommended)</h2>"
            "<p class='sec-desc'>Sends sign-in codes and team notifications as a Microsoft 365 <b>shared mailbox</b>, with no password, through an "
            "app registration (Microsoft Graph). No DNS change. Set up once in Microsoft Entra: register an app, give it the <b>Mail.Send</b> "
            "application permission with admin consent, create a client secret, and limit the app to the shared mailbox. "
            "The secret stays on the server in a private file and is never shown again.</p>"
            + ("<p>Connected: <code>%s</code></p>" % e(hint) if hint else "<p class='muted'>Not connected.</p>")
            + "<form method='post' action='%s' autocomplete='off'>%s<div class='fgrid'>"
              "<div><label>Shared mailbox to send from</label><input name='sender' type='email' placeholder='info@hellovoice.co.uk' required></div>"
              "<div><label>Directory (tenant) ID</label><input name='tenant' placeholder='xxxxxxxx-xxxx-…' required></div>"
              "<div><label>Application (client) ID</label><input name='client_id' placeholder='xxxxxxxx-xxxx-…' required></div>"
              "<div><label>Client secret (Value)</label><input name='secret' type='password' autocomplete='new-password' required></div>"
              "<div><label>Send a test to (optional)</label><input name='test' type='email' placeholder='you@hellovoice.co.uk'></div></div>"
              "<button class='btn lime' name='action' value='save'>%s</button></form>" % (u("/portal/keys"), back, "Replace" if hint else "Connect")
            + (("<form method='post' action='%s' class='inline' style='margin-top:10px'>%s<button class='btn small danger' name='action' value='clear' "
                "data-confirm-title='Disconnect email sending?' data-confirm='Sign-in codes and team emails stop until it is connected again.' data-confirm-ok='Disconnect'>Disconnect</button></form>") % (u("/portal/keys"), back) if hint else "")
            + "</div>")


def smtp_card():
    hint = mailer.smtp_hint()
    back = "<input type='hidden' name='back' value='/portal?tab=settings'><input type='hidden' name='which' value='smtp'>"
    return ("<div class='card'><h2>Email: SMTP server (Amazon SES, Microsoft 365 or other)</h2>"
            "<p class='sec-desc'>Sends the sign-in codes and team notifications from one of your own Outlook mailboxes, the same email "
            "hellovoice.co.uk already uses, so no DNS change is needed. In Microsoft 365 admin, turn on <b>Authenticated SMTP</b> for that "
            "mailbox (Exchange admin → Recipients → Mailboxes → the mailbox → Manage email apps). If the mailbox uses MFA, use an app password. "
            "The password stays on the server in a private file and is never shown again.</p>"
            + ("<p>Connected: <code>%s</code></p>" % e(hint) if hint else "<p class='muted'>No mailbox connected.</p>")
            + "<form method='post' action='%s' autocomplete='off'>%s<div class='fgrid'>"
              "<div><label>SMTP username</label><input name='user' placeholder='AKIA… (SES) or name@hellovoice.co.uk' required></div>"
              "<div><label>SMTP password</label><input name='password' type='password' autocomplete='new-password' required></div>"
              "<div><label>Send a test to (optional)</label><input name='test' type='email' placeholder='you@hellovoice.co.uk'></div>"
              "<div><label>Send as</label><input name='send_as' type='email' placeholder='info@hellovoice.co.uk'>"
              "<div class='price-hint'>Required for SES (a verified address or domain there). For Microsoft 365, a shared mailbox the user may send as.</div></div>"
              "<div><label>Server</label><input name='host' value='smtp.office365.com'>"
              "<div class='price-hint'>SES: email-smtp.&lt;region&gt;.amazonaws.com, e.g. email-smtp.eu-west-1.amazonaws.com</div></div></div>"
              "<button class='btn lime' name='action' value='save'>%s</button></form>" % (u("/portal/keys"), back, "Replace mailbox" if hint else "Connect mailbox")
            + (("<form method='post' action='%s' class='inline' style='margin-top:10px'>%s<button class='btn small danger' name='action' value='clear' "
                "data-confirm-title='Disconnect the mailbox?' data-confirm='Sign-in codes and team emails stop until it is connected again.' data-confirm-ok='Disconnect'>Disconnect</button></form>") % (u("/portal/keys"), back) if hint else "")
            + "</div>")


def portal_page(tab="accounts", ok=None, err=None, query=None):
    tab = tab if tab in dict(TABS) else "accounts"
    body = {"accounts": _accounts_tab, "codes": _codes_tab, "briefs": _briefs_tab, "chats": _chats_tab, "usage": _usage_tab, "settings": _settings_tab}[tab]()
    status = ("<span class='pill %s'>Gemini %s</span> <span class='pill %s'>Email %s</span>" % (
        "live" if gemini.configured() else "warn", "ready" if gemini.configured() else "not set up",
        "live" if mailer.configured() else "warn", ("ready (%s)" % {"graph": "shared mailbox", "smtp": "mailbox", "resend": "Resend"}.get(mailer.engine(), "")) if mailer.configured() else "not set up"))
    return page("Client portal", STAT_CSS + ui.header("Client portal", "Company-email accounts, AI credits, briefs and AI settings. " + status,
                tabs=_tabs(tab)) + _banner(ok, err) + body, "/portal")


# ------------------------------------------------- access codes -> accounts --

def _codes_tab():
    """The shared access codes still in use, with what hangs off each, and the one action:
    invite that client to an email account. Nothing here revokes a code or moves a link."""
    import codelinks
    rows = codelinks.shared_codes()
    hid = lambda name, val: "<input type='hidden' name='%s' value='%s'>" % (name, e(val))
    back = hid("back", "/portal?tab=codes")
    intro = ("<div class='card'><h2>Move shared access codes onto email accounts</h2><p class='sec-desc'>The sign-in page no longer "
             "offers access codes. Invite each client below to an email account: the code's selections and campaigns are linked to "
             "that account (they see them and can approve or reject creators), and the code keeps working, so every link already "
             "sent still opens. Nothing is revoked here; retire a code from <a href='%s'>Access codes</a> when its client is in. "
             "No email is sent from here: tell the client to sign in at the catalogue with that address.</p></div>" % u("/codes"))
    if not rows:
        return intro + "<div class='card'><p class='muted'>No active shared access codes.</p></div>"
    cards = []
    for x in rows:
        c = x["code"]
        sels = "".join("<li><a href='%s'>%s</a> <span class='muted'>%d creators · %s</span></li>" % (
            u("/selections/edit?id=%d" % s_["id"]), e(s_["name"]), len(json.loads(s_["codes"] or "[]")), e(ago(s_["updated_at"])))
            for s_ in x["selections"]) or "<li class='muted'>none</li>"
        camps = "".join("<li><a href='%s'>%s</a> <span class='pill'>%s</span></li>" % (u("/campaigns/edit?id=%d" % k["id"]), e(k["name"]), e(k["status"]))
                        for k in x["campaigns"]) or "<li class='muted'>none</li>"
        links = "".join(
            "<li>%s %s <form method='post' action='%s' class='inline'>%s%s<button class='btn tiny ghost' title='Stop linking'>Remove</button></form></li>" % (
                e(l["email"]),
                ("<span class='pill live'>linked · %s</span>" % e(l["user_name"] or "account")) if l["user_code_id"] else "<span class='pill warn'>waiting for first sign-in</span>",
                u("/portal/code/unlink"), hid("link", l["id"]), back) for l in x["links"]) or "<li class='muted'>not invited yet</li>"
        form = ("<form method='post' action='%s' class='row'>%s%s<div><label>Client's work email</label>"
                "<input type='email' name='email' required placeholder='name@company.com'></div>"
                "<div><button class='btn lime'>Invite to email account</button></div></form>" % (u("/portal/code/link"), hid("code_id", c["id"]), back))
        cards.append("<div class='card'><h2>%s <span class='muted'>· ····%s</span></h2><p class='muted'>Created %s · used %d times · last %s</p>"
                     "<div class='fgrid'><div><strong>Selections</strong><ul>%s</ul></div><div><strong>Campaigns</strong><ul>%s</ul></div>"
                     "<div><strong>Email accounts</strong><ul>%s</ul></div></div>%s</div>"
                     % (e(c["label"]), e(c["hint"]), e(ts(c["created_at"])), c["uses"] or 0, e(ago(x["last_used"])) if x["last_used"] else "never",
                        sels, camps, links, form))
    return intro + "".join(cards)


# ------------------------------------------------------------- one client --

def user_page(usr, ok=None, err=None):
    cid = usr["code_id"]
    bal = portal.balance(cid)
    ledger = portal.ledger(cid, 25)
    with db.connect() as conn:
        sels = conn.execute("SELECT id, name, updated_at, codes, token FROM selections WHERE code_id = ? ORDER BY updated_at DESC LIMIT 20", (cid,)).fetchall()
        camps = conn.execute("SELECT id, name, status, starts_at, token FROM campaigns WHERE code_id = ? ORDER BY id DESC LIMIT 20", (cid,)).fetchall()
        quotes = conn.execute("SELECT id, at, selection_name, handled_at FROM requests WHERE code_id = ? ORDER BY id DESC LIMIT 20", (cid,)).fetchall()
        ev = conn.execute("SELECT kind, COUNT(*) n, MAX(at) last FROM events WHERE code_id = ? GROUP BY kind ORDER BY n DESC", (cid,)).fetchall()
    hid = lambda name, val: "<input type='hidden' name='%s' value='%s'>" % (name, e(val))
    back = hid("back", "/portal/user?id=%d" % usr["id"])
    status_btns = "".join(
        "<form method='post' action='%s' class='inline'>%s%s%s<button class='btn small %s'>%s</button></form> " % (
            u("/portal/user/status"), hid("id", usr["id"]), hid("status", s), back, cls, lbl)
        for s, lbl, cls in (("active", "Activate", "lime"), ("pending", "Put on hold", "ghost"), ("suspended", "Suspend", "danger"))
        if s != usr["status"])
    profile = (
        "<div class='card'><h2>Profile</h2><form method='post' action='%s'>%s%s<div class='fgrid'>"
        "<div><label>Name</label><input name='name' value='%s'></div><div><label>Company</label><input name='company' value='%s'></div>"
        "<div><label>Job title</label><input name='job_title' value='%s'></div><div><label>Phone</label><input name='phone' value='%s'></div>"
        "<div><label>KAM</label><select name='kam'>%s</select></div>"
        "<div><label>Monthly credits</label><input type='number' min='0' name='monthly_credits' value='%s' placeholder='default'></div></div>"
        "<label style='margin-top:12px'>Internal notes</label><textarea name='notes' rows='3'>%s</textarea>"
        "<p class='muted'>%s · joined %s · domain %s</p><button class='btn lime'>Save</button></form></div>"
        % (u("/portal/user/save"), hid("id", usr["id"]), back, e(usr["name"]), e(usr["company"]), e(usr["job_title"]), e(usr["phone"]),
           "<option value=''>—</option>" + "".join("<option value='%s'%s>%s</option>" % (e(m), " selected" if usr["kam"] == m else "", e(n))
                                                    for n, m in notify.kams()),
           e(usr["monthly_credits"] if usr["monthly_credits"] is not None else ""),
           e(usr["notes"]), e(usr["email"]), e(ts(usr["created_at"])), e(usr["domain"])))
    credits = (
        "<div class='card'><h2>AI credits: %d</h2><form method='post' action='%s' class='row'>%s%s"
        "<div><label>Add or remove</label><input type='number' name='amount' placeholder='e.g. 50 or -10' required></div>"
        "<div><label>Reason</label><input name='reason' placeholder='Top-up for Q4 campaign'></div><div><button class='btn lime'>Apply</button></div></form>"
        "<div style='margin:4px 0 14px'>%s</div>"
        "<table><thead><tr><th>When</th><th>Change</th><th>Balance</th><th>Reason</th></tr></thead><tbody>%s</tbody></table></div>"
        % (bal, u("/portal/user/credits"), hid("id", usr["id"]), back,
           " ".join("<form method='post' action='%s' class='inline'>%s%s%s%s<button class='btn small ghost'>+%d</button></form>"
                    % (u("/portal/user/credits"), hid("id", usr["id"]), back, hid("amount", n), hid("reason", "Credit pack +%d" % n), n)
                    for n in (50, 200, 500)),
           "".join("<tr><td class='muted'>%s</td><td>%+d</td><td>%d</td><td>%s</td></tr>" % (e(ago(r["at"])), r["delta"], r["balance_after"], e(r["reason"]))
                   for r in ledger) or "<tr><td colspan='4' class='muted'>No movements.</td></tr>"))
    status_pill = lambda st: "<span class='pill %s'>%s</span>" % ({"live": "live", "draft": "warn"}.get(st, ""), e(st))
    work = (
        "<div class='card'><h2>Work</h2>"
        "<p><strong>Campaigns</strong></p><ul>%s</ul>"
        "<p><strong>Quote requests</strong></p><ul>%s</ul>"
        % ("".join("<li><a href='%s'>%s</a> %s %s</li>" % (u("/campaigns/edit?id=%d" % k["id"]), e(k["name"]), status_pill(k["status"]),
                                                            views.open_link("campaign", k["token"], "Client view", "btn tiny ghost")) for k in camps)
           or "<li class='muted'>none</li>",
           "".join("<li><a href='%s'>%s</a> <span class='muted'>%s · %s</span></li>" % (u("/requests") + "#r%d" % r["id"], e(r["selection_name"] or "Quote"),
                   e(ago(r["at"])), "answered" if r["handled_at"] else "<b>waiting</b>") for r in quotes) or "<li class='muted'>none</li>")
        + "<p><strong>Selections</strong></p><ul>%s</ul><p><strong>Briefs</strong></p><ul>%s</ul><p><strong>Activity</strong></p><ul>%s</ul></div>"
        % ("".join("<li><a href='%s'>%s</a> <span class='muted'>%d creators · %s</span> %s</li>" % (u("/selections/edit?id=%d" % s["id"]), e(s["name"]),
                   len(json.loads(s["codes"] or "[]")), e(ago(s["updated_at"])), views.open_link("selection", s["token"], "Link", "btn tiny ghost")) for s in sels)
           or "<li class='muted'>none</li>",
           "".join("<li>%s <span class='muted'>%s</span></li>" % (e(b["summary"]), e(ago(b["created_at"]))) for b in portal.briefs_for(cid, 10)) or "<li class='muted'>none</li>",
           "".join("<li>%s × %d <span class='muted'>last %s</span></li>" % (e(r["kind"]), r["n"], e(ago(r["last"]))) for r in ev) or "<li class='muted'>none</li>"))
    reqs = [r for r in portal.open_credit_requests(cid) if not r["handled_at"]]
    req_html = "".join(
        "<div class='note'><strong>Asked for %d credits</strong> %s · %s <form method='post' action='%s' class='inline'>%s%s"
        "<input type='hidden' name='grant' value='%d'><button class='btn small lime' name='action' value='grant'>Grant</button> "
        "<button class='btn small ghost' name='action' value='decline'>Decline</button></form></div>"
        % (r["amount"], e(r["note"] or ""), e(ago(r["at"])), u("/portal/credit-request"), hid("id", r["id"]), back, r["amount"]) for r in reqs)
    chats = "".join("<li><a href='%s'>%s</a> <span class='muted'>%d messages · %s</span></li>"
                    % (u("/portal/chat?id=%d" % t["id"]), e((t["first"] or "Conversation")[:80]), t["n"], e(ago(t["last"])))
                    for t in portal.threads(cid, "client", 30) if t["n"])
    quotes = "".join("<li>%s <a class='muted' href='%s'>quotation</a></li>" % (e(s["name"]), u("/portal/quote?sel=%d" % s["id"])) for s in sels)
    extra = ("<div class='card'><h2>Conversations</h2><ul>%s</ul><h2 style='margin-top:18px'>Quotations</h2><ul>%s</ul></div>"
             % (chats or "<li class='muted'>none</li>", quotes or "<li class='muted'>none</li>"))
    danger = ("<details class='card'><summary class='hd'><h2>Delete account</h2></summary><p class='sec-desc'>Revokes access and erases the person's "
              "details, chats and sign-in codes. Selections and quote requests stay as business records without their details.</p>"
              "<form method='post' action='%s'>%s%s<input name='confirm' placeholder='Type DELETE' required> "
              "<button class='btn small danger'>Delete account</button></form></details>" % (u("/portal/user/delete"), hid("id", usr["id"]), back))
    return page(usr["email"], STAT_CSS + ui.header(usr["name"] or usr["email"], "%s · %s" % (usr["company"] or "no company", usr["email"]),
                crumbs=[("Client portal", u("/portal")), (usr["email"], None)], actions=status_btns + _status_pill(usr["status"]))
                + _banner(ok, err) + req_html + profile + credits + work + extra + danger, "/portal")


# ----------------------------------------------------------------- copilot --

SUGGESTIONS = [
    "Which creators are missing a city, tier or photo?",
    "What are clients asking for that our roster can't supply?",
    "Who signed up this week and what did they ask for?",
    "Find 10 skincare creators in Riyadh on Instagram with 50k–300k followers",
    "How many credits has each client used this month?",
    "Add a new creator: Reem Saleh, @reem.s on Instagram, 85k, Riyadh, skincare, Micro-tier",
    "Make a draft campaign from the latest selection and set it to start next Sunday",
]

COPILOT_JS = r"""
(function(){
  var log=document.getElementById('cp-log'), box=document.getElementById('cp-text'), form=document.getElementById('cp-form'),
      thread=null, busy=false, URL_CHAT=%(chat)s, URL_OK=%(ok)s, URL_NO=%(no)s;
  function esc(s){return s.replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function md(t){ var h=esc(t).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/`([^`]+)`/g,'<code>$1</code>');
    var out=[],inl=false; h.split('\n').forEach(function(l){ if(/^\s*[-*] /.test(l)){ if(!inl){out.push('<ul>');inl=true;} out.push('<li>'+l.replace(/^\s*[-*] /,'')+'</li>'); }
      else { if(inl){out.push('</ul>');inl=false;} out.push(l?'<p>'+l+'</p>':''); } }); if(inl) out.push('</ul>'); return out.join(''); }
  function add(role,html){ var d=document.createElement('div'); d.className='cp-m cp-'+role; d.innerHTML=html; log.appendChild(d); log.scrollTop=log.scrollHeight; return d; }
  function post(url,body){ return fetch(url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(function(r){return r.json();}); }
  function queued(list){ (list||[]).forEach(function(q){
    var d=add('act','<div><b>Waiting for you</b><p>'+esc(q.text)+'</p></div><div class="cp-btns"><button class="btn small lime">Confirm</button> <button class="btn small ghost">Dismiss</button></div>');
    var b=d.querySelectorAll('button');
    b[0].onclick=function(){ b[0].disabled=b[1].disabled=true; post(URL_OK,{token:q.token}).then(function(r){ d.innerHTML=r.ok?'<b>Done.</b> '+esc(q.text)+' <span class="muted">Undo it from History &amp; undo.</span>':'<b>Not done.</b> '+esc(r.error||'Unknown error'); }); };
    b[1].onclick=function(){ post(URL_NO,{token:q.token}).then(function(){ d.innerHTML='<span class="muted">Dismissed: '+esc(q.text)+'</span>'; }); }; }); }
  function send(t){ if(busy||!t.trim())return; busy=true; add('me',esc(t)); var w=add('bot','<span class="muted">Thinking…</span>');
    post(URL_CHAT,{message:t,thread:thread}).then(function(r){ busy=false; if(!r.ok){ w.innerHTML='<span class="cp-err">'+esc(r.error||'Something went wrong')+'</span>'; return; }
      thread=r.thread; w.innerHTML=md(r.reply||''); queued(r.queued); }).catch(function(){ busy=false; w.innerHTML='<span class="cp-err">Could not reach the server.</span>'; }); }
  form.addEventListener('submit',function(e){ e.preventDefault(); var t=box.value; box.value=''; send(t); });
  box.addEventListener('keydown',function(e){ if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); form.requestSubmit(); } });
  document.querySelectorAll('.cp-chip').forEach(function(c){ c.onclick=function(){ send(c.textContent); }; });
})();
"""


def copilot_page(email, configured, embed=False):
    chips = "".join("<button type='button' class='cp-chip'>%s</button>" % e(s) for s in SUGGESTIONS)
    off = "" if configured else ("<div class='note'>The copilot needs a Gemini key. <a href='%s'>Add it in Client portal → Settings &amp; keys</a>.</div>"
                                 % u("/portal?tab=settings"))
    css = ("<style>.cp{display:flex;flex-direction:column;height:calc(100vh - 250px);min-height:420px}"
           "#cp-log{flex:1;overflow:auto;background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px;display:flex;flex-direction:column;gap:10px}"
           ".cp-m{max-width:78%;padding:10px 14px;border-radius:14px;line-height:1.5;font-size:var(--t-md,14.5px)}.cp-m p{margin:0 0 6px}.cp-m ul{margin:4px 0 6px 18px;padding:0}"
           ".cp-me{align-self:flex-end;background:var(--ink);color:#fff}.cp-bot{align-self:flex-start;background:#f3f1ec}"
           ".cp-act{align-self:flex-start;background:var(--amber-soft);border:1px solid var(--amber);width:78%}.cp-btns{margin-top:8px}"
           ".cp-err{color:var(--red)}#cp-form{display:flex;gap:10px;margin-top:12px}#cp-text{flex:1;min-height:46px;max-height:140px;border-radius:14px;padding:10px 14px;font:inherit;border:1px solid var(--line-strong)}"
           ".cp-chips{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 12px}.cp-chip{border:1px solid var(--line-strong);background:#fff;border-radius:999px;padding:6px 14px;font:inherit;font-size:var(--t-sm,13px);cursor:pointer}"
           ".cp-chip:hover{border-color:var(--ink)}</style>")
    js = COPILOT_JS % {"chat": json.dumps(u("/ai/chat")), "ok": json.dumps(u("/ai/confirm")), "no": json.dumps(u("/ai/dismiss"))}
    body = (css + ui.header("AI copilot", "Ask about your data, build selections, check client activity, or ask it to make a change. "
                            "Changes are never made until you press Confirm, and each one appears in History so you can undo it.")
            + off + "<div class='cp'><div class='cp-chips'>" + chips + "</div><div id='cp-log'><div class='cp-m cp-bot'>Hi. What would you like to look at or change?</div></div>"
            "<form id='cp-form'><textarea id='cp-text' placeholder='Ask anything about creators, clients, briefs or credits…' rows='1'></textarea>"
            "<button class='btn lime'>Send</button></form></div><script>" + js + "</script>")
    if embed:
        # Inside the side panel that every admin page has: just the conversation.
        slim = ("<style>body{margin:0;background:var(--white)}.cp{height:100vh;min-height:0;padding:12px;box-sizing:border-box}"
                ".cp-chips{max-height:84px;overflow:auto}#cp-log{border:0;background:var(--paper)}</style>")
        return ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<meta name="robots" content="noindex,nofollow"><title>AI copilot</title><link rel="stylesheet" href="%s"></head><body>%s%s%s'
                '<div class="cp"><div class="cp-chips">%s</div><div id="cp-log"><div class="cp-m cp-bot">Hi. Ask about creators, clients, briefs or credits, '
                'or ask for a change. Nothing changes until you press Confirm.</div></div><form id="cp-form"><textarea id="cp-text" '
                'aria-label="Message the copilot" placeholder="Ask anything…" rows="1"></textarea><button class="btn lime">Send</button></form></div>'
                '<script>%s</script></body></html>') % (u("/static/admin.css"), css, slim, off, chips, js)
    return page("AI copilot", body, "/ai")
