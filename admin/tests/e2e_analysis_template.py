"""The full-analysis template (owner, 2026-10-15): every profile-analysis page previews the FULL analysis
with sample data. The endpoint needs a signed-in viewer, fills every section the creator page draws, uses
only the dummy pictures in assets/sample/, and reads nothing from any creator.

    python3 admin/tests/e2e_analysis_template.py
"""
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import analysis, db, mailer, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EVERY = [k for k, _ in analysis.OVERVIEW if k not in ("code", "handle", "source", "paid_post_performance")] + \
    ["audience", "audience_likers", "growth", "top_posts", "sponsored_posts", "recent_posts", "brands", "hashtags",
     "creator_interests", "content_languages", "fake_followers_dist", "er_dist", "bio", "location", "photo_url",
     "followers_change_pct", "avg_likes_change_pct", "posts_per_week", "last_post"]


class Template(unittest.TestCase):
    signup = base.Portal.signup

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        mailer.CAPTURE = True
        views.set_base("")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def test_every_section_filled_with_dummy_pictures(self):
        self.assertEqual(base.Client(self.base).get("/api/analysis/template")[0], 401)
        c, _ = self.signup("t1@glowderma.com")
        s, d, _ = c.get("/api/analysis/template")
        self.assertEqual(s, 200, d)
        self.assertTrue(d["sample"] and d["template"])
        self.assertEqual(d["creator"]["photo_url"], "/assets/sample/profile.jpg")
        self.assertEqual(d["platforms"], ["Instagram", "TikTok"])
        for plat, a in d["analyses"].items():
            missing = [k for k in EVERY if a.get(k) in (None, [], {}, "")]
            self.assertEqual(missing, [], plat)
            for sec in analysis.AUDIENCE_SECTIONS + ["ages_female", "ages_male"]:
                self.assertTrue(a["audience"].get(sec) and a["audience_likers"].get(sec), (plat, sec))
            pics = [p["thumb"] for k in ("top_posts", "sponsored_posts", "recent_posts") for p in a[k]]
            self.assertTrue(pics and all(x.startswith("/assets/sample/") for x in pics), pics)
            logos = [b["logo"] for b in a["brands"]]
            self.assertTrue(len(logos) >= 6 and all(x.startswith("/assets/clients/") for x in logos), logos)
            names = {b["name"] for b in a["brands"]}
            self.assertTrue(all(p["brand"] in names for p in a["sponsored_posts"]))        # every sponsored badge has a logo
            pics += logos
            for x in pics + [a["photo_url"]]:
                self.assertTrue((ROOT / x.lstrip("/")).is_file(), x)                  # every picture exists
            self.assertTrue(all(p["url"] == "#" for k in ("top_posts", "sponsored_posts", "recent_posts") for p in a[k]))
        txt = json.dumps(d).lower()
        for w in ("http", "instagram.com", "tiktok.com", "media:", "hv-"):
            self.assertNotIn(w, txt, w)                                               # nothing real, no link out


if __name__ == "__main__":
    unittest.main(verbosity=2)
