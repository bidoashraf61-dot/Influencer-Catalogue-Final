"""Creator gender (owner, 2026-10-18): the setter, the Male / Female roster filter, and the AI reader.

    python3 admin/tests/test_gender.py
"""
import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
import e2e_portal as base  # noqa: E402
import db, gemini, paging  # noqa: E402
import gender_backfill as gb  # noqa: E402


def stub_for(answers):
    def stub(body):
        text = json.dumps([{"i": i, "g": g, "c": c} for i, (g, c) in enumerate(answers)])
        return {"candidates": [{"content": {"parts": [{"text": text}]}}], "usageMetadata": {}}
    return stub


class Gender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base.seed()

    @classmethod
    def tearDownClass(cls):
        gemini.STUB = None
        shutil.rmtree(base.TMP, ignore_errors=True)

    def test_setter_and_precedence(self):
        code = db.list_creators(active_only=True)[0]["code"]
        self.assertTrue(db.set_gender(code, "Female", "ai", 0.9))
        c = db.creator(code)
        self.assertEqual((c["gender"], c["gender_source"], c["gender_conf"]), ("female", "ai", 0.9))
        self.assertFalse(db.set_gender(code, "female", "ai", 0.9))                # nothing changed
        self.assertTrue(db.set_gender(code, "male", "admin"))                     # the team's word
        self.assertFalse(db.set_gender(code, "female", "ai", 0.99))               # the AI never overwrites it
        self.assertFalse(db.set_gender(code, "female", "sheet", 1.0))
        self.assertEqual(db.creator(code)["gender"], "male")
        self.assertTrue(db.set_gender(code, "", "admin"))                         # cleared
        self.assertIsNone(db.creator(code)["gender"])
        self.assertFalse(db.set_gender(code, "other", "admin"))                   # only male / female count

    def test_roster_filter_and_facets(self):
        cards = [{"code": "A1", "name": "A", "tier": "Nano", "platform": "Instagram", "gender": "female", "followers": 10},
                 {"code": "A2", "name": "B", "tier": "Nano", "platform": "Instagram", "gender": "male", "followers": 9},
                 {"code": "A3", "name": "C", "tier": "Nano", "platform": "Instagram", "gender": "", "followers": 8}]
        idx = paging.Index({"v": 1}, cards, [{"name": "Nano"}])
        self.assertEqual(idx.facets()["gender"], ["Male", "Female"])
        f = paging.clean_query({"gender": ["Female"]})
        self.assertEqual(f["gender"], ["Female"])
        self.assertTrue(paging.filtering(f))
        self.assertEqual(paging.clean_query({"gender": ["Alien"]})["gender"], [])       # unknown values are dropped
        got = paging.page(idx, f)
        self.assertEqual([c["code"] for c in got["items"]], ["A1"])               # unknown gender is not in either list
        got2 = paging.page(idx, paging.clean_query({"gender": ["Male", "Female"]}))
        self.assertEqual(sorted(c["code"] for c in got2["items"]), ["A1", "A2"])
        none = paging.Index({"v": 2}, [dict(c, gender="") for c in cards], [{"name": "Nano"}])
        self.assertEqual(none.facets()["gender"], [])                             # no filter offered until someone is known

    def test_ai_reader(self):
        gemini.STUB = stub_for([("female", 0.95), ("unknown", 0.2), ("male", 0.9)])
        got = gb.classify([("C1", "Noha Ali", "noha.ali"), ("C2", "Glow Clinic", "glowclinic"), ("C3", "Khalid", "khalid_k")], gemini)
        self.assertEqual(got, {"C1": ("female", 0.95), "C2": ("unknown", 0.2), "C3": ("male", 0.9)})
        gemini.STUB = lambda body: {"candidates": [{"content": {"parts": [{"text": "[{\"i\": 99, \"g\": \"male\", \"c\": 1}, {\"i\": 0, \"g\": \"x\", \"c\": 1}]"}]}}], "usageMetadata": {}}
        self.assertEqual(gb.classify([("C1", "A", "a")], gemini), {})              # out-of-range or unknown labels are ignored


if __name__ == "__main__":
    unittest.main(verbosity=2)
