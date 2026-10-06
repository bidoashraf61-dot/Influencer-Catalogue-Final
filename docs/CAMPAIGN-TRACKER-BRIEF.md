# Campaign Tracker — build brief

Status: **built (M1–M7), not yet deployed.** Agreed 2026-10-05 (brainstorm with Bido).
How to run it: `docs/ADMIN.md` §5b · capture job: `docs/CAPTURE-AGENT.md` ·
deploy: `deploy/README.md` → "Campaign tracker release".
Build locally in this repo → push to `origin` → pull on the live server.

---

## 1. Objective

A campaign tracker with the **full capabilities of a dedicated campaign-tracking tool**,
living as its own page in the catalogue, in the catalogue's theme.

- **We** (admin) create, run and edit every campaign.
- **Clients** only view their own campaign reports — they never create or edit.
- No third-party subscription needed for tracking; post data is captured by Claude.

## 2. Decisions locked

| Topic | Decision |
|---|---|
| Client role | View-only live report |
| Client access | Same passcode as the catalogue; a code sees only campaigns linked to it |
| Phase 1 scope | Everything: links, campaign page, automated post capture, insights |
| Link domain | Existing subdomain: `ugc-catalogue.hellovoice.co.uk/go/<slug>` |
| Post capture | Scheduled **Claude in Chrome** job on a team Mac → POSTs to admin API |
| Insights (reach, impressions, story views) | Creator screenshot upload, read by Claude, approved in admin |
| KPIs shown to client | Clicks, post metrics (views/likes/comments/ER), reach/impressions, EMV |
| CPM | **Internal only** (admin), never on the client page |
| Campaign origin | "Start campaign" from a selection, or blank |
| Sales / ROAS / CAC / AOV | Out — clients are not on Shopify; UTMs hand this to the client's own analytics |

## 3. Capability map

| Capability | Ours | Where |
|---|---|---|
| Campaign: name, client, dates, creators | ✅ | Admin |
| Detection rules: hashtags, @mentions, keywords | ✅ matched on caption by capture job | Admin + capture |
| "Campaign" vs "All content" tabs | ✅ matched vs unmatched posts in window | Admin + client page |
| Auto-capture posts, Reels, Stories, TikTok, YouTube | ✅ via Claude in Chrome (Snapchat too) | Capture job |
| Manual "Import content" by link | ✅ | Admin |
| Refresh metrics over time | ✅ one capture run every 24 hours for every live campaign (posts, Reels, Stories, videos) | Capture job |
| Per-creator tracking links: clicks, unique, app, device, country | ✅ | `/go/` + admin |
| Est. reach / est. impressions | ✅ same rules; replaced by **real** values when insights approved | Calc module |
| ER%, Video ER%, Impressions ER% | ✅ same formulas | Calc module |
| EMV with custom multipliers (workspace + campaign) | ✅ | Admin settings |
| Creator cost, CPM | ✅ internal | Admin |
| Compliance alert (missing #ad / disclosure) | ✅ flag when caption lacks agreed disclosure tag | Capture + admin |
| CSV/Excel export, video download | ✅ | Admin; client gets PDF/CSV of their report |
| Shopify sales attribution | ❌ out of scope | — |

## 4. Users and what each sees

| | Admin (us) | Client | Creator |
|---|---|---|---|
| Create/edit campaigns, rules, links, costs | ✅ | ❌ | ❌ |
| See report: KPIs, posts, clicks, EMV | ✅ | ✅ own only | ❌ |
| See CPM, creator cost, rating, margin | ✅ | ❌ | ❌ |
| Upload insight screenshots | ✅ fallback | ❌ | ✅ via private link, own posts only |
| Approve insight numbers | ✅ | ❌ | ❌ |

## 5. System overview

```
                 ┌──────────────── live server ────────────────┐
 Creator bio ──► │ /go/<slug>  → log click → 302 to destination │
                 │                                               │
 Client ───────► │ /campaign/#<token>  (static page, theme)      │
   (passcode)    │      └─ GET /api/campaign  (client-safe JSON) │
                 │                                               │
 Creator ──────► │ /insights/#<creator-token> → upload screenshot│
                 │                                               │
 Admin ────────► │ /admin/campaigns …  (full control)            │
                 │                                               │
                 │ /api/capture/*  (token-auth, ingest)          │
                 └───────────────▲──────────────────────────────┘
                                 │ HTTPS + capture token
                     Team Mac: scheduled Claude in Chrome job
                     (dedicated company IG/TikTok/Snap login)
```

All campaign data lives in `catalogue.db` on the server. **This repo is public —
nothing campaign-related is ever committed** (no exports, no screenshots, no seed data
with real names).

## 6. Admin (control centre)

New nav item **Campaigns**.

1. **Campaign list** — name, client, status (draft / live / ended), dates, creators,
   posts captured, clicks, last capture time. Filters: client, status.
2. **New / edit campaign**
   - Name, client (linked access code), start/end dates, status.
   - Detection rules: hashtags, @mentions, keywords, required disclosure tag.
   - Default destination URL + UTM base (`utm_source` auto per app, `utm_campaign`, `utm_content=<creator code>`).
   - Total campaign cost (internal), per-creator cost (internal).
   - EMV multipliers: inherit workspace defaults or override.
   - Visibility toggles per KPI block (e.g. hide EMV for one client).
   - "Start campaign" button on a **selection** pre-fills creators, client and code.
3. **Creators tab** — add/remove creators from roster; per creator: handles per platform,
   tracking link (slug editable, destination override), cost, insight-upload link (copy),
   posts count, clicks.
4. **Content tab** — grid of captured posts: platform, type (post/reel/story/video),
   date, matched/unmatched, disclosure flag, latest metrics, snapshot history.
   Actions: import by URL, move between Campaign/All content, hide, delete, edit numbers.
5. **Insights queue** — uploaded screenshots with Claude-extracted numbers side by side;
   approve / correct / reject. Only approved numbers reach the client.
6. **Analytics tab** — the client report view **plus** internal blocks (CPM, cost per click,
   cost per creator, creator rating).
7. **Exports** — CSV/XLSX of creators, content, clicks; client PDF of the report.
8. **Settings** — workspace EMV multipliers, capture token (rotate).

## 7. Client campaign page (`/campaign/`)

Static page in the catalogue theme (same shell, fonts, colours as `index.html` and
`selection/`). Opens with the client's existing passcode; lists their campaigns if
more than one.

Sections, top to bottom:
1. **Header** — campaign name, client logo, dates, status, "last updated" and the line
   **"Data updated every 24 hours"**.
2. **KPI strip** — creators, posts, total views, est./real reach, impressions,
   engagements, avg ER, clicks, EMV.
3. **Over time** — views/engagement/clicks by day.
4. **Creators table** — photo, name, platform, posts, views, ER, reach, clicks, EMV.
   (No cost, no rating.)
5. **Content grid** — thumbnails with metrics; filter by platform/type/creator;
   tabs "Campaign" / "All content" (admin can hide the second).
6. **Clicks** — by creator, app, device, country.
7. **Download** — PDF report, CSV.

Labels mark estimates as "est." and real values as "from creator insights".

## 8. Tracking links (`/go/<slug>`)

- Slug default `<campaign-short>-<creator-code>`, editable, unique.
- On hit: record time, hashed IP+UA, app (from user-agent: Instagram, TikTok, Snapchat,
  WhatsApp, YouTube, browser), device, OS, country (offline DB-IP Lite), referrer;
  then `302` to destination with UTMs appended.
- Unique click = same hashed device per link per day.
- Bot/preview hits (link previews, crawlers) logged but excluded from counts.
- Ended campaigns keep redirecting (bios outlive campaigns); admin can disable a link.

## 9. Capture job (Claude in Chrome, team Mac)

- A **scheduled task** on a team Mac, Chrome logged into **dedicated company accounts**
  (never personal or client accounts).
- Each run:
  1. `GET /api/capture/jobs` → list of live campaigns, creators, handles, rules, and
     posts due for a snapshot.
  2. Visit each creator profile; find new content in the campaign window; read
     caption, date, type, URL, thumbnail, likes, comments, views.
  3. **Stories**: daily run while live — capture frame + views not public, so story
     reach comes from insights; record existence, time, link sticker.
  4. `POST /api/capture/content` with results (idempotent by post URL).
  5. Pull pending insight screenshots, read the numbers, `POST` them as **pending
     approval**.
- Schedule: **one run every 24 hours** while a campaign is live; every run snapshots every post
  in the window, so each post gets a daily metrics history. A final run on the end date + 7 days.
- Auth: long random capture token, stored hashed on the server, rotatable in admin.
- Guardrails: slow pacing between profiles; stop and alert on login wall/captcha
  (never solve captchas); log every run in admin ("last capture", errors).

## 10. Insights upload (creators)

- Private link per creator per campaign (`/insights/#<token>`), no login, expires
  with the campaign + 30 days.
- Creator picks the post, uploads screenshot(s) of Instagram/TikTok/Snap insights.
- Stored under the server's private data dir (not the public `assets/` mount).
- Claude extracts reach, impressions, story views, saves, shares, profile visits →
  admin approves → replaces estimates on the report.

## 11. Metric definitions

| Metric | Formula |
|---|---|
| Engagement | likes + comments |
| Est. reach — post | engagement × 10, capped at followers (factor in Settings) |
| Est. reach — story | followers × 5% (factor in Settings) |
| Video (reel/video/short) | reach = views; counted as views, not impressions |
| Est. impressions — post | est. reach × 1.5 |
| Est. impressions — story | = est. reach |
| Real reach / impressions | approved insight values (override estimates) |
| ER% | engagement ÷ followers × 100 (stories and hidden-like posts excluded) |
| Video ER% | engagement ÷ views × 100 |
| Impressions ER% | engagement ÷ impressions × 100 (non-video) |
| Clicks / unique clicks | from `/go/` log |
| CTR | clicks ÷ (views or impressions) × 100 |
| EMV | Σ (action count × multiplier) per platform & action, in SAR |
| CPM *(internal)* | cost ÷ impressions × 1,000 |
| Cost per click *(internal)* | cost ÷ clicks |

EMV multipliers start blank — Bido sets the SAR values before launch.

## 12. Data model (new tables)

`campaigns` (id, token, name, code_id, selection_id, starts, ends, status, rules JSON,
destination, utm JSON, cost, emv JSON, visibility JSON, created/updated) ·
`campaign_creators` (campaign_id, creator code, handles JSON, cost, link slug,
destination override, insights token) ·
`content` (id, campaign_id, creator, platform, type, url UNIQUE, posted_at, caption,
thumb, matched, disclosure_ok, hidden) ·
`snapshots` (content_id, at, likes, comments, views, source = capture|manual|insights) ·
`insights` (content_id, file, extracted JSON, status pending|approved|rejected, by, at) ·
`links` (slug UNIQUE, campaign_id, creator, destination, active) ·
`clicks` (link slug, at, device_hash, app, device, os, country, referrer, bot) ·
`capture_runs` (at, ok, posts_found, errors).

## 13. Security and privacy

- Client API returns a **client-safe projection** only: no cost, CPM, rating, notes.
- Passcode-scoped: a code sees only campaigns linked to it.
- IPs stored only as salted hashes.
- Screenshots and exports never in `assets/` or the repo.
- Capture + insights endpoints token-authenticated and rate-limited.

## 14. Build, push, deploy

1. Build and test locally: `python3 admin/server.py --port 8900 --base-path /admin`.
2. Commit to this repo (code only, no data) → `git push origin main`.
3. On the server: `git pull`, restart `hv-catalogue` service; DB migrates on start.
4. nginx: add `location /go/` and `location /insights` → admin service; `/campaign/`
   is static.
5. Install the scheduled Claude in Chrome task on the team Mac with the capture token.

## 15. Milestones

| # | Deliverable | Done when |
|---|---|---|
| M1 | Data model + admin Campaigns (create, from selection, creators, rules) | campaign created from a selection locally |
| M2 | Tracking links `/go/` + click analytics | test clicks show app/device/country |
| M3 | Manual content import + metrics + calc module | KPIs match hand calculation |
| M4 | Client `/campaign/` page in theme, passcode-scoped | client code sees only its campaign, no internal fields |
| M5 | Capture API + Claude in Chrome job | one real past campaign captured end to end |
| M6 | Insights upload + Claude extraction + approval | approved reach replaces estimate on client page |
| M7 | Exports (CSV/XLSX/PDF) + deploy to live | live pilot campaign running |

Pilot: one live campaign (e.g. next SVR/SEMAK wave) before rolling out to all.

## 16. Assumptions (correct if wrong)

- Platforms: Instagram, TikTok, Snapchat, YouTube.
- A dedicated company account per platform exists or will be created for capture.
- One team Mac stays on during live campaigns.
- Creators accept the screenshot-upload requirement in their brief/contract.
- Campaign currency SAR.
