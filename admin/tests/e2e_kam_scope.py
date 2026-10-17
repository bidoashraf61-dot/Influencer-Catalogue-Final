"""KAM scoped access + "My clients" (owner, 2026-10-11, programme item 82).

A key account manager sees only her clients (company domains mapped to her in domain_kam, plus
accounts naming her in users.kam) in every admin list, page, search, API and the copilot; anything
else answers "Not your client" (403). Owners and admins are unaffected. In the portal she opens
her clients' selections and reports, and the "Show locked data" switch reaches only them. The
domain mapping assigns new sign-ups and, when saved in Settings, existing accounts. All names
below are invented.

    python3 admin/tests/e2e_kam_scope.py
"""
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import assistant, db, gemini, guard, kam_scope, mailer, portal, server, team, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

KAM, OTHER = "mariam.k@hvkam.com", "omar.k@hvkam.com"


class KamScope(unittest.TestCase):
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
        db.set_setting("domain_kam", {"PolyCo.com": KAM, "rivalco.com": OTHER})
        cls.ready = False

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()
        mailer.OUTBOX.clear()
        if not KamScope.ready:
            self.world()
            KamScope.ready = True

    # ---------------------------------------------------------------- world --
    def world(self):
        W = KamScope
        self.signup("lead@polyco.com")
        self.signup("buyer@rivalco.com")
        self.signup("ceo@legacyco.com")
        W.mine = portal.user_by_email("lead@polyco.com")
        W.theirs = portal.user_by_email("buyer@rivalco.com")
        W.named = portal.user_by_email("ceo@legacyco.com")
        portal.update_profile(W.named["id"], kam=KAM)                      # named on the account, domain unmapped
        W.named = portal.user_by_email("ceo@legacyco.com")
        W.s_mine = db.save_selection(None, "Polyco Ramadan glow", ["HV-MI-001", "HV-MI-002"], {}, None, None, code_id=W.mine["code_id"])
        W.s_named = db.save_selection(None, "Legacy summer sun", ["HV-MI-005"], {}, None, None, code_id=W.named["code_id"])
        W.s_other = db.save_selection(None, "Rival secret launch", ["HV-MD-004"], {}, None, None, code_id=W.theirs["code_id"])
        W.k_mine = db.create_campaign("Polyco wave one", code_id=W.mine["code_id"], selection_id=W.s_mine)
        db.save_campaign(W.k_mine, status="live", starts_at=1, ends_at=2)
        W.k_other = db.create_campaign("Rival wave one", code_id=W.theirs["code_id"], selection_id=W.s_other)
        db.save_campaign(W.k_other, status="live", starts_at=1, ends_at=2)
        W.r_mine = db.create_request(W.mine["code_id"], "Lead", "Polyco", "lead@polyco.com", "", "Polyco Ramadan glow", "[]")
        W.r_other = db.create_request(W.theirs["code_id"], "Buyer", "Rivalco", "buyer@rivalco.com", "", "Rival secret launch", "[]")
        with db.connect() as conn:
            W.a_mine = conn.execute("INSERT INTO analysis_requests (code, code_id, at) VALUES (?,?,?)",
                                    ("HV-MI-001", W.mine["code_id"], db.now() - 3 * 86400)).lastrowid
            W.a_other = conn.execute("INSERT INTO analysis_requests (code, code_id, at) VALUES (?,?,?)",
                                     ("HV-MD-004", W.theirs["code_id"], db.now())).lastrowid
        W.kam, s, _ = self.member(KAM, "kam")
        self.assertEqual(s, 303)
        with db.connect() as conn:
            conn.execute("UPDATE admins SET name = 'Mariam K' WHERE email = ?", (KAM,))
        self.member(OTHER, "kam")

    def kam_portal(self):
        """Her own portal account (signed in by email), made once."""
        if getattr(KamScope, "_kp", None) is None:
            KamScope._kp = self.signup(KAM)[0]
        return KamScope._kp

    def tok(self, sid):
        return db.selection(sid)["token"]

    # ---------------------------------------------------------- the scope rule --
    def test_01_scope_function(self):
        k = db.admin_by_email(KAM)
        self.assertEqual(kam_scope.clients(k), frozenset({self.mine["code_id"], self.named["code_id"]}))
        self.assertEqual(kam_scope.clients(db.admin_by_email(OTHER)), frozenset({self.theirs["code_id"]}))
        self.assertIsNone(kam_scope.clients(db.admin_by_email("boss@hellovoice.co.uk")))
        self.assertEqual(self.mine["kam"], KAM)                             # the domain set it at sign-up

    # ------------------------------------------------------------ every list --
    def test_02_lists_are_hers_only(self):
        k = self.kam
        for path, mine, other in (
                ("/selections", "Polyco Ramadan glow", "Rival secret launch"),
                ("/campaigns", "Polyco wave one", "Rival wave one"),
                ("/clients", "lead@polyco.com", "buyer@rivalco.com"),
                ("/requests", "lead@polyco.com", "buyer@rivalco.com"),
                ("/portal", "lead@polyco.com", "buyer@rivalco.com"),
                ("/codes", "lead@polyco.com", "buyer@rivalco.com"),
                ("/", "lead@polyco.com", "buyer@rivalco.com")):
            s, body, _ = k.get(path)
            self.assertEqual(s, 200, path)
            self.assertIn(mine, body, path)
            self.assertNotIn(other, body, path)
        s, body, _ = k.get("/selections")
        self.assertIn("Legacy summer sun", body)                             # named on the account
        s, body, _ = k.get("/analysis")
        self.assertEqual(s, 200)
        self.assertNotIn("Rival secret launch", body)
        s, b, _ = k.get("/api/search?q=wave")
        self.assertEqual([x["label"] for x in b["campaigns"]], ["Polyco wave one"])
        s, b, _ = k.get("/api/search?q=rival")
        self.assertEqual((b["selections"], b["campaigns"], b["clients"]), ([], [], []))
        s, b, _ = k.get("/api/pulse")
        self.assertEqual((b["open"], b["a_open"]), (1, 1))

    # --------------------------------------------------------- not your client --
    def test_03_other_clients_are_refused(self):
        k = self.kam
        for path in ("/selections/edit?id=%d" % self.s_other, "/selections/fit?id=%d" % self.s_other,
                     "/campaigns/edit?id=%d" % self.k_other, "/campaigns/report?id=%d" % self.k_other,
                     "/campaigns/export.csv?id=%d" % self.k_other, "/campaigns/setup?selection=%d" % self.s_other,
                     "/portal/user?id=%d" % self.theirs["id"], "/portal/quote?sel=%d" % self.s_other,
                     "/analysis/json?c=HV-MD-004", "/planner?id=%d" % self.k_other,
                     "/analytics", "/history", "/portal?tab=usage", "/portal?tab=codes", "/settings"):
            s, body, _ = k.get(path)
            self.assertEqual(s, 403, path)
        s, body, _ = k.get("/selections/edit?id=%d" % self.s_other)
        self.assertIn("Not your client", body)
        for path, form in (("/selections/save", {"id": self.s_other, "name": "x"}),
                           ("/selections/delete", {"id": self.s_other}),
                           ("/quote/ready", {"id": self.s_other}),
                           ("/campaigns/status", {"id": self.k_other, "status": "ended"}),
                           ("/campaigns/delete", {"id": self.k_other}),
                           ("/selections/assign", {"id": self.s_mine, "client": self.theirs["code_id"]}),
                           ("/selections/new", {"mode": "scratch", "name": "Grab", "code_id": self.theirs["code_id"]}),
                           ("/selections/new", {"mode": "scratch", "name": "Unfiled"}),
                           ("/analysis/fulfil", {"id": self.a_other}),
                           ("/requests/handled", {"id": self.r_other, "handled": "1"}),
                           ("/portal/user/credits", {"id": self.theirs["id"], "amount": 50}),
                           ("/clients/preview", {"id": self.theirs["code_id"]}),
                           ("/codes/revoke", {"id": self.theirs["code_id"]}),
                           ("/settings/domain-kam", {"rows": 1, "domain_0": "rivalco.com", "kam_0": KAM})):
            s, body, _ = k.req("POST", path, form=form)
            self.assertEqual(s, 403, path)
        self.assertIsNotNone(db.selection(self.s_other))
        self.assertEqual(db.campaign(self.k_other)["status"], "live")
        self.assertEqual(kam_scope.domain_map()["rivalco.com"], OTHER)
        with db.connect() as conn:
            self.assertIsNone(conn.execute("SELECT handled_at FROM requests WHERE id = ?", (self.r_other,)).fetchone()[0])
        s, b, _ = k.post("/api/search", {})                                 # unknown POST: refused, never run
        self.assertIn(s, (403, 404))

    def test_04_full_rights_inside_scope(self):
        k = self.kam
        for path in ("/selections/edit?id=%d" % self.s_mine, "/campaigns/edit?id=%d" % self.k_mine,
                     "/campaigns/report?id=%d" % self.k_mine, "/portal/user?id=%d" % self.mine["id"],
                     "/analysis/json?c=HV-MI-001", "/portal/quote?sel=%d" % self.s_mine):
            self.assertEqual(k.get(path)[0], 200, path)
        s, _, r = k.req("POST", "/requests/handled", form={"id": self.r_mine, "handled": "1"})
        self.assertNotEqual(s, 403)
        s, _, r = k.req("POST", "/portal/user/save", form={"id": self.mine["id"], "name": "Lead Person", "kam": OTHER})
        self.assertEqual(s, 303)
        u = portal.user_by_id(self.mine["id"])
        self.assertEqual((u["name"], u["kam"]), ("Lead Person", KAM))      # a KAM cannot hand a client away
        s, _, r = k.req("POST", "/selections/new", form={"mode": "scratch", "name": "Polyco Eid", "code_id": self.mine["code_id"]})
        self.assertEqual(s, 303)
        self.assertTrue(any(x["name"] == "Polyco Eid" for x in db.list_selections()))

    def test_05_owner_unaffected(self):
        a = self.admin()
        s, body, _ = a.get("/selections")
        for name in ("Polyco Ramadan glow", "Legacy summer sun", "Rival secret launch"):
            self.assertIn(name, body)
        self.assertEqual(a.get("/selections/edit?id=%d" % self.s_other)[0], 200)
        self.assertEqual(a.get("/campaigns/edit?id=%d" % self.k_other)[0], 200)
        s, b, _ = a.get("/api/search?q=rival")
        self.assertEqual(len(b["selections"]), 1)
        self.assertEqual(a.get("/analytics")[0], 200)

    # ---------------------------------------------------------------- portal --
    def test_06_portal_kam_opens_her_clients_only(self):
        c = self.kam_portal()                                                # her own portal account
        s, me, _ = c.get("/api/me")
        self.assertTrue(me["staff"] and me["kam"])
        s, b, _ = c.get("/api/selection?s=" + self.tok(self.s_mine))
        self.assertTrue(b.get("ok"), b)
        self.assertEqual(b["role"], "admin")
        s, b, _ = c.get("/api/selection?s=" + self.tok(self.s_other))
        self.assertFalse(b.get("ok"))
        self.assertEqual(c.get("/api/campaign?t=" + db.campaign(self.k_mine)["token"])[0], 200)
        self.assertIn(c.get("/api/campaign?t=" + db.campaign(self.k_other)["token"])[0], (401, 404))
        # "Show locked data" reaches her clients' creators only, never everything
        c.post("/api/me/unlock", {"on": True})
        s, me, _ = c.get("/api/me")
        self.assertTrue(me["unlock"])
        s, b, _ = c.get("/api/creator?c=HV-MI-001")
        self.assertEqual(b["gate"]["state"], "unlocked")
        s, b, _ = c.get("/api/creator?c=HV-MD-004")
        self.assertNotEqual(b["gate"]["state"], "unlocked")
        self.assertFalse(c.get("/api/selection?s=" + self.tok(self.s_other))[1].get("ok"))
        # a client who is not a KAM gets no My clients
        cl, _ = self.signup("plain@plainco.com")
        self.assertFalse(cl.get("/api/me")[1].get("kam"))
        self.assertEqual(cl.get("/api/account/clients")[0], 403)

    def test_07_kam_admin_session_is_not_hellovoice_in_the_portal(self):
        k = self.kam
        self.assertFalse(k.get("/api/selection?s=" + self.tok(self.s_other))[1].get("ok"))
        self.assertTrue(k.get("/api/selection?s=" + self.tok(self.s_mine))[1].get("ok"))
        self.assertIn(k.get("/api/campaign?t=" + db.campaign(self.k_other)["token"])[0], (401, 404))
        self.assertEqual(k.get("/api/campaign?t=" + db.campaign(self.k_mine)["token"])[0], 200)

    def test_08_my_clients_payload(self):
        c = self.kam_portal()
        s, b, _ = c.get("/api/account/clients")
        self.assertEqual(s, 200, b)
        emails = [x["email"] for x in b["clients"]]
        self.assertEqual(sorted(emails), ["ceo@legacyco.com", "lead@polyco.com"])
        self.assertEqual(b["domains"], ["polyco.com"])
        poly = next(x for x in b["clients"] if x["email"] == "lead@polyco.com")
        self.assertIn("Polyco Ramadan glow", [s_["name"] for s_ in poly["selections"]])
        sel = next(s_ for s_ in poly["selections"] if s_["name"] == "Polyco Ramadan glow")
        self.assertEqual(sel["quote"]["key"], "live")                      # its campaign is live
        self.assertEqual(sel["counts"]["creators"], 2)
        self.assertIn("/selections/edit?id=%d" % self.s_mine, sel["admin"])
        camp = next(k_ for k_ in poly["campaigns"] if k_["name"] == "Polyco wave one")
        self.assertEqual(camp["status"], "live")
        self.assertIn("views", camp)
        self.assertEqual(poly["analyses"]["requested"], 1)
        self.assertIn(poly["analyses"]["items"][0]["state"], ("waiting", "late", "delivered"))
        self.assertIn("credits", poly)
        self.assertIn("/portal/user?id=%d" % self.mine["id"], poly["admin"])
        raw = json.dumps(b).lower()
        for word in ("cost", "margin", "price", "rival"):
            self.assertNotIn(word, raw)
        s, acc, _ = c.get("/api/account")
        self.assertTrue(acc["is_kam"])

    # ------------------------------------------------------ domain -> KAM --
    def test_09_domain_mapping(self):
        self.signup("first@newco.com")
        self.assertFalse(portal.user_by_email("first@newco.com")["kam"])
        a = self.admin()
        cur = kam_scope.domain_map()
        form = {"rows": len(cur) + 1}
        for i, (d, k_) in enumerate(sorted(cur.items())):
            form["domain_%d" % i], form["kam_%d" % i] = d, k_
        form["domain_%d" % len(cur)], form["kam_%d" % len(cur)] = "newco.com", KAM
        s, _, r = a.req("POST", "/settings/domain-kam", form=form)
        self.assertEqual(s, 303)
        self.assertEqual(portal.user_by_email("first@newco.com")["kam"], KAM)     # existing account updated
        self.signup("second@newco.com")
        self.assertEqual(portal.user_by_email("second@newco.com")["kam"], KAM)    # new sign-up assigned
        sc = kam_scope.clients(db.admin_by_email(KAM))
        self.assertIn(portal.user_by_email("second@newco.com")["code_id"], sc)
        s, body, _ = a.get("/settings")
        self.assertIn("Key account managers", body)
        self.assertIn("newco.com", body)

    # ---------------------------------------------------------------- copilot --
    def test_10_copilot_is_scoped(self):
        sc = kam_scope.clients(db.admin_by_email(KAM))
        kam_scope.begin(sc)
        try:
            ctx = {"who": KAM, "code_id": db.admin_code_id(), "kam_creators": kam_scope.current_creators()}
            self.assertIn("error", assistant.run_tool("admin", "sql_query", {"sql": "select 1"}, ctx))
            self.assertIn("error", assistant.run_tool("admin", "stats", {}, ctx))
            self.assertIn("error", assistant.run_tool("admin", "grant_credits", {"email": "buyer@rivalco.com", "amount": 5}, ctx))
            names = [x["name"] for x in assistant.run_tool("admin", "list_campaigns", {}, ctx)]
            self.assertIn("Polyco wave one", names)
            self.assertNotIn("Rival wave one", names)
            self.assertIn("error", assistant.run_tool("admin", "get_campaign", {"id": self.k_other}, ctx))
            self.assertIn("error", assistant.run_tool("admin", "client_overview", {"email": "buyer@rivalco.com"}, ctx))
            clients = [x["email"] for x in assistant.run_tool("admin", "list_clients", {}, ctx)]
            self.assertNotIn("buyer@rivalco.com", clients)
            names = [d["name"] for d in assistant.declarations("admin", kam=True)]
            self.assertNotIn("sql_query", names)
            self.assertNotIn("update_creator", names)
        finally:
            kam_scope.end()

    # ---------------------------------------------- item-level KAM (item 119) --
    def test_11_item_level_kam_and_invites(self):
        """Owner, 2026-10-17: the owner hands ONE selection/campaign of another client to a KAM; it is added to
        her clients (never replaces them), she is told, she can open it and invite the client's email to it."""
        db.set_setting("kams", ["Mariam K <%s>" % KAM, "Omar K <%s>" % OTHER])
        k, boss = self.kam, self.admin()
        # before: the other client's selection and campaign are refused to her
        self.assertEqual(k.get("/selections/edit?id=%d" % self.s_other)[0], 403)
        # she may not assign anything herself
        self.assertEqual(k.req("POST", "/selections/kam", form={"id": self.s_other, "kam": KAM})[0], 403)
        # the owner hands the selection and the campaign to her
        s, _, _ = boss.req("POST", "/selections/kam", form={"id": self.s_other, "kam": KAM})
        self.assertEqual(s, 303)
        s, _, _ = boss.req("POST", "/campaigns/kam", form={"id": self.k_other, "kam": KAM})
        self.assertEqual(s, 303)
        self.assertEqual(boss.req("POST", "/selections/kam", form={"id": self.s_other, "kam": "stranger@x.com"})[0], 303)
        self.assertEqual(db.kam_of_item("selection", self.s_other), KAM)    # an unknown KAM changed nothing
        self.assertTrue(any(KAM in str(m) for m in mailer.OUTBOX))          # she was emailed
        # now she opens them; her own clients still work; a third client's stays refused
        self.assertEqual(k.get("/selections/edit?id=%d" % self.s_other)[0], 200)
        self.assertEqual(k.get("/campaigns/edit?id=%d" % self.k_other)[0], 200)
        self.assertEqual(k.get("/selections/edit?id=%d" % self.s_mine)[0], 200)
        sel_list = k.get("/selections")[1]
        self.assertIn("Rival secret launch", sel_list)
        # the other KAM does not see what was handed to her
        self.assertEqual(self.member(OTHER, "kam")[1] in (303, 200), True)
        # she invites the client's email to the item
        s, _, _ = k.req("POST", "/selections/invite", form={"id": self.s_other, "do": "add", "email": "boss@rivalco.com"})
        self.assertEqual(s, 303)
        self.assertEqual([p["email"] for p in __import__("access").people(db.selection(self.s_other))], ["boss@rivalco.com"])
        s, _, _ = k.req("POST", "/campaigns/invite", form={"id": self.k_other, "do": "add", "email": "second@rivalco.com"})
        self.assertEqual(s, 303)
        # but not on a client that is not hers
        s, _, _ = k.req("POST", "/selections/invite", form={"id": self.s_named, "do": "add", "email": "x@legacyco.com"})
        self.assertEqual(s, 303)                                            # her client (named): allowed
        # taking it back closes it again
        boss.req("POST", "/selections/kam", form={"id": self.s_other, "kam": ""})
        boss.req("POST", "/campaigns/kam", form={"id": self.k_other, "kam": ""})
        self.assertEqual(k.get("/selections/edit?id=%d" % self.s_other)[0], 403)
        self.assertEqual(k.get("/campaigns/edit?id=%d" % self.k_other)[0], 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
