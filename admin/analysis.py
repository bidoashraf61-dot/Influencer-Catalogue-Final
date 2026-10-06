"""Creator full analysis: the template admins fill in, and the parser that
turns it (or a pasted JSON document) into the stored analysis.

The sections mirror a standard profile report: overview numbers (all content,
reels, stories, collaborations), audience quality (real people, mass and
suspicious followers, fake followers and likers), audience by followers and
by likers (countries, cities, gender, ages, languages, interests, brand
affinity, reachability), follower and likes growth, popular and sponsored
posts, brands worked with (with logos), hashtags and mentions.

One workbook can carry many creators — every sheet is keyed by creator code —
so a whole batch is one upload.
"""

import copy
import json
import re
import urllib.parse
from pathlib import Path

import xlsx

# Pictures that belong to an analysis — the profile photo and post covers
# taken from the profile report, and brand logos (shared, in _brands/). Client
# data: not in git, served only to a viewer with a code (/api/creator-media).
MEDIA = Path(__file__).resolve().parent / "analysis_media"

OVERVIEW = [
    ("code", "Creator code (HV-…)"), ("platform", "Platform"), ("handle", "Handle"),
    ("followers", "Followers"), ("following", "Following"), ("posts_count", "Posts"),
    ("er", "Engagement rate %"), ("avg_likes", "Avg likes"), ("avg_comments", "Avg comments"),
    ("avg_views", "Avg views"), ("avg_reel_plays", "Avg reel plays"),
    ("paid_post_performance", "Paid post performance %"),
    ("fake_followers_pct", "Fake followers %"), ("credibility_pct", "Audience credibility %"),
    ("source", "Source (internal, never shown to clients)"), ("updated", "Data date (YYYY-MM-DD)"),
    # Added to match the profile report; every one is optional.
    ("account_type", "Account type (Creator / Business)"),
    ("est_impressions", "Estimated impressions"), ("est_reach", "Estimated reach"),
    ("reels_er", "Reels engagement rate %"), ("avg_reel_likes", "Reels avg likes"),
    ("avg_reel_comments", "Reels avg comments"), ("avg_reel_shares", "Reels avg shares"),
    ("story_reach", "Stories estimated reach"), ("story_impressions", "Stories estimated impressions"),
    ("paid_views_pct", "Paid views %"), ("fake_likers_pct", "Fake likers %"),
    ("real_people_pct", "Real people %"), ("mass_followers_pct", "Real mass followers %"),
    ("suspicious_mass_pct", "Suspicious mass %"), ("suspicious_pct", "Suspicious accounts %"),
]
TEXT_KEYS = ("platform", "handle", "source", "updated", "account_type")
AUDIENCE_SECTIONS = ["countries", "cities", "gender", "ages", "languages", "interests",
                     "brand_affinity", "reachability"]
SHEETS = {
    "Overview": [label for _, label in OVERVIEW],
    "Audience": ["Creator code", "Section (" + " / ".join(AUDIENCE_SECTIONS) + ")",
                 "Label (country code SA, city, female/male, 18-24, …)", "Percent",
                 "Audience of (followers / likers — empty means followers)"],
    "Growth": ["Creator code", "Month (YYYY-MM)", "Followers", "Avg likes (optional)"],
    "Posts": ["Creator code", "Kind (top / sponsored)", "Post link", "Image link (optional)",
              "Date (YYYY-MM-DD)", "Likes", "Comments", "Views", "Brand (sponsored)"],
    "Brands": ["Creator code", "Brand", "Posts mentioning it", "Logo link or website (optional)"],
    "Hashtags": ["Creator code", "Hashtag or @mention", "Times used or %"],
}
EXAMPLE = {
    "Overview": ["HV-XX-000", "Instagram", "example_handle", "84000", "610", "512", "3.4", "2700",
                 "160", "", "31000", "2.9", "6", "88", "Report Oct 2026", "2026-10-01",
                 "Creator", "120000", "80000", "2.1", "2300", "90", "60", "9000", "9500",
                 "30", "5", "78", "6", "4", "12"],
    "Audience": ["HV-XX-000", "countries", "SA", "71", ""],
    "Growth": ["HV-XX-000", "2026-09", "84000", ""],
    "Posts": ["HV-XX-000", "top", "https://www.instagram.com/p/…", "", "2026-09-12", "5400", "210", "", ""],
    "Brands": ["HV-XX-000", "Example brand", "3", "examplebrand.com"],
    "Hashtags": ["HV-XX-000", "#skincare", "14"],
}


def template_xlsx(code=None):
    """The blank template; with a creator code, the example rows already
    carry that code, so the file only needs the numbers."""
    sheets = []
    for name, header in SHEETS.items():
        example = [code if (code and v == "HV-XX-000") else v for v in EXAMPLE[name]]
        rows = [header, example]
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
            if k in TEXT_KEYS:
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
        who = (r[4].strip().lower() if len(r) > 4 else "")
        aud = d.setdefault("audience_likers", {}) if who.startswith("lik") else d["audience"]
        if section == "gender":
            aud.setdefault("gender", {})[label.lower()] = pct
        elif section == "countries":
            aud.setdefault("countries", []).append({"code": label.upper()[:2], "pct": pct})
        else:
            aud.setdefault(section, []).append({"name": label, "pct": pct})
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
    for sheet, key, fields in (("Brands", "brands", ("name", "count", "logo")),
                               ("Hashtags", "hashtags", ("tag", "count"))):
        for r in rows(sheet):
            d = doc(r[0] if r else "")
            if d is None:
                continue
            vals = (r[1:] + [""] * len(fields))[:len(fields)]
            item = {}
            for f, v in zip(fields, vals):
                item[f] = _num(v) if f in ("count", "followers") else (v.strip() or None)
            if item.get(fields[0]):
                d.setdefault(key, []).append(item)
    for d in docs.values():
        for aud in (d["audience"], d.get("audience_likers") or {}):
            for k in ("countries", "cities", "ages", "languages", "interests", "brand_affinity"):
                if k in aud:
                    aud[k].sort(key=lambda x: -(x.get("pct") or 0))
        if "growth" in d:
            d["growth"].sort(key=lambda x: x["month"])
    return docs, problems


# Further fields read off a profile report (tools/profile_import.py), kept when
# an analysis is pasted back as JSON.
REPORT_EXTRA = {"bio", "location", "followers_change_pct", "avg_likes_change_pct", "likes_hidden",
                "er_note", "reels_er_note", "notable_followers_pct", "creator_interests",
                "fake_followers_dist", "er_dist", "photo"}


def media_path(code, name):
    """The file behind a "media:<name>" reference, or None."""
    code = re.sub(r"[^A-Z0-9-]", "", str(code or "").upper())
    name = Path(str(name or "")).name
    if not code or not name or name.startswith("."):
        return None
    f = MEDIA / ("_brands" if name.startswith("brand-") else code) / name
    return f if f.is_file() else None


def with_media_urls(data, code, base):
    """A copy of the analysis with every "media:" reference turned into a link
    the viewer's browser can load from this service."""
    d = copy.deepcopy(data or {})
    # Where the numbers came from is ours to know, not the client's.
    d.pop("source", None)

    def url(ref):
        if isinstance(ref, str) and ref.startswith("media:"):
            return base + "/api/creator-media?" + urllib.parse.urlencode({"c": code, "n": ref[6:]})
        return ref
    if d.get("photo"):
        d["photo_url"] = url(d.pop("photo"))
    for key in ("top_posts", "sponsored_posts"):
        for p in d.get(key) or []:
            p["thumb"] = url(p.get("thumb"))
    for b in d.get("brands") or []:
        b["logo"] = url(b.get("logo"))
    return d


def clean_json(doc):
    """A pasted JSON analysis, kept to the known shape."""
    if not isinstance(doc, dict):
        raise ValueError("The analysis must be a JSON object.")
    allowed = {k for k, _ in OVERVIEW} | {"audience", "audience_likers", "growth", "top_posts",
                                          "sponsored_posts", "brands", "hashtags"} | REPORT_EXTRA
    out = {k: v for k, v in doc.items() if k in allowed and k != "code"}
    if not isinstance(out.get("audience", {}), dict):
        raise ValueError("'audience' must be an object.")
    out.setdefault("audience", {})
    return json.loads(json.dumps(out))
