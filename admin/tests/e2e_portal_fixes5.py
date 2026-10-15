"""End-to-end tests for HELVY Connect fix batch 5 (2026-10-10, branch portal-fixes-5), item 44:

(b) the countries, the gender and the age groups of the AI shortlist brief take several answers
    (goal already did); the brief, the selection's target, the saved brief, "Edit brief" and the
    chat's brief all carry them; budget, count and timing stay single;
(a) a selection built by the AI shortlist is consistent with the scoring and ROI metrics: the
    brief is attached, every creator is scored with the number the shortlist gave, and the ROI
    Calculator opens pre-filled from that brief.

Same harness as e2e_portal.py (throwaway copy of admin/*.py, empty database, captured mail,
scripted Gemini), so it never touches catalogue.db or the network.

    python3 admin/tests/e2e_portal_fixes5.py
"""
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import db, gemini, guard, mailer, roi, selstatus, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

FULL = {"followers": 42000, "er": 4.6, "avg_views": 9100,
        "audience": {"countries": [{"code": "SA", "pct": 52}, {"code": "AE", "pct": 22}],
                     "gender": {"female": 72, "male": 28},
                     "ages": [{"name": "18-24", "pct": 30}, {"name": "25-34", "pct": 40}, {"name": "35-44", "pct": 20}]}}
BASIC = {"followers": 38000, "er": 3.1, "avg_views": 5000, "basic": True}

ANS = {"goal": ["awareness", "traffic"], "platforms": ["Instagram"], "market": ["SA", "AE"], "gender": ["Women", "Men"],
       "age": ["18-24", "25-34"], "category": ["skincare"], "count": "15", "budget": "150"}


class Fixes5(unittest.TestCase):
    signup = base.Portal.signup

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        mailer.CAPTURE = True
        gemini.STUB = base.stub
        views.set_base("")
        selstatus.EMAIL_DELAY = 0
        # a mix every AI shortlist meets: measured, public numbers only, and not analysed at all
        db.save_analysis("HV-MI-001", FULL, platform="Instagram")
        db.save_analysis("HV-MI-002", BASIC, platform="Instagram")
        db.save_analysis("HV-MD-004", {"followers": 120000, "er": 1.2, "avg_views": 9000, "basic": True}, platform="Instagram")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()
        mailer.OUTBOX.clear()

    # ----------------------------------------------------------------- (b) --
    def test_01_questions_say_which_take_several(self):
        c, _ = self.signup("q5@glowderma.com")
        s, q, _ = c.get("/api/brief/questions")
        by = {x["id"]: x for x in q["questions"]}
        for qid in ("goal", "market", "gender", "age"):
            self.assertTrue(by[qid]["multi_ok"], qid)
        for qid in ("budget", "count", "timing"):
            self.assertFalse(by[qid].get("multi_ok"), qid)

    def test_02_multi_brief_builds_one_selection_with_both_countries_and_ages(self):
        c, _ = self.signup("multi5@glowderma.com")
        s, b, _ = c.post("/api/brief/run", {"answers": ANS, "name": "KSA + UAE"})
        self.assertEqual(s, 200, b)
        self.assertIn("Saudi Arabia and UAE", b["brief"])
        s, sel, _ = c.get("/api/selection?s=" + b["token"])
        self.assertEqual(sel["brief"]["target"]["country"], "SA|AE")
        self.assertEqual(sel["brief"]["target"]["age"], "18-24|25-34")
        self.assertEqual(sel["brief"]["target"]["gender"], "Any")           # Women + Men = everyone
        self.assertEqual(sel["brief"]["objective"], "Awareness+Traffic")
        # the saved brief reads back as given, for "Edit brief"
        s, f, _ = c.get("/api/brief/for?s=" + b["token"])
        self.assertEqual(f["brief"]["answers"]["market"], ["SA", "AE"])
        self.assertEqual(f["brief"]["answers"]["age"], ["18-24", "25-34"])
        self.assertEqual(f["brief"]["answers"]["gender"], "Any")
        # the score badges for the catalogue cards come from the same brief
        s, sc, _ = c.get("/api/brief/scores?b=%d" % b["brief_id"])
        self.assertEqual(s, 200)
        self.assertTrue(sc["scores"])

    def test_03_attach_takes_several_and_legacy_single_values_still_work(self):
        c, _ = self.signup("attach5@glowderma.com")
        s, made, _ = c.post("/api/selection", {"name": "By hand", "codes": ["HV-MI-001", "HV-MD-004"]})
        token = made["token"]
        db.set_scores_published(token)                                      # published by HelloVoice (gate, 2026-10-15)
        # a brief saved before this batch: one value each
        legacy = {"goal": "awareness", "platforms": ["Instagram"], "market": "AE", "gender": "Women", "age": "25-34", "category": ["skincare"]}
        s, att, _ = c.post("/api/brief/attach", {"token": token, "answers": legacy})
        self.assertTrue(att["ok"], att)
        s, sel, _ = c.get("/api/selection?s=" + token)
        self.assertEqual(sel["brief"]["target"], {"country": "AE", "gender": "Women", "age": "25-34", "category": "skincare"})
        legacy_scores = {k: v["score"] for k, v in sel["scores"].items()}
        self.assertTrue(all(v is not None for v in legacy_scores.values()), legacy_scores)
        # the same selection scored for two countries and two age groups
        s, att, _ = c.post("/api/brief/attach", {"token": token, "answers": dict(legacy, market=["SA", "AE"], age=["18-24", "25-34"], gender=["Women", "Men"])})
        self.assertTrue(att["ok"], att)
        self.assertIn("Saudi Arabia and UAE", att["brief"])
        s, sel, _ = c.get("/api/selection?s=" + token)
        self.assertEqual(sel["brief"]["target"]["country"], "SA|AE")
        self.assertEqual(sel["brief"]["target"]["gender"], "Any")
        # HV-MI-001 has 52% of the audience in KSA and 22% in UAE: far more of it is in the target
        # when both countries count, so its score rises (shares are summed, not compared one by one)
        # Fix batch 6: the audience is no longer scored, so the NUMBER does not move with the countries (the
        # measured audience is a check beside it, summed over the countries; locked until the analysis is unlocked)
        self.assertEqual(sel["scores"]["HV-MI-001"]["score"], legacy_scores["HV-MI-001"])
        # budget, count and timing are one value: a list is ignored, not half-kept
        s, att, _ = c.post("/api/brief/attach", {"token": token, "answers": dict(legacy, budget=["50", "150"])})
        self.assertTrue(att["ok"], att)

    def test_04_chat_brief_with_several_countries(self):
        c, _ = self.signup("chat5@glowderma.com")
        s, r, _ = c.post("/api/chat", {"message": "campaign for skincare", "brief": dict(ANS, goal="awareness")})
        self.assertEqual(s, 200, r)
        s, g, _ = c.post("/api/brief/guess", {"text": "skincare campaign in KSA on Instagram"})
        self.assertEqual(s, 200)
        self.assertEqual(g["answers"]["market"], "SA")                      # the free reader still gives one

    def test_05_timing_advisor_takes_a_list_of_countries(self):
        c, _ = self.signup("timing5@glowderma.com")
        s, t, _ = c.get("/api/timing?c=skincare&m=AE%2CSA")
        self.assertEqual(s, 200, t)
        self.assertTrue(t["ok"])

    # ----------------------------------------------------------------- (a) --
    def test_06_ai_selection_is_consistent_with_its_scores(self):
        c, _ = self.signup("consistent5@glowderma.com")
        for answers in (ANS, dict(ANS, market="SA", gender="Any", age="Any", platforms=["Instagram"], goal="awareness"),
                        dict(ANS, category=["food"], goal="engagement")):
            s, b, _ = c.post("/api/brief/run", {"answers": answers, "name": "Consistency"})
            self.assertEqual(s, 200, b)
            picks = {p["code"]: p for p in b["picks"]}
            self.assertTrue(picks)
            s, sel, _ = c.get("/api/selection?s=" + b["token"])
            # the brief is attached: objective set, no "Add your campaign objective" prompt
            self.assertNotIn("needs_objective", sel)
            self.assertTrue(sel["brief"]["objective"])
            self.assertEqual(sel["brief"]["objective"], b["objective"])
            s, f, _ = c.get("/api/brief/for?s=" + b["token"])
            self.assertEqual(f["brief"]["summary"], b["brief"])
            # every creator is scored, and not below what the shortlist said
            self.assertEqual(set(sel["scores"]), set(picks))
            for code, p in picks.items():
                got = sel["scores"][code]["score"]
                self.assertIsNotNone(got, "%s has no score on the selection page" % code)
                self.assertGreaterEqual(got, p["score"] - 3, "%s: shortlist %s, selection %s" % (code, p["score"], got))
                # same rules, same number: the only allowed gap is a different platform being the best one
                self.assertEqual(got, p["score"], "%s: shortlist %s, selection %s" % (code, p["score"], got))
                self.assertEqual(sel["scores"][code]["tag"], p["tag"])

    def test_07_roi_calculator_opens_prefilled_from_the_brief(self):
        c, _ = self.signup("roi5@glowderma.com")
        s, b, _ = c.post("/api/brief/run", {"answers": dict(ANS, market=["KW", "AE"], goal=["engagement"], platforms=["TikTok"]), "name": "ROI seed"})
        self.assertEqual(s, 200, b)
        s, r, _ = c.get("/api/roi/saved?s=" + b["token"])
        self.assertEqual(s, 200, r)
        self.assertIsNone(r["saved"])
        seed = r["seed"]
        # fix batch 7: no budget and no market in the seed; the brief's number of creators is
        self.assertEqual((seed["goal"], seed["platforms"], seed["count"]), ("engagement", ["TikTok"], 15))
        self.assertNotIn("budget", seed)
        self.assertNotIn("market", seed)
        # the same inputs the drawer will send are valid for the calculator
        s, est, _ = c.post("/api/roi/estimate", {"goal": seed["goal"], "platforms": seed["platforms"], "token": b["token"]})
        self.assertEqual(s, 200, est)
        self.assertNotIn("market_label", est["result"])
        self.assertNotIn("budget", est["result"])
        # Conversion reads as Traffic
        s, b2, _ = c.post("/api/brief/run", {"answers": dict(ANS, budget="open", goal="conversion", market="EG", platforms=["Instagram", "TikTok"]), "name": "No budget"})
        seed2 = c.get("/api/roi/saved?s=" + b2["token"])[1]["seed"]
        self.assertEqual((seed2["goal"], seed2["platforms"]), ("traffic", ["Instagram", "TikTok"]))
        self.assertNotIn("budget", seed2)
        # a saved estimate wins over the seed
        s, sv, _ = c.post("/api/roi/save", {"token": b["token"], "goal": "awareness", "budget": 80000, "platforms": ["Instagram"], "market": "SA"})
        self.assertEqual(s, 200, sv)
        got = c.get("/api/roi/saved?s=" + b["token"])[1]
        self.assertEqual(got["saved"]["input"]["goal"], "awareness")
        self.assertEqual(got["seed"]["goal"], "engagement")                  # the server still offers it; the page prefers the saved one

    def test_08_a_selection_without_a_brief_has_no_seed(self):
        c, _ = self.signup("noseed5@glowderma.com")
        s, made, _ = c.post("/api/selection", {"name": "Plain", "codes": ["HV-MI-001"]})
        s, r, _ = c.get("/api/roi/saved?s=" + made["token"])
        self.assertEqual(s, 200)
        self.assertIsNone(r["seed"])

    def test_09_creator_without_an_analysis_is_scored_like_the_shortlist_scored_it(self):
        c, _ = self.signup("roster5@glowderma.com")
        s, made, _ = c.post("/api/selection", {"name": "Roster only", "codes": ["HV-MI-005"]})
        s, att, _ = c.post("/api/brief/attach", {"token": made["token"], "answers": {"goal": "awareness", "platforms": ["Instagram"],
                                                                                    "market": "SA", "category": ["technology"]}})
        self.assertTrue(att["ok"], att)
        s, sel, _ = c.get("/api/selection?s=" + made["token"])
        sc = sel["scores"]["HV-MI-005"]
        self.assertIsNotNone(sc["score"])
        self.assertTrue(sc["basic"])                                          # marked as from public numbers
        self.assertEqual(sc["score"], att["picks"][0]["score"])


if __name__ == "__main__":
    try:
        unittest.main(verbosity=1)
    finally:
        shutil.rmtree(base.TMP, ignore_errors=True)
