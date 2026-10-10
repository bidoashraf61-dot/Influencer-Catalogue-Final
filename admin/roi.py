"""ROI Calculator for clients (HELVY Connect), version 4 (fix batch 7, Bido 2026-10-10).

A calculator of campaign STRUCTURE against PERFORMANCE. No budget, no prices, no CPM or cost
per result, no market factor: money lives in the quotation. The client sees what a selection
(or a mix of creator sizes) is expected to deliver, what HelloVoice's recommended structure
would deliver with the SAME number of creators and posts, how the two compare, and up to
three ranked ways to close the gap.

Per post (one post per creator per chosen platform):

  views         the creator's MEDIAN views, else followers x the same-size peer-median view
                rate (benchmarks.py, own roster, needs 30 peers), else the creator's measured
                AVERAGE (Instagram reel plays, TikTok average), else followers x the guide
                (Instagram: IG_VIEW_RATE calibrated on 39 real reels; others Settings ->
                Benchmark library).
  expected      a median describes the TYPICAL post, a campaign's total is the SUM of posts and
                views are skewed, so a median-based figure (own median, peer median, guide) is
                multiplied by MEAN_OVER_MEDIAN. A measured average is already an expected value.
  interactions  views x the creator's own engagement rate, else same-size peers, else the guide
  reach         views x reach-per-view      clicks   views x CTR     (guide values, estimates)
  efficiency    0.8 + 0.4 x score/100 for a selection's creators (fit.score for the selection's
                objective); the recommended structure's creators are typical (1.0)

The recommended structure (the "ideal"): per goal an editable SHAPE (percent of creators by
size, setting ``roi_shapes``, defaults ``SHAPES_DEFAULT``); several goals average their shapes;
counts by largest remainder so they sum to the number of creators; spread evenly over the
chosen platforms. Selection quality = selection result / ideal result per goal (Awareness
views, Engagement interactions, Traffic clicks), averaged; it can exceed 100 %.

Honest ranges: per post margin 0.48 x sqrt(20 / n) from the n posts its numbers rest on (0.48
when estimated), combined as independent errors, never narrower than +/-10 %, two significant
figures.

    estimate(goal, platforms, creators=None, mix=None, goals=None, second_posts=None, count=None)
    full(...)                  the comparison with the ways to improve, as the API returns it
    ideal_counts(goals, n, platforms)      the recommended structure's creators by size
    creators_of(selection, which)          a selection's creators as the calculator needs them
    save(...) / latest_for(sel_id)         an estimate kept with a selection
    versus(campaign)                       saved ranges against the live report
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
TIER_ORDER = ["mega", "macro", "mid", "micro", "nano"]
TIER_NAME = {"mega": ("Mega", "1M+ followers"), "macro": ("Macro", "500K–1M"), "mid": ("Mid", "100K–500K"),
             "micro": ("Micro", "20K–100K"), "nano": ("Nano", "Under 20K")}
SIZE_WORD = {"mega": "mega", "macro": "macro", "mid": "mid-size", "micro": "micro", "nano": "nano"}
PRIMARY = {"awareness": "views", "engagement": "interactions", "traffic": "clicks"}

# The recommended structure: percent of creators by size, per campaign type, one post per creator, one
# shape per goal for every product category (no pharma cap). A research-based STARTING POINT (HelloVoice,
# 2026-10-10, from CAMPAIGN-STRUCTURE-BEST-PRACTICE-2026-10-10.md), low confidence on the exact
# percentages and not an industry benchmark; within +/- ON_STRUCTURE_POINTS counts as on structure.
# Replace here and only here (or per installation in Settings -> Client portal -> "Recommended
# structure", setting ``roi_shapes``). Each goal sums to 100.
SHAPES_DEFAULT = {
    "awareness": {"macro": 10, "mid": 25, "micro": 45, "nano": 20},
    "engagement": {"macro": 3, "mid": 20, "micro": 45, "nano": 32},
    "traffic": {"mid": 25, "micro": 55, "nano": 20},
}
# How many creators a campaign of each type usually runs (low, high): a hint beside the "How many
# creators?" control, never a limit or a verdict. Research-based starting point, low confidence
# (CAMPAIGN-STRUCTURE-BEST-PRACTICE-2026-10-10.md, mid-size budgets). Setting ``roi_count_ranges``.
COUNT_RANGES_DEFAULT = {"awareness": (12, 25), "engagement": (15, 30), "traffic": (8, 20)}
COUNT_MIN, COUNT_MAX = 1, 60      # any whole number in this span is accepted
ON_STRUCTURE_POINTS = 10          # a tier within +/- 10 points of its recommended share counts as on structure

# HelloVoice planning assumptions (not in the industry guide). Editable as the "roi_assumptions" setting.
ASSUMPTIONS = {"impressions_per_view": {"Instagram": 1.5, "TikTok": 1.2, "Snapchat": 1.0, "YouTube": 1.1},
               "landing_rate": 0.8}
MARGIN_BASE = 0.48                # margin of a post whose numbers rest on 20 posts, or on followers only
MARGIN_N = 20
RANGE_FLOOR = 0.10                # a range is never narrower than +/-10 %
ESTIMATE_LINE = "Estimate, not a result. Real results depend on the content, the timing and the audience."
STRUCTURE_NAME = "HelloVoice’s recommended structure"
# Instagram reel view rate (views / followers, %) by size when a creator has no measured views and the
# peers are too few: calibrated on 39 real reels (the 18 Penduline reels + 21 roster creators with reel
# plays), 2026-10-10, instead of the international-style guide (micro 16, mid 13, macro 8.5, mega 5.5)
# which measured too high for micro and too low for mid and macro. Used by the ROI Calculator ONLY; the
# campaign planner (plans.LIBRARY) is untouched. Replaced by peers/medians once the Instagram sample exists.
IG_VIEW_RATE = {"nano": 12.0, "micro": 12.0, "mid": 20.0, "macro": 12.0, "mega": 3.0}
# A campaign's views are the SUM of its posts' views, and views are heavily skewed (a few viral posts):
# the average post is well above the typical (median) post. Across 1,098 TikTok creators with 20 posts the
# median swing of views (spread / average) is 1.54, i.e. average / median = exp(ln(1 + 1.54^2) / 2) = 1.83
# for log-normal views. Medians and peer medians describe a typical post, so totals multiply them by this
# factor; a creator's own measured AVERAGE (and a peer cell built from creators' averages) is already an
# expected value and is left alone. Derived from the roster, not tuned on any one campaign.
MEAN_OVER_MEDIAN = 1.8
SECOND_POST = 0.8                 # a second post by the same creator repeats the audience a little: 80 %
GOOD_ENOUGH = 0.01                # a way to improve must add at least one point of quality

SCHEMA = """
CREATE TABLE IF NOT EXISTS roi_estimates (
    id INTEGER PRIMARY KEY,
    code_id INTEGER,                 -- who saved it
    selection_id INTEGER,            -- the selection it is kept with
    goal TEXT NOT NULL,
    input TEXT NOT NULL,             -- JSON: goals, platforms, mix, source
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


# ------------------------------------------------------------- the shapes --

def validate_shape(raw):
    """(clean, error): one goal's shape {size: percent}. Percentages are numbers >= 0 over known
    sizes and must add up to 100 (within 0.5). ``clean`` keeps only the sizes above 0."""
    if not isinstance(raw, dict):
        return None, "Not a set of percentages."
    clean = {}
    for t, v in raw.items():
        if t not in TIER_ORDER:
            return None, "Unknown size %s." % t
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v < 0 or v > 100:
            return None, "%s must be a number from 0 to 100." % TIER_NAME[t][0]
        if v > 0:
            clean[t] = float(v)
    total = sum(clean.values())
    if abs(total - 100.0) > 0.5:
        return None, "The percentages add up to %g, not 100." % round(total, 1)
    return clean, None


def validate_shapes(raw):
    """(clean {goal: shape}, errors {goal: message}) for a submitted set of shapes."""
    clean, errors = {}, {}
    for g in GOALS:
        if g not in (raw or {}):
            continue
        c, err = validate_shape(raw[g])
        if err:
            errors[g] = err
        else:
            clean[g] = c
    return clean, errors


def shapes():
    """{goal: {size: percent}}: the setting ``roi_shapes`` where valid, else SHAPES_DEFAULT."""
    out = {g: {t: float(v) for t, v in SHAPES_DEFAULT[g].items()} for g in GOALS}
    try:
        got = db.setting("roi_shapes")
    except Exception:
        got = None
    if isinstance(got, dict):
        clean, _ = validate_shapes(got)
        out.update(clean)
    return out


def validate_count_ranges(raw):
    """(clean {goal: (low, high)}, errors {goal: message}) for submitted ranges: whole numbers
    from COUNT_MIN to COUNT_MAX with low <= high."""
    clean, errors = {}, {}
    for g in GOALS:
        if g not in (raw or {}):
            continue
        v = raw[g]
        try:
            lo, hi = v
            ok = all(isinstance(x, (int, float)) and not isinstance(x, bool) and x == int(x) for x in (lo, hi))
        except (TypeError, ValueError):
            ok = False
        if not ok:
            errors[g] = "Use whole numbers."
            continue
        lo, hi = int(lo), int(hi)
        if not (COUNT_MIN <= lo <= hi <= COUNT_MAX):
            errors[g] = "Use whole numbers from %d to %d, low not above high." % (COUNT_MIN, COUNT_MAX)
            continue
        clean[g] = (lo, hi)
    return clean, errors


def count_ranges():
    """{goal: (low, high)}: the setting ``roi_count_ranges`` where valid, else COUNT_RANGES_DEFAULT."""
    out = dict(COUNT_RANGES_DEFAULT)
    try:
        got = db.setting("roi_count_ranges")
    except Exception:
        got = None
    if isinstance(got, dict):
        clean, _ = validate_count_ranges(got)
        out.update(clean)
    return out


def count_range_for(goals):
    """(low, high) for one goal, or for several: the average of the lows and of the highs, rounded."""
    gl = _goal_list(None, goals)
    table = count_ranges()
    lo = int(round(sum(table[g][0] for g in gl) / float(len(gl))))
    hi = int(round(sum(table[g][1] for g in gl) / float(len(gl))))
    return lo, max(lo, hi)


def shape_for(goals, table=None):
    """The percent of creators by size for one goal, or the average of several goals' shapes."""
    table = table or shapes()
    gl = _goal_list(None, goals)
    acc = {}
    for g in gl:
        for t, v in table[g].items():
            acc[t] = acc.get(t, 0.0) + v / len(gl)
    return acc


def largest_remainder(weights, n):
    """{key: count} summing to n, in proportion to ``weights`` (largest remainder; ties go to the
    larger size so the result never depends on dict order)."""
    n = max(0, int(n))
    tot = float(sum(w for w in weights.values() if w > 0))
    if not n or not tot:
        return {}
    quota = {k: w / tot * n for k, w in weights.items() if w > 0}
    out = {k: int(math.floor(q + 1e-9)) for k, q in quota.items()}
    left = n - sum(out.values())
    order = sorted(quota, key=lambda k: (-(quota[k] - out[k]), TIER_ORDER.index(k) if k in TIER_ORDER else 99))
    for k in order[:left]:
        out[k] += 1
    return {k: v for k, v in out.items() if v}


def ideal_counts(goals, n, platforms=None, table=None, per_platform_posts=None):
    """The recommended structure for ``n`` creators posting once on each chosen platform:
    {platform: {size: count}}. ``per_platform_posts`` overrides the posts per platform (the
    total is still spread by largest remainder, evenly, when only a total is given as an int)."""
    platforms = [p for p in PLATFORMS if p in (platforms or [])] or ["Instagram"]
    shape = shape_for(goals, table)
    if isinstance(per_platform_posts, dict):
        per = {p: int(per_platform_posts.get(p, 0)) for p in platforms}
    elif isinstance(per_platform_posts, int):
        per = {p: c for p, c in zip(platforms, _even(per_platform_posts, len(platforms)))}
    else:
        per = {p: int(n) for p in platforms}
    return {p: largest_remainder(shape, per[p]) for p in platforms}


def _even(total, k):
    base, extra = divmod(max(0, int(total)), k)
    return [base + (1 if i < extra else 0) for i in range(k)]


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

    ``doc`` is the creator's analysis of this platform (or None), ``score`` their fit score on it
    (None: a typical creator, factor 1.0), ``lib`` the global guide. ``measured`` is True when the
    views are the creator's own."""
    doc = doc or {}
    L = lib[platform]
    size = tier_of(followers)
    feed = platform in benchmarks.FEED
    f = float(followers or 0)

    # -- views
    v, n_v, basis, measured = None, 0, "guide", False
    typical = True                      # a median-type figure: totals need the mean-over-median factor
    mv = _num(doc.get("median_views"))
    if mv:
        v, n_v, basis, measured = mv, int(doc.get("sample_posts") or 0), "median", True
    if v is None:
        med, pn, used = benchmarks.peer_median_pair(platform, size, "view_rate_med", "view_rate")
        if med:
            v, n_v, basis = f * med / 100.0, 0, "peers"
            typical = used == "view_rate_med"   # a cell of creators' AVERAGES is already an expected value
    if v is None:
        av = _num(doc.get("avg_reel_plays")) if feed else _num(doc.get("avg_views"))
        if av:
            v, n_v, basis, measured = av, int(doc.get("sample_posts") or 0), "average", True
            typical = False
    if v is None:
        rate_g = IG_VIEW_RATE[size] if platform == "Instagram" else _mid(L["view_rate"][size])
        v, n_v, basis = f * rate_g / 100.0, 0, "guide"
    m_v = _margin(n_v)
    v_exp = v * (MEAN_OVER_MEDIAN if typical else 1.0)       # expected (average) views, not the typical post

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
    views = v_exp * eff * extra
    inter_v = v_exp * rate / 100.0 * eff * extra
    ctr = _mid(L["ctr"]) / 100.0
    clicks = v_exp * ctr * eff * extra
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


def _half(posts, key, mkey):
    tot = sum(p[key] for p in posts)
    if not tot:
        return 0.0, 0.0
    half = math.sqrt(sum((p[mkey] * p[key]) ** 2 for p in posts))
    return tot, max(half, RANGE_FLOOR * tot)


def combine(posts, key, mkey):
    """(sum, low, high): the posts' total and its range, errors treated as independent, floor +/-10 %."""
    tot, half = _half(posts, key, mkey)
    if not tot:
        return 0.0, 0, 0
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
    """Mix input: {size: n} (every chosen platform) or {platform: {size: n}}. Typical creators (factor 1.0)."""
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
    gl = [("traffic" if g == "conversion" else g) for g in (goals or [])]
    gl = [g for g in gl if g in GOALS]
    if not gl:
        gl = [goal] if goal in GOALS else ["awareness"]
    return list(dict.fromkeys(gl))


FIG = {"views": ("Views", "views", "m_views"), "reach": ("Reach", "reach", "m_views"),
       "interactions": ("Interactions", "interactions", "m_inter"), "clicks": ("Clicks", "clicks", "m_clicks")}
ORDER = {"awareness": ["views", "reach"], "engagement": ["interactions", "views"], "traffic": ["clicks", "views"]}
# the figure each goal is judged on, and the post field that feeds it
_PRIMARY_FIELD = {"awareness": ("views", "m_views"), "engagement": ("interactions", "m_inter"), "traffic": ("clicks", "m_clicks")}


def _figures(posts, gl):
    """(figures list, totals dict) for a set of posts, as the calculator shows them."""
    A = assumptions()
    out_fig, totals = {}, {}
    for key, (label, vk, mk) in FIG.items():
        tot, lo, hi = combine(posts, vk, mk)
        out_fig[key] = {"key": key, "label": label, "value": _sig2n(tot), "range": [lo, hi], "unit": ""}
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
    return figures, totals, out_fig


def _by_size_creators(creators, platforms):
    out = {}
    for c in creators or []:
        fol = [int(c["followers"][p]) for p in platforms if (c.get("followers") or {}).get(p)]
        if fol:
            t = tier_of(max(fol))
            out[t] = out.get(t, 0) + 1
    return out


def _counts_text(by_size):
    n = float(sum(by_size.values())) or 1.0
    return [{"size": t, "label": TIER_NAME[t][0], "n": by_size.get(t, 0), "pct": int(round(by_size.get(t, 0) / n * 100))}
            for t in TIER_ORDER]


def _on_structure(sel_c, ideal_c):
    """{size: "on" | "short" | "over"}: the selection's share of creators against the recommended
    share, +/- ON_STRUCTURE_POINTS points counting as on structure."""
    ns, ni = float(sum(sel_c.values())) or 1.0, float(sum(ideal_c.values())) or 1.0
    out = {}
    for t in TIER_ORDER:
        d = sel_c.get(t, 0) / ns * 100 - ideal_c.get(t, 0) / ni * 100
        out[t] = "short" if d < -ON_STRUCTURE_POINTS else "over" if d > ON_STRUCTURE_POINTS else "on"
    return out


# --------------------------------------------------------- the comparison --

def _side(posts, gl, creators_n, by_size, platforms):
    figures, totals, raw = _figures(posts, gl)
    scores = [p["score"] for p in posts if p.get("score") is not None and not p.get("second")]
    by_plat = {p: sum(1 for x in posts if x["platform"] == p and not x.get("second")) for p in platforms}
    return {"creators": creators_n, "posts": len(posts), "by_size": _counts_text(by_size),
            "by_platform": [{"platform": p, "posts": n} for p, n in by_plat.items()],
            "figures": figures, "totals": totals,
            "ranges": {k: {"value": v["value"], "range": v["range"]} for k, v in raw.items() if k in ("views", "interactions", "clicks")},
            "score": round(sum(scores) / len(scores)) if scores else None,
            "_raw": raw}


def _ideal_posts(counts, lib):
    posts = []
    for p, m in counts.items():
        for t, n in m.items():
            for _ in range(n):
                v = post_values(p, plans.TIER_FOLLOWERS[t], None, None, lib)
                posts.append(dict(v, code=None, score=None))
    return posts


def _quality(sel, ideal, gl):
    """Selection quality: selection / ideal on each goal's primary figure, averaged. {} when either side is empty."""
    ratios, rels = {}, []
    for g in gl:
        vk, mk = _PRIMARY_FIELD[g]
        s_tot, s_half = _half(sel["_posts"], vk, mk)
        o_tot, o_half = _half(ideal["_posts"], vk, mk)
        if not s_tot or not o_tot:
            continue
        r = s_tot / o_tot
        ratios[g] = r
        rels.append(r * math.sqrt((s_half / s_tot) ** 2 + (o_half / o_tot) ** 2))
    if not ratios:
        return None
    q = sum(ratios.values()) / len(ratios)
    half = sum(rels) / len(rels)
    lo, hi = max(q - half, 0.0), q + half
    # the two ranges on the first goal's primary figure: how much they overlap
    vk, mk = _PRIMARY_FIELD[gl[0]]
    s_tot, s_half = _half(sel["_posts"], vk, mk)
    o_tot, o_half = _half(ideal["_posts"], vk, mk)
    overlap = 0.0
    if s_tot and o_tot:
        a_lo, a_hi, b_lo, b_hi = s_tot - s_half, s_tot + s_half, o_tot - o_half, o_tot + o_half
        overlap = max(0.0, min(a_hi, b_hi) - max(a_lo, b_lo)) / max(min(a_hi - a_lo, b_hi - b_lo), 1e-9)
    r5 = lambda x: int(5 * round(x * 100 / 5.0))          # noqa: E731
    band = overlap >= 0.5
    pct, plo, phi = r5(q), r5(lo), r5(hi)
    text = ("%d–%d%%" % (plo, phi)) if band and plo != phi else ("about %d%%" % pct)
    return {"pct": pct, "low": plo, "high": phi, "band": band and plo != phi, "overlap": round(overlap, 2), "text": text,
            "by_goal": {g: r5(r) for g, r in ratios.items()}, "_q": q}


def _list_sizes(c):
    bits = ["%d %s" % (c[t], t) for t in TIER_ORDER if c.get(t)]
    return ", ".join(bits) if bits else "none"


def _compare_line(ideal_c, sel_c, n_ideal, n_sel, goal_label):
    """What the recommended structure has at this number of creators and what the selection has."""
    line = "The ideal for %d creator%s has %s" % (n_ideal, "" if n_ideal == 1 else "s", _list_sizes(ideal_c))
    if n_sel:
        line += "; you have %s." % _list_sizes(sel_c)
    else:
        line += "."
    return line


def _word(n):
    return {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six"}.get(n, str(n))


def _gap_words(sel_c, ideal_c, unit, n):
    """Plain-words gap between the selection's and the recommended structure's creators by size.
    Only tiers more than ON_STRUCTURE_POINTS points off their recommended share are named."""
    status = _on_structure(sel_c, ideal_c)
    avg_unit = (sum(ideal_c.get(t, 0) * unit.get(t, 0) for t in TIER_ORDER) / float(n)) if n else 0.0
    out = []
    for t in TIER_ORDER:                                    # biggest sizes first
        want, have = ideal_c.get(t, 0), sel_c.get(t, 0)
        w = SIZE_WORD[t]
        if status[t] == "short":
            k = max(want - have, 1)
            out.append((k, t, "No %s creator" % w if have == 0 else "%s %s creator%s short" % (_word(k), w, "" if k == 1 else "s")))
        elif status[t] == "over":
            extra = max(have - want, 1)
            if unit.get(t, 0) < 0.6 * avg_unit:
                out.append((extra * 0.5, t, "%s %s creator%s add little" % (_word(extra), w, "" if extra == 1 else "s")))
            else:
                out.append((extra * 0.3, t, "%s more %s creator%s than recommended" % (_word(extra), w, "" if extra == 1 else "s")))
    out.sort(key=lambda x: -x[0])
    return [x[2] for x in out[:3]]


def _unit_by_size(platform, gl, lib):
    """What one typical post of each size delivers for the goals, relative to the best size (0..1)."""
    raw = {t: post_values(platform, plans.TIER_FOLLOWERS[t], None, None, lib) for t in TIER_ORDER}
    out = {t: 0.0 for t in TIER_ORDER}
    for g in gl:
        vk = _PRIMARY_FIELD[g][0]
        top = max(raw[t][vk] for t in TIER_ORDER) or 1.0
        for t in TIER_ORDER:
            out[t] += raw[t][vk] / top / len(gl)
    return out


def estimate(goal, platforms, creators=None, mix=None, goals=None, second_posts=None, count=None, table=None):
    """The expected results of a selection (``creators``) or a mix of sizes (``mix``), the
    recommended structure for the same number of creators and posts, and how they compare.
    ``count``: creators to plan for when there is nothing chosen yet."""
    gl = _goal_list(goal, goals)
    goal = gl[0]
    platforms = [p for p in PLATFORMS if p in (platforms or [])] or ["Instagram"]
    lib = plans.library()
    chosen = creators is not None and len(creators) > 0
    if creators is not None:
        raw, skipped = _posts_from_creators(creators, platforms, second_posts)
        in_play = [c for c in creators if c.get("name") not in skipped and c.get("code") not in skipped
                   and any((c.get("followers") or {}).get(p) for p in platforms)]
        n_creators = len(in_play)
        sel_by_size = _by_size_creators(in_play, platforms)
    else:
        raw, skipped = _posts_from_mix(mix, platforms), []
        per = {p: sum(1 for x in raw if x["platform"] == p) for p in platforms}
        n_creators = max(per.values()) if per else 0
        m = mix or {}
        per_plat = any(isinstance(v, dict) for v in m.values())
        sel_by_size = {}
        for p in platforms:
            mm = m.get(p) if per_plat else m
            for t in plans.TIERS:
                k = max(0, min(int((mm or {}).get(t) or 0), 200))
                if k:
                    sel_by_size[t] = max(sel_by_size.get(t, 0), k)
    posts = [dict(p, **post_values(p["platform"], p["followers"], p.get("doc"), p.get("score"), lib)) for p in raw]
    for p in posts:
        if p.get("second"):
            for k in ("views", "interactions", "reach", "clicks"):
                p[k] *= SECOND_POST
    first_posts = [p for p in posts if not p.get("second")]

    # -- the recommended structure: the same number of creators and posts, or the number the client
    # chose (any whole number COUNT_MIN..COUNT_MAX; outside the usual range is fine): one post per
    # creator per chosen platform
    try:
        chosen = int(count) if count else 0
    except (TypeError, ValueError):
        chosen = 0
    chosen = max(COUNT_MIN, min(chosen, COUNT_MAX)) if chosen else 0
    default_n = n_creators
    if chosen:
        n_ideal = chosen
        per_platform = {p: n_ideal for p in platforms}
    elif first_posts:
        if creators is not None:
            ideal_per = _even(len(first_posts), len(platforms))
            per_platform = {p: c for p, c in zip(platforms, ideal_per)}
        else:
            per_platform = {p: sum(1 for x in first_posts if x["platform"] == p) for p in platforms}
        n_ideal = n_creators
    else:
        n_ideal = 0
        per_platform = {p: 0 for p in platforms}
    n_ideal = max(0, min(n_ideal, 400))
    counts = ideal_counts(gl, n_ideal, platforms, table, per_platform_posts=per_platform) if n_ideal else {p: {} for p in platforms}
    ideal_posts = _ideal_posts(counts, lib)
    lead = max(platforms, key=lambda p: per_platform.get(p, 0)) if per_platform else platforms[0]
    ideal_by_size = dict(counts.get(lead) or {})

    sel = _side(posts, gl, n_creators, sel_by_size, platforms)
    sel["_posts"] = posts
    ideal = _side(ideal_posts, gl, n_ideal, ideal_by_size, platforms)
    ideal["_posts"] = ideal_posts
    ideal["score"] = 50 if ideal_posts else None          # typical creators: the peer-median score
    quality = _quality(sel, ideal, gl) if first_posts and ideal_posts else None
    c_lo, c_hi = count_range_for(gl)

    measured_c = len({p.get("code") for p in first_posts if p.get("measured") and p.get("code")}) if creators is not None else 0
    if creators is not None and first_posts:
        trust = "Based on measured data for %d of %d creator%s." % (measured_c, n_creators, "" if n_creators == 1 else "s")
    else:
        trust = "Based on what similar creators of each size deliver; no individual creator measured."
    plat_line = " and ".join(platforms)
    unit = _unit_by_size(lead, gl, lib)
    gap = _gap_words(sel_by_size, ideal_by_size, unit, n_ideal) if first_posts and n_ideal else []
    goal_label = " + ".join(GOAL_LABEL[g] for g in gl)
    shape = shape_for(gl, table)
    return {
        "goal": goal, "goals": gl, "goal_label": goal_label, "platforms": platforms,
        "creators": n_creators, "posts": len(posts), "skipped": skipped, "measured_posts": sum(1 for p in posts if p.get("measured")),
        "measured_creators": measured_c,
        "figures": sel["figures"], "totals": sel["totals"],
        "selection": dict({k: v for k, v in sel.items() if not k.startswith("_")},
                          on_structure=_on_structure(sel_by_size, ideal_by_size) if first_posts and n_ideal else {}),
        "ideal": dict({k: v for k, v in ideal.items() if not k.startswith("_")},
                      title="Ideal for %s with %d creator%s" % (goal_label, n_ideal, "" if n_ideal == 1 else "s"),
                      shape=[{"size": t, "label": TIER_NAME[t][0], "pct": round(shape[t])} for t in TIER_ORDER if t in shape],
                      tolerance=ON_STRUCTURE_POINTS,
                      mix=counts, name=STRUCTURE_NAME),
        "quality": ({k: v for k, v in quality.items() if not k.startswith("_")} if quality else None),
        "gap": gap, "ways": [],
        "count": n_ideal, "ideal_count": n_ideal, "count_default": default_n,
        "count_range": {"low": c_lo, "high": c_hi, "text": "%d–%d" % (c_lo, c_hi), "min": COUNT_MIN, "max": COUNT_MAX},
        "compare_line": _compare_line(counts.get(lead) or {}, sel_by_size, n_ideal, n_creators, goal_label) if n_ideal else "",
        "trust": {"line": trust, "measured": measured_c, "of": n_creators if creators is not None and first_posts else 0},
        "note": ESTIMATE_LINE,
        "summary": "%s · %s · %s" % (goal_label, plat_line,
                                     ("%d creator%s" % (n_creators, "" if n_creators == 1 else "s")) if n_creators else "no creators yet"),
        "estimate": True, "version": 4,
        "_posts": posts, "_ideal_posts": ideal_posts, "_q": quality["_q"] if quality else None,
        "_sel_by_size": sel_by_size, "_ideal_by_size": ideal_by_size, "_unit": unit,
    }


def public(res):
    """The result without the working (never sent to a client)."""
    return {k: v for k, v in res.items() if not k.startswith("_")}


# ------------------------------------------------------------ the advice --

def _creator_contrib(res, gl):
    """{code: share of the recommended structure's result the creator adds} (quality points / 100)."""
    ip = res["_ideal_posts"]
    norm = {}
    for g in gl:
        vk, _m = _PRIMARY_FIELD[g]
        norm[g] = sum(p[vk] for p in ip) or 1.0
    out = {}
    for p in res["_posts"]:
        if not p.get("code"):
            continue
        out[p["code"]] = out.get(p["code"], 0.0) + sum(p[_PRIMARY_FIELD[g][0]] / norm[g] for g in gl) / len(gl)
    return out


def _as_creator(entries):
    """One creator dict from the candidate rows of one code (one per platform)."""
    first = entries[0]
    return {"code": first["code"], "name": first.get("name") or first["code"],
            "followers": {e["platform"]: e["followers"] for e in entries}, "docs": {},
            "scores": {e["platform"]: e["score"] for e in entries if e.get("score") is not None}}


def advise(res, gl, creators=None, candidates=None, max_items=3, platforms=None, second=None, count=None):
    """Ways to improve, ranked by the quality points each adds, at most ``max_items``. Each is
    {"id", "text", "gain", "points", "action": {...}}; the action is machine-readable:
      {"type": "replace", "remove": [code], "add": [code]}
      {"type": "remove", "codes": [...]}          {"type": "add", "codes": [...]}
      {"type": "second_post", "codes": [...]}     {"type": "add_platform", "platform": "TikTok"}
      {"type": "use_mix", "mix": {platform: {size: n}}}      (a mix input: switch to the recommended one)
    Each is scored by re-running the calculator, so the gain is the real change in selection
    quality. Ranking is by performance, never by price."""
    q0 = res.get("_q")
    gl = gl or ["awareness"]
    platforms = platforms or res["platforms"]
    items = []
    if creators is None:
        ideal = res.get("ideal") or {}
        if q0 is not None and q0 < 0.9 and ideal.get("mix"):
            items.append({"id": "use_mix", "gain": 1.0 - q0, "points": int(round((1.0 - q0) * 100)),
                          "text": "Your mix reaches about %d%% of the recommended structure, which is %s." % (
                              int(5 * round(q0 * 20)), mix_text(ideal["mix"])),
                          "action": {"type": "use_mix", "mix": ideal["mix"]}})
        return items[:max_items]
    if q0 is None or not creators:
        return items

    def quality_of(cs, plats=None, sec=None):
        r = estimate(gl[0], plats or platforms, creators=cs, goals=gl, second_posts=sec if sec is not None else second, count=count)
        return r.get("_q")

    contrib = _creator_contrib(res, gl)
    by_code = {c["code"]: c for c in creators}
    ranked = sorted((c for c in creators if c["code"] in contrib), key=lambda c: contrib[c["code"]])
    sel_c, ideal_c = res["_sel_by_size"], res["_ideal_by_size"]
    missing = [t for t in TIER_ORDER if ideal_c.get(t, 0) > sel_c.get(t, 0)]
    surplus = [t for t in TIER_ORDER if sel_c.get(t, 0) > ideal_c.get(t, 0)]

    def size_of_creator(c):
        fol = [int(c["followers"][p]) for p in platforms if (c.get("followers") or {}).get(p)]
        return tier_of(max(fol)) if fol else None

    def who(c):
        return "%s (%s)" % (c.get("name") or c["code"], c["code"])

    # candidates by creator, best first (by the score-adjusted value they would add), missing sizes first
    cands = {}
    for e in candidates or []:
        cands.setdefault(e["code"], []).append(e)
    lib = plans.library()
    pool = []
    for code, rows in cands.items():
        if code in by_code:
            continue
        cr = _as_creator(rows)
        t = size_of_creator(cr)
        if t is None:
            continue
        val = sum(post_values(p, f, None, cr["scores"].get(p), lib)["views"] for p, f in cr["followers"].items() if p in platforms)
        pool.append((t in missing, val, cr, t))
    pool.sort(key=lambda x: (not x[0], -x[1], x[2]["code"]))
    pool = pool[:6]

    # 1) replace the weakest (preferring one whose size is in surplus) with a creator of a missing size
    weak = [c for c in ranked if size_of_creator(c) in surplus][:2] or ranked[:1]
    best = None
    for w in weak:
        for _m, _v, cr, t in pool[:3]:
            if not _m:
                continue
            q = quality_of([c for c in creators if c["code"] != w["code"]] + [cr])
            if q is not None and (best is None or q > best[0]):
                best = (q, w, cr, t)
    if best and best[0] - q0 >= GOOD_ENOUGH:
        q, w, cr, t = best
        items.append({"id": "replace", "gain": q - q0, "points": int(round((q - q0) * 100)),
                      "text": "Swap %s, a %s creator who adds little, for %s, a %s creator." % (
                          who(w), SIZE_WORD[size_of_creator(w) or "micro"], who(cr), SIZE_WORD[t]),
                      "action": {"type": "replace", "remove": [w["code"]], "add": [cr["code"]]}})
    # 2) take the weakest out (the recommended structure for one creator fewer is closer)
    if len(creators) > 1:
        w = ranked[0]
        q = quality_of([c for c in creators if c["code"] != w["code"]])
        if q is not None and q - q0 >= GOOD_ENOUGH:
            items.append({"id": "remove", "gain": q - q0, "points": int(round((q - q0) * 100)),
                          "text": "%s adds the least. Keep as reserve or remove." % who(w),
                          "action": {"type": "remove", "codes": [w["code"]]}})
    # 3) add a creator of a missing size, best performer first
    best = None
    for _m, _v, cr, t in pool[:3]:
        q = quality_of(creators + [cr])
        if q is not None and (best is None or q > best[0]):
            best = (q, cr, t)
    if best and best[0] - q0 >= GOOD_ENOUGH:
        q, cr, t = best
        items.append({"id": "add", "gain": q - q0, "points": int(round((q - q0) * 100)),
                      "text": "Add %s, a %s creator and a strong performer." % (who(cr), SIZE_WORD[t]),
                      "action": {"type": "add", "codes": [cr["code"]]}})
    # 4) a second post for the best performers
    top = [c["code"] for c in reversed(ranked) if c["code"] not in (second or [])][:2]
    if top:
        q = quality_of(creators, sec=list(second or []) + top)
        if q is not None and q - q0 >= GOOD_ENOUGH:
            items.append({"id": "second", "gain": q - q0, "points": int(round((q - q0) * 100)),
                          "text": "A second post from your top %d creator%s adds about %d points." % (
                              len(top), "" if len(top) == 1 else "s", int(round((q - q0) * 100))),
                          "action": {"type": "second_post", "codes": top}})
    # 5) another platform
    for p in PLATFORMS:
        if p in platforms:
            continue
        on = sum(1 for c in creators if (c.get("followers") or {}).get(p))
        if on < max(1, len(creators) // 2):
            continue
        q = quality_of(creators, plats=list(platforms) + [p])
        if q is not None and q - q0 >= GOOD_ENOUGH:
            items.append({"id": "platform", "gain": q - q0, "points": int(round((q - q0) * 100)),
                          "text": "Add %s: %d of your %d creators are there." % (p, on, len(creators)),
                          "action": {"type": "add_platform", "platform": p}})
    items.sort(key=lambda i: -i["gain"])
    return items[:max_items]


def mix_text(mix):
    bits = []
    for p, m in (mix or {}).items():
        parts = ["%d %s" % (m[t], SIZE_WORD[t]) for t in TIER_ORDER if m.get(t)]
        if parts:
            bits.append("%s on %s" % (", ".join(parts), p))
    return "; ".join(bits)


def candidates_from_db(exclude, platforms, goals, objective=None, target=None, limit=40):
    """Roster creators to add, best performers first (score), on the chosen platforms, not
    already in the selection. Each {"code", "name", "platform", "size", "followers", "score"}."""
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
            out.append({"code": c["code"], "name": c["name"], "platform": p, "size": tier_of(f), "followers": f, "score": s["score"]})
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


def full(goal, platforms, creators=None, mix=None, goals=None, second_posts=None, sel=None, with_advice=True, count=None):
    """The comparison with the ways to improve, as the API returns it (no working)."""
    res = estimate(goal, platforms, creators=creators, mix=mix, goals=goals, second_posts=second_posts, count=count)
    gl = res["goals"]
    if with_advice:
        cands = None
        if creators is not None and creators:
            try:
                inside = json.loads(sel["codes"] or "[]") if sel is not None else []
                cands = candidates_from_db([c["code"] for c in creators] + inside, res["platforms"], gl,
                                           objective_for_selection(sel, gl) if sel is not None else None)
            except Exception:
                cands = None
        res["ways"] = advise(res, gl, creators=creators, candidates=cands, second=second_posts, count=count)
    return public(res)


# ------------------------------------------------------------------ saving --

def save(code_id, sel_id, goal, inp, result, by=""):
    result = public(result) if isinstance(result, dict) else result
    with db.connect() as conn:
        cur = conn.execute("INSERT INTO roi_estimates (code_id, selection_id, goal, input, result, created_at, created_by) "
                           "VALUES (?,?,?,?,?,?,?)", (code_id, sel_id, goal, json.dumps(inp)[:4000], json.dumps(result)[:30000],
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


# What older estimates carried and the calculator no longer shows (budget and market, cost per
# result, the market verdict, frequency, the budget plan, advice, sources): stripped on read.
_REMOVED_RESULT = ("advice", "sources", "cost", "verdict", "split", "_posts", "budget", "market", "market_label", "plan",
                   "planned_creators")
_REMOVED_INPUT = ("budget", "market")
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
    inp = {k: v for k, v in json.loads(r["input"] or "{}").items() if k not in _REMOVED_INPUT}
    return {"id": r["id"], "goal": r["goal"], "at": r["created_at"], "input": inp,
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

_COUNT = _re.compile(r"\b(\d{1,3})\s*(?:x\s*)?(?:creators?|influencers?|bloggers?|ugc|accounts?|posts?|reels?|videos?|مؤثر\w*|منشئ\w*)", _re.I)
_ASK = _re.compile(r"\b(reach|what can|how (many|much) (views|reach|people|clicks)|get me|roi|ideal|best mix|structure|mix)\b", _re.I)


def from_text(text):
    """A typed "what can 10 creators on TikTok do for clicks?" answered at once with a calculator
    card (the recommended structure for that number of creators): free, no AI call. None when the
    message is not that question."""
    t = " ".join(ascii_digits(text).split())
    m = _COUNT.search(t)
    if not m or not _ASK.search(t):
        return None
    n = int(m.group(1))
    if n < COUNT_MIN or n > COUNT_MAX:
        return None
    low = t.lower()
    goal = "traffic" if _re.search(r"click|traffic|visit|site|link|landing|زيارات", low) else \
        "engagement" if _re.search(r"engag|interact|comment|تفاعل", low) else "awareness"
    plats = [p for p, w in (("Instagram", r"insta|\big\b|reels"), ("TikTok", r"tik ?tok"), ("Snapchat", r"snap"), ("YouTube", r"youtube"))
             if _re.search(w, low)] or ["Instagram", "TikTok"]
    res = estimate(goal, plats, creators=[], goals=[goal], count=n)
    out = public(res)
    ideal = out["ideal"]
    out["figures"] = ideal["figures"]                       # the card shows the recommended structure's results
    out["ideal_only"] = True
    out["mix"] = ideal["mix"]
    out["summary"] = ideal["title"] + " · " + " and ".join(plats)
    out["count"] = n
    return out
