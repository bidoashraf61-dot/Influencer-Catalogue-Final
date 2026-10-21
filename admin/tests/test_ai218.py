"""Team AI, phase 1 (item 218, 2026-10-21): switches and caps, post checks, report drafts the KAM approves,
next-step suggestions and the 9:00 digest. Gemini is scripted (no paid call).

    python3 admin/tests/test_ai218.py
"""
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import db, gemini, guard, mailer, portal, server, views  # noqa: E402
import aifeatures, nextstep, postcheck, reportai  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

KAM, BOSS = "mariam.k@hvkam.com", "boss@hellovoice.co.uk"
CALLS = []


def stub(body):
    gen = body.get("generationConfig", {})
    props = (gen.get("responseSchema") or {}).get("properties", {})
    text = body["contents"][-1]["parts"][0].get("text", "")
    CALLS.append(sorted(props))
    if "risk" in props:
        out = ({"risk": "high", "issues": [{"kind": "claim", "quote": "cures acne", "why": "Promises a cure."}]}
               if "cures" in text else {"risk": "none", "issues": []})
    elif "worked" in props:
        out = {"summary": "Polyco wave is on track with strong engagement." + (" It cost SAR 900." if "PRICEY" in text else ""),
               "worked": ["Reels beat photos"], "improve": ["Two creators are late"], "next": ["Chase late posts", "Boost the top reel", "Add a story"]}
    elif "lines" in props:
        lines = json.loads(text.split("Lines:\n", 1)[1])
        out = {"lines": ["Friendly: " + l[:80] for l in lines]}
    else:
        return base.stub(body)
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(out)}]}}], "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 40}}


class TeamAI(unittest.TestCase):
    signup = base.Portal.signup
    member = base.Portal.member

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        mailer.CAPTURE = True
        gemini.STUB = stub
        views.set_base("")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        db.set_setting("domain_kam", {"polyco.com": KAM})
        db.set_setting("kams", ["Mariam K <%s>" % KAM])
        reportai.init(); postcheck.init()
        cls.ready = False

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()
        mailer.OUTBOX.clear()
        if not TeamAI.ready:
            W = TeamAI
            self.signup("lead@polyco.com")
            W.lead = portal.user_by_email("lead@polyco.com")
            W.s1 = db.save_selection(None, "Polyco glow", ["HV-MI-001", "HV-MI-002"], {}, None, None, code_id=W.lead["code_id"])
            W.k1 = db.create_campaign("Polyco wave", code_id=W.lead["code_id"], selection_id=W.s1)
            now = db.now()
            db.save_campaign(W.k1, status="live", starts_at=now - 10 * 86400, ends_at=now + 4 * 86400)
            with db.connect() as conn:
                conn.execute("UPDATE campaigns SET rules = ? WHERE id = ?",
                             (json.dumps({"hashtags": ["#polyco", "#glowup"], "mentions": [], "keywords": [], "disclosure": ["#ad"]}), W.k1))
            db.add_campaign_creators(W.k1, ["HV-MI-001", "HV-MI-002"])
            W.p_ok = self._post("HV-MI-001", "https://www.instagram.com/p/ok1/", "Loving it #polyco #glowup #ad")
            W.p_nodisc = self._post("HV-MI-001", "https://www.instagram.com/p/nodisc/", "Loving it #polyco #glowup")
            W.p_notag = self._post("HV-MI-002", "https://www.instagram.com/p/notag/", "Glow #polyco #ad")
            W.p_empty = self._post("HV-MI-002", "https://www.instagram.com/stories/x/1/", "")
            self.member(BOSS, "owner"); self.member(KAM, "kam")
            W.boss = self.signup(BOSS)[0]; W.kam = self.signup(KAM)[0]
            W.client = self.signup("other@polyco.com")[0]
            W.k = lambda: db.campaign(W.k1)
            TeamAI.ready = True

    def _post(self, code, url, caption):
        cid, _ = db.add_content(TeamAI.k1, {"code": code, "platform": "Instagram", "kind": "reel", "url": url,
                                            "posted_at": db.now() - 86400, "caption": caption or None,
                                            "views": 12000, "likes": 800, "comments": 40, "followers": 40000})
        return cid

    def check(self, cid):
        return postcheck.check(db.content_item(cid), TeamAI.k())

    # ------------------------------------------------------------ switches --
    def test_01_helpers_ship_off(self):
        for name in aifeatures.FEATURES:
            self.assertFalse(aifeatures.conf(name)["on"])
            self.assertFalse(aifeatures.allowed(name))
            self.assertEqual(aifeatures.why_not(name), "switched off")
        aifeatures.save("report", on=True, cap=0.0)
        self.assertEqual(aifeatures.why_not("report"), "this month's cap is used")
        aifeatures.save("report", on=False, cap=10)

    # --------------------------------------------------------- post checks --
    def test_02_rules_are_free_and_always_on(self):
        CALLS.clear()
        self.assertEqual(self.check(self.p_ok)["status"], "pass")
        r = self.check(self.p_nodisc)
        self.assertEqual(r["status"], "fail")
        self.assertIn("disclosure", r["reasons"][0]["text"].lower())
        r = self.check(self.p_notag)
        self.assertEqual((r["status"], r["reasons"][0]["kind"]), ("warn", "tags"))
        self.assertEqual(self.check(self.p_empty)["status"], "none")
        self.assertEqual(CALLS, [], "no Gemini call while the helper is off")
        # The KAM heard about the failing post, once.
        kam = portal.user_by_email(KAM)
        with db.connect() as conn:
            n = conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND kind = 'team_flag'", (kam["id"],)).fetchone()[0]
        self.assertEqual(n, 1)
        self.check(self.p_nodisc)
        with db.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM notifications WHERE kind = 'team_flag'").fetchone()[0], 1)
        # The client never gets one.
        with db.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM notifications WHERE kind = 'team_flag' AND user_id = ?",
                                          (TeamAI.lead["id"],)).fetchone()[0], 0)

    def test_03_ai_layer_reads_claims_once_per_caption(self):
        aifeatures.save("compliance", on=True)
        try:
            cid = self._post("HV-MI-002", "https://www.instagram.com/p/claim/", "This cream cures acne in 3 days #polyco #glowup #ad")
            CALLS.clear()
            r = self.check(cid)
            self.assertEqual(r["status"], "fail")
            self.assertTrue(r["ai"])
            self.assertTrue(any("cure" in x["text"].lower() for x in r["reasons"]))
            self.check(cid)
            self.assertEqual(len(CALLS), 1, "same caption, no second call")
            self.assertGreater(aifeatures.spent("compliance"), 0)
            # "OK as is" clears it until the caption changes.
            code, got = postcheck.clear(TeamAI.k(), KAM, cid)
            self.assertEqual(code, 200)
            self.assertEqual(postcheck.of_campaign(TeamAI.k1)[cid]["status"], "ok")
            with db.connect() as conn:
                conn.execute("UPDATE content SET caption = 'Now it cures everything #polyco #glowup #ad' WHERE id = ?", (cid,))
            self.assertEqual(self.check(cid)["status"], "fail")
        finally:
            aifeatures.save("compliance", on=False)

    def test_04_job_and_needs_queue(self):
        postcheck.tick()
        g = {x["key"]: x for x in self.kam.get("/api/needs")[1]["groups"]}
        self.assertIn("flags", g)
        self.assertEqual(g["flags"]["items"][0]["token"], TeamAI.k()["token"])

    # ------------------------------------------------------------- reports --
    def test_05_report_needs_the_switch(self):
        self.assertIsNone(reportai.draft(TeamAI.k(), "w1"))
        self.assertIsNone(reportai.row(TeamAI.k1, "w1"))

    def test_06_draft_approve_and_client_view(self):
        aifeatures.save("report", on=True)
        try:
            got = reportai.draft(TeamAI.k(), "w1")
            self.assertEqual(got["status"], "draft")
            self.assertEqual(len(got["draft"]["next"]), 3)
            self.assertIsNone(reportai.client_view(TeamAI.k()), "nothing for the client before approval")
            kam = portal.user_by_email(KAM)
            with db.connect() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND kind = 'team_report'",
                                              (kam["id"],)).fetchone()[0], 1)
            # In the Edit mode and the queue.
            s, b, _ = self.kam.get("/api/edit/campaign?t=" + TeamAI.k()["token"])
            self.assertEqual(s, 200)
            self.assertEqual(b["reports"]["reports"][0]["period"], "w1")
            self.assertIn("check", b["creators"][0]["posts"][0])
            self.assertEqual(self.client.get("/api/edit/campaign?t=" + TeamAI.k()["token"])[0], 403)
            g = {x["key"]: x for x in self.kam.get("/api/needs")[1]["groups"]}
            self.assertIn("reports", g)
            # A price in the KAM's text is refused.
            t = TeamAI.k()["token"]
            s, b, _ = self.kam.post("/api/edit/report", {"t": t, "do": "approve", "period": "w1", "summary": "Fees were SAR 400.",
                                                          "worked": [], "improve": [], "next": ["x"]})
            self.assertEqual(s, 400)
            s, b, _ = self.kam.post("/api/edit/report", {"t": t, "do": "approve", "period": "w1", "summary": "On track, edited by Mariam.",
                                                          "worked": ["Reels"], "improve": [], "next": "Chase late posts\nBoost the top reel"})
            self.assertEqual(s, 200, b)
            cv = reportai.client_view(TeamAI.k())
            self.assertEqual(cv["summary"], "On track, edited by Mariam.")
            self.assertEqual(cv["next"], ["Chase late posts", "Boost the top reel"])
            with db.connect() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND kind = 'camp_report' AND ref LIKE 'repok:%'",
                                              (TeamAI.lead["id"],)).fetchone()[0], 1)
            # A client cannot approve.
            self.assertEqual(self.client.post("/api/edit/report", {"t": t, "do": "dismiss", "period": "w1"})[0], 403)
        finally:
            aifeatures.save("report", on=False)

    def test_07_redo_limit_and_banned_drafts(self):
        aifeatures.save("report", on=True)
        try:
            reportai.draft(TeamAI.k(), "w2", notify=False)
            for _ in range(reportai.MAX_TRIES - 1):
                self.assertEqual(reportai.redo(TeamAI.k(), "w2")[0], 200)
            self.assertEqual(reportai.redo(TeamAI.k(), "w2")[0], 400)
            self.assertIsNone(reportai._clean({"summary": "It cost SAR 900.", "worked": [], "improve": [], "next": ["a"]}))
            self.assertIsNone(reportai._clean({"summary": "Top creator scored 88.", "worked": [], "improve": [], "next": ["a"]}))
        finally:
            aifeatures.save("report", on=False)

    # ----------------------------------------------------------- next step --
    def test_08_suggestions(self):
        k = TeamAI.k()
        s = nextstep.suggest(k, "live")
        self.assertIn(s["key"], ("flags", "report"))
        with db.connect() as conn:
            conn.execute("UPDATE campaigns SET next_step = 'Send wave 2', next_due = ? WHERE id = ?", (db.now() - 3 * 86400, TeamAI.k1))
        s = nextstep.suggest(TeamAI.k(), "live")
        self.assertEqual((s["key"], s["text"]), ("overdue", "Send wave 2"))
        with db.connect() as conn:
            conn.execute("UPDATE campaigns SET next_step = NULL, next_due = NULL WHERE id = ?", (TeamAI.k1,))
        k2 = db.create_campaign("Quiet one", code_id=TeamAI.lead["code_id"])
        with db.connect() as conn:
            conn.execute("UPDATE campaigns SET updated_at = ? WHERE id = ?", (db.now() - 10 * 86400, k2))
        s = nextstep.suggest(db.campaign(k2), "draft")
        self.assertEqual(s["key"], "quiet")
        self.assertEqual(nextstep.suggest(db.campaign(k2), "approved")["key"], "golive")
        # The board card carries it for the team only.
        s, b, _ = self.kam.get("/api/board")
        self.assertEqual(s, 200)
        mine = {c["id"]: c for c in b["campaigns"]}
        self.assertIn("suggest", mine[TeamAI.k1])
        self.assertEqual(mine[k2]["suggest"]["key"], "quiet")
        s, b, _ = self.client.get("/api/board")
        if s == 200:
            self.assertFalse(any("suggest" in c for c in b["campaigns"]), "clients never get suggestions")

    def test_09_digest_once_a_day(self):
        CALLS.clear()
        n = nextstep.digest()
        self.assertGreaterEqual(n, 2)                 # the owner and the KAM
        self.assertEqual(CALLS, [], "rule-written while the helper is off")
        self.assertEqual(nextstep.digest(), n)       # sent again, but the bell keeps one per day
        kam = portal.user_by_email(KAM)
        with db.connect() as conn:
            rows = conn.execute("SELECT title, body FROM notifications WHERE user_id = ? AND kind = 'team_digest'", (kam["id"],)).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertIn("Polyco wave", rows[0]["body"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM notifications WHERE kind = 'team_digest' AND user_id = ?",
                                          (TeamAI.lead["id"],)).fetchone()[0], 0)
        aifeatures.save("nextstep", on=True)
        try:
            self.assertEqual(nextstep._reworded(["A: b"]), ["Friendly: A: b"])
        finally:
            aifeatures.save("nextstep", on=False)

    def test_11_admin_card_and_save(self):
        import portal_views
        html = portal_views.team_ai_card()
        for label in ("Report writer", "Post checks", "Next-step digest", "tai_on_report", "tai_cap_compliance"):
            self.assertIn(label, html)
        aifeatures.save("compliance", on=True, cap=7)
        self.assertEqual(aifeatures.conf("compliance"), {"on": True, "cap": 7.0})
        aifeatures.save("compliance", on=False, cap=15)

    def test_10_due_at_nine_riyadh(self):
        import calendar
        nine = calendar.timegm((2026, 10, 22, 6, 0, 0)) + 60        # 09:01 Riyadh
        db.set_setting("digest_last_day", "")
        self.assertFalse(nextstep.due(nine - 3600))
        self.assertTrue(nextstep.due(nine))
        db.set_setting("digest_last_day", "2026-10-22")
        self.assertFalse(nextstep.due(nine))


if __name__ == "__main__":
    unittest.main(verbosity=2)
