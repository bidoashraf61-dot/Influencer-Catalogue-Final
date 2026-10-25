"""Selection page filters, bulk actions and saved views (portal item 242, 2026-10-24).

Three things the selection page needs from the server and could not get before:

* facts(): per creator, the extra fields the new filters read — gender, nationality, licences,
  engagement rate, average views, whether an analysis or public metrics exist, verified badge.
  Audience figures (top country, share of women) are locked analysis data: they go to HelloVoice
  only, never to a client (the same rule as api_discover's free_only).
* api_bulk(): approve / reject / set back many creators in one call, with ONE notification
  (the client's bell is already bundled by selstatus.ring_client; the KAM gets one summary email).
* api_bulk_tags() and api_views(): add or remove a client tag on many creators; named saved
  views per selection, kept in settings["sel_views:<id>"] (no schema change).
"""
import json
import re

import db

VIEWS_MAX = 20


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def facts(codes, by, team=False):
    """{code: {...}} for the codes on one selection page. Keys are short: the page holds 1,000."""
    codes = [c for c in codes if c in by]
    out = {c: {} for c in codes}
    if not codes:
        return out
    for c in codes:
        row = by[c]
        keys = row.keys()
        g = (row["gender"] if "gender" in keys else None) or ""
        if g:
            out[c]["g"] = g.title()
        nat = (row["nationality"] if "nationality" in keys else None) or ""
        if nat.strip():
            out[c]["nat"] = nat.strip().title()[:30]
    with db.connect() as conn:
        for i in range(0, len(codes), 500):
            part = codes[i:i + 500]
            q = ",".join("?" * len(part))
            for r in conn.execute("SELECT code, country FROM creator_licences WHERE code IN (%s) AND "
                                  "(status = 'verified' OR (status = 'claimed' AND source != 'bio-weak'))" % q, part):
                out[r["code"]].setdefault("lic", []).append(r["country"])
            # Latest public metrics per platform: engagement and the verified badge.
            for r in conn.execute("SELECT code, platform, er_pct, verified, followers, MAX(at) FROM profile_metrics "
                                  "WHERE code IN (%s) GROUP BY code, platform" % q, part):
                f = out[r["code"]]
                f["m"] = 1
                if r["verified"]:
                    f["ver"] = 1
                er = _num(r["er_pct"])
                if er is not None and (r["followers"] or 0) >= f.get("_pf", -1):
                    f["_pf"] = r["followers"] or 0
                    f["er"] = round(er, 2)
            for r in conn.execute("SELECT code, data, source FROM creator_analysis WHERE code IN (%s)" % q, part):
                f = out[r["code"]]
                try:
                    d = json.loads(r["data"] or "{}")
                except ValueError:
                    continue
                # "Apify basic" is public profile numbers, not a full analysis report.
                if (r["source"] or "") != "Apify basic":
                    f["an"] = 1
                else:
                    f["m"] = 1
                fol = _num(d.get("followers")) or 0
                er = _num(d.get("er"))
                if er is not None and fol >= f.get("_af", -1):
                    f["_af"] = fol
                    f["er"] = round(er, 2)
                v = _num(d.get("avg_reel_plays")) or _num(d.get("avg_views"))
                if v and v > f.get("v", 0):
                    f["v"] = int(v)
                if team:
                    a = d.get("audience") or {}
                    top = (a.get("countries") or [None])[0]
                    if isinstance(top, dict) and top.get("code") and fol >= f.get("_cf", -1):
                        f["_cf"] = fol
                        f["ac"] = top["code"]
                        fem = _num((a.get("gender") or {}).get("female"))
                        if fem is not None:
                            f["af"] = round(fem)
    for f in out.values():
        for k in ("_pf", "_af", "_cf"):
            f.pop(k, None)
    # Audience share filters (Bido, 2026-10-25), for clients too: each creator's highest share per
    # country, gender and age band across their analysed platforms. A client gets each share rounded
    # DOWN to 5 points: the filter's steps are 5 points, so every "at least N%" still answers exactly,
    # and the page never prints these numbers.
    try:
        import discover
        best = discover.audience_best()
    except Exception:
        best = {}
    step = 1 if team else 5
    cut = lambda v: int(v) - int(v) % step
    for c in codes:
        b = best.get(c)
        if not b:
            continue
        au = {"c": {k: cut(v) for k, v in sorted(b["c"].items(), key=lambda kv: -kv[1])[:6] if v >= 5},
              "a": {k: cut(v) for k, v in b["a"].items() if v >= 5}}
        for g in ("f", "m"):
            if g in b:
                au[g] = cut(b[g])
        out[c]["au"] = au
    return {c: f for c, f in out.items() if f}


# ------------------------------------------------------------------- bulk --

def _target(h, b):
    """(sel, reader, role, codes) for a bulk action, or None after answering."""
    token = str(b.get("token") or "")
    reader = h.selection_viewer(token)
    if not reader:
        h.send_json(401, {"ok": False, "reason": "locked"}, h.cors())
        return None
    import portal
    sel = db.selection(token=token) if token else None
    if sel is None or (sel["code_id"] is not None and int(reader) != db.admin_code_id()
                       and not portal.opens(int(reader), sel)):
        h.send_json(404, {"ok": False}, h.cors())
        return None
    listed = json.loads(sel["codes"] or "[]")
    want = [str(c or "").strip().upper() for c in (b.get("codes") or [])][:1000]
    codes = [c for c in dict.fromkeys(want) if c in listed]
    if not codes:
        h.send_json(400, {"ok": False, "reason": "no_codes"}, h.cors())
        return None
    return sel, int(reader), h.selection_role(sel, reader), codes


def api_bulk(h):
    """POST {token, codes:[...], status, reason?, note?} or {token, items:[{code, status, reason, note}]}
    (the second form is Undo: each creator back to what it was). Owner and HelloVoice only."""
    import selstatus
    import notify
    b = h.json_body()
    items = b.get("items")
    if isinstance(items, list) and items:
        b = dict(b, codes=[i.get("code") for i in items if isinstance(i, dict)])
    got = _target(h, b)
    if not got:
        return
    sel, reader, role, codes = got
    if role == "viewer":
        return h.send_json(403, {"ok": False, "reason": "not_owner",
                                 "message": "Only the person who owns this selection can approve or reject creators."}, h.cors())
    plan = {}
    if isinstance(items, list) and items:
        for i in items:
            if isinstance(i, dict):
                plan[str(i.get("code") or "").strip().upper()] = (str(i.get("status") or ""), i.get("reason"), i.get("note"))
    else:
        for c in codes:
            plan[c] = (str(b.get("status") or ""), b.get("reason"), b.get("note"))
    if role == "owner" and any(p[0] == "unavailable" for p in plan.values()):
        return h.send_json(403, {"ok": False, "reason": "hv_only", "message": "Only HelloVoice marks a creator unavailable."}, h.cors())
    kind, name, user = h._status_who(role, reader)
    done, rows, lines = {}, {}, []
    for c in codes:
        status, reason, note = plan.get(c, ("", None, None))
        row, err = selstatus.set_status(sel, c, status, kind, name, reason, note)
        if err:
            continue
        rows[c] = row
        done.setdefault(status, []).append(c)
        if kind == "hv":
            selstatus.ring_client(sel, c, status, name, row.get("note"))     # bundled per selection + status
    if not rows:
        return h.send_json(400, {"ok": False, "reason": "status"}, h.cors())
    if kind != "hv":
        # One email to the KAM for the whole batch, not one line per click.
        names = {r["code"]: r["name"] for r in db.creators_by_codes(list(rows))}
        for status, cs in done.items():
            shown = ", ".join(names.get(c) or c for c in cs[:30]) + (" and %d more" % (len(cs) - 30) if len(cs) > 30 else "")
            lines.append("%s %d: %s" % (selstatus.LABEL.get(status, status), len(cs), shown))
        who = ((user["name"] or user["email"]) + (", " + user["company"] if user["company"] else "")) if user else "A client"
        try:
            notify.send("status", ["%s changed %d creators at once on “%s”:" % (who, len(rows), sel["name"])] + lines,
                        kam=user["kam"] if user is not None and "kam" in user.keys() else None)
        except Exception:
            pass
    db.log("shortlist", reader, h.client_ip(), h.headers.get("User-Agent"),
           "status-bulk:%s" % ",".join("%s=%d" % (k, len(v)) for k, v in done.items()))
    p = h.selection_status_payload(sel, json.loads(sel["codes"] or "[]"), reader)
    return h.send_json(200, {"ok": True, "rows": rows, "status_counts": p.get("status_counts")}, h.cors())


def _clean_tag(t):
    return re.sub(r"[<>]", "", re.sub(r"\s+", " ", str(t or ""))).strip()[:24]


def api_bulk_tags(h):
    """POST {token, codes, add?, remove?}: one client tag on or off many creators."""
    import portal
    b = h.json_body()
    got = _target(h, b)
    if not got:
        return
    sel, reader, role, codes = got
    if not portal.may_edit(int(reader), sel, db.admin_code_id()):
        return h.send_json(403, {"ok": False, "reason": "not_owner",
                                 "message": "Only the person who owns this selection can change it."}, h.cors())
    add, rem = _clean_tag(b.get("add")), _clean_tag(b.get("remove"))
    if not add and not rem:
        return h.send_json(400, {"ok": False, "reason": "tag"}, h.cors())
    have = json.loads((sel["client_tags"] if "client_tags" in sel.keys() else None) or "{}")
    everyone = have
    for c in codes:
        mine = [t for t in (have.get(c) or []) if not rem or t.lower() != rem.lower()]
        if add and add.lower() not in [t.lower() for t in mine] and len(mine) < 8:
            mine.append(add)
        if mine != (have.get(c) or []):
            everyone = db.set_client_tags(sel["id"], c, mine)
    return h.send_json(200, {"ok": True, "client_tags": everyone}, h.cors())


# ------------------------------------------------------------ saved views --

def _clean_view(v):
    """A view is the page's own state: filters, chips, group, sort. Only plain strings and lists."""
    if not isinstance(v, dict):
        return None
    out = {}
    for k, x in list(v.items())[:40]:
        k = str(k)[:20]
        if isinstance(x, str):
            out[k] = x[:200]
        elif isinstance(x, list):
            out[k] = [str(i)[:80] for i in x[:60] if isinstance(i, (str, int, float)) or i is None]
    return out


def views_of(sel_id):
    return db.setting("sel_views:%d" % sel_id, []) or []


def api_views(h):
    """POST {token, op: list|save|delete, name?, view?, id?}. Everyone who opens the selection sees its
    views; the owner and HelloVoice save and delete them."""
    import time
    b = h.json_body()
    token = str(b.get("token") or "")
    reader = h.selection_viewer(token)
    if not reader:
        return h.send_json(401, {"ok": False, "reason": "locked"}, h.cors())
    import portal
    sel = db.selection(token=token) if token else None
    if sel is None or (sel["code_id"] is not None and int(reader) != db.admin_code_id()
                       and not portal.opens(int(reader), sel)):
        return h.send_json(404, {"ok": False}, h.cors())
    views = views_of(sel["id"])
    op = str(b.get("op") or "list")
    if op != "list":
        if h.selection_role(sel, reader) == "viewer":
            return h.send_json(403, {"ok": False, "reason": "not_owner",
                                     "message": "Only the person who owns this selection can save views."}, h.cors())
        if op == "save":
            name = re.sub(r"[<>]", "", " ".join(str(b.get("name") or "").split()))[:40]
            view = _clean_view(b.get("view"))
            if not name or view is None:
                return h.send_json(400, {"ok": False, "reason": "name"}, h.cors())
            views = [v for v in views if v.get("name", "").lower() != name.lower()]
            vid = "v%d" % int(time.time() * 1000)
            views.insert(0, {"id": vid, "name": name, "view": view, "at": int(time.time())})
            views = views[:VIEWS_MAX]
        elif op == "delete":
            vid = str(b.get("id") or "")
            views = [v for v in views if v.get("id") != vid]
        db.set_setting("sel_views:%d" % sel["id"], views)
    return h.send_json(200, {"ok": True, "views": views}, h.cors())


# ----------------------------------------------- who may publish scores --

def can_publish(h):
    """The "Client sees" switches (scores and fit, profile analysis) are for HelloVoice owner and admin
    accounts only (Bido, 2026-10-24): never a key account manager, an admin-role viewer, a client, an
    owner of the selection or a colleague. Signed in to the admin, or to the portal with an admin email."""
    import team
    import portal
    if h.kam_clients() is not None:
        return False
    a = h.admin()
    if a is None:
        u = portal.user_for_code(h.viewer_cookie_id())
        a = db.admin_by_email(u["email"]) if u is not None and u["email"] else None
    return a is not None and team.role_of(a) in ("owner", "admin")
