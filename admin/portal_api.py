"""HTTP routes for the client portal and the admin AI pages, as a mixin.

``Handler`` in server.py inherits ``PortalMixin``; the methods here use the same
helpers (``send_json``, ``cors``, ``viewer_code_id`` ...) and take the module-level
constants (secret, cookie names) from the server module through ``self._srv()``.

Public (client) routes
    GET  /api/me                 who am I, credits, prices
    GET  /api/brief/questions    the MCQ
    GET  /api/chat/history       this client's recent chat
    POST /api/auth/start         email -> one-time code by email (company domains only)
    POST /api/auth/verify        email + code -> signed in, or "finish your profile"
    POST /api/auth/profile       name / company -> account created, signed in
    POST /api/auth/logout
    POST /api/me/update          edit profile
    POST /api/brief/parse        free text -> MCQ answers   (credits)
    POST /api/brief/run          MCQ answers -> scored selection (credits)
    POST /api/chat               ask the assistant          (credits)

Admin routes (signed-in admin only)
    GET  /ai, /portal            copilot page, accounts & AI settings
    POST /ai/chat, /ai/confirm, /ai/dismiss
    POST /portal/...             account, credit and setting changes
"""
import json
import sys
import time
import urllib.parse

import assistant
import db
import fx
import gemini
import guard
import mailer
import matcher
import notify
import portal
import portal_views

_score_cache = {}          # brief id -> (time, scores) for the catalogue's fit badges

REASON_TEXT = {
    "invalid": "Enter a valid work email address.",
    "personal": "Please use your company email address. Personal addresses such as Gmail or Outlook can't be used.",
    "blocked": "That email domain can't be used here. Contact us if you think this is a mistake.",
    "closed": "New sign-ups are closed right now. Please contact the HelloVoice team.",
    "not_invited": "Your company hasn't been invited yet. Please contact the HelloVoice team to get access.",
}
OTP_FAIL_TEXT = {
    "invalid": "That code isn't right.",
    "expired": "That code has expired. Request a new one.",
    "locked": "Too many wrong tries. Request a new code.",
}
AI_FAIL = {
    "not_configured": (503, "The assistant isn't available right now."),
    "budget": (503, "The assistant is resting for now. Please try again later."),
    "busy": (503, "The assistant is busy. Try again in a moment."),
    "upstream": (502, "The assistant couldn't answer. You weren't charged."),
}


class PortalMixin:
    # ------------------------------------------------------------ plumbing --

    def _srv(self):
        return sys.modules[type(self).__module__]

    def _ua(self):
        return self.headers.get("User-Agent")

    def _identity(self):
        """(code_id, user_row or None, kind) for the current viewer."""
        cid = self.viewer_code_id()
        if cid is None:
            return None, None, None
        if cid == db.admin_code_id():
            return cid, None, "admin"
        user = portal.user_for_code(cid)
        return cid, user, ("user" if user else "guest")

    def _me_payload(self, cid, user, kind):
        if kind == "guest":
            portal.ensure_allowance(cid)
        if kind == "user":
            portal.monthly_refill(cid)
        out = {"signed_in": True, "kind": kind, "credits": portal.balance(cid) if kind != "admin" else None,
               "costs": portal.costs(), "ai": gemini.configured()}
        if user:
            out["user"] = {k: user[k] for k in ("email", "name", "company", "job_title", "phone")}
            out["team"] = [{"name": t["name"], "job_title": t["job_title"]} for t in portal.teammates(cid)]
            out["monthly_credits"] = portal.monthly_allowance(user)
        return out

    def _issue_pass(self, row, extra=None):
        """Mint the viewer ticket for a code row — what ``/api/unlock`` does for a
        typed passcode, used here for signed-in clients. Returns the response."""
        srv = self._srv()
        import auth
        import secrets
        ua = self._ua()
        token = self.cookies().get(srv.DEVICE_COOKIE, "")
        if len(token) < 20:
            token = secrets.token_urlsafe(24)
        device = db.device_hash(token)
        ok, why = db.code_state(row)
        if not ok:
            return self.send_json(403, {"ok": False, "reason": why}, self.cors())
        admitted, why = db.admit_device(row, device, self.client_ip(), ua)
        if not admitted:
            db.log("unlock_fail", row["id"], self.client_ip(), ua, why)
            return self.send_json(403, {"ok": False, "reason": why,
                                        "message": "This account is already signed in on its maximum number of devices."},
                                  self.cors())
        db.bump_code_use(row["id"])
        db.log("unlock_ok", row["id"], self.client_ip(), ua, "sign-in")
        expiry = db.now() + srv.VIEWER_TTL
        ticket = auth.sign("%d:%d:%s" % (row["id"], expiry, device), srv.SECRET)
        policy = "SameSite=None; Secure" if srv.ALLOWED_ORIGINS else "SameSite=Lax"
        cookie = f"{srv.VIEWER_COOKIE}={ticket}; Path=/; HttpOnly; {policy}; Max-Age={srv.VIEWER_TTL}"
        dev = f"{srv.DEVICE_COOKIE}={token}; Path=/; HttpOnly; {policy}; Max-Age={srv.DEVICE_TTL}"
        user = portal.user_for_code(row["id"])
        # No roster here: the page reloads after sign-in and fetches it once, the normal way.
        payload = {"ok": True, "step": "done", "me": self._me_payload(row["id"], user, "user" if user else "guest")}
        payload.update(extra or {})
        return self.send_json(200, payload, self.cors() + [("Set-Cookie", cookie), ("Set-Cookie", dev)])

    def _code_row(self, code_id):
        with db.connect() as conn:
            return conn.execute("SELECT * FROM codes WHERE id = ?", (code_id,)).fetchone()

    def _throttled(self, key, limit, window, hit=True):
        """True (and a 429 sent) when ``key`` is over its limit. Records the attempt unless
        ``hit`` is False (the sign-in code counts only mails actually sent)."""
        if not guard.limiter.allow(key, limit, window):
            self.too_many(guard.limiter.retry_after(key, limit, window))
            return True
        if hit:
            guard.limiter.hit(key)
        return False

    @staticmethod
    def _int(v, default=0):
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    def _need_viewer(self):
        cid, user, kind = self._identity()
        if cid is None:
            self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
            return None
        return cid, user, kind

    # ----------------------------------------------------------- public GET --

    def portal_get(self, path, query):
        """Handle a public portal GET. Returns True if the path was ours."""
        if path == "/api/me":
            cid, user, kind = self._identity()
            if cid is None:
                # email_signin: only offer the email gate once mail can actually be sent,
                # so clients with an access code never see a sign-in that cannot work yet.
                self.send_json(200, {"ok": True, "signed_in": False, "ai": gemini.configured(),
                                     "signup": portal.signup_mode(),
                                     "email_signin": mailer.configured()}, self.cors())
            else:
                self.send_json(200, dict(self._me_payload(cid, user, kind), ok=True), self.cors())
            return True
        if path == "/api/brief/questions":
            self.send_json(200, {"ok": True, "questions": matcher.public_questions(), "costs": portal.costs()}, self.cors())
            return True
        if path == "/api/credits":
            who = self._need_viewer()
            if who:
                cid = who[0]
                self.send_json(200, {"ok": True, "balance": portal.balance(cid), "costs": portal.costs(),
                                     "ledger": [{"delta": r["delta"], "reason": r["reason"], "at": r["at"]}
                                                for r in portal.ledger(cid, 30)]}, self.cors())
            return True
        if path == "/api/briefs":
            who = self._need_viewer()
            if who:
                self.send_json(200, {"ok": True, "briefs": [
                    {"id": b["id"], "summary": b["summary"], "objective": b["objective"], "at": b["created_at"],
                     "selection": (db.selection(b["selection_id"])["token"] if b["selection_id"] and db.selection(b["selection_id"]) else None)}
                    for b in portal.briefs_for(who[0], 20)]}, self.cors())
            return True
        if path == "/api/brief/for":
            who = self._need_viewer()
            if who:
                sel = db.selection(token=query.get("s") or "") if query.get("s") else None
                if sel is None or (sel["code_id"] is not None and sel["code_id"] not in portal.team_codes(who[0])
                                   and who[0] != db.admin_code_id()):
                    self.send_json(404, {"ok": False}, self.cors())
                else:
                    with db.connect() as conn:
                        b = conn.execute("SELECT id, summary FROM briefs WHERE selection_id = ? ORDER BY id DESC LIMIT 1",
                                         (sel["id"],)).fetchone()
                    self.send_json(200, {"ok": True, "brief": dict(b) if b else None}, self.cors())
            return True
        if path == "/api/brief/scores":
            who = self._need_viewer()
            if who:
                b = portal.brief(self._int(query.get("b")))
                if b is None or (b["code_id"] not in portal.team_codes(who[0]) and who[0] != db.admin_code_id()):
                    self.send_json(404, {"ok": False}, self.cors())
                else:
                    self.send_json(200, {"ok": True, "brief": b["summary"], "scores": self._brief_scores(b)}, self.cors())
            return True
        if path == "/api/team":
            who = self._need_viewer()
            if who:
                cid = who[0]
                team = portal.team_codes(cid) - {cid}
                sels = []
                if team:
                    with db.connect() as conn:
                        sels = conn.execute(
                            "SELECT s.name, s.token, s.codes, s.updated_at, u.name owner FROM selections s JOIN users u ON u.code_id = s.code_id "
                            "WHERE s.code_id IN (%s) AND s.archived_at IS NULL ORDER BY s.updated_at DESC LIMIT 30" % ",".join("?" * len(team)),
                            list(team)).fetchall()
                self.send_json(200, {"ok": True, "members": [{"name": t["name"], "job_title": t["job_title"]} for t in portal.teammates(cid)],
                                     "selections": [{"name": s["name"], "token": s["token"], "owner": s["owner"], "at": s["updated_at"],
                                                     "creators": len(json.loads(s["codes"] or "[]"))} for s in sels]}, self.cors())
            return True
        if path == "/api/me/export":
            who = self._need_viewer()
            if who:
                if who[2] != "user":
                    self.send_json(400, {"ok": False, "reason": "no_profile"}, self.cors())
                else:
                    self.send(200, json.dumps(portal.export(who[0]), indent=2, ensure_ascii=False), "application/json; charset=utf-8",
                              self.cors() + [("Content-Disposition", "attachment; filename=my-hellovoice-data.json")])
            return True
        if path == "/api/chat/history":
            who = self._need_viewer()
            if who:
                cid, user, kind = who
                t = portal.find_thread(cid, "client", "", self._int(query.get("t"))) if (query.get("t") or "").isdigit() else None
                msgs = [{"role": m["role"], "text": m["content"]} for m in portal.messages(t["id"], 40)] if t else []
                self.send_json(200, {"ok": True, "thread": t["id"] if t else None, "messages": msgs}, self.cors())
            return True
        return False

    # ---------------------------------------------------------- public POST --

    def portal_post(self, path):
        """Handle a public portal POST. Returns True if the path was ours."""
        routes = {
            "/api/auth/start": self.api_auth_start, "/api/auth/verify": self.api_auth_verify,
            "/api/auth/profile": self.api_auth_profile, "/api/auth/logout": self.api_auth_logout,
            "/api/me/update": self.api_me_update, "/api/brief/parse": self.api_brief_parse,
            "/api/brief/run": self.api_brief_run, "/api/chat": self.api_chat,
            "/api/brief/guess": self.api_brief_guess, "/api/brief/attach": self.api_brief_attach,
            "/api/credits/request": self.api_credits_request, "/api/me/delete": self.api_me_delete,
        }
        fn = routes.get(path)
        if not fn:
            return False
        fn()
        return True

    # ------------------------------------------------------------------ auth --

    def api_auth_start(self):
        b = self.json_body()
        email, why = portal.check_email(b.get("email"))
        if why:
            return self.send_json(400, {"ok": False, "reason": why, "message": REASON_TEXT.get(why, "Can't use that email.")}, self.cors())
        ip = self.client_ip()
        # Per address, per email, and a global ceiling that protects the sender's reputation.
        domain = email.rsplit("@", 1)[1]
        if (self._throttled("otp:ip:" + ip, 12, 3600, hit=False) or self._throttled("otp:em:" + email, 6, 3600, hit=False)
                or self._throttled("otp:dom:" + domain, 40, 3600, hit=False)
                or self._throttled("otp:all", 400, 3600, hit=False)):
            return
        if not mailer.configured():
            return self.send_json(503, {"ok": False, "reason": "mail_not_configured",
                                        "message": "Email sign-in isn't available yet. Please use your access code."}, self.cors())
        code, wait = portal.new_otp(email, ip)
        if wait:
            return self.send_json(200, {"ok": True, "sent": False, "wait": portal.OTP_RESEND_SECONDS}, self.cors())
        for k in ("otp:ip:" + ip, "otp:em:" + email, "otp:dom:" + domain, "otp:all"):
            guard.limiter.hit(k)
        try:
            subject, text, html = mailer.otp_message(code, portal.OTP_MINUTES)
            mailer.send(email, subject, text, html)
        except mailer.MailError as exc:
            db.log("otp_mail_fail", None, ip, self._ua(), str(exc)[:80])
            return self.send_json(502, {"ok": False, "reason": "mail_failed",
                                        "message": "We couldn't send the email. Please try again shortly."}, self.cors())
        db.log("otp_sent", None, ip, self._ua(), email.rsplit("@", 1)[1])
        return self.send_json(200, {"ok": True, "sent": True, "minutes": portal.OTP_MINUTES,
                                    "resend_in": portal.OTP_RESEND_SECONDS}, self.cors())

    def api_auth_verify(self):
        b = self.json_body()
        email = guard.normalise_email(b.get("email"))
        ip = self.client_ip()
        if not email:
            return self.send_json(400, {"ok": False, "reason": "invalid", "message": OTP_FAIL_TEXT["invalid"]}, self.cors())
        keys = ("otpv:ip:" + ip, "otpv:em:" + email)
        if not (guard.limiter.allow(keys[0], 20, 600) and guard.limiter.allow(keys[1], 10, 600)):
            return self.too_many(guard.limiter.retry_after(keys[1], 10, 600))
        ok, why = portal.check_otp(email, b.get("otp"))
        if not ok:
            for k in keys:
                guard.limiter.hit(k)
            db.log("otp_fail", None, ip, self._ua(), why)
            return self.send_json(400, {"ok": False, "reason": why, "message": OTP_FAIL_TEXT.get(why, "That code isn't right.")}, self.cors())
        user = portal.user_by_email(email)
        if user:
            return self._enter(user)
        # New address: it must still be an allowed company domain, then a profile is needed.
        _, why = portal.check_email(email)
        if why:
            return self.send_json(400, {"ok": False, "reason": why, "message": REASON_TEXT.get(why)}, self.cors())
        domain = email.rsplit("@", 1)[1]
        return self.send_json(200, {"ok": True, "step": "profile", "email": email,
                                    "ticket": portal.sign_ticket(self._srv().SECRET, email),
                                    "suggested_company": domain.split(".")[0].replace("-", " ").title()}, self.cors())

    def _enter(self, user):
        """Sign an existing account in, or say why it can't be."""
        if user["status"] == "suspended":
            return self.send_json(403, {"ok": False, "reason": "suspended",
                                        "message": "This account is suspended. Please contact the HelloVoice team."}, self.cors())
        if user["status"] == "pending":
            return self.send_json(200, {"ok": True, "step": "pending",
                                        "message": "Thanks. Your account is waiting for approval by the HelloVoice team. "
                                                   "We'll email you as soon as it's ready."}, self.cors())
        portal.touch_login(user["id"])
        return self._issue_pass(self._code_row(user["code_id"]))

    def api_auth_profile(self):
        b = self.json_body()
        email = portal.read_ticket(self._srv().SECRET, b.get("ticket"))
        if not email:
            return self.send_json(400, {"ok": False, "reason": "expired", "message": "That step expired. Please sign in again."}, self.cors())
        user = portal.user_by_email(email)
        if user:
            return self._enter(user)
        name = " ".join(str(b.get("name") or "").split())
        company = " ".join(str(b.get("company") or "").split())
        if len(name) < 2 or len(company) < 2:
            return self.send_json(400, {"ok": False, "reason": "profile", "message": "Please enter your name and company."}, self.cors())
        _, why = portal.check_email(email)
        if why:
            return self.send_json(400, {"ok": False, "reason": why, "message": REASON_TEXT.get(why)}, self.cors())
        if portal.signups_from(self.client_ip()) >= portal.signups_per_ip():
            return self.send_json(429, {"ok": False, "reason": "too_many_accounts",
                                        "message": "Too many accounts were created from this network today. Please contact the HelloVoice team."}, self.cors())
        user = portal.create_user(email, name, company, b.get("job_title"), b.get("phone"), self.client_ip())
        db.log("signup", user["code_id"], self.client_ip(), self._ua(), email.rsplit("@", 1)[1])
        notify.send("signup", ["%s (%s) from %s signed up." % (user["name"], user["email"], user["company"]),
                               "Job title: %s" % (user["job_title"] or "—"), "Phone: %s" % (user["phone"] or "—")])
        return self._enter(user)

    def api_auth_logout(self):
        srv = self._srv()
        policy = "SameSite=None; Secure" if srv.ALLOWED_ORIGINS else "SameSite=Lax"
        return self.send_json(200, {"ok": True}, self.cors() + [
            ("Set-Cookie", f"{srv.VIEWER_COOKIE}=; Path=/; HttpOnly; {policy}; Max-Age=0")])

    def api_me_update(self):
        who = self._need_viewer()
        if not who:
            return
        cid, user, kind = who
        if kind != "user":
            return self.send_json(400, {"ok": False, "reason": "no_profile"}, self.cors())
        b = self.json_body()
        u = portal.update_profile(user["id"], name=b.get("name"), company=b.get("company"),
                                  job_title=b.get("job_title"), phone=b.get("phone"))
        return self.send_json(200, {"ok": True, "user": {k: u[k] for k in ("email", "name", "company", "job_title", "phone")}}, self.cors())

    # ----------------------------------------------------------------- brief --

    def _ai_fail(self, exc):
        code, msg = AI_FAIL.get(getattr(exc, "reason", ""), (502, "The assistant couldn't answer. You weren't charged."))
        return self.send_json(code, {"ok": False, "reason": exc.reason, "message": msg}, self.cors())

    def _no_credits(self, cid, kind):
        return self.send_json(402, {"ok": False, "reason": "no_credits", "balance": portal.balance(cid),
                                    "cost": portal.costs().get(kind, 1),
                                    "message": "You're out of AI credits. Contact the HelloVoice team to top up."}, self.cors())

    def _brief_scores(self, b):
        """{code: [score, tag, basis]} for every creator against a stored brief. Free and cached a
        while, so the catalogue can badge every card."""
        hit = _score_cache.get(b["id"])
        if hit and time.time() - hit[0] < 600:
            return hit[1]
        answers, _ = matcher.clean_answers(json.loads(b["answers"] or "{}"))
        out = {i["code"]: [i["score"], i["tag"], i["basis"]] for i in matcher.score_all(matcher.to_brief(answers))}
        if len(_score_cache) > 50:
            _score_cache.clear()
        _score_cache[b["id"]] = (time.time(), out)
        return out

    def api_brief_attach(self):
        """A client built a selection by hand and answers the brief questions for it: free. The
        selection takes the brief's objective and audience, so its page scores against them."""
        who = self._need_viewer()
        if not who:
            return
        cid, user, kind = who
        b = self.json_body()
        sel = db.selection(token=str(b.get("token") or "")) if b.get("token") else None
        if sel is None or (sel["code_id"] is not None and sel["code_id"] not in portal.team_codes(cid) and cid != db.admin_code_id()):
            return self.send_json(404, {"ok": False, "reason": "unknown"}, self.cors())
        answers, missing = matcher.clean_answers(b.get("answers"))
        if missing:
            return self.send_json(400, {"ok": False, "reason": "missing", "missing": missing}, self.cors())
        if self._throttled("attach:%d" % cid, 30, 3600):
            return
        brief = matcher.to_brief(answers)
        db.set_selection_objective(sel["id"], brief["objective"])
        db.set_selection_target(sel["id"], brief["target"])
        codes = json.loads(sel["codes"] or "[]")
        items = matcher.score_all(brief, only=set(codes))
        text = matcher.describe(answers)
        bid = portal.save_brief(cid, user["id"] if user else None, "selection", answers, text, brief["objective"], brief["target"],
                                sel["id"], {"codes": codes})
        db.log("brief", cid, self.client_ip(), self._ua(), ("selection: " + text)[:80])
        notify.send("brief", ["%s described the campaign for their selection “%s” (%d creators)." % (
            (user["company"] or user["email"]) if user else "A client", sel["name"], len(codes)), text],
            kam=user["kam"] if user else None)
        shown = {r["code"]: r for r in self.roster_payload(only=set(codes))}
        return self.send_json(200, {"ok": True, "brief_id": bid, "brief": text, "token": sel["token"], "name": sel["name"],
                                    "picks": [dict(i, why="", creator=shown.get(i["code"])) for i in items],
                                    "totals": {"n": len(items)}, "narrated": False, "summary": "", "alternates": []}, self.cors())

    def api_credits_request(self):
        who = self._need_viewer()
        if not who:
            return
        cid, user, kind = who
        if kind == "admin":
            return self.send_json(400, {"ok": False}, self.cors())
        b = self.json_body()
        amount = max(1, min(self._int(b.get("amount"), 50), 10000))
        if self._throttled("creditreq:%d" % cid, 3, 86400):
            return
        rid = portal.request_credits(cid, amount, b.get("note"))
        notify.send("credits", ["%s asked for %d more AI credits." % ((user["company"] or user["email"]) if user else "An access-code client", amount),
                                "Note: %s" % (b.get("note") or "—")], kam=user["kam"] if user else None)
        return self.send_json(200, {"ok": True, "id": rid,
                                    "message": "Request sent. The HelloVoice team will top you up shortly."}, self.cors())

    def api_me_delete(self):
        who = self._need_viewer()
        if not who:
            return
        cid, user, kind = who
        if kind != "user":
            return self.send_json(400, {"ok": False, "reason": "no_profile"}, self.cors())
        if str(self.json_body().get("confirm") or "") != "DELETE":
            return self.send_json(400, {"ok": False, "reason": "confirm", "message": "Type DELETE to confirm."}, self.cors())
        portal.delete_account(user["id"])
        db.log("account_deleted", cid, self.client_ip(), self._ua(), None)
        return self.api_auth_logout()

    def api_brief_guess(self):
        """Free: the answers a message already gives, so the chat only asks what is missing."""
        who = self._need_viewer()
        if not who:
            return
        if self._throttled("guess:%d" % who[0], 120, 600):
            return
        answers, missing = matcher.guess(str(self.json_body().get("text") or "")[:1500])
        return self.send_json(200, {"ok": True, "answers": answers, "missing": missing}, self.cors())

    def api_brief_parse(self):
        who = self._need_viewer()
        if not who:
            return
        cid, user, kind = who
        text = " ".join(str(self.json_body().get("text") or "").split())[:1500]
        if len(text) < 8:
            return self.send_json(400, {"ok": False, "reason": "short", "message": "Describe the campaign in a sentence or two."}, self.cors())
        if not gemini.configured():
            return self.send_json(503, {"ok": False, "reason": "not_configured", "message": AI_FAIL["not_configured"][1]}, self.cors())
        if self._throttled("parse:%d" % cid, 20, 3600):
            return
        ok, cost, bal = portal.charge(cid, "parse", "brief text")
        if not ok:
            return self._no_credits(cid, "parse")
        try:
            answers = matcher.parse_request(text, cid)
        except gemini.AIError as exc:
            portal.refund(cid, cost, "failed brief read")
            return self._ai_fail(exc)
        return self.send_json(200, {"ok": True, "answers": answers, "credits": portal.balance(cid)}, self.cors())

    def api_brief_run(self):
        who = self._need_viewer()
        if not who:
            return
        cid, user, kind = who
        b = self.json_body()
        answers, missing = matcher.clean_answers(b.get("answers"))
        if missing:
            return self.send_json(400, {"ok": False, "reason": "missing", "missing": missing,
                                        "message": "Please answer the highlighted questions."}, self.cors())
        if self._throttled("brief:%d" % cid, 12, 3600):
            return
        costs = portal.costs()
        if kind == "guest":
            portal.ensure_allowance(cid)
        # Reserve the credits BEFORE any model tokens are spent, so parallel requests cannot all
        # pass a balance check and then be charged once. Asked for the full price; if the balance
        # only covers the plain shortlist, that is what runs.
        want_ai = gemini.configured()
        kind_paid = "brief" if want_ai else "search"
        ok, cost, bal = portal.charge(cid, kind_paid, "AI shortlist")
        if not ok and want_ai:
            kind_paid = "search"
            ok, cost, bal = portal.charge(cid, kind_paid, "AI shortlist")
        if not ok:
            return self._no_credits(cid, "search")
        try:
            brief = matcher.to_brief(answers)
            result = matcher.rank(brief)
            if not result["picks"]:
                portal.refund(cid, cost, "no creators matched")
                return self.send_json(200, {"ok": True, "empty": True, "message":
                                            "No creators matched. Try fewer filters or another platform.",
                                            "credits": portal.balance(cid)}, self.cors())
            summary, reasons, narrated = "", {}, False
            if kind_paid == "brief":
                try:
                    nar = matcher.narrate(matcher.describe(answers) + ((". " + answers["notes"]) if answers.get("notes") else ""), result, cid)
                    summary, reasons, narrated = nar["summary"], nar["reasons"], True
                except gemini.AIError:
                    diff = cost - costs["search"]
                    if diff > 0:
                        portal.refund(cid, diff, "shortlist without AI text")
                        cost -= diff
        except Exception:
            portal.refund(cid, cost, "failed shortlist")
            raise
        bal = portal.balance(cid)

        codes = [p["code"] for p in result["picks"]]
        name = (str(b.get("name") or "").strip() or "AI shortlist") [:100]
        single = brief["platforms"][0] if len(brief["platforms"]) == 1 else None
        sid = db.save_selection(None, name, codes, {}, None, None, None, cid, single)
        db.set_selection_objective(sid, brief["objective"])
        db.set_selection_target(sid, brief["target"])
        text = matcher.describe(answers)
        brief_id = portal.save_brief(cid, user["id"] if user else None, "mcq", answers, text, brief["objective"], brief["target"], sid,
                                     {"codes": codes, "summary": summary})
        db.log("brief", cid, self.client_ip(), self._ua(), text[:80])
        notify.send("brief", ["%s ran an AI shortlist (%d creators)." % ((user["company"] or user["email"]) if user else "A client", len(codes)),
                              text, ("Notes: " + answers["notes"]) if answers.get("notes") else ""], kam=user["kam"] if user else None)
        token = db.selection(sid)["token"]
        shown = {r["code"]: r for r in self.roster_payload(only=set(codes) | {a["code"] for a in result["alternates"]})}
        return self.send_json(200, {
            "ok": True, "token": token, "name": name, "summary": summary, "narrated": narrated, "brief": text, "brief_id": brief_id,
            "objective": brief["objective"], "totals": result["totals"], "pool": result["pool"],
            "picks": [dict(p, why=reasons.get(p["code"], ""), creator=shown.get(p["code"])) for p in result["picks"]],
            "alternates": [dict({k: a[k] for k in ("code", "score", "tag", "basis", "price")}, creator=shown.get(a["code"]))
                           for a in result["alternates"]],
            "spent": cost, "credits": bal if kind != "admin" else None}, self.cors())

    # ------------------------------------------------------------------ chat --

    def api_chat(self):
        who = self._need_viewer()
        if not who:
            return
        cid, user, kind = who
        b = self.json_body()
        text = " ".join(str(b.get("message") or "").split())[:800]
        if not text:
            return self.send_json(400, {"ok": False, "reason": "empty"}, self.cors())
        if not gemini.configured():
            return self.send_json(503, {"ok": False, "reason": "not_configured", "message": AI_FAIL["not_configured"][1]}, self.cors())
        if self._throttled("chat:%d" % cid, 40, 600):
            return
        tid = self._int(b.get("thread")) or None
        ok, cost, bal = portal.charge(cid, "chat", "chat message")
        if not ok:
            return self._no_credits(cid, "chat")
        th = portal.thread(cid, "client", "", tid=tid)
        past = [(m["role"], m["content"]) for m in portal.messages(th["id"], 12)]
        ctx = {"code_id": cid, "user": dict(user) if user else {}}
        brief, _ = matcher.clean_answers(b.get("brief")) if isinstance(b.get("brief"), dict) else ({}, [])
        asked = text
        if brief:
            # The client answered the free questions first; hand the model the whole brief in this one call.
            asked = text + "\n\n[Brief the client filled in: " + matcher.describe(brief) + \
                ((". Notes: " + brief["notes"]) if brief.get("notes") else "") + \
                ". Use suggest_shortlist with exactly these answers if they want creators.]"
        try:
            res = assistant.converse("client", ctx, past, asked, code_id=cid, kind="chat", credits=cost)
        except gemini.AIError as exc:
            portal.refund(cid, cost, "failed chat")
            return self._ai_fail(exc)
        portal.add_message(th["id"], "user", text)
        portal.add_message(th["id"], "model", res["reply"], {"cards": res["cards"]})
        db.log("chat", cid, self.client_ip(), self._ua(), text[:60])
        card_codes = list(dict.fromkeys(res["cards"]))[:12]
        shown = {r["code"]: r for r in self.roster_payload(only=set(card_codes))} if card_codes else {}
        return self.send_json(200, {"ok": True, "reply": res["reply"], "cards": [shown[c] for c in card_codes if c in shown],
                                    "thread": th["id"], "credits": portal.balance(cid) if kind != "admin" else None}, self.cors())

    # =============================================================== admin ==

    def portal_admin_get(self, path, query, who):
        if path == "/ai":
            return self.send(200, portal_views.copilot_page(who["email"] if "email" in who.keys() else "", gemini.configured()))
        if path == "/ai/history":
            owner = who["email"]
            th = portal.find_thread(None, "admin", owner, int(query.get("t") or 0)) if (query.get("t") or "").isdigit() else None
            msgs = [{"role": m["role"], "text": m["content"]} for m in portal.messages(th["id"], 60)] if th else []
            return self.send_json(200, {"ok": True, "thread": th["id"] if th else None, "messages": msgs})
        if path == "/portal/chat":
            th = portal.find_thread_any(self._int(query.get("id")))
            if not th:
                return self.redirect("/portal?tab=chats&e=" + urllib.parse.quote("No such conversation."))
            return self.send(200, portal_views.chat_page(th))
        if path == "/portal/quote":
            sel = db.selection(self._int(query.get("sel")))
            if sel is None:
                return self.redirect("/selections?e=" + urllib.parse.quote("That selection no longer exists."))
            return self.send(200, portal_views.quote_page(sel, self.site_origin()))
        if path == "/portal/usage.csv":
            return self.send(200, portal_views.usage_csv(), "text/csv; charset=utf-8",
                             [("Content-Disposition", "attachment; filename=portal-usage.csv")])
        if path == "/portal":
            return self.send(200, portal_views.portal_page(query.get("tab") or "accounts", query.get("ok"), query.get("e"), query))
        if path == "/portal/user":
            u = portal.user_by_id(int(query.get("id") or 0))
            if not u:
                return self.redirect("/portal?e=" + urllib.parse.quote("No such client."))
            return self.send(200, portal_views.user_page(u, query.get("ok"), query.get("e")))
        return None

    def portal_admin_post(self, path, who):
        email = who["email"] if "email" in who.keys() else "admin"
        if path == "/ai/chat":
            return self.ai_chat(email)
        if path == "/ai/confirm":
            token = str(self.json_body().get("token") or "")
            return self.send_json(200, assistant.confirm(token, email))
        if path == "/ai/dismiss":
            return self.send_json(200, {"ok": assistant.dismiss(str(self.json_body().get("token") or ""), email)})
        if path.startswith("/portal/"):
            return self.portal_form(path, email)
        return None

    def ai_chat(self, email):
        b = self.json_body()
        text = " ".join(str(b.get("message") or "").split())[:2000]
        if not text:
            return self.send_json(400, {"ok": False, "error": "Say something."})
        if not gemini.configured():
            return self.send_json(503, {"ok": False, "error": "Add a Gemini key on the AI settings tab first."})
        if self._throttled("aichat:" + email, 60, 600):
            return
        th = portal.thread(None, "admin", email, tid=self._int(b.get("thread")) or None)
        past = [(m["role"], m["content"]) for m in portal.messages(th["id"], 16)]
        ctx = {"who": email, "code_id": db.admin_code_id()}
        try:
            res = assistant.converse("admin", ctx, past, text, code_id=None, kind="copilot")
        except gemini.AIError as exc:
            return self.send_json(502, {"ok": False, "error": str(exc)})
        portal.add_message(th["id"], "user", text)
        portal.add_message(th["id"], "model", res["reply"], {"queued": res["queued"]})
        return self.send_json(200, {"ok": True, "reply": res["reply"], "queued": res["queued"], "thread": th["id"]})

    def portal_form(self, path, email):
        f = self.form_body()
        back = f.get("back") or "/portal"
        # Only our own pages; no backslashes or control characters (a browser reads /\\x as //x).
        if (not back.startswith(("/portal", "/codes")) or "\\" in back or any(ord(c) < 32 or c == "\x7f" for c in back)):
            back = "/portal"
        sep = "&" if "?" in back else "?"

        def done(msg, ok=True):
            return self.redirect(back + sep + ("ok=" if ok else "e=") + urllib.parse.quote(msg))

        def user_of(f):
            return portal.user_by_id(int(f.get("id") or 0))

        if path == "/portal/user/status":
            u = user_of(f)
            if not u or f.get("status") not in ("active", "suspended", "pending"):
                return done("Unknown client or status.", False)
            portal.set_status(u["id"], f["status"])
            return done("%s is now %s." % (u["email"], f["status"]))
        if path == "/portal/user/credits":
            u = user_of(f)
            try:
                n = int(f.get("amount") or 0)
            except ValueError:
                n = 0
            if not u or n == 0 or abs(n) > 100000:
                return done("Enter a non-zero amount.", False)
            bal = portal.grant(u["code_id"], n, (f.get("reason") or "Admin adjustment")[:100], actor=email)
            return done("Balance for %s is now %d." % (u["email"], bal))
        if path == "/portal/user/save":
            u = user_of(f)
            if not u:
                return done("Unknown client.", False)
            portal.update_profile(u["id"], name=f.get("name"), company=f.get("company"), job_title=f.get("job_title"),
                                  phone=f.get("phone"), notes=f.get("notes"), kam=f.get("kam") or "",
                                  monthly_credits=f.get("monthly_credits", ""))
            return done("Saved.")
        if path == "/portal/user/delete":
            u = user_of(f)
            if not u or f.get("confirm") != "DELETE":
                return done("Type DELETE to confirm.", False)
            portal.delete_account(u["id"])
            return self.redirect("/portal?ok=" + urllib.parse.quote("Account deleted and personal data erased."))
        if path == "/portal/credit-request":
            rid = self._int(f.get("id"))
            grant_n = self._int(f.get("grant")) if f.get("action") == "grant" else 0
            r = portal.handle_credit_request(rid, max(0, min(grant_n, 100000)), email)
            if not r:
                return done("That request was already handled.", False)
            return done("Granted %d credits." % grant_n if grant_n else "Request declined.")
        if path == "/portal/code/credits":
            try:
                cid, n = int(f.get("code_id") or 0), int(f.get("amount") or 0)
            except ValueError:
                return done("Enter numbers.", False)
            if not cid or not n:
                return done("Enter a code and an amount.", False)
            bal = portal.grant(cid, n, (f.get("reason") or "Admin adjustment")[:100], actor=email)
            return done("Balance is now %d." % bal)
        if path == "/portal/settings":
            return self.portal_settings(f, done)
        if path == "/portal/keys":
            return self.portal_keys(f, done)
        return done("Unknown action.", False)

    def portal_settings(self, f, done):
        import history
        def num(key, lo, hi, default):
            try:
                return max(lo, min(hi, int(f.get(key, default))))
            except (TypeError, ValueError):
                return default
        costs = {k: num("cost_" + k, 0, 1000, v) for k, v in portal.DEFAULT_COSTS.items()}
        mode = f.get("signup_mode") if f.get("signup_mode") in ("open", "approval", "allowlist", "closed") else "open"

        def lines(key):
            raw = (f.get(key) or "").replace(",", "\n").split()
            return sorted({d.strip().lower().lstrip("@") for d in raw if "." in d})
        with history.tracked("settings", "all", "Changed client-portal settings"):
            db.set_setting("signup_mode", mode)
            db.set_setting("signup_credits", num("signup_credits", 0, 100000, portal.DEFAULT_SIGNUP_CREDITS))
            db.set_setting("guest_credits", num("guest_credits", 0, 100000, portal.DEFAULT_GUEST_CREDITS))
            db.set_setting("user_max_devices", num("user_max_devices", 1, 50, 5))
            db.set_setting("signups_per_ip_day", num("signups_per_ip_day", 1, 1000, 3))
            db.set_setting("ai_costs", costs)
            db.set_setting("domain_allow", lines("domain_allow"))
            db.set_setting("domain_block", lines("domain_block"))
            db.set_setting("ai_monthly_tokens", num("ai_monthly_tokens", 10000, 1000000000, gemini.DEFAULT_MONTHLY_TOKENS))
            def money(key, default, hi):
                try:
                    return max(0.0, min(hi, float(f.get(key, default))))
                except (TypeError, ValueError):
                    return default
            db.set_setting("ai_monthly_usd", money("ai_monthly_usd", gemini.DEFAULT_MONTHLY_USD, 100000))
            db.set_setting("email_cost_usd", money("email_cost_usd", mailer.DEFAULT_EMAIL_USD, 1))
            cm = (f.get("copilot_model") or "").strip()
            db.set_setting("copilot_model", cm if cm and all(c.isalnum() or c in "-._" for c in cm) else None)
            table = {}
            for line in (f.get("ai_prices") or "").splitlines():
                bits = line.split()
                if len(bits) == 3 and all(c.isalnum() or c in "-._" for c in bits[0]):
                    try:
                        table[bits[0]] = [max(0.0, float(bits[1])), max(0.0, float(bits[2]))]
                    except ValueError:
                        pass
            if table:
                db.set_setting("ai_prices", table)
            model = (f.get("gemini_model") or "").strip()
            if model and all(c.isalnum() or c in "-._" for c in model):
                db.set_setting("gemini_model", model)
            sender = (f.get("mail_from") or "").strip()
            if sender and "@" in sender and "\n" not in sender:
                db.set_setting("mail_from", sender[:120])
            db.set_setting("monthly_credits", num("monthly_credits", 0, 100000, 0))
            db.set_setting("team_sharing", f.get("team_sharing") == "on")
            db.set_setting("notify_emails", sorted({x.strip().lower() for x in (f.get("notify_emails") or "").replace(",", " ").split() if "@" in x}))
            db.set_setting("kams", [l.strip() for l in (f.get("kams") or "").splitlines() if "@" in l][:50])
            kb = (f.get("kb_text") or "").strip()
            db.set_setting("kb_text", kb[:4000] if kb else None)
        return done("Settings saved.")

    def portal_keys(self, f, done):
        which, action = f.get("which"), f.get("action")
        mod = {"gemini": gemini, "mail": mailer}.get(which)
        if not mod:
            return done("Unknown key.", False)
        if action == "clear":
            mod.clear_key()
            return done("Key removed.")
        try:
            mod.save_key(f.get("key"))
        except ValueError as exc:
            return done(str(exc), False)
        return done("Key saved. It is never shown again.")
