"""The competitor-evidence Excel template (owner, 2026-10-15): download it, fill it, upload it, and the
portal does the rest. It replaces running build_evidence_pack.py / build_tiktok_pack.py on a study
workbook and uploading their JSON (which still works).

Four sheets: Instructions, Brands (the client's brands and each competitor's fit), Posts (one row per
competitor collab post) and Creators (optional: every platform link of a creator, used when the pack's
creators are added to the roster). A Lists sheet feeds the dropdowns.

Only what a person has to look up is asked for. The import works out the rest itself, the same way
the scripts did: relevance to the client's product (from the brand's match words), engagement on
views, views per follower, views against the competitor's average, and a rating from that. The best
creators per competitor are ranked when the pack is read (evidence.creators_of), never stored.

Stdlib only (admin/xlsx.py): openpyxl is not in the admin image and is not installed there."""
import datetime
import re
import statistics

import xlsx

FITS = ("direct", "partial", "off-product")
PLATFORMS = ("instagram", "tiktok")
TYPES = ("influencer", "hcp")
YES_NO = ("Yes", "No")
# Collab type: the label people pick -> the stored code (evidence.COLLAB_LABEL is the reverse).
COLLABS = (("Co-author", "co_author"), ("Co-author + paid", "co_author_paid"), ("Own post, tagged", "creator_post_tag"),
           ("Own post + paid", "creator_post_tag_paid"), ("On brand page", "brand_page"),
           ("TikTok best video (median figures)", "tiktok_summary"))
COLLAB_CODE = {k.lower(): v for k, v in COLLABS}
COLLAB_CODE.update({v: v for _, v in COLLABS})
# Product tags that mean "the post does not say which product" (the study's own marker included).
UNSPECIFIED = ("غير محدد من الكابشن", "not named", "not specified", "unspecified")

BRAND_COLS = (("brand", "Brand", "Alpha Plus"),
              ("product", "Product description", "Brightening / dark spots: Vitamin C serum, cream, SPF30"),
              ("match_tags", "Match words (comma separated)", "Vitamin C, dark spots, serum"),
              ("competitor", "Competitor", "Garnier"),
              ("fit", "Competitor fit", "partial"))
POST_COLS = (("brand", "Brand", "Alpha Plus", "Must be on the Brands sheet."),
             ("competitor", "Competitor", "Garnier", "Must be listed for that brand on the Brands sheet."),
             ("platform", "Platform", "instagram", "instagram or tiktok."),
             ("url", "Post URL", "https://www.instagram.com/reel/AbC123/", "The post's own link. One row per post."),
             ("handle", "Handle", "sara.skin", "The creator's handle on that platform, without @."),
             ("alt_handle", "Other handle", "sara_skin_tt", "Optional: the same creator's handle on the other platform (helps find them on the roster)."),
             ("name", "Creator name", "Sara Ahmed", "As the creator writes it."),
             ("creator_type", "Creator type", "influencer", "influencer or hcp (doctor / pharmacist). UGC creators are influencers."),
             ("city", "City", "Riyadh", "Optional."),
             ("followers", "Followers", "120000", "On that platform, a whole number."),
             ("posted_at", "Posted date", "2026-03-14", "YYYY-MM-DD, or an Excel date."),
             ("collab_type", "Collab type", "Own post, tagged", "Pick from the list."),
             ("posted_on", "Posted on", "Creator page", "Optional: where it went live."),
             ("content_type", "Content type", "Review", "Optional: review, tutorial, routine, unboxing…"),
             ("product_tags", "Product tags", "Vitamin C serum", "What the post shows. Compared with the brand's match words."),
             ("views", "Views", "85000", "Whole number. Leave empty if not shown."),
             ("likes", "Likes", "2100", "Leave empty if likes are hidden."),
             ("comments", "Comments", "64", ""),
             ("shares", "Shares", "", "Optional."),
             ("saves", "Saves", "", "Optional."),
             ("paid_boost", "Paid-boosted?", "No", "Yes when the views were bought (very high views, almost no engagement)."),
             ("likes_hidden", "Likes hidden?", "No", "Yes when the creator hides likes (an empty Likes cell counts as hidden too)."),
             ("save_rate", "Save rate", "", "Optional, TikTok: saves ÷ views, e.g. 0.012."),
             ("note", "Note", "", "Optional, internal: never shown to the client."))
CREATOR_COLS = (("handle", "Handle", "sara.skin"), ("name", "Name", "Sara Ahmed"), ("type", "Creator type", "influencer"),
                ("city", "City", "Riyadh"), ("followers", "Followers", "120000"),
                ("Instagram", "Instagram link", "https://www.instagram.com/sara.skin/"),
                ("TikTok", "TikTok link", "https://www.tiktok.com/@sara_skin_tt"), ("Snapchat", "Snapchat link", ""),
                ("YouTube", "YouTube link", ""), ("X", "X link", ""), ("Facebook", "Facebook link", ""))
SHEETS = ("Instructions", "Brands", "Posts", "Creators", "Lists")


def _letter(i):
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def template():
    """The empty template, with one example row on each sheet's Instructions and dropdowns on the data sheets."""
    lists = [("Platform", PLATFORMS), ("Creator type", TYPES), ("Competitor fit", FITS),
             ("Collab type", [k for k, _ in COLLABS]), ("Yes / No", YES_NO)]
    depth = max(len(v) for _, v in lists)
    list_rows = [[n for n, _ in lists]] + [[(v[i] if i < len(v) else "") for _, v in lists] for i in range(depth)]
    src = {n: "Lists!$%s$2:$%s$%d" % (_letter(i), _letter(i), len(v) + 1) for i, (n, v) in enumerate(lists)}

    intro = [["Competitor evidence template"],
             ["Fill the Brands sheet first, then one Posts row per competitor collab post. Upload the file at "
              "Admin > Competitor evidence. Uploading the same file again updates the pack, it never duplicates."],
             ["The portal works out relevance to the product, engagement, views per follower, views against the "
              "competitor's average, the rating and the best creators by itself. Do not add columns for them."],
             ["Columns with * are required. Keep the header rows as they are. The examples are on this sheet only; nothing here is imported."],
             [""], ["Brands sheet", "What it means", "Example"]]
    intro += [[h + (" *" if k in ("brand", "competitor", "fit") else ""),
               {"brand": "The client's brand.", "product": "One line on the product the proposal is for.",
                "match_tags": "Words that mean the same category. A post whose Product tags contain one is 'Same category'.",
                "competitor": "One row per competitor of that brand.",
                "fit": "direct, partial (partly the same product) or off-product."}[k], ex] for k, h, ex in BRAND_COLS]
    intro += [[""], ["Posts sheet", "What it means", "Example"]]
    intro += [[h + (" *" if k in REQUIRED else ""), why, ex] for k, h, ex, why in POST_COLS]
    intro += [[""], ["Creators sheet (optional)", "What it means", "Example"]]
    intro += [[h, "Every platform the creator is on; used when the pack's creators are added to the roster.", ex]
              for _, h, ex in CREATOR_COLS]

    brands = [[h + (" *" if k in ("brand", "competitor", "fit") else "") for k, h, _ in BRAND_COLS]]
    posts = [[h + (" *" if k in REQUIRED else "") for k, h, _, _ in POST_COLS]]
    creators = [[h for _, h, _ in CREATOR_COLS]]
    pc = {k: i for i, (k, _, _, _) in enumerate(POST_COLS)}
    col = lambda k: "%s2:%s5000" % (_letter(pc[k]), _letter(pc[k]))
    rules = [(2, "E2:E500", src["Competitor fit"]),
             (3, col("platform"), src["Platform"]), (3, col("creator_type"), src["Creator type"]),
             (3, col("collab_type"), src["Collab type"]), (3, col("paid_boost"), src["Yes / No"]),
             (3, col("likes_hidden"), src["Yes / No"]), (4, "C2:C5000", src["Creator type"])]
    return xlsx.write_book([
        ("Instructions", intro, {0: 34, 1: 90, 2: 44}, None),
        ("Brands", brands, {0: 18, 1: 48, 2: 40, 3: 18, 4: 16}, None),
        ("Posts", posts, {i: (40 if k == "url" else 22 if k in ("product_tags", "collab_type", "note") else 14)
                          for i, (k, _, _, _) in enumerate(POST_COLS)}, None),
        ("Creators", creators, {i: (36 if i >= 5 else 16) for i in range(len(CREATOR_COLS))}, None),
        ("Lists", list_rows, {i: 30 for i in range(len(lists))}, None),
    ], rules)


REQUIRED = ("brand", "competitor", "platform", "url", "handle")


def is_xlsx(raw):
    return isinstance(raw, (bytes, bytearray)) and raw[:2] == b"PK"


# ------------------------------------------------------------------ reading --

class _Errors:
    def __init__(self):
        self.items = []

    def add(self, sheet, row, col, msg):
        self.items.append("%s sheet, row %d, %s: %s" % (sheet, row, col, msg) if row else "%s sheet: %s" % (sheet, msg))

    def raise_if_any(self):
        if self.items:
            head = "Nothing was imported. Fix %s and upload again:" % ("this" if len(self.items) == 1 else "these %d" % len(self.items))
            more = len(self.items) - 25
            raise ValueError(" ".join([head] + ["(%d) %s" % (i + 1, t) for i, t in enumerate(self.items[:25])]
                                      + (["…and %d more." % more] if more > 0 else [])))


def _clean_head(h):
    return re.sub(r"\s*\*\s*$", "", str(h or "")).strip().lower()


def _table(book, name, cols, errs):
    """[(row number, {key: text})] for a sheet, by header label. Missing required headers are errors."""
    rows = book.get(name)
    if rows is None:
        errs.add(name, 0, "", "the sheet is missing. Start from a fresh template.")
        return []
    if not rows:
        return []
    head = [_clean_head(h) for h in rows[0]]
    at = {}
    for k, label in cols:
        if label.lower() in head:
            at[k] = head.index(label.lower())
    out = []
    for n, r in enumerate(rows[1:], start=2):
        vals = {k: (r[i].strip() if i < len(r) and r[i] is not None else "") for k, i in at.items()}
        if any(vals.values()):
            out.append((n, vals))
    return out, at


def _int(v, sheet, n, col, errs):
    if v == "":
        return None
    try:
        f = float(v.replace(",", ""))
    except ValueError:
        errs.add(sheet, n, col, "\"%s\" is not a number." % v)
        return None
    if f < 0:
        errs.add(sheet, n, col, "cannot be negative.")
        return None
    return int(round(f))


def _float(v, sheet, n, col, errs):
    if v == "":
        return None
    try:
        return float(v.replace(",", "").rstrip("%")) / (100.0 if v.endswith("%") else 1.0)
    except ValueError:
        errs.add(sheet, n, col, "\"%s\" is not a number." % v)
        return None


def _date(v, sheet, n, col, errs):
    if v == "":
        return ""
    if re.fullmatch(r"\d+(\.\d+)?", v) and 20000 < float(v) < 80000:          # an Excel date serial
        return (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(float(v)))).isoformat()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(v[:19], fmt).date().isoformat()
        except ValueError:
            pass
    errs.add(sheet, n, col, "\"%s\" is not a date. Use YYYY-MM-DD." % v)
    return ""


def _yes(v, sheet, n, col, errs):
    t = v.strip().lower()
    if t in ("", "no", "n", "false", "0", "لا"):
        return False
    if t in ("yes", "y", "true", "1", "x", "نعم"):
        return True
    errs.add(sheet, n, col, "\"%s\" should be Yes or No." % v)
    return False


def _handle(v):
    v = v.strip()
    m = re.search(r"(?:instagram\.com|tiktok\.com)/@?([A-Za-z0-9_.]+)", v)
    return (m.group(1) if m else v).lstrip("@").strip().lower()


def relevance(tags, words):
    """match | unspecified | other: the post's product against the brand's match words (as the scripts did)."""
    t = (tags or "").strip().lower()
    if t and any(w and w.lower() in t for w in words):
        return "match"
    return "unspecified" if not t or any(u.lower() in t for u in UNSPECIFIED) else "other"


def rating(x):
    """The study's four-step read of one post, from its views against the competitor's average."""
    if x is None:
        return None
    return "excellent" if x >= 2 else "good" if x >= 1 else "average" if x >= 0.5 else "weak"


def derive(posts):
    """Fill what the portal computes for itself. Mutates and returns the post dicts."""
    groups = {}
    for p in posts:
        v, f, lk = p.get("views"), p.get("followers"), p.get("likes")
        if p.get("er_views") is None and v and lk is not None:
            p["er_views"] = round((lk + (p.get("comments") or 0)) / float(v), 6)
        if p.get("views_per_follower") is None and v and f:
            p["views_per_follower"] = round(v / float(f), 6)
        if p.get("save_rate") is None and v and p.get("saves") is not None:
            p["save_rate"] = round(p["saves"] / float(v), 6)
        groups.setdefault((p["brand"], p["competitor"], p["platform"]), []).append(p)
    for ps in groups.values():
        organic = [p["views"] for p in ps if p.get("views") and not p.get("likely_paid_boost")]
        avg = statistics.mean(organic) if organic else None
        for p in ps:
            if p.get("x_brand_avg") is None and avg and p.get("views"):
                p["x_brand_avg"] = round(p["views"] / avg, 4)
            if not p.get("rating"):
                p["rating"] = None if p.get("likely_paid_boost") else rating(p.get("x_brand_avg"))
    return posts


def parse(raw):
    """A filled template -> (brands meta, posts, meta), the same shape as evidence.parse_pack. Raises ValueError
    naming every bad cell (sheet, row, column); nothing is imported while any remain."""
    try:
        book = xlsx.read_all(bytes(raw))
    except xlsx.BadWorkbook as ex:
        raise ValueError(str(ex))
    errs = _Errors()
    if "Posts" not in book or "Brands" not in book:
        raise ValueError("That workbook is not the competitor evidence template (it needs Brands and Posts sheets). "
                         "Download the template from this page and fill that.")

    got = _table(book, "Brands", [(k, h) for k, h, _ in BRAND_COLS], errs)
    brows, bat = got if got else ([], {})
    for k in ("brand", "competitor", "fit"):
        if k not in bat:
            errs.add("Brands", 1, "header", "the \"%s\" column is missing." % dict((a, b) for a, b, _ in BRAND_COLS)[k])
    brands, order = {}, []
    last = None
    for n, r in brows:
        name = r.get("brand") or last
        if not name:
            errs.add("Brands", n, "Brand", "is empty.")
            continue
        last = name
        b = brands.get(name)
        if b is None:
            b = brands[name] = {"brand": name, "product": "", "match_tags": [], "fit": {}}
            order.append(name)
        if r.get("product"):
            b["product"] = r["product"]
        if r.get("match_tags"):
            b["match_tags"] += [w.strip() for w in re.split(r"[,،;\n]", r["match_tags"]) if w.strip()]
        comp, fit = r.get("competitor", ""), r.get("fit", "").lower()
        if not comp:
            if not (r.get("product") or r.get("match_tags")):
                errs.add("Brands", n, "Competitor", "is empty.")
            continue
        if fit not in FITS:
            errs.add("Brands", n, "Competitor fit", "\"%s\" should be direct, partial or off-product." % r.get("fit", ""))
        if comp in b["fit"]:
            errs.add("Brands", n, "Competitor", "%s is listed twice for %s." % (comp, name))
        b["fit"][comp] = fit if fit in FITS else "unknown"

    got = _table(book, "Posts", [(k, h) for k, h, _, _ in POST_COLS], errs)
    prows, pat = got if got else ([], {})
    label = {k: h for k, h, _, _ in POST_COLS}
    for k in REQUIRED:
        if k not in pat:
            errs.add("Posts", 1, "header", "the \"%s\" column is missing." % label[k])
    posts, seen = [], {}
    for n, r in prows:
        def need(k):
            if not r.get(k):
                errs.add("Posts", n, label[k], "is empty.")
            return r.get(k, "")
        brand, comp, plat, url = need("brand"), need("competitor"), need("platform").lower(), need("url")
        handle = _handle(need("handle"))
        if brand and brand not in brands:
            errs.add("Posts", n, "Brand", "\"%s\" is not on the Brands sheet." % brand)
        elif brand and comp and comp not in brands[brand]["fit"]:
            errs.add("Posts", n, "Competitor", "\"%s\" is not listed for %s on the Brands sheet." % (comp, brand))
        if plat and plat not in PLATFORMS:
            errs.add("Posts", n, "Platform", "\"%s\" should be instagram or tiktok." % r.get("platform"))
        if url and not re.match(r"https?://", url):
            errs.add("Posts", n, "Post URL", "must start with https://.")
        if url and brand:
            if (brand, url) in seen:
                errs.add("Posts", n, "Post URL", "the same post is already on row %d for %s." % (seen[(brand, url)], brand))
            seen[(brand, url)] = n
        ctype = (r.get("creator_type") or "influencer").lower()
        if ctype in ("doctor", "pharmacist", "doctor / pharmacist", "hcp"):
            ctype = "hcp"
        elif ctype in ("influencer", "ugc", "ugc creator"):
            ctype = "influencer"
        else:
            errs.add("Posts", n, "Creator type", "\"%s\" should be influencer or hcp." % r.get("creator_type"))
        collab = r.get("collab_type", "")
        code = COLLAB_CODE.get(collab.lower()) if collab else None
        if collab and not code:
            errs.add("Posts", n, "Collab type", "\"%s\" is not one of the list's options." % collab)
        likes = _int(r.get("likes", ""), "Posts", n, "Likes", errs)
        hidden = _yes(r.get("likes_hidden", ""), "Posts", n, "Likes hidden?", errs) or likes is None
        p = {"brand": brand, "competitor": comp, "platform": plat, "url": url, "handle": handle,
             "alt_handle": _handle(r["alt_handle"]) if r.get("alt_handle") else None,
             "name": r.get("name") or None, "creator_type": ctype, "city": r.get("city") or None,
             "followers": _int(r.get("followers", ""), "Posts", n, "Followers", errs),
             "posted_at": _date(r.get("posted_at", ""), "Posts", n, "Posted date", errs),
             "collab_type": code, "posted_on": r.get("posted_on") or None, "content_type": r.get("content_type") or None,
             "product_tags": r.get("product_tags") or None,
             "views": _int(r.get("views", ""), "Posts", n, "Views", errs), "likes": None if hidden else likes,
             "comments": _int(r.get("comments", ""), "Posts", n, "Comments", errs),
             "shares": _int(r.get("shares", ""), "Posts", n, "Shares", errs),
             "saves": _int(r.get("saves", ""), "Posts", n, "Saves", errs),
             "likely_paid_boost": 1 if _yes(r.get("paid_boost", ""), "Posts", n, "Paid-boosted?", errs) else 0,
             "likes_hidden": 1 if hidden else 0,
             "save_rate": _float(r.get("save_rate", ""), "Posts", n, "Save rate", errs),
             "note": r.get("note") or None,
             "er_views": None, "views_per_follower": None, "x_brand_avg": None, "rating": None}
        b = brands.get(brand)
        p["relevance"] = "match" if code == "tiktok_summary" else relevance(p["product_tags"], b["match_tags"] if b else [])
        posts.append(p)
    if not prows and not errs.items:
        errs.add("Posts", 0, "", "has no rows. Add one row per competitor collab post.")

    creators = {}
    if "Creators" in book:
        got = _table(book, "Creators", [(k, h) for k, h, _ in CREATOR_COLS], errs)
        for n, r in (got[0] if got else []):
            h = _handle(r.get("handle", ""))
            if not h:
                errs.add("Creators", n, "Handle", "is empty.")
                continue
            links = {}
            for k, lab, _ in CREATOR_COLS[5:]:
                v = r.get(k, "")
                if v and not re.match(r"https?://", v):
                    errs.add("Creators", n, lab, "must be a full link starting with https://.")
                elif v:
                    links[k] = v
            t = (r.get("type") or "").lower()
            creators[h] = {"name": r.get("name") or None, "followers": _int(r.get("followers", ""), "Creators", n, "Followers", errs),
                           "city": r.get("city") or None, "type": "hcp" if t == "hcp" else ("influencer" if t else None), "links": links}
    errs.raise_if_any()

    derive(posts)
    meta = {"objective": "awareness (reach & views)", "platforms": sorted({p["platform"] for p in posts}),
            "source": "Excel template", "creators": creators}
    return [brands[b] for b in order], posts, meta
