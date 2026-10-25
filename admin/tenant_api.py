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
    u = portal.user_for_code(cid)
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
      the tenant's captures-a-day cap   (Tenants -> Limits; 0 or unset means none)
      Apify's own monthly budget        (apify.start_job refuses past it)
      one run at a time per competitor  (a job already running is not started twice)
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
