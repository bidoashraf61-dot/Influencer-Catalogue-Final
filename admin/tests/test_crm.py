"""The account CRM behind the Companies tab (items 209 + 220, 2026-10-21): stages from the data with an
override that holds until the data moves, health from the worst signal, quote money, notes, prospects that
become accounts, scope (admins all, KAMs hers, clients nothing), History with undo.

    python3 admin/tests/test_crm.py
"""
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import crm, db, gemini, guard, history, mailer, portal, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

KAM, OTHER, BOSS = "mariam.k@hvkam.com", "omar.k@hvkam.com", "boss@hellovoice.co.uk"
DAY = 86400


class Crm(unittest.TestCase):
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
        if not Crm.ready:
            W = Crm
            self.signup("lead@polyco.com"); self.signup("buyer@rivalco.com")
            W.lead = portal.user_by_email("lead@polyco.com"); W.buyer = portal.user_by_email("buyer@rivalco.com")
            self.member(BOSS, "owner"); self.member(KAM, "kam"); self.member(OTHER, "kam")
            W.boss = self.signup(BOSS)[0]; W.kam = self.signup(KAM)[0]; W.plain = self.signup("plain@plainco.com")[0]
            crm.ensure()
            Crm.ready = True

    def get(self, client, key="polyco.com"):
        s, b, _ = client.get("/api/crm/companies")
        self.assertEqual(s, 200, b)
        return {r["key"]: r for r in b["rows"]}

    def test_01_scope(self):
        self.assertEqual(self.plain.get("/api/crm/companies")[0], 403)
        rows = self.get(self.boss)
        self.assertTrue({"polyco.com", "rivalco.com"} <= set(rows))
        mine = self.get(self.kam)
        self.assertIn("polyco.com", mine); self.assertNotIn("rivalco.com", mine)
        self.assertEqual(rows["polyco.com"]["kam"]["email"], KAM)

    def test_02_stage_follows_the_data(self):
        self.assertEqual(self.get(self.boss)["polyco.com"]["stage"], "lead")                   # an account with nothing yet
        s1 = db.save_selection(None, "Polyco glow", ["HV-MI-001"], {}, None, None, code_id=self.lead["code_id"])
        self.assertEqual(self.get(self.boss)["polyco.com"]["stage"], "engaged")
        with db.connect() as conn:
            conn.execute("INSERT INTO requests (at, code_id, name, company, selection_name, selection) VALUES (?,?,?,?,?,?)",
                         (db.now() - 2 * DAY, self.lead["code_id"], "Lead", "Polyco", "Polyco glow", '["HV-MI-001"]'))
        self.assertEqual(self.get(self.boss)["polyco.com"]["stage"], "quote")
        k1 = db.create_campaign("Polyco wave", code_id=self.lead["code_id"], selection_id=s1)
        db.save_campaign(k1, status="live", starts_at=1, ends_at=2)
        r = self.get(self.boss)["polyco.com"]
        self.assertEqual((r["stage"], r["live"]), ("active", 1))
        k2 = db.create_campaign("Polyco wave 2", code_id=self.lead["code_id"], selection_id=s1)
        self.assertEqual(self.get(self.boss)["polyco.com"]["stage"], "repeat")
        type(self).k1, type(self).k2 = k1, k2

    def test_03_override_holds_until_the_data_moves(self):
        s, b, _ = self.kam.post("/api/crm/set", {"key": "polyco.com", "stage": "dormant"})
        self.assertEqual(s, 200, b)
        r = self.get(self.boss)["polyco.com"]
        self.assertEqual((r["stage"], r["stage_override"], r["stage_auto"]), ("dormant", True, "repeat"))
        db.save_campaign(self.k2, status="ended")
        db.save_campaign(self.k1, status="ended")                                               # live 0, two campaigns: auto is still repeat
        self.assertEqual(self.get(self.boss)["polyco.com"]["stage"], "dormant")
        with db.connect() as conn:
            conn.execute("DELETE FROM campaigns WHERE id = ?", (self.k2,))
        db.save_campaign(self.k1, status="live", starts_at=1, ends_at=2)
        r = self.get(self.boss)["polyco.com"]                                                    # auto is now "active": the override lets go
        self.assertEqual((r["stage"], r["stage_override"]), ("active", False))
        self.assertEqual(self.kam.post("/api/crm/set", {"key": "polyco.com", "stage": ""})[0], 200)
        with db.connect() as conn:
            h = conn.execute("SELECT id FROM history WHERE entity = 'company' ORDER BY id DESC").fetchone()
        self.assertIsNotNone(h)

    def test_04_next_step_overdue_and_health(self):
        due = db.now() - 3 * DAY
        s, b, _ = self.kam.post("/api/crm/set", {"key": "polyco.com", "next_step": "Send wave 2", "next_due": due})
        self.assertEqual(s, 200, b)
        r = self.get(self.boss)["polyco.com"]
        self.assertEqual((r["next_step"], r["overdue"], r["health"]), ("Send wave 2", True, "low"))
        self.assertIn("late", r["why"])
        self.kam.post("/api/crm/set", {"key": "polyco.com", "next_due": db.now() + 5 * DAY})
        r = self.get(self.boss)["polyco.com"]
        self.assertEqual((r["overdue"], r["health"]), (False, "good"))
        self.assertEqual(self.kam.post("/api/crm/set", {"key": "rivalco.com", "next_step": "x"})[0], 404)   # not hers
        with db.connect() as conn:
            conn.execute("UPDATE users SET last_login_at = ?, created_at = ? WHERE id = ?", (db.now() - 60 * DAY, db.now() - 70 * DAY, self.lead["id"]))
            conn.execute("UPDATE selections SET updated_at = ? WHERE code_id = ?", (db.now() - 60 * DAY, self.lead["code_id"]))
            conn.execute("UPDATE campaigns SET updated_at = ? WHERE code_id = ?", (db.now() - 60 * DAY, self.lead["code_id"]))
            conn.execute("UPDATE requests SET at = ? WHERE code_id = ?", (db.now() - 60 * DAY, self.lead["code_id"]))
        r = self.get(self.boss)["polyco.com"]
        self.assertEqual(r["health"], "low"); self.assertIn("60 days", r["why"])

    def test_05_quotes_money_and_notes(self):
        s, d, _ = self.kam.get("/api/crm/company?k=polyco.com")
        self.assertEqual(s, 200, d)
        q = d["quotes"][0]
        self.assertEqual(self.kam.post("/api/crm/quote", {"id": q["id"], "value_sar": "abc"})[0], 400)
        self.assertEqual(self.kam.post("/api/crm/quote", {"id": q["id"], "value_sar": 48000})[0], 200)
        r = self.get(self.boss)["polyco.com"]
        self.assertEqual((r["open_n"], r["open_sar"], r["approved_sar"]), (1, 48000, 0))
        self.assertEqual(self.kam.post("/api/crm/quote", {"id": q["id"], "value_sar": 48000, "approved_sar": 44000})[0], 200)
        r = self.get(self.boss)["polyco.com"]
        self.assertEqual((r["open_n"], r["approved_sar"]), (0, 44000))
        rival_q = None
        with db.connect() as conn:
            conn.execute("INSERT INTO requests (at, code_id, name, company, selection_name, selection) VALUES (?,?,?,?,?,?)",
                         (db.now(), self.buyer["code_id"], "B", "Rival", "s", "[]"))
            rival_q = conn.execute("SELECT id FROM requests WHERE code_id = ?", (self.buyer["code_id"],)).fetchone()["id"]
        self.assertEqual(self.kam.post("/api/crm/quote", {"id": rival_q, "value_sar": 5})[0], 403)         # another KAM's client
        self.assertEqual(self.plain.post("/api/crm/quote", {"id": q["id"], "value_sar": 5})[0], 403)
        s, b, _ = self.kam.post("/api/crm/note", {"key": "polyco.com", "text": "Wants Riyadh doctors only.", "kind": "call"})
        self.assertEqual(s, 200, b)
        self.assertEqual(b["notes"][0]["kind"], "call")
        self.assertEqual(self.kam.post("/api/crm/note", {"key": "polyco.com", "text": "  "})[0], 400)
        self.assertEqual(self.kam.post("/api/crm/note", {"key": "rivalco.com", "text": "x"})[0], 404)
        # the client never sees any of it
        self.assertNotIn("crm", self.plain.get("/api/account")[1])

    def test_06_prospects_become_accounts(self):
        s, b, _ = self.kam.post("/api/crm/prospect", {"name": "Newco", "domain": "https://www.newco.com/about", "next_step": "Intro call"})
        self.assertEqual(s, 200, b)
        self.assertEqual(b["key"], "newco.com")
        r = self.get(self.kam)["newco.com"]
        self.assertEqual((r["prospect"], r["stage"], r["kam"]["email"], r["health"]), (True, "lead", KAM, "none"))
        self.assertEqual(self.kam.post("/api/crm/prospect", {"name": "Newco", "domain": "newco.com"})[0], 409)
        self.assertEqual(self.kam.post("/api/crm/prospect", {"name": "Bad", "domain": "not a domain"})[0], 400)
        self.assertEqual(self.kam.post("/api/crm/prospect", {"name": "Poly", "domain": "polyco.com"})[0], 409)
        self.signup("first@newco.com")                                                          # someone signs up: it is an account now
        r = self.get(self.boss)["newco.com"]
        self.assertEqual((r["prospect"], r["people"]), (False, 1))
        with db.connect() as conn:
            h = conn.execute("SELECT id FROM history WHERE entity = 'company' AND key = 'newco.com'").fetchone()
        ok, _ = history.undo(h["id"])
        self.assertTrue(ok)

    def test_07_person_fields(self):
        s, d, _ = self.boss.get("/api/hub/company?k=polyco.com")
        p = d["people"][0]
        self.assertIn("phone", p); self.assertFalse(p["decision_maker"])
        self.assertEqual(self.kam.post("/api/crm/person", {"id": p["id"], "decision_maker": True})[0], 200)
        self.assertTrue(self.boss.get("/api/hub/company?k=polyco.com")[1]["people"][0]["decision_maker"])
        self.assertEqual(self.kam.post("/api/crm/person", {"id": self.buyer["id"], "decision_maker": True})[0], 404)

    def test_08_feeds_the_needs_you_queue(self):
        self.kam.post("/api/crm/set", {"key": "polyco.com", "next_step": "Call back", "next_due": db.now() - 4 * DAY})
        s, b, _ = self.boss.get("/api/needs")
        g = {x["key"]: x for x in b["groups"]}
        self.assertIn("Call back", [i["title"] for i in g["overdue"]["items"]])
        self.assertEqual([i for i in g["overdue"]["items"] if i.get("act") == "company"][0]["key"], "polyco.com")
        self.assertIn("polyco.com", [i["key"] for i in g["red"]["items"]])                     # 60 days quiet in test_04: at risk
        s, b, _ = self.kam.get("/api/needs")
        self.assertNotIn("rivalco.com", [i.get("key") for x in b["groups"] for i in x["items"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
