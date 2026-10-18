"""The invite row offers the portal's emails, Give access and Send invite (owner, 2026-10-18)."""
import unittest

import access


class InviteFields(unittest.TestCase):
    def test_has_both_buttons_and_a_picker(self):
        h = access.invite_fields("inv")
        self.assertIn("Give access", h)
        self.assertIn("Send invite", h)
        self.assertIn("list='inv-people'", h)


if __name__ == "__main__":
    unittest.main()
