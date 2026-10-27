"""Requests for more: a module, a role or a limit. Filed from the locked pages and the "Request
more" refusals, answered by HelloVoice in the Tenants inbox.

`detail` is a small JSON object saying exactly what was asked, so approving applies it without
anyone retyping a number:

    module   {"module": "helvi-track", "level": "manage"}
    role     {"module": "helvi-track", "role": "editor", "user_id": 12}
    limit    {"key": "campaigns_max", "value": 20}

The table is `module_requests`: `access_requests` already means "a client asks to open a
selection" and has its own screen under Clients.
"""
import json

import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS module_requests (
    id         INTEGER PRIMARY KEY,
    code_id    INTEGER NOT NULL,
    user_id    INTEGER,
    module     TEXT,
    kind       TEXT NOT NULL,             -- module | role | limit
    status     TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | declined
    note       TEXT,
    detail     TEXT,                      -- JSON, see the module docstring
    created_at INTEGER NOT NULL,
    decided_at INTEGER,
    decided_by TEXT,
    reply      TEXT
);
CREATE INDEX IF NOT EXISTS module_requests_status ON module_requests(status, created_at);
"""
KINDS = ("module", "role", "limit")
_ready = False


def _conn():
    global _ready
    if not _ready:
        with db.connect() as c:
            c.executescript(SCHEMA)
        _ready = True
    return db.connect()


def file_request(code_id, user_id, module, kind, note="", detail=None):
    """File one request. A second identical pending one is folded into the first."""
    if kind not in KINDS:
        raise ValueError("kind must be one of %s" % ", ".join(KINDS))
    d = json.dumps(detail or {}, sort_keys=True)
    with _conn() as c:
        r = c.execute("SELECT id FROM module_requests WHERE code_id = ? AND IFNULL(user_id,0) = ? AND "
                      "IFNULL(module,'') = ? AND kind = ? AND detail = ? AND status = 'pending'",
                      (int(code_id), int(user_id or 0), module or "", kind, d)).fetchone()
        if r:
            return r["id"]
        return c.execute("INSERT INTO module_requests (code_id,user_id,module,kind,note,detail,created_at) "
                         "VALUES (?,?,?,?,?,?,?)", (int(code_id), user_id, module, kind, (note or "")[:500], d,
                                                    db.now())).lastrowid


def pending_count():
    with _conn() as c:
        return c.execute("SELECT COUNT(*) n FROM module_requests WHERE status = 'pending'").fetchone()["n"]


def listing(status=None, limit=300):
    with _conn() as c:
        q = "SELECT * FROM module_requests" + (" WHERE status = ?" if status else "") + " ORDER BY id DESC LIMIT ?"
        rows = c.execute(q, ([status] if status else []) + [limit]).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["detail"] = json.loads(r["detail"] or "{}")
        except Exception:
            d["detail"] = {}
        out.append(d)
    return out


def get(rid):
    with _conn() as c:
        r = c.execute("SELECT * FROM module_requests WHERE id = ?", (int(rid),)).fetchone()
    if r is None:
        return None
    d = dict(r)
    try:
        d["detail"] = json.loads(r["detail"] or "{}")
    except Exception:
        d["detail"] = {}
    return d


def close(rid, status, by, reply=""):
    with _conn() as c:
        c.execute("UPDATE module_requests SET status = ?, decided_at = ?, decided_by = ?, reply = ? "
                  "WHERE id = ? AND status = 'pending'", (status, db.now(), by or "", (reply or "")[:300], int(rid)))
