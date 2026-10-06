# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Client brand and marketing managers** (pharma, healthcare, beauty, FMCG — mostly KSA, also UAE/Egypt). Not analytics experts. They open the catalogue to shortlist creators and the campaign report to see whether a campaign is working, on a laptop or a phone.
- **Their senior managers**, who receive the report forwarded or as a PDF and only glance at it: they need the verdict (good / moderate / bad) without reading numbers.
- **HelloVoice key account managers**, who show the catalogue, creator analyses and campaign reports in pitches as proof.
- **HelloVoice admins** (Bido and the team), who run everything from the admin dashboard — not all of them technical.

## Product Purpose

HelloVoice's influencer catalogue: a passcode-protected roster of vetted creators that clients shortlist from, plus — new in Oct 2026 — campaign tracking (a full campaign tracker run by HelloVoice) and per-creator full analysis pages. Success means a client can pick creators with confidence, see at a glance how their campaign is performing, and trust HelloVoice enough to book the next one.

## Positioning

The creators, the campaign data and the analysis are HelloVoice's own: run end to end by the agency that produced the content, covering Instagram, TikTok, Snapchat and YouTube, with real numbers from creators' own insights replacing estimates once approved.

## Operating Context

- Catalogue at the site root, selection pages, campaign report at `/campaign/`, all behind the client's access code; one code sees only its own selections and campaigns.
- Admin dashboard (`/admin`) controls everything: roster, codes, selections, campaigns, insights approval, settings.
- Data is captured once every 24 hours by a scheduled Claude-in-Chrome job; the report says so.
- Reports are forwarded and printed to PDF.

## Capabilities and Constraints

- Static HTML/CSS/JS pages + stdlib-Python admin service; no framework, no build step for the campaign pages. Repo is public: no client or creator data in it.
- Clients view only; they never create or edit campaigns.
- Internal figures (costs, CPM, margins, creator ratings, notes) never reach a client page. EMV is hidden from clients.
- Benchmarks: built-in defaults by platform and follower tier, editable in Settings, plus per-campaign targets.
- Creator full analysis: uploaded by admins (template / bulk); creators without one show a locked page with "Request full analysis", which lands in the admin inbox.
- Clients with any valid code may open creator analysis pages.

## Brand Commitments

HelloVoice catalogue theme (`assets/css/catalogue.css`): Bebas Neue display, DM Sans body, ink / lime / linen with orange and red accents; HelloVoice logos in `assets/brand/`. English UI; Arabic where creators are addressed.

## Evidence on Hand

- Client logos: `assets/clients/` (used on the catalogue carousel).
- Platform and campaign data come from the live database only. No benchmark figures are claimed as HelloVoice results; built-in benchmarks are labelled as industry guides.

## Product Principles

1. Verdict before numbers: every metric carries a plain good / moderate / bad signal against a stated benchmark.
2. Visual first: charts, rankings and imagery lead; tables support.
3. Honest about estimates: anything estimated is labelled until real insights replace it.
4. Simple to run: an admin who is not technical can set up and steer a campaign without help.
5. Client data stays private: one code, one client's view.
