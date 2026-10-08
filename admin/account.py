"""The client's own space: what /account/ shows and the few things a client
can change about themselves.

Only signed-in account holders have one. Access-code guests and the admin
preview get none: the portal menu does not offer it to them and every
endpoint here refuses them.

    summary(user, code_id)      the whole profile page in one call: profile, completion,
                                selections with their statuses, analyses, campaigns,
                                briefs, notifications, credits, invites and Helvy's next step
    save_image(user, kind, raw) the profile photo or company logo
    image_path(user, kind)      where it is, for serving it back to its owner
    completion(user)            profile completeness and the credits each step earns

Images live in admin/profile_media/, outside the public site and out of git.
They are only ever served through the API to the signed-in owner (or an
admin), never by a public URL.
"""
import json
import os
import secrets
from pathlib import Path

import db
import metrics
import portal
import uploads

MEDIA = Path(__file__).resolve().parent / "profile_media"
MAX_IMAGE = 2 * 1024 * 1024           # bytes, after base64 decoding
KINDS = ("photo", "logo")


def init():
    """Columns this module needs on users. Safe to run on every start."""
    MEDIA.mkdir(exist_ok=True)
    with db.connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        for col in ("photo", "logo", "notify"):
            if col not in cols:
                conn.execute("ALTER TABLE users ADD COLUMN %s TEXT" % col)


def _col(user, key):
    return user[key] if key in user.keys() else None


# ---------------------------------------------------------------- images --

def save_image(user, kind, raw):
    """Store a new photo or logo for this user, replacing the old file.
    Returns (ok, reason). Only real JPEG, PNG or WebP files are kept."""
    if kind not in KINDS:
        return False, "kind"
    if not raw:
        return False, "empty"
    if len(raw) > MAX_IMAGE:
        return False, "too_big"
    fmt = uploads.image_kind(raw[:16])
    if fmt not in ("jpg", "png", "webp"):
        return False, "not_image"
    MEDIA.mkdir(exist_ok=True)
    name = "%d-%s-%s.%s" % (user["id"], kind, secrets.token_hex(6), fmt)
    (MEDIA / name).write_bytes(raw)
    old = _col(user, kind)
    with db.connect() as conn:
        conn.execute("UPDATE users SET %s = ? WHERE id = ?" % kind, (name, user["id"]))
    _remove_file(old)
    return True, None


def remove_image(user, kind):
    if kind not in KINDS:
        return False
    old = _col(user, kind)
    with db.connect() as conn:
        conn.execute("UPDATE users SET %s = NULL WHERE id = ?" % kind, (user["id"],))
    _remove_file(old)
    return True


def _remove_file(name):
    if not name or "/" in name or ".." in name:
        return
    try:
        (MEDIA / name).unlink()
    except OSError:
        pass


def image_path(user, kind):
    """The file on disk for this user's photo or logo, or None."""
    name = _col(user, kind) if kind in KINDS else None
    if not name or "/" in name or ".." in name:
        return None
    p = MEDIA / name
    return p if p.is_file() else None


def image_version(user, kind):
    """A short tag that changes when the image does, for cache-busting."""
    name = _col(user, kind)
    return name.rsplit("-", 1)[-1].split(".")[0] if name else None


# ------------------------------------------------------------- completion --

def completion(user):
    """How complete the profile is, each step with the credits it earns."""
    import rewards
    return rewards.completion(user)


# ---------------------------------------------------------------- summary --

def _tiers_for(codes):
    if not codes:
        return {}
    out = {}
    with db.connect() as conn:
        rows = conn.execute("SELECT tier FROM creators WHERE code IN (%s)" % ",".join("?" * len(codes)), list(codes)).fetchall()
    for r in rows:
        t = r["tier"] or "Other"
        out[t] = out.get(t, 0) + 1
    return out


def _tier_map(codes):
    if not codes:
        return {}
    with db.connect() as conn:
        rows = conn.execute("SELECT code, tier FROM creators WHERE active = 1 AND code IN (%s)" % ",".join("?" * len(codes)),
                            list(codes)).fetchall()
    return {r["code"]: r["tier"] for r in rows}


def _next_month():
    import time
    t = time.gmtime()
    y, m = (t.tm_year + 1, 1) if t.tm_mon == 12 else (t.tm_year, t.tm_mon + 1)
    import calendar
    return calendar.timegm((y, m, 1, 0, 0, 0, 0, 0, 0))


def profile(user):
    u = {k: user[k] for k in ("email", "name", "company", "job_title", "phone", "created_at")}
    u["photo"] = image_version(user, "photo")
    u["logo"] = image_version(user, "logo")
    u["brands"] = _col(user, "brands") or ""
    u["industry"] = _col(user, "industry") or ""
    try:
        u["markets"] = json.loads(_col(user, "markets") or "[]")
    except ValueError:
        u["markets"] = []
    u["language"] = _col(user, "language") or ""
    return u


def _next_step(user, selections, analyses, comp, kam):
    """One thing to do next, for Helvy's line on Overview."""
    mine = [s for s in selections if s["mine"] and s["counts"]["review"] and s["creators"]]
    if mine:
        s = max(mine, key=lambda x: x["counts"]["review"])
        n = s["counts"]["review"]
        tail = (" %s quotes the approved list." % kam.split()[0]) if kam else " HelloVoice quotes the approved list."
        return {"kind": "review", "lead": "%d creator%s in " % (n, "" if n == 1 else "s"), "strong": s["name"],
                "tail": " %s waiting for your yes or no.%s" % ("is" if n == 1 else "are", tail),
                "cta": "Review %d creator%s" % (n, "" if n == 1 else "s"), "href": "selection/#s=" + s["token"]}
    ready = [a for a in analyses if a["state"] == "unlocked"]
    if ready:
        a = ready[0]
        return {"kind": "analysis", "lead": "The full analysis of ", "strong": a["name"], "tail": " is open.",
                "cta": "Open the analysis", "href": "creator/#c=" + a["code"]}
    if comp["missing"]:
        st = next(x for x in comp["steps"] if not x["done"])
        return {"kind": "profile", "lead": st["label"] + " and earn ", "strong": "+%d credits" % st["credits"],
                "tail": ". Helvy uses it to pre-fill your briefs.", "cta": "Finish my profile", "href": "account/#account"}
    return {"kind": "find", "lead": "Ready for the next campaign? Tell Helvy the brief and get a ", "strong": "scored shortlist",
            "tail": ".", "cta": "Find creators", "href": ""}


def summary(user, code_id, secret=b""):
    """Everything /account/ shows, in one payload. Client-safe: no costs,
    margins or internal notes ever leave here."""
    import gating
    import inbox
    import rewards
    import selstatus
    team = sorted(portal.team_codes(code_id))
    with db.connect() as conn:
        sels = conn.execute(
            "SELECT s.id, s.name, s.token, s.codes, s.updated_at, s.code_id, u.name owner FROM selections s "
            "LEFT JOIN users u ON u.code_id = s.code_id "
            "WHERE s.code_id IN (%s) AND s.archived_at IS NULL ORDER BY s.updated_at DESC LIMIT 60" % ",".join("?" * len(team)),
            team).fetchall()
        camps = conn.execute(
            "SELECT * FROM campaigns WHERE code_id IN (%s) AND status != 'draft' "
            "ORDER BY CASE status WHEN 'live' THEN 0 ELSE 1 END, starts_at DESC LIMIT 30" % ",".join("?" * len(team)),
            team).fetchall()

    every = set()
    for s in sels:
        every.update(json.loads(s["codes"] or "[]"))
    tiers = _tier_map(every)
    selections, shortlisted = [], set()
    for s in sels:
        codes = [c for c in json.loads(s["codes"] or "[]") if c in tiers]
        if s["code_id"] == code_id:
            shortlisted.update(codes)
        st = selstatus.of(s["id"])
        selections.append({"name": s["name"], "token": s["token"], "creators": len(codes), "updated_at": s["updated_at"],
                           "mine": s["code_id"] == code_id, "owner": None if s["code_id"] == code_id else (s["owner"] or "A colleague"),
                           "counts": selstatus.counts(codes, st, tiers)})

    campaigns, grades = [], []
    agg = {"exposure": 0, "reach": 0, "views": 0, "delivered": 0, "planned": 0}
    for k in camps:
        try:
            rep = metrics.report(k)
        except Exception:
            rep = None
        t = rep["total"] if rep else {}
        v = rep["verdict"] if rep else {"label": "Getting started", "grade": None}
        row = {"token": k["token"], "name": k["name"], "status": k["status"],
               "starts_at": k["starts_at"], "ends_at": k["ends_at"],
               "verdict": {"label": v.get("label"), "grade": v.get("grade")},
               "exposure": t.get("exposure") or 0, "reach": t.get("reach") or 0, "views": t.get("views") or 0,
               "er": t.get("er"), "er_grade": t.get("er_grade"),
               "delivered": t.get("delivered") or 0, "planned": t.get("planned") or 0,
               "updated_at": rep["updated_at"] if rep else None}
        campaigns.append(row)
        if k["status"] == "live":
            for key in ("exposure", "reach", "views", "delivered", "planned"):
                agg[key] += row[key] or 0
            if row["er_grade"]:
                grades.append(row["er_grade"])

    live = [c for c in campaigns if c["status"] == "live"]
    er_vals = [c["er"] for c in live if c["er"] is not None]
    insights = {
        "live_campaigns": len(live),
        "exposure": agg["exposure"], "reach": agg["reach"], "views": agg["views"],
        "er": (sum(er_vals) / len(er_vals)) if er_vals else None,
        "er_grade": metrics._avg_grade(grades),
        "delivered": agg["delivered"], "planned": agg["planned"],
        "shortlisted": len(shortlisted), "tiers": _tiers_for(shortlisted),
    }
    comp = completion(user)
    analyses = gating.for_client(code_id)
    kam = _col(user, "kam") or None
    briefs = []
    for b in portal.briefs_for(code_id, 30):
        sel = db.selection(b["selection_id"]) if b["selection_id"] else None
        briefs.append({"id": b["id"], "summary": b["summary"], "objective": b["objective"], "source": b["source"],
                       "at": b["created_at"], "selection": sel["token"] if sel else None, "selection_name": sel["name"] if sel else None})
    return {"user": profile(user), "completion": comp, "credits": portal.balance(code_id),
            "monthly_credits": portal.monthly_allowance(user), "next_refill": _next_month(),
            "costs": portal.costs(), "kam": kam,
            "insights": insights, "campaigns": campaigns, "selections": selections,
            "analyses": analyses, "briefs": briefs,
            "notifications": {"items": inbox.feed(user, 60, bell=False), "unread": inbox.unread(user),
                              "prefs": inbox.prefs(user), "counts": inbox.counts(user)},
            "ledger": [{"delta": r["delta"], "reason": r["reason"], "at": r["at"], "balance": r["balance_after"]}
                       for r in portal.ledger(code_id, 60)],
            "invite": rewards.summary(user, secret),
            "next": _next_step(user, selections, analyses, comp, kam),
            "markets": [{"value": v, "label": l} for v, l in _market_options()],
            "industries": [{"value": v, "label": l} for v, l in _industry_options()],
            "languages": list(portal.LANGUAGES),
            "team": [{"name": t["name"], "job_title": t["job_title"]} for t in portal.teammates(code_id)]}


def _market_options():
    import matcher
    return matcher._BY_ID["market"]["options"]


def _industry_options():
    import matcher
    return matcher._BY_ID["category"]["options"]
