"""Item 181 (2026-10-20): no page may carry the old ACCESS CODE form or the client-side passcode.

Everyone signs in with their work email; the gate markup holds only the logo and a status line,
and portal.js draws the email sign-in in it. Checks the page generator's templates (the catalogue
and selection pages are built from it at deploy) and every hand-written page, plus the scripts.

    python3 admin/tests/test_no_code_gate.py
The browser side (timings, 502s, signed-in vs signed-out) is admin/tests/e2e_no_code_gate.mjs.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGES = ["index.html", "selection/index.html", "creator/index.html", "campaign/index.html",
         "campaign/dashboard/index.html", "account/index.html", "market/index.html"]
SCRIPTS = ["catalogue.js", "portal.js", "campaign.js", "creator.js", "dashboard.js", "account.js", "evidence.js"]
CODE_FORM = re.compile(r'id="cat-code"|id="cat-gate-form"|placeholder="Access code"|Enter the access code', re.I)


class NoCodeGate(unittest.TestCase):
    def test_generator_templates(self):
        src = (ROOT / "build" / "influencer_catalogue.py").read_text(encoding="utf-8")
        self.assertIsNone(CODE_FORM.search(src))
        self.assertNotIn("passHash", src)
        self.assertNotIn("Hellovoice123", src)
        self.assertNotIn("CATALOGUE_PASSCODE\", ", src)
        # Both pages start on the logo alone while the server is asked.
        self.assertEqual(src.count('<body class="cat-locked cat-checking"'), 2)
        self.assertEqual(src.count('id="cat-gate-note"'), 2)

    def test_pages(self):
        for page in PAGES:
            f = ROOT / page
            if not f.exists():
                continue
            html = f.read_text(encoding="utf-8")
            self.assertIsNone(CODE_FORM.search(html), page)
            self.assertNotIn('type="password"', html, page)
            self.assertNotIn("passHash", html, page)

    def test_scripts(self):
        for name in SCRIPTS:
            js = (ROOT / "assets" / "js" / name).read_text(encoding="utf-8")
            self.assertNotIn("cat-gate-form", js, name)          # no code form is wired up
            self.assertNotIn('"cat-code"', js, name)
            self.assertNotIn("/api/unlock", js, name)              # nothing posts a typed code
            self.assertNotIn("passHash", js, name)
        portal = (ROOT / "assets" / "js" / "portal.js").read_text(encoding="utf-8")
        # The sign-in no longer waits for the mail key, and a 401 seen by a page draws it.
        self.assertNotIn("if (r.b && r.b.email_signin) enhanceGate", portal)
        self.assertIn('addEventListener("cat:locked"', portal)
        self.assertNotIn("paneShared", portal)


if __name__ == "__main__":
    unittest.main()
