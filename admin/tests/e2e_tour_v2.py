"""End-to-end tests for the HELVY Connect onboarding tour v2 (branch tour-v2) and its leftovers:

- the tour reward through the real server: offered / started / later / done, +5 once,
  replays pay nothing, signed-out calls refused;
- the tour's contract with the pages: tour.js / tour.css are separate files fetched only on
  start, versioned inside connect.js and stamped by update.sh; hv-loader.js (the first
  script on every page) hands a demo frame to the tour before any page script runs; the
  demo world answers every /api/ call, keeps storage in memory and calls nothing but
  POST /api/tour itself;
- the demo world is fictional: eight AI-generated demo photos, demo codes only, no real
  creator code, handle or profile link; the copy never states a roster total;
- the journey: 7 stops in 4 chapters (Brief Helvy, Build your shortlist, Check & book,
  Track results), the opener says "Take the 3-minute tour?";
- Helvy: the "stamp" clip is gone, "approve" is registered in HVHelvy and used by every
  desk sequence; the admin copilot launcher uses the same config (data-helvy-only);
- the sign-in code email uses the transparent smile still (PNG with alpha);
- the old 10.6 MB hero-reel.mp4 is out of the repo and nothing points at it;
- every client page still loads hv-loader.js first.

Same harness as e2e_portal.py (a throwaway copy of admin/*.py, an empty database, captured
mail, a scripted Gemini), so it never touches catalogue.db or the network. The tour's
on-screen behaviour (each stop on the real pages, desktop and phone) is checked in a
browser; see docs/PORTAL.md.

    python3 admin/tests/e2e_tour_v2.py
"""
import re
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402  (copies admin/*.py to a temp dir and puts it on the path)
from e2e_portal import Client  # noqa: E402

import db, gemini, guard, knowledge, mailer, portal, selstatus, server, ui, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
JS = REPO / "assets" / "js"
CSS = REPO / "assets" / "css"


def read(p):
    return (REPO / p).read_text(encoding="utf-8")


class TourV2(unittest.TestCase):
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
        for ch in ("Brief Helvy", "Build your shortlist", "Check & book", "Track results"):
            self.assertIn('"%s"' % ch, self.connect, ch)
            self.assertIn('"%s"' % ch, self.tour, ch)
        self.assertNotIn("2-minute", self.connect + self.tour)
        self.assertIn("3-minute tour", knowledge.__file__ and Path(knowledge.__file__).read_text())
        # 7 stops, in the customer's order
        stops = re.findall(r'\{ ch: (\d), name: "([^"]+)"', self.tour)
        self.assertEqual([s[1] for s in stops], ["Tell Helvy your campaign", "Browse and filter to add more", "Review your shortlist",
                                                 "Unlock the full analysis", "Request a quote", "Track your campaign live", "Where everything lives"])
        self.assertEqual([int(s[0]) for s in stops], [0, 1, 1, 2, 2, 3, 3])
        for words in ("within 1 working day", "updates every 24 hours", "Replay any time from", "+5", "30 credits"):
            self.assertIn(words, self.tour, words)

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
        # the tour itself talks to the server about one thing only: the tour state
        calls = re.findall(r'api\("(GET|POST)", "([^"]+)"', self.tour)
        self.assertTrue(calls)
        self.assertEqual({p for _, p in calls}, {"/api/tour"})
        self.assertNotIn("XMLHttpRequest", self.tour)
        # portal.js runs the chat in the demo frame only, and the demo hooks exist only there
        portal_js = read("assets/js/portal.js")
        self.assertIn("(window.self !== window.top && !window.hvDemo)", portal_js)
        self.assertIn("if (window.hvDemo) {\n      HV.voiceDemo", portal_js)
        self.assertIn("if (window.hvDemo) HV.aiDemo", portal_js)

    def test_05_demo_data_is_fictional(self):
        photos = sorted((REPO / "assets" / "demo").glob("demo-*.webp"))
        self.assertEqual([p.name for p in photos], ["demo-%d.webp" % i for i in range(1, 9)])
        for p in photos:
            self.assertLess(p.stat().st_size, 120_000, p.name)
            self.assertEqual(p.read_bytes()[8:12], b"WEBP", p.name)
        self.assertIsNone(re.search(r"HV-[A-Z]{2}-\d{3}", self.tour))          # no real creator code
        self.assertNotRegex(self.tour, r"instagram\.com|tiktok\.com|snapchat\.com|youtube\.com")   # no real profile link
        codes = set(re.findall(r'"(DEMO-\d\d)"', self.tour))
        self.assertEqual(codes, {"DEMO-0%d" % i for i in range(1, 9)})
        self.assertIn('"Northwind Pharma"', self.tour); self.assertIn('"Ramadan Skincare"', self.tour)
        # never a roster total on screen: the demo roster is its 8 people, and no copy counts the roster
        self.assertNotRegex(self.tour, r"\d[\d,]* (vetted )?creators (in|on) (the|our) (roster|catalogue)")
        # Helvy never quotes a price in the chat
        self.assertIn("Creator prices come in your quote, never in the chat.", self.tour)

    # --------------------------------------------------------------- Helvy --
    def test_06_helvy_approve_replaces_stamp_everywhere(self):
        helvy = REPO / "assets" / "brand" / "helvy"
        for ext in ("webm", "mov"):
            self.assertTrue((helvy / ("helvy-approve." + ext)).is_file(), ext)
            self.assertFalse((helvy / ("helvy-stamp." + ext)).exists(), ext)
        self.assertIn("cards: 1, approve: 1 }", self.loader)
        every = "".join(read("assets/js/" + f) for f in ("portal.js", "connect.js", "tour.js", "catalogue.js", "account.js", "hv-loader.js"))
        self.assertNotIn('"stamp"', every)
        self.assertEqual(every.count('["thinking", "cards", "approve"]'), 2)   # HV.cooking + the AI shortlist card
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
