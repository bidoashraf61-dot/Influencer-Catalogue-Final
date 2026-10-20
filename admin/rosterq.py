"""Roster quality (items 224-225, Bido 2026-10-21): creators that do not belong on the roster, and
duplicates the profile-link key misses.

Out of scope is decided by EVIDENCE on the record, never by a name, ethnicity or nationality:
  audience_out    the audience in our markets is under HARD % on every platform with audience data, or
                  under CUT % with a second piece of evidence (fake followers SECOND_FAKE %+, engagement
                  under LOW_ER %, content in neither Arabic nor English) (markets = KSA + UAE + Egypt; GCC = Kuwait, Qatar, Bahrain, Oman counts toward the
                  share but is reported apart, so the number is known)
  fake_followers  every platform with a fake-follower figure is at or above FAKE %
  placeholder     a handle that names nobody (user123456, digits only, under 3 letters) with no local
                  audience to show it is a real local creator, no followers,
                  or no analysis and no source on record, or zero posts on every stored profile check
  language        the content languages are known and include neither Arabic nor English
Unclear (no audience data, or a share just over the cut) goes to a Gemini flash-lite read, which gives
in / out / unsure and one line of reason. Nothing is archived here without a person's click: the
admin queue (Roster > Out of scope) calls archive(), which hides the creator (active = 0) with the
reason in the note, one History entry each, so each one can be undone. A creator on a live selection
or a campaign is never archived by this module.
"""
import json
import re
import time

CORE = {"SA": "Saudi Arabia", "AE": "UAE", "EG": "Egypt"}
GCC = {"KW": "Kuwait", "QA": "Qatar", "BH": "Bahrain", "OM": "Oman"}
HARD = 10.0                     # % of audience in CORE + GCC under which the audience alone is enough
CUT = 25.0                      # from HARD to CUT a second piece of evidence is needed (Bido, 2026-10-21)
SECOND_FAKE = 35.0              # second evidence: fake followers at or above this on every platform,
LOW_ER, LOW_ER_FOLLOWERS = 0.3, 10000   # or engagement under LOW_ER % with over LOW_ER_FOLLOWERS followers,
                                        # or content in neither Arabic nor English
BIG = 500000                    # a big creator in the HARD-CUT band is never pre-ticked for archive
UNCLEAR_TO = 35.0               # a share from CUT up to this is close enough to ask the AI
FAKE = 50.0
LANGS_OK = {"arabic", "english"}
LANGS_UNKNOWN = {"unknown", "non-arabic", "none", ""}

REASONS = {
    "audience_out": "Audience outside our markets",
    "fake_followers": "Fake followers 50%+",
    "placeholder": "Placeholder or dead profile",
    "language": "Content not in Arabic or English",
    "ai_out": "AI read: outside our markets",
}

_PLACEHOLDER = (re.compile(r"user\d{5,}"), re.compile(r"[\d._]+"))


# ------------------------------------------------------------------ evidence --

def market_mix(analyses):
    """{"core", "gcc", "share", "top", "has"} from the best platform (the one with most audience in
    our markets): a creator whose TikTok is Saudi and Instagram is not is still in scope."""
    best = None
    for d in (analyses or {}).values():
        countries = ((d or {}).get("audience") or {}).get("countries") or []
        if not countries:
            continue
        core = sum(float(c.get("pct") or 0) for c in countries if c.get("code") in CORE)
        gcc = sum(float(c.get("pct") or 0) for c in countries if c.get("code") in GCC)
        top = [(c.get("code") or "", c.get("name") or "", round(float(c.get("pct") or 0), 1)) for c in countries[:3]]
        cand = {"core": round(core, 1), "gcc": round(gcc, 1), "share": round(core + gcc, 1), "top": top, "has": True}
        if best is None or cand["share"] > best["share"]:
            best = cand
    return best or {"core": None, "gcc": None, "share": None, "top": [], "has": False}


def languages(analyses):
    out = set()
    for d in (analyses or {}).values():
        for lang in (d or {}).get("content_languages") or []:
            out.add(str(lang).strip())
    return sorted(out)


def assess(creator, analyses, posts=None):
    """{"reasons": [{"key", "label", "detail"}], "mix", "langs", "unclear"} for one creator.

    ``creator`` is a creators row (or dict), ``analyses`` {platform: analysis data}, ``posts`` the
    post counts the profile checks stored for it (None when never checked)."""
    c = dict(creator)
    mix = market_mix(analyses)
    langs = languages(analyses)
    reasons = []
    fakes = [float(d.get("fake_followers_pct")) for d in (analyses or {}).values()
             if d and d.get("fake_followers_pct") is not None]
    ers = [(float(d.get("er")), d.get("followers") or 0) for d in (analyses or {}).values()
           if d and d.get("er") is not None]
    known = [x for x in langs if x.lower() not in LANGS_UNKNOWN]
    foreign = bool(known) and not any(x.lower() in LANGS_OK for x in known)
    second = []
    if fakes and min(fakes) >= SECOND_FAKE:
        second.append("fake followers %s%%" % round(min(fakes)))
    if ers and all(e < LOW_ER and f > LOW_ER_FOLLOWERS for e, f in ers):
        second.append("engagement %s%%" % round(min(e for e, _ in ers), 2))
    if foreign:
        second.append("content in " + ", ".join(known))
    if mix["has"] and (mix["share"] < HARD or (mix["share"] < CUT and second)):
        top = ", ".join("%s %s%%" % (n or code, p) for code, n, p in mix["top"])
        reasons.append(("audience_out", "%s%% in KSA/UAE/Egypt + %s%% GCC; top: %s%s" % (
            mix["core"], mix["gcc"], top, ("; with " + ", ".join(second)) if mix["share"] >= HARD else "")))
    if fakes and min(fakes) >= FAKE:
        reasons.append(("fake_followers", "fake followers %s%%" % round(min(fakes))))
    handle = (c.get("handle") or "").strip().lstrip("@").lower()
    why = []
    in_market = mix["has"] and mix["share"] >= CUT
    # An un-renamed TikTok handle (user123...) on an account with a local audience is a real creator
    # (2026-10-21 dry run: 550k followers, 69% Saudi): the handle alone is not evidence.
    if (not handle or len(handle) < 3 or any(p.fullmatch(handle) for p in _PLACEHOLDER)) and not in_market:
        why.append("handle '%s' names nobody" % handle if handle else "no handle")
    if not c.get("followers"):
        why.append("no followers on record")
    if not analyses and not (c.get("note") or "").strip():
        why.append("no analysis and no source on record")
    if posts and all(p == 0 for p in posts):
        why.append("0 posts on every profile check")
    if why:
        reasons.append(("placeholder", "; ".join(why)))
    if foreign:
        reasons.append(("language", "content in " + ", ".join(known)))
    unclear = not reasons and (not mix["has"] or mix["share"] < UNCLEAR_TO)
    keys = {k for k, _ in reasons}
    # Pre-ticked for the bulk Archive only on strong evidence: fake followers alone, or a big creator
    # who still has HARD %+ of a local audience, waits for a person to tick it.
    preselect = bool(keys - {"fake_followers"}) and not (
        (c.get("followers") or 0) >= BIG and mix["has"] and mix["share"] >= HARD)
    return {"reasons": [{"key": k, "label": REASONS[k], "detail": d} for k, d in reasons],
            "mix": mix, "langs": langs, "unclear": unclear, "preselect": preselect}


# ---------------------------------------------------------------- the scan --

def _protected(conn):
    """Codes on a selection that is not deleted, or on any campaign: never archived from here."""
    out = set()
    for r in conn.execute("SELECT codes FROM selections WHERE deleted_at IS NULL AND archived_at IS NULL"):
        try:
            out |= set(json.loads(r[0] or "[]"))
        except ValueError:
            pass
    out |= {r[0] for r in conn.execute("SELECT code FROM campaign_creators UNION SELECT code FROM content")}
    return out


def _posts(conn):
    import sqlite3
    posts = {}
    try:
        for r in conn.execute("SELECT code, platform, posts FROM profile_snapshots WHERE posts IS NOT NULL ORDER BY at"):
            posts.setdefault(r[0], {})[r[1]] = r[2]       # the latest check per platform wins
    except sqlite3.OperationalError:                       # profile checks never run here (apify.init makes the table)
        pass
    return posts


def _analyses_by_code(conn):
    """(code, {platform: data}) one creator at a time, so the whole analysis table (hundreds of MB
    of JSON) is never in memory at once: the admin container is capped at 1 GB."""
    code, group = None, {}
    for r in conn.execute("SELECT code, platform, data FROM creator_analysis ORDER BY code"):
        if r[0] != code:
            if code is not None:
                yield code, group
            code, group = r[0], {}
        try:
            group[r[1]] = json.loads(r[2] or "{}")
        except ValueError:
            pass
    if code is not None:
        yield code, group


def scan(conn):
    """Every active creator that has a reason or is unclear: [{"code", "reasons", "mix", "langs",
    "unclear", "preselect", "protected"}]. Reads only; run it off the request path (~1 minute)."""
    creators = {r["code"]: r for r in conn.execute("SELECT * FROM creators WHERE active = 1")}
    posts = _posts(conn)
    prot = _protected(conn)
    out, seen = [], set()

    def one(code, an):
        p = posts.get(code)
        a = assess(creators[code], an, list(p.values()) if p else None)
        if a["reasons"] or a["unclear"]:
            a["code"] = code
            a["protected"] = code in prot
            out.append(a)

    for code, an in _analyses_by_code(conn):
        if code in creators:
            seen.add(code)
            one(code, an)
    for code in creators:
        if code not in seen:
            one(code, {})
    return out


def summary(results):
    """Counts per reason (a creator with two reasons is in both), plus unclear, protected, GCC-led."""
    out = {k: 0 for k in REASONS}
    out.update({"flagged": 0, "unclear": 0, "protected": 0, "gcc_led": 0})
    for r in results:
        for x in r["reasons"]:
            out[x["key"]] += 1
        out["flagged"] += 1 if r["reasons"] else 0
        out["unclear"] += 1 if r["unclear"] else 0
        out["protected"] += 1 if r["protected"] and r["reasons"] else 0
        m = r["mix"]
        out["gcc_led"] += 1 if m["has"] and m["gcc"] and m["gcc"] > m["core"] else 0
    return out


# ------------------------------------------------------------- the queue --

def init(conn=None):
    import db
    if conn is None:
        with db.connect() as own:
            return init(own)
    conn.execute("""CREATE TABLE IF NOT EXISTS roster_flags (
      code       TEXT PRIMARY KEY,
      reasons    TEXT NOT NULL,          -- JSON [{key, label, detail}]
      mix        TEXT,                   -- JSON market_mix()
      langs      TEXT,
      unclear    INTEGER NOT NULL DEFAULT 0,
      preselect  INTEGER NOT NULL DEFAULT 0,   -- ticked by default for the bulk Archive
      ai_verdict TEXT,                   -- in | out | unsure
      ai_reason  TEXT,
      ai_at      INTEGER,
      status     TEXT NOT NULL DEFAULT 'open',   -- open | kept | archived
      decided_by TEXT,
      decided_at INTEGER,
      scanned_at INTEGER NOT NULL)""")


def save_scan(results, conn=None):
    """Write a scan to the queue. A creator someone chose to keep stays kept unless a new reason
    appears; one no longer flagged leaves the queue; the AI's earlier read is kept."""
    import db
    if conn is None:
        with db.connect() as own:
            return save_scan(results, own)
    init(conn)
    now = int(time.time())
    seen = set()
    for r in results:
        seen.add(r["code"])
        keys = sorted(x["key"] for x in r["reasons"])
        old = conn.execute("SELECT reasons, status FROM roster_flags WHERE code = ?", (r["code"],)).fetchone()
        status = "open"
        if old is not None and old["status"] in ("kept", "archived"):
            was = sorted(x["key"] for x in json.loads(old["reasons"] or "[]"))
            status = old["status"] if set(keys) <= set(was) else "open"
        conn.execute(
            "INSERT INTO roster_flags (code, reasons, mix, langs, unclear, preselect, status, scanned_at) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(code) DO UPDATE SET reasons = excluded.reasons, mix = excluded.mix, langs = excluded.langs, "
            "unclear = excluded.unclear, preselect = excluded.preselect, status = ?, scanned_at = excluded.scanned_at",
            (r["code"], json.dumps(r["reasons"]), json.dumps(r["mix"]), json.dumps(r["langs"]),
             1 if r["unclear"] else 0, 1 if r.get("preselect") else 0, status, now, status))
    gone = [row[0] for row in conn.execute("SELECT code FROM roster_flags WHERE status = 'open'") if row[0] not in seen]
    for code in gone:
        if conn.execute("SELECT ai_verdict FROM roster_flags WHERE code = ?", (code,)).fetchone()[0] != "out":
            conn.execute("DELETE FROM roster_flags WHERE code = ?", (code,))
    return len(results)


def queue(reason=None, status="open", conn=None):
    """Flag rows joined to their creator, for the admin tab. ``reason`` = a REASONS key, "unclear"
    or None for all."""
    import db
    if conn is None:
        with db.connect() as own:
            return queue(reason, status, own)
    init(conn)
    rows = conn.execute(
        "SELECT f.*, c.name, c.handle, c.platform, c.followers, c.city, c.photo, c.profiles "
        "FROM roster_flags f JOIN creators c ON c.code = f.code WHERE f.status = ? ORDER BY c.followers DESC",
        (status,)).fetchall()
    prot = _protected(conn)
    out = []
    for r in rows:
        d = dict(r)
        d["reasons"] = json.loads(d["reasons"] or "[]")
        if d.get("ai_verdict") == "out" and not any(x["key"] == "ai_out" for x in d["reasons"]):
            d["reasons"].append({"key": "ai_out", "label": REASONS["ai_out"], "detail": d.get("ai_reason") or ""})
        d["mix"] = json.loads(d["mix"] or "null")
        d["protected"] = d["code"] in prot
        keys = {x["key"] for x in d["reasons"]}
        if reason == "unclear":
            if not d["unclear"] or keys:
                continue
        elif reason and reason not in keys:
            continue
        out.append(d)
    return out


def counts(conn=None):
    import db
    if conn is None:
        with db.connect() as own:
            return counts(own)
    out = {k: 0 for k in REASONS}
    out["unclear"] = 0
    for d in queue(conn=conn):
        keys = {x["key"] for x in d["reasons"]}
        for k in keys:
            out[k] += 1
        if not keys and d["unclear"]:
            out["unclear"] += 1
    return out


def archive(codes, who):
    """Hide each creator from the catalogue and every client view, with the reason in the note.
    One History entry per creator (undo restores it). Protected creators are skipped.
    Returns (archived, skipped_protected)."""
    import db, history
    init()
    with db.connect() as conn:
        prot = _protected(conn)
    done, skipped = [], []
    stamp = time.strftime("%Y-%m-%d")
    for code in dict.fromkeys(codes or []):
        c = db.creator(code)
        if c is None or not c["active"]:
            continue
        if code in prot:
            skipped.append(code)
            continue
        with db.connect() as conn:
            f = conn.execute("SELECT reasons, ai_verdict, ai_reason FROM roster_flags WHERE code = ?", (code,)).fetchone()
        labels = [x["label"] for x in json.loads(f["reasons"] or "[]")] if f else []
        if f and f["ai_verdict"] == "out":
            labels.append(REASONS["ai_out"])
        why = "; ".join(labels) or "out of scope"
        row = dict(c)
        row["active"] = 0
        row["note"] = ("[Archived %s, out of scope: %s] " % (stamp, why)) + (c["note"] or "")
        with history.tracked("creator", code, "Archived %s (out of scope: %s)" % (code, why)):
            db.upsert_creator(row)
        with db.connect() as conn:
            conn.execute("UPDATE roster_flags SET status = 'archived', decided_by = ?, decided_at = ? WHERE code = ?",
                         (who, int(time.time()), code))
        done.append(code)
    return done, skipped


def keep(codes, who):
    """In scope after all: off the queue until a new reason appears."""
    import db
    init()
    with db.connect() as conn:
        for code in codes or []:
            conn.execute("UPDATE roster_flags SET status = 'kept', decided_by = ?, decided_at = ? WHERE code = ?",
                         (who, int(time.time()), code))
    return len(codes or [])


# ---------------------------------------------------------------- AI read --

AI_MODEL = "gemini-3.1-flash-lite"
AI_BATCH = 25
AI_SYSTEM = (
    "You check whether social media creators fit a talent roster for brands in Saudi Arabia, the UAE and "
    "Egypt (the wider Gulf counts too). Judge ONLY from the evidence given: where the profile says it is, the "
    "bio, the content languages, the audience countries and the brands worked with. Never judge from a "
    "person's name, looks, ethnicity, religion or nationality. A creator living in the region whose audience "
    "is local is IN even if they are an expat. Answer OUT only when the evidence shows the account serves a "
    "market outside the region, or is not a real creator (a shop, a fan page, a placeholder). If the evidence "
    "is thin, answer UNSURE. Give a reason of at most 15 words naming the evidence.")
AI_SCHEMA = {"type": "OBJECT", "properties": {"items": {"type": "ARRAY", "items": {
    "type": "OBJECT", "properties": {"i": {"type": "INTEGER"}, "verdict": {"type": "STRING", "enum": ["in", "out", "unsure"]},
                                     "reason": {"type": "STRING"}}, "required": ["i", "verdict", "reason"]}}},
    "required": ["items"]}


def evidence(creator, analyses):
    """What the AI may see: no name, no photo."""
    ev = {"platform": creator["platform"], "followers": creator["followers"], "city_on_record": creator["city"]}
    for pl, d in (analyses or {}).items():
        d = d or {}
        loc = d.get("location")
        ev[pl] = {"location": loc.get("name") if isinstance(loc, dict) else loc,
                  "bio": (d.get("bio") or "")[:300], "languages": d.get("content_languages") or [],
                  "audience_top": [(c.get("name"), c.get("pct")) for c in ((d.get("audience") or {}).get("countries") or [])[:4]],
                  "brands": [b.get("name") for b in (d.get("brands") or [])[:6] if isinstance(b, dict)],
                  "interests": (d.get("creator_interests") or [])[:6]}
    return ev


def ai_review(limit=500):
    """Read the unclear creators the AI has not seen yet, AI_BATCH per call. Returns how many were read."""
    import db, gemini
    init()
    if not gemini.configured():
        return 0
    done = 0
    while done < limit:
        with db.connect() as conn:
            rows = conn.execute("SELECT f.code FROM roster_flags f WHERE f.unclear = 1 AND f.ai_verdict IS NULL "
                                "AND f.status = 'open' LIMIT ?", (min(AI_BATCH, limit - done),)).fetchall()
            if not rows:
                break
            batch = []
            for r in rows:
                c = db.creator(r["code"], conn)
                an = {}
                for a in conn.execute("SELECT platform, data FROM creator_analysis WHERE code = ?", (r["code"],)):
                    try:
                        an[a[0]] = json.loads(a[1] or "{}")
                    except ValueError:
                        pass
                batch.append((r["code"], evidence(c, an)))
        prompt = "Creators:\n" + "\n".join("%d. %s" % (n, json.dumps(ev, ensure_ascii=False)) for n, (_, ev) in enumerate(batch))
        try:
            out = gemini.generate_json(prompt, AI_SCHEMA, system=AI_SYSTEM, kind="roster_quality", temperature=0.1,
                                       max_tokens=4096, timeout=60, model_name=AI_MODEL, think=0)
        except Exception as exc:
            print("rosterq: AI read failed:", repr(exc)[:160], flush=True)
            break
        got = {it.get("i"): it for it in (out.get("items") or []) if isinstance(it, dict)}
        now = int(time.time())
        with db.connect() as conn:
            for n, (code, _) in enumerate(batch):
                it = got.get(n) or {"verdict": "unsure", "reason": "no answer"}
                v = it.get("verdict") if it.get("verdict") in ("in", "out", "unsure") else "unsure"
                conn.execute("UPDATE roster_flags SET ai_verdict = ?, ai_reason = ?, ai_at = ? WHERE code = ?",
                             (v, (it.get("reason") or "")[:200], now, code))
        done += len(batch)
    return done


# ------------------------------------------------------------- duplicates --

def _norm_handle(h):
    return re.sub(r"[._\-]", "", (h or "").strip().lower().lstrip("@"))


def _handles(row):
    """{(platform, normalised handle)} from the handle field and every profile link."""
    import db
    out = set()
    first = (row["platform"] or "").split(",")[0].strip().lower()
    if row["handle"]:
        out.add((first, _norm_handle(row["handle"])))
    for p in db.split_profiles(row["profiles"] or ""):
        k = db._profile_key(p.get("url")) or ""
        m = re.search(r"(?:instagram\.com|tiktok\.com|snapchat\.com/add|youtube\.com|x\.com|twitter\.com|facebook\.com)/@?([^/?#]+)", k)
        if m and m.group(1) not in ("profile.php", "p", "reel", "share"):
            out.add(((p.get("platform") or "").strip().lower(), _norm_handle(m.group(1))))
    return {x for x in out if len(x[1]) >= 3}


def dupe_candidates(rows=None, known=None):
    """Pairs the profile-link key misses: [{"kind", "why", "creators": [rows]}].

    kind "same" = the same handle on the same platform written differently (noha.magdi / nohamagdi): a
    duplicate card. kind "cross" = the same handle on different platforms with no platform in common:
    one person with an Instagram card and a TikTok card, to merge into one card that keeps both.
    ``known`` = codes already in db.duplicate_groups(), left out here."""
    import db
    import namematch
    rows = rows if rows is not None else db.list_creators(active_only=True)
    known = known or set()
    by = {}
    for r in rows:
        for pl, h in _handles(r):
            by.setdefault(h, {}).setdefault(r["code"], set()).add(pl)
    out, seen = [], set()
    for h, owners in by.items():
        if len(owners) < 2:
            continue
        codes = sorted(owners)
        key = tuple(codes)
        if key in seen or set(codes) <= known:
            continue
        seen.add(key)
        plats = [owners[c] for c in codes]
        shared = set.intersection(*plats)
        crs = [r for r in rows if r["code"] in owners]
        names = {namematch.norm(r["name"] or "") for r in crs}
        same_name = len(names) == 1
        kind = "same" if shared else "cross"
        why = ("same handle '%s' on %s" % (h, ", ".join(sorted(shared))) if shared
               else "same handle '%s' on %s" % (h, " + ".join(sorted(set().union(*plats)))))
        out.append({"kind": kind, "why": why, "strong": same_name, "creators": crs})
    out.sort(key=lambda g: (g["kind"] != "same", not g["strong"]))
    return out


# ------------------------------------------------------------ background --

import threading as _threading
_lock = _threading.Lock()
JOB = {"kind": None, "started": None, "finished": None, "message": ""}


def running():
    return _lock.locked()


def start(kind, who=""):
    """Run "scan" or "ai" in a background thread, one job at a time (the admin is capped at 1 GB).
    False when one is already running."""
    if not _lock.acquire(blocking=False):
        return False
    JOB.update(kind=kind, started=int(time.time()), finished=None, message="running")

    def work():
        import db
        try:
            if kind == "scan":
                with db.connect() as conn:
                    res = scan(conn)
                save_scan(res)
                s = summary(res)
                db.set_setting("roster_quality_last", {"at": int(time.time()), "by": who, "summary": s})
                JOB["message"] = "%d flagged, %d unclear" % (s["flagged"], s["unclear"])
            elif kind == "ai":
                n = ai_review(limit=int(db.setting("roster_quality_ai_limit", 8000) or 8000))
                JOB["message"] = "%d read by the AI" % n
        except Exception as exc:                              # never take the admin down
            JOB["message"] = "failed: " + repr(exc)[:160]
            print("rosterq:", JOB["message"], flush=True)
        finally:
            JOB["finished"] = int(time.time())
            _lock.release()

    _threading.Thread(target=work, daemon=True, name="roster-quality").start()
    return True
