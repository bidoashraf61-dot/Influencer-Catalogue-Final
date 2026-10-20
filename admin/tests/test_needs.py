"""Control Centre in the profile, slice a (item 209, 2026-10-21): the team's "Needs you" queue, approving a
sign-up from it (with History and undo), the "This month" strip, and the step-up code.

    python3 admin/tests/test_needs.py
"""
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import db, gemini, guard, history, mailer, portal, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

KAM, BOSS = "mariam.k@hvkam.com", "boss@hellovoice.co.uk"


class Needs(unittest.TestCase):
    signup = base.Portal.signup
    member = base.Portal.member

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        mailer.CAPTURE = True
        gemini.STUB = base.stub
        views.set_base("")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        db.set_setting("domain_kam", {"polyco.com": KAM})
        db.set_setting("kams", ["Mariam K <%s>" % KAM])
        cls.ready = False

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()
        mailer.OUTBOX.clear()
        if not Needs.ready:
            W = Needs
            self.signup("lead@polyco.com"); self.signup("waiting@polyco.com"); self.signup("waiting@rivalco.com")
            W.lead = portal.user_by_email("lead@polyco.com")
            W.wpoly = portal.user_by_email("waiting@polyco.com"); W.wrival = portal.user_by_email("waiting@rivalco.com")
            portal.set_status(W.wpoly["id"], "pending"); portal.set_status(W.wrival["id"], "pending")
            W.s1 = db.save_selection(None, "Polyco glow", ["HV-MI-001"], {}, None, None, code_id=W.lead["code_id"])
            W.k1 = db.create_campaign("Polyco wave", code_id=W.lead["code_id"], selection_id=W.s1)
            db.save_campaign(W.k1, status="live", starts_at=1, ends_at=2)
            with db.connect() as conn:
                conn.execute("UPDATE campaigns SET next_step = 'Send wave 2', next_due = ? WHERE id = ?", (db.now() - 3 * 86400, W.k1))
                conn.execute("INSERT INTO requests (at, code_id, name, company, selection_name, selection) VALUES (?,?,?,?,?,?)",
                             (db.now() - 3600, W.lead["code_id"], "Lead", "Polyco", "Polyco glow", '["HV-MI-001"]'))
            self.member(BOSS, "owner"); self.member(KAM, "kam")
            W.boss = self.signup(BOSS)[0]; W.kam = self.signup(KAM)[0]
            W.plain = self.signup("plain@plainco.com")[0]
            Needs.ready = True

    def groups(self, client):
        s, b, _ = client.get("/api/needs")
        self.assertEqual(s, 200, b)
        return {g["key"]: g for g in b["groups"]}, b

    def test_01_who_gets_the_queue(self):
        self.assertEqual(self.plain.get("/api/needs")[0], 403)
        self.assertIsNone(self.plain.get("/api/account")[1].get("cc"))
        cc = self.boss.get("/api/account")[1]["cc"]
        self.assertEqual((cc["role"], cc["admin_links"]), ("admin", True))
        cc = self.kam.get("/api/account")[1]["cc"]
        self.assertEqual((cc["role"], cc["admin_links"]), ("kam", False))

    def test_02_admin_sees_everything_kam_her_own(self):
        g, b = self.groups(self.boss)
        emails = {i["sub"].split(" · ")[-1] for i in g["signups"]["items"]}
        self.assertTrue({"waiting@polyco.com", "waiting@rivalco.com"} <= emails, emails)
        self.assertNotIn(BOSS, emails)                               # the team is never a sign-up to approve
        self.assertEqual(g["overdue"]["items"][0]["title"], "Send wave 2")
        self.assertEqual(g["quotes"]["count"], 1)
        self.assertEqual(b["kpis"]["live"], 1)
        g, _ = self.groups(self.kam)
        emails = {i["sub"].split(" · ")[-1] for i in g["signups"]["items"]}
        self.assertIn("waiting@polyco.com", emails)                  # her domain
        self.assertNotIn("waiting@rivalco.com", emails)              # not hers
        self.assertIn("overdue", g)

    def test_03_approve_with_history_and_undo(self):
        s, b, _ = self.kam.post("/api/needs/approve", {"id": self.wrival["id"]})
        self.assertEqual(s, 400, b)                                  # a KAM: not her client
        s, b, _ = self.boss.post("/api/needs/approve", {"id": self.wrival["id"]})
        self.assertEqual(s, 200, b)
        self.assertEqual(portal.user_by_id(self.wrival["id"])["status"], "active")
        with db.connect() as conn:
            h = conn.execute("SELECT * FROM history WHERE entity = 'user' AND key = ? ORDER BY id DESC", (str(self.wrival["id"]),)).fetchone()
        self.assertEqual(h["who"], BOSS)
        ok, _ = history.undo(h["id"])
        self.assertTrue(ok)
        u = portal.user_by_id(self.wrival["id"])
        self.assertEqual(u["status"], "pending")
        with db.connect() as conn:
            self.assertIsNotNone(conn.execute("SELECT revoked_at FROM codes WHERE id = ?", (u["code_id"],)).fetchone()["revoked_at"])
        self.assertEqual(self.boss.post("/api/needs/approve", {"id": self.lead["id"]})[0], 400)   # already active

    def test_04_step_up(self):
        self.assertEqual(self.plain.post("/api/stepup/send", {})[0], 403)
        s, b, _ = self.boss.post("/api/stepup/send", {})
        self.assertEqual((s, b["to"]), (200, BOSS), b)
        code = mailer.OUTBOX[-1]["text"].split("code is ")[1][:6]
        self.assertEqual(self.boss.post("/api/stepup/verify", {"code": "000000" if code != "000000" else "111111"})[0], 400)
        s, b, _ = self.boss.post("/api/stepup/verify", {"code": code})
        self.assertEqual(s, 200, b)
        self.assertGreater(b["seconds"], 500)
        self.assertGreater(self.boss.get("/api/account")[1]["cc"]["stepup"], 500)
        self.assertEqual(self.kam.get("/api/account")[1]["cc"]["stepup"], 0)          # the window is per person
        # A step-up code is not a sign-in code.
        from e2e_portal import Client
        c = Client(self.base)
        c.post("/api/auth/start", {"email": BOSS})
        self.assertNotEqual(c.post("/api/auth/verify", {"email": BOSS, "otp": code})[1].get("ok"), True)

    def test_05_account_controls(self):
        # hold -> reactivate by a KAM on her own client; suspend and credits need an admin and a code.
        u = portal.user_by_email("waiting@polyco.com")
        s, b, _ = self.kam.post("/api/hub/account", {"id": u["id"], "action": "hold"})
        self.assertEqual(s, 200, b)
        s, d, _ = self.boss.get("/api/hub/company?k=polyco.com")
        st = {p["email"]: p for p in d["people"]}
        self.assertEqual(st["waiting@polyco.com"]["state"], "held")
        self.assertEqual(st["waiting@polyco.com"]["can"][0], "reactivate")
        self.assertIn("credits", st["lead@polyco.com"])
        g, _ = self.groups(self.boss)
        self.assertNotIn("waiting@polyco.com", {i["sub"].split(" · ")[-1] for i in (g.get("signups") or {"items": []})["items"]})
        self.assertEqual(self.kam.post("/api/hub/account", {"id": u["id"], "action": "reactivate"})[0], 200)
        self.assertEqual(portal.user_by_email("waiting@polyco.com")["status"], "active")
        lead = self.lead
        self.assertEqual(self.kam.post("/api/hub/account", {"id": lead["id"], "action": "suspend"})[0], 403)      # KAM: admin only
        self.assertEqual(self.kam.post("/api/hub/account", {"id": lead["id"], "action": "credits", "amount": 5})[0], 403)
        rival = portal.user_by_email("waiting@rivalco.com")
        self.assertEqual(self.kam.post("/api/hub/account", {"id": rival["id"], "action": "hold"})[0], 403)         # not her client
        with db.connect() as conn:
            conn.execute("DELETE FROM stepup_grants")                                                              # test_04 left a window open
        s, b, _ = self.boss.post("/api/hub/account", {"id": lead["id"], "action": "credits", "amount": 5})
        self.assertEqual((s, b.get("reason")), (403, "stepup"), b)                                                # needs the code
        with db.connect() as conn:
            conn.execute("UPDATE otp SET created_at = created_at - 100")                                            # past the resend cooldown
        self.boss.post("/api/stepup/send", {}); code = mailer.OUTBOX[-1]["text"].split("code is ")[1][:6]
        self.assertEqual(self.boss.post("/api/stepup/verify", {"code": code})[0], 200)
        before = portal.balance(lead["code_id"])
        s, b, _ = self.boss.post("/api/hub/account", {"id": lead["id"], "action": "credits", "amount": 5})
        self.assertEqual((s, portal.balance(lead["code_id"])), (200, before + 5), b)
        self.assertEqual(self.boss.post("/api/hub/account", {"id": lead["id"], "action": "credits", "amount": 0})[0], 400)
        self.assertEqual(self.boss.post("/api/hub/account", {"id": lead["id"], "action": "suspend"})[0], 200)
        self.assertEqual(portal.user_by_email("lead@polyco.com")["status"], "suspended")
        self.assertEqual(self.boss.post("/api/hub/account", {"id": lead["id"], "action": "reactivate"})[0], 200)
        s, d, _ = self.boss.get("/api/hub/companies")
        pc = {c["domain"]: c for c in d["companies"]}["polyco.com"]
        self.assertEqual((pc["waiting"], pc["blocked"]), (0, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
