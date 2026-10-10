"""Routes for the quote lifecycle and for creating a campaign from a selection (fix batch 9).

Client:  POST /api/selection/quote/approve   {token}      the selection's OWNER approves a ready quote

Admin (behind the admin session, like every other admin page; the role gate in server.py applies):
         POST /quote/ready      id, note, link, back      HelloVoice marks the quote ready
         POST /quote/withdraw   id, back                  take "Quote ready" back (before approval)
         GET  /campaigns/setup  selection                 the four-step form, pre-filled
         POST /campaigns/setup  selection, name, ...      saves a DRAFT campaign linked to the selection
"""
import json
import urllib.parse

import db
import lifecycle
import portal
import metrics

import phase_e_api


class LifecycleMixin(phase_e_api.PhaseEMixin):

    # ----------------------------------------------------------------- client --

    def lifecycle_post(self, path):
        if path != "/api/selection/quote/approve":
            return False
        self.api_quote_approve()
        return True

    def api_quote_approve(self):
        b = self.json_body()
        token = str(b.get("token") or "")
        reader = self.selection_viewer(token)
        if not reader:
            return self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
        sel = db.selection(token=token) if token else None
        if sel is None or (sel["code_id"] is not None and int(reader) != db.admin_code_id()
                           and sel["code_id"] not in portal.team_codes(int(reader))):
            return self.send_json(404, {"ok": False}, self.cors())
        role = self.selection_role(sel, reader)
        if role != "owner":
            owner = portal.user_for_code(sel["code_id"]) if sel["code_id"] else None
            who = owner["name"] if owner is not None and owner["name"] else "the person who owns this selection"
            return self.send_json(403, {"ok": False, "reason": "not_owner",
                                        "message": "Only %s can approve the quote." % who}, self.cors())
        if self._throttled("quote:%d" % int(reader), 30, 600):
            return
        user = portal.user_for_code(int(reader))
        key, err = lifecycle.approve(sel, user["id"] if user is not None else None,
                                     (user["name"] if user is not None and user["name"] else "Client"),
                                     kam=(user["kam"] if user is not None and "kam" in user.keys() else None),
                                     link=self.site_origin() + (self._srv().BASE or "") + "/selections/edit?id=%d" % sel["id"])
        if err:
            return self.send_json(409, {"ok": False, "reason": err, "state": key,
                                        "message": "There is no quote ready to approve yet."}, self.cors())
        db.log("shortlist", int(reader), self.client_ip(), self.headers.get("User-Agent"), "quote:approved:%d" % sel["id"])
        return self.send_json(200, {"ok": True, "lifecycle": lifecycle.client_payload(db.selection(sel["id"]), "owner")}, self.cors())

    # ------------------------------------------------------------------ admin --

    def _quote_selection(self, f):
        sid = (f.get("id") or "").strip()
        return db.selection(int(sid)) if sid.isdigit() else None

    def _admin_name(self):
        a = self.admin()
        return (a["name"] if a is not None and "name" in a.keys() and a["name"] else None) or \
               ((a["email"].split("@")[0].replace(".", " ").title()) if a is not None else "HelloVoice")

    def _back(self, f, sel):
        back = (f.get("back") or "").strip()
        if not back.startswith("/") or back.startswith("//"):
            back = "/selections/edit?id=%d#st=status" % sel["id"]
        return back

    def _go(self, back, kind, msg):
        base, _, frag = back.partition("#")
        sep = "&" if "?" in base else "?"
        return self.redirect(base + sep + kind + "=" + urllib.parse.quote(msg) + (("#" + frag) if frag else ""))

    def post_quote_ready(self):
        f = self.form_body()
        sel = self._quote_selection(f)
        if sel is None:
            return self.redirect("/requests")
        back = self._back(f, sel)
        key, err = lifecycle.set_ready(sel, f.get("note"), f.get("link"), self._admin_name())
        if err == "link":
            return self._go(back, "e", "The quote link must be a full https:// address.")
        if err:
            return self._go(back, "e", "The quote is already approved, so it can no longer be changed here.")
        return self._go(back, "ok", "Quote marked ready. The client's bell tells them; no email is sent to the client.")

    def post_quote_withdraw(self):
        f = self.form_body()
        sel = self._quote_selection(f)
        if sel is None:
            return self.redirect("/requests")
        back = self._back(f, sel)
        key, err = lifecycle.withdraw_ready(sel)
        if err:
            return self._go(back, "e", "Only a quote that is ready and not yet approved can be taken back.")
        return self._go(back, "ok", "Taken back. The selection reads Quote requested again.")

    def _setup_selection(self, raw):
        sid = (raw or "").strip()
        return db.selection(int(sid)) if sid.isdigit() else None

    def get_campaign_setup(self, query):
        import lifecycle_ui
        sel = self._setup_selection(query.get("selection"))
        if sel is None:
            return self.redirect("/selections?e=" + urllib.parse.quote("That selection no longer exists."))
        if lifecycle.state_of(sel)["key"] == "draft":
            return self.redirect("/selections/edit?id=%d&e=%s" % (sel["id"], urllib.parse.quote(
                "A campaign can be created once the client has requested a quote.")))
        return self.send(200, lifecycle_ui.setup_page(sel, lifecycle_ui.setup_defaults(sel), query.get("e")))

    def post_campaign_setup(self):
        """Saves the stepper form as a DRAFT campaign linked to the selection. It reuses
        db.create_campaign (creators, costs, tracking links) and db.save_campaign (objective, rules):
        going live stays the existing action."""
        import re
        f = self.form_body(multi=("code", "platform", "goal"))
        sel = self._setup_selection(f.get("selection"))
        if sel is None:
            return self.redirect("/selections?e=" + urllib.parse.quote("That selection no longer exists."))
        if lifecycle.state_of(sel)["key"] == "draft":
            return self.redirect("/selections/edit?id=%d&e=%s" % (sel["id"], urllib.parse.quote(
                "A campaign can be created once the client has requested a quote.")))
        back = "/campaigns/setup?selection=%d" % sel["id"]

        def fail(msg):
            return self.redirect(back + "&e=" + urllib.parse.quote(msg))

        name = " ".join((f.get("name") or "").split())[:120]
        if not name:
            return fail("Give the campaign a name.")
        known = {c["code"] for c in db.list_creators()}
        in_sel = set(json.loads(sel["codes"] or "[]"))
        codes = [c.strip().upper() for c in (f.get("code") or [])]
        codes = [c for c in dict.fromkeys(codes) if c in known and c in in_sel]
        if not codes:
            return fail("Tick at least one creator.")
        plats = [p for p in (f.get("platform") or []) if p in db.PLATFORMS]
        platform = plats[0] if len(plats) == 1 else None
        goals = [g for g in (f.get("goal") or []) if g in metrics.GOAL_KEYS]
        objective = metrics.blend_key(goals) or "balanced"
        destination = (f.get("destination") or "").strip()
        if destination and not re.match(r"^https?://[^\s/]+\.[^\s]+$", destination):
            return fail("The destination must be a full web address starting with https://")
        starts, ends = (f.get("starts") or "").strip(), (f.get("ends") or "").strip()
        t_start = db.day_bounds(starts, None) if starts else None
        t_end = db.day_bounds(ends, None) if ends else None
        if (starts and t_start is None) or (ends and t_end is None):
            return fail("That date is not valid.")
        if t_end is not None:
            t_end += 86400 - 1
        if t_start is not None and t_end is not None and t_end < t_start:
            return fail("The last day is before the first day.")
        rules = db.parse_rules(f.get("rules"))
        told = db.parse_rules(f.get("disclosure"))
        rules["disclosure"] = told["hashtags"] + told["keywords"]
        keys = sel.keys()
        costs = {k: v for k, v in json.loads((sel["costs"] if "costs" in keys else None) or "{}").items() if isinstance(v, int)}
        notes = " ".join((f.get("notes") or "").split())[:600]
        if len(plats) > 1:
            notes = ("Platforms: " + ", ".join(plats) + (". " + notes if notes else ""))
        cid = db.create_campaign(name, client=(f.get("client") or "").strip()[:120] or None, code_id=sel["code_id"],
                                 selection_id=sel["id"], platform=platform, codes=codes,
                                 costs={k: v for k, v in costs.items() if k in codes})
        db.save_campaign(cid, objective=objective, rules=rules, destination=destination or None,
                         starts_at=t_start, ends_at=t_end, notes=notes or None)
        return self.redirect("/campaigns/edit?id=%d&ok=%s" % (cid, urllib.parse.quote(
            "Draft campaign created from the selection. Finish its setup, then set it live: the client's chip becomes Campaign live.")))
