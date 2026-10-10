"""Fix batch 3 (items 14 and 15): what a client the full analysis is NOT unlocked for may
receive about a creator who has one. Only the creator page's free headline (followers,
platforms, average views, engagement rate, the data date) is real; everything else either
stays on the server or is the server's sample analysis. A granted client gets it all.

Covers the creator endpoint, the locked page's sample, selection scores (the number and
stamp stay, the evidence that quotes the analysis goes), Add more like these, Creators
like this, Find a replacement, content ideas, the Helvy chat tools and discovery.

Same harness as e2e_portal.py (throwaway copy of admin/*.py, empty database, captured
mail, scripted Gemini).

    python3 admin/tests/e2e_portal_fixes3_gating.py
"""
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402  (copies admin/*.py to a temp dir and puts it on the path)

import assistant, db, gating, gemini, guard, ideas, mailer, portal, selstatus, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

# A full analysis whose figures are easy to spot anywhere in a payload.
SECRET_DOC = {"followers": 42000, "er": 4.2, "avg_views": 9100, "avg_likes": 1717.17, "avg_comments": 191.91,
              "fake_followers_pct": 13.37, "fake_likers_pct": 12.21, "updated": "2026-09-30",
              "bio": "Secret bio line", "est_reach": 98765.43,
              "audience": {"countries": [{"code": "SA", "pct": 77.77}, {"code": "EG", "pct": 8.88}],
                           "gender": {"female": 81.11, "male": 18.89},
                           "ages": [{"name": "25-34", "pct": 44.44}],
                           "interests": [{"name": "Secretinterest", "pct": 33.33}]},
              "creator_interests": ["Secrettopic"],
              "growth": [{"month": "2026-08", "followers": 41000}, {"month": "2026-09", "followers": 42000}],
              "brands": [{"name": "Secretbrand", "count": 3}], "hashtags": [{"tag": "#secrettag", "count": 11}],
              "top_posts": [{"url": "https://www.instagram.com/p/SECRETPOST/", "likes": 5555, "comments": 66}]}
MARKERS = ("77.77", "8.88", "13.37", "12.21", "81.11", "44.44", "33.33", "1717.17", "191.91", "98765.43", "5555",
           "Secretbrand", "Secretinterest", "Secrettopic", "secrettag", "SECRETPOST", "Secret bio line",
           "of the audience", "(measured)", "Works in the", "Measured audience")
CODES = ["HV-MI-001", "HV-MI-002", "HV-MD-003", "HV-MD-004", "HV-MI-005"]
ANSWERS = {"goal": "awareness", "platforms": ["Instagram"], "market": "SA", "category": ["skincare"],
           "gender": "Women", "age": "25-34"}
CARD_KEYS = {"code", "name", "tier", "city", "nationality", "interest", "followers", "photo_url", "profiles", "band"}
HEADLINE_KEYS = {"followers", "platforms", "avg_views", "er", "er_platform", "er_followers", "updated"}


class Fixes3Gating(unittest.TestCase):
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
        for code in CODES:
            db.save_analysis(code, SECRET_DOC, "test", platform="Instagram")
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

    def clean(self, payload, where):
        raw = json.dumps(payload, ensure_ascii=False)
        for m in MARKERS:
            self.assertNotIn(m, raw, "%s leaks %r" % (where, m))

    def grant(self, email, code):
        with db.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO analysis_grants (code_id, code, granted_at, granted_by) VALUES (?,?,?,?)",
                         (portal.user_by_email(email)["code_id"], code, db.now(), "test"))

    def selection(self, c, name, codes, brief=True):
        tok = c.post("/api/selection", {"name": name, "codes": codes})[1]["token"]
        if brief:
            s, r, _ = c.post("/api/brief/attach", {"token": tok, "answers": ANSWERS})
            self.assertEqual(s, 200, r)
        return tok

    # ------------------------------------------------------------- creator page --
    def test_01_creator_endpoint_sends_only_the_headline_and_the_sample(self):
        c, _ = self.signup("look@lockco.com")
        s, b, _ = c.get("/api/creator?c=HV-MD-004")
        self.assertEqual(s, 200, b)
        self.assertEqual(set(b), {"ok", "creator", "platforms", "analyses", "requested", "gate", "benchmarks"})
        self.assertEqual(set(b["creator"]), CARD_KEYS)
        self.assertEqual((b["analyses"], b["requested"]), ({}, []))
        g = b["gate"]
        self.assertTrue(set(g) <= {"state", "selections", "headline", "sample", "requested_at", "ready_by"}, g.keys())
        self.assertEqual(set(g["headline"]), HEADLINE_KEYS)
        h = g["headline"]
        self.assertEqual((h["er"], h["avg_views"], h["updated"]), (4.2, 9100, "2026-09-30"))   # the free layer is real
        self.clean(b, "/api/creator (locked)")
        # the sample is a whole analysis, made from the code alone: the same whatever is on file
        x = g["sample"]["analysis"]
        for key in ("top_posts", "sponsored_posts", "fake_followers_pct", "fake_followers_dist", "growth", "brands",
                    "creator_interests", "audience", "audience_likers", "hashtags", "er_dist", "paid_post_performance"):
            self.assertIn(key, x)
        for key in ("countries", "cities", "gender", "ages", "ages_female", "languages", "interests", "brand_affinity", "reachability"):
            self.assertIn(key, x["audience"])
        self.assertEqual(g["sample"], json.loads(json.dumps(gating.sample("HV-MD-004", "Instagram"))))
        db.save_analysis("HV-MD-004", dict(SECRET_DOC, followers=99999, er=1.1), "test", platform="Instagram")
        try:
            self.assertEqual(c.get("/api/creator?c=HV-MD-004")[1]["gate"]["sample"], g["sample"])
        finally:
            db.save_analysis("HV-MD-004", SECRET_DOC, "test", platform="Instagram")
        self.assertEqual(c.get("/api/creator-media?c=HV-MD-004&n=a.jpg")[0], 403)
        # granted: the whole analysis, real
        self.grant("look@lockco.com", "HV-MD-004")
        b = c.get("/api/creator?c=HV-MD-004")[1]
        self.assertEqual(b["gate"]["state"], "unlocked")
        self.assertNotIn("sample", b["gate"])
        raw = json.dumps(b)
        for m in ("77.77", "13.37", "Secretbrand", "5555", "Secret bio line"):
            self.assertIn(m, raw)

    # ----------------------------------------------------------- selection scores --
    def test_02_selection_scores_keep_number_and_stamp_only(self):
        c, _ = self.signup("score@lockco2.com")
        tok = self.selection(c, "Scores", ["HV-MI-001", "HV-MD-004"])
        b = c.get("/api/selection?s=" + tok)[1]
        sc = b["scores"]["HV-MD-004"]
        self.assertIsInstance(sc["score"], int)
        self.assertTrue(sc["tag"])
        self.assertTrue(sc.get("locked"))
        self.assertEqual([p for p in sc["parts"] if "udience" in p["label"]], [])
        self.clean(b["scores"], "selection scores (locked)")
        # the voice/chat view of the selection: number and stamp only
        v = c.get("/api/voice/selection?s=" + tok)[1]
        self.clean(v, "/api/voice/selection")
        # granted: the evidence is back, and the number is the same
        self.grant("score@lockco2.com", "HV-MD-004")
        open_ = c.get("/api/selection?s=" + tok)[1]["scores"]["HV-MD-004"]
        self.assertEqual(open_["score"], sc["score"])
        self.assertFalse(open_.get("locked"))
        self.assertIn("(measured)", json.dumps(open_))
        self.assertIn("of the audience", json.dumps(open_))
        # the redaction itself: measured part and its lines go, free lines stay
        red = gating.redact_score({"score": 70, "tag": "Good fit", "conclusion": "x",
                                   "parts": [{"label": "Engagement", "s": 1}, {"label": "Audience (measured)", "s": 0.9},
                                             {"label": "Audience (assumed 80%)", "s": 0.8}],
                                   "strengths": ["Engagement 4.2%", "Works in the skincare space", "78% of the audience is in Saudi Arabia"],
                                   "watchouts": ["Only 9% of the audience are men", "Small reach (12K followers)"],
                                   "checks": [{"label": "Gender", "text": "81% of the audience are women"},
                                              {"label": "Our campaigns", "text": "2.1% engagement per view in 2 of our campaigns"}]})
        self.assertEqual([p["label"] for p in red["parts"]], ["Engagement", "Audience (assumed 80%)"])
        self.assertEqual(red["strengths"], ["Engagement 4.2%"])
        self.assertEqual(red["watchouts"], ["Small reach (12K followers)"])
        self.assertEqual([x["label"] for x in red["checks"]], ["Our campaigns"])

    # ------------------------------------------------ alike / more / replacements --
    def test_03_look_alikes_more_and_replacements_carry_cards_only(self):
        c, _ = self.signup("alike@lockco3.com")
        tok = self.selection(c, "Alike", ["HV-MI-001", "HV-MD-004"])
        c.post("/api/selection/status", {"token": tok, "code": "HV-MI-001", "status": "approved"})
        roster_keys = set(c.get("/api/roster")[1]["roster"][0])
        for path, body, key in (("/api/selection/alike", {"token": tok, "code": "HV-MD-004"}, "creators"),
                                ("/api/selection/more", {"token": tok, "count": 3}, "added")):
            s, r, _ = c.post(path, body)
            self.assertEqual(s, 200, r)
            self.clean(r, path)
            for item in r.get(key) or []:
                self.assertEqual(set(item) - roster_keys, {"why"}, path)
        c.post("/api/selection/status", {"token": tok, "code": "HV-MD-004", "status": "rejected"})
        s, r, _ = c.post("/api/selection/replace", {"token": tok, "code": "HV-MD-004"})
        self.assertEqual(s, 200, r)
        self.clean(r, "/api/selection/replace")
        for item in r["replacements"]:
            self.assertTrue(set(item) <= roster_keys)
        # the AI shortlist: picks keep score, stamp and the free evidence
        s, r, _ = c.post("/api/brief/run", {"answers": dict(ANSWERS, count="5")})
        self.assertEqual(s, 200, r)
        self.clean({k: r.get(k) for k in ("picks", "alternates", "summary")}, "/api/brief/run")

    # ------------------------------------------------------------- content ideas --
    def test_04_ideas_use_the_analysis_only_when_unlocked(self):
        c, _ = self.signup("idea@lockco4.com")
        cid = portal.user_by_email("idea@lockco4.com")["code_id"]
        tok = self.selection(c, "Ideas", ["HV-MD-004"])
        sel = db.selection(token=tok)
        ctx = ideas.context("HV-MD-004", cid, sel)
        self.assertIsNone(ctx["style"])
        self.clean(ctx, "ideas.context (locked)")
        # a batch HelloVoice drafted from the analysis on the same selection is not served to the locked client
        admin_ctx = ideas.context("HV-MD-004", db.admin_code_id(), sel)
        self.assertIn("81.11", json.dumps(admin_ctx))
        self.assertTrue(admin_ctx["style"])
        batch = [{"format": "Reel", "hook_en": "A", "concept_en": "B", "hook_ar": "ج", "concept_ar": "د"}]
        ideas.keep(ideas.scope_of(sel, cid), "HV-MD-004", batch, ideas.brief_key(admin_ctx))
        b = c.get("/api/ideas?c=HV-MD-004&s=" + tok)[1]
        self.assertEqual(b["ideas"], [])
        # once granted, the client gets the analysis-based batch and the style
        self.grant("idea@lockco4.com", "HV-MD-004")
        self.assertEqual(c.get("/api/ideas?c=HV-MD-004&s=" + tok)[1]["ideas"], batch)
        self.assertTrue(ideas.context("HV-MD-004", cid, sel)["style"])
        # a batch written without the analysis is everyone's
        ideas.keep("c:1", "HV-MI-002", batch, ideas.brief_key({"style": None}))
        self.assertEqual(ideas.kept("c:1", "HV-MI-002", full=False)["ideas"], batch)

    # ------------------------------------------------------------- Helvy's tools --
    def test_05_helvy_tools_answer_free_fields_only(self):
        c, _ = self.signup("chat@lockco5.com")
        cid = portal.user_by_email("chat@lockco5.com")["code_id"]
        ctx = {"code_id": cid}
        self.clean(assistant.t_get_creator(ctx, "HV-MI-002"), "get_creator")
        every = list(assistant.METRICS)
        r = assistant.t_creator_metrics(ctx, codes=["HV-MI-002"], fields=every[:6])
        r2 = assistant.t_creator_metrics(ctx, codes=["HV-MI-002"], fields=every[6:])
        one = dict(r["creators"][0], **r2["creators"][0])
        self.assertEqual((one["engagement_rate_pct"], one["avg_views"], one["followers"]), (4.2, 9100, 42000))
        for f in assistant.LOCKED_METRICS:
            self.assertIsNone(one[f], f)
        self.clean([r, r2], "creator_metrics")
        for m in ("avg_likes", "fake_followers_pct", "audience_share_in_country_pct"):
            self.assertEqual(assistant.t_rank_by_metric(ctx, metric=m)["creators"], [], m)
        self.clean(assistant.t_suggest_shortlist(ctx, goal="awareness", category=["skincare"], count=5), "suggest_shortlist")
        tok = self.selection(c, "Chat", ["HV-MI-002", "HV-MD-003"], brief=False)
        sctx = dict(ctx, selection={"token": tok})
        for m in ("avg_likes", "avg_comments", "fake_followers_pct", "audience_share_in_country_pct"):
            got = assistant.t_selection_stats(sctx, metric=m)
            self.assertEqual(got["breakdown"], [], m)
            self.assertIn("locked", got)
        self.assertEqual(len(assistant.t_selection_stats(sctx, metric="engagement_rate_pct")["breakdown"]), 2)
        # granted: the same tools answer in full
        self.grant("chat@lockco5.com", "HV-MI-002")
        r = assistant.t_creator_metrics(ctx, codes=["HV-MI-002"], fields=["fake_followers_pct", "avg_likes"])
        self.assertEqual((r["creators"][0]["fake_followers_pct"], r["creators"][0]["avg_likes"]), (13.37, 1717.17))

    # ------------------------------------------------------------------ discovery --
    def test_06_discovery_filters_only_on_free_figures_for_a_client(self):
        c, _ = self.signup("find@lockco6.com")
        f = c.get("/api/discover/facets")[1]["facets"]
        self.assertEqual((f["countries"], f["brands"], f["interests"]), ([], [], []))
        allc = c.post("/api/discover", {"filters": {}})[1]["codes"]
        # a locked filter that no creator passes changes nothing for a client…
        self.assertEqual(c.post("/api/discover", {"filters": {"a_country": ["EG"], "a_country_min": 90}})[1]["codes"], allc)
        self.assertEqual(c.post("/api/discover", {"filters": {"real_min": 99}})[1]["codes"], allc)
        # …the free ones still work
        self.assertEqual(c.post("/api/discover", {"filters": {"er_min": 9}})[1]["codes"], [])
        # HelloVoice keeps the full filters
        a = self.admin()
        self.assertIn("SA", a.get("/api/discover/facets")[1]["facets"]["countries"])
        self.assertEqual(a.post("/api/discover", {"filters": {"a_country": ["EG"], "a_country_min": 90}})[1]["codes"], [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
