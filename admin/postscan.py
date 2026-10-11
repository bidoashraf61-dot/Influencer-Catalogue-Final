"""Post-level scan (2026-10-11): the last 25 posts per creator, kept as an overlay on the analysis.

Scoring needs median views, the views series (consistency), per-post hashtags (interest) and an
engagement figure from more than 12 posts. This module runs the two agreed actors and keeps what
they return in ``post_samples`` (one row per creator and platform). ``db.analyses_for`` lays that
row over the analysis, so a verified analysis keeps its audience and fake-follower numbers and
gains the post numbers; nothing in ``creator_analysis`` is rewritten.

    sones/instagram-posts-scraper-lowcost      $0.0003 per post + $0.005 per run
    maximedupre/tiktok-creator-analytics       $0.00001 per creator

Every run carries a maxTotalChargeUsd, so Apify itself stops it at the cap."""
import json
import re
import time
from datetime import datetime, timezone

import apify
import db

IG_ACTOR = "sones~instagram-posts-scraper-lowcost"
TT_ACTOR = "maximedupre~tiktok-creator-analytics"
POSTS = 25
RECENT_DAYS = 90
KEYS = ("er", "er_basis", "sample_posts", "median_views", "views_p25", "views_p75", "views_spread", "views_series",
        "avg_views", "avg_reel_plays", "median_likes", "median_comments", "median_shares", "median_er_on_views",
        "hashtags", "posts_per_week", "last_post")

SCHEMA = """CREATE TABLE IF NOT EXISTS post_samples (
  code TEXT NOT NULL, platform TEXT NOT NULL, handle TEXT, at INTEGER NOT NULL, run_id TEXT,
  data TEXT NOT NULL, PRIMARY KEY (code, platform))"""


def init(conn):
    conn.execute(SCHEMA)


# -------------------------------------------------------------------- derive --

def _day(ts):
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return None


def derive_instagram(items, followers=None):
    """Numbers for one creator from their posts (the actor's items, newest first)."""
    posts = [p for p in items if isinstance(p, dict)]
    now = time.time()
    recent = [p for p in posts if p.get("taken_at") and now - float(p["taken_at"]) <= RECENT_DAYS * 86400]
    use = recent if len(recent) >= 10 else posts          # under 10 recent posts: take what we have
    use = use[:POSTS]
    rows, tags, stamps = [], [], []
    for p in use:
        likes = p.get("like_count")
        likes = likes if isinstance(likes, (int, float)) and likes >= 0 else None     # -1 = hidden
        com = p.get("comment_count")
        com = com if isinstance(com, (int, float)) and com >= 0 else None
        plays = p.get("play_count")
        is_video = p.get("media_type") == 2 or p.get("product_type") in ("clips", "igtv")
        rows.append({"views": plays if is_video and isinstance(plays, (int, float)) and plays > 0 else None,
                     "likes": likes, "comments": com})
        text = ((p.get("caption") or {}).get("text") or "") if isinstance(p.get("caption"), dict) else ""
        tags.append((apify._TAG.findall(text), apify._MEN.findall(text)))
        if p.get("taken_at"):
            stamps.append(float(p["taken_at"]))
    out = {"sample_posts": len(use)}
    if not use:
        return out
    out.update(apify.post_stats(rows))
    out["sample_posts"] = len(use)
    lk = [r["likes"] for r in rows if r["likes"] is not None]
    cm = [r["comments"] for r in rows if r["comments"] is not None]
    if followers and lk:
        out["er"] = round((sum(lk) / len(lk) + (sum(cm) / len(cm) if cm else 0)) * 100.0 / followers, 3)
    vids = [r["views"] for r in rows if r["views"]]
    if vids:
        out["avg_reel_plays"] = round(sum(vids) / float(len(vids)))
    out["hashtags"] = apify.tags_from_posts(tags)
    if len(stamps) > 1 and max(stamps) > min(stamps):
        out["posts_per_week"] = round((len(stamps) - 1) * 7 * 86400.0 / (max(stamps) - min(stamps)), 2)
    if stamps:
        out["last_post"] = _day(max(stamps))
    return {k: v for k, v in out.items() if v not in (None, [], "")}


def derive_tiktok(it):
    m = apify.derive_tiktok_analytics(it)
    out = {k: m[k] for k in KEYS if m.get(k) not in (None, [], "")}
    if m.get("er_pct") is not None:
        out["er"] = m["er_pct"]
    out["er_basis"] = "views"
    return out, m.get("followers")


# ----------------------------------------------------------------- the store --

def save(code, platform, handle, data, run_id):
    clean = {k: v for k, v in data.items() if k in KEYS and v not in (None, [], "")}
    if not clean:
        return False
    with db.connect() as conn:
        init(conn)
        conn.execute("INSERT OR REPLACE INTO post_samples (code, platform, handle, at, run_id, data) VALUES (?,?,?,?,?,?)",
                     (code, platform, handle, db.now(), run_id, json.dumps(clean)))
    return True


def overlay_rows(conn, codes):
    """{(code, platform): data} for many creators, or {} before the first scan."""
    out = {}
    try:
        init(conn)
        for i in range(0, len(codes), 400):
            part = codes[i:i + 400]
            for r in conn.execute("SELECT code, platform, data FROM post_samples WHERE code IN (%s)" % ",".join("?" * len(part)), part):
                try:
                    out[(r["code"], r["platform"])] = json.loads(r["data"])
                except ValueError:
                    pass
    except Exception:
        return {}
    return out


# ------------------------------------------------------------------- running --

def _run(actor, body, cap_usd, wait_s=900):
    d = apify.call("POST", "/acts/%s/runs" % actor, body, params={"maxTotalChargeUsd": "%.2f" % cap_usd})["data"]
    rid, t0 = d["id"], time.time()
    while time.time() - t0 < wait_s:
        time.sleep(5)
        d = apify.call("GET", "/actor-runs/" + rid)["data"]
        if d.get("status") in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break
    items = []
    # A run that ends FAILED because one handle was not found still holds the others' results.
    if d.get("defaultDatasetId"):
        got = apify.call("GET", "/datasets/%s/items" % d["defaultDatasetId"], params={"clean": "true", "limit": "5000"})
        items = got if isinstance(got, list) else []
    return d, items


def scan(codes, platforms=("Instagram", "TikTok"), cap_usd=1.0):
    """Run the actors for the creators' handles and keep the numbers. Returns a summary."""
    rows = {c["code"]: c for c in db.creators_by_codes(list(codes))}
    docs = db.analyses_for(list(codes))
    summary = {"cost": 0.0, "saved": [], "missing": [], "runs": []}
    by_plat = {pl: {} for pl in platforms}
    for code, c in rows.items():
        for pl, h in apify.creator_handles(c).items():
            if pl in by_plat:
                by_plat[pl][code] = h
    if "Instagram" in by_plat and by_plat["Instagram"]:
        hm = {h.lower(): code for code, h in by_plat["Instagram"].items()}
        d, items = _run(IG_ACTOR, {"usernames": sorted(set(by_plat["Instagram"].values())), "postsPerProfile": POSTS,
                                   "maxRetries": 3}, cap_usd)
        summary["runs"].append({"actor": IG_ACTOR, "status": d.get("status"), "cost": d.get("usageTotalUsd"), "items": len(items)})
        summary["cost"] += float(d.get("usageTotalUsd") or 0)
        grouped = {}
        for p in items:
            u = str(p.get("scraped_username") or (p.get("user") or {}).get("username") or "").lower()
            if u in hm:
                grouped.setdefault(u, []).append(p)
        for u, ps in grouped.items():
            ps.sort(key=lambda p: -(p.get("taken_at") or 0))
            code = hm[u]
            fol = ((docs.get(code) or {}).get("Instagram") or {}).get("data", {}).get("followers") or rows[code]["followers"]
            if save(code, "Instagram", u, derive_instagram(ps, fol), d.get("id")):
                summary["saved"].append((code, "Instagram", len(ps)))
        summary["missing"] += [(c, "Instagram") for c, h in by_plat["Instagram"].items() if h.lower() not in grouped]
    if "TikTok" in by_plat and by_plat["TikTok"]:
        hm = {h.lower(): code for code, h in by_plat["TikTok"].items()}
        d, items = _run(TT_ACTOR, {"target": "handles", "creatorHandles": ["@" + h for h in by_plat["TikTok"].values()],
                                   "postSampleSize": POSTS}, cap_usd)
        summary["runs"].append({"actor": TT_ACTOR, "status": d.get("status"), "cost": d.get("usageTotalUsd"), "items": len(items)})
        summary["cost"] += float(d.get("usageTotalUsd") or 0)
        seen = set()
        for it in items:
            h = str(((it.get("creator") or {}).get("handle")) or "").lstrip("@").lower()
            if h in hm:
                data, _ = derive_tiktok(it)
                if save(hm[h], "TikTok", h, data, d.get("id")):
                    summary["saved"].append((hm[h], "TikTok", data.get("sample_posts")))
                    seen.add(h)
        summary["missing"] += [(c, "TikTok") for c, h in by_plat["TikTok"].items() if h.lower() not in seen]
    return summary
