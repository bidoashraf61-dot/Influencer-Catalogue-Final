"""Control Centre step 1 (item 101): admins sign in with an emailed code, owners invite by email,
and risky actions ask for a fresh confirmation that can also be an emailed code.

    python3 admin/tests/e2e_admin_login.py
"""
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402
from e2e_portal import Client  # noqa: E402

import db, guard, mailer, portal, server, team, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


def last_code():
    return mailer.OUTBOX[-1]["text"].split("code is ")[1][:6]


class AdminLogin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base.seed()
        mailer.CAPTURE = True
        views.set_base("")
        portal.OTP_RESEND_SECONDS = 0
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()
        mailer.OUTBOX.clear()

    def email_in(self, email="boss@hellovoice.co.uk"):
        c = Client(self.base)
        s, _, _ = c.req("POST", "/login/email", form={"email": email})
        self.assertEqual(s, 303)
        return c

    def test_1_login_page_offers_email_code(self):
        s, body, _ = Client(self.base).get("/login")
        self.assertEqual(s, 200)
        self.assertIn("Email me a sign-in code", body)
        self.assertIn("Use a password instead", body)

    def test_2_email_code_signs_an_admin_in(self):
        c = self.email_in()
        self.assertEqual(len(mailer.OUTBOX), 1)
        s, _, r = c.req("POST", "/login/email/verify", form={"email": "boss@hellovoice.co.uk", "code": last_code()})
        self.assertEqual(s, 303)
        s, body, _ = c.get("/")
        self.assertEqual(s, 200)

    def test_3_unknown_email_gets_the_same_answer_and_no_mail(self):
        c = Client(self.base)
        s, _, r = c.req("POST", "/login/email", form={"email": "nobody@evil.com"})
        self.assertEqual(s, 303)
        self.assertIn("/login/email", r.headers["Location"])
        self.assertEqual(mailer.OUTBOX, [])

    def test_4_wrong_code_is_refused(self):
        c = self.email_in()
        s, _, r = c.req("POST", "/login/email/verify", form={"email": "boss@hellovoice.co.uk", "code": "000000"})
        self.assertEqual(s, 303)
        self.assertIn("e=1", r.headers["Location"])
        s, _, r = c.get("/")
        self.assertEqual(s, 303)                       # still signed out

    def test_5_a_client_code_does_not_open_a_non_admin(self):
        c = Client(self.base)
        c.req("POST", "/login/email", form={"email": "client@pfizer.com"})
        self.assertEqual(mailer.OUTBOX, [])

    def test_6_removed_admin_cannot_sign_in(self):
        team.invite("gone@hellovoice.co.uk", "Gone", "kam")
        a = db.admin_by_email("gone@hellovoice.co.uk")
        team.set_disabled(a["id"], True)
        self.email_in("gone@hellovoice.co.uk")
        self.assertEqual(mailer.OUTBOX, [])

    def test_7_owner_invites_by_email_no_password_shown(self):
        c = self.email_in()
        c.req("POST", "/login/email/verify", form={"email": "boss@hellovoice.co.uk", "code": last_code()})
        mailer.OUTBOX.clear()
        s, _, r = c.req("POST", "/team/invite", form={"email": "new@hellovoice.co.uk", "name": "New", "role": "kam"})
        if s == 303 and "/reauth" in r.headers["Location"]:
            c.req("POST", "/reauth", form={"send_code": "1", "next": "/team"})
            c.req("POST", "/reauth", form={"mailcode": last_code(), "next": "/team"})
            mailer.OUTBOX.clear()
            s, _, r = c.req("POST", "/team/invite", form={"email": "new@hellovoice.co.uk", "name": "New", "role": "kam"})
        self.assertEqual(s, 303)
        self.assertNotIn("pw=", r.headers["Location"])
        self.assertIsNotNone(db.admin_by_email("new@hellovoice.co.uk"))
        self.assertEqual(mailer.OUTBOX[-1]["to"], "new@hellovoice.co.uk")
        # and the invited person can now sign in by code
        mailer.OUTBOX.clear()
        d = self.email_in("new@hellovoice.co.uk")
        s, _, _ = d.req("POST", "/login/email/verify", form={"email": "new@hellovoice.co.uk", "code": last_code()})
        self.assertEqual(s, 303)
        self.assertEqual(d.get("/")[0], 200)

    def test_8_confirmation_accepts_an_emailed_code(self):
        c = self.email_in()
        c.req("POST", "/login/email/verify", form={"email": "boss@hellovoice.co.uk", "code": last_code()})
        s, body, _ = c.get("/reauth?next=/team")
        self.assertIn("Email me a code", body)
        mailer.OUTBOX.clear()
        c.req("POST", "/reauth", form={"send_code": "1", "next": "/team"})
        s, _, r = c.req("POST", "/reauth", form={"mailcode": last_code(), "next": "/team"})
        self.assertEqual(s, 303)
        self.assertEqual(r.headers["Location"], "/team")
        self.assertEqual(c.get("/team")[0], 200)

    def test_10_portal_sign_in_opens_the_admin_without_a_second_code(self):
        import e2e_portal
        db.set_setting("signup_mode", "open")
        signup = e2e_portal.Portal.signup
        class T:                                       # borrow the portal test's sign-up helper
            base = self.base
            assertEqual = self.assertEqual
        c, _ = signup(T, "boss@hellovoice.co.uk")
        mailer.OUTBOX.clear()
        s, _, r = c.get("/")
        self.assertEqual(s, 303)
        self.assertNotIn("/login", r.headers["Location"])   # straight in: no second code
        self.assertEqual(mailer.OUTBOX, [])
        self.assertEqual(c.get("/")[0], 200)
        s, _, r = c.get("/clients?show=waiting")             # the page asked for is kept
        self.assertEqual(s, 200)

    def test_11_a_client_portal_account_gets_no_admin(self):
        import e2e_portal
        signup = e2e_portal.Portal.signup
        class T:
            base = self.base
            assertEqual = self.assertEqual
        c, _ = signup(T, "buyer@pfizer.com")
        s, _, r = c.get("/")
        self.assertEqual(s, 303)
        self.assertIn("/login", r.headers["Location"])

    def test_9_deleting_a_creator_asks_for_confirmation(self):
        self.assertTrue(team.needs_step_up("POST", "/roster/delete"))
        self.assertTrue(team.needs_step_up("POST", "/portal/user/credits"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
