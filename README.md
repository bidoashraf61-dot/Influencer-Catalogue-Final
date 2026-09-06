# HelloVoice — Influencer Catalogue

Two things live here: the **client-facing catalogue**, which is the repo root
and is published as static files, and the **admin service** in `admin/`, which
is a small Python program you run on a server.

```
index.html                 the roster
selection/                 one named shortlist, driven by the URL fragment
assets/                    only the files those two pages reference
admin/                     Influencer Catalogue Admin — the dashboard + API
build/                     the scripts that generate the catalogue
docs/CATALOGUE.md          how the catalogue works, and its limits
docs/ADMIN.md              how the dashboard works — read before deploying it
```

Nothing else is here on purpose. An earlier deployment published the whole
HelloVoice site and visitors landed on the homepage rather than the catalogue.

---

## The catalogue

Static HTML. Served from `ugc-catalogue.hellovoice.co.uk` on our own host —
**not** GitHub Pages. A Pages workflow used to sit here and failed on all
eleven of its runs because Pages was never enabled; it was removed rather than
left emailing on every push.

**Passcode:** `Hellovoice123` in the static build — checked in the browser, so
it stops a link being forwarded and nothing more. This repo is public and the
pages carry every creator's name, handle and photo; the passcode does not
change that. Point the build at the admin service and the check moves to the
server, where it means something.

### Regenerating

From the main working repo, not from here:

```bash
python3 build/influencer_catalogue.py   # writes site/catalogue/
python3 build/catalogue_dist.py         # assembles dist/ — copy that here
```

`catalogue_dist.py` resolves assets by reading the built pages, so nothing
unreferenced ships and nothing referenced is missed.

---

## The admin service

**Stdlib Python only.** No pip install, no build step, no framework. It runs
anywhere Python 3.8+ exists.

```bash
python3 admin/seed.py --email you@hellovoice.co.uk   # create the first admin
python3 admin/seed.py --import-roster                # load the creators
python3 admin/server.py --port 8900 --base-path /admin
```

Then `http://127.0.0.1:8900/admin`. In production it sits behind nginx on the
catalogue's own domain, so `/api/*` is same-origin: no CORS, and the viewer
cookie can be `SameSite=Lax` rather than `None`. **[docs/ADMIN.md](docs/ADMIN.md)
carries the systemd unit and the nginx block — read it before deploying.**

What it does:

- **Access codes** with expiry, use limits and immediate revocation, shown in
  full with a Copy button
- **Roster** — add, edit and hide creators; codes are assigned from the
  database rather than typed
- **Photos** — one at a time, a whole folder at once matched by name / handle /
  code, or embedded in an `.xlsx` and matched by row
- **Bulk import** from `.csv` or `.xlsx`, all-or-nothing, plus a roster export
  that round-trips
- **Quote requests** as an inbox, each showing the full selection
- **Analytics** over any date range: a funnel from issued to quoted, activity
  per day, what clients shortlist by tier and platform, and why codes were
  refused

### The database is not in this repo

`admin/catalogue.db` is gitignored and must be. It holds the roster, every
quote request, and live access codes in readable form. Copy it to the server
separately and back it up somewhere private — it is a single file.

### Deploy order matters

Stand the service up first and confirm you can sign in. **Only then** rebuild
the catalogue against it:

```bash
CATALOGUE_API="https://ugc-catalogue.hellovoice.co.uk" python3 build/influencer_catalogue.py
```

The other way round takes the catalogue down: a page built against a service
that is not answering shows the gate and refuses every code.

---

## Before sending the link to a client

1. **Test the quote form on the live domain.** FormSubmit rejects `localhost`,
   so it cannot be verified any earlier. Submit once and confirm the mail
   arrives at info@hellovoice.co.uk. Not needed once the admin service is
   handling requests.
2. **Eight creators have no photo, seven of those accounts are dead** — worth
   correcting in the roster. The dashboard's roster export lists who.
3. **The Interest filter is hidden** until `content/interests.json` supplies
   real categories; the workbook has no niche column.
