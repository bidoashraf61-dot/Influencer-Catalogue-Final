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
        "client": ("/api/evidence",),
        "admin": ("/evidence",),
        "tables": ("evidence_packs", "evidence_posts", "evidence_roster"),
        "tenant": "selection",                    # whose it is: the selection the pack is filed under
    },
    {
        "key": "helvi-track",
        "name": "Helvi Track",
        "what": "Campaign tracking: the dashboard and report, tracking links, posts, insights and what people said.",
        "client": ("/api/campaign", "/api/campaigns", "/go/", "/insights/"),
        "admin": ("/campaigns",),
        "tables": ("campaigns", "campaign_creators", "content", "clicks", "links", "insights",
                   "snapshots", "comments"),
        "tenant": "campaign",
    },
]
BY_KEY = {m["key"]: m for m in MODULES}

SCHEMA = """
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
