"""ROI Calculator for clients (HELVY Connect, phase D).

What the client's OWN budget can buy, before they brief HelloVoice: reach, views,
impressions and frequency (Awareness), interactions and engagement rate
(Engagement), or tracking-link clicks and landing visits (Traffic), each judged
good / moderate / low against a fair range. No sales and no revenue: HelloVoice
tracks up to the tracking link, so ROI here means cost per result.

Where the numbers come from, in order of trust:
  1. the creators' own measured averages (their analysis: average views, likes,
     comments), when a selection's creators are used and the platform matches;
  2. the industry guide in plans.LIBRARY (per platform and size: view rate,
     engagement rate, reach per view, CTR and the CPM / CPE / CPC a client should
     pay at most), editable in Settings -> Benchmark library;
  3. blended with HelloVoice's own tracked campaigns (plans.house_benchmarks)
     once there are enough posts.
A few planning assumptions the guide does not cover (impressions per view, the
share of clicks that reach the page) are HelloVoice's own and listed as such.

Never: creator fees, HelloVoice prices, margins. The budget is the client's
number and is only used to divide by.

Verdict words match the campaign report's grades: good / moderate / low.

    estimate(goal, budget, platforms, market, creators=None, mix=None)
    creators_of(selection, which)     a selection's creators as the calculator needs them
    save(...) / latest_for(sel_id)    an estimate kept with a selection
    versus(campaign)                  saved estimate against the live report
"""
import json

import db
import plans

GOALS = ("awareness", "engagement", "traffic")
GOAL_LABEL = {"awareness": "Awareness", "engagement": "Engagement", "traffic": "Traffic"}
PLATFORMS = ("Instagram", "TikTok", "Snapchat", "YouTube")
MARKETS = {"SA": "Saudi Arabia", "AE": "UAE", "EG": "Egypt"}
GRADE_LABEL = {"good": "Good", "moderate": "Moderate", "low": "Low"}
TIER_ORDER = ["mega", "macro", "mid", "micro", "nano"]
TIER_NAME = {"mega": ("Mega", "1M+ followers"), "macro": ("Macro", "500K–1M"), "mid": ("Mid", "100K–500K"),
             "micro": ("Micro", "20K–100K"), "nano": ("Nano", "Under 20K")}

# HelloVoice planning assumptions (not in the industry guide). Editable as the
# "roi_assumptions" setting; always listed as assumptions under the result.
ASSUMPTIONS = {
    "impressions_per_view": {"Instagram": 1.5, "TikTok": 1.2, "Snapchat": 1.0, "YouTube": 1.1},
    "landing_rate": 0.8,              # share of link clicks that load the page
    "frequency_good": [1.2, 3.5],     # times each person sees the content: the healthy range
}
HOUSE_MIN_POSTS = 20                  # below this our own results are too few to blend in
HOUSE_MAX_WEIGHT = 0.5

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


def assumptions():
    out = json.loads(json.dumps(ASSUMPTIONS))
    got = db.setting("roi_assumptions") or {}
    if isinstance(got, dict):
        for k, v in got.items():
            if k == "impressions_per_view" and isinstance(v, dict):
                for p, f in v.items():
                    if p in out[k] and isinstance(f, (int, float)) and 1 <= f <= 5:
                        out[k][p] = float(f)
            elif k == "landing_rate" and isinstance(v, (int, float)) and 0 < v <= 1:
                out[k] = float(v)
    return out


def tier_of(followers):
    """The calculator's five sizes (the client-facing bands: nano under 20K)."""
    f = followers or 0
    return "nano" if f < 20000 else "micro" if f < 100000 else "mid" if f < 500000 else "macro" if f < 1000000 else "mega"


def _lib_tier(t):
    return "micro" if t == "micro" else t          # plans uses the same five names


def _mid(pair):
    return (float(pair[0]) + float(pair[1])) / 2.0


def _rates(lib, house):
    """Per platform: the view rate and engagement rate per size, blended with HelloVoice's own
    results when there are enough of them. Returns (rates, blended_posts)."""
    out, used = {}, 0
    for p in PLATFORMS:
        L = lib[p]
        h = house.get(p) or {}
        w = 0.0
        if (h.get("posts") or 0) >= HOUSE_MIN_POSTS:
            w = min(HOUSE_MAX_WEIGHT, h["posts"] / 200.0)
            used += h["posts"]
        vr, er = {}, {}
        for t in plans.TIERS:
            v, e = _mid(L["view_rate"][t]), _mid(L["eng_rate"][t])
            if w and h.get("view_rate"):
                v = (1 - w) * v + w * h["view_rate"]
            if w and h.get("eng_rate"):
                e = (1 - w) * e + w * h["eng_rate"]
            vr[t], er[t] = v, e
        out[p] = {"view_rate": vr, "eng_rate": er, "eng_range": L["eng_rate"], "reach_per_view": L["reach_per_view"],
                  "ctr": _mid(L["ctr"]), "ctr_range": L["ctr"], "cpm": L["cpm"], "cpe": L["cpe"], "cpc": L["cpc"], "w": w}
    return out, used


def _grade_cost(x, ceilings):
    """Cost per result against [acceptable, good] ceilings: at or under good is good."""
    acc, good = ceilings
    if x is None:
        return None
    return "good" if x <= good else "moderate" if x <= acc else "low"


def _grade_rate(x, rng):
    """A rate against its [safe, expected] range: the middle or better is good."""
    if x is None:
        return None
    lo, hi = rng
    return "good" if x >= (lo + hi) / 2.0 else "moderate" if x >= lo else "low"


def _sig(grade):
    return {"grade": grade, "label": GRADE_LABEL.get(grade, "")} if grade else None


def _posts_from_creators(creators, platforms):
    """[(platform, tier, followers, own)] — one post per creator per chosen platform they are on."""
    posts, skipped = [], []
    for c in creators:
        on = [p for p in platforms if (c.get("followers") or {}).get(p)]
        if not on:
            skipped.append(c.get("name") or c.get("code"))
            continue
        for p in on:
            f = int(c["followers"][p])
            own = c.get("own") if c.get("own") and c["own"].get("platform") == p else None
            posts.append((p, tier_of(f), f, own))
    return posts, skipped


def _posts_from_mix(mix, platforms):
    posts = []
    for t in plans.TIERS:
        n = max(0, min(int((mix or {}).get(t) or 0), 200))
        for _ in range(n):
            for p in platforms:
                posts.append((p, t, plans.TIER_FOLLOWERS[t], None))
    return posts


def estimate(goal, budget, platforms, market="SA", creators=None, mix=None):
    goal = goal if goal in GOALS else "awareness"
    platforms = [p for p in PLATFORMS if p in (platforms or [])] or ["Instagram"]
    market = market if market in MARKETS else "SA"
    try:
        budget = max(0.0, min(float(str(budget or 0).replace(",", "")), 1e9))
    except ValueError:
        budget = 0.0
    lib = plans.library()
    house = plans.house_benchmarks()
    R, house_posts = _rates(lib, house)
    A = assumptions()
    if creators is not None:
        posts, skipped = _posts_from_creators(creators, platforms)
        n_creators = len(creators) - len(skipped)
    else:
        posts, skipped = _posts_from_mix(mix, platforms), []
        n_creators = sum(max(0, int((mix or {}).get(t) or 0)) for t in plans.TIERS)

    views = eng = reach = imps = clicks = 0.0
    likes = comments = 0.0
    measured_split = True
    by_plat, by_tier = {}, {}
    measured = 0
    for p, t, f, own in posts:
        r = R[p]
        if own and own.get("views"):
            v = float(own["views"])
            measured += 1
        else:
            v = f * r["view_rate"][_lib_tier(t)] / 100.0
        if own and own.get("eng") is not None and own.get("views"):
            e = float(own["eng"])
            if own.get("likes") is not None and own.get("comments") is not None:
                likes += float(own["likes"]); comments += float(own["comments"])
            else:
                measured_split = False
        else:
            e = v * r["eng_rate"][_lib_tier(t)] / 100.0
            measured_split = False
        views += v
        eng += e
        reach += v * r["reach_per_view"]
        imps += v * A["impressions_per_view"][p]
        clicks += v * r["ctr"] / 100.0
        by_plat[p] = by_plat.get(p, 0.0) + v
        by_tier[t] = by_tier.get(t, 0.0) + v

    def wavg(key, i=None):
        if not views:
            vals = [R[p][key] for p in platforms]
            return [sum(v[j] for v in vals) / len(vals) for j in (0, 1)] if i is None else None
        return [sum(R[p][key][j] * w for p, w in by_plat.items()) / views for j in (0, 1)]

    landing = clicks * A["landing_rate"]
    er = eng / views * 100 if views else None
    ctr = clicks / views * 100 if views else None
    freq = imps / reach if reach else None
    cpm = budget / views * 1000 if budget and views else None
    cpe = budget / eng if budget and eng else None
    cpc = budget / clicks if budget and clicks else None
    bands = {"cpm": wavg("cpm"), "cpe": wavg("cpe"), "cpc": wavg("cpc")}
    er_rng = [sum(R[p]["eng_range"][_lib_tier(t)][j] * 1.0 for p, t, f, o in posts) / len(posts) for j in (0, 1)] if posts else [0, 0]
    ctr_rng = [sum(R[p]["ctr_range"][j] * w for p, w in by_plat.items()) / views for j in (0, 1)] if views else [0, 0]
    g_cpm, g_cpe, g_cpc = _grade_cost(cpm, bands["cpm"]), _grade_cost(cpe, bands["cpe"]), _grade_cost(cpc, bands["cpc"])
    g_er, g_ctr = _grade_rate(er, er_rng), _grade_rate(ctr, ctr_rng)
    fg = A["frequency_good"]
    g_freq = None if freq is None else "good" if fg[0] <= freq <= fg[1] else "moderate" if freq <= fg[1] * 1.4 else "low"

    F = {
        "reach": {"label": "Reach", "value": reach, "unit": "", "sig": _sig(g_cpm)},
        "views": {"label": "Views", "value": views, "unit": "", "sig": _sig(g_cpm)},
        "impressions": {"label": "Impressions", "value": imps, "unit": "", "sig": _sig(g_cpm)},
        "frequency": {"label": "Frequency", "value": freq, "unit": "×", "sig": _sig(g_freq)},
        "cpm": {"label": "CPM", "value": cpm, "unit": "SAR", "sig": _sig(g_cpm)},
        "interactions": {"label": "Interactions", "value": eng, "unit": "", "sig": _sig(g_cpe or g_er)},
        "er": {"label": "Engagement rate", "value": er, "unit": "%", "sig": _sig(g_er)},
        "cpe": {"label": "CPE", "value": cpe, "unit": "SAR", "sig": _sig(g_cpe)},
        "clicks": {"label": "Clicks", "value": clicks, "unit": "", "sig": _sig(g_cpc or g_ctr)},
        "ctr": {"label": "CTR", "value": ctr, "unit": "%", "sig": _sig(g_ctr)},
        "landing": {"label": "Landing visits", "value": landing, "unit": "", "sig": _sig(g_cpc or g_ctr)},
        "cpc": {"label": "CPC", "value": cpc, "unit": "SAR", "sig": _sig(g_cpc)},
    }
    order = {"awareness": ["reach", "views", "impressions", "frequency", "cpm"],
             "engagement": ["interactions", "er", "cpe"],
             "traffic": ["clicks", "ctr", "landing", "cpc"]}[goal]
    figures = [dict(F[k], key=k, value=_r(k, F[k]["value"])) for k in order if F[k]["value"] is not None]
    cost_key = {"awareness": "cpm", "engagement": "cpe", "traffic": "cpc"}[goal]
    cost_val = {"cpm": cpm, "cpe": cpe, "cpc": cpc}[cost_key]
    band = bands[cost_key]
    grade = {"cpm": g_cpm, "cpe": g_cpe, "cpc": g_cpc}[cost_key] or {"awareness": g_freq, "engagement": g_er, "traffic": g_ctr}[goal]
    cost = None
    if cost_val is not None:
        good, acc = band[1], band[0]
        lo, hi = good * 0.5, acc * 1.15
        hi = max(hi, cost_val * 1.1)
        cost = {"key": cost_key, "label": cost_key.upper(), "value": _r(cost_key, cost_val), "fair": [_r(cost_key, good), _r(cost_key, acc)],
                "scale": [_r(cost_key, lo), _r(cost_key, hi)], "sig": _sig(grade if cost_val is not None else None)}
    split = None
    if goal == "engagement" and measured_split and likes + comments > 0:
        split = [{"label": "Likes", "value": int(round(likes))}, {"label": "Comments", "value": int(round(comments))}]
    return {
        "goal": goal, "goal_label": GOAL_LABEL[goal], "budget": int(round(budget)) if budget else None,
        "platforms": platforms, "market": market, "market_label": MARKETS[market],
        "creators": n_creators, "posts": len(posts), "skipped": skipped, "measured_posts": measured,
        "figures": figures, "cost": cost, "split": split,
        "verdict": _sig(grade) or {"grade": None, "label": "Add a budget"},
        "advice": advice(goal, grade, platforms, market, by_tier, views, n_creators),
        "sources": sources(platforms, house_posts, measured),
        "totals": {k: _r(k, v) for k, v in (("views", views), ("reach", reach), ("impressions", imps), ("engagement", eng),
                                              ("er", er), ("clicks", clicks), ("landing", landing), ("ctr", ctr)) if v is not None},
        "summary": "%s · %s · %s" % (GOAL_LABEL[goal], " and ".join(platforms),
                                     ("%d creator%s" % (n_creators, "" if n_creators == 1 else "s")) if n_creators else "no creators yet"),
        "estimate": True,
    }


def _r(key, v):
    if v is None:
        return None
    if key in ("er", "ctr"):
        return round(v, 2 if v < 1 else 1)
    if key == "frequency":
        return round(v, 1)
    if key in ("cpm", "cpc", "cpe"):
        return round(v, 2) if v < 10 else round(v, 1) if v < 100 else int(round(v))
    return plans._round(key, v) or 0


def advice(goal, grade, platforms, market, by_tier, views, n):
    """Helvy's one line: practical, never a price."""
    if not views:
        return "Add creators or a tier mix and I'll show what the budget can reach."
    big = (by_tier.get("macro", 0) + by_tier.get("mega", 0)) / views if views else 0
    small = (by_tier.get("micro", 0) + by_tier.get("nano", 0)) / views if views else 0
    if goal == "awareness":
        if grade in ("moderate", "low") and big > 0.6:
            return "Most of the reach rides on the biggest creators. Spreading the budget across more mid and micro creators usually brings the CPM down."
        if "TikTok" not in platforms and grade != "good":
            return "Adding TikTok usually lowers the cost per view in KSA; one post moved there is worth testing."
        return "Strong reach for this mix. Ask for Reels and TikToks rather than photos to keep the views up."
    if goal == "engagement":
        lead = "Micro creators do most of the work here. " if small > 0.4 else ""
        if market == "SA":
            return lead + "Arabic-first content usually lifts engagement in KSA, so ask for it in the brief."
        return lead + "Comments and saves come from content people can use: routines, how-tos and honest reviews."
    if "Snapchat" not in platforms:
        return "Clicks come from links people can tap. A swipe-up on Snapchat would add more, and every creator should put the link in the caption too."
    return "Ask every creator for the tracking link in the caption, not only in stories: stories alone lose most of the clicks."


def sources(platforms, house_posts, measured):
    out = ["Industry benchmarks by platform and creator size (Favikon, Qoruz, Metricool × HypeAuditor, Emplicit, Upgrowth, "
           "Kolsquare MENA 2026, IQFluence, Influencer Marketing Hub Saudi 2026)"]
    if measured:
        out.append("the creators' own measured averages for %d post%s" % (measured, "" if measured == 1 else "s"))
    if house_posts:
        out.append("blended with HelloVoice campaign results (%d tracked posts)" % house_posts)
    out.append("HelloVoice planning assumptions for impressions and landing visits")
    return out


# --------------------------------------------------------- selection input --

def creators_of(sel, which="approved", statuses=None):
    """A selection's creators with followers per platform and their own averages where measured.
    ``which``: approved (falls back to everyone not rejected when none is approved yet) or all."""
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
    out = []
    for code in codes:
        c = rows.get(code)
        if c is None:
            continue
        foll = {}
        for a in db.split_profiles(c["profiles"] or ""):
            if a.get("followers") and a.get("platform") in PLATFORMS:
                foll[a["platform"]] = int(a["followers"])
        if c["followers"] and c["platform"] in PLATFORMS and c["platform"] not in foll:
            foll[c["platform"]] = int(c["followers"])
        own = None
        for plat, got in (every.get(code) or {}).items():
            d = (got or {}).get("data") or {}
            v = d.get("avg_reel_plays") or d.get("avg_views")
            if plat in PLATFORMS and v:
                lk, cm = d.get("avg_likes"), d.get("avg_comments")
                own = {"platform": plat, "views": v, "likes": lk, "comments": cm,
                       "eng": ((lk or 0) + (cm or 0)) if (lk is not None or cm is not None) else None}
                if d.get("followers") and plat not in foll:
                    foll[plat] = int(d["followers"])
                break
        out.append({"code": code, "name": c["name"], "followers": foll, "own": own})
    return out


# ------------------------------------------------------------------ saving --

def save(code_id, sel_id, goal, inp, result, by=""):
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


def row_view(r):
    if r is None:
        return None
    return {"id": r["id"], "goal": r["goal"], "at": r["created_at"], "input": json.loads(r["input"] or "{}"),
            "result": json.loads(r["result"] or "{}")}


# ------------------------------------------------------ estimate vs actual --

def versus(k):
    """A campaign's saved estimate (kept with its selection, the last one saved before it started)
    against what the report measured. None when either side is missing."""
    if not k or not k["selection_id"] or k["status"] == "draft":
        return None
    saved = latest_for(k["selection_id"], before=k["starts_at"])
    if saved is None:
        return None
    est = (json.loads(saved["result"] or "{}").get("totals") or {})
    act = plans._measured(k)
    if not act or not act.get("posts"):
        return None
    rows = []
    for key, label in (("views", "Views"), ("reach", "Reach"), ("engagement", "Interactions"), ("er", "Engagement rate"),
                       ("clicks", "Tracking-link clicks")):
        e, a = est.get(key), act.get(key)
        if e is None or a is None or not e:
            continue
        if key == "clicks" and not a:
            continue                     # no tracking links on this campaign: nothing to compare
        if key == "er":
            delta = round(a - e, 1)
            grade = "good" if a >= e else "moderate" if a >= e - 0.7 else "low"
            text = "%+.1f pt" % delta
        else:
            ratio = a / float(e)
            delta = int(round((ratio - 1) * 100))
            grade = "good" if ratio >= 1 else "moderate" if ratio >= 0.85 else "low"
            text = "%+d%%" % delta
        rows.append({"key": key, "label": label, "estimate": e, "actual": a, "delta": text, "sig": _sig(grade)})
    if not rows:
        return None
    beat = [r["label"].lower() for r in rows if r["sig"]["grade"] == "good"]
    short = [r["label"].lower() for r in rows if r["sig"]["grade"] == "low"]
    line = ((beat[0][:1].upper() + beat[0][1:] + " beat the estimate. ") if beat else "") + \
           (("%s fell short: worth a look before the next campaign." % (short[0][:1].upper() + short[0][1:])) if short else
            ("Everything landed close to the estimate." if not beat else ""))
    return {"campaign": k["name"], "token": k["token"], "saved_at": saved["created_at"], "goal": saved["goal"],
            "ended": k["status"] == "ended", "ends_at": k["ends_at"], "rows": rows, "helvy": line.strip()}


# --------------------------------------------------------------- in the chat --

import re as _re

_AMOUNT = _re.compile(r"(?:sar|sr|riyals?|ريال)\s*(\d[\d,\.]*)\s*(k|m|thousand|million|ألف)?|(\d[\d,\.]*)\s*(k|m|thousand|million|ألف)?\s*(?:sar|sr|riyals?|ريال)", _re.I)
_ASK = _re.compile(r"\b(reach|budget|what can|how (many|much) (views|reach|people|clicks)|get me|buy|roi)\b|ميزانية|ميزانيتي", _re.I)


def from_text(text):
    """A typed "what can SAR 60,000 do on TikTok if we want clicks?" answered at once with a
    calculator card: free, no AI call. None when the message is not that question."""
    t = " ".join(str(text or "").split())
    m = _AMOUNT.search(t)
    if not m or not _ASK.search(t):
        return None
    num, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    try:
        v = float(num.replace(",", ""))
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
    mix = {"mid": 2, "micro": 6}
    res = estimate(goal, v, plats, "SA", mix=mix)
    return dict(res, mix=mix)
