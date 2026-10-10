"""End-to-end tests for HELVY Connect fix batch 3, the profile's delete actions (branch f3-account):

- a client deletes their own selection (soft: archived and marked, never erased); a colleague
  cannot (403), a selection HelloVoice built for them cannot (403), deleting twice is harmless;
- a deleted selection leaves every client list and its link stops opening for clients (404
  "unknown"), while the admin still opens it and sees "Deleted by client";
- a client deletes their own brief; the selection it scored asks for an objective again
  (needs_objective, no scores); another client's brief cannot be deleted; twice is harmless.

Same harness as e2e_portal.py (a throwaway copy of admin/*.py, an empty database, captured
mail, a scripted Gemini), so it never touches catalogue.db or the network.

    python3 admin/tests/e2e_portal_fixes3_account.py
"""
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402  (copies admin/*.py to a temp dir and puts it on the path)

import db, gemini, guard, mailer, portal, selstatus, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

DOC = {"followers": 42000, "er": 4.6, "avg_views": 9100, "fake_followers_pct": 8.0,
       "audience": {"countries": [{"code": "SA", "pct": 78.0}], "gender": {"female": 82.0, "male": 18.0},
                    "ages": [{"name": "25-34", "pct": 45.0}]}}
ANSWERS = {"goal": "engagement", "platforms": ["Instagram"], "market": "SA", "category": ["skincare"],
           "gender": "Women", "age": "25-34"}


class Fixes3Account(unittest.TestCase):
    signup = base.Portal.signup
    admin = base.Portal.admin

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        mailer.CAPTURE = True
        gemini.STUB = base.stub
        views.set_base("")
        selstatus.EMAIL_DELAY = 0
        for code in ("HV-MI-001", "HV-MI-002"):
            db.save_analysis(code, DOC, platform="Instagram")
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

    def account(self, c):
        s, b, _ = c.get("/api/account")
        self.assertEqual(s, 200, b)
        return b

    def listed(self, c):
        """Every client list a selection can show up in, as {token}."""
        out = {s["token"]: s for s in self.account(c)["selections"]}
        for path, key in (("/api/voice/selections", "selections"), ("/api/team", "selections"), ("/api/roi/selections", "items")):
            for s in c.get(path)[1].get(key) or []:
                out.setdefault(s["token"], s)
        return out

    # ------------------------------------------------------- selections --
    def test_01_owner_deletes_own_selection_and_it_disappears(self):
        c, _ = self.signup("owner@del-test.com")
        token = self.sel(c, "Mine to delete", ["HV-MI-001", "HV-MI-002"])
        keep = self.sel(c, "Mine to keep", ["HV-MI-001"])
        row = self.listed(c)[token]
        self.assertTrue(row["can_delete"])
        self.assertEqual(db.selection(token=token)["origin"], "client")

        s, b, _ = c.post("/api/selection/delete", {"token": token})
        self.assertEqual((s, b.get("ok")), (200, True), b)
        # gone from every client list, the other one stays
        lists = self.listed(c)
        self.assertNotIn(token, lists)
        self.assertIn(keep, lists)
        # its link no longer opens for the client
        s, b, _ = c.get("/api/selection?s=" + token)
        self.assertEqual((s, b.get("reason")), (404, "unknown"))
        # deleting twice is harmless (same date), deleting an unknown token is 404
        first = db.selection(token=token, deleted=True)["deleted_at"]
        s, b, _ = c.post("/api/selection/delete", {"token": token})
        self.assertEqual((s, b.get("ok")), (200, True), b)
        self.assertEqual(db.selection(token=token, deleted=True)["deleted_at"], first)
        s, b, _ = c.post("/api/selection/delete", {"token": "nope"})
        self.assertEqual(s, 404)
        # re-saving the same name and creators from the catalogue makes a new one, never revives it
        again = self.sel(c, "Mine to delete", ["HV-MI-001", "HV-MI-002"])
        self.assertNotEqual(again, token)

        # the admin still has it: the link opens and the lists mark it
        row = db.selection(token=token, deleted=True)
        self.assertIsNotNone(row)
        self.assertTrue(row["archived_at"])
        self.assertEqual(row["deleted_by"], portal.user_by_email("owner@del-test.com")["code_id"])
        a = self.admin()
        s, b, _ = a.get("/api/selection?s=" + token)
        self.assertEqual(s, 200, b)
        s, page, _ = a.get("/selections?archived=1")
        self.assertEqual(s, 200)
        self.assertIn("Mine to delete", page)
        self.assertIn("Deleted by client", page)
        s, page, _ = a.get("/selections/edit?id=%d" % row["id"])
        self.assertEqual(s, 200)
        self.assertIn("Deleted by client", page)
        # restoring it from the archive gives it back to the client
        db.set_archived("selections", row["id"], False)
        self.assertIn(token, self.listed(c))
        self.assertEqual(c.get("/api/selection?s=" + token)[0], 200)

    def test_02_colleague_cannot_delete(self):
        c, _ = self.signup("maha@team-del.com")
        token = self.sel(c, "Team shortlist", ["HV-MI-001"])
        col, _ = self.signup("sara@team-del.com")
        row = self.listed(col).get(token)
        self.assertIsNotNone(row)                                  # shared with the colleague
        self.assertFalse(row["can_delete"])
        s, b, _ = col.post("/api/selection/delete", {"token": token})
        self.assertEqual((s, b.get("reason")), (403, "not_yours"))
        self.assertIsNone(db.selection(token=token)["deleted_at"])
        # an outsider does not even learn it exists
        out, _ = self.signup("x@elsewhere-del.com")
        s, b, _ = out.post("/api/selection/delete", {"token": token})
        self.assertEqual(s, 404)

    def test_02b_colleague_can_look_but_never_edit(self):
        """Same company is not shared editing: only the selection's owner may tag, re-save,
        set the objective or save an ROI estimate on it. A colleague's re-save is their own copy."""
        c, _ = self.signup("owner@only-own.com")
        token = self.sel(c, "Owner list", ["HV-MI-001", "HV-MI-002"])
        col, _ = self.signup("peer@only-own.com")
        self.assertEqual(col.get("/api/selection?s=" + token)[0], 200)          # looks: fine
        s, b, _ = col.post("/api/selection/tags", {"token": token, "code": "HV-MI-001", "tags": ["Mine"]})
        self.assertEqual((s, b.get("reason")), (403, "not_owner"))
        s, b, _ = c.post("/api/selection/tags", {"token": token, "code": "HV-MI-001", "tags": ["Keep"]})
        self.assertEqual((s, b.get("ok")), (200, True), b)                       # the owner: fine
        s, b, _ = col.post("/api/brief/attach", {"token": token, "answers": {"objective": ["Awareness"]}})
        self.assertEqual((s, b.get("reason")), (403, "not_owner"))
        # a colleague re-saving the same token must not change the owner's creators
        s, b, _ = col.post("/api/selection", {"token": token, "name": "Owner list", "codes": ["HV-MI-001"]})
        self.assertEqual(s, 200, b)
        self.assertNotEqual(b["token"], token)                                   # their own copy
        self.assertEqual(json.loads(db.selection(token=token)["codes"]), ["HV-MI-001", "HV-MI-002"])

    def test_03_helloVoice_selection_cannot_be_deleted_by_the_client(self):
        c, _ = self.signup("noor@hv-del.com")
        cid = portal.user_by_email("noor@hv-del.com")["code_id"]
        sid = db.save_selection(None, "Built by HelloVoice", ["HV-MI-001"], {}, None, None, code_id=cid)
        token = db.selection(sid)["token"]
        row = self.listed(c)[token]
        self.assertTrue(row["mine"])
        self.assertFalse(row["can_delete"])
        s, b, _ = c.post("/api/selection/delete", {"token": token})
        self.assertEqual((s, b.get("reason")), (403, "not_yours"))
        self.assertEqual(c.get("/api/selection?s=" + token)[0], 200)

    def test_04_legacy_rows_are_classed_conservatively(self):
        # the migration's rule, applied by hand to a fresh table copy
        with db.connect() as conn:
            conn.execute("CREATE TEMP TABLE t AS SELECT * FROM selections WHERE 0")
            for i, (code_id, request_id, prices) in enumerate(((5, None, "{}"), (None, None, "{}"), (5, 3, "{}"), (5, None, '{"A": [1, 2]}'))):
                conn.execute("INSERT INTO t (id, token, name, codes, code_id, request_id, prices, created_at, updated_at) "
                             "VALUES (?, ?, 'x', '[]', ?, ?, ?, 0, 0)", (9000 + i, "tk%d" % i, code_id, request_id, prices))
            conn.execute("UPDATE t SET origin = CASE WHEN code_id IS NULL OR request_id IS NOT NULL "
                         "OR COALESCE(prices, '{}') NOT IN ('{}', '', 'null') THEN 'admin' ELSE 'client' END")
            got = [r[0] for r in conn.execute("SELECT origin FROM t ORDER BY id")]
            conn.execute("DROP TABLE t")
        self.assertEqual(got, ["client", "admin", "admin", "admin"])
        # and init() is idempotent: running it again changes nothing
        db.init()
        portal.init()

    # ----------------------------------------------------------- briefs --
    def test_05_brief_delete_clears_the_selection_objective(self):
        c, _ = self.signup("dana@brief-del.com")
        token = self.sel(c, "Scored by a brief", ["HV-MI-001", "HV-MI-002"])
        s, att, _ = c.post("/api/brief/attach", {"token": token, "answers": ANSWERS})
        self.assertTrue(att.get("ok"), att)
        b = c.get("/api/selection?s=" + token)[1]
        self.assertNotIn("needs_objective", b)
        self.assertTrue(b["scores"])
        briefs = self.account(c)["briefs"]
        self.assertEqual(briefs[0]["id"], att["brief_id"])
        self.assertTrue(briefs[0]["can_delete"])

        s, r, _ = c.post("/api/brief/delete", {"id": att["brief_id"]})
        self.assertEqual((s, r.get("ok")), (200, True), r)
        b = c.get("/api/selection?s=" + token)[1]
        self.assertTrue(b.get("needs_objective"))
        self.assertEqual(b["scores"], {})
        self.assertIsNone(b["brief"]["objective"])
        # gone from the client's briefs, the brief-for-selection lookup and the fit badges
        self.assertNotIn(att["brief_id"], [x["id"] for x in self.account(c)["briefs"]])
        self.assertNotIn(att["brief_id"], [x["id"] for x in c.get("/api/briefs")[1]["briefs"]])
        self.assertIsNone(c.get("/api/brief/for?s=" + token)[1]["brief"])
        self.assertEqual(c.get("/api/brief/scores?b=%d" % att["brief_id"])[0], 404)
        # twice is harmless
        s, r, _ = c.post("/api/brief/delete", {"id": att["brief_id"]})
        self.assertEqual((s, r.get("ok")), (200, True), r)
        # the admin still sees it, marked
        row = portal.brief(att["brief_id"])
        self.assertTrue(row["deleted_at"])
        a = self.admin()
        s, page, _ = a.get("/portal?tab=briefs")
        self.assertEqual(s, 200)
        self.assertIn("Deleted by client", page)
        # a new objective scores the selection again
        s, att2, _ = c.post("/api/brief/attach", {"token": token, "answers": ANSWERS})
        self.assertTrue(att2.get("ok"))
        self.assertNotIn("needs_objective", c.get("/api/selection?s=" + token)[1])

    def test_06_brief_from_an_ai_shortlist_and_an_admin_objective(self):
        c, _ = self.signup("rima@brief-run.com")
        ans = dict(ANSWERS, count="5", budget="400")
        s, run, _ = c.post("/api/brief/run", {"answers": ans, "name": "AI list"})
        self.assertEqual(s, 200, run)
        self.assertEqual(db.selection(token=run["token"])["origin"], "client")
        self.assertNotIn("needs_objective", c.get("/api/selection?s=" + run["token"])[1])
        c.post("/api/brief/delete", {"id": run["brief_id"]})
        self.assertTrue(c.get("/api/selection?s=" + run["token"])[1].get("needs_objective"))
        # an objective the admin set after the brief is not the brief's: deleting leaves it
        token = self.sel(c, "Admin re-aimed", ["HV-MI-001"])
        s, att, _ = c.post("/api/brief/attach", {"token": token, "answers": ANSWERS})
        db.set_selection_objective(db.selection(token=token)["id"], "Awareness")
        c.post("/api/brief/delete", {"id": att["brief_id"]})
        b = c.get("/api/selection?s=" + token)[1]
        self.assertNotIn("needs_objective", b)
        self.assertEqual(b["brief"]["objective"], "Awareness")

    def test_07_cannot_delete_someone_elses_brief(self):
        c, _ = self.signup("lina@brief-own.com")
        token = self.sel(c, "Lina's", ["HV-MI-001"])
        s, att, _ = c.post("/api/brief/attach", {"token": token, "answers": ANSWERS})
        # a colleague sees the selection but the brief is Lina's
        col, _ = self.signup("huda@brief-own.com")
        s, r, _ = col.post("/api/brief/delete", {"id": att["brief_id"]})
        self.assertEqual((s, r.get("reason")), (403, "not_yours"))
        # another company: not found
        out, _ = self.signup("z@other-brief.com")
        s, r, _ = out.post("/api/brief/delete", {"id": att["brief_id"]})
        self.assertEqual(s, 404)
        self.assertIsNone(portal.brief(att["brief_id"])["deleted_at"])
        self.assertNotIn("needs_objective", c.get("/api/selection?s=" + token)[1])
        # signed out: locked
        s, r, _ = base.Client(self.base).post("/api/brief/delete", {"id": att["brief_id"]})
        self.assertEqual(s, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
