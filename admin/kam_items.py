"""Hand one selection or campaign to a key account manager (owner, 2026-10-17, programme item 119).

A KAM already sees every selection and campaign of her clients (kam_scope). This adds the single
items the owner gives her, on top: ``item_kam`` rows, read into her scope (``kam_scope.Scope``).
She is told by email, and by the bell when she has a portal account. She can then open the item and
invite the client's email to it (access.invite) from her own admin account.

    kam_options()                      [(name, email)] the KAMs that can be picked
    assign(kind, item, email, by)      kind: "selection" | "campaign"; empty email takes it back
    card(kind, item)                   the picker card for the selection's Share tab / campaign's Setup tab
    post(handler, path)                POST /selections/kam and /campaigns/kam (owners and admins only)
"""
import urllib.parse

import db
import inbox
import notify

SEL_ROUTE, CAMP_ROUTE = "/selections/kam", "/campaigns/kam"


def kam_options():
    return notify.kams()


def _name(email):
    for n, m in kam_options():
        if m == email:
            return n or m
    return email


def _tell(kind, item, email, by):
    """Email + bell. Never raises."""
    import mailer
    import portal
    label = "selection" if kind == "selection" else "campaign"
    path = "/selections/edit?id=%d" % item["id"] if kind == "selection" else "/campaigns/edit?id=%d" % item["id"]
    try:
        notify.send("kam_assign", ['%s gave you the %s "%s".' % (by or "HelloVoice", label, item["name"]),
                                   "Open it, then invite the client's email from its Share tab." if kind == "selection"
                                   else "Open it to follow it and invite the client."],
                    kam=email, link=mailer.SITE + "/admin" + path, also=[])
    except Exception:
        pass
    try:
        u = portal.user_by_email(email)
        if u is not None and u["id"]:
            inbox.emit([u["id"]], "sel_shared" if kind == "selection" else "camp_shared",
                       '%s gave you the %s "%s"' % (by or "HelloVoice", label, item["name"]),
                       body="It is on your list now.", href="admin" + path, ref="kam:%s:%d:%d" % (kind, item["id"], db.now()))
    except Exception:
        pass


def assign(kind, item_id, email, by=""):
    """Returns (item row, error). error: unknown, kam."""
    item = db.selection(int(item_id)) if kind == "selection" else db.campaign(int(item_id))
    if item is None:
        return None, "unknown"
    email = (email or "").strip().lower()
    if email and email not in {m for _, m in kam_options()}:
        return item, "kam"
    was = db.kam_assign(kind, item["id"], email, by)
    if email and email != was:
        _tell(kind, item, email, by)
    return item, None


def card(kind, item):
    import kam_scope
    if kam_scope.current() is not None:
        return ""                    # a key account manager never re-assigns
    import views
    e_, u_ = views.e, views.u
    cur = db.kam_of_item(kind, item["id"]) or ""
    opts = "<option value=''>No key account manager</option>" + "".join(
        "<option value=\"%s\"%s>%s</option>" % (e_(m), " selected" if m == cur else "", e_(n or m)) for n, m in kam_options())
    route = SEL_ROUTE if kind == "selection" else CAMP_ROUTE
    return ("<div class='card' id='kam-item'><div class='hd'><h2>Key account manager</h2></div>"
            "<p class='sec-desc'>Hand this %s to one account manager, on top of her own clients. She sees it, edits it, and can invite "
            "the client's email to it from her account. She is told by email.</p>"
            "<form method='post' action='%s' class='row limits'><input type='hidden' name='id' value='%d'>"
            "<div style='flex:2'><label for='kam-pick'>Account manager</label><select id='kam-pick' name='kam'>%s</select></div>"
            "<div style='align-self:end'><button class='btn small lime'>Save</button></div></form>%s</div>" % (
                kind, e_(u_(route)), item["id"], opts,
                ("<p class='price-hint'>Now with %s.</p>" % e_(_name(cur))) if cur else ""))


def post(handler, path):
    f = handler.form_body()
    raw = (f.get("id") or "").strip()
    kind = "selection" if path == SEL_ROUTE else "campaign"
    back = ("/selections/edit?id=%s#st=share" if kind == "selection" else "/campaigns/edit?id=%s") % raw
    q = urllib.parse.quote
    if not raw.isdigit():
        return handler.redirect("/selections" if kind == "selection" else "/campaigns")
    who = handler.admin()
    item, err = assign(kind, int(raw), f.get("kam") or "", (who["email"] if who is not None else ""))
    sep = "&" if "?" in back else "?"
    if err == "unknown":
        return handler.redirect(("/selections" if kind == "selection" else "/campaigns") + "?e=" + q("That item no longer exists."))
    if err == "kam":
        return handler.redirect(back.replace("#st=share", "") + sep + "e=" + q("Pick an account manager from the list.") + ("#st=share" if kind == "selection" else ""))
    email = (f.get("kam") or "").strip().lower()
    msg = ("Handed to %s. She has been told." % _name(email)) if email else "Taken back from the account manager."
    return handler.redirect(back.replace("#st=share", "") + sep + "ok=" + q(msg) + ("#st=share" if kind == "selection" else ""))
