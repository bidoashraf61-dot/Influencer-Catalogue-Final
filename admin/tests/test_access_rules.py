"""The gate's decision (2026-10-28).

    python3 -m unittest admin/tests/test_access_rules.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from access_rules import refusal, default_role  # noqa: E402


class Gate(unittest.TestCase):
    def test_owned_module_with_a_role_passes(self):
        for role in ("viewer", "editor", "admin"):
            self.assertIsNone(refusal("view", False, role, "GET"))
        self.assertIsNone(refusal("manage", False, "editor", "POST"))

    def test_company_without_the_module_is_locked_whatever_the_role(self):
        self.assertEqual(refusal("off", False, "admin", "GET"), "locked")
        self.assertEqual(refusal("off", False, "none", "POST"), "locked")

    def test_paused_is_told_apart_from_never_owned(self):
        self.assertEqual(refusal("off", True, "admin", "GET"), "paused")

    def test_no_role_is_refused_on_every_method(self):
        self.assertEqual(refusal("view", False, "none", "GET"), "no_role")
        self.assertEqual(refusal("manage", False, "none", "POST"), "no_role")

    def test_viewer_reads_but_cannot_change(self):
        self.assertIsNone(refusal("manage", False, "viewer", "GET"))
        self.assertEqual(refusal("manage", False, "viewer", "POST"), "read_only")
        self.assertEqual(refusal("manage", False, "viewer", "delete"), "read_only")

    def test_existing_account_holders_are_unchanged(self):
        # no company_code_id and no role row: admin, so nothing a client does today is refused
        self.assertEqual(default_role(False), "admin")
        self.assertIsNone(refusal("view", False, default_role(False), "POST"))

    def test_an_invited_colleague_has_nothing_until_given_a_role(self):
        self.assertEqual(refusal("view", False, default_role(True), "GET"), "no_role")


if __name__ == "__main__":
    unittest.main()
