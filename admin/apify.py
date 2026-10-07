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
    "ig_profiles": {"label": "Instagram profiles", "platform": "Instagram", "kind": "profiles",
                    "actor": "apify/instagram-profile-scraper",
                    "input": '{"usernames": "{{handles}}"}'},
    "ig_posts": {"label": "Instagram posts", "platform": "Instagram", "kind": "posts",
                 "actor": "apify/instagram-post-scraper",
                 "input": '{"username": "{{handles}}", "resultsLimit": 5}'},
    "tt_profiles": {"label": "TikTok profiles (check input on the actor page)", "platform": "TikTok",
                    "kind": "profiles", "actor": "khadinakbar/tiktok-profile-scraper",
                    "input": '{"usernames": "{{handles}}"}'},
    "sc_profiles": {"label": "Snapchat profiles (check input on the actor page)", "platform": "Snapchat",
                    "kind": "profiles", "actor": "scraper-engine/snapchat-profile-scraper",
                    "input": '{"usernames": "{{handles}}"}'},
    "custom": {"label": "Another actor", "platform": "", "kind": "other",
               "actor": "", "input": '{"profiles": "{{handles}}"}'},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_jobs (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  actor       TEXT NOT NULL,
  kind        TEXT NOT NULL DEFAULT 'profiles',   -- profiles | posts | other
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
  status      TEXT NOT NULL,                      -- RUNNING | SUCCEEDED | FAILED | REFUSED
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
CREATE INDEX IF NOT EXISTS profile_snapshots_code ON profile_snapshots(code, at DESC);
"""


class ApifyError(Exception):
    pass


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)


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
    if "{{handles}}" not in tmpl:
        raise ApifyError("The input must contain {{handles}} where the creators' handles go.")
    sched = f.get("schedule") if f.get("schedule") in ("manual", "daily", "weekly") else "manual"
    at = f.get("at_time") if re.fullmatch(r"\d{2}:\d{2}", f.get("at_time") or "") else "03:00"
    wd = int(f["weekday"]) if (f.get("weekday") or "").isdigit() and int(f["weekday"]) < 7 else 0
    mh = int(f["max_handles"]) if (f.get("max_handles") or "").isdigit() else 100
    vals = ((f.get("name") or "").strip() or "Untitled job", actor,
            f.get("kind") if f.get("kind") in ("profiles", "posts", "other") else "other",
            (f.get("platform") or "").strip(), (f.get("source") or "all").strip(),
            tmpl, max(1, min(mh, HARD_MAX_HANDLES)), sched, at, wd)
    with db.connect() as conn:
        if (f.get("id") or "").isdigit():
            conn.execute("UPDATE api_jobs SET name=?,actor=?,kind=?,platform=?,source=?,input=?,"
                         "max_handles=?,schedule=?,at_time=?,weekday=? WHERE id=?",
                         vals + (int(f["id"]),))
            return int(f["id"])
        cur = conn.execute("INSERT INTO api_jobs (name,actor,kind,platform,source,input,max_handles,"
                           "schedule,at_time,weekday,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
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


def start_job(jid, trigger="manual"):
    """Start one run. Returns (ok, message). Refuses, and records why, when the
    month's budget is spent, there is nothing to send or the token is missing."""
    job = get_job(jid)
    if job is None:
        return False, "That job no longer exists."
    if not get_token():
        return False, "Save an Apify token first."
    with db.connect() as conn:
        busy = conn.execute("SELECT 1 FROM api_runs WHERE job_id = ? AND status = 'RUNNING'", (jid,)).fetchone()
    if busy:
        return False, "This job is already running."
    if spent_this_month() >= budget():
        return False, _refuse(job, trigger, "Monthly budget of $%.2f reached." % budget())
    pairs = build_handles(job)
    if not pairs:
        return False, _refuse(job, trigger, "No creator has a %s handle for this source." % (job["platform"] or "matching"))
    handles = [h for _c, h in pairs]
    body = json.loads(job["input"].replace('"{{handles}}"', json.dumps(handles)))
    try:
        res = call("POST", "/acts/" + job["actor"].replace("/", "~") + "/runs", body,
                   params={"maxTotalChargeUsd": "%.2f" % run_cap()})["data"]
    except ApifyError as ex:
        return False, _refuse(job, trigger, str(ex))
    with db.connect() as conn:
        conn.execute("INSERT INTO api_runs (job_id, job_name, trigger, apify_run, dataset, status, handles, "
                     "handle_map, started_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (jid, job["name"], trigger, res.get("id"), res.get("defaultDatasetId"), "RUNNING",
                      len(handles), json.dumps({h.lower(): c for c, h in pairs}), db.now()))
        conn.execute("UPDATE api_jobs SET last_started = ? WHERE id = ?", (db.now(), jid))
    return True, "Started with %d handles." % len(handles)


def _num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def ingest_profiles(run, items):
    """Dated follower snapshots from a profile run. Field names differ a little
    between actors, so a few spellings are accepted."""
    hmap = json.loads(run["handle_map"] or "{}")
    job = get_job(run["job_id"]) if run["job_id"] else None
    plat = job["platform"] if job else ""
    saved = 0
    with db.connect() as conn:
        for it in items:
            h = str(it.get("username") or it.get("uniqueId") or it.get("handle")
                    or (it.get("authorMeta") or {}).get("name") or "").lstrip("@").lower()
            code = hmap.get(h)
            if not code:
                continue
            f = next((x for x in (_num(it.get(k)) for k in (
                "followersCount", "followers", "followerCount", "subscriberCount",
                "subscribersCount", "subscribers")) if x is not None), None)
            if f is None:
                continue
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
        if job and job["kind"] == "profiles":
            saved = ingest_profiles(run, items)
            if not saved:
                note = "Results came back but none matched a creator handle."
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
    return len(live)


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
