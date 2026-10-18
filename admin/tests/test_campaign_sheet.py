"""Campaign workbook: template -> fill -> parse (preview) -> apply.

    python3 admin/tests/test_campaign_sheet.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import threading, urllib.request, urllib.error, re  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402
import campaign_sheet, db, gemini, mailer, server, views, xlsx  # noqa: E402


def fill(campaign, creators):
    """The blank template with answers written in (column B / the Creators rows)."""
    sheets = xlsx.read_all(campaign_sheet.template())
    rows = [list(r) for r in sheets["Campaign"]]
    for r in rows[1:]:
        key = r[0].replace(" *", "")
        if key in campaign:
            r[1] = campaign[key]
    out = [("Campaign", rows, None, None),
           ("Creators", [sheets["Creators"][0]] + creators, None, None)]
    return xlsx.write_book(out)


GOOD = {"Campaign name": "Sheet Test Wave", "Client (brand)": "SVR", "Campaign type": "Awareness, Traffic",
        "Platforms": "Instagram", "Industry": "Beauty & skincare", "First day": "2026-11-01", "Last day": "2026-11-30",
        "Client budget (SAR)": "50000", "Destination link": "https://svr.example.com/shop", "Hashtags": "#svr #suncare",
        "Mentions": "@svr_ksa"}


class Sheet(unittest.TestCase):
    admin = base.Portal.admin

    @classmethod
    def setUpClass(cls):
        base.seed()
        mailer.CAPTURE = True
        gemini.STUB = base.stub
        views.set_base("")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    def upload(self, c, path, fields, data=None):
        b = "----hvsheet"
        body = "".join('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (b, k, v) for k, v in fields.items()).encode()
        if data is not None:
            body += ('--%s\r\nContent-Disposition: form-data; name="sheet"; filename="c.xlsx"\r\nContent-Type: application/octet-stream\r\n\r\n' % b).encode() + data + b"\r\n"
        body += ("--%s--\r\n" % b).encode()
        req = urllib.request.Request(c.base + path, data=body, method="POST",
                                     headers={"Origin": c.base, "Content-Type": "multipart/form-data; boundary=" + b})
        try:
            r = c.op.open(req)
        except urllib.error.HTTPError as exc:
            r = exc
        return r.status if hasattr(r, "status") else r.code, r.read().decode("utf-8", "replace"), r

    def test_01_template_has_the_sheets_and_fields(self):
        book = xlsx.read_all(campaign_sheet.template())
        self.assertEqual(list(book), list(campaign_sheet.SHEETS))
        labels = [r[0] for r in book["Campaign"][1:]]
        self.assertIn("Campaign name *", labels)
        self.assertIn("Destination link", labels)

    def test_02_good_sheet_previews_with_targets_and_writes_nothing(self):
        code = db.list_creators()[0]["code"]
        before = len(db.list_campaigns())
        got = campaign_sheet.parse(fill(GOOD, [[code, "2", "1500", "", ""], ["@brand_new_one", "1", "", "30000", "Instagram"]]))
        self.assertEqual(got["errors"], [])
        self.assertEqual(got["campaign"]["goals"], ["awareness", "traffic"])
        self.assertEqual(got["creators"][0]["code"], code)
        self.assertIsNone(got["creators"][1]["code"])
        self.assertTrue(got["targets"]["target"].get("views"))
        self.assertTrue(any("roster" in w for w in got["warnings"]))
        self.assertEqual(len(db.list_campaigns()), before)

    def test_03_problems_are_all_listed(self):
        got = campaign_sheet.parse(fill({"Campaign name": "", "Campaign type": "Fame", "Platforms": "Facebook",
                                          "First day": "soon", "Destination link": "svr.com"}, []))
        text = " ".join(got["errors"])
        for needle in ("name", "Campaign type", "Platforms", "not a date", "Destination", "at least one creator"):
            self.assertIn(needle, text)
        self.assertIsNone(got["targets"])

    def test_04_apply_creates_the_campaign_creators_links_and_targets(self):
        code = db.list_creators()[0]["code"]
        got = campaign_sheet.parse(fill(GOOD, [[code, "2", "1500", "", ""]]))
        cid, notes = campaign_sheet.apply(got, "tester")
        k = db.campaign(cid)
        self.assertEqual((k["name"], k["status"], k["platform"]), ("Sheet Test Wave", "draft", "Instagram"))
        self.assertEqual(k["objective"], "awareness+traffic")
        self.assertTrue(k["destination"].startswith("https://svr"))
        members = db.campaign_creators(cid)
        self.assertEqual([m["cc_code"] for m in members], [code])
        self.assertEqual((members[0]["planned"], members[0]["campaign_cost"]), (2, 1500))
        import json
        self.assertTrue(json.loads(k["targets"]).get("views"))
        self.assertIn("#svr", json.loads(k["rules"])["hashtags"])
        self.assertTrue(notes)

    def test_05_admin_download_preview_confirm(self):
        a = self.admin()
        s, raw, r = a.get("/campaigns/template.xlsx")
        self.assertEqual(s, 200)
        s, page, _ = a.get("/campaigns")
        self.assertEqual(s, 200)
        self.assertIn("Download template", page)
        code = db.list_creators()[0]["code"]
        before = len(db.list_campaigns())
        s, html, _ = self.upload(a, "/campaigns/import", {}, fill(GOOD, [[code, "1", "", "", ""]]))
        self.assertEqual(s, 200)
        self.assertIn("Create the campaign", html)
        self.assertEqual(len(db.list_campaigns()), before)                      # preview writes nothing
        token = re.search(r"name='token' value='([^']+)'", html).group(1)
        s, _, r = self.upload(a, "/campaigns/import/confirm", {"token": token})
        self.assertEqual(s, 303)
        self.assertEqual(len(db.list_campaigns()), before + 1)
        self.assertIn("/campaigns/edit?id=", r.headers["Location"])
        s, _, r = self.upload(a, "/campaigns/import/confirm", {"token": token})   # a token works once
        self.assertEqual(s, 303)
        self.assertEqual(len(db.list_campaigns()), before + 1)
        bad = fill({"Campaign name": ""}, [])
        s, html, _ = self.upload(a, "/campaigns/import", {}, bad)
        self.assertIn("Fix these first", html)
        self.assertNotIn("Create the campaign", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
