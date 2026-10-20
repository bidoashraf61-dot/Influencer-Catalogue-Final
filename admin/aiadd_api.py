"""HTTP routes for item 178, "Add creators with AI" on a selection page (mixed into ConnectMixin).

    GET  /api/selection/ai-add?s=token          the selection's brief (answers to pre-fill, or null),
                                                the price for this viewer, the starting N
    POST /api/selection/ai-add/find             {token, answers, n} -> a preview of N creators not in
                                                the selection yet, with why-chips (credits: brief)
    POST /api/selection/ai-add/add              {token, run, codes} -> the ticked ones join the selection

Who: whoever may add to the selection (its owner, someone it was granted to, HelloVoice and the
client's key account manager), through ConnectMixin._ai_target like "Add more like these".
Price: the AI shortlist's ("brief"; "search" when the AI is off or the balance only covers that),
charged to the owner only, free during an active campaign (ConnectMixin._charged / portal.charge).
Nothing numeric reaches the page: no scores, no audience shares, no roster size.
"""
import json

import aiadd
import db
import gemini
import matcher
import notify
import portal


class AiAddMixin:

    def aiadd_get(self, path, query):
        if path != "/api/selection/ai-add":
            return False
        got = self._ai_target({"token": query.get("s") or ""})
        if not got:
            return True
        sel, reader, role = got
        br = portal.live_brief_for_selection(sel["id"])
        brief = None
        if br is not None:
            try:
                ans = json.loads(br["answers"] or "{}")
            except ValueError:
                ans = {}
            answers, missing = matcher.clean_answers(ans if isinstance(ans, dict) else {})
            if not missing:
                brief = {"summary": br["summary"] or "", "answers": answers}
        kind = self._aiadd_kind()
        cost = portal.price_of(reader, kind) if role == "owner" else 0
        self.send_json(200, {"ok": True, "brief": brief, "cost": cost, "free": cost == 0,
                             "n": aiadd.brief_count(brief["answers"]) if brief else aiadd.DEFAULT_N, "max": aiadd.MAX_N,
                             "inside": len(aiadd.inside(sel)), "role": role,
                             "credits": portal.balance(reader) if role == "owner" else None},
                       self.cors() + [("Cache-Control", "no-store")])
        return True

    def aiadd_post(self, path):
        fn = {"/api/selection/ai-add/find": self.api_aiadd_find, "/api/selection/ai-add/add": self.api_aiadd_add}.get(path)
        if not fn:
            return False
        fn()
        return True

    @staticmethod
    def _aiadd_kind():
        return "brief" if gemini.configured() else "search"

    def api_aiadd_find(self):
        b = self.json_body()
        got = self._ai_target(b)
        if not got:
            return
        sel, reader, role = got
        answers, missing = matcher.clean_answers(b.get("answers"))
        if missing:
            return self.send_json(400, {"ok": False, "reason": "missing", "missing": missing,
                                        "message": "Please answer the highlighted questions."}, self.cors())
        n = aiadd.clamp_n(b.get("n"))
        if self._throttled("aiadd:%d" % reader, 12, 3600):
            return
        # Reserved before any work, like the AI shortlist: its price, or the plain search's when
        # the balance only covers that.
        kind = self._aiadd_kind()
        ok, cost = self._aiadd_charge(reader, kind, sel) if role == "owner" else (True, 0)
        if not ok:
            return
        try:
            picks, brief = aiadd.preview(sel, answers, n)
            self._redact(reader, picks)            # locked analysis evidence out, as on the AI shortlist
        except Exception:
            portal.refund(reader, cost, "failed add with AI")
            raise
        if not picks:
            portal.refund(reader, cost, "no creators to add")
            return self.send_json(200, {"ok": True, "picks": [], "asked": n, "spent": 0,
                                        "message": "Helvi found no one new for this brief. Try fewer power-ups or another platform.",
                                        "credits": portal.balance(reader) if role == "owner" else None}, self.cors())
        codes = [p["code"] for p in picks]
        rows = {c["code"]: c for c in db.creators_by_codes(codes, active_only=True)}
        shown = {r["code"]: r for r in self.roster_payload(only=set(codes))}
        run_id = aiadd.save_run(sel["id"], reader, answers, n, codes, cost)
        # A selection without a brief keeps the one just answered, so next time it starts filled in.
        saved = False
        if portal.live_brief_for_selection(sel["id"]) is None:
            user = portal.user_for_code(reader) if role == "owner" else None
            text = matcher.describe(answers)
            db.set_selection_objective(sel["id"], brief["objective"])
            db.set_selection_target(sel["id"], brief["target"])
            portal.save_brief(reader, user["id"] if user else None, "ai_add", answers, text, brief["objective"], brief["target"],
                              sel["id"], {"codes": json.loads(sel["codes"] or "[]")})
            saved = True
        db.log("brief", reader, self.client_ip(), self.headers.get("User-Agent"), ("ai add: %d" % len(codes))[:80])
        out = []
        for p in picks:
            card = shown.get(p["code"])
            if card is None:
                continue
            item = aiadd.card_pick(p, brief, rows.get(p["code"]))
            item["creator"] = self._pick_card(card)
            item["creator"]["platforms"] = [x for x in str(card.get("platform") or "").replace("|", ",").split(",") if x.strip()][:5]
            out.append(item)
        return self.send_json(200, {"ok": True, "run": run_id, "asked": n, "picks": out, "brief_saved": saved,
                                    "spent": cost, "free": portal.ai_free(reader) is not None,
                                    "credits": portal.balance(reader) if role == "owner" else None},
                              self.cors() + [("Cache-Control", "no-store")])

    def _aiadd_charge(self, reader, kind, sel):
        """The owner pays the AI shortlist's price, falling back to the plain search's."""
        ref = "Helvi: add creators to " + sel["name"][:60]
        ok, cost, _ = portal.charge(reader, kind, ref)
        if not ok and kind == "brief":
            ok, cost, _ = portal.charge(reader, "search", ref)
        if not ok:
            self.send_json(402, {"ok": False, "reason": "no_credits", "balance": portal.balance(reader),
                                 "cost": portal.costs().get("search", 1),
                                 "message": "You're out of credits. Request more from your profile."}, self.cors())
            return False, 0
        return True, cost

    def api_aiadd_add(self):
        b = self.json_body()
        got = self._ai_target(b)
        if not got:
            return
        sel, reader, role = got
        row = aiadd.run(self._int(b.get("run")))
        if row is None or row["selection_id"] != sel["id"]:
            return self.send_json(404, {"ok": False, "reason": "gone", "message": "That search has expired. Run it again."}, self.cors())
        if self._throttled("aiaddput:%d" % reader, 60, 3600):
            return
        sel = db.selection(sel["id"])
        new = aiadd.to_add(row, sel, b.get("codes"))
        if not new:
            return self.send_json(200, {"ok": True, "added": [], "message": "Those creators are already in this selection."}, self.cors())
        import assistant
        before = json.loads(sel["codes"] or "[]")
        assistant._save_codes(sel, before + new, ctx={"code_id": reader} if role == "owner" else None)
        aiadd.mark_added(row["id"], new)
        db.log("shortlist", reader, self.client_ip(), self.headers.get("User-Agent"), "ai add:%d" % len(new))
        user = portal.user_for_code(reader) if role == "owner" else None
        if user is not None:
            notify.send("brief", ["%s added %d creator%s to “%s” with AI." % (user["company"] or user["email"], len(new),
                                                                              "" if len(new) == 1 else "s", sel["name"])],
                        kam=user["kam"])
        return self.send_json(200, {"ok": True, "added": new}, self.cors())
