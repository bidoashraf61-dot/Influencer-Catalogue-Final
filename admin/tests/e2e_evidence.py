"""Competitor evidence packs (admin/evidence.py): import, roster matching, adding creators to the
selection, the client's view (only once shared) and KAM scope. All names below are invented.

    python3 admin/tests/e2e_evidence.py
"""
import json
import shutil
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import db, evidence, gemini, guard, mailer, portal, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

KAM, OTHER = "mariam.k@hvkam.com", "omar.k@hvkam.com"


def post(url, comp, brand, handle, views_, likes, rel="match", paid=False, er=None):
    return {"url": url, "platform": "instagram", "handle": handle, "name": handle.title(), "followers": 40000,
            "date": "2026-03-01", "collab_type": "co_author", "product_tags": "x", "relevance": rel,
            "views": views_, "likes": likes, "comments": 10,
            "er_views": er if er is not None else (None if likes is None else (likes + 10) / views_),
            "likely_paid_boost": paid, "likes_hidden": likes is None, "performance_read": "internal note"}


PACK = {"generated": "2026-10-14", "source": "study.xlsx", "platforms": ["instagram"], "objective": "awareness",
        "brands": [{"brand": "Glow Serum", "product": "Vitamin C serum", "competitors": [
            {"competitor": "RivalSkin", "fit": "direct", "posts_detail": [
                post("https://www.instagram.com/reel/A1/", "RivalSkin", "Glow Serum", "noha", 90000, 2000),
                post("https://www.instagram.com/reel/A2/", "RivalSkin", "Glow Serum", "noha", 50000, 1500),
                post("https://www.instagram.com/reel/A3/", "RivalSkin", "Glow Serum", "sara", 30000, None),
                post("https://www.instagram.com/reel/A4/", "RivalSkin", "Glow Serum", "bought", 2000000, 30, paid=True),
                post("https://www.instagram.com/reel/A5/", "RivalSkin", "Glow Serum", "lina", 70000, 900, rel="other")]}]}]}
TIKTOK = {"platforms": ["tiktok"], "source": "tiktok study",
          "brands": [{"brand": "Glow Serum", "competitors": [{"competitor": "RivalSkin", "fit": "direct", "posts_detail": [
              dict(post("https://www.tiktok.com/@khalid/video/9", "RivalSkin", "Glow Serum", "khalid", 400000, 20000), platform="tiktok")]}]}]}


def upload(c, path, fields, payload):
    """multipart/form-data POST with one JSON file (the test Client only speaks JSON and forms)."""
    b = "----hvtest"
    parts = []
    for k, v in fields.items():
        parts.append('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (b, k, v))
    head = "".join(parts) + '--%s\r\nContent-Disposition: form-data; name="file"; filename="pack.json"\r\nContent-Type: application/json\r\n\r\n' % b
    body = head.encode() + json.dumps(payload).encode() + ("\r\n--%s--\r\n" % b).encode()
    req = urllib.request.Request(c.base + path, data=body, method="POST",
                                 headers={"Origin": c.base, "Content-Type": "multipart/form-data; boundary=" + b})
    try:
        r = c.op.open(req)
    except urllib.error.HTTPError as exc:
        r = exc
    return (r.status if hasattr(r, "status") else r.code), r


class Evidence(unittest.TestCase):
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
        db.set_setting("domain_kam", {"polyco.com": KAM, "rivalco.com": OTHER})
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.ready = False

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()
        mailer.OUTBOX.clear()
        if not Evidence.ready:
            W = Evidence
            W.client, _ = self.signup("lead@polyco.com")
            W.stranger, _ = self.signup("buyer@rivalco.com")
            W.mine = portal.user_by_email("lead@polyco.com")
            W.theirs = portal.user_by_email("buyer@rivalco.com")
            W.sel = db.save_selection(None, "Polyco glow", ["HV-MI-005"], {}, None, None, code_id=W.mine["code_id"])
            W.sel_other = db.save_selection(None, "Rival list", ["HV-MD-004"], {}, None, None, code_id=W.theirs["code_id"])
            W.token = db.selection(W.sel)["token"]
            self.member(KAM, "kam")
            self.member(OTHER, "kam")
            Evidence.ready = True

    def pack_id(self):
        with db.connect() as conn:
            return conn.execute("SELECT MAX(id) FROM evidence_packs WHERE deleted_at IS NULL").fetchone()[0]

    def test_1_import_matches_roster_and_ranks_organic(self):
        a = self.admin()
        s, r = upload(a, "/evidence/import", {"title": "Polyco competitors", "code_id": self.mine["code_id"],
                                              "selection_id": self.sel}, PACK)
        self.assertEqual(s, 303)
        self.assertIn("matched", r.headers["Location"])
        pid = self.pack_id()
        rows = evidence.posts(pid)
        self.assertEqual(len(rows), 5)
        self.assertEqual({r["handle"]: r["code"] for r in rows}["noha"], "HV-MI-001")      # matched by handle
        comp = evidence.summary(evidence.pack(pid))[0]["competitors"][0]
        handles = [t["handle"] for t in comp["top"]]
        self.assertEqual(handles[0], "noha")                      # median 70K beats sara's 30K
        self.assertNotIn("bought", handles)                       # paid-boosted only: not evidence
        self.assertNotIn("lina", handles)                         # other product
        self.assertEqual(comp["paid_boost"], 1)
        s, body, _ = a.get("/evidence/view?id=%d" % pid)
        self.assertEqual(s, 200)
        self.assertIn("RivalSkin", body)
        self.assertIn("internal note", body)                      # admins see the analyst's read
        self.assertEqual(a.get("/evidence")[0], 200)

    def test_2_add_creators_to_the_selection(self):
        a = self.admin()
        pid = self.pack_id()
        s, _, _ = a.req("POST", "/evidence/add", form={"id": str(pid), "codes": "HV-MI-001"})
        self.assertEqual(s, 303)
        self.assertIn("HV-MI-001", json.loads(db.selection(self.sel)["codes"]))

    def test_3_client_sees_it_only_once_shared(self):
        pid = self.pack_id()
        s, b, _ = self.client.get("/api/evidence?s=" + self.token)
        self.assertEqual((s, b["evidence"]), (200, None))         # not shared yet
        a = self.admin()
        a.req("POST", "/evidence/save", form={"id": str(pid), "title": "Polyco competitors",
                                              "selection_id": str(self.sel), "client_visible": "1"})
        s, b, _ = self.client.get("/api/evidence?s=" + self.token)
        self.assertEqual(s, 200)
        ev = b["evidence"]
        comp = ev["brands"][0]["competitors"][0]
        self.assertEqual(comp["competitor"], "RivalSkin")
        self.assertTrue(comp["top"][0]["in_selection"])           # added in test 2
        raw = json.dumps(ev)
        self.assertNotIn("internal note", raw)                    # no analyst notes
        self.assertNotIn("HV-MI-001", raw)                        # no roster codes
        self.assertNotIn("/reel/A5/", raw)                        # other-product posts left out
        s, b, _ = self.stranger.get("/api/evidence?s=" + self.token)
        self.assertEqual(s, 401)                                  # another company's account

    def test_4_tiktok_adds_to_the_same_pack(self):
        a = self.admin()
        pid = self.pack_id()
        s, _ = upload(a, "/evidence/import", {"pack_id": pid}, TIKTOK)
        self.assertEqual(s, 303)
        pk = evidence.pack(pid)
        self.assertEqual(json.loads(pk["platforms"]), ["instagram", "tiktok"])
        comp = evidence.summary(pk)[0]["competitors"][0]
        self.assertEqual(comp["top"][0]["handle"], "khalid")
        self.assertEqual(comp["top"][0]["code"], "HV-MD-003")

    def test_5_kam_scope(self):
        pid = self.pack_id()
        mine, _, _ = self.member(KAM, "kam")
        other, _, _ = self.member(OTHER, "kam")
        self.assertEqual(mine.get("/evidence/view?id=%d" % pid)[0], 200)
        self.assertEqual(other.get("/evidence/view?id=%d" % pid)[0], 403)
        self.assertNotIn("Polyco competitors", other.get("/evidence")[1])
        self.assertEqual(other.req("POST", "/evidence/add", form={"id": str(pid), "codes": "HV-MI-002"})[0], 403)
        s, _ = upload(other, "/evidence/import", {"title": "x", "code_id": self.mine["code_id"]}, PACK)
        self.assertEqual(s, 403)                                  # not her client
        # her own client, but a selection of someone else's
        s, r = upload(other, "/evidence/import", {"title": "x", "code_id": self.theirs["code_id"],
                                                  "selection_id": self.sel}, PACK)
        self.assertEqual(s, 403)

    def test_6_bad_file_is_refused_readably(self):
        a = self.admin()
        s, r = upload(a, "/evidence/import", {"title": "x", "code_id": self.mine["code_id"]}, {"nope": 1})
        self.assertEqual(s, 303)
        self.assertIn("e=", r.headers["Location"])

    def test_7_delete(self):
        a = self.admin()
        pid = self.pack_id()
        a.req("POST", "/evidence/delete", form={"id": str(pid)})
        self.assertIsNone(evidence.pack(pid))
        s, b, _ = self.client.get("/api/evidence?s=" + self.token)
        self.assertEqual(b["evidence"], None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
