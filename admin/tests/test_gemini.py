"""Gemini client: fallback chain, budget ceiling, audit. No network."""
import shutil, sys, tempfile, unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="hv-gem-"))
for f in SRC.glob("*.py"):
    shutil.copy(f, TMP / f.name)
sys.path.insert(0, str(TMP))
import db, gemini, history, portal  # noqa: E402

OK = {"candidates": [{"content": {"parts": [{"text": "hi"}]}}], "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2, "thoughtsTokenCount": 10}}


class G(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init(); history.init(); portal.init()
        gemini.STUB = None
        gemini.key = lambda: "test-key-123456789012345"

    def tearDown(self):
        gemini._post = self._orig if hasattr(self, "_orig") else gemini._post

    def patch(self, fn):
        self._orig = gemini._post
        gemini._post = fn

    def test_falls_through_retired_and_overloaded_models(self):
        seen = []
        def post(mdl, body, timeout):
            seen.append(mdl)
            if mdl == gemini.DEFAULT_MODEL:
                raise gemini.Upstream("gone", 404)
            if mdl == gemini.FALLBACKS[0]:
                raise gemini.Upstream("busy", 503)
            return OK
        self.patch(post)
        out = gemini.generate("hello", kind="t")
        self.assertEqual(out["text"], "hi")
        self.assertEqual(seen, [gemini.DEFAULT_MODEL, gemini.FALLBACKS[0], gemini.FALLBACKS[1]])
        with db.connect() as c:
            r = c.execute("SELECT model, out_tokens FROM ai_audit ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual((r["model"], r["out_tokens"]), (gemini.FALLBACKS[1], 12))   # thinking tokens are counted

    def test_bad_key_does_not_fall_through(self):
        n = []
        def post(mdl, body, timeout):
            n.append(mdl); raise gemini.NotConfigured("The Gemini key was refused.")
        self.patch(post)
        with self.assertRaises(gemini.NotConfigured):
            gemini.generate("hello", kind="t")
        self.assertEqual(len(n), 1)

    def test_all_models_down_raises_upstream_and_is_audited(self):
        self.patch(lambda m, b, t: (_ for _ in ()).throw(gemini.Upstream("down", 503)))
        with self.assertRaises(gemini.Upstream):
            gemini.generate("hello", kind="t")
        with db.connect() as c:
            self.assertEqual(c.execute("SELECT ok FROM ai_audit ORDER BY id DESC LIMIT 1").fetchone()[0], 0)

    def test_monthly_ceiling_blocks_calls(self):
        self.patch(lambda m, b, t: OK)
        db.set_setting("ai_monthly_tokens", 10000)
        db.set_setting("ai_monthly_tokens", 1)
        try:
            with self.assertRaises(gemini.OverBudget):
                gemini.generate("hello", kind="t")
        finally:
            db.set_setting("ai_monthly_tokens", gemini.DEFAULT_MONTHLY_TOKENS)

    def test_key_validation(self):
        for bad in ("", "short", "has space in it 12345678901234567890"):
            with self.assertRaises(ValueError):
                gemini.save_key(bad)


if __name__ == "__main__":
    unittest.main(verbosity=1)
