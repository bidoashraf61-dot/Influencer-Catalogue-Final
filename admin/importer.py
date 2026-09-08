"""Bulk creator import from a spreadsheet.

Both formats are read with the standard library — CSV through `csv`, and
.xlsx through `admin/xlsx.py`, which unzips the workbook itself. Nothing to
install on the server, on any host.

Nothing is written until every row has been checked. A file with one bad row
imports nothing and reports the line, rather than leaving the roster half
updated.

PICTURES IN AN .XLSX. A photo is never *in* a cell — a cell holds text. Excel
stores pictures as floating drawings in xl/media/, anchored to a position on
the sheet, and the cell they cover stays empty. They can still be read, and
the anchor's top-left corner names a row, so a picture sitting on a creator's
row is attached to that creator.

The consequence worth knowing, because it is visible rather than hidden: a
picture dragged so its top-left corner falls into the row below attaches to
whoever is on that row. CSV cannot carry an image in any form.
"""

import csv
import io

import db
import xlsx

# One column per platform, each holding a full profile link. A column per
# platform rather than one "profiles" cell because a spreadsheet is edited by
# eye: it is obvious what goes where, and sorting or filtering on "who is on
# TikTok" works. platform/handle stay so an older sheet still imports.
PROFILE_COLUMNS = ["instagram", "tiktok", "snapchat", "youtube", "x", "facebook"]
PROFILE_LABELS = {"instagram": "Instagram", "tiktok": "TikTok",
                  "snapchat": "Snapchat", "youtube": "YouTube",
                  "x": "X", "facebook": "Facebook"}

# Each platform brings a link column and a followers column, side by side, so
# a row reads left to right as "this profile, that many followers".
PROFILE_PAIRS = [c for col in PROFILE_COLUMNS for c in (col, col + "_followers")]

COLUMNS = (["code", "name", "followers", "city", "nationality", "tier"]
           + PROFILE_PAIRS
           + ["interest", "note", "active", "photo", "platform", "handle"])

# Aliases people actually type. The real list comes from the database, so a
# tier added in the dashboard is importable the moment it exists.
TIER_ALIASES = {"mid": "Mid-Tier", "mid tier": "Mid-Tier"}


def tier_lookup():
    import db
    out = {}
    for name in db.tier_names():
        out[name.lower()] = name
    for alias, real in TIER_ALIASES.items():
        if real.lower() in out:
            out[alias] = out[real.lower()]
    return out
PLATFORMS = {"instagram": "Instagram", "ig": "Instagram",
             "tiktok": "TikTok", "tt": "TikTok"}

def _template_row(**kw):
    return [kw.get(col, "") for col in COLUMNS]


TEMPLATE_ROWS = [
    _template_row(
        name="Noha Magdy", followers="697000", city="Jeddah",
        nationality="Egyptian", tier="Macro",
        instagram="https://www.instagram.com/noha.mgdi/",
        instagram_followers="697000", interest="Skincare",
        note="example row — delete before importing", active="yes",
        photo="insert the picture on this row (.xlsx only)"),
    _template_row(
        name="Omnya Elmasry", city="Riyadh, Jeddah", nationality="Saudi",
        tier="Macro",
        instagram="https://www.instagram.com/omnyaelmasry.0/",
        instagram_followers="618900",
        tiktok="https://www.tiktok.com/@omnyaelmasry.0",
        tiktok_followers="240000",
        note="several platforms — leave followers blank above and it is the sum",
        active="yes"),
    _template_row(
        name="Two accounts, one platform", city="Riyadh", nationality="Saudi",
        tier="Micro",
        instagram="https://www.instagram.com/example.en/, "
                  "https://www.instagram.com/example.ar/",
        instagram_followers="31000, 18500",
        note="separate several links in one cell with a comma; followers line "
             "up in the same order",
        active="yes"),
]


MULTI_SPLIT = ",;\u060c\u061b\n\r"


def split_multi(text):
    """One cell holding several values. Commas and semicolons are what people
    reach for, a line break is what Alt+Enter produces in Excel, and the Arabic
    pair is here for the same reason the city splitter has them."""
    out, buf = [], ""
    for ch in str(text or "") + ",":
        if ch in MULTI_SPLIT:
            value = buf.strip()
            buf = ""
            if value:
                out.append(value)
        else:
            buf += ch
    return out


def template_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLUMNS)
    w.writerows(TEMPLATE_ROWS)
    # BOM so Excel opens it as UTF-8 rather than mangling Arabic city names
    return "﻿" + buf.getvalue()


def template_xlsx():
    """The template as an .xlsx — the only format that can carry pictures, and
    the only one that can carry dropdowns.

    A spreadsheet cell cannot be a set of tick boxes the way the dashboard is.
    The nearest honest equivalent is Excel's own dropdown, backed by a second
    sheet listing what the roster actually uses — so the options are visible
    and a category is picked rather than retyped into a fourth spelling.

    They are offered, not enforced. Interests and cities take several values
    separated by commas, which no single-select dropdown can express, so a
    typed cell is still accepted.
    """
    tiers = db.tier_names() or ["Nano", "Micro", "Mid-Tier", "Macro"]
    interests = db.known_interests()
    cities = db.known_cities()
    nationalities = db.known_nationalities() or ["Saudi"]

    rows = [COLUMNS] + [list(r) for r in TEMPLATE_ROWS]
    widths = dict([(COLUMNS.index("photo"), 30), (COLUMNS.index("interest"), 30),
                   (COLUMNS.index("name"), 22), (COLUMNS.index("city"), 20),
                   (COLUMNS.index("nationality"), 16),
                   (COLUMNS.index("note"), 46)]
                  + [(COLUMNS.index(c), 34) for c in PROFILE_COLUMNS])

    # The reference sheet. The columns are independent lists, so the longest
    # decides the height and the shorter ones are padded out.
    lists = [tiers, interests, cities, nationalities,
             [PROFILE_LABELS[c] for c in PROFILE_COLUMNS], ["yes", "no"]]
    ref = [["tier", "interest", "city", "nationality", "platform", "active"]]
    for i in range(max(len(x) for x in lists)):
        ref.append([(x[i] if i < len(x) else "") for x in lists])

    def letter(index):
        out, index = "", index + 1
        while index:
            index, rem = divmod(index - 1, 26)
            out = chr(65 + rem) + out
        return out

    last = len(rows) + 400          # room to paste a whole roster underneath

    def rule(column, ref_col, count):
        col = letter(COLUMNS.index(column))
        return (1, "%s2:%s%d" % (col, col, last),
                "Options!$%s$2:$%s$%d" % (ref_col, ref_col, count + 1))

    validations = [
        rule("tier", "A", len(tiers)),
        rule("interest", "B", len(interests)),
        rule("city", "C", len(cities)),
        rule("nationality", "D", len(nationalities)),
        rule("active", "F", 2),
    ]

    return xlsx.write_book(
        [("Creators", rows, widths, {2: 60, 3: 60, 4: 60}),
         ("Options", ref, {0: 14, 1: 20, 2: 18, 3: 18, 4: 16, 5: 10}, {})],
        validations)



def _rows_from_xlsx(data):
    """Returns ([(sheet row, cells)], {sheet row: image bytes})."""
    try:
        return xlsx.read(data)
    except xlsx.BadWorkbook as ex:
        raise RuntimeError(str(ex))


def _rows_from_csv(data):
    """Returns ([(line number, cells)], {}) — a CSV holds text and nothing else,
    so there are never any images."""
    text = data.decode("utf-8-sig", "replace")
    # Sniff the delimiter: exports from Arabic/European locales use ';'
    sample = text[:2048]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    return [(i, [(c or "").strip() for c in row])
            for i, row in enumerate(csv.reader(io.StringIO(text), delimiter=delim),
                                    start=1)], {}


def parse(data: bytes, filename: str):
    """Return (rows, errors, photos).

    `rows` are dicts ready for db.upsert_creator, minus the code, which the
    caller assigns; each carries `_row`, its real line in the sheet. `photos`
    maps that same row number to image bytes for an .xlsx with pictures on it,
    and is always empty for a CSV.

    Row numbers are the sheet's own, not a position in the filtered list — an
    error naming "row 14" has to point at row 14 of the file the person is
    looking at, and blank lines in the middle used to shift it.
    """
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        table, photos = _rows_from_xlsx(data)
    else:
        table, photos = _rows_from_csv(data)

    table = [(i, r) for i, r in table if any((c or "").strip() for c in r)]
    if not table:
        return [], ["The file is empty."], {}

    header = [h.strip().lower().replace(" ", "_") for h in table[0][1]]
    if "name" not in header:
        return [], ["No 'name' column found. Download the template and use its headings."], {}

    index = {col: header.index(col) for col in COLUMNS if col in header}
    tiers = tier_lookup()
    rows, errors = [], []

    for n, raw in table[1:]:
        def cell(col):
            i = index.get(col)
            return (raw[i].strip() if i is not None and i < len(raw) else "")

        person = cell("name")
        if not person:
            continue  # a blank name is an empty row, not an error

        tier_raw = cell("tier").lower()
        tier = tiers.get(tier_raw)
        if not tier:
            errors.append("Row " + str(n) + " (" + person + "): tier '"
                          + (cell("tier") or "blank") + "' is not one of "
                          + ", ".join(sorted(set(tiers.values()))) + ".")
            continue

        # The platform column is a leftover from when a creator had exactly
        # one. It is only consulted when the row has no profile links at all,
        # so a sheet written either way imports.
        plat_raw = cell("platform").lower()
        platform = PLATFORMS.get(plat_raw, "")
        has_links = any(cell(col) for col in PROFILE_COLUMNS)
        if not platform and not has_links:
            errors.append(
                "Row " + str(n) + " (" + person + "): no profile link. Put the "
                "full link in at least one of: "
                + ", ".join(PROFILE_LABELS[c] for c in PROFILE_COLUMNS) + ".")
            continue

        followers_raw = cell("followers").replace(",", "").replace(" ", "")
        followers = None
        if followers_raw:
            if not followers_raw.isdigit():
                errors.append("Row " + str(n) + " (" + person + "): followers '"
                              + cell("followers") + "' is not a number.")
                continue
            followers = int(followers_raw)

        active_raw = cell("active").lower()
        active = 0 if active_raw in ("no", "false", "0", "hidden") else 1

        # A link per platform column. A cell holding a bare username instead of
        # a link is rescued rather than rejected — it is an easy thing to type,
        # and refusing the whole file over it would be obnoxious.
        profiles = []
        for col in PROFILE_COLUMNS:
            # NOT `raw`: that is the row this closure reads through cell(), and
            # shadowing it made every column after the first read characters
            # out of a string instead of cells out of the row.
            cellval = cell(col)
            if not cellval:
                continue
            label = PROFILE_LABELS[col]
            # A creator can run two accounts on one platform. Rather than a
            # second column per platform — twelve more headings — one cell
            # takes several, separated by a comma, semicolon or a line break,
            # and the followers cell is read the same way, position for
            # position.
            links = split_multi(cellval)
            counts = split_multi(cell(col + "_followers"))
            for i, link in enumerate(links):
                if "/" not in link and "." not in link:
                    link = db.profile_url(label, link) or link
                count = (counts[i] if i < len(counts) else "").replace(",", "")
                profiles.append({"platform": label, "url": link,
                                 "followers": int(count) if count.isdigit() else None})

        # An older sheet, with one platform and a handle and no link columns.
        if not profiles and cell("handle"):
            legacy = PLATFORMS.get(cell("platform").lower())
            url = db.profile_url(legacy, cell("handle")) if legacy else ""
            if url:
                profiles.append({"platform": legacy, "url": url})

        stored = db.join_profiles(profiles)
        listed = db.split_profiles(stored)
        if followers is None:
            followers = db.total_followers(listed)

        rows.append({
            "_row": n,
            "code": cell("code").upper() or None,
            "name": person,
            # Derived from the links, so they cannot disagree with them.
            "handle": (db.handle_from_url(listed[0]["url"]) if listed
                       else cell("handle").lstrip("@")) or None,
            "platform": (db.join_cities([x["platform"] for x in listed])
                         or platform),
            "profiles": stored,
            "followers": followers,
            "city": cell("city") or None,
            "nationality": cell("nationality") or None,
            "tier": tier,
            "interest": cell("interest") or None,
            "note": cell("note") or None,
            "active": active,
        })
        # The photo column, if someone typed in it, is a label for where to put
        # the picture — not data. The image itself is matched by row.

    seen = {}
    for r in rows:
        if r["code"]:
            if r["code"] in seen:
                errors.append("Code " + r["code"] + " appears twice in the file.")
            seen[r["code"]] = True

    return rows, errors, photos
