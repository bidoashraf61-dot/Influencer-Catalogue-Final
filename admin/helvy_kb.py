"""Helvy's second round of knowledge (phase C + D, #9): what HelloVoice's campaigns
achieved, the occasions calendar, the client's own selection decisions and the KSA
rules. Each is a read-only tool for the client assistant.

Privacy rules, enforced here and not left to the model:
  - campaign results: the client's own campaigns in full; campaigns HelloVoice has
    marked approved-to-name (Settings: case_study_campaigns) by name; everything
    else only as aggregates over at least MIN_GROUP campaigns, never one client's
    figures. Costs, fees and budgets never leave this module.
  - decisions: only the selections this client (or their team) can already see.
"""
import json
import time

import db
import occasions as _occ
import plans
import portal

MIN_GROUP = 3
_cache = {"at": 0, "rows": None}

KSA_RULES = """
KSA RULES (general guidance, not legal advice; the client's regulatory team has the final say)
- Mawthooq: influencers who advertise in Saudi Arabia need the Mawthooq licence from the General Authority for Media Regulation (GAMR). HelloVoice checks licences and shows a "Verified ✓" stamp on creators whose licence was verified; the catalogue can be filtered by licence. Recommend licensed creators for any paid KSA post.
- UAE: paid influencer content needs the UAE Media Council advertiser permit.
- Disclosure: paid posts must be clearly marked as advertising.
- Medical and health claims: the SFDA regulates health, medicine, cosmetics and supplement advertising. Prescription-only medicines must not be advertised to the public; cosmetics and supplements must not claim to treat, cure or prevent disease; avoid before/after promises, "guaranteed" results and unapproved comparisons. Content for healthcare professionals (HCP) follows separate rules. Flag any claim in a brief that sounds medical and suggest the client's medical/regulatory team approves the script; HelloVoice runs a compliance check before posting.
""".strip()


def _measured_rows():
    """[(campaign row, measured)] for every non-draft campaign with posts. Cached 10 minutes."""
    if _cache["rows"] is not None and time.time() - _cache["at"] < 600:
        return _cache["rows"]
    rows = []
    for k in db.list_campaigns():
        if k["status"] == "draft":
            continue
        try:
            m = plans._measured(k)
        except Exception:
            m = {}
        if m and m.get("posts"):
            rows.append((k, m))
    _cache.update(at=time.time(), rows=rows)
    return rows


def _category(k):
    plan = plans.plan_of(k) or {}
    return plans.CATEGORIES.get(plan.get("category") or "", ("", 1))[0] or None


def _median(v):
    return plans._median([x for x in v if x is not None])


def campaign_results(code_id):
    named = set(db.setting("case_study_campaigns", []) or [])
    mine = portal.team_codes(code_id) if code_id is not None else set()
    cases, groups = [], {}
    for k, m in _measured_rows():
        per_post = (m.get("views") or 0) / float(m["posts"]) if m.get("views") else None
        key = (k["platform"] or "Several platforms", _category(k) or "Other")
        g = groups.setdefault(key, {"campaigns": 0, "posts": 0, "er": [], "views_per_post": []})
        g["campaigns"] += 1
        g["posts"] += m["posts"]
        g["er"].append(m.get("er"))
        g["views_per_post"].append(per_post)
        if k["code_id"] in mine or k["id"] in named:
            cases.append({"campaign": k["name"], "brand": k["client"] or None, "yours": k["code_id"] in mine,
                          "platform": k["platform"] or "several", "category": _category(k), "status": k["status"],
                          "posts": m["posts"], "views": m.get("views"), "reach": m.get("reach"),
                          "engagement_rate_pct": m.get("er"), "clicks": m.get("clicks")})
    agg = [{"platform": p, "category": c, "campaigns": g["campaigns"], "posts": g["posts"],
            "median_engagement_rate_pct": round(_median(g["er"]), 2) if _median(g["er"]) is not None else None,
            "median_views_per_post": int(_median(g["views_per_post"])) if _median(g["views_per_post"]) else None}
           for (p, c), g in sorted(groups.items()) if g["campaigns"] >= MIN_GROUP]
    return {"case_studies": cases[:8], "aggregates": agg,
            "note": "Aggregates cover at least %d campaigns each and never name a client. Case studies are this client's own "
                    "campaigns or ones HelloVoice may name. Never mention costs, fees or budgets." % MIN_GROUP}


def decisions(code_id):
    """The client's own approve/reject decisions and reasons, to learn their taste."""
    import selstatus
    ids = sorted(portal.team_codes(code_id))
    with db.connect() as conn:
        sels = conn.execute("SELECT id, name, codes, code_id FROM selections WHERE code_id IN (%s) ORDER BY updated_at DESC LIMIT 10"
                            % ",".join("?" * len(ids)), ids).fetchall()
    roster = {c["code"]: c for c in db.list_creators()}
    reasons, out = {}, []
    for s in sels:
        st = selstatus.of(s["id"])
        one = {"selection": s["name"], "approved": [], "rejected": []}
        for code, row in st.items():
            c = roster.get(code)
            who = {"code": code, "name": c["name"] if c else code, "tier": c["tier"] if c else None,
                   "interests": c["interest"] if c else None, "city": c["city"] if c else None}
            if row["s"] == "approved":
                one["approved"].append(who)
            elif row["s"] == "rejected":
                label = selstatus.REASONS.get(row["reason"] or "", "")
                if label:
                    reasons[label] = reasons.get(label, 0) + 1
                one["rejected"].append(dict(who, reason=label or None, note=row["note"] or None))
        if one["approved"] or one["rejected"]:
            one["approved"], one["rejected"] = one["approved"][:20], one["rejected"][:20]
            out.append(one)
    return {"selections": out, "reject_reasons": reasons,
            "how_to_use": "Suggest creators like the approved ones and avoid what they rejected and why. Never quote prices."}


def upcoming(months=4, sector=""):
    items = _occ.upcoming(months=months, sector=sector)
    return {"today": time.strftime("%Y-%m-%d"), "occasions": items[:14],
            "rule": "Influencer content needs 6-8 weeks from brief to posting: 'brief_by' is the latest comfortable date to brief."}
