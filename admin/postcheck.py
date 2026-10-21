"""Post checks (item 218 phase 1, 2026-10-21): every captured campaign post is checked against the campaign's
rules and brief, and the account manager is told about the ones that need a look. Clients never see a flag.

Two layers, one result per post (``content_checks``):

    rules (free, always on)    the required disclosure is missing (campaigns.rules.disclosure, as the capture
                               already marks it in content.disclosure_ok); a required #hashtag or @mention is
                               missing; no caption or on-screen text was captured, so nothing could be read.
    AI (switch "compliance")   Gemini reads the caption (a story's sticker / on-screen text arrives as its caption)
                               with the brief's product, main claim and "health claim" answer, and flags wording
                               that over-promises (cure, guarantee, dosage, off-label use, before/after promises,
                               medical advice) or goes against the brief. One small call per post, cached by a hash
                               of the text, so a re-capture of the same caption costs nothing.

Result: ``pass`` | ``warn`` | ``fail`` | ``none`` (nothing to read), with the reasons. A KAM can mark a flagged
post "OK as is"; that sticks until the caption changes. A new ``fail`` rings the KAM's bell once per post
(``team_flag``). A transcript slot (``transcript`` column) is there for spoken words, filled later once a priced
test has been approved; today it stays empty.

The job runs every 10 minutes over posts that have no check yet or whose text changed, at most ``BATCH`` per pass.
"""
import hashlib
import json
import re
import threading
import time

import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS content_checks (
    content_id INTEGER PRIMARY KEY REFERENCES content(id) ON DELETE CASCADE,
    campaign_id INTEGER NOT NULL,
    status TEXT NOT NULL,             -- pass | warn | fail | none
    reasons TEXT NOT NULL,            -- JSON list of {kind, level, text}
    text_hash TEXT,                   -- what was read: caption + transcript
    ai INTEGER NOT NULL DEFAULT 0,    -- 1 = the AI layer read it
    transcript TEXT,                  -- spoken words, when captured (not yet)
    checked_at INTEGER NOT NULL,
    cleared_by TEXT,                  -- "OK as is" by a KAM
    cleared_at INTEGER,
    told_at INTEGER                   -- the KAM's bell, once
);
CREATE INDEX IF NOT EXISTS content_checks_campaign ON content_checks(campaign_id, status);
"""
BATCH = 40
INTERVAL = 600
LEVEL = {"pass": 0, "none": 0, "warn": 1, "fail": 2}

RESULT = {"type": "OBJECT", "properties": {
    "risk": {"type": "STRING", "enum": ["none", "low", "high"]},
    "issues": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "kind": {"type": "STRING", "enum": ["claim", "brief", "tone", "other"]},
        "quote": {"type": "STRING"}, "why": {"type": "STRING"}}, "required": ["kind", "why"]}}},
    "required": ["risk", "issues"]}

SYSTEM = ("You check one sponsored social-media post for a brand, in the Gulf (Saudi Arabia, UAE). Read the caption "
          "(English or Arabic). Flag only real problems: health or cosmetic claims that over-promise (cure, treat, "
          "guaranteed results, dosage or medical advice, off-label use, 'doctor approved' without basis, before/after "
          "promises), wording against the brief, or offensive tone. risk 'high' = a regulator or the brand would object; "
          "'low' = worth a look; 'none' = fine. Quote the exact words. Write each 'why' in one short English sentence.")

_ready = False
_started = False


def init():
    global _ready
    if _ready:
        return
    with db.connect() as conn:
        conn.executescript(SCHEMA)
    _ready = True


def _hash(*parts):
    return hashlib.sha1("\n".join(p or "" for p in parts).encode("utf-8")).hexdigest()[:16]


def _tags(text):
    low = (text or "").lower()
    tags = set(re.findall(r"[#@][\w؀-ۿ.]+", low))
    return tags | {t.rstrip(".") for t in tags}


def rules_check(k, item):
    """The free part: a list of reasons, from the campaign's own rules."""
    rules = db.rules_of(k)
    text = item["caption"] or ""
    out = []
    if not text.strip():
        return [{"kind": "text", "level": "none", "text": "No caption or on-screen text was captured, so nothing could be checked."}]
    if item["disclosure_ok"] == 0:
        out.append({"kind": "disclosure", "level": "fail",
                    "text": "Required disclosure missing (%s)." % " ".join(rules["disclosure"][:3])})
    tags = _tags(text)
    miss = [t for t in rules["hashtags"] + rules["mentions"] if t.lower() not in tags]
    if miss and item["section"] == "campaign":
        out.append({"kind": "tags", "level": "warn", "text": "Missing %s." % ", ".join(miss[:4])})
    return out


def _brief(k):
    try:
        import cbrief
        a = (cbrief._stored(k).get("answers") or {})
        if not a and k["selection_id"]:
            with db.connect() as conn:
                s = conn.execute("SELECT * FROM selections WHERE id = ?", (k["selection_id"],)).fetchone()
            a = cbrief.seed([s]) if s is not None else {}
    except Exception:
        a = {}
    return {key: a.get(key) for key in ("product", "claim", "regulated", "tone", "category") if a.get(key)}


def ai_check(k, item, transcript=None):
    """The paid part: a list of reasons, or None when the AI did not run."""
    import aifeatures
    import gemini
    if not aifeatures.allowed("compliance"):
        return None
    prompt = {"brand": k["client"] or k["name"], "brief": _brief(k), "platform": item["platform"], "kind": item["kind"],
              "caption": (item["caption"] or "")[:2500]}
    if transcript:
        prompt["spoken"] = transcript[:3000]
    try:
        got = gemini.generate_json("Post (JSON):\n" + json.dumps(prompt, ensure_ascii=False), RESULT, system=SYSTEM,
                                   kind="post_check", temperature=0.1, max_tokens=700, timeout=30, think=0)
    except Exception as exc:
        print("postcheck: post %s: %s" % (item["id"], repr(exc)[:160]), flush=True)
        return None
    risk = got.get("risk") if isinstance(got, dict) else None
    if risk not in ("low", "high"):
        return []
    out = []
    for i in (got.get("issues") or [])[:3]:
        why = " ".join(str(i.get("why") or "").split())[:200]
        quote = " ".join(str(i.get("quote") or "").split())[:120]
        if why:
            out.append({"kind": i.get("kind") or "other", "level": "fail" if risk == "high" else "warn",
                        "text": why + (' ("%s")' % quote if quote else "")})
    return out


def _status(reasons):
    if not reasons:
        return "pass"
    if all(r["level"] == "none" for r in reasons):
        return "none"
    return max((r["level"] for r in reasons if r["level"] != "none"), key=lambda lv: LEVEL[lv])


def check(item, k=None, force=False):
    """Check one post (a content row). Returns the stored result as a dict."""
    init()
    k = k or db.campaign(item["campaign_id"])
    with db.connect() as conn:
        old = conn.execute("SELECT * FROM content_checks WHERE content_id = ?", (item["id"],)).fetchone()
    transcript = old["transcript"] if old is not None else None
    h = _hash(item["caption"], transcript, str(item["disclosure_ok"]), item["section"], k["rules"] or "")
    import aifeatures
    want_ai = aifeatures.allowed("compliance") and bool((item["caption"] or "").strip())
    if old is not None and old["text_hash"] == h and not force and (old["ai"] or not want_ai):
        return _shape(old)
    reasons = rules_check(k, item)
    ai = None
    if want_ai and not any(r["level"] == "none" for r in reasons):
        ai = ai_check(k, item, transcript)
        reasons += ai or []
    status = _status(reasons)
    same_text = old is not None and old["text_hash"] == h
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO content_checks (content_id, campaign_id, status, reasons, text_hash, ai, transcript, checked_at, cleared_by, cleared_at, told_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(content_id) DO UPDATE SET status = excluded.status, reasons = excluded.reasons, "
            "text_hash = excluded.text_hash, ai = excluded.ai, checked_at = excluded.checked_at, "
            "cleared_by = excluded.cleared_by, cleared_at = excluded.cleared_at, told_at = excluded.told_at",
            (item["id"], item["campaign_id"], status, json.dumps(reasons, ensure_ascii=False), h, 1 if ai is not None else 0,
             transcript, db.now(),
             old["cleared_by"] if same_text else None, old["cleared_at"] if same_text else None,
             old["told_at"] if same_text else None))
        row = conn.execute("SELECT * FROM content_checks WHERE content_id = ?", (item["id"],)).fetchone()
    if status == "fail" and not row["told_at"] and not row["cleared_at"]:
        _tell_kam(k, item, reasons)
    return _shape(row)


def _shape(r):
    if r is None:
        return None
    return {"status": "ok" if r["cleared_at"] else r["status"], "raw": r["status"], "reasons": json.loads(r["reasons"] or "[]"),
            "ai": bool(r["ai"]), "at": r["checked_at"], "cleared_by": r["cleared_by"] or "", "cleared_at": r["cleared_at"]}


def _tell_kam(k, item, reasons):
    try:
        import board
        import inbox
        import portal
        kam = board.kam_for(k)
        u = portal.user_by_email(kam) if kam else None
        if u is not None and u["status"] == "active":
            first = next((r["text"] for r in reasons if r["level"] == "fail"), "")
            inbox.emit([u["id"]], "team_flag", "A post needs a look:", rest=" " + k["name"], body=first[:280],
                       href="campaign/#t=%s&edit=checks" % k["token"], ref="flag:%d" % item["id"], once=True)
        with db.connect() as conn:
            conn.execute("UPDATE content_checks SET told_at = ? WHERE content_id = ?", (db.now(), item["id"]))
    except Exception:
        pass


def clear(k, actor, content_id, undo=False):
    """A KAM marks a flagged post "OK as is" (or takes that back). (code, payload)."""
    import history
    init()
    item = db.content_item(int(content_id)) if str(content_id or "").isdigit() else None
    if item is None or item["campaign_id"] != k["id"]:
        return 404, {"ok": False, "message": "That post is gone."}
    history.set_actor(actor)
    with history.tracked("campaign", k["id"], "Reviewed a post check"):
        with db.connect() as conn:
            conn.execute("UPDATE content_checks SET cleared_by = ?, cleared_at = ? WHERE content_id = ?",
                         (None if undo else (actor or ""), None if undo else db.now(), item["id"]))
    return 200, {"ok": True, "message": "Flag back on." if undo else "Marked OK. The flag is gone."}


def recheck(k, content_id):
    item = db.content_item(int(content_id)) if str(content_id or "").isdigit() else None
    if item is None or item["campaign_id"] != k["id"]:
        return 404, {"ok": False, "message": "That post is gone."}
    return 200, {"ok": True, "message": "Checked again.", "check": check(item, k, force=True)}


# ------------------------------------------------------------------- views --

def of_campaign(cid):
    """{content_id: result} for one campaign (the Edit mode's Content and Checks tabs)."""
    init()
    with db.connect() as conn:
        return {r["content_id"]: _shape(r) for r in conn.execute("SELECT * FROM content_checks WHERE campaign_id = ?", (cid,))}


def counts(cid):
    out = {"pass": 0, "warn": 0, "fail": 0, "none": 0, "ok": 0, "unchecked": 0}
    checks = of_campaign(cid)
    for p in db.campaign_content(cid, include_hidden=False):
        c = checks.get(p["id"])
        out[c["status"] if c else "unchecked"] += 1
    return out


def flagged(scope_ok):
    """Posts failing a check and not cleared, for "Needs you": one row per campaign."""
    init()
    out = []
    with db.connect() as conn:
        for r in conn.execute("SELECT k.id cid, k.name, k.token, k.code_id, COUNT(*) n, MIN(x.checked_at) at FROM content_checks x "
                              "JOIN content c ON c.id = x.content_id AND c.hidden = 0 JOIN campaigns k ON k.id = x.campaign_id "
                              "WHERE x.status = 'fail' AND x.cleared_at IS NULL GROUP BY k.id ORDER BY at"):
            if scope_ok(r):
                out.append({"id": r["cid"], "title": "%d post%s flagged · %s" % (r["n"], "" if r["n"] == 1 else "s", r["name"]),
                            "sub": "Disclosure, missing tags or claim wording", "at": r["at"], "token": r["token"], "n": r["n"],
                            "act": "checks"})
    return out


# -------------------------------------------------------------------- job --

def pending(limit=BATCH):
    """Posts of live (or recently ended) campaigns with no check yet, or whose text changed since."""
    init()
    since = db.now() - 30 * 86400
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT c.* FROM content c JOIN campaigns k ON k.id = c.campaign_id LEFT JOIN content_checks x ON x.content_id = c.id "
            "WHERE c.hidden = 0 AND k.status <> 'draft' AND (k.status = 'live' OR COALESCE(k.ends_at, 0) >= ?) "
            "ORDER BY x.content_id IS NOT NULL, c.created_at DESC LIMIT ?", (since, limit * 5)).fetchall()
    return rows


def tick():
    init()
    import aifeatures
    want_ai = aifeatures.allowed("compliance")
    done = 0
    camps = {}
    with db.connect() as conn:
        checked = {r["content_id"]: r for r in conn.execute("SELECT content_id, text_hash, ai FROM content_checks")}
    for item in pending():
        if done >= BATCH:
            break
        k = camps.get(item["campaign_id"]) or db.campaign(item["campaign_id"])
        camps[item["campaign_id"]] = k
        old = checked.get(item["id"])
        if old is not None:
            h = _hash(item["caption"], None, str(item["disclosure_ok"]), item["section"], k["rules"] or "")
            if old["text_hash"] == h and (old["ai"] or not want_ai or not (item["caption"] or "").strip()):
                continue
        try:
            check(item, k)
            done += 1
        except Exception as exc:
            print("postcheck: %s %s" % (item["id"], repr(exc)[:160]), flush=True)
    return done


def _loop():
    time.sleep(90)
    while True:
        try:
            tick()
        except Exception as ex:
            print("postcheck:", type(ex).__name__, ex, flush=True)
        time.sleep(INTERVAL)


def start():
    global _started
    if _started:
        return
    _started = True
    init()
    threading.Thread(target=_loop, name="post-checks", daemon=True).start()
