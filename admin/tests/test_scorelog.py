"""scorelog: freezing, late rows, sample campaigns, outcomes and the report, on a throwaway database."""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pathlib import Path
import db
import scorelog

TMP = tempfile.mkdtemp()
db.DB_PATH = Path(TMP) / "t.db"
db.init()
NOW = 1_790_000_000


def creator(code, followers):
    with db.connect() as c:
        c.execute("INSERT INTO creators (code,name,handle,platform,followers,tier,interest) VALUES (?,?,?,?,?,?,?)",
                  (code, "n " + code, code, "Instagram", followers, "micro", "Beauty"))


def analysis(code, followers, view_rate, er=1.4):
    doc = {"followers": followers, "er": er, "avg_likes": 600, "avg_comments": 40,
           "avg_views": followers * view_rate / 100.0, "sample_posts": 12, "fake_followers_pct": 25}
    with db.connect() as c:
        c.execute("INSERT INTO creator_analysis (code,platform,data,source,updated_at) VALUES (?,?,?,?,?)",
                  (code, "Instagram", json.dumps(doc), "t", NOW))


def campaign(name, client="Acme", objective="awareness", codes=()):
    with db.connect() as c:
        cur = c.execute("INSERT INTO campaigns (token,name,client,objective,platform,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                        ("tok" + name, name, client, objective, "Instagram", "live", NOW, NOW))
        cid = cur.lastrowid
        for i, code in enumerate(codes):
            c.execute("INSERT INTO campaign_creators (campaign_id,code,sort,added_at) VALUES (?,?,?,?)", (cid, code, i, NOW))
    return cid


def post(cid, code, views, followers, likes=100):
    with db.connect() as c:
        cur = c.execute("INSERT INTO content (campaign_id,code,platform,kind,url,followers,created_at) VALUES (?,?,?,?,?,?,?)",
                        (cid, code, "Instagram", "reel", "https://x/%s/%s" % (cid, code), followers, NOW))
        c.execute("INSERT INTO snapshots (content_id,at,likes,comments,views) VALUES (?,?,?,?,?)", (cur.lastrowid, NOW, likes, 5, views))


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for code, f, vr in (("A1", 50000, 30), ("A2", 50000, 22), ("A3", 50000, 14), ("A4", 50000, 9), ("A5", 50000, 6), ("A6", 50000, 4)):
            creator(code, f)
            analysis(code, f, vr)
        creator("NOAN", 40000)                                   # no analysis: logged with no score
        cls.cid = campaign("Live", codes=["A1", "A2", "A3", "A4", "A5", "A6", "NOAN"])

    def test_1_logs_every_creator_once_and_freezes(self):
        self.assertEqual(scorelog.snapshot(self.cid), 7)
        self.assertEqual(scorelog.snapshot(self.cid), 0)         # idempotent
        with db.connect() as c:
            row = c.execute("SELECT * FROM score_log WHERE campaign_id=? AND code='A1'", (self.cid,)).fetchone()
            before = row["score"]
            c.execute("UPDATE creator_analysis SET data=? WHERE code='A1'", (json.dumps({"followers": 50000, "er": 0.1, "avg_likes": 1, "avg_views": 10}),))
        scorelog.snapshot(self.cid)
        with db.connect() as c:
            self.assertEqual(c.execute("SELECT score FROM score_log WHERE campaign_id=? AND code='A1'", (self.cid,)).fetchone()["score"], before)
            noan = c.execute("SELECT * FROM score_log WHERE campaign_id=? AND code='NOAN'", (self.cid,)).fetchone()
        self.assertIsNone(noan["score"])
        self.assertEqual(row["engine"], "v5")
        self.assertEqual(row["objective"], "Awareness")
        self.assertEqual(row["late"], 0)
        self.assertGreater(row["pred_view_rate"], 25)
        self.assertTrue(json.loads(row["inputs"])["metrics"])

    def test_2_sample_campaigns_are_never_logged(self):
        cid = campaign("SAMPLE – demo", client="SunShield (demo)", codes=["A1"])
        self.assertEqual(scorelog.snapshot(cid), 0)

    def test_3_late_when_results_already_exist(self):
        cid = campaign("Old", codes=["A1", "A2"])
        post(cid, "A1", 1000, 50000)
        scorelog.snapshot(cid)
        with db.connect() as c:
            self.assertEqual([r["late"] for r in c.execute("SELECT late FROM score_log WHERE campaign_id=?", (cid,))], [1, 1])

    def test_4_report_ranks_prediction_against_results(self):
        # delivered view rate follows the stored view rate, so a good score should rank them well
        for code, f, delivered in (("A1", 50000, 28), ("A2", 50000, 20), ("A3", 50000, 15), ("A4", 50000, 8), ("A5", 50000, 7), ("A6", 50000, 3)):
            post(self.cid, code, f * delivered / 100.0, f)
        rep = [r for r in scorelog.report(self.cid)][0]
        self.assertEqual((rep["logged"], rep["with_results"], rep["real_predictions"], rep["late"]), (7, 6, 6, 0))
        self.assertEqual(rep["outcome"], "view rate")
        self.assertGreater(rep["score_corr"], 0.9)
        self.assertIsNone(rep["followers_corr"])                  # equal followers: no spread to rank
        self.assertIn("Campaign", scorelog.report_text(self.cid))

    def test_5_spearman(self):
        self.assertEqual(scorelog.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertEqual(scorelog.spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)
        self.assertIsNone(scorelog.spearman([1, 2, 3], [1, 2, 3]))
        self.assertIsNone(scorelog.spearman([1, 1, 1, 1], [1, 2, 3, 4]))

if __name__ == "__main__":
    unittest.main(verbosity=1)
