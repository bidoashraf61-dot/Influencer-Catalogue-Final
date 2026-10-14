import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import score_v5 as s

KSA = "Saudi Arabia"
IG = dict(platform="Instagram", followers=50000, country=KSA, er_pct=1.4, avg_likes=600, avg_comments=40,
          avg_views=12000, fake_pct=25, aud_countries=[{"name": KSA, "pct": 55}])
TT = dict(platform="TikTok", followers=50000, country=KSA, er_pct=4.0, avg_likes=3000, avg_views=60000,
          aud_countries=[{"name": KSA, "pct": 50}])
POSTS = [dict(views=10000, likes=400, comments=40), dict(views=20000, likes=900, comments=60),
         dict(views=15000, likes=600, comments=50), dict(views=12000, likes=500, comments=30)]


class V5(unittest.TestCase):
    def test_weights(self):
        self.assertEqual(s.weights_for("Awareness"), {"reach": 100, "engagement": 0})
        self.assertEqual(s.weights_for("Engagement"), {"reach": 0, "engagement": 100})
        self.assertEqual(s.weights_for("Traffic"), {"reach": 30, "engagement": 70})
        self.assertEqual(s.weights_for("Awareness+Engagement"), {"reach": 50, "engagement": 50})

    def test_engagement_graded_against_published_range(self):
        ref = s.intl_benchmarks.reference("Instagram", 50000)
        m = lambda er: s.score(dict(IG, er_pct=er), "Engagement", KSA)["metrics"]["engagement"]
        self.assertAlmostEqual(m(ref["low"])["score"], 40.0, 1)
        self.assertAlmostEqual(m(ref["high"])["score"], 75.0, 1)
        self.assertAlmostEqual(m(ref["high"] * 2)["score"], 85.0, 1)      # each step above the range adds less (2026-10-14)
        self.assertAlmostEqual(m(ref["high"] * 3)["score"], 90.0, 1)      # the best score
        self.assertEqual((m(0.3)["label"], m(1.5)["label"], m(4.0)["label"]), ("below", "within", "above"))

    def test_view_rate_has_headroom(self):
        rng = s._range("reach", "Instagram", 50000)            # micro: 5 - 8
        m = lambda vr: s.score(dict(IG, avg_views=vr / 100.0 * 50000), "Awareness", KSA)["metrics"]["reach"]["score"]
        self.assertAlmostEqual(m(rng[1]), 75.0, 1)
        self.assertLess(m(rng[1] * 2), 95)                     # no longer 100 at twice the high end
        self.assertAlmostEqual(m(rng[1] * 3), 90.0, 1)                # the peak: no cliff at 3x any more (2026-10-14)
        self.assertLess(m(rng[1] * 5), m(rng[1] * 3))                 # far out it eases down: often bought or a bad scrape
        self.assertGreater(m(rng[1] * 5), 80)
        self.assertLess(m(24.0), 100)                          # a typical Instagram view rate is not saturated
        self.assertLess(m(17.0), m(24.0))

    def test_score_ignores_audience_and_authenticity(self):
        base = s.score(IG, "Engagement", KSA)["score"]
        worse = s.score(dict(IG, fake_pct=70, aud_countries=[{"name": KSA, "pct": 0}]), "Engagement", KSA)
        self.assertEqual(worse["score"], base)
        self.assertEqual((worse["quality"]["audience_fit"]["label"], worse["quality"]["authenticity"]["label"]), ("Poor", "Poor"))

    def test_quality_labels_reported(self):
        q = s.score(IG, "Engagement", KSA)["quality"]
        self.assertEqual((q["audience_fit"]["label"], q["authenticity"]["label"]), ("Good", "Good"))
        self.assertIn("55% of followers in Saudi Arabia", q["audience_fit"]["note"])

    def test_full_data_is_high_confidence_and_nothing_to_check(self):
        r = s.score(IG, "Engagement", KSA)
        self.assertEqual((r["confidence"], r["confidence_pct"]), ("High", 100))
        self.assertEqual((r["check_manually"], r["estimated"]), ([], []))

    def test_missing_labels_listed_but_do_not_change_score(self):
        full = s.score(IG, "Engagement", KSA)
        bare = s.score(dict(IG, fake_pct=None, aud_countries=None, country=None), "Engagement", KSA)
        self.assertEqual(bare["score"], full["score"])
        listed = {x["metric"]: x["scored"] for x in bare["check_manually"]}
        self.assertEqual(listed, {"audience_fit": False, "authenticity": False})
        self.assertEqual(bare["confidence"], "High")             # confidence is about the scored metric only

    def test_instagram_hidden_likes_uses_posts_ladder(self):
        r = s.score(dict(IG, avg_likes=None, avg_comments=None, er_pct=0.1, recent_posts=POSTS), "Engagement", KSA)
        self.assertEqual(r["metrics"]["engagement"]["source"], "recent_posts")
        self.assertIn("engagement", r["estimated"])
        self.assertLess(r["confidence_pct"], 100)

    def test_instagram_hidden_likes_no_posts_needs_data(self):
        r = s.score(dict(IG, avg_likes=None, er_pct=0.1), "Engagement", KSA)
        self.assertTrue(r["unscored"])
        self.assertEqual(r["check_manually"][0]["metric"], "engagement")
        self.assertTrue(r["check_manually"][0]["scored"])

    def test_tiktok_engagement_ladder(self):
        bare = dict(TT, avg_likes=None, avg_views=None)
        self.assertEqual(s.score(bare, "Engagement", KSA)["metrics"]["engagement"]["source"], "unsupported")
        self.assertEqual(s.score(dict(bare, recent_posts=POSTS), "Engagement", KSA)["metrics"]["engagement"]["source"], "recent_posts")

    def test_reach_ladder(self):
        bare = dict(IG, avg_views=None, avg_plays=None)
        self.assertTrue(s.score(bare, "Awareness", KSA)["unscored"])
        self.assertEqual(s.score(dict(bare, recent_posts=POSTS), "Awareness", KSA)["metrics"]["reach"]["source"], "recent_posts")
        d = s.score(dict(TT, avg_views=None, avg_likes=None, engagements=2400.0), "Awareness", KSA)
        self.assertEqual(d["metrics"]["reach"]["source"], "derived")

    def test_traffic_reweights_when_reach_missing(self):
        both = s.score(IG, "Traffic", KSA)
        no_views = s.score(dict(IG, avg_views=None), "Traffic", KSA)
        self.assertEqual(set(both["metrics"]), {"engagement", "reach"})
        self.assertEqual(set(no_views["metrics"]), {"engagement"})
        self.assertIn("reach", [x["metric"] for x in no_views["check_manually"]])

    def test_audience_ladder_and_iso_codes(self):
        self.assertEqual(s.score(dict(IG, aud_countries=[{"code": "SA", "pct": 55}]), "Engagement", KSA)["quality"]["audience_fit"]["value"], 55)
        proxy = s.score(dict(IG, aud_countries=None), "Engagement", KSA)["quality"]["audience_fit"]
        self.assertEqual(proxy["source"], "creator_country")

    def test_inferred_authenticity_only_flags(self):
        r = s.score(dict(IG, fake_pct=None, er_pct=0.1), "Engagement", KSA)
        self.assertEqual(r["quality"]["authenticity"]["label"], "Poor")
        self.assertNotIn("authenticity", s.score(dict(IG, fake_pct=None), "Engagement", KSA)["quality"])

    def test_tiktok_has_no_fake_followers(self):
        r = s.score(TT, "Engagement", KSA)
        self.assertNotIn("authenticity", r["quality"])
        self.assertIn("authenticity", [x["metric"] for x in r["check_manually"]])

    def test_bad_scrape_not_trusted(self):
        self.assertTrue(s.score(dict(IG, er_pct=311.0, avg_likes=1), "Engagement", KSA)["unscored"])

    def test_objective_changes_ranking(self):
        reach = dict(IG, er_pct=0.2, avg_views=40000)
        eng = dict(IG, er_pct=3.0, avg_views=1500)
        a = lambda c: s.score(c, "Awareness", KSA)["score"]
        e = lambda c: s.score(c, "Engagement", KSA)["score"]
        self.assertGreater(a(reach), a(eng))
        self.assertGreater(e(eng), e(reach))

    def test_gates(self):
        camp = dict(platform="Instagram", countries=[KSA], industries=["Beauty & Personal Care"])
        ok = dict(IG, industry="Beauty & Personal Care", industry_tier="Confirmed", days_since_post=10)
        self.assertEqual(s.gates(ok, camp), [])
        bad = dict(ok, country="Egypt", industry_tier="Review", days_since_post=200)
        self.assertEqual(sorted(s.gates(bad, camp)), ["country", "inactive", "industry"])

if __name__ == "__main__":
    unittest.main(verbosity=1)
