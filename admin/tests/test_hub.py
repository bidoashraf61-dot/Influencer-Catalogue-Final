"""The admin control hub on the profile (owner, 2026-10-18, item 129 phase 1): every company for an admin,
a KAM's own for her; people, their selections and campaigns; set a KAM; share by email.

    python3 admin/tests/test_hub.py
"""
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import db, gemini, guard, kam_scope, mailer, portal, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

KAM, OTHER, BOSS = "mariam.k@hvkam.com", "omar.k@hvkam.com", "boss@hellovoice.co.uk"


class Hub(unittest.TestCase):
    signup = base.Portal.signup
    admin = base.Portal.admin
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
        if not Hub.ready:
            W = Hub
            self.signup("lead@polyco.com"); self.signup("second@polyco.com"); self.signup("buyer@rivalco.com")
            W.lead = portal.user_by_email("lead@polyco.com"); W.buyer = portal.user_by_email("buyer@rivalco.com")
            W.s1 = db.save_selection(None, "Polyco glow", ["HV-MI-001"], {}, None, None, code_id=W.lead["code_id"])
            W.s2 = db.save_selection(None, "Rival secret", ["HV-MD-004"], {}, None, None, code_id=W.buyer["code_id"])
            W.k1 = db.create_campaign("Polyco wave", code_id=W.lead["code_id"], selection_id=W.s1)
            db.save_campaign(W.k1, status="live", starts_at=1, ends_at=2)
            W.k2 = db.create_campaign("Rival wave", code_id=W.buyer["code_id"], selection_id=W.s2)
            self.member(BOSS, "owner"); self.member(KAM, "kam"); self.member(OTHER, "kam")
            W.boss = self.signup(BOSS)[0]; W.kam = self.signup(KAM)[0]; W.plain = self.signup("plain@plainco.com")[0]
            Hub.ready = True

    def test_01_who_sees_what(self):
        self.assertEqual(self.plain.get("/api/hub/companies")[0], 403)                    # a normal client: no hub
        s, b, _ = self.boss.get("/api/hub/companies")
        self.assertEqual(s, 200, b)
        names = {c["domain"]: c for c in b["companies"]}
        self.assertEqual(set(names) & {"polyco.com", "rivalco.com"}, {"polyco.com", "rivalco.com"})
        self.assertEqual(names["polyco.com"]["people"], 2)
        self.assertEqual((names["polyco.com"]["selections"], names["polyco.com"]["campaigns"], names["polyco.com"]["live"]), (1, 1, 1))
        self.assertEqual(names["polyco.com"]["kam"]["email"], KAM)
        self.assertEqual([k["email"] for k in b["kams"]], [KAM, OTHER])
        s, kb, _ = self.kam.get("/api/hub/companies")                                     # a KAM: only her own company
        self.assertEqual(s, 200)
        self.assertEqual({c["domain"] for c in kb["companies"] if c["domain"]} & {"polyco.com", "rivalco.com"}, {"polyco.com"})
        self.assertEqual(self.boss.get("/api/account")[1].get("hub"), "admin")
        self.assertEqual(self.kam.get("/api/account")[1].get("hub"), "kam")

    def test_02_company_detail(self):
        s, d, _ = self.boss.get("/api/hub/company?k=polyco.com")
        self.assertEqual(s, 200)
        by = {p["email"]: p for p in d["people"]}
        self.assertEqual([x["name"] for x in by["lead@polyco.com"]["selections"]], ["Polyco glow"])
        self.assertEqual(by["lead@polyco.com"]["campaigns"][0]["status"], "live")
        self.assertEqual(by["lead@polyco.com"]["selections"][0]["link"], "selection/#s=" + db.selection(self.s1)["token"])
        self.assertEqual(self.boss.get("/api/hub/company?k=nope.example")[0], 404)
        self.assertEqual(self.kam.get("/api/hub/company?k=rivalco.com")[0], 404)         # not hers

    def test_03_kam_controls(self):
        b = self.boss
        s, j, _ = b.post("/api/hub/kam", {"kind": "company", "ref": "polyco.com", "kam": OTHER})
        self.assertEqual((s, kam_scope.domain_map()["polyco.com"]), (200, OTHER))
        b.post("/api/hub/kam", {"kind": "company", "ref": "polyco.com", "kam": KAM})
        s, j, _ = b.post("/api/hub/kam", {"kind": "person", "ref": self.lead["id"], "kam": OTHER})
        self.assertEqual((s, portal.user_by_id(self.lead["id"])["kam"]), (200, OTHER))
        s, j, _ = b.post("/api/hub/kam", {"kind": "selection", "ref": self.s2, "kam": KAM})
        self.assertEqual((s, db.kam_of_item("selection", self.s2)), (200, KAM))
        s, j, _ = b.post("/api/hub/kam", {"kind": "campaign", "ref": self.k2, "kam": KAM})
        self.assertEqual((s, db.kam_of_item("campaign", self.k2)), (200, KAM))
        self.assertEqual(b.post("/api/hub/kam", {"kind": "selection", "ref": self.s2, "kam": "stranger@x.com"})[0], 400)
        # a KAM cannot change anyone's account manager
        self.assertEqual(self.kam.post("/api/hub/kam", {"kind": "selection", "ref": self.s1, "kam": OTHER})[0], 400)
        # what was handed to her appears under "Handed to you"
        s, kb, _ = self.kam.get("/api/hub/companies")
        self.assertIn("handed", [c["key"] for c in kb["companies"]])
        s, hd, _ = self.kam.get("/api/hub/company?k=handed")
        self.assertEqual(s, 200)
        self.assertIn("Rival secret", [x["name"] for p in hd["people"] for x in p["selections"]])
        b.post("/api/hub/kam", {"kind": "selection", "ref": self.s2, "kam": ""})
        b.post("/api/hub/kam", {"kind": "campaign", "ref": self.k2, "kam": ""})
        b.post("/api/hub/kam", {"kind": "person", "ref": self.lead["id"], "kam": ""})

    def test_04_share_by_email(self):
        s, j, _ = self.boss.post("/api/hub/share", {"kind": "selection", "ref": self.s2, "email": "newbie@rivalco.com"})
        self.assertEqual((s, j.get("state")), (200, "invited"), j)
        s, j, _ = self.boss.post("/api/hub/share", {"kind": "campaign", "ref": self.k2, "email": "second@rivalco.com"})
        self.assertEqual(s, 200, j)
        self.assertEqual(self.boss.post("/api/hub/share", {"kind": "selection", "ref": self.s2, "email": "nope"})[0], 400)
        # a KAM shares inside her scope only
        s, j, _ = self.kam.post("/api/hub/share", {"kind": "selection", "ref": self.s1, "email": "x@polyco.com"})
        self.assertEqual(s, 200, j)
        s, j, _ = self.kam.post("/api/hub/share", {"kind": "selection", "ref": self.s2, "email": "x@rivalco.com"})
        self.assertEqual(s, 400)
        self.assertIn("do not manage", j["message"])

    def test_05_move_to_another_client(self):
        b, k = self.boss, self.kam
        s, j, _ = b.get("/api/hub/people?q=rivalco")
        self.assertEqual(s, 200)
        self.assertIn("buyer@rivalco.com", [p["email"] for p in j["people"]])
        self.assertEqual(self.plain.get("/api/hub/people?q=rivalco")[0], 403)
        self.assertEqual(b.get("/api/hub/people?q=r")[1]["people"], [])                   # too short to search
        second = portal.user_by_email("second@polyco.com")
        # an admin moves a client's selection (and its campaign) to another client
        s, j, _ = b.post("/api/hub/move", {"kind": "selection", "ref": self.s2, "to": self.lead["id"], "related": True, "tell": False})
        self.assertEqual(s, 200, j)
        self.assertEqual(db.selection(self.s2)["code_id"], self.lead["code_id"])
        self.assertEqual(db.campaign(self.k2)["code_id"], self.lead["code_id"])           # it came along
        s, j, _ = b.post("/api/hub/move", {"kind": "selection", "ref": self.s2, "to": self.buyer["id"], "related": True, "tell": False})
        self.assertEqual((s, db.selection(self.s2)["code_id"]), (200, self.buyer["code_id"]))
        # a campaign always moves as a package: its selection and brief come with it
        with db.connect() as conn:
            conn.execute("INSERT INTO briefs (code_id, selection_id, source, answers, created_at) VALUES (?,?,?,?,?)",
                         (self.buyer["code_id"], self.s2, "text", "{}", db.now()))
        s, j, _ = b.post("/api/hub/move", {"kind": "campaign", "ref": self.k2, "to": self.lead["id"], "related": False, "tell": False})
        self.assertEqual(s, 200, j)
        self.assertEqual((db.campaign(self.k2)["code_id"], db.selection(self.s2)["code_id"]), (self.lead["code_id"], self.lead["code_id"]))
        self.assertIn("selection", j["message"])
        with db.connect() as conn:
            self.assertEqual({r[0] for r in conn.execute("SELECT code_id FROM briefs WHERE selection_id = ?", (self.s2,))}, {self.lead["code_id"]})
        b.post("/api/hub/move", {"kind": "campaign", "ref": self.k2, "to": self.buyer["id"], "related": False, "tell": False})
        self.assertEqual(db.selection(self.s2)["code_id"], self.buyer["code_id"])
        self.assertEqual(b.post("/api/hub/move", {"kind": "selection", "ref": self.s2, "to": 999999})[0], 400)
        # a KAM moves only inside her own clients
        s, j, _ = k.post("/api/hub/move", {"kind": "selection", "ref": self.s1, "to": second["id"], "related": True, "tell": False})
        self.assertEqual((s, db.selection(self.s1)["code_id"]), (200, second["code_id"]), j)
        s, j, _ = k.post("/api/hub/move", {"kind": "selection", "ref": self.s1, "to": self.buyer["id"], "related": True, "tell": False})
        self.assertEqual(s, 400)
        self.assertIn("own clients", j["message"])
        s, j, _ = k.post("/api/hub/move", {"kind": "selection", "ref": self.s2, "to": second["id"]})
        self.assertEqual(s, 400)
        self.assertIn("do not manage", j["message"])
        k.post("/api/hub/move", {"kind": "selection", "ref": self.s1, "to": self.lead["id"], "related": True, "tell": False})
        self.assertEqual(db.selection(self.s1)["code_id"], self.lead["code_id"])

    def test_06_team_is_not_a_client_and_kam_options(self):
        """Owner, 2026-10-18: HelloVoice (owner) and BlueHolding (the account managers) are not clients; their emails are
        the KAM choices; items filed under team accounts or plain access codes show in "Not filed under a client"."""
        team = self.signup("salma@blueholding.co.uk")[0]
        tu = portal.user_by_email("salma@blueholding.co.uk")
        tsel = db.save_selection(None, "Jamjoom campaign", ["HV-MI-001"], {}, None, None, code_id=tu["code_id"])
        tcamp = db.create_campaign("Jamjoom Wave 1", code_id=tu["code_id"], selection_id=tsel)
        with db.connect() as conn:                                              # a plain access code that holds work
            cur = conn.execute("INSERT INTO codes (code_hash, hint, label, created_at) VALUES ('h-test', '····', 'Shared pharma code', ?)", (db.now(),))
            loose = cur.lastrowid
        lsel = db.save_selection(None, "Loose shortlist", ["HV-MI-002"], {}, None, None, code_id=loose)
        s, b, _ = self.boss.get("/api/hub/companies")
        self.assertEqual(s, 200)
        keys = [c["key"] for c in b["companies"]]
        self.assertNotIn("blueholding.co.uk", keys)                              # not a client
        self.assertNotIn("hellovoice.co.uk", keys)
        self.assertEqual(keys[0], "unassigned")                                  # flagged group first
        emails = [k["email"] for k in b["kams"]]
        self.assertIn("salma@blueholding.co.uk", emails)                         # team emails are the KAM choices
        self.assertNotIn("buyer@rivalco.com", emails)                            # a client is not
        s, d, _ = self.boss.get("/api/hub/company?k=unassigned")
        self.assertEqual(s, 200)
        names = {p["name"]: p for p in d["people"]}
        self.assertIn("Jamjoom campaign", [x["name"] for p in d["people"] for x in p["selections"]])
        self.assertIn("Jamjoom Wave 1", [x["name"] for p in d["people"] for x in p["campaigns"]])
        self.assertIn("Shared pharma code", names)                               # the plain code is listed by its label
        # an owner or admin also sees these in their own profile (Selections and Campaigns tabs)
        sm = self.boss.get("/api/account")[1]
        self.assertIn("Jamjoom campaign", [x["name"] for x in sm["selections"]])
        self.assertIn("Loose shortlist", [x["name"] for x in sm["selections"]])
        self.assertIn("Shared pharma code", [x["owner"] for x in sm["selections"] if x["name"] == "Loose shortlist"])
        self.assertNotIn("Loose shortlist", [x["name"] for x in self.plain.get("/api/account")[1]["selections"]])   # a client never does
        self.assertNotIn("Loose shortlist", [x["name"] for x in self.kam.get("/api/account")[1]["selections"]])     # nor a KAM
        self.assertEqual(self.kam.get("/api/hub/company?k=unassigned")[0], 404)  # a KAM never sees this group
        self.assertNotIn("unassigned", [c["key"] for c in self.kam.get("/api/hub/companies")[1]["companies"]])
        # a team email can be set as the account manager; a stranger cannot
        s, j, _ = self.boss.post("/api/hub/kam", {"kind": "company", "ref": "polyco.com", "kam": "salma@blueholding.co.uk"})
        self.assertEqual((s, kam_scope.domain_map()["polyco.com"]), (200, "salma@blueholding.co.uk"))
        self.boss.post("/api/hub/kam", {"kind": "company", "ref": "polyco.com", "kam": KAM})
        # team accounts are not move targets
        self.assertEqual(self.boss.get("/api/hub/people?q=salma")[1]["people"], [])
        # a stray item can be moved to its client
        s, j, _ = self.boss.post("/api/hub/move", {"kind": "selection", "ref": lsel, "to": self.lead["id"], "related": True, "tell": False})
        self.assertEqual((s, db.selection(lsel)["code_id"]), (200, self.lead["code_id"]))

    def test_07_assign_to_plain_code_and_delete(self):
        """Owner, 2026-10-18: assign a campaign to a client that only has an access code; delete a campaign (History keeps it)."""
        import history
        with db.connect() as conn:
            code = conn.execute("INSERT INTO codes (code_hash, hint, label, created_at) VALUES ('h-plain', '····', 'Plainco shared code', ?)", (db.now(),)).lastrowid
        sel = db.save_selection(None, "Plainco picks", ["HV-MI-001"], {}, None, None, code_id=self.buyer["code_id"])
        camp = db.create_campaign("Plainco push", code_id=self.buyer["code_id"], selection_id=sel)
        s, j, _ = self.boss.get("/api/hub/people?q=plainco")
        self.assertEqual(s, 200)
        hit = [p for p in j["people"] if p["kind"] == "code"]
        self.assertEqual([(p["name"], p["code_id"]) for p in hit], [("Plainco shared code", code)])
        # a KAM cannot assign to a code outside her clients (and does not even see it)
        self.assertEqual(self.kam.get("/api/hub/people?q=plainco")[1]["people"], [])
        self.assertEqual(self.kam.post("/api/hub/move", {"kind": "campaign", "ref": camp, "code": code, "related": False, "tell": False})[0], 400)
        s, j, _ = self.boss.post("/api/hub/move", {"kind": "campaign", "ref": camp, "code": code, "related": False, "tell": False})
        self.assertEqual((s, db.campaign(camp)["code_id"]), (200, code), j)
        # delete: a KAM outside her scope is refused; an admin deletes; History has it
        self.assertEqual(self.kam.post("/api/hub/delete", {"kind": "campaign", "ref": camp})[0], 400)
        self.assertEqual(self.boss.post("/api/hub/delete", {"kind": "selection", "ref": sel})[0], 400)       # only campaigns
        self.assertEqual(self.plain.post("/api/hub/delete", {"kind": "campaign", "ref": camp})[0], 403)
        s, j, _ = self.boss.post("/api/hub/delete", {"kind": "campaign", "ref": camp})
        self.assertEqual(s, 200, j)
        self.assertIsNone(db.campaign(camp))
        self.assertTrue(any("Deleted campaign Plainco push" in (r["label"] or "") for r in history.listing("campaign")))
        self.assertEqual(self.boss.post("/api/hub/delete", {"kind": "campaign", "ref": camp})[0], 400)       # already gone

    def test_08_all_campaigns_and_package_delete(self):
        """Owner, 2026-10-18: every campaign is reachable from the panel (even one filed under nobody) and Delete takes the
        campaign with its selection and brief, unless another campaign uses the selection."""
        import history
        sel = db.save_selection(None, "Orphan picks", ["HV-MI-001"], {}, None, None, code_id=None)
        camp = db.create_campaign("Nobody's campaign", code_id=None, selection_id=sel)
        with db.connect() as conn:
            conn.execute("INSERT INTO briefs (code_id, selection_id, source, answers, created_at) VALUES (?,?,?,?,?)", (1, sel, "text", "{}", db.now()))
        s, j, _ = self.boss.get("/api/hub/campaigns?q=nobody")
        self.assertEqual(s, 200)
        self.assertEqual([(c["name"], c["owner"]["kind"], c["selection"]) for c in j["items"]], [("Nobody's campaign", "none", "Orphan picks")])
        s, j, _ = self.boss.get("/api/hub/campaigns")
        self.assertGreaterEqual(j["total"], 3)
        self.assertEqual(self.plain.get("/api/hub/campaigns")[0], 403)
        kn = [c["name"] for c in self.kam.get("/api/hub/campaigns")[1]["items"]]
        self.assertNotIn("Nobody's campaign", kn)                                  # a KAM only sees her own
        # a second campaign on the same selection keeps it alive
        camp2 = db.create_campaign("Second wave", code_id=None, selection_id=sel)
        s, j, _ = self.boss.post("/api/hub/delete", {"kind": "campaign", "ref": camp2, "with_selection": True})
        self.assertEqual(s, 200, j)
        self.assertIsNotNone(db.selection(sel))                                    # still used by the first campaign
        self.assertIn("stays", j["message"])
        s, j, _ = self.boss.post("/api/hub/delete", {"kind": "campaign", "ref": camp, "with_selection": True})
        self.assertEqual(s, 200, j)
        self.assertIsNone(db.campaign(camp))
        self.assertIsNone(db.selection(sel))                                       # the package went together
        with db.connect() as conn:
            self.assertIsNotNone(conn.execute("SELECT deleted_at FROM briefs WHERE selection_id = ?", (sel,)).fetchone()[0])
        self.assertTrue(any("Deleted selection Orphan picks" in (r["label"] or "") for r in history.listing("selection")))
        # campaign only, selection kept
        sel3 = db.save_selection(None, "Keep me", ["HV-MI-001"], {}, None, None, code_id=None)
        camp3 = db.create_campaign("Just the campaign", code_id=None, selection_id=sel3)
        s, j, _ = self.boss.post("/api/hub/delete", {"kind": "campaign", "ref": camp3, "with_selection": False})
        self.assertEqual((s, db.campaign(camp3), db.selection(sel3) is not None), (200, None, True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
