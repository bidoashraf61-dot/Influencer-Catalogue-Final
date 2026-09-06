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

# Mirrors TIERS in build/influencer_catalogue.py. Kept here so the dashboard can
# price a selection without importing the static build.
TIER_PRICE = {
    "Nano": (435, 870),
    "Micro": (870, 1740),
    "Mid-Tier": (1450, 2900),
    "Macro": (2175, 4350),
}


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
            days = int(query.get("days", 30))
            return self.send(200, views.analytics_page(db.stats(days), db.recent_events(200), days))
        if path == "/roster":
            return self.send(200, views.roster_page(
                db.list_creators(), query.get("e"), query.get("ok")))
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
                                                      db.list_creators(), TIER_PRICE))
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
                       int(max_uses) if max_uses.isdigit() and int(max_uses) > 0 else None)
        # Shown once. It is stored only as a hash, so it cannot be shown again.
        return self.redirect("/codes?new=" + urllib.parse.quote(code))

    def post_code_revoke(self):
        cid = self.form_body().get("id")
        if cid and cid.isdigit():
            db.revoke_code(int(cid))
        return self.redirect("/codes")

    def post_roster_save(self):
        f = self.form_body()
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
            "city": (f.get("city") or "").strip(),
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

        # Two indexes, so a file can be named either way. Handles are matched
        # case-insensitively because a download tends to lowercase them.
        by_code, by_handle = {}, {}
        for c in db.list_creators():
            by_code[c["code"].upper()] = c["code"]
            if c["handle"]:
                by_handle.setdefault(c["handle"].lower(), []).append(c["code"])

        saved, unmatched, rejected, ambiguous = 0, [], [], []
        for part in parts:
            name = Path(part["filename"]).name
            stem = Path(name).stem.strip()
            key = stem.upper()
            code = by_code.get(key)
            if not code:
                hits = by_handle.get(stem.lower().lstrip("@"), [])
                if len(hits) > 1:
                    # Two creators on the same handle across platforms. Guessing
                    # would silently put the photo on the wrong card.
                    ambiguous.append(name)
                    continue
                code = hits[0] if hits else None
            if not code:
                unmatched.append(name)
                continue

            ok, why = uploads.photo_bytes(part["data"])
            if not ok:
                rejected.append(name + " (" + why + ")")
                continue

            filename = uploads.write_photo(part["data"], code, PHOTO_DIR)
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
        msg += listing("Ambiguous handle, skipped", ambiguous)
        msg += listing("Rejected", rejected)

        key = "ok" if saved else "e"
        return self.redirect("/roster?" + key + "=" + urllib.parse.quote(msg))

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
                                    "roster": self.roster_payload()},
                              self.cors() + [("Set-Cookie", cookie)])

    def api_roster(self):
        code_id = self.viewer_code_id()
        if not code_id:
            return self.send_json(401, {"ok": False, "reason": "locked"}, self.cors())
        return self.send_json(200, {"ok": True, "roster": self.roster_payload()}, self.cors())

    def roster_payload(self):
        return [
            {
                "code": r["code"], "name": r["name"], "handle": r["handle"],
                "platform": r["platform"], "followers": r["followers"],
                "city": r["city"], "tier": r["tier"], "interest": r["interest"],
                "photo": r["photo"],
            }
            for r in db.list_creators(active_only=True)
        ]

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
