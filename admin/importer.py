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

import xlsx

COLUMNS = ["code", "name", "platform", "handle", "followers",
           "city", "tier", "interest", "note", "active", "photo"]

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

TEMPLATE_ROWS = [
    ["", "Noha Magdy", "Instagram", "noha.mgdi", "697000", "Jeddah", "Macro",
     "Skincare", "example row — delete before importing", "yes",
     "insert the picture on this row (.xlsx only)"],
    ["", "Omnya Elmasry", "TikTok", "omnyaelmasry.0", "618900", "", "Macro",
     "", "leave code blank and the portal assigns one", "yes", ""],
]


def template_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLUMNS)
    w.writerows(TEMPLATE_ROWS)
    # BOM so Excel opens it as UTF-8 rather than mangling Arabic city names
    return "﻿" + buf.getvalue()


def template_xlsx():
    """The same template as an .xlsx, which is the only format that can carry
    pictures. Written with the stdlib, so there is nothing to install."""
    rows = [COLUMNS] + [list(r) for r in TEMPLATE_ROWS]
    # Column K wide enough to drop a picture into, and the example rows tall
    # enough that one sits on its own row rather than straddling two.
    return xlsx.write(rows, sheet_name="Creators",
                      widths={10: 30}, row_heights={2: 60, 3: 60})


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

        plat_raw = cell("platform").lower()
        platform = PLATFORMS.get(plat_raw)
        if not platform:
            errors.append("Row " + str(n) + " (" + person + "): platform '"
                          + (cell("platform") or "blank") + "' is not Instagram or TikTok.")
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

        rows.append({
            "_row": n,
            "code": cell("code").upper() or None,
            "name": person,
            "handle": cell("handle").lstrip("@") or None,
            "platform": platform,
            "followers": followers,
            "city": cell("city") or None,
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
