"""Trial share links (item 271, Bido 2026-10-28): a prospect opens the BlueHolding demo company with no sign-in.

The demo is a company with Helvi Selection, Track and Intelligence at manage, holding demo data only. It is not
a row in the live database: it lives in ``trial/template.db``, built from a copy of the live database by
``tools/trial_template.py`` with everything that is not demo data deleted (whitelist: a table not named there
is emptied). Each link gets its own copy, ``trial/links/<id>.db``, so a visitor can create a campaign or name a
competitor and only they see it; the copy is deleted when the link has ended.

Two processes, so real data is never even in memory where a trial request runs:

* **The main service** (port 8900) keeps the links (``trial_links``, ``trial_contacts`` in catalogue.db).
  ``/try/<token>`` sets the ``hv_trial`` cookie and lands on the workspace; every later request carrying that
  cookie (and no admin session) is forwarded unchanged to the trial process, naming the link's copy.
* **The trial process** (127.0.0.1:8901, ``server.py --trial``) is the same code started with ``HV_TRIAL=1``:
  it opens only files under ``trial/``, has no admin session, sees the visitor as the demo company's owner,
  starts no scheduler, refuses every outbound connection (no Apify, Gemini, email or push) and accepts only
  the POSTs listed in ``POST_OK``.
"""
import hashlib
import hmac
import http.client
import json
import os
import re
import secrets
import shutil
import socket
from pathlib import Path

import db

HERE = Path(__file__).resolve().parent
DIR = HERE / "trial"
TEMPLATE = DIR / "template.db"
LINKS = DIR / "links"
PORT = int(os.environ.get("HV_TRIAL_PORT") or 8901)
COOKIE = "hv_trial"
DAYS = 14
DEMO_CODE = 9001                 # the demo company's code inside every trial database
DEMO_USER = 9001                 # its owner, the person every visitor is
ACTIVE = os.environ.get("HV_TRIAL") == "1"     # True in the trial process only
HDR_LINK = "X-HV-Trial-Link"
HDR_NAME = "X-HV-Trial-Client"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trial_links (
    id           INTEGER PRIMARY KEY,
    token        TEXT NOT NULL UNIQUE,
    client       TEXT NOT NULL,
    note         TEXT,
    created_by   TEXT,
    created_at   INTEGER NOT NULL,
    expires_at   INTEGER NOT NULL,
    revoked_at   INTEGER,
    opens        INTEGER NOT NULL DEFAULT 0,
    first_open_at INTEGER,
    last_open_at INTEGER,
    requests     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS trial_contacts (
    id       INTEGER PRIMARY KEY,
    link_id  INTEGER NOT NULL,
    at       INTEGER NOT NULL,
    name     TEXT,
    email    TEXT,
    phone    TEXT,
    message  TEXT,
    ip       TEXT,
    handled_at INTEGER,
    handled_by TEXT
);
"""


def init():
    with db.connect() as c:
        c.executescript(SCHEMA)
    LINKS.mkdir(parents=True, exist_ok=True)


# ===================================================================== main service: the links ==

def create(client, days=DAYS, note="", by=""):
    client = re.sub(r"\s+", " ", str(client or "")).strip()[:60]
    if not client:
        raise ValueError("Name the client the link is for.")
    days = max(1, min(int(days or DAYS), 90))
    now = db.now()
    with db.connect() as c:
        rid = c.execute("INSERT INTO trial_links (token, client, note, created_by, created_at, expires_at) "
                        "VALUES (?,?,?,?,?,?)", (secrets.token_urlsafe(12), client, (note or "")[:200], by, now,
                                                 now + days * 86400)).lastrowid
    return link(rid)


def link(rid=None, token=None):
    with db.connect() as c:
        if token is not None:
            return c.execute("SELECT * FROM trial_links WHERE token = ?", (str(token),)).fetchone()
        return c.execute("SELECT * FROM trial_links WHERE id = ?", (int(rid or 0),)).fetchone()


def listing():
    with db.connect() as c:
        rows = c.execute("SELECT * FROM trial_links ORDER BY id DESC LIMIT 300").fetchall()
        asks = {}
        for r in c.execute("SELECT link_id, COUNT(*) n FROM trial_contacts GROUP BY link_id"):
            asks[r["link_id"]] = r["n"]
    return rows, asks


def contacts(limit=100):
    with db.connect() as c:
        return c.execute("SELECT t.*, l.client FROM trial_contacts t LEFT JOIN trial_links l ON l.id = t.link_id "
                         "ORDER BY t.id DESC LIMIT ?", (limit,)).fetchall()


def extend(rid, days=DAYS):
    r = link(rid)
    if r is None:
        return False
    base = max(r["expires_at"], db.now())
    with db.connect() as c:
        c.execute("UPDATE trial_links SET expires_at = ?, revoked_at = NULL WHERE id = ?",
                  (base + max(1, min(int(days), 90)) * 86400, r["id"]))
    return True


def revoke(rid):
    with db.connect() as c:
        c.execute("UPDATE trial_links SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL", (db.now(), int(rid)))
    drop_copy(int(rid))
    return True


def reset(rid):
    """Throw the link's copy away: the next visit starts from the template again."""
    drop_copy(int(rid))


def is_open(r):
    return r is not None and r["revoked_at"] is None and r["expires_at"] > db.now()


def copy_path(rid):
    return LINKS / ("%d.db" % int(rid))


def drop_copy(rid):
    for suffix in ("", "-wal", "-shm", "-journal"):
        try:
            os.remove(str(copy_path(rid)) + suffix)
        except FileNotFoundError:
            pass


def sweep():
    """Delete the copies of links that have ended (a day after, so a late page load still says 'ended')."""
    cut = db.now() - 86400
    with db.connect() as c:
        dead = [r["id"] for r in c.execute("SELECT id FROM trial_links WHERE expires_at < ? OR revoked_at IS NOT NULL",
                                           (cut,))]
    for rid in dead:
        if copy_path(rid).exists():
            drop_copy(rid)


def ensure_copy(r):
    """The link's own database, made from the template on its first visit and named for its client."""
    dst = copy_path(r["id"])
    if dst.exists():
        return dst
    if not TEMPLATE.exists():
        raise RuntimeError("The demo template has not been built yet (tools/trial_template.py).")
    LINKS.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp")
    shutil.copyfile(TEMPLATE, tmp)
    import sqlite3
    c = sqlite3.connect(str(tmp))
    try:
        c.execute("UPDATE users SET name = ?, company = ? WHERE id = ?", (r["client"], r["client"], DEMO_USER))
        c.execute("INSERT INTO tenant_settings (code_id, key, value, changed_at, changed_by) VALUES (?,?,?,?,?) "
                  "ON CONFLICT(code_id, key) DO UPDATE SET value = excluded.value",
                  (DEMO_CODE, "brand_name", r["client"], db.now(), "trial"))
        c.commit()
    finally:
        c.close()
    os.replace(tmp, dst)
    return dst


def opened(r, first_visit):
    with db.connect() as c:
        c.execute("UPDATE trial_links SET opens = opens + ?, requests = requests + 1, last_open_at = ?, "
                  "first_open_at = COALESCE(first_open_at, ?) WHERE id = ?",
                  (1 if first_visit else 0, db.now(), db.now(), r["id"]))


# The cookie names the link and is signed, so it cannot be edited into another link's id.
def _sig(secret, rid, token):
    return hmac.new(secret.encode() if isinstance(secret, str) else secret, ("%d:%s" % (rid, token)).encode(),
                    hashlib.sha256).hexdigest()[:24]


def cookie_value(secret, r):
    return "%d.%s" % (r["id"], _sig(secret, r["id"], r["token"]))


def from_cookie(secret, raw):
    """(link row or None, present): present is True when a trial cookie was sent at all."""
    m = re.fullmatch(r"(\d{1,9})\.([0-9a-f]{24})", raw or "")
    if not m:
        return None, bool(raw)
    r = link(int(m.group(1)))
    if r is None or not hmac.compare_digest(_sig(secret, r["id"], r["token"]), m.group(2)):
        return None, True
    return r, True


def state(r):
    left = max(0, r["expires_at"] - db.now())
    return {"trial": True, "client": r["client"], "ends_at": r["expires_at"], "days_left": -(-left // 86400),
            "open": is_open(r)}


def contact(r, b, ip):
    name = str(b.get("name") or "").strip()[:80]
    email = str(b.get("email") or "").strip()[:120]
    phone = str(b.get("phone") or "").strip()[:40]
    msg = str(b.get("message") or "").strip()[:1000]
    if not name or not (email or phone):
        return False, "Add your name and an email or phone number."
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return False, "That email does not look right."
    with db.connect() as c:
        recent = c.execute("SELECT COUNT(*) n FROM trial_contacts WHERE link_id = ? AND at > ?",
                           (r["id"], db.now() - 3600)).fetchone()["n"]
        if recent >= 5:
            return False, "Thanks, we already have your message. We will be in touch."
        c.execute("INSERT INTO trial_contacts (link_id, at, name, email, phone, message, ip) VALUES (?,?,?,?,?,?,?)",
                  (r["id"], db.now(), name, email, phone, msg, ip))
    try:
        import notify
        notify.send("Trial request", ["Trial: %s" % r["client"], "From: %s" % name, "Email: %s" % (email or "—"),
                                      "Phone: %s" % (phone or "—"), "", msg or "(no message)"],
                    link="/tenants/requests")
    except Exception as e:                       # the request is stored either way
        print("trial contact notify:", repr(e)[:120], flush=True)
    return True, "Thanks %s. HelloVoice will contact you within one working day." % name.split(" ")[0]


# Headers that describe the connection, not the request: never passed through the forwarder.
_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
        "transfer-encoding", "upgrade", "content-length", "host"}


def forward(h, r):
    """Send this request to the trial process for link ``r`` and relay its answer, as it is."""
    first = not copy_path(r["id"]).exists()
    try:
        ensure_copy(r)
    except Exception as e:
        print("trial copy:", repr(e)[:200], flush=True)
        return h.send(503, "The demo is being prepared. Try again in a minute.".encode(), "text/plain; charset=utf-8")
    opened(r, first)
    body = h.body() if h.command == "POST" else None
    hdrs = {k: v for k, v in h.headers.items() if k.lower() not in _HOP and not k.lower().startswith("x-hv-")}
    hdrs[HDR_LINK] = str(r["id"])
    hdrs[HDR_NAME] = r["client"].encode("utf-8").hex()
    hdrs["X-Forwarded-For"] = h.client_ip()
    if body is not None:
        hdrs["Content-Length"] = str(len(body))
    try:
        conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=90)
        conn.request(h.command, h.path, body=body, headers=hdrs)
        resp = conn.getresponse()
        data = resp.read()
        out = [(k, v) for k, v in resp.getheaders() if k.lower() not in _HOP and k.lower() != "server"
               and k.lower() != "date"]
        conn.close()
    except (OSError, http.client.HTTPException) as e:
        print("trial forward:", repr(e)[:200], flush=True)
        return h.send(503, "The demo is restarting. Try again in a minute.".encode(), "text/plain; charset=utf-8")
    h.send_response(resp.status)
    for k, v in out:
        h.send_header(k, v)
    h.send_header("Content-Length", str(len(data)))
    h.end_headers()
    if h.command != "HEAD":
        h.wfile.write(data)


# ================================================================ the trial process ==

def _no_network(*a, **k):
    raise OSError("Not available in the trial: nothing leaves the demo.")


def activate():
    """Called once when the trial process starts: never connect anywhere, never open catalogue.db."""
    import socket as _s
    host_ok = ("127.0.0.1", "localhost")
    real = _s.create_connection

    def guarded(address, *a, **k):
        # Only the trial process itself (the assistant's loopback bridge) is reachable, on its own port.
        if address and address[0] in host_ok and int(address[1]) == PORT:
            return real(address, *a, **k)
        return _no_network()
    _s.create_connection = guarded
    import smtplib
    smtplib.SMTP.connect = lambda self, *a, **k: _no_network()
    db.DB_PATH = TEMPLATE
    LINKS.mkdir(parents=True, exist_ok=True)


ON_FIRST_USE = None              # set by server.trial_main
_ready = set()
_ready_lock = __import__("threading").Lock()


def begin(h):
    """Point this request at its link's copy. False when the request did not come from the main service."""
    raw = h.headers.get(HDR_LINK, "")
    if not raw.isdigit() or h.client_address[0] not in ("127.0.0.1", "::1"):
        db.use_path(TEMPLATE)
        return False
    p = copy_path(int(raw))
    if not p.exists():
        db.use_path(TEMPLATE)
        return False
    db.use_path(p)
    if str(p) not in _ready:
        with _ready_lock:
            if str(p) not in _ready and ON_FIRST_USE is not None:
                try:
                    ON_FIRST_USE()             # the same schema steps the process ran on start, for a copy made earlier
                except Exception as e:
                    print("trial copy init:", repr(e)[:200], flush=True)
            _ready.add(str(p))
    return True


def end():
    db.use_path(None)


def client_name(h):
    try:
        return bytes.fromhex(h.headers.get(HDR_NAME, "")).decode("utf-8")[:60]
    except ValueError:
        return ""


# What a visitor may change: their own copy's data, nothing that spends, sends, uploads or signs in.
POST_OK = {
    "/api/my/campaign", "/api/my/post", "/api/my/competitor",
    "/api/workspace/pref", "/api/workspace/role", "/api/workspace/decide",
    "/api/selection/status", "/api/selection/reason", "/api/selection/tags", "/api/selection/platform",
    "/api/selection/status/bulk", "/api/selection/tags/bulk", "/api/selection/views", "/api/selection/order",
    "/api/selection/rename", "/api/selection/alike", "/api/selection/mergeable", "/api/selection/scores",
    "/api/board/stage", "/api/board/pin", "/api/board/save", "/api/board/targets", "/api/board/plan",
    "/api/board/edit", "/api/board/selection-stage", "/api/board/live",
    "/api/roi/estimate", "/api/roi/save", "/api/roi/vs",
    "/api/analysis/decide", "/api/notifications/read", "/api/event", "/api/tour", "/api/timing",
    "/api/campaign/share", "/api/campaign/next",
}
REFUSED = {"ok": False, "reason": "trial",
           "error": "Not in the trial: this is where HelloVoice would do it for real. Ask us from the banner.",
           "message": "Not in the trial: this is where HelloVoice would do it for real. Ask us from the banner."}


def post_allowed(path):
    return path in POST_OK


# Pages the trial process may answer outside /api/: the public tracking pages. Anything else (the admin) is
# never a trial page; the visitor goes back to their workspace.
def page_allowed(path):
    return path.startswith(("/go/", "/insights/", "/api/"))


# ===================================================================== pages ==

def _esc(v):
    import html
    return html.escape(str(v if v is not None else ""), quote=True)


def page(r, kind):
    """The few pages /try/ answers itself: ended, missing, preparing, and a staff note."""
    client = r["client"] if r is not None else ""
    title, text, extra = {
        "ended": ("This trial has ended", "The demo link%s is no longer open. Ask HelloVoice for a new one."
                  % ((" for " + _esc(client)) if client else ""), ""),
        "missing": ("Link not found", "Check the address you were given, or ask HelloVoice for a new link.", ""),
        "preparing": ("Getting the demo ready", "This takes a few seconds. Reload the page in a moment.", ""),
        "staff": ("You are signed in as HelloVoice", "Staff are never a trial visitor, so this link would show you the "
                  "real portal. Open it in a private window to see exactly what %s will see." % _esc(client),
                  "<p class='t-url'><code>%s</code></p>" % _esc("/admin/try/" + r["token"] if r is not None else "")),
    }[kind]
    return ("<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
            "initial-scale=1'><meta name='robots' content='noindex,nofollow'><title>%s · HELVi Connect</title>"
            "<link rel='stylesheet' href='/assets/css/catalogue.css'><style>"
            "body{margin:0;min-height:100vh;display:grid;place-items:center;background:#e9dcd2;color:#121212;"
            "font:400 17px/1.6 'DM Sans',Arial,sans-serif;padding:24px;box-sizing:border-box}"
            "main{max-width:560px;background:#fff;border-radius:28px;padding:40px 36px;box-shadow:0 24px 50px -30px rgba(0,0,0,.35)}"
            "img{height:56px;width:auto;margin:0 0 28px}h1{font:400 clamp(2.4rem,1.7rem + 2vw,3.4rem)/.95 Bebasneue,'Bebas Neue',"
            "Arial,sans-serif;margin:0 0 14px;letter-spacing:.01em}p{margin:0 0 18px;color:#383838}"
            "a.t-btn{display:inline-block;font:400 20px/1 Bebasneue,'Bebas Neue',Arial,sans-serif;letter-spacing:.06em;"
            "background:#121212;color:#fff;text-decoration:none;border-radius:999px;padding:15px 24px 13px}"
            "a.t-btn:hover{background:#383838}a.t-btn:focus-visible{outline:3px solid #ff691e;outline-offset:3px}"
            ".t-url code{font-size:14px;background:#efece6;padding:6px 10px;border-radius:6px;word-break:break-all}"
            "</style></head><body><main><img src='/assets/brand/helvy-connect/helvy-connect-light-320.webp' alt='HELVi Connect'>"
            "<h1>%s</h1><p>%s</p>%s<a class='t-btn' href='https://hellovoice.co.uk/contact-us/'>Contact HelloVoice</a>"
            "</main></body></html>" % (_esc(title), _esc(title), text, extra))


def admin_html(query=None, base_url=""):
    """Admin › Tenants › Demo links: make, copy, extend, reset and end trial links; the requests they sent."""
    import views
    e, u = views.e, views.u
    query = query or {}
    sweep()
    rows, asks = listing()
    now = db.now()
    note = ""
    if query.get("ok"):
        note = "<div class='ok'>" + e(query.get("ok")) + "</div>"
    elif query.get("e"):
        note = "<div class='err'>" + e(query.get("e")) + "</div>"
    if not TEMPLATE.exists():
        note += ("<div class='err'>The demo template is not built yet, so links cannot open. Build it with "
                 "<code>tools/trial_template.py</code> (docs/TRIAL-LINKS.md).</div>")
    fresh = query.get("new")
    trs = []
    for r in rows:
        live = is_open(r)
        url = base_url + u("/try/" + r["token"])
        st = ("<span class='pill live'>Open</span>" if live else
              "<span class='pill dead'>%s</span>" % ("Ended" if r["revoked_at"] else "Expired"))
        left = ("%d days left" % (-(-(r["expires_at"] - now) // 86400))) if live else views.ts(r["revoked_at"] or r["expires_at"])
        acts = ""
        if live:
            acts = ("<button type='button' class='btn tiny' data-copy='%s'>Copy link</button>" % e(url) +
                    "".join("<form method='post' action='%s' class='tl-f'><input type='hidden' name='id' value='%d'>"
                            "<button class='btn tiny ghost' name='do' value='%s'%s>%s</button></form>"
                            % (e(u("/tenants/trials/act")), r["id"], v, c, lab)
                            for v, lab, c in (("extend", "+14 days", ""),
                                              ("reset", "Reset data", " data-ask='Throw away what the visitor changed? Their next visit starts from the demo again.'"),
                                              ("revoke", "End now", " data-ask='End this link now? It stops working at once.'"))))
        else:
            acts = ("<form method='post' action='%s' class='tl-f'><input type='hidden' name='id' value='%d'>"
                    "<button class='btn tiny ghost' name='do' value='extend'>Reopen 14 days</button></form>"
                    % (e(u("/tenants/trials/act")), r["id"]))
        trs.append("<tr%s><th scope='row'><b>%s</b><div class='muted'>%s</div></th><td>%s<div class='muted'>%s</div></td>"
                   "<td>%d</td><td>%s</td><td>%s</td><td>%s</td><td class='tl-acts'>%s</td></tr>" % (
                       " class='tl-new'" if fresh and str(r["id"]) == fresh else "",
                       e(r["client"]), e(r["note"] or ""), st, e(left), r["opens"],
                       e(views.ts(r["last_open_at"])) if r["last_open_at"] else "<span class='muted'>Not opened</span>",
                       ("<a href='#tl-asks'>%d</a>" % asks[r["id"]]) if asks.get(r["id"]) else "—",
                       e(r["created_by"] or ""), acts))
    ask_rows = "".join(
        "<tr><th scope='row'><b>%s</b><div class='muted'>%s</div></th><td>%s</td><td>%s<div class='muted'>%s</div></td>"
        "<td>%s</td></tr>" % (e(c["client"] or "—"), e(views.ts(c["at"])), e(c["name"]), e(c["email"] or "—"),
                              e(c["phone"] or ""), e(c["message"] or "")) for c in contacts())
    body = (
        "<div class='card'><div class='hd'><h2>Demo links</h2><div class='hd-acts'><a class='btn small ghost' href='"
        + e(u("/tenants")) + "'>All tenants</a></div></div>" + note +
        "<p class='sec-desc'>A link opens the BlueHolding demo company (Selection, Track and Intelligence, all at manage) "
        "with sample data only, no sign-in. Each link has its own copy: what the visitor creates only they see, nothing "
        "spends AI or Apify credit, nothing is emailed. The copy is deleted when the link ends.</p>"
        "<form method='post' action='" + e(u("/tenants/trials/new")) + "' class='tl-new-f'>"
        "<label>Client<input name='client' required maxlength='60' placeholder='e.g. Bayer'></label>"
        "<label>Days<input name='days' type='number' min='1' max='90' value='14'></label>"
        "<label class='tl-grow'>Note <span class='muted'>(for you)</span><input name='note' maxlength='200' placeholder='e.g. Sent to Sara after the Derm congress'></label>"
        "<button class='btn'>Make link</button></form>"
        "<p class='muted tl-tip'>To land on one page, add <code>?to=</code> and the page, e.g. <code>…/try/&lt;token&gt;?to=/campaign/dashboard/</code>. "
        "The visitor can still move anywhere in the demo.</p></div>"
        "<div class='card'><table class='tbl'><thead><tr><th>Client</th><th>Status</th><th>Visits</th><th>Last seen</th>"
        "<th>Requests</th><th>Made by</th><th></th></tr></thead><tbody>"
        + ("".join(trs) or "<tr><td colspan='7' class='muted'>No links yet.</td></tr>") + "</tbody></table></div>"
        "<div class='card' id='tl-asks'><div class='hd'><h2>Requests from trials</h2></div>"
        "<p class='sec-desc'>Sent from the trial banner's Talk to HelloVoice form. The team is also emailed.</p>"
        "<table class='tbl'><thead><tr><th>Trial</th><th>Name</th><th>Contact</th><th>Message</th></tr></thead><tbody>"
        + (ask_rows or "<tr><td colspan='4' class='muted'>None yet.</td></tr>") + "</tbody></table></div>"
        "<style>.tl-new-f{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin:8px 0 10px}"
        ".tl-new-f label{display:flex;flex-direction:column;gap:4px;font-weight:600;font-size:13px}.tl-grow{flex:1 1 260px}"
        ".tl-new-f input{min-height:40px;padding:6px 10px;border:1px solid var(--line-strong);border-radius:8px;font:inherit}"
        ".tl-new-f input[type=number]{width:80px}.tl-acts{display:flex;gap:6px;flex-wrap:wrap;align-items:center}"
        ".tl-f{margin:0}.tl-new{background:var(--lime-soft,#f6ffd2)}.tl-tip{margin:0}.tl-tip code{font-size:12px}</style>"
        "<script>document.addEventListener('click',function(ev){var b=ev.target.closest('[data-copy]');if(b){"
        "var t=b.getAttribute('data-copy');(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){"
        "b.textContent='Copied';setTimeout(function(){b.textContent='Copy link'},1600)},function(){window.prompt('Copy the link',t)});return}"
        "var a=ev.target.closest('[data-ask]');if(a&&!confirm(a.getAttribute('data-ask')))ev.preventDefault();});</script>")
    return views.page("Demo links", body, "/tenants")
