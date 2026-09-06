# HelloVoice — creator catalogue

The repo root **is** the published site.

```
index.html            the roster, 162 creators
selection/            one named shortlist, driven by the URL fragment
assets/               only the files those two pages reference
build/                the scripts that generate them
docs/CATALOGUE.md     how it works, and its limits — read this first
```

Nothing else is here on purpose. An earlier deployment published the whole
HelloVoice site and visitors landed on the homepage rather than the catalogue.

**Live:** GitHub Pages, Source → GitHub Actions. The workflow publishes the
repo root on every push to `main`.

**Passcode:** `Hellovoice123` — checked in the browser, so it stops a link
being forwarded, nothing more. This repo is public and the pages carry every
creator's name, handle and photo; the passcode does not change that.

## Regenerating

From the main working repo, not from here:

```bash
python3 build/influencer_catalogue.py   # writes site/catalogue/
python3 build/catalogue_dist.py         # assembles dist/ — copy that here
```

`catalogue_dist.py` resolves assets by reading the built pages, so nothing
unreferenced ships and nothing referenced is missed.

## Before sending the link to a client

1. **Test the quote form on the live domain.** FormSubmit rejects `localhost`,
   so it cannot be verified any earlier. Submit once and confirm the mail
   arrives at info@hellovoice.co.uk.
2. **Eight creators have no photo, seven of those accounts are dead** — worth
   correcting in the roster. See docs/CATALOGUE.md.
3. **The Interest filter is hidden** until `content/interests.json` supplies
   real categories; the workbook has no niche column.
