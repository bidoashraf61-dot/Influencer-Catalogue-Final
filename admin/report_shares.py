"""Client report links (item 291, Bido 2026-11-03): the portal is for BlueHolding; clients get reports.

One secret link opens ONE report, with no sign-in and no way into the rest of the portal: a Track campaign
dashboard, a selection (shortlist), a creator's full analysis, or the competitor study filed under a selection.
The data is live (the page reads the portal as it is now), stamped "Data as of" on screen and in the PDF.

* A link is a row in ``report_shares``: kind + ref (the campaign or selection token, or the creator code),
  who it is for (label), when it ends (expires_at) and whether it was revoked. Owner/admin accounts and the
  account's KAM make them; every make and revoke is in History (entity "share", so Undo works).
* The link is ``/report/#r=<token>``. That page asks ``/api/report`` what the token opens; the answer sets the
  ``hv_report`` cookie (the tokens this browser holds) and the page moves to the report itself with ``&r=``.
* The server lets a share in exactly where a public read-only link (``public_links``) is let in: the client's
  view with money taken out, every write refused. Two exceptions: a selection link may show prices when the
  maker ticked it, and it may approve, reject and comment on creators (selection_status, by "<label> (shared
  link)") so the decision comes back to the portal.
* Ended and revoked links answer 410; nothing is deleted, so the list keeps who opened what and how often.
"""
import re
import secrets

import db

KINDS = {"campaign": "Track campaign", "selection": "Selection", "creator": "Creator analysis",
         "study": "Competitor study"}
DAYS = (7, 14, 30, 90)
DEFAULT_DAYS = 30
COOKIE = "hv_report"

SCHEMA = """
CREATE TABLE IF NOT EXISTS report_shares (
    id            INTEGER PRIMARY KEY,
    token         TEXT NOT NULL UNIQUE,
    kind          TEXT NOT NULL,
    ref           TEXT NOT NULL,
    title         TEXT,
    label         TEXT,
    prices        INTEGER NOT NULL DEFAULT 0,
    created_by    TEXT,
    created_at    INTEGER NOT NULL,
    expires_at    INTEGER NOT NULL,
    revoked_at    INTEGER,
    revoked_by    TEXT,
    opens         INTEGER NOT NULL DEFAULT 0,
    first_open_at INTEGER,
    last_open_at  INTEGER
);
CREATE INDEX IF NOT EXISTS report_shares_item ON report_shares (kind, ref);
"""


def init():
    with db.connect() as c:
        c.executescript(SCHEMA)


def _clean(s, n):
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def create(kind, ref, title="", label="", days=DEFAULT_DAYS, prices=False, by=""):
    """A new link. ``title`` is the report's name as it stood (shown in lists after a rename or delete)."""
    import history
    if kind not in KINDS:
        raise ValueError("Unknown report.")
    ref = _clean(ref, 80)
    if not ref:
        raise ValueError("Unknown report.")
    try:
        days = int(days or DEFAULT_DAYS)
    except (TypeError, ValueError):
        days = DEFAULT_DAYS
    days = max(1, min(days, 365))
    now = db.now()
    with db.connect() as c:
        rid = c.execute("INSERT INTO report_shares (token, kind, ref, title, label, prices, created_by, created_at, expires_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (secrets.token_urlsafe(18), kind, ref, _clean(title, 120), _clean(label, 80),
                         1 if (prices and kind == "selection") else 0, by, now, now + days * 86400)).lastrowid
    r = get(rid=rid)
    history.record("created", "share", rid, "Shared %s with a client link: %s" % (KINDS[kind].lower(), r["title"] or ref),
                   None, history.snapshot("share", rid))
    return r


def get(rid=None, token=None):
    with db.connect() as c:
        if token is not None:
            return c.execute("SELECT * FROM report_shares WHERE token = ?", (str(token),)).fetchone()
        return c.execute("SELECT * FROM report_shares WHERE id = ?", (int(rid or 0),)).fetchone()


def is_open(r):
    return r is not None and r["revoked_at"] is None and r["expires_at"] > db.now()


def state(r):
    if r is None:
        return "unknown"
    if r["revoked_at"] is not None:
        return "revoked"
    return "open" if r["expires_at"] > db.now() else "ended"


def valid(token, kind=None, ref=None):
    """The open link behind ``token`` when it opens ``kind`` (one kind or a tuple) for ``ref``, else None."""
    token = str(token or "").strip()
    if not token or len(token) > 64:
        return None
    r = get(token=token)
    if not is_open(r):
        return None
    if kind is not None and r["kind"] not in ((kind,) if isinstance(kind, str) else tuple(kind)):
        return None
    if ref is not None and r["ref"] != str(ref):
        return None
    return r


def touch(r):
    now = db.now()
    with db.connect() as c:
        c.execute("UPDATE report_shares SET opens = opens + 1, first_open_at = COALESCE(first_open_at, ?), "
                  "last_open_at = ? WHERE id = ?", (now, now, r["id"]))


def revoke(rid, by=""):
    import history
    r = get(rid=rid)
    if r is None or r["revoked_at"] is not None:
        return r
    before = history.snapshot("share", r["id"])
    with db.connect() as c:
        c.execute("UPDATE report_shares SET revoked_at = ?, revoked_by = ? WHERE id = ?", (db.now(), by, r["id"]))
    history.record("edited", "share", r["id"], "Revoked the client link to %s" % (r["title"] or r["ref"]),
                   before, history.snapshot("share", r["id"]))
    return get(rid=r["id"])


def edit(rid, by="", label=None, prices=None, extend=None):
    """Change an open or ended link (item 296): rename it, show or hide prices (selection only), or add ``extend``
    days from today or from its end, whichever is later (an ended link opens again). A revoked link stays closed."""
    import history
    r = get(rid=rid)
    if r is None or r["revoked_at"] is not None:
        return r
    sets, args, said = [], [], []
    if label is not None and _clean(label, 80) != (r["label"] or ""):
        sets.append("label = ?"); args.append(_clean(label, 80)); said.append("renamed it")
    if prices is not None and r["kind"] == "selection" and bool(prices) != bool(r["prices"]):
        sets.append("prices = ?"); args.append(1 if prices else 0); said.append("prices on" if prices else "prices off")
    if extend:
        try:
            days = max(1, min(int(extend), 365))
        except (TypeError, ValueError):
            days = 7
        now = db.now()
        sets.append("expires_at = ?"); args.append(min(max(now, r["expires_at"]) + days * 86400, now + 365 * 86400))
        said.append("+%d days" % days)
    if not sets:
        return r
    before = history.snapshot("share", r["id"])
    sel = db.selection(token=r["ref"], deleted=True) if r["kind"] == "selection" and "label = ?" in sets else None
    with db.connect() as c:
        c.execute("UPDATE report_shares SET %s WHERE id = ?" % ", ".join(sets), args + [r["id"]])
        if sel is not None:
            # The decisions made through the link carry its name (feedback()): they follow the rename.
            c.execute("UPDATE selection_status SET by_name = ? WHERE selection_id = ? AND by_name = ?",
                      (((_clean(label, 80) or "Client") + " (shared link)")[:80], sel["id"],
                       ((r["label"] or "Client") + " (shared link)")[:80]))
    history.record("edited", "share", r["id"], "Client link to %s: %s" % (r["title"] or r["ref"], ", ".join(said)),
                   before, history.snapshot("share", r["id"]))
    return get(rid=r["id"])


def feedback(r):
    """What a selection link's holder decided: the creators approved, rejected or noted as "<label> (shared link)"
    (server._status_who). None for other kinds."""
    if r["kind"] != "selection":
        return None
    sel = db.selection(token=r["ref"], deleted=True)
    if sel is None:
        return None
    by = ((r["label"] or "Client") + " (shared link)")[:80]
    with db.connect() as c:
        rows = c.execute("SELECT status, COUNT(*), SUM(CASE WHEN COALESCE(note, '') <> '' THEN 1 ELSE 0 END) "
                         "FROM selection_status WHERE selection_id = ? AND by_name = ? GROUP BY status",
                         (sel["id"], by)).fetchall()
    out = {"approved": 0, "rejected": 0, "review": 0, "notes": 0}
    for st, n, notes in rows:
        if st in out:
            out[st] += n
        out["notes"] += notes or 0
    return out


def for_item(kind, ref, limit=30):
    """An item's links, open ones first, newest first."""
    with db.connect() as c:
        rows = c.execute("SELECT * FROM report_shares WHERE kind = ? AND ref = ? ORDER BY id DESC LIMIT ?",
                         (kind, str(ref), int(limit))).fetchall()
    return sorted(rows, key=lambda r: 0 if is_open(r) else 1)


def listing(limit=400):
    with db.connect() as c:
        return c.execute("SELECT * FROM report_shares ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()


def page(r):
    """Where the report itself lives on the site (relative to the site root)."""
    t = r["token"]
    return {"campaign": "/campaign/#t=%s&r=%s",          # the report, not the dashboard (item 294)
            "selection": "/selection/#s=%s&r=%s",
            "creator": "/creator/#c=%s&r=%s",
            "study": "/market/#s=%s&r=%s"}[r["kind"]] % (r["ref"], t)


def link(r, site):
    return site.rstrip("/") + "/report/#r=" + r["token"]


def public(r, site, with_link=True):
    """A row for the staff lists: never the creator's own token in lists that are not staff-only."""
    out = {"id": r["id"], "kind": r["kind"], "kind_label": KINDS.get(r["kind"], r["kind"]), "ref": r["ref"],
           "title": r["title"] or "", "label": r["label"] or "", "prices": bool(r["prices"]),
           "created_by": r["created_by"] or "", "created_at": r["created_at"], "expires_at": r["expires_at"],
           "revoked_at": r["revoked_at"], "revoked_by": r["revoked_by"] or "", "opens": r["opens"],
           "last_open_at": r["last_open_at"], "state": state(r)}
    if with_link:
        out["url"] = link(r, site)
        out["page"] = page(r)          # Preview as client: the report itself, so the preview is not counted as an open
    return out


def admin_html(query=None, site=""):
    """Admin › Tenants › Client report links: every link made from a report page, who it was for, how often it
    was opened, and Revoke. Links are made on the report itself (Share with client), not here."""
    import views
    e, u = views.e, views.u
    query = query or {}
    note = ""
    if query.get("ok"):
        note = "<div class='ok'>" + e(query.get("ok")) + "</div>"
    elif query.get("e"):
        note = "<div class='err'>" + e(query.get("e")) + "</div>"
    now = db.now()
    trs = []
    for r in listing():
        st = state(r)
        pill = {"open": "<span class='pill live'>Open</span>", "ended": "<span class='pill dead'>Ended</span>",
                "revoked": "<span class='pill dead'>Revoked</span>"}[st]
        when = ("%d days left" % (-(-(r["expires_at"] - now) // 86400))) if st == "open" else \
            views.ts(r["revoked_at"] or r["expires_at"])
        acts = ""
        if st == "open":
            acts = ("<button type='button' class='btn tiny' data-copy='%s'>Copy link</button>"
                    "<form method='post' action='%s' class='rl-f'><input type='hidden' name='id' value='%d'>"
                    "<button class='btn tiny ghost' data-ask='Revoke this link? It stops working at once.'>Revoke</button></form>"
                    % (e(link(r, site)), e(u("/tenants/reports/revoke")), r["id"]))
        trs.append("<tr><th scope='row'><b>%s</b><div class='muted'>%s</div></th><td>%s</td><td>%s<div class='muted'>%s</div></td>"
                   "<td>%d</td><td>%s</td><td>%s<div class='muted'>%s</div></td><td class='rl-acts'>%s</td></tr>" % (
                       e(r["title"] or r["ref"]), e(KINDS.get(r["kind"], r["kind"]) + (" · with prices" if r["prices"] else "")),
                       e(r["label"] or "—"), pill, e(when), r["opens"],
                       e(views.ts(r["last_open_at"])) if r["last_open_at"] else "<span class='muted'>Not opened</span>",
                       e(r["created_by"] or ""), e(views.ts(r["created_at"])), acts))
    body = (
        "<div class='card'><div class='hd'><h2>Client report links</h2><div class='hd-acts'><a class='btn small ghost' href='"
        + e(u("/tenants")) + "'>All tenants</a></div></div>" + note +
        "<p class='sec-desc'>One link opens one report (a Track campaign, a selection, a creator analysis or a competitor "
        "study) with live data, no sign-in and no way into the rest of the portal. Make them with <b>Share with client</b> "
        "on the report itself (owner and admin accounts, and the account's KAM). Revoking stops a link at once; every make "
        "and revoke is in History.</p></div>"
        "<div class='card'><table class='tbl'><thead><tr><th>Report</th><th>For</th><th>Status</th><th>Opens</th>"
        "<th>Last opened</th><th>Made by</th><th></th></tr></thead><tbody>"
        + ("".join(trs) or "<tr><td colspan='7' class='muted'>No client links yet.</td></tr>") + "</tbody></table></div>"
        "<style>.rl-acts{display:flex;gap:6px;flex-wrap:wrap;align-items:center}.rl-f{margin:0}</style>"
        "<script>document.addEventListener('click',function(ev){var b=ev.target.closest('[data-copy]');if(b){"
        "var t=b.getAttribute('data-copy');(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){"
        "b.textContent='Copied';setTimeout(function(){b.textContent='Copy link'},1600)},function(){window.prompt('Copy the link',t)});return}"
        "var a=ev.target.closest('[data-ask]');if(a&&!confirm(a.getAttribute('data-ask')))ev.preventDefault();});</script>")
    return views.page("Client report links", body, "/tenants")
