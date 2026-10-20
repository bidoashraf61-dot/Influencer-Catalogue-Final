"""Push composer on the profile (item 209 slice c, 2026-10-21): who may push to whom, reach counts, scope,
the step-up code for big audiences, scheduling, the test to one's own phone, safe links.

    python3 admin/tests/test_pushcomposer.py
"""
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import db, gemini, guard, mailer, portal, pushcomposer, server, views  # noqa: E402
import push, stepup, webpush  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

KAM, OTHER, BOSS = "mariam.k@hvkam.com", "omar.k@hvkam.com", "boss@hellovoice.co.uk"


def sub(n):
    return {"endpoint": "https://fcm.googleapis.com/fcm/send/pc-%s" % n,
            "keys": {"p256dh": webpush.b64u(webpush.encode_point(webpush.mul(webpush.new_private()))), "auth": "BTBZMqHH6r4Tts7J_aSIgg"}}


class Compose(unittest.TestCase):
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
        webpush.KEY_FILE = str(base.TMP / ".vapid-key")
        webpush.send = lambda s, p, **kw: (201, False)
        push.init()
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
        if not Compose.ready:
            W = Compose
            for e in ("a@polyco.com", "b@polyco.com", "c@polyco.com", "buyer@rivalco.com"):
                self.signup(e)
            W.a, W.b, W.c = (portal.user_by_email(e) for e in ("a@polyco.com", "b@polyco.com", "c@polyco.com"))
            W.buyer = portal.user_by_email("buyer@rivalco.com")
            push.subscribe({"user_id": W.a["id"]}, sub(1)); push.subscribe({"user_id": W.b["id"]}, sub(2))
            sid = db.save_selection(None, "Polyco glow", ["HV-MI-001"], {}, None, None, code_id=W.a["code_id"])
            W.k = db.create_campaign("Polyco wave", code_id=W.a["code_id"], selection_id=sid)
            db.save_campaign(W.k, status="live", starts_at=1, ends_at=2)
            W.tok = db.campaign(W.k)["token"]
            self.member(BOSS, "owner"); self.member(KAM, "kam"); self.member(OTHER, "kam")
            W.boss = self.signup(BOSS)[0]; W.kam = self.signup(KAM)[0]; W.other = self.signup(OTHER)[0]; W.plain = self.signup("plain@plainco.com")[0]
            Compose.ready = True

    def test_01_context_and_scope(self):
        self.assertEqual(self.plain.get("/api/compose/context?k=polyco.com")[0], 403)
        s, d, _ = self.boss.get("/api/compose/context?k=polyco.com")
        self.assertEqual(s, 200, d)
        self.assertEqual({p["email"]: p["phone"] for p in d["people"]}["a@polyco.com"], True)
        self.assertEqual({p["email"]: p["phone"] for p in d["people"]}["c@polyco.com"], False)
        self.assertEqual([c["name"] for c in d["campaigns"]], ["Polyco wave"])
        self.assertEqual(self.kam.get("/api/compose/context?k=polyco.com")[0], 200)
        self.assertEqual(self.kam.get("/api/compose/context?k=rivalco.com")[0], 404)            # not her client

    def test_02_reach(self):
        aud = {"type": "company", "key": "polyco.com"}
        s, r, _ = self.boss.post("/api/compose/reach", {"aud": aud})
        self.assertEqual((s, r["people"], r["push_people"], r["needs_code"]), (200, 3, 2, False), r)
        self.assertEqual(r["no_phone_n"], 1)
        s, r, _ = self.boss.post("/api/compose/reach", {"aud": {"type": "campaign", "campaigns": [self.k]}})
        self.assertEqual(s, 200, r)
        self.assertEqual(self.kam.post("/api/compose/reach", {"aud": {"type": "company", "key": "rivalco.com"}})[0], 400)
        self.assertEqual(self.kam.post("/api/compose/reach", {"aud": {"type": "people", "people": [self.buyer["id"]]}})[0], 400)
        self.assertEqual(self.boss.post("/api/compose/reach", {"aud": {"type": "all"}})[0], 400)                # never "every client" from here

    def test_03_send_now_and_scheduled(self):
        aud = {"type": "people", "people": [self.a["id"], self.b["id"]]}
        s, b, _ = self.kam.post("/api/compose/send", {"aud": aud, "title": "Your report is updated", "body": "Two new reels went live.", "url": "/account/"})
        self.assertEqual((s, b["people"]), (200, 2), b)
        with db.connect() as conn:
            m = conn.execute("SELECT * FROM push_messages WHERE id = ?", (b["id"],)).fetchone()
            n = conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND kind = 'announce'", (self.a["id"],)).fetchone()[0] \
                if conn.execute("SELECT name FROM sqlite_master WHERE name = 'notifications'").fetchone() else 1
        self.assertEqual((m["source"], m["created_by"], m["title"]), ("manual", KAM, "Your report is updated"))
        self.assertGreaterEqual(n, 1)
        self.assertEqual(self.kam.post("/api/compose/send", {"aud": aud, "title": ""})[0], 400)
        s, b, _ = self.kam.post("/api/compose/send", {"aud": aud, "title": "Later", "send_at": db.now() + 7200})
        self.assertEqual((s, b["scheduled"]), (200, True), b)
        with db.connect() as conn:
            self.assertEqual(conn.execute("SELECT status FROM push_messages WHERE id = ?", (b["id"],)).fetchone()["status"], "scheduled")
        self.assertEqual(self.kam.post("/api/compose/send", {"aud": aud, "title": "Far", "send_at": db.now() + 90 * 86400})[0], 400)
        self.assertEqual(self.kam.post("/api/compose/send", {"aud": {"type": "people", "people": [self.buyer["id"]]}, "title": "x"})[0], 400)

    def test_04_safe_links_and_test_send(self):
        self.assertEqual(pushcomposer._safe_url("https://evil.example/x", {"t"}), "/account/")
        self.assertEqual(pushcomposer._safe_url("//evil.example", {"t"}), "/account/")
        self.assertEqual(pushcomposer._safe_url("/campaign/dashboard/#t=t", {"t"}), "/campaign/dashboard/#t=t")
        self.assertEqual(pushcomposer._safe_url("/campaign/dashboard/#t=zzz", {"t"}), "/account/")
        aud = {"type": "company", "key": "polyco.com"}
        push.subscribe({"email": BOSS, "admin_id": 1}, sub(9))
        s, b, _ = self.boss.post("/api/compose/send", {"aud": aud, "title": "Test", "body": "Just me", "test": True})
        self.assertEqual(s, 200, b)
        with db.connect() as conn:
            m = conn.execute("SELECT * FROM push_messages WHERE id = ?", (b["id"],)).fetchone()
        self.assertEqual((m["source"], json.loads(m["audience"])["type"]), ("test", "test"))

    def test_05_big_audience_needs_the_code(self):
        for i in range(8):
            self.signup("p%d@polyco.com" % i)
        with db.connect() as conn:
            conn.execute("DELETE FROM stepup_grants") if conn.execute("SELECT name FROM sqlite_master WHERE name = 'stepup_grants'").fetchone() else None
        aud = {"type": "company", "key": "polyco.com"}
        s, r, _ = self.boss.post("/api/compose/reach", {"aud": aud})
        self.assertEqual((r["people"], r["needs_code"]), (11, True), r)
        s, b, _ = self.boss.post("/api/compose/send", {"aud": aud, "title": "Everyone"})
        self.assertEqual((s, b.get("reason")), (403, "stepup"), b)
        with db.connect() as conn:
            conn.execute("UPDATE otp SET created_at = created_at - 100")
        self.boss.post("/api/stepup/send", {}); code = mailer.OUTBOX[-1]["text"].split("code is ")[1][:6]
        self.assertEqual(self.boss.post("/api/stepup/verify", {"code": code})[0], 200)
        s, b, _ = self.boss.post("/api/compose/send", {"aud": aud, "title": "Everyone"})
        self.assertEqual((s, b["people"]), (200, 11), b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
