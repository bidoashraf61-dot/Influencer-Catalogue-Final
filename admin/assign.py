"""One-step "Assign to client" (2026-10-11).

Before: an admin moved a selection to a client by changing "Client (access code)" on the
selection page and, separately, the client of each campaign; the client was never told.

Now one action does all of it:

  * the selection moves to the chosen client account (a portal account, or a plain access code);
  * the campaigns made from it can move with it (ticked by default);
  * the client's bell rings: "HelloVoice shared "<name>" with you" linking to the selection
    (and the campaign report). It is an in-portal bell only, never an email;
  * History records each change (who, when, from, to) so it can be undone.

The rules live here, and the two pages (the selection's Share tab and the campaign's Setup tab)
only render a card and post to ``/selections/assign`` or ``/campaigns/assign``. The role check is
the dispatcher's (team.can): owners, admins and key account managers may; viewers may not.
"""
import urllib.parse

import db
import history
import inbox
import portal

# The two jobs the pages ask for.
SEL_ROUTE, CAMP_ROUTE = "/selections/assign", "/campaigns/assign"


# ---------------------------------------------------------------- targets --

def _who(code, user):
    """A short human name for a code: the person for a portal account, else the code's label."""
    if user is not None:
        name = (user["name"] or "").strip()
        company = (user["company"] or "").strip()
        head = name or user["email"]
        return head + (" · " + company if company else "")
    return code["label"] if code is not None else "No client"


def usable(code_id):
    """(code row, None) when this code may be assigned to, else (None, reason)."""
    code = db.get_code(code_id) if code_id else None
    if code is None or code["label"] == db.ADMIN_LABEL:
        return None, "That client no longer exists."
    ok, why = db.code_state(code)
    if not ok:
        return None, "That client's access code is %s, so it can't receive work. Restore it first." % why
    user = portal.user_for_code(code["id"])
    if user is not None and user["status"] != "active":
        return None, "That account is %s, so it can't receive work yet." % user["status"]
    return code, None


def targets():
    """Who can be assigned to: portal accounts first (name, company, email), then plain access
    codes. Revoked, expired, archived and used-up codes are left out. [{id, label, email, kind}]"""
    accounts, plain = [], []
    for c in db.list_codes():
        code, _why = usable(c["id"])
        if code is None:
            continue
        u = portal.user_for_code(c["id"])
        if u is not None:
            accounts.append({"id": c["id"], "kind": "account", "label": _who(c, u), "email": u["email"]})
        else:
            plain.append({"id": c["id"], "kind": "code", "label": c["label"], "email": ""})
    key = lambda t: t["label"].lower()
    return sorted(accounts, key=key) + sorted(plain, key=key)


def owner_name(code_id):
    """Who has it now, for the confirm step and the History line."""
    if not code_id:
        return ""
    code = db.get_code(code_id)
    return _who(code, portal.user_for_code(code_id)) if code is not None else "an old client"


# ------------------------------------------------------------------- core --

def _ring(code_id, sel, campaigns):
    """The bell, never an email. ``sel`` is the moved selection row or None; ``campaigns`` the moved
    campaign rows. A draft campaign is not visible to the client, so it is not announced."""
    users = inbox.for_codes([code_id])
    if not users:
        return 0
    shown = [k for k in campaigns if k["status"] != "draft"]
    n = 0
    if sel is not None:
        rest = ""
        if len(shown) == 1:
            rest = " and its campaign " + shown[0]["name"]
        elif shown:
            rest = " and its %d campaigns" % len(shown)
        n += inbox.emit(users, "sel_shared", 'HelloVoice shared "%s" with you' % sel["name"], rest=rest,
                        body="Open it to review the creators and their prices.",
                        href="selection/#s=" + sel["token"],
                        ref="assign:sel:%d:%d:%d" % (sel["id"], code_id, db.now()))
    for k in shown:
        n += inbox.emit(users, "camp_shared", 'HelloVoice shared the campaign "%s" with you' % k["name"],
                        body="Its report is on your campaigns list.", href="campaign/#t=" + k["token"],
                        ref="assign:camp:%d:%d:%d" % (k["id"], code_id, db.now()))
    return n


def _move_campaign(k, code_id, old_labels, new_label, via):
    """Point one campaign at the new client; its brand label follows only when it was the old
    client's name (a brand typed by hand, like "SVR", is left alone)."""
    fields = {"code_id": code_id}
    if (k["client"] or "").strip() and (k["client"] or "").strip() in old_labels and new_label:
        fields["client"] = new_label
    with history.tracked("campaign", k["id"], 'Assigned campaign "%s" to %s%s' % (k["name"], owner_name(code_id), via)):
        db.save_campaign(k["id"], **fields)


def assign_selection(sel_id, code_id, move_campaigns=True, tell=True, confirmed=False):
    """Move one selection (and, by default, its campaigns) to a client.

    Returns {"ok", "noop", "error", "needs_confirm", "from", "to", "campaigns": [names], "notified": n}."""
    sel = db.selection(sel_id)
    out = {"ok": False, "noop": False, "error": None, "needs_confirm": False, "from": "", "to": "",
           "campaigns": [], "notified": 0}
    if sel is None:
        out["error"] = "That selection no longer exists."
        return out
    code, why = usable(code_id)
    if code is None:
        out["error"] = why
        return out
    old_id = sel["code_id"]
    out["from"], out["to"] = owner_name(old_id), owner_name(code["id"])
    linked = db.campaigns_for_selection(sel["id"]) if move_campaigns else []
    todo = [k for k in linked if k["code_id"] != code["id"]]
    sel_moves = old_id != code["id"]
    if not sel_moves and not todo:
        out.update(ok=True, noop=True)
        return out
    if sel_moves and old_id and not confirmed:
        out["needs_confirm"] = True
        out["error"] = "This moves it away from %s. Confirm to continue." % out["from"]
        return out

    old_labels = set()
    if old_id:
        old = db.get_code(old_id)
        old_user = portal.user_for_code(old_id)
        if old is not None:
            old_labels.add(old["label"])
        if old_user is not None:
            old_labels.update(x for x in (old_user["company"], old_user["name"]) if x)
    new_label = code["label"]
    via = (" (was %s)" % out["from"]) if out["from"] else ""
    moved_sel = None
    if sel_moves:
        shown = (sel["client_name"] if "client_name" in sel.keys() else None) or ""
        # A typed "for <name>" that was just the old client's name would now be wrong.
        keep_name = "" if (not shown or shown in old_labels) else shown
        with history.tracked("selection", sel["id"], 'Assigned selection "%s" to %s%s' % (sel["name"], out["to"], via)):
            db.set_selection_client(sel["id"], code["id"], keep_name)
        moved_sel = db.selection(sel["id"])
    for k in todo:
        _move_campaign(k, code["id"], old_labels, new_label, "" if sel_moves else via)
    out["campaigns"] = [k["name"] for k in todo]
    if tell:
        out["notified"] = _ring(code["id"], moved_sel, [db.campaign(k["id"]) for k in todo])
    out["ok"] = True
    return out


def assign_campaign(cid, code_id, with_selection=False, tell=True, confirmed=False):
    """Move one campaign to a client; its selection comes too when ticked."""
    k = db.campaign(cid)
    out = {"ok": False, "noop": False, "error": None, "needs_confirm": False, "from": "", "to": "",
           "campaigns": [], "notified": 0, "selection": None}
    if k is None:
        out["error"] = "That campaign no longer exists."
        return out
    code, why = usable(code_id)
    if code is None:
        out["error"] = why
        return out
    old_id = k["code_id"]
    out["from"], out["to"] = owner_name(old_id), owner_name(code["id"])
    sel = db.selection(k["selection_id"]) if (with_selection and k["selection_id"]) else None
    camp_moves = old_id != code["id"]
    sel_moves = sel is not None and sel["code_id"] != code["id"]
    if not camp_moves and not sel_moves:
        out.update(ok=True, noop=True)
        return out
    away = (old_id if camp_moves else None) or (sel["code_id"] if sel_moves else None)
    if away and not confirmed:
        out["needs_confirm"] = True
        out["from"] = owner_name(away)
        out["error"] = "This moves it away from %s. Confirm to continue." % out["from"]
        return out
    old_labels = set()
    if old_id:
        old = db.get_code(old_id)
        if old is not None:
            old_labels.add(old["label"])
        ou = portal.user_for_code(old_id)
        if ou is not None:
            old_labels.update(x for x in (ou["company"], ou["name"]) if x)
    via = (" (was %s)" % out["from"]) if out["from"] else ""
    if camp_moves:
        _move_campaign(k, code["id"], old_labels, code["label"], via)
        out["campaigns"] = [k["name"]]
    moved_sel = None
    if sel_moves:
        was = owner_name(sel["code_id"])
        shown = (sel["client_name"] if "client_name" in sel.keys() else None) or ""
        keep_name = "" if (not shown or shown in old_labels) else shown
        with history.tracked("selection", sel["id"], 'Assigned selection "%s" to %s%s' % (
                sel["name"], out["to"], (" (was %s)" % was) if was else "")):
            db.set_selection_client(sel["id"], code["id"], keep_name)
        moved_sel = db.selection(sel["id"])
        out["selection"] = sel["name"]
    if tell:
        out["notified"] = _ring(code["id"], moved_sel, [db.campaign(k["id"])] if camp_moves else [])
    out["ok"] = True
    return out


# -------------------------------------------------------------- the cards --

CSS = """<style>
.asg-grid{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:20px 28px;align-items:start}
.asg-now{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;margin:0 0 14px}
.asg-now b{font-weight:600}
.asg-camps{list-style:none;margin:0;padding:0;display:grid;gap:6px}
.asg-camps li{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;padding:8px 10px;border:1px solid var(--line);border-radius:var(--r-sm);background:var(--white)}
.asg-camps li .muted{margin-left:auto;font-size:var(--t-xs,12px)}
.asg-camps .asg-draft{flex-basis:100%;font-size:var(--t-xs,12px);color:var(--amber)}
.asg-opts{display:grid;gap:10px;margin:14px 0 16px}
.asg-opts label{display:flex;gap:10px;align-items:flex-start;font-weight:500;margin:0}
.asg-opts label small{display:block;font-weight:400;color:var(--muted);font-size:var(--t-xs,12px);margin-top:2px}
.asg-h{margin:0 0 8px;font-size:var(--t-sm,13px);font-weight:600;color:var(--gray)}
@media (max-width:760px){.asg-grid{grid-template-columns:1fr}}
</style>"""


def _options(chosen=None):
    import views
    acc = [t for t in targets() if t["kind"] == "account"]
    plain = [t for t in targets() if t["kind"] == "code"]
    opt = lambda t: "<option value='%d'%s>%s</option>" % (
        t["id"], " selected" if t["id"] == chosen else "",
        views.e(t["label"] + (" · " + t["email"] if t["email"] else "")))
    out = "<option value=''>Choose a client…</option>"
    if acc:
        out += "<optgroup label='Portal accounts'>" + "".join(opt(t) for t in acc) + "</optgroup>"
    if plain:
        out += "<optgroup label='Access codes (no portal account)'>" + "".join(opt(t) for t in plain) + "</optgroup>"
    return out


def _now_line(code_id, noun):
    import views
    who = owner_name(code_id)
    return ("<p class='asg-now'><span class='pill own'>%s</span><span class='muted'>currently has this %s</span></p>" % (views.e(who), noun)
            if who else "<p class='asg-now'><span class='pill warn'>No client yet</span>"
                        "<span class='muted'>Nobody can open this %s until you assign it.</span></p>" % noun)


def selection_card(sel, campaigns):
    """The Share tab's guided path: pick the client, see the campaigns that go with it, tick whether
    to tell them, assign. Sits outside the page's save form (forms cannot nest)."""
    import views
    e_, u_ = views.e, views.u
    live = lambda k: k["status"] != "draft"
    camps = ""
    for k in campaigns:
        holder = owner_name(k["code_id"]) or "no client"
        camps += ("<li><a href='%s?id=%d'>%s</a> %s<span class='muted'>%s</span>%s</li>" % (
            u_("/campaigns/edit"), k["id"], e_(k["name"]), views.status_pill(k["status"]), e_(holder),
            "" if live(k) else "<span class='asg-draft'>Draft: the client will not see it until it is live.</span>"))
    owner = owner_name(sel["code_id"])
    confirm = ""
    if owner:
        confirm = (" data-confirm-title='Move it away from %s?' data-confirm-what='%s' "
                   "data-confirm='This moves it away from %s. They stop seeing it straight away.' data-confirm-ok='Assign'"
                   % (e_(owner), e_(sel["name"]), e_(owner)))
    return (
        CSS + "<div class='card' id='assign'><div class='hd'><h2>Assign to client</h2></div>"
        "<p class='sec-desc'>One step: the selection, and the campaigns made from it, move to the client you pick, "
        "and their bell tells them. Nothing is emailed.</p>"
        + _now_line(sel["code_id"], "selection")
        + "<form method='post' action='" + u_(SEL_ROUTE) + "'" + confirm + ">"
        + "<input type='hidden' name='id' value='%d'><input type='hidden' name='confirmed' value='1'>" % sel["id"]
        + "<div class='asg-grid'><div><label for='asg-client'>Client</label>"
          "<select id='asg-client' name='client' required>" + _options() + "</select>"
          "<div class='price-hint'>Portal accounts first, then plain access codes. Revoked and expired codes are not listed.</div></div>"
        + "<div><p class='asg-h'>Campaigns made from this selection</p>"
        + (("<ul class='asg-camps'>" + camps + "</ul>") if camps else
           "<p class='muted'>None yet. Start one from the Campaign tab and it will follow the selection.</p>")
        + "</div></div>"
        + "<div class='asg-opts'>"
        + ("<label><input type='checkbox' name='move_campaigns' value='1' checked><span>Also move its campaigns"
           "<small>Each campaign above gets the same client, so they see its report too.</small></span></label>" if camps else "")
        + "<label><input type='checkbox' name='tell' value='1' checked><span>Tell the client (bell)"
          "<small>An in-portal notification only, never an email. Plain access codes have no bell.</small></span></label>"
          "</div>"
        + "<button class='btn lime'>Assign to client</button></form></div>")


def campaign_card(k, selection):
    """On a campaign's Setup page: move this campaign (and, when ticked, its selection)."""
    import views
    e_, u_ = views.e, views.u
    confirm = ""
    away = owner_name(k["code_id"])
    if away:
        confirm = (" data-confirm-title='Move it away from %s?' data-confirm-what='%s' "
                   "data-confirm='This moves it away from %s. They stop seeing its report straight away.' data-confirm-ok='Assign'"
                   % (e_(away), e_(k["name"]), e_(away)))
    sel_opt = ""
    if selection is not None:
        sel_opt = ("<label><input type='checkbox' name='with_selection' value='1'><span>Also move its selection "
                   "&ldquo;%s&rdquo;<small>Now with %s.</small></span></label>" % (e_(selection["name"]), e_(owner_name(selection["code_id"]) or "no client")))
    return (
        CSS + "<section class='step' id='assign'><h2>Assign to client</h2><div class='card'>"
        + _now_line(k["code_id"], "campaign")
        + "<form method='post' action='" + u_(CAMP_ROUTE) + "'" + confirm + ">"
        + "<input type='hidden' name='id' value='%d'><input type='hidden' name='confirmed' value='1'>" % k["id"]
        + "<label for='asg-client'>Client</label><select id='asg-client' name='client' required style='max-width:420px'>"
        + _options() + "</select>"
        + "<div class='asg-opts'>" + sel_opt
        + "<label><input type='checkbox' name='tell' value='1' checked><span>Tell the client (bell)"
          "<small>An in-portal notification only, never an email. A draft campaign is not announced: they cannot see it yet.</small></span></label></div>"
        + "<button class='btn small lime'>Assign to client</button></form></div></section>")


# --------------------------------------------------------------- the POST --

def post(handler, path):
    """The two form posts. A viewer never gets here (team.can refuses the path)."""
    f = handler.form_body()
    raw = (f.get("id") or "").strip()
    tcode = (f.get("client") or "").strip()
    tell = f.get("tell") == "1"
    confirmed = f.get("confirmed") == "1"
    q = urllib.parse.quote
    if path == SEL_ROUTE:
        back = "/selections/edit?id=%s" % raw
        if not raw.isdigit() or not tcode.isdigit():
            return handler.redirect(back + "&e=" + q("Pick a client to assign this to.") + "#st=share")
        r = assign_selection(int(raw), int(tcode), move_campaigns=f.get("move_campaigns") == "1",
                             tell=tell, confirmed=confirmed)
        if r["error"] or not r["ok"]:
            return handler.redirect(back + "&e=" + q(r["error"] or "Could not assign.") + "#st=share")
        if r["noop"]:
            msg = "Nothing changed: it already belongs to %s." % r["to"]
        else:
            msg = "Assigned to %s." % r["to"]
            if r["campaigns"]:
                msg += " Moved %d campaign%s with it." % (len(r["campaigns"]), "" if len(r["campaigns"]) == 1 else "s")
            if tell:
                msg += " Their bell rang." if r["notified"] else " They have no portal account, so there was no bell to ring; send them the link."
        return handler.redirect(back + "&ok=" + q(msg) + "#st=share")
    # a campaign
    back = "/campaigns/edit?id=%s" % raw
    if not raw.isdigit() or not tcode.isdigit():
        return handler.redirect(back + "&e=" + q("Pick a client to assign this to."))
    r = assign_campaign(int(raw), int(tcode), with_selection=f.get("with_selection") == "1",
                        tell=tell, confirmed=confirmed)
    if r["error"] or not r["ok"]:
        return handler.redirect(back + "&e=" + q(r["error"] or "Could not assign."))
    if r["noop"]:
        msg = "Nothing changed: it already belongs to %s." % r["to"]
    else:
        msg = "Assigned to %s." % r["to"]
        if r.get("selection"):
            msg += " Its selection moved too."
        if tell:
            msg += " Their bell rang." if r["notified"] else " They have no portal account, so there was no bell to ring."
    return handler.redirect(back + "&ok=" + q(msg))
