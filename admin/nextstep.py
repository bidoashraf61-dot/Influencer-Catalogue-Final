"""Next-step suggestions on the board and the 9:00 digest (item 218 phase 1, 2026-10-21).

Suggestions are rules, free and instant: each staff card on the campaign board gets one suggested next step
with a due date, read from what the board already knows (stage, how long nothing moved, posts against plan,
the dashboard's verdict) plus the report drafts and post flags waiting. "Use" copies it into the card's own
next step (the existing board edit), so nothing changes until someone presses it. Clients never see these.

The digest: once a day at 9:00 Riyadh time, every active admin and account manager with something waiting gets
one bell + phone push (``team_digest``) listing their top five, worst first: overdue steps, flagged posts,
report drafts, then the suggestions. Admins see every client, a KAM her own (the same scope as "Needs you").
The lines are rule-written; when the "nextstep" AI helper is on, one light Gemini call per person rewords them
into a friendlier message (never adds or drops an item).
"""
import datetime
import json
import threading
import time

import db

DAY = 86400
RIYADH = 3 * 3600
DIGEST_HOUR = 9
TOP = 5
QUIET_DAYS = 7          # a planning card with no change for this long gets a nudge
_started = False

PRIORITY = {"overdue": 0, "flags": 1, "report": 2, "behind": 3, "chase_posts": 4, "review": 5, "golive": 6, "wrapup": 7, "quiet": 8}


def _days(n):
    return n * DAY


def _today_end(now=None):
    """End of today in Riyadh, as a UTC timestamp (the board's due dates are day-precision)."""
    now = now or db.now()
    d = datetime.datetime.utcfromtimestamp(now + RIYADH).date()
    return int((datetime.datetime(d.year, d.month, d.day) - datetime.datetime(1970, 1, 1)).total_seconds()) - RIYADH + DAY - 1


def _waiting(cid):
    """(report drafts waiting, flagged posts) for one campaign. Cheap: two counts."""
    import postcheck
    import reportai
    reportai.init()
    postcheck.init()
    with db.connect() as conn:
        rep = conn.execute("SELECT period FROM campaign_reports WHERE campaign_id = ? AND status = 'draft' ORDER BY created_at DESC LIMIT 1",
                           (cid,)).fetchone()
        flags = conn.execute("SELECT COUNT(*) FROM content_checks x JOIN content c ON c.id = x.content_id AND c.hidden = 0 "
                             "WHERE x.campaign_id = ? AND x.status = 'fail' AND x.cleared_at IS NULL", (cid,)).fetchone()[0]
    return (rep["period"] if rep else None), flags


def suggest(k, stage, numbers=None, posts=None, now=None):
    """One suggestion for a campaign card: {"key", "text", "due", "why"}, or None. Rules only."""
    import reportai
    now = now or db.now()
    today = _today_end(now)
    ns = (k["next_step"] if "next_step" in k.keys() else None) or ""
    nd = k["next_due"] if "next_due" in k.keys() else None
    rep, flags = _waiting(k["id"])
    if ns and nd and nd + DAY <= now:
        late = int((now - nd) // DAY)
        return {"key": "overdue", "text": ns, "due": today, "why": "Overdue by %d day%s" % (late, "" if late == 1 else "s")}
    if flags:
        return {"key": "flags", "text": "Check %d flagged post%s" % (flags, "" if flags == 1 else "s"), "due": today,
                "why": "Disclosure, tags or claim wording"}
    if rep:
        return {"key": "report", "text": "Approve the %s" % reportai.label(rep).lower(), "due": today,
                "why": "Helvi wrote a draft; the client sees it once approved"}
    quiet = int((now - (k["updated_at"] or now)) // DAY)
    if stage == "live":
        v = ((numbers or {}).get("verdict") or {}).get("grade")
        if v == "low":
            return {"key": "behind", "text": "Agree a catch-up plan with the client", "due": today + _days(2),
                    "why": "The dashboard says behind target"}
        p = posts or {}
        planned, live = p.get("planned") or 0, p.get("live") or 0
        if planned and live < planned and k["starts_at"] and k["ends_at"]:
            span = max(DAY, k["ends_at"] - k["starts_at"])
            elapsed = (now - k["starts_at"]) / float(span)
            if elapsed >= 0.5 and live < planned * elapsed:
                left = planned - live
                return {"key": "chase_posts", "text": "Chase %d post%s still to go live" % (left, "" if left == 1 else "s"),
                        "due": today + _days(1), "why": "%d of %d posts live, %d%% of the time gone" % (live, planned, round(elapsed * 100))}
    if stage == "review" and quiet >= 3:
        return {"key": "review", "text": "Ask the client for their decision on the creators", "due": today + _days(1),
                "why": "With the client for %d days" % quiet}
    if stage == "approved" and (not k["starts_at"] or k["starts_at"] <= now):
        return {"key": "golive", "text": "Set the start date and go live", "due": today + _days(2),
                "why": "Agreed but not live yet"}
    if stage == "completed" and k["ends_at"] and now - k["ends_at"] <= _days(21):
        try:
            final = reportai.row(k["id"], "final")
        except Exception:
            final = None
        if final is None or final["status"] != "approved":
            return {"key": "wrapup", "text": "Send the final report and pitch the next campaign", "due": today + _days(3),
                    "why": "Ended %d days ago" % max(0, int((now - k["ends_at"]) // DAY))}
    if stage in ("draft", "shortlisting") and quiet >= QUIET_DAYS:
        return {"key": "quiet", "text": "Follow up: nothing has moved for %d days" % quiet, "due": today + _days(1),
                "why": "Still in %s" % stage.capitalize()}
    return None


def for_card(k, stage, numbers, posts):
    """What a staff card carries: the suggestion, unless it is already the card's own next step."""
    try:
        s = suggest(k, stage, numbers, posts)
    except Exception:
        return None
    if s is None:
        return None
    ns = ((k["next_step"] if "next_step" in k.keys() else None) or "").strip().lower()
    if s["key"] != "overdue" and ns and ns == s["text"].strip().lower():
        return None
    return s


# ------------------------------------------------------------------ digest --

def _staff():
    """[(portal user row, role, admin row)] for every active admin / KAM with a portal account."""
    import portal
    import team
    out = []
    for a in team.list_admins():
        if a["disabled_at"]:
            continue
        r = team.role_of(a)
        role = "admin" if r in ("owner", "admin") else "kam" if r == "kam" else None
        if role is None:
            continue
        u = portal.user_by_email(a["email"]) if a["email"] else None
        if u is not None and u["status"] == "active":
            out.append((u, role, a))
    return out


def items_for(role, a, now=None):
    """Everything waiting for one person, worst first: [{"key", "text", "campaign", "why", "href"}]."""
    import board
    import needs
    now = now or db.now()
    scope = needs._scope(role, a)
    out = []
    for k in db.list_campaigns():
        if k["status"] == "ended" and k["ends_at"] and now - k["ends_at"] > _days(21):
            continue
        if scope is not None and not (needs._mine(scope, k["code_id"]) or k["id"] in (getattr(scope, "camp_ids", None) or ())):
            continue
        try:
            sels = board._selections(board.selection_ids(k))
            stage = board.stage_of(k, sels)
            numbers, posts = board._numbers(k) if stage in ("live", "completed") else (None, None)
            s = suggest(k, stage, numbers, posts, now)
        except Exception:
            continue
        if s is not None:
            out.append(dict(s, campaign=k["name"], token=k["token"], href="account/#board"))
    out.sort(key=lambda x: (PRIORITY.get(x["key"], 9), x["due"] or 0))
    return out


REWORD = {"type": "OBJECT", "properties": {"lines": {"type": "ARRAY", "items": {"type": "STRING"}}}, "required": ["lines"]}


def _lines(items):
    return ["%s: %s" % (i["campaign"], i["text"]) + (" (%s)" % i["why"] if i.get("why") else "") for i in items]


def _reworded(lines):
    import aifeatures
    import gemini
    if not aifeatures.allowed("nextstep"):
        return None
    try:
        got = gemini.generate_json("Lines:\n" + json.dumps(lines, ensure_ascii=False), REWORD,
                                   system="Rewrite each line as one short, friendly to-do for an account manager (max 90 characters). "
                                          "Keep the campaign name first. Same number of lines, same order, no new facts, no prices.",
                                   kind="next_step_ai", temperature=0.3, max_tokens=500, timeout=25,
                                   model_name=gemini.chat_model(), think=0)
        out = [" ".join(str(x).split())[:120] for x in (got.get("lines") or [])]
        return out if len(out) == len(lines) and all(out) else None
    except Exception:
        return None


def digest(now=None, only=None):
    """Send today's digest to everyone who has something waiting. Returns how many were sent."""
    import inbox
    now = now or db.now()
    day = datetime.datetime.utcfromtimestamp(now + RIYADH).strftime("%Y-%m-%d")
    sent = 0
    for u, role, a in _staff():
        if only is not None and u["id"] not in only:
            continue
        items = items_for(role, a, now)
        if not items:
            continue
        top = items[:TOP]
        lines = _reworded(_lines(top)) or _lines(top)
        more = len(items) - len(top)
        title = "Today: %d thing%s need you" % (len(items), "" if len(items) == 1 else "s")
        body = "\n".join("• " + l for l in lines) + ("\n+%d more on the board" % more if more > 0 else "")
        inbox.emit([u["id"]], "team_digest", title, body=body, href="account/#needs", ref="digest:" + day, once=True,
                   meta={"day": day, "count": len(items)})
        sent += 1
    return sent


def due(now=None):
    """True once a day, after 9:00 Riyadh, until today's digest went out."""
    now = now or db.now()
    local = datetime.datetime.utcfromtimestamp(now + RIYADH)
    return local.hour >= DIGEST_HOUR and db.setting("digest_last_day", "") != local.strftime("%Y-%m-%d")


def tick(now=None):
    now = now or db.now()
    if not due(now):
        return None
    day = datetime.datetime.utcfromtimestamp(now + RIYADH).strftime("%Y-%m-%d")
    db.set_setting("digest_last_day", day)          # before sending: a crash mid-way never sends twice (the bell's ref also guards)
    return digest(now)


def _loop():
    time.sleep(120)
    while True:
        try:
            tick()
        except Exception as ex:
            print("nextstep:", type(ex).__name__, ex, flush=True)
        time.sleep(600)


def start():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, name="next-step-digest", daemon=True).start()
