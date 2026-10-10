"""End-to-end tests for fix batch 3, item 16: the catalogue served page by page.

- /api/roster/page answers 48 cards and has_more, never a total; a "match" count only
  while a filter or a search is on;
- every filter (tier, platform, place, interest, followers, licence, Audience/Performance
  via discover), search, sort and group-by run on the server and agree with catalogue.js;
- a cursor is stable: the same cursor gives the same batch, and one handed out before a
  creator changed still continues the list it started;
- the gate is /api/roster's: a locked browser gets nothing, a link needs its own code;
- /api/roster/cards returns only creators on the roster (active), in the order asked;
- /api/roster/facets lists options, no counts;
- the onboarding tour's demo world answers the new endpoints.

Same harness as e2e_portal.py (a throwaway copy of admin/*.py, an empty database).

    python3 admin/tests/e2e_portal_fixes3_paging.py
"""
import json
import shutil
import sys
import threading
import time
import unittest
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402  (copies admin/*.py to a temp dir and puts it on the path)
from e2e_portal import Client  # noqa: E402

import auth, db, gemini, guard, licence, mailer, paging, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
CITIES = ["Riyadh", "Jeddah", "Dubai", "Cairo", "UAE (Ajman)", "Kuwait Not Specified yet", "Doha", ""]
PLATS = ["Instagram", "TikTok", "Snapchat"]
TIERS = ["Micro", "Mid-Tier"]
INTERESTS = ["Food", "Skincare, Beauty", "Travel"]


def q(**kw):
    """Query string: lists become repeated keys."""
    pairs = []
    for k, v in kw.items():
        for x in (v if isinstance(v, list) else [v]):
            pairs.append((k, x))
    return urllib.parse.urlencode(pairs)


class Paging(unittest.TestCase):
    signup = base.Portal.signup

    @classmethod
    def setUpClass(cls):
        base.seed()
        licence.init()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        mailer.CAPTURE = True
        gemini.STUB = base.stub
        views.set_base("")
        paging.CHECK_EVERY = 0           # see a change at once
        for i in range(130):
            plat = PLATS[i % 3]
            fol = 10000 + i * 997
            profs = [{"platform": plat, "url": "https://x/t%d" % i, "followers": fol}]
            if i % 5 == 0:
                profs.append({"platform": "TikTok", "url": "https://x/t%d/tt" % i, "followers": 500})
            db.upsert_creator({"code": "HV-TS-%03d" % i, "name": "Test Creator %d" % i, "handle": "t%d" % i,
                               "platform": plat if i % 5 else plat + ", TikTok", "followers": fol,
                               "city": CITIES[i % len(CITIES)], "nationality": "", "tier": TIERS[i % 2],
                               "interest": INTERESTS[i % 3], "photo": None, "profiles": json.dumps(profs),
                               "active": 0 if i % 13 == 12 else 1, "note": "", "sort": 0})
        db.upsert_creator({"code": "HV-TS-900", "name": "𝓓𝓻. 𝓗𝓪𝓵𝓪 Sami", "handle": "hala", "platform": "Instagram",
                           "followers": 5000, "city": "Riyadh", "nationality": "", "tier": "Micro", "interest": "Health",
                           "photo": None, "profiles": json.dumps([{"platform": "Instagram", "url": "https://x/h", "followers": 5000}]),
                           "active": 1, "note": "", "sort": 0})
        licence.update("HV-TS-001", "SA", "verified", "123")
        licence.update("HV-TS-002", "AE", "claimed")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()
        if not hasattr(Paging, "c"):
            Paging.c, _ = self.signup("paging@pager-test.com")

    def page(self, c=None, **kw):
        s, b, _ = (c or self.c).get("/api/roster/page?" + q(**kw))
        self.assertEqual(s, 200, b)
        return b

    def walk(self, **kw):
        out, cur = [], None
        for _ in range(50):
            b = self.page(**dict(kw, **({"cursor": cur} if cur else {})))
            out += b["items"]
            if not b["has_more"]:
                self.assertIsNone(b["cursor"])
                return out, b
            cur = b["cursor"]
        self.fail("never ended")

    def active(self):
        return [r for r in db.list_creators(active_only=True)]

    @staticmethod
    def total(card):
        return sum(int(p.get("followers") or 0) for p in card.get("profiles") or []) or int(card.get("followers") or 0)

    # ------------------------------------------------------------------ batches --
    def test_01_batches_of_48_and_never_a_total(self):
        b = self.page()
        self.assertEqual(len(b["items"]), 48)
        self.assertTrue(b["has_more"])
        self.assertTrue(b["cursor"])
        self.assertNotIn("match", b)
        for k in ("total", "count", "size"):
            self.assertNotIn(k, b)
        self.assertIn("tiers", b)                 # the first batch carries what the page needs to price
        self.assertIn("fx", b)
        b2 = self.page(cursor=b["cursor"])
        self.assertNotIn("tiers", b2)
        items, last = self.walk()
        codes = [c["code"] for c in items]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(set(codes), {r["code"] for r in self.active()})
        self.assertNotIn("HV-TS-012", codes)      # inactive
        # the same fields per card as /api/roster
        s, full, _ = self.c.get("/api/roster")
        by = {r["code"]: r for r in full["roster"]}
        self.assertEqual(items[0], by[items[0]["code"]])
        # default order: most followers first, summed over accounts
        fs = [self.total(c) for c in items]
        self.assertEqual(fs, sorted(fs, reverse=True))
        # limit: up to 480 (returning to the same spot), never more
        self.assertEqual(len(self.page(limit=100)["items"]), 100)
        self.assertLessEqual(len(self.page(limit=100000)["items"]), paging.MAX_LIMIT)

    # ------------------------------------------------------------------ filters --
    def test_02_filters_run_on_the_server(self):
        items, b = self.walk(tier="Micro")
        self.assertTrue(items and all(c["tier"] == "Micro" for c in items))
        self.assertEqual(b["match"], len(items))
        self.assertEqual(len(items), sum(1 for r in self.active() if r["tier"] == "Micro"))
        # OR within a dimension, AND across
        items, _ = self.walk(platform=["Snapchat", "TikTok"], tier="Mid-Tier")
        self.assertTrue(items)
        for c in items:
            self.assertEqual(c["tier"], "Mid-Tier")
            self.assertTrue(set(paging.values(c["platform"])) & {"Snapchat", "TikTok"}, c["platform"])
        # places: a city key, a country-only value, a bracketed city, a pending country
        for key, want in (("Saudi Arabia|Riyadh", "Riyadh"), ("UAE|Ajman", "UAE (Ajman)"),
                          ("Kuwait|City not specified", "Kuwait Not Specified yet")):
            items, _ = self.walk(place=key)
            self.assertTrue(items, key)
            self.assertTrue(all(c["city"] == want or want in c["city"] for c in items), (key, {c["city"] for c in items}))
        self.assertEqual(paging.place("UAE (Ajman)")[2], "UAE|Ajman")
        self.assertEqual(paging.place("KSA")[2], "Saudi Arabia|City not specified")
        self.assertEqual(paging.place("Somewhere else")[2], "Other|Somewhere Else")
        items, _ = self.walk(interest="Beauty")
        self.assertTrue(items and all("Beauty" in c["interest"] for c in items))
        # followers range on the sum of every account
        items, _ = self.walk(fmin=50000, fmax=90000)
        self.assertTrue(items)
        self.assertTrue(all(50000 <= self.total(c) <= 90000 for c in items))
        # licence: Mawthooq (SA) and/or UAE
        self.assertEqual([c["code"] for c in self.walk(lic="SA")[0]], ["HV-TS-001"])
        self.assertEqual({c["code"] for c in self.walk(lic=["SA", "AE"])[0]}, {"HV-TS-001", "HV-TS-002"})
        # Audience / Performance (discover.py): only creators whose analysis passes
        db.save_analysis("HV-TS-003", {"followers": 40000, "er": 6.0, "audience": {"countries": [{"code": "SA", "pct": 80.0}]}},
                         platform="Instagram")
        import discover
        want = set(discover.match({"er_min": 5}, None))
        got = {c["code"] for c in self.walk(disc=json.dumps({"er_min": 5}))[0]}
        self.assertEqual(got, want)
        # nothing matches: an empty batch, has_more false, match 0
        b = self.page(q="nobody-is-called-this")
        self.assertEqual((b["items"], b["has_more"], b["match"]), ([], False, 0))

    def test_03_search_folds_like_the_page(self):
        b = self.page(q=paging.fold("dr hala"))
        self.assertEqual([c["code"] for c in b["items"]], ["HV-TS-900"])
        b = self.page(q="DR. HALA")                 # the server folds it too
        self.assertEqual([c["code"] for c in b["items"]], ["HV-TS-900"])
        b = self.page(q="hv ts 05")                  # codes are searchable
        self.assertTrue(all(c["code"].startswith("HV-TS-05") for c in b["items"]) and b["items"])
        self.assertEqual(b["match"], len(b["items"]))

    def test_04_sorts_and_groups(self):
        def all_(**kw):
            return self.walk(**kw)[0]
        fs = [self.total(c) for c in all_(sort="followers-asc")]
        self.assertEqual(fs, sorted(fs))
        names = [c["name"].lower() for c in all_(sort="name")]
        self.assertEqual(names, sorted(names))
        rows = all_(sort="tier-desc")
        tiers = [r["name"] for r in db.list_tiers()]
        ranks = [paging.tier_rank(c["tier"], tiers) for c in rows]
        self.assertEqual(ranks, sorted(ranks, reverse=True))
        rec = [c["code"] for c in all_(sort="")]                 # "Recommended": the roster's own order
        self.assertEqual(rec, [r["code"] for r in self.active()])
        # group by country: sections in the fixed country order, Other / none last, a creator in each of its groups
        items = all_(group="country")
        groups = []
        for c in items:
            if not groups or groups[-1] != c["g"]:
                groups.append(c["g"])
        self.assertEqual(len(groups), len(set(groups)), groups)              # one run per group
        fixed = [g for g in groups if g in paging.COUNTRY_ORDER]
        self.assertEqual(fixed, sorted(fixed, key=paging.COUNTRY_ORDER.index))
        self.assertEqual(groups[-1], "Location not specified")
        items = all_(group="platform")
        multi = [c for c in items if c["code"] == "HV-TS-000"]
        self.assertEqual(sorted(c["g"] for c in multi), ["Instagram", "TikTok"])
        # grouped answers count creators, not entries
        b = self.page(group="platform", tier="Micro")
        self.assertEqual(b["match"], sum(1 for r in self.active() if r["tier"] == "Micro"))

    def test_05_cursor_is_stable(self):
        b = self.page(sort="followers-desc")
        again = self.page(cursor=b["cursor"], sort="followers-desc")
        self.assertEqual(again, self.page(cursor=b["cursor"], sort="followers-desc"))
        # a creator changes (a new roster version): the old cursor continues the old order
        second = [c["code"] for c in again["items"]]
        top = b["items"][0]["code"]
        with db.connect() as conn:
            conn.execute("UPDATE creators SET followers = 1, profiles = ?, updated_at = ? WHERE code = ?",
                         (json.dumps([{"platform": "Instagram", "url": "https://x", "followers": 1}]), int(time.time()) + 5, top))
        fresh = self.page(sort="followers-desc")
        self.assertNotEqual(fresh["v"], b["v"])
        self.assertNotIn(top, [c["code"] for c in fresh["items"]])
        self.assertEqual([c["code"] for c in self.page(cursor=b["cursor"], sort="followers-desc")["items"]], second)
        # a junk cursor starts from the top rather than failing
        self.assertEqual(self.page(cursor="nonsense")["items"][0]["code"], fresh["items"][0]["code"])

    # --------------------------------------------------------------------- gate --
    def test_06_gated_exactly_like_the_roster(self):
        locked = Client(self.base)
        for path in ("/api/roster", "/api/roster/page", "/api/roster/facets", "/api/roster/cards?codes=HV-TS-001"):
            s, b, _ = locked.get(path)
            self.assertEqual((s, b.get("reason")), (401, "locked"), path)
            self.assertNotIn("items", b)
            self.assertNotIn("cards", b)
        # an access-code viewer: a selection link they hold no code for is refused, like /api/roster
        a_id = db.create_code(auth.hash_code("Page Alpha 1"), "pa", "Alpha co", None, None, "Page Alpha 1", 5)
        b_id = db.create_code(auth.hash_code("Page Beta 2"), "pb", "Beta co", None, None, "Page Beta 2", 5)
        sa = db.selection(db.save_selection(None, "Alpha", ["HV-TS-001"], {}, None, None, None, a_id))["token"]
        sb = db.selection(db.save_selection(None, "Beta", ["HV-TS-002"], {}, None, None, None, b_id))["token"]
        v = Client(self.base)
        s, b, _ = v.post("/api/unlock", {"code": "Page Alpha 1", "link": "s:" + sa, "lite": True})
        self.assertTrue(b["ok"])
        self.assertNotIn("roster", b)                # the lite unlock the page now uses sends no roster
        for link in ("s:" + sa, "cat"):
            for path in ("/api/roster", "/api/roster/page", "/api/roster/facets", "/api/roster/cards"):
                self.assertEqual(v.get(path + "?link=" + link)[0], 200, (path, link))
        for path in ("/api/roster", "/api/roster/page", "/api/roster/facets", "/api/roster/cards"):
            s, b, _ = v.get(path + "?link=s:" + sb)
            self.assertEqual((s, b.get("reason")), (401, "link"), path)

    # -------------------------------------------------------------------- cards --
    def test_07_cards_by_code_only_visible_creators(self):
        s, b, _ = self.c.get("/api/roster/cards?" + q(codes="HV-TS-005,HV-TS-012,HV-NOPE-1,hv-ts-001,HV-TS-005"))
        self.assertEqual(s, 200)
        self.assertEqual([c["code"] for c in b["cards"]], ["HV-TS-005", "HV-TS-001"])    # inactive and unknown dropped, order kept
        self.assertIn("tiers", b)
        s, b, _ = self.c.get("/api/roster/cards?" + q(codes=",".join("HV-TS-%03d" % i for i in range(130)) + ",HV-MI-001,HV-MI-002"))
        self.assertLessEqual(len(b["cards"]), 200)
        s, b, _ = self.c.get("/api/roster/cards")
        self.assertEqual((s, b["cards"]), (200, []))

    def test_08_facets_are_options_not_counts(self):
        s, b, _ = self.c.get("/api/roster/facets")
        self.assertEqual(s, 200)
        f = b["facets"]
        self.assertEqual(set(f), {"tier", "platform", "place", "interest"})
        for k, vs in f.items():
            self.assertTrue(all(isinstance(v, str) for v in vs), k)
        self.assertEqual(f["tier"][0], "Mid-Tier" if sum(1 for r in self.active() if r["tier"] == "Mid-Tier")
                         > sum(1 for r in self.active() if r["tier"] == "Micro") else "Micro")
        self.assertIn("Saudi Arabia|Riyadh", f["place"])
        self.assertIn("UAE|Ajman", f["place"])
        self.assertIn("Beauty", f["interest"])
        self.assertNotIn("Unspecified", json.dumps(f))

    def test_09_index_is_built_once_per_version(self):
        calls = []
        orig = server.Handler._roster_build
        server.Handler._roster_build = lambda self, *a, **k: calls.append(1) or orig(self, *a, **k)
        try:
            server._ROSTER_CACHE.clear()
            paging.invalidate()
            self.page()
            n = len(calls)
            b = self.page(tier="Micro")
            self.page(cursor=b.get("cursor") or "", tier="Micro")
            self.page(q="test")
            self.c.get("/api/roster/facets")
            self.c.get("/api/roster/cards?codes=HV-TS-001")
            self.assertEqual(len(calls), n)         # batches, filters and facets never rebuild the roster
        finally:
            server.Handler._roster_build = orig

    # --------------------------------------------------------------------- tour --
    def test_10_tour_demo_answers_the_new_endpoints(self):
        js = (ROOT / "assets" / "js" / "tour.js").read_text()
        for path in ('"/api/roster/page"', '"/api/roster/facets"', '"/api/roster/cards"'):
            self.assertIn("p === " + path, js)
        cat = (ROOT / "assets" / "js" / "catalogue.js").read_text()
        for path in ("/api/roster/page", "/api/roster/facets", "/api/roster/cards"):
            self.assertIn(path, cat)
        self.assertNotIn('"/api/roster?link=', cat)            # the page never asks for the whole roster


if __name__ == "__main__":
    unittest.main(verbosity=2)
