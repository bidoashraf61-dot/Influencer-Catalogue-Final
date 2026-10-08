"""End-to-end tests for HELVY Connect portal v3: the bell, the profile page and its
credit rewards, invites, analysis gating and selection status.

Same harness as e2e_portal.py (a throwaway copy of admin/*.py, an empty database,
captured mail, a scripted Gemini), so it never touches catalogue.db or the network.

    python3 admin/tests/e2e_portal_v3.py
"""
import json
import shutil
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402  (copies admin/*.py to a temp dir and puts it on the path)
from e2e_portal import Client  # noqa: E402

import db, gemini, guard, inbox, mailer, portal, rewards, selstatus, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

# Real-looking figures that must never reach a client the analysis is not unlocked for.
SECRET_DOC = {"followers": 42000, "er": 4.2, "avg_views": 9100, "fake_followers_pct": 13.37,
              "audience": {"countries": [{"code": "SA", "pct": 77.77}, {"code": "EG", "pct": 8.88}],
                           "gender": {"female": 81.11, "male": 18.89},
                           "ages": [{"name": "25-34", "pct": 44.44}]},
              "brands": [{"name": "Secretbrand"}], "top_posts": [{"url": "https://x/p/1", "likes": 5555}]}
LOCKED_MARKERS = ("77.77", "13.37", "81.11", "44.44", "Secretbrand", "5555")


class V3(unittest.TestCase):
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

    def user(self, email):
        return portal.user_by_email(email)

    def bell(self, c, limit=5):
        s, b, _ = c.get("/api/notifications?limit=%d" % limit)
        self.assertEqual(s, 200, b)
        return b

    # ------------------------------------------------------------ the bell --
    def test_01_bell_rings_for_hellovoice_status_changes_and_marks_read(self):
        c, _ = self.signup("bell@novartis.com")
        mailer.OUTBOX.clear()                                            # the sign-in code is the only client email
        token = c.post("/api/selection", {"name": "Ramadan", "codes": ["HV-MI-001", "HV-MI-002"]})[1]["token"]
        self.assertEqual(self.bell(c)["unread"], 0)
        a = self.admin()
        sel = db.selection(token=token)
        for code in ("HV-MI-001", "HV-MI-002"):
            s, r, _ = a.req("POST", "/selections/status", form={"id": sel["id"], "code": code, "status": "approved"})
            self.assertTrue(r["ok"], r)
        b = self.bell(c)
        self.assertEqual(b["unread"], 1)                                # bundled: one line for both
        self.assertEqual(b["items"][0]["title"], "HelloVoice approved 2 creators")
        self.assertIn("Ramadan", b["items"][0]["rest"])
        # Unavailable is its own line
        a.req("POST", "/selections/status", form={"id": sel["id"], "code": "HV-MI-002", "status": "unavailable", "note": "Booked those dates"})
        b = self.bell(c)
        self.assertEqual(b["unread"], 2)
        self.assertEqual(b["items"][0]["kind"], "unavailable")
        self.assertEqual(b["items"][0]["body"], "Booked those dates")
        # toggles: switching Selections off hides it from the bell, the history keeps it
        c.post("/api/me/notify", {"selections": False})
        self.assertEqual(self.bell(c)["unread"], 0)
        acc = c.get("/api/account")[1]
        self.assertEqual(len(acc["notifications"]["items"]), 2)
        c.post("/api/me/notify", {"selections": True})
        c.post("/api/notifications/read", {"ids": [b["items"][0]["id"]]})
        self.assertEqual(self.bell(c)["unread"], 1)
        c.post("/api/notifications/read", {})
        self.assertEqual(self.bell(c)["unread"], 0)
        # nothing was emailed to the client
        self.assertFalse(any(m["to"] == "bell@novartis.com" for m in mailer.OUTBOX))

    def test_02_bell_campaign_credits_and_ideas_off_by_default(self):
        c, _ = self.signup("camp@novartis.com")
        u = self.user("camp@novartis.com")
        cid = db.create_campaign("Back to School", "Novartis", u["code_id"])
        db.save_campaign(cid, status="live")
        db.add_content(cid, {"url": "https://x/p/9", "code": "HV-MI-001", "platform": "Instagram", "kind": "post", "views": 100})
        db.add_content(cid, {"url": "https://x/p/10", "code": "HV-MI-001", "platform": "Instagram", "kind": "post", "views": 50})
        db.save_campaign(cid, status="ended")
        kinds = [i["kind"] for i in self.bell(c, 20)["items"]]
        self.assertEqual(kinds.count("camp_live"), 1)
        self.assertEqual(kinds.count("camp_report"), 1)                  # once a day, however many posts
        self.assertEqual(kinds.count("camp_final"), 1)
        # credits low: crossing below 5
        portal.grant(u["code_id"], -portal.balance(u["code_id"]) + 6, "set to 6")
        portal.spend(u["code_id"], 2, "test")
        self.assertIn("credits_low", [i["kind"] for i in self.bell(c, 20)["items"]])
        # admin top-up
        a = self.admin()
        a.req("POST", "/portal/user/credits", form={"id": u["id"], "amount": "50", "back": "/portal"})
        self.assertIn("credits_added", [i["kind"] for i in self.bell(c, 20)["items"]])
        self.assertFalse(inbox.prefs(self.user("camp@novartis.com"))["ideas"])

    # ------------------------------------------------------ profile rewards --
    def test_03_profile_rewards_once_and_never_blank(self):
        c, _ = self.signup("reward@roche.com")
        u = self.user("reward@roche.com")
        start = portal.balance(u["code_id"])
        r = c.post("/api/me/update", {"job_title": "   ", "phone": ""})[1]
        self.assertEqual(r["earned"], [])                                # blanks earn nothing
        r = c.post("/api/me/update", {"job_title": "Brand Manager"})[1]
        self.assertEqual([e["key"] for e in r["earned"]], ["job_title"])
        self.assertEqual(c.post("/api/me/update", {"job_title": "Senior Brand Manager"})[1]["earned"], [])  # once
        c.post("/api/me/update", {"phone": "+966500000000", "brands": "Cetaphil, Daylong"})
        r = c.post("/api/me/update", {"industry": "skincare"})[1]
        self.assertEqual(r["earned"], [])                                # industry alone is not the step
        r = c.post("/api/me/update", {"markets": ["SA", "AE", "XX"], "language": "Arabic and English"})[1]
        self.assertEqual([e["key"] for e in r["earned"]], ["industry_markets"])
        self.assertEqual(r["user"]["markets"], ["SA", "AE"])
        png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        c.post("/api/me/image", {"kind": "photo", "data": png})
        r = c.post("/api/me/image", {"kind": "logo", "data": png})[1]
        self.assertEqual(sorted(e["key"] for e in r["earned"]), ["complete", "logo"])
        self.assertEqual(r["completion"]["pct"], 100)
        self.assertEqual(portal.balance(u["code_id"]) - start, 30)       # 2+2+3+3+5+5+10
        reasons = [x["reason"] for x in portal.ledger(u["code_id"], 20) if x["reason"].startswith("Profile reward")]
        self.assertIn("Profile reward: Add your brands and products", reasons)
        # the brief can start from the profile
        me = c.get("/api/me")[1]
        self.assertEqual((me["user"]["industry"], me["user"]["markets"]), ("skincare", ["SA", "AE"]))

    def test_04_invite_pays_once_same_domain_max_five(self):
        a, _ = self.signup("boss@gsk.com")
        inviter = self.user("boss@gsk.com")
        tok = c_tok = a.get("/api/account")[1]["invite"]["token"]
        self.assertTrue(rewards.read_token(tok, server.SECRET) == inviter["id"])
        before = portal.balance(inviter["code_id"])
        # through the link
        c = Client(self.base)
        c.post("/api/auth/start", {"email": "new1@gsk.com"})
        code = mailer.OUTBOX[-1]["text"].split("code is ")[1][:6]
        b = c.post("/api/auth/verify", {"email": "new1@gsk.com", "otp": code})[1]
        c.post("/api/auth/profile", {"ticket": b["ticket"], "name": "New One", "company": "GSK", "invite": c_tok})
        self.assertEqual(portal.balance(inviter["code_id"]) - before, 20)
        kinds = [i for i in self.bell(a, 10)["items"] if i["kind"] == "colleague"]
        self.assertEqual(kinds[0]["title"], "New One joined your team")
        self.assertIn("20 credits", kinds[0]["body"])
        # signing in again pays nothing more
        self.skip_cooldown()
        c2 = Client(self.base)
        c2.post("/api/auth/start", {"email": "new1@gsk.com"})
        code = mailer.OUTBOX[-1]["text"].split("code is ")[1][:6]
        c2.post("/api/auth/verify", {"email": "new1@gsk.com", "otp": code})
        self.assertEqual(portal.balance(inviter["code_id"]) - before, 20)
        # other domain: recorded as not counted
        r = a.post("/api/team/invite", {"name": "X", "email": "x@other.com"})[1]
        self.assertFalse(r["counted"])
        # max five paid invites
        for i in range(2, 8):
            a.post("/api/team/invite", {"name": "P%d" % i, "email": "p%d@gsk.com" % i})
            guard.limiter._hits.clear()
            self.signup("p%d@gsk.com" % i)
        self.assertEqual(portal.balance(inviter["code_id"]) - before, 100)
        self.assertEqual(a.get("/api/account")[1]["invite"]["left"], 0)

    # ------------------------------------------------------ analysis gating --
    def test_05_locked_analysis_never_leaves_the_server(self):
        db.save_analysis("HV-MD-004", SECRET_DOC, platform="Instagram")
        c, _ = self.signup("gate@sanofi.com")
        s, b, r = c.get("/api/creator?c=HV-MD-004")
        raw = json.dumps(b)
        self.assertEqual(b["gate"]["state"], "outside")
        for m in LOCKED_MARKERS:
            self.assertNotIn(m, raw, m)
        self.assertEqual(b["analyses"], {})
        self.assertTrue(b["gate"]["sample"]["sample"])
        h = b["gate"]["headline"]
        self.assertEqual((h["er"], h["avg_views"]), (4.2, 9100))           # the free layer is real
        # media of the analysis is locked too
        self.assertEqual(c.get("/api/creator-media?c=HV-MD-004&n=x.jpg")[0], 403)
        # outside a selection: no request
        s, r2, _ = c.post("/api/creator/request", {"code": "HV-MD-004"})
        self.assertEqual((s, r2["reason"]), (403, "outside"))
        # inside one: requested, then the admin fulfils it
        tok = c.post("/api/selection", {"name": "Gate list", "codes": ["HV-MD-004", "HV-MI-001"]})[1]["token"]
        self.assertEqual(c.get("/api/creator?c=HV-MD-004")[1]["gate"]["state"], "locked")
        # selection scores keep the number but not the locked evidence
        sel_raw = json.dumps(c.get("/api/selection?s=" + tok)[1])
        for m in LOCKED_MARKERS:
            self.assertNotIn(m, sel_raw, m)
        s, r3, _ = c.post("/api/creator/request", {"code": "HV-MD-004"})
        self.assertEqual(r3["gate"]["state"], "requested")
        self.assertIn("ready_by", r3["gate"])
        a = self.admin()
        s, page, _ = a.get("/analysis")
        self.assertIn("Fulfil", page)
        rid = [q for q in __import__("gating").queue() if q["code"] == "HV-MD-004"][0]["id"]
        a.req("POST", "/analysis/fulfil", form={"id": rid})
        b = c.get("/api/creator?c=HV-MD-004")[1]
        self.assertEqual(b["gate"]["state"], "unlocked")
        self.assertIn("77.77", json.dumps(b))
        self.assertEqual(self.bell(c)["items"][0]["kind"], "analysis_ready")
        # a colleague on the same domain sees it unlocked too; another company does not
        col, _ = self.signup("mate@sanofi.com")
        self.assertEqual(col.get("/api/creator?c=HV-MD-004")[1]["gate"]["state"], "unlocked")
        other, _ = self.signup("x@bayer.com")
        self.assertNotIn("77.77", json.dumps(other.get("/api/creator?c=HV-MD-004")[1]))

    def test_06_upload_answers_requests_and_assistant_respects_locks(self):
        import assistant
        c, _ = self.signup("chat@abbvie.com")
        u = self.user("chat@abbvie.com")
        c.post("/api/selection", {"name": "Chat list", "codes": ["HV-MI-005"]})
        self.assertTrue(c.post("/api/creator/request", {"code": "HV-MI-005"})[1]["ok"])
        ctx = {"code_id": u["code_id"]}
        db.save_analysis("HV-MI-002", SECRET_DOC, platform="Instagram")
        r = assistant.t_creator_metrics(ctx, codes=["HV-MI-002"], fields=["fake_followers_pct", "engagement_rate_pct"])
        one = r["creators"][0]
        self.assertIsNone(one["fake_followers_pct"])
        self.assertEqual(one["engagement_rate_pct"], 4.2)
        self.assertIn("locked", one)
        self.assertNotIn("77.77", json.dumps(assistant.t_get_creator(ctx, "HV-MI-002")))
        low = assistant.t_rank_by_metric(ctx, metric="fake_followers_pct", order="asc")
        self.assertEqual(low["creators"], [])
        with self.assertRaises(ValueError):
            assistant.d_analysis({"code": "HV-MI-002"}, ctx)               # not in a selection
        self.assertIn("locked", assistant.system_prompt("client", {"user": {}}).lower())
        # uploading HV-MI-005's analysis unlocks it for the client who asked and rings
        db.save_analysis("HV-MI-005", SECRET_DOC, platform="Instagram")
        self.assertEqual(c.get("/api/creator?c=HV-MI-005")[1]["gate"]["state"], "unlocked")
        self.assertEqual(self.bell(c)["items"][0]["kind"], "analysis_ready")
        r = assistant.t_creator_metrics(ctx, codes=["HV-MI-005"], fields=["fake_followers_pct"])
        self.assertEqual(r["creators"][0]["fake_followers_pct"], 13.37)
        acc = c.get("/api/account")[1]
        self.assertEqual([x["state"] for x in acc["analyses"] if x["code"] == "HV-MI-005"], ["unlocked"])

    # ------------------------------------------------------ selection status --
    def test_07_only_the_owner_decides_and_the_kam_hears(self):
        db.set_setting("kams", ["Lina K <lina@hellovoice.co.uk>"])
        try:
            o, _ = self.signup("owner@merck.com")
            portal.update_profile(self.user("owner@merck.com")["id"], kam="Lina K")
            mate, _ = self.signup("mate@merck.com")
            tok = o.post("/api/selection", {"name": "Eid", "codes": ["HV-MI-001", "HV-MI-002", "HV-MD-003"]})[1]["token"]
            sel = o.get("/api/selection?s=" + tok)[1]
            self.assertEqual((sel["role"], sel["status_counts"]["review"], sel["status_counts"]["creators"]), ("owner", 3, 3))
            self.assertEqual(mate.get("/api/selection?s=" + tok)[1]["role"], "viewer")
            s, r, _ = mate.post("/api/selection/status", {"token": tok, "code": "HV-MI-001", "status": "approved"})
            self.assertEqual((s, r["reason"]), (403, "not_owner"))
            s, r, _ = o.post("/api/selection/status", {"token": tok, "code": "HV-MI-001", "status": "unavailable"})
            self.assertEqual(s, 403)
            mailer.OUTBOX.clear()
            s, r, _ = o.post("/api/selection/status", {"token": tok, "code": "HV-MI-001", "status": "approved"})
            self.assertEqual((s, r["status"]["s"], r["status"]["by"]), (200, "approved", "Ali Hassan"))
            s, r, _ = o.post("/api/selection/status", {"token": tok, "code": "HV-MI-002", "status": "rejected"})
            r = o.post("/api/selection/reason", {"token": tok, "code": "HV-MI-002", "reason": "price", "note": ""})[1]
            self.assertEqual(r["status"]["reason"], "price")
            time.sleep(0.4)
            self.assertTrue(any(m["to"] == "lina@hellovoice.co.uk" and "Selection feedback" in m["subject"] for m in mailer.OUTBOX))
            counts = o.get("/api/selection?s=" + tok)[1]["status_counts"]
            self.assertEqual((counts["approved"], counts["rejected"], counts["review"]), (1, 1, 1))
            # the client's own changes do not ring their own bell
            self.assertEqual([i for i in self.bell(o, 20)["items"] if i["kind"] == "sel_feedback"], [])
        finally:
            db.set_setting("kams", [])

    def test_08_replacement_costs_two_credits_once(self):
        o, _ = self.signup("swap@pfizer.org")
        u = self.user("swap@pfizer.org")
        tok = o.post("/api/selection", {"name": "Swap", "codes": ["HV-MI-001", "HV-MI-002"]})[1]["token"]
        s, r, _ = o.post("/api/selection/replace", {"token": tok, "code": "HV-MI-001"})
        self.assertEqual((s, r["reason"]), (400, "not_rejected"))
        o.post("/api/selection/status", {"token": tok, "code": "HV-MI-001", "status": "rejected"})
        before = portal.balance(u["code_id"])
        r = o.post("/api/selection/replace", {"token": tok, "code": "HV-MI-001"})[1]
        self.assertTrue(r["ok"], r)
        got = [x["code"] for x in r["replacements"]]
        self.assertTrue(1 <= len(got) <= 3)
        self.assertFalse(set(got) & {"HV-MI-001", "HV-MI-002"})
        self.assertEqual(before - portal.balance(u["code_id"]), 2)
        r2 = o.post("/api/selection/replace", {"token": tok, "code": "HV-MI-001"})[1]
        self.assertEqual(([x["code"] for x in r2["replacements"]], r2["spent"]), (got, 0))   # opening again is free
        self.assertEqual(o.get("/api/selection?s=" + tok)[1]["status"]["HV-MI-001"]["replacements"], got)

    def test_09_admin_status_tab_and_profile_page_render(self):
        o, _ = self.signup("render@pfizer.net")
        tok = o.post("/api/selection", {"name": "Render", "codes": ["HV-MI-001"]})[1]["token"]
        a = self.admin()
        sel = db.selection(token=tok)
        s, page, _ = a.get("/selections/edit?id=%d" % sel["id"])
        self.assertEqual(s, 200)
        self.assertIn("Client status", page)
        acc = o.get("/api/account")[1]
        for key in ("completion", "notifications", "analyses", "briefs", "ledger", "invite", "next", "markets", "industries"):
            self.assertIn(key, acc)
        self.assertEqual(acc["next"]["kind"], "review")
        self.assertEqual(acc["selections"][0]["counts"]["review"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
