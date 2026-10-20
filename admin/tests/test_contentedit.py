"""Edit mode on the campaign dashboard (item 209 slice c, 2026-10-21): who may edit, add a post (platform read from
the link), paste many links, type numbers, hide and delete, who is still to post, insights, History.

    python3 admin/tests/test_contentedit.py
"""
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import contentedit, db, gemini, guard, kam_scope, mailer, portal, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

KAM, OTHER, BOSS = "mariam.k@hvkam.com", "omar.k@hvkam.com", "boss@hellovoice.co.uk"


class Edit(unittest.TestCase):
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
        if not Edit.ready:
            W = Edit
            self.signup("lead@polyco.com"); self.signup("buyer@rivalco.com")
            W.lead = portal.user_by_email("lead@polyco.com"); W.buyer = portal.user_by_email("buyer@rivalco.com")
            sid = db.save_selection(None, "Polyco glow", ["HV-MI-001", "HV-MD-004"], {}, None, None, code_id=W.lead["code_id"])
            W.k = db.create_campaign("Polyco wave", code_id=W.lead["code_id"], selection_id=sid)
            db.add_campaign_creators(W.k, ["HV-MI-001", "HV-MD-004"])
            db.save_campaign(W.k, status="live", starts_at=1, ends_at=2)
            W.tok = db.campaign(W.k)["token"]
            rk = db.create_campaign("Rival wave", code_id=W.buyer["code_id"])
            W.rtok = db.campaign(rk)["token"]
            self.member(BOSS, "owner"); self.member(KAM, "kam"); self.member(OTHER, "kam")
            W.boss = self.signup(BOSS)[0]; W.kam = self.signup(KAM)[0]; W.other = self.signup(OTHER)[0]; W.plain = self.signup("plain@plainco.com")[0]
            Edit.ready = True

    def test_01_platform_from_the_link(self):
        for u, p in (("https://www.instagram.com/reel/C9x/", "Instagram"), ("https://vm.tiktok.com/ZM1/", "TikTok"), ("https://youtu.be/abc", "YouTube"),
                     ("https://x.com/a/status/1", "X"), ("https://example.com/a", None)):
            self.assertEqual(contentedit.platform_of(u), p, u)

    def test_02_who_may_edit(self):
        q = "/api/edit/campaign?t=" + self.tok
        self.assertEqual(self.plain.get(q)[0], 403)                      # a client
        self.assertEqual(self.other.get(q)[0], 404)                      # a KAM, not her client
        self.assertEqual(self.kam.get("/api/edit/campaign?t=" + self.rtok)[0], 404)
        s, b, _ = self.kam.get(q)
        self.assertEqual(s, 200, b)
        self.assertEqual(self.boss.get(q)[0], 200)
        self.assertEqual({c["code"] for c in b["creators"]}, {"HV-MI-001", "HV-MD-004"})
        self.assertEqual(self.plain.post("/api/edit/post", {"t": self.tok, "code": "HV-MI-001", "url": "https://instagram.com/p/1"})[0], 403)

    def test_03_add_numbers_hide_delete(self):
        t = self.tok
        s, b, _ = self.kam.post("/api/edit/post", {"t": t, "code": "hv-mi-001", "url": "https://www.instagram.com/reel/AAA111/"})
        self.assertEqual((s, b["platform"], b["created"]), (200, "Instagram", True), b)
        self.assertEqual(self.kam.post("/api/edit/post", {"t": t, "code": "HV-MI-001", "url": "http://nope"})[0], 400)
        self.assertEqual(self.kam.post("/api/edit/post", {"t": t, "code": "HV-ZZ-999", "url": "https://instagram.com/p/2"})[0], 400)
        s, b, _ = self.kam.post("/api/edit/post", {"t": t, "code": "HV-MI-001", "url": "https://www.tiktok.com/@a/video/74100", "views": "12,300", "likes": 800})
        self.assertEqual((s, b["platform"]), (200, "TikTok"))
        v = self.kam.get("/api/edit/campaign?t=" + t)[1]
        posts = [p for c in v["creators"] if c["code"] == "HV-MI-001" for p in c["posts"]]
        tk = [p for p in posts if p["platform"] == "TikTok"][0]
        self.assertEqual((tk["views"], tk["likes"]), (12300, 800))
        ig = [p for p in posts if p["platform"] == "Instagram"][0]
        self.assertEqual(self.kam.post("/api/edit/numbers", {"t": t, "post": ig["id"], "views": 5000, "likes": 300, "comments": 12, "shares": 4, "saves": 9})[0], 200)
        self.assertEqual(self.kam.post("/api/edit/numbers", {"t": t, "post": ig["id"]})[0], 400)           # nothing typed
        self.assertEqual(self.kam.post("/api/edit/numbers", {"t": t, "post": 99999, "views": 1})[0], 404)
        self.assertEqual(self.kam.post("/api/edit/update", {"t": t, "post": ig["id"], "do": "hide"})[0], 200)
        self.assertTrue([p for c in self.kam.get("/api/edit/campaign?t=" + t)[1]["creators"] for p in c["posts"] if p["id"] == ig["id"]][0]["hidden"])
        self.assertEqual(self.kam.post("/api/edit/update", {"t": t, "post": ig["id"], "do": "delete"})[0], 200)
        self.assertEqual(self.kam.post("/api/edit/update", {"t": t, "post": ig["id"], "do": "explode"})[0], 404)
        with db.connect() as conn:
            h = conn.execute("SELECT who, label FROM history WHERE entity = 'campaign' AND key = ? ORDER BY id", (str(self.k),)).fetchall()
        self.assertTrue(h and all(r["who"] == KAM for r in h), [tuple(r) for r in h])
        # a post of one campaign cannot be edited through another
        rk = db.campaign(token=self.rtok)
        self.assertEqual(self.boss.post("/api/edit/update", {"t": self.rtok, "post": tk["id"], "do": "hide"})[0], 404)

    def test_04_bulk_links_and_pending(self):
        t = self.tok
        s, b, _ = self.kam.post("/api/edit/bulk", {"t": t, "code": "HV-MD-004", "text": "https://instagram.com/reel/B1/\nnot a link\nhttps://www.tiktok.com/@x/video/1,\nhttps://instagram.com/reel/B1/"})
        self.assertEqual(s, 200, b)
        self.assertIn("2 posts added", b["message"])
        self.assertEqual(self.kam.post("/api/edit/bulk", {"t": t, "code": "HV-MD-004", "text": "nothing here"})[0], 400)
        s, b, _ = self.kam.post("/api/edit/pending", {"t": t, "code": "HV-MD-004", "status": "Shooting", "date": "2026-11-03"})
        self.assertEqual(s, 200, b)
        c = [c for c in self.kam.get("/api/edit/campaign?t=" + t)[1]["creators"] if c["code"] == "HV-MD-004"][0]
        self.assertEqual((c["pending_status"], c["pending_date"]), ("Shooting", "2026-11-03"))
        self.assertEqual(len(c["posts"]), 2)
        self.assertEqual(self.kam.post("/api/edit/pending", {"t": t, "code": "HV-MI-999", "status": "Shooting"})[0], 400)
        self.kam.post("/api/edit/pending", {"t": t, "code": "HV-MD-004", "status": "", "date": ""})
        self.assertEqual([c for c in self.kam.get("/api/edit/campaign?t=" + t)[1]["creators"] if c["code"] == "HV-MD-004"][0]["pending_status"], "")

    def test_05_insights(self):
        t = self.tok
        post = [p for c in self.boss.get("/api/edit/campaign?t=" + t)[1]["creators"] for p in c["posts"] if p["platform"] == "TikTok"][0]
        iid = db.add_insight(self.k, "HV-MI-001", ["a.png"], content_id=post["id"])
        db.set_insight_extracted(iid, {"reach": 48200, "views": 61000})
        v = self.boss.get("/api/edit/campaign?t=" + t)[1]
        row = [i for i in v["insights"] if i["id"] == iid][0]
        self.assertEqual((row["status"], row["values"]["reach"]), ("extracted", 48200))
        self.assertEqual(self.kam.post("/api/edit/insight", {"t": t, "id": iid, "do": "approve", "values": {}})[0], 400)
        s, b, _ = self.kam.post("/api/edit/insight", {"t": t, "id": iid, "do": "approve", "post": post["id"], "values": {"reach": "48,200", "views": 61000}})
        self.assertEqual(s, 200, b)
        self.assertEqual(db.insight(iid)["status"], "approved")
        i2 = db.add_insight(self.k, "HV-MI-001", ["b.png"], content_id=post["id"])
        self.assertEqual(self.kam.post("/api/edit/insight", {"t": t, "id": i2, "do": "reject"})[0], 200)
        self.assertEqual(db.insight(i2)["status"], "rejected")
        self.assertNotIn(i2, [i["id"] for i in self.boss.get("/api/edit/campaign?t=" + t)[1]["insights"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
