"""End-to-end tests for HELVY Connect phase E (branch phase-e):

- brief from a link or a file: the filled brief comes back for review (nothing saved),
  5 credits, free with an active campaign, refunded on an AI failure, nothing charged
  when the source cannot be read; SSRF blocked through the API; oversized bodies
  refused unread; invented claims dropped; regulated products flagged; works without
  Gemini (free keyword fill);
- the timing advisor in the brief result and on its own route;
- content ideas per creator: 2 credits, kept so reopening is free, "again" charges,
  no prices, only for creators in the viewer's own selection;
- the weekly bell update and the "Next time" panel through the API, other clients refused;
- Helvy never quotes prices in any of it.

Same harness as e2e_portal.py (a throwaway copy of admin/*.py, an empty database,
captured mail, a scripted Gemini), so it never touches catalogue.db or the network.

    python3 admin/tests/e2e_portal_phase_e.py
"""
import base64
import http.server
import io
import json
import shutil
import socket
import sys
import threading
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402  (copies admin/*.py to a temp dir and puts it on the path)

import briefsrc, db, gemini, guard, inbox, mailer, portal, server, views, weekly  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

DAY = 86400
CALLS = []


def stub(body):
    """The base Gemini stub, plus the two phase E schemas."""
    gen = body.get("generationConfig", {})
    props = (gen.get("responseSchema") or {}).get("properties", {})
    text = body["contents"][-1]["parts"][0].get("text", "")
    if "claims" in props:
        CALLS.append("source")
        if "EXPLODE" in text:
            raise gemini.Upstream("boom")
        out = {"product": "GlowSun SPF50", "brand": "Glow", "category": ["skincare", "NOT-REAL"], "audience": "Women 25-34 with oily skin",
               "gender": "Women", "age": "25-34", "market": "SA", "markets": ["SA", "AE", "XX"], "goal": "awareness",
               "timing": "quarter", "launch": "2027-01", "platforms": ["Instagram"],
               "claims": ["Dermatologist-tested", "Cures acne in 3 days"], "regulated": "none",
               "confidence": {"product": "high", "category": "high", "audience": "medium", "market": "high", "goal": "low"}}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(out)}]}}], "usageMetadata": {"promptTokenCount": 900, "candidatesTokenCount": 200}}
    if "ideas" in props:
        CALLS.append("ideas")
        out = {"ideas": [
            {"format": "Reel", "hook_en": "My 7am routine, before the Riyadh sun", "concept_en": "Morning routine reel, SPF as the last step.",
             "hook_ar": "روتيني الصباحي قبل شمس الرياض", "concept_ar": "ريل للروتين الصباحي وواقي الشمس آخر خطوة."},
            {"format": "Story", "hook_en": "Only SAR 49 this week!", "concept_en": "Price push.", "hook_ar": "بـ٤٩ ريال فقط", "concept_ar": "عرض سعر."},
            {"format": "TikTok", "hook_en": "Three things I stopped doing to my skin", "concept_en": "List video ending on the sunscreen habit.",
             "hook_ar": "ثلاث أشياء وقفت أسويها لبشرتي", "concept_ar": "فيديو قائمة ينتهي بعادة واقي الشمس."}]}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(out, ensure_ascii=False)}]}}], "usageMetadata": {"promptTokenCount": 700, "candidatesTokenCount": 300}}
    return base.stub(body)


def docx(paragraphs):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", "<w:document><w:body>" + "".join(
            "<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % p for p in paragraphs) + "</w:body></w:document>")
    return buf.getvalue()


BRIEF = docx(["Campaign brief: GlowSun SPF50 by Glow", "A light sunscreen for women 25-34 with oily skin in Riyadh and Dubai.",
              "Dermatologist-tested. Launch January 2027. Goal: awareness on Instagram."])


class Page(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = (b"<html><head><title>GlowSun SPF50</title></head><body><h1>GlowSun SPF50</h1><p>Sunscreen for women in Riyadh. "
                b"Dermatologist-tested, launch in January. Instagram awareness campaign.</p></body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class PhaseE(unittest.TestCase):
    signup = base.Portal.signup

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        mailer.CAPTURE = True
        gemini.STUB = stub
        views.set_base("")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        # "brand.test" is a public product page served locally
        cls.site = ThreadingHTTPServer(("127.0.0.1", 0), Page)
        threading.Thread(target=cls.site.serve_forever, daemon=True).start()
        cls.site_port = cls.site.server_address[1]
        briefsrc.PORTS.add(cls.site_port)
        real = socket.getaddrinfo
        briefsrc.RESOLVE = lambda h, p, *a: [(2, 1, 6, "", ("127.0.0.1", p))] if h == "brand.test" else real(h, p, *a)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.site.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()
        mailer.OUTBOX.clear()
        briefsrc.TEST_ALLOW_IPS.clear()
        gemini.STUB = stub

    def credits(self, c):
        return c.get("/api/me")[1]["credits"]

    def upload(self, c, data=BRIEF, name="GlowSun brief.docx"):
        return c.post("/api/brief/source", {"file": {"name": name, "data": "data:application/octet-stream;base64," + base64.b64encode(data).decode()}})

    # ---------------------------------------------------- brief from a file --
    def test_01_file_fills_the_brief_for_review_and_costs_five(self):
        c, _ = self.signup("brief@glow-a.com")
        before = self.credits(c)
        with db.connect() as conn:
            briefs = conn.execute("SELECT COUNT(*) FROM briefs").fetchone()[0]
        s, b, _ = self.upload(c)
        self.assertEqual(s, 200, b)
        self.assertTrue(b["ai"])
        a = b["answers"]
        self.assertEqual((a["goal"], a["market"], a["category"], a["gender"], a["age"]), ("awareness", "SA", ["skincare"], "Women", "25-34"))
        self.assertIn("Product: GlowSun SPF50", a["notes"])
        self.assertIn("uploaded brief", a["notes"])
        self.assertEqual(b["fields"]["markets"], ["SA", "AE"])                   # unknown markets dropped
        self.assertEqual(b["claims"], ["Dermatologist-tested"])                  # the invented claim is gone
        self.assertEqual(b["confidence"]["timing"], "medium")
        self.assertEqual(b["confidence"]["goal"], "low")
        self.assertEqual(b["regulated"], "cosmetic")                              # sunscreen, found in the text
        self.assertEqual({f["kind"] for f in b["flags"]} >= {"claims", "licence"}, True)
        self.assertTrue(b["timing"]["windows"])
        self.assertEqual((b["spent"], self.credits(c)), (5, before - 5))
        self.assertEqual(b["source"]["kind"], "file")
        with db.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM briefs").fetchone()[0], briefs)     # nothing saved
            audit = conn.execute("SELECT detail FROM events WHERE kind = 'brief_source' ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIn("GlowSun brief.docx", audit["detail"])
        blob = json.dumps(b)
        for t in ("SAR", "price", " fee"):
            self.assertNotIn(t, blob)

    def test_02_unreadable_sources_cost_nothing(self):
        c, _ = self.signup("bad@glow-b.com")
        calls = len(CALLS)
        before = self.credits(c)
        for data, name, reason in ((b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 64, "old.doc", "doc"),
                                   (bytes(range(256)) * 10, "x.bin", "type"), (b"hi", "a.txt", "empty")):
            s, b, _ = self.upload(c, data, name)
            self.assertEqual((s, b["reason"]), (400, reason))
        for url in ("http://127.0.0.1:%d/admin" % self.httpd.server_address[1], "http://169.254.169.254/latest/meta-data/",
                    "file:///etc/passwd", "https://influencer-catalogue.hellovoice.co.uk/admin/api/me", "http://10.0.0.1/",
                    "http://[::1]/", "http://2130706433/"):
            s, b, _ = c.post("/api/brief/source", {"url": url})
            self.assertEqual(s, 400, url)
            self.assertIn(b["reason"], ("blocked", "scheme"), url)
        self.assertEqual(self.credits(c), before)
        self.assertEqual(len(CALLS), calls)                                       # the model was never called
        # a body over the cap is refused before it is read
        big = {"file": {"name": "big.pdf", "data": "A" * (briefsrc.MAX_FILE * 2)}}
        s, b, _ = c.post("/api/brief/source", big)
        self.assertEqual((s, b["reason"]), (413, "too_big"))

    def test_03_link_is_read_and_ai_failure_is_refunded(self):
        c, _ = self.signup("link@glow-c.com")
        briefsrc.TEST_ALLOW_IPS.add("127.0.0.1")
        before = self.credits(c)
        s, b, _ = c.post("/api/brief/source", {"url": "http://brand.test:%d/spf50" % self.site_port})
        self.assertEqual(s, 200, b)
        self.assertEqual(b["source"]["label"], "brand.test")
        self.assertIn("From brand.test", b["answers"]["notes"])
        self.assertEqual(self.credits(c), before - 5)
        s, b, _ = self.upload(c, docx(["EXPLODE this brief: a long enough text about a sunscreen for women in Riyadh."]))
        self.assertEqual(s, 502)
        self.assertEqual(self.credits(c), before - 5)                             # refunded

    def test_04_free_with_an_active_campaign_and_without_ai(self):
        c, _ = self.signup("free@glow-test.com")
        u = portal.user_by_email("free@glow-test.com")
        k = db.create_campaign("Live one", "Glow", u["code_id"])
        db.save_campaign(k, status="live", starts_at=db.now() - DAY, ends_at=db.now() + 20 * DAY)
        before = self.credits(c)
        s, b, _ = self.upload(c)
        self.assertEqual((s, b["spent"], b["free"]), (200, 0, True))
        self.assertEqual(self.credits(c), before)
        gemini.STUB = None
        saved = gemini.key
        gemini.key = lambda: ""
        try:
            s, b, _ = self.upload(c)
            self.assertEqual((s, b["ai"], b["spent"]), (200, False, 0))
            self.assertEqual(b["answers"]["market"], "SA")                       # "Riyadh" read for free
            self.assertIn("skincare", b["answers"]["category"])
        finally:
            gemini.key = saved

    def test_05_timing_in_the_brief_result_and_on_its_own(self):
        c, _ = self.signup("time@glow-e.com")
        s, b, _ = c.get("/api/timing?c=skincare&m=SA")
        self.assertEqual(s, 200)
        self.assertTrue(b["windows"])
        self.assertRegex(b["headline"], r" is (in \d+ weeks?|on now)")
        s, r, _ = c.post("/api/brief/run", {"answers": {"goal": "awareness", "platforms": ["Instagram"], "market": "SA", "category": ["skincare"]}})
        self.assertEqual(s, 200, r)
        self.assertIn("windows", r["timing"])
        self.assertEqual(Client_get_anon(self.base, "/api/timing?c=skincare")[0], 401)

    # ---------------------------------------------------- content ideas --
    def test_06_content_ideas(self):
        c, _ = self.signup("ideas@glow-f.com")
        s, sel, _ = c.post("/api/selection", {"name": "SPF creators", "codes": ["HV-MI-001", "HV-MI-002"]})
        tok = sel["token"]
        c.post("/api/brief/attach", {"token": tok, "answers": {"goal": "awareness", "platforms": ["Instagram"], "market": "SA", "category": ["skincare"]}})
        s, g, _ = c.get("/api/ideas?c=HV-MI-001&s=" + tok)
        self.assertEqual((s, g["ideas"], g["cost"]), (200, [], 2))
        before = self.credits(c)
        s, b, _ = c.post("/api/ideas", {"code": "HV-MI-001", "token": tok})
        self.assertEqual(s, 200, b)
        self.assertEqual(len(b["ideas"]), 2)                                      # the one with a price was dropped
        for i in b["ideas"]:
            self.assertTrue(i["hook_en"] and i["hook_ar"] and i["concept_en"] and i["concept_ar"])
            self.assertNotRegex(json.dumps(i, ensure_ascii=False), r"SAR|ريال|price")
        self.assertEqual(self.credits(c), before - 2)
        # reopening is free; the creator page sees the same ideas through the selection
        s, b2, _ = c.post("/api/ideas", {"code": "HV-MI-001", "token": tok})
        self.assertEqual((b2["kept"], b2["spent"]), (True, 0))
        s, g, _ = c.get("/api/ideas?c=HV-MI-001")
        self.assertEqual((len(g["ideas"]), g["selection"]["token"]), (2, tok))
        self.assertEqual(self.credits(c), before - 2)
        s, b3, _ = c.post("/api/ideas", {"code": "HV-MI-001", "token": tok, "again": True})
        self.assertEqual((b3["spent"], self.credits(c)), (2, before - 4))
        # not in this selection, or someone else's selection
        self.assertEqual(c.post("/api/ideas", {"code": "HV-MD-003", "token": tok})[0], 404)
        o, _ = self.signup("other@rival-test.com")
        self.assertEqual(o.post("/api/ideas", {"code": "HV-MI-001", "token": tok})[0], 404)
        self.assertEqual(o.get("/api/ideas?c=HV-MI-001&s=" + tok)[0], 404)
        # the creator page without a selection: the client's own scope
        s, b4, _ = o.post("/api/ideas", {"code": "HV-MI-005"})
        self.assertEqual((s, len(b4["ideas"])), (200, 2))
        self.assertEqual(o.post("/api/ideas", {"code": "NOPE-1"})[0], 404)

    def test_07_ideas_prompt_has_no_prices_and_locked_style_stays_out(self):
        seen = []
        def spy(body):
            seen.append(json.dumps(body, ensure_ascii=False))
            return stub(body)
        gemini.STUB = spy
        db.save_analysis("HV-MI-002", {"followers": 38000, "er": 4.1, "posts": [{"caption": "SECRET-CAPTION morning routine", "brand": "RivalBrand"}]},
                         platform="Instagram")
        c, _ = self.signup("spy@glow-g.com")
        s, sel, _ = c.post("/api/selection", {"name": "Spy", "codes": ["HV-MI-002"]})
        c.post("/api/ideas", {"code": "HV-MI-002", "token": sel["token"]})
        prompt = seen[-1]
        self.assertNotIn("SECRET-CAPTION", prompt)                                # locked analysis is not used
        self.assertNotRegex(prompt.split("SYSTEM")[0] if "SYSTEM" in prompt else prompt, r"price_from|1500|3000")
        import gating
        u = portal.user_by_email("spy@glow-g.com")
        with db.connect() as conn:
            conn.execute("INSERT INTO analysis_grants (code_id, code, granted_at, granted_by) VALUES (?,?,?,?)",
                         (u["code_id"], "HV-MI-002", db.now(), "test"))
        self.assertTrue(gating.unlocked(u["code_id"], "HV-MI-002"))
        c.post("/api/ideas", {"code": "HV-MI-002", "token": sel["token"], "again": True})
        self.assertIn("SECRET-CAPTION", seen[-1])                                 # unlocked: style is used

    # --------------------------------------------- weekly + next time --
    def test_08_weekly_bell_and_next_time_panel(self):
        c, _ = self.signup("camp@glow-h.com")
        u = portal.user_by_email("camp@glow-h.com")
        mailer.OUTBOX.clear()                                                     # the sign-in code
        k = db.create_campaign("Ramadan Glow", "Glow", u["code_id"], codes=["HV-MI-001", "HV-MI-002", "HV-MD-003"])
        db.save_campaign(k, status="live", starts_at=db.now() - 9 * DAY, ends_at=db.now() + 20 * DAY)
        db.set_planned(k, {"HV-MI-001": 2, "HV-MI-002": 2, "HV-MD-003": 2})
        for i, (code, v, l) in enumerate([("HV-MI-001", 30000, 2100), ("HV-MI-001", 28000, 1900), ("HV-MI-002", 9000, 120)]):
            db.add_content(k, {"url": "https://x/p/w%d" % i, "code": code, "platform": "Instagram", "kind": "reel", "views": v, "likes": l})
        weekly.tick()
        weekly.tick()
        s, n, _ = c.get("/api/notifications")
        weeklies = [x for x in n["items"] if x["kind"] == "camp_weekly"]
        self.assertEqual(len(weeklies), 1)
        self.assertEqual(len(weeklies[0]["body"].split("\n")), 3)
        self.assertEqual(mailer.OUTBOX, [])
        tok = db.campaign(k)["token"]
        s, p, _ = c.get("/api/campaign/next?t=" + tok)
        self.assertEqual((s, p["ended"], p["next"]), (200, False, None))
        db.save_campaign(k, status="ended")
        s, p, _ = c.get("/api/campaign/next?t=" + tok)
        self.assertTrue(p["ended"])
        nx = p["next"]
        self.assertEqual([x["code"] for x in nx["rebook"]][:1], ["HV-MI-001"])
        self.assertIn("HV-MD-003", [x["code"] for x in nx["replace"]])
        for x in nx.get("instead") or []:
            self.assertNotIn("price", json.dumps(x))
        s, n, _ = c.get("/api/notifications")
        self.assertEqual(len([x for x in n["items"] if x["kind"] == "camp_next"]), 1)
        o, _ = self.signup("nosy@rival-test.com")
        self.assertEqual(o.get("/api/campaign/next?t=" + tok)[0], 404)


def Client_get_anon(base_url, path):
    return base.Client(base_url).get(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
