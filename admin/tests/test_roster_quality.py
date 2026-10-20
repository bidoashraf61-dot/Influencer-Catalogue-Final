"""Roster quality (items 224-225, 2026-10-21): the out-of-scope rules, the review queue (archive /
keep / protected / undo), the AI read, and the same-handle pairs the profile-link key misses.

    python3 admin/tests/test_roster_quality.py
"""
import json
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import db, gemini, history, rosterq, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

base.seed()


def aud(**pct):
    """An analysis with these audience countries, e.g. aud(SA=60, IN=20)."""
    return {"audience": {"countries": [{"code": k, "name": k, "pct": v} for k, v in pct.items()]}}


def creator(code, handle, platform="Instagram", followers=40000, note="source sheet", name=None, profiles=None):
    db.upsert_creator({"code": code, "name": name or code, "handle": handle, "platform": platform, "followers": followers,
                       "city": "UAE Not Specified yet", "nationality": None, "tier": "Micro", "interest": "", "photo": None,
                       "profiles": json.dumps(profiles if profiles is not None else
                                              [{"platform": platform, "url": "https://%s.com/%s" % (platform.lower(), handle)}]),
                       "active": 1, "note": note, "sort": 0})


class Rules(unittest.TestCase):
    def a(self, analyses, **c):
        row = {"code": "X", "handle": c.get("handle", "real.name"), "followers": c.get("followers", 40000), "note": c.get("note", "src")}
        return rosterq.assess(row, analyses, c.get("posts"))

    def keys(self, r):
        return {x["key"] for x in r["reasons"]}

    def test_local_audience_is_in_scope(self):
        r = self.a({"Instagram": aud(SA=55, IN=20)})
        self.assertEqual(self.keys(r), set())
        self.assertFalse(r["unclear"])

    def test_under_ten_percent_alone_is_out(self):
        r = self.a({"Instagram": aud(IN=80, AE=4)})
        self.assertIn("audience_out", self.keys(r))
        self.assertTrue(r["preselect"])

    def test_ten_to_25_needs_a_second_signal(self):
        self.assertEqual(self.keys(self.a({"TikTok": aud(SA=18, IQ=40)})), set())               # borderline alone: kept
        self.assertTrue(self.a({"TikTok": aud(SA=18, IQ=40)})["unclear"])                      # ...and sent to the AI
        d = dict(aud(SA=18, IQ=40), fake_followers_pct=40)
        self.assertIn("audience_out", self.keys(self.a({"Instagram": d})))
        d = dict(aud(SA=18, IQ=40), er=0.1, followers=50000)
        self.assertIn("audience_out", self.keys(self.a({"Instagram": d})))
        d = dict(aud(SA=18, IQ=40), content_languages=["Russian"])
        self.assertIn("audience_out", self.keys(self.a({"Instagram": d})))

    def test_gcc_counts_toward_the_share(self):
        r = self.a({"Instagram": aud(KW=30, IQ=40)})
        self.assertEqual(self.keys(r), set())
        self.assertEqual(r["mix"]["gcc"], 30)
        self.assertEqual(r["mix"]["core"], 0)

    def test_best_platform_wins(self):
        self.assertEqual(self.keys(self.a({"Instagram": aud(IN=90), "TikTok": aud(SA=70)})), set())

    def test_fake_followers_alone_is_flagged_but_not_preticked(self):
        r = self.a({"Instagram": dict(aud(SA=60), fake_followers_pct=72)})
        self.assertEqual(self.keys(r), {"fake_followers"})
        self.assertFalse(r["preselect"])

    def test_big_creator_with_some_local_audience_is_not_preticked(self):
        d = dict(aud(SA=15, IQ=40), fake_followers_pct=40)
        r = self.a({"Instagram": d}, followers=900000)
        self.assertIn("audience_out", self.keys(r))
        self.assertFalse(r["preselect"])

    def test_language(self):
        self.assertIn("language", self.keys(self.a({"TikTok": {"content_languages": ["Amharic", "Oromo"]}})))
        self.assertEqual(self.keys(self.a({"TikTok": {"content_languages": ["Unknown"]}})), set())
        self.assertEqual(self.keys(self.a({"TikTok": {"content_languages": ["Urdu", "English"]}})), set())

    def test_placeholder_handle_with_local_audience_is_real(self):
        self.assertEqual(self.keys(self.a({"TikTok": aud(SA=69)}, handle="user217216810739")), set())
        self.assertIn("placeholder", self.keys(self.a({}, handle="user217216810739")))
        self.assertIn("placeholder", self.keys(self.a({}, note="")))                 # no analysis, no source
        self.assertIn("placeholder", self.keys(self.a({"TikTok": aud(SA=60)}, posts=[0, 0])))

    def test_no_names_in_the_ai_evidence(self):
        ev = rosterq.evidence({"platform": "TikTok", "followers": 1, "city": "Dubai", "name": "Secret Name"},
                              {"TikTok": dict(aud(AE=20), bio="hello")})
        self.assertNotIn("Secret Name", json.dumps(ev))


class Queue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rosterq.init()
        gemini.STUB = None
        views.set_base("")
        creator("HV-T-001", "far.away")                                   # audience out
        creator("HV-T-002", "local.one")                                  # in scope
        creator("HV-T-003", "on.a.list")                                  # out, but on a selection
        creator("HV-T-004", "fakey")                                      # fake only
        creator("HV-T-005", "nodata")                                     # unclear
        db.save_analysis("HV-T-001", dict(aud(IN=85), platform="Instagram"), "test", platform="Instagram")
        db.save_analysis("HV-T-002", dict(aud(SA=70), platform="Instagram"), "test", platform="Instagram")
        db.save_analysis("HV-T-003", dict(aud(BR=90), platform="Instagram"), "test", platform="Instagram")
        db.save_analysis("HV-T-004", dict(aud(AE=60), fake_followers_pct=80, platform="Instagram"), "test", platform="Instagram")
        db.save_analysis("HV-T-005", {"platform": "Instagram", "bio": "Dubai mum"}, "test", platform="Instagram")
        db.save_selection(None, "Client list", ["HV-T-003"], {}, None, None)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def scan(self):
        with db.connect() as conn:
            res = rosterq.scan(conn)
        rosterq.save_scan(res)
        return {r["code"]: r for r in res}

    def admin(self):
        c = base.Client(self.base)
        s, _, _ = c.req("POST", "/login", form={"email": "boss@hellovoice.co.uk", "password": "correct-horse-battery"})
        self.assertEqual(s, 303)
        return c

    def test_10_scan_and_queue(self):
        res = self.scan()
        self.assertIn("HV-T-001", res)
        self.assertNotIn("HV-T-002", res)
        self.assertTrue(res["HV-T-003"]["protected"])
        self.assertTrue(res["HV-T-005"]["unclear"])
        q = {d["code"]: d for d in rosterq.queue()}
        self.assertEqual(q["HV-T-001"]["preselect"], 1)
        self.assertEqual(q["HV-T-004"]["preselect"], 0)
        self.assertEqual({d["code"] for d in rosterq.queue("unclear")} & {"HV-T-001", "HV-T-004"}, set())

    def test_20_page_renders(self):
        self.scan()
        a = self.admin()
        s, html, _ = a.get("/roster/quality")
        self.assertEqual(s, 200)
        self.assertIn("HV-T-001", html)
        self.assertIn("Archive ticked", html)
        self.assertIn("in use", html)                                     # the protected one has a lock, no box
        self.assertNotIn("value='HV-T-003'", html)
        for path in ("/roster/quality?tab=kept", "/roster/quality?tab=archived", "/roster/quality?tab=pairs",
                     "/roster/quality?reason=fake_followers", "/roster/quality?reason=unclear", "/roster"):
            self.assertEqual(a.get(path)[0], 200, path)

    def test_30_archive_hides_and_undo_restores(self):
        self.scan()
        a = self.admin()
        s, _, r = a.req("POST", "/roster/quality/decide", form=[("do", "archive"), ("codes", "HV-T-001"), ("codes", "HV-T-003")])
        self.assertEqual(s, 303)
        self.assertIn("1%20archived", r.headers["Location"].replace("+", "%20"))
        self.assertEqual(db.creator("HV-T-001")["active"], 0)
        self.assertIn("out of scope", db.creator("HV-T-001")["note"])
        self.assertEqual(db.creator("HV-T-003")["active"], 1)            # on a selection: never archived
        self.assertNotIn("HV-T-001", {c["code"] for c in db.list_creators(active_only=True)})
        self.assertIn("HV-T-001", {d["code"] for d in rosterq.queue(status="archived")})
        with db.connect() as conn:
            hid = conn.execute("SELECT id FROM history WHERE entity = 'creator' AND key = 'HV-T-001' AND label LIKE 'Archived%' "
                               "ORDER BY id DESC").fetchone()[0]
        history.undo(hid)
        self.assertEqual(db.creator("HV-T-001")["active"], 1)

    def test_40_keep_stays_kept_until_new_evidence(self):
        self.scan()
        rosterq.keep(["HV-T-004"], "test")
        self.scan()
        self.assertIn("HV-T-004", {d["code"] for d in rosterq.queue(status="kept")})
        db.save_analysis("HV-T-004", dict(aud(IN=90), fake_followers_pct=80, platform="Instagram"), "test", platform="Instagram")
        self.scan()
        self.assertIn("HV-T-004", {d["code"] for d in rosterq.queue()})   # a new reason reopens it

    def test_50_ai_read_unclear(self):
        self.scan()
        seen = {}

        def stub(body):
            text = body["contents"][-1]["parts"][0]["text"]
            seen["text"] = text
            n = text.count("\n")
            items = [{"i": i, "verdict": "out", "reason": "audience abroad"} for i in range(n)]
            return {"candidates": [{"content": {"parts": [{"text": json.dumps({"items": items})}]}}],
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 10}}
        gemini.STUB = stub
        try:
            self.assertGreaterEqual(rosterq.ai_review(), 1)
        finally:
            gemini.STUB = None
        q = {d["code"]: d for d in rosterq.queue("ai_out")}
        self.assertIn("HV-T-005", q)
        self.assertEqual(q["HV-T-005"]["ai_verdict"], "out")

    def test_60_background_job_is_single_flight(self):
        self.assertTrue(rosterq.start("scan", "test"))
        self.assertFalse(rosterq.start("scan", "test"))
        for _ in range(100):
            if not rosterq.running():
                break
            time.sleep(0.05)
        self.assertFalse(rosterq.running())
        self.assertIn("flagged", rosterq.JOB["message"])

    def test_70_kam_cannot_archive(self):
        import team
        self.assertFalse(team.can({"role": "kam"}, "POST", "/roster/quality/decide"))


class Pairs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        creator("HV-P-001", "noha.magdi", name="Noha Magdi")
        creator("HV-P-002", "nohamagdi", name="Noha Magdi")                          # same platform, written differently
        creator("HV-P-003", "sara_style", platform="Instagram", name="Sara")
        creator("HV-P-004", "sara_style", platform="TikTok", name="Sara")            # IG card + TikTok card
        creator("HV-P-005", "other", platform="TikTok", name="Other")

    def test_pairs(self):
        groups = rosterq.dupe_candidates()
        by = {tuple(sorted(c["code"] for c in g["creators"])): g for g in groups}
        self.assertEqual(by[("HV-P-001", "HV-P-002")]["kind"], "same")
        self.assertEqual(by[("HV-P-003", "HV-P-004")]["kind"], "cross")
        self.assertTrue(by[("HV-P-003", "HV-P-004")]["strong"])
        self.assertFalse(any("HV-P-005" in k for k in by))

    def test_known_groups_left_out(self):
        groups = rosterq.dupe_candidates(known={"HV-P-001", "HV-P-002"})
        self.assertFalse(any({c["code"] for c in g["creators"]} == {"HV-P-001", "HV-P-002"} for g in groups))


if __name__ == "__main__":
    unittest.main(verbosity=2)
