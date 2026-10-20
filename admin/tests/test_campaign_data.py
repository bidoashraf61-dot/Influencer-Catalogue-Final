"""Campaign data round (items 215-217, owner 2026-10-21):

215  a selection a campaign holds cannot be deleted by a client, and a campaign whose creators no selection
     holds gets one made from them (board.selection_from_campaign), both in History;
216  a post on a platform the creator has no profile for adds that profile (postprofiles), from the stored
     capture or the post link, never for the demo campaign or another creator's link, undoable;
217  on the Goals tab a creator's results count on every platform they posted on, against the target of the
     platform they were booked for, with the per-platform breakdown.

    python3 admin/tests/test_campaign_data.py
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

import board, db, gemini, guard, history, mailer, metrics, portal, postprofiles, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

DAY = 86400


def _profiles(code):
    return {p["platform"]: p for p in db.split_profiles(db.creator(code)["profiles"])}


class CampaignData(unittest.TestCase):
    signup = base.Portal.signup

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

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()

    # ------------------------------------------------------------------ 215
    def test_215a_client_cannot_delete_a_selection_a_campaign_holds(self):
        lead, _ = self.signup("lead@arcco.com")
        cid = portal.user_by_email("lead@arcco.com")["code_id"]
        held = db.save_selection(None, "Held list", ["HV-MI-001"], {}, None, None, None, cid, origin="client")
        free = db.save_selection(None, "Free list", ["HV-MI-002"], {}, None, None, None, cid, origin="client")
        db.create_campaign("Arc live", client="Arcco", code_id=cid, selection_id=held)
        s, b, _ = lead.post("/api/selection/delete", {"token": db.selection(held)["token"]})
        self.assertEqual((s, b.get("reason"), b.get("campaigns")), (409, "in_campaign", ["Arc live"]), b)
        self.assertIsNone(db.selection(held)["deleted_at"])
        s, b, _ = lead.post("/api/selection/delete", {"token": db.selection(free)["token"]})
        self.assertEqual(s, 200, b)
        self.assertTrue(db.selection(free)["deleted_at"])

    def test_215b_selection_made_from_the_campaigns_creators(self):
        gone = db.save_selection(None, "Placeholder", ["HV-MD-004"], {}, None, None)
        k = db.create_campaign("Iva test", client="Arc", selection_id=gone)
        db.add_campaign_creators(k, ["HV-MI-001", "HV-MI-002", "HV-MD-003"])
        db.client_delete_selection(gone, None)                      # what happened to Ivatherm's selection
        self.assertEqual(board._selections(board.selection_ids(db.campaign(k))), [])
        sid = board.selection_from_campaign(k, "test")
        self.assertIsNotNone(sid)
        kk = db.campaign(k)
        self.assertEqual(kk["selection_id"], sid)
        sel = db.selection(sid)
        self.assertEqual((sel["name"], sorted(json.loads(sel["codes"]))), ("Iva test", ["HV-MD-003", "HV-MI-001", "HV-MI-002"]))
        self.assertEqual([s["id"] for s in board._selections(board.selection_ids(kk))], [sid])
        self.assertIsNone(board.selection_from_campaign(k, "test"))  # nothing left to do
        with db.connect() as conn:
            labels = [r[0] for r in conn.execute("SELECT label FROM history WHERE (entity='campaign' AND key=?) OR (entity='selection' AND key=?)",
                                                 (str(k), str(sid)))]
        self.assertTrue(any("Made a selection" in x for x in labels) and any("Created selection" in x for x in labels), labels)

    def test_215c_a_live_selection_is_linked_beside_not_replaced(self):
        first = db.save_selection(None, "Wave one", ["HV-MI-001"], {}, None, None)
        k = db.create_campaign("Two waves", client="Arc", selection_id=first)
        db.add_campaign_creators(k, ["HV-MI-001", "HV-MI-005"])
        sid = board.selection_from_campaign(k, "test")
        self.assertEqual(db.campaign(k)["selection_id"], first)
        self.assertEqual(board.selection_ids(db.campaign(k)), [first, sid])

    # ------------------------------------------------------------------ 216
    def _post(self, k, code, platform, url, views=1000, likes=50):
        cid_, _ = db.add_content(k, {"code": code, "platform": platform, "url": url, "posted_at": int(time.time()) - 3 * DAY,
                                     "views": views, "likes": likes, "comments": 5, "shares": 2, "saves": 1})
        return cid_

    def test_216a_author_reads_each_platform(self):
        tt = postprofiles.author("TikTok", {"creator": {"username": "dr.test", "followerCount": 94700, "avatarUrl": "https://p/a.jpg", "id": "77"}})
        self.assertEqual((tt["url"], tt["followers"], tt["photo"], tt["id"]), ("https://www.tiktok.com/@dr.test", 94700, "https://p/a.jpg", "77"))
        link = postprofiles.author("TikTok", {}, "https://www.tiktok.com/@only.link/video/123")
        self.assertEqual((link["url"], link["followers"]), ("https://www.tiktok.com/@only.link", None))
        yt = postprofiles.author("YouTube", {"channel_url": "https://www.youtube.com/@user-drTest", "channel": "Dr Test"})
        self.assertEqual(yt["url"], "https://www.youtube.com/@user-drTest")
        self.assertIsNone(postprofiles.author("Facebook", {"author": "None", "authorUrl": "None"}))   # share link: needs a fetch
        fb = postprofiles.author("Facebook", {"authorUrl": "https://www.facebook.com/drtest", "authorName": "Dr Test", "authorId": "9"})
        self.assertEqual((fb["url"], fb["id"]), ("https://www.facebook.com/drtest", "9"))
        pg = postprofiles.author("Facebook", {"facebookUrl": "https://www.facebook.com/share/r/X/", "pageName": "dr.test.page"})
        self.assertEqual(pg["url"], "https://www.facebook.com/dr.test.page")

    def test_216b_gaps_and_fill(self):
        k = db.create_campaign("Jam test", client="Jam")
        db.add_campaign_creators(k, ["HV-MI-002"])
        tt = self._post(k, "HV-MI-002", "TikTok", "https://www.tiktok.com/@sara.tt/video/111")
        self._post(k, "HV-MI-002", "Instagram", "https://www.instagram.com/reel/AAA/")    # has a profile: no gap
        fb = self._post(k, "HV-MI-002", "Facebook", "https://www.facebook.com/share/r/XYZ/")
        with db.connect() as conn:
            conn.execute("INSERT INTO profile_raw (run_id, code, platform, actor, at, data) VALUES (1, ?, 'TikTok', 'x', ?, ?)",
                         ("post:%d" % tt, db.now(), json.dumps({"creator": {"username": "sara.tt", "followerCount": 51000}})))
        demo = db.create_campaign("Demo", client="HelloVoice (demo)")
        self._post(demo, "HV-MI-005", "TikTok", "https://www.tiktok.com/@omar.demo/video/DEMO1")
        g = {(x["code"], x["platform"]): x for x in postprofiles.gaps()}
        self.assertEqual(set(g), {("HV-MI-002", "TikTok"), ("HV-MI-002", "Facebook")})          # demo left out
        self.assertEqual((g[("HV-MI-002", "TikTok")]["source"], g[("HV-MI-002", "TikTok")]["found"]["followers"]), ("capture", 51000))
        self.assertIsNone(g[("HV-MI-002", "Facebook")]["found"])                                  # needs a fetch
        self.assertEqual(postprofiles.fill(list(g.values())), [("HV-MI-002", "TikTok")])
        p = _profiles("HV-MI-002")
        self.assertEqual((p["TikTok"]["url"], p["TikTok"]["followers"]), ("https://www.tiktok.com/@sara.tt", 51000))
        self.assertIn("Instagram", p)                                                             # nothing else lost
        with db.connect() as conn:
            h = conn.execute("SELECT id, label FROM history WHERE entity='creator' AND key='HV-MI-002' ORDER BY id DESC").fetchone()
            snap = conn.execute("SELECT followers FROM profile_snapshots WHERE code='HV-MI-002' AND platform='TikTok'").fetchone()
        self.assertIn("Added TikTok profile", h["label"])
        self.assertEqual(snap[0], 51000)
        self.assertEqual(postprofiles.fill(list(g.values())), [])                                 # second run: nothing
        ok, _msg = history.undo(h["id"])
        self.assertTrue(ok)
        self.assertNotIn("TikTok", _profiles("HV-MI-002"))
        self.assertTrue(fb)

    def test_216c_capture_hook_and_another_creators_link(self):
        import apify
        k = db.create_campaign("Hook test", client="Hooks")
        db.add_campaign_creators(k, ["HV-MI-001", "HV-MD-004"])
        a = self._post(k, "HV-MI-001", "TikTok", "https://www.tiktok.com/@noha.tt/video/222")
        b = self._post(k, "HV-MD-004", "TikTok", "https://www.tiktok.com/@noha.tt/video/333")   # someone else's account
        job = {"platform": "TikTok", "actor": "x/y"}
        run = {"id": 2}
        apify.ingest_posts(run, job, [{"url": "https://www.tiktok.com/@noha.tt/video/222", "playCount": 900,
                                       "creator": {"username": "noha.tt", "followerCount": 12000}}],
                           {"https://www.tiktok.com/@noha.tt/video/222": str(a)})
        self.assertEqual(_profiles("HV-MI-001")["TikTok"]["followers"], 12000)
        apify.ingest_posts(run, job, [{"url": "https://www.tiktok.com/@noha.tt/video/333", "playCount": 50,
                                       "creator": {"username": "noha.tt", "followerCount": 12000}}],
                           {"https://www.tiktok.com/@noha.tt/video/333": str(b)})
        self.assertNotIn("TikTok", _profiles("HV-MD-004"))                                        # link is HV-MI-001's
        db.set_setting("post_profiles_auto", False)
        try:
            self.assertFalse(postprofiles.learn(db.connect().__enter__(), b, "TikTok", {"creator": {"username": "lina.tt"}}))
        finally:
            db.set_setting("post_profiles_auto", True)

    # ------------------------------------------------------------------ 217
    def test_217_results_count_on_every_platform(self):
        k = db.create_campaign("Goals test", client="Goal")
        now = int(time.time())
        db.save_campaign(k, status="live", starts_at=now - 20 * DAY, ends_at=now + 20 * DAY,
                         plan={"platform": "Instagram + TikTok", "platforms": ["Instagram", "TikTok"], "posts": 2,
                               "creator_platforms": {"HV-MI-001": "Instagram", "HV-MD-003": "TikTok"}})
        db.add_campaign_creators(k, ["HV-MI-001", "HV-MD-003"])
        db.set_planned(k, {"HV-MI-001": 1, "HV-MD-003": 1})
        with db.connect() as conn:          # HV-MI-001 also has a TikTok account; the target stays on Instagram
            items = db.split_profiles(db.creator("HV-MI-001")["profiles"]) + [{"platform": "TikTok", "url": "https://www.tiktok.com/@noha2", "followers": 900000}]
            conn.execute("UPDATE creators SET profiles = ? WHERE code = 'HV-MI-001'", (db.join_profiles(items),))
        self._post(k, "HV-MI-001", "Instagram", "https://www.instagram.com/reel/G1/", views=6000)
        self._post(k, "HV-MI-001", "TikTok", "https://www.tiktok.com/@noha2/video/G2", views=5000)
        self._post(k, "HV-MI-001", "YouTube", "https://www.youtube.com/shorts/G3", views=1000)
        camp = db.campaign(k)
        r = metrics.report(camp)
        g = metrics.goals_view(camp, r)
        c = next(x for x in g["creators"] if x["code"] == "HV-MI-001")
        self.assertEqual(c["booked"], ["Instagram"])
        self.assertEqual([p["platform"] for p in c["platforms"]], ["Instagram"])                 # target: Instagram only
        self.assertEqual(c["views"], 12000)
        self.assertEqual(c["views_per_video"], 12000)                                            # 1 booked video, all platforms
        self.assertEqual([(p["platform"], p["booked"], p["views"]) for p in c["by_platform"]],
                         [("Instagram", True, 6000), ("TikTok", False, 5000), ("YouTube", False, 1000)])
        self.assertEqual(c["engagement"], sum(p["engagement"] for p in c["by_platform"]))
        self.assertTrue(any("every platform" in n for n in g["notes"]))
        # engagement = likes + comments + shares + saves
        self.assertEqual(c["by_platform"][0]["engagement"], 50 + 5 + 2 + 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
