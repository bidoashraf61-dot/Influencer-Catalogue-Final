"""Push composer on the profile (item 209, slice c, 2026-10-21): the team sends a push to one client company from
its page (everyone there, the people on a campaign, or chosen people), with a reach count, a phone preview, a
test to one's own phone, and an optional send time. It uses the same queue and rules as the admin's "App & alerts"
send (push.create_message): the message lands in each person's bell too, and manual pushes wait out quiet hours.

    who         may push to
    admin       any client company
    KAM         her own clients
    everyone    never: "every client", a role, or anyone outside the viewer's clients stays in the admin

A push to 10 people or more asks for the emailed step-up code first.
"""
import json
import re

import db
import hub

BIG = 10                    # this many recipients and the sender must confirm with an emailed code
TITLE_MAX, BODY_MAX = 60, 180


def _scope(role, a):
    """({user id: row}, {company key: [rows]}) for the clients this viewer may push to."""
    groups, _, _ = hub._groups(role, a)
    users = {}
    for key, g in groups.items():
        for u in g["users"]:
            users[u["id"]] = u
    return users, groups


def _devices(user_ids):
    import push
    with db.connect() as conn:
        return {d["user_id"] for d in push._devices(conn, user_ids, ()) if d["user_id"]}


def context(role, a, key):
    """What the composer shows for one company: its people (with whether each has phone alerts) and campaigns."""
    users, groups = _scope(role, a)
    g = groups.get(key)
    if g is None:
        return None
    ids = [u["id"] for u in g["users"] if u["status"] == "active"]
    phones = _devices(ids)
    people = [{"id": u["id"], "name": u["name"] or u["email"], "email": u["email"], "job_title": u["job_title"] or "", "phone": u["id"] in phones}
              for u in g["users"] if u["status"] == "active"]
    codes = [u["code_id"] for u in g["users"] if u["code_id"] is not None]
    camps = []
    if codes:
        with db.connect() as conn:
            for k in conn.execute("SELECT id, name, token, status, code_id FROM campaigns WHERE code_id IN (%s) ORDER BY "
                                  "CASE status WHEN 'live' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END, id DESC" % ",".join("?" * len(codes)), codes):
                camps.append({"id": k["id"], "name": k["name"], "status": k["status"], "token": k["token"]})
    return {"key": key, "name": hub._name_of(key, g), "people": people, "campaigns": camps, "big": BIG, "title_max": TITLE_MAX, "body_max": BODY_MAX}


def _audience(role, a, aud):
    """(user ids, label, error). Only company, campaign or people audiences, only inside the viewer's clients."""
    import push
    users, groups = _scope(role, a)
    typ = (aud or {}).get("type")
    if typ == "company":
        g = groups.get(str(aud.get("key") or ""))
        if g is None:
            return None, "", "That company is not in your list."
        ids = {u["id"] for u in g["users"] if u["status"] == "active"}
        return ids, hub._name_of(aud["key"], g), None
    if typ == "campaign":
        want = [int(x) for x in (aud.get("campaigns") or []) if str(x).isdigit()]
        if not want:
            return None, "", "Pick a campaign."
        mine_codes = {u["code_id"] for u in users.values() if u["code_id"] is not None}
        with db.connect() as conn:
            rows = conn.execute("SELECT id, name, code_id FROM campaigns WHERE id IN (%s)" % ",".join("?" * len(want)), want).fetchall()
        if len(rows) != len(want) or any(r["code_id"] not in mine_codes for r in rows):
            return None, "", "Those campaigns are not in your list."
        ids, _ = push.resolve({"type": "campaign", "campaigns": want})
        ids = {i for i in ids if i in users and users[i]["status"] == "active"}
        return ids, ", ".join(r["name"] for r in rows), None
    if typ == "people":
        want = {int(x) for x in (aud.get("people") or []) if str(x).isdigit()}
        ids = {i for i in want if i in users and users[i]["status"] == "active"}
        if not ids or len(ids) != len(want):
            return None, "", "Pick people from this company."
        return ids, "%d chosen" % len(ids), None
    return None, "", "Pick who gets it."


def reach(role, a, aud):
    import push
    ids, label, err = _audience(role, a, aud)
    if err:
        return 400, {"ok": False, "message": err}
    r = push.reach({"type": "people", "people": sorted(ids)})
    users, _ = _scope(role, a)
    phones = _devices(list(ids))
    off = sorted((users[i]["name"] or users[i]["email"]) for i in ids if i not in phones)
    return 200, {"ok": True, "label": label, "people": len(ids), "push_people": len({i for i in ids if i in phones}), "devices": r["devices"],
                 "no_phone": off[:8], "no_phone_n": len(off), "needs_code": len(ids) >= BIG}


def _safe_url(url, camp_tokens):
    url = str(url or "").strip()
    if url.startswith("/account") and "//" not in url[1:]:
        return url
    m = re.match(r"^/campaign/dashboard/#t=([A-Za-z0-9_-]+)$", url)
    if m and m.group(1) in camp_tokens:
        return url
    return "/account/"


def send(role, a, actor_email, aud, title, body, url, send_at=None, test=False, stepup_open=False):
    import push, team
    title, body = str(title or "").strip()[:TITLE_MAX], str(body or "").strip()[:BODY_MAX]
    if not title:
        return 400, {"ok": False, "message": "Add a title."}
    ids, label, err = _audience(role, a, aud)
    if err:
        return 400, {"ok": False, "message": err}
    with db.connect() as conn:
        toks = {r["token"] for r in conn.execute("SELECT token FROM campaigns")}
    url = _safe_url(url, toks)
    if test:
        n = push.create_message(title, body, url, {"type": "test"}, actor_email, test_email=actor_email)     # devices it went to
        with db.connect() as conn:
            mid = conn.execute("SELECT MAX(id) FROM push_messages WHERE source = 'test' AND created_by = ?", (actor_email,)).fetchone()[0]
        if not n:
            return 200, {"ok": True, "id": mid, "devices": 0, "message": "No phone of yours has alerts on yet. Scan the HELVi QR from your profile menu first."}
        return 200, {"ok": True, "id": mid, "devices": n, "message": "A test is on its way to your phone."}
    if not ids:
        return 400, {"ok": False, "message": "Nobody is in that audience."}
    if len(ids) >= BIG and not stepup_open:
        return 403, {"ok": False, "reason": "stepup", "message": "Confirm with an emailed code first."}
    when = None
    if send_at:
        try:
            when = int(send_at)
        except (TypeError, ValueError):
            return 400, {"ok": False, "message": "That time is not valid."}
        if when <= db.now() + 60:
            when = None
        elif when > db.now() + 60 * 86400:
            return 400, {"ok": False, "message": "Schedule up to 60 days ahead."}
    mid = push.create_message(title, body, url, {"type": "people", "people": sorted(ids), "label": label, "from": "profile"}, actor_email, send_at=when)
    team.log("push_sent", actor_email, ("%d people: %s" % (len(ids), title))[:300])
    r = push.reach({"type": "people", "people": sorted(ids)})
    return 200, {"ok": True, "id": mid, "scheduled": bool(when), "people": len(ids), "push_people": r["push_people"],
                 "message": ("Scheduled for %s." if when else "Sent to %s.") % ("1 person" if len(ids) == 1 else "%d people" % len(ids))}
