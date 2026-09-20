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
  /api/unlock           POST {code}   -> sets a viewer cookie, returns roster
  /api/roster           GET           -> roster, viewer cookie required
  /api/request          POST          -> store a quote request
  /api/event            POST          -> record a shortlist action

The roster is served only after a code is checked HERE. That is the difference
between this and the static build: on the static site the passcode is a hash in
the JavaScript and the data sits in the page regardless. Expiry, revocation and
analytics are only meaningful because the check happens server-side.
"""

import argparse
import html
import json
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
import links  # noqa: E402
import uploads  # noqa: E402
import views  # noqa: E402

SECRET = auth.load_secret(HERE / ".secret")
# Photos live with the built site so the catalogue and the dashboard share one
# copy — uploading here updates what a client sees.
PHOTO_DIR = HERE.parent / "site" / "assets" / "catalogue"

# How many creators the roster shows at once. The whole list on one page came
# to 311KB of HTML and 757 thumbnails at 759 creators, and grows in a straight
# line: 1.8MB and 5,000 thumbnails at 5,000 creators. Paging keeps the page the
# same size however far the roster grows.
ROSTER_PAGE = 100
links.PHOTO_DIR = PHOTO_DIR
LOGO = HERE.parent / "site" / "assets" / "helv" / "logo-knockout.webp"
ADMIN_COOKIE = "hv_admin"
VIEWER_COOKIE = "hv_view"
ADMIN_TTL = 12 * 3600
VIEWER_TTL = 12 * 3600

# Where the catalogue is served from. The API is called cross-origin from it,
# so it must be named explicitly — "*" cannot be used with credentials.
ALLOWED_ORIGINS = set()

# When the dashboard is served under a path (e.g. /admin) rather than its own
# subdomain, every route and redirect has to carry that prefix. Serving it on
# the catalogue's own domain means the API is same-origin: no CORS, and the
# viewer cookie can be SameSite=Lax instead of None.
BASE = ""

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
        # behind nginx the socket address is the proxy, not the visitor
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() if fwd else self.client_address[0]

    def body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

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
        code_id, _, expiry = raw.partition(":")
        if not expiry.isdigit() or int(expiry) < db.now():
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

        if path == "/":
            return self.send(200, views.dashboard(db.stats(), db.recent_events(12), who))
        if path == "/codes":
            return self.send(200, views.codes_page(db.list_codes(), query.get("new"), query.get("e")))
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
            everyone = db.list_creators(search=query.get("q"))
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
                page_no=page, pages=pages, total=total, per_page=ROSTER_PAGE))
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
            return self.send(200, views.selections_page(
                db.list_selections(), query.get("e"), query.get("ok"), self.site_origin()))
        if path == "/selections/edit":
            sid = query.get("id", "")
            sel = db.selection(int(sid)) if sid.isdigit() else None
            if sel is None:
                return self.redirect("/selections?e=" + urllib.parse.quote("That selection no longer exists."))
            return self.send(200, views.selection_edit_page(
                sel, db.list_creators(), db.tier_prices(), self.site_origin(),
                query.get("e"), query.get("ok")))
        return self.send(404, views.simple("Not found", "That page does not exist."))

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
        if path == "/login":
            return self.post_login()

        who = self.require_admin()
        if not who:
            return

        if path == "/codes/new":
            return self.post_code_new()
        if path == "/codes/revoke":
            return self.post_code_revoke()
        if path == "/roster/save":
            return self.post_roster_save()
        if path == "/selections/new":
            return self.post_selection_new()
        if path == "/selections/save":
            return self.post_selection_save()
        if path == "/selections/delete":
            return self.post_selection_delete()
        if path == "/roster/delete":
            return self.post_roster_delete()
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
                       code_plain=code)
        return self.redirect("/codes?new=" + urllib.parse.quote(code))

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
                        stale.unlink()
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
                                    ok=code + " deleted.")
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
        f = self.form_body(multi=("code", "p_from", "p_to", "drop"))
        sid = (f.get("id") or "").strip()
        sel = db.selection(int(sid)) if sid.isdigit() else None
        if sel is None:
            return self.redirect("/selections")

        def num(v):
            v = "".join(ch for ch in (v or "") if ch.isdigit())
            return int(v) if v else None

        codes, prices = [], {}
        known = {c["code"] for c in db.list_creators()}
        rows = zip(f.get("code") or [], f.get("p_from") or [], f.get("p_to") or [])
        remove = set(f.get("drop") or [])
        for code, lo, hi in rows:
            code = code.strip().upper()
            if not code or code in codes or code in remove or code not in known:
                continue
            codes.append(code)
            lo, hi = num(lo), num(hi)
            if lo is None and hi is not None: lo = hi
            if hi is None and lo is not None: hi = lo
            if lo is not None:
                prices[code] = sorted([lo, hi])
        for c in re.findall(r"HV-[A-Z0-9]{2,4}-\d+", (f.get("add") or "").upper()):
            if c in known and c not in codes:
                codes.append(c)
        t_from, t_to = num(f.get("total_from")), num(f.get("total_to"))
        if t_from is None and t_to is not None: t_from = t_to
        if t_to is None and t_from is not None: t_to = t_from
        if t_from is not None and t_to < t_from: t_from, t_to = t_to, t_from
        name = (f.get("name") or "").strip() or sel["name"]
        db.save_selection(sel["id"], name, codes, prices, t_from, t_to)
        return self.redirect("/selections/edit?id=%d&ok=%s" % (sel["id"], urllib.parse.quote("Saved.")))

    def post_selection_delete(self):
        sid = (self.form_body().get("id") or "").strip()
        if sid.isdigit():
            db.delete_selection(int(sid))
        return self.redirect("/selections?ok=" + urllib.parse.quote("Selection deleted."))

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
        prices = {}
        for c in codes:
            p = own.get(c) or db.price_of(by[c], bands)
            if p:
                prices[c] = list(p)
        total = ([sel["total_from"], sel["total_to"]]
                 if sel["total_from"] is not None else None)
        return self.send_json(200, {"ok": True, "name": sel["name"], "codes": codes,
                                    "prices": prices, "total": total,
                                    "token": sel["token"]}, self.cors())

    def post_request_handled(self):
        f = self.form_body()
        if (f.get("id") or "").isdigit():
            db.mark_handled(int(f["id"]), f.get("handled") == "1")
        return self.redirect("/requests")

    # ---------------------------------------------------------- public API --

    def api_unlock(self):
        code = (self.json_body().get("code") or "").strip()
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

        db.bump_code_use(row["id"])
        db.log("unlock_ok", row["id"], self.client_ip(), ua)
        expiry = db.now() + VIEWER_TTL
        if row["expires_at"]:
            expiry = min(expiry, row["expires_at"])
        ticket = auth.sign("%d:%d" % (row["id"], expiry), SECRET)
        max_age = max(0, expiry - db.now())
        # Cross-origin needs SameSite=None, which needs Secure, which needs
        # HTTPS. Same-origin needs none of that and is the safer default.
        policy = "SameSite=None; Secure" if ALLOWED_ORIGINS else "SameSite=Lax"
        cookie = (f"{VIEWER_COOKIE}={ticket}; Path=/; HttpOnly; "
                  f"{policy}; Max-Age={max_age}")
        return self.send_json(200, {"ok": True, "label": row["label"],
                                    "roster": self.roster_payload(),
                                    "tiers": self.tier_payload()},
                              self.cors() + [("Set-Cookie", cookie)])

    def api_roster(self):
        code_id = self.viewer_code_id()
        if not code_id:
            return self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
        return self.send_json(200, {"ok": True, "roster": self.roster_payload(),
                                    "tiers": self.tier_payload()}, self.cors())

    def tier_payload(self):
        """Sent with the roster so the page totals a selection at today's
        rates rather than whatever was hard-coded when it was built."""
        return [
            {"name": t["name"], "from": t["price_from"], "to": t["price_to"],
             "reach": t["reach"]}
            for t in db.list_tiers()
        ]

    def roster_payload(self):
        bands = db.tier_prices()
        return [
            {
                "code": r["code"], "name": r["name"], "handle": r["handle"],
                "platform": r["platform"], "followers": r["followers"],
                "city": r["city"], "nationality": r["nationality"],
                "tier": r["tier"], "interest": r["interest"],
                "photo": r["photo"], "lowres": self.is_lowres(r["photo"]),
                # The page builds no photo URL of its own any more. Every code
                # is HV-XX-NNN, so the pattern was walkable and the whole set
                # could be pulled without a passcode; nginx now refuses a photo
                # this service did not sign.
                "photo_url": links.photo(r["photo"]) if r["photo"] else None,
                # This creator's price: their own rate if one is set, their
                # tier's band otherwise. The page prices a selection from this.
                "price": list(db.price_of(r, bands) or []) or None,
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
        return bool(w) and w <= 150

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
