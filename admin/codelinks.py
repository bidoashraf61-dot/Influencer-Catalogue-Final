"""Moving shared access codes onto email accounts (HELVY Connect, phase C).

The sign-in page no longer offers "I have an access code". About six shared codes are
still in use, so HelloVoice invites each of those clients to an email account first.
Nothing is revoked here and nothing moves: a code keeps working (its selection and
campaign links still ask for it), and the account it is linked to simply sees the
code's selections and campaigns as its own, and owns them (approve / reject).

    init()                       the table (safe on every start)
    invite(code_id, email, by)   link now if the account exists, else when it signs up
    claim(email, user_code_id)   called when an account is created: picks up its invites
    linked_for(user_code_ids)    the shared codes linked to any of these account codes
    shared_codes()               the admin view: active shared codes, their selections,
                                 campaigns and links

A "shared code" is a typed passcode row: not the admin preview, not a signed-up
client's personal row, not revoked and not expired.
"""
import db
import guard

SCHEMA = """
CREATE TABLE IF NOT EXISTS code_links (
    id INTEGER PRIMARY KEY,
    legacy_code_id INTEGER NOT NULL,     -- codes.id of the shared access code
    email TEXT NOT NULL,                 -- who it was invited to (normalised)
    user_code_id INTEGER,                -- users.code_id once that account exists
    created_at INTEGER NOT NULL,
    created_by TEXT,
    linked_at INTEGER,
    UNIQUE (legacy_code_id, email)
);
CREATE INDEX IF NOT EXISTS code_links_user ON code_links(user_code_id);
CREATE INDEX IF NOT EXISTS code_links_email ON code_links(email);
"""


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)


def _personal_ids(conn):
    return {r["code_id"] for r in conn.execute("SELECT code_id FROM users WHERE code_id IS NOT NULL")}


def is_shared(code_id):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM codes WHERE id = ?", (code_id,)).fetchone()
        if row is None or row["id"] == db.admin_code_id() or row["id"] in _personal_ids(conn):
            return False
    return db.code_state(row)[0]


def invite(code_id, email, by=""):
    """Returns ``(row, error)``. ``error`` is one of: not_shared, email."""
    import portal
    if not is_shared(code_id):
        return None, "not_shared"
    email = guard.normalise_email(email)
    if not email or "@" not in email:
        return None, "email"
    user = portal.user_by_email(email)
    now = db.now()
    with db.connect() as conn:
        conn.execute("INSERT OR IGNORE INTO code_links (legacy_code_id, email, created_at, created_by) VALUES (?,?,?,?)",
                     (code_id, email, now, by))
        if user is not None and user["code_id"]:
            conn.execute("UPDATE code_links SET user_code_id = ?, linked_at = COALESCE(linked_at, ?) "
                         "WHERE legacy_code_id = ? AND email = ?", (user["code_id"], now, code_id, email))
        row = conn.execute("SELECT * FROM code_links WHERE legacy_code_id = ? AND email = ?", (code_id, email)).fetchone()
    return row, None


def claim(email, user_code_id):
    """A new account picks up every code it was invited to."""
    email = guard.normalise_email(email)
    if not email:
        return 0
    with db.connect() as conn:
        cur = conn.execute("UPDATE code_links SET user_code_id = ?, linked_at = ? WHERE email = ? AND user_code_id IS NULL",
                           (user_code_id, db.now(), email))
        return cur.rowcount


def remove(link_id):
    with db.connect() as conn:
        conn.execute("DELETE FROM code_links WHERE id = ?", (link_id,))


def linked_for(user_code_ids):
    ids = [int(x) for x in (user_code_ids or ()) if x is not None]
    if not ids:
        return set()
    with db.connect() as conn:
        rows = conn.execute("SELECT legacy_code_id FROM code_links WHERE user_code_id IN (%s)" % ",".join("?" * len(ids)),
                            ids).fetchall()
    return {r["legacy_code_id"] for r in rows}


def shared_codes():
    """Every active shared code with what hangs off it, newest use first."""
    out = []
    with db.connect() as conn:
        personal = _personal_ids(conn)
        rows = conn.execute("SELECT * FROM codes ORDER BY id").fetchall()
        for c in rows:
            if c["id"] == db.admin_code_id() or c["id"] in personal or not db.code_state(c)[0]:
                continue
            if "archived_at" in c.keys() and c["archived_at"]:
                continue
            sels = conn.execute("SELECT id, name, token, codes, updated_at FROM selections WHERE code_id = ? ORDER BY updated_at DESC",
                                (c["id"],)).fetchall()
            camps = conn.execute("SELECT id, name, status, token FROM campaigns WHERE code_id = ? ORDER BY id DESC", (c["id"],)).fetchall()
            last = conn.execute("SELECT MAX(at) FROM events WHERE code_id = ?", (c["id"],)).fetchone()[0]
            links = conn.execute("SELECT l.*, u.name AS user_name, u.status AS user_status FROM code_links l "
                                 "LEFT JOIN users u ON u.code_id = l.user_code_id WHERE l.legacy_code_id = ? ORDER BY l.id",
                                 (c["id"],)).fetchall()
            out.append({"code": c, "selections": sels, "campaigns": camps, "last_used": last, "links": links})
    out.sort(key=lambda x: -(x["last_used"] or 0))
    return out
