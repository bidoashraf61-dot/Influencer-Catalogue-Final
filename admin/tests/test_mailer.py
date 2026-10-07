"""Company-mailbox (SMTP) engine against a tiny local SMTP server. No network."""
import base64, shutil, socketserver, sys, tempfile, threading, unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="hv-mail-"))
for f in SRC.glob("*.py"):
    shutil.copy(f, TMP / f.name)
sys.path.insert(0, str(TMP))
import db, history, portal, mailer, gemini  # noqa: E402

GOT = []


class FakeSMTP(socketserver.StreamRequestHandler):
    def handle(self):
        w = lambda s: self.wfile.write((s + "\r\n").encode())
        w("220 fake ready")
        data, user, pw = None, None, None
        while True:
            line = self.rfile.readline().decode(errors="replace")
            if not line:
                return
            cmd = line.strip()
            if data is not None:
                if cmd == ".":
                    GOT.append({"user": user, "pw": pw, "msg": "\n".join(data)}); data = None; w("250 queued")
                else:
                    data.append(line.rstrip("\r\n"))
                continue
            u = cmd.upper()
            if u.startswith("EHLO"):
                self.wfile.write(b"250-fake\r\n250 AUTH LOGIN PLAIN\r\n")
            elif u.startswith("AUTH PLAIN"):
                parts = base64.b64decode(cmd.split()[2]).split(b"\0")
                user, pw = parts[1].decode(), parts[2].decode()
                w("235 ok" if pw == "right-pass" else "535 bad credentials")
            elif u.startswith(("MAIL", "RCPT", "RSET", "NOOP")):
                w("250 ok")
            elif u == "DATA":
                data = []; w("354 go")
            elif u == "QUIT":
                w("221 bye"); return
            else:
                w("502 no")


class Mailbox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init(); history.init(); portal.init()
        cls.srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), FakeSMTP)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.port = cls.srv.server_address[1]

    def test_sends_through_the_mailbox_as_that_mailbox(self):
        db.set_setting("mail_from", "HelloVoice <info@hellovoice.co.uk>")
        mailer.save_smtp("portal@hellovoice.co.uk", "right-pass", "127.0.0.1", self.port)
        self.assertEqual(mailer.engine(), "smtp")
        self.assertTrue(mailer.configured())
        subject, text, html = mailer.otp_message("123456")
        mailer.send("client@pfizer.com", subject, text, html)
        m = GOT[-1]
        self.assertEqual(m["user"], "portal@hellovoice.co.uk")
        self.assertIn("From: HelloVoice <portal@hellovoice.co.uk>", m["msg"])   # forced to the mailbox
        self.assertIn("To: client@pfizer.com", m["msg"])
        self.assertIn("123456", m["msg"])
        self.assertEqual(oct(mailer.SMTP_FILE.stat().st_mode)[-3:], "600")

    def test_wrong_password_is_a_clear_error(self):
        mailer.save_smtp("portal@hellovoice.co.uk", "wrong-pass", "127.0.0.1", self.port)
        with self.assertRaises(mailer.MailError) as cm:
            mailer.send("client@pfizer.com", "s", "t")
        self.assertIn("refused the sign-in", str(cm.exception))

    def test_no_encryption_no_password_for_remote_hosts(self):
        mailer.save_smtp("portal@hellovoice.co.uk", "right-pass", "localhost.invalid", self.port)
        with self.assertRaises(mailer.MailError):
            mailer.send("client@pfizer.com", "s", "t")

    def test_smtp_send_as_shared_mailbox(self):
        mailer.save_smtp("bido@hellovoice.co.uk", "right-pass", "127.0.0.1", self.port, send_as="info@hellovoice.co.uk")
        mailer.send("client@pfizer.com", "s", "t")
        self.assertEqual(GOT[-1]["user"], "bido@hellovoice.co.uk")
        self.assertIn("From: HelloVoice <info@hellovoice.co.uk>", GOT[-1]["msg"])
        mailer.clear_smtp()

    def test_graph_sends_as_shared_mailbox(self):
        calls = []
        def fake(url, data, headers, timeout=15):
            calls.append((url, data, headers))
            if "oauth2" in url:
                return 200, {"access_token": "tok-1", "expires_in": 3600}
            return 202, {}
        orig = mailer._graph_post
        mailer._graph_post = fake
        try:
            mailer.save_graph("1234abcd-1234-1234-1234-1234567890ab", "abcd1234-1234-1234-1234-1234567890ab",
                              "a-very-long-client-secret-value", "info@hellovoice.co.uk")
            self.assertEqual(mailer.engine(), "graph")
            subject, text, html = mailer.otp_message("654321")
            mailer.send("client@pfizer.com", subject, text, html)
            mailer.send("client2@pfizer.com", subject, text, html)
            self.assertEqual(sum(1 for c in calls if "oauth2" in c[0]), 1)         # token reused
            url, data, headers = calls[-1]
            self.assertIn("/users/info%40hellovoice.co.uk/sendMail", url)
            body = __import__("json").loads(data)
            self.assertEqual(body["message"]["toRecipients"][0]["emailAddress"]["address"], "client2@pfizer.com")
            self.assertIn("654321", body["message"]["body"]["content"])
            self.assertEqual(headers["Authorization"], "Bearer tok-1")
            self.assertEqual(oct(mailer.GRAPH_FILE.stat().st_mode)[-3:], "600")
            with self.assertRaises(ValueError):
                mailer.save_graph("not-a-tenant id", "x", "y", "z")
        finally:
            mailer._graph_post = orig
            mailer.clear_graph()

    def test_graph_permission_error_is_plain(self):
        import io, urllib.error
        def fake(url, data, headers, timeout=15):
            if "oauth2" in url:
                return 200, {"access_token": "tok", "expires_in": 3600}
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, io.BytesIO(b'{"error":{"code":"ErrorAccessDenied"}}'))
        orig = mailer._graph_post
        mailer._graph_post = fake
        try:
            mailer.save_graph("hellovoice.co.uk", "abcd1234-1234-1234-1234-1234567890ab", "a-very-long-client-secret-value", "info@hellovoice.co.uk")
            with self.assertRaises(mailer.MailError) as cm:
                mailer.send("c@pfizer.com", "s", "t")
            self.assertIn("Mail.Send", str(cm.exception))
        finally:
            mailer._graph_post = orig
            mailer.clear_graph()

    def test_ses_style_key_login(self):
        mailer.save_smtp("AKIAEXAMPLEKEY123", "right-pass", "127.0.0.1", self.port, send_as="info@hellovoice.co.uk")
        mailer.send("client@pfizer.com", "s", "t")
        self.assertEqual(GOT[-1]["user"], "AKIAEXAMPLEKEY123")                  # case kept
        self.assertIn("From: HelloVoice <info@hellovoice.co.uk>", GOT[-1]["msg"])
        with self.assertRaises(ValueError):
            mailer.save_smtp("AKIAEXAMPLEKEY123", "right-pass", "127.0.0.1", self.port)   # needs Send as
        mailer.clear_smtp()

    def test_validation_and_clear(self):
        with self.assertRaises(ValueError):
            mailer.save_smtp("not-an-email", "x")
        mailer.clear_smtp()
        self.assertIsNone(mailer.smtp_conf())


if __name__ == "__main__":
    unittest.main(verbosity=1)
