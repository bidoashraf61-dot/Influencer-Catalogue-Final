"""The Manage drawer on the Select board (item 331, owner 2026-11-04): every control for one selection, with the
permission matrix enforced HERE, never only hidden in the page.

    GET  /api/board/selection-manage?s=<token>     view(): what this person may do, and the selection's details
    POST /api/board/selection-manage               act():  {s, do: stage | meta | visibility | archive | delete, ...}

Who may do what (owner = a team account with the owner role; admin = an admin; kam = a key account manager on her
own clients' selections):

    stage       owner, admin, kam   any column, any direction; a reason is required unless it is the next column on
    meta        owner, admin, kam   next step, due date, internal notes (notes never reach a client)
    visibility  owner, admin        hide a selection from the client's own boards
    archive     owner, admin, kam   reversible (Admin > Selections > Archive, and History)
    delete      owner               forever, after typing the selection's name
    KAM change  owner, admin        through the existing /api/hub/assign-kam

A client, on a selection they own, gets their own options instead: rename, approve a ready quote (both through the
existing routes), remove (when the existing rule allows it) and request changes (do: request; tells the KAM and the team,
and lands in the internal notes). They never receive notes, the KAM's email, or any staff control. Other team logins get nothing.
Every change is recorded in History, and the selection's owner and KAM get a bell notice (never the actor).
"""
import time

import board
import db
import history

SCHEMA = """
CREATE TABLE IF NOT EXISTS selection_meta (
    sel_id INTEGER PRIMARY KEY,
    next_text TEXT,
    next_due INTEGER,
    notes TEXT,
    hidden INTEGER NOT NULL DEFAULT 0,
    updated_by TEXT,
    updated_at INTEGER
);
"""

STAGES = board.STAGES
LABEL = board.LABEL


def ensure(conn):
    """The table and column exist on THIS database. Called before reading them, not only at start-up: a trial link's
    database is a copy of a template built earlier, which never ran init()."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'selection_meta'").fetchone():
        conn.executescript(SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(selections)")}
    if "stage_override" not in cols:
        # A stage set by hand from the Manage drawer: wins over what the quote and campaigns say (board.selection_stage).
        conn.execute("ALTER TABLE selections ADD COLUMN stage_override TEXT")


def init():
    with db.connect() as conn:
        ensure(conn)


def actor(h):
    """(level, email): owner | admin | kam | team | client | None."""
    import team
    role, who = board.viewer(h)
    email = board._me(h) or ""
    if role == "admin":
        return ("owner" if team.role_of(who) == "owner" else "admin"), email
    if role in ("team", "kam", "client"):
        return role, email
    return None, ""


def can(h, level, sel):
    off = {"stage": False, "meta": False, "visibility": False, "archive": False, "delete": False, "kam": False,
           "move": False, "rename": False, "approve": False, "request": False, "remove": False}
    if level in ("owner", "admin"):
        return dict(off, stage=True, meta=True, visibility=True, archive=True, kam=True, move=True, rename=True, delete=(level == "owner"))
    if level == "kam" and h.admin_like_for(sel["code_id"], sel["id"], None):
        return dict(off, stage=True, meta=True, archive=True, move=True, rename=True)
    if level == "client":
        import lifecycle
        import portal
        import selrename
        cid = board.viewer(h)[1]
        if cid is None or not portal.owns(cid, sel["code_id"]):
            return off
        return dict(off, rename=bool(selrename.client_may(cid, sel, db.admin_code_id())), request=True,
                    approve=lifecycle.chip(sel)["key"] == "ready",
                    remove=(sel["origin"] or "admin") == "client" and int(cid) != int(db.admin_code_id()))
    return off


def meta_of(sel_id):
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM selection_meta WHERE sel_id = ?", (int(sel_id),)).fetchone()
    return r


def _stage_now(sel):
    import lifecycle
    chip = lifecycle.chip(sel)["key"]
    return board.selection_stage(sel, chip, None), board.selection_stage(sel, chip, None, use_override=False)


def view(h, token):
    level, _ = actor(h)
    sel = db.selection(token=str(token or "")) if token else None
    if level is None:
        return 401, {"ok": False, "reason": "signin"}
    if sel is None or sel["deleted_at"]:
        return 404, {"ok": False, "message": "That selection is not here any more."}
    allow = can(h, level, sel)
    if not any(allow.values()):
        return 403, {"ok": False, "message": "You cannot manage this selection."}
    if level == "client":
        m = meta_of(sel["id"])
        if m is not None and m["hidden"]:
            return 404, {"ok": False, "message": "That selection is not here any more."}
        return 200, {"ok": True, "level": level, "can": allow, "id": sel["id"], "name": sel["name"], "stage": _stage_now(sel)[0],
                     "stages": [{"key": k, "label": LABEL[k]} for k in STAGES],
                     "next_text": (m["next_text"] if m else "") or "", "next_due": (m["next_due"] if m else None)}
    m = meta_of(sel["id"])
    stage, derived = _stage_now(sel)
    kam = db.kam_of_item("selection", sel["id"]) or ""
    out = {"ok": True, "level": level, "can": allow, "id": sel["id"], "name": sel["name"], "stage": stage, "derived": derived,
           "by_hand": stage != derived, "stages": [{"key": k, "label": LABEL[k]} for k in STAGES],
           "next_text": (m["next_text"] if m else "") or "", "next_due": (m["next_due"] if m else None),
           "notes": (m["notes"] if m else "") or "", "hidden": bool(m["hidden"]) if m else False, "kam": kam,
           "archived": bool(sel["archived_at"])}
    if allow["kam"]:
        import hub
        out["kam_options"] = [{"name": k["name"], "email": k["email"]} for k in hub.kam_options()]
    return 200, out


def _tell(sel, actor_email, title, rest):
    """The selection owner's and its KAM's bell, never the person who made the change."""
    try:
        import inbox
        import portal
        ids = []
        u = portal.user_for_code(sel["code_id"]) if sel["code_id"] is not None else None
        if u is not None:
            ids.append(u["id"])
        k = db.kam_of_item("selection", sel["id"])
        ku = portal.user_by_email(k) if k else None
        if ku is not None:
            ids.append(ku["id"])
        me = portal.user_by_email(actor_email) if actor_email else None
        ids = [i for i in ids if not (me is not None and i == me["id"])]
        if ids:
            inbox.emit(ids, "sel_updated", title, rest, href="/selection/#s=" + sel["token"], ref="manage:%s" % sel["id"])
    except Exception:
        pass


def _clean(s, n):
    return " ".join(str(s or "").split())[:n]


def act(h, b):
    level, email = actor(h)
    if level is None:
        return 401, {"ok": False, "reason": "signin"}
    sel = db.selection(token=str(b.get("s") or "")) if b.get("s") else None
    if sel is None or sel["deleted_at"]:
        return 404, {"ok": False, "message": "That selection is not here any more."}
    allow = can(h, level, sel)
    do = str(b.get("do") or "")
    if not allow.get(do):
        return 403, {"ok": False, "message": "That is not yours to change."}
    history.set_actor(email or level)
    sid = int(sel["id"])
    name = sel["name"]

    if do == "request":
        text = _clean(b.get("text"), 500)
        if len(text) < 3:
            return 400, {"ok": False, "message": "Say what you would like changed."}
        import notify
        import portal
        u = portal.user_for_code(sel["code_id"]) if sel["code_id"] is not None else None
        kam = (u["kam"] if u is not None and "kam" in u.keys() else None) or db.kam_of_item("selection", sid)
        with history.tracked("selection", str(sid), "Client asked for changes on %s: %s" % (name, text)):
            with db.connect() as conn:
                r = conn.execute("SELECT notes FROM selection_meta WHERE sel_id = ?", (sid,)).fetchone()
                line = "%s asked for changes: %s" % (email or "The client", text)
                notes = ((r["notes"] + "\n") if r and r["notes"] else "") + line
                conn.execute("INSERT INTO selection_meta (sel_id, notes, updated_by, updated_at) VALUES (?,?,?,?) "
                             "ON CONFLICT(sel_id) DO UPDATE SET notes = excluded.notes, updated_by = excluded.updated_by, "
                             "updated_at = excluded.updated_at", (sid, notes[-2000:], email, db.now()))
                conn.execute("UPDATE selections SET updated_at = ? WHERE id = ?", (db.now(), sid))
        notify.send("quote_changed", ["Changes requested on %s" % name, text, email], kam=kam)
        _tell(sel, email, "Changes requested on %s" % name, text)
        return 200, {"ok": True, "message": "Sent. Your account manager will come back to you."}

    if do == "stage":
        to = str(b.get("to") or "")
        if to not in STAGES:
            return 400, {"ok": False, "message": "Pick one of the six stages."}
        stage, derived = _stage_now(sel)
        if to == stage:
            return 200, {"ok": True, "stage": stage, "message": "%s is already in %s." % (name, LABEL[to])}
        reason = _clean(b.get("reason"), 300)
        step = STAGES.index(to) - STAGES.index(stage)
        if step != 1 and len(reason) < 3:
            return 400, {"ok": False, "need_reason": True,
                         "message": "Say why: moving back, or skipping a stage, needs a short reason."}
        with history.tracked("selection", str(sid), "Moved %s to %s by hand%s" % (name, LABEL[to], (": " + reason) if reason else "")):
            with db.connect() as conn:
                conn.execute("UPDATE selections SET stage_override = ?, updated_at = ? WHERE id = ?",
                             (None if to == derived else to, db.now(), sid))
        _tell(sel, email, "%s moved to %s" % (name, LABEL[to]), reason)
        return 200, {"ok": True, "stage": to, "by_hand": to != derived, "message": "%s moved to %s." % (name, LABEL[to])}

    if do == "meta":
        text = _clean(b.get("next_text"), 200)
        notes = str(b.get("notes") or "").strip()[:2000]
        due = None
        raw = str(b.get("next_due") or "").strip()
        if raw:
            try:
                due = int(time.mktime(time.strptime(raw[:10], "%Y-%m-%d"))) + 12 * 3600
            except ValueError:
                return 400, {"ok": False, "message": "The due date must be a day, like 2026-11-20."}
        with history.tracked("selection", str(sid), "Edited next step and notes of %s" % name):
            with db.connect() as conn:
                conn.execute("INSERT INTO selection_meta (sel_id, next_text, next_due, notes, hidden, updated_by, updated_at) "
                             "VALUES (?,?,?,?,0,?,?) ON CONFLICT(sel_id) DO UPDATE SET next_text = excluded.next_text, "
                             "next_due = excluded.next_due, notes = excluded.notes, updated_by = excluded.updated_by, "
                             "updated_at = excluded.updated_at", (sid, text, due, notes, email, db.now()))
                conn.execute("UPDATE selections SET updated_at = ? WHERE id = ?", (db.now(), sid))
        if text:
            _tell(sel, email, "Next step on %s" % name, text)
        return 200, {"ok": True, "message": "Saved."}

    if do == "visibility":
        hide = bool(b.get("hidden"))
        with history.tracked("selection", str(sid), "%s %s %s the client" % ("Hid" if hide else "Showed", name, "from" if hide else "to")):
            with db.connect() as conn:
                conn.execute("INSERT INTO selection_meta (sel_id, hidden, updated_by, updated_at) VALUES (?,?,?,?) "
                             "ON CONFLICT(sel_id) DO UPDATE SET hidden = excluded.hidden, updated_by = excluded.updated_by, "
                             "updated_at = excluded.updated_at", (sid, 1 if hide else 0, email, db.now()))
        return 200, {"ok": True, "hidden": hide, "message": "Hidden from the client's boards." if hide else "Visible to the client again."}

    if do == "archive":
        with history.tracked("selection", str(sid), "Archived selection %s from the board" % name):
            db.set_archived("selections", sid, True)
        return 200, {"ok": True, "message": "%s archived. Bring it back from Admin > Selections > Archive." % name}

    if do == "delete":
        if _clean(b.get("confirm"), 200).lower() != _clean(name, 200).lower():
            return 400, {"ok": False, "message": "Type the selection's name exactly to delete it."}
        with history.tracked("selection", str(sid), "Deleted selection %s from the board" % name):
            db.delete_selection(sid)
            with db.connect() as conn:
                conn.execute("DELETE FROM selection_meta WHERE sel_id = ?", (sid,))
        return 200, {"ok": True, "deleted": True, "message": "%s deleted." % name}

    return 400, {"ok": False, "message": "Unknown action."}
