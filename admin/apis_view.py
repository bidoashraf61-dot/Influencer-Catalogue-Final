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
    opts = [("all", "All active creators")]
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
        + opt("posts", "Posts (kept in Apify)", g("kind")) + opt("other", "Other (kept in Apify)", g("kind"))
        + "</select></div></div><div class='row'>"
        + "<div><label>Actor</label><input name='actor' required value='" + e(g("actor")) + "' placeholder='username/actor-name'></div>"
        + "<div><label>Which creators</label><select name='source'>" + _sources(g("source", "all")) + "</select></div>"
        + "<div><label>Max handles per run</label><input name='max_handles' type='number' min='1' max='1000' value='"
        + str(g("max_handles", 100)) + "'></div></div>"
        + "<label>Input sent to the actor (JSON)</label><textarea name='input' rows='3' style='font-family:monospace;width:100%'>"
        + e(g("input", apify.PRESETS["ig_profiles"]["input"])) + "</textarea>"
        + "<div class='price-hint'><code>{{handles}}</code> is replaced with the creators' handles. "
          "Field names differ per actor, so copy them from the actor's Input tab in Apify.</div>"
        + "<div class='row'><div><label>Runs</label><select name='schedule'>"
        + opt("manual", "Only when I press Run", sched) + opt("daily", "Every day", sched)
        + opt("weekly", "Every week", sched) + "</select></div>"
        + "<div><label>At (Riyadh time)</label><input name='at_time' type='time' value='" + e(g("at_time", "03:00")) + "'></div>"
        + "<div><label>Weekly on</label><select name='weekday'>"
        + "".join(opt(str(i), d, str(g("weekday", 0))) for i, d in enumerate(DAYS)) + "</select></div></div>"
        + "<button class='btn lime'>Save job</button></form>")


def apify_tab():
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
            + post("/apis/job/toggle", "Pause" if j["enabled"] else "Resume", "small ghost")
            + post("/apis/job/delete", "Delete", "small danger ghost", "Delete this job? Its past runs stay in the list.")
            + "</td></tr><tr><td colspan='5'><details><summary class='btn small ghost'>Edit</summary>"
            + _job_form(j) + "</details></td></tr>")
    jobs_body = "".join(rows) or "<tr><td colspan='5'>" + ui.empty("flag", "No jobs yet", "Create one below.") + "</td></tr>"

    presets = "".join("<option value='%s'>%s</option>" % (k, e(p["label"])) for k, p in apify.PRESETS.items())
    preset_js = ("<script>(function(){var P=" + json.dumps({k: p for k, p in apify.PRESETS.items()}) + ";"
                 "var s=document.getElementById('preset');if(!s)return;s.addEventListener('change',function(){"
                 "var p=P[s.value],f=s.form;f.actor.value=p.actor;f.platform.value=p.platform;f.kind.value=p.kind;f.input.value=p.input;});})();</script>")
    jobs = (
        "<section class='card'><div class='hd'><h2>Jobs</h2>"
        "<form method='post' action='" + u("/apis/refresh") + "' class='inline'><button class='btn small ghost'>Check running jobs</button></form></div>"
        "<p class='sec-desc'>A job is a saved recipe: which actor, which creators, and when. "
        "Times are Riyadh time. The scheduler checks every minute.</p>"
        "<table><thead><tr><th>Job</th><th>Runs</th><th>Last started</th><th>State</th><th></th></tr></thead><tbody>"
        + jobs_body + "</tbody></table>"
        "<details class='card' style='margin-top:14px'><summary class='hd'><h2>New job</h2></summary>"
        "<label>Start from</label><select id='preset' form='newjob'>" + presets + "</select>"
        + _job_form(None).replace("<form ", "<form id='newjob' ", 1) + "</details></section>" + preset_js)

    runs = []
    for r in apify.list_runs():
        cls = {"SUCCEEDED": "live", "RUNNING": "warn"}.get(r["status"], "dead")
        runs.append(
            "<tr><td>" + e(r["job_name"] or "—") + "<br><span class='muted' style='font-size:12px'>" + e(r["trigger"]) + "</span></td>"
            "<td><span class='pill " + cls + "'>" + e(r["status"].lower()) + "</span></td>"
            "<td>" + str(r["handles"]) + "</td><td>" + str(r["results"]) + "</td><td>" + str(r["saved"]) + "</td>"
            "<td>$%.2f</td><td class='muted'>" % r["cost"] + V.ts(r["started_at"]) + "</td>"
            "<td class='muted' style='font-size:12px'>" + e((r["message"] or "")[:200]) + "</td></tr>")
    runs_body = "".join(runs) or "<tr><td colspan='8' class='muted'>No runs yet.</td></tr>"
    runs_card = (
        "<section class='card'><div class='hd'><h2>Runs</h2><span class='muted'>"
        + (str(n_snap) + " snapshots for " + str(n_creators) + " creators, last " + V.ago(last) if n_snap else "No snapshots saved yet")
        + "</span></div><table><thead><tr><th>Job</th><th>Status</th><th>Sent</th><th>Results</th><th>Saved</th>"
        "<th>Cost</th><th>Started</th><th></th></tr></thead><tbody>" + runs_body + "</tbody></table></section>")

    return conn_card + limits + jobs + runs_card


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


def apis_page(error=None, message=None, tab="overview"):
    keys = {i["key"]: i for i in INTEGRATIONS}
    tab = tab if tab in keys else "overview"
    tabs = [(u("/apis?tab=overview"), "Overview", None, tab == "overview")]
    tabs += [(u("/apis?tab=" + i["key"]), i["label"], None, tab == i["key"]) for i in INTEGRATIONS]
    inner = keys[tab]["body"]() if tab in keys else overview_tab()
    body = (ui.header("APIs", "Connect outside services and run them from here.",
                      crumbs=[("System", None), ("APIs", None)], tabs=tabs)
            + V._notes(error, message) + inner)
    return V.page("APIs", body, "/apis")
