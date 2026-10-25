"""Campaign KPIs: one place where every number on a campaign report is worked
out, so the dashboard, the client's page and the exports cannot disagree.

Definitions (also in docs/CAMPAIGN-TRACKER-BRIEF.md §11):

  engagement          likes + comments + shares + saves (every campaign, owner 2026-10-19)
  est. reach, post    engagement × REACH_PER_ENGAGEMENT, capped at followers
  est. reach, video   views × VIDEO_REACH_PER_VIEW (40%) — plays count replays and
                      repeat viewers, so unique people are fewer than views
  est. reach, story   followers × STORY_VIEW_RATE
  est. impressions    post: est. reach × 1.5 · story: = est. reach
  video               views are counted as views, not as impressions
  real values         an approved insight's reach / impressions / views
                      replace the estimates for that post
  ER%                 engagement ÷ followers, averaged over posts whose likes
                      are visible (stories excluded)
  Video ER%           engagement ÷ views, over videos whose likes are visible
  hidden likes        the creator switched the like count off: engagement for
                      that post is comments only, it is left out of every
                      rate, and the report lists it so the real number can be
                      taken from the creator's insights
  Impressions ER%     engagement ÷ impressions, over non-video posts
  EMV                 Σ count × SAR multiplier, per action and platform
  CPM (internal)      cost ÷ (impressions + views) × 1,000
  CTR                 clicks ÷ (impressions + views)

Estimates are labelled as such everywhere they are shown. The factors are
settings, not constants, so they can be tuned without a deploy.
"""

import json

import db
import plans

DEFAULT_FACTORS = {"reach_per_engagement": 10.0, "story_view_rate": 0.05,
                   "impressions_per_reach": 1.5, "video_reach_per_view": 0.40,
                   "report_reach_per_view": 0.90}
# video_reach_per_view: unique people ÷ plays for an Instagram reel. Our first
# 5 posts with real insights (Oct 2026) measured 20–22% on the big creators and
# 59–79% on the small ones, 22% overall by views and 40% on a simple average;
# 40% is the working estimate used when PLANNING a campaign. Editable in Settings.
# report_reach_per_view: what a campaign report assumes for a reel whose real viewers
# are not known yet — kept just below its views (a small margin) until the creator's
# insights arrive and replace it with the measured number. Reports only; planning
# keeps video_reach_per_view.
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
    "video_er": [4.5, 3.0],
    # views ÷ followers, % — how far a video travelled
    "view_rate": [30.0, 10.0],
    # story reach ÷ followers, %
    "story_rate": [8.0, 4.0],
    # clicks ÷ (impressions + views), %
    "ctr": [1.0, 0.3],
    # share of followers / likers that are fake, % — LOWER is better:
    # at or under the first is "good", at or under the second "moderate"
    "fake_followers": [15.0, 30.0],
    "fake_likers": [15.0, 30.0],
}


def band_of(followers):
    try:
        f = float(followers or 0)
    except (TypeError, ValueError):
        f = 0
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
    keys = {"clicks": True, "emv": True, "all_content": False, "reach": False, "audience": True}
    try:
        got = json.loads(campaign["visibility"] or "{}") if "visibility" in campaign.keys() else {}
    except ValueError:
        got = {}
    out = {k: bool(got.get(k, v)) for k, v in keys.items()}
    out["reach"] = False      # reach is not shown on any client report (owner, 2026-10-18)
    return out


def post_numbers(c, f, all_eng=True):
    """Every derived number for one piece of content. Engagement is likes + comments + shares + saves;
    `all_eng=False` gives likes + comments only (published benchmarks count those)."""
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
    if all_eng:
        eng += (out["shares"] or 0) + (out["saves"] or 0)
        out["engagement"] = eng

    if video:
        out["reach"] = int(ins["reach"]) if ins.get("reach") else \
            int(round((views or 0) * f.get("report_reach_per_view", DEFAULT_FACTORS["report_reach_per_view"])))
        out["impressions"] = 0           # video exposure is counted as views
        out["reach_real"] = bool(ins.get("reach"))
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
    out["video_er"] = (eng / float(views) * 100) if (video and views and likes is not None) else None
    out["likes_hidden"] = likes is None and not story
    out["views_hidden"] = bool(video and views is None)      # the platform shows no view count (Snapchat)
    # What this post does not show publicly, so it can be asked for.
    gaps = []
    if out["likes_hidden"]:
        gaps.append("likes")
    if out["shares"] is None:
        gaps.append("shares")
    if out["saves"] is None:
        gaps.append("saves")
    if not out["reach_real"]:
        gaps.append("reach")
    out["gaps"] = gaps
    # People who saw it: views for a video, reach for a post or story.
    # Adding the two counts the same viewers twice.
    out["exposure"] = (views or 0) if video else out["reach"]
    out["imp_er"] = (eng / float(out["impressions"]) * 100) if (
        not video and not story and out["impressions"]) else None
    out["view_rate"] = (views / float(followers) * 100) if (video and views and followers) else None
    out["story_rate"] = (out["reach"] / float(followers) * 100) if (story and followers) else None
    return out


def _piece_dates(posts):
    """When each piece of content went up, oldest first — one date per piece (a carousel
    counts once). Used by the publishing plan to date videos that are already published."""
    first = {}
    for p in posts:
        t = p.get("posted_at")
        if not t:
            continue
        pk = p["pk"]
        if pk not in first or t < first[pk]:
            first[pk] = t
    return sorted(first.values())


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


def goal_grade(value, goal):
    """A rate against the campaign's own goal, on the same steps as target_progress: at or over it "good",
    from 70% of it "moderate", else "low"."""
    if value is None or not goal:
        return None
    return "good" if value >= goal else ("moderate" if value >= 0.7 * goal else "low")


def goal_grading(targets, total, creators, posts, progress=None):
    """One rule for every ER verdict (owner, 2026-10-19; extended 2026-10-23): when the campaign has an ER goal,
    the campaign's, each creator's and each post's engagement rate are graded against that goal, not the tier
    benchmarks, so the dashboard, the report and its PDF cannot read Strong in one place and Fair in another.
    The campaign's own rate is the one its ER target measures (goal platforms only, progress item "er"), so the
    headline rate and its grade are the same number on every page. Changes the grades in place and returns the
    goal (None when there is none)."""
    goal = targets.get("er") if targets else None
    if not isinstance(goal, (int, float)) or goal <= 0:
        return None
    pair = [goal, round(0.7 * goal, 4)]
    item = next((i for i in (progress or {}).get("items", []) if i["key"] == "er"), None)
    rate = item["actual"] if item else (total.get("video_er") if total.get("video_er") is not None else total.get("er"))
    total["er_grade"] = total["video_er_grade"] = goal_grade(rate, goal)
    for c in creators:
        c["er_grade"] = goal_grade(c.get("er"), goal)
        c["video_er_grade"] = goal_grade(c.get("video_er"), goal)
    for p in posts:
        h = p.get("health")
        if not h or p.get("story"):
            continue                       # a story is judged on its reach rate, which has no goal
        h["grade"] = goal_grade(h.get("value"), goal)
        h["benchmark"] = pair
        h["band"] = None
        h["goal"] = goal
    return goal


def history_to_now(history, total):
    """The "so far" charts end on the numbers the page shows: the last day carries the campaign totals
    (approved insights, shares and saves, and HelloVoice's estimates included), so the curve cannot end below
    the Views or Engagement figure above it. Earlier days stay the captured snapshots."""
    if not history:
        return history
    last = dict(history[-1])
    for k in ("likes", "comments", "views", "shares", "saves", "engagement"):
        if total.get(k) is not None:
            last[k] = total[k]
    return history[:-1] + [last]


def report_rev(rep):
    """A short fingerprint of everything a client page shows, so the report and the dashboard can tell a real
    change (new numbers, targets, estimates, steps, visibility, comments, sales) from an unchanged answer.
    Leaves out what moves with the clock (elapsed share, expected-by-today, next capture) and the signed query
    strings on pictures, which are re-signed daily."""
    import hashlib
    clock = {"elapsed", "expected", "due", "next_update_at", "next_at", "next_read", "pace", "share", "selections"}

    def clean(v, key=None):
        if isinstance(v, dict):
            return {k: clean(x, k) for k, x in v.items() if k not in clock}
        if isinstance(v, list):
            return [clean(x, key) for x in v]
        if isinstance(v, str) and key in ("photo", "photo_large", "thumb", "logos"):
            return v.split("?", 1)[0]
        if isinstance(v, float):
            return round(v, 6)
        return v
    raw = json.dumps(clean(rep), sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def report(campaign, internal=False, raw=False):
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

    bm0 = benchmarks()
    # The grading benchmarks are published likes + comments rates; engagement here also counts shares + saves,
    # so they are lifted by what shares + saves add on each platform (plans.share_save_uplift): a post by its own
    # platform, creator rows and totals by the campaign's main platform.
    up = plans.share_save_uplift()

    def lifted(platform):
        f = up.get(platform, 1.0)
        if f == 1.0:
            return bm0
        return dict(bm0, er={b: [round(v * f, 2) for v in pair] for b, pair in bm0["er"].items()},
                    video_er=[round(v * f, 2) for v in bm0["video_er"]])     # rounded: the pages print them as is

    # A post that carries no follower count of its own takes the creator's followers on that platform, so
    # its view rate can be worked out (the benchmark gauge read "Typical" without it).
    foll_by = {m["cc_code"]: creator_followers(m) for m in members}
    for c in content:
        if not c.get("followers"):
            got = (foll_by.get(c["code"]) or {}).get(c["platform"])
            if got:
                c["followers"] = got
    posts = []
    for c in content:
        n = post_numbers(c, f)
        n["health"] = post_health(n, c.get("followers"), lifted(c["platform"]))
        emv = 0.0
        for action in ("impressions", "views", "likes", "comments", "shares", "saves"):
            emv += (n.get(action) or 0) * _rate(rates, c["platform"], action)
        n["emv"] = emv
        posts.append({**c, **n})
    # One video on several platforms is one piece: its numbers add up like any others, but it counts
    # once as a delivered video and once in the engagement-rate average.
    for p in posts:
        p["pk"] = p.get("piece") or p["id"]
    sizes = {}
    for p in posts:
        sizes[p["pk"]] = sizes.get(p["pk"], 0) + 1
    for p in posts:
        p["piece_size"] = sizes[p["pk"]]

    camp = [p for p in posts if p["section"] == "campaign"]
    main = campaign["platform"] if campaign["platform"] in plans.PLATFORMS else None
    if not main and camp:
        counts = {}
        for p in camp:
            counts[p["platform"]] = counts.get(p["platform"], 0) + 1
        main = max(counts, key=counts.get)
    bm = lifted(main)

    def totals(items, extra_clicks=0):
        t = {k: sum((p.get(k) or 0) for p in items)
             for k in ("likes", "comments", "engagement", "views", "reach", "impressions",
                       "shares", "saves", "emv")}
        t["seen"] = sum(p["exposure"] for p in items)
        t["hidden_likes"] = sum(1 for p in items if p["likes_hidden"])
        pieces = {}
        for p in items:
            pieces.setdefault(p["pk"], []).append(p)
        t["posts"] = len(pieces)
        t["clicks"] = extra_clicks
        t["er"] = _avg(_avg(q["er"] for q in g) for g in pieces.values())
        t["video_er"] = _avg(_avg(q["video_er"] for q in g) for g in pieces.values())
        t["imp_er"] = _avg(_avg(q["imp_er"] for q in g) for g in pieces.values())
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

    # Whole-campaign results set by hand replace the measured ones, and are
    # listed in total["adjusted"] so every page marks them as estimates.
    total["adjusted"] = []
    if not raw:
        for key, val in db.campaign_overrides(campaign).items():
            if key == "_basis":
                continue
            total[key] = val
            if key == "er":
                total["video_er"] = val
            total["adjusted"].append(key)

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
        delivered = len({p["pk"] for p in mine})
        posted_ats = _piece_dates(mine)
        # Graded on the followers of the campaign's platform when the creator has them there (a TikTok-sized
        # count made an Instagram creator "mega", 2026-10-19), else on their main count.
        # A multi-platform campaign grades each creator on the platform they post on there (plan.creator_platforms,
        # else their posts here), 2026-10-20 Ivatherm.
        plat_here = campaign["platform"] or ((plans.plan_of(campaign) or {}).get("creator_platforms") or {}).get(code)             or (mine[0]["platform"] if mine else None)
        followers = (foll_by.get(code) or {}).get(plat_here) or m["followers"]
        row = {"code": code, "name": m["name"] or code, "photo": m["photo"],
               "followers": followers, "planned": m["planned"], "delivered": delivered,
               "posted_ats": posted_ats,
               "pending_status": (m["pending_status"] if "pending_status" in m.keys() else None),
               "pending_date": (m["pending_date"] if "pending_date" in m.keys() else None),
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

    objective = objective_of(campaign)
    links_on = has_links(campaign)
    w = weights_for(objective, links_on, campaign_weights(campaign))
    scoreboard(creators, bm, w)
    targets = db.campaign_targets(campaign)
    targets_auto = False
    if not targets:
        # Every campaign shows its progress bar (owner, 2026-10-19): with no agreed targets, the safe targets built from
        # its creators and their planned posts stand in, marked as suggested. ER is left out: the builder's rate is per
        # follower, the report's video rate is per view, so the two would not compare.
        try:
            safe = recommend_targets(campaign).get("safe") or {}
        except Exception:
            safe = {}
        targets = {k: safe[k] for k in db.TARGET_KEYS if k != "er" and isinstance(safe.get(k), (int, float)) and safe[k] > 0}
        targets_auto = bool(targets)
    # Every platform counts towards the targets, the bonus ones too, so the goals read the same totals as the rest of the
    # dashboard (owner, 2026-10-23: the Goals tab showed 3M views beside 5.7M on the dashboard).
    tot_goal = total
    progress = target_progress(campaign, tot_goal, targets, plan_fraction(campaign, creators))
    planned = sum(c["planned"] or 0 for c in creators)
    total["planned"] = planned or None
    total["delivered"] = total["posts"]
    total["er_grade"] = _avg_grade([c["er_grade"] for c in creators if c["posts"]])
    total["ctr_grade"] = grade(total["ctr"], bm["ctr"])
    total["video_er_grade"] = grade(total["video_er"], bm["video_er"])
    er_goal = goal_grading(targets, total, creators, posts, progress)
    verdict = overall_verdict(progress, total)

    out = {"campaign": {"id": cid, "name": campaign["name"], "client": campaign["client"],
                        "status": campaign["status"], "starts_at": campaign["starts_at"],
                        "ends_at": campaign["ends_at"], "platform": campaign["platform"]},
           "total": total, "creators": creators, "posts": posts,
           "history": db.content_history(cid), "clicks": clicks,
           "emv_set": bool(rates), "visibility": vis, "factors": f,
           "benchmarks": dict(bm, er_goal=er_goal), "targets": targets, "targets_auto": targets_auto,
           "progress": progress, "verdict": verdict,
           "objective": {"key": objective, "label": objective_info(objective)[0], "kpis": objective_info(objective)[2],
                         "weights": dict(zip(("exposure", "engagement", "er", "clicks"), w)), "links": links_on},
           "gaps": data_gaps(camp),
           "updated_at": max([p["metrics_at"] or 0 for p in posts] + [0]) or None}
    out["history"] = history_to_now(out["history"], total)
    if internal:
        exposure = total["exposure"]
        out["internal"] = {
            "cost": cost_total,
            "cpm": (cost_total / float(exposure) * 1000) if cost_total and exposure else None,
            "cpe": (cost_total / float(total["engagement"])) if cost_total and total["engagement"] else None,
            "cpc": (cost_total / float(clicks["clicks"])) if cost_total and clicks["clicks"] else None,
        }
    return out


def data_gaps(posts):
    """What the public numbers leave out, so the team can ask the creators
    for insights: counts per kind, and the posts with hidden likes."""
    if not posts:
        return {"posts": 0}
    hidden = [{"id": p["id"], "code": p["code"], "url": p["url"], "creator": p.get("creator_name") or p["code"]}
              for p in posts if p.get("likes_hidden")]
    return {"posts": len(posts), "likes_hidden": len(hidden), "hidden": hidden,
            "no_shares": sum(1 for p in posts if "shares" in p["gaps"]),
            "no_saves": sum(1 for p in posts if "saves" in p["gaps"]),
            "reach_estimated": sum(1 for p in posts if "reach" in p["gaps"])}


def _avg_grade(grades):
    pts = {"good": 2, "moderate": 1, "low": 0}
    vals = [pts[g] for g in grades if g in pts]
    if not vals:
        return None
    avg = sum(vals) / float(len(vals))
    return "good" if avg >= 1.5 else ("moderate" if avg >= 0.75 else "low")


# What the leaderboard rewards, chosen per campaign: (reach+views, engagement,
# engagement rate, affiliate clicks). Each row sums to 1. The rate weight is 0:
# the score is the RESULTS a creator delivered for the campaign, each as a share
# of the best creator's result, so a creator with a handful of views cannot rank
# high on a ratio.
OBJECTIVES = {
    "balanced": ("Balanced", (0.45, 0.35, 0.0, 0.20)),
    "awareness": ("Awareness", (0.70, 0.20, 0.0, 0.10)),
    "engagement": ("Engagement", (0.20, 0.70, 0.0, 0.10)),
    "traffic": ("Traffic", (0.20, 0.20, 0.0, 0.60)),
    # Not a template: weights the admin typed for this one campaign.
    "custom": ("Custom", (0.45, 0.35, 0.0, 0.20)),
}
# A campaign's type is Awareness, Engagement and/or Traffic. Several can be chosen at once: the key
# is then "awareness+traffic" and the weights are the average of the chosen types' rows (as
# fit.blend does for creator scores). "balanced" and "custom" stay for the admin only; the old
# "conversion" key reads as "traffic".
GOAL_KEYS = ("awareness", "engagement", "traffic")
BLEND_ORDER = {k: i for i, k in enumerate(GOAL_KEYS)}


def blend_key(parts):
    """["traffic", "awareness"] -> "awareness+traffic"; None when nothing valid is named."""
    names = [("traffic" if p == "conversion" else p) for p in parts]
    names = sorted({p for p in names if p in GOAL_KEYS}, key=BLEND_ORDER.get)
    return "+".join(names) if names else None


def valid_objective(key):
    """A key a campaign may hold: a listed objective or a blend of the three goals."""
    if key in OBJECTIVES:
        return True
    return bool(key) and "+" in str(key) and blend_key(str(key).split("+")) == str(key)


def objective_info(key):
    """(label, weights, kpis) for an objective key, single or blended."""
    if key in OBJECTIVES:
        return OBJECTIVES[key][0], OBJECTIVES[key][1], OBJECTIVE_KPIS[key]
    parts = [p for p in str(key).split("+") if p in GOAL_KEYS] or ["awareness"]
    w = tuple(sum(OBJECTIVES[p][1][i] for p in parts) / len(parts) for i in range(4))
    kpis = list(dict.fromkeys(k for p in parts for k in OBJECTIVE_KPIS[p]))
    return " + ".join(OBJECTIVES[p][0] for p in parts), w, kpis


def brief_goals(selection_id):
    """The goals of the brief behind a selection (its live brief, else the selection's own objective),
    as keys: ["awareness", "traffic"]. Empty when nothing is recorded."""
    if not selection_id:
        return []
    with db.connect() as conn:
        r = conn.execute("SELECT objective FROM briefs WHERE selection_id = ? AND deleted_at IS NULL ORDER BY id DESC LIMIT 1",
                         (selection_id,)).fetchone()
        raw = r["objective"] if r and r["objective"] else None
        if not raw:
            s = conn.execute("SELECT objective FROM selections WHERE id = ?", (selection_id,)).fetchone()
            raw = s["objective"] if s and s["objective"] else None
    if not raw:
        return []
    low = [p.strip().lower() for p in str(raw).split("+")]
    if low == ["balanced"]:
        return list(GOAL_KEYS)
    return [p for p in (blend_key(low) or "").split("+") if p]


# The ready-made starting points offered in the campaign setup.
TEMPLATES = [(k, v) for k, v in OBJECTIVES.items() if k != "custom"]
TEMPLATE_NOTES = {"balanced": "Views, engagement and clicks all count",
                  "awareness": "Reach and views matter most",
                  "engagement": "Likes and comments matter most",
                  "traffic": "Link clicks matter most"}


# Which targets each objective puts in front of the client.
OBJECTIVE_KPIS = {"balanced": ["views", "engagement", "er"], "awareness": ["views"],
                  "engagement": ["engagement", "er"], "traffic": ["clicks", "views"],
                  "custom": ["views", "engagement", "er"]}
SAFE_SHARE = 0.8      # of a creator's own averages, when their analysis is on file


def recommend_targets(campaign):
    """Targets to agree with the client, built creator by creator from what
    is booked (posts planned) and what each creator usually delivers.

    safe    = what to promise: the "fair" benchmark for the creator's size,
              or 80% of their own averages when their full analysis is on file
    stretch = what to aim for: the "strong" benchmark, or 100% of averages

    Each planned post is counted as one video (reel / TikTok), the usual
    deliverable; reach for a video is its views. Clicks only when the
    campaign has an affiliate destination."""
    bm = benchmarks()
    members = db.campaign_creators(campaign["id"])
    out = {"safe": {}, "stretch": {}, "notes": [], "basis": []}
    tot = {"safe": {"views": 0, "engagement": 0, "followers": 0}, "stretch": {"views": 0, "engagement": 0, "followers": 0}}
    posts = 0
    unplanned, measured = 0, 0
    for m in members:
        n = m["planned"] or 0
        if not n:
            unplanned += 1
            n = 1
        posts += n
        a = (db.analysis(m["cc_code"]) or {}).get("data") or {}
        # The analysis's own follower count when it has one, so averages
        # and the audience they came from describe the same account.
        f = a.get("followers") or m["followers"] or 0
        band = band_of(f)
        avg_views = a.get("avg_reel_plays") or a.get("avg_views")
        avg_eng = (a.get("avg_likes") or 0) + (a.get("avg_comments") or 0)
        if avg_views or avg_eng:
            measured += 1
        for kind, share, er_i, vr_i in (("safe", SAFE_SHARE, 1, 1), ("stretch", 1.0, 0, 0)):
            v = avg_views * share if avg_views else f * bm["view_rate"][vr_i] / 100.0
            e_ = avg_eng * share if avg_eng else f * bm["er"][band][er_i] / 100.0
            tot[kind]["views"] += v * n
            tot[kind]["engagement"] += e_ * n
            tot[kind]["followers"] += f * n
        out["basis"].append({"code": m["cc_code"], "name": m["name"] or m["cc_code"], "planned": m["planned"],
                             "source": "own averages" if (avg_views or avg_eng) else BAND_LABEL[band] + " benchmark"})
    if not members:
        out["notes"].append("Add creators first — targets are built from them.")
        return out
    for kind, ctr_i in (("safe", 1), ("stretch", 0)):
        t = tot[kind]
        o = out[kind]
        o["posts"] = posts
        o["views"] = int(round(t["views"], -2))
        o["reach"] = int(round(t["views"] * factors()["video_reach_per_view"], -2))     # unique people, below total views
        o["engagement"] = int(round(t["engagement"], -1))
        o["er"] = round(t["engagement"] / t["followers"] * 100, 1) if t["followers"] else None
        if campaign["destination"]:
            o["clicks"] = int(round(t["views"] * bm["ctr"][ctr_i] / 100.0))
    if unplanned:
        out["notes"].append("%d creator(s) have no posts planned yet — counted as 1 post each." % unplanned)
    out["notes"].append("%d of %d creators use their own averages (full analysis on file); the rest use benchmarks."
                        % (measured, len(members)))
    if not campaign["destination"]:
        out["notes"].append("No affiliate destination, so no click target.")
    key = objective_of(campaign)
    label, _, kpis = objective_info(key)
    out["objective"] = label
    out["primary"] = [k for k in kpis if k in out["safe"]]
    return out


def weights_for(objective, has_links, custom=None):
    """The objective's leaderboard weights. A campaign with no tracked links
    has no clicks to score, so that part is dropped and the other three are
    scaled up to still make 100 — nobody is marked on a metric that does not
    exist in their campaign."""
    w = list(custom if (objective == "custom" and custom) else objective_info(objective)[1])
    if not has_links:
        rest = sum(w[:3])
        w = [x / rest for x in w[:3]] + [0.0]
    return tuple(w)


def has_links(campaign, clicks=None):
    """True when the campaign tracks link clicks: a destination is set, or an
    active link has a destination of its own."""
    if campaign["destination"]:
        return True
    with db.connect() as conn:
        # Every creator gets an automatic link, but it leads nowhere until a
        # destination is set — only a link with its own destination counts.
        return bool(conn.execute("SELECT 1 FROM links WHERE campaign_id = ? AND active = 1 "
                                 "AND destination IS NOT NULL AND destination != '' LIMIT 1",
                                 (campaign["id"],)).fetchone())


def campaign_weights(campaign):
    """The weights typed for this campaign — (reach & views, engagement,
    engagement rate, clicks), summing to 1 — or None."""
    raw = campaign["weights"] if "weights" in campaign.keys() else None
    try:
        w = json.loads(raw) if raw else None
    except (ValueError, TypeError):
        return None
    if isinstance(w, list) and len(w) == 4 and all(isinstance(x, (int, float)) and x >= 0 for x in w) and sum(w) > 0:
        t = float(sum(w))
        return tuple(x / t for x in w)
    return None


def weights_from_percents(vals):
    """Four typed percentages -> weights summing to 1, or None when nothing
    usable was typed. They need not add up to exactly 100: they are scaled."""
    out = []
    for v in vals:
        try:
            out.append(max(0.0, float(str(v).replace("%", "").strip() or 0)))
        except ValueError:
            return None
    t = sum(out)
    return tuple(x / t for x in out) if t > 0 else None


def objective_for(weights, prefer=None):
    """The template these weights are (to the nearest half point), else "custom". ``prefer`` is
    a blended key the admin picked: it is kept when the weights are still that blend's."""
    cands = [(prefer, objective_info(prefer)[1])] if prefer and valid_objective(prefer) and prefer not in ("custom",) else []
    for key, w in cands + [(k, v) for k, (_, v) in TEMPLATES]:
        if all(abs(a - b) < 0.005 for a, b in zip(weights, w)):
            return key
    return "custom"


def objective_of(campaign):
    """The campaign's objective key. A stored one is kept (the old "conversion" reads as "traffic");
    an unknown or missing one is taken from the goals of the brief behind its selection, a blend
    when it named several, and only then falls back to "balanced"."""
    keys = campaign.keys()
    key = campaign["objective"] if "objective" in keys else None
    if key == "conversion":
        return "traffic"
    if valid_objective(key):
        return key
    goals = brief_goals(campaign["selection_id"] if "selection_id" in keys else None)
    return blend_key(goals) or "balanced"


def scoreboard(creators, bm, weights=None):
    """A 0–100 score per creator, so the leaderboard ranks results rather
    than audience size alone. Four parts, weighted by the campaign's
    objective (OBJECTIVES; balanced = 35/25/25/15). Every part is measured
    against the OTHER creators in this campaign — never against followers or
    an outside benchmark — as the share of the best creator's result:

      exposure (views for videos, reach for posts) against the best in the campaign
      engagement (likes + comments) against the best in the campaign
      engagement rate = reactions per view, against the best in the campaign
           (posts with hidden likes are left out, never counted as zero)
      link clicks against the best in the campaign

    Creators with no counted posts score 0 and are ranked last."""
    w = weights or OBJECTIVES["balanced"][1]
    def peak(key):
        return max([c[key] or 0 for c in creators] + [0]) or 1
    pe = max([c.get("seen") or 0 for c in creators] + [0]) or 1
    pg, pc = peak("engagement"), peak("clicks")

    def per_view(c):
        # reactions per view: videos first, else per impression for photos
        r = c["video_er"] if c.get("video_er") is not None else c.get("imp_er")
        return r or 0
    pr = max([per_view(c) for c in creators] + [0]) or 1
    for c in creators:
        if not c["posts"]:
            c["score"] = 0.0
            continue
        quality = per_view(c) / pr
        c["parts"] = {"exposure": round(100 * w[0] * (c.get("seen") or 0) / pe, 1),
                      "engagement": round(100 * w[1] * (c["engagement"] or 0) / pg, 1),
                      "er": round(100 * w[2] * quality, 1),
                      "clicks": round(100 * w[3] * (c["clicks"] or 0) / pc, 1)}
        c["score"] = round(100 * (w[0] * (c.get("seen") or 0) / pe
                                  + w[1] * (c["engagement"] or 0) / pg
                                  + w[2] * quality
                                  + w[3] * (c["clicks"] or 0) / pc), 1)
    ranked = sorted(creators, key=lambda c: (-c["score"], c["name"]))
    for i, c in enumerate(ranked):
        c["rank"] = i + 1 if c["posts"] else None
        c["badge"] = {1: "gold", 2: "silver", 3: "bronze"}.get(i + 1) if c["posts"] else None
    creators.sort(key=lambda c: (c["rank"] is None, c["rank"] or 0))


MATURE_DAYS = 7          # a video is expected to reach its share of the targets a week after it is due


def plan_fraction(campaign, creators, now=None):
    """Where the publishing plan says the campaign should be: (share of the videos due by now, share of
    the targets those videos should have reached by now). Each creator's planned videos are spread over the
    publishing step (the first falls on its first day, the last on its last day); a creator's own "next post expected" date replaces
    the due date of the next video they owe. A video is expected to reach its share of views, reach and
    engagement MATURE_DAYS after it is due. None when the plan cannot be read."""
    import calendar
    now = now or db.now()
    pub = next((x for x in db.campaign_steps(campaign) if x["key"] == "publishing" and x["on"] and x["start"] and x["end"]), None)
    total = sum(int(c.get("planned") or 0) for c in creators)
    if not pub or not total:
        return None

    def ts(d, end=False):
        y, m, dd = (int(v) for v in d.split("-"))
        return calendar.timegm((y, m, dd, 23, 59, 59) if end else (y, m, dd, 0, 0, 0)) - 3 * 3600   # Riyadh day
    start, end = ts(pub["start"]), ts(pub["end"], True)
    due = mature = 0.0
    for c in creators:
        n = int(c.get("planned") or 0)
        got = int(c.get("delivered") or 0)
        posted = sorted(x for x in (c.get("posted_ats") or []) if x)
        for i in range(1, n + 1):
            # First video due on the first publishing day, the last on the last day, evenly between
            # (a creator with one video owes it on the last day).
            t = start + (end - start) * ((i - 1) / float(n - 1) if n > 1 else 1.0)
            if i <= len(posted):
                # It is published: the day it went up IS its due date. Without this a creator
                # with one video is dated to the last day of the window however long ago they
                # posted, so the plan shows nothing due (2026-10-25, Ivatherm).
                t = posted[i - 1]
            elif i == got + 1 and c.get("pending_date"):
                try:
                    t = ts(c["pending_date"])
                except ValueError:
                    pass
            if t <= now:
                due += 1
                mature += min(1.0, (now - t) / float(MATURE_DAYS * 86400))
    return due / total, mature / total


def goal_platforms(plan):
    """The platforms a campaign's goals were set for, from its saved plan ("Instagram + TikTok" or one)."""
    if not plan:
        return []
    got = plan.get("platforms") or [x.strip() for x in str(plan.get("platform") or "").split("+")]
    return [x for x in got if x in plans.PLATFORMS]


def creator_followers(m):
    """{platform: followers} for one campaign creator row."""
    foll = {}
    for a in db.split_profiles(m["profiles"] or ""):
        if a.get("followers"):
            foll[a["platform"]] = int(a["followers"])
    if m["followers"] and m["platform"] and m["platform"] not in foll:
        foll[m["platform"]] = int(m["followers"])
    return foll


SIZE_WORDS = {"nano": "under 10K followers", "micro": "10K–100K followers", "mid": "100K–500K followers",
              "macro": "500K–1M followers", "mega": "over 1M followers"}


def _pacing_dates(campaign, creators):
    """Each creator's upcoming videos: [(video number, due epoch or None, confirmed)] from the publishing
    plan (same spread as plan_fraction); the next video takes the creator's own expected date."""
    import calendar
    pub = next((x for x in db.campaign_steps(campaign) if x["key"] == "publishing" and x["on"] and x["start"] and x["end"]), None)

    def ts(d, end=False):
        y, m, dd = (int(v) for v in d.split("-"))
        return calendar.timegm((y, m, dd, 23, 59, 59) if end else (y, m, dd, 0, 0, 0)) - 3 * 3600
    start = ts(pub["start"]) if pub else None
    end = ts(pub["end"], True) if pub else None
    out = {}
    for c in creators:
        n, got = int(c.get("planned") or 0), int(c.get("delivered") or 0)
        rows = []
        for i in range(got + 1, n + 1):
            t, conf = None, False
            if pub:
                t = start + (end - start) * ((i - 1) / float(n - 1) if n > 1 else 1.0)
            if i == got + 1 and c.get("pending_date"):
                try:
                    t, conf = ts(c["pending_date"]), True
                except ValueError:
                    pass
            rows.append((i, t, conf))
        out[c["code"]] = rows
    return out, ((start, end) if pub else None)


def _ri(v, nd=0):
    return int(round(v, nd))


def _platform_goals(campaign, plan, gp, r, camp, members, sched, window):
    """The Goals tab measured one goal platform at a time, so the page's platform filter can switch it:
    {platform: {progress, forecast, creators, pace, bench, now}}. Targets are the plan's own estimate for that
    platform (plan.by_platform) and the videos the creators planned there (a planned video counts on every goal
    platform where the creator has an account). Empty when the plan kept no per-platform estimate, so older plans
    fall back to the whole-campaign view."""
    own = plan.get("by_platform") or {}
    if not own or any(not ((own.get(pl) or {}).get("safe") and (own[pl].get("expected"))) for pl in gp):
        return {}
    lib = plans.rates()
    cf = plans.CATEGORIES.get(plan.get("category"), ("", 1.0))[1]
    camp_targets = db.campaign_targets(campaign)
    by_code = {m["cc_code"]: m for m in members}
    out = {}
    for pl in gp:
        o = own[pl]
        mine = [c for c in r["creators"] if (creator_followers(by_code[c["code"]]).get(pl) if c["code"] in by_code else None)]
        posts_pl = [p for p in camp if p["platform"] == pl]
        pieces = {}
        for p in posts_pl:
            pieces.setdefault(p["pk"], []).append(p)
        # ---- targets: this platform's own
        tgt = {}
        planned = sum(int(c.get("planned") or 0) or 1 for c in mine)
        for key in ("posts", "views", "engagement", "er"):
            if key not in camp_targets:
                continue
            v = planned if key == "posts" else o["safe"].get(key)
            if v:
                tgt[key] = plans._round(key, v)
        tot = {"posts": len(pieces), "views": sum(p.get("views") or 0 for p in posts_pl), "reach": 0,
               "engagement": sum(p.get("engagement") or 0 for p in posts_pl), "clicks": 0,
               "er": _avg(_avg(q["er"] for q in g) for g in pieces.values()),
               "video_er": _avg(_avg(q["video_er"] for q in g) for g in pieces.values())}
        # ---- the publishing plan for the videos on this platform
        cs = []
        for c in mine:
            his = [p for p in posts_pl if p["code"] == c["code"]]
            got = len({p["pk"] for p in his})
            cs.append(dict(c, planned=int(c.get("planned") or 0) or 1, delivered=got,
                           posted_ats=_piece_dates(his)))
        planf = plan_fraction(campaign, cs)
        progress = target_progress(campaign, tot, tgt, planf)
        # ---- creators on this platform
        crs, tv, te = [], [0.0, 0.0], [0.0, 0.0]
        for c in cs:
            f = creator_followers(by_code[c["code"]])[pl]
            t = plans.tier_of(f)
            v = [f * lib[pl]["view_rate"][t][i] / 100.0 for i in (0, 1)]
            e = [v[i] * lib[pl]["eng_rate"][t][i] * cf / 100.0 for i in (0, 1)]
            n = c["planned"]
            for i in (0, 1):
                tv[i] += v[i] * n
                te[i] += e[i] * n
            mp = [p for p in posts_pl if p["code"] == c["code"]]
            pc = len({p["pk"] for p in mp})
            avg_v = sum(p.get("views") or 0 for p in mp) / float(pc) if pc else None
            ratio = (avg_v / v[0]) if (avg_v is not None and v[0]) else None
            nxt = next(((tt, conf) for (i, tt, conf) in sched.get(c["code"], [])), None)
            crs.append({"code": c["code"], "name": c["name"], "photo": c.get("photo"), "planned": n, "live": pc,
                        "platforms": [{"platform": pl, "followers": f, "size": SIZE_WORDS[t]}], "size": SIZE_WORDS[t],
                        "exp_views": [_ri(v[0], -2), _ri(v[1], -2)] if v[1] else None,
                        "views_per_video": round(avg_v) if avg_v is not None else None,
                        "eng_per_video": round(sum(p.get("engagement") or 0 for p in mp) / pc) if pc else None,
                        "status": None if ratio is None else ("met" if ratio >= 1 else "close" if ratio >= 0.7 else "behind"),
                        "next": ({"at": nxt[0], "confirmed": nxt[1]} if (nxt and not pc) else None)})
        # ---- forecast to the end, on this platform's videos
        prog = {i["key"]: i for i in progress["items"]}
        fc = {"planned": planned, "live": len(pieces)}
        for key, got, aim in (("views", tot["views"], tv[1]), ("engagement", tot["engagement"], te[1])):
            it = prog.get(key)
            if not it or not pieces or not planned:
                continue
            run = got / float(len(pieces)) * planned
            left = 0.0
            for c in crs:
                owed = max(0, (c["planned"] or 1) - (c["live"] or 0))
                if owed and c["exp_views"]:
                    f = c["platforms"][0]["followers"]
                    t = plans.tier_of(f)
                    vv = f * lib[pl]["view_rate"][t][1] / 100.0
                    left += owed * (vv if key == "views" else vv * lib[pl]["eng_rate"][t][1] * cf / 100.0)
            lo, hi = sorted((run, got + left))
            fc[key] = {"low": _ri(lo, -2 if lo >= 1000 else 0), "high": _ri(hi, -2 if hi >= 1000 else 0), "target": it["goal"],
                       "verdict": "ahead" if lo >= it["goal"] else ("ontrack" if hi >= it["goal"] else "behind")}
        fc["early"] = len(pieces) < 3
        # ---- pace on this platform's share
        pace = None
        if planf and window:
            t0, t1 = window[0], window[1] + MATURE_DAYS * 86400
            pts = [(t, plan_fraction(campaign, cs, now=t)) for t in range(t0, t1 + 86400, 86400)]
            pace = {"start": t0, "end": t1, "posts": [[t, round(f[0], 4)] for t, f in pts if f],
                    "mature": [[t, round(f[1], 4)] for t, f in pts if f]}
        elif campaign["starts_at"] and campaign["ends_at"]:
            pace = {"start": campaign["starts_at"], "end": campaign["ends_at"], "posts": None, "mature": None}
        # ---- benchmark band and where this platform is now
        n = sum(c["planned"] for c in cs)
        bench = None
        if n:
            vr, er = [0.0, 0.0], [0.0, 0.0]
            for c in cs:
                t = plans.tier_of(creator_followers(by_code[c["code"]])[pl])
                for i in (0, 1):
                    vr[i] += lib[pl]["view_rate"][t][i] * c["planned"] / n
                    er[i] += lib[pl]["eng_rate"][t][i] * c["planned"] / n * cf
            bench = {"view_rate": [round(vr[0], 1), round(vr[1], 1)], "eng_rate": [round(er[0], 2), round(er[1], 2)]}
        vrs = [p["view_rate"] for p in posts_pl if p.get("view_rate") is not None]
        out[pl] = {"progress": progress, "forecast": fc, "creators": crs, "pace": pace, "bench": bench,
                   "now": {"view_rate": (sum(vrs) / len(vrs)) if vrs else None,
                           "er": tot["video_er"] if tot["video_er"] is not None else tot["er"]},
                   "aim": {"views": _ri(tv[1], -3), "engagement": _ri(te[1], -2)}}
    return out


def goals_view(campaign, r, photo=None):
    """Everything the client's "Goals & benchmarks" tab needs beyond the targets themselves: the forecast, each
    creator's own benchmark, the platform split, what is still to come, the pace curves and the data notes.
    Client-safe: no budget, value floor, cost ratio or reach."""
    plan = plans.plan_of(campaign)
    gp = goal_platforms(plan)
    if not plan or not gp:
        return None
    lib = plans.rates()
    cf = plans.CATEGORIES.get(plan.get("category"), ("", 1.0))[1]
    members = db.campaign_creators(campaign["id"])
    by_code = {m["cc_code"]: m for m in members}
    camp = [p for p in r["posts"] if p["section"] == "campaign"]
    now = db.now()

    def expect(pl, f):
        """(views per video [safe, aim], engagement per video [safe, aim]) for f followers on pl."""
        t = plans.tier_of(f)
        v = [f * lib[pl]["view_rate"][t][i] / 100.0 for i in (0, 1)]
        e = [v[i] * lib[pl]["eng_rate"][t][i] * cf / 100.0 for i in (0, 1)]
        return v, e, t

    creators, tot_v, tot_e = [], [0.0, 0.0], [0.0, 0.0]
    plat_exp = {pl: {"views": [0.0, 0.0], "engagement": [0.0, 0.0], "videos": 0} for pl in gp}
    sched, window = _pacing_dates(campaign, r["creators"])
    booked_by = plan.get("creator_platforms") or {}
    missing = []
    for c in r["creators"]:
        m = by_code.get(c["code"])
        foll = creator_followers(m) if m is not None else {}
        n = int(c.get("planned") or 0) or 1
        # Item 217 (owner, 2026-10-21): the target is set on the platform the creator was booked for
        # (plan.creator_platforms, else every goal platform), and what they got counts on every platform they posted on.
        booked = [booked_by[c["code"]]] if booked_by.get(c["code"]) in gp else list(gp)
        pv, pe, plats, bands = [0.0, 0.0], [0.0, 0.0], [], []
        if any(not foll.get(pl) for pl in booked):
            missing.append(c["name"])
        for pl in booked:
            f = foll.get(pl)
            if not f:
                continue
            v, e, t = expect(pl, f)
            for i in (0, 1):
                pv[i] += v[i]
                pe[i] += e[i]
                plat_exp[pl]["views"][i] += v[i] * n
                plat_exp[pl]["engagement"][i] += e[i] * n
            plat_exp[pl]["videos"] += n
            plats.append({"platform": pl, "followers": f, "size": SIZE_WORDS[t]})
            bands.append((pl, SIZE_WORDS[t]))
        for i in (0, 1):
            tot_v[i] += pv[i] * n
            tot_e[i] += pe[i] * n
        mine = [p for p in camp if p["code"] == c["code"]]
        pieces = len({p["pk"] for p in mine})
        views = sum(p.get("views") or 0 for p in mine)
        eng = sum(p.get("engagement") or 0 for p in mine)
        got = int(c.get("delivered") or 0)
        # The booked videos done so far: the ones on a booked platform (a copy pushed elsewhere adds its views to
        # them, it is not another video), or whatever went live when nothing is on a booked platform yet.
        done = min(len({p["pk"] for p in mine if p["platform"] in booked}) or pieces, n)
        avg_v = views / float(done) if done else None
        ratio = (avg_v / pv[0]) if (avg_v is not None and pv[0]) else None
        split = []
        for pl in sorted({p["platform"] for p in mine}, key=lambda x: (x not in booked, x)):
            q = [p for p in mine if p["platform"] == pl]
            split.append({"platform": pl, "booked": pl in booked, "videos": len({p["pk"] for p in q}),
                          "views": sum(p.get("views") or 0 for p in q), "engagement": sum(p.get("engagement") or 0 for p in q)})
        status = None if ratio is None else ("met" if ratio >= 1 else "close" if ratio >= 0.7 else "behind")
        nxt = next(((t, conf) for (i, t, conf) in sched.get(c["code"], [])), None)
        creators.append({"code": c["code"], "name": c["name"], "photo": c.get("photo"), "planned": int(c.get("planned") or 0),
                         "live": got, "platforms": plats, "size": (bands[0][1] if len({b for _, b in bands}) == 1 else " · ".join("%s %s" % (pl, b.replace(" followers", "")) for pl, b in bands)) if bands else "",
                         "exp_views": [_ri(pv[0], -2), _ri(pv[1], -2)] if pv[1] else None,
                         "views_per_video": round(avg_v) if avg_v is not None else None,
                         "eng_per_video": round(eng / float(done)) if done else None,
                         "views": views, "engagement": eng, "booked": booked, "by_platform": split,
                         "status": status, "ratio": ratio,
                         "next": ({"at": nxt[0], "confirmed": nxt[1]} if (nxt and not pieces) else None)})
    # ---- platform split
    prog = {i["key"]: i for i in r["progress"]["items"]}
    planf = plan_fraction(campaign, r["creators"])
    frac = planf[1] if planf else max(r["progress"]["elapsed"], 0.15)
    platforms = []
    for pl in gp:
        mine = [p for p in camp if p["platform"] == pl]
        v, e = sum(p.get("views") or 0 for p in mine), sum(p.get("engagement") or 0 for p in mine)
        ex = plat_exp[pl]
        own = (plan.get("by_platform") or {}).get(pl) or {}      # the plan's own estimate for this platform, when it kept one
        if own.get("safe") and own.get("expected"):
            ex = {"views": [own["safe"].get("views") or 0, own["expected"].get("views") or 0],
                  "engagement": [own["safe"].get("engagement") or 0, own["expected"].get("engagement") or 0]}
        row = {"platform": pl, "goal": True, "videos": len({p["pk"] for p in mine}), "views": v, "engagement": e,
               "views_safe": _ri(ex["views"][0], -2), "views_aim": _ri(ex["views"][1], -2),
               "eng_safe": _ri(ex["engagement"][0], -1), "eng_aim": _ri(ex["engagement"][1], -1)}
        for key, a, b in (("views", v, ex["views"][0]), ("eng", e, ex["engagement"][0])):
            due = b * frac
            row[key + "_status"] = ("met" if a >= b else "ontrack" if a >= due else "close" if due and a >= 0.7 * due else "behind") if b else None
        platforms.append(row)
    for pl in sorted({p["platform"] for p in camp} - set(gp)):
        mine = [p for p in camp if p["platform"] == pl]
        platforms.append({"platform": pl, "goal": False, "videos": len({p["pk"] for p in mine}),
                          "views": sum(p.get("views") or 0 for p in mine), "engagement": sum(p.get("engagement") or 0 for p in mine)})
    # ---- forecast
    planned = sum(int(c.get("planned") or 0) for c in r["creators"])
    # the forecast runs on every platform, like the targets (2026-10-23)
    done_pieces = len({p["pk"] for p in camp})
    fc = {"planned": planned, "live": done_pieces}
    gv = sum(p.get("views") or 0 for p in camp)
    ge = sum(p.get("engagement") or 0 for p in camp)
    # what is still owed is estimated on the goal platforms; the bonus platforms add their share on top
    gv_gp = sum(p.get("views") or 0 for p in camp if p["platform"] in gp)
    ge_gp = sum(p.get("engagement") or 0 for p in camp if p["platform"] in gp)
    lift = {"views": gv / float(gv_gp) if gv_gp else 1.0, "engagement": ge / float(ge_gp) if ge_gp else 1.0}
    for key, got, aim, per in (("views", gv, tot_v[1], "views"), ("engagement", ge, tot_e[1], "engagement")):
        it = prog.get(key)
        if not it or not done_pieces or not planned:
            continue
        run = got / float(done_pieces) * planned
        left = 0.0
        for cr in creators:
            owed = max(0, (cr["planned"] or 1) - (cr["live"] or 0))
            if owed and cr["exp_views"]:
                m = by_code.get(cr["code"])
                foll = creator_followers(m) if m is not None else {}
                for pl in gp:
                    if foll.get(pl):
                        v, e, _ = expect(pl, foll[pl])
                        left += owed * (v[1] if key == "views" else e[1])
        high = got + left * lift[key]
        lo, hi = sorted((run, high))
        goal = it["goal"]
        fc[key] = {"low": _ri(lo, -2 if lo >= 1000 else 0), "high": _ri(hi, -2 if hi >= 1000 else 0), "target": goal,
                   "verdict": "ahead" if lo >= goal else ("ontrack" if hi >= goal else "behind")}
    fc["early"] = done_pieces < 3
    # ---- still to come
    owed = []
    for c in r["creators"]:
        for (i, t, conf) in sched.get(c["code"], []):
            owed.append({"code": c["code"], "name": c["name"], "n": i, "of": int(c.get("planned") or 0), "at": t, "confirmed": conf})
    owed.sort(key=lambda x: (x["at"] is None, x["at"] or 0, x["name"]))
    # ---- pace: the expected curve follows the publishing plan, sampled by day
    pace = None
    if planf and window:
        t0, t1 = window[0], window[1] + MATURE_DAYS * 86400
        pts = [(t, plan_fraction(campaign, r["creators"], now=t)) for t in range(t0, t1 + 86400, 86400)]
        pace = {"start": t0, "end": t1, "posts": [[t, round(f[0], 4)] for t, f in pts if f],
                "mature": [[t, round(f[1], 4)] for t, f in pts if f]}
    elif campaign["starts_at"] and campaign["ends_at"]:
        pace = {"start": campaign["starts_at"], "end": campaign["ends_at"], "posts": None, "mature": None}
    # ---- data notes (only what changes what the client reads)
    notes = []
    G = r["gaps"]
    if G.get("likes_hidden"):
        notes.append("%d of %d posts hide likes, so engagement on those is comments only and they are left out of the engagement rate."
                     % (G["likes_hidden"], G["posts"]))
    if missing:
        notes.append("Follower counts are missing on a goal platform for %s, so their benchmark is partial." % ", ".join(missing))
    addons = [p["platform"] for p in platforms if not p["goal"]]
    if addons:
        notes.append("%s %s tracked as a bonus: no goal of their own, but their views and engagement count towards the targets." % (" and ".join(addons) if len(addons) < 3 else ", ".join(addons), "is" if len(addons) == 1 else "are"))
    if any(len(c["by_platform"]) > 1 or any(not x["booked"] for x in c["by_platform"]) for c in creators):
        notes.append("A creator's results count on every platform they posted on, so a video also pushed to another "
                     "platform adds its views and engagement to their target.")
    if any(p["kind"] == "story" for p in camp):
        notes.append("Stories are tracked as posts but have no view-based goal.")
    else:
        notes.append("Stories are not tracked in this campaign.")
    if planned and done_pieces < planned:
        notes.append("Videos keep gaining views for about a week after they go live, so recent videos read low at first.")
    return {"platforms": gp, "creators": creators, "split": platforms, "forecast": fc, "owed": owed, "pace": pace,
            "aim": {"views": _ri(tot_v[1], -3), "engagement": _ri(tot_e[1], -2)}, "notes": notes,
            "by_platform": _platform_goals(campaign, plan, gp, r, camp, members, sched, window)}


def target_progress(campaign, total, targets, plan=None):
    """Each target against what is done, and against where the campaign
    should be by now (straight-line through its dates), graded."""
    start, end = campaign["starts_at"], campaign["ends_at"]
    now = db.now()
    if start and end and end > start:
        elapsed = max(0.0, min(1.0, (now - start) / float(end - start)))
    else:
        elapsed = 1.0
    # ER on a video campaign is engagement ÷ views (what the planner targets);
    # on photo posts it is engagement ÷ followers.
    er = total["video_er"] if total.get("video_er") is not None else total["er"]
    actual = {"posts": total["posts"], "views": total["views"], "reach": total["reach"],
              "engagement": total["engagement"], "er": er, "clicks": total["clicks"]}
    out = []
    for key, goal in targets.items():
        if key == "reach":                    # reach is no longer a target (owner, 2026-10-18)
            continue
        got = actual.get(key) or 0
        if key == "er":                       # a rate is judged as is, not pro-rata
            expected = goal
        elif plan is not None:                # follow the publishing plan: no minimum, nothing due = nothing expected
            expected = goal * (plan[0] if key == "posts" else plan[1])
        else:
            expected = goal * max(elapsed, 0.15)   # the first days are not judged as failure
        ratio = got / float(expected) if expected else (1.0 if plan is not None else 0)
        out.append({"key": key, "goal": goal, "actual": got, "pct": got / float(goal) * 100 if goal else 0,
                    "expected": expected,
                    "grade": "good" if ratio >= 1 else ("moderate" if ratio >= 0.7 else "low")})
    # The whole campaign's progress: every target counts, each capped at its
    # goal, so it reads 100% only when views, reach, engagement and rate
    # are ALL met — beating one target cannot hide another that is short.
    overall = (sum(min(100.0, i["pct"]) for i in out) / len(out)) if out else None
    due = (sum(min(100.0, i["expected"] / i["goal"] * 100) for i in out) / len(out)) if out else None
    return {"elapsed": elapsed, "items": out, "overall": overall, "due": due,
            "all_met": bool(out) and all(i["actual"] >= i["goal"] for i in out)}


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


def track_records():
    """Our own record with each creator, from the campaigns we have run:
    ({code: {"campaigns", "posts", "er"}}, typical_er). `er` is reactions per
    view over their counted video posts, in %; `typical_er` the median across
    creators with a record (None until there are three), so a creator can be
    judged against what our own creators usually deliver."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT c.code, c.campaign_id, s.likes, s.comments, s.views FROM content c "
            "JOIN snapshots s ON s.id = (SELECT id FROM snapshots WHERE content_id = c.id ORDER BY at DESC, id DESC LIMIT 1) "
            "WHERE c.hidden = 0 AND c.section = 'campaign'").fetchall()
    per = {}
    for r in rows:
        if not r["views"]:
            continue
        d = per.setdefault(r["code"], {"camps": set(), "posts": 0, "react": 0, "views": 0})
        d["camps"].add(r["campaign_id"]); d["posts"] += 1
        d["react"] += (r["likes"] or 0) + (r["comments"] or 0); d["views"] += r["views"]
    out = {c: {"campaigns": len(d["camps"]), "posts": d["posts"], "er": 100.0 * d["react"] / d["views"]}
           for c, d in per.items() if d["views"]}
    ers = sorted(v["er"] for v in out.values())
    typical = (ers[len(ers) // 2] if len(ers) % 2 else (ers[len(ers) // 2 - 1] + ers[len(ers) // 2]) / 2) if len(ers) >= 3 else None
    return out, typical


_AUD_CACHE = {"at": 0.0, "v": None}
AUD_TTL = 3600


def catalogue_audience():
    """The average audience of every creator profile that has an uploaded
    analysis: for each country, its mean share across those profiles (a profile
    that does not list the country counts as 0). Returns (rows, profiles).

    One query for the whole roster, not four per creator (at 14,000 creators the old loop made 57,000
    queries and took 40 s, and the campaign report waited for it); kept for an hour."""
    import time as _time
    import json as _json
    import analysis as _an
    if _AUD_CACHE["v"] is not None and _time.time() - _AUD_CACHE["at"] < AUD_TTL:
        return _AUD_CACHE["v"]
    with db.connect() as conn:
        crow = {r["code"]: r for r in conn.execute("SELECT code, platform, profiles FROM creators")}
        rows = conn.execute("SELECT code, platform, json_extract(data, '$.audience.countries') AS c "
                            "FROM creator_analysis ORDER BY updated_at DESC").fetchall()
    by = {}
    for r in rows:
        by.setdefault(r["code"], []).append(r)
    sums, n = {}, 0
    for code, lst in by.items():
        cr = crow.get(code)
        main = _an.creator_platforms(cr)[0] if cr else "Instagram"
        pick = next((r for r in lst if r["platform"] == main), lst[0])
        try:
            countries = _json.loads(pick["c"]) if pick["c"] else []
        except ValueError:
            countries = []
        got = {}
        for row in countries or []:
            cc, pct_ = (row.get("code") or "").upper(), row.get("pct")
            if len(cc) == 2 and isinstance(pct_, (int, float)):
                got[cc] = got.get(cc, 0.0) + pct_
        if not got:
            continue
        n += 1
        for cc, v in got.items():
            sums[cc] = sums.get(cc, 0.0) + v
    out = ({cc: v / n for cc, v in sums.items()} if n else {}), n
    _AUD_CACHE["v"], _AUD_CACHE["at"] = out, _time.time()
    return out


def target_country(campaign):
    """The market the campaign is for, from its selection's target (an ISO code), or None."""
    try:
        sid = campaign["selection_id"] if "selection_id" in campaign.keys() else None
        sel = db.selection(sid) if sid else None
        t = json.loads((sel["target"] if sel is not None and "target" in sel.keys() else None) or "{}")
    except (ValueError, TypeError):
        return None
    cc = str(t.get("country") or "").strip().upper()
    return cc if len(cc) == 2 and cc.isalpha() else None


def audience_mix(creators, reach_by_code, target=None):
    """Where the creators' audience is (owner, 2026-10-18): each creator who has an uploaded full analysis
    counts with their own audience, weighted by the reach they delivered (equal weights while no reach is
    counted yet). Creators without an analysis are NOT filled in with the catalogue average any more, which
    read as a verdict on the campaign; their share is reported as not yet analysed.

    basis: "own" (every creator with reach is analysed) or "partial". coverage is the share of reach that
    came from analysed creators. ``target`` (an ISO country) adds where the campaign's market ranks."""
    rows_in = []
    for c in creators:
        a = db.analysis(c["code"])
        countries = ((a or {}).get("data") or {}).get("audience", {}).get("countries") or []
        rows_in.append((c, float(reach_by_code.get(c["code"]) or 0), countries))
    all_reach = sum(w for _, w, _ in rows_in)
    equal = all_reach <= 0
    own, covered, total = {}, 0.0, 0.0
    for c, w, countries in rows_in:
        w = 1.0 if equal else w
        total += w
        if not countries or not w:
            continue
        covered += w
        for row in countries:
            cc, pct_ = (row.get("code") or "").upper(), row.get("pct")
            if len(cc) == 2 and isinstance(pct_, (int, float)):
                own[cc] = own.get(cc, 0.0) + w * pct_ / 100.0
    if not covered or not own:
        return None
    ranked = sorted(({"code": k, "pct": v / covered * 100} for k, v in own.items()), key=lambda r: -r["pct"])
    coverage = covered / total * 100 if total else 0
    out = {"countries": ranked[:8], "coverage": coverage, "basis": "own" if coverage >= 99 else "partial",
           "analysed": sum(1 for _, _, ct in rows_in if ct), "creators": len(rows_in)}
    if target:
        t = next(((n + 1, r) for n, r in enumerate(ranked) if r["code"] == target), None)
        out["target"] = {"code": target, "pct": t[1]["pct"] if t else 0.0, "rank": t[0] if t else None}
    return out


def next_capture(campaign):
    """When this campaign's posts are next captured by a scheduled job (epoch seconds, Riyadh slots), or None."""
    import time as _t
    now = db.now()
    best = None
    with db.connect() as conn:
        jobs = conn.execute("SELECT schedule, at_time, weekday FROM api_jobs WHERE enabled = 1 AND source = ? "
                            "AND schedule IN ('daily','weekly')", ("campaign:%d" % campaign["id"],)).fetchall()
    for j in jobs:
        try:
            hh, mm = (int(x) for x in j["at_time"].split(":"))
        except (ValueError, AttributeError):
            continue
        local = now + 3 * 3600
        slot = local - local % 86400 + hh * 3600 + mm * 60 - 3 * 3600
        for d in range(0, 9):
            t = slot + d * 86400
            if t <= now:
                continue
            if j["schedule"] == "weekly" and _t.gmtime(t + 3 * 3600).tm_wday != j["weekday"]:
                continue
            best = t if best is None or t < best else best
            break
    if best and campaign["ends_at"] and best > campaign["ends_at"]:
        return None
    return best


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
            "reach_real", "impressions_real", "video", "story", "health", "likes_hidden", "gaps", "exposure",
            "pk", "piece_size", "views_hidden")
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
                                 "clicks", "planned", "delivered", "pending_status", "pending_date",
                                 "profiles", "band", "er_grade",
                                 "video_er_grade", "score", "rank", "badge", "seen", "parts", "hidden_likes")
               if k in c}
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
           "updated_at": r["updated_at"], "next_update_at": next_capture(campaign),
           "verdict": r["verdict"], "objective": r["objective"], "targets_auto": r.get("targets_auto", False),
           "plan": plans.client_view(plans.plan_of(k)), "gaps": r["gaps"],
           "progress": r["progress"] if vis["reach"] else {"elapsed": r["progress"]["elapsed"],
                                                            "items": [i for i in r["progress"]["items"]
                                                                      if i["key"] not in ("reach",)]},
           "benchmarks": {"er": r["benchmarks"]["er"], "video_er": r["benchmarks"]["video_er"],
                          "view_rate": r["benchmarks"]["view_rate"], "story_rate": r["benchmarks"]["story_rate"],
                          "ctr": r["benchmarks"]["ctr"], "bands": BAND_LABEL,
                          "er_goal": r["benchmarks"].get("er_goal")}}
    if not vis["clicks"]:
        out["progress"]["items"] = [i for i in out["progress"]["items"] if i["key"] != "clicks"]
    its = out["progress"]["items"]
    out["progress"]["overall"] = (sum(min(100.0, i["pct"]) for i in its) / len(its)) if its else None
    out["progress"]["due"] = (sum(min(100.0, i["expected"] / i["goal"] * 100) for i in its) / len(its)) if its else None
    out["progress"]["all_met"] = bool(its) and all(i["actual"] >= i["goal"] for i in its)
    reach_by = {c["code"]: (c.get("reach") or 0) + (c.get("views") or 0) for c in r["creators"]}
    out["audience"] = audience_mix(r["creators"], reach_by, target_country(campaign)) if vis["audience"] else None
    # What people said (2026-10-19) takes the audience card's place and its visibility switch.
    out["comments"] = None
    if vis["audience"]:
        try:
            import comments
            out["comments"] = comments.client_view(k)
        except Exception as exc:
            print("comments: client view skipped:", repr(exc)[:160], flush=True)
    out["goals"] = goals_view(campaign, r)
    for g in (out["goals"] or {}).get("creators", []):
        g["photo"] = pics.get(g["code"])
        g.pop("ratio", None)
    for bp in ((out["goals"] or {}).get("by_platform") or {}).values():
        for g in bp["creators"]:
            g["photo"] = pics.get(g["code"])
    out["reach_basis"] = {"per_view": factors()["report_reach_per_view"]}
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
    # Clicks to sales (owner, 2026-10-20): promo-code / retailer sales for the campaign, stored as one client-safe
    # summary in settings.campaign_sales {campaign id: {...}}; shown in the affiliate-clicks slot.
    out["sales"] = None
    if vis["clicks"]:
        try:
            sv = (db.setting("campaign_sales") or {}).get(str(k["id"]))
            out["sales"] = sv if isinstance(sv, dict) and sv.get("totals") else None
        except (AttributeError, TypeError, ValueError):
            pass
    out["rev"] = report_rev(out)
    return out
