"""Reading and writing .xlsx with the standard library only.

openpyxl did this and did it well, but it is a pip install, and it was the one
dependency in a service whose whole deployment story is "copy the folder and
run python3". On a locked-down host that single package is the difference
between the spreadsheet import working and not, and the failure lands on
whoever is trying to upload a roster rather than on whoever set up the server.

An .xlsx is a zip of XML. `zipfile` and `xml.etree` are both stdlib, so this
needs nothing installed anywhere.

What it handles, because it is what a roster sheet actually contains:

  * shared strings, inline strings and plain numbers
  * gaps — B3 with no A3 keeps its column, rather than shifting left
  * pictures, matched to the row their top-left anchor sits in
  * dates, as the text Excel already stored for display where it exists

What it does not: formulas (the cached value is used, which is what
data_only=True gave us anyway), styles, charts, multiple sheets beyond the
first. None of those belong in a creator roster.
"""

import io
import re
import xml.etree.ElementTree as ET
import zipfile

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
DOC = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
XDR = "{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}"
DRAW = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


class BadWorkbook(Exception):
    """Not a readable .xlsx. Raised with something a person can act on."""


# ---------------------------------------------------------------- reading --

def _col(ref):
    """Column index from a cell reference: A1 -> 0, AB7 -> 27."""
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1 if n else 0


def _row_no(ref, fallback):
    m = re.search(r"(\d+)$", ref or "")
    return int(m.group(1)) if m else fallback


def _rel_map(zf, part):
    """{rId: target} for a part's .rels sidecar, targets made zip-relative."""
    base = part.rsplit("/", 1)[0]
    rels = base + "/_rels/" + part.rsplit("/", 1)[-1] + ".rels"
    if rels not in zf.namelist():
        return {}
    out = {}
    for r in ET.fromstring(zf.read(rels)):
        target = r.get("Target", "")
        if target.startswith("/"):
            target = target[1:]
        else:
            # ../media/image1.png relative to xl/drawings -> xl/media/image1.png
            parts = base.split("/")
            for bit in target.split("/"):
                if bit == "..":
                    parts.pop()
                elif bit not in ("", "."):
                    parts.append(bit)
            target = "/".join(parts)
        out[r.get("Id")] = target
    return out


def _shared_strings(zf):
    name = "xl/sharedStrings.xml"
    if name not in zf.namelist():
        return []
    out = []
    for si in ET.fromstring(zf.read(name)):
        # A run-formatted string is several <t> under <r>; join them.
        out.append("".join(t.text or "" for t in si.iter(MAIN + "t")))
    return out


def _first_sheet(zf):
    book = ET.fromstring(zf.read("xl/workbook.xml"))
    sheets = book.find(MAIN + "sheets")
    if sheets is None or not len(sheets):
        raise BadWorkbook("That file has no sheets in it.")
    rid = sheets[0].get(DOC + "id")
    target = _rel_map(zf, "xl/workbook.xml").get(rid)
    if not target or target not in zf.namelist():
        # Some writers omit the relationship; the conventional path still works
        for guess in ("xl/worksheets/sheet1.xml", "xl/worksheets/sheet.xml"):
            if guess in zf.namelist():
                return guess
        raise BadWorkbook("Could not find the first sheet inside that file.")
    return target


def _images(zf, sheet_part):
    """{sheet row number: image bytes} from the drawings anchored on a sheet.

    The row is the one the picture's top-left corner sits in — the only thing
    an anchor reliably gives, and what the eye reads as "this row's photo".
    The first picture on a row wins; a second is ignored rather than silently
    replacing it.
    """
    out = {}
    for rid, part in _rel_map(zf, sheet_part).items():
        if "drawing" not in part or part not in zf.namelist():
            continue
        media = _rel_map(zf, part)
        for anchor in ET.fromstring(zf.read(part)):
            frm = anchor.find(XDR + "from")
            if frm is None:
                continue          # absolute placement: no row to bind it to
            row_el = frm.find(XDR + "row")
            if row_el is None or not (row_el.text or "").strip().isdigit():
                continue
            row = int(row_el.text.strip()) + 1     # xlsx counts rows from zero
            if row in out:
                continue
            blip = anchor.find(".//" + DRAW + "blip")
            if blip is None:
                continue
            src = media.get(blip.get(DOC + "embed"))
            if src and src in zf.namelist():
                data = zf.read(src)
                if data:
                    out[row] = data
    return out


def read(data):
    """Return ([(sheet row, [cell text, ...])], {sheet row: image bytes})."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise BadWorkbook(
            "That file is not a readable .xlsx. If it is an older .xls, open it "
            "in Excel and use File → Save As → .xlsx or .csv.")
    with zf:
        if "xl/workbook.xml" not in zf.namelist():
            raise BadWorkbook(
                "That .xlsx has no workbook inside it — it may be corrupt. "
                "Re-save it from Excel.")
        strings = _shared_strings(zf)
        sheet_part = _first_sheet(zf)

        table = []
        for i, row in enumerate(
                ET.fromstring(zf.read(sheet_part)).iter(MAIN + "row"), start=1):
            n = _row_no(row.get("r"), i)
            cells = []
            for c in row:
                if not c.tag.endswith("}c"):
                    continue
                # Keep gaps: B3 without A3 must stay in column B.
                at = _col(c.get("r") or "")
                while len(cells) < at:
                    cells.append("")
                kind = c.get("t")
                if kind == "inlineStr":
                    text = "".join(t.text or "" for t in c.iter(MAIN + "t"))
                else:
                    v = c.find(MAIN + "v")
                    text = (v.text or "") if v is not None else ""
                    if kind == "s" and text.strip().isdigit():
                        idx = int(text)
                        text = strings[idx] if idx < len(strings) else ""
                cells.append(text.strip())
            table.append((n, cells))
        return table, _images(zf, sheet_part)


# ---------------------------------------------------------------- writing --

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    "</Types>")

_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>")

_BOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    "</Relationships>")


def _esc(v):
    return (str("" if v is None else v)
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _ref(col, row):
    letters = ""
    col += 1
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters + str(row)


def write_book(sheets, validations=None):
    """A workbook of several sheets, with optional dropdown lists.

    `sheets` is [(name, rows, widths, row_heights)]. `validations` is
    [(sheet_index, "F2:F999", "Options!$A$2:$A$9")] — Excel's own dropdown,
    which is the closest a spreadsheet gets to the multi-select in the
    dashboard. They are offered rather than enforced: showErrorMessage is off,
    so a cell can still hold two categories separated by a comma, which a
    single-select dropdown could never express.
    """
    parts = []
    for i, (name, rows, widths, heights) in enumerate(sheets, start=1):
        rules = [v for v in (validations or []) if v[0] == i]
        parts.append(_sheet_xml(rows, widths, heights, rules))

    types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
             + "".join(
                 '<Override PartName="/xl/worksheets/sheet%d.xml" '
                 'ContentType="application/vnd.openxmlformats-officedocument.'
                 'spreadsheetml.worksheet+xml"/>' % i
                 for i in range(1, len(sheets) + 1))
             + "</Types>")

    book_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 + "".join(
                     '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/'
                     'officeDocument/2006/relationships/worksheet" '
                     'Target="worksheets/sheet%d.xml"/>' % (i, i)
                     for i in range(1, len(sheets) + 1))
                 + "</Relationships>")

    book = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>" + "".join(
                '<sheet name="' + _esc(name) + '" sheetId="%d" r:id="rId%d"/>' % (i, i)
                for i, (name, _, _, _) in enumerate(sheets, start=1))
            + "</sheets></workbook>")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", types)
        zf.writestr("_rels/.rels", _ROOT_RELS)
        zf.writestr("xl/workbook.xml", book)
        zf.writestr("xl/_rels/workbook.xml.rels", book_rels)
        for i, xml in enumerate(parts, start=1):
            zf.writestr("xl/worksheets/sheet%d.xml" % i, xml)
    return buf.getvalue()


def _sheet_xml(rows, widths=None, row_heights=None, rules=()):
    body = []
    for r, row in enumerate(rows, start=1):
        height = (row_heights or {}).get(r)
        attrs = ' ht="' + str(height) + '" customHeight="1"' if height else ""
        body.append('<row r="' + str(r) + '"' + attrs + ">")
        for c, value in enumerate(row):
            if value is None or value == "":
                continue
            body.append('<c r="' + _ref(c, r) + '" t="inlineStr"><is><t xml:space="preserve">'
                        + _esc(value) + "</t></is></c>")
        body.append("</row>")

    cols = ""
    if widths:
        cols = "<cols>" + "".join(
            '<col min="' + str(i + 1) + '" max="' + str(i + 1) + '" width="'
            + str(w) + '" customWidth="1"/>' for i, w in sorted(widths.items())
        ) + "</cols>"

    # Schema order matters: cols, then sheetData, then dataValidations. Out of
    # order and Excel calls the file corrupt rather than ignoring the part.
    valid = ""
    if rules:
        valid = ('<dataValidations count="%d">' % len(rules)) + "".join(
            '<dataValidation type="list" allowBlank="1" showInputMessage="1" '
            'showErrorMessage="0" sqref="' + _esc(where) + '">'
            "<formula1>" + _esc(source) + "</formula1></dataValidation>"
            for _, where, source in rules) + "</dataValidations>"

    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            + cols + "<sheetData>" + "".join(body) + "</sheetData>" + valid
            + "</worksheet>")


def write(rows, sheet_name="Sheet1", widths=None, row_heights=None):
    """A workbook of `rows` (lists of values) as bytes.

    Everything is written as an inline string. It costs a few bytes against a
    shared-string table and removes a whole class of index bug from a file
    whose job is to be filled in by hand and read back.
    """
    body = []
    for r, row in enumerate(rows, start=1):
        height = (row_heights or {}).get(r)
        attrs = ' ht="' + str(height) + '" customHeight="1"' if height else ""
        body.append('<row r="' + str(r) + '"' + attrs + ">")
        for c, value in enumerate(row):
            if value is None or value == "":
                continue
            body.append('<c r="' + _ref(c, r) + '" t="inlineStr"><is><t xml:space="preserve">'
                        + _esc(value) + "</t></is></c>")
        body.append("</row>")

    cols = ""
    if widths:
        cols = "<cols>" + "".join(
            '<col min="' + str(i + 1) + '" max="' + str(i + 1) + '" width="'
            + str(w) + '" customWidth="1"/>' for i, w in sorted(widths.items())
        ) + "</cols>"

    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
             'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
             + cols + "<sheetData>" + "".join(body) + "</sheetData></worksheet>")

    book = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="' + _esc(sheet_name)
            + '" sheetId="1" r:id="rId1"/></sheets></workbook>')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("_rels/.rels", _ROOT_RELS)
        zf.writestr("xl/workbook.xml", book)
        zf.writestr("xl/_rels/workbook.xml.rels", _BOOK_RELS)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()
