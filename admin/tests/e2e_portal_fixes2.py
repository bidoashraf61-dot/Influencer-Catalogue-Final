"""End-to-end tests for the HELVY Connect fix batch of 2026-10-09 (branch portal-fixes-2):

- a selection with no campaign objective is never scored (also after "Add more like these"),
  and is scored once the client answers the brief questions;
- the reject reason, given after the rejection from the "?" pop-up: chips, Other with a note,
  shown back to the owner and to a colleague, refused for viewers and for creators that are
  not rejected;
- the roster answer: built once per roster version, ETag + 304, gzip, a new ETag when a
  creator changes, nothing for a locked browser;
- the full-analysis promise: ready within 1 working day (Friday and Saturday skipped).

Same harness as e2e_portal.py (a throwaway copy of admin/*.py, an empty database, captured
mail, a scripted Gemini), so it never touches catalogue.db or the network.

    python3 admin/tests/e2e_portal_fixes2.py
"""
import calendar
import gzip
import json
import shutil
import sys
import threading
import time
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402  (copies admin/*.py to a temp dir and puts it on the path)
from e2e_portal import Client  # noqa: E402

import db, gating, gemini, guard, mailer, portal, selstatus, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

DOC = {"followers": 42000, "er": 4.6, "avg_views": 9100, "fake_followers_pct": 8.0,
       "audience": {"countries": [{"code": "SA", "pct": 78.0}, {"code": "EG", "pct": 8.0}],
                    "gender": {"female": 82.0, "male": 18.0}, "ages": [{"name": "25-34", "pct": 45.0}]}}
ANSWERS = {"goal": "engagement", "platforms": ["Instagram"], "market": "SA", "category": ["skincare"],
           "gender": "Women", "age": "25-34"}


class Fixes2(unittest.TestCase):
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
        for code in ("HV-MI-001", "HV-MI-002", "HV-MD-004"):
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

    def scores(self, c, token):
        s, b, _ = c.get("/api/selection?s=" + token)
        self.assertEqual(s, 200, b)
        return b

    # ------------------------------------------------- #8 no objective, no scores --
    def test_01_no_objective_means_no_scores_until_the_brief_is_answered(self):
        c, _ = self.signup("nadia@obj-test.com")
        token = self.sel(c, "Hand-built", ["HV-MI-001", "HV-MI-002"])
        b = self.scores(c, token)
        self.assertTrue(b.get("needs_objective"))
        self.assertEqual(b["scores"], {})
        self.assertIsNone(b["brief"]["objective"])
        # Add more like these: the creators it adds are not scored either
        s, st, _ = c.post("/api/selection/status", {"token": token, "code": "HV-MI-001", "status": "approved"})
        self.assertTrue(st.get("ok"), st)
        s, more, _ = c.post("/api/selection/more", {"token": token, "count": 3})
        self.assertEqual(s, 200, more)
        added = [a["code"] for a in more.get("added") or []]
        b = self.scores(c, token)
        self.assertTrue(b.get("needs_objective"))
        self.assertEqual(b["scores"], {}, added)
        for a in more.get("added") or []:
            self.assertNotIn("score", a)
        # the free brief questions give the selection its objective: now it is scored
        s, att, _ = c.post("/api/brief/attach", {"token": token, "answers": ANSWERS})
        self.assertTrue(att.get("ok"), att)
        b = self.scores(c, token)
        self.assertNotIn("needs_objective", b)
        self.assertEqual(b["brief"]["objective"], "Engagement")
        self.assertIsNotNone(b["scores"]["HV-MI-001"]["score"])
        self.assertTrue(set(b["codes"]) <= set(b["scores"]))       # added creators included

    def test_02_an_objective_from_the_admin_or_a_campaign_counts(self):
        c, _ = self.signup("omar@obj-test.com")
        token = self.sel(c, "Admin objective", ["HV-MI-002"])
        sel = db.selection(token=token)
        db.set_selection_objective(sel["id"], "Awareness")
        self.assertNotIn("needs_objective", self.scores(c, token))
        token2 = self.sel(c, "Campaign objective", ["HV-MD-004"])
        sel2 = db.selection(token=token2)
        k = db.create_campaign("Spring", "Obj test", portal.user_by_email("omar@obj-test.com")["code_id"])
        db.save_campaign(k, selection_id=sel2["id"], objective="engagement")
        b = self.scores(c, token2)
        self.assertNotIn("needs_objective", b)
        self.assertIn("HV-MD-004", b["scores"])

    # -------------------------------------------- #9 the reject reason pop-up --
    def test_03_reject_reason_is_given_after_the_rejection(self):
        c, _ = self.signup("lama@why-test.com")
        token = self.sel(c, "Why test", ["HV-MI-001", "HV-MI-002", "HV-MD-004"])
        # a reason for a creator that is not rejected is refused
        s, b, _ = c.post("/api/selection/reason", {"token": token, "code": "HV-MI-001", "reason": "price"})
        self.assertEqual((s, b.get("reason")), (400, "not_rejected"))
        s, b, _ = c.post("/api/selection/status", {"token": token, "code": "HV-MI-001", "status": "rejected"})
        self.assertTrue(b.get("ok"), b)
        self.assertEqual((b["status"]["s"], b["status"]["reason"]), ("rejected", ""))   # the card shows only the "?"
        # a chip
        s, b, _ = c.post("/api/selection/reason", {"token": token, "code": "HV-MI-001", "reason": "price", "note": ""})
        self.assertEqual((s, b["status"]["reason"]), (200, "price"))
        # Other, with a few words (trimmed, one line)
        s, b, _ = c.post("/api/selection/reason", {"token": token, "code": "HV-MI-001", "reason": "other", "note": "  Too many\n sponsored   posts "})
        self.assertEqual((b["status"]["reason"], b["status"]["note"]), ("other", "Too many sponsored posts"))
        # an unknown chip is not stored as a reason
        s, b, _ = c.post("/api/selection/reason", {"token": token, "code": "HV-MI-001", "reason": "<script>", "note": ""})
        self.assertEqual(b["status"]["reason"], "")
        c.post("/api/selection/reason", {"token": token, "code": "HV-MI-001", "reason": "audience", "note": ""})
        # it stays rejected, and the page reads the reason back for the "?" tooltip
        b = self.scores(c, token)
        self.assertEqual((b["status"]["HV-MI-001"]["s"], b["status"]["HV-MI-001"]["reason"]), ("rejected", "audience"))
        self.assertEqual(b["status_counts"]["rejected"], 1)
        # a colleague sees the reason but cannot change it
        col, _ = self.signup("rana@why-test.com")
        b = self.scores(col, token)
        self.assertEqual((b["role"], b["status"]["HV-MI-001"]["reason"]), ("viewer", "audience"))
        s, r, _ = col.post("/api/selection/reason", {"token": token, "code": "HV-MI-001", "reason": "price"})
        self.assertEqual((s, r.get("reason")), (403, "not_owner"))
        # undo clears the reason with the rejection
        c.post("/api/selection/status", {"token": token, "code": "HV-MI-001", "status": "review"})
        self.assertEqual(self.scores(c, token)["status"]["HV-MI-001"]["reason"], "")

    # ---------------------------------------------------- #15 roster caching --
    def raw(self, c, path, headers=None):
        req = urllib.request.Request(self.base + path, headers=dict({"Origin": self.base}, **(headers or {})))
        try:
            r = c.op.open(req)
        except urllib.error.HTTPError as exc:
            r = exc
        return (r.status if hasattr(r, "status") else r.code), r.headers, r.read()

    def test_04_roster_is_cached_with_an_etag(self):
        locked = Client(self.base)
        s, h, body = self.raw(locked, "/api/roster")
        self.assertEqual(s, 401)
        self.assertIsNone(h.get("ETag"))
        c, _ = self.signup("hana@roster-test.com")
        s, h, body = self.raw(c, "/api/roster")
        self.assertEqual(s, 200)
        tag = h.get("ETag")
        self.assertTrue(tag and tag.startswith('"r-'), tag)
        self.assertIn("no-cache", h.get("Cache-Control"))
        b = json.loads(body)
        self.assertTrue(b["ok"])
        self.assertGreaterEqual(len(b["roster"]), 5)
        self.assertGreater(b["exp"], time.time())                   # when the kept copy must go
        self.assertIn("tiers", b)
        self.assertIn("fx", b)
        # the same version again: an empty 304, also when the browser lists several tags
        s, h2, body2 = self.raw(c, "/api/roster", {"If-None-Match": tag})
        self.assertEqual((s, body2, h2.get("ETag")), (304, b"", tag))
        s, _, _ = self.raw(c, "/api/roster", {"If-None-Match": '"stale", ' + tag})
        self.assertEqual(s, 304)
        # gzip when asked, the same document
        s, hz, zbody = self.raw(c, "/api/roster", {"Accept-Encoding": "gzip"})
        self.assertEqual((s, hz.get("Content-Encoding"), hz.get("ETag")), (200, "gzip", tag))
        self.assertEqual(json.loads(gzip.decompress(zbody)), b)
        # built once: a second request does not rebuild the roster
        calls = []
        orig = server.Handler._roster_build
        server.Handler._roster_build = lambda self, *a, **k: calls.append(1) or orig(self, *a, **k)
        try:
            self.raw(c, "/api/roster")
            self.assertEqual(calls, [])
            # a creator changes: a new version, a new tag, and the old tag no longer matches
            with db.connect() as conn:
                conn.execute("UPDATE creators SET city = 'Khobar', updated_at = ? WHERE code = 'HV-MI-005'", (db.now() + 5,))
            s, h3, body3 = self.raw(c, "/api/roster", {"If-None-Match": tag})
            self.assertEqual(s, 200)
            self.assertNotEqual(h3.get("ETag"), tag)
            self.assertEqual(len(calls), 1)
            self.assertEqual({r["code"]: r["city"] for r in json.loads(body3)["roster"]}["HV-MI-005"], "Khobar")
        finally:
            server.Handler._roster_build = orig

    # --------------------------------------------------- #5 one working day --
    def test_05_full_analysis_is_promised_within_one_working_day(self):
        self.assertEqual(gating.WORK_DAYS, 1)
        day = lambda y, m, d: calendar.timegm((y, m, d, 9, 0, 0))
        wd = lambda ts: time.gmtime(ts).tm_wday
        self.assertEqual(gating.ready_by(day(2026, 10, 5)) - day(2026, 10, 5), 86400)     # Monday -> Tuesday
        thu = day(2026, 10, 8)
        self.assertEqual(wd(thu), 3)
        self.assertEqual(wd(gating.ready_by(thu)), 6)                                      # Thursday -> Sunday
        self.assertEqual(gating.ready_by(thu) - thu, 3 * 86400)
        src = (Path(base.SRC) / "assistant.py").read_text() + (Path(base.SRC) / "server.py").read_text()
        self.assertNotIn("2 working days", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
