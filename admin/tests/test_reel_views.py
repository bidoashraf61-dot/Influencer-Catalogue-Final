"""Reel views from apify/instagram-reel-scraper (2026-10-14): each reel is one result; once the run is
read, every creator's reels are summed up into median / average plays and merged into their post
sample, keeping what the 25-post scan found.

    python3 admin/tests/test_reel_views.py
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="hv-reels-"))
for f in SRC.glob("*.py"):
    shutil.copy(f, TMP / f.name)
sys.path.insert(0, str(TMP))

import apify  # noqa: E402
import db  # noqa: E402
import postscan  # noqa: E402


def reel(owner, plays, i):
    return {"ownerUsername": owner, "videoPlayCount": plays, "videoViewCount": None, "likesCount": plays // 50,
            "commentsCount": 3, "timestamp": "2026-09-%02dT10:00:00.000Z" % (i + 1), "url": "https://www.instagram.com/reel/%s%d/" % (owner, i)}


class Reels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()
        apify.init()
        with db.connect() as conn:
            postscan.init(conn)
            conn.execute("INSERT OR REPLACE INTO post_samples (code, platform, handle, at, run_id, data) VALUES (?,?,?,?,?,?)",
                         ("HV-MI-1", "Instagram", "aa", db.now(), "scan", json.dumps({"median_likes": 40, "hashtags": [["#x", 0.5]], "er": 2.1})))
            cls.job = conn.execute("INSERT INTO api_jobs (name,actor,kind,platform,source,input,created_at) VALUES (?,?,?,?,?,?,?)",
                                   ("r", apify.REEL_ACTOR, "posts", "Instagram", "all", apify.PRESETS["ig_reels"]["input"], db.now())).lastrowid
            cls.run_id = conn.execute("INSERT INTO api_runs (job_id, job_name, trigger, status, handle_map, started_at) VALUES (?,?,?,?,?,?)",
                                   (cls.job, "r", "manual", "RUNNING", json.dumps({"aa": "HV-MI-1", "bb": "HV-MI-2"}), db.now())).lastrowid

    def test_preset_input(self):
        body = apify.render_input(apify.PRESETS["ig_reels"]["input"], ["aa", "bb"])
        self.assertEqual((body["username"], body["resultsLimit"]), (["aa", "bb"], 12))

    def test_rollup_merges_views_and_keeps_the_scan(self):
        run = {"id": self.run_id, "handle_map": json.dumps({"aa": "HV-MI-1", "bb": "HV-MI-2"})}
        job = apify.get_job(self.job)
        items = [reel("aa", p, i) for i, p in enumerate([1000, 2000, 3000, 4000, 50000])] + [reel("bb", 0, 0)]
        apify.ingest(run, job, items[:3])                      # read a page at a time, as refresh_run does
        apify.ingest(run, job, items[3:])
        self.assertEqual(apify.reels_rollup(self.run_id), 1)     # bb had no plays: nothing saved for them
        with db.connect() as conn:
            d = json.loads(conn.execute("SELECT data FROM post_samples WHERE code = 'HV-MI-1'").fetchone()[0])
            none = conn.execute("SELECT 1 FROM post_samples WHERE code = 'HV-MI-2'").fetchone()
        self.assertEqual(d["median_views"], 3000)
        self.assertEqual(d["avg_reel_plays"], 12000)
        self.assertEqual((d["median_likes"], d["er"]), (40, 2.1))   # the 25-post scan's numbers stay
        self.assertIsNone(none)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
