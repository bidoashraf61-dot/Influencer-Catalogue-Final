"""Unit tests for phase E's campaign jobs (admin/weekly.py):

- the weekly bell update: one per campaign-week however many ticks run, none before the
  first full week, none without posts, none for drafts / ended / unassigned campaigns,
  three lines with the verdict, never an email;
- "what to do next time": rebook / replace / watch from results, benchmarks and delivery,
  one bell when the campaign ends (by status or by date), stable on re-runs, no prices.

A throwaway database; never the network.

    python3 admin/tests/test_weekly.py
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="hv-weekly-"))
db.DB_PATH = TMP / "t.db"
import history  # noqa: E402
import inbox  # noqa: E402
import mailer  # noqa: E402
import portal  # noqa: E402
import weekly  # noqa: E402

DAY = 86400
CREATORS = [("HV-MI-001", "Noha Magdy", 42000), ("HV-MI-002", "Sara Ali", 38000), ("HV-MI-003", "Omar T", 31000),
            ("HV-MI-004", "Lama K", 29000), ("HV-MI-005", "Huda S", 45000), ("HV-MI-006", "Reem A", 40000)]


def setUpModule():
    db.init()
    history.init()
    portal.init()
    db.save_tier("Micro", "MI", 1500, 3000, reach="10-50K")
    for code, name, fol in CREATORS:
        db.upsert_creator({"code": code, "name": name, "handle": code.lower(), "platform": "Instagram", "followers": fol,
                           "city": "Riyadh", "nationality": "Saudi Arabia", "tier": "Micro", "interest": "Skincare, Beauty",
                           "photo": None, "profiles": json.dumps([{"platform": "Instagram", "url": "https://x/" + code, "followers": fol}]),
                           "active": 1, "note": "", "sort": 0})
    mailer.CAPTURE = True


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def account(email):
    portal.create_user(email, "Test Person", "Brand Co")
    return portal.user_by_email(email)


def campaign(user, name, started_days_ago=10, length=28, status="live", codes=None, planned=None):
    codes = codes or [c[0] for c in CREATORS[:3]]
    k = db.create_campaign(name, "Brand Co", user["code_id"] if user else None, codes=codes)
    now = db.now()
    db.save_campaign(k, status=status, starts_at=now - started_days_ago * DAY, ends_at=now - started_days_ago * DAY + length * DAY)
    if planned:
        db.set_planned(k, planned)
    return k


def post(k, code, n, views, likes, comments=10):
    db.add_content(k, {"url": "https://x/p/%s-%d-%d" % (code, k, n), "code": code, "platform": "Instagram", "kind": "reel",
                       "views": views, "likes": likes, "comments": comments})


def bell(user, kind):
    return [n for n in inbox.feed(user, 100, bell=False) if n["kind"] == kind]


class Weekly(unittest.TestCase):
    def test_one_update_per_week_however_many_ticks(self):
        u = account("weekly@brand-a.com")
        k = campaign(u, "Ramadan Glow", started_days_ago=9)
        post(k, "HV-MI-001", 1, 20000, 1100)
        post(k, "HV-MI-002", 1, 9000, 300)
        mailer.OUTBOX.clear()
        for _ in range(4):
            weekly.tick()
        notes = bell(u, "camp_weekly")
        self.assertEqual(len(notes), 1)
        n = notes[0]
        self.assertTrue(n["title"].startswith("Ramadan Glow: "), n["title"])
        lines = n["body"].split("\n")
        self.assertEqual(len(lines), 3, lines)
        self.assertIn("2 posts live", lines[2])
        self.assertIn("Noha Magdy", lines[2])                       # the leader
        self.assertEqual(n["href"], "campaign/#t=" + db.campaign(k)["token"])
        self.assertEqual(n["group"], "campaigns")
        self.assertEqual(mailer.OUTBOX, [])                         # bell only, never an email
        for t in ("SAR", "price", "fee", "cost"):
            self.assertNotIn(t, n["title"] + n["body"])
        # next week: one more; the week after that is not here yet
        weekly.tick(now=db.now() + 7 * DAY)
        weekly.tick(now=db.now() + 7 * DAY + 3600)
        self.assertEqual(len(bell(u, "camp_weekly")), 2)
        with db.connect() as conn:
            weeks = [r[0] for r in conn.execute("SELECT week FROM campaign_weekly WHERE campaign_id = ? ORDER BY week", (k,))]
        self.assertEqual(weeks, ["1", "2"])

    def test_no_update_before_a_full_week_without_posts_or_for_the_wrong_campaigns(self):
        u = account("quiet@brand-b.com")
        young = campaign(u, "Too young", started_days_ago=3)
        post(young, "HV-MI-001", 1, 5000, 200)
        empty = campaign(u, "No posts yet", started_days_ago=12)
        draft = campaign(u, "Draft one", started_days_ago=12, status="draft")
        post(draft, "HV-MI-001", 1, 5000, 200)
        nobody = campaign(None, "Unassigned", started_days_ago=12)
        post(nobody, "HV-MI-001", 1, 5000, 200)
        weekly.tick()
        self.assertEqual(bell(u, "camp_weekly"), [])
        # posts arrive later in the week: the update goes out then, once
        post(empty, "HV-MI-002", 1, 7000, 300)
        weekly.tick()
        weekly.tick()
        notes = bell(u, "camp_weekly")
        self.assertEqual([n["title"].split(":")[0] for n in notes], ["No posts yet"])

    def test_teammates_get_it_too(self):
        u = account("lead@brand-c.com")
        mate = account("mate@brand-c.com")
        k = campaign(u, "Team camp", started_days_ago=8)
        post(k, "HV-MI-003", 1, 4000, 100)
        weekly.tick()
        self.assertEqual(len(bell(mate, "camp_weekly")), 1)


class NextTime(unittest.TestCase):
    def test_rebook_replace_watch(self):
        # six creators, two posts planned each: two stars, two middling, one weak, one no-show
        u = account("next@brand-d.com")
        codes = [c[0] for c in CREATORS]
        k = campaign(u, "Summer SPF", started_days_ago=40, length=30, codes=codes, planned={c: 2 for c in codes})
        posts = {"HV-MI-001": [(60000, 3600), (52000, 3000)], "HV-MI-002": [(45000, 2500), (40000, 2300)],
                 "HV-MI-003": [(20000, 700), (18000, 650)], "HV-MI-004": [(15000, 520), (14000, 500)],
                 "HV-MI-005": [(9000, 90), (8000, 70)]}                       # HV-MI-006 never posted
        for code, items in posts.items():
            for i, (v, l) in enumerate(items):
                post(k, code, i, v, l, comments=5)
        weekly.tick()
        data = weekly.panel(db.campaign(k))
        groups = {g: [x["code"] for x in data[g]] for g in ("rebook", "replace", "watch")}
        self.assertEqual(groups["rebook"][:2], ["HV-MI-001", "HV-MI-002"])
        self.assertIn("HV-MI-006", groups["replace"])
        self.assertIn("HV-MI-005", groups["replace"])
        self.assertTrue(set(groups["watch"]) <= {"HV-MI-003", "HV-MI-004"})
        six = next(x for x in data["replace"] if x["code"] == "HV-MI-006")
        self.assertEqual(six["lead"], "No posts delivered")
        self.assertIn("delivered 0 of 2 posts", six["why"])
        one = data["rebook"][0]
        self.assertTrue(any(w.startswith("#1 of 5") for w in one["why"]), one["why"])
        self.assertTrue(data["summary"].startswith("Book Noha Magdy"), data["summary"])
        blob = json.dumps(data)
        for t in ("SAR", "price", "fee", "cost"):
            self.assertNotIn(t, blob)
        # one bell, however many ticks; the panel stays the same
        weekly.tick()
        weekly.tick()
        notes = bell(u, "camp_next")
        self.assertEqual(len(notes), 1)
        self.assertIn("Rebook 2, replace 2", notes[0]["body"])
        self.assertEqual(weekly.panel(db.campaign(k))["summary"], data["summary"])

    def test_marking_ended_rings_at_once_and_a_live_campaign_has_no_panel(self):
        u = account("ended@brand-e.com")
        k = campaign(u, "Founding Day", started_days_ago=5, length=30)
        post(k, "HV-MI-001", 1, 30000, 2000)
        self.assertIsNone(weekly.panel(db.campaign(k)))
        db.save_campaign(k, status="ended")                     # the admin marks it final
        self.assertEqual(len(bell(u, "camp_next")), 1)
        self.assertIsNotNone(weekly.panel(db.campaign(k)))
        weekly.tick()
        self.assertEqual(len(bell(u, "camp_next")), 1)

    def test_an_old_campaign_gets_the_panel_without_a_bell(self):
        u = account("old@brand-g.com")
        k = campaign(u, "Last year", started_days_ago=120, length=30, status="ended")
        post(k, "HV-MI-001", 1, 30000, 2000)
        with db.connect() as conn:
            conn.execute("DELETE FROM campaign_next WHERE campaign_id = ?", (k,))
            conn.execute("DELETE FROM notifications WHERE kind = 'camp_next'")
        weekly.tick()
        self.assertIsNotNone(weekly.panel(db.campaign(k)))
        self.assertEqual(bell(u, "camp_next"), [])

    def test_no_results_no_panel(self):
        u = account("none@brand-f.com")
        k = campaign(u, "Nothing posted", started_days_ago=40, length=30)
        weekly.tick()
        self.assertIsNone(weekly.panel(db.campaign(k)))
        self.assertEqual(bell(u, "camp_next"), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
