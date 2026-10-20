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
        self.assertEqual((s, b["role"], b["can_move"]), (200, "kam", True))          # item 194: her drafts
        self.assertEqual(b["locked_stages"], ["live", "completed"])
        names = {c["name"] for c in b["campaigns"]}
        self.assertIn("Poly draft", names)
        self.assertNotIn("Rival draft", names)                        # another KAM's client
        s, b, _ = self.lead.get("/api/board")
        self.assertEqual((s, b["role"], b["can_move"]), (200, "client", True))       # item 194: their team's drafts
        names = {c["name"] for c in b["campaigns"]}
        self.assertTrue({"Poly draft", "Poly shortlist", "Poly live", "Poly done"} <= names)   # drafts included
        self.assertNotIn("Rival draft", names)
        c = next(x for x in b["campaigns"] if x["name"] == "Poly shortlist")
        self.assertEqual(c["selections"][0]["name"], "Glow list")
        self.assertNotIn("email", c["kam"] or {})                      # the KAM's name only; the email stays with the team
        self.assertNotIn("staged", c)
        self.assertEqual(set(c["counts"]), {"creators", "approved", "review"})
        self.assertEqual(c["counts"]["creators"], 2)
        self.assertEqual(sorted(c["moves"]), ["approved", "draft", "review"])
        live = next(x for x in b["campaigns"] if x["name"] == "Poly live")
        self.assertEqual((live["moves"], set(live["numbers"] or {}) >= {"views", "engagement", "er"}), ([], True))
        blob = json.dumps(b)
        for word in ("score", "cost", "analysis"):
            self.assertNotIn('"%s' % word, blob)
        self.assertEqual(base.Client(self.base).get("/api/board")[0], 401)

    # ---------------------------------------------------------- admin-only moves
    def test_03_planning_moves_for_all_live_for_admins(self):
        tok = db.campaign(self.k_draft)["token"]
        # Item 194: a client and a KAM move their own drafts between the planning columns...
        for who, to in ((self.lead, "review"), (self.kam, "shortlisting")):
            s, b, _ = who.post("/api/board/stage", {"t": tok, "to": to})
            self.assertEqual((s, b.get("stage")), (200, to), b)
        # ...never to Live or Completed, never Live / Unlive, and never a live campaign out of Live
        for who in (self.lead, self.kam):
            for to in ("live", "completed"):
                s, b, _ = who.post("/api/board/stage", {"t": tok, "to": to})
                self.assertEqual(s, 403, b)
            s, b, _ = who.post("/api/board/live", {"t": tok, "on": True})
            self.assertEqual(s, 403, b)
            s, b, _ = who.post("/api/board/stage", {"t": db.campaign(self.k_live)["token"], "to": "approved"})
            self.assertEqual(s, 403, b)
        self.assertEqual(db.campaign(self.k_live)["status"], "live")
        # a colleague's campaign shared to another client is not theirs to move
        s, b, _ = self.rival.post("/api/board/stage", {"t": db.campaign(self.k_rival)["token"], "to": "review"})
        self.assertEqual(s, 200, b)                                    # their own
        s, b, _ = self.lead.post("/api/board/stage", {"t": db.campaign(self.k_rival)["token"], "to": "review"})
        self.assertEqual(s, 404)
        with db.connect() as conn:
            conn.execute("UPDATE campaigns SET stage = NULL WHERE id IN (?, ?)", (self.k_draft, self.k_rival))
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
        def bells():
            with db.connect() as conn:
                return conn.execute("SELECT kind FROM notifications WHERE user_id = ? AND ref LIKE ?",
                                    (self.u_lead["id"], "%%:%d" % self.k_draft)).fetchall()
        self.assertEqual([r[0] for r in bells()], ["camp_live"])          # Live: the client's bell (and push) ring
        s, b, _ = self.boss.post("/api/board/live", {"t": tok, "on": False})
        self.assertEqual(len(bells()), 1)                                  # Unlive: silent
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
        # a client never gets a full analysis, even one HelloVoice granted or published (owner, 2026-10-20)
        import gating
        with db.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO analysis_grants (code_id, code, granted_at, granted_by) VALUES (?,?,?,?)",
                         (self.u_lead["code_id"], "HV-MI-001", 1, "test"))
        self.assertFalse(gating.unlocked(self.u_lead["code_id"], "HV-MI-001"))
        self.assertEqual(gating.unlocked_set(self.u_lead["code_id"], ["HV-MI-001", "HV-MI-002"]), set())
        s, b, _ = self.lead.get("/api/creator?c=HV-MI-001")
        self.assertNotEqual(b["gate"]["state"], "unlocked")
        # the KAM's scope no longer unlocks a creator's analysis
        portal.unlock_begin(True, scope=frozenset({self.u_lead["code_id"]}))
        try:
            self.assertFalse(gating.unlocked(portal.user_by_email(KAM)["code_id"], "HV-MD-004"))
        finally:
            portal.unlock_begin(False)

    # ----------------------------------------------------- item 194: selections on the board
    def test_08_selection_columns_and_moves(self):
        sel = db.selection(self.s_more)
        tok = sel["token"]
        self.assertEqual(board.selection_stage(sel, lifecycle.chip(sel)["key"]), "shortlisting")
        self.assertEqual(board.selection_stage(db.selection(self.s_empty), "draft"), "draft")
        # the account page carries the column and where it may go
        s, b, _ = self.lead.get("/api/account")
        row = next(x for x in b["selections"] if x["token"] == tok)
        self.assertEqual((row["stage"], sorted(row["moves"])), ("shortlisting", ["approved", "draft", "review"]), row)
        # the owner's team drags it; a rival client and a stranger cannot
        s, b, _ = self.mate.post("/api/board/selection-stage", {"s": tok, "to": "review"})
        self.assertEqual((s, b.get("stage")), (200, "review"), b)
        self.assertEqual(db.selection(self.s_more)["stage"], "review")
        self.assertEqual(self.rival.post("/api/board/selection-stage", {"s": tok, "to": "draft"})[0], 403)
        self.assertEqual(base.Client(self.base).post("/api/board/selection-stage", {"s": tok, "to": "draft"})[0], 401)
        # never by a drag into Live or Completed
        for to in ("live", "completed"):
            self.assertEqual(self.lead.post("/api/board/selection-stage", {"s": tok, "to": to})[0], 403)
        # the KAM for her client, an admin for anyone
        self.assertEqual(self.kam.post("/api/board/selection-stage", {"s": tok, "to": "approved"})[0], 200)
        self.assertEqual(self.boss.post("/api/board/selection-stage", {"s": db.selection(self.s_rival)["token"], "to": "review"})[0], 200)
        self.assertEqual(self.kam.post("/api/board/selection-stage", {"s": db.selection(self.s_rival)["token"], "to": "draft"})[0], 403)
        # an approved quote decides the column and locks the drag
        sel = db.selection(self.s_more)
        lifecycle.mark_requested(sel, by_name="Lead"); lifecycle.set_ready(sel, "", "", "HV"); lifecycle.approve(sel, None, "Lead")
        self.assertEqual(board.selection_stage(db.selection(self.s_more), lifecycle.chip(db.selection(self.s_more))["key"]), "approved")
        s, b, _ = self.lead.post("/api/board/selection-stage", {"s": tok, "to": "draft"})
        self.assertEqual(s, 403, b)
        s, b, _ = self.lead.get("/api/account")
        row = next(x for x in b["selections"] if x["token"] == tok)
        self.assertEqual((row["stage"], row["moves"]), ("approved", []))
        with db.connect() as conn:
            conn.execute("DELETE FROM selection_quote WHERE selection_id = ?", (self.s_more,))
            conn.execute("UPDATE selections SET stage = NULL WHERE id IN (?, ?)", (self.s_more, self.s_rival))

    # ------------------------------------------- item 197/204/206: edits on the card
    def test_09_edit_from_the_card(self):
        k = db.campaign(self.k_short)
        tok = k["token"]
        # clients read; their card has no edit block
        s, b, _ = self.lead.get("/api/board")
        c = next(x for x in b["campaigns"] if x["token"] == tok)
        self.assertNotIn("can_edit", c)
        self.assertEqual(c["briefs"][0]["selection_name"], "Glow list")
        self.assertEqual(self.lead.post("/api/board/edit", {"t": tok, "name": "Hacked"})[0], 403)
        # the KAM edits her client's campaign
        s, b, _ = self.kam.post("/api/board/edit", {"t": tok, "name": "Poly shortlist v2", "client": "Polyco KSA",
                                                     "starts": "2026-11-01", "ends": "2026-11-30"})
        self.assertEqual(s, 200, b)
        k = db.campaign(self.k_short)
        self.assertEqual((k["name"], k["client"]), ("Poly shortlist v2", "Polyco KSA"))
        self.assertEqual(k["ends_at"] - k["starts_at"], 30 * 86400 - 1)
        self.assertEqual(self.kam.post("/api/board/edit", {"t": tok, "starts": "2026-12-01", "ends": "2026-11-01"})[0], 400)
        self.assertEqual(self.kam.post("/api/board/edit", {"t": tok, "name": "x"})[0], 400)
        s, b, _ = self.boss.post("/api/board/edit", {"t": tok, "objective": "awareness", "targets": {"views": "250000", "er": "3.5", "posts": ""}})
        self.assertEqual(s, 200, b)
        self.assertEqual(db.campaign_targets(db.campaign(self.k_short)), {"views": 250000, "er": 3.5})
        self.assertEqual(self.boss.post("/api/board/edit", {"t": tok, "objective": "custom"})[0], 400)
        # admin card carries the edit block and the KAM list
        s, b, _ = self.boss.get("/api/board")
        c = next(x for x in b["campaigns"] if x["token"] == tok)
        self.assertEqual((c["can_edit"], c["edit"]["objective"]), (True, "awareness"))
        self.assertTrue(any(x["email"] == KAM for x in b["kams"]))
        # selections: attachable lists the client's others, detach takes one out (the first one moves up)
        s, b, _ = self.boss.get("/api/board/attachable?t=" + tok)
        self.assertEqual(s, 200, b)
        names = {x["name"] for x in b["selections"]}
        self.assertNotIn("Rival list", names)
        before = board.selection_ids(db.campaign(self.k_short))
        first = db.selection(before[0])
        self.assertEqual(self.lead.post("/api/board/detach", {"t": tok, "s": first["token"]})[0], 403)
        s, b, _ = self.kam.post("/api/board/detach", {"t": tok, "s": first["token"]})
        self.assertEqual(s, 200, b)
        after = board.selection_ids(db.campaign(self.k_short))
        self.assertEqual(after, before[1:])
        self.assertEqual(db.campaign(self.k_short)["selection_id"], before[1] if len(before) > 1 else None)
        # logo: images only
        self.assertEqual(self.boss.post("/api/board/logo", {"t": tok, "data": "data:text/plain;base64,aGVsbG8="})[0], 400)
        png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        s, b, _ = self.boss.post("/api/board/logo", {"t": tok, "data": png})
        self.assertEqual(s, 200, b)
        self.assertTrue(db.campaign_logos(db.campaign(self.k_short))[0].startswith("upload/"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
