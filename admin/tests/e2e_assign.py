"""End-to-end tests for the one-step "Assign to client" (2026-10-11, branch assign-to-client).

- the selection moves to the chosen account and its campaigns move with it (or stay, when unticked);
- the client's bell says what was shared and links to the selection and the campaign report, and
  nothing is emailed;
- assigning to the same client changes and notifies nothing;
- a revoked or expired code is refused, and is not offered in the select;
- a viewer is refused on the server, a key account manager may;
- History records who, from and to;
- the new client's lists show the selection and campaign, the previous owner's no longer do, and a
  colleague on the same company domain sees them read-only.

    python3 admin/tests/e2e_assign.py
"""
import json
import shutil
import sys
import threading
import unittest
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import assign, db, guard, history, inbox, mailer, portal, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


class Assign(unittest.TestCase):
    signup = base.Portal.signup
    admin = base.Portal.admin
    member = base.Portal.member

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        mailer.CAPTURE = True
        views.set_base("")
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

    # ---------------------------------------------------------------- helpers
    def cid(self, email):
        return portal.user_by_email(email)["code_id"]

    def make(self, name="Skincare shortlist", owner=None, live=True, campaigns=2):
        sid = db.save_selection(None, name, ["HV-MI-001", "HV-MI-002"], {}, None, None, code_id=owner)
        ks = []
        for i in range(campaigns):
            k = db.create_campaign("%s wave %d" % (name, i + 1), client=(db.get_code(owner)["label"] if owner else None),
                                   code_id=owner, selection_id=sid)
            if live and i == 0:
                db.save_campaign(k, status="live", starts_at=1, ends_at=2)
            ks.append(k)
        return sid, ks

    def post(self, a, path, **form):
        s, _b, r = a.req("POST", path, form={"confirmed": "1", **form})
        return s, urllib.parse.unquote(r.headers.get("Location", ""))

    def sels(self, c):
        return {s["token"]: s for s in c.get("/api/account")[1]["selections"]}

    def camps(self, c):
        return [k["name"] for k in c.get("/api/campaigns")[1]["campaigns"]]

    def bell(self, c):
        return c.get("/api/notifications")[1]["items"]

    def plain_code(self, label, n=[0]):
        n[0] += 1
        return db.create_code("hash-assign-%d" % n[0], "····", label, code_plain="PLAIN%d" % n[0])

    # ------------------------------------------------------------------ tests
    def test_01_moves_selection_and_campaigns_and_rings_the_bell(self):
        old, _ = self.signup("old@firsto.com")
        new, _ = self.signup("new@seconda.com")
        a_id, b_id = self.cid("old@firsto.com"), self.cid("new@seconda.com")
        sid, (live, draft) = self.make("Ramadan skincare", owner=a_id)
        token = db.selection(sid)["token"]
        self.assertIn(token, self.sels(old))
        self.assertIn("Ramadan skincare wave 1", self.camps(old))
        mailer.OUTBOX.clear()
        a = self.admin()
        s, loc = self.post(a, "/selections/assign", id=str(sid), client=str(b_id), move_campaigns="1", tell="1")
        self.assertEqual(s, 303)
        self.assertIn("ok=", loc)
        self.assertEqual(db.selection(sid)["code_id"], b_id)
        self.assertEqual({db.campaign(live)["code_id"], db.campaign(draft)["code_id"]}, {b_id})
        self.assertEqual(db.campaign(live)["client"], db.get_code(b_id)["label"])      # label followed the client
        # the new client sees both lists, the old one no longer does
        self.assertIn(token, self.sels(new))
        self.assertIn("Ramadan skincare wave 1", self.camps(new))
        self.assertNotIn("Ramadan skincare wave 2", self.camps(new))                  # a draft is never listed
        self.assertNotIn(token, self.sels(old))
        self.assertNotIn("Ramadan skincare wave 1", self.camps(old))
        # the bell
        items = self.bell(new)
        sel_bell = next(i for i in items if i["kind"] == "sel_shared")
        self.assertIn('HelloVoice shared "Ramadan skincare" with you', sel_bell["title"] + sel_bell["rest"])
        self.assertIn("and its campaign Ramadan skincare wave 1", sel_bell["rest"])
        self.assertTrue(sel_bell["href"].endswith("selection/#s=" + token))
        camp_bell = next(i for i in items if i["kind"] == "camp_shared")
        self.assertIn("campaign/#t=" + db.campaign(live)["token"], camp_bell["href"])
        self.assertFalse(any("wave 2" in (i["title"] + i["rest"]) for i in items))     # the draft is not announced
        self.assertEqual(self.bell(old), [i for i in self.bell(old) if i["kind"] != "sel_shared" or "Ramadan" not in i["title"]])
        self.assertEqual(mailer.OUTBOX, [])                                           # never an email

    def test_02_campaigns_stay_when_unticked_and_no_bell_when_unticked(self):
        c1, _ = self.signup("a@stayco.com")
        c2, _ = self.signup("b@moveco.com")
        a_id, b_id = self.cid("a@stayco.com"), self.cid("b@moveco.com")
        sid, (k1, k2) = self.make("Stay put", owner=a_id)
        a = self.admin()
        before = len(self.bell(c2))
        s, loc = self.post(a, "/selections/assign", id=str(sid), client=str(b_id))      # neither box sent
        self.assertIn("ok=", loc)
        self.assertEqual(db.selection(sid)["code_id"], b_id)
        self.assertEqual({db.campaign(k1)["code_id"], db.campaign(k2)["code_id"]}, {a_id})
        self.assertEqual(len(self.bell(c2)), before)

    def test_03_same_client_is_a_no_op(self):
        c, _ = self.signup("same@sameco.com")
        cid = self.cid("same@sameco.com")
        sid, _ks = self.make("Same", owner=cid)
        a = self.admin()
        n = len(self.bell(c))
        hist = len(history.listing(limit=500))
        s, loc = self.post(a, "/selections/assign", id=str(sid), client=str(cid), move_campaigns="1", tell="1")
        self.assertIn("Nothing changed", loc)
        self.assertEqual(len(self.bell(c)), n)
        self.assertEqual(len(history.listing(limit=500)), hist)
        r = assign.assign_selection(sid, cid)
        self.assertTrue(r["noop"] and r["ok"])

    def test_04_revoked_and_expired_codes_are_refused_and_not_offered(self):
        a = self.admin()
        sid, _ = self.make("Refuse", owner=None, campaigns=0)
        dead = self.plain_code("Dead client")
        db.revoke_code(dead)
        old = self.plain_code("Expired client")
        with db.connect() as conn:
            conn.execute("UPDATE codes SET expires_at = 5 WHERE id = ?", (old,))
        live = self.plain_code("Live plain client")
        for cid in (dead, old):
            s, loc = self.post(a, "/selections/assign", id=str(sid), client=str(cid))
            self.assertIn("e=", loc)
            self.assertIsNone(db.selection(sid)["code_id"])
        ids = {t["id"] for t in assign.targets()}
        self.assertNotIn(dead, ids)
        self.assertNotIn(old, ids)
        self.assertIn(live, ids)
        page = a.get("/selections/edit?id=%d" % sid)[1]
        self.assertIn("Assign to client", page)
        self.assertIn("Live plain client", page)
        self.assertNotIn("Dead client", page.split("Assign to client", 1)[1].split("</select>", 1)[0])
        # a plain access code works, with no bell to ring
        s, loc = self.post(a, "/selections/assign", id=str(sid), client=str(live), tell="1")
        self.assertEqual(db.selection(sid)["code_id"], live)
        self.assertIn("no portal account", loc)

    def test_05_roles(self):
        c, _ = self.signup("role@roleco.com")
        cid = self.cid("role@roleco.com")
        sid, _ = self.make("Roles", owner=None, campaigns=1)
        v, s, _ = self.member("view-assign@hellovoice.co.uk", "viewer")
        self.assertEqual(v.req("POST", "/selections/assign", form={"id": str(sid), "client": str(cid)})[0], 403)
        self.assertEqual(v.req("POST", "/campaigns/assign", form={"id": "1", "client": str(cid)})[0], 403)
        self.assertIsNone(db.selection(sid)["code_id"])
        k, s, _ = self.member("kam-assign@hellovoice.co.uk", "kam")
        # KAM scoped access (2026-10-11): a key account manager assigns within her own clients only.
        # The unfiled selection is nobody's client, so it is refused ("Not your client")...
        self.assertEqual(k.req("POST", "/selections/assign", form={"id": str(sid), "client": str(cid), "confirmed": "1"})[0], 403)
        self.assertIsNone(db.selection(sid)["code_id"])
        # ...and once roleco.com is hers, moving a selection between her clients works.
        db.set_setting("domain_kam", {"roleco.com": "kam-assign@hellovoice.co.uk"})
        self.signup("role2@roleco.com")
        mine, _ = self.make("Roles mine", owner=self.cid("role2@roleco.com"), campaigns=1)
        self.assertEqual(k.req("POST", "/selections/assign", form={"id": str(mine), "client": str(cid), "confirmed": "1"})[0], 303)
        self.assertEqual(db.selection(mine)["code_id"], cid)
        db.set_setting("domain_kam", {})

    def test_06_away_from_another_client_needs_confirmation_and_history_records_it(self):
        o, _ = self.signup("o@ownerco.com")
        n, _ = self.signup("n@newerco.com")
        o_id, n_id = self.cid("o@ownerco.com"), self.cid("n@newerco.com")
        sid, (k1,) = self.make("History run", owner=o_id, campaigns=1)
        a = self.admin()
        # without the confirmation the server refuses (an API caller cannot skip the prompt)
        s, _b, r = a.req("POST", "/selections/assign", form={"id": str(sid), "client": str(n_id), "move_campaigns": "1"})
        self.assertIn("moves it away from", urllib.parse.unquote(r.headers["Location"]))
        self.assertEqual(db.selection(sid)["code_id"], o_id)
        # the page asks first, naming who loses it
        page = a.get("/selections/edit?id=%d" % sid)[1]
        self.assertIn("Move it away from", page)
        self.assertIn("Ali Hassan", page)
        self.post(a, "/selections/assign", id=str(sid), client=str(n_id), move_campaigns="1", tell="1")
        rows = [r for r in history.listing(limit=50) if "History run" in (r["label"] or "")]
        labels = " | ".join(r["label"] for r in rows)
        self.assertIn('Assigned selection "History run" to', labels)
        self.assertIn("(was Ali Hassan", labels)
        self.assertIn('Assigned campaign "History run wave 1" to', labels)
        self.assertTrue(all(r["who"] for r in rows))
        sel_row = history.entry(next(r for r in rows if r["entity"] == "selection")["id"])
        self.assertEqual(json.loads(sel_row["before"])["selections"][0]["code_id"], o_id)
        self.assertEqual(json.loads(sel_row["after"])["selections"][0]["code_id"], n_id)

    def test_07_campaign_page_assigns_the_campaign_and_optionally_its_selection(self):
        o, _ = self.signup("o@campone.com")
        n, _ = self.signup("n@camptwo.com")
        o_id, n_id = self.cid("o@campone.com"), self.cid("n@camptwo.com")
        sid, (k1,) = self.make("Camp page", owner=o_id, campaigns=1)
        a = self.admin()
        page = a.get("/campaigns/edit?id=%d" % k1)[1]
        self.assertIn("Assign to client", page)
        self.assertIn("Also move its selection", page)
        mailer.OUTBOX.clear()
        self.post(a, "/campaigns/assign", id=str(k1), client=str(n_id), tell="1")
        self.assertEqual(db.campaign(k1)["code_id"], n_id)
        self.assertEqual(db.selection(sid)["code_id"], o_id)                           # the selection stayed
        self.assertTrue(any(i["kind"] == "camp_shared" for i in self.bell(n)))
        self.post(a, "/campaigns/assign", id=str(k1), client=str(o_id), with_selection="1")
        self.assertEqual((db.campaign(k1)["code_id"], db.selection(sid)["code_id"]), (o_id, o_id))
        self.assertEqual(mailer.OUTBOX, [])

    def test_08_colleague_on_the_same_domain_sees_it_read_only(self):
        c1, _ = self.signup("lead@teamco.com")
        c2, _ = self.signup("mate@teamco.com")
        lead = self.cid("lead@teamco.com")
        sid, _ = self.make("Team share", owner=None, campaigns=0)
        token = db.selection(sid)["token"]
        a = self.admin()
        self.post(a, "/selections/assign", id=str(sid), client=str(lead), tell="1")
        self.assertTrue(self.sels(c1)[token]["mine"])
        mate = self.sels(c2)[token]
        self.assertFalse(mate["mine"])
        self.assertFalse(mate.get("can_delete"))
        self.assertTrue(any(i["kind"] == "sel_shared" for i in self.bell(c2)))        # the team hears too

    def test_09_pending_or_missing_targets_refused(self):
        sid, _ = self.make("Missing", owner=None, campaigns=0)
        self.assertIn("no longer exists", assign.assign_selection(sid, 99999)["error"])
        self.assertIn("no longer exists", assign.assign_selection(999999, 1)["error"])
        self.assertIsNone(assign.assign_campaign(999999, 1)["selection"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
