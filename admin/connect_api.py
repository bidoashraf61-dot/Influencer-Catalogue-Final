"""HTTP routes for HELVY Connect phases C + D, as a mixin on ``Handler`` (through PortalMixin).

Client routes
    POST /api/tour                 {action: offered|later|started|done} -> state (+5 credits once on done)
    POST /api/roi/estimate         {goal, budget, platforms, market, token?, which?, mix?} -> the calculator's result (free)
    POST /api/roi/save             {token, goal, budget, platforms, market, which?|mix?} -> kept with the selection
    GET  /api/roi/saved?s=token    the latest estimate kept with a selection
    GET  /api/roi/vs[?t=token]     saved estimate against the live report, per campaign the viewer may see
    GET  /api/roi/selections       the viewer's selections to save an estimate to (name, token)
    POST /api/selection/more       {token, note, chips, count}   Add more like these   (credits: more)
    POST /api/selection/alike      {token, code, again}          Creators like this    (credits: alike)

Every AI price goes through portal.charge, which makes it free while the client has an
active campaign. The ROI Calculator is deterministic and free for everyone.
"""
import json

import aimore
import phase_e_api
import db
import portal
import rewards
import roi


class ConnectMixin(phase_e_api.PhaseEMixin):

    def connect_get(self, path, query):
        if self.phase_e_get(path, query):
            return True
        if path == "/api/roi/saved":
            got = self._roi_selection(query.get("s") or "")
            if got:
                sel, cid = got
                self.send_json(200, {"ok": True, "saved": roi.row_view(roi.latest_for(sel["id"]))}, self.cors())
            return True
        if path == "/api/roi/vs":
            who = self._need_viewer()
            if who:
                self.send_json(200, {"ok": True, "items": self._roi_versus(who[0], query.get("t") or "")},
                               self.cors() + [("Cache-Control", "no-store")])
            return True
        if path == "/api/roi/selections":
            who = self._need_viewer()
            if who:
                cid = who[0]
                ids = sorted(portal.team_codes(cid))
                with db.connect() as conn:
                    rows = conn.execute("SELECT name, token, codes FROM selections WHERE code_id IN (%s) ORDER BY updated_at DESC LIMIT 40"
                                        % ",".join("?" * len(ids)), ids).fetchall()
                self.send_json(200, {"ok": True, "items": [{"name": r["name"], "token": r["token"],
                                                             "creators": len(json.loads(r["codes"] or "[]"))} for r in rows]}, self.cors())
            return True
        return False

    def connect_post(self, path):
        if self.phase_e_post(path):
            return True
        fn = {"/api/tour": self.api_tour, "/api/roi/estimate": self.api_roi_estimate, "/api/roi/save": self.api_roi_save,
              "/api/selection/more": self.api_selection_more, "/api/selection/alike": self.api_selection_alike}.get(path)
        if not fn:
            return False
        fn()
        return True

    # ------------------------------------------------------------------ tour --

    def api_tour(self):
        who = self._need_account()
        if not who:
            return
        cid, user = who
        action = str(self.json_body().get("action") or "")
        if action == "done":
            paid = rewards.tour_finished(user)
            return self.send_json(200, {"ok": True, "tour": "done", "earned": paid, "credits": portal.balance(cid)}, self.cors())
        if action not in rewards.TOUR_STATES:
            return self.send_json(400, {"ok": False, "reason": "action"}, self.cors())
        return self.send_json(200, {"ok": True, "tour": rewards.set_tour(user, action)}, self.cors())

    # ------------------------------------------------------------------- ROI --

    def _roi_selection(self, token):
        """(selection, viewer code) the viewer may read, or None after answering."""
        token = str(token or "").strip()
        reader = self.selection_viewer(token) if token else None
        if not reader:
            self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
            return None
        sel = db.selection(token=token)
        if sel is None or (sel["code_id"] is not None and int(reader) != db.admin_code_id()
                           and sel["code_id"] not in portal.team_codes(int(reader))):
            self.send_json(404, {"ok": False}, self.cors())
            return None
        return sel, int(reader)

    def _roi_input(self, b):
        goal = b.get("goal") if b.get("goal") in roi.GOALS else "awareness"
        plats = [p for p in (b.get("platforms") or []) if p in roi.PLATFORMS][:4] or ["Instagram"]
        market = b.get("market") if b.get("market") in roi.MARKETS else "SA"
        mix = {t: max(0, min(self._int((b.get("mix") or {}).get(t)), 200)) for t in roi.TIER_ORDER} if isinstance(b.get("mix"), dict) else None
        which = "all" if b.get("which") == "all" else "approved"
        return {"goal": goal, "budget": b.get("budget"), "platforms": plats, "market": market, "mix": mix, "which": which}

    def api_roi_estimate(self):
        who = self._need_viewer()
        if not who:
            return
        if self._throttled("roi:%d" % who[0], 240, 600):
            return
        b = self.json_body()
        inp = self._roi_input(b)
        creators = None
        if b.get("token") and not inp["mix"]:
            got = self._roi_selection(b.get("token"))
            if not got:
                return
            creators = roi.creators_of(got[0], inp["which"])
        res = roi.estimate(inp["goal"], inp["budget"], inp["platforms"], inp["market"], creators=creators,
                           mix=inp["mix"] if creators is None else None)
        return self.send_json(200, {"ok": True, "result": res}, self.cors())

    def api_roi_save(self):
        b = self.json_body()
        got = self._roi_selection(b.get("token"))
        if not got:
            return
        sel, reader = got
        if self._throttled("roisave:%d" % reader, 60, 600):
            return
        inp = self._roi_input(b)
        creators = None if inp["mix"] else roi.creators_of(sel, inp["which"])
        res = roi.estimate(inp["goal"], inp["budget"], inp["platforms"], inp["market"], creators=creators, mix=inp["mix"])
        u = portal.user_for_code(reader)
        rid = roi.save(reader, sel["id"], inp["goal"], {k: v for k, v in inp.items() if v is not None}, res,
                       by=(u["name"] if u is not None and u["name"] else "HelloVoice" if reader == db.admin_code_id() else "Client"))
        return self.send_json(200, {"ok": True, "id": rid, "selection": sel["name"]}, self.cors())

    def _roi_versus(self, cid, token):
        ids = portal.team_codes(cid) if cid != db.admin_code_id() else None
        with db.connect() as conn:
            if token:
                rows = conn.execute("SELECT * FROM campaigns WHERE token = ?", (token,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM campaigns WHERE status != 'draft' AND selection_id IS NOT NULL ORDER BY id DESC LIMIT 20").fetchall()
        out = []
        for k in rows:
            if ids is not None and k["code_id"] not in ids:
                continue
            try:
                v = roi.versus(k)
            except Exception:
                v = None
            if v:
                out.append(v)
        return out

    # ------------------------------------------------------- AI on selections --

    def _ai_target(self, b, need_code=False):
        """(sel, reader, role) for an AI action on a selection, owner or HelloVoice only."""
        token = str(b.get("token") or "")
        reader = self.selection_viewer(token)
        if not reader:
            self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
            return None
        sel = db.selection(token=token) if token else None
        if sel is None or (sel["code_id"] is not None and int(reader) != db.admin_code_id()
                           and sel["code_id"] not in portal.team_codes(int(reader))):
            self.send_json(404, {"ok": False}, self.cors())
            return None
        role = self.selection_role(sel, reader)
        if role == "viewer":
            self.send_json(403, {"ok": False, "reason": "not_owner",
                                 "message": "Only the person who owns this selection can add creators to it."}, self.cors())
            return None
        return sel, int(reader), role

    def _charged(self, reader, role, kind, ref):
        if role != "owner":
            return True, 0
        ok, cost, _ = portal.charge(reader, kind, ref)
        if not ok:
            self.send_json(402, {"ok": False, "reason": "no_credits", "balance": portal.balance(reader),
                                 "cost": portal.costs().get(kind, 1),
                                 "message": "You're out of credits. Request more from your profile."}, self.cors())
            return False, 0
        return True, cost

    def api_selection_more(self):
        """Add more like these: Helvy studies the approved creators and adds more that match
        to Under review, for the owner to decide."""
        b = self.json_body()
        got = self._ai_target(b)
        if not got:
            return
        sel, reader, role = got
        if self._throttled("more:%d" % reader, 20, 3600):
            return
        note = " ".join(str(b.get("note") or "").split())[:160]
        chips = [c for c in (b.get("chips") or []) if c in aimore.QUICK][:4]
        count = max(1, min(self._int(b.get("count"), 5), aimore.MAX_COUNT))
        ok, cost = self._charged(reader, role, "more", "Helvy: add more like these")
        if not ok:
            return
        try:
            picks, err = aimore.more(sel, self.selection_objective(sel), self.selection_target(sel), note, chips, count)
        except Exception:
            picks, err = [], "failed"
        if not picks:
            portal.refund(reader, cost, "no creators added")
            msg = {"no_seeds": "Approve a few creators first, so Helvy knows what you like."}.get(
                err, "Helvy found no one close enough. Try fewer filters, or ask your account manager.")
            return self.send_json(200, {"ok": True, "added": [], "message": msg, "spent": 0,
                                        "credits": portal.balance(reader) if role == "owner" else None}, self.cors())
        sel = db.selection(sel["id"])
        codes = json.loads(sel["codes"] or "[]")
        new = [p["code"] for p in picks if p["code"] not in codes]
        import assistant
        assistant._save_codes(sel, codes + new)
        aimore.record_more(sel, reader, note, chips, new)
        db.log("shortlist", reader, self.client_ip(), self.headers.get("User-Agent"), "more:%d" % len(new))
        shown = {r["code"]: r for r in self.roster_payload(only=set(new))}
        why = {p["code"]: p["why"] for p in picks}
        return self.send_json(200, {"ok": True, "added": [dict(shown[c], why=why.get(c, "")) for c in new if c in shown],
                                    "spent": cost, "free": portal.ai_free(reader) is not None,
                                    "credits": portal.balance(reader) if role == "owner" else None}, self.cors())

    def api_selection_alike(self):
        """Creators like this: three look-alikes of one card. Kept, so reopening is free;
        "again" finds three more (and costs again)."""
        b = self.json_body()
        got = self._ai_target(b)
        if not got:
            return
        sel, reader, role = got
        code = str(b.get("code") or "").strip().upper()
        if code not in json.loads(sel["codes"] or "[]"):
            return self.send_json(404, {"ok": False, "reason": "not_in_selection"}, self.cors())
        before = aimore.kept(sel["id"], code)
        cost = 0
        if before and not b.get("again"):
            picks = [{"code": c, "why": ""} for c in before[-3:]]
            roster = {c["code"]: c for c in db.list_creators(active_only=True)}
            me = roster.get(code)
            picks = [{"code": p["code"], "why": aimore.reason(roster[p["code"]], me) if me is not None and p["code"] in roster else ""}
                     for p in picks]
        else:
            if self._throttled("alike:%d" % reader, 30, 3600):
                return
            ok, cost = self._charged(reader, role, "alike", "Helvy: creators like " + code)
            if not ok:
                return
            picks = aimore.alike(sel, code, shown=set(before))
            if not picks:
                portal.refund(reader, cost, "no look-alikes found")
                return self.send_json(200, {"ok": True, "creators": [], "spent": 0,
                                            "message": "Helvy found no one else close enough to this creator."}, self.cors())
            aimore.keep(sel["id"], code, before + [p["code"] for p in picks])
        shown = {r["code"]: r for r in self.roster_payload(only={p["code"] for p in picks})}
        return self.send_json(200, {"ok": True, "creators": [dict(shown[p["code"]], why=p["why"]) for p in picks if p["code"] in shown],
                                    "spent": cost, "free": portal.ai_free(reader) is not None,
                                    "credits": portal.balance(reader) if role == "owner" else None}, self.cors())
