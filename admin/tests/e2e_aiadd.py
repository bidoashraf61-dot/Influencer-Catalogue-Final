"""Item 178: "Add creators with AI" on a selection page.

The selection's brief (or a new one) runs through the AI shortlist's own matcher, skips the
creators already in it, previews N with why-chips in words, and adds only what was ticked.
Same price as the AI shortlist; no numbers reach the page; selection scores stay paused.

    python3 admin/tests/e2e_aiadd.py
"""
import json
import re
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import aiadd, db, gemini, guard, mailer, portal, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

BRIEF = {"goal": "awareness", "platforms": ["Instagram"], "market": "SA", "category": ["skincare"]}
NUMERIC_KEYS = {"score", "rank_score", "perf", "fit", "fit_items", "score_range", "pool", "totals", "price", "followers_share"}


def walk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


class AiAdd(unittest.TestCase):
    signup = base.Portal.signup

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        db.set_setting("selections_unscored", "all")             # live state: scores paused
        mailer.CAPTURE = True
        gemini.STUB = base.stub                                  # no key locally: the AI is mocked
        views.set_base("")
        # Creators need posts on file to be scored (score v5); the e2e seed has none.
        full = {"followers": 42000, "er": 4.6, "avg_views": 9100, "sample_posts": 20, "median_views": 8200, "median_er_on_views": 3.4,
                "audience": {"countries": [{"code": "SA", "pct": 52}], "gender": {"female": 72, "male": 28}}}
        for i, code in enumerate(("HV-MI-001", "HV-MI-002", "HV-MD-004", "HV-MI-005")):
            db.save_analysis(code, dict(full, er=4.6 - i * 0.5), platform="Instagram")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()

    def make(self, c, codes, brief=True):
        s, made, _ = c.post("/api/selection", {"name": "Launch picks", "codes": codes})
        self.assertEqual(s, 200, made)
        if brief:
            s, r, _ = c.post("/api/brief/attach", {"token": made["token"], "answers": dict(BRIEF, count="5")})
            self.assertTrue(r["ok"], r)
        return made["token"]

    def no_numbers(self, payload):
        for k, v in walk(payload.get("picks") or []):
            self.assertNotIn(k, NUMERIC_KEYS, k)
        for p in payload.get("picks") or []:
            for chip in p["chips"]:
                self.assertNotRegex(chip, r"%|/100|\d+\s*(k|K|M)\b")
            self.assertEqual(set(p), {"code", "chips", "creator"})

    # ------------------------------------------------------------------ tests --
    def test_01_prefilled_brief_preview_skips_inside_then_adds_ticked(self):
        c, _ = self.signup("brand@aiadd-one.com")
        tok = self.make(c, ["HV-MI-001"])
        s, st, _ = c.get("/api/selection/ai-add?s=" + tok)
        self.assertEqual(s, 200, st)
        self.assertEqual(st["brief"]["answers"]["category"], ["skincare"])
        self.assertEqual((st["n"], st["inside"], st["cost"], st["role"]), (5, 1, portal.costs()["brief"], "owner"))
        before = portal.balance(portal.user_by_email("brand@aiadd-one.com")["code_id"])
        ans = dict(st["brief"]["answers"], licence="preferred")             # a power-up adjusted on top
        s, r, _ = c.post("/api/selection/ai-add/find", {"token": tok, "answers": ans, "n": 3})
        self.assertEqual(s, 200, r)
        codes = [p["code"] for p in r["picks"]]
        self.assertTrue(codes)
        self.assertLessEqual(len(codes), 3)
        self.assertNotIn("HV-MI-001", codes)                                # already in the selection
        self.assertTrue(all(p["chips"] for p in r["picks"]))
        self.assertTrue(all(p["creator"]["name"] for p in r["picks"]))
        self.no_numbers(r)
        self.assertFalse(r["brief_saved"])                                  # it had one: left as it was
        self.assertEqual(r["spent"], portal.costs()["brief"])
        self.assertEqual(r["credits"], before - r["spent"])
        # Only what was ticked joins; a code that was never previewed is refused silently.
        s, a, _ = c.post("/api/selection/ai-add/add", {"token": tok, "run": r["run"], "codes": [codes[0], "HV-MD-003"]})
        self.assertEqual(a["added"], [codes[0]] if codes[0] != "HV-MD-003" else ["HV-MD-003"])
        now = json.loads(db.selection(token=tok)["codes"])
        self.assertEqual(now, ["HV-MI-001", codes[0]])
        # Adding the same one again changes nothing.
        s, a2, _ = c.post("/api/selection/ai-add/add", {"token": tok, "run": r["run"], "codes": [codes[0]]})
        self.assertEqual(a2["added"], [])
        self.assertEqual(json.loads(aiadd.run(r["run"])["added"]), [codes[0]])
        self.assertEqual(db.setting("selections_unscored"), "all")         # scores stay paused

    def test_02_no_brief_runs_wizard_answers_and_keeps_them(self):
        c, _ = self.signup("brand@aiadd-two.com")
        tok = self.make(c, ["HV-MI-002"], brief=False)
        s, st, _ = c.get("/api/selection/ai-add?s=" + tok)
        self.assertIsNone(st["brief"])
        self.assertEqual(st["n"], aiadd.DEFAULT_N)
        s, r, _ = c.post("/api/selection/ai-add/find", {"token": tok, "answers": {"goal": "awareness", "platforms": ["any"]}, "n": 2})
        self.assertEqual((s, r["reason"]), (400, "missing"))                # the core questions are required
        s, r, _ = c.post("/api/selection/ai-add/find", {"token": tok, "answers": dict(BRIEF, platforms=["any"]), "n": 2})
        self.assertEqual(s, 200, r)
        self.assertTrue(r["brief_saved"])
        self.assertNotIn("HV-MI-002", [p["code"] for p in r["picks"]])
        s, st, _ = c.get("/api/selection/ai-add?s=" + tok)
        self.assertEqual(st["brief"]["answers"]["market"], "SA")            # next time it starts filled in

    def test_03_viewer_and_stranger_cannot(self):
        c, _ = self.signup("owner@aiadd-three.com")
        tok = self.make(c, ["HV-MI-001"])
        other, _ = self.signup("x@aiadd-elsewhere.com")
        s, r, _ = other.get("/api/selection/ai-add?s=" + tok)
        self.assertIn(s, (401, 403, 404))
        s, r, _ = other.post("/api/selection/ai-add/find", {"token": tok, "answers": BRIEF, "n": 2})
        self.assertIn(s, (401, 403, 404))
        self.assertEqual(json.loads(db.selection(token=tok)["codes"]), ["HV-MI-001"])

    def test_04_run_belongs_to_its_selection(self):
        c, _ = self.signup("brand@aiadd-four.com")
        a = self.make(c, ["HV-MI-001"])
        b = self.make(c, ["HV-MI-002"])
        s, r, _ = c.post("/api/selection/ai-add/find", {"token": a, "answers": BRIEF, "n": 2})
        s, x, _ = c.post("/api/selection/ai-add/add", {"token": b, "run": r["run"], "codes": [p["code"] for p in r["picks"]]})
        self.assertEqual((s, x["reason"]), (404, "gone"))
        self.assertEqual(json.loads(db.selection(token=b)["codes"]), ["HV-MI-002"])

    def test_05_low_balance_falls_back_to_plain_search_and_nothing_found_refunds(self):
        c, _ = self.signup("brand@aiadd-five.com")
        tok = self.make(c, ["HV-MI-001"])
        cid = portal.user_by_email("brand@aiadd-five.com")["code_id"]
        portal.spend(cid, portal.balance(cid), "test drain")
        s, r, _ = c.post("/api/selection/ai-add/find", {"token": tok, "answers": BRIEF, "n": 2})
        self.assertEqual((s, r["spent"]), (200, portal.costs()["search"]))   # like the AI shortlist
        portal.grant(cid, 20, "test top-up", actor="test")
        bal = portal.balance(cid)
        # A space nobody posts in on a platform nobody uses: nothing new, money back.
        s, r, _ = c.post("/api/selection/ai-add/find", {"token": tok, "n": 2,
                                                        "answers": dict(BRIEF, platforms=["YouTube"], category=["automotive"])})
        self.assertEqual((s, r["picks"], r["spent"]), (200, [], 0))
        self.assertEqual(portal.balance(cid), bal)

    def test_06_n_is_clamped_and_words_carry_no_figures(self):
        self.assertEqual((aiadd.clamp_n(0), aiadd.clamp_n(500), aiadd.clamp_n("x")), (1, aiadd.MAX_N, aiadd.DEFAULT_N))
        self.assertEqual(aiadd.brief_count({"count": "15"}), 15)
        self.assertEqual(aiadd.brief_count({"count": "other:12 creators"}), 12)
        item = {"chips": ["Women 25–34", "Pharmacist"], "band": "micro",
                "strengths": ["Engagement 4.2%", "A typical post reaches 31% of followers", "Audience 70% in KSA", "Healthcare professional"]}
        words = aiadd.why_words(item, {"target": {"category": "skincare"}}, None)
        self.assertEqual(words, ["Women 25–34", "Pharmacist", "Strong engagement", "Strong views per post"])
        for w in words:
            self.assertFalse(re.search(r"\d%", w))
        floor = aiadd.why_words({"chips": [], "strengths": [], "band": "nano"}, {"target": {}}, None)
        self.assertEqual(floor, ["Nano creator"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
