"""AI on a selection (HELVi Connect, phase D): "Creators like this".

"Add more like these" (more(), /api/selection/more) was retired on 2026-10-20 for item 178,
"Add creators with AI" (aiadd.py). Its table selection_more stays for the history it holds.

It stands on what already exists: discover.like() (who a creator resembles: topics,
size, place, platforms and, where both are measured, audience) and the matcher's
scoring against the selection's own brief. Nothing here decides prices or reads a
creator's fee, and the reasons quote only what a client already sees on a card
(size, city, platforms, interests), never locked analysis figures.

    alike(sel, code, again)                            three creators like one card (kept, so reopening is free)

Costs (portal.costs): alike 2; free during an active campaign (portal.charge).
"""
import json
import re

import db
import discover


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
