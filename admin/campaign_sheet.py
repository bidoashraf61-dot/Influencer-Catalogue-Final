"""Campaign workbook: download a template, fill it in, upload it, check it, create the campaign.

One workbook sets up a whole campaign: its details and goal type, its booked creators, the
rules that detect posts, and the destination for tracking links. Targets are never typed: they
are worked out from the goal type, platforms, industry and the creators (plans.py). Results are
not in the workbook: posts and numbers come from the Apify captures once the campaign is live.

    template()                 -> .xlsx bytes (Start here, Campaign, Creators, Lists)
    parse(data)                -> {"campaign", "creators", "errors", "warnings", "targets"} (writes nothing)
    apply(parsed, by)          -> (campaign id, [notes]) (writes; call only on a parsed sheet with no errors)
"""
import datetime
import json
import re

import db
import plans
import xlsx

SHEETS = ("Start here", "Campaign", "Creators", "Lists")
GOALS = {"awareness": "Awareness", "engagement": "Engagement", "traffic": "Traffic"}

# (label, hint, required). The label is the lookup key on upload: do not rename.
CAMPAIGN_FIELDS = [
    ("Campaign name", "e.g. SVR Sun Secure, Wave 4", True),
    ("Client (brand)", "As the report shows it, e.g. SVR", False),
    ("Client access code", "Pick the access code that sees the report (leave empty to file it later)", False),
    ("Campaign type", "Awareness, Engagement or Traffic. Several: separate with commas. Sets the goal mix", True),
    ("Platforms", "Instagram, TikTok, Snapchat, YouTube. Several: separate with commas", True),
    ("Industry", "Pick one. Pharma plans engagement 20% lower", False),
    ("First day", "YYYY-MM-DD", False),
    ("Last day", "YYYY-MM-DD", False),
    ("Client budget (SAR)", "Internal: never shown to the client. Used for the value floor", False),
    ("Tracked links", "yes or no. Traffic campaigns always track links", False),
    ("Destination link", "Where each creator's tracking link sends people. https://...", False),
    ("Hashtags", "Posts carrying these are detected as campaign posts, e.g. #svr #suncare", False),
    ("Mentions", "Accounts creators must tag, e.g. @svr_ksa", False),
    ("Keywords", "Words that also mark a campaign post", False),
    ("Disclosure tags", "e.g. #ad #sponsored", False),
    ("Notes", "Internal", False),
]
CREATOR_COLUMNS = [
    "Creator (code, profile link or @handle)", "Videos planned", "Fee (SAR, internal)",
    "Followers (only for a creator not in the roster)", "Platform (only for a creator not in the roster)",
]
YES = {"yes", "y", "true", "1", "نعم"}
MAX_CREATORS = 300


# ------------------------------------------------------------------ template --

def _lists():
    labels = [c["label"] for c in db.list_codes() if c["label"]]
    cats = [v[0] for v in plans.CATEGORIES.values()]
    return [("Campaign type", list(GOALS.values())), ("Platform", list(plans.PLATFORMS)),
            ("Industry", cats), ("Tracked links", ["yes", "no"]), ("Client access code", labels)]


def template():
    """The blank workbook, with dropdowns where a field has a short list of answers."""
    lists = _lists()
    rows = [["Start here"], [""],
            ["1. Fill the Campaign sheet (column B) and the Creators sheet (one creator per row). Fields marked * are required."],
            ["2. Upload it on the admin Campaigns page. You see a preview and every problem before anything is saved."],
            ["3. The campaign is created as a draft. Its goals are calculated for you from the type, platforms, industry and creators."],
            ["4. Each creator gets a tracking link, and posts are detected from the hashtags, mentions and keywords you give."],
            ["5. Results are not typed here: views, likes and comments come from the Apify captures once the campaign is live."],
            [""], ["Tips"],
            ["A creator can be a roster code (HV-MI-001), a profile link, or an @handle. A new profile is added to the roster."],
            ["Do not rename the labels in column A of the Campaign sheet, or the column headings on the Creators sheet."]]
    camp = [["Field", "Your answer", "Notes"]]
    for label, hint, req in CAMPAIGN_FIELDS:
        camp.append([label + (" *" if req else ""), "", hint])
    creators = [["Creator (code, profile link or @handle) *"] + CREATOR_COLUMNS[1:]]
    creators.append(["@example_creator", "1", "", "", ""])
    ref = [[name for name, _ in lists]]
    for i in range(max(len(v) for _, v in lists)):
        ref.append([(v[i] if i < len(v) else "") for _, v in lists])
    sheets = [("Start here", rows, {0: 110}, None),
              ("Campaign", camp, {0: 26, 1: 38, 2: 80}, None),
              ("Creators", creators, {0: 42, 1: 16, 2: 20, 3: 36, 4: 34}, None),
              ("Lists", ref, {i: 26 for i in range(len(lists))}, None)]

    def col(i):
        return chr(65 + i)
    where = {name: i for i, (name, _) in enumerate(lists)}
    vals = []
    for label, lname, cell_row in (("Campaign type", "Campaign type", None), ("Industry", "Industry", None),
                                   ("Tracked links", "Tracked links", None), ("Client access code", "Client access code", None)):
        idx = [f[0] for f in CAMPAIGN_FIELDS].index(label) + 2
        n = len(lists[where[lname]][1]) + 1
        vals.append((2, "B%d:B%d" % (idx, idx), "Lists!$%s$2:$%s$%d" % (col(where[lname]), col(where[lname]), max(n, 2))))
    return xlsx.write_book(sheets, vals)


# --------------------------------------------------------------------- parse --

def _text(v):
    return ("" if v is None else str(v)).strip()


def _day(v):
    """YYYY-MM-DD from text or an Excel date serial; None when empty; False when unreadable."""
    t = _text(v)
    if not t:
        return None
    if re.fullmatch(r"\d{5}(\.0+)?", t):                      # Excel serial day
        return (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(float(t)))).isoformat()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.datetime.strptime(t[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return False


def _money(v):
    d = "".join(ch for ch in _text(v) if ch.isdigit() or ch == ".")
    try:
        return int(float(d)) if d else None
    except ValueError:
        return None


def _pick(text, allowed):
    """The allowed values named in a comma list, case-insensitive; (values, unknown words)."""
    got, bad = [], []
    for w in re.split(r"[,;/+]", text):
        w = w.strip()
        if not w:
            continue
        hit = next((a for a in allowed if a.lower() == w.lower()), None)
        (got if hit else bad).append(hit or w)
    return list(dict.fromkeys(got)), bad


def _followers_on(c, platform):
    try:
        for a in db.split_profiles(c["profiles"] or ""):
            if a.get("platform") == platform and a.get("followers"):
                return int(a["followers"])
    except Exception:
        pass
    return int(c["followers"]) if c["followers"] and (c["platform"] or "") == platform else None


def parse(data):
    """Read a filled workbook. Writes nothing. `errors` block the import; `warnings` do not."""
    import analysis
    errors, warnings = [], []
    try:
        book = xlsx.read_all(data)
    except xlsx.BadWorkbook as ex:
        return {"errors": [str(ex)], "warnings": [], "campaign": {}, "creators": [], "targets": None}
    crows = book.get("Campaign")
    if crows is None or book.get("Creators") is None:
        return {"errors": ["This is not the campaign template: the Campaign and Creators sheets are missing. "
                           "Download the template again."], "warnings": [], "campaign": {}, "creators": [], "targets": None}
    vals = {}
    for r in crows[1:]:
        if r and _text(r[0]):
            vals[re.sub(r"\s*\*\s*$", "", _text(r[0])).lower()] = _text(r[1]) if len(r) > 1 else ""

    def get(label):
        return vals.get(label.lower(), "")

    c = {"name": get("Campaign name"), "client": get("Client (brand)"), "notes": get("Notes")}
    if not c["name"]:
        errors.append("Campaign: give the campaign a name.")
    goals, bad = _pick(get("Campaign type"), list(GOALS.values()))
    if not goals:
        errors.append("Campaign: choose a campaign type (Awareness, Engagement or Traffic).")
    if bad:
        errors.append("Campaign type: not recognised: " + ", ".join(bad) + ".")
    plats, bad = _pick(get("Platforms"), list(plans.PLATFORMS))
    if not plats:
        errors.append("Campaign: choose at least one platform (Instagram, TikTok, Snapchat or YouTube).")
    if bad:
        errors.append("Platforms: not recognised: " + ", ".join(bad) + ". Facebook has no approved rates yet.")
    c["goals"] = [g.lower() for g in goals]
    c["platforms"] = plats
    cat_text = get("Industry")
    c["category"] = next((k for k, v in plans.CATEGORIES.items() if v[0].lower() == cat_text.lower() or k == cat_text.lower()), "other")
    if cat_text and c["category"] == "other" and cat_text.lower() != "other":
        warnings.append("Industry “%s” is not in the list, so “Other” is used." % cat_text)
    for key, label in (("starts", "First day"), ("ends", "Last day")):
        d = _day(get(label))
        if d is False:
            errors.append("%s: “%s” is not a date. Use YYYY-MM-DD." % (label, get(label)))
            d = None
        c[key] = d
    if c["starts"] and c["ends"] and c["ends"] < c["starts"]:
        errors.append("The last day is before the first day.")
    c["budget"] = _money(get("Client budget (SAR)"))
    c["tracked"] = get("Tracked links").lower() in YES or goals == ["Traffic"]
    dest = get("Destination link")
    if dest and not re.match(r"^https?://[^\s/]+\.[^\s]+$", dest):
        errors.append("Destination link must be a full web address starting with https://")
        dest = ""
    c["destination"] = dest
    if c["tracked"] and not dest:
        warnings.append("Tracked links are on but there is no destination link: add one on the campaign before going live.")
    rules = db.parse_rules(" ".join([get("Hashtags"), get("Mentions"), get("Keywords")]))
    told = db.parse_rules(get("Disclosure tags"))
    rules["disclosure"] = told["hashtags"] + told["keywords"]
    c["rules"] = rules
    if not (rules["hashtags"] or rules["mentions"] or rules["keywords"]):
        warnings.append("No hashtags, mentions or keywords: posts cannot be detected automatically until you add some.")
    label = get("Client access code")
    c["code_id"] = None
    if label:
        hit = next((x for x in db.list_codes() if (x["label"] or "").lower() == label.lower()), None)
        if hit is None:
            warnings.append("Access code “%s” was not found: the campaign is created without one." % label)
        else:
            c["code_id"] = hit["id"]

    # creators
    res = analysis.Resolver(db.list_creators(), db.creator_aliases())
    by_code = {x["code"]: x for x in db.list_creators()}
    crow = book["Creators"]
    creators, seen = [], set()
    for n, r in enumerate(crow[1:], start=2):
        entry = _text(r[0]) if r else ""
        if not entry or entry.lower() == "@example_creator":
            continue
        entry = re.sub(r"\s*\*\s*$", "", entry)
        planned = _money(r[1] if len(r) > 1 else "") or 1
        row = {"row": n, "entry": entry, "planned": planned, "fee": _money(r[2] if len(r) > 2 else ""),
               "followers": _money(r[3] if len(r) > 3 else ""),
               "platform": next((p for p in db.PLATFORMS if p.lower() == _text(r[4] if len(r) > 4 else "").lower()), None)}
        code, _ = res.resolve(entry)
        row["code"] = code
        row["name"] = (by_code[code]["name"] or code) if code in by_code else None
        if code and code in seen:
            warnings.append("Creators row %d: %s appears twice; the first row is used." % (n, entry))
            continue
        if code:
            seen.add(code)
        creators.append(row)
    if not creators:
        errors.append("Creators: add at least one creator.")
    if len(creators) > MAX_CREATORS:
        errors.append("Creators: %d rows is more than the %d a campaign can take from one file." % (len(creators), MAX_CREATORS))
    new = [x for x in creators if not x["code"]]
    if new:
        warnings.append("%d creator%s not in the roster will be added to it, hidden from clients until their details are filled in."
                        % (len(new), "" if len(new) == 1 else "s"))

    # targets, worked out the same way the planner does
    targets = None
    if not errors:
        rows = []
        for x in creators:
            cr = by_code.get(x["code"]) if x["code"] else None
            for p in plats:
                f = (_followers_on(cr, p) if cr is not None else None) or x["followers"]
                rows.append({"platform": p, "tier": plans.tier_of(f) if f else "micro", "posts": x["planned"],
                             "followers": f, "slot": x["entry"]})
        targets = _plan(c, rows)
    return {"campaign": c, "creators": creators, "errors": errors, "warnings": warnings, "targets": targets}


def _objective(goals):
    if len(goals) == 1:
        return goals[0]
    import metrics
    return metrics.blend_key(goals)


def _plan(c, rows):
    brief = {"platform": c["platforms"][0], "objective": c["goals"][0] if len(c["goals"]) == 1 else "balanced",
             "category": c["category"], "budget": c["budget"] or 0, "tracked_links": c["tracked"]}
    return plans.calculate_platforms(brief, rows)


# --------------------------------------------------------------------- apply --

def apply(parsed, by="admin"):
    """Create the campaign from a parsed sheet that has no errors. Returns (campaign id, notes)."""
    import history
    c = parsed["campaign"]
    history.set_actor(by or "admin")
    notes = []
    cid = db.create_campaign(c["name"], client=c["client"] or None, code_id=c["code_id"], platform=None, origin="sheet")
    codes, planned, costs, followers_by_code = [], {}, {}, {}
    for x in parsed["creators"]:
        got, msgs = db.resolve_creators([x["entry"]], c["name"])
        notes += msgs
        if not got:
            notes.append("Not added: " + x["entry"])
            continue
        code = got[0]
        codes.append(code)
        followers_by_code[code] = x["followers"]
        planned[code] = x["planned"]
        if x["fee"] is not None:
            costs[code] = x["fee"]
    db.add_campaign_creators(cid, codes, costs)
    db.set_planned(cid, planned)
    k = db.campaign(cid)
    import metrics
    sheet_f = dict(followers_by_code)
    rows, guessed = [], 0
    for m in db.campaign_creators(cid):
        foll = metrics.creator_followers(m)
        for pl in c["platforms"]:
            f = foll.get(pl) or sheet_f.get(m["cc_code"])
            guessed += 0 if f else 1
            rows.append({"platform": pl, "tier": plans.tier_of(f) if f else "micro", "posts": m["planned"] or 1,
                         "followers": f, "name": m["name"] or m["cc_code"], "slot": m["name"] or m["cc_code"]})
    if guessed:
        notes.append("Followers are not known for %d creator-platform pair%s: a micro-sized creator is assumed there until they are filled in."
                     % (guessed, "" if guessed == 1 else "s"))
    p = _plan(c, rows)
    keep = {x: p.get(x) for x in ("platform", "objective", "category", "budget", "links", "posts", "estimate", "floor",
                                   "target", "benchmark", "roi", "by_platform", "platforms")}
    targets = {key: (round(v, 2) if key == "er" else int(v)) for key, v in (p.get("target") or {}).items()
               if key in db.TARGET_KEYS and v}
    keep["brief"] = {"type": "+".join(c["goals"]), "platform": " + ".join(c["platforms"]), "platforms": c["platforms"],
                     "category": c["category"], "budget": str(c["budget"] or ""), "source": "sheet"}
    keep["agreed"] = targets
    keep["saved_at"] = db.now()
    t_start = db.day_bounds(c["starts"], None) if c["starts"] else None
    t_end = (db.day_bounds(c["ends"], None) + 86400 - 1) if c["ends"] and db.day_bounds(c["ends"], None) else None
    fields = dict(starts_at=t_start, ends_at=t_end, rules=c["rules"], destination=c["destination"] or None,
                  cost=c["budget"], notes=c["notes"] or None, targets=targets, objective=_objective(c["goals"]), plan=keep)
    if len(c["platforms"]) == 1:
        fields["platform"] = c["platforms"][0]
    db.save_campaign(cid, **fields)
    notes.append("Campaign created as a draft with %d creator%s and goals worked out from the sheet. Set it live when the dates and links are ready."
                 % (len(codes), "" if len(codes) == 1 else "s"))
    return cid, notes
