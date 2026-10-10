"""The admin Reference page: admins only, read only, public-safe data, live roster tab.

Same harness as e2e_portal.py (a throwaway copy of admin/*.py and admin/reference/, an empty
database, captured mail), so it never touches catalogue.db or the network.

    python3 admin/tests/test_reference.py
"""
import json
import re
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402  (copies admin/*.py and admin/reference/ to a temp dir)
from e2e_portal import Client  # noqa: E402

import auth, benchmarks, db, gemini, guard, mailer, reference_view, roi, server, team, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

TABS = ("market", "bench", "structure", "roster", "sources")
TIERS = ("nano", "micro", "mid", "macro", "mega")
# names that were in the research notes and must not be in the shipped data
NAMES = ("Al-Sayeri", "Aleen", "Joud", "Habshi", "Basil", "Saji")
# creators in the throwaway database: neither names nor handles may reach the page
CREATOR_WORDS = ("Noha Magdy", "Sara Ali", "Khalid R", "Lina H", "Omar T", "noha", "khalid")


def peers(n, platform="Instagram", followers=42000):
    """n synthetic analyses for one platform and size: enough to clear the 30-peer bar."""
    return [(platform, {"followers": followers + i, "er": 2.0 + i / 20.0, "avg_reel_plays": (followers + i) * 0.1,
                        "median_likes": 600 + i, "median_comments": 30}) for i in range(n)]


class Reference(unittest.TestCase):
    signup = base.Portal.signup

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        mailer.CAPTURE = True
        gemini.STUB = base.stub
        views.set_base("")
        cls.kam_pw = team.invite("kam@hellovoice.co.uk", "A KAM", "kam")
        cls.viewer_pw = team.invite("view@hellovoice.co.uk", "A viewer", "viewer")
        cls.admin_pw = team.invite("adm@hellovoice.co.uk", "An admin", "admin")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        benchmarks.SOURCE = None
        benchmarks.invalidate()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()
        benchmarks.SOURCE = None
        benchmarks.invalidate()

    def login(self, email, pw):
        c = Client(self.base)
        s, _, _ = c.req("POST", "/login", form={"email": email, "password": pw})
        self.assertEqual(s, 303)
        return c

    def owner(self):
        return self.login("boss@hellovoice.co.uk", "correct-horse-battery")

    # --------------------------------------------------------------- the data --
    def test_01_datasets_load_with_the_expected_structure(self):
        m = reference_view.load("market")
        for mk, cur in (("KSA", "SAR"), ("UAE", "AED"), ("Egypt", "EGP")):
            self.assertEqual(m["markets"][mk]["currency"], cur)
            self.assertEqual(set(m["markets"][mk]["platforms"]), {"instagram", "tiktok", "snapchat", "youtube"})
            for plat in m["markets"][mk]["platforms"].values():
                self.assertEqual(set(plat["tiers"]), set(TIERS))
                for c in plat["tiers"].values():
                    for k in ("low", "average", "cap"):
                        self.assertIn(cur, c[k])
                        self.assertIn("USD", c[k])
                    self.assertIn(c["confidence"], ("high", "medium", "low"))
                    self.assertIsInstance(c["n_independent_sources"], int)
                    self.assertIsInstance(c["sources"], list)
                    self.assertIn("is_extrapolation", c)
                    self.assertLessEqual(c["low"][cur], c["average"][cur])
                    self.assertLessEqual(c["average"][cur], c["cap"][cur])
        self.assertEqual(m["reference"]["updated"], "2026-10-10")

        b = reference_view.load("bench")
        for mk in ("KSA", "UAE", "Egypt"):
            for pk in ("instagram_reels", "tiktok", "snapchat", "youtube_shorts"):
                for t in TIERS:
                    cell = b["markets"][mk][pk][t]
                    for metric in ("view_rate", "eng_rate", "price_per_post_usd", "cpm_usd", "cpe_usd", "cpc_usd"):
                        self.assertIn(cell[metric]["kind"], ("published_vendor", "published_global_proxy", "extrapolation", "no_public_data"))
        self.assertNotIn("derived_checks", b)          # HelloVoice rate-card arithmetic stays out of the public repo

        c = reference_view.load("structure")
        self.assertEqual([o["id"] for o in c["objectives"]], ["awareness", "engagement", "traffic"])
        for o in c["objectives"]:
            self.assertEqual(sum(o["shape_pct"].values()), 100)
            self.assertLess(o["creators"][0], o["creators"][1])
        self.assertEqual(len(c["findings"]), 8)

        s = reference_view.load("sources")["sources"]
        ids = [x["id"] for x in s]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sum(1 for x in s if x["set"] == "campaign_structure"), 33)
        for x in s:
            self.assertTrue(x["title"] and (x["url"].startswith("http") or x["url"] == ""), x["id"])
        # every source a figure cites exists in the list
        cited = set()
        for name in ("market", "bench", "structure"):
            d = dict(reference_view.load(name))
            d.pop("reference", None)
            cited |= set(re.findall(r"\b(CS\d+|[ST]\d+)\b", json.dumps(d)))
        self.assertFalse(cited - set(ids), sorted(cited - set(ids)))

    def test_02_shipped_data_names_no_creators_and_holds_no_client_data(self):
        text = "".join((reference_view.DIR / f).read_text(encoding="utf-8") for f in reference_view.FILES.values())
        for w in NAMES:
            self.assertNotIn(w, text)
        for w in ("catalogue.db", "HV-MI-", "@gmail", "hellovoice.co.uk/admin"):
            self.assertNotIn(w, text)

    # ------------------------------------------------------------ the access --
    def test_10_owner_and_admin_open_every_tab(self):
        for c in (self.owner(), self.login("adm@hellovoice.co.uk", self.admin_pw)):
            for tab in TABS:
                s, body, _ = c.get("/reference?tab=" + tab)
                self.assertEqual(s, 200, tab)
                self.assertIn("Reference only. Vendor and published figures are estimates, not verified.", body)
                self.assertIn("The calculator uses only measured data (our roster, tracked posts) and the recommended structure.", body)
            s, body, _ = c.get("/reference")
            self.assertEqual(s, 200)
            self.assertIn("Market prices", body)

    def test_11_kam_viewer_anonymous_and_clients_get_no_page(self):
        for email, pw in (("kam@hellovoice.co.uk", self.kam_pw), ("view@hellovoice.co.uk", self.viewer_pw)):
            c = self.login(email, pw)
            s, body, _ = c.get("/reference")
            self.assertEqual(s, 403, email)
            self.assertNotIn("Reference only", body)
            s, body, _ = c.get("/reference?tab=sources")
            self.assertEqual(s, 403)
            # and the nav does not offer it
            s, home, _ = c.get("/analytics")
            self.assertNotIn("/reference", home)
        anon = Client(self.base)
        s, body, r = anon.get("/reference")
        self.assertIn(s, (302, 303, 401))
        self.assertNotIn("Reference only", str(body))
        # a signed-in portal client (a different cookie) is not an admin
        client, _ = self.signup("ali@pfizer.com")
        s, body, _ = client.get("/reference")
        self.assertIn(s, (302, 303, 401, 403))
        self.assertNotIn("Reference only", str(body))

    def test_12_page_is_read_only(self):
        c = self.owner()
        for tab in TABS:
            s, body, _ = c.get("/reference?tab=" + tab)
            content = body.split('<main class="page" id="main">', 1)[1].split("</main>", 1)[0]
            self.assertNotRegex(content.lower(), r"method=['\"]post['\"]", tab)
        before = db.setting("roi_shapes")
        s, _, _ = c.req("POST", "/reference", form={"tab": "market", "roi_shapes": "x"})
        self.assertNotEqual(s, 200)
        self.assertEqual(db.setting("roi_shapes"), before)

    # ---------------------------------------------------------------- the tabs --
    def test_20_market_filters_and_sources_open(self):
        c = self.owner()
        s, body, _ = c.get("/reference?tab=market&market=UAE&platform=tiktok")
        self.assertEqual(s, 200)
        self.assertIn("AED", body)
        self.assertIn("United Arab Emirates, TikTok", body)
        self.assertIn("Extrapolation", body)
        self.assertIn("reference?tab=sources&amp;q=T4", body)
        s, body, _ = c.get("/reference?tab=market&market=Egypt&platform=instagram")
        self.assertIn("EGP", body)
        s, body, _ = c.get("/reference?tab=market&market=Mars&platform=nope")          # unknown filters fall back
        self.assertEqual(s, 200)
        self.assertIn("Saudi Arabia, Instagram", body)

    def test_21_benchmarks_show_kind_confidence_and_sources(self):
        c = self.owner()
        s, body, _ = c.get("/reference?tab=bench&market=KSA&platform=instagram")
        self.assertEqual(s, 200)
        for word in ("Proxy", "Published", "No public data", "Confidence", "reference?tab=sources&amp;q=S9"):
            self.assertIn(word, body)
        s, body, _ = c.get("/reference?tab=bench&market=Egypt&platform=snapchat")
        self.assertEqual(s, 200)
        self.assertIn("No public data", body)

    def test_22_structure_marks_values_in_use_and_shows_the_live_setting(self):
        c = self.owner()
        s, body, _ = c.get("/reference?tab=structure")
        self.assertEqual(s, 200)
        self.assertIn("In use by the ROI calculator", body)
        self.assertNotIn("edited in Settings", body)
        db.set_setting("roi_shapes", {"awareness": {"macro": 20, "mid": 20, "micro": 40, "nano": 20}})
        db.set_setting("roi_count_ranges", {"awareness": [7, 9]})
        try:
            s, body, _ = c.get("/reference?tab=structure")
            self.assertEqual(s, 200)
            self.assertIn("edited in Settings", body)
            self.assertIn("<b>7 to 9</b>", body)
            self.assertIn("<b>20%</b>", body)
            self.assertEqual(roi.shapes()["awareness"]["macro"], 20.0)
        finally:
            db.set_setting("roi_shapes", None)
            db.set_setting("roi_count_ranges", None)

    def test_23_roster_tab_is_live_flags_30_peers_and_names_nobody(self):
        c = self.owner()
        with db.connect() as conn:
            n_settings = conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
            n_tables = conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0]
        s, body, _ = c.get("/reference?tab=roster")
        self.assertEqual(s, 200)
        self.assertIn("No analyses yet", body)                           # throwaway DB holds none
        benchmarks.SOURCE = lambda: peers(35) + peers(12, "TikTok", 250000)
        benchmarks.invalidate()
        s, body, _ = c.get("/reference?tab=roster")
        self.assertEqual(s, 200)
        self.assertIn("Instagram", body)
        self.assertIn("TikTok", body)
        self.assertIn("Used by the calculator", body)                    # Instagram micro: 35 peers
        self.assertIn("<td>35</td>", body)
        self.assertIn("<td>12</td>", body)
        self.assertIn("fewer than 30 creators", body)                    # TikTok mid: 12 peers
        for w in CREATOR_WORDS:
            self.assertNotIn(w, body)
        with db.connect() as conn:                                       # nothing was persisted
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0], n_settings)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0], n_tables)

    def test_24_sources_search(self):
        c = self.owner()
        s, body, _ = c.get("/reference?tab=sources&q=S9")
        self.assertIn("Modash", body)
        self.assertNotIn("Socialinsider, Instagram benchmarks", body)    # exact id, not S9x
        s, body, _ = c.get("/reference?tab=sources&q=yamammi")
        self.assertIn("T4", body)
        self.assertIn("350 signed contracts", body)
        s, body, _ = c.get("/reference?tab=sources&q=OpenSponsorship&set=campaign_structure")
        self.assertIn("CS1", body)
        s, body, _ = c.get("/reference?tab=sources&q=zzzznothing")
        self.assertIn("No source matches", body)
        s, body, _ = c.get("/reference?tab=sources&q=%3Cscript%3Ealert(1)%3C/script%3E")
        self.assertNotIn("<script>alert(1)", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
