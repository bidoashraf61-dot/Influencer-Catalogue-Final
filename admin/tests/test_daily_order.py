"""The catalogue's default "Recommended" order (2026-10-19, groups reset 2026-10-20): doctors (any HCP
tier), then Saudi celebrities (Mega in Saudi Arabia), then creators on a selection, then other Mega,
Macro, Micro, Nano; random inside each group, the same for everyone on a Riyadh day, new the next day.
Explicit sorts are untouched.

    python3 admin/tests/test_daily_order.py
"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import paging

TIERS = ["Mega", "HCP - Nano", "HCP - Micro", "HCP - Macro", "HCP - Mega", "Macro", "Micro", "Nano", ""]
CITIES = ["Riyadh", "Dubai", "Jeddah", "Cairo"]          # Saudi, UAE, Saudi, Egypt
SAUDI = {"Riyadh", "Jeddah"}
CARDS = [{"code": "HV-D-%03d" % i, "name": "Creator %03d" % i, "tier": TIERS[i % len(TIERS)], "platform": "Instagram",
          "city": CITIES[(i // len(TIERS)) % len(CITIES)], "interest": "Food" if i % 2 else "Travel",
          "followers": 1000 + (i * 7919) % 900000, "profiles": []}
         for i in range(270)]
PICKED = frozenset(c["code"] for i, c in enumerate(CARDS) if i % 5 == 0)
TABLE = [{"name": t} for t in TIERS if t]
DAY1, DAY2 = "20261019", "20261020"
SIZE = {"Mega": 3, "Macro": 4, "Micro": 6, "Nano": 7}


def group(code):
    c = next(x for x in CARDS if x["code"] == code)
    if c["tier"].startswith("HCP"):
        return 0
    if c["tier"] == "Mega" and c["city"] in SAUDI:
        return 1
    if code in PICKED:
        return 2
    return SIZE.get(c["tier"], 8)


def query(**kw):
    return paging.clean_query({k: [v] for k, v in kw.items()})


class DailyOrder(unittest.TestCase):
    def setUp(self):
        paging._state["results"] = {}
        self.idx = paging.Index("daily-test", CARDS, TABLE)

    def codes(self, f, day=None):
        seq, _ = paging.ordered(self.idx, f, day=day, picked=PICKED)
        return [self.idx.cards[i]["code"] for i, _, _ in seq.slice(0, 10000)]

    def tiers(self, codes):
        by = {c["code"]: c["tier"] for c in CARDS}
        return [by[c] for c in codes]

    def test_default_is_daily(self):
        self.assertEqual(paging.clean_query({})["sort"], "daily")
        self.assertEqual(query(sort="nonsense")["sort"], "daily")
        self.assertEqual(query(sort="")["sort"], "")            # the roster's own order stays available

    def test_groups_in_order(self):
        got = self.codes(query(), DAY1)
        self.assertEqual(len(got), len(CARDS))
        groups = [group(c) for c in got]
        self.assertEqual(groups, sorted(groups))
        self.assertEqual(set(groups), set(range(9)) - {5})     # no Mid in the fixture
        self.assertTrue(self.tiers(got)[0].startswith("HCP"))   # doctors first
        self.assertTrue(self.tiers(got)[-1] == "")              # no tier: last

    def test_hcp_and_celebs_ahead_of_selections(self):
        got = self.codes(query(), DAY1)
        first_picked = next(i for i, c in enumerate(got) if group(c) == 2)
        before = got[:first_picked]
        self.assertTrue(all(group(c) in (0, 1) for c in before))
        # a non-Saudi Mega creator does not count as a celebrity
        uae_mega = [c["code"] for c in CARDS if c["tier"] == "Mega" and c["city"] == "Dubai" and c["code"] not in PICKED]
        self.assertTrue(uae_mega and all(got.index(c) > first_picked for c in uae_mega))

    def test_selection_set_changes_order(self):
        a = self.codes(query(), DAY1)
        seq, _ = paging.ordered(self.idx, query(), day=DAY1, picked=frozenset())
        b = [self.idx.cards[i]["code"] for i, _, _ in seq.slice(0, 10000)]
        self.assertNotEqual(a, b)

    def test_same_day_stable(self):
        a = self.codes(query(), DAY1)
        paging._state["results"] = {}
        self.idx = paging.Index("daily-test-2", CARDS, TABLE)   # a rebuilt index (a creator edit) keeps the day's order
        self.assertEqual(a, self.codes(query(), DAY1))

    def test_next_day_different_but_same_groups(self):
        a, b = self.codes(query(), DAY1), self.codes(query(), DAY2)
        self.assertNotEqual(a, b)
        self.assertEqual([group(c) for c in a], [group(c) for c in b])
        # shuffled, not by followers: inside the Mega group the order is not most-followers-first
        fol = {c["code"]: c["followers"] for c in CARDS}
        mega = [c for c in a if group(c) == 1]
        self.assertNotEqual(mega, sorted(mega, key=lambda c: -fol[c]))

    def test_filtered_view_keeps_relative_order(self):
        full = self.codes(query(), DAY1)
        food = self.codes(query(interest="Food"), DAY1)
        self.assertEqual(food, [c for c in full if c in set(food)])

    def test_explicit_sorts_unchanged(self):
        fol = {c["code"]: c["followers"] for c in CARDS}
        for day in (DAY1, DAY2):
            got = self.codes(query(sort="followers-desc"), day)
            self.assertEqual([fol[c] for c in got], sorted(fol.values(), reverse=True))
            names = self.codes(query(sort="name"), day)
            self.assertEqual(names, sorted(names, key=lambda c: "creator " + c[-3:]))
        self.assertEqual(self.codes(query(sort="followers-asc"), DAY1), self.codes(query(sort="followers-asc"), DAY2))
        self.assertEqual(self.codes(query(sort=""), DAY1), [c["code"] for c in CARDS])

    def test_riyadh_day(self):
        # 2026-10-19 21:30 UTC is already 2026-10-20 in Riyadh
        self.assertEqual(paging.riyadh_day(1792445400), "20261020")
        self.assertEqual(paging.riyadh_day(1792445400 - 3 * 3600), "20261019")

    def test_cursor_keeps_the_day_it_started(self):
        orig = paging.riyadh_day
        try:
            paging.riyadh_day = lambda now=None: DAY1
            first = paging.page(self.idx, query())
            self.assertTrue(first["cursor"].endswith("." + DAY1))
            paging.riyadh_day = lambda now=None: DAY2          # midnight passes mid-scroll
            nxt = paging.page(self.idx, query(), cursor=first["cursor"])
            want = self.codes(query(), DAY1)[paging.BATCH:2 * paging.BATCH]
            self.assertEqual([c["code"] for c in nxt["items"]], want)
            fresh = paging.page(self.idx, query())              # a new visit gets the new day
            self.assertEqual([c["code"] for c in fresh["items"]], self.codes(query(), DAY2)[:paging.BATCH])
        finally:
            paging.riyadh_day = orig

    def test_explicit_sort_cursor_has_no_day(self):
        b = paging.page(self.idx, query(sort="followers-desc"))
        self.assertEqual(b["cursor"].count("."), 1)


if __name__ == "__main__":
    unittest.main()
