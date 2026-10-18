"""The team notification emails use the designed HTML (owner, 2026-10-18)."""
import re
import unittest

import mailer


class NotifyEmail(unittest.TestCase):
    def test_designed_page_has_no_leftover_placeholders(self):
        page = mailer.notify_message("Handed to you", ['Ana gave you the selection "X".', "Open it."], "https://x.test/a?b=1&c=2", "k@x.test")
        self.assertFalse(re.findall(r"\{[A-Za-z_]+\}", page))
        self.assertIn("Open it", page)
        self.assertIn("Sent to k@x.test", page)
        self.assertNotIn("Not expecting", page)

    def test_escapes_names(self):
        page = mailer.notify_message("Handed to you", ['<b>x</b> gave you "<i>"'], None, "k@x.test")
        self.assertNotIn("<b>x</b>", page)


if __name__ == "__main__":
    unittest.main()
