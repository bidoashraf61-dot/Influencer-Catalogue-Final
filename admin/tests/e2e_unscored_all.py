"""selections_unscored = "all" (owner, 2026-10-11): every selection shows a fit label only, no score,
until the scoring logic is final. A list of ids still works; Helvy gives no numbers.

    python3 admin/tests/e2e_unscored_all.py
"""
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402
import e2e_portal_fixes6 as f6  # noqa: E402

import assistant, db, gemini, guard, mailer, selstatus, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


class UnscoredAll(unittest.TestCase):
    signup = base.Portal.signup
    selection = f6.Fixes6.selection

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        mailer.CAPTURE = True
        gemini.STUB = base.stub
        views.set_base("")
        selstatus.EMAIL_DELAY = 0
        db.save_analysis("HV-MI-001", f6.FULL, platform="Instagram")
        db.save_analysis("HV-MI-002", f6.BASIC, platform="Instagram")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()
        db.set_setting("selections_unscored", [])

    def test_all_hides_every_score_and_labels_matching(self):
        c, _ = self.signup("unscored@glowderma.com")
        tok = self.selection(c, "Paused", ["HV-MI-001", "HV-MI-002"])
        s, sel, _ = c.get("/api/selection?s=" + tok)
        self.assertTrue(sel["scores"])                                   # scored before the switch
        db.set_setting("selections_unscored", "all")
        s, sel, _ = c.get("/api/selection?s=" + tok)
        self.assertEqual(sel["scores"], {})
        self.assertTrue(sel["scoring_off"])
        self.assertFalse(sel["needs_objective"])
        self.assertEqual({k: v["fit"] for k, v in sel["verdicts"].items()},
                         {"HV-MI-001": "Matching", "HV-MI-002": "Matching"})
        res = assistant._explain({}, "HV-MI-001")
        self.assertIsNone(res["score"])
        self.assertTrue(res["paused"])

    def test_list_of_ids_still_works(self):
        c, _ = self.signup("unscored2@glowderma.com")
        a = self.selection(c, "Off", ["HV-MI-001"])
        b = self.selection(c, "On", ["HV-MI-001"])
        db.set_setting("selections_unscored", [db.selection(token=a)["id"]])
        s, sa, _ = c.get("/api/selection?s=" + a)
        s, sb, _ = c.get("/api/selection?s=" + b)
        self.assertEqual(sa["scores"], {})
        self.assertTrue(sb["scores"])
        self.assertNotIn("scoring_off", sb)


if __name__ == "__main__":
    unittest.main(verbosity=2)
