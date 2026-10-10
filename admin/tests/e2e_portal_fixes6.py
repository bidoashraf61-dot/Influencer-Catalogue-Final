"""End-to-end tests for HELVY Connect fix batch 6 (2026-10-10, branch portal-fixes-6):

- Awareness, Engagement and Traffic are the only campaign types; a stored Conversion reads as Traffic,
  Balanced as an equal blend; a campaign without an objective of its own takes its selection's goals;
- scoring v2: scores carry confidence, reach and a limited-data flag; reach is not scored;
- ROI Calculator v3: ranges, a trust line, a suggested mix and ways to improve with machine-readable
  actions through the API; nothing about cost or prices; the admin's planner settings stay internal;
- Helvy's roi_plan tool.

Same harness as e2e_portal.py (throwaway copy of admin/*.py, empty database, captured mail,
scripted Gemini), so it never touches catalogue.db or the network.

    python3 admin/tests/e2e_portal_fixes6.py
"""
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import assistant, db, gemini, guard, mailer, metrics, roi, selstatus, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

FULL = {"followers": 42000, "er": 4.6, "avg_views": 9100, "sample_posts": 20, "median_views": 8200, "median_er_on_views": 3.4,
        "audience": {"countries": [{"code": "SA", "pct": 52}, {"code": "AE", "pct": 22}], "gender": {"female": 72, "male": 28}}}
BASIC = {"followers": 38000, "er": 3.1, "avg_views": 5000, "basic": True, "sample_posts": 12}


class Fixes6(unittest.TestCase):
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
        db.save_analysis("HV-MI-001", FULL, platform="Instagram")
        db.save_analysis("HV-MI-002", BASIC, platform="Instagram")
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

    def selection(self, c, name, codes, goal="awareness"):
        s, made, _ = c.post("/api/selection", {"name": name, "codes": codes})
        c.post("/api/brief/attach", {"token": made["token"], "answers": {"goal": goal, "platforms": ["Instagram"], "market": "SA",
                                                                         "category": ["skincare"]}})
        return made["token"]

    # ------------------------------------------------------------ campaign types --
    def test_01_conversion_is_gone_and_old_values_read(self):
        c, _ = self.signup("types6@glowderma.com")
        s, q, _ = c.get("/api/brief/questions")
        goal = next(x for x in q["questions"] if x["id"] == "goal")
        self.assertEqual([o["value"] for o in goal["options"]], ["awareness", "engagement", "traffic"])
        tok = self.selection(c, "Legacy", ["HV-MI-001", "HV-MI-002"], goal=["awareness", "conversion"])
        s, sel, _ = c.get("/api/selection?s=" + tok)
        self.assertEqual(sel["brief"]["objective"], "Awareness+Traffic")
        # the Helvy tool and the shortlist take the three
        decl = assistant.CLIENT_TOOLS["suggest_shortlist"][1]
        self.assertNotIn("conversion", json.dumps(decl))

    def test_02_campaign_objective_comes_from_the_brief_goals(self):
        c, _ = self.signup("camp6@glowderma.com")
        tok = self.selection(c, "Two goals", ["HV-MI-001", "HV-MI-002"], goal=["awareness", "engagement"])
        sel = db.selection(token=tok)
        k = db.create_campaign("Two goals live", "Glowderma", sel["code_id"], selection_id=sel["id"])
        row = db.campaign(k)
        self.assertEqual(metrics.objective_of(row), "awareness+engagement")
        label, w, kpis = metrics.objective_info("awareness+engagement")
        self.assertEqual(label, "Awareness + Engagement")
        a, e_ = metrics.OBJECTIVES["awareness"][1], metrics.OBJECTIVES["engagement"][1]
        for x, y, z in zip(w, a, e_):
            self.assertAlmostEqual(x, (y + z) / 2.0)
        self.assertEqual(metrics.OBJECTIVES["traffic"][0], "Traffic")
        # legacy and unknown keys
        db.save_campaign(k, objective="conversion")
        self.assertEqual(metrics.objective_of(db.campaign(k)), "traffic")
        db.save_campaign(k, objective="nonsense")
        self.assertEqual(metrics.objective_of(db.campaign(k)), "awareness+engagement")      # back to the brief, not "balanced"
        db.save_campaign(k, objective="balanced")
        self.assertEqual(metrics.objective_of(db.campaign(k)), "balanced")                  # admin-only, kept
        self.assertTrue(metrics.valid_objective("awareness+traffic"))
        self.assertFalse(metrics.valid_objective("awareness+conversion"))

    # ------------------------------------------------------------------ scoring --
    def test_03_scores_carry_confidence_and_reach(self):
        c, _ = self.signup("score6@glowderma.com")
        tok = self.selection(c, "Scored", ["HV-MI-001", "HV-MI-002"])
        s, sel, _ = c.get("/api/selection?s=" + tok)
        for code in ("HV-MI-001", "HV-MI-002"):
            sc = sel["scores"][code]
            self.assertIn(sc["confidence"]["level"], ("high", "medium", "low"))
            self.assertIn("limited_data", sc)
            self.assertIsInstance(sc["reach_followers"], int)
            self.assertNotIn("Reach", [p["label"] for p in sc["parts"]])

    # ---------------------------------------------------------------------- ROI --
    def test_04_roi_api_ranges_trust_plan_and_ways(self):
        c, _ = self.signup("roi6@glowderma.com")
        tok = self.selection(c, "ROI", ["HV-MI-001", "HV-MI-002", "HV-MD-004"])
        s, r, _ = c.post("/api/roi/estimate", {"token": tok, "goals": ["awareness", "traffic"], "budget": 200000,
                                               "platforms": ["Instagram", "TikTok"], "market": "EG"})
        self.assertEqual(s, 200, r)
        res = r["result"]
        self.assertEqual(res["goals"], ["awareness", "traffic"])
        self.assertTrue(res["trust"]["line"].startswith("Based on measured data for"))
        self.assertIn("Estimate, not a result", res["note"])
        keys = {f["key"] for f in res["figures"]}
        self.assertEqual(keys, {"views", "reach", "clicks"})
        for f in res["figures"]:
            self.assertLessEqual(f["range"][0], f["value"] * 1.0001)
        txt = json.dumps(res).lower()
        for word in ("cpm", "cpe", "cpc", "frequency", "verdict", "price", "creators_budget"):
            self.assertNotIn(word, txt, word)
        self.assertIn("plan", res)
        self.assertLessEqual(len(res["ways"]), 3)
        for w in res["ways"]:
            self.assertIn(w["action"]["type"], ("remove", "add", "second_post", "add_platform", "use_mix"))
            self.assertNotRegex(w["text"].lower(), r"sar|price|cost|cheap")
        # the market does not change a number
        s, r2, _ = c.post("/api/roi/estimate", {"token": tok, "goals": ["awareness", "traffic"], "budget": 200000,
                                                "platforms": ["Instagram", "TikTok"], "market": "SA"})
        self.assertEqual(r2["result"]["figures"], res["figures"])
        # the budget does not change the estimate either
        s, r3, _ = c.post("/api/roi/estimate", {"token": tok, "goals": ["awareness", "traffic"], "budget": 5000,
                                                "platforms": ["Instagram", "TikTok"]})
        self.assertEqual(r3["result"]["figures"], res["figures"])
        # a second post for a creator is counted
        s, r4, _ = c.post("/api/roi/estimate", {"token": tok, "goals": ["awareness"], "platforms": ["Instagram"], "second_posts": ["HV-MI-001"]})
        s, r5, _ = c.post("/api/roi/estimate", {"token": tok, "goals": ["awareness"], "platforms": ["Instagram"]})
        self.assertGreater(r4["result"]["totals"]["views"], r5["result"]["totals"]["views"])

    def test_05_mix_input_gets_a_suggested_mix_and_old_estimates_read(self):
        c, _ = self.signup("mix6@glowderma.com")
        s, r, _ = c.post("/api/roi/estimate", {"goals": ["engagement"], "budget": 150000, "platforms": ["TikTok"], "mix": {"micro": 1}})
        res = r["result"]
        self.assertTrue(res["plan"]["mix"])
        self.assertEqual(res["trust"]["of"], 0)
        # a per-platform mix (the suggested one) is accepted back
        s, r, _ = c.post("/api/roi/estimate", {"goals": ["engagement"], "platforms": ["TikTok"], "mix": res["plan"]["mix"]})
        self.assertEqual(s, 200)
        self.assertEqual(r["result"]["creators"], res["plan"]["creators"])
        # saving keeps ranges and reads back clean
        tok = self.selection(c, "Saved", ["HV-MI-001"])
        s, b, _ = c.post("/api/roi/save", {"token": tok, "goals": ["awareness"], "platforms": ["Instagram"], "budget": 90000})
        self.assertTrue(b["ok"], b)
        saved = c.get("/api/roi/saved?s=" + tok)[1]["saved"]
        self.assertEqual(saved["input"]["goals"], ["awareness"])
        self.assertNotIn("cost", saved["result"])

    def test_06_helvy_plan_tool(self):
        ctx = {"code_id": 1, "kind": "client"}
        out = assistant._roi_plan_tool(ctx, ["awareness", "conversion"], 120000, ["Instagram"])
        self.assertTrue(out["suggested_mix"])
        self.assertIn("rules", out)
        self.assertEqual(ctx["roi"]["goals"], ["awareness", "traffic"])
        for word in ("sar", "price", "cost"):
            self.assertNotIn(word, json.dumps({k: v for k, v in out.items() if k != "rules"}).lower())
        self.assertIn("error", assistant._roi_plan_tool({"code_id": 1}, ["awareness"], 0, ["Instagram"]))
        self.assertIn("roi_plan", assistant.CLIENT_TOOLS)

    def test_07_planner_settings_are_internal(self):
        db.set_setting("roi_creator_share", 0.5)
        db.set_setting("roi_planning_prices", {"micro": 2345})
        share, prices = roi.settings()
        self.assertEqual((share, prices["micro"], prices["nano"]), (0.5, 2345, 650))
        c, _ = self.signup("priv6@glowderma.com")
        s, r, _ = c.post("/api/roi/estimate", {"goals": ["awareness"], "budget": 100000, "platforms": ["Instagram"], "mix": {"micro": 2}})
        self.assertNotIn("2345", json.dumps(r))
        db.set_setting("roi_creator_share", None)
        db.set_setting("roi_planning_prices", None)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=1)
    finally:
        shutil.rmtree(base.TMP, ignore_errors=True)
