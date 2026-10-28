"""Reading a private creator's profile result (2026-10-28).

    python3 -m unittest admin/tests/test_private_profile.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from private_profile import extract, source  # noqa: E402


class Extract(unittest.TestCase):
    def test_instagram_profile(self):
        got = extract({"username": "Dr.Sara", "fullName": "Dr Sara Khalil", "followersCount": 48200,
                       "profilePicUrlHD": "https://cdn.example/a.jpg", "profilePicUrl": "https://cdn.example/b.jpg"})
        self.assertEqual(got, {"handle": "dr.sara", "followers": 48200, "name": "Dr Sara Khalil", "pic": "https://cdn.example/a.jpg"})

    def test_tiktok_profile(self):
        got = extract({"authorMeta": {"name": "dr7ossam", "nickName": "Dr Hossam", "fans": 91000, "avatar": "https://cdn.example/t.jpg"}})
        self.assertEqual((got["handle"], got["followers"], got["name"], got["pic"]), ("dr7ossam", 91000, "Dr Hossam", "https://cdn.example/t.jpg"))

    def test_missing_pieces_are_none_not_errors(self):
        got = extract({"username": "x"})
        self.assertEqual((got["handle"], got["followers"], got["name"], got["pic"]), ("x", None, None, None))
        self.assertEqual(extract(None), {})
        self.assertIsNone(extract({"username": "x", "followersCount": -3})["followers"])
        self.assertIsNone(extract({"username": "x", "profilePicUrl": "not a link"})["pic"])

    def test_the_job_source_names_the_company(self):
        self.assertEqual(source(55), "private:55")


if __name__ == "__main__":
    unittest.main()
