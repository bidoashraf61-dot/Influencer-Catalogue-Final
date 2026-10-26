"""Item 175: deploy/catalogue/stamp_assets.py keeps every ?v= stamp equal to the file's content,
on every page, and gives sw.js a new VERSION whenever the app shell changes. It also refuses a
link that does not line up with the tag it sits in (2026-10-26: a hand-stamped publish put
dashboard.js in the dashboard's stylesheet link and the live page lost all of its CSS).

    python3 admin/tests/test_stamp_assets.py
"""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deploy" / "catalogue"))
import stamp_assets  # noqa: E402


def md5(b):
    return hashlib.md5(b).hexdigest()[:8]


class StampTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.root = Path(self.tmp.name)
        for d in ("assets/js", "assets/css", "assets/app", "new-page", "campaign/dashboard"):
            (r / d).mkdir(parents=True)
        self.w("assets/js/tour.js", "tour1")
        self.w("assets/js/connect.js", 'load("assets/js/tour.js?v=00000000"); x = "assets/css/connect.css" + "?p=1";')
        self.w("assets/js/hv-drag.js", "drag1")
        self.w("assets/css/app.css", "a{}")
        self.w("assets/app/icon-192.png", "png")
        self.w("sw.js", 'const VERSION = "hca-3";\nself.x = 1;')
        self.w("offline.html", "<p>offline</p>")
        self.w("new-page/index.html",
               '<link href="../assets/css/app.css"><script src="../assets/js/connect.js?v=deadbeef"></script>'
               '<!-- assets/js/hv-drag.js in a comment stays as it is --><img src="../assets/app/icon-192.png?v=c4">')
        self.w("campaign/dashboard/index.html", '<script src="../../assets/js/hv-drag.js?v=c6cf08a6"></script>')
        self.w("campaign/dashboard/._index.html", '<script src="../../assets/js/hv-drag.js?v=c6cf08a6"></script>')

    def tearDown(self):
        self.tmp.cleanup()

    def w(self, rel, text):
        (self.root / rel).write_text(text)

    def r(self, rel):
        return (self.root / rel).read_text()

    def run_it(self, *flags):
        return stamp_assets.main([str(self.root)] + list(flags))

    def test_every_page_and_file_and_nested(self):
        self.assertEqual(self.run_it("--check"), 1)
        self.assertEqual(self.run_it(), 0)
        self.assertEqual(self.run_it("--check"), 0)
        cj = self.r("assets/js/connect.js")
        self.assertIn("tour.js?v=" + md5(b"tour1"), cj)
        self.assertIn('"assets/css/connect.css" + "?p=1"', cj)                # unstamped js refs untouched
        page = self.r("new-page/index.html")
        self.assertIn("../assets/css/app.css?v=" + md5(b"a{}"), page)         # unstamped -> stamped
        self.assertIn("../assets/js/connect.js?v=" + md5(cj.encode()), page)  # hash includes the tour stamp
        self.assertIn("assets/js/hv-drag.js in a comment", page)
        self.assertIn("icon-192.png?v=c4", page)                              # images are not touched
        self.assertIn("hv-drag.js?v=" + md5(b"drag1"), self.r("campaign/dashboard/index.html"))
        self.assertIn("v=c6cf08a6", self.r("campaign/dashboard/._index.html"))  # macOS junk skipped

    def test_sw_version_follows_the_shell(self):
        self.run_it()
        v1 = self.r("sw.js").splitlines()[0]
        self.assertRegex(v1, r'^const VERSION = "hca-[0-9a-f]{10}";$')
        self.run_it()
        self.assertEqual(self.r("sw.js").splitlines()[0], v1)                  # same build, same worker
        self.w("assets/js/hv-drag.js", "drag2")
        self.assertEqual(self.run_it("--check"), 1)
        self.run_it()
        self.assertNotEqual(self.r("sw.js").splitlines()[0], v1)              # any script change -> new worker
        v2 = self.r("sw.js").splitlines()[0]
        self.w("assets/app/icon-192.png", "png2")
        self.run_it()
        self.assertNotEqual(self.r("sw.js").splitlines()[0], v2)              # icon change -> new worker


class BrokenLinkTest(unittest.TestCase):
    """Exit 2, from --check and from a stamping run alike: a publish must stop, not carry on."""
    setUp = StampTest.setUp           # the same fixture tree, not the same tests
    tearDown = StampTest.tearDown
    w, r, run_it = StampTest.w, StampTest.r, StampTest.run_it

    def page(self, body):
        self.w("new-page/index.html", body)

    def test_the_2026_10_26_incident_is_refused(self):
        # ".css" pasted over as ".js": the file is not there, and the tag is a stylesheet.
        self.page('<link rel="stylesheet" href="../assets/css/dashboard.js?v=626f6b2f"/>')
        self.assertEqual(self.run_it("--check"), 2)
        self.assertEqual(self.run_it(), 2)
        self.assertEqual(self.run_it("--links-only"), 2)

    def test_a_stylesheet_pointing_at_a_real_script_is_refused(self):
        # hv-drag.js exists and hashes fine, so only the tag it sits in can tell this is wrong.
        self.page('<link rel="stylesheet" href="../assets/js/hv-drag.js">')
        self.assertEqual(self.run_it("--links-only"), 2)
        self.assertEqual(self.run_it(), 2)

    def test_a_script_pointing_at_a_real_stylesheet_is_refused(self):
        self.page('<script src="../assets/css/app.css"></script>')
        self.assertEqual(self.run_it("--links-only"), 2)

    def test_a_missing_asset_is_refused_even_in_the_right_kind_of_tag(self):
        self.page('<link rel="stylesheet" href="../assets/css/gone.css">')
        self.assertEqual(self.run_it("--check"), 2)

    def test_a_js_file_naming_a_script_that_is_not_there(self):
        self.w("assets/js/connect.js", 'load("assets/js/vanished.js?v=00000000");')
        self.assertEqual(self.run_it("--check"), 2)

    def test_remote_stylesheets_and_inline_scripts_are_left_alone(self):
        self.page('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans">'
                  '<link rel="stylesheet" href="//cdn.example.com/x/flag-icons.min.css">'
                  '<link rel="preload" as="style" href="../assets/js/hv-drag.js">'
                  '<link rel="icon" href="../assets/app/icon-192.png">'
                  '<script>var inline = 1;</script>')
        self.assertEqual(self.run_it("--links-only"), 0)
        self.assertEqual(self.run_it(), 0)

    def test_a_clean_tree_still_passes(self):
        self.assertEqual(self.run_it("--links-only"), 0)
        self.assertEqual(self.run_it(), 0)
        self.assertEqual(self.run_it("--check"), 0)

    def test_bad_arguments_are_their_own_exit_code(self):
        self.assertEqual(stamp_assets.main([]), 64)       # never confused with a broken link


if __name__ == "__main__":
    unittest.main()
