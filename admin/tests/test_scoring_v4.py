"""Scoring v4: engagement, view rate, interest and consistency, weighted by the campaign objective.
Run: python3 -I admin/tests/test_scoring_v4.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import fit  # noqa: E402
import score_model as sm  # noqa: E402

sm._cache.update(at=1e18, over={"interest_on": True, "post_scan_on": True})   # the full model

SERIES = [9000, 6000, 12000, 7000, 8000, 7500, 9500, 6500, 7000, 8200, 7900, 8100]


def doc(**kw):
    d = {"followers": 60000, "er": 1.6, "sample_posts": 20, "median_views": 7500, "views_series": SERIES,
         "hashtags": [{"tag": "#skincare", "count": 40.0}], "basic": True}
    d.update(kw)
    return d


def score(d, cat="Beauty", objective="Balanced", platform="Instagram"):
    return fit.score_core(d, platform, d.get("followers"), objective, {"category": cat, "country": "SA"})


def part(r, key):
    return [p for p in r["parts"] if p["key"] == key][0]


class V4(unittest.TestCase):
    def test_four_parameters(self):
        r = score(doc())
        self.assertEqual([p["key"] for p in r["parts"]], ["engagement", "view_rate", "interest", "consistency"])
        self.assertAlmostEqual(sum(p["w"] for p in r["parts"]), 100.0, places=0)

    def test_objective_moves_the_weights(self):
        aw, en = score(doc(), objective="Awareness"), score(doc(), objective="Engagement")
        self.assertGreater(part(aw, "view_rate")["w"], part(en, "view_rate")["w"])
        self.assertGreater(part(en, "engagement")["w"], part(aw, "engagement")["w"])

    def test_half_the_available_posts_is_full_marks(self):
        s = lambda c: part(score(doc(hashtags=[{"tag": "#skincare", "count": c}])), "interest")["s"]
        self.assertAlmostEqual(s(50.0), 1.0, places=2)
        self.assertAlmostEqual(s(25.0), 0.5, places=2)

    def test_missing_data_hands_its_weight_over(self):
        r = score(doc(median_views=None, views_series=None, avg_views=None))
        keys = [p["key"] for p in r["parts"]]
        self.assertNotIn("view_rate", keys)
        self.assertAlmostEqual(sum(p["w"] for p in r["parts"]), 100.0, places=0)

    def test_steady_views_beat_swinging_views(self):
        swing = score(doc(views_series=[100, 20000, 50, 18000, 90, 25000, 70, 30000, 60, 22000, 80, 19000]))
        self.assertGreater(part(score(doc()), "consistency")["s"], part(swing, "consistency")["s"])

    def test_no_space_asked_has_no_interest(self):
        self.assertNotIn("interest", [p["key"] for p in score(doc(), cat="Any")["parts"]])

    def test_few_posts_read_limited_data(self):
        self.assertTrue(score(doc(sample_posts=6))["limited_data"])
        self.assertFalse(score(doc(sample_posts=20))["limited_data"])

    def test_metrics_listed(self):
        labels = [m["label"] for m in score(doc())["metrics"]]
        for want in ("Engagement", "View rate", "Interest", "Consistency", "Posts analysed", "Reach"):
            self.assertIn(want, labels)

    def test_implausible_engagement_is_flagged_not_scored(self):
        r = score(doc(er=37.8))
        self.assertNotIn("engagement", [p["key"] for p in r["parts"]])
        self.assertTrue(any(m["label"] == "Engagement" and m["level"] == "bad" for m in r["metrics"]))

    def test_feed_creator_without_views_cannot_read_strong(self):
        r = score(doc(er=6.0, median_views=None, views_series=None, avg_views=None, hashtags=[{"tag": "#skincare", "count": 100.0}]))
        self.assertLessEqual(r["score"], sm.FEED_CAP)
        self.assertTrue(r["limited_data"])

    def test_scale_either_direction(self):
        self.assertEqual(sm.scale(0.5, 2.0, 0.5), 1.0)
        self.assertEqual(sm.scale(2.5, 2.0, 0.5), 0.0)
        self.assertEqual(sm.scale(0.3, 0.3, 3.5), 0.0)


if __name__ == "__main__":
    unittest.main()
