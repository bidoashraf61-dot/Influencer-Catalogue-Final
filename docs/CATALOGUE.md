# Influencer proposal catalogue

A gated, card-based portal for sending the Alpha Plus UGC roster to a client
without handing over the roster itself.

```bash
python3 build/influencer_catalogue.py     # regenerate the page
python3 build/catalogue_photos.py <dir>   # install harvested photos by handle
```

Two pages: `/catalogue/` (the full roster) and `/catalogue/selection/` (one
shortlist). Both gated by the same passcode.

`clone.py` sweeps every page it does not generate, so `catalogue` is listed in
its `KEEP` set. Without that entry a site rebuild silently deletes the roster
and the client's link 404s.

---

## 1. The security model — read this first

**This started as an anonymised catalogue and is no longer one.**

The original build withheld three fields, so a leaked copy was worthless: it
said only "a Jeddah Instagram account in the 50–500K band". Three changes were
then requested, and each removed one of those protections:

| change | what it exposed |
|---|---|
| show the creator's name | the alias stopped being an alias |
| show the exact follower count | name + count identifies the account in one search |
| link the platform icon to the profile | the `@handle` is now an `href` in the page source |

**Nothing is withheld any more.** A client with the link and the passcode can
lift all 162 names and handles out of the page source in seconds. This was an
informed decision, made after the trade-off was put in writing — it is recorded
here so nobody later mistakes the current build for the protected one.

What still stands:

- the **passcode** (`Hellovoice123`, `CATALOGUE_PASSCODE` to change it), which
  stops the link being forwarded around an office. It is checked in the
  browser, so it is a lock on a glass door.
- the **anti-copy layer** in `catalogue.js` — right-click, selection, drag,
  copy/cut, `Ctrl/Cmd+S/P/U/C`, devtools shortcuts, an opaque cover when the
  window loses focus, and a blanked `@media print`. It stops casual copying and
  nothing else. **Do not describe this to a client as security.**

`content/catalogue_private.json` is still written and still gitignored, but it
is no longer a secret — it now only saves you re-reading the workbook.

### Going back to the protected build

```bash
CATALOGUE_ANON=1 python3 build/influencer_catalogue.py
```

Names become codes, exact counts become follower bands, and the platform mark
stops linking out. Everything else — photos, filters, selection, submission —
is identical.

---

## 2. Data

Source: `Influncer Proposal Catalogue/Alpha_Plus_influncers.xlsx`, sheet
`المؤثرون`, 162 rows.

| tier | n | price from | price to |
|---|---|---|---|
| Nano | 28 | 435 | 870 |
| Micro | 61 | 870 | 1,740 |
| Mid-Tier | 70 | 1,450 | 2,900 |
| Macro | 3 | 2,175 | 4,350 |

Final client prices in SAR, read from the tier sheets.

**No price appears on a card.** The client sees one indicative total for the
shortlist as a whole, on the selection page, and nothing per creator — so a
forwarded screenshot of the roster carries no rate card. The per-creator band
is still in the quote email, which goes to HelloVoice.

That is a presentation change, not a secret. The four tier ranges are in
`TIER_PRICE` in `catalogue.js` because the browser computes the total, and
anyone who opens the file can read them. Only the admin service can make the
total genuinely server-side; see `docs/ADMIN.md`.

Split: Instagram 128 / TikTok 34. Riyadh 95 / Jeddah 45 / Unspecified 22.

Each card carries: photo, tier chip, a platform mark linking to the profile
(labelled "Visit profile"), the code, the creator's name, exact follower count,
city and tier. The tier chip is the site's lime on black, the same accent as
the Showreel pill; the platform mark carries the
platform's own colours — Instagram's gradient, TikTok's black with the offset
cyan and magenta. Tier follower ranges come from each
tier sheet's own header (`نطاق الفئة`): Nano under 10K, Micro 10K–50K,
Mid 50K–500K, Macro 500K–1M.

Codes are assigned by tier, then by descending followers, so `AP-MC-001` is
always the biggest Macro account. They are stable as long as the roster and
its follower ordering do not change — **if you re-run the build after
follower counts shift, codes can move.** Freeze the private key file alongside
any proposal you have already sent.

### Interests: the filter is hidden until you supply data

The `الفئة` column holds the tier, not the content category — there is no
beauty / skincare / hair field anywhere in the workbook.

**The Interest filter is therefore not rendered.** With no data every creator
falls back to one default value, and a filter built off that would tell the
client *all 162 are Skincare creators* — asserting something untrue rather
than merely omitting it. The filter works and is tested; it simply refuses to
show fabricated segmentation.

Drop a `{code: interest}` map at `content/interests.json` and it appears on the
next build, with the chip list built from whatever values are present:

```json
{ "HV-MD-014": "Hair Care", "HV-MI-003": "Fragrance" }
```

Anything unlisted falls back to `Skincare`, so a partial map is fine. The build
prints whether the filter is shown or hidden, and why.

The ticker's interest line is the `INTERESTS` list in the builder and is
presentational only — it names the categories HelloVoice works across, and is
not a claim about any individual creator.


### Follower counts are stale

The workbook is out of date — Ghalya read 570,730 live against 511,000 in the
sheet. When `content/_harvest.json` is present the builder prefers the live
number for banding, and records both in the private key as `followers` and
`sheet_followers`.

---

## 3. Photos

**154 of 162 (95%).** Instagram 123/128, TikTok 31/34.

| source | route | resolution |
|---|---|---|
| Instagram | `web_profile_info` API, logged in | 320×320 |
| Instagram | profile page `og:image`, **logged out** | 100×100 |
| TikTok | logged-in browser, `__UNIVERSAL_DATA_FOR_REHYDRATION__` | **often 1000px+** |

Sources at or below 150px get `.cat-card__photo--soft`: a circular portrait
over a blurred bed of itself, rather than a 3× upscale that reads as broken.

### The eight that cannot be sourced

Seven of the eight are dead accounts — roster errors worth reporting to the
client, not scraping failures:

| code | handle | platform | status |
|---|---|---|---|
| HV-NA-006 | anmar | Instagram | 404, gone |
| HV-MD-013 | he_1244 | Instagram | 404, gone |
| HV-MI-015 | lillyfranssis_makeup | Instagram | 404, gone |
| HV-MI-020 | mahabassem | Instagram | 404, gone |
| HV-MI-013 | mayar__eldeeb | Instagram | 200, no profile payload — deactivated |
| HV-NA-004 | aliakhhh | TikTok | "Couldn't find this account" |
| HV-MI-051 | rrvii8 | TikTok | "Couldn't find this account" |
| HV-MI-019 | saudigirlreviews | TikTok | exists but never renders |

### Scraping TikTok

Neither `fetch()` nor a logged-out request works: TikTok serves a shell and
loads the profile by XHR, and plain requests get HTTP 403. **You must navigate
a logged-in tab to each profile**, let it hydrate, then read
`__UNIVERSAL_DATA_FOR_REHYDRATION__` — falling back to the largest profile
image in the DOM when that script is absent after a reload.

**Pace it.** Rapid sequential navigation triggers bot detection: first a
"Please wait…" interstitial, then a hard *"Access denied"* block on the whole
domain. ~20s between profiles is sustainable; faster is not. Do not try to
defeat the detection — wait it out.

### The same trap, twice

On Instagram, scraping the logged-in profile page returns **the viewer's own
avatar**, not the profile's — it produced 39 identical copies of the HelloVoice
logo that passed every structural check (HTTP 200, valid JPEG, sane size,
right filename). On TikTok the DOM fallback did the same thing, grabbing the
signed-in user's sidebar avatar for two accounts whose profiles failed to
render. Both were caught only by comparing bytes.

**Always verify uniqueness before shipping:**

```bash
cd site/assets/catalogue && md5 -q *.jpg | sort | uniq -d
```

Any output means duplicates, which means wrong images. The DOM fallback now
skips anything inside a nav/sidebar and anything under 200px, but a byte
comparison is the check that actually caught it.

**Cache-bust the photos.** They are replaced in place across passes while the
URL stays the same, so a stale cached image renders the old picture and sends
you hunting a data bug that is not there. This cost real time: two cards
appeared to show the HelloVoice logo when the files on disk were already
correct. Every photo URL is now content-hashed.

Photos land in `site/assets/catalogue/<CODE>.jpg`. Any card without one falls
back to a plate carrying the code's number, so the page is complete at any
coverage level.

Note: showing faces alongside names makes the roster fully identifiable. That
was a deliberate, informed choice — see section 1.


---

## 3b. Selections

A shortlist travels entirely in the URL fragment:

```
/catalogue/selection/#n=Ramadan%20Push&c=HV-MC-001,HV-NA-004,HV-MD-013
```

The fragment never reaches the server, so this needs no backend and works on
any static host. Both directions use it: you shortlist on the catalogue, hit
**Review selection**, name it and share the link; or the client shortlists and
sends theirs back.

The selection page shows the name as its heading, a summary (count, per-tier
split, indicative total range), and the chosen creators as cards in the link's
order. Each card can be removed, which rewrites the fragment so what they see
stays what they can re-share. There is no route back to the full roster — a
curated proposal stays curated. The quote request carries the selection name,
so the email subject reads *"Ramadan Push — Alpha Plus"*.

Codes the current build does not recognise are dropped and counted in the
summary as "Not in this roster", so a stale link degrades rather than breaks.

### What this does not do

**One unlock covers both pages.** The code is remembered in a session cookie,
which every tab on the origin shares and which the browser drops when it
closes. It used to be `sessionStorage`, scoped to a single tab — so the
selection page, which opens in a new one, asked the client for the very same
code they had just typed. A forwarded link still gates a stranger: verified
with cookies and storage cleared, the page stays locked, names are not
rendered, and a wrong code is still refused.

**It is a link, not a saved record.** Nothing is stored anywhere. Lose the
link and the selection is gone; there is no list of past selections, because a
static page cannot persist one reliably.

**It does not hide the rest of the roster.** A static page has to be able to
draw *any* selection, so the selection page ships all 162 cards and reveals the
ones the fragment names. Anyone with the link and the passcode can read the
others out of the page source. Sending a selection link is a way to focus
attention, not to withhold the remainder.

---

## 4. Submission

**Quoting happens on the selection page only.** The roster's tray offers Clear
and Review selection; the request form lives where the shortlist is settled and
its total is on screen, so nobody asks for a quote without having seen one.

"Request a quote" collects name, company,
email and phone and POSTs to FormSubmit, which relays it to
**info@hellovoice.co.uk** (`CATALOGUE_EMAIL` to change). No backend of ours.

The email arrives as a table, with each pick spelled out rather than as a bare
code, so an enquiry is actionable without opening the private key:

```
HV-MC-001 — Noha Magdy  (Instagram, Macro, Jeddah)
HV-NA-001 — Lilian Hassanieh  (Instagram, Nano, Riyadh)
```

On success the form is replaced by a green confirmation carrying a **Copy
selection link** button. The link is captured before the shortlist is cleared —
reading it afterwards would hand back an emptied selection — so the client
keeps a way back to exactly what they sent.

The client receives no file, no download and no mail draft — only a
confirmation.

### Two things that will bite you

**The address must be activated once.** FormSubmit emails an "Activate Form"
link to info@hellovoice.co.uk on the first submission; until someone clicks it
nothing is delivered. An activation email was already triggered on
2 Sep 2026 — check that inbox.

**FormSubmit needs a real Origin.** It rejects requests without one, so the
page must be served over http(s). Opened as a `file://` document the form will
always fail, with the message *"Make sure you open this page through a web
server"*.

**And it answers 200 on failure.** A rejected submission returns HTTP 200 with
`{"success":"false"}`. Checking only the status code reported "Sent" to the
client while nothing had been delivered; the handler now reads the body and
treats `success:"false"` as an error. Keep that if you swap the endpoint.


---

## 5. Hero showreel

The header plays `/assets/video/hero-reel.mp4` — the same reel the influencer
campaigns page uses — muted, looping, `playsinline`, `preload="none"` behind
`hero-reel-poster.jpg`. Swap the path in the builder's hero block to change it.

The lime pill overlaps the giant heading via a negative bottom margin that
scales with the title (`clamp`), so the bite stays proportional at every width
instead of drifting apart on wide screens.

---

## 6. Theme

Follows [THEME-BRIEF.md](THEME-BRIEF.md): Bebas Neue headings, DM Sans body,
ink `#121212`, linen `#e9dcd2`, lime `#e8ff76` for the rotated pill and the
active/selected state, orange `#ff691e` full-bleed ticker, 1680px container,
5% global padding, 44px minimum tap targets below 991px, and no hover zoom on
card media.

`catalogue.css` is standalone rather than layered on `main.css` so the portal
cannot inherit site layout rules that fight the grid. It redeclares the two
`@font-face` rules against the same `/assets/ref/*.ttf` files.
