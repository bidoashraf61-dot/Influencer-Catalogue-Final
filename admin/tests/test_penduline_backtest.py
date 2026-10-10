"""Penduline campaign 01 (18 real Instagram reels, 577,608 actual views): the old and the new model
on the same posts. It PRINTS the tables (run with -v or directly) and asserts only sane things; no
constant is tuned to make a number pass.

    python3 -m unittest tests.test_penduline_backtest     (from admin/)
"""
import json
import math
import statistics
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import peerfix  # noqa: E402
import fit  # noqa: E402
import plans  # noqa: E402
import roi  # noqa: E402

POSTS = json.loads((Path(__file__).resolve().parent / "fixtures" / "penduline_campaign01.json").read_text())
ACTUAL = sum(p["views"] for p in POSTS)


def er_on_views(p):
    return ((p["likes"] or 0) + (p["comments"] or 0)) / float(p["views"]) * 100 if p["likes"] is not None else None


class Backtest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        peerfix.load_peers()
        plans.house_benchmarks = lambda: {}
        roi.db.setting = lambda key, default=None: default
        cls.old_fit = peerfix.legacy("fit_v1")
        cls.old_roi = peerfix.legacy("roi_v2")
        cls.old_roi.db.setting = lambda key, default=None: default

    def scores(self):
        old, new = [], []
        for p in POSTS:
            d = dict(p["doc"], followers=p["doc"].get("followers") or p["followers"])
            o = self.old_fit.score_core(dict(d), "Instagram", p["followers"], "Awareness", None, "mid", None, None, None, 3)
            n = fit.score_core(dict(d), "Instagram", p["followers"], "Awareness", None, "mid", None, None, None, 1)
            old.append(o["score"]); new.append(n["score"])
        return old, new

    def test_score_vs_what_happened(self):
        old, new = self.scores()
        vr = [p["views"] / float(p["followers"]) * 100 for p in POSTS]
        idx = [i for i, p in enumerate(POSTS) if er_on_views(p) is not None]
        er = [er_on_views(POSTS[i]) for i in idx]
        lf = [math.log10(p["followers"]) for p in POSTS]
        rows = [("old model", old), ("new model", new)]
        print("\n== Penduline backtest: score (objective Awareness) vs what happened, Spearman rank correlation ==")
        print("%-12s %-22s %-24s %-22s" % ("", "vs view rate (n=18)", "vs engagement on views (n=%d)" % len(idx), "vs log followers (n=18)"))
        res = {}
        for name, sc in rows:
            a = peerfix.spearman(sc, vr)
            b = peerfix.spearman([sc[i] for i in idx], er)
            c = peerfix.spearman(sc, lf)
            res[name] = (a, b, c)
            print("%-12s %-22.2f %-24.2f %-22.2f" % (name, a, b, c))
        print("context: engagement on views itself vs log followers %.2f, vs views %.2f (small accounts get more likes per view)" % (
            peerfix.spearman(er, [lf[i] for i in idx]), peerfix.spearman(er, [POSTS[i]["views"] for i in idx])))
        print("scores old:", old)
        print("scores new:", new)
        # sane things only
        self.assertTrue(all(0 <= s <= 100 for s in new if s is not None))
        # Reported honestly, not forced: engagement on views is itself driven by size here (small accounts get more
        # likes per view), and a size-neutral score cannot follow that. Only "not strongly negative" is asserted.
        self.assertGreater(res["new model"][1], -0.5, "the new score is strongly negatively correlated with engagement on views")
        self.assertGreater(res["new model"][1], res["old model"][1], "the new score should be less anti-correlated with engagement than the old one")
        self.assertLess(abs(res["new model"][2]), abs(res["old model"][2]), "the new score must lean less on follower count than the old one")

    def _creators(self):
        by = {}
        for p in POSTS:
            by.setdefault(p["code"], {"code": p["code"], "name": p["code"], "followers": {"Instagram": p["followers"]},
                                      "docs": {"Instagram": dict(p["doc"], followers=p["followers"])}, "scores": {}})
        return by

    def test_forecast_vs_actual(self):
        # new model: the 18 actual posts, each by the creator's own record, efficiency from the new score
        raw = []
        for p in POSTS:
            d = dict(p["doc"], followers=p["followers"])
            s = fit.score_core(dict(d), "Instagram", p["followers"], "Awareness", None, "mid", None, None, None, 1)["score"]
            raw.append(roi.post_values("Instagram", p["followers"], d, s, plans.library()))
        tot, lo, hi = roi.combine(raw, "views", "m_views")
        per_new = [r["views"] for r in raw]
        # old model: the guide view rate by size, +/-20 %
        L = self.old_roi.plans.library()
        per_old = []
        for p in POSTS:
            t = self.old_roi.tier_of(p["followers"])
            per_old.append(p["followers"] * self.old_roi._mid(L["Instagram"]["view_rate"][t]) / 100.0)
        old_tot = sum(per_old)
        old_lo, old_hi = old_tot * 0.8, old_tot * 1.2

        def med_err(pred):
            return statistics.median(abs(a - b) / float(b) for a, b in zip(pred, [p["views"] for p in POSTS]))

        def med_ratio(pred):
            return statistics.median(a / float(b) for a, b in zip(pred, [p["views"] for p in POSTS]))
        print("\n== Penduline backtest: predicted total views for the 18 posts, actual %s ==" % format(ACTUAL, ","))
        print("%-10s %-14s %-24s %-12s %-18s %-16s" % ("model", "predicted", "range", "pred/actual", "actual in range?", "median |error| per post"))
        print("%-10s %-14s %-24s %-12.2f %-18s %-16.0f%%" % ("old (v2)", format(int(old_tot), ","), "%s–%s" % (format(int(old_lo), ","), format(int(old_hi), ",")),
                                                           old_tot / ACTUAL, "yes" if old_lo <= ACTUAL <= old_hi else "no", med_err(per_old) * 100))
        print("%-10s %-14s %-24s %-12.2f %-18s %-16.0f%%" % ("new (v3)", format(int(tot), ","), "%s–%s" % (format(lo, ","), format(hi, ",")),
                                                           tot / ACTUAL, "yes" if lo <= ACTUAL <= hi else "no", med_err(per_new) * 100))
        print("median predicted/actual per post: old %.2f, new %.2f" % (med_ratio(per_old), med_ratio(per_new)))
        print("basis of the new views per post:", sorted({r["basis"] for r in raw}))
        self.assertGreater(tot, 0)
        self.assertLessEqual(lo, tot)
        self.assertGreaterEqual(hi, tot)

    def test_v4_structure_vs_performance(self):
        """Fix batch 7. (1) the 18 posts' total views against the actual; (2) the Selection quality of the
        campaign's creators against the Awareness ideal for the same number of creators.
        NOTE: IG_VIEW_RATE was calibrated on 39 reels that include these 18, so (1) is in-sample."""
        creators = list(self._creators().values())
        for c in creators:
            d = c["docs"]["Instagram"]
            c["scores"]["Instagram"] = fit.score_core(dict(d), "Instagram", c["followers"]["Instagram"], "Awareness", None, "mid",
                                                       None, None, None, 1)["score"]
        res = roi.estimate("awareness", ["Instagram"], creators=creators, goals=["awareness"])
        # each of the 18 posts as its own post (repeat posts count again), as the v2/v3 backtest did
        raw = []
        for p in POSTS:
            d = dict(p["doc"], followers=p["followers"])
            s = fit.score_core(dict(d), "Instagram", p["followers"], "Awareness", None, "mid", None, None, None, 1)["score"]
            raw.append(roi.post_values("Instagram", p["followers"], d, s, plans.library()))
        tot, lo, hi = roi.combine(raw, "views", "m_views")
        print("\n== Penduline backtest v4 ==")
        print("18 posts: predicted %s, range %s-%s, predicted/actual %.2f, actual in range: %s" % (
            format(int(tot), ","), format(lo, ","), format(hi, ","), tot / ACTUAL, lo <= ACTUAL <= hi))
        q = res["quality"]
        print("%d creators, %d posts (one each): expected views %s; ideal for the same number %s; Selection quality %s (band %s, overlap %.2f)" % (
            res["creators"], res["posts"], res["figures"][0]["range"], res["ideal"]["figures"][0]["range"], q["text"], q["band"], q["overlap"]))
        print("gap:", res["gap"], "| by size:", [(x["label"], x["n"]) for x in res["selection"]["by_size"] if x["n"]],
              "| ideal:", res["ideal"]["mix"])
        self.assertGreater(tot, 0)
        self.assertIsNotNone(q)


if __name__ == "__main__":
    unittest.main(verbosity=2)
