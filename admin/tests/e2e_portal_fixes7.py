"""End-to-end tests for HELVY Connect fix batch 7 (2026-10-10, branch portal-fixes-7): ROI Calculator v4,
structure vs performance.

- the comparison through the API: the recommended structure for the same creators and posts, the
  Selection quality, the gap, ways to improve with machine-readable actions;
- no budget, price, cost or market anywhere in the output, and an old client's budget/market is ignored;
- the recommended-structure settings card: saved when each goal adds up to 100, refused otherwise;
- Helvy's roi_compare tool and the chat's typed "N creators" answer.

Shapes are read from roi.SHAPES_DEFAULT, never hard-coded here.

    python3 admin/tests/e2e_portal_fixes7.py
"""
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import assistant, db, gemini, guard, mailer, roi, selstatus, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

FULL = {"followers": 42000, "er": 4.6, "avg_views": 9100, "sample_posts": 20, "median_views": 8200, "median_er_on_views": 3.4}
BASIC = {"followers": 38000, "er": 3.1, "avg_views": 5000, "basic": True, "sample_posts": 12}
FORBIDDEN = ("budget", "price", "cpm", "cpe", "cpc", "frequency", "verdict", "market", "planning", "creators_share")


class Fixes7(unittest.TestCase):
    signup = base.Portal.signup
    admin = base.Portal.admin

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

    def selection(self, c, name, codes):
        s, made, _ = c.post("/api/selection", {"name": name, "codes": codes})
        c.post("/api/brief/attach", {"token": made["token"], "answers": {"goal": "awareness", "platforms": ["Instagram"], "market": "SA",
                                                                         "category": ["skincare"], "count": "5"}})
        return made["token"]

    def test_01_comparison_through_the_api(self):
        c, _ = self.signup("cmp7@glowderma.com")
        tok = self.selection(c, "Compare", ["HV-MI-001", "HV-MI-002", "HV-MD-004"])
        s, r, _ = c.post("/api/roi/estimate", {"token": tok, "goals": ["awareness"], "platforms": ["Instagram", "TikTok"]})
        self.assertEqual(s, 200, r)
        res = r["result"]
        self.assertEqual(res["version"], 4)
        n = res["creators"]
        self.assertTrue(n >= 1)
        ideal = res["ideal"]
        self.assertEqual(ideal["creators"], n)
        self.assertEqual(ideal["posts"], res["posts"])
        self.assertEqual(sum(sum(m.values()) for m in ideal["mix"].values()), res["posts"])
        self.assertIn("Ideal for Awareness with %d creator" % n, ideal["title"])
        self.assertEqual(ideal["name"], "HelloVoice’s recommended structure")
        self.assertIsNotNone(res["quality"])
        self.assertEqual(res["quality"]["pct"] % 5, 0)
        self.assertEqual(res["trust"]["line"].split(" for ")[0], "Based on measured data")
        self.assertIn("Estimate, not a result", res["note"])
        txt = json.dumps(res).lower()
        for w in FORBIDDEN:
            self.assertNotIn(w, txt, w)
        self.assertLessEqual(len(res["ways"]), 3)
        for w in res["ways"]:
            self.assertIn(w["action"]["type"], ("replace", "remove", "add", "second_post", "add_platform"))
            self.assertGreater(w["points"], 0)
        # an old client's budget and market change nothing
        s, r2, _ = c.post("/api/roi/estimate", {"token": tok, "goals": ["awareness"], "platforms": ["Instagram", "TikTok"],
                                                "budget": 999999, "market": "EG"})
        self.assertEqual(r2["result"]["figures"], res["figures"])
        self.assertEqual(r2["result"]["quality"], res["quality"])

    def test_02_mix_page_and_chat_card(self):
        c, _ = self.signup("mix7@glowderma.com")
        s, r, _ = c.post("/api/roi/estimate", {"goals": ["engagement"], "platforms": ["TikTok"], "mix": {"nano": 6}})
        res = r["result"]
        self.assertEqual(res["ideal"]["creators"], 6)
        self.assertEqual(res["ideal"]["mix"]["TikTok"], roi.largest_remainder(roi.SHAPES_DEFAULT["engagement"], 6))
        self.assertEqual([w["action"]["type"] for w in res["ways"]], ["use_mix"])
        # the typed question: an instant, free card with the ideal only
        before = c.get("/api/me")[1]["credits"]
        s, raw, _ = c.post("/api/chat/stream", {"message": "What can 12 creators do for engagement on instagram?"})
        done = [json.loads(x) for x in raw.splitlines() if x.strip()][-1]
        self.assertEqual(done["t"], "done")
        card = done["roi"]
        self.assertTrue(card["ideal_only"])
        self.assertEqual((card["count"], card["goal"]), (12, "engagement"))
        self.assertEqual(card["mix"]["Instagram"], roi.largest_remainder(roi.SHAPES_DEFAULT["engagement"], 12))
        self.assertEqual(before, c.get("/api/me")[1]["credits"])
        # an amount of money is not a calculator question any more
        self.assertIsNone(roi.from_text("What can SAR 60,000 reach on TikTok?"))

    def test_03_saved_estimate_has_no_budget_and_reads_back(self):
        c, _ = self.signup("save7@glowderma.com")
        tok = self.selection(c, "Saved", ["HV-MI-001", "HV-MI-002"])
        s, b, _ = c.post("/api/roi/save", {"token": tok, "goals": ["awareness"], "platforms": ["Instagram"], "budget": 50000, "market": "AE"})
        self.assertTrue(b["ok"], b)
        saved = c.get("/api/roi/saved?s=" + tok)[1]["saved"]
        for k in ("budget", "market"):
            self.assertNotIn(k, saved["input"])
        self.assertIn("quality", saved["result"])
        for w in FORBIDDEN:
            self.assertNotIn(w, json.dumps(saved).lower(), w)

    def test_04_settings_card_validates_the_shapes(self):
        a = self.admin()
        s, body, _ = a.get("/portal?tab=settings")
        self.assertEqual(s, 200)
        self.assertIn("Recommended structure", body)
        self.assertIn("not an industry benchmark", body)
        self.assertNotIn("Planning price per post", body)
        form = {"signup_mode": "open", "back": "/portal?tab=settings"}
        for g in roi.GOALS:
            for t in roi.TIER_ORDER:
                form["roi_shape_%s_%s" % (g, t)] = str(roi.SHAPES_DEFAULT[g].get(t, 0))
        # a valid change to awareness is stored
        good = dict(form, roi_shape_awareness_macro="0", roi_shape_awareness_mid="30", roi_shape_awareness_micro="50", roi_shape_awareness_nano="20")
        a.req("POST", "/portal/settings", form=good)
        self.assertEqual(roi.shapes()["awareness"], {"mid": 30.0, "micro": 50.0, "nano": 20.0})
        self.assertEqual(roi.ideal_counts(["awareness"], 10)["Instagram"], {"mid": 3, "micro": 5, "nano": 2})
        # one that does not add up is refused and keeps the previous shape; the other goals still save
        bad = dict(good, roi_shape_traffic_micro="70", roi_shape_awareness_mid="35")
        a.req("POST", "/portal/settings", form=bad)
        self.assertEqual(roi.shapes()["traffic"], {t: float(v) for t, v in roi.SHAPES_DEFAULT["traffic"].items()})
        self.assertEqual(roi.shapes()["awareness"]["mid"], 30.0)
        # back to the defaults: nothing is stored
        a.req("POST", "/portal/settings", form=form)
        self.assertIsNone(db.setting("roi_shapes"))
        self.assertEqual(roi.shapes()["awareness"], {t: float(v) for t, v in roi.SHAPES_DEFAULT["awareness"].items()})

    def test_05_helvy_tools(self):
        self.assertIn("roi_compare", assistant.CLIENT_TOOLS)
        self.assertNotIn("roi_plan", assistant.CLIENT_TOOLS)
        for name in ("roi_estimate", "roi_compare"):
            decl = json.dumps(assistant.CLIENT_TOOLS[name][1]["parameters"]).lower()
            self.assertNotIn("budget", decl)
        ctx = {"code_id": 1, "kind": "client"}
        out = assistant._roi_tool(ctx, "awareness", ["Instagram"], {"nano": 6})
        self.assertIn("quality_of_the_mix", out)
        self.assertEqual(ctx["roi"]["ideal"]["creators"], 6)
        text = json.dumps({k: v for k, v in out.items() if k != "note"}).lower()
        for w in FORBIDDEN + ("sar",):
            self.assertNotIn(w, text, w)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=1)
    finally:
        shutil.rmtree(base.TMP, ignore_errors=True)
