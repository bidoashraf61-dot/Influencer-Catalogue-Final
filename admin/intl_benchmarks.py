"""International engagement benchmarks: the reference every creator is scored against.

Bido, 2026-10-11: a creator's engagement is compared with published international
benchmarks (never with our own roster), and a benchmark is a RANGE, not one number:

    low   the lowest source's typical value for the band (the conservative floor)
    high  the middle source's typical value for the band

so a creator's score is a range too: scored against the high end (harsh) and against the
low end (generous). Where only two sources exist the "middle" is their average; where only
one exists low and high are the same.

    Instagram   (likes + comments) / followers, %   by follower band
    TikTok      interactions / views, %             by follower band

Platforms with no agreed benchmark (YouTube, Snapchat, Facebook, X) are not scored. Any
figure can be overridden from Settings (the ``intl_benchmarks`` key: {platform: {band: [low,
high]}}); the Settings page writes it.

Bands (followers): nano < 20K, micro 20K-100K, mid 100K-500K, macro 500K-1M, mega 1M+.
"""
import time

VERSION = "2026-10-11.2"

TABLE = {
    "Instagram": {
        "metric": "engagement per follower: (likes + comments) / followers, %",
        "basis": "followers",
        "bands": {"nano": [1.0, 3.75], "micro": [0.8, 2.75], "mid": [0.9, 2.25], "macro": [0.9, 1.5], "mega": [0.7, 1.5]},
        "rule": "low = lowest source; high = the middle of the three sources",
        "sources": [
            "IQFluence, Sep 2026, 30.1M Instagram creators, median by tier (lowest source)",
            "HypeAuditor, 2025, rough tiers (middle source)",
            "Buffer, Sep 2025, 27M posts / 273K connected accounts (highest source)",
        ],
    },
    "TikTok": {
        "metric": "engagement per view: interactions / views, %",
        "basis": "views",
        "bands": {"nano": [3.4, 3.8], "micro": [3.4, 3.6], "mid": [3.4, 3.7], "macro": [3.4, 3.7], "mega": [3.4, 3.4]},
        "rule": "low = Rival IQ; high = the average of Rival IQ and Socialinsider (only two sources)",
        "sources": [
            "Rival IQ, 2025, median brand account by view (3.4%, lowest source)",
            "Socialinsider, 2025, 2M videos / 214K profiles, by view (3.75-4.40% by size)",
        ],
    },
}

BANDS = ("nano", "micro", "mid", "macro", "mega")
BAND_LABEL = {"nano": "nano (under 20K)", "micro": "micro (20K-100K)", "mid": "mid (100K-500K)",
              "macro": "macro (500K-1M)", "mega": "mega (1M+)"}
SAMPLE_FOLLOWERS = {"nano": 1000, "micro": 50000, "mid": 200000, "macro": 700000, "mega": 2000000}

_cache = {"at": 0.0, "over": {}}


def band_of(followers):
    f = followers or 0
    return "nano" if f < 20000 else "micro" if f < 100000 else "mid" if f < 500000 else "macro" if f < 1000000 else "mega"


def _overrides(fresh=False):
    now = time.time()
    if fresh or now - _cache["at"] > 60:
        try:
            import db
            got = db.setting("intl_benchmarks")
            _cache["over"] = got if isinstance(got, dict) else {}
        except Exception:
            _cache["over"] = {}
        _cache["at"] = now
    return _cache["over"]


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def pair(platform, band, fresh=False):
    """[low, high] for a platform and band: the Settings override when it is valid, else the table's."""
    entry = TABLE.get(platform)
    if not entry or band not in entry["bands"]:
        return None
    got = (_overrides(fresh).get(platform) or {}).get(band)
    if isinstance(got, (list, tuple)) and len(got) == 2 and _num(got[0]) and _num(got[1]):
        lo, hi = float(got[0]), float(got[1])
        return [lo, max(lo, hi)]
    if _num(got):
        return [float(got), float(got)]
    lo, hi = entry["bands"][band]
    return [float(lo), float(hi)]


def reference(platform, followers):
    """{"low", "high", "mid", "band", "metric", "platform"} for a creator, or None when the
    platform has no agreed benchmark or the creator's size is unknown."""
    if platform not in TABLE or not followers:
        return None
    band = band_of(followers)
    p = pair(platform, band)
    if not p:
        return None
    return {"low": p[0], "high": p[1], "mid": round((p[0] + p[1]) / 2.0, 2), "band": band,
            "metric": TABLE[platform]["metric"], "platform": platform}


def table():
    """Rows for the admin page: platform, band, low, high, defaults, metric, sources."""
    out = []
    for platform, entry in TABLE.items():
        for band in BANDS:
            p = pair(platform, band, fresh=True)
            out.append({"platform": platform, "band": band, "label": BAND_LABEL[band], "low": p[0], "high": p[1],
                        "default": entry["bands"][band], "metric": entry["metric"], "sources": entry["sources"],
                        "version": VERSION})
    return out
