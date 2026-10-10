"""Peer benchmarks (fix batch 6): sizes, cells, percentiles, the 30-peer rule, the cache."""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import peerfix  # noqa: E402
import benchmarks  # noqa: E402


def rows(platform, n, lo, hi, er_lo=0.5, er_hi=6.0, seed=1, **extra):
    rnd = random.Random(seed)
    return [(platform, dict({"followers": rnd.randint(lo, hi), "er": rnd.uniform(er_lo, er_hi), "er_basis": "views",
                             "avg_views": rnd.randint(500, 20000)}, **extra)) for _ in range(n)]


class Sizes(unittest.TestCase):
    def test_bands(self):
        got = [benchmarks.size_of(f) for f in (0, 19999, 20000, 99999, 100000, 499999, 500000, 999999, 1000000)]
        self.assertEqual(got, ["nano", "nano", "micro", "micro", "mid", "mid", "macro", "macro", "mega"])


class Cells(unittest.TestCase):
    def setUp(self):
        benchmarks.SOURCE = lambda: rows("TikTok", 40, 25000, 90000) + rows("TikTok", 10, 150000, 400000, seed=2) \
            + rows("Instagram", 35, 1500, 18000, seed=3)
        benchmarks.invalidate()

    def tearDown(self):
        peerfix.clear_peers()

    def test_cells_are_per_platform_and_size(self):
        self.assertEqual(benchmarks.cell("TikTok", "micro", "er")["n"], 40)
        self.assertEqual(benchmarks.cell("TikTok", "mid", "er")["n"], 10)
        self.assertIsNone(benchmarks.cell("Snapchat", "micro", "er"))

    def test_percentile_needs_thirty_peers(self):
        self.assertIsNotNone(benchmarks.percentile("TikTok", "micro", "er", 3.0))
        self.assertIsNone(benchmarks.percentile("TikTok", "mid", "er", 3.0))          # only 10
        self.assertIsNone(benchmarks.median("TikTok", "mid", "er"))

    def test_percentile_is_monotone_and_bounded(self):
        a = benchmarks.percentile("TikTok", "micro", "er", 1.0)["pct"]
        b = benchmarks.percentile("TikTok", "micro", "er", 3.0)["pct"]
        c = benchmarks.percentile("TikTok", "micro", "er", 50.0)["pct"]
        self.assertTrue(0 <= a < b < c <= 1)
        self.assertLess(c, 1.0 + 1e-9)
        pc = benchmarks.percentile("TikTok", "micro", "er", 3.0)
        self.assertTrue(pc["p25"] <= pc["median"] <= pc["p75"])

    def test_size_neutrality_of_the_cells(self):
        # the same engagement is a different standing in a different size
        benchmarks.SOURCE = lambda: rows("TikTok", 40, 25000, 90000, 0.5, 3.0) + rows("TikTok", 40, 150000, 400000, 3.0, 8.0, seed=2)
        benchmarks.invalidate()
        low = benchmarks.percentile("TikTok", "micro", "er", 3.0)["pct"]
        high = benchmarks.percentile("TikTok", "mid", "er", 3.0)["pct"]
        self.assertGreater(low, 0.9)
        self.assertLess(high, 0.1)

    def test_a_cell_is_cached_then_refreshed(self):
        calls = []
        benchmarks.SOURCE = lambda: calls.append(1) or rows("TikTok", 40, 25000, 90000)
        benchmarks.invalidate()
        benchmarks.cell("TikTok", "micro", "er"); benchmarks.cell("TikTok", "micro", "er")
        self.assertEqual(len(calls), 1)
        benchmarks.invalidate()
        benchmarks.cell("TikTok", "micro", "er")
        self.assertEqual(len(calls), 2)

    def test_median_cell_preferred_when_big_enough(self):
        benchmarks.SOURCE = lambda: rows("TikTok", 40, 25000, 90000, median_views=3000, median_er_on_views=2.0)
        benchmarks.invalidate()
        med, n, metric = benchmarks.peer_median_pair("TikTok", "micro", "view_rate_med", "view_rate")
        self.assertEqual((metric, n), ("view_rate_med", 40))
        benchmarks.SOURCE = lambda: rows("TikTok", 10, 25000, 90000, median_views=3000) + rows("TikTok", 40, 25000, 90000, seed=9)
        benchmarks.invalidate()
        self.assertEqual(benchmarks.peer_median_pair("TikTok", "micro", "view_rate_med", "view_rate")[2], "view_rate")


class Samples(unittest.TestCase):
    def test_instagram_rate_is_per_follower_tiktok_per_view(self):
        ig = benchmarks.sample_of("Instagram", {"followers": 50000, "er": 1.2, "avg_reel_plays": 8000})
        self.assertEqual(ig["er"], 1.2)
        self.assertAlmostEqual(ig["view_rate"], 16.0)
        tt = benchmarks.sample_of("TikTok", {"followers": 50000, "er": 4.0, "er_basis": "views", "avg_views": 10000,
                                              "median_views": 6000, "median_er_on_views": 3.1, "views_series": [1, 2, 3, 4, 5, 6, 7, 8]})
        self.assertEqual((tt["er"], tt["er_med"]), (4.0, 3.1))
        self.assertAlmostEqual(tt["view_rate"], 20.0)
        self.assertAlmostEqual(tt["view_rate_med"], 12.0)
        self.assertIn("spread", tt)

    def test_rubbish_is_dropped(self):
        self.assertEqual(benchmarks.sample_of("Instagram", {"followers": 500, "er": 2}), {})
        self.assertNotIn("er", benchmarks.sample_of("Instagram", {"followers": 20000, "er": 400}))
        self.assertNotIn("er", benchmarks.sample_of("Instagram", {"followers": 20000, "er": 2, "likes_hidden": True}))

    def test_fixture_loads(self):
        cells = peerfix.load_peers()
        self.assertGreater(len(cells), 10)
        self.assertGreaterEqual(benchmarks.cell("TikTok", "micro", "er")["n"], 400)
        peerfix.clear_peers()


if __name__ == "__main__":
    unittest.main()
