"""Per-creator status on a selection: Under review, Approved, Rejected, Unavailable.

Every creator starts Under review. The selection's owner (the client it belongs to)
approves or rejects; colleagues who share it only look. HelloVoice can set any
status, and is the only one who can mark a creator Unavailable. Each change keeps
who made it and when; a rejection may carry a reason.

A change by HelloVoice rings the client's bell ("Feedback on your selection"); a
change by the client tells their account manager by email, bundled so a client
deciding twelve creators sends one email, not twelve.

    of(sel_id)                   {code: {...}} for the creators that have one
    set(sel, code, status, ...)  validate, store, notify; returns the row as the page shows it
    counts(sel, codes)           what the summary bar shows
"""
import json
import threading

import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS selection_status (
    selection_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'review',   -- review | approved | rejected | unavailable
    reason TEXT,                             -- price | audience | style | competitor | other
    note TEXT,                               -- the "other" words, or HelloVoice's note
    by_kind TEXT,                            -- client | hv
    by_name TEXT,
    at INTEGER,
    replacements TEXT,                       -- JSON [codes] Helvy suggested for this one
    PRIMARY KEY (selection_id, code)
);
"""

STATUSES = ("review", "approved", "rejected", "unavailable")
LABEL = {"review": "Under review", "approved": "Approved", "rejected": "Rejected", "unavailable": "Unavailable"}
REASONS = {"price": "Price", "audience": "Audience", "style": "Content style", "competitor": "Worked with a competitor",
           "other": "Other"}
EMAIL_DELAY = 300              # seconds a client's changes are gathered before one email goes


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)


def _row(r):
    return {"s": r["status"], "reason": r["reason"] or "", "note": r["note"] or "",
            "by": r["by_name"] or "", "hv": r["by_kind"] == "hv", "at": r["at"],
            "replacements": json.loads(r["replacements"] or "[]")}


def of(sel_id):
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM selection_status WHERE selection_id = ?", (sel_id,)).fetchall()
    return {r["code"]: _row(r) for r in rows}


def get(sel_id, code):
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM selection_status WHERE selection_id = ? AND code = ?", (sel_id, code)).fetchone()
    return _row(r) if r else None


def counts(codes, status_map, tiers):
    """The summary bar: creators, influencers, doctors and each status."""
    n = {"creators": len(codes), "influencers": 0, "doctors": 0}
    for s in STATUSES:
        n[s] = 0
    for c in codes:
        n[(status_map.get(c) or {}).get("s", "review")] += 1
        if str(tiers.get(c) or "").upper().startswith("HCP"):
            n["doctors"] += 1
        else:
            n["influencers"] += 1
    return n


def set_status(sel, code, status, by_kind, by_name, reason=None, note=None):
    """Store one change. Returns (row, error). The caller has checked who may do what."""
    if status not in STATUSES:
        return None, "status"
    if code not in json.loads(sel["codes"] or "[]"):
        return None, "not_in_selection"
    reason = reason if reason in REASONS else None
    if status != "rejected":
        reason = None
    note = " ".join(str(note or "").split())[:200] or None
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO selection_status (selection_id, code, status, reason, note, by_kind, by_name, at) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(selection_id, code) DO UPDATE SET status = excluded.status, reason = excluded.reason, "
            "note = excluded.note, by_kind = excluded.by_kind, by_name = excluded.by_name, at = excluded.at",
            (sel["id"], code, status, reason, note, by_kind, by_name, db.now()))
    return get(sel["id"], code), None


def set_reason(sel, code, reason, note):
    """The optional "why" on a rejection, added after the click."""
    reason = reason if reason in REASONS else None
    note = " ".join(str(note or "").split())[:200] or None
    with db.connect() as conn:
        conn.execute("UPDATE selection_status SET reason = ?, note = ? WHERE selection_id = ? AND code = ? AND status = 'rejected'",
                     (reason, note, sel["id"], code))
    return get(sel["id"], code)


def set_replacements(sel_id, code, codes):
    with db.connect() as conn:
        conn.execute("UPDATE selection_status SET replacements = ? WHERE selection_id = ? AND code = ?",
                     (json.dumps(list(codes)[:3]), sel_id, code))


# ------------------------------------------------------------ notifications --

def ring_client(sel, code, status, by_name, note=None):
    """HelloVoice changed a status: the client's bell, bundled per selection and status."""
    import inbox
    if not sel["code_id"]:
        return
    users = inbox.for_codes([sel["code_id"]])
    c = db.creator(code)
    who = (c["name"] if c else code) or code
    href = "selection/#s=" + sel["token"]
    if status == "unavailable":
        inbox.emit(users, "unavailable", "%s is no longer available" % who, rest=" for " + sel["name"],
                   body=note or "Booked in your campaign dates. Helvy can suggest a replacement.", href=href)
        return
    verb = {"approved": "approved", "rejected": "rejected", "review": "set back to Under review"}[status]
    first = (by_name or "HelloVoice").split()[0]

    def merge(old):
        names = list((old or {}).get("names") or [])
        if who not in names:
            names.append(who)
        return {"names": names, "note": note or (old or {}).get("note") or ""}

    def build(meta):
        names = meta["names"]
        lead = "HelloVoice %s %s" % (verb, names[0] if len(names) == 1 else "%d creators" % len(names))
        body = ("Note: " + meta["note"]) if meta.get("note") else "Marked by %s, your account manager" % first
        return lead, " in " + sel["name"], body, href

    inbox.bundle(users, "sel_feedback", "fb:%d:%s" % (sel["id"], status), 1800, build, merge)


_pending = {}
_lock = threading.Lock()


def tell_kam(sel, code, status, user, reason=None, note=None, delay=None):
    """The client changed a status: their KAM hears, in one email per burst of changes."""
    import notify
    c = db.creator(code)
    line = "%s (%s): %s%s" % ((c["name"] if c else code), code, LABEL[status],
                              (" — " + REASONS.get(reason, "") + ((": " + note) if note else "")) if status == "rejected" and (reason or note) else "")
    key = sel["id"]
    with _lock:
        item = _pending.get(key)
        if item:
            item["lines"].append(line)
            return
        _pending[key] = {"lines": [line]}

    def flush():
        with _lock:
            item = _pending.pop(key, None)
        if not item:
            return
        who = ((user["name"] or user["email"]) + (", " + user["company"] if user["company"] else "")) if user else "A client"
        notify.send("status", ["%s changed creators on their selection “%s”:" % (who, sel["name"])] + item["lines"],
                    kam=user["kam"] if user is not None and "kam" in user.keys() else None)

    wait = EMAIL_DELAY if delay is None else delay
    if wait <= 0:
        flush()
    else:
        t = threading.Timer(wait, flush)
        t.daemon = True
        t.start()
