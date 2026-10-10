"""HTTP routes for HELVY Connect phase E, as a mixin on ``Handler`` (through ConnectMixin).

Client routes
    POST /api/brief/source         {url} or {file: {name, data: base64 / data-URL}} -> the filled brief to review
                                    (credits: source; free during an active campaign; nothing is saved, the file is dropped)
    GET  /api/timing?c=cat,cat&m=SA&t=timing&l=YYYY-MM   launch windows from the occasions calendar (free)
    GET  /api/ideas?c=CODE[&s=token]                      kept ideas + the client's selections holding the creator
    POST /api/ideas                {code, token?, again}  2-3 content ideas, AR + EN (credits: ideas)
    GET  /api/campaign/next?t=token                       the "Next time" panel of an ended campaign

The weekly bell update and the Next time bell are made by weekly.py (a timer in the
admin service), not by a route.
"""
import json

import briefsrc
import db
import gemini
import gating
import ideas
import matcher
import occasions
import portal

MAX_UPLOAD_BODY = briefsrc.MAX_FILE * 4 // 3 + 64 * 1024        # base64 + the JSON around it


class PhaseEMixin:

    def phase_e_get(self, path, query):
        if path == "/api/timing":
            who = self._need_viewer()
            if who:
                cats = [c for c in str(query.get("c") or "").split(",") if c in matcher._enum("category")][:6]
                market = query.get("m") if query.get("m") in matcher._enum("market") else "SA"
                timing = query.get("t") if query.get("t") in matcher._enum("timing") else None
                self.send_json(200, dict(occasions.advise(cats, market, timing, str(query.get("l") or "")[:10]), ok=True), self.cors())
            return True
        if path == "/api/ideas":
            self.api_ideas_get(query)
            return True
        if path == "/api/campaign/next":
            k, status = self.viewer_campaign(str(query.get("t") or "")[:40])
            if k is None:
                self.send_json(status, {"ok": False}, self.cors())
                return True
            import weekly
            data = weekly.panel(k)
            if data and data.get("instead"):
                shown = {r["code"]: r for r in self.roster_payload(only=set(data["instead"]))}
                data = dict(data, instead=[{k2: shown[c].get(k2) for k2 in ("code", "name", "photo_url", "followers", "platform", "city", "tier")}
                                           for c in data["instead"] if c in shown])
            self.send_json(200, {"ok": True, "ended": weekly.ended(k), "next": data}, self.cors() + [("Cache-Control", "no-store")])
            return True
        return False

    def phase_e_post(self, path):
        fn = {"/api/brief/source": self.api_brief_source, "/api/ideas": self.api_ideas}.get(path)
        if not fn:
            return False
        fn()
        return True

    # ------------------------------------------------------- brief from a source --

    def api_brief_source(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > MAX_UPLOAD_BODY:
            # Never kept: drained in small pieces (so the browser gets this answer, not a broken
            # pipe) up to 16 MB, then the connection is closed.
            self.close_connection = True
            left = min(length, 16 * 1024 * 1024)
            while left > 0:
                chunk = self.rfile.read(min(65536, left))
                if not chunk:
                    break
                left -= len(chunk)
            return self.send_json(413, {"ok": False, "reason": "too_big", "message": briefsrc.MESSAGES["too_big"]}, self.cors())
        who = self._need_viewer()
        if not who:
            return
        cid, user, kind = who
        if self._throttled("source:%d" % cid, 20, 3600):
            return
        b = self.json_body()
        f = b.get("file") if isinstance(b.get("file"), dict) else None
        url = str(b.get("url") or "").strip()
        if not f and not url:
            return self.send_json(400, {"ok": False, "reason": "empty", "message": "Paste a link or choose a file."}, self.cors())
        # 1. Read the source: free, and nothing is charged when it cannot be read.
        try:
            if f:
                data = briefsrc.decode_upload(f.get("data"))
                got = briefsrc.from_file(f.get("name"), data)
                del data                                   # the upload is not kept anywhere
                origin = "uploaded brief “%s”" % got["label"]
            else:
                got = briefsrc.from_url(url)
                origin = got["label"]
        except briefsrc.SourceError as exc:
            return self.send_json(400, {"ok": False, "reason": exc.reason, "message": exc.message}, self.cors())
        src = {"kind": "file" if f else "link", "label": got["label"], "format": got["kind"], "chars": got["chars"],
               "title": got.get("title") or ""}
        db.log("brief_source", cid, self.client_ip(), self._ua(), ("file " if f else "link ") + got["label"][:60])
        # 2. No AI key: the free keyword reader still fills what the text says plainly.
        if not gemini.configured():
            answers, _ = matcher.guess(got["text"][:3000])
            answers["notes"] = (("Product: " + src["title"] + ". ") if src["title"] else "") + "From " + origin
            return self.send_json(200, {"ok": True, "ai": False, "source": src, "answers": answers,
                                        "fields": {"product": src["title"][:80], "brand": "", "audience": "", "markets": [answers["market"]] if answers.get("market") else [], "launch": ""},
                                        "confidence": {k: ("low" if (answers.get(k) if k != "product" else src["title"]) else "missing") for k in briefsrc.SCHEMA_FIELDS},
                                        "claims": [], "regulated": briefsrc.regulated_kind(got["text"], answers.get("category")),
                                        "flags": [], "timing": occasions.advise(answers.get("category") or [], answers.get("market") or "SA"),
                                        "spent": 0, "credits": portal.balance(cid) if kind != "admin" else None}, self.cors())
        # 3. Gemini fills the brief; charged first, refunded on failure.
        if kind == "guest":
            portal.ensure_allowance(cid)
        ok, cost, bal = portal.charge(cid, "source", "brief from " + src["kind"])
        if not ok:
            return self._no_credits(cid, "source")
        try:
            res = briefsrc.read(got["text"], origin, code_id=cid, credits=cost)
        except gemini.AIError as exc:
            portal.refund(cid, cost, "failed brief read")
            return self._ai_fail(exc)
        except Exception:
            portal.refund(cid, cost, "failed brief read")
            raise
        res.update({"ok": True, "ai": True, "source": src, "spent": cost, "free": portal.ai_free(cid) is not None,
                    "credits": portal.balance(cid) if kind != "admin" else None})
        return self.send_json(200, res, self.cors())

    # ------------------------------------------------------------ content ideas --

    def _ideas_target(self, code, token):
        """(creator code, selection or None, reader) the viewer may draft ideas for, or None after answering."""
        code = str(code or "").strip().upper()[:24]
        token = str(token or "").strip()[:40]
        if token:
            reader = self.selection_viewer(token)
            sel = db.selection(token=token) if reader else None
            if not reader:
                self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
                return None
            if sel is None or (sel["code_id"] is not None and int(reader) != db.admin_code_id()
                               and sel["code_id"] not in portal.team_codes(int(reader))):
                self.send_json(404, {"ok": False}, self.cors())
                return None
            if code not in json.loads(sel["codes"] or "[]"):
                self.send_json(404, {"ok": False, "reason": "not_in_selection"}, self.cors())
                return None
            reader = int(reader)
        else:
            who = self._need_viewer()
            if not who:
                return None
            reader, sel = who[0], None
        c = db.creator(code)
        if c is None or not c["active"]:
            self.send_json(404, {"ok": False, "reason": "creator"}, self.cors())
            return None
        return code, sel, reader

    def api_ideas_get(self, query):
        got = self._ideas_target(query.get("c"), query.get("s"))
        if not got:
            return
        code, sel, reader = got
        sels = gating.selections_with(reader, code) if reader != db.admin_code_id() else []
        if sel is None and sels:
            sel = db.selection(token=sels[0]["token"])
        hit = ideas.kept(ideas.scope_of(sel, reader), code)
        return self.send_json(200, {"ok": True, "code": code, "ideas": (hit or {}).get("ideas") or [], "at": (hit or {}).get("at"),
                                    "selection": {"name": sel["name"], "token": sel["token"]} if sel is not None else None,
                                    "selections": sels[:12], "cost": portal.price_of(reader, "ideas"),
                                    "ai": gemini.configured()}, self.cors())

    def api_ideas(self):
        b = self.json_body()
        token = b.get("token")
        got = self._ideas_target(b.get("code"), token)
        if not got:
            return
        code, sel, reader = got
        if sel is None and reader != db.admin_code_id():
            sels = gating.selections_with(reader, code)
            if sels:
                sel = db.selection(token=sels[0]["token"])
        scope = ideas.scope_of(sel, reader)
        hit = ideas.kept(scope, code)
        if hit and hit.get("ideas") and not b.get("again"):
            return self.send_json(200, {"ok": True, "ideas": hit["ideas"], "kept": True, "spent": 0,
                                        "credits": portal.balance(reader) if reader != db.admin_code_id() else None}, self.cors())
        if not gemini.configured():
            return self.send_json(503, {"ok": False, "reason": "not_configured", "message": "Helvy can't write ideas right now."}, self.cors())
        if self._throttled("ideas:%d" % reader, 30, 3600):
            return
        ok, cost, _ = portal.charge(reader, "ideas", "Helvy: content ideas for " + code)
        if not ok:
            return self.send_json(402, {"ok": False, "reason": "no_credits", "balance": portal.balance(reader),
                                        "cost": portal.costs().get("ideas", 2),
                                        "message": "You're out of credits. Request more from your profile."}, self.cors())
        user = portal.user_for_code(reader)
        prof = None
        if user is not None:
            import account
            prof = account.profile(user)
        ctx = ideas.context(code, reader, sel, prof)
        try:
            out = ideas.generate(ctx, code_id=reader, credits=cost)
        except gemini.AIError as exc:
            portal.refund(reader, cost, "failed content ideas")
            return self._ai_fail(exc)
        except Exception:
            portal.refund(reader, cost, "failed content ideas")
            raise
        if not out:
            portal.refund(reader, cost, "no usable content ideas")
            return self.send_json(200, {"ok": True, "ideas": [], "spent": 0,
                                        "message": "Helvy couldn't write ideas that fit the rules this time. Please try again."}, self.cors())
        ideas.keep(scope, code, out, ideas.brief_key(ctx))
        db.log("ideas", reader, self.client_ip(), self._ua(), code)
        return self.send_json(200, {"ok": True, "ideas": out, "spent": cost, "free": portal.ai_free(reader) is not None,
                                    "used_style": bool(ctx.get("style")),
                                    "credits": portal.balance(reader) if reader != db.admin_code_id() else None}, self.cors())
