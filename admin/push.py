"""HELVi Connect app: phone push alerts and install tracking (item 168).

Every alert starts life as a bell notification (inbox.emit) or a team email
(notify.send); both hand it here, and the loop turns it into Web Push messages
for that person's phones. Manual pushes from the admin go the same way.

    track(ident, body)          the app's own reports: visits, install guide, installs, permission
    subscribe(ident, sub, ...)  store a browser's PushSubscription
    from_inbox(rows)            called by inbox.emit for every stored notification
    team(event, lines, link, emails)   called by notify.send for team alerts
    create_message(...)         a manual push (now or scheduled)
    start()                     the sender loop: queue -> deliveries -> Web Push, plus milestones

Rules (setting "push_rules", edited in Admin -> App & alerts):
    quiet hours 23:00-08:00 Riyadh and at most 3 automatic pushes a day per person;
    held pushes go at 08:00. Manual pushes skip the daily cap (quiet hours still apply).
Nothing here raises into the caller: a push that cannot go must not break the action.
"""
import collections
import json
import secrets
import threading
import time

import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS push_devices (
    id INTEGER PRIMARY KEY,
    endpoint TEXT NOT NULL UNIQUE,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    user_id INTEGER,
    admin_id INTEGER,
    code_id INTEGER,
    email TEXT,
    device_key TEXT,
    platform TEXT,
    os TEXT,
    browser TEXT,
    standalone INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',     -- active | off | gone
    fails INTEGER DEFAULT 0,
    sent INTEGER DEFAULT 0,
    clicked INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL,
    last_seen_at INTEGER
);
CREATE INDEX IF NOT EXISTS push_dev_user ON push_devices(user_id);
CREATE INDEX IF NOT EXISTS push_dev_email ON push_devices(email);

CREATE TABLE IF NOT EXISTS app_clients (
    device_key TEXT PRIMARY KEY,
    user_id INTEGER,
    admin_id INTEGER,
    code_id INTEGER,
    email TEXT,
    platform TEXT,                              -- ios | android | desktop
    os TEXT,
    browser TEXT,
    first_seen INTEGER,
    last_seen INTEGER,
    installed_at INTEGER,
    last_launch_at INTEGER,
    launches INTEGER DEFAULT 0,
    permission TEXT,                            -- granted | denied | default | unsupported
    guide_at INTEGER,
    guide_closed_at INTEGER,
    asked_at INTEGER,
    prompted_at INTEGER,
    granted_at INTEGER,
    denied_at INTEGER
);
CREATE INDEX IF NOT EXISTS app_cli_user ON app_clients(user_id);

CREATE TABLE IF NOT EXISTS push_messages (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,                       -- manual | auto | test
    rule TEXT,
    title TEXT NOT NULL,
    body TEXT,
    url TEXT,
    audience TEXT,                              -- JSON
    created_by TEXT,
    created_at INTEGER NOT NULL,
    send_at INTEGER,
    status TEXT NOT NULL,                       -- draft | scheduled | sending | sent | cancelled
    sent_at INTEGER,
    people INTEGER DEFAULT 0,
    devices INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS push_deliveries (
    id INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL,
    device_id INTEGER NOT NULL,
    user_id INTEGER,
    email TEXT,
    token TEXT NOT NULL,
    status TEXT NOT NULL,                       -- queued | sent | failed | gone | skipped
    reason TEXT,
    send_after INTEGER NOT NULL,
    sent_at INTEGER,
    http INTEGER,
    acked_at INTEGER,
    clicked_at INTEGER
);
CREATE INDEX IF NOT EXISTS push_del_due ON push_deliveries(status, send_after);
CREATE INDEX IF NOT EXISTS push_del_msg ON push_deliveries(message_id);

CREATE TABLE IF NOT EXISTS push_prefs (user_id INTEGER PRIMARY KEY, phone INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS push_milestones (campaign_id INTEGER NOT NULL, key TEXT NOT NULL, at INTEGER,
    PRIMARY KEY (campaign_id, key));
CREATE TABLE IF NOT EXISTS push_camp_state (campaign_id INTEGER PRIMARY KEY, posts INTEGER, posts_push_at INTEGER);
-- "Scan to get the app" (item 169): a one-use, 15-minute sign-in for the person's phone.
CREATE TABLE IF NOT EXISTS app_handoff (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL, used_at INTEGER, used_ip TEXT);
"""
LATER_COLUMNS = (("app_clients", "qr_at", "INTEGER"), ("app_clients", "welcome_at", "INTEGER"),
                 ("push_prefs", "welcome_at", "INTEGER"))
HANDOFF_TTL = 15 * 60

DEFAULT_RULES = {
    "on": True,                     # master switch for every automatic push
    "camp_status": True,            # live / ended / final report
    "goals": True, "goal_steps": [25, 50, 75, 100],
    "posts": True, "posts_gap_h": 4,
    "views": True, "view_steps": [100000, 500000, 1000000, 5000000],
    "bell": True,                   # everything else the bell sends (selections, analysis, quotes, credits)
    "team": True,                   # KAM / admin: briefs, quote requests, red flags
    "quiet": [23, 8],               # Riyadh hours, start and end
    "daily_max": 3,
}
RULE_LABELS = {"camp_status": "Campaign live / ended / final report", "goals": "Goal reached",
               "posts": "First post + new posts live", "views": "Views passed", "bell": "Selections, analysis, quotes, credits",
               "team": "Team alerts", "manual": "Manual", "test": "Test"}
# inbox kind -> rule. Kinds not listed never push (daily "report updated", ideas).
KIND_RULE = {"camp_live": "camp_status", "camp_final": "camp_status", "camp_goal": "goals", "camp_views": "views",
             "camp_posts": "posts", "camp_shared": "bell", "camp_weekly": "bell", "camp_next": "bell",
             "analysis_ready": "bell", "sel_feedback": "bell", "sel_shared": "bell", "sel_updated": "bell",
             "unavailable": "bell", "quote_requested": "bell", "quote_ready": "bell", "quote_approved": "bell",
             "credits_low": "bell", "credits_added": "bell", "colleague": "bell", "announce": "manual"}
RIYADH = 3 * 3600
TICK = 5                            # seconds between queue passes
MILESTONE_EVERY = 600

_queue = collections.deque()        # filled from request threads, drained by the loop (never blocks a caller)
_lock = threading.Lock()


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        for table, col, ddl in LATER_COLUMNS:
            if col not in {r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)}:
                conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, ddl))


def rules():
    got = db.setting("push_rules", {}) or {}
    out = dict(DEFAULT_RULES)
    out.update({k: v for k, v in got.items() if k in DEFAULT_RULES})
    return out


def save_rules(changes):
    cur = rules()
    for k, v in (changes or {}).items():
        if k in ("goal_steps", "view_steps"):
            vals = sorted({int(x) for x in v if str(x).strip().isdigit() and int(x) > 0})
            if vals:
                cur[k] = vals
        elif k in ("posts_gap_h", "daily_max"):
            try:
                cur[k] = max(0, min(48, int(v)))
            except (TypeError, ValueError):
                pass
        elif k == "quiet":
            try:
                a, b = int(v[0]) % 24, int(v[1]) % 24
                cur[k] = [a, b]
            except (TypeError, ValueError, IndexError):
                pass
        elif k in DEFAULT_RULES:
            cur[k] = bool(v)
    db.set_setting("push_rules", cur)
    return cur


# -------------------------------------------------------------- identity --

def platform_of(ua):
    ua = ua or ""
    if "iPhone" in ua or "iPad" in ua or "iPod" in ua:
        return "ios"
    if "Android" in ua:
        return "android"
    return "desktop"


def phone_on(user_id):
    if not user_id:
        return True
    with db.connect() as conn:
        r = conn.execute("SELECT phone FROM push_prefs WHERE user_id = ?", (user_id,)).fetchone()
    return True if r is None else bool(r["phone"])


def set_phone(user_id, on):
    with db.connect() as conn:
        conn.execute("INSERT INTO push_prefs (user_id, phone) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET phone = excluded.phone",
                     (user_id, 1 if on else 0))
    return bool(on)


def _clean(v, n=60):
    return str(v or "")[:n]


EVENT_COLS = {"qr": "qr_at", "welcome": "welcome_at", "guide": "guide_at", "guide_closed": "guide_closed_at", "asked": "asked_at", "prompted": "prompted_at",
              "granted": "granted_at", "denied": "denied_at", "installed": "installed_at"}


def track(ident, body, ua=""):
    """The app reports what happened on this device. ``ident`` = {user_id, admin_id, code_id, email}."""
    key = _clean(body.get("k"), 40)
    if len(key) < 8:
        return False
    ev = _clean(body.get("e"), 20)
    now = db.now()
    plat = body.get("p") if body.get("p") in ("ios", "android", "desktop") else platform_of(ua)
    perm = body.get("perm") if body.get("perm") in ("granted", "denied", "default", "unsupported") else None
    standalone = bool(body.get("sa"))
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM app_clients WHERE device_key = ?", (key,)).fetchone()
        if row is None:
            conn.execute("INSERT INTO app_clients (device_key, first_seen, last_seen, launches) VALUES (?, ?, ?, 0)", (key, now, now))
            row = conn.execute("SELECT * FROM app_clients WHERE device_key = ?", (key,)).fetchone()
        sets = {"last_seen": now, "platform": plat, "os": _clean(body.get("os"), 30) or row["os"],
                "browser": _clean(body.get("br"), 30) or row["browser"]}
        for col in ("user_id", "admin_id", "code_id", "email"):
            if ident.get(col):
                sets[col] = ident[col]
        if perm:
            sets["permission"] = perm
            if perm == "granted" and not row["granted_at"]:
                sets["granted_at"] = now
            if perm == "denied" and not row["denied_at"]:
                sets["denied_at"] = now
        if standalone and not row["installed_at"]:
            sets["installed_at"] = now                 # the first full-screen open is the install
        if ev == "launch" and standalone:
            sets["last_launch_at"] = now
            sets["launches"] = (row["launches"] or 0) + 1
        col = EVENT_COLS.get(ev)
        if col and (col in ("guide_closed_at",) or not row[col]):
            sets[col] = now
        conn.execute("UPDATE app_clients SET %s WHERE device_key = ?" % ", ".join("%s = ?" % c for c in sets),
                     list(sets.values()) + [key])
    return True


# ---------------------------------------------------------- phone hand-off --

def _hash(token):
    import hashlib
    return hashlib.sha256(str(token).encode()).hexdigest()


def handoff(user_id):
    """A one-use token that signs this person in on the phone that scans it."""
    token = secrets.token_urlsafe(24)
    now = db.now()
    with db.connect() as conn:
        conn.execute("DELETE FROM app_handoff WHERE expires_at < ?", (now - 86400,))
        n = conn.execute("SELECT COUNT(*) FROM app_handoff WHERE user_id = ? AND created_at > ?", (user_id, now - 3600)).fetchone()[0]
        if n >= 20:
            return None
        conn.execute("INSERT INTO app_handoff (token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                     (_hash(token), user_id, now, now + HANDOFF_TTL))
    return token


def redeem(token, ip=None):
    """The user id for a fresh, unused token (and marks it used), else None."""
    if not token or len(str(token)) > 64:
        return None
    now = db.now()
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM app_handoff WHERE token_hash = ?", (_hash(token),)).fetchone()
        if r is None or r["used_at"] or r["expires_at"] < now:
            return None
        if not conn.execute("UPDATE app_handoff SET used_at = ?, used_ip = ? WHERE token_hash = ? AND used_at IS NULL",
                            (now, ip, r["token_hash"])).rowcount:
            return None
    return r["user_id"]


def welcome_seen(user_id):
    if not user_id:
        return True
    with db.connect() as conn:
        r = conn.execute("SELECT welcome_at FROM push_prefs WHERE user_id = ?", (user_id,)).fetchone()
    return bool(r and r["welcome_at"])


def mark_welcome(user_id):
    with db.connect() as conn:
        conn.execute("INSERT INTO push_prefs (user_id, phone, welcome_at) VALUES (?, 1, ?) "
                     "ON CONFLICT(user_id) DO UPDATE SET welcome_at = COALESCE(welcome_at, excluded.welcome_at)",
                     (user_id, db.now()))


def phone_app(user_id):
    """Has this person the app on a phone with alerts on?"""
    if not user_id:
        return False
    with db.connect() as conn:
        return bool(conn.execute("SELECT 1 FROM push_devices WHERE user_id = ? AND status = 'active' AND platform IN ('ios','android')",
                                 (user_id,)).fetchone())


def installed(user_id=None, device_key=None):
    """Has this person (or this very phone) the app on a phone's Home Screen?"""
    with db.connect() as conn:
        if device_key and conn.execute("SELECT 1 FROM app_clients WHERE device_key = ? AND installed_at IS NOT NULL",
                                       (str(device_key)[:40],)).fetchone():
            return True
        if user_id and conn.execute("SELECT 1 FROM app_clients WHERE user_id = ? AND installed_at IS NOT NULL AND platform IN ('ios','android')",
                                    (user_id,)).fetchone():
            return True
    return phone_app(user_id)


def subscribe(ident, sub, device_key="", ua="", standalone=False, old=None):
    try:
        endpoint = str(sub["endpoint"])
        p256dh, auth = str(sub["keys"]["p256dh"]), str(sub["keys"]["auth"])
    except (KeyError, TypeError):
        return False
    if not endpoint.startswith("https://") or len(endpoint) > 1000 or len(p256dh) > 200 or len(auth) > 64:
        return False
    now = db.now()
    with db.connect() as conn:
        if old:
            conn.execute("UPDATE push_devices SET status = 'gone' WHERE endpoint = ?", (str(old)[:1000],))
        vals = dict(p256dh=p256dh, auth=auth, device_key=_clean(device_key, 40), platform=platform_of(ua),
                    browser=_browser(ua), os=_os(ua), standalone=1 if standalone else 0, status="active", fails=0,
                    last_seen_at=now)
        for col in ("user_id", "admin_id", "code_id", "email"):
            if ident.get(col):
                vals[col] = ident[col]
        r = conn.execute("SELECT id FROM push_devices WHERE endpoint = ?", (endpoint,)).fetchone()
        if r:
            conn.execute("UPDATE push_devices SET %s WHERE id = ?" % ", ".join("%s = ?" % c for c in vals),
                         list(vals.values()) + [r["id"]])
        else:
            vals.update(endpoint=endpoint, created_at=now)
            conn.execute("INSERT INTO push_devices (%s) VALUES (%s)" % (", ".join(vals), ",".join("?" * len(vals))),
                         list(vals.values()))
    return True


def unsubscribe(endpoint):
    with db.connect() as conn:
        return conn.execute("UPDATE push_devices SET status = 'off' WHERE endpoint = ?", (str(endpoint)[:1000],)).rowcount


def _browser(ua):
    ua = ua or ""
    for name, tag in (("Samsung", "SamsungBrowser"), ("Edge", "Edg/"), ("Firefox", "Firefox"), ("Chrome", "CriOS"),
                      ("Chrome", "Chrome"), ("Safari", "Safari")):
        if tag in ua:
            return name
    return ""


def _os(ua):
    import re
    ua = ua or ""
    m = re.search(r"OS (\d+)[_.](\d+)", ua) if platform_of(ua) == "ios" else re.search(r"Android (\d+)", ua)
    if m:
        return ("iOS " + ".".join(m.groups())) if platform_of(ua) == "ios" else "Android " + m.group(1)
    return "Mac" if "Macintosh" in ua else ("Windows" if "Windows" in ua else "")


# ------------------------------------------------------------- enqueueing --

def from_inbox(rows):
    """[(user_id, kind, title, rest, body, href)] just stored by inbox.emit. Queued only:
    the caller may be inside an open database transaction."""
    for r in rows or ():
        _queue.append(("bell",) + tuple(r))


def team(event, lines, link, emails):
    """A team email (notify.send) also goes to the team's phones."""
    if not emails:
        return
    import notify
    title = notify.EVENTS.get(event, event)
    body = next((str(x) for x in lines if x), "")
    _queue.append(("team", event, title, body, link or "/admin/", list(emails)))


def _drain():
    """Group what was queued into messages and deliveries."""
    items = []
    while _queue:
        try:
            items.append(_queue.popleft())
        except IndexError:
            break
    if not items:
        return 0
    R = rules()
    groups = collections.OrderedDict()
    for it in items:
        if it[0] == "bell":
            _, uid, kind, title, rest, body, href = it
            rule = KIND_RULE.get(kind)
            if not rule or (rule != "manual" and (not R["on"] or not R.get(rule))):
                continue
            if rule != "manual" and not phone_on(uid):
                continue
            full = (str(title) + (str(rest) if rest else "")).strip()
            url = href if str(href).startswith(("http", "/")) else "/" + str(href or "account/#notifications")
            groups.setdefault((rule, full, body, url, kind), {"users": [], "emails": []})["users"].append(uid)
        else:
            _, event, title, body, link, emails = it
            if not R["on"] or not R.get("team"):
                continue
            groups.setdefault(("team", title, body, link, event), {"users": [], "emails": []})["emails"].extend(emails)
    n = 0
    for (rule, title, body, url, tag), who in groups.items():
        n += _make(rule, title, body, url, who["users"], who["emails"], source="manual" if rule == "manual" else "auto",
                   tag=tag, audience={"rule": rule, "kind": tag})
    return n


def _riyadh_hour(ts):
    return time.gmtime(ts + RIYADH).tm_hour


def _send_after(ts, R):
    a, b = R["quiet"]
    h = _riyadh_hour(ts)
    quiet = (a <= h or h < b) if a > b else (a <= h < b)
    if not quiet or a == b:
        return ts
    t = time.gmtime(ts + RIYADH)
    day0 = ts - (t.tm_hour * 3600 + t.tm_min * 60 + t.tm_sec)          # Riyadh midnight, as epoch
    nxt = day0 + b * 3600
    return nxt if nxt > ts else nxt + 86400


def _today_auto(conn, user_id, email, now):
    t = time.gmtime(now + RIYADH)
    day0 = now - (t.tm_hour * 3600 + t.tm_min * 60 + t.tm_sec)
    col, val = ("d.user_id", user_id) if user_id else ("d.email", email)
    return conn.execute("SELECT COUNT(DISTINCT d.message_id) FROM push_deliveries d JOIN push_messages m ON m.id = d.message_id "
                        "WHERE %s = ? AND m.source = 'auto' AND d.status IN ('queued','sent') AND d.send_after >= ?" % col,
                        (val, day0)).fetchone()[0]


def _devices(conn, user_ids=(), emails=()):
    out = {}
    if user_ids:
        ids = list(dict.fromkeys(int(u) for u in user_ids if u))
        for i in range(0, len(ids), 400):
            chunk = ids[i:i + 400]
            for r in conn.execute("SELECT * FROM push_devices WHERE status = 'active' AND user_id IN (%s)" % ",".join("?" * len(chunk)), chunk):
                out[r["id"]] = r
    if emails:
        em = list(dict.fromkeys(str(e).lower() for e in emails if e))
        for r in conn.execute("SELECT * FROM push_devices WHERE status = 'active' AND lower(email) IN (%s)" % ",".join("?" * len(em)), em):
            out[r["id"]] = r
    return list(out.values())


def _make(rule, title, body, url, user_ids=(), emails=(), source="auto", tag=None, audience=None, created_by=None,
          send_at=None, message_id=None):
    """Create (or fill) a message and its deliveries. Returns the number of devices."""
    R = rules()
    now = db.now()
    with db.connect() as conn:
        devs = _devices(conn, user_ids, emails)
        if message_id is None:
            message_id = conn.execute(
                "INSERT INTO push_messages (source, rule, title, body, url, audience, created_by, created_at, send_at, status) "
                "VALUES (?,?,?,?,?,?,?,?,?, 'sending')",
                (source, rule, str(title)[:120], str(body or "")[:300], url, json.dumps(audience or {}), created_by, now,
                 send_at or now)).lastrowid
        people, n = set(), 0
        capped = {}
        for d in devs:
            person = d["user_id"] or (d["email"] or "").lower() or d["id"]
            status, reason = "queued", None
            if source == "auto":
                if person not in capped:
                    capped[person] = _today_auto(conn, d["user_id"], d["email"], now) >= R["daily_max"]
                if capped[person]:
                    status, reason = "skipped", "daily cap"
            after = now if source == "test" else _send_after(max(now, send_at or now), R)
            conn.execute("INSERT INTO push_deliveries (message_id, device_id, user_id, email, token, status, reason, send_after) "
                         "VALUES (?,?,?,?,?,?,?,?)",
                         (message_id, d["id"], d["user_id"], d["email"], secrets.token_urlsafe(9), status, reason, after))
            if status == "queued":
                people.add(person)
                n += 1
        conn.execute("UPDATE push_messages SET people = ?, devices = ?, status = 'sending' WHERE id = ?",
                     (len(people), n, message_id))
    return n


# ----------------------------------------------------------------- manual --

AUDIENCES = ("all", "role", "client", "campaign", "people")


def resolve(aud):
    """Audience -> (user ids, staff emails). aud = {"type", "roles", "clients" (domains), "campaigns", "people", "kam"}."""
    import portal  # noqa: F401  (users table lives there)
    typ = aud.get("type") if aud.get("type") in AUDIENCES else "people"
    users, emails = set(), set()
    with db.connect() as conn:
        active = "status = 'active' AND deleted_at IS NULL"
        if typ == "all":
            users |= {r[0] for r in conn.execute("SELECT id FROM users WHERE " + active)}
            emails |= {r[0].lower() for r in conn.execute("SELECT email FROM admins WHERE disabled_at IS NULL")}
        elif typ == "role":
            roles = set(aud.get("roles") or [])
            staff = {r[0].lower() for r in conn.execute("SELECT email FROM admins WHERE disabled_at IS NULL")}
            if "client" in roles:
                users |= {r["id"] for r in conn.execute("SELECT id, email FROM users WHERE " + active)
                          if (r["email"] or "").lower() not in staff}
            for role in ("kam", "admin"):
                if role in roles:
                    for r in conn.execute("SELECT email, role FROM admins WHERE disabled_at IS NULL"):
                        rr = r["role"] or "owner"
                        if (role == "kam" and rr == "kam") or (role == "admin" and rr in ("owner", "admin")):
                            emails.add(r["email"].lower())
        elif typ == "client":
            doms = [str(d).lower() for d in aud.get("clients") or [] if d]
            for d in doms:
                users |= {r[0] for r in conn.execute("SELECT id FROM users WHERE %s AND (lower(domain) = ? OR lower(email) LIKE ?)" % active,
                                                     (d, "%@" + d))}
        elif typ == "campaign":
            import inbox
            codes = [r["code_id"] for r in conn.execute(
                "SELECT code_id FROM campaigns WHERE id IN (%s)" % ",".join("?" * len(aud.get("campaigns") or [0])),
                [int(x) for x in aud.get("campaigns") or [0]]) if r["code_id"]]
            users |= set(inbox.for_codes(codes))
        else:
            users |= {int(x) for x in aud.get("people") or [] if str(x).isdigit()}
            emails |= {str(x).lower() for x in aud.get("staff") or [] if "@" in str(x)}
        if aud.get("kam") and typ in ("client", "campaign") and users:
            emails |= set(kam_emails_for_users(conn, users))
    return users, emails


def kam_emails_for_users(conn, user_ids):
    import kam_scope
    import notify
    dmap = kam_scope.domain_map()
    out = set()
    ids = list(user_ids)
    for r in conn.execute("SELECT email, kam FROM users WHERE id IN (%s)" % ",".join("?" * len(ids)), ids):
        dom = (r["email"] or "").split("@")[-1].lower()
        k = dmap.get(dom) or notify.kam_address(r["kam"])
        if k:
            out.add(k.lower())
    return out


def reach(aud):
    users, emails = resolve(aud)
    with db.connect() as conn:
        devs = _devices(conn, users, emails)
    pushed = {d["user_id"] or (d["email"] or "").lower() for d in devs}
    return {"people": len(users) + len(emails), "push_people": len(pushed), "devices": len(devs),
            "bell_only": max(0, len(users) - len({d["user_id"] for d in devs if d["user_id"]}))}


def create_message(title, body, url, aud, created_by, send_at=None, test_email=None):
    """A manual push. Lands in every chosen client's bell too (kind "announce"), then goes
    to their phones now or at ``send_at``. ``test_email`` sends only to that person's devices."""
    title, body = str(title or "").strip()[:60], str(body or "").strip()[:180]
    url = str(url or "/account/").strip() or "/account/"
    if not url.startswith(("/", "https://")):
        url = "/" + url
    if not title:
        return None
    now = db.now()
    if test_email:
        return _make("test", title, body, url, emails=[test_email], source="test", created_by=created_by,
                     audience={"type": "test", "email": test_email})
    when = int(send_at) if send_at and int(send_at) > now + 60 else None
    with db.connect() as conn:
        mid = conn.execute("INSERT INTO push_messages (source, rule, title, body, url, audience, created_by, created_at, send_at, status) "
                           "VALUES ('manual', 'manual', ?,?,?,?,?,?,?, ?)",
                           (title, body, url, json.dumps(aud), created_by, now, when or now,
                            "scheduled" if when else "sending")).lastrowid
    if not when:
        _fire_manual(mid)
    return mid


def _fire_manual(mid):
    with db.connect() as conn:
        m = conn.execute("SELECT * FROM push_messages WHERE id = ?", (mid,)).fetchone()
        conn.execute("UPDATE push_messages SET status = 'sending' WHERE id = ?", (mid,))
    aud = json.loads(m["audience"] or "{}")
    users, emails = resolve(aud)
    if users:
        import inbox
        href = m["url"][1:] if m["url"].startswith("/") else m["url"]
        inbox.emit(list(users), "announce", m["title"], body=m["body"], href=href, ref="push:%d" % mid, once=True, push=False)
    _make("manual", m["title"], m["body"], m["url"], users, emails, source="manual", message_id=mid, send_at=db.now())


def cancel(mid):
    with db.connect() as conn:
        n = conn.execute("UPDATE push_messages SET status = 'cancelled' WHERE id = ? AND status = 'scheduled'", (mid,)).rowcount
    return bool(n)


# ------------------------------------------------------------------- send --

def _payload(m, d, unread=None):
    out = {"title": m["title"], "body": m["body"] or "", "url": m["url"] or "/account/", "d": d["id"], "k": d["token"],
           "tag": "m%d" % m["id"], "at": m["created_at"]}
    if unread is not None:
        out["unread"] = unread
    return out


def _send_due(limit=60):
    import webpush
    now = db.now()
    with db.connect() as conn:
        due = conn.execute("SELECT d.*, v.endpoint, v.p256dh, v.auth, v.status AS vstatus FROM push_deliveries d "
                           "JOIN push_devices v ON v.id = d.device_id WHERE d.status = 'queued' AND d.send_after <= ? "
                           "ORDER BY d.id LIMIT ?", (now, limit)).fetchall()
        msgs = {}
        for d in due:
            if d["message_id"] not in msgs:
                msgs[d["message_id"]] = conn.execute("SELECT * FROM push_messages WHERE id = ?", (d["message_id"],)).fetchone()
    sent = 0
    unread_cache = {}
    for d in due:
        m = msgs.get(d["message_id"])
        if m is None or m["status"] == "cancelled" or d["vstatus"] != "active":
            with db.connect() as conn:
                conn.execute("UPDATE push_deliveries SET status = 'skipped', reason = 'device off' WHERE id = ?", (d["id"],))
            continue
        unread = None
        if d["user_id"]:
            if d["user_id"] not in unread_cache:
                try:
                    import inbox
                    import portal
                    u = portal.user_by_id(d["user_id"])
                    unread_cache[d["user_id"]] = inbox.unread(u) if u else None
                except Exception:
                    unread_cache[d["user_id"]] = None
            unread = unread_cache[d["user_id"]]
        try:
            code, gone = webpush.send({"endpoint": d["endpoint"], "keys": {"p256dh": d["p256dh"], "auth": d["auth"]}},
                                      _payload(m, d, unread), ttl=4 * 24 * 3600,
                                      urgency="high" if m["source"] in ("manual", "test") else "normal")
        except Exception as exc:
            code, gone = 0, False
            print("push: send failed:", repr(exc)[:120], flush=True)
        ok = 200 <= code < 300
        with db.connect() as conn:
            conn.execute("UPDATE push_deliveries SET status = ?, http = ?, sent_at = ? WHERE id = ?",
                         ("sent" if ok else ("gone" if gone else "failed"), code, db.now(), d["id"]))
            if ok:
                conn.execute("UPDATE push_devices SET sent = sent + 1, fails = 0 WHERE id = ?", (d["device_id"],))
            elif gone:
                conn.execute("UPDATE push_devices SET status = 'gone' WHERE id = ?", (d["device_id"],))
            else:
                conn.execute("UPDATE push_devices SET fails = fails + 1, status = CASE WHEN fails >= 9 THEN 'gone' ELSE status END "
                             "WHERE id = ?", (d["device_id"],))
        sent += ok
    # Messages with nothing left to send are done.
    with db.connect() as conn:
        conn.execute("UPDATE push_messages SET status = 'sent', sent_at = COALESCE(sent_at, ?) WHERE status = 'sending' "
                     "AND NOT EXISTS (SELECT 1 FROM push_deliveries d WHERE d.message_id = push_messages.id AND d.status = 'queued')",
                     (db.now(),))
    return sent


def ack(did, token, clicked=False):
    try:
        did = int(did)
    except (TypeError, ValueError):
        return False
    col = "clicked_at" if clicked else "acked_at"
    with db.connect() as conn:
        r = conn.execute("SELECT device_id, token, clicked_at, acked_at FROM push_deliveries WHERE id = ?", (did,)).fetchone()
        if r is None or not secrets.compare_digest(str(token or ""), r["token"]):
            return False
        if r[col]:
            return True
        conn.execute("UPDATE push_deliveries SET %s = ? WHERE id = ?" % col, (db.now(), did))
        if clicked:
            if not r["acked_at"]:
                conn.execute("UPDATE push_deliveries SET acked_at = ? WHERE id = ?", (db.now(), did))
            conn.execute("UPDATE push_devices SET clicked = clicked + 1 WHERE id = ?", (r["device_id"],))
    return True


# ------------------------------------------------------------- milestones --

def _fmt(n):
    n = float(n)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div:
            v = n / div
            return ("%d" % v if v == int(v) else ("%.1f" % v).rstrip("0").rstrip(".")) + suf
    return "%d" % n


GOAL_NAMES = {"posts": "Posts", "views": "Views", "engagement": "Engagement", "er": "Engagement rate", "clicks": "Clicks"}


def milestones():
    """Live campaigns: goal steps, view thresholds and new posts, each fired once.
    A campaign seen for the first time is only recorded (no burst of old milestones)."""
    import inbox
    import metrics
    R = rules()
    fired = 0
    with db.connect() as conn:
        camps = conn.execute("SELECT * FROM campaigns WHERE status = 'live' AND code_id IS NOT NULL").fetchall()
    for k in camps:
        try:
            fired += _campaign_milestones(k, R, inbox, metrics)
        except Exception as exc:
            print("push: milestones skipped for campaign %d: %r" % (k["id"], exc), flush=True)
    return fired


def _campaign_milestones(k, R, inbox, metrics):
    fired = 0
    cid = k["id"]
    if True:
        rep = metrics.report(k)
        users = inbox.for_codes([k["code_id"]])
        href = "campaign/#t=" + k["token"]
        with db.connect() as conn:
            done = {r["key"] for r in conn.execute("SELECT key FROM push_milestones WHERE campaign_id = ?", (cid,))}
            seeded = "seed" in done
            st = conn.execute("SELECT * FROM push_camp_state WHERE campaign_id = ?", (cid,)).fetchone()
        new = []                                       # (key, kind, title, body)
        views = (rep.get("total") or {}).get("views") or 0
        hit = [s for s in R["view_steps"] if views >= s and "v%d" % s not in done]
        if hit:
            top = max(hit)
            new += [("v%d" % s, None, None, None) for s in hit if s != top]
            new.append(("v%d" % top, "camp_views", "%s views: %s" % (_fmt(top), k["name"]),
                        "Your campaign passed %s views." % _fmt(top)))
        prog = rep.get("progress") or {}
        for p in (prog.get("items") if isinstance(prog, dict) else prog) or []:
            if p.get("key") not in GOAL_NAMES or not p.get("goal"):
                continue
            hit = [s for s in R["goal_steps"] if p.get("pct", 0) >= s and "g:%s:%d" % (p["key"], s) not in done]
            if hit:
                top = max(hit)
                new += [("g:%s:%d" % (p["key"], s), None, None, None) for s in hit if s != top]
                name = GOAL_NAMES[p["key"]]
                title = ("%s goal reached" % name) if top >= 100 else ("%s goal %d%% reached" % (name, top))
                act = _fmt(p["actual"]) if p["key"] != "er" else "%.2f%%" % (p["actual"] or 0)
                goal = _fmt(p["goal"]) if p["key"] != "er" else "%.2f%%" % p["goal"]
                new.append(("g:%s:%d" % (p["key"], top), "camp_goal", title, "%s of %s on %s." % (act, goal, k["name"])))
        posts = (rep.get("total") or {}).get("posts") or 0
        now = db.now()
        post_note = None
        if st is not None and posts > (st["posts"] or 0) and R.get("posts"):
            if not st["posts"]:
                post_note = ("camp_posts", "First post is live: %s" % k["name"], "The campaign's first post went up. Tap for the report.")
            elif now - (st["posts_push_at"] or 0) >= R["posts_gap_h"] * 3600:
                d = posts - st["posts"]
                post_note = ("camp_posts", "%d new post%s live" % (d, "" if d == 1 else "s"),
                             "%s now has %d post%s live." % (k["name"], posts, "" if posts == 1 else "s"))
        with db.connect() as conn:
            for key, kind, title, body in new:
                conn.execute("INSERT OR IGNORE INTO push_milestones (campaign_id, key, at) VALUES (?,?,?)", (cid, key, now))
            if not seeded:
                conn.execute("INSERT OR IGNORE INTO push_milestones (campaign_id, key, at) VALUES (?, 'seed', ?)", (cid, now))
            if st is None:
                conn.execute("INSERT INTO push_camp_state (campaign_id, posts, posts_push_at) VALUES (?,?,0)", (cid, posts))
            elif post_note or posts < (st["posts"] or 0):
                conn.execute("UPDATE push_camp_state SET posts = ?, posts_push_at = ? WHERE campaign_id = ?",
                             (posts, now if post_note else st["posts_push_at"], cid))
        if not seeded:
            return 0                                    # first sight: record only
        kam = []
        if users:
            with db.connect() as conn:
                kam = list(kam_emails_for_users(conn, users))
        for key, kind, title, body in new + ([("posts",) + post_note] if post_note else []):
            if not kind:
                continue
            ref = "ms:%d:%s" % (cid, key)
            inbox.emit(users, kind, title, body=body, href=href, ref=ref, once=True)
            if kam and R.get("team"):
                _queue.append(("team", kind, title, body, "/" + href, kam))
            fired += 1
    return fired


# ------------------------------------------------------------------- loop --

_started = False


def tick(now=None):
    out = {"queued": _drain(), "sent": 0, "scheduled": 0}
    now = now or db.now()
    with db.connect() as conn:
        due = [r["id"] for r in conn.execute("SELECT id FROM push_messages WHERE status = 'scheduled' AND send_at <= ?", (now,))]
    for mid in due:
        _fire_manual(mid)
        out["scheduled"] += 1
    out["sent"] = _send_due()
    return out


def start():
    global _started
    with _lock:
        if _started:
            return
        _started = True

    def loop():
        time.sleep(20)
        last_ms = 0
        while True:
            try:
                if time.time() - last_ms >= MILESTONE_EVERY:
                    last_ms = time.time()
                    n = milestones()
                    if n:
                        print("push: %d milestone(s)" % n, flush=True)
                out = tick()
                if out["sent"] or out["scheduled"]:
                    print("push:", out, flush=True)
            except Exception as exc:
                print("push: pass skipped:", repr(exc)[:160], flush=True)
            time.sleep(TICK)
    threading.Thread(target=loop, daemon=True, name="push").start()


# --------------------------------------------------------------- reporting --

def overview(days=30):
    since = db.now() - days * 86400
    with db.connect() as conn:
        q = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731
        installed = q("SELECT COUNT(*) FROM app_clients WHERE installed_at IS NOT NULL")
        new_week = q("SELECT COUNT(*) FROM app_clients WHERE installed_at >= ?", db.now() - 7 * 86400)
        on_people = q("SELECT COUNT(DISTINCT COALESCE(user_id, email)) FROM push_devices WHERE status = 'active'")
        devices_on = q("SELECT COUNT(*) FROM push_devices WHERE status = 'active'")
        blocked = q("SELECT COUNT(*) FROM app_clients WHERE permission = 'denied'")
        sent = q("SELECT COUNT(*) FROM push_deliveries WHERE status IN ('sent','failed','gone') AND sent_at >= ?", since)
        ok = q("SELECT COUNT(*) FROM push_deliveries WHERE status = 'sent' AND sent_at >= ?", since)
        acked = q("SELECT COUNT(*) FROM push_deliveries WHERE acked_at IS NOT NULL AND sent_at >= ?", since)
        clicked = q("SELECT COUNT(*) FROM push_deliveries WHERE clicked_at IS NOT NULL AND sent_at >= ?", since)
        mobile = "platform IN ('ios','android')"
        funnel = [
            ("Saw the desktop welcome", q("SELECT COUNT(*) FROM app_clients WHERE welcome_at IS NOT NULL")),
            ("Scanned the QR", q("SELECT COUNT(*) FROM app_handoff WHERE used_at IS NOT NULL")),
            ("Visited on a phone", q("SELECT COUNT(*) FROM app_clients WHERE " + mobile)),
            ("Saw the install guide", q("SELECT COUNT(*) FROM app_clients WHERE guide_at IS NOT NULL AND " + mobile)),
            ("Installed the app", q("SELECT COUNT(*) FROM app_clients WHERE installed_at IS NOT NULL AND " + mobile)),
            ("Asked for alerts", q("SELECT COUNT(*) FROM app_clients WHERE prompted_at IS NOT NULL AND " + mobile)),
            ("Allowed alerts", q("SELECT COUNT(*) FROM app_clients WHERE permission = 'granted' AND " + mobile)),
            ("Tapped a push", q("SELECT COUNT(DISTINCT device_key) FROM push_devices WHERE clicked > 0 AND " + mobile)),
        ]
        plat = {}
        for r in conn.execute("SELECT platform, COUNT(*) n, SUM(CASE WHEN permission = 'granted' THEN 1 ELSE 0 END) g "
                              "FROM app_clients WHERE installed_at IS NOT NULL GROUP BY platform"):
            plat[r["platform"] or "desktop"] = {"installed": r["n"], "on": r["g"] or 0}
        old_ios = q("SELECT COUNT(*) FROM app_clients WHERE platform = 'ios' AND permission = 'unsupported'")
    return {"installed": installed, "new_week": new_week, "on_people": on_people, "devices_on": devices_on,
            "blocked": blocked, "sent": sent, "delivered": ok, "acked": acked, "clicked": clicked,
            "funnel": funnel, "platforms": plat, "old_ios": old_ios}


def people(search="", limit=300):
    """One row per person (account, team member or access code), with their devices."""
    with db.connect() as conn:
        clients = conn.execute("SELECT * FROM app_clients ORDER BY last_seen DESC LIMIT 2000").fetchall()
        devs = conn.execute("SELECT * FROM push_devices WHERE status != 'gone'").fetchall()
        stats = {}
        for r in conn.execute("SELECT COALESCE(CAST(user_id AS TEXT), lower(email)) who, COUNT(*) n, "
                              "SUM(CASE WHEN clicked_at IS NOT NULL THEN 1 ELSE 0 END) c FROM push_deliveries "
                              "WHERE status = 'sent' GROUP BY who"):
            stats[r["who"]] = (r["n"], r["c"] or 0)
        users = {r["id"]: r for r in conn.execute("SELECT id, email, name, company FROM users")}
        staff = {r["email"].lower(): r for r in conn.execute("SELECT email, name, role FROM admins")}
        codes = {r["id"]: r for r in conn.execute("SELECT id, label FROM codes")}
    rows = collections.OrderedDict()
    for c in clients:
        who = ("u", c["user_id"]) if c["user_id"] else (("e", (c["email"] or "").lower()) if c["email"] else ("c", c["code_id"] or c["device_key"]))
        rows.setdefault(who, {"clients": [], "devices": []})["clients"].append(c)
    for d in devs:
        who = ("u", d["user_id"]) if d["user_id"] else (("e", (d["email"] or "").lower()) if d["email"] else ("c", d["code_id"] or d["device_key"]))
        rows.setdefault(who, {"clients": [], "devices": []})["devices"].append(d)
    out = []
    for (t, v), g in rows.items():
        u = users.get(v) if t == "u" else None
        email = (u["email"] if u else (v if t == "e" else "")) or ""
        st = staff.get(email.lower())
        name = (u["name"] if u else None) or (st["name"] if st else None) or (codes[v]["label"] if t == "c" and v in codes else "") or email or "Guest"
        role = ("KAM" if st and st["role"] == "kam" else "Team") if st else ("Client" if u else "Guest")
        cl = g["clients"]
        perms = [c["permission"] for c in cl if c["permission"]]
        active = [d for d in g["devices"] if d["status"] == "active"]
        if active:
            state = "on"
        elif "denied" in perms:
            state = "blocked"
        elif "unsupported" in perms:
            state = "cant"
        else:
            state = "not_asked"
        n, c = stats.get(str(v) if t == "u" else email.lower(), (0, 0))
        raw = {(c2["platform"] or "", c2["os"] or "", c2["browser"] or "") for c2 in cl} | \
            {(d["platform"] or "", d["os"] or "", d["browser"] or "") for d in g["devices"]}
        # The same phone reported by the page and by its subscription: keep the fuller description.
        plats = sorted(x for x in raw if not any(y != x and y[0] == x[0] and (not x[1] or x[1] == y[1]) and (not x[2] or x[2] == y[2])
                                                 for y in raw))
        row = {"key": "%s:%s" % (t, v), "user_id": v if t == "u" else None, "email": email, "name": name, "role": role,
               "company": (u["company"] if u else "") or "", "devices": plats,
               "installed": min([c2["installed_at"] for c2 in cl if c2["installed_at"]] or [0]) or None,
               "last": max([c2["last_seen"] or 0 for c2 in cl] + [d["last_seen_at"] or 0 for d in g["devices"]] or [0]) or None,
               "standalone_last": max([c2["last_launch_at"] or 0 for c2 in cl] or [0]) or None,
               "state": state, "subs": len(active), "pushes": n, "clicks": c}
        hay = " ".join([row["name"], row["email"], row["company"]]).lower()
        if search and search.lower() not in hay:
            continue
        out.append(row)
    return out[:limit]


def history(limit=80):
    with db.connect() as conn:
        rows = conn.execute("SELECT m.*, (SELECT COUNT(*) FROM push_deliveries d WHERE d.message_id = m.id AND d.status = 'sent') ok, "
                            "(SELECT COUNT(*) FROM push_deliveries d WHERE d.message_id = m.id AND d.status IN ('sent','failed','gone')) tried, "
                            "(SELECT COUNT(*) FROM push_deliveries d WHERE d.message_id = m.id AND d.clicked_at IS NOT NULL) clicks, "
                            "(SELECT COUNT(*) FROM push_deliveries d WHERE d.message_id = m.id AND d.status = 'skipped') held "
                            "FROM push_messages m ORDER BY m.id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def rule_counts():
    with db.connect() as conn:
        return {r["rule"]: r["n"] for r in conn.execute(
            "SELECT rule, COUNT(*) n FROM push_messages WHERE source = 'auto' AND devices > 0 GROUP BY rule")}
