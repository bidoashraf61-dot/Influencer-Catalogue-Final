"""Bulk creator import from a spreadsheet.

CSV is the native format — `csv` is stdlib, so it works on any server. `.xlsx`
is read only when openpyxl happens to be installed; if it is not, the uploader
is told to save as CSV rather than being left with a silent failure.

Nothing is written until every row has been checked. A file with one bad row
imports nothing and reports the line, rather than leaving the roster half
updated.
"""

import csv
import io

COLUMNS = ["code", "name", "platform", "handle", "followers",
           "city", "tier", "interest", "note", "active"]

TIERS = {"nano": "Nano", "micro": "Micro", "mid-tier": "Mid-Tier",
         "mid": "Mid-Tier", "macro": "Macro"}
PLATFORMS = {"instagram": "Instagram", "ig": "Instagram",
             "tiktok": "TikTok", "tt": "TikTok"}

TEMPLATE_ROWS = [
    ["", "Noha Magdy", "Instagram", "noha.mgdi", "697000", "Jeddah", "Macro",
     "Skincare", "example row — delete before importing", "yes"],
    ["", "Omnya Elmasry", "TikTok", "omnyaelmasry.0", "618900", "", "Macro",
     "", "leave code blank and the portal assigns one", "yes"],
]


def template_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLUMNS)
    w.writerows(TEMPLATE_ROWS)
    # BOM so Excel opens it as UTF-8 rather than mangling Arabic city names
    return "﻿" + buf.getvalue()


def _rows_from_xlsx(data):
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError(
            "This server cannot read .xlsx (openpyxl is not installed). "
            "Open the file in Excel and use File → Save As → CSV.")
    import tempfile
    import os
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    try:
        os.write(fd, data)
        os.close(fd)
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        ws = wb[wb.sheetnames[0]]
        return [["" if c is None else str(c).strip() for c in row]
                for row in ws.iter_rows(values_only=True)]
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _rows_from_csv(data):
    text = data.decode("utf-8-sig", "replace")
    # Sniff the delimiter: exports from Arabic/European locales use ';'
    sample = text[:2048]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    return [[(c or "").strip() for c in row]
            for row in csv.reader(io.StringIO(text), delimiter=delim)]


def parse(data: bytes, filename: str):
    """Return (rows, errors). `rows` are dicts ready for db.upsert_creator,
    minus the code, which the caller assigns."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        table = _rows_from_xlsx(data)
    else:
        table = _rows_from_csv(data)

    table = [r for r in table if any((c or "").strip() for c in r)]
    if not table:
        return [], ["The file is empty."]

    header = [h.strip().lower().replace(" ", "_") for h in table[0]]
    if "name" not in header:
        return [], ["No 'name' column found. Download the template and use its headings."]

    index = {col: header.index(col) for col in COLUMNS if col in header}
    rows, errors = [], []

    for n, raw in enumerate(table[1:], start=2):
        def cell(col):
            i = index.get(col)
            return (raw[i].strip() if i is not None and i < len(raw) else "")

        person = cell("name")
        if not person:
            continue  # a blank name is an empty row, not an error

        tier_raw = cell("tier").lower()
        tier = TIERS.get(tier_raw)
        if not tier:
            errors.append("Row " + str(n) + " (" + person + "): tier '"
                          + (cell("tier") or "blank") + "' is not Nano, Micro, Mid-Tier or Macro.")
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

    seen = {}
    for r in rows:
        if r["code"]:
            if r["code"] in seen:
                errors.append("Code " + r["code"] + " appears twice in the file.")
            seen[r["code"]] = True

    return rows, errors
