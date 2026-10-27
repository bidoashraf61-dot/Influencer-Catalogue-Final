"""Which modules a tenant has, and at what level.

A **tenant is a client company** — the `codes` row their people sign in against, which
every client-owned thing already hangs off as `code_id`. A **module** is a product that
tenant either has or does not. The core — the roster, selections, quotes, the portal —
is not a module and is never switched off.

    off      the module's routes refuse and its data never reaches the browser.
             Nothing is deleted: switching it back on returns everything untouched.
    view     the tenant reads what HelloVoice made for them. This is what every client
             has had until now, so it is the default and the day this shipped nothing
             changed for anybody.
    manage   the tenant adds and edits their own, inside their caps. The endpoints that
             let them do that are the next phase; a tenant set to manage today can do
             what view does and no more, which is why the Tenants page says so.

HelloVoice staff are never gated here — an owner, admin or KAM opens every module for
every client — and only an owner sets the levels, on /tenants.

The registry below is the one list of what belongs to a module: its client routes, its
admin routes, its tables. A third module is a row here, not a hunt through the router.

Where a request carries no token and nobody is signed in (a /go/ click from a stranger's
phone, say) there is no tenant to check and the request passes; the dashboards and the
packs behind it are still gated.
"""
import db

LEVELS = ("off", "view", "manage")
DEFAULT = "view"
LEVEL_LABEL = {"off": "Off", "view": "View only", "manage": "Manage their own"}
LEVEL_HELP = {
    "off": "Hidden from them completely. Their data is kept and comes back if you switch it on.",
    "view": "They read what HelloVoice made for them. This is how every client has worked so far.",
    "manage": "They add and edit their own, inside their caps. The screens for it are not built yet.",
}

MODULES = [
    {
        "key": "helvi-intelligence",
        "name": "Helvi Intelligence",
        "what": "Competitor evidence: which creators already worked with their competitors, and how those posts did.",
        "logo": "/assets/brand/modules/helvi-intelligence-480.png",
        "client": ("/api/evidence",),
        "admin": ("/evidence",),
        "tables": ("evidence_packs", "evidence_posts", "evidence_roster"),
        "tenant": "selection",                    # whose it is: the selection the pack is filed under
    },
    {
        "key": "helvi-track",
        "name": "Helvi Track",
        "what": "Campaign tracking: the dashboard and report, tracking links, posts, insights and what people said.",
        "logo": "/assets/brand/modules/helvi-track-480.png",
        "client": ("/api/campaign", "/api/campaigns", "/go/", "/insights/"),
        "admin": ("/campaigns",),
        "tables": ("campaigns", "campaign_creators", "content", "clicks", "links", "insights",
                   "snapshots", "comments"),
        "tenant": "campaign",
    },
]
BY_KEY = {m["key"]: m for m in MODULES}

# What an owner can set for one tenant besides its modules. Each field has a platform
# default and the tenant row holds only what differs from it, so a new tenant works
# before anyone configures anything and a default can be moved in one place.
#
# `enforced` is the honest part: a cap is only real where something checks it. Credits,
# campaigns and selections are checked where a tenant creates one. Seats and captures a
# day are stored and wait for the tenant-side screens that can spend them -- today no
# tenant can trigger a capture at all, so there is nothing to refuse.
LIMITS = [
    {"key": "credits_month", "label": "AI credits a month", "kind": "int", "enforced": True,
     "help": "Tops the balance up on the 1st. Empty uses the platform's monthly credits setting."},
    {"key": "campaigns_max", "label": "Campaigns", "kind": "int", "enforced": True,
     "help": "How many campaigns they may have. Empty means no limit."},
    {"key": "selections_max", "label": "Selections", "kind": "int", "enforced": True,
     "help": "How many selections they may keep. Empty means no limit."},
    {"key": "spend_month", "label": "Collection $ a month", "kind": "int", "enforced": True,
     "help": "What their collection runs may cost in a month, in dollars. Checked against what Apify "
             "actually billed, before a run starts. Empty means only the shared budget stops them."},
    {"key": "seats", "label": "Seats", "kind": "int", "enforced": False,
     "help": "People on their account. Recorded; invites do not check it yet."},
    {"key": "captures_day", "label": "Captures a day", "kind": "int", "enforced": False,
     "help": "Collection runs a day once they can start their own. Nothing spends on their behalf yet."},
]

BRAND = [
    {"key": "brand_name", "label": "Name on reports", "kind": "text", "enforced": False,
     "help": "What they are called on the report and in the app. Empty uses their account name."},
    {"key": "brand_colour", "label": "Colour", "kind": "text", "enforced": False,
     "help": "Hex, e.g. #1b9b52. Empty uses the HELVi Connect colours."},
    {"key": "brand_logo", "label": "Logo", "kind": "text", "enforced": False,
     "help": "A link to their logo. Empty uses the one on each campaign."},
]
NOTES = [
    {"key": "notes", "label": "Notes", "kind": "text", "enforced": False,
     "help": "Internal. Never shown to the client."},
]
FIELDS = {f["key"]: f for f in LIMITS + BRAND + NOTES}

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenant_settings (
    code_id    INTEGER NOT NULL,
    key        TEXT NOT NULL,             -- a key from LIMITS or BRAND
    value      TEXT,                      -- "" / NULL means "use the platform default"
    changed_at INTEGER NOT NULL,
    changed_by TEXT,
    PRIMARY KEY (code_id, key)
);

CREATE TABLE IF NOT EXISTS tenant_modules (
    code_id    INTEGER NOT NULL,          -- the client's codes row: the tenant
    module     TEXT NOT NULL,             -- a key from MODULES
    level      TEXT NOT NULL,             -- off | view | manage
    changed_at INTEGER NOT NULL,
    changed_by TEXT,                      -- the owner's email
    PRIMARY KEY (code_id, module)
);
"""

_ready = False


def init():
    global _ready
    with db.connect() as conn:
        conn.executescript(SCHEMA)
    _ready = True


def _conn():
    """db.connect(), making sure the table exists (tools import this without main())."""
    if not _ready:
        init()
    return db.connect()


# --------------------------------------------------------------- the levels --

def levels(code_id):
    """{module key: level} for one tenant, every module answered, defaults filled in."""
    out = {m["key"]: DEFAULT for m in MODULES}
    if code_id is None:
        return out
    with _conn() as conn:
        for r in conn.execute("SELECT module, level FROM tenant_modules WHERE code_id = ?", (int(code_id),)):
            if r["module"] in out and r["level"] in LEVELS:
                out[r["module"]] = r["level"]
    return out


def level(code_id, key):
    return levels(code_id).get(key, DEFAULT)


def set_level(code_id, key, lvl, by=""):
    """Returns the level actually stored. An unknown module or level is ignored rather
    than written, so a stale form can never turn a module off by accident."""
    if key not in BY_KEY or lvl not in LEVELS:
        return None
    with _conn() as conn:
        conn.execute("INSERT INTO tenant_modules (code_id, module, level, changed_at, changed_by) "
                     "VALUES (?,?,?,?,?) ON CONFLICT(code_id, module) DO UPDATE SET "
                     "level = excluded.level, changed_at = excluded.changed_at, changed_by = excluded.changed_by",
                     (int(code_id), key, lvl, db.now(), by or ""))
    return lvl


def all_levels():
    """{code_id: {module: level}} for every tenant that has a row — the Tenants list."""
    out = {}
    with _conn() as conn:
        for r in conn.execute("SELECT code_id, module, level FROM tenant_modules"):
            out.setdefault(r["code_id"], {})[r["module"]] = r["level"]
    return out


# ------------------------------------------------------- limits and brand --

def settings(code_id):
    """{key: value} for one tenant — only what an owner has actually set."""
    if code_id is None:
        return {}
    with _conn() as conn:
        return {r["key"]: r["value"] for r in
                conn.execute("SELECT key, value FROM tenant_settings WHERE code_id = ?", (int(code_id),))
                if r["key"] in FIELDS}


def value(code_id, key, default=None):
    """What this tenant's field is set to, or `default` when they are on the platform's."""
    v = settings(code_id).get(key)
    return default if v in (None, "") else v


def number(code_id, key):
    """An int limit, or None for no limit."""
    try:
        v = value(code_id, key)
        return None if v in (None, "") else max(0, int(v))
    except (TypeError, ValueError):
        return None


def set_value(code_id, key, val, by=""):
    """Store one field. An empty value clears the override and returns the tenant to the
    platform default rather than writing a zero."""
    if key not in FIELDS:
        return None
    val = (str(val) if val is not None else "").strip()
    if FIELDS[key]["kind"] == "int" and val:
        try:
            val = str(max(0, int(val)))
        except ValueError:
            return None
    with _conn() as conn:
        if val == "":
            conn.execute("DELETE FROM tenant_settings WHERE code_id = ? AND key = ?", (int(code_id), key))
        else:
            conn.execute("INSERT INTO tenant_settings (code_id, key, value, changed_at, changed_by) "
                         "VALUES (?,?,?,?,?) ON CONFLICT(code_id, key) DO UPDATE SET "
                         "value = excluded.value, changed_at = excluded.changed_at, changed_by = excluded.changed_by",
                         (int(code_id), key, val, db.now(), by or ""))
    return val


def all_settings():
    """{code_id: {key: value}} — the Tenants list, in one read."""
    out = {}
    with _conn() as conn:
        for r in conn.execute("SELECT code_id, key, value FROM tenant_settings"):
            if r["key"] in FIELDS:
                out.setdefault(r["code_id"], {})[r["key"]] = r["value"]
    return out


COUNTABLE = {"campaigns", "selections"}


def count(code_id, table):
    """How many of a thing this tenant has. Only the two tables a cap is checked against,
    named here rather than passed in, so this can never become a way to read anything else."""
    if table not in COUNTABLE or code_id is None:
        return 0
    with _conn() as conn:
        r = conn.execute("SELECT COUNT(*) n FROM %s WHERE code_id = ?" % table, (int(code_id),)).fetchone()
    return r["n"] if r else 0


def over(code_id, key, have):
    """True when a tenant is at or past a cap and must be refused. No cap set = never."""
    cap = number(code_id, key)
    return cap is not None and have >= cap


# ------------------------------------------------------------------ roles --
# A person's role in one module: none / viewer / editor / admin. The gate session owns this table
# (docs/SAAS-MODEL.md); it is declared the same way here so the Tenants page works either side of
# that landing, and written by delete + insert so it never depends on the primary key it chose.

ROLES = ("none", "viewer", "editor", "admin")
_ROLES_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_modules (
    user_id INTEGER NOT NULL, code_id INTEGER NOT NULL, module TEXT NOT NULL, role TEXT NOT NULL
);
"""


_roles_ready = False


def _roles_conn():
    global _roles_ready
    if not _roles_ready:
        with db.connect() as conn:
            conn.executescript(_ROLES_SCHEMA)
        _roles_ready = True
    return db.connect()


def user_roles(user_ids):
    """{(user_id, module): role} for these people. A person with no row has the role `viewer`."""
    ids = [int(i) for i in user_ids]
    if not ids:
        return {}
    with _roles_conn() as conn:
        return {(r["user_id"], r["module"]): r["role"] for r in
                conn.execute("SELECT user_id, module, role FROM user_modules WHERE user_id IN (%s)"
                             % ",".join("?" * len(ids)), ids)}


def set_role(user_id, code_id, module, role):
    if module not in BY_KEY or role not in ROLES:
        return None
    with _roles_conn() as conn:
        conn.execute("DELETE FROM user_modules WHERE user_id = ? AND module = ?", (int(user_id), module))
        conn.execute("INSERT INTO user_modules (user_id, code_id, module, role) VALUES (?,?,?,?)",
                     (int(user_id), int(code_id), module, role))
    return role


# ----------------------------------------------------------------- the gate --

def for_path(path):
    """The module a client-facing path belongs to, or None for the core."""
    for m in MODULES:
        for p in m["client"]:
            if path == p or path.startswith(p + "/") or (p.endswith("/") and path.startswith(p)):
                return m
    return None


def tenant_of(h, mod, query):
    """Whose request this is: the client the selection or campaign belongs to, else the
    signed-in viewer. None when there is nobody to gate."""
    body = h.json_body() if h.command == "POST" else {}
    if mod["tenant"] == "selection":
        token = (query.get("s") or "").strip() or str(body.get("token") or "").strip()
        sel = db.selection(token=token) if token else None
        if sel is not None:
            return sel["code_id"]
    elif mod["tenant"] == "campaign":
        token = (query.get("t") or "").strip() or str(body.get("t") or body.get("token") or "").strip()
        k = db.campaign(token=token) if token else None
        if k is not None:
            return k["code_id"]
    try:
        return h.viewer_code_id()
    except Exception:
        return None


def blocked(h, path, query=None):
    """The module refusing this request, or None. HelloVoice staff are never refused."""
    mod = for_path(path)
    if mod is None:
        return None
    try:
        if h.admin_like():
            return None
    except Exception:
        pass
    cid = tenant_of(h, mod, query or {})
    if cid is None:
        return None
    return mod if level(cid, mod["key"]) == "off" else None
