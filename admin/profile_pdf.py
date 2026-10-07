"""Profile report (PDF) -> creator analysis, inside the admin.

The same reader as tools/profile_import.py, kept here so the admin container
can use it without the tools/ folder. PyMuPDF is installed beside the admin
code (admin/_vendor) at deploy time; without it the upload says so plainly.
"""
import json, os, re, sys, tempfile, time
from pathlib import Path

_VENDOR = Path(__file__).resolve().parent / "_vendor"
if _VENDOR.is_dir():
    sys.path.insert(0, str(_VENDOR))



def num(s):
    m = re.search(r"[<>]?(-?[\d,]+(?:\.\d+)?)\s*([kKmM]?)", (s or "").replace("\u2212", "-"))
    if not m:
        return None
    n = float(m.group(1).replace(",", "")) * {"": 1, "k": 1e3, "m": 1e6}[m.group(2).lower()]
    return int(n) if n == int(n) else round(n, 2)


def lines(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"]).strip()
            if t:
                out.append((l["bbox"][0], l["bbox"][1], l["spans"][0]["size"], t))
    return out


def value_at(ls, y, minx=100):
    c = [l for l in ls if abs(l[1] - y) < 8 and l[0] > minx and l[3][0] in "0123456789<>"]
    return num(c[0][3]) if c else None


ISO = {"Egypt": "EG", "France": "FR", "Germany": "DE", "Indonesia": "ID", "Iran": "IR", "Iraq": "IQ",
       "Italy": "IT", "Kuwait": "KW", "Lebanon": "LB", "Saudi Arabia": "SA", "Turkey": "TR",
       "United Arab Emirates": "AE", "United States": "US", "United Kingdom": "GB", "Qatar": "QA",
       "Jordan": "JO", "Oman": "OM", "Bahrain": "BH", "Morocco": "MA", "Algeria": "DZ", "Tunisia": "TN",
       "Libya": "LY", "Sudan": "SD", "Syria": "SY", "Palestine": "PS", "Brazil": "BR", "India": "IN",
       "Spain": "ES", "Portugal": "PT", "Mexico": "MX", "Argentina": "AR", "Canada": "CA",
       "Russia": "RU", "Malaysia": "MY", "Singapore": "SG", "Philippines": "PH", "Bangladesh": "BD", "Afghanistan": "AF", "Somalia": "SO", "Ethiopia": "ET", "Kenya": "KE", "South Africa": "ZA", "Netherlands": "NL", "The Netherlands": "NL", "Belgium": "BE", "Sweden": "SE", "Norway": "NO", "Denmark": "DK", "Austria": "AT", "Poland": "PL", "Greece": "GR", "Japan": "JP", "South Korea": "KR", "China": "CN", "Thailand": "TH", "Vietnam": "VN", "Chile": "CL", "Peru": "PE", "Venezuela": "VE", "Ecuador": "EC", "Uruguay": "UY", "Paraguay": "PY", "Bolivia": "BO", "Ukraine": "UA", "Azerbaijan": "AZ", "Kazakhstan": "KZ", "Uzbekistan": "UZ", "Mauritania": "MR", "Senegal": "SN", "Ghana": "GH", "Cyprus": "CY", "Romania": "RO", "Hungary": "HU", "Czechia": "CZ", "Finland": "FI", "Puerto Rico": "PR", "Costa Rica": "CR", "Guatemala": "GT", "Panama": "PA", "Honduras": "HN", "El Salvador": "SV", "Nicaragua": "NI", "Cuba": "CU", "Haiti": "HT", "Jamaica": "JM", "Angola": "AO", "Cameroon": "CM", "Ivory Coast": "CI", "Côte d'Ivoire": "CI", "Sri Lanka": "LK", "Nepal": "NP", "Taiwan": "TW", "Hong Kong": "HK", "Yemen": "YE", "Palestinian Territories": "PS", "Australia": "AU", "Ireland": "IE", "New Zealand": "NZ", "Dominican Republic": "DO", "Switzerland": "CH", "Pakistan": "PK", "Nigeria": "NG", "Colombia": "CO",
       "Bulgaria": "BG", "Serbia": "RS", "Croatia": "HR", "Slovakia": "SK", "Slovenia": "SI", "Lithuania": "LT", "Latvia": "LV", "Estonia": "EE", "Iceland": "IS", "Luxembourg": "LU", "Malta": "MT", "Albania": "AL", "Georgia": "GE", "Armenia": "AM", "Belarus": "BY", "Moldova": "MD", "North Macedonia": "MK", "Bosnia and Herzegovina": "BA", "Kosovo": "XK", "Montenegro": "ME", "Mongolia": "MN", "Myanmar": "MM", "Cambodia": "KH", "Laos": "LA", "Brunei": "BN", "Maldives": "MV", "Bhutan": "BT", "Kyrgyzstan": "KG", "Tajikistan": "TJ", "Turkmenistan": "TM", "Zimbabwe": "ZW", "Zambia": "ZM", "Uganda": "UG", "Tanzania": "TZ", "Rwanda": "RW", "Mozambique": "MZ", "Madagascar": "MG", "Mali": "ML", "Niger": "NE", "Chad": "TD", "Burkina Faso": "BF", "Guinea": "GN", "Benin": "BJ", "Togo": "TG", "Liberia": "LR", "Sierra Leone": "SL", "Gabon": "GA", "Congo": "CG", "Democratic Republic of the Congo": "CD", "Namibia": "NA", "Botswana": "BW", "Malawi": "MW", "Djibouti": "DJ", "Eritrea": "ER", "Comoros": "KM", "Mauritius": "MU", "Trinidad and Tobago": "TT", "Bahamas": "BS", "Barbados": "BB", "Belize": "BZ", "Guyana": "GY", "Suriname": "SR", "Czech Republic": "CZ", "Türkiye": "TR", "Macao": "MO", "Somaliland": "SO", "Gambia": "GM", "Lesotho": "LS", "Eswatini": "SZ", "Burundi": "BI", "South Sudan": "SS", "Central African Republic": "CF", "Cape Verde": "CV", "Seychelles": "SC", "Fiji": "FJ", "Papua New Guinea": "PG", "Jersey": "JE", "Gibraltar": "GI"}
REACH = {"<500 accounts": "<500", "500-1k accounts": "500-1000",
         "1k-1.5k accounts": "1000-1500", ">1.5k accounts": ">1500"}


def table(text, title, colname, end_markers):
    """{'followers': [(label, pct)], 'likers': [...]} from a split table of the report."""
    i = text.find(title + "\n" + colname + "\n")
    if i < 0:
        return {}
    seg = text[i + len(title) + len(colname) + 2:]
    cut = min([seg.find("\n" + m) for m in end_markers if seg.find("\n" + m) >= 0] or [len(seg)])
    ls = seg[:cut].split("\n")
    cols = []
    while ls and ls[0] in ("Likers", "Followers"):
        cols.append(ls.pop(0).lower())
    out = {c: [] for c in cols}
    k = 0
    while k + len(cols) < len(ls) + 1 and k < len(ls):
        lab, vals = ls[k], ls[k + 1:k + 1 + len(cols)]
        k += 1 + len(cols)
        for c, v in zip(cols, vals):
            m = re.fullmatch(r"[\d,]+ / ([\d.]+)%", v.strip())
            if m:
                out[c].append((lab.strip(), float(m.group(1))))
    return out


# Bios whose Arabic lines come out of the PDF in visual order with broken
# shaping; corrected by hand from the report.
BIO_FIX = {
    "ayaah.hany": {2: "❥ممتنة لتفآصيلي الصغيرة وعآلمى الخآص بى🪴"},
    "ayahraafataly": {1: "دَع أخطائي جانباً، أنظر قليلاً لمحتواكِ"},
    "itssronaa": {0: "[من مر صدفة يصلي على النبي]♥️"},
    "reemalmasryyy": {1: "\"وَلَو كَانَ العُمرُ يُهدَى، لَأَهدَيتُ وَالِدَيَّ عُمرِي\"", 3: "{ لا إله إلا الله }"},
    "shereen_elenany1": {1: "أنا الكزن اللي في الرحلة ✨️"},
    "zahraahussein__": {3: "لطلب العرض الخاص لوقف الصلع الوراثي⬇️👇🏻"},
    "zienaqussay_": {0: "اللهم ارحم أبي🤍"},
}
BLUE = (0.2313999980688095, 0.5098000168800354, 0.9646999835968018)
MEDIAN = (0.7490000128746033, 0.8587999939918518, 0.9961000084877014)


def close(a, b):
    return a and b and all(abs(x - y) < 0.01 for x, y in zip(a, b))


def growth_line(page, ls, y_top, y_bot):
    """The blue line in one growth chart, read against its own grid and axis."""
    if y_top is None or y_bot is None:   # a chart the report left out (e.g. hidden likes)
        return []
    grid = sorted(set(round(d["rect"].y0) for d in page.get_drawings()
                      if y_top < d["rect"].y0 < y_bot and d["rect"].height < 2 and d["rect"].width > 400))
    ticks = [(y, num(t)) for x, y, s, t in ls if y_top < y < y_bot and x < 60 and s < 8 and num(t) is not None]
    months = sorted((x, t) for x, y, s, t in ls if y_top < y < y_bot and s < 8 and re.fullmatch(r"[A-Z][a-z]{2}", t))
    if len(ticks) < 2 or not months:
        return []
    # each tick label sits ~4pt above its grid line
    pts = []
    for ty, v in ticks:
        g = min(grid, key=lambda gy: abs(gy - (ty + 4))) if grid else ty + 4
        pts.append((g, v))
    (ya, va), (yb, vb) = max(pts), min(pts)
    val = lambda y: va + (ya - y) / (ya - yb) * (vb - va)
    line = [d for d in page.get_drawings() if y_top < d["rect"].y0 < y_bot and close(d.get("color"), BLUE) and not d.get("fill")]
    if not line:
        return []
    xy = []
    for it in line[0]["items"]:
        p0, p1 = it[1], it[-1]
        xy += [(p0.x, p0.y), (p1.x, p1.y)]
    xs = [x + 5 for x, t in months]          # label x is its left edge; ~5pt to centre
    out = {}
    for x, y in xy:
        i = min(range(len(xs)), key=lambda k: abs(xs[k] - x))
        if abs(xs[i] - x) < 4:
            out[months[i][1]] = val(y)
    return [(m, out[m]) for _, m in months if m in out]


def distribution(page, ls, y_top, y_bot):
    if y_top is None or y_bot is None:
        return None
    bars = sorted((d["rect"].x0, d["rect"].height, d.get("fill")) for d in page.get_drawings()
                  if y_top < d["rect"].y0 < y_bot and 55 < d["rect"].width < 70 and d["rect"].height > 3 and d.get("fill"))
    labels = sorted((x, t) for x, y, s, t in ls if y_top - 30 < y < y_bot and re.fullmatch(r"[<>]?\d+(\.\d+)?%", t))
    if len(bars) < 4:
        return None
    peak = max(h for _, h, _ in bars)
    out = {"buckets": [], "creator": None, "median": None}
    for i, (x, h, fill) in enumerate(bars):
        lab = min(labels, key=lambda l: abs(l[0] - x))[1] if labels else ""
        out["buckets"].append({"label": lab, "h": round(h / peak * 100, 1)})
        if close(fill, BLUE): out["creator"] = i
        if close(fill, MEDIAN): out["median"] = i
    return out


def parse(path, handle):
    import fitz
    doc = fitz.open(path); page = doc[0]
    ls, text = lines(page), page.get_text()
    by = lambda t: next((y for x, y, s, t2 in ls if t2 == t), None)
    a = {"platform": "Instagram", "handle": handle, "source": "report Oct 2026",
         "updated": "2026-10-0" + ("1" if "Oct-01" in path else "6")}
    acct = next((t for x, y, s, t in ls if " account" in t and y < 130), "")
    a["account_type"] = "Business" if acct.startswith("Business") else "Creator"
    if "•" in acct: a["location"] = acct.split("•", 1)[1].strip()
    # The numbers row sits under its "Followers" label, which moves up when the
    # report has no location line — find it rather than assuming a height.
    label_y = next((y for x, y, s, t in ls if t == "Followers" and y < 200), 139)
    for x, y, s, t in ls:
        if label_y + 6 < y < label_y + 21:
            parts = t.split()
            if x < 150:
                a["followers"] = num(parts[0])
                if len(parts) > 1: a["followers_change_pct"] = num(parts[1])
            elif x < 350:
                if parts[0] == "Hidden": a["likes_hidden"] = True
                else: a["avg_likes"] = num(parts[0])
                if len(parts) > 1: a["avg_likes_change_pct"] = num(parts[1])
            else:
                a["er"] = num(t)
    pp = by("Popular posts")
    bio = [t for x, y, s, t in sorted(ls, key=lambda l: l[1]) if label_y + 26 < y < pp and x < 40]
    for i, fixed in BIO_FIX.get(handle, {}).items():
        bio[i] = fixed
    if bio: a["bio"] = "\n".join(bio)

    sect = None
    keys = {
        (None, "Fake followers"): "fake_followers_pct", (None, "Real people"): "real_people_pct",
        (None, "Notable followers"): "notable_followers_pct",
        (None, "Real mass followers"): "mass_followers_pct", (None, "Suspicious mass"): "suspicious_mass_pct",
        (None, "Suspicious accounts"): "suspicious_pct",
        ("All content", "Estimated impressions"): "est_impressions", ("All content", "Estimated reach"): "est_reach",
        ("All content", "Average comments"): "avg_comments",
        ("Reels", "Average reel plays"): "avg_reel_plays",
        ("Reels", "Average likes"): "avg_reel_likes", ("Reels", "Average comments"): "avg_reel_comments",
        ("Reels", "Average shares"): "avg_reel_shares",
        ("Stories", "Estimated reach"): "story_reach", ("Stories", "Estimated impressions"): "story_impressions",
        ("Collaborations", "Paid engagement"): "paid_post_performance", ("Collaborations", "Paid views"): "paid_views_pct",
    }
    reach = []
    for x, y, s, t in sorted(ls, key=lambda l: l[1]):
        if x > 40 or s > 9.5:
            continue
        if t in ("All content", "Reels", "Stories", "Collaborations"):
            sect = t; continue
        if y > 2300: break
        if t == "Engagement rate" and sect in ("All content", "Reels"):
            big = [l for l in ls if abs(l[1] - y) < 10 and l[0] > 100]
            if big:
                m = re.match(r"([\d.]+)%\s*(.*)", big[0][3])
                if m:
                    a["er" if sect == "All content" else "reels_er"] = float(m.group(1)) if sect == "Reels" else a.get("er", float(m.group(1)))
                    if m.group(2): a["er_note" if sect == "All content" else "reels_er_note"] = m.group(2).strip()
            continue
        v = value_at(ls, y)
        k = keys.get((sect, t))
        if k and v is not None: a[k] = v
        if t in REACH and v is not None: reach.append({"name": REACH[t], "pct": v})

    # audience, followers and likers
    ends = ["Languages", "Age split", "Male age split", "Female age split", "Location by Country",
            "Location by City", "Audience interests", "Audience brand affinity", "Something went wrong"]
    specs = [("gender", "Gender split", "Gender"), ("ages", "Age split", "Age"),
             ("ages_male", "Male age split", "Age"), ("ages_female", "Female age split", "Age"),
             ("countries", "Location by Country", "Country"), ("cities", "Location by City", "City"),
             ("languages", "Languages", "Language"), ("interests", "Audience interests", "Interests"),
             ("brand_affinity", "Audience brand affinity", "Brand")]
    aud = {"followers": {}, "likers": {}}
    for sec, title, col in specs:
        for who, rows in table(text, title, col, ends).items():
            d = aud[who]
            for lab, p in rows:
                if sec == "gender":
                    d.setdefault("gender", {})[lab.lower()] = p
                elif sec == "countries":
                    if lab not in ISO:
                        print("  ! %s: country %r has no code here — left out; add it to ISO" % (handle, lab))
                        continue
                    d.setdefault("countries", []).append({"code": ISO[lab], "pct": p})
                else:
                    if sec == "interests": lab = lab[0].upper() + lab[1:]
                    d.setdefault(sec, []).append({"name": lab, "pct": p})
    if reach: aud["followers"]["reachability"] = reach
    a["audience"] = aud["followers"]
    if aud["likers"]: a["audience_likers"] = aud["likers"]

    # growth: followers and avg likes, one point per month on the chart
    gf = growth_line(page, ls, by("Followers growth"), by("Likes growth"))
    gl = growth_line(page, ls, by("Likes growth"), by("Fake followers distribution"))
    year = {m: (2025 if m in ("Nov", "Dec") else 2026) for m in ("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}
    mnum = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}
    if gf:
        likes = dict(gl)
        a["growth"] = [{"month": "%d-%02d" % (year[m], mnum[m]), "followers": int(round(v, -2)),
                        "avg_likes": int(round(likes[m])) if m in likes else None} for m, v in gf]
    a["fake_followers_dist"] = distribution(page, ls, by("Fake followers distribution"), by("Content"))
    a["er_dist"] = distribution(page, ls, by("Engagement rate distribution"), by("Creator brand affinity") or by("Creator Interests") or by("Audience data by followers"))

    def side(title, stop):
        i = text.find(title + "\n")
        if i < 0: return ""
        seg = text[i + len(title) + 1:]
        return seg[:min([seg.find(s) for s in stop if seg.find(s) >= 0] or [len(seg)])]
    brands = [b for b in side("Creator brand affinity", ["Creator Interests", "Audience data"]).split("\n") if b.strip()]
    if brands: a["brands"] = [{"name": b, "count": None, "logo": None} for b in brands]
    ci = [b for b in side("Creator Interests", ["Audience data"]).split("\n") if b.strip()]
    if ci: a["creator_interests"] = ci
    tags = []
    for title, stop in (("Popular hashtags", ["Popular mentions"]), ("Popular mentions", ["Gender split"])):
        for m in re.finditer(r"([#@][^\n]*?)\n?([\d.]+)%", side(title, stop)):
            tag = m.group(1).strip()
            if re.search(r"[\u0600-\u06FF]", tag):
                # the PDF holds Arabic in visual order: words of a tag come out reversed
                tag = tag[0] + "_".join(reversed(tag[1:].split("_")))
            tags.append({"tag": tag, "count": float(m.group(2))})
    if tags: a["hashtags"] = tags

    # media: profile photo and the cover of each popular post
    media = {}
    infos = page.get_image_info(xrefs=True)
    ph = [i for i in infos if i["bbox"][1] < 40 and i["width"] >= 150]
    if ph:
        media["photo"] = doc.extract_image(ph[0]["xref"])
    links = [l for l in page.get_links() if re.search(r"(instagram|tiktok)\.com/", l.get("uri") or "")]
    links.sort(key=lambda l: (round(l["from"].y0), l["from"].x0))
    # each number under a post sits right of its icon: a heart (likes) or a
    # speech bubble (comments); a post with hidden likes shows only the bubble
    icons = [(d["rect"].x0, d["rect"].y0, "likes" if d["rect"].width > 10 else "comments")
             for d in page.get_drawings() if pp < d["rect"].y0 < pp + 420
             and 8.5 < d["rect"].height < 10.5 and 8.5 < d["rect"].width < 11.5 and len(d["items"]) >= 20]
    stats = []
    for x, y, s_, t in ls:
        if pp < y < pp + 420 and s_ < 9.5 and num(t) is not None:
            near = [ic for ic in icons if abs(ic[1] - y) < 5 and 0 < x - ic[0] < 20]
            if near: stats.append((x, y, max(near)[2], num(t)))
    posts = []
    for n, l in enumerate(links):
        R = l["from"]
        cand = [i for i in infos if i["height"] >= 300 and R.x0 - 2 <= (i["bbox"][0] + i["bbox"][2]) / 2 <= R.x1 + 2
                and R.y0 - 2 <= (i["bbox"][1] + i["bbox"][3]) / 2 <= R.y1 + 2]
        name = None
        if cand:
            name = "post-%d" % (n + 1)
            media[name] = doc.extract_image(cand[0]["xref"])
        mine = {k: v for x, y, k, v in stats if R.x0 - 2 <= x <= R.x1 and R.y0 <= y <= R.y1 + 40}
        lk, cm = mine.get("likes"), mine.get("comments")
        posts.append({"url": l["uri"], "thumb": name, "likes": lk, "comments": cm, "views": None, "date": None, "brand": None})
    a["top_posts"] = posts
    return a, media





def fix_er(a):
    """The report's headline engagement rate is sometimes 0.00% for an account
    that plainly has likes and comments. Showing 0% is wrong, so work it out
    from the averages the same report gives, and say so. Returns True if it
    changed anything."""
    f, lk, cm = a.get("followers"), a.get("avg_likes"), a.get("avg_comments")
    if not a.get("er") and f and ((lk or 0) + (cm or 0)) > 0:
        a["er"] = round(((lk or 0) + (cm or 0)) / f * 100, 2)
        a["er_note"] = "calculated from average likes and comments (the report showed 0.00%)"
        return True
    return False


def available():
    try:
        import fitz  # noqa: F401
        return True
    except Exception:
        return False


def sniff_creator(data, resolver):
    """The creator a report PDF belongs to, read from the PDF itself: first the
    profile links on page 1, then any roster handle printed there. Returns a
    code only when exactly one creator fits."""
    import fitz, analysis
    try:
        page = fitz.open(stream=data, filetype="pdf")[0]
        links = [l.get("uri") or "" for l in page.get_links()]
        text = page.get_text()
    except Exception:
        return None
    found = set()
    for uri in links:
        n = analysis.norm(analysis.handle_from(uri)) if analysis.is_link(uri) else ""
        found.update(resolver.by_handle.get(n, []))
    if len(found) == 1:
        return next(iter(found))
    found = set()
    for w in set(re.findall(r"[A-Za-z0-9._]{4,}", text)):
        found.update(resolver.by_handle.get(analysis.norm(w), []))
    return next(iter(found)) if len(found) == 1 else None


def detect_platform(data):
    """Which platform a report PDF is about, or None. The post links in it are
    the surest sign (every popular post links to its own platform); the words on
    the first page are the fallback."""
    import fitz
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        uris = " ".join((l.get("uri") or "") for p in doc for l in p.get_links()).lower()
        text = doc[0].get_text().lower()
    except Exception:
        return None
    tik, ins = uris.count("tiktok.com"), uris.count("instagram.com")
    if tik != ins:
        return "TikTok" if tik > ins else "Instagram"
    tik, ins = "tiktok" in text, "instagram" in text
    return "TikTok" if tik and not ins else "Instagram" if ins and not tik else None


def completeness(doc):
    """How much a document holds: every non-empty value, nested, counted once."""
    if isinstance(doc, dict):
        return sum(completeness(v) for v in doc.values())
    if isinstance(doc, list):
        return sum(completeness(v) for v in doc)
    return 0 if doc in (None, "", False) else 1


def import_pdf(data, code, handle=None, source=None, platform=None):
    """Read one profile report PDF and store it as creator `code`'s analysis
    for one platform (given, else read off the report, else their main one),
    pictures included. A TikTok report in the same layout is read the same
    way; what the report does not carry is simply absent. Returns the stored
    document."""
    import analysis, db
    if not available():
        raise RuntimeError("The PDF reader (PyMuPDF) is not installed on this server yet.")
    if db.creator(code) is None:
        raise ValueError("Unknown creator " + code)
    platform = analysis.canon_platform(platform) or detect_platform(data)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as t:
        t.write(data)
        path = t.name
    try:
        handle = handle or (db.creator(code)["name"] or code)
        a, media = parse(path, handle)
    finally:
        os.unlink(path)
    fix_er(a)
    if not platform:
        # Nothing in the report names its platform (a channel report with no posts
        # to link): the platform whose follower count it matches, else their main one.
        crow = db.creator(code)
        near = [analysis.canon_platform(p.get("platform")) for p in db.split_profiles(crow["profiles"] or "")
                if p.get("followers") and a.get("followers") and abs(p["followers"] - a["followers"]) <= 0.08 * a["followers"]]
        platform = next((p for p in near if p), None) or db.platforms_of(code)[0]
    a["platform"] = platform
    a["updated"] = time.strftime("%Y-%m-%d", time.gmtime())
    a["source"] = source or "profile report PDF"
    d = analysis.MEDIA / code
    d.mkdir(parents=True, exist_ok=True)
    # Instagram keeps the file names it always had; another platform's pictures
    # get their own, so a TikTok import cannot overwrite the Instagram ones.
    pre = "" if platform == "Instagram" else platform.lower() + "-"
    for k, im in media.items():
        fn = "%s%s.%s" % (pre, k, im["ext"])
        (d / fn).write_bytes(im["image"])
        if k == "photo":
            a["photo"] = "media:" + fn
        for p in a["top_posts"]:
            if p["thumb"] == k:
                p["thumb"] = "media:" + fn
    brands = analysis.MEDIA / "_brands"
    for b in a.get("brands") or []:
        s = "brand-" + "".join(c for c in __import__("unicodedata").normalize("NFKD", b["name"].lower()).encode("ascii", "ignore").decode() if c.isalnum()) + ".png"
        if not b.get("logo") and (brands / s).is_file():
            b["logo"] = "media:" + s
    # The same report uploaded twice in one go: keep the fuller copy, not just the later one.
    cur = db.analysis(code, platform)
    if cur and cur["source"] == a["source"] and db.now() - (cur["updated_at"] or 0) < 900 \
            and completeness(cur["data"]) > completeness(a):
        a["_kept_existing"] = True
        return a
    db.save_analysis(code, a, a["source"], platform=platform)
    return a
