"""Campaign brief on the board card (items 211-213, owner 2026-10-21): every shortlister question on the
card, Helvi's data-based suggestions, planned targets with their sources, one Save that writes all or
nothing, the brief pushed to the campaign's selections, and words only for KAMs and clients.

    python3 admin/tests/test_cbrief.py
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_board as tb  # noqa: E402
from test_board import base, db  # noqa: E402

import cbrief, history, plans  # noqa: E402


class CampaignBrief(tb.Board):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        tb.Board.ready = False                        # the board's setUp seeds its world on tb.Board
        tb.Board.base = cls.base

    def tok(self, kid):
        return db.campaign(kid)["token"]

    def test_10_staff_open_every_question_with_suggestions_and_targets(self):
        s, b, _ = self.boss.get("/api/board/brief?t=" + self.tok(self.k_short))
        self.assertEqual(s, 200, b)
        ids = [q["id"] for g in b["questions"] for q in g["items"]]
        for qid in ("goal", "platforms", "market", "category", "mix", "creator_size", "count", "deliverable", "timing",
                    "gender", "age", "creator_type", "product", "claim", "licence", "aud_city", "content_lang", "collab", "tone"):
            self.assertIn(qid, ids)
        self.assertNotIn("budget", ids)                          # the card never talks prices
        self.assertTrue(all(q["options"] for g in b["questions"] for q in g["items"] if q["type"] != "text"))
        self.assertIn("count", b["suggest"])
        self.assertTrue(b["suggest"]["count"]["why"])
        self.assertIn("posts", b["plan"]["why"])

    def test_11_targets_follow_the_planner_and_the_share_save_lift(self):
        sels = [db.selection(self.s_full)]
        ans = {"goal": ["engagement"], "platforms": ["Instagram", "TikTok"]}
        old = plans.share_save_uplift
        try:
            plans.share_save_uplift = lambda fresh=False: {p: 1.0 for p in plans.PLATFORMS}
            one = cbrief.targets(sels, ans)
            plans.share_save_uplift = lambda fresh=False: {p: 2.0 for p in plans.PLATFORMS}
            two = cbrief.targets(sels, ans)
        finally:
            plans.share_save_uplift = old
        self.assertGreater(one["targets"]["posts"], 0)
        self.assertEqual(one["targets"]["views"], two["targets"]["views"])
        self.assertAlmostEqual(two["targets"]["engagement"] / float(one["targets"]["engagement"]), 2.0, delta=0.05)
        self.assertNotIn("clicks", one["targets"])               # clicks only for traffic
        self.assertIn("clicks", cbrief.targets(sels, dict(ans, goal=["traffic"]))["targets"])
        self.assertLessEqual(one["targets"]["views"], one["likely"]["views"])   # the target is the safe end
        self.assertIn("shares + saves", two["why"]["engagement"])

    def test_12_one_save_writes_everything_and_pushes_to_selections(self):
        tok = self.tok(self.k_short)
        n_hist = len(history.list_for("campaign", self.k_short)) if hasattr(history, "list_for") else None
        ans = {"goal": ["awareness", "traffic"], "platforms": ["Instagram"], "market": ["SA"], "category": ["skincare"],
               "mix": "micro", "gender": "Women", "tone": ["educational"]}
        s, b, _ = self.boss.post("/api/board/save", {"t": tok, "name": "Poly shortlist two", "next": "Send the quote",
                                                     "targets": {"views": 50000, "posts": 4}, "typed": ["views"],
                                                     "brief": {"answers": ans}})
        self.assertEqual(s, 200, b)
        self.assertIn("drives its selection", b["message"])
        k = db.campaign(self.k_short)
        self.assertEqual((k["name"], k["next_step"], k["objective"]), ("Poly shortlist two", "Send the quote", "awareness+traffic"))
        self.assertEqual(db.campaign_targets(k), {"views": 50000, "posts": 4})
        st = json.loads(k["brief"])
        self.assertEqual(st["typed"], ["views"])
        self.assertEqual(st["answers"]["tone"], ["educational"])
        sel = db.selection(self.s_full)
        self.assertEqual(sel["objective"], "Awareness+Traffic")
        with db.connect() as conn:
            r = conn.execute("SELECT source, answers FROM briefs WHERE selection_id = ? ORDER BY id DESC LIMIT 1", (self.s_full,)).fetchone()
        self.assertEqual(r["source"], "board")
        self.assertEqual(json.loads(r["answers"])["mix"], "micro")
        if n_hist is not None:
            self.assertEqual(len(history.list_for("campaign", self.k_short)), n_hist + 1)   # one entry, not one per section
        s, b, _ = self.boss.get("/api/board/brief?t=" + tok)
        self.assertEqual(b["answers"]["goal"], ["awareness", "traffic"])
        self.assertFalse(b["meta"]["seeded"])

    def test_13_a_bad_field_saves_nothing(self):
        tok = self.tok(self.k_draft)
        before = dict(db.campaign(self.k_draft))
        s, b, _ = self.boss.post("/api/board/save", {"t": tok, "name": "Changed name", "ends": "not-a-date",
                                                     "brief": {"answers": {"goal": ["awareness"]}}})
        self.assertEqual(s, 400, b)
        after = db.campaign(self.k_draft)
        self.assertEqual((after["name"], after["brief"]), (before["name"], before["brief"]))
        s, b, _ = self.boss.post("/api/board/save", {"t": tok, "brief": {"answers": {"platforms": ["Instagram"]}}})
        self.assertEqual((s, b.get("field")), (400, "goal"))
        s, b, _ = self.boss.post("/api/board/save", {"t": tok, "kam": "nobody@nowhere.com", "name": "Changed name"})
        self.assertEqual((s, b.get("field")), (400, "kam"))
        self.assertEqual(db.campaign(self.k_draft)["name"], before["name"])

    def test_14_missing_core_answers_keep_the_selections_as_they_are(self):
        tok = self.tok(self.k_rival)
        s, b, _ = self.boss.post("/api/board/save", {"t": tok, "brief": {"answers": {"goal": ["engagement"], "mix": "big"}}})
        self.assertEqual(s, 200, b)
        self.assertIn("Add the platforms and countries and space", b["message"])
        with db.connect() as conn:
            self.assertIsNone(conn.execute("SELECT id FROM briefs WHERE selection_id = ? AND source = 'board'", (self.s_rival,)).fetchone())

    def test_15_clients_read_words_and_cannot_save(self):
        tok = self.tok(self.k_short)
        s, b, _ = self.lead.get("/api/board/brief?t=" + tok)
        self.assertEqual(s, 200, b)
        self.assertNotIn("suggest", b)
        self.assertNotIn("plan", b)
        self.assertTrue(all("answer" in r for g in b["answers"] for r in g["items"]))
        self.assertEqual(self.lead.post("/api/board/save", {"t": tok, "name": "Mine now"})[0], 403)
        self.assertEqual(self.lead.post("/api/board/plan", {"t": tok, "answers": {}})[0], 403)
        self.assertEqual(self.rival.get("/api/board/brief?t=" + tok)[0], 404)

    def test_16_nothing_from_an_analysis_reaches_the_kam(self):
        s, b, _ = self.kam.get("/api/board/brief?t=" + self.tok(self.k_short))
        self.assertEqual(s, 200, b)
        text = json.dumps(b)
        for code in json.loads(db.selection(self.s_full)["codes"]):
            self.assertNotIn(code, text)                        # aggregate words, never a creator
        for word in ('"score"', "fake_followers", "avg_views", "followers_count"):
            self.assertNotIn(word, text)

    def test_18_own_typical_views_beat_the_benchmark(self):
        sels = [db.selection(self.s_full)]
        code = json.loads(sels[0]["codes"])[0]
        old = cbrief._summaries
        try:
            cbrief._summaries = lambda: {code: [{"platform": "Instagram", "views": 100000, "likes": 4000, "comments": 1000}]}
            got = cbrief.targets(sels, {"goal": ["awareness"], "platforms": ["Instagram"]})
        finally:
            cbrief._summaries = old
        base_ = cbrief.targets(sels, {"goal": ["awareness"], "platforms": ["Instagram"]})
        self.assertGreater(got["targets"]["views"], base_["targets"]["views"] + 70000)     # 80% of 100,000 joins the plan
        self.assertIn("1 from their own recent posts", got["why"]["views"])
        self.assertNotIn("100,000", json.dumps(got["why"]))                               # no creator figure in the words

    def test_17_plan_recalculates_unsaved_answers(self):
        s, b, _ = self.boss.post("/api/board/plan", {"t": self.tok(self.k_short), "answers": {"goal": ["traffic"], "platforms": ["Instagram"]}})
        self.assertEqual(s, 200, b)
        self.assertIn("clicks", b["headline"])


for _n in [n for n in dir(tb.Board) if n.startswith("test_")]:
    setattr(CampaignBrief, _n, None)                  # the board's own tests run in test_board.py


if __name__ == "__main__":
    unittest.main()
