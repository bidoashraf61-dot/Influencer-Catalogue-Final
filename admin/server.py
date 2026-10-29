#!/usr/bin/env python3
"""HelloVoice catalogue — admin dashboard and gated roster API.

Stdlib only: no pip install, no build step. Drops onto any server with Python 3
and runs behind nginx.

    python3 admin/server.py --port 8900

Routes
  /                     dashboard (login required)
  /login  /logout       admin session
  /codes                issue, expire, revoke access codes
  /analytics            who opened what, when
  /roster               add, edit, deactivate creators
  /requests             quote requests as an inbox
  /go/<slug>            public tracking link: counts the tap, redirects
  /insights/<token>     public: a creator uploads insight screenshots
  /campaigns …          campaign setup, content, insights, links, report
  /settings             EMV rates, estimate factors, capture token
  /api/campaigns        GET  viewer: the passcode's campaigns
  /api/campaign         GET  viewer: one campaign's report (client-safe)
  /api/capture/*        capture job (Bearer token): jobs, content, insights
  /campaigns            booked creators, dates and detection rules per client
  /api/unlock           POST {code}   -> sets a viewer cookie, returns roster
  /api/roster           GET           -> roster, viewer cookie required
  /api/discover/facets  GET           -> Audience/Performance filter options (names only)
  /api/discover         POST          -> codes passing analysis filters (analyses stay here)
  /api/discover/like    POST          -> codes most like one creator, best first
  /api/discover/parse   POST          -> a typed brief read into sidebar filters (free)
  /api/request          POST          -> store a quote request
  /api/event            POST          -> record a shortlist action

The roster is served only after a code is checked HERE. That is the difference
between this and the static build: on the static site the passcode is a hash in
the JavaScript and the data sits in the page regardless. Expiry, revocation and
analytics are only meaningful because the check happens server-side.
"""


import os as _os, sys as _sys
from pathlib import Path as _P
_LIB = _P(__file__).resolve().parent / "_vendor" / "lib"
if __name__ == "__main__" and _LIB.is_dir() and str(_LIB) not in _os.environ.get("LD_LIBRARY_PATH", ""):
    # The slim container has no C++ runtime and the PDF reader needs one. The
    # libraries live beside it; the loader only reads this variable at start-up.
    _os.environ["LD_LIBRARY_PATH"] = str(_LIB) + (":" + _os.environ["LD_LIBRARY_PATH"] if _os.environ.get("LD_LIBRARY_PATH") else "")
    _os.execv(_sys.executable, [_sys.executable] + _sys.argv)

import argparse
import gzip
import hashlib
import html
import json
import math
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import auth  # noqa: E402
import guard  # noqa: E402
import mailer  # noqa: E402
import industry  # noqa: E402
import lifecycle  # noqa: E402
import industry_views  # noqa: E402
import portal  # noqa: E402
import portal_api  # noqa: E402
import team  # noqa: E402
import kam_scope  # noqa: E402
import team_views  # noqa: E402
import importer  # noqa: E402
import db  # noqa: E402
import actions  # noqa: E402
import history  # noqa: E402
import fx  # noqa: E402
import analysis  # noqa: E402
import links  # noqa: E402
import metrics  # noqa: E402
import plans  # noqa: E402
import thumbs  # noqa: E402
import track  # noqa: E402
import uploads  # noqa: E402
import account  # noqa: E402
import gating  # noqa: E402
import selstatus  # noqa: E402
import matcher  # noqa: E402
import apify
import profile_thumbs
import apis_view
import evidence
import access_rules
import modules
import reference_view
import trial
import views  # noqa: E402
import ui  # noqa: E402

SECRET = auth.load_secret(HERE / ".secret")
_GZIP_TYPES = {"application/json", "text/html", "text/plain", "text/css", "application/javascript", "text/javascript", "image/svg+xml"}
_ROSTER_CACHE = {}
_ROSTER_BUILD_LOCK = __import__("threading").Lock()   # one roster build at a time (see roster_payload)
# The /api/roster answer itself, serialised and gzipped once per roster version, with its
# ETag: a repeat visit costs an empty 304 and nobody pays the ~0.8 s build or the 1.7 MB
# json.dumps + gzip again until a creator, an analysis, a tier, a rate or the day's photo
# signatures change. One entry; cleared with _ROSTER_CACHE.
_ROSTER_BODY = {}
ROSTER_SAFETY_S = 3600                 # rebuilt at least hourly, in case a change slips past the fingerprint
# Salt for the visitor hash on tracking-link clicks: derived from the server
# secret so it is stable across restarts, but not the secret itself.
CLICK_SALT = __import__("hashlib").sha256(b"clicks|" + SECRET).hexdigest()
# Insight screenshots creators upload. Private: beside the database, never in
# the site's assets, served only to an admin or the capture job.
INSIGHT_DIR = HERE / "insight_files"
INSIGHT_MAX = 12 * 1024 * 1024        # per file
INSIGHT_FILES = 6                     # per upload
# Brand logos uploaded for one campaign (ones not already in assets/clients).
LOGO_DIR = HERE / "campaign_files"
# The client logos the catalogue already ships: offered as one-click choices.
CLIENT_LOGOS = next((p for p in (HERE.parent / "site" / "assets" / "clients",
                                 HERE.parent / "assets" / "clients") if p.is_dir()), None)
# Photos live with the built site so the catalogue and the dashboard share one
# copy — uploading here updates what a client sees.
PHOTO_DIR = HERE.parent / "site" / "assets" / "catalogue"

# How many creators the roster shows at once. The whole list on one page came
# to 311KB of HTML and 757 thumbnails at 759 creators, and grows in a straight
# line: 1.8MB and 5,000 thumbnails at 5,000 creators. Paging keeps the page the
# same size however far the roster grows.
ROSTER_PAGE = 100
links.PHOTO_DIR = PHOTO_DIR
history.PHOTO_DIR = PHOTO_DIR
evidence.PHOTO_DIR = PHOTO_DIR
LOGO = HERE.parent / "site" / "assets" / "helv" / "logo-knockout.webp"
STATIC = HERE / "static"
ADMIN_COOKIE = "hv_admin"
VIEWER_COOKIE = "hv_view"
# Set with a client's pass by "Preview as client" in the admin: read-only, for an admin only.
PREVIEW_COOKIE = "hv_preview"
PREVIEW_TTL = 3600
# The only POSTs a preview may still make (a calculation and analytics; nothing is saved or charged).
PREVIEW_POSTS = ("/api/event", "/api/roi/estimate", "/api/me/ping", "/api/me/unlock", "/api/me/as-client",
                 "/api/push/event", "/api/push/subscribe", "/api/push/unsubscribe", "/api/push/ack", "/api/push/click")
# Every shared link (a selection, a campaign report, the catalogue itself)
# remembers the access code that opened it, in this browser: each new link
# asks for its own code once, and links of different clients open side by side.
LINKS_COOKIE = "hv_links"
ADMIN_TTL = 12 * 3600
VIEWER_TTL = 12 * 3600

# The device cookie: a random ID that marks one browser, so an access code can
# be limited to a number of devices. Long-lived on purpose — it is what lets
# the client's own laptop back in next week without taking another slot.
# 400 days is the most a browser will keep a cookie for.
DEVICE_COOKIE = "hv_dev"
DEVICE_TTL = 400 * 86400

# Where the catalogue is served from. The API is called cross-origin from it,
# so it must be named explicitly — "*" cannot be used with credentials.
ALLOWED_ORIGINS = set()

# When the dashboard is served under a path (e.g. /admin) rather than its own
# subdomain, every route and redirect has to carry that prefix. Serving it on
# the catalogue's own domain means the API is same-origin: no CORS, and the
# viewer cookie can be SameSite=Lax instead of None.
BASE = ""
# Where public pages (/go/, /insights/) live: the site root, whatever BASE is.
BASE_PUBLIC = ""

def squash(text):
    """A name reduced to something a filename can be compared against.

    "Noha Magdy", "noha_magdy" and "NOHA-MAGDY.jpg" are the same person; the
    separators are whatever the person saving the file happened to type. Only
    letters and digits survive, so this holds for Arabic names too.
    """
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


# Tiers and their price bands live in the database now, editable from the
# dashboard. Three hard-coded copies of this table used to sit in three
# programs, and changing a rate meant remembering all three or quoting one
# price on the page and another in the email.


def ts(value):
    if not value:
        return "—"
    return datetime.fromtimestamp(value, timezone.utc).strftime("%d %b %Y, %H:%M")


def _json_list(raw):
    """A JSON list stored as text -> a list; anything else -> []."""
    try:
        v = json.loads(raw) if raw else []
        return v if isinstance(v, list) else []
    except (TypeError, ValueError):
        return []


# The most creators one selection can hold (cards are still fetched 200 per call).
SELECTION_MAX = 1000


class Handler(portal_api.PortalMixin, BaseHTTPRequestHandler):
    server_version = "hv-catalogue"

    # ----------------------------------------------------------- plumbing --

    def log_message(self, fmt, *args):
        sys.stderr.write("%s  %s\n" % (self.address_string(), fmt % args))

    def cookies(self):
        raw = self.headers.get("Cookie", "")
        out = {}
        for part in raw.split(";"):
            if "=" in part:
                k, _, v = part.partition("=")
                out[k.strip()] = v.strip()
        return out

    def client_ip(self):
        # Behind nginx the socket address is the proxy, not the visitor. The
        # LAST X-Forwarded-For entry is the one our own proxy added; anything
        # before it came from the client and can be typed by anyone.
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[-1].strip() if fwd else self.client_address[0]

    def body(self):
        # Read once and kept: the history wrapper reads the form to learn what
        # is about to change, then the handler reads it again.
        if not hasattr(self, "_body"):
            length = int(self.headers.get("Content-Length") or 0)
            self._body = self.rfile.read(length) if length else b""
        return self._body

    def json_body(self):
        try:
            return json.loads(self.body() or b"{}")
        except Exception:
            return {}

    def form_body(self, multi=()):
        ctype = self.headers.get("Content-Type", "")
        if ctype.startswith("multipart/form-data"):
            return uploads.parse_multipart(self.body(), ctype, multi=multi)
        return {k: (v if k in multi else v[0])
                for k, v in urllib.parse.parse_qs(self.body().decode(), keep_blank_values=bool(multi)).items()}

    def send(self, code, body=b"", ctype="text/html; charset=utf-8", headers=None):
        # While a tracked action runs, its answer waits until the change is in
        # the History — otherwise the redirected page could load first.
        if getattr(self, "_held", None) is not None:
            self._held.append((code, body, ctype, headers))
            return
        if isinstance(body, str):
            body = body.encode()
        # Text answers go out gzipped when the browser accepts it: the roster
        # alone is ~1.5 MB of JSON and shrinks about 7x. NPM proxies /admin
        # straight here, so nothing upstream compresses it.
        zipped = (len(body) > 1024 and ctype.split(";")[0] in _GZIP_TYPES
                  and "gzip" in (self.headers.get("Accept-Encoding") or "")
                  and not any(k.lower() == "content-encoding" for k, _ in (headers or [])))
        if zipped:
            body = gzip.compress(body, 5)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if zipped:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        for k, v in (headers or {}):
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, code, payload, headers=None):
        self.send(code, json.dumps(payload), "application/json; charset=utf-8", headers)

    def redirect(self, to, headers=None):
        if to.startswith("/") and BASE and not to.startswith(BASE + "/") and to != BASE:
            to = BASE + to
        h = [("Location", to)] + list(headers or [])
        if getattr(self, "_held", None) is None:
            h += self.undo_cookie()
        self.send(303, b"", "text/plain", h)

    def undo_cookie(self):
        """The next page offers Undo for what this POST just changed in History."""
        made = history.made() if self.command == "POST" else []
        if not made:
            return []
        label = made[0][1] or "Change saved"
        if len(made) > 1:
            label = "%d changes saved" % len(made)
        history.start_request()
        val = urllib.parse.quote(",".join(str(i) for i, _ in made[-50:]) + "|" + label[:140], safe="")
        return [("Set-Cookie", "hv_undo=%s; Path=/; Max-Age=60; SameSite=Lax%s" % (val, self.secure_flag()))]

    def secure_flag(self):
        """'; Secure' when we are served over https (an https --origin is set)."""
        return "; Secure" if any(o.startswith("https://") for o in ALLOWED_ORIGINS) else ""

    def cors(self):
        """Only for /api/*. The dashboard is same-origin and needs none."""
        origin = self.headers.get("Origin", "")
        if origin and (origin in ALLOWED_ORIGINS or not ALLOWED_ORIGINS):
            return [
                ("Access-Control-Allow-Origin", origin),
                ("Access-Control-Allow-Credentials", "true"),
                ("Vary", "Origin"),
            ]
        return []

    # -------------------------------------------------------------- auth --

    AS_CLIENT_COOKIE = "hv_asclient"

    def as_client(self):
        """View as client (owner, 2026-10-15): a team member looking at the client pages exactly as the
        client sees them. Only the client-facing API reads it; the admin pages are never affected."""
        if self.cookies().get(self.AS_CLIENT_COOKIE, "") != "1":
            return False
        p = self.route(urllib.parse.urlparse(self.path).path)
        return p.startswith("/api/") and p not in ("/api/me/as-client",)

    def admin(self):
        if trial.ACTIVE or self.as_client():
            return None                                # a trial visitor, or seen as the client: no admin session
        token = auth.unsign(self.cookies().get(ADMIN_COOKIE, ""), SECRET)
        if not token:
            return None
        row = db.session(token)
        if row is None:
            return None
        row = team.check_idle(token, row)          # signed out after the team's idle limit
        if row is not None:
            self._admin_token = token
        return row

    # ------------------------------------------------- App & alerts (item 168) --

    def get_app_alerts(self, path, query):
        import push
        import push_views
        if path == "/app-alerts/reach":
            try:
                aud = json.loads(query.get("aud") or "{}")
            except ValueError:
                aud = {}
            return self.send_json(200, dict(push.reach(aud if isinstance(aud, dict) else {}), ok=True))
        flash = None
        if query.get("ok"):
            flash = ("ok", query["ok"])
        elif query.get("e"):
            flash = ("err", query["e"])
        tab = query.get("tab") or "overview"
        if tab == "send":
            return self.send(200, push_views.send_page(flash))
        if tab == "history":
            return self.send(200, push_views.history_page(flash))
        if tab == "rules":
            return self.send(200, push_views.rules_page(flash))
        return self.send(200, push_views.overview_page(query.get("q", ""), flash))

    def post_app_alerts(self, path, who):
        import push
        import push_views
        f = self.form_body()
        me = who["email"] if "email" in who.keys() else "admin"
        q = urllib.parse.quote
        if path == "/app-alerts/rules":
            push.save_rules(push_views.parse_rules(f))
            team.log("push_rules", me, "saved", self.client_ip())
            return self.redirect("/app-alerts?tab=rules&ok=" + q("Rules saved."))
        if path == "/app-alerts/update-now":
            n = push.send_update(created_by=me)
            team.log("push_update", me, "%d devices" % n, self.client_ip())
            return self.redirect("/app-alerts?tab=history&ok=" + q("Update notice sent to %d device%s." % (n, "" if n == 1 else "s")))
        if path == "/app-alerts/cancel":
            ok = push.cancel(int(f.get("id") or 0)) if str(f.get("id") or "").isdigit() else False
            return self.redirect("/app-alerts?tab=history&" + ("ok=" + q("Scheduled push cancelled.") if ok else "e=" + q("That push was already sent.")))
        if path == "/app-alerts/test":
            email = (f.get("email") or "").strip().lower()
            n = push.create_message("Test from HelloVoice", "If you can read this, alerts work on this phone.", "/account/#notifications",
                                    {}, me, test_email=email) if email else 0
            return self.redirect("/app-alerts?" + ("ok=" + q("Test push sent to %d phone%s." % (n, "" if n == 1 else "s")) if n
                                                   else "e=" + q("No phone with alerts on for that person.")))
        if path == "/app-alerts/send":
            title, body = (f.get("title") or "").strip(), (f.get("body") or "").strip()
            url = (f.get("url") or "").strip() if f.get("dest") == "custom" else (f.get("dest") or "/account/")
            if not title:
                return self.redirect("/app-alerts?tab=send&e=" + q("Give the push a title."))
            if f.get("test"):
                n = push.create_message(title, body, url, {}, me, test_email=me)
                return self.redirect("/app-alerts?tab=send&" + ("ok=" + q("Test sent to your %d phone%s." % (n, "" if n == 1 else "s")) if n
                                                                else "e=" + q("You have no phone with alerts on yet. Open the portal on your phone, install the app and turn alerts on.")))
            try:
                aud = json.loads(f.get("aud") or "{}")
            except ValueError:
                aud = {}
            if not isinstance(aud, dict) or aud.get("type") not in push.AUDIENCES:
                return self.redirect("/app-alerts?tab=send&e=" + q("Choose who gets it."))
            users, emails = push.resolve(aud)
            if not users and not emails:
                return self.redirect("/app-alerts?tab=send&e=" + q("Nobody matches that audience."))
            at = push_views.parse_send_at(f.get("send_at")) if f.get("when") == "later" else None
            if f.get("when") == "later" and (not at or at <= db.now() + 60):
                return self.redirect("/app-alerts?tab=send&e=" + q("Pick a time in the future to schedule it."))
            mid = push.create_message(title, body, url, aud, me, send_at=at)
            team.log("push_send", me, "%s · %s" % (mid, title[:60]), self.client_ip())
            return self.redirect("/app-alerts?tab=history&ok=" + q("Push scheduled." if at else "Push sent."))
        return self.send(404, "Not found", "text/plain")

    def not_your_client(self, path):
        """403 for a key account manager outside her clients: a page in the admin, JSON for the API."""
        if path.startswith("/api/") or path.startswith("/ai/"):
            return self.send_json(403, {"ok": False, "reason": "not_your_client", "message": kam_scope.NOT_YOURS + "."})
        return self.send(403, views.not_your_client_page(path))

    def require_admin(self):
        who = self.admin()
        if not who:
            if self.command == "GET" and self.portal_sso():
                return None
            self.redirect("/login")
            return None
        return who

    def portal_sso(self):
        """One sign-in (owner, 2026-10-14): a team member already signed in to the portal with their email code
        opens the admin without a second code. Their portal pass names their own account; when that account's
        email is an active admin, an admin session starts here (two-step sign-in still asked when it is on).
        Returns True when it answered the request."""
        cid = self.viewer_cookie_id()
        if cid is None or cid == db.admin_code_id():
            return False
        u = portal.user_for_code(cid)
        if not u or u["status"] != "active" or not u["email"]:
            return False
        row = db.admin_by_email(u["email"])
        if row is None or row["disabled_at"]:
            return False
        if row["totp_on"] or team.must_use_2fa(row):
            pend = auth.sign("2fa:%d:%d" % (row["id"], db.now() + 300), SECRET)
            self.redirect("/login/2fa", [("Set-Cookie", "hv_2fa=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=300%s" % (pend, self.secure_flag()))])
            return True
        raw = urllib.parse.urlparse(self.path)
        here = self.route(raw.path) + ("?" + raw.query if raw.query else "")
        self.start_session(row, to=here if here.startswith("/") and not here.startswith("//") else "/")
        return True

    def viewer_code_id(self):
        """Who is looking at the catalogue: the client's passcode pass, or —
        for a signed-in admin with no pass — the internal admin preview code,
        so the admin never needs a passcode."""
        cid = self.viewer_cookie_id()
        if cid is None and self.admin():
            if self.kam_clients() is not None:
                # A key account manager is never "HelloVoice, sees everything" in the catalogue:
                # she is her own portal account (if she has one), opening her clients' work by scope.
                u = portal.user_by_email(self.admin()["email"]) if self.admin()["email"] else None
                return u["code_id"] if u is not None and u["status"] == "active" else None
            cid = db.admin_code_id()
        # A colleague invited into a company (users.company_code_id) works on the company's data: selections, campaigns,
        # credits. person_code_id() is still the pass itself, for the places that need who it is, not whose data it is.
        return modules.data_code_id(cid)

    def person_code_id(self):
        """The code on this browser's own pass: who is signed in, as against viewer_code_id() = whose data they see."""
        return self.viewer_cookie_id()

    def person_user(self, code_id):
        """portal.user_for_code(code_id), except that the company code a colleague works under means the colleague:
        an email, a History entry or a role decision about "the viewer" names the person who acted, not the company's
        account holder. Looking up an object's owner (selection or campaign code) still uses portal.user_for_code."""
        me = self.person_code_id()
        if me is not None and access_rules.is_acting_person(code_id, me, modules.data_code_id(me)):
            u = portal.user_for_code(me)
            if u is not None:
                return u
        return portal.user_for_code(code_id)

    def staff_viewer(self, cid=None):
        """True when this browser is signed in to the portal as someone who ALSO has admin access
        (their email is an admin account). They stay themselves, with their own account; a switch in
        their menu ("Show locked data") reveals what is locked, and nothing else changes."""
        if self.as_client():
            return False                               # View as client: a client like any other
        return self.staff_account(cid)

    def staff_account(self, cid=None):
        """staff_viewer() whatever the View as client switch says (the switch itself needs it)."""
        cid = cid if cid is not None else self.viewer_cookie_id()
        if cid is None or cid == db.admin_code_id():
            return False
        u = portal.user_for_code(cid)
        return bool(u and u["email"] and db.admin_by_email(u["email"]))

    UNLOCK_COOKIE = "hv_unlock"

    def staff_unlocked(self):
        """A person with admin access who has switched "Show locked data" on. A key account
        manager's switch never unlocks everything: see kam_unlocked()."""
        if not self.staff_viewer() or self.kam_clients() is not None:
            return False
        if self.cookies().get(self.UNLOCK_COOKIE, "") == "1":
            return True
        # Owner and admin accounts see everything without the switch (owner, 2026-10-15).
        u = portal.user_for_code(self.viewer_cookie_id())
        a = db.admin_by_email(u["email"]) if u is not None and u["email"] else None
        import team as _team
        return a is not None and _team.role_of(a) in ("owner", "admin")

    def kam_clients(self):
        """None, or (for a key account manager signed in to the admin, or to the portal with an
        email that is a KAM's admin login) the frozenset of her clients' code ids. Once per request."""
        if self.as_client():
            return None
        memo = getattr(self, "_kam_memo", None)
        if memo is not None and memo[0] == self.path:
            return memo[1]
        sc = None
        who = self.admin()
        if who is not None:
            sc = kam_scope.clients(who)
        else:
            cid = self.viewer_cookie_id()
            u = portal.user_for_code(cid) if cid is not None and cid != db.admin_code_id() else None
            a = kam_scope.admin_for_email(u["email"]) if u is not None and u["email"] else None
            if a is not None and not a["disabled_at"]:
                sc = kam_scope.clients(a)
        self._kam_memo = (self.path, sc)
        return sc

    def kam_unlocked(self):
        """A key account manager whose locked data is open (her admin session, or her switch):
        reaches only her own clients (portal.unlock_client / unlock_creator)."""
        if self.kam_clients() is None:
            return False
        return bool(self.admin()) or (self.cookies().get(self.UNLOCK_COOKIE, "") == "1" and self.staff_viewer())

    def admin_like(self):
        """HelloVoice admin session, or admin access with the unlock switch on: the checks that
        mean "nothing is locked for this reader". Never true for a key account manager: her
        clients' work opens through admin_like_for()."""
        return (bool(self.admin()) and self.kam_clients() is None) or self.staff_unlocked()

    def admin_like_for(self, code_id, sel_id=None, camp_id=None):
        """admin_like() for one thing filed under ``code_id``: also true for a key account manager
        when it is one of her clients, or the selection (``sel_id``) or campaign (``camp_id``) was handed to her."""
        if self.admin_like():
            return True
        sc = self.kam_clients()
        try:
            if sc is not None and ((sel_id is not None and int(sel_id) in getattr(sc, "sel_ids", ()))
                                   or (camp_id is not None and int(camp_id) in getattr(sc, "camp_ids", ()))):
                return True
            return sc is not None and code_id is not None and int(code_id) in sc
        except (TypeError, ValueError):
            return False

    def preview_mode(self):
        """An admin looking at the portal AS a client (read-only): the preview cookie plus a live
        admin session. Without the admin session the cookie means nothing."""
        return self.cookies().get(PREVIEW_COOKIE, "") == "1" and bool(self.admin())

    # ------------------------------------------------- per-link access codes --

    @staticmethod
    def link_hash(key):
        return hashlib.sha256(("link:" + key).encode()).hexdigest()[:16]

    def link_entries(self):
        """{link hash: (code id, expiry)} unlocked in this browser and not expired."""
        raw = auth.unsign(self.cookies().get(LINKS_COOKIE, ""), SECRET) or ""
        out = {}
        for part in raw.split(","):
            bits = part.split("~")
            if len(bits) == 3 and bits[1].isdigit() and bits[2].isdigit() and int(bits[2]) > db.now():
                out[bits[0]] = (int(bits[1]), int(bits[2]))
        return out

    @staticmethod
    def passcodes_off():
        """Owner, 2026-10-15: nobody opens anything with a typed access code; everyone signs in by email."""
        return bool(db.setting("passcodes_off", False))

    def link_code(self, key):
        """The access code this browser typed for this link, while it is still
        good and this browser is still one of its devices; else None."""
        e = None if self.passcodes_off() else self.link_entries().get(self.link_hash(key))
        if not e:
            return self.as_client_owner(key)
        return self._link_code_row(e)

    def as_client_owner(self, key):
        """View as client on a selection or campaign the team member's own account cannot open (it belongs
        to another client): the page opens as that client's account sees it, read-only (owner, 2026-10-15)."""
        if not (key[:2] in ("s:", "c:") and self.as_client() and self.staff_account()):
            return None
        tok = key[2:]
        obj = db.selection(token=tok) if key[:2] == "s:" else db.campaign(token=tok)
        if obj is None or obj["code_id"] is None:
            return None
        own = self.viewer_cookie_id()
        return obj["code_id"] if own is None or obj["code_id"] not in portal.team_codes(own) else None

    def _link_code_row(self, e):
        row = db.get_code(e[0])
        if row is None or not db.code_state(row)[0]:
            return None
        if row["max_devices"] and not db.device_allowed(row["id"], db.device_hash(self.cookies().get(DEVICE_COOKIE, ""))):
            return None
        return row["id"]

    # ----------------------------------------- public read-only links (2026-10-18) --
    # A link on the public_links allowlist opens for anyone, signed in or not, read-only: the
    # client's view with every price, total and cost taken out. Only used when the normal checks
    # refuse, so signed-in, admin and KAM readers are unchanged; every write stays refused.
    PUBLIC_MONEY_KEYS = frozenset(("price", "prices", "total_from", "total_to", "cost", "costs", "margin",
                                   "margin_max", "margins", "fee", "fees", "budget", "cpm", "cpe", "cpc", "emv",
                                   "price_from", "price_to", "replace_cost", "more_cost", "alike_cost",
                                   "credits", "ai_free", "campaign_cost", "spend"))

    def public_link(self, kind, token):
        return bool(token) and db.public_link_on(kind, token)

    @classmethod
    def public_strip(cls, obj):
        """A copy of ``obj`` with every money key removed, at any depth."""
        if isinstance(obj, dict):
            return {k: cls.public_strip(v) for k, v in obj.items() if k not in cls.PUBLIC_MONEY_KEYS}
        if isinstance(obj, list):
            return [cls.public_strip(v) for v in obj]
        return obj

    def public_selection(self, token):
        """The selection behind a public link token, or None (not public, unknown or deleted)."""
        if not token or not self.public_link("selection", token):
            return None
        sel = db.selection(token=token)
        return sel if sel is not None and not sel["deleted_at"] else None

    def selection_viewer(self, token):
        """Who acts on a selection page: the admin, else the code typed for that
        link, else this browser's general pass."""
        if self.admin_like():
            return db.admin_code_id()
        if token and self.kam_clients() is not None:
            sel = db.selection(token=token, deleted=True)
            if sel is not None and self.admin_like_for(sel["code_id"], sel["id"]):
                return db.admin_code_id()          # a key account manager on her own client's selection
        return (self.link_code("s:" + token) if token else None) or self.viewer_code_id()

    def signed_in_client(self):
        """A client signed in by email has no code to type: their pass counts for their own links."""
        cid = self.viewer_cookie_id()
        return cid if cid is not None and portal.user_for_code(cid) else None

    def links_cookie(self, keys, code_id, expiry):
        entries = self.link_entries()
        for k in keys:
            entries[self.link_hash(k)] = (code_id, expiry)
        keep = sorted(entries.items(), key=lambda kv: -kv[1][1])[:40]
        val = auth.sign(",".join("%s~%d~%d" % (h, c, x) for h, (c, x) in keep), SECRET)
        policy = "SameSite=None; Secure" if ALLOWED_ORIGINS else "SameSite=Lax"
        return ("Set-Cookie", f"{LINKS_COOKIE}={val}; Path=/; HttpOnly; {policy}; Max-Age={max(0, keep[0][1][1] - db.now())}")

    def link_target_code(self, key):
        """(found, code id) for a selection or campaign link key."""
        kind, _, tok = key.partition(":")
        if kind == "s" and tok:
            sel = db.selection(token=tok)
            return (sel is not None, sel["code_id"] if sel is not None else None)
        if kind == "c" and tok and tok != "list":
            k = db.campaign(token=tok)
            return (k is not None, k["code_id"] if k is not None else None)
        return (False, None)

    def viewer_cookie_id(self):
        if trial.ACTIVE:
            return trial.DEMO_CODE                     # every trial visitor is the demo company's owner (trial.py)
        raw = auth.unsign(self.cookies().get(VIEWER_COOKIE, ""), SECRET)
        if not raw or ":" not in raw:
            return None
        parts = raw.split(":")
        code_id, expiry = parts[0], parts[1] if len(parts) > 1 else ""
        if not code_id.isdigit() or not expiry.isdigit() or int(expiry) < db.now():
            return None
        # The pass names the device it was issued to. It must still be this
        # browser, and the device must still be on the code — removing it in
        # the dashboard shuts it out on its next request. A pass issued before
        # devices were counted carries none and simply runs out (12 hours).
        if len(parts) > 2:
            mine = db.device_hash(self.cookies().get(DEVICE_COOKIE, ""))
            if mine != parts[2] or not db.device_allowed(int(code_id), parts[2]):
                return None
        # Passcodes off (owner, 2026-10-15): only a pass from email sign-in counts (and the admin's client preview).
        if self.passcodes_off() and (len(parts) < 4 or parts[3] != "e") and not self.preview_mode():
            return None
        # Re-check the code every request: revoking must take effect at once,
        # not whenever the cookie happens to lapse.
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM codes WHERE id = ?", (code_id,)).fetchone()
        ok, _ = db.code_state(row)
        return int(code_id) if ok else None

    # ------------------------------------------------------------ routing --

    def do_OPTIONS(self):
        self.send(204, b"", "text/plain", self.cors() + [
            ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type"),
        ])

    def route(self, raw):
        path = raw.rstrip("/") or "/"
        if BASE and path.startswith(BASE):
            path = path[len(BASE):] or "/"
        return path

    # Reads that ask the same team / campaign question several times share one answer per
    # request (portal.memo_*). GETs only change nothing that matters; of the POSTs only the
    # selection decisions, which never touch users, teams or campaigns.
    MEMO_POSTS = ("/api/selection/status", "/api/selection/reason", "/api/selection/tags", "/api/selection/platform")

    def _unlock_begin(self):
        self._kam_memo = None
        kam_scope.end()
        sc = self.kam_clients()
        if sc is None:
            portal.unlock_begin(self.staff_unlocked())
        else:
            portal.unlock_begin(self.kam_unlocked(), scope=sc)

    def do_GET(self):
        if self.trial_route():
            return
        portal.memo_begin()
        self._unlock_begin()
        try:
            return self._do_get()
        finally:
            portal.unlock_begin(False)
            kam_scope.end()
            portal.memo_end()
            trial.end()

    # ------------------------------------------------------- trial links (item 271) --

    def trial_route(self):
        """True when the request was answered here: a trial link opened, or a trial visitor's request
        handed to the trial process (trial.py). In the trial process itself: point the request at its
        link's copy and refuse what a trial may not do."""
        path = self.route(urllib.parse.urlparse(self.path).path)
        if trial.ACTIVE:
            if not trial.begin(self):
                self.send_json(410, {"ok": False, "reason": "trial_ended"}, self.cors())
                return True
            if not trial.page_allowed(path):
                self.send(302, b"", "text/plain", [("Location", "/workspace/"), ("Cache-Control", "no-store")])
                trial.end()
                return True
            if path == "/api/trial/state":
                st = {"trial": True, "client": trial.client_name(self)}
                self.send_json(200, st, self.cors() + [("Cache-Control", "no-store")])
                trial.end()
                return True
            if self.command == "POST" and path.startswith("/api/push/"):
                self.send_json(200, {"ok": True, "trial": True}, self.cors())   # the phone app is not part of a trial
                trial.end()
                return True
            if self.command == "POST" and not trial.post_allowed(path):
                self.send_json(403, trial.REFUSED, self.cors())
                trial.end()
                return True
            return False
        if path == "/try" or path.startswith("/try/"):
            self.trial_open(path[len("/try/"):] if path.startswith("/try/") else "")
            return True
        raw = self.cookies().get(trial.COOKIE, "")
        if not raw:
            return False
        r, _ = trial.from_cookie(SECRET, raw)
        gone = [("Set-Cookie", "%s=; Path=/; Max-Age=0" % trial.COOKIE),
                ("Set-Cookie", "hv_trial_on=; Path=/; Max-Age=0")]
        if self.admin():
            return False                               # HelloVoice staff are never a trial visitor
        if not trial.is_open(r):
            if path.startswith("/api/"):
                self.send_json(410, {"ok": False, "reason": "trial_ended",
                                     "error": "This trial has ended. Ask HelloVoice for a new link."},
                               self.cors() + gone)
            else:
                self.send(410, trial.page(r, "ended"), headers=gone)
            return True
        if path == "/api/trial/state":
            return self.send_json(200, trial.state(r), self.cors() + [("Cache-Control", "no-store")]) or True
        if path == "/api/trial/contact" and self.command == "POST":
            if not guard.origin_ok(self.headers, ALLOWED_ORIGINS):
                return self.send_json(403, {"ok": False}, self.cors()) or True
            if not guard.limiter.allow("trialc:%s" % self.client_ip(), 6, 3600):
                return self.too_many(guard.limiter.retry_after("trialc:%s" % self.client_ip(), 6, 3600)) or True
            guard.limiter.hit("trialc:%s" % self.client_ip())
            ok, said = trial.contact(r, self.json_body(), self.client_ip())
            return self.send_json(200 if ok else 400, {"ok": ok, "message": said, "error": None if ok else said},
                                  self.cors()) or True
        trial.forward(self, r)
        return True

    def trial_open(self, token):
        """/try/<token>[?to=/page]: the share link. Sets the trial cookie and lands on the demo."""
        token = token.strip("/")
        r = trial.link(token=token) if re.fullmatch(r"[A-Za-z0-9_-]{8,40}", token or "") else None
        if r is None:
            return self.send(404, trial.page(None, "missing"), headers=[("Cache-Control", "no-store")])
        if not trial.is_open(r):
            return self.send(410, trial.page(r, "ended"), headers=[("Cache-Control", "no-store")])
        if self.admin():
            return self.send(200, trial.page(r, "staff"), headers=[("Cache-Control", "no-store")])
        try:
            trial.ensure_copy(r)
        except Exception as e:
            print("trial copy:", repr(e)[:200], flush=True)
            return self.send(503, trial.page(r, "preparing"), headers=[("Cache-Control", "no-store")])
        to = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query)).get("to") or "/workspace/"
        if not to.startswith("/") or to.startswith("//") or "\\" in to:
            to = "/workspace/"
        age = max(60, r["expires_at"] - db.now())
        sec = self.secure_flag()
        return self.send(302, b"", "text/plain", [
            ("Location", to), ("Cache-Control", "no-store"), ("Referrer-Policy", "no-referrer"),
            ("Set-Cookie", "%s=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=%d%s"
             % (trial.COOKIE, trial.cookie_value(SECRET, r), age, sec)),
            ("Set-Cookie", "hv_trial_on=1; Path=/; SameSite=Lax; Max-Age=%d%s" % (age, sec)),
            # A trial browser is no one's portal account: drop any client pass it carried.
            ("Set-Cookie", VIEWER_COOKIE + "=; Path=/; Max-Age=0")])

    def _do_get(self):
        path = self.route(urllib.parse.urlparse(self.path).path)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))

        # One gate for every module (phase 1, 2026-10-25): a tenant whose module is off is
        # refused here, before any handler runs. Staff are never gated; see modules.py.
        off = modules.refusal_for(self, path, query)
        if off is not None:
            return self.send_json(off["status"], off["body"], self.cors())

        if path == "/api/access/state":
            # What a person meets in a module they cannot open (the locked page): access_api.py.
            import access_api
            st, payload = access_api.state(self, query)
            return self.send_json(st, payload, self.cors() + [("Cache-Control", "no-store")])
        if path.startswith("/go/"):
            return self.go(path[len("/go/"):])
        if path.startswith("/insights/"):
            return self.insights_public(path[len("/insights/"):], query)
        if path == "/api/campaigns":
            return self.api_campaigns()
        if path == "/api/campaign/refresh":
            return self.api_campaign_refresh(query.get("t") or "", False)
        if path == "/api/campaign/comments":
            # What people say (2026-10-19): the full comment list for the client's browser, same access as the report.
            self._share_token = (query.get("share") or "").strip()
            k, status = self.viewer_campaign(query.get("t") or "", public_ok=True)
            if k is None:
                return self.send_json(status, {"ok": False}, self.cors())
            if not metrics.visibility(k).get("audience", True):
                return self.send_json(200, {"ok": True, "items": []}, self.cors())
            import comments
            return self.send_json(200, dict(comments.client_list(k), ok=True), self.cors())
        if path == "/api/campaign":
            self._share_token = (query.get("share") or "").strip()
            return self.api_campaign(query.get("t") or "")
        if path == "/api/creator":
            return self.api_creator((query.get("c") or "").strip().upper())
        if path == "/api/creator-media":
            return self.api_creator_media(query.get("c") or "", query.get("n") or "")
        if path == "/api/campaign-logo":
            return self.api_campaign_logo(query.get("t") or "", query.get("n") or "")
        if path == "/api/campaign-thumb":
            return self.api_campaign_thumb(query.get("t") or "", query.get("n") or "")
        if path == "/api/campaign.csv":
            return self.api_campaign_csv(query.get("t") or "")
        if path.startswith("/api/capture/"):
            return self.capture_get(path[len("/api/capture/"):], query)
        if path in ("/api/roster/page", "/api/roster/facets", "/api/roster/cards"):
            return self.api_roster_paged(path.rsplit("/", 1)[1],
                                         urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query, keep_blank_values=True))
        if path == "/api/admin/creator":
            return self.api_admin_creator_get((query.get("code") or "").strip().upper())
        if path.startswith("/api/") and self.portal_get(path, query):
            return
        if path == "/api/roster":
            return self.api_roster((query.get("link") or "").strip()[:80])
        if path == "/api/licences":
            # Advertising licences for the cards: bio claims and verified ones only.
            if not self.viewer_code_id():
                return self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
            import licence
            return self.send_json(200, {"ok": True, "licences": licence.for_roster()}, self.cors())
        if path == "/api/discover/facets":
            return self.api_discover("facets")
        if path == "/api/my/evidence":
            import tenant_api
            st, payload = tenant_api.evidence_list(self)
            return self.send_json(st, payload, self.cors() + [("Cache-Control", "no-store")])
        if path == "/api/my/campaigns":
            import tenant_api
            st, payload = tenant_api.campaigns_list(self)
            return self.send_json(st, payload, self.cors() + [("Cache-Control", "no-store")])
        if path == "/api/my/competitors":
            # The tenant's own list (Helvi Intelligence at manage). tenant_api does the gating.
            import tenant_api
            st, payload = tenant_api.competitors_list(self)
            return self.send_json(st, payload, self.cors())
        if path == "/api/evidence":
            return self.api_evidence(query.get("s") or "")
        if path == "/api/brand-logo":
            got = evidence.logo_file(query.get("n") or "")
            if not got:
                return self.send(404, b"", "text/plain")
            return self.send(200, got[0], got[1], [("Cache-Control", "public, max-age=2592000"),
                                                    ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")])
        if path == "/api/evidence/map":
            return self.api_evidence(query.get("s") or "", None, None, True)
        if path == "/api/evidence/thumb":
            return self.api_evidence(query.get("s") or "", None, kam_scope._int(query.get("p")))
        if path == "/api/evidence/creator":
            return self.api_evidence(query.get("s") or "", (query.get("c") or "").strip().upper())
        if path == "/api/selection/gate":
            gs = db.selection(token=query.get("s") or "")
            if gs is None:
                return self.send_json(404, {"ok": False}, self.cors())
            return self.send_json(200, {"ok": True, "scores": bool(gs["scores_published"]),
                                        "analysis": bool(gs["analysis_published"])}, self.cors())
        if path == "/api/selection":
            return self.api_selection(
                query.get("s") or "", query.get("n") or "",
                [c for c in (query.get("c") or "").split(",") if c])
        if path == "/health":
            return self.send_json(200, {"ok": True})
        if path == "/static/admin.css":
            return self.send(200, views.CSS, "text/css; charset=utf-8")
        if path == "/editor.js":
            return self.send(200, views.EDITOR_JS, "application/javascript; charset=utf-8",
                             [("Cache-Control", "public, max-age=31536000, immutable")])
        if path == "/shell.js":
            return self.send(200, ui.SHELL_JS, "application/javascript; charset=utf-8",
                             [("Cache-Control", "public, max-age=31536000, immutable")])
        if path == "/manifest.webmanifest":
            # Lets the admin be added to a phone's home screen and open full-screen, like an app.
            return self.send(200, json.dumps({
                "name": "HelloVoice Admin", "short_name": "HV Admin", "start_url": (BASE or "") + "/",
                "scope": (BASE or "") + "/", "display": "standalone", "background_color": "#f5f3ef", "theme_color": "#121212",
                "icons": [{"src": (BASE or "") + "/static/icon-180.png", "sizes": "180x180", "type": "image/png", "purpose": "any"}]}),
                "application/manifest+json", [("Cache-Control", "public, max-age=86400")])
        if path in ("/static/icon-180.png", "/static/icon-32.png"):
            f = STATIC / Path(path).name
            if f.is_file():
                return self.send(200, f.read_bytes(), "image/png", [("Cache-Control", "public, max-age=604800")])
            return self.send(404, b"", "text/plain")
        if path.startswith("/static/fonts/") or path == "/static/logo-knockout.webp":
            # Brand fonts and logo, kept with the admin so it does not depend on the built site.
            name = Path(path).name
            f = STATIC / ("fonts/" + name if path.startswith("/static/fonts/") else name)
            if f.is_file() and f.suffix in (".ttf", ".webp"):
                ctype = "font/ttf" if f.suffix == ".ttf" else "image/webp"
                return self.send(200, f.read_bytes(), ctype, [("Cache-Control", "public, max-age=604800")])
            return self.send(404, b"", "text/plain")
        if path == "/static/logo.webp":
            # Full-colour mark for the light sign-in page (the knockout one is white on white there).
            f = STATIC / "logo-color.webp"
            if f.exists():
                return self.send(200, f.read_bytes(), "image/webp", [("Cache-Control", "public, max-age=604800")])
            if LOGO.exists():
                return self.send(200, LOGO.read_bytes(), "image/webp")
            return self.send(404, b"", "text/plain")
        if path.startswith("/photo/"):
            # Only admins see these; a client gets photos from the site itself.
            if not self.admin():
                return self.send(404, b"", "text/plain")
            name = Path(path[len("/photo/"):]).name
            f = PHOTO_DIR / name
            if f.is_file() and f.parent == PHOTO_DIR:
                # The roster puts 758 of these on one page. "no-cache" with no
                # validator left the browser nothing to revalidate against, so
                # every photo was fetched in full on every visit — 21.1 MB a
                # page load, and the wait that produced the broken pipes in the
                # log. With an ETag the same request costs an empty 304.
                st = f.stat()
                tag = '"%x-%x"' % (int(st.st_mtime), st.st_size)
                if self.headers.get("If-None-Match") == tag:
                    return self.send(304, b"", "image/jpeg",
                                     [("ETag", tag), ("Cache-Control", "no-cache")])
                return self.send(200, f.read_bytes(), "image/jpeg",
                                 [("ETag", tag),
                                  ("Last-Modified", formatdate(st.st_mtime, usegmt=True)),
                                  ("Cache-Control", "no-cache")])
            return self.send(404, b"", "text/plain")
        if path == "/login":
            return self.send(200, views.login_page(query.get("e"), BASE))
        if path == "/login/email":
            em = (query.get("email") or "").strip().lower()
            return self.send(200, views.login_code_page(em, "That code is not right or has expired." if query.get("e") else None, BASE)) if em else self.redirect("/login")
        if path == "/login/2fa":
            row = self.pending_2fa()
            if row is None:
                return self.redirect("/login")
            secret = None
            if not row["totp_on"]:
                secret = row["totp_secret"] or team.new_secret()
                if not row["totp_secret"]:
                    with db.connect() as conn:
                        conn.execute("UPDATE admins SET totp_secret = ? WHERE id = ?", (secret, row["id"]))
            return self.send(200, team_views.two_step_page(row["email"], secret,
                                                           "That code is not right. Try the newest one." if query.get("e") else None))
        if path == "/logout":
            token = auth.unsign(self.cookies().get(ADMIN_COOKIE, ""), SECRET)
            if token:
                db.drop_session(token)
            return self.redirect("/login", [("Set-Cookie", f"{ADMIN_COOKIE}=; Path=/; Max-Age=0")])

        who = self.require_admin()
        if not who:
            return
        views.set_user(who["email"] if "email" in who.keys() else "")
        ui.set_role(team.role_of(who))

        # Roles, and a password re-check for exports.
        if not team.can(who, "GET", path, query):
            return self.send(403, team_views.forbidden_page(team.role_of(who)))
        # Key account managers: their own clients only (kam_scope). Lists filter at the source.
        scope = kam_scope.clients(who)
        kam_scope.begin(scope)
        if kam_scope.check(scope, "GET", path, query):
            return self.not_your_client(path)
        if team.needs_step_up("GET", path) and not team.fresh(who):
            raw_q = urllib.parse.urlparse(self.path).query
            return self.redirect("/reauth?next=" + urllib.parse.quote(path + ("?" + raw_q if raw_q else "")))
        if team.needs_step_up("GET", path):
            team.log("export", who["email"], path, self.client_ip())
        if path == "/team":
            secret = None
            if query.get("setup") and not who["totp_on"]:
                a = team.admin_by_id(who["admin_id"])
                secret = a["totp_secret"]
            return self.send(200, team_views.team_page(who, query.get("ok"), query.get("e"), secret,
                                                       (query.get("new"), query.get("pw")) if query.get("new") and query.get("pw") else None))
        if path == "/reauth":
            nxt = query.get("next") or "/"
            return self.send(200, team_views.reauth_page(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/",
                                                         bool(who["totp_on"]), bool(query.get("again")), "That is not right." if query.get("e") else None, bool(query.get("mailed"))))
        if path in ("/ai", "/ai/history", "/portal", "/portal/user", "/portal/usage.csv", "/portal/chat", "/portal/quote"):
            return self.portal_admin_get(path, query, who)
        if path == "/api/search":
            return self.api_search((query.get("q") or "").strip())
        if path == "/":
            if scope is not None:
                return self.send(200, views.kam_dashboard(who, scope, message=query.get("ok"), error=query.get("e")))
            return self.send(200, views.control_centre(who, message=query.get("ok"), error=query.get("e")))
        if path == "/history":
            kind = (query.get("kind") or "").strip() or None
            q = (query.get("q") or "").strip() or None
            rows = history.listing(kind, q, limit=5000)
            pg, start = views.page_slice(len(rows), query.get("page"))
            later = {r["id"]: len(history.later_changes(r)) for r in rows[start:start + views.PER_PAGE]
                     if not r["undone_at"] and r["action"] != "undo"}
            return self.send(200, views.history_page(rows, later, kind, q, query.get("ok"), query.get("e"), pg))
        if path == "/codes":
            lists = {}
            for sel in db.list_selections():
                if sel["code_id"]:
                    lists.setdefault(sel["code_id"], []).append(sel["name"])
            return self.send(200, views.codes_page(db.list_codes(), query.get("new"), query.get("e"),
                                                   db.code_devices(), query.get("ok"), lists))
        if path == "/open-catalogue":
            # Straight into the catalogue as the signed-in admin: the page
            # opens on the "already unlocked" cookie and the admin session
            # stands in for the passcode on every call it then makes.
            db.admin_code_id()
            return self.send(303, b"", "text/plain", [
                ("Location", self.site_origin() + "/"),
                ("Set-Cookie", "cat-ok=1; Path=/; SameSite=Lax")])
        if path == "/analytics":
            # Two dates off a calendar, not a fixed window. int(query["days"])
            # used to sit here and raised ValueError on anything non-numeric in
            # the URL — a hand-edited address was a 500.
            today = db.now()
            default_from = today - 29 * 86400
            start = db.day_bounds(query.get("from", ""), db.day_bounds(
                time.strftime("%Y-%m-%d", time.gmtime(default_from)), default_from))
            # `to` is inclusive to the person picking it, so the window runs to
            # the end of that day rather than its midnight.
            end = db.day_bounds(query.get("to", ""), today) + 86400
            return self.send(200, views.analytics_page(
                db.stats(start=start, end=end), db.recent_events(200)))
        if path == "/roster":
            # Date added: two days off a calendar, both inclusive.
            d_from, d_to = (query.get("from") or "").strip(), (query.get("to") or "").strip()
            t_from = db.day_bounds(d_from, None) if d_from else None
            t_to = db.day_bounds(d_to, None) if d_to else None
            if t_to is not None:
                t_to += 86400 - 1
            everyone = db.list_creators(search=query.get("q"), added_from=t_from, added_to=t_to)
            editing = (query.get("edit") or "").strip().upper() or None
            total = len(everyone)
            pages = max(1, -(-total // ROSTER_PAGE))

            # Opening a creator has to land on the page that creator is on, or
            # the form would be rendered into a slice that is not being shown
            # and the Edit button would appear to do nothing.
            if editing is not None:
                at = next((i for i, c in enumerate(everyone)
                           if c["code"] == editing), None)
                page = 1 if at is None else at // ROSTER_PAGE + 1
            else:
                asked = (query.get("page") or "1").strip()
                page = int(asked) if asked.isdigit() and int(asked) > 0 else 1
                page = min(page, pages)

            start = (page - 1) * ROSTER_PAGE
            return self.send(200, views.roster_page(
                everyone[start:start + ROSTER_PAGE],
                query.get("e"), query.get("ok"),
                cities=db.known_cities(), tiers=db.list_tiers(),
                nationalities=db.known_nationalities(),
                interests=db.known_interests(),
                editing=editing,
                q=(query.get("q") or "").strip(),
                bands=db.tier_bands(),
                tab=query.get("tab"), dupes=db.duplicate_groups(),
                page_no=page, pages=pages, total=total, per_page=ROSTER_PAGE,
                dates=(d_from if t_from is not None else "", d_to if t_to is not None else "")))
        if path == "/roster/quality":
            return self.roster_quality(query)
        if path == "/roster/review":
            country = query.get("country") if query.get("country") in industry.COUNTRIES else None
            row = industry.next_in_queue(country, query.get("after"))
            card = industry.review_card(row, BASE) if row is not None else None
            return self.send(200, industry_views.review_page(card, industry.queue_counts(country), country, query.get("ok"), query.get("e")))
        if path == "/roster/export":
            only = {c.strip().upper() for c in (query.get("codes") or "").split(",") if c.strip()} or None
            return self.send(200, self.roster_csv(only), "text/csv; charset=utf-8",
                             [("Content-Disposition",
                               'attachment; filename="roster.csv"')])
        if path == "/roster/template.xlsx":
            # The only format that can carry pictures — a CSV is text.
            try:
                book = importer.template_xlsx()
            except RuntimeError as ex:
                return self.redirect("/roster?e=" + urllib.parse.quote(str(ex)))
            return self.send(
                200, book,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                [("Content-Disposition",
                  'attachment; filename="creator-import-template.xlsx"')])
        if path == "/roster/template":
            return self.send(200, importer.template_csv(), "text/csv; charset=utf-8",
                             [("Content-Disposition",
                               'attachment; filename="creator-import-template.csv"')])
        if path == "/licences":
            import licence
            return self.send(200, licence.page_html(query))
        if path == "/tenants" or path.startswith("/tenants/"):
            # Who has which module. Owners configure the platform; admins run the business, so an admin
            # reads the list and a company's page and may Share access there (Bido 2026-10-28), nothing more.
            role_ = team.role_of(who)
            if role_ != "owner" and not (role_ == "admin" and path in ("/tenants", "/tenants/co")):
                return self.send(403, team_views.forbidden_page(team.role_of(who)))
            import tenants
            if path == "/tenants/co":
                return self.send(200, tenants.company_html((query.get("k") or "").strip(), query, owner=role_ == "owner"))
            if path == "/tenants/requests":
                return self.send(200, tenants.requests_html(query))
            if path == "/tenants/trials":
                return self.send(200, trial.admin_html(query, next(iter(sorted(ALLOWED_ORIGINS)), "")))
            if path == "/tenants/hist":
                return self.send_json(200, tenants.history_rows((query.get("k") or "").strip(), query.get("f") or ""),
                                      [("Cache-Control", "no-store")])
            if path == "/tenants":
                return self.send(200, tenants.page_html(query))
        if path == "/requests":
            return self.send(200, views.requests_page(db.list_requests(),
                                                      db.list_creators(), db.tier_prices()))
        if path == "/api/pulse":
            return self.send_json(200, db.request_pulse(), [("Cache-Control", "no-store")])
        if path == "/selections":
            arch = query.get("archived") == "1"
            every = db.list_selections()
            n_arch = sum(1 for x in every if x["archived_at"])
            shown = [x for x in every if bool(x["archived_at"]) == arch]
            pg, start = views.page_slice(len(shown), query.get("page"))
            with db.connect() as conn:
                counts = {r[0]: r[1] for r in conn.execute(
                    "SELECT selection_id, COUNT(*) FROM campaigns WHERE selection_id IS NOT NULL GROUP BY selection_id")}
            return self.send(200, views.selections_page(
                shown[start:start + views.PER_PAGE], query.get("e"), query.get("ok"), self.site_origin(),
                archived=arch, n_archived=n_arch, page_no=pg, total=len(shown),
                clients=[c for c in db.list_codes() if not (c["archived_at"] if "archived_at" in c.keys() else None)],
                currencies=[c for c in fx.CURRENCIES if fx.usable(c)], camp_counts=counts,
                interests=db.known_interests()))
        if path == "/selections/edit":
            sid = query.get("id", "")
            sel = db.selection(int(sid)) if sid.isdigit() else None
            if sel is None:
                return self.redirect("/selections?e=" + urllib.parse.quote("That selection no longer exists."))
            return self.send(200, views.selection_edit_page(
                sel, db.list_creators(), db.tier_prices(), self.site_origin(),
                query.get("e"), query.get("ok"), db.campaigns_for_selection(sel["id"]),
                interests=db.known_interests(), access_codes=db.list_codes()))
        if path == "/selections/fit":
            # The Fit & tags tab, fetched when it is opened.
            sid = query.get("id", "")
            sel = db.selection(int(sid)) if sid.isdigit() else None
            if sel is None:
                return self.send(404, "<p class='err'>That selection no longer exists.</p>")
            return self.send(200, views.selection_fit_panel(sel, db.list_creators(), self.selection_scores(sel), db.known_interests()))
        if path == "/campaigns/comments":
            import comments
            return comments.admin_get(self, query)
        if path == "/campaigns/sales":
            import sales
            return sales.admin_get(self, query)
        if path == "/campaigns/sales/template.xlsx":
            import sales
            return sales.template_get(self)
        if path == "/campaigns/setup":
            return self.get_campaign_setup(query)
        if path == "/campaigns/template.xlsx":
            import campaign_sheet
            return self.send(200, campaign_sheet.template(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             [("Content-Disposition", 'attachment; filename="campaign-template.xlsx"')])
        if path == "/campaigns":
            return self.send(200, views.campaigns_page(
                db.list_campaigns(), db.list_codes(), query.get("e"), query.get("ok"),
                selections=db.list_selections()))
        if path in ("/campaigns/content", "/campaigns/report", "/campaigns/insights",
                    "/campaigns/export.xlsx", "/campaigns/export.csv", "/campaigns/insight-file"):
            cid = query.get("id", "")
            k = db.campaign(int(cid)) if cid.isdigit() else None
            if k is None:
                return self.redirect("/campaigns?e=" + urllib.parse.quote("That campaign no longer exists."))
            if path == "/campaigns/content":
                return self.send(200, views.campaign_content_page(
                    k, db.campaign_creators(k["id"]), self.all_posts(k),
                    query.get("e"), query.get("ok")))
            if path == "/campaigns/report":
                return self.send(200, views.campaign_report_page(
                    k, metrics.report(k, internal=True), self.site_origin()))
            if path == "/campaigns/insights":
                return self.send(200, views.campaign_insights_page(
                    k, db.campaign_insights(k["id"]), db.campaign_creators(k["id"]),
                    db.campaign_content(k["id"]), self.site_origin(), query.get("e"), query.get("ok")))
            if path == "/campaigns/insight-file":
                return self.insight_file(query.get("i", ""), query.get("n", ""), k["id"])
            if path == "/campaigns/export.csv":
                return self.send(200, self.posts_csv(metrics.report(k, internal=True)),
                                 "text/csv; charset=utf-8",
                                 [("Content-Disposition", 'attachment; filename="posts-%s.csv"'
                                   % db.campaign_slug(k))])
            return self.send(200, self.report_xlsx(k),
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             [("Content-Disposition", 'attachment; filename="report-%s.xlsx"'
                               % db.campaign_slug(k))])
        if path == "/clients/preview/exit":
            gone = "; Path=/; HttpOnly; Max-Age=0; SameSite=Lax"
            return self.redirect("/clients", [("Set-Cookie", VIEWER_COOKIE + "=" + gone),
                                              ("Set-Cookie", PREVIEW_COOKIE + "=" + gone)])
        if path == "/clients" and not (query.get("archived") or query.get("page")):
            import hub_views
            return self.send(200, hub_views.clients_page(query.get("show") or "all", query.get("open"), query.get("ok"), query.get("e")))
        if path == "/access-requests":
            import access
            return self.send(200, access.page(query.get("ok"), query.get("e"), can=self.admin_like_for))
        if path == "/evidence":
            return self.send(200, evidence.list_page(kam_scope.clients(who), db.list_codes(), db.list_selections(),
                                                     query.get("ok"), query.get("e")))
        if path == "/evidence/template":
            import evidence_xlsx
            return self.send(200, evidence_xlsx.template(),
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             [("Content-Disposition", 'attachment; filename="competitor-evidence-template.xlsx"'),
                              ("Cache-Control", "no-store")])
        if path == "/evidence/view":
            pk = evidence.pack(kam_scope._int(query.get("id")))
            if pk is None:
                return self.redirect("/evidence?e=" + urllib.parse.quote("That pack is gone."))
            sels = [s for s in db.list_selections() if pk["code_id"] is None or s["code_id"] == pk["code_id"]]
            return self.send(200, evidence.view_page(pk, query.get("brand"), sels, query.get("ok"), query.get("e"),
                                                     (query.get("c") or "").strip().upper() or None))
        if path == "/work":
            import hub_views
            return self.send(200, hub_views.board_page(query.get("ok"), query.get("e"), query.get("team") == "1"))
        if path in ("/clients", "/clients/by-code"):
            arch = query.get("archived") == "1"
            every = db.client_overview()
            n_arch = sum(1 for o in every if o["code"]["archived_at"])
            shown = [o for o in every if bool(o["code"]["archived_at"]) == arch]
            pg, start = views.page_slice(len(shown), query.get("page"), 20)
            return self.send(200, views.clients_page(shown[start:start + 20], self.site_origin(),
                                                     archived=arch, n_archived=n_arch, page_no=pg,
                                                     total=len(shown), ok=query.get("ok")))
        if path == "/analysis":
            return self.send(200, views.analysis_page(
                db.list_creators(), db.analysis_platforms(), db.analysis_requests(), self.site_origin(),
                query.get("q", ""), query.get("e"), query.get("ok"), platform=query.get("p", ""),
                sources=([("selection:%d" % r["id"], "Selection · " + r["name"]) for r in db.list_selections()]
                         + [("campaign:%d" % r["id"], "Campaign · " + r["name"]) for r in db.list_campaigns()]),
                page_no=int(query["page"]) if (query.get("page") or "").isdigit() and int(query["page"]) > 0 else 1))
        if path == "/selections/suggest":
            return self.selection_suggest(query)
        if path == "/analysis/review":
            return self.analysis_review_get(query)
        if path == "/analysis/find":
            return self.analysis_find(query)
        if path == "/analysis/template.xlsx":
            code = re.sub(r"[^A-Z0-9-]", "", (query.get("code") or "").upper())[:20] or None
            return self.send(200, analysis.template_xlsx(code),
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             [("Content-Disposition", 'attachment; filename="creator-analysis-%s.xlsx"'
                               % (code or "template"))])
        if path == "/analysis/json":
            code = (query.get("c") or "").upper()
            a = db.analysis(code, analysis.canon_platform(query.get("p")))
            return self.send(200, json.dumps(a["data"] if a else {}, indent=2, ensure_ascii=False),
                             "application/json; charset=utf-8")
        if path == "/planner":
            return self.planner_get(query)
        if path == "/calculator":
            return self.send(200, views.calculator_page(
                plans.library(), plans.sources(), initial=("c:" + query["id"]) if (query.get("id") or "").isdigit() else None,
                ok=query.get("ok"), error=query.get("e")))
        if path == "/campaigns/thumb":
            f = thumbs.path_of("file:" + Path(query.get("n") or "").name)
            if f is None:
                return self.send(404, b"", "text/plain")
            kind = uploads.image_kind(f.read_bytes()[:16]) or "jpg"
            return self.send(200, f.read_bytes(), "image/" + ("jpeg" if kind == "jpg" else kind),
                             [("Cache-Control", "private, max-age=604800")])
        if path == "/campaigns/logo":
            # The admin's own preview of an uploaded logo.
            name = Path(query.get("n") or "").name
            f = LOGO_DIR / name
            if not f.is_file():
                return self.send(404, b"", "text/plain")
            kind = uploads.image_kind(f.read_bytes()[:16]) or "png"
            return self.send(200, f.read_bytes(), "image/" + ("jpeg" if kind == "jpg" else kind))
        if path == "/app-alerts" or path.startswith("/app-alerts/"):
            return self.get_app_alerts(path, query)
        if path == "/settings":
            return self.send(200, views.settings_page(
                db.setting("emv_rates") or {}, metrics.factors(),
                bool(db.setting("capture_token")), db.capture_runs(), track.GEO_DB.exists(),
                None, query.get("e"), query.get("ok"), metrics.benchmarks(), fx_rates=fx.rates()))
        if path == "/apis/runs.csv":
            return self.send(200, apify.runs_csv().encode(), "text/csv; charset=utf-8",
                             [("Content-Disposition", "attachment; filename=apify-runs.csv")])
        if path == "/apis/creator" and query.get("code"):
            return self.send(200, apis_view.creator_page(query["code"].upper()))
        if path == "/apis/run" and query.get("id", "").isdigit():
            return self.send(200, apis_view.run_page(int(query["id"])))
        if path == "/apis/run.json" and query.get("id", "").isdigit():
            data = [dict(code=r["code"], actor=r["actor"], data=json.loads(r["data"]))
                    for r in apify.run_results(int(query["id"]))]
            return self.send(200, json.dumps(data, indent=2, ensure_ascii=False).encode(),
                             "application/json; charset=utf-8",
                             [("Content-Disposition", "attachment; filename=run-%s.json" % query["id"])])
        if path == "/reference/goal-formulas":
            import goal_docs
            return self.send(200, goal_docs.page_html())
        if path == "/reference":
            return self.send(200, reference_view.reference_page(query))
        if path == "/apis":
            return self.send(200, apis_view.apis_page(query.get("e"), query.get("ok"), query.get("tab", "overview"), query.get("q", ""), query))
        if path == "/campaigns/links":
            cid = query.get("id", "")
            k = db.campaign(int(cid)) if cid.isdigit() else None
            if k is None:
                return self.redirect("/campaigns?e=" + urllib.parse.quote("That campaign no longer exists."))
            return self.send(200, views.campaign_links_page(
                k, db.campaign_links(k["id"]), db.click_stats(k["id"]), self.site_origin(),
                track.GEO_DB.exists(), query.get("e"), query.get("ok")))
        if path == "/campaigns/clicks.csv":
            cid = query.get("id", "")
            k = db.campaign(int(cid)) if cid.isdigit() else None
            if k is None:
                return self.send(404, b"", "text/plain")
            return self.send(200, self.clicks_csv(k["id"]), "text/csv; charset=utf-8",
                             [("Content-Disposition", 'attachment; filename="clicks-%s.csv"'
                               % db.campaign_slug(k))])
        if path == "/campaigns/edit":
            cid = query.get("id", "")
            k = db.campaign(int(cid)) if cid.isdigit() else None
            if k is None:
                return self.redirect("/campaigns?e=" + urllib.parse.quote("That campaign no longer exists."))
            sel = db.selection(k["selection_id"]) if k["selection_id"] else None
            return self.send(200, views.campaign_edit_page(
                k, db.campaign_creators(k["id"]), db.list_codes(), db.rules_of(k), sel,
                query.get("e"), query.get("ok"), self.client_logo_names(), db.list_selections(),
                metrics.report(k, internal=True)))
        return self.send(404, views.simple("Not found", "That page does not exist."))

    def do_HEAD(self):
        """Link-preview fetchers often ask with HEAD. Only tracking links
        answer it — logged as a preview, never counted as a click."""
        path = self.route(urllib.parse.urlparse(self.path).path)
        if trial.ACTIVE or path.startswith("/try"):
            return self.send(405, b"", "text/plain")
        if path.startswith("/go/"):
            return self.go(path[len("/go/"):])
        return self.send(405, b"", "text/plain")

    def go(self, slug):
        """A tracking link: record the tap, send the visitor on.

        302 with no-store, so a second tap is a second request we see rather
        than a redirect the browser remembered. A link that is switched off, or
        whose campaign has nowhere to send people yet, says so plainly instead
        of throwing the visitor at an error page."""
        row = db.link(slug.strip("/").lower()) if slug else None
        dest = (row["destination"] or row["campaign_destination"]) if row else None
        if row is None or not row["active"] or not dest:
            return self.send(404, views.link_gone(), headers=[("Cache-Control", "no-store")])
        ua = self.headers.get("User-Agent", "")
        ref = self.headers.get("Referer", "")
        app = track.app_of(ua, ref)
        device, os_ = track.device_of(ua)
        bot = track.is_bot(ua, self.command)
        ip = self.client_ip()
        try:
            db.record_click(row, db.now(), track.visitor(ip, ua, CLICK_SALT), app, device, os_,
                            track.country_of(ip, self.headers.get("CF-IPCountry")), ref, bot)
        except Exception as ex:   # a failed log must never cost the visitor the redirect
            sys.stderr.write("click not recorded: %r\n" % ex)
        k = {"id": row["campaign_id"], "name": row["campaign_name"]}
        to = track.with_utm(dest, db.campaign_slug(k), row["code"], app)
        return self.send(302, b"", "text/plain",
                         [("Location", to), ("Cache-Control", "no-store"),
                          ("Referrer-Policy", "no-referrer"), ("X-Robots-Tag", "noindex")])

    def too_many(self, retry, body=None):
        """429 in the shape the caller expects: JSON for /api/*, text otherwise."""
        h = [("Retry-After", str(max(1, retry)))]
        if self.path.split("?")[0].startswith(BASE + "/api/") or self.path.startswith("/api/"):
            return self.send_json(429, body or {"ok": False, "reason": "slow_down",
                                                "retry_after": max(1, retry)}, self.cors() + h)
        return self.send(429, "Too many attempts. Wait a few minutes and try again.",
                         "text/plain; charset=utf-8", h)

    def do_POST(self):
        if self.trial_route():
            return
        if self.route(urllib.parse.urlparse(self.path).path) in self.MEMO_POSTS:
            portal.memo_begin()
        self._unlock_begin()
        try:
            return self._do_post()
        finally:
            portal.unlock_begin(False)
            kam_scope.end()
            portal.memo_end()
            trial.end()

    def _do_post(self):
        path = self.route(urllib.parse.urlparse(self.path).path)
        history.start_request()
        off = modules.refusal_for(self, path, dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query)))
        if off is not None:
            return self.send_json(off["status"], off["body"], self.cors())

        # CSRF: a cross-site form post cannot forge Origin / Sec-Fetch-Site.
        if not guard.origin_ok(self.headers, ALLOWED_ORIGINS):
            db.log("csrf_block", ip=self.client_ip(), user_agent=self.headers.get("User-Agent"),
                   detail=f"{self.headers.get('Origin', '')[:80]} {path[:60]}")
            return self.send(403, "Cross-site request blocked.", "text/plain; charset=utf-8")
        # A blanket ceiling on the public API, so no single address can hammer it.
        if path.startswith("/api/") and not guard.limiter.allow(f"api:{self.client_ip()}", 240, 60):
            return self.too_many(guard.limiter.retry_after(f"api:{self.client_ip()}", 240, 60))
        if path.startswith("/api/"):
            guard.limiter.hit(f"api:{self.client_ip()}")

        if path.startswith("/api/") and path not in PREVIEW_POSTS and (self.preview_mode() or (self.as_client() and path != "/api/auth/logout")):
            return self.send_json(403, {"ok": False, "reason": "preview",
                                        "message": "You are previewing as a client: this is read-only. Exit the preview to make changes."},
                                  self.cors())
        if path == "/api/admin/creator":
            return self.api_admin_creator_post()
        if path == "/api/admin/board/move":
            return self.api_board_move()
        if path == "/api/admin/creator/photo":
            return self.api_admin_creator_photo()
        if path.startswith("/api/") and self.portal_post(path):
            return
        if path == "/api/unlock":
            return self.api_unlock()
        if path == "/api/request":
            return self.api_request()
        if path in ("/api/discover", "/api/discover/like", "/api/discover/parse"):
            return self.api_discover(path.rsplit("/", 1)[-1])
        if path == "/api/event":
            return self.api_event()
        if path == "/api/selection/tags":
            return self.api_selection_tags()
        if path == "/api/selection/platform":
            return self.api_selection_platform()
        if path == "/api/access/request":
            # "Request this module" / "Request access" on a locked page: access_api.py files it in the Tenants inbox.
            import access_api
            st, payload = access_api.request(self, self.json_body())
            return self.send_json(st, payload, self.cors())
        if path.startswith("/api/my/"):
            # A tenant writing their own, when their module is set to manage (tenant_api.py).
            import tenant_api
            b = self.json_body()
            if path == "/api/my/post":
                st, payload = tenant_api.add_post(self, b)
            elif path == "/api/my/post/update":
                st, payload = tenant_api.update_post(self, b)
            elif path == "/api/my/campaign":
                st, payload = tenant_api.campaign_save(self, b)
            elif path == "/api/my/competitor":
                st, payload = tenant_api.competitor_save(self, b)
            elif path == "/api/my/competitor/collect":
                st, payload = tenant_api.collect(self, b)
            else:
                st, payload = 404, {"ok": False}
            return self.send_json(st, payload, self.cors())

        if path == "/api/evidence/add":
            return self.api_evidence_add()
        if path == "/api/evidence/request":
            return self.api_evidence_request()
        if path == "/api/selection/status/bulk":           # item 242
            import selfilters
            return selfilters.api_bulk(self)
        if path == "/api/selection/tags/bulk":
            import selfilters
            return selfilters.api_bulk_tags(self)
        if path == "/api/selection/views":
            import selfilters
            return selfilters.api_views(self)
        if path == "/api/selection/order":          # item 3b (Bido, 25 Oct 2026): card order, set on the selection page
            return self.api_selection_order()
        if path == "/api/selection/status":
            return self.api_selection_status()
        if path == "/api/selection/scores":
            return self.api_selection_scores_publish()
        if path == "/api/selection/request-access":
            return self.api_selection_request_access()
        if path == "/api/selection/invite":
            return self.api_selection_invite()
        if path == "/api/campaign/share":
            return self.api_campaign_share()
        if path == "/api/campaign/refresh":
            b = self.json_body()
            return self.api_campaign_refresh((b.get("t") or ""), True, "comments" if b.get("what") == "comments" else "posts")
        if path == "/api/campaign/refresh-request":
            return self.api_campaign_refresh_request()
        if path == "/api/campaign/start":
            return self.api_campaign_start()
        if path == "/api/campaign/build-selection":
            return self.api_campaign_build_selection()
        if path == "/api/selection/reason":
            return self.api_selection_reason()
        if path == "/api/selection/replace":
            return self.api_selection_replace()
        if path == "/api/selection/rename":
            return self.api_selection_rename()
        if path == "/api/selection":
            return self.api_selection_save()
        if path == "/api/creator/request":
            return self.api_creator_request()
        if path.startswith("/api/capture/"):
            return self.capture_post(path[len("/api/capture/"):])
        if path.startswith("/insights/"):
            return self.insights_upload(path[len("/insights/"):])
        if path == "/login":
            return self.post_login()
        if path == "/login/2fa":
            return self.post_login_2fa()
        if path == "/login/email":
            return self.post_login_email()
        if path == "/login/email/verify":
            return self.post_login_email_verify()

        who = self.require_admin()
        if not who:
            return
        history.set_actor(who["email"] if "email" in who.keys() else "admin")
        views.set_user(who["email"] if "email" in who.keys() else "")
        ui.set_role(team.role_of(who))
        if not team.can(who, "POST", path):
            return self.send(403, team_views.forbidden_page(team.role_of(who)))
        scope = kam_scope.clients(who)
        kam_scope.begin(scope)
        if kam_scope.check(scope, "POST", path, None, self.form_body() if not self.headers.get("Content-Type", "").startswith("application/json") else {}):
            return self.not_your_client(path)
        if team.needs_step_up("POST", path) and not team.fresh(who):
            ref = urllib.parse.urlparse(self.headers.get("Referer") or "").path or "/"
            if BASE and ref.startswith(BASE):
                ref = ref[len(BASE):] or "/"
            return self.redirect("/reauth?again=1&next=" + urllib.parse.quote(ref))
        if path == "/reauth":
            return self.post_reauth(who)
        if path.startswith("/team/") or path.startswith("/account/2fa/"):
            return self.post_team(path, who)
        if path in ("/ai/chat", "/ai/confirm", "/ai/dismiss") or path.startswith("/portal/"):
            if path == "/portal/keys":
                team.log("key", who["email"], (self.form_body().get("which") or "") + " " + (self.form_body().get("action") or "save"), self.client_ip())
            return self.portal_admin_post(path, who)
        if path == "/history/undo":
            return self.post_history_undo()
        if path == "/clients/preview":
            return self.post_client_preview()
        if path.startswith("/app-alerts/"):
            return self.post_app_alerts(path, who)
        if path.startswith("/tenants/"):
            if path == "/tenants/share" and team.role_of(who) in ("owner", "admin"):
                # Share access (Bido 2026-10-28): owners and admins, never a KAM or a viewer.
                import tenants
                import workspace
                import datetime
                b = self.json_body()
                c = tenants.company(str(b.get("k") or ""))
                if c is None:
                    return self.send_json(404, {"ok": False, "message": "No such company."})
                until = None
                if str(b.get("until") or "").strip():
                    try:
                        d = datetime.datetime.strptime(str(b["until"])[:10], "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
                        until = int(d.timestamp()) + 86399          # through the end of that day
                    except ValueError:
                        return self.send_json(400, {"ok": False, "message": "Pick the end date again."})
                    if until < db.now():
                        return self.send_json(400, {"ok": False, "message": "The end date has passed."})
                ok, msg = workspace.staff_share(c["ids"], b.get("email"), " ".join(str(b.get("name") or "").split())[:120],
                                                b.get("roles") if isinstance(b.get("roles"), dict) else {}, until,
                                                who["email"] if "email" in who.keys() else "")
                return self.send_json(200 if ok else 400, {"ok": ok, "message": msg}, [("Cache-Control", "no-store")])
            if team.role_of(who) != "owner":
                return self.send(403, team_views.forbidden_page(team.role_of(who)))
            import tenants
            by = who["email"] if "email" in who.keys() else ""
            if path == "/tenants/set":
                b = self.json_body()
                ok, msg, val, changed = tenants.apply_edit(str(b.get("k") or ""), str(b.get("field") or ""),
                                                           b.get("value"), by, self.client_ip())
                return self.send_json(200 if ok else 400, {"ok": ok, "error": msg, "value": val, "changed": changed},
                                      [("Cache-Control", "no-store")])
            if path == "/tenants/trials/new":
                f = self.form_body()
                try:
                    r = trial.create(f.get("client"), int(f.get("days") or trial.DAYS), f.get("note") or "", by)
                except ValueError as ex:
                    return self.redirect("/tenants/trials?e=" + urllib.parse.quote(str(ex)))
                return self.redirect("/tenants/trials?new=%d&ok=%s" % (r["id"], urllib.parse.quote(
                    "Link for %s made. Copy it from the list." % r["client"])))
            if path == "/tenants/trials/act":
                f = self.form_body()
                rid = int(f.get("id") or 0) if str(f.get("id") or "").isdigit() else 0
                do = f.get("do") or ""
                r = trial.link(rid)
                if r is None or do not in ("extend", "reset", "revoke"):
                    return self.redirect("/tenants/trials?e=" + urllib.parse.quote("That link no longer exists."))
                {"extend": trial.extend, "reset": trial.reset, "revoke": trial.revoke}[do](rid)
                said = {"extend": "%s: 14 more days.", "reset": "%s: back to the demo data.",
                        "revoke": "%s: ended."}[do] % r["client"]
                return self.redirect("/tenants/trials?ok=" + urllib.parse.quote(said))
            if path == "/tenants/requests/decide":
                f = self.form_body()
                try:
                    rid = int(f.get("id") or 0)
                except ValueError:
                    rid = 0
                ok, said = tenants.decide(rid, f.get("do") or "", (f.get("value") or "").strip(),
                                          (f.get("reply") or "").strip(), by, self.client_ip())
                return self.redirect("/tenants/requests?" + ("ok=" if ok else "e=") + urllib.parse.quote(said))

        if path.startswith("/evidence/"):
            return self.post_evidence(path, who)
        if path == "/campaigns/invite":
            import access
            f = self.form_body()
            cid = (f.get("id") or "").strip()
            k = db.campaign(int(cid)) if cid.isdigit() else None
            if k is None:
                return self.redirect("/campaigns?e=" + urllib.parse.quote("That campaign no longer exists."))
            if not self.admin_like_for(k["code_id"] if k["code_id"] is not None else kam_scope.campaign_code(k["id"])[1],
                                       k["selection_id"], k["id"]):
                return self.redirect("/campaigns?e=" + urllib.parse.quote("That campaign belongs to a client you do not manage."))
            back = "/campaigns/edit?id=%s" % cid
            sel = db.selection(k["selection_id"]) if k["selection_id"] else None
            if f.get("do") == "remove" and sel is not None:
                access.uninvite(sel, f.get("email") or "")
                db.cinvite_remove(k["id"], f.get("email") or "")
                return self.redirect(back + "&ok=" + urllib.parse.quote("Access removed for %s." % (f.get("email") or "that email")))
            if f.get("do") == "add" and not access.known_email(f.get("email") or ""):
                return self.redirect(back + "&e=" + urllib.parse.quote("%s has no portal account yet. Use Send invite: we email them the link." % (f.get("email") or "").strip()))
            state, err = access.invite_campaign(k, f.get("email") or "", who["email"])
            msgs = {"email": "That does not look like an email address.", "self": "That is the owner: they already have it.",
                    "limit": "This already has %d invited people." % access.MAX_INVITES,
                    "no_selection": "This campaign has no selection yet. Link its selection first."}
            if err:
                return self.redirect(back + "&e=" + urllib.parse.quote(msgs[err]))
            return self.redirect(back + "&ok=" + urllib.parse.quote(
                "%s can now open this campaign and its selection." % f.get("email").strip() if state == "granted"
                else "Invited. It opens for %s when they sign in with that email." % f.get("email").strip()))
        if path == "/selections/rename":
            return self.post_selection_rename(who)
        if path == "/selections/invite":
            import access
            f = self.form_body()
            sid = (f.get("id") or "").strip()
            sel = db.selection(int(sid)) if sid.isdigit() else None
            back = "/selections/edit?id=%s" % sid
            if sel is None:
                return self.redirect("/selections?e=" + urllib.parse.quote("That selection no longer exists."))
            if sel["code_id"] is not None and not self.admin_like_for(sel["code_id"], sel["id"]):
                return self.redirect("/selections?e=" + urllib.parse.quote("That selection belongs to a client you do not manage."))
            if f.get("do") == "remove":
                access.uninvite(sel, f.get("email") or "")
                return self.redirect(back + "&ok=" + urllib.parse.quote("Access removed for %s." % (f.get("email") or "that email")) + "#st=share")
            if f.get("do") == "add" and not access.known_email(f.get("email") or ""):
                return self.redirect(back + "&e=" + urllib.parse.quote("%s has no portal account yet. Use Send invite: we email them the link." % (f.get("email") or "").strip()) + "#st=share")
            state, err = access.invite(sel, f.get("email") or "", who["email"])
            msgs = {"email": "That does not look like an email address.", "self": "That is the selection's owner: they already have it.",
                    "limit": "That selection already has %d invited people." % access.MAX_INVITES}
            if err:
                return self.redirect(back + "&e=" + urllib.parse.quote(msgs[err]) + "#st=share")
            return self.redirect(back + "&ok=" + urllib.parse.quote(
                "%s can now open and edit this selection." % f.get("email").strip() if state == "granted"
                else "Invited. This selection opens for %s when they sign in with that email." % f.get("email").strip()) + "#st=share")
        if path == "/access-requests":
            import access
            f = self.form_body()
            rid = kam_scope._int(f.get("id") or "")
            r = db.access_request(rid) if rid is not None else None
            if r is None:
                return self.redirect("/access-requests?e=" + urllib.parse.quote("That request no longer exists."))
            sel = db.selection(r["selection_id"])
            if sel is not None and not self.admin_like_for(sel["code_id"], sel["id"]):
                return self.redirect("/access-requests?e=" + urllib.parse.quote("That selection belongs to a client you do not manage."))
            ok = access.grant(rid, who["email"]) if f.get("do") == "grant" else access.deny(rid, who["email"])
            return self.redirect("/access-requests?ok=" + urllib.parse.quote(
                ("Access granted to %s." if f.get("do") == "grant" else "Request from %s declined.") % (r["email"] or "the person")
                if ok else "Already decided."))
        if path == "/archive":
            f = self.form_body()
            kind = f.get("kind")
            spec = {"client": ("code", "codes", "/clients"), "selection": ("selection", "selections", "/selections")}.get(kind)
            rid = (f.get("id") or "").strip()
            if not spec or not rid.isdigit():
                return self.redirect("/")
            on = f.get("on") == "1"
            entity, table, back = spec
            with history.tracked(entity, rid, ("Archived " if on else "Unarchived ") + describe(entity, rid, kind)):
                db.set_archived(table, int(rid), on)
            return self.redirect(back + ("?archived=1&" if not on else "?") + "ok=" + urllib.parse.quote(
                ("Moved to the archive." if on else "Back from the archive.")))
        spec = TRACKED.get(path)
        if spec:
            return self.tracked_post(path, spec)
        return self.admin_post(path)

    def admin_post(self, path):
        if path.startswith("/apis/"):
            return self.post_apis(path)
        if path == "/codes/new":
            return self.post_code_new()
        if path == "/codes/revoke":
            return self.post_code_revoke()
        if path == "/codes/restore":
            return self.post_code_restore()
        if path == "/codes/archive":
            return self.post_code_archive()
        if path == "/codes/unarchive":
            return self.post_code_unarchive()
        if path == "/codes/delete":
            return self.post_code_delete()
        if path == "/codes/passcode":
            return self.post_code_passcode()
        if path == "/codes/rename":
            return self.post_code_rename()
        if path == "/codes/limits":
            return self.post_code_limits()
        if path == "/codes/device/remove":
            return self.post_device_remove()
        if path == "/roster/save":
            return self.post_roster_save()
        if path == "/roster/review":
            return self.post_roster_review()
        if path == "/selections/new":
            return self.post_selection_new()
        if path == "/selections/save":
            return self.post_selection_save()
        if path == "/selections/delete":
            return self.post_selection_delete()
        if path in ("/selections/assign", "/campaigns/assign"):
            import assign
            return assign.post(self, path)
        if path in ("/selections/kam", "/campaigns/kam"):
            import kam_items
            return kam_items.post(self, path)
        if path == "/campaigns/new":
            return self.post_campaign_new()
        if path in ("/campaigns/import", "/campaigns/import/confirm"):
            return self.post_campaign_import(path.endswith("/confirm"))
        if path == "/campaigns/setup":
            return self.post_campaign_setup()
        if path == "/quote/ready":
            return self.post_quote_ready()
        if path == "/quote/withdraw":
            return self.post_quote_withdraw()
        if path == "/campaigns/save":
            return self.post_campaign_save()
        if path == "/campaigns/comments":
            import comments
            return comments.admin_post(self)
        if path == "/campaigns/sales":
            import sales
            return sales.admin_post(self)
        if path == "/campaigns/status":
            return self.post_campaign_status()
        if path == "/campaigns/delete":
            return self.post_campaign_delete()
        if path == "/campaigns/link":
            return self.post_campaign_link()
        if path == "/campaigns/content/add":
            return self.post_content_add()
        if path == "/campaigns/content/update":
            return self.post_content_update()
        if path == "/campaigns/content/group":
            return self.post_content_group()
        if path == "/campaigns/content/bulk":
            return self.post_content_bulk()
        if path == "/campaigns/content/pending":
            return self.post_content_pending()
        if path == "/campaigns/insights/decide":
            return self.post_insight_decide()
        if path == "/campaigns/insights/upload":
            return self.post_insight_admin_upload()
        if path == "/campaigns/sync":
            return self.post_campaign_sync()
        if path == "/campaigns/link/custom":
            return self.post_custom_link()
        if path == "/campaigns/link/toggle":
            return self.post_link_toggle()
        if path == "/analysis/pdf":
            return self.post_analysis_pdf()
        if path == "/analysis/upload":
            return self.post_analysis_upload()
        if path == "/analysis/template":
            return self.post_analysis_template()
        if path == "/analysis/find":
            return self.analysis_find({}, self.form_body())
        if path == "/analysis/review":
            return self.post_analysis_review()
        if path == "/analysis/save":
            return self.post_analysis_save()
        if path == "/analysis/delete":
            return self.post_analysis_delete()
        if path == "/analysis/handled":
            f = self.form_body()
            if (f.get("id") or "").isdigit():
                db.handle_analysis_request(int(f["id"]))
            return self.redirect("/analysis?ok=" + urllib.parse.quote("Closed without unlocking."))
        if path == "/analysis/fulfil":
            # Unlock the full analysis for the client who asked, and ring their bell.
            f = self.form_body()
            rid = int(f["id"]) if (f.get("id") or "").isdigit() else 0
            with db.connect() as conn:
                r = conn.execute("SELECT * FROM analysis_requests WHERE id = ?", (rid,)).fetchone()
            if r is None:
                return self.redirect("/analysis?e=" + urllib.parse.quote("That request no longer exists."))
            if not gating.has_analysis(r["code"]):
                return self.redirect("/analysis?q=%s&e=%s" % (r["code"], urllib.parse.quote(
                    "Upload %s's analysis first; uploading it unlocks this request by itself." % r["code"])))
            a = self.admin()
            gating.fulfil(rid, a["email"] if a is not None else "admin")
            return self.redirect("/analysis?ok=" + urllib.parse.quote("Unlocked for the client. Their bell says it's ready."))
        if path == "/selections/status":
            return self.post_selection_status_admin()
        if path == "/settings/fx":
            return self.post_settings_fx()
        if path == "/settings/domain-kam":
            return self.post_domain_kam()
        if path == "/planner/apply":
            return self.post_planner_apply()
        if path == "/calculator/save":
            return self.post_calculator_save()
        if path == "/calculator/results":
            return self.post_calculator_results()
        if path == "/planner/library":
            return self.post_planner_library()
        if path == "/settings/save":
            return self.post_settings()
        if path == "/settings/token":
            return self.post_settings_token()
        if path == "/roster/delete":
            return self.post_roster_delete()
        if path == "/roster/bulk":
            return self.post_roster_bulk()
        if path == "/roster/merge":
            return self.post_roster_merge()
        if path == "/roster/quality/run":
            return self.post_roster_quality_run()
        if path == "/roster/quality/decide":
            return self.post_roster_quality_decide()
        if path == "/roster/import":
            return self.post_roster_import()
        if path == "/roster/photos":
            return self.post_roster_photos()
        if path == "/tiers/save":
            return self.post_tier_save()
        if path == "/tiers/delete":
            return self.post_tier_delete()
        if path == "/requests/handled":
            return self.post_request_handled()
        if path in ("/licences/save", "/licences/scan"):
            import licence
            if path.endswith("scan"):
                res = licence.scan(db.setting("licence_confirmed_codes", None))
                return self.redirect("/licences?ok=" + urllib.parse.quote("%d claims from %d creators." % (res["claims"], res["creators"])))
            f = self.form_body()
            who = self.admin()
            licence.update((f.get("code") or "").strip(), f.get("country"), f.get("status"), f.get("number"),
                           f.get("expires_on"), f.get("note"), (who["email"] if who and "email" in who.keys() else "admin"))
            return self.redirect("/licences?status=claimed")
        if path == "/password":
            return self.post_password()
        return self.send(404, views.simple("Not found", "That action does not exist."))

    # ---------------------------------------------------------- history --

    def tracked_post(self, path, spec):
        """Run an admin action with a snapshot before and after, so it can be
        undone from the History page. `spec` is (entity, form field holding
        its key or None, verb)."""
        entity, field, verb = spec
        f = self.form_body()
        key = (f.get(field) or "").strip() if field else ("*" if entity in ("roster", "tiers", "settings") else "")
        if entity == "creator" and key:
            key = key.upper()
        new_keys = None
        if not key:                        # a create: learn its key afterwards
            new_keys = KEYSETS[entity]()
        creators_before = KEYSETS["creator"]() if path == "/campaigns/save" else None
        self._held = []
        named_before = describe(entity, key, verb) if key else None   # a delete loses the name
        try:
            with history.tracked(entity, key or None, "") as t:
                out = self.admin_post(path)
                if new_keys is not None:
                    fresh = sorted(KEYSETS[entity]() - new_keys)
                    t["key"] = fresh[0] if len(fresh) == 1 else None
                after = describe(entity, t["key"], verb)
                t["label"] = named_before if (named_before and len(named_before) > len(after)) else after
            if creators_before is not None:   # creators a campaign save added to the roster
                for code in sorted(KEYSETS["creator"]() - creators_before):
                    history.record("created", "creator", code, describe("creator", code, "Added from a campaign"),
                                   None, history.snapshot("creator", code))
        finally:
            held, self._held = self._held, None
            extra = self.undo_cookie()                 # recorded only now, after the block
            for code, body, ctype, headers in held:
                if extra and 300 <= code < 400:
                    headers, extra = list(headers or []) + extra, []
                self.send(code, body, ctype, headers)
        return out

    def post_selection_rename(self, who):
        """Rename a selection from the admin (portal item 173): the selections list, the Clients hub and
        the selection's own page. Inline edits post with ``X-HV-Rename: 1`` and get JSON back; a plain
        form gets a redirect to ``back``. A key account manager reaches here only for her own clients
        (kam_scope._POST_SELECTION); History records the change, so it can be undone."""
        import selrename
        f = self.form_body()
        js = self.headers.get("X-HV-Rename") == "1"
        sid = (f.get("id") or "").strip()
        sel = db.selection(int(sid)) if sid.isdigit() else None
        back = f.get("back") or ""
        if not back.startswith("/") or back.startswith("//"):
            back = "/selections"
        err = None
        if sel is None:
            err = "missing"
        elif sel["code_id"] is not None and not self.admin_like_for(sel["code_id"], sel["id"]):
            err = "forbidden"
        if err is None:
            row, err = selrename.apply(sel, f.get("name"), allow_deleted=True)
        if js:
            if err:
                return self.send_json(403 if err == "forbidden" else 404 if err == "missing" else 400,
                                      {"ok": False, "reason": err, "message": selrename.MESSAGES[err]})
            return self.send_json(200, {"ok": True, "id": row["id"], "name": row["name"]})
        sep = "&" if "?" in back else "?"
        if err:
            return self.redirect(back + sep + "e=" + urllib.parse.quote(selrename.MESSAGES[err]))
        return self.redirect(back + sep + "ok=" + urllib.parse.quote("Renamed to %s." % row["name"]))

    def post_campaign_status(self):
        """Go live / take offline from the campaigns list."""
        f = self.form_body()
        cid, to = (f.get("id") or "").strip(), (f.get("status") or "").strip()
        k = db.campaign(int(cid)) if cid.isdigit() else None
        if k is None or to not in db.CAMPAIGN_STATUSES:
            return self.redirect("/campaigns")
        if to == "live":
            missing = [what for what, ok in (("first and last day", k["starts_at"] and k["ends_at"]),
                                             ("the client's access code", k["code_id"]))
                       if not ok]
            if missing:
                return self.redirect("/campaigns?e=" + urllib.parse.quote(
                    "%s can't go live yet — set %s on its Setup tab." % (k["name"], " and ".join(missing))))
        db.save_campaign(k["id"], status=to)
        word = {"live": "is live — the client sees its report on the catalogue",
                "draft": "is offline — the client no longer sees it", "ended": "has ended"}[to]
        return self.redirect("/campaigns?ok=" + urllib.parse.quote("%s %s." % (k["name"], word)))

    def post_history_undo(self):
        f = self.form_body()
        hid = (f.get("id") or "").strip()
        ids = [int(x) for x in (f.get("ids") or "").split(",") if x.strip().isdigit()]
        if ids:                                   # the Undo toast: undo the whole action, newest first
            done = [history.undo(i) for i in sorted(ids, reverse=True)]
            ok = all(d[0] for d in done)
            msg = done[0][1] if len(done) == 1 else ("Undone." if ok else "Some of it could not be undone; see History.")
            back = f.get("back") or "/"
            if not back.startswith("/") or back.startswith("//") or "\\" in back:
                back = "/"
            if BASE and back.startswith(BASE + "/"):
                back = back[len(BASE):]
            history.start_request()
            return self.redirect(back + ("&" if "?" in back else "?") + ("ok=" if ok else "e=") + urllib.parse.quote(msg))
        ok, msg = history.undo(int(hid)) if hid.isdigit() else (False, "Nothing to undo.")
        back = "/history" + ("?kind=" + urllib.parse.quote(f["kind"]) if f.get("kind") else "")
        sep = "&" if "?" in back else "?"
        return self.redirect(back + sep + ("ok=" if ok else "e=") + urllib.parse.quote(msg))

    # ------------------------------------------------------- admin actions --

    def post_login(self):
        form = self.form_body()
        email = (form.get("email") or "").strip().lower()
        # The account key includes the source address: otherwise anyone could lock the real admin out
        # by typing five wrong passwords from anywhere.
        ip_key, em_key = f"login:ip:{self.client_ip()}", f"login:em:{self.client_ip()}:{email[:80]}"
        # 8 failures per address and 5 per account in 15 minutes, then a lockout.
        # Counted on failure only, so a real admin who types it right is never slowed.
        for key, limit in ((ip_key, 8), (em_key, 5)):
            if not guard.limiter.allow(key, limit, 900):
                return self.too_many(guard.limiter.retry_after(key, limit, 900))
        row = db.admin_by_email(email)
        ok = row and auth.verify_password(form.get("password") or "", row["password_hash"])
        # Same delay either way: a fast "no" tells an attacker the email is wrong.
        time.sleep(0.4)
        if ok and row["disabled_at"]:
            ok = False
        if not ok:
            guard.limiter.hit(ip_key)
            guard.limiter.hit(em_key)
            db.log("admin_fail", ip=self.client_ip(), user_agent=self.headers.get("User-Agent"),
                   detail=email[:80])
            team.log("login_fail", email[:80], "", self.client_ip())
            return self.redirect("/login?e=1")
        guard.limiter.reset(em_key)
        if row["totp_on"] or team.must_use_2fa(row):
            # Password is right; now the code from their phone (or, the first time, setting it up).
            pend = auth.sign("2fa:%d:%d" % (row["id"], db.now() + 300), SECRET)
            return self.redirect("/login/2fa", [("Set-Cookie", "hv_2fa=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=300%s" % (pend, self.secure_flag()))])
        return self.start_session(row)

    def post_login_email(self):
        """Step one of the email sign-in. The answer is the same whether or not the address has access."""
        email = (self.form_body().get("email") or "").strip().lower()[:120]
        ip = self.client_ip()
        for key, limit in ((f"alogin:ip:{ip}", 12), (f"alogin:em:{email}", 6)):
            if not guard.limiter.allow(key, limit, 3600):
                return self.too_many(guard.limiter.retry_after(key, limit, 3600))
            guard.limiter.hit(key)
        row = db.admin_by_email(email) if "@" in email else None
        if row is not None and not row["disabled_at"] and mailer.configured():
            code, wait = portal.new_otp(email, ip)
            if code:
                try:
                    subject, text, html = mailer.otp_message(code, portal.OTP_MINUTES, to=email)
                    mailer.send(email, subject.replace("HELVi Connect", "HELVi Connect admin"), text, html)
                    team.log("login_code", email, "", ip)
                except mailer.MailError:
                    db.log("otp_mail_fail", None, ip, self.headers.get("User-Agent"), "admin")
        elif row is None or row["disabled_at"]:
            time.sleep(0.4)
        return self.redirect("/login/email?email=" + urllib.parse.quote(email))

    def post_login_email_verify(self):
        f = self.form_body()
        email = (f.get("email") or "").strip().lower()[:120]
        ip = self.client_ip()
        for key, limit in ((f"alogin:v:ip:{ip}", 20), (f"alogin:v:em:{email}", 8)):
            if not guard.limiter.allow(key, limit, 900):
                return self.too_many(guard.limiter.retry_after(key, limit, 900))
        row = db.admin_by_email(email) if "@" in email else None
        ok = False
        if row is not None and not row["disabled_at"]:
            ok, _why = portal.check_otp(email, f.get("code"))
        if not ok:
            guard.limiter.hit(f"alogin:v:ip:{ip}")
            guard.limiter.hit(f"alogin:v:em:{email}")
            team.log("login_fail", email[:80], "email code", ip)
            return self.redirect("/login/email?e=1&email=" + urllib.parse.quote(email))
        if row["totp_on"] or team.must_use_2fa(row):
            pend = auth.sign("2fa:%d:%d" % (row["id"], db.now() + 300), SECRET)
            return self.redirect("/login/2fa", [("Set-Cookie", "hv_2fa=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=300%s" % (pend, self.secure_flag()))])
        return self.start_session(row)

    def start_session(self, row, extra_cookies=(), to="/"):
        db.touch_admin_login(row["id"])
        token = db.create_session(row["id"], ADMIN_TTL)
        with db.connect() as conn:
            conn.execute("UPDATE sessions SET last_seen = ? WHERE token = ?", (db.now(), token))
        team.log("login", row["email"], "", self.client_ip())
        cookie = (f"{ADMIN_COOKIE}={auth.sign(token, SECRET)}; Path=/; HttpOnly; "
                  f"SameSite=Lax; Max-Age={ADMIN_TTL}{self.secure_flag()}")
        return self.redirect(to or "/", [("Set-Cookie", cookie)] + list(extra_cookies))

    def chat_admin_email(self, cid):
        """The email of the HelloVoice owner or admin behind this portal sign-in, else None. Only a real admin
        (never a key account manager, never someone viewing as a client) gets the assistant's admin hands."""
        if cid is None or self.kam_clients() is not None or not self.staff_viewer(cid):
            return None
        u = portal.user_for_code(cid)
        a = db.admin_by_email(u["email"]) if u is not None and u["email"] else None
        if a is None or a["disabled_at"] or team.role_of(a) not in ("owner", "admin"):
            return None
        return a["email"]

    def loopback_admin_cookie(self, email):
        """A short admin session for the assistant's own call back into this server, for an admin who is
        confirming from the portal. Returns (Cookie header, token to drop afterwards), or (None, None) when
        two-step sign-in is on and they have no admin session open: they sign in to the admin once instead."""
        if self.admin() is not None and self.headers.get("Cookie"):
            return self.headers.get("Cookie"), None
        row = db.admin_by_email(email)
        if row is None or row["disabled_at"] or row["totp_on"] or team.must_use_2fa(row):
            return None, None
        token = db.create_session(row["id"], 300)
        return "%s=%s" % (ADMIN_COOKIE, auth.sign(token, SECRET)), token

    def pending_2fa(self):
        raw = auth.unsign(self.cookies().get("hv_2fa", ""), SECRET)
        if not raw or not raw.startswith("2fa:"):
            return None
        _, aid, exp = raw.split(":")
        if not exp.isdigit() or int(exp) < db.now():
            return None
        row = team.admin_by_id(int(aid))
        return row if row is not None and not row["disabled_at"] else None

    def post_login_2fa(self):
        row = self.pending_2fa()
        if row is None:
            return self.redirect("/login")
        key = "2fa:%d" % row["id"]
        if not guard.limiter.allow(key, 6, 300):
            return self.too_many(guard.limiter.retry_after(key, 6, 300))
        step = team.totp_matches(row["totp_secret"], self.form_body().get("code"), row["totp_last"])
        if step is None:
            guard.limiter.hit(key)
            team.log("2fa_fail", row["email"], "", self.client_ip())
            return self.redirect("/login/2fa?e=1")
        if not row["totp_on"]:
            team.set_totp(row["id"], row["totp_secret"], True)
            team.log("2fa_on", row["email"], "at sign-in", self.client_ip())
        team.use_totp_step(row["id"], step)
        return self.start_session(row, [("Set-Cookie", "hv_2fa=; Path=/; Max-Age=0")])

    def post_reauth(self, who):
        f = self.form_body()
        nxt = f.get("next") or "/"
        nxt = nxt if nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt else "/"
        key = "reauth:%d" % who["admin_id"]
        if not guard.limiter.allow(key, 5, 600):
            return self.too_many(guard.limiter.retry_after(key, 5, 600))
        a = team.admin_by_id(who["admin_id"])
        if f.get("send_code"):
            code, _w = portal.new_otp(a["email"], self.client_ip())
            if code and mailer.configured():
                try:
                    subject, text, html = mailer.otp_message(code, portal.OTP_MINUTES, to=a["email"])
                    mailer.send(a["email"], subject, text, html)
                except mailer.MailError:
                    pass
            return self.redirect("/reauth?mailed=1&next=" + urllib.parse.quote(nxt))
        if (f.get("mailcode") or "").strip():
            ok, _why = portal.check_otp(a["email"].strip().lower(), f.get("mailcode"))
        else:
            ok = auth.verify_password(f.get("password") or "", a["password_hash"])
        step = None
        if ok and a["totp_on"]:
            step = team.totp_matches(a["totp_secret"], f.get("code"), a["totp_last"])
            ok = step is not None
        if not ok:
            guard.limiter.hit(key)
            team.log("reauth_fail", who["email"], "", self.client_ip())
            return self.redirect("/reauth?e=1&next=" + urllib.parse.quote(nxt))
        if step is not None:
            team.use_totp_step(a["id"], step)
        team.mark_reauth(self._admin_token)
        return self.redirect(nxt)

    def post_team(self, path, who):
        f = self.form_body()
        me, ip = who["email"], self.client_ip()

        def back(msg, ok=True, extra=""):
            return self.redirect("/team?" + ("ok=" if ok else "e=") + urllib.parse.quote(msg) + extra)
        try:
            if path == "/account/2fa/start":
                with db.connect() as conn:
                    conn.execute("UPDATE admins SET totp_secret = ?, totp_on = 0 WHERE id = ?", (team.new_secret(), who["admin_id"]))
                return self.redirect("/team?setup=1")
            if path == "/account/2fa/enable":
                a = team.admin_by_id(who["admin_id"])
                step = team.totp_matches(a["totp_secret"], f.get("code"), a["totp_last"])
                if step is None:
                    return self.redirect("/team?setup=1&f=code&e=" + urllib.parse.quote("That code is not right. Try the newest one."))
                team.set_totp(a["id"], a["totp_secret"], True)
                team.use_totp_step(a["id"], step)
                team.log("2fa_on", me, "", ip)
                return back("Two-step sign-in is on.")
            if path == "/account/2fa/disable":
                if team.must_use_2fa(who):
                    return back("Your role requires two-step sign-in.", False)
                team.set_totp(who["admin_id"], None, False)
                team.log("2fa_off", me, "", ip)
                return back("Two-step sign-in is off.")
            if path == "/team/policy":
                roles = [r for r in urllib.parse.parse_qs(self.body().decode()).get("req", []) if r in team.ROLES]
                db.set_setting("require_2fa_roles", roles)
                try:
                    db.set_setting("admin_idle_minutes", max(5, min(1440, int(f.get("idle") or 120))))
                except ValueError:
                    pass
                team.log("policy", me, "2-step for %s; idle %s min" % (",".join(roles) or "nobody", f.get("idle")), ip)
                return back("Sign-in rules saved.")
            aid = int(f.get("id") or 0)
            target = team.admin_by_id(aid) if aid else None
            if path == "/team/invite":
                team.invite(f.get("email"), f.get("name"), f.get("role"))
                team.log("invite", me, "%s as %s" % (f.get("email"), f.get("role")), ip)
                note = ""
                if mailer.configured():
                    try:
                        site = "https://influencer-catalogue.hellovoice.co.uk" + BASE + "/login"
                        mailer.send(f.get("email").strip().lower(), "You now have HELVi Connect admin access",
                                    "You have been given %s access to HELVi Connect admin.\n\nSign in with your work email at %s. "
                                    "We email you a 6-digit code, so there is no password to remember.\n\nHELVi Connect · Powered by HelloVoice"
                                    % (team.ROLE_LABEL.get(f.get("role"), f.get("role")), site))
                    except mailer.MailError:
                        note = " The invitation email could not be sent; tell them to sign in at the admin page."
                return self.redirect("/team?ok=" + urllib.parse.quote("Added. They sign in with an email code." + note))
            if target is None:
                return back("No such person.", False)
            if path == "/team/role":
                team.set_role(aid, f.get("role"))
                team.end_sessions(aid)
                team.log("role", me, "%s -> %s" % (target["email"], f.get("role")), ip)
                return back("%s is now %s." % (target["email"], team.ROLE_LABEL.get(f.get("role"), f.get("role"))))
            if path in ("/team/disable", "/team/enable"):
                team.set_disabled(aid, path.endswith("disable"))
                team.log(path.rsplit("/", 1)[1], me, target["email"], ip)
                return back("Access removed." if path.endswith("disable") else "Access restored.")
            if path == "/team/signout":
                team.end_sessions(aid)
                team.log("signout", me, target["email"], ip)
                return back("%s is signed out everywhere." % target["email"])
            if path == "/team/reinvite":
                if mailer.configured():
                    try:
                        site = "https://influencer-catalogue.hellovoice.co.uk" + BASE + "/login"
                        mailer.send(target["email"], "You have HELVi Connect admin access",
                                    "You have %s access to HELVi Connect admin.\n\nSign in with your work email at %s. "
                                    "We email you a 6-digit code, so there is no password to remember.\n\nHELVi Connect · Powered by HelloVoice"
                                    % (team.ROLE_LABEL.get(team.role_of(target), ""), site))
                    except mailer.MailError:
                        return back("The email could not be sent. Try again shortly.", False)
                team.log("reinvite", me, target["email"], ip)
                return back("Invite sent again to %s." % target["email"])
            if path == "/team/reset2fa":
                team.set_totp(aid, None, False)
                team.end_sessions(aid)
                team.log("2fa_reset", me, target["email"], ip)
                return back("Two-step sign-in reset for %s." % target["email"])
        except ValueError as exc:
            return back(str(exc), False)
        return back("Unknown action.", False)

    def post_password(self):
        who = self.admin()
        form = self.form_body()
        new = form.get("new") or ""
        row = db.admin_by_email(who["email"])
        if not auth.verify_password(form.get("current") or "", row["password_hash"]):
            return self.redirect("/?f=current&e=" + urllib.parse.quote("That is not your current password.") + "#account")
        problems = auth.password_problems(new)
        if problems:
            return self.redirect("/?f=new&e=" + urllib.parse.quote(" ".join(problems)) + "#account")
        db.set_admin_password(row["id"], auth.hash_password(new))
        team.log("password", who["email"], "", self.client_ip())
        return self.redirect("/?ok=" + urllib.parse.quote("Your password is changed."))

    def post_code_new(self):
        form = self.form_body()
        label = (form.get("label") or "").strip() or "Unnamed"
        days = form.get("days", "").strip()
        max_uses = form.get("max_uses", "").strip()
        max_devices = form.get("max_devices", "").strip()
        if days.isdigit() and int(days) > 3650:
            return self.redirect("/codes?e=" + urllib.parse.quote(
                "Expiry can be at most 3650 days (10 years). Leave it empty for a code "
                "that never expires."))
        expires = db.now() + int(days) * 86400 if days.isdigit() and int(days) > 0 else None
        # A passcode typed by the admin ("Alpha Plus122") or, left blank, one
        # generated. Typed ones are matched ignoring case, spaces and dashes.
        code = (form.get("custom") or "").strip()
        if code:
            problem = auth.custom_code_problem(code)
            if problem:
                return self.redirect("/codes?e=" + urllib.parse.quote(problem))
            if db.code_by_hash(auth.hash_code(code)):
                return self.redirect("/codes?e=" + urllib.parse.quote(
                    "That passcode is already in use. Choose another."))
        else:
            code = auth.generate_code()
        new_id = db.create_code(auth.hash_code(code), auth.code_hint(code), label, expires,
                                int(max_uses) if max_uses.isdigit() and int(max_uses) > 0 else None,
                                code_plain=code,
                                max_devices=int(max_devices) if max_devices.isdigit()
                                and int(max_devices) > 0 else None)
        # The AI allowance for this link. Left empty it falls back to the guest default.
        credits = form.get("credits", "").strip()
        if credits.isdigit():
            portal.grant(new_id, int(credits), "Allowance at creation", actor="admin")
        return self.redirect("/codes?new=" + urllib.parse.quote(code))

    def post_code_passcode(self):
        """Change the passcode a client types. One code row, so the Access codes
        page and the selection page always show the same one."""
        f = self.form_body()
        cid = (f.get("id") or "").strip()
        row = db.get_code(int(cid)) if cid.isdigit() else None
        back = (f.get("back") or "/codes").strip()
        if not back.startswith("/") or back.startswith("//"):
            back = "/codes"
        sep = "&" if "?" in back.split("#")[0] else "?"
        def go(kind, msg):
            base, _, frag = back.partition("#")
            return self.redirect(base + sep + kind + "=" + urllib.parse.quote(msg) + ("#" + frag if frag else ""))
        if row is None:
            return self.redirect("/codes")
        code = (f.get("passcode") or "").strip()
        problem = auth.custom_code_problem(code)
        if problem:
            return go("e", problem)
        other = db.code_by_hash(auth.hash_code(code))
        if other is not None and other["id"] != row["id"]:
            return go("e", "That passcode is already in use. Choose another.")
        db.set_code_passcode(row["id"], code, auth.hash_code(code), auth.code_hint(code))
        return go("ok", "Passcode for " + row["label"] + " changed. Tell the client the new one.")

    def post_code_rename(self):
        """Rename the client a code is issued to. With `cascade`, the selections
        and campaigns it opens show the new name too; each is its own History
        entry, so any one can be undone."""
        f = self.form_body()
        cid = (f.get("id") or "").strip()
        row = db.get_code(int(cid)) if cid.isdigit() else None
        if row is None or row["label"] == db.ADMIN_LABEL:
            return self.redirect("/codes")
        label = " ".join((f.get("label") or "").split())[:80]
        back = "#code-" + str(row["id"])
        if not label:
            return self.redirect("/codes?e=" + urllib.parse.quote("The client name cannot be empty.") + back)
        if label == db.ADMIN_LABEL:
            return self.redirect("/codes?e=" + urllib.parse.quote("That name is reserved. Choose another.") + back)
        old = row["label"]
        if label != old:
            with history.tracked("code", str(row["id"]), "Renamed client " + old + " to " + label):
                db.rename_code(row["id"], label)
        n_sel = n_camp = 0
        if f.get("cascade") == "1":
            sel_ids, camp_ids = db.code_attached(row["id"])
            for sid in sel_ids:
                sel = db.selection(sid)
                if sel is None or ((sel["client_name"] if "client_name" in sel.keys() else None) or label) == label:
                    continue
                with history.tracked("selection", str(sid), describe("selection", sid, "Client name to " + label + " on")):
                    db.set_selection_client(sid, sel["code_id"], label)
                n_sel += 1
            for kid in camp_ids:
                k = db.campaign(kid)
                if k is None or (k["client"] or "") == label:
                    continue
                with history.tracked("campaign", str(kid), describe("campaign", kid, "Client name to " + label + " on")):
                    db.set_campaign_client(kid, label)
                n_camp += 1
        also = [("%d selection%s" % (n_sel, "" if n_sel == 1 else "s")) if n_sel else "",
                ("%d campaign%s" % (n_camp, "" if n_camp == 1 else "s")) if n_camp else ""]
        also = " and ".join(a for a in also if a)
        msg = ("Renamed " + old + " to " + label if label != old else "Name unchanged") + (
            "; also updated " + also + "." if also else ".")
        return self.redirect("/codes?ok=" + urllib.parse.quote(msg) + back)

    def post_code_limits(self):
        """Change a code's device limit, use limit and expiry. Empty = none."""
        f = self.form_body()
        cid = (f.get("id") or "").strip()
        row = db.get_code(int(cid)) if cid.isdigit() else None
        if row is None:
            return self.redirect("/codes")

        def limit(key):
            v = (f.get(key) or "").strip()
            return int(v) if v.isdigit() and int(v) > 0 else None

        # A date from the calendar, inclusive: the code works to the end of it.
        day = (f.get("expires") or "").strip()
        start = db.day_bounds(day, None) if day else None
        expires = start + 86400 - 1 if start is not None else None
        if day and start is None:
            return self.redirect("/codes?e=" + urllib.parse.quote("That expiry date is not valid."))
        db.update_code_limits(row["id"], limit("max_devices"), limit("max_uses"), expires)
        return self.redirect("/codes?ok=" + urllib.parse.quote(
            "Saved the limits for " + row["label"] + ".") + "#code-" + str(row["id"]))

    def post_device_remove(self):
        """Take a device off a code: it loses access at its next request and
        its slot is free for another."""
        f = self.form_body()
        did, cid = (f.get("id") or "").strip(), (f.get("code") or "").strip()
        if did.isdigit():
            db.remove_device(int(did))
        return self.redirect("/codes?ok=" + urllib.parse.quote("Device removed.")
                             + ("#code-" + cid if cid.isdigit() else ""))

    def post_apis(self, path):
        f = self.form_body()
        who_row = self.admin()
        who = who_row["email"] if who_row is not None and "email" in who_row.keys() else "admin"
        jid = int(f["id"]) if (f.get("id") or "").isdigit() else None
        q = urllib.parse.quote
        try:
            if path == "/apis/pause":
                apify.set_paused(not apify.paused())
                apify.audit(who, "Paused Apify" if apify.paused() else "Resumed Apify")
                return self.redirect("/apis?tab=apify&ok=" + q("Apify is paused." if apify.paused() else "Apify resumed."))
            if path == "/apis/run/abort" and jid:
                ok, msg = apify.abort_run(jid)
                apify.audit(who, "Stopped run %d" % jid, msg)
                return self.redirect("/apis?tab=apify&" + ("ok=" if ok else "e=") + q(msg))
            if path == "/apis/run/retry" and jid:
                ok, msg = apify.retry_run(jid)
                apify.audit(who, "Retried run %d" % jid, msg)
                return self.redirect("/apis?tab=apify&" + ("ok=" if ok else "e=") + q(msg))
            if path == "/apis/job/clone" and jid:
                new = apify.clone_job(jid)
                apify.audit(who, "Copied job %d" % jid, "new job %s" % new)
                return self.redirect("/apis?tab=apify&ok=" + q("Job copied. The copy is set to run manually."))
            if path == "/apis/job/estimate" and jid:
                n, est = apify.estimate_job(jid)
                return self.redirect("/apis?tab=apify&ok=" + q("%d creators, about $%.2f if run now." % (n, est)))
            if path == "/apis/token":
                apify.save_token(f.get("token"))
                apify.audit(who, "Saved Apify token")
                info = apify.test_connection()
                return self.redirect("/apis?tab=apify&ok=" + q("Connected as %s." % (info.get("username") or "your account")))
            if path == "/apis/token/clear":
                apify.clear_token()
                apify.audit(who, "Removed Apify token")
                return self.redirect("/apis?tab=apify&ok=" + q("Token removed."))
            if path == "/apis/test":
                try:
                    i = apify.test_connection()
                except apify.ApifyError as ex:
                    apify.record_test(False, str(ex))
                    raise
                bits = [i.get("username") or "connected", i.get("plan") or ""]
                if i.get("used") is not None and i.get("cap") is not None:
                    bits.append("$%.2f of $%.2f used this month" % (i["used"], i["cap"]))
                apify.record_test(True, ", ".join(b for b in bits if b))
                return self.redirect("/apis?tab=apify&ok=" + q("Connected: " + ", ".join(b for b in bits if b)))
            if path == "/apis/budget":
                for key, field in (("apify_budget_usd", "budget"), ("apify_run_cap_usd", "run_cap")):
                    try:
                        v = float(f.get(field, ""))
                    except ValueError:
                        raise apify.ApifyError("Budget and per-run limit must be numbers.")
                    if not 0 < v <= 1000:
                        raise apify.ApifyError("Budget and per-run limit must be between 0 and 1000.")
                    db.set_setting(key, v)
                apify.audit(who, "Changed spend limits", "budget %s, per run %s" % (f.get("budget"), f.get("run_cap")))
                return self.redirect("/apis?tab=apify&ok=" + q("Limits saved."))
            if path == "/apis/pack":
                plats = [p for p in ("Instagram", "TikTok") if f.get("plat_" + p.lower())]
                mh = int(f["max_handles"]) if (f.get("max_handles") or "").isdigit() else 20
                one = (f.get("one_creator") or "").strip().upper()
                if one:
                    f["source"], f["max_handles"] = "creator:" + one, "1"
                ok, msg = apify.run_pack(plats, f.get("source") or "sample20", max(1, min(mh, apify.HARD_MAX_HANDLES)),
                                         bool(f.get("audience")), bool(f.get("audit")),
                                         f.get("schedule") if f.get("schedule") in ("manual", "daily", "weekly") else "manual",
                                         f.get("at_time") or "03:00", int(f["weekday"]) if (f.get("weekday") or "").isdigit() else 0)
                apify.audit(who, "Collect everything", msg[:200])
                return self.redirect("/apis?tab=apify&" + ("ok=" if ok else "e=") + q(msg))
            if path == "/apis/job/save":
                apify.save_job(f)
                apify.audit(who, "Saved job", f.get("name") or "")
                return self.redirect("/apis?tab=apify&ok=" + q("Job saved."))
            if path == "/apis/job/delete" and jid:
                apify.delete_job(jid)
                apify.audit(who, "Deleted job %d" % jid)
                return self.redirect("/apis?tab=apify&ok=" + q("Job deleted."))
            if path == "/apis/job/toggle" and jid:
                apify.toggle_job(jid)
                apify.audit(who, "Paused or resumed job %d" % jid)
                return self.redirect("/apis?tab=apify")
            if path == "/apis/job/run" and jid:
                ok, msg = apify.start_job(jid)
                apify.audit(who, "Ran job %d" % jid, msg)
                return self.redirect("/apis?tab=apify&" + ("ok=" if ok else "e=") + q(msg))
            if path == "/apis/refresh":
                n = apify.refresh_all()
                return self.redirect("/apis?tab=apify&ok=" + q("Checked %d running job(s)." % n))
        except apify.ApifyError as ex:
            return self.redirect("/apis?tab=apify&e=" + q(str(ex)))
        return self.redirect("/apis?tab=apify")

    def _code_done(self, cid, done, missing="That client code no longer exists."):
        """A code action answers the way every other page does: ?ok= when it changed, ?e= when it could not."""
        q = urllib.parse.quote
        return self.redirect("/codes?" + ("ok=" if done else "e=") + q(done if done else missing))

    def post_code_archive(self):
        cid = self.form_body().get("id")
        row = db.get_code(int(cid)) if cid and cid.isdigit() else None
        if row is None:
            return self._code_done(cid, "")
        # Revoke first: a live code is never put away by a stray click.
        if not db.code_state(row)[0]:
            db.archive_code(row["id"])
            return self._code_done(cid, "Moved %s to the archive." % row["label"])
        return self._code_done(cid, "", "Revoke %s first; a live code is not archived." % row["label"])

    def post_code_unarchive(self):
        cid = self.form_body().get("id")
        row = db.get_code(int(cid)) if cid and cid.isdigit() else None
        if row is None:
            return self._code_done(cid, "")
        db.unarchive_code(row["id"])
        return self._code_done(cid, "Brought %s back from the archive." % row["label"])

    def post_code_delete(self):
        cid = self.form_body().get("id")
        row = db.get_code(int(cid)) if cid and cid.isdigit() else None
        why = db.delete_code(int(cid)) if row is not None else "That client code no longer exists."
        return self._code_done(cid, "" if why else "Deleted %s." % row["label"], why or "")

    def post_code_restore(self):
        cid = self.form_body().get("id")
        row = db.get_code(int(cid)) if cid and cid.isdigit() else None
        if row is None:
            return self._code_done(cid, "")
        db.restore_code(row["id"])
        return self._code_done(cid, "Restored %s." % row["label"])

    def post_code_revoke(self):
        cid = self.form_body().get("id")
        row = db.get_code(int(cid)) if cid and cid.isdigit() else None
        if row is None:
            return self._code_done(cid, "")
        db.revoke_code(row["id"])
        return self._code_done(cid, "Revoked %s. They can no longer sign in with it." % row["label"])

    def roster_back(self, f, code=None, ok=None, e=None):
        """Where a roster action returns to: the same search, the same page,
        scrolled to the creator it touched. Every early return used to send
        the admin to page 1, to scroll back down to where they were."""
        keep = {}
        if (f.get("q") or "").strip():
            keep["q"] = f["q"].strip()
        for k in ("from", "to"):
            if (f.get(k) or "").strip():
                keep[k] = f[k].strip()
        pg = (f.get("page") or "").strip()
        if pg.isdigit() and pg != "1":
            keep["page"] = pg
        if ok:
            keep["ok"] = ok
        if e:
            keep["e"] = e
        return self.redirect("/roster" + ("?" + urllib.parse.urlencode(keep) if keep else "")
                             + ("#" + code if code else ""))

    def post_roster_save(self):
        f = self.form_body(multi=("city", "interest",
                                  "p_platform", "p_url", "p_followers", "ind_subs", "ind_also"))
        code = (f.get("code") or "").strip().upper()
        tier = (f.get("tier") or "Nano").strip()
        # Adding: the portal assigns the code from what is already in the
        # database. Editing: the code is the identity and never changes.
        if not code:
            for _ in range(5):
                candidate = db.next_code(tier)
                if db.creator(candidate) is None:
                    code = candidate
                    break
            if not code:
                return self.roster_back(f, e="Could not assign a code — try again.")

        existing = db.creator(code)
        # A form opened before someone else saved must not write its older
        # values back over the newer ones. Adding has nothing to compare to.
        seen_at = (f.get("prev_updated") or "").strip()
        if existing is not None and seen_at:
            current = str(existing["updated_at"] or "")
            if current and current != seen_at:
                return self.roster_back(f, code, e=(
                    code + " was changed somewhere else while this form was open. "
                    "Nothing was overwritten — open it again and redo the change."))
        photo = (existing["photo"] if existing else None)
        saved, err = uploads.save_photo(f.get("photo_file"), code, PHOTO_DIR)
        if saved:
            Handler.forget_photo_widths()
        if err:
            return self.roster_back(f, code, e=err)
        if saved:
            photo = saved
        elif (f.get("photo") or "").strip():
            photo = f["photo"].strip()

        followers = (f.get("followers") or "").replace(",", "").strip()

        # This creator's own rate per video. Both empty: the tier's band is
        # used. One figure: a fixed price. Two: a range, in either order.
        def money(key):
            v = "".join(ch for ch in (f.get(key) or "") if ch.isdigit())
            return int(v) if v else None
        p_from, p_to = money("price_from"), money("price_to")
        if p_from is None and p_to is not None:
            p_from = p_to
        if p_to is None and p_from is not None:
            p_to = p_from
        if p_from is not None and p_to < p_from:
            p_from, p_to = p_to, p_from

        # The form posts one p_platform/p_url pair per row, blanks included.
        # A row with a platform but a bare username instead of a link is
        # rescued rather than rejected — that is a very easy thing to type.
        pairs = []
        platforms = list(f.get("p_platform") or [])
        urls = list(f.get("p_url") or [])
        counts = list(f.get("p_followers") or [])
        # A row counts if it names a platform and carries EITHER a link or a
        # follower count. Demanding both threw the count away in silence: pick
        # Snapchat, type 40,000, save without pasting the link, and the number
        # was gone with the save still reporting success.
        for i in range(max(len(urls), len(platforms), len(counts))):
            platform = (platforms[i] if i < len(platforms) else "").strip()
            url = (urls[i] if i < len(urls) else "").strip()
            count = counts[i] if i < len(counts) else None
            if not platform or (not url and not str(count or "").strip()):
                continue
            if url and "/" not in url and "." not in url:
                url = db.profile_url(platform, url) or url
            pairs.append({"platform": platform, "url": url, "followers": count})
        profiles = db.join_profiles(pairs)
        listed = db.split_profiles(profiles)

        db.upsert_creator({
            "code": code,
            # handle and platform are derived from the profiles now. They stay
            # as columns because photos are matched by handle and the whole
            # catalogue filters on platform, and deriving them means the two
            # can never disagree with the links actually shown.
            # The first row that actually has a link: a row may now be a
            # platform and a number while the link is still to come.
            "handle": db.handle_from_url(
                next((p["url"] for p in listed if p.get("url")), "")),
            "platform": db.join_cities([p["platform"] for p in listed]) or "Instagram",
            "profiles": profiles,
            "name": (f.get("name") or "").strip(),
            # The headline figure. Left blank it is the sum across platforms,
            # so a creator on three of them still sorts and bands correctly.
            "followers": (int(followers) if followers.isdigit()
                          else db.total_followers(listed)),
            # Ticked boxes plus anything typed into "add a city". Both go
            # through join_cities, so the separator is decided in one place.
            "city": db.join_cities(
                list(f.get("city") or []) + db.split_cities(f.get("city_new") or "")) or None,
            "nationality": (f.get("nationality") or "").strip() or None,
            "tier": tier,
            # Ticked categories plus anything typed into "add", through the
            # same joiner the cities use so the separator is decided once.
            "interest": db.join_cities(
                list(f.get("interest") or [])
                + db.split_cities(f.get("interest_new") or "")) or None,
            "photo": photo or None,
            "active": 1 if f.get("active") else 0,
            "note": (f.get("note") or "").strip() or None,
            "sort": int(f["sort"]) if (f.get("sort") or "").isdigit() else 0,
            "price_from": p_from,
            "price_to": p_to,
            # Our own star rating of working with them. Internal: it is never
            # part of what a client is sent.
            "rating": (int(f["rating"]) if (f.get("rating") or "").isdigit()
                       and 1 <= int(f["rating"]) <= 5 else None),
        })
        # The Industry section (Control Centre step 3). Only written when the form carried it and something changed,
        # so an older form, or a save that did not touch it, leaves the classification alone.
        if "ind_main" in f and (f.get("ind_main") or "").strip():
            try:
                ind, subs, also, tier = industry.clean(f.get("ind_main").strip(), list(f.get("ind_subs") or []),
                                                       list(f.get("ind_also") or []), f.get("ind_tier") or "Confirmed")
                cur = industry.current(existing) if existing is not None else None
                if cur is None or (cur["industry"], cur["subs"], cur["also"], cur["tier"]) != (ind, subs, also, tier):
                    who = self.admin()
                    with db.connect() as conn:
                        industry.write(conn, code, ind, subs, also, tier, (who["email"] if who else ""), existing)
            except ValueError as exc:
                return self.roster_back(f, code, e=str(exc))
        # Back to the view the edit was made from: same search, same page,
        # scrolled to this creator, with a note saying it saved.
        return self.roster_back(f, code, ok=("Saved " + code + "."))

    # ---- quick edit from the catalogue (Control Centre step 3): team members who may edit creators only --
    def _creator_editor(self):
        who = self.admin()
        if not who or not team.can(who, "POST", "/roster/save") or team.role_of(who) == "kam":
            self.send_json(403, {"ok": False, "reason": "not_allowed", "message": "Only the HelloVoice team can edit creators."}, self.cors())
            return None
        return who

    def _quick_payload(self, row):
        cur = industry.current(row)
        return {"ok": True, "code": row["code"], "name": row["name"] or "", "city": row["city"] or "", "nationality": row["nationality"] or "",
                "handle": row["handle"] or "", "platform": row["platform"] or "", "followers": row["followers"] or 0,
                "active": bool(row["active"]), "photo_url": links.photo(row["photo"]) if row["photo"] else None,
                "industry": cur["industry"] or "", "subs": cur["subs"], "also": cur["also"], "tier": cur["tier"] or "",
                "updated_at": str(row["updated_at"] or ""), "industries": industry.INDUSTRIES, "sub_list": industry.SUBS,
                "admin_url": BASE + "/roster?q=" + urllib.parse.quote(row["code"])}

    def api_admin_creator_get(self, code):
        if not self._creator_editor():
            return
        row = db.creator(code)
        if row is None:
            return self.send_json(404, {"ok": False, "message": "No such creator."}, self.cors())
        return self.send_json(200, self._quick_payload(row), self.cors())

    def api_admin_creator_post(self):
        who = self._creator_editor()
        if not who:
            return
        b = self.json_body() or {}
        code = str(b.get("code") or "").strip().upper()
        row = db.creator(code)
        if row is None:
            return self.send_json(404, {"ok": False, "message": "No such creator."}, self.cors())
        if b.get("prev_updated") and str(row["updated_at"] or "") != str(b.get("prev_updated")):
            return self.send_json(409, {"ok": False, "reason": "changed",
                                        "message": "Someone else changed this creator a moment ago. Close and open it again."}, self.cors())
        name = " ".join(str(b.get("name") or row["name"] or "").split())[:120]
        city = " ".join(str(b.get("city") or "").split())[:120] or None
        active = 1 if b.get("active", bool(row["active"])) else 0
        actor = who["email"]
        try:
            ind = None
            if b.get("industry"):
                ind = industry.clean(b.get("industry"), b.get("subs") or [], b.get("also") if b.get("also") is not None else industry.current(row)["also"], "Confirmed")
            with history.tracked("creator", code, "Quick edit of %s on the catalogue" % code):
                with db.connect() as conn:
                    conn.execute("UPDATE creators SET name = ?, city = ?, active = ?, updated_at = ? WHERE code = ?",
                                 (name or row["name"], city, active, db.now(), code))
                    cur = industry.current(row)
                    if ind and (cur["industry"], cur["subs"], cur["also"], cur["tier"]) != ind:
                        industry.write(conn, code, ind[0], ind[1], ind[2], ind[3], actor, row)
        except ValueError as exc:
            return self.send_json(400, {"ok": False, "message": str(exc)}, self.cors())
        return self.send_json(200, self._quick_payload(db.creator(code)), self.cors())

    def api_admin_creator_photo(self):
        if not self._creator_editor():
            return
        b = self.json_body() or {}
        code = str(b.get("code") or "").strip().upper()
        row = db.creator(code)
        if row is None:
            return self.send_json(404, {"ok": False, "message": "No such creator."}, self.cors())
        raw = str(b.get("data") or "")
        try:
            import base64
            data = base64.b64decode(raw.split(",", 1)[1] if raw.startswith("data:") else raw, validate=False)
        except Exception:
            data = b""
        if not data or len(data) > 8 * 1024 * 1024:
            return self.send_json(400, {"ok": False, "message": "Choose a JPG or PNG under 8 MB."}, self.cors())
        saved, err = uploads.save_photo({"data": data, "filename": "photo.jpg"}, code, PHOTO_DIR)
        if err or not saved:
            return self.send_json(400, {"ok": False, "message": err or "That picture could not be used."}, self.cors())
        with history.tracked("creator", code, "Replaced the photo of %s on the catalogue" % code):
            with db.connect() as conn:
                conn.execute("UPDATE creators SET photo = ?, updated_at = ? WHERE code = ?", (saved, db.now(), code))
        Handler.forget_photo_widths()
        return self.send_json(200, self._quick_payload(db.creator(code)), self.cors())

    def api_board_move(self):
        """Drag-and-drop on the selections-and-campaigns board (owner-approved 2026-10-14). Only the moves an admin
        may make; each goes through the same rules as its button elsewhere, and is recorded in History."""
        who = self.admin()
        if not who or not team.can(who, "POST", "/campaigns/status"):
            return self.send_json(403, {"ok": False, "message": "Only the HelloVoice team can move cards."}, self.cors())
        kam_scope.begin(kam_scope.clients(who))             # a key account manager moves only her own cards
        b = self.json_body() or {}
        kind, to = b.get("kind"), b.get("to")
        try:
            rid = int(b.get("id") or 0)
        except (TypeError, ValueError):
            rid = 0
        no = lambda msg: self.send_json(400, {"ok": False, "message": msg}, self.cors())
        actor = (who["name"] if "name" in who.keys() and who["name"] else who["email"])

        def go_live(k):
            missing = [w for w, ok in (("the first and last day", k["starts_at"] and k["ends_at"]), ("the client's access code", k["code_id"])) if not ok]
            if missing:
                return {"ok": True, "go": BASE + "/campaigns/edit?id=%d&e=%s" % (k["id"], urllib.parse.quote(
                    "Set %s on the Setup tab, then press Go live." % " and ".join(missing)))}
            with history.tracked("campaign", k["id"], "Started %s from the board" % k["name"]):
                db.save_campaign(k["id"], status="live")
            return {"ok": True, "message": "%s is live." % k["name"]}

        if kind == "sel":
            sel = db.selection(rid)
            if sel is None or not kam_scope.allows(kam_scope.selection_code(sel["id"])[1]):
                return no("That selection is not here any more.")
            key = lifecycle.state_of(sel)["key"]
            if to == "requested" and key == "draft":
                if not sel["code_id"]:
                    return no("Assign a client to this selection first.")
                with history.tracked("selection", sel["id"], "Marked %s as quote requested (board)" % sel["name"]):
                    lifecycle.mark_requested(sel, by_name="%s for the client" % actor)
                return self.send_json(200, {"ok": True, "message": "Marked as Quote requested."})
            if to == "approved" and key == "ready":
                with history.tracked("selection", sel["id"], "Approved %s for the client (board)" % sel["name"]):
                    _k, err = lifecycle.approve(sel, None, "%s, for the client" % actor)
                return self.send_json(200, {"ok": True, "message": "Approved. Next: start the campaign."}) if not err else no("Only a ready quote can be approved.")
            if to == "ready" and key in ("draft", "requested"):
                with history.tracked("selection", sel["id"], "Marked the quote ready for %s (board)" % sel["name"]):
                    _k, err = lifecycle.set_ready(sel, b.get("note") or "", "", actor)
                return self.send_json(200, {"ok": True, "message": "Quote ready: the client was told."}) if not err else no("That quote can't be marked ready now.")
            if to == "requested" and key == "ready":
                with history.tracked("selection", sel["id"], "Took the quote back for %s (board)" % sel["name"]):
                    _k, err = lifecycle.withdraw_ready(sel)
                return self.send_json(200, {"ok": True, "message": "Taken back."}) if not err else no("Only a quote that is ready and not yet approved can be taken back.")
            if to == "live" and key == "approved":
                camps = [c for c in lifecycle.state_of(sel)["campaigns"] if c["status"] == "draft"]
                if camps:
                    return self.send_json(200, go_live(db.campaign(camps[0]["id"])))
                return self.send_json(200, {"ok": True, "go": BASE + "/campaigns/setup?selection=%d" % sel["id"]})
            return no("That move is not possible from here.")
        if kind == "camp":
            k = db.campaign(rid)
            if k is None or not kam_scope.allows(kam_scope.campaign_code(k["id"])[1]):
                return no("That campaign is not here any more.")
            if to == "live" and k["status"] in ("draft", "ended"):
                return self.send_json(200, go_live(k))
            if to == "approved" and k["status"] == "live":
                with history.tracked("campaign", k["id"], "Took %s offline from the board" % k["name"]):
                    db.save_campaign(k["id"], status="draft")
                return self.send_json(200, {"ok": True, "message": "%s is offline: the client no longer sees it." % k["name"]})
            if to == "completed" and k["status"] == "live":
                with history.tracked("campaign", k["id"], "Ended %s from the board" % k["name"]):
                    db.save_campaign(k["id"], status="ended")
                return self.send_json(200, {"ok": True, "message": "%s has ended." % k["name"]})
            return no("That move is not possible from here.")
        return no("Unknown card.")

    def post_roster_review(self):
        f = self.form_body(multi=("ind_subs", "ind_also"))
        code = (f.get("code") or "").strip().upper()
        country = f.get("country") if f.get("country") in industry.COUNTRIES else ""
        back = "/roster/review?" + ("country=%s&" % country if country else "")
        who = self.admin()
        actor = (who["name"] if "name" in who.keys() and who["name"] else who["email"]) if who else ""
        do = f.get("do") or "confirm"
        if db.creator(code) is None:
            return self.redirect(back + "e=" + urllib.parse.quote("There is no creator with the code %s." % (code or "(none)")))
        try:
            if do == "skip":
                return self.redirect(back + "after=" + urllib.parse.quote(f.get("after") or ""))
            if do == "unfit":
                industry.hide(code, actor)
                return self.redirect(back + "ok=" + urllib.parse.quote("%s is hidden from clients. Undo it in History." % code))
            industry.set_for(code, f.get("ind_main"), list(f.get("ind_subs") or []), list(f.get("ind_also") or []), "Confirmed", actor)
        except ValueError as exc:
            return self.redirect(back + "e=" + urllib.parse.quote(str(exc)))
        return self.redirect(back + "ok=" + urllib.parse.quote("Saved %s as %s." % (code, f.get("ind_main"))))

    def post_roster_import(self):
        part = self.form_body().get("sheet")
        if not part or not isinstance(part, dict) or not part.get("data"):
            return self.redirect("/roster?e=" + urllib.parse.quote("Choose a file first."))
        try:
            rows, errors, photos = importer.parse(part["data"], part.get("filename", ""))
        except RuntimeError as ex:
            return self.redirect("/roster?e=" + urllib.parse.quote(str(ex)))

        if errors:
            # Nothing is written when anything is wrong: a half-imported roster
            # is harder to recover from than a rejected file.
            summary = " ".join(errors[:4])
            if len(errors) > 4:
                summary += " (+" + str(len(errors) - 4) + " more)"
            return self.redirect("/roster?e=" + urllib.parse.quote(
                "Nothing was imported. " + summary))
        if not rows:
            return self.redirect("/roster?e=" + urllib.parse.quote("No creator rows found."))

        added = updated = attached = 0
        bad_photos = []
        # One transaction for the whole sheet. Parsing already refuses a file
        # if any row is wrong, but the writing was row by row, so a failure
        # partway still left everything before it committed — the half-imported
        # roster that promise exists to prevent. next_code() reads through the
        # same connection, so it sees rows added earlier in this very
        # transaction and cannot hand out a code twice.
        with db.connect() as conn:
            for i, r in enumerate(rows):
                code = r["code"]
                existing = db.creator(code, conn) if code else None
                if existing:
                    updated += 1
                else:
                    if not code:
                        code = db.next_code(r["tier"], conn=conn)
                    added += 1
                # An existing photo survives a re-import; a picture on the sheet
                # replaces it, because putting one there is an explicit act.
                photo = existing["photo"] if (existing and existing["photo"]) else None
                raw = photos.get(r.get("_row"))
                if raw:
                    ok, why = uploads.photo_bytes(raw)
                    if ok:
                        photo = uploads.write_photo(raw, code, PHOTO_DIR)
                        Handler.forget_photo_widths()
                        attached += 1
                    else:
                        bad_photos.append("row " + str(r["_row"]) + " (" + why + ")")

                fields = {k: v for k, v in r.items() if not k.startswith("_")}
                db.upsert_creator(dict(fields, code=code, photo=photo, sort=i), conn)

        msg = str(added) + " added, " + str(updated) + " updated."
        if attached:
            msg += " " + str(attached) + (" photo" if attached == 1 else " photos")
            msg += " taken from the sheet."
        if bad_photos:
            shown = ", ".join(bad_photos[:4])
            if len(bad_photos) > 4:
                shown += " (+" + str(len(bad_photos) - 4) + " more)"
            msg += " Pictures skipped: " + shown + "."
        return self.redirect("/roster?ok=" + urllib.parse.quote(msg))

    def post_roster_photos(self):
        """Attach many photos at once, matched to creators by filename.

        The roster form takes one photo at a time, which is right for fixing a
        single creator and wrong after importing eighty of them. A folder of
        images named for the code or the handle covers both ways people
        actually hold these files.
        """
        parts = self.form_body(multi=("photos",)).get("photos") or []
        parts = [p for p in parts
                 if isinstance(p, dict) and p.get("data") and p.get("filename")]
        if not parts:
            return self.redirect("/roster?e=" + urllib.parse.quote(
                "Choose some image files first."))

        # Three indexes, so a file can be named whichever way it already is.
        # Most people have never seen the codes — the photo they downloaded is
        # called after the person or their handle, so match on those too.
        by_code, by_handle, by_name = {}, {}, {}
        for c in db.list_creators():
            by_code[c["code"].upper()] = c["code"]
            if c["handle"]:
                by_handle.setdefault(c["handle"].lower(), []).append(c["code"])
            if c["name"]:
                by_name.setdefault(squash(c["name"]), []).append(c["code"])

        saved, unmatched, rejected, ambiguous = 0, [], [], []
        for part in parts:
            name = Path(part["filename"]).name
            # "Noha Magdy (1).jpg" is what a second download is called. The
            # suffix is the browser's, not part of anyone's name.
            stem = re.sub(r"\s*\(\d+\)$", "", Path(name).stem.strip())

            code, clash = by_code.get(stem.upper()), False
            for index, key in ((by_handle, stem.lower().lstrip("@")),
                               (by_name, squash(stem))):
                if code:
                    break
                hits = index.get(key, [])
                if len(hits) > 1:
                    # The same handle or name on two creators. Guessing would
                    # put the photo on the wrong card, silently.
                    clash = True
                    break
                if hits:
                    code = hits[0]
            if clash:
                ambiguous.append(name)
                continue
            if not code:
                unmatched.append(name)
                continue

            ok, why = uploads.photo_bytes(part["data"])
            if not ok:
                rejected.append(name + " (" + why + ")")
                continue

            filename = uploads.write_photo(part["data"], code, PHOTO_DIR)
            Handler.forget_photo_widths()
            row = db.creator(code)
            db.upsert_creator(dict(row, photo=filename))
            saved += 1

        def listing(label, items):
            if not items:
                return ""
            shown = ", ".join(items[:5])
            if len(items) > 5:
                shown += " (+" + str(len(items) - 5) + " more)"
            return " " + label + ": " + shown + "."

        msg = str(saved) + (" photo" if saved == 1 else " photos") + " attached."
        msg += listing("No creator matched", unmatched)
        msg += listing("Matched two creators, so skipped", ambiguous)
        msg += listing("Rejected", rejected)

        key = "ok" if saved else "e"
        return self.redirect("/roster?" + key + "=" + urllib.parse.quote(msg))

    def post_roster_bulk(self):
        """Hide, show, re-tier or add to a selection many creators at once. Each creator's change is
        its own History entry, so any one of them can be undone."""
        raw = urllib.parse.parse_qs(self.body().decode())
        codes = list(dict.fromkeys(c.strip().upper() for c in raw.get("codes", []) if c.strip()))[:500]
        action, value = (raw.get("action") or [""])[0], (raw.get("value") or [""])[0].strip()
        back = (raw.get("back") or ["/roster"])[0]
        back = back if back.startswith("/roster") and "\\" not in back else "/roster"
        sep = "&" if "?" in back else "?"
        if not codes:
            return self.redirect(back + sep + "e=" + urllib.parse.quote("Tick at least one creator first."))
        known = {c["code"]: c for c in db.list_creators() if c["code"] in set(codes)}
        if action in ("hide", "show", "tier"):
            if action == "tier" and value not in db.tier_names():
                return self.redirect(back + sep + "f=value&e=" + urllib.parse.quote("Choose a tier."))
            n = 0
            for code, c in known.items():
                row = dict(c)
                if action == "tier":
                    row["tier"] = value
                else:
                    row["active"] = 0 if action == "hide" else 1
                if row == dict(c):
                    continue
                with history.tracked("creator", code, "%s %s" % ({"hide": "Hid", "show": "Showed", "tier": "Moved to " + value}[action], code)):
                    db.upsert_creator(row)
                n += 1
            word = {"hide": "hidden", "show": "shown to clients", "tier": "moved to " + value}[action]
            return self.redirect(back + sep + "ok=" + urllib.parse.quote("%d creator%s %s. Undo any of them from History." % (n, "" if n == 1 else "s", word)))
        if action == "select":
            if value.isdigit() and db.selection(int(value)):
                sel = db.selection(int(value))
                have = json.loads(sel["codes"] or "[]")
                new = have + [c for c in known if c not in have]
                with history.tracked("selection", sel["id"], "Added %d creators to %s" % (len(new) - len(have), sel["name"])):
                    db.save_selection(sel["id"], sel["name"], new, json.loads(sel["prices"] or "{}"), sel["total_from"], sel["total_to"],
                                      platform=sel["platform"])
                return self.redirect("/selections/edit?id=%d&ok=" % sel["id"] + urllib.parse.quote("%d creators added." % (len(new) - len(have))))
            name = value or "New selection"
            with history.tracked("selection", None, "Created selection " + name) as t:
                sid = db.save_selection(None, name[:120], list(known), {}, None, None)
                t["key"] = sid
            return self.redirect("/selections/edit?id=%d&ok=" % sid + urllib.parse.quote("Selection created with %d creators." % len(known)))
        if action == "export":
            return self.redirect("/roster/export?codes=" + urllib.parse.quote(",".join(known)))
        return self.redirect(back + sep + "e=" + urllib.parse.quote("Choose what to do with the ticked creators."))

    def roster_csv(self, only=None):
        """The roster as the import template, already filled in.

        Two jobs at once: it is the list of codes — which nobody memorises and
        the dashboard otherwise only shows a screen at a time — and it is a
        valid import file, so editing a column and uploading it back updates
        those creators instead of duplicating them.
        """
        import csv
        import io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(importer.COLUMNS)
        for c in db.list_creators():
            if only is not None and c["code"] not in only:
                continue
            # Grouped, not keyed: a creator can have two accounts on one
            # platform, and keying by platform would export only the last of
            # them — a round trip that silently loses an account is worse than
            # no export at all.
            found = {}
            for prof in db.split_profiles(c["profiles"]):
                found.setdefault(prof["platform"], []).append(prof)
            pairs = []
            for col in importer.PROFILE_COLUMNS:
                group = found.get(importer.PROFILE_LABELS[col], [])
                pairs.append(", ".join(x["url"] for x in group))
                pairs.append(", ".join(str(x["followers"] or "") for x in group)
                             if any(x["followers"] for x in group) else "")
            w.writerow([
                c["code"], c["name"],
                c["followers"] if c["followers"] is not None else "",
                db.join_cities(db.split_cities(c["city"])),
                c["nationality"] or "", c["tier"],
            ] + pairs + [
                c["interest"] or "",
                c["note"] or "", "yes" if c["active"] else "no",
                "on file" if c["photo"] else "",
                c["platform"], c["handle"] or "",
            ])
        # BOM so Excel opens it as UTF-8 rather than mangling Arabic city names
        return "\ufeff" + buf.getvalue()

    def post_tier_save(self):
        """Add a tier, or edit one that exists. Both go through here because
        they are the same operation with a different starting row."""
        f = self.form_body()
        name = (f.get("name") or "").strip()
        was = (f.get("was") or "").strip()          # set when editing
        code = (f.get("code") or "").strip().upper()[:4]
        reach = (f.get("reach") or "").strip() or None
        lo = (f.get("price_from") or "").strip()
        hi = (f.get("price_to") or "").strip()
        sort = (f.get("sort") or "").strip()

        def bad(msg):
            return self.redirect("/roster?e=" + urllib.parse.quote(msg))

        if not name:
            return bad("A tier needs a name.")
        if not code.isalnum() or not code:
            return bad("The code is the middle of a creator code — letters or "
                       "digits only, like MI.")
        if not lo.isdigit() or not hi.isdigit():
            return bad("Both prices must be whole numbers.")
        lo, hi = int(lo), int(hi)
        if hi < lo:
            # Swapping silently would quote a range backwards on every card.
            return bad("The upper price is below the lower one.")

        if was and was != name:
            if db.get_tier(name):
                return bad("There is already a tier called " + name + ".")
            db.rename_tier(was, name)
        rf = (f.get("reach_from") or "").replace(",", "").strip()
        rt = (f.get("reach_to") or "").replace(",", "").strip()
        db.save_tier(name, code, lo, hi, reach,
                     int(sort) if sort.lstrip("-").isdigit() else 0,
                     int(rf) if rf.isdigit() else None,
                     int(rt) if rt.isdigit() else None,
                     auto=bool(f.get("auto")))
        return self.redirect("/roster?ok=" + urllib.parse.quote(
            "Tier " + name + " saved at " + format(lo, ",") + " – "
            + format(hi, ",") + " SAR."))

    def post_tier_delete(self):
        name = (self.form_body().get("name") or "").strip()
        used = db.delete_tier(name)
        if used:
            return self.redirect("/roster?e=" + urllib.parse.quote(
                str(used) + (" creator is" if used == 1 else " creators are")
                + " still on the " + name + " tier. Move them first."))
        return self.redirect("/roster?ok=" + urllib.parse.quote(
            "Tier " + name + " removed."))

    def post_roster_merge(self):
        """Fold duplicate creators into the one to keep. Their selections,
        campaigns, posts, insights and analysis move across; empty fields on the
        kept creator are filled from the others; the duplicates are deleted.
        Each change is its own entry in History, so each can be undone."""
        f = self.form_body(multi=("drop",))
        keep = (f.get("keep") or "").strip().upper()
        raw = f.get("drop") or []
        drops = [d.strip().upper() for d in ([raw] if isinstance(raw, str) else raw) if d.strip().upper() != keep]
        if not keep or not drops or db.creator(keep) is None:
            return self.redirect("/roster?tab=dupes&e=" + urllib.parse.quote("Pick the creator to keep."))
        done = []
        for d in drops:
            if db.creator(d) is None:
                continue
            self.merge_one(keep, d)
            done.append(d)
        Handler._pairs_cache = (0, None)
        back = (f.get("back") or "").strip()
        back = back if back.startswith("/roster/quality") else "/roster?tab=dupes"
        return self.redirect(back + ("&" if "?" in back else "?") + "ok=" + urllib.parse.quote(
            "Combined %s into %s: every platform, link, analysis, selection and campaign is kept on %s. Undo from History if it was a mistake." % (", ".join(done) or "nothing", keep, keep)))

    # --------------------------------------------- roster quality (items 224-225) --

    _pairs_cache = (0, None)

    def roster_quality(self, query):
        import rosterq, rosterq_views
        tab = query.get("tab") if query.get("tab") in ("open", "kept", "archived", "pairs") else "open"
        reason = query.get("reason") if query.get("reason") in list(rosterq.REASONS) + ["unclear"] else None
        asked = (query.get("page") or "1").strip()
        page_no = int(asked) if asked.isdigit() and int(asked) > 0 else 1
        if tab == "pairs":
            at, groups = Handler._pairs_cache
            if groups is None or time.time() - at > 300:       # 14k rows: once per 5 minutes, not per page view
                known = {c["code"] for g in db.duplicate_groups() for c in g}
                groups = rosterq.dupe_candidates(known=known)
                Handler._pairs_cache = (time.time(), groups)
            return self.send(200, rosterq_views.quality_page(tab, None, groups, {}, 1, None, rosterq.JOB, query.get("ok"), query.get("e")))
        rows = rosterq.queue(None if tab != "open" else reason, status=tab)
        counts = rosterq.counts() if tab == "open" else {}
        counts["total"] = len(rosterq.queue(status="open")) if tab == "open" and reason else len(rows) if tab == "open" else 0
        with db.connect() as conn:
            rosterq.init(conn)
            counts["unclear_unread"] = conn.execute("SELECT COUNT(*) FROM roster_flags WHERE unclear = 1 AND ai_verdict IS NULL "
                                                    "AND status = 'open'").fetchone()[0]
        pages = max(1, -(-len(rows) // rosterq_views.PER))
        return self.send(200, rosterq_views.quality_page(tab, reason, rows, counts, min(page_no, pages),
                                                         db.setting("roster_quality_last"), rosterq.JOB, query.get("ok"), query.get("e")))

    def post_roster_quality_run(self):
        import rosterq
        kind = (self.form_body().get("kind") or "").strip()
        if kind not in ("scan", "ai"):
            return self.redirect("/roster/quality?e=" + urllib.parse.quote("Unknown job."))
        who = self.admin()
        if kind == "ai":
            import gemini
            if not gemini.configured():
                return self.redirect("/roster/quality?e=" + urllib.parse.quote("Gemini is not set up: save its key in Client portal › Settings & keys."))
        if not rosterq.start(kind, (who["email"] if who else "") or ""):
            return self.redirect("/roster/quality?e=" + urllib.parse.quote("A roster-quality job is already running. Refresh in a minute."))
        return self.redirect("/roster/quality?ok=" + urllib.parse.quote(
            "Scan started: about a minute. Refresh to see it." if kind == "scan" else "AI read started in the background: a few minutes. Refresh to see the verdicts."))

    def post_roster_quality_decide(self):
        import rosterq
        f = self.form_body(multi=("codes",))
        raw = f.get("codes") or []
        codes = [c.strip().upper() for c in ([raw] if isinstance(raw, str) else raw) if c.strip()]
        back = (f.get("back") or "").strip()
        back = back if back.startswith("/roster/quality") else "/roster/quality"
        sep = "&" if "?" in back else "?"
        if not codes:
            return self.redirect(back + sep + "e=" + urllib.parse.quote("Tick at least one creator first."))
        who = self.admin()
        name = (who["email"] if who else "") or ""
        if f.get("do") == "archive":
            done, skipped = rosterq.archive(codes, name)
            msg = "%d archived: hidden from the catalogue and every client view. Undo any of them from History." % len(done)
            if skipped:
                msg += " %d skipped: on a selection or campaign." % len(skipped)
            return self.redirect(back + sep + "ok=" + urllib.parse.quote(msg))
        if f.get("do") == "keep":
            n = rosterq.keep(codes, name)
            return self.redirect(back + sep + "ok=" + urllib.parse.quote("%d kept: off this list until new evidence appears." % n))
        return self.redirect(back + sep + "e=" + urllib.parse.quote("Choose Archive or Keep."))

    def merge_one(self, keep, drop):
        label = "Merged duplicate %s into %s" % (drop, keep)
        # selections that list the duplicate
        with db.connect() as conn:
            sels = conn.execute("SELECT id, codes, prices, costs FROM selections").fetchall()
        for sel in sels:
            codes = json.loads(sel["codes"] or "[]")
            if drop not in codes:
                continue
            with history.tracked("selection", sel["id"], label):
                new = []
                for c in codes:
                    c = keep if c == drop else c
                    if c not in new:
                        new.append(c)
                prices, costs = json.loads(sel["prices"] or "{}"), json.loads(sel["costs"] or "{}")
                for dct in (prices, costs):
                    if drop in dct:
                        v = dct.pop(drop)
                        dct.setdefault(keep, v)
                if db.zero_priced(sel["id"]):
                    prices = db.zero_prices(new)
                with db.connect() as conn:
                    conn.execute("UPDATE selections SET codes=?, prices=?, costs=?, updated_at=? WHERE id=?",
                                 (json.dumps(new), json.dumps(prices), json.dumps(costs), db.now(), sel["id"]))
        # campaigns that include the duplicate
        with db.connect() as conn:
            camps = [r[0] for r in conn.execute(
                "SELECT campaign_id FROM campaign_creators WHERE code = ? UNION SELECT campaign_id FROM content WHERE code = ?",
                (drop, drop))]
        for cid in camps:
            with history.tracked("campaign", cid, label):
                with db.connect() as conn:
                    has_keep = conn.execute("SELECT 1 FROM campaign_creators WHERE campaign_id = ? AND code = ?", (cid, keep)).fetchone()
                    if has_keep:
                        drow = conn.execute("SELECT planned, cost FROM campaign_creators WHERE campaign_id = ? AND code = ?", (cid, drop)).fetchone()
                        if drow:
                            conn.execute("UPDATE campaign_creators SET planned = MAX(COALESCE(planned,0), ?), "
                                         "cost = COALESCE(cost, ?) WHERE campaign_id = ? AND code = ?",
                                         (drow["planned"] or 0, drow["cost"], cid, keep))
                            conn.execute("DELETE FROM campaign_creators WHERE campaign_id = ? AND code = ?", (cid, drop))
                        conn.execute("DELETE FROM links WHERE campaign_id = ? AND code = ? AND is_default = 1", (cid, drop))
                    else:
                        conn.execute("UPDATE campaign_creators SET code = ? WHERE campaign_id = ? AND code = ?", (keep, cid, drop))
                    for table in ("content", "insights", "links"):
                        conn.execute("UPDATE %s SET code = ? WHERE campaign_id = ? AND code = ?" % table, (keep, cid, drop))
        # analysis and its pictures
        d_all, k_all = db.analyses(drop), db.analyses(keep)
        # Both are the same person, so both analyses are valid: a platform only the
        # duplicate has moves across, and where both have one the fuller is kept
        # (a full PDF report is never lost to a thin basic copy).
        import profile_pdf as _pp
        moved = {pl: a for pl, a in d_all.items()
                 if pl not in k_all or _pp.completeness(a["data"]) > _pp.completeness(k_all[pl]["data"])}
        if moved:
            import analysis as analysis_mod, shutil
            for pl, a in moved.items():
                db.save_analysis(keep, a["data"], a["source"], platform=pl)
            src, dst = analysis_mod.MEDIA / drop, analysis_mod.MEDIA / keep
            if src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
                for fn in src.iterdir():
                    shutil.copy(str(fn), str(dst / fn.name))
        with db.connect() as conn:
            conn.execute("UPDATE analysis_requests SET code = ? WHERE code = ?", (keep, drop))
        # whatever was not carried over is the weaker copy; the duplicate leaves nothing behind
        db.delete_analysis(drop)
        # fill the kept creator's gaps from the duplicate
        k, d = db.creator(keep), db.creator(drop)
        row = {x: k[x] for x in k.keys()}
        for field in ("photo", "city", "nationality", "interest", "note", "price_from", "price_to", "rating", "cost"):
            if field in row and not row.get(field) and d[field]:
                row[field] = d[field]
        have = {(p["platform"], (p.get("url") or "").lower()) for p in db.split_profiles(k["profiles"] or "")}
        profs = db.split_profiles(k["profiles"] or "")
        for p in db.split_profiles(d["profiles"] or ""):
            if (p["platform"], (p.get("url") or "").lower()) not in have:
                profs.append(p)
        row["profiles"] = json.dumps(profs)
        # One creator on several platforms: the platform list and the total reach
        # are the sum of what both records knew.
        import analysis as _an
        plats = []
        for src in (k, d):
            for pl in _an.creator_platforms(src):
                if pl not in plats:
                    plats.append(pl)
        for p in profs:
            pl = _an.canon_platform(p.get("platform"))
            if pl and pl not in plats:
                plats.append(pl)
        row["platform"] = ", ".join(plats)
        total = db.total_followers(profs)
        if total:
            row["followers"] = total
        adopted_photo = bool(row.get("photo")) and row.get("photo") == d["photo"] and k["photo"] != d["photo"]
        with history.tracked("creator", keep, label):
            with db.connect() as conn:
                db.upsert_creator(row, conn)
        # the duplicate goes (its photo to the bin unless the kept creator took it)
        with history.tracked("creator", drop, label):
            if d["photo"] and not adopted_photo:
                history.trash_photo(Path(str(d["photo"]).split("?")[0]).name)
            db.delete_creator(drop)

    def post_roster_delete(self):
        f = self.form_body()
        code = f.get("code")
        if code:
            # The picture is not in the database, it is a file beside the site,
            # so deleting the row on its own left the photograph on disk — and
            # a signed link to it kept working. Take it with the record.
            existing = db.creator(code)
            if existing is not None and existing["photo"]:
                stale = PHOTO_DIR / Path(str(existing["photo"]).split("?")[0]).name
                try:
                    if stale.parent == PHOTO_DIR and stale.is_file():
                        # To the bin, not erased: Undo on the History page
                        # brings the photograph back with the creator.
                        history.trash_photo(stale.name)
                        Handler.forget_photo_widths()
                except OSError:
                    # A photo we cannot remove is untidy, not a reason to leave
                    # the creator in the roster.
                    pass
            # Where the admin was: the creator just below the deleted one (or
            # just above, if it was the last), on whatever page that creator
            # sits once the row is gone. Returning to the top of the page meant
            # scrolling back down after every delete.
            everyone = [c["code"] for c in db.list_creators(search=f.get("q"))]
            near = None
            if code in everyone:
                i = everyone.index(code)
                near = (everyone[i + 1] if i + 1 < len(everyone)
                        else everyone[i - 1] if i > 0 else None)
            db.delete_creator(code)
            if near is not None:
                at = [c["code"] for c in db.list_creators(search=f.get("q"))].index(near)
                f = dict(f, page=str(at // ROSTER_PAGE + 1))
            return self.roster_back(f, ("near-" + near) if near else None,
                                    ok=code + " deleted. Changed your mind? Restore it from History → Trash.")
        return self.roster_back(f)

    # --------------------------------------------------------- selections --

    def site_origin(self):
        """The catalogue's own address, for the links a selection hands out."""
        # ALLOWED_ORIGINS is a set, so it cannot be indexed; with one origin
        # configured (the catalogue's) any element is the one.
        return (sorted(ALLOWED_ORIGINS)[0] if ALLOWED_ORIGINS
                else "https://" + (self.headers.get("Host") or "")).rstrip("/")

    def post_client_preview(self):
        """Clients page button: open the portal as this client (read-only). Sets the client's pass for
        an hour plus the preview marker, then lands on the client's own page."""
        f = self.form_body()
        rid = (f.get("id") or "").strip()
        row = db.get_code(int(rid)) if rid.isdigit() else None
        if row is None or row["id"] == db.admin_code_id():
            return self.redirect("/clients")
        expiry = db.now() + PREVIEW_TTL
        ticket = auth.sign("%d:%d" % (row["id"], expiry), SECRET)
        policy = "SameSite=None; Secure" if ALLOWED_ORIGINS else "SameSite=Lax"
        base = "; Path=/; HttpOnly; %s; Max-Age=%d" % (policy, PREVIEW_TTL)
        db.log("preview", row["id"], self.client_ip(), self.headers.get("User-Agent"), "admin preview of " + (row["label"] or "")[:60])
        target = self.site_origin() + ("/account/" if portal.user_for_code(row["id"]) else "/")
        self.send(303, b"", "text/plain", [("Location", target),
                                           ("Set-Cookie", VIEWER_COOKIE + "=" + ticket + base),
                                           ("Set-Cookie", PREVIEW_COOKIE + "=1" + base)])

    def post_selection_new(self):
        """Re-price a selection a client already has: one they sent as a quote
        request, or one whose link was pasted in. Asking twice for the same
        request reopens the one already priced rather than starting another."""
        f = self.form_body(multi=("t_category",))
        if f.get("mode") == "scratch":
            # A new, empty selection built here: a name, the client, the platform and the currency.
            name = (f.get("name") or "").strip()[:120]
            if not name:
                return self.redirect("/selections?f=name&e=" + urllib.parse.quote("Give the selection a name."))
            cid = (f.get("code_id") or "").strip()
            cur = (f.get("currency") or "SAR").strip().upper()
            plat = (f.get("platform") or "").strip() or None
            with history.tracked("selection", None, "Created selection " + name) as t:
                sid = db.save_selection(None, name, [], {}, None, None, code_id=int(cid) if cid.isdigit() else None,
                                        platform=plat if plat in db.PLATFORMS else None)
                db.set_selection_currency(sid, cur if fx.usable(cur) else "SAR")
                import fit as _fit_new
                if (f.get("sel_objective") or "") in _fit_new.OBJECTIVES:
                    db.set_selection_objective(sid, f["sel_objective"])
                db.set_selection_target(sid, {
                    "country": self.clean_multi(f.get("t_country"), dict(_fit_new.COUNTRIES), "SA"),
                    "gender": f.get("t_gender") if f.get("t_gender") in _fit_new.GENDERS else "Any",
                    "age": self.clean_multi(f.get("t_age"), _fit_new.AGE_BANDS, "Any"),
                    "category": self.clean_categories(f.get("t_category"))})
                t["key"] = sid
            return self.redirect("/selections/edit?id=%d&ok=%s#st=creators" % (
                sid, urllib.parse.quote("Created. Add the creators, then set their prices.")))
        if f.get("mode") == "from_campaign":
            cid = (f.get("campaign") or "").strip()
            k = db.campaign(int(cid)) if cid.isdigit() else None
            if k is None:
                return self.redirect("/campaigns")
            known = {c["code"] for c in db.list_creators()}
            codes = [m["cc_code"] for m in db.campaign_creators(k["id"]) if m["cc_code"] in known]
            if not codes:
                return self.redirect("/campaigns/edit?id=%d&e=%s" % (k["id"], urllib.parse.quote("Add creators to the campaign first.")))
            name = (k["name"] + " — selection")[:120]
            with history.tracked("selection", None, "Created selection " + name) as t:
                sid = db.save_selection(None, name, codes, {}, None, None, code_id=k["code_id"], auto_campaign=False,
                                        platform=k["platform"] if k["platform"] in db.PLATFORMS else None)
                t["key"] = sid
            return self.redirect("/selections/edit?id=%d&ok=%s#st=creators" % (
                sid, urllib.parse.quote("Created from the campaign. Set the prices.")))
        rid = (f.get("request") or "").strip()
        known = {c["code"] for c in db.list_creators()}
        code_id = None

        if rid.isdigit():
            existing = db.selection_for_request(int(rid))
            if existing is not None:
                return self.redirect("/selections/edit?id=%d" % existing["id"])
            req = db.request(int(rid))
            if req is None:
                return self.redirect("/requests")
            codes = [c for c in json.loads(req["selection"] or "[]") if isinstance(c, str)]
            # The same name the client's link carries, so that link matches.
            name = req["selection_name"] or ((req["company"] or "Client") + " selection")
            code_id = req["code_id"]
            # The client's own shortlist is already here — naming it on the
            # catalogue recorded it. Price THAT one, or the link they hold
            # would go on showing the standard prices while a second, priced
            # copy sat in the dashboard.
            mine = db.selection_for_link(name, [c for c in codes if c in known], code_id)
            if mine is not None:
                db.attach_request(mine["id"], int(rid))
                return self.redirect("/selections/edit?id=%d" % mine["id"])
        else:
            link = (f.get("link") or "").strip()
            frag = urllib.parse.unquote(link.split("#", 1)[1]) if "#" in link else ""
            parts = dict(p.split("=", 1) for p in frag.split("&") if "=" in p)
            if parts.get("s"):
                sel = db.selection(token=parts["s"], deleted=True)
                if sel is not None:
                    return self.redirect("/selections/edit?id=%d" % sel["id"])
            name = (parts.get("n") or "").strip()
            codes = [c.strip().upper() for c in (parts.get("c") or "").split(",") if c.strip()]
            if not codes:
                return self.redirect("/selections?e=" + urllib.parse.quote(
                    "That is not a selection link. Paste the whole link the client has, "
                    "the one containing /selection/#n=…&c=…"))
            existing = db.selection_for_link(name, codes)
            if existing is not None:
                return self.redirect("/selections/edit?id=%d" % existing["id"])
            name = name or "Selection"
            rid = ""
        codes = [c for c in codes if c in known]
        sid = db.save_selection(None, name, codes, {}, None, None,
                                int(rid) if rid.isdigit() else None, code_id)
        return self.redirect("/selections/edit?id=%d" % sid)

    def post_selection_save(self):
        f = self.form_body(multi=("code", "vcode", "p_from", "p_to", "cost", "tags", "segs", "fit", "roles", "reason", "drop", "default", "t_category", "plat_assign"))
        sid = (f.get("id") or "").strip()
        sel = db.selection(int(sid)) if sid.isdigit() else None
        if sel is None:
            return self.redirect("/selections")
        make_default = {c.strip().upper() for c in (f.get("default") or [])}

        def num(v):
            v = "".join(ch for ch in (v or "") if ch.isdigit())
            return int(v) if v else None

        cur = (f.get("currency") or "SAR").strip().upper()
        cur = cur if fx.usable(cur) else "SAR"

        # The margin is a percentage and may carry a decimal ("27.5").
        raw_margin = "".join(ch for ch in (f.get("margin") or "") if ch.isdigit() or ch == ".")
        try:
            margin = round(float(raw_margin), 2) if raw_margin else None
        except ValueError:
            margin = None

        raw_max = "".join(ch for ch in (f.get("margin_max") or "") if ch.isdigit() or ch == ".")
        try:
            margin_max = round(float(raw_max), 2) if raw_max else None
        except ValueError:
            margin_max = None
        codes, prices, costs = [], {}, {}
        known = {c["code"] for c in db.list_creators()}
        cost_in = f.get("cost") or []
        rows = zip(f.get("code") or [], f.get("p_from") or [], f.get("p_to") or [],
                   cost_in + [""] * (len(f.get("code") or []) - len(cost_in)))
        remove = set(f.get("drop") or [])
        # The Fit & tags tab has its own row per creator (vcode), so its lists
        # line up with each other whatever the pricing table holds.
        # The tab is fetched only when opened: if it never was, leave its data as it is.
        fit_loaded = bool(f.get("fit_loaded"))
        vc = (f.get("vcode") or []) if fit_loaded else []
        vc = [vc] if isinstance(vc, str) else list(vc)
        tag_in = f.get("tags") or []
        tag_in = [tag_in] if isinstance(tag_in, str) else list(tag_in)
        tag_in = tag_in + [""] * (len(vc) - len(tag_in))
        tags = {}
        for code_, raw in zip(vc, tag_in):
            seen_t, mine = set(), []
            for t in re.split(r"[,;\n]+", raw or ""):
                t = re.sub(r"\s+", " ", t).strip()[:24]
                if t and t.lower() not in seen_t and len(mine) < 8:
                    seen_t.add(t.lower()); mine.append(t)
            if mine:
                tags[code_.strip().upper()] = mine
        if fit_loaded:
            # Item 3c (Bido, 25 Oct 2026): a tag opens a section of its own when the client groups
            # by Tags, unless it is ticked here as a sub-tag -- then it only ever shows inside a main
            # tag's section, under "Then by: Tags". One mark per tag, shared by every selection.
            subs_in = f.get("tagsub") or []
            subs_in = [subs_in] if isinstance(subs_in, str) else list(subs_in)
            db.set_setting("tag_subs", sorted({re.sub(r"\s+", " ", t_).strip().lower()
                                               for t_ in subs_in if t_ and t_.strip()}))
        seg_in = f.get("segs") or []
        seg_in = [seg_in] if isinstance(seg_in, str) else list(seg_in)
        seg_in = seg_in + [""] * (len(vc) - len(seg_in))
        segments = {}
        for code_, raw in zip(vc, seg_in):
            seen_s, mine = set(), []
            for t in re.split(r"[,;\n]+", raw or ""):
                t = re.sub(r"\s+", " ", t).strip()[:40]
                if t and t.lower() not in seen_s and len(mine) < 6:
                    seen_s.add(t.lower()); mine.append(t)
            if mine:
                segments[code_.strip().upper()] = mine
        import fit as fit_mod
        n_rows = len(vc)
        lists = {}
        for k in ("fit", "roles", "reason"):
            v = f.get(k) or []
            v = [v] if isinstance(v, str) else list(v)
            lists[k] = v + [""] * (n_rows - len(v))
        pa = f.get("plat_assign") or []
        pa = [pa] if isinstance(pa, str) else list(pa)
        pa = pa + [""] * (len(vc) - len(pa))
        platforms_map = {}
        for code_, raw in zip(vc, pa):
            raw = (raw or "").strip()
            val = "Both" if raw == "Both" else (analysis.canon_platform(raw) or "")
            if val:
                platforms_map[code_.strip().upper()] = val
        verdicts = {}
        for i, code_ in enumerate(vc):
            v = fit_mod.clean(lists["fit"][i].strip(), [x.strip() for x in lists["roles"][i].split(",")], lists["reason"][i])
            if v:
                verdicts[code_.strip().upper()] = v
        for code, lo, hi, cost in rows:
            code = code.strip().upper()
            if not code or code in codes or code in remove or code not in known:
                continue
            codes.append(code)
            # A cost sets the price to cost plus the margin — unless the admin
            # typed a different price for that creator, which is kept as their
            # own (the page then shows the profit and margin it leaves).
            # Costs and prices are typed in the selection's currency, and the
            # price is rounded in it too (10 SAR, 10 AED, 5 USD, 50 EGP);
            # they are stored in SAR underneath.
            cost = num(cost) or None             # 0 is "no cost typed", never a real fee
            if cost is not None:
                rate = float(fx.rates().get(cur, 1.0))
                step_c = {"USD": 5, "EGP": 50}.get(cur, 10)
                costs[code] = cost if cur == "SAR" else round(cost / rate, 2)
                # The client's range: from cost + the minimum margin (the lowest
                # we accept) up to cost + the maximum margin; one price when
                # no higher maximum is set.
                auto_lo = int(math.ceil(cost * (1 + (margin or 0) / 100.0) / step_c) * step_c)
                auto_hi = (int(math.ceil(cost * (1 + margin_max / 100.0) / step_c) * step_c)
                           if (margin_max is not None and margin_max > (margin or 0)) else auto_lo)
                lo_c, hi_c = num(lo), num(hi)
                typed = lo_c if lo_c is not None else hi_c
                if typed is not None:
                    a, b = (lo_c if lo_c is not None else hi_c), (hi_c if hi_c is not None else lo_c)
                    a, b = min(a, b), max(a, b)
                if typed is not None and (abs(a - auto_lo) > step_c or abs(b - auto_hi) > step_c):
                    prices[code] = sorted([fx.to_sar(a, cur), fx.to_sar(b, cur)])      # typed by hand: kept
                else:
                    prices[code] = sorted([fx.to_sar(auto_lo, cur), fx.to_sar(auto_hi, cur)])
                continue
            # Typed in the selection's currency, kept in SAR.
            lo, hi = fx.to_sar(num(lo), cur), fx.to_sar(num(hi), cur)
            if lo is None and hi is not None: lo = hi
            if hi is None and lo is not None: hi = lo
            if lo is not None:
                prices[code] = sorted([lo, hi])
        for c in re.findall(r"HV-[A-Z0-9]{2,4}-\d+", (f.get("add") or "").upper()):
            if c in known and c not in codes:
                codes.append(c)
        platform = (f.get("platform") or "").strip() or None
        # 0 is not a total: it would show the client "0 SAR". Treated as empty,
        # which means "add up the creators".
        t_from = fx.to_sar(num(f.get("total_from")) or None, cur)
        t_to = fx.to_sar(num(f.get("total_to")) or None, cur)
        if t_from is None and t_to is not None: t_from = t_to
        if t_to is None and t_from is not None: t_to = t_from
        if t_from is not None and t_to < t_from: t_from, t_to = t_to, t_from
        name = (f.get("name") or "").strip() or sel["name"]
        db.set_selection_currency(sel["id"], cur)
        import fit as _fit_mod
        if "sel_client" in f:
            raw = (f.get("sel_client") or "").strip()
            cid = int(raw) if raw.isdigit() and db.get_code(int(raw)) is not None else None
            db.set_selection_client(sel["id"], cid, (f.get("client_name") or "").strip()[:80])
        if fit_loaded and (f.get("sel_objective") or "") in _fit_mod.OBJECTIVES:
            db.set_selection_objective(sel["id"], f["sel_objective"])
        # The audience target lives on the Fit & tags tab, which is only sent when it
        # was opened: saving without it must leave the target as it is.
        if fit_loaded and any(k in f for k in ("t_country", "t_gender", "t_age", "t_category")):
            db.set_selection_target(sel["id"], {
                "country": self.clean_multi(f.get("t_country"), dict(_fit_mod.COUNTRIES), "SA"),
                "gender": f.get("t_gender") if f.get("t_gender") in _fit_mod.GENDERS else "Any",
                "age": self.clean_multi(f.get("t_age"), _fit_mod.AGE_BANDS, "Any"),
                "category": self.clean_categories(f.get("t_category"))})
        if db.zero_priced(sel["id"]) and (any(v and max(v) > 0 for v in prices.values()) or costs):
            db.unzero_selection(sel["id"])                  # prices typed by hand in the admin: they apply from now on
        db.save_selection(sel["id"], name, codes, prices, t_from, t_to, platform=platform,
                          margin=margin, costs=costs, margin_max=margin_max,
                          tags=({k: v for k, v in tags.items() if k in codes} if fit_loaded else None),
                          verdicts=({k: v for k, v in verdicts.items() if k in codes} if fit_loaded else None),
                          platforms=({k: v for k, v in platforms_map.items() if k in codes} if fit_loaded else None),
                          segments=({k: v for k, v in segments.items() if k in codes} if fit_loaded and "segs" in f else None))
        if "sel_group" in f and (f.get("sel_group") or "") in dict(db.GROUPS):
            db.set_selection_group(sel["id"], f.get("sel_group") or "")
        # A price typed here belongs to THIS selection. Only the ones ticked
        # "make default" also become the creator's price on the roster, so a
        # one-off deal does not silently change what every later selection
        # starts from. Each roster change is its own entry in History.
        with db.connect() as conn:
            db.set_costs({k: int(round(v)) for k, v in costs.items()}, conn)
        saved_default = []
        for code in sorted(make_default):
            band = prices.get(code)
            if not band:
                continue
            c0 = db.creator(code)
            if c0 is None or (c0["price_from"], c0["price_to"]) == (band[0], band[1]):
                continue
            with history.tracked("creator", code, "Price set as default from selection: " + name):
                with db.connect() as conn:
                    row = {k: c0[k] for k in c0.keys()}
                    row["price_from"], row["price_to"] = band[0], band[1]
                    db.upsert_creator(row, conn)
            saved_default.append(code)
        msg = "Saved." + ((" Default price updated for " + ", ".join(saved_default) + ".") if saved_default else "")
        self.ring_selection(sel)
        return self.redirect("/selections/edit?id=%d&ok=%s" % (sel["id"], urllib.parse.quote(msg)))

    def post_selection_status_admin(self):
        """The admin's Client status tab: one creator at a time, answered as JSON."""
        f = self.form_body()
        sid = (f.get("id") or "").strip()
        sel = db.selection(int(sid)) if sid.isdigit() else None
        if sel is None:
            return self.send_json(404, {"ok": False, "message": "That selection no longer exists."})
        code = (f.get("code") or "").strip().upper()
        kind, name, _u = self._status_who("admin", db.admin_code_id())
        row, err = selstatus.set_status(sel, code, f.get("status") or "", kind, name, f.get("reason"), f.get("note"))
        if err:
            return self.send_json(400, {"ok": False, "message": {"status": "Pick a status.",
                                                                   "not_in_selection": "That creator is not in this selection."}.get(err, err)})
        selstatus.ring_client(sel, code, row["s"], name, row.get("note"))
        return self.send_json(200, {"ok": True, "status": row, "label": selstatus.LABEL[row["s"]],
                                    "who": "%s · HelloVoice" % name})

    def ring_selection(self, before):
        """HelloVoice saved a client's selection: "shared with you" the first time it is
        theirs, then "updated" (at most once a day)."""
        import inbox
        sel = db.selection(before["id"])
        if sel is None or not sel["code_id"]:
            return
        users = inbox.for_codes([sel["code_id"]])
        href = "selection/#s=" + sel["token"]
        n = len(json.loads(sel["codes"] or "[]"))
        if not n:
            return
        with db.connect() as conn:
            made_here = conn.execute("SELECT 1 FROM history WHERE entity = 'selection' AND key = ? AND action = 'created' LIMIT 1",
                                     (str(sel["id"]),)).fetchone() is not None
        shared = 0
        if before["code_id"] != sel["code_id"] or made_here:
            # Made (or moved) here for this client: the first save with creators shares it.
            shared = inbox.emit(users, "sel_shared", "HelloVoice shared a selection:", rest=" " + sel["name"],
                                body="%d creator%s to review" % (n, "" if n == 1 else "s"), href=href,
                                ref="shared:%d:%d" % (sel["id"], sel["code_id"]), once=True)
        if not shared:
            inbox.emit(users, "sel_updated", sel["name"] + " was updated",
                       body="HelloVoice changed the creators or prices", href=href,
                       ref="upd:%d:%s" % (sel["id"], inbox.today()), once=True)

    def post_selection_delete(self):
        sid = (self.form_body().get("id") or "").strip()
        if not sid.isdigit() or db.selection(int(sid)) is None:
            return self.redirect("/selections?e=" + urllib.parse.quote("That selection no longer exists."))
        db.delete_selection(int(sid))
        return self.redirect("/selections?ok=" + urllib.parse.quote(
            "Selection deleted. Changed your mind? Restore it from History → Trash."))

    # ---------------------------------------------------------- campaigns --

    def post_campaign_new(self):
        """A blank campaign from the form on the Campaigns page, or one filled
        from a selection: its creators, passcode, platform and the costs it
        was priced from."""
        f = self.form_body()
        sid = (f.get("selection") or "").strip()
        if sid.isdigit():
            sel = db.selection(int(sid))
            if sel is None:
                return self.redirect("/selections?e=" + urllib.parse.quote(
                    "That selection no longer exists."))
            known = {c["code"] for c in db.list_creators()}
            codes = [c for c in json.loads(sel["codes"] or "[]") if c in known]
            costs = json.loads((sel["costs"] if "costs" in sel.keys() else None) or "{}")
            client = None
            if sel["code_id"]:
                code = db.get_code(sel["code_id"])
                client = code["label"] if code else None
            cid = db.create_campaign(sel["name"], client=client, code_id=sel["code_id"],
                                     selection_id=sel["id"], platform=sel["platform"],
                                     codes=codes, costs={k: v for k, v in costs.items()
                                                         if isinstance(v, int)})
            return self.redirect("/campaigns/edit?id=%d&ok=%s" % (cid, urllib.parse.quote(
                "Campaign started from the selection. Set its dates and rules, then set it live.")))
        name = (f.get("name") or "").strip()
        if not name:
            return self.redirect("/campaigns?f=name&e=" + urllib.parse.quote("Give the campaign a name."))
        code_id = (f.get("code_id") or "").strip()
        cid = db.create_campaign(name, client=(f.get("client") or "").strip() or None,
                                 code_id=int(code_id) if code_id.isdigit() else None)
        return self.redirect("/campaigns/edit?id=%d" % cid)

    _IMPORTS = {}                           # token -> (parsed sheet, time): a preview waits for its Confirm

    def post_campaign_import(self, confirm):
        """Upload a filled campaign workbook: preview it (writes nothing), then create the campaign on Confirm."""
        import campaign_sheet
        import kam_scope
        if kam_scope.current() is not None:
            return self.redirect("/campaigns?e=" + urllib.parse.quote("Only an admin can set up a campaign from a workbook."))
        pend = Handler._IMPORTS
        for t in [t for t, (_, at) in pend.items() if time.time() - at > 1800]:
            pend.pop(t, None)
        f = self.form_body()
        if confirm:
            got = pend.pop((f.get("token") or "").strip(), None)
            if got is None:
                return self.redirect("/campaigns?e=" + urllib.parse.quote("That preview has expired. Upload the workbook again."))
            parsed = got[0]
            if parsed["errors"]:
                return self.redirect("/campaigns?e=" + urllib.parse.quote("The workbook still has problems."))
            cid, notes = campaign_sheet.apply(parsed, getattr(self, "admin_name", None) or "admin")
            return self.redirect("/campaigns/edit?id=%d&ok=%s" % (cid, urllib.parse.quote(" ".join(notes[-1:]))))
        part = f.get("sheet")
        if not part or not isinstance(part, dict) or not part.get("data"):
            return self.redirect("/campaigns?e=" + urllib.parse.quote("Choose the filled workbook first."))
        parsed = campaign_sheet.parse(part["data"])
        import secrets
        token = secrets.token_urlsafe(12)
        pend[token] = (parsed, time.time())
        return self.send(200, views.campaign_import_preview(parsed, token))

    def post_campaign_save(self):
        f = self.form_body(multi=("code", "cost", "drop", "planned", "logo", "logo_file",
                                  "pending_status", "pending_date"))
        cid = (f.get("id") or "").strip()
        k = db.campaign(int(cid)) if cid.isdigit() else None
        if k is None:
            return self.redirect("/campaigns")
        back = "/campaigns/edit?id=%d" % k["id"]

        def fail(msg):
            return self.redirect(back + "&e=" + urllib.parse.quote(msg))

        # Two people saving the same campaign: the slower one would silently
        # undo the faster one's changes. Refuse it and let them reload.
        if (f.get("updated_at") or "").strip() != str(k["updated_at"]):
            return fail("Someone else saved this campaign while you had it open. "
                        "Reload the page and make your change again.")

        def money(v):
            v = "".join(ch for ch in (v or "") if ch.isdigit())
            return int(v) if v else None

        starts = (f.get("starts") or "").strip()
        ends = (f.get("ends") or "").strip()
        t_start = db.day_bounds(starts, None) if starts else None
        t_end = db.day_bounds(ends, None) if ends else None
        if (starts and t_start is None) or (ends and t_end is None):
            return fail("That date is not valid.")
        if t_end is not None:
            t_end += 86400 - 1          # the last day counts in full
        if t_start is not None and t_end is not None and t_end < t_start:
            return fail("The last day is before the first day.")
        status = (f.get("status") or "draft").strip()
        if status not in db.CAMPAIGN_STATUSES:
            status = "draft"
        if status == "live" and (t_start is None or t_end is None):
            return fail("Set the first and last day before setting the campaign live.")

        destination = (f.get("destination") or "").strip()
        if destination and not re.match(r"^https?://[^\s/]+\.[^\s]+$", destination):
            return fail("The destination must be a full web address starting with https://")

        rules = db.parse_rules(f.get("rules"))
        told = db.parse_rules(f.get("disclosure"))
        rules["disclosure"] = told["hashtags"] + told["keywords"]
        code_id = (f.get("code_id") or "").strip()
        platform = (f.get("platform") or "").strip() or None
        if platform and platform not in db.PLATFORMS:
            platform = None

        # Creators: fees, removals, then additions.
        known = {c["code"] for c in db.list_creators()}
        codes_in = f.get("code") or []
        fees = f.get("cost") or []
        costs = {code.strip().upper(): money(fee)
                 for code, fee in zip(codes_in, fees + [""] * (len(codes_in) - len(fees)))}
        remove = {c.strip().upper() for c in (f.get("drop") or [])}
        # Codes, profile links or @handles, any mix: each is matched to the
        # roster, and a profile the roster does not have yet is added to it.
        entries = [c for c in re.split(r"[\s,;]+", f.get("add") or "") if c.strip()]
        adds, add_notes = db.resolve_creators(entries, k["name"]) if entries else ([], [])
        adds = [c for c in adds if c not in remove]

        db.save_campaign(k["id"], name=(f.get("name") or "").strip() or k["name"],
                         client=(f.get("client") or "").strip() or None,
                         code_id=int(code_id) if code_id.isdigit() else None,
                         platform=platform, starts_at=t_start, ends_at=t_end, status=status,
                         rules=rules, destination=destination or None,
                         cost=money(f.get("total_cost")), notes=(f.get("notes") or "").strip() or None)
        vis = {key: f.get("vis_" + key) == "1" for key in ("reach", "clicks", "all_content", "audience")}
        vis["emv"] = False                   # EMV is internal only
        vis["scored"] = f.get("vis_scored") == "1"
        vis["notes"] = (f.get("vis_notes") or "").strip()[:2000]
        own_rates = self.rates_from(f)
        targets = {}
        for key in db.TARGET_KEYS:
            raw = "".join(ch for ch in (f.get("target_" + key) or "") if ch.isdigit() or ch == ".")
            try:
                if raw and float(raw) > 0:
                    targets[key] = float(raw) if key == "er" else int(float(raw))
            except ValueError:
                pass
        steps = []
        for key, label in db.DEFAULT_STEPS:
            st = f.get("step_state_" + key)
            a, b = (f.get("step_start_" + key) or "").strip(), (f.get("step_end_" + key) or "").strip()
            steps.append({"key": key, "label": (f.get("step_label_" + key) or "").strip()[:60] or label,
                          "on": f.get("step_on_" + key) == "1",
                          "start": a if db.day_bounds(a, None) is not None else None,
                          "end": b if db.day_bounds(b, None) is not None else None,
                          "state": st if st in db.STEP_STATES else "pending"})
        phase = next((x["key"] for x in steps if x["on"] and x["state"] == "active"), None)
        logos = [x for x in (f.get("logo") or []) if self.logo_ok(x)][:6]
        up = [p for p in (f.get("logo_file") or []) if isinstance(p, dict) and p.get("data")]
        for part in up[:3]:
            kind = uploads.image_kind(part["data"])
            if kind in ("png", "jpg", "webp") and len(part["data"]) <= 3 * 1024 * 1024:
                import secrets as _s
                LOGO_DIR.mkdir(exist_ok=True)
                name = _s.token_hex(10) + "." + kind
                (LOGO_DIR / name).write_bytes(part["data"])
                logos.append("upload/" + name)
        sel_id = (f.get("selection_id") or "").strip()
        # The objective is a template that fills four percentages the admin can
        # then change. What is saved is the percentages: when they are one of
        # the templates the campaign keeps that name, otherwise it is "Custom".
        tpl = f.get("objective") if metrics.valid_objective(f.get("objective")) else "balanced"
        typed = metrics.weights_from_percents([f.get("w_reach"), f.get("w_eng"), f.get("w_er"), f.get("w_clicks")]) \
            if any((f.get(x) or "").strip() for x in ("w_reach", "w_eng", "w_er", "w_clicks")) else None
        if typed is not None:
            objective = metrics.objective_for(typed, prefer=tpl)
            weights = [round(x, 4) for x in typed] if objective == "custom" else None
        else:
            objective, weights = (tpl if tpl != "custom" else "balanced"), None
        db.save_campaign(k["id"], visibility=vis, emv={"*": own_rates} if own_rates else None,
                         targets=targets, phase=phase, steps=steps,
                         objective=objective, weights=weights,
                         status_note=(f.get("status_note") or "").strip()[:240] or None, logos=logos,
                         selection_id=int(sel_id) if sel_id.isdigit() else None)
        planned = {}
        for code, n in zip(codes_in, (f.get("planned") or []) + [""] * len(codes_in)):
            n = "".join(ch for ch in (n or "") if ch.isdigit())
            planned[code.strip().upper()] = int(n) if n else None
        db.set_planned(k["id"], planned)
        statuses, dates = f.get("pending_status") or [], f.get("pending_date") or []
        pending = {}
        for i, code in enumerate(codes_in):
            st = (statuses[i] if i < len(statuses) else "").strip()
            dt = (dates[i] if i < len(dates) else "").strip()
            pending[code.strip().upper()] = (st if st in db.PENDING_STATUSES else None,
                                             dt if db.day_bounds(dt, None) is not None else None)
        db.set_pending(k["id"], pending)
        db.save_campaign_creators(k["id"], costs, remove)
        if adds:
            db.add_campaign_creators(k["id"], adds)
        if adds or add_notes:
            msg = "Saved. Added %d creator%s." % (len(adds), "" if len(adds) == 1 else "s")
            if add_notes:
                msg += " " + " · ".join(add_notes)
            return self.redirect(back + "&ok=" + urllib.parse.quote(msg[:1500]))
        return self.redirect(back + "&ok=" + urllib.parse.quote("Saved."))

    def post_campaign_link(self):
        """One link's destination override, and its name while unclicked."""
        f = self.form_body()
        cid = (f.get("id") or "").strip()
        back = "/campaigns/links?id=" + cid
        slug = (f.get("slug") or "").strip()
        dest = (f.get("destination") or "").strip()
        if dest and not re.match(r"^https?://[^\s/]+\.[^\s]+$", dest):
            return self.redirect(back + "&e=" + urllib.parse.quote(
                "The destination must be a full web address starting with https://"))
        with db.connect() as _c:
            _own = _c.execute("SELECT campaign_id FROM links WHERE slug = ?", (slug,)).fetchone()
        if _own is None or str(_own[0]) != cid:
            return self.redirect(back + "&e=" + urllib.parse.quote("That link is not on this campaign."))
        problem = db.save_link(slug, dest, (f.get("new_slug") or "").strip().lower() or None)
        if problem:
            return self.redirect(back + "&e=" + urllib.parse.quote(problem))
        return self.redirect(back + "&ok=" + urllib.parse.quote("Link saved."))

    def clicks_csv(self, cid):
        import csv, io
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["time (UTC)", "link", "creator", "app", "device", "os", "country",
                    "referrer", "counted"])
        with db.connect() as conn:
            for r in conn.execute("SELECT * FROM clicks WHERE campaign_id = ? ORDER BY at",
                                  (cid,)):
                w.writerow([ts(r["at"]), r["slug"], r["code"], r["app"], r["device"], r["os"],
                            r["country"] or "", r["referrer"] or "",
                            "no (bot/preview)" if r["bot"] else "yes"])
        return "\ufeff" + out.getvalue()      # BOM: Excel reads it as UTF-8

    # ------------------------------------------------- content & settings --

    def all_posts(self, k):
        """Every post (hidden too) with its derived numbers, for the admin."""
        f = metrics.factors()
        out = []
        for c in db.campaign_content(k["id"]):
            out.append({**c, **metrics.post_numbers(c, f)})
        return out

    @staticmethod
    def rates_from(f):
        rates = {}
        for a in metrics.EMV_ACTIONS:
            v = "".join(ch for ch in (f.get("emv_" + a) or "") if ch.isdigit() or ch == ".")
            try:
                if v and float(v) > 0:
                    rates[a] = float(v)
            except ValueError:
                pass
        return rates

    @staticmethod
    def counts_from(f):
        out = {}
        for m in db.METRICS:
            v = "".join(ch for ch in (f.get(m) or "") if ch.isdigit())
            out[m] = int(v) if v else None
        return out

    def post_content_add(self):
        """Add one post. Only the link is needed: the platform and kind come from the link, the creator from the handle in it
        (or, for an Instagram link that names nobody, from reading the post), and the numbers and date from the platform."""
        f = self.form_body()
        cid = (f.get("id") or "").strip()
        k = db.campaign(int(cid)) if cid.isdigit() else None
        if k is None:
            return self.redirect("/campaigns")
        back = "/campaigns/content?id=%d" % k["id"]
        url = (f.get("url") or "").strip()
        if not re.match(r"^https://[^\s/]+\.[^\s]+$", url):
            return self.redirect(back + "&e=" + urllib.parse.quote("The post link must start with https://"))
        import postlink
        url = postlink.canonical(url)               # a share link is followed to the post, so its numbers can be matched
        plat_i, kind_i, handle = postlink.infer(url)
        members = db.campaign_creators(k["id"])
        mine = {m["cc_code"] for m in members}
        code = (f.get("code") or "").strip().upper()
        found, how = None, ""
        if not code:
            hs = [(m["cc_code"], apify.creator_handles(m)) for m in members if m["code"]]
            code = postlink.pick_creator(handle, hs) or ""
            how = "the handle in the link" if code else ""
            if not code and len(mine) == 1:
                code, how = next(iter(mine)), "the only creator on the campaign"
            if not code and (plat_i or "Instagram") == "Instagram":
                found = apify.look_up_post(url)
                code = postlink.pick_creator(found["owner"], hs) if found else ""
                how = "reading the post" if code else ""
        if code not in mine:
            who = ", ".join("%s (%s)" % (m["cc_code"], (m["name"] if "name" in m.keys() and m["name"] else "")) for m in members[:15])
            return self.redirect(back + "&f=code&e=" + urllib.parse.quote(
                "I could not tell which creator posted this. Tell me one of: %s." % who if code == "" else "Pick a creator in this campaign."))
        platform = f.get("platform") if f.get("platform") in db.PLATFORMS else (plat_i or "Instagram")
        kind = f.get("kind") if f.get("kind") in db.KINDS else (kind_i or "post")
        posted = db.day_bounds(f.get("posted") or "", None) or (found or {}).get("posted_at")
        counts = self.counts_from(f)
        for m_, v_ in ((found or {}).get("numbers") or {}).items():
            if counts.get(m_) is None:
                counts[m_] = v_
        item = {"code": code, "platform": platform, "kind": kind, "url": url, "posted_at": posted,
                "caption": (f.get("caption") or "").strip() or (found or {}).get("caption"),
                "followers": db.platform_followers(code, platform), **counts}
        _, created = db.add_content(k["id"], item, source="manual")
        thumbs.fill_later(k["id"])
        tail = ""
        if found and found.get("numbers"):
            tail = " Its numbers and date were read from %s." % platform
        else:
            # Nothing was read yet: start this campaign's capture for the platform now, when that is only a handful of posts.
            with db.connect() as conn:
                job = conn.execute("SELECT id FROM api_jobs WHERE source = ? AND kind = 'post_urls' AND platform = ? LIMIT 1",
                                   ("campaign:%d" % k["id"], platform)).fetchone()
                n = conn.execute("SELECT COUNT(*) FROM content WHERE campaign_id = ? AND hidden = 0 AND platform = ?",
                                 (k["id"], platform)).fetchone()[0]
            ok_, _msg = apify.start_job(job["id"], "link") if job is not None and n <= 8 else (False, "")
            tail = (" Its numbers and date are being read from %s now." % platform if ok_
                    else " Its numbers and date arrive with the next capture.")
        return self.redirect(back + "&ok=" + urllib.parse.quote(
            ("Post added for %s%s." % (code, " (%s)" % how if how else "") if created
             else "That post was already here: its numbers were updated.") + tail))

    def post_content_pending(self):
        f = self.form_body(multi=("code", "pending_status", "pending_date"))
        cid = (f.get("id") or "").strip()
        k = db.campaign(int(cid)) if cid.isdigit() else None
        if k is None:
            return self.redirect("/campaigns")
        codes, sts, dts = f.get("code") or [], f.get("pending_status") or [], f.get("pending_date") or []
        as_list = lambda v: [v] if isinstance(v, str) else v
        codes, sts, dts = as_list(codes), as_list(sts), as_list(dts)
        mine = {m["cc_code"] for m in db.campaign_creators(k["id"])}
        pending = {}
        for i, code in enumerate(codes):
            code = code.strip().upper()
            if code not in mine:
                continue
            st = (sts[i] if i < len(sts) else "").strip()
            dt = (dts[i] if i < len(dts) else "").strip()
            pending[code] = (st if st in db.PENDING_STATUSES else None,
                             dt if db.day_bounds(dt, None) is not None else None)
        db.set_pending(k["id"], pending)
        return self.redirect("/campaigns/content?id=%d&ok=%s#add=status" % (k["id"], urllib.parse.quote("Saved.")))

    def post_content_bulk(self):
        """Paste many post links for one creator, or paste a block of numbers.
        links:   one URL per line.
        numbers: one line per post — the post URL, then likes comments views
                 shares saves (any separator; missing ones are left alone)."""
        f = self.form_body()
        cid = (f.get("id") or "").strip()
        k = db.campaign(int(cid)) if cid.isdigit() else None
        if k is None:
            return self.redirect("/campaigns")
        back = "/campaigns/content?id=%d" % k["id"]
        text = f.get("text") or ""
        if f.get("do") == "numbers":
            def norm(x):
                return re.sub(r"[?#].*$", "", x.strip()).rstrip("/").lower()
            by_url = {norm(p["url"]): p for p in db.campaign_content(k["id"])}
            done = miss = 0
            for line in text.splitlines():
                m = re.search(r"https?://\S+", line)
                if not m:
                    continue
                post = by_url.get(norm(m.group(0).rstrip(",;")))
                if not post:
                    miss += 1
                    continue
                nums = re.findall(r"\d[\d,\.]*", line[m.end():])
                vals = {}
                for name, raw in zip(("likes", "comments", "views", "shares", "saves"), nums):
                    digits = raw.replace(",", "").split(".")[0]
                    if digits.isdigit():
                        vals[name] = int(digits)
                if vals:
                    db.add_snapshot(post["id"], vals, "manual")
                    done += 1
            msg = "Numbers saved on %d post%s." % (done, "" if done == 1 else "s")
            if miss:
                msg += " %d link%s did not match a post here — add them first." % (miss, "" if miss == 1 else "s")
            return self.redirect(back + "&ok=" + urllib.parse.quote(msg))
        code = (f.get("code") or "").strip().upper()
        if code not in {m["cc_code"] for m in db.campaign_creators(k["id"])}:
            return self.redirect(back + "&f=code&e=" + urllib.parse.quote("Pick a creator in this campaign."))
        platform = f.get("platform") if f.get("platform") in db.PLATFORMS else "Instagram"
        kind = f.get("kind") if f.get("kind") in db.KINDS else "post"
        posted = db.day_bounds(f.get("posted") or "", None)
        added = seen = 0
        for line in text.splitlines():
            m = re.search(r"https://[^\s,;]+\.[^\s,;]+", line)
            if not m:
                continue
            item = {"code": code, "platform": platform, "kind": kind, "url": m.group(0), "posted_at": posted,
                    "caption": None, "followers": db.platform_followers(code, platform)}
            _, created = db.add_content(k["id"], item, source="manual")
            added += 1 if created else 0
            seen += 0 if created else 1
        if added:
            thumbs.fill_later(k["id"])
        if not added and not seen:
            return self.redirect(back + "&e=" + urllib.parse.quote("No links found. Paste one https:// link per line."))
        msg = "%d post%s added." % (added, "" if added == 1 else "s")
        if seen:
            msg += " %d already here." % seen
        return self.redirect(back + "&ok=" + urllib.parse.quote(msg))

    def post_content_group(self):
        """Tick posts of one creator, say they are the same video on different platforms (or split one out)."""
        f = self.form_body(multi=("pick",))
        cid = (f.get("id") or "").strip()
        k = db.campaign(int(cid)) if cid.isdigit() else None
        if k is None:
            return self.redirect("/campaigns")
        back = "/campaigns/content?id=" + cid
        q = urllib.parse.quote
        picks = [int(x) for x in (f.get("pick") or []) if str(x).isdigit()]
        with db.connect() as _c:
            mine_ids = {r[0] for r in _c.execute("SELECT id FROM content WHERE campaign_id = ?", (k["id"],))}
        picks = [i for i in picks if i in mine_ids]
        if f.get("do") == "split":
            for i in picks:
                db.ungroup_content(i)
            return self.redirect(back + "&ok=" + q("Taken out of its video."))
        n, err = db.group_content(k["id"], picks)
        if err == "few":
            return self.redirect(back + "&e=" + q("Tick at least two posts of the same video."))
        if err == "creator":
            return self.redirect(back + "&e=" + q("Those posts are from different creators. Tick one creator's posts only."))
        return self.redirect(back + "&ok=" + q("%d posts now count as one video. Their numbers add up." % n))

    def post_content_update(self):
        f = self.form_body()
        cid, pid = (f.get("id") or "").strip(), (f.get("content") or "").strip()
        item = db.content_item(int(pid)) if pid.isdigit() else None
        if item is None or str(item["campaign_id"]) != cid:
            return self.redirect("/campaigns")
        back = "/campaigns/content?id=" + cid
        what = f.get("do")
        if what in ("campaign", "other"):
            db.update_content(item["id"], section=what)
        elif what in ("hide", "unhide"):
            db.update_content(item["id"], hidden=1 if what == "hide" else 0)
        elif what == "delete":
            db.delete_content(item["id"])
        elif what == "metrics":
            db.add_snapshot(item["id"], self.counts_from(f), "manual")
        return self.redirect(back + "&ok=" + urllib.parse.quote("Saved."))

    def post_domain_kam(self):
        """Settings card: company domain -> key account manager (owners and admins only: /settings
        is refused to a KAM by team.can)."""
        f = self.form_body()
        try:
            n = max(0, min(200, int(f.get("rows") or 0)))
        except ValueError:
            n = 0
        mapping = {}
        for i in range(n):
            d, k = (f.get("domain_%d" % i) or "").strip(), (f.get("kam_%d" % i) or "").strip()
            if d and k:
                mapping[d] = k
        with history.tracked("settings", "*", "Changed key account manager domains"):
            saved, changed = kam_scope.set_domain_map(mapping)
        who = self.admin()
        team.log("domain_kam", who["email"] if who is not None else "", ", ".join("%s=%s" % kv for kv in sorted(saved.items()))[:300], self.client_ip())
        return self.redirect("/settings?ok=" + urllib.parse.quote(
            "Saved %d domain%s. %d existing account%s now show their key account manager." % (
                len(saved), "" if len(saved) == 1 else "s", changed, "" if changed == 1 else "s")) + "#kams")

    def post_settings_fx(self):
        """Fixed exchange rates: 1 SAR = x of each currency. Empty switches a
        currency off."""
        f = self.form_body()
        out = {}
        for c in fx.CURRENCIES[1:]:
            raw = "".join(ch for ch in (f.get("fx_" + c) or "") if ch.isdigit() or ch == ".")
            try:
                out[c] = float(raw) if raw and float(raw) > 0 else None
            except ValueError:
                out[c] = None
        db.set_setting("fx_rates", out)
        return self.redirect("/settings?ok=" + urllib.parse.quote("Exchange rates saved.") + "#fx")

    def post_settings(self):
        f = self.form_body()
        db.set_setting("emv_rates", {"*": self.rates_from(f)})
        fac = {}
        for key, default in metrics.DEFAULT_FACTORS.items():
            try:
                v = float((f.get(key) or "").strip())
                fac[key] = v if v > 0 else default
            except ValueError:
                fac[key] = default
        db.set_setting("reach_factors", fac)
        bm = metrics.benchmarks()
        def pair(prefix, current):
            try:
                g, o = float(f.get(prefix + "_good") or current[0]), float(f.get(prefix + "_ok") or current[1])
                return [g, o] if g >= o >= 0 else current
            except ValueError:
                return current
        for b in bm["er"]:
            bm["er"][b] = pair("bm_er_" + b, bm["er"][b])
        for key in ("video_er", "view_rate", "story_rate", "ctr"):
            bm[key] = pair("bm_" + key, bm[key])
        for key in ("fake_followers", "fake_likers"):
            try:   # lower is better: the "good" ceiling sits under the "moderate" one
                g, o = float(f.get("bm_" + key + "_good") or bm[key][0]), float(f.get("bm_" + key + "_ok") or bm[key][1])
                bm[key] = [g, o] if 0 <= g <= o <= 100 else bm[key]
            except ValueError:
                pass
        db.set_setting("benchmarks", bm)
        import score_model as sm
        if any(k.startswith("sm_") for k in f):
            wover, bover = {}, {}
            for o, row in sm.WEIGHTS.items():
                for p, d in row.items():
                    try:
                        x = float(f.get("sm_w_%s_%s" % (o, p)) or d)
                    except ValueError:
                        continue
                    if x >= 0 and x != float(d):
                        wover.setdefault(o, {})[p] = x
            for m, groups in sm.BANDS.items():
                for g, (dz, df) in groups.items():
                    try:
                        z = float(f.get("sm_b_%s_%s_zero" % (m, g)) or dz)
                        fu = float(f.get("sm_b_%s_%s_full" % (m, g)) or df)
                    except ValueError:
                        continue
                    if z >= 0 and fu >= 0 and z != fu and (z, fu) != (float(dz), float(df)):
                        bover.setdefault(m, {})[g] = [z, fu]
            db.set_setting("score_model", {"weights": wover, "bands": bover})
            sm._overrides(fresh=True)
        import intl_benchmarks as ib
        if any(k.startswith("ib_") for k in f):
            over = {}
            for platform, entry in ib.TABLE.items():
                for band in ib.BANDS:
                    d_lo, d_hi = entry["bands"][band]
                    try:
                        lo = float(f.get("ib_%s_%s_low" % (platform, band)) or d_lo)
                        hi = float(f.get("ib_%s_%s_high" % (platform, band)) or d_hi)
                    except ValueError:
                        continue
                    if lo > 0 and hi >= lo and (lo, hi) != (float(d_lo), float(d_hi)):
                        over.setdefault(platform, {})[band] = [lo, hi]
            db.set_setting("intl_benchmarks", over)
            ib._overrides(fresh=True)
        return self.redirect("/settings?ok=" + urllib.parse.quote("Settings saved."))

    def post_settings_token(self):
        import hashlib, secrets
        token = "hvcap_" + secrets.token_urlsafe(32)
        db.set_setting("capture_token", hashlib.sha256(token.encode()).hexdigest())
        return self.send(200, views.settings_page(
            db.setting("emv_rates") or {}, metrics.factors(), True, db.capture_runs(),
            track.GEO_DB.exists(), token))

    # -------------------------------------------------------- client API --

    def selection_client(self, sel):
        """Who a selection is for, as the client reads it: the name set on the
        selection, else the account holder's company (their code's label is an
        internal 'Client: email'), else the passcode's client label."""
        named = sel["client_name"] if "client_name" in sel.keys() else None
        if named:
            return named
        if not sel["code_id"]:
            return ""
        u = portal.user_for_code(sel["code_id"])
        if u is not None:
            return u["company"] or u["name"] or ""
        return (db.get_code(sel["code_id"]) or {"label": ""})["label"]

    def api_campaign_start(self):
        """A signed-in client starts a campaign from their account (owner, 2026-10-17): a draft under their
        account that their account manager is told about and approves. {name, note}"""
        b = self.json_body()
        cid = self.signed_in_client()
        user = self.person_user(cid) if cid is not None else None
        if user is None or self.admin_like():
            return self.send_json(401, {"ok": False, "reason": "signin", "message": "Sign in with your work email first."}, self.cors())
        if self._throttled("campstart:%d" % cid, 10, 3600):
            return
        name = " ".join(str(b.get("name") or "").split())[:120]
        if len(name) < 3:
            return self.send_json(400, {"ok": False, "reason": "name", "message": "Give the campaign a name (3 letters or more)."}, self.cors())
        note = " ".join(str(b.get("note") or "").split())[:500]
        # The tenant's own cap (Tenants -> Limits). Counted here, where they create one.
        if modules.over(cid, "campaigns_max", modules.count(cid, "campaigns")):
            return self.send_json(403, {"ok": False, "reason": "limit", "message":
                                        "You have as many campaigns as your plan allows. Ask your account manager for more."},
                                  self.cors())
        k = db.create_campaign(name, client=user["company"] or None, code_id=cid, origin="client")
        if note:
            db.save_campaign(k, notes="Client's note: " + note)
        import kam_items
        kam_items.tell_campaign_started(db.campaign(k), user, note)
        return self.send_json(200, {"ok": True, "token": db.campaign(k)["token"]}, self.cors())

    def api_campaign_build_selection(self):
        """"Build your selection" on a campaign with none (owner, 2026-10-17): an empty selection is made for the
        client, linked to the campaign, and opened in the catalogue ready to fill. {t: campaign token}"""
        b = self.json_body()
        cid = self.signed_in_client()
        if cid is None or self.admin_like():
            return self.send_json(401, {"ok": False, "reason": "signin", "message": "Sign in with your work email first."}, self.cors())
        k = db.campaign(token=str(b.get("t") or ""))
        if k is None or k["code_id"] not in portal.team_codes(cid):
            return self.send_json(404, {"ok": False, "reason": "unknown"}, self.cors())
        if k["selection_id"]:
            sel = db.selection(k["selection_id"])
            return self.send_json(200, {"ok": True, "token": sel["token"] if sel else None, "name": k["name"], "existing": True}, self.cors())
        sid = db.save_selection(None, k["name"], [], {}, None, None, None, k["code_id"], origin="client", auto_campaign=False)
        db.save_campaign(k["id"], selection_id=sid)
        return self.send_json(200, {"ok": True, "token": db.selection(sid)["token"], "name": k["name"]}, self.cors())

    def api_campaigns(self):
        """The campaigns this passcode may see. Drafts are never listed."""
        code_id = (db.admin_code_id() if self.admin_like() else None) or self.link_code("c:list") or self.signed_in_client()
        if code_id is None:
            return self.send_json(401, {"ok": False, "reason": "link"}, self.cors())
        team = sorted(portal.team_codes(code_id))
        granted = sorted(db.granted_selection_ids(code_id)) or [-1]     # campaigns of selections granted to them
        staff = (self.admin_like() or self.kam_clients() is not None) and not self.as_client()
        if staff:
            # HelloVoice (owner, 2026-10-16): the team's own account has no campaigns, so its list was empty.
            # An admin sees every campaign; a key account manager, her clients'.
            with db.connect() as conn:
                every = conn.execute("SELECT token, name, client, status, phase, starts_at, ends_at, logos, code_id, id, selection_id, origin FROM campaigns "
                                     "WHERE (status != 'draft' OR origin = 'client') ORDER BY starts_at DESC").fetchall()
            out = []
            for r in every:
                cid = r["code_id"] if r["code_id"] is not None else kam_scope.campaign_code(r["id"])[1]
                if not self.admin_like_for(cid, r["selection_id"], r["id"]):
                    continue
                d = {k: r[k] for k in ("token", "name", "client", "status", "phase", "starts_at", "ends_at", "logos")}
                d["logos"] = [self.logo_url(x, r["token"]) for x in db.campaign_logos(r)][:3]
                d["draft"] = r["status"] == "draft"
                d["has_selection"] = bool(r["selection_id"])
                d["id"] = r["id"]
                out.append(d)
            out = self._pin_campaigns(out, code_id)
            return self.send_json(200, {"ok": True, "campaigns": out}, self.cors() + [("Cache-Control", "no-store")])
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT token, name, client, status, phase, starts_at, ends_at, logos, selection_id, code_id FROM campaigns "
                "WHERE (code_id IN (%s) OR selection_id IN (%s)) AND (status != 'draft' OR origin = 'client') ORDER BY starts_at DESC"
                % (",".join("?" * len(team)), ",".join("?" * len(granted))), team + granted).fetchall()
        out = []
        mine_team = set(team)
        for r in rows:
            d = dict(r)
            d["logos"] = [self.logo_url(x, r["token"]) for x in db.campaign_logos(r)][:3]
            d["draft"] = r["status"] == "draft"
            d["has_selection"] = bool(r["selection_id"])
            d["can_build"] = (not r["selection_id"]) and r["code_id"] in mine_team and self.person_user(code_id) is not None
            d.pop("selection_id", None); d.pop("code_id", None)
            out.append(d)
        out = self._pin_campaigns(out, code_id)
        return self.send_json(200, {"ok": True, "can_start": self.person_user(code_id) is not None, "campaigns": out},
                              self.cors() + [("Cache-Control", "no-store")])

    def _pin_campaigns(self, out, code_id):
        """Pinned campaigns (setting pinned_campaigns, owner 2026-10-20: the Demo Campaign) lead the list of every
        BlueHolding / HelloVoice account and of admins, marked pinned. Others see their list unchanged."""
        try:
            pins = [int(x) for x in (db.setting("pinned_campaigns") or [])]
        except (TypeError, ValueError):
            pins = []
        u = self.person_user(code_id) if code_id is not None else None
        if not pins or not (self.admin_like() or (u is not None and (u["domain"] or "").lower() in portal.SAMPLE_DOMAINS)):
            for d in out:
                d.pop("id", None)
            return out
        have = {d.get("token") for d in out}
        with db.connect() as conn:
            rows = conn.execute("SELECT id, token, name, client, status, phase, starts_at, ends_at, logos, selection_id FROM campaigns "
                                "WHERE id IN (%s) AND status != 'draft'" % ",".join("?" * len(pins)), pins).fetchall()
        tokens = set()
        for r in rows:
            tokens.add(r["token"])
            if r["token"] in have:
                continue
            d = {k: r[k] for k in ("token", "name", "client", "status", "phase", "starts_at", "ends_at")}
            d["logos"] = [self.logo_url(x, r["token"]) for x in db.campaign_logos(r)][:3]
            d["draft"] = False
            d["has_selection"] = bool(r["selection_id"])
            out.append(d)
        for d in out:
            d.pop("id", None)
            if d.get("token") in tokens:
                d["pinned"] = True
        order = {r["token"]: pins.index(r["id"]) for r in rows}
        return sorted(out, key=lambda d: (0, order[d["token"]]) if d.get("pinned") else (1, 0))

    def viewer_campaign(self, token, public_ok=False):
        k, status = self._viewer_campaign(token)
        self._public_view = False
        if k is None and public_ok and token and self.public_link("campaign", token):
            pk = db.campaign(token=token)
            if pk is not None and pk["status"] != "draft":
                self._public_view = True          # anyone, read-only (public_links)
                return pk, 200
        return k, status

    def _viewer_campaign(self, token):
        k = db.campaign(token=token) if token else None
        if k is not None and self.admin_like_for(k["code_id"] if k["code_id"] is not None else kam_scope.campaign_code(k["id"])[1],
                                                 k["selection_id"], k["id"]):
            return k, 200                       # admins (and a KAM, her clients') open any report, drafts included
        # The code typed for this report, or for the client's campaign list it was opened from.
        code_id = self.link_code("c:" + token) if token else None
        if code_id is None:
            listed = self.link_code("c:list")
            if listed is not None and k is not None and k["code_id"] in portal.team_codes(listed):
                code_id = listed
        if code_id is None:
            code_id = self.signed_in_client()
        share = getattr(self, "_share_token", "")
        if k is not None and share and k["status"] != "draft" and db.share_valid(k["id"], share):
            acct = self.signed_in_client()
            if acct is None:
                return None, 401                # the share link needs a sign in or sign up first
            db.viewer_add(k["id"], acct, "share")
            code_id = acct
        if code_id is None:
            return None, 401
        # Not found and not yours look the same from outside.
        if k is None or not portal.opens_campaign(code_id, k) or k["status"] == "draft":
            return None, 404
        return k, 200

    def campaign_role(self, k):
        """admin (the team) | edit | view (invited by email) | None."""
        if k is None:
            return None
        if self.admin_like_for(k["code_id"] if k["code_id"] is not None else kam_scope.campaign_code(k["id"])[1],
                               k["selection_id"], k["id"]):
            return "admin"
        acct = self.signed_in_client()
        u = self.person_user(acct) if acct is not None else None
        return db.cinvite_role(k["id"], u["email"]) if u is not None else None

    def api_campaign(self, token):
        k, status = self.viewer_campaign(token, public_ok=True)
        if k is None:
            return self.send_json(status, {"ok": False, "signin": status == 401}, self.cors())
        public = bool(getattr(self, "_public_view", False))
        db.log("view", None if public else self.viewer_code_id(), self.client_ip(), self.headers.get("User-Agent"),
               ("public " if public else "") + "campaign:" + k["name"][:60])
        rep = metrics.client_report(k, photo=links.thumb, photo_large=links.photo)
        rep["campaign"]["logos"] = [self.logo_url(x, k["token"]) for x in rep["campaign"]["logos"]]
        for p in rep["posts"]:
            p["thumb"] = self.thumb_url(p.get("thumb"), k["token"])
        if public:
            # Read-only for anyone: the client's report, no share controls, no money fields.
            rep = self.public_strip(rep)
            rep["public"] = True
            return self.send_json(200, {"ok": True, "report": rep, "public": True},
                                  self.cors() + [("Cache-Control", "no-store")])
        role = self.campaign_role(k)
        # Every selection the campaign holds (item 174), the ones this reader may open.
        try:
            import board
            acct0 = self.signed_in_client()
            rep["campaign"]["selections"] = [
                {"token": s["token"], "name": s["name"], "creators": board._creators(s)}
                for s in board._selections(board.selection_ids(k))
                if role == "admin" or (acct0 is not None and portal.opens(int(acct0), s))]
        except Exception:
            rep["campaign"]["selections"] = []
        if role in ("view", "edit"):
            acct = self.signed_in_client()
            u = self.person_user(acct) if acct is not None else None
            if u is not None:
                db.cinvite_seen(k["id"], u["email"])
        if role in ("admin", "edit"):
            import mailer
            sh = db.share_get(k["id"])
            on = bool(sh and sh["enabled"])
            rep["share"] = {"can": True, "role": role, "people": db.cinvites_for(k["id"]), "enabled": on,
                            "url": (mailer.SITE + "/campaign/dashboard/#t=%s&share=%s" % (k["token"], sh["token"])) if on else None}
        return self.send_json(200, {"ok": True, "report": rep},
                              self.cors() + [("Cache-Control", "no-store")])

    REFRESH_LIMIT = 10          # "Update now" presses a client may use per campaign; the team has no limit
    REFRESH_WAIT = 90           # seconds between two updates of one campaign

    def api_campaign_refresh(self, token, start, what="posts"):
        """The dashboard's Update posts / Update comments (item 223, 2026-10-21; was one Update now): run the
        campaign's capture jobs (the ones that fit the posts it has) so the numbers are fresh, or read every video's
        comments again. GET = the state ({left, running, last_at, posts{...}, comments{...}}); POST {what} = start.
        Clients share one count of free fetches across both; the team has no limit and sees the Apify cost."""
        import apify
        k, status = self.viewer_campaign(token, public_ok=not start)
        if k is None:
            return self.send_json(status, {"ok": False, "signin": status == 401}, self.cors())
        if getattr(self, "_public_view", False):
            # A public read-only reader: no Update now, and nothing is polled or started for them.
            return self.send_json(200, {"ok": True, "limit": 0, "used": 0, "unlimited": False, "left": 0,
                                        "running": False, "last_at": db.refresh_last(k["id"]), "public": True},
                                  self.cors() + [("Cache-Control", "no-store")])
        team = self.campaign_role(k) in ("admin", "edit")
        import comments as _cm
        if _cm._is_sample(k):
            # The demo campaign (owner, 2026-10-20): dummy data, nothing to fetch, no Apify spend.
            if start:
                return self.send_json(409, {"ok": False, "reason": "demo",
                                            "message": "This is a demo campaign: its numbers are sample data, so there is nothing to update."}, self.cors())
            return self.send_json(200, {"ok": True, "limit": 0, "used": 0, "unlimited": True, "left": None, "running": False,
                                        "last_at": db.refresh_last(k["id"]), "demo": True}, self.cors() + [("Cache-Control", "no-store")])
        if start and k["status"] == "live":
            apify.ensure_campaign_jobs(k["id"])     # a campaign set live before 2026-10-19 gets its capture jobs here
        jobs = [j for j in apify.list_jobs() if j["source"] == "campaign:%d" % k["id"] and j["kind"] == "post_urls"
                and j["enabled"] and j["schedule"] in ("daily", "weekly")]
        ids = [j["id"] for j in jobs]

        def running():
            if not ids:
                return False
            with db.connect() as conn:
                return bool(conn.execute("SELECT 1 FROM api_runs WHERE status IN ('QUEUED','RUNNING') AND job_id IN (%s)"
                                         % ",".join("?" * len(ids)), ids).fetchone())

        def plain_time(hhmm):
            try:
                hh, mm = (int(x) for x in hhmm.split(":"))
            except (ValueError, AttributeError):
                return None
            return "%d:%02d %s" % ((hh % 12) or 12, mm, "am" if hh < 12 else "pm")

        def sides(team):
            import metrics
            times = sorted({plain_time(j["at_time"]) for j in jobs if j["schedule"] == "daily"} - {None})
            posts = {"schedule": ("Every day at %s (Riyadh time)" % " and ".join(times)) if times else "Not scheduled",
                     "next_at": metrics.next_capture(k), "running": running(), "last_at": None}
            with db.connect() as conn:
                if ids:
                    r = conn.execute("SELECT MAX(finished_at) FROM api_runs WHERE status = 'SUCCEEDED' AND job_id IN (%s)"
                                     % ",".join("?" * len(ids)), ids).fetchone()
                    posts["last_at"] = r[0] if r else None
                pressed = db.refresh_last(k["id"], "posts")
                if team and ids:
                    posts["est"] = round(sum(apify.estimate_job(i)[1] for i in ids), 2)
                    if pressed:
                        r = conn.execute("SELECT SUM(cost) FROM api_runs WHERE started_at >= ? AND job_id IN (%s)"
                                         % ",".join("?" * len(ids)), [pressed] + ids).fetchone()
                        posts["cost"] = round(r[0], 3) if r and r[0] is not None else None
            cm = _cm.schedule_info(k, since=db.refresh_last(k["id"], "comments"))
            if cm.get("running") or cm.get("pending_ai"):
                _cm.catch_up()                   # someone may be watching the fetch: finish it without waiting for the loop
            if not team:
                cm.pop("cost", None)
            else:
                cm["est"] = _cm.fetch_estimate(k["id"])
                cm["budget_left"] = round(max(0.0, apify.budget() - apify.spent_this_month()), 2)
            return {"posts": posts, "comments": cm}

        def state(**more):
            used = db.refresh_count(k["id"])
            try:
                extra = int((db.setting("campaign_update_extra", {}) or {}).get(str(k["id"]), 0))
            except (TypeError, ValueError, AttributeError):
                extra = 0
            limit = self.REFRESH_LIMIT + max(0, extra)         # a team-granted extra comes on top of the free ones
            d = {"ok": True, "limit": limit, "used": used, "unlimited": team,
                 "left": None if team else max(0, limit - used), "running": running(), "last_at": db.refresh_last(k["id"])}
            d.update(sides(team))
            d.update(more)
            return self.send_json(200, d, self.cors() + [("Cache-Control", "no-store")])
        if not start:
            if running():
                try:
                    apify.refresh_all()          # finish runs that are done, without waiting for the minute tick
                except Exception:
                    pass
            return state()
        if running():
            return state()
        who = self.admin()
        try:
            extra = int((db.setting("campaign_update_extra", {}) or {}).get(str(k["id"]), 0))
        except (TypeError, ValueError, AttributeError):
            extra = 0
        if not team and db.refresh_count(k["id"]) >= self.REFRESH_LIMIT + max(0, extra):
            return self.send_json(429, {"ok": False, "reason": "limit", "message": "You have used all your free updates for this campaign."}, self.cors())
        last = db.refresh_last(k["id"], what)
        if last and db.now() - last < self.REFRESH_WAIT:
            return self.send_json(429, {"ok": False, "reason": "wait", "message": "Updated a moment ago. Try again in a minute."}, self.cors())
        if what == "comments":
            if _cm.schedule_info(k)["running"]:
                return state(what="comments")
            n = _cm.fetch_now(k["id"])
            if not n:
                return self.send_json(502, {"ok": False, "reason": "none", "message": "There are no videos to read comments from yet."}, self.cors())
            db.refresh_log(k["id"], self.signed_in_client(), team, n, "comments")
            return state(started=n, what="comments")
        started, t0 = 0, db.now()
        for j in jobs:
            if apify._post_pairs(j):
                ok, _msg = apify.start_job(j["id"], "portal")
                started += 1 if ok else 0
        if not started:
            return self.send_json(502, {"ok": False, "reason": "none", "message": "There is nothing to update right now."}, self.cors())
        # The daily capture follows the last update: from now it runs every 24 hours from this moment.
        lt = time.gmtime(t0 + 3 * 3600)
        with db.connect() as conn:
            conn.execute("UPDATE api_jobs SET at_time = ? WHERE id IN (%s)" % ",".join("?" * len(ids)), ["%02d:%02d" % (lt.tm_hour, lt.tm_min)] + ids)
        db.refresh_log(k["id"], self.signed_in_client(), team, started, "posts")
        return state(started=started, what="posts")

    def api_campaign_refresh_request(self):
        """A viewer who used all their free updates asks the team for more: the account manager and the owners are emailed."""
        b = self.json_body()
        k, status = self.viewer_campaign(str(b.get("t") or ""))
        if k is None:
            return self.send_json(status, {"ok": False, "signin": status == 401}, self.cors())
        cid = self.viewer_code_id()
        user = self.person_user(cid) if cid is not None else None
        if self._throttled("updreq:%d:%d" % (k["id"], cid or 0), 3, 86400):
            return
        note = " ".join(str(b.get("note") or "").split())[:400]
        who = "%s <%s>%s" % ((user["name"] or user["email"]) if user else "A viewer", user["email"] if user else "no email",
                             (" · " + user["company"]) if user and user["company"] else "")
        import access
        import notify
        notify.send("quote", ['%s used all their free updates on the campaign "%s" and asks for more.' % (who, k["name"]),
                              ("Their note: " + note) if note else "",
                              "To give them more, add an extra for this campaign (or reply to them)."],
                    kam=(user["kam"] if user is not None and "kam" in user.keys() else None),
                    link=mailer.SITE + "/admin/campaigns/edit?id=%d" % k["id"], also=access._owners())
        return self.send_json(200, {"ok": True, "message": "Request sent. Your account manager will be in touch."}, self.cors())

    def api_campaign_share(self):
        """Manage who can open a campaign's dashboard (the team, and invitees with the edit role).
        {t, action: on|off|invite|role|remove, email?, role?: view|edit}"""
        import guard
        import mailer
        b = self.json_body()
        k = db.campaign(token=str(b.get("t") or ""))
        role = self.campaign_role(k)
        if role not in ("admin", "edit"):
            return self.send_json(404, {"ok": False}, self.cors())
        action = str(b.get("action") or "on")
        who = self.admin()
        acct = self.signed_in_client()
        u = self.person_user(acct) if acct is not None else None
        by = who["email"] if who is not None else (u["email"] if u is not None else "")
        by_name = (u["name"] if u is not None and u["name"] else "") or "HelloVoice"
        msg = ""
        if action == "off":
            db.share_disable(k["id"])
        elif action == "on":
            db.share_enable(k["id"], by)
        elif action in ("invite", "role", "remove"):
            raw = str(b.get("email") or "")
            email = guard.normalise_email(raw) or ""
            if not email:
                return self.send_json(400, {"ok": False, "message": "That does not look like an email address."}, self.cors())
            if action == "remove":
                db.cinvite_remove(k["id"], email)
                msg = "Access removed for %s." % email
            else:
                r = "edit" if str(b.get("role") or "view") == "edit" else "view"
                have = db.cinvites_for(k["id"])
                if len(have) >= 25 and email not in {x["email"] for x in have}:
                    return self.send_json(400, {"ok": False, "message": "This dashboard already has 25 invited people."}, self.cors())
                if u is not None and (u["email"] or "").lower() == email:
                    return self.send_json(400, {"ok": False, "message": "That is you: you already have access."}, self.cors())
                new, changed = db.cinvite_add(k["id"], email, r, by)
                what = "view and edit" if r == "edit" else "view only"
                msg = "%s can now %s." % (email, what) if not new else "Invited %s (%s)." % (email, what)
                if changed and mailer.configured():
                    try:
                        mailer.send_access(email, "campaign dashboard", k["name"], by_name, what,
                                           "%s/campaign/dashboard/#t=%s" % (mailer.SITE, k["token"]))
                        msg += " We emailed them the link."
                    except Exception:
                        msg += " The email could not be sent: copy the link to them."
        else:
            return self.send_json(400, {"ok": False}, self.cors())
        sh = db.share_get(k["id"])
        on = bool(sh and sh["enabled"])
        return self.send_json(200, {"ok": True, "enabled": on, "message": msg, "people": db.cinvites_for(k["id"]),
                                    "url": (mailer.SITE + "/campaign/dashboard/#t=%s&share=%s" % (k["token"], sh["token"])) if on else None}, self.cors())

    def api_campaign_csv(self, token):
        k, status = self.viewer_campaign(token)
        if k is None:
            return self.send(status, b"", "text/plain")
        return self.send(200, self.full_csv(metrics.client_report(k)), "text/csv; charset=utf-8",
                         self.cors() + [("Content-Disposition", 'attachment; filename="campaign-%s.csv"'
                                         % db.campaign_slug(k))])

    def full_csv(self, rep):
        """The client's whole report as one CSV: summary, targets, creators,
        posts and clicks, each block under its own heading line, so it opens
        in Excel as one readable sheet."""
        import csv, io
        out = io.StringIO()
        w = csv.writer(out)
        c, t = rep["campaign"], rep["total"]
        f2 = lambda v: "" if v is None else ("%.2f" % v)
        w.writerow(["CAMPAIGN REPORT"])
        w.writerow(["Campaign", c["name"]]); w.writerow(["Brand", c.get("client") or ""])
        w.writerow(["Dates", views._date_value(c.get("starts_at")) + " to " + views._date_value(c.get("ends_at"))])
        w.writerow(["Objective", (rep.get("objective") or {}).get("label", "")])
        w.writerow(["Overall", (rep.get("verdict") or {}).get("label", "")])
        w.writerow(["Data updated", ts(rep.get("updated_at")) if rep.get("updated_at") else ""])
        w.writerow([])
        w.writerow(["RESULTS"])
        for label, key in (("Posts live", "delivered"), ("Posts planned", "planned"), ("Views", "views"), ("Reach", "reach"),
                           ("Impressions", "impressions"), ("Engagement", "engagement"), ("Likes", "likes"),
                           ("Comments", "comments"), ("Saves", "saves"), ("Shares", "shares"), ("Affiliate clicks", "clicks")):
            if key in t:
                w.writerow([label, t.get(key) if t.get(key) is not None else ""])
        w.writerow(["Avg engagement rate %", f2(t.get("er"))]); w.writerow(["Video engagement rate %", f2(t.get("video_er"))])
        if "ctr" in t:
            w.writerow(["Click-through %", "" if t.get("ctr") is None else "%.3f" % t["ctr"]])
        items = (rep.get("progress") or {}).get("items") or []
        if items:
            w.writerow([]); w.writerow(["TARGETS", "Goal", "Achieved", "% of goal", "Status"])
            for i in items:
                w.writerow([i["key"], i["goal"], round(i["actual"], 2) if isinstance(i["actual"], float) else i["actual"],
                            round(i["pct"]), {"good": "Strong", "moderate": "Fair", "low": "Low"}.get(i["grade"], "")])
        w.writerow([]); w.writerow(["LEADERBOARD", "Rank", "Creator", "Posts live", "Posts planned", "Followers", "Views",
                                    "Reach", "Engagement", "ER %", "Video ER %", "Clicks", "Score /100"])
        for cr in rep["creators"]:
            w.writerow(["", cr.get("rank") or "", cr["name"], cr.get("delivered"), cr.get("planned") or "", cr.get("followers") or "",
                        cr.get("views"), cr.get("reach", ""), cr.get("engagement"), f2(cr.get("er")), f2(cr.get("video_er")),
                        cr.get("clicks", ""), "%.0f" % (cr.get("score") or 0)])
        w.writerow([])
        posts = self.posts_csv(rep)[1:].splitlines()          # same columns as the posts export
        w.writerow(["POSTS"])
        out.write("\r\n".join(posts) + "\r\n")
        cl = rep.get("clicks")
        if cl and cl.get("clicks"):
            w.writerow([]); w.writerow(["AFFILIATE CLICKS", "Total", cl["clicks"], "Unique people", cl["uniques"]])
            for title, key in (("By creator", "by_creator"), ("By app", "by_app"), ("By country", "by_country"), ("By device", "by_device")):
                w.writerow([title])
                for r in cl.get(key) or []:
                    w.writerow(["", r["k"], r["n"]])
        return "\ufeff" + out.getvalue()

    def posts_csv(self, rep):
        import csv, io
        out = io.StringIO()
        w = csv.writer(out)
        names = {c["code"]: c["name"] for c in rep["creators"]}
        cols = ["posted (UTC)", "creator", "platform", "type", "link", "counts", "likes", "comments",
                "views", "reach", "reach source", "impressions", "ER %", "video ER %", "EMV (SAR)"]
        w.writerow(cols)
        for p in rep["posts"]:
            w.writerow([ts(p.get("posted_at")) if p.get("posted_at") else "", names.get(p["code"], p["code"]),
                        p["platform"], p["kind"], p["url"],
                        "campaign" if p.get("section") == "campaign" else "all content",
                        p.get("likes"), p.get("comments"), p.get("views") or "", p.get("reach", ""),
                        ("creator insights" if p.get("reach_real") else "estimate") if "reach" in p else "",
                        p.get("impressions", ""), "%.2f" % p["er"] if p.get("er") is not None else "",
                        "%.2f" % p["video_er"] if p.get("video_er") is not None else "",
                        "%.0f" % p["emv"] if p.get("emv") else ""])
        return "﻿" + out.getvalue()

    def report_xlsx(self, k):
        """The internal workbook: summary, creators, posts, clicks."""
        import xlsx
        r = metrics.report(k, internal=True)
        t, inn = r["total"], r["internal"]
        n = lambda v, d=0: "" if v is None else (round(v, d) if d else int(round(v)))
        summary = [["Campaign", k["name"]], ["Client", k["client"] or ""],
                   ["Dates", (views._date_value(k["starts_at"]) + " → " + views._date_value(k["ends_at"]))],
                   ["Status", k["status"]], [""],
                   ["Posts", t["posts"]], ["Views", n(t["views"])], ["Reach", n(t["reach"])],
                   ["Impressions", n(t["impressions"])], ["Engagement", n(t["engagement"])],
                   ["Avg ER %", n(t["er"], 2)], ["Video ER %", n(t["video_er"], 2)],
                   ["Impressions ER %", n(t["imp_er"], 2)], ["Clicks", t["clicks"]], ["CTR %", n(t["ctr"], 3)],
                   ["EMV (SAR)", n(t["emv"])], [""], ["INTERNAL — do not send"],
                   ["Cost (SAR)", n(inn["cost"])], ["CPM (SAR)", n(inn["cpm"], 2)],
                   ["Cost per engagement (SAR)", n(inn["cpe"], 2)], ["Cost per click (SAR)", n(inn["cpc"], 2)]]
        creators = [["Code", "Creator", "Followers", "Posts", "Views", "Reach", "Impressions", "Engagement",
                     "ER %", "Video ER %", "Clicks", "EMV (SAR)", "Fee (SAR)", "CPM (SAR)", "Cost/click (SAR)"]]
        for c in r["creators"]:
            creators.append([c["code"], c["name"], c["followers"] or "", c["posts"], n(c["views"]), n(c["reach"]),
                             n(c["impressions"]), n(c["engagement"]), n(c["er"], 2), n(c["video_er"], 2),
                             c["clicks"], n(c["emv"]), n(c.get("cost")), n(c.get("cpm"), 2), n(c.get("cpc"), 2)])
        posts = [["Posted", "Creator", "Platform", "Type", "Link", "Counts", "Likes", "Comments", "Views",
                  "Reach", "Reach source", "Impressions", "ER %", "Video ER %", "EMV (SAR)", "Disclosure"]]
        names = {c["code"]: c["name"] for c in r["creators"]}
        for p in r["posts"]:
            posts.append([views._date_value(p["posted_at"]), names.get(p["code"], p["code"]), p["platform"],
                          p["kind"], p["url"], p["section"], p["likes"], p["comments"], p["views"] or "",
                          n(p["reach"]), "insights" if p["reach_real"] else "estimate", n(p["impressions"]),
                          n(p["er"], 2), n(p["video_er"], 2), n(p["emv"]) if r["emv_set"] else "",
                          {None: "", 1: "ok", 0: "missing"}[p["disclosure_ok"]]])
        cl = [["Link", "Creator", "Clicks", "Unique"]]
        for l in db.campaign_links(k["id"]):
            cl.append([l["slug"], names.get(l["code"], l["code"]), l["clicks"], l["uniques"]])
        return xlsx.write_book([("Summary", summary, {0: 28, 1: 40}, None),
                                ("Creators", creators, None, None), ("Posts", posts, {4: 50}, None),
                                ("Clicks", cl, {0: 40}, None)])

    # ----------------------------------------------------------- capture --

    def capture_ok(self):
        import hashlib, hmac
        want = db.setting("capture_token")
        got = self.headers.get("Authorization", "")
        if not want or not got.startswith("Bearer "):
            return False
        return hmac.compare_digest(hashlib.sha256(got[7:].strip().encode()).hexdigest(), want)

    def capture_get(self, what, query):
        if not self.capture_ok():
            return self.send_json(401, {"ok": False, "error": "bad or missing token"})
        if what == "jobs":
            jobs = []
            for k in db.capture_jobs():
                members = db.campaign_creators(k["id"])
                with db.connect() as conn:
                    known = [dict(r) for r in conn.execute(
                        "SELECT id, code, platform, kind, url FROM content WHERE campaign_id = ?", (k["id"],))]
                jobs.append({
                    "campaign_id": k["id"], "name": k["name"], "platform": k["platform"],
                    "starts_at": k["starts_at"], "ends_at": k["ends_at"], "rules": db.rules_of(k),
                    "creators": [{"code": m["cc_code"], "name": m["name"],
                                  "profiles": [a for a in db.split_profiles(m["profiles"])
                                               if a.get("url") and (not k["platform"] or a["platform"] == k["platform"])]}
                                 for m in members if m["code"]],
                    "known_posts": known})
            pend = [{"id": r["id"], "campaign_id": r["campaign_id"], "code": r["code"],
                     "post_url": r["content_url"] or r["post_url"], "platform": r["platform"], "kind": r["kind"],
                     "files": json.loads(r["files"] or "[]")} for r in db.pending_insights()]
            return self.send_json(200, {"ok": True, "now": db.now(), "campaigns": jobs,
                                        "insights_pending": pend, "kinds": db.KINDS,
                                        "insight_fields": db.INSIGHT_FIELDS})
        if what == "insight-file":
            row = db.insight(int(query["i"])) if (query.get("i") or "").isdigit() else None
            if row is None:
                return self.send(404, b"", "text/plain")
            return self.insight_file(str(row["id"]), query.get("n", ""), row["campaign_id"])
        return self.send_json(404, {"ok": False})

    def capture_post(self, what):
        if not self.capture_ok():
            return self.send_json(401, {"ok": False, "error": "bad or missing token"})
        body = self.json_body()
        if what == "content":
            cid = body.get("campaign_id")
            k = db.campaign(int(cid)) if str(cid).isdigit() else None
            if k is None:
                return self.send_json(404, {"ok": False, "error": "no such campaign"})
            members = {m["cc_code"] for m in db.campaign_creators(k["id"])}
            done, created, refused = 0, 0, []
            for it in body.get("items") or []:
                why = self.capture_item_problem(it, k, members)
                if why:
                    refused.append({"url": it.get("url"), "why": why})
                    continue
                item = {"code": it["code"].upper(), "platform": it["platform"], "kind": it["kind"],
                        "url": it["url"].strip(), "posted_at": self.epoch(it.get("posted_at")),
                        "caption": (it.get("caption") or None), "thumb": it.get("thumb") or None,
                        "followers": it.get("followers") if isinstance(it.get("followers"), int)
                        else db.platform_followers(it["code"].upper(), it["platform"])}
                for m in db.METRICS:
                    v = it.get(m)
                    item[m] = v if isinstance(v, int) and v >= 0 else None
                _, new = db.add_content(k["id"], item, "capture")
                done += 1; created += 1 if new else 0
            if done:
                thumbs.fill_later(k["id"])      # keep each post's picture before its CDN link expires
            return self.send_json(200, {"ok": True, "saved": done, "new": created, "refused": refused})
        if what == "insight":
            iid = body.get("id")
            row = db.insight(int(iid)) if str(iid).isdigit() else None
            if row is None:
                return self.send_json(404, {"ok": False})
            db.set_insight_extracted(row["id"], body.get("values") or {})
            return self.send_json(200, {"ok": True})
        if what == "run":
            db.log_capture_run(bool(body.get("ok")), body.get("posts"), body.get("insights"),
                               body.get("errors") if isinstance(body.get("errors"), str)
                               else json.dumps(body.get("errors") or "")[:4000])
            return self.send_json(200, {"ok": True})
        return self.send_json(404, {"ok": False})

    @staticmethod
    def epoch(v):
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
        if isinstance(v, str) and v.strip():
            text = v.strip().replace("Z", "+00:00")
            try:
                d = datetime.fromisoformat(text)
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                return int(d.timestamp())
            except ValueError:
                return db.day_bounds(text[:10], None)
        return None

    def capture_item_problem(self, it, k, members):
        if not isinstance(it, dict):
            return "not an object"
        if (it.get("code") or "").upper() not in members:
            return "creator not in this campaign"
        if it.get("platform") not in db.PLATFORMS:
            return "unknown platform"
        if it.get("kind") not in db.KINDS:
            return "kind must be one of " + ", ".join(db.KINDS)
        if not re.match(r"^https://[^\s/]+\.[^\s]+$", (it.get("url") or "").strip()):
            return "url must start with https://"
        t = self.epoch(it.get("posted_at"))
        if t is not None and k["starts_at"] and (t < k["starts_at"] - 86400 or
                                                (k["ends_at"] and t > k["ends_at"] + 86400)):
            return "posted outside the campaign dates"
        return None

    # ---------------------------------------------------------- insights --

    def insight_file(self, iid, name, cid):
        row = db.insight(int(iid)) if str(iid).isdigit() else None
        if row is None or row["campaign_id"] != cid:
            return self.send(404, b"", "text/plain")
        files = json.loads(row["files"] or "[]")
        name = Path(name).name
        if name not in files:
            return self.send(404, b"", "text/plain")
        f = INSIGHT_DIR / name
        if not f.is_file():
            return self.send(404, b"", "text/plain")
        kind = uploads.image_kind(f.read_bytes()[:16]) or "jpeg"
        return self.send(200, f.read_bytes(), "image/" + ("jpeg" if kind == "jpg" else kind),
                         [("Cache-Control", "private, no-store")])

    def save_insight_files(self, parts):
        """Store uploaded screenshots under random names. Returns (names, error)."""
        import secrets
        files = [p for p in parts if isinstance(p, dict) and p.get("data")]
        if not files:
            return None, "Choose at least one screenshot."
        if len(files) > INSIGHT_FILES:
            return None, "At most %d screenshots at a time." % INSIGHT_FILES
        INSIGHT_DIR.mkdir(exist_ok=True)
        names = []
        for p in files:
            if len(p["data"]) > INSIGHT_MAX:
                return None, "Each screenshot must be under 12 MB."
            kind = uploads.image_kind(p["data"])
            if kind not in ("jpg", "png", "webp"):
                return None, "Screenshots must be JPG, PNG or WEBP images."
            name = secrets.token_hex(12) + "." + kind
            (INSIGHT_DIR / name).write_bytes(p["data"])
            names.append(name)
        return names, None

    def insights_public(self, token, query):
        row = db.creator_by_insights_token(token.strip("/"))
        if row is None or (row["ends_at"] and row["ends_at"] + 30 * 86400 < db.now()):
            return self.send(404, views.link_gone(), headers=[("Cache-Control", "no-store")])
        with db.connect() as conn:
            posts = conn.execute("SELECT id, url, kind, platform, posted_at FROM content WHERE campaign_id = ? "
                                 "AND code = ? AND hidden = 0 ORDER BY posted_at DESC",
                                 (row["campaign_id"], row["code"])).fetchall()
            sent = conn.execute("SELECT COUNT(*) FROM insights WHERE campaign_id = ? AND code = ?",
                                (row["campaign_id"], row["code"])).fetchone()[0]
        return self.send(200, views.insights_upload_page(row, posts, sent, query.get("ok"), query.get("e")),
                         headers=[("Cache-Control", "no-store"), ("X-Robots-Tag", "noindex")])

    def insights_upload(self, token):
        token = token.strip("/")
        row = db.creator_by_insights_token(token)
        if row is None or (row["ends_at"] and row["ends_at"] + 30 * 86400 < db.now()):
            return self.send(404, views.link_gone())
        back = (BASE_PUBLIC + "/insights/" + token)
        if int(self.headers.get("Content-Length") or 0) > INSIGHT_FILES * INSIGHT_MAX + 65536:
            return self.redirect_plain(back + "?e=" + urllib.parse.quote("That upload is too large."))
        f = self.form_body(multi=("shots",))
        names, err = self.save_insight_files(f.get("shots") or [])
        if err:
            return self.redirect_plain(back + "?e=" + urllib.parse.quote(err))
        pid = (f.get("post") or "").strip()
        item = db.content_item(int(pid)) if pid.isdigit() else None
        if item is not None and (item["campaign_id"] != row["campaign_id"] or item["code"] != row["code"]):
            item = None
        url = (f.get("url") or "").strip()[:500] or None
        db.add_insight(row["campaign_id"], row["code"], names, item["id"] if item else None,
                       None if item else url, (f.get("note") or "").strip()[:500] or None)
        return self.redirect_plain(back + "?ok=1")

    def redirect_plain(self, to):
        """A redirect that is NOT given the /admin prefix: the creator's page
        lives at the site root."""
        self.send(303, b"", "text/plain", [("Location", to)])

    def post_insight_admin_upload(self):
        f = self.form_body(multi=("shots",))
        cid = (f.get("id") or "").strip()
        k = db.campaign(int(cid)) if cid.isdigit() else None
        if k is None:
            return self.redirect("/campaigns")
        back = "/campaigns/insights?id=%d" % k["id"]
        code = (f.get("code") or "").strip().upper()
        if code not in {m["cc_code"] for m in db.campaign_creators(k["id"])}:
            return self.redirect(back + "&f=code&e=" + urllib.parse.quote("Pick a creator in this campaign."))
        names, err = self.save_insight_files(f.get("shots") or [])
        if err:
            return self.redirect(back + "&e=" + urllib.parse.quote(err))
        pid = (f.get("post") or "").strip()
        item = db.content_item(int(pid)) if pid.isdigit() else None
        db.add_insight(k["id"], code, names, item["id"] if item and item["campaign_id"] == k["id"] else None)
        return self.redirect(back + "&ok=" + urllib.parse.quote("Uploaded. The capture job reads it on its next run, or type the numbers yourself."))

    def post_insight_decide(self):
        f = self.form_body()
        cid, iid = (f.get("id") or "").strip(), (f.get("insight") or "").strip()
        row = db.insight(int(iid)) if iid.isdigit() else None
        if row is None or str(row["campaign_id"]) != cid:
            return self.redirect("/campaigns")
        back = "/campaigns/insights?id=" + cid
        if f.get("do") == "reject":
            db.decide_insight(row["id"], False)
            return self.redirect(back + "&ok=" + urllib.parse.quote("Rejected."))
        pid = (f.get("post") or "").strip()
        item = db.content_item(int(pid)) if pid.isdigit() else None
        if item is None or item["campaign_id"] != row["campaign_id"]:
            return self.redirect(back + "&e=" + urllib.parse.quote(
                "Choose which post these numbers belong to before approving."))
        values = {k: f.get(k) for k in db.INSIGHT_FIELDS}
        if not db.clean_insight_values(values):
            return self.redirect(back + "&e=" + urllib.parse.quote("Enter at least one number to approve."))
        db.decide_insight(row["id"], True, values, item["id"])
        return self.redirect(back + "&ok=" + urllib.parse.quote("Approved — the report now uses these numbers."))

    # ---------------------------------------------------- logos, links, sync --

    def client_logo_names(self):
        if CLIENT_LOGOS is None:
            return []
        return sorted(p.name for p in CLIENT_LOGOS.iterdir()
                      if p.suffix == ".webp" and "@2x" not in p.name)

    def logo_ok(self, ref):
        if ref.startswith("clients/"):
            return Path(ref).name in self.client_logo_names()
        if ref.startswith("upload/"):
            return (LOGO_DIR / Path(ref).name).is_file()
        return False

    def logo_url(self, ref, token):
        if ref.startswith("clients/"):
            name = Path(ref).name
            try:
                v = int((CLIENT_LOGOS / name).stat().st_mtime)      # a replaced logo is fetched again, not served from the browser cache
            except (OSError, TypeError):
                v = 0
            return "/assets/clients/" + name + ("?v=%d" % v if v else "")
        return BASE + "/api/campaign-logo?" + urllib.parse.urlencode({"t": token, "n": Path(ref).name})

    # ------------------------------------------------------------ planner --

    def planner_get(self, query):
        cid = query.get("id", "")
        k = db.campaign(int(cid)) if cid.isdigit() else None
        saved = (plans.plan_of(k) or {}) if k else {}
        brief = dict(saved.get("brief") or {})
        if not brief and k:
            brief = {"objective": metrics.objective_of(k), "platform": k["platform"] or "Instagram",
                     "budget": "", "links": "1" if k["destination"] else "",
                     "source": "campaign"}
        for key in ("template", "objective", "platform", "category", "budget", "links", "stories", "source") + \
                tuple("n_" + t for t in plans.TIERS):
            if key in query:
                brief[key] = query[key]
        tpl = plans.TEMPLATES.get(brief.get("template") or "")
        if tpl and query.get("apply_template") == "1":
            brief.update({"objective": tpl["objective"], "platform": tpl["platform"], "category": tpl["category"]})
            for t in plans.TIERS:
                brief["n_" + t] = tpl["mix"].get(t, "")
            if not k:
                brief["source"] = "tiers"
        budget = "".join(ch for ch in str(brief.get("budget") or "") if ch.isdigit() or ch == ".")
        b = {"platform": brief.get("platform"), "objective": brief.get("objective"),
             "category": brief.get("category"), "budget": float(budget) if budget else 0,
             "tracked_links": brief.get("links") == "1"}
        # Platforms: the ticked ones when the form was sent, else the saved brief's, else the main platform.
        if query.get("sub") == "1":
            plats = [p for p in plans.PLATFORMS if query.get("p_" + p) == "1"]
        else:
            plats = [p for p in (brief.get("platforms") or []) if p in plans.PLATFORMS]
        if not plats:
            plats = [brief.get("platform") if brief.get("platform") in plans.PLATFORMS else "Instagram"]
        brief["platforms"] = plats
        brief["platform"] = plats[0]
        b["platform"] = plats[0]
        if k and brief.get("source") != "tiers":
            mix = plans.mix_platforms_from_campaign(k, plats)
        else:
            mix = plans.mix_platforms_from_counts({t: (str(brief.get("n_" + t) or "").strip() or "0")
                                                   for t in plans.TIERS if str(brief.get("n_" + t) or "0").strip().isdigit()}, plats)
        plan = plans.calculate_platforms(b, mix)
        plan["brief"] = brief
        plan["template"] = brief.get("template") or None
        return self.send(200, views.planner_page(k, brief, plan, plans.house_benchmarks(), plans.library(),
                                                 query.get("e"), query.get("ok")))

    def post_planner_apply(self):
        f = self.form_body()
        cid = (f.get("id") or "").strip()
        k = db.campaign(int(cid)) if cid.isdigit() else None
        if k is None:
            return self.redirect("/campaigns")
        try:
            plan = json.loads(f.get("plan") or "{}")
        except ValueError:
            plan = {}
        targets = {}
        for key in db.TARGET_KEYS:
            raw = "".join(ch for ch in (f.get("target_" + key) or "") if ch.isdigit() or ch == ".")
            if raw and raw.count(".") <= 1 and float(raw) > 0:
                v = float(raw)
                targets[key] = round(v, 2) if key == "er" else int(v)
        keep = {x: plan.get(x) for x in ("platform", "objective", "category", "budget", "links", "posts",
                                          "estimate", "floor", "target", "benchmark", "roi", "brief", "template")}
        keep["agreed"] = targets
        keep["saved_at"] = db.now()
        obj = f.get("objective") if metrics.valid_objective(f.get("objective")) else metrics.objective_of(k)
        db.save_campaign(k["id"], targets=targets, objective=obj, plan=keep)
        return self.redirect("/planner?id=%d&ok=%s" % (k["id"], urllib.parse.quote(
            "Goals saved — the client's report now shows these targets and the benchmark.")))

    def post_calculator_save(self):
        """Save the figures worked out in the calculator as a campaign's goals:
        the targets the client sees, its objective, and the benchmark ranges
        behind them. The numbers are the ones typed on the page; the benchmark
        and estimates are worked out here from the campaign's booked creators."""
        f = self.form_body()
        cid = (f.get("id") or "").strip()
        k = db.campaign(int(cid)) if cid.isdigit() else None
        if k is None:
            return self.redirect("/calculator")
        typ = "traffic" if f.get("type") == "conversion" else f.get("type")        # old form value
        typ = typ if typ in ("awareness", "engagement", "traffic") else "awareness"
        objective = typ
        platform = f.get("platform") if f.get("platform") in plans.PLATFORMS else "Instagram"
        category = f.get("category") if f.get("category") in plans.CATEGORIES else "other"
        raw_budget = "".join(ch for ch in (f.get("budget") or "") if ch.isdigit() or ch == ".")
        budget = float(raw_budget) if raw_budget else 0
        targets = {}
        for key in db.TARGET_KEYS:
            raw = "".join(ch for ch in (f.get("target_" + key) or "") if ch.isdigit() or ch == ".")
            if raw and raw.count(".") <= 1 and float(raw) > 0:
                v = float(raw)
                targets[key] = round(v, 2) if key == "er" else int(v)
        p = plans.calculate({"platform": platform, "objective": objective, "category": category, "budget": budget,
                             "tracked_links": typ == "traffic"}, plans.mix_from_campaign(k))
        keep = {x: p.get(x) for x in ("platform", "objective", "category", "budget", "links", "posts",
                                       "estimate", "floor", "target", "benchmark", "roi")}
        keep["brief"] = {"type": typ, "platform": platform, "category": category, "budget": str(int(budget)) if budget else "", "source": "campaign"}
        keep["agreed"] = targets
        keep["saved_at"] = db.now()
        db.save_campaign(k["id"], targets=targets, objective=objective, plan=keep)
        return self.redirect("/calculator?id=%d&ok=%s" % (k["id"], urllib.parse.quote(
            "Goals saved: the client's report now shows these targets and the benchmark.")))

    def post_calculator_results(self):
        """Whole-campaign results by hand: pick a template or type the numbers.
        They show to the client as estimates. "Back to measured" clears them."""
        f = self.form_body()
        cid = (f.get("id") or "").strip()
        k = db.campaign(int(cid)) if cid.isdigit() else None
        if k is None:
            return self.redirect("/calculator")
        back = "/calculator?id=%d&ok=" % k["id"]
        if f.get("do") == "clear":
            db.save_campaign(k["id"], overrides={})
            return self.redirect(back + urllib.parse.quote("Back to the measured numbers."))
        out = {}
        for key in db.OVERRIDE_KEYS:
            raw = "".join(ch for ch in (f.get("r_" + key) or "") if ch.isdigit() or ch == ".")
            if raw and raw.count(".") <= 1 and float(raw) > 0:
                v = float(raw)
                out[key] = round(v, 2) if key == "er" else int(v)
        if not out:
            return self.redirect(back + urllib.parse.quote("Nothing to save: type at least one number."))
        out["_basis"] = (f.get("basis") or "set by hand").strip()[:120]
        db.save_campaign(k["id"], overrides=out)
        return self.redirect(back + urllib.parse.quote("Results saved. The client's report shows them marked as estimates."))

    def post_planner_library(self):
        f = self.form_body()
        back = (f.get("back") or "").strip()
        dest = "/planner" + ("?id=" + back + "&" if back.isdigit() else "?")
        if f.get("reset") == "1":
            db.set_setting("benchmark_library", {})
            return self.redirect(dest + "ok=" + urllib.parse.quote("Benchmark library reset to the defaults."))
        try:
            got = json.loads(f.get("library") or "")
            assert isinstance(got, dict)
        except (ValueError, AssertionError):
            return self.redirect(dest + "e=" + urllib.parse.quote("That is not valid JSON — nothing was saved."))
        db.set_setting("benchmark_library", got)
        return self.redirect(dest + "ok=" + urllib.parse.quote("Benchmark library saved."))

    def thumb_url(self, ref, token=None):
        """A stored post picture as a link the viewer may open; a captured
        CDN link is passed through (it may still work for a few days)."""
        if not ref:
            return None
        if str(ref).startswith("file:"):
            name = Path(str(ref)[5:]).name
            if token is None:
                return BASE + "/campaigns/thumb?n=" + urllib.parse.quote(name)
            return BASE + "/api/campaign-thumb?" + urllib.parse.urlencode({"t": token, "n": name})
        return ref

    def api_campaign_thumb(self, token, name):
        k, status = self.viewer_campaign(token, public_ok=True)
        name = Path(name).name
        if k is None:
            return self.send(404, b"", "text/plain")
        with db.connect() as conn:
            ok = conn.execute("SELECT 1 FROM content WHERE campaign_id = ? AND thumb = ?",
                              (k["id"], "file:" + name)).fetchone()
        f = thumbs.path_of("file:" + name) if ok else None
        if f is None:
            return self.send(404, b"", "text/plain")
        kind = uploads.image_kind(f.read_bytes()[:16]) or "jpg"
        return self.send(200, f.read_bytes(), "image/" + ("jpeg" if kind == "jpg" else kind),
                         [("Cache-Control", "private, max-age=604800")])

    def api_campaign_logo(self, token, name):
        k, status = self.viewer_campaign(token, public_ok=True)
        if k is None:
            # Item 214: whoever sees the card on the board sees its logo, drafts included (a client's draft
            # report stays closed to them; its logo is not).
            import board
            k = board.campaign_for(self, token=token)[0] if token else None
        name = Path(name).name
        if k is None or ("upload/" + name) not in db.campaign_logos(k):
            return self.send(404, b"", "text/plain")
        f = LOGO_DIR / name
        if not f.is_file():
            return self.send(404, b"", "text/plain")
        kind = uploads.image_kind(f.read_bytes()[:16]) or "png"
        return self.send(200, f.read_bytes(), "image/" + ("jpeg" if kind == "jpg" else kind),
                         [("Cache-Control", "private, max-age=86400")])

    def post_campaign_sync(self):
        f = self.form_body()
        cid = (f.get("id") or "").strip()
        if not cid.isdigit():
            return self.redirect("/campaigns")
        n = db.sync_from_selection(int(cid))
        return self.redirect("/campaigns/edit?id=%s&ok=%s" % (cid, urllib.parse.quote(
            ("Added %d creator(s) from the selection." % n) if n else "Already in line with the selection.")))

    def post_custom_link(self):
        f = self.form_body()
        cid = (f.get("id") or "").strip()
        back = "/campaigns/links?id=" + cid
        dest = (f.get("destination") or "").strip()
        if dest and not re.match(r"^https?://[^\s/]+\.[^\s]+$", dest):
            return self.redirect(back + "&e=" + urllib.parse.quote("The destination must start with https://"))
        problem = db.add_custom_link(int(cid) if cid.isdigit() else 0, (f.get("code") or "").upper(),
                                     (f.get("slug") or "").strip().lower(), dest,
                                     (f.get("label") or "").strip()[:60])
        if problem:
            return self.redirect(back + "&e=" + urllib.parse.quote(problem))
        return self.redirect(back + "&ok=" + urllib.parse.quote("Custom link added."))

    def post_link_toggle(self):
        f = self.form_body()
        row = db.link((f.get("slug") or "").strip())
        if row is None or str(row["campaign_id"]) != (f.get("id") or ""):
            return self.redirect("/campaigns")
        db.set_link_active(row["slug"], not row["active"])
        # Back to the same row, so the change is in front of the admin.
        return self.redirect("/campaigns/links?id=%d&ok=%s#link-%s" % (row["campaign_id"], urllib.parse.quote(
            "%s's link switched %s." % (row["code"], "off — taps now show 'This link is not active'"
                                         if row["active"] else "back on")), row["slug"]))

    # --------------------------------------------------- creator analysis --

    def analysis_resolver(self):
        return analysis.Resolver(db.list_creators(), db.creator_aliases())

    def clean_multi(self, raw, allowed, default):
        """A target field that may hold several values ("SA|AE"): the ones that are allowed, joined."""
        import fit as fit_mod
        got = [x for x in fit_mod.target_list(raw) if x in allowed]
        return "|".join(got) or default

    def clean_categories(self, raw):
        """The ticked product categories, kept to ones the roster knows, as "A|B|C" (or "Any")."""
        items = [raw] if isinstance(raw, str) else list(raw or [])
        known = {k.lower(): k for k in db.known_interests()}
        out = []
        for i in items:
            i = re.sub(r"\s+", " ", str(i or "")).strip()[:40]
            i = known.get(i.lower(), i)
            if i and i.lower() != "any" and i not in out and "|" not in i:
                out.append(i)
        return "|".join(out[:8]) or "Any"

    def selection_has_objective(self, sel):
        """True once the selection has a campaign objective of its own: one the client gave
        (the brief questions), the AI shortlist's brief, the admin's, or its campaign's.
        Without one nothing is scored (client decision 2026-10-09): a score against an
        assumed "Balanced" goal read as a real verdict."""
        keys = sel.keys()
        return bool((sel["objective"] if "objective" in keys else None) or db.selection_campaign_objective(sel["id"]))

    def selection_objective(self, sel):
        import fit as fit_mod
        keys = sel.keys()
        got = (sel["objective"] if "objective" in keys else None) or fit_mod.FROM_CAMPAIGN.get(db.selection_campaign_objective(sel["id"]) or "", "Balanced")
        return fit_mod.canonical(got) if fit_mod.known_objective(got) else "Balanced"

    def selection_target(self, sel):
        import fit as fit_mod
        try:
            t = json.loads((sel["target"] if "target" in sel.keys() else None) or "{}")
        except ValueError:
            t = {}
        return dict(fit_mod.DEFAULT_TARGET, **{k: v for k, v in t.items() if v})

    @staticmethod
    def scores_gate_applies(sel):
        """Every selection (owner, 2026-10-15): nothing is scored for the client until an admin publishes it."""
        return True

    def scores_gated(self, sel):
        """True while a HelloVoice-made selection's scores are not published to the client yet."""
        return self.scores_gate_applies(sel) and not (sel["scores_published"] if "scores_published" in sel.keys() else 1)

    def api_selection_request_access(self):
        """A signed-in person asks for a selection that is not theirs (owner, 2026-10-15)."""
        import access
        b = self.json_body()
        sel = db.selection(token=str(b.get("token") or ""))
        if sel is None:
            return self.send_json(404, {"ok": False, "reason": "unknown"}, self.cors())
        cid = self.signed_in_client()
        user = self.person_user(cid) if cid is not None else None
        if user is None:
            return self.send_json(401, {"ok": False, "reason": "signin", "message": "Sign in with your work email first."}, self.cors())
        if portal.opens(cid, sel):
            return self.send_json(200, {"ok": True, "already": True}, self.cors())
        if self._throttled("access:%d" % cid, 10, 3600):
            return
        access.request(sel, user)
        return self.send_json(200, {"ok": True, "requested": True}, self.cors())

    def api_selection_invite(self):
        """The selection's owner (or HelloVoice) invites an email to this one selection, lists or removes
        invites (owner, 2026-10-16). {token, do: list|add|remove, email}"""
        import access
        b = self.json_body()
        sel = db.selection(token=str(b.get("token") or ""))
        if sel is None:
            return self.send_json(404, {"ok": False, "reason": "unknown"}, self.cors())
        cid = self.signed_in_client()
        admin = self.admin_like_for(sel["code_id"], sel["id"])
        if not admin:
            if cid is None:
                return self.send_json(401, {"ok": False, "reason": "signin", "message": "Sign in with your work email first."}, self.cors())
            if not portal.may_edit(cid, sel, db.admin_code_id()):
                return self.send_json(403, {"ok": False, "reason": "owner_only", "message": "Only the owner of this selection can invite people."}, self.cors())
        do = str(b.get("do") or "list")
        email = str(b.get("email") or "")
        if do == "remove":
            access.uninvite(sel, email)
        elif do == "add":
            if cid is not None and self._throttled("invite:%d" % cid, 20, 3600):
                return
            me = self.person_user(cid) if cid is not None else None
            state, err = access.invite(sel, email, (me["email"] if me is not None else "HelloVoice"),
                                       (me["name"] if me is not None else "") or "")
            if err:
                msg = {"email": "That does not look like an email address.", "self": "That is the selection's owner: they already have it.",
                       "limit": "This selection already has %d invited people." % access.MAX_INVITES}[err]
                return self.send_json(400, {"ok": False, "reason": err, "message": msg}, self.cors())
        return self.send_json(200, {"ok": True, "people": access.people(sel)}, self.cors())

    def api_selection_scores_publish(self):
        """HelloVoice publishes (or takes back) a selection's scores for the client (owner, 2026-10-15)."""
        b = self.json_body()
        sel = db.selection(token=str(b.get("token") or ""))
        if sel is None:
            return self.send_json(404, {"ok": False, "reason": "unknown"}, self.cors())
        reader = self.selection_viewer(sel["token"])
        if self.kam_clients() is not None or not (self.admin_like_for(sel["code_id"], sel["id"]) or self.selection_role(sel, reader) == "admin"):
            # Never a key account manager (owner, 2026-10-20): scores and analysis are published by HelloVoice admins.
            return self.send_json(403, {"ok": False, "reason": "hv_only", "message": "Only HelloVoice publishes scores."}, self.cors())
        import selfilters as _sf
        if not _sf.can_publish(self):
            # Item 248 (Bido, 2026-10-24): only HelloVoice owner and admin accounts.
            return self.send_json(403, {"ok": False, "reason": "hv_admin_only", "message": "Only HelloVoice owners and admins change what the client sees."}, self.cors())
        on = bool(b.get("publish"))
        # what: "scores" (default) or "analysis" (the creators' full profile analysis).
        col = "analysis_published" if b.get("what") == "analysis" else "scores_published"
        with db.connect() as conn:
            conn.execute("UPDATE selections SET %s = ? WHERE id = ?" % col, (1 if on else 0, sel["id"]))
        db.log("shortlist", reader, self.client_ip(), self.headers.get("User-Agent"), "%s:%s:%s" % (col, sel["id"], "publish" if on else "hide"))
        return self.send_json(200, {"ok": True, "published": on, "what": "analysis" if col == "analysis_published" else "scores"}, self.cors())

    def api_selection_order(self):
        """Item 3b (Bido, 25 Oct 2026): save the exact card order a HelloVoice admin arranged on the
        selection page itself. The order IS selections.codes, which is what every reader opens in."""
        b = self.json_body()
        sel = db.selection(token=str(b.get("token") or ""))
        if sel is None:
            return self.send_json(404, {"ok": False, "reason": "unknown"}, self.cors())
        reader = self.selection_viewer(sel["token"])
        if self.kam_clients() is not None or not (self.admin_like_for(sel["code_id"], sel["id"])
                                                  or self.selection_role(sel, reader) == "admin"):
            return self.send_json(403, {"ok": False, "reason": "hv_only", "message": "Only HelloVoice arranges the cards."}, self.cors())
        import selfilters as _sf
        if not _sf.can_publish(self):
            return self.send_json(403, {"ok": False, "reason": "hv_admin_only",
                                        "message": "Only HelloVoice owners and admins change the order the client sees."}, self.cors())
        want = [str(c).strip().upper() for c in (b.get("codes") or []) if str(c).strip()]
        listed = json.loads(sel["codes"] or "[]")
        known, seen, order = set(listed), set(), []
        for c in want:                     # only creators already on this selection, each once
            if c in known and c not in seen:
                seen.add(c); order.append(c)
        if len(order) != len(listed):      # anything the page did not send keeps its place at the end
            order += [c for c in listed if c not in seen]
        if order == listed:
            return self.send_json(200, {"ok": True, "codes": order, "changed": False}, self.cors())
        with db.connect() as conn:
            conn.execute("UPDATE selections SET codes = ?, updated_at = ? WHERE id = ?",
                         (json.dumps(order), int(time.time()), sel["id"]))
        db.log("shortlist", reader, self.client_ip(), self.headers.get("User-Agent"), "order:%s:%d" % (sel["id"], len(order)))
        return self.send_json(200, {"ok": True, "codes": order, "changed": True}, self.cors())

    def selection_scoring_off(self, sel):
        """True when a selection shows no scores (setting selections_unscored: a list of
        selection ids, or "all" while the scoring logic is being reworked, 2026-10-11)."""
        raw = db.setting("selections_unscored")
        # selections_scored: ids that keep their scores while the rest are paused (the sample campaign's selection).
        try:
            if int(sel["id"]) in set(int(x) for x in (db.setting("selections_scored") or [])):
                return False
        except (TypeError, ValueError):
            pass
        if raw == "all":
            return True
        try:
            return int(sel["id"]) in set(int(x) for x in (raw or []))
        except (TypeError, ValueError):
            return False

    def selection_scores(self, sel, objective=None, target=None):
        """{code: score} for every creator of a selection, worked out now from
        their analyses: one number against the selection's objective and target.
        Creators without a full analysis come back with score None."""
        import fit as fit_mod
        codes = json.loads(sel["codes"] or "[]")
        objective = objective or self.selection_objective(sel)
        target = target or self.selection_target(sel)
        wanted = sel["platform"] if "platform" in sel.keys() else None
        try:
            assign = json.loads((sel["platforms"] if "platforms" in sel.keys() else None) or "{}")
        except ValueError:
            assign = {}
        rows = {c["code"]: c for c in db.creators_by_codes(codes)}
        every = db.analyses_for(codes)
        records, typical = metrics.track_records()
        bench = metrics.benchmarks()
        out = {}
        for code in codes:
            c = rows.get(code)
            if c is None:
                continue
            mine = every.get(code) or {}
            rec = dict(records[code], typical_er=typical) if code in records else None

            def one(pl):
                doc = mine[pl]["data"]
                followers = doc.get("followers") or c["followers"]
                return fit_mod.score(doc, pl, c["followers"], objective=objective, target=target,
                                     band=metrics.band_of(followers), bench=bench, record=rec,
                                     creator_interest=c["interest"], creator=c)
            if not mine:
                # Nobody has analysed this creator: the same roster estimate the AI shortlist gave
                # them, so the page and the shortlist show one number (fix batch 5).
                out[code] = dict(matcher._roster_estimate(c, objective, target, analysis.canon_platform(wanted) if wanted else None),
                                 assigned="Auto")
                out[code] = self._brief_rules(c, out[code], "roster", target)
                continue
            import profile_pdf as _pp
            main = analysis.creator_platforms(c)
            tried = {pl: one(pl) for pl in mine}
            scored = [pl for pl in tried if tried[pl]["score"] is not None]
            # Which platform the creator is scored on: the one assigned for this selection; "Both"
            # shows both and ranks by the weaker; else the selection's platform; else the best, a
            # measured analysis before public numbers (as the AI shortlist chooses).
            assigned = (assign.get(code) or "").strip()
            sel_plat = analysis.canon_platform(wanted) if wanted else None
            if assigned == "Both" and len(scored) >= 2:
                shown = min(scored, key=lambda pl: tried[pl]["score"])
            elif assigned in tried:
                shown = assigned
            elif sel_plat in tried:
                shown = sel_plat
            else:
                full = [pl for pl in scored if not mine[pl]["data"].get("basic")]
                shown = max(full or scored or list(tried), key=lambda pl: (tried[pl]["score"] is not None, tried[pl]["score"] or 0,
                                                                          _pp.completeness(mine[pl]["data"]), pl == (main[0] if main else "")))
            # The brief's own requirements (country, product space), the same as on the shortlist.
            for pl in tried:
                if tried[pl]["score"] is not None:
                    tried[pl] = self._brief_rules(c, tried[pl], "basic" if tried[pl].get("basic") else "analysis", target)
            out[code] = dict(tried[shown])
            out[code]["assigned"] = assigned if (assigned in tried or (assigned == "Both" and len(scored) >= 2)) else "Auto"
            out[code]["platforms"] = {pl: tried[pl] for pl in tried if tried[pl]["score"] is not None}
            out[code]["available"] = sorted(tried)
            if out[code]["score"] is None:
                # Not enough public data to score from the analysis: the roster estimate stands in.
                est = matcher._roster_estimate(c, objective, target, sel_plat)
                if est.get("score") is not None:
                    out[code] = dict(self._brief_rules(c, est, "roster", target), assigned=out[code]["assigned"],
                                     platforms=out[code]["platforms"], available=out[code]["available"])
        return out

    def _brief_rules(self, c, s, basis, target):
        """``s`` (a fit result) with the brief's country and product-space rules applied."""
        if s.get("score") is None:
            return s
        return matcher.apply_rules(c, s, s["score"], basis, target)[2]

    def selection_suggest(self, query):
        """A suggested fit and role for one creator, from their analysis of a
        platform (the selection's, else the creator's own). The admin reads it,
        edits it and saves it; nothing is stored here."""
        import fit as fit_mod
        code = (query.get("code") or "").strip().upper()
        c = db.creator(code)
        if c is None:
            return self.send_json(404, {"note": "Unknown creator."})
        plat = analysis.canon_platform(query.get("p"))
        if plat:
            a = db.analysis(code, plat)
        else:
            a = db.analysis(code)
            plat = (a or {}).get("platform") or db.platforms_of(code)[0]
        obj = query.get("o") if query.get("o") in fit_mod.OBJECTIVES else "Balanced"
        followers = ((a["data"] if a else {}).get("followers")) or c["followers"]
        records, typical = metrics.track_records()
        rec = dict(records.get(code) or {}, typical_er=typical) if code in records else None
        out = fit_mod.suggest(a["data"] if a else None, plat, c["followers"], objective=obj,
                              band=metrics.band_of(followers), bench=metrics.benchmarks(), record=rec)
        out["platform"] = plat
        sel = {"codes": json.dumps([code]), "platform": None, "id": 0}
        tgt = {"country": query.get("tc"), "gender": query.get("tg"), "age": query.get("ta"), "category": query.get("tk")}
        sc = fit_mod.score(a["data"] if a else None, plat, c["followers"], objective=obj,
                           target=dict(fit_mod.DEFAULT_TARGET, **{k: v for k, v in tgt.items() if v}),
                           band=metrics.band_of(followers), bench=metrics.benchmarks(), record=rec,
                           creator_interest=c["interest"], creator=c)
        out["score"] = sc
        if sc["score"] is not None:
            out["fit"] = sc["tag"]
            out["reason"] = sc["conclusion"][:160]
            out["checks"] = [{"label": p["label"], "value": "%d%%" % round(p["s"] * 100), "bench": "weight %g" % p["w"],
                              "grade": 1 if p["s"] >= 0.75 else -1 if p["s"] <= 0.45 else 0} for p in sc["parts"]]
        return self.send_json(200, out)

    def analysis_find(self, query, form=None):
        """The creator picker's data. GET: search the roster (q, platform,
        only those still without an analysis, or the creators of a selection
        or campaign). POST `list`: turn pasted handles, links or names into
        creators. Answers JSON: the first rows to show, and every match to add
        in one click."""
        have = db.analysis_platforms()
        ap = analysis.canon_platform((query or {}).get("ap"))
        lacks = lambda c: (ap or analysis.creator_platforms(c)[0]) not in have.get(c["code"], {}) and \
            (not ap or ap in analysis.creator_platforms(c))
        if form is not None:
            res = self.analysis_resolver()
            found, missing = [], []
            for line in re.split(r"[\n,;]+", form.get("list") or ""):
                line = line.strip()
                if not line:
                    continue
                code, sug = res.resolve(line)
                (found if code else missing).append(code or line)
            rows = [c for c in db.list_creators() if c["code"] in set(found)]
        else:
            src = (query.get("source") or "").strip()
            rows = db.list_creators(search=query.get("q") or None)
            if src.startswith("selection:") and src[10:].isdigit():
                sel = db.selection(int(src[10:]))
                keep = set(json.loads(sel["codes"])) if sel else set()
                rows = [c for c in db.list_creators() if c["code"] in keep]
            elif src.startswith("campaign:") and src[9:].isdigit():
                keep = {r["cc_code"] for r in db.campaign_creators(int(src[9:]))}
                rows = [c for c in db.list_creators() if c["code"] in keep]
            if query.get("platform"):
                rows = [c for c in rows if (c["platform"] or "").lower() == query["platform"].lower()]
            if query.get("nohave") == "1":
                rows = [c for c in rows if lacks(c)]
            missing = []
        item = lambda c: {"code": c["code"], "name": c["name"], "handle": c["handle"] or "",
                          "platform": c["platform"] or "", "followers": c["followers"],
                          "has": sorted(have.get(c["code"], {})),
                          "platforms": analysis.creator_platforms(c)}
        return self.send_json(200, {"total": len(rows), "items": [item(c) for c in rows[:150]],
                                    "all": [[c["code"], c["name"]] for c in rows[:3000]],
                                    "missing": missing})

    def post_analysis_template(self):
        """A workbook prefilled with the creators of a selection, a campaign,
        everyone still without an analysis, or a pasted list of handles/names."""
        f = self.form_body()
        src = (f.get("source") or "").strip()
        everyone = db.list_creators()
        by_code = {c["code"]: c for c in everyone}
        codes, missing = [], []
        if src.startswith("selection:") and src[10:].isdigit():
            sel = db.selection(int(src[10:]))
            codes = json.loads(sel["codes"]) if sel else []
        elif src.startswith("campaign:") and src[9:].isdigit():
            codes = [r["cc_code"] for r in db.campaign_creators(int(src[9:]))]
        elif src == "codes":
            codes = [c for c in re.split(r"[\s,]+", f.get("codes") or "") if c]
        elif src == "missing":
            have = db.analysis_platforms()
            ap = analysis.canon_platform(f.get("platform"))
            codes = [c["code"] for c in everyone
                     if (ap or analysis.creator_platforms(c)[0]) not in have.get(c["code"], {})
                     and (not ap or ap in analysis.creator_platforms(c))][:500]
        else:
            res = self.analysis_resolver()
            for line in re.split(r"[\n,;]+", f.get("list") or ""):
                line = line.strip()
                if not line:
                    continue
                code, _ = res.resolve(line)
                if code:
                    codes.append(code)
                else:
                    missing.append(line)
        chosen = [by_code[c] for c in dict.fromkeys(codes) if c in by_code]
        if not chosen:
            return self.redirect("/analysis?e=" + urllib.parse.quote(
                "No creators found for that choice." + (" Not recognised: " + ", ".join(missing[:8]) if missing else "")) + "#prefilled")
        return self.send(200, analysis.template_xlsx(chosen, missing=missing, platform=f.get("platform")),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         [("Content-Disposition", 'attachment; filename="creator-analysis-%d-creators.xlsx"' % len(chosen))])

    def post_analysis_pdf(self):
        """Profile report PDFs -> analyses. Each file is matched to a creator by
        the handle in its name (report-<handle>-Oct-06-2026.pdf), then by a
        roster handle printed on its first page; what cannot be matched goes
        to the review screen instead of being refused."""
        import profile_pdf
        f = self.form_body(multi=("file",))
        parts = [p for p in (f.get("file") or []) if isinstance(p, dict) and p.get("data")]
        if not parts:
            return self.redirect("/analysis?e=" + urllib.parse.quote("Choose one or more profile report PDFs.") + "#pdf")
        if not profile_pdf.available():
            return self.redirect("/analysis?e=" + urllib.parse.quote(
                "The PDF reader is not installed on this server yet. Ask whoever deploys the admin to install it.") + "#pdf")
        res = self.analysis_resolver()
        picked = res.resolve((f.get("code") or "").strip())[0] if len(parts) == 1 else None
        want_plat = analysis.canon_platform(f.get("platform"))
        done, bad, held, kept = [], [], [], []
        for p in parts:
            name = p.get("filename") or "file.pdf"
            m = re.match(r"report-(.+?)-[A-Za-z]{3}-\d\d-\d{4}(?: ?\(\d+\))?\.pdf$", name)
            handle = m.group(1) if m else re.sub(r"\.pdf$", "", name, flags=re.I)
            code = picked
            seen_plat = want_plat or profile_pdf.detect_platform(p["data"])
            if not code:
                code = res.resolve(handle, seen_plat)[0]
            if not code:
                code = profile_pdf.sniff_creator(p["data"], res)
            if not code:
                held.append((name, p["data"]))
                continue
            try:
                got = profile_pdf.import_pdf(p["data"], code, handle, source="profile report PDF", platform=want_plat)
                (kept if got.get("_kept_existing") else done).append(code if not got.get("_kept_existing") else name)
            except Exception as ex:
                bad.append(name + " (" + str(ex)[:120] + ")")
        msg = "Imported %d %s: %s." % (len(done), "analysis" if len(done) == 1 else "analyses", ", ".join(done)) if done else ""
        if kept:
            msg += (" " if msg else "") + "%d repeat file%s skipped — a fuller copy of the same report was already saved (%s)." % (
                len(kept), "" if len(kept) == 1 else "s", ", ".join(kept[:4]) + (" …" if len(kept) > 4 else ""))
        if bad:
            msg += (" " if msg else "") + "Could not import: " + "; ".join(bad)
        if held:
            token = analysis.stash("pdf", held)
            return self.redirect("/analysis/review?t=%s&%s=%s" % (token, "ok" if not bad else "e", urllib.parse.quote(msg)))
        return self.redirect("/analysis?%s=%s#pdf" % ("e" if bad and not done else "ok", urllib.parse.quote(msg)))

    def post_analysis_upload(self):
        f = self.form_body()
        part = f.get("file")
        if not isinstance(part, dict) or not part.get("data"):
            return self.redirect("/analysis?e=" + urllib.parse.quote("Choose the filled-in template (.xlsx)."))
        head = part["data"][:8]
        wrong = ("That is a PDF report — drop it in Option A (PDF reports) above instead." if head.startswith(b"%PDF") else
                 "That is an old Excel (.xls) file. Open it and use Save As → Excel Workbook (.xlsx)." if head.startswith(b"\xd0\xcf\x11\xe0") else
                 "That looks like a CSV or text file. Open it in Excel and use Save As → Excel Workbook (.xlsx)." if not head.startswith(b"PK") else None)
        if wrong:
            return self.redirect("/analysis?e=" + urllib.parse.quote(wrong) + "#prefilled")
        try:
            docs, problems, unresolved = analysis.parse_workbook(part["data"], self.analysis_resolver())
        except Exception as ex:
            return self.redirect("/analysis?e=" + urllib.parse.quote(str(ex)[:200]))
        if unresolved:
            token = analysis.stash("xlsx", [(part.get("filename") or "analysis.xlsx", part["data"])])
            return self.redirect("/analysis/review?t=" + token)
        if not docs:
            return self.redirect("/analysis?e=" + urllib.parse.quote(
                "No creators with numbers found in that file. " + " ".join(problems[:5])))
        return self.save_analysis_docs(docs, problems)

    def save_analysis_docs(self, docs, problems, prefix=""):
        with db.connect() as conn:
            for (code, plat), d in docs.items():
                db.save_analysis(code, d, d.get("source") or "template upload", conn, platform=plat)
        msg = prefix + "Saved %d analys%s: %s." % (len(docs), "is" if len(docs) == 1 else "es",
                                                    ", ".join("%s (%s)" % k for k in list(docs)[:12]) + (" …" if len(docs) > 12 else ""))
        if problems:
            msg += " Skipped: " + " ".join(problems[:6])
        return self.redirect("/analysis?ok=" + urllib.parse.quote(msg))

    def analysis_review_get(self, query):
        h = analysis.held(query.get("t"))
        if not h:
            return self.redirect("/analysis?e=" + urllib.parse.quote("That upload has expired — please upload it again."))
        kind, files = h
        res = self.analysis_resolver()
        creators = db.list_creators()
        if kind == "xlsx":
            docs, problems, unresolved = analysis.parse_workbook(files[0][1], res)
            items = [(k, [res.describe(c) for c in sug], (res.describe(sug[0]) if len(sug) == 1 else ""))
                     for k, sug in unresolved.items()]
            matched = len(docs)
        else:
            items, matched = [], 0
            for name, _ in files:
                m = re.match(r"report-(.+?)-[A-Za-z]{3}-\d\d-\d{4}", name)
                guess = m.group(1) if m else re.sub(r"\.pdf$", "", name, flags=re.I)
                sug = res.resolve(guess)[1]
                items.append((name, [res.describe(c) for c in sug], (res.describe(sug[0]) if len(sug) == 1 else "")))
        return self.send(200, views.analysis_review_page(
            kind, query["t"], items, matched, creators, res, query.get("e"), query.get("ok")))

    def post_analysis_review(self):
        f = self.form_body()
        token = f.get("t")
        h = analysis.held(token)
        if not h:
            return self.redirect("/analysis?e=" + urllib.parse.quote("That upload has expired — please upload it again."))
        kind, files = h
        res = self.analysis_resolver()
        remember = f.get("remember") == "1"
        picks, bad = {}, []
        n = 0
        while ("key_%d" % n) in f:
            key, raw = f["key_%d" % n], (f.get("pick_%d" % n) or "").strip()
            n += 1
            if not raw:
                picks[key] = ""
                continue
            code = analysis.code_from_pick(raw)
            if code not in res.label:
                bad.append(key)
                picks[key] = ""
            else:
                picks[key] = code
        if kind == "xlsx":
            docs, problems, still = analysis.parse_workbook(files[0][1], res, picks)
            problems += ["%s was not recognised — skipped." % k for k in bad]
            problems += ["%s skipped." % k for k in still]
            if remember:
                for key, code in picks.items():
                    if code:
                        db.remember_alias(analysis.norm(key), code)
            analysis.release(token)
            if not docs:
                return self.redirect("/analysis?e=" + urllib.parse.quote("Nothing to save. " + " ".join(problems[:5])))
            return self.save_analysis_docs(docs, problems)
        if not any(picks.values()):
            return self.redirect("/analysis/review?t=%s&e=%s" % (token, urllib.parse.quote(
                "Nothing is chosen yet. For each file click the creator it belongs to (or type their name), then press Save.")))
        import profile_pdf
        done, failed = [], list(bad)
        for name, data in files:
            code = picks.get(name)
            if not code:
                continue
            m = re.match(r"report-(.+?)-[A-Za-z]{3}-\d\d-\d{4}", name)
            handle = m.group(1) if m else None
            try:
                profile_pdf.import_pdf(data, code, handle, source="profile report PDF", platform=analysis.canon_platform(f.get("platform")))
                done.append(code)
                if remember and handle:
                    db.remember_alias(analysis.norm(handle), code)
            except Exception as ex:
                failed.append(name + " (" + str(ex)[:100] + ")")
        analysis.release(token)
        msg = "Imported %d %s: %s." % (len(done), "analysis" if len(done) == 1 else "analyses", ", ".join(done)) if done else ""
        if failed:
            msg += (" " if msg else "") + "Not imported: " + "; ".join(failed)
        return self.redirect("/analysis?%s=%s" % ("ok" if done else "e", urllib.parse.quote(msg or "Nothing was imported.")))

    def post_analysis_save(self):
        f = self.form_body()
        code = (f.get("code") or "").strip().upper()
        if db.creator(code) is None:
            return self.redirect("/analysis?e=" + urllib.parse.quote("Unknown creator code."))
        try:
            doc = analysis.clean_json(json.loads(f.get("json") or "{}"))
        except ValueError as ex:
            return self.redirect("/analysis?q=%s&e=%s" % (code, urllib.parse.quote(str(ex))))
        plat = analysis.canon_platform(f.get("platform")) or analysis.canon_platform(doc.get("platform")) or db.platforms_of(code)[0]
        db.save_analysis(code, doc, doc.get("source") or "pasted JSON", platform=plat)
        return self.redirect("/analysis?q=%s&p=%s&ok=%s" % (code, plat, urllib.parse.quote("%s analysis saved for %s." % (plat, code))))

    def post_analysis_delete(self):
        f = self.form_body()
        code = (f.get("code") or "").strip().upper()
        plat = analysis.canon_platform(f.get("platform"))
        db.delete_analysis(code, plat)
        return self.redirect("/analysis?ok=" + urllib.parse.quote("%sanalysis removed for %s." % ((plat + " ") if plat else "", code)))

    def api_creator(self, code):
        """One creator for the analysis page: the public card facts always,
        the full analysis when one is uploaded."""
        code_id = self.viewer_code_id()
        if code_id is None:
            return self.send_json(401, {"ok": False}, self.cors())
        r = db.creator(code)
        if r is None or not r["active"]:
            return self.send_json(404, {"ok": False}, self.cors())
        every = db.analyses(code)
        # The platforms this creator is on, plus any that has an analysis on file.
        plats = list(db.platforms_of(code))
        plats += [p for p in every if p not in plats]
        asked = db.open_requests(code, code_id)
        db.log("view", code_id, self.client_ip(), self.headers.get("User-Agent"), "analysis:" + code)
        card = {"code": r["code"], "name": r["name"], "tier": r["tier"], "city": r["city"],
                "nationality": r["nationality"], "interest": r["interest"], "followers": r["followers"],
                "photo_url": links.photo(r["photo"]) if r["photo"] else None,
                "profiles": db.split_profiles(r["profiles"]),
                "band": metrics.band_of(r["followers"])}
        # Analysis gating: the headline numbers are free; the rest is for a client the team
        # has unlocked it for. Anyone else gets sample data drawn here, never the real values.
        # Never locked for anyone on the HelloVoice team (owner, 2026-10-15): an admin session, or a portal
        # sign-in with an admin email, sees every analysis without the "Show locked data" switch.
        # A key account manager never sees a creator's locked analysis (owner, 2026-10-20, item 174).
        staff = ((self.admin_like() or (bool(self.admin()) and not kam_scope.is_kam(self.admin())) or self.staff_viewer())
                 and self.kam_clients() is None)
        gate = {"state": "unlocked"} if staff else gating.state(code_id, code)
        gate["headline"] = gating.headline(card, every)
        import sample_analysis                       # item 39: is "See a sample full analysis" on?
        gate["sample_full"] = sample_analysis.available()
        if staff:
            gate["admin"] = True
        if gate["state"] != "unlocked":
            gate["sample"] = gating.sample(code, plats[0] if plats else None)
            return self.send_json(200, {"ok": True, "creator": card, "platforms": plats, "analyses": {},
                                        "requested": [], "gate": gate, "benchmarks": metrics.benchmarks()},
                                  self.cors() + [("Cache-Control", "no-store")])
        return self.send_json(200, {"ok": True, "creator": card,
                                    "platforms": plats,
                                    "analyses": {p: analysis.with_media_urls(a["data"], r["code"], BASE)
                                                 for p, a in every.items()},
                                    "requested": asked, "gate": gate,
                                    "benchmarks": metrics.benchmarks()},
                              self.cors() + [("Cache-Control", "no-store")])

    def api_creator_media(self, code, name):
        """A picture from a creator's analysis — post cover, photo or brand
        logo — for a viewer who has unlocked the catalogue."""
        viewer = self.viewer_code_id()
        if viewer is None:
            return self.send(401, b"", "text/plain")
        # Post covers and brand logos are part of the locked analysis.
        if not self.admin_like() and not gating.unlocked(viewer, str(code or "").strip().upper()):
            return self.send(403, b"", "text/plain")
        f = analysis.media_path(code, name)
        if f is None:
            return self.send(404, b"", "text/plain")
        data = f.read_bytes()
        kind = uploads.image_kind(data[:16]) or "jpg"
        return self.send(200, data, "image/" + ("jpeg" if kind == "jpg" else kind),
                         [("Cache-Control", "private, max-age=604800")])

    def api_creator_request(self):
        code_id = self.viewer_code_id()
        if code_id is None:
            return self.send_json(401, {"ok": False}, self.cors())
        code = (self.json_body().get("code") or "").strip().upper()
        c = db.creator(code)
        if c is None:
            return self.send_json(404, {"ok": False}, self.cors())
        plat = analysis.canon_platform(self.json_body().get("platform")) or db.platforms_of(code)[0]
        ok, why = gating.request(code_id, code, plat)
        if not ok:
            msg = {"outside": "Add this creator to one of your selections first, then ask your account manager.",
                   "unlocked": "The full analysis is already open for you."}.get(why, "This can't be requested here.")
            return self.send_json(403 if why == "outside" else 400, {"ok": False, "reason": why, "message": msg}, self.cors())
        db.log("shortlist", code_id, self.client_ip(), self.headers.get("User-Agent"), "analysis request:%s:%s" % (code, plat))
        if why != "already":
            u = self.person_user(code_id)
            sels = gating.selections_with(code_id, code)
            import notify
            # Item 195 (owner, 2026-10-20): the request waits in the Analyses inbox on /account/ for an
            # admin to approve (opens it to this person only) or reject; the KAM is told as before.
            notify.send("analysis", ["%s requested the full analysis of %s (%s)." % (
                ((u["name"] or u["email"]) + ", " + (u["company"] or "")) if u else "A client", c["name"], code),
                "In: %s" % ", ".join(x["name"] for x in sels[:3]),
                "Approve or reject it in Analyses on your HELVi Connect profile."],
                kam=u["kam"] if u is not None else None)
        return self.send_json(200, {"ok": True, "gate": gating.state(code_id, code)}, self.cors())

    def post_campaign_delete(self):
        cid = (self.form_body().get("id") or "").strip()
        if cid.isdigit():
            db.delete_campaign(int(cid))
        return self.redirect("/campaigns?ok=" + urllib.parse.quote("Campaign deleted."))

    # ------------------------------------------------- competitor evidence --

    def post_evidence(self, path, who):
        f = self.form_body(multi=("codes",))
        one = lambda k: (f.get(k)[0] if isinstance(f.get(k), list) else f.get(k)) or ""
        pid = kam_scope._int(one("id") or one("pack_id"))
        pk = evidence.pack(pid) if pid is not None else None
        back = "/evidence/view?id=%d" % pid if pk is not None else "/evidence"
        go = lambda key, msg, extra="": self.redirect(back + ("&" if "?" in back else "?") + key + "=" + urllib.parse.quote(msg) + extra)

        def sel_ok(sid, code_id):
            """A selection may only carry a pack of its own client."""
            if sid is None:
                return True
            sel = db.selection(sid)
            return sel is not None and (code_id is None or sel["code_id"] == code_id)

        if path == "/evidence/import":
            part = f.get("file")
            if not isinstance(part, dict) or not part.get("data"):
                return go("e", "Choose the filled Excel template (or an evidence-pack JSON file).")
            try:
                if pk is not None:
                    _, n, m = evidence.import_pack(part["data"], None, pk["code_id"], pack_id=pk["id"], by=who["email"])
                    return go("ok", "Added %d posts (%d matched to the roster)." % (n, m))
                code_id, sid = kam_scope._int(one("code_id")), kam_scope._int(one("selection_id"))
                if code_id is None:
                    return go("e", "Choose the client this pack is for.")
                if not sel_ok(sid, code_id):
                    return go("e", "That selection belongs to another client.")
                title = one("title").strip()[:120]
                # The same client, selection and title again is the same pack: update it, never a second copy.
                same = [r for r in evidence.list_packs() if r["code_id"] == code_id and r["selection_id"] == sid
                        and (r["title"] or "").strip().lower() == title.lower()]
                if same:
                    _, n, m = evidence.import_pack(part["data"], None, code_id, pack_id=same[0]["id"], by=who["email"])
                    return self.redirect("/evidence/view?id=%d&ok=%s" % (same[0]["id"], urllib.parse.quote(
                        "Updated the existing pack: %d posts; %d matched to roster creators." % (n, m))))
                new, n, m = evidence.import_pack(part["data"], title, code_id, sid, by=who["email"])
            except ValueError as ex:
                return go("e", str(ex))
            return self.redirect("/evidence/view?id=%d&ok=%s" % (new, urllib.parse.quote(
                "Imported %d posts; %d matched to roster creators." % (n, m))))
        if pk is None:
            return self.redirect("/evidence?e=" + urllib.parse.quote("That pack is gone."))
        if path == "/evidence/save":
            sid = kam_scope._int(one("selection_id"))
            if not sel_ok(sid, pk["code_id"]):
                return go("e", "That selection belongs to another client.")
            evidence.save(pk["id"], one("title").strip()[:120] or pk["title"], sid, one("client_visible") == "1")
            return go("ok", "Saved.")
        if path == "/evidence/rematch":
            return go("ok", "%d posts matched to roster creators." % evidence.rematch(pk["id"]))
        if path == "/evidence/add":
            codes = [c.strip().upper() for c in (f.get("codes") or []) if c.strip()]
            if pk["selection_id"] is None:
                return go("e", "File this pack under a selection first.")
            n = evidence.add_to_selection(pk, codes)
            brand = one("back")
            return go("ok", "Added %d creator%s to the selection." % (n, "" if n == 1 else "s"),
                      ("&brand=" + urllib.parse.quote(brand)) if brand else "")
        if path == "/evidence/roster":
            added, _ = evidence.add_to_roster(pk, who["email"])
            return go("ok", "Added %d creator%s to the roster, hidden and marked for analysis." % (len(added), "" if len(added) == 1 else "s"))
        if path == "/evidence/delete":
            evidence.delete(pk["id"])
            return self.redirect("/evidence?ok=" + urllib.parse.quote("Pack deleted."))
        return self.send(404, "Not found", "text/plain; charset=utf-8")

    def api_evidence_add(self):
        """Market Intelligence: put a creator from the selection's evidence pack into the selection.
        For HelloVoice (and a KAM on her client) and the selection's owner; colleagues only look."""
        b = self.json_body()
        token = str(b.get("token") or "")
        sel = db.selection(token=token) if token else None
        if sel is None:
            return self.send_json(404, {"ok": False, "reason": "unknown"}, self.cors())
        staff = self.admin_like_for(sel["code_id"], sel["id"])
        reader = self.selection_viewer(token)
        if not staff and not (reader is not None and portal.may_edit(int(reader), sel, db.admin_code_id())):
            return self.send_json(403, {"ok": False, "reason": "not_owner"}, self.cors())
        pk = evidence.for_selection(sel["id"], client_only=not staff)
        if pk is None:
            return self.send_json(404, {"ok": False, "reason": "unknown"}, self.cors())
        with history.tracked("selection", sel["id"], "Added @%s from Market Intelligence" % str(b.get("handle") or "")[:40]):
            code = evidence.add_by_handle(pk, sel, str(b.get("handle") or ""))
        if code is None:
            return self.send_json(404, {"ok": False, "reason": "not_on_roster"}, self.cors())
        return self.send_json(200, {"ok": True, "code": code}, self.cors())

    def api_evidence_request(self):
        """Market Intelligence: ask HelloVoice for a creator the client cannot pick, either one marked
        Unavailable on the selection or a competitor's creator who is not on the roster yet. Anyone who
        may open the selection can ask; it reaches the account manager and the notify list."""
        b = self.json_body()
        token = str(b.get("token") or "")
        sel = db.selection(token=token) if token else None
        if sel is None:
            return self.send_json(404, {"ok": False, "reason": "unknown"}, self.cors())
        staff = self.admin_like_for(sel["code_id"], sel["id"]) or (self.staff_viewer() and self.kam_clients() is None)
        cid = None
        if not staff:
            cid = self.link_code("s:" + token) or self.signed_in_client()
            if cid is None or (not portal.opens(int(cid), sel)
                               and int(cid) != db.admin_code_id()):
                return self.send_json(401, {"ok": False, "reason": "link"}, self.cors())
        pk = evidence.for_selection(sel["id"], client_only=not staff)
        if pk is None:
            return self.send_json(404, {"ok": False, "reason": "unknown"}, self.cors())
        handle = str(b.get("handle") or "").lower().lstrip("@")[:60]
        kind = "unavailable" if b.get("kind") == "unavailable" else "roster"
        with evidence._conn() as conn:
            r = conn.execute("SELECT name, code FROM evidence_posts WHERE pack_id = ? AND handle = ? LIMIT 1", (pk["id"], handle)).fetchone()
        if r is None:
            return self.send_json(404, {"ok": False, "reason": "unknown"}, self.cors())
        db.log("shortlist", cid, self.client_ip(), self.headers.get("User-Agent"), "creator request:%s:%s" % (kind, handle))
        if not staff:
            u = self.person_user(int(cid)) if cid is not None else None
            who = ((u["name"] or u["email"]) + ", " + (u["company"] or "")) if u else "An access-code client"
            what = ("is marked Unavailable on the selection; they ask you to check again" if kind == "unavailable"
                    else "is not on the roster yet; they ask you to sign them")
            import notify
            notify.send("creator_request", ["%s asked for %s (@%s) from Market Intelligence." % (who, r["name"] or handle, handle),
                                            "The creator %s." % what, "Selection: %s" % sel["name"]],
                        kam=u["kam"] if u is not None else None)
        return self.send_json(200, {"ok": True}, self.cors())

    def api_evidence(self, token, creator=None, thumb_post=None, as_map=False):
        """The competitor evidence filed under a selection, for its client page — only when an admin
        switched it on for the client, and behind the same link check as /api/selection. With
        ``creator`` (a code in the selection): that creator's Track record."""
        sel = db.selection(token=token) if token else None
        if sel is None:
            return self.send_json(404, {"ok": False, "reason": "unknown"}, self.cors())
        staff = self.admin_like_for(sel["code_id"], sel["id"]) or (self.staff_viewer() and self.kam_clients() is None)
        public = False
        if not staff:
            cid = self.link_code("s:" + token) or self.signed_in_client()
            if cid is None or (not portal.opens(int(cid), sel)
                               and int(cid) != db.admin_code_id()):
                if self.public_selection(token) is None:
                    return self.send_json(401, {"ok": False, "reason": "link"}, self.cors())
                public = True                   # public read-only link: the client's view, no actions
        pk = evidence.for_selection(sel["id"], client_only=not staff)
        if pk is None:
            if creator is not None or thumb_post is not None or as_map:
                return self.send_json(404, {"ok": False, "reason": "unknown"}, self.cors())
            return self.send_json(200, {"ok": True, "evidence": None}, self.cors())
        codes = json.loads(sel["codes"] or "[]")
        if as_map:
            import selstatus
            status = selstatus.of(sel["id"])
            # Rejected creators stay on the map (owner, 2026-10-15): dimmed, with a Rejected tag, and in the totals.
            rejected = {c for c, st in status.items() if st["s"] == "rejected"}
            locked = {c for c, st in status.items() if st["s"] == "unavailable"}
            approved = {c for c, st in status.items() if st["s"] == "approved"}
            reader = None if public else self.selection_viewer(sel["token"])
            out = evidence.map_payload(pk, codes, self.selection_objective(sel), (), locked, rejected, approved)
            out["can_add"] = bool(staff or (reader is not None and portal.may_edit(int(reader), sel, db.admin_code_id())))
            # Approve / Reject on the panel (owner, 2026-10-15): the same rule as the status API, so only the
            # selection's owner and HelloVoice get the buttons; everyone else reads the status.
            out["role"] = self.selection_role(sel, reader)
            out["can_decide"] = out["role"] in ("admin", "owner")
            out["reasons"] = {c: st.get("reason") or "" for c, st in status.items() if st["s"] == "rejected"}
            out["preview"] = bool(staff and not pk["client_visible"])
            if public:
                out = self.public_strip(out)
                out["can_add"] = False
                out["can_decide"] = False
                out["role"] = "viewer"
            return self.send_json(200, {"ok": True, "map": out}, self.cors())
        if thumb_post is not None:
            url = evidence.post_for_thumb(pk["id"], thumb_post)
            got = evidence.thumb(url) if url else None
            if not got:
                return self.send(404, b"", "text/plain")
            return self.send(200, got[0], "image/" + ("jpeg" if got[1] == "jpg" else got[1]),
                             [("Cache-Control", "private, max-age=604800")])
        if creator is not None:
            tr = evidence.creator_payload(pk, creator) if creator in codes else None
            if tr is None:
                return self.send_json(404, {"ok": False, "reason": "unknown"}, self.cors())
            if public:
                tr = self.public_strip(tr)
            return self.send_json(200, {"ok": True, "creator": tr, "preview": bool(staff and not pk["client_visible"])}, self.cors())
        out = evidence.client_payload(pk, codes)
        out["preview"] = bool(staff and not pk["client_visible"])
        if public:
            out = self.public_strip(out)
        return self.send_json(200, {"ok": True, "evidence": out}, self.cors())

    @staticmethod
    def selection_engagement(codes, by, platform=None):
        """Projected engagements per post per creator (likes + comments), for an engagement or conversion
        objective (owner, 2026-10-15): minimum = their typical (median, else average) likes + comments, best
        case = their best recent post's, capped at three times typical. No numbers: 1-3% of followers, marked
        estimated. {code: [low, high, estimated]}, the same shape as selection_reach."""
        docs = db.analyses_for(codes)
        out = {}
        for c in codes:
            best = None
            for plat, row in (docs.get(c) or {}).items():
                if platform and str(plat).lower() != str(platform).lower():
                    continue
                d = row.get("data") if isinstance(row, dict) else None
                if not isinstance(d, dict):
                    continue
                lk = d.get("median_likes") if d.get("median_likes") is not None else d.get("avg_likes")
                cm = d.get("median_comments") if d.get("median_comments") is not None else d.get("avg_comments")
                if not isinstance(lk, (int, float)) or lk <= 0:
                    continue
                lo = lk + (cm if isinstance(cm, (int, float)) else 0)
                tops = [(p.get("likes") or 0) + (p.get("comments") or 0) for p in (d.get("top_posts") or []) if isinstance(p, dict)]
                hi = min(max(tops), 3 * lo) if tops else lo * 1.5
                hi = max(hi, lo)
                if best is None or lo > best[0]:
                    best = [int(lo), int(hi), False]
            if best is None:
                fol = int((by.get(c) or {})["followers"] or 0) if by.get(c) is not None and "followers" in by[c].keys() else 0
                if fol:
                    best = [int(fol * 0.01), int(fol * 0.03), True]
            if best:
                out[c] = best
        return out

    @staticmethod
    def selection_reach(codes, by, platform=None):
        """Projected views per creator for the selection's reach range (owner, 2026-10-15): minimum = their
        typical (median) views, best case = their best recent post (top of the last 25), capped at the larger of
        their followers and twice their typical views. A creator with no view numbers falls back to 5-15% of followers and is marked estimated.
        {code: [low, high, estimated]}; the page adds up the creators still in play."""
        docs = db.analyses_for(codes)
        out = {}
        for c in codes:
            best = None
            for plat, row in (docs.get(c) or {}).items():
                if platform and str(plat).lower() != str(platform).lower():
                    continue
                d = row.get("data") if isinstance(row, dict) else None
                if not isinstance(d, dict):
                    continue
                lo = d.get("median_views") or d.get("avg_reel_plays") or d.get("avg_views")
                if not isinstance(lo, (int, float)) or lo <= 0:
                    continue
                series = [v for v in (d.get("views_series") or []) if isinstance(v, (int, float))]
                hi = max(series) if series else (d.get("views_p75") or lo) * 1.5
                fol = d.get("followers") or 0
                if fol:
                    hi = min(hi, max(fol, 2 * lo))     # a reel can out-reach the follower count, never wildly
                hi = max(hi, lo)
                if best is None or lo > best[0]:
                    best = [int(lo), int(hi), False]
            if best is None:
                fol = int((by.get(c) or {})["followers"] or 0) if by.get(c) is not None and "followers" in by[c].keys() else 0
                if fol:
                    best = [int(fol * 0.05), int(fol * 0.15), True]
            if best:
                out[c] = best
        return out

    def api_selection(self, token, name=None, codes=None):
        """A priced selection, for the client's page — by its token, or by the
        name and creators of a link the client already holds. Behind the same
        passcode as the roster: the link alone shows nothing."""
        viewer = self.viewer_code_id()
        public = False
        if token:
            # A selection its client deleted is "unknown" to clients; HelloVoice still opens it.
            sel = db.selection(token=token, deleted=bool(self.admin_like() or self.kam_clients() is not None))
            # An admin opens every selection, whether signed in to the admin or to the portal with an admin email.
            staff = sel is not None and (self.admin_like_for(sel["code_id"], sel["id"])
                                         or (self.staff_viewer() and self.kam_clients() is None))
            if sel is not None and sel["deleted_at"] and not staff:
                sel = None                      # a KAM opens deleted selections of her own clients only
            # Prices agreed with one client are for that client. The token is
            # in a link, and a link travels; the code typed FOR THIS LINK is what
            # identifies who is reading it. Admins signed in open any link.
            if sel is not None and not staff:
                cid = self.link_code("s:" + token) or self.signed_in_client()
                if cid is None or (not portal.opens(int(cid), sel)
                                   and int(cid) != db.admin_code_id()):
                    if self.public_selection(token) is None:
                        return self.send_json(401, {"ok": False, "reason": "link"}, self.cors())
                    public = True               # public read-only link (public_links): anyone, no prices
        elif not viewer:
            return self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
        elif codes:
            try:
                viewer_id = int(viewer)
            except (TypeError, ValueError):
                viewer_id = None
            sel = db.selection_for_link(name or "", codes, viewer_id)
        else:
            sel = None
        if sel is None:
            return self.send_json(404, {"ok": False, "reason": "unknown"}, self.cors())
        bands = db.tier_prices()
        listed = json.loads(sel["codes"] or "[]")
        by = {c["code"]: c for c in db.creators_by_codes(listed, active_only=True)}
        codes = [c for c in listed if c in by]
        own = db.zero_prices(json.loads(sel["codes"] or "[]")) if db.zero_priced(sel["id"]) else json.loads(sel["prices"] or "{}")
        platform = sel["platform"] if "platform" in sel.keys() else None
        prices = {}
        for c in codes:
            p = own.get(c) or db.price_for(by[c], bands, platform)
            if p:
                prices[c] = list(p)
        total = ([sel["total_from"], sel["total_to"]]
                 if sel["total_from"] is not None else None)
        out = {"ok": True, "name": sel["name"], "codes": codes,
                                    "prices": prices, "total": total,
                                    "platform": platform,
                                    "tags": {k: v for k, v in json.loads((sel["tags"] if "tags" in sel.keys() else None) or "{}").items() if k in by and k in codes},
                                    "segments": {k: v for k, v in json.loads((sel["segments"] if "segments" in sel.keys() else None) or "{}").items() if k in by and k in codes},
                                    "group_by": (sel["group_by"] if "group_by" in sel.keys() else None) or "",
                                    "tag_subs": db.setting("tag_subs") or [],
                                    "brief": {"objective": self.selection_objective(sel), "target": self.selection_target(sel),
                                              "client": self.selection_client(sel)},
                                    "scores": {k: {"score": v["score"], "tag": v["tag"], "score_range": v.get("score_range"),
                                                   "tag_range": v.get("tag_range"), "metrics": v.get("metrics") or [], "strengths": v["strengths"],
                                                   "watchouts": v["watchouts"], "conclusion": v["conclusion"],
                                                   "parts": [{"label": p["label"], "s": p["s"]} for p in v["parts"]],
                                                   "platform": v["platform"], "objective": v["objective"],
                                                   "basic": bool(v.get("basic")), "checks": v.get("checks") or [],
                                                   "confidence": v.get("confidence"), "reach_followers": v.get("reach_followers"),
                                                   "limited_data": bool(v.get("limited_data")),
                                                   "assigned": v.get("assigned") or "Auto", "available": v.get("available") or [],
                                                   "platforms": {pl: {"score": x["score"], "tag": x["tag"], "score_range": x.get("score_range"),
                                                                      "tag_range": x.get("tag_range"), "metrics": x.get("metrics") or [], "strengths": x["strengths"],
                                                                      "watchouts": x["watchouts"], "conclusion": x["conclusion"],
                                                                      "parts": [{"label": p["label"], "s": p["s"]} for p in x["parts"]],
                                                                      "platform": x["platform"], "objective": x["objective"],
                                                                      "basic": bool(x.get("basic")), "checks": x.get("checks") or [],
                                                                      "confidence": x.get("confidence"), "reach_followers": x.get("reach_followers"),
                                                                      "limited_data": bool(x.get("limited_data"))}
                                                                 for pl, x in (v.get("platforms") or {}).items()}}
                                               for k, v in self.selection_scores(sel).items()},
                                    "client_tags": {k: v for k, v in json.loads((sel["client_tags"] if "client_tags" in sel.keys() else None) or "{}").items() if k in by and k in codes},
                                    "client_platforms": {k: v for k, v in json.loads((sel["client_platforms"] if "client_platforms" in sel.keys() else None) or "{}").items() if k in by and k in codes},
                                    "verdicts": {k: v for k, v in json.loads((sel["verdicts"] if "verdicts" in sel.keys() else None) or "{}").items() if k in by and k in codes},
                                    "currency": (sel["currency"] if "currency" in sel.keys() else None) or "SAR",
                                    "fx": fx.rates(),
                                    "token": sel["token"]}
        if not self.selection_has_objective(sel):
            # No campaign objective: no scores at all, and the page asks for the objective.
            out["scores"] = {}
            out["needs_objective"] = True
            out["brief"]["objective"] = None
        if self.selection_scoring_off(sel):
            # Unscored on purpose (owner decision 2026-10-11): the page shows the editorial
            # fit tag only, never a score, and does not ask for an objective. A creator with
            # no fit tag of the admin's reads "Matching".
            out["scores"] = {}
            out["needs_objective"] = False
            out["scoring_off"] = True
            out["verdicts"] = {k: dict(out["verdicts"].get(k) or {}) for k in set(out["verdicts"]) | set(codes)}
            for v in out["verdicts"].values():
                if not v.get("fit"):
                    v["fit"] = "Matching"
        # Scores gate (owner, 2026-10-15): on a selection HelloVoice made, the client sees no scores until
        # HelloVoice publishes them; HelloVoice (and the client's KAM) always see them, marked as a preview.
        reader0 = None if public else self.selection_viewer(sel["token"])
        # Clients and key account managers never see scores, never preview them and never publish or hide
        # them (owner, 2026-10-20, item 174): the scores are HelloVoice admins' alone, checked here.
        team = ((not public) and (self.selection_role(sel, reader0) == "admin" or self.admin_like_for(sel["code_id"], sel["id"]))
                and self.kam_clients() is None)
        gated = self.scores_gated(sel)
        out["scores_gate"] = {"applies": self.scores_gate_applies(sel), "published": not gated, "team": bool(team),
                              "analysis": bool(sel["analysis_published"] if "analysis_published" in sel.keys() else 0) if team else False}
        import selfilters as _sf             # item 248: the "Client sees" switches, owner and admin accounts only
        out["scores_gate"]["can_publish"] = bool(team) and _sf.can_publish(self)
        # Item 3b (Bido, 25 Oct 2026): arranging the cards by hand on the selection page is for
        # HelloVoice owner and admin accounts only — the same gate as the "Client sees" switches.
        out["can_arrange"] = bool(team) and _sf.can_publish(self)
        if not team and gated:
            # No score and no fit badge (or its reason) for a client or a KAM until HelloVoice switches
            # "Scores & fit" on for the client (Bido, 2026-10-25; it was "never" since 2026-10-20).
            out["scores"] = {}
            out["scores_pending"] = False
            out["verdicts"] = {k: {kk: vv for kk, vv in (v or {}).items() if kk not in ("fit", "reason")}
                               for k, v in (out.get("verdicts") or {}).items()}
        try:
            out["reach"] = self.selection_reach(codes, by, platform)
        except Exception:
            out["reach"] = {}
        # Views for awareness, likes + comments for engagement / conversion (owner, 2026-10-15).
        import fit as _fit_m
        out["metric"] = _fit_m.metric_for(sel["objective"] if "objective" in sel.keys() else None)
        try:
            out["engagement"] = self.selection_engagement(codes, by, platform) if out["metric"] == "engagement" else {}
        except Exception:
            out["engagement"] = {}
        reader = None if public else self.selection_viewer(sel["token"])
        # Analysis gating: a score keeps its number, but the evidence that quotes locked
        # figures (audience shares, fake followers) waits until that creator is unlocked.
        open_ = None if (not public) and (self.admin_like() or portal.sample_member(reader, sel)) else gating.unlocked_set(reader, codes)
        if open_ is not None:
            out["scores"] = {k: (v if k in open_ else gating.redact_score(v)) for k, v in out["scores"].items()}
        out.update(self.selection_status_payload(sel, codes, reader, by))
        try:                                    # item 242: what the new selection filters read
            import selfilters
            out["facts"] = selfilters.facts(codes, by, bool(team))
        except Exception:
            out["facts"] = {}
        import selrename        # item 173: who may rename (owner, KAM, HelloVoice; never a colleague or an invitee)
        out["can_rename"] = (not public) and bool(sel["token"]) and selrename.client_may(reader, sel, db.admin_code_id())
        if public:
            # Read-only for anyone: no prices, totals or costs, no owner name, no actions.
            out = self.public_strip(out)
            out.pop("total", None)
            out["owner"] = None
            if isinstance(out.get("lifecycle"), dict):
                out["lifecycle"]["owner"] = ""
            out["role"] = "viewer"
            out["public"] = True
            db.log("view", None, self.client_ip(), self.headers.get("User-Agent"), "public selection:" + sel["name"][:60])
        return self.send_json(200, out, self.cors())

    def selection_role(self, sel, reader):
        """admin (HelloVoice: any status), owner (the client it belongs to: approve and
        reject) or viewer (a colleague or a link holder: look only)."""
        if self.admin_like() or (reader is not None and int(reader) == db.admin_code_id()):
            return "admin"
        if portal.sample_member(reader, sel) and not self.as_client():
            return "admin"           # the sample selection: every control on for BlueHolding and HelloVoice accounts
        if self.staff_viewer() and self.kam_clients() is None:
            return "admin"           # HelloVoice staff signed in to the portal: same controls as the admin
        if reader is not None and sel["code_id"] is not None and portal.owns(int(reader), sel["code_id"]):
            return "owner"
        if reader is not None and db.selection_granted(sel["id"], reader):
            return "owner"           # granted this selection (owner, 2026-10-15): the client's own controls
        return "viewer"

    def selection_status_payload(self, sel, codes, reader, by=None):
        """What the selection page needs for statuses: each creator's, the summary bar,
        what this reader may do, and the price of a replacement search."""
        st = {k: v for k, v in selstatus.of(sel["id"]).items() if k in codes}
        if by is None:
            by = {c["code"]: c for c in db.creators_by_codes(codes, active_only=True)}
        tiers = {c: by[c]["tier"] for c in codes if c in by}
        owner = portal.user_for_code(sel["code_id"]) if sel["code_id"] else None
        role = self.selection_role(sel, reader)
        import lifecycle
        return {"status": st, "status_counts": selstatus.counts(codes, st, tiers), "role": role,
                "lifecycle": lifecycle.client_payload(sel, role),
                "owner": (owner["name"] if owner is not None else None),
                "kam": ((owner["kam"] or "").split("<")[0].strip() if owner is not None and owner["kam"] else None),
                "replace_cost": portal.price_of(int(reader), "replace") if reader is not None else portal.costs().get("replace", 2),
                "alike_cost": portal.price_of(int(reader), "alike") if reader is not None else portal.costs().get("alike", 2),
                "ai_free": portal.ai_free(int(reader)) if reader is not None and role != "admin" else None,
                "credits": portal.balance(int(reader)) if reader is not None and role != "admin" else None}

    def post_request_handled(self):
        f = self.form_body()
        if (f.get("id") or "").isdigit():
            db.mark_handled(int(f["id"]), f.get("handled") == "1")
        return self.redirect("/requests")

    # ---------------------------------------------------------- public API --

    def api_unlock(self):
        if self.passcodes_off():
            return self.send_json(410, {"ok": False, "reason": "email_only",
                                        "message": "Access codes are no longer used. Sign in with your work email."}, self.cors())
        body = self.json_body()
        code = (body.get("code") or "").strip()
        # Guessing codes: 10 wrong tries per address per 10 minutes.
        gk = f"unlock:{self.client_ip()}"
        if not guard.limiter.allow(gk, 10, 600):
            return self.too_many(guard.limiter.retry_after(gk, 10, 600))
        # The campaign report only needs the pass, not the whole roster.
        lite = bool(body.get("lite"))
        row = None
        if code:
            row = (db.code_by_hash(auth.hash_code(code))
                   or db.code_by_hash(auth.legacy_hash_code(code)))
        ok, reason = db.code_state(row)
        ua = self.headers.get("User-Agent")
        if not ok:
            guard.limiter.hit(gk)
            db.log("unlock_fail", row["id"] if row else None, self.client_ip(), ua, reason)
            # The reason is deliberately returned: "expired" is far more useful
            # to an honest client than a flat "wrong code", and tells an
            # attacker nothing they could not learn by trying.
            return self.send_json(403, {"ok": False, "reason": reason}, self.cors())

        # Which browser this is. A new one gets an ID now; the code then has
        # to have room for it.
        token = self.cookies().get(DEVICE_COOKIE, "")
        if len(token) < 20:
            import secrets
            token = secrets.token_urlsafe(24)
        device = db.device_hash(token)
        admitted, why = db.admit_device(row, device, self.client_ip(), ua)
        if not admitted:
            db.log("unlock_fail", row["id"], self.client_ip(), ua, why)
            return self.send_json(403, {"ok": False, "reason": why}, self.cors())

        link = (body.get("link") or "").strip()[:80]
        found, target = self.link_target_code(link) if link else (False, None)
        if found and target is not None and target not in portal.team_codes(row["id"]):
            guard.limiter.hit(gk)
            db.log("unlock_fail", row["id"], self.client_ip(), ua, "other link")
            return self.send_json(403, {"ok": False, "reason": "otherlink"}, self.cors())

        db.bump_code_use(row["id"])
        db.log("unlock_ok", row["id"], self.client_ip(), ua,
               "new device" if why == "new" else None)
        expiry = db.now() + VIEWER_TTL
        if row["expires_at"]:
            expiry = min(expiry, row["expires_at"])
        ticket = auth.sign("%d:%d:%s" % (row["id"], expiry, device), SECRET)
        max_age = max(0, expiry - db.now())
        # Cross-origin needs SameSite=None, which needs Secure, which needs
        # HTTPS. Same-origin needs none of that and is the safer default.
        policy = "SameSite=None; Secure" if ALLOWED_ORIGINS else "SameSite=Lax"
        cookie = (f"{VIEWER_COOKIE}={ticket}; Path=/; HttpOnly; "
                  f"{policy}; Max-Age={max_age}")
        dev_cookie = (f"{DEVICE_COOKIE}={token}; Path=/; HttpOnly; "
                      f"{policy}; Max-Age={DEVICE_TTL}")
        payload = {"ok": True, "label": row["label"]}
        if not lite:
            payload.update(roster=self.roster_payload(), tiers=self.tier_payload(), fx=fx.rates())
        extra = []
        if link:
            # A selection's code also opens the catalogue behind it (adding creators);
            # never the other way round.
            extra.append(self.links_cookie([link] + (["cat"] if link.startswith("s:") else []), row["id"], expiry))
        return self.send_json(200, payload,
                              self.cors() + [("Set-Cookie", cookie),
                                             ("Set-Cookie", dev_cookie)] + extra)

    def roster_refusal(self, link=""):
        """None when this browser may read the roster (and cards from it); else the reason.
        /api/roster and the paged answers below are gated by this one rule."""
        if not self.viewer_code_id():
            return "locked"
        # A page that names its link asks for that link's own code once.
        if link and not self.admin_like() and not self.signed_in_client() and self.link_code(link) is None:
            return "link"
        return None

    def api_roster(self, link=""):
        why = self.roster_refusal(link)
        if why:
            return self.send_json(401, {"ok": False, "reason": why}, self.cors())
        raw, gz, tag, stamp = self.roster_body()
        head = self.cors() + [("ETag", tag), ("Cache-Control", "private, no-cache"),
                              ("Last-Modified", formatdate(stamp, usegmt=True)), ("Vary", "Cookie")]
        if tag in [t.strip() for t in (self.headers.get("If-None-Match") or "").split(",")]:
            return self.send(304, b"", "application/json; charset=utf-8", head)
        if "gzip" in (self.headers.get("Accept-Encoding") or ""):
            return self.send(200, gz, "application/json; charset=utf-8",
                             head + [("Content-Encoding", "gzip"), ("Vary", "Accept-Encoding")])
        return self.send(200, raw, "application/json; charset=utf-8", head)

    def roster_body(self):
        """(json bytes, gzipped bytes, ETag, built-at) of the roster answer, built once per version.
        "exp" tells the page when the signed photo links expire, so a copy it keeps in
        sessionStorage is never used past them."""
        tiers, rates = self.tier_payload(), fx.rates()
        key = (links.expires_at(), self._roster_fingerprint(), json.dumps(tiers, sort_keys=True), json.dumps(rates, sort_keys=True))
        hit = _ROSTER_BODY.get("v")
        if hit and hit[0] == key and time.time() - hit[1][3] < ROSTER_SAFETY_S:
            return hit[1]
        payload = {"ok": True, "roster": self.roster_payload(), "tiers": tiers, "fx": rates, "exp": links.expires_at()}
        raw = json.dumps(payload, separators=(",", ":")).encode()
        tag = '"r-' + __import__("hashlib").sha1(raw).hexdigest()[:24] + '"'
        out = (raw, gzip.compress(raw, 6), tag, time.time())
        _ROSTER_BODY.clear()
        _ROSTER_BODY["v"] = (key, out)
        return out

    def roster_index(self):
        """The paged roster's in-memory index (admin/paging.py), rebuilt only when the
        roster version /api/roster's ETag follows changes."""
        import paging

        def key():
            return (links.expires_at(), self._roster_fingerprint(),
                    json.dumps(self.tier_payload(), sort_keys=True), json.dumps(fx.rates(), sort_keys=True))
        return paging.current(key, lambda: (self.roster_payload(), self.tier_payload()))

    def api_roster_paged(self, job, q):
        """The catalogue one batch at a time (see admin/paging.py).

        GET /api/roster/page?link=&q=&tier=&platform=&place=&interest=&fmin=&fmax=&lic=&aud=&disc=&dplat=
                            &sort=&group=&cursor=&limit=
            -> {ok, items: [card], has_more, cursor, v, match?}; the first batch (no cursor)
               also carries tiers, fx and exp, so the page needs nothing else to draw.
               "match" only while a filter or a search is on: never the roster's size.
        GET /api/roster/facets?link=   -> {ok, facets: {tier, platform, place, interest}, v}
               option values, most common first, no counts.
        GET /api/roster/cards?link=&codes=A,B   -> {ok, cards, tiers, fx, exp}
               the named creators that are on the roster (max 200), in that order.
        Same gate as /api/roster: a locked browser, or a link this browser has no code
        for, gets a 401 and nothing else."""
        import paging
        one = lambda k: (q.get(k) or [""])[0]
        why = self.roster_refusal(one("link").strip()[:80])
        if why and job == "cards" and one("link").strip()[:2] == "s:":
            psel = self.public_selection(one("link").strip()[2:80])
            if psel is not None:
                # A public read-only selection link: the cards of that selection's creators only, no prices.
                allowed = set(json.loads(psel["codes"] or "[]"))
                codes = [c.strip().upper() for c in ",".join(q.get("codes") or []).split(",") if c.strip()]
                codes = [c for c in codes if c in allowed][:200]
                tiers = [{"name": x["name"], "from": None, "to": None, "reach": x["reach"]} for x in self.tier_payload()]
                return self.send_json(200, {"ok": True, "cards": self.public_strip(paging.cards(self.roster_index(), codes)),
                                            "tiers": tiers, "fx": fx.rates(), "exp": links.expires_at(), "public": True},
                                      self.cors() + [("Cache-Control", "private, no-cache"), ("Vary", "Cookie")])
        if why:
            return self.send_json(401, {"ok": False, "reason": why}, self.cors())
        idx = self.roster_index()
        head = self.cors() + [("Cache-Control", "private, no-cache"), ("Vary", "Cookie")]
        if job == "facets":
            return self.send_json(200, {"ok": True, "facets": idx.facets(), "v": paging._tag(idx)}, head)
        if job == "cards":
            codes = [c.strip().upper() for c in ",".join(q.get("codes") or []).split(",") if c.strip()][:200]
            return self.send_json(200, {"ok": True, "cards": paging.cards(idx, codes), "tiers": self.tier_payload(),
                                        "fx": fx.rates(), "exp": links.expires_at()}, head)
        f = paging.clean_query(q)
        try:
            limit = int(one("limit") or paging.BATCH)
        except ValueError:
            limit = paging.BATCH

        def lic():
            import licence
            return licence.for_roster()

        def disc(filters, plat):
            import discover
            return discover.match(filters, plat)

        def aud():
            import discover
            return discover.top_markets()
        out = paging.page(idx, f, one("cursor")[:80] or None, limit, lic, disc, aud)
        if not one("cursor"):
            out.update(tiers=self.tier_payload(), fx=fx.rates(), exp=links.expires_at())
        return self.send_json(200, out, head)

    def api_discover(self, job):
        """The catalogue's Audience and Performance filters, lookalikes and
        typed searches. Analyses never leave the server: the page gets codes."""
        if not self.viewer_code_id():
            return self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
        import discover
        # Analysis gating: for a client, filtering on a locked figure (audience, fake followers,
        # brands, likes…) would answer "does this creator's audience pass X?" one code at a time,
        # so only the free headline figures (engagement, average views) filter, and the facets
        # list none of the locked options.
        free = not self.admin_like()
        if job == "facets":
            return self.send_json(200, {"ok": True, "facets": discover.facets(free_only=free)}, self.cors())
        b = self.json_body()
        if job == "like":
            return self.send_json(200, {"ok": True, "codes": discover.like(str(b.get("code") or "")[:40])}, self.cors())
        if job == "parse":
            return self.send_json(200, {"ok": True, "filters": discover.parse(str(b.get("text") or "")[:400])}, self.cors())
        plat = b.get("platform") if b.get("platform") in ("Instagram", "TikTok", "Snapchat", "YouTube", "X", "Facebook") else None
        return self.send_json(200, {"ok": True, "codes": discover.match(b.get("filters"), plat, free_only=free)}, self.cors())

    def tier_payload(self):
        """Sent with the roster so the page totals a selection at today's
        rates rather than whatever was hard-coded when it was built."""
        return [
            {"name": t["name"], "from": t["price_from"], "to": t["price_to"],
             "reach": t["reach"]}
            for t in db.list_tiers()
        ]

    def roster_payload(self, platform=None, only=None):
        # The full roster is the same for every viewer, so it is built once and
        # reused until a creator, an analysis or a tier changes (or an hour
        # pass, or the day's photo signatures roll over). It took ~0.45 s per
        # unlock with 2,100+ creators.
        if only is not None:
            return self._roster_build(platform, only)
        key = (platform, links.expires_at(), self._roster_fingerprint())
        hit = _ROSTER_CACHE.get(key)
        if hit and time.time() - hit[0] < ROSTER_SAFETY_S:
            return hit[1]
        # One build at a time (2026-10-14): at 14,000+ creators several requests arriving on a cold cache each
        # built the whole roster in parallel, multiplying CPU and memory until the container was OOM-killed.
        with _ROSTER_BUILD_LOCK:
            hit = _ROSTER_CACHE.get(key)
            if hit and time.time() - hit[0] < ROSTER_SAFETY_S:
                return hit[1]
            out = self._roster_build(platform, None)
            _ROSTER_CACHE.clear()
            _ROSTER_CACHE[key] = (time.time(), out)
            return out

    def _roster_fingerprint(self):
        with db.connect() as conn:
            return tuple(conn.execute(
                "SELECT (SELECT count(*) || ':' || coalesce(" + db.CREATOR_STAMP + ", 0) FROM creators),"
                " (SELECT count(*) || ':' || coalesce(max(rowid), 0) FROM creator_analysis),"
                " (SELECT group_concat(name || ':' || coalesce(price_from, '') || ':' || coalesce(price_to, '')) FROM tiers)").fetchone())

    def _roster_build(self, platform=None, only=None):
        land = db.setting("portal_countries", db.PORTAL_COUNTRIES) if only is None else None
        bands = db.tier_prices()
        analysed = db.analysis_codes()
        def accounts(r):
            out = []
            for a in db.account_tiers(r):
                band = bands.get(a["tier"]) if a["tier"] else None
                out.append({"platform": a["platform"], "url": a["url"],
                            "followers": a["followers"], "tier": a["tier"],
                            "price": list(band) if band else None})
            return out
        return [
            {
                "code": r["code"], "name": r["name"], "handle": r["handle"],
                "platform": r["platform"], "followers": r["followers"],
                "city": r["city"], "nationality": r["nationality"],
                "tier": r["tier"], "interest": r["interest"],
                "photo": r["photo"], "lowres": self.is_lowres(r["photo"]),
                "analysis": r["code"] in analysed,
                # The tier of each account, not only of the biggest one: a
                # creator can be Mid-Tier on Instagram and Micro on TikTok, and
                # a campaign booking the TikTok is buying the smaller audience.
                "accounts": accounts(r),
                # The page builds no photo URL of its own any more. Every code
                # is HV-XX-NNN, so the pattern was walkable and the whole set
                # could be pulled without a passcode; nginx now refuses a photo
                # this service did not sign.
                "photo_url": links.photo(r["photo"]) if r["photo"] else None,
                # This creator's price: their own rate if one is set, their
                # tier's band otherwise. The page prices a selection from this.
                "price": list(db.price_for(r, bands, platform) or []) or None,
                "profiles": db.split_profiles(r["profiles"]),
                # The creator's single main industry and what they also cover (owner, 2026-10-13). The
                # tier (Confirmed / Probable / Review) says how sure we are; the estimated % stays internal.
                "ind": r["industry"], "sub": _json_list(r["sub_niches"]), "also": _json_list(r["also_industries"]),
                "itier": r["industry_tier"],
            }
            for r in db.list_creators(active_only=True)
            if (only is not None and r["code"] in only) or (only is None and self._in_markets(r, land))
        ]

    def _in_markets(self, r, land=None):
        """portal_countries (owner, 2026-10-12; GCC added 2026-10-21, item 226): the portal browses Saudi Arabia,
        UAE, Egypt, Kuwait, Qatar, Bahrain and Oman only.
        A creator whose city names another country is hidden from browsing (still in the admin and on
        selections already made); a city not set yet stays, since the country is unknown.
        ``land`` is the setting read once by the caller (a build checks 14,000+ creators)."""
        import paging
        if land is None:
            land = db.setting("portal_countries", db.PORTAL_COUNTRIES)
        if not land:
            return True
        country, label, _key = paging.place(r["city"])
        if country in land:
            return True
        return country == "Other" and str(r["city"] or "").strip().lower() in ("", "unspecified", "other", "unknown")

    # Measuring 154 files on every unlock would be wasteful and they rarely
    # change, so the widths are read once and dropped whenever a photo is
    # written. Instagram hands back a 100px thumbnail on one path and 320px on
    # another; a 100px source stretched across a 330px card is the pixelation,
    # and the card treats those differently rather than upscaling them.
    _widths = {}

    @classmethod
    def forget_photo_widths(cls):
        cls._widths = {}
        _ROSTER_CACHE.clear()        # a new photo changes photo_url and lowres
        _ROSTER_BODY.clear()
        import paging
        paging.invalidate()

    def is_lowres(self, photo):
        if not photo:
            return False
        name = str(photo).split("?")[0]
        if name not in self._widths:
            path = PHOTO_DIR / name
            self._widths[name] = uploads.jpeg_width(path) if path.exists() else 0
        w = self._widths[name]
        # 320 is the bar tools/photo_audit.py grades against: below it a
        # ~330px card shows the source stretched, so it gets the soft circle.
        return bool(w) and w < 320

    def api_request(self):
        code_id = self.viewer_code_id()
        if not code_id:
            return self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
        b = self.json_body()
        selection = b.get("selection") or []
        if not isinstance(selection, list) or not selection:
            return self.send_json(400, {"ok": False, "reason": "empty selection"}, self.cors())
        # A saved selection: only its owner (or HelloVoice) may ask for its quote. A colleague on the
        # same company sees the selection but cannot send it. No token = the sender's own unsaved list.
        tok = str(b.get("token") or "").strip()[:80]
        sel = None
        if tok:
            sel = db.selection(token=tok)
            if sel is None or (sel["code_id"] is not None and int(code_id) != db.admin_code_id()
                               and not portal.opens(int(code_id), sel)):
                return self.send_json(404, {"ok": False, "reason": "unknown"}, self.cors())
            if not portal.may_edit(int(code_id), sel, db.admin_code_id()):
                return self.send_json(403, {"ok": False, "reason": "not_owner",
                                            "message": "Only the person who owns this selection can request its quote."}, self.cors())
        rid = db.create_request(
            code_id, b.get("name"), b.get("company"), b.get("email"), b.get("phone"),
            b.get("selection_name"), [str(c)[:40] for c in selection[:SELECTION_MAX]],
        )
        db.log("request", code_id, self.client_ip(), self.headers.get("User-Agent"), str(rid))
        if tok and sel is not None:
            import lifecycle
            _u = self.person_user(code_id)
            lifecycle.mark_requested(sel, rid, (_u["name"] if _u is not None and _u["name"] else b.get("name")),
                                     _u["id"] if _u is not None else None)
        # The browser still mails the quote through the form service; this is the server's own copy to
        # the client's KAM and the team, which does not depend on that service accepting it.
        import notify
        u = self.person_user(code_id)
        notify.send("quote", ["%s requested a quote for “%s” (%d creators)." % (
            (u["company"] or u["email"]) if u else (b.get("company") or "A client"), b.get("selection_name") or "a selection", len(selection)),
            "Name: %s" % (b.get("name") or ""), "Email: %s" % (b.get("email") or ""), "Phone: %s" % (b.get("phone") or "")],
            kam=u["kam"] if u else None, link=self.site_origin() + BASE + "/requests")
        return self.send_json(200, {"ok": True, "id": rid}, self.cors())

    def api_search(self, q):
        """Quick search for the command palette: creators, selections,
        campaigns and clients matching what was typed."""
        out = {"creators": [], "selections": [], "campaigns": [], "clients": []}
        if len(q) >= 2:
            ql = q.lower()
            for c in db.list_creators(search=q)[:6]:
                out["creators"].append({"label": c["name"], "hint": "%s · %s" % (c["code"], c["tier"]),
                                        "href": views.u("/roster") + "?q=" + urllib.parse.quote(c["code"])})
            for s in db.list_selections():
                if ql in (s["name"] or "").lower() and not (s["archived_at"] if "archived_at" in s.keys() else None):
                    out["selections"].append({"label": s["name"], "hint": "Selection",
                                              "href": views.u("/selections/edit") + "?id=%d" % s["id"]})
            for k in db.list_campaigns():
                if ql in (k["name"] or "").lower() or ql in (k["client"] or "").lower():
                    out["campaigns"].append({"label": k["name"], "hint": k["status"],
                                             "href": views.u("/campaigns/edit") + "?id=%d" % k["id"]})
            for c in db.list_codes():
                if ql in (c["label"] or "").lower():
                    out["clients"].append({"label": c["label"], "hint": "Client",
                                           "href": views.u("/clients")})
            for k in out:
                out[k] = out[k][:6]
        return self.send_json(200, out, [("Cache-Control", "no-store")])

    def api_selection_platform(self):
        """A client choosing which platform to see a creator's match on (and so, which one they
        want booked). Same rules as their tags: their own passcode, or the admin."""
        b = self.json_body()
        viewer = self.selection_viewer(str(b.get("token") or ""))
        if not viewer:
            return self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
        sel = db.selection(token=str(b.get("token") or ""))
        if sel is None or (int(viewer) != db.admin_code_id() and not portal.owns(int(viewer), sel["code_id"]) and not portal.sample_member(viewer, sel)):
            return self.send_json(404, {"ok": False}, self.cors())
        code = str(b.get("code") or "").strip().upper()
        if code not in json.loads(sel["codes"] or "[]"):
            return self.send_json(404, {"ok": False}, self.cors())
        raw = str(b.get("platform") or "").strip()
        plat = "Both" if raw == "Both" else (analysis.canon_platform(raw) or "")
        if plat and plat != "Both" and plat not in db.analyses(code):
            return self.send_json(400, {"ok": False, "reason": "no analysis on that platform"}, self.cors())
        return self.send_json(200, {"ok": True, "client_platforms": db.set_client_platform(sel["id"], code, plat)}, self.cors())

    def _status_target(self, b):
        """(sel, reader, role, code) for a status action, or None after answering."""
        token = str(b.get("token") or "")
        reader = self.selection_viewer(token)
        if not reader:
            self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
            return None
        sel = db.selection(token=token) if token else None
        staff = self.staff_viewer() and self.kam_clients() is None
        if sel is None or (sel["code_id"] is not None and int(reader) != db.admin_code_id()
                           and not staff and not portal.opens(int(reader), sel)):
            self.send_json(404, {"ok": False}, self.cors())
            return None
        code = str(b.get("code") or "").strip().upper()
        if code not in json.loads(sel["codes"] or "[]"):
            self.send_json(404, {"ok": False, "reason": "not_in_selection"}, self.cors())
            return None
        return sel, int(reader), self.selection_role(sel, reader), code

    def _status_who(self, role, reader):
        if role == "admin":
            a = self.admin()
            u = self.person_user(reader) if a is None else None
            if u is not None and u["name"]:
                return "hv", u["name"], None   # staff signed in to the portal: their own name
            name = (a["name"] if a is not None and "name" in a.keys() and a["name"] else None) or \
                   ((a["email"].split("@")[0].replace(".", " ").title()) if a is not None else "HelloVoice")
            return "hv", name, None
        u = self.person_user(reader)
        return "client", (u["name"] if u is not None and u["name"] else "Client"), u

    def api_selection_status(self):
        """Approve, reject or set back one creator. The selection's owner decides; HelloVoice
        can set anything, including Unavailable; colleagues only look."""
        b = self.json_body()
        got = self._status_target(b)
        if not got:
            return
        sel, reader, role, code = got
        status = str(b.get("status") or "")
        if role == "viewer":
            owner = portal.user_for_code(sel["code_id"]) if sel["code_id"] else None
            return self.send_json(403, {"ok": False, "reason": "not_owner", "message": "Only %s can approve or reject creators in this selection." % (
                (owner["name"] if owner is not None and owner["name"] else "the person who owns it"))}, self.cors())
        if role == "owner" and status == "unavailable":
            return self.send_json(403, {"ok": False, "reason": "hv_only", "message": "Only HelloVoice marks a creator unavailable."}, self.cors())
        if self._throttled("status:%d" % reader, 240, 600):
            return
        kind, name, user = self._status_who(role, reader)
        row, err = selstatus.set_status(sel, code, status, kind, name, b.get("reason"), b.get("note"))
        if err:
            return self.send_json(400, {"ok": False, "reason": err}, self.cors())
        if kind == "hv":
            selstatus.ring_client(sel, code, status, name, row.get("note"))
        else:
            selstatus.tell_kam(sel, code, status, user, row.get("reason"), row.get("note"))
        db.log("shortlist", reader, self.client_ip(), self.headers.get("User-Agent"), "status:%s:%s" % (code, status))
        codes = json.loads(sel["codes"] or "[]")
        p = self.selection_status_payload(sel, codes, reader)
        return self.send_json(200, {"ok": True, "status": row, "status_counts": p["status_counts"]}, self.cors())

    def api_selection_reason(self):
        """The optional "why" under a rejection: price, audience, content style, a competitor, other."""
        b = self.json_body()
        got = self._status_target(b)
        if not got:
            return
        sel, reader, role, code = got
        if role == "viewer":
            return self.send_json(403, {"ok": False, "reason": "not_owner"}, self.cors())
        row = selstatus.set_reason(sel, code, b.get("reason"), b.get("note"))
        if row is None or row["s"] != "rejected":
            return self.send_json(400, {"ok": False, "reason": "not_rejected"}, self.cors())
        if role == "owner":
            selstatus.tell_kam(sel, code, "rejected", self.person_user(reader), row["reason"], row["note"])
        return self.send_json(200, {"ok": True, "status": row}, self.cors())

    def api_selection_replace(self):
        """Find a replacement with Helvi: three creators like the rejected one that fit the
        same campaign, not already in the selection. Costs credits once; the three are
        kept, so opening them again is free."""
        import matcher
        b = self.json_body()
        got = self._status_target(b)
        if not got:
            return
        sel, reader, role, code = got
        if role == "viewer":
            return self.send_json(403, {"ok": False, "reason": "not_owner"}, self.cors())
        row = selstatus.get(sel["id"], code)
        if row is None or row["s"] not in ("rejected", "unavailable"):
            return self.send_json(400, {"ok": False, "reason": "not_rejected"}, self.cors())
        codes = json.loads(sel["codes"] or "[]")
        if row["replacements"] and not b.get("again"):
            picks, cost = [c for c in row["replacements"]], 0
        else:
            if self._throttled("replace:%d" % reader, 20, 3600):
                return
            ok, cost, bal = portal.charge(reader, "replace", "Helvi: replacement for " + code) if role == "owner" else (True, 0, None)
            if not ok:
                return self.send_json(402, {"ok": False, "reason": "no_credits", "balance": portal.balance(reader),
                                            "cost": portal.costs().get("replace", 2),
                                            "message": "You're out of credits. Request more from your profile."}, self.cors())
            gone = db.creator(code)
            hcp = str((gone["tier"] if gone is not None else "") or "").upper().startswith("HCP")
            tier = gone["tier"] if gone is not None else None
            plat = sel["platform"] if "platform" in sel.keys() and sel["platform"] else None
            brief = {"objective": self.selection_objective(sel), "target": self.selection_target(sel),
                     "platforms": [plat] if plat else (analysis.creator_platforms(gone)[:1] if gone is not None else [])}
            try:
                items = matcher.score_all(brief, exclude=set(codes) | set(row["replacements"] or []), strict=True)
            except Exception:
                items = []
            tier_of = {c["code"]: c["tier"] for c in db.list_creators(active_only=True)}
            items = [i for i in items if str(tier_of.get(i["code"]) or "").upper().startswith("HCP") == hcp]
            items.sort(key=lambda i: (tier_of.get(i["code"]) != tier, -i["rank_score"]))
            picks = [i["code"] for i in items[:3]]
            if not picks:
                portal.refund(reader, cost, "no replacement found")
                return self.send_json(200, {"ok": True, "replacements": [], "message": "Helvi found no one close enough. Your account manager can help."}, self.cors())
            selstatus.set_replacements(sel["id"], code, picks)
        shown = {r["code"]: r for r in self.roster_payload(only=set(picks))}
        # "Why" for each pick, from card fields only (public data), as in Creators like this.
        import aimore
        gone = db.creator(code)
        rows = {r["code"]: r for r in db.creators_by_codes(picks)}
        why = {c: ("In %s's place: " % (gone["name"] or code)) + aimore.reason(rows[c], gone)[:1].lower() + aimore.reason(rows[c], gone)[1:]
               if gone is not None and c in rows else "" for c in picks}
        return self.send_json(200, {"ok": True, "replacements": [dict(shown[c], why=why.get(c, "")) for c in picks if c in shown], "spent": cost,
                                    "free": portal.ai_free(reader) is not None,
                                    "credits": portal.balance(reader) if role == "owner" else None}, self.cors())

    def api_selection_tags(self):
        """A client labelling a creator on their own selection page (Shortlist,
        Backup, Phase 2…). Allowed for the passcode the selection belongs to,
        and for the admin; the labels are kept apart from the admin's own."""
        b = self.json_body()
        viewer = self.selection_viewer(str(b.get("token") or ""))
        if not viewer:
            return self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
        sel = db.selection(token=str(b.get("token") or ""))
        if sel is None or (sel["code_id"] is not None and int(viewer) != db.admin_code_id()
                           and not portal.opens(int(viewer), sel)):
            return self.send_json(404, {"ok": False}, self.cors())
        if not portal.may_edit(int(viewer), sel, db.admin_code_id()):
            return self.send_json(403, {"ok": False, "reason": "not_owner", "message": "Only the person who owns this selection can change it. Colleagues on the same company can view it."}, self.cors())
        code = str(b.get("code") or "").strip().upper()
        if code not in json.loads(sel["codes"] or "[]"):
            return self.send_json(404, {"ok": False}, self.cors())
        seen, mine = set(), []
        for t in (b.get("tags") or [])[:20]:
            t = re.sub(r"[<>]", "", re.sub(r"\s+", " ", str(t))).strip()[:24]
            if t and t.lower() not in seen and len(mine) < 8:
                seen.add(t.lower()); mine.append(t)
        everyone = db.set_client_tags(sel["id"], code, mine)
        return self.send_json(200, {"ok": True, "tags": mine, "client_tags": everyone}, self.cors())

    def api_selection_rename(self):
        """POST {token, name} (portal item 173): rename from the selection page or /account/.
        Owner, HelloVoice and the client's key account manager only (selrename.client_may)."""
        import selrename
        b = self.json_body()
        token = str(b.get("token") or "").strip()[:80]
        if self._throttled("selren:%s" % self.client_ip(), 60, 3600):
            return
        sel = db.selection(token=token) if token else None
        if sel is None:
            return self.send_json(404, {"ok": False, "reason": "missing", "message": selrename.MESSAGES["missing"]}, self.cors())
        viewer = self.selection_viewer(token)
        admin_id = db.admin_code_id()
        if not selrename.client_may(viewer, sel, admin_id):
            return self.send_json(403 if viewer else 401, {"ok": False, "reason": "forbidden",
                                                           "message": selrename.MESSAGES["forbidden"]}, self.cors())
        if viewer is not None and int(viewer) == int(admin_id):
            a = self.admin()
            who = (a["email"] if a is not None and "email" in a.keys() else None) or "HelloVoice"
        else:
            u = self.person_user(int(viewer))
            who = "client: " + ((u["email"] if u is not None else None) or "code %s" % viewer)
        row, err = selrename.apply(sel, b.get("name"), who)
        if err:
            return self.send_json(400, {"ok": False, "reason": err, "message": selrename.MESSAGES[err]}, self.cors())
        return self.send_json(200, {"ok": True, "token": row["token"], "name": row["name"]}, self.cors())

    def api_selection_save(self):
        """A client naming a shortlist. It is recorded here so it appears in
        the dashboard by itself, ready to be priced, instead of an admin having
        to paste the link. Re-saving the same one — the client went back and
        added a creator — updates it rather than making another."""
        b = self.json_body()
        viewer = self.selection_viewer((str(b.get("token") or "")).strip())
        if not viewer:
            return self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
        name = (str(b.get("name") or "Selection")).strip()[:120] or "Selection"
        known = {c["code"] for c in db.list_creators(active_only=True)}
        codes, seen = [], set()
        asked = b.get("codes") or []
        for c in asked[:SELECTION_MAX]:
            c = str(c).strip().upper()
            if c in known and c not in seen:
                seen.add(c); codes.append(c)
        if not codes:
            return self.send_json(400, {"ok": False, "reason": "empty"}, self.cors())

        token = (str(b.get("token") or "")).strip()
        sel = db.selection(token=token) if token else None
        if sel is not None and not portal.may_edit(viewer, sel, db.admin_code_id()):
            sel = None                      # not theirs (another client, or a colleague's): never touched
        if sel is None:
            sel = db.selection_for_link(name, codes, viewer)
        if sel is None:
            if modules.over(viewer, "selections_max", modules.count(viewer, "selections")):
                return self.send_json(403, {"ok": False, "reason": "limit", "message":
                                            "You have as many selections as your plan allows. Ask your account manager for more."},
                                      self.cors())
            sid = db.save_selection(None, name, codes, {}, None, None, None, viewer, origin="client")
            return self.send_json(200, {"ok": True, "token": db.selection(sid)["token"],
                                        "capped": SELECTION_MAX if len(asked) > SELECTION_MAX else None},
                                  self.cors())

        # Item 173: the name. A page sends the name it loaded (loaded_name); unchanged there means "keep
        # whatever it is now", so a stale tab never writes an old name back over a rename made elsewhere.
        # A real change goes through the rename rule (1-80 characters, History); an invalid one is ignored.
        import selrename
        loaded = b.get("loaded_name")
        if loaded is not None and name == (str(loaded).strip()[:120] or "Selection"):
            name = sel["name"]
        elif name != sel["name"]:
            u_ = self.person_user(int(viewer)) if int(viewer) != db.admin_code_id() else None
            row, err = selrename.apply(sel, name, ("client: " + u_["email"]) if u_ is not None else None)
            name = sel["name"] if err else row["name"]
            sel = row if row is not None else sel
        prices = {k: v for k, v in json.loads(sel["prices"] or "{}").items() if k in codes}
        stored = json.loads(sel["codes"] or "[]")
        same = sorted(stored) == sorted(codes)
        # A total typed for one shortlist cannot stand for a different one, so
        # a client adding or removing a creator returns it to the sum of the
        # prices — which the admin can type again.
        t_from = sel["total_from"] if same else None
        t_to = sel["total_to"] if same else None
        # Same creators = a rename (e.g. naming an AI shortlist before opening it): the
        # single-platform mark the shortlist was saved with stays as it was.
        db.save_selection(sel["id"], name, codes, prices, t_from, t_to,
                          platform=sel["platform"] if same else None)
        out = {"ok": True, "token": sel["token"], "capped": SELECTION_MAX if len(asked) > SELECTION_MAX else None}
        if not same and int(viewer) != db.admin_code_id():
            # A quote may already exist: the change is recorded, the account manager told, the page warns.
            import lifecycle
            if lifecycle.on_client_edit(sel, stored, codes, self.person_user(viewer),
                                        link=self.site_origin() + BASE + "/selections/edit?id=%d" % sel["id"]):
                out["lifecycle"] = lifecycle.client_payload(db.selection(sel["id"]), "owner")
        return self.send_json(200, out, self.cors())

    def api_event(self):
        code_id = self.viewer_code_id()
        if not code_id:
            return self.send_json(401, {"ok": False}, self.cors())
        b = self.json_body()
        kind = b.get("kind")
        # mail_sent / mail_failed: the quote email goes from the browser to
        # FormSubmit, which this server cannot reach (Cloudflare refuses it),
        # so the page reports the outcome here. Without that, a rejected email
        # is invisible to everyone — which is how quotes went unmailed while
        # the dashboard showed them arriving.
        if kind not in ("view", "shortlist", "mail_sent", "mail_failed"):
            return self.send_json(400, {"ok": False}, self.cors())
        db.log(kind, code_id, self.client_ip(), self.headers.get("User-Agent"),
               str(b.get("detail") or "")[:80])
        return self.send_json(200, {"ok": True}, self.cors())


# Admin actions that are recorded for undo: path -> (what they change, the
# form field naming which one, how the History page describes it). A field
# of None, or an empty one, is a create — its key is found afterwards.
TRACKED = {
    "/roster/save": ("creator", "code", "Saved creator"),
    "/roster/delete": ("creator", "code", "Deleted creator"),
    "/roster/import": ("roster", None, "Imported a roster sheet"),
    "/tiers/save": ("tiers", None, "Changed tiers"),
    "/tiers/delete": ("tiers", None, "Deleted a tier"),
    "/selections/new": ("selection", None, "Created selection"),
    "/selections/save": ("selection", "id", "Saved selection"),
    "/selections/delete": ("selection", "id", "Deleted selection"),
    "/campaigns/new": ("campaign", None, "Created campaign"),
    "/campaigns/import/confirm": ("campaign", None, "Created campaign from an Excel template"),
    "/campaigns/setup": ("campaign", None, "Created campaign from a selection"),
    "/campaigns/save": ("campaign", "id", "Saved campaign"),
    "/campaigns/delete": ("campaign", "id", "Deleted campaign"),
    "/campaigns/status": ("campaign", "id", "Changed status of campaign"),
    "/settings/fx": ("settings", None, "Changed exchange rates"),
    "/planner/library": ("settings", None, "Changed the benchmark library"),
    "/planner/apply": ("campaign", "id", "Set goals from the ROI planner"),
    "/calculator/save": ("campaign", "id", "Set goals from the calculator"),
    "/calculator/results": ("campaign", "id", "Adjusted campaign results by hand"),
    "/campaigns/link": ("campaign", "id", "Changed a tracking link"),
    "/campaigns/link/custom": ("campaign", "id", "Added a tracking link"),
    "/campaigns/link/toggle": ("campaign", "id", "Switched a tracking link"),
    "/campaigns/content/add": ("campaign", "id", "Added a post"),
    "/campaigns/content/update": ("campaign", "id", "Changed a post"),
    "/campaigns/content/group": ("campaign", "id", "Grouped posts as one video"),
    "/campaigns/content/bulk": ("campaign", "id", "Bulk-added posts or numbers"),
    "/campaigns/content/pending": ("campaign", "id", "Updated who is still to post"),
    "/campaigns/insights/decide": ("campaign", "id", "Reviewed insights"),
    "/campaigns/insights/upload": ("campaign", "id", "Uploaded insights"),
    "/campaigns/sales": ("campaign", "id", "Changed campaign sales"),
    "/campaigns/sync": ("campaign", "id", "Synced campaign creators"),
    "/codes/new": ("code", None, "Created access code"),
    "/codes/revoke": ("code", "id", "Revoked access code"),
    "/codes/restore": ("code", "id", "Restored access code"),
    "/codes/archive": ("code", "id", "Archived access code"),
    "/codes/unarchive": ("code", "id", "Took an access code out of the archive"),
    "/codes/delete": ("code", "id", "Deleted archived access code"),
    "/codes/limits": ("code", "id", "Changed access code limits"),
    "/codes/passcode": ("code", "id", "Changed a passcode"),
    "/codes/device/remove": ("code", "code", "Removed a device"),
}


def _keys(sql):
    with db.connect() as conn:
        return {str(r[0]) for r in conn.execute(sql)}


KEYSETS = {
    "creator": lambda: _keys("SELECT code FROM creators"),
    "selection": lambda: _keys("SELECT id FROM selections"),
    "campaign": lambda: _keys("SELECT id FROM campaigns"),
    "code": lambda: _keys("SELECT id FROM codes"),
}


def describe(entity, key, verb):
    """'Deleted creator HV-MI-212 · Bodor Mamdouh' — read from the before or
    after state, whichever exists."""
    name = ""
    try:
        with db.connect() as conn:
            if entity == "creator" and key:
                r = conn.execute("SELECT name FROM creators WHERE code = ?", (key,)).fetchone()
                name = key + (" · " + r[0] if r else "")
            elif entity in ("selection", "campaign", "code") and key and str(key).isdigit():
                table, col = {"selection": ("selections", "name"), "campaign": ("campaigns", "name"),
                              "code": ("codes", "label")}[entity]
                r = conn.execute("SELECT %s FROM %s WHERE id = ?" % (col, table), (int(key),)).fetchone()
                name = (r[0] if r else "#" + str(key))
    except Exception:
        pass
    return verb + ((" " + name) if name else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8900)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--origin", action="append", default=[],
                    help="catalogue origin allowed to call /api/* (repeatable). "
                         "Omit when the catalogue is served from this same origin.")
    ap.add_argument("--base-path", default="",
                    help="serve the dashboard under a path, e.g. /admin")
    ap.add_argument("--trial", action="store_true",
                    help="the trial process (trial.py): demo databases only, no schedulers, no network")
    args = ap.parse_args()
    if args.trial:
        return trial_main(args)

    db.init()
    history.init()
    portal.init()
    import licence
    licence.init()
    account.init()
    import workspace
    workspace.init()
    workspace.start()
    import creators_private
    creators_private.ensure()               # the owner column and the triggers that keep a private creator private
    team.init()
    evidence.init()
    import push
    push.init()
    apify.start_scheduler()
    # Post thumbnails (2026-10-13): two resumable jobs fetched from the post links (scripts in /app/admin/jobs/).
    # This keeps them running: if one is not running it is started again, so a restart of this service does not
    # need anyone to relaunch them. Nothing starts while the job is already running.
    def _thumb_supervisor():
        import subprocess as _sp
        jobs = {}      # paused 2026-10-13: the platform links now load live in the viewer's browser; stored copies are kept
        if False: jobs = {"Instagram": "post_thumbs_ig", "TikTok": "post_thumbs_tt"}
        while True:
            for plat, name in jobs.items():
                try:
                    running = _sp.run(["pgrep", "-f", "jobs/post_thumbs.py %s" % plat], capture_output=True).returncode == 0
                    if not running:
                        logf = open("/tmp/thumbs_%s.log" % plat.lower()[:2], "a")
                        _sp.Popen([sys.executable, "-u", str(HERE / "jobs" / "post_thumbs.py"), plat], stdout=logf, stderr=logf)
                        print("thumbs job started:", plat, flush=True)
                except Exception as e:
                    print("thumbs supervisor:", repr(e)[:120], flush=True)
            time.sleep(60)
    __import__("threading").Thread(target=_thumb_supervisor, daemon=True, name="thumb-supervisor").start()
    profile_thumbs.start()
    # Phase E: weekly campaign updates + "what to do next time" (on start, then hourly; idempotent).
    import weekly
    weekly.start()
    # Prediction log (2026-10-13): freezes each campaign creator's score so it can be tested against the results.
    import scorelog
    scorelog.start()
    __import__("discover").warm()          # the shortlist's analysis summaries, loaded before the first brief (item 275)
    # What people said (2026-10-19): campaign comments read 2 and 7 days after each video.
    import comments
    comments.start()
    import postcheck, nextstep               # item 218: post checks and the 9:00 digest
    postcheck.start()
    nextstep.start()
    # HELVY Connect app (item 168): phone pushes from the bell, team alerts, milestones and manual sends.
    push.start()
    db.purge_expired_sessions()
    trial.init()
    _start_trial_process(args)
    ALLOWED_ORIGINS.update(args.origin)
    global BASE
    BASE = "/" + args.base_path.strip("/") if args.base_path.strip("/") else ""
    actions.configure(port=args.port, base=BASE)   # where the copilot's bridge knocks
    views.set_base(BASE)

    if db.admin_count() == 0:
        print("No admin yet. Create one:\n  python3 admin/seed.py --email you@example.com")

    # The full roster takes about a minute and a half to build at 14,000 creators (it measures every photo) and
    # is rebuilt whenever its version changes: a creator edit, and every day at 00:00 UTC when the photo
    # signatures roll over. A background refresher keeps it current, so no visitor ever waits for the build:
    # while a new version is being made the previous one keeps answering (admin/paging.py current()).
    def _warm():
        import time as _t
        first = True
        while True:
            try:
                h = Handler.__new__(Handler)
                h.roster_index()
                h.roster_payload()
                if first:
                    print("roster warmed", flush=True)
                    first = False
            except Exception as e:      # a failed pass only means the next one tries again
                print("roster refresh skipped:", repr(e)[:120], flush=True)
            _t.sleep(25)
    __import__("threading").Thread(target=_warm, daemon=True, name="roster-warm").start()

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"admin  http://{args.host}:{args.port}{BASE or ''}")
    print(f"origins allowed: {', '.join(ALLOWED_ORIGINS) or '(any — set --origin in production)'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def _start_trial_process(args):
    """Keep the trial process (trial.py) running beside this one, restarting it if it stops."""
    import subprocess as _sp

    def run():
        while True:
            env = dict(_os.environ, HV_TRIAL="1", HV_DB_PATH=str(trial.TEMPLATE), HV_TRIAL_PORT=str(trial.PORT))
            cmd = [sys.executable, "-u", str(HERE / "server.py"), "--trial", "--host", "127.0.0.1",
                   "--port", str(trial.PORT), "--base-path", args.base_path]
            for o in args.origin:
                cmd += ["--origin", o]
            try:
                p = _sp.Popen(cmd, env=env)
                print("trial process started, pid", p.pid, flush=True)
                p.wait()
                print("trial process stopped:", p.returncode, flush=True)
            except Exception as e:
                print("trial process:", repr(e)[:160], flush=True)
            try:
                trial.sweep()
            except Exception:
                pass
            time.sleep(5)
    __import__("threading").Thread(target=run, daemon=True, name="trial-process").start()


def trial_main(args):
    """The trial process: same handlers, demo databases only (trial.py)."""
    if not trial.ACTIVE:
        sys.exit("--trial needs HV_TRIAL=1 (it is started by the main service)")
    trial.activate()
    import licence
    import workspace
    import creators_private

    def schema():
        db.init()
        history.init()
        portal.init()
        licence.init()
        account.init()
        workspace.init()
        creators_private.ensure()
        team.init()
        evidence.init()
        trial.init()
    schema()
    trial.ON_FIRST_USE = schema
    ALLOWED_ORIGINS.update(args.origin)
    global BASE
    BASE = "/" + args.base_path.strip("/") if args.base_path.strip("/") else ""
    actions.configure(port=args.port, base=BASE)
    views.set_base(BASE)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"trial  http://{args.host}:{args.port}{BASE or ''}  template {trial.TEMPLATE}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
