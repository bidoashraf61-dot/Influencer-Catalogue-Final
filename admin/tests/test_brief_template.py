"""Brief template and reader upgrades (item 277, 2026-10-29).

    python3 admin/tests/test_brief_template.py
"""
import io
import re
import sys
import unittest
import zipfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import brief_template as bt
import briefsrc
import matcher


def fill(data, ticks=(), chosen=()):
    """The template as a client leaves it after ticking boxes and choosing / typing answers in Word."""
    z = zipfile.ZipFile(io.BytesIO(data))
    doc = z.read("word/document.xml").decode()
    for tag in ticks:
        i = doc.index('w:val="%s"' % tag)
        j = doc.index("</w:sdt>", i)
        doc = doc[:i] + doc[i:j].replace('w14:checked w14:val="0"', 'w14:checked w14:val="1"').replace("☐", "☒") + doc[j:]
    for tag, text in chosen:
        i = doc.index('<w:tag w:val="%s"/>' % tag)
        j = doc.index("</w:sdt>", i)
        blk = doc[i:j].replace("<w:showingPlcHdr/>", "")
        blk = re.sub(r"(<w:sdtContent>).*(</w:sdtContent>)", lambda m: m.group(1) + "<w:r><w:t>%s</w:t></w:r>" % text + m.group(2), blk, flags=re.S)
        doc = doc[:i] + blk + doc[j:]
    out = io.BytesIO()
    z2 = zipfile.ZipFile(out, "w")
    for n in z.namelist():
        z2.writestr(n, doc if n == "word/document.xml" else z.read(n))
    z2.close()
    return out.getvalue()


class Template(unittest.TestCase):
    def test_every_question_is_in_the_template(self):
        ids = {f["id"] for _, fs in bt.sections() for f in fs}
        for qid in ("goal", "platforms", "market", "category", "count", "mix", "creator_size", "creator_type", "content_lang",
                    "max_fake", "budget", "launch", "gender", "age"):
            self.assertIn(qid, ids)
        self.assertTrue(bt.is_template(bt.build()))

    def test_filled_template_reads_exactly(self):
        data = fill(bt.build(),
                    ticks=("goal=awareness", "goal=engagement", "platforms=Instagram", "market=SA", "market=KW",
                           "category=health care", "creator_type=doctor", "creator_size=micro"),
                    chosen=(("gender", "Mostly women"), ("mix", "Many micro"), ("count", "10"), ("budget", "SAR 120,000"),
                            ("max_fake", "15% or less"), ("launch", "1 December 2026"), ("product", "ZinCare")))
        raw = bt.to_raw(bt.read(data), today=date(2026, 10, 29))
        self.assertEqual(raw["goal"], ["awareness", "engagement"])
        self.assertEqual(raw["market"], ["SA", "KW"])
        self.assertEqual(raw["count"], "other:10")
        self.assertEqual(raw["budget"], "150")
        self.assertEqual(raw["timing"], "month")
        self.assertEqual(raw["mix"], "micro")
        answers, missing = matcher.clean_answers(raw)
        self.assertEqual(missing, [])
        b = matcher.to_brief(answers)
        self.assertEqual(b["count"], 10)
        self.assertEqual(b["target"]["country"], "SA|KW")
        self.assertEqual(b["target"]["power"]["creator_type"], ["doctor"])

    def test_empty_template_reads_nothing(self):
        self.assertEqual(bt.read(bt.build()), {})

    def test_other_files_are_refused(self):
        z = io.BytesIO()
        w = zipfile.ZipFile(z, "w")
        w.writestr("word/document.xml", "<w:document><w:body><w:p><w:r><w:t>My own brief</w:t></w:r></w:p></w:body></w:document>")
        w.close()
        for data in (z.getvalue(), b"%PDF-1.4 hello", b"plain text brief"):
            with self.assertRaises(briefsrc.SourceError) as e:
                briefsrc.from_template(data, "brief.docx")
            self.assertEqual(e.exception.reason, "not_template")

    def test_damaged_template_is_broken_not_a_crash(self):
        data = bytearray(bt.build())
        i = data.index(b"word/document.xml") + 200          # inside the compressed document
        data[i:i + 400] = b"\0" * 400
        with self.assertRaises(briefsrc.SourceError) as e:
            briefsrc.from_template(bytes(data), "brief.docx")
        self.assertIn(e.exception.reason, ("broken", "not_template"))
        with self.assertRaises(briefsrc.SourceError):
            briefsrc.from_template(bt.build()[:-300], "cut.docx")

    def test_timing_from_the_date(self):
        t = date(2026, 10, 29)
        self.assertEqual(bt.timing_of("2026-11-05", t), "asap")
        self.assertEqual(bt.timing_of("2026-12-01", t), "month")
        self.assertEqual(bt.timing_of("2027-01-15", t), "quarter")
        self.assertEqual(bt.timing_of("2027-06-01", t), "later")


class LinkReader(unittest.TestCase):
    def test_raw_from_model_answers(self):
        raw = briefsrc.raw_from({"goal": ["awareness", "engagement"], "markets": ["KW", "LB"], "count": 10, "budget_sar": 40000,
                                 "max_fake_pct": 20, "creator_type": ["doctor"], "content_lang": "ar", "mix": "big"})
        self.assertEqual(raw["market"], ["KW", "other:Lebanon"])
        self.assertEqual(raw["count"], "other:10")
        self.assertEqual(raw["budget"], "50")
        self.assertEqual(raw["max_fake"], "15")
        answers, _ = matcher.clean_answers(raw)
        self.assertEqual(matcher.to_brief(answers)["target"]["country"], "KW|LB")
        self.assertEqual(answers["goal"], ["awareness", "engagement"])


if __name__ == "__main__":
    unittest.main()
