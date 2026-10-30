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
import access_rules
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
        # The catalogue (owner, 2026-10-28): the roster, creator pages and analysis, selections, quotes. It used to be
        # the core and never switchable; it is a module now so a company can own Track or Intelligence without it.
        # Everyone starts with it on, so nothing changes for anybody the day it ships.
        "key": "helvi-selection",
        "name": "Helvi Selection",
        "what": "The creator catalogue: browse the roster, creator pages and analysis, shortlists, selections and quotes.",
        "logo": "/assets/brand/modules/helvi-selection-logo-v4.png",
        "client": ("/api/roster", "/api/creator", "/api/creator-media", "/api/licences", "/api/discover", "/api/search",
                   "/api/selection"),
        "admin": ("/creators", "/selections"),
        "tables": ("selections",),
        "tenant": "selection",
    },
    {
        "key": "helvi-intelligence",
        "name": "Helvi Intelligence",
        "what": "Competitor evidence: which creators already worked with their competitors, and how those posts did.",
        "logo": "/assets/brand/modules/helvi-intelligence-logo-v5.png",
        "client": ("/api/evidence",),
        "admin": ("/evidence",),
        "tables": ("evidence_packs", "evidence_posts", "evidence_roster"),
        "tenant": "selection",                    # whose it is: the selection the pack is filed under
    },
    {
        "key": "helvi-track",
        "name": "Helvi Track",
        "what": "Campaign tracking: the dashboard and report, tracking links, posts, insights and what people said.",
        "logo": "/assets/brand/modules/helvi-track-logo-v4.png",
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
# (docs/SAAS-MODEL.md) and creates it; this page only reads and writes it, and treats a missing
# table as "no roles yet". Written by delete + insert so it never depends on the key it chose.

ROLES = ("none", "viewer", "editor", "admin")


def _roles_conn():
    return db.connect()


def user_roles(user_ids):
    """{(user_id, module): role} for these people. A person with no row has the role `viewer`."""
    ids = [int(i) for i in user_ids]
    if not ids:
        return {}
    try:
        with _roles_conn() as conn:
            return {(r["user_id"], r["module"]): r["role"] for r in
                    conn.execute("SELECT user_id, module, role FROM user_modules WHERE user_id IN (%s)"
                                 % ",".join("?" * len(ids)), ids)}
    except Exception:                      # the table belongs to the gate session and may not exist yet
        return {}


def set_role(user_id, code_id, module, role, by=""):
    if module not in BY_KEY or role not in ROLES:
        return None
    try:
        with _roles_conn() as conn:
            conn.execute("DELETE FROM user_modules WHERE user_id = ? AND module = ?", (int(user_id), module))
            conn.execute("INSERT INTO user_modules (user_id, code_id, module, role, changed_at, changed_by) VALUES (?,?,?,?,?,?)",
                         (int(user_id), int(code_id), module, role, db.now(), by or ""))
    except Exception:
        return None
    return role


# ------------------------------------------------------- people and the gate --
# What a person may do is the lower of the company's level and their own role (docs/SAAS-MODEL.md). The decision
# itself is access_rules.refusal(), which has no imports and is tested on its own; this part finds the facts.

def paused(code_id, key):
    """True when HelloVoice paused this module for the company, as against the company never having had it.
    Both read as level off; the locked page differs (paused: your data is safe; never had: request it)."""
    try:
        with _conn() as conn:
            r = conn.execute("SELECT value FROM tenant_settings WHERE code_id = ? AND key = ?",
                             (int(code_id), "paused:" + key)).fetchone()
        return bool(r and r["value"] == "1")
    except Exception:
        return False


def set_paused(code_id, key, flag, by=""):
    if key not in BY_KEY:
        return None
    with _conn() as conn:
        if flag:
            conn.execute("INSERT INTO tenant_settings (code_id, key, value, changed_at, changed_by) VALUES (?,?,?,?,?) "
                         "ON CONFLICT(code_id, key) DO UPDATE SET value = excluded.value, changed_at = excluded.changed_at, "
                         "changed_by = excluded.changed_by", (int(code_id), "paused:" + key, "1", db.now(), by or ""))
        else:
            conn.execute("DELETE FROM tenant_settings WHERE code_id = ? AND key = ?", (int(code_id), "paused:" + key))
    return bool(flag)


def person_of(h):
    """The signed-in portal person behind this request, or None (a staff session, a passcode pass, a public link)."""
    try:
        cid = h.viewer_cookie_id()
    except Exception:
        return None
    if cid is None:
        return None
    import portal
    return portal.user_for_code(cid)


def company_of(user):
    """The company a person works in: their company's code, or their own code when they are the account holder."""
    k = user.keys()
    return user["company_code_id"] if "company_code_id" in k and user["company_code_id"] else user["code_id"]


def data_code_id(code_id):
    """The code the data of whoever holds this pass lives under (docs/SAAS-MODEL.md): a colleague invited into a
    company works on the company's selections, campaigns and credits, so their pass resolves to the company's code.
    Anyone else, and anything that is not a portal person (the admin preview), resolves to itself."""
    if code_id is None:
        return None
    import portal
    u = portal.user_for_code(code_id)
    if u is None:
        return code_id
    return access_rules.company_code(u["code_id"], u["company_code_id"] if "company_code_id" in u.keys() else None)


def is_colleague(user):
    return company_of(user) != user["code_id"]


def role_of(user, key):
    """none | viewer | editor | admin. A person with no row gets access_rules.default_role()."""
    try:
        with _roles_conn() as conn:
            r = conn.execute("SELECT role FROM user_modules WHERE user_id = ? AND module = ?",
                             (int(user["id"]), key)).fetchone()
        if r and r["role"] in ROLES:
            return r["role"]
    except Exception:                        # no roles table yet: every account holder stays admin
        pass
    return access_rules.default_role(is_colleague(user))


def company_admin(code_id, key):
    """First name of someone at the company who can give roles in this module, or None."""
    try:
        with _roles_conn() as conn:
            rows = conn.execute("SELECT id, name, code_id, company_code_id FROM users WHERE (code_id = ? OR company_code_id = ?) "
                                "AND status = 'active' ORDER BY (company_code_id IS NULL) DESC, id", (int(code_id), int(code_id))).fetchall()
            for u in rows:
                if role_of(u, key) == "admin":
                    return (u["name"] or "").split(" ")[0] or None
    except Exception:
        pass
    return None


def state_for(user, key):
    """What this person meets in this module: {code, level, role, paused}. code is None when it opens."""
    cid = company_of(user)
    lvl, role, p = level(cid, key), role_of(user, key), paused(cid, key)
    return {"code": access_rules.refusal(lvl, p, role, "GET"), "level": lvl, "role": role, "paused": p, "company": cid}


REASON = {"locked": "module_off", "paused": "module_off", "no_role": "module_no_role", "read_only": "module_read_only"}


def refusal_for(h, path, query=None):
    """None, or {status, body}: the module refusing this request, for this person. HelloVoice staff are never
    refused. A request with nobody behind it (a /go/ click, a public report link) is checked on the company only."""
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
    person = None
    try:
        person = person_of(h)
    except Exception:
        person = None
    role = "editor"                          # no person, or acting inside somebody else's shared link: company level only
    if person is not None and (cid == company_of(person) or cid == person["code_id"]):
        cid = company_of(person)
        role = role_of(person, mod["key"])
    code = access_rules.refusal(level(cid, mod["key"]), paused(cid, mod["key"]), role, getattr(h, "command", "GET"))
    if code is None:
        return None
    return {"status": 403, "body": {"ok": False, "code": code, "reason": REASON[code], "module": mod["key"], "name": mod["name"]}}


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
