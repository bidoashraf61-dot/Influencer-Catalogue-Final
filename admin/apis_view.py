"""The APIs page: connect Apify, save jobs, run them now or on a schedule, see
what they cost. Everything is a form posting to /apis/*; the token is never
rendered, only its last four characters."""
import json

import apify
import db
import ui
import views as V

e, u = V.e, V.u
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _sources(current):
    opts = [("sample20", "Test sample: 20 creators (those with an analysis first)"),
            ("all", "All active creators"),
            ("noanalysis", "Only creators with no analysis uploaded yet"),
            ("nosnap", "Only creators not scraped yet on this platform")]
    for s in db.list_selections():
        opts.append(("selection:%d" % s["id"], "Selection: " + (s["name"] or "Untitled")))
    for c in db.list_campaigns():
        opts.append(("campaign:%d" % c["id"], "Campaign: " + (c["name"] or "Untitled")))
    return "".join("<option value='%s'%s>%s</option>" % (e(v), " selected" if v == current else "", e(l))
                   for v, l in opts)


def _job_form(job, presets_js=False):
    j = job
    g = (lambda k, d="": (j[k] if j is not None and j[k] is not None else d))
    sched = g("schedule", "manual")
    opt = lambda val, label, cur: "<option value='%s'%s>%s</option>" % (val, " selected" if val == cur else "", label)
    return (
        "<form method='post' action='" + u("/apis/job/save") + "'>"
        + ("<input type='hidden' name='id' value='" + str(j["id"]) + "'>" if j is not None else "")
        + "<div class='row'>"
        + "<div><label>Job name</label><input name='name' required value='" + e(g("name")) + "' placeholder='Weekly follower check'></div>"
        + "<div><label>Platform</label><input name='platform' value='" + e(g("platform", "Instagram")) + "'></div>"
        + "<div><label>What it brings back</label><select name='kind'>"
        + opt("profiles", "Profile numbers (saved as snapshots)", g("kind", "profiles"))
        + opt("analysis", "Analysis (results kept as returned)", g("kind"))
        + opt("posts", "Posts (results kept as returned)", g("kind")) + opt("other", "Other", g("kind"))
        + "</select></div></div><div class='row'>"
        + "<div><label>Actor</label><input name='actor' required value='" + e(g("actor")) + "' placeholder='username/actor-name'></div>"
        + "<div><label>Which creators</label><select name='source'>" + _sources(g("source", "all")) + "</select></div>"
        + "<div><label>Max handles per run</label><input name='max_handles' type='number' min='1' max='1000' value='"
        + str(g("max_handles", 100)) + "'></div>"
        + "<div><label>Estimated cost per creator (USD)</label><input name='est_each' type='number' step='0.001' min='0' value='"
        + str(g("est_each", 0.003)) + "'></div></div>"
        + "<label>Input sent to the actor (JSON)</label><textarea name='input' rows='3' style='font-family:monospace;width:100%'>"
        + e(g("input", apify.PRESETS["ig_profiles"]["input"])) + "</textarea>"
        + "<div class='price-hint'><code>{{handles}}</code> sends all the handles in one run. <code>{{handle}}</code> makes "
          "one run per creator (needed by actors that take a single handle). <code>{{count}}</code> is how many. "
          "A run that would pass the monthly budget is refused. Field names differ per actor, so copy them from "
          "the actor's Input tab in Apify.</div>"
        + "<div class='row'><div><label>Runs</label><select name='schedule'>"
        + opt("manual", "Only when I press Run", sched) + opt("daily", "Every day", sched)
        + opt("weekly", "Every week", sched) + "</select></div>"
        + "<div><label>At (Riyadh time)</label><input name='at_time' type='time' value='" + e(g("at_time", "03:00")) + "'></div>"
        + "<div><label>Weekly on</label><select name='weekday'>"
        + "".join(opt(str(i), d, str(g("weekday", 0))) for i, d in enumerate(DAYS)) + "</select></div></div>"
        + "<button class='btn lime'>Save job</button></form>")


def pack_card():
    chk = lambda n, label, on=True: ("<label style='display:inline-flex;gap:6px;margin-right:16px'><input type='checkbox' name='%s'%s> %s</label>"
                                     % (n, " checked" if on else "", label))
    return (
        "<section class='card'><div class='hd'><h2>Collect everything</h2></div>"
        "<p class='sec-desc'>One press runs the full set of actors for the platforms you tick: profile numbers, "
        "engagement analytics, and audience demographics. Each step is a normal job below, so it can be "
        "edited or scheduled on its own. If the whole collection would pass the monthly budget, nothing starts.</p>"
        "<form method='post' action='" + u("/apis/pack") + "' onsubmit=\"return confirm('This starts several runs and spends money. Continue?')\">"
        "<div style='margin:6px 0 12px'>" + chk("plat_instagram", "Instagram") + chk("plat_tiktok", "TikTok") + "</div>"
        "<div class='row'><div><label>Which creators</label><select name='source'>" + _sources("sample20") + "</select></div>"
        "<div><label>Max creators</label><input name='max_handles' type='number' min='1' max='1000' value='20'></div>"
        "<div><label>Or one specific creator (code)</label><input name='one_creator' placeholder='e.g. HV-MI-007' autocomplete='off'></div>"
        "<div><label>Repeat</label><select name='schedule'><option value='manual'>Only now</option>"
        "<option value='weekly'>Every week</option><option value='daily'>Every day</option></select></div>"
        "<div><label>At (Riyadh time)</label><input name='at_time' type='time' value='03:00'></div></div>"
        "<div style='margin:10px 0'>" + chk("audience", "Audience demographics (about $1.70 per creator per platform)")
        + chk("audit", "Instagram follower audit (about $2 per creator)", False) + "</div>"
        "<button class='btn lime'>Collect everything</button></form></section>")


def data_tab(query_q=""):
    cov = []
    for plat in ("Instagram", "TikTok"):
        cov.append("<tr><td colspan='3'><strong>" + plat + "</strong></td></tr>"
                   + "".join("<tr><td>" + e(l) + "</td><td class='muted' style='font-size:12px'>" + e(a) + "</td><td>"
                             + str(n) + " creators</td></tr>" for l, a, n in apify.coverage(plat)))
    rows = "".join(
        "<tr><td><a href='" + u("/apis/creator?code=" + r["code"]) + "'><strong>" + e(r["name"]) + "</strong></a> "
        "<span class='muted'>" + e(r["code"]) + "</span></td><td>" + str(r["actors"]) + " sources</td>"
        "<td class='muted'>" + V.ago(r["last"]) + "</td></tr>" for r in apify.creators_with_data(query_q))
    return ("<section class='card'><div class='hd'><h2>Coverage</h2></div><table><tbody>" + "".join(cov) + "</tbody></table></section>"
            "<section class='card'><div class='hd'><h2>Creators with collected data</h2></div>"
            "<form method='get' action='" + u("/apis") + "'><input type='hidden' name='tab' value='data'>"
            "<input name='q' value='" + e(query_q) + "' placeholder='Search by creator name or code' style='width:100%;margin-bottom:12px'></form>"
            "<table><tbody>" + (rows or "<tr><td class='muted'>Nothing collected yet. Run a collection first.</td></tr>")
            + "</tbody></table></section>")


def creator_page(code):
    with db.connect() as conn:
        c = conn.execute("SELECT * FROM creators WHERE code = ?", (code,)).fetchone()
    cards = []
    for r in apify.creator_data(code):
        try:
            pretty = json.dumps(json.loads(r["data"]), indent=2, ensure_ascii=False)
        except ValueError:
            pretty = r["data"]
        cards.append("<details class='card' open><summary class='hd'><h2>" + e(r["platform"] or "") + " · " + e(r["actor"] or "")
                     + "</h2><span class='muted'>" + V.ts(r["at"]) + "</span></summary><pre style='white-space:pre-wrap;font-size:12px;"
                     "max-height:520px;overflow:auto'>" + e(pretty) + "</pre></details>")
    body = (ui.header(c["name"] if c else code, "Everything collected for this creator, latest result from each source.",
                      crumbs=[("APIs", u("/apis?tab=data")), (code, None)])
            + ("".join(cards) or "<p class='muted'>Nothing collected for this creator yet.</p>"))
    return V.page("APIs", body, "/apis")


def health_card():
    h, t = apify.health(), apify.last_test()
    spent, bud = apify.spent_this_month(), apify.budget()
    pct = int(min(100, round(spent * 100.0 / bud))) if bud else 0
    colour = "#c0392b" if pct >= 100 else ("#e67e22" if pct >= 80 else "var(--ink)")
    alert = ""
    if pct >= 80:
        alert = ("<div class='err'><strong>%d%% of the monthly budget is used</strong> ($%.2f of $%.2f)."
                 " New runs are refused once it is reached.</div>" % (pct, spent, bud))
    paused = apify.paused()
    return (
        alert
        + ("<div class='err'><strong>Apify is paused.</strong> No run will start, scheduled or manual.</div>" if paused else "")
        + "<section class='card'><div class='hd'><h2>Status</h2>"
          "<form method='post' action='" + u("/apis/pause") + "' class='inline'><button class='btn small " + ("lime" if paused else "danger") + "'>"
        + ("Resume everything" if paused else "Pause everything") + "</button></form></div>"
        "<div class='row'>"
        "<div><label>Connection</label>" + (
            ("<span class='pill " + ("live" if t["ok"] else "dead") + "'>" + ("ok" if t["ok"] else "failed") + "</span> <span class='muted'>tested "
             + V.ago(t["at"]) + "</span>") if t else "<span class='muted'>not tested yet</span>") + "</div>"
        "<div><label>Last successful run</label>" + V.ago(h["last_ok"]) + "</div>"
        "<div><label>Running / queued</label>%d / %d</div>" % (h["running"], h["queued"])
        + "<div><label>Failed in the last 24 h</label>%d</div></div>" % h["failed_24h"]
        + "<label style='margin-top:10px'>Budget this month: $%.2f of $%.2f (%d%%)</label>" % (spent, bud, pct)
        + "<div style='height:10px;border-radius:6px;background:var(--line,#e5e5e0);overflow:hidden'><div style='height:100%%;width:%d%%;background:%s'></div></div>"
          % (pct, colour) + "</section>")


def usage_card():
    rows = "".join("<tr><td>%s</td><td>%d</td><td>%d</td><td>$%.2f</td></tr>" % (e(r["job_name"] or "—"), r["runs"], r["ok"], r["cost"])
                   for r in apify.spend_by_job())
    return ("<section class='card'><div class='hd'><h2>Spend by job, this month</h2></div><table><thead><tr><th>Job</th>"
            "<th>Runs</th><th>Succeeded</th><th>Cost</th></tr></thead><tbody>"
            + (rows or "<tr><td colspan='4' class='muted'>No runs this month.</td></tr>") + "</tbody></table></section>")


def activity_card():
    rows = "".join("<tr><td class='muted'>%s</td><td>%s</td><td><strong>%s</strong> <span class='muted'>%s</span></td></tr>"
                   % (V.ts(r["at"]), e(r["who"] or ""), e(r["action"]), e(r["detail"] or "")) for r in apify.list_audit())
    return ("<section class='card'><div class='hd'><h2>Activity</h2><span class='muted'>who changed what on this page</span></div>"
            "<table><tbody>" + (rows or "<tr><td class='muted'>Nothing yet.</td></tr>") + "</tbody></table></section>")


def apify_tab(query=None):
    query = query or {}
    hint = apify.token_hint()
    spent, bud, cap = apify.spent_this_month(), apify.budget(), apify.run_cap()
    n_snap, n_creators, last = apify.snapshot_summary()

    conn_card = (
        "<section class='card'><div class='hd'><h2>Apify connection</h2>"
        "<span class='pill " + ("live" if hint else "dead") + "'>" + ("connected" if hint else "not connected") + "</span></div>"
        "<p class='sec-desc'>The token stays on the server. It is never shown again after saving, only its last four characters.</p>"
        + ("<p>Saved token: <code>" + e(hint) + "</code></p>"
           "<form method='post' action='" + u("/apis/test") + "' class='inline'><button class='btn small'>Test connection</button></form> "
           "<form method='post' action='" + u("/apis/token/clear") + "' class='inline' onsubmit=\"return confirm('Remove the token? Scheduled jobs stop until a new one is saved.')\">"
           "<button class='btn small danger'>Remove token</button></form>" if hint else "")
        + "<form method='post' action='" + u("/apis/token") + "' autocomplete='off' style='margin-top:12px'>"
          "<label>" + ("Replace token" if hint else "Apify API token") + "</label>"
          "<input name='token' type='password' autocomplete='off' placeholder='From Apify → Settings → Integrations' required>"
          "<button class='btn lime' style='margin-top:8px'>Save and test</button></form></section>")

    limits = (
        "<section class='card'><div class='hd'><h2>Spend limits</h2><span class='muted'>$%.2f of $%.2f used this month</span></div>"
        "<p class='sec-desc'>Our own guard rails, on top of the cap you set inside Apify. A run is refused once the month's budget is reached, "
        "and each run is stopped by Apify at the per-run limit.</p>"
        "<form method='post' action='%s'><div class='row'>"
        "<div><label>Monthly budget (USD)</label><input name='budget' type='number' step='0.5' min='0.5' value='%s'></div>"
        "<div><label>Per-run limit (USD)</label><input name='run_cap' type='number' step='0.25' min='0.25' value='%s'></div>"
        "<div style='align-self:end'><button class='btn small'>Save limits</button></div></div></form></section>"
    ) % (spent, bud, u("/apis/budget"), bud, cap)

    rows = []
    for j in apify.list_jobs():
        when = {"manual": "Manual", "daily": "Daily " + j["at_time"],
                "weekly": DAYS[j["weekday"]] + " " + j["at_time"]}[j["schedule"]]
        pid = "job-%d" % j["id"]
        post = lambda path, label, cls="small", confirm=None: (
            "<form method='post' action='" + u(path) + "' class='inline'"
            + (" onsubmit=\"return confirm('" + confirm + "')\"" if confirm else "")
            + "><input type='hidden' name='id' value='" + str(j["id"]) + "'><button class='btn " + cls + "'>" + label + "</button></form> ")
        rows.append(
            "<tr><td><strong>" + e(j["name"]) + "</strong><br><span class='muted' style='font-size:12px'>"
            + e(j["actor"]) + " · " + e(j["platform"]) + " · up to " + str(j["max_handles"]) + "</span></td>"
            "<td>" + e(when) + "</td><td class='muted'>" + V.ago(j["last_started"]) + "</td>"
            "<td><span class='pill " + ("live" if j["enabled"] else "dead") + "'>" + ("on" if j["enabled"] else "paused") + "</span></td>"
            "<td class='right'>" + post("/apis/job/run", "Run now", "small lime")
            + post("/apis/job/estimate", "Estimate cost", "small ghost")
            + post("/apis/job/clone", "Copy", "small ghost")
            + post("/apis/job/toggle", "Pause" if j["enabled"] else "Resume", "small ghost")
            + post("/apis/job/delete", "Delete", "small danger ghost", "Delete this job? Its past runs stay in the list.")
            + "</td></tr><tr><td colspan='5'><details><summary class='btn small ghost'>Edit</summary>"
            + _job_form(j) + "</details></td></tr>")
    jobs_body = "".join(rows) or "<tr><td colspan='5'>" + ui.empty("flag", "No jobs yet", "Create one below.") + "</td></tr>"

    presets = "".join("<option value='%s'>%s</option>" % (k, e(p["label"])) for k, p in apify.PRESETS.items())
    preset_js = ("<script>(function(){var P=" + json.dumps({k: p for k, p in apify.PRESETS.items()}) + ";"
                 "var s=document.getElementById('preset');if(!s)return;s.addEventListener('change',function(){"
                 "var p=P[s.value],f=s.form;f.actor.value=p.actor;f.platform.value=p.platform;f.kind.value=p.kind;f.input.value=p.input;f.est_each.value=p.est;});})();</script>")
    jobs = (
        "<section class='card'><div class='hd'><h2>Jobs</h2>"
        "<form method='post' action='" + u("/apis/refresh") + "' class='inline'><button class='btn small ghost'>Check running jobs</button></form></div>"
        "<p class='sec-desc'>A job is a saved recipe: which actor, which creators, and when. "
        "<a href='#new-job'>Create a new job below</a>. "
        "Times are Riyadh time. The scheduler checks every minute.</p>"
        "<table><thead><tr><th>Job</th><th>Runs</th><th>Last started</th><th>State</th><th></th></tr></thead><tbody>"
        + jobs_body + "</tbody></table>"
        "<div class='card' id='new-job' style='margin-top:14px'><div class='hd'><h2>+ New job</h2></div>"
        "<label>Start from</label><select id='preset' form='newjob'>" + presets + "</select>"
        + _job_form(None).replace("<form ", "<form id='newjob' ", 1) + "</div></section>" + preset_js)

    runs = []
    flt_status, flt_job = query.get("status", ""), query.get("job", "")
    for r in apify.list_runs(50, flt_status, flt_job):
        cls = {"SUCCEEDED": "live", "RUNNING": "warn", "QUEUED": "warn"}.get(r["status"], "dead")
        ctl = ""
        if r["status"] in ("RUNNING", "QUEUED"):
            ctl = (" <form method='post' action='" + u("/apis/run/abort") + "' class='inline'><input type='hidden' name='id' value='%d'>"
                   "<button class='btn small ghost'>Stop</button></form>" % r["id"])
        elif r["status"] in ("FAILED", "REFUSED") and r["handle_map"]:
            ctl = (" <form method='post' action='" + u("/apis/run/retry") + "' class='inline'><input type='hidden' name='id' value='%d'>"
                   "<button class='btn small'>Retry</button></form>" % r["id"])
        view = (" <a href='" + u("/apis/run?id=%d" % r["id"]) + "'>" + ("View" if r["results"] else "Details") + "</a>") if (r["results"] or r["apify_run"]) else ""
        runs.append(
            "<tr><td>" + e(r["job_name"] or "—") + "<br><span class='muted' style='font-size:12px'>" + e(r["trigger"]) + "</span></td>"
            "<td><span class='pill " + cls + "'>" + e(r["status"].lower()) + "</span></td>"
            "<td>" + str(r["handles"]) + "</td><td>" + str(r["results"]) + "</td><td>" + str(r["saved"]) + "</td>"
            "<td>$%.2f</td><td class='muted'>" % r["cost"] + V.ts(r["started_at"]) + "</td>"
            "<td class='muted' style='font-size:12px'>" + e((r["message"] or "")[:200]) + view + ctl + "</td></tr>")
    runs_body = "".join(runs) or "<tr><td colspan='8' class='muted'>No runs yet.</td></tr>"
    names = sorted({j["name"] for j in apify.list_jobs()} | {r["job_name"] for r in apify.list_runs(200) if r["job_name"]})
    filt = ("<form method='get' action='" + u("/apis") + "' class='row' style='margin-bottom:10px'><input type='hidden' name='tab' value='apify'>"
            "<div><label>Status</label><select name='status'><option value=''>All</option>"
            + "".join("<option value='%s'%s>%s</option>" % (s, " selected" if flt_status.upper() == s else "", s.lower())
                      for s in ("SUCCEEDED", "RUNNING", "QUEUED", "FAILED", "REFUSED")) + "</select></div>"
            "<div><label>Job</label><select name='job'><option value=''>All</option>"
            + "".join("<option value='%s'%s>%s</option>" % (e(n), " selected" if flt_job == n else "", e(n)) for n in names)
            + "</select></div><div style='align-self:end'><button class='btn small'>Filter</button> "
            "<a class='btn small ghost' href='" + u("/apis/runs.csv") + "'>Export CSV</a></div></form>")
    runs_card = (
        "<section class='card'><div class='hd'><h2>Runs</h2><span class='muted'>"
        + (str(n_snap) + " snapshots for " + str(n_creators) + " creators, last " + V.ago(last) if n_snap else "No snapshots saved yet")
        + "</span></div>" + filt + "<table><thead><tr><th>Job</th><th>Status</th><th>Sent</th><th>Results</th><th>Saved</th>"
        "<th>Cost</th><th>Started</th><th></th></tr></thead><tbody>" + runs_body + "</tbody></table></section>")

    return health_card() + conn_card + limits + pack_card() + jobs + usage_card() + runs_card + activity_card()


# One entry per integration. A new service adds a tab here (label, one-line
# purpose, a function returning its tab body, one returning its status) and
# its own /apis/<key>/* routes; the page, tabs and overview need no change.
INTEGRATIONS = [
    {"key": "apify", "label": "Apify",
     "about": "Follower counts and posts for the creators, from Instagram, TikTok and Snapchat.",
     "body": apify_tab, "status": lambda: ("connected", True) if apify.token_hint() else ("not connected", False)},
]


def overview_tab():
    cards = []
    for i in INTEGRATIONS:
        text, ok = i["status"]()
        cards.append(
            "<section class='card'><div class='hd'><h2>" + e(i["label"]) + "</h2><span class='pill "
            + ("live" if ok else "dead") + "'>" + e(text) + "</span></div><p class='sec-desc'>" + e(i["about"])
            + "</p><a class='btn small' href='" + u("/apis?tab=" + i["key"]) + "'>Open</a></section>")
    return ("<div class='home-grid'>" + "".join(cards) + "</div>"
            "<p class='muted'>More services can be added here as tabs, each with its own connection and settings.</p>")


def apis_page(error=None, message=None, tab="overview", q="", query=None):
    keys = {i["key"]: i for i in INTEGRATIONS}
    tab = tab if (tab in keys or tab == "data") else "overview"
    tabs = [(u("/apis?tab=overview"), "Overview", None, tab == "overview")]
    tabs += [(u("/apis?tab=" + i["key"]), i["label"], None, tab == i["key"]) for i in INTEGRATIONS]
    tabs.append((u("/apis?tab=data"), "Collected data", None, tab == "data"))
    inner = (apify_tab(query) if tab == "apify" else keys[tab]["body"]()) if tab in keys else (data_tab(q) if tab == "data" else overview_tab())
    body = (ui.header("APIs", "Connect outside services and run them from here.",
                      crumbs=[("System", None), ("APIs", None)], tabs=tabs)
            + V._notes(error, message) + inner)
    return V.page("APIs", body, "/apis")


def run_page(rid):
    """What one run brought back, exactly as the actor returned it."""
    run = apify.get_run(rid)
    if run is None:
        return V.page("APIs", ui.header("APIs", "That run does not exist.") , "/apis")
    rows = []
    for r in apify.run_results(rid):
        who = (r["name"] + " · " if r["name"] else "") + (r["code"] or "not matched to a creator")
        try:
            pretty = json.dumps(json.loads(r["data"]), indent=2, ensure_ascii=False)
        except ValueError:
            pretty = r["data"]
        rows.append("<details class='card'><summary class='hd'><h2>" + e(who) + "</h2><span class='muted'>"
                    + e(r["actor"] or "") + "</span></summary><pre style='white-space:pre-wrap;font-size:12px;"
                    "max-height:480px;overflow:auto'>" + e(pretty) + "</pre></details>")
    body = (ui.header("Run results", e(run["job_name"] or "") + " · " + V.ts(run["started_at"]) + " · $%.2f" % run["cost"],
                      crumbs=[("APIs", u("/apis?tab=apify")), ("Run %d" % rid, None)],
                      actions="<a class='btn small' href='" + u("/apis/run.json?id=%d" % rid) + "'>Download JSON</a>")
            + ("<div class='" + ("err" if run["status"] in ("FAILED", "REFUSED") else "note") + "'><strong>" + e(run["status"].lower())
               + "</strong> " + e(run["message"] or "") + (" <a href='https://console.apify.com/actors/runs/" + e(run["apify_run"])
               + "' target='_blank' rel='noopener'>Open in Apify</a>" if run["apify_run"] else "") + "</div>" if (run["message"] or run["apify_run"]) else "")
            + ("".join(rows) or "<p class='muted'>No results were kept for this run.</p>"))
    return V.page("APIs", body, "/apis")
