"""End-to-end tests for HELVY Connect phases C + D: the AI-free rule during an active
campaign, access-code links to email accounts, the tour reward, the ROI Calculator,
"Add more like these", "Creators like this", Helvy's knowledge and no-price rule, and
the sign-in code email.

Same harness as e2e_portal.py (a throwaway copy of admin/*.py, an empty database,
captured mail, a scripted Gemini), so it never touches catalogue.db or the network.

    python3 admin/tests/e2e_portal_cd.py
"""
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402  (copies admin/*.py to a temp dir and puts it on the path)
from e2e_portal import Client  # noqa: E402

import assistant, auth, codelinks, db, faq, gemini, guard, helvy_kb, mailer, occasions, portal, roi, selstatus, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

DAY = 86400


class CD(unittest.TestCase):
    signup = base.Portal.signup
    admin = base.Portal.admin
    skip_cooldown = base.Portal.skip_cooldown

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        mailer.CAPTURE = True
        gemini.STUB = base.stub
        views.set_base("")
        selstatus.EMAIL_DELAY = 0
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

    def approve(self, c, token, code):
        s, b, _ = c.post("/api/selection/status", {"token": token, "code": code, "status": "approved"})
        self.assertTrue(b.get("ok"), b)

    # ------------------------------------------------- AI free during a campaign --
    def test_01_ai_is_free_from_campaign_start_to_end_plus_30_days(self):
        c, _ = self.signup("free@sanofi-test.com")
        u = portal.user_by_email("free@sanofi-test.com")
        cid = u["code_id"]
        self.assertIsNone(portal.ai_free(cid))
        self.assertEqual(portal.charge(cid, "chat", "t")[1], 1)                    # paid before any campaign
        k = db.create_campaign("Ramadan", "Sanofi", cid)
        now = db.now()
        db.save_campaign(k, status="live", starts_at=now - 2 * DAY, ends_at=now + 5 * DAY)
        before = portal.balance(cid)
        ok, cost, bal = portal.charge(cid, "brief", "t")
        self.assertEqual((ok, cost, bal), (True, 0, before))                       # free, nothing recorded
        me = c.get("/api/me")[1]
        self.assertEqual(me["ai_free"]["campaign"], "Ramadan")
        # ended 20 days ago: still inside the 30-day tail
        db.save_campaign(k, status="ended", starts_at=now - 60 * DAY, ends_at=now - 20 * DAY)
        self.assertEqual(portal.charge(cid, "replace", "t")[1], 0)
        # ended 31 days ago: credits again
        db.save_campaign(k, starts_at=now - 90 * DAY, ends_at=now - 31 * DAY)
        self.assertEqual(portal.charge(cid, "replace", "t")[1], 2)
        # a draft never counts
        db.save_campaign(k, status="draft", starts_at=now - DAY, ends_at=now + DAY)
        self.assertIsNone(portal.ai_free(cid))
        self.assertEqual(portal.price_of(cid, "more"), 3)

    # ------------------------------------------------ access codes -> accounts --
    def test_02_shared_code_links_to_an_email_account_and_keeps_working(self):
        code_id = db.create_code(auth.hash_code("Northwind Shared 7"), "ed 7", "Northwind (shared)", code_plain="Northwind Shared 7")
        sid = db.save_selection(None, "Northwind Q4", ["HV-MI-001", "HV-MI-002"], {}, None, None, None, code_id)
        sel = db.selection(sid)
        a = self.admin()
        s, page, _ = a.get("/portal?tab=codes")
        self.assertEqual(s, 200)
        self.assertIn("Northwind (shared)", page)
        self.assertIn("Northwind Q4", page)
        # invite before the account exists: it waits for the first sign-in
        s, _, r = a.req("POST", "/portal/code/link", form={"code_id": code_id, "email": "sara@northwind-test.com", "back": "/portal?tab=codes"})
        self.assertEqual(s, 303)
        self.assertIn("waiting for first sign-in", a.get("/portal?tab=codes")[1])
        c, _ = self.signup("sara@northwind-test.com")
        u = portal.user_by_email("sara@northwind-test.com")
        self.assertIn(code_id, portal.team_codes(u["code_id"]))
        self.assertTrue(portal.owns(u["code_id"], code_id))
        # she owns the code's selection now: she can approve
        s, b, _ = c.post("/api/selection/status", {"token": sel["token"], "code": "HV-MI-001", "status": "approved"})
        self.assertTrue(b.get("ok"), b)
        # and the code is untouched: still live, its link still opens with it
        self.assertTrue(db.code_state(db.get_code(code_id))[0])
        g = Client(self.base)
        s, b, _ = g.post("/api/unlock", {"code": "Northwind Shared 7", "link": "s:" + sel["token"], "lite": True})
        self.assertTrue(b.get("ok"), b)
        # an account that already exists is linked at once
        self.signup("omar@northwind-test.com")
        row, err = codelinks.invite(code_id, "omar@northwind-test.com", "boss")
        self.assertIsNone(err)
        self.assertIsNotNone(row["user_code_id"])
        self.assertEqual(codelinks.invite(u["code_id"], "x@y-test.com")[1], "not_shared")   # a personal row is not a shared code

    # -------------------------------------------------------------------- tour --
    def test_03_tour_pays_five_credits_once(self):
        c, _ = self.signup("tour@novartis-test.com")
        self.assertIsNone(c.get("/api/me")[1]["tour"])
        self.assertEqual(c.post("/api/tour", {"action": "offered"})[1]["tour"], "offered")
        bal = c.get("/api/me")[1]["credits"]
        r = c.post("/api/tour", {"action": "done"})[1]
        self.assertEqual((r["earned"], r["credits"]), (5, bal + 5))
        r = c.post("/api/tour", {"action": "done"})[1]                              # replay: no second reward
        self.assertEqual(r["earned"], 0)
        self.assertEqual(c.post("/api/tour", {"action": "later"})[1]["tour"], "done")
        u = portal.user_by_email("tour@novartis-test.com")
        reasons = [l["reason"] for l in portal.ledger(u["code_id"])]
        self.assertEqual(sum(1 for x in reasons if x.startswith("Tour reward")), 1)
        self.assertEqual(Client(self.base).post("/api/tour", {"action": "done"})[0], 401)

    # --------------------------------------------------------------------- ROI --
    def test_04_roi_calculator_mix_selection_save_and_versus(self):
        c, _ = self.signup("roi@bayer-test.com")
        r = c.post("/api/roi/estimate", {"goal": "awareness", "budget": 120000, "platforms": ["Instagram", "TikTok"],
                                         "mix": {"mid": 3, "micro": 6}})[1]["result"]
        self.assertTrue(r["estimate"])
        self.assertIn(r["verdict"]["grade"], ("good", "moderate", "low"))
        self.assertEqual([f["key"] for f in r["figures"]], ["reach", "views", "impressions", "frequency", "cpm"])
        self.assertEqual(r["posts"], 18)                                            # 9 creators x 2 platforms
        # fix batch 4: every figure as a range around the estimate; no advice line, no sources sent
        for f in r["figures"]:
            self.assertLessEqual(f["range"][0], f["value"])
            self.assertGreaterEqual(f["range"][1], f["value"])
        self.assertNotIn("advice", r)
        self.assertNotIn("sources", r)
        self.assertNotIn("Kolsquare", json.dumps(r))
        # the verdict follows the client's budget: a tiny budget is good value, a huge one is not
        cheap = roi.estimate("engagement", 1000, ["Instagram"], mix={"micro": 10})
        dear = roi.estimate("engagement", 5000000, ["Instagram"], mix={"micro": 10})
        self.assertEqual((cheap["verdict"]["grade"], dear["verdict"]["grade"]), ("good", "low"))
        t = roi.estimate("traffic", 60000, ["TikTok"], mix={"mid": 2, "micro": 6})
        self.assertEqual([f["key"] for f in t["figures"]], ["clicks", "ctr", "landing", "cpc"])
        # a selection: its own creators, one post per platform they are on
        tok = self.sel(c, "Derm launch", ["HV-MI-001", "HV-MD-003", "HV-MI-002"])
        self.approve(c, tok, "HV-MI-001")
        self.approve(c, tok, "HV-MD-003")
        r = c.post("/api/roi/estimate", {"token": tok, "goal": "engagement", "budget": 50000, "platforms": ["Instagram", "TikTok"]})[1]["result"]
        self.assertEqual(r["creators"], 2)                                         # the approved ones
        s, b, _ = c.post("/api/roi/save", {"token": tok, "goal": "engagement", "budget": 50000, "platforms": ["Instagram", "TikTok"]})
        self.assertTrue(b["ok"], b)
        saved = c.get("/api/roi/saved?s=" + tok)[1]["saved"]
        self.assertEqual(saved["goal"], "engagement")
        # another client cannot read it
        o, _ = self.signup("other@roche-test.com")
        self.assertEqual(o.get("/api/roi/saved?s=" + tok)[0], 404)
        # after the campaign: estimate vs actual
        u = portal.user_by_email("roi@bayer-test.com")
        sel = db.selection(token=tok)
        k = db.create_campaign("Derm launch live", "Bayer", u["code_id"], selection_id=sel["id"])
        db.save_campaign(k, status="live", starts_at=db.now() + 60, ends_at=db.now() + 30 * DAY)
        db.add_content(k, {"url": "https://x/p/roi1", "code": "HV-MI-001", "platform": "Instagram", "kind": "reel", "views": 9000, "likes": 400, "comments": 20})
        items = c.get("/api/roi/vs")[1]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["campaign"], "Derm launch live")
        self.assertTrue(all(row["sig"]["grade"] in ("good", "moderate", "low") for row in items[0]["rows"]))
        self.assertEqual(o.get("/api/roi/vs")[1]["items"], [])

    # ------------------------------------------------------- AI on selections --
    def test_05_add_more_like_these_and_creators_like_this(self):
        c, _ = self.signup("more@astra-test.com")
        u = portal.user_by_email("more@astra-test.com")
        # every creator rejected: nothing to learn from, nothing charged
        t0 = self.sel(c, "Nope", ["HV-MI-005"])
        c.post("/api/selection/status", {"token": t0, "code": "HV-MI-005", "status": "rejected"})
        bal = portal.balance(u["code_id"])
        r = c.post("/api/selection/more", {"token": t0, "count": 2})[1]
        self.assertEqual((r["added"], portal.balance(u["code_id"])), ([], bal))
        self.assertIn("Approve a few creators", r["message"])
        tok = self.sel(c, "Skin", ["HV-MI-001", "HV-MD-004"])
        self.approve(c, tok, "HV-MI-001")
        bal = portal.balance(u["code_id"])
        s, r, _ = c.post("/api/selection/more", {"token": tok, "count": 2, "note": "Riyadh-based", "chips": ["under100k", "nope"]})
        self.assertEqual(s, 200, r)
        if r["added"]:
            self.assertEqual(r["spent"], 3)
            self.assertEqual(portal.balance(u["code_id"]), bal - 3)
            added = [x["code"] for x in r["added"]]
            sel = db.selection(token=tok)
            self.assertTrue(set(added) <= set(json.loads(sel["codes"])))
            st = selstatus.of(sel["id"])
            self.assertTrue(all(st.get(a, {"s": "review"})["s"] == "review" for a in added))   # they arrive Under review
            self.assertTrue(all(x["why"] for x in r["added"]))
        else:
            self.assertEqual(portal.balance(u["code_id"]), bal)                    # refunded when nobody fits
        # Creators like this: 2 credits, reopening is free, "again" costs again
        bal = portal.balance(u["code_id"])
        r = c.post("/api/selection/alike", {"token": tok, "code": "HV-MI-001"})[1]
        self.assertTrue(r["ok"], r)
        if r["creators"]:
            self.assertEqual(portal.balance(u["code_id"]), bal - 2)
            r2 = c.post("/api/selection/alike", {"token": tok, "code": "HV-MI-001"})[1]
            self.assertEqual(r2["spent"], 0)
            self.assertEqual([x["code"] for x in r2["creators"]], [x["code"] for x in r["creators"]])
        # a colleague (same domain) can look but not add
        col, _ = self.signup("col@astra-test.com")
        s, b, _ = col.post("/api/selection/more", {"token": tok})
        self.assertEqual((s, b["reason"]), (403, "not_owner"))
        # free during an active campaign
        k = db.create_campaign("Live one", "Astra", u["code_id"])
        db.save_campaign(k, status="live", starts_at=db.now() - DAY, ends_at=db.now() + DAY)
        bal = portal.balance(u["code_id"])
        c.post("/api/selection/alike", {"token": tok, "code": "HV-MD-004"})
        self.assertEqual(portal.balance(u["code_id"]), bal)
        p = c.get("/api/selection?s=" + tok)
        payload = p[1] if isinstance(p[1], dict) else {}
        if payload.get("ok"):
            self.assertEqual((payload["more_cost"], payload["alike_cost"], payload["replace_cost"]), (0, 0, 0))

    # ------------------------------------------------------------------ Helvy --
    def test_06_helvy_knowledge_and_no_prices(self):
        decl = [d["name"] for d in assistant.declarations("client")]
        self.assertNotIn("price_bands", decl)
        for t in ("campaign_results", "occasions", "my_decisions", "roi_estimate"):
            self.assertIn(t, decl)
        prompt = assistant.system_prompt("client", {"user": {"name": "Sara"}})
        self.assertIn("You are Helvy", prompt)
        self.assertIn("NO PRICES", prompt)
        self.assertIn("Mawthooq", prompt)
        c = db.creator("HV-MI-001")
        self.assertNotIn("price_sar", assistant.creator_view(c))
        self.assertNotIn("SAR", faq.answer("How much does it cost?")["reply"])
        up = occasions.upcoming(today=__import__("datetime").date(2027, 1, 1), months=3)
        names = [o["name"] for o in up]
        self.assertIn("Ramadan", names)
        self.assertTrue(all("brief_by" in o for o in up))
        # campaign results: another client's campaign is never named, only aggregated
        a, _ = self.signup("res@pfizer-test.com")
        b_, _ = self.signup("res@gsk-test.com")
        ua, ub = portal.user_by_email("res@pfizer-test.com"), portal.user_by_email("res@gsk-test.com")
        for i in range(3):
            k = db.create_campaign("Pfizer secret %d" % i, "Pfizer", ua["code_id"])
            db.save_campaign(k, status="live", platform="Instagram")
            db.add_content(k, {"url": "https://x/p/res%d" % i, "code": "HV-MI-001", "platform": "Instagram", "kind": "reel", "views": 1000 + i, "likes": 50})
        helvy_kb._cache.update(rows=None)
        mine = json.dumps(helvy_kb.campaign_results(ua["code_id"]))
        theirs = json.dumps(helvy_kb.campaign_results(ub["code_id"]))
        self.assertIn("Pfizer secret", mine)
        self.assertNotIn("Pfizer secret", theirs)
        self.assertNotIn("Pfizer", theirs)
        self.assertTrue(helvy_kb.campaign_results(ub["code_id"])["aggregates"])     # 3+ campaigns: an anonymous median
        db.set_setting("case_study_campaigns", [k])
        self.assertIn("Pfizer secret 2", json.dumps(helvy_kb.campaign_results(ub["code_id"])))
        db.set_setting("case_study_campaigns", [])
        # decisions: the client's own approvals and reasons
        tok = self.sel(a, "Taste", ["HV-MI-001", "HV-MI-002"])
        self.approve(a, tok, "HV-MI-001")
        a.post("/api/selection/status", {"token": tok, "code": "HV-MI-002", "status": "rejected", "reason": "audience"})
        d = helvy_kb.decisions(ua["code_id"])
        self.assertEqual(d["reject_reasons"], {"Audience": 1})
        self.assertEqual(helvy_kb.decisions(ub["code_id"])["selections"], [])

    def test_07_budget_question_in_chat_is_an_instant_free_roi_card(self):
        c, _ = self.signup("chatroi@nahdi-test.com")
        before = c.get("/api/me")[1]["credits"]
        s, raw, _ = c.post("/api/chat/stream", {"message": "What can SAR 60,000 do on TikTok if we want clicks?"})
        lines = [json.loads(x) for x in raw.splitlines() if x.strip()]
        done = [x for x in lines if x["t"] == "done"][0]
        self.assertEqual(done["roi"]["goal"], "traffic")
        self.assertEqual(done["roi"]["platforms"], ["TikTok"])
        self.assertEqual(done["roi"]["budget"], 60000)
        self.assertEqual(before, c.get("/api/me")[1]["credits"])
        self.assertIsNone(roi.from_text("Hello there"))

    # ------------------------------------------------------------------- email --
    def test_08_sign_in_code_email(self):
        subject, text, html = mailer.otp_message("482913", 10, to="sara@northwind-test.com")
        self.assertEqual(subject, "Your HELVY Connect sign-in code: 482913")
        self.assertIn("482913", text)
        self.assertIn("Your HELVY Connect code is 482913", html)                   # preheader
        self.assertIn(">482913<", html)                                             # copyable, no spaces between digits
        self.assertIn("Expires in 10 minutes", html)
        self.assertIn("never asks for this code by phone or chat", html)
        self.assertIn("A BlueHolding Company", html)
        self.assertIn("Al-Olaya, Riyadh", html)
        self.assertIn("v:roundrect", html)                                          # Outlook button
        imgs = __import__("re").findall(r"<img [^>]*>", html)
        self.assertEqual(len(imgs), 3)
        for img in imgs:
            self.assertIn('src="https://influencer-catalogue.hellovoice.co.uk/', img)
            self.assertIn(".png", img)
            self.assertIn("width=", img)
            self.assertIn("alt=", img)
        self.assertNotIn("7fa8ff", html)                                            # no temporary blue
        for f in ("assets/brand/email/helvy-connect-on-ink-480.png", "assets/brand/email/helvy-still-192.png",
                  "assets/brand/email/hellovoice-white-240.png"):
            self.assertTrue((Path(__file__).resolve().parents[2] / f).is_file(), f)

    # ------------------------------------------------------------- admin pages --
    def test_09_admin_pages_render(self):
        a = self.admin()
        for path in ("/portal?tab=codes", "/portal?tab=settings"):
            s, body, _ = a.get(path)
            self.assertEqual(s, 200, path)
        s, _, _ = a.req("POST", "/portal/settings", form={"case_study_campaigns": "3, x, 9", "signup_mode": "open", "back": "/portal?tab=settings"})
        self.assertEqual(db.setting("case_study_campaigns"), [3, 9])


if __name__ == "__main__":
    unittest.main(verbosity=1)
