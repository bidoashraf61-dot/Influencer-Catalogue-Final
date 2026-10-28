"""Helvy's hands: the one bridge from the assistant to the portal's own actions.

Nothing here repeats what an action does. A confirmed call goes back in through
the portal's own door on localhost carrying the admin's session cookie, so the
handler that runs is the handler a click runs: the same permission checks, the
same validation, the same History entry, and the same sentence back. An action
whose rules change in the portal changes here for free.

Four things keep it safe:

  * Nothing runs from the model. Every call is queued and waits for the admin's
    Confirm, like the write tools that came before it.
  * Only what REGISTRY lists can be called, and only with the fields that
    action's own form submits. An unknown action, an unknown field or a missing
    required one is refused before anything is queued, so the model cannot
    invent a route or smuggle an extra value into a form.
  * Forms that save a whole page at once are deliberately left out.
    ``/campaigns/save`` replaces every field it is sent, so a partial submit
    would quietly blank the dates or the brief. Each action below changes one
    thing; a campaign's own fields go through the older update_campaign tool,
    which merges.
  * The cookie comes from the admin's live Confirm request and is never stored.
    The loopback sends no Origin header, which ``guard.origin_ok`` allows for
    server-to-server calls, and it never leaves the machine.

The answer is read back out of the redirect the portal sends a browser: ``?ok=``
is what it would show the admin in green, ``?e=`` what it would show in red.
"""
import http.client
import urllib.parse

TIMEOUT = 120                      # a report or a sync can take a while
_WHERE = {"host": "127.0.0.1", "port": 8900, "base": "/admin"}


def configure(port=None, base=None, host=None):
    """Told by server.py at startup where it is listening."""
    if port:
        _WHERE["port"] = int(port)
    if base is not None:
        _WHERE["base"] = base
    if host:
        _WHERE["host"] = host


# --------------------------------------------------------------- registry --

PLATFORMS = "Instagram, TikTok, Snapchat, YouTube, X, Facebook or Threads"
KINDS = "post, reel, story, video or short"
COUNTS = {"likes": "Likes.", "comments": "Comments.", "views": "Views.",
          "shares": "Shares.", "saves": "Saves."}


def _a(path, about, line, fields, required=(), multi=(), risk="normal", lands=(), defaults=None):
    return {"path": path, "about": about, "line": line, "fields": fields,
            "required": tuple(required), "multi": tuple(multi), "risk": risk,
            "lands": tuple(lands), "defaults": dict(defaults or {})}


REGISTRY = {
    # ---- the campaign itself
    "campaign.create": _a(
        "/campaigns/new",
        "Start a new draft campaign, on its own or filled from a selection (its creators, client and prices come along).",
        "Create the campaign “{name}”",
        {"name": "What to call it.", "selection": "Selection id to build it from (optional).",
         "client": "Client name to show on the report (optional).",
         "code_id": "Access-code id of the client who may open it (optional)."},
        required=("name",), lands=("/campaigns/edit",)),
    "campaign.status": _a(
        "/campaigns/status",
        "Take a campaign live, back offline (draft) or mark it ended. Live needs its first and last day and a client access code.",
        "Set campaign {id} to {status}",
        {"id": "Campaign id.", "status": "draft, live or ended."},
        required=("id", "status")),
    "campaign.sync_from_selection": _a(
        "/campaigns/sync",
        "Pull into the campaign any creator who is in its selection but not yet on it.",
        "Add campaign {id}'s missing creators from its selection",
        {"id": "Campaign id."}, required=("id",)),
    "campaign.delete": _a(
        "/campaigns/delete",
        "Delete a campaign and everything on it. There is no undo for this one.",
        "DELETE campaign {id} and everything on it",
        {"id": "Campaign id."}, required=("id",), risk="high"),

    # ---- filling in the posts
    "post.add": _a(
        "/campaigns/content/add",
        "Add one published post to a campaign from its link ALONE. Send only id and url: the platform, kind, creator, date and "
        "numbers are worked out from the link and read from the platform. Add code, platform, kind, posted or counts only "
        "when the admin gave them or the portal asked. One video shared on several platforms is ONE video: the portal joins "
        "a new link to the creator's same video on another platform (same creator, posted within 12 hours). If it could "
        "not tell, the post is added as its own video: ask the admin whether it is the same video as another post, and if so "
        "group them with post.group. Never leave one video counted twice. Facebook share links (facebook.com/share/...) and "
        "other links without a handle never say who posted: send code with them. When the admin names the creator, or answers "
        "which creator a post is, ALWAYS put that code in the call.",
        "Add the post {url} to campaign {id}",
        dict({"id": "Campaign id.", "url": "The post link, starting https://",
              "code": "Creator code on this campaign, e.g. HV-MC-137. Needed when the link names nobody (Facebook share links); "
                      "always send it when the admin named the creator.",
              "platform": "One of " + PLATFORMS + " (optional: found from the link).",
              "kind": "One of " + KINDS + " (optional: found from the link).",
              "posted": "The day it went up, YYYY-MM-DD.",
              "caption": "The caption (optional)."}, **COUNTS),
        required=("id", "url")),
    "post.add_many": _a(
        "/campaigns/content/bulk",
        "Paste many posts at once for one creator (do=links, one link per line), or a block of numbers for posts already "
        "there (do=numbers, one line each: the post link then likes comments views shares saves).",
        "Add {code}'s pasted posts to campaign {id}",
        {"id": "Campaign id.", "do": "links or numbers.", "text": "One line per post.",
         "code": "Creator code (for do=links).", "platform": "One of " + PLATFORMS + ".",
         "kind": "One of " + KINDS + ".", "posted": "The day they went up, YYYY-MM-DD."},
        required=("id", "do", "text")),
    "post.update": _a(
        "/campaigns/content/update",
        "Change one post: move it between the campaign and other work (do=campaign|other), hide or unhide it "
        "(do=hide|unhide), delete it (do=delete), or save counts by hand (do=metrics with the numbers).",
        "{do} post {content} on campaign {id}",
        dict({"id": "Campaign id.", "content": "The post's id.",
              "do": "campaign, other, hide, unhide, delete or metrics."}, **COUNTS),
        required=("id", "content", "do")),
    "post.group": _a(
        "/campaigns/content/group",
        "Say that several of one creator's posts are the same video on different platforms, or split one back out (do=split).",
        "Group the picked posts on campaign {id}",
        {"id": "Campaign id.", "pick": "The post ids.", "do": "group or split."},
        required=("id", "pick"), multi=("pick",)),
    "post.expected": _a(
        "/campaigns/content/pending",
        "Record what a creator still owes and when their next post is expected, which is what the publishing plan reads.",
        "Save the expected posts on campaign {id}",
        {"id": "Campaign id.", "code": "Creator codes.", "pending_status": "One per creator.",
         "pending_date": "One per creator, YYYY-MM-DD."},
        required=("id", "code"), multi=("code", "pending_status", "pending_date")),

    # ---- tracking links
    "link.edit": _a(
        "/campaigns/link",
        "Point one tracking link somewhere else, or rename its slug.",
        "Change tracking link {slug} on campaign {id}",
        {"id": "Campaign id.", "slug": "The link's slug.",
         "destination": "Where it should land, a full https:// address.",
         "new_slug": "A new slug (optional)."},
        required=("id", "slug")),
    "link.add": _a(
        "/campaigns/link/custom",
        "Add an extra tracking link to a campaign, for a creator or for the campaign as a whole.",
        "Add a tracking link to campaign {id}",
        {"id": "Campaign id.", "destination": "Where it lands, a full https:// address.",
         "code": "Creator code (optional).", "slug": "The slug to use (optional).",
         "label": "What to call it (optional)."},
        required=("id", "destination")),
    "link.toggle": _a(
        "/campaigns/link/toggle",
        "Switch one tracking link off or back on. Taps on a link that is off are told it is not active.",
        "Switch tracking link {slug} on campaign {id}",
        {"id": "Campaign id.", "slug": "The link's slug."},
        required=("id", "slug")),

    # ---- creators' own numbers
    "insight.decide": _a(
        "/campaigns/insights/decide",
        "Approve a creator's uploaded screenshot numbers onto one of their posts, or reject them (do=reject).",
        "Decide insight {insight} on campaign {id}",
        dict({"id": "Campaign id.", "insight": "The insight's id.", "do": "approve or reject.",
              "post": "Which post id the numbers belong to (needed to approve)."}, **COUNTS),
        required=("id", "insight")),

    # ---- client access codes
    "code.create": _a(
        "/codes/new",
        "Issue a new client access code (the passcode a client types). Leave 'custom' empty and one is generated.",
        "Issue a new access code for “{label}”",
        {"label": "The client it is for.", "custom": "A passcode to use instead of a generated one (optional).",
         "days": "Days until it expires, empty for never (optional).", "max_uses": "Most sign-ins (optional).",
         "max_devices": "Most devices (optional).", "credits": "AI credits to start with (optional)."},
        required=("label",), lands=("/codes",)),
    "code.rename": _a(
        "/codes/rename", "Rename the client a code is issued to; cascade=1 also renames it on their selections and campaigns.",
        "Rename client code {id} to “{label}”",
        {"id": "Code id.", "label": "The new client name.", "cascade": "1 to rename it everywhere it shows (optional)."},
        required=("id", "label")),
    "code.limits": _a(
        "/codes/limits", "Set a code's device limit, use limit and last day. An empty value means no limit.",
        "Change the limits on client code {id}",
        {"id": "Code id.", "max_devices": "Most devices.", "max_uses": "Most sign-ins.", "expires": "Last day, YYYY-MM-DD."},
        required=("id",)),
    "code.passcode": _a(
        "/codes/passcode", "Change the passcode a client types. Tell the client the new one afterwards.",
        "Change the passcode of client code {id}",
        {"id": "Code id.", "passcode": "The new passcode."}, required=("id", "passcode")),
    "code.revoke": _a(
        "/codes/revoke", "Revoke a code: that client can no longer sign in with it until it is restored.",
        "Revoke client code {id}", {"id": "Code id."}, required=("id",)),
    "code.restore": _a(
        "/codes/restore", "Restore a revoked code.", "Restore client code {id}", {"id": "Code id."}, required=("id",)),
    "code.archive": _a(
        "/codes/archive", "Move a revoked code to the archive.", "Archive client code {id}", {"id": "Code id."}, required=("id",)),
    "code.unarchive": _a(
        "/codes/unarchive", "Bring a code back from the archive.", "Unarchive client code {id}", {"id": "Code id."}, required=("id",)),
    "code.delete": _a(
        "/codes/delete", "Delete an archived code that nothing is tied to. Asks the admin to confirm it is them again.",
        "DELETE client code {id}", {"id": "Code id."}, required=("id",), risk="high"),

    # ---- selections
    "selection.create": _a(
        "/selections/new", "Start an empty selection for a client (add creators afterwards with the selection tools).",
        "Create the selection “{name}”",
        {"name": "What to call it.", "code_id": "Client code id (optional).",
         "currency": "SAR, USD, AED... (optional, default SAR).", "platform": "Instagram, TikTok... (optional)."},
        required=("name",), lands=("/selections",), defaults={"mode": "scratch"}),
    "selection.rename": _a(
        "/selections/rename", "Rename a selection.", "Rename selection {id} to “{name}”",
        {"id": "Selection id.", "name": "The new name."}, required=("id", "name")),
    "selection.delete": _a(
        "/selections/delete", "Delete a selection. It can be restored from History > Trash.",
        "Delete selection {id}", {"id": "Selection id."}, required=("id",)),

    # ---- undo
    "history.undo": _a(
        "/history/undo", "Undo one change from History (the admin's own undo button). id is the History entry's number.",
        "Undo History entry {id}", {"id": "History entry id.", "kind": "Leave empty."}, required=("id",)),

    # ---- the team
    "team.invite": _a(
        "/team/invite", "Give a colleague admin access; they sign in with an email code. Owner only.",
        "Invite {email} as {role}",
        {"email": "Their work email.", "name": "Their name.", "role": "owner, admin, manager, editor or viewer."},
        required=("email", "role")),
    "team.role": _a(
        "/team/role", "Change what a team member may do. Owner only.", "Make team member {id} a {role}",
        {"id": "Team member id.", "role": "owner, admin, manager, editor or viewer."}, required=("id", "role")),
    "team.disable": _a(
        "/team/disable", "Remove a team member's access.", "Remove access for team member {id}", {"id": "Team member id."}, required=("id",)),
    "team.enable": _a(
        "/team/enable", "Give a removed team member their access back.", "Restore access for team member {id}",
        {"id": "Team member id."}, required=("id",)),
    "team.signout": _a(
        "/team/signout", "Sign a team member out everywhere.", "Sign team member {id} out everywhere",
        {"id": "Team member id."}, required=("id",)),
    "team.reinvite": _a(
        "/team/reinvite", "Email a team member their sign-in invite again.", "Resend the invite to team member {id}",
        {"id": "Team member id."}, required=("id",)),
    "team.reset_2fa": _a(
        "/team/reset2fa", "Reset a team member's two-step sign-in and sign them out.", "RESET two-step sign-in for team member {id}",
        {"id": "Team member id."}, required=("id",), risk="high"),

    # ---- roster
    "roster.industry": _a(
        "/roster/review", "Confirm which industry a creator belongs to (do=confirm, the default) or hide them from clients "
        "as not a fit (do=unfit). For anything else about a creator use update_creator.",
        "{do} industry for creator {code}",
        {"code": "Creator code.", "do": "confirm or unfit.", "ind_main": "The main industry (to confirm).",
         "ind_subs": "Sub-industries (optional).", "ind_also": "Also-fits (optional)."},
        required=("code",), multi=("ind_subs", "ind_also")),
}

AREAS = {"campaign": "The campaign itself: create, go live, delete, pull creators from its selection.",
         "post": "The posts on a campaign: add one or many, edit, hide, delete, group, and what is still expected.",
         "link": "A campaign's tracking links.",
         "insight": "Screenshot numbers a creator sent in.",
         "code": "Client access codes: issue, rename, limits, passcode, revoke, restore, archive, delete.",
         "selection": "Selections: create an empty one, rename, delete.",
         "team": "The HelloVoice team's admin access: invite, roles, remove, sign out, reset two-step.",
         "history": "Undo a change from History.",
         "roster": "A creator's industry confirmation. Other creator edits use update_creator."}


def catalogue(area=""):
    """What the model is shown: every action, or one area's."""
    area = (area or "").strip().lower().rstrip(".")
    out = []
    for name, a in sorted(REGISTRY.items()):
        if area and not name.startswith(area + "."):
            continue
        out.append({"action": name, "does": a["about"],
                    "fields": a["fields"], "required": list(a["required"]),
                    "takes_a_list": list(a["multi"]) or None,
                    "warning": "No undo." if a["risk"] == "high" else None})
    return {"areas": AREAS, "actions": out} if not area else {"actions": out}


# ------------------------------------------------------- any form on a page --
#
# The registry names the actions an admin does most. Everything else the admin can do by hand is a form on
# some page, so the assistant reads that page's forms (names, kinds, choices) and submits one the way a
# click does, through the same handler. It sees the form's structure, never its data, so nothing a client
# typed can ride in on it. Forms that save a whole page at once, and anything about sign-in or secrets, stay out.

NEVER = ("/login", "/logout", "/reauth", "/password", "/account/2fa", "/portal/keys", "/apis/token", "/settings/token",
         "/ai/", "/confirm", "/clients/preview", "/tenants/save")
WHOLE_PAGE = {"/campaigns/save": "update_campaign (it merges)", "/roster/save": "update_creator or add_creator",
              "/tiers/save": "set_tier_price", "/selections/save": "create_selection or the selection's own actions",
              "/settings/save": None, "/evidence/save": None, "/analysis/save": None, "/licences/save": None}
DESTRUCTIVE = ("delete", "remove", "clear", "reset", "purge", "revoke", "abort", "withdraw")


def _path_ok(path):
    path = (path or "").strip()
    if not path.startswith("/") or path.startswith("//") or "\\" in path or ".." in path or "?" in path or "#" in path:
        raise ValueError("path must be a portal path like /requests/handled, with no query string.")
    if any(path == n.rstrip("/") or path.startswith(n) for n in NEVER):
        raise ValueError("%s is about sign-in or secrets, so it is not something the assistant does. The admin does it themselves." % path)
    if path in WHOLE_PAGE:
        use = WHOLE_PAGE[path]
        raise ValueError("%s saves a whole page at once and would blank what is not sent. %s"
                         % (path, ("Use %s." % use) if use else "The admin does this one on the page."))
    return path


def read_forms(page, cookie):
    """The forms on one admin page, structure only: [{action, label, fields: [{name, kind, choices?}]}]."""
    from html.parser import HTMLParser
    page = (page or "").strip()
    if not page.startswith("/") or page.startswith("//") or ".." in page or "\\" in page:
        return {"error": "page must be an admin page path such as /requests or /campaigns/content?id=2."}
    if not cookie:
        return {"error": "No admin session to read the page with. Open the admin once and sign in, then ask again."}
    conn = http.client.HTTPConnection(_WHERE["host"], _WHERE["port"], timeout=30)
    try:
        conn.request("GET", _WHERE["base"] + page, headers={"Cookie": cookie})
        res = conn.getresponse()
        html = res.read(2000000).decode("utf-8", "replace")
        where = res.getheader("Location") or ""
    except OSError as exc:
        return {"error": "The portal did not answer: %s" % exc}
    finally:
        conn.close()
    if res.status in (301, 302, 303):
        return {"error": "That page sent the call to %s, so there is nothing to read there." % (where or "another page")}
    if res.status >= 400:
        return {"error": "The portal answered %d for that page." % res.status}

    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.forms, self.cur, self.sel, self.text = [], None, None, []
            self.label = ""

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag in ("h1", "h2", "h3"):
                self.text = []
            if tag == "form" and (a.get("method") or "get").lower() == "post":
                self.cur = {"action": (a.get("action") or "").split("?")[0], "label": self.label, "fields": [], "_seen": {}}
            elif self.cur is not None and tag in ("input", "select", "textarea", "button") and a.get("name"):
                n = a["name"]
                kind = a.get("type") or tag
                if kind in ("submit", "button", "image", "reset", "file"):
                    if kind == "file":
                        self.cur["fields"].append({"name": n, "kind": "file (the assistant cannot upload files)"})
                    elif a.get("value") and a.get("name"):
                        self.cur["fields"].append({"name": n, "kind": "button", "choices": [a["value"][:60]]})
                    return
                if n in self.cur["_seen"]:
                    f = self.cur["_seen"][n]
                    if kind in ("radio", "checkbox") and a.get("value"):
                        f.setdefault("choices", []).append(a["value"][:60])
                    return
                f = {"name": n, "kind": kind}
                if kind == "hidden":
                    f["fixed"] = (a.get("value") or "")[:80]
                if kind in ("radio", "checkbox") and a.get("value"):
                    f["choices"] = [a["value"][:60]]
                if tag == "select":
                    self.sel = f
                    f["choices"] = []
                self.cur["_seen"][n] = f
                self.cur["fields"].append(f)
            elif tag == "option" and self.sel is not None and a.get("value") is not None and len(self.sel["choices"]) < 40:
                self.sel["choices"].append(a["value"][:60])

        def handle_endtag(self, tag):
            if tag in ("h1", "h2", "h3"):
                self.label = " ".join("".join(self.text).split())[:80]
            if tag == "select":
                self.sel = None
            if tag == "form" and self.cur is not None:
                self.cur.pop("_seen", None)
                if self.cur["action"] and self.cur["fields"]:
                    self.forms.append(self.cur)
                self.cur = None

        def handle_data(self, data):
            self.text.append(data)

    p = P()
    try:
        p.feed(html)
    except Exception:                      # a page with broken markup still gives what was read so far
        pass
    out = []
    for f in p.forms:
        act = f["action"]
        base = _WHERE["base"]
        if base and act.startswith(base):
            act = act[len(base):] or "/"
        try:
            _path_ok(act)
        except ValueError:
            continue
        out.append({"submit_to": act, "section": f["label"], "fields": f["fields"]})
    return {"page": page, "forms": out[:40],
            "how": "Submit one with do_action action=form.submit and fields={\"path\": <submit_to>, \"values\": {<field>: <value>}}. "
                   "Send only the fields the change needs, plus the hidden ones (their 'fixed' value) and any id. Never invent a field."}


# ------------------------------------------------------------------ check --

def _form_action(fields):
    """form.submit: any form on any admin page, as a registry-shaped action built on the spot."""
    path = _path_ok(str((fields or {}).get("path") or ""))
    values = (fields or {}).get("values")
    if isinstance(values, str):
        import json
        try:
            values = json.loads(values)
        except ValueError:
            raise ValueError("values must be a JSON object of field names and values.")
    if not isinstance(values, dict) or not values:
        raise ValueError("form.submit needs values: an object of the form's field names and what to put in them.")
    values = {str(k): v for k, v in values.items() if v not in (None, "") and not isinstance(v, dict)}
    risky = any(w in path.lower() for w in DESTRUCTIVE)
    a = {"path": path, "about": "Submit a form", "line": "Submit the form at " + path, "required": (), "multi": tuple(values),
         "risk": "high" if risky else "normal", "lands": (), "defaults": {}, "fields": {k: "" for k in values}}
    return a, values


def check(action, fields):
    """The action and its fields, or ValueError. Nothing is queued until this passes."""
    if (action or "").strip() == "form.submit":
        return _form_action(fields)
    a = REGISTRY.get((action or "").strip())
    if a is None:
        raise ValueError("No such action: %r. Call list_actions first." % action)
    fields = {k: v for k, v in (fields or {}).items() if v not in (None, "")}
    unknown = [k for k in fields if k not in a["fields"]]
    if unknown:
        raise ValueError("%s does not take %s. It takes: %s."
                         % (action, ", ".join(sorted(unknown)), ", ".join(sorted(a["fields"]))))
    missing = [k for k in a["required"] if k not in fields]
    if missing:
        raise ValueError("%s needs %s." % (action, ", ".join(missing)))
    for k in _ID_FIELDS:
        if k not in fields or k not in a["fields"]:
            continue
        if str(fields[k]).strip().isdigit():
            fields[k] = str(fields[k]).strip()
        elif k == "id" and a["fields"][k].startswith("Campaign id"):
            fields[k] = _campaign_by_name(str(fields[k]))       # the model gave a name: find the number
        else:
            raise ValueError("%s: %s must be the number from the portal, not %r." % (action, k, fields[k]))
    return a, fields


_ID_FIELDS = ("id", "content", "insight", "post", "code_id", "selection")


def _campaign_by_name(name):
    """A campaign's id from what the admin called it, or ValueError saying which names matched."""
    import db
    want = " ".join(name.lower().split())
    with db.connect() as conn:
        rows = conn.execute("SELECT id, name, client FROM campaigns WHERE deleted_at IS NULL").fetchall() \
            if _has_col("campaigns", "deleted_at") else conn.execute("SELECT id, name, client FROM campaigns").fetchall()
    exact = [r for r in rows if " ".join((r["name"] or "").lower().split()) == want]
    near = exact or [r for r in rows if want and want in " ".join(((r["name"] or "") + " " + (r["client"] or "")).lower().split())]
    if len(near) == 1:
        return str(near[0]["id"])
    if not near:
        raise ValueError("No campaign is called %r. Use list_campaigns to find its number." % name)
    raise ValueError("%d campaigns match %r: %s. Ask which one, or use its number."
                     % (len(near), name, "; ".join("%s = %s" % (r["id"], r["name"]) for r in near[:8])))


def _has_col(table, col):
    import db
    with db.connect() as conn:
        return any(r["name"] == col for r in conn.execute("PRAGMA table_info(%s)" % table))


def describe(action, fields):
    """The one sentence the admin reads on the Confirm card."""
    a, fields = check(action, fields)
    if action == "post.add":
        _post_add_creator(fields)
    if action == "form.submit":
        line = "%s: %s" % (a["line"], ", ".join("%s = %s" % (k, _short(v)) for k, v in sorted(fields.items())))
        return line + (". This may not be undoable" if a["risk"] == "high" else "")
    shown = {k: fields.get(k, "") for k in a["fields"]}
    try:
        line = a["line"].format(**shown)
    except (KeyError, IndexError):
        line = a["about"]
    rest = [k for k in fields if "{%s}" % k not in a["line"]]
    if rest:
        line += " — " + ", ".join("%s %s" % (k, _short(fields[k])) for k in sorted(rest))
    if a["risk"] == "high":
        line += ". This cannot be undone"
    return line


def _post_add_creator(fields):
    """A post link that names nobody needs its creator's code before it is queued. The portal can read the poster off an
    Instagram link only, so without the code a Facebook share link comes back Not done after Confirm. Refusing here makes
    the model send the code the admin gave, or ask for it."""
    if fields.get("code") or not str(fields.get("id") or "").isdigit():
        return
    import apify, db, postlink
    plat, _, handle = postlink.infer(postlink.canonical(str(fields.get("url") or "")))
    if (plat or "Instagram") == "Instagram":
        return
    members = db.campaign_creators(int(fields["id"]))
    if len({m["cc_code"] for m in members}) <= 1:
        return
    if postlink.pick_creator(handle, [(m["cc_code"], apify.creator_handles(m)) for m in members if m["code"]]):
        return
    who = ", ".join("%s (%s)" % (m["cc_code"], m["name"] if "name" in m.keys() and m["name"] else "") for m in members[:15])
    raise ValueError("post.add: this %s link does not say who posted it, so send code too. If the admin already named the "
                     "creator, use that code; otherwise ask which one: %s." % (plat, who))


def _short(v):
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)[:120]
    v = str(v)
    return v if len(v) <= 120 else v[:117] + "..."


# -------------------------------------------------------------------- run --

def run(action, fields, cookie):
    """Do it, through the portal's own door, as the admin who pressed Confirm."""
    a, fields = check(action, fields)
    if not cookie:
        return {"ok": False, "error": "No admin session to act with. Open the admin once and sign in (two-step code if asked), then ask again."}
    pairs = []
    for k, v in dict(a["defaults"], **fields).items():
        if isinstance(v, (list, tuple)):
            pairs += [(k, str(x)) for x in v]
        else:
            pairs.append((k, str(v)))
    body = urllib.parse.urlencode(pairs)
    conn = http.client.HTTPConnection(_WHERE["host"], _WHERE["port"], timeout=TIMEOUT)
    try:
        conn.request("POST", _WHERE["base"] + a["path"], body,
                     {"Content-Type": "application/x-www-form-urlencoded",
                      "Content-Length": str(len(body)), "Cookie": cookie})
        res = conn.getresponse()
        where = res.getheader("Location") or ""
        text = res.read(4000).decode("utf-8", "replace")
    except OSError as exc:
        return {"ok": False, "error": "The portal did not answer: %s" % exc}
    finally:
        conn.close()
    return _read_back(res.status, where, text, action, a["lands"])


def _read_back(status, where, text, action, lands=()):
    """A handler answers a browser with a redirect carrying its own message.

    Only ``?ok=`` (or landing where that action's success lands) counts as done.
    A wordless redirect to a list page is how these handlers refuse a bad id, and
    a redirect to the sign-in page is what an expired session looks like - neither
    may be reported back as success.
    """
    path = urllib.parse.urlparse(where).path
    q = urllib.parse.parse_qs(urllib.parse.urlparse(where).query)
    said = (q.get("ok") or [""])[0]
    wrong = (q.get("e") or [""])[0]
    if path.endswith("/reauth"):
        return {"ok": False, "error": "The portal wants you to confirm it is you before this one (Team, passcodes and deletes). "
                                      "Open the admin, confirm when asked, then ask again."}
    if any(path.endswith(p) for p in ("/login", "/password")):
        return {"ok": False, "error": "Not signed in: the portal sent the call to its sign-in page. "
                                      "Sign in again and ask once more."}
    if status in (401, 403):
        return {"ok": False, "error": "The portal refused it: %s" % (text[:200] or status)}
    if wrong:
        return {"ok": False, "error": wrong}
    if status >= 400:
        return {"ok": False, "error": "The portal answered %d: %s" % (status, text[:200])}
    if said:
        return {"ok": True, "message": said, "action": action}
    if q.get("new") and path.endswith("/codes"):
        # A new access code is shown once, in the redirect: hand it to the admin.
        return {"ok": True, "message": "Issued. The new passcode is %s. Share it with the client." % q["new"][0], "action": action}
    if lands and any(path.endswith(p) or p in path for p in lands):
        return {"ok": True, "message": "Done.", "action": action}
    return {"ok": False, "error": "The portal did not confirm it - it answered with %s and no message. "
                                  "Nothing was reported as changed; check the page before trying again."
                                  % (path or "no page")}
