"""End-to-end tests for HELVi Connect fix batch 8 (2026-10-11, branch portal-fixes-8).

- #39 the sample full analysis: the endpoint serves only the configured creator, anonymised (no name,
  handle, bio, photo, URL, post cover, brand or hashtag), the per-creator gating is unchanged, the
  setting turns it off, and it works for a creator whose own analysis is locked;
- #38 Helvi's new tools (explain_score, compare_creators, campaign_report, roi_walkthrough) and the
  hand-off to the account manager, none of which may carry a price or budget field;
- #41 the working note: step labels are plain actions.

    python3 admin/tests/e2e_portal_fixes8.py
"""
import json
import re
import shutil
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import assistant, benchmarks, db, faq, gating, gemini, guard, mailer, portal, sample_analysis, selstatus, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

SAMPLE = "HV-HCPG-003"
NAME, HANDLE = "Dr. Zzyzx Quillfeather", "zzyzxdoc"
REAL = {
    "platform": "Instagram", "handle": HANDLE, "bio": "Dermatologist. Book at zzyzx-clinic.example. DM for collabs",
    "photo": "media:photo-zzyzx.jpg", "location": "Riyadh, Zzyzx Clinic", "source": "modash", "updated": "2026-10-01",
    "followers": 1340000, "er": 1.9, "avg_likes": 24000, "avg_comments": 410, "avg_views": 88000, "fake_followers_pct": 11.5,
    "followers_change_pct": 1.2, "account_type": "Creator", "sample_posts": 24, "median_views": 70000,
    "audience": {"countries": [{"code": "SA", "pct": 71.0}, {"code": "AE", "pct": 9.0}],
                 "cities": [{"name": "Riyadh", "pct": 30.0}], "gender": {"female": 66.0, "male": 34.0},
                 "ages": [{"name": "25-34", "pct": 41.0}], "interests": [{"name": "Health & Wellness", "pct": 30.0}],
                 "brand_affinity": [{"name": "Nivea", "pct": 12.0}]},
    "growth": [{"month": "2026-08", "followers": 1300000, "avg_likes": 23000}, {"month": "2026-09", "followers": 1340000, "avg_likes": 24000}],
    "top_posts": [{"url": "https://www.instagram.com/p/ABC123/", "thumb": "media:post1.jpg", "date": "2026-09-03", "likes": 50000,
                   "comments": 900, "views": 400000, "caption": "Come to Zzyzx Clinic"}],
    "sponsored_posts": [{"url": "https://www.instagram.com/p/DEF456/", "thumb": "media:post2.jpg", "date": "2026-08-20",
                         "likes": 20000, "comments": 300, "views": 150000, "brand": "Vichy"}],
    "brands": [{"name": "Vichy", "count": 4, "logo": "media:brand-vichy.png"}],
    "hashtags": [{"tag": "#zzyzxclinic", "count": 12.5}, {"tag": "@vichy_ksa", "count": 4.0}],
    "creator_interests": ["Health & Wellness", "Beauty & Cosmetics"],
    "fake_followers_dist": {"buckets": [{"label": "0-5%", "h": 80}], "creator": 0},
}
STEADY = {"followers": 52000, "er": 4.1, "avg_views": 9000, "avg_reel_plays": 21000, "sample_posts": 24, "median_views": 8500, "median_er_on_views": 3.2,
          "views_series": [8000, 8200, 8400, 9000, 8800, 8600, 8700, 8300, 8500, 8900, 9100, 8700]}
BASIC = {"followers": 38000, "er": 3.1, "avg_views": 5000, "basic": True, "sample_posts": 12}
PRICE_WORDS = ("budget", "price", "cpm", "cpe", "cpc", "cost", "fee", "sar ", "rate card", "quote of")


def scrub(obj):
    """The data of a tool result, without its instruction text (which names the no-price rule)."""
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items() if k not in ("note", "instruction")}
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    return obj


def peers(n=40):
    import random
    rnd = random.Random(7)
    return [("Instagram", {"followers": rnd.randint(21000, 90000), "er": rnd.uniform(0.8, 6.0), "avg_views": rnd.randint(2000, 30000),
                           "avg_reel_plays": rnd.randint(2000, 60000), "views_spread": rnd.uniform(0.1, 1.2), "sample_posts": 20})
            for _ in range(n)]


class Fixes8(unittest.TestCase):
    signup = base.Portal.signup
    admin = base.Portal.admin

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        mailer.CAPTURE = True
        views.set_base("")
        selstatus.EMAIL_DELAY = 0
        db.save_tier("HCP", "HC", 0, 0)
        db.upsert_creator({"code": SAMPLE, "name": NAME, "handle": HANDLE, "platform": "Instagram", "followers": 1340000, "city": "Riyadh",
                           "nationality": "Saudi Arabia", "tier": "HCP", "interest": "Dermatology", "photo": None,
                           "profiles": json.dumps([{"platform": "Instagram", "url": "https://www.instagram.com/zzyzxdoc", "followers": 1340000}]),
                           "active": 1, "note": "", "sort": 0})
        db.save_analysis(SAMPLE, REAL, platform="Instagram")
        db.save_analysis("HV-MI-001", STEADY, platform="Instagram")
        db.save_analysis("HV-MI-002", BASIC, platform="Instagram")
        db.save_analysis("HV-MD-004", dict(STEADY, followers=120000, er=2.0, avg_views=15000, avg_reel_plays=30000, views_series=[1000, 30000, 2000, 28000, 500, 25000, 900, 22000, 300, 31000, 700]),
                         platform="Instagram")
        benchmarks.SOURCE = lambda: peers()
        benchmarks.invalidate()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        benchmarks.SOURCE = None
        benchmarks.invalidate()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        db.set_setting("signups_per_ip_day", 1000)
        db.set_setting("signup_mode", "open")
        db.set_setting("sample_analysis_on", True)
        db.set_setting("sample_analysis_code", SAMPLE)
        guard.limiter._hits.clear()
        mailer.OUTBOX.clear()
        gemini.STUB = base.stub

    def selection(self, c, name, codes):
        s, made, _ = c.post("/api/selection", {"name": name, "codes": codes})
        c.post("/api/brief/attach", {"token": made["token"], "answers": {"goal": "awareness", "platforms": ["Instagram"], "market": "SA",
                                                                         "category": ["skincare"], "count": "5"}})
        return made["token"]

    def cid(self, email):
        return portal.user_by_email(email)["code_id"]

    # ------------------------------------------------------------- #39 sample

    def test_01_anonymised_payload(self):
        c, _ = self.signup("s1@glowderma.com")
        s, raw, _ = c.get("/api/analysis/sample")
        self.assertEqual(s, 200, raw)
        txt = json.dumps(raw).lower().replace("@mention", "")
        for w in ("zzyzx", "quillfeather", "dr.", "clinic", "vichy", "nivea", "http", "instagram.com", "media:", ".jpg", "book at",
                  "collab", "hv-hcpg", "modash", "riyadh,", "@"):
            self.assertNotIn(w, txt, w)
        cr = raw["creator"]
        self.assertEqual((cr["code"], cr["name"], cr["photo_url"], cr["city"]), ("SAMPLE", "Sample creator", None, None))
        self.assertTrue(all(p.get("url") is None for p in cr["profiles"]))
        a = raw["analyses"]["Instagram"]
        for k in ("handle", "bio", "photo", "photo_url", "location", "source"):
            self.assertNotIn(k, a)
        self.assertEqual((a["followers"], a["er"], a["avg_views"]), (1340000, 1.9, 88000))      # the numbers are real
        self.assertEqual(a["audience"]["countries"][0], {"code": "SA", "pct": 71.0})
        post = a["top_posts"][0]
        self.assertEqual((post["url"], post["thumb"], post["likes"], post["views"]), ("#", None, 50000, 400000))
        self.assertNotIn("caption", post)
        self.assertRegex(a["sponsored_posts"][0]["brand"], r"^Brand [A-Z]$")
        self.assertEqual([t["tag"] for t in a["hashtags"]], ["#hashtag1", "@mention1"])
        self.assertEqual(raw["gate"], {"state": "unlocked", "sample": True})
        self.assertEqual(raw["label"], "Sample · anonymised creator")

    def test_02_only_the_configured_creator(self):
        c, _ = self.signup("s2@glowderma.com")
        s, a, _ = c.get("/api/analysis/sample?c=HV-MI-001&code=HV-MI-001")        # a creator code in the request is ignored
        self.assertEqual(a["analyses"]["Instagram"]["followers"], 1340000)
        db.set_setting("sample_analysis_code", "HV-MI-001")
        s, b, _ = c.get("/api/analysis/sample")
        self.assertEqual(b["analyses"]["Instagram"]["followers"], 52000)
        # a creator with public numbers only has no full analysis to show: nothing is served
        db.set_setting("sample_analysis_code", "HV-MI-002")
        self.assertEqual(c.get("/api/analysis/sample")[0], 404)
        db.set_setting("sample_analysis_code", "HV-NOPE-1")
        self.assertEqual(c.get("/api/analysis/sample")[0], 404)

    def test_03_gating_unchanged_and_sample_works_when_locked(self):
        c, _ = self.signup("s3@glowderma.com")
        self.selection(c, "Derm", [SAMPLE, "HV-MI-001"])
        s, d, _ = c.get("/api/creator?c=" + SAMPLE)
        self.assertEqual(s, 200)
        self.assertEqual(d["gate"]["state"], "locked")
        self.assertEqual(d["analyses"], {})
        self.assertTrue(d["gate"]["sample_full"])
        blob = json.dumps(d).lower()
        self.assertNotIn("book at", blob)
        self.assertNotIn("zzyzx clinic", blob)
        self.assertNotIn("1340000", json.dumps(d["gate"]["sample"]))               # the layout sample is still invented data
        # while it is locked, the sample endpoint still answers for the configured creator
        s, smp, _ = c.get("/api/analysis/sample")
        self.assertEqual(s, 200)
        self.assertEqual(smp["analyses"]["Instagram"]["followers"], 1340000)
        # another creator's locked analysis is not reachable through it
        s, other, _ = c.get("/api/creator?c=HV-MI-001")
        self.assertEqual(other["analyses"], {})

    def test_04_off_hides_the_button_and_the_data(self):
        c, _ = self.signup("s4@glowderma.com")
        self.selection(c, "Derm", [SAMPLE])
        db.set_setting("sample_analysis_on", False)
        self.assertEqual(c.get("/api/analysis/sample")[0], 404)
        self.assertFalse(c.get("/api/creator?c=" + SAMPLE)[1]["gate"]["sample_full"])
        db.set_setting("sample_analysis_on", True)
        self.assertTrue(c.get("/api/creator?c=" + SAMPLE)[1]["gate"]["sample_full"])
        self.assertEqual(base.Client(self.base).get("/api/analysis/sample")[0], 401)

    def test_04b_blurred_covers_are_served_never_originals(self):
        c, _ = self.signup("s4b@glowderma.com")
        d = sample_analysis.COVERS / SAMPLE
        d.mkdir(parents=True, exist_ok=True)
        (d / "cover-0.jpg").write_bytes(b"\xff\xd8\xff\xe0BLURRED")
        try:
            s, raw, _ = c.get("/api/analysis/sample")
            post = raw["analyses"]["Instagram"]["top_posts"][0]
            self.assertEqual(post["thumb"], "api/analysis/sample/cover?i=0")
            self.assertEqual(post["er"], round((50000 + 900) * 100.0 / 1340000, 2))      # (likes + comments) / followers
            s, body, h = c.get("/api/analysis/sample/cover?i=0")
            self.assertEqual(s, 200)
            self.assertIn("image/jpeg", h.headers.get("Content-Type", ""))
            # no file for another index, an out-of-range index, or a name instead of a number
            self.assertEqual(c.get("/api/analysis/sample/cover?i=1")[0], 404)
            self.assertEqual(c.get("/api/analysis/sample/cover?i=99")[0], 404)
            self.assertEqual(c.get("/api/analysis/sample/cover?i=../post-1")[0], 404)
            # a cover is only served for the configured creator, and nothing when the sample is off
            db.set_setting("sample_analysis_code", "HV-MI-001")
            self.assertEqual(c.get("/api/analysis/sample/cover?i=0")[0], 404)
            db.set_setting("sample_analysis_code", SAMPLE)
            db.set_setting("sample_analysis_on", False)
            self.assertEqual(c.get("/api/analysis/sample/cover?i=0")[0], 404)
        finally:
            (d / "cover-0.jpg").unlink()

    def test_05_settings_card(self):
        a = self.admin()
        s, body, _ = a.get("/portal?tab=settings")
        self.assertIn("Sample full analysis", body)
        self.assertIn("sample_analysis_code", body)
        form = {"signup_mode": "open", "back": "/portal?tab=settings", "sample_analysis_code": "hv-mi-001"}
        a.req("POST", "/portal/settings", form=form)                                 # checkbox absent: off
        self.assertEqual(db.setting("sample_analysis_code"), "HV-MI-001")
        self.assertFalse(sample_analysis.config()[0])
        a.req("POST", "/portal/settings", form=dict(form, sample_analysis_on="on", sample_analysis_code="not a code!"))
        self.assertEqual(sample_analysis.config(), (True, SAMPLE))                    # junk falls back to the default
        a.req("POST", "/portal/settings", form={"signup_mode": "open", "back": "/portal?tab=settings"})
        self.assertTrue(sample_analysis.config()[0])                                  # a form without the card changes nothing

    # ----------------------------------------------------- #38 explain / compare

    def test_10_explain_score(self):
        cid = db.admin_code_id()
        got = assistant.t_explain_score({"code_id": cid}, "HV-MI-001")
        self.assertIsNotNone(got["score"])
        eng = next(p for p in got["parts"] if p["part"] == "Engagement")
        self.assertEqual(eng["compared_with"], 40)
        self.assertTrue(0 <= eng["percentile"] <= 100)
        self.assertIn("similar", eng["reading"])
        self.assertTrue(any(p["part"] == "Steady views" for p in got["parts"]))
        self.assertEqual(sum(p["counts_for_pct"] for p in got["parts"]) in range(98, 103), True)
        self.assertIn(got["confidence"]["level"], ("low", "medium", "high"))
        self.assertIsInstance(got["missing"], list)
        blob = json.dumps(scrub(got)).lower()
        for w in PRICE_WORDS:
            self.assertNotIn(w, blob, w)
        self.assertIn("error", assistant.t_explain_score({"code_id": cid}, "HV-NOPE-1"))
        none = assistant.t_explain_score({"code_id": cid}, "HV-MD-003")            # no analysis on file
        self.assertIsNone(none["score"])
        self.assertTrue(none["missing"])

    def test_11_explain_hides_locked_parts_for_a_client(self):
        c, _ = self.signup("x1@glowderma.com")
        cid = self.cid("x1@glowderma.com")
        mine = assistant.t_explain_score({"code_id": cid}, "HV-MI-001")
        admin = assistant.t_explain_score({"code_id": db.admin_code_id()}, "HV-MI-001")
        self.assertTrue(any(p["part"] == "Steady views" for p in admin["parts"]))
        self.assertFalse(any(p["part"] == "Steady views" for p in mine["parts"]))
        self.assertTrue(any("full analysis" in m for m in mine["missing"]))
        gating.request  # noqa: B018  (the module under test is untouched)
        # once the team opens the analysis for this client, the part shows
        with db.connect() as conn:
            conn.execute("INSERT INTO analysis_grants (code_id, code, granted_at, granted_by) VALUES (?,?,?,?)",
                         (cid, "HV-MI-001", int(time.time()), "test"))
        self.assertTrue(any(p["part"] == "Steady views" for p in assistant.t_explain_score({"code_id": cid}, "HV-MI-001")["parts"]))

    def test_12_compare_creators(self):
        cid = db.admin_code_id()
        got = assistant.t_compare_creators({"code_id": cid}, ["HV-MI-001", "HV-MD-004", "HV-MI-002", "HV-MI-005"])
        self.assertEqual(len(got["creators"]), 3)                                    # at most three
        self.assertIsInstance(got["recommendation"], str)
        self.assertIn("HV-MI-001", got["recommendation"] + json.dumps(got["creators"]))
        for r in got["creators"]:
            self.assertIn("parts", r)
        blob = json.dumps(scrub(got)).lower()
        for w in PRICE_WORDS:
            self.assertNotIn(w, blob, w)
        self.assertIn("error", assistant.t_compare_creators({"code_id": cid}, ["HV-MI-001"]))
        two = assistant.t_compare_creators({"code_id": cid}, ["HV-MI-001", "HV-MD-004"])
        self.assertGreater([r for r in two["creators"] if r["code"] == "HV-MI-001"][0]["score"] or 0, 0)
        self.assertIn("(HV-MI-001)", two["recommendation"])

    def test_13_uses_the_open_selection_score(self):
        cid = db.admin_code_id()
        ctx = {"code_id": cid, "selection": {"token": "x", "objective": "Traffic",
               "details": {"HV-MI-001": {"score": 61, "tag": "Good fit", "platform": "Instagram", "limited_data": False, "basic": False,
                                         "confidence": {"level": "high", "posts": 24, "peers_n": 40},
                                         "parts": [{"key": "engagement", "label": "Engagement vs similar creators", "s": 0.8, "w": 1.0, "src": "peers", "n": 40}]}}}}
        got = assistant.t_explain_score(ctx, "HV-MI-001")
        self.assertEqual((got["score"], got["scored_for"], got["fit"]), (61, "Traffic", "Good fit"))
        self.assertEqual(got["parts"][0]["percentile"], 80)
        self.assertEqual(got["confidence"]["level"], "high")

    # ------------------------------------------- #38 campaign report, walkthrough

    def test_20_campaign_report_is_the_clients_own(self):
        c, _ = self.signup("camp8@glowderma.com")
        cid = self.cid("camp8@glowderma.com")
        self.assertIn("error", assistant.t_campaign_report({"code_id": cid}))
        other, _ = self.signup("camp8b@glowderma.com")
        ocid = self.cid("camp8b@glowderma.com")
        mine = db.create_campaign("Ramadan Skin", "Glow", cid, None, "Instagram", codes=["HV-MI-001"])
        theirs = db.create_campaign("Other Client Launch", "Other", ocid, None, "Instagram", codes=["HV-MI-002"])
        db.save_campaign(mine, status="live", starts_at=int(time.time()) - 86400 * 5, ends_at=int(time.time()) + 86400 * 20)
        db.save_campaign(theirs, status="live", starts_at=int(time.time()) - 86400, ends_at=int(time.time()) + 86400 * 20)
        got = assistant.t_campaign_report({"code_id": cid})
        self.assertEqual(got["campaign"], "Ramadan Skin")
        self.assertIn("so_far", got)
        self.assertIsInstance(got["what_to_do_next"], list)
        blob = json.dumps(scrub(got)).lower()
        self.assertNotIn("other client", blob)
        for w in PRICE_WORDS:
            self.assertNotIn(w, blob, w)
        # asking for someone else's campaign by token still returns only the client's own
        tok = db.campaign(theirs)["token"]
        again = assistant.t_campaign_report({"code_id": cid}, tok)
        self.assertEqual(again["campaign"], "Ramadan Skin")
        # a draft is never shown
        db.save_campaign(mine, status="draft")
        self.assertIn("error", assistant.t_campaign_report({"code_id": cid}))

    def test_21_roi_walkthrough(self):
        c, _ = self.signup("roi8@glowderma.com")
        tok = self.selection(c, "Walk", ["HV-MI-001", "HV-MD-004"])
        sel = db.selection(token=tok)
        ctx = {"code_id": self.cid("roi8@glowderma.com"), "selection": {"token": tok, "objective": "Awareness"}}
        got = assistant.t_roi_walkthrough(ctx, None, ["Instagram"], 0)
        self.assertEqual(len(got["walkthrough"]), 6)
        self.assertIn("selection_quality", got["live_comparison"])
        blob = json.dumps(scrub(got)).lower()
        for w in ("budget", "cpm", "cost per"):
            self.assertNotIn(w, blob, w)
        self.assertIsNotNone(sel)
        self.assertIn("roi_walkthrough", assistant.CLIENT_TOOLS)

    # ------------------------------------------------------------- #38 handoff

    def test_30_handoff_event(self):
        db.set_setting("notify_emails", ["am@hellovoice.co.uk"])
        db.set_setting("notify_events", ["quote"])                 # a team that saved its list before "handoff" existed
        c, _ = self.signup("hand8@glowderma.com")
        tok = self.selection(c, "Hand", ["HV-MI-001"])
        s, raw, _ = c.post("/api/chat/stream", {"message": "How much does this cost for 3 creators?", "selection": tok})
        done = [json.loads(x) for x in raw.splitlines() if x.strip()][-1]
        self.assertEqual(done["t"], "done")
        self.assertEqual(done["handoff"], {"reason": "Asked about prices"})                        # the FAQ answer carries the button
        mailer.OUTBOX.clear()
        s, r, _ = c.post("/api/chat/handoff", {"thread": done["thread"], "selection": tok, "reason": "Wants a discount on 3 creators"})
        self.assertEqual((s, r["ok"]), (200, True), r)
        self.assertIn("one working day", r["message"])
        for _i in range(50):
            if mailer.OUTBOX:
                break
            time.sleep(0.05)
        self.assertEqual(len(mailer.OUTBOX), 1)
        mail = mailer.OUTBOX[0]
        self.assertEqual(mail["to"], "am@hellovoice.co.uk")
        self.assertIn("Account manager request", mail["subject"])
        self.assertIn("How much does this cost for 3 creators?", mail["text"])                 # the chat snippet, from storage
        self.assertIn("/selection/#s=" + tok, mail["text"])                                  # and the open selection's link
        self.assertIn("Wants a discount", mail["text"])

    def test_31_handoff_ignores_a_forged_thread_and_selection(self):
        db.set_setting("notify_emails", ["am@hellovoice.co.uk"])
        db.set_setting("notify_events", ["handoff"])
        a, _ = self.signup("hand9a@glowderma.com")
        b, _ = self.signup("hand9b@glowderma.com")
        tok = self.selection(a, "Private", ["HV-MI-001"])
        s, raw, _ = a.post("/api/chat/stream", {"message": "secret plan for the launch", "selection": tok})
        thread = [json.loads(x) for x in raw.splitlines() if x.strip()][-1]["thread"]
        mailer.OUTBOX.clear()
        s, r, _ = b.post("/api/chat/handoff", {"thread": thread, "selection": tok, "reason": "x"})
        self.assertTrue(r["ok"])
        time.sleep(0.4)
        text = " ".join(m["text"] for m in mailer.OUTBOX)
        self.assertNotIn("secret plan", text)
        self.assertNotIn(tok, text)

    def test_32_model_calls_the_handoff_tool(self):
        base_stub = base.stub

        def stub(body):
            last = body["contents"][-1]["parts"][0]
            if "functionResponse" not in last and "discount" in last.get("text", ""):
                return {"candidates": [{"content": {"parts": [{"functionCall": {"name": "handoff_to_manager", "args": {"reason": "discount"}}}]}}],
                        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}}
            if "functionResponse" not in last and "find skincare" in last.get("text", ""):
                return {"candidates": [{"content": {"parts": [{"functionCall": {"name": "search_creators", "args": {"query": "skin"}}}]}}],
                        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}}
            return base_stub(body)
        gemini.STUB = stub
        c, _ = self.signup("hand10@glowderma.com")
        s, raw, _ = c.post("/api/chat/stream", {"message": "Can I get a discount on five creators?"})
        evs = [json.loads(x) for x in raw.splitlines() if x.strip()]
        done = evs[-1]
        self.assertEqual(done["handoff"], {"reason": "discount"})
        s, raw, _ = c.post("/api/chat/stream", {"message": "find skincare creators in riyadh"})
        steps = [e["text"] for e in [json.loads(x) for x in raw.splitlines() if x.strip()] if e["t"] == "step"]
        self.assertEqual(steps, ["Searching creators"])
        # a normal answer carries no button
        s, raw, _ = c.post("/api/chat/stream", {"message": "campaign for skincare in KSA"})
        self.assertIsNone([json.loads(x) for x in raw.splitlines() if x.strip()][-1].get("handoff"))

    def test_33_tools_are_listed_and_free(self):
        for name in ("explain_score", "compare_creators", "campaign_report", "roi_walkthrough", "handoff_to_manager"):
            self.assertIn(name, assistant.CLIENT_TOOLS)
            self.assertIn(name, [d["name"] for d in assistant.declarations("client")])
        self.assertNotIn("handoff_to_manager", [d["name"] for d in assistant.declarations("admin")])
        import knowledge
        for name in ("explain_score", "compare_creators", "campaign_report", "roi_walkthrough", "Send this to my account manager"):
            self.assertIn(name, knowledge.KNOWLEDGE)

    def test_34_step_labels_are_plain_actions(self):
        for tool, label in assistant.STEP_LABEL.items():
            self.assertFalse(re.search(r"\d|_", label), label)
            self.assertNotEqual(label.lower(), tool)
            self.assertLess(len(label.split()), 7, label)


if __name__ == "__main__":
    unittest.main(verbosity=2)
