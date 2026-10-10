"""Unit tests for fix batch 5, item 44(b): the countries, the gender and the age groups of the
AI shortlist brief take several answers, exactly as the goal does. Budget, the number of
creators and the timing stay single choice. Legacy briefs saved with one value still read.

    python3 admin/tests/test_matcher_multi.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fit  # noqa: E402
import matcher  # noqa: E402

BASE = {"goal": "awareness", "platforms": ["Instagram"], "category": ["beauty"]}


def clean(**extra):
    answers, missing = matcher.clean_answers(dict(BASE, **extra))
    return answers, missing


class Multi(unittest.TestCase):
    def test_which_questions_take_several(self):
        by = {q["id"]: q for q in matcher.public_questions()}
        for qid in ("goal", "market", "gender", "age"):
            self.assertTrue(by[qid].get("multi_ok"), qid)
        for qid in ("budget", "count", "timing"):
            self.assertFalse(by[qid].get("multi_ok"), qid)
            self.assertEqual(by[qid]["type"], "one", qid)

    def test_countries_kept_as_a_list(self):
        a, missing = clean(market=["SA", "AE"])
        self.assertEqual((a["market"], missing), (["SA", "AE"], []))
        self.assertEqual(matcher.to_brief(a)["target"]["country"], "SA|AE")
        a, _ = clean(market=["AE"])
        self.assertEqual(a["market"], "AE")                       # one pick stays a plain value
        a, _ = clean(market="EG")                                  # legacy: a single string
        self.assertEqual(a["market"], "EG")
        self.assertEqual(matcher.to_brief(a)["target"]["country"], "EG")
        a, missing = clean(market=["XX"])
        self.assertIn("market", missing)

    def test_countries_are_capped_and_cleaned(self):
        a, _ = clean(market=["SA", "AE", "EG", "KW", "QA", "SA", "nonsense"])
        self.assertEqual(a["market"], ["SA", "AE", "EG", "KW"])

    def test_age_groups(self):
        a, _ = clean(market="SA", age=["18-24", "25-34"])
        self.assertEqual(a["age"], ["18-24", "25-34"])
        self.assertEqual(matcher.to_brief(a)["target"]["age"], "18-24|25-34")
        a, _ = clean(market="SA", age="25-34")                     # legacy
        self.assertEqual(matcher.to_brief(a)["target"]["age"], "25-34")
        a, _ = clean(market="SA", age=["Any", "18-24"])           # "All ages" wins over a band
        self.assertEqual(a["age"], "Any")
        self.assertEqual(matcher.to_brief(a)["target"]["age"], "Any")
        self.assertEqual(matcher.to_brief(clean(market="SA")[0])["target"]["age"], "Any")

    def test_women_and_men_together_are_everyone(self):
        a, _ = clean(market="SA", gender=["Women", "Men"])
        self.assertEqual(a["gender"], "Any")
        self.assertEqual(matcher.to_brief(a)["target"]["gender"], "Any")
        a, _ = clean(market="SA", gender=["Women"])
        self.assertEqual(matcher.to_brief(a)["target"]["gender"], "Women")
        a, _ = clean(market="SA", gender="Men")
        self.assertEqual(matcher.to_brief(a)["target"]["gender"], "Men")
        self.assertEqual(fit.one_gender("Women|Men"), "Any")

    def test_budget_count_timing_do_not_take_lists(self):
        a, _ = clean(market="SA", budget=["150", "400"], count=["5", "8"], timing=["asap", "later"])
        for k in ("budget", "count", "timing"):
            self.assertNotIn(k, a)
        a, _ = clean(market="SA", budget="150", count="8", timing="asap")
        self.assertEqual((a["budget"], a["count"], a["timing"]), ("150", "8", "asap"))

    def test_other_beside_options(self):
        a, _ = clean(market=["SA", "other:Kuwait"])
        self.assertEqual(matcher.to_brief(a)["target"]["country"], "SA|KW")
        a, _ = clean(market="SA", age=["25-34", "other:about 40"])
        self.assertEqual(matcher.to_brief(a)["target"]["age"], "25-34|35-44")

    def test_summary_reads_naturally(self):
        a, _ = clean(market=["SA", "AE"])
        self.assertIn("for Saudi Arabia and UAE", matcher.describe(a))
        a, _ = clean(market=["SA", "AE", "EG"])
        self.assertIn("for Saudi Arabia, UAE and Egypt", matcher.describe(a))
        a, _ = clean(market="SA")
        self.assertIn("for Saudi Arabia", matcher.describe(a))

    def test_roi_seed_reads_the_brief(self):
        a, _ = clean(market=["KW", "AE"], goal=["engagement", "traffic"], platforms=["TikTok"], budget="150")
        self.assertEqual(matcher.roi_seed(a), {"goal": "engagement", "platforms": ["TikTok"], "market": "AE",
                                               "platforms_from_brief": True, "budget": 150000})
        a, _ = clean(market="SA", goal="conversion", budget="open")
        seed = matcher.roi_seed(a)
        self.assertEqual((seed["goal"], seed["market"]), ("traffic", "SA"))
        self.assertNotIn("budget", seed)
        a, _ = clean(market="SA", goal="balanced", platforms=["any"], budget="other:120k")
        seed = matcher.roi_seed(a)
        self.assertEqual((seed["goal"], seed["budget"], seed["platforms"]), ("awareness", 120000, ["Instagram", "TikTok"]))
        self.assertEqual(matcher.timing_market(["AE", "SA"]), "SA")
        self.assertEqual(matcher.timing_market(["AE", "EG"]), "AE")
        self.assertEqual(matcher.timing_market("EG"), "EG")


class Scoring(unittest.TestCase):
    DOC = {"followers": 60000, "er": 4.4, "avg_views": 9000,
           "audience": {"countries": [{"code": "SA", "pct": 40}, {"code": "AE", "pct": 30}, {"code": "EG", "pct": 10}],
                        "gender": {"female": 66, "male": 34},
                        "ages": [{"name": "18-24", "pct": 30}, {"name": "25-34", "pct": 35}, {"name": "35-44", "pct": 15}]}}

    def part(self, **target):
        r = fit.score(self.DOC, "Instagram", 60000, objective="Awareness", target=dict({"country": "SA"}, **target))
        return next(p for p in r["parts"] if p["key"] == "market")["s"], r

    def test_audience_share_is_summed_across_countries(self):
        sa, _ = self.part(country="SA")
        both, r = self.part(country="SA|AE")
        self.assertAlmostEqual(sa, 40 / 60.0, places=2)
        self.assertEqual(both, 1.0)                               # 70% of the audience is in KSA + UAE
        self.assertIn("70%", " ".join(r["checks"][0]["text"].split()))
        self.assertIn("Saudi Arabia and UAE", r["checks"][0]["text"])
        eg, _ = self.part(country="EG")
        self.assertLess(eg, sa)

    def test_audience_share_is_summed_across_age_bands(self):
        one, _ = self.part(country="SA", age="25-34")
        two, r = self.part(country="SA", age="18-24|25-34")
        self.assertGreater(two, one)
        age = next(c for c in r["checks"] if c["label"] == "Age")
        self.assertIn("65%", age["text"])
        self.assertIn("18-24 and 25-34", age["text"])
        self.assertEqual(age["level"], "ok")

    def test_age_bands_are_counted_once(self):
        # a report band that overlaps both asked-for bands is not added twice
        ages = [{"name": "18-34", "pct": 60}, {"name": "35-44", "pct": 20}]
        self.assertEqual(fit._age_share(ages, "18-24|25-34"), 60)
        self.assertEqual(fit._age_share(ages, "18-24"), 60)
        self.assertEqual(fit._age_share(ages, "Any"), None)

    def test_a_target_with_one_value_scores_as_before(self):
        a = fit.score(self.DOC, "Instagram", 60000, objective="Awareness", target={"country": "SA", "gender": "Women", "age": "25-34"})
        b = fit.score(self.DOC, "Instagram", 60000, objective="Awareness", target={"country": "SA", "gender": "Women", "age": "25-34"})
        self.assertEqual(a["score"], b["score"])
        self.assertIsNotNone(a["score"])

    def test_place_mark_takes_any_of_the_countries(self):
        creator = {"city": "Dubai", "nationality": "UAE"}
        self.assertEqual(fit._place_mark(creator, "SA")[0], 0.2)
        self.assertEqual(fit._place_mark(creator, "SA|AE")[0], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
