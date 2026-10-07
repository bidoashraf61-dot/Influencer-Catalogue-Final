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
    objective = objective if objective in WEIGHTS else "Balanced"
    w = WEIGHTS[objective]
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
    out.update({"fit": fit, "reason": ("For %s: " % objective.lower() if objective != "Balanced" else "") + " · ".join(line[:3]),
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
        if cat in str(creator_interest or "").lower() or any(w in p for p in pool for w in words):
            return 1.0
    return 0.25


def score(doc, platform, followers=None, objective="Balanced", target=None, band="mid", bench=None,
          record=None, creator_interest=None, min_parts=3):
    """The matching score for one creator, or {"score": None, ...} when the
    analysis holds too little to judge. Returns {"score", "tag", "parts",
    "strengths", "watchouts", "conclusion", "objective", "platform"}."""
    out = {"score": None, "tag": "", "parts": [], "strengths": [], "watchouts": [], "conclusion": "",
           "objective": objective, "platform": platform}
    if not doc:
        out["note"] = "No analysis on file."
        return out
    bench = bench or {}
    target = dict(DEFAULT_TARGET, **{k: v for k, v in (target or {}).items() if v})
    objective = objective if objective in WEIGHTS else "Balanced"
    w = WEIGHTS[objective]
    f = doc.get("followers") or followers
    er = doc.get("er")
    fake = doc.get("fake_followers_pct")
    if fake is None and doc.get("credibility_pct") is not None:
        fake = round(100 - doc["credibility_pct"], 1)
    au = doc.get("audience") or {}
    feed = platform in (None, "Instagram", "Facebook", "X")
    if er is not None and doc.get("er_note") and not feed:
        # A video account's rate that the importer had to work out is likes per FOLLOWER, which
        # a 6% per-view benchmark would crush. Use per-view when the report has the views,
        # else judge it against the follower-based range.
        views = doc.get("avg_views")
        if views:
            er = ((doc.get("avg_likes") or 0) + (doc.get("avg_comments") or 0)) / float(views) * 100
        else:
            feed = True
    bars = (bench.get("er") or {}).get(band) if feed else bench.get("video_er")
    good, ok = bars if bars else ((3.0, 1.5) if feed else (6.0, 3.0))
    fk_good, fk_bad = bench.get("fake_followers") or (15.0, 30.0)

    parts = []          # (key, label, s 0..1, [(s, strength, watchout)])

    def add(key, label, subs):
        subs = [x for x in subs if x is not None]
        if subs:
            parts.append((key, label, sum(x[0] for x in subs) / len(subs), subs))

    if er is not None:
        s = 1.0 if er >= good else (0.6 + 0.4 * (er - ok) / (good - ok) if er >= ok and good > ok else 0.6 * er / ok if ok else 0.0)
        s = _clamp(s)
        # A rate the importer worked out from average likes (the report showed 0%) is a guess:
        # it counts, but never as a full-marks strength.
        est = bool(doc.get("er_note"))
        if est:
            s = min(s, 0.7)
        word = ("Engagement about %s (estimated from average likes)" if est else "Engagement %s") % _pct(er)
        add("engagement", "Engagement", [(s,
            word + (", above the %s benchmark" % _pct(good) if er >= good else ", within the healthy range (%s and over)" % _pct(ok)),
            word + ", below the %s benchmark" % _pct(ok))])
    if fake is not None:
        s = 1.0 if fake <= fk_good else 0.0 if fake >= fk_bad else 1 - (fake - fk_good) / (fk_bad - fk_good)
        add("credibility", "Real audience", [(s, "Only %s fake followers" % _pct(fake), "%s fake followers" % _pct(fake))])

    subs = []
    tc = target["country"]
    cname = dict(COUNTRIES).get(tc, tc)
    countries = au.get("countries") or []
    if countries:
        home = next((c.get("pct") for c in countries if str(c.get("code", "")).upper() == tc), 0) or 0
        subs.append((_clamp(home / 60.0), "%s of the audience is in %s" % (_pct(home), cname),
                     "Only %s of the audience is in %s" % (_pct(home), cname)))
    g = target["gender"]
    if g in ("Women", "Men") and au.get("gender"):
        share = (au["gender"].get("female" if g == "Women" else "male")) or 0
        subs.append((_clamp(share / 60.0), "%s of the audience are %s" % (_pct(share), g.lower()),
                     "Only %s of the audience are %s" % (_pct(share), g.lower())))
    if target["age"] != "Any" and au.get("ages"):
        share = _age_share(au["ages"], target["age"])
        if share is not None:
            subs.append((_clamp(share / 40.0), "%s of the audience is aged %s" % (_pct(share), target["age"]),
                         "Only %s of the audience is aged %s" % (_pct(share), target["age"])))
    nic = _niche(target["category"], doc, creator_interest)
    if nic is not None:
        names = ", ".join(c.strip().lower() for c in str(target["category"]).split("|") if c.strip())
        subs.append((nic, "Works in the %s space" % names,
                     "Little sign of %s content or audience interest" % names))
    add("market", "Audience match", subs)

    if f:
        import math
        s = _clamp((math.log10(max(f, 1)) - 3.7) / (5.7 - 3.7))        # 5K -> 0, 500K -> 1
        add("reach", "Reach", [(s, "Reach of %s followers" % _k(f), "Small reach (%s followers)" % _k(f))])
    if record and record.get("posts", 0) >= 2 and record.get("er") is not None and record.get("typical_er"):
        r = record["er"] / record["typical_er"]
        s = _clamp(0.7 * r if r < 1 else 0.7 + 0.3 * min(1.0, (r - 1) / 0.5))
        add("record", "Our record", [(s, "Delivered %s engagement per view in our %d campaign%s (typical %s)" % (
            _pct(record["er"]), record["campaigns"], "" if record["campaigns"] == 1 else "s", _pct(record["typical_er"])),
            "Below our typical engagement in our past campaigns (%s vs %s)" % (_pct(record["er"]), _pct(record["typical_er"])))])

    out["parts"] = [{"key": k, "label": lab, "s": round(s, 2), "w": w.get(k, 1.0)} for k, lab, s, _ in parts]
    if len(parts) < min_parts:
        out["note"] = "Not enough analysis data to score."
        return out
    tw = sum(w.get(k, 1.0) for k, _, _, _ in parts)
    val = 100.0 * sum(w.get(k, 1.0) * s for k, _, s, _ in parts) / tw
    if fake is not None and fake >= fk_bad:
        val = min(val, 39.0)                          # a mostly bought audience is never a fit
    val = int(round(val))
    out["score"], out["tag"] = val, band_for(val)
    ranked = sorted(parts, key=lambda p: -w.get(p[0], 1.0))
    subs_all = [(w.get(k, 1.0), s_, st, wo) for k, _, _, subs in ranked for (s_, st, wo) in subs]
    subs_all.sort(key=lambda x: -x[0])
    out["strengths"] = [st for _, s_, st, _ in subs_all if s_ >= 0.75][:4]
    out["watchouts"] = [wo for _, s_, _, wo in subs_all if s_ <= 0.45][:3]
    lead = {"Balanced": "overall", "Awareness": "awareness", "Engagement": "engagement", "Conversion": "conversion"}[objective]
    txt = ("%s (%d/100)." % (out["tag"], val)) if objective == "Balanced" else ("%s for %s (%d/100)." % (out["tag"], lead, val))
    if out["strengths"]:
        txt += " Strengths: " + "; ".join(out["strengths"][:2]) + "."
    if out["watchouts"]:
        txt += " Watch: " + "; ".join(out["watchouts"][:2]) + "."
    out["conclusion"] = txt
    for p in out["parts"]:
        pass
    return out
