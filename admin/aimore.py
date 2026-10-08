"""AI on a selection (HELVY Connect, phase D): "Add more like these" and "Creators like this".

Both stand on what already exists: discover.like() (who a creator resembles: topics,
size, place, platforms and, where both are measured, audience) and the matcher's
scoring against the selection's own brief. Nothing here decides prices or reads a
creator's fee, and the reasons quote only what a client already sees on a card
(size, city, platforms, interests), never locked analysis figures.

    more(sel, objective, target, note, chips, count)   creators to add, best first, with reasons
    alike(sel, code, again)                            three creators like one card (kept, so reopening is free)

Costs (portal.costs): more 3, alike 2; free during an active campaign (portal.charge).
"""
import json
import re

import db
import discover

QUICK = {  # chip id -> label, as the card shows them
    "doctors": "More doctors",
    "tiktok": "TikTok first",
    "under100k": "Under 100K followers",
    "women2534": "Women 25–34",
}
MAX_COUNT = 10

SCHEMA = """
CREATE TABLE IF NOT EXISTS selection_alike (
    selection_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    picks TEXT NOT NULL,          -- JSON [codes] shown for this card, newest batch last
    at INTEGER NOT NULL,
    PRIMARY KEY (selection_id, code)
);
CREATE TABLE IF NOT EXISTS selection_more (
    id INTEGER PRIMARY KEY,
    selection_id INTEGER NOT NULL,
    code_id INTEGER,
    note TEXT,
    chips TEXT,
    added TEXT NOT NULL,          -- JSON [codes] added to the selection
    at INTEGER NOT NULL
);
"""


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)


def _hcp(c):
    return str((c["tier"] if c is not None else "") or "").upper().startswith("HCP")


def _size(c):
    t = re.sub(r"^hcp\s*-\s*", "", str(c["tier"] or ""), flags=re.I).strip()
    return t or None


def _topics(c):
    return {w.strip().lower() for w in re.split(r"[,/|;]+", str(c["interest"] or "")) if w.strip()}


def _city(c):
    return str(c["city"] or "").split(",")[0].strip()


def _plats(c):
    return {p.strip() for p in str(c["platform"] or "").split(",") if p.strip()}


def reason(pick, seed):
    """Why ``pick`` is like ``seed``, from card fields only."""
    bits = []
    if _hcp(pick) and _hcp(seed):
        bits.append("a healthcare professional like %s" % (seed["name"] or seed["code"]))
    common = sorted(_topics(pick) & _topics(seed))
    if common:
        bits.append("posts about " + ", ".join(common[:2]))
    if _city(pick) and _city(pick).lower() == _city(seed).lower():
        bits.append("based in " + _city(pick))
    if _size(pick) and _size(pick) == _size(seed):
        bits.append("same size (%s)" % _size(pick))
    both = sorted(_plats(pick) & _plats(seed))
    if both and len(bits) < 3:
        bits.append("on " + " and ".join(both[:2]))
    if not bits:
        return "Close to %s in content and audience." % (seed["name"] or seed["code"])
    text = "; ".join(bits[:3])
    return text[:1].upper() + text[1:] + "."


def _seeds(sel):
    import selstatus
    codes = json.loads(sel["codes"] or "[]")
    st = selstatus.of(sel["id"])
    approved = [c for c in codes if (st.get(c) or {}).get("s") == "approved"]
    rejected = {c for c in codes if (st.get(c) or {}).get("s") in ("rejected", "unavailable")}
    seeds = approved or [c for c in codes if c not in rejected]
    return seeds, set(codes), rejected


def _read_note(note):
    """The client's few extra words, read for free: cities and the brief keywords the matcher knows."""
    import matcher
    t = " " + " ".join(str(note or "").lower().split()) + " "
    cities = [city for city, words in discover._CITY_WORDS.items() if any(w in t for w in words)]
    answers, _ = matcher.guess(note or "")
    return cities, answers


def more(sel, objective, target, note="", chips=(), count=5):
    """Creators to add to ``sel``: like its approved creators, fitting its brief and the extra
    words. Returns ``(picks, error)``; picks are ``[{code, why}]``."""
    import matcher
    seeds, inside, rejected = _seeds(sel)
    if not seeds:
        return [], "no_seeds"
    count = max(1, min(int(count or 5), MAX_COUNT))
    chips = [c for c in (chips or []) if c in QUICK]
    roster = {c["code"]: c for c in db.list_creators(active_only=True)}
    like_score, best_seed = {}, {}
    for s in seeds[:12]:
        for rank, code in enumerate(discover.like(s, limit=60)):
            if code in inside or code in rejected or code not in roster:
                continue
            pts = 60 - rank
            like_score[code] = like_score.get(code, 0) + pts
            if pts > best_seed.get(code, (0, None))[0]:
                best_seed[code] = (pts, s)
    if not like_score:
        return [], "none"
    cities, ans = _read_note(note)
    brief_target = dict(target or {})
    if ans.get("market"):
        brief_target["country"] = ans["market"]
    if ans.get("gender"):
        brief_target["gender"] = ans["gender"]
    if ans.get("category"):
        brief_target["category"] = "|".join(ans["category"])
    if "women2534" in chips:
        brief_target["gender"], brief_target["age"] = "Women", "25-34"
    plats = ["TikTok"] if "tiktok" in chips else [p for p in (ans.get("platforms") or []) if p in matcher.PLATFORMS]
    pool = set(like_score)
    if "under100k" in chips:
        pool = {c for c in pool if (roster[c]["followers"] or 0) < 100000}
    if "doctors" in chips:
        docs = {c for c in pool if _hcp(roster[c])}
        pool = docs or pool
    if cities:
        near = {c for c in pool if any(x.lower() in str(roster[c]["city"] or "").lower() for x in cities)}
        pool = near or pool
    try:
        scored = matcher.score_all({"objective": objective, "target": brief_target, "platforms": plats}, exclude=inside | rejected, only=pool)
    except Exception:
        scored = []
    top_like = max(like_score.values()) or 1
    fit_of = {i["code"]: i["rank_score"] for i in scored}
    if plats:
        pool = {c for c in pool if c in fit_of} or pool
    ranked = sorted(pool, key=lambda c: -(0.55 * like_score[c] / top_like + 0.45 * (fit_of.get(c, 40) / 100.0)))
    picks = []
    for code in ranked[:count]:
        seed = roster.get(best_seed.get(code, (0, seeds[0]))[1]) or roster.get(seeds[0])
        picks.append({"code": code, "why": reason(roster[code], seed) if seed is not None else ""})
    return picks, None


def record_more(sel, code_id, note, chips, codes):
    with db.connect() as conn:
        conn.execute("INSERT INTO selection_more (selection_id, code_id, note, chips, added, at) VALUES (?,?,?,?,?,?)",
                     (sel["id"], code_id, " ".join(str(note or "").split())[:200], json.dumps(list(chips or [])), json.dumps(codes), db.now()))


def kept(sel_id, code):
    with db.connect() as conn:
        r = conn.execute("SELECT picks FROM selection_alike WHERE selection_id = ? AND code = ?", (sel_id, code)).fetchone()
    return json.loads(r["picks"]) if r else []


def alike(sel, code, shown=()):
    """Three creators like ``code`` not already in the selection (or shown before)."""
    roster = {c["code"]: c for c in db.list_creators(active_only=True)}
    me = roster.get(code) or db.creator(code)
    if me is None:
        return []
    inside = set(json.loads(sel["codes"] or "[]"))
    out = []
    for c in discover.like(code, limit=48):
        if c in inside or c in shown or c not in roster:
            continue
        out.append({"code": c, "why": reason(roster[c], me)})
        if len(out) == 3:
            break
    return out


def keep(sel_id, code, codes):
    with db.connect() as conn:
        conn.execute("INSERT INTO selection_alike (selection_id, code, picks, at) VALUES (?,?,?,?) "
                     "ON CONFLICT(selection_id, code) DO UPDATE SET picks = excluded.picks, at = excluded.at",
                     (sel_id, code, json.dumps(list(codes)[:30]), db.now()))
