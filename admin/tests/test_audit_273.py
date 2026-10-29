"""AI shortlist audit (item 273, 2026-10-29): category tags, places, the free-text reader, typed countries
and the fake-follower cap under power-ups.

    python3 admin/tests/test_audit_273.py
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fit
import matcher


def row(interest="", tier="Micro", city="", nationality=""):
    return {"code": "X", "interest": interest, "tier": tier, "city": city, "nationality": nationality}


class Tags(unittest.TestCase):
    def test_health_care_is_medical_not_fitness(self):
        self.assertTrue(matcher._tagged(row("Health & Medical, Beauty"), ["health care"]))
        self.assertTrue(matcher._tagged(row("Health Care"), ["health care"]))
        self.assertFalse(matcher._tagged(row("Health & Fitness, Food & Restaurants"), ["health care"]))
        self.assertFalse(matcher._tagged(row("Wellness"), ["health care"]))
        self.assertTrue(matcher._tagged(row("Wellness", tier="HCP Nano"), ["health care"]))

    def test_beauty_alone_is_not_skincare_hair_or_fragrance(self):
        for cat in ("skincare", "hair care", "fragrance"):
            self.assertFalse(matcher._tagged(row("Beauty, Make-up, Lifestyle"), [cat]), cat)
        self.assertTrue(matcher._tagged(row("Beauty, Skincare"), ["skincare"]))
        self.assertTrue(matcher._tagged(row("Hair Care"), ["hair care"]))
        self.assertTrue(matcher._tagged(row("Skincare"), ["beauty"]))

    def test_fitness_and_literal_spaces(self):
        self.assertTrue(matcher._tagged(row("Health & Fitness"), ["fitness"]))
        self.assertFalse(matcher._tagged(row("Health & Medical"), ["fitness"]))
        self.assertTrue(matcher._tagged(row("E-commerce & Shopping"), ["e-commerce"]))
        self.assertTrue(matcher._tagged(row("Home & Interior"), ["home & interior"]))
        self.assertTrue(matcher._tagged(row("Motherhood"), ["mother & baby"]))


class Places(unittest.TestCase):
    def test_placeholder_countries_are_read(self):
        self.assertEqual(fit._place_mark(row(city="UAE Not Specified yet"), "AE"), (1.0, {"AE"}))
        self.assertEqual(fit._place_mark(row(city="Iraq Not Specified yet"), "SA")[1], {"IQ"})
        self.assertEqual(fit._place_mark(row(city="woman from Egypt"), "EG")[1], {"EG"})   # "oman" inside "woman" is not Oman
        # Based in: the catalogue's own place rule, a known city counts for its country (item 280)
        self.assertTrue(matcher._based_in(row(city="Riyadh"), ["SA"]))
        self.assertTrue(matcher._based_in(row(city="UAE Not Specified yet"), ["AE"]))
        self.assertFalse(matcher._based_in(row(city="Riyadh"), ["EG"]))
        self.assertFalse(matcher._based_in(row(city="Amman"), ["SA"]))


class FreeText(unittest.TestCase):
    def test_words_are_whole(self):
        got = matcher.guess("We are Biotech pharma, need doctors in Riyadh")[0]
        self.assertEqual(got.get("category"), ["health care"])
        self.assertEqual(matcher.guess("creators with 10k followers for a moment of joy")[0], {})
        self.assertEqual(matcher.guess("Launch campaign, link in bio")[0].get("goal"), "awareness")
        self.assertEqual(matcher.guess("budget 50k for sales")[0].get("budget"), "150")

    def test_typed_country_is_kept(self):
        a, _ = matcher.clean_answers({"goal": "awareness", "platforms": ["Instagram"], "market": "other:Kuwait",
                                      "category": ["beauty"]})
        self.assertEqual(matcher.to_brief(a)["target"]["country"], "KW")


class FakeCap(unittest.TestCase):
    def test_power_blend_keeps_the_cap(self):
        s = {"score": 39, "tag": "Not recommended", "fake_capped": True, "platform": "Instagram", "watchouts": []}
        with mock.patch.object(matcher.powerups, "fit_for", return_value={"score": 100, "chips": [], "items": []}):
            val, _, out = matcher.apply_rules(row("Beauty"), s, 39, "analysis", {"power": {"gender": "Women"}})
        self.assertLessEqual(val, fit.FAKE_CAP)
        self.assertEqual(out["tag"], "Not recommended")


if __name__ == "__main__":
    unittest.main()
