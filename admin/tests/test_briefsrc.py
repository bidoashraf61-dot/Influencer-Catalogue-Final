"""Unit tests for phase E's brief-from-a-link-or-file reader (admin/briefsrc.py) and the
timing advisor (occasions.advise).

- URL safety: schemes, credentials, ports, our own hosts, every private / loopback /
  link-local / CGNAT / mapped address, DNS answers that mix public and private
  addresses, redirects into the private network, size cap, timeouts, and that the
  connection goes to the checked address (no DNS rebinding);
- extraction: HTML (scripts dropped, meta and JSON-LD kept), DOCX, PDF (PyMuPDF when
  installed and the stdlib reader), old .doc, binary, empty, zip bombs;
- claims: only claims written in the source survive; regulated products are flagged.

A throwaway database (settings only) and a local HTTP server; never the network.

    python3 admin/tests/test_briefsrc.py
"""
import datetime
import http.server
import io
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
import zipfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="hv-briefsrc-"))
db.DB_PATH = TMP / "t.db"
db.init()
import briefsrc  # noqa: E402
import occasions  # noqa: E402

SEEN = {}


class Site(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        SEEN["host"] = self.headers.get("Host")
        p = self.path
        if p == "/page":
            body = (b"<html><head><title>GlowSun SPF50</title><meta name='description' content='Daily sunscreen for oily skin'>"
                    b"<script>alert('x'); var secret = 1;</script>"
                    b"<script type='application/ld+json'>{\"@type\":\"Product\",\"name\":\"GlowSun SPF50\",\"brand\":{\"name\":\"Glow\"}}</script>"
                    b"</head><body><nav>Menu Home Shop</nav><h1>GlowSun SPF50</h1><p>Light sunscreen for women 25-34 in Riyadh."
                    b" Dermatologist tested.</p><footer>Copyright</footer></body></html>")
            return self._send(200, body, "text/html; charset=utf-8")
        if p == "/huge":
            return self._send(200, b"<html><body><p>" + b"a" * (3 * 1024 * 1024) + b"</p></body></html>", "text/html")
        if p == "/bigpdf":
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(5 * 1024 * 1024))
            self.end_headers()
            self.wfile.write(b"%PDF-1.4\n" + b"0" * 1000)
            return
        if p.startswith("/to/"):
            self.send_response(302)
            self.send_header("Location", "http://" + p[4:] + "/")
            self.end_headers()
            return
        if p == "/loop":
            self.send_response(302)
            self.send_header("Location", "/loop")
            self.end_headers()
            return
        if p == "/slow":
            time.sleep(2.5)
            return self._send(200, b"<html><body>late</body></html>", "text/html")
        if p == "/private":
            return self._send(401, b"sign in", "text/plain")
        return self._send(404, b"no", "text/plain")

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def docx(paragraphs, bomb=False):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        xml = "<w:document><w:body>" + "".join("<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % p for p in paragraphs)
        if bomb:
            xml += "<w:p><w:r><w:t>" + "A" * (25 * 1024 * 1024) + "</w:t></w:r></w:p>"
        z.writestr("word/document.xml", xml + "</w:body></w:document>")
    return buf.getvalue()


def simple_pdf(text, compress=True):
    stream = ("BT /F1 12 Tf 72 720 Td (%s) Tj ET" % text).encode("latin-1")
    body = zlib.compress(stream) if compress else stream
    filt = b"/Filter /FlateDecode " if compress else b""
    return (b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            b"3 0 obj << /Type /Page /Parent 2 0 R /Contents 4 0 R /MediaBox [0 0 612 792] >> endobj\n"
            b"4 0 obj << " + filt + b"/Length " + str(len(body)).encode() + b" >>\nstream\n" + body + b"\nendstream endobj\n"
            b"trailer << /Root 1 0 R >>\n%%EOF")


class UrlSafety(unittest.TestCase):
    def reason(self, fn, *a):
        with self.assertRaises(briefsrc.SourceError) as cm:
            fn(*a)
        return cm.exception.reason

    def test_schemes_credentials_ports_and_our_hosts(self):
        for bad in ("ftp://brand.com/x", "file:///etc/passwd", "javascript:alert(1)", "gopher://x/", "data:text/html,hi"):
            self.assertEqual(self.reason(briefsrc.check_url, bad), "scheme", bad)
        for bad in ("http://user:pw@brand.com/", "https://brand.com@10.0.0.1/", "http://brand.com:8080/", "https://brand.com:22/",
                    "localhost:8900", "http://localhost/", "https://hellovoice.co.uk/x", "https://influencer-catalogue.hellovoice.co.uk/admin",
                    "https://HELLOVOICE.CO.UK./", "http://mail.eshteryexpress.com/", "http://metadata.google.internal/", "http://box.local/"):
            self.assertEqual(self.reason(briefsrc.check_url, bad), "blocked", bad)
        for bad in ("", "http://", "http://exa mple.com", "x" * 2100):
            self.assertIn(self.reason(briefsrc.check_url, bad), ("url",), bad)
        self.assertEqual(briefsrc.check_url("brand.com/product").geturl(), "https://brand.com/product")
        self.assertEqual(briefsrc.check_url("https://www.brand.com:443/p?q=1").hostname, "www.brand.com")

    def test_private_and_special_addresses_are_refused(self):
        for ip in ("127.0.0.1", "127.8.8.8", "10.1.2.3", "172.16.0.9", "172.18.0.240", "192.168.1.1", "169.254.169.254",
                   "100.64.0.1", "0.0.0.0", "224.0.0.1", "240.0.0.1", "255.255.255.255", "::1", "::", "fe80::1", "fd00::1",
                   "::ffff:127.0.0.1", "::ffff:10.0.0.1", "2002:7f00:1::1", "54.74.66.161"):
            self.assertFalse(briefsrc.public_ip(ip), ip)
        for ip in ("8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"):
            self.assertTrue(briefsrc.public_ip(ip), ip)
        db.set_setting("brief_fetch_block_ips", ["8.8.4.4"])
        self.assertFalse(briefsrc.public_ip("8.8.4.4"))

    def test_numeric_and_odd_ip_spellings_resolve_to_loopback_and_are_refused(self):
        for host in ("2130706433", "0x7f000001", "127.1", "localtest.invalid"):
            r = self.reason(briefsrc.resolve, host, 80)
            self.assertIn(r, ("blocked", "dns"), host)

    def test_a_dns_answer_with_any_private_address_is_refused(self):
        real = briefsrc.RESOLVE
        try:
            briefsrc.RESOLVE = lambda h, p, *a: [(2, 1, 6, "", ("93.184.216.34", p)), (2, 1, 6, "", ("10.0.0.5", p))]
            self.assertEqual(self.reason(briefsrc.resolve, "mixed.example", 443), "blocked")
            briefsrc.RESOLVE = lambda h, p, *a: [(2, 1, 6, "", ("93.184.216.34", p))]
            self.assertEqual(briefsrc.resolve("ok.example", 443), "93.184.216.34")
        finally:
            briefsrc.RESOLVE = real


class Fetching(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Site)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.port = cls.srv.server_address[1]
        cls.saved = (set(briefsrc.PORTS), briefsrc.RESOLVE, briefsrc.STEP_SECONDS)
        briefsrc.PORTS.add(cls.port)
        briefsrc.TEST_ALLOW_IPS.add("127.0.0.1")
        real = socket.getaddrinfo
        # brand.test is "a public site" that lives on the local test server
        briefsrc.RESOLVE = lambda h, p, *a: [(2, 1, 6, "", ("127.0.0.1", p))] if h == "brand.test" else real(h, p, *a)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        briefsrc.PORTS.clear()
        briefsrc.PORTS.update(cls.saved[0])
        briefsrc.RESOLVE, briefsrc.STEP_SECONDS = cls.saved[1], cls.saved[2]
        briefsrc.TEST_ALLOW_IPS.clear()

    def url(self, path):
        return "http://brand.test:%d%s" % (self.port, path)

    def test_reads_a_page_through_the_checked_address(self):
        got = briefsrc.from_url(self.url("/page"))
        self.assertEqual(SEEN["host"], "brand.test:%d" % self.port)        # Host is the name; the socket went to the checked IP
        self.assertIn("GlowSun SPF50", got["text"])
        self.assertIn("Daily sunscreen for oily skin", got["text"])
        self.assertIn("Brand: Glow", got["text"])
        self.assertNotIn("alert", got["text"])
        self.assertNotIn("Menu Home", got["text"])
        self.assertEqual((got["kind"], got["label"]), ("html", "brand.test"))

    def test_redirects_are_checked_at_every_hop(self):
        for target in ("10.0.0.1", "169.254.169.254", "192.168.0.1", "localhost"):   # 127.0.0.1 is the test site here
            with self.assertRaises(briefsrc.SourceError) as cm:
                briefsrc.fetch(self.url("/to/" + target))
            self.assertEqual(cm.exception.reason, "blocked", target)
        with self.assertRaises(briefsrc.SourceError) as cm:
            briefsrc.fetch(self.url("/loop"))
        self.assertEqual(cm.exception.reason, "redirects")

    def test_size_cap_status_and_timeout(self):
        got = briefsrc.fetch(self.url("/huge"))
        self.assertTrue(got["truncated"])
        self.assertEqual(len(got["data"]), briefsrc.MAX_BYTES)
        with self.assertRaises(briefsrc.SourceError) as cm:
            briefsrc.from_url(self.url("/bigpdf"))
        self.assertEqual(cm.exception.reason, "too_big")
        with self.assertRaises(briefsrc.SourceError) as cm:
            briefsrc.fetch(self.url("/private"))
        self.assertEqual(cm.exception.reason, "status")
        briefsrc.STEP_SECONDS = 1
        try:
            t = time.time()
            with self.assertRaises(briefsrc.SourceError) as cm:
                briefsrc.fetch(self.url("/slow"))
            self.assertEqual(cm.exception.reason, "connect")
            self.assertLess(time.time() - t, 2.4)
        finally:
            briefsrc.STEP_SECONDS = 8

    def test_the_local_server_itself_is_refused_without_the_test_allowance(self):
        briefsrc.TEST_ALLOW_IPS.clear()
        try:
            with self.assertRaises(briefsrc.SourceError) as cm:
                briefsrc.fetch(self.url("/page"))
            self.assertEqual(cm.exception.reason, "blocked")
        finally:
            briefsrc.TEST_ALLOW_IPS.add("127.0.0.1")


class Extraction(unittest.TestCase):
    def reason(self, data, name=""):
        with self.assertRaises(briefsrc.SourceError) as cm:
            briefsrc.from_file(name, data)
        return cm.exception.reason

    def test_docx(self):
        got = briefsrc.from_file("Brief.docx", docx(["Campaign brief for GlowSun &amp; friends",
                                                       "Audience: women 25-34 in Riyadh and Jeddah, launch March 2027."]))
        self.assertEqual(got["kind"], "docx")
        self.assertIn("GlowSun & friends", got["text"])
        self.assertIn("Jeddah", got["text"])

    def test_zip_bomb_old_doc_binary_and_empty(self):
        self.assertEqual(self.reason(docx(["x"], bomb=True), "b.docx"), "too_big")
        self.assertEqual(self.reason(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 100, "old.doc"), "doc")
        self.assertEqual(self.reason(bytes(range(256)) * 20, "x.bin"), "type")
        self.assertEqual(self.reason(b"hi", "short.txt"), "empty")
        self.assertEqual(self.reason(b"PK\x03\x04garbage", "x.docx"), "broken")

    def test_pdf_stdlib_reader(self):
        for compress in (True, False):
            txt = briefsrc.pdf_text_stdlib(simple_pdf("GlowSun SPF50 sunscreen launch for women in Riyadh (KSA)", compress))
            self.assertIn("GlowSun SPF50 sunscreen launch", txt)
        with self.assertRaises(briefsrc.SourceError):
            briefsrc.pdf_text_stdlib(b"%PDF-1.4\n/Encrypt 5 0 R\n" + b"0" * 100)

    def test_pdf_through_from_file(self):
        try:
            import fitz
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "Brief: GlowSun SPF50 sunscreen for women 25-34 in Riyadh. Launch in Ramadan 2027.")
            data = doc.tobytes()
        except Exception:
            data = simple_pdf("Brief: GlowSun SPF50 sunscreen for women 25-34 in Riyadh. Launch in Ramadan 2027.")
        got = briefsrc.from_file("brief.pdf", data)
        self.assertEqual(got["kind"], "pdf")
        self.assertIn("GlowSun SPF50", got["text"])

    def test_upload_decoding_caps_size(self):
        import base64
        self.assertEqual(briefsrc.decode_upload("data:application/pdf;base64," + base64.b64encode(b"hello").decode()), b"hello")
        with self.assertRaises(briefsrc.SourceError) as cm:
            briefsrc.decode_upload(base64.b64encode(b"x" * (briefsrc.MAX_FILE + 10)).decode())
        self.assertEqual(cm.exception.reason, "too_big")


class Claims(unittest.TestCase):
    def test_only_claims_written_in_the_source_survive(self):
        src = "GlowSun SPF50. Dermatologist-tested. Reduces dark spots in 4 weeks!"
        kept = briefsrc.keep_claims(["Dermatologist-tested", "reduces dark spots in 4 weeks", "Cures acne", "Clinically proven"], src)
        self.assertEqual(kept, ["Dermatologist-tested", "reduces dark spots in 4 weeks"])

    def test_regulated_detection(self):
        self.assertEqual(briefsrc.regulated_kind("Take 2 tablets of 500 mg daily", []), "medicine")
        self.assertEqual(briefsrc.regulated_kind("vitamin D supplement", []), "supplement")
        self.assertEqual(briefsrc.regulated_kind("a light sunscreen SPF 50", []), "cosmetic")
        self.assertEqual(briefsrc.regulated_kind("a new coffee", ["food"]), "none")
        self.assertEqual(briefsrc.regulated_kind("a new launch", ["health care"]), "medicine")


class Timing(unittest.TestCase):
    def test_derm_congress_cast_now(self):
        a = occasions.advise(["skincare"], "SA", None, "", today=datetime.date(2026, 10, 9))
        names = [w["name"] for w in a["windows"]]
        self.assertIn("Saudi Derm Congress", names)
        w = a["windows"][names.index("Saudi Derm Congress")]
        self.assertEqual(w["message"], "Saudi Derm Congress is in 14 weeks: cast now.")
        for w in a["windows"]:
            self.assertNotRegex(w["message"], r"SAR|price|fee|\$")

    def test_launch_date_pulls_windows_and_non_ksa_skips_saudi_days(self):
        a = occasions.advise(["food"], "SA", None, "2027-02", today=datetime.date(2026, 10, 9))
        self.assertIn(a["windows"][0]["name"], ("Ramadan", "Saudi Founding Day"))
        b = occasions.advise(["food"], "AE", None, "2027-02", today=datetime.date(2026, 10, 9))
        self.assertNotIn("Saudi Founding Day", [w["name"] for w in b["windows"]])

    def test_sector_first_then_soonest(self):
        a = occasions.advise(["skincare"], "SA", None, "", today=datetime.date(2026, 10, 9), limit=10)
        own = [occasions.SECTOR_OF["skincare"] in dict((c[0], c[5]) for c in occasions.CALENDAR)[w["name"]].split() for w in a["windows"]]
        self.assertEqual(own, sorted(own, reverse=True))           # every sector match before any general one
        k = own.count(True)
        for part in (a["windows"][:k], a["windows"][k:]):
            starts = [w["starts"] for w in part]
            self.assertEqual(starts, sorted(starts))                  # then the soonest first

    def test_too_close_is_left_out(self):
        a = occasions.advise(["health care"], "SA", None, "", today=datetime.date(2026, 11, 5))
        self.assertNotIn("World Diabetes Day", [w["name"] for w in a["windows"]])


if __name__ == "__main__":
    try:
        unittest.main(verbosity=1)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
