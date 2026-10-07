import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import guard


class Email(unittest.TestCase):
    def ok(self, e, **kw): return guard.company_email(e, **kw)[0]
    def why(self, e, **kw): return guard.company_email(e, **kw)[1]

    def test_company_passes(self):
        self.assertEqual(self.ok("  Jane.Doe@Pfizer.com "), "jane.doe@pfizer.com")
        self.assertEqual(self.ok("a@mail.nahdi.sa"), "a@mail.nahdi.sa")

    def test_personal_blocked(self):
        for e in ("a@gmail.com", "a@GMAIL.com", "a@outlook.com", "a@icloud.com",
                  "a@x.gmail.com", "a@yahoo.co.uk", "a@mailinator.com", "a@stc.com.sa"):
            self.assertEqual(self.why(e), "personal", e)

    def test_invalid(self):
        for e in ("", "x", "a@b", "a@@b.com", "a b@c.com", "a@b..com", "a@-b.com", "a@b.c1", "a@1.2.3.4"):
            self.assertEqual(self.why(e), "invalid", e)

    def test_plus_tags_collapse(self):
        self.assertEqual(self.ok("Jane+promo1@Pfizer.com"), "jane@pfizer.com")
        self.assertEqual(self.ok("jane+a+b@pfizer.com"), "jane@pfizer.com")

    def test_lookalike_not_blocked(self):
        self.assertEqual(self.ok("a@notgmail.com"), "a@notgmail.com")
        self.assertEqual(self.ok("a@gmail.com.evil.io"), "a@gmail.com.evil.io")

    def test_admin_lists(self):
        self.assertEqual(self.ok("a@gmail.com", allow=["gmail.com"]), "a@gmail.com")
        self.assertEqual(self.why("a@pfizer.com", block=["pfizer.com"]), "blocked")
        self.assertEqual(self.why("a@x.pfizer.com", block=["pfizer.com"]), "blocked")
        self.assertEqual(self.why("a@gmail.com", allow=["gmail.com"], block=["gmail.com"]), "blocked")


class Limit(unittest.TestCase):
    def test_window(self):
        L = guard.Limiter()
        for i in range(3): L.hit("k", now=100 + i)
        self.assertFalse(L.allow("k", 3, 60, now=110))
        self.assertEqual(L.retry_after("k", 3, 60, now=110), 51)
        self.assertTrue(L.allow("k", 3, 60, now=161))
        L.reset("k"); self.assertTrue(L.allow("k", 3, 60, now=110))


class Csrf(unittest.TestCase):
    def test_origin(self):
        A = {"https://x.co"}
        self.assertTrue(guard.origin_ok({"Origin": "https://x.co"}, A))
        self.assertFalse(guard.origin_ok({"Origin": "https://evil.io"}, A))
        self.assertFalse(guard.origin_ok({"Origin": "null"}, A))
        self.assertTrue(guard.origin_ok({}, A))
        self.assertFalse(guard.origin_ok({"Sec-Fetch-Site": "cross-site"}, A))
        self.assertTrue(guard.origin_ok({"Origin": "http://h:1", "Host": "h:1"}, set()))
        self.assertFalse(guard.origin_ok({"Origin": "http://e.io", "Host": "h:1"}, set()))


if __name__ == "__main__":
    unittest.main()
