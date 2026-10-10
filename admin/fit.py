"""Fit and campaign-role calls on a creator, and the suggestion for them.

A client reading a creator's analysis has to decide for themselves whether
the creator suits the campaign. The admin makes that call once, per creator in
a selection, with ready-made words: how well they fit, and the part they play
(awareness, engagement, conversion, UGC). `suggest` proposes both and shows
its working, so the admin confirms or changes it rather than starting from
nothing. It weighs, for the campaign's objective:

  - the creator's analysis of the platform, against the benchmark ranges in
    Settings (engagement by follower band, fake followers),
  - how much of the audience is in our market (KSA),
  - their reach,
  - and our own record with them: past campaigns, against what our creators
    usually deliver.

Nothing reaches a client until the admin saves, and every field stays editable.
"""

import re

FITS = ["Strong fit", "Good fit", "Possible fit", "Not recommended"]
ROLES = ["Awareness", "Engagement", "Conversion", "UGC content"]
OBJECTIVES = ["Balanced", "Awareness", "Engagement", "Conversion"]
MARKET = "SA"                                 # the audience that matters for most of our work
MARKET_NAME = "KSA"

# How much each thing counts for each objective. Higher = matters more.
WEIGHTS = {
    "Balanced":   {"engagement": 1.5, "credibility": 1.5, "market": 1.5, "reach": 1.5, "record": 1.5},
    "Awareness":  {"engagement": 1.0, "credibility": 1.0, "market": 1.0, "reach": 3.0, "record": 1.0},
    "Engagement": {"engagement": 3.0, "credibility": 1.0, "market": 1.0, "reach": 0.5, "record": 1.0},
    "Conversion": {"engagement": 2.0, "credibility": 2.0, "market": 3.0, "reach": 0.5, "record": 2.0},
}
# The objective names campaigns use -> the ones shown here.
FROM_CAMPAIGN = {"balanced": "Balanced", "awareness": "Awareness", "engagement": "Engagement", "traffic": "Conversion"}


# More than one goal (fix batch 3: the selection objective takes several, e.g. awareness AND
# engagement). Stored as "Awareness+Engagement"; scored with the average of those goals'
# weights, so each one counts and none is dropped. "Balanced" alongside others adds nothing.
def objective_of(goals):
    """A list of goal names (Awareness, Engagement, Conversion, Balanced) -> one stored objective."""
    names = [g for g in dict.fromkeys(goals or []) if g in OBJECTIVES]
    named = [g for g in OBJECTIVES if g in names and g != "Balanced"]
    if not named:
        return "Balanced"
    return "+".join(named)


def parts_of(objective):
    """'Awareness+Engagement' -> ['Awareness', 'Engagement']; anything unknown -> ['Balanced']."""
    names = [p for p in str(objective or "").split("+") if p in OBJECTIVES]
    return names or ["Balanced"]


def known_objective(objective):
    """True for one of OBJECTIVES or a "+" combination of them."""
    return bool(objective) and all(p in OBJECTIVES for p in str(objective).split("+"))


def blend(table, objective):
    """The weights for an objective from ``table`` (WEIGHTS or WEIGHTS_BASIC), averaged over its goals."""
    parts = parts_of(objective)
    keys = table["Balanced"].keys()
    return {k: sum(table[p][k] for p in parts) / float(len(parts)) for k in keys}


def objective_label(objective):
    """How a (combined) objective reads: 'Awareness + Engagement'."""
    return " + ".join(parts_of(objective))


def _pct(v):
    return ("%g" % round(v, 1)) + "%"


def _k(n):
    n = float(n)
    return ("%gM" % round(n / 1e6, 1)) if n >= 1e6 else ("%gK" % round(n / 1e3, 1)) if n >= 1e3 else "%d" % n


def clean(fit, roles, reason):
    """What the admin typed, kept to the ready-made words."""
    fit = fit if fit in FITS else ""
    roles = [r for r in ROLES if r in (roles or [])]
    reason = " ".join(str(reason or "").split())[:160]
    return {"fit": fit, "roles": roles, "reason": reason} if (fit or roles or reason) else None


def suggest(doc, platform, followers=None, objective="Balanced", band="mid", bench=None, record=None):
    """{"fit", "roles", "reason", "evidence", "checks"} from one platform's
    analysis, or {"note": ...} when there is nothing to go on.

    `bench` is the benchmark library, `band` the creator's follower band and
    `record` our own history with them ({"campaigns", "posts", "er", "typical_er"}),
    all supplied by the caller so this stays plain arithmetic."""
    if not doc:
        return {"note": "No %s analysis on file yet — nothing to suggest from." % (platform or "platform")}
    bench = bench or {}
    objective = objective if known_objective(objective) else "Balanced"
    w = blend(WEIGHTS, objective)
    f = doc.get("followers") or followers
    er = doc.get("er")
    fake = doc.get("fake_followers_pct")
    if fake is None and doc.get("credibility_pct") is not None:
        fake = round(100 - doc["credibility_pct"], 1)
    countries = (doc.get("audience") or {}).get("countries") or []
    home = next((c.get("pct") for c in countries if str(c.get("code", "")).upper() == MARKET), None)
    if home is None and countries:
        home = 0

    # engagement: a feed platform is judged by its follower band, video platforms by the video range
    bars = (bench.get("er") or {}).get(band) if platform in (None, "Instagram", "Facebook", "X") else bench.get("video_er")
    good, ok = bars if bars else ((3.0, 1.5) if platform in (None, "Instagram") else (6.0, 3.0))
    what = ("%s creators" % band) if platform in (None, "Instagram", "Facebook", "X") else "%s video" % (platform or "")
    fk_good, fk_bad = bench.get("fake_followers") or (15.0, 30.0)

    scores, checks, evidence = {}, [], []     # scores are -1 .. +1; absent = no data
    if er is not None:
        s = 1 if er >= good else 0 if er >= ok else -1
        scores["engagement"] = s
        word = "above" if s > 0 else "within range of" if s == 0 else "below"
        evidence.append("Engagement %s — %s the %s benchmark for %s" % (_pct(er), word, _pct(good if s > 0 else ok), what))
        checks.append({"label": "Engagement", "value": _pct(er), "bench": "good ≥ %s, ok ≥ %s" % (_pct(good), _pct(ok)), "grade": s})
    if fake is not None:
        s = 1 if fake <= fk_good else -1 if fake >= fk_bad else 0
        scores["credibility"] = s
        evidence.append(("Only %s fake followers" % _pct(fake)) if s > 0 else
                        ("%s fake followers — high" % _pct(fake)) if s < 0 else ("%s fake followers" % _pct(fake)))
        checks.append({"label": "Fake followers", "value": _pct(fake), "bench": "good ≤ %s, bad ≥ %s" % (_pct(fk_good), _pct(fk_bad)), "grade": s})
    if home is not None:
        s = 1 if home >= 60 else -1 if home < 30 else 0
        scores["market"] = s
        evidence.append("%s of the audience is in %s" % (_pct(home), MARKET_NAME))
        checks.append({"label": "Audience in " + MARKET_NAME, "value": _pct(home), "bench": "good ≥ 60%, low < 30%", "grade": s})
    if f:
        s = 1 if f >= 200000 else -1 if f < 30000 else 0
        scores["reach"] = s
        checks.append({"label": "Followers", "value": _k(f), "bench": "wide ≥ 200K, small < 30K", "grade": s})
        if s > 0:
            evidence.append("Reach: %s followers" % _k(f))
    if record and record.get("posts", 0) >= 2 and record.get("er") is not None and record.get("typical_er"):
        ratio = record["er"] / record["typical_er"]
        s = 1 if ratio >= 1.2 else -1 if ratio <= 0.7 else 0
        scores["record"] = s
        evidence.append("Our record: %d posts in %d campaign%s, %s engagement per view (our typical %s)" % (
            record["posts"], record["campaigns"], "" if record["campaigns"] == 1 else "s", _pct(record["er"]), _pct(record["typical_er"])))
        checks.append({"label": "Our past campaigns", "value": _pct(record["er"]), "bench": "our typical %s" % _pct(record["typical_er"]), "grade": s})

    # roles come from what the numbers show, whatever the objective
    roles = []
    local_ok = home is None or home >= 50
    real_ok = fake is None or fake <= fk_bad * 0.67
    if scores.get("reach") == 1:
        roles.append("Awareness")
    if scores.get("engagement") == 1:
        roles.append("Engagement")
        if (not f or f <= 500000) and local_ok and real_ok:
            roles.append("Conversion")
    elif scores.get("engagement") == 0 and local_ok and real_ok and home is not None and home >= 60 and (not f or f <= 200000):
        roles.append("Conversion")

    used = {k: v for k, v in scores.items() if w.get(k)}
    total_w = sum(w[k] for k in used)
    index = sum(w[k] * v for k, v in used.items()) / total_w if total_w else 0.0
    out = {"checks": checks, "objective": objective, "roles": roles}
    if len(used) < 2:
        out.update({"fit": "", "reason": " · ".join(evidence[:3]), "evidence": evidence,
                    "note": "Not enough numbers in this analysis to suggest a fit; roles are from what is there."})
        return out
    if fake is not None and fake >= fk_bad:
        fit = "Not recommended"
    else:
        fit = "Strong fit" if index >= 0.55 else "Good fit" if index >= 0.25 else "Possible fit" if index >= -0.1 else "Not recommended"
    # the line the client reads: what matters most for this objective, first
    order = sorted((k for k in used), key=lambda k: -w[k])
    line = [e for k in order for e in evidence if _belongs(e, k)]
    out.update({"fit": fit, "reason": ("For %s: " % objective_label(objective).lower() if objective != "Balanced" else "") + " · ".join(line[:3]),
                "evidence": evidence})
    out["reason"] = out["reason"][:160]
    return out


def _belongs(sentence, key):
    s = sentence.lower()
    return {"engagement": s.startswith("engagement"), "credibility": "fake" in s,
            "market": "audience is in" in s, "reach": s.startswith("reach"), "record": s.startswith("our record")}[key]


# ------------------------------------------------------------ matching score --
#
# One number per creator for one selection: how well they fit what the
# selection is for (its objective and its target audience). It is worked out
# live from the creator's analysis and never stored, so it cannot go stale;
# whatever the admin types by hand (fit tag, reason) sits on top of it.

SCORE_BANDS = [(80, "Strong fit"), (60, "Good fit"), (40, "Possible fit"), (0, "Not recommended")]
COUNTRIES = [("SA", "Saudi Arabia"), ("AE", "UAE"), ("EG", "Egypt"), ("KW", "Kuwait"), ("QA", "Qatar"), ("BH", "Bahrain"),
             ("OM", "Oman"), ("JO", "Jordan"), ("LB", "Lebanon"), ("IQ", "Iraq"), ("MA", "Morocco")]
AGE_BANDS = ["13-17", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
GENDERS = ["Any", "Women", "Men"]
DEFAULT_TARGET = {"country": "SA", "gender": "Any", "age": "Any", "category": "Any"}
# What a category looks for in a creator's interests and audience interests.
CATEGORY_WORDS = {
    "beauty": ["beauty", "cosmetic", "skin", "makeup", "hair", "fragrance", "personal care", "nail"],
    "health": ["health", "medical", "wellness", "fitness", "nutrition", "pharma", "doctor", "diet", "vitamin", "supplement"],
    "mother & baby": ["baby", "mother", "child", "kids", "family", "parent", "toys"],
    "food": ["food", "restaurant", "cooking", "recipe", "drink", "coffee", "cafe"],
    "lifestyle": ["lifestyle", "fashion", "shopping", "travel", "home", "friends"],
    "fashion": ["fashion", "clothes", "shoes", "accessor", "style", "shopping"],
    "technology": ["tech", "gadget", "electronic", "gaming", "software", "phone"],
    "automotive": ["car", "auto", "vehicle", "motor"],
    "travel": ["travel", "tourism", "hotel", "holiday"],
    "fitness": ["fitness", "sport", "gym", "health", "wellness"],
    "skincare": ["skin", "beauty", "cosmetic", "derma", "care"],
    "hair care": ["hair", "beauty", "salon", "care"],
    "make-up": ["makeup", "make-up", "beauty", "cosmetic"],
    "fragrance": ["fragrance", "perfume", "beauty"],
    "health care": ["health", "medical", "doctor", "pharma", "wellness", "nutrition", "vitamin", "supplement"],
    "motherhood": ["baby", "mother", "child", "kids", "family", "parent", "toys"],
    "sports": ["sport", "fitness", "gym", "football"],
    "gaming": ["gaming", "game", "esport"],
    "finance": ["finance", "bank", "invest", "money", "business"],
    "tv podcasting": ["podcast", "tv", "show", "entertain", "media"],
}


def band_for(score):
    return next(name for lo, name in SCORE_BANDS if score >= lo)


def _clamp(x):
    return max(0.0, min(1.0, x))


def _age_share(ages, wanted):
    """Share of the audience in an age band, adding up the report's bands that overlap it."""
    def span(name):
        n = str(name).replace("+", "-99")
        lo, _, hi = n.partition("-")
        try:
            return int(lo), int(hi or lo)
        except ValueError:
            return None
    w = span(wanted)
    if not w:
        return None
    total = 0.0
    for a in ages or []:
        s = span(a.get("name", ""))
        if s and s[0] <= w[1] and s[1] >= w[0]:
            total += a.get("pct") or 0
    return total


def has_word(text, word):
    """``word`` appears in ``text`` as a word or a word's start. Short words must be whole words
    (plural allowed): "car" is in "cars" and "car care", not in "skincare"; "cosmetic" still
    finds "cosmetics"."""
    word = word.lower()
    if len(word) <= 4:
        return re.search(r"(?<![a-z])" + re.escape(word) + r"s?(?![a-z])", text) is not None
    return re.search(r"(?<![a-z])" + re.escape(word), text) is not None


def _niche(category, doc, creator_interest):
    """1.0 when the creator's own category or their audience's interests name the category, else 0.25."""
    cats = [c.strip().lower() for c in str(category or "").split("|") if c.strip() and c.strip().lower() != "any"]
    if not cats:
        return None
    pool = [str(creator_interest or "").lower()]
    pool += [str(x).lower() for x in (doc.get("creator_interests") or [])]
    pool += [str(i.get("name", "")).lower() for i in (doc.get("audience") or {}).get("interests") or []]
    pool += [str(i.get("name", "")).lower() for i in (doc.get("audience") or {}).get("brand_affinity") or []]
    for cat in cats:
        words = CATEGORY_WORDS.get(cat) or [w for w in cat.replace("&", " ").split() if len(w) >= 4] or [cat]
        if cat in str(creator_interest or "").lower() or any(has_word(p, w) for p in pool for w in words):
            return 1.0
    return 0.25


def score(doc, platform, followers=None, objective="Balanced", target=None, band="mid", bench=None,
          record=None, creator_interest=None, min_parts=3, creator=None):
    """The matching score for one creator. Everyone is scored on the SAME parameters, whatever
    data they have (see score_core); a full analysis adds verified checks beside the number."""
    if not doc:
        return {"score": None, "tag": "", "parts": [], "strengths": [], "watchouts": [], "conclusion": "",
                "objective": objective, "platform": platform, "note": "No analysis on file.", "checks": []}
    return score_core(doc, platform, followers, objective, target, band, bench, creator, record, min_parts)


# ------------------------------------------------- scoring on basic (public) data --
#
# Most creators have only the public numbers (followers, engagement, average
# likes and comments, views on TikTok, bio, hashtags) and no audience report.
# They are scored on what that record can show, and the stamp says so. Real
# audience (fake followers) cannot be judged from it and is left out; audience
# match is estimated from the roster (city, nationality, interest) and the bio
# and hashtags instead of a measured audience split.

ASSUMED_AUDIENCE = 0.8           # no measured audience: assume a good match (80%)...
# ...but every part's weight is scaled by how far its data can be trusted, so a guess
# can only nudge the score: measured 1.0, worked out from other numbers 0.5, assumed 0.2.
TRUST = {"measured": 1.0, "estimated": 0.5, "assumed": 0.2}
WEIGHTS_BASIC = {
    "Balanced":   {"engagement": 1.5, "reach": 1.5, "views": 1.5, "market": 1.5},
    "Awareness":  {"engagement": 1.0, "reach": 3.0, "views": 3.0, "market": 1.0},
    "Engagement": {"engagement": 3.0, "reach": 0.5, "views": 1.0, "market": 1.0},
    "Conversion": {"engagement": 2.0, "reach": 0.5, "views": 2.0, "market": 3.0},
}
PLACE_WORDS = {
    "SA": ["riyadh", "jeddah", "jedda", "dammam", "khobar", "al khobar", "dhahran", "taif", "makkah", "mecca", "madinah", "medina",
           "abha", "tabuk", "jazan", "jizan", "hail", "qassim", "buraidah", "al ahsa", "hofuf", "jubail", "yanbu", "ksa",
           "saudi", "saudi arabia", "saudia"],
    "AE": ["dubai", "abu dhabi", "sharjah", "ajman", "al ain", "ras al khaimah", "fujairah", "uae", "emirates", "emirati"],
    "EG": ["cairo", "giza", "alexandria", "mansora", "mansoura", "port said", "boursaeed", "tanta", "zagazig", "egypt", "egyptian",
           "nasr city", "maadi", "heliopolis", "new cairo", "6th of october", "october", "sheikh zayed", "dokki", "mohandessin",
           "zamalek", "ismailia", "suez", "aswan", "luxor", "hurghada", "sharm", "fayoum", "minya", "assiut", "sohag", "damietta"],
    "KW": ["kuwait", "kuwaiti"], "QA": ["qatar", "doha", "qatari"], "BH": ["bahrain", "manama", "bahraini"],
    "OM": ["oman", "muscat", "omani"], "JO": ["jordan", "amman", "jordanian"], "LB": ["lebanon", "beirut", "lebanese"],
    "IQ": ["iraq", "baghdad", "erbil", "iraqi"], "MA": ["morocco", "casablanca", "rabat", "marrakech", "moroccan"],
}


def _place_mark(creator, target_cc):
    """1.0 when the roster places the creator in the target country, 0.2 when it places them
    elsewhere, 0.5 when it says nothing useful."""
    def tokens(text):
        t = str(text or "").lower()
        return [x.strip() for x in re.split(r"[,/|;&+]|\band\b", t) if x.strip()]
    hits = set()
    for raw in tokens(creator["city"] if creator is not None else "") + tokens(creator["nationality"] if creator is not None else ""):
        for cc, words in PLACE_WORDS.items():
            if raw in words or any(w == raw or (len(w) > 4 and w in raw) for w in words):
                hits.add(cc)
    if not hits:
        return 0.5, None
    return (1.0 if target_cc in hits else 0.2), hits


def typical_views(doc):
    """(views, "median" | "estimated") for a typical video, or (None, None). The real median when it
    was collected; otherwise the mean of the sampled videos after dropping the 6 best, worked out from
    the average and the best six we kept. An average alone is inflated by viral videos."""
    if doc.get("median_views"):
        return float(doc["median_views"]), "median"
    n = doc.get("sample_posts") or 0
    avg = doc.get("avg_views")
    top = [p.get("views") for p in (doc.get("top_posts") or []) if p.get("views")]
    if avg and n >= 12 and len(top) >= 6:
        tail = (n * float(avg) - sum(top[:6])) / (n - 6)
        if tail > 0:
            return tail, "estimated"
    return None, None


def score_core(doc, platform, followers=None, objective="Balanced", target=None, band="mid", bench=None,
               creator=None, record=None, min_parts=3):
    """The one scoring formula, used for every creator. It needs only what a public profile shows
    (engagement, reach, views, and an audience estimate from the roster and the bio). When the
    creator also has a full analysis, `checks` carries what it adds (fake followers, the measured
    audience, our own record) as warnings beside the number; the only thing that moves the number
    is a bought audience, which caps it."""
    verified = not doc.get("basic")
    out = {"score": None, "tag": "", "parts": [], "strengths": [], "watchouts": [], "conclusion": "",
           "objective": objective, "platform": platform, "basic": not verified, "checks": []}
    bench = bench or {}
    target = dict(DEFAULT_TARGET, **{k: v for k, v in (target or {}).items() if v})
    objective = objective if known_objective(objective) else "Balanced"
    w = blend(WEIGHTS_BASIC, objective)
    f = doc.get("followers") or followers
    er = doc.get("er")
    feed = platform in (None, "Instagram", "Facebook", "X")
    views_in = doc.get("avg_views")
    if doc.get("er_basis") == "views":
        video = True                                  # a rate per view, as the collector measures it
    elif feed:
        video = False                                 # a rate per follower
    elif doc.get("er_note"):
        # a video account's rate the importer worked out from likes: per view if views are known
        if views_in:
            er = ((doc.get("avg_likes") or 0) + (doc.get("avg_comments") or 0)) / float(views_in) * 100
            video = True
        else:
            video = False
    else:
        video = True                                  # a TikTok/YouTube report's own rate is per view
    bars = bench.get("video_er") if video else (bench.get("er") or {}).get(band)
    good, ok = bars if bars else ((4.5, 3.0) if video else (3.0, 1.5))
    parts = []
    wmul = {}

    def add(key, label, s, strength, watch):
        parts.append((key, label, _clamp(s), strength, watch))

    if er is not None:
        s = 1.0 if er >= good else (0.6 + 0.4 * (er - ok) / (good - ok) if er >= ok and good > ok else 0.6 * er / ok if ok else 0.0)
        est = bool(doc.get("er_note"))           # a rate the importer worked out: counts, but never as full marks
        if est:
            s = min(s, 0.7)
            wmul["engagement"] = TRUST["estimated"]
        lab = "Engagement about %s (estimated from average likes)" if est else "Engagement %s"
        add("engagement", "Engagement", s,
            (lab % _pct(er)) + (" per view" if video else "") + ", " + (("above the %s benchmark" % _pct(good)) if er >= good else ("within the healthy range (%s and over)" % _pct(ok))),
            (lab % _pct(er)) + (" per view" if video else "") + ", below the %s benchmark" % _pct(ok))
    if f:
        import math
        add("reach", "Reach", (math.log10(max(f, 1)) - 3.7) / 2.0, "Reach of %s followers" % _k(f), "Small reach (%s followers)" % _k(f))
    typ, how = typical_views(doc) if platform not in (None, "Instagram", "Facebook", "X") else (None, None)
    if typ:
        import math
        s = (math.log10(max(typ, 1)) - 3.0) / 2.0               # 1K -> 0, 10K -> 0.5, 100K -> 1
        tag = " (estimated)" if how == "estimated" else ""
        if how == "estimated":
            wmul["views"] = TRUST["estimated"]
        add("views", "Typical views", s, "A typical video gets about %s views%s" % (_k(typ), tag),
            "A typical video gets only about %s views%s" % (_k(typ), tag))
    # audience match, estimated from the roster and the profile text
    subs = []
    pm, hits = _place_mark(creator, target["country"])
    cname = dict(COUNTRIES).get(target["country"], target["country"])
    if hits:
        subs.append((pm, "Based in %s" % cname, "Based outside %s" % cname))
    cats = [c for c in str(target["category"]).split("|") if c.strip() and c.strip().lower() != "any"]
    if cats:
        text = " ".join(filter(None, [str(creator["interest"] if creator is not None else ""), str(doc.get("bio") or ""),
                                      " ".join(str((h.get("tag") if isinstance(h, dict) else h) or "") for h in (doc.get("hashtags") or []))]))
        fake_doc = {"creator_interests": [text], "audience": {}}
        nic = _niche("|".join(cats), fake_doc, creator["interest"] if creator is not None else "")
        names = ", ".join(c.strip().lower() for c in cats)
        subs.append((nic, "Works in the %s space" % names, "Little sign of %s content in their profile" % names))
    au = doc.get("audience") or {}
    measured = []
    if verified and (au.get("countries") or au.get("gender") or au.get("ages")):
        # a full analysis: the audience as it was measured
        if au.get("countries"):
            home = next((c.get("pct") for c in au["countries"] if str(c.get("code", "")).upper() == target["country"]), 0) or 0
            measured.append((home / 60.0, "%s of the audience is in %s" % (_pct(home), cname), "Only %s of the audience is in %s" % (_pct(home), cname)))
        if target["gender"] in ("Women", "Men") and au.get("gender"):
            share = au["gender"].get("female" if target["gender"] == "Women" else "male") or 0
            measured.append((share / 60.0, "%s of the audience are %s" % (_pct(share), target["gender"].lower()),
                             "Only %s of the audience are %s" % (_pct(share), target["gender"].lower())))
        if target["age"] != "Any" and au.get("ages"):
            share = _age_share(au["ages"], target["age"])
            if share is not None:
                measured.append((share / 40.0, "%s of the audience is aged %s" % (_pct(share), target["age"]),
                                 "Only %s of the audience is aged %s" % (_pct(share), target["age"])))
        if cats:
            nm = _niche("|".join(cats), doc, creator["interest"] if creator is not None else "")
            names = ", ".join(c.strip().lower() for c in cats)
            measured.append((nm, "Works in the %s space" % names, "Little sign of %s content or audience interest" % names))
    if measured:
        add("market", "Audience (measured)", sum(_clamp(x[0]) for x in measured) / len(measured),
            "; ".join(x[1] for x in measured if _clamp(x[0]) >= 0.75) or None, "; ".join(x[2] for x in measured if _clamp(x[0]) <= 0.45) or None)
    else:
        # no audience report: assume a good match rather than guess from the roster
        wmul["market"] = TRUST["assumed"]
        add("market", "Audience (assumed 80%)", ASSUMED_AUDIENCE, None, None)

    def wt(k):
        return w.get(k, 1.0) * wmul.get(k, 1.0)

    out["parts"] = [{"key": k, "label": lab, "s": round(s, 2), "w": round(wt(k), 2)} for k, lab, s, _, _ in parts]
    if len(parts) < min_parts:
        out["note"] = "Not enough public data to score."
        return out
    tw = sum(wt(k) for k, _, _, _, _ in parts)
    val = int(round(100.0 * sum(wt(k) * s for k, _, s, _, _ in parts) / tw))
    extra_watch = []
    if verified:
        au = doc.get("audience") or {}
        countries = au.get("countries") or []
        if countries:
            home = next((c.get("pct") for c in countries if str(c.get("code", "")).upper() == target["country"]), 0) or 0
            cn = dict(COUNTRIES).get(target["country"], target["country"])
            out["checks"].append({"label": "Measured audience", "text": "%s of the measured audience is in %s" % (_pct(home), cn),
                                  "level": "ok" if home >= 60 else "warn" if home >= 30 else "bad"})
        if target["gender"] in ("Women", "Men") and au.get("gender"):
            share = au["gender"].get("female" if target["gender"] == "Women" else "male") or 0
            out["checks"].append({"label": "Gender", "text": "%s of the audience are %s" % (_pct(share), target["gender"].lower()),
                                  "level": "ok" if share >= 60 else "warn" if share >= 40 else "bad"})
        if target["age"] != "Any" and au.get("ages"):
            share = _age_share(au["ages"], target["age"])
            if share is not None:
                out["checks"].append({"label": "Age", "text": "%s of the audience is aged %s" % (_pct(share), target["age"]),
                                      "level": "ok" if share >= 40 else "warn" if share >= 20 else "bad"})
        if record and record.get("posts", 0) >= 2 and record.get("er") is not None and record.get("typical_er"):
            r = record["er"] / record["typical_er"]
            out["checks"].append({"label": "Our campaigns", "text": "%s engagement per view in %d of our campaign%s (typical %s)" % (
                _pct(record["er"]), record["campaigns"], "" if record["campaigns"] == 1 else "s", _pct(record["typical_er"])),
                "level": "ok" if r >= 1.2 else "bad" if r <= 0.7 else "warn"})
    out["score"], out["tag"] = val, band_for(val)
    order = sorted(parts, key=lambda p: -wt(p[0]))
    out["strengths"] = [st for _, _, s, st, _ in order if st and s >= 0.75][:4]
    out["watchouts"] = extra_watch + [wo for _, _, s, _, wo in order if wo and s <= 0.45][:3 - len(extra_watch)]
    lead = "" if objective == "Balanced" else " for " + objective_label(objective).lower()
    txt = "%s%s (%d/100)%s." % (out["tag"], lead, val, ", from public numbers only" if not verified else "")
    if out["strengths"]:
        txt += " Strengths: " + "; ".join(out["strengths"][:2]) + "."
    if out["watchouts"]:
        txt += " Watch: " + "; ".join(out["watchouts"][:2]) + "."
    out["conclusion"] = txt
    out["objective"] = objective
    return out
