"""The client's own space: what /account/ shows and the few things a client
can change about themselves.

Only signed-in account holders have one. Access-code guests and the admin
preview get none: the portal menu does not offer it to them and every
endpoint here refuses them.

    summary(user, code_id)      the whole profile page in one call: profile, completion,
                                selections with their statuses, analyses, campaigns,
                                briefs, notifications, credits, invites and Helvi's next step
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
    """One thing to do next, for Helvi's line on Overview."""
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
                "tail": ". Helvi uses it to pre-fill your briefs.", "cta": "Finish my profile", "href": "account/#account"}
    return {"kind": "find", "lead": "Ready for the next campaign? Tell Helvi the brief and get a ", "strong": "scored shortlist",
            "tail": ".", "cta": "Find creators", "href": ""}


def _may_rename(code_id, sel):
    import selrename
    return selrename.client_may(code_id, sel, db.admin_code_id())


def _kam_label(email):
    """The account manager's name for a card (never the email to a client)."""
    if not email:
        return None
    try:
        import hub
        n = hub._kam_name(email)
    except Exception:
        n = ""
    return n if n and "@" not in n else (str(email).split("@")[0].replace(".", " ").title() or None)


def summary(user, code_id, secret=b""):
    """Everything /account/ shows, in one payload. Client-safe: no costs,
    margins or internal notes ever leave here."""
    import gating
    import inbox
    import rewards
    import selstatus
    import lifecycle
    import board
    team = set(portal.team_codes(code_id))
    own_team = set(team)
    is_admin = False
    kam_sc = None
    # An owner or admin also sees, in their own Selections and Campaigns, everything filed under team accounts or
    # plain access codes (owner, 2026-10-18), so work like "Jamjoom" is never out of sight.
    try:
        import hub
        role, adm = hub.viewer(user)
        if role == "admin":
            is_admin = True
            team |= hub.unfiled_code_ids()
        elif role == "kam":
            import kam_scope
            kam_sc = kam_scope.clients(adm)
    except Exception:
        pass
    team = sorted(team)
    # Selections HelloVoice granted this person one by one (owner, 2026-10-15), and their campaigns.
    granted = sorted(db.granted_selection_ids(code_id)) or [-1]
    gq = ",".join("?" * len(granted))
    with db.connect() as conn:
        sels = conn.execute(
            "SELECT s.id, s.name, s.token, s.codes, s.updated_at, s.code_id, s.origin, s.request_id, s.created_at, s.stage, "
            "u.name owner, u.company company, u.kam kam, c.label code_label FROM selections s "
            "LEFT JOIN users u ON u.code_id = s.code_id LEFT JOIN codes c ON c.id = s.code_id "
            "WHERE (s.code_id IN (%s) OR s.id IN (%s)) AND s.archived_at IS NULL ORDER BY s.updated_at DESC LIMIT 60"
            % (",".join("?" * len(team)), gq), team + granted).fetchall()
        camps = conn.execute(
            "SELECT * FROM campaigns WHERE (code_id IN (%s) OR selection_id IN (%s)) AND status != 'draft' "
            "ORDER BY CASE status WHEN 'live' THEN 0 ELSE 1 END, starts_at DESC LIMIT 30" % (",".join("?" * len(team)), gq),
            team + granted).fetchall()

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
        chip = lifecycle.chip(s)
        stage = board.selection_stage(s, chip["key"], len(codes))
        # Item 194: who may drag it between the planning columns (board.may_move_selection, the same rule).
        may = is_admin or (s["code_id"] is not None and s["code_id"] in own_team) or (
            kam_sc is not None and ((s["code_id"] is not None and int(s["code_id"]) in kam_sc) or s["id"] in kam_sc.sel_ids))
        held = [k for k in (db.campaign(i) for i in board.campaigns_holding(s["id"])) if k is not None]
        selections.append({"stage": stage, "moves": board.selection_moves(may, chip["key"], stage),
                           "created_at": s["created_at"], "client": s["company"] or s["code_label"] or "",
                           "kam": _kam_label(s["kam"]),
                           "campaigns": [{"name": k["name"], "token": k["token"], "live": k["status"] == "live"} for k in held][:3],
                           "name": s["name"], "token": s["token"], "creators": len(codes), "updated_at": s["updated_at"],
                           "id": s["id"], "admin_delete": is_admin, "mine": s["code_id"] == code_id, "owner": None if s["code_id"] == code_id else (s["owner"] or s["code_label"] or "A colleague"),
                           # Only the client's own work can be deleted: not a colleague's, not HelloVoice's.
                           "can_delete": (s["origin"] or "admin") == "client" and code_id != db.admin_code_id()
                                         and portal.owns(code_id, s["code_id"]),
                           # Rename (item 173): the owner, never a colleague or someone it was shared with.
                           "can_rename": _may_rename(code_id, s),
                           "counts": selstatus.counts(codes, st, tiers),
                           "quote": chip})

    campaigns, grades = [], []
    agg = {"exposure": 0, "reach": 0, "views": 0, "delivered": 0, "planned": 0}
    try:
        pins = [int(x) for x in (db.setting("pinned_campaigns") or [])]
    except (TypeError, ValueError):
        pins = []
    camps = sorted(camps, key=lambda k: 0 if k["id"] in pins else 1)      # the pinned demo first (owner, 2026-10-20)
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
               # Same rate the dashboard shows: the video engagement rate when there is one.
               "er": t.get("video_er") if t.get("video_er") is not None else t.get("er"),
               "er_grade": t.get("er_grade"), "engagement": t.get("engagement") or 0,
               "delivered": t.get("delivered") or 0, "planned": t.get("planned") or 0,
               "updated_at": rep["updated_at"] if rep else None,
               # The dashboard's own goal grades, so the card says what the dashboard says.
               "goal_grades": {i.get("key"): i.get("grade") for i in ((rep or {}).get("progress") or {}).get("items") or [] if i.get("key")},
               "quote": (lifecycle.chip(db.selection(k["selection_id"])) if k["selection_id"] and db.selection(k["selection_id"]) is not None else None)}
        row["pinned"] = k["id"] in pins
        # The card shows HelloVoice × the campaign's own client logo (owner, 2026-10-20), not the account's logo.
        row["client"] = k["client"]
        row["logos"] = db.campaign_logos(k)[:2]
        campaigns.append(row)
        if k["status"] == "live" and not row["pinned"]:
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
        if sel is not None and sel["deleted_at"]:
            sel = None                      # its selection was deleted: the brief no longer opens it
        briefs.append({"id": b["id"], "can_delete": code_id != db.admin_code_id(), "summary": b["summary"], "objective": b["objective"], "source": b["source"],
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
