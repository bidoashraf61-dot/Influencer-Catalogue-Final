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
_build_lock = threading.Lock()     # held for a whole index build (minutes at 14,000+ creators); _lock never is
_state = {"checked": 0.0, "key": None, "versions": [], "results": {}}

SORTS = ("", "daily", "followers-desc", "followers-asc", "tier-desc", "tier-asc", "name", "added-desc", "added-asc")
GROUPS = ("tier", "platform", "country", "interest")
# Labels the classification can return that are not an industry a client would book by.
NOT_AN_INDUSTRY = ("General Lifestyle", "Unclassifiable")
# "Recommended" (sort=daily, the catalogue's default since 2026-10-19; groups reset 2026-10-20):
# doctors (any HCP tier) first, then Saudi celebrities (Mega tier, located in Saudi Arabia), then
# creators already put in a selection, then everyone else by tier size. Random inside each group,
# the same random for everyone all day (seeded by the Riyadh date), a new one the next day.
# Unknown or no tier goes last.
DAILY_GROUPS = {"mega": 3, "macro": 4, "mid-tier": 5, "mid": 5, "micro": 6, "nano": 7}
G_HCP, G_CELEB, G_PICKED, G_OTHER = 0, 1, 2, 8
CELEB_COUNTRY = "Saudi Arabia"
PICKED_EVERY = 600         # seconds the "in a selection" set is reused before it is read again
_picked = {"at": 0.0, "codes": frozenset(), "tag": ""}
RIYADH_OFFSET = 3 * 3600    # Riyadh is UTC+3 all year (no daylight saving)


def riyadh_day(now=None):
    """Today in Riyadh as "YYYYMMDD": the seed of the daily order."""
    return time.strftime("%Y%m%d", time.gmtime((time.time() if now is None else now) + RIYADH_OFFSET))


def daily_group(tier, countries=(), picked=False):
    """0 doctors (any HCP tier), 1 Saudi celebrities (Mega in Saudi Arabia), 2 in a selection,
    3 other Mega, 4 Macro, 5 Mid, 6 Micro, 7 Nano, 8 anything else."""
    t = str(tier or "").strip().lower()
    if t.startswith("hcp"):
        return G_HCP
    if t == "mega" and CELEB_COUNTRY in (countries or ()):
        return G_CELEB
    if picked:
        return G_PICKED
    return DAILY_GROUPS.get(t, G_OTHER)


def picked_codes():
    """(codes, tag): every creator on a selection that is not deleted, archived ones included.
    Read at most once every PICKED_EVERY seconds; the tag names the set for the result cache."""
    now = time.time()
    if _picked["tag"] and now - _picked["at"] < PICKED_EVERY:
        return _picked["codes"], _picked["tag"]
    codes = set()
    try:
        import db
        with db.connect() as conn:
            for (raw,) in conn.execute("SELECT codes FROM selections WHERE deleted_at IS NULL"):
                try:
                    codes.update(str(c) for c in json.loads(raw or "[]"))
                except (ValueError, TypeError):
                    pass
    except Exception:
        if _picked["tag"]:
            return _picked["codes"], _picked["tag"]
    codes = frozenset(codes)
    tag = hashlib.sha1(",".join(sorted(codes)).encode()).hexdigest()[:10]
    _picked.update(at=now, codes=codes, tag=tag)
    return codes, tag


def daily_key(day, code):
    """The creator's place inside its group on ``day``: a hash, so it does not depend on who
    else is in the result (a filtered view keeps the same relative order)."""
    return int.from_bytes(hashlib.blake2b(("%s|%s" % (day, code)).encode(), digest_size=8).digest(), "big")


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

def _added_at():
    """{code: created_at} for the "Newest added" / "Oldest added" sorts (the cards do not carry the date)."""
    try:
        import db
        with db.connect() as conn:
            return {r[0]: r[1] or 0 for r in conn.execute("SELECT code, created_at FROM creators")}
    except Exception:
        return {}


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
        self.ind = [None] * n        # main industry
        self.sub = [None] * n        # sub-niches (list)
        self.also = [None] * n       # other industries the creator also covers
        self.itier = [""] * n        # Confirmed / Probable / Review ("" = not classified)
        self.added = [0] * n         # when the creator joined the roster (epoch; 0 = not known, always sorts last)
        added = _added_at() if cards and "created_at" not in cards[0] else {}
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
            self.ind[i] = c.get("ind") or None
            self.sub[i] = c.get("sub") or []
            self.also[i] = c.get("also") or []
            self.itier[i] = c.get("itier") or ""
            self.added[i] = _int(c.get("created_at")) or added.get(c.get("code"), 0)
        self._facets = None
        self._daily = (None, None)

    def daily(self, day, picked=frozenset(), ptag=""):
        """(group, shuffle key) per card for ``day``; worked out once per day and selection set."""
        got, keys = self._daily
        if got != (day, ptag):
            keys = [(daily_group(self.tier[i], self.countries[i], (c.get("code") or "") in picked),
                     daily_key(day, c.get("code") or "")) for i, c in enumerate(self.cards)]
            self._daily = ((day, ptag), keys)
        return keys

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
            # Industry filter: only real industries (a catch-all is not one), most Confirmed creators first;
            # the sub-niches of each, most common first. No counts are sent.
            inds, subs = {}, {}
            for i in range(len(self.cards)):
                if self.itier[i] == "Confirmed" and self.ind[i] and self.ind[i] not in NOT_AN_INDUSTRY:
                    inds[self.ind[i]] = inds.get(self.ind[i], 0) + 1
                if self.itier[i] in ("Confirmed", "Probable") and self.ind[i]:
                    for sn in self.sub[i]:
                        d = subs.setdefault(self.ind[i], {})
                        d[sn] = d.get(sn, 0) + 1
            self._facets["industry"] = [k for k, _ in sorted(inds.items(), key=lambda kv: -kv[1])]
            self._facets["sub"] = {k: [x for x, _ in sorted(v.items(), key=lambda kv: -kv[1])] for k, v in subs.items() if k in inds}
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
        if len(vs) > 1 and time.time() - getattr(vs[0], "superseded", 0) > KEEP_OLD:
            del vs[0]
        if vs and vs[-1].version == key:
            return vs[-1]
    with _build_lock:                   # one build at a time: a cold cache must not start one build per request
        with _lock:
            vs = _state["versions"]
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

    sort = one("sort", 20) if "sort" in q else "daily"
    out = {
        "q": fold(one("q", 120)),
        "tier": many("tier"), "platform": many("platform"), "place": many("place", 200), "interest": many("interest"),
        "industry": many("industry"), "sub": many("sub", 80),
        "fmin": num("fmin"), "fmax": num("fmax"),
        "lic": [v for v in many("lic") if v in ("SA", "AE", "EG")],
        "aud": _aud(many("aud")),
        "sort": sort if sort in SORTS else "daily",
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


AUD = ("SA", "AE", "EG", "KW", "QA", "BH", "OM")    # discover.MARKETS; "GCC" opens into the last four
AUD_GCC = ("KW", "QA", "BH", "OM")


def _aud(vals):
    out = []
    for v in vals:
        for c in (AUD_GCC if v == "GCC" else (v,)):
            if c in AUD and c not in out:
                out.append(c)
    return out


def filtering(f):
    """True when the reader has narrowed the roster: only then is a "match" count sent."""
    return bool(f["q"] or f["tier"] or f["platform"] or f["place"] or f["interest"] or f["industry"] or f["sub"] or f["fmin"] or f["fmax"]
                or f["lic"] or f["disc"] or f.get("aud"))


def _key(idx, f):
    return (_tag(idx), json.dumps(f, sort_keys=True))


class Ordered:
    """One query's answer, compact: card positions as a C int array (40 KB at 10,000, where a
    list of tuples took ~0.9 MB), and for a grouped view a group number per entry."""
    __slots__ = ("at", "gid", "names", "pm")

    def __init__(self, at, gid=None, names=None, pm=None):
        # pm: for an industry search, 1 where the creator is a probable match (listed after the confirmed ones)
        self.at, self.gid, self.names, self.pm = at, gid, names, pm

    def __len__(self):
        return len(self.at)

    def slice(self, start, end):
        if self.gid is None:
            if self.pm is not None:
                return [(i, None, p) for i, p in zip(self.at[start:end], self.pm[start:end])]
            return [(i, None, 0) for i in self.at[start:end]]
        return [(i, self.names[g], 0) for i, g in zip(self.at[start:end], self.gid[start:end])]


def _industry_level(idx, i, inds, subs):
    """0 = not a match, 1 = confirmed match, 2 = probable match. A creator whose industry call is "Review"
    is never in an industry or sub-niche result. Industry and sub-niche both asked: the weaker one decides."""
    tier = idx.itier[i]
    if tier not in ("Confirmed", "Probable") or not idx.ind[i]:
        return 0
    level = 1
    if inds:
        if idx.ind[i] in inds:
            lv = 1 if tier == "Confirmed" else 2
        elif any(a in inds for a in idx.also[i]):
            lv = 2
        else:
            return 0
        level = max(level, lv)
    if subs:
        if any(s in subs for s in idx.sub[i]):
            lv = 1 if tier == "Confirmed" else 2
        else:
            return 0
        level = max(level, lv)
    return level


def ordered(idx, f, licences=None, discover=None, day=None, picked=None, audience=None):
    """This query's Ordered answer, best first, and how many creators match. Cached for RESULT_TTL.
    ``day`` ("YYYYMMDD", Riyadh) seeds the daily order; today when not given. ``picked`` (codes on
    a selection) lifts those creators in the daily order; read from the database when not given."""
    ptag = ""
    if f["sort"] == "daily":
        if picked is None:
            picked, ptag = picked_codes()
        else:
            picked = frozenset(picked)
            ptag = hashlib.sha1(",".join(sorted(picked)).encode()).hexdigest()[:10]
        f = dict(f, day=day or riyadh_day(), pk=ptag)
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
    if f.get("aud"):
        # "Audience in" (item 226): ``audience()`` is {code: top-audience market codes}.
        want = set(f["aud"])
        tops = audience() if audience else {}
        codes = {code for code, got in tops.items() if got & want}
        allow = codes if allow is None else (allow & codes)
    sets = {d: set(f[d]) for d in ("tier", "platform", "place", "interest") if f[d]}
    ind_set, sub_set = set(f["industry"]), set(f["sub"])
    level = {}          # card position -> 1 confirmed match, 2 probable match (industry / sub-niche search only)
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
        if ind_set or sub_set:
            lv = _industry_level(idx, i, ind_set, sub_set)
            if not lv:
                continue
            level[i] = lv
        if allow is not None and cards[i]["code"] not in allow:
            continue
        keep.append(i)
    s = f["sort"]
    fol, rank = idx.followers, idx.rank
    if s == "daily":
        dk = idx.daily(f["day"], picked, ptag)
        keep.sort(key=lambda i: dk[i])
    elif s == "followers-desc":
        keep.sort(key=lambda i: -fol[i])
    elif s == "followers-asc":
        keep.sort(key=lambda i: fol[i])
    elif s == "tier-desc":
        keep.sort(key=lambda i: (-rank[i], -fol[i]))
    elif s == "tier-asc":
        keep.sort(key=lambda i: (rank[i], -fol[i]))
    elif s == "name":
        keep.sort(key=lambda i: idx.name[i])
    elif s == "added-desc":
        keep.sort(key=lambda i: (-idx.added[i], -fol[i]))
    elif s == "added-asc":
        keep.sort(key=lambda i: (idx.added[i] or float("inf"), -fol[i]))
    if level:                       # confirmed matches first, probable ones after; the chosen order holds inside each
        keep.sort(key=lambda i: level[i])
    matched = len(keep)
    if f["group"]:
        out = _grouped(idx, keep, f["group"])
    elif level:
        out = Ordered(array("i", keep), pm=array("b", [1 if level[i] == 2 else 0 for i in keep]))
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


def page(idx, f, cursor=None, limit=BATCH, licences=None, discover=None, audience=None):
    """One batch. The cursor is "<version tag>.<offset>": a version still held keeps
    its order, so a list never shifts under someone scrolling it. The daily order adds
    ".<day>", so someone scrolling across Riyadh midnight keeps the day they started on."""
    start, day = 0, None
    if cursor:
        tag, _, off = str(cursor).partition(".")
        off, _, d = off.partition(".")
        if f["sort"] == "daily" and len(d) == 8 and d.isdigit():
            day = d
        older = held(tag)
        if older is not None:
            idx = older
        try:
            start = max(0, int(off))
        except ValueError:
            start = 0
    limit = max(1, min(MAX_LIMIT, int(limit or BATCH)))
    if f["sort"] == "daily" and day is None:
        day = riyadh_day()
    seq, matched = ordered(idx, f, licences, discover, day, audience=audience)
    chunk = seq.slice(start, start + limit)
    # While "Audience in" is on, each card says which of the asked markets is its top audience
    # ("ta": codes, never a share), so the card can show "Top audience: Kuwait".
    tops = (audience() if audience else {}) if f.get("aud") else None
    items = []
    for i, g, pm in chunk:
        c = idx.cards[i]
        if g is not None:
            c = dict(c, g=g)
        if pm:
            c = dict(c, pm=1)
        if tops is not None:
            ta = [k for k in AUD if k in f["aud"] and k in tops.get(c.get("code"), ())]
            if ta:
                c = dict(c, ta=ta)
        items.append(c)
    end = start + len(chunk)
    more = end < len(seq)
    out = {"ok": True, "items": items, "has_more": more,
           "cursor": ("%s.%d" % (_tag(idx), end) + ("." + day if day else "")) if more else None, "v": _tag(idx)}
    if filtering(f):
        out["match"] = matched
    # The roster's size, rounded DOWN to the thousand and shown as "14,000+" (owner, 2026-10-13): the exact
    # number is never sent.
    out["plus"] = max((len(idx.cards) // 1000) * 1000, roster_plus_floor())
    return out


def roster_plus_floor():
    """Owner, 2026-10-21: the out-of-scope clean-up archives creators, but the public figure stays "14,000+".
    Setting roster_plus_floor (a whole thousand) is the least the catalogue shows; 0 = the real rounded size."""
    try:
        import db
        return max(0, int(db.setting("roster_plus_floor", 0) or 0)) // 1000 * 1000
    except Exception:
        return 0


def cards(idx, codes):
    """The named creators that are on the roster, in the order asked."""
    out, seen = [], set()
    for code in codes:
        i = idx.at.get(code)
        if i is not None and code not in seen:
            seen.add(code)
            out.append(idx.cards[i])
    return out
