"""The competitor study through a client link (item 303): the map reads, notes are written and read back,
"Ask HelloVoice" reaches the KAM, and the KAM hears once a day when the link is opened or its PDF saved.
All names below are invented.

    python3 admin/tests/e2e_study_link.py
"""
import json
import shutil
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402
import e2e_evidence as ev  # noqa: E402

import db, gemini, guard, mailer, portal, report_shares, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

KAM = "mariam.k@hvkam.com"


class StudyLink(unittest.TestCase):
    signup = base.Portal.signup
    admin = base.Portal.admin
    member = base.Portal.member

    @classmethod
    def setUpClass(cls):
        base.seed()
        import evidence
        evidence.init()
        report_shares.init()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        db.set_setting("notify_emails", ["team@hv.test"])
        db.set_setting("notify_events", ["signup", "creator_request"])   # a saved list from before the new events existed
        mailer.CAPTURE = True
        gemini.STUB = base.stub
        views.set_base("")
        db.set_setting("domain_kam", {"polyco.com": KAM})
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.ready = False

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()
        mailer.OUTBOX.clear()
        if not StudyLink.ready:
            W = StudyLink
            W.client, _ = self.signup("lead@polyco.com")
            W.mine = portal.user_by_email("lead@polyco.com")
            W.sel = db.save_selection(None, "Polyco glow", ["HV-MI-001", "HV-MI-005"], {}, None, None, code_id=W.mine["code_id"])
            W.token = db.selection(W.sel)["token"]
            self.member(KAM, "kam")
            a = self.admin()
            s, _ = ev.upload(a, "/evidence/import", {"title": "Polyco competitors", "code_id": W.mine["code_id"], "selection_id": W.sel}, ev.PACK)
            assert s == 303, s
            W.link = report_shares.create("study", W.token, title="Polyco glow", label="Polyco marketing", by="test")
            StudyLink.ready = True

    # anonymous browser holding only the link
    def call(self, method, path, body=None, link=True):
        url = self.base + path + (("&" if "?" in path else "?") + "r=" + self.link["token"] if link else "")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={"Origin": self.base, "Content-Type": "application/json"})
        try:
            r = urllib.request.urlopen(req)
        except urllib.error.HTTPError as exc:
            r = exc
        raw = r.read()
        try:
            return r.status if hasattr(r, "status") else r.code, json.loads(raw or b"{}")
        except ValueError:
            return r.status if hasattr(r, "status") else r.code, {}

    def mails(self, word):
        """The distinct messages (one per alert, whatever the number of recipients) that mention ``word``."""
        time.sleep(0.4)                                   # notify sends from a thread
        seen = {}
        for m in mailer.OUTBOX:
            if word in (m.get("text") or "") + (m.get("subject") or ""):
                seen.setdefault((m.get("subject"), m.get("text")), []).append(m.get("to"))
        return [{"to": to, "key": k} for k, to in seen.items()]

    def test_1_map_reads_through_the_link_only(self):
        s, b = self.call("GET", "/api/evidence/map?s=" + self.token)
        self.assertEqual(s, 200)
        m = b["map"]
        self.assertEqual(m["brand"], "Glow Serum")
        self.assertTrue(any(c["handle"] == "noha" for c in m["creators"]))
        self.assertTrue(all("url" in q for c in m["creators"] for q in c["posts"]))
        self.assertFalse(m["can_add"])
        self.assertEqual(self.call("GET", "/api/evidence/map?s=" + self.token, link=False)[0], 401)

    def test_2_notes_round_trip_and_tell_the_kam(self):
        s, b = self.call("GET", "/api/evidence/notes?s=" + self.token)
        self.assertEqual((s, b.get("notes")), (200, {}))
        s, b = self.call("POST", "/api/evidence/note", {"token": self.token, "handle": "@Noha", "note": "  Love her   tone  "})
        self.assertEqual(s, 200)
        self.assertEqual(b["note"]["t"], "Love her tone")
        self.assertEqual(b["note"]["by"], "Polyco marketing (study link)")
        got = self.mails("left a note on @noha")
        self.assertTrue(got, "the KAM is told of a client note")
        self.assertIn(KAM, json.dumps(got[0], default=str))
        s, b = self.call("GET", "/api/evidence/notes?s=" + self.token)
        self.assertEqual(b["notes"]["noha"][0]["t"], "Love her tone")
        # not a creator of the study, empty, or no link: refused
        self.assertEqual(self.call("POST", "/api/evidence/note", {"token": self.token, "handle": "nobody", "note": "x"})[0], 404)
        self.assertEqual(self.call("POST", "/api/evidence/note", {"token": self.token, "handle": "noha", "note": "   "})[0], 400)
        self.assertEqual(self.call("POST", "/api/evidence/note", {"token": self.token, "handle": "noha", "note": "x"}, link=False)[0], 401)
        self.assertEqual(self.call("GET", "/api/evidence/notes?s=" + self.token, link=False)[0], 401)

    def test_3_ask_hellovoice_from_the_link(self):
        s, b = self.call("POST", "/api/evidence/request", {"token": self.token, "handle": "noha", "kind": "book"})
        self.assertEqual(s, 200)
        got = self.mails("would like to book them")
        self.assertTrue(got)
        self.assertIn("Polyco marketing (competitor study link)", json.dumps(got[0], default=str))
        s, b = self.call("POST", "/api/evidence/request", {"token": self.token, "handle": "newface", "kind": "roster"})
        self.assertEqual(s, 200)
        self.assertEqual(self.call("POST", "/api/evidence/request", {"token": self.token, "handle": "noha", "kind": "book"}, link=False)[0], 401)

    def test_4_kam_hears_once_a_day_when_opened(self):
        s, b = self.call("GET", "/api/report?r=" + self.link["token"], link=False)
        self.assertEqual(s, 200)
        self.assertEqual(len(self.mails("opened the competitor study link")), 1)
        mailer.OUTBOX.clear()
        self.call("GET", "/api/report?r=" + self.link["token"], link=False)
        self.assertEqual(self.mails("opened the competitor study link"), [], "one alert a day")
        self.call("GET", "/api/report?r=" + self.link["token"] + "&peek=1", link=False)
        self.assertEqual(self.mails("competitor study"), [], "the page's own peek is not an open")

    def test_5_pdf_ping_once_a_day(self):
        self.assertEqual(self.call("POST", "/api/report/ping", {"what": "pdf"})[0], 200)
        self.assertEqual(len(self.mails("saved the PDF of")), 1)
        mailer.OUTBOX.clear()
        self.assertEqual(self.call("POST", "/api/report/ping", {"what": "pdf"})[0], 200)
        self.assertEqual(self.mails("saved the PDF of"), [])
        self.assertEqual(self.call("POST", "/api/report/ping", {"what": "pdf"}, link=False)[0], 404)

    def test_6_revoked_link_stops_everything(self):
        other = report_shares.create("study", self.token, title="Polyco glow", label="Gone", by="test")
        report_shares.revoke(other["id"], by="test")
        keep = StudyLink.link
        StudyLink.link = other
        try:
            self.assertEqual(self.call("GET", "/api/evidence/map?s=" + self.token)[0], 401)
            self.assertEqual(self.call("POST", "/api/evidence/note", {"token": self.token, "handle": "noha", "note": "x"})[0], 401)
        finally:
            StudyLink.link = keep


if __name__ == "__main__":
    unittest.main(verbosity=2)
