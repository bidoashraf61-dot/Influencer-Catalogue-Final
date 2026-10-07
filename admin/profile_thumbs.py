"""Pictures for the popular posts on a basic profile record.

A post's picture link read off Instagram or TikTok expires within days, so each
one is fetched once and kept on this server (admin/analysis_media/<CODE>/, client
data, not in git). The record's post then points at it as "media:<name>", which
the creator page loads through /api/creator-media for a viewer with a passcode.

It reuses thumbs.py, the fetcher the campaign reports use (Instagram's own
picture address, TikTok's oEmbed thumbnail, then the page's og:image), so it
needs no Apify credit and no login. One picture a second, one record at a time,
backing off when the platforms start refusing.
"""
import hashlib
import json
import threading
import time

import analysis
import db
import thumbs

PAUSE = 1.0            # seconds between pictures
MAX_FAILS = 5          # creators in a row with no picture at all: back off
BACKOFF = 600          # seconds
MAX_KEEP = 6           # pictures kept per record


def _save(code, data, kind):
    d = analysis.MEDIA / code
    d.mkdir(parents=True, exist_ok=True)
    name = "post-%s.%s" % (hashlib.sha1(data).hexdigest()[:12], kind)
    (d / name).write_bytes(data)
    return "media:" + name


def fetch_one(code, url, platform):
    """Fetch and keep one post's picture. Returns its media reference or None."""
    for cand in thumbs.candidates(url, platform):
        got = thumbs._image(cand)
        if got:
            return _save(code, got[0], got[1])
    return None


def next_rows(limit=3):
    with db.connect() as conn:
        return conn.execute(
            "SELECT code, platform FROM creator_analysis WHERE source = 'Apify basic' "
            "AND data LIKE '%\"top_posts\"%' AND data NOT LIKE '%\"thumbs_done\"%' LIMIT ?", (limit,)).fetchall()


def process(code, platform):
    """Fetch the missing pictures for one record. Returns how many were stored."""
    with db.connect() as conn:
        row = conn.execute("SELECT data FROM creator_analysis WHERE code = ? AND platform = ?", (code, platform)).fetchone()
    if row is None:
        return 0
    data = json.loads(row["data"])
    got = {}
    for p in (data.get("top_posts") or [])[:MAX_KEEP]:
        if p.get("thumb") or not p.get("url"):
            continue
        ref = fetch_one(code, p["url"], platform)
        if ref:
            got[p["url"]] = ref
        time.sleep(PAUSE)
    # re-read before writing, so nothing saved meanwhile is lost
    with db.connect() as conn:
        fresh = conn.execute("SELECT data, source FROM creator_analysis WHERE code = ? AND platform = ?", (code, platform)).fetchone()
        if fresh is None or fresh["source"] != "Apify basic":
            return 0
        d = json.loads(fresh["data"])
        for p in d.get("top_posts") or []:
            if p.get("url") in got:
                p["thumb"] = got[p["url"]]
        d["thumbs_done"] = True
        conn.execute("UPDATE creator_analysis SET data = ? WHERE code = ? AND platform = ? AND source = 'Apify basic'",
                     (json.dumps(d), code, platform))
    return len(got)


def stats():
    """(records finished, records with posts, pictures stored)"""
    done = total = pics = 0
    with db.connect() as conn:
        for r in conn.execute("SELECT data FROM creator_analysis WHERE source = 'Apify basic' AND data LIKE '%\"top_posts\"%'"):
            total += 1
            if '"thumbs_done"' in r["data"]:
                done += 1
            pics += r["data"].count('"media:post-')
    return done, total, pics


def _loop():
    fails = 0
    while True:
        try:
            if not db.setting("thumbs_backfill", True):
                time.sleep(300)
                continue
            rows = next_rows()
            if not rows:
                time.sleep(300)
                continue
            for r in rows:
                n = process(r["code"], r["platform"])
                fails = 0 if n else fails + 1
            if fails >= MAX_FAILS:
                time.sleep(BACKOFF)
                fails = 0
        except Exception as ex:           # a bad record must never stop the worker
            print("profile thumbs:", type(ex).__name__, ex, flush=True)
            time.sleep(30)


def start():
    threading.Thread(target=_loop, name="profile-thumbs", daemon=True).start()
