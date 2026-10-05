"""Campaign KPIs: one place where every number on a campaign report is worked
out, so the dashboard, the client's page and the exports cannot disagree.

Definitions (also in docs/CAMPAIGN-TRACKER-BRIEF.md §11):

  engagement          likes + comments
  est. reach, post    engagement × REACH_PER_ENGAGEMENT, capped at followers
  est. reach, story   followers × STORY_VIEW_RATE
  est. impressions    post: est. reach × 1.5 · story: = est. reach
  video               views are counted as views, not as impressions
  real values         an approved insight's reach / impressions / views
                      replace the estimates for that post
  ER%                 engagement ÷ followers, averaged over posts whose likes
                      are visible (stories excluded)
  Video ER%           engagement ÷ views, over videos
  Impressions ER%     engagement ÷ impressions, over non-video posts
  EMV                 Σ count × SAR multiplier, per action and platform
  CPM (internal)      cost ÷ (impressions + views) × 1,000
  CTR                 clicks ÷ (impressions + views)

Estimates are labelled as such everywhere they are shown. The factors are
settings, not constants, so they can be tuned without a deploy.
"""

import json

import db

DEFAULT_FACTORS = {"reach_per_engagement": 10.0, "story_view_rate": 0.05,
                   "impressions_per_reach": 1.5}
EMV_ACTIONS = ["impressions", "views", "likes", "comments", "shares", "saves", "clicks"]


# ------------------------------------------------------------- benchmarks --
#
# Industry guide ranges, editable in Settings. Each is (good_from, ok_from):
# at or above the first is "good", at or above the second "moderate", below
# it "low". They are guides, labelled as such on the report — never claimed
# as HelloVoice results.

BANDS = [("nano", 0, 10000), ("micro", 10000, 50000), ("mid", 50000, 500000),
         ("macro", 500000, 1000000), ("mega", 1000000, None)]
BAND_LABEL = {"nano": "Nano (<10K)", "micro": "Micro (10–50K)", "mid": "Mid (50–500K)",
              "macro": "Macro (500K–1M)", "mega": "Mega (1M+)"}

DEFAULT_BENCHMARKS = {
    # engagement ÷ followers, % — feed posts, by follower band
    "er": {"nano": [4.0, 2.0], "micro": [3.0, 1.5], "mid": [2.0, 1.0],
           "macro": [1.5, 0.8], "mega": [1.0, 0.5]},
    # engagement ÷ views, % — reels, TikToks, videos
    "video_er": [6.0, 3.0],
    # views ÷ followers, % — how far a video travelled
    "view_rate": [30.0, 10.0],
    # story reach ÷ followers, %
    "story_rate": [8.0, 4.0],
    # clicks ÷ (impressions + views), %
    "ctr": [1.0, 0.3],
}


def band_of(followers):
    f = followers or 0
    for name, lo, hi in BANDS:
        if f >= lo and (hi is None or f < hi):
            return name
    return "nano"


def benchmarks():
    got = db.setting("benchmarks") or {}
    out = json.loads(json.dumps(DEFAULT_BENCHMARKS))
    for k, v in got.items():
        if k == "er" and isinstance(v, dict):
            for b, pair in v.items():
                if b in out["er"] and isinstance(pair, list) and len(pair) == 2:
                    out["er"][b] = [float(pair[0]), float(pair[1])]
        elif k in out and isinstance(v, list) and len(v) == 2:
            out[k] = [float(v[0]), float(v[1])]
    return out


def grade(value, pair):
    """'good' | 'moderate' | 'low' | None against a (good_from, ok_from) pair."""
    if value is None or not pair:
        return None
    if value >= pair[0]:
        return "good"
    if value >= pair[1]:
        return "moderate"
    return "low"


def factors():
    got = db.setting("reach_factors") or {}
    return {k: float(got.get(k, v)) for k, v in DEFAULT_FACTORS.items()}


def emv_rates(campaign):
    """{platform or "*": {action: SAR}}. The campaign's own override, else the
    workspace defaults. Empty = EMV not set up, and it is not shown."""
    own = None
    if campaign["emv"] if "emv" in campaign.keys() else None:
        try:
            own = json.loads(campaign["emv"])
        except ValueError:
            own = None
    rates = own if own else (db.setting("emv_rates") or {})
    return {p: {a: float(v) for a, v in (r or {}).items() if a in EMV_ACTIONS and v}
            for p, r in rates.items() if r}


def _rate(rates, platform, action):
    for key in (platform, "*"):
        if key in rates and action in rates[key]:
            return rates[key][action]
    return 0.0


def visibility(campaign):
    """What the client's report shows. All on unless switched off."""
    keys = {"clicks": True, "emv": True, "all_content": False, "reach": True}
    try:
        got = json.loads(campaign["visibility"] or "{}") if "visibility" in campaign.keys() else {}
    except ValueError:
        got = {}
    return {k: bool(got.get(k, v)) for k, v in keys.items()}


def post_numbers(c, f):
    """Every derived number for one piece of content."""
    likes, comments = c.get("likes"), c.get("comments")
    ins = c.get("insights") or {}
    if ins.get("likes") is not None:
        likes = ins["likes"]
    if ins.get("comments") is not None:
        comments = ins["comments"]
    eng = (likes or 0) + (comments or 0)
    video = c["kind"] in db.VIDEO_KINDS
    story = c["kind"] == "story"
    followers = c.get("followers") or 0
    views = ins.get("views", c.get("views"))
    out = {"likes": likes, "comments": comments, "engagement": eng, "views": views or 0,
           "shares": ins.get("shares", c.get("shares")), "saves": ins.get("saves", c.get("saves")),
           "video": video, "story": story, "real": bool(ins)}

    if video:
        out["reach"] = ins.get("reach") or (views or 0)
        out["impressions"] = 0           # video exposure is counted as views
        out["reach_real"] = "reach" in ins
    else:
        if story:
            est = followers * f["story_view_rate"]
            if views:                    # a story's own view count, if read
                est = views
        else:
            est = min(eng * f["reach_per_engagement"], followers) if followers else \
                eng * f["reach_per_engagement"]
        out["reach"] = int(ins["reach"]) if "reach" in ins else int(round(est))
        out["reach_real"] = "reach" in ins
        imp = ins.get("impressions")
        if imp is None:
            imp = out["reach"] if story else out["reach"] * f["impressions_per_reach"]
        out["impressions"] = int(round(imp))
        if story:
            out["views"] = 0             # folded into impressions, not double-counted
    out["impressions_real"] = "impressions" in ins
    out["er"] = (eng / float(followers) * 100) if (followers and likes is not None
                                                   and not story) else None
    out["video_er"] = (eng / float(views) * 100) if (video and views) else None
    out["imp_er"] = (eng / float(out["impressions"]) * 100) if (
        not video and not story and out["impressions"]) else None
    out["view_rate"] = (views / float(followers) * 100) if (video and views and followers) else None
    out["story_rate"] = (out["reach"] / float(followers) * 100) if (story and followers) else None
    return out


def post_health(n, followers, bm):
    """The one signal a post card shows, with the benchmark it was judged by."""
    if n["story"]:
        pair = bm["story_rate"]
        return {"metric": "Story reach rate", "value": n["story_rate"], "grade": grade(n["story_rate"], pair),
                "benchmark": pair}
    if n["video"]:
        g1, g2 = grade(n["video_er"], bm["video_er"]), grade(n["view_rate"], bm["view_rate"])
        order = {"good": 2, "moderate": 1, "low": 0}
        best = max([g for g in (g1, g2) if g] or [None], key=lambda g: order.get(g, -1)) if (g1 or g2) else None
        return {"metric": "Video ER", "value": n["video_er"], "grade": best, "benchmark": bm["video_er"],
                "view_rate": n["view_rate"], "view_grade": g2}
    pair = bm["er"][band_of(followers)]
    return {"metric": "ER", "value": n["er"], "grade": grade(n["er"], pair), "benchmark": pair,
            "band": band_of(followers)}


def _avg(values):
    vals = [v for v in values if v is not None]
    return (sum(vals) / len(vals)) if vals else None


def report(campaign, internal=False):
    """The whole report for one campaign as plain data. `internal` adds cost,
    CPM and cost per click — never set for the client's page."""
    cid = campaign["id"]
    f = factors()
    rates = emv_rates(campaign)
    vis = visibility(campaign)
    members = db.campaign_creators(cid)
    clicks = db.click_stats(cid)
    clicks_by = {r["k"]: r["n"] for r in clicks["by_creator"]}
    content = [c for c in db.campaign_content(cid) if not c["hidden"]]

    bm = benchmarks()
    posts = []
    for c in content:
        n = post_numbers(c, f)
        n["health"] = post_health(n, c.get("followers"), bm)
        emv = 0.0
        for action in ("impressions", "views", "likes", "comments", "shares", "saves"):
            emv += (n.get(action) or 0) * _rate(rates, c["platform"], action)
        n["emv"] = emv
        posts.append({**c, **n})

    camp = [p for p in posts if p["section"] == "campaign"]

    def totals(items, extra_clicks=0):
        t = {k: sum((p.get(k) or 0) for p in items)
             for k in ("likes", "comments", "engagement", "views", "reach", "impressions",
                       "shares", "saves", "emv")}
        t["posts"] = len(items)
        t["clicks"] = extra_clicks
        t["er"] = _avg(p["er"] for p in items)
        t["video_er"] = _avg(p["video_er"] for p in items)
        t["imp_er"] = _avg(p["imp_er"] for p in items)
        exposure = t["impressions"] + t["views"]
        t["exposure"] = exposure
        t["ctr"] = (extra_clicks / float(exposure) * 100) if exposure else None
        t["real_share"] = (sum(1 for p in items if p["real"]) / float(len(items))) if items else 0
        return t

    total = totals(camp, clicks["clicks"])
    if rates:
        total["emv"] += clicks["clicks"] * _rate(rates, "*", "clicks")
    else:
        total["emv"] = None

    cost_total = campaign["cost"]
    if cost_total is None:
        fees = [m["campaign_cost"] for m in members if m["campaign_cost"] is not None]
        cost_total = sum(fees) if fees else None

    creators = []
    for m in members:
        code = m["cc_code"]
        mine = [p for p in camp if p["code"] == code]
        t = totals(mine, clicks_by.get(code, 0))
        if not rates:
            t["emv"] = None
        delivered = len(mine)
        followers = m["followers"]
        row = {"code": code, "name": m["name"] or code, "photo": m["photo"],
               "followers": followers, "planned": m["planned"], "delivered": delivered,
               "profiles": db.split_profiles(m["profiles"]) if m["code"] else [],
               "band": band_of(followers), **t}
        row["er_grade"] = grade(t["er"], bm["er"][band_of(followers)]) if t["er"] is not None else None
        row["video_er_grade"] = grade(t["video_er"], bm["video_er"])
        if internal:
            row["cost"] = m["campaign_cost"]
            row["cpm"] = (m["campaign_cost"] / float(t["exposure"]) * 1000
                          if m["campaign_cost"] and t["exposure"] else None)
            row["cpc"] = (m["campaign_cost"] / float(t["clicks"])
                          if m["campaign_cost"] and t["clicks"] else None)
        creators.append(row)

    scoreboard(creators, bm)
    targets = db.campaign_targets(campaign)
    progress = target_progress(campaign, total, targets)
    planned = sum(c["planned"] or 0 for c in creators)
    total["planned"] = planned or None
    total["delivered"] = total["posts"]
    total["er_grade"] = _avg_grade([c["er_grade"] for c in creators if c["posts"]])
    total["ctr_grade"] = grade(total["ctr"], bm["ctr"])
    total["video_er_grade"] = grade(total["video_er"], bm["video_er"])
    verdict = overall_verdict(progress, total)

    out = {"campaign": {"id": cid, "name": campaign["name"], "client": campaign["client"],
                        "status": campaign["status"], "starts_at": campaign["starts_at"],
                        "ends_at": campaign["ends_at"], "platform": campaign["platform"]},
           "total": total, "creators": creators, "posts": posts,
           "history": db.content_history(cid), "clicks": clicks,
           "emv_set": bool(rates), "visibility": vis, "factors": f,
           "benchmarks": bm, "targets": targets, "progress": progress, "verdict": verdict,
           "updated_at": max([p["metrics_at"] or 0 for p in posts] + [0]) or None}
    if internal:
        exposure = total["exposure"]
        out["internal"] = {
            "cost": cost_total,
            "cpm": (cost_total / float(exposure) * 1000) if cost_total and exposure else None,
            "cpe": (cost_total / float(total["engagement"])) if cost_total and total["engagement"] else None,
            "cpc": (cost_total / float(clicks["clicks"])) if cost_total and clicks["clicks"] else None,
        }
    return out


def _avg_grade(grades):
    pts = {"good": 2, "moderate": 1, "low": 0}
    vals = [pts[g] for g in grades if g in pts]
    if not vals:
        return None
    avg = sum(vals) / float(len(vals))
    return "good" if avg >= 1.5 else ("moderate" if avg >= 0.75 else "low")


def scoreboard(creators, bm):
    """A 0–100 score per creator, so the leaderboard ranks results rather
    than audience size alone:

      35%  exposure (views + reach) against the best in the campaign
      25%  engagement against the best in the campaign
      25%  engagement rate against the creator's own tier benchmark
           (meeting the "good" mark = full points, capped)
      15%  link clicks against the best in the campaign

    Creators with no counted posts score 0 and are ranked last."""
    def peak(key):
        return max([c[key] or 0 for c in creators] + [0]) or 1
    pe = max([(c["views"] or 0) + (c["reach"] or 0) for c in creators] + [0]) or 1
    pg, pc = peak("engagement"), peak("clicks")
    for c in creators:
        if not c["posts"]:
            c["score"] = 0.0
            continue
        rate = c["er"] if c["er"] is not None else c["video_er"]
        target = bm["er"][c["band"]][0] if c["er"] is not None else bm["video_er"][0]
        quality = min(1.0, (rate or 0) / target) if target else 0
        c["score"] = round(100 * (0.35 * ((c["views"] or 0) + (c["reach"] or 0)) / pe
                                  + 0.25 * (c["engagement"] or 0) / pg
                                  + 0.25 * quality
                                  + 0.15 * (c["clicks"] or 0) / pc), 1)
    ranked = sorted(creators, key=lambda c: (-c["score"], c["name"]))
    for i, c in enumerate(ranked):
        c["rank"] = i + 1 if c["posts"] else None
        c["badge"] = {1: "gold", 2: "silver", 3: "bronze"}.get(i + 1) if c["posts"] else None
    creators.sort(key=lambda c: (c["rank"] is None, c["rank"] or 0))


def target_progress(campaign, total, targets):
    """Each target against what is done, and against where the campaign
    should be by now (straight-line through its dates), graded."""
    start, end = campaign["starts_at"], campaign["ends_at"]
    now = db.now()
    if start and end and end > start:
        elapsed = max(0.0, min(1.0, (now - start) / float(end - start)))
    else:
        elapsed = 1.0
    actual = {"posts": total["posts"], "views": total["views"], "reach": total["reach"],
              "engagement": total["engagement"], "er": total["er"], "clicks": total["clicks"]}
    out = []
    for key, goal in targets.items():
        got = actual.get(key) or 0
        if key == "er":                       # a rate is judged as is, not pro-rata
            expected = goal
        else:
            expected = goal * max(elapsed, 0.15)   # the first days are not judged as failure
        ratio = got / float(expected) if expected else 0
        out.append({"key": key, "goal": goal, "actual": got, "pct": got / float(goal) * 100 if goal else 0,
                    "expected": expected,
                    "grade": "good" if ratio >= 1 else ("moderate" if ratio >= 0.7 else "low")})
    return {"elapsed": elapsed, "items": out}


def overall_verdict(progress, total):
    """One word for the whole campaign: Ahead / On track / Behind / Too early."""
    items = progress["items"]
    if not total["posts"] and progress["elapsed"] < 0.25:
        return {"key": "early", "label": "Getting started", "grade": None}
    grades = [i["grade"] for i in items] or [g for g in (total.get("er_grade"), total.get("video_er_grade")) if g]
    g = _avg_grade(grades)
    if g is None:
        return {"key": "early", "label": "Getting started", "grade": None}
    if items and all(i["actual"] >= i["goal"] for i in items):
        return {"key": "ahead", "label": "Targets reached", "grade": "good"}
    return {"key": g, "label": {"good": "On track", "moderate": "Close to target", "low": "Behind target"}[g],
            "grade": g}


def audience_mix(creators, reach_by_code):
    """Where the campaign's audience is, from the creators' uploaded full
    analyses, each creator weighted by the reach they delivered. Only
    creators with an analysis count; the share covered is returned so the
    report can say so."""
    totals, covered, all_reach = {}, 0.0, 0.0
    for c in creators:
        w = float(reach_by_code.get(c["code"]) or 0)
        all_reach += w
        a = db.analysis(c["code"])
        countries = ((a or {}).get("data") or {}).get("audience", {}).get("countries") or []
        if not a or not countries or not w:
            continue
        covered += w
        for row in countries:
            cc, pct_ = (row.get("code") or "").upper(), row.get("pct")
            if len(cc) == 2 and isinstance(pct_, (int, float)):
                totals[cc] = totals.get(cc, 0.0) + w * pct_ / 100.0
    if not covered:
        return None
    rows = sorted(({"code": k, "pct": v / covered * 100} for k, v in totals.items()),
                  key=lambda r: -r["pct"])[:8]
    return {"countries": rows, "coverage": covered / all_reach * 100 if all_reach else 0}


def client_report(campaign, photo=None, photo_large=None):
    """The report as the client may see it: no cost, no CPM, no EMV, no
    ratings or notes, and only the sections switched on for them. `photo`
    turns a stored photo name into a signed URL."""
    r = report(campaign, internal=False)
    vis = r["visibility"]
    have = db.analysis_codes()
    keep = ("id", "code", "platform", "kind", "url", "posted_at", "caption", "thumb",
            "section", "likes", "comments", "engagement", "views", "reach", "impressions",
            "shares", "saves", "er", "video_er", "imp_er", "view_rate", "story_rate", "real",
            "reach_real", "impressions_real", "video", "story", "health")
    posts = [{k: p.get(k) for k in keep} for p in r["posts"]
             if vis["all_content"] or p["section"] == "campaign"]
    names = {c["code"]: c["name"] for c in r["creators"]}
    pics = {c["code"]: (photo(c["photo"]) if photo and c["photo"] else None) for c in r["creators"]}
    for p in posts:
        p["creator"] = names.get(p["code"], p["code"])
        p["photo"] = pics.get(p["code"])
        if not vis["reach"]:
            for k in ("reach", "impressions", "imp_er", "reach_real", "impressions_real", "story_rate"):
                p.pop(k, None)
    creators = []
    for c in r["creators"]:
        row = {k: c[k] for k in ("code", "name", "followers", "posts", "likes", "comments", "engagement",
                                 "views", "reach", "impressions", "shares", "saves", "er", "video_er",
                                 "clicks", "planned", "delivered", "profiles", "band", "er_grade",
                                 "video_er_grade", "score", "rank", "badge")}
        row["photo"] = pics.get(c["code"])
        row["photo_large"] = photo_large(c["photo"]) if photo_large and c["photo"] else None
        row["has_analysis"] = c["code"] in have
        if not vis["clicks"]:
            row.pop("clicks")
        if not vis["reach"]:
            row.pop("reach"); row.pop("impressions")
        creators.append(row)
    total = {k: v for k, v in r["total"].items() if k != "emv"}
    if not vis["clicks"]:
        for k in ("clicks", "ctr", "ctr_grade"):
            total.pop(k, None)
    if not vis["reach"]:
        for k in ("reach", "impressions", "imp_er", "exposure"):
            total.pop(k, None)
    k = campaign
    steps = [x for x in db.campaign_steps(k) if x["on"]]
    current = next((x["key"] for x in steps if x["state"] == "active"), None)
    if current is None and steps and all(x["state"] == "done" for x in steps):
        current = "done"
    out = {"campaign": dict(r["campaign"], phase=current, status_note=k["status_note"],
                            logos=db.campaign_logos(k), steps=steps),
           "total": total, "creators": creators, "posts": posts, "history": r["history"],
           "visibility": {kk: v for kk, v in vis.items() if kk != "emv"},
           "updated_at": r["updated_at"], "verdict": r["verdict"],
           "progress": r["progress"] if vis["reach"] else {"elapsed": r["progress"]["elapsed"],
                                                            "items": [i for i in r["progress"]["items"]
                                                                      if i["key"] not in ("reach",)]},
           "benchmarks": {"er": r["benchmarks"]["er"], "video_er": r["benchmarks"]["video_er"],
                          "view_rate": r["benchmarks"]["view_rate"], "story_rate": r["benchmarks"]["story_rate"],
                          "ctr": r["benchmarks"]["ctr"], "bands": BAND_LABEL}}
    if not vis["clicks"]:
        out["progress"]["items"] = [i for i in out["progress"]["items"] if i["key"] != "clicks"]
    reach_by = {c["code"]: (c.get("reach") or 0) + (c.get("views") or 0) for c in r["creators"]}
    out["audience"] = audience_mix(r["creators"], reach_by)
    if vis["clicks"]:
        cl = r["clicks"]
        out["clicks"] = {kk: cl[kk] for kk in ("clicks", "uniques", "by_day", "by_app", "by_device",
                                               "by_country")}
        out["clicks"]["by_creator"] = [{"k": names.get(x["k"], x["k"]), "code": x["k"], "n": x["n"]}
                                       for x in cl["by_creator"]]
        with db.connect() as conn:
            out["clicks"]["links"] = conn.execute(
                "SELECT COUNT(*) FROM links WHERE campaign_id = ? AND active = 1", (k["id"],)).fetchone()[0]
        out["clicks"]["has_destination"] = bool(k["destination"])
    return out
