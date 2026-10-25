"""The competitors a tenant names for themselves (Helvi Intelligence at `manage`).

A competitor is a brand the client wants watched: a name and the handles it posts under.
It belongs to the tenant — the `codes` row — not to a selection, because the same rival
matters across every campaign they run.

What this does NOT do yet: collect anything. An evidence pack is still built from a
competitor study and uploaded in the admin, so naming a competitor here tells HelloVoice
what to go and study. The collection run that would fill a pack straight from these
handles is the next slice, and it is the thing the captures-a-day cap is waiting for.
"""
import json
import re

import db

PLATFORMS = ("Instagram", "TikTok", "Snapchat", "YouTube")
MAX_PER_TENANT = 40
HANDLE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS competitors (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code_id    INTEGER NOT NULL,          -- the tenant who named them
    name       TEXT NOT NULL,
    handles    TEXT NOT NULL,             -- JSON {"Instagram": "nivea_arabia", ...}
    note       TEXT,
    added_by   TEXT,                      -- the client's email, or an admin's
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS competitors_code ON competitors(code_id);
"""

_ready = False


def init():
    global _ready
    with db.connect() as conn:
        conn.executescript(SCHEMA)
    _ready = True


def _conn():
    if not _ready:
        init()
    return db.connect()


def clean_handles(raw):
    """{platform: handle} keeping only the platforms we know and handles that look like one.
    A pasted profile link is accepted and reduced to its handle, since that is what people
    have to hand."""
    out = {}
    for p, v in (raw or {}).items():
        if p not in PLATFORMS:
            continue
        v = str(v or "").strip()
        if not v:
            continue
        if "/" in v:                                  # a link: take the last useful part
            bits = [b for b in re.split(r"[/?#]", v) if b and "." not in b and b not in ("https:", "http:")]
            v = bits[-1] if bits else v
        v = v.lstrip("@")
        if HANDLE.match(v):
            out[p] = v
    return out


def listing(code_id):
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM competitors WHERE code_id = ? ORDER BY name COLLATE NOCASE",
                            (int(code_id),)).fetchall()
    return [{"id": r["id"], "name": r["name"], "handles": json.loads(r["handles"] or "{}"),
             "note": r["note"] or "", "added_by": r["added_by"] or ""} for r in rows]


def count(code_id):
    with _conn() as conn:
        r = conn.execute("SELECT COUNT(*) n FROM competitors WHERE code_id = ?", (int(code_id),)).fetchone()
    return r["n"] if r else 0


def add(code_id, name, handles, note="", by=""):
    name = " ".join(str(name or "").split())[:80]
    handles = clean_handles(handles)
    if not name:
        return None, "Give the competitor a name."
    if not handles:
        return None, "Add at least one handle: %s." % ", ".join(PLATFORMS)
    if count(code_id) >= MAX_PER_TENANT:
        return None, "That is as many competitors as one account can hold."
    with _conn() as conn:
        same = conn.execute("SELECT id FROM competitors WHERE code_id = ? AND lower(name) = lower(?)",
                            (int(code_id), name)).fetchone()
        if same:
            return None, "That competitor is already on your list."
        cur = conn.execute("INSERT INTO competitors (code_id, name, handles, note, added_by, created_at, updated_at) "
                           "VALUES (?,?,?,?,?,?,?)",
                           (int(code_id), name, json.dumps(handles), (note or "").strip()[:300] or None,
                            by or "", db.now(), db.now()))
    return cur.lastrowid, None


def edit(code_id, cid, name=None, handles=None, note=None):
    """Only ever within the tenant's own list: code_id is in the WHERE, not trusted from the body."""
    with _conn() as conn:
        row = conn.execute("SELECT * FROM competitors WHERE id = ? AND code_id = ?",
                           (int(cid), int(code_id))).fetchone()
        if row is None:
            return False, "That competitor is gone."
        new_name = " ".join(str(name).split())[:80] if name is not None else row["name"]
        new_handles = clean_handles(handles) if handles is not None else json.loads(row["handles"] or "{}")
        if not new_name:
            return False, "Give the competitor a name."
        if not new_handles:
            return False, "Keep at least one handle."
        conn.execute("UPDATE competitors SET name = ?, handles = ?, note = ?, updated_at = ? WHERE id = ? AND code_id = ?",
                     (new_name, json.dumps(new_handles),
                      (note if note is not None else row["note"] or "").strip()[:300] or None,
                      db.now(), int(cid), int(code_id)))
    return True, None


def remove(code_id, cid):
    with _conn() as conn:
        conn.execute("DELETE FROM competitors WHERE id = ? AND code_id = ?", (int(cid), int(code_id)))
    return True


def all_named():
    """Every tenant's competitors, for the admin: {code_id: [rows]}. What HelloVoice has been
    asked to study, in one read."""
    out = {}
    with _conn() as conn:
        for r in conn.execute("SELECT * FROM competitors ORDER BY code_id, name COLLATE NOCASE"):
            out.setdefault(r["code_id"], []).append(
                {"id": r["id"], "name": r["name"], "handles": json.loads(r["handles"] or "{}"),
                 "note": r["note"] or "", "added_by": r["added_by"] or ""})
    return out
