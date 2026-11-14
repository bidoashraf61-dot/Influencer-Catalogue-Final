"""Staff-only portal (item 382, Bido 2026-11-15).

While the ``staff_only`` setting is on:

- only addresses on the staff domains (setting ``staff_domains``, default blueholding.co.uk and
  hellovoice.co.uk) can sign in or sign up; everyone else gets the request-access form;
- every other account's pass stops counting (server.viewer_cookie_id asks code_allowed()), so an
  outside client is signed out on their next request. Nothing is deleted: switching the setting off
  lets them straight back in;
- share links (report links /r/, study links, public selection / campaign links, demo trial links)
  are untouched: they never depended on a pass.

The request form files a row in ``invite_requests``. A request is a lead, never an account
(Bido: "Nothing automatic"): the team marks it contacted / declined in Admin > Access requests,
and sends share links by hand. On each request: an email to the owner and info@, and a push to the
owner and admins.
"""
import re
import threading
import time

import db
import guard

DEFAULT_DOMAINS = ("blueholding.co.uk", "hellovoice.co.uk")
STATUSES = ("new", "contacted", "declined")

SCHEMA = """
CREATE TABLE IF NOT EXISTS invite_requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    at          INTEGER NOT NULL,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    company     TEXT NOT NULL,
    phone       TEXT,
    ip          TEXT,
    user_agent  TEXT,
    from_code_id INTEGER,              -- a locked outside account that asked to come back
    status      TEXT NOT NULL DEFAULT 'new',
    note        TEXT,
    decided_at  INTEGER,
    decided_by  TEXT
);
CREATE INDEX IF NOT EXISTS invite_requests_at ON invite_requests(at);
"""

_ready = False


def ensure():
    global _ready
    if _ready:
        return
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(invite_requests)")}
        if "phone" not in cols:                       # added 2026-11-15: the form asks for a phone, company dropped
            conn.execute("ALTER TABLE invite_requests ADD COLUMN phone TEXT")
    _ready = True


# ------------------------------------------------------------------ the switch --

def on():
    v = db.setting("staff_only", False)
    return v is True or str(v).lower() in ("1", "true", "on", "yes")


def set_on(flag, by=""):
    db.set_setting("staff_only", bool(flag))
    _cache.clear()
    try:
        db.log("staff_only", None, None, None, ("on" if flag else "off") + " by " + (by or "?"))
    except Exception:
        pass


def domains():
    raw = db.setting("staff_domains", list(DEFAULT_DOMAINS)) or list(DEFAULT_DOMAINS)
    if isinstance(raw, str):
        raw = raw.replace(",", " ").split()
    out = {str(d).strip().lower().lstrip("@") for d in raw if str(d).strip()}
    return out or set(DEFAULT_DOMAINS)


def is_staff_email(email):
    email = (email or "").strip().lower()
    if "@" not in email:
        return False
    return guard._matches(email.rsplit("@", 1)[1], domains())


# code id -> (checked at, allowed). viewer_cookie_id runs several times a request; a short memo keeps
# it to one users lookup per account every few seconds. Switching the lock clears it.
_cache = {}
_TTL = 15


def code_allowed(code_id):
    """True when this code's pass may open the portal. Always True while the lock is off."""
    if not on():
        return True
    if code_id is None:
        return False
    code_id = int(code_id)
    if code_id == db.admin_code_id():
        return True                          # the internal admin preview code: staff only by construction
    hit = _cache.get(code_id)
    t = time.time()
    if hit and t - hit[0] < _TTL:
        return hit[1]
    with db.connect() as conn:
        u = conn.execute("SELECT email FROM users WHERE code_id = ? AND deleted_at IS NULL", (code_id,)).fetchone()
    ok = bool(u is not None and is_staff_email(u["email"]))
    if len(_cache) > 2000:
        _cache.clear()
    _cache[code_id] = (t, ok)
    return ok


def locked_profile(code_id):
    """{name, email, company} of an outside account the lock shut out, to fill the request form in."""
    if code_id is None:
        return None
    with db.connect() as conn:
        u = conn.execute("SELECT name, email, company, phone FROM users WHERE code_id = ? AND deleted_at IS NULL",
                         (int(code_id),)).fetchone()
    if u is None:
        return None
    return {"name": u["name"] or "", "email": u["email"] or "", "company": u["company"] or "", "phone": u["phone"] or ""}


# ------------------------------------------------------------------- requests --

def _clean(v, n):
    return " ".join(str(v or "").split())[:n]


def clean_phone(raw):
    """'' (none given), the number as typed but tidied, or None when it cannot be a phone number."""
    v = _clean(raw, 40)
    if not v:
        return ""
    digits = re.sub(r"\D", "", v)
    if not 7 <= len(digits) <= 15 or not re.fullmatch(r"[+()\d .\-]+", v):
        return None
    return v


def file_request(name, email, phone=None, ip=None, ua=None, from_code_id=None, company=None):
    """(row id, None) or (None, reason). Name and email are required, the phone is optional (Bido 2026-11-15:
    WhatsApp number instead of company; stored in the phone column). Same email asking again within a day files nothing new."""
    ensure()
    name, company = _clean(name, 80), _clean(company, 120)
    email = guard.normalise_email(email)
    if len(name) < 2:
        return None, "name"
    if not email:
        return None, "email"
    phone = clean_phone(phone)
    if phone is None:
        return None, "phone"
    t = db.now()
    with db.connect() as conn:
        dup = conn.execute("SELECT id FROM invite_requests WHERE email = ? AND at > ? ORDER BY id DESC LIMIT 1",
                           (email, t - 86400)).fetchone()
        if dup is not None:
            return dup["id"], "duplicate"
        if not company and from_code_id:                 # a locked client: their account still names the company
            u = conn.execute("SELECT company FROM users WHERE code_id = ?", (int(from_code_id),)).fetchone()
            company = (u["company"] or "") if u is not None else ""
        cur = conn.execute("INSERT INTO invite_requests (at, name, email, company, phone, ip, user_agent, from_code_id) "
                           "VALUES (?,?,?,?,?,?,?,?)", (t, name, email, company or "", phone, ip, (ua or "")[:200], from_code_id))
        rid = cur.lastrowid
    _alert(rid, name, email, company, phone, from_code_id)
    return rid, None


def listing(status=None, limit=200):
    ensure()
    with db.connect() as conn:
        if status:
            return conn.execute("SELECT * FROM invite_requests WHERE status = ? ORDER BY id DESC LIMIT ?",
                                (status, limit)).fetchall()
        return conn.execute("SELECT * FROM invite_requests ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def count_new():
    ensure()
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM invite_requests WHERE status = 'new'").fetchone()[0]


def decide(rid, status, note, by):
    ensure()
    if status not in STATUSES:
        return False, "Unknown status."
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM invite_requests WHERE id = ?", (int(rid),)).fetchone()
        if r is None:
            return False, "That request no longer exists."
        conn.execute("UPDATE invite_requests SET status = ?, note = COALESCE(NULLIF(?, ''), note), decided_at = ?, "
                     "decided_by = ? WHERE id = ?", (status, _clean(note, 300), db.now(), by, int(rid)))
    return True, "%s marked %s." % (r["name"], status)


# --------------------------------------------------------------------- alerts --

def _people():
    """(email to, push to): owner(s) + info@ by email; owner(s) + admins on their phones."""
    with db.connect() as conn:
        rows = conn.execute("SELECT email, role FROM admins WHERE disabled_at IS NULL").fetchall()
    owners = [r["email"].lower() for r in rows if r["role"] == "owner" and r["email"]]
    admins = [r["email"].lower() for r in rows if r["role"] in ("owner", "admin") and r["email"]]
    mail = db.setting("invite_request_emails", None)
    if isinstance(mail, str):
        mail = mail.replace(",", " ").split()
    mail = [str(x).strip().lower() for x in (mail or owners + ["info@hellovoice.co.uk"]) if "@" in str(x)]
    return list(dict.fromkeys(mail)), list(dict.fromkeys(admins))


def _alert(rid, name, email, company, phone, from_code_id):
    lines = ["%s (%s)%s asked for access to HELVi Connect." % (name, email, (" from " + company) if company else ""),
             ("WhatsApp: " + phone) if phone else "No WhatsApp number given.",
             "They had an account before the portal closed." if from_code_id else "New visitor, no account.",
             "Nothing is granted automatically: contact them and send a share link."]
    link = None
    try:
        import mailer
        link = mailer.SITE.rstrip("/") + "/admin/portal-access"
    except Exception:
        pass
    mail_to, push_to = _people()
    try:
        import push
        push.team("access_request", lines, "/admin/portal-access", push_to)
    except Exception:
        pass

    def run():
        try:
            import mailer
            if not mailer.configured():
                return
            subject = "HELVi Connect · Access requested: %s%s" % (name, (" (%s)" % company) if company else "")
            text = "\n".join(lines) + ("\n\nOpen: " + link if link else "")
            for addr in mail_to[:10]:
                try:
                    try:
                        page = mailer.notify_message("Access requested", lines, link, addr)
                    except Exception:
                        page = None
                    mailer.send(addr, subject, text, html=page, reply_to=email)
                except Exception:
                    pass
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


# ----------------------------------------------------------------- admin page --

def admin_html(query, can_switch):
    import views
    e, u = views.e, views.u
    query = query or {}
    note = ("<div class='ok'>" + e(query.get("ok")) + "</div>") if query.get("ok") else (
        ("<div class='err'>" + e(query.get("e")) + "</div>") if query.get("e") else "")
    state = on()
    sw = ""
    if can_switch:
        sw = ("<form method='post' action='%s' class='sl-sw'><input type='hidden' name='on' value='%s'>"
              "<button class='btn small%s' onclick=\"return confirm('%s')\">%s</button></form>"
              % (e(u("/portal-access/switch")), "0" if state else "1", " ghost" if state else "",
                 "Open the portal to every work email again?" if state else
                 "Close the portal: only %s can sign in, every other account is signed out. Share links keep working. Continue?"
                 % " and ".join(sorted(domains())),
                 "Open the portal again" if state else "Close the portal to staff"))
    status = ("<p class='sec-desc'><span class='pill %s'>%s</span> %s</p>" % (
        "live" if state else "dead", "Staff only" if state else "Open",
        ("Only %s can sign in. Everyone else sees the request form. Share links still open." % ", ".join(sorted(domains())))
        if state else "Any work email can sign up. Switch on to close the portal to staff."))

    def rows(items, pending):
        out = ""
        for r in items:
            if pending:
                ctl = ("<form method='post' action='%s' class='sl-dec'><input type='hidden' name='id' value='%d'>"
                       "<input name='note' placeholder='Note (optional)' size='18' aria-label='Note'>"
                       "<button class='btn tiny' name='status' value='contacted'>Contacted</button>"
                       "<button class='btn tiny ghost' name='status' value='declined'>Decline</button></form>"
                       % (e(u("/portal-access/decide")), r["id"]))
            else:
                ctl = "<span class='pill %s'>%s</span> <span class='muted'>%s · %s</span>%s" % (
                    "live" if r["status"] == "contacted" else "dead", e(r["status"]), e(r["decided_by"] or ""),
                    e(views.ts(r["decided_at"])), ("<div class='muted'>" + e(r["note"]) + "</div>") if r["note"] else "")
            ph = (r["phone"] if "phone" in r.keys() else "") or ""
            tel = ("<a href='https://wa.me/%s' target='_blank' rel='noopener'>%s</a>" % (e(re.sub(r"\D", "", ph)), e(ph))) if ph else "<span class='muted'>—</span>"
            out += ("<tr><td><b>%s</b>%s%s</td><td><a href='mailto:%s'>%s</a></td><td>%s</td><td class='muted'>%s</td><td>%s</td></tr>"
                    % (e(r["name"]), " <span class='pill'>had an account</span>" if r["from_code_id"] else "",
                       ("<div class='muted'>%s</div>" % e(r["company"])) if r["company"] else "",
                       e(r["email"]), e(r["email"]), tel, e(views.ts(r["at"])), ctl))
        return out

    head = "<thead><tr><th>Name</th><th>Email</th><th>WhatsApp</th><th>When</th><th></th></tr></thead>"
    new, done = listing("new"), [r for r in listing() if r["status"] != "new"][:60]
    body = (
        "<div class='card'><div class='hd'><h2>Portal access</h2>" + sw + "</div>" + note + status + "</div>"
        "<div class='card'><div class='hd'><h2>Access requests</h2></div>"
        "<p class='sec-desc'>People who filled in the request form on the closed sign-in page. A request grants nothing: "
        "contact them, send a share link if it fits, then mark it.</p>"
        "<table class='tbl'>" + head + "<tbody>" + (rows(new, True) or "<tr><td colspan='5' class='muted'>Nothing waiting.</td></tr>")
        + "</tbody></table></div>"
        "<div class='card'><div class='hd'><h2>Answered</h2></div><table class='tbl'>" + head + "<tbody>"
        + (rows(done, False) or "<tr><td colspan='5' class='muted'>None yet.</td></tr>") + "</tbody></table></div>"
        "<style>.sl-dec{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:0}.sl-dec input{min-height:32px;padding:2px 8px;"
        "border:1px solid var(--line-strong);border-radius:8px;font:inherit}.sl-sw{margin:0}</style>")
    return views.page("Portal access", body, "/portal-access")
