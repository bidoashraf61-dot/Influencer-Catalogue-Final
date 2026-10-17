"""Find creators from names, handles, profile links or codes (Helvi's find_creators tool).

A pasted list of names rarely matches the roster letter for letter: handles carry @ or a profile
link, Arabic names differ in alef/ya/ta-marbuta spelling and diacritics, English names come with
emoji and "Dr." prefixes. Everything is normalised the same way on both sides, then scored:
code or handle exact, name exact, every word of the query inside the name, else a fuzzy ratio.
"""
import difflib
import json
import re

import db

_TASHKEEL = re.compile("[ً-ْـٰ]")
_NOISE = re.compile(r"[^\w\s]|_", re.UNICODE)
_TITLES = {"dr", "doctor", "د", "دكتور", "دكتوره", "the", "mr", "mrs", "ms"}
_URL = re.compile(r"(?:instagram\.com|tiktok\.com/@?|snapchat\.com/add|youtube\.com/@?|x\.com|twitter\.com)/?@?([A-Za-z0-9._-]+)", re.I)


def norm(text):
    """Lowercase, no emoji/punctuation, Arabic letters unified, titles dropped."""
    t = _TASHKEEL.sub("", str(text or "").lower())
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    t = _NOISE.sub(" ", t)
    words = [w for w in t.split() if w not in _TITLES]
    return " ".join(words)


def handle_of(query):
    """The handle inside a profile link or @handle, else None."""
    q = str(query or "").strip()
    m = _URL.search(q)
    if m:
        return m.group(1).lower().strip("._-")
    if q.startswith("@"):
        return q[1:].strip().lower()
    return None


def _handles(c):
    out = set()
    if c["handle"]:
        out.add(str(c["handle"]).lower().lstrip("@"))
    try:
        for p in json.loads((c["profiles"] if "profiles" in c.keys() else None) or "[]"):
            m = _URL.search(str(p.get("url") or "")) if isinstance(p, dict) else None
            if m:
                out.add(m.group(1).lower())
    except (ValueError, TypeError, AttributeError):
        pass
    return out


def build_index():
    rows = []
    for c in db.list_creators(active_only=True):
        rows.append((c, norm(c["name"]), _handles(c)))
    return rows


def _score(q, qh, qn, c, name_n, handles):
    if str(c["code"]).lower() == q.lower().strip():
        return 1.0
    if qh and qh in handles:
        return 1.0
    if not qn:
        return 0.0
    if qn == name_n:
        return 0.98
    qs, ns = set(qn.split()), set(name_n.split())
    best = difflib.SequenceMatcher(None, qn, name_n).ratio() if name_n else 0.0
    if qs and qs <= ns:
        best = max(best, 0.9 - 0.01 * (len(ns) - len(qs)))        # every word of the query is in the name
    elif ns and ns <= qs and len(ns) >= 2:
        best = max(best, 0.85)
    for h in handles:                                             # a plain name that is really a handle
        best = max(best, difflib.SequenceMatcher(None, qn.replace(" ", ""), h.replace(".", "").replace("_", "")).ratio() * 0.95)
    return best


def find(queries, index=None, per=3):
    """[{query, status: exact|likely|ambiguous|none, matches: [(creator row, score)]}] in input order."""
    index = index or build_index()
    out = []
    for q in queries:
        q = str(q or "").strip()
        if not q:
            continue
        qh, qn = handle_of(q), norm(q)
        scored = sorted(((_score(q, qh, qn, c, n, h), c) for c, n, h in index), key=lambda x: (-x[0], -(x[1]["followers"] or 0)))
        top = [(s, c) for s, c in scored[:per] if s >= 0.72]
        if not top:
            status = "none"
        elif top[0][0] >= 0.98 and (len(top) == 1 or top[1][0] < 0.95):
            status = "exact"
        elif len(top) == 1 or top[0][0] - top[1][0] >= 0.08:
            status = "likely" if top[0][0] >= 0.85 else "ambiguous"
        else:
            status = "ambiguous"
        out.append({"query": q, "status": status, "matches": [(c, round(s, 2)) for s, c in top]})
    return out
