"""Peer benchmarks from our own roster (fix batch 6, Bido 2026-10-10).

A creator is judged against creators of the SAME PLATFORM and the SAME SIZE, never against
a number from a report and never against a bigger or smaller account. The peers are the
analyses already on file (creator_analysis); nothing is stored: the cells are worked out
when asked for and cached for ten minutes.

    sizes     nano < 20K, micro 20-100K, mid 100-500K, macro 500K-1M, mega 1M+
    metrics   er             engagement: Instagram per follower, TikTok/YouTube per view, %
              er_med         the same from a creator's MEDIAN post (new TikTok analyses)
              view_rate      average views of a video / followers, %
              view_rate_med  the same from the median video
              spread         how much views swing (std / mean of the sampled posts): lower = steadier

`percentile(platform, size, metric, value)` answers 0..1 (1 = better than every peer; for
`spread` the caller flips it) once a cell holds at least MIN_PEERS creators; below that it
answers None and the caller falls back to the global estimate (Settings) or drops the factor.

A creator's own record is read with `sample_of(platform, doc)`, the same function that
builds the cells, so a creator and their peers are always measured the same way.
"""
import json
import math
import time

MIN_PEERS = 30
TTL = 600                          # seconds a computed set of cells is kept
SIZES = ("nano", "micro", "mid", "macro", "mega")
SIZE_LABEL = {"nano": "Nano (under 20K)", "micro": "Micro (20K–100K)", "mid": "Mid (100K–500K)",
              "macro": "Macro (500K–1M)", "mega": "Mega (1M+)"}
METRICS = ("er", "er_med", "view_rate", "view_rate_med", "spread")
FEED = ("Instagram", "Facebook", "X")      # engagement is a rate per follower there

_cache = {"at": 0.0, "cells": None}
SOURCE = None                      # tests: a callable returning [(platform, doc), ...]


def size_of(followers):
    f = followers or 0
    return "nano" if f < 20000 else "micro" if f < 100000 else "mid" if f < 500000 else "macro" if f < 1000000 else "mega"


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v else None


def series_spread(series):
    """std / mean of a views series, 2 decimals; None when there are too few posts."""
    v = [float(x) for x in (series or []) if isinstance(x, (int, float)) and x >= 0]
    if len(v) < 5:
        return None
    mean = sum(v) / len(v)
    if mean <= 0:
        return None
    return round((sum((x - mean) ** 2 for x in v) / len(v)) ** 0.5 / mean, 2)


def sample_of(platform, doc):
    """{metric: value} for one analysis doc. Only what the doc really holds; nothing is guessed."""
    out = {}
    f = _num(doc.get("followers"))
    if not f or f < 1000:
        return out
    feed = platform in FEED
    er = _num(doc.get("er"))
    if feed:
        if er is not None and not doc.get("likes_hidden"):
            out["er"] = er
        ml, mc = _num(doc.get("median_likes")), _num(doc.get("median_comments"))
        if ml is not None and mc is not None:
            out["er_med"] = (ml + mc) / f * 100.0
        plays = _num(doc.get("avg_reel_plays"))
        if plays:
            out["view_rate"] = plays / f * 100.0
    else:
        if er is not None and (doc.get("er_basis") == "views" or not doc.get("er_note")):
            out["er"] = er
        med_er = _num(doc.get("median_er_on_views"))
        if med_er is not None:
            out["er_med"] = med_er
        av = _num(doc.get("avg_views"))
        if av:
            out["view_rate"] = av / f * 100.0
    mv = _num(doc.get("median_views"))
    if mv:
        out["view_rate_med"] = mv / f * 100.0
    sp = _num(doc.get("views_spread"))
    if sp is None:
        sp = series_spread(doc.get("views_series"))
    if sp is not None:
        out["spread"] = sp
    # a rate that is not a plausible share of followers/views is a bad scrape, not a peer
    for k in list(out):
        if out[k] < 0 or (k in ("er", "er_med") and out[k] > 100) or (k.startswith("view_rate") and out[k] > 5000) \
                or (k == "spread" and out[k] > 20):
            del out[k]
    return out


def _from_db():
    import db
    with db.connect() as conn:
        for r in conn.execute("SELECT platform, data FROM creator_analysis"):
            try:
                d = json.loads(r["data"])
            except (TypeError, ValueError):
                continue
            if isinstance(d, dict):
                yield r["platform"], d


def build(rows):
    """{(platform, size, metric): sorted values} from (platform, doc) rows."""
    cells = {}
    for platform, doc in rows:
        s = sample_of(platform, doc)
        if not s:
            continue
        size = size_of(_num(doc.get("followers")))
        for m, v in s.items():
            cells.setdefault((platform, size, m), []).append(v)
    for v in cells.values():
        v.sort()
    return cells


def cells(force=False):
    now = time.time()
    if force or _cache["cells"] is None or now - _cache["at"] > TTL:
        try:
            _cache["cells"], _cache["at"] = build(SOURCE() if SOURCE else _from_db()), now
        except Exception:
            # no table / no database (a unit test, a fresh install): no peers, try again in a minute
            _cache["cells"], _cache["at"] = {}, now - TTL + 60
    return _cache["cells"]


def invalidate():
    _cache["cells"], _cache["at"] = None, 0.0


def _q(vals, q):
    return vals[int(round(q * (len(vals) - 1)))]


def cell(platform, size, metric):
    """{"n", "p25", "median", "p75"} or None when there are no peers at all."""
    v = cells().get((platform, size, metric))
    if not v:
        return None
    return {"n": len(v), "p25": _q(v, .25), "median": _q(v, .5), "p75": _q(v, .75)}


def percentile(platform, size, metric, value, min_peers=MIN_PEERS):
    """{"pct": 0..1, "n", "p25", "median", "p75"} for ``value`` among same-platform, same-size
    peers; None when the cell holds fewer than ``min_peers`` creators. Mid-rank on ties."""
    v = cells().get((platform, size, metric))
    if value is None or not v or len(v) < min_peers:
        return None
    import bisect
    lo, hi = bisect.bisect_left(v, value), bisect.bisect_right(v, value)
    return {"pct": (lo + 0.5 * (hi - lo)) / len(v), "n": len(v), "p25": _q(v, .25), "median": _q(v, .5), "p75": _q(v, .75)}


def median(platform, size, metric, min_peers=MIN_PEERS):
    """The peer median, or None under ``min_peers`` creators."""
    c = cell(platform, size, metric)
    return c["median"] if c and c["n"] >= min_peers else None


def peer_median_pair(platform, size, med_metric, avg_metric, min_peers=MIN_PEERS):
    """(median, n, metric_used): the median-based cell when it is big enough, else the
    average-based one."""
    for m in (med_metric, avg_metric):
        c = cell(platform, size, m)
        if c and c["n"] >= min_peers:
            return c["median"], c["n"], m
    return None, 0, None


def table():
    """Every cell with at least one creator, for the admin page: [{platform, size, metric, n, p25, median, p75}]."""
    out = []
    for (p, s, m), v in sorted(cells().items(), key=lambda kv: (kv[0][0], SIZES.index(kv[0][1]), METRICS.index(kv[0][2]))):
        out.append({"platform": p, "size": s, "metric": m, "n": len(v), "p25": round(_q(v, .25), 2),
                    "median": round(_q(v, .5), 2), "p75": round(_q(v, .75), 2), "usable": len(v) >= MIN_PEERS})
    return out
