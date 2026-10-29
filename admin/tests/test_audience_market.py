"""Audience in" filter (item 226, 2026-10-21): a creator is in a market when that country is the biggest
audience country on any analysed platform; GCC = Kuwait, Qatar, Bahrain, Oman.

    python3 admin/tests/test_audience_market.py
"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db, discover, paging


def summ(platform, **shares):
    return {"platform": platform, "countries": shares, "top": discover._top(shares)}


DOCS = {
    "SAUDI": [summ("Instagram", SA=55, AE=10)],
    "KUWAIT_TT": [summ("Instagram", SA=40, KW=30), summ("TikTok", KW=45, SA=20)],   # Saudi on IG, Kuwait on TikTok
    "QATAR": [summ("Instagram", QA=38, SA=30)],
    "INDIA": [summ("Instagram", IN=60, AE=12)],
    "TIE": [summ("Instagram", OM=30, EG=30)],
    "NODATA": [summ("Instagram")],
}


def card(code, followers=1000):
    return {"code": code, "name": code, "tier": "Micro", "platform": "Instagram", "city": "Riyadh", "interest": "",
            "followers": followers, "profiles": []}


CARDS = [card(c, f) for c, f in (("SAUDI", 9000), ("KUWAIT_TT", 8000), ("QATAR", 7000), ("INDIA", 6000),
                                 ("TIE", 5000), ("NODATA", 4000))]


class Rule(unittest.TestCase):
    def setUp(self):
        self._load = discover._load
        discover._load = lambda: DOCS

    def tearDown(self):
        discover._load = self._load

    def test_top_country(self):
        self.assertEqual(discover._top({"SA": 40, "KW": 30}), {"SA"})
        self.assertEqual(discover._top({"OM": 30, "EG": 30}), {"OM", "EG"})     # a tie counts both
        self.assertEqual(discover._top({}), set())

    def test_any_platform(self):
        tops = discover.top_markets()
        self.assertEqual(tops["KUWAIT_TT"], {"SA", "KW"})
        self.assertEqual(tops["SAUDI"], {"SA"})
        self.assertNotIn("INDIA", tops)          # top country outside the seven markets
        self.assertNotIn("NODATA", tops)

    def test_gcc_group(self):
        self.assertEqual(discover.markets_of(["GCC"]), ["KW", "QA", "BH", "OM"])
        self.assertEqual(discover.markets_of(["SA", "XX", "SA"]), ["SA"])

    def test_counts(self):
        n = discover.market_counts()
        self.assertEqual((n["SA"], n["KW"], n["QA"], n["OM"], n["EG"], n["GCC"]), (2, 1, 1, 1, 1, 3))


class Filter(unittest.TestCase):
    def run_q(self, **kw):
        idx = paging.Index("t-aud", CARDS, [{"name": "Micro"}])
        f = paging.clean_query({k: v if isinstance(v, list) else [v] for k, v in kw.items()})
        tops = {"SAUDI": {"SA"}, "KUWAIT_TT": {"SA", "KW"}, "QATAR": {"QA"}, "TIE": {"OM", "EG"}}
        out = paging.page(idx, dict(f, sort="followers-desc"), audience=lambda: tops)
        return out, f

    # Item 280 (Bido, 2026-10-29): the roster takes no audience filter; old links that carry one are ignored.
    def test_clean_query_drops_audience(self):
        f = paging.clean_query({"aud": ["GCC", "SA"], "ac": ["KW"], "acp": ["40"], "ag": ["female"]})
        self.assertEqual((f["aud"], f["ash"]), ([], {}))
        self.assertFalse(paging.filtering(f))

    def test_audience_link_shows_everyone(self):
        out, _ = self.run_q(aud="KW")
        self.assertEqual(len(out["items"]), 6)
        self.assertNotIn("match", out)

    def test_discover_audience_keys_dropped(self):
        f = paging.clean_query({"disc": ['{"a_country": ["KW"], "er_min": 2}']})
        self.assertEqual(f["disc"], {"er_min": 2})


class Markets(unittest.TestCase):
    def test_portal_countries_include_gcc(self):
        for land in ("Kuwait", "Qatar", "Bahrain", "Oman", "Saudi Arabia", "UAE", "Egypt"):
            self.assertIn(land, db.PORTAL_COUNTRIES)
        for city in ("Kuwait City", "Doha", "Manama", "Muscat"):
            self.assertIn(paging.place(city)[0], db.PORTAL_COUNTRIES)


if __name__ == "__main__":
    unittest.main()
