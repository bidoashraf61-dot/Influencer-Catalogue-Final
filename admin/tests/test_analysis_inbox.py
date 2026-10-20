"""Analysis inbox (item 195, owner 2026-10-20): client requests land on the admin's Analyses tab, grouped by
client and campaign; Approve opens the analysis to the person who asked only; Reject tells them; KAMs see their
clients' requests; an upload no longer closes requests by itself.

    python3 admin/tests/test_analysis_inbox.py
"""
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import db, gating, gemini, guard, mailer, portal, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

KAM, OTHER, BOSS = "mariam.k@hvkam.com", "omar.k@hvkam.com", "boss@hellovoice.co.uk"
FULL = {"followers": 42000, "er": 4.6, "avg_views": 9100, "sample_posts": 20,
        "audience": {"countries": [{"code": "SA", "pct": 52}], "gender": {"female": 72, "male": 28}}}


class Inbox(unittest.TestCase):
    signup = base.Portal.signup
    member = base.Portal.member

    @classmethod
    def setUpClass(cls):
        base.seed()
        import apify
        apify.init()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        mailer.CAPTURE = True
        gemini.STUB = base.stub
        views.set_base("")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        db.set_setting("domain_kam", {"polyco.com": KAM, "rivalco.com": OTHER})
        db.set_setting("kams", ["Mariam K <%s>" % KAM, "Omar K <%s>" % OTHER])
        cls.ready = False

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()
        mailer.OUTBOX.clear()
        if Inbox.ready:
            return
        W = Inbox
        W.lead, _ = self.signup("lead@polyco.com")
        W.mate, _ = self.signup("mate@polyco.com")
        W.rival, _ = self.signup("buyer@rivalco.com")
        W.u_lead, W.u_mate = portal.user_by_email("lead@polyco.com"), portal.user_by_email("mate@polyco.com")
        W.u_rival = portal.user_by_email("buyer@rivalco.com")
        W.s = db.save_selection(None, "Glow list", ["HV-MI-001", "HV-MI-002"], {}, None, None, code_id=W.u_lead["code_id"])
        db.save_selection(None, "Mate list", ["HV-MI-001"], {}, None, None, code_id=W.u_mate["code_id"])
        db.save_selection(None, "Rival list", ["HV-MD-004"], {}, None, None, code_id=W.u_rival["code_id"])
        W.k = db.create_campaign("Poly glow", client="Polyco", code_id=W.u_lead["code_id"], selection_id=W.s)
        self.member(BOSS, "owner"); self.member(KAM, "kam"); self.member(OTHER, "kam")
        W.boss, _ = self.signup(BOSS)
        W.kam, _ = self.signup(KAM)
        W.ready = True

    def ask(self, who, code):
        s, b, _ = who.post("/api/creator/request", {"code": code})
        self.assertEqual(s, 200, b)

    def test_01_requests_land_grouped_and_scoped(self):
        self.ask(self.lead, "HV-MI-001")
        self.ask(self.rival, "HV-MD-004")
        s, b, _ = self.boss.get("/api/analysis/inbox")
        self.assertEqual((s, b["role"]), (200, "admin"), b)
        mine = [r for r in b["requests"] if r["code"] == "HV-MI-001" and r["state"] == "open"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["campaigns"][0]["name"], "Poly glow")
        self.assertEqual(mine[0]["selections"][0]["name"], "Glow list")
        self.assertIn("HV-MD-004", {r["code"] for r in b["requests"]})
        s, b, _ = self.kam.get("/api/analysis/inbox")
        self.assertEqual({r["code"] for r in b["requests"]}, {"HV-MI-001"})      # her client only
        self.assertEqual(self.lead.get("/api/analysis/inbox")[0], 403)
        self.assertEqual(self.lead.post("/api/analysis/decide", {"id": mine[0]["id"], "ok": True})[0], 403)

    def test_02_approve_opens_it_to_that_person_only(self):
        rid = next(r["id"] for r in self.boss.get("/api/analysis/inbox")[1]["requests"] if r["code"] == "HV-MI-001" and r["state"] == "open")
        s, b, _ = self.boss.post("/api/analysis/decide", {"id": rid, "ok": True})
        self.assertEqual(s, 400, b)                                    # nothing on file yet
        self.assertIn("Upload", b["message"])
        db.save_analysis("HV-MI-001", dict(FULL), platform="Instagram")
        with db.connect() as conn:
            self.assertIsNone(conn.execute("SELECT handled_at FROM analysis_requests WHERE id = ?", (rid,)).fetchone()[0])  # upload: still open
        s, b, _ = self.boss.post("/api/analysis/decide", {"id": rid, "ok": True})
        self.assertEqual(s, 200, b)
        self.assertTrue(gating.unlocked(self.u_lead["code_id"], "HV-MI-001"))
        self.assertFalse(gating.unlocked(self.u_mate["code_id"], "HV-MI-001"))     # a colleague: still locked
        s, b, _ = self.lead.get("/api/creator?c=HV-MI-001")
        self.assertEqual(b["gate"]["state"], "unlocked")
        s, b, _ = self.lead.get("/api/account")
        self.assertEqual(next(a for a in b["analyses"] if a["code"] == "HV-MI-001")["state"], "unlocked")
        with db.connect() as conn:
            self.assertTrue(conn.execute("SELECT 1 FROM notifications WHERE user_id = ? AND kind = 'analysis_ready'", (self.u_lead["id"],)).fetchone())
        self.assertEqual(self.boss.post("/api/analysis/decide", {"id": rid, "ok": True})[0], 400)   # already answered

    def test_03_reject_tells_them_and_kam_may_answer_hers_only(self):
        rid = next(r["id"] for r in self.boss.get("/api/analysis/inbox")[1]["requests"] if r["code"] == "HV-MD-004" and r["state"] == "open")
        self.assertEqual(self.kam.post("/api/analysis/decide", {"id": rid, "ok": False})[0], 404)   # another KAM's client
        s, b, _ = self.boss.post("/api/analysis/decide", {"id": rid, "ok": False, "note": "Not available this month."})
        self.assertEqual(s, 200, b)
        with db.connect() as conn:
            n = conn.execute("SELECT body FROM notifications WHERE user_id = ? AND kind = 'analysis_reply'", (self.u_rival["id"],)).fetchone()
        self.assertEqual(n[0], "Not available this month.")
        s, b, _ = self.rival.get("/api/account")
        a = next(a for a in b["analyses"] if a["code"] == "HV-MD-004")
        self.assertEqual((a["state"], a["note"]), ("declined", "Not available this month."))
        self.assertFalse(gating.unlocked(self.u_rival["code_id"], "HV-MD-004"))
        got = {r["id"]: r["state"] for r in self.boss.get("/api/analysis/inbox")[1]["requests"]}
        self.assertEqual(got[rid], "rejected")
        # they may ask again
        self.ask(self.rival, "HV-MD-004")


if __name__ == "__main__":
    unittest.main(verbosity=1)
