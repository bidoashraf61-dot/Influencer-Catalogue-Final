"""End-to-end tests for HELVY Connect fix batch 9 (2026-10-11, branch portal-fixes-9):

#42 the quote lifecycle chip: Draft -> Quote requested -> Quote ready -> Approved -> Campaign live ->
    Completed; owner-only request and approve; colleagues read-only; bell only (never a client email);
    the selection stays editable after a request with a warning and the account manager told;
    legacy selections get the right state with no migration.
#43 the admin "Create campaign" from a selection: pre-filled from the selection and its brief,
    saved as a DRAFT linked to it, admin-only; going live / ending moves the client's chip.

    python3 admin/tests/e2e_portal_fixes9.py
"""
import json
import shutil
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402
from e2e_portal import Client  # noqa: E402

import db, gemini, guard, lifecycle, lifecycle_ui, mailer, notify, portal, selstatus, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

BRIEF = {"goal": ["awareness", "traffic"], "platforms": ["Instagram", "TikTok"], "market": "SA", "category": ["skincare"], "count": "5"}


class Fixes9(unittest.TestCase):
    signup = base.Portal.signup
    admin = base.Portal.admin

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        db.set_setting("notify_emails", ["team@hellovoice.co.uk"])
        mailer.CAPTURE = True
        gemini.STUB = base.stub
        views.set_base("")
        selstatus.EMAIL_DELAY = 0
        lifecycle.NOTIFY_DELAY = 0
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        db.set_setting("signups_per_ip_day", 1000)
        guard.limiter._hits.clear()
        mailer.OUTBOX.clear()

    # ---------------------------------------------------------------- helpers --
    def selection(self, c, name, codes=("HV-MI-001", "HV-MI-002", "HV-MD-003")):
        s, made, _ = c.post("/api/selection", {"name": name, "codes": list(codes)})
        self.assertTrue(made["ok"], made)
        return made["token"]

    def state(self, c, tok):
        s, b, _ = c.get("/api/selection?s=" + tok)
        self.assertEqual(s, 200, b)
        return b["lifecycle"]

    def request_quote(self, c, tok, name="Ali Hassan"):
        s, b, _ = c.post("/api/request", {"name": name, "company": "Glow", "email": "x@glow.com", "phone": "1",
                                          "selection_name": "x", "token": tok, "selection": ["HV-MI-001"]})
        return s, b

    def bell(self, c):
        return c.get("/api/notifications?limit=10")[1]

    def to_client(self):
        return [m for m in mailer.OUTBOX if m["to"] != "team@hellovoice.co.uk"]

    # ------------------------------------------------------------------- #42 --
    def test_01_every_transition_and_nobody_is_emailed(self):
        owner, _ = self.signup("owner9@glowderma.com")
        mate, _ = self.signup("mate9@glowderma.com")
        tok = self.selection(owner, "Ramadan 9")
        lc = self.state(owner, tok)
        self.assertEqual((lc["key"], lc["label"], lc["role"]), ("draft", "Draft", "owner"))
        self.assertEqual([s["key"] for s in lc["steps"]], ["draft", "requested", "ready", "approved", "live", "completed"])
        self.assertEqual(lc["steps"][0]["state"], "current")
        self.assertEqual(lc["warn"], "")                      # nothing to update yet
        mailer.OUTBOX.clear()

        # 1 Draft -> Quote requested (owner sends the request)
        s, b = self.request_quote(owner, tok)
        self.assertEqual((s, b["ok"]), (200, True))
        lc = self.state(owner, tok)
        self.assertEqual((lc["key"], lc["label"]), ("requested", "Quote requested"))
        self.assertEqual(lc["steps"][1]["by"], "Ali Hassan")
        self.assertTrue(lc["steps"][1]["at"])
        self.assertEqual(lc["warn"], "This updates your quote request")
        self.assertFalse(lc["can_approve"])

        # approving before the quote is ready is refused
        s, r, _ = owner.post("/api/selection/quote/approve", {"token": tok})
        self.assertEqual((s, r["reason"]), (409, "not_ready"))

        # 2 Quote requested -> Quote ready, with a note and a link the client sees
        a = self.admin()
        sel = db.selection(token=tok)
        mailer.OUTBOX.clear()
        s, _b, r = a.req("POST", "/quote/ready", form={"id": sel["id"], "note": "Includes 3 reels and 3 months of usage rights",
                                                         "link": "https://files.hellovoice.co.uk/quote-9.pdf"})
        self.assertEqual(s, 303)
        lc = self.state(owner, tok)
        self.assertEqual((lc["key"], lc["label"]), ("ready", "Quote ready"))
        self.assertEqual(lc["note"], "Includes 3 reels and 3 months of usage rights")
        self.assertEqual(lc["link"], "https://files.hellovoice.co.uk/quote-9.pdf")
        self.assertTrue(lc["can_approve"])
        self.assertEqual(lc["steps"][2]["state"], "current")
        self.assertEqual(lc["steps"][1]["state"], "done")
        # the bell rings for the owner AND the colleague; no email to either
        for who in (owner, mate):
            items = self.bell(who)["items"]
            self.assertTrue(any(i["kind"] == "quote_ready" and "Ramadan 9" in i["rest"] for i in items), items)
        self.assertEqual(self.to_client(), [])
        self.assertFalse(any("owner9@" in m["to"] or "mate9@" in m["to"] for m in mailer.OUTBOX))

        # a colleague sees the chip and timeline but can neither approve nor change anything
        ml = self.state(mate, tok)
        self.assertEqual((ml["key"], ml["role"], ml["can_approve"], ml["warn"]), ("ready", "viewer", False, ""))
        s, r, _ = mate.post("/api/selection/quote/approve", {"token": tok})
        self.assertEqual((s, r["reason"]), (403, "not_owner"))
        self.assertEqual(self.state(owner, tok)["key"], "ready")

        # 3 Quote ready -> Approved, by the owner only
        mailer.OUTBOX.clear()
        s, r, _ = owner.post("/api/selection/quote/approve", {"token": tok})
        self.assertEqual((s, r["ok"]), (200, True), r)
        self.assertEqual(r["lifecycle"]["key"], "approved")
        lc = self.state(owner, tok)
        self.assertEqual((lc["key"], lc["steps"][3]["by"]), ("approved", "Ali Hassan"))
        self.assertTrue(lc["steps"][3]["at"])
        self.assertFalse(lc["can_approve"])
        # approving again changes nothing
        s, r, _ = owner.post("/api/selection/quote/approve", {"token": tok})
        self.assertEqual((s, r["lifecycle"]["key"]), (200, "approved"))
        # the colleague is told on the bell; the team (not the client) gets the email
        self.assertTrue(any(i["kind"] == "quote_approved" for i in self.bell(mate)["items"]))
        self.assertFalse(any(i["kind"] == "quote_approved" for i in self.bell(owner)["items"]))   # they did it themselves
        self.assertEqual(self.to_client(), [])
        self.assertTrue(any(m["to"] == "team@hellovoice.co.uk" and "approved the quote" in m["text"] for m in mailer.OUTBOX))

        # 4 Approved -> Campaign live -> Completed, through the campaign
        k_id = db.create_campaign("Ramadan 9", client="Glow", code_id=sel["code_id"], selection_id=sel["id"],
                                  codes=["HV-MI-001"])
        self.assertEqual(self.state(owner, tok)["key"], "approved")           # a draft campaign changes nothing
        db.save_campaign(k_id, starts_at=db.now() - 86400, ends_at=db.now() + 86400 * 10)
        mailer.OUTBOX.clear()
        db.save_campaign(k_id, status="live")
        lc = self.state(owner, tok)
        self.assertEqual((lc["key"], lc["label"]), ("live", "Campaign live"))
        self.assertTrue(lc["steps"][4]["at"])
        self.assertEqual(lc["campaign"]["name"], "Ramadan 9")
        self.assertTrue(any(i["kind"] == "camp_live" for i in self.bell(owner)["items"]))
        self.assertEqual(self.state(mate, tok)["key"], "live")
        db.save_campaign(k_id, status="ended")
        lc = self.state(owner, tok)
        self.assertEqual((lc["key"], lc["label"]), ("completed", "Completed"))
        self.assertTrue(lc["steps"][5]["at"])
        self.assertTrue(any(i["kind"] == "camp_final" for i in self.bell(owner)["items"]))
        self.assertEqual(self.to_client(), [])
        # reopening the campaign moves the chip back to live
        db.save_campaign(k_id, status="live")
        self.assertEqual(self.state(owner, tok)["key"], "live")

    def test_02_edit_after_request_warns_and_tells_the_account_manager(self):
        owner, _ = self.signup("edit9@glowderma.com")
        tok = self.selection(owner, "Eid 9", ["HV-MI-001", "HV-MI-002", "HV-MD-003"])
        sent = []
        real = notify.send
        notify.send = lambda event, lines, kam=None, link=None: sent.append((event, list(lines), kam))
        try:
            # a draft edit is just an edit: no warning, nobody told
            s, r, _ = owner.post("/api/selection", {"token": tok, "name": "Eid 9", "codes": ["HV-MI-001", "HV-MI-002"]})
            self.assertTrue(r["ok"])
            self.assertNotIn("lifecycle", r)
            self.assertEqual([e for e in sent if e[0] == "quote_changed"], [])
            self.request_quote(owner, tok)
            sent.clear()
            s, r, _ = owner.post("/api/selection", {"token": tok, "name": "Eid 9",
                                                    "codes": ["HV-MI-001", "HV-MI-002", "HV-MD-004"]})
            self.assertTrue(r["ok"])
            self.assertEqual(r["lifecycle"]["warn"], "This updates your quote request")
            self.assertEqual(r["lifecycle"]["key"], "requested")
            self.assertEqual(len(r["lifecycle"]["changes"]), 1)
            self.assertEqual((r["lifecycle"]["changes"][0]["added"], r["lifecycle"]["changes"][0]["removed"]), (1, 0))
            ev = [e for e in sent if e[0] == "quote_changed"]
            self.assertEqual(len(ev), 1)
            self.assertIn("1 added", " ".join(ev[0][1]))
            self.assertIn("Eid 9", " ".join(ev[0][1]))
            # renaming only (same creators) is not a change to the quote
            sent.clear()
            owner.post("/api/selection", {"token": tok, "name": "Eid 9 renamed", "codes": ["HV-MI-001", "HV-MI-002", "HV-MD-004"]})
            self.assertEqual([e for e in sent if e[0] == "quote_changed"], [])
            # and the data the page reads back
            lc = self.state(owner, tok)
            self.assertEqual(lc["key"], "requested")
            self.assertEqual(lc["warn"], "This updates your quote request")
        finally:
            notify.send = real

    def test_03_changed_after_ready_is_flagged_to_the_team_only(self):
        owner, _ = self.signup("flag9@glowderma.com")
        tok = self.selection(owner, "Flag 9")
        self.request_quote(owner, tok)
        a = self.admin()
        sel = db.selection(token=tok)
        a.req("POST", "/quote/ready", form={"id": sel["id"], "note": "ok"})
        self.assertEqual(self.state(owner, tok)["key"], "ready")
        owner.post("/api/selection", {"token": tok, "name": "Flag 9", "codes": ["HV-MI-001", "HV-MI-002"]})
        self.assertEqual(self.state(owner, tok)["key"], "ready")             # the state holds
        st = lifecycle.admin_payload(db.selection(token=tok))
        self.assertTrue(st["changed_after_ready"])
        self.assertTrue(st["can_withdraw"])
        s, body, _ = a.get("/selections/edit?id=%d" % sel["id"])
        self.assertEqual(s, 200)
        self.assertIn("changed the creators after the quote was marked ready", body)
        self.assertIn("Quote ready", body)

    def test_04_only_the_owner_requests_and_a_bad_link_is_refused(self):
        owner, _ = self.signup("own94@glowderma.com")
        mate, _ = self.signup("mate94@glowderma.com")
        tok = self.selection(owner, "Own 9")
        s, r = self.request_quote(mate, tok, "Mate")
        self.assertEqual(s, 403)
        self.assertEqual(self.state(owner, tok)["key"], "draft")
        s, r = self.request_quote(owner, tok)
        self.assertEqual(s, 200)
        a = self.admin()
        sel = db.selection(token=tok)
        s, _b, r = a.req("POST", "/quote/ready", form={"id": sel["id"], "note": "x", "link": "http://insecure.example/q.pdf"})
        self.assertEqual(s, 303)
        self.assertIn("e=", r.headers["Location"])
        self.assertEqual(self.state(owner, tok)["key"], "requested")
        s, _b, r = a.req("POST", "/quote/ready", form={"id": sel["id"], "note": "x\n" * 400, "link": "javascript:alert(1)"})
        self.assertEqual(self.state(owner, tok)["key"], "requested")
        # taking it back and approval lock
        a.req("POST", "/quote/ready", form={"id": sel["id"], "note": "ready"})
        self.assertEqual(self.state(owner, tok)["key"], "ready")
        a.req("POST", "/quote/withdraw", form={"id": sel["id"]})
        self.assertEqual(self.state(owner, tok)["key"], "requested")
        a.req("POST", "/quote/ready", form={"id": sel["id"], "note": "ready"})
        owner.post("/api/selection/quote/approve", {"token": tok})
        a.req("POST", "/quote/withdraw", form={"id": sel["id"]})            # approved: cannot be taken back
        self.assertEqual(self.state(owner, tok)["key"], "approved")

    def test_05_legacy_selections_get_the_right_state_with_no_migration(self):
        c, _ = self.signup("legacy9@glowderma.com")
        u = portal.user_by_email("legacy9@glowderma.com")
        # an old selection with a request that was only ever matched by name and client
        sid = db.save_selection(None, "Old shortlist", ["HV-MI-001", "HV-MI-002"], {}, None, None, None, u["code_id"], origin="client")
        db.create_request(u["code_id"], "Ali", "Glow", "a@glow.com", "1", "Old shortlist", ["HV-MI-001", "HV-MI-002"])
        self.assertEqual(lifecycle.chip(db.selection(sid))["key"], "requested")
        # one linked by request_id
        sid2 = db.save_selection(None, "Linked", ["HV-MI-001"], {}, None, None, None, u["code_id"], origin="client")
        rid = db.create_request(u["code_id"], "Ali", "Glow", "a@glow.com", "1", "other name", ["HV-MI-001"])
        db.attach_request(sid2, rid)
        self.assertEqual(lifecycle.chip(db.selection(sid2))["key"], "requested")
        # a selection with a live campaign and no quote rows at all reads Campaign live
        sid3 = db.save_selection(None, "Running", ["HV-MI-001"], {}, None, None, None, u["code_id"], origin="client")
        k = db.create_campaign("Running", code_id=u["code_id"], selection_id=sid3, codes=["HV-MI-001"])
        with db.connect() as conn:
            conn.execute("DELETE FROM selection_quote WHERE selection_id = ?", (sid3,))
        db.save_campaign(k, starts_at=db.now() - 100, ends_at=db.now() + 10000, status="live")
        self.assertEqual(lifecycle.chip(db.selection(sid3))["key"], "live")
        # an untouched one is a Draft
        sid4 = db.save_selection(None, "Fresh", ["HV-MI-001"], {}, None, None, None, u["code_id"], origin="client")
        self.assertEqual(lifecycle.chip(db.selection(sid4))["key"], "draft")
        # the migration is idempotent
        lifecycle.init(); lifecycle.init()
        self.assertEqual(lifecycle.chip(db.selection(sid))["key"], "requested")

    def test_06_chip_in_the_profile_lists_and_in_helvys_context(self):
        c, _ = self.signup("prof9@glowderma.com")
        tok = self.selection(c, "Profile 9")
        self.request_quote(c, tok)
        acc = c.get("/api/account")[1]
        row = next(s for s in acc["selections"] if s["token"] == tok)
        self.assertEqual((row["quote"]["key"], row["quote"]["label"]), ("requested", "Quote requested"))
        # Helvy knows, and is told never to quote a price
        import assistant
        sel = db.selection(token=tok)
        line = lifecycle.summary_line(sel)
        self.assertIn("Quote requested", line)
        note = assistant._selection_note({"name": "Profile 9", "count": 3, "quote": line})
        self.assertIn("Quote status: Quote requested", note)
        self.assertIn("Never quote prices", note)
        # a live campaign shows on the profile's Campaigns list as its selection's chip
        u = portal.user_by_email("prof9@glowderma.com")
        k = db.create_campaign("Profile 9 live", code_id=u["code_id"], selection_id=sel["id"], codes=["HV-MI-001"])
        db.save_campaign(k, starts_at=db.now() - 100, ends_at=db.now() + 9999, status="live")
        acc = c.get("/api/account")[1]
        camp = next(x for x in acc["campaigns"] if x["name"] == "Profile 9 live")
        self.assertEqual(camp["quote"]["key"], "live")

    def test_07_the_client_never_reads_internal_fields(self):
        c, _ = self.signup("priv9@glowderma.com")
        tok = self.selection(c, "Private 9")
        self.request_quote(c, tok)
        a = self.admin()
        sel = db.selection(token=tok)
        a.req("POST", "/quote/ready", form={"id": sel["id"], "note": "Three reels"})
        body = json.dumps(self.state(c, tok)).lower()
        for w in ("margin", "cost", "price", "changed_after_ready", "can_create_campaign", "approved_by_user"):
            self.assertNotIn(w, body, w)

    # ------------------------------------------------------------------- #43 --
    def prepared(self, email, name="Setup 9"):
        c, _ = self.signup(email)
        u = portal.user_by_email(email)
        tok = self.selection(c, name, ["HV-MI-001", "HV-MI-002", "HV-MD-003", "HV-MD-004"])
        sel = db.selection(token=tok)
        c.post("/api/brief/attach", {"token": tok, "answers": BRIEF})
        with db.connect() as conn:
            conn.execute("UPDATE briefs SET objective = ? WHERE selection_id = ?", ("Awareness + Traffic", sel["id"]))
        return c, tok, db.selection(token=tok), u

    def test_10_the_form_is_prefilled_from_the_selection_and_its_brief(self):
        c, tok, sel, u = self.prepared("pre9@glowderma.com")
        a = self.admin()
        # not available while the selection is a draft
        s, _b, r = a.req("GET", "/campaigns/setup?selection=%d" % sel["id"])
        self.assertEqual(s, 303)
        self.request_quote(c, tok)
        selstatus.set_status(sel, "HV-MI-001", "approved", "client", "Ali")
        selstatus.set_status(sel, "HV-MI-002", "approved", "client", "Ali")
        selstatus.set_status(sel, "HV-MD-003", "rejected", "client", "Ali")
        d = lifecycle_ui.setup_defaults(sel)
        self.assertEqual(d["name"], "Setup 9")
        self.assertEqual(d["client"], "Pfizer KSA")                            # the account's company, not "Client: email"
        self.assertEqual(d["rules"], "#pfizerksa")
        self.assertEqual(d["goals"], ["awareness", "traffic"])
        self.assertEqual(d["objective"], "awareness+traffic")                  # the multi-goal brief is a blend
        self.assertEqual(d["platforms"], ["Instagram", "TikTok"])
        self.assertEqual(d["chosen"], ["HV-MI-001", "HV-MI-002"])             # approved only, when anyone is approved
        self.assertEqual(d["approved_n"], 2)
        self.assertIn("#ad", d["disclosure"])
        self.assertEqual((d["starts"], d["ends"]), ("", ""))                   # dates blank
        s, body, _ = a.get("/campaigns/setup?selection=%d" % sel["id"])
        self.assertEqual(s, 200)
        self.assertIn("value='Setup 9'", body)
        self.assertIn("name='goal' value='awareness' data-label='Awareness' checked", body)
        self.assertIn("name='goal' value='traffic' data-label='Traffic' checked", body)
        self.assertNotIn("name='goal' value='engagement' data-label='Engagement' checked", body)
        self.assertIn("name='platform' value='Instagram' data-label='Instagram' checked", body)
        self.assertIn("name='platform' value='Snapchat' data-label='Snapchat'>", body)
        self.assertIn("value='HV-MI-001' data-st='approved' data-live='1' checked", body)
        self.assertIn("value='HV-MD-003' data-st='rejected' data-live='0'>", body)    # rejected: not ticked
        # nobody approved: everyone not rejected is ticked
        c2, tok2, sel2, _u = self.prepared("pre92@glowderma.com", "Setup 9b")
        self.request_quote(c2, tok2)
        selstatus.set_status(sel2, "HV-MD-004", "unavailable", "hv", "HelloVoice")
        d2 = lifecycle_ui.setup_defaults(sel2)
        self.assertEqual(d2["chosen"], ["HV-MI-001", "HV-MI-002", "HV-MD-003"])

    def test_11_saving_creates_a_linked_draft_and_goes_live_through_the_existing_action(self):
        c, tok, sel, u = self.prepared("mk9@glowderma.com", "Make 9")
        self.request_quote(c, tok)
        a = self.admin()
        selstatus.set_status(sel, "HV-MI-001", "approved", "client", "Ali")
        before = {k["id"] for k in db.list_campaigns()}
        form = [("selection", sel["id"]), ("name", "Make 9 — wave 1"), ("client", "Glow Derma"),
                ("platform", "Instagram"), ("goal", "awareness"), ("goal", "traffic"),
                ("code", "HV-MI-001"), ("code", "HV-MI-002"), ("code", "HV-NOT-IN-SEL"),
                ("rules", "#glow #glowderma @glowderma_ksa serum"), ("disclosure", "#ad"),
                ("destination", "https://glow.example.com/shop"), ("starts", "2026-11-01"), ("ends", "2026-11-30"), ("notes", "Wave one")]
        import urllib.parse
        data = urllib.parse.urlencode(form).encode()
        import urllib.request
        req = urllib.request.Request(self.base + "/campaigns/setup", data=data, method="POST",
                                                           headers={"Origin": self.base, "Content-Type": "application/x-www-form-urlencoded"})
        try:
            resp = a.op.open(req)
        except Exception as exc:        # NoRedirect raises on the 303
            resp = exc
        self.assertEqual(resp.code if hasattr(resp, "code") else resp.status, 303)
        made = [k for k in db.list_campaigns() if k["id"] not in before]
        self.assertEqual(len(made), 1)
        k = db.campaign(made[0]["id"])
        self.assertEqual((k["status"], k["selection_id"], k["code_id"]), ("draft", sel["id"], sel["code_id"]))
        self.assertEqual(k["name"], "Make 9 — wave 1")
        self.assertEqual(k["client"], "Glow Derma")
        self.assertEqual(k["platform"], "Instagram")
        self.assertEqual(k["objective"], "awareness+traffic")
        self.assertEqual(k["destination"], "https://glow.example.com/shop")
        rules = db.rules_of(k)
        self.assertEqual(rules["hashtags"], ["#glow", "#glowderma"])
        self.assertEqual(rules["mentions"], ["@glowderma_ksa"])
        self.assertEqual(rules["keywords"], ["serum"])
        self.assertEqual(rules["disclosure"], ["#ad"])
        self.assertTrue(k["starts_at"] and k["ends_at"] and k["ends_at"] > k["starts_at"])
        carried = [m["cc_code"] for m in db.campaign_creators(k["id"])]
        self.assertEqual(sorted(carried), ["HV-MI-001", "HV-MI-002"])           # ticked ones, and only ones in the selection
        self.assertEqual(len(db.campaign_links(k["id"])), 2)                    # a tracking link per creator, as before
        # still a draft: the client sees no change, and the existing go-live moves the chip
        self.assertEqual(self.state(c, tok)["key"], "requested")
        s, _b, r = a.req("POST", "/campaigns/status", form={"id": k["id"], "status": "live"})
        self.assertEqual(self.state(c, tok)["key"], "live")
        self.assertTrue(any(i["kind"] == "camp_live" for i in self.bell(c)["items"]))
        a.req("POST", "/campaigns/status", form={"id": k["id"], "status": "ended"})
        self.assertEqual(self.state(c, tok)["key"], "completed")

    def test_12_single_goal_blank_name_and_no_creators_are_refused(self):
        c, tok, sel, u = self.prepared("bad9@glowderma.com", "Bad 9")
        self.request_quote(c, tok)
        a = self.admin()
        before = len(db.list_campaigns())
        s, _b, r = a.req("POST", "/campaigns/setup", form={"selection": sel["id"], "name": "", "code": "HV-MI-001"})
        self.assertIn("e=", r.headers["Location"])
        s, _b, r = a.req("POST", "/campaigns/setup", form={"selection": sel["id"], "name": "No creators"})
        self.assertIn("e=", r.headers["Location"])
        s, _b, r = a.req("POST", "/campaigns/setup", form={"selection": sel["id"], "name": "x", "code": "HV-MI-001",
                                                           "destination": "javascript:alert(1)"})
        self.assertIn("e=", r.headers["Location"])
        self.assertEqual(len(db.list_campaigns()), before)
        s, _b, r = a.req("POST", "/campaigns/setup", form={"selection": sel["id"], "name": "Engage", "code": "HV-MI-001", "goal": "engagement"})
        k = db.campaign(int(r.headers["Location"].split("id=")[1].split("&")[0]))
        self.assertEqual(k["objective"], "engagement")
        self.assertIsNone(k["platform"])                                       # none chosen: every platform

    def test_13_admin_only(self):
        c, tok, sel, u = self.prepared("adm9@glowderma.com", "Admin 9")
        self.request_quote(c, tok)
        # a client (signed in to the portal) cannot open or post the admin pages
        s, _b, r = c.req("GET", "/campaigns/setup?selection=%d" % sel["id"])
        self.assertIn(s, (302, 303, 401, 403))
        before = len(db.list_campaigns())
        s, _b, r = c.req("POST", "/campaigns/setup", form={"selection": sel["id"], "name": "Hax", "code": "HV-MI-001"})
        self.assertIn(s, (302, 303, 401, 403))
        self.assertEqual(len(db.list_campaigns()), before)
        s, _b, r = c.req("POST", "/quote/ready", form={"id": sel["id"], "note": "free"})
        self.assertIn(s, (302, 303, 401, 403))
        self.assertEqual(self.state(c, tok)["key"], "requested")
        # a viewer-role team member is refused too
        db.create_admin("view9@hellovoice.co.uk", __import__("auth").hash_password("viewer-pass-9999"))
        import team
        with db.connect() as conn:
            conn.execute("UPDATE admins SET role = 'viewer' WHERE email = ?", ("view9@hellovoice.co.uk",))
        v = Client(self.base)
        s, _b, r = v.req("POST", "/login", form={"email": "view9@hellovoice.co.uk", "password": "viewer-pass-9999"})
        s, _b, r = v.req("POST", "/campaigns/setup", form={"selection": sel["id"], "name": "Viewer", "code": "HV-MI-001"})
        self.assertEqual(s, 403)
        self.assertEqual(len(db.list_campaigns()), before)

    def test_14_admin_pages_show_the_state(self):
        c, tok, sel, u = self.prepared("pg9@glowderma.com", "Pages 9")
        self.request_quote(c, tok)
        a = self.admin()
        s, body, _ = a.get("/requests")
        self.assertEqual(s, 200)
        self.assertIn("Quote status", body)
        self.assertIn("Mark quote ready", body)
        s, body, _ = a.get("/selections/edit?id=%d" % sel["id"])
        self.assertIn("Create campaign", body)
        self.assertIn("lc-pill", body)
        # draft: the form says why Create campaign is not there yet
        c2, _ = self.signup("pg92@glowderma.com")
        t2 = self.selection(c2, "Draft 9")
        s, body, _ = a.get("/selections/edit?id=%d" % db.selection(token=t2)["id"])
        self.assertIn("unlocks once a quote has been requested", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
