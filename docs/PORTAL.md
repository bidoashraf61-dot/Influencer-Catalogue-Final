# Client portal: accounts, AI shortlist, chat, copilot

Built on branch `portal-v2`. Everything here is additive: access codes keep
working, and the email sign-in only appears on the catalogue once mail is set up.

## What a client gets

1. **Sign in with a work email.** One-time 6-digit code by email, then a one-time
   profile step (name, company). No passwords. Personal providers (Gmail,
   Outlook, iCloud, Yahoo, disposable inboxes) are refused. The catalogue is
   the landing page once signed in.
2. **Find creators.** Eleven short multiple-choice questions (or one sentence
   that the AI turns into answers). The answers become a **brief** that is stored,
   then every creator is scored against it and a budget-aware shortlist is saved
   as a real **selection** that opens on the existing selection page.
3. **Ask.** A chat assistant that searches the roster, builds shortlists and
   answers questions about prices and how HelloVoice works.
4. **Account.** Profile, AI credits and history, past briefs, link to campaign
   tracking. Each client sees only their own selections, campaigns and briefs.

## What the admin gets

- **Clients → Client portal** (`/portal`): accounts (approve, hold, suspend),
  per-client page (profile, credits, ledger, selections, briefs, activity),
  all briefs, AI usage (tokens vs the monthly ceiling, per-action counts, latest
  calls) and **Settings & keys**.
- **Insights → AI copilot** (`/ai`): ask about the data; ask for changes:
  edit or add creators, create or edit campaigns (status, dates, creators),
  change tier prices, create selections, adjust credits, approve or suspend
  clients, change sign-up domains. A
  change is queued as a plain sentence and only runs when you press **Confirm**.
  It is recorded in **History & undo** like any other edit.
- The selection page shows **Client brief** when the shortlist came from the AI.
- Access codes can carry their own **AI credits** at creation.

## Also included (round 3)

- **Sign-up is automatic** for any company domain (no approval step; Approval mode is still available).
- **Hand-built selections get a brief too.** When a client saves a selection, a free 6-question card
  offers to score it; the answers become the selection's objective and audience.
- **Fit badges on the catalogue** for the client's latest brief, with a chip to hide them.
- **Colleagues share** selections and campaigns (same company domain; switch in Settings).
- **Credits:** clients request more from their account panel; you grant from Client accounts or their
  page (+50 / +200 / +500 packs); optional monthly top-up per client or for everyone.
- **KAMs and emails:** assign a KAM per client; new clients, briefs, quote requests and credit requests
  are emailed to the KAM and the team list (Settings & keys).
- **Chats tab:** read every client conversation.
- **Funnel:** sign-ups → sign-ins → briefs → selections → quote requests, last 30 days.
- **Printable quotation** from any selection (Print → Save as PDF), linked from the selection page.
- **Data rights:** clients download their data and can delete their account; admins can too.
- **Language:** the portal is English only for now; the chat assistant understands and replies in any language (Arabic, English, ...). An Arabic UI table is kept in portal.js for later.

## Matching quality (tested on the production roster, 7 Oct 2026)

Fixed after testing against the live 2,152-creator roster:
the product space is enforced (a creator not tagged for it is marked down ×0.6 and says so),
healthcare briefs put HCP-tier creators first, "car" no longer matches "skincare" (this also fixes the
existing selection scores), budgets are checked on the middle of each fee and spread across all slots,
and equal scores break by reach for awareness, by smaller accounts otherwise. When the roster has no
creators for a space (e.g. automotive today) the shortlist says "Possible fit" instead of pretending.

## Cost tracking (USD)

**Client portal → Usage & cost** shows what the portal costs in dollars:
this month, today, last 30 days, all time, the projected month end, the monthly
budget, cost per credit, a 30-day chart, cost by action and by model, and
**consumption per account** (each client, each access code, the admin preview
and the platform itself). **Download CSV** exports month × account × action for
finance. Each client's page and the accounts table also show their AI cost.

Every Gemini call stores its own dollar cost when it happens (input and output
tokens, thinking included, times the model's price), and every sign-in email
stores its cost too. Changing a price later never rewrites past spend.
Default prices are Google's list prices on 7 Oct 2026; `gemini-3.8-flash` is a
launch price until 31 Dec 2026, so check it in January (Settings & keys).
A **monthly budget in USD** (default $50) stops AI for everyone when reached.

## Model

`gemini-3.8-flash` for everything by default: 1,048,576-token input window,
65,536 output, function calling and JSON output verified live, $0.75 / $3.75 per
million tokens. If it is retired or overloaded, the call moves to
`gemini-3.5-flash`, then `gemini-3.1-flash-lite`, then `gemini-flash-latest`.
The copilot can use its own model (e.g. `gemini-3.1-pro-preview`) without
changing what clients use.

Production data (7 Oct 2026): the active roster is about 200k characters
(~60–80k tokens) and fits the window easily; the 2,118 creator analyses are
about 4M characters (~1–1.3M tokens) and do not. The assistants therefore
fetch only what each question needs (typically 5–20k tokens, under 2 cents).

## Free questions in the chat

When a client asks the chat for creators or a campaign, it first reads what the
message already says (keyword matching, free), then asks only the missing brief
questions as tap-to-answer options — also free. Then the client chooses
**Build my shortlist** (5 credits) or **Ask the assistant** (1 credit, with the
whole brief attached), so one paid call has everything it needs.

## How it works

| Piece | File | Notes |
|---|---|---|
| Abuse controls | `guard.py` | Rate limiter, CSRF origin check, company-email rules |
| Accounts, OTP, credits, briefs, chat store | `portal.py` | Tables created by `portal.init()` (additive) |
| Gemini over HTTPS | `gemini.py` | Key in `.gemini-key`, audit table, monthly token ceiling |
| Email over HTTPS | `mailer.py` | Resend; key in `.mail-key` |
| Brief → ranked shortlist | `matcher.py` | Deterministic scoring with `fit.py`; free keyword pre-fill (`guess`); Gemini only parses text and writes reasons |
| Assistants | `assistant.py` | Tool-using; client tools read-only; admin writes are queued |
| Routes | `portal_api.py` | Mixin on `Handler` |
| Admin pages | `portal_views.py` | |
| Client UI | `assets/js/portal.js`, `assets/css/portal.css` | Loaded by every catalogue page |

**Identity.** A signed-up client gets a personal, never-typed access-code row.
Signing in mints the same signed `hv_view` ticket the passcode flow uses, so
selections, campaigns, events, device limits and revocation all work unchanged.
Suspending a client revokes that row: they are out on their next request.

**Credits.** One ledger per code (`credit_ledger`), debited atomically, never
negative. Default prices: shortlist with reasons 5, shortlist without AI text 2,
read a free-text brief 1, chat message 1. A failed AI call is refunded. The admin
is never charged. Welcome credits and the guest-passcode allowance are settings.

**AI is optional.** With no Gemini key, sign-in, the brief form and the
deterministic shortlist and scores still work. Only the free-text reader, the
written reasons, the chat and the copilot need the key.

**Scores.** Measured scores (creators with an analysis) are used as-is. Creators
with no analysis get a roster-only estimate, discounted ×0.85 and labelled
"Estimated". Without a measured audience split, a creator placed in another
country is multiplied by 0.6, so a large Dubai account does not win a KSA brief.

## Security model

- OTP: 6 digits, hashed with a server salt, 10-minute life, 5 attempts, 30 s
  resend cooldown; asking for a new code does not cancel the last two, so nobody
  can lock a client out by requesting codes. Limits per network, per email, per
  domain and a global hourly ceiling count only emails actually sent.
- `name+tag@company.com` is the same mailbox as `name@company.com` (no free
  accounts per tag); 3 new accounts per network per day by default; welcome
  credits only once an account is active.
- Credits are reserved before any model call, so parallel requests cannot spend
  more than the balance. Admin lockout is keyed on network + account.
- Sign-in, access-code and admin-login throttling; CSRF origin check on every
  POST; `Secure` cookie flag over https.
- Client chat tools return only the creator fields the catalogue already shows.
  Cost, rating and internal notes are never sent to a model for a client.
- Copilot SQL is one read-only `SELECT` through an authorizer that allows a fixed
  table list. `codes`, `admins`, `sessions`, `otp`, `settings` and `history` are
  refused, as are functions that can build huge values. Copilot writes never run
  directly (queued, confirm, history), and no write can be queued in a turn that
  read client-written text (names, companies, brief notes, quote requests).
- All model output that selects data is validated against the allowed options.
  Free text from clients and tool results are treated as data, not instructions.
- Keys are written to mode-600 files on the server, never shown after saving,
  and are gitignored (the repository is public).

## Setting it up (once)

1. **Email (recommended)**: a Microsoft 365 **shared mailbox through Microsoft Graph** — Entra app
   registration with Mail.Send (application, admin consent) + client secret, limited to the shared
   mailbox; paste tenant ID, client ID, secret and the mailbox in Settings & keys. No password, no DNS.
   Other options: a **company mailbox** on Microsoft 365 (what hellovoice.co.uk already
   uses, no DNS change): turn on *Authenticated SMTP* for the mailbox in Exchange admin, then
   Admin → Client portal → Settings & keys → *Email: company mailbox* (address + password or app
   password, optional test address). Alternative: Resend (needs DNS records at GoDaddy).
2. **Gemini**: create a key in Google AI Studio (restrict it to the Generative
   Language API). Paste it under *Gemini API key*. Never paste it in chat or
   commit it. Set the monthly token ceiling.
3. Choose **Who can sign up**. The default is **Approval**: a new company signs
   in, lands on "waiting for approval", and you activate it under Client accounts
   (the roster is confidential, so a person lets each new company in). Open,
   Invite only and Closed are the other modes. Set welcome credits, the
   accounts-per-network cap and the allow/block domain lists.

## Release

```bash
# 1. Back up the database
ssh AWS 'cp /home/ubuntu/influencer-catalogue-admin/admin/catalogue.db \
  /home/ubuntu/influencer-catalogue-admin/admin/catalogue.db.pre-portal-v2.bak'
# 2. Admin code: pull, copy the Python files, restart (tables are added on start)
ssh AWS 'git -C /home/ubuntu/influencer-catalogue-src pull && \
  cp /home/ubuntu/influencer-catalogue-src/admin/*.py /home/ubuntu/influencer-catalogue-admin/admin/ && \
  sudo docker restart influencer-catalogue-admin'
# 3. Site: the normal publish (it now stamps portal.js / portal.css)
ssh AWS '/home/ubuntu/influencer-catalogue/update.sh'
```

Check: `/admin/api/me` returns JSON; `/admin/portal` loads for an admin; the
catalogue shows the **access code** gate until the Resend key is saved, then the
**email** gate. Rollback: restore the previous `*.py` files and restart; the new
tables are unused by the old code.

## Tests

```bash
python3 admin/tests/test_guard.py     # limiter, CSRF, email rules
python3 admin/tests/e2e_portal.py     # full flows on a throwaway server and database
```

The e2e suite uses a stubbed Gemini and captured mail, and never touches
`catalogue.db` or the network.

## Portal v3: HELVY Connect (branch `portal-v3`)

| Piece | File | Notes |
|---|---|---|
| Bell (in-portal notifications) | `inbox.py` | Table `notifications`, per account. Groups: analysis, selections, campaigns, account, ideas (off by default). Toggles only filter the bell; history keeps everything. Never emailed. |
| Analysis gating | `gating.py` | Table `analysis_grants`. Free headline only (followers, platforms, average views, engagement, data date). The locked page is the real analysis page (same sections, cards and tabs) drawn from `gating.sample(code, platform)`, a whole analysis made from the code alone, blurred under Sample data + Locked. Requests only for creators in the client's (team's) selections. Admin **Fulfil** on Creator analysis, or an upload, unlocks for the client's team and rings the bell. Past handled requests became grants on first start. Fit-score evidence (measured audience part, its strengths and watch-outs, audience checks) and assistant tools (incl. average likes and comments) hide locked figures; discovery filters only on engagement and views for a client; content ideas drafted from the analysis are not served to a client it is locked for. |
| Selection status | `selstatus.py` | Table `selection_status`. Owner approves / rejects (optional reason); HelloVoice sets anything incl. Unavailable (admin selection page → **Client status** tab, or the client page). HelloVoice changes ring the bell; client changes email the KAM once per 5-minute burst (`notify` event `status`). **Find a replacement**: 2 credits (`costs.replace`), three similar creators kept on the row, reopening is free. |
| Rewards and invites | `rewards.py` | Profile rewards (30 in all, once, non-blank) as ledger lines `Profile reward: …` with ref `reward:<step>`; invites table; +20 to the inviter on the colleague's first sign-in (same domain, max 5). |
| Profile page | `account/index.html`, `assets/js/account.js`, `assets/css/account.css` | Overview, Selections, Analyses, Campaigns, Briefs, Notifications, Credits, Account. New profile fields: brands, industry, markets, language (pre-fill briefs). Helvy's picture is ONE file: `assets/brand/helvy.webp`. |
| Bell UI, icons | `assets/js/portal.js`, `assets/css/portal.css` | Bell between Campaign tracking and the account circle, account holders only. |

New client routes: `GET /api/notifications`, `POST /api/notifications/read`, `POST /api/selection/status`, `/api/selection/reason`,
`/api/selection/replace`. Admin: `POST /analysis/fulfil`, `POST /selections/status`. All tables are created by `portal.init()`.

Tests: `python3 admin/tests/e2e_portal_v3.py` and `e2e_portal_fixes3_gating.py` (locked figures never appear in `/api/creator`, selection scores, look-alikes, more, replacements, the AI shortlist, ideas, Helvy's tools or discovery; a granted client gets them all).

## Phases C + D: HELVY Connect (branch `portal-cd`)

| Piece | File | Notes |
|---|---|---|
| Sign-in scene | `assets/js/portal.js` (`enhanceGate`), `assets/css/connect.css` | Client door (work email, six-box code, first-time name / company / job title) and HelloVoice team door (admin access person by person). No access-code link on the client door; a selection or campaign link that still needs its code shows "Opened a shared link?", and `?access=code` shows it on the catalogue. |
| Sign-in code email | `admin/mailer.py` (`OTP_HTML`) | 600px table, inline styles, PNGs on the catalogue host (`assets/brand/email/`), VML button, dark mode. |
| Access codes → accounts | `admin/codelinks.py`, Client portal → **Access codes → accounts** | Invite a shared code's client to an email account: the account sees and owns the code's selections and campaigns (`portal.team_codes` / `portal.owns`). Codes are never revoked or moved here. |
| AI free during a campaign | `portal.charge` / `portal.active_campaign` | Every AI action is free from a (team) campaign's start date to its end date + 30 days. `/api/me` → `ai_free`. |
| Tour (v2) | `assets/js/connect.js` (opener + loader), `assets/js/tour.js` + `assets/css/tour.css` (fetched on start), `assets/demo/`, `admin/rewards.py` | Offered once (`users.tour`), replay from Help / profile; +5 once (`reward:tour`). `POST /api/tour`. See *Onboarding tour v2* below. |
| ROI Calculator | `admin/roi.py`, `admin/connect_api.py`, `connect.js` | Deterministic, free. `plans.LIBRARY` (+ house results, + creators' own averages), grades good / moderate / low. Table `roi_estimates`; estimate vs actual per campaign. Routes `/api/roi/*`. |
| AI on selections | `admin/aimore.py` | `/api/selection/more` (3 credits), `/api/selection/alike` (2, kept so reopening is free). Tables `selection_more`, `selection_alike`. |
| Helvy knowledge | `admin/helvy_kb.py`, `admin/occasions.py`, `assistant.py`, `knowledge.py`, `faq.py` | Tools `campaign_results` (own, named via Settings, or aggregates over 3+ campaigns), `occasions`, `my_decisions`, `roi_estimate`; KSA rules; **no prices ever** (price tool removed, prices stripped from creator views, FAQ routes to a quote). |
| Privacy / Terms | `privacy/`, `terms/` | **Drafts pending legal review.** |

Tests: `python3 admin/tests/e2e_portal_cd.py`, `python3 admin/tests/test_roi.py`.

## Fix batch 2026-10-09 (branch `portal-fixes-2`)

| Piece | Where | Notes |
|---|---|---|
| Helvy's files | `assets/js/hv-loader.js` (`window.HVHelvy`) | The ONE place the clips are named. Transparent, waist-up: `helvy-<name>.webm` (VP9 alpha, Chrome/Edge/Firefox) and `.mov` (HEVC alpha, Safari and every iOS browser), `helvy-still.webp`; `assets/brand/helvy.webp` is the transparent head still for small avatars. Names: idle, hello, bye, loader, thinking, celebrate, point, cards, stamp. Bump `VER` (and the `?v=` on the still) when the files are replaced: `/assets/` is cached 30 days as immutable. |
| Autoplay | `HVHelvy.video()` | muted / defaultMuted / playsinline / autoplay / loop set before the source, retried on canplay and visibility, paused off screen, the still if autoplay is refused (no play button). Ambient clips wait for the page to load; `eager` ones (loader, coach) do not. |
| Cooking | `portal.js` `HV.cooking()` | thinking -> cards -> stamp with rotating steps, for Add more like these, Creators like this and Find a replacement. |
| Loader rule | `hv-loader.js` | Shell first; the Helvy loader only if the page is not ready after 0.6 s, gone by 1.5 s; images never waited for. The catalogue calls `hvLoader.done()` when its first cards are drawn. |
| Roster | `server.py` `roster_body()`, `catalogue.js` | Serialised + gzipped once per roster version with an ETag (304 on If-None-Match); the page keeps it in sessionStorage per tab (`hv-roster`, dropped on sign-out / 401 / before `exp`), shows the shell and skeletons at once, renders 48 cards then the rest in idle slices. Card photos are lazy `<img>`. |
| No objective, no score | `server.py` `selection_has_objective()` | `/api/selection` sends `scores: {}` and `needs_objective: true` until the selection has an objective (client brief, AI brief, admin, or its campaign). The page shows "Add your campaign objective to score these creators" (`HV.scoreBrief`). |
| Reject reason | `catalogue.js` | A "?" beside Rejected: pop-up with the reasons, Other + note, Skip / Save; the saved reason on hover / focus. |
| Promise | `gating.WORK_DAYS = 1` | Full analysis within 1 working day (Friday and Saturday skipped). |

Tests: `python3 admin/tests/e2e_portal_fixes2.py`.


## Onboarding tour v2 (2026-10-09)

"Take the 3-minute tour?" — 7 stops in 4 chapters, the customer's own path: **Brief Helvy**
(the chat brief + "what can 50,000 SAR reach?", the AI shortlist desk) · **Build your
shortlist** (browse and filter; the selection: chips, score badge breakdown, approve /
reject, reason, replacement) · **Check & book** (a complete sample full analysis to scroll,
the locked request, request a quote, the bell) · **Track results** (the live demo campaign,
where everything lives, +5 credits).

How it works: the tour opens a frame over the page and plays the **real** pages in it
(catalogue, selection, creator, campaign, Helvy's chat). `hv-loader.js` — the first script on
every page — sees the frame belongs to a running tour (`top.hvTourDemo.active`) and calls
`hvTourDemo.install(window)` before any page script runs. From then on, in the frame:

- every `/api/` call is answered by tour.js from the demo world (Northwind Pharma · Ramadan
  Skincare, eight AI-generated demo creators `DEMO-01..08`, photos in `assets/demo/`):
  nothing reaches the server, so nothing is saved, no AI call is made and no credit is used;
- `localStorage`, `sessionStorage` and `document.cookie` are in-memory, so the client's own
  roster cache, chat history and settings are untouched; outside links and new windows are
  blocked; the "Paused" privacy cover and the showreel are off.

`portal.js` exposes two hooks only inside a demo frame (`window.hvDemo`): `HV.voiceDemo` (types
the scripted brief into the real chat) and `HV.aiDemo` (runs the AI shortlist card's desk).
The tour's only real call is `POST /api/tour`.

Versioning: connect.js names `tour.js?v=…` / `tour.css?v=…`; `update.sh` rewrites both to the
files' hash inside connect.js before it hashes connect.js itself. Tests:
`admin/tests/e2e_tour_v2.py` (server + contract); the on-screen journey is checked in a
browser at 1440 and 390 wide.

## Phase E (branch `phase-e`, 2026-10-10)

| Piece | Where | Notes |
|---|---|---|
| Brief from a link or a file | `admin/briefsrc.py`, `admin/phase_e_api.py` (`POST /api/brief/source`), `portal.js` (`HV.briefSource`) | "Paste a product link" / "Upload a brief (PDF or Word)" in the brief window (step 1, also the selection's objective questions), the AI shortlist card ("Or start from a product link / brief file") and the chat's Find creators flow. Gemini fills product, space, audience, markets, objective and timing with a confidence each (Found / Check / A guess / Not found); the client edits and confirms, nothing is saved by this route. Claims are only kept when they are written in the source; regulated products (medicine, cosmetic, supplement, device) get the claims flag, KSA briefs the Mawthooq flag. Cost `source` = 5, free during an active campaign; nothing is charged when the source cannot be read; refunded on an AI failure. Without a Gemini key the free keyword reader fills what the text says plainly. |
| Fetch safety | `briefsrc.check_url / resolve / fetch` | http/https only, ports 80/443, no user:password, our own hosts refused (`*.hellovoice.co.uk`, the box's name and IP, `*.local/.internal`, extra names in setting `brief_fetch_block`, extra IPs in `brief_fetch_block_ips`); every DNS answer must be public (no loopback, private, link-local incl. 169.254.169.254, CGNAT, multicast, reserved, mapped); the socket goes to the checked address (no rebinding); redirects followed by hand (3) and re-checked; 8 s per step, 15 s total, 2 MB read cap. |
| File reading | `briefsrc.extract` | PDF through PyMuPDF (already vendored in `admin/_vendor` on the server), else a small stdlib reader for ordinary text PDFs; Word `.docx` through `zipfile` (zip-bomb checks); `.txt`; old `.doc` asks for .docx/PDF; scanned PDFs say so. 4 MB upload cap; bodies over the cap are refused before parsing; the bytes are dropped after extraction. **No new dependency.** |
| Timing advisor | `occasions.advise`, `GET /api/timing`, `helvy_kb.upcoming` (`weeks_away`, `advice`), assistant rule 8 | "Saudi Derm Congress is in 14 weeks: cast now." in the brief-from-source result, the brief review, the shortlist result (`/api/brief/run` → `timing`) and the chat review; Helvy uses the same line in chat. Cast now = 6–14 weeks out; tighter = brief this week; further = brief by a date; under 3 weeks is left out. No prices. |
| Content ideas | `admin/ideas.py`, `GET/POST /api/ideas`, `connect.js` (`HV.ideas`), `catalogue.js` (card button) | 2–3 hooks + concepts, English and Saudi Arabic, fitted to the creator's card fields and, only when the full analysis is unlocked for this client, their best-post captions, brands and audience; plus the selection's brief. Lines mentioning money are dropped; no claims beyond the brief. Kept per selection (or per client on the creator page), so reopening is free; "New ideas" costs again. Cost `ideas` = 2, free during an active campaign. Helvy's "cooking" sequence while it writes. Table `content_ideas`. |
| Weekly campaign update | `admin/weekly.py` (`weekly`, `verdict`) | Bell only (kind `camp_weekly`, group Campaigns): title "<campaign>: on track", body three lines (main goal vs target and what is due, engagement vs benchmark, posts live + leader); opens the report. Week n counted from the start date (first after 7 days); none without posts. Idempotent: table `campaign_weekly (campaign_id, week)` + bell ref `week:<id>:<n>`. No email, no PDF. |
| What to do next time | `weekly.next_time / recommend / panel`, `GET /api/campaign/next?t=`, `connect.js` (`campaignNextTime`) | When a campaign is marked Ended (instant, via the `campaign_status` hook) or its end date has passed (next tick): Book again / Replace / One more test from rank on results, engagement vs the benchmark for the creator's size and posts delivered vs booked, plus up to three look-alikes of the best performer. Refreshed for 21 days after the end as late numbers land, then frozen. One bell (`camp_next`). Optional Gemini rewording of the summary with setting `next_time_ai` (off by default). Table `campaign_next`. |
| Job schedule | `weekly.start()` in `server.main` | Runs 30 s after the admin service starts, then every hour (same pattern as the Apify scheduler); each tick is idempotent, so restarts never send twice. Manual run: `sudo docker exec influencer-catalogue-admin python3 /app/admin/weekly.py`. Last run time in setting `weekly_last_tick`. |
| Voice | `portal.js` (chat compose) | Browser speech-to-text (Web Speech API) with an EN / ع (Arabic, Saudi) switch kept per browser; what is heard shows live above the box and is sent as a normal message when the client stops; Helvy replies in text. HelloVoice records and stores no audio (Chrome / Edge / Safari do the recognition themselves). Unsupported browsers: no mic, a tooltip on the box. |

Also: `connect.js` now runs once even when `portal.js` has injected it before the page's own tag (the look-alike sheet used to open twice).

Tests: `python3 admin/tests/test_briefsrc.py` (URL safety incl. SSRF, extraction, claims, timing), `python3 admin/tests/test_weekly.py` (weekly idempotency, next-time logic), `python3 admin/tests/e2e_portal_phase_e.py` (routes, credits, refunds, privacy, stubbed Gemini).

## Fix batch 3 (branch `portal-fixes-3`, 2026-10-10)

| Piece | Where | Notes |
|---|---|---|
| Helvy autoplay | `hv-loader.js` (`HVHelvy`) | A refused autoplay (Safari in macOS/iOS Low Power Mode refuses every one) no longer swaps the clip for the still for good: the still stands in while the clip waits (hidden, no play button), and play is retried on canplay, on returning to the tab and on the first tap/click/key anywhere. Only a clip the browser cannot decode stays a still. |
| Chat launcher | `connect.css` | Helvy on a lime disc (#d8ff45); ink behind the close cross when open. Every other Helvy stays a transparent cut-out. |
| AI shortlist card | `portal.css`, `portal.js` | Closed card is a two-row ink panel: Helvy on a lime circle, title, Start; then "Or start from" + Product link / Brief file on their own row. Phone: Start full width, the two sources side by side. |
| No catalogue fit scores | `portal.js` | The brief "FIT x%" pills, their MutationObserver, the `/api/brief/scores` call and the "Fit scores shown" chip are gone from the catalogue. Scores exist only in a selection with an objective, on the round `.cat-score` stamp (number + %, BASIC/MATCH label). |
| Replacement panel | `connect.js` (`HV.replaceSheet`, shared `suggestSheet`), `catalogue.js`, `server.py` | Find a replacement opens the same side panel as Creators like this. `/api/selection/replace` items now carry `why` ("In X's place: …", card fields only). Kept three free on reopen, Show 3 more costs again; added creators join Under review, the rejected creator stays rejected. |
| Objective studio | `portal.js` (`objectiveStudio`, `HV.scoreBrief(token, {edit})`), `catalogue.js` (`renderObjective`, `hvSelection.refresh`) | The selection's "Add objective": AI-card world in a dialog (Helvy reacts, campaign-power meter, six-step track, optional link/file fill). Goals multi-select. Scores only the creators already in the selection. Full-power wait with named steps, then the page refetches `/api/selection` and redraws (no reload). Done state: "Objective added · Awareness, Engagement · Edit"; Edit reopens the answers from `/api/brief/for` (now returns `answers`). |
| Several goals | `matcher.py` (`objective_for`, goal `multi_ok`), `fit.py` (`objective_of`, `blend`, `known_objective`, `objective_label`) | Stored as `Awareness+Engagement`; weights are the average of the goals' weights; "Balanced" next to a real goal adds nothing. Single-goal answers and every other caller are unchanged. |
| Add more like these | `portal.js` (`HV.cooking({list:true})`), `connect.js` | Helvy's desk sequence beside named steps that light up one by one with a bar; the steps finish before the creators land. |
| Speed | `catalogue.js` (selection `render`), `db.creators_by_codes`, `portal.memo_*`, `server.py` | Selection page keeps only its own cards on the page and redraws only them; decisions are optimistic (rolled back on a failed save); the page tells the loader it is ready once its cards are drawn. `/api/selection` reads only the selection's creators and asks the team / active-campaign questions once per request (memo on GETs and the selection-decision POSTs only). |

Tests: `python3 admin/tests/e2e_portal_fixes3.py` (objective, replacement, payload, memo), `e2e_portal_fixes3_account.py` (selection / brief delete), `e2e_portal_fixes3_gating.py` (what an un-granted client receives).

## Fix batch 4 (branch `portal-fixes-4`, 2026-10-10)

| Piece | Where | Notes |
|---|---|---|
| ROI budget digits | `connect.js` (`budgetBox`), `roi.py` (`ascii_digits`, `parse_budget`) | Arabic-Indic (٠-٩) and Persian (۰-۹) digits and the Arabic separators are read as digits, in the field (caret kept, IME composition respected) and on the server (estimate and the chat's "what can SAR ٦٠٬٠٠٠ do" reader). |
| ROI as ranges | `roi.py` (`band_of`, `SPREAD`), `connect.js` (`fig`, `resultPanel`, `printPdf`, `roiCard`) | Each figure carries `range` [low, high]: counts and rates ±20 %, costs the inverse band, frequency ±15 %, two significant figures. The client sees only ranges. No `advice` and no `sources` are sent (old saved estimates are stripped in `row_view`); the page, PDF and chat card say "Estimate, not a result. Real results depend on the content, the timing and the audience." The Calculator's goals stay Awareness / Engagement / Traffic. |
| Launch windows | `occasions.advise` | Strict order: the brief's sector first, then the soonest; with a launch date, windows within 45 days of it first, then the same rule by closeness. |
| AI shortlist goals | `matcher.py` (goal options + `legacy`), `fit.py` (`Traffic` in `WEIGHTS`, `WEIGHTS_BASIC`, `LINK_ROUTE`), `portal.js` (`ask`) | Awareness, Engagement, Traffic, Conversion (= the old Sales weights), Other; several at once on the card ("Awareness+Traffic"). Traffic weighs engagement, views and market and adds a "Link clicks" part from the platform's link route (Snapchat swipe-up 1.0, Instagram story sticker 0.85, YouTube description 0.7, TikTok bio 0.6). Old "balanced" answers still read; campaign objective `traffic` now maps to Traffic. |
| Helvy on lime | `hv-loader.js` (`video(name, {set: "voice"})`), `portal.js` (`HV.lime`) | The `assets/brand/voice/` clips (opaque H.264 / VP9, lime background) in lime discs: AI card intro (loop), coach (point, think, thumbs, cheer), the Building stage (camera scan), the result (cheer); Add more like these (loop, thumbs on a quick pick, scan while working, cheer when added). A reaction's follow-up loop plays on the same `<video>`, so a clip a tap started keeps playing in Safari Low Power Mode. |
| Chat Helvy | `connect.css` (`.cx-launch`), `portal.js` (`headWorking`) | The launcher shows the whole character inside the disc (no head over the edge). While Helvy works on an answer the header and the thinking bubble play his desk sequence until the last word is typed. |
| Selection close | `catalogue.css` | The close section and footer no longer stack two ink paddings and an empty status line; the footer starts on a hairline. `a.cat-btn` no longer underlined. |
| Trusted by | `portal.js` (`LOGOS` third value), `connect.css` | Per-logo heights for equal optical area (and ink density), 16–32 px, one tone (white at 62 %). |

Tests: `python3 admin/tests/e2e_portal_fixes4.py`, plus `test_roi.py` (Arabic digits, ranges), `test_matcher_other.py` (goals, Traffic), `test_briefsrc.py` (launch window order).
