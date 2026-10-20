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
    fulfil(request_id, who)     approve: unlock for the person who asked and ring their bell
    decide(request_id, ok, ...) the admin inbox's Approve / Reject (item 195)
    inbox(role, scope)          open and recent requests, grouped client -> campaign / selection
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
        # Item 195 (owner, 2026-10-20): an admin's Approve opens the analysis to THAT person only.
        # personal = 1 marks those grants; they open even while CLIENTS_SEE_ANALYSIS is off.
        gcols = {r[1] for r in conn.execute("PRAGMA table_info(analysis_grants)")}
        if "personal" not in gcols:
            conn.execute("ALTER TABLE analysis_grants ADD COLUMN personal INTEGER")
        rcols = {r[1] for r in conn.execute("PRAGMA table_info(analysis_requests)")}
        for col in ("outcome", "handled_by", "note"):
            if col not in rcols:
                conn.execute("ALTER TABLE analysis_requests ADD COLUMN " + col + " TEXT")
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


def _unlock_all():
    """A person with admin access who switched "Show locked data" on (this request only)."""
    import portal
    return portal.unlock_all()


def published_codes(code_id):
    """Creators in this team's selections whose profile analysis HelloVoice pushed (owner, 2026-10-15):
    every creator of such a selection, including ones added after the push."""
    team = _team(code_id)
    if not team:
        return set()
    with db.connect() as conn:
        rows = conn.execute("SELECT codes FROM selections WHERE analysis_published = 1 AND deleted_at IS NULL AND code_id IN (%s)"
                            % ",".join("?" * len(team)), list(team)).fetchall()
    out = set()
    for r in rows:
        out.update(json.loads(r["codes"] or "[]"))
    return out


# Owner, 2026-10-20 (item 174): clients and key account managers never see a creator's full profile analysis,
# granted or published. Grants and publish flags are kept in the database untouched; set True to bring them back.
CLIENTS_SEE_ANALYSIS = False


def _personal(code_id, code=None):
    """Creators an admin opened to this one person from the inbox (item 195)."""
    with db.connect() as conn:
        if code is not None:
            return bool(conn.execute("SELECT 1 FROM analysis_grants WHERE code_id = ? AND code = ? AND personal = 1 LIMIT 1",
                                     (int(code_id), code)).fetchone())
        return {r[0] for r in conn.execute("SELECT code FROM analysis_grants WHERE code_id = ? AND personal = 1", (int(code_id),))}


def unlocked(code_id, code):
    if code_id is None:
        return False
    if code_id == db.admin_code_id() or _unlock_all():
        return True
    if _personal(code_id, code):
        return True                                    # approved for this person from the admin inbox
    if not CLIENTS_SEE_ANALYSIS:
        return False
    # A key account manager's scope never unlocks an analysis (owner, 2026-10-20, item 174).
    if code in published_codes(code_id):
        return True                                    # pushed on one of the team's selections
    team = _team(code_id)
    with db.connect() as conn:
        return bool(conn.execute("SELECT 1 FROM analysis_grants WHERE code = ? AND code_id IN (%s) LIMIT 1"
                                 % ",".join("?" * len(team)), [code] + list(team)).fetchone())


def unlocked_set(code_id, codes=None):
    """The creators this viewer may see in full (None = all, for the admin preview)."""
    if code_id is None:
        return set()
    if code_id == db.admin_code_id() or _unlock_all():
        return None
    mine = _personal(code_id)
    if not CLIENTS_SEE_ANALYSIS:
        return mine if codes is None else mine & set(codes)
    team = _team(code_id)
    with db.connect() as conn:
        rows = conn.execute("SELECT code FROM analysis_grants WHERE code_id IN (%s)" % ",".join("?" * len(team)), list(team)).fetchall()
    got = {r["code"] for r in rows} | published_codes(code_id) | mine
    return got if codes is None else got & set(codes)


def selections_with(code_id, code, own_only=False):
    if own_only and code_id is not None:
        import codelinks
        team = {code_id} | codelinks.linked_for({code_id})
    else:
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
    if not selections_with(code_id, code, own_only=True):
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
    """Approve a request (item 195): open the creator's analysis to the person who asked (a personal grant),
    close their open requests for that creator, and ring their bell. Returns the request row or None. Pass
    ``conn`` to do it inside a transaction that is already open."""
    if conn is None:
        with db.connect() as own:
            return fulfil(request_id, who, own)
    r = conn.execute("SELECT * FROM analysis_requests WHERE id = ?", (request_id,)).fetchone()
    if r is None or r["code_id"] is None:
        return None
    conn.execute("INSERT INTO analysis_grants (code_id, code, granted_at, granted_by, request_id, personal) VALUES (?,?,?,?,?,1) "
                 "ON CONFLICT(code_id, code) DO UPDATE SET personal = 1, granted_at = excluded.granted_at, "
                 "granted_by = excluded.granted_by, request_id = excluded.request_id",
                 (r["code_id"], r["code"], db.now(), who, r["id"]))
    conn.execute("UPDATE analysis_requests SET handled_at = ?, outcome = 'approved', handled_by = ? "
                 "WHERE code = ? AND handled_at IS NULL AND code_id = ?", (db.now(), who, r["code"], r["code_id"]))
    _ring(conn, r["code_id"], r["code"])
    return r


def decide(request_id, ok, who="", note=""):
    """(ok, message): the inbox's Approve / Reject. Approve needs an analysis on file to open."""
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM analysis_requests WHERE id = ?", (int(request_id),)).fetchone()
        if r is None or r["code_id"] is None:
            return False, "That request is not here any more."
        c = conn.execute("SELECT name FROM creators WHERE code = ?", (r["code"],)).fetchone()
        name = (c["name"] if c else r["code"]) or r["code"]
        if r["handled_at"] is not None:
            return False, "That request was already answered."
        if ok:
            if not has_analysis(r["code"]):
                return False, "Upload %s's analysis first, then approve." % name
            fulfil(r["id"], who, conn)
            return True, "Approved: %s's analysis is open to them now." % name
        note = " ".join(str(note or "").split())[:300]
        conn.execute("UPDATE analysis_requests SET handled_at = ?, outcome = 'rejected', handled_by = ?, note = ? "
                     "WHERE code = ? AND handled_at IS NULL AND code_id = ?", (db.now(), who, note or None, r["code"], r["code_id"]))
        import inbox
        u = conn.execute("SELECT id, status FROM users WHERE code_id = ?", (r["code_id"],)).fetchone()
        if u is not None and u["status"] == "active":
            inbox.emit([u["id"]], "analysis_reply", "Your account manager replied about", rest=" " + name,
                       body=note or "The full analysis isn't available for this creator. Your account manager will be in touch.",
                       href="creator/#c=" + r["code"], ref="analysis-no:%d" % r["id"], once=True, conn=conn)
        return True, "Rejected. They have been told."


def inbox(scope=None, days=30):
    """The admin Analyses tab (item 195): open requests and the last ``days`` of answers.
    ``scope`` None = every client (admins); else a KAM's client code ids (with .sel_ids)."""
    since = db.now() - days * 86400
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT a.*, r.name creator_name, r.photo, u.name user_name, u.email user_email, u.company, c.label code_label "
            "FROM analysis_requests a LEFT JOIN creators r ON r.code = a.code LEFT JOIN users u ON u.code_id = a.code_id "
            "LEFT JOIN codes c ON c.id = a.code_id WHERE a.code_id IS NOT NULL AND (a.handled_at IS NULL OR a.handled_at >= ?) "
            "ORDER BY a.at DESC LIMIT 400", (since,)).fetchall()
        have = {x["code"] for x in conn.execute("SELECT DISTINCT code FROM creator_analysis")}
    import board
    out = []
    for r in rows:
        if scope is not None and int(r["code_id"]) not in scope:
            continue
        sels = selections_with(r["code_id"], r["code"])
        camps = []
        for s in sels:
            sel = db.selection(token=s["token"])
            for cid in (board.campaigns_holding(sel["id"]) if sel is not None else []):
                k = db.campaign(cid)
                if k is not None and not any(x["token"] == k["token"] for x in camps):
                    camps.append({"name": k["name"], "token": k["token"], "status": k["status"]})
        state = "open" if r["handled_at"] is None else (r["outcome"] or "approved")
        if r["handled_by"] == "upload" or (r["handled_at"] is not None and not r["outcome"]):
            state = "closed"
        out.append({"id": r["id"], "code": r["code"], "creator": r["creator_name"] or r["code"], "photo": bool(r["photo"]),
                    "platform": r["platform"] or "", "at": r["at"], "ready_by": ready_by(r["at"]),
                    "client": r["company"] or r["code_label"] or "Unfiled", "user": r["user_name"] or r["user_email"] or r["code_label"] or "",
                    "state": state, "handled_at": r["handled_at"], "handled_by": r["handled_by"] or "", "note": r["note"] or "",
                    "has_analysis": r["code"] in have, "selections": sels[:3], "campaigns": camps[:3]})
    return out


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
    """An analysis uploaded for a creator used to answer that creator's open requests by itself. Since item 195
    an admin approves each one from the inbox, so while clients don't see analyses by default the requests
    stay open (with the analysis now on file, ready to approve)."""
    if not CLIENTS_SEE_ANALYSIS:
        return
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
        reqs = conn.execute("SELECT a.code, a.at, a.handled_at, a.outcome, a.note, a.code_id, r.name, r.photo FROM analysis_requests a "
                            "LEFT JOIN creators r ON r.code = a.code WHERE a.code_id IN (%s) ORDER BY a.at DESC" % ph, list(team)).fetchall()
        gr = conn.execute("SELECT g.code, g.granted_at, r.name FROM analysis_grants g LEFT JOIN creators r ON r.code = g.code "
                          "WHERE g.code_id IN (%s) ORDER BY g.granted_at DESC" % ph, list(team)).fetchall()
    out, seen = [], set()
    if not CLIENTS_SEE_ANALYSIS:
        # only what an admin approved for this person opens (item 195); old team grants stay closed
        mine = _personal(code_id)
        gr = [g for g in gr if g["code"] in mine]
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
        elif r["outcome"] == "rejected" and r["code_id"] == code_id:
            seen.add(r["code"])
            out.append({"code": r["code"], "name": r["name"] or r["code"], "state": "declined", "at": r["handled_at"], "note": r["note"] or ""})
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
    if "metrics" in sc:
        out["metrics"] = [m for m in (sc.get("metrics") or [])
                          if not _locked_text(m.get("label")) and not _locked_text(m.get("value"))]
    out["strengths"] = [x for x in (sc.get("strengths") or []) if not _locked_text(x)]
    out["watchouts"] = [x for x in (sc.get("watchouts") or []) if not _locked_text(x)]
    if "conclusion" in sc:
        out["conclusion"] = "%s (%s/100)." % (sc.get("tag") or "Score", sc.get("score")) if sc.get("score") is not None else ""
    if isinstance(sc.get("platforms"), dict):
        out["platforms"] = {k: redact_score(v) for k, v in sc["platforms"].items()}
    out["locked"] = True
    return out
