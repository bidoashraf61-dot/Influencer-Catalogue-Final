"""Private creators (2026-10-28): the link parsing, and the triggers that keep them private.

    python3 -m unittest admin/tests/test_creators_private.py
"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from creators_private import parse_profile, SCHEMA_STEPS  # noqa: E402


class Parse(unittest.TestCase):
    def test_profile_links(self):
        self.assertEqual(parse_profile("https://www.instagram.com/dr.sara/"), ("Instagram", "dr.sara", "https://www.instagram.com/dr.sara/"))
        self.assertEqual(parse_profile("instagram.com/x") , None)          # no scheme: not accepted
        self.assertEqual(parse_profile("https://www.tiktok.com/@dr7ossam?lang=en")[1], "dr7ossam")
        self.assertEqual(parse_profile("https://www.snapchat.com/add/abdelmagiedk20")[1], "abdelmagiedk20")
        self.assertEqual(parse_profile("https://www.youtube.com/@DrSara")[1], "DrSara")
        self.assertEqual(parse_profile("https://www.facebook.com/dr.sara.clinic")[1], "dr.sara.clinic")

    def test_a_post_or_a_stranger_is_not_a_profile(self):
        self.assertIsNone(parse_profile("https://www.instagram.com/reel/De2QdUTRNFZ/"))
        self.assertIsNone(parse_profile("https://www.tiktok.com/@dr7ossam/video/7701334726115757332/") and None)
        self.assertIsNone(parse_profile("https://example.com/dr.sara"))
        self.assertIsNone(parse_profile(""))


class Triggers(unittest.TestCase):
    def db(self):
        c = sqlite3.connect(":memory:")
        c.execute("CREATE TABLE creators (code TEXT PRIMARY KEY, name TEXT, active INTEGER, owner_code_id INTEGER)")
        for s in SCHEMA_STEPS[1:]:
            c.execute(s)
        return c

    def test_a_private_creator_cannot_be_inserted_active(self):
        c = self.db()
        with self.assertRaises(sqlite3.DatabaseError):
            c.execute("INSERT INTO creators VALUES ('PV-5-1', 'x', 1, 5)")

    def test_a_private_creator_cannot_be_made_active_or_set_free(self):
        c = self.db()
        c.execute("INSERT INTO creators VALUES ('PV-5-1', 'x', 0, 5)")
        with self.assertRaises(sqlite3.DatabaseError):
            c.execute("UPDATE creators SET active = 1 WHERE code = 'PV-5-1'")
        with self.assertRaises(sqlite3.DatabaseError):
            c.execute("UPDATE creators SET owner_code_id = NULL WHERE code = 'PV-5-1'")
        with self.assertRaises(sqlite3.DatabaseError):
            c.execute("UPDATE creators SET owner_code_id = 9 WHERE code = 'PV-5-1'")

    def test_roster_creators_are_untouched(self):
        c = self.db()
        c.execute("INSERT INTO creators VALUES ('HV-MC-007', 'Roster', 1, NULL)")
        c.execute("UPDATE creators SET active = 0 WHERE code = 'HV-MC-007'")
        c.execute("UPDATE creators SET active = 1 WHERE code = 'HV-MC-007'")
        self.assertEqual(c.execute("SELECT active FROM creators WHERE code = 'HV-MC-007'").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
