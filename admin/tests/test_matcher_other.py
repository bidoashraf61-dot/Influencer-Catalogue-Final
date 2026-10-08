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
        self.assertEqual(matcher.to_brief(answers)["objective"], "Conversion")

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


if __name__ == "__main__":
    unittest.main()
