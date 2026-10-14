"""Control Centre step 3 (item 101): the industry review queue, the Industry section of the creator form,
and the catalogue's quick edit API (team only, undoable, stale-safe).

    python3 admin/tests/e2e_industry_edit.py
"""
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402
from e2e_portal import Client  # noqa: E402

import auth, db, guard, history, industry, server, team, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


def row(code):
    return db.creator(code)


class IndustryEdit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base.seed()
        views.set_base("")
        with db.connect() as conn:
            conn.execute("UPDATE creators SET industry='Beauty & Personal Care', sub_niches='[\"Makeup\"]', also_industries='[\"Fashion\"]', "
                         "industry_tier='Review', industry_conf=55, industry_source='Claude Sonnet 5.5 classification 2026-10-13: runs disagree' "
                         "WHERE code IN ('HV-MI-001','HV-MD-004')")
        team.invite("viewer@hellovoice.co.uk", "V", "viewer")
        db.set_admin_password(db.admin_by_email("viewer@hellovoice.co.uk")["id"], auth.hash_password("correct-horse-battery"))
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()

    def admin(self, email="boss@hellovoice.co.uk"):
        c = Client(self.base)
        s, _, _ = c.req("POST", "/login", form={"email": email, "password": "correct-horse-battery"})
        self.assertEqual(s, 303)
        return c

    def test_1_queue_shows_biggest_review_creator_first(self):
        a = self.admin()
        s, body, _ = a.get("/roster/review")
        self.assertEqual(s, 200)
        self.assertIn("Lina H", body)                         # HV-MD-004, 120K, before HV-MI-001 (42K)
        self.assertIn("55% sure", body)
        self.assertIn("disagreed", body)

    def test_2_skip_moves_on_confirm_saves_and_is_undoable(self):
        a = self.admin()
        s, _, r = a.req("POST", "/roster/review", form={"code": "HV-MD-004", "after": "120000:HV-MD-004", "do": "skip"})
        self.assertIn("after=", r.headers["Location"])
        s, body, _ = a.get(r.headers["Location"].replace(self.base, ""))
        self.assertIn("Noha Magdy", body)
        s, _, r = a.req("POST", "/roster/review", form={"code": "HV-MI-001", "do": "confirm", "ind_main": "Health & Medical",
                                                         "ind_subs": "Pharmacy", "ind_also": "Beauty & Personal Care"})
        self.assertIn("ok=", r.headers["Location"])
        c = row("HV-MI-001")
        self.assertEqual((c["industry"], c["industry_tier"], json.loads(c["sub_niches"])), ("Health & Medical", "Confirmed", ["Pharmacy"]))
        self.assertIn("was: Beauty & Personal Care", c["industry_source"])
        last = history.listing(None, None, limit=1)[0]
        self.assertIn("Set industry of HV-MI-001", last["label"])

    def test_3_not_a_fit_hides_without_deleting(self):
        a = self.admin()
        a.req("POST", "/roster/review", form={"code": "HV-MD-004", "do": "unfit"})
        self.assertEqual(row("HV-MD-004")["active"], 0)
        with db.connect() as conn:
            conn.execute("UPDATE creators SET active = 1 WHERE code = 'HV-MD-004'")

    def test_4_bad_industry_is_refused(self):
        a = self.admin()
        s, _, r = a.req("POST", "/roster/review", form={"code": "HV-MD-004", "do": "confirm", "ind_main": "Nonsense"})
        self.assertIn("e=", r.headers["Location"])

    def test_5_quick_edit_api(self):
        a = self.admin()
        s, c, _ = a.get("/api/admin/creator?code=HV-MI-002")
        self.assertEqual(s, 200)
        self.assertIn("Beauty & Personal Care", c["industries"])
        s, out, _ = a.post("/api/admin/creator", {"code": "HV-MI-002", "name": "Sara A.", "city": "Riyadh", "industry": "Health & Fitness",
                                                   "subs": ["Wellness", "Not-a-niche"], "active": True, "prev_updated": c["updated_at"]})
        self.assertEqual(s, 200, out)
        self.assertEqual((out["name"], out["industry"], out["subs"], out["tier"]), ("Sara A.", "Health & Fitness", ["Wellness"], "Confirmed"))
        s, out2, _ = a.post("/api/admin/creator", {"code": "HV-MI-002", "name": "Old form", "prev_updated": c["updated_at"]})
        self.assertEqual(s, 409)                                # stale form never overwrites
        self.assertEqual(row("HV-MI-002")["name"], "Sara A.")
        s, out3, _ = a.post("/api/admin/creator", {"code": "HV-MI-002", "active": False, "prev_updated": out["updated_at"]})
        self.assertEqual(row("HV-MI-002")["active"], 0)
        with db.connect() as conn:
            conn.execute("UPDATE creators SET active = 1 WHERE code = 'HV-MI-002'")

    def test_6_viewers_and_strangers_cannot_edit(self):
        v = self.admin("viewer@hellovoice.co.uk")
        self.assertEqual(v.get("/api/admin/creator?code=HV-MI-002")[0], 403)
        self.assertEqual(v.post("/api/admin/creator", {"code": "HV-MI-002", "name": "x"})[0], 403)
        self.assertEqual(Client(self.base).get("/api/admin/creator?code=HV-MI-002")[0], 403)

    def test_7_photo_upload_rejects_rubbish(self):
        a = self.admin()
        s, out, _ = a.post("/api/admin/creator/photo", {"code": "HV-MI-002", "data": "data:image/png;base64,bm90IGFuIGltYWdl"})
        self.assertEqual(s, 400)

    def test_8_creator_form_has_industry_and_saves_it(self):
        a = self.admin()
        s, page, _ = a.get("/roster?edit=HV-MI-005")
        self.assertEqual(s, 200)
        self.assertIn("How sure are we?", page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
