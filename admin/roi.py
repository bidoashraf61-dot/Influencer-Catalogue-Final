"""ROI Calculator for clients (HELVY Connect), version 3 (fix batch 6, Bido 2026-10-10).

What a selection (or a mix of creator sizes) can deliver, as RANGES, and a planner that says
how to get more. No cost metrics, no prices, no market verdict, no frequency: the client sees
views, reach, interactions and clicks, how sure we are, and a short ranked list of ways to
improve. The market (KSA, UAE, Egypt) does not change a number: one set per platform and size.

The chain, per post (one post per creator per chosen platform):

  views         the creator's MEDIAN views (measured, TikTok after the 100-post sample)
                else followers x the median view rate of same-size peers on that platform
                (benchmarks.py, own roster, needs 30 peers)
                else the creator's measured AVERAGE views / reel plays
                else followers x the global guide rate (Settings -> Benchmark library)
  interactions  views x the creator's own engagement rate (per view on TikTok/YouTube, reel
                likes+comments per play on Instagram, else per follower), else the same-size
                peer median, else the global guide
  reach         views x reach-per-view (guide, an estimate)
  clicks        views x CTR (guide, an estimate; only a tracked link produces clicks)
  efficiency    0.8 + 0.4 x (creator score / 100), applied to views, interactions and clicks.
                The score is fit.score for the selection's objective; a mix of sizes has no
                creators, so it uses the peer-median score 50 (factor 1.0).

Honest ranges: each post carries a margin 0.48 x sqrt(20 / n) from the number of posts n
its own numbers rest on (0.48 when they are estimated from followers only). A selection's
range is the sum +/- sqrt(sum((margin_i x value_i)^2)), the errors treated as independent,
never narrower than +/-10 %, shown to two significant figures.

The planner (advice only, never a verdict, never a price): given goals, a budget and
platforms it picks a mix of creator sizes that maximises the goal inside the creators' share
of the budget (Settings roi_creator_share, planning prices roi_planning_prices; neither is
ever sent to a client) and, when a selection is open, ranks ways to close the gap by
performance (score, views per follower), never by price.

    estimate(goal, budget, platforms, market, creators=None, mix=None, goals=None, second_posts=None)
    plan(goals, budget, platforms, ...)       the suggested mix and its ranges
    advise(...)                               "Ways to improve", max 3, each with an action
    creators_of(selection, which)             a selection's creators as the calculator needs them
    save(...) / latest_for(sel_id)            an estimate kept with a selection
    versus(campaign)                          saved ranges against the live report
"""
import json
import math
import re as _re

import benchmarks
import db
import plans

GOALS = ("awareness", "engagement", "traffic")
GOAL_LABEL = {"awareness": "Awareness", "engagement": "Engagement", "traffic": "Traffic"}
PLATFORMS = ("Instagram", "TikTok", "Snapchat", "YouTube")
MARKETS = {"SA": "Saudi Arabia", "AE": "UAE", "EG": "Egypt"}
TIER_ORDER = ["mega", "macro", "mid", "micro", "nano"]
TIER_NAME = {"mega": ("Mega", "1M+ followers"), "macro": ("Macro", "500K–1M"), "mid": ("Mid", "100K–500K"),
             "micro": ("Micro", "20K–100K"), "nano": ("Nano", "Under 20K")}
SIZE_WORD = {"mega": "mega", "macro": "macro", "mid": "mid-size", "micro": "micro", "nano": "nano"}

# HelloVoice planning assumptions (not in the industry guide). Editable as the "roi_assumptions" setting.
ASSUMPTIONS = {"impressions_per_view": {"Instagram": 1.5, "TikTok": 1.2, "Snapchat": 1.0, "YouTube": 1.1},
               "landing_rate": 0.8}
MARGIN_BASE = 0.48                # margin of a post whose numbers rest on 20 posts, or on followers only
MARGIN_N = 20
RANGE_FLOOR = 0.10                # a selection's range is never narrower than +/-10 %
SHARE_DEFAULT = 0.6               # creators' share of the client's budget (setting roi_creator_share, never shown)
PRICES_DEFAULT = {"nano": 650, "micro": 1300, "mid": 3500, "macro": 6500, "mega": 30000}   # SAR per post (setting roi_planning_prices, never shown)
ESTIMATE_LINE = "Estimate, not a result. Real results depend on the content, the timing and the audience."
OVERLAP = 0.92                    # each further post in the same platform and size adds 8 % less (audience overlap)

SCHEMA = """
CREATE TABLE IF NOT EXISTS roi_estimates (
    id INTEGER PRIMARY KEY,
    code_id INTEGER,                 -- who saved it
    selection_id INTEGER,            -- the selection it is kept with
    goal TEXT NOT NULL,
    input TEXT NOT NULL,             -- JSON: budget, platforms, market, source
    result TEXT NOT NULL,            -- JSON: what the calculator showed
    created_at INTEGER NOT NULL,
    created_by TEXT
);
CREATE INDEX IF NOT EXISTS roi_sel ON roi_estimates(selection_id, created_at);
"""


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)


def tier_of(followers):
    """The calculator's five sizes (nano under 20K, micro 20-100K, mid 100-500K, macro 500K-1M, mega 1M+)."""
    return benchmarks.size_of(followers)


def settings():
    """(creator_share, planning_prices): internal planner settings, never sent to a client."""
    share, prices = SHARE_DEFAULT, dict(PRICES_DEFAULT)
    try:
        v = db.setting("roi_creator_share")
        if isinstance(v, (int, float)) and 0.1 <= float(v) <= 1:
            share = float(v)
        got = db.setting("roi_planning_prices")
        if isinstance(got, dict):
            for t in prices:
                x = got.get(t)
                if isinstance(x, (int, float)) and x > 0:
                    prices[t] = float(x)
    except Exception:
        pass
    return share, prices


def assumptions():
    out = json.loads(json.dumps(ASSUMPTIONS))
    try:
        got = db.setting("roi_assumptions") or {}
    except Exception:
        got = {}
    if isinstance(got, dict):
        if isinstance(got.get("impressions_per_view"), dict):
            for p, f in got["impressions_per_view"].items():
                if p in out["impressions_per_view"] and isinstance(f, (int, float)) and 1 <= f <= 5:
                    out["impressions_per_view"][p] = float(f)
        if isinstance(got.get("landing_rate"), (int, float)) and 0 < got["landing_rate"] <= 1:
            out["landing_rate"] = float(got["landing_rate"])
    return out


# Arabic-Indic (U+0660-0669) and Persian / Urdu (U+06F0-06F9) digits as ASCII, and the
# Arabic thousands (U+066C) and decimal (U+066B) separators as "," and ".".
_DIGITS = {**{0x0660 + i: str(i) for i in range(10)}, **{0x06F0 + i: str(i) for i in range(10)},
           0x066C: ",", 0x066B: ".", 0x060C: ","}


def ascii_digits(text):
    return str(text if text is not None else "").translate(_DIGITS)


def parse_budget(value):
    """The client's budget as a number: ASCII, Arabic-Indic or Persian digits, with or
    without thousands separators or spaces. 0 when there is no usable number."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        n = float(value)
    else:
        t = _re.sub(r"[\s,  '’]", "", ascii_digits(value))
        try:
            n = float(t) if t else 0.0
        except ValueError:
            return 0.0
    return max(0.0, min(n, 1e9)) if n == n else 0.0


# ------------------------------------------------------------ one post --

def _mid(pair):
    return (float(pair[0]) + float(pair[1])) / 2.0


def _margin(n):
    """Per-post margin from the number of posts the numbers rest on; MARGIN_BASE when estimated from followers only."""
    if not n or n <= 0:
        return MARGIN_BASE
    return MARGIN_BASE * math.sqrt(MARGIN_N / float(n))


def efficiency(score):
    """0.8 + 0.4 x score/100; 1.0 (the peer-median score of 50) when there is no score."""
    return 1.0 if score is None else 0.8 + 0.4 * max(0.0, min(100.0, float(score))) / 100.0


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v else None


def post_values(platform, followers, doc, score, lib, extra=1.0):
    """One post's expected views, interactions, reach, clicks and their margins.

    ``doc`` is the creator's analysis of this platform (or None), ``score`` their fit score on it,
    ``lib`` the global guide. Returns a dict; ``measured`` is True when the views are the creator's own."""
    doc = doc or {}
    L = lib[platform]
    size = tier_of(followers)
    feed = platform in benchmarks.FEED
    f = float(followers or 0)

    # -- views
    v, n_v, basis, measured = None, 0, "guide", False
    mv = _num(doc.get("median_views"))
    if mv:
        v, n_v, basis, measured = mv, int(doc.get("sample_posts") or 0), "median", True
    if v is None:
        med, pn, _m = benchmarks.peer_median_pair(platform, size, "view_rate_med", "view_rate")
        if med:
            v, n_v, basis = f * med / 100.0, 0, "peers"
    if v is None:
        av = _num(doc.get("avg_reel_plays")) if feed else _num(doc.get("avg_views"))
        if av:
            v, n_v, basis, measured = av, int(doc.get("sample_posts") or 0), "average", True
    if v is None:
        v, n_v, basis = f * _mid(L["view_rate"][size]) / 100.0, 0, "guide"
    m_v = _margin(n_v)

    # -- interactions
    own_rate, n_e = None, 0                      # per view, %
    inter, e_basis = None, "guide"
    if feed:
        likes, coms, plays = _num(doc.get("avg_reel_likes")), _num(doc.get("avg_reel_comments")), _num(doc.get("avg_reel_plays"))
        if plays and likes is not None and plays > 0:
            own_rate, n_e = (likes + (coms or 0)) / plays * 100.0, int(doc.get("reel_posts") or doc.get("sample_posts") or 0)
        elif _num(doc.get("er")) is not None and f and not doc.get("likes_hidden"):
            inter, n_e, e_basis = f * _num(doc["er"]) / 100.0 / max(v, 1.0) * v, int(doc.get("sample_posts") or 0), "own"
            own_rate = _num(doc["er"]) / 100.0 * f / max(v, 1.0) * 100.0
    else:
        r = _num(doc.get("median_er_on_views"))
        if r is None and doc.get("er_basis") == "views":
            r = _num(doc.get("er"))
        if r is not None:
            own_rate, n_e = r, int(doc.get("sample_posts") or 0)
    if own_rate is not None:
        e_basis, rate = "own", own_rate
    else:
        med, _n, _m = benchmarks.peer_median_pair(platform, size, "er_med", "er")
        if med:
            rate = (med / 100.0 * f / max(v, 1.0) * 100.0) if feed else med
            e_basis = "peers"
        else:
            rate = _mid(L["eng_rate"][size])
    m_e = _margin(n_e if e_basis == "own" else 0)
    eff = efficiency(score)
    views = v * eff * extra
    inter_v = v * rate / 100.0 * eff * extra
    ctr = _mid(L["ctr"]) / 100.0
    clicks = v * ctr * eff * extra
    return {"platform": platform, "size": size, "followers": f, "views": views, "interactions": inter_v,
            "reach": views * L["reach_per_view"], "clicks": clicks,
            "m_views": m_v, "m_inter": math.sqrt(m_v ** 2 + m_e ** 2), "m_clicks": math.sqrt(m_v ** 2 + MARGIN_BASE ** 2),
            "measured": measured, "basis": basis, "eff": eff}


def _sig2(v, up):
    """v rounded down (up=False) or up to two significant figures: 4,312 -> 4,300 / 4,400."""
    if not v or v <= 0:
        return 0
    e = math.floor(math.log10(v)) - 1
    q = 10 ** e
    n = (math.ceil(v / q - 1e-9) if up else math.floor(v / q + 1e-9)) * q
    return int(n) if e >= 0 else round(n, -e)


def _sig2n(v):
    """v to the nearest two significant figures (208,123 -> 210,000)."""
    if not v or v <= 0:
        return 0
    e = math.floor(math.log10(v)) - 1
    q = 10 ** e
    n = round(v / q) * q
    return int(n) if e >= 0 else round(n, -e)


def combine(posts, key, mkey):
    """(sum, low, high): the posts' total and its range, errors treated as independent, floor +/-10 %."""
    tot = sum(p[key] for p in posts)
    if not tot:
        return 0.0, 0, 0
    half = math.sqrt(sum((p[mkey] * p[key]) ** 2 for p in posts))
    half = max(half, RANGE_FLOOR * tot)
    return tot, _sig2(max(tot - half, 0), False), _sig2(tot + half, True)


def _posts_from_creators(creators, platforms, second_posts=None):
    posts, skipped = [], []
    second = set(second_posts or [])
    for c in creators:
        on = [p for p in platforms if (c.get("followers") or {}).get(p)]
        if not on:
            skipped.append(c.get("name") or c.get("code"))
            continue
        for p in on:
            doc = (c.get("docs") or {}).get(p)
            if doc is None and c.get("own") and c["own"].get("platform") == p:      # the older creator shape
                o = c["own"]
                doc = {"avg_views": o.get("views"), "avg_reel_plays": o.get("views") if p == "Instagram" else None}
            posts.append({"platform": p, "followers": int(c["followers"][p]), "doc": doc, "code": c.get("code"),
                          "score": (c.get("scores") or {}).get(p), "name": c.get("name")})
            if c.get("code") in second:
                posts.append(dict(posts[-1], second=True))
    return posts, skipped


def _posts_from_mix(mix, platforms):
    """Mix input: {size: n} (every chosen platform) or {platform: {size: n}}. Peer-median score 50 (factor 1.0)."""
    posts = []
    per_plat = isinstance(mix, dict) and any(isinstance(v, dict) for v in mix.values())
    for p in platforms:
        m = (mix or {}).get(p) if per_plat else mix
        for t in plans.TIERS:
            n = max(0, min(int((m or {}).get(t) or 0), 200))
            for _ in range(n):
                posts.append({"platform": p, "followers": plans.TIER_FOLLOWERS[t], "doc": None, "code": None, "score": None, "name": None})
    return posts


def _goal_list(goal, goals):
    gl = [g for g in (goals or []) if g in GOALS]
    if not gl:
        gl = [goal] if goal in GOALS else ["awareness"]
    return list(dict.fromkeys(gl))


FIG = {"views": ("Views", "views", "m_views", ""), "reach": ("Reach", "reach", "m_views", ""),
       "interactions": ("Interactions", "interactions", "m_inter", ""), "clicks": ("Clicks", "clicks", "m_clicks", "")}
ORDER = {"awareness": ["views", "reach"], "engagement": ["interactions", "views"], "traffic": ["clicks", "views"]}


def estimate(goal, budget, platforms, market="SA", creators=None, mix=None, goals=None, second_posts=None):
    gl = _goal_list(goal, goals)
    goal = gl[0]
    platforms = [p for p in PLATFORMS if p in (platforms or [])] or ["Instagram"]
    market = market if market in MARKETS else "SA"
    budget = parse_budget(budget)
    lib = plans.library()
    if creators is not None:
        raw, skipped = _posts_from_creators(creators, platforms, second_posts)
        n_creators = len(creators) - len(skipped)
    else:
        raw, skipped = _posts_from_mix(mix, platforms), []
        n_creators = len(raw)
    posts = [dict(p, **post_values(p["platform"], p["followers"], p.get("doc"), p.get("score"), lib,
                                   extra=1.0)) for p in raw]
    # a second post by the same creator repeats the audience a little less than a new creator would
    for p in posts:
        if p.get("second"):
            for k in ("views", "interactions", "reach", "clicks"):
                p[k] *= 0.8
    A = assumptions()
    out_fig, totals = {}, {}
    for key, (label, vk, mk, unit) in FIG.items():
        tot, lo, hi = combine(posts, vk, mk)
        out_fig[key] = {"key": key, "label": label, "value": _sig2n(tot),
                        "range": [lo, hi], "unit": unit}
        totals[key if key != "interactions" else "engagement"] = int(round(tot))
    views_t, inter_t, clicks_t = totals["views"], totals["engagement"], totals["clicks"]
    er = inter_t / views_t * 100 if views_t else None
    ctr = clicks_t / views_t * 100 if views_t else None
    if er is not None:
        totals["er"] = round(er, 2 if er < 1 else 1)
    if ctr is not None:
        totals["ctr"] = round(ctr, 2 if ctr < 1 else 1)
    totals["landing"] = int(round(clicks_t * A["landing_rate"]))
    totals["impressions"] = int(round(sum(p["views"] * A["impressions_per_view"][p["platform"]] for p in posts)))
    order = list(dict.fromkeys(k for g in gl for k in ORDER[g]))
    figures = [out_fig[k] for k in order if out_fig[k]["value"] or posts]
    if "interactions" in order and er is not None:
        figures.append({"key": "er", "label": "Engagement rate", "value": totals["er"], "unit": "%",
                        "range": [round(er * 0.8, 2 if er < 1 else 1), round(er * 1.2, 2 if er < 1 else 1)]})
    measured_c = len({p.get("code") for p in posts if p.get("measured") and p.get("code")}) if creators is not None else 0
    if creators is not None:
        trust = "Based on measured data for %d of %d creator%s." % (measured_c, n_creators, "" if n_creators == 1 else "s")
    else:
        trust = "Based on what similar creators of each size deliver; no individual creator measured."
    plat_line = " and ".join(platforms)
    return {
        "goal": goal, "goals": gl, "goal_label": " + ".join(GOAL_LABEL[g] for g in gl),
        "budget": int(round(budget)) if budget else None,
        "platforms": platforms, "market": market, "market_label": MARKETS[market],
        "creators": n_creators, "posts": len(posts), "skipped": skipped, "measured_posts": sum(1 for p in posts if p.get("measured")),
        "measured_creators": measured_c,
        "figures": figures, "totals": totals,
        "trust": {"line": trust, "measured": measured_c, "of": n_creators if creators is not None else 0},
        "note": ESTIMATE_LINE,
        "summary": "%s · %s · %s" % (" + ".join(GOAL_LABEL[g] for g in gl), plat_line,
                                     ("%d creator%s" % (n_creators, "" if n_creators == 1 else "s")) if n_creators else "no creators yet"),
        "estimate": True, "version": 3,
        "_posts": posts,
    }


def public(res):
    """The result without the working (never sent to a client)."""
    return {k: v for k, v in res.items() if not k.startswith("_")}


# -------------------------------------------------------------- planner --

def _unit_value(platform, size, lib, goal):
    """What one post of this size on this platform delivers for a goal (peer-median based)."""
    pv = post_values(platform, plans.TIER_FOLLOWERS[size], None, None, lib)
    return {"awareness": pv["views"], "engagement": pv["interactions"], "traffic": pv["clicks"]}[goal]


def plan_mix(goals, budget, platforms, supply=None, lib=None):
    """The mix of creator sizes (one post each) that maximises the goal inside the creators' share
    of the budget: {platform: {size: n}}. Greedy by expected result per planning price with
    diminishing returns, limited by how many creators of that size the roster has (``supply``:
    {(platform, size): n}) when known. Prices are internal and never returned."""
    lib = lib or plans.library()
    share, prices = settings()
    pool = parse_budget(budget) * share
    gl = _goal_list(None, goals)
    cells = [(p, t) for p in platforms for t in plans.TIERS]
    ref = {g: max(_unit_value(p, t, lib, g) for p, t in cells) or 1.0 for g in gl}

    def value(p, t):
        return sum(_unit_value(p, t, lib, g) / ref[g] for g in gl) / len(gl)
    mix = {p: {} for p in platforms}
    left = pool
    taken = {c: 0 for c in cells}
    for _ in range(400):
        best, best_r = None, 0.0
        for (p, t) in cells:
            if prices[t] > left + 1e-9:
                continue
            if supply is not None and taken[(p, t)] >= supply.get((p, t), 0):
                continue
            r = value(p, t) * (OVERLAP ** taken[(p, t)]) / prices[t]
            if r > best_r:
                best, best_r = (p, t), r
        if best is None:
            break
        p, t = best
        mix[p][t] = mix[p].get(t, 0) + 1
        taken[best] += 1
        left -= prices[t]
    return {p: m for p, m in mix.items() if m}


def plan(goals, budget, platforms, market="SA", supply=None):
    """The suggested mix and what it reaches, as ranges. No prices, no budget split in the result."""
    platforms = [p for p in PLATFORMS if p in (platforms or [])] or ["Instagram"]
    gl = _goal_list(None, goals)
    mix = plan_mix(gl, budget, platforms, supply)
    flat = {p: m for p, m in mix.items()}
    res = estimate(gl[0], 0, platforms, market, mix=flat, goals=gl)
    res["budget"] = int(round(parse_budget(budget))) or None
    res["mix"] = flat
    res["planned_creators"] = sum(sum(m.values()) for m in flat.values())
    return res


def _primary(res, gl):
    """The primary figures of a result for a goal list: {goal: value}."""
    t = res["totals"]
    return {"awareness": t.get("views", 0), "engagement": t.get("engagement", 0), "traffic": t.get("clicks", 0)}


def coverage(res, planned, gl):
    """How much of the plan a result reaches: the mean of result/plan over the goals (1.0 = the plan)."""
    a, b = _primary(res, gl), _primary(planned, gl)
    rs = [a[g] / float(b[g]) for g in gl if b.get(g)]
    return sum(rs) / len(rs) if rs else None


def _contribution(post, gl):
    w = {"awareness": post["views"], "engagement": post["interactions"], "traffic": post["clicks"]}
    return sum(w[g] for g in gl) / len(gl)


def advise(res, planned, gl, candidates=None, platforms=None, creators=None, max_items=3):
    """Ways to improve, ranked by how much each adds, at most ``max_items``. Each is
    {"id", "text", "gain", "action": {...}} with a machine-readable action:
      {"type": "remove", "codes": [...]}            take these out (or keep as reserve)
      {"type": "add", "codes": [...]}               add these creators
      {"type": "second_post", "codes": [...]}       a second post for these creators
      {"type": "add_platform", "platform": "TikTok"}
      {"type": "use_mix", "mix": {...}}             (a mix input) switch to the suggested mix
    Ranking is by performance (score, views per follower), never by price."""
    items = []
    gl = gl or ["awareness"]
    if not planned or not planned.get("planned_creators"):
        return items
    posts = [p for p in res.get("_posts") or [] if not p.get("second")]
    n_sel = len({p.get("code") for p in posts if p.get("code")}) if creators is not None else res.get("creators", 0)
    n_plan = planned["planned_creators"]
    cov = coverage(res, planned, gl)
    if creators is None:
        # a mix of sizes: offer the suggested mix when the result falls short of it
        if cov is not None and cov < 0.85:
            items.append({"id": "use_mix", "gain": 1 - cov, "text": "Your mix reaches about %d%% of what the plan reaches. The suggested mix is %s." % (
                int(round(cov * 100)), mix_text(planned["mix"])), "action": {"type": "use_mix", "mix": planned["mix"]}})
        return items[:max_items]
    # over the plan: too many creators for the same result
    if n_sel > n_plan * 1.15 and cov is not None and cov >= 0.9:
        k = max(1, n_sel - n_plan)
        by = {}
        for p in posts:
            by[p["code"]] = by.get(p["code"], 0) + _contribution(p, gl)
        weakest = [c for c, _ in sorted(by.items(), key=lambda kv: kv[1])[:k]]
        items.append({"id": "reserve", "gain": 0.0, "text": "You have %d creators; the plan needs about %d. These %d add the least: keep them as reserve or remove them." % (
            n_sel, n_plan, len(weakest)), "action": {"type": "remove", "codes": weakest}})
    if cov is not None and cov < 0.9:
        pct = int(round(cov * 100))
        # a) more creators of the sizes the plan uses and the selection lacks
        have = {}
        for p in posts:
            have[(p["platform"], p["size"])] = have.get((p["platform"], p["size"]), 0) + 1
        want = {}
        for p, m in planned["mix"].items():
            for t, n in m.items():
                want[(p, t)] = n
        lacking = sorted(((n - have.get(k, 0), k) for k, n in want.items() if n > have.get(k, 0)), reverse=True)
        if candidates:
            sized = None
            for gap, (p, t) in lacking:
                pool = [c for c in candidates if c["platform"] == p and c["size"] == t][:gap]
                if pool:
                    sized = (gap, p, t, pool)
                    break
            if sized:
                gap, p, t, pool = sized
                items.append({"id": "add", "gain": min(0.5, gap / float(max(n_plan, 1))),
                              "text": "You are at %d%% of the plan: add %d %s creator%s on %s." % (pct, len(pool), SIZE_WORD[t], "" if len(pool) == 1 else "s", p),
                              "action": {"type": "add", "codes": [c["code"] for c in pool]}})
        # b) a second post for the best performers
        ranked = sorted(posts, key=lambda p: -(_contribution(p, gl) * (p.get("score") or 50) / 50.0))
        top = []
        for p in ranked:
            if p.get("code") and p["code"] not in top:
                top.append(p["code"])
            if len(top) >= 2:
                break
        if top:
            gain = sum(_contribution(p, gl) * 0.8 for p in posts if p.get("code") in top)
            tot = sum(_contribution(p, gl) for p in posts) or 1.0
            items.append({"id": "second", "gain": gain / tot, "text": "A second post from your top %d creator%s adds about %d%% to the total." % (
                len(top), "" if len(top) == 1 else "s", int(round(gain / tot * 100))), "action": {"type": "second_post", "codes": top}})
        # c) another platform the plan uses
        for p in (planned.get("platforms") or []):
            if p not in (res.get("platforms") or []) and p in PLATFORMS:
                items.append({"id": "platform", "gain": 0.25, "text": "Add %s: your creators there would reach more people." % p,
                              "action": {"type": "add_platform", "platform": p}})
                break
    items.sort(key=lambda i: -i["gain"])
    return items[:max_items]


def mix_text(mix):
    bits = []
    for p, m in mix.items():
        parts = ["%d %s" % (m[t], SIZE_WORD[t]) for t in TIER_ORDER if m.get(t)]
        if parts:
            bits.append("%s on %s" % (", ".join(parts), p))
    return "; ".join(bits)


def candidates_from_db(exclude, platforms, goals, objective=None, target=None, limit=40):
    """Roster creators to add, best performers first (score, then views per follower), on the
    chosen platforms, not already in the selection. Each {"code", "platform", "size", "followers", "score"}."""
    import analysis
    import matcher
    rows = [c for c in db.list_creators(active_only=True) if c["code"] not in set(exclude)]
    out = []
    for p in platforms:
        pool = [c for c in rows if p in analysis.creator_platforms(c)]
        pool.sort(key=lambda c: c["code"])
        pool = pool[:600]
        if not pool:
            continue
        sc = matcher.score_codes([c["code"] for c in pool], objective or "Balanced", target or {}, p)
        for c in pool:
            s = sc.get(c["code"]) or {}
            if s.get("score") is None or s.get("platform") not in (None, p) or s.get("confidence", {}).get("level") == "low":
                continue
            f = int(c["followers"] or 0)
            out.append({"code": c["code"], "platform": p, "size": tier_of(f), "followers": f, "score": s["score"]})
    out.sort(key=lambda c: (-c["score"], c["code"]))
    return out[:limit * 5]


# --------------------------------------------------------- selection input --

def objective_for_selection(sel, goals=None):
    import fit
    keys = sel.keys()
    got = (sel["objective"] if "objective" in keys else None) or fit.FROM_CAMPAIGN.get(db.selection_campaign_objective(sel["id"]) or "", None)
    if got and fit.known_objective(got):
        return fit.canonical(got)
    if goals:
        return fit.objective_of([GOAL_LABEL.get(g, g) for g in goals if g in GOALS])
    return "Balanced"


def creators_of(sel, which="approved", statuses=None, goals=None):
    """A selection's creators with followers per platform, their analyses, and their fit score per
    platform for the selection's objective. ``which``: approved (falls back to everyone not
    rejected when none is approved yet) or all."""
    import selstatus
    codes = json.loads(sel["codes"] or "[]")
    st = statuses if statuses is not None else selstatus.of(sel["id"])
    if which == "approved":
        ok = [c for c in codes if (st.get(c) or {}).get("s") == "approved"]
        if not ok:
            ok = [c for c in codes if (st.get(c) or {}).get("s", "review") not in ("rejected", "unavailable")]
        codes = ok
    else:
        codes = [c for c in codes if (st.get(c) or {}).get("s") not in ("rejected", "unavailable")]
    want = set(codes)
    rows = {c["code"]: c for c in db.list_creators() if c["code"] in want}
    every = db.analyses_for(list(want)) if want else {}
    objective = objective_for_selection(sel, goals)
    try:
        target = json.loads((sel["target"] if "target" in sel.keys() else None) or "{}")
    except ValueError:
        target = {}
    scores = {}
    try:
        import matcher
        for p in PLATFORMS:
            got = matcher.score_codes(list(want), objective, target, p) if want else {}
            for code, s in got.items():
                if s.get("score") is not None and s.get("platform") in (None, p) and p in (every.get(code) or {}):
                    scores.setdefault(code, {})[p] = s["score"]
    except Exception:
        scores = {}
    out = []
    for code in codes:
        c = rows.get(code)
        if c is None:
            continue
        foll, docs = {}, {}
        for a in db.split_profiles(c["profiles"] or ""):
            if a.get("followers") and a.get("platform") in PLATFORMS:
                foll[a["platform"]] = int(a["followers"])
        if c["followers"] and c["platform"] in PLATFORMS and c["platform"] not in foll:
            foll[c["platform"]] = int(c["followers"])
        for plat, got in (every.get(code) or {}).items():
            d = (got or {}).get("data") or {}
            if plat in PLATFORMS:
                docs[plat] = d
                if d.get("followers") and plat not in foll:
                    foll[plat] = int(d["followers"])
        out.append({"code": code, "name": c["name"], "followers": foll, "docs": docs, "scores": scores.get(code) or {}})
    return out


def supply_from_db():
    """{(platform, size): creators} on the roster, so the planner never asks for more than exists."""
    out = {}
    try:
        import analysis
        for c in db.list_creators(active_only=True):
            f = int(c["followers"] or 0)
            for p in analysis.creator_platforms(c):
                if p in PLATFORMS:
                    out[(p, tier_of(f))] = out.get((p, tier_of(f)), 0) + 1
    except Exception:
        return None
    return out or None


def full(goal, budget, platforms, market, creators=None, mix=None, goals=None, second_posts=None, sel=None, with_advice=True):
    """The estimate with the plan and the ways to improve, as the API returns it (no working)."""
    res = estimate(goal, budget, platforms, market, creators=creators, mix=mix, goals=goals, second_posts=second_posts)
    gl = res["goals"]
    ways, planned = [], None
    if with_advice and parse_budget(budget) > 0:
        planned = plan(gl, budget, res["platforms"], res["market"], supply=supply_from_db())
        cands = None
        if creators is not None:
            try:
                inside = json.loads(sel["codes"] or "[]") if sel is not None else []
                cands = candidates_from_db([c["code"] for c in creators] + inside, res["platforms"], gl,
                                           objective_for_selection(sel, gl) if sel is not None else None)
            except Exception:
                cands = None
        ways = advise(res, planned, gl, candidates=cands, creators=creators)
    out = public(res)
    out["ways"] = ways
    if planned is not None:
        out["plan"] = {"mix": planned["mix"], "creators": planned["planned_creators"], "figures": planned["figures"], "text": mix_text(planned["mix"])}
    return out


# ------------------------------------------------------------------ saving --

def save(code_id, sel_id, goal, inp, result, by=""):
    result = public(result) if isinstance(result, dict) else result
    with db.connect() as conn:
        cur = conn.execute("INSERT INTO roi_estimates (code_id, selection_id, goal, input, result, created_at, created_by) "
                           "VALUES (?,?,?,?,?,?,?)", (code_id, sel_id, goal, json.dumps(inp)[:4000], json.dumps(result)[:20000],
                                                      db.now(), by[:120]))
        return cur.lastrowid


def latest_for(sel_id, before=None):
    with db.connect() as conn:
        if before:
            r = conn.execute("SELECT * FROM roi_estimates WHERE selection_id = ? AND created_at <= ? ORDER BY created_at DESC, id DESC LIMIT 1",
                             (sel_id, before)).fetchone()
            if r:
                return r
        return conn.execute("SELECT * FROM roi_estimates WHERE selection_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                            (sel_id,)).fetchone()


# What older estimates carried and the calculator no longer shows (cost per result, the market
# verdict, frequency, advice, sources): stripped when an old one is read back.
_REMOVED_RESULT = ("advice", "sources", "cost", "verdict", "split", "_posts")
_REMOVED_FIGURES = {"cpm", "cpe", "cpc", "frequency", "impressions", "ctr", "landing"}


def clean_result(res):
    res = dict(res or {})
    for k in _REMOVED_RESULT:
        res.pop(k, None)
    res["figures"] = [{k: v for k, v in f.items() if k != "sig"} for f in (res.get("figures") or []) if f.get("key") not in _REMOVED_FIGURES]
    t = res.get("totals") or {}
    res["totals"] = {k: v for k, v in t.items() if k in ("views", "reach", "engagement", "er", "clicks", "ctr")}
    return res


def row_view(r):
    if r is None:
        return None
    return {"id": r["id"], "goal": r["goal"], "at": r["created_at"], "input": json.loads(r["input"] or "{}"),
            "result": clean_result(json.loads(r["result"] or "{}"))}


# ------------------------------------------------------ estimate vs actual --

def versus(k):
    """A campaign's saved estimate (kept with its selection, the last one saved before it started)
    against what the report measured: views, interactions and clicks, each against the saved
    RANGE. None when either side is missing."""
    if not k or not k["selection_id"] or k["status"] == "draft":
        return None
    saved = latest_for(k["selection_id"], before=k["starts_at"])
    if saved is None:
        return None
    res = clean_result(json.loads(saved["result"] or "{}"))
    est = res.get("totals") or {}
    ranges = {f["key"]: f.get("range") for f in res.get("figures") or []}
    ranges["engagement"] = ranges.get("interactions") or ranges.get("engagement")
    act = plans._measured(k)
    if not act or not act.get("posts"):
        return None
    rows = []
    for key, label in (("views", "Views"), ("engagement", "Interactions"), ("clicks", "Tracking-link clicks")):
        e, a = est.get(key), act.get(key)
        if e is None or a is None or not e:
            continue
        if key == "clicks" and not a:
            continue                     # no tracking links on this campaign: nothing to compare
        rng = ranges.get(key) or [int(e * 0.8), int(e * 1.2)]
        pos = "above" if a > rng[1] else "below" if a < rng[0] else "within"
        ratio = a / float(e)
        rows.append({"key": key, "label": label, "estimate": e, "range": rng, "actual": a,
                     "delta": "%+d%%" % int(round((ratio - 1) * 100)), "position": pos,
                     "sig": {"grade": "low" if pos == "below" else "good", "label": {"above": "Above the range", "within": "Within the range", "below": "Below the range"}[pos]}})
    if not rows:
        return None
    above = [r["label"] for r in rows if r["position"] == "above"]
    below = [r["label"] for r in rows if r["position"] == "below"]
    line = ((above[0] + " came in above the estimated range. ") if above else "") + \
           (("%s fell below the estimated range: worth a look before the next campaign." % below[0]) if below else
            ("Everything landed inside or above the estimated range." if not above else ""))
    return {"campaign": k["name"], "token": k["token"], "saved_at": saved["created_at"], "goal": saved["goal"],
            "ended": k["status"] == "ended", "ends_at": k["ends_at"], "rows": rows, "helvy": line.strip()}


# --------------------------------------------------------------- in the chat --

_AMOUNT = _re.compile(r"(?:sar|sr|riyals?|ريال)\s*(\d[\d,\.]*)\s*(k|m|thousand|million|ألف)?|(\d[\d,\.]*)\s*(k|m|thousand|million|ألف)?\s*(?:sar|sr|riyals?|ريال)", _re.I)
_ASK = _re.compile(r"\b(reach|budget|what can|how (many|much) (views|reach|people|clicks)|get me|buy|roi)\b|ميزانية|ميزانيتي", _re.I)


def from_text(text):
    """A typed "what can SAR 60,000 do on TikTok if we want clicks?" answered at once with a
    calculator card: free, no AI call. None when the message is not that question."""
    t = " ".join(ascii_digits(text).split())
    m = _AMOUNT.search(t)
    if not m or not _ASK.search(t):
        return None
    num, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    try:
        v = float(num.replace(",", "").rstrip("."))
    except ValueError:
        return None
    unit = (unit or "").lower()
    v *= 1000 if unit in ("k", "thousand", "ألف") else 1e6 if unit in ("m", "million") else 1
    if v < 1000:
        return None
    low = t.lower()
    goal = "traffic" if _re.search(r"click|traffic|visit|site|link|landing|زيارات", low) else \
        "engagement" if _re.search(r"engag|interact|comment|تفاعل", low) else "awareness"
    plats = [p for p, w in (("Instagram", r"insta|\big\b|reels"), ("TikTok", r"tik ?tok"), ("Snapchat", r"snap"), ("YouTube", r"youtube"))
             if _re.search(w, low)] or ["Instagram", "TikTok"]
    res = public(plan([goal], v, plats, "SA", supply=supply_from_db()))
    res["budget"] = int(round(v))
    return res
