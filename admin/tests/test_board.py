"""Campaign board (items 174, 176, 177, 182; owner 2026-10-20): campaign-first, six stages, who sees what,
admin-only stage moves and Live / Unlive (server side), "Create campaign with this selection", per-person pins,
and no scores or analysis for clients and key account managers.

    python3 admin/tests/test_board.py
"""
import json
import shutil
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import board, db, gemini, guard, lifecycle, mailer, portal, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

KAM, OTHER, BOSS = "mariam.k@hvkam.com", "omar.k@hvkam.com", "boss@hellovoice.co.uk"


class Board(unittest.TestCase):
    signup = base.Portal.signup
    member = base.Portal.member

    @classmethod
    def setUpClass(cls):
        base.seed()
        import apify
        apify.init()
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
        if Board.ready:
            return
        W = Board
        W.lead, _ = self.signup("lead@polyco.com")
        W.mate, _ = self.signup("mate@polyco.com")
        W.rival, _ = self.signup("buyer@rivalco.com")
        W.u_lead = portal.user_by_email("lead@polyco.com")
        W.u_rival = portal.user_by_email("buyer@rivalco.com")
        lc, rc = W.u_lead["code_id"], W.u_rival["code_id"]
        W.s_empty = db.save_selection(None, "Empty list", [], {}, None, None, code_id=lc)
        W.s_full = db.save_selection(None, "Glow list", ["HV-MI-001", "HV-MI-002"], {}, None, None, code_id=lc)
        W.s_more = db.save_selection(None, "Second wave", ["HV-MD-003"], {}, None, None, code_id=lc)
        W.s_rival = db.save_selection(None, "Rival list", ["HV-MD-004"], {}, None, None, code_id=rc)
        W.k_draft = db.create_campaign("Poly draft", client="Polyco", code_id=lc, selection_id=W.s_empty)
        W.k_short = db.create_campaign("Poly shortlist", client="Polyco", code_id=lc, selection_id=W.s_full)
        W.k_live = db.create_campaign("Poly live", client="Polyco", code_id=lc)
        db.save_campaign(W.k_live, status="live", starts_at=1, ends_at=int(time.time()) + 86400)
        W.k_done = db.create_campaign("Poly done", client="Polyco", code_id=lc)
        db.save_campaign(W.k_done, status="ended", starts_at=1, ends_at=2)
        W.k_rival = db.create_campaign("Rival draft", client="Rivalco", code_id=rc, selection_id=W.s_rival)
        self.member(BOSS, "owner"); self.member(KAM, "kam"); self.member(OTHER, "kam")
        W.boss, _ = self.signup(BOSS)
        W.kam, _ = self.signup(KAM)
        W.ready = True

    # ------------------------------------------------------------------ stages
    def test_01_existing_campaigns_map_without_writes(self):
        stages = {k: board.stage_of(db.campaign(k)) for k in (self.k_draft, self.k_short, self.k_live, self.k_done)}
        self.assertEqual(stages, {self.k_draft: "draft", self.k_short: "shortlisting", self.k_live: "live", self.k_done: "completed"})
        with db.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM campaigns WHERE stage IS NOT NULL").fetchone()[0], 0)
        # a requested quote reads Client review, an approved one Approved
        sel = db.selection(self.s_full)
        lifecycle.mark_requested(sel, by_name="Lead")
        self.assertEqual(board.stage_of(db.campaign(self.k_short)), "review")
        lifecycle.set_ready(sel, "", "", "HV")
        lifecycle.approve(sel, None, "Lead")
        self.assertEqual(board.stage_of(db.campaign(self.k_short)), "approved")
        # undo for the rest of the tests
        with db.connect() as conn:
            conn.execute("DELETE FROM selection_quote WHERE selection_id = ?", (self.s_full,))
        self.assertEqual(board.stage_of(db.campaign(self.k_short)), "shortlisting")

    # ------------------------------------------------------------- visibility
    def test_02_who_sees_what(self):
        s, b, _ = self.boss.get("/api/board")
        self.assertEqual((s, b["role"], b["can_move"]), (200, "admin", True), b)
        names = {c["name"] for c in b["campaigns"]}
        self.assertTrue({"Poly draft", "Poly live", "Rival draft"} <= names)
        self.assertEqual([x["key"] for x in b["stages"]], list(board.STAGES))
        s, b, _ = self.kam.get("/api/board")
        self.assertEqual((s, b["role"], b["can_move"]), (200, "kam", False))
        names = {c["name"] for c in b["campaigns"]}
        self.assertIn("Poly draft", names)
        self.assertNotIn("Rival draft", names)                        # another KAM's client
        s, b, _ = self.lead.get("/api/board")
        self.assertEqual((s, b["role"], b["can_move"]), (200, "client", False))
        names = {c["name"] for c in b["campaigns"]}
        self.assertTrue({"Poly draft", "Poly shortlist", "Poly live", "Poly done"} <= names)   # drafts included
        self.assertNotIn("Rival draft", names)
        c = next(x for x in b["campaigns"] if x["name"] == "Poly shortlist")
        self.assertEqual(c["selections"][0]["name"], "Glow list")
        self.assertNotIn("kam", c)                                     # the team's fields stay with the team
        blob = json.dumps(b)
        for word in ("score", "cost", "analysis"):
            self.assertNotIn('"%s' % word, blob)
        self.assertEqual(base.Client(self.base).get("/api/board")[0], 401)

    # ---------------------------------------------------------- admin-only moves
    def test_03_only_admins_move_and_set_live(self):
        tok = db.campaign(self.k_draft)["token"]
        for who in (self.lead, self.kam):
            s, b, _ = who.post("/api/board/stage", {"t": tok, "to": "review"})
            self.assertEqual(s, 403, b)
            s, b, _ = who.post("/api/board/live", {"t": tok, "on": True})
            self.assertEqual(s, 403, b)
        self.assertIsNone(db.campaign(self.k_draft)["stage"])
        s, b, _ = self.rival.post("/api/board/stage", {"t": tok, "to": "review"})
        self.assertEqual(s, 404)                                       # not even visible
        s, b, _ = self.boss.post("/api/board/stage", {"t": tok, "to": "review"})
        self.assertEqual((s, b["stage"]), (200, "review"), b)
        s, b, _ = self.boss.post("/api/board/live", {"t": tok, "on": True})
        self.assertEqual(s, 400)                                       # no dates yet
        self.assertIn("setup", b)
        db.save_campaign(self.k_draft, starts_at=1, ends_at=int(time.time()) + 86400)
        s, b, _ = self.boss.post("/api/board/live", {"t": tok, "on": True})
        self.assertEqual((s, db.campaign(self.k_draft)["status"], b["stage"]), (200, "live", "live"), b)
        s, b, _ = self.boss.post("/api/board/live", {"t": tok, "on": False})
        k = db.campaign(self.k_draft)
        self.assertEqual((s, k["status"], board.stage_of(k)), (200, "draft", "approved"))
        s, b, _ = self.boss.post("/api/board/stage", {"id": self.k_draft, "to": "completed"})
        self.assertEqual((s, db.campaign(self.k_draft)["status"]), (200, "ended"))
        s, b, _ = self.boss.post("/api/board/stage", {"id": self.k_draft, "to": "draft"})
        self.assertEqual((db.campaign(self.k_draft)["status"], board.stage_of(db.campaign(self.k_draft))), ("draft", "draft"))
        self.assertEqual(self.boss.post("/api/board/stage", {"t": tok, "to": "nowhere"})[0], 400)

    # ------------------------------------------------- create campaign with this selection
    def test_04_create_campaign_from_a_selection(self):
        tok = db.selection(self.s_more)["token"]
        s, b, _ = self.lead.get("/api/board/targets?s=" + tok)
        self.assertEqual(s, 200, b)
        names = [c["name"] for c in b["campaigns"]]
        self.assertIn("Poly shortlist", names)
        self.assertNotIn("Poly done", names)                           # completed campaigns take no new selections
        self.assertNotIn("Rival draft", names)
        self.assertEqual(self.rival.get("/api/board/targets?s=" + tok)[0], 404)
        # a new campaign: Draft, the client's KAM holds it and is told
        mailer.OUTBOX.clear()
        s, b, _ = self.lead.post("/api/board/attach", {"s": tok, "name": "Ramadan glow"})
        self.assertEqual((s, b["created"], b["campaign"]["stage"]), (200, True, "draft"), b)
        k = db.campaign(token=b["campaign"]["token"])
        self.assertEqual((k["code_id"], k["selection_id"], k["origin"], k["status"]), (self.u_lead["code_id"], self.s_more, "client", "draft"))
        self.assertEqual(db.kam_of_item("campaign", k["id"]), KAM)
        time.sleep(0.3)
        self.assertTrue(any(m["to"] == KAM for m in mailer.OUTBOX), mailer.OUTBOX)
        u_kam = portal.user_by_email(KAM)
        with db.connect() as conn:
            self.assertTrue(conn.execute("SELECT 1 FROM notifications WHERE user_id = ? AND ref LIKE 'board:%'", (u_kam["id"],)).fetchone())
        self.assertEqual(self.lead.post("/api/board/attach", {"s": tok, "name": "x"})[0], 400)    # name too short
        # add to an existing campaign: the campaign now holds two selections and their creators
        short = db.campaign(self.k_short)
        s, b, _ = self.lead.post("/api/board/attach", {"s": tok, "t": short["token"]})
        self.assertEqual((s, b["created"]), (200, False), b)
        self.assertEqual(board.selection_ids(short), [self.s_full, self.s_more])
        self.assertIn("HV-MD-003", [r["code"] for r in db.campaign_creators(self.k_short)])
        s, b, _ = self.lead.post("/api/board/attach", {"s": tok, "t": short["token"]})
        self.assertIn("Already", b["message"])
        # never into another client's campaign
        s, b, _ = self.lead.post("/api/board/attach", {"s": tok, "t": db.campaign(self.k_rival)["token"]})
        self.assertEqual(s, 400)
        # a colleague may file it too; a KAM for her own client; the board shows both selections
        s, b, _ = self.kam.post("/api/board/attach", {"s": db.selection(self.s_empty)["token"], "t": short["token"]})
        self.assertEqual(s, 200, b)
        s, bb, _ = self.lead.get("/api/board")
        c = next(x for x in bb["campaigns"] if x["name"] == "Poly shortlist")
        self.assertEqual([x["name"] for x in c["selections"]], ["Glow list", "Second wave", "Empty list"])
        # the report carries the campaign's selections
        db.save_campaign(self.k_short, status="live", starts_at=1, ends_at=int(time.time()) + 86400)
        s, rep, _ = self.lead.get("/api/campaign?t=" + short["token"])
        self.assertEqual(s, 200, rep)
        self.assertEqual([x["name"] for x in rep["report"]["campaign"]["selections"]], ["Glow list", "Second wave", "Empty list"])
        # a selection inside a live campaign reads "Campaign live" in its chip, whichever slot it is in
        self.assertEqual(lifecycle.chip(db.selection(self.s_more))["key"], "live")
        db.save_campaign(self.k_short, status="draft")

    # ----------------------------------------------------------------- pins
    def test_05_pins_are_per_person(self):
        tok = db.campaign(self.k_done)["token"]
        s, b, _ = self.lead.post("/api/board/pin", {"t": tok, "on": True})
        self.assertEqual((s, b["my_pin"]), (200, True))
        first = self.lead.get("/api/board")[1]["campaigns"][0]
        self.assertEqual((first["name"], first["my_pin"]), ("Poly done", True))
        mate = self.mate.get("/api/board")[1]["campaigns"]
        self.assertFalse(next(c for c in mate if c["name"] == "Poly done")["my_pin"])
        self.lead.post("/api/board/pin", {"t": tok, "on": False})
        self.assertFalse(next(c for c in self.lead.get("/api/board")[1]["campaigns"] if c["name"] == "Poly done")["my_pin"])
        self.assertEqual(self.rival.post("/api/board/pin", {"t": tok, "on": True})[0], 404)

    # ----------------------------------------------------------- admin hub (177)
    def test_06_hub_rows_carry_the_stage(self):
        s, d, _ = self.boss.get("/api/hub/company?k=polyco.com")
        self.assertEqual(s, 200)
        rows = [k for p in d["people"] for k in p["campaigns"]]
        self.assertTrue(rows)
        self.assertTrue(all(r["stage"]["key"] in board.STAGES and r["can_stage"] for r in rows))
        s, d, _ = self.kam.get("/api/hub/company?k=polyco.com")
        rows = [k for p in d["people"] for k in p["campaigns"]]
        self.assertTrue(rows and not any(r["can_stage"] for r in rows))
        s, d, _ = self.boss.get("/api/hub/campaigns")
        self.assertTrue(all("stage" in r for r in d["items"]))

    # ----------------------------------------------------- scores and analysis (8)
    def test_07_no_scores_for_clients_or_kams(self):
        with db.connect() as conn:
            conn.execute("UPDATE selections SET scores_published = 1, analysis_published = 1 WHERE id = ?", (self.s_full,))
        tok = db.selection(self.s_full)["token"]
        s, b, _ = self.lead.get("/api/selection?s=" + tok)
        self.assertEqual(s, 200, b)
        self.assertEqual((b["scores"], b["scores_gate"]["team"], b["scores_gate"]["analysis"]), ({}, False, False))
        s, b, _ = self.kam.get("/api/selection?s=" + tok)
        self.assertEqual(s, 200, b)
        self.assertEqual((b["scores"], b["scores_gate"]["team"], b["scores_gate"]["analysis"]), ({}, False, False))
        for who in (self.kam, self.lead):
            s, b, _ = who.post("/api/selection/scores", {"token": tok, "publish": False})
            self.assertEqual(s, 403, b)
        s, b, _ = self.boss.get("/api/selection?s=" + tok)
        self.assertTrue(b["scores_gate"]["team"])
        # the KAM's scope no longer unlocks a creator's analysis
        import gating
        portal.unlock_begin(True, scope=frozenset({self.u_lead["code_id"]}))
        try:
            self.assertFalse(gating.unlocked(portal.user_by_email(KAM)["code_id"], "HV-MD-004"))
        finally:
            portal.unlock_begin(False)


if __name__ == "__main__":
    unittest.main(verbosity=1)
