"""What a tenant may write for themselves, when their module is set to `manage`.

These are the tenant's own endpoints, not the team's. `contentedit.py` -- the admin's
campaign editing -- stays closed to clients, exactly as its docstring says; what happens
here is the same db calls behind a narrower door:

    the module must be `manage` for this tenant   (modules.level)
    the campaign must be theirs                   (campaigns.code_id)
    they must be signed in as that client         (signed_in_client)

A refusal is never silent: the tenant is told which of the three it was, so an account
manager reading it over their shoulder knows what to change.

Every change is written to History against the campaign with the client's email as the
actor, so a post a client added and a post the team added are told apart afterwards.
"""
import db
import modules

TRACK = "helvi-track"
INTEL = "helvi-intelligence"


def _who(h):
    """The signed-in client, or None. An admin reading a client page is not a tenant:
    the team has its own screens and should use them."""
    try:
        if h.admin_like():
            return None
        return h.signed_in_client()
    except Exception:
        return None


def gate(h, module, token=None):
    """(code_id, campaign row or None, error payload or None)."""
    cid = _who(h)
    if cid is None:
        return None, None, (401, {"ok": False, "reason": "signin",
                                  "message": "Sign in with your work email first."})
    # A person invited into a company works on the company's account, within their role there.
    import portal
    import workspace
    u = portal.user_for_code(cid)
    if u is not None:
        h._tenant_user = u
        cid = workspace.tenant_of(u)
        if workspace.RANK[workspace.effective(u, module)] < workspace.RANK["editor"]:
            return None, None, (403, {"ok": False, "reason": "no_role",
                                      "message": "Your role here reads only. Ask your account admin for editor access."})
    if modules.level(cid, module) != "manage":
        return None, None, (403, {"ok": False, "reason": "not_manage",
                                  "message": "Your account reads this; it does not edit it. "
                                             "Ask your account manager to open it up."})
    if token is None:
        return cid, None, None
    k = db.campaign(token=str(token or "")) if token else None
    if k is None or k["code_id"] != cid:
        return None, None, (404, {"ok": False, "reason": "unknown",
                                  "message": "That campaign is not on your account."})
    return cid, k, None


def actor(h, cid):
    import portal
    u = getattr(h, "_tenant_user", None) or portal.user_for_code(cid)
    return ("client: " + (u["email"] if u is not None else "")).strip()


# ------------------------------------------------------------------ Track --

def add_post(h, b):
    cid, k, err = gate(h, TRACK, b.get("t"))
    if err:
        return err
    import contentedit
    text = str(b.get("text") or "").strip()
    if text:
        return contentedit.bulk_links(k, actor(h, cid), str(b.get("code") or ""), text, str(b.get("platform") or ""))
    return contentedit.add_post(k, actor(h, cid), str(b.get("code") or ""), str(b.get("url") or ""),
                                platform=str(b.get("platform") or ""), kind=str(b.get("kind") or ""),
                                caption=str(b.get("caption") or ""), posted=str(b.get("posted") or ""),
                                counts=b.get("counts") or {})


def update_post(h, b):
    """The tenant corrects a post on their own campaign: its numbers, or hide / unhide / delete."""
    cid, k, err = gate(h, TRACK, b.get("t"))
    if err:
        return err
    import contentedit
    do = str(b.get("do") or "").strip()
    if do == "numbers":
        return contentedit.set_numbers(k, actor(h, cid), b.get("id"), b.get("values") or {})
    if do in ("hide", "unhide", "delete"):
        return contentedit.update_post(k, actor(h, cid), b.get("id"), do)
    return 400, {"ok": False, "message": "Say what to do with the post."}


# ----------------------------------------------------------- Intelligence --

def competitors_list(h):
    cid, _, err = gate(h, INTEL)
    if err:
        return err
    import competitors
    # Each item carries last_run_at and last_note, so the tenant sees why a run came back empty.
    return 200, {"ok": True, "items": competitors.listing(cid), "platforms": list(competitors.PLATFORMS),
                 # Said plainly rather than implied: naming one does not start a collection.
                 "note": "HelloVoice studies the competitors you name here and files the evidence under your account."}


def competitor_save(h, b):
    cid, _, err = gate(h, INTEL)
    if err:
        return err
    import competitors
    op = str(b.get("op") or "add")
    if op == "remove":
        competitors.remove(cid, b.get("id"))
        return 200, {"ok": True, "items": competitors.listing(cid)}
    if op == "edit":
        ok, why = competitors.edit(cid, b.get("id"), b.get("name"), b.get("handles"), b.get("note"))
        if not ok:
            return 400, {"ok": False, "message": why}
        return 200, {"ok": True, "items": competitors.listing(cid)}
    new, why = competitors.add(cid, b.get("name"), b.get("handles"), str(b.get("note") or ""), actor(h, cid))
    if new is None:
        return 400, {"ok": False, "message": why}
    _tell_the_team(cid, b.get("name"))
    return 200, {"ok": True, "id": new, "items": competitors.listing(cid)}


def collect(h, b):
    """Start a collection run for one of the tenant's competitors (Helvi Intelligence at manage).

    Three brakes, in this order, because each costs more to find out the hard way:
      the tenant's captures-a-day cap   (Tenants -> Limits; unset means none)
      the tenant's monthly spend cap    (what Apify actually billed their runs, not an estimate)
      Apify's own monthly budget        (apify.start_job refuses past it, for everyone together)
      one run at a time per competitor  (a job already running is not started twice)

    The spend cap is the one that matters: a day cap limits how often a tenant runs, not what
    they cost, and the Apify budget is shared -- without this, one tenant can spend everybody's.
    """
    cid, _, err = gate(h, INTEL)
    if err:
        return err
    import apify
    import competitors
    comp = competitors.get(b.get("id"))
    if comp is None or comp["code_id"] != cid:
        return 404, {"ok": False, "message": "That competitor is not on your list."}
    cap = modules.number(cid, "captures_day")
    if cap is not None and competitors.runs_today(cid) >= cap:
        return 403, {"ok": False, "reason": "limit",
                     "message": "You have used today's %d collection%s. It resets tomorrow." % (cap, "" if cap == 1 else "s")}
    spend_cap = modules.number(cid, "spend_month")
    if spend_cap is not None:
        used = competitors.spend_month(cid)
        est = float(apify.PRESETS["comp_ig"]["est"])
        if used + est > spend_cap:
            return 403, {"ok": False, "reason": "limit",
                         "message": "Collections have used $%.2f of this month's $%d. "
                                    "Ask your account manager to raise it." % (used, spend_cap)}
    plat = "Instagram"                       # the only platform a collection reads for now
    if not (comp["handles"] or {}).get(plat):
        return 400, {"ok": False, "message": "Add their %s handle first." % plat}
    jid = _collection_job(comp, plat)
    ok, said = apify.start_job(jid, trigger="client")
    if ok:
        competitors.mark_run(comp["id"])
    return (200 if ok else 400), {"ok": bool(ok), "message": said if not ok else
                                  "Collecting. The evidence appears on your account when it finishes."}


def _collection_job(comp, platform):
    """The Apify job for this competitor, made once and reused so its runs stay together."""
    import apify
    src = "competitor:%d" % comp["id"]
    for j in apify.list_jobs():
        if j["source"] == src and j["platform"] == platform:
            return j["id"]
    p = apify.PRESETS["comp_ig"]
    return apify.save_job({"name": "Competitor · %s" % comp["name"], "actor": p["actor"], "kind": p["kind"],
                           "platform": platform, "source": src, "input": p["input"],
                           "max_handles": "1", "schedule": "manual", "est_each": str(p["est"])})


def _tell_the_team(cid, name):
    """A named competitor is a job for somebody: it reaches the account manager the same way a
    creator request does. Quietly ignored if the notify path is unavailable."""
    try:
        import kam_items
        if hasattr(kam_items, "tell_competitor_named"):
            kam_items.tell_competitor_named(cid, name)
            return
    except Exception:
        pass
    try:
        db.log("competitor", cid, None, None, "named:%s" % str(name or "")[:80])
    except Exception:
        pass


# ------------------------------------------------- Track: the tenant's own campaigns --
# The Work tab of Helvi Track in /workspace/. A company at `manage` sets up and runs its own
# campaigns here; the team's /campaigns screens stay theirs. Going live is what starts the
# daily capture jobs, so it is counted against the campaigns cap like a new campaign is.

def _day(s):
    """'2026-11-03' -> UTC midnight, or None."""
    import datetime
    try:
        d = datetime.datetime.strptime(str(s or "")[:10], "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
        return int(d.timestamp())
    except ValueError:
        return None


def _iso(ts):
    import datetime
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d") if ts else ""


def _words(v):
    """'#a, #b c' -> ['#a', '#b', 'c'] (hashtags and mentions as the rules hold them)."""
    out = []
    for w in str(v or "").replace(",", " ").split():
        if w not in out:
            out.append(w[:60])
    return out[:20]


def campaigns_list(h):
    cid, _, err = gate(h, TRACK)
    if err:
        return err
    out = []
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM campaigns WHERE code_id = ? ORDER BY CASE status WHEN 'live' THEN 0 "
                            "WHEN 'draft' THEN 1 ELSE 2 END, updated_at DESC LIMIT 50", (cid,)).fetchall()
        for k in rows:
            posts = conn.execute("SELECT COUNT(*) n FROM content WHERE campaign_id = ?", (k["id"],)).fetchone()["n"]
            rules = db.rules_of(k)
            out.append({"t": k["token"], "name": k["name"], "client": k["client"] or "", "status": k["status"],
                        "platform": k["platform"] or "", "starts": _iso(k["starts_at"]), "ends": _iso(k["ends_at"]),
                        "hashtags": " ".join(rules.get("hashtags") or []), "mentions": " ".join(rules.get("mentions") or []),
                        "posts": posts,
                        "creators": [{"code": c["cc_code"], "name": c["name"] or c["cc_code"], "handle": c["handle"] or "",
                                      "platform": c["platform"] or ""} for c in db.campaign_creators(k["id"])]})
    return 200, {"ok": True, "items": out, "platforms": db.PLATFORMS,
                 "cap": modules.number(cid, "campaigns_max"), "count": modules.count(cid, "campaigns")}


def campaign_save(h, b):
    """op: create | edit | live | end."""
    op = str(b.get("op") or "create")
    if op == "create":
        cid, _, err = gate(h, TRACK)
        if err:
            return err
        if modules.over(cid, "campaigns_max", modules.count(cid, "campaigns")):
            return 403, {"ok": False, "reason": "limit",
                         "message": "You have all %d campaigns your plan includes. Request more to add another."
                                    % modules.number(cid, "campaigns_max")}
        name = " ".join(str(b.get("name") or "").split())[:120]
        if len(name) < 2:
            return 400, {"ok": False, "message": "Give the campaign a name."}
        plat = b.get("platform") if b.get("platform") in db.PLATFORMS else None
        # "Track this campaign" from a selection: its creators come along (only the company's own selection).
        sel, codes = None, []
        if b.get("s"):
            import json as _json
            sel = db.selection(token=str(b.get("s")))
            if sel is None or sel["code_id"] != cid:
                return 404, {"ok": False, "message": "That selection is not on your account."}
            known = {c["code"] for c in db.list_creators()}
            codes = [c for c in _json.loads(sel["codes"] or "[]") if c in known]
            plat = plat or sel["platform"]
        kid = db.create_campaign(name, client=" ".join(str(b.get("client") or "").split())[:120] or None,
                                 code_id=cid, platform=plat, origin="client",
                                 selection_id=sel["id"] if sel is not None else None, codes=codes)
        k = db.campaign(kid)
        _edit(k, b)
        _log(k, actor(h, cid), "Created the campaign")
        return 200, {"ok": True, "t": k["token"], "message": "Campaign created as a draft. Add creators, then go live."}
    cid, k, err = gate(h, TRACK, b.get("t"))
    if err:
        return err
    if op == "edit":
        _edit(k, b)
        _log(k, actor(h, cid), "Edited the campaign")
        return 200, {"ok": True, "message": "Saved."}
    if op == "live":
        if not (k["starts_at"] and k["ends_at"]):
            return 400, {"ok": False, "message": "Set the start and end dates first."}
        if not db.campaign_creators(k["id"]):
            return 400, {"ok": False, "message": "Add at least one creator first."}
        db.save_campaign(k["id"], status="live")
        _log(k, actor(h, cid), "Set the campaign live")
        return 200, {"ok": True, "message": "Live. Posts are collected daily from now on."}
    if op == "add_creators":
        # Creators by profile link (one a line): the company's own private creators (creators_private.py),
        # filed once and reused. A link already on their account comes back as the same creator.
        import creators_private
        links = [x.strip() for x in str(b.get("links") or "").replace(",", "\n").splitlines() if x.strip()][:50]
        if not links:
            return 400, {"ok": False, "message": "Paste at least one profile link."}
        codes, bad = [], []
        for link in links:
            got = creators_private.add_by_handle(cid, link)
            if got.get("ok"):
                codes.append(got["code"])
            else:
                bad.append(link)
        added = db.add_campaign_creators(k["id"], codes) if codes else 0
        _log(k, actor(h, cid), "Added %d creator(s) by link" % added)
        msg = ("%d creator%s added." % (added, "" if added == 1 else "s")) if added else "Already in this campaign."
        if bad:
            msg += " Not a profile link: %s." % ", ".join(bad[:3])
        return (200 if codes else 400), {"ok": bool(codes), "message": msg}
    if op == "remove_creator":
        code = str(b.get("code") or "").strip().upper()
        if code not in {c["cc_code"] for c in db.campaign_creators(k["id"])}:
            return 404, {"ok": False, "message": "That creator is not in this campaign."}
        db.save_campaign_creators(k["id"], {}, remove=[code])
        _log(k, actor(h, cid), "Removed %s" % code)
        return 200, {"ok": True, "message": "Removed."}
    if op == "end":
        db.save_campaign(k["id"], status="ended")
        _log(k, actor(h, cid), "Ended the campaign")
        return 200, {"ok": True, "message": "Ended. The report stays available."}
    return 400, {"ok": False, "message": "Say what to do with the campaign."}


def _edit(k, b):
    f = {}
    if "name" in b and len(" ".join(str(b.get("name") or "").split())) >= 2:
        f["name"] = " ".join(str(b["name"]).split())[:120]
    if "client" in b:
        f["client"] = " ".join(str(b.get("client") or "").split())[:120] or None
    if "platform" in b:
        f["platform"] = b.get("platform") if b.get("platform") in db.PLATFORMS else None
    s, e = _day(b.get("starts")), _day(b.get("ends"))
    if s:
        f["starts_at"] = s
    if e:
        f["ends_at"] = e + 86399
    if "hashtags" in b or "mentions" in b:
        rules = dict(db.rules_of(k))
        if "hashtags" in b:
            rules["hashtags"] = _words(b.get("hashtags"))
        if "mentions" in b:
            rules["mentions"] = _words(b.get("mentions"))
        f["rules"] = rules
    if f:
        db.save_campaign(k["id"], **f)


def _log(k, who, what):
    try:
        import history
        history.record("client_campaign", "campaign", k["id"], "%s: %s" % (who, what), None, k["name"])
    except Exception:
        pass


# ------------------------------------------- Intelligence: the tenant's own evidence --
# The Results tab of Helvi Intelligence in /workspace/. Reading needs only the module on and a
# role of viewer or better. A creator a competitor used who is also on the HelloVoice roster
# carries a tag: it opens the creator's card when the company owns Helvi Selection, and is a
# locked "Available through Helvi Selection" otherwise -- the roster code is not sent then.

def _reader(h, module):
    """(company code, person) for a read, or an error payload."""
    cid = _who(h)
    if cid is None:
        return None, None, (401, {"ok": False, "reason": "signin", "message": "Sign in with your work email first."})
    import portal
    import workspace
    u = portal.user_for_code(cid)
    if u is None:
        return None, None, (401, {"ok": False, "reason": "signin", "message": "Sign in with your work email first."})
    if workspace.effective(u, module) == "none":
        return None, None, (403, {"ok": False, "reason": "no_role", "message": "This module is not in your role."})
    return workspace.tenant_of(u), u, None


def evidence_list(h):
    cid, u, err = _reader(h, INTEL)
    if err:
        return err
    import workspace
    selection_open = workspace.effective(u, "helvi-selection") != "none"
    out = []
    with db.connect() as conn:
        packs = conn.execute("SELECT id, title, created_at, updated_at FROM evidence_packs WHERE code_id = ? "
                             "AND client_visible = 1 AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT 20", (cid,)).fetchall()
        for p in packs:
            rows = conn.execute("SELECT competitor, platform, handle, name, followers, code, views, url FROM evidence_posts "
                                "WHERE pack_id = ?", (p["id"],)).fetchall()
            by = {}
            for r in rows:
                key = (r["platform"], (r["handle"] or "").lower())
                c = by.setdefault(key, {"handle": r["handle"] or "", "name": r["name"] or r["handle"] or "",
                                        "platform": r["platform"], "followers": r["followers"], "posts": 0,
                                        "best_views": 0, "competitors": [], "on_roster": False, "code": None})
                c["posts"] += 1
                c["best_views"] = max(c["best_views"], r["views"] or 0)
                if r["competitor"] not in c["competitors"]:
                    c["competitors"].append(r["competitor"])
                if r["code"]:
                    c["on_roster"] = True
                    c["code"] = r["code"] if selection_open else None
            creators = sorted(by.values(), key=lambda c: (-c["posts"], -(c["best_views"] or 0)))
            out.append({"id": p["id"], "title": p["title"], "updated": p["updated_at"] or p["created_at"],
                        "posts": len(rows), "competitors": sorted({r["competitor"] for r in rows}),
                        "creators": creators[:60], "more": max(0, len(creators) - 60)})
    return 200, {"ok": True, "packs": out, "selection_open": selection_open}
