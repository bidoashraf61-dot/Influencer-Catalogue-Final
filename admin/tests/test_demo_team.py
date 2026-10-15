"""The demo reaches every BlueHolding account (owner, 2026-10-15), even when the account holding it is
deactivated; other companies never see it.   python3 admin/tests/test_demo_team.py"""
import shutil, sys, tempfile, unittest
from pathlib import Path
SRC = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="hv-demo-"))
for f in SRC.glob("*.py"):
    shutil.copy(f, TMP / f.name)
sys.path.insert(0, str(TMP))
import db, portal  # noqa: E402


class DemoTeam(unittest.TestCase):
    def test_every_blueholding_account(self):
        db.init(); portal.init()
        now = db.now()
        with db.connect() as conn:
            def user(email, cid, status="active"):
                conn.execute("INSERT INTO codes (id, code_hash, hint, label, created_at) VALUES (?,?,?,?,?)", (cid, "h%d" % cid, "x", email, now))
                conn.execute("INSERT INTO users (email, name, domain, code_id, status, created_at) VALUES (?,?,?,?,?,?)",
                             (email, email, email.split("@")[1], cid, status, now))
            user("owner@blueholding.co.uk", 901, "suspended")
            user("new@blueholding.co.uk", 902)
            user("buyer@otherco.com", 903)
        sid = db.save_selection(None, "SAMPLE", ["HV-MI-001"], {}, None, None, code_id=901)
        db.set_setting("sample_selections", [sid])
        self.assertIn(901, portal.team_codes(902))
        self.assertNotIn(901, portal.team_codes(903))


if __name__ == "__main__":
    unittest.main()
