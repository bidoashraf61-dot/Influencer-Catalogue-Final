"""End-to-end test of the client portal against a real in-process server.

Runs on a throwaway copy of admin/*.py with an empty database, so it never
touches catalogue.db, .secret or the network: mail is captured and Gemini is a
scripted stub.

    python3 admin/tests/e2e_portal.py
"""
import http.cookiejar
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="hv-e2e-"))
for f in SRC.glob("*.py"):
    shutil.copy(f, TMP / f.name)
shutil.copytree(SRC / "static", TMP / "static", dirs_exist_ok=True)
sys.path.insert(0, str(TMP))

import auth, db, gemini, guard, history, mailer, portal, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


def seed():
    db.init(); history.init(); portal.init()
    db.save_tier("Micro", "MI", 1500, 3000, reach="10-50K")
    db.save_tier("Mid-Tier", "MD", 5000, 9000, reach="50-250K")
    rows = [
        ("HV-MI-001", "Noha Magdy", "noha", "Instagram", 42000, "Riyadh", "Saudi Arabia", "Micro", "Skincare, Beauty"),
        ("HV-MI-002", "Sara Ali", "sara", "Instagram", 38000, "Jeddah", "Saudi Arabia", "Micro", "Health, Wellness"),
        ("HV-MD-003", "Khalid R", "khalid", "TikTok", 160000, "Riyadh", "Saudi Arabia", "Mid-Tier", "Food, Lifestyle"),
        ("HV-MD-004", "Lina H", "lina", "Instagram", 120000, "Dubai", "UAE", "Mid-Tier", "Skincare, Fashion"),
        ("HV-MI-005", "Omar T", "omar", "Instagram", 31000, "Riyadh", "Saudi Arabia", "Micro", "Technology, Gaming"),
    ]
    for code, name, handle, plat, fol, city, nat, tier, interest in rows:
        db.upsert_creator({"code": code, "name": name, "handle": handle, "platform": plat, "followers": fol, "city": city,
                           "nationality": nat, "tier": tier, "interest": interest, "photo": None,
                           "profiles": json.dumps([{"platform": plat, "url": "https://x/" + handle, "followers": fol}]),
                           "active": 1, "note": "", "sort": 0})
    db.create_admin("boss@hellovoice.co.uk", auth.hash_password("correct-horse-battery"))


def stub(body):
    """A scripted Gemini: reads the request and answers like the real one would."""
    last = body["contents"][-1]["parts"][0]
    text = last.get("text", "")
    gen = body.get("generationConfig", {})
    if "functionResponse" in last:
        name = last["functionResponse"]["name"]
        return {"candidates": [{"content": {"parts": [{"text": "Done via " + name}]}}], "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 10}}
    if gen.get("responseSchema"):
        props = gen["responseSchema"].get("properties", {})
        if "reasons" in props:
            codes = [c for c in ("HV-MI-001", "HV-MI-002", "HV-MD-003", "HV-MD-004", "HV-MI-005") if c in text]
            out = {"summary": "A balanced skincare-led mix.", "reasons": [{"code": c, "why": "Fits the brief."} for c in codes] + [{"code": "HV-FAKE-999", "why": "x"}]}
        else:
            out = {"goal": "awareness", "platforms": ["Instagram"], "market": "SA", "category": ["skincare", "NOT-A-CATEGORY"], "count": "5", "budget": "WRONG"}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(out)}]}}], "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 60}}
    if "FAIL" in text:
        raise gemini.Upstream("boom")
    if "campaign for skincare" in text:
        call = {"name": "suggest_shortlist", "args": {"goal": "awareness", "category": ["skincare"], "market": "SA", "count": 3}}
    elif "rename noha" in text:
        call = {"name": "update_creator", "args": {"code": "HV-MI-001", "city": "Dammam"}}
    elif "peek codes" in text:
        call = {"name": "sql_query", "args": {"sql": "select code_plain from codes"}}
    elif "count creators" in text:
        call = {"name": "sql_query", "args": {"sql": "select count(*) as n from creators"}}
    else:
        return {"candidates": [{"content": {"parts": [{"text": "Hello!"}]}}], "usageMetadata": {"promptTokenCount": 30, "candidatesTokenCount": 5}}
    return {"candidates": [{"content": {"parts": [{"functionCall": call}]}}], "usageMetadata": {"promptTokenCount": 60, "candidatesTokenCount": 8}}


class Client:
    def __init__(self, base):
        self.base, self.jar = base, http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), NoRedirect)

    def req(self, method, path, body=None, form=None, headers=None):
        h = {"Origin": self.base}
        h.update(headers or {})
        data = None
        if body is not None:
            data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
        if form is not None:
            data, h["Content-Type"] = urllib.parse.urlencode(form).encode(), "application/x-www-form-urlencoded"
        try:
            r = self.op.open(urllib.request.Request(self.base + path, data=data, method=method, headers=h))
        except urllib.error.HTTPError as exc:
            r = exc
        raw = r.read()
        try:
            return r.status if hasattr(r, "status") else r.code, json.loads(raw), r
        except ValueError:
            return (r.status if hasattr(r, "status") else r.code), raw.decode("utf-8", "replace"), r

    get = lambda self, p, **k: self.req("GET", p, **k)
    post = lambda self, p, b=None, **k: self.req("POST", p, body=b if b is not None else {}, **k)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class Portal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed()
        mailer.CAPTURE = True
        gemini.STUB = stub
        views.set_base("")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()
        mailer.OUTBOX.clear()

    # ----------------------------------------------------------------- helpers
    def signup(self, email="ali@pfizer.com"):
        c = Client(self.base)
        s, b, _ = c.post("/api/auth/start", {"email": email})
        self.assertEqual((s, b["sent"]), (200, True), b)
        code = mailer.OUTBOX[-1]["text"].split("code is ")[1][:6]
        s, b, _ = c.post("/api/auth/verify", {"email": email, "otp": code})
        self.assertEqual(b.get("step"), "profile", b)
        s, b, _ = c.post("/api/auth/profile", {"ticket": b["ticket"], "name": "Ali Hassan", "company": "Pfizer KSA"})
        self.assertEqual((s, b.get("step")), (200, "done"), b)
        return c, b

    def skip_cooldown(self):
        with db.connect() as conn:
            conn.execute("UPDATE otp SET created_at = created_at - 100")

    # --------------------------------------------------------------- the tests
    def test_1_domain_rules(self):
        c = Client(self.base)
        for e in ("someone@gmail.com", "x@outlook.com", "x@mail.yahoo.com", "x@mailinator.com"):
            s, b, _ = c.post("/api/auth/start", {"email": e})
            self.assertEqual((s, b["reason"]), (400, "personal"), e)
        s, b, _ = c.post("/api/auth/start", {"email": "nonsense"})
        self.assertEqual(b["reason"], "invalid")
        self.assertEqual(mailer.OUTBOX, [])

    def test_2_signup_flow_and_credits(self):
        c, b = self.signup("ali@pfizer.com")
        self.assertEqual(b["me"]["credits"], 50)
        self.assertEqual(b["me"]["kind"], "user")
        self.assertEqual(len(b["roster"]), 5)
        s, me, _ = c.get("/api/me")
        self.assertEqual((me["signed_in"], me["user"]["company"]), (True, "Pfizer KSA"))
        # signing in again from a fresh browser: straight in, no profile step, same account
        c2 = Client(self.base)
        self.skip_cooldown()
        c2.post("/api/auth/start", {"email": "ali@pfizer.com"})
        code = mailer.OUTBOX[-1]["text"].split("code is ")[1][:6]
        s, b2, _ = c2.post("/api/auth/verify", {"email": "ali@pfizer.com", "otp": code})
        self.assertEqual(b2["step"], "done")
        # a code works once
        s, b3, _ = Client(self.base).post("/api/auth/verify", {"email": "ali@pfizer.com", "otp": code})
        self.assertEqual(b3["reason"], "invalid")

    def test_3_otp_lockout(self):
        c = Client(self.base)
        c.post("/api/auth/start", {"email": "lock@sanofi.com"})
        good = mailer.OUTBOX[-1]["text"].split("code is ")[1][:6]
        bad = "000000" if good != "000000" else "111111"
        for _ in range(5):
            s, b, _ = c.post("/api/auth/verify", {"email": "lock@sanofi.com", "otp": bad})
            self.assertEqual(s, 400)
        s, b, _ = c.post("/api/auth/verify", {"email": "lock@sanofi.com", "otp": good})
        self.assertEqual((s, b["reason"]), (400, "locked"))

    def test_4_resend_cooldown_and_ratelimit(self):
        c = Client(self.base)
        s, b, _ = c.post("/api/auth/start", {"email": "a@bayer.com"})
        self.assertTrue(b["sent"])
        s, b, _ = c.post("/api/auth/start", {"email": "a@bayer.com"})
        self.assertFalse(b["sent"])
        self.assertEqual(len(mailer.OUTBOX), 1)

    def test_5_brief_run_scores_and_selects(self):
        c, _ = self.signup("br@abbott.com")
        s, q, _ = c.get("/api/brief/questions")
        self.assertTrue(any(x["id"] == "goal" for x in q["questions"]))
        s, b, _ = c.post("/api/brief/run", {"answers": {"goal": "awareness"}})
        self.assertEqual((s, b["reason"]), (400, "missing"))
        ans = {"goal": "awareness", "platforms": ["Instagram"], "market": "SA", "category": ["skincare"], "count": "5", "budget": "400",
               "evil": "<script>"}
        s, b, _ = c.post("/api/brief/run", {"answers": ans, "name": "Skin launch"})
        self.assertEqual(s, 200, b)
        codes = [p["code"] for p in b["picks"]]
        self.assertTrue(set(codes) <= {"HV-MI-001", "HV-MI-002", "HV-MI-005", "HV-MD-004"})
        self.assertNotIn("HV-MD-003", codes)                       # TikTok-only: filtered by platform
        self.assertEqual(codes[0], "HV-MI-001")                     # skincare + Riyadh beats the rest
        self.assertTrue(b["narrated"] and b["picks"][0]["why"])
        self.assertEqual((b["spent"], b["credits"]), (5, 45))
        self.assertTrue(all(p["score"] is not None and p["basis"] == "roster" for p in b["picks"]))
        # the selection is real, owned by this client, and the existing page scores it
        s, sel, _ = c.get("/api/selection?s=" + b["token"])
        self.assertEqual(s, 200, sel)
        self.assertEqual(sorted(sel["codes"] if "codes" in sel else [x["code"] for x in sel["creators"]]), sorted(codes))
        s, briefs, _ = c.get("/api/briefs")
        self.assertIn("Reach as many people", briefs["briefs"][0]["summary"])
        self.assertIn("Saudi Arabia", briefs["briefs"][0]["summary"])
        # another client cannot open it
        other, _ = self.signup("other@gsk.com")
        s, sel2, _ = other.get("/api/selection?s=" + b["token"])
        self.assertNotEqual(s, 200)

    def test_6_credits_run_out_and_refund(self):
        c, b = self.signup("poor@roche.com")
        uid = portal.user_by_email("poor@roche.com")["code_id"]
        portal.grant(uid, -48, "test drain")                       # 2 left
        ans = {"goal": "balanced", "platforms": ["any"], "market": "SA", "category": ["beauty"]}
        s, r, _ = c.post("/api/brief/run", {"answers": ans})       # 2 credits left: shortlist w/o AI text (search = 2)
        self.assertEqual(s, 200, r)
        self.assertFalse(r["narrated"])
        self.assertEqual(portal.balance(uid), 0)
        s, r, _ = c.post("/api/brief/run", {"answers": ans})
        self.assertEqual((s, r["reason"]), (402, "no_credits"))
        portal.grant(uid, 3, "top-up")
        s, r, _ = c.post("/api/chat", {"message": "FAIL please"})  # upstream error -> refunded
        self.assertEqual(s, 502)
        self.assertEqual(portal.balance(uid), 3)

    def test_7_parse_text_validates_model_output(self):
        c, _ = self.signup("parse@bayer.com")
        s, r, _ = c.post("/api/brief/parse", {"text": "We need an awareness campaign for skincare in KSA"})
        self.assertEqual(s, 200, r)
        a = r["answers"]
        self.assertEqual(a["category"], ["skincare"])              # invented category dropped
        self.assertNotIn("budget", a)                              # invalid enum dropped
        self.assertEqual(r["credits"], 49)

    def test_8_chat_uses_tools(self):
        c, _ = self.signup("chat@nahdi.com.sa")
        s, r, _ = c.post("/api/chat", {"message": "I need a campaign for skincare"})
        self.assertEqual(s, 200, r)
        self.assertTrue(r["reply"].startswith("Done via suggest_shortlist"))
        self.assertTrue(r["cards"] and r["cards"][0]["name"] and r["credits"] == 49)
        s, h, _ = c.get("/api/chat/history?t=%d" % r["thread"])
        self.assertEqual([m["role"] for m in h["messages"]], ["user", "model"])
        # a client cannot read admin tools or another client's thread
        other, _ = self.signup("nosy@pfizer.com")
        s, h2, _ = other.get("/api/chat/history?t=%d" % r["thread"])
        self.assertEqual(h2["messages"], [])
        s, r2, _ = c.post("/api/chat", {"message": "peek codes"})
        self.assertNotIn("code_plain", json.dumps(r2))

    def test_9_guest_code_gets_allowance(self):
        code_id = db.create_code(auth.hash_code("Guest Pass 1"), "ss 1", "Guest co", None, None, "Guest Pass 1", 5)
        c = Client(self.base)
        s, b, _ = c.post("/api/unlock", {"code": "Guest Pass 1"})
        self.assertTrue(b["ok"])
        s, me, _ = c.get("/api/me")
        self.assertEqual((me["kind"], me["credits"]), ("guest", 10))

    def test_10_suspend_and_logout(self):
        c, _ = self.signup("sus@pfizer.com")
        s, me, _ = c.get("/api/me")
        self.assertTrue(me["signed_in"])
        u = portal.user_by_email("sus@pfizer.com")
        portal.set_status(u["id"], "suspended")
        s, r, _ = c.get("/api/roster")
        self.assertEqual(s, 401)
        portal.set_status(u["id"], "active")
        self.assertEqual(c.get("/api/roster")[0], 200)
        c.post("/api/auth/logout")
        self.assertEqual(c.get("/api/roster")[0], 401)

    def test_11_approval_mode(self):
        db.set_setting("signup_mode", "approval")
        try:
            c = Client(self.base)
            c.post("/api/auth/start", {"email": "new@sandoz.com"})
            code = mailer.OUTBOX[-1]["text"].split("code is ")[1][:6]
            s, b, _ = c.post("/api/auth/verify", {"email": "new@sandoz.com", "otp": code})
            s, b, _ = c.post("/api/auth/profile", {"ticket": b["ticket"], "name": "Nadia K", "company": "Sandoz"})
            self.assertEqual(b["step"], "pending")
            self.assertEqual(c.get("/api/roster")[0], 401)
            u = portal.user_by_email("new@sandoz.com")
            portal.set_status(u["id"], "active")
            self.assertEqual(portal.balance(u["code_id"]), 50)
        finally:
            db.set_setting("signup_mode", "open")

    def test_12_allowlist_lets_a_personal_domain_through(self):
        db.set_setting("domain_allow", ["gmail.com"])
        try:
            s, b, _ = Client(self.base).post("/api/auth/start", {"email": "boutique@gmail.com"})
            self.assertEqual(s, 200, b)
        finally:
            db.set_setting("domain_allow", [])

    def test_14_closed_mode_only_blocks_new_addresses(self):
        self.signup("existing@lilly.com")
        db.set_setting("signup_mode", "closed")
        try:
            c = Client(self.base)
            s, b, _ = c.post("/api/auth/start", {"email": "stranger@novo.com"})
            self.assertEqual((s, b["reason"]), (400, "closed"))
            s, b, _ = c.post("/api/auth/start", {"email": "existing@lilly.com"})
            self.assertEqual(s, 200, b)
        finally:
            db.set_setting("signup_mode", "open")

    def test_15_email_signin_flag_follows_mail_config(self):
        c = Client(self.base)
        self.assertTrue(c.get("/api/me")[1]["email_signin"])
        mailer.CAPTURE = False
        try:
            self.assertFalse(c.get("/api/me")[1]["email_signin"])
            s, b, _ = c.post("/api/auth/start", {"email": "a@bayer.com"})
            self.assertEqual((s, b["reason"]), (503, "mail_not_configured"))
        finally:
            mailer.CAPTURE = True

    def test_13_csrf_blocks_foreign_origin(self):
        c = Client(self.base)
        s, b, _ = c.req("POST", "/api/auth/start", body={"email": "a@bayer.com"}, headers={"Origin": "https://evil.example"})
        self.assertEqual(s, 403)

    # ------------------------------------------------------------------- admin
    def admin(self):
        c = Client(self.base)
        s, _, r = c.req("POST", "/login", form={"email": "boss@hellovoice.co.uk", "password": "correct-horse-battery"})
        self.assertEqual(s, 303)
        return c

    def test_20_admin_pages_render(self):
        a = self.admin()
        for path in ("/portal", "/portal?tab=briefs", "/portal?tab=usage", "/portal?tab=settings", "/ai", "/codes", "/"):
            s, body, _ = a.get(path)
            self.assertEqual(s, 200, path)
        self.signup("page@pfizer.com")
        u = portal.user_by_email("page@pfizer.com")
        s, body, _ = a.get("/portal/user?id=%d" % u["id"])
        self.assertEqual(s, 200)
        self.assertIn("page@pfizer.com", body)

    def test_21_copilot_write_needs_confirm_and_is_undoable(self):
        a = self.admin()
        s, r, _ = a.post("/ai/chat", {"message": "rename noha to dammam"})
        self.assertEqual(s, 200, r)
        self.assertEqual(db.creator("HV-MI-001")["city"], "Riyadh")        # nothing happened yet
        self.assertEqual(len(r["queued"]), 1)
        tok = r["queued"][0]["token"]
        s, res, _ = a.post("/ai/confirm", {"token": tok})
        self.assertTrue(res["ok"], res)
        self.assertEqual(db.creator("HV-MI-001")["city"], "Dammam")
        rows = history.listing(None, None, limit=5)
        self.assertTrue(any("Copilot" in (r["label"] or "") for r in rows))
        hid = next(r["id"] for r in rows if "Copilot" in (r["label"] or ""))
        ok, _msg = history.undo(hid)
        self.assertTrue(ok)
        self.assertEqual(db.creator("HV-MI-001")["city"], "Riyadh")
        # a token works once
        s, res2, _ = a.post("/ai/confirm", {"token": tok})
        self.assertFalse(res2["ok"])

    def test_22_copilot_sql_is_read_only_and_walled(self):
        a = self.admin()
        s, r, _ = a.post("/ai/chat", {"message": "count creators"})
        self.assertEqual(s, 200)
        out = assistant_sql("select count(*) as n from creators")
        self.assertEqual(out["rows"][0][0], 5)
        for bad in ("select code_plain from codes", "select * from admins", "select value from settings",
                    "delete from creators", "select 1; select 2", "pragma table_info(creators)",
                    "select * from sessions", "select code_hash from otp", "select * from history"):
            self.assertIn("error", assistant_sql(bad), bad)
        self.assertEqual(db.creator("HV-MI-001")["code"], "HV-MI-001")

    def test_23_clients_cannot_reach_admin_routes(self):
        c, _ = self.signup("sneak@pfizer.com")
        for path in ("/portal", "/ai", "/portal/user?id=1"):
            s, _, r = c.get(path)
            self.assertEqual(s, 303, path)                          # bounced to /login
        s, _, _ = c.req("POST", "/ai/chat", body={"message": "hi"})
        self.assertEqual(s, 303)


def assistant_sql(sql):
    import assistant
    return assistant.t_sql_query({}, sql)


if __name__ == "__main__":
    unittest.main(verbosity=2)
