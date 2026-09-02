# HelloVoice — influencer catalogue

The built catalogue portal and the scripts that generate it.

**This repository is private and must stay private.** The built pages carry
162 creators' names, their `@handles` as profile links, follower counts,
cities and photos, plus client pricing. The passcode on the page is checked in
the browser, so it protects nothing here.

## What is in here

```
site/                      the built static site — this is what gets served
build/influencer_catalogue.py   generates /catalogue/ and /catalogue/selection/
build/catalogue_photos.py       installs harvested photos by handle
build/serve.py                  local review server (sends no-store)
docs/CATALOGUE.md               how it works, and its limits — read this first
```

## Serving it

Any static host. The document root is `site/`.

```bash
python3 build/serve.py          # local review, http://localhost:8811
```

## Rebuilding

```bash
python3 build/influencer_catalogue.py
```

Environment variables:

| variable | default | purpose |
|---|---|---|
| `CATALOGUE_PASSCODE` | `Alphaplus@123` | the access code |
| `CATALOGUE_EMAIL` | `info@hellovoice.co.uk` | where quote requests are sent |
| `CATALOGUE_ENDPOINT` | FormSubmit for that address | override the submit endpoint |
| `CATALOGUE_PREFIX` | `HV` | card code prefix |
| `CATALOGUE_ANON` | unset | `1` restores the anonymised build |

## Before you send the link to a client

1. **Test the quote form on the live domain.** FormSubmit rejects `localhost`
   outright, so it cannot be verified before deployment. Submit once and
   confirm the mail arrives at info@hellovoice.co.uk.
2. **Eight creators have no photo, and seven of those handles are dead** —
   four Instagram 404s, one deactivated, two TikTok "couldn't find this
   account". Worth correcting in the roster. See docs/CATALOGUE.md.
3. **The Interest filter is hidden** until `content/interests.json` supplies
   real categories. The workbook has no niche column.
