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


class Sizes(unittest.TestCase):
    def test_sizes(self):
        self.assertEqual([roi.tier_of(n) for n in (5000, 19999, 20000, 50000, 100000, 200000, 500000, 700000, 1000000, 2000000)],
                         ["nano", "nano", "micro", "micro", "mid", "mid", "macro", "macro", "mega", "mega"])


def _bare():
    import plans
    plans.house_benchmarks = lambda: {}
    roi.db.setting = lambda key, default=None: default
    roi.benchmarks.SOURCE = lambda: []
    roi.benchmarks.invalidate()


class ChatBudget(unittest.TestCase):
    def test_reads_amount_goal_and_platform(self):
        cases = {"What can SAR 60,000 do on TikTok if we want clicks?": (60000, "traffic", ["TikTok"]),
                 "what can 80k SAR reach on instagram": (80000, "awareness", ["Instagram"]),
                 "budget of 50 thousand riyals for engagement": (50000, "engagement", ["Instagram", "TikTok"])}
        _bare()
        for text, (budget, goal, plats) in cases.items():
            r = roi.from_text(text)
            self.assertIsNotNone(r, text)
            self.assertEqual((r["budget"], r["goal"], r["platforms"]), (budget, goal, plats), text)
            self.assertNotIn("_posts", r)

    def test_ignores_other_questions(self):
        for text in ("How much does a reel cost?", "Find me 5 creators in Riyadh", "SAR 200 for a coffee"):
            self.assertIsNone(roi.from_text(text), text)


class ArabicDigits(unittest.TestCase):
    """Fix batch 4, item 24: a budget typed with Arabic-Indic or Persian digits."""
    def test_parse_budget(self):
        cases = {"١٢٠٠٠٠": 120000, "١٢٠٬٠٠٠": 120000, "۱۲۰,۰۰۰": 120000, "120,000": 120000, "12 000": 12000,
                 "٧٥٠٠٠٫٥": 75000.5, 90000: 90000, "": 0, None: 0, "abc": 0, "-5": 0, "9" * 12: 1e9}
        for raw, want in cases.items():
            self.assertEqual(roi.parse_budget(raw), want, raw)

    def test_ascii_digits_leaves_other_text(self):
        self.assertEqual(roi.ascii_digits("SAR ٦٠٬٠٠٠ on TikTok"), "SAR 60,000 on TikTok")

    def test_estimate_and_chat_read_arabic_digits(self):
        _bare()
        a = roi.estimate("awareness", "١٢٠٬٠٠٠", ["Instagram"], "SA", mix={"micro": 4})
        b = roi.estimate("awareness", 120000, ["Instagram"], "SA", mix={"micro": 4})
        self.assertEqual(a["budget"], 120000)
        self.assertEqual(a["figures"], b["figures"])
        r = roi.from_text("وش ممكن توصل ميزانية ٦٠٬٠٠٠ ريال على تيك توك")
        self.assertIsNotNone(r)
        self.assertEqual(r["budget"], 60000)


class Ranges(unittest.TestCase):
    """Ranges shown, nothing about cost, no advice or sources in the estimate itself."""
    def test_sig2_rounds_down_and_up(self):
        self.assertEqual((roi._sig2(4312, False), roi._sig2(4312, True)), (4300, 4400))
        self.assertEqual(roi._sig2n(208123), 210000)

    def test_estimate_has_ranges_and_nothing_removed(self):
        _bare()
        for goal in roi.GOALS:
            r = roi.public(roi.estimate(goal, 90000, ["Instagram", "TikTok"], "SA", mix={"mid": 2, "micro": 6}))
            for gone in ("cost", "verdict", "advice", "sources", "split", "_posts"):
                self.assertNotIn(gone, r)
            keys = {f["key"] for f in r["figures"]}
            self.assertFalse(keys & {"cpm", "cpe", "cpc", "frequency", "impressions"})
            for f in r["figures"]:
                if f["key"] != "er":
                    self.assertTrue(f["range"][0] <= f["value"] <= f["range"][1], (goal, f))
            self.assertIn("Estimate, not a result", r["note"])

    def test_calculator_goals_are_the_three_types(self):
        self.assertEqual(list(roi.GOALS), ["awareness", "engagement", "traffic"])


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
