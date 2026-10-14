"""Control Centre step 4 (item 101): one Clients page with a side panel, and the selections-and-campaigns board.

    python3 admin/tests/e2e_hub.py
"""
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402
from e2e_portal import Client  # noqa: E402

import auth, db, guard, portal, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


class Hub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base.seed()
        views.set_base("")
        db.set_setting("signup_mode", "approval")
        cls.waiting = portal.create_user("buyer@samplepharma.com", "Sara", "Sample Pharma")
        db.set_setting("signup_mode", "open")
        cls.active = portal.create_user("lead@sampleretail.com", "Ahmed", "Sample Retail")
        cls.team = portal.create_user("marwa@blueholding.co.uk", "Marwa", "Blueholding")
        u = portal.user_by_email("lead@sampleretail.com")
        db.save_selection(None, "Retail shortlist", ["HV-MI-001", "HV-MI-002"], {}, None, None, code_id=u["code_id"])
        t = portal.user_by_email("marwa@blueholding.co.uk")
        db.save_selection(None, "Team test list", ["HV-MI-005"], {}, None, None, code_id=t["code_id"])
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()

    def admin(self):
        c = Client(self.base)
        c.req("POST", "/login", form={"email": "boss@hellovoice.co.uk", "password": "correct-horse-battery"})
        c.req("POST", "/reauth", form={"password": "correct-horse-battery", "next": "/"})
        return c

    def test_1_one_list_with_filters(self):
        a = self.admin()
        s, body, _ = a.get("/clients")
        self.assertEqual(s, 200)
        for name in ("Sara", "Ahmed", "Marwa"):
            self.assertIn(name, body)
        s, body, _ = a.get("/clients?show=waiting")
        self.assertIn("Sara", body)
        self.assertNotIn("lead@sampleretail.com", body)
        s, body, _ = a.get("/clients?show=team")
        self.assertIn("Marwa", body)
        self.assertNotIn("buyer@samplepharma.com", body)

    def test_2_approve_from_the_row_comes_back_here(self):
        a = self.admin()
        u = portal.user_by_email("buyer@samplepharma.com")
        s, _, r = a.req("POST", "/portal/user/status", form={"id": str(u["id"]), "status": "active", "back": "/clients?show=waiting"})
        self.assertEqual(s, 303)
        self.assertTrue(r.headers["Location"].startswith("/clients"), r.headers["Location"])
        self.assertEqual(portal.user_by_email("buyer@samplepharma.com")["status"], "active")

    def test_3_panel_shows_credits_selections_and_preview(self):
        a = self.admin()
        u = portal.user_by_email("lead@sampleretail.com")
        s, body, _ = a.get("/clients?open=u%d" % u["id"])
        self.assertIn("Retail shortlist", body)
        self.assertIn("Add credits", body)
        self.assertIn("View the catalogue as them", body)
        self.assertIn("open-link", body)                       # the client's own view of each selection

    def test_4_board_has_six_columns_and_hides_team_tests(self):
        a = self.admin()
        s, body, _ = a.get("/work")
        self.assertEqual(s, 200)
        for col in ("Draft", "Quote requested", "Quote ready", "Approved", "Campaign live", "Completed"):
            self.assertIn(col, body)
        self.assertIn("Retail shortlist", body)
        self.assertNotIn("Team test list", body)
        self.assertIn("Team test list", a.get("/work?team=1")[1])

    def test_6_board_moves(self):
        import lifecycle
        a = self.admin()
        sel = next(x for x in db.list_selections() if x["name"] == "Retail shortlist")
        s, b, _ = a.post("/api/admin/board/move", {"kind": "sel", "id": sel["id"], "to": "ready", "note": "Prices inside"})
        self.assertEqual((s, b["ok"]), (200, True), b)
        self.assertEqual(lifecycle.state_of(db.selection(sel["id"]))["key"], "ready")
        s, b, _ = a.post("/api/admin/board/move", {"kind": "sel", "id": sel["id"], "to": "requested"})
        self.assertNotEqual(lifecycle.state_of(db.selection(sel["id"]))["key"], "ready")
        a.post("/api/admin/board/move", {"kind": "sel", "id": sel["id"], "to": "ready"})
        s, b, _ = a.post("/api/admin/board/move", {"kind": "sel", "id": sel["id"], "to": "approved"})
        self.assertEqual(lifecycle.state_of(db.selection(sel["id"]))["key"], "approved")   # approved for the client
        s, b, _ = a.post("/api/admin/board/move", {"kind": "sel", "id": sel["id"], "to": "requested"})
        self.assertEqual(s, 400)                                  # an approved quote is not taken back from here
        cid = db.create_campaign("Board camp", code_id=sel["code_id"])
        s, b, _ = a.post("/api/admin/board/move", {"kind": "camp", "id": cid, "to": "live"})
        self.assertIn("/campaigns/edit", b.get("go", ""))         # no dates yet: sent to set them up
        db.save_campaign(cid, status="live")
        s, b, _ = a.post("/api/admin/board/move", {"kind": "camp", "id": cid, "to": "approved"})
        self.assertEqual(db.campaign(cid)["status"], "draft")       # taken offline
        db.save_campaign(cid, status="live")
        s, b, _ = a.post("/api/admin/board/move", {"kind": "camp", "id": cid, "to": "completed"})
        self.assertEqual(db.campaign(cid)["status"], "ended")
        self.assertEqual(Client(self.base).post("/api/admin/board/move", {"kind": "camp", "id": cid, "to": "live"})[0], 403)

    def test_5_old_pages_still_open(self):
        a = self.admin()
        for p in ("/clients/by-code", "/clients?archived=1", "/selections", "/portal", "/codes"):
            self.assertEqual(a.get(p)[0], 200, p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
