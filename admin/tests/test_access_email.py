"""The "shared with you" email (owner, 2026-10-18): the sign-in code email's design for access invites.

    python3 admin/tests/test_access_email.py
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mailer  # noqa: E402


class AccessEmail(unittest.TestCase):
    def test_message(self):
        subj, text, html = mailer.access_message("campaign dashboard", 'Jam <b>joom</b> & "co"', "Abdelrahman Ashraf",
                                                 "view only", "https://x.test/campaign/dashboard/#t=abc", "a@b.co")
        self.assertEqual(subj, "Abdelrahman Ashraf shared the campaign dashboard with you")
        self.assertIsNone(re.search(r"\{[A-Za-z_]+\}", html))                    # nothing left unfilled
        self.assertIn("Jam &lt;b&gt;joom&lt;/b&gt; &amp; &quot;co&quot;", html)  # the name is escaped
        self.assertNotIn("<b>joom", html)
        self.assertIn("view only", html)
        self.assertIn('href="https://x.test/campaign/dashboard/#t=abc"', html)
        self.assertIn("a@b.co", html)
        self.assertIn("https://x.test/campaign/dashboard/#t=abc", text)
        self.assertIn("helvy-connect-on-ink-480.png", html)                      # the same header as the code email
        s2 = mailer.access_message("selection", "S", "", "view and edit", "https://x.test/s", "a@b.co")[0]
        self.assertEqual(s2, "HelloVoice shared a selection with you")


if __name__ == "__main__":
    unittest.main(verbosity=2)
