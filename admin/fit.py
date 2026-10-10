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

FITS = ["Strong fit", "Good fit", "Possible fit", "Not recommended"]
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


def score_core(doc, platform, followers=None, objective="Balanced", target=None, band="mid", bench=None,
               creator=None, record=None, min_parts=1):
    """The one scoring formula, used for every creator (scoring v2, see the header above).

    Returns the same shape as before (score, tag, parts, strengths, watchouts, checks, conclusion,
    objective, platform, basic) plus ``confidence`` ({"level": high|medium|low, "posts", "peers_n",
    "source": peers|global}), ``reach_followers`` and ``limited_data``."""
    import benchmarks
    verified = not doc.get("basic")
    out = {"score": None, "tag": "", "parts": [], "strengths": [], "watchouts": [], "conclusion": "",
           "objective": objective, "platform": platform, "basic": not verified, "checks": [],
           "confidence": {"level": "low", "posts": 0, "peers_n": 0, "source": "peers"},
           "reach_followers": None, "limited_data": True}
    bench = bench or {}
    target = dict(DEFAULT_TARGET, **{k: v for k, v in (target or {}).items() if v})
    target["gender"] = one_gender(target["gender"])
    objective = canonical(objective) if known_objective(objective) else "Balanced"
    w = blend(WEIGHTS_V2, objective)
    f = doc.get("followers") or followers
    out["reach_followers"] = int(f) if f else None
    size = benchmarks.size_of(f)
    plat = platform or "Instagram"
    feed = plat in benchmarks.FEED
    parts = []                      # (key, label, s, strength, watch, mult, src, n)

    def add(key, label, s, strength, watch, mult=1.0, src=None, n=0):
        parts.append((key, label, _clamp(s), strength, watch, mult, src, n))

    sample = benchmarks.sample_of(plat, dict(doc, followers=f)) if f else {}
    name = "%s %s creators" % (benchmarks.SIZE_LABEL[size].split(" (")[0].lower(), plat)

    # -- engagement
    er_val, er_metric, est = None, None, False
    if "er_med" in sample:
        er_val, er_metric = sample["er_med"], "er_med"
    elif "er" in sample:
        er_val, er_metric = sample["er"], "er"
    elif not feed and doc.get("avg_views") and doc.get("avg_likes") is not None:
        # a video account's rate the importer only had likes for: per view, estimated
        er_val = ((doc.get("avg_likes") or 0) + (doc.get("avg_comments") or 0)) / float(doc["avg_views"]) * 100
        er_metric, est = "er", True
    elif doc.get("er") is not None and not doc.get("likes_hidden"):
        er_val, er_metric, est = float(doc["er"]), "er", bool(doc.get("er_note"))
    if er_val is not None:
        per_view = (not feed) or doc.get("er_basis") == "views"
        pc = None
        for m in dict.fromkeys([er_metric, "er"]):
            pc = benchmarks.percentile(plat, size, m, er_val)
            if pc:
                break
        unit = " per view" if per_view else ""
        if pc:
            s, src, n = pc["pct"], "peers", pc["n"]
            txt = "Engagement %s%s, ahead of %d%% of %s" % (_pct(er_val), unit, int(round(s * 100)), name)
            wtxt = "Engagement %s%s, behind %d%% of %s" % (_pct(er_val), unit, int(round((1 - s) * 100)), name)
        else:
            bars = bench.get("video_er") if per_view else (bench.get("er") or {}).get(band)
            good, ok = bars if bars else ((4.5, 3.0) if per_view else (3.0, 1.5))
            s, src, n = _bar_score(er_val, good, ok), "global", 0
            txt = "Engagement %s%s, above the %s global estimate" % (_pct(er_val), unit, _pct(good))
            wtxt = "Engagement %s%s, below the %s global estimate" % (_pct(er_val), unit, _pct(ok))
        mult = TRUST["estimated"] if (est or src == "global") else TRUST["measured"]
        if est:
            s = min(s, 0.7)
        add("engagement", "Engagement vs similar creators" if src == "peers" else "Engagement (global estimate)",
            s, txt, wtxt, mult, src, n)

    # -- views
    vr_val, vr_metric = None, None
    if "view_rate_med" in sample:
        vr_val, vr_metric = sample["view_rate_med"], "view_rate_med"
    elif "view_rate" in sample:
        vr_val, vr_metric = sample["view_rate"], "view_rate"
    if vr_val is not None:
        pc = None
        for m in dict.fromkeys([vr_metric, "view_rate"]):
            pc = benchmarks.percentile(plat, size, m, vr_val)
            if pc:
                break
        if pc:
            s, src, n = pc["pct"], "peers", pc["n"]
            txt = "A typical video reaches %s of followers, ahead of %d%% of %s" % (_pct(vr_val), int(round(s * 100)), name)
            wtxt = "A typical video reaches %s of followers, behind %d%% of %s" % (_pct(vr_val), int(round((1 - s) * 100)), name)
        else:
            good, ok = bench.get("view_rate") or (30.0, 10.0)
            s, src, n = _bar_score(vr_val, good, ok), "global", 0
            txt = "A typical video reaches %s of followers, above the %s global estimate" % (_pct(vr_val), _pct(good))
            wtxt = "A typical video reaches %s of followers, below the %s global estimate" % (_pct(vr_val), _pct(ok))
        add("views", "Views vs similar creators" if src == "peers" else "Views (global estimate)", s, txt, wtxt,
            TRUST["measured"] if src == "peers" else TRUST["estimated"], src, n)

    # -- consistency (needs the spread of the sampled posts; peers only: there is no global bar)
    if "spread" in sample and (doc.get("sample_posts") or len(doc.get("views_series") or [])) >= 10:
        pc = benchmarks.percentile(plat, size, "spread", sample["spread"])
        if pc:
            s = 1.0 - pc["pct"]
            add("consistency", "Steady views", s, "Views hold steady from post to post (steadier than %d%% of %s)" % (int(round(s * 100)), name),
                "Views swing a lot from post to post (steadier than only %d%% of %s)" % (int(round(s * 100)), name),
                TRUST["measured"], "peers", pc["n"])

    # -- interest
    cats = [c for c in str(target["category"]).split("|") if c.strip() and c.strip().lower() != "any"]
    got = interest_share(doc, creator, cats)
    if got is not None:
        share, measured, why = got
        add("interest", "Product-space match", min(1.0, share / 0.5) if not measured else min(1.0, share / 0.5),
            why or "Works in the %s space" % ", ".join(c.lower() for c in cats),
            "Little sign of %s content" % ", ".join(c.lower() for c in cats),
            TRUST["measured"] if measured else TRUST["estimated"], "doc" if measured else "keywords", 0)

    data_keys = [p[0] for p in parts if p[0] in ("engagement", "views", "consistency")]
    if not data_keys and doc.get("roster_only"):
        # nobody has measured this creator: a neutral prior, so a tagged creator can still be
        # listed but never outranks one with numbers
        add("prior", "No numbers on file yet", 0.5, None, None, TRUST["assumed"], None, 0)
    if len(parts) < max(min_parts, 1):
        out["note"] = "Not enough public data to score."
        return out

    def wt(p):
        return w.get(p[0], 1.0) * p[5]
    out["parts"] = [{"key": p[0], "label": p[1], "s": round(p[2], 2), "w": round(wt(p), 2), "src": p[6], "n": p[7]} for p in parts]
    tw = sum(wt(p) for p in parts)
    if tw <= 0:
        out["note"] = "Not enough public data to score."
        return out
    val = int(round(100.0 * sum(wt(p) * p[2] for p in parts) / tw))

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
    capped = False
    if fake is not None:
        out["checks"].append({"label": "Fake followers", "text": "%s of followers look fake" % _pct(fake),
                              "level": "ok" if fake <= fk_good else "bad" if fake >= fk_bad else "warn"})
        if fake >= fk_bad:
            capped = True
            extra_watch.append("%s fake followers: the score is capped" % _pct(fake))
    if record and record.get("posts", 0) >= 2 and record.get("er") is not None and record.get("typical_er"):
        r = record["er"] / record["typical_er"]
        out["checks"].append({"label": "Our campaigns", "text": "%s engagement per view in %d of our campaign%s (typical %s)" % (
            _pct(record["er"]), record["campaigns"], "" if record["campaigns"] == 1 else "s", _pct(record["typical_er"])),
            "level": "ok" if r >= 1.2 else "bad" if r <= 0.7 else "warn"})
        if record["posts"] >= RECORD_MIN_POSTS and (r >= 1.2 or r <= 0.7):
            val = max(0, min(100, val + (RECORD_NUDGE if r >= 1.2 else -RECORD_NUDGE)))
            (out["strengths"] if r >= 1.2 else extra_watch).append(
                "Our record with them (%d posts) is %s our typical" % (record["posts"], "above" if r >= 1.2 else "below"))
    if capped:
        val = min(val, FAKE_CAP)

    # -- confidence
    posts = int(doc.get("sample_posts") or (12 if verified else 0))
    peer_parts = [p for p in parts if p[6] == "peers"]
    glob = [p for p in parts if p[6] == "global"]
    eng = next((p for p in parts if p[0] == "engagement"), None)
    peers_n = min([p[7] for p in peer_parts]) if peer_parts else 0
    if not data_keys or posts < 6 or not peer_parts:
        level = "low"
    elif posts >= 20 and len(peer_parts) >= 2 and eng is not None and eng[6] == "peers":
        level = "high"
    else:
        level = "medium"
    out["confidence"] = {"level": level, "posts": posts, "peers_n": peers_n,
                         "source": "global" if (glob and (not eng or eng[6] == "global")) else "peers"}
    out["limited_data"] = level == "low" or len(data_keys) < 2

    out["score"], out["tag"] = val, band_for(val)
    order = sorted(parts, key=lambda p: -wt(p))
    out["strengths"] += [p[3] for p in order if p[3] and p[2] >= 0.75 and p[0] != "prior"][:4]
    out["watchouts"] = extra_watch + [p[4] for p in order if p[4] and p[2] <= 0.45 and p[0] != "prior"][:3 - len(extra_watch)]
    lead = "" if objective == "Balanced" else " for " + objective_label(objective).lower()
    txt = "%s%s (%d/100)%s." % (out["tag"], lead, val, ", from public numbers only" if not verified else "")
    if out["strengths"]:
        txt += " Strengths: " + "; ".join(out["strengths"][:2]) + "."
    if out["watchouts"]:
        txt += " Watch: " + "; ".join(out["watchouts"][:2]) + "."
    if out["limited_data"]:
        txt += " Limited data: read it as a first look."
    out["conclusion"] = txt
    out["objective"] = objective
    return out
