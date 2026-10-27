"""post_numbers must take the Instagram-only figures from data-slayer's combined result (2026-10-27).

    python3 -m unittest admin/tests/test_post_numbers.py
"""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
_db = types.ModuleType("db")
_db.on = lambda *a, **k: None
sys.modules.setdefault("db", _db)
import apify  # noqa: E402


class PostNumbers(unittest.TestCase):
    def test_instagram_reel_shared_to_facebook_uses_the_instagram_figures(self):
        # Jamjoom reel 511: the plain totals add the Facebook copy's comments and plays.
        item = {"metrics": {"comment_count": 795, "fb_comment_count": 470, "ig_comment_count": 325,
                            "like_count": 5425, "ig_like_count": 5425, "fb_like_count": 2899,
                            "play_count": 537555, "fb_play_count": 317065, "ig_play_count": 220490,
                            "share_count": 2651, "save_count": 2418}}
        n = apify.post_numbers(item)
        self.assertEqual((n["comments"], n["views"], n["likes"]), (325, 220490, 5425))
        self.assertEqual((n["shares"], n["saves"]), (2651, 2418))

    def test_other_actors_are_unchanged(self):
        n = apify.post_numbers({"commentsCount": 12, "likesCount": 3, "videoPlayCount": 99})
        self.assertEqual((n["comments"], n["likes"], n["views"]), (12, 3, 99))

    def test_ig_figures_alone_do_not_override(self):
        # no fb_* counterpart: nothing to separate, the usual field is used
        n = apify.post_numbers({"metrics": {"comment_count": 7, "ig_comment_count": 5}})
        self.assertEqual(n["comments"], 7)


if __name__ == "__main__":
    unittest.main()
