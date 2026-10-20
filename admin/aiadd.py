"""Item 178: "Add creators with AI" on a selection page.

The same machinery as the catalogue's "Build a shortlist with AI" card (matcher.to_brief,
matcher.rank, the power-ups' 60/40 blend inside matcher.apply_rules), pointed at one
selection: it skips the creators already in it, finds N more, and returns them as a preview
the person ticks before anything is added. No second engine.

Rules (Bido, MCQ 2026-10-20):
* The selection's own brief is the starting point; without one the wizard asks it first and
  it is saved to the selection (like "Score this selection" does).
* Any N (1 to MAX_N). Creators already in the selection are never suggested.
* Same credit price as the AI shortlist (portal "brief", or "search" when the AI is off).
* Why-chips in words only. No scores, no shares, no roster size reach the page: the numbers
  stay on the server (gating.py; selection scores are paused anyway).

    preview(sel, answers, n)               -> (picks, brief)   picks: [{code, chips}]
    why_words(item, brief, creator_row)    -> ["Pharmacist", "Women 25–34", ...]
    save_run / run / mark_added            the audit row per search, and the add check
"""
import json
import re

import db
import gating
import matcher
import metrics

MAX_N = 50
DEFAULT_N = 8

SCHEMA = """
CREATE TABLE IF NOT EXISTS selection_aiadd (
    id INTEGER PRIMARY KEY,
    selection_id INTEGER NOT NULL,
    code_id INTEGER,
    answers TEXT NOT NULL,        -- JSON answers the search ran with
    asked INTEGER NOT NULL,       -- N
    picks TEXT NOT NULL,          -- JSON [codes] shown in the preview, best first
    added TEXT,                   -- JSON [codes] the person ticked and added
    cost INTEGER NOT NULL DEFAULT 0,
    at INTEGER NOT NULL,
    added_at INTEGER
);
"""
_ready = set()


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)
    _ready.add(str(db.DB_PATH))


def _ensure():
    if str(db.DB_PATH) not in _ready:
        init()


def clamp_n(v, default=DEFAULT_N):
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, MAX_N))


def brief_count(answers):
    """The number of creators the stored brief asked for, as a starting N."""
    c = (answers or {}).get("count")
    if isinstance(c, int):
        return clamp_n(c)
    if isinstance(c, str):
        if c in matcher.COUNT_OF:
            return clamp_n(matcher.COUNT_OF[c])
        if c.startswith(matcher.OTHER):
            got = matcher._from_other("count", c[len(matcher.OTHER):])
            if got:
                return clamp_n(got)
    return DEFAULT_N


# ------------------------------------------------------------------ the words --

SIZE_WORDS = {"nano": "Nano creator", "micro": "Micro creator", "mid": "Mid-size creator",
              "macro": "Macro creator", "mega": "Mega creator"}
SPACE_WORDS = {"health care": "Healthcare", "food": "Food", "travel": "Travel", "entertainment": "Entertainment",
               "e-commerce": "E-commerce", "music & art": "Music and art", "home & interior": "Home and interior",
               "technology": "Tech", "finance": "Finance", "fitness": "Fitness"}
_DIGIT = re.compile(r"\d")


def _strength_word(s):
    """A fit strength ("Engagement 4.2%", "Views hold steady…") in words, or None. Anything that
    still carries a figure, or quotes the locked analysis, is dropped."""
    t = " ".join(str(s or "").split())
    low = t.lower()
    if not t:
        return None
    if low.startswith("healthcare professional"):
        return "Healthcare professional"
    if low.startswith("engagement"):
        return "Strong engagement"
    if "typical post reaches" in low:
        return "Strong views per post"
    if low.startswith("views hold steady"):
        return "Steady views"
    if _DIGIT.search(t) or "%" in t or gating._locked_text(t):
        return None
    return t[:40]


def why_words(item, brief, c=None):
    """Up to four short chips, words only, for one pick: the power-up chips first (they say how
    the creator fits what was asked), then the performance strengths, then the product space
    and the creator's size as a floor so every card says something."""
    out = []

    def add(w):
        if w and w not in out:
            out.append(w)
    for w in item.get("chips") or []:
        # The power-up chips are written as words (ages read "25–34", never a share).
        if "%" not in str(w) and "/100" not in str(w):
            add(str(w)[:40])
    hcp_said = any(w in ("Doctor", "Pharmacist", "Dermatology & aesthetics") for w in out)
    for s in item.get("strengths") or []:
        w = _strength_word(s)
        if not (hcp_said and w == "Healthcare professional"):     # "Doctor" already says it
            add(w)
    cats = [x for x in str((brief.get("target") or {}).get("category") or "").split("|") if x and x.lower() != "any"]
    if c is not None and cats and len(out) < 4:
        hit = [x for x in cats if matcher._tagged(c, [x])]
        if hit:
            q = matcher._BY_ID["category"]
            label = SPACE_WORDS.get(hit[0]) or dict(q["options"]).get(hit[0], hit[0])
            add("Posts about " + label[:1].lower() + label[1:])
    if len(out) < 2:
        add(SIZE_WORDS.get(item.get("band") or (metrics.band_of(c["followers"]) if c is not None else None)))
    return out[:4]


# ------------------------------------------------------------------ the search --

def inside(sel):
    return set(json.loads(sel["codes"] or "[]"))


def preview(sel, answers, n):
    """N creators for ``sel`` from ``answers`` (the brief, power-ups included), none of them
    already in it. Returns ``(picks, brief)``; picks are the matcher's items, best first."""
    brief = matcher.to_brief(answers)
    brief["count"] = clamp_n(n)
    # The brief's budget cut is for a whole shortlist; adding to a selection asks only for N.
    brief["budget_max"] = None
    result = matcher.rank(brief, exclude=inside(sel))
    return result["picks"], brief


def card_pick(item, brief, c=None):
    """What the preview may show of one pick: its code and why-chips. Nothing numeric."""
    return {"code": item["code"], "chips": why_words(item, brief, c)}


# ------------------------------------------------------------------ the record --

def save_run(sel_id, code_id, answers, n, codes, cost):
    _ensure()
    with db.connect() as conn:
        cur = conn.execute("INSERT INTO selection_aiadd (selection_id, code_id, answers, asked, picks, cost, at) VALUES (?,?,?,?,?,?,?)",
                           (sel_id, code_id, json.dumps(answers), int(n), json.dumps(list(codes)), int(cost or 0), db.now()))
        return cur.lastrowid


def run(run_id):
    _ensure()
    with db.connect() as conn:
        return conn.execute("SELECT * FROM selection_aiadd WHERE id = ?", (run_id,)).fetchone()


def to_add(row, sel, codes):
    """The ticked codes that may be added: shown in this run's preview, not in the selection yet,
    in the preview's order."""
    shown = json.loads(row["picks"] or "[]")
    want = {str(c).strip().upper() for c in (codes or []) if isinstance(c, str)}
    have = inside(sel)
    return [c for c in shown if c in want and c not in have]


def mark_added(run_id, codes):
    _ensure()
    with db.connect() as conn:
        r = conn.execute("SELECT added FROM selection_aiadd WHERE id = ?", (run_id,)).fetchone()
        before = json.loads(r["added"] or "[]") if r else []
        conn.execute("UPDATE selection_aiadd SET added = ?, added_at = ? WHERE id = ?",
                     (json.dumps(before + [c for c in codes if c not in before]), db.now(), run_id))
