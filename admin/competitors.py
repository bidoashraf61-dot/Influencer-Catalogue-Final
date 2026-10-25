"""The competitors a tenant names for themselves (Helvi Intelligence at `manage`).

A competitor is a brand the client wants watched: a name and the handles it posts under.
It belongs to the tenant — the `codes` row — not to a selection, because the same rival
matters across every campaign they run.

A collection run (2026-10-25) reads the competitor's own recent posts through Apify and
files the creators in them as an evidence pack: see `collect()` in tenant_api.py and
`evidence.ingest_competitor_posts`. It finds the creators a brand posted with, tagged or
credited — not every paid post ever made for them, which is still what a full study is for.
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
        have = {r["name"] for r in conn.execute("PRAGMA table_info(competitors)")}
        for col, ddl in (("pack_id", "INTEGER"), ("last_run_at", "INTEGER"), ("last_note", "TEXT")):
            if col not in have:
                conn.execute("ALTER TABLE competitors ADD COLUMN %s %s" % (col, ddl))
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


PROFILE = {"Instagram": "https://www.instagram.com/%s/", "TikTok": "https://www.tiktok.com/@%s",
           "Snapchat": "https://www.snapchat.com/add/%s", "YouTube": "https://www.youtube.com/@%s"}


def profile_url(platform, handle):
    return (PROFILE.get(platform) or "%s") % str(handle or "").lstrip("@")


def get(cid):
    with _conn() as conn:
        r = conn.execute("SELECT * FROM competitors WHERE id = ?", (int(cid),)).fetchone()
    if r is None:
        return None
    return {"id": r["id"], "code_id": r["code_id"], "name": r["name"],
            "handles": json.loads(r["handles"] or "{}"), "note": r["note"] or "",
            "pack_id": r["pack_id"] if "pack_id" in r.keys() else None,
            "last_run_at": r["last_run_at"] if "last_run_at" in r.keys() else None,
            "last_note": r["last_note"] if "last_note" in r.keys() else None}


def mark_run(cid, pack_id=None, note=None):
    """note carries why a run found nothing — a wrong handle is the usual reason, and the
    tenant is the only one who can fix it, so they are told rather than left guessing."""
    with _conn() as conn:
        conn.execute("UPDATE competitors SET last_run_at = ?, last_note = ? WHERE id = ?",
                     (db.now(), note, int(cid)))
        if pack_id is not None:
            conn.execute("UPDATE competitors SET pack_id = ? WHERE id = ?", (int(pack_id), int(cid)))


def _month_start():
    import time
    t = time.gmtime()
    return int(time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, 0))) - time.timezone


def _my_sources(code_id):
    return ["competitor:%d" % c["id"] for c in listing(code_id)]


def spend_month(code_id):
    """What this tenant's collection runs have cost since the 1st, in dollars. Read from the
    runs themselves — Apify's own figure once a run finishes — so it is the real bill, not an
    estimate that drifts."""
    srcs = _my_sources(code_id)
    if not srcs:
        return 0.0
    with _conn() as conn:
        r = conn.execute(
            "SELECT COALESCE(SUM(r.cost), 0) c FROM api_runs r JOIN api_jobs j ON j.id = r.job_id "
            "WHERE r.started_at >= ? AND j.source IN (%s)" % ",".join("?" * len(srcs)),
            [_month_start()] + srcs).fetchone()
    return round(float(r["c"] or 0), 4)


def runs_today(code_id):
    """Collection runs started for this tenant since midnight — what the captures-a-day cap counts."""
    import time
    t = time.gmtime()
    midnight = int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, 0))) - time.timezone
    ids = [str(c["id"]) for c in listing(code_id)]
    if not ids:
        return 0
    srcs = ["competitor:" + i for i in ids]
    with _conn() as conn:
        r = conn.execute(
            "SELECT COUNT(*) n FROM api_runs r JOIN api_jobs j ON j.id = r.job_id "
            "WHERE r.started_at >= ? AND j.source IN (%s)" % ",".join("?" * len(srcs)),
            [midnight] + srcs).fetchone()
    return r["n"] if r else 0


def listing(code_id):
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM competitors WHERE code_id = ? ORDER BY name COLLATE NOCASE",
                            (int(code_id),)).fetchall()
    return [{"id": r["id"], "name": r["name"], "handles": json.loads(r["handles"] or "{}"),
             "note": r["note"] or "", "added_by": r["added_by"] or "",
             "pack_id": r["pack_id"] if "pack_id" in r.keys() else None,
             "last_run_at": r["last_run_at"] if "last_run_at" in r.keys() else None,
             "last_note": r["last_note"] if "last_note" in r.keys() else None} for r in rows]


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
