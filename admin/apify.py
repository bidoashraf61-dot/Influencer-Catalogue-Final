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
RETRY_WAIT = 30 * 60                   # seconds before the scheduler tries a job that got no run again
DEFAULT_BUDGET = 5.0                   # USD per month, ours; Apify has its own cap
DEFAULT_RUN_CAP = 1.0                  # USD per run, sent to Apify as maxTotalChargeUsd

# Starting points. The actor id and the input stay editable on every job, so a
# different actor needs no code change. Only "profiles" jobs are read back into
# snapshots; any other kind is run and recorded, and its results stay in Apify.
PRESETS = {
    "ig_profiles": {"label": "Instagram · profile numbers", "platform": "Instagram", "kind": "profiles",
                    "actor": "apify/instagram-profile-scraper", "est": 0.003,
                    "input": '{"usernames": "{{handles}}", "includeAboutSection": false}'},
    "ig_audience": {"label": "Instagram · audience demographics (one run per creator)", "platform": "Instagram",
                    "kind": "analysis", "actor": "hypebridge/influencer-evaluation-agent-instagram-tiktok", "est": 1.70,
                    "input": '{"influencerHandle": "{{handle}}", "platform": "instagram"}'},
    "ig_audit": {"label": "Instagram · follower audit (about $2 per creator)", "platform": "Instagram",
                 "kind": "analysis", "actor": "seemuapps/instagram-fake-follower-auditor", "est": 2.00,
                 "input": '{"username": "{{handle}}", "sampleSize": 200}'},
    "tt_profiles": {"label": "TikTok · profile numbers", "platform": "TikTok", "kind": "profiles",
                    "actor": "khadinakbar/tiktok-profile-scraper", "est": 0.002,
                    "input": '{"profiles": "{{handles}}", "maxResults": "{{count}}"}'},
    "tt_analytics": {"label": "TikTok · engagement analytics", "platform": "TikTok", "kind": "analysis",
                     "actor": "maximedupre/tiktok-creator-analytics", "est": 0.0001,
                     "input": '{"target": "handles", "creatorHandles": "{{handles}}", "postSampleSize": 100}'},
    "tt_audience": {"label": "TikTok · audience demographics (one run per creator)", "platform": "TikTok",
                    "kind": "analysis", "actor": "hypebridge/influencer-evaluation-agent-instagram-tiktok", "est": 1.70,
                    "input": '{"influencerHandle": "{{handle}}", "platform": "tiktok"}'},
    "ig_reels": {"label": "Instagram · reel views (12 latest reels)", "platform": "Instagram", "kind": "posts",
                 "actor": "apify/instagram-reel-scraper", "est": 0.032,
                 "input": '{"username": "{{handles}}", "resultsLimit": 12, "skipPinnedPosts": true}'},
    # Campaign posts: one run for all of a campaign's links on one platform (source "campaign:<id>"),
    # numbers stored as a dated snapshot on each post. Each result is matched to its post by the id in its link.
    "post_ig": {"label": "Campaign posts · Instagram reels", "platform": "Instagram", "kind": "post_urls",
                "actor": "codenest/instagram-reels-scraper", "est": 0.004,
                "input": '{"reel_urls": "{{url_objs}}"}'},
    # A competitor's own recent posts, read for the creators in them (source "competitor:<id>", 2026-10-25).
    # The handles are profile URLs, so {{urls}} feeds directUrls; every result belongs to the one competitor
    # the job names, which is why this kind never goes through _match.
    "comp_ig": {"label": "Competitor · Instagram posts and the creators in them", "platform": "Instagram",
                "kind": "competitor", "actor": "apify/instagram-scraper", "est": 0.012,
                "input": '{"directUrls": "{{urls}}", "resultsType": "posts", "resultsLimit": 30, '
                         '"addParentData": false, "searchType": "user"}'},
    "post_tt": {"label": "Campaign posts · TikTok videos", "platform": "TikTok", "kind": "post_urls",
                "actor": "maximedupre/tiktok-audio-downloader", "est": 0.002,
                "input": '{"videoUrls": "{{url_objs}}"}'},
    "post_sc": {"label": "Campaign posts · Snapchat spotlights", "platform": "Snapchat", "kind": "post_urls",
                "actor": "tri_angle/snapchat-spotlight-scraper", "est": 0.003,
                "input": '{"spotlightUrls": "{{urls}}"}'},
    "post_fb": {"label": "Campaign posts · Facebook reels", "platform": "Facebook", "kind": "post_urls",
                "actor": "clappi/facebook-posts-reels-scraper", "est": 0.005,
                "input": '{"postUrls": "{{urls}}"}'},
    "post_yt": {"label": "Campaign posts · YouTube videos and shorts", "platform": "YouTube", "kind": "post_urls",
                "actor": "beyondops/youtube-metadata-scraper-pro-v2", "est": 0.001,
                "input": '{"videoUrls": "{{urls}}"}'},
    "custom": {"label": "Another actor", "platform": "", "kind": "other", "actor": "", "est": 0.01,
               "input": '{"profiles": "{{handles}}"}'},
}

# Campaign capture (Bido, 2026-10-19): a campaign that goes live gets the same daily capture jobs as Jamjoom, one per
# platform, so the dashboard's Update now and the daily run work from day one. Snapchat uses the actor Jamjoom settled on.
CAMPAIGN_CAPTURE = [("post_ig", None), ("post_tt", None), ("post_fb", None), ("post_yt", None),
                    ("post_sc", {"actor": "chronometrica/snapchat-metrics-scraper", "est": 0.002,
                                 "input": '{"startUrls": "{{urls}}"}'})]
CAMPAIGN_CAPTURE_AT = "18:00"          # Riyadh time; Update now moves it to the time of the last press

MAX_PARALLEL = 5                       # per-creator runs in flight at once
# TikTok analytics samples the last 100 posts (the actor charges $0.00001 per creator at any size,
# 1-100); a creator with fewer posts is covered whole. Fix batch 6, Bido 2026-10-10.
TIKTOK_SAMPLE = 100
# Actors that run out of memory on a long list are sent a few creators at a time.
CHUNK = {"maximedupre/tiktok-creator-analytics": 25}

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
CREATE TABLE IF NOT EXISTS api_audit (
  id     INTEGER PRIMARY KEY,
  at     INTEGER NOT NULL,
  who    TEXT,
  action TEXT NOT NULL,
  detail TEXT
);
CREATE TABLE IF NOT EXISTS profile_metrics (
  id          INTEGER PRIMARY KEY,
  code        TEXT NOT NULL,
  platform    TEXT NOT NULL,
  handle      TEXT,
  at          INTEGER NOT NULL,
  followers   INTEGER, following INTEGER, posts INTEGER,
  avg_likes   REAL, avg_comments REAL, er_pct REAL,
  posts_per_week REAL, last_post TEXT, sample_posts INTEGER,
  verified    INTEGER, category TEXT, run_id INTEGER
);
CREATE INDEX IF NOT EXISTS profile_metrics_code ON profile_metrics(code, platform, at DESC);
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
        # Fix batch 6: TikTok analytics jobs saved with the old 20-post sample take 100 (same price).
        for r in conn.execute("SELECT id, input FROM api_jobs WHERE actor = ?", ("maximedupre/tiktok-creator-analytics",)).fetchall():
            fixed = re.sub(r'("postSampleSize"\s*:\s*)(\d+)', lambda m: m.group(1) + str(TIKTOK_SAMPLE) if int(m.group(2)) < TIKTOK_SAMPLE else m.group(0), r["input"])
            if fixed != r["input"]:
                conn.execute("UPDATE api_jobs SET input = ? WHERE id = ?", (fixed, r["id"]))


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


def call_text(path, timeout=30):
    """A plain-text answer from Apify, such as a run's log."""
    token = get_token()
    if not token:
        return ""
    req = urllib.request.Request(API + path, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError):
        return ""


def run_cost(d):
    """What a run cost. Pay-per-result actors charge through events, which the
    run's usage total does not always include, so both are counted and the
    larger is kept."""
    usage = float(d.get("usageTotalUsd") or 0)
    events = 0.0
    try:
        prices = ((d.get("pricingInfo") or {}).get("pricingPerEvent") or {}).get("actorChargeEvents") or {}
        for name, n in (d.get("chargedEventCounts") or {}).items():
            events += float(n or 0) * float((prices.get(name) or {}).get("eventPriceUsd") or 0)
    except (TypeError, ValueError):
        pass
    return max(usage, events)


def failure_note(run, d, status):
    """Why a run did not finish: Apify's own status line and the tail of its log."""
    bits = ["Apify ended the run as %s." % status]
    if d.get("statusMessage"):
        bits.append(str(d["statusMessage"])[:300])
    log = call_text("/actor-runs/%s/log" % run["apify_run"])
    lines = [ln.strip() for ln in log.splitlines() if ln.strip()][-6:]
    if lines:
        bits.append("Log: " + " | ".join(l[:200] for l in lines))
    return " ".join(bits)


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
    """What this month has cost, counting runs still in flight at their estimate
    so a batch started all at once cannot each pass the budget check alone."""
    with db.connect() as conn:
        done = conn.execute("SELECT COALESCE(SUM(cost),0) c FROM api_runs WHERE started_at >= ? "
                            "AND status NOT IN ('QUEUED','RUNNING')", (month_start(),)).fetchone()["c"]
        pending = conn.execute("SELECT COALESCE(SUM(r.handles * COALESCE(j.est_each, 0.01)),0) c FROM api_runs r "
                               "LEFT JOIN api_jobs j ON j.id = r.job_id WHERE r.status IN ('QUEUED','RUNNING')"
                               ).fetchone()["c"]
    return done + pending


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


def _post_pairs(job):
    """[(content id, post link)] for a campaign's live posts on the job's platform."""
    src = job["source"] or ""
    if not (src.startswith("campaign:") and src[9:].isdigit()):
        return []
    with db.connect() as conn:
        rows = conn.execute("SELECT id, url FROM content WHERE campaign_id = ? AND hidden = 0 AND platform = ? "
                            "ORDER BY id", (int(src[9:]), job["platform"])).fetchall()
    cap = max(1, min(int(job["max_handles"] or 100), HARD_MAX_HANDLES))
    return [(str(r["id"]), r["url"]) for r in rows][:cap]


def build_handles(job):
    """[(creator code, handle)] for a job, in order, no duplicates, capped."""
    if job["kind"] == "post_urls":
        return _post_pairs(job)
    plat = job["platform"]
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM creators WHERE active = 1 ORDER BY sort, code").fetchall()
        allowed = None
        src = job["source"] or "all"
        if src.startswith("selection:") and src[10:].isdigit():
            r = conn.execute("SELECT codes FROM selections WHERE id = ?", (int(src[10:]),)).fetchone()
            allowed = set(json.loads(r["codes"] or "[]")) if r else set()
        elif src.startswith("creator:"):
            allowed = {src[8:].strip().upper()}
        elif src.startswith("evidence-noviews:") and src[17:].isdigit():
            import evidence
            allowed = evidence.noviews_codes(int(src[17:]))
        elif src.startswith("evidence-gaps:") and src[14:].isdigit():
            import evidence
            allowed = evidence.gap_codes(int(src[14:]))
        elif src == "evidence" or (src.startswith("evidence:") and src[9:].isdigit()):
            # Creators a competitor evidence pack added to the roster. They are hidden until reviewed,
            # and analysing them is the point of the mark, so hidden ones count here.
            import evidence
            allowed = evidence.roster_codes(int(src[9:]) if src != "evidence" else None)
            have = {c["code"] for c in rows}
            rows = list(rows) + [c for c in conn.execute("SELECT * FROM creators WHERE active = 0 ORDER BY sort, code")
                                 if c["code"] in allowed and c["code"] not in have]
        elif src == "sample20":
            have = {r["code"] for r in conn.execute("SELECT code FROM creator_analysis")}
            ranked = sorted(rows, key=lambda c: (c["code"] not in have, c["code"]))
            usable = [c["code"] for c in ranked if creator_handles(c).get(plat)]
            allowed = set(usable[:20])
        elif src == "noposts":
            have = set()
            for r in conn.execute("SELECT code, data FROM creator_analysis WHERE platform = ?", (plat,)):
                try:
                    d = json.loads(r["data"])
                except ValueError:
                    d = {}
                if not d.get("basic") or d.get("top_posts") or d.get("posts_stored"):
                    have.add(r["code"])
            allowed = {c["code"] for c in rows} - have
        elif src == "noplat":
            have = {r["code"] for r in conn.execute("SELECT code FROM creator_analysis WHERE platform = ?", (plat,))}
            allowed = {c["code"] for c in rows} - have
        elif src == "noanalysis":
            have = {r["code"] for r in conn.execute("SELECT code FROM creator_analysis")}
            allowed = {c["code"] for c in rows} - have
        elif src == "nosnap":
            have = {r["code"] for r in conn.execute(
                "SELECT DISTINCT code FROM profile_snapshots WHERE platform = ?", (plat,))}
            allowed = {c["code"] for c in rows} - have
        elif src.startswith("competitor:") and src[11:].isdigit():
            # Not a creator at all: the competitor's own profile, as a URL the actor can open.
            import competitors as _comp
            c_ = _comp.get(int(src[11:]))
            h_ = (c_ or {}).get("handles", {}).get(plat or "Instagram")
            return [("COMP:%s" % src[11:], _comp.profile_url(plat or "Instagram", h_))] if h_ else []
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
    if not any(t in tmpl for t in ("{{handles}}", "{{handle}}", "{{urls}}", "{{url_objs}}")):
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
            f.get("kind") if f.get("kind") in ("profiles", "analysis", "posts", "post_urls", "competitor", "other") else "other",
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

def list_runs(limit=25, status="", job=""):
    q, args = "SELECT * FROM api_runs", []
    where = []
    if status:
        where.append("status = ?")
        args.append(status.upper())
    if job:
        where.append("job_name = ?")
        args.append(job)
    if where:
        q += " WHERE " + " AND ".join(where)
    with db.connect() as conn:
        return conn.execute(q + " ORDER BY id DESC LIMIT ?", args + [limit]).fetchall()


def _refuse(job, trigger, why):
    with db.connect() as conn:
        conn.execute("INSERT INTO api_runs (job_id, job_name, trigger, status, message, started_at, finished_at) "
                     "VALUES (?,?,?,?,?,?,?)", (job["id"], job["name"], trigger, "REFUSED", why, db.now(), db.now()))
    return why


def render_input(tmpl, handles):
    """The job's JSON with the handles put in. "{{handles}}" becomes the list,
    "{{handle}}" the first one, "{{count}}" how many there are."""
    t = tmpl.replace('"{{url_objs}}"', json.dumps([{"url": h} for h in handles]))
    t = t.replace('"{{urls}}"', json.dumps(list(handles)))
    t = t.replace('"{{handles}}"', json.dumps(handles))
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
    if paused():
        return False, "Apify is paused. Resume it on this page first."
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
    chunk = CHUNK.get(job["actor"])
    if chunk and len(pairs) > chunk:
        with db.connect() as conn:
            for i in range(0, len(pairs), chunk):
                part = pairs[i:i + chunk]
                conn.execute("INSERT INTO api_runs (job_id, job_name, trigger, status, handles, handle_map, started_at) "
                             "VALUES (?,?,?,?,?,?,?)", (jid, job["name"], trigger, "QUEUED", len(part),
                                                       json.dumps({h.lower(): c for c, h in part}), db.now()))
            conn.execute("UPDATE api_jobs SET last_started = ? WHERE id = ?", (db.now(), jid))
        pump()
        return True, "Queued %d runs of up to %d creators, about $%.2f." % (-(-len(pairs) // chunk), chunk, est)
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
                params={"maxTotalChargeUsd": "%.2f" % max(run_cap(), float(job["est_each"] or 0) * 1.3 * max(1, len(handles)))})["data"]


def pump():
    """Start queued per-creator runs, up to MAX_PARALLEL in flight."""
    if paused():
        return
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


_HANDLE_KEYS = ("username", "ownerUsername", "uniqueId", "handle", "influencerHandle", "userName", "profileName", "nickname_id")


def _match(item, hmap):
    """Which handle in this run an item belongs to."""
    for k in _HANDLE_KEYS:
        v = item.get(k)
        if isinstance(v, str) and v.lstrip("@").lower() in hmap:
            return v.lstrip("@").lower()
    cr = item.get("creator")
    if isinstance(cr, dict) and str(cr.get("handle", "")).lstrip("@").lower() in hmap:
        return str(cr["handle"]).lstrip("@").lower()
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



_TAG = re.compile(r"#([^\s#@!?.,;:()\[\]{}\"'<>]{2,60})", re.U)
_MEN = re.compile(r"@([A-Za-z0-9._]{2,30})")


def tag_shares(pairs, total, top=10):
    """[{"tag", "count"}] where count is the share of posts (percent) that used it."""
    from collections import Counter
    c = Counter()
    for tags in pairs:
        for t in set(tags):
            c[t] += 1
    return [{"tag": t, "count": round(n * 100.0 / total, 1)} for t, n in c.most_common(top) if total]


def tags_from_posts(rows):
    """Hashtags and @mentions across posts: rows are (hashtags, mentions) lists."""
    total = len(rows)
    tags = tag_shares([["#" + str(t).lstrip("#") for t in r[0]] for r in rows], total)
    ments = tag_shares([["@" + str(m).lstrip("@") for m in r[1]] for r in rows], total)
    return tags + ments


def derive_instagram(it):
    """Basic numbers worked out from an Instagram profile result: the profile's
    own counts, and averages over the latest posts it carries."""
    posts = [p for p in (it.get("latestPosts") or []) if isinstance(p, dict)]
    likes = [p.get("likesCount") for p in posts if isinstance(p.get("likesCount"), (int, float)) and p["likesCount"] >= 0]
    coms = [p.get("commentsCount") for p in posts if isinstance(p.get("commentsCount"), (int, float)) and p["commentsCount"] >= 0]
    followers = _num(it.get("followersCount"))
    out = {"followers": followers, "following": _num(it.get("followsCount")), "posts": _num(it.get("postsCount")),
           "verified": 1 if it.get("verified") else 0, "category": it.get("businessCategoryName") or "",
           "avg_likes": round(sum(likes) / len(likes), 1) if likes else None,
           "avg_comments": round(sum(coms) / len(coms), 1) if coms else None,
           "er_pct": None, "posts_per_week": None, "last_post": None, "sample_posts": len(posts)}
    if followers and out["avg_likes"] is not None:
        out["er_pct"] = round((out["avg_likes"] + (out["avg_comments"] or 0)) * 100.0 / followers, 3)
    scored = sorted((p for p in posts if p.get("url")), key=lambda p: (p.get("likesCount") or 0) + (p.get("commentsCount") or 0), reverse=True)
    out["top_posts"] = [{"url": p["url"], "likes": p.get("likesCount"), "comments": p.get("commentsCount"),
                         "date": str(p.get("timestamp") or "")[:10] or None} for p in scored[:6]]
    out["hashtags"] = tags_from_posts([(p.get("hashtags") or [], p.get("mentions") or []) for p in posts]) if posts else []
    vids = [p for p in posts if str(p.get("type")).lower() == "video"]
    if vids and followers:
        vl = [p.get("likesCount") for p in vids if isinstance(p.get("likesCount"), (int, float)) and p["likesCount"] >= 0]
        vc = [p.get("commentsCount") for p in vids if isinstance(p.get("commentsCount"), (int, float)) and p["commentsCount"] >= 0]
        if vl:
            out["avg_reel_likes"] = round(sum(vl) / len(vl), 1)
            out["avg_reel_comments"] = round(sum(vc) / len(vc), 1) if vc else None
            out["reels_er"] = round((out["avg_reel_likes"] + (out["avg_reel_comments"] or 0)) * 100.0 / followers, 3)
            out["reel_posts"] = len(vids)
    stamps = sorted(str(p.get("timestamp"))[:10] for p in posts if p.get("timestamp"))
    if stamps:
        out["last_post"] = stamps[-1]
        try:
            span = (time.mktime(time.strptime(stamps[-1], "%Y-%m-%d")) - time.mktime(time.strptime(stamps[0], "%Y-%m-%d"))) / 86400.0
            if len(stamps) > 1 and span > 0:
                out["posts_per_week"] = round((len(stamps) - 1) * 7.0 / span, 2)
        except ValueError:
            pass
    return out


def _median(v):
    v = sorted(v)
    n = len(v)
    return None if not n else (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0)


def _pctile(v, q):
    v = sorted(v)
    return None if not v else v[int(round(q * (len(v) - 1)))]


def post_stats(posts, rp=None):
    """What the sampled posts say about a typical post: the MEDIAN views, likes and comments (an
    average is lifted by viral posts), the middle half of views, how much views swing (spread over
    the average), and how many posts the sample holds. A creator with fewer posts than were asked
    for is covered whole: `sample_posts` is how many were really used."""
    views = [p["views"] for p in posts if isinstance(p.get("views"), (int, float)) and p["views"] >= 0]
    likes = [p["likes"] for p in posts if isinstance(p.get("likes"), (int, float)) and p["likes"] >= 0]
    coms = [p["comments"] for p in posts if isinstance(p.get("comments"), (int, float)) and p["comments"] >= 0]
    shares = [p["shares"] for p in posts if isinstance(p.get("shares"), (int, float)) and p["shares"] >= 0]
    out = {"sample_posts": len(posts)}
    if views:
        mean = sum(views) / float(len(views))
        out.update(median_views=round(_median(views)), views_p25=round(_pctile(views, .25)), views_p75=round(_pctile(views, .75)),
                   views_spread=round((sum((x - mean) ** 2 for x in views) / len(views)) ** 0.5 / mean, 2) if mean else None,
                   views_series=[int(x) for x in views[:TIKTOK_SAMPLE]])
    if likes:
        out["median_likes"] = round(_median(likes), 1)
    if coms:
        out["median_comments"] = round(_median(coms), 1)
    if shares:
        out["median_shares"] = round(_median(shares), 1)
    if views and likes and len(likes) == len(views):
        per = [(l + (c or 0) + (s or 0)) * 100.0 / v for l, c, s, v in
               zip(likes, coms if len(coms) == len(views) else [0] * len(views), shares if len(shares) == len(views) else [0] * len(views), views) if v > 0]
        if per:
            out["median_er_on_views"] = round(_median(per), 2)
    return out


def trim_posts(it):
    """The analytics result with each post cut to its numbers (no caption text), so a 100-post
    sample fits the raw store whole instead of being replaced by an "[omitted]" note."""
    rp = it.get("recentPosts")
    if not isinstance(rp, dict) or not isinstance(rp.get("posts"), list):
        return it
    slim = [{k: p.get(k) for k in ("url", "publishedAt", "views", "likes", "comments", "shares") if p.get(k) is not None}
            for p in rp["posts"] if isinstance(p, dict)]
    return dict(it, recentPosts=dict(rp, posts=slim))


def derive_tiktok_analytics(it):
    """Basic numbers from the TikTok creator analytics result: the profile's own
    counts and averages over the latest posts (engagement here is measured
    against views, as that actor defines it)."""
    cr, au = it.get("creator") or {}, it.get("audience") or {}
    rp = it.get("recentPosts") or {}
    av, eng = rp.get("averages") or {}, rp.get("engagement") or {}
    posts = [p for p in (rp.get("posts") or []) if isinstance(p, dict)]
    stamps = sorted(str(p.get("publishedAt"))[:10] for p in posts if p.get("publishedAt"))
    out = {"followers": _num(au.get("followers")), "following": _num(au.get("following")),
           "posts": _num(au.get("videoCount")), "verified": 1 if cr.get("isVerified") else 0, "category": "",
           "avg_likes": round(av["likes"], 1) if isinstance(av.get("likes"), (int, float)) else None,
           "avg_comments": round(av["comments"], 1) if isinstance(av.get("comments"), (int, float)) else None,
           "avg_views": round(av["views"]) if isinstance(av.get("views"), (int, float)) else None,
           "er_pct": round(eng["ratePercent"], 3) if isinstance(eng.get("ratePercent"), (int, float)) else None,
           "er_basis": "views", "posts_per_week": None, "last_post": stamps[-1] if stamps else None,
           "sample_posts": _num(rp.get("usedCount")) or len(posts), "bio": cr.get("bio") or ""}
    out.update(post_stats(posts, rp))
    top = sorted((p for p in posts if p.get("url")), key=lambda p: p.get("views") or 0, reverse=True)
    out["top_posts"] = [{"url": p["url"], "likes": p.get("likes"), "comments": p.get("comments"), "views": p.get("views"),
                         "date": str(p.get("publishedAt") or "")[:10] or None} for p in top[:6]]
    out["hashtags"] = tags_from_posts([(_TAG.findall(p.get("text") or ""), _MEN.findall(p.get("text") or "")) for p in posts]) if posts else []
    if len(stamps) > 1:
        try:
            span = (time.mktime(time.strptime(stamps[-1], "%Y-%m-%d")) - time.mktime(time.strptime(stamps[0], "%Y-%m-%d"))) / 86400.0
            if span > 0:
                out["posts_per_week"] = round((len(stamps) - 1) * 7.0 / span, 2)
        except ValueError:
            pass
    return out


def save_basic(conn, code, plat, handle, it, m, run_id):
    """Keep the worked-out numbers and, for a creator with no analysis on this
    platform, a basic profile record the creator page can show. A creator who
    already has a real analysis is never touched."""
    conn.execute("INSERT INTO profile_metrics (code,platform,handle,at,followers,following,posts,avg_likes,avg_comments,"
                 "er_pct,posts_per_week,last_post,sample_posts,verified,category,run_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (code, plat, handle, db.now(), m["followers"], m["following"], m["posts"], m["avg_likes"], m["avg_comments"],
                  m["er_pct"], m["posts_per_week"], m["last_post"], m["sample_posts"], m["verified"], m["category"], run_id))
    cur = conn.execute("SELECT data FROM creator_analysis WHERE code = ? AND platform = ?", (code, plat)).fetchone()
    kept = {}
    if cur is not None:
        try:
            old = json.loads(cur["data"])
            if not old.get("basic"):
                return False
            kept = {p.get("url"): p["thumb"] for p in old.get("top_posts") or [] if p.get("thumb")}
        except ValueError:
            return False
    data = {"basic": True, "platform": plat, "handle": handle, "updated": time.strftime("%Y-%m-%d", time.gmtime()),
            "followers": m["followers"], "following": m["following"], "posts_count": m["posts"],
            "avg_likes": m["avg_likes"], "avg_comments": m["avg_comments"], "er": m["er_pct"],
            "posts_per_week": m["posts_per_week"], "last_post": m["last_post"], "sample_posts": m["sample_posts"],
            "verified": bool(m["verified"]), "account_type": m["category"] or None,
            "bio": it.get("biography") or m.get("bio") or "", "external_url": it.get("externalUrl") or ""}
    data["posts_stored"] = True
    for p in m.get("top_posts") or []:
        if p.get("url") in kept:
            p["thumb"] = kept[p["url"]]
    for k in ("top_posts", "hashtags", "avg_reel_likes", "avg_reel_comments", "reels_er", "reel_posts"):
        if m.get(k) not in (None, [], ""):
            data[k] = m[k]
    if m.get("avg_views") is not None:
        data["avg_views"] = m["avg_views"]
    for k in ("median_views", "views_p25", "views_p75", "views_spread", "views_series",
              "median_likes", "median_comments", "median_shares", "median_er_on_views"):
        if m.get(k) not in (None, [], ""):
            data[k] = m[k]
    if m.get("er_basis"):
        data["er_basis"] = m["er_basis"]
    db.save_analysis(code, data, "Apify basic", conn, plat)
    return True


_POST_FIELDS = {
    "likes": ("likescount", "likecount", "likes", "diggcount", "reactioncount", "reactionscount", "reactions",
              "like_count", "digg_count", "totalreactions"),
    "comments": ("commentscount", "commentcount", "comments", "comment_count", "commentnum"),
    "views": ("videoplaycount", "viewscount", "playcount", "play_count", "videoviewcount", "viewcount", "views", "view_count",
              "plays", "videoplays", "playscount"),
    "shares": ("sharescount", "sharecount", "shares", "share_count", "repostcount", "reposts"),
    "saves": ("collectcount", "savescount", "savecount", "saves", "bookmarkcount", "favoritecount"),
}


def _post_key(url):
    """The id that names a post in its link, lower case, as it will appear in the actor's result."""
    u = (url or "").lower()
    for rx in (r"/(?:reel|reels|p|tv)/([a-z0-9_\-]+)", r"/video/(\d+)", r"/shorts/([a-z0-9_\-]+)",
               r"[?&]v=([a-z0-9_\-]+)", r"/spotlight/([a-z0-9_\-]{16,})", r"/share/(?:r|v|p)/([a-z0-9_\-]+)"):
        m = re.search(rx, u)
        if m:
            return m.group(1)
    return None


def _scalars(obj, out, depth=0):
    if depth > 3:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                _scalars(v, out, depth + 1)
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                out.setdefault(str(k).lower(), v)
    elif isinstance(obj, list):
        for v in obj[:5]:
            _scalars(v, out, depth + 1)


def post_numbers(item):
    """{likes, comments, views, shares, saves} found in one actor result, whatever it calls them."""
    flat = {}
    _scalars(item, flat)
    vals = {}
    for m, names in _POST_FIELDS.items():
        for n in names:
            v = _num(flat.get(n))
            if v is not None and v >= 0:      # -1 means the platform does not show it
                vals[m] = v
                break
    return vals


def _thumb_hint(item):
    """A picture link the actor returned for a post, for the thumbnail fetch to try when the page gives none."""
    flat = {}

    def walk(o, d=0):
        if d > 2:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and v.startswith("http"):
                    flat.setdefault(str(k).lower(), v)
                elif isinstance(v, (dict, list)):
                    walk(v, d + 1)
        elif isinstance(o, list):
            for v in o[:3]:
                walk(v, d + 1)
    walk(item)
    for k in ("thumbnailurl", "displayurl", "coverurl", "cover", "thumbnail", "thumbnail_url", "imageurl",
              "previewimageurl", "thumb", "image", "poster"):
        if flat.get(k):
            return flat[k]
    return None


def _posted_at(item):
    """When the post went up, from whichever field the actor uses (epoch seconds or milliseconds, or an ISO date)."""
    import datetime as _dt
    for k in ("taken_at_ts", "taken_at", "createTime", "create_time", "createdAt", "datePosted", "publishedAt",
              "published_at", "timestamp", "upload_date", "uploadDate", "date"):
        v = item.get(k)
        if v in (None, "", 0):
            continue
        try:
            n = float(v)
            return int(n / 1000 if n > 1e12 else n)
        except (TypeError, ValueError):
            pass
        s = str(v).strip().replace("Z", "+00:00")
        for fmt in (None, "%Y-%m-%d", "%Y%m%d"):
            try:
                d = _dt.datetime.fromisoformat(s) if fmt is None else _dt.datetime.strptime(s[:10 if fmt == "%Y-%m-%d" else 8], fmt)
                if d.tzinfo is None:
                    d = d.replace(tzinfo=_dt.timezone.utc)
                return int(d.timestamp())
            except ValueError:
                continue
    return None


def _caption(item):
    c = item.get("caption")
    if isinstance(c, dict):
        c = c.get("text")
    if not c:
        c = item.get("description") or item.get("title") or item.get("text")
    return c.strip()[:4000] if isinstance(c, str) and c.strip() else None


def ingest_posts(run, job, items, hmap, store_raw=True):
    """Campaign-post runs: each result goes to the post whose link id it carries (the only post when a
    run has one), and its numbers become that post's snapshot for today."""
    saved = 0
    keys = {url: (cid, _post_key(url)) for url, cid in hmap.items()}
    with db.connect() as conn:
        for it in items:
            if not isinstance(it, dict):
                continue
            text = json.dumps(it, default=str).lower()
            # The whole link id first: Snapchat spotlight ids of one creator share their first 24 characters,
            # so a shortened id sent one post's numbers to the other. The first 24 only when no whole id matches
            # and they name a single post.
            whole = sorted(((len(k), c) for _u, (c, k) in keys.items() if k and k in text), reverse=True)
            part = {c for _u, (c, k) in keys.items() if k and k[:24] in text}
            cid = whole[0][1] if whole else (next(iter(part)) if len(part) == 1 else None)
            if cid is None and len(keys) == 1:
                cid = next(iter(keys.values()))[0]
            if store_raw:
                small = it if len(json.dumps(it, default=str)) <= 60000 else _compact(it)
                conn.execute("INSERT INTO profile_raw (run_id, code, platform, actor, at, data) VALUES (?,?,?,?,?,?)",
                             (run["id"], "post:%s" % cid if cid else "", job["platform"], job["actor"], db.now(),
                              json.dumps(small, default=str)))
            vals = post_numbers(it) if cid else {}
            hint = _thumb_hint(it) if cid else None
            if hint:
                conn.execute("UPDATE content SET thumb = ? WHERE id = ? AND (thumb IS NULL OR thumb = '')", (hint, int(cid)))
            if cid:
                # The date and caption the platform shows, for a post added by hand without them (the chart is drawn by date,
                # and the disclosure check reads the caption). Never overwrites what the team typed in.
                row = conn.execute("SELECT c.posted_at, c.caption, k.* FROM content c JOIN campaigns k ON k.id = c.campaign_id "
                                   "WHERE c.id = ?", (int(cid),)).fetchone()
                when, cap = _posted_at(it), _caption(it)
                if row is not None and row["posted_at"] is None and when:
                    conn.execute("UPDATE content SET posted_at = ? WHERE id = ?", (when, int(cid)))
                if row is not None and not row["caption"] and cap:
                    _sec, disc = db.match_rules(db.rules_of(row), cap)
                    conn.execute("UPDATE content SET caption = ?, disclosure_ok = ? WHERE id = ?", (cap, disc, int(cid)))
                # Item 216: a post on a platform the creator has no profile for adds that profile (History, undoable).
                import postprofiles
                postprofiles.learn(conn, int(cid), job["platform"], it)
            if vals:
                db.add_snapshot(int(cid), vals, "apify", conn)
                saved += 1
        camp = conn.execute("SELECT campaign_id FROM content WHERE id = ?", (int(next(iter(hmap.values()))),)).fetchone() if hmap else None
    if camp:
        try:
            import thumbs
            thumbs.fill_later(camp["campaign_id"])      # store the pictures on our own server
        except Exception:
            pass
    return saved


def ingest(run, job, items, store_raw=True):
    """Keep every result as the actor returned it, the follower number as a
    dated snapshot, and for Instagram profile runs the basic numbers.
    store_raw=False reads results already kept (reingest_run) without storing them twice."""
    hmap = json.loads(run["handle_map"] or "{}")
    plat = job["platform"] if job else ""
    if job and job["kind"] == "post_urls":
        return ingest_posts(run, job, items, hmap, store_raw)
    if job and job["kind"] == "competitor":
        # Every item is one of the competitor's posts; evidence.py turns the creators in them
        # into pack rows, so the result reads exactly like an imported study.
        import evidence as _ev
        return _ev.ingest_competitor_posts(job, items)
    saved = 0
    with db.connect() as conn:
        for it in items:
            if not isinstance(it, dict):
                continue
            h = _match(it, hmap)
            code = hmap.get(h) if h else None
            raw = trim_posts(it) if isinstance(it.get("recentPosts"), dict) else it
            small = raw if len(json.dumps(raw, default=str)) <= 60000 else _compact(raw)
            if store_raw:
                conn.execute("INSERT INTO profile_raw (run_id, code, platform, actor, at, data) VALUES (?,?,?,?,?,?)",
                             (run["id"], code or "", plat, job["actor"] if job else "", db.now(),
                              json.dumps(small, default=str)))
            # The TikTok analytics actor (preset kind "analysis") brings the profile counts too: its
            # numbers were only read on "profiles" jobs, so the preset's own runs saved nothing.
            if job and job["kind"] in ("profiles", "analysis") and code and isinstance(it.get("audience"), dict) and isinstance(it.get("creator"), dict):
                m = derive_tiktok_analytics(it)
                if m["followers"] is not None:
                    conn.execute("INSERT INTO profile_snapshots (code,platform,handle,at,followers,following,posts,verified,run_id) "
                                 "VALUES (?,?,?,?,?,?,?,?,?)", (code, plat, h, db.now(), m["followers"], m["following"],
                                                               m["posts"], m["verified"], run["id"]))
                    saved += 1
                    save_basic(conn, code, plat, h, it, m, run["id"])
                    _evidence_profile(conn, code, plat, m["followers"], it)
                continue
            if job and job["kind"] == "profiles" and code:
                f = next((x for x in (_num(it.get(k)) for k in (
                    "followersCount", "followers", "followerCount", "follower_count", "subscriberCount",
                    "subscribersCount", "subscribers")) if x is not None), None)
                if f is None and isinstance(it.get("authorMeta"), dict):
                    f = _num(it["authorMeta"].get("fans"))
                if f is not None:
                    conn.execute("INSERT INTO profile_snapshots (code,platform,handle,at,followers,following,posts,verified,run_id) "
                                 "VALUES (?,?,?,?,?,?,?,?,?)",
                                 (code, plat, h, db.now(), f,
                                  _num(it.get("followsCount", it.get("following", it.get("following_count")))),
                                  _num(it.get("postsCount", it.get("posts", it.get("video_count")))),
                                  1 if it.get("verified") else 0, run["id"]))
                    saved += 1
                    if plat == "Instagram" and "followersCount" in it:
                        save_basic(conn, code, plat, h, it, derive_instagram(it), run["id"])
                    _evidence_profile(conn, code, plat, f, it)
    return saved


REEL_ACTOR = "apify/instagram-reel-scraper"


def reels_rollup(run_id):
    """Reel views per creator from a reel-scraper run (2026-10-14): the reels are one result each, so
    they are summed up once the whole run is read. The views numbers (median, middle half, spread,
    series, average plays, engagement on views) are merged into the creator's post sample; what the
    25-post scan found (likes, hashtags, posting rhythm) stays. Returns how many creators got views."""
    import postscan
    with db.connect() as conn:
        run = conn.execute("SELECT * FROM api_runs WHERE id = ?", (run_id,)).fetchone()
        hmap = json.loads(run["handle_map"] or "{}") if run is not None else {}
        rows = conn.execute("SELECT code, data FROM profile_raw WHERE run_id = ?", (run_id,)).fetchall()
        postscan.init(conn)
    by = {}
    for r in rows:
        try:
            it = json.loads(r["data"])
        except ValueError:
            continue
        code = r["code"] or hmap.get(str(it.get("ownerUsername") or "").lower())
        plays = it.get("videoPlayCount") if isinstance(it.get("videoPlayCount"), (int, float)) else it.get("videoViewCount")
        if not code or not isinstance(plays, (int, float)) or plays <= 0:
            continue
        by.setdefault(code, []).append({"views": plays, "likes": it.get("likesCount"), "comments": it.get("commentsCount"),
                                        "at": str(it.get("timestamp") or "")})
    n = 0
    for code, reels in by.items():
        reels.sort(key=lambda x: x["at"], reverse=True)
        st = post_stats(reels)
        views = [x["views"] for x in reels]
        add = {k: st[k] for k in ("median_views", "views_p25", "views_p75", "views_spread", "views_series", "median_er_on_views")
               if st.get(k) not in (None, [], "")}
        if not add:
            continue
        add["avg_reel_plays"] = round(sum(views) / float(len(views)))
        with db.connect() as conn:
            cur = conn.execute("SELECT handle, data FROM post_samples WHERE code = ? AND platform = 'Instagram'", (code,)).fetchone()
        old = json.loads(cur["data"]) if cur is not None else {}
        handle = cur["handle"] if cur is not None else next((h for h, c in hmap.items() if c == code), "")
        n += postscan.save(code, "Instagram", handle, dict(old, **add), "reels:%s" % run_id)
    return n


def reingest_run(run_id):
    """Read a finished run's kept results again (after a reader fix), without asking Apify or paying
    again. Returns how many creators' numbers were saved."""
    with db.connect() as conn:
        run = conn.execute("SELECT * FROM api_runs WHERE id = ?", (run_id,)).fetchone()
        items = [json.loads(r["data"]) for r in conn.execute("SELECT data FROM profile_raw WHERE run_id = ? ORDER BY id", (run_id,))]
    if run is None or not items:
        return 0
    job = get_job(run["job_id"]) if run["job_id"] else None
    return ingest(run, job, items, store_raw=False)


_SLIM = "profilePicUrl,profilePicUrlHD,externalUrlShimmed,latestIgtvVideos,relatedProfiles"
# Instagram profile runs keep the HD picture link: creators added from competitor evidence take their photo from it.
_SLIM_IG_PROFILES = "profilePicUrl,externalUrlShimmed,latestIgtvVideos,relatedProfiles"


def _evidence_profile(conn, code, plat, followers, item):
    """Creators a competitor evidence pack added are hidden until reviewed; their roster entry (followers,
    tier, photo) is brought up to date from the profile result. Never fails an ingest."""
    try:
        import evidence
        evidence.on_profile(conn, code, plat, followers, item)
    except Exception as ex:
        print("evidence profile update:", code, repr(ex)[:120], flush=True)


def refresh_run(run):
    """Ask Apify how one run is going and finish it off when it is done. Results
    are read a page at a time: a large run's results are far bigger than this
    service's memory."""
    try:
        d = call("GET", "/actor-runs/" + run["apify_run"])["data"]
    except ApifyError as ex:
        if db.now() - run["started_at"] > 6 * 3600:
            _finish(run, "FAILED", 0, 0, 0.0, "Lost track of this run: " + str(ex))
        return
    st = d.get("status")
    cost = run_cost(d)
    if st in ("READY", "RUNNING", "ABORTING", "TIMING-OUT"):
        return
    if st != "SUCCEEDED":
        _finish(run, "FAILED", 0, 0, cost, failure_note(run, d, st))
        return
    total, saved, note = 0, 0, None
    job = get_job(run["job_id"]) if run["job_id"] else None
    try:
        offset = 0
        while True:
            page = call("GET", "/datasets/%s/items" % run["dataset"],
                        params={"format": "json", "clean": "1", "limit": "20", "offset": str(offset),
                                "omit": _SLIM_IG_PROFILES if job and job["kind"] == "profiles" and job["platform"] == "Instagram" else _SLIM},
                        timeout=90)
            page = page if isinstance(page, list) else []
            if not page:
                break
            total += len(page)
            saved += ingest(run, job, page)
            offset += len(page)
            if len(page) < 20 or total >= 5000:
                break
        if not total:
            note = "The run finished but returned no results."
        elif job and job["kind"] == "profiles" and not saved:
            note = "Results kept, but no follower count was recognised in them."
        elif job and job["kind"] == "post_urls" and not saved:
            note = "Results kept, but no post numbers were recognised in them."
    except ApifyError as ex:
        note = "Run finished but the results could not be read: " + str(ex)
    if job and job["actor"] == REEL_ACTOR:
        try:
            saved = reels_rollup(run["id"])
            if total and not saved:
                note = "Reels kept, but no play counts were in them."
        except Exception as ex:
            note = "Reels kept, but they could not be summed up: " + repr(ex)[:120]
    _finish(run, "SUCCEEDED", total, saved, cost, note)


def _finish(run, status, results, saved, cost, message):
    with db.connect() as conn:
        conn.execute("UPDATE api_runs SET status=?, results=?, saved=?, cost=?, message=?, finished_at=? WHERE id=?",
                     (status, results, saved, cost, message, db.now(), run["id"]))


_REFRESH_LOCK = threading.Lock()


def refresh_all():
    # One pass at a time: the scheduler and a dashboard's "Update now" both call this.
    if not _REFRESH_LOCK.acquire(blocking=False):
        return 0
    try:
        with db.connect() as conn:
            # Comment runs belong to comments.py, which reads them and never keeps the commenters (2026-10-21: this
            # poller used to take them first, keep the raw items with commenter names and leave the comments unread).
            live = conn.execute("SELECT * FROM api_runs WHERE status = 'RUNNING' AND apify_run IS NOT NULL "
                                "AND NOT (job_id IS NULL AND job_name LIKE 'Comments ·%')").fetchall()
        for r in live:
            refresh_run(r)
        pump()
        return len(live)
    finally:
        _REFRESH_LOCK.release()


def get_run(rid):
    with db.connect() as conn:
        return conn.execute("SELECT * FROM api_runs WHERE id = ?", (rid,)).fetchone()


def run_results(rid):
    with db.connect() as conn:
        return conn.execute("SELECT r.*, c.name FROM profile_raw r LEFT JOIN creators c ON c.code = r.code "
                            "WHERE r.run_id = ? ORDER BY r.id", (rid,)).fetchall()


# ------------------------------------------------------------ full collection --
# The perfect set per platform: every step is an ordinary job, so each can still
# be edited, paused or scheduled on its own. Steps marked expensive stay off
# unless asked for.
PACKS = {
    "Instagram": [("ig_profiles", "profile numbers", False),
                  ("ig_audience", "audience demographics", False), ("ig_audit", "follower audit", True)],
    "TikTok": [("tt_profiles", "profile numbers", False), ("tt_analytics", "engagement analytics", False),
               ("tt_audience", "audience demographics", False)],
}


def pack_job(preset, source, max_handles, schedule, at_time, weekday):
    """The job for one step of the collection: reused when it exists, so a
    repeat run does not pile up duplicates."""
    p = PRESETS[preset]
    name = "Full · " + p["label"]
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM api_jobs WHERE name = ?", (name,)).fetchone()
    return save_job({"id": str(row["id"]) if row else "", "name": name, "actor": p["actor"], "kind": p["kind"],
                     "platform": p["platform"], "source": source, "input": p["input"],
                     "max_handles": str(max_handles), "est_each": str(p["est"]), "schedule": schedule,
                     "at_time": at_time, "weekday": str(weekday)})


def run_pack(platforms, source, max_handles, with_audience, with_audit, schedule="manual",
             at_time="03:00", weekday=0):
    """Start every step for each platform. Checked as a whole first: if the
    whole collection would pass the monthly budget, nothing starts."""
    if not get_token():
        return False, "Save an Apify token first."
    steps = []
    for plat in platforms:
        for key, label, expensive in PACKS.get(plat, []):
            if "audience" in label and not with_audience:
                continue
            if expensive and not with_audit:
                continue
            steps.append(key)
    if not steps:
        return False, "Pick at least one platform."
    plan, total = [], 0.0
    for key in steps:
        jid = pack_job(key, source, max_handles, schedule, at_time, weekday)
        job = get_job(jid)
        n = len(build_handles(job))
        plan.append((jid, job["name"], n))
        total += n * float(job["est_each"] or 0)
    if not any(n for _j, _n, n in plan):
        return False, "No creator has a handle for that platform and source."
    if spent_this_month() + total > budget():
        return False, ("The whole collection is about $%.2f; this month has $%.2f left of the $%.2f budget. "
                       "Raise the budget or choose fewer steps or creators."
                       % (total, max(0.0, budget() - spent_this_month()), budget()))
    started = []
    for jid, name, n in plan:
        if n:
            ok, msg = start_job(jid, "manual")
            started.append("%s: %s" % (name.replace("Full · ", ""), msg if ok else "not started (%s)" % msg))
    return True, "Started %d steps, about $%.2f in all. " % (len(started), total) + " ".join(started)


def coverage(platform):
    """Per step: how many creators have a result from it."""
    out = []
    with db.connect() as conn:
        for key, label, _x in PACKS.get(platform, []):
            actor = PRESETS[key]["actor"]
            n = conn.execute("SELECT COUNT(DISTINCT code) c FROM profile_raw WHERE code != '' AND actor = ? "
                             "AND platform = ?", (actor, platform)).fetchone()["c"]
            out.append((label, actor, n))
    return out


def creators_with_data(q="", limit=60):
    like = "%" + q.strip().lower() + "%"
    with db.connect() as conn:
        return conn.execute(
            "SELECT c.code, c.name, MAX(r.at) last, COUNT(DISTINCT r.actor) actors FROM profile_raw r "
            "JOIN creators c ON c.code = r.code WHERE r.code != '' AND (lower(c.name) LIKE ? OR lower(c.code) LIKE ?) "
            "GROUP BY c.code ORDER BY last DESC LIMIT ?", (like, like, limit)).fetchall()


def creator_data(code):
    """The latest result from each actor for one creator."""
    with db.connect() as conn:
        return conn.execute(
            "SELECT * FROM profile_raw WHERE code = ? AND id IN (SELECT MAX(id) FROM profile_raw WHERE code = ? "
            "GROUP BY actor, platform) ORDER BY platform, actor", (code, code)).fetchall()


# ----------------------------------------------------------- portal helpers --

def audit(who, action, detail=""):
    """A line in the activity log: who changed what on this page, and when."""
    with db.connect() as conn:
        conn.execute("INSERT INTO api_audit (at, who, action, detail) VALUES (?,?,?,?)",
                     (db.now(), who or "", action, (detail or "")[:300]))


def list_audit(limit=15):
    with db.connect() as conn:
        return conn.execute("SELECT * FROM api_audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def paused():
    return bool(db.setting("apify_paused", False))


def set_paused(flag):
    db.set_setting("apify_paused", bool(flag))


def record_test(ok, text):
    db.set_setting("apify_last_test", {"at": db.now(), "ok": bool(ok), "text": text})


def last_test():
    return db.setting("apify_last_test") or None


def health():
    with db.connect() as conn:
        ok = conn.execute("SELECT MAX(finished_at) t FROM api_runs WHERE status = 'SUCCEEDED'").fetchone()["t"]
        live = conn.execute("SELECT COUNT(*) c FROM api_runs WHERE status = 'RUNNING'").fetchone()["c"]
        queued = conn.execute("SELECT COUNT(*) c FROM api_runs WHERE status = 'QUEUED'").fetchone()["c"]
        failed = conn.execute("SELECT COUNT(*) c FROM api_runs WHERE status IN ('FAILED','REFUSED') AND started_at >= ?",
                              (db.now() - 86400,)).fetchone()["c"]
    return {"last_ok": ok, "running": live, "queued": queued, "failed_24h": failed}


def spend_by_job():
    with db.connect() as conn:
        return conn.execute(
            "SELECT job_name, COUNT(*) runs, SUM(CASE WHEN status='SUCCEEDED' THEN 1 ELSE 0 END) ok, "
            "COALESCE(SUM(cost),0) cost FROM api_runs WHERE started_at >= ? GROUP BY job_name "
            "ORDER BY cost DESC", (month_start(),)).fetchall()


def estimate_job(jid):
    job = get_job(jid)
    n = len(build_handles(job)) if job else 0
    return n, n * float(job["est_each"] or 0) if job else 0.0


def clone_job(jid):
    j = get_job(jid)
    if j is None:
        return None
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO api_jobs (name,actor,kind,platform,source,input,max_handles,schedule,at_time,weekday,"
            "enabled,est_each,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (j["name"] + " (copy)", j["actor"], j["kind"], j["platform"], j["source"], j["input"], j["max_handles"],
             "manual", j["at_time"], j["weekday"], 1, j["est_each"], db.now()))
        return cur.lastrowid


def abort_run(rid):
    run = get_run(rid)
    if run is None or run["status"] not in ("RUNNING", "QUEUED"):
        return False, "That run is not active."
    if run["status"] == "RUNNING" and run["apify_run"]:
        try:
            call("POST", "/actor-runs/%s/abort" % run["apify_run"])
        except ApifyError as ex:
            return False, str(ex)
    _finish(run, "FAILED", 0, 0, run["cost"] or 0.0, "Stopped by you.")
    return True, "Run stopped."


def retry_run(rid):
    """Queue the same creators again for a run that failed or was refused."""
    run = get_run(rid)
    if run is None or run["status"] not in ("FAILED", "REFUSED") or not run["handle_map"]:
        return False, "Only a failed run that had creators can be retried."
    if paused():
        return False, "Apify is paused. Resume it first."
    with db.connect() as conn:
        conn.execute("INSERT INTO api_runs (job_id, job_name, trigger, status, handles, handle_map, started_at) "
                     "VALUES (?,?,?,?,?,?,?)", (run["job_id"], run["job_name"], "retry", "QUEUED", run["handles"],
                                               run["handle_map"], db.now()))
    pump()
    return True, "Queued again."


def runs_csv():
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "job", "trigger", "status", "creators", "results", "saved", "cost_usd", "started", "finished", "message"])
    with db.connect() as conn:
        for r in conn.execute("SELECT * FROM api_runs ORDER BY id DESC"):
            w.writerow([r["id"], r["job_name"], r["trigger"], r["status"], r["handles"], r["results"], r["saved"],
                        "%.4f" % r["cost"], time.strftime("%Y-%m-%d %H:%M", time.gmtime(r["started_at"])),
                        time.strftime("%Y-%m-%d %H:%M", time.gmtime(r["finished_at"])) if r["finished_at"] else "",
                        (r["message"] or "").replace("\n", " ")])
    return buf.getvalue()


# ---------------------------------------------------------------- scheduler --

def _due(job, t):
    if not job["enabled"] or job["schedule"] == "manual":
        return False
    local = time.gmtime(t + RIYADH)
    hh, mm = (int(x) for x in job["at_time"].split(":"))
    if job["schedule"] == "weekly" and local.tm_wday != job["weekday"]:
        return False
    slot = t - (local.tm_hour * 3600 + local.tm_min * 60 + local.tm_sec) + hh * 3600 + mm * 60
    if t < slot or (job["last_started"] or 0) >= slot:
        return False
    return _waited_since_last_try(job, t)


def _waited_since_last_try(job, t):
    """A job refused or thrown out before it reached Apify never gets last_started,
    so its slot stayed due and the minute-by-minute loop tried it again all day
    (2,183 refused rows on 2026-10-26). Hold a repeat attempt to one per
    RETRY_WAIT, which still picks the job up by itself once the budget is raised."""
    with db.connect() as conn:
        last = conn.execute("SELECT MAX(started_at) t FROM api_runs WHERE job_id = ?", (job["id"],)).fetchone()["t"]
    return not last or t - last >= RETRY_WAIT


def tick(t=None):
    t = t or db.now()
    if not get_token():
        return
    refresh_all()
    if paused():
        return
    for job in list_jobs():
        if _due(job, t):
            if job["kind"] == "post_urls" and not _post_pairs(job):
                continue                   # a campaign platform with no posts yet: nothing to read, nothing to log
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


# ----------------------------------------------------------- campaign capture --

def ensure_campaign_jobs(cid):
    """Give a campaign a daily capture job for each platform it has none for (the Jamjoom set). A platform that
    already has a job, even a paused or manual one, is left as the team set it. Returns the ids created."""
    src = "campaign:%d" % int(cid)
    with db.connect() as conn:
        k = conn.execute("SELECT name, client FROM campaigns WHERE id = ?", (int(cid),)).fetchone()
        if k is None:
            return []
        import comments
        if comments._is_sample(k):
            return []                   # the demo campaign holds dummy posts: nothing to capture (owner, 2026-10-20)
        have = {r["platform"] for r in conn.execute(
            "SELECT platform FROM api_jobs WHERE source = ? AND kind = 'post_urls'", (src,))}
    made = []
    for key, over in CAMPAIGN_CAPTURE:
        p = dict(PRESETS[key], **(over or {}))
        if p["platform"] in have:
            continue
        what = p["label"].split("·", 1)[-1].split("(")[0].strip()
        made.append(save_job({"name": "%s · %s" % ((k["name"] or "Campaign").strip(), what), "actor": p["actor"],
                              "kind": "post_urls", "platform": p["platform"], "source": src, "input": p["input"],
                              "max_handles": "50", "est_each": str(p["est"]), "schedule": "daily",
                              "at_time": CAMPAIGN_CAPTURE_AT, "weekday": "0"}))
    return made


def _on_campaign_status(cid, was, now_):
    if now_ == "live":
        ensure_campaign_jobs(cid)


db.on("campaign_status", _on_campaign_status)
