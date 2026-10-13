"""Fit and campaign-role calls on a creator, and the suggestion for them.

A client reading a creator's analysis has to decide for themselves whether
the creator suits the campaign. The admin makes that call once, per creator in
a selection, with ready-made words: how well they fit, and the part they play
(awareness, engagement, UGC content). `suggest` proposes both and shows
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

FITS = ["Strong fit", "Good fit", "Possible fit", "Not recommended", "Matching"]   # Matching: a plain editorial tag, no score
ROLES = ["Awareness", "Engagement", "Conversion", "UGC content"]
# Campaign types (owner decision 2026-10-10): Awareness, Engagement and Traffic, one or several at
# once. "Conversion" is no longer offered; a stored "Conversion" reads as Traffic (the link-click
# goal) and a stored "Balanced" reads as an equal blend of the three.
OBJECTIVES = ["Balanced", "Awareness", "Engagement", "Traffic"]
CAMPAIGN_TYPES = ["Awareness", "Engagement", "Traffic"]
LEGACY_OBJECTIVE = {"Conversion": "Traffic"}
# How much each thing counts for each type. Higher = matters more. (Used by `suggest`, the
# admin's fit suggestion; the number on a creator card comes from WEIGHTS_V2 below.)
WEIGHTS = {
    "Awareness":  {"engagement": 1.0, "credibility": 1.0, "market": 1.0, "reach": 3.0, "record": 1.0},
    "Engagement": {"engagement": 3.0, "credibility": 1.0, "market": 1.0, "reach": 0.5, "record": 1.0},
    # link clicks come from an engaged audience in the right market, with enough reach for the
    # clicks to add up; our own campaign record shows who drives them.
    "Traffic":    {"engagement": 2.5, "credibility": 1.5, "market": 2.0, "reach": 1.0, "record": 2.0},
}
# The objective names campaigns use -> the ones shown here.
FROM_CAMPAIGN = {"balanced": "Balanced", "awareness": "Awareness", "engagement": "Engagement", "traffic": "Traffic",
                 "conversion": "Traffic"}


# More than one goal (fix batch 3: the selection objective takes several, e.g. awareness AND
# engagement). Stored as "Awareness+Engagement"; scored with the average of those goals'
# weights, so each one counts and none is dropped.
def _norm(name):
    return LEGACY_OBJECTIVE.get(name, name)


def objective_of(goals):
    """A list of goal names (Awareness, Engagement, Traffic; Balanced and the old Conversion are
    still read) -> one stored objective: "Awareness+Traffic". Nothing named = "Balanced"."""
    names = [_norm(g) for g in dict.fromkeys(goals or [])]
    named = [g for g in CAMPAIGN_TYPES if g in names]
    if not named:
        return "Balanced"
    return "+".join(named)


def parts_of(objective):
    """'Awareness+Engagement' -> ['Awareness', 'Engagement']; the old 'Conversion' -> ['Traffic'];
    'Balanced' (or anything unknown) -> ['Balanced'], which blend() reads as the three together."""
    names = [_norm(p) for p in str(objective or "").split("+")]
    names = [p for p in dict.fromkeys(names) if p in CAMPAIGN_TYPES]
    return names or ["Balanced"]


def canonical(objective):
    """The stored form of an objective: legacy Conversion read as Traffic, order fixed, unknown = Balanced."""
    parts = parts_of(objective)
    return "Balanced" if parts == ["Balanced"] else "+".join(parts)


def known_objective(objective):
    """True for one of OBJECTIVES, the legacy Conversion, or a "+" combination of them."""
    return bool(objective) and all(_norm(p) in OBJECTIVES for p in str(objective).split("+"))


def blend(table, objective):
    """The weights for an objective from ``table`` (WEIGHTS or WEIGHTS_V2), averaged over its
    goals. Balanced is the average of all three."""
    parts = parts_of(objective)
    if parts == ["Balanced"]:
        parts = CAMPAIGN_TYPES
    keys = table["Awareness"].keys()
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
    objective = canonical(objective) if known_objective(objective) else "Balanced"
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


def target_list(v):
    """The values of a target field that may hold several ("SA|AE", "18-24|25-34", or a list) as
    a list. "Any", empty and None give []. One value is a list of one: old selections hold one."""
    parts = v if isinstance(v, (list, tuple)) else str(v or "").split("|")
    out = [str(p).strip() for p in parts if str(p).strip() and str(p).strip().lower() != "any"]
    return list(dict.fromkeys(out))


def one_gender(v):
    """The audience gender as one value: "Women" and "Men" together mean everyone."""
    g = target_list(v)
    return g[0] if len(g) == 1 and g[0] in ("Women", "Men") else "Any"


def _join_words(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else ""


def country_names(v):
    """"Saudi Arabia and UAE" for "SA|AE"."""
    return _join_words([dict(COUNTRIES).get(c, c) for c in target_list(v)] or [dict(COUNTRIES).get(DEFAULT_TARGET["country"])])


def age_text(v):
    """"18-24 and 25-34" for "18-24|25-34"."""
    return _join_words(target_list(v))


def age_need(n):
    """The share of the audience that counts as a full match for ``n`` age bands: 40% for one band,
    20 points more for each extra band (a wider age range holds more of the audience), up to 80%."""
    return 40.0 if n <= 1 else min(40.0 + 20.0 * (n - 1), 80.0)


def _age_share(ages, wanted):
    """Share of the audience in the wanted age band(s), adding up the report's bands that overlap
    any of them (each report band counted once)."""
    def span(name):
        n = str(name).replace("+", "-99")
        lo, _, hi = n.partition("-")
        try:
            return int(lo), int(hi or lo)
        except ValueError:
            return None
    ws = [w for w in (span(x) for x in target_list(wanted)) if w]
    if not ws:
        return None
    total = 0.0
    for a in ages or []:
        s = span(a.get("name", ""))
        if s and any(s[0] <= w[1] and s[1] >= w[0] for w in ws):
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
          record=None, creator_interest=None, min_parts=1, creator=None):
    """The matching score for one creator. Everyone is scored on the SAME parameters, whatever
    data they have (see score_core); a full analysis adds verified checks beside the number."""
    if not doc:
        return {"score": None, "tag": "", "parts": [], "strengths": [], "watchouts": [], "conclusion": "",
                "objective": objective, "platform": platform, "note": "No analysis on file.", "checks": [],
                "confidence": {"level": "low", "posts": 0, "peers_n": 0, "source": "peers"},
                "reach_followers": followers or None, "limited_data": True}
    return score_core(doc, platform, followers, objective, target, band, bench, creator, record, min_parts)


# ------------------------------------------------------- scoring, version 2 --
#
# Fix batch 6 (Bido, 2026-10-10). A creator is scored against creators of the SAME
# PLATFORM and the SAME SIZE from our own roster (benchmarks.py), on four things only:
#
#   engagement   how well their audience reacts      (percentile among same-size peers)
#   views        how far a typical video travels     (median views / followers, vs peers)
#   consistency  how steady those views are          (lower swing is better; needs a series)
#   interest     how much of their content is in the brief's product space
#
# Size is not a part of the score: a nano and a mega creator who are both at the top of their
# own size score the same. The creator's reach is shown beside the score (reach_followers).
# Audience (country, gender, age) is not scored; a measured audience stays a check beside it.
# A bought audience caps the number, and our own record with the creator nudges it only
# once they have 5 or more posts with us.
#
# Where a peer cell holds fewer than benchmarks.MIN_PEERS creators the part falls back to the
# global estimate in Settings (and counts for half), or is left out; the score then says
# "limited data". Every part's weight is scaled by how far its data can be trusted, so an
# estimate can only nudge the score: measured 1.0, estimated 0.5, assumed 0.2.

TRUST = {"measured": 1.0, "estimated": 0.5, "assumed": 0.2}
WEIGHTS_V2 = {
    "Awareness":  {"engagement": 1.5, "views": 3.0, "consistency": 1.0, "interest": 1.5},
    "Engagement": {"engagement": 3.0, "views": 1.0, "consistency": 1.0, "interest": 1.5},
    "Traffic":    {"engagement": 2.5, "views": 2.0, "consistency": 1.0, "interest": 2.0},
}   # Balanced = the average of the three rows; a stored Conversion reads as Traffic
WEIGHTS_BASIC = WEIGHTS_V2          # the name older code and tests use
RECORD_MIN_POSTS = 5                # our own campaign record moves the number from this many posts
RECORD_NUDGE = 5                    # points, up or down
FAKE_CAP = 39                       # a bought audience cannot score above "Not recommended"
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
    """1.0 when the roster places the creator in the target country (any of them, when several
    are asked for), 0.2 when it places them elsewhere, 0.5 when it says nothing useful."""
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
    return (1.0 if hits & set(target_list(target_cc) or [DEFAULT_TARGET["country"]]) else 0.2), hits


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




def _bar_score(v, good, ok):
    """A value against a global [good, ok] bar pair: 1 at good, 0.6 at ok, falling to 0."""
    if v >= good:
        return 1.0
    if v >= ok and good > ok:
        return 0.6 + 0.4 * (v - ok) / (good - ok)
    return 0.6 * v / ok if ok else 0.0


def _interest_words(cat):
    return CATEGORY_WORDS.get(cat) or [w for w in cat.replace("&", " ").split() if len(w) >= 4] or [cat]


def interest_share(doc, creator, cats):
    """(share 0..1, measured, why) of the creator's content that sits in the asked-for product
    space(s), or None when none is asked for.

    A future analysis field ``interest_shares`` ({category: percent}) is taken as measured.
    Until it exists the share is read from the keywords: the share of the creator's roster
    interest tags, and of their hashtags, that name the space; a bio that names it counts at
    least 0.3. That is an estimate and is weighted as one."""
    cats = [c.strip().lower() for c in (cats or []) if c and c.strip().lower() != "any"]
    if not cats:
        return None
    shares = doc.get("interest_shares")
    if isinstance(shares, dict) and shares:
        low = {str(k).lower(): v for k, v in shares.items() if isinstance(v, (int, float))}
        got = [low[c] for c in cats if c in low]
        if got:
            sh = min(1.0, sum(got) / 100.0)
            return sh, True, "%s of their content is %s" % (_pct(sum(got)), ", ".join(cats))

    def hit(text):
        t = str(text or "").lower()
        return any(c in t or any(has_word(t, w) for w in _interest_words(c)) for c in cats)
    interest = str(creator["interest"] if creator is not None and "interest" in creator.keys() else "")
    tags = [t.strip() for t in re.split(r"[,/|;&]|\band\b", interest) if t.strip()]
    tags += [str(x) for x in (doc.get("creator_interests") or [])]
    tag_share = (sum(1 for t in tags if hit(t)) / float(len(tags))) if tags else 0.0
    hashtags = [str((h.get("tag") if isinstance(h, dict) else h) or "") for h in (doc.get("hashtags") or [])]
    hash_share = (sum(1 for t in hashtags if hit(t)) / float(len(hashtags))) if len(hashtags) >= 3 else 0.0
    bio = 0.3 if hit(doc.get("bio")) else 0.0
    share = max(tag_share, hash_share, bio)
    return share, False, ("Content tagged for %s" % ", ".join(cats)) if share >= 0.5 else (
        "Some %s content" % ", ".join(cats) if share > 0 else "")


INTEREST_WEIGHT = 0.5      # the product-space match carries up to a third of the number (1 : 0.5 with engagement)
INTEREST_FULL_SHARE = 0.5  # the posts we hold are the base: half of them in the space is full marks


def post_interest(doc, creator, cats):
    """How much of what the creator actually posts sits in the brief's product space, read from
    the posts we hold, or None when the brief names no space.

    Returns {"lo", "hi" (score 0..1 at each end), "share_lo", "share_hi", "posts" (posts the
    reading rests on), "matched_lo", "matched_hi" (posts naming the space), "evidence" (0..1, how
    far to trust it), "src": doc|posts|keywords, "why", "watch"}.

    A measured ``interest_shares`` field wins. Otherwise the creator's hashtags are read: each
    carries the share of the analysed posts that used it, so the posts naming the space are
    between the busiest matching tag (nobody doubled up) and the sum of them (no post names two).
    The number of posts available is the base: 3 of 12 posts is 50 points, 6 of 12 (half) is 100.
    With no hashtags the roster interest tags and bio give a keyword estimate that
    counts at 0.3."""
    cats = [c.strip().lower() for c in (cats or []) if c and c.strip().lower() != "any"]
    if not cats:
        return None
    space = ", ".join(cats)
    n = int(doc.get("sample_posts") or 0)
    shares = doc.get("interest_shares")
    if isinstance(shares, dict) and shares:
        low = {str(k).lower(): v for k, v in shares.items() if isinstance(v, (int, float))}
        got = [low[c] for c in cats if c in low]
        if got:
            sh = min(1.0, sum(got) / 100.0)
            s = min(1.0, sh / INTEREST_FULL_SHARE)
            return {"lo": s, "hi": s, "share_lo": sh, "share_hi": sh, "posts": n, "matched_lo": None, "matched_hi": None,
                    "evidence": 1.0, "src": "doc", "why": "%s of their content is %s" % (_pct(sum(got)), space),
                    "watch": "Little %s content" % space}

    def hit(text):
        t = str(text or "").lower()
        return any(c in t or any(has_word(t, w) for w in _interest_words(c)) for c in cats)
    tags = [(str((h.get("tag") if isinstance(h, dict) else h) or ""), (h.get("count") if isinstance(h, dict) else None))
            for h in (doc.get("hashtags") or [])]
    tags = [(t, c) for t, c in tags if t.startswith("#") or c is not None]
    tags = [(t, c) for t, c in tags if not t.startswith("@")]
    if n >= 3 and tags and any(isinstance(c, (int, float)) for _, c in tags):
        def tag_hit(t):     # a hashtag is run-together words (#skincare), so a keyword may sit inside it
            t = t.lower().lstrip("#")
            return any(c in t or any(len(w) >= 4 and w in t for w in _interest_words(c)) for c in cats)
        pcts = [min(100.0, float(c)) for t, c in tags if isinstance(c, (int, float)) and tag_hit(t)]
        sh_lo = (max(pcts) / 100.0) if pcts else 0.0
        sh_hi = min(1.0, sum(pcts) / 100.0) if pcts else 0.0
        m_lo, m_hi = int(round(sh_lo * n)), int(round(sh_hi * n))
        s_lo, s_hi = min(1.0, sh_lo / INTEREST_FULL_SHARE), min(1.0, sh_hi / INTEREST_FULL_SHARE)
        ev = 1.0
        mt = "%d" % m_lo if m_lo == m_hi else "%d-%d" % (m_lo, m_hi)
        return {"lo": s_lo, "hi": s_hi, "share_lo": sh_lo, "share_hi": sh_hi, "posts": n, "matched_lo": m_lo, "matched_hi": m_hi,
                "evidence": ev, "src": "posts",
                "why": "%s of their %d analysed posts name %s" % (mt, n, space),
                "watch": "Only %s of their %d analysed posts name %s" % (mt, n, space)}
    got = interest_share(doc, creator, cats)
    sh = got[0] if got else 0.0
    s = min(1.0, sh / INTEREST_FULL_SHARE)
    return {"lo": s, "hi": s, "share_lo": sh, "share_hi": sh, "posts": n, "matched_lo": None, "matched_hi": None,
            "evidence": 0.3, "src": "keywords",
            "why": (got[2] if got and got[2] else "Works in the %s space" % space),
            "watch": "Little sign of %s content in what we hold (profile tags only)" % space}


def score_engine():
    """Which formula scores creators: "v5" (score_v5.py, 2026-10-13) or "v4" (score_model.py). Setting
    ``score_engine``; anything but "v4" reads as v5, so v4 is one setting away if v5 ever has to be backed out."""
    try:
        import db
        return "v4" if db.setting("score_engine") == "v4" else "v5"
    except Exception:
        return "v5"


def _v5_names(objective):
    """The goals scored: Balanced reads as the three together, like blend()."""
    parts = parts_of(objective)
    return CAMPAIGN_TYPES if parts == ["Balanced"] else parts


def _v5_run(doc, plat, f, objective):
    """score_v5 for one analysis doc. The audience and fake-follower checks stay with the checks below
    (they never move the number), so no target country goes in here."""
    import score_v5
    creator = {"platform": plat, "followers": f, "er_pct": doc.get("er"), "avg_likes": doc.get("avg_likes"),
               "avg_comments": doc.get("avg_comments"), "avg_views": doc.get("avg_views"),
               "avg_plays": doc.get("avg_reel_plays"), "fake_pct": doc.get("fake_followers_pct"),
               "recent_posts": doc.get("recent_posts")}
    return score_v5.score(creator, "+".join(_v5_names(objective)), None)


_V5_SOURCE = {"stored": "stored figure", "recent_posts": "worked out from recent posts", "unsupported": "rate only, nothing to verify it",
              "derived": "derived, rough"}


def _v5_row(label, e, unit):
    """(good text, bad text, hover row) for one scored v5 metric."""
    b = e["benchmark"]
    where = "%s the published %g-%g%% range" % (e["label"], b["low"], b["high"])
    shown = "%s%s" % (_pct(e["value"]), unit)
    src = _V5_SOURCE.get(e["source"], e["source"]) + (" (%s)" % e["note"] if e.get("note") and e["source"] == "recent_posts" else "")
    s = e["score"] / 100.0
    row = {"label": label, "value": "%s · %d%% of benchmark" % (shown, e["pct_of_benchmark"]),
           "note": "%s (%s tier) · %s · trust %d%%" % (where, b["band"], src, int(round(e["confidence"] * 100))),
           "level": "ok" if s >= 0.6 and e["source"] == "stored" else "warn" if s >= 0.3 or e["source"] != "stored" else "bad"}
    top = b["high"] or 0
    if top and e["value"] > top * 1.5:
        typical = "%.0f times the typical top of %g-%g%%" % (e["value"] / top, b["low"], b["high"])
    else:
        typical = "typical %g-%g%%" % (b["low"], b["high"])
    return "%s %s (%s)" % (label, shown, typical), "%s %s (%s)" % (label, shown, typical), row


def score_core(doc, platform, followers=None, objective="Balanced", target=None, band="mid", bench=None,
               creator=None, record=None, min_parts=1):
    """The one scoring formula, used for every creator (scoring v4, 2026-10-11).

    Four parameters read from the posts we hold (score_model.py): engagement, view rate, interest
    (posts naming the brief's space / posts available) and consistency of views. Each is scaled
    between two editable points and the campaign objective sets the weights (Awareness leans on
    view rate, Engagement on engagement, Traffic on interest). A parameter with no data hands its
    weight to the others. Audience, fake followers and our own record are shown as checks beside
    the number and never move it. The international benchmark is a reference line in the hover.

    Returns the same shape as before (score, tag, parts, strengths, watchouts, checks, conclusion,
    objective, platform, basic) plus ``metrics`` (the hover rows), ``confidence``,
    ``reach_followers``, ``limited_data`` and ``score_range`` / ``tag_range``."""
    import benchmarks
    import intl_benchmarks
    import score_model as sm
    verified = not doc.get("basic")
    out = {"score": None, "tag": "", "parts": [], "strengths": [], "watchouts": [], "conclusion": "",
           "objective": objective, "platform": platform, "basic": not verified, "checks": [],
           "confidence": {"level": "low", "posts": 0, "peers_n": 0, "source": "posts"},
           "reach_followers": None, "limited_data": True, "score_range": None, "tag_range": None}
    target = dict(DEFAULT_TARGET, **{k: v for k, v in (target or {}).items() if v})
    target["gender"] = one_gender(target["gender"])
    objective = canonical(objective) if known_objective(objective) else "Balanced"
    out["objective"] = objective
    f = doc.get("followers") or followers
    out["reach_followers"] = int(f) if f else None
    plat = platform or "Instagram"
    bench = bench or {}
    feed = plat in benchmarks.FEED
    group = "feed" if feed else "video"
    sample = benchmarks.sample_of(plat, dict(doc, followers=f)) if f else {}
    posts = int(doc.get("sample_posts") or (12 if verified else 0))
    unit_er = "" if feed and doc.get("er_basis") != "views" else " per view"

    # name -> (score 0..1 mid, lo, hi, text-good, text-bad, metric row)
    got = {}

    def put(key, s_lo, s_hi, good, bad, row):
        got[key] = {"lo": s_lo, "hi": s_hi, "mid": (s_lo + s_hi) / 2.0, "good": good, "bad": bad, "row": row}

    use_v5 = score_engine() == "v5"     # score_v5.py: engagement and view rate against published ranges, see its docstring

    # -- engagement
    er_val = sample.get("er_med") if sample.get("er_med") is not None else sample.get("er")
    er_bad = None
    if er_val is not None and er_val > sm.ENGAGEMENT_IMPLAUSIBLE:
        er_bad, er_val = er_val, None          # a bad scrape or hidden likes: shown, never scored
    if er_val is not None and not use_v5:
        (z, fl), bsrc, btier = sm.band_for("engagement", group, plat, f)
        s = sm.scale(er_val, z, fl)
        ref = intl_benchmarks.reference(plat, f)
        refnote = (" · international reference %s" % (("%g%%" % ref["low"]) if ref["high"] - ref["low"] < 0.05
                                                     else "%g-%g%%" % (ref["low"], ref["high"]))) if ref else ""
        put("engagement", s, s, "Engagement %s%s" % (_pct(er_val), unit_er), "Engagement %s%s" % (_pct(er_val), unit_er),
            {"label": "Engagement", "value": "%s%s" % (_pct(er_val), unit_er),
             "note": "scores 0 at %g%%, 100 at %g%%%s%s" % (z, fl, (" (%s tier, research)" % btier) if btier else "", refnote),
             "level": "ok" if s >= 0.6 else "warn" if s >= 0.3 else "bad"})

    # -- view rate
    vr = sample.get("view_rate_med") if sample.get("view_rate_med") is not None else sample.get("view_rate")
    if vr is not None and not use_v5:
        (z, fl), bsrc, btier = sm.band_for("view_rate", group, plat, f)
        s = sm.scale(vr, z, fl)
        put("view_rate", s, s, "A typical post reaches %s of followers" % _pct(vr),
            "A typical post reaches only %s of followers" % _pct(vr),
            {"label": "View rate", "value": "%s of followers" % _pct(vr), "note": "median views / followers; 0 at %g%%, 100 at %g%%%s" % (z, fl, (" (%s tier, research)" % btier) if btier else ""),
             "level": "ok" if s >= 0.6 else "warn" if s >= 0.3 else "bad"})

    # -- consistency (needs the spread of at least 10 posts)
    spread = sample.get("spread")
    if spread is not None and posts >= 10 and not use_v5:
        z, fl = sm.band("consistency", group)
        s = sm.scale(spread, z, fl)
        put("consistency", s, s, "Views hold steady from post to post", "Views swing a lot from post to post",
            {"label": "Consistency", "value": "swing %.2f" % spread, "note": "std / mean of views; 100 at %g or less, 0 at %g or more" % (fl, z),
             "level": "ok" if s >= 0.6 else "warn" if s >= 0.3 else "bad"})

    # -- interest: the posts we hold are the 100%
    cats = [c for c in str(target["category"]).split("|") if c.strip() and c.strip().lower() != "any"]
    pi = post_interest(doc, creator, cats) if sm.interest_on() and not use_v5 else None
    if pi is not None:
        space = ", ".join(c.lower() for c in cats)
        if pi["src"] == "posts":
            mt = "%d" % pi["matched_lo"] if pi["matched_lo"] == pi["matched_hi"] else "%d-%d" % (pi["matched_lo"], pi["matched_hi"])
            val_t, note_t = "%s of %d posts" % (mt, pi["posts"]), "name %s; the posts we hold are the 100%%" % space
        elif pi["src"] == "doc":
            val_t, note_t = _pct(100 * pi["share_lo"]) + " of content", "measured in the analysis"
        else:
            val_t = ("~%s of tags" % _pct(100 * pi["share_lo"])) if pi["share_lo"] else "no match"
            note_t = "profile tags only, no post data (counts at 30%)"
        i_mid = (pi["lo"] + pi["hi"]) / 2.0
        put("interest", pi["lo"], pi["hi"], pi["why"], pi["watch"],
            {"label": "Interest", "value": val_t, "note": note_t, "level": "ok" if i_mid >= 0.6 else "warn" if i_mid >= 0.3 else "bad"})
        got["interest"]["ev"] = pi["evidence"]
        got["interest"]["src"] = pi["src"]
        got["interest"]["n"] = pi["posts"]

    if er_bad is not None and not use_v5:
        out.setdefault("_flags", []).append({"label": "Engagement", "value": "%s%s" % (_pct(er_bad), unit_er),
                                              "note": "looks wrong for %s, left out of the score: verify the handle" % plat, "level": "bad"})
    v5r = None
    if use_v5:
        v5r = _v5_run(doc, plat, f, objective)
        if v5r.get("unscored"):
            out["note"] = "%s Not scored." % v5r["reason"]
            out["metrics"] = [{"label": "Check by hand", "value": c["metric"].replace("_", " ") + " missing", "note": c["fix"], "level": "info"}
                              for c in v5r.get("check_manually", []) if c["scored"]]
            return out
        for k5, kfit, label, unit in (("engagement", "engagement", "Engagement", unit_er), ("reach", "view_rate", "View rate", " of followers")):
            e = v5r["metrics"].get(k5)
            if e:
                good, bad, row = _v5_row(label, e, unit)
                put(kfit, e["score"] / 100.0, e["score"] / 100.0, good, bad, row)
                got[kfit]["ev"] = e["confidence"]
    if not any(k in got for k in ("engagement", "view_rate", "consistency")):
        out["note"] = "No post numbers on file for %s, so it is not scored." % plat
        return out
    if len([k for k in got]) < max(min_parts, 1):
        out.setdefault("note", "Not enough public data to score.")
        return out

    # -- weights by the campaign objective, over what is available
    if use_v5:
        import score_v5
        v5w = score_v5.weights_for("+".join(_v5_names(objective)))
        w = {"engagement": v5w["engagement"], "view_rate": v5w["reach"], "interest": 0.0, "consistency": 0.0}
    else:
        table = sm.weights()
        w = blend(table, objective)
    ev = {k: (got[k].get("ev", 1.0)) for k in got}
    wt = {k: w[k] * ev[k] for k in got}
    tw = sum(wt.values())
    lo_v = sum(wt[k] * got[k]["lo"] for k in got) / tw
    hi_v = sum(wt[k] * got[k]["hi"] for k in got) / tw
    out["parts"] = [{"key": k, "label": sm.LABEL[k], "s": round(got[k]["mid"], 2), "w": round(100.0 * wt[k] / tw, 1),
                     "src": got[k].get("src", "posts"), "n": got[k].get("n", 0)} for k in sm.PARAMS if k in got]
    out["score_range"] = [int(round(100 * lo_v)), int(round(100 * hi_v))]
    val = int(round(100.0 * (lo_v + hi_v) / 2.0))
    for k in sm.PARAMS:
        if k in got:
            got[k]["row"]["note"] += " · weight %d%%" % int(round(100.0 * wt[k] / tw))

    # -- checks beside the number (never in it)
    au = doc.get("audience") or {}
    tcs = target_list(target["country"]) or [DEFAULT_TARGET["country"]]
    cname = country_names(tcs)
    extra_watch = []
    if verified:
        countries = au.get("countries") or []
        if countries:
            home = sum((c.get("pct") or 0) for c in countries if str(c.get("code", "")).upper() in tcs)
            out["checks"].append({"label": "Measured audience", "text": "%s of the measured audience is in %s" % (_pct(home), cname),
                                  "level": "ok" if home >= 60 else "warn" if home >= 30 else "bad"})
        if target["gender"] in ("Women", "Men") and au.get("gender"):
            share = au["gender"].get("female" if target["gender"] == "Women" else "male") or 0
            out["checks"].append({"label": "Gender", "text": "%s of the audience are %s" % (_pct(share), target["gender"].lower()),
                                  "level": "ok" if share >= 60 else "warn" if share >= 40 else "bad"})
        if target_list(target["age"]) and au.get("ages"):
            share = _age_share(au["ages"], target["age"])
            if share is not None:
                need = age_need(len(target_list(target["age"])))
                out["checks"].append({"label": "Age", "text": "%s of the audience is aged %s" % (_pct(share), age_text(target["age"])),
                                      "level": "ok" if share >= need else "warn" if share >= need / 2 else "bad"})
    fake = doc.get("fake_followers_pct")
    if fake is None and doc.get("credibility_pct") is not None:
        fake = round(100 - doc["credibility_pct"], 1)
    fk_good, fk_bad = bench.get("fake_followers") or (15.0, 30.0)
    if fake is not None:
        out["checks"].append({"label": "Fake followers", "text": "%s of followers look fake" % _pct(fake),
                              "level": "ok" if fake <= fk_good else "bad" if fake >= fk_bad else "warn"})
        if fake >= fk_bad:
            extra_watch.append("fake followers %s, not counted in this score" % _pct(fake))
    if record and record.get("posts", 0) >= 2 and record.get("er") is not None and record.get("typical_er"):
        r = record["er"] / record["typical_er"]
        out["checks"].append({"label": "Our campaigns", "text": "%s engagement per view in %d of our campaign%s (typical %s)" % (
            _pct(record["er"]), record["campaigns"], "" if record["campaigns"] == 1 else "s", _pct(record["typical_er"])),
            "level": "ok" if r >= 1.2 else "bad" if r <= 0.7 else "warn"})

    # -- confidence: how many posts the engagement figure rests on
    level = "low" if posts < 6 else "high" if posts >= 20 else "medium"
    out["confidence"] = {"level": level, "posts": posts, "peers_n": 0, "source": "posts"}
    out["limited_data"] = posts < 10 or bool(feed and ("view_rate" not in got or "engagement" not in got))
    if use_v5:
        out["confidence"] = {"level": v5r["confidence"].lower(), "posts": posts, "peers_n": 0, "source": "v5", "pct": v5r["confidence_pct"]}
        out["limited_data"] = v5r["confidence"] != "High" or bool(v5r["estimated"])

    # -- every metric behind the number, in the order the hover reads them
    metrics = [got[k]["row"] for k in sm.PARAMS if k in got] + out.pop("_flags", [])
    metrics.append({"label": "Posts analysed", "value": str(posts) if posts else "none on file",
                    "note": "the 100% base for the interest match" if posts else "score is from public numbers",
                    "level": "ok" if posts >= 20 else "warn" if posts >= 10 else "bad"})
    if out["reach_followers"]:
        metrics.append({"label": "Reach", "value": _k(out["reach_followers"]), "note": "followers on %s" % plat, "level": "info"})
    for c in out["checks"]:
        if c["label"] in ("Measured audience", "Gender", "Age", "Fake followers", "Our campaigns"):
            metrics.append({"label": c["label"], "value": c["text"], "note": "", "level": c["level"]})
    if use_v5:
        conf_level = "ok" if v5r["confidence"] == "High" else "warn" if v5r["confidence"] == "Medium" else "bad"
        est = [m.replace("_", " ") for m in v5r["estimated"]]
        metrics.append({"label": "Confidence", "value": "%s (%d%%)" % (v5r["confidence"], v5r["confidence_pct"]),
                        "note": "how much of the best possible evidence is behind the number" + ("; estimated: " + ", ".join(est) if est else ""),
                        "level": conf_level})
        for c in v5r["check_manually"]:
            if c["scored"] or (c["metric"] == "authenticity" and plat != "TikTok"):
                metrics.append({"label": "Check by hand", "value": c["metric"].replace("_", " ") + " missing", "note": c["fix"] + " Not in the score.", "level": "info"})
    out["metrics"] = metrics

    capped = None
    if not use_v5 and feed and ("view_rate" not in got or "engagement" not in got) and val > sm.FEED_CAP:
        miss = [n for n, k in (("view counts", "view_rate"), ("an engagement figure", "engagement")) if k not in got]
        capped = "Capped at %s: no %s on file for %s" % (band_for(sm.FEED_CAP), " or ".join(miss), plat)
        val = sm.FEED_CAP
        out["score_range"] = [min(x, sm.FEED_CAP) for x in out["score_range"]]
    out["score"], out["tag"] = val, band_for(val)
    lo_s, hi_s = out["score_range"]
    out["tag_range"] = [band_for(lo_s), band_for(hi_s)]
    out["strengths"] = [got[k]["good"] for k in sm.PARAMS if k in got and got[k]["mid"] >= 0.6]
    out["watchouts"] = extra_watch + [got[k]["bad"] for k in sm.PARAMS if k in got and got[k]["mid"] < 0.3]
    if capped:
        out["watchouts"].insert(0, capped)
        out["metrics"].append({"label": "Cap", "value": "max %d (%s)" % (sm.FEED_CAP, band_for(sm.FEED_CAP)), "note": capped, "level": "warn"})
    lead = "" if objective == "Balanced" else " for " + objective_label(objective).lower()
    measured = [sm.LABEL[k].lower() for k in sm.PARAMS if k in got]
    txt = "Score %d out of 100 (%s)%s." % (val, out["tag"], lead)
    txt += " Based on %d of 4 measures: %s." % (len(measured), ", ".join(measured))
    if not verified:
        txt += " Public numbers only."
    if out["strengths"]:
        txt += " Good: %s." % "; ".join(out["strengths"][:2])
    if out["watchouts"]:
        txt += " Check: %s." % "; ".join(out["watchouts"][:2])
    if out["limited_data"]:
        txt += " Limited data: a first look only."
    out["conclusion"] = txt
    return out
