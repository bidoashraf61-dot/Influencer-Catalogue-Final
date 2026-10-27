"""The Instagram/Facebook views overlap (2026-10-27): a reel's fb_play_count is taken out of the campaign's unique
views only when a tracked Facebook post carries the same plays.

    python3 -m unittest admin/tests/test_overlap_views.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from overlap import overlap_views  # noqa: E402


class OverlapViews(unittest.TestCase):
    def test_tracked_facebook_copy_is_the_overlap(self):
        self.assertEqual(overlap_views({"fb_play_count": 2278007}, [2278007]), 2278007)

    def test_small_drift_between_two_captures_still_matches(self):
        self.assertEqual(overlap_views({"fb_play_count": 1000}, [1040]), 1000)

    def test_facebook_copy_we_do_not_track_is_not_removed(self):
        self.assertEqual(overlap_views({"fb_play_count": 2278007}, [100, 5000]), 0)
        self.assertEqual(overlap_views({"fb_play_count": 2278007}, []), 0)

    def test_no_facebook_figure_means_no_overlap(self):
        self.assertEqual(overlap_views({}, [5]), 0)
        self.assertEqual(overlap_views(None, [5]), 0)
        self.assertEqual(overlap_views({"fb_play_count": 0}, [0]), 0)


if __name__ == "__main__":
    unittest.main()
