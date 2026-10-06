"""History and undo: every admin change can be taken back.

Each tracked action stores a complete snapshot of the thing it touched, taken
just before and just after — a creator's row, a selection, a campaign with
every row that hangs off it (its creators, links, clicks, posts, daily
snapshots, insights), an access code with its devices, the tier table. Undo
puts the "before" snapshot back exactly. An undo is itself an action in the
history, so undoing it is redo.

Snapshots, not diffs: restoring a snapshot cannot drift from what was there,
and it works the same for an edit, a delete or a create (whose "before" is
nothing, so undoing it removes the thing again).

Kept 90 days. Deleted creators' photographs are moved to admin/trash/ rather
than erased, and come back with the creator.
"""

import json
import shutil
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import db

KEEP_DAYS = 90
TRASH = Path(__file__).resolve().parent / "trash"
PHOTO_DIR = None                # set by the server: site/assets/catalogue

# Who is acting, for the request being served. Threads, because the server
# handles requests on several at once.
_actor = threading.local()


def set_actor(who):
    _actor.who = who


def actor():
    return getattr(_actor, "who", None) or "system"


SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
  id         INTEGER PRIMARY KEY,
  at         INTEGER NOT NULL,
  who        TEXT,
  action     TEXT NOT NULL,        -- created | edited | deleted | imported | undo
  entity     TEXT NOT NULL,        -- creator | selection | campaign | code | tiers | roster
  key        TEXT,
  label      TEXT,
  before     TEXT,                 -- JSON snapshot, NULL = did not exist
  after      TEXT,
  undone_at  INTEGER,
  undone_by  TEXT,
  undo_of    INTEGER
);
CREATE INDEX IF NOT EXISTS history_at  ON history(at DESC);
CREATE INDEX IF NOT EXISTS history_key ON history(entity, key);
"""


def init():
    TRASH.mkdir(exist_ok=True)
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM history WHERE at < ?", (db.now() - KEEP_DAYS * 86400,))


# ------------------------------------------------------------- snapshots --

def _rows(conn, table, where, args):
    return [{k: r[k] for k in r.keys()}
            for r in conn.execute("SELECT * FROM %s WHERE %s" % (table, where), args).fetchall()]


def _tables_with(conn, column):
    out = []
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(%s)" % name)}
        if column in cols:
            out.append(name)
    return out


def snapshot(entity, key, conn=None):
    """The thing as it is now, with everything that belongs to it, or None
    when it does not exist."""
    if conn is None:
        with db.connect() as own:
            return snapshot(entity, key, own)
    if key is None:
        return None
    if entity == "creator":
        rows = _rows(conn, "creators", "code = ?", (key,))
        return {"creators": rows} if rows else None
    if entity == "selection":
        rows = _rows(conn, "selections", "id = ?", (int(key),))
        return {"selections": rows} if rows else None
    if entity == "code":
        rows = _rows(conn, "codes", "id = ?", (int(key),))
        if not rows:
            return None
        return {"codes": rows, "code_devices": _rows(conn, "code_devices", "code_id = ?", (int(key),))}
    if entity == "campaign":
        rows = _rows(conn, "campaigns", "id = ?", (int(key),))
        if not rows:
            return None
        out = {"campaigns": rows}
        for t in _tables_with(conn, "campaign_id"):
            if t != "campaigns":
                out[t] = _rows(conn, t, "campaign_id = ?", (int(key),))
        ids = [r["id"] for r in out.get("content", [])]
        if ids:
            out["snapshots"] = _rows(conn, "snapshots", "content_id IN (%s)" % ",".join("?" * len(ids)), ids)
        return out
    if entity == "tiers":
        return {"tiers": _rows(conn, "tiers", "1", ()), "creators": _rows(conn, "creators", "1", ())}
    if entity == "roster":
        return {"creators": _rows(conn, "creators", "1", ())}
    raise ValueError("unknown entity " + entity)


def _clear(conn, entity, key):
    """Remove the thing's current state, so a snapshot can be laid back."""
    if entity == "creator":
        conn.execute("DELETE FROM creators WHERE code = ?", (key,))
    elif entity == "selection":
        conn.execute("DELETE FROM selections WHERE id = ?", (int(key),))
    elif entity == "code":
        conn.execute("DELETE FROM code_devices WHERE code_id = ?", (int(key),))
        conn.execute("DELETE FROM codes WHERE id = ?", (int(key),))
    elif entity == "campaign":
        conn.execute("DELETE FROM campaigns WHERE id = ?", (int(key),))   # cascades
    elif entity == "tiers":
        conn.execute("DELETE FROM tiers")
        conn.execute("DELETE FROM creators")
    elif entity == "roster":
        conn.execute("DELETE FROM creators")


# Parents before children, so foreign keys are satisfied as rows go back.
_ORDER = ["campaigns", "codes", "tiers", "creators", "selections", "campaign_creators",
          "links", "content", "snapshots", "insights", "clicks", "code_devices"]


def _lay(conn, snap):
    tables = sorted(snap, key=lambda t: _ORDER.index(t) if t in _ORDER else len(_ORDER))
    for t in tables:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(%s)" % t)}
        for row in snap[t]:
            keep = [c for c in row if c in cols]
            conn.execute("INSERT OR REPLACE INTO %s (%s) VALUES (%s)" % (
                t, ",".join(keep), ",".join("?" * len(keep))), [row[c] for c in keep])


def _photos(snap):
    return [str(r.get("photo") or "").split("?")[0]
            for r in (snap or {}).get("creators", []) if r.get("photo")]


def trash_photo(name):
    """Move a photo out of the public folder into admin/trash/."""
    if not name or PHOTO_DIR is None:
        return
    src = Path(PHOTO_DIR) / Path(name).name
    if src.is_file():
        TRASH.mkdir(exist_ok=True)
        shutil.move(str(src), str(TRASH / src.name))


def _unbin_photos(names):
    for n in names:
        src, dst = TRASH / Path(n).name, Path(PHOTO_DIR or ".") / Path(n).name
        if src.is_file() and not dst.exists():
            shutil.move(str(src), str(dst))


# ---------------------------------------------------------------- record --

def record(action, entity, key, label, before, after, conn=None, undo_of=None):
    if before == after:
        return None
    if conn is None:
        with db.connect() as own:
            return record(action, entity, key, label, before, after, own, undo_of)
    cur = conn.execute(
        "INSERT INTO history (at,who,action,entity,key,label,before,after,undo_of) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (db.now(), actor(), action, entity, None if key is None else str(key), label,
         json.dumps(before, ensure_ascii=False) if before is not None else None,
         json.dumps(after, ensure_ascii=False) if after is not None else None, undo_of))
    return cur.lastrowid


@contextmanager
def tracked(entity, key, label, action=None):
    """Snapshot before, run the block, snapshot after, record the change.

        with history.tracked("creator", code, "Edited " + code) as t:
            ... write ...
            t["key"] = new_code      # when the key is only known afterwards

    Nothing is recorded if nothing changed, or if the block raises."""
    box = {"key": key, "label": label, "id": None}
    before = snapshot(entity, key) if key is not None else None
    yield box
    after = snapshot(entity, box["key"]) if box["key"] is not None else None
    act = action or ("created" if before is None else "deleted" if after is None else "edited")
    box["id"] = record(act, entity, box["key"], box["label"], before, after)


# ------------------------------------------------------------------ undo --

def entry(hid):
    with db.connect() as conn:
        return conn.execute("SELECT * FROM history WHERE id = ?", (hid,)).fetchone()


def later_changes(row):
    """Actions on the same thing after this one that are still in force."""
    with db.connect() as conn:
        return conn.execute(
            "SELECT * FROM history WHERE entity = ? AND key IS ? AND id > ? AND undone_at IS NULL "
            "AND action != 'undo' ORDER BY id", (row["entity"], row["key"], row["id"])).fetchall()


def undo(hid):
    """Put the thing back as it was before action `hid`. Returns (ok, message)."""
    row = entry(hid)
    if row is None:
        return False, "That entry no longer exists."
    if row["undone_at"]:
        return False, "That was already undone."
    before = json.loads(row["before"]) if row["before"] else None
    with db.connect() as conn:
        now_snap = snapshot(row["entity"], row["key"], conn)
        _clear(conn, row["entity"], row["key"])
        if before:
            _lay(conn, before)
        conn.execute("UPDATE history SET undone_at = ?, undone_by = ? WHERE id = ?",
                     (db.now(), actor(), hid))
        record("undo", row["entity"], row["key"], "Undid: " + (row["label"] or row["action"]),
               now_snap, before, conn, undo_of=hid)
    # Photos follow their creators: back from the bin, or into it.
    if before:
        _unbin_photos(_photos(before))
    gone = set(_photos(now_snap)) - set(_photos(before))
    for n in gone:
        trash_photo(n)
    return True, "Undone: " + (row["label"] or row["action"]) + "."


def listing(kind=None, q=None, limit=300):
    where, args = ["1"], []
    if kind == "trash":
        where.append("action = 'deleted' AND undone_at IS NULL")
    elif kind:
        where.append("entity = ?"); args.append(kind)
    if q:
        where.append("(lower(label) LIKE ? OR lower(key) LIKE ?)")
        args += ["%" + q.lower() + "%"] * 2
    with db.connect() as conn:
        return conn.execute(
            "SELECT id, at, who, action, entity, key, label, undone_at, undone_by, undo_of "
            "FROM history WHERE " + " AND ".join(where) + " ORDER BY id DESC LIMIT ?",
            args + [limit]).fetchall()
