"""The campaign brief on the board card (items 211-213, owner 2026-10-21).

One brief per campaign, stored on the campaign (``campaigns.brief``, JSON) and seeded from the newest
brief on each of its selections until it is first saved. It holds every question the AI shortlister
asks (the core questions and the power-ups), answered by picking options: each question also carries
a "Helvi suggests" answer read from the campaign's own creators (free, words only, never a figure from
an analysis). Saving pushes the objective and the audience to every attached selection, so their pages
and shortlists agree with the card.

Targets (item 211): the planner's formula (the same for every campaign), worked creator by creator
on each chosen platform: their own usual views and likes + comments when an analysis is on file, the
typical rate for their size otherwise. Engagement is likes + comments + shares + saves, lifted by the
share/save uplift our own campaigns measure. The target is the safe estimate; the expected one is
shown beside it as "likely". Each number comes with a sentence saying where it comes from, in
aggregate only: KAMs and clients never see a creator's analysis or score.

Requirements: Portal Programme/BRIEF-campaign-brief-211-213-2026-10-21.md.
"""

import json

import db
import matcher
import plans
import powerups

# The questions on the card, grouped as the shortlister asks them. Budget stays out (the AI card
# replaced it with the creator mix, and the card never talks prices); notes, the claim tags and the
# lookalike picks are not multiple-choice and stay with the shortlister.
GROUPS = [
    ("campaign", "Campaign", ["goal", "platforms", "market", "category", "deliverable", "timing"]),
    ("creators", "Creators", ["mix", "creator_size", "count", "creator_type", "collab", "licence", "max_fake", "min_engagement"]),
    ("audience", "Audience", ["gender", "age", "aud_city", "content_lang"]),
    ("product", "Product", ["product", "claim", "regulated", "tone"]),
]
REQUIRED = ("goal", "platforms", "market", "category")      # what a selection's own brief needs (matcher)
# Short labels for the card's rows; the shortlister keeps its full questions.
SHORT = {"goal": "Objective", "platforms": "Platforms", "market": "Countries", "category": "Product space", "deliverable": "Content",
         "timing": "Start", "mix": "Creator mix", "creator_size": "Creator sizes", "count": "How many creators",
         "max_fake": "Fake followers", "min_engagement": "Minimum engagement", "gender": "Audience gender", "age": "Audience age"}
GOAL_LABEL = {"awareness": "Awareness", "engagement": "Engagement", "traffic": "Traffic"}

# Sponsored posts usually land a little under a creator's usual views; own averages are planned at this share.
SPONSORED = 0.8
TARGET_KEYS = ("posts", "views", "reach", "engagement", "er", "clicks")
SIZE_OF = [("nano", 20000), ("micro", 100000), ("mid", 500000), ("macro", 1000000), ("mega", None)]   # matcher's sizes
COUNTRY = {"SA": "Saudi Arabia", "AE": "the UAE", "EG": "Egypt"}
# The brief's product space -> the planner's category (engagement differs by what is sold).
CATEGORY_OF = {"health care": "pharma", "skincare": "beauty", "beauty": "beauty", "hair care": "beauty", "fragrance": "beauty",
               "mother & baby": "baby", "food": "fmcg", "e-commerce": "retail", "technology": "tech", "automotive": "auto"}


# ------------------------------------------------------------------ questions --

def _power_q():
    return {q["id"]: q for q in powerups.QUESTIONS}


def questions():
    """[{key, label, items: [{id, label, type: one|many|text, options: [{value, label, hint}], max}]}]"""
    pq = _power_q()
    out = []
    for key, label, ids in GROUPS:
        items = []
        for qid in ids:
            q = matcher._BY_ID.get(qid) or pq.get(qid)
            if q is None:
                continue
            kind = "text" if q["type"] == "text" else "many" if (q["type"] == "many" or q.get("multi_ok")) else "one"
            opts = [{"value": v, "label": l, "hint": matcher.HINTS.get((qid, v), "")} for v, l in q.get("options", [])]
            items.append({"id": qid, "label": SHORT.get(qid) or q["label"].rstrip("?"), "type": kind, "options": opts,
                          "max": q.get("max"), "required": qid in REQUIRED})
        out.append({"key": key, "label": label, "items": items})
    return out


def _ids():
    return [qid for _k, _l, ids in GROUPS for qid in ids]


def clean(raw):
    """The answers ``raw`` allows, restricted to the card's questions. Never fails."""
    got, _missing = matcher.clean_answers(raw if isinstance(raw, dict) else {})
    keep = set(_ids())
    return {k: v for k, v in got.items() if k in keep}


def missing(answers):
    return [q for q in REQUIRED if not answers.get(q)]


# --------------------------------------------------------------- the stored brief --

def _stored(k):
    raw = k["brief"] if "brief" in k.keys() else None
    try:
        got = json.loads(raw or "{}")
    except (TypeError, ValueError):
        got = {}
    return got if isinstance(got, dict) else {}


def goals_of(objective):
    """The campaign's objective key -> goal answers ("balanced" reads as all three, as metrics does)."""
    o = str(objective or "").lower()
    if not o or o == "custom":
        return []
    if o == "balanced":
        return ["awareness", "engagement", "traffic"]
    return [p for p in o.split("+") if p in GOAL_LABEL]


def _selection_briefs(sels):
    out = []
    with db.connect() as conn:
        for s in sels:
            r = conn.execute("SELECT answers FROM briefs WHERE selection_id = ? AND deleted_at IS NULL ORDER BY id DESC LIMIT 1",
                             (s["id"],)).fetchone()
            if r:
                try:
                    a = json.loads(r["answers"] or "{}")
                except ValueError:
                    a = {}
                if isinstance(a, dict):
                    out.append(a)
    return out


def seed(sels):
    """The selections' newest briefs folded into one: the first answer wins, lists join."""
    out = {}
    for a in _selection_briefs(sels):
        for qid, v in clean(a).items():
            if qid not in out:
                out[qid] = v
            elif isinstance(out[qid], list) and isinstance(v, list):
                out[qid] = out[qid] + [x for x in v if x not in out[qid]]
    return out


def load(k, sels):
    """(answers, meta) for the card: the saved campaign brief, else the seed. The goal always follows
    the campaign's own objective, which the dashboard reads."""
    st = _stored(k)
    answers = clean(st.get("answers")) if st.get("answers") else seed(sels)
    g = goals_of(k["objective"] if "objective" in k.keys() else None)
    if g:
        answers["goal"] = g
    meta = {"saved_at": st.get("saved_at"), "saved_by": st.get("saved_by"), "typed": [t for t in st.get("typed") or [] if t in TARGET_KEYS],
            "seeded": not st.get("answers")}
    return answers, meta


# ------------------------------------------------------------ the campaign's creators --

def _codes(sels):
    out = []
    for s in sels:
        try:
            for c in json.loads(s["codes"] or "[]"):
                if c not in out:
                    out.append(c)
        except (TypeError, ValueError):
            pass
    return out


def _creators(sels):
    codes = _codes(sels)
    if not codes:
        return []
    with db.connect() as conn:
        rows = {r["code"]: r for r in conn.execute("SELECT * FROM creators WHERE code IN (%s)" % ",".join("?" * len(codes)), codes)}
    return [rows[c] for c in codes if c in rows]


def _followers(c):
    foll = {}
    for a in db.split_profiles(c["profiles"] or ""):
        if a.get("followers"):
            foll[a["platform"]] = int(a["followers"])
    if c["followers"] and c["platform"] and c["platform"] not in foll:
        foll[c["platform"]] = int(c["followers"])
    return foll


def _main_followers(c):
    f = _followers(c)
    return f.get(c["platform"]) or (max(f.values()) if f else 0)


def _size(n):
    for key, top in SIZE_OF:
        if top is None or n < top:
            return key
    return "mega"


def _summaries():
    import discover
    return discover._load()


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def _avg_share(lst_by, field, names):
    """Mean share of ``names`` in ``field`` over the creators that measure it, and how many do."""
    vals = [powerups._share(lst, field, names) for lst in lst_by]
    vals = [v for v in vals if v is not None]
    return (sum(vals) / len(vals) if vals else None), len(vals)


def _cap(t):
    return t[:1].upper() + t[1:]


def _of(n, total):
    return "%d of %d" % (n, total) if n != total else ("all %d" % total if total > 2 else "both" if total == 2 else "the one")


# ------------------------------------------------------------------ suggestions --

def suggest(sels):
    """{question id: {"value": answer, "why": words}} read from the campaign's creators. Free, no model."""
    cs = _creators(sels)
    n = len(cs)
    if not n:
        return {}
    out = {}
    docs = _summaries()
    lst_by = [docs.get(c["code"]) or [] for c in cs]
    measured = sum(1 for l in lst_by if l)

    # Platforms: every platform at least 40% of them are on.
    on = {}
    for c in cs:
        for p in _followers(c):
            if p in matcher.PLATFORMS:
                on[p] = on.get(p, 0) + 1
    plats = [p for p, k in sorted(on.items(), key=lambda x: -x[1]) if k >= max(1, 0.4 * n)]
    if plats:
        out["platforms"] = {"value": plats, "why": _cap("; ".join("%s are on %s" % (_of(on[p], n), p) for p in plats)) + "."}

    # Sizes, mix and how many.
    sizes = {}
    big = 0
    for c in cs:
        f = _main_followers(c)
        sizes[_size(f)] = sizes.get(_size(f), 0) + 1
        big += 1 if f >= 500000 else 0
    order = [s for s, _ in SIZE_OF if s in sizes]
    words = ", ".join("%d %s" % (sizes[s], s) for s in order)
    out["creator_size"] = {"value": order, "why": "Their sizes: %s." % words}
    small = sizes.get("nano", 0) + sizes.get("micro", 0)
    if big >= 0.5 * n:
        mix = "big"
    elif 1 <= big <= 2 and n >= 5:
        mix = "hero"
    elif small >= 0.7 * n:
        mix = "micro"
    else:
        mix = "auto"
    out["mix"] = {"value": mix, "why": _cap("%s have 500k followers or more." % _of(big, n)) if mix in ("big", "hero")
                  else _cap("%s have under 100k followers." % _of(small, n)) if mix == "micro" else "Their sizes are spread out, so Helvi balances the mix."}
    out["count"] = {"value": "5" if n <= 5 else "8" if n <= 10 else "15" if n <= 20 else "25",
                    "why": "The campaign holds %d creator%s." % (n, "" if n == 1 else "s")}

    # The space: what the creators themselves are about.
    spaces = []
    for v, label in matcher._BY_ID["category"]["options"]:
        k = sum(1 for c in cs if powerups._space_match(c, [v]) == 100)
        if k >= max(1, 0.4 * n):
            spaces.append((k, v, label))
    spaces = sorted(spaces, key=lambda x: -x[0])[:3]
    if spaces:
        out["category"] = {"value": [v for _k, v, _l in spaces],
                           "why": _cap("; ".join("%s post about %s" % (_of(k, n), l.lower()) for k, _v, l in spaces)) + "."}
        if spaces[0][1] == "health care":
            out["regulated"] = {"value": "yes", "why": "Healthcare products usually make a health claim."}

    types = []
    for v, label in powerups.TYPE_OPTIONS:
        k = sum(1 for c in cs if powerups._type_match(c, [v])[0] == 100)
        if k >= max(1, 0.4 * n):
            types.append((k, v, label))
    types = sorted(types, key=lambda x: -x[0])[:2]
    if types:
        out["creator_type"] = {"value": [v for _k, v, _l in types],
                               "why": _cap("; ".join("%s are %s" % (_of(k, n), l.lower()) for k, _v, l in types)) + "."}

    lic = powerups.licences()
    k = sum(1 for c in cs if lic.get(c["code"]))
    if k:
        out["licence"] = {"value": "preferred" if k >= 0.5 * n else "not_needed",
                          "why": _cap("%s hold a Mawthooq licence." % _of(k, n))}

    tones = powerups.tones()
    tally = {}
    for c in cs:
        for t in tones.get(c["code"]) or []:
            tally[t] = tally.get(t, 0) + 1
    tl = dict(powerups.TONE_OPTIONS)
    top_t = [t for t, k in sorted(tally.items(), key=lambda x: -x[1]) if t in tl and k >= max(1, 0.4 * n)][:2]
    if top_t:
        out["tone"] = {"value": top_t, "why": "Most of their content reads as %s." % " and ".join(tl[t].lower() for t in top_t)}

    if not measured:
        return out
    basis = " (read from %s with an audience on file)" % _of(measured, n) if measured < n else ""

    # Audience: where, who, what age, which city, which language. Words only.
    best = []
    for code in ("SA", "AE", "EG"):
        v, m = _avg_share(lst_by, "countries", [code])
        if v is not None and v >= 15:
            best.append((v, code))
    if best:
        best = [c for _v, c in sorted(best, reverse=True)]
        out["market"] = {"value": best, "why": "Their followers are mostly in %s%s." % (" and ".join(COUNTRY[c] for c in best), basis)}
    fem = _avg([max((s.get("female") for s in l if s.get("female") is not None), default=None) for l in lst_by])
    if fem is not None:
        g = "Women" if fem >= 60 else "Men" if fem <= 40 else "Any"
        out["gender"] = {"value": g, "why": {"Women": "Their followers are mostly women", "Men": "Their followers are mostly men",
                                             "Any": "Their followers are a mix of women and men"}[g] + basis + "."}
    ages = []
    for v_, names in powerups.AGE_NAMES.items():
        v, m = _avg_share(lst_by, "ages", names)
        if v is not None and v >= 25:
            ages.append(v_)
    if ages:
        lab = dict(matcher._BY_ID["age"]["options"])
        out["age"] = {"value": ages if len(ages) > 1 else ages[0], "why": "Most of their followers are %s%s." % (" and ".join(lab[a] for a in ages), basis)}
    cities = []
    for v_, label in powerups.CITY_OPTIONS:
        names = [v_, "Khobar", "Al Khobar"] if v_ == "Dammam" else [v_]
        v, m = _avg_share(lst_by, "cities", names)
        if v is not None and v >= 10:
            cities.append((v, v_, label))
    if cities:
        cities = sorted(cities, reverse=True)[:3]
        out["aud_city"] = {"value": [v for _s, v, _l in cities], "why": "Their followers cluster in %s%s." % (", ".join(l for _s, _v, l in cities), basis)}
    ar = en = lang_n = 0
    for l in lst_by:
        have = powerups._langs(l)
        if have:
            lang_n += 1
            ar += "arabic" in have
            en += "english" in have
    if lang_n:
        v = "both" if ar >= 0.3 * lang_n and en >= 0.3 * lang_n else "ar" if ar >= en else "en"
        out["content_lang"] = {"value": v, "why": {"both": "They post in Arabic and English.", "ar": "They mostly post in Arabic.",
                                                   "en": "They mostly post in English."}[v]}
    paid = [powerups._collab(l) for l in lst_by]
    paid = [(p.get("paid") or 0) for p in paid if p is not None]
    if paid:
        fresh, proven = sum(1 for p in paid if p == 0), sum(1 for p in paid if p >= 3)
        v = "fresh" if fresh >= 0.6 * len(paid) else "proven" if proven >= 0.6 * len(paid) else "either"
        out["collab"] = {"value": v, "why": {"fresh": "Most of them have done few or no brand deals.",
                                             "proven": "Most of them have worked with brands before.",
                                             "either": "They are a mix of new and brand-experienced faces."}[v]}
    return out


# --------------------------------------------------------------------- targets --

def _fmt(n):
    return "{:,}".format(int(round(n)))


def targets(sels, answers):
    """{"targets", "likely", "why", "headline", "creators", "posts"} for these selections and answers.
    The goal decides the headline numbers and whether clicks are planned."""
    goals = [g for g in (answers.get("goal") or []) if g in GOAL_LABEL] if isinstance(answers.get("goal"), list) \
        else ([answers["goal"]] if answers.get("goal") in GOAL_LABEL else [])
    headline = list(dict.fromkeys(k for g in (goals or ["awareness", "engagement"]) for k in plans.OBJECTIVE_KPIS[g]))
    links = "traffic" in goals
    cs = _creators(sels)
    if not cs:
        return {"targets": {}, "likely": {}, "why": {"posts": "Add a selection with creators to this campaign first."},
                "headline": headline, "creators": 0, "posts": 0}
    lib = plans.rates()
    up = plans.share_save_uplift()
    wanted = [p for p in (answers.get("platforms") or []) if p in plans.PLATFORMS]
    cats = answers.get("category") or []
    cat = next((CATEGORY_OF[c] for c in cats if c in CATEGORY_OF), "other")
    cf = plans.CATEGORIES[cat][1]
    docs = _summaries()

    tot = {"safe": dict.fromkeys(("views", "eng", "reach", "clicks"), 0.0), "exp": dict.fromkeys(("views", "eng", "reach", "clicks"), 0.0)}
    posts, own_v, own_e, by_plat, used = 0, 0, 0, {}, set()
    for c in cs:
        foll = _followers(c)
        plats = [p for p in wanted if foll.get(p)] if wanted else ([c["platform"]] if c["platform"] in lib and foll.get(c["platform"]) else [])
        lst = docs.get(c["code"]) or []
        for p in plats:
            L, f = lib[p], foll[p]
            tier = plans.tier_of(f)
            mine = next((s for s in lst if s["platform"] == p), None)
            posts += 1
            used.add(c["code"])
            by_plat[p] = by_plat.get(p, 0) + 1
            if mine and mine.get("views"):
                v = (mine["views"] * SPONSORED, mine["views"])
                own_v += 1
            else:
                v = (f * L["view_rate"][tier][0] / 100.0, f * L["view_rate"][tier][1] / 100.0)
            if mine and mine.get("views") and mine.get("likes") is not None:
                rate = ((mine["likes"] or 0) + (mine.get("comments") or 0)) / float(mine["views"]) * up.get(p, 1.0)
                e = (v[0] * rate, v[1] * rate)
                own_e += 1
            else:
                e = (v[0] * L["eng_rate"][tier][0] * cf / 100.0, v[1] * L["eng_rate"][tier][1] * cf / 100.0)
            for i, kind in enumerate(("safe", "exp")):
                tot[kind]["views"] += v[i]
                tot[kind]["eng"] += e[i]
                tot[kind]["reach"] += v[i] * L["reach_per_view"]
                tot[kind]["clicks"] += v[i] * L["ctr"][i] / 100.0 if links else 0

    def pack(x):
        out = {"posts": posts, "views": x["views"], "reach": x["reach"], "engagement": x["eng"],
               "er": x["eng"] / x["views"] * 100 if x["views"] else None}
        if links:
            out["clicks"] = x["clicks"]
        return {k: plans._round(k, v) for k, v in out.items() if v}

    n, pl = len(used), sorted(by_plat, key=lambda p: -by_plat[p])
    why = {}
    where = " and ".join(pl) if pl else "their main platform"
    skipped = len(cs) - n
    why["posts"] = ("One post from each creator on %s: %d post%s from %d creator%s." % (where, posts, "" if posts == 1 else "s", n, "" if n == 1 else "s")
                    + (" %d creator%s not on the chosen platforms." % (skipped, " is" if skipped == 1 else "s are") if skipped else ""))
    bench = posts - own_v
    src = []
    if own_v:
        src.append("%d from their own recent posts, planned at %d%% because sponsored posts usually land a little under" % (own_v, SPONSORED * 100))
    if bench:
        src.append("%d from the typical rate for their size on that platform, at the low end of the published range" % bench)
    why["views"] = "Each creator's usual views per post: " + "; ".join(src) + "."
    why["reach"] = "Views × the share of unique people per view: " + ", ".join(
        "%s %d%%" % (p, round(lib[p]["reach_per_view"] * 100)) for p in pl) + "."
    lifts = ", ".join("%s ×%s" % (p, ("%.2f" % up.get(p, 1.0)).rstrip("0").rstrip(".")) for p in pl if up.get(p, 1.0) != 1.0)
    why["engagement"] = ("Likes + comments + shares + saves. Their usual likes and comments (%s), " % (
        "own posts for %d, typical rate for the rest" % own_e if own_e and own_e < posts else "their own posts" if own_e else "the typical rate for their size")
        + ("lifted for shares and saves by what our own campaigns measure (%s)." % lifts if lifts else "with no share/save lift yet (too few tracked videos).")
        + (" %s content is planned %d%% lower." % (plans.CATEGORIES[cat][0].split(" /")[0], round((1 - cf) * 100)) if cf < 1 else ""))
    why["er"] = "Engagement ÷ views."
    if links:
        why["clicks"] = "Views × the typical click rate on a tracked link: " + ", ".join(
            "%s %s%%" % (p, ("%.2f" % lib[p]["ctr"][0]).rstrip("0").rstrip(".")) for p in pl) + "."
    return {"targets": pack(tot["safe"]), "likely": pack(tot["exp"]), "why": why, "headline": headline,
            "creators": n, "posts": posts}


# ------------------------------------------------------------------------- views --

def label_of(qid, v):
    q = matcher._BY_ID.get(qid) or _power_q().get(qid)
    vals = v if isinstance(v, list) else [v]
    if q is None or q["type"] == "text":
        return ", ".join(str(x) for x in vals)
    opts = dict(q.get("options", []) + q.get("legacy", []))
    return ", ".join(matcher.other_text(x) or opts.get(x, str(x)) for x in vals)


def read_only(answers):
    """[{label, items: [{label, answer}]}] for a client: the answered questions only, in words."""
    out = []
    for g in questions():
        rows = [{"label": q["label"], "answer": label_of(q["id"], answers[q["id"]])} for q in g["items"] if answers.get(q["id"])]
        if rows:
            out.append({"label": g["label"], "items": rows})
    return out


def payload(k, sels, staff):
    """What the card's Brief section opens on. Staff get the questions, Helvi's suggestions and the
    targets; a client gets the brief in words."""
    answers, meta = load(k, sels)
    if not staff:
        return {"answers": read_only(answers), "summary": matcher.describe(answers) if answers else "", "saved_at": meta["saved_at"]}
    return {"questions": questions(), "answers": answers, "meta": meta, "suggest": suggest(sels),
            "plan": targets(sels, answers), "targets": db.campaign_targets(k), "missing": missing(answers)}


def set_typed(k, typed):
    """Only which targets were typed by hand changed (the numbers themselves are campaign columns)."""
    st = _stored(k)
    st["typed"] = [t for t in typed if t in TARGET_KEYS]
    db.save_campaign(k["id"], brief=json.dumps(st))


def save(k, sels, answers, typed, by):
    """Write the campaign brief, and push the objective and the audience to every attached selection
    whose brief it completes. Returns (pushed selection count, missing required ids)."""
    import portal
    answers = clean(answers)
    st = _stored(k)
    st.update(answers=answers, typed=[t for t in typed if t in TARGET_KEYS], saved_at=db.now(), saved_by=by)
    db.save_campaign(k["id"], brief=json.dumps(st))
    miss = missing(answers)
    if miss:
        return 0, miss
    brief = matcher.to_brief(answers)
    text = matcher.describe(answers)
    pushed = 0
    for s in sels:
        try:
            codes = json.loads(s["codes"] or "[]")
        except (TypeError, ValueError):
            codes = []
        db.set_selection_objective(s["id"], brief["objective"])
        db.set_selection_target(s["id"], brief["target"])
        portal.save_brief(s["code_id"], None, "board", answers, text, brief["objective"], brief["target"], s["id"],
                          {"codes": codes, "campaign": k["id"]})
        pushed += 1
    return pushed, []
