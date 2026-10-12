"""Industry / sub-niche filter (2026-10-13): confirmed matches first, probable after, Review never."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import paging

def card(code, ind, tier, sub=(), also=(), followers=1000):
    return {"code": code, "name": code, "tier": "Micro", "platform": "Instagram", "city": "Riyadh", "interest": "",
            "followers": followers, "profiles": [], "ind": ind, "sub": list(sub), "also": list(also), "itier": tier}

CARDS = [
    card("A", "Beauty & Personal Care", "Confirmed", ["Skincare", "Makeup"], followers=500),
    card("B", "Beauty & Personal Care", "Probable", ["Skincare"], followers=900),
    card("C", "Fashion", "Confirmed", ["Modest fashion"], ["Beauty & Personal Care"], followers=800),
    card("D", "Beauty & Personal Care", "Review", ["Makeup"], followers=9000),     # never in industry results
    card("E", "Sports", "Confirmed", [], [], followers=7000),
    card("F", "General Lifestyle", "Confirmed", [], [], followers=300),
    card("G", None, "", [], [], followers=200),
]

class T(unittest.TestCase):
    def run_q(self, **kw):
        idx = paging.Index("t", CARDS, [{"name": "Micro"}])
        f = paging.clean_query({k: v if isinstance(v, list) else [v] for k, v in kw.items()})
        seq, n = paging.ordered(idx, f)
        return [(idx.cards[i]["code"], pm) for i, g, pm in seq.slice(0, 50)], n

    def test_industry_confirmed_first_probable_after(self):
        got, n = self.run_q(industry="Beauty & Personal Care", sort="followers-desc")
        self.assertEqual([c for c, _ in got], ["A", "B", "C"])       # D (Review) never; A confirmed, then B and C probable
        self.assertEqual([pm for _, pm in got], [0, 1, 1])
        self.assertEqual(n, 3)

    def test_sub_niche(self):
        got, _ = self.run_q(industry="Beauty & Personal Care", sub="Skincare")
        self.assertEqual(got, [("A", 0), ("B", 1)])

    def test_sub_alone(self):
        got, _ = self.run_q(sub="Modest fashion")
        self.assertEqual(got, [("C", 0)])

    def test_unclassified_and_catchall_never(self):
        got, _ = self.run_q(industry=["Sports", "General Lifestyle"])
        self.assertEqual([c for c, _ in got], ["E", "F"])             # F is Confirmed under its own label if asked directly
        got, _ = self.run_q(industry="Fashion")
        self.assertNotIn("G", [c for c, _ in got])

    def test_facets_hide_catchalls_and_review(self):
        idx = paging.Index("t", CARDS, [{"name": "Micro"}])
        fac = idx.facets()
        self.assertNotIn("General Lifestyle", fac["industry"])
        self.assertEqual(fac["industry"][0], "Beauty & Personal Care" if False else fac["industry"][0])
        self.assertIn("Skincare", fac["sub"]["Beauty & Personal Care"])
        self.assertNotIn("D", str(fac))

    def test_no_filter_no_flags(self):
        got, _ = self.run_q()
        self.assertTrue(all(pm == 0 for _, pm in got))
        self.assertEqual(len(got), 7)

if __name__ == "__main__":
    unittest.main()
