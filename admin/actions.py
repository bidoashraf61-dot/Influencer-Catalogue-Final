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
        "when the admin gave them or the portal asked.",
        "Add the post {url} to campaign {id}",
        dict({"id": "Campaign id.", "url": "The post link, starting https://",
              "code": "Creator code on this campaign (optional: found from the link).",
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


# ------------------------------------------------------------------ check --

def check(action, fields):
    """The action and its fields, or ValueError. Nothing is queued until this passes."""
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
    return a, fields


def describe(action, fields):
    """The one sentence the admin reads on the Confirm card."""
    a, fields = check(action, fields)
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
