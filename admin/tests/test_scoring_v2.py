"""Scoring v2 (fix batch 6): peer percentiles, size neutrality, limited data, multi-goal, caps, record."""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import peerfix  # noqa: E402
import benchmarks  # noqa: E402
import fit  # noqa: E402


def peers():
    rnd = random.Random(7)
    out = []
    for size, (lo, hi) in {"nano": (3000, 19000), "micro": (25000, 90000), "mid": (150000, 450000), "macro": (600000, 900000)}.items():
        for _ in range(60):
            f = rnd.randint(lo, hi)
            # every size has the SAME engagement and view-rate distribution: a size-neutral score must treat them alike
            out.append(("TikTok", {"followers": f, "er": rnd.uniform(1, 9), "er_basis": "views", "avg_views": f * rnd.uniform(0.05, 0.6),
                                   "sample_posts": 20}))
            out.append(("Instagram", {"followers": f, "er": rnd.uniform(0.3, 5)}))
    return out


class Scoring(unittest.TestCase):
    def setUp(self):
        benchmarks.SOURCE = peers
        benchmarks.invalidate()

    def tearDown(self):
        peerfix.clear_peers()

    def tt(self, followers, er, views_rate, **extra):
        return dict({"followers": followers, "er": er, "er_basis": "views", "avg_views": followers * views_rate, "basic": True,
                     "sample_posts": 20}, **extra)

    def test_peer_percentile_is_the_part(self):
        top = fit.score_core(self.tt(50000, 8.8, 0.55), "TikTok", objective="Awareness")
        mid = fit.score_core(self.tt(50000, 5.0, 0.32), "TikTok", objective="Awareness")
        low = fit.score_core(self.tt(50000, 1.2, 0.07), "TikTok", objective="Awareness")
        self.assertGreater(top["score"], mid["score"] + 20)
        self.assertGreater(mid["score"], low["score"] + 20)
        self.assertTrue(40 <= mid["score"] <= 60, mid["score"])
        parts = {p["key"]: p for p in top["parts"]}
        self.assertEqual(parts["engagement"]["src"], "peers")
        self.assertGreater(parts["engagement"]["s"], 0.9)
        self.assertIn("ahead of", top["strengths"][0])

    def test_size_does_not_move_the_score(self):
        scores = [fit.score_core(self.tt(f, 5.0, 0.32), "TikTok", objective="Awareness")["score"] for f in (8000, 60000, 300000, 750000)]
        self.assertLessEqual(max(scores) - min(scores), 16, scores)      # sampling noise of 60 peers per size
        a = fit.score_core(self.tt(8000, 5.0, 0.32), "TikTok", objective="Awareness")
        b = fit.score_core(self.tt(750000, 5.0, 0.32), "TikTok", objective="Awareness")
        self.assertEqual((a["reach_followers"], b["reach_followers"]), (8000, 750000))      # reach is shown, not scored
        self.assertNotIn("reach", [p["key"] for p in a["parts"]])

    def test_output_shape_and_confidence(self):
        r = fit.score_core(self.tt(50000, 5.0, 0.32), "TikTok", objective="Awareness")
        for k in ("score", "tag", "parts", "strengths", "watchouts", "checks", "conclusion", "objective", "platform", "basic",
                  "confidence", "reach_followers", "limited_data"):
            self.assertIn(k, r)
        self.assertEqual(r["confidence"]["level"], "high")
        self.assertEqual((r["confidence"]["posts"], r["confidence"]["source"]), (20, "peers"))
        self.assertGreaterEqual(r["confidence"]["peers_n"], 30)
        ig = fit.score_core({"followers": 50000, "er": 1.1, "basic": True, "sample_posts": 12}, "Instagram", objective="Engagement")
        self.assertEqual(ig["confidence"]["level"], "medium")                  # one benchmarked factor, 12 posts
        self.assertTrue(ig["limited_data"])

    def test_limited_data_when_a_peer_cell_is_thin(self):
        # Snapchat has no peers: parts fall back to the global estimate, count for half, and the score says so
        r = fit.score_core({"followers": 50000, "avg_views": 9000, "basic": True}, "Snapchat", objective="Awareness")
        self.assertEqual([p["src"] for p in r["parts"]], ["global"])
        self.assertEqual(r["confidence"]["level"], "low")
        r = fit.score_core({"followers": 50000, "basic": True}, "Snapchat", objective="Awareness")
        self.assertIsNone(r["score"])        # nothing to go on at all
        r = fit.score_core({"followers": 50000, "avg_views": 9000, "er": 3.0, "basic": True}, "Snapchat", objective="Awareness")
        parts = {p["key"]: p for p in r["parts"]}
        self.assertEqual(parts["engagement"]["src"], "global")
        self.assertEqual(parts["views"]["src"], "global")
        self.assertEqual(r["confidence"]["level"], "low")
        self.assertTrue(r["limited_data"])
        self.assertIn("Limited data", r["conclusion"])
        # a global estimate only counts for half, so it cannot carry the score alone
        self.assertEqual(parts["engagement"]["w"], round(1.5 * 0.5, 2))

    def test_consistency_only_with_a_series(self):
        steady = self.tt(50000, 5.0, 0.32, views_spread=0.2, sample_posts=100)
        wild = self.tt(50000, 5.0, 0.32, views_spread=3.0, sample_posts=100)
        # no spread peers yet: the factor is left out, not guessed
        self.assertNotIn("consistency", [p["key"] for p in fit.score_core(dict(steady), "TikTok", objective="Awareness")["parts"]])
        rnd = random.Random(5)
        benchmarks.SOURCE = lambda: peers() + [("TikTok", {"followers": rnd.randint(25000, 90000), "views_spread": rnd.uniform(0.3, 2.5)}) for _ in range(40)]
        benchmarks.invalidate()
        a = fit.score_core(dict(steady), "TikTok", objective="Awareness")
        b = fit.score_core(dict(wild), "TikTok", objective="Awareness")
        pa = {p["key"]: p for p in a["parts"]}["consistency"]["s"]
        pb = {p["key"]: p for p in b["parts"]}["consistency"]["s"]
        self.assertGreater(pa, 0.9)
        self.assertLess(pb, 0.1)
        self.assertGreater(a["score"], b["score"])

    def test_medians_preferred_when_present(self):
        a = fit.score_core(self.tt(50000, 5.0, 0.60), "TikTok", objective="Awareness")                       # a viral average
        b = fit.score_core(self.tt(50000, 5.0, 0.60, median_views=50000 * 0.08), "TikTok", objective="Awareness")  # its median is low
        self.assertGreater(a["score"], b["score"])

    def test_interest_from_keywords_and_future_shares(self):
        c = {"interest": "Skincare, Beauty, Lifestyle"}
        d = self.tt(50000, 5.0, 0.32)
        hit = fit.score_core(dict(d), "TikTok", objective="Awareness", target={"category": "skincare"}, creator=c)
        miss = fit.score_core(dict(d), "TikTok", objective="Awareness", target={"category": "automotive"}, creator=c)
        none = fit.score_core(dict(d), "TikTok", objective="Awareness")
        self.assertGreater(hit["score"], miss["score"])
        self.assertEqual(sorted(p["key"] for p in miss["parts"]), ["engagement", "interest", "views"])
        self.assertNotIn("interest", [p["key"] for p in none["parts"]])
        shares = fit.score_core(dict(d, interest_shares={"skincare": 80}), "TikTok", objective="Awareness", target={"category": "skincare"}, creator={"interest": ""})
        w = {p["key"]: p for p in shares["parts"]}["interest"]
        self.assertEqual((w["src"], w["s"]), ("doc", 1.0))
        self.assertEqual(w["w"], 1.5)                                         # measured: full weight
        kw = {p["key"]: p for p in hit["parts"]}["interest"]
        self.assertEqual(kw["w"], 0.75)                                       # keywords: estimated, half weight

    def test_weights_and_multi_goal(self):
        W = fit.WEIGHTS_V2
        self.assertEqual(W["Awareness"], {"engagement": 1.5, "views": 3.0, "consistency": 1.0, "interest": 1.5})
        self.assertEqual(W["Engagement"], {"engagement": 3.0, "views": 1.0, "consistency": 1.0, "interest": 1.5})
        self.assertEqual(W["Traffic"], {"engagement": 2.5, "views": 2.0, "consistency": 1.0, "interest": 2.0})
        self.assertNotIn("Conversion", W)
        blend = fit.blend(W, "Awareness+Engagement")
        self.assertAlmostEqual(blend["views"], 2.0)
        self.assertAlmostEqual(blend["engagement"], 2.25)
        for k in ("link", "activity", "reach", "market"):
            self.assertNotIn(k, blend)
        d = self.tt(50000, 8.8, 0.07)        # great engagement, weak views
        aw = fit.score_core(dict(d), "TikTok", objective="Awareness")["score"]
        en = fit.score_core(dict(d), "TikTok", objective="Engagement")["score"]
        both = fit.score_core(dict(d), "TikTok", objective="Awareness+Engagement")["score"]
        self.assertGreater(en, aw)
        self.assertTrue(min(aw, en) <= both <= max(aw, en))

    def test_fake_followers_cap_and_record_nudge(self):
        d = self.tt(50000, 8.8, 0.55, basic=False, fake_followers_pct=45.0)
        r = fit.score_core(dict(d), "TikTok", objective="Awareness")
        self.assertLessEqual(r["score"], fit.FAKE_CAP)
        self.assertTrue(any("capped" in w for w in r["watchouts"]))
        base = fit.score_core(self.tt(50000, 5.0, 0.32), "TikTok", objective="Awareness")["score"]
        good = {"posts": 6, "campaigns": 2, "er": 3.0, "typical_er": 2.0}
        few = dict(good, posts=3)
        up = fit.score_core(self.tt(50000, 5.0, 0.32), "TikTok", objective="Awareness", record=good)
        same = fit.score_core(self.tt(50000, 5.0, 0.32), "TikTok", objective="Awareness", record=few)
        self.assertEqual(up["score"], base + fit.RECORD_NUDGE)
        self.assertEqual(same["score"], base)                                  # a check, not a mover, under 5 posts
        self.assertTrue(any(c["label"] == "Our campaigns" for c in same["checks"]))

    def test_conversion_reads_as_traffic(self):
        d = self.tt(50000, 5.0, 0.32)
        self.assertEqual(fit.score_core(dict(d), "TikTok", objective="Conversion")["score"],
                         fit.score_core(dict(d), "TikTok", objective="Traffic")["score"])
        self.assertEqual(fit.score_core(dict(d), "TikTok", objective="Conversion")["objective"], "Traffic")
        bal = fit.score_core(dict(d), "TikTok", objective="Balanced")
        self.assertEqual(bal["objective"], "Balanced")

    def test_roster_only_gets_a_neutral_listed_number(self):
        r = fit.score_core({"followers": 40000, "basic": True, "roster_only": True}, "TikTok", objective="Awareness",
                           target={"category": "skincare"}, creator={"interest": "Skincare"})
        self.assertIsNotNone(r["score"])
        self.assertEqual(r["confidence"]["level"], "low")
        none = fit.score_core({"followers": 40000, "basic": True, "roster_only": True}, "TikTok", objective="Awareness")
        self.assertEqual(none["score"], 50)

    def test_real_roster_cells_score_sensibly(self):
        peerfix.load_peers()
        r = fit.score_core({"followers": 60000, "er": 12.0, "er_basis": "views", "avg_views": 30000, "basic": True, "sample_posts": 20},
                           "TikTok", objective="Awareness")
        self.assertGreater(r["score"], 70)
        self.assertEqual(r["confidence"]["level"], "high")


if __name__ == "__main__":
    unittest.main()
