"""The campaign board (items 174, 176, 177, 182, owner 2026-10-20).

Campaign first: a campaign is run by a key account manager, filed under a client, and holds MANY
selections. Its first selection stays in ``campaigns.selection_id`` (everything that already reads
it keeps working); the others are linked in ``campaign_selections``. A selection can still live on
its own, filed under no campaign.

Six stages, one column each:

    draft -> shortlisting -> review -> approved -> live -> completed

``live`` and ``completed`` ARE the campaign's status (live / ended); the four before are a draft
campaign's stage. An admin's choice is kept in ``campaigns.stage``; a campaign nobody has staged yet
(every campaign that existed before the board) is read from what is already there, so the
migration writes nothing:

    status live                          -> live
    status ended                         -> completed
    a selection's quote approved         -> approved
    a quote requested or ready           -> review       (the client is looking at it)
    a selection with creators in it      -> shortlisting
    otherwise                            -> draft

Who sees what: an admin every campaign; a key account manager hers (her clients and what was handed
to her); a client their own team's campaigns as a read-only board (campaigns opened to them by a
grant, an invite or a share link show once they are no longer drafts, as before). Anyone may start
a campaign or add a selection to one. Moving between the four planning stages (draft .. approved) is open to
everyone inside their own access (item 194, owner 2026-10-20): an admin any campaign, a KAM hers, a client their
own team's (not one only shared with them); Live, Completed and taking a campaign off the air stay admin-only.
All of it is checked here, on the server, not only by hiding buttons. Nothing on a card is a score or an analysis.

Selections sit on the same six columns on the account page (item 194): read from their quote, or the planning
column someone dragged them to (selections.stage). Live and Completed come from their campaign, never a drag.

    viewer(h)                 (role, who) for a request: admin | team | kam | client | None
    stage_of(k, sels)         the column a campaign sits in
    board(h)                  the payload of GET /api/board
    moves_for(h, role, who, k, stage)   the columns this viewer may move a campaign to
    move(h, k, to)            move a campaign (live / completed, admins only, also change its status)
    selection_stage(sel, chip)          the column a selection sits in
    selection_moves(...) / move_selection(h, sel, to)   the same for a selection
    set_live(h, k, on)        Live / Unlive
    pin(h, k, on)             per person
    attach(h, sel, ...)       "Create campaign with this selection": add it to a campaign or start one
"""
import json
import re
import time

import db

STAGES = ("draft", "shortlisting", "review", "approved", "live", "completed")
LABEL = {"draft": "Draft", "shortlisting": "Shortlisting", "review": "Client review", "approved": "Approved",
         "live": "Live", "completed": "Completed"}
HINT = {"draft": "Named, nothing picked yet", "shortlisting": "Creators being chosen",
        "review": "With the client to decide", "approved": "Agreed, being set up",
        "live": "Posts going out, tracked daily", "completed": "Finished, final report"}
DRAFT_STAGES = STAGES[:4]
NAME_MIN, NAME_MAX = 3, 120


def now():
    return int(time.time())


# ------------------------------------------------------------------- who --

def viewer(h):
    """(role, who) for this request.

    admin   an owner or admin (admin session, or a portal account whose email is one): sees all, moves stages
    team    any other HelloVoice team login (viewer role): sees all, moves nothing
    kam     a key account manager: her own campaigns, moves nothing
    client  a signed-in client (or an access code typed for the campaign list): their own, read-only
    """
    import portal
    import team
    if h.as_client():
        cid = h.signed_in_client() or h.link_code("c:list")
        return ("client", cid) if cid is not None else (None, None)
    if h.kam_clients() is not None:
        return "kam", None
    a = h.admin()
    if a is not None:
        return ("admin" if team.role_of(a) in ("owner", "admin") else "team"), a
    cid = h.viewer_cookie_id()
    u = portal.user_for_code(cid) if cid is not None else None
    if u is not None and u["email"]:
        adm = db.admin_by_email(u["email"])
        if adm is not None and not (adm["disabled_at"] if "disabled_at" in adm.keys() else None):
            return ("admin" if team.role_of(adm) in ("owner", "admin") else "team"), adm
    cid = h.signed_in_client() or h.link_code("c:list")
    return ("client", cid) if cid is not None else (None, None)


def pin_key(h):
    """Pins are per person: their portal account, else their admin login, else the access code."""
    import portal
    cid = h.viewer_cookie_id()
    u = portal.user_for_code(cid) if cid is not None else None
    if u is not None:
        return "u:%d" % u["id"]
    a = h.admin()
    if a is not None:
        return "a:%d" % a["id"]
    cid = h.link_code("c:list")
    return ("c:%d" % int(cid)) if cid is not None else None


# ---------------------------------------------------------------- reading --

def selection_ids(k):
    """The campaign's selections, first one first."""
    out = [int(k["selection_id"])] if k["selection_id"] else []
    with db.connect() as conn:
        for r in conn.execute("SELECT selection_id FROM campaign_selections WHERE campaign_id = ? ORDER BY added_at, rowid",
                              (int(k["id"]),)):
            if int(r[0]) not in out:
                out.append(int(r[0]))
    return out


def campaigns_holding(sid):
    """Ids of every campaign that holds this selection (as its first one or linked)."""
    with db.connect() as conn:
        ids = [r[0] for r in conn.execute("SELECT id FROM campaigns WHERE selection_id = ? UNION "
                                          "SELECT campaign_id FROM campaign_selections WHERE selection_id = ?", (int(sid), int(sid)))]
    return sorted(set(int(i) for i in ids))


def _selections(ids):
    if not ids:
        return []
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM selections WHERE id IN (%s) AND deleted_at IS NULL" % ",".join("?" * len(ids)),
                            list(ids)).fetchall()
    by = {r["id"]: r for r in rows}
    return [by[i] for i in ids if i in by]


def _creators(sel):
    try:
        return len(json.loads(sel["codes"] or "[]"))
    except (TypeError, ValueError):
        return 0


def stage_of(k, sels=None, chips=None):
    """The column a campaign sits in (see the module note)."""
    if k["status"] == "live":
        return "live"
    if k["status"] == "ended":
        return "completed"
    st = k["stage"] if "stage" in k.keys() else None
    if st in DRAFT_STAGES:
        return st
    import lifecycle
    sels = sels if sels is not None else _selections(selection_ids(k))
    keys = chips if chips is not None else [lifecycle.chip(s)["key"] for s in sels]
    # A selection that went live in ANOTHER campaign had its quote approved: that is as far as it says here.
    if any(x in ("approved", "live", "completed") for x in keys):
        return "approved"
    if any(x in ("requested", "ready") for x in keys):
        return "review"
    if any(_creators(s) for s in sels):
        return "shortlisting"
    return "draft"


def kam_for(k):
    """The campaign's key account manager: the one it was handed to, else its client's (their own
    account's KAM, else their company domain's)."""
    import kam_scope
    import notify
    import portal
    own = db.kam_of_item("campaign", k["id"])
    if own:
        return own
    u = portal.user_for_code(k["code_id"]) if k["code_id"] is not None else None
    if u is None:
        return ""
    mine = (u["kam"] if "kam" in u.keys() else None) or ""
    if mine:
        return (notify.kam_address(mine) or mine).lower()
    return (kam_scope.domain_map() or {}).get((u["domain"] or "").lower(), "")


def _kam_name(email):
    try:
        import hub
        return hub._kam_name(email)
    except Exception:
        return email


_CLIENT_FILES = None


def _client_files(folder):
    global _CLIENT_FILES
    if folder is None:
        return []
    if _CLIENT_FILES is None or _CLIENT_FILES[0] != str(folder):
        try:
            names = sorted(p.name for p in folder.iterdir() if p.suffix in (".webp", ".png", ".svg") and "@" not in p.name)
        except OSError:
            names = []
        _CLIENT_FILES = (str(folder), names)
    return _CLIENT_FILES[1]


def _slug(v):
    return re.sub(r"[^a-z0-9]+", "-", str(v or "").lower()).strip("-")


def client_logo(name, folder):
    """A client logo from the catalogue's own set (assets/clients/) whose file name matches the client's
    name ("Avalon Pharma" -> avalon-pharma.webp, "Abbott KSA" -> abbott.webp), else None."""
    s = _slug(name)
    if not s:
        return None
    files = _client_files(folder)
    stems = {f.rsplit(".", 1)[0]: f for f in files}
    if s in stems:
        return stems[s]
    words = s.split("-")
    for n in range(len(words), 0, -1):
        cand = "-".join(words[:n])
        if len(cand) >= 3 and cand in stems:
            return stems[cand]
    return None


def _pins(who):
    if not who:
        return {}
    with db.connect() as conn:
        return {r["campaign_id"]: r["at"] for r in conn.execute("SELECT campaign_id, at FROM campaign_pins WHERE who = ?", (who,))}


def _visible(h, role, who):
    """Campaign rows this viewer may see on the board."""
    import kam_scope
    import portal
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM campaigns ORDER BY updated_at DESC, id DESC").fetchall()
    if role in ("admin", "team"):
        return rows
    if role == "kam":
        out = []
        for k in rows:
            code = k["code_id"] if k["code_id"] is not None else kam_scope.campaign_code(k["id"])[1]
            if h.admin_like_for(code, k["selection_id"], k["id"]):
                out.append(k)
        return out
    if role == "client" and who is not None:
        team = portal.team_codes(int(who))
        out = []
        for k in rows:
            if k["code_id"] in team:
                out.append(k)                         # their own team's: every stage
            elif k["status"] != "draft" and portal.opens_campaign(int(who), k):
                out.append(k)                         # opened to them by a grant, invite or share: once it is out of draft
        return out
    return []


def _own_team(who):
    import portal
    try:
        return set(portal.team_codes(int(who))) if who is not None else set()
    except (TypeError, ValueError):
        return set()


def moves_for(h, role, who, k, stage, team=None):
    """The columns this viewer may move campaign ``k`` (now in ``stage``) to (item 194).

    admin   any other column (Live checks dates and client in move())
    kam     her campaigns (the board only lists hers), between the four planning columns
    client  their own team's campaigns, between the four planning columns
    A campaign that is live or completed leaves those columns only by an admin's hand."""
    if role == "admin":
        return [s for s in STAGES if s != stage]
    if stage not in DRAFT_STAGES or k["status"] != "draft":
        return []
    if role == "kam":
        code = k["code_id"] if k["code_id"] is not None else None
        if not h.admin_like_for(code, k["selection_id"], k["id"]):
            return []
    elif role == "client":
        if k["code_id"] not in (team if team is not None else _own_team(who)):
            return []
    else:
        return []
    return [s for s in DRAFT_STAGES if s != stage]


def _numbers(k):
    """Live and completed campaigns: what the dashboard says (views, engagement, rate, posts). Never a score."""
    if k["status"] not in ("live", "ended"):
        return None, None
    try:
        import metrics
        rep = metrics.report(k)
    except Exception:
        return None, None
    t = (rep or {}).get("total") or {}
    er = t.get("video_er") if t.get("video_er") is not None else t.get("er")
    grades = {i.get("key"): i.get("grade") for i in ((rep or {}).get("progress") or {}).get("items") or [] if i.get("key")}
    v = (rep or {}).get("verdict") or {}
    return ({"views": t.get("views") or 0, "engagement": t.get("engagement") or 0, "er": er,
             "er_grade": grades.get("er") or t.get("er_grade"),
             # item 208: the dashboard's overall verdict, the board's on-track colour
             "verdict": {"grade": v.get("grade"), "label": v.get("label")} if v.get("grade") else None},
            {"live": t.get("delivered") or 0, "planned": t.get("planned") or 0})


def card(h, k, role, pins, logo_dir, staff, demo=frozenset(), who=None, team=None):
    """One campaign card. Never a score, a cost or an analysis."""
    import lifecycle
    import selstatus
    sels = _selections(selection_ids(k))
    chips = [lifecycle.chip(s) for s in sels]
    stage = stage_of(k, sels, [c["key"] for c in chips])
    logos = []
    for ref in db.campaign_logos(k):
        if ref.startswith("clients/") or k["status"] != "draft" or staff:
            logos.append(h.logo_url(ref, k["token"]))
    if not logos:
        f = client_logo(k["client"] or "", logo_dir)
        if f:
            logos.append("/assets/clients/" + f)
    out = {"id": k["id"], "token": k["token"], "name": k["name"], "client": k["client"] or "",
           "stage": stage, "status": k["status"], "starts_at": k["starts_at"], "ends_at": k["ends_at"],
           "logos": logos[:3], "my_pin": k["id"] in pins, "pinned_at": pins.get(k["id"]), "demo": k["id"] in demo,
           "report": k["status"] != "draft",
           "origin": (k["origin"] if "origin" in k.keys() else None) or "",
           "updated_at": k["updated_at"],
           "selections": [{"token": s["token"], "name": s["name"], "creators": _creators(s), "chip": c}
                          for s, c in zip(sels, chips)]}
    # Item 194: what the card shows at a glance. Creators across its selections and where the client is with
    # them (approved / still to review), posts live against plan, and the dashboard's own numbers once live.
    tally = {"creators": 0, "approved": 0, "review": 0}
    for s in sels:
        try:
            codes = json.loads(s["codes"] or "[]")
        except (TypeError, ValueError):
            codes = []
        st = selstatus.of(s["id"])
        tally["creators"] += len(codes)
        for c in codes:
            got = (st.get(c) or {}).get("s", "review")
            if got in ("approved", "review"):
                tally[got] += 1
    out["counts"] = tally
    out["numbers"], out["posts"] = _numbers(k)
    kam = kam_for(k)
    # Everyone sees who runs it; the email stays with the team.
    out["kam"] = ({"email": kam, "name": _kam_name(kam)} if staff else {"name": _kam_name(kam)}) if kam else None
    out["moves"] = moves_for(h, role, who, k, stage, team)
    if staff:
        out["staged"] = bool(k["stage"] if "stage" in k.keys() else None)
    return out


def _order(cards):
    """Pinned first (most recently pinned on top), then the most recently changed."""
    return sorted(cards, key=lambda c: (0 if c["my_pin"] else 1, -(c["pinned_at"] or 0), -(c["updated_at"] or 0), -c["id"]))


def board(h, logo_dir):
    role, who = viewer(h)
    if role is None:
        return None
    staff = role in ("admin", "team", "kam")
    pins = _pins(pin_key(h))
    demo = _demo_ids()
    team = _own_team(who) if role == "client" else None
    cards = _order([card(h, k, role, pins, logo_dir, staff, demo, who, team) for k in _visible(h, role, who)])
    # can_move: this viewer may move at least one card; each card's "moves" says where. can_go_live: admins only.
    return {"role": role, "can_move": any(c["moves"] for c in cards), "can_go_live": role == "admin",
            "locked_stages": [] if role == "admin" else ["live", "completed"], "can_start": role in ("admin", "kam") or _client_user(h, who) is not None,
            "stages": [{"key": s, "label": LABEL[s], "hint": HINT[s]} for s in STAGES], "campaigns": cards}


def _demo_ids():
    """The team's demo campaign(s) (setting pinned_campaigns, owner 2026-10-20, live-only so far): marked "Demo" on
    the board. Not the same thing as a person's own pin (my_pin, item 182)."""
    try:
        return frozenset(int(x) for x in (db.setting("pinned_campaigns") or []))
    except (TypeError, ValueError):
        return frozenset()


def _client_user(h, who):
    import portal
    return portal.user_for_code(int(who)) if who is not None else None


def campaign_for(h, token=None, cid=None):
    """(campaign this viewer may see, by token, or by id for the team; role)."""
    role, who = viewer(h)
    if role is None:
        return None, None
    k = None
    if token:
        k = db.campaign(token=str(token))
    elif cid is not None and role in ("admin", "team", "kam"):
        try:
            k = db.campaign(int(cid))
        except (TypeError, ValueError):
            k = None
    if k is None:
        return None, role
    if k["id"] not in {r["id"] for r in _visible(h, role, who)}:
        return None, role
    return k, role


# ---------------------------------------------------------------- writing --

def _set_stage(cid, stage):
    with db.connect() as conn:
        conn.execute("UPDATE campaigns SET stage = ?, updated_at = ? WHERE id = ?", (stage, now(), int(cid)))


def move(h, k, to, actor=""):
    """Move a campaign to another column. (ok, message, extra). Who may go where: moves_for()."""
    import history
    role, who = viewer(h)
    if to not in STAGES:
        return False, "Unknown stage.", {}
    if role != "admin":
        if k["id"] not in {r["id"] for r in _visible(h, role, who)}:
            return False, "That campaign is not yours to move.", {"status": 403}
        if to not in moves_for(h, role, who, k, stage_of(k)):
            if to in ("live", "completed") or k["status"] != "draft":
                return False, "HelloVoice sets a campaign Live or Completed. Ask your account manager.", {"status": 403}
            return False, "That campaign is not yours to move.", {"status": 403}
    if to == "live":
        missing = [w for w, ok in (("the first and last day", k["starts_at"] and k["ends_at"]), ("the client", k["code_id"])) if not ok]
        if missing:
            return False, "%s can't go live yet: set %s on its Setup tab first." % (k["name"], " and ".join(missing)), \
                {"setup": "/admin/campaigns/edit?id=%d" % k["id"]}
        with history.tracked("campaign", k["id"], "Set %s live from the campaign board" % k["name"]):
            if k["status"] != "live":
                db.save_campaign(k["id"], status="live")
            _set_stage(k["id"], None)
        return True, "%s is live: the client sees its report." % k["name"], {}
    if to == "completed":
        with history.tracked("campaign", k["id"], "Completed %s from the campaign board" % k["name"]):
            if k["status"] != "ended":
                db.save_campaign(k["id"], status="ended")
            _set_stage(k["id"], None)
        return True, "%s is completed." % k["name"], {}
    with history.tracked("campaign", k["id"], "Moved %s to %s on the campaign board" % (k["name"], LABEL[to])):
        if k["status"] != "draft":
            db.save_campaign(k["id"], status="draft")       # off the air: the client no longer sees the report
        _set_stage(k["id"], to)
    return True, "%s moved to %s." % (k["name"], LABEL[to]), {}


def set_live(h, k, on, actor=""):
    """Live / Unlive. Unlive takes the campaign off the air and back to Approved."""
    if on:
        return move(h, k, "live", actor)
    if k["status"] != "live":
        return False, "%s is not live." % k["name"], {}
    return move(h, k, "approved", actor)


def pin(h, k, on):
    who = pin_key(h)
    if not who:
        return False
    with db.connect() as conn:
        if on:
            conn.execute("INSERT OR REPLACE INTO campaign_pins (who, campaign_id, at) VALUES (?,?,?)", (who, int(k["id"]), now()))
        else:
            conn.execute("DELETE FROM campaign_pins WHERE who = ? AND campaign_id = ?", (who, int(k["id"])))
    return True


def link_selection(cid, sid, by=""):
    """Put a selection into a campaign (its creators join the campaign too). True when it was new there."""
    k = db.campaign(int(cid))
    if k is None:
        return False
    if k["selection_id"] and int(k["selection_id"]) == int(sid):
        return False
    with db.connect() as conn:
        if not k["selection_id"]:
            conn.execute("UPDATE campaigns SET selection_id = ?, updated_at = ? WHERE id = ?", (int(sid), now(), int(cid)))
            new = True
        else:
            new = conn.execute("INSERT OR IGNORE INTO campaign_selections (campaign_id, selection_id, added_at, added_by) VALUES (?,?,?,?)",
                               (int(cid), int(sid), now(), by)).rowcount > 0
            if new:
                conn.execute("UPDATE campaigns SET updated_at = ? WHERE id = ?", (now(), int(cid)))
    sel = db.selection(int(sid))
    if new and sel is not None and k["status"] == "draft":
        try:
            db.add_campaign_creators(int(cid), json.loads(sel["codes"] or "[]"))
        except (TypeError, ValueError):
            pass
    return new


def _may_file(h, role, who, sel):
    """May this viewer put this selection into a campaign? Staff for what they reach; a client for a selection
    they own or can edit."""
    import portal
    if role == "admin":
        return True
    if role == "kam":
        return h.admin_like_for(sel["code_id"], sel["id"])
    if role == "client" and who is not None:
        return portal.may_edit(int(who), sel, db.admin_code_id()) or (sel["code_id"] is not None and sel["code_id"] in portal.team_codes(int(who)))
    return False


def targets(h, sel):
    """The campaigns this viewer may add ``sel`` to (dialog list), pinned first. Completed ones are left out."""
    role, who = viewer(h)
    if role is None or not _may_file(h, role, who, sel):
        return None
    pins = _pins(pin_key(h))
    holding = set(campaigns_holding(sel["id"]))
    out = []
    for k in _visible(h, role, who):
        if k["status"] == "ended":
            continue
        if role == "client" and k["code_id"] not in __import__("portal").team_codes(int(who)):
            continue                                  # a client files only into their own team's campaigns
        if role in ("admin", "kam") and sel["code_id"] is not None and k["code_id"] is not None and k["code_id"] != sel["code_id"]:
            continue                                  # staff: the campaigns of the selection's own client
        out.append({"token": k["token"], "name": k["name"], "client": k["client"] or "", "stage": stage_of(k),
                    "has": k["id"] in holding, "my_pin": k["id"] in pins, "pinned_at": pins.get(k["id"]),
                    "updated_at": k["updated_at"], "id": k["id"]})
    out = sorted(out, key=lambda c: (0 if c["my_pin"] else 1, -(c["pinned_at"] or 0), -(c["updated_at"] or 0), -c["id"]))
    for c in out:
        c.pop("pinned_at", None); c.pop("updated_at", None); c.pop("id", None)
    return {"role": role, "campaigns": out, "selection": {"token": sel["token"], "name": sel["name"]}}


def _client_name(sel):
    import portal
    named = sel["client_name"] if "client_name" in sel.keys() else None
    if named:
        return named
    u = portal.user_for_code(sel["code_id"]) if sel["code_id"] is not None else None
    return (u["company"] or u["name"] or None) if u is not None else None


def attach(h, sel, campaign_ref=None, new_name=None):
    """"Create campaign with this selection" (item 174): add ``sel`` to one of the viewer's campaigns, or
    start a new one with it. A new campaign is a Draft under the selection's client; the client's key
    account manager is told (email + bell). Returns (ok, message, campaign row or None, created)."""
    import history
    role, who = viewer(h)
    if role is None:
        return False, "Sign in with your work email first.", None, False
    if not _may_file(h, role, who, sel):
        return False, "You can't file this selection.", None, False
    actor = _actor(h)
    if campaign_ref:
        t = targets(h, sel) or {"campaigns": []}
        if str(campaign_ref) not in {c["token"] for c in t["campaigns"]}:
            return False, "That campaign is not one you can add to.", None, False
        k = db.campaign(token=str(campaign_ref))
        with history.tracked("campaign", k["id"], "Added the selection %s to %s" % (sel["name"], k["name"])):
            new = link_selection(k["id"], sel["id"], actor)
        if new:
            tell_kam(k, sel, actor, created=False)
        return True, ("Added to %s." % k["name"]) if new else ("Already in %s." % k["name"]), db.campaign(k["id"]), False
    name = " ".join(str(new_name or "").split())[:NAME_MAX]
    if len(name) < NAME_MIN:
        return False, "Give the campaign a name (3 letters or more).", None, False
    code_id = sel["code_id"]
    if code_id is None and role == "client":
        code_id = int(who)
    cid = db.create_campaign(name, client=_client_name(sel), code_id=code_id, selection_id=sel["id"],
                             platform=sel["platform"] if "platform" in sel.keys() else None,
                             codes=json.loads(sel["codes"] or "[]"), origin="client" if role == "client" else "team")
    _set_stage(cid, "draft")                       # a new campaign starts as a Draft (owner, 2026-10-20)
    k = db.campaign(cid)
    history.record("created", "campaign", cid, "Started %s from the selection %s" % (name, sel["name"]), None,
                   history.snapshot("campaign", cid))
    kam = kam_for(k)
    if kam:
        db.kam_assign("campaign", cid, kam, actor)  # the campaign is run by the client's KAM
    tell_kam(k, sel, actor, created=True)
    return True, "%s is started as a draft. Your account manager has been told." % name, k, True


def _actor(h):
    import portal
    cid = h.viewer_cookie_id()
    u = portal.user_for_code(cid) if cid is not None else None
    if u is not None:
        return u["name"] or u["email"]
    a = h.admin()
    if a is not None:
        return (a["name"] if "name" in a.keys() and a["name"] else a["email"])
    return "A client"


def tell_kam(k, sel, actor, created):
    """Email + bell to the campaign's key account manager. Never raises."""
    import inbox
    import mailer
    import notify
    import portal
    kam = kam_for(k)
    line = ('%s started the campaign "%s" with the selection "%s".' % (actor, k["name"], sel["name"]) if created
            else '%s added the selection "%s" to the campaign "%s".' % (actor, sel["name"], k["name"]))
    try:
        notify.send("campaign_started", [line, "It is on the campaign board as %s." % LABEL[stage_of(k)]],
                    kam=kam or None, link=mailer.SITE + "/campaign/#board")
    except Exception:
        pass
    try:
        addr = notify.kam_address(kam) if kam else None
        u = portal.user_by_email(addr) if addr else None
        if u is not None and u["id"]:
            inbox.emit([u["id"]], "camp_shared", line, body="Open the campaign board to follow it.", href="campaign/#board",
                       ref="board:%d:%d" % (k["id"], sel["id"]), once=True)
    except Exception:
        pass


# ------------------------------------------------------------ selections --
# Item 194 (owner, 2026-10-20): the account page shows selections on the same six columns. A selection's
# column is read from its quote; while its quote is still open (draft, requested, ready) anyone who may
# work on it can drag it between the four planning columns, and that choice is kept in selections.stage.
# Approved, Live and Completed always come from the quote and its campaign: a drag never claims them.

_SEL_FROM_QUOTE = {"approved": "approved", "live": "live", "completed": "completed"}
_SEL_OPEN = ("draft", "requested", "ready")


def selection_stage(sel, chip_key, creators=None):
    """The column a selection sits in."""
    if chip_key in _SEL_FROM_QUOTE:
        return _SEL_FROM_QUOTE[chip_key]
    st = sel["stage"] if "stage" in sel.keys() else None
    if st in DRAFT_STAGES:
        return st
    if chip_key in ("requested", "ready"):
        return "review"
    n = creators if creators is not None else _creators(sel)
    return "shortlisting" if n else "draft"


def selection_moves(may, chip_key, stage):
    """Where a selection may be dragged: the planning columns, while its quote is open and ``may`` is true."""
    if not may or chip_key not in _SEL_OPEN:
        return []
    return [s for s in DRAFT_STAGES if s != stage]


def may_move_selection(h, sel):
    """An admin any selection; a KAM her clients' or one handed to her; a client their own team's."""
    role, who = viewer(h)
    if role == "admin":
        return True
    if role == "kam":
        return h.admin_like_for(sel["code_id"], sel["id"], None)
    if role == "client":
        return sel["code_id"] is not None and sel["code_id"] in _own_team(who)
    return False


def move_selection(h, sel, to):
    """Drag a selection to another planning column. (ok, message, extra)."""
    import history
    import lifecycle
    if viewer(h)[0] is None:
        return False, "Sign in with your work email first.", {"status": 401}
    if to not in STAGES:
        return False, "Unknown stage.", {}
    if not may_move_selection(h, sel):
        return False, "That selection is not yours to move.", {"status": 403}
    key = lifecycle.chip(sel)["key"]
    if to == selection_stage(sel, key):
        return True, "%s is already in %s." % (sel["name"], LABEL[to]), {"stage": to}
    if to not in DRAFT_STAGES:
        return False, "A selection reaches %s with its campaign, not by a drag." % LABEL[to], {"status": 403}
    if key not in _SEL_OPEN:
        return False, "%s's quote is approved: it moves with its campaign now." % sel["name"], {"status": 403}
    with history.tracked("selection", sel["id"], "Moved %s to %s on the board" % (sel["name"], LABEL[to])):
        with db.connect() as conn:
            conn.execute("UPDATE selections SET stage = ? WHERE id = ?", (to, int(sel["id"])))
    return True, "%s moved to %s." % (sel["name"], LABEL[to]), {"stage": to}
