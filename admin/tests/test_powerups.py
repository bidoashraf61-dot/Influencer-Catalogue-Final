"""Brief power-ups (item 172): optional answers that blend fit into the score as soft boosts.

    python3 admin/tests/test_powerups.py
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db  # noqa: E402

os.environ.pop("GEMINI_API_KEY", None)          # keyword reading only: no network in tests
TMP = Path(tempfile.mkdtemp())
db.DB_PATH = TMP / "t.db"
db.init()

import discover  # noqa: E402
import matcher  # noqa: E402
import powerups  # noqa: E402
import tone  # noqa: E402


def creator(code, followers, tier, industry_, subs, city="Riyadh"):
    db.upsert_creator({"code": code, "name": "Test " + code, "handle": code.lower(), "platform": "Instagram",
                       "followers": followers, "tier": tier, "city": city, "interest": "Health", "active": 1,
                       "nationality": None, "photo": None, "profiles": "[]", "note": None, "sort": 0})
    with db.connect() as conn:
        conn.execute("UPDATE creators SET industry = ?, sub_niches = ? WHERE code = ?", (industry_, json.dumps(subs), code))


def analysis(code, female, ages, cities, langs, paid=0):
    db.save_analysis(code, {"followers": 50000, "er": 3.0, "bio": "bio",
                            "content_languages": langs, "collab_summary": {"posts": 10, "paid": paid, "gifted": 0, "last_date": "2026-09-01"},
                            "audience": {"gender": {"female": female, "male": 100 - female},
                                         "ages": [{"name": k, "pct": v} for k, v in ages.items()],
                                         "countries": [{"code": "SA", "pct": 70}],
                                         "cities": [{"name": k, "pct": v} for k, v in cities.items()]}},
                     source="test", platform="Instagram")


creator("HV-T-001", 60000, "HCP - Micro", "Health & Medical", ["Pharmacy"])
creator("HV-T-002", 80000, "Micro", "Beauty & Personal Care", ["Makeup"])
creator("HV-T-003", 900000, "Macro", "Family & Parenting", ["Mom life"])
creator("HV-T-004", 15000, "Nano", "General Lifestyle", [])          # no analysis at all
analysis("HV-T-001", 78, {"25-34": 55, "35-44": 20}, {"Riyadh": 40}, ["Arabic"], paid=0)
analysis("HV-T-002", 30, {"18-24": 60, "25-34": 20}, {"Jeddah": 50}, ["English"], paid=6)
analysis("HV-T-003", 85, {"25-34": 45, "35-44": 35}, {}, ["Arabic", "English"], paid=2)
tone.ensure()
with db.connect() as conn:
    conn.execute("INSERT INTO creator_tone (code, tones, model, updated_at) VALUES ('HV-T-001', '[\"educational\"]', 't', 1)")


def row(code):
    return next(c for c in db.list_creators() if c["code"] == code)


BASE = {"goal": "awareness", "platforms": ["Instagram"], "market": "SA", "category": ["health care"]}


class Answers(unittest.TestCase):
    def test_power_answers_cleaned(self):
        a, missing = matcher.clean_answers(dict(BASE, creator_type=["pharmacist", "nope"], licence="preferred",
                                                lookalikes=["HV-T-002", "HV-XX-999", "bad code!"], tone=["fun"],
                                                content_lang="ar", collab="either", claim_tags=["Pharmacy", "Not a tag"],
                                                product="Lumi D3 drops", mix="hero"))
        self.assertEqual(missing, [])
        self.assertEqual(a["creator_type"], ["pharmacist"])
        self.assertEqual(a["lookalikes"], ["HV-T-002"])
        self.assertEqual(a["claim_tags"], ["Pharmacy"])
        self.assertEqual(a["mix"], "hero")

    def test_no_power_means_no_fit(self):
        b = matcher.to_brief(matcher.clean_answers(dict(BASE))[0])
        self.assertNotIn("power", b["target"])
        b = matcher.to_brief(matcher.clean_answers(dict(BASE, gender="Any", age="Any", collab="either"))[0])
        self.assertNotIn("power", b["target"])                  # "everyone" / "either" ask for nothing

    def test_power_in_target(self):
        b = matcher.to_brief(matcher.clean_answers(dict(BASE, gender="Women", age=["25-34"]))[0])
        p = b["target"]["power"]
        self.assertEqual((p["gender"], p["age"], p["market"], p["space"]), ("Women", ["25-34"], ["SA"], ["health care"]))
        b = matcher.to_brief(matcher.clean_answers(dict(BASE, creator_type=["pharmacist"], lookalikes=["HV-T-002"],
                                                        product="Drops", claim_tags=["Pharmacy"], regulated="yes"))[0])
        p = b["target"]["power"]
        self.assertEqual((p["creator_type"], p["lookalikes"], p["claim"], p["regulated"]), (["pharmacist"], ["HV-T-002"], True, True))

    def test_public_questions_unchanged_for_the_form(self):
        ids = [q["id"] for q in matcher.public_questions()]
        self.assertIn("mix", ids)
        for pid in ("creator_type", "lookalikes", "tone", "claim_tags"):
            self.assertNotIn(pid, ids)                        # served apart, under "powerups"
        pub = powerups.public()
        self.assertEqual([c["id"] for c in pub["cards"]][:3], ["type", "claim", "licence"])
        self.assertEqual(pub["top3"]["health care"], ["type", "claim", "licence"])


class Fit(unittest.TestCase):
    P = {"gender": "Women", "age": ["25-34"], "creator_type": ["pharmacist"], "content_lang": "ar",
         "market": ["SA"], "space": ["health care"], "tone": ["educational"], "collab": "fresh"}

    def test_pharmacist_women_fits_best(self):
        f1 = powerups.fit_for(row("HV-T-001"), self.P)
        f2 = powerups.fit_for(row("HV-T-002"), self.P)
        self.assertGreater(f1["score"], f2["score"])
        self.assertIn("Pharmacist", f1["chips"])
        self.assertTrue(any(c.startswith("Women") for c in f1["chips"]))
        for ch in f1["chips"]:
            self.assertFalse(any(d.isdigit() for d in ch.replace("25–34", "")), ch)   # words, no shares

    def test_missing_data_is_neutral(self):
        f = powerups.fit_for(row("HV-T-004"), {"gender": "Women"})
        self.assertEqual(f["score"], powerups.NEUTRAL)
        self.assertEqual({i["level"] for i in f["items"]}, {"none"})

    def test_tone_and_licence(self):
        f = powerups.fit_for(row("HV-T-001"), {"tone": ["educational"]})
        self.assertEqual(f["score"], 100)
        self.assertEqual(powerups.fit_for(row("HV-T-002"), {"tone": ["educational"]})["items"][0]["level"], "none")
        self.assertEqual(powerups.fit_for(row("HV-T-002"), {"licence": "preferred"})["score"], 40)

    def test_lookalikes(self):
        f = powerups.fit_for(row("HV-T-003"), {"lookalikes": ["HV-T-001"]})
        self.assertEqual(f["items"][0]["k"], "like")
        self.assertGreaterEqual(f["score"], 0)

    def test_regulated_claim_lifts_medical(self):
        p = {"claim": True, "regulated": True, "claim_tags": ["Pharmacy"], "space": ["health care"]}
        self.assertGreater(powerups.fit_for(row("HV-T-001"), p)["score"], powerups.fit_for(row("HV-T-002"), p)["score"])


class Ranking(unittest.TestCase):
    def test_blend_applies_only_with_power(self):
        s = {"score": 80, "tag": "Strong fit", "platform": "Instagram"}
        val, factor, out = matcher.apply_rules(row("HV-T-001"), dict(s), 80, "analysis", {"country": "SA", "category": "health care"})
        self.assertEqual((val, factor), (80, 1.0))
        tgt = {"country": "SA", "category": "health care", "power": {"creator_type": ["mom"], "space": ["health care"], "market": ["SA"]}}
        val, factor, out = matcher.apply_rules(row("HV-T-001"), dict(s), 80, "analysis", tgt)
        self.assertEqual(out["perf"], 80)
        self.assertEqual(val, powerups.blend(80, out["fit"]["score"]))
        self.assertLess(factor, 1.0)

    def test_mix_is_soft(self):
        items = [{"code": "A", "rank_score": 90, "band": "micro", "audience_level": 1},
                 {"code": "B", "rank_score": 85, "band": "mega", "audience_level": 1},
                 {"code": "C", "rank_score": 82, "band": "nano", "audience_level": 1}]
        self.assertEqual([i["code"] for i in matcher._mix(list(items), "hero")], ["B", "A", "C"])
        self.assertEqual([i["code"] for i in matcher._mix(list(items), "big")], ["B", "A", "C"])
        self.assertEqual([i["code"] for i in matcher._mix(list(items), "micro")], ["A", "C", "B"])
        self.assertEqual(len(matcher._mix(list(items), "micro")), 3)       # nobody removed
        self.assertEqual([i["code"] for i in matcher._mix(list(items), None)], ["A", "B", "C"])

    def test_read_claim_without_ai(self):
        got = powerups.read_claim("Lumi vitamin D3 drops", "Clinically proven to support strong bones", ["health care"])
        self.assertTrue(got["regulated"])
        self.assertTrue(got["tags"])
        self.assertTrue(set(got["tags"]) <= powerups.all_tags())

    def test_tone_import(self):
        f = TMP / "tones.jsonl"
        f.write_text('{"code": "HV-T-002", "tones": ["fun", "bogus"], "model": "m"}\n{"code": "HV-T-003", "tones": []}\n')
        self.assertEqual(tone.import_file(str(f)), 1)
        self.assertEqual(tone.all_tags()["HV-T-002"], ["fun"])


if __name__ == "__main__":
    unittest.main()
