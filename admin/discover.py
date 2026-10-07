"""Discovery: the roster filtered on what only the analyses know.

The catalogue filters on the card's own fields (platform, size, place,
interest) in the browser. Audience and performance live in the creator
analyses, which are client data and stay on the server: the page sends the
filters it wants, and gets back only the codes that pass. No number from an
analysis leaves this module.

Three jobs:
  facets()       the options the sidebar offers (names only, never counts)
  match(f)       codes whose analysis passes every filter in ``f``
  like(code)     creators most like one creator, best first
  parse(text)    a sentence turned into sidebar filters (keyword reading, free)

An analysis is per platform. A creator passes when any one of their
analyses passes all the filters: a Mid-Tier Instagram account with a Saudi
audience qualifies even if their TikTok audience is Egyptian.
"""

import json
import re
import threading
from datetime import date

import db

_lock = threading.Lock()
_cache = {"sig": None, "docs": {}, "facets": None}

AGE_ORDER = ["13-17", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"]


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _shares(items, key="name"):
    """[{name|code, pct}] -> {value: pct}"""
    out = {}
    for it in items or []:
        if isinstance(it, dict) and it.get(key) and _num(it.get("pct")) is not None:
            out[str(it[key]).strip()] = _num(it["pct"])
    return out


def _growth(d):
    g = _num(d.get("followers_change_pct"))
    if g is not None:
        return g
    pts = [x for x in (d.get("growth") or []) if _num(x.get("followers"))]
    if len(pts) >= 2 and _num(pts[0]["followers"]):
        a, b = _num(pts[0]["followers"]), _num(pts[-1]["followers"])
        return (b - a) / a * 100
    return None


def _days_since(text):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(text or ""))
    if not m:
        return None
    try:
        return (date.today() - date(int(m[1]), int(m[2]), int(m[3]))).days
    except ValueError:
        return None


def summary(d, platform):
    """The facts a filter can ask about, from one stored analysis."""
    au = d.get("audience") or {}
    gender = au.get("gender") or {}
    real = _num(d.get("real_people_pct"))
    if real is None:
        real = _num(d.get("credibility_pct"))
    if real is None and _num(d.get("fake_followers_pct")) is not None:
        real = 100 - _num(d.get("fake_followers_pct"))
    sponsored = bool(d.get("sponsored_posts")) or _num(d.get("paid_post_performance")) is not None
    return {
        "platform": platform,
        "er": _num(d.get("er")),
        "reels_er": _num(d.get("reels_er")),
        "views": _num(d.get("avg_views")) or _num(d.get("avg_reel_plays")),
        "likes": _num(d.get("avg_likes")),
        "comments": _num(d.get("avg_comments")),
        "real": real,
        "growth": _growth(d),
        "ppw": _num(d.get("posts_per_week")),
        "idle": _days_since(d.get("last_post")),
        "account": str(d.get("account_type") or "").strip().title() or None,
        "sponsored": sponsored,
        "brands": {str(b.get("name")).strip() for b in d.get("brands") or [] if isinstance(b, dict) and b.get("name")},
        "topics": {str(t).strip() for t in d.get("creator_interests") or [] if str(t).strip()},
        "countries": _shares(au.get("countries"), "code"),
        "cities": _shares(au.get("cities")),
        "female": _num(gender.get("female")),
        "male": _num(gender.get("male")),
        "ages": _shares(au.get("ages")),
        "langs": _shares(au.get("languages")),
        "interests": _shares(au.get("interests")),
        "affinity": _shares(au.get("brand_affinity")),
    }


def _load():
    """Summaries for every analysis, rebuilt only when an analysis changed."""
    with db.connect() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(creator_analysis)")}
        sig = tuple(conn.execute("SELECT COUNT(*), COALESCE(MAX(updated_at), 0) FROM creator_analysis").fetchone())
        if sig == _cache["sig"]:
            return _cache["docs"]
        q = "SELECT code, %s, data FROM creator_analysis" % ("platform" if "platform" in cols else "'Instagram'")
        rows = conn.execute(q).fetchall()
    docs = {}
    for code, platform, data in rows:
        try:
            d = json.loads(data or "{}")
        except ValueError:
            continue
        docs.setdefault(code, []).append(summary(d, platform or "Instagram"))
    with _lock:
        _cache.update(sig=sig, docs=docs, facets=None)
    return docs


def facets():
    """What the Audience and Performance groups offer, most common first.
    Names only: how many creators carry each one is commercial information."""
    docs = _load()
    if _cache["facets"] is not None:
        return _cache["facets"]
    tally = {k: {} for k in ("countries", "cities", "langs", "interests", "affinity", "brands", "topics", "account", "ages")}
    for lst in docs.values():
        for s in lst:
            for k in ("countries", "cities", "langs", "interests", "affinity", "ages"):
                for name, pct in s[k].items():
                    if pct >= 3:
                        tally[k][name] = tally[k].get(name, 0) + 1
            for k in ("brands", "topics"):
                for name in s[k]:
                    tally[k][name] = tally[k].get(name, 0) + 1
            if s["account"]:
                tally["account"][s["account"]] = tally["account"].get(s["account"], 0) + 1

    def top(k, n, floor=1):
        return [v for v, c in sorted(tally[k].items(), key=lambda x: (-x[1], x[0].lower())) if c >= floor][:n]

    out = {
        "measured": bool(docs),
        "countries": top("countries", 40),
        "cities": top("cities", 40, 2),
        "languages": top("langs", 24),
        "ages": [a for a in AGE_ORDER if a in tally["ages"]] or AGE_ORDER[1:6],
        "interests": sorted(top("interests", 60), key=str.lower),
        "affinity": top("affinity", 60, 2),
        "brands": top("brands", 60, 1),
        "topics": sorted(top("topics", 40), key=str.lower),
        "accounts": top("account", 6),
    }
    with _lock:
        _cache["facets"] = out
    return out


def _share_of(shares, picked):
    return sum(shares.get(p, 0) for p in picked)


def _passes(s, f):
    def at_least(v, key):
        lim = _num(f.get(key))
        return lim is None or (v is not None and v >= lim)

    def at_most(v, key):
        lim = _num(f.get(key))
        return lim is None or (v is not None and v <= lim)

    if f.get("a_country") and _share_of(s["countries"], f["a_country"]) < (_num(f.get("a_country_min")) or 20):
        return False
    if f.get("a_city") and _share_of(s["cities"], f["a_city"]) < (_num(f.get("a_city_min")) or 10):
        return False
    if f.get("a_lang") and _share_of(s["langs"], f["a_lang"]) < (_num(f.get("a_lang_min")) or 20):
        return False
    if f.get("a_age") and _share_of(s["ages"], f["a_age"]) < (_num(f.get("a_age_min")) or 25):
        return False
    g = f.get("a_gender")
    if g:
        fem, mal = s["female"], s["male"]
        if fem is None or mal is None:
            return False
        ok = {"women": fem >= 60, "men": mal >= 60, "balanced": 40 <= fem <= 60}
        if not any(ok.get(x) for x in (g if isinstance(g, list) else [g])):
            return False
    if f.get("a_interest") and not set(f["a_interest"]) & set(s["interests"]):
        return False
    if f.get("a_affinity") and not set(f["a_affinity"]) & set(s["affinity"]):
        return False
    if f.get("brands") and not set(f["brands"]) & s["brands"]:
        return False
    if f.get("topics") and not set(f["topics"]) & s["topics"]:
        return False
    if f.get("account") and s["account"] not in f["account"]:
        return False
    if f.get("sponsored") and not s["sponsored"]:
        return False
    idle = _num(f.get("active_days"))
    if idle is not None and (s["idle"] is None or s["idle"] > idle):
        return False
    return (at_least(s["real"], "real_min") and at_least(s["er"], "er_min") and at_most(s["er"], "er_max")
            and at_least(s["reels_er"], "reels_er_min") and at_least(s["views"], "views_min")
            and at_least(s["likes"], "likes_min") and at_least(s["comments"], "comments_min")
            and at_least(s["growth"], "growth_min") and at_least(s["ppw"], "ppw_min"))


FILTER_KEYS = {"a_country", "a_country_min", "a_city", "a_city_min", "a_lang", "a_lang_min", "a_age", "a_age_min",
               "a_gender", "a_interest", "a_affinity", "brands", "topics", "account", "sponsored", "active_days",
               "real_min", "er_min", "er_max", "reels_er_min", "views_min", "likes_min", "comments_min",
               "growth_min", "ppw_min"}
LIST_KEYS = {"a_country", "a_city", "a_lang", "a_age", "a_gender", "a_interest", "a_affinity", "brands", "topics", "account"}


def clean(raw):
    """Only known keys, lists of short strings, numbers as numbers."""
    f = {}
    for k, v in (raw or {}).items() if isinstance(raw, dict) else []:
        if k not in FILTER_KEYS or v in (None, "", [], False):
            continue
        if k in LIST_KEYS:
            vals = v if isinstance(v, list) else [v]
            vals = [str(x)[:80] for x in vals[:60] if str(x).strip()]
            if vals:
                f[k] = vals
        elif k == "sponsored":
            f[k] = True
        elif _num(v) is not None:
            f[k] = _num(v)
    return f


def match(raw, platform=None):
    """Codes with at least one analysis passing every filter."""
    f = clean(raw)
    docs = _load()
    out = []
    for code, lst in docs.items():
        for s in lst:
            if platform and s["platform"] != platform:
                continue
            if _passes(s, f):
                out.append(code)
                break
    return out


def _tokens(text):
    return {w for w in re.split(r"[^\w]+", str(text or "").lower()) if len(w) > 2}


def _cos(a, b):
    keys = set(a) | set(b)
    if not keys:
        return None
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    na = sum(v * v for v in a.values()) ** 0.5
    nb = sum(v * v for v in b.values()) ** 0.5
    return dot / (na * nb) if na and nb else None


TIER_STEP = {"nano": 0, "micro": 1, "mid-tier": 2, "mid": 2, "macro": 3, "mega": 4}


def _tier(t):
    base = re.sub(r"^hcp\s*-\s*", "", str(t or "").lower()).strip()
    return TIER_STEP.get(base), str(t or "").lower().startswith("hcp")


def like(code, limit=48):
    """Creators most like ``code``: what they post about, where they are,
    their size and, where both are measured, who their audience is."""
    rows = {r["code"]: r for r in db.list_creators(active_only=True)}
    me = rows.get(code)
    if not me:
        return []
    docs = _load()
    mine = (docs.get(code) or [None])[0]
    my_topics = _tokens(me["interest"]) | ({t.lower() for t in mine["topics"]} if mine else set())
    my_tier, my_hcp = _tier(me["tier"])
    my_city = str(me["city"] or "").lower()
    my_plats = {p.strip().lower() for p in str(me["platform"] or "").split(",") if p.strip()}
    scored = []
    for other, r in rows.items():
        if other == code:
            continue
        s = 0.0
        topics = _tokens(r["interest"])
        theirs = (docs.get(other) or [None])[0]
        if theirs:
            topics |= {t.lower() for t in theirs["topics"]}
        if my_topics and topics:
            s += 3.0 * len(my_topics & topics) / len(my_topics | topics) * 2
        t, hcp = _tier(r["tier"])
        if my_tier is not None and t is not None:
            s += max(0, 2 - abs(my_tier - t))
        # A doctor is looked-alike by doctors first: that is what a healthcare brief is buying.
        if hcp == my_hcp:
            s += 3 if hcp else 0.3
        elif my_hcp:
            s -= 1
        city = str(r["city"] or "").lower()
        if my_city and city:
            if city == my_city:
                s += 1.5
            elif city.split(",")[-1].strip() == my_city.split(",")[-1].strip():
                s += 0.8
        if my_plats & {p.strip().lower() for p in str(r["platform"] or "").split(",")}:
            s += 0.8
        if (me["nationality"] or "") and r["nationality"] == me["nationality"]:
            s += 0.7
        if mine and theirs:
            c = _cos(mine["countries"], theirs["countries"])
            if c is not None:
                s += 3 * c
            if mine["female"] is not None and theirs["female"] is not None:
                s += 1.5 * (1 - min(1, abs(mine["female"] - theirs["female"]) / 50))
            c = _cos(mine["ages"], theirs["ages"])
            if c is not None:
                s += 1.5 * c
        if s > 0:
            scored.append((s, other))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [c for _, c in scored[:limit]]


# A sentence -> sidebar filters. Keyword reading only (free, instant): the
# paid AI shortlist stays in the portal's "Find creators".
_TIER_WORDS = {"Nano": ["nano"], "Micro": ["micro"], "Mid-Tier": ["mid-tier", "mid tier", "midtier", " mid "],
               "Macro": ["macro"], "Mega": ["mega", "celebrit", "famous"]}
_HCP_WORDS = ["doctor", "dr ", "dermatologist", "pharmacist", "physician", "nurse", "dentist", "hcp", "طبيب", "دكتور", "صيدل"]
_CITY_WORDS = {"Riyadh": ["riyadh", "الرياض"], "Jeddah": ["jeddah", "jedda", "جدة"], "Dammam": ["dammam", "الدمام"],
               "Khobar": ["khobar"], "Makkah": ["makkah", "mecca", "مكة"], "Madinah": ["madinah", "medina", "المدينة"],
               "Dubai": ["dubai", "دبي"], "Abu Dhabi": ["abu dhabi", "أبوظبي"], "Cairo": ["cairo", "القاهرة"],
               "Alexandria": ["alexandria", "الإسكندرية"]}
_COUNTRY = {"SA": "Saudi Arabia", "AE": "UAE", "EG": "Egypt", "KW": "Kuwait", "QA": "Qatar", "BH": "Bahrain",
            "OM": "Oman", "JO": "Jordan", "LB": "Lebanon", "IQ": "Iraq", "MA": "Morocco"}


def parse(text):
    import fit
    import matcher
    t = " " + " ".join(str(text or "").lower().split()) + " "
    raw, _missing = matcher.guess(text)
    out = {"platform": list(raw.get("platforms") or []), "tier": [], "country": [], "city": [],
           "interest_words": [], "hcp": False, "a_gender": None, "a_country": []}
    for tier, words in _TIER_WORDS.items():
        if any(w in t for w in words):
            out["tier"].append(tier)
    out["hcp"] = any(w in t for w in _HCP_WORDS)
    for city, words in _CITY_WORDS.items():
        if any(w in t for w in words):
            out["city"].append(city)
    for cc, words in fit.PLACE_WORDS.items():
        if any(re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", t) for w in words):
            if cc in _COUNTRY and _COUNTRY[cc] not in out["country"]:
                out["country"].append(_COUNTRY[cc])
    if not out["country"] and any(w in t for w in ("السعودية", "الرياض", "جدة")):
        out["country"].append("Saudi Arabia")
    # "an audience in Saudi" / "Saudi audience" asks about followers, not where the creator lives.
    if re.search(r"audience|followers|متابع|جمهور", t):
        out["a_country"] = [cc for cc, name in _COUNTRY.items() if name in out["country"]]
    for cat in raw.get("category") or []:
        out["interest_words"] += [cat] + [w.strip() for w in matcher._EXTRA_CATEGORY.get(cat, []) if w.strip()]
    g = raw.get("gender")
    out["a_gender"] = "women" if g == "Women" else "men" if g == "Men" else None
    out["understood"] = bool(out["platform"] or out["tier"] or out["country"] or out["city"] or
                             out["interest_words"] or out["hcp"] or out["a_gender"])
    return out
