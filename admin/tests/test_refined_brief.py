"""The refined campaign brief (owner-approved 2026-10-13): the questions, what the brief keeps, and the
client's limits (since item 282 the fake-follower share ranks and minimum engagement is gone; creator size removes).

    python3 admin/tests/test_refined_brief.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import matcher  # noqa: E402

FULL = {"goal": ["awareness", "traffic"], "platforms": ["Instagram"], "market": ["SA", "AE"],
        "category": ["skincare", "beauty"], "creator_size": ["micro", "mid"], "count": "8",
        "max_fake": "30", "timing": "month", "deliverable": ["reels"]}


class Questions(unittest.TestCase):
    def test_approved_list(self):
        ids = [q["id"] for q in matcher.public_questions()]
        self.assertEqual(ids, ["goal", "platforms", "market", "gender", "age", "category", "budget", "mix",
                               "creator_size", "count", "deliverable", "max_fake", "timing", "notes"])
        self.assertNotIn("min_engagement", ids)          # item 282

    def test_new_questions_are_offered_as_options(self):
        by = {q["id"]: q for q in matcher.public_questions()}
        self.assertEqual([o["value"] for o in by["creator_size"]["options"]], ["nano", "micro", "mid", "macro", "mega"])
        self.assertEqual([o["value"] for o in by["max_fake"]["options"]], ["15", "30", "50", "none"])

    def test_old_category_value_still_stored(self):
        self.assertEqual(matcher.answer_label("category", "beauty"), "Beauty and makeup")


class Brief(unittest.TestCase):
    def test_full_answers_reach_the_brief(self):
        b = matcher.to_brief(FULL)
        self.assertEqual(b["size"], ["micro", "mid"])
        self.assertEqual(b["max_fake"], 30)
        self.assertNotIn("min_engagement", b)
        self.assertEqual(b["target"]["power"]["max_fake"], 30)      # item 282: the limit ranks, through the match
        self.assertIsNone(b["budget_max"])

    def test_no_limits_means_none(self):
        b = matcher.to_brief({"goal": "awareness", "platforms": ["Instagram"], "market": "SA", "category": ["fashion"],
                              "max_fake": "none"})
        self.assertIsNone(b["max_fake"])
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
            kept = matcher._client_limits({"max_fake": 30}, self.items())
            self.assertEqual([i["code"] for i in kept], ["A", "B", "C"])       # item 282: nobody removed
            self.assertEqual([i["fake_pct"] for i in kept], [60, 10, None])
        finally:
            matcher.db.analyses_for = orig

    def test_no_limits_changes_nothing(self):
        items = self.items()
        self.assertIs(matcher._client_limits({"max_fake": None}, items), items)


if __name__ == "__main__":
    unittest.main()
