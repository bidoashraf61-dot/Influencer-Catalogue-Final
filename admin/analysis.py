"""Creator full analysis: the template admins fill in, and the parser that
turns it (or a pasted JSON document) into the stored analysis.

The sections mirror a Modash profile report: overview numbers, audience
(countries, cities, gender, ages, languages, interests, brand affinity,
reachability, credibility), follower growth, top and sponsored posts, brands
worked with, hashtags, notable followers and lookalike creators.

One workbook can carry many creators — every sheet is keyed by creator code —
so a whole batch is one upload.
"""

import json
import re

import xlsx

OVERVIEW = [
    ("code", "Creator code (HV-…)"), ("platform", "Platform"), ("handle", "Handle"),
    ("followers", "Followers"), ("following", "Following"), ("posts_count", "Posts"),
    ("er", "Engagement rate %"), ("avg_likes", "Avg likes"), ("avg_comments", "Avg comments"),
    ("avg_views", "Avg views"), ("avg_reel_plays", "Avg reel plays"),
    ("paid_post_performance", "Paid post performance %"),
    ("fake_followers_pct", "Fake followers %"), ("credibility_pct", "Audience credibility %"),
    ("source", "Source (e.g. Modash Oct 2026)"), ("updated", "Data date (YYYY-MM-DD)"),
]
AUDIENCE_SECTIONS = ["countries", "cities", "gender", "ages", "languages", "interests",
                     "brand_affinity", "reachability"]
SHEETS = {
    "Overview": [label for _, label in OVERVIEW],
    "Audience": ["Creator code", "Section (" + " / ".join(AUDIENCE_SECTIONS) + ")",
                 "Label (country code SA, city, female/male, 18-24, …)", "Percent"],
    "Growth": ["Creator code", "Month (YYYY-MM)", "Followers", "Avg likes (optional)"],
    "Posts": ["Creator code", "Kind (top / sponsored)", "Post link", "Image link (optional)",
              "Date (YYYY-MM-DD)", "Likes", "Comments", "Views", "Brand (sponsored)"],
    "Brands": ["Creator code", "Brand", "Posts mentioning it"],
    "Hashtags": ["Creator code", "Hashtag or @mention", "Times used"],
    "Notable followers": ["Creator code", "Name", "Handle", "Followers"],
    "Lookalikes": ["Creator code", "Name", "Handle", "Followers", "HV code if in roster"],
}
EXAMPLE = {
    "Overview": ["HV-XX-000", "Instagram", "example_handle", "84000", "610", "512", "3.4", "2700",
                 "160", "", "31000", "2.9", "6", "88", "Modash Oct 2026", "2026-10-01"],
    "Audience": ["HV-XX-000", "countries", "SA", "71"],
    "Growth": ["HV-XX-000", "2026-09", "84000", ""],
    "Posts": ["HV-XX-000", "top", "https://www.instagram.com/p/…", "", "2026-09-12", "5400", "210", "", ""],
    "Brands": ["HV-XX-000", "Example brand", "3"],
    "Hashtags": ["HV-XX-000", "#skincare", "14"],
    "Notable followers": ["HV-XX-000", "Example name", "example", "120000"],
    "Lookalikes": ["HV-XX-000", "Example name", "example2", "90000", ""],
}


def template_xlsx():
    sheets = []
    for name, header in SHEETS.items():
        rows = [header, EXAMPLE[name]]
        sheets.append((name, rows, {i: 22 for i in range(len(header))}, None))
    return xlsx.write_book(sheets)


def _num(v):
    if v is None:
        return None
    t = str(v).strip().replace(",", "").replace("%", "")
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*([kKmM]?)", t)
    if not m:
        return None
    n = float(m.group(1)) * {"": 1, "k": 1e3, "m": 1e6}[m.group(2).lower()]
    return int(n) if n == int(n) else round(n, 2)


def _intish(v):
    n = _num(v)
    return int(round(n)) if isinstance(n, (int, float)) else None


def parse_workbook(data, known_codes):
    """{code: analysis document}, [problems]. Rows for codes not in the roster
    and the template's example rows are skipped with a note."""
    book = xlsx.read_all(data)
    docs, problems = {}, []

    def rows(name):
        table = book.get(name) or []
        return [r for r in table[1:] if any(c.strip() for c in r)]

    def doc(code):
        code = (code or "").strip().upper()
        if not code or code.startswith("HV-XX"):
            return None
        if code not in known_codes:
            problems.append(code + " is not in the roster — skipped.")
            return None
        return docs.setdefault(code, {"audience": {}})

    keys = [k for k, _ in OVERVIEW]
    for r in rows("Overview"):
        d = doc(r[0] if r else "")
        if d is None:
            continue
        r = r + [""] * (len(keys) - len(r))
        for i, k in enumerate(keys[1:], start=1):
            v = r[i].strip()
            if not v:
                continue
            if k in ("platform", "handle", "source", "updated"):
                d[k] = v
            else:
                d[k] = _num(v)
    for r in rows("Audience"):
        d = doc(r[0] if r else "")
        if d is None or len(r) < 4:
            continue
        section, label, pct = r[1].strip().lower().replace(" ", "_"), r[2].strip(), _num(r[3])
        if section not in AUDIENCE_SECTIONS or pct is None:
            problems.append("Audience row for %s skipped: section '%s'." % (r[0], r[1]))
            continue
        if section == "gender":
            d["audience"].setdefault("gender", {})[label.lower()] = pct
        elif section == "countries":
            d["audience"].setdefault("countries", []).append({"code": label.upper()[:2], "pct": pct})
        else:
            d["audience"].setdefault(section, []).append({"name": label, "pct": pct})
    for r in rows("Growth"):
        d = doc(r[0] if r else "")
        if d is None or len(r) < 3:
            continue
        d.setdefault("growth", []).append({"month": r[1].strip()[:7], "followers": _intish(r[2]),
                                           "avg_likes": _intish(r[3]) if len(r) > 3 else None})
    for r in rows("Posts"):
        d = doc(r[0] if r else "")
        if d is None or len(r) < 3 or not r[2].startswith("https://"):
            continue
        r = r + [""] * (9 - len(r))
        kind = "sponsored_posts" if r[1].strip().lower().startswith("spon") else "top_posts"
        d.setdefault(kind, []).append({
            "url": r[2].strip(), "thumb": r[3].strip() if r[3].startswith("https://") else None,
            "date": r[4].strip()[:10] or None, "likes": _intish(r[5]), "comments": _intish(r[6]),
            "views": _intish(r[7]), "brand": r[8].strip() or None})
    for sheet, key, fields in (("Brands", "brands", ("name", "count")),
                               ("Hashtags", "hashtags", ("tag", "count")),
                               ("Notable followers", "notable_followers", ("name", "handle", "followers")),
                               ("Lookalikes", "lookalikes", ("name", "handle", "followers", "code"))):
        for r in rows(sheet):
            d = doc(r[0] if r else "")
            if d is None:
                continue
            vals = (r[1:] + [""] * len(fields))[:len(fields)]
            item = {}
            for f, v in zip(fields, vals):
                item[f] = _intish(v) if f in ("count", "followers") else (v.strip() or None)
            if item.get(fields[0]):
                d.setdefault(key, []).append(item)
    for d in docs.values():
        for k in ("countries", "cities", "ages", "languages", "interests", "brand_affinity"):
            if k in d["audience"]:
                d["audience"][k].sort(key=lambda x: -(x.get("pct") or 0))
        if "growth" in d:
            d["growth"].sort(key=lambda x: x["month"])
    return docs, problems


def clean_json(doc):
    """A pasted JSON analysis, kept to the known shape."""
    if not isinstance(doc, dict):
        raise ValueError("The analysis must be a JSON object.")
    allowed = {k for k, _ in OVERVIEW} | {"audience", "growth", "top_posts", "sponsored_posts", "brands",
                                          "hashtags", "notable_followers", "lookalikes"}
    out = {k: v for k, v in doc.items() if k in allowed and k != "code"}
    if not isinstance(out.get("audience", {}), dict):
        raise ValueError("'audience' must be an object.")
    out.setdefault("audience", {})
    return json.loads(json.dumps(out))
