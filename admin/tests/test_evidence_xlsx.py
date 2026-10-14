"""The competitor-evidence Excel template (admin/evidence_xlsx.py): the template opens with its sheets and
dropdowns, a filled copy imports exactly like the same data as JSON (derived fields included), bad cells
are named by sheet, row and column, and uploading again updates the pack. Every name here is invented.

    python3 admin/tests/test_evidence_xlsx.py
"""
import json
import sys
import tempfile
import unittest
import zipfile
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db  # noqa: E402

db.DB_PATH = Path(tempfile.mkdtemp(prefix="hv-evx-")) / "t.db"
import evidence, evidence_xlsx, xlsx  # noqa: E402
db.init()

HEAD_B = [h + (" *" if k in ("brand", "competitor", "fit") else "") for k, h, _ in evidence_xlsx.BRAND_COLS]
HEAD_P = [h + (" *" if k in evidence_xlsx.REQUIRED else "") for k, h, _, _ in evidence_xlsx.POST_COLS]
HEAD_C = [h for _, h, _ in evidence_xlsx.CREATOR_COLS]
PK = [k for k, _, _, _ in evidence_xlsx.POST_COLS]

BRANDS = [["Glow Serum", "Vitamin C serum for dark spots", "vitamin c, dark spots", "RivalSkin", "direct"],
          ["", "", "", "OtherCo", "partial"]]


def post(**kw):
    base = {"brand": "Glow Serum", "competitor": "RivalSkin", "platform": "instagram", "url": "", "handle": "noha.test",
            "name": "Noha Test", "creator_type": "influencer", "city": "Riyadh", "followers": "40000",
            "posted_at": "2026-03-01", "collab_type": "Own post, tagged", "product_tags": "Vitamin C serum",
            "views": "90000", "likes": "2000", "comments": "10", "paid_boost": "No", "likes_hidden": "No"}
    base.update(kw)
    return [base.get(k, "") for k in PK]


ROWS = [post(url="https://www.instagram.com/reel/T1/"),
        post(url="https://www.instagram.com/reel/T2/", views="30000", likes="", product_tags="moisturiser"),
        post(url="https://www.instagram.com/reel/T3/", handle="@Sara.Test", name="Sara Test", creator_type="hcp",
             views="2000000", likes="30", paid_boost="Yes", product_tags=""),
        post(url="https://www.instagram.com/reel/T4/", competitor="OtherCo", views="50000", likes="900",
             posted_at="45900", collab_type="Co-author")]


def book(rows=ROWS, brands=BRANDS, creators=()):
    return xlsx.write_book([("Instructions", [["x"]], None, None), ("Brands", [HEAD_B] + brands, None, None),
                            ("Posts", [HEAD_P] + rows, None, None), ("Creators", [HEAD_C] + list(creators), None, None)])


def as_json():
    """The same four posts, as the old scripts' JSON would carry them (derived values worked out by hand)."""
    def p(url, handle, name, ctype, views, likes, comments, rel, paid, comp, date, collab, x, rating, tags):
        return {"url": url, "platform": "instagram", "handle": handle, "name": name, "creator_type": ctype,
                "city": "Riyadh", "followers": 40000, "date": date, "collab_type": collab, "product_tags": tags or None,
                "relevance": rel, "views": views, "likes": likes, "comments": comments,
                "er_views": None if likes is None else round((likes + comments) / views, 6),
                "views_per_follower": round(views / 40000, 6), "x_brand_avg": x, "rating": rating,
                "likely_paid_boost": paid, "likes_hidden": likes is None}
    avg = (90000 + 30000) / 2.0
    return {"source": "Excel template", "platforms": ["instagram"], "brands": [{"brand": "Glow Serum",
            "product": "Vitamin C serum for dark spots", "competitors": [
                {"competitor": "RivalSkin", "fit": "direct", "posts_detail": [
                    p("https://www.instagram.com/reel/T1/", "noha.test", "Noha Test", "influencer", 90000, 2000, 10, "match", False,
                      "RivalSkin", "2026-03-01", "creator_post_tag", round(90000 / avg, 4), "good", "Vitamin C serum"),
                    p("https://www.instagram.com/reel/T2/", "noha.test", "Noha Test", "influencer", 30000, None, 10, "other", False,
                      "RivalSkin", "2026-03-01", "creator_post_tag", round(30000 / avg, 4), "average", "moisturiser"),
                    p("https://www.instagram.com/reel/T3/", "sara.test", "Sara Test", "hcp", 2000000, 30, 10, "unspecified", True,
                      "RivalSkin", "2026-03-01", "creator_post_tag", round(2000000 / avg, 4), None, "")]},
                {"competitor": "OtherCo", "fit": "partial", "posts_detail": [
                    p("https://www.instagram.com/reel/T4/", "noha.test", "Noha Test", "influencer", 50000, 900, 10, "match", False,
                      "OtherCo", "2025-08-31", "co_author", 1.0, "good", "Vitamin C serum")]}]}]}


def stored(pid):
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM evidence_posts WHERE pack_id = ? ORDER BY url", (pid,)).fetchall()
    skip = {"id", "pack_id", "note", "alt_handle", "save_rate", "posted_on", "content_type", "shares", "saves"}
    return [{k: r[k] for k in r.keys() if k not in skip} for r in rows]


class Template(unittest.TestCase):
    def test_1_template_has_sheets_headers_and_dropdowns(self):
        raw = evidence_xlsx.template()
        b = xlsx.read_all(raw)
        self.assertEqual(list(b), list(evidence_xlsx.SHEETS))
        self.assertEqual(b["Posts"][0][:5], ["Brand *", "Competitor *", "Platform *", "Post URL *", "Handle *"])
        self.assertEqual(len(b["Posts"]), 1)                       # header only: examples live on Instructions
        posts_xml = zipfile.ZipFile(io.BytesIO(raw)).read("xl/worksheets/sheet3.xml").decode()
        self.assertIn("<dataValidations", posts_xml)
        self.assertIn("Lists!$", posts_xml)
        for k in ("relevance", "er_views", "views_per_follower", "x_brand_avg", "rating"):
            self.assertNotIn(k, [c for c, _, _, _ in evidence_xlsx.POST_COLS])

    def test_2_round_trip_matches_json_import(self):
        a, n, _ = evidence.import_pack(book(), "From Excel", None)
        b, n2, _ = evidence.import_pack(json.dumps(as_json()), "From JSON", None)
        self.assertEqual((n, n2), (4, 4))
        self.assertEqual(stored(a), stored(b))
        pk = evidence.pack(a)
        br = json.loads(pk["brands"])[0]
        self.assertEqual(br["fit"], {"RivalSkin": "direct", "OtherCo": "partial"})
        self.assertEqual(br["match_tags"], ["vitamin c", "dark spots"])

    def test_3_bad_cells_are_named_and_nothing_imports(self):
        rows = ROWS + [post(url="https://www.instagram.com/reel/T9/", views="lots"),
                       post(url="not a link", competitor="Nobody"),
                       post(url="https://www.instagram.com/reel/T1/")]
        with db.connect() as conn:
            before = conn.execute("SELECT COUNT(*) FROM evidence_posts").fetchone()[0]
        with self.assertRaises(ValueError) as cx:
            evidence.import_pack(book(rows), "Bad", None)
        msg = str(cx.exception)
        self.assertIn("Posts sheet, row 6, Views: \"lots\" is not a number.", msg)
        self.assertIn("Posts sheet, row 7, Competitor: \"Nobody\" is not listed for Glow Serum", msg)
        self.assertIn("Posts sheet, row 7, Post URL: must start with https://.", msg)
        self.assertIn("Posts sheet, row 8, Post URL: the same post is already on row 2", msg)
        with db.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM evidence_posts").fetchone()[0], before)

    def test_4_brand_fit_checked(self):
        with self.assertRaises(ValueError) as cx:
            evidence.import_pack(book(brands=[["Glow Serum", "", "", "RivalSkin", "maybe"]]), "Bad fit", None)
        self.assertIn("Brands sheet, row 2, Competitor fit", str(cx.exception))

    def test_5_upload_again_updates_not_duplicates(self):
        pid, _, _ = evidence.import_pack(book(), "Re-upload", None)
        rows = [post(url="https://www.instagram.com/reel/T1/", views="99000")] + ROWS[1:3]     # T4 taken off, T1 changed
        evidence.import_pack(book(rows), None, None, pack_id=pid)
        got = {r["url"][-3:]: r for r in stored(pid)}
        self.assertEqual(sorted(got), ["T1/", "T2/", "T3/"])
        self.assertEqual(got["T1/"]["views"], 99000)

    def test_6_creators_sheet_and_excel_date(self):
        c = [["noha.test", "Noha Test", "influencer", "Riyadh", "40000", "https://www.instagram.com/noha.test/",
              "https://www.tiktok.com/@noha_tt", "", "", "", ""]]
        brands, posts, meta = evidence.parse_pack(book(creators=c))
        self.assertEqual(meta["creators"]["noha.test"]["links"]["TikTok"], "https://www.tiktok.com/@noha_tt")
        self.assertEqual([p for p in posts if p["url"].endswith("T4/")][0]["posted_at"], "2025-08-31")
        self.assertEqual([p for p in posts if p["url"].endswith("T3/")][0]["handle"], "sara.test")

    def test_7_not_the_template(self):
        bad = xlsx.write_book([("Sheet1", [["a"]], None, None)])
        with self.assertRaises(ValueError) as cx:
            evidence.parse_pack(bad)
        self.assertIn("not the competitor evidence template", str(cx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
