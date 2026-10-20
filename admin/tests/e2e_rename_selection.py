"""Rename a selection (portal item 173).

- the owner renames from the selection page / profile (POST /api/selection/rename): the name is
  trimmed and checked (1 to 80 characters), History records it, the payloads carry can_rename;
- someone invited to it (the client's own controls) may; a colleague who can only look, an outsider
  and a signed-out visitor cannot (403 / 401), and their payloads say can_rename false;
- a stale tab re-saving with the name it loaded never writes the old name back;
- a legacy quote request matched by the OLD name is pinned first, so the lifecycle survives;
- HelloVoice renames from the admin lists (POST /selections/rename, JSON or a plain form), the lists
  draw the inline control, a read-only viewer gets none; a key account manager renames her own
  client's selection (admin and portal) and never another's;
- Helvi's rename_selection tool follows the same rule.

Same harness as e2e_portal.py (a throwaway copy of admin/*.py, an empty database, captured mail),
so it never touches catalogue.db or the network.

    python3 admin/tests/e2e_rename_selection.py
"""
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import assistant, db, gemini, guard, history, lifecycle, mailer, portal, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

KAM, OTHER_KAM = "rania.k@hvkam-rn.com", "fadi.k@hvkam-rn.com"
JS = {"X-HV-Rename": "1"}


class RenameSelection(unittest.TestCase):
    signup = base.Portal.signup
    admin = base.Portal.admin
    member = base.Portal.member

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        db.set_setting("domain_kam", {"kamclient-rn.com": KAM, "otherclient-rn.com": OTHER_KAM})
        mailer.CAPTURE = True
        gemini.STUB = base.stub
        views.set_base("")
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

    def sel(self, c, name, codes=("HV-MI-001", "HV-MI-002")):
        s, b, _ = c.post("/api/selection", {"name": name, "codes": list(codes)})
        self.assertEqual(s, 200, b)
        return b["token"]

    def acct_row(self, c, token):
        s, b, _ = c.get("/api/account")
        self.assertEqual(s, 200, b)
        return {x["token"]: x for x in b["selections"]}.get(token)

    def history_labels(self, sid):
        with db.connect() as conn:
            return [(r["label"], r["who"]) for r in conn.execute(
                "SELECT label, who FROM history WHERE entity = 'selection' AND key = ? ORDER BY id", (str(sid),))]

    # ------------------------------------------------------------------ owner --
    def test_01_owner_renames_and_it_shows_everywhere(self):
        c, _ = self.signup("owner@rename-one.com")
        token = self.sel(c, "Ramadan glow")
        self.assertTrue(c.get("/api/selection?s=" + token)[1]["can_rename"])
        self.assertTrue(self.acct_row(c, token)["can_rename"])
        s, b, _ = c.post("/api/selection/rename", {"token": token, "name": "   Ramadan   glow  —  final  "})
        self.assertEqual((s, b.get("ok"), b.get("name")), (200, True, "Ramadan glow — final"), b)
        self.assertEqual(db.selection(token=token)["name"], "Ramadan glow — final")
        self.assertEqual(c.get("/api/selection?s=" + token)[1]["name"], "Ramadan glow — final")
        self.assertEqual(self.acct_row(c, token)["name"], "Ramadan glow — final")
        sid = db.selection(token=token)["id"]
        self.assertIn(("Renamed selection Ramadan glow to Ramadan glow — final", "client: owner@rename-one.com"),
                      self.history_labels(sid))
        # the same name again changes nothing and records nothing
        n = len(self.history_labels(sid))
        s, b, _ = c.post("/api/selection/rename", {"token": token, "name": "Ramadan glow — final"})
        self.assertEqual((s, b.get("ok")), (200, True))
        self.assertEqual(len(self.history_labels(sid)), n)
        # a campaign made from it reads the new name through the selection
        k = db.create_campaign("Wave one", code_id=db.selection(sid)["code_id"], selection_id=sid)
        with db.connect() as conn:
            row = conn.execute("SELECT s.name FROM campaigns k JOIN selections s ON s.id = k.selection_id WHERE k.id = ?", (k,)).fetchone()
        self.assertEqual(row["name"], "Ramadan glow — final")

    def test_02_name_rules(self):
        c, _ = self.signup("owner@rename-two.com")
        token = self.sel(c, "Rules")
        for raw, reason in (("", "empty"), ("     ", "empty"), ("<>", "empty"), ("x" * 81, "long")):
            s, b, _ = c.post("/api/selection/rename", {"token": token, "name": raw})
            self.assertEqual((s, b.get("reason")), (400, reason), raw)
            self.assertTrue(b.get("message"))
        self.assertEqual(db.selection(token=token)["name"], "Rules")
        s, b, _ = c.post("/api/selection/rename", {"token": token, "name": "y" * 80})
        self.assertEqual((s, b.get("name")), (200, "y" * 80))
        s, b, _ = c.post("/api/selection/rename", {"token": token, "name": "<b>Bold</b> plan"})
        self.assertEqual(b.get("name"), "bBold/b plan")                 # no markup can be stored
        s, b, _ = c.post("/api/selection/rename", {"token": "no-such-token", "name": "Nope"})
        self.assertEqual((s, b.get("reason")), (404, "missing"))

    # ------------------------------------------------------- who may not --
    def test_03_colleague_invitee_outsider_cannot(self):
        c, _ = self.signup("owner@rename-team.com")
        token = self.sel(c, "Team list")
        sid = db.selection(token=token)["id"]
        col, _ = self.signup("peer@rename-team.com")                    # same company: may look
        self.assertEqual(col.get("/api/selection?s=" + token)[0], 200)
        self.assertFalse(col.get("/api/selection?s=" + token)[1]["can_rename"])
        self.assertFalse(self.acct_row(col, token)["can_rename"])
        s, b, _ = col.post("/api/selection/rename", {"token": token, "name": "Hijacked"})
        self.assertEqual((s, b.get("reason")), (403, "forbidden"))

        # invited one by one: the client's own controls (2026-10-15), so they may rename (decision 2026-10-20)
        inv, _ = self.signup("guest@rename-invited.com")
        db.grant_selection(sid, portal.user_by_email("guest@rename-invited.com")["code_id"], by="test")
        self.assertEqual(inv.get("/api/selection?s=" + token)[0], 200)
        self.assertTrue(inv.get("/api/selection?s=" + token)[1]["can_rename"])
        self.assertTrue(self.acct_row(inv, token)["can_rename"])
        s, b, _ = inv.post("/api/selection/rename", {"token": token, "name": "Invitee named it"})
        self.assertEqual((s, b.get("name")), (200, "Invitee named it"), b)
        self.assertIn(("Renamed selection Team list to Invitee named it", "client: guest@rename-invited.com"), self.history_labels(sid))
        c.post("/api/selection/rename", {"token": token, "name": "Team list"})

        out, _ = self.signup("x@rename-elsewhere.com")
        s, b, _ = out.post("/api/selection/rename", {"token": token, "name": "Hijacked"})
        self.assertEqual(s, 403)
        anon = base.Client(self.base)
        s, b, _ = anon.post("/api/selection/rename", {"token": token, "name": "Hijacked"})
        self.assertEqual(s, 401)
        self.assertEqual(db.selection(token=token)["name"], "Team list")

    def test_04_deleted_selection_cannot_be_renamed_by_client(self):
        c, _ = self.signup("owner@rename-del.com")
        token = self.sel(c, "Gone soon")
        self.assertEqual(c.post("/api/selection/delete", {"token": token})[0], 200)
        s, b, _ = c.post("/api/selection/rename", {"token": token, "name": "Back"})
        self.assertEqual((s, b.get("reason")), (404, "missing"))

    # ------------------------------------------------------- lifecycle --
    def test_05_legacy_request_survives_rename(self):
        c, _ = self.signup("owner@rename-quote.com")
        token = self.sel(c, "Quote me")
        sel = db.selection(token=token)
        self.assertIsNone(sel["request_id"])
        rid = db.create_request(sel["code_id"], "Owner", "Quote Co", "owner@rename-quote.com", "", "Quote me", "[]")
        self.assertEqual(lifecycle.chip(db.selection(sel["id"]))["key"], "requested")
        s, b, _ = c.post("/api/selection/rename", {"token": token, "name": "Quote me, renamed"})
        self.assertEqual(s, 200, b)
        after = db.selection(sel["id"])
        self.assertEqual(after["request_id"], rid)
        self.assertEqual(lifecycle.chip(after)["key"], "requested")

    # -------------------------------------------------------- stale tab --
    def test_05b_stale_tab_does_not_write_the_old_name_back(self):
        c, _ = self.signup("owner@rename-stale.com")
        token = self.sel(c, "Old name")
        s, b, _ = c.post("/api/selection/rename", {"token": token, "name": "New name"})
        self.assertEqual(s, 200, b)
        # a tab that loaded "Old name" adds a creator: the creators change, the name stays new
        s, b, _ = c.post("/api/selection", {"token": token, "name": "Old name", "loaded_name": "Old name",
                                             "codes": ["HV-MI-001", "HV-MI-002", "HV-MD-003"]})
        self.assertEqual((s, b.get("token")), (200, token), b)
        row = db.selection(token=token)
        self.assertEqual(row["name"], "New name")
        self.assertEqual(len(__import__("json").loads(row["codes"])), 3)
        # a name the person really changed on that page still applies, through the rename rule
        s, b, _ = c.post("/api/selection", {"token": token, "name": "Typed on purpose", "loaded_name": "Old name",
                                             "codes": ["HV-MI-001", "HV-MI-002", "HV-MD-003"]})
        self.assertEqual(db.selection(token=token)["name"], "Typed on purpose")
        self.assertIn(("Renamed selection New name to Typed on purpose", "client: owner@rename-stale.com"),
                      self.history_labels(row["id"]))
        # an invalid name in a save is ignored, the creators still save
        c.post("/api/selection", {"token": token, "name": "q" * 100, "codes": ["HV-MI-001"]})
        row = db.selection(token=token)
        self.assertEqual((row["name"], __import__("json").loads(row["codes"])), ("Typed on purpose", ["HV-MI-001"]))

    # ------------------------------------------------------------ admin --
    def test_06_admin_renames_from_the_lists(self):
        c, _ = self.signup("owner@rename-admin.com")
        token = self.sel(c, "Admin list")
        sid = db.selection(token=token)["id"]
        a = self.admin()
        s, page, _ = a.get("/selections")
        self.assertEqual(s, 200)
        self.assertIn("data-hv-rename='%d'" % sid, page)
        s, js, _ = a.get("/shell.js")
        self.assertIn("hv-arn-btn", js)
        s, b, _ = a.req("POST", "/selections/rename", form={"id": str(sid), "name": "Renamed by HelloVoice"}, headers=JS)
        self.assertEqual((s, b.get("ok"), b.get("name")), (200, True, "Renamed by HelloVoice"), b)
        self.assertEqual(c.get("/api/selection?s=" + token)[1]["name"], "Renamed by HelloVoice")
        self.assertIn(("Renamed selection Admin list to Renamed by HelloVoice", "boss@hellovoice.co.uk"), self.history_labels(sid))
        s, b, _ = a.req("POST", "/selections/rename", form={"id": str(sid), "name": " "}, headers=JS)
        self.assertEqual((s, b.get("reason")), (400, "empty"))
        s, b, _ = a.req("POST", "/selections/rename", form={"id": "999999", "name": "x"}, headers=JS)
        self.assertEqual((s, b.get("reason")), (404, "missing"))
        # without JavaScript: a plain form and a redirect back
        s, _, r = a.req("POST", "/selections/rename", form={"id": str(sid), "name": "Plain form", "back": "/selections"})
        self.assertEqual(s, 303)
        self.assertIn("/selections?ok=", r.headers.get("Location"))
        self.assertEqual(db.selection(sid)["name"], "Plain form")
        # undo from History puts the old name back
        with db.connect() as conn:
            hid = conn.execute("SELECT id FROM history WHERE entity='selection' AND key=? ORDER BY id DESC LIMIT 1", (str(sid),)).fetchone()["id"]
        history.undo(hid)
        self.assertEqual(db.selection(sid)["name"], "Renamed by HelloVoice")
        # the admin on the client's page (portal API) may rename too
        s, g, _ = a.get("/api/selection?s=" + token)
        self.assertTrue(g["can_rename"])
        s, b, _ = a.post("/api/selection/rename", {"token": token, "name": "From the page"})
        self.assertEqual((s, b.get("name")), (200, "From the page"), b)
        # the Clients hub panel draws the control too
        u = portal.user_by_email("owner@rename-admin.com")
        s, page, _ = a.get("/clients?open=u%d" % u["id"])
        self.assertEqual(s, 200)
        self.assertIn("data-hv-rename='%d'" % sid, page)

    def test_07_viewer_role_gets_no_control_and_cannot_post(self):
        c, _ = self.signup("owner@rename-viewer.com")
        token = self.sel(c, "Viewer list")
        sid = db.selection(token=token)["id"]
        v, s, _ = self.member("viewer@hellovoice.co.uk", "viewer")
        self.assertEqual(s, 303)
        s, page, _ = v.get("/selections")
        self.assertEqual(s, 200)
        self.assertNotIn("data-hv-rename='%d'" % sid, page)
        s, _, _ = v.req("POST", "/selections/rename", form={"id": str(sid), "name": "Nope"}, headers=JS)
        self.assertEqual(s, 403)
        self.assertEqual(db.selection(sid)["name"], "Viewer list")

    def test_08_kam_own_client_only(self):
        mine, _ = self.signup("lead@kamclient-rn.com")
        theirs, _ = self.signup("lead@otherclient-rn.com")
        t_mine, t_other = self.sel(mine, "KAM client list"), self.sel(theirs, "Other KAM list")
        s_mine, s_other = db.selection(token=t_mine)["id"], db.selection(token=t_other)["id"]
        k, s, _ = self.member(KAM, "kam")
        self.assertEqual(s, 303)
        s, b, _ = k.req("POST", "/selections/rename", form={"id": str(s_mine), "name": "Renamed by her KAM"}, headers=JS)
        self.assertEqual((s, b.get("ok")), (200, True), b)
        s, _, _ = k.req("POST", "/selections/rename", form={"id": str(s_other), "name": "Not hers"}, headers=JS)
        self.assertEqual(s, 403)
        self.assertEqual(db.selection(s_other)["name"], "Other KAM list")
        # on the client's page (portal API, signed in to the admin)
        self.assertTrue(k.get("/api/selection?s=" + t_mine)[1]["can_rename"])
        s, b, _ = k.post("/api/selection/rename", {"token": t_mine, "name": "KAM from the page"})
        self.assertEqual((s, b.get("ok")), (200, True), b)
        s, b, _ = k.post("/api/selection/rename", {"token": t_other, "name": "Not hers"})
        self.assertIn(s, (401, 403))
        self.assertEqual(db.selection(s_other)["name"], "Other KAM list")

    # ------------------------------------------------------------ Helvi --
    def test_09_helvi_tool_same_rule(self):
        c, _ = self.signup("owner@rename-helvi.com")
        token = self.sel(c, "Helvi list")
        owner = portal.user_by_email("owner@rename-helvi.com")
        ctx = {"code_id": owner["code_id"], "selection": {"token": token}}
        a = {"name": "  Helvi   named it "}
        self.assertIn("Helvi named it", assistant.d_sel_rename(a, ctx))
        out = assistant.x_sel_rename(a, ctx)
        self.assertTrue(out["ok"])
        self.assertEqual(db.selection(token=token)["name"], "Helvi named it")
        with self.assertRaises(ValueError):
            assistant.d_sel_rename({"name": "z" * 81}, ctx)
        col, _ = self.signup("peer@rename-helvi.com")
        peer = portal.user_by_email("peer@rename-helvi.com")
        with self.assertRaises(ValueError):
            assistant.x_sel_rename({"name": "Hijacked"}, {"code_id": peer["code_id"], "selection": {"token": token}})
        self.assertEqual(db.selection(token=token)["name"], "Helvi named it")


if __name__ == "__main__":
    unittest.main(verbosity=2)
