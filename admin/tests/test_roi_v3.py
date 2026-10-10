"""ROI Calculator v3 (fix batch 6): the chain, honest ranges, efficiency, combined error, the
planner on a toy roster, the advice and its actions, and what must never reach a client."""
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import peerfix  # noqa: E402
import benchmarks  # noqa: E402
import plans  # noqa: E402
import roi  # noqa: E402

LIB = None


def setup_module():
    plans.house_benchmarks = lambda: {}
    roi.db.setting = lambda key, default=None: default


def creator(code, followers, platform="TikTok", doc=None, score=None, name=None):
    return {"code": code, "name": name or code, "followers": {platform: followers}, "docs": {platform: doc} if doc else {},
            "scores": {platform: score} if score is not None else {}}


class Base(unittest.TestCase):
    def setUp(self):
        setup_module()
        benchmarks.SOURCE = lambda: []
        benchmarks.invalidate()
        self.lib = plans.library()


class Chain(Base):
    def test_efficiency_factor(self):
        self.assertEqual(roi.efficiency(None), 1.0)
        self.assertEqual(roi.efficiency(50), 1.0)
        self.assertAlmostEqual(roi.efficiency(100), 1.2)
        self.assertAlmostEqual(roi.efficiency(0), 0.8)

    def test_median_views_are_used_and_efficiency_applied_to_views_interactions_clicks(self):
        doc = {"median_views": 10000, "median_er_on_views": 4.0, "sample_posts": 100, "followers": 50000}
        a = roi.post_values("TikTok", 50000, doc, 50, self.lib)
        b = roi.post_values("TikTok", 50000, doc, 100, self.lib)
        self.assertEqual(a["basis"], "median")
        self.assertTrue(a["measured"])
        self.assertAlmostEqual(a["views"], 10000)
        self.assertAlmostEqual(a["interactions"], 10000 * 0.04)
        self.assertAlmostEqual(b["views"] / a["views"], 1.2)
        self.assertAlmostEqual(b["interactions"] / a["interactions"], 1.2)
        self.assertAlmostEqual(b["clicks"] / a["clicks"], 1.2)
        self.assertAlmostEqual(a["reach"], 10000 * self.lib["TikTok"]["reach_per_view"])

    def test_without_a_median_peers_then_own_average_then_guide(self):
        f = 50000
        doc = {"avg_views": 30000, "sample_posts": 20, "followers": f}
        guide = roi.post_values("TikTok", f, None, None, self.lib)
        self.assertEqual(guide["basis"], "guide")
        mid = (self.lib["TikTok"]["view_rate"]["micro"][0] + self.lib["TikTok"]["view_rate"]["micro"][1]) / 2.0
        self.assertAlmostEqual(guide["views"], f * mid / 100.0)
        avg = roi.post_values("TikTok", f, doc, None, self.lib)
        self.assertEqual(avg["basis"], "average")
        self.assertAlmostEqual(avg["views"], 30000)
        # a peer cell with 30+ creators beats the average
        benchmarks.SOURCE = lambda: [("TikTok", {"followers": 30000 + i * 1000, "avg_views": (30000 + i * 1000) * 0.10, "er": 3, "er_basis": "views"})
                                     for i in range(40)]
        benchmarks.invalidate()
        peer = roi.post_values("TikTok", f, doc, None, self.lib)
        self.assertEqual(peer["basis"], "peers")
        self.assertAlmostEqual(peer["views"], f * 0.10, delta=f * 0.01)

    def test_margin_from_sample_size(self):
        self.assertAlmostEqual(roi._margin(20), 0.48)
        self.assertAlmostEqual(roi._margin(100), 0.48 * math.sqrt(0.2))
        self.assertAlmostEqual(roi._margin(0), 0.48)
        self.assertAlmostEqual(roi._margin(5), 0.96)

    def test_instagram_engagement_per_follower_when_no_reels(self):
        v = roi.post_values("Instagram", 100000, {"er": 2.0, "sample_posts": 12, "followers": 100000, "avg_reel_plays": 40000}, None, self.lib)
        self.assertAlmostEqual(v["views"], 40000)
        self.assertAlmostEqual(v["interactions"], 100000 * 0.02, delta=1)


class Ranges(Base):
    def test_combined_error_is_smaller_than_the_sum_of_the_errors(self):
        posts = [roi.post_values("TikTok", 50000, {"median_views": 10000, "sample_posts": 20, "followers": 50000}, None, self.lib)
                 for _ in range(9)]
        tot, lo, hi = roi.combine(posts, "views", "m_views")
        self.assertAlmostEqual(tot, 90000)
        half = math.sqrt(9 * (0.48 * 10000) ** 2)
        self.assertAlmostEqual(hi, roi._sig2(tot + half, True), delta=1000)
        self.assertLess(half / tot, 0.48 / 2)                                  # 9 independent posts: a third of the single margin
        self.assertLess((hi - tot) / tot, 0.25)                                 # rounded up to two figures

    def test_range_never_narrower_than_ten_percent(self):
        posts = [roi.post_values("TikTok", 50000, {"median_views": 10000, "sample_posts": 100, "followers": 50000}, None, self.lib)
                 for _ in range(100)]
        tot, lo, hi = roi.combine(posts, "views", "m_views")
        self.assertLessEqual(lo, tot * 0.91)
        self.assertGreaterEqual(hi, tot * 1.09)

    def test_two_significant_figures(self):
        r = roi.public(roi.estimate("awareness", 0, ["Instagram"], "SA", mix={"micro": 3}))
        for f in r["figures"]:
            for x in f["range"]:
                self.assertEqual(float("%.2g" % x), x, f)

    def test_market_does_not_move_a_number(self):
        a = roi.public(roi.estimate("awareness", 50000, ["Instagram", "TikTok"], "SA", mix={"mid": 2, "micro": 6}))
        b = roi.public(roi.estimate("awareness", 50000, ["Instagram", "TikTok"], "EG", mix={"mid": 2, "micro": 6}))
        self.assertEqual(a["figures"], b["figures"])
        self.assertEqual(a["totals"], b["totals"])

    def test_trust_line(self):
        cs = [creator("A", 50000, doc={"median_views": 9000, "sample_posts": 100}), creator("B", 40000), creator("C", 60000)]
        r = roi.public(roi.estimate("awareness", 0, ["TikTok"], "SA", creators=cs))
        self.assertEqual(r["trust"]["line"], "Based on measured data for 1 of 3 creators.")
        self.assertEqual(roi.public(roi.estimate("awareness", 0, ["TikTok"], "SA", mix={"mid": 2}))["trust"]["measured"], 0)
        self.assertIn("Estimate, not a result", r["note"])

    def test_a_second_post_adds_less_than_a_new_creator(self):
        cs = [creator("A", 50000, doc={"median_views": 9000, "sample_posts": 100}), creator("B", 40000, doc={"median_views": 8000, "sample_posts": 100})]
        one = roi.estimate("awareness", 0, ["TikTok"], "SA", creators=cs)
        two = roi.estimate("awareness", 0, ["TikTok"], "SA", creators=cs, second_posts=["A"])
        gain = two["totals"]["views"] - one["totals"]["views"]
        self.assertAlmostEqual(gain, 9000 * 0.8, delta=2)


class NothingRemoved(Base):
    def test_no_cost_verdict_frequency_or_advice_fields(self):
        r = roi.full("awareness", 100000, ["Instagram"], "SA", mix={"micro": 2}, goals=["awareness"])
        txt = json.dumps(r).lower()
        for word in ("cpm", "cpe", "cpc", "frequency", "verdict", "creators_budget", "planning_price", "price"):
            self.assertNotIn(word, txt, word)
        for gone in ("cost", "verdict", "split", "sources", "_posts"):
            self.assertNotIn(gone, r)

    def test_old_saved_estimates_still_read(self):
        old = {"goal": "awareness", "figures": [{"key": "reach", "label": "Reach", "value": 1000, "range": [800, 1200], "sig": {"grade": "good"}},
                                                {"key": "cpm", "label": "CPM", "value": 80, "range": [70, 90]},
                                                {"key": "frequency", "label": "Frequency", "value": 2.0}],
               "cost": {"key": "cpm"}, "verdict": {"label": "Low"}, "advice": "x", "totals": {"views": 2000, "cpm": 80, "reach": 1000}}
        clean = roi.clean_result(old)
        self.assertEqual([f["key"] for f in clean["figures"]], ["reach"])
        self.assertNotIn("sig", clean["figures"][0])
        for k in ("cost", "verdict", "advice"):
            self.assertNotIn(k, clean)
        self.assertEqual(clean["totals"], {"views": 2000, "reach": 1000})


class Planner(Base):
    SUPPLY = {("TikTok", "nano"): 5, ("TikTok", "micro"): 5, ("TikTok", "mid"): 3, ("TikTok", "macro"): 1, ("TikTok", "mega"): 0,
              ("Instagram", "nano"): 5, ("Instagram", "micro"): 5, ("Instagram", "mid"): 3, ("Instagram", "macro"): 1, ("Instagram", "mega"): 0}

    def test_mix_stays_inside_the_creators_share_of_the_budget(self):
        share, prices = roi.settings()
        self.assertEqual((share, prices["micro"]), (0.6, 1300))
        mix = roi.plan_mix(["awareness"], 20000, ["TikTok"], self.SUPPLY, self.lib)
        cost = sum(prices[t] * n for m in mix.values() for t, n in m.items())
        self.assertLessEqual(cost, 20000 * share + 1e-6)
        self.assertGreater(cost, 20000 * share * 0.7)                         # and it does spend it

    def test_more_budget_never_gives_fewer_creators_or_less_reach(self):
        a = roi.plan(["awareness"], 30000, ["TikTok", "Instagram"], supply=self.SUPPLY)
        b = roi.plan(["awareness"], 90000, ["TikTok", "Instagram"], supply=self.SUPPLY)
        self.assertGreaterEqual(b["planned_creators"], a["planned_creators"])
        self.assertGreaterEqual(b["totals"]["views"], a["totals"]["views"])

    def test_supply_caps_the_mix(self):
        mix = roi.plan_mix(["awareness"], 1000000, ["TikTok"], {("TikTok", "micro"): 2, ("TikTok", "nano"): 1}, self.lib)
        self.assertEqual(mix, {"TikTok": {"micro": 2, "nano": 1}})

    def test_goal_changes_the_mix_inputs_and_all_goals_count(self):
        m1 = roi.plan_mix(["awareness"], 80000, ["TikTok"], self.SUPPLY, self.lib)
        self.assertTrue(m1)
        both = roi.plan(["awareness", "traffic"], 80000, ["TikTok"], supply=self.SUPPLY)
        self.assertEqual(both["goals"], ["awareness", "traffic"])
        self.assertIn("clicks", [f["key"] for f in both["figures"]])
        self.assertIn("views", [f["key"] for f in both["figures"]])

    def test_prices_are_internal_settings(self):
        roi.db.setting = lambda key, default=None: {"roi_creator_share": 0.5, "roi_planning_prices": {"micro": 2345}}.get(key, default)
        share, prices = roi.settings()
        self.assertEqual((share, prices["micro"], prices["nano"]), (0.5, 2345, 650))
        res = roi.public(roi.plan(["awareness"], 50000, ["TikTok"], supply=self.SUPPLY))
        self.assertNotIn("2345", json.dumps(res))

    def test_zero_budget_plans_nothing(self):
        self.assertEqual(roi.plan_mix(["awareness"], 0, ["TikTok"], self.SUPPLY, self.lib), {})


class Advice(Base):
    def selection(self, n, platform="TikTok", views=9000, score=50):
        return [creator("C%02d" % i, 30000 + i * 1000, platform, {"median_views": views - i * 100, "median_er_on_views": 3.0, "sample_posts": 100,
                                                                     "followers": 30000 + i * 1000}, score) for i in range(n)]

    def test_too_many_creators_are_offered_as_reserve_weakest_first(self):
        gl = ["awareness"]
        cs = self.selection(14)
        res = roi.estimate("awareness", 0, ["TikTok"], "SA", creators=cs)
        planned = {"planned_creators": 9, "mix": {"TikTok": {"micro": 9}}, "totals": {"views": res["totals"]["views"] * 0.9, "engagement": 1, "clicks": 1},
                   "platforms": ["TikTok"]}
        items = roi.advise(res, planned, gl, creators=cs)
        rs = [i for i in items if i["action"]["type"] == "remove"]
        self.assertEqual(len(rs), 1)
        self.assertEqual(len(rs[0]["action"]["codes"]), 5)
        self.assertIn("14 creators", rs[0]["text"])
        self.assertIn("about 9", rs[0]["text"])
        # the five weakest by views, never by price
        self.assertEqual(sorted(rs[0]["action"]["codes"]), sorted(c["code"] for c in cs[-5:]))

    def test_under_the_plan_adds_creators_second_posts_and_platforms_in_that_order_of_gain(self):
        gl = ["awareness"]
        cs = self.selection(3)
        res = roi.estimate("awareness", 0, ["TikTok"], "SA", creators=cs)
        planned = roi.plan(gl, 60000, ["TikTok", "Instagram"], supply={("TikTok", "micro"): 20, ("Instagram", "micro"): 20})
        cands = [{"code": "N%d" % i, "platform": "TikTok", "size": "micro", "followers": 40000, "score": 80 - i} for i in range(10)]
        cov = roi.coverage(res, planned, gl)
        self.assertLess(cov, 0.9)
        items = roi.advise(res, planned, gl, candidates=cands, creators=cs)
        self.assertLessEqual(len(items), 3)
        types = [i["action"]["type"] for i in items]
        self.assertIn("add", types)
        self.assertIn("second_post", types)
        self.assertIn("add_platform", types)
        add = next(i for i in items if i["action"]["type"] == "add")
        self.assertTrue(add["action"]["codes"][0].startswith("N0"))             # the best performer first
        self.assertIn("%d%% of the plan" % int(round(cov * 100)), add["text"])
        second = next(i for i in items if i["action"]["type"] == "second_post")
        self.assertEqual(second["action"]["codes"], ["C00", "C01"])
        self.assertEqual(next(i for i in items if i["action"]["type"] == "add_platform")["action"]["platform"], "Instagram")
        self.assertEqual([i["gain"] for i in items], sorted((i["gain"] for i in items), reverse=True))
        for i in items:
            self.assertNotRegex(i["text"].lower(), r"sar|price|cost|cheap|budget")

    def test_a_mix_input_gets_the_suggested_mix(self):
        res = roi.estimate("awareness", 0, ["TikTok"], "SA", mix={"micro": 1})
        planned = roi.plan(["awareness"], 60000, ["TikTok"], supply={("TikTok", "micro"): 20, ("TikTok", "mid"): 10})
        items = roi.advise(res, planned, ["awareness"], creators=None)
        self.assertEqual([i["action"]["type"] for i in items], ["use_mix"])
        self.assertEqual(items[0]["action"]["mix"], planned["mix"])

    def test_on_plan_gives_no_advice(self):
        cs = self.selection(6)
        res = roi.estimate("awareness", 0, ["TikTok"], "SA", creators=cs)
        planned = {"planned_creators": 6, "mix": {"TikTok": {"micro": 6}}, "totals": {"views": res["totals"]["views"] * 0.95, "engagement": 1, "clicks": 1},
                   "platforms": ["TikTok"]}
        self.assertEqual(roi.advise(res, planned, ["awareness"], creators=cs), [])


class VersusRanges(Base):
    def test_clean_result_keeps_ranges_for_the_comparison(self):
        res = {"figures": [{"key": "views", "range": [100, 200], "value": 150}, {"key": "interactions", "range": [10, 20], "value": 15}],
               "totals": {"views": 150, "engagement": 15, "reach": 90}}
        c = roi.clean_result(res)
        self.assertEqual({f["key"]: f["range"] for f in c["figures"]}, {"views": [100, 200], "interactions": [10, 20]})


if __name__ == "__main__":
    unittest.main()
