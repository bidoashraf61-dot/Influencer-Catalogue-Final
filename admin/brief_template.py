"""The HelloVoice brief template (item 277, Bido 2026-10-29: "Template only").

A Word file a client downloads, fills and uploads. Every question is a Word content control:
tick boxes for questions that take several answers, drop-downs for one answer, text boxes for
words and numbers, a date picker for the launch. Each control carries a tag naming the question
and the option, so reading a filled template is exact and needs no AI: it is free and instant.

The questions and options come from matcher.QUESTIONS and powerups (one source of truth), so a
new option shows up in the next template download by itself.

    build()            -> the .docx bytes (built on demand, never stale)
    is_template(data)  -> True for a file made from this template (the ID in the footer)
    read(data)         -> {"raw": answers for matcher.clean_answers, "fields": {...}, "found": [...]}
"""
import html
import io
import re
import zipfile
from datetime import date, datetime

TEMPLATE_ID = "HELV-BRIEF-V1"
FILE_NAME = "HelloVoice-Brief-Template.docx"

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"


def _countries():
    import fit
    return [(cc, name) for cc, name in fit.COUNTRIES if cc in ("SA", "AE", "EG", "KW", "QA", "BH", "OM", "JO")]


def sections():
    """[(section title, [field])]; a field is {id, label, kind: text|number|date|one|many, options, hint}."""
    import matcher
    import powerups
    q = matcher._BY_ID
    opts = lambda qid: [(v, l) for v, l in q[qid]["options"] if v not in ("any", "open", "none", "auto") or qid in ("mix",)]
    pq = {x["id"]: x for x in powerups.QUESTIONS}
    return [
        ("1. The campaign", [
            {"id": "brand", "label": "Brand", "kind": "text"},
            {"id": "product", "label": "Product or service", "kind": "text"},
            {"id": "claim", "label": "Main claim (exactly as your regulatory team approved it)", "kind": "text"},
            {"id": "goal", "label": "Goal (tick one or more)", "kind": "many", "options": opts("goal")},
            {"id": "platforms", "label": "Platforms (tick one or more)", "kind": "many", "options": [o for o in q["platforms"]["options"] if o[0] != "any"]},
            {"id": "market", "label": "Countries the audience is in (tick one or more)", "kind": "many", "options": _countries()},
            {"id": "category", "label": "Product space (tick one or more)", "kind": "many", "options": q["category"]["options"]},
            {"id": "launch", "label": "Launch or start date", "kind": "date"},
        ]),
        ("2. The audience", [
            {"id": "gender", "label": "Who is the audience?", "kind": "one", "options": q["gender"]["options"]},
            {"id": "age", "label": "Main age groups (tick one or more)", "kind": "many", "options": [o for o in q["age"]["options"] if o[0] != "Any"]},
            {"id": "content_lang", "label": "Content language", "kind": "one", "options": pq["content_lang"]["options"]},
        ]),
        ("3. The creators", [
            {"id": "count", "label": "How many creators?", "kind": "number", "hint": "A number, e.g. 10"},
            {"id": "mix", "label": "Creator mix", "kind": "one", "options": q["mix"]["options"]},
            {"id": "creator_size", "label": "Creator sizes (tick any)", "kind": "many", "options": q["creator_size"]["options"]},
            {"id": "creator_type", "label": "Creator type (tick any)", "kind": "many", "options": pq["creator_type"]["options"]},
            {"id": "max_fake", "label": "Highest share of fake followers you accept", "kind": "one", "options": q["max_fake"]["options"]},
            {"id": "licence", "label": "Mawthooq licence", "kind": "one", "options": pq["licence"]["options"]},
            {"id": "deliverable", "label": "Content they should make (tick any)", "kind": "many", "options": q["deliverable"]["options"]},
            {"id": "budget", "label": "Budget for creators, SAR before VAT", "kind": "number", "hint": "A number, e.g. 120000"},
            {"id": "notes", "label": "Anything else we should know?", "kind": "text"},
        ]),
    ]


# ------------------------------------------------------------------------------------------ build --

def _esc(s):
    return html.escape(str(s), quote=True)


def _run(text, bold=False, size=None, color=None, font=None):
    pr = ""
    if bold:
        pr += "<w:b/>"
    if color:
        pr += '<w:color w:val="%s"/>' % color
    if size:
        pr += '<w:sz w:val="%d"/>' % size
    if font:
        pr += '<w:rFonts w:ascii="%s" w:eastAsia="%s" w:hAnsi="%s"/>' % (font, font, font)
    return '<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % (("<w:rPr>%s</w:rPr>" % pr) if pr else "", _esc(text))


def _p(inner, space_after=60):
    return '<w:p><w:pPr><w:spacing w:after="%d"/></w:pPr>%s</w:p>' % (space_after, inner)


def _checkbox(tag):
    return ('<w:sdt><w:sdtPr><w:tag w:val="%s"/><w14:checkbox><w14:checked w14:val="0"/>'
            '<w14:checkedState w14:val="2612" w14:font="MS Gothic"/><w14:uncheckedState w14:val="2610" w14:font="MS Gothic"/>'
            '</w14:checkbox></w:sdtPr><w:sdtContent>%s</w:sdtContent></w:sdt>') % (_esc(tag), _run("☐", font="MS Gothic"))


def _dropdown(tag, options):
    items = '<w:listItem w:displayText="Choose one" w:value=""/>' + "".join(
        '<w:listItem w:displayText="%s" w:value="%s"/>' % (_esc(l), _esc(v)) for v, l in options)
    return ('<w:sdt><w:sdtPr><w:tag w:val="%s"/><w:showingPlcHdr/><w:dropDownList>%s</w:dropDownList></w:sdtPr>'
            '<w:sdtContent>%s</w:sdtContent></w:sdt>') % (_esc(tag), items, _run("Choose one", color="808080"))


def _textbox(tag, hint="Type here"):
    return ('<w:sdt><w:sdtPr><w:tag w:val="%s"/><w:showingPlcHdr/><w:text w:multiLine="1"/></w:sdtPr>'
            '<w:sdtContent>%s</w:sdtContent></w:sdt>') % (_esc(tag), _run(hint, color="808080"))


def _datebox(tag):
    return ('<w:sdt><w:sdtPr><w:tag w:val="%s"/><w:showingPlcHdr/><w:date><w:dateFormat w:val="d MMMM yyyy"/>'
            '<w:lid w:val="en-GB"/><w:storeMappedDataAs w:val="dateTime"/><w:calendar w:val="gregorian"/></w:date></w:sdtPr>'
            '<w:sdtContent>%s</w:sdtContent></w:sdt>') % (_esc(tag), _run("Pick a date", color="808080"))


def _cell(inner, width, shade=None):
    sh = '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % shade if shade else ""
    return '<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s</w:tcPr>%s</w:tc>' % (width, sh, inner)


def _field_row(f):
    label = _p(_run(f["label"], bold=True, size=20), 0)
    if f["kind"] == "many":
        cell = "".join(_p(_checkbox("%s=%s" % (f["id"], v)) + _run(" " + l, size=20), 20) for v, l in f["options"])
    elif f["kind"] == "one":
        cell = _p(_dropdown(f["id"], f["options"]), 0)
    elif f["kind"] == "date":
        cell = _p(_datebox(f["id"]), 0)
    else:
        cell = _p(_textbox(f["id"], f.get("hint") or "Type here"), 0)
    return "<w:tr>%s%s</w:tr>" % (_cell(label, 3600, "EAF5EE"), _cell(cell, 5800))


def build():
    """The template as .docx bytes."""
    body = [_p(_run("HelloVoice campaign brief", bold=True, size=36, color="0C5A2D"), 80),
            _p(_run("Fill this template and upload it in HELVi Connect (Build a shortlist with AI > Brief file). "
                    "Tick boxes and drop-downs are read exactly, so your shortlist matches your brief. "
                    "Leave anything you are unsure of empty: Helvi asks before building.", size=20, color="444444"), 200)]
    borders = "".join('<w:%s w:val="single" w:sz="4" w:space="0" w:color="C9D8CF"/>' % b
                      for b in ("top", "left", "bottom", "right", "insideH", "insideV"))
    for title, fields in sections():
        body.append(_p(_run(title, bold=True, size=26, color="0C5A2D"), 80))
        body.append('<w:tbl><w:tblPr><w:tblW w:w="9400" w:type="dxa"/><w:tblBorders>%s</w:tblBorders>'
                    '<w:tblCellMar><w:top w:w="80" w:type="dxa"/><w:left w:w="120" w:type="dxa"/>'
                    '<w:bottom w:w="80" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tblCellMar></w:tblPr>'
                    '<w:tblGrid><w:gridCol w:w="3600"/><w:gridCol w:w="5800"/></w:tblGrid>%s</w:tbl>'
                    % (borders, "".join(_field_row(f) for f in fields)))
        body.append(_p("", 160))
    body.append(_p(_run("Template ID: %s · Do not remove this line." % TEMPLATE_ID, size=16, color="999999"), 0))
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="%s" xmlns:w14="%s" '
           'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" mc:Ignorable="w14">'
           '<w:body>%s<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
           '<w:pgMar w:top="1000" w:right="1100" w:bottom="1000" w:left="1100" w:header="600" w:footer="600" w:gutter="0"/>'
           '</w:sectPr></w:body></w:document>') % (W, W14, "".join(body))
    buf = io.BytesIO()
    z = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)
    z.writestr("[Content_Types].xml",
               '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
               '<Default Extension="xml" ContentType="application/xml"/>'
               '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
               '<Override PartName="/docProps/custom.xml" ContentType="application/vnd.openxmlformats-officedocument.custom-properties+xml"/>'
               '</Types>')
    z.writestr("_rels/.rels",
               '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               '<Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
               '<Relationship Id="r2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties" Target="docProps/custom.xml"/>'
               '</Relationships>')
    z.writestr("docProps/custom.xml",
               '<?xml version="1.0" encoding="UTF-8"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" '
               'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
               '<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="HELV_BRIEF"><vt:lpwstr>%s</vt:lpwstr></property>'
               '</Properties>' % TEMPLATE_ID)
    z.writestr("word/document.xml", doc)
    z.close()
    return buf.getvalue()


# ------------------------------------------------------------------------------------------- read --

_SDT = re.compile(r"<w:sdt>(.*?)</w:sdt>", re.S)


def _text_of(xml):
    return html.unescape("".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", xml))).strip()


class Damaged(ValueError):
    """A Word file whose zip is broken (cut off in the upload, or corrupt)."""


def _document(data):
    """document.xml of a Word file; None when it is not a Word file; Damaged when it is one but broken."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        info = z.getinfo("word/document.xml")
    except (zipfile.BadZipFile, KeyError, ValueError):
        return None
    if info.file_size > 20 * 1024 * 1024 or (info.compress_size and info.file_size / float(info.compress_size) > 200):
        return None
    try:
        return z.read("word/document.xml").decode("utf-8", "replace")
    except Exception:            # a truncated or corrupt entry: zlib.error, EOFError, BadZipFile (CRC)
        raise Damaged("broken")


def is_template(data):
    doc = _document(data)
    return bool(doc and TEMPLATE_ID in _text_of(doc))


def _number(text):
    t = str(text or "").lower().replace(",", "").replace("٬", "")
    t = t.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(k|thousand|m|million|ألف|مليون)?", t)
    if not m:
        return None
    v = float(m.group(1))
    unit = m.group(2) or ""
    return v * (1e6 if unit in ("m", "million", "مليون") else 1e3 if unit else 1)


def timing_of(launch, today=None):
    """The timing option for a launch date: asap (2 weeks), month (6 weeks), quarter (~4 months), later."""
    if not launch:
        return None
    try:
        d = datetime.strptime(launch[:10], "%Y-%m-%d").date() if len(launch) >= 10 else datetime.strptime(launch[:7] + "-01", "%Y-%m-%d").date()
    except ValueError:
        return None
    days = (d - (today or date.today())).days
    return "asap" if days <= 14 else "month" if days <= 42 else "quarter" if days <= 120 else "later"


def read(data):
    """The answers in a filled template (exact: from the content controls). Raises ValueError when
    the file is not the template."""
    doc = _document(data)
    if not doc or TEMPLATE_ID not in _text_of(doc):
        raise ValueError("not_template")
    kinds = {f["id"]: f for _, fs in sections() for f in fs}
    got, labels = {}, {}
    for m in _SDT.finditer(doc):
        block = m.group(1)
        tag = re.search(r'<w:tag w:val="([^"]*)"', block)
        if not tag:
            continue
        tag = html.unescape(tag.group(1))
        content = re.search(r"<w:sdtContent>(.*)</w:sdtContent>", block, re.S)
        text = _text_of(content.group(1)) if content else ""
        if "=" in tag:                                          # a tick box: "goal=awareness"
            qid, val = tag.split("=", 1)
            chk = re.search(r'<w14:checked w14:val="(\w+)"', block)
            on = (chk and chk.group(1) in ("1", "true")) or "☒" in text
            if on:
                got.setdefault(qid, []).append(val)
            continue
        if "<w:showingPlcHdr/>" in block:                     # still the grey placeholder
            continue
        f = kinds.get(tag)
        if not f:
            continue
        if f["kind"] == "one":
            by_label = {l.lower(): v for v, l in f["options"]}
            v = by_label.get(text.lower()) or (text if text in {v for v, _ in f["options"]} else None)
            if v:
                got[tag], labels[tag] = v, text
        elif f["kind"] == "date":
            full = re.search(r'w:fullDate="(\d{4}-\d{2}-\d{2})', block)
            if full:
                got[tag] = full.group(1)
            else:
                for fmt in ("%d %B %Y", "%d/%m/%Y", "%Y-%m-%d", "%d %b %Y"):
                    try:
                        got[tag] = datetime.strptime(text, fmt).date().isoformat()
                        break
                    except ValueError:
                        continue
        elif text:
            got[tag] = text[:600]
    return got


def to_raw(got, today=None):
    """Template answers -> the answers dict matcher.clean_answers reads, plus the free-text fields."""
    import matcher
    raw = {}
    for k in ("goal", "platforms", "market", "category", "age", "creator_size", "creator_type", "deliverable"):
        if got.get(k):
            raw[k] = got[k]
    for k in ("gender", "content_lang", "mix", "max_fake", "licence"):
        if got.get(k):
            raw[k] = got[k]
    n = _number(got.get("count"))
    if n:
        n = int(n)
        raw["count"] = str(n) if str(n) in matcher.COUNT_OF else "other:%d" % n
    b = _number(got.get("budget"))
    if b:
        raw["budget"] = "50" if b < 50000 else "150" if b <= 150000 else "400" if b <= 400000 else "400+"
    t = timing_of(got.get("launch"), today)
    if t:
        raw["timing"] = t
    for k in ("product", "claim"):
        if got.get(k):
            raw[k] = got[k][:200]
    if got.get("notes"):
        raw["notes"] = got["notes"][:600]
    return raw
