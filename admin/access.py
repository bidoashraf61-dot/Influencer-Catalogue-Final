"""Access by email (owner, 2026-10-15). No passcodes: everyone signs in with their work email and a one-time
code. A signed-in person who opens a selection that is not theirs asks for access from the page; the client's
KAM and the owner get an email; on the admin's Access requests page one click grants that ONE selection (and the
campaign made from it), and the person is emailed a link.

    request(sel, user)          record the ask and email the team (once per pending ask)
    grant(rid, who) / deny(rid, who)
    page(ok, err)               the admin page
"""
import time

import db
import mailer
import notify
from views import e, page as shell, u

SITE = mailer.SITE


def _owners():
    with db.connect() as conn:
        return [r[0] for r in conn.execute("SELECT email FROM admins WHERE role = 'owner' AND disabled_at IS NULL AND email LIKE '%@%'")]


def request(sel, user):
    """(request id, new?)"""
    import portal
    rid, new = db.access_request_add(sel["id"], user["code_id"], user["email"], user["name"], user["company"])
    if new:
        owner = portal.user_for_code(sel["code_id"]) if sel["code_id"] else None
        who = "%s <%s>%s" % (user["name"] or user["email"], user["email"], (" · " + user["company"]) if user["company"] else "")
        notify.send("access_request", ["%s asked for access to the selection “%s”%s." % (
                        who, sel["name"], (" (client: %s)" % (owner["company"] or owner["name"])) if owner is not None else ""),
                     "Grant or decline it on the Access requests page."],
                    kam=owner["kam"] if owner is not None and "kam" in owner.keys() else None,
                    link=SITE + u("/access-requests"), also=_owners())
    return rid, new


def grant(rid, who):
    r = db.access_request(rid)
    if r is None or r["status"] != "pending":
        return False
    db.grant_selection(r["selection_id"], r["code_id"], who)
    db.access_request_decide(rid, "granted", who)
    sel = db.selection(r["selection_id"])
    if sel is not None and r["email"] and mailer.configured():
        try:
            mailer.send(r["email"], "You now have access to “%s”" % sel["name"],
                        "Hi %s,\n\nHelloVoice gave you access to the selection “%s”. Open it here (sign in with this email):\n%s/selection/#s=%s\n\nHelloVoice"
                        % ((r["name"] or "").split(" ")[0] or "there", sel["name"], SITE, sel["token"]))
        except Exception:
            pass
    return True


def deny(rid, who):
    r = db.access_request(rid)
    if r is None or r["status"] != "pending":
        return False
    db.access_request_decide(rid, "declined", who)
    return True


def _when(t):
    return time.strftime("%d %b %Y, %H:%M", time.gmtime(t)) if t else ""


def page(ok=None, err=None, can=None):
    """``can(code_id)``: which clients' requests this admin may see (a KAM: her own clients)."""
    def mine(r):
        if can is None:
            return True
        sel = db.selection(r["selection_id"])
        return sel is not None and can(sel["code_id"])
    pend = [r for r in db.access_requests("pending") if mine(r)]
    done = [r for r in db.access_requests(None) if r["status"] != "pending" and mine(r)][:30]
    msg = ("<div class='flash ok'>%s</div>" % e(ok) if ok else "") + ("<div class='flash err'>%s</div>" % e(err) if err else "")
    rows = []
    for r in pend:
        rows.append("<tr><td><b>%s</b><br><span class='muted'>%s%s</span></td><td><a href='%s'>%s</a></td><td>%s</td>"
                    "<td><form method='post' action='%s' style='display:inline'><input type='hidden' name='id' value='%d'>"
                    "<button class='btn small lime' name='do' value='grant'>Grant</button> "
                    "<button class='btn small ghost' name='do' value='deny'>Decline</button></form></td></tr>" % (
                        e(r["name"] or r["email"]), e(r["email"]), (" · " + e(r["company"])) if r["company"] else "",
                        e(u("/selections/edit?id=%d" % r["selection_id"])), e(r["selection_name"] or "#%d" % r["selection_id"]),
                        e(_when(r["at"])), e(u("/access-requests")), r["id"]))
    hist = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        e(r["email"]), e(r["selection_name"] or ""), e(r["status"].title()), e(_when(r["decided_at"]) + (" · " + r["decided_by"] if r["decided_by"] else "")))
        for r in done)
    body = ("<div class='hd'><h1>Access requests</h1></div>"
            "<p class='sec-desc'>People who signed in with their work email and asked to open a selection. Granting opens that one "
            "selection (and the campaign made from it) for that person, and emails them the link.</p>" + msg +
            "<div class='card'><div class='hd'><h2>Waiting (%d)</h2></div>" % len(pend) +
            ("<table class='t'><tr><th>Person</th><th>Selection</th><th>Asked</th><th></th></tr>" + "".join(rows) + "</table>"
             if rows else "<p class='muted'>No requests waiting.</p>") + "</div>" +
            ("<div class='card'><div class='hd'><h2>Recent decisions</h2></div><table class='t'><tr><th>Person</th><th>Selection</th>"
             "<th>Decision</th><th>When</th></tr>" + hist + "</table></div>" if hist else ""))
    return shell("Access requests", body, "/access-requests")
