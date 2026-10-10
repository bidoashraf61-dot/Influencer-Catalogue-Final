"""End-to-end tests for the HELVY Connect fix batch 3 (2026-10-10, branch portal-fixes-3):

- the selection objective takes several goals (stored as "Awareness+Engagement", scored with
  both goals' weights), a selection is scored only once it has an objective, and the brief's
  answers come back for Edit;
- Find a replacement: three creators outside the selection, each with a "why", kept (opening
  them again is free), only for the selection's owner;
- the selection request reads only the selection's creators, and per-request memoised team /
  campaign lookups never leak between requests.

Same harness as e2e_portal.py (a throwaway copy of admin/*.py, an empty database, captured
mail, a scripted Gemini), so it never touches catalogue.db or the network.

    python3 admin/tests/e2e_portal_fixes3.py
"""
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402
from e2e_portal import Client  # noqa: E402

import db, fit, gemini, guard, mailer, matcher, portal, selstatus, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

TWO = {"goal": ["awareness", "engagement"], "platforms": ["Instagram"], "market": "SA", "category": ["skincare"],
       "gender": "Women", "age": "25-34"}


class Fixes3(unittest.TestCase):
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
        for code in ("HV-MI-001", "HV-MI-002", "HV-MD-004"):
            db.save_analysis(code, {"followers": 42000, "er": 4.6, "avg_views": 9100, "basic": True}, platform="Instagram")
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

    def sel(self, c, name, codes):
        s, b, _ = c.post("/api/selection", {"name": name, "codes": codes})
        self.assertEqual(s, 200, b)
        return b["token"]

    # ------------------------------------------------------------ objective --
    def test_01_goals_multi_select_scores_only_after_the_objective(self):
        c, _ = self.signup("hala@multi-goal.com")
        token = self.sel(c, "Multi goal", ["HV-MI-001", "HV-MI-002", "HV-MD-004"])
        s, b, _ = c.get("/api/selection?s=" + token)
        self.assertTrue(b.get("needs_objective"))
        self.assertEqual(b["scores"], {})
        s, att, _ = c.post("/api/brief/attach", {"token": token, "answers": TWO})
        self.assertTrue(att.get("ok"), att)
        self.assertIn("awareness and engagement", att["brief"].lower())
        s, b, _ = c.get("/api/selection?s=" + token)
        self.assertNotIn("needs_objective", b)
        self.assertEqual(b["brief"]["objective"], "Awareness+Engagement")
        self.assertTrue(set(b["codes"]) <= set(b["scores"]))
        one = next(v for v in b["scores"].values() if v["score"] is not None)
        self.assertEqual(one["objective"], "Awareness+Engagement")
        # Edit reopens the answers as given
        s, f, _ = c.get("/api/brief/for?s=" + token)
        self.assertEqual(f["brief"]["answers"]["goal"], ["awareness", "engagement"])
        # one goal again: back to a single objective
        s, att, _ = c.post("/api/brief/attach", {"token": token, "answers": dict(TWO, goal=["conversion"])})
        s, b, _ = c.get("/api/selection?s=" + token)
        self.assertEqual(b["brief"]["objective"], "Conversion")

    def test_02_goal_cleaning_and_blended_weights(self):
        a, missing = matcher.clean_answers(dict(TWO, goal=["awareness", "nonsense", "engagement", "awareness"]))
        self.assertEqual(a["goal"], ["awareness", "engagement"])
        self.assertEqual(missing, [])
        a, _ = matcher.clean_answers(dict(TWO, goal=["engagement"]))
        self.assertEqual(a["goal"], "engagement")                  # one goal stays a plain value
        a, missing = matcher.clean_answers(dict(TWO, goal=["nonsense"]))
        self.assertIn("goal", missing)
        self.assertEqual(matcher.objective_for(["balanced", "awareness"]), "Awareness")
        self.assertEqual(matcher.objective_for(["balanced"]), "Balanced")
        w = fit.blend(fit.WEIGHTS_BASIC, "Awareness+Engagement")
        for k in w:
            self.assertAlmostEqual(w[k], (fit.WEIGHTS_BASIC["Awareness"][k] + fit.WEIGHTS_BASIC["Engagement"][k]) / 2)
        self.assertTrue(fit.known_objective("Awareness+Conversion"))
        self.assertFalse(fit.known_objective("Awareness+Hack"))
        doc = {"followers": 50000, "er": 3.2, "avg_views": 12000, "basic": True}
        both = fit.score_core(doc, "Instagram", objective="Awareness+Engagement")
        self.assertEqual(both["objective"], "Awareness+Engagement")
        self.assertIn("awareness + engagement", both["conclusion"].lower())

    # ----------------------------------------------------------- replacement --
    def test_03_replacement_suggestions_have_a_why_and_are_kept(self):
        c, _ = self.signup("rana@repl-test.com")
        token = self.sel(c, "Replace test", ["HV-MI-001", "HV-MI-002"])
        c.post("/api/brief/attach", {"token": token, "answers": TWO})
        s, b, _ = c.post("/api/selection/replace", {"token": token, "code": "HV-MI-001"})
        self.assertEqual((s, b.get("reason")), (400, "not_rejected"))
        c.post("/api/selection/status", {"token": token, "code": "HV-MI-001", "status": "rejected"})
        s, b, _ = c.post("/api/selection/replace", {"token": token, "code": "HV-MI-001"})
        self.assertEqual(s, 200, b)
        self.assertTrue(b["ok"])
        picks = b["replacements"]
        self.assertTrue(picks)
        for p in picks:
            self.assertNotIn(p["code"], ("HV-MI-001", "HV-MI-002"))
            self.assertTrue(p["why"].startswith("In Noha Magdy's place"), p["why"])
            for k in ("name", "tier", "followers", "platform"):
                self.assertIn(k, p)
        first = b["spent"]
        s, again, _ = c.post("/api/selection/replace", {"token": token, "code": "HV-MI-001"})
        self.assertEqual(again["spent"], 0)                          # kept: free the second time
        self.assertEqual([p["code"] for p in again["replacements"]], [p["code"] for p in picks])
        self.assertGreaterEqual(first, 0)
        # adding one (the page re-saves the selection with it) leaves the rejected creator rejected
        s, b2, _ = c.post("/api/selection", {"name": "Replace test", "codes": ["HV-MI-001", "HV-MI-002", picks[0]["code"]], "token": token})
        s, view, _ = c.get("/api/selection?s=" + token)
        self.assertIn(picks[0]["code"], view["codes"])
        self.assertEqual(view["status"]["HV-MI-001"]["s"], "rejected")
        self.assertNotEqual((view["status"].get(picks[0]["code"]) or {"s": "review"})["s"], "rejected")

    def test_04_only_the_owner_finds_replacements(self):
        c, _ = self.signup("sami@repl-own.com")
        token = self.sel(c, "Owner only", ["HV-MI-001", "HV-MD-003"])
        c.post("/api/selection/status", {"token": token, "code": "HV-MD-003", "status": "rejected"})
        mate, _ = self.signup("dana@repl-own.com")                  # same company: a viewer here
        s, b, _ = mate.post("/api/selection/replace", {"token": token, "code": "HV-MD-003"})
        self.assertEqual((s, b.get("reason")), (403, "not_owner"))

    # ------------------------------------------------- selection read / memo --
    def test_05_selection_payload_only_has_its_own_creators_and_memo_is_per_request(self):
        c, _ = self.signup("lina@memo-test.com")
        token = self.sel(c, "Memo", ["HV-MI-002", "HV-MI-001", "HV-NOT-THERE"])
        s, b, _ = c.get("/api/selection?s=" + token)
        self.assertEqual(b["codes"], ["HV-MI-002", "HV-MI-001"])     # listed order, unknown dropped
        self.assertEqual(set(b["status_counts"].keys()) >= {"review"}, True)
        self.assertEqual([r["code"] for r in db.creators_by_codes(["HV-MI-002", "HV-MI-001", "nope"])], ["HV-MI-001", "HV-MI-002"])
        # outside a request nothing is cached
        u = portal.user_by_email("lina@memo-test.com")
        self.assertIsNone(portal.active_campaign(u["code_id"]))
        k = db.create_campaign("Live now", "Memo", u["code_id"])
        db.save_campaign(k, status="live")
        self.assertIsNotNone(portal.active_campaign(u["code_id"]))
        # and a fresh request sees the new campaign (AI free -> cost 0)
        s, b, _ = c.get("/api/selection?s=" + token)
        self.assertEqual(b["replace_cost"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
