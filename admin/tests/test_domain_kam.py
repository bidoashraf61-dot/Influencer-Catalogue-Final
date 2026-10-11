"""domain_kam (owner, 2026-10-11): a new account on a listed domain gets its account manager.

    python3 admin/tests/test_domain_kam.py
"""
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402
import db, portal  # noqa: E402


class DomainKam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(base.TMP, ignore_errors=True)

    def test_listed_domain_gets_kam(self):
        db.set_setting("domain_kam", {"PolyCo.com": "kam@hv.test"})
        portal.create_user("a@polyco.com", "A", "PolyCo", ip="1.1.1.1")
        u = portal.user_by_email("a@polyco.com")
        self.assertIsNotNone(u)
        self.assertEqual(u["kam"], "kam@hv.test")


if __name__ == "__main__":
    unittest.main(verbosity=2)
