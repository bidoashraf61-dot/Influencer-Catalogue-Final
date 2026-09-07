# Influencer Catalogue Admin

A dashboard for issuing access codes, watching who opens the catalogue,
editing the roster and reading quote requests — plus the API that makes those
things real rather than decorative.

**Stdlib Python only.** No pip install, no build step, no framework — Excel
files included, which `admin/xlsx.py` reads and writes by unzipping the
workbook itself. It runs anywhere Python 3.8+ exists.

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

**The code is stored as written, and the list shows it in full with a Copy
button.** It was hashed at first, borrowed from password practice without the
reason behind it: passwords are hashed because people reuse them elsewhere, so
a stolen database becomes a key to other services. Nobody reuses a catalogue
share code — and anyone who can read the `codes` table can already read the
`creators` table beside it, which is the very thing the code unlocks. The hash
protected nothing, while "shown once, then gone" cost a real code every time
someone closed the tab.

The hash stays as the lookup `/api/unlock` uses, so nothing about checking a
code changed.

**Codes issued before this change cannot be shown.** They were only ever
hashed; the last four characters are all that was kept. Those rows still work
and still revoke — they just read `••••-HZBT`. Re-issue if you need the text.

What this does mean: the database now holds live access codes in readable
form. Back it up somewhere private, and keep treating it as the crown jewels
(§6) — which it already was.

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
its **filename**, any of three ways — so in most cases nothing needs renaming:

| file | matches |
|---|---|
| `Noha Magdy.jpg`, `noha_magdy.jpg`, `NOHA-MAGDY.jpg` | that name |
| `noha.mgdi.jpg` | that handle |
| `HV-MC-001.jpg` | that code |

Case, spaces, dashes and underscores are all equivalent — only letters and
digits are compared, which holds for Arabic names too — and a `(1)` the
browser appended to a second download is stripped before matching.

**Nobody has to learn the codes.** They exist for the client-facing cards, not
for filing photos. If you do want them, *Export the roster (.csv)* on the same
page lists every creator with their code, handle and whether a photo is on
file; it is also a valid import file, so a column can be edited and uploaded
back.

Whatever matches nothing is **listed back by name**, not silently dropped —
a batch that quietly attached 44 of 50 photos and said "done" would be worse
than one that failed outright. Files are checked by the same magic bytes and
6MB limit as a single upload, and a rejected file writes nothing: no image on
disk, no change to the row.

A name or handle that fits two creators is skipped rather than guessed,
because guessing puts a photo on the wrong card. Verified by giving a second
creator an existing name: the upload reported *"Matched two creators, so
skipped"* and neither row changed.

### Bulk import

Download the template from the roster page, fill it in, upload it. Two
formats: **.xlsx**, which can carry the photos, and **CSV**, which cannot.

- **A blank code is assigned automatically**; an existing code updates that
  creator rather than duplicating them.
- **Nothing is written unless every row is valid.** A bad tier or a
  non-numeric follower count rejects the whole file and names the rows. A
  half-imported roster is harder to recover from than a rejected upload. The
  row it names is the sheet's own line, so blank rows in the middle no longer
  shift the number.
- **Neither format needs anything installed.** An `.xlsx` is a zip of XML, and
  `admin/xlsx.py` unzips it with `zipfile` and `xml.etree` — so Excel files
  work on any host, not only one where somebody remembered to `pip install`.
  A file that is not a readable workbook is refused with a message naming the
  fix rather than failing somewhere inside a parser.
- The CSV template ships with a UTF-8 BOM so Excel does not mangle Arabic city
  names, and the parser accepts `;` delimiters for locales that export that way.

### Photos inside the sheet

A photo is never *in* a cell — a cell holds text. Excel stores pictures as
floating drawings in `xl/media/`, anchored to a position on the sheet, and the
cell underneath stays empty. That is why the template's `photo` column is a
landing place rather than a field: whatever you type there is ignored, and the
picture you insert on that row is what counts.

**The row a picture's top-left corner sits in is the creator it belongs to.**
Insert one per row and it lands correctly. Drag a picture down until its corner
falls into the row below and it attaches to that person instead — which is
fair, because that is where it visibly is.

Verified end to end: a sheet with pictures on rows 2 and 4 and nothing on row
3 imported as *"3 added, 2 photos taken from the sheet"*, the images matched
by content hash to the right two creators and row 3 left with none.

Caveats, all of them visible rather than silent:

- **.xlsx only.** CSV cannot carry an image in any form, and no encoding trick
  changes that.
- Two pictures on one row: the first wins, the second is ignored rather than
  silently overwriting it.
- A picture that is not a real image, or is over 6MB, is **named in the result
  by its row** and skipped. The rest of the import still goes through.
- **A photo already on file survives a re-import that carries no pictures** —
  losing 154 photos to a spreadsheet upload would be a bad day. A picture on
  the sheet replaces it, because putting one there is deliberate.

If your photos are a folder of files rather than something you want to paste
into Excel, *Attach photos in bulk* above is the faster route.

---

## 5. Analytics

### What is recorded

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

### What the page shows

The numbers were always there; they were laid out as tables of counts, which
tells you how much happened and not whether any of it went anywhere.

- **The range is a calendar**, two native `<input type="date">` fields and
  Apply. Native, so the browser supplies its own calendar and its own locale —
  a hand-built picker would be a lot of JavaScript to arrive at something worse
  on a phone. `to` is inclusive: pick the 6th and the 6th is counted, right to
  the end of that day. Dates are read as UTC, matching how SQLite groups the
  daily chart, so events do not land in the wrong column at the edges. A bad or
  reversed range falls back rather than erroring — verified with
  `?from=banana`, a reversed pair, and the old `?days=7`, all 200.
- Past four months the chart **rolls up to weeks**, because a daily bar across
  a year is a hairline.
- **Headline figures** carry their own context — opens says how many of the
  issued codes were used, quote requests says what share of opened codes
  actually asked.
- **Activity** is an SVG chart with a real axis and gridlines: opens and
  shortlists per day, quote-request days marked above the column. Days with
  nothing on them are drawn as gaps rather than skipped, because a chart that
  only plots active days compresses a quiet fortnight into nothing and reads
  as steady use.
- **How far each code got** is the funnel — issued, opened, shortlisted,
  requested, each with the percentage of the step before. A catalogue opened
  forty times that produced no shortlist is a different problem from one
  nobody opened, and a table of totals cannot tell the two apart.
- **What clients shortlist** breaks the shortlisting down by tier and by
  platform. Over a few campaigns this is the commercially useful chart: it is
  demand, in the client's own choices.
- **Why codes were refused** splits the rejected attempts into unknown,
  expired, revoked and exhausted. Several *expired* means codes are outliving
  their campaigns; several *unknown* is someone mistyping, or guessing.
- **By client** is one row per code: opens, creators shortlisted, whether they
  asked for a quote, and when they last looked.
- **Most shortlisted creators** now shows the photo, name, tier and platform
  rather than a bare code, so it can be read without cross-referencing.

Charts are hand-drawn SVG. No charting library, no CDN, nothing to load — the
same reason the rest of this service has no dependencies.

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
