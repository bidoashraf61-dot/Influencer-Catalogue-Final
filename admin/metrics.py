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
    return out


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

    posts = []
    for c in content:
        n = post_numbers(c, f)
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
        row = {"code": code, "name": m["name"] or code, "photo": m["photo"],
               "followers": m["followers"], **t}
        if internal:
            row["cost"] = m["campaign_cost"]
            row["cpm"] = (m["campaign_cost"] / float(t["exposure"]) * 1000
                          if m["campaign_cost"] and t["exposure"] else None)
            row["cpc"] = (m["campaign_cost"] / float(t["clicks"])
                          if m["campaign_cost"] and t["clicks"] else None)
        creators.append(row)

    out = {"campaign": {"id": cid, "name": campaign["name"], "client": campaign["client"],
                        "status": campaign["status"], "starts_at": campaign["starts_at"],
                        "ends_at": campaign["ends_at"], "platform": campaign["platform"]},
           "total": total, "creators": creators, "posts": posts,
           "history": db.content_history(cid), "clicks": clicks,
           "emv_set": bool(rates), "visibility": vis, "factors": f,
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


def client_report(campaign):
    """The report as the client may see it: no cost, no internal fields, no
    ratings, and only the sections switched on for them."""
    r = report(campaign, internal=False)
    vis = r["visibility"]
    keep = ("id", "code", "platform", "kind", "url", "posted_at", "caption", "thumb",
            "section", "likes", "comments", "engagement", "views", "reach", "impressions",
            "shares", "saves", "er", "video_er", "imp_er", "emv", "real", "reach_real",
            "impressions_real", "video", "story")
    posts = [{k: p.get(k) for k in keep} for p in r["posts"]
             if vis["all_content"] or p["section"] == "campaign"]
    names = {c["code"]: c["name"] for c in r["creators"]}
    for p in posts:
        p["creator"] = names.get(p["code"], p["code"])
        if not vis["emv"]:
            p.pop("emv", None)
        if not vis["reach"]:
            for k in ("reach", "impressions", "imp_er", "reach_real", "impressions_real"):
                p.pop(k, None)
    creators = []
    for c in r["creators"]:
        row = {k: c[k] for k in ("code", "name", "followers", "posts", "likes", "comments",
                                 "engagement", "views", "reach", "impressions", "er",
                                 "video_er", "emv", "clicks")}
        if not vis["emv"]:
            row.pop("emv")
        if not vis["clicks"]:
            row.pop("clicks")
        if not vis["reach"]:
            row.pop("reach"); row.pop("impressions")
        creators.append(row)
    total = dict(r["total"])
    if not vis["emv"]:
        total.pop("emv", None)
    if not vis["clicks"]:
        total.pop("clicks", None); total.pop("ctr", None)
    if not vis["reach"]:
        for k in ("reach", "impressions", "imp_er", "exposure"):
            total.pop(k, None)
    out = {"campaign": r["campaign"], "total": total, "creators": creators, "posts": posts,
           "history": r["history"], "visibility": vis, "updated_at": r["updated_at"]}
    if vis["clicks"]:
        cl = r["clicks"]
        out["clicks"] = {k: cl[k] for k in ("clicks", "uniques", "by_day", "by_app",
                                            "by_device", "by_country")}
        out["clicks"]["by_creator"] = [{"k": names.get(x["k"], x["k"]), "n": x["n"]}
                                       for x in cl["by_creator"]]
    return out
