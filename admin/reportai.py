"""Report writer (item 218 phase 1, 2026-10-21): an AI draft of each live campaign's weekly report and of
its final report, which the account manager edits and approves before the client sees it.

    weekly   one draft per campaign-week, made by the weekly job right after the automatic 3-line bell
             (weekly.py), which stays exactly as it is.
    final    one draft when the campaign ends (status Ended or end date passed).

The draft is built only from the campaign's own numbers (metrics.report), the weekly verdict, the
comment insights the client already sees, and the Next time panel: the same facts the dashboard shows.
It never contains prices, fees, costs, scores or anything from a creator's profile analysis, and a draft
that mentions one is thrown away. A KAM may ask for a fresh draft up to three times per period.

Nothing reaches the client until someone approves it: approval stores the (possibly edited) text, shows
it as "Summary from HelloVoice" on the dashboard and rings the client's bell once (``camp_report``).
The KAM hears about a new draft through the bell (``team_report``) and the profile's "Needs you" queue.
The AI part runs only when the "report" helper is switched on (aifeatures); otherwise nothing is drafted.
"""
import json
import re

import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign_reports (
    id INTEGER PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    period TEXT NOT NULL,           -- 'w3' = third campaign week, '2026-W41' for undated campaigns, 'final'
    draft TEXT,                     -- JSON as the AI wrote it: summary, worked, improve, next
    body TEXT,                      -- JSON as approved (the KAM's edits); NULL until approved
    status TEXT NOT NULL DEFAULT 'draft',    -- draft | approved | dismissed
    tries INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    approved_by TEXT,
    approved_at INTEGER,
    UNIQUE (campaign_id, period)
);
"""
MAX_TRIES = 3
FIELDS = ("summary", "worked", "improve", "next")
LIMITS = {"summary": 600, "worked": 3, "improve": 3, "next": 3}
BANNED = re.compile(r"\bSAR\b|\$|USD|ريال|price|pricing|fee|fees|cost|budget|invoice|score|scored|analysis", re.I)

RESULT = {"type": "OBJECT", "properties": {
    "summary": {"type": "STRING"},
    "worked": {"type": "ARRAY", "items": {"type": "STRING"}},
    "improve": {"type": "ARRAY", "items": {"type": "STRING"}},
    "next": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["summary", "worked", "improve", "next"]}

SYSTEM = ("You write a short campaign report for a brand client of HelloVoice, an influencer agency. Use ONLY the facts "
          "given; never invent a number. Plain, warm, specific English (or Arabic if the campaign language is Arabic). "
          "summary: 2-4 sentences on where the campaign stands against its goal. worked: up to 3 short bullets. "
          "improve: up to 3 short bullets. next: exactly 3 concrete recommendations for the coming week (or the next "
          "campaign, for a final report). Never mention prices, fees, costs, budgets, scores or profile analyses.")

_ready = False


def init():
    global _ready
    if _ready:
        return
    with db.connect() as conn:
        conn.executescript(SCHEMA)
    _ready = True


# ------------------------------------------------------------------ facts --

def _period(k, week):
    return ("w" + week) if week and week.isdigit() else (week or "final")


def facts(k, final=False):
    """The plain facts the model may use. Same numbers as the client's dashboard, nothing internal."""
    import metrics
    import weekly
    r = metrics.report(k)
    t = r["total"]
    v = weekly.verdict(k, r) or {}
    people = []
    for c in r["creators"]:
        if not c.get("posts") and not c.get("planned"):
            continue
        people.append({"name": c.get("name"), "rank": c.get("rank"), "posts": c.get("posts") or 0,
                       "planned": c.get("planned") or 0, "views": c.get("views"), "engagement": c.get("engagement"),
                       "engagement_rate": c.get("video_er") if c.get("video_er") is not None else c.get("er")})
    people.sort(key=lambda x: (x["rank"] is None, x["rank"] or 0))
    out = {"campaign": k["name"], "client": k["client"] or "", "objective": r["objective"]["label"],
           "status": v.get("title") or r["verdict"]["label"], "three_lines": v.get("lines") or [],
           "totals": {key: t.get(key) for key in ("posts", "planned", "views", "reach", "engagement", "er", "video_er", "clicks")
                      if t.get(key) is not None},
           "goals": [{"kpi": i["key"], "actual": i["actual"], "goal": i["goal"], "pct": round(i["pct"])}
                     for i in (r["progress"].get("items") or [])],
           "creators": people[:12], "final": bool(final)}
    try:
        import comments
        cv = comments.client_view(k)
        if cv["status"] == "ready":
            n = sum(b["n"] for b in cv["buckets"])
            pos = sum(b["pos"] for b in cv["buckets"])
            neg = sum(b["neg"] for b in cv["buckets"])
            themes = {}
            for b in cv["buckets"]:
                for th, c in b["themes"].items():
                    themes[th] = themes.get(th, 0) + c
            out["comments"] = {"read": n, "positive": pos, "negative": neg,
                               "top_themes": [th for th, _ in sorted(themes.items(), key=lambda x: -x[1])[:4]]}
    except Exception:
        pass
    if final:
        try:
            p = weekly.panel(k)
            if p:
                out["next_time"] = {g: [x["name"] for x in p[g]] for g in ("rebook", "replace", "watch")}
        except Exception:
            pass
    return out


def _clean(d):
    """Trim the model's answer to the shape and limits, or None when it breaks a rule."""
    if not isinstance(d, dict):
        return None
    out = {"summary": " ".join(str(d.get("summary") or "").split())[:LIMITS["summary"]]}
    for f in ("worked", "improve", "next"):
        items = [" ".join(str(x).split())[:220] for x in (d.get(f) or []) if str(x).strip()]
        out[f] = items[:LIMITS[f]]
    if not out["summary"] or not out["next"]:
        return None
    text = " ".join([out["summary"]] + out["worked"] + out["improve"] + out["next"])
    if BANNED.search(text):
        return None
    return out


def write(k, final=False):
    """One Gemini call. Returns the cleaned draft, or None. Raises nothing."""
    import aifeatures
    import gemini
    if not aifeatures.allowed("report"):
        return None
    try:
        f = facts(k, final)
        if not f["totals"].get("posts"):
            return None
        got = gemini.generate_json("Facts (JSON):\n" + json.dumps(f, ensure_ascii=False), RESULT, system=SYSTEM,
                                   kind="report_ai", temperature=0.3, max_tokens=1200, timeout=40, think=0)
    except Exception as exc:
        print("reportai: campaign %s: %s" % (k["id"], repr(exc)[:160]), flush=True)
        return None
    return _clean(got)


# ------------------------------------------------------------------- store --

def row(cid, period):
    init()
    with db.connect() as conn:
        return conn.execute("SELECT * FROM campaign_reports WHERE campaign_id = ? AND period = ?", (cid, period)).fetchone()


def _shape(r):
    if r is None:
        return None
    return {"id": r["id"], "period": r["period"], "label": label(r["period"]), "status": r["status"],
            "draft": json.loads(r["draft"]) if r["draft"] else None, "body": json.loads(r["body"]) if r["body"] else None,
            "tries": r["tries"], "tries_left": max(0, MAX_TRIES - r["tries"]), "at": r["updated_at"],
            "approved_by": r["approved_by"] or "", "approved_at": r["approved_at"]}


def label(period):
    if period == "final":
        return "Final report"
    if period.startswith("w") and period[1:].isdigit():
        return "Week %s report" % period[1:]
    return "Weekly report"


def draft(k, period, final=False, notify=True):
    """Make the period's first draft if there is none. Returns the row's data or None."""
    init()
    if row(k["id"], period) is not None:
        return None
    d = write(k, final)
    if d is None:
        return None
    now = db.now()
    with db.connect() as conn:
        cur = conn.execute("INSERT OR IGNORE INTO campaign_reports (campaign_id, period, draft, created_at, updated_at) "
                           "VALUES (?,?,?,?,?)", (k["id"], period, json.dumps(d, ensure_ascii=False), now, now))
        if not cur.rowcount:
            return None
    if notify:
        _tell_kam(k, period)
    return _shape(row(k["id"], period))


def _tell_kam(k, period):
    try:
        import board
        import inbox
        import portal
        kam = board.kam_for(k)
        u = portal.user_by_email(kam) if kam else None
        if u is not None and u["status"] == "active":
            inbox.emit([u["id"]], "team_report", "%s draft ready to approve:" % label(period), rest=" " + k["name"],
                       body="Read it, edit if needed, then approve to show it to the client.",
                       href="campaign/#t=%s&edit=report" % k["token"], ref="rep:%d:%s" % (k["id"], period), once=True)
    except Exception:
        pass


def redo(k, period, final=None):
    """A fresh draft for a period still in draft (KAM's button). (code, payload)."""
    r = row(k["id"], period)
    if r is None:
        return 404, {"ok": False, "message": "No draft for that period yet."}
    if r["status"] == "approved":
        return 400, {"ok": False, "message": "Already approved. The client has seen it."}
    if r["tries"] >= MAX_TRIES:
        return 400, {"ok": False, "message": "That was the last fresh draft for this period. Edit this one instead."}
    import aifeatures
    if not aifeatures.allowed("report"):
        return 400, {"ok": False, "message": "The report writer is %s." % (aifeatures.why_not("report") or "off")}
    d = write(k, period == "final" if final is None else final)
    if d is None:
        return 502, {"ok": False, "message": "No new draft came back. Try again in a minute."}
    with db.connect() as conn:
        conn.execute("UPDATE campaign_reports SET draft = ?, status = 'draft', tries = tries + 1, updated_at = ? WHERE id = ?",
                     (json.dumps(d, ensure_ascii=False), db.now(), r["id"]))
    return 200, {"ok": True, "message": "New draft written.", "report": _shape(row(k["id"], period))}


def _from_form(body):
    out = {"summary": " ".join(str(body.get("summary") or "").split())[:LIMITS["summary"]]}
    for f in ("worked", "improve", "next"):
        v = body.get(f) or []
        if isinstance(v, str):
            v = v.splitlines()
        out[f] = [" ".join(str(x).split())[:220] for x in v if str(x).strip()][:LIMITS[f]]
    return out


def approve(k, actor, period, body):
    """Publish the KAM's text to the client. (code, payload)."""
    import history
    import inbox
    r = row(k["id"], period)
    if r is None:
        return 404, {"ok": False, "message": "No draft for that period."}
    text = _from_form(body or {})
    if not text["summary"]:
        return 400, {"ok": False, "message": "Write a summary before approving."}
    if BANNED.search(" ".join([text["summary"]] + text["worked"] + text["improve"] + text["next"])):
        return 400, {"ok": False, "message": "Take out prices, costs or scores first. Clients never see them."}
    now = db.now()
    history.set_actor(actor)
    with history.tracked("campaign", k["id"], "Approved the %s" % label(period).lower()):
        with db.connect() as conn:
            conn.execute("UPDATE campaign_reports SET body = ?, status = 'approved', approved_by = ?, approved_at = ?, updated_at = ? "
                         "WHERE id = ?", (json.dumps(text, ensure_ascii=False), actor or "", now, now, r["id"]))
    if k["code_id"]:
        final = period == "final"
        inbox.emit(inbox.for_codes([k["code_id"]]), "camp_final" if final else "camp_report",
                   ("Final report ready: " if final else "New summary from HelloVoice: ") + k["name"],
                   body=text["summary"][:280], href="campaign/#t=" + k["token"], ref="repok:%d:%s" % (k["id"], period), once=True)
    return 200, {"ok": True, "message": "Approved. The client can see it now.", "report": _shape(row(k["id"], period))}


def dismiss(k, actor, period):
    r = row(k["id"], period)
    if r is None or r["status"] == "approved":
        return 400, {"ok": False, "message": "Nothing to dismiss."}
    with db.connect() as conn:
        conn.execute("UPDATE campaign_reports SET status = 'dismissed', updated_at = ? WHERE id = ?", (db.now(), r["id"]))
    return 200, {"ok": True, "message": "Dismissed. The client will not see this one."}


def make_now(k):
    """The KAM's "Write a draft now" when the weekly job has not made one yet (needs posts). (code, payload)."""
    import aifeatures
    import weekly
    if not aifeatures.allowed("report"):
        return 400, {"ok": False, "message": "The report writer is %s." % (aifeatures.why_not("report") or "off")}
    final = weekly.ended(k)
    period = "final" if final else _period(k, weekly.week_key(k) or "1")
    if row(k["id"], period) is not None:
        return 400, {"ok": False, "message": "This period already has a draft."}
    got = draft(k, period, final=final, notify=False)
    if got is None:
        return 400, {"ok": False, "message": "Not enough results yet to write a report (no posts live)."}
    return 200, {"ok": True, "message": "Draft written.", "report": got}


# ------------------------------------------------------------------- views --

def team_view(k):
    """For the Edit mode's Report tab: every period, newest first, and whether the writer is on."""
    import aifeatures
    init()
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM campaign_reports WHERE campaign_id = ? ORDER BY created_at DESC", (k["id"],)).fetchall()
    return {"reports": [_shape(r) for r in rows], "on": aifeatures.allowed("report"), "why_not": aifeatures.why_not("report")}


def client_view(k):
    """The newest approved report (the final one wins), as approved. None when there is none."""
    init()
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM campaign_reports WHERE campaign_id = ? AND status = 'approved' "
                         "ORDER BY (period = 'final') DESC, approved_at DESC LIMIT 1", (k["id"],)).fetchone()
    if r is None:
        return None
    s = _shape(r)
    return {"label": s["label"], "at": s["approved_at"], "summary": s["body"]["summary"], "worked": s["body"]["worked"],
            "improve": s["body"]["improve"], "next": s["body"]["next"]}


def waiting(scope_ok):
    """Drafts waiting for approval, for "Needs you". ``scope_ok(campaign_row)`` decides who sees which."""
    init()
    out = []
    with db.connect() as conn:
        for r in conn.execute("SELECT r.id, r.period, r.created_at, k.id cid, k.name, k.token, k.code_id FROM campaign_reports r "
                              "JOIN campaigns k ON k.id = r.campaign_id WHERE r.status = 'draft' ORDER BY r.created_at"):
            if scope_ok(r):
                out.append({"id": r["id"], "title": label(r["period"]) + " · " + r["name"], "sub": "Draft written by Helvi",
                            "at": r["created_at"], "token": r["token"], "act": "report"})
    return out


# -------------------------------------------------------------------- job --

def on_week(k, week):
    """Called by weekly.weekly right after a week's bell was sent."""
    try:
        draft(k, _period(k, week))
    except Exception as exc:
        print("reportai: week draft %s: %s" % (k["id"], repr(exc)[:160]), flush=True)


def on_end(k):
    try:
        draft(k, "final", final=True)
    except Exception as exc:
        print("reportai: final draft %s: %s" % (k["id"], repr(exc)[:160]), flush=True)
