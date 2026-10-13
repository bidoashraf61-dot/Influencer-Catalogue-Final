"""The refined campaign brief (owner-approved 2026-10-13): the questions, what the brief keeps, and the
client's hard limits on the shortlist (fake-follower share, minimum engagement, creator size).

    python3 admin/tests/test_refined_brief.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import matcher  # noqa: E402

FULL = {"goal": ["awareness", "traffic"], "platforms": ["Instagram"], "market": ["SA", "AE"],
        "category": ["skincare", "beauty"], "creator_size": ["micro", "mid"], "count": "8",
        "max_fake": "30", "min_engagement": "above_benchmark", "timing": "month", "deliverable": ["reels"]}


class Questions(unittest.TestCase):
    def test_approved_list(self):
        ids = [q["id"] for q in matcher.public_questions()]
        self.assertEqual(ids, ["goal", "platforms", "market", "gender", "age", "category", "creator_size",
                               "count", "deliverable", "max_fake", "min_engagement", "timing", "notes"])
        self.assertNotIn("budget", ids)

    def test_new_questions_are_offered_as_options(self):
        by = {q["id"]: q for q in matcher.public_questions()}
        self.assertEqual([o["value"] for o in by["creator_size"]["options"]], ["nano", "micro", "mid", "macro", "mega"])
        self.assertEqual([o["value"] for o in by["max_fake"]["options"]], ["15", "30", "50", "none"])
        self.assertEqual([o["value"] for o in by["min_engagement"]["options"]], ["none", "above_benchmark", "top25"])

    def test_old_category_value_still_stored(self):
        self.assertEqual(matcher.answer_label("category", "beauty"), "Makeup")


class Brief(unittest.TestCase):
    def test_full_answers_reach_the_brief(self):
        b = matcher.to_brief(FULL)
        self.assertEqual(b["size"], ["micro", "mid"])
        self.assertEqual(b["max_fake"], 30)
        self.assertEqual(b["min_engagement"], "above_benchmark")
        self.assertIsNone(b["budget_max"])

    def test_no_limits_means_none(self):
        b = matcher.to_brief({"goal": "awareness", "platforms": ["Instagram"], "market": "SA", "category": ["fashion"],
                              "max_fake": "none", "min_engagement": "none"})
        self.assertIsNone(b["max_fake"])
        self.assertIsNone(b["min_engagement"])
        self.assertEqual(b["size"], [])

    def test_old_brief_with_budget_still_reads(self):
        self.assertEqual(matcher.answer_label("budget", "150"), "50,000 – 150,000")


class Limits(unittest.TestCase):
    def items(self):
        return [
            {"code": "A", "platform": "Instagram", "followers": 50000},   # fake 60%: removed by a 30% limit
            {"code": "B", "platform": "Instagram", "followers": 50000},   # fake 10%: kept
            {"code": "C", "platform": "Instagram", "followers": 50000},   # no fake figure: kept, flagged
        ]

    def docs(self, rows):
        return lambda codes: {c: {"Instagram": {"data": rows.get(c, {})}} for c in codes}

    def test_fake_share_limit(self):
        orig = matcher.db.analyses_for
        try:
            matcher.db.analyses_for = self.docs({"A": {"fake_followers_pct": 60, "er": 5},
                                                 "B": {"fake_followers_pct": 10, "er": 5},
                                                 "C": {"er": 5}})
            kept = matcher._client_limits({"max_fake": 30, "min_engagement": None}, self.items())
            self.assertEqual([i["code"] for i in kept], ["B", "C"])
            self.assertIn("fake share not known", [i for i in kept if i["code"] == "C"][0]["watchouts"])
        finally:
            matcher.db.analyses_for = orig

    def test_top25_keeps_best_quarter(self):
        orig = matcher.db.analyses_for
        try:
            rows = {c: {"er": e} for c, e in zip("ABCD", [1, 2, 3, 10])}
            matcher.db.analyses_for = self.docs(rows)
            items = [{"code": c, "platform": "Instagram", "followers": 50000} for c in "ABCD"]
            kept = matcher._client_limits({"max_fake": None, "min_engagement": "top25"}, items)
            self.assertEqual([i["code"] for i in kept], ["D"])
        finally:
            matcher.db.analyses_for = orig

    def test_no_limits_changes_nothing(self):
        items = self.items()
        self.assertIs(matcher._client_limits({"max_fake": None, "min_engagement": None}, items), items)


if __name__ == "__main__":
    unittest.main()
