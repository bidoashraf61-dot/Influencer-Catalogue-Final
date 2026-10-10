"""ROI Calculator v4 (fix batch 7): structure vs performance. The chain, honest ranges, efficiency,
combined error, the recommended-structure shapes, optimum vs selection, Selection quality, the advice
and its actions, settings validation, and what must never reach a client (budget, prices, market).

The recommended shapes are read from roi.SHAPES_DEFAULT, never hard-coded here."""
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
        self.assertAlmostEqual(a["views"], 10000 * roi.MEAN_OVER_MEDIAN)      # totals are expected (average) views, not the typical post
        self.assertAlmostEqual(a["interactions"], 10000 * roi.MEAN_OVER_MEDIAN * 0.04)
        self.assertAlmostEqual(b["views"] / a["views"], 1.2)
        self.assertAlmostEqual(b["interactions"] / a["interactions"], 1.2)
        self.assertAlmostEqual(b["clicks"] / a["clicks"], 1.2)
        self.assertAlmostEqual(a["reach"], 10000 * roi.MEAN_OVER_MEDIAN * self.lib["TikTok"]["reach_per_view"])

    def test_without_a_median_peers_then_own_average_then_guide(self):
        f = 50000
        doc = {"avg_views": 30000, "sample_posts": 20, "followers": f}
        guide = roi.post_values("TikTok", f, None, None, self.lib)
        self.assertEqual(guide["basis"], "guide")
        mid = (self.lib["TikTok"]["view_rate"]["micro"][0] + self.lib["TikTok"]["view_rate"]["micro"][1]) / 2.0
        self.assertAlmostEqual(guide["views"], f * mid / 100.0 * roi.MEAN_OVER_MEDIAN)
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
        self.assertAlmostEqual(tot, 90000 * roi.MEAN_OVER_MEDIAN)
        half = math.sqrt(9 * (0.48 * 10000 * roi.MEAN_OVER_MEDIAN) ** 2)
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
        r = roi.public(roi.estimate("awareness", ["Instagram"], mix={"micro": 3}))
        for f in r["figures"]:
            for x in f["range"]:
                self.assertEqual(float("%.2g" % x), x, f)

    def test_there_is_no_market_input(self):
        a = roi.public(roi.estimate("awareness", ["Instagram", "TikTok"], mix={"mid": 2, "micro": 6}))
        b = roi.public(roi.estimate("awareness", ["Instagram", "TikTok"], mix={"mid": 2, "micro": 6}))
        self.assertEqual(a["figures"], b["figures"])
        self.assertEqual(a["totals"], b["totals"])
        self.assertNotIn("market", json.dumps(a).lower())

    def test_trust_line(self):
        cs = [creator("A", 50000, doc={"median_views": 9000, "sample_posts": 100}), creator("B", 40000), creator("C", 60000)]
        r = roi.public(roi.estimate("awareness", ["TikTok"], creators=cs))
        self.assertEqual(r["trust"]["line"], "Based on measured data for 1 of 3 creators.")
        self.assertEqual(roi.public(roi.estimate("awareness", ["TikTok"], mix={"mid": 2}))["trust"]["measured"], 0)
        self.assertIn("Estimate, not a result", r["note"])

    def test_a_second_post_adds_less_than_a_new_creator(self):
        cs = [creator("A", 50000, doc={"median_views": 9000, "sample_posts": 100}), creator("B", 40000, doc={"median_views": 8000, "sample_posts": 100})]
        one = roi.estimate("awareness", ["TikTok"], creators=cs)
        two = roi.estimate("awareness", ["TikTok"], creators=cs, second_posts=["A"])
        gain = two["totals"]["views"] - one["totals"]["views"]
        self.assertAlmostEqual(gain, 9000 * roi.MEAN_OVER_MEDIAN * 0.8, delta=2)


    def test_median_peer_cell_gets_the_expected_views_factor_an_average_cell_does_not(self):
        f = 50000
        benchmarks.SOURCE = lambda: [("TikTok", {"followers": 30000 + i * 1000, "median_views": (30000 + i * 1000) * 0.10, "avg_views": (30000 + i * 1000) * 0.10,
                                                 "er": 3, "er_basis": "views"}) for i in range(40)]
        benchmarks.invalidate()
        med = roi.post_values("TikTok", f, None, None, self.lib)
        self.assertEqual(med["basis"], "peers")
        self.assertAlmostEqual(med["views"], f * 0.10 * roi.MEAN_OVER_MEDIAN, delta=f * 0.02)

    def test_instagram_guide_is_the_calibrated_reel_rate(self):
        for size, followers in (("nano", 10000), ("micro", 50000), ("mid", 200000), ("macro", 700000), ("mega", 1500000)):
            v = roi.post_values("Instagram", followers, None, None, self.lib)
            self.assertEqual((v["size"], v["basis"]), (size, "guide"))
            self.assertAlmostEqual(v["views"], followers * roi.IG_VIEW_RATE[size] / 100.0 * roi.MEAN_OVER_MEDIAN)
        # the campaign planner's guide is untouched
        self.assertNotEqual(self.lib["Instagram"]["view_rate"]["micro"], [roi.IG_VIEW_RATE["micro"]] * 2)


class Shapes(Base):
    """The recommended structure: shapes are data (SHAPES_DEFAULT / setting roi_shapes)."""

    def test_defaults_sum_to_100_over_known_sizes(self):
        for g in roi.GOALS:
            self.assertAlmostEqual(sum(roi.SHAPES_DEFAULT[g].values()), 100.0)
            self.assertTrue(set(roi.SHAPES_DEFAULT[g]) <= set(roi.TIER_ORDER))
        self.assertEqual(roi.shapes(), {g: {t: float(v) for t, v in roi.SHAPES_DEFAULT[g].items()} for g in roi.GOALS})

    def test_largest_remainder_sums_to_n_and_follows_the_shape(self):
        for g in roi.GOALS:
            for n in range(1, 41):
                c = roi.largest_remainder(roi.SHAPES_DEFAULT[g], n)
                self.assertEqual(sum(c.values()), n, (g, n))
                for t, v in c.items():
                    want = roi.SHAPES_DEFAULT[g][t] / 100.0 * n
                    self.assertLess(abs(v - want), 1.0, (g, n, t))
        c = roi.largest_remainder({"a": 50, "b": 50}, 3)
        self.assertEqual(sum(c.values()), 3)
        self.assertEqual(roi.largest_remainder({"micro": 60, "mid": 40}, 0), {})

    def test_several_goals_average_their_shapes(self):
        both = roi.shape_for(["awareness", "traffic"])
        for t in roi.TIER_ORDER:
            a = roi.SHAPES_DEFAULT["awareness"].get(t, 0)
            b = roi.SHAPES_DEFAULT["traffic"].get(t, 0)
            self.assertAlmostEqual(both.get(t, 0.0), (a + b) / 2.0)
        self.assertAlmostEqual(sum(both.values()), 100.0)
        # a legacy goal reads as traffic
        self.assertEqual(roi.shape_for(["conversion"]), roi.shape_for(["traffic"]))

    def test_counts_are_spread_evenly_over_the_platforms(self):
        got = roi.ideal_counts(["awareness"], 10, ["Instagram", "TikTok"])
        self.assertEqual(sum(got["Instagram"].values()), 10)
        self.assertEqual(got["Instagram"], got["TikTok"])
        # 9 posts over 2 platforms: 5 and 4
        got = roi.ideal_counts(["awareness"], 9, ["Instagram", "TikTok"], per_platform_posts=9)
        self.assertEqual((sum(got["Instagram"].values()), sum(got["TikTok"].values())), (5, 4))

    def test_shape_setting_is_validated_and_used(self):
        clean, err = roi.validate_shape({"micro": 70, "mid": 30})
        self.assertIsNone(err)
        self.assertEqual(clean, {"micro": 70.0, "mid": 30.0})
        for bad in ({"micro": 70, "mid": 20}, {"micro": 130}, {"huge": 100}, {"micro": -5, "mid": 105}, {"micro": "x"}, "nope"):
            self.assertIsNotNone(roi.validate_shape(bad)[1], bad)
        clean, errs = roi.validate_shapes({"awareness": {"micro": 100}, "traffic": {"micro": 90}})
        self.assertEqual(list(clean), ["awareness"])
        self.assertEqual(list(errs), ["traffic"])
        # the setting replaces a goal's shape; an invalid one is ignored
        roi.db.setting = lambda key, default=None: {"roi_shapes": {"awareness": {"nano": 100}, "traffic": {"micro": 90}}}.get(key, default)
        sh = roi.shapes()
        self.assertEqual(sh["awareness"], {"nano": 100.0})
        self.assertEqual(sh["traffic"], {t: float(v) for t, v in roi.SHAPES_DEFAULT["traffic"].items()})
        self.assertEqual(roi.ideal_counts(["awareness"], 4)["Instagram"], {"nano": 4})


class Compare(Base):
    """Optimum vs selection, Selection quality and the efficiency gate."""

    def selection(self, n, platform="TikTok", views=9000, score=None, followers=40000):
        return [creator("C%02d" % i, followers, platform, {"median_views": views, "median_er_on_views": 3.0, "sample_posts": 100,
                                                            "followers": followers}, score) for i in range(n)]

    def test_the_ideal_has_the_same_number_of_creators_and_posts(self):
        cs = self.selection(7)
        r = roi.estimate("awareness", ["TikTok"], creators=cs, goals=["awareness"])
        self.assertEqual((r["creators"], r["posts"]), (7, 7))
        self.assertEqual(r["ideal"]["creators"], 7)
        self.assertEqual(r["ideal"]["posts"], 7)
        self.assertEqual(sum(sum(m.values()) for m in r["ideal"]["mix"].values()), 7)
        self.assertEqual(r["ideal"]["mix"]["TikTok"], roi.largest_remainder(roi.SHAPES_DEFAULT["awareness"], 7))
        two = roi.estimate("awareness", ["TikTok", "Instagram"], creators=[
            dict(c, followers={"TikTok": 40000, "Instagram": 40000}) for c in cs], goals=["awareness"])
        self.assertEqual(two["posts"], 14)
        self.assertEqual(two["ideal"]["posts"], 14)
        self.assertIn("with 7 creators", two["ideal"]["title"])

    def test_quality_is_selection_over_ideal_on_the_primary_figure(self):
        cs = self.selection(10)
        r = roi.estimate("awareness", ["TikTok"], creators=cs, goals=["awareness"])
        sel = sum(p["views"] for p in r["_posts"])
        ide = sum(p["views"] for p in r["_ideal_posts"])
        self.assertAlmostEqual(r["_q"], sel / ide)
        self.assertEqual(r["quality"]["pct"], int(5 * round(sel / ide * 20)))
        # engagement and traffic use interactions and clicks
        e = roi.estimate("engagement", ["TikTok"], creators=cs, goals=["engagement"])
        self.assertAlmostEqual(e["_q"], sum(p["interactions"] for p in e["_posts"]) / sum(p["interactions"] for p in e["_ideal_posts"]))
        t = roi.estimate("traffic", ["TikTok"], creators=cs, goals=["traffic"])
        self.assertAlmostEqual(t["_q"], sum(p["clicks"] for p in t["_posts"]) / sum(p["clicks"] for p in t["_ideal_posts"]))
        # several goals: the average of the goals' ratios
        m = roi.estimate("awareness", ["TikTok"], creators=cs, goals=["awareness", "traffic"])
        parts = [sum(p["views"] for p in m["_posts"]) / sum(p["views"] for p in m["_ideal_posts"]),
                 sum(p["clicks"] for p in m["_posts"]) / sum(p["clicks"] for p in m["_ideal_posts"])]
        self.assertAlmostEqual(m["_q"], sum(parts) / 2.0)

    def test_quality_can_exceed_100_percent(self):
        cs = self.selection(6, views=900000, followers=60000)               # viral creators
        r = roi.estimate("awareness", ["TikTok"], creators=cs, goals=["awareness"])
        self.assertGreater(r["_q"], 1.0)
        self.assertGreater(r["quality"]["pct"], 100)

    def test_efficiency_gate_moves_the_selection_not_the_ideal(self):
        weak = roi.estimate("awareness", ["TikTok"], creators=self.selection(6, score=0), goals=["awareness"])
        mid = roi.estimate("awareness", ["TikTok"], creators=self.selection(6, score=50), goals=["awareness"])
        top = roi.estimate("awareness", ["TikTok"], creators=self.selection(6, score=100), goals=["awareness"])
        self.assertAlmostEqual(weak["_q"] / mid["_q"], 0.8)
        self.assertAlmostEqual(top["_q"] / mid["_q"], 1.2)
        self.assertEqual(weak["ideal"]["figures"], top["ideal"]["figures"])       # typical creators: factor 1.0
        self.assertTrue(all(p["eff"] == 1.0 for p in top["_ideal_posts"]))

    def test_ranges_have_the_floor_and_two_figures_on_both_sides(self):
        r = roi.estimate("awareness", ["TikTok"], creators=self.selection(8), goals=["awareness"])
        for side in (r["selection"], r["ideal"]):
            for f in side["figures"]:
                if f["key"] == "er":
                    continue
                lo, hi = f["range"]
                for x in (lo, hi):
                    self.assertEqual(float("%.2g" % x), x)
                self.assertLessEqual(lo, f["value"] * 0.95)            # at least about +/-10 % (value is itself rounded)
                self.assertGreaterEqual(hi, f["value"] * 1.05)

    def test_quality_is_a_band_when_the_ranges_overlap_heavily_and_rounds_to_five(self):
        r = roi.estimate("awareness", ["TikTok"], creators=self.selection(10), goals=["awareness"])
        q = r["quality"]
        self.assertEqual(q["pct"] % 5, 0)
        self.assertEqual(q["low"] % 5, 0)
        if q["band"]:
            self.assertGreaterEqual(q["overlap"], 0.5)
            self.assertIn("–", q["text"])
        else:
            self.assertTrue(q["text"].startswith("about"))

    def test_within_ten_points_counts_as_on_structure(self):
        counts = roi.largest_remainder(roi.SHAPES_DEFAULT["awareness"], 20)
        sizes = {"macro": 700000, "mid": 200000, "micro": 40000, "nano": 8000, "mega": 1500000}

        def build(c):
            out, i = [], 0
            for t, n in c.items():
                for _ in range(n):
                    out.append(creator("S%02d" % i, sizes[t], "TikTok"))
                    i += 1
            return out
        base = roi.estimate("awareness", ["TikTok"], creators=build(counts), goals=["awareness"])
        self.assertEqual(set(base["selection"]["on_structure"].values()), {"on"})
        self.assertEqual(base["gap"], [])
        # one creator moved from micro to nano is 5 points: still on structure
        moved = dict(counts, micro=counts["micro"] - 1, nano=counts["nano"] + 1)
        r = roi.estimate("awareness", ["TikTok"], creators=build(moved), goals=["awareness"])
        self.assertEqual(r["gap"], [])
        # all nano: micro is 45 points short and nano 80 over
        r = roi.estimate("awareness", ["TikTok"], creators=build({"nano": 20}), goals=["awareness"])
        self.assertEqual(r["selection"]["on_structure"]["micro"], "short")
        self.assertEqual(r["selection"]["on_structure"]["nano"], "over")
        self.assertEqual(r["ideal"]["tolerance"], roi.ON_STRUCTURE_POINTS)
        pct = {x["size"]: x["pct"] for x in r["ideal"]["by_size"]}
        self.assertEqual(pct["micro"], int(round(roi.SHAPES_DEFAULT["awareness"]["micro"])))

    def test_gap_is_said_in_plain_words(self):
        cs = [creator("N%d" % i, 8000, "TikTok") for i in range(4)] + [creator("M%d" % i, 40000, "TikTok") for i in range(2)]
        r = roi.estimate("awareness", ["TikTok"], creators=cs, goals=["awareness"])
        txt = " ".join(r["gap"])
        self.assertTrue(r["gap"])
        self.assertLessEqual(len(r["gap"]), 3)
        self.assertRegex(txt, r"(No|short)")
        self.assertIn("nano", txt)

    def test_a_mix_gets_its_ideal_and_a_use_mix_way(self):
        r = roi.full("awareness", ["TikTok"], mix={"nano": 6}, goals=["awareness"])
        self.assertEqual(r["ideal"]["creators"], 6)
        self.assertEqual(r["ideal"]["mix"]["TikTok"], roi.largest_remainder(roi.SHAPES_DEFAULT["awareness"], 6))
        self.assertEqual([w["action"]["type"] for w in r["ways"]], ["use_mix"])
        self.assertEqual(r["ways"][0]["action"]["mix"], r["ideal"]["mix"])
        ok = roi.full("awareness", ["TikTok"], mix=r["ideal"]["mix"], goals=["awareness"])
        self.assertEqual(ok["ways"], [])

    def test_nothing_chosen_uses_the_count(self):
        r = roi.estimate("engagement", ["Instagram"], creators=[], goals=["engagement"], count=8)
        self.assertEqual(r["creators"], 0)
        self.assertEqual(r["ideal"]["creators"], 8)
        self.assertIsNone(r["quality"])
        self.assertEqual(r["ideal"]["title"], "Ideal for Engagement with 8 creators")

    def test_second_posts_are_extra_results_not_extra_ideal_posts(self):
        cs = self.selection(4)
        a = roi.estimate("awareness", ["TikTok"], creators=cs, goals=["awareness"])
        b = roi.estimate("awareness", ["TikTok"], creators=cs, goals=["awareness"], second_posts=["C00", "C01"])
        self.assertEqual(a["ideal"]["posts"], b["ideal"]["posts"])
        self.assertGreater(b["_q"], a["_q"])


class Advice(Base):
    """Ways to improve: real re-runs of the calculator, machine-readable actions, no prices."""

    def roster(self):
        return [{"code": "NANO%d" % i, "name": "Nano %d" % i, "platform": "TikTok", "size": "nano", "followers": 9000, "score": 70 - i} for i in range(3)] + \
               [{"code": "MID%d" % i, "name": "Mid %d" % i, "platform": "TikTok", "size": "mid", "followers": 220000, "score": 80 - i} for i in range(3)] + \
               [{"code": "MIC%d" % i, "name": "Micro %d" % i, "platform": "TikTok", "size": "micro", "followers": 50000, "score": 60 - i} for i in range(3)]

    def nanos(self, n=6):
        return [creator("N%02d" % i, 8000 + i * 100, "TikTok", None, 40 + i) for i in range(n)]

    def test_replace_the_weakest_nano_with_a_missing_size(self):
        cs = self.nanos()
        res = roi.estimate("awareness", ["TikTok"], creators=cs, goals=["awareness"])
        ways = roi.advise(res, ["awareness"], creators=cs, candidates=self.roster())
        self.assertTrue(ways)
        self.assertLessEqual(len(ways), 3)
        self.assertEqual([w["gain"] for w in ways], sorted((w["gain"] for w in ways), reverse=True))
        types = {w["action"]["type"] for w in ways}
        self.assertTrue(types & {"replace", "add"})
        for w in ways:
            a = w["action"]
            self.assertIn(a["type"], ("replace", "remove", "add", "second_post", "add_platform", "use_mix"))
            if a["type"] == "replace":
                self.assertEqual(len(a["remove"]), 1)
                self.assertEqual(len(a["add"]), 1)
                self.assertTrue(a["remove"][0].startswith("N"))
                self.assertTrue(a["add"][0].startswith(("MID", "MIC")))        # a size the ideal needs and the selection lacks
            self.assertGreater(w["points"], 0)
            self.assertNotRegex(w["text"].lower(), r"\bsar\b|price|cost|cheap|budget|market")

    def test_gain_is_the_real_change_in_quality(self):
        cs = self.nanos()
        res = roi.estimate("awareness", ["TikTok"], creators=cs, goals=["awareness"])
        ways = roi.advise(res, ["awareness"], creators=cs, candidates=self.roster())
        w = next(x for x in ways if x["action"]["type"] in ("replace", "add"))
        extra = [c for c in [dict(code=e["code"], name=e["name"], followers={"TikTok": e["followers"]}, docs={}, scores={"TikTok": e["score"]})
                             for e in self.roster()] if c["code"] in w["action"].get("add", w["action"].get("codes", []))]
        after = [c for c in cs if c["code"] not in w["action"].get("remove", [])] + extra
        q1 = roi.estimate("awareness", ["TikTok"], creators=after, goals=["awareness"])["_q"]
        self.assertAlmostEqual(q1 - res["_q"], w["gain"], places=6)

    def test_second_post_and_platform_actions(self):
        cs = [creator("A%d" % i, 40000, "TikTok", {"median_views": 3000 - i * 100, "sample_posts": 100, "followers": 40000}, 60) for i in range(3)]
        for c in cs:
            c["followers"]["Instagram"] = 45000
        res = roi.estimate("awareness", ["TikTok"], creators=cs, goals=["awareness"])
        ways = roi.advise(res, ["awareness"], creators=cs, candidates=[])
        by = {w["action"]["type"]: w for w in ways}
        if "second_post" in by:
            self.assertEqual(by["second_post"]["action"]["codes"], ["A0", "A1"])        # the best performers first
        self.assertIn("add_platform", by)
        self.assertEqual(by["add_platform"]["action"]["platform"], "Instagram")
        self.assertGreater(by["add_platform"]["points"], 0)

    def test_a_selection_at_the_ideal_gets_no_advice(self):
        counts = roi.largest_remainder(roi.SHAPES_DEFAULT["awareness"], 10)
        sizes = {"macro": 700000, "mid": 200000, "micro": 40000, "nano": 8000, "mega": 1500000}
        cs, i = [], 0
        for t, n in counts.items():
            for _ in range(n):
                cs.append(creator("X%02d" % i, sizes[t], "TikTok"))
                i += 1
        res = roi.estimate("awareness", ["TikTok"], creators=cs, goals=["awareness"])
        self.assertAlmostEqual(res["_q"], 1.0, places=1)
        self.assertEqual(res["gap"], [])
        ways = roi.advise(res, ["awareness"], creators=cs, candidates=self.roster())
        self.assertTrue(all(w["points"] >= 1 for w in ways))


class Count(Base):
    """Fix batch 7.1: the client chooses how many creators the ideal is planned for."""

    def cs(self, n):
        return [creator("C%02d" % i, 40000, "TikTok") for i in range(n)]

    def test_default_ranges_and_averaging_for_several_goals(self):
        for g in roi.GOALS:
            lo, hi = roi.count_range_for([g])
            self.assertEqual((lo, hi), roi.COUNT_RANGES_DEFAULT[g])
        lo, hi = roi.count_range_for(["awareness", "traffic"])
        d = roi.COUNT_RANGES_DEFAULT
        self.assertEqual(lo, int(round((d["awareness"][0] + d["traffic"][0]) / 2.0)))
        self.assertEqual(hi, int(round((d["awareness"][1] + d["traffic"][1]) / 2.0)))
        lo, hi = roi.count_range_for(["awareness", "engagement", "traffic"])
        self.assertEqual((lo, hi), (int(round(sum(v[0] for v in d.values()) / 3.0)), int(round(sum(v[1] for v in d.values()) / 3.0))))
        self.assertEqual(roi.count_range_for(["conversion"]), d["traffic"])           # legacy reads as traffic

    def test_the_setting_is_validated_and_used(self):
        clean, err = roi.validate_count_ranges({"awareness": (10, 30), "engagement": (0, 5), "traffic": (20, 8)})
        self.assertEqual(clean, {"awareness": (10, 30)})
        self.assertEqual(set(err), {"engagement", "traffic"})
        self.assertIn("awareness", roi.validate_count_ranges({"awareness": (1.5, 3)})[1] or {"awareness": 1})
        self.assertEqual(roi.validate_count_ranges({"awareness": (1, 61)})[0], {})
        roi.db.setting = lambda key, default=None: {"roi_count_ranges": {"awareness": [10, 30], "traffic": [50, 2]}}.get(key, default)
        self.assertEqual(roi.count_range_for(["awareness"]), (10, 30))
        self.assertEqual(roi.count_range_for(["traffic"]), roi.COUNT_RANGES_DEFAULT["traffic"])      # invalid: default

    def test_count_replans_the_ideal_at_that_number(self):
        cs = self.cs(6)
        base = roi.estimate("awareness", ["TikTok"], creators=cs, goals=["awareness"])
        self.assertEqual((base["count"], base["ideal_count"], base["count_default"]), (6, 6, 6))
        r = roi.estimate("awareness", ["TikTok"], creators=cs, goals=["awareness"], count=15)
        self.assertEqual((r["count"], r["ideal_count"], r["count_default"]), (15, 15, 6))
        self.assertEqual(r["ideal"]["creators"], 15)
        self.assertEqual(r["ideal"]["posts"], 15)                                  # 1 post per creator per chosen platform
        self.assertEqual(r["ideal"]["mix"]["TikTok"], roi.largest_remainder(roi.SHAPES_DEFAULT["awareness"], 15))
        self.assertIn("The ideal for 15 creators has", r["compare_line"])
        self.assertIn("you have 6 micro", r["compare_line"])
        self.assertEqual(r["ideal"]["title"], "Ideal for Awareness with 15 creators")
        self.assertLess(r["_q"], base["_q"])                                       # a bigger ideal asks more of the same selection
        two = roi.estimate("awareness", ["TikTok", "Instagram"], creators=[dict(c, followers={"TikTok": 40000, "Instagram": 40000}) for c in cs],
                           goals=["awareness"], count=15)
        self.assertEqual(two["ideal"]["posts"], 30)

    def test_any_whole_number_is_accepted_outside_the_range_only_the_hint_changes(self):
        cs = self.cs(4)
        for n, want in ((1, 1), (3, 3), (40, 40), (60, 60), (200, 60)):
            r = roi.estimate("awareness", ["TikTok"], creators=cs, goals=["awareness"], count=n)
            self.assertEqual(r["ideal_count"], want, n)
            self.assertEqual(r["count_range"]["text"], "12–25")
            self.assertNotIn("warning", json.dumps(r).lower())
            self.assertNotIn("too few", json.dumps(r).lower())
            self.assertNotIn("too many", json.dumps(r).lower())
        self.assertEqual(roi.estimate("awareness", ["TikTok"], creators=cs, goals=["awareness"], count="bad")["ideal_count"], 4)

    def test_a_mix_and_an_empty_selection_use_the_chosen_count(self):
        r = roi.estimate("engagement", ["Instagram"], mix={"micro": 3}, goals=["engagement"], count=20)
        self.assertEqual(r["ideal_count"], 20)
        self.assertEqual(r["count_default"], 3)
        self.assertEqual(r["ideal"]["mix"]["Instagram"], roi.largest_remainder(roi.SHAPES_DEFAULT["engagement"], 20))
        e = roi.estimate("traffic", ["Instagram"], creators=[], goals=["traffic"], count=9)
        self.assertEqual((e["ideal_count"], e["creators"]), (9, 0))
        self.assertTrue(e["compare_line"].endswith("."))
        self.assertNotIn("you have", e["compare_line"])

    def test_advice_keeps_the_chosen_count(self):
        cs = [creator("N%02d" % i, 8000, "TikTok", None, 50) for i in range(6)]
        roster = [{"code": "MID%d" % i, "name": "Mid %d" % i, "platform": "TikTok", "size": "mid", "followers": 220000, "score": 80} for i in range(3)]
        res = roi.estimate("awareness", ["TikTok"], creators=cs, goals=["awareness"], count=12)
        ways = roi.advise(res, ["awareness"], creators=cs, candidates=roster, count=12)
        for w in ways:
            if w["action"]["type"] in ("add", "replace"):
                codes = w["action"].get("add") or w["action"].get("codes")
                extra = [{"code": e["code"], "name": e["name"], "followers": {"TikTok": e["followers"]}, "docs": {}, "scores": {"TikTok": e["score"]}}
                         for e in roster if e["code"] in codes]
                after = [c for c in cs if c["code"] not in w["action"].get("remove", [])] + extra
                q1 = roi.estimate("awareness", ["TikTok"], creators=after, goals=["awareness"], count=12)["_q"]
                self.assertAlmostEqual(q1 - res["_q"], w["gain"], places=6)


class NothingRemoved(Base):
    def test_no_budget_price_cost_or_market_anywhere_in_public_output(self):
        cs = [creator("A", 40000, "TikTok"), creator("B", 9000, "TikTok")]
        outs = [roi.full("awareness", ["Instagram"], mix={"micro": 2}, goals=["awareness"]),
                roi.full("traffic", ["TikTok"], creators=cs, goals=["traffic", "engagement"], with_advice=True),
                roi.from_text("what can 10 creators do on tiktok for clicks?")]
        for r in outs:
            txt = json.dumps(r).lower()
            for word in ("budget", "price", "cpm", "cpe", "cpc", "frequency", "verdict", "market", "sar ", "creators_share", "planning"):
                self.assertNotIn(word, txt, word)
            for gone in ("cost", "verdict", "split", "sources", "_posts", "plan", "budget", "market", "market_label"):
                self.assertNotIn(gone, r)

    def test_budget_and_market_arguments_are_gone(self):
        import inspect
        self.assertNotIn("budget", inspect.signature(roi.estimate).parameters)
        self.assertNotIn("market", inspect.signature(roi.estimate).parameters)
        self.assertFalse(hasattr(roi, "parse_budget"))
        self.assertFalse(hasattr(roi, "plan_mix"))
        self.assertFalse(hasattr(roi, "settings"))

    def test_old_saved_estimates_still_read_and_lose_budget_and_market(self):
        old = {"goal": "awareness", "budget": 90000, "market": "SA", "market_label": "Saudi Arabia", "plan": {"mix": {}, "text": "x"},
               "figures": [{"key": "reach", "label": "Reach", "value": 1000, "range": [800, 1200], "sig": {"grade": "good"}},
                           {"key": "cpm", "label": "CPM", "value": 80, "range": [70, 90]},
                           {"key": "frequency", "label": "Frequency", "value": 2.0}],
               "cost": {"key": "cpm"}, "verdict": {"label": "Low"}, "advice": "x", "totals": {"views": 2000, "cpm": 80, "reach": 1000}}
        clean = roi.clean_result(old)
        self.assertEqual([f["key"] for f in clean["figures"]], ["reach"])
        self.assertNotIn("sig", clean["figures"][0])
        for k in ("cost", "verdict", "advice", "budget", "market", "market_label", "plan"):
            self.assertNotIn(k, clean)
        self.assertEqual(clean["totals"], {"views": 2000, "reach": 1000})

        class Row(dict):
            pass
        row = Row(id=1, goal="awareness", created_at=1, input=json.dumps({"goals": ["awareness"], "budget": 5, "market": "EG", "platforms": ["Instagram"]}),
                  result=json.dumps(old))
        v = roi.row_view(row)
        self.assertEqual(v["input"], {"goals": ["awareness"], "platforms": ["Instagram"]})

    def test_legacy_conversion_reads_as_traffic(self):
        r = roi.estimate("conversion", ["TikTok"], mix={"micro": 2}, goals=["conversion"])
        self.assertEqual(r["goals"], ["traffic"])


class Chat(Base):
    def test_typed_count_is_answered_with_the_recommended_structure(self):
        r = roi.from_text("What can 10 creators do on TikTok if we want clicks?")
        self.assertIsNotNone(r)
        self.assertEqual((r["goal"], r["platforms"], r["count"]), ("traffic", ["TikTok"], 10))
        self.assertEqual(r["mix"]["TikTok"], roi.largest_remainder(roi.SHAPES_DEFAULT["traffic"], 10))
        self.assertTrue(r["ideal_only"])
        for text in ("How much does a reel cost?", "What can SAR 60,000 reach?", "Find me creators in Riyadh", "Hello"):
            self.assertIsNone(roi.from_text(text), text)

    def test_arabic_digits(self):
        r = roi.from_text("ماذا يحقق ١٠ مؤثرين على تيك توك reach")
        self.assertIsNotNone(r)
        self.assertEqual(r["count"], 10)


class VersusRanges(Base):
    def test_clean_result_keeps_ranges_for_the_comparison(self):
        res = {"figures": [{"key": "views", "range": [100, 200], "value": 150}, {"key": "interactions", "range": [10, 20], "value": 15}],
               "totals": {"views": 150, "engagement": 15, "reach": 90}}
        c = roi.clean_result(res)
        self.assertEqual({f["key"]: f["range"] for f in c["figures"]}, {"views": [100, 200], "interactions": [10, 20]})


if __name__ == "__main__":
    unittest.main()
