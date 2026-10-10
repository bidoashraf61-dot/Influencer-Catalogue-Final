"""The catalogue's roster, one batch at a time.

The page used to download the whole roster (/api/roster, ~1 MB at 2,300 creators, 6 MB
of JSON at 10,000) and filter, sort and group it in the browser. Here the same work runs
on the server, over an in-memory index built once per roster version (the same version
/api/roster's ETag follows: creators, analyses, tiers, rates and the day's photo
signatures), and the page asks for 48 cards at a time.

  Index      the roster cards (the exact /api/roster rows) plus what filtering needs,
             precomputed: total followers, folded search text, place keys, tier rank.
  facets()   the options the filter bar offers, most common first. Never a count.
  query()    one batch: search, every filter, sort and group-by, then a slice.
             Answers {items, cursor, has_more} and a "match" count only when a filter
             or a search is on (the page shows "N creators match" then, never the
             size of the roster).
  cards()    named creators (the selection page, the AI shortlist, "add" flows).

Ordered results are cached per (version, query) for a minute, so the next batch of the
same view is a slice, not a re-sort. The last two index versions are kept, so a cursor
issued before a creator was edited still continues the list it started.

The JS this mirrors lives in assets/js/catalogue.js: fold(), values(), place(),
tierRank(), totalFollowers(), Controls.matches/order and initApp's group-by. Keep them
in step.
"""

from array import array
import hashlib
import json
import re
import threading
import time
import unicodedata

BATCH = 48
MAX_LIMIT = 480            # returning to the same spot reloads every batch the page had, in one go
RESULT_TTL = 60            # seconds an ordered result is reused (licences and analyses can change under it)
CHECK_EVERY = 1.0          # seconds between roster-version checks; tests set 0
KEEP_OLD = 900             # seconds the previous version stays for cursors already handed out (it costs a second roster in memory)
_lock = threading.Lock()
_state = {"checked": 0.0, "key": None, "versions": [], "results": {}}

SORTS = ("", "followers-desc", "followers-asc", "tier-desc", "tier-asc", "name")
GROUPS = ("tier", "platform", "country", "interest")
G_NONE = {"tier": "No tier", "platform": "No platform", "country": "Location not specified",
          "interest": "No interest listed"}

# ------------------------------------------------------------- text, as catalogue.js reads it

_MARKS = re.compile("[̀-ًͯ-ٟ]")


def fold(text):
    """catalogue.js fold(): NFKD, accents and Arabic diacritics off, hamza forms on alef
    unified, lower case, anything that is not a letter or a digit squeezed to one space."""
    t = unicodedata.normalize("NFKD", str(text or ""))
    t = _MARKS.sub("", t)
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")
    t = t.lower()
    out, gap = [], False
    for ch in t:
        if unicodedata.category(ch)[0] in "LN":
            if gap and out:
                out.append(" ")
            gap = False
            out.append(ch)
        else:
            gap = True
    return "".join(out)


_SPLIT = re.compile("[,;،؛/]")


def values(text):
    """catalogue.js values(): a multi-valued field split on , ; ، ؛ /"""
    if not text:
        return []
    return [v.strip() for v in _SPLIT.split(str(text)) if v.strip()]


# ------------------------------------------------------------------- places (catalogue.js place())

COUNTRY_ORDER = ["Saudi Arabia", "UAE", "Egypt", "Kuwait", "Qatar", "Bahrain", "Oman", "Jordan", "Lebanon"]
PLACES = {
    "Saudi Arabia": ["riyadh", "jeddah", "jedda", "dammam", "khobar", "al khobar", "dhahran",
                     "taif", "makkah", "mecca", "madinah", "medina", "elmadina elmonawara", "al madinah",
                     "najran", "abha", "khamis mushait", "tabuk", "jazan", "jizan", "hail", "qassim",
                     "buraidah", "al ahsa", "hofuf", "jubail", "yanbu", "al kharj", "ksa", "saudi arabia",
                     "saudi", "saudi arabia not specified yet"],
    "UAE": ["dubai", "abu dhabi", "sharjah", "ajman", "al ain", "ras al khaimah",
            "umm al quwain", "fujairah", "uae", "united arab emirates", "emirates"],
    "Egypt": ["cairo", "giza", "alexandria", "mansora", "mansoura", "boursaeed", "port said",
              "tanta", "zagazig", "egypt"],
    "Kuwait": ["kuwait", "kuwait city"],
    "Qatar": ["qatar", "doha"],
    "Bahrain": ["bahrain", "manama"],
    "Oman": ["oman", "muscat"],
    "Jordan": ["jordan", "amman"],
    "Lebanon": ["lebanon", "beirut"],
}
PLACE_LABEL = {
    "elmadina elmonawara": "Madinah", "al madinah": "Madinah", "medina": "Madinah",
    "mecca": "Makkah", "jedda": "Jeddah", "al khobar": "Khobar", "boursaeed": "Port Said",
    "mansora": "Mansoura", "jizan": "Jazan",
}
COUNTRY_WORDS = ["ksa", "saudi", "saudi arabia", "saudi arabia not specified yet", "uae", "united arab emirates",
                 "emirates", "egypt", "kuwait", "qatar", "bahrain", "oman", "jordan", "lebanon"]
COUNTRY_OF = {p: c for c, ps in PLACES.items() for p in ps}
_PENDING = re.compile(r"^\s*(.+?)\s+not specified yet\s*$", re.I)


def _title(s):
    """JS s.replace(/\\b[a-z]/g, upper): a letter after a non-word character goes upper case."""
    return re.sub(r"\b[a-z]", lambda m: m.group(0).upper(), s, flags=re.ASCII)


def place(raw):
    """One raw city value -> (country, label, key), exactly as catalogue.js place()."""
    raw = str(raw or "")
    m = _PENDING.match(raw)
    if m:
        named = m.group(1).lower()
        land = COUNTRY_OF.get(named) or next((c for c in COUNTRY_ORDER if c.lower() == named), None) or _title(named)
        return land, "City not specified", land + "|City not specified"
    clean = re.sub(r"\s+", " ", re.sub(r"[()]", " ", re.sub(r"\(([^)]*)\)?", " ", raw))).strip()
    k = clean.lower()
    inner = ((re.search(r"\(([^)]*)", raw) or [None, ""])[1] or "").lower().strip()
    if inner in COUNTRY_OF and (k not in COUNTRY_OF or k in COUNTRY_WORDS):
        k = inner
    country = COUNTRY_OF.get(k)
    if not country:
        other = _title(clean.lower()) or "Other"
        return "Other", other, "Other|" + other
    label = "City not specified" if k in COUNTRY_WORDS else (PLACE_LABEL.get(k) or _title(k))
    return country, label, country + "|" + label


# ------------------------------------------------------------------------------- tiers

TIER_SIZE = ["nano", "micro", "mid-tier", "mid", "macro", "mega"]


def tier_rank(name, table):
    """catalogue.js tierRank(): HCP tiers rank beside the band they mirror."""
    name = str(name or "")
    base = re.sub(r"^hcp\s*-\s*", "", name, flags=re.I).lower()
    i = TIER_SIZE.index(base) if base in TIER_SIZE else -1
    if i == 3:
        i = 2
    if i == -1:
        i = table.index(name) if name in table else -1
    return i * 2 + (1 if re.match(r"^hcp", name, re.I) else 0)


# ------------------------------------------------------------------------------- the index

class Index:
    """The roster cards and, per card, the values the filters, sorts and groups read."""

    def __init__(self, version, cards, tiers):
        self.version = version
        # The short name cursors and cached results carry.
        self.tag = hashlib.sha1(json.dumps(version, sort_keys=True, default=str).encode()).hexdigest()[:10]
        self.cards = cards
        self.at = {c["code"]: i for i, c in enumerate(cards)}
        table = [t["name"] for t in tiers]
        self.tier_table = table
        n = len(cards)
        self.followers = [0] * n
        self.search = [""] * n
        self.tier = [""] * n
        self.platforms = [None] * n
        self.interests = [None] * n
        self.places = [None] * n
        self.countries = [None] * n
        self.rank = [0] * n
        self.name = [""] * n
        for i, c in enumerate(cards):
            total = sum(_int(p.get("followers")) for p in (c.get("profiles") or []))
            self.followers[i] = total or _int(c.get("followers"))
            self.search[i] = fold((c.get("name") or "") + " " + (c.get("code") or ""))
            self.tier[i] = c.get("tier") or ""
            self.platforms[i] = values(c.get("platform"))
            self.interests[i] = values(c.get("interest"))
            keys, lands = [], []
            for v in values(c.get("city") or "Unspecified"):
                if v.lower() == "unspecified":
                    continue
                land, _, key = place(v)
                keys.append(key)
                if land not in lands:
                    lands.append(land)
            self.places[i] = keys
            self.countries[i] = lands
            self.rank[i] = tier_rank(self.tier[i], table)
            self.name[i] = (c.get("name") or "").lower()
        self._facets = None

    # -- the filter bar's options --
    def facets(self):
        if self._facets is None:
            def order(lists):
                seen = {}
                for vs in lists:
                    for v in vs:
                        seen[v] = seen.get(v, 0) + 1
                return [k for k, _ in sorted(seen.items(), key=lambda kv: -kv[1])]
            self._facets = {
                "tier": order([t] if t else [] for t in self.tier),
                "platform": order(self.platforms),
                "place": order(self.places),
                "interest": order(self.interests),
            }
        return self._facets


def _int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return 0


def current(key_fn, build_fn):
    """The index for the roster as it is now. key_fn() names the version cheaply;
    build_fn() returns (cards, tiers) and runs only when that name changes."""
    now = time.time()
    with _lock:
        vs = _state["versions"]
        if vs and now - _state["checked"] < CHECK_EVERY:
            return vs[-1]
    key = key_fn()
    with _lock:
        vs = _state["versions"]
        _state["checked"] = time.time()
        if vs and vs[-1].version == key:
            return vs[-1]
    cards, tiers = build_fn()
    idx = Index(key, cards, tiers)
    with _lock:
        vs = _state["versions"]
        if not vs or vs[-1].version != key:
            if vs:
                vs[-1].superseded = time.time()
            vs.append(idx)
            del vs[:-2]                 # the one before stays a while, for cursors already handed out
            _state["results"] = {k: v for k, v in _state["results"].items() if any(k[0] == x.tag for x in vs)}
        return vs[-1]


def invalidate():
    """Something changed that the version key cannot see (a photo replaced on disk)."""
    with _lock:
        _state["checked"] = 0.0
        _state["versions"] = []
        _state["results"] = {}


def _tag(idx):
    return idx.tag


def held(tag):
    with _lock:
        vs = _state["versions"]
        if len(vs) > 1 and time.time() - getattr(vs[0], "superseded", 0) > KEEP_OLD:
            del vs[0]
        for x in vs:
            if _tag(x) == tag:
                return x
    return None


# ------------------------------------------------------------------------------- queries

def clean_query(q):
    """The request's filters, kept to known keys and short values. ``q`` is a dict of
    lists (urllib.parse.parse_qs)."""
    def many(k, cap=60):
        out = []
        for v in q.get(k) or []:
            v = str(v)[:120]
            if v and v not in out:
                out.append(v)
        return out[:cap]

    def one(k, size=200):
        v = (q.get(k) or [""])[0]
        return str(v)[:size]

    def num(k):
        v = one(k, 20).strip()
        try:
            n = int(float(v))
        except ValueError:
            return None
        return n if n > 0 else None

    sort = one("sort", 20) if "sort" in q else "followers-desc"
    out = {
        "q": fold(one("q", 120)),
        "tier": many("tier"), "platform": many("platform"), "place": many("place", 200), "interest": many("interest"),
        "fmin": num("fmin"), "fmax": num("fmax"),
        "lic": [v for v in many("lic") if v in ("SA", "AE", "EG")],
        "sort": sort if sort in SORTS else "followers-desc",
        "group": one("group", 20) if one("group", 20) in GROUPS else "",
        "disc": None, "dplat": None,
    }
    if out["fmin"] and out["fmax"] and out["fmax"] < out["fmin"]:
        out["fmin"], out["fmax"] = out["fmax"], out["fmin"]
    raw = one("disc", 2000)
    if raw:
        try:
            d = json.loads(raw)
            out["disc"] = d if isinstance(d, dict) and d else None
        except ValueError:
            out["disc"] = None
    plat = one("dplat", 20)
    out["dplat"] = plat if plat in ("Instagram", "TikTok", "Snapchat", "YouTube", "X", "Facebook") else None
    return out


def filtering(f):
    """True when the reader has narrowed the roster: only then is a "match" count sent."""
    return bool(f["q"] or f["tier"] or f["platform"] or f["place"] or f["interest"] or f["fmin"] or f["fmax"]
                or f["lic"] or f["disc"])


def _key(idx, f):
    return (_tag(idx), json.dumps(f, sort_keys=True))


class Ordered:
    """One query's answer, compact: card positions as a C int array (40 KB at 10,000, where a
    list of tuples took ~0.9 MB), and for a grouped view a group number per entry."""
    __slots__ = ("at", "gid", "names")

    def __init__(self, at, gid=None, names=None):
        self.at, self.gid, self.names = at, gid, names

    def __len__(self):
        return len(self.at)

    def slice(self, start, end):
        if self.gid is None:
            return [(i, None) for i in self.at[start:end]]
        return [(i, self.names[g]) for i, g in zip(self.at[start:end], self.gid[start:end])]


def ordered(idx, f, licences=None, discover=None):
    """This query's Ordered answer, best first, and how many creators match. Cached for RESULT_TTL."""
    key = _key(idx, f)
    now = time.time()
    with _lock:
        hit = _state["results"].get(key)
        if hit and now - hit[0] < RESULT_TTL:
            return hit[1], hit[2]
    allow = None
    if f["lic"]:
        lic = licences() if licences else {}
        allow = {code for code, ls in lic.items() if any(l.get("country") in f["lic"] for l in ls)}
    if f["disc"]:
        codes = set(discover(f["disc"], f["dplat"]) if discover else [])
        allow = codes if allow is None else (allow & codes)
    sets = {d: set(f[d]) for d in ("tier", "platform", "place", "interest") if f[d]}
    keep = []
    cards, q = idx.cards, f["q"]
    for i in range(len(cards)):
        if q and q not in idx.search[i]:
            continue
        if f["fmin"] and idx.followers[i] < f["fmin"]:
            continue
        if f["fmax"] and idx.followers[i] > f["fmax"]:
            continue
        if "tier" in sets and idx.tier[i] not in sets["tier"]:
            continue
        if "platform" in sets and not any(v in sets["platform"] for v in idx.platforms[i]):
            continue
        if "place" in sets and not any(v in sets["place"] for v in idx.places[i]):
            continue
        if "interest" in sets and not any(v in sets["interest"] for v in idx.interests[i]):
            continue
        if allow is not None and cards[i]["code"] not in allow:
            continue
        keep.append(i)
    s = f["sort"]
    fol, rank = idx.followers, idx.rank
    if s == "followers-desc":
        keep.sort(key=lambda i: -fol[i])
    elif s == "followers-asc":
        keep.sort(key=lambda i: fol[i])
    elif s == "tier-desc":
        keep.sort(key=lambda i: (-rank[i], -fol[i]))
    elif s == "tier-asc":
        keep.sort(key=lambda i: (rank[i], -fol[i]))
    elif s == "name":
        keep.sort(key=lambda i: idx.name[i])
    matched = len(keep)
    if f["group"]:
        out = _grouped(idx, keep, f["group"])
    else:
        out = Ordered(array("i", keep))
    with _lock:
        res = _state["results"]
        if len(res) >= 32:
            for k in sorted(res, key=lambda k: res[k][0])[:8]:
                res.pop(k, None)
        res[key] = (now, out, matched)
    return out, matched


def _gkeys(idx, i, dim):
    if dim == "tier":
        out = [idx.tier[i]] if idx.tier[i] else []
    elif dim == "platform":
        out = idx.platforms[i]
    elif dim == "interest":
        out = idx.interests[i]
    else:
        out = idx.countries[i]
    return out or [G_NONE[dim]]


def _grouped(idx, keep, dim):
    """initApp's layoutGroups: sections in a fixed order (tier table, country list), then
    the biggest first, then by name; 'none' last. A creator in two groups is in both."""
    members, count = {}, {}
    for i in keep:
        for k in _gkeys(idx, i, dim):
            members.setdefault(k, []).append(i)
            count[k] = count.get(k, 0) + 1
    fixed = idx.tier_table if dim == "tier" else COUNTRY_ORDER if dim == "country" else None
    none = G_NONE[dim]

    def sort_key(k):
        pos = 0
        if fixed is not None:
            pos = fixed.index(k) if k in fixed else 99
        return (k == none, pos, -count[k], k.lower())
    names, at, gid = [], array("i"), array("H")
    for k in sorted(members, key=sort_key):
        names.append(k)
        at.extend(members[k])
        gid.extend([len(names) - 1] * len(members[k]))
    return Ordered(at, gid, names)


def page(idx, f, cursor=None, limit=BATCH, licences=None, discover=None):
    """One batch. The cursor is "<version tag>.<offset>": a version still held keeps
    its order, so a list never shifts under someone scrolling it."""
    start = 0
    if cursor:
        tag, _, off = str(cursor).partition(".")
        older = held(tag)
        if older is not None:
            idx = older
        try:
            start = max(0, int(off))
        except ValueError:
            start = 0
    limit = max(1, min(MAX_LIMIT, int(limit or BATCH)))
    seq, matched = ordered(idx, f, licences, discover)
    chunk = seq.slice(start, start + limit)
    items = []
    for i, g in chunk:
        c = idx.cards[i]
        items.append(dict(c, g=g) if g is not None else c)
    end = start + len(chunk)
    more = end < len(seq)
    out = {"ok": True, "items": items, "has_more": more,
           "cursor": ("%s.%d" % (_tag(idx), end)) if more else None, "v": _tag(idx)}
    if filtering(f):
        out["match"] = matched
    return out


def cards(idx, codes):
    """The named creators that are on the roster, in the order asked."""
    out, seen = [], set()
    for code in codes:
        i = idx.at.get(code)
        if i is not None and code not in seen:
            seen.add(code)
            out.append(idx.cards[i])
    return out
