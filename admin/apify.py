"""Apify connection: the token, saved jobs, runs and the profile numbers they bring back.

Everything that talks to Apify happens here, on the server. The token is kept in
admin/.apify-token (mode 600, never in git) and is never sent to a browser: the
Integrations page only ever shows its last four characters.

A job is a saved recipe: which actor to run, which creators' handles to feed it,
and when. A scheduler thread starts due jobs, follows their runs and, for profile
jobs, stores follower counts as dated snapshots. Nothing here edits a creator.
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import db

TOKEN_FILE = Path(__file__).resolve().parent / ".apify-token"
API = "https://api.apify.com/v2"
RIYADH = 3 * 3600                      # Saudi time has no daylight saving
HARD_MAX_HANDLES = 1000                # one run never takes more than this
DEFAULT_BUDGET = 5.0                   # USD per month, ours; Apify has its own cap
DEFAULT_RUN_CAP = 1.0                  # USD per run, sent to Apify as maxTotalChargeUsd

# Starting points. The actor id and the input stay editable on every job, so a
# different actor needs no code change. Only "profiles" jobs are read back into
# snapshots; any other kind is run and recorded, and its results stay in Apify.
PRESETS = {
    "ig_profiles": {"label": "Instagram · profile numbers", "platform": "Instagram", "kind": "profiles",
                    "actor": "apify/instagram-profile-scraper", "est": 0.003,
                    "input": '{"usernames": "{{handles}}", "includeAboutSection": false}'},
    "ig_fakes": {"label": "Instagram · fake-follower score (cheap)", "platform": "Instagram", "kind": "analysis",
                 "actor": "charlestechy/instagram-influencer-deep-analyzer", "est": 0.001,
                 "input": '{"usernames": "{{handles}}"}'},
    "ig_audience": {"label": "Instagram · audience demographics (one run per creator)", "platform": "Instagram",
                    "kind": "analysis", "actor": "hypebridge/influencer-evaluation-agent-instagram-tiktok", "est": 0.15,
                    "input": '{"influencerHandle": "{{handle}}", "platform": "instagram"}'},
    "ig_audit": {"label": "Instagram · follower audit (about $1 per creator)", "platform": "Instagram",
                 "kind": "analysis", "actor": "seemuapps/instagram-fake-follower-auditor", "est": 0.99,
                 "input": '{"username": "{{handle}}", "sampleSize": 200}'},
    "tt_profiles": {"label": "TikTok · profile numbers", "platform": "TikTok", "kind": "profiles",
                    "actor": "khadinakbar/tiktok-profile-scraper", "est": 0.002,
                    "input": '{"profiles": "{{handles}}", "maxResults": "{{count}}"}'},
    "tt_analytics": {"label": "TikTok · engagement analytics", "platform": "TikTok", "kind": "analysis",
                     "actor": "maximedupre/tiktok-creator-analytics", "est": 0.001,
                     "input": '{"target": "handles", "creatorHandles": "{{handles}}", "postSampleSize": 20}'},
    "tt_audience": {"label": "TikTok · audience demographics (one run per creator)", "platform": "TikTok",
                    "kind": "analysis", "actor": "hypebridge/influencer-evaluation-agent-instagram-tiktok", "est": 0.15,
                    "input": '{"influencerHandle": "{{handle}}", "platform": "tiktok"}'},
    "custom": {"label": "Another actor", "platform": "", "kind": "other", "actor": "", "est": 0.01,
               "input": '{"profiles": "{{handles}}"}'},
}

MAX_PARALLEL = 5                       # per-creator runs in flight at once

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_jobs (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  actor       TEXT NOT NULL,
  kind        TEXT NOT NULL DEFAULT 'profiles',   -- profiles | analysis | posts | other
  platform    TEXT NOT NULL DEFAULT 'Instagram',
  source      TEXT NOT NULL DEFAULT 'all',        -- all | selection:<id> | campaign:<id>
  input       TEXT NOT NULL,                      -- JSON; "{{handles}}" is replaced
  max_handles INTEGER NOT NULL DEFAULT 100,
  schedule    TEXT NOT NULL DEFAULT 'manual',     -- manual | daily | weekly
  at_time     TEXT NOT NULL DEFAULT '03:00',      -- Riyadh time
  weekday     INTEGER NOT NULL DEFAULT 0,         -- 0 = Monday
  enabled     INTEGER NOT NULL DEFAULT 1,
  last_started INTEGER,
  created_at  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS api_runs (
  id          INTEGER PRIMARY KEY,
  job_id      INTEGER REFERENCES api_jobs(id) ON DELETE SET NULL,
  job_name    TEXT,
  trigger     TEXT NOT NULL,                      -- manual | schedule
  apify_run   TEXT,
  dataset     TEXT,
  status      TEXT NOT NULL,                      -- QUEUED | RUNNING | SUCCEEDED | FAILED | REFUSED
  handles     INTEGER NOT NULL DEFAULT 0,
  results     INTEGER NOT NULL DEFAULT 0,
  saved       INTEGER NOT NULL DEFAULT 0,
  cost        REAL NOT NULL DEFAULT 0,
  handle_map  TEXT,                               -- JSON {handle: creator code}
  message     TEXT,
  started_at  INTEGER NOT NULL,
  finished_at INTEGER
);
CREATE TABLE IF NOT EXISTS profile_snapshots (
  id        INTEGER PRIMARY KEY,
  code      TEXT NOT NULL,                        -- creators.code
  platform  TEXT NOT NULL,
  handle    TEXT NOT NULL,
  at        INTEGER NOT NULL,
  followers INTEGER,
  following INTEGER,
  posts     INTEGER,
  verified  INTEGER,
  run_id    INTEGER
);
CREATE TABLE IF NOT EXISTS profile_raw (
  id      INTEGER PRIMARY KEY,
  run_id  INTEGER NOT NULL,
  code    TEXT,                                   -- creators.code, empty when unmatched
  platform TEXT,
  actor   TEXT,
  at      INTEGER NOT NULL,
  data    TEXT NOT NULL                           -- the actor's own result, as returned
);
CREATE INDEX IF NOT EXISTS profile_raw_run ON profile_raw(run_id);
CREATE INDEX IF NOT EXISTS profile_raw_code ON profile_raw(code, at DESC);
CREATE INDEX IF NOT EXISTS profile_snapshots_code ON profile_snapshots(code, at DESC);
"""


class ApifyError(Exception):
    pass


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(api_jobs)")}
        if "est_each" not in cols:
            conn.execute("ALTER TABLE api_jobs ADD COLUMN est_each REAL NOT NULL DEFAULT 0.01")


# -------------------------------------------------------------------- token --

def get_token():
    try:
        return TOKEN_FILE.read_text().strip() or None
    except OSError:
        return None


def save_token(token):
    token = (token or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]{20,200}", token):
        raise ApifyError("That does not look like an Apify token. Copy it again from "
                         "Apify → Settings → Integrations.")
    old = os.umask(0o077)
    try:
        TOKEN_FILE.write_text(token)
        os.chmod(TOKEN_FILE, 0o600)
    finally:
        os.umask(old)


def clear_token():
    try:
        TOKEN_FILE.unlink()
    except OSError:
        pass


def token_hint():
    t = get_token()
    return ("••••" + t[-4:]) if t else None


# --------------------------------------------------------------------- http --

def call(method, path, body=None, params=None, timeout=30):
    """One Apify API call. The token goes in a header, never in a URL, and no
    error message ever contains it."""
    token = get_token()
    if not token:
        raise ApifyError("No Apify token is saved yet.")
    url = API + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as ex:
        detail = ""
        try:
            detail = json.loads(ex.read().decode()).get("error", {}).get("message", "")
        except Exception:
            pass
        raise ApifyError("Apify answered %s. %s" % (ex.code, detail or "Check the token and the actor name."))
    except (urllib.error.URLError, OSError) as ex:
        raise ApifyError("Could not reach Apify: " + str(getattr(ex, "reason", ex)))
    return json.loads(raw.decode()) if raw else {}


def test_connection():
    me = call("GET", "/users/me").get("data", {})
    out = {"username": me.get("username"), "plan": (me.get("plan") or {}).get("id") or "",
           "email": me.get("email") or ""}
    try:
        lim = call("GET", "/users/me/limits").get("data", {})
        out["cap"] = (lim.get("limits") or {}).get("maxMonthlyUsageUsd")
        out["used"] = (lim.get("current") or {}).get("monthlyUsageUsd")
    except ApifyError:
        pass
    return out


# ----------------------------------------------------------------- settings --

def budget():
    try:
        return float(db.setting("apify_budget_usd", DEFAULT_BUDGET))
    except (TypeError, ValueError):
        return DEFAULT_BUDGET


def run_cap():
    try:
        return float(db.setting("apify_run_cap_usd", DEFAULT_RUN_CAP))
    except (TypeError, ValueError):
        return DEFAULT_RUN_CAP


def month_start(t=None):
    t = time.gmtime(t or time.time())
    return int(time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, 0))) - time.timezone


def spent_this_month():
    with db.connect() as conn:
        return conn.execute("SELECT COALESCE(SUM(cost),0) c FROM api_runs WHERE started_at >= ?",
                            (month_start(),)).fetchone()["c"]


# ------------------------------------------------------------------ handles --

_URL = [("Instagram", re.compile(r"instagram\.com/([A-Za-z0-9._]+)", re.I)),
        ("TikTok", re.compile(r"tiktok\.com/@([A-Za-z0-9._]+)", re.I)),
        ("Snapchat", re.compile(r"snapchat\.com/(?:add/)?([A-Za-z0-9._\-]+)", re.I))]
_NOT_HANDLES = {"p", "reel", "reels", "explore", "stories", "accounts", "tv"}


def _clean(h):
    h = (h or "").strip().lstrip("@").strip("/")
    return h if re.fullmatch(r"[A-Za-z0-9._\-]{1,60}", h) and h.lower() not in _NOT_HANDLES else None


def creator_handles(c):
    """{platform: handle} for one creator row, from its profile links and its
    main handle."""
    out = {}
    try:
        profiles = json.loads(c["profiles"] or "[]")
    except ValueError:
        profiles = []
    for p in profiles:
        url = (p or {}).get("url") or ""
        for plat, rx in _URL:
            m = rx.search(url)
            if m and _clean(m.group(1)):
                out.setdefault(plat, _clean(m.group(1)))
    if c["handle"] and c["platform"] and c["platform"] not in out and _clean(c["handle"]):
        out[c["platform"]] = _clean(c["handle"])
    return out


def build_handles(job):
    """[(creator code, handle)] for a job, in order, no duplicates, capped."""
    plat = job["platform"]
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM creators WHERE active = 1 ORDER BY sort, code").fetchall()
        allowed = None
        src = job["source"] or "all"
        if src.startswith("selection:") and src[10:].isdigit():
            r = conn.execute("SELECT codes FROM selections WHERE id = ?", (int(src[10:]),)).fetchone()
            allowed = set(json.loads(r["codes"] or "[]")) if r else set()
        elif src == "sample20":
            have = {r["code"] for r in conn.execute("SELECT code FROM creator_analysis")}
            ranked = sorted(rows, key=lambda c: (c["code"] not in have, c["code"]))
            usable = [c["code"] for c in ranked if creator_handles(c).get(plat)]
            allowed = set(usable[:20])
        elif src == "noanalysis":
            have = {r["code"] for r in conn.execute("SELECT code FROM creator_analysis")}
            allowed = {c["code"] for c in rows} - have
        elif src == "nosnap":
            have = {r["code"] for r in conn.execute(
                "SELECT DISTINCT code FROM profile_snapshots WHERE platform = ?", (plat,))}
            allowed = {c["code"] for c in rows} - have
        elif src.startswith("campaign:") and src[9:].isdigit():
            allowed = {r["code"] for r in conn.execute(
                "SELECT code FROM campaign_creators WHERE campaign_id = ?", (int(src[9:]),))}
    out, seen = [], set()
    for c in rows:
        if allowed is not None and c["code"] not in allowed:
            continue
        h = creator_handles(c).get(plat) if plat else None
        if h and h.lower() not in seen:
            seen.add(h.lower())
            out.append((c["code"], h))
    cap = max(1, min(int(job["max_handles"] or 100), HARD_MAX_HANDLES))
    return out[:cap]


# --------------------------------------------------------------------- jobs --

def list_jobs():
    with db.connect() as conn:
        return conn.execute("SELECT * FROM api_jobs ORDER BY id DESC").fetchall()


def get_job(jid):
    with db.connect() as conn:
        return conn.execute("SELECT * FROM api_jobs WHERE id = ?", (jid,)).fetchone()


def save_job(f):
    actor = (f.get("actor") or "").strip().replace("~", "/")
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+", actor):
        raise ApifyError("The actor must look like username/actor-name, as shown on its Apify page.")
    tmpl = (f.get("input") or "").strip()
    try:
        json.loads(tmpl)
    except ValueError:
        raise ApifyError("The input is not valid JSON.")
    if "{{handles}}" not in tmpl and "{{handle}}" not in tmpl:
        raise ApifyError("The input must contain {{handles}} (all in one run) or {{handle}} "
                         "(one run per creator) where the handles go.")
    sched = f.get("schedule") if f.get("schedule") in ("manual", "daily", "weekly") else "manual"
    at = f.get("at_time") if re.fullmatch(r"\d{2}:\d{2}", f.get("at_time") or "") else "03:00"
    wd = int(f["weekday"]) if (f.get("weekday") or "").isdigit() and int(f["weekday"]) < 7 else 0
    mh = int(f["max_handles"]) if (f.get("max_handles") or "").isdigit() else 100
    try:
        est = max(0.0, float(f.get("est_each") or 0.01))
    except ValueError:
        est = 0.01
    vals = ((f.get("name") or "").strip() or "Untitled job", actor,
            f.get("kind") if f.get("kind") in ("profiles", "analysis", "posts", "other") else "other",
            (f.get("platform") or "").strip(), (f.get("source") or "all").strip(),
            tmpl, max(1, min(mh, HARD_MAX_HANDLES)), sched, at, wd, est)
    with db.connect() as conn:
        if (f.get("id") or "").isdigit():
            conn.execute("UPDATE api_jobs SET name=?,actor=?,kind=?,platform=?,source=?,input=?,"
                         "max_handles=?,schedule=?,at_time=?,weekday=?,est_each=? WHERE id=?",
                         vals + (int(f["id"]),))
            return int(f["id"])
        cur = conn.execute("INSERT INTO api_jobs (name,actor,kind,platform,source,input,max_handles,"
                           "schedule,at_time,weekday,est_each,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                           vals + (db.now(),))
        return cur.lastrowid


def delete_job(jid):
    with db.connect() as conn:
        conn.execute("DELETE FROM api_jobs WHERE id = ?", (jid,))


def toggle_job(jid):
    with db.connect() as conn:
        conn.execute("UPDATE api_jobs SET enabled = 1 - enabled WHERE id = ?", (jid,))


# --------------------------------------------------------------------- runs --

def list_runs(limit=25):
    with db.connect() as conn:
        return conn.execute("SELECT * FROM api_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def _refuse(job, trigger, why):
    with db.connect() as conn:
        conn.execute("INSERT INTO api_runs (job_id, job_name, trigger, status, message, started_at, finished_at) "
                     "VALUES (?,?,?,?,?,?,?)", (job["id"], job["name"], trigger, "REFUSED", why, db.now(), db.now()))
    return why


def render_input(tmpl, handles):
    """The job's JSON with the handles put in. "{{handles}}" becomes the list,
    "{{handle}}" the first one, "{{count}}" how many there are."""
    t = tmpl.replace('"{{handles}}"', json.dumps(handles))
    t = t.replace('"{{handle}}"', json.dumps(handles[0] if handles else ""))
    t = t.replace('"{{count}}"', str(max(1, len(handles))))
    return json.loads(t)


def start_job(jid, trigger="manual"):
    """Start a job. A job whose input uses {{handles}} is one Apify run for all
    of them; one that uses {{handle}} is one run per creator, queued and fed to
    Apify a few at a time. Returns (ok, message). Refuses, and records why,
    when the month's budget would be passed, nothing matches or no token is saved."""
    job = get_job(jid)
    if job is None:
        return False, "That job no longer exists."
    if not get_token():
        return False, "Save an Apify token first."
    with db.connect() as conn:
        busy = conn.execute("SELECT 1 FROM api_runs WHERE job_id = ? AND status IN ('RUNNING','QUEUED')",
                            (jid,)).fetchone()
    if busy:
        return False, "This job is already running."
    pairs = build_handles(job)
    if not pairs:
        return False, _refuse(job, trigger, "No creator has a %s handle for this source." % (job["platform"] or "matching"))
    est = len(pairs) * float(job["est_each"] or 0)
    if spent_this_month() + est > budget():
        return False, _refuse(job, trigger, "About $%.2f for %d creators would pass the monthly budget of $%.2f "
                                            "(already $%.2f this month). Raise the budget or run fewer."
                              % (est, len(pairs), budget(), spent_this_month()))
    if "{{handle}}" in job["input"]:
        with db.connect() as conn:
            for code, h in pairs:
                conn.execute("INSERT INTO api_runs (job_id, job_name, trigger, status, handles, handle_map, started_at) "
                             "VALUES (?,?,?,?,?,?,?)", (jid, job["name"], trigger, "QUEUED", 1,
                                                       json.dumps({h.lower(): code}), db.now()))
            conn.execute("UPDATE api_jobs SET last_started = ? WHERE id = ?", (db.now(), jid))
        pump()
        return True, "Queued %d runs, about $%.2f." % (len(pairs), est)
    handles = [h for _c, h in pairs]
    try:
        res = _launch(job, handles)
    except ApifyError as ex:
        return False, _refuse(job, trigger, str(ex))
    with db.connect() as conn:
        conn.execute("INSERT INTO api_runs (job_id, job_name, trigger, apify_run, dataset, status, handles, "
                     "handle_map, started_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (jid, job["name"], trigger, res.get("id"), res.get("defaultDatasetId"), "RUNNING",
                      len(handles), json.dumps({h.lower(): c for c, h in pairs}), db.now()))
        conn.execute("UPDATE api_jobs SET last_started = ? WHERE id = ?", (db.now(), jid))
    return True, "Started with %d handles, about $%.2f." % (len(handles), est)


def _launch(job, handles):
    return call("POST", "/acts/" + job["actor"].replace("/", "~") + "/runs", render_input(job["input"], handles),
                params={"maxTotalChargeUsd": "%.2f" % run_cap()})["data"]


def pump():
    """Start queued per-creator runs, up to MAX_PARALLEL in flight."""
    with db.connect() as conn:
        running = conn.execute("SELECT COUNT(*) c FROM api_runs WHERE status = 'RUNNING'").fetchone()["c"]
        queued = conn.execute("SELECT * FROM api_runs WHERE status = 'QUEUED' ORDER BY id").fetchall()
    for r in queued:
        if running >= MAX_PARALLEL:
            break
        job = get_job(r["job_id"]) if r["job_id"] else None
        if job is None:
            _finish(r, "FAILED", 0, 0, 0.0, "The job was deleted before this run started.")
            continue
        if spent_this_month() >= budget():
            _finish(r, "REFUSED", 0, 0, 0.0, "Monthly budget of $%.2f reached." % budget())
            continue
        try:
            res = _launch(job, list(json.loads(r["handle_map"]).keys()))
        except ApifyError as ex:
            _finish(r, "FAILED", 0, 0, 0.0, str(ex))
            continue
        with db.connect() as conn:
            conn.execute("UPDATE api_runs SET status='RUNNING', apify_run=?, dataset=?, started_at=? WHERE id=?",
                         (res.get("id"), res.get("defaultDatasetId"), db.now(), r["id"]))
        running += 1


def _num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


_HANDLE_KEYS = ("username", "uniqueId", "handle", "influencerHandle", "userName", "profileName", "nickname_id")


def _match(item, hmap):
    """Which handle in this run an item belongs to."""
    for k in _HANDLE_KEYS:
        v = item.get(k)
        if isinstance(v, str) and v.lstrip("@").lower() in hmap:
            return v.lstrip("@").lower()
    am = item.get("authorMeta")
    if isinstance(am, dict) and str(am.get("name", "")).lower() in hmap:
        return str(am["name"]).lower()
    for v in item.values():                      # a profile link or a nested name
        if isinstance(v, str):
            tail = v.rstrip("/").rsplit("/", 1)[-1].lstrip("@").lower()
            if tail in hmap:
                return tail
    if len(hmap) == 1:                           # a one-creator run: it is theirs
        return next(iter(hmap))
    return None


def _compact(item):
    """The result as returned, except fields over 2 KB (post lists, related
    accounts) are replaced by a note, so a large run does not fill the database."""
    out = {}
    for k, v in item.items():
        size = len(json.dumps(v, default=str))
        out[k] = v if size <= 2000 else "[omitted: %d bytes]" % size
    return out


def ingest(run, job, items):
    """Keep every result as the actor returned it, and, for profile jobs, the
    follower number as a dated snapshot."""
    hmap = json.loads(run["handle_map"] or "{}")
    plat = job["platform"] if job else ""
    saved = 0
    with db.connect() as conn:
        for it in items:
            if not isinstance(it, dict):
                continue
            h = _match(it, hmap)
            code = hmap.get(h) if h else None
            small = it if len(json.dumps(it, default=str)) <= 20000 else _compact(it)
            conn.execute("INSERT INTO profile_raw (run_id, code, platform, actor, at, data) VALUES (?,?,?,?,?,?)",
                         (run["id"], code or "", plat, job["actor"] if job else "", db.now(),
                          json.dumps(small, default=str)))
            if job and job["kind"] == "profiles" and code:
                f = next((x for x in (_num(it.get(k)) for k in (
                    "followersCount", "followers", "followerCount", "subscriberCount",
                    "subscribersCount", "subscribers")) if x is not None), None)
                if f is None and isinstance(it.get("authorMeta"), dict):
                    f = _num(it["authorMeta"].get("fans"))
                if f is not None:
                    conn.execute("INSERT INTO profile_snapshots (code,platform,handle,at,followers,following,posts,verified,run_id) "
                                 "VALUES (?,?,?,?,?,?,?,?,?)",
                                 (code, plat, h, db.now(), f, _num(it.get("followsCount", it.get("following"))),
                                  _num(it.get("postsCount", it.get("posts"))), 1 if it.get("verified") else 0, run["id"]))
                    saved += 1
    return saved


def refresh_run(run):
    """Ask Apify how one run is going and finish it off when it is done."""
    try:
        d = call("GET", "/actor-runs/" + run["apify_run"])["data"]
    except ApifyError as ex:
        if db.now() - run["started_at"] > 6 * 3600:
            _finish(run, "FAILED", 0, 0, 0.0, "Lost track of this run: " + str(ex))
        return
    st = d.get("status")
    cost = float(d.get("usageTotalUsd") or 0)
    if st in ("READY", "RUNNING"):
        return
    if st != "SUCCEEDED":
        _finish(run, "FAILED", 0, 0, cost, "Apify ended the run as " + str(st) + ".")
        return
    items, saved, note = [], 0, None
    try:
        items = call("GET", "/datasets/%s/items" % run["dataset"],
                     params={"format": "json", "clean": "1", "limit": "5000"}, timeout=60)
        items = items if isinstance(items, list) else []
        job = get_job(run["job_id"]) if run["job_id"] else None
        saved = ingest(run, job, items)
        if not items:
            note = "The run finished but returned no results."
        elif job and job["kind"] == "profiles" and not saved:
            note = "Results kept, but no follower count was recognised in them."
    except ApifyError as ex:
        note = "Run finished but the results could not be read: " + str(ex)
    _finish(run, "SUCCEEDED", len(items), saved, cost, note)


def _finish(run, status, results, saved, cost, message):
    with db.connect() as conn:
        conn.execute("UPDATE api_runs SET status=?, results=?, saved=?, cost=?, message=?, finished_at=? WHERE id=?",
                     (status, results, saved, cost, message, db.now(), run["id"]))


def refresh_all():
    with db.connect() as conn:
        live = conn.execute("SELECT * FROM api_runs WHERE status = 'RUNNING' AND apify_run IS NOT NULL").fetchall()
    for r in live:
        refresh_run(r)
    pump()
    return len(live)


def get_run(rid):
    with db.connect() as conn:
        return conn.execute("SELECT * FROM api_runs WHERE id = ?", (rid,)).fetchone()


def run_results(rid):
    with db.connect() as conn:
        return conn.execute("SELECT r.*, c.name FROM profile_raw r LEFT JOIN creators c ON c.code = r.code "
                            "WHERE r.run_id = ? ORDER BY r.id", (rid,)).fetchall()


# ---------------------------------------------------------------- scheduler --

def _due(job, t):
    if not job["enabled"] or job["schedule"] == "manual":
        return False
    local = time.gmtime(t + RIYADH)
    hh, mm = (int(x) for x in job["at_time"].split(":"))
    if job["schedule"] == "weekly" and local.tm_wday != job["weekday"]:
        return False
    slot = t - (local.tm_hour * 3600 + local.tm_min * 60 + local.tm_sec) + hh * 3600 + mm * 60
    return t >= slot and (job["last_started"] or 0) < slot


def tick(t=None):
    t = t or db.now()
    if not get_token():
        return
    refresh_all()
    for job in list_jobs():
        if _due(job, t):
            start_job(job["id"], "schedule")


def _loop():
    while True:
        try:
            tick()
        except Exception as ex:            # a bad tick must never stop the scheduler
            print("apify scheduler:", type(ex).__name__, ex, flush=True)
        time.sleep(60)


def start_scheduler():
    init()
    threading.Thread(target=_loop, name="apify-scheduler", daemon=True).start()


# --------------------------------------------------------------------- data --

def snapshot_summary():
    with db.connect() as conn:
        r = conn.execute("SELECT COUNT(*) n, COUNT(DISTINCT code) c, MAX(at) last FROM profile_snapshots").fetchone()
    return r["n"], r["c"], r["last"]
