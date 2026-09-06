# Influencer Catalogue Admin

A dashboard for issuing access codes, watching who opens the catalogue,
editing the roster and reading quote requests — plus the API that makes those
things real rather than decorative.

**Stdlib Python only.** No pip install, no build step, no framework. It runs
anywhere Python 3.8+ exists.

```bash
python3 admin/seed.py --email you@hellovoice.co.uk   # create the first admin
python3 admin/seed.py --import-roster                # load the 162 creators
python3 admin/server.py --port 8900 --base-path /admin
```

The dashboard is then at `/admin` **on the catalogue's own domain** — see §2.

---

## 1. Why this exists, and what changed

The static catalogue checks its passcode **in the browser**. The roster sits in
the page whether or not you type anything, so:

- the passcode stops a link being forwarded, and nothing else
- an expiry date could be defeated by changing the computer's clock
- revoking access meant rebuilding and re-uploading the whole site
- nothing was recorded, so "did the client actually look?" was unanswerable

With this service the roster is **served only after the server has checked the
code**. That single change is what makes expiry, revocation and analytics
mean anything. A revoked code stops working on the client's very next request —
verified, not assumed.

The old static build still exists and still works. Nothing here forces you off
it; the two can run side by side while you decide.

---

## 2. Deploying behind nginx / openresty

The dashboard lives at `/admin` on the same hostname as the catalogue. That is
not just tidier than a second subdomain — it is the safer arrangement:

- **no CORS.** The catalogue calls `/api/*` on its own origin, so there is no
  preflight, no reflected `Access-Control-Allow-Origin`, no allow-list to keep
  correct.
- **no cross-site cookies.** The viewer ticket can be `SameSite=Lax` instead of
  `SameSite=None; Secure`. `None` means the cookie rides along on requests
  originating from any other site; `Lax` does not. Browsers are steadily
  tightening on `None`, and this setup never needs it.
- **no new DNS record and no second certificate.**

`--base-path /admin` makes every link, form action, redirect and asset the
dashboard emits carry the prefix — creator photos included, so one nginx
location covers the whole dashboard. `/api/*` is deliberately **not** prefixed:
the catalogue calls it at the root of the domain, so nginx routes it separately.
Without `--base-path` the service still serves at the root exactly as before;
both layouts are tested.

### The service

```ini
# /etc/systemd/system/hv-catalogue.service
[Unit]
Description=HelloVoice catalogue admin
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/srv/hv-catalogue
ExecStart=/usr/bin/python3 /srv/hv-catalogue/admin/server.py \
          --port 8900 --base-path /admin
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now hv-catalogue
```

### The proxy

Two locations reach the service; everything else is the static catalogue.

```nginx
server {
    server_name ugc-catalogue.hellovoice.co.uk;

    # the catalogue itself — the dist/ tree
    root /srv/hv-catalogue/dist;
    location / { try_files $uri $uri/ =404; }

    # the dashboard
    location /admin { proxy_pass http://127.0.0.1:8900; include /etc/nginx/hv-proxy.conf; }

    # the API the catalogue calls: unlock, roster, request, event
    location /api/  { proxy_pass http://127.0.0.1:8900; include /etc/nginx/hv-proxy.conf; }
}
```

```nginx
# /etc/nginx/hv-proxy.conf
proxy_set_header Host              $host;
proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

`X-Forwarded-For` matters: without it every event logs the proxy's address
instead of the visitor's, and the analytics page becomes a list of `127.0.0.1`.

**Serve it over HTTPS.** Admin sessions and viewer tickets are cookies; over
plain HTTP they are readable in transit.

### If you do want a separate hostname

Run it at the root (drop `--base-path`) and name the catalogue's origin with
`--origin https://ugc-catalogue.hellovoice.co.uk`, repeatable. That switches the
viewer cookie to `SameSite=None; Secure`, which needs HTTPS on both sides. With
no `--origin` at all the service reflects any origin — convenient locally, wrong
in production, and the startup banner says so.

## 3. Access codes

Generated as `XXXX-XXXX-XXXX` from an alphabet with no `0/O` or `1/I/l`, because
these get read down a phone.

**Only a hash is stored.** The code is shown once, when you create it, and
cannot be recovered — the same reasoning as a password. Lose it and issue
another. The list shows the last four characters so a row is identifiable.

A code can carry an expiry, a maximum number of uses, or neither. Each unlock
re-checks state, so revoking is immediate even for someone already holding a
valid session cookie.

`unknown`, `expired`, `revoked` and `exhausted` are returned to the client
distinctly. A client seeing *"this code expired"* can ask for a new one; a
flat "wrong code" wastes everybody's time, and an attacker learns nothing they
could not learn by trying.

---

## 4. The roster

### Codes are assigned, not typed

Adding a creator no longer asks for a code. It is derived from the tier and
what is already stored — `HV-NA-029` follows the highest existing `HV-NA-*` —
so two people adding at once cannot collide, and a code is never mistyped. On
edit the code is read-only: it is the identity a client quoted back to you, and
changing it would orphan every past request.

### Photos

Upload straight from the roster form. Files are checked by **magic bytes, not
extension**, and land in `site/assets/catalogue/<CODE>.jpg` — the same folder
the built catalogue reads, so uploading here changes what a client sees.

Limit 6MB. JPEG, PNG, WebP and GIF are accepted; anything else is rejected with
a plain message rather than being written and rendering broken.

### Attaching photos in bulk

Select a whole folder of images at once. Each file is matched to a creator by
its **filename**:

| file | matches |
|---|---|
| `HV-NA-001.jpg` | that code |
| `noha.mgdi.jpg` | that handle, case-insensitively |

Whatever matches nothing is **listed back by name**, not silently dropped —
a batch that quietly attached 44 of 50 photos and said "done" would be worse
than one that failed outright. Files are checked by the same magic bytes and
6MB limit as a single upload, and a rejected file writes nothing: no image on
disk, no change to the row.

A handle shared by two creators across platforms is skipped rather than
guessed, because guessing puts a photo on the wrong card.

### Bulk import

Download the CSV template from the roster page, fill it in, upload it.

**The template has no photo column, and cannot have one.** A spreadsheet cell
holds text; a photo is bytes. So an import brings in every field except the
image, and *Attach photos in bulk* on the same page covers the rest.

- **A blank code is assigned automatically**; an existing code updates that
  creator rather than duplicating them.
- **A photo already on file survives a re-import** — the sheet has no photo
  column, and losing 154 photos to a spreadsheet upload would be a bad day.
- **Nothing is written unless every row is valid.** A bad tier or a
  non-numeric follower count rejects the whole file and names the rows. A
  half-imported roster is harder to recover from than a rejected upload.
- `.xlsx` works **only if openpyxl is installed on the server**. It is not a
  stdlib module, so if it is missing the uploader is told to save as CSV
  rather than meeting a silent failure. CSV always works.
- The template ships with a UTF-8 BOM so Excel does not mangle Arabic city
  names, and the parser accepts `;` delimiters for locales that export that way.

---

## 5. What is recorded

| event | when |
|---|---|
| `unlock_ok` | a valid code opened the catalogue |
| `unlock_fail` | a code was refused, with the reason |
| `shortlist` | a creator was added to a selection |
| `request` | a quote request was submitted |
| `admin_fail` | a failed dashboard login |

Each row keeps the code, timestamp, IP and user agent. That is enough to answer
"did Alpha Plus open it, and when" without becoming surveillance: no
fingerprinting, no third-party analytics, nothing leaves the server.

---

## 6. Security notes, honestly

- **Passwords** are PBKDF2-HMAC-SHA256, 240k iterations, per-user salt.
  `hashlib.scrypt` would be the better primitive but is missing from some
  Python builds, including macOS's system Python — an unavailable "better"
  algorithm is worse than a present good one.
- **Cookies** are HMAC-signed; a tampered one is rejected. Verified in tests.
- **Sessions** live in the database and can be dropped server-side. The signing
  secret is generated on first run into `admin/.secret` (mode 600). Delete it
  to sign everyone out.
- **Login timing** is padded so a wrong email and a wrong password take the
  same time.
- **Escaping**: every value rendered goes through `e()`. There is no template
  path that emits raw input.
- **Not implemented**: rate limiting on `/api/unlock`. Codes are 31^12, so
  guessing is impractical, but a determined attacker can still make noise in
  your logs. Put a `limit_req` zone in nginx if that matters.
- **The database is the crown jewels.** It holds names, handles, follower
  counts and every quote request. Back up `admin/catalogue.db`; it is a single
  file. Do not commit it.

---

## 7. Wiring the catalogue to it

Done. Build with the service's URL and the pages stop embedding the roster:

```bash
CATALOGUE_API="https://ugc-catalogue.hellovoice.co.uk" python3 build/influencer_catalogue.py
python3 build/catalogue_dist.py
```

With the same-origin layout of §2 that URL is the catalogue's own domain, so
every `/api/*` call is same-origin. On a separate hostname, point it at that
hostname instead and pass the matching `--origin` to the service.

What changes:

- the page ships **no creators at all** — 40KB instead of 300KB, with no names
  and no handles in the source
- the gate POSTs to `/api/unlock`; the roster arrives as JSON only if the code
  passes, and the browser renders the cards
- refusals are shown in the client's language: *"That code has expired. Ask us
  for a new one."* rather than a flat wrong-code
- quote requests POST to `/api/request` and appear in the dashboard, attributed
  to the code that opened the catalogue — FormSubmit is no longer in the loop
- adding a creator to a shortlist logs a `shortlist` event, so Analytics can
  show which creators actually draw interest

**Without `CATALOGUE_API` the build stays exactly as it was** — embedded roster,
passcode in the page, FormSubmit. Both modes are tested; the static one is what
ships until the service is running.

### One thing this does not solve

A selection link still hands over the whole roster. `/api/roster` returns
everything and the page hides what the link does not name, so a client who
opens a three-creator shortlist has received all 161 over the wire. Narrowing
that means scoping a code to a set of creators — worth doing, not done.

### Deploy order matters

Build with `CATALOGUE_API` **only once the service is actually reachable at that
URL.** A page built against a service that is not running shows the gate and
refuses every code — the catalogue would be down. Stand the service up, confirm
`/health`, then rebuild the client.

### There is no admin link on the catalogue

Deliberately. The catalogue is what clients open; a visible "Admin" button
advertises the login page to every one of them and invites a guess at the
password. Bookmark `/admin` instead — it is one path on a domain you already
have open.
