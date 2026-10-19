"""HELVi Connect app (item 168): install tracking, subscriptions, bell -> push, quiet hours,
daily cap, phone switch, manual pushes, milestones, team alerts, admin pages and roles.
The push services are faked (webpush.send is captured); the crypto has its own test.

    python3 admin/tests/test_push.py
"""
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import db, gemini, guard, inbox, mailer, metrics, notify, portal, server, views  # noqa: E402
import push, webpush  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

SENT = []


def fake_send(sub, payload, **kw):
    SENT.append((sub["endpoint"], payload, kw))
    return 201, False


def sub(n):
    return {"endpoint": "https://fcm.googleapis.com/fcm/send/dev-%s" % n,
            "keys": {"p256dh": webpush.b64u(webpush.encode_point(webpush.mul(webpush.new_private()))), "auth": "BTBZMqHH6r4Tts7J_aSIgg"}}


class Push(unittest.TestCase):
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
        webpush.KEY_FILE = str(base.TMP / ".vapid-key")
        webpush.send = fake_send
        push.init()
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
        SENT.clear()
        push.save_rules({"quiet": [0, 0], "daily_max": 10})      # quiet hours off unless a test turns them on
        if not Push.ready:
            Push.c, _ = self.signup("sara@jamjoom.com")
            Push.u = portal.user_by_email("sara@jamjoom.com")
            Push.ready = True

    def ua(self, ios=False):
        return {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) Safari/604.1" if ios else
                "Mozilla/5.0 (Linux; Android 14; Pixel 8) Chrome/129.0 Mobile Safari/537.36"}

    def drain(self):
        return push.tick()

    def test_01_key_and_tracking(self):
        s, b, _ = self.c.get("/api/push/key")
        self.assertEqual(s, 200)
        self.assertEqual(len(webpush.unb64u(b["key"])), 65)
        s, b, _ = self.c.post("/api/push/event", {"k": "dev-aaaa-1111", "e": "seen", "p": "ios", "perm": "default"}, headers=self.ua(True))
        self.assertEqual((s, b["ok"]), (200, True))
        self.c.post("/api/push/event", {"k": "dev-aaaa-1111", "e": "guide", "p": "ios"}, headers=self.ua(True))
        self.c.post("/api/push/event", {"k": "dev-aaaa-1111", "e": "launch", "p": "ios", "sa": True}, headers=self.ua(True))
        with db.connect() as conn:
            r = conn.execute("SELECT * FROM app_clients WHERE device_key = 'dev-aaaa-1111'").fetchone()
        self.assertEqual(r["user_id"], self.u["id"])
        self.assertTrue(r["guide_at"] and r["installed_at"])
        self.assertEqual(r["launches"], 1)
        self.assertEqual(self.c.post("/api/push/event", {"k": "x", "e": "seen"})[0], 400)       # junk key

    def test_02_subscribe_and_bell_pushes(self):
        anon = base.Client(self.base)
        self.assertEqual(anon.post("/api/push/subscribe", {"sub": sub("anon")})[0], 401)
        s, b, _ = self.c.post("/api/push/subscribe", {"sub": sub("sara"), "k": "dev-aaaa-1111", "sa": True}, headers=self.ua(True))
        self.assertEqual((s, b["ok"]), (200, True), b)
        inbox.emit([self.u["id"]], "sel_shared", "A selection was shared:", rest=" Ramadan", body="Open it", href="selection/#s=abc")
        inbox.emit([self.u["id"]], "camp_report", "Report updated", href="campaign/#t=x")       # never pushed
        out = self.drain()
        self.assertEqual(out["sent"], 1, out)
        ep, payload, kw = SENT[0]
        self.assertTrue(ep.endswith("dev-sara"))
        self.assertEqual(payload["title"], "A selection was shared: Ramadan")
        self.assertEqual(payload["url"], "/selection/#s=abc")
        self.assertIn("unread", payload)
        # The service worker reports delivery and the tap.
        self.assertEqual(self.c.post("/api/push/ack", {"d": payload["d"], "k": "wrong"})[0], 404)
        self.assertEqual(base.Client(self.base).post("/api/push/ack", {"d": payload["d"], "k": payload["k"]})[0], 200)
        self.assertEqual(base.Client(self.base).post("/api/push/click", {"d": payload["d"], "k": payload["k"]})[0], 200)
        with db.connect() as conn:
            d = conn.execute("SELECT * FROM push_deliveries WHERE id = ?", (payload["d"],)).fetchone()
        self.assertTrue(d["acked_at"] and d["clicked_at"])

    def test_03_quiet_hours_hold(self):
        push.save_rules({"quiet": [0, 23]})                 # 00:00-23:00 Riyadh: almost always quiet
        import time
        h = time.gmtime(db.now() + push.RIYADH).tm_hour
        inbox.emit([self.u["id"]], "analysis_ready", "Analysis ready", href="account/")
        out = self.drain()
        with db.connect() as conn:
            d = conn.execute("SELECT * FROM push_deliveries ORDER BY id DESC LIMIT 1").fetchone()
        if h < 23:
            self.assertEqual(out["sent"], 0)
            self.assertEqual(d["status"], "queued")
            self.assertGreater(d["send_after"], db.now())
            self.assertEqual(time.gmtime(d["send_after"] + push.RIYADH).tm_hour, 23)
            with db.connect() as conn:
                conn.execute("UPDATE push_deliveries SET status = 'skipped' WHERE id = ?", (d["id"],))

    def test_04_daily_cap_and_phone_switch(self):
        push.save_rules({"daily_max": 1})
        with db.connect() as conn:
            conn.execute("DELETE FROM push_deliveries")
        inbox.emit([self.u["id"]], "credits_added", "Credits added", href="account/#credits")
        inbox.emit([self.u["id"]], "colleague", "A colleague joined", href="account/")
        out = self.drain()
        self.assertEqual(out["sent"], 1)
        with db.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM push_deliveries WHERE status = 'skipped' AND reason = 'daily cap'").fetchone()[0], 1)
        push.save_rules({"daily_max": 10})
        self.assertEqual(self.c.post("/api/push/phone", {"on": False})[1]["phone"], False)
        SENT.clear()
        inbox.emit([self.u["id"]], "quote_ready", "Quote ready", href="account/")
        self.assertEqual(self.drain()["sent"], 0)
        self.assertEqual(self.c.post("/api/push/phone", {"on": True})[1]["phone"], True)
        self.assertEqual(self.c.get("/api/push/state")[1]["phone"], True)

    def test_05_manual_push_from_admin(self):
        a = self.admin()
        s, r, _ = a.get("/app-alerts/reach?aud=" + __import__("urllib.parse").parse.quote(json.dumps({"type": "client", "clients": ["jamjoom.com"], "kam": False})))
        self.assertEqual(s, 200)
        self.assertEqual((r["people"], r["push_people"], r["devices"]), (1, 1, 1), r)
        s, _, resp = a.req("POST", "/app-alerts/send", form={
            "title": "Ramadan shortlists are open", "body": "Open the selection.", "dest": "/account/#selections",
            "aud": json.dumps({"type": "client", "clients": ["jamjoom.com"], "kam": False}), "when": "now"})
        self.assertEqual(s, 303)
        self.assertIn("ok=", resp.headers["Location"])
        self.drain()
        mine = [p for _e, p, _k in SENT if p["title"] == "Ramadan shortlists are open"]
        self.assertEqual(len(mine), 1, SENT)                     # once: the bell copy does not push again
        feed = inbox.feed(portal.user_by_id(self.u["id"]), bell=False)
        self.assertEqual(feed[0]["kind"], "announce")
        self.assertEqual(feed[0]["href"], "account/#selections")
        # Scheduled, then cancelled.
        s, _, resp = a.req("POST", "/app-alerts/send", form={
            "title": "Later", "body": "x", "dest": "/", "aud": json.dumps({"type": "all"}), "when": "later",
            "send_at": "2099-01-01T10:00"})
        self.assertIn("scheduled", resp.headers["Location"].lower())
        with db.connect() as conn:
            mid = conn.execute("SELECT id FROM push_messages WHERE title = 'Later'").fetchone()[0]
        self.assertEqual(a.req("POST", "/app-alerts/cancel", form={"id": str(mid)})[0], 303)
        with db.connect() as conn:
            self.assertEqual(conn.execute("SELECT status FROM push_messages WHERE id = ?", (mid,)).fetchone()[0], "cancelled")
        # Nobody matches.
        s, _, resp = a.req("POST", "/app-alerts/send", form={"title": "x", "dest": "/", "aud": json.dumps({"type": "client", "clients": ["nobody.com"]}),
                                                             "when": "now"})
        self.assertIn("e=", resp.headers["Location"])

    def test_06_milestones(self):
        cid = db.create_campaign("Jamjoom Wave 1", code_id=self.u["code_id"])
        db.save_campaign(cid, status="live", starts_at=1, ends_at=2)
        state = {"views": 150000, "posts": 0, "progress": [{"key": "posts", "goal": 20, "actual": 0, "pct": 0}]}
        real = metrics.report
        metrics.report = lambda k, internal=False, raw=False: ({"total": {"views": state["views"], "posts": state["posts"]},
                                                               "progress": state["progress"]} if k["id"] == cid else real(k, internal, raw))
        try:
            self.assertEqual(push.milestones(), 0)               # first sight: recorded, nothing sent (100K already passed)
            state.update(views=1200000, posts=1, progress=[{"key": "posts", "goal": 20, "actual": 11, "pct": 55}])
            self.assertEqual(push.milestones(), 3)               # 1M views (500K folded), posts goal 50%, first post
            self.assertEqual(push.milestones(), 0)               # each once
            self.drain()
            titles = sorted(p["title"] for _e, p, _k in SENT)
            self.assertIn("1M views: Jamjoom Wave 1", titles)
            self.assertIn("Posts goal 50% reached", titles)
            self.assertIn("First post is live: Jamjoom Wave 1", titles)
            kinds = {n["kind"] for n in inbox.feed(portal.user_by_id(self.u["id"]), bell=False, limit=10)}
            self.assertTrue({"camp_views", "camp_goal", "camp_posts"} <= kinds)
        finally:
            metrics.report = real

    def test_07_team_alerts_reach_staff_phones(self):
        boss = self.admin()
        s, b, _ = boss.post("/api/push/subscribe", {"sub": sub("boss"), "k": "dev-boss-0001"})
        self.assertEqual(s, 200, b)
        db.set_setting("notify_emails", ["boss@hellovoice.co.uk"])
        notify.send("brief", ["New brief from Jamjoom", "Ramadan launch"], link="https://x/admin/briefs")
        self.drain()
        got = [p for e, p, _k in SENT if e.endswith("dev-boss")]
        self.assertEqual(len(got), 1, SENT)
        self.assertEqual(got[0]["title"], notify.EVENTS["brief"])
        self.assertEqual(got[0]["body"], "New brief from Jamjoom")

    def test_08_admin_pages_and_roles(self):
        a = self.admin()
        for tab in ("overview", "send", "history", "rules"):
            s, body, _ = a.get("/app-alerts?tab=" + tab)
            self.assertEqual(s, 200, tab)
            self.assertIn("App &amp; alerts", body)
        s, body, _ = a.get("/app-alerts?tab=overview")
        self.assertIn("Ali Hassan", body)                        # the signed-up person shows in People
        self.assertEqual(a.req("POST", "/app-alerts/rules", form={"on": "1", "goals": "1", "goal_steps": "50, 100",
                                                                    "view_steps": "250k, 2m", "posts_gap_h": "6", "daily_max": "2",
                                                                    "quiet_a": "22", "quiet_b": "7"})[0], 303)
        R = push.rules()
        self.assertEqual((R["goal_steps"], R["view_steps"], R["posts_gap_h"], R["daily_max"], R["quiet"], R["views"]),
                         ([50, 100], [250000, 2000000], 6, 2, [22, 7], False))
        k, s, _ = self.member("kam9@hellovoice.co.uk", "kam")
        self.assertEqual(k.get("/app-alerts")[0], 403)
        self.assertEqual(k.req("POST", "/app-alerts/send", form={"title": "x"})[0], 403)


if __name__ == "__main__":
    unittest.main()
