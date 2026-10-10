"""TikTok analytics at a 100-post sample (fix batch 6, Bido 2026-10-10): the job asks for 100 posts,
a creator with fewer is covered whole, and the sample's MEDIANS are kept (not just averages).

    python3 admin/tests/test_apify_tiktok.py
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="hv-apify-"))
for f in SRC.glob("*.py"):
    shutil.copy(f, TMP / f.name)
sys.path.insert(0, str(TMP))

import apify  # noqa: E402
import db  # noqa: E402


def result(n, base=1000):
    posts = [{"url": "https://t/%d" % i, "publishedAt": "2026-09-%02dT10:00:00Z" % (1 + i % 28), "views": base + i * 10,
              "likes": 50 + i, "comments": 5, "shares": 2, "text": "caption #skincare %d" % i} for i in range(n)]
    views = [p["views"] for p in posts]
    return {"creator": {"handle": "x", "isVerified": False, "bio": "b"},
            "audience": {"followers": 50000, "following": 10, "totalLikes": 1, "videoCount": 400},
            "recentPosts": {"requestedCount": 100, "usedCount": n, "averages": {"views": sum(views) / n, "likes": 80.0, "comments": 5.0, "shares": 2.0},
                            "medians": {}, "engagement": {"ratePercent": 6.0, "basis": "views"}, "posts": posts}}


class Hundred(unittest.TestCase):
    def test_preset_asks_for_100(self):
        self.assertEqual(json.loads(apify.PRESETS["tt_analytics"]["input"].replace("{{handles}}", "a"))["postSampleSize"], 100)

    def test_100_posts_give_medians_and_the_whole_series(self):
        m = apify.derive_tiktok_analytics(result(100))
        self.assertEqual(m["sample_posts"], 100)
        self.assertEqual(m["median_views"], round((1000 + 49 * 10 + 1000 + 50 * 10) / 2.0))
        self.assertEqual(len(m["views_series"]), 100)
        self.assertLessEqual(m["views_p25"], m["median_views"])
        self.assertGreaterEqual(m["views_p75"], m["median_views"])
        self.assertIsNotNone(m["median_er_on_views"])

    def test_a_creator_with_fewer_posts_is_covered_whole(self):
        m = apify.derive_tiktok_analytics(result(7))
        self.assertEqual(m["sample_posts"], 7)
        self.assertEqual(len(m["views_series"]), 7)

    def test_the_raw_record_keeps_every_post_without_caption_text(self):
        slim = apify.trim_posts(result(100))
        posts = slim["recentPosts"]["posts"]
        self.assertEqual(len(posts), 100)
        self.assertNotIn("text", posts[0])
        self.assertLess(len(json.dumps(slim)), 60000)

    def test_saved_jobs_with_20_posts_move_to_100(self):
        db.init()
        apify.init()
        with db.connect() as conn:
            conn.execute("INSERT INTO api_jobs (name,actor,kind,platform,source,input,created_at) VALUES (?,?,?,?,?,?,?)",
                         ("old", "maximedupre/tiktok-creator-analytics", "analysis", "TikTok", "all",
                          '{"target": "handles", "creatorHandles": "{{handles}}", "postSampleSize": 20}', db.now()))
        apify.init()
        with db.connect() as conn:
            row = conn.execute("SELECT input FROM api_jobs WHERE name = 'old'").fetchone()
        self.assertEqual(json.loads(row["input"])["postSampleSize"], 100)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
