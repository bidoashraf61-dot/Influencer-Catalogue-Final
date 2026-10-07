"""The client's own space: what /account/ shows and the few things a client
can change about themselves.

Only signed-in account holders have one. Access-code guests and the admin
preview get none: the portal menu does not offer it to them and every
endpoint here refuses them.

    summary(user, code_id)      the home page in one call: profile, completion,
                                insights, campaigns, selections, attention list
    save_image(user, kind, raw) the profile photo or company logo
    image_path(user, kind)      where it is, for serving it back to its owner
    set_notify(user, prefs)     which emails the client wants

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
NOTIFY_KEYS = ("quote", "live", "report")
NOTIFY_DEFAULT = {"quote": True, "live": True, "report": True}


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


# ---------------------------------------------------------- notifications --

def notify_prefs(user):
    try:
        got = json.loads(_col(user, "notify") or "{}")
    except ValueError:
        got = {}
    return {k: bool(got.get(k, NOTIFY_DEFAULT[k])) for k in NOTIFY_KEYS}


def set_notify(user, prefs):
    clean = {k: bool(prefs.get(k)) for k in NOTIFY_KEYS if k in prefs}
    merged = dict(notify_prefs(user), **clean)
    with db.connect() as conn:
        conn.execute("UPDATE users SET notify = ? WHERE id = ?", (json.dumps(merged), user["id"]))
    return merged


# ------------------------------------------------------------- completion --

def completion(user):
    """How complete the profile is, and the steps still open, in the order a
    client is most likely to do them."""
    steps = [("photo", "Add a profile photo", bool(_col(user, "photo"))),
             ("job_title", "Add your job title", bool(user["job_title"])),
             ("phone", "Add a phone number", bool(user["phone"])),
             ("company", "Add your company", bool(user["company"])),
             ("logo", "Add your company logo", bool(_col(user, "logo")))]
    done = 1 + sum(1 for s in steps if s[2])         # name and email are there from sign-up
    total = 1 + len(steps)
    return {"pct": int(round(done * 100.0 / total)),
            "missing": [{"key": k, "label": label} for k, label, ok in steps if not ok]}


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


def summary(user, code_id):
    """Everything /account/ shows, in one payload. Client-safe: no costs,
    margins or internal notes ever leave here."""
    team = sorted(portal.team_codes(code_id))
    with db.connect() as conn:
        sels = conn.execute(
            "SELECT id, name, token, codes, updated_at FROM selections "
            "WHERE code_id = ? AND archived_at IS NULL ORDER BY updated_at DESC LIMIT 50", (code_id,)).fetchall()
        camps = conn.execute(
            "SELECT * FROM campaigns WHERE code_id IN (%s) AND status != 'draft' "
            "ORDER BY CASE status WHEN 'live' THEN 0 ELSE 1 END, starts_at DESC LIMIT 30" % ",".join("?" * len(team)),
            team).fetchall()
        handled = conn.execute(
            "SELECT selection_name, handled_at FROM requests WHERE code_id = ? AND handled_at IS NOT NULL "
            "AND handled_at > ? ORDER BY handled_at DESC LIMIT 5", (code_id, db.now() - 14 * 86400)).fetchall()

    selections, shortlisted = [], set()
    for s in sels:
        codes = json.loads(s["codes"] or "[]")
        shortlisted.update(codes)
        selections.append({"name": s["name"], "token": s["token"], "creators": len(codes),
                           "updated_at": s["updated_at"]})

    campaigns, grades = [], []
    agg = {"exposure": 0, "reach": 0, "views": 0, "delivered": 0, "planned": 0}
    attention = []
    week = db.now() - 7 * 86400
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
        if row["updated_at"] and row["updated_at"] >= week and k["status"] == "live":
            attention.append({"kind": "report", "text": "New results on %s" % k["name"],
                              "href": "campaign/#t=" + k["token"]})
    for h in handled:
        attention.append({"kind": "quote", "text": "We've answered your quote request%s" % (
            " for " + h["selection_name"] if h["selection_name"] else ""), "href": None})

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
    u = {k: user[k] for k in ("email", "name", "company", "job_title", "phone", "created_at")}
    u["photo"] = image_version(user, "photo")
    u["logo"] = image_version(user, "logo")
    return {"user": u, "completion": completion(user), "credits": portal.balance(code_id),
            "monthly_credits": portal.monthly_allowance(user),
            "kam": _col(user, "kam") or None, "notify": notify_prefs(user),
            "insights": insights, "campaigns": campaigns, "selections": selections,
            "attention": attention[:6],
            "team": [{"name": t["name"], "job_title": t["job_title"]} for t in portal.teammates(code_id)]}
