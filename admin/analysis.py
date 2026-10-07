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
    ("code", "Creator (code, @handle or name)"), ("platform", "Platform"), ("handle", "Handle"),
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
PLATFORM_COL = "Platform (Instagram / TikTok / … — empty means the Overview row's, else their main one)"
# The platforms an analysis can be about, in the order they are offered.
PLATFORMS = ["Instagram", "TikTok", "Snapchat", "YouTube", "X", "Facebook"]
_PLAT_ALIASES = {"ig": "Instagram", "insta": "Instagram", "instagram": "Instagram", "tiktok": "TikTok", "tik tok": "TikTok",
                 "tt": "TikTok", "snapchat": "Snapchat", "snap": "Snapchat", "sc": "Snapchat", "youtube": "YouTube",
                 "yt": "YouTube", "x": "X", "twitter": "X", "facebook": "Facebook", "fb": "Facebook"}


def canon_platform(v):
    """"tiktok", "TikTok " or "tik tok" -> "TikTok"; None when it names none of ours."""
    t = re.sub(r"\s+", " ", str(v or "").strip().lower())
    return _PLAT_ALIASES.get(t)


def creator_platforms(row):
    """The platforms a creator is on, main one first: the roster's platform
    field (it may hold several: "Instagram, Snapchat") and their profile links."""
    out = []
    try:
        profiles = json.loads(row["profiles"] or "[]")
    except (ValueError, TypeError, KeyError, IndexError):
        profiles = []
    try:
        main = row["platform"] or ""
    except (KeyError, IndexError):
        main = ""
    cands = re.split(r"[,&/+]|\band\b", main) + [p.get("platform") for p in profiles if isinstance(p, dict)]
    for c in cands:
        c = canon_platform(c)
        if c and c not in out:
            out.append(c)
    return out or ["Instagram"]


def handle_on(row, platform):
    """The creator's handle on one platform, from the profile link for it."""
    try:
        profiles = json.loads(row["profiles"] or "[]")
    except (ValueError, TypeError, KeyError, IndexError):
        profiles = []
    for p in profiles:
        if isinstance(p, dict) and canon_platform(p.get("platform")) == platform and is_link(p.get("url")):
            h = handle_from(p["url"])
            if h:
                return h
    return (row["handle"] or "").lstrip("@") if platform == creator_platforms(row)[0] else ""


SHEETS = {
    "Overview": [label for _, label in OVERVIEW],
    "Audience": ["Creator (code, @handle or name)", "Section (" + " / ".join(AUDIENCE_SECTIONS) + ")",
                 "Label (country code SA, city, female/male, 18-24, …)", "Percent",
                 "Audience of (followers / likers — empty means followers)", PLATFORM_COL],
    "Growth": ["Creator (code, @handle or name)", "Month (YYYY-MM)", "Followers", "Avg likes (optional)", PLATFORM_COL],
    "Posts": ["Creator (code, @handle or name)", "Kind (top / sponsored)", "Post link", "Image link (optional)",
              "Date (YYYY-MM-DD)", "Likes", "Comments", "Views", "Brand (sponsored)", PLATFORM_COL],
    "Brands": ["Creator (code, @handle or name)", "Brand", "Posts mentioning it", "Logo link or website (optional)", PLATFORM_COL],
    "Hashtags": ["Creator (code, @handle or name)", "Hashtag or @mention", "Times used or %", PLATFORM_COL],
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


def norm(s):
    """A name or handle reduced to what identifies it: lower case, no @, no
    spaces or punctuation, so "@Sara.Ali", "sara ali" and "SaraAli" agree."""
    return re.sub(r"[^\w]+", "", str(s or "").lower().lstrip("@"), flags=re.UNICODE).replace("_", "")


_NOT_HANDLES = {"p", "reel", "reels", "explore", "stories", "watch", "channel", "video", "tv", "accounts", "share"}


def handle_from(text):
    """The handle in a pasted profile link or @mention, else the text itself.
    A link to a post or reel names no creator, so it gives back nothing."""
    t = str(text or "").strip()
    m = re.search(r"(?:instagram|tiktok|snapchat|twitter|x|youtube|facebook|threads)\.(?:com|net)/(?:add/|@|user/|c/)?([A-Za-z0-9._]+)", t)
    if m:
        return "" if m.group(1).lower() in _NOT_HANDLES else m.group(1)
    return t


def is_link(text):
    return bool(re.match(r"\s*(https?://|www\.)", str(text or ""), re.I))


class Resolver:
    """Finds a creator from whatever the person typed: the HV code, the
    handle (with or without @, or a profile link), or the name. Anything that
    is not exact is offered as a suggestion, never silently guessed."""

    def __init__(self, creators, aliases=None):
        self.by_code = {}
        self.by_handle, self.by_name = {}, {}
        self.aliases = {norm(k): v for k, v in (aliases or {}).items()}
        self.label = {}
        for c in creators:
            code = c["code"]
            self.by_code[code.upper()] = code
            self.label[code] = c
            for table, val in ((self.by_handle, c["handle"]), (self.by_name, c["name"])):
                n = norm(val)
                if n and code not in table.get(n, []):
                    table.setdefault(n, []).append(code)
            # The same person's other accounts: their profile links name handles too.
            try:
                profiles = json.loads(c["profiles"] or "[]")
            except (ValueError, TypeError, KeyError, IndexError):
                profiles = []
            for item in profiles if isinstance(profiles, list) else []:
                url = item.get("url") if isinstance(item, dict) else None
                n = norm(handle_from(url)) if is_link(url) else ""
                if n and code not in self.by_handle.get(n, []):
                    self.by_handle.setdefault(n, []).append(code)
        self._fuzzy_keys = None

    def resolve(self, key, platform=None):
        """(code or None, [suggested codes]). A code is returned only when
        exactly one creator fits; when several share a handle, the platform
        (if the sheet says one) breaks the tie."""
        raw = str(key or "").strip()
        up = raw.upper()
        if up in self.by_code:
            return self.by_code[up], []
        n = norm(raw)
        alias = self.aliases.get(n)
        if alias and alias in self.label:
            return alias, []
        for table in (self.by_handle, self.by_name):
            for probe in (n, norm(handle_from(raw))):
                hits = table.get(probe) or []
                if len(hits) == 1:
                    return hits[0], []
                if len(hits) > 1 and platform:
                    same = [h for h in hits if (self.label[h]["platform"] or "").lower() == platform.strip().lower()]
                    if len(same) == 1:
                        return same[0], []
                if len(hits) > 1:
                    return None, hits[:8]
        return None, self.suggest(raw)

    def suggest(self, raw, limit=5):
        import difflib
        n = norm(handle_from(raw))
        if not n:
            return []
        if self._fuzzy_keys is None:
            self._fuzzy_keys = {}
            for table in (self.by_handle, self.by_name):
                for k, codes in table.items():
                    self._fuzzy_keys.setdefault(k, []).extend(codes)
        out = []
        for k in difflib.get_close_matches(n, list(self._fuzzy_keys), n=limit, cutoff=0.72):
            for code in self._fuzzy_keys[k]:
                if code not in out:
                    out.append(code)
        # A partial name ("sara" for "Sara Ali") is also worth offering.
        if len(out) < limit and len(n) >= 3:
            for k, codes in self._fuzzy_keys.items():
                if n in k:
                    for code in codes:
                        if code not in out:
                            out.append(code)
        return out[:limit]

    def describe(self, code):
        c = self.label.get(code)
        if not c:
            return code
        h = ("@" + c["handle"].lstrip("@")) if c["handle"] else ""
        return "%s · %s%s%s" % (code, c["name"], (" · " + h) if h else "",
                                (" · " + c["platform"]) if c["platform"] else "")


def code_from_pick(text):
    """The creator code at the front of a review-screen entry ("HV-MC-001 · Name")."""
    m = re.match(r"\s*([A-Za-z0-9]+(?:-[A-Za-z0-9]+)+)", str(text or ""))
    return m.group(1).upper() if m else None


# What a prefilled workbook asks for under each section, so the numbers can
# be typed straight in.
AUDIENCE_SKELETON = [("gender", "female"), ("gender", "male"),
                     ("ages", "13-17"), ("ages", "18-24"), ("ages", "25-34"), ("ages", "35-44"), ("ages", "45+"),
                     ("countries", "SA"), ("countries", "AE"), ("countries", "EG")]


# Cells with a fixed set of answers are dropdowns in the workbook, so they are
# picked, never typed. They are offered, not enforced: a city or an interest
# the list does not know can still be typed.
COUNTRY_CODES = ["SA", "AE", "EG", "KW", "QA", "BH", "OM", "JO", "LB", "IQ", "MA", "TN", "DZ", "SD", "SY", "YE", "US", "GB"]
LABELS = ["female", "male", "13-17", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"] + COUNTRY_CODES
OPTION_LISTS = [("Platform", PLATFORMS), ("Section", AUDIENCE_SECTIONS), ("Audience of", ["followers", "likers"]),
                ("Post kind", ["top", "sponsored"]), ("Label (gender, age, country)", LABELS),
                ("Account type", ["Creator", "Business"])]


def _letter(i):
    out = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


def options_sheet():
    """The Options sheet the dropdowns read from: one column per list."""
    longest = max(len(v) for _, v in OPTION_LISTS)
    rows = [[name for name, _ in OPTION_LISTS]] + [
        [(vals[i] if i < len(vals) else "") for _, vals in OPTION_LISTS] for i in range(longest)]
    return ("Options", rows, {i: 24 for i in range(len(OPTION_LISTS))}, None)


def dropdowns(order):
    """Validations for the analysis sheets. `order` is the workbook's sheet
    names in order; the Options sheet must be among them."""
    idx = {n: i for i, n in enumerate(order, start=1)}
    ref = lambda col, n: "Options!$%s$2:$%s$%d" % (_letter(col), _letter(col), n + 1)
    plat, sect, aud, kind, label, acct = (ref(i, len(v)) for i, (_, v) in enumerate(OPTION_LISTS))
    keys = [k for k, _ in OVERVIEW]
    rules = [(idx["Overview"], "B2:B3000", plat),
             (idx["Overview"], "%s2:%s3000" % ((_letter(keys.index("account_type")),) * 2), acct),
             (idx["Audience"], "B2:B6000", sect), (idx["Audience"], "C2:C6000", label),
             (idx["Audience"], "E2:E6000", aud), (idx["Audience"], "F2:F6000", plat),
             (idx["Growth"], "E2:E6000", plat),
             (idx["Posts"], "B2:B6000", kind), (idx["Posts"], "J2:J6000", plat),
             (idx["Brands"], "E2:E6000", plat), (idx["Hashtags"], "D2:D6000", plat)]
    return rules


def template_xlsx(creators=None, code=None, missing=(), platform=None):
    """The template. With `creators` (roster rows) it comes prefilled: the
    identity and platform are on every row and the Audience sheet carries the
    usual questions, so only numbers are typed. `platform` makes it the
    template for that platform's analysis (each creator's handle there is
    filled in); empty means each creator's main platform."""
    sheets = []
    if creators:
        plat = canon_platform(platform)
        for name, header in SHEETS.items():
            pcol = len(header) - 1 if name != "Overview" else 1
            rows = [header + ["Name (for reference, ignored)"]]
            for c in creators:
                p = plat or creator_platforms(c)[0]

                def pad(row, c=c, p=p):
                    row = row + [""] * (len(header) - len(row))
                    row[pcol] = p
                    return row + [c["name"]]
                if name == "Overview":
                    rows.append(pad([c["code"], p, handle_on(c, p)]))
                elif name == "Audience":
                    for sec, label in AUDIENCE_SKELETON:
                        rows.append(pad([c["code"], sec, label]))
                else:
                    rows.append(pad([c["code"]]))
            sheets.append((name, rows, {i: 22 for i in range(len(header) + 1)}, None))
        ref = [["Code", "Name", "Handle", "Platforms"]] + [
            [c["code"], c["name"], c["handle"] or "", ", ".join(creator_platforms(c))] for c in creators] + [
            ["NOT FOUND", m, "", ""] for m in missing]
        sheets.append(("Creators (reference)", ref, {0: 16, 1: 28, 2: 24, 3: 24}, None))
        sheets.append(options_sheet())
        return xlsx.write_book(sheets, dropdowns([s_[0] for s_ in sheets]))
    for name, header in SHEETS.items():
        example = [code if (code and v == "HV-XX-000") else v for v in EXAMPLE[name]]
        sheets.append((name, [header, example], {i: 22 for i in range(len(header))}, None))
    sheets.append(options_sheet())
    return xlsx.write_book(sheets, dropdowns([s_[0] for s_ in sheets]))


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


def parse_workbook(data, resolver, picks=None):
    """(docs {(code, platform): analysis}, problems, unresolved {key: [codes]}).

    The first column of every row names the creator — code, @handle or name.
    The platform comes from the row's Platform column, else from that
    creator's Overview row, else their main platform, so one workbook can hold
    a creator's Instagram and TikTok side by side. A name that fits more than
    one creator, or none, is listed in `unresolved` so the admin can pick;
    `picks` {key: code or ""} carries those answers on a second pass (an empty
    answer skips the rows). The example rows and rows with nothing but the
    identity filled in are ignored."""
    book = xlsx.read_all(data)
    picks = {norm(k): v for k, v in (picks or {}).items()}
    docs, problems, unresolved = {}, [], {}
    ov_plat = {}                                   # code -> platforms named on its Overview rows

    def rows(name):
        table = book.get(name) or []
        return [r for r in table[1:] if any(c.strip() for c in r)]

    def cell(r, i):
        return r[i].strip() if len(r) > i else ""

    def who(key, platform=None, alt=()):
        """The creator `key` names; when the first column is empty or unknown,
        the handle or profile link on the same row (`alt`) is tried before asking."""
        key = (key or "").strip()
        if key.upper().startswith("HV-XX"):
            return None
        code, suggestions = (None, [])
        for k in [key] + [a.strip() for a in alt if a and a.strip()]:
            if not k:
                continue
            code, suggestions = resolver.resolve(k, platform)
            if code:
                break
        key = key or next((a.strip() for a in alt if a and a.strip()), "")
        if not key:
            return None
        if code is None:
            pick = picks.get(norm(key))
            if pick:
                return pick
            if pick is None:
                unresolved.setdefault(key, suggestions)
            return None
        return code

    def doc(key, platform_cell="", alt=()):
        code = who(key, canon_platform(platform_cell), alt)
        if code is None:
            return None
        plat = canon_platform(platform_cell)
        if not plat:
            named = ov_plat.get(code) or []
            plat = named[0] if len(named) == 1 else creator_platforms(resolver.label[code])[0]
        return docs.setdefault((code, plat), {"audience": {}, "platform": plat})

    keys = [k for k, _ in OVERVIEW]
    for r in rows("Overview"):
        r = r + [""] * (len(keys) - len(r))
        vals = {}
        for i, k in enumerate(keys[1:], start=1):
            v = r[i].strip()
            if v:
                vals[k] = v if k in TEXT_KEYS else _num(v)
        # Platform and handle come prefilled; they alone are not data.
        if not {k for k, v in vals.items() if v is not None} - {"platform", "handle"}:
            continue
        code = who(r[0], canon_platform(vals.get("platform")), [vals.get("handle")] + [c for c in r if is_link(c)])
        if code is None:
            continue
        plat = canon_platform(vals.get("platform")) or creator_platforms(resolver.label[code])[0]
        ov_plat.setdefault(code, [])
        if plat not in ov_plat[code]:
            ov_plat[code].append(plat)
        d = docs.setdefault((code, plat), {"audience": {}, "platform": plat})
        d.update({k: v for k, v in vals.items() if (v is not None or k in TEXT_KEYS) and k != "platform"})
        d["platform"] = plat
    for r in rows("Audience"):
        pct = _num(cell(r, 3))
        if pct is None:
            continue
        section, label = cell(r, 1).lower().replace(" ", "_"), cell(r, 2)
        d = doc(r[0], cell(r, 5))
        if d is None:
            continue
        if section not in AUDIENCE_SECTIONS or not label:
            problems.append("Audience row for %s skipped: section '%s'." % (r[0], r[1]))
            continue
        who_ = cell(r, 4).lower()
        aud = d.setdefault("audience_likers", {}) if who_.startswith("lik") else d["audience"]
        if section == "gender":
            aud.setdefault("gender", {})[label.lower()] = pct
        elif section == "countries":
            aud.setdefault("countries", []).append({"code": label.upper()[:2], "pct": pct})
        else:
            aud.setdefault(section, []).append({"name": label, "pct": pct})
    for r in rows("Growth"):
        followers = _intish(cell(r, 2))
        if followers is None:
            continue
        d = doc(r[0], cell(r, 4))
        if d is None:
            continue
        d.setdefault("growth", []).append({"month": cell(r, 1)[:7], "followers": followers,
                                           "avg_likes": _intish(cell(r, 3))})
    for r in rows("Posts"):
        if not cell(r, 2).startswith("https://"):
            continue
        d = doc(r[0], cell(r, 9))
        if d is None:
            continue
        r = r + [""] * (9 - len(r))
        kind = "sponsored_posts" if r[1].strip().lower().startswith("spon") else "top_posts"
        d.setdefault(kind, []).append({
            "url": r[2].strip(), "thumb": r[3].strip() if r[3].startswith("https://") else None,
            "date": r[4].strip()[:10] or None, "likes": _intish(r[5]), "comments": _intish(r[6]),
            "views": _intish(r[7]), "brand": r[8].strip() or None})
    for sheet, key, fields, pidx in (("Brands", "brands", ("name", "count", "logo"), 4),
                                     ("Hashtags", "hashtags", ("tag", "count"), 3)):
        for r in rows(sheet):
            if not cell(r, 1):
                continue
            d = doc(r[0], cell(r, pidx))
            if d is None:
                continue
            vals = (r[1:] + [""] * len(fields))[:len(fields)]
            item = {}
            for f, v in zip(fields, vals):
                item[f] = _num(v) if f in ("count", "followers") else (v.strip() or None)
            if item.get(fields[0]):
                d.setdefault(key, []).append(item)
    # A creator whose rows held nothing is not an analysis.
    docs = {c: d for c, d in docs.items()
            if any(v for k, v in d.items() if k not in ("audience", "platform")) or d["audience"]}
    for d in docs.values():
        for aud in (d["audience"], d.get("audience_likers") or {}):
            for k in ("countries", "cities", "ages", "languages", "interests", "brand_affinity"):
                if k in aud:
                    aud[k].sort(key=lambda x: -(x.get("pct") or 0))
        if "growth" in d:
            d["growth"].sort(key=lambda x: x["month"])
    return docs, problems, unresolved


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


# --------------------------------------------------------- held uploads --
# An upload that names creators we cannot match waits here (client data: not
# in git) while the admin picks who each one is; a day later it is gone.
PENDING = Path(__file__).resolve().parent / "analysis_pending"


def stash(kind, files):
    """Hold [(name, bytes)] for the review screen; returns its token."""
    import secrets, shutil, time
    PENDING.mkdir(exist_ok=True)
    for d in PENDING.iterdir():
        if d.is_dir() and time.time() - d.stat().st_mtime > 86400:
            shutil.rmtree(d, ignore_errors=True)
    token = secrets.token_hex(12)
    d = PENDING / token
    d.mkdir()
    for i, (_, data) in enumerate(files):
        (d / ("%d.bin" % i)).write_bytes(data)
    (d / "meta.json").write_text(json.dumps({"kind": kind, "names": [n for n, _ in files]}))
    return token


def held(token):
    """(kind, [(name, bytes)]) for a token, or None when it is gone."""
    if not re.fullmatch(r"[0-9a-f]{24}", str(token or "")):
        return None
    d = PENDING / token
    try:
        meta = json.loads((d / "meta.json").read_text())
        return meta["kind"], [(n, (d / ("%d.bin" % i)).read_bytes()) for i, n in enumerate(meta["names"])]
    except (OSError, ValueError, KeyError):
        return None


def release(token):
    import shutil
    if re.fullmatch(r"[0-9a-f]{24}", str(token or "")):
        shutil.rmtree(PENDING / token, ignore_errors=True)
