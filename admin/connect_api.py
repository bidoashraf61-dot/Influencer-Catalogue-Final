"""HTTP routes for HELVi Connect phases C + D, as a mixin on ``Handler`` (through PortalMixin).

Client routes
    POST /api/tour                 {action: offered|later|started|done} -> state (+5 credits once on done)
    POST /api/roi/estimate         {goals, platforms, token?, which?, mix?, count?} -> structure vs performance (free; no budget, no prices)
    POST /api/roi/save             {token, goals, platforms, which?|mix?} -> kept with the selection
    GET  /api/roi/saved?s=token    the latest estimate kept with a selection
    GET  /api/roi/vs[?t=token]     saved estimate against the live report, per campaign the viewer may see
    GET  /api/roi/selections       the viewer's selections to save an estimate to (name, token)
    POST /api/selection/alike      {token, code, again}          Creators like this    (credits: alike)
    GET  /api/selection/ai-add, POST /api/selection/ai-add/find|add   Add creators with AI (aiadd_api.py)

Every AI price goes through portal.charge, which makes it free while the client has an
active campaign. The ROI Calculator is deterministic and free for everyone.
"""
import json

import aimore
import aiadd_api
import lifecycle_api
import phase_e_api
import db
import portal
import rewards
import roi


class ConnectMixin(lifecycle_api.LifecycleMixin, aiadd_api.AiAddMixin):

    def connect_get(self, path, query):
        if self.phase_e_get(path, query):
            return True
        if self.aiadd_get(path, query):           # item 178: Add creators with AI
            return True
        if path == "/api/roi/saved":
            got = self._roi_selection(query.get("s") or "")
            if got:
                sel, cid = got
                self.send_json(200, {"ok": True, "saved": roi.row_view(roi.latest_for(sel["id"])),
                                     "seed": self._roi_seed(sel)}, self.cors())
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
                    rows = conn.execute("SELECT name, token, codes FROM selections WHERE code_id IN (%s) AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT 40"
                                        % ",".join("?" * len(ids)), ids).fetchall()
                self.send_json(200, {"ok": True, "items": [{"name": r["name"], "token": r["token"],
                                                             "creators": len(json.loads(r["codes"] or "[]"))} for r in rows]}, self.cors())
            return True
        return False

    def connect_post(self, path):
        if self.lifecycle_post(path):
            return True
        if self.phase_e_post(path):
            return True
        if self.aiadd_post(path):                 # item 178: Add creators with AI
            return True
        fn = {"/api/tour": self.api_tour, "/api/roi/estimate": self.api_roi_estimate, "/api/roi/save": self.api_roi_save,
              "/api/selection/alike": self.api_selection_alike}.get(path)
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

    def _roi_seed(self, sel):
        """Starting values for the calculator from the brief that built or scored this selection
        (goals, platforms, and the number of creators it asked for). None without a brief."""
        br = portal.live_brief_for_selection(sel["id"])
        if br is None:
            # no brief, but the selection may carry an objective (the admin's, or its campaign's)
            import fit
            obj = sel["objective"] if "objective" in sel.keys() else None
            if obj and fit.known_objective(obj):
                parts = fit.parts_of(obj)
                goals = [p.lower() for p in (parts if parts != ["Balanced"] else fit.CAMPAIGN_TYPES)]
                return {"goal": goals[0], "goals": goals, "platforms": ["Instagram", "TikTok"],
                        "platforms_from_brief": False, "summary": ""}
            return None
        try:
            import matcher
            answers, _ = matcher.clean_answers(json.loads(br["answers"] or "{}"))
            return dict(matcher.roi_seed(answers), summary=br["summary"] or "")
        except Exception:
            return None

    def _roi_input(self, b):
        raw_goals = b.get("goals") if isinstance(b.get("goals"), list) else [b.get("goal")]
        goals = [("traffic" if g == "conversion" else g) for g in raw_goals]       # an old client may still send it
        goals = list(dict.fromkeys(g for g in goals if g in roi.GOALS)) or ["awareness"]
        goal = goals[0]
        plats = [p for p in (b.get("platforms") or []) if p in roi.PLATFORMS][:4] or ["Instagram"]
        mix = None
        if isinstance(b.get("mix"), dict):
            m = b["mix"]
            if any(isinstance(v, dict) for v in m.values()):          # a suggested mix: {platform: {size: n}}
                mix = {p: {t: max(0, min(self._int((m.get(p) or {}).get(t)), 200)) for t in roi.TIER_ORDER}
                       for p in plats if isinstance(m.get(p), dict)}
            else:
                mix = {t: max(0, min(self._int(m.get(t)), 200)) for t in roi.TIER_ORDER}
        which = "all" if b.get("which") == "all" else "approved"
        second = [str(c).strip().upper()[:24] for c in (b.get("second_posts") or []) if isinstance(c, str)][:20]
        count = max(0, min(self._int(b.get("count")), roi.COUNT_MAX)) or None      # how many creators the ideal is planned for
        # no budget and no market: the calculator compares structure and performance only
        return {"goal": goal, "goals": goals, "platforms": plats, "mix": mix,
                "which": which, "second_posts": second, "count": count}

    def api_roi_estimate(self):
        who = self._need_viewer()
        if not who:
            return
        if self._throttled("roi:%d" % who[0], 240, 600):
            return
        b = self.json_body()
        inp = self._roi_input(b)
        creators, sel = None, None
        if b.get("token") and not inp["mix"]:
            got = self._roi_selection(b.get("token"))
            if not got:
                return
            sel = got[0]
            creators = roi.creators_of(sel, inp["which"], goals=inp["goals"])
        res = roi.full(inp["goal"], inp["platforms"], creators=creators,
                       mix=inp["mix"] if creators is None else None, goals=inp["goals"],
                       second_posts=inp["second_posts"], sel=sel, count=inp["count"])
        return self.send_json(200, {"ok": True, "result": res}, self.cors())

    def api_roi_save(self):
        b = self.json_body()
        got = self._roi_selection(b.get("token"))
        if not got:
            return
        sel, reader = got
        if not portal.may_edit(reader, sel, db.admin_code_id()):
            return self.send_json(403, {"ok": False, "reason": "not_owner", "message": "Only the person who owns this selection can change it. Colleagues on the same company can view it."}, self.cors())
        if self._throttled("roisave:%d" % reader, 60, 600):
            return
        inp = self._roi_input(b)
        creators = None if inp["mix"] else roi.creators_of(sel, inp["which"], goals=inp["goals"])
        res = roi.full(inp["goal"], inp["platforms"], creators=creators, mix=inp["mix"],
                       goals=inp["goals"], second_posts=inp["second_posts"], sel=sel, with_advice=False, count=inp["count"])
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
            ok, cost = self._charged(reader, role, "alike", "Helvi: creators like " + code)
            if not ok:
                return
            picks = aimore.alike(sel, code, shown=set(before))
            if not picks:
                portal.refund(reader, cost, "no look-alikes found")
                return self.send_json(200, {"ok": True, "creators": [], "spent": 0,
                                            "message": "Helvi found no one else close enough to this creator."}, self.cors())
            aimore.keep(sel["id"], code, before + [p["code"] for p in picks])
        shown = {r["code"]: r for r in self.roster_payload(only={p["code"] for p in picks})}
        return self.send_json(200, {"ok": True, "creators": [dict(shown[p["code"]], why=p["why"]) for p in picks if p["code"] in shown],
                                    "spent": cost, "free": portal.ai_free(reader) is not None,
                                    "credits": portal.balance(reader) if role == "owner" else None}, self.cors())
