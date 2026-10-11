"""selections_zero_price (owner, 2026-10-11): a listed selection prices every creator at 0,
including creators added later; other selections keep their prices.

    python3 admin/tests/e2e_zero_price.py
"""
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402
import e2e_portal_fixes6 as f6  # noqa: E402

import db, gemini, guard, mailer, selstatus, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


class ZeroPrice(unittest.TestCase):
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
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()

    def test_zero_and_stays_zero(self):
        c, _ = self.signup("zero@glowderma.com")
        a = self.selection(c, "Free", ["HV-MI-001"])
        b = self.selection(c, "Paid", ["HV-MI-001"])
        sa = db.selection(token=a)
        db.set_setting("selections_zero_price", [sa["id"]])
        s, pa, _ = c.get("/api/selection?s=" + a)
        s, pb, _ = c.get("/api/selection?s=" + b)
        self.assertEqual(pa["prices"], {"HV-MI-001": [0, 0]})
        self.assertNotEqual(pb["prices"].get("HV-MI-001"), [0, 0])
        # a creator added later is stored at zero too
        db.save_selection(sa["id"], sa["name"], ["HV-MI-001", "HV-MI-002"], {"HV-MI-002": [900, 900]}, 5000, 6000,
                          platform=sa["platform"])
        row = db.selection(token=a)
        import json
        self.assertEqual(json.loads(row["prices"]), {"HV-MI-001": [0, 0], "HV-MI-002": [0, 0]})
        self.assertEqual((row["total_from"], row["total_to"]), (0, 0))
        s, pa, _ = c.get("/api/selection?s=" + a)
        self.assertTrue(all(v == [0, 0] for v in pa["prices"].values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
