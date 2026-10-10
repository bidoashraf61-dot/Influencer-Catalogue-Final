"""Who may see a creator's full analysis, and what everyone else gets instead.

Free layer (real numbers, always): followers, platforms, average views and
engagement rate. Everything else in an analysis (popular posts, followers and
fake followers, growth, content performance, brand affinity, audience data,
hashtags, the PDF) is locked until
HelloVoice fulfils a request for that client. A locked page is drawn from SAMPLE
data made here, so the real values never reach a browser that has not been given
them.

    unlocked(code_id, code)     True for the admin preview and for a granted team
    state(code_id, code)        unlocked | requested | locked | outside
    selections_with(code_id, code)   the client's selections holding the creator
    request(code_id, code, platform) the client asks (only from inside a selection)
    fulfil(request_id, who)     unlock for that client and ring their bell
    headline(card, analyses)    the free layer
    sample(code, platform)      the stand-in analysis the locked sections are drawn from
    redact_score(score)         strip locked evidence out of a fit score

Requests are free and unlimited: every one is a lead for the account manager.
"""
import hashlib
import json
import random
import time

import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_grants (
    id INTEGER PRIMARY KEY,
    code_id INTEGER NOT NULL,          -- the client's access-code row (their team sees it too)
    code TEXT NOT NULL,                -- creators.code
    granted_at INTEGER NOT NULL,
    granted_by TEXT,
    request_id INTEGER,
    UNIQUE (code_id, code)
);
"""

WORK_DAYS = 1                      # the promise: ready within 1 working day (client-approved 2026-10-09)
WEEKEND = (4, 5)                   # Friday, Saturday (KSA); time.gmtime().tm_wday, Monday = 0


def init():
    """The grants table, plus a grant for every request the team already answered
    before gating existed, so nobody loses an analysis they were sent."""
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        if not db.setting("gating_migrated", False):
            conn.execute("INSERT OR IGNORE INTO analysis_grants (code_id, code, granted_at, granted_by, request_id) "
                         "SELECT code_id, code, COALESCE(handled_at, at), 'before gating', id FROM analysis_requests "
                         "WHERE handled_at IS NOT NULL AND code_id IS NOT NULL")
    if not db.setting("gating_migrated", False):
        db.set_setting("gating_migrated", True)
    db.on("analysis_saved", _answered_by_upload)


def ready_by(ts):
    """WORK_DAYS working days after ``ts`` (Friday and Saturday do not count)."""
    t, left = int(ts), WORK_DAYS
    while left:
        t += 86400
        if time.gmtime(t).tm_wday not in WEEKEND:
            left -= 1
    return t


# ------------------------------------------------------------------ access --

def _team(code_id):
    import portal
    return portal.team_codes(code_id) if code_id is not None else set()


def unlocked(code_id, code):
    if code_id is None:
        return False
    if code_id == db.admin_code_id():
        return True
    team = _team(code_id)
    with db.connect() as conn:
        return bool(conn.execute("SELECT 1 FROM analysis_grants WHERE code = ? AND code_id IN (%s) LIMIT 1"
                                 % ",".join("?" * len(team)), [code] + list(team)).fetchone())


def unlocked_set(code_id, codes=None):
    """The creators this viewer may see in full (None = all, for the admin preview)."""
    if code_id is None:
        return set()
    if code_id == db.admin_code_id():
        return None
    team = _team(code_id)
    with db.connect() as conn:
        rows = conn.execute("SELECT code FROM analysis_grants WHERE code_id IN (%s)" % ",".join("?" * len(team)), list(team)).fetchall()
    got = {r["code"] for r in rows}
    return got if codes is None else got & set(codes)


def selections_with(code_id, code):
    team = _team(code_id)
    if not team:
        return []
    with db.connect() as conn:
        rows = conn.execute("SELECT name, token, codes FROM selections WHERE archived_at IS NULL AND code_id IN (%s) "
                            "ORDER BY updated_at DESC" % ",".join("?" * len(team)), list(team)).fetchall()
    return [{"name": r["name"], "token": r["token"]} for r in rows if code in json.loads(r["codes"] or "[]")]


def open_request(code_id, code):
    team = _team(code_id)
    if not team:
        return None
    with db.connect() as conn:
        return conn.execute("SELECT * FROM analysis_requests WHERE code = ? AND handled_at IS NULL AND code_id IN (%s) "
                            "ORDER BY at LIMIT 1" % ",".join("?" * len(team)), [code] + list(team)).fetchone()


def grant_row(code_id, code):
    team = _team(code_id)
    if not team:
        return None
    with db.connect() as conn:
        return conn.execute("SELECT * FROM analysis_grants WHERE code = ? AND code_id IN (%s) ORDER BY granted_at LIMIT 1"
                            % ",".join("?" * len(team)), [code] + list(team)).fetchone()


def state(code_id, code):
    """What this viewer's analysis button says, with the dates it needs."""
    if unlocked(code_id, code):
        g = grant_row(code_id, code)
        return {"state": "unlocked", "granted_at": g["granted_at"] if g else None}
    sels = selections_with(code_id, code)
    r = open_request(code_id, code)
    if r is not None:
        return {"state": "requested", "requested_at": r["at"], "ready_by": ready_by(r["at"]), "selections": sels}
    return {"state": "locked" if sels else "outside", "selections": sels}


def request(code_id, code, platform=None):
    """(ok, reason). Only for a creator inside one of the client's own selections."""
    if code_id == db.admin_code_id():
        return False, "admin"
    if unlocked(code_id, code):
        return False, "unlocked"
    if not selections_with(code_id, code):
        return False, "outside"
    if open_request(code_id, code) is not None:
        return True, "already"
    db.request_analysis(code, code_id, platform)
    return True, None


# ------------------------------------------------------------------ fulfil --

def has_analysis(code):
    with db.connect() as conn:
        return bool(conn.execute("SELECT 1 FROM creator_analysis WHERE code = ? LIMIT 1", (code,)).fetchone())


def fulfil(request_id, who="", conn=None):
    """Unlock a request's creator for that client, close every open request the team
    has for that creator, and ring the bell. Returns the request row or None. Pass
    ``conn`` to do it inside a transaction that is already open."""
    if conn is None:
        with db.connect() as own:
            return fulfil(request_id, who, own)
    r = conn.execute("SELECT * FROM analysis_requests WHERE id = ?", (request_id,)).fetchone()
    if r is None or r["code_id"] is None:
        return None
    team = _team(r["code_id"])
    conn.execute("INSERT OR IGNORE INTO analysis_grants (code_id, code, granted_at, granted_by, request_id) VALUES (?,?,?,?,?)",
                 (r["code_id"], r["code"], db.now(), who, r["id"]))
    conn.execute("UPDATE analysis_requests SET handled_at = ? WHERE code = ? AND handled_at IS NULL AND code_id IN (%s)"
                 % ",".join("?" * len(team)), [db.now(), r["code"]] + list(team))
    _ring(conn, r["code_id"], r["code"])
    return r


def _ring(conn, code_id, code):
    import inbox
    c = conn.execute("SELECT name FROM creators WHERE code = ?", (code,)).fetchone()
    name = (c["name"] if c else code) or code
    u = conn.execute("SELECT id, status FROM users WHERE code_id = ?", (code_id,)).fetchone()
    users = [u["id"]] if u is not None and u["status"] == "active" else []
    inbox.emit(users, "analysis_ready", "Full analysis ready:", rest=" " + name,
               body="Audience, followers, content and brand affinity are open",
               href="creator/#c=" + code, ref="analysis:" + code, once=True, conn=conn)


def _answered_by_upload(conn, code, platform):
    """An analysis uploaded for a creator answers that creator's open requests:
    each client who asked gets it unlocked and a bell."""
    rows = conn.execute("SELECT id FROM analysis_requests WHERE code = ? AND handled_at IS NULL "
                        "AND (platform IS NULL OR platform = ?)", (code, platform)).fetchall()
    for r in rows:
        fulfil(r["id"], "upload", conn)


def queue():
    """Open requests for the admin, oldest first, with what the team needs to act."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT a.*, r.name creator_name, c.label code_label, u.company, u.name user_name, u.kam "
            "FROM analysis_requests a LEFT JOIN creators r ON r.code = a.code LEFT JOIN codes c ON c.id = a.code_id "
            "LEFT JOIN users u ON u.code_id = a.code_id WHERE a.handled_at IS NULL ORDER BY a.at").fetchall()
        have = {x["code"] for x in conn.execute("SELECT DISTINCT code FROM creator_analysis")}
    return [dict(r, has_analysis=r["code"] in have, ready_by=ready_by(r["at"])) for r in rows]


def grants(limit=60):
    with db.connect() as conn:
        return conn.execute(
            "SELECT g.*, r.name creator_name, c.label code_label, u.company FROM analysis_grants g "
            "LEFT JOIN creators r ON r.code = g.code LEFT JOIN codes c ON c.id = g.code_id "
            "LEFT JOIN users u ON u.code_id = g.code_id ORDER BY g.granted_at DESC LIMIT ?", (limit,)).fetchall()


def for_client(code_id):
    """The client's Analyses tab: everything requested or unlocked for their team."""
    team = _team(code_id)
    if not team:
        return []
    ph = ",".join("?" * len(team))
    with db.connect() as conn:
        reqs = conn.execute("SELECT a.code, a.at, a.handled_at, r.name, r.photo FROM analysis_requests a "
                            "LEFT JOIN creators r ON r.code = a.code WHERE a.code_id IN (%s) ORDER BY a.at DESC" % ph, list(team)).fetchall()
        gr = conn.execute("SELECT g.code, g.granted_at, r.name FROM analysis_grants g LEFT JOIN creators r ON r.code = g.code "
                          "WHERE g.code_id IN (%s) ORDER BY g.granted_at DESC" % ph, list(team)).fetchall()
    out, seen = [], set()
    for g in gr:
        if g["code"] in seen:
            continue
        seen.add(g["code"])
        out.append({"code": g["code"], "name": g["name"] or g["code"], "state": "unlocked", "at": g["granted_at"]})
    for r in reqs:
        if r["code"] in seen:
            continue
        seen.add(r["code"])
        if r["handled_at"] is None:
            out.append({"code": r["code"], "name": r["name"] or r["code"], "state": "requested", "at": r["at"],
                        "ready_by": ready_by(r["at"])})
    return out


# -------------------------------------------------------------- free layer --

def headline(card, analyses):
    """Followers, platforms, average views and engagement: real, for everyone."""
    profiles = card.get("profiles") or []
    followers = sum(int(p.get("followers") or 0) for p in profiles if isinstance(p, dict)) or card.get("followers") or 0
    plats = []
    for p in profiles:
        if isinstance(p, dict) and p.get("platform") and p["platform"] not in plats:
            plats.append(p["platform"])
    main, doc = None, None
    for pl, a in (analyses or {}).items():
        d = a["data"] if isinstance(a, dict) and "data" in a else a
        if doc is None or (doc.get("basic") and not d.get("basic")):
            main, doc = pl, d
    doc = doc or {}
    views = doc.get("avg_views") or doc.get("avg_reel_plays")
    return {"followers": followers, "platforms": plats or ([main] if main else []),
            "avg_views": int(views) if isinstance(views, (int, float)) else None,
            "er": round(float(doc["er"]), 2) if isinstance(doc.get("er"), (int, float)) else None,
            "er_platform": main, "er_followers": doc.get("followers") or followers,
            "updated": doc.get("updated")}


# ----------------------------------------------------------- locked sample --

_S_COUNTRIES = ["SA", "AE", "EG", "KW", "QA"]
_S_CITIES = ["Riyadh", "Jeddah", "Dammam", "Dubai", "Cairo"]
_S_LANGS = ["Arabic", "English", "French"]
_S_INTERESTS = ["Beauty & Cosmetics", "Clothes, Shoes & Accessories", "Friends, Family & Relationships",
                "Restaurants, Food & Grocery", "Travel, Tourism & Aviation", "Health & Wellness", "Fitness & Yoga"]
_S_AGES = ["13-17", "18-24", "25-34", "35-44", "45-64"]
_S_BUCKETS = ["0-5%", "5-10%", "10-15%", "15-20%", "20-25%", "25-30%", "30-35%", "35%+"]


def _shares(rnd, labels, lo, hi, key="name", total=100.0):
    """Made-up shares for ``labels``, largest first, summing to under ``total``."""
    raw = sorted((rnd.uniform(lo, hi) for _ in labels), reverse=True)
    scale = total / (sum(raw) * rnd.uniform(1.05, 1.35))
    return [{key: lab, "pct": round(v * scale, 2)} for lab, v in zip(labels, raw)]


def _dist(rnd):
    peak = rnd.randint(1, 3)
    h = [round(max(4.0, 100 - abs(i - peak) * rnd.uniform(18, 30)), 1) for i in range(len(_S_BUCKETS))]
    me = min(len(h) - 1, peak + rnd.choice([-1, 0, 1, 2]))
    return {"buckets": [{"label": lab, "h": v} for lab, v in zip(_S_BUCKETS, h)], "creator": me,
            "median": peak if peak != me else None}


def sample(code, platform=None):
    """Stand-in data for the locked sections: a whole analysis in the same shape
    as an uploaded one (so the locked page draws the real sections, cards and
    tabs), the same for a creator every time, and made from nothing but the code:
    no figure in it is read from the creator's record or analysis.

    Returned as ``{"sample": True, "analysis": {...}}``."""
    rnd = random.Random(int(hashlib.sha256(("sample:" + str(code)).encode()).hexdigest()[:12], 16))
    followers = rnd.randint(24, 480) * 1000
    er = round(rnd.uniform(1.2, 4.8), 2)
    likes = int(followers * er / 100 * 0.96)
    comments = max(3, int(likes * rnd.uniform(0.015, 0.04)))
    views = int(followers * rnd.uniform(0.25, 0.9))
    women = round(rnd.uniform(38, 78), 2)
    t = time.gmtime()
    months = []
    for back in range(11, -1, -1):
        y, m = t.tm_year, t.tm_mon - back
        while m <= 0:
            y, m = y - 1, m + 12
        months.append("%04d-%02d" % (y, m))
    f0, l0, growth = followers * rnd.uniform(0.78, 0.94), likes * rnd.uniform(0.8, 1.1), []
    for i, mo in enumerate(months):
        growth.append({"month": mo, "followers": int(f0 + (followers - f0) * i / 11.0 * rnd.uniform(0.9, 1.1)),
                       "avg_likes": int(l0 * rnd.uniform(0.85, 1.2))})
    growth[-1]["followers"] = followers

    def audience():
        ages = _shares(rnd, _S_AGES, 4, 40)
        ages.sort(key=lambda x: _S_AGES.index(x["name"]))
        fem = [{"name": a["name"], "pct": round(a["pct"] * women / 100.0, 2)} for a in ages]
        mal = [{"name": a["name"], "pct": round(a["pct"] - f["pct"], 2)} for a, f in zip(ages, fem)]
        return {"countries": _shares(rnd, _S_COUNTRIES, 3, 60, key="code"),
                "cities": _shares(rnd, _S_CITIES, 2, 30, total=70.0),
                "gender": {"female": women, "male": round(100 - women, 2)},
                "ages": ages, "ages_female": fem, "ages_male": mal,
                "languages": _shares(rnd, _S_LANGS, 4, 70),
                "interests": _shares(rnd, _S_INTERESTS, 10, 40),
                "brand_affinity": _shares(rnd, ["Brand %s" % ch for ch in "ABCDEF"], 2, 12, total=40.0),
                "reachability": [{"name": n, "pct": v["pct"]} for n, v in
                                 zip(["<500", "500-1000", "1000-1500", ">1500"], _shares(rnd, range(4), 5, 50))]}

    def post(i, brand=None):
        p = {"url": "#", "thumb": None, "date": "%s-%02d" % (months[-1 - (i % 3)], rnd.randint(1, 28)),
             "likes": int(likes * rnd.uniform(1.5, 4)), "comments": int(comments * rnd.uniform(1.2, 3)),
             "views": int(views * rnd.uniform(1.5, 5))}
        if brand:
            p["brand"] = brand
        return p
    reel_likes = int(likes * rnd.uniform(1.1, 1.8))
    return {"sample": True, "analysis": {
        "sample": True, "platform": platform or "Instagram", "account_type": "Creator",
        "followers": followers, "followers_change_pct": round(rnd.uniform(-1.5, 4.5), 2),
        "avg_likes": likes, "avg_likes_change_pct": round(rnd.uniform(-6, 9), 2), "avg_comments": comments,
        "avg_views": views, "er": er, "est_impressions": int(followers * rnd.uniform(0.3, 0.6)),
        "est_reach": int(followers * rnd.uniform(0.15, 0.35)),
        "avg_reel_plays": int(views * rnd.uniform(1.2, 2.2)), "avg_reel_likes": reel_likes,
        "avg_reel_comments": int(comments * rnd.uniform(1.1, 1.6)), "avg_reel_shares": int(reel_likes * rnd.uniform(0.02, 0.08)),
        "reels_er": round(er * rnd.uniform(1.0, 1.5), 2),
        "story_reach": int(followers * rnd.uniform(0.04, 0.1)), "story_impressions": int(followers * rnd.uniform(0.05, 0.13)),
        "paid_post_performance": round(rnd.uniform(40, 120), 2), "paid_views_pct": round(rnd.uniform(30, 110), 2),
        "fake_followers_pct": round(rnd.uniform(4, 22), 2), "fake_likers_pct": round(rnd.uniform(3, 18), 2),
        "fake_followers_dist": _dist(rnd), "er_dist": _dist(rnd),
        "audience": audience(), "audience_likers": audience(), "growth": growth,
        "top_posts": [post(i) for i in range(6)],
        "sponsored_posts": [post(i, "Brand %s" % "ABC"[i]) for i in range(3)],
        "brands": [{"name": "Brand %s" % ch, "count": rnd.randint(1, 9)} for ch in "ABCDEF"],
        "creator_interests": rnd.sample(_S_INTERESTS, 4),
        "hashtags": [{"tag": "#topic%d" % i, "count": round(rnd.uniform(3, 30), 2)} for i in range(1, 7)]
                    + [{"tag": "@brand%s" % ch, "count": round(rnd.uniform(2, 20), 2)} for ch in "abcde"],
    }}


# ------------------------------------------------------------ fit scores --

# Evidence drawn from the locked part of an analysis. "works in the … space" is the measured
# niche line (fit.score_core reads it off the audience and creator interests of a full analysis).
_LOCKED_WORDS = ("audience", "fake", "real follower", "real people", "aged", "women", "men ", "credib",
                 "works in the", "brand affinity", "interest")


def _locked_text(t):
    t = str(t or "").lower()
    return any(w in t for w in _LOCKED_WORDS)


def _locked_part(p):
    """A score part measured from the locked analysis ("Audience (measured)"); the assumed
    audience part says nothing about the creator and stays."""
    lab = str((p or {}).get("label") or "").lower()
    return "measured" in lab or (_locked_text(lab) and "assumed" not in lab)


def redact_score(sc):
    """A fit score with the locked evidence taken out (audience shares, fake followers, the
    measured audience part and its strengths and watch-outs): the number and its stamp stay,
    the evidence waits for the full analysis. Engagement, reach and views are free."""
    if not isinstance(sc, dict):
        return sc
    out = dict(sc)
    out["checks"] = [c for c in (sc.get("checks") or [])
                     if not _locked_text(c.get("label")) and not _locked_text(c.get("text"))]
    if "parts" in sc:
        out["parts"] = [p for p in (sc.get("parts") or []) if not _locked_part(p)]
    out["strengths"] = [x for x in (sc.get("strengths") or []) if not _locked_text(x)]
    out["watchouts"] = [x for x in (sc.get("watchouts") or []) if not _locked_text(x)]
    if "conclusion" in sc:
        out["conclusion"] = "%s (%s/100)." % (sc.get("tag") or "Score", sc.get("score")) if sc.get("score") is not None else ""
    if isinstance(sc.get("platforms"), dict):
        out["platforms"] = {k: redact_score(v) for k, v in sc["platforms"].items()}
    out["locked"] = True
    return out
