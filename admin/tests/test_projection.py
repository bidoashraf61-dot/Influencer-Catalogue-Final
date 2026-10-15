"""What a selection projects (owner, 2026-10-15): views for awareness, likes + comments for an
engagement or conversion objective, per creator as [typical, best case, estimated].

    python3 admin/tests/test_projection.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fit  # noqa: E402


class Metric(unittest.TestCase):
    def test_objective_picks_the_metric(self):
        self.assertEqual(fit.metric_for("Awareness"), "views")
        self.assertEqual(fit.metric_for(None), "views")
        self.assertEqual(fit.metric_for("Balanced"), "views")
        self.assertEqual(fit.metric_for("Engagement"), "engagement")
        self.assertEqual(fit.metric_for("Conversion"), "engagement")             # legacy, read as Traffic
        self.assertEqual(fit.metric_for("Traffic"), "engagement")
        self.assertEqual(fit.metric_for("Awareness+Engagement"), "views")       # awareness leads


class Engagement(unittest.TestCase):
    def test_typical_best_and_estimate(self):
        import db
        import server
        real = db.analyses_for
        db.analyses_for = lambda codes: {
            "A": {"TikTok": {"data": {"median_likes": 100, "median_comments": 10,
                                      "top_posts": [{"likes": 900, "comments": 50}, {"likes": 200}]}}},
            "B": {"Instagram": {"data": {"avg_likes": 40, "avg_comments": 5}}}}
        try:
            by = {"C": {"followers": 10000}}
            out = server.Handler.selection_engagement(["A", "B", "C", "D"], by)
        finally:
            db.analyses_for = real
        self.assertEqual(out["A"], [110, 330, False])        # best post 950 capped at 3x typical
        self.assertEqual(out["B"], [45, 67, False])          # no posts: 1.5x typical
        self.assertEqual(out["C"], [100, 300, True])         # no numbers: 1-3% of followers
        self.assertNotIn("D", out)


if __name__ == "__main__":
    unittest.main()
