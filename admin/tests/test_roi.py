"""Unit tests for the pure parts of phase C + D: ROI grades and sizes, reading a budget
question typed in the chat, the occasions calendar and look-alike reasons. No database."""
import datetime
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import aimore
import occasions
import roi


class Grades(unittest.TestCase):
    def test_cost_against_ceilings(self):
        ceil = [70, 40]                                            # [acceptable, good] as in plans.LIBRARY
        self.assertEqual(roi._grade_cost(30, ceil), "good")
        self.assertEqual(roi._grade_cost(55, ceil), "moderate")
        self.assertEqual(roi._grade_cost(90, ceil), "low")
        self.assertIsNone(roi._grade_cost(None, ceil))

    def test_rate_against_range(self):
        self.assertEqual(roi._grade_rate(4.0, [2.5, 4.5]), "good")
        self.assertEqual(roi._grade_rate(3.0, [2.5, 4.5]), "moderate")
        self.assertEqual(roi._grade_rate(1.0, [2.5, 4.5]), "low")

    def test_words_match_the_campaign_report(self):
        self.assertEqual(set(roi.GRADE_LABEL), {"good", "moderate", "low"})

    def test_sizes(self):
        self.assertEqual([roi.tier_of(n) for n in (5000, 50000, 200000, 700000, 2000000)],
                         ["nano", "micro", "mid", "macro", "mega"])


class ChatBudget(unittest.TestCase):
    def test_reads_amount_goal_and_platform(self):
        cases = {"What can SAR 60,000 do on TikTok if we want clicks?": (60000, "traffic", ["TikTok"]),
                 "what can 80k SAR reach on instagram": (80000, "awareness", ["Instagram"]),
                 "budget of 50 thousand riyals for engagement": (50000, "engagement", ["Instagram", "TikTok"])}
        import plans
        plans.house_benchmarks = lambda: {}                       # no database in a unit test
        roi.db.setting = lambda key, default=None: default
        for text, (budget, goal, plats) in cases.items():
            r = roi.from_text(text)
            self.assertIsNotNone(r, text)
            self.assertEqual((r["budget"], r["goal"], r["platforms"]), (budget, goal, plats), text)

    def test_ignores_other_questions(self):
        for text in ("How much does a reel cost?", "Find me 5 creators in Riyadh", "SAR 200 for a coffee"):
            self.assertIsNone(roi.from_text(text), text)


class Calendar(unittest.TestCase):
    def test_upcoming_is_sorted_with_brief_dates(self):
        up = occasions.upcoming(today=datetime.date(2027, 1, 20), months=2)
        self.assertEqual([o["starts"] for o in up], sorted(o["starts"] for o in up))
        ram = [o for o in up if o["name"] == "Ramadan"][0]
        self.assertEqual(ram["dates"], "approximate (moon-sighted)")
        self.assertTrue(ram["brief_late"])                        # 8 weeks before 8 Feb has passed on 20 Jan
        self.assertTrue(all(o["kind"] != "congress" or "derma" in o["suits"] or "pharma" in o["suits"] or "auto" in o["suits"] for o in up))

    def test_sector_filter_keeps_all_sector_occasions(self):
        up = occasions.upcoming(today=datetime.date(2027, 1, 1), months=3, sector="auto")
        names = [o["name"] for o in up]
        self.assertIn("Automechanika Riyadh", names)
        self.assertIn("Ramadan", names)                           # "all" occasions suit everyone
        self.assertNotIn("World Cancer Day", names)


class Reasons(unittest.TestCase):
    def row(self, **k):
        base = {"code": "X", "name": "Seed", "tier": "Micro", "interest": "Skincare, Beauty", "city": "Riyadh", "platform": "Instagram"}
        base.update(k)
        return base

    def test_reason_uses_card_fields_only(self):
        why = aimore.reason(self.row(code="Y", name="Pick"), self.row())
        self.assertIn("based in Riyadh", why)
        self.assertIn("skincare", why.lower())
        self.assertTrue(why.endswith("."))
        self.assertNotIn("%", why)                                # never an analysis figure

    def test_doctors_are_named_as_such(self):
        why = aimore.reason(self.row(tier="HCP - Micro"), self.row(tier="HCP - Mid", name="Dr. Sami"))
        self.assertTrue(why.startswith("A healthcare professional like Dr. Sami"))


if __name__ == "__main__":
    unittest.main()
