import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import matcher

BASE = {"goal": "awareness", "platforms": ["Instagram"], "market": "SA", "category": ["beauty"]}


class Other(unittest.TestCase):
    """The "Other" answer on the brief questions: kept, read into the brief, shown as typed."""

    def brief(self, **extra):
        answers, missing = matcher.clean_answers(dict(BASE, **extra))
        self.assertEqual(missing, [])
        return answers, matcher.to_brief(answers)

    def test_every_option_question_offers_other(self):
        for q in matcher.public_questions():
            self.assertEqual(q["other"], q["type"] != "text", q["id"])

    def test_typed_count_sets_the_shortlist_size(self):
        answers, b = self.brief(count="other:40 creators")
        self.assertEqual(answers["count"], "other:40 creators")
        self.assertEqual(b["count"], 40)
        self.assertIn("How many creators: 40 creators", b["notes"])
        self.assertTrue(matcher.describe(answers).endswith("40 creators"))

    def test_count_is_clamped(self):
        self.assertEqual(self.brief(count="other:500")[1]["count"], 50)

    def test_typed_budget_sets_the_cap(self):
        self.assertEqual(self.brief(budget="other:120k")[1]["budget_max"], 120000)
        self.assertEqual(self.brief(budget="other:90,000")[1]["budget_max"], 90000)
        self.assertEqual(self.brief(budget="other:250")[1]["budget_max"], 250000)

    def test_other_satisfies_a_required_question(self):
        answers, missing = matcher.clean_answers(dict(BASE, goal="other:app downloads"))
        self.assertEqual(missing, [])
        self.assertEqual(matcher.to_brief(answers)["objective"], "Traffic")      # sales and downloads read as Traffic

    def test_many_keeps_options_and_one_other(self):
        answers, b = self.brief(platforms=["Instagram", "other:LinkedIn", "other:X"])
        self.assertEqual(answers["platforms"], ["Instagram", "other:LinkedIn"])
        self.assertEqual(b["platforms"], ["Instagram"])
        self.assertIn("LinkedIn", matcher.describe(answers))
        self.assertNotIn("other:", matcher.describe(answers))

    def test_empty_or_unknown_values_dropped(self):
        answers, _ = matcher.clean_answers(dict(BASE, count="other:   ", timing="soon"))
        self.assertNotIn("count", answers)
        self.assertNotIn("timing", answers)
        self.assertLessEqual(len(matcher.clean_answers(dict(BASE, goal="other:" + "x" * 300))[0]["goal"]), 6 + matcher.OTHER_MAX)

    def test_plain_options_unchanged(self):
        _, b = self.brief(count="15", budget="150")
        self.assertEqual((b["count"], b["budget_max"], b["notes"]), (15, 150000, ""))


class Goals(unittest.TestCase):
    """Fix batch 4, item 28: the AI shortlist goals match the ROI Calculator, several at once."""

    def test_goal_options(self):
        q = next(q for q in matcher.public_questions() if q["id"] == "goal")
        self.assertEqual([(o["value"], o["label"]) for o in q["options"]],
                         [("awareness", "Awareness"), ("engagement", "Engagement"), ("traffic", "Traffic")])
        self.assertTrue(q["multi_ok"])
        self.assertTrue(q["other"])
        self.assertNotIn("legacy", q)

    def test_several_goals_are_stored_and_blended(self):
        answers, missing = matcher.clean_answers(dict(BASE, goal=["awareness", "traffic"]))
        self.assertEqual((missing, answers["goal"]), ([], ["awareness", "traffic"]))
        self.assertEqual(matcher.to_brief(answers)["objective"], "Awareness+Traffic")
        self.assertEqual(matcher.describe(answers).split(";")[0], "Awareness and traffic")
        w = matcher.fit.blend(matcher.fit.WEIGHTS_BASIC, "Awareness+Traffic")
        self.assertAlmostEqual(w["views"], (3.0 + 2.0) / 2)

    def test_conversion_is_withdrawn_and_old_values_still_read(self):
        # Fix batch 6 (owner, 2026-10-10): Awareness, Engagement and Traffic are the only campaign types
        self.assertEqual(set(matcher.fit.WEIGHTS_BASIC), {"Awareness", "Engagement", "Traffic"})
        self.assertNotIn("Conversion", matcher.fit.OBJECTIVES)
        # a stored Conversion (alone or blended) reads as Traffic; Balanced as an equal blend of the three
        a, _ = matcher.clean_answers(dict(BASE, goal="conversion"))
        self.assertEqual((a["goal"], matcher.to_brief(a)["objective"]), ("traffic", "Traffic"))
        a, _ = matcher.clean_answers(dict(BASE, goal=["awareness", "conversion"]))
        self.assertEqual(a["goal"], ["awareness", "traffic"])
        fit = matcher.fit
        self.assertTrue(fit.known_objective("Conversion"))
        self.assertEqual(fit.parts_of("Awareness+Conversion"), ["Awareness", "Traffic"])
        self.assertEqual(fit.canonical("Traffic+Conversion"), "Traffic")
        eq = fit.blend(fit.WEIGHTS_BASIC, "Balanced")
        for k in eq:
            self.assertAlmostEqual(eq[k], sum(fit.WEIGHTS_BASIC[g][k] for g in fit.CAMPAIGN_TYPES) / 3.0)
        self.assertEqual(fit.blend(fit.WEIGHTS_BASIC, "Conversion"), fit.WEIGHTS_BASIC["Traffic"])
        old, _ = matcher.clean_answers(dict(BASE, goal="balanced"))
        self.assertEqual((old["goal"], matcher.to_brief(old)["objective"]), ("balanced", "Balanced"))
        self.assertEqual(matcher.answer_label("goal", "balanced"), "Balanced")

    def test_scoring_has_four_factors_and_no_link_route(self):
        doc = {"followers": 120000, "er": 4.0, "avg_views": 30000, "basic": True}
        for plat in ("Snapchat", "TikTok", "Instagram"):
            r = matcher.fit.score_core(dict(doc), plat, objective="Traffic")
            self.assertTrue({p["key"] for p in r["parts"]} <= {"engagement", "views", "consistency", "interest"}, plat)
        self.assertFalse(hasattr(matcher.fit, "LINK_ROUTE"))

    def test_other_beside_listed_goals_is_kept(self):
        answers, _ = matcher.clean_answers(dict(BASE, goal=["engagement", "other:app installs"]))
        self.assertEqual(answers["goal"], ["engagement", "other:app installs"])
        b = matcher.to_brief(answers)
        self.assertTrue(b["objective"].startswith("Engagement"))
        self.assertIn("app installs", b["notes"])

    def test_typed_words_pick_traffic(self):
        self.assertEqual(matcher.guess("we want clicks to our website from riyadh")[0].get("goal"), "traffic")
        self.assertEqual(matcher.guess("drive sales of our new cream")[0].get("goal"), "traffic")


if __name__ == "__main__":
    unittest.main()
