"""End-to-end tests for the HELVY Connect onboarding tour v3 (branch tour-v3, item 40) and its leftovers.

The tour is ONE CLIENT'S FIRST CAMPAIGN, from brief to results, played on the real portal pages in a
frame on an invented demo roster. This suite checks, without a browser:

- the tour reward through the real server: offered / started / later / done, +5 once, replays pay
  nothing, signed-out calls refused (and the tour never adds credits itself);
- the tour's contract with the pages: tour.js / tour.css are separate files fetched only on start,
  versioned inside connect.js and stamped by update.sh; hv-loader.js (the first script on every page)
  hands a demo frame to the tour before any page script runs; the demo answers every /api/ call,
  keeps storage in memory, answers the quote form's mail endpoint itself, and the tour talks to the
  server about the tour state only (plus one GET of the static roster file);
- the demo world is fictional: eight invented creators, demo codes only, names from one invented
  list, no handle or profile link of a real account, nothing read from the catalogue database or the
  private catalogue file (so the public repo carries no creator data), the committed roster file is
  what tools/gen_demo_roster.py writes;
- the story: seven chapters in the customer's order, every step's target exists in the page that
  draws it (checked against the page sources), the opener lists the same chapters;
- the demo API answers every endpoint the steps use with the LIVE response shapes (the tour's own
  JavaScript is run under node and compared with the server's real answers);
- Helvy, the sign-in email and the leftovers of v2.

Same harness as e2e_portal.py (a throwaway copy of admin/*.py, an empty database, captured mail, a
scripted Gemini), so it never touches catalogue.db or the network. The tour's on-screen behaviour (each
step on the real pages, desktop and phone) is walked in a browser: admin/tests/tour_walk.mjs.

    python3 admin/tests/e2e_tour_v3.py
"""
import json
import re
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402  (copies admin/*.py to a temp dir and puts it on the path)
from e2e_portal import Client  # noqa: E402

import benchmarks, db, gemini, guard, knowledge, lifecycle, mailer, matcher, plans, portal, roi, sample_analysis, selstatus, server, ui, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402
from unittest import mock  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
JS = REPO / "assets" / "js"
CSS = REPO / "assets" / "css"
CHAPTERS = ["Brief", "Shortlist", "Check a creator", "Plan", "Ask Helvy", "Quote", "Follow"]


def read(p):
    return (REPO / p).read_text(encoding="utf-8")


def skeleton(v):
    """The shape of a JSON value: dicts by key, lists by the union of their items, scalars by kind."""
    if isinstance(v, dict):
        return {k: skeleton(x) for k, x in v.items()}
    if isinstance(v, list):
        out = None
        for x in v:
            sk = skeleton(x)
            if out is None:
                out = sk
            elif isinstance(out, dict) and isinstance(sk, dict):
                out = dict(sk, **out)
        return [out] if out is not None else []
    if v is None:
        return "null"
    return {bool: "bool", int: "num", float: "num", str: "str"}.get(type(v), "other")


def keys_of(sk, path=""):
    """Every key path of a skeleton ('a.b', lists as 'a[].b')."""
    out = set()
    if isinstance(sk, dict):
        for k, v in sk.items():
            out.add(path + k)
            out |= keys_of(v, path + k + ".")
    elif isinstance(sk, list) and sk:
        out |= keys_of(sk[0], path[:-1] + "[]." if path.endswith(".") else path + "[].")
    return out


class TourV3(unittest.TestCase):
    signup = base.Portal.signup
    admin = base.Portal.admin

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        mailer.CAPTURE = True
        gemini.STUB = base.stub
        views.set_base("")
        selstatus.EMAIL_DELAY = 0
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.tour = read("assets/js/tour.js")
        cls.connect = read("assets/js/connect.js")
        cls.loader = read("assets/js/hv-loader.js")

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()
        mailer.OUTBOX.clear()

    # ------------------------------------------------------------ the reward --
    def test_01_reward_once_through_the_server(self):
        c, _ = self.signup("tour2@northwind-test.com")
        cid = portal.user_by_email("tour2@northwind-test.com")["code_id"]
        self.assertIsNone(c.get("/api/me")[1]["tour"])
        for action in ("offered", "started"):
            self.assertEqual(c.post("/api/tour", {"action": action})[0], 200)
        before = portal.balance(cid)
        r = c.post("/api/tour", {"action": "done"})[1]
        self.assertTrue(r["ok"]); self.assertEqual(r["earned"], 5); self.assertEqual(r["credits"], before + 5)
        r = c.post("/api/tour", {"action": "done"})[1]                         # replay
        self.assertEqual(r["earned"], 0); self.assertEqual(portal.balance(cid), before + 5)
        self.assertEqual(c.post("/api/tour", {"action": "later"})[1]["tour"], "done")   # skipping a replay keeps "done"
        self.assertEqual(c.get("/api/me")[1]["tour"], "done")                  # the opener is never offered again
        self.assertEqual(Client(self.base).post("/api/tour", {"action": "done"})[0], 401)

    # ------------------------------------------------- loading and versioning --
    def test_02_tour_loads_only_on_start_and_is_versioned(self):
        self.assertTrue((JS / "tour.js").is_file()); self.assertTrue((CSS / "tour.css").is_file())
        # connect.js names both with a ?v= that update.sh rewrites to the files' hash
        self.assertRegex(self.connect, r'"assets/js/tour\.js\?v=[0-9a-z]+"')
        self.assertRegex(self.connect, r'"assets/css/tour\.css\?v=[0-9a-z]+"')
        upd = read("deploy/catalogue/update.sh")
        self.assertIn("'js/tour.js', 'css/tour.css'", upd)
        self.assertLess(upd.index("js/tour.js"), upd.index("names = ("))       # stamped before connect.js is hashed
        # no page names the tour: it is fetched by connect.js when a client starts it
        for page in ("index.html", "selection/index.html", "creator/index.html", "campaign/index.html", "account/index.html"):
            self.assertNotIn("tour.js", read(page), page)
        self.assertNotIn("tour.js", read("build/influencer_catalogue.py"))
        # HV.tour(chapter) jumps; HV.tour(true) from the menu starts at the beginning
        self.assertIn('typeof chapter === "number" ? chapter : null', self.connect)

    def test_03_opener_copy_and_chapters(self):
        self.assertIn('"Take the ", h("span", { class: "cx-nowrap" }, "3-minute"), " tour?"', self.connect)
        self.assertNotIn("2-minute", self.connect + self.tour)
        self.assertIn("3-minute tour", Path(knowledge.__file__).read_text())
        # the opener (connect.js) and the tour (tour.js) name the same seven chapters, in the story's order
        opener = re.search(r"var CHAPTERS = \[(.*?)\];", self.connect, re.S).group(1)
        self.assertEqual(re.findall(r'\["[a-z]+", "([^"]+)"', opener), CHAPTERS)
        inner = re.search(r"var CHAPTERS = \[(.*?)\];\n  // A query per view", self.tour, re.S).group(1)
        self.assertEqual(re.findall(r'\["([^"]+)", "[a-z]+", "', inner), CHAPTERS)
        stops = re.findall(r'\{ ch: (\d), name: "([^"]+)"', self.tour)
        self.assertEqual([s[1] for s in stops], CHAPTERS)
        self.assertEqual([int(s[0]) for s in stops], list(range(7)))
        # about three minutes: one sentence per step, short and skippable
        steps = re.findall(r'\bt: "([^"]+)", p: "([^"]+)"', self.tour)
        self.assertTrue(18 <= len(steps) <= 26, len(steps))
        for t, p in steps:
            self.assertLessEqual(len(p), 110, p)             # one sentence
            self.assertEqual(p.count(". ") + p.count("? "), 0, p)
        self.assertIn("Skip tour", self.tour)
        self.assertIn("role: \"progressbar\"", self.tour)    # the progress indicator
        # the walkthrough the owner asked for, in order
        order = ["aiAsk0", "aiAsk2", "aiGo", "scoreTip", "sampleHover", "sampleOpen", "roiOpen", "roiCount", "roiQuality", "roiWays",
                 "chat:Why did", "chat:Compare", "chat:Can you", "quoteOpen", "quoteSend", "lcReady", "lcApprove", "tab:overview"]
        at = [self.tour.index('run: "%s' % r) for r in order]
        self.assertEqual(at, sorted(at))
        self.assertIn("refreshed every 24 hours", self.tour)
        self.assertIn("Replay any time from", self.tour)
        self.assertIn('"+5"', self.tour)

    # ------------------------------------------------------------ the demo world --
    def test_04_frame_handover_happens_first_and_only_for_the_tour(self):
        # hv-loader.js is the first script on every page and installs the demo before anything else runs
        i = self.loader.index("top_.hvTourDemo.install(window)")
        self.assertLess(i, self.loader.index("var HELVY = window.HVHelvy"))
        self.assertIn("top_ !== window && top_.hvTourDemo && top_.hvTourDemo.active", self.loader)
        self.assertIn("if (DEMO) ready = true; else arm(T0);", self.loader)
        # the shim: every /api/ call answered in the frame, storage and cookies in memory, no outside link
        for needle in ('/\\/api\\//.test(url)', 'Object.defineProperty(win, "localStorage"', 'Object.defineProperty(win, "sessionStorage"',
                       'Object.defineProperty(win.document, "cookie"', "win.open = function () { return null; };", "to.origin !== win.location.origin"):
            self.assertIn(needle, self.tour, needle)
        # the quote form also posts to a mail endpoint on another site: answered in the frame, never sent
        self.assertIn("to.origin !== win.location.origin) return Promise.resolve(json(win, { success:", self.tour)
        # the tour itself talks to the server about one thing only: the tour state (and the static roster file)
        calls = re.findall(r'api\("(GET|POST)", "([^"]+)"', self.tour)
        self.assertTrue(calls)
        self.assertEqual({p for _, p in calls}, {"/api/tour"})
        self.assertEqual(re.findall(r'fetch\(ROOT \+ "([^"]+)"', self.tour), ["assets/demo/demo-roster.json"])
        self.assertNotIn("XMLHttpRequest", self.tour)
        # portal.js runs the chat in the demo frame only, and the demo hooks exist only there
        portal_js = read("assets/js/portal.js")
        self.assertIn("(window.self !== window.top && !window.hvDemo)", portal_js)
        self.assertIn("if (window.hvDemo) {\n      HV.voiceDemo", portal_js)
        self.assertIn("if (window.hvDemo) HV.aiDemo = function (ans, name, opts)", portal_js)

    def test_05_demo_data_is_fictional(self):
        photos = sorted((REPO / "assets" / "demo").glob("demo-*.webp"))
        self.assertEqual([p.name for p in photos], ["demo-%d.webp" % i for i in range(1, 9)])
        for p in photos:
            self.assertLess(p.stat().st_size, 120_000, p.name)
            self.assertEqual(p.read_bytes()[8:12], b"WEBP", p.name)
        # (a) the roster: every name from the invented list, demo codes only, handles that are not links
        gen = read("tools/gen_demo_roster.py")
        invented = re.search(r"INVENTED_NAMES = \((.*?)\)", gen, re.S).group(1)
        invented = set(re.findall(r'"([^"]+)"', invented))
        doc = json.loads(read("assets/demo/demo-roster.json"))
        self.assertEqual(set(doc["invented_names"]), invented)
        self.assertEqual(len(doc["people"]), 8)
        for p in doc["people"]:
            self.assertIn(p["name"], invented)
            self.assertRegex(p["code"], r"^DEMO-0[1-8]$")
            self.assertNotRegex(p["handle"], r"https?:|\.com|\.co|@|/")
            self.assertIn(p["photo"], range(1, 9))
        self.assertNotRegex(json.dumps(doc), r"instagram\.com|tiktok\.com|snapchat\.com|youtube\.com|HV-[A-Z]{2}-\d{3}")
        # ... and it is what the generator writes (the file is reviewable and cannot drift)
        r = subprocess.run([sys.executable, str(REPO / "tools" / "gen_demo_roster.py"), "--check"], capture_output=True)
        self.assertEqual(r.returncode, 0, "assets/demo/demo-roster.json is out of date: run python3 tools/gen_demo_roster.py")
        # no private data is read: not by the generator, not by the tour, and nothing of the private
        # catalogue appears in the roster when that file is present on this machine
        for text in (gen, self.tour):
            self.assertNotRegex(text, r"catalogue_private|catalogue\.db|sqlite3|\.photo-secret|\.secret\b")
        self.assertNotRegex(gen, r"\bopen\(|json\.load|\.glob\(|os\.walk|import (sqlite3|db)\b")
        private = REPO / "content" / "catalogue_private.json"
        if private.exists():
            blob = private.read_text(encoding="utf-8").lower()
            for p in doc["people"]:
                self.assertNotIn(p["handle"].lower(), blob)
                self.assertNotIn(p["name"].lower(), blob)
        self.assertIsNone(re.search(r"HV-[A-Z]{2}-\d{3}", self.tour))          # no real creator code
        self.assertNotRegex(self.tour, r"instagram\.com|tiktok\.com|snapchat\.com|youtube\.com")   # no real profile link
        self.assertIn('"Northwind Pharma"', self.tour); self.assertIn('"Ramadan Skincare"', self.tour)
        # never a roster total on screen: the demo roster is its 8 people, and no copy counts the roster
        self.assertNotRegex(self.tour, r"\d[\d,]* (vetted )?creators (in|on) (the|our) (roster|catalogue)")
        # Helvy never quotes a price in the chat
        for text in self.demo()["chat"]["hand"] + self.demo()["chat"]["explain"] + self.demo()["chat"]["compare"]:
            self.assertNotRegex(json.dumps(text), r"SAR\s*\d|\bCPM\b|\bAED\s*\d")

    # ---------------------------------------------------- every step's target --
    def test_06_every_steps_target_exists_in_the_page_that_draws_it(self):
        pages = "".join(read(f) for f in ("assets/js/catalogue.js", "assets/js/portal.js", "assets/js/connect.js", "assets/js/creator.js",
                                         "assets/js/campaign.js", "assets/js/account.js", "build/influencer_catalogue.py",
                                         "creator/index.html", "campaign/index.html", "account/index.html", "campaign/dashboard/index.html"))
        roster = json.loads(read("assets/demo/demo-roster.json"))
        codes = {p["code"] for p in roster["people"]}
        sels = set(re.findall(r'(?:target|also|alt): "([^"]+)"', self.tour))
        sels |= set(re.findall(r'(?:querySelector(?:All)?|press|waitFor)\(\s*"([^"]+)"', self.tour))
        sels |= {"#" + i for i in re.findall(r'getElementById\("([^"]+)"\)', self.tour)}
        self.assertGreater(len(sels), 25)
        # the tour's own targets that are not the page's: the HV panel and the tour's chrome
        own = {"#hv-panel", "#hv-bell", "#hv-bell-drop", "#hv-panel:not([hidden])", "#pt-menu", "#pt-avatar"}
        missing = []
        for sel in sorted(sels):
            for kind, name in re.findall(r"([#.])([A-Za-z_][\w-]*)", re.sub(r"\[[^\]]*\]", "", sel)):
                if name.startswith("tv-") or "#" + name in own:        # the tour's own chrome, not the page's
                    continue
                if name not in pages:
                    missing.append((sel, name))
            for c in re.findall(r"data-code='([^']+)'", sel):
                self.assertIn(c, codes, sel)
        self.assertEqual(missing, [], "tour targets the pages never draw")
        # the demo codes the steps use are the roster's
        self.assertTrue(set(re.findall(r'"(DEMO-\d\d)"', self.tour)) <= codes)
        self.assertTrue(set(re.findall(r"'(DEMO-\d\d)'", self.tour)) <= codes)
        # every page the story visits is a page the demo knows how to load and wait for
        views_used = set(re.findall(r'view: "([a-z]+)"', self.tour))
        self.assertEqual(views_used, {"catalogue", "selection", "creator", "campaign", "account"})
        for v in views_used:
            self.assertRegex(self.tour, r"\b%s: \"[^\"]+\"\s*[,}]" % v)

    # ------------------------------------------------ the demo API, live shapes --
    _dump = None

    def demo(self):
        """What the tour's demo answers to every endpoint a step uses, from running tour.js under node."""
        if TourV3._dump is None:
            node = shutil.which("node")
            if not node:
                self.skipTest("node is not installed")
            r = subprocess.run([node, str(REPO / "admin" / "tests" / "tour_demo_dump.js"), str(REPO)], capture_output=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr.decode()[:2000])
            TourV3._dump = json.loads(r.stdout.decode())
        return TourV3._dump

    def _estimate_fixture(self):
        def cr(code, fol, platform="Instagram", score=None):
            return {"code": code, "name": code, "followers": {platform: fol}, "docs": {}, "scores": {platform: score} if score is not None else {}}
        with mock.patch.object(db, "setting", lambda key, default=None: default), mock.patch.object(plans, "house_benchmarks", lambda: {}):
            benchmarks.SOURCE = lambda: []
            benchmarks.invalidate()
            return roi.full("awareness", ["Instagram", "TikTok"], creators=[cr("A", 612000, score=91), cr("B", 273000, score=88), cr("C", 188000, score=79)],
                            goals=["awareness", "engagement"], count=15)

    def test_07_demo_roi_answers_in_the_live_shape(self):
        d = self.demo()
        real = self._estimate_fixture()
        self.assertTrue(real["ways"], "the fixture should have ways to compare")
        for name in ("estimate", "estimateCount", "estimateSingle"):
            got = d[name]["result"]
            self.assertEqual(d[name]["ok"], True)
            self.assertEqual(set(got), set(real), name)                         # quality / ideal / gap / ways / count_range ...
            for k in ("selection", "ideal", "quality", "count_range", "trust"):
                self.assertEqual(set(got[k]), set(real[k]), "%s.%s" % (name, k))
            self.assertEqual(set(got["quality"]), set(real["quality"]))        # pct, low, high, band, met, overlap, text, by_goal
            self.assertLessEqual(set(got["quality"]["by_goal"]), {"awareness", "engagement", "traffic"})
            self.assertEqual(set(got["ideal"]["by_size"][0]), set(real["ideal"]["by_size"][0]))
            self.assertEqual(set(got["figures"][0]) - {"unit"}, set(real["figures"][0]) - {"unit"})
        full = d["estimateCount"]["result"]
        self.assertEqual(full["count"], 15)                                       # the client chose how many
        self.assertEqual(full["ideal"]["creators"], 15)
        self.assertEqual(full["count_range"]["text"], "14–28")                    # the usual range for these two goals
        self.assertEqual(set(full["quality"]["by_goal"]), {"awareness", "engagement"})   # each goal beside the average
        self.assertTrue(full["gap"] and full["ways"] and len(full["ways"]) <= 3)
        for w in full["ways"]:
            self.assertEqual(set(w), {"id", "text", "gain", "points", "action"})
            self.assertIn(w["action"]["type"], ("replace", "remove", "add", "second_post", "add_platform", "use_mix"))
        # a mix of sizes: nothing chosen, so no quality, and a way to use the recommended mix
        mix = d["estimateMix"]["result"]
        self.assertEqual(set(mix), set(real))
        # no budget, price, CPM, market anywhere in what the calculator returns
        blob = json.dumps(d["estimate"]) + json.dumps(d["estimateCount"]) + json.dumps(d["estimateMix"])
        for word in ('"cpm"', '"cpe"', '"cpc"', '"budget"', '"price"', '"market"', '"cost"', "SAR "):
            self.assertNotIn(word, blob)
        # saved estimate against actual: the same rows the report reads
        self.assertEqual(set(d["roiVs"]["items"][0]), {"campaign", "token", "saved_at", "ended", "rows", "helvy"})
        self.assertEqual(set(d["roiVs"]["items"][0]["rows"][0]), {"key", "label", "estimate", "range", "actual", "position", "sig", "delta"})

    def test_08_demo_lifecycle_sample_and_chat_in_the_live_shape(self):
        d = self.demo()
        # lifecycle: the six steps with the server's keys, owner can approve only when the quote is ready
        sel = {"id": 987654, "name": "Shape", "code_id": None, "request_id": None, "created_at": 1}
        real = lifecycle.client_payload(sel, "owner")
        for k, lc in d["lifecycle"].items():
            self.assertEqual(set(lc), set(real), k)
            self.assertEqual(set(lc["steps"][0]), set(real["steps"][0]), k)
            self.assertEqual([s["key"] for s in lc["steps"]], list(lifecycle.STATES))
            self.assertEqual(lc["label"], lifecycle.LABEL[k])
            self.assertEqual(lc["can_approve"], k == "ready")
        self.assertEqual([s["state"] for s in d["lifecycle"]["approved"]["steps"]], ["done", "done", "done", "current", "todo", "todo"])
        self.assertEqual(d["lifecycle"]["live"]["campaign"]["token"], "demo-ramadan-live")
        self.assertEqual(d["approve"]["lifecycle"]["key"], "approved")
        # the anonymised sample full analysis: only what sample_analysis.anonymise() would copy
        full = {k: 1.5 for k in sample_analysis.NUMBERS}
        full.update({"updated": "2026-10-01", "account_type": "Creator", "likes_hidden": False,
                     "fake_followers_dist": {"buckets": [{"label": "5%", "h": 3}], "creator": 1, "median": 2},
                     "er_dist": {"buckets": [{"label": "5%", "h": 3}], "creator": 1, "median": 2},
                     "growth": [{"month": "2026-09", "followers": 1, "avg_likes": 1}],
                     "audience": {"gender": {"female": 1, "male": 2}, "countries": [{"code": "SA", "pct": 1}]},
                     "audience_likers": {}, "top_posts": [{"likes": 1}], "sponsored_posts": [{"brand": "x", "likes": 1}],
                     "brands": [{"name": "y", "count": 1}], "hashtags": [{"tag": "#a", "count": 1}], "creator_interests": ["Beauty"]})
        allowed = set(sample_analysis.anonymise(full, "Instagram"))
        s = d["sample"]
        self.assertEqual(set(s), {"ok", "sample", "label", "creator", "platforms", "analyses", "requested", "gate", "benchmarks"})
        self.assertEqual(s["label"], sample_analysis.LABEL)
        self.assertEqual(s["creator"]["name"], "Sample creator")
        self.assertIsNone(s["creator"]["photo_url"])
        for a in s["analyses"].values():
            self.assertLessEqual(set(a), allowed)
            for sec in ("top_posts", "sponsored_posts"):
                for post in a[sec]:
                    self.assertIsNone(post["thumb"]); self.assertEqual(post["url"], "#demo-post")
            self.assertNotRegex(json.dumps(a), r"\bhandle\b|\bbio\b|photo_url|DEMO-0|Velora|Sahar|Dune|Oasis")
        # the locked profile offers the sample button and keeps its sections locked
        locked = d["creatorLocked"]
        self.assertEqual(locked["gate"]["state"], "locked")
        self.assertTrue(locked["gate"]["sample_full"])
        self.assertEqual(locked["analyses"], {})
        self.assertEqual(set(locked["gate"]["headline"]), {"followers", "platforms", "avg_views", "er", "er_platform", "er_followers", "updated"})
        self.assertEqual(d["creatorOpen"]["gate"]["state"], "unlocked")
        # chat: step* delta* done; a hand-off carries no price; the working note lines are plain actions
        for name, events in d["chat"].items():
            kinds = [e["t"] for e in events]
            self.assertEqual(kinds[0], "step", name)
            self.assertEqual(kinds[-1], "done", name)
            self.assertLessEqual(set(kinds), {"step", "delta", "done"})
            self.assertLessEqual(set(events[-1]), {"t", "thread", "reply", "credits", "roi", "breakdown", "actions", "cards", "handoff", "next"}, name)
            for e in events:
                if e["t"] == "step":
                    self.assertNotRegex(e["text"], r"\d|_")
        self.assertEqual(d["chat"]["hand"][-1]["handoff"], {"reason": "pricing"})
        self.assertTrue(d["chat"]["find"][-1]["cards"])
        self.assertEqual(set(d["chat"]["find"][-1]["cards"][0]), {"code", "name", "photo_url", "fit", "followers", "city", "tier"})
        self.assertEqual(set(d["handoff"]), {"ok", "message"})
        self.assertEqual(set(d["voiceSelection"]), {"ok", "token", "name", "count", "brief", "quote", "objective", "scores", "details"})

    def test_09_demo_pages_in_the_live_shape(self):
        d = self.demo()
        # the brief questions are the server's own, word for word
        self.assertEqual(d["questions"]["questions"], json.loads(json.dumps(matcher.public_questions())))
        goal = d["questions"]["questions"][0]
        self.assertTrue(goal["multi_ok"])                                          # several goals
        self.assertTrue(next(q for q in d["questions"]["questions"] if q["id"] == "market")["multi_ok"])   # several countries
        # the live server, for the shapes the demo must match
        c, _ = self.signup("shapes@northwind-test.com")
        _, me, _ = c.get("/api/me")
        self.assertLessEqual(set(d["me"]), set(me))
        s, b, _ = c.post("/api/selection", {"name": "Shapes", "codes": ["HV-MI-001", "HV-MI-002", "HV-MD-003"]})
        tok = b["token"]
        _, live, _ = c.get("/api/selection?s=" + tok)
        demo_sel = d["selection"]
        self.assertEqual(set(demo_sel) - {"needs_objective"}, set(live) - {"needs_objective"})
        self.assertEqual(set(demo_sel["lifecycle"]), set(live["lifecycle"]))
        # a score, as the selection page and its tooltip read it
        first = next(iter(demo_sel["scores"].values()))
        self.assertEqual(set(first), {"score", "tag", "strengths", "watchouts", "conclusion", "parts", "platform", "objective", "basic", "checks",
                                      "confidence", "reach_followers", "limited_data", "assigned", "available", "platforms"})
        self.assertEqual(set(first["confidence"]), {"level", "posts", "peers_n", "source"})
        self.assertIn(first["confidence"]["level"], ("high", "medium", "low"))
        self.assertTrue(any(x["limited_data"] for x in demo_sel["scores"].values()))      # "limited data" is on show
        # the roster rows, the profile and the account page
        _, roster, _ = c.get("/api/roster")
        self.assertEqual(set(d["roster"]["roster"][0]), set(roster["roster"][0]))
        _, creator, _ = c.get("/api/creator?c=HV-MI-001")
        self.assertEqual(set(d["creatorLocked"]), set(creator))
        _, acc, _ = c.get("/api/account")
        self.assertEqual(set(d["account"]), set(acc))
        for k in ("user", "completion", "invite", "next", "insights", "notifications"):
            self.assertEqual(set(d["account"][k]), set(acc[k]), k)
        self.assertEqual(set(d["account"]["selections"][0]), set(acc["selections"][0]))
        self.assertEqual(set(d["account"]["briefs"][0]), {"id", "can_delete", "summary", "objective", "source", "at", "selection", "selection_name"})
        # the AI shortlist's answer
        _, run, _ = c.post("/api/brief/run", {"answers": {"goal": ["awareness", "engagement"], "platforms": ["Instagram"], "market": ["SA"], "category": ["skincare"]}})
        if run.get("ok") and run.get("picks"):
            self.assertLessEqual(set(run), set(d["briefRun"]) | {"empty", "message"} | set(run))
            for k in ("ok", "picks", "platform_scores", "credits", "brief"):
                self.assertIn(k, d["briefRun"])
            self.assertLessEqual(set(d["briefRun"]["picks"][0]), set(run["picks"][0]))
        # the campaign report is unchanged since v2: its top-level report keys
        self.assertEqual(set(d["campaign"]["report"]) >= {"campaign", "total", "creators", "posts", "verdict", "progress", "clicks"}, True)

    def test_10_reward_is_the_servers_and_once(self):
        # the tour never adds credits itself: it shows what POST /api/tour {done} answered, and only a
        # first finish says "earned"; a replay says so and pays nothing (the server test is test_01)
        self.assertIn('api("POST", "/api/tour", { action: "done" })', self.tour)
        self.assertIn("HV.setCredits(r.b.credits)", self.tour)
        self.assertIn("if (r.b.earned)", self.tour)
        self.assertEqual(self.tour.count("HV.setCredits("), 1)
        self.assertNotRegex(self.tour, r"credits\s*\+=|credits\s*=\s*\d+\s*\+")
        c, _ = self.signup("once@northwind-test.com")
        cid = portal.user_by_email("once@northwind-test.com")["code_id"]
        first = c.post("/api/tour", {"action": "done"})[1]
        second = c.post("/api/tour", {"action": "done"})[1]
        third = c.post("/api/tour", {"action": "done"})[1]
        self.assertEqual((first["earned"], second["earned"], third["earned"]), (5, 0, 0))
        self.assertEqual(portal.balance(cid), first["credits"])

    # --------------------------------------------------------------- Helvy --
    def test_06_helvy_approve_replaces_stamp_everywhere(self):
        helvy = REPO / "assets" / "brand" / "helvy"
        for ext in ("webm", "mov"):
            self.assertTrue((helvy / ("helvy-approve." + ext)).is_file(), ext)
            self.assertFalse((helvy / ("helvy-stamp." + ext)).exists(), ext)
        self.assertIn("cards: 1, approve: 1 }", self.loader)
        every = "".join(read("assets/js/" + f) for f in ("portal.js", "connect.js", "tour.js", "catalogue.js", "account.js", "hv-loader.js"))
        self.assertNotIn('"stamp"', every)
        self.assertEqual(every.count('["thinking", "cards", "approve"]'), 1)   # HV.cooking (COOK_SEQ), the one definition
        # fix batch 4: the AI shortlist card's wait is Helvy's camera scan on lime again
        self.assertIn('appendChild(lime("scan"))', every)
        self.assertIn("Approving your picks…", every)
        # the admin copilot launcher: the same HVHelvy config, Helvy only, no old clips
        self.assertIn('data-helvy-only', ui._VOICE_LAUNCHER)
        self.assertIn("/assets/js/hv-loader.js?v=" + ui.HELVY_VER, ui._VOICE_LAUNCHER)
        self.assertIn('VER = "?v=%s"' % ui.HELVY_VER, self.loader)
        self.assertNotIn("/assets/brand/voice/", ui._VOICE_LAUNCHER + ui._JS_VOICE)
        self.assertIn('HVHelvy.video(\'idle\'', ui._JS_VOICE)
        self.assertIn('if (me && me.hasAttribute("data-helvy-only")) return;', self.loader)
        a = self.admin()
        s, body, _ = a.get("/portal?tab=codes")
        self.assertEqual(s, 200)
        self.assertIn("data-helvy-only", body)
        self.assertIn("Ask Helvy", body)

    # ----------------------------------------------------------- leftovers --
    def test_07_sign_in_email_uses_the_transparent_still(self):
        subject, text, html = mailer.otp_message("482913", 10, to="sara@northwind-test.com")
        self.assertIn('src="https://influencer-catalogue.hellovoice.co.uk/assets/brand/email/helvy-still-192.png"', html)
        self.assertNotIn("helvy-smile-240.png", html)
        self.assertNotIn("border-radius:46px", html)                          # no disc
        png = (REPO / "assets/brand/email/helvy-still-192.png").read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(png[25], 6)                                           # colour type 6: RGBA, transparent

    def test_08_old_hero_reel_is_gone(self):
        self.assertFalse((REPO / "assets/video/hero-reel.mp4").exists())
        for p in ("build/influencer_catalogue.py", "build/catalogue_dist.py", "index.html", "deploy/catalogue/update.sh"):
            self.assertIsNone(re.search(r"hero-reel\.mp4", read(p)), p)
        self.assertTrue((REPO / "assets/video/hero-reel-720.mp4").is_file())

    def test_09_every_page_loads_hv_loader_first(self):
        # index.html and selection/index.html in the repo are an old static build; the live ones
        # come from build/influencer_catalogue.py (checked through its <head> templates).
        pages = {p: read(p) for p in ("creator/index.html", "campaign/index.html", "campaign/dashboard/index.html",
                                      "account/index.html", "privacy/index.html", "terms/index.html")}
        build = read("build/influencer_catalogue.py")
        for tmpl in re.findall(r"<head>.*?</head>", build, re.S):
            pages["build:" + str(len(pages))] = tmpl
        for name, html in pages.items():
            scripts = re.findall(r"<script[^>]*\bsrc=\"([^\"]+)\"", html)
            if not scripts:
                continue
            self.assertIn("hv-loader.js", scripts[0], name)

    def test_10_nudge_and_phone_header(self):
        css = read("assets/css/connect.css")
        nudge = re.search(r"\.hv-nudge b \{[^}]*\}", css).group(0)
        self.assertIn("color: var(--ink)", nudge)                              # was lime on white
        portal_css = read("assets/css/portal.css")
        self.assertIn(".cat-topbar .pt-dock { position: static;", portal_css)  # no longer floats over the pill
        self.assertNotIn(".cat-topbar .pt-dock { position: absolute;", portal_css)


if __name__ == "__main__":
    unittest.main(verbosity=1)
