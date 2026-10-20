"""The quote lifecycle of a selection: the one chip a client reads (fix batch 9, #42).

    Draft -> Quote requested -> Quote ready -> Approved -> Campaign live -> Completed

Almost everything is DERIVED from data that already exists:

  * Quote requested  a row in ``requests`` for the selection (``selections.request_id``, else the
                     newest request from the same client with the same name), so every selection a
                     client already sent for a quote reads "Quote requested" without a migration.
  * Quote ready      HelloVoice marks it in the admin (``selection_quote.ready_*``: a note and an
                     optional link the client sees; nothing else about price comes from this flow).
  * Approved         the selection's OWNER presses Approve (``selection_quote.approved_*``).
  * Campaign live    a campaign linked to the selection (``campaigns.selection_id``) is live.
  * Completed        no linked campaign is live and one has ended.

The only table added is ``selection_quote`` (+ ``quote_changes`` for edits after the request).
Everything is created with IF NOT EXISTS, so the migration is idempotent.

Rules (Bido, 2026-10-10): the selection stays editable after a quote request, with the warning
"This updates your quote request" and the account manager told (notify event ``quote_changed``);
only the owner (``portal.may_edit``) requests and approves; colleagues see the chip and timeline
read-only; the client is only ever told through the in-portal bell, never by email; the account
manager and team are emailed through ``notify`` (that is the team, not the client).

    chip(sel)                      {"key", "label"}  cheap, for lists
    state_of(sel)                  the full state + timeline, internal
    client_payload(sel, role)      what the selection page / profile / Helvi may read
    admin_payload(sel)             the same + note, link, who, campaigns, "changed since ready"
"""
import json
import re
import threading

import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS selection_quote (
    selection_id INTEGER PRIMARY KEY,
    requested_at INTEGER, requested_by TEXT, request_id INTEGER,
    ready_at INTEGER, ready_by TEXT, ready_note TEXT, ready_link TEXT,
    approved_at INTEGER, approved_by TEXT, approved_by_user INTEGER,
    live_at INTEGER, ended_at INTEGER
);
CREATE TABLE IF NOT EXISTS quote_changes (
    id INTEGER PRIMARY KEY,
    selection_id INTEGER NOT NULL,
    at INTEGER NOT NULL,
    by_name TEXT,
    added INTEGER NOT NULL DEFAULT 0,
    removed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS quote_changes_sel ON quote_changes(selection_id, at);
"""

STATES = ("draft", "requested", "ready", "approved", "live", "completed")
LABEL = {"draft": "Draft", "requested": "Quote requested", "ready": "Quote ready", "approved": "Approved",
         "live": "Campaign live", "completed": "Completed"}
ACTIVE = ("requested", "ready", "approved")        # editing now updates a quote that exists
NOTE_MAX, LINK_MAX = 500, 300
NOTIFY_DELAY = 120                                  # seconds a burst of edits is gathered before one email
WARNING = "This updates your quote request"


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)
    db.on("campaign_status", _campaign_status)


# ------------------------------------------------------------------ state --

def _row(conn, sid):
    return conn.execute("SELECT * FROM selection_quote WHERE selection_id = ?", (sid,)).fetchone()


def _keys(sel):
    try:
        return set(sel.keys())
    except AttributeError:
        return set(sel)


def _field(sel, name):
    return sel[name] if name in _keys(sel) else None


def _owner_name(code_id):
    import portal
    u = portal.user_for_code(code_id) if code_id else None
    return (u["name"] if u is not None and u["name"] else None)


def _request(conn, sel):
    """(request id, at, by) of the quote request behind this selection, or None."""
    rid = _field(sel, "request_id")
    if rid:
        r = conn.execute("SELECT id, at, name FROM requests WHERE id = ?", (rid,)).fetchone()
        if r is not None:
            return r["id"], r["at"], r["name"]
    if _field(sel, "code_id") is not None and _field(sel, "name"):
        r = conn.execute("SELECT id, at, name FROM requests WHERE code_id = ? AND selection_name = ? "
                         "ORDER BY at DESC LIMIT 1", (sel["code_id"], sel["name"])).fetchone()
        if r is not None:
            return r["id"], r["at"], r["name"]
    return None


def state_of(sel):
    """The state and the timeline of one selection (a row or any mapping with id, name, code_id,
    request_id, created_at). Internal: ``client_payload`` is what leaves the server."""
    sid = sel["id"]
    with db.connect() as conn:
        q = _row(conn, sid)
        legacy = _request(conn, sel)
        # A campaign holds many selections (item 174): its first in campaigns.selection_id, the rest linked.
        camps = conn.execute("SELECT id, name, token, status, starts_at, ends_at, updated_at FROM campaigns "
                             "WHERE selection_id = ? OR id IN (SELECT campaign_id FROM campaign_selections WHERE selection_id = ?) "
                             "ORDER BY created_at", (sid, sid)).fetchall()
        changes = conn.execute("SELECT at, by_name, added, removed FROM quote_changes WHERE selection_id = ? "
                               "ORDER BY at DESC, id DESC LIMIT 8", (sid,)).fetchall()
    q = dict(q) if q is not None else {}
    req_at = q.get("requested_at") or (legacy[1] if legacy else None)
    req_by = q.get("requested_by") or (legacy[2] if legacy else None)
    ready_at, approved_at = q.get("ready_at"), q.get("approved_at")
    live = [k for k in camps if k["status"] == "live"]
    ended = [k for k in camps if k["status"] == "ended"]
    if live:
        key = "live"
    elif ended:
        key = "completed"
    elif approved_at:
        key = "approved"
    elif ready_at:
        key = "ready"
    elif req_at:
        key = "requested"
    else:
        key = "draft"
    shown = (live or ended or [None])[0]
    live_at = q.get("live_at") or ((shown["starts_at"] or shown["updated_at"]) if shown is not None else None)
    ended_at = q.get("ended_at") or (((ended[0]["ends_at"] or ended[0]["updated_at"]) if ended else None))
    owner = _owner_name(_field(sel, "code_id"))
    origin = _field(sel, "origin") or "admin"
    return {
        "key": key, "label": LABEL[key],
        "created_at": _field(sel, "created_at"), "created_by": (owner or "You") if origin == "client" else "HelloVoice",
        "requested_at": req_at, "requested_by": req_by,
        "ready_at": ready_at, "ready_by": q.get("ready_by"), "note": q.get("ready_note") or "", "link": q.get("ready_link") or "",
        "approved_at": approved_at, "approved_by": q.get("approved_by"),
        "live_at": live_at if key in ("live", "completed") else None,
        "ended_at": ended_at if key == "completed" else None,
        "campaign": ({"name": shown["name"], "token": shown["token"], "status": shown["status"]} if shown is not None else None),
        "campaigns": [{"id": k["id"], "name": k["name"], "token": k["token"], "status": k["status"]} for k in camps],
        "changes": [{"at": c["at"], "by": c["by_name"] or "", "added": c["added"], "removed": c["removed"]} for c in changes],
        "changed_after_ready": bool(ready_at and any(c["at"] >= ready_at for c in changes)),
    }


def chip(sel):
    k = state_of(sel)["key"]
    return {"key": k, "label": LABEL[k]}


def _steps(st, role):
    """The timeline: every step, with a date and who did it once it happened."""
    order = [
        ("draft", "Draft", st["created_at"], st["created_by"], ""),
        ("requested", "Quote requested", st["requested_at"], st["requested_by"], ""),
        ("ready", "Quote ready", st["ready_at"], st["ready_by"] or "HelloVoice", st["note"]),
        ("approved", "Approved", st["approved_at"], st["approved_by"], ""),
        ("live", "Campaign live", st["live_at"], "HelloVoice" if st["live_at"] else None, ""),
        ("completed", "Completed", st["ended_at"], "HelloVoice" if st["ended_at"] else None, ""),
    ]
    here = STATES.index(st["key"])
    out = []
    for i, (key, label, at, by, note) in enumerate(order):
        # A step is done when the selection is past it, or it has a date; the current one is marked.
        state = "current" if i == here else ("done" if (i < here or at) else "todo")
        out.append({"key": key, "label": label, "at": at, "by": by or "", "state": state, "note": note})
    return out


def _hint(st, role, owner):
    k = st["key"]
    if k == "draft":
        return "Edit freely. When it is ready, request a quote and your account manager prices it."
    if k == "requested":
        return "HelloVoice is preparing your quote, usually within one working day. You can still change the creators."
    if k == "ready":
        return ("Your quote is ready. Approve it to start setting up the campaign." if role == "owner"
                else "Your quote is ready. %s approves it." % (owner or "The person who owns this selection"))
    if k == "approved":
        return "Approved. HelloVoice is setting up the campaign."
    if k == "live":
        return "The campaign is live. Its report refreshes every 24 hours."
    return "The campaign has ended and the final report is ready."


def client_payload(sel, role="viewer"):
    """What a client may read. ``role`` is selection_role(): owner, viewer or admin. Never a price,
    cost or margin: only the note and link the account manager chose to attach."""
    st = state_of(sel)
    owner = _owner_name(_field(sel, "code_id"))
    editable = role in ("owner", "admin")
    return {
        "key": st["key"], "label": st["label"], "role": role,
        "steps": _steps(st, role),
        "hint": _hint(st, role, owner),
        "note": st["note"] if st["key"] in ("ready", "approved", "live", "completed") else "",
        "link": st["link"] if st["key"] in ("ready", "approved", "live", "completed") else "",
        "can_approve": role == "owner" and st["key"] == "ready",
        # Editing is allowed; while a quote exists it updates it and the page says so.
        "warn": WARNING if (editable and st["key"] in ACTIVE) else "",
        "changes": st["changes"][:5] if st["key"] in ACTIVE + ("live", "completed") else [],
        "campaign": ({"name": st["campaign"]["name"], "token": st["campaign"]["token"]}
                     if st["campaign"] and st["campaign"]["status"] in ("live", "ended") else None),
        "owner": owner or "",
    }


def admin_payload(sel):
    st = state_of(sel)
    out = client_payload(sel, "admin")
    out.update({"ready_at": st["ready_at"], "approved_at": st["approved_at"], "requested_at": st["requested_at"],
                "campaigns": st["campaigns"], "changed_after_ready": st["changed_after_ready"],
                "can_create_campaign": st["key"] != "draft",
                "can_mark_ready": st["key"] in ("draft", "requested", "ready"),
                "can_withdraw": st["key"] == "ready"})
    return out


def summary_line(sel):
    """One plain sentence for Helvi's context."""
    st = state_of(sel)
    k = st["key"]
    extra = {"requested": " HelloVoice has not marked the quote ready yet.",
             "ready": " The owner has not approved it yet.",
             "approved": " HelloVoice is setting up the campaign.",
             "live": " The campaign is live.", "completed": " The campaign has ended."}.get(k, "")
    return "Quote status: %s.%s Never quote prices; the account manager's note is the only price information." % (LABEL[k], extra)


# -------------------------------------------------------------- the writes --

def _upsert(conn, sid, **cols):
    if _row(conn, sid) is None:
        conn.execute("INSERT INTO selection_quote (selection_id) VALUES (?)", (sid,))
    conn.execute("UPDATE selection_quote SET " + ", ".join(c + " = ?" for c in cols) + " WHERE selection_id = ?",
                 list(cols.values()) + [sid])


def _bell(sel, kind, title, rest="", body="", exclude_user=None, ref=None):
    import inbox
    if not _field(sel, "code_id"):
        return 0
    users = inbox.for_codes([sel["code_id"]], exclude_user=exclude_user)
    return inbox.emit(users, kind, title, rest=rest, body=body, href="selection/#s=" + sel["token"],
                      ref=ref, once=bool(ref))


def mark_requested(sel, request_id=None, by_name=None, by_user=None):
    """The owner sent the selection for a quote. A quote that was ready goes back to requested (they
    asked again); an approved one stays approved."""
    sid = sel["id"]
    with db.connect() as conn:
        cols = {"requested_at": db.now(), "requested_by": (by_name or None), "request_id": request_id}
        q = _row(conn, sid)
        if q is not None and q["ready_at"] and not q["approved_at"]:
            cols.update(ready_at=None, ready_by=None, ready_note=None, ready_link=None)
        _upsert(conn, sid, **cols)
    _bell(sel, "quote_requested", "Quote requested:", " " + sel["name"],
          "%s asked HelloVoice for a quote." % (by_name or "A colleague"), exclude_user=by_user)


def _clean_link(link):
    link = (link or "").strip()
    if not link:
        return "", None
    if len(link) > LINK_MAX or not re.match(r"^https://[^\s/]+\.[^\s]+$", link):
        return "", "link"
    return link, None


def set_ready(sel, note="", link="", by_name="HelloVoice"):
    """HelloVoice marks the quote ready. Returns (state key, error)."""
    st = state_of(sel)
    if st["key"] not in ("draft", "requested", "ready"):
        return st["key"], "locked"
    link, bad = _clean_link(link)
    if bad:
        return st["key"], "link"
    note = " ".join(str(note or "").split())[:NOTE_MAX]
    with db.connect() as conn:
        _upsert(conn, sel["id"], ready_at=db.now(), ready_by=(by_name or "HelloVoice")[:80],
                ready_note=note or None, ready_link=link or None)
    _bell(sel, "quote_ready", "Your quote is ready:", " " + sel["name"],
          note or "Open the selection to read it and approve.", ref="ready:%d:%d" % (sel["id"], db.now()))
    return "ready", None


def withdraw_ready(sel):
    st = state_of(sel)
    if st["key"] != "ready":
        return st["key"], "locked"
    with db.connect() as conn:
        _upsert(conn, sel["id"], ready_at=None, ready_by=None, ready_note=None, ready_link=None)
    return state_of(sel)["key"], None


def approve(sel, user_id, name, kam=None, link=None):
    """The owner approves the ready quote. Returns (state key, error). Idempotent."""
    st = state_of(sel)
    if st["key"] in ("approved", "live", "completed") and st["approved_at"]:
        return st["key"], None
    if st["key"] != "ready":
        return st["key"], "not_ready"
    with db.connect() as conn:
        _upsert(conn, sel["id"], approved_at=db.now(), approved_by=(name or "Client")[:80], approved_by_user=user_id)
    _bell(sel, "quote_approved", "Quote approved:", " " + sel["name"],
          "%s approved it. HelloVoice will set up the campaign." % (name or "The owner"), exclude_user=user_id)
    import notify
    notify.send("quote_approved", ["%s approved the quote for “%s”." % (name or "A client", sel["name"]),
                                   "Next: create the campaign from the selection."], kam=kam, link=link)
    return "approved", None


# ---------------------------------------------------- edits after a request --

_pending = {}
_lock = threading.Lock()


def on_client_edit(sel, old_codes, new_codes, user=None, link=None):
    """The owner changed the creators of a selection that already has a quote. Recorded in the
    timeline and told to the account manager (one email per burst of edits). Returns True when the
    change touched a live quote, so the caller can say "This updates your quote request"."""
    old, new = set(old_codes or ()), set(new_codes or ())
    if old == new:
        return False
    if state_of(sel)["key"] not in ACTIVE:
        return False
    added, removed = len(new - old), len(old - new)
    who = (user["name"] if user is not None and user["name"] else None) or "The client"
    with db.connect() as conn:
        conn.execute("INSERT INTO quote_changes (selection_id, at, by_name, added, removed) VALUES (?,?,?,?,?)",
                     (sel["id"], db.now(), who, added, removed))
    kam = user["kam"] if user is not None and "kam" in user.keys() else None
    company = (user["company"] if user is not None and "company" in user.keys() else None) or ""
    with _lock:
        item = _pending.get(sel["id"])
        if item:
            item["added"] += added
            item["removed"] += removed
            return True
        _pending[sel["id"]] = {"added": added, "removed": removed}

    def flush():
        with _lock:
            item = _pending.pop(sel["id"], None)
        if not item:
            return
        import notify
        bits = []
        if item["added"]:
            bits.append("%d added" % item["added"])
        if item["removed"]:
            bits.append("%d removed" % item["removed"])
        notify.send("quote_changed",
                    ["%s%s changed “%s” after asking for a quote: %s." % (who, (", " + company) if company else "", sel["name"],
                                                                         ", ".join(bits) or "creators changed"),
                     "The quote may need updating."], kam=kam, link=link)

    if NOTIFY_DELAY <= 0:
        flush()
    else:
        t = threading.Timer(NOTIFY_DELAY, flush)
        t.daemon = True
        t.start()
    return True


# ---------------------------------------------------------- campaign hooks --

def _campaign_status(cid, was, now_):
    """A campaign linked to a selection went live or ended: remember when, and ring the selection's
    owner (and team) if the campaign was filed under a different client code."""
    k = db.campaign(cid)
    if k is None or not k["selection_id"]:
        return
    sel = db.selection(k["selection_id"])
    if sel is None:
        return
    with db.connect() as conn:
        if now_ == "live":
            _upsert(conn, sel["id"], live_at=db.now(), ended_at=None)
        elif now_ == "ended":
            _upsert(conn, sel["id"], ended_at=db.now())
    if sel["code_id"] and sel["code_id"] != k["code_id"]:
        if now_ == "live":
            _bell(sel, "camp_live", k["name"] + " is live", body="Your selection is now Campaign live.", ref="live:%d" % cid)
        elif now_ == "ended":
            _bell(sel, "camp_final", "Final report ready:", " " + k["name"], "The campaign has ended and every result is in.",
                  ref="final:%d" % cid)
