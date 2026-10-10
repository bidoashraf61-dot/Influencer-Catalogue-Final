"""Campaign jobs for the client's bell (HELVY Connect phase E).

1. **Weekly update.** Once a week per live campaign, one bell notification with a
   three-line verdict made from the campaign's own numbers against its targets and
   the benchmarks (metrics.report). Clicking opens the campaign report. No email,
   no PDF, no extra page.
2. **What to do next time.** When a campaign ends (marked Ended, or its end date has
   passed), the creators are sorted into rebook / replace / watch, deterministically
   from the same report: rank on results, engagement against the benchmark for their
   size, posts delivered against posts planned. Shown as the "Next time" panel on the
   campaign report, and one bell notification. Gemini may reword the summary only
   when the setting ``next_time_ai`` is on (off by default).

How it runs: ``start()`` (called from server.main, like the Apify scheduler) runs
``tick()`` 30 seconds after the admin service starts and then every hour. A tick is
idempotent: a week is recorded in ``campaign_weekly`` (campaign, week) before its
notification is sent, and the bell keeps one "camp_weekly" per ref, so restarts,
several ticks a day or two servers never send a week twice. The daily capture adds
the numbers; the next tick after a campaign-week boundary turns them into the update.
A week is counted from the campaign's start date (week 1 ends 7 days after it); a
campaign with no start date uses calendar (ISO) weeks. No posts yet means no update
that week (nothing to say), and it is tried again on the next tick.

    python3 admin/weekly.py          run one tick now (on the server: docker exec ... python3 admin/weekly.py)
"""
import datetime
import json
import math
import re
import threading
import time

import db

WEEK = 7 * 86400
INTERVAL = 3600
NEXT_WINDOW_DAYS = 21               # numbers keep landing for a while after the end: recompute until then

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign_weekly (
    campaign_id INTEGER NOT NULL,
    week TEXT NOT NULL,             -- '3' = third week since the start date, or '2026-W41'
    lines TEXT NOT NULL,            -- JSON: title + three lines, as sent
    at INTEGER NOT NULL,
    PRIMARY KEY (campaign_id, week)
);
CREATE TABLE IF NOT EXISTS campaign_next (
    campaign_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,             -- JSON: the rebook / replace / watch panel
    at INTEGER NOT NULL,
    notified_at INTEGER
);
"""

VERDICT_WORD = {"ahead": "targets reached", "good": "on track", "moderate": "close to target", "low": "behind target",
                "early": "getting started"}
KPI_NAME = {"views": "views", "reach": "reach", "engagement": "engagements", "er": "engagement rate", "clicks": "link clicks",
            "posts": "posts"}
_started = False


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)
    db.on("campaign_status", _on_status)


def _on_status(cid, was, now_):
    if now_ == "ended":
        try:
            next_time(db.campaign(cid), notify=True)
        except Exception:
            pass


# --------------------------------------------------------------- formatting --

def big(n):
    if n is None:
        return "0"
    n = float(n)
    a = abs(n)
    if a >= 1e6:
        return ("%.1fM" % (n / 1e6)).replace(".0M", "M")
    if a >= 1e4:
        return "%dK" % round(n / 1e3)
    if a >= 1e3:
        return ("%.1fK" % (n / 1e3)).replace(".0K", "K")
    return "{:,}".format(int(round(n)))


def _kpi(key, v):
    return ("%.1f%%" % v) if key == "er" else big(v)


# ------------------------------------------------------------- the verdict --

def verdict(k, r=None):
    """``{"title", "lines": [3 strings], "key"}`` for one campaign, or None when it has no posts yet."""
    import metrics
    r = r or metrics.report(k)
    t, prog = r["total"], r["progress"]
    if not t.get("posts"):
        return None
    v = r["verdict"]
    title = "%s: %s" % (k["name"], VERDICT_WORD.get(v["key"], v["label"].lower()))
    # 1. the campaign's main goal against its target, or what it has done so far
    items = {i["key"]: i for i in prog.get("items") or []}
    main = next((key for key in metrics.OBJECTIVE_KPIS.get(r["objective"]["key"], []) if key in items), None) \
        or next(iter(items), None)
    if main:
        i = items[main]
        due = (" (%d%% due by now)" % round(min(100.0, i["expected"] / i["goal"] * 100))) if main != "er" and i["goal"] else ""
        l1 = "%s %s of the %s goal: %d%%%s." % (KPI_NAME.get(main, main).capitalize(), _kpi(main, i["actual"]),
                                                _kpi(main, i["goal"]), round(i["pct"]), due)
    else:
        l1 = "%s views and %s engagements from %d post%s so far." % (big(t.get("views")), big(t.get("engagement")),
                                                                     t["posts"], "" if t["posts"] == 1 else "s")
    # 2. engagement against the benchmark
    bm = r["benchmarks"]
    word = {"good": "strong", "moderate": "fair", "low": "low"}
    if t.get("video_er") is not None:
        g = metrics.grade(t["video_er"], bm["video_er"])
        l2 = "Video engagement %.1f%%: %s against the %.1f%%+ benchmark." % (t["video_er"], word.get(g, "not graded"), bm["video_er"][0])
    elif t.get("er") is not None:
        g = t.get("er_grade")
        l2 = "Engagement rate %.1f%%: %s for these creators' size." % (t["er"], word.get(g, "not graded"))
    else:
        l2 = "%s engagements so far." % big(t.get("engagement"))
    # 3. delivery and the leader
    top = next((c for c in r["creators"] if c.get("rank") == 1), None)
    planned = t.get("planned")
    l3 = ("%d of %d posts live" % (t["posts"], planned)) if planned else ("%d post%s live" % (t["posts"], "" if t["posts"] == 1 else "s"))
    if top:
        l3 += "; leading: %s" % top["name"]
    return {"title": title[:200], "lines": [l1, l2, l3 + "."], "key": v["key"]}


def week_key(k, now=None):
    now = now or db.now()
    if k["starts_at"]:
        n = int((now - k["starts_at"]) // WEEK)
        return str(n) if n >= 1 else None
    y, w, _ = datetime.datetime.utcfromtimestamp(now).date().isocalendar()
    return "%d-W%02d" % (y, w)


def weekly(k, now=None):
    """Send this week's update for one campaign if it is due. Returns the week sent, or None."""
    import inbox
    now = now or db.now()
    if k is None or k["status"] != "live" or not k["code_id"]:
        return None
    if k["ends_at"] and now > k["ends_at"] + 86400:
        return None
    wk = week_key(k, now)
    if wk is None:
        return None
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM campaign_weekly WHERE campaign_id = ? AND week = ?", (k["id"], wk)).fetchone():
            return None
    v = verdict(k)
    if v is None:
        return None
    with db.connect() as conn:
        cur = conn.execute("INSERT OR IGNORE INTO campaign_weekly (campaign_id, week, lines, at) VALUES (?,?,?,?)",
                           (k["id"], wk, json.dumps(v), now))
        if not cur.rowcount:
            return None                          # another tick got there first
        label = ("Week %s" % wk) if wk.isdigit() else "This week"
        inbox.emit(inbox.for_codes([k["code_id"]]), "camp_weekly", v["title"], body="\n".join(v["lines"]),
                   href="campaign/#t=" + k["token"], ref="week:%d:%s" % (k["id"], wk), once=True,
                   meta={"week": wk, "label": label, "verdict": v["key"]}, conn=conn)
    return wk


# ------------------------------------------------------------ next time --

def ended(k, now=None):
    now = now or db.now()
    return k is not None and k["status"] != "draft" and (k["status"] == "ended" or bool(k["ends_at"] and k["ends_at"] < now))


def recommend(r):
    """Deterministic rebook / replace / watch from a metrics.report. Returns the panel's data."""
    import metrics
    bm = r["benchmarks"]
    people = r["creators"]
    ranked = [c for c in people if c.get("posts")]
    n = len(ranked)
    third = max(1, int(math.ceil(n / 3.0))) if n else 0
    out = {"rebook": [], "replace": [], "watch": []}
    for c in people:
        posts, planned = c.get("posts") or 0, c.get("planned") or 0
        video = c.get("video_er") is not None
        rate = c.get("video_er") if video else c.get("er")
        grade = c.get("video_er_grade") if video else c.get("er_grade")
        pair = bm["video_er"] if video else bm["er"].get(c.get("band") or "micro", bm["er"]["micro"])
        why = []
        if posts and c.get("rank"):
            why.append("#%d of %d on results" % (c["rank"], n))
        if rate is not None:
            why.append("%s %.1f%% (strong from %.1f%%)" % ("video engagement" if video else "engagement rate", rate, pair[0]))
        short = planned and posts < planned
        if planned:
            why.append("delivered %d of %d post%s" % (posts, planned, "" if planned == 1 else "s"))
        top = bool(posts and c.get("rank") and c["rank"] <= third)
        bottom = bool(posts and c.get("rank") and n >= 3 and c["rank"] > n - third)
        if not posts and planned:
            bucket, lead = "replace", "No posts delivered"
        elif planned and posts < planned * 0.5:
            bucket, lead = "replace", "Delivered under half of the posts booked"
        elif grade == "low" and (bottom or n < 3):
            bucket, lead = "replace", "Engagement below the benchmark for their size"
        elif posts and (grade == "good" or (top and grade != "low")) and not short:
            bucket, lead = "rebook", "Top results" if top else "Strong engagement"
        elif not posts:
            continue                                 # nothing booked and nothing posted: not part of the verdict
        else:
            bucket, lead = "watch", "Mixed results"
        out[bucket].append({"code": c["code"], "name": c["name"], "rank": c.get("rank"), "score": c.get("score"),
                            "lead": lead, "why": why[:3], "grade": grade})
    for k in out:
        out[k].sort(key=lambda x: (x["rank"] is None, x["rank"] or 0))
    # Who could take a replaced creator's place: creators like the best rebook.
    out["instead"] = []
    if out["replace"] and out["rebook"]:
        import discover
        inside = {c["code"] for c in people}
        try:
            out["instead"] = [x for x in discover.like(out["rebook"][0]["code"], limit=24) if x not in inside][:3]
        except Exception:
            out["instead"] = []
        out["instead_like"] = out["rebook"][0]["name"]
    parts = []
    if out["rebook"]:
        parts.append("book %s again" % _names(out["rebook"]))
    if out["replace"]:
        parts.append("replace %s" % _names(out["replace"]))
    if out["watch"]:
        parts.append("give %s one more test" % _names(out["watch"]))
    s = "; ".join(parts) or "Not enough results to recommend anyone yet"
    out["summary"] = (s[:1].upper() + s[1:] + ".")[:400]
    out["counts"] = {k: len(out[k]) for k in ("rebook", "replace", "watch")}
    return out


def _names(items):
    names = [i["name"] for i in items[:3]]
    more = len(items) - len(names)
    s = ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1]
    return s + (" (+%d more)" % more if more > 0 else "")


def _ai_summary(k, data):
    """Optional friendlier wording (setting next_time_ai). Never changes who is in which group."""
    if not db.setting("next_time_ai", False):
        return None
    import gemini
    if not gemini.configured():
        return None
    try:
        facts = {g: [{"name": x["name"], "lead": x["lead"], "why": x["why"]} for x in data[g]] for g in ("rebook", "replace", "watch")}
        out = gemini.generate("Campaign '%s' ended. Groups: %s" % (k["name"], json.dumps(facts, ensure_ascii=False)),
                              system="Write one or two plain sentences (under 45 words) telling the client whom to book again and "
                                     "whom to replace next time, and why, using only these facts. Never mention prices, fees or costs.",
                              temperature=0.3, max_tokens=200, kind="next_time")
        text = " ".join(out["text"].split())[:400]
        return text if text and not re.search(r"SAR|\$|price|fee|cost|ريال", text, re.I) else None
    except Exception:
        return None


def next_time(k, notify=True, now=None):
    """Compute (or refresh) the Next time panel for an ended campaign; ring the bell once.
    Returns the panel's data, or None when the campaign has not ended or has no results."""
    import inbox
    import metrics
    now = now or db.now()
    if not ended(k, now):
        return None
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM campaign_next WHERE campaign_id = ?", (k["id"],)).fetchone()
    end = k["ends_at"] or now
    if row is not None and now > end + NEXT_WINDOW_DAYS * 86400:
        return json.loads(row["data"])               # settled: keep what the client was shown
    r = metrics.report(k)
    if not r["total"].get("posts"):
        return None
    data = recommend(r)
    data["ai_summary"] = _ai_summary(k, data) if row is None else (json.loads(row["data"]).get("ai_summary"))
    data["at"] = now
    with db.connect() as conn:
        conn.execute("INSERT INTO campaign_next (campaign_id, data, at) VALUES (?,?,?) "
                     "ON CONFLICT(campaign_id) DO UPDATE SET data = excluded.data, at = excluded.at",
                     (k["id"], json.dumps(data, ensure_ascii=False), now))
        sent = conn.execute("SELECT notified_at FROM campaign_next WHERE campaign_id = ?", (k["id"],)).fetchone()["notified_at"]
        if notify and not sent and k["code_id"]:
            c = data["counts"]
            body = "Rebook %d, replace %d%s. Open the report for who and why." % (
                c["rebook"], c["replace"], (", test again %d" % c["watch"]) if c["watch"] else "")
            inbox.emit(inbox.for_codes([k["code_id"]]), "camp_next", "What to do next time:", rest=" " + k["name"], body=body,
                       href="campaign/#t=" + k["token"], ref="next:%d" % k["id"], once=True, conn=conn)
            conn.execute("UPDATE campaign_next SET notified_at = ? WHERE campaign_id = ?", (now, k["id"]))
    return data


def panel(k):
    """What the campaign report shows: the stored panel (computed on demand once ended)."""
    if not ended(k):
        return None
    with db.connect() as conn:
        row = conn.execute("SELECT data FROM campaign_next WHERE campaign_id = ?", (k["id"],)).fetchone()
    if row is not None:
        return json.loads(row["data"])
    return next_time(k, notify=True)


# --------------------------------------------------------------- the job --

def tick(now=None):
    """One pass over every campaign. Safe to run any number of times."""
    now = now or db.now()
    sent, nexts = 0, 0
    for k in db.list_campaigns():
        try:
            if weekly(k, now):
                sent += 1
            if ended(k, now) and (not k["ends_at"] or now <= k["ends_at"] + NEXT_WINDOW_DAYS * 86400):
                if next_time(k, notify=True, now=now) is not None:
                    nexts += 1
        except Exception as ex:                    # one bad campaign must not stop the rest
            print("weekly: campaign %s: %s %s" % (k["id"], type(ex).__name__, ex), flush=True)
    db.set_setting("weekly_last_tick", now)
    return {"weekly": sent, "next_time": nexts}


def _loop():
    time.sleep(30)
    while True:
        try:
            tick()
        except Exception as ex:
            print("weekly:", type(ex).__name__, ex, flush=True)
        time.sleep(INTERVAL)


def start():
    global _started
    if _started:
        return
    _started = True
    init()
    threading.Thread(target=_loop, name="campaign-weekly", daemon=True).start()


if __name__ == "__main__":
    db.init()
    import portal
    portal.init()
    init()
    print(tick())
