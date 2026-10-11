"""The creator score model (scoring v4, 2026-10-11): four parameters, each read from the posts we
hold, scaled between two editable points, and weighted by the campaign objective.

    engagement   median (likes + comments) / followers; per view on video platforms
    view_rate    median views / followers
    interest     posts naming the brief's product space / posts available (the posts are the 100%)
    consistency  how steady views are from post to post (std / mean of the views)

A band is [zero_at, full_at]: the value that scores 0 and the value that scores 100, linear
between. For consistency a LOWER number is better, so zero_at > full_at. Weights are per
objective and always read as shares of what is available (a missing parameter hands its weight
to the others). Editable in Admin > Settings > Creator score model (setting key ``score_model``)."""
import time

PARAMS = ("engagement", "view_rate", "interest", "consistency")
LABEL = {"engagement": "Engagement", "view_rate": "View rate", "interest": "Interest", "consistency": "Consistency"}
OBJECTIVES = ("Awareness", "Engagement", "Traffic")
VERSION = "2026-10-11.5"
ENGAGEMENT_IMPLAUSIBLE = 10.0   # % : above this the figure is read as a bad scrape, not a result
FEED_CAP = 79                   # a feed creator without views or an engagement figure cannot read Strong

WEIGHTS = {
    "Awareness":  {"engagement": 20, "view_rate": 45, "interest": 20, "consistency": 15},
    "Engagement": {"engagement": 45, "view_rate": 15, "interest": 25, "consistency": 15},
    "Traffic":    {"engagement": 30, "view_rate": 25, "interest": 30, "consistency": 15},
}
# metric -> group -> [zero_at, full_at]; "feed" = Instagram, Facebook, X (per follower), "video" = per view
BANDS = {
    "engagement":  {"feed": [0.3, 3.5], "video": [1.5, 7.0]},
    "view_rate":   {"feed": [3.0, 50.0], "video": [3.0, 50.0]},
    "consistency": {"feed": [2.0, 0.5], "video": [2.0, 0.5]},
}
_cache = {"at": 0.0, "over": {}}


def _overrides(fresh=False):
    now = time.time()
    if fresh or now - _cache["at"] > 60:
        try:
            import db
            got = db.setting("score_model")
            _cache["over"] = got if isinstance(got, dict) else {}
        except Exception:
            _cache["over"] = {}
        _cache["at"] = now
    return _cache["over"]


def _pos(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None


def weights(fresh=False):
    """{objective: {param: weight}} with the Settings overrides applied where valid."""
    over = (_overrides(fresh).get("weights") or {})
    out = {}
    for o, row in WEIGHTS.items():
        out[o] = {}
        for p, w in row.items():
            got = _pos((over.get(o) or {}).get(p))
            out[o][p] = got if got is not None else float(w)
    return out


def band(metric, group, fresh=False):
    """[zero_at, full_at] for a metric and platform group."""
    d = BANDS[metric][group]
    got = ((_overrides(fresh).get("bands") or {}).get(metric) or {}).get(group)
    if isinstance(got, (list, tuple)) and len(got) == 2 and _pos(got[0]) is not None and _pos(got[1]) is not None \
            and float(got[0]) != float(got[1]):
        return [float(got[0]), float(got[1])]
    return [float(d[0]), float(d[1])]


def scale(v, zero_at, full_at):
    """0..1: 0 at zero_at, 1 at full_at, linear and clamped; works for either direction."""
    if zero_at == full_at:
        return 0.0
    return max(0.0, min(1.0, (v - zero_at) / float(full_at - zero_at)))


# -- the research tiers (admin/reference/benchmarks.json, KSA block = global proxies) --------------
_PLAT_KEY = {"Instagram": "instagram_reels", "TikTok": "tiktok", "Snapchat": "snapchat", "YouTube": "youtube_shorts"}
_METRIC_KEY = {"engagement": "eng_rate", "view_rate": "view_rate"}
_TIERS = ("nano", "micro", "mid", "macro", "mega")
_ref = {"data": None}


def tier_of(followers):
    f = followers or 0
    return "nano" if f < 20000 else "micro" if f < 100000 else "mid" if f < 500000 else "macro" if f < 1000000 else "mega"


def _reference():
    if _ref["data"] is None:
        try:
            import json
            import os
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "reference", "benchmarks.json")) as fh:
                _ref["data"] = json.load(fh).get("markets", {}).get("KSA", {})
        except Exception:
            _ref["data"] = {}
    return _ref["data"]


def research_range(metric, platform, followers):
    """([low, high], tier) from the research for a metric, platform and size, or None. A tier with no
    figure (mega view rate) borrows the next smaller tier that has one."""
    key = _METRIC_KEY.get(metric)
    plat = _reference().get(_PLAT_KEY.get(platform) or "instagram_reels") or {}
    if not key or not plat:
        return None
    i = _TIERS.index(tier_of(followers))
    for t in reversed(_TIERS[:i + 1]):
        x = (plat.get(t) or {}).get(key) or {}
        lo, hi = _pos(x.get("low")), _pos(x.get("high"))
        if lo and hi:
            return [lo, hi], t
    return None


def band_for(metric, group, platform, followers):
    """([zero_at, full_at], source, tier): a value set in Settings wins; then the research tier
    (0 at the low end, 100 at twice the high end); then the flat default."""
    edited = ((_overrides().get("bands") or {}).get(metric) or {}).get(group)
    if isinstance(edited, (list, tuple)) and len(edited) == 2:
        return band(metric, group), "settings", None
    r = research_range(metric, platform, followers)
    if r:
        (lo, hi), tier = r
        return [lo / 2.0, hi * 2.0], "research", tier
    return band(metric, group), "default", None
