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
import importer  # noqa: E402
import db  # noqa: E402
import history  # noqa: E402
import fx  # noqa: E402
import analysis  # noqa: E402
import links  # noqa: E402
import metrics  # noqa: E402
import plans  # noqa: E402
import thumbs  # noqa: E402
import track  # noqa: E402
import uploads  # noqa: E402
import apify
import apis_view
import views  # noqa: E402

SECRET = auth.load_secret(HERE / ".secret")
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
LOGO = HERE.parent / "site" / "assets" / "helv" / "logo-knockout.webp"
STATIC = HERE / "static"
ADMIN_COOKIE = "hv_admin"
VIEWER_COOKIE = "hv_view"
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


class Handler(BaseHTTPRequestHandler):
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
        return {k: v[0] for k, v in urllib.parse.parse_qs(self.body().decode()).items()}

    def send(self, code, body=b"", ctype="text/html; charset=utf-8", headers=None):
        # While a tracked action runs, its answer waits until the change is in
        # the History — otherwise the redirected page could load first.
        if getattr(self, "_held", None) is not None:
            self._held.append((code, body, ctype, headers))
            return
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
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
        self.send(303, b"", "text/plain", h)

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

    def admin(self):
        token = auth.unsign(self.cookies().get(ADMIN_COOKIE, ""), SECRET)
        return db.session(token) if token else None

    def require_admin(self):
        who = self.admin()
        if not who:
            self.redirect("/login")
            return None
        return who

    def viewer_code_id(self):
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

    def do_GET(self):
        path = self.route(urllib.parse.urlparse(self.path).path)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))

        if path.startswith("/go/"):
            return self.go(path[len("/go/"):])
        if path.startswith("/insights/"):
            return self.insights_public(path[len("/insights/"):], query)
        if path == "/api/campaigns":
            return self.api_campaigns()
        if path == "/api/campaign":
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
        if path == "/api/roster":
            return self.api_roster()
        if path == "/api/selection":
            return self.api_selection(
                query.get("s") or "", query.get("n") or "",
                [c for c in (query.get("c") or "").split(",") if c])
        if path == "/health":
            return self.send_json(200, {"ok": True})
        if path == "/static/admin.css":
            return self.send(200, views.CSS, "text/css; charset=utf-8")
        if path.startswith("/static/fonts/") or path == "/static/logo-knockout.webp":
            # Brand fonts and logo, kept with the admin so it does not depend on the built site.
            name = Path(path).name
            f = STATIC / ("fonts/" + name if path.startswith("/static/fonts/") else name)
            if f.is_file() and f.suffix in (".ttf", ".webp"):
                ctype = "font/ttf" if f.suffix == ".ttf" else "image/webp"
                return self.send(200, f.read_bytes(), ctype, [("Cache-Control", "public, max-age=604800")])
            return self.send(404, b"", "text/plain")
        if path == "/static/logo.webp":
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
        if path == "/logout":
            token = auth.unsign(self.cookies().get(ADMIN_COOKIE, ""), SECRET)
            if token:
                db.drop_session(token)
            return self.redirect("/login", [("Set-Cookie", f"{ADMIN_COOKIE}=; Path=/; Max-Age=0")])

        who = self.require_admin()
        if not who:
            return
        views.set_user(who["email"] if "email" in who.keys() else "")

        if path == "/api/search":
            return self.api_search((query.get("q") or "").strip())
        if path == "/":
            return self.send(200, views.dashboard(db.stats(), db.recent_events(12), who))
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
        if path == "/roster/export":
            return self.send(200, self.roster_csv(), "text/csv; charset=utf-8",
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
                currencies=[c for c in fx.CURRENCIES if fx.usable(c)], camp_counts=counts))
        if path == "/selections/edit":
            sid = query.get("id", "")
            sel = db.selection(int(sid)) if sid.isdigit() else None
            if sel is None:
                return self.redirect("/selections?e=" + urllib.parse.quote("That selection no longer exists."))
            return self.send(200, views.selection_edit_page(
                sel, db.list_creators(), db.tier_prices(), self.site_origin(),
                query.get("e"), query.get("ok"), db.campaigns_for_selection(sel["id"])))
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
        if path == "/clients":
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
                db.list_creators(), db.analysis_codes(), db.analysis_requests(), self.site_origin(),
                query.get("q", ""), query.get("e"), query.get("ok"),
                page_no=int(query["page"]) if (query.get("page") or "").isdigit() and int(query["page"]) > 0 else 1))
        if path == "/analysis/template.xlsx":
            code = re.sub(r"[^A-Z0-9-]", "", (query.get("code") or "").upper())[:20] or None
            return self.send(200, analysis.template_xlsx(code),
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             [("Content-Disposition", 'attachment; filename="creator-analysis-%s.xlsx"'
                               % (code or "template"))])
        if path == "/analysis/json":
            code = (query.get("c") or "").upper()
            a = db.analysis(code)
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
        if path == "/settings":
            return self.send(200, views.settings_page(
                db.setting("emv_rates") or {}, metrics.factors(),
                bool(db.setting("capture_token")), db.capture_runs(), track.GEO_DB.exists(),
                None, query.get("e"), query.get("ok"), metrics.benchmarks(), fx_rates=fx.rates()))
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
        if path == "/apis":
            return self.send(200, apis_view.apis_page(query.get("e"), query.get("ok"), query.get("tab", "overview"), query.get("q", "")))
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

    def do_POST(self):
        path = self.route(urllib.parse.urlparse(self.path).path)

        if path == "/api/unlock":
            return self.api_unlock()
        if path == "/api/request":
            return self.api_request()
        if path == "/api/event":
            return self.api_event()
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

        who = self.require_admin()
        if not who:
            return
        history.set_actor(who["email"] if "email" in who.keys() else "admin")
        views.set_user(who["email"] if "email" in who.keys() else "")
        if path == "/history/undo":
            return self.post_history_undo()
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
        if path == "/codes/limits":
            return self.post_code_limits()
        if path == "/codes/device/remove":
            return self.post_device_remove()
        if path == "/roster/save":
            return self.post_roster_save()
        if path == "/selections/new":
            return self.post_selection_new()
        if path == "/selections/save":
            return self.post_selection_save()
        if path == "/selections/delete":
            return self.post_selection_delete()
        if path == "/campaigns/new":
            return self.post_campaign_new()
        if path == "/campaigns/save":
            return self.post_campaign_save()
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
        if path == "/analysis/save":
            return self.post_analysis_save()
        if path == "/analysis/delete":
            return self.post_analysis_delete()
        if path == "/analysis/handled":
            f = self.form_body()
            if (f.get("id") or "").isdigit():
                db.handle_analysis_request(int(f["id"]))
            return self.redirect("/analysis?ok=" + urllib.parse.quote("Marked as handled."))
        if path == "/settings/fx":
            return self.post_settings_fx()
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
        if path == "/roster/merge":
            return self.post_roster_merge()
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
            for args in held:
                self.send(*args)
        return out

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
        ok, msg = history.undo(int(hid)) if hid.isdigit() else (False, "Nothing to undo.")
        back = "/history" + ("?kind=" + urllib.parse.quote(f["kind"]) if f.get("kind") else "")
        sep = "&" if "?" in back else "?"
        return self.redirect(back + sep + ("ok=" if ok else "e=") + urllib.parse.quote(msg))

    # ------------------------------------------------------- admin actions --

    def post_login(self):
        form = self.form_body()
        email = (form.get("email") or "").strip().lower()
        row = db.admin_by_email(email)
        ok = row and auth.verify_password(form.get("password") or "", row["password_hash"])
        # Same delay either way: a fast "no" tells an attacker the email is wrong.
        time.sleep(0.4)
        if not ok:
            db.log("admin_fail", ip=self.client_ip(), user_agent=self.headers.get("User-Agent"),
                   detail=email[:80])
            return self.redirect("/login?e=1")
        db.touch_admin_login(row["id"])
        token = db.create_session(row["id"], ADMIN_TTL)
        cookie = (f"{ADMIN_COOKIE}={auth.sign(token, SECRET)}; Path=/; HttpOnly; "
                  f"SameSite=Lax; Max-Age={ADMIN_TTL}")
        return self.redirect("/", [("Set-Cookie", cookie)])

    def post_password(self):
        who = self.admin()
        form = self.form_body()
        new = form.get("new") or ""
        row = db.admin_by_email(who["email"])
        if not auth.verify_password(form.get("current") or "", row["password_hash"]):
            return self.redirect("/?e=badpass")
        problems = auth.password_problems(new)
        if problems:
            return self.redirect("/?e=" + urllib.parse.quote(" ".join(problems)))
        db.set_admin_password(row["id"], auth.hash_password(new))
        return self.redirect("/?ok=password")

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
        db.create_code(auth.hash_code(code), auth.code_hint(code), label, expires,
                       int(max_uses) if max_uses.isdigit() and int(max_uses) > 0 else None,
                       code_plain=code,
                       max_devices=int(max_devices) if max_devices.isdigit()
                       and int(max_devices) > 0 else None)
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
        jid = int(f["id"]) if (f.get("id") or "").isdigit() else None
        q = urllib.parse.quote
        try:
            if path == "/apis/token":
                apify.save_token(f.get("token"))
                info = apify.test_connection()
                return self.redirect("/apis?tab=apify&ok=" + q("Connected as %s." % (info.get("username") or "your account")))
            if path == "/apis/token/clear":
                apify.clear_token()
                return self.redirect("/apis?tab=apify&ok=" + q("Token removed."))
            if path == "/apis/test":
                i = apify.test_connection()
                bits = [i.get("username") or "connected", i.get("plan") or ""]
                if i.get("used") is not None and i.get("cap") is not None:
                    bits.append("$%.2f of $%.2f used this month" % (i["used"], i["cap"]))
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
                return self.redirect("/apis?tab=apify&ok=" + q("Limits saved."))
            if path == "/apis/pack":
                plats = [p for p in ("Instagram", "TikTok") if f.get("plat_" + p.lower())]
                mh = int(f["max_handles"]) if (f.get("max_handles") or "").isdigit() else 20
                ok, msg = apify.run_pack(plats, f.get("source") or "sample20", max(1, min(mh, apify.HARD_MAX_HANDLES)),
                                         bool(f.get("audience")), bool(f.get("audit")),
                                         f.get("schedule") if f.get("schedule") in ("manual", "daily", "weekly") else "manual",
                                         f.get("at_time") or "03:00", int(f["weekday"]) if (f.get("weekday") or "").isdigit() else 0)
                return self.redirect("/apis?tab=apify&" + ("ok=" if ok else "e=") + q(msg))
            if path == "/apis/job/save":
                apify.save_job(f)
                return self.redirect("/apis?tab=apify&ok=" + q("Job saved."))
            if path == "/apis/job/delete" and jid:
                apify.delete_job(jid)
                return self.redirect("/apis?tab=apify&ok=" + q("Job deleted."))
            if path == "/apis/job/toggle" and jid:
                apify.toggle_job(jid)
                return self.redirect("/apis?tab=apify")
            if path == "/apis/job/run" and jid:
                ok, msg = apify.start_job(jid)
                return self.redirect("/apis?tab=apify&" + ("ok=" if ok else "e=") + q(msg))
            if path == "/apis/refresh":
                n = apify.refresh_all()
                return self.redirect("/apis?tab=apify&ok=" + q("Checked %d running job(s)." % n))
        except apify.ApifyError as ex:
            return self.redirect("/apis?tab=apify&e=" + q(str(ex)))
        return self.redirect("/apis?tab=apify")

    def post_code_archive(self):
        cid = self.form_body().get("id")
        row = db.get_code(int(cid)) if cid and cid.isdigit() else None
        # Revoke first: a live code is never put away by a stray click.
        if row is not None and not db.code_state(row)[0]:
            db.archive_code(row["id"])
        return self.redirect("/codes")

    def post_code_unarchive(self):
        cid = self.form_body().get("id")
        if cid and cid.isdigit():
            db.unarchive_code(int(cid))
        return self.redirect("/codes")

    def post_code_delete(self):
        cid = self.form_body().get("id")
        why = db.delete_code(int(cid)) if cid and cid.isdigit() else "Unknown code."
        return self.redirect("/codes" + ("?e=" + urllib.parse.quote(why) if why else ""))

    def post_code_restore(self):
        cid = self.form_body().get("id")
        if cid and cid.isdigit():
            db.restore_code(int(cid))
        return self.redirect("/codes")

    def post_code_revoke(self):
        cid = self.form_body().get("id")
        if cid and cid.isdigit():
            db.revoke_code(int(cid))
        return self.redirect("/codes")

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
                                  "p_platform", "p_url", "p_followers"))
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
        # Back to the view the edit was made from: same search, same page,
        # scrolled to this creator, with a note saying it saved.
        return self.roster_back(f, code, ok=("Saved " + code + "."))

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

    def roster_csv(self):
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
        return self.redirect("/roster?tab=dupes&ok=" + urllib.parse.quote(
            "Merged %s into %s. Undo from History if it was a mistake." % (", ".join(done) or "nothing", keep)))

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
        d_an, k_an = db.analysis(drop), db.analysis(keep)
        if d_an and not k_an:
            import analysis as analysis_mod, shutil
            db.save_analysis(keep, d_an["data"], d_an["source"])
            src, dst = analysis_mod.MEDIA / drop, analysis_mod.MEDIA / keep
            if src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
                for fn in src.iterdir():
                    shutil.copy(str(fn), str(dst / fn.name))
        with db.connect() as conn:
            conn.execute("UPDATE analysis_requests SET code = ? WHERE code = ?", (keep, drop))
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

    def post_selection_new(self):
        """Re-price a selection a client already has: one they sent as a quote
        request, or one whose link was pasted in. Asking twice for the same
        request reopens the one already priced rather than starting another."""
        f = self.form_body()
        if f.get("mode") == "scratch":
            # A new, empty selection built here: a name, the client, the platform and the currency.
            name = (f.get("name") or "").strip()[:120]
            if not name:
                return self.redirect("/selections?e=" + urllib.parse.quote("Give the selection a name."))
            cid = (f.get("code_id") or "").strip()
            cur = (f.get("currency") or "SAR").strip().upper()
            plat = (f.get("platform") or "").strip() or None
            with history.tracked("selection", None, "Created selection " + name) as t:
                sid = db.save_selection(None, name, [], {}, None, None, code_id=int(cid) if cid.isdigit() else None,
                                        platform=plat if plat in db.PLATFORMS else None)
                db.set_selection_currency(sid, cur if fx.usable(cur) else "SAR")
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
                sid = db.save_selection(None, name, codes, {}, None, None, code_id=k["code_id"],
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
                sel = db.selection(token=parts["s"])
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
        f = self.form_body(multi=("code", "p_from", "p_to", "cost", "drop", "default"))
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
            cost = num(cost)
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
        db.save_selection(sel["id"], name, codes, prices, t_from, t_to, platform=platform,
                          margin=margin, costs=costs, margin_max=margin_max)
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
        return self.redirect("/selections/edit?id=%d&ok=%s" % (sel["id"], urllib.parse.quote(msg)))

    def post_selection_delete(self):
        sid = (self.form_body().get("id") or "").strip()
        if sid.isdigit():
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
            return self.redirect("/campaigns?e=" + urllib.parse.quote("Give the campaign a name."))
        code_id = (f.get("code_id") or "").strip()
        cid = db.create_campaign(name, client=(f.get("client") or "").strip() or None,
                                 code_id=int(code_id) if code_id.isdigit() else None)
        return self.redirect("/campaigns/edit?id=%d" % cid)

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
        vis = {key: f.get("vis_" + key) == "1" for key in ("reach", "clicks", "all_content")}
        vis["emv"] = False                   # EMV is internal only
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
        db.save_campaign(k["id"], visibility=vis, emv={"*": own_rates} if own_rates else None,
                         targets=targets, phase=phase, steps=steps,
                         objective=f.get("objective") if f.get("objective") in metrics.OBJECTIVES else "balanced",
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
        f = self.form_body()
        cid = (f.get("id") or "").strip()
        k = db.campaign(int(cid)) if cid.isdigit() else None
        if k is None:
            return self.redirect("/campaigns")
        back = "/campaigns/content?id=%d" % k["id"]
        url = (f.get("url") or "").strip()
        code = (f.get("code") or "").strip().upper()
        if not re.match(r"^https://[^\s/]+\.[^\s]+$", url):
            return self.redirect(back + "&e=" + urllib.parse.quote("The post link must start with https://"))
        if code not in {m["cc_code"] for m in db.campaign_creators(k["id"])}:
            return self.redirect(back + "&e=" + urllib.parse.quote("Pick a creator in this campaign."))
        platform = f.get("platform") if f.get("platform") in db.PLATFORMS else "Instagram"
        kind = f.get("kind") if f.get("kind") in db.KINDS else "post"
        posted = db.day_bounds(f.get("posted") or "", None)
        item = {"code": code, "platform": platform, "kind": kind, "url": url, "posted_at": posted,
                "caption": (f.get("caption") or "").strip() or None,
                "followers": db.platform_followers(code, platform), **self.counts_from(f)}
        _, created = db.add_content(k["id"], item, source="manual")
        thumbs.fill_later(k["id"])
        return self.redirect(back + "&ok=" + urllib.parse.quote(
            "Post added." if created else "That post was already here — its numbers were updated."))

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
            return self.redirect(back + "&e=" + urllib.parse.quote("Pick a creator in this campaign."))
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
        return self.redirect("/settings?ok=" + urllib.parse.quote("Settings saved."))

    def post_settings_token(self):
        import hashlib, secrets
        token = "hvcap_" + secrets.token_urlsafe(32)
        db.set_setting("capture_token", hashlib.sha256(token.encode()).hexdigest())
        return self.send(200, views.settings_page(
            db.setting("emv_rates") or {}, metrics.factors(), True, db.capture_runs(),
            track.GEO_DB.exists(), token))

    # -------------------------------------------------------- client API --

    def api_campaigns(self):
        """The campaigns this passcode may see. Drafts are never listed."""
        code_id = self.viewer_code_id()
        if code_id is None:
            return self.send_json(401, {"ok": False}, self.cors())
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT token, name, client, status, phase, starts_at, ends_at, logos FROM campaigns "
                "WHERE code_id = ? AND status != 'draft' ORDER BY starts_at DESC", (code_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["logos"] = [self.logo_url(x, r["token"]) for x in db.campaign_logos(r)][:3]
            out.append(d)
        return self.send_json(200, {"ok": True, "campaigns": out},
                              self.cors() + [("Cache-Control", "no-store")])

    def viewer_campaign(self, token):
        code_id = self.viewer_code_id()
        if code_id is None:
            return None, 401
        k = db.campaign(token=token) if token else None
        # Not found and not yours look the same from outside.
        if k is None or k["code_id"] != code_id or k["status"] == "draft":
            return None, 404
        return k, 200

    def api_campaign(self, token):
        k, status = self.viewer_campaign(token)
        if k is None:
            return self.send_json(status, {"ok": False}, self.cors())
        db.log("view", self.viewer_code_id(), self.client_ip(), self.headers.get("User-Agent"),
               "campaign:" + k["name"][:60])
        rep = metrics.client_report(k, photo=links.thumb, photo_large=links.photo)
        rep["campaign"]["logos"] = [self.logo_url(x, k["token"]) for x in rep["campaign"]["logos"]]
        for p in rep["posts"]:
            p["thumb"] = self.thumb_url(p.get("thumb"), k["token"])
        return self.send_json(200, {"ok": True, "report": rep},
                              self.cors() + [("Cache-Control", "no-store")])

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
            return self.redirect(back + "&e=" + urllib.parse.quote("Pick a creator in this campaign."))
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
            return "/assets/clients/" + Path(ref).name
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
        for key in ("template", "objective", "platform", "category", "budget", "links", "source") + \
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
        if k and brief.get("source") != "tiers":
            mix = plans.mix_from_campaign(k)
        else:
            mix = plans.mix_from_counts({t: (str(brief.get("n_" + t) or "").strip() or "0")
                                         for t in plans.TIERS if str(brief.get("n_" + t) or "0").strip().isdigit()})
        plan = plans.calculate(b, mix)
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
        obj = f.get("objective") if f.get("objective") in metrics.OBJECTIVES else metrics.objective_of(k)
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
        typ = f.get("type") if f.get("type") in ("awareness", "engagement", "conversion") else "awareness"
        objective = {"awareness": "awareness", "engagement": "engagement", "conversion": "traffic"}[typ]
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
                             "tracked_links": typ == "conversion"}, plans.mix_from_campaign(k))
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
        k, status = self.viewer_campaign(token)
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
        k, status = self.viewer_campaign(token)
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

    def post_analysis_pdf(self):
        """Profile report PDFs -> analyses. Each file is matched to a creator by
        the handle in its name (report-<handle>-Oct-06-2026.pdf); with one file
        a creator can be picked instead."""
        import profile_pdf
        f = self.form_body(multi=("file",))
        parts = [p for p in (f.get("file") or []) if isinstance(p, dict) and p.get("data")]
        if not parts:
            return self.redirect("/analysis?e=" + urllib.parse.quote("Choose one or more profile report PDFs.") + "#pdf")
        if not profile_pdf.available():
            return self.redirect("/analysis?e=" + urllib.parse.quote(
                "The PDF reader is not installed on this server yet. Ask whoever deploys the admin to install it.") + "#pdf")
        creators = db.list_creators()
        by_handle = {}
        for c in creators:
            h = (c["handle"] or "").strip().lstrip("@").lower()
            if h:
                by_handle[h] = c["code"]
        picked = (f.get("code") or "").strip().upper()
        done, bad = [], []
        for p in parts:
            name = p.get("filename") or "file.pdf"
            m = re.match(r"report-(.+?)-[A-Za-z]{3}-\d\d-\d{4}\.pdf$", name)
            handle = m.group(1) if m else None
            code = picked if (len(parts) == 1 and picked) else by_handle.get((handle or "").lower())
            if not code:
                bad.append(name + " (no creator with handle " + (handle or "?") + " — pick the creator and upload it alone)")
                continue
            try:
                profile_pdf.import_pdf(p["data"], code, handle, source="profile report PDF")
                done.append(code)
            except Exception as ex:
                bad.append(name + " (" + str(ex)[:120] + ")")
        msg = "Imported %d analysis%s: %s." % (len(done), "" if len(done) == 1 else "es", ", ".join(done)) if done else ""
        if bad:
            return self.redirect("/analysis?%s=%s#pdf" % ("ok" if done else "e", urllib.parse.quote(
                (msg + " " if msg else "") + "Could not import: " + "; ".join(bad))))
        return self.redirect("/analysis?ok=" + urllib.parse.quote(msg))

    def post_analysis_upload(self):
        f = self.form_body()
        part = f.get("file")
        if not isinstance(part, dict) or not part.get("data"):
            return self.redirect("/analysis?e=" + urllib.parse.quote("Choose the filled-in template (.xlsx)."))
        known = {c["code"] for c in db.list_creators()}
        try:
            docs, problems = analysis.parse_workbook(part["data"], known)
        except Exception as ex:
            return self.redirect("/analysis?e=" + urllib.parse.quote(str(ex)[:200]))
        if not docs:
            return self.redirect("/analysis?e=" + urllib.parse.quote(
                "No creators found in that file. " + " ".join(problems[:5])))
        with db.connect() as conn:
            for code, d in docs.items():
                db.save_analysis(code, d, d.get("source") or "template upload", conn)
        msg = "Saved full analysis for %d creator(s)." % len(docs)
        if problems:
            msg += " Skipped: " + " ".join(problems[:6])
        return self.redirect("/analysis?ok=" + urllib.parse.quote(msg))

    def post_analysis_save(self):
        f = self.form_body()
        code = (f.get("code") or "").strip().upper()
        if db.creator(code) is None:
            return self.redirect("/analysis?e=" + urllib.parse.quote("Unknown creator code."))
        try:
            doc = analysis.clean_json(json.loads(f.get("json") or "{}"))
        except ValueError as ex:
            return self.redirect("/analysis?q=%s&e=%s" % (code, urllib.parse.quote(str(ex))))
        db.save_analysis(code, doc, doc.get("source") or "pasted JSON")
        return self.redirect("/analysis?q=%s&ok=%s" % (code, urllib.parse.quote("Analysis saved for " + code + ".")))

    def post_analysis_delete(self):
        code = (self.form_body().get("code") or "").strip().upper()
        db.delete_analysis(code)
        return self.redirect("/analysis?ok=" + urllib.parse.quote("Analysis removed for " + code + "."))

    def api_creator(self, code):
        """One creator for the analysis page: the public card facts always,
        the full analysis when one is uploaded."""
        code_id = self.viewer_code_id()
        if code_id is None:
            return self.send_json(401, {"ok": False}, self.cors())
        r = db.creator(code)
        if r is None or not r["active"]:
            return self.send_json(404, {"ok": False}, self.cors())
        a = db.analysis(code)
        with db.connect() as conn:
            asked = conn.execute("SELECT 1 FROM analysis_requests WHERE code = ? AND code_id = ? "
                                 "AND handled_at IS NULL", (code, code_id)).fetchone() is not None
        db.log("view", code_id, self.client_ip(), self.headers.get("User-Agent"), "analysis:" + code)
        card = {"code": r["code"], "name": r["name"], "tier": r["tier"], "city": r["city"],
                "nationality": r["nationality"], "interest": r["interest"], "followers": r["followers"],
                "photo_url": links.photo(r["photo"]) if r["photo"] else None,
                "profiles": db.split_profiles(r["profiles"]),
                "band": metrics.band_of(r["followers"])}
        return self.send_json(200, {"ok": True, "creator": card,
                                    "analysis": analysis.with_media_urls(a["data"], r["code"], BASE) if a else None,
                                    "updated_at": a["updated_at"] if a else None,
                                    "requested": asked,
                                    "benchmarks": metrics.benchmarks()},
                              self.cors() + [("Cache-Control", "no-store")])

    def api_creator_media(self, code, name):
        """A picture from a creator's analysis — post cover, photo or brand
        logo — for a viewer who has unlocked the catalogue."""
        if self.viewer_code_id() is None:
            return self.send(401, b"", "text/plain")
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
        if db.creator(code) is None:
            return self.send_json(404, {"ok": False}, self.cors())
        db.request_analysis(code, code_id)
        db.log("shortlist", code_id, self.client_ip(), self.headers.get("User-Agent"), "analysis request:" + code)
        return self.send_json(200, {"ok": True}, self.cors())

    def post_campaign_delete(self):
        cid = (self.form_body().get("id") or "").strip()
        if cid.isdigit():
            db.delete_campaign(int(cid))
        return self.redirect("/campaigns?ok=" + urllib.parse.quote("Campaign deleted."))

    def api_selection(self, token, name=None, codes=None):
        """A priced selection, for the client's page — by its token, or by the
        name and creators of a link the client already holds. Behind the same
        passcode as the roster: the link alone shows nothing."""
        viewer = self.viewer_code_id()
        if not viewer:
            return self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
        if token:
            sel = db.selection(token=token)
            # Prices agreed with one client are for that client. The token is
            # in a link, and a link travels; the passcode is what identifies
            # who is reading it.
            if sel is not None and sel["code_id"] is not None:
                try:
                    if int(viewer) != sel["code_id"]:
                        sel = None
                except (TypeError, ValueError):
                    sel = None
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
        by = {c["code"]: c for c in db.list_creators(active_only=True)}
        codes = [c for c in json.loads(sel["codes"] or "[]") if c in by]
        own = json.loads(sel["prices"] or "{}")
        platform = sel["platform"] if "platform" in sel.keys() else None
        prices = {}
        for c in codes:
            p = own.get(c) or db.price_for(by[c], bands, platform)
            if p:
                prices[c] = list(p)
        total = ([sel["total_from"], sel["total_to"]]
                 if sel["total_from"] is not None else None)
        return self.send_json(200, {"ok": True, "name": sel["name"], "codes": codes,
                                    "prices": prices, "total": total,
                                    "platform": platform,
                                    "currency": (sel["currency"] if "currency" in sel.keys() else None) or "SAR",
                                    "fx": fx.rates(),
                                    "token": sel["token"]}, self.cors())

    def post_request_handled(self):
        f = self.form_body()
        if (f.get("id") or "").isdigit():
            db.mark_handled(int(f["id"]), f.get("handled") == "1")
        return self.redirect("/requests")

    # ---------------------------------------------------------- public API --

    def api_unlock(self):
        body = self.json_body()
        code = (body.get("code") or "").strip()
        # The campaign report only needs the pass, not the whole roster.
        lite = bool(body.get("lite"))
        row = None
        if code:
            row = (db.code_by_hash(auth.hash_code(code))
                   or db.code_by_hash(auth.legacy_hash_code(code)))
        ok, reason = db.code_state(row)
        ua = self.headers.get("User-Agent")
        if not ok:
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
        return self.send_json(200, payload,
                              self.cors() + [("Set-Cookie", cookie),
                                             ("Set-Cookie", dev_cookie)])

    def api_roster(self):
        code_id = self.viewer_code_id()
        if not code_id:
            return self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
        return self.send_json(200, {"ok": True, "roster": self.roster_payload(),
                                    "tiers": self.tier_payload(), "fx": fx.rates()}, self.cors())

    def tier_payload(self):
        """Sent with the roster so the page totals a selection at today's
        rates rather than whatever was hard-coded when it was built."""
        return [
            {"name": t["name"], "from": t["price_from"], "to": t["price_to"],
             "reach": t["reach"]}
            for t in db.list_tiers()
        ]

    def roster_payload(self, platform=None):
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
            }
            for r in db.list_creators(active_only=True)
        ]

    # Measuring 154 files on every unlock would be wasteful and they rarely
    # change, so the widths are read once and dropped whenever a photo is
    # written. Instagram hands back a 100px thumbnail on one path and 320px on
    # another; a 100px source stretched across a 330px card is the pixelation,
    # and the card treats those differently rather than upscaling them.
    _widths = {}

    @classmethod
    def forget_photo_widths(cls):
        cls._widths = {}

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
        rid = db.create_request(
            code_id, b.get("name"), b.get("company"), b.get("email"), b.get("phone"),
            b.get("selection_name"), [str(c)[:40] for c in selection[:200]],
        )
        db.log("request", code_id, self.client_ip(), self.headers.get("User-Agent"), str(rid))
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

    def api_selection_save(self):
        """A client naming a shortlist. It is recorded here so it appears in
        the dashboard by itself, ready to be priced, instead of an admin having
        to paste the link. Re-saving the same one — the client went back and
        added a creator — updates it rather than making another."""
        viewer = self.viewer_code_id()
        if not viewer:
            return self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
        b = self.json_body()
        name = (str(b.get("name") or "Selection")).strip()[:120] or "Selection"
        known = {c["code"] for c in db.list_creators(active_only=True)}
        codes, seen = [], set()
        for c in (b.get("codes") or [])[:200]:
            c = str(c).strip().upper()
            if c in known and c not in seen:
                seen.add(c); codes.append(c)
        if not codes:
            return self.send_json(400, {"ok": False, "reason": "empty"}, self.cors())

        token = (str(b.get("token") or "")).strip()
        sel = db.selection(token=token) if token else None
        if sel is not None and sel["code_id"] is not None and sel["code_id"] != viewer:
            sel = None                      # another client's selection: never touched
        if sel is None:
            sel = db.selection_for_link(name, codes, viewer)
        if sel is None:
            sid = db.save_selection(None, name, codes, {}, None, None, None, viewer)
            return self.send_json(200, {"ok": True, "token": db.selection(sid)["token"]},
                                  self.cors())

        prices = {k: v for k, v in json.loads(sel["prices"] or "{}").items() if k in codes}
        stored = json.loads(sel["codes"] or "[]")
        same = sorted(stored) == sorted(codes)
        # A total typed for one shortlist cannot stand for a different one, so
        # a client adding or removing a creator returns it to the sum of the
        # prices — which the admin can type again.
        t_from = sel["total_from"] if same else None
        t_to = sel["total_to"] if same else None
        db.save_selection(sel["id"], name, codes, prices, t_from, t_to)
        return self.send_json(200, {"ok": True, "token": sel["token"]}, self.cors())

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
    "/campaigns/content/bulk": ("campaign", "id", "Bulk-added posts or numbers"),
    "/campaigns/content/pending": ("campaign", "id", "Updated who is still to post"),
    "/campaigns/insights/decide": ("campaign", "id", "Reviewed insights"),
    "/campaigns/insights/upload": ("campaign", "id", "Uploaded insights"),
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
    args = ap.parse_args()

    db.init()
    history.init()
    apify.start_scheduler()
    db.purge_expired_sessions()
    ALLOWED_ORIGINS.update(args.origin)
    global BASE
    BASE = "/" + args.base_path.strip("/") if args.base_path.strip("/") else ""
    views.set_base(BASE)

    if db.admin_count() == 0:
        print("No admin yet. Create one:\n  python3 admin/seed.py --email you@example.com")

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"admin  http://{args.host}:{args.port}{BASE or ''}")
    print(f"origins allowed: {', '.join(ALLOWED_ORIGINS) or '(any — set --origin in production)'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
