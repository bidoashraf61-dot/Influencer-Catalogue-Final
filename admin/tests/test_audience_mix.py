"""Audience countries card (owner, 2026-10-18): the creators' own profile audience weighted by reach, no
catalogue-average filler, the campaign's target market shown, and a per-campaign hide switch.

    python3 admin/tests/test_audience_mix.py
"""
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402
import db, metrics  # noqa: E402


def analysed(code, countries):
    db.save_analysis(code, {"audience": {"countries": [{"code": c, "pct": p} for c, p in countries]}}, source="test")


class AudienceMix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base.seed()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(base.TMP, ignore_errors=True)

    def test_weighted_by_reach_without_filler(self):
        a, b, c = "HV-MI-001", "HV-MI-002", "HV-MI-005"
        analysed(a, [("EG", 60), ("SA", 20)])
        analysed(b, [("SA", 80), ("EG", 10)])
        # c has no analysis: its reach must NOT be filled with an average
        out = metrics.audience_mix([{"code": a}, {"code": b}, {"code": c}], {a: 100, b: 300, c: 600}, "SA")
        eg = next(r["pct"] for r in out["countries"] if r["code"] == "EG")
        sa = next(r["pct"] for r in out["countries"] if r["code"] == "SA")
        self.assertAlmostEqual(eg, (100 * .60 + 300 * .10) / 400 * 100, places=4)      # shares of the analysed reach
        self.assertAlmostEqual(sa, (100 * .20 + 300 * .80) / 400 * 100, places=4)
        self.assertEqual(out["basis"], "partial")
        self.assertAlmostEqual(out["coverage"], 40.0, places=4)
        self.assertEqual((out["analysed"], out["creators"]), (2, 3))
        self.assertEqual((out["target"]["code"], out["target"]["rank"]), ("SA", 1))
        # every creator analysed
        full = metrics.audience_mix([{"code": a}, {"code": b}], {a: 100, b: 300}, "EG")
        self.assertEqual(full["basis"], "own")
        self.assertEqual(full["target"]["rank"], 2)

    def test_nothing_analysed_is_none_and_no_reach_uses_equal_weights(self):
        self.assertIsNone(metrics.audience_mix([{"code": "HV-MI-009"}], {"HV-MI-009": 50}))
        analysed("HV-MI-001", [("EG", 60), ("SA", 20)])
        analysed("HV-MI-002", [("SA", 80), ("EG", 10)])
        eq = metrics.audience_mix([{"code": "HV-MI-001"}, {"code": "HV-MI-002"}], {}, "XX")
        self.assertEqual(eq["basis"], "own")
        self.assertEqual(eq["target"], {"code": "XX", "pct": 0.0, "rank": None})   # target market absent from the audience

    def test_hide_switch(self):
        k = db.create_campaign("Aud test", code_id=None)
        self.assertTrue(metrics.visibility(db.campaign(k))["audience"])               # on by default (old campaigns too)
        db.save_campaign(k, visibility='{"audience": false}')
        self.assertFalse(metrics.visibility(db.campaign(k))["audience"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
