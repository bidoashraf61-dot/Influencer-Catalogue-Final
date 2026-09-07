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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import auth  # noqa: E402
import importer  # noqa: E402
import db  # noqa: E402
import uploads  # noqa: E402
import views  # noqa: E402

SECRET = auth.load_secret(HERE / ".secret")
# Photos live with the built site so the catalogue and the dashboard share one
# copy — uploading here updates what a client sees.
PHOTO_DIR = HERE.parent / "site" / "assets" / "catalogue"
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
                return self.send(200, f.read_bytes(), "image/jpeg",
                                 [("Cache-Control", "no-cache")])
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
            return self.send(200, views.roster_page(
                db.list_creators(), query.get("e"), query.get("ok"),
                cities=db.known_cities(), tiers=db.list_tiers()))
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
        return self.send(404, views.simple("Not found", "That page does not exist."))

    def do_POST(self):
        path = self.route(urllib.parse.urlparse(self.path).path)

        if path == "/api/unlock":
            return self.api_unlock()
        if path == "/api/request":
            return self.api_request()
        if path == "/api/event":
            return self.api_event()
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
        expires = db.now() + int(days) * 86400 if days.isdigit() and int(days) > 0 else None
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

    def post_roster_save(self):
        f = self.form_body(multi=("city",))
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
                return self.redirect("/roster?e=" + urllib.parse.quote(
                    "Could not assign a code — try again."))

        existing = db.creator(code)
        photo = (existing["photo"] if existing else None)
        saved, err = uploads.save_photo(f.get("photo_file"), code, PHOTO_DIR)
        if saved:
            Handler.forget_photo_widths()
        if err:
            return self.redirect("/roster?e=" + urllib.parse.quote(err))
        if saved:
            photo = saved
        elif (f.get("photo") or "").strip():
            photo = f["photo"].strip()

        followers = (f.get("followers") or "").replace(",", "").strip()
        db.upsert_creator({
            "code": code,
            "name": (f.get("name") or "").strip(),
            "handle": (f.get("handle") or "").strip().lstrip("@"),
            "platform": (f.get("platform") or "Instagram").strip(),
            "followers": int(followers) if followers.isdigit() else None,
            # Ticked boxes plus anything typed into "add a city". Both go
            # through join_cities, so the separator is decided in one place.
            "city": db.join_cities(
                list(f.get("city") or []) + db.split_cities(f.get("city_new") or "")) or None,
            "tier": tier,
            "interest": (f.get("interest") or "").strip() or None,
            "photo": photo or None,
            "active": 1 if f.get("active") else 0,
            "note": (f.get("note") or "").strip() or None,
            "sort": int(f["sort"]) if (f.get("sort") or "").isdigit() else 0,
        })
        return self.redirect("/roster")

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
        for i, r in enumerate(rows):
            code = r["code"]
            if code and db.creator(code):
                updated += 1
            else:
                if not code:
                    code = db.next_code(r["tier"])
                added += 1

            existing = db.creator(code)
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
            db.upsert_creator(dict(fields, code=code, photo=photo, sort=i))

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
            w.writerow([
                c["code"], c["name"], c["platform"], c["handle"] or "",
                c["followers"] if c["followers"] is not None else "",
                db.join_cities(db.split_cities(c["city"])), c["tier"],
                c["interest"] or "",
                c["note"] or "", "yes" if c["active"] else "no",
                "on file" if c["photo"] else "",
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
        db.save_tier(name, code, lo, hi, reach,
                     int(sort) if sort.lstrip("-").isdigit() else 0)
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
        code = self.form_body().get("code")
        if code:
            db.delete_creator(code)
        return self.redirect("/roster")

    def post_request_handled(self):
        f = self.form_body()
        if (f.get("id") or "").isdigit():
            db.mark_handled(int(f["id"]), f.get("handled") == "1")
        return self.redirect("/requests")

    # ---------------------------------------------------------- public API --

    def api_unlock(self):
        code = (self.json_body().get("code") or "").strip()
        row = db.code_by_hash(auth.hash_code(code)) if code else None
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
        return [
            {
                "code": r["code"], "name": r["name"], "handle": r["handle"],
                "platform": r["platform"], "followers": r["followers"],
                "city": r["city"], "tier": r["tier"], "interest": r["interest"],
                "photo": r["photo"], "lowres": self.is_lowres(r["photo"]),
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

    def api_event(self):
        code_id = self.viewer_code_id()
        if not code_id:
            return self.send_json(401, {"ok": False}, self.cors())
        b = self.json_body()
        kind = b.get("kind")
        if kind not in ("view", "shortlist"):
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
