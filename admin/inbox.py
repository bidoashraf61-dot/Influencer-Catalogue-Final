"""The client's notification bell: what HelloVoice did for them, kept per account.

In-portal only. Nothing here sends a client an email (the sign-in code is the only
client email); the team's own emails stay in notify.py.

    emit(user_ids, kind, title, ...)     store one notification per account
    for_codes(code_ids)                   the active accounts behind access-code rows
    feed(user, limit, bell=True)          newest first; bell=True honours the toggles
    unread(user)                          the dot on the bell
    mark_read(user, ids=None)             one, several or all
    prefs(user) / set_prefs(user, ...)    which groups show in the bell

Groups are what the client switches on and off: analysis, selections, campaigns,
account, and ideas (HelloVoice suggestions, off by default). Every notification is
stored whatever the toggles say, so turning a group back on shows its history.
"""
import json
import time

import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    grp TEXT NOT NULL,
    title TEXT NOT NULL,          -- the bold lead
    rest TEXT,                    -- plain words after it ("in Ramadan 2027")
    body TEXT,                    -- the second line
    href TEXT,                    -- relative to the site root
    ref TEXT,                     -- de-duplication key
    meta TEXT,                    -- JSON, for bundling ("approved 2 creators")
    at INTEGER NOT NULL,
    read_at INTEGER
);
CREATE INDEX IF NOT EXISTS notif_user ON notifications(user_id, id);
CREATE INDEX IF NOT EXISTS notif_ref ON notifications(user_id, kind, ref);
"""

# kind -> group. The group is what a toggle controls.
KINDS = {
    "analysis_ready": "analysis",
    "sel_feedback": "selections", "sel_shared": "selections", "sel_updated": "selections", "unavailable": "selections",
    "camp_live": "campaigns", "camp_report": "campaigns", "camp_final": "campaigns",
    "camp_weekly": "campaigns", "camp_next": "campaigns",
    "credits_low": "account", "credits_monthly": "account", "credits_added": "account", "colleague": "account",
    "idea": "ideas",
}
GROUPS = ("analysis", "selections", "campaigns", "account", "ideas")
DEFAULTS = {"analysis": True, "selections": True, "campaigns": True, "account": True, "ideas": False}
KEEP = 400                         # per account; older ones are dropped


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)
    db.on("campaign_status", _campaign_status)
    db.on("campaign_content", _campaign_content)


# ------------------------------------------------------------------ prefs --

def prefs(user):
    raw = user["notify"] if user is not None and "notify" in user.keys() else None
    try:
        got = json.loads(raw or "{}")
    except ValueError:
        got = {}
    return {g: bool(got.get(g, DEFAULTS[g])) for g in GROUPS}


def set_prefs(user, changes):
    clean = {g: bool(changes[g]) for g in GROUPS if g in (changes or {})}
    merged = dict(prefs(user), **clean)
    with db.connect() as conn:
        conn.execute("UPDATE users SET notify = ? WHERE id = ?", (json.dumps(merged), user["id"]))
    return merged


# -------------------------------------------------------------- recipients --

def for_codes(code_ids, team=True, exclude_user=None):
    """Active account ids behind these access-code rows, with their colleagues when
    team sharing is on (they see the same selections and campaigns). Guests and the
    admin preview have no account and so no bell."""
    import portal
    ids = set()
    for cid in code_ids or ():
        if cid is None:
            continue
        ids |= portal.team_codes(cid) if team else {cid}
    if not ids:
        return []
    with db.connect() as conn:
        rows = conn.execute("SELECT id FROM users WHERE status = 'active' AND deleted_at IS NULL AND code_id IN (%s)"
                            % ",".join("?" * len(ids)), list(ids)).fetchall()
    return [r["id"] for r in rows if r["id"] != exclude_user]


# -------------------------------------------------------------------- emit --

def emit(user_ids, kind, title, rest="", body="", href="", ref=None, meta=None, once=False, conn=None):
    """Store a notification for each account. ``ref`` with ``once`` skips accounts that
    already have this kind+ref (e.g. one "report updated" a day). Pass ``conn`` to write
    inside a transaction that is already open. Never raises: a notification must not
    break the action that caused it."""
    if kind not in KINDS:
        return 0
    if conn is None:
        try:
            with db.connect() as own:
                return emit(user_ids, kind, title, rest, body, href, ref, meta, once, own)
        except Exception:
            return 0
    n = 0
    try:
        for uid in dict.fromkeys(u for u in (user_ids or ()) if u):
            if once and ref and conn.execute("SELECT 1 FROM notifications WHERE user_id = ? AND kind = ? AND ref = ?",
                                             (uid, kind, ref)).fetchone():
                continue
            conn.execute("INSERT INTO notifications (user_id, kind, grp, title, rest, body, href, ref, meta, at) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (uid, kind, KINDS[kind], str(title)[:200], str(rest or "")[:200], str(body or "")[:300],
                          str(href or "")[:300], ref, json.dumps(meta) if meta else None, db.now()))
            conn.execute("DELETE FROM notifications WHERE user_id = ? AND id NOT IN "
                         "(SELECT id FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT ?)", (uid, uid, KEEP))
            n += 1
    except Exception:
        return n
    return n


def bundle(user_ids, kind, ref, window, build, meta_new):
    """Fold repeated events into one unread notification: the same ``ref`` within
    ``window`` seconds updates the last one instead of adding another. ``build(meta)``
    returns (title, rest, body, href) for the merged meta; ``meta_new(old)`` merges."""
    try:
        with db.connect() as conn:
            for uid in dict.fromkeys(u for u in (user_ids or ()) if u):
                r = conn.execute("SELECT id, meta FROM notifications WHERE user_id = ? AND kind = ? AND ref = ? "
                                 "AND read_at IS NULL AND at >= ? ORDER BY id DESC LIMIT 1",
                                 (uid, kind, ref, db.now() - window)).fetchone()
                old = json.loads(r["meta"] or "{}") if r else None
                meta = meta_new(old)
                title, rest, body, href = build(meta)
                if r:
                    conn.execute("UPDATE notifications SET title = ?, rest = ?, body = ?, href = ?, meta = ?, at = ? WHERE id = ?",
                                 (title[:200], (rest or "")[:200], (body or "")[:300], href or "", json.dumps(meta), db.now(), r["id"]))
                else:
                    conn.execute("INSERT INTO notifications (user_id, kind, grp, title, rest, body, href, ref, meta, at) "
                                 "VALUES (?,?,?,?,?,?,?,?,?,?)",
                                 (uid, kind, KINDS[kind], title[:200], (rest or "")[:200], (body or "")[:300], href or "",
                                  ref, json.dumps(meta), db.now()))
    except Exception:
        pass


# -------------------------------------------------------------------- read --

def _row(r):
    return {"id": r["id"], "kind": r["kind"], "group": r["grp"], "title": r["title"], "rest": r["rest"] or "",
            "body": r["body"] or "", "href": r["href"] or "", "at": r["at"], "unread": r["read_at"] is None}


def feed(user, limit=50, bell=True, group=None):
    on = [g for g, v in prefs(user).items() if v] if bell else list(GROUPS)
    if group:
        on = [g for g in on if g == group]
    if not on:
        return []
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM notifications WHERE user_id = ? AND grp IN (%s) ORDER BY id DESC LIMIT ?"
                            % ",".join("?" * len(on)), [user["id"]] + on + [int(limit)]).fetchall()
    return [_row(r) for r in rows]


def unread(user):
    on = [g for g, v in prefs(user).items() if v]
    if not on:
        return 0
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL AND grp IN (%s)"
                            % ",".join("?" * len(on)), [user["id"]] + on).fetchone()[0]


def counts(user):
    """{group: n} over the whole history, for the filter chips."""
    with db.connect() as conn:
        rows = conn.execute("SELECT grp, COUNT(*) n FROM notifications WHERE user_id = ? GROUP BY grp", (user["id"],)).fetchall()
    return {r["grp"]: r["n"] for r in rows}


def mark_read(user, ids=None):
    with db.connect() as conn:
        if ids:
            ids = [int(i) for i in ids if str(i).isdigit()][:200]
            if not ids:
                return 0
            return conn.execute("UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL AND id IN (%s)"
                                % ",".join("?" * len(ids)), [db.now(), user["id"]] + ids).rowcount
        return conn.execute("UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL",
                            (db.now(), user["id"])).rowcount


# ------------------------------------------------------- campaign events --

def _campaign_status(cid, was, now_):
    k = db.campaign(cid)
    if k is None or not k["code_id"]:
        return
    users = for_codes([k["code_id"]])
    href = "campaign/#t=" + k["token"]
    if now_ == "live":
        emit(users, "camp_live", k["name"] + " is live", body="The first posts are going up. The report refreshes every 24 hours.",
             href=href, ref="live:%d" % cid, once=True)
    elif now_ == "ended":
        emit(users, "camp_final", "Final report ready:", rest=" " + k["name"],
             body="The campaign has ended and every result is in.", href=href, ref="final:%d" % cid, once=True)


def _campaign_content(conn, cid):
    """New numbers on a live campaign: one "report updated" a day at most."""
    k = conn.execute("SELECT * FROM campaigns WHERE id = ?", (cid,)).fetchone()
    if k is None or not k["code_id"] or k["status"] != "live":
        return
    posts = conn.execute("SELECT COUNT(*) FROM content WHERE campaign_id = ? AND hidden = 0 AND section = 'campaign'",
                         (cid,)).fetchone()[0]
    bits = []
    if k["starts_at"] and k["ends_at"] and k["ends_at"] > k["starts_at"]:
        total = max(1, int(round((k["ends_at"] - k["starts_at"]) / 86400.0)))
        day = max(1, min(total, int((db.now() - k["starts_at"]) // 86400) + 1))
        bits.append("Day %d of %d" % (day, total))
    bits.append("%d post%s live" % (posts, "" if posts == 1 else "s"))
    emit(for_codes([k["code_id"]]), "camp_report", k["name"] + " report updated", body=" · ".join(bits),
         href="campaign/#t=" + k["token"], ref="report:%d:%s" % (cid, today()), once=True, conn=conn)


def today():
    return time.strftime("%Y-%m-%d", time.gmtime())
