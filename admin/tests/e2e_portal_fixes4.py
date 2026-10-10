"""End-to-end tests for the HELVY Connect fix batch 4 (2026-10-10, branch portal-fixes-4):

- the AI shortlist goals are Awareness, Engagement, Traffic and Conversion (Balanced and
  Sales retired), several at once, scored as a combined objective;
- the ROI Calculator reads a budget typed in Arabic-Indic or Persian digits, shows every
  figure as a range, and sends no sources and no advice line to the client;
- an estimate saved before this batch loses its old advice and sources on the way out.

Same harness as e2e_portal.py (a throwaway copy of admin/*.py, an empty database, captured
mail, a scripted Gemini), so it never touches catalogue.db or the network.

    python3 admin/tests/e2e_portal_fixes4.py
"""
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import db, gemini, guard, mailer, roi, selstatus, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

ANS = {"platforms": ["Instagram"], "market": "SA", "category": ["skincare"], "count": "5", "budget": "400"}


class Fixes4(unittest.TestCase):
    signup = base.Portal.signup

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        mailer.CAPTURE = True
        gemini.STUB = base.stub
        views.set_base("")
        selstatus.EMAIL_DELAY = 0
        for code in ("HV-MI-001", "HV-MI-002", "HV-MD-004"):
            db.save_analysis(code, {"followers": 42000, "er": 4.6, "avg_views": 9100, "basic": True}, platform="Instagram")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()
        mailer.OUTBOX.clear()

    # ----------------------------------------------------------- AI shortlist --
    def test_01_goal_options_match_the_roi_calculator(self):
        c, _ = self.signup("goals@glowderma.com")
        s, q, _ = c.get("/api/brief/questions")
        goal = next(x for x in q["questions"] if x["id"] == "goal")
        self.assertEqual([o["value"] for o in goal["options"]], ["awareness", "engagement", "traffic", "conversion"])
        self.assertEqual([o["label"] for o in goal["options"]], ["Awareness", "Engagement", "Traffic", "Conversion"])
        self.assertTrue(goal["multi_ok"])
        self.assertNotIn("legacy", goal)

    def test_02_several_goals_build_one_combined_shortlist(self):
        c, _ = self.signup("multi@glowderma.com")
        s, b, _ = c.post("/api/brief/run", {"answers": dict(ANS, goal=["awareness", "traffic"]), "name": "Two goals"})
        self.assertEqual(s, 200, b)
        self.assertTrue(b["picks"])
        s, sel, _ = c.get("/api/selection?s=" + b["token"])
        self.assertEqual(sel["brief"]["objective"], "Awareness+Traffic")
        s, b2, _ = c.post("/api/brief/run", {"answers": dict(ANS, goal="conversion")})
        self.assertEqual(s, 200, b2)
        s, sel2, _ = c.get("/api/selection?s=" + b2["token"])
        self.assertEqual(sel2["brief"]["objective"], "Conversion")

    # ---------------------------------------------------------- ROI Calculator --
    def test_03_roi_reads_arabic_digits_and_shows_ranges_only(self):
        c, _ = self.signup("roi4@glowderma.com")
        body = {"goal": "engagement", "platforms": ["Instagram"], "mix": {"micro": 6}}
        a = c.post("/api/roi/estimate", dict(body, budget="١٢٠٬٠٠٠"))[1]["result"]
        b = c.post("/api/roi/estimate", dict(body, budget=120000))[1]["result"]
        self.assertEqual(a["budget"], 120000)
        self.assertEqual(a["figures"], b["figures"])
        for f in a["figures"]:
            self.assertTrue(f["range"][0] <= f["value"] <= f["range"][1], f)
        self.assertTrue(a["cost"]["scale"][0] <= a["cost"]["range"][0] and a["cost"]["range"][1] <= a["cost"]["scale"][1])
        text = json.dumps(a)
        for gone in ("advice", "sources", "Kolsquare", "planning assumptions", "forecast of sales"):
            self.assertNotIn(gone, text)

    def test_04_old_saved_estimates_lose_advice_and_sources(self):
        row = {"id": 1, "goal": "awareness", "created_at": 0, "input": "{}",
               "result": json.dumps({"figures": [], "advice": "x", "sources": ["Kolsquare"]})}
        out = roi.row_view(row)
        self.assertNotIn("advice", out["result"])
        self.assertNotIn("sources", out["result"])


if __name__ == "__main__":
    try:
        unittest.main(verbosity=1)
    finally:
        shutil.rmtree(base.TMP, ignore_errors=True)
