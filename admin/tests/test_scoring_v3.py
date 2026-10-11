"""Scoring v3: engagement against the international range, plus the product-space match read
from the posts we hold (weighted by how many posts there are). Run: python3 -I admin/tests/test_scoring_v3.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import fit  # noqa: E402

TAGS = [{"tag": "#skincare", "count": 40.0}, {"tag": "#riyadh", "count": 50.0}]


def doc(**kw):
    d = {"followers": 60000, "er": 1.6, "sample_posts": 12, "hashtags": TAGS, "basic": True}
    d.update(kw)
    return d


def score(d, cat="Any"):
    return fit.score_core(d, "Instagram", 60000, "Balanced", {"category": cat, "country": "SA"})


class V3(unittest.TestCase):
    def test_no_space_asked_is_engagement_only(self):
        r = score(doc())
        self.assertEqual([p["key"] for p in r["parts"]], ["engagement"])
        self.assertTrue(r["score_range"][0] <= r["score"] <= r["score_range"][1])

    def test_more_posts_naming_the_space_score_higher(self):
        low = score(doc(hashtags=[{"tag": "#skincare", "count": 10.0}]), "Beauty")["score"]
        high = score(doc(hashtags=[{"tag": "#skincare", "count": 80.0}]), "Beauty")["score"]
        self.assertGreater(high, low)
        m = {x["label"]: x for x in score(doc(), "Beauty")["metrics"]}
        self.assertEqual(m["Product space"]["value"], "5 of 12 posts")

    def test_available_posts_are_the_100_percent(self):
        def interest(d):
            return [p for p in score(d, "Beauty")["parts"] if p["key"] == "interest"][0]["s"]
        self.assertAlmostEqual(interest(doc(hashtags=[{"tag": "#skincare", "count": 100.0}])), 1.0, places=2)
        self.assertAlmostEqual(interest(doc(hashtags=[{"tag": "#skincare", "count": 25.0}])), 0.25, places=2)

    def test_keywords_only_counts_at_a_third(self):
        p = [p for p in score(doc(hashtags=[], sample_posts=0), "Beauty")["parts"] if p["key"] == "interest"][0]
        self.assertEqual(p["src"], "keywords")
        self.assertLess(p["w"], 0.2)

    def test_metrics_cover_engagement_posts_reach(self):
        labels = [m["label"] for m in score(doc())["metrics"]]
        for want in ("Engagement", "Posts analysed", "Reach"):
            self.assertIn(want, labels)


if __name__ == "__main__":
    unittest.main()
