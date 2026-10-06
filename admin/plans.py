"""Campaign planner: benchmarks per platform, templates per objective, and an
ROI calculator that turns a client's budget and the creators booked into the
targets to agree.

Three sources sit side by side, so a target never rests on one guess:

  industry guide   LIBRARY below — conservative published ranges, editable in
                   Settings → Benchmark library. [safe, expected] per tier.
  HelloVoice data  what our own tracked campaigns actually delivered, per
                   platform (house_benchmarks), once there is enough of it.
  this campaign    the creators booked × the benchmarks for their size,
                   adjusted for the product category.

The target to agree is the MINIMUM ACCEPTED: the lower of
  - what the budget must buy to be fair value (budget ÷ the most a client
    should pay per 1,000 views / per engagement / per click), and
  - what the booked creators can safely deliver (safe benchmarks).
So HelloVoice commits to what is both worth the money and within reach, and
exceeds it. When the safe estimate is below the value floor the planner says
so: the plan needs more (or smaller, better-value) creators, or a lower fee.

Every rate here is a guide, labelled as such wherever it is shown.
"""

import json

import db

TIERS = ["nano", "micro", "mid", "macro", "mega"]
TIER_LABEL = {"nano": "Nano (<10K)", "micro": "Micro (10–100K)", "mid": "Mid (100–500K)",
              "macro": "Macro (500K–1M)", "mega": "Mega (1M+)"}
TIER_FOLLOWERS = {"nano": 6000, "micro": 35000, "mid": 200000, "macro": 700000, "mega": 1500000}
PLATFORMS = ["Instagram", "TikTok", "Snapchat", "YouTube"]


def tier_of(followers):
    f = followers or 0
    return "nano" if f < 10000 else "micro" if f < 100000 else "mid" if f < 500000 \
        else "macro" if f < 1000000 else "mega"


# --------------------------------------------------------------- library --
#
# Per platform, per tier, [safe, expected]:
#   view_rate  views of one video ÷ the creator's followers, %
#   eng_rate   engagement (likes + comments) ÷ views, %
# Per platform:
#   reach_per_view  unique people ÷ views (replays and repeat viewers)
#   ctr             link clicks ÷ views, % — only with a tracked link
#   cpm / cpe / cpc the MOST a client should pay (SAR) per 1,000 views, per
#                   engagement and per click for the campaign to be fair value:
#                   [acceptable, good]. Below "good" is strong value.
#
# Ranges are deliberately at the lower end of published 2025 reports
# (HypeAuditor, Favikon, Emplicit, Influencer Marketing Hub, Kolsquare MENA)
# and GCC rate cards, so a target built on them is one we can beat.

LIBRARY = {
    "Instagram": {
        "view_rate": {"nano": [12, 25], "micro": [10, 22], "mid": [8, 18], "macro": [5, 12], "mega": [3, 8]},
        "eng_rate": {"nano": [3.0, 5.5], "micro": [2.5, 4.5], "mid": [2.0, 3.5], "macro": [1.5, 2.8], "mega": [1.0, 2.0]},
        "reach_per_view": 0.85, "ctr": [0.3, 0.8],
        "cpm": [45, 25], "cpe": [3.0, 1.5], "cpc": [6, 3],
        "note": "Reels. Feed photos reach about half a reel's audience; stories 4–8% of followers.",
    },
    "TikTok": {
        "view_rate": {"nano": [20, 45], "micro": [15, 35], "mid": [10, 25], "macro": [7, 18], "mega": [5, 12]},
        "eng_rate": {"nano": [4.0, 7.5], "micro": [3.5, 6.0], "mid": [3.0, 5.0], "macro": [2.5, 4.5], "mega": [2.0, 3.5]},
        "reach_per_view": 0.8, "ctr": [0.2, 0.6],
        "cpm": [30, 15], "cpe": [2.0, 1.0], "cpc": [5, 2.5],
        "note": "Views swing more than on Instagram — one post can travel far beyond followers.",
    },
    "Snapchat": {
        "view_rate": {"nano": [8, 15], "micro": [7, 13], "mid": [6, 11], "macro": [5, 9], "mega": [4, 7]},
        "eng_rate": {"nano": [0.5, 1.2], "micro": [0.5, 1.0], "mid": [0.4, 0.9], "macro": [0.3, 0.8], "mega": [0.3, 0.6]},
        "reach_per_view": 0.95, "ctr": [0.4, 1.0],
        "cpm": [35, 20], "cpe": [8.0, 4.0], "cpc": [5, 2.5],
        "note": "Story views. Snapchat shows no public likes, so judge it on views and swipe-ups.",
    },
    "YouTube": {
        "view_rate": {"nano": [6, 15], "micro": [5, 12], "mid": [4, 10], "macro": [3, 8], "mega": [2, 6]},
        "eng_rate": {"nano": [2.0, 4.0], "micro": [1.8, 3.5], "mid": [1.5, 3.0], "macro": [1.2, 2.5], "mega": [1.0, 2.0]},
        "reach_per_view": 0.85, "ctr": [0.3, 0.9],
        "cpm": [60, 35], "cpe": [4.0, 2.0], "cpc": [7, 3.5],
        "note": "Long videos and Shorts. Views keep coming for weeks; judge at 30 days.",
    },
}

# Engagement varies by what is sold: regulated health content draws fewer
# likes, food and beauty more. Applied to eng_rate only.
CATEGORIES = {
    "pharma": ("Pharma / OTC / healthcare", 0.8),
    "baby": ("Baby & mother care", 1.0),
    "beauty": ("Beauty & skincare", 1.0),
    "fmcg": ("FMCG / food & drink", 1.05),
    "retail": ("Retail / pharmacy / e-commerce", 0.95),
    "tech": ("Tech & telecom", 0.85),
    "auto": ("Automotive", 0.9),
    "other": ("Other", 1.0),
}

# What each objective puts first, and so which targets the client sees as
# the headline. The leaderboard weights live in metrics.OBJECTIVES.
OBJECTIVE_KPIS = {"awareness": ["views", "reach"], "engagement": ["engagement", "er"],
                  "traffic": ["clicks", "views"], "balanced": ["views", "engagement", "er"]}

# Ready briefs to start from; everything they set can be changed on the page.
TEMPLATES = {
    "awareness-ig-reels": {"label": "Awareness — Instagram reels", "objective": "awareness", "platform": "Instagram",
                           "category": "baby", "mix": {"micro": 12, "mid": 6, "macro": 2},
                           "why": "Reach a new audience fast; judged on views and reach."},
    "awareness-pharma": {"label": "Pharma / OTC awareness — Instagram", "objective": "awareness", "platform": "Instagram",
                         "category": "pharma", "mix": {"micro": 10, "mid": 4},
                         "why": "Regulated claims, approved scripts; lower engagement is normal, views are the headline."},
    "awareness-tiktok": {"label": "Awareness — TikTok", "objective": "awareness", "platform": "TikTok",
                         "category": "beauty", "mix": {"nano": 10, "micro": 10, "mid": 3},
                         "why": "Cheapest views in KSA; many small creators beat one big one."},
    "engagement-ugc": {"label": "Engagement — UGC & reviews", "objective": "engagement", "platform": "Instagram",
                       "category": "beauty", "mix": {"nano": 15, "micro": 10},
                       "why": "Comments, saves and trust; nano and micro creators engage best."},
    "launch-mixed": {"label": "Product launch — Instagram + TikTok", "objective": "balanced", "platform": "Instagram",
                     "category": "fmcg", "mix": {"micro": 10, "mid": 5, "macro": 1},
                     "why": "A burst in launch week: views first, then engagement."},
    "traffic-affiliate": {"label": "Traffic / sales — tracked links", "objective": "traffic", "platform": "Instagram",
                          "category": "retail", "mix": {"micro": 15, "mid": 3},
                          "why": "Every creator has their own link; judged on clicks and cost per click."},
    "snap-stories": {"label": "Awareness — Snapchat stories", "objective": "awareness", "platform": "Snapchat",
                     "category": "fmcg", "mix": {"micro": 8, "mid": 4, "macro": 1},
                     "why": "Snapchat reaches 75% of Saudi adults; judged on story views."},
}


def library():
    """The library with any edits saved in Settings laid over the defaults."""
    out = json.loads(json.dumps(LIBRARY))
    got = db.setting("benchmark_library") or {}
    for plat, vals in (got.items() if isinstance(got, dict) else []):
        if plat not in out or not isinstance(vals, dict):
            continue
        for key, v in vals.items():
            if key in ("view_rate", "eng_rate") and isinstance(v, dict):
                for t, pair in v.items():
                    if t in TIERS and isinstance(pair, list) and len(pair) == 2:
                        out[plat][key][t] = [float(pair[0]), float(pair[1])]
            elif key in ("ctr", "cpm", "cpe", "cpc") and isinstance(v, list) and len(v) == 2:
                out[plat][key] = [float(v[0]), float(v[1])]
            elif key == "reach_per_view" and isinstance(v, (int, float)) and 0 < v <= 1:
                out[plat][key] = float(v)
    return out


# ------------------------------------------------------- our own numbers --

def house_benchmarks():
    """What HelloVoice's tracked campaigns actually delivered, per platform:
    view rate and engagement rate per video (visible likes only), and cost
    per 1,000 views per campaign. Needs posts to mean anything; `posts` says
    how many it rests on."""
    out = {}
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT c.campaign_id, c.platform, c.kind, c.followers, s.likes, s.comments, s.views "
            "FROM content c JOIN snapshots s ON s.id = (SELECT id FROM snapshots x WHERE x.content_id = c.id "
            "ORDER BY x.at DESC, x.id DESC LIMIT 1) WHERE c.hidden = 0 AND c.section = 'campaign'").fetchall()
        costs = {r["id"]: r["cost"] for r in conn.execute("SELECT id, cost FROM campaigns")}
    by = {}
    for r in rows:
        if r["kind"] not in db.VIDEO_KINDS or not r["views"]:
            continue
        x = by.setdefault(r["platform"], {"vr": [], "er": [], "views": {}, "posts": 0})
        x["posts"] += 1
        if r["followers"]:
            x["vr"].append(r["views"] / float(r["followers"]) * 100)
        if r["likes"] is not None:
            x["er"].append(((r["likes"] or 0) + (r["comments"] or 0)) / float(r["views"]) * 100)
        x["views"][r["campaign_id"]] = x["views"].get(r["campaign_id"], 0) + r["views"]
    for plat, x in by.items():
        cpms = [costs[c] / float(v) * 1000 for c, v in x["views"].items() if costs.get(c) and v]
        out[plat] = {"posts": x["posts"], "campaigns": len(x["views"]),
                     "view_rate": _median(x["vr"]), "eng_rate": _median(x["er"]),
                     "cpm": _median(cpms)}
    return out


def _median(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


# ------------------------------------------------------------ calculator --

def mix_from_campaign(campaign):
    """[{tier, posts, followers}] from the creators booked: each creator's
    planned posts (1 when none is set) and their own follower count."""
    rows = []
    for m in db.campaign_creators(campaign["id"]):
        rows.append({"tier": tier_of(m["followers"]), "posts": m["planned"] or 1,
                     "followers": m["followers"] or 0, "name": m["name"] or m["cc_code"]})
    return rows


def mix_from_counts(counts, followers=None):
    """[{tier, posts, followers}] from posts per tier, at typical sizes."""
    fol = dict(TIER_FOLLOWERS, **(followers or {}))
    return [{"tier": t, "posts": int(counts.get(t) or 0), "followers": fol[t]}
            for t in TIERS if int(counts.get(t) or 0) > 0]


def calculate(brief, mix):
    """The plan. `brief`: platform, objective, category, budget (SAR, what the
    client pays), tracked_links (bool). `mix`: from mix_from_*."""
    lib = library()
    plat = brief.get("platform") if brief.get("platform") in lib else "Instagram"
    L = lib[plat]
    cat = brief.get("category") if brief.get("category") in CATEGORIES else "other"
    cf = CATEGORIES[cat][1]
    objective = brief.get("objective") if brief.get("objective") in OBJECTIVE_KPIS else "balanced"
    budget = float(brief.get("budget") or 0)
    links = bool(brief.get("tracked_links")) or objective == "traffic"

    est = {"safe": {"views": 0.0, "engagement": 0.0}, "expected": {"views": 0.0, "engagement": 0.0}}
    followers_x_posts, posts = 0.0, 0
    tiers = {}
    for row in mix:
        t, n, f = row["tier"], row["posts"], row["followers"] or TIER_FOLLOWERS[row["tier"]]
        posts += n
        followers_x_posts += f * n
        tt = tiers.setdefault(t, {"posts": 0, "views": [0.0, 0.0], "engagement": [0.0, 0.0]})
        tt["posts"] += n
        for i, kind in enumerate(("safe", "expected")):
            v = f * L["view_rate"][t][i] / 100.0 * n
            e_ = v * L["eng_rate"][t][i] * cf / 100.0
            est[kind]["views"] += v
            est[kind]["engagement"] += e_
            tt["views"][i] += v
            tt["engagement"][i] += e_
    for kind, i in (("safe", 0), ("expected", 1)):
        x = est[kind]
        x["posts"] = posts
        x["reach"] = x["views"] * L["reach_per_view"]
        x["er"] = x["engagement"] / x["views"] * 100 if x["views"] else None
        x["clicks"] = x["views"] * L["ctr"][i] / 100.0 if links else None

    # The value floor: what the budget has to buy to be worth it.
    floor = {}
    if budget:
        floor["views"] = budget / L["cpm"][0] * 1000
        floor["reach"] = floor["views"] * L["reach_per_view"]
        floor["engagement"] = budget / L["cpe"][0]
        if links:
            floor["clicks"] = budget / L["cpc"][0]

    target, checks = {"posts": posts}, []
    for key in ("views", "reach", "engagement", "clicks"):
        safe = est["safe"].get(key)
        if safe is None:
            continue
        fl = floor.get(key)
        if fl is None:
            target[key] = safe
            continue
        target[key] = min(fl, safe)
        checks.append({"key": key, "floor": fl, "safe": safe, "expected": est["expected"][key],
                       "ok": safe >= fl, "margin": (safe / fl - 1) * 100 if fl else None})
    if est["safe"]["er"] is not None:
        target["er"] = est["safe"]["er"]
    target = {k: _round(k, v) for k, v in target.items() if v}

    roi = {}
    if budget:
        for kind in ("safe", "expected"):
            x = est[kind]
            roi[kind] = {"cpm": budget / x["views"] * 1000 if x["views"] else None,
                         "cpe": budget / x["engagement"] if x["engagement"] else None,
                         "cpc": budget / x["clicks"] if x.get("clicks") else None}
        roi["ceilings"] = {"cpm": L["cpm"], "cpe": L["cpe"], "cpc": L["cpc"] if links else None}

    notes = []
    if not posts:
        notes.append("Add creators or posts per tier to calculate.")
    short = [c for c in checks if not c["ok"] and c["key"] in OBJECTIVE_KPIS[objective]]
    if short:
        notes.append("The booked creators are unlikely to deliver fair value on "
                     + ", ".join(c["key"] for c in short)
                     + " for this budget. Add creators (micro and mid give the most views per riyal), "
                       "or lower the fee — the targets below are what they can safely deliver.")
    elif checks:
        notes.append("The safe estimate clears the value floor, so the targets are the minimum the "
                     "budget must buy. Plan to beat them.")
    if cat == "pharma":
        notes.append("Pharma content: engagement is planned 20% lower — approved scripts and no claims draw fewer likes.")
    if plat == "Instagram":
        notes.append("Instagram hides likes when a creator switches them off; ask those creators for insights.")

    return {"platform": plat, "objective": objective, "category": cat, "budget": budget or None,
            "links": links, "posts": posts,
            "avg_followers": followers_x_posts / posts if posts else None,
            "estimate": {k: {kk: _round(kk, vv) for kk, vv in v.items() if vv is not None} for k, v in est.items()},
            "floor": {k: _round(k, v) for k, v in floor.items()},
            "target": target, "checks": checks, "roi": roi, "notes": notes,
            "primary": OBJECTIVE_KPIS[objective], "tiers": tiers,
            "benchmark": benchmark_ranges(L, mix, cf)}


def benchmark_ranges(L, mix, cf=1.0):
    """The guide ranges for this campaign's mix, weighted by posts per tier —
    what the client sees beside each target."""
    n = sum(r["posts"] for r in mix) or 0
    if not n:
        return {}
    vr = [sum(L["view_rate"][r["tier"]][i] * r["posts"] for r in mix) / n for i in (0, 1)]
    er = [sum(L["eng_rate"][r["tier"]][i] * r["posts"] for r in mix) / n * cf for i in (0, 1)]
    return {"view_rate": [round(vr[0], 1), round(vr[1], 1)], "eng_rate": [round(er[0], 2), round(er[1], 2)],
            "ctr": L["ctr"], "reach_per_view": L["reach_per_view"]}


def _round(key, v):
    if v is None:
        return None
    if key == "er":
        return round(v, 2)
    if key in ("posts",):
        return int(v)
    if v >= 100000:
        return int(round(v, -3))
    if v >= 1000:
        return int(round(v, -2))
    return int(round(v))


def plan_of(campaign):
    try:
        return json.loads(campaign["plan"] or "null") if "plan" in campaign.keys() else None
    except ValueError:
        return None


def client_view(plan):
    """What of a saved plan the client may see: the benchmark ranges and the
    estimate, never the budget, the value floor or the cost ratios."""
    if not plan:
        return None
    return {"platform": plan.get("platform"), "category": CATEGORIES.get(plan.get("category"), ("", 1))[0],
            "template": (TEMPLATES.get(plan.get("template") or "") or {}).get("label"),
            "benchmark": plan.get("benchmark") or {},
            "estimate": (plan.get("estimate") or {}).get("expected") or {},
            "safe": (plan.get("estimate") or {}).get("safe") or {}}
