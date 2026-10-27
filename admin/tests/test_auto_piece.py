"""A video shared on several platforms must count as one video (2026-10-27).

    python3 -m unittest admin/tests/test_auto_piece.py
"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pieces import auto_piece  # noqa: E402

H = 3600


def make(rows):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE content (id INTEGER PRIMARY KEY, campaign_id INT, code TEXT, platform TEXT, posted_at INT, "
              "piece INT, hidden INT DEFAULT 0, section TEXT DEFAULT 'campaign')")
    for r in rows:
        c.execute("INSERT INTO content (id, campaign_id, code, platform, posted_at, piece) VALUES (?,?,?,?,?,?)", r)
    return c


def piece(c, i):
    return c.execute("SELECT piece FROM content WHERE id = ?", (i,)).fetchone()[0]


class AutoPiece(unittest.TestCase):
    def test_same_creator_other_platform_a_minute_apart_is_one_video(self):
        # Dr. Hossam Selim: TikTok 525 posted 15:00, Instagram 526 posted 15:01
        c = make([(525, 2, "H", "TikTok", 54000, None), (526, 2, "H", "Instagram", 54060, None)])
        self.assertEqual(auto_piece(c, 526), 525)
        self.assertEqual((piece(c, 525), piece(c, 526)), (525, 525))

    def test_joins_a_video_that_already_has_several_platforms(self):
        c = make([(491, 2, "A", "Instagram", 1000, 491), (493, 2, "A", "TikTok", 1100, 491), (494, 2, "A", "Facebook", 1200, None)])
        self.assertEqual(auto_piece(c, 494), 491)
        self.assertEqual({piece(c, 491), piece(c, 493), piece(c, 494)}, {491})

    def test_far_apart_is_another_video(self):
        c = make([(1, 2, "A", "TikTok", 0, None), (2, 2, "A", "Instagram", 13 * H, None)])
        self.assertIsNone(auto_piece(c, 2))

    def test_same_platform_is_another_video(self):
        c = make([(1, 2, "A", "Instagram", 0, None), (2, 2, "A", "Instagram", H, None)])
        self.assertIsNone(auto_piece(c, 2))

    def test_video_that_already_has_this_platform_is_not_joined(self):
        c = make([(1, 2, "A", "Instagram", 0, 1), (2, 2, "A", "TikTok", 100, 1), (3, 2, "A", "TikTok", 200, None)])
        self.assertIsNone(auto_piece(c, 3))

    def test_two_candidate_videos_is_left_to_a_person(self):
        c = make([(1, 2, "A", "TikTok", 0, None), (2, 2, "A", "Facebook", 100, None), (3, 2, "A", "Instagram", 200, None)])
        self.assertIsNone(auto_piece(c, 3))

    def test_other_creator_or_campaign_never_joins(self):
        c = make([(1, 2, "A", "TikTok", 0, None), (2, 2, "B", "Instagram", 60, None), (3, 5, "A", "Instagram", 60, None)])
        self.assertIsNone(auto_piece(c, 2))
        self.assertIsNone(auto_piece(c, 3))

    def test_no_posted_time_is_left_alone(self):
        c = make([(1, 2, "A", "TikTok", 0, None), (2, 2, "A", "Instagram", None, None)])
        self.assertIsNone(auto_piece(c, 2))


if __name__ == "__main__":
    unittest.main()
