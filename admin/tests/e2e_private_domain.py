"""team_sharing_off_domains (owner, 2026-10-11): a listed company's selections open only for the
account they are assigned to and HelloVoice; colleagues on the same domain and other accounts are refused.

    python3 admin/tests/e2e_private_domain.py
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


class PrivateDomain(unittest.TestCase):
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

    def test_listed_domain_keeps_selections_to_the_owner(self):
        owner, _ = self.signup("owner@pharmaco.com")
        mate, _ = self.signup("mate@pharmaco.com")
        other, _ = self.signup("other@elsewhere.com")
        tok = self.selection(owner, "Private", ["HV-MI-001"])
        s, b, _ = mate.get("/api/selection?s=" + tok)
        self.assertTrue(b.get("ok"))                                    # team sharing on by default
        db.set_setting("team_sharing_off_domains", ["PharmaCo.com"])
        for c, ok in ((owner, True), (mate, False), (other, False)):
            s, b, _ = c.get("/api/selection?s=" + tok)
            self.assertEqual(bool(b.get("ok")), ok)
        db.set_setting("team_sharing_off_domains", [])
        s, b, _ = mate.get("/api/selection?s=" + tok)
        self.assertTrue(b.get("ok"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
