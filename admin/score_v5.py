"""Scoring v5 (draft, 2026-10-13, rev 5): the score is the lead metric(s) only; quality is shown beside it.
Standalone: not wired into the portal.

    SCORED     Awareness  = view rate (views or reel plays / followers)
               Engagement = engagement rate
               Traffic    = 70% engagement rate + 30% view rate
    LABELS     audience fit (share of followers in the target country) and authenticity (fake followers %)
               are reported beside the score as Good / Fair / Poor. They never change the score
               (Penduline backtest, 2026-10-13: neither predicted the views a creator delivered).

Each metric is calculated from the best source available, then from lower rungs with a lower
confidence factor (1.0 = a stored figure we trust; less = derived or proxy). The result reports, per
metric, which rung was used; the overall confidence; which values are estimated; and which are still
missing so they can be checked by hand. A missing value is left out and does NOT change the score.
The scored metrics are required: without one the creator "needs data".

Benchmarks: a metric is graded only against the published international range [low, high] for the
platform and size band (engagement: intl_benchmarks.py; view rate: reference/benchmarks.json):
at the low end of the range = 40 points, at the high end = 75, and 100 at 2x the high end for engagement
or 5x the high end for view rate (reel plays can exceed followers, so view rate needs more headroom).

    score      = sum(weight * confidence * metric score) / sum(weight * confidence)   over scored metrics present
    confidence = sum(weight * confidence of metrics present) / sum(weight * best confidence, scored metrics)
                 High >= 85%, Medium >= 60%, else Low (shown with the score; Low = indicative only)
Bands: Strong >= 70, Fair 50-69, Weak < 50."""
import statistics
import intl_benchmarks
import score_model

VERSION = "2026-10-13.5"
SCORED = ("reach", "engagement")
LABELS = ("audience_fit", "authenticity")
WEIGHTS = {
    "Awareness":  {"reach": 100, "engagement": 0},
    "Engagement": {"reach": 0, "engagement": 100},
    "Traffic":    {"reach": 30, "engagement": 70},
}
ALIAS = {"Conversion": "Traffic", "Launch": "Awareness"}
AUTH_CURVE = [(15, 100), (25, 85), (32, 70), (43, 45), (55, 20), (70, 0)]
IMPLAUSIBLE = {"engagement": 50.0, "reach": 500.0}   # above this the figure is read as a bad scrape
TOP = {"engagement": 2.0, "reach": 5.0}              # the score reaches 100 at this multiple of the range's high end
MIN_POSTS = 2                                        # posts needed to derive a figure from recent posts

# confidence factor per ladder rung (assumptions, editable)
CONF = {
    "engagement": {"stored": 1.0, "recent_posts": 0.7, "unsupported": 0.5},
    "reach": {"stored": 0.9, "recent_posts": 0.6, "derived": 0.4},
    "audience_fit": {"report": 0.8, "report_old": 0.6, "creator_country": 0.4},
    "authenticity": {"stored": 0.6, "inferred": 0.3},
}
BEST = {m: max(v.values()) for m, v in CONF.items()}
FIX = {
    "engagement": "Refresh with Apify, or ask the creator for an insights screenshot.",
    "reach": "Refresh with Apify (average views / reel plays).",
    "audience_fit": "Request an audience analysis (country split).",
    "authenticity": "Run an audit tool or request an analysis (fake followers %).",
}
COUNTRY_CODE = {"saudi arabia": "SA", "united arab emirates": "AE", "uae": "AE", "egypt": "EG", "kuwait": "KW",
                "qatar": "QA", "bahrain": "BH", "oman": "OM", "jordan": "JO", "lebanon": "LB", "iraq": "IQ"}
STRONG_SOURCES = ("stored", "report")


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _interp(points, x):
    if x <= points[0][0]:
        return float(points[0][1])
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (x - x0) / (x1 - x0) * (y1 - y0)
    return float(points[-1][1])


def weights_for(objective):
    """Weights over the scored metrics; 'A+B' blends are averaged. Unknown names read as Engagement."""
    raw = [p.strip() for p in str(objective or "Engagement").split("+") if p.strip()]
    names = []
    for p in raw:
        names += ["Awareness", "Engagement", "Traffic"] if p == "Balanced" else [ALIAS.get(p, p)]
    names = [n if n in WEIGHTS else "Engagement" for n in names] or ["Engagement"]
    return {m: sum(WEIGHTS[n][m] for n in names) / float(len(names)) for m in SCORED}


# -- benchmarks -------------------------------------------------------------------------------------
def _range(kind, platform, followers):
    if kind == "engagement":
        ref = intl_benchmarks.reference(platform, followers)
        rng = [ref["low"], ref["high"]] if ref else None
    else:
        got = score_model.research_range("view_rate", platform, followers)
        rng = list(got[0]) if got else None
    if rng and rng[1] <= rng[0]:
        rng[1] = rng[0] * 1.25
    return rng


def _grade(kind, value, rng):
    low, high = rng
    return max(0.0, min(100.0, _interp([(0.0, 0.0), (low, 40.0), (high, 75.0), (TOP[kind] * high, 100.0)], value)))


def _graded(kind, value, creator, source, conf, note=None):
    """Entry for a benchmarked metric, or None when the value is implausible or has no benchmark."""
    platform, followers = creator.get("platform"), _num(creator.get("followers"))
    if value is None or value < 0 or value > IMPLAUSIBLE[kind]:
        return None
    rng = _range(kind, platform, followers) if followers else None
    if not rng:
        return None
    mid = (rng[0] + rng[1]) / 2.0
    return {"value": round(value, 2), "score": _grade(kind, value, rng), "source": source, "confidence": conf,
            "benchmark": {"low": rng[0], "high": rng[1], "band": intl_benchmarks.band_of(followers)},
            "pct_of_benchmark": int(round(value / mid * 100)),
            "label": "below" if value < rng[0] else "above" if value > rng[1] else "within", "note": note}


def _posts(creator):
    return [p for p in (creator.get("recent_posts") or []) if isinstance(p, dict)]


# -- the ladders ------------------------------------------------------------------------------------
def _engagement(c):
    platform, followers = c.get("platform"), _num(c.get("followers"))
    er = _num(c.get("er_pct"))
    has = lambda k: _num(c.get(k)) is not None
    backed = has("avg_likes") or has("avg_views") or has("avg_plays") or has("engagements")
    # rung 1: the stored rate with figures behind it. Instagram needs likes (hidden likes understate the rate).
    if er is not None and (has("avg_likes") if platform == "Instagram" else backed):
        got = _graded("engagement", er, c, "stored", CONF["engagement"]["stored"])
        if got:
            return got
    # rung 2: derived from the recent posts we hold
    posts = _posts(c)
    val, n = None, 0
    if platform == "Instagram" and followers:
        use = [(_num(p.get("likes")), _num(p.get("comments")) or 0.0) for p in posts if _num(p.get("likes")) is not None]
        if len(use) >= MIN_POSTS:
            val, n = statistics.mean((l + m) / followers * 100.0 for l, m in use), len(use)
    elif platform == "TikTok":
        use = [(_num(p.get("views")), (_num(p.get("likes")) or 0.0) + (_num(p.get("comments")) or 0.0)) for p in posts]
        use = [u for u in use if u[0]]
        if len(use) >= MIN_POSTS:
            val, n = sum(u[1] for u in use) / sum(u[0] for u in use) * 100.0, len(use)
    if val is not None:
        got = _graded("engagement", val, c, "recent_posts", CONF["engagement"]["recent_posts"], "from %d posts" % n)
        if got:
            return got
    # rung 3: a TikTok rate with nothing to verify it (it is per view, so hidden likes do not understate it)
    if platform == "TikTok" and er is not None:
        return _graded("engagement", er, c, "unsupported", CONF["engagement"]["unsupported"], "rate only, nothing to verify it")
    return None


def _reach(c):
    followers = _num(c.get("followers"))
    if not followers:
        return None
    plays = _num(c.get("avg_plays")) or _num(c.get("avg_views"))
    if plays:                                                       # rung 1: the stored average
        got = _graded("reach", plays / followers * 100.0, c, "stored", CONF["reach"]["stored"])
        if got:
            return got
    views = [v for v in (_num(p.get("views")) for p in _posts(c)) if v]
    if len(views) >= MIN_POSTS:                                     # rung 2: median of the recent posts
        got = _graded("reach", statistics.median(views) / followers * 100.0, c, "recent_posts",
                      CONF["reach"]["recent_posts"], "median of %d posts" % len(views))
        if got:
            return got
    eng, er = _num(c.get("engagements")), _num(c.get("er_pct"))
    if c.get("platform") == "TikTok" and eng and er:                # rung 3: the TikTok rate is engagements / views
        return _graded("reach", eng / (er / 100.0) / followers * 100.0, c, "derived", CONF["reach"]["derived"],
                       "engagements / rate (rough)")
    return None


# -- quality labels (shown beside the score, never scored) -------------------------------------------
def _audience(c, country):
    if not country:
        return None
    aud = c.get("aud_countries") or []
    if aud:                                                         # rung 1: the audience report
        want = str(country).lower()
        code = COUNTRY_CODE.get(want, want).lower()
        hit = next((a for a in aud if str(a.get("name") or "").lower() == want or str(a.get("code") or "").lower() == code), None)
        pct = hit["pct"] if hit else 0.0
        src = "report_old" if (_num(c.get("aud_report_age_days")) or 0) > 90 else "report"
        return {"value": pct, "label": "Good" if pct >= 50 else "Fair" if pct >= 25 else "Poor", "source": src,
                "confidence": CONF["audience_fit"][src], "note": "%s%% of followers in %s" % (round(pct), country)}
    own = c.get("country")                                          # rung 2: where the creator is based (a proxy)
    if own:
        same = str(own).lower() == str(country).lower()
        return {"value": own, "label": "Fair" if same else "Poor", "source": "creator_country",
                "confidence": CONF["audience_fit"]["creator_country"], "note": "based in %s; audience unknown" % own}
    return None


def _authenticity(c, eng):
    fake = _num(c.get("fake_pct")) if c.get("platform") != "TikTok" else None    # TikTok has no fake-follower data
    if fake is not None:                                            # rung 1: the stored figure
        return {"value": fake, "label": "Good" if fake <= 25 else "Fair" if fake <= 40 else "Poor", "source": "stored",
                "confidence": CONF["authenticity"]["stored"], "note": "%s%% fake followers" % round(fake)}
    # rung 2: a collapse in verified engagement is a warning sign
    if eng and eng["source"] in ("stored", "recent_posts") and eng["value"] < 0.5 * eng["benchmark"]["low"]:
        return {"value": None, "label": "Poor", "source": "inferred", "confidence": CONF["authenticity"]["inferred"],
                "note": "engagement far below the benchmark"}
    return None


# -- gates and the score ----------------------------------------------------------------------------
def gates(creator, campaign):
    """Reasons the creator does not fit the campaign at all ([] = passes)."""
    why = []
    if campaign.get("platform") and creator.get("platform") != campaign["platform"]:
        why.append("platform")
    if campaign.get("countries") and creator.get("country") not in campaign["countries"]:
        why.append("country")
    if campaign.get("industries") and not (creator.get("industry") in campaign["industries"]
                                            and creator.get("industry_tier") in ("Confirmed", "Probable")):
        why.append("industry")
    days = _num(creator.get("days_since_post"))
    if days is not None and days > campaign.get("max_days", 90):
        why.append("inactive")
    return why


def score(creator, objective="Engagement", target_country=None):
    """creator: platform, followers, country, er_pct, avg_likes, avg_comments, avg_views, avg_plays, engagements,
    fake_pct, aud_countries[{name|code,pct}], recent_posts[{views,likes,comments}], aud_report_age_days (optional).
    Returns the score, band, confidence, the rung used per metric, the estimated values, the quality labels and the
    values to check by hand (missing; they never change the score)."""
    w = {m: v for m, v in weights_for(objective).items() if v > 0}
    eng = _engagement(creator)
    found = {"engagement": eng if "engagement" in w else None, "reach": _reach(creator) if "reach" in w else None}
    present = {m: e for m, e in found.items() if e}
    quality = {"audience_fit": _audience(creator, target_country), "authenticity": _authenticity(creator, eng)}
    quality_present = {k: v for k, v in quality.items() if v}
    check = [{"metric": m, "scored": True, "fix": FIX[m]} for m in w if m not in present]
    check += [{"metric": m, "scored": False, "fix": FIX[m]} for m in LABELS
              if m not in quality_present and not (m == "audience_fit" and not target_country)]
    if not present:
        return {"version": VERSION, "unscored": True, "reason": "Needs data: no usable scored metric.",
                "check_manually": check}
    eff = {m: w[m] * present[m]["confidence"] for m in present}
    final = sum(eff[m] * present[m]["score"] for m in present) / sum(eff.values())
    coverage = sum(eff.values()) / sum(w[m] * BEST[m] for m in w)
    confidence = "High" if coverage >= 0.85 else "Medium" if coverage >= 0.6 else "Low"
    estimated = [m for m, e in present.items() if e["source"] not in STRONG_SOURCES]
    estimated += [m for m, e in quality_present.items() if e["source"] not in STRONG_SOURCES]
    return {"version": VERSION, "unscored": False, "score": round(final, 1),
            "band": "Strong" if final >= 70 else "Fair" if final >= 50 else "Weak",
            "confidence": confidence, "confidence_pct": int(round(coverage * 100)),
            "indicative": confidence == "Low", "metrics": present, "quality": quality_present,
            "estimated": estimated, "check_manually": check, "objective": objective}
