"""The sample full analysis (HELVY Connect item 39).

A client whose creator analysis is locked can open "a sample full analysis": the REAL analysis of one
configured creator, drawn by the same page as any full analysis, with everything that could say who it
is taken out. The page of the sample is built here and nowhere else: the endpoint takes no creator
code, so it can only ever serve the one configured creator, and the per-creator gating on
/api/creator is untouched.

Settings (Client portal -> Settings): ``sample_analysis_code`` (default HV-HCPG-003) and
``sample_analysis_on`` (default on).

Anonymisation is an allow-list: only the figures a full analysis page draws are copied, as numbers.
Name, handle, bio, photo, location, every URL and post cover, captions, brand names and hashtags are
never copied. Where the page needs a label for a list, a neutral one is written ("Brand A",
"#hashtag 1").
"""
import re

import db
import metrics

DEFAULT_CODE = "HV-HCPG-003"
LABEL = "Sample · anonymised creator"

# Plain figures of an analysis the page reads (analysis.OVERVIEW and REPORT_EXTRA, minus identity).
NUMBERS = ("followers", "following", "posts_count", "er", "avg_likes", "avg_comments", "avg_views", "avg_reel_plays",
           "paid_post_performance", "fake_followers_pct", "credibility_pct", "est_impressions", "est_reach", "reels_er",
           "avg_reel_likes", "avg_reel_comments", "avg_reel_shares", "story_reach", "story_impressions", "paid_views_pct",
           "fake_likers_pct", "real_people_pct", "mass_followers_pct", "suspicious_mass_pct", "suspicious_pct",
           "followers_change_pct", "avg_likes_change_pct", "notable_followers_pct", "sample_posts", "median_views",
           "median_er_on_views")
SECTIONS = ("countries", "cities", "gender", "ages", "ages_female", "ages_male", "languages", "interests",
            "brand_affinity", "reachability")
_BAD = re.compile(r"[@#]|https?:|www\.|\.(com|net|org|co|sa|ae)\b", re.I)


def config():
    on = db.setting("sample_analysis_on", True)
    code = str(db.setting("sample_analysis_code", DEFAULT_CODE) or DEFAULT_CODE).strip().upper()
    return bool(on), code


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _label(v, limit=48):
    """A list label copied only when it is plain words (no handle, tag or link)."""
    s = " ".join(str(v or "").split())[:limit]
    return None if not s or _BAD.search(s) else s


def _dist(d):
    if not isinstance(d, dict):
        return None
    out = {"buckets": [{"label": _label(b.get("label"), 12) or "", "h": _num(b.get("h"))}
                       for b in (d.get("buckets") or []) if isinstance(b, dict)]}
    for k in ("creator", "median"):
        if isinstance(d.get(k), int):
            out[k] = d[k]
    return out


def _audience(a, brand):
    out = {}
    if not isinstance(a, dict):
        return out
    for sec in SECTIONS:
        v = a.get(sec)
        if sec == "gender":
            if isinstance(v, dict):
                out[sec] = {k: _num(x) for k, x in v.items() if k in ("female", "male")}
            continue
        rows = []
        for r in (v or [])[:20] if isinstance(v, list) else []:
            if not isinstance(r, dict):
                continue
            key = "code" if "code" in r else "name"
            lab = _label(r.get(key))
            if sec == "brand_affinity" and lab:             # brands the audience follows: named only as letters
                lab = brand(lab)
            if lab and _num(r.get("pct")) is not None:
                rows.append({key: lab, "pct": r["pct"]})
        out[sec] = rows
    return out


def _letters(n):
    return "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[n % 26]


def anonymise(data, platform=None):
    """An analysis as the sample page may show it. ``data`` is one platform's stored analysis."""
    d = data if isinstance(data, dict) else {}
    out = {"sample": True, "platform": platform or d.get("platform") or "Instagram"}
    for k in NUMBERS:
        if _num(d.get(k)) is not None:
            out[k] = d[k]
    if d.get("account_type") in ("Creator", "Business", "Personal"):
        out["account_type"] = d["account_type"]
    if isinstance(d.get("likes_hidden"), bool):
        out["likes_hidden"] = d["likes_hidden"]
    if isinstance(d.get("updated"), str) and re.fullmatch(r"\d{4}-\d\d-\d\d", d["updated"][:10]):
        out["updated"] = d["updated"][:10]
    for k in ("fake_followers_dist", "er_dist"):
        v = _dist(d.get(k))
        if v:
            out[k] = v
    out["growth"] = [{"month": str(g.get("month"))[:7], "followers": _num(g.get("followers")), "avg_likes": _num(g.get("avg_likes"))}
                     for g in (d.get("growth") or []) if isinstance(g, dict)][:24]
    brands = {}

    def brand(name):
        key = str(name or "").strip().lower()
        if key not in brands:
            brands[key] = "Brand " + _letters(len(brands))
        return brands[key]

    out["audience"] = _audience(d.get("audience"), brand)
    out["audience_likers"] = _audience(d.get("audience_likers"), brand)

    def post(p, sponsored):
        o = {"url": "#", "thumb": None, "likes": _num(p.get("likes")), "comments": _num(p.get("comments")),
             "views": _num(p.get("views"))}
        if isinstance(p.get("date"), str) and re.fullmatch(r"\d{4}-\d\d(-\d\d)?", p["date"][:10]):
            o["date"] = p["date"][:10]
        if sponsored:
            o["brand"] = brand(p.get("brand"))
        return o
    out["top_posts"] = [post(p, False) for p in (d.get("top_posts") or []) if isinstance(p, dict)][:12]
    out["sponsored_posts"] = [post(p, True) for p in (d.get("sponsored_posts") or []) if isinstance(p, dict)][:12]
    out["brands"] = [{"name": brand(b.get("name")), "count": _num(b.get("count")), "logo": None}
                     for b in (d.get("brands") or []) if isinstance(b, dict)][:12]
    tags, n_tag, n_men = [], 0, 0
    for t in (d.get("hashtags") or [])[:20]:
        if not isinstance(t, dict):
            continue
        if str(t.get("tag") or "").startswith("@"):
            n_men += 1
            tags.append({"tag": "@mention%d" % n_men, "count": _num(t.get("count"))})
        else:
            n_tag += 1
            tags.append({"tag": "#hashtag%d" % n_tag, "count": _num(t.get("count"))})
    out["hashtags"] = tags
    out["creator_interests"] = [x for x in (_label(i) for i in (d.get("creator_interests") or [])[:8]) if x]
    return out


def source():
    """(creator row, {platform: stored analysis}) of the configured creator, or None when the
    sample is off, the creator is missing or inactive, or has no full analysis."""
    on, code = config()
    if not on or not code:
        return None
    c = db.creator(code)
    if c is None or not c["active"]:
        return None
    every = {p: a for p, a in (db.analyses(code) or {}).items() if not (a["data"] or {}).get("basic")}
    return (c, every) if every else None


def available():
    return source() is not None


def payload():
    """The page's data: the same shape as /api/creator, for the sample creator only, or None."""
    got = source()
    if got is None:
        return None
    c, every = got
    analyses = {p: anonymise(a["data"], p) for p, a in every.items()}
    plats = list(analyses)
    main = analyses[plats[0]]
    followers = int(sum(a.get("followers") or 0 for a in analyses.values()) or c["followers"] or 0)
    card = {"code": "SAMPLE", "name": "Sample creator", "tier": c["tier"], "city": None, "nationality": None,
            "interest": None, "followers": followers, "photo_url": None,
            "profiles": [{"platform": p, "url": None, "followers": analyses[p].get("followers")} for p in plats],
            "band": metrics.band_of(followers or main.get("followers"))}
    return {"ok": True, "sample": True, "label": LABEL, "creator": card, "platforms": plats, "analyses": analyses,
            "requested": [], "gate": {"state": "unlocked", "sample": True}, "benchmarks": metrics.benchmarks()}
