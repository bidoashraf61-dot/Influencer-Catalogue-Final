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

## Portal v3: HELVi Connect (branch `portal-v3`)

| Piece | File | Notes |
|---|---|---|
| Bell (in-portal notifications) | `inbox.py` | Table `notifications`, per account. Groups: analysis, selections, campaigns, account, ideas (off by default). Toggles only filter the bell; history keeps everything. Never emailed. |
| Analysis gating | `gating.py` | Table `analysis_grants`. Free headline only (followers, platforms, average views, engagement, data date). The locked page is the real analysis page (same sections, cards and tabs) drawn from `gating.sample(code, platform)`, a whole analysis made from the code alone, blurred under Sample data + Locked. Requests only for creators in the client's (team's) selections. Admin **Fulfil** on Creator analysis, or an upload, unlocks for the client's team and rings the bell. Past handled requests became grants on first start. Fit-score evidence (measured audience part, its strengths and watch-outs, audience checks) and assistant tools (incl. average likes and comments) hide locked figures; discovery filters only on engagement and views for a client; content ideas drafted from the analysis are not served to a client it is locked for. |
| Selection status | `selstatus.py` | Table `selection_status`. Owner approves / rejects (optional reason); HelloVoice sets anything incl. Unavailable (admin selection page → **Client status** tab, or the client page). HelloVoice changes ring the bell; client changes email the KAM once per 5-minute burst (`notify` event `status`). **Find a replacement**: 2 credits (`costs.replace`), three similar creators kept on the row, reopening is free. |
| Rewards and invites | `rewards.py` | Profile rewards (30 in all, once, non-blank) as ledger lines `Profile reward: …` with ref `reward:<step>`; invites table; +20 to the inviter on the colleague's first sign-in (same domain, max 5). |
| Profile page | `account/index.html`, `assets/js/account.js`, `assets/css/account.css` | Overview, Selections, Analyses, Campaigns, Briefs, Notifications, Credits, Account. New profile fields: brands, industry, markets, language (pre-fill briefs). Helvi's picture is ONE file: `assets/brand/helvy.webp`. |
| Bell UI, icons | `assets/js/portal.js`, `assets/css/portal.css` | Bell between Campaign tracking and the account circle, account holders only. |

New client routes: `GET /api/notifications`, `POST /api/notifications/read`, `POST /api/selection/status`, `/api/selection/reason`,
`/api/selection/replace`. Admin: `POST /analysis/fulfil`, `POST /selections/status`. All tables are created by `portal.init()`.

Tests: `python3 admin/tests/e2e_portal_v3.py` and `e2e_portal_fixes3_gating.py` (locked figures never appear in `/api/creator`, selection scores, look-alikes, more, replacements, the AI shortlist, ideas, Helvi's tools or discovery; a granted client gets them all).

## Phases C + D: HELVi Connect (branch `portal-cd`)

| Piece | File | Notes |
|---|---|---|
| Sign-in scene | `assets/js/portal.js` (`enhanceGate`), `assets/css/connect.css` | Client door (work email, six-box code, first-time name / company / job title) and HelloVoice team door (admin access person by person). No access-code link on the client door; a selection or campaign link that still needs its code shows "Opened a shared link?", and `?access=code` shows it on the catalogue. |
| Sign-in code email | `admin/mailer.py` (`OTP_HTML`) | 600px table, inline styles, PNGs on the catalogue host (`assets/brand/email/`), VML button, dark mode. |
| Access codes → accounts | `admin/codelinks.py`, Client portal → **Access codes → accounts** | Invite a shared code's client to an email account: the account sees and owns the code's selections and campaigns (`portal.team_codes` / `portal.owns`). Codes are never revoked or moved here. |
| AI free during a campaign | `portal.charge` / `portal.active_campaign` | Every AI action is free from a (team) campaign's start date to its end date + 30 days. `/api/me` → `ai_free`. |
| How HELVi works (item 179; the tour was removed in item 180) | `welcome/index.html`, `assets/js/welcome.js`, `assets/css/welcome.css`, `assets/welcome/` (film + poster); Account -> Overview card in `assets/js/account.js` | Public page, no sign-in. See "How HELVi works" below |
| ROI Calculator | `admin/roi.py`, `admin/connect_api.py`, `connect.js` | Deterministic, free. `plans.LIBRARY` (+ house results, + creators' own averages), grades good / moderate / low. Table `roi_estimates`; estimate vs actual per campaign. Routes `/api/roi/*`. |
| AI on selections | `admin/aimore.py`, `admin/aiadd.py` | `/api/selection/alike` (2, kept so reopening is free); "Add creators with AI" (item 178): `/api/selection/ai-add`, `/ai-add/find` (AI shortlist price, refunded when no one new), `/ai-add/add`. `/api/selection/more` retired 2026-10-20. Tables `selection_alike`, `selection_aiadd` (`selection_more` kept for history). |
| Helvi knowledge | `admin/helvy_kb.py`, `admin/occasions.py`, `assistant.py`, `knowledge.py`, `faq.py` | Tools `campaign_results` (own, named via Settings, or aggregates over 3+ campaigns), `occasions`, `my_decisions`, `roi_estimate`; KSA rules; **no prices ever** (price tool removed, prices stripped from creator views, FAQ routes to a quote). |
| Privacy / Terms | `privacy/`, `terms/` | **Drafts pending legal review.** |

Tests: `python3 admin/tests/e2e_portal_cd.py`, `python3 admin/tests/test_roi.py`.

## Fix batch 2026-10-09 (branch `portal-fixes-2`)

| Piece | Where | Notes |
|---|---|---|
| Helvi's files | `assets/js/hv-loader.js` (`window.HVHelvy`) | The ONE place the clips are named. Transparent, waist-up: `helvy-<name>.webm` (VP9 alpha, Chrome/Edge/Firefox) and `.mov` (HEVC alpha, Safari and every iOS browser), `helvy-still.webp`; `assets/brand/helvy.webp` is the transparent head still for small avatars. Names: idle, hello, bye, loader, thinking, celebrate, point, cards, stamp. Bump `VER` (and the `?v=` on the still) when the files are replaced: `/assets/` is cached 30 days as immutable. |
| Autoplay | `HVHelvy.video()` | muted / defaultMuted / playsinline / autoplay / loop set before the source, retried on canplay and visibility, paused off screen, the still if autoplay is refused (no play button). Ambient clips wait for the page to load; `eager` ones (loader, coach) do not. |
| Cooking | `portal.js` `HV.cooking()` | thinking -> cards -> stamp with rotating steps, for Add more like these, Creators like this and Find a replacement. |
| Loader rule | `hv-loader.js` | Shell first; the Helvi loader only if the page is not ready after 0.6 s, gone by 1.5 s; images never waited for. The catalogue calls `hvLoader.done()` when its first cards are drawn. |
| Roster | `server.py` `roster_body()`, `catalogue.js` | Serialised + gzipped once per roster version with an ETag (304 on If-None-Match); the page keeps it in sessionStorage per tab (`hv-roster`, dropped on sign-out / 401 / before `exp`), shows the shell and skeletons at once, renders 48 cards then the rest in idle slices. Card photos are lazy `<img>`. |
| No objective, no score | `server.py` `selection_has_objective()` | `/api/selection` sends `scores: {}` and `needs_objective: true` until the selection has an objective (client brief, AI brief, admin, or its campaign). The page shows "Add your campaign objective to score these creators" (`HV.scoreBrief`). |
| Reject reason | `catalogue.js` | A "?" beside Rejected: pop-up with the reasons, Other + note, Skip / Save; the saved reason on hover / focus. |
| Promise | `gating.WORK_DAYS = 1` | Full analysis within 1 working day (Friday and Saturday skipped). |

Tests: `python3 admin/tests/e2e_portal_fixes2.py`.


## How HELVi works: the onboarding film (2026-10-20, items 179 + 180)

The in-portal tour (v3, item 40: `tour.js`, `tour.css`, `assets/demo/`, the demo frame hooks in
`hv-loader.js` and `portal.js`, the first-sign-in "Take the 3-minute tour?" opener) was **removed**
in item 180. Onboarding is now one short film on its own page, **`/welcome/`** (public, no sign-in):

- the film with a branded poster and a lime play control; it is **lazy** (`preload="none"`, no
  `src` until play or a chapter is pressed), `playsinline`, native controls once playing, so it
  works in the installed app and on phones; it pauses when the page goes to the background;
- beside it (under it below 1100px) the **chapters**, which double as the notes on what the portal
  does. Once the real film is in, set each chapter's start time and `TIMED = true` in
  `assets/js/welcome.js`: chapters then show their time, jump to it, and light up as the film plays;
- a closing band: Open the catalogue / Go to my profile.

Ways in: **"Watch how it works"** on the catalogue cover (`build/influencer_catalogue.py`), **"How
HELVi works"** in the profile menu (replaces "Take the tour") and the profile sidebar, and the ink
**"How HELVi works"** card on Account -> Overview.

**First sign-in card (Bido, 2026-10-20):** a one-time ink "Welcome, <name>. Watch how it works"
card (bottom-left; on phones above the bottom bar) links to `/welcome/`. Once per account, kept on
the server by reusing `users.tour` through `POST /api/tour` ("offered" when shown, "later" when
dismissed), so accounts that already saw the old tour offer never get it. It waits until the app's
setup prompts (desktop QR welcome, phone Home Screen guide, alerts card) and any dialog have
closed, and the app's prompts in turn wait for it (`.cx-hiw` is in app.js's busy check).
Code: `connect.js` (HOW HELVi WORKS block), styles in `connect.css`.

**The film file:** `assets/welcome/onboarding.mp4` is a 6-second branded placeholder until the
final film arrives. Replace it (H.264 + AAC, 16:9, faststart), optionally replace
`assets/welcome/onboarding-poster.jpg`, then deploy: `update.sh` stamps both with `?v=<hash>`
(the poster inside `account.js` too), so every browser and the installed app get the new file.
The service worker does not cache `/assets/welcome/` (range requests go straight to the network).

Server side is unchanged: `POST /api/tour` and the `users.tour` column stay (credits already paid
for the tour are kept) and now carry the first-sign-in card's once-per-account flag. Helvi's knowledge line about the tour
now points to `/welcome/` (`admin/knowledge.py`, needs the usual manual copy to the admin).

## Phase E (branch `phase-e`, 2026-10-10)

| Piece | Where | Notes |
|---|---|---|
| Brief from a link or a file | `admin/briefsrc.py`, `admin/phase_e_api.py` (`POST /api/brief/source`), `portal.js` (`HV.briefSource`) | "Paste a product link" / "Upload a brief (PDF or Word)" in the brief window (step 1, also the selection's objective questions), the AI shortlist card ("Or start from a product link / brief file") and the chat's Find creators flow. Gemini fills product, space, audience, markets, objective and timing with a confidence each (Found / Check / A guess / Not found); the client edits and confirms, nothing is saved by this route. Claims are only kept when they are written in the source; regulated products (medicine, cosmetic, supplement, device) get the claims flag, KSA briefs the Mawthooq flag. Cost `source` = 5, free during an active campaign; nothing is charged when the source cannot be read; refunded on an AI failure. Without a Gemini key the free keyword reader fills what the text says plainly. |
| Fetch safety | `briefsrc.check_url / resolve / fetch` | http/https only, ports 80/443, no user:password, our own hosts refused (`*.hellovoice.co.uk`, the box's name and IP, `*.local/.internal`, extra names in setting `brief_fetch_block`, extra IPs in `brief_fetch_block_ips`); every DNS answer must be public (no loopback, private, link-local incl. 169.254.169.254, CGNAT, multicast, reserved, mapped); the socket goes to the checked address (no rebinding); redirects followed by hand (3) and re-checked; 8 s per step, 15 s total, 2 MB read cap. |
| File reading | `briefsrc.extract` | PDF through PyMuPDF (already vendored in `admin/_vendor` on the server), else a small stdlib reader for ordinary text PDFs; Word `.docx` through `zipfile` (zip-bomb checks); `.txt`; old `.doc` asks for .docx/PDF; scanned PDFs say so. 4 MB upload cap; bodies over the cap are refused before parsing; the bytes are dropped after extraction. **No new dependency.** |
| Timing advisor | `occasions.advise`, `GET /api/timing`, `helvy_kb.upcoming` (`weeks_away`, `advice`), assistant rule 8 | "Saudi Derm Congress is in 14 weeks: cast now." in the brief-from-source result, the brief review, the shortlist result (`/api/brief/run` → `timing`) and the chat review; Helvi uses the same line in chat. Cast now = 6–14 weeks out; tighter = brief this week; further = brief by a date; under 3 weeks is left out. No prices. |
| Content ideas | `admin/ideas.py`, `GET/POST /api/ideas`, `connect.js` (`HV.ideas`), `catalogue.js` (card button) | 2–3 hooks + concepts, English and Saudi Arabic, fitted to the creator's card fields and, only when the full analysis is unlocked for this client, their best-post captions, brands and audience; plus the selection's brief. Lines mentioning money are dropped; no claims beyond the brief. Kept per selection (or per client on the creator page), so reopening is free; "New ideas" costs again. Cost `ideas` = 2, free during an active campaign. Helvi's "cooking" sequence while it writes. Table `content_ideas`. |
| Weekly campaign update | `admin/weekly.py` (`weekly`, `verdict`) | Bell only (kind `camp_weekly`, group Campaigns): title "<campaign>: on track", body three lines (main goal vs target and what is due, engagement vs benchmark, posts live + leader); opens the report. Week n counted from the start date (first after 7 days); none without posts. Idempotent: table `campaign_weekly (campaign_id, week)` + bell ref `week:<id>:<n>`. No email, no PDF. |
| What to do next time | `weekly.next_time / recommend / panel`, `GET /api/campaign/next?t=`, `connect.js` (`campaignNextTime`) | When a campaign is marked Ended (instant, via the `campaign_status` hook) or its end date has passed (next tick): Book again / Replace / One more test from rank on results, engagement vs the benchmark for the creator's size and posts delivered vs booked, plus up to three look-alikes of the best performer. Refreshed for 21 days after the end as late numbers land, then frozen. One bell (`camp_next`). Optional Gemini rewording of the summary with setting `next_time_ai` (off by default). Table `campaign_next`. |
| Job schedule | `weekly.start()` in `server.main` | Runs 30 s after the admin service starts, then every hour (same pattern as the Apify scheduler); each tick is idempotent, so restarts never send twice. Manual run: `sudo docker exec influencer-catalogue-admin python3 /app/admin/weekly.py`. Last run time in setting `weekly_last_tick`. |
| Voice | `portal.js` (chat compose) | Browser speech-to-text (Web Speech API) with an EN / ع (Arabic, Saudi) switch kept per browser; what is heard shows live above the box and is sent as a normal message when the client stops; Helvi replies in text. HelloVoice records and stores no audio (Chrome / Edge / Safari do the recognition themselves). Unsupported browsers: no mic, a tooltip on the box. |

Also: `connect.js` now runs once even when `portal.js` has injected it before the page's own tag (the look-alike sheet used to open twice).

Tests: `python3 admin/tests/test_briefsrc.py` (URL safety incl. SSRF, extraction, claims, timing), `python3 admin/tests/test_weekly.py` (weekly idempotency, next-time logic), `python3 admin/tests/e2e_portal_phase_e.py` (routes, credits, refunds, privacy, stubbed Gemini).

## Fix batch 3 (branch `portal-fixes-3`, 2026-10-10)

| Piece | Where | Notes |
|---|---|---|
| Helvi autoplay | `hv-loader.js` (`HVHelvy`) | A refused autoplay (Safari in macOS/iOS Low Power Mode refuses every one) no longer swaps the clip for the still for good: the still stands in while the clip waits (hidden, no play button), and play is retried on canplay, on returning to the tab and on the first tap/click/key anywhere. Only a clip the browser cannot decode stays a still. |
| Chat launcher | `connect.css` | Helvi on a lime disc (#d8ff45); ink behind the close cross when open. Every other Helvi stays a transparent cut-out. |
| AI shortlist card | `portal.css`, `portal.js` | Closed card is a two-row ink panel: Helvi on a lime circle, title, Start; then "Or start from" + Product link / Brief file on their own row. Phone: Start full width, the two sources side by side. |
| No catalogue fit scores | `portal.js` | The brief "FIT x%" pills, their MutationObserver, the `/api/brief/scores` call and the "Fit scores shown" chip are gone from the catalogue. Scores exist only in a selection with an objective, on the round `.cat-score` stamp (number + %, BASIC/MATCH label). |
| Replacement panel | `connect.js` (`HV.replaceSheet`, shared `suggestSheet`), `catalogue.js`, `server.py` | Find a replacement opens the same side panel as Creators like this. `/api/selection/replace` items now carry `why` ("In X's place: …", card fields only). Kept three free on reopen, Show 3 more costs again; added creators join Under review, the rejected creator stays rejected. |
| Objective studio | `portal.js` (`objectiveStudio`, `HV.scoreBrief(token, {edit})`), `catalogue.js` (`renderObjective`, `hvSelection.refresh`) | The selection's "Add objective": AI-card world in a dialog (Helvi reacts, campaign-power meter, six-step track, optional link/file fill). Goals multi-select. Scores only the creators already in the selection. Full-power wait with named steps, then the page refetches `/api/selection` and redraws (no reload). Done state: "Objective added · Awareness, Engagement · Edit"; Edit reopens the answers from `/api/brief/for` (now returns `answers`). |
| Several goals | `matcher.py` (`objective_for`, goal `multi_ok`), `fit.py` (`objective_of`, `blend`, `known_objective`, `objective_label`) | Stored as `Awareness+Engagement`; weights are the average of the goals' weights; "Balanced" next to a real goal adds nothing. Single-goal answers and every other caller are unchanged. |
| Add more like these | `portal.js` (`HV.cooking({list:true})`), `connect.js` | Helvi's desk sequence beside named steps that light up one by one with a bar; the steps finish before the creators land. |
| Speed | `catalogue.js` (selection `render`), `db.creators_by_codes`, `portal.memo_*`, `server.py` | Selection page keeps only its own cards on the page and redraws only them; decisions are optimistic (rolled back on a failed save); the page tells the loader it is ready once its cards are drawn. `/api/selection` reads only the selection's creators and asks the team / active-campaign questions once per request (memo on GETs and the selection-decision POSTs only). |

Tests: `python3 admin/tests/e2e_portal_fixes3.py` (objective, replacement, payload, memo), `e2e_portal_fixes3_account.py` (selection / brief delete), `e2e_portal_fixes3_gating.py` (what an un-granted client receives).

## Fix batch 4 (branch `portal-fixes-4`, 2026-10-10)

| Piece | Where | Notes |
|---|---|---|
| ROI budget digits | `connect.js` (`budgetBox`), `roi.py` (`ascii_digits`, `parse_budget`) | Arabic-Indic (٠-٩) and Persian (۰-۹) digits and the Arabic separators are read as digits, in the field (caret kept, IME composition respected) and on the server (estimate and the chat's "what can SAR ٦٠٬٠٠٠ do" reader). |
| ROI as ranges | `roi.py` (`band_of`, `SPREAD`), `connect.js` (`fig`, `resultPanel`, `printPdf`, `roiCard`) | Each figure carries `range` [low, high]: counts and rates ±20 %, costs the inverse band, frequency ±15 %, two significant figures. The client sees only ranges. No `advice` and no `sources` are sent (old saved estimates are stripped in `row_view`); the page, PDF and chat card say "Estimate, not a result. Real results depend on the content, the timing and the audience." The Calculator's goals stay Awareness / Engagement / Traffic. |
| Launch windows | `occasions.advise` | Strict order: the brief's sector first, then the soonest; with a launch date, windows within 45 days of it first, then the same rule by closeness. |
| AI shortlist goals | `matcher.py` (goal options + `legacy`), `fit.py` (`Traffic` in `WEIGHTS`, `WEIGHTS_BASIC`, `LINK_ROUTE`), `portal.js` (`ask`) | Awareness, Engagement, Traffic, Conversion (= the old Sales weights), Other; several at once on the card ("Awareness+Traffic"). Traffic weighs engagement, views and market and adds a "Link clicks" part from the platform's link route (Snapchat swipe-up 1.0, Instagram story sticker 0.85, YouTube description 0.7, TikTok bio 0.6). Old "balanced" answers still read; campaign objective `traffic` now maps to Traffic. |
| Helvi on lime | `hv-loader.js` (`video(name, {set: "voice"})`), `portal.js` (`HV.lime`) | The `assets/brand/voice/` clips (opaque H.264 / VP9, lime background) in lime discs: AI card intro (loop), coach (point, think, thumbs, cheer), the Building stage (camera scan), the result (cheer); Add more like these (loop, thumbs on a quick pick, scan while working, cheer when added). A reaction's follow-up loop plays on the same `<video>`, so a clip a tap started keeps playing in Safari Low Power Mode. |
| Chat Helvi | `connect.css` (`.cx-launch`), `portal.js` (`headWorking`) | The launcher shows the whole character inside the disc (no head over the edge). While Helvi works on an answer the header and the thinking bubble play his desk sequence until the last word is typed. |
| Selection close | `catalogue.css` | The close section and footer no longer stack two ink paddings and an empty status line; the footer starts on a hairline. `a.cat-btn` no longer underlined. |
| Trusted by | `portal.js` (`LOGOS` third value), `connect.css` | Per-logo heights for equal optical area (and ink density), 16–32 px, one tone (white at 62 %). |

Tests: `python3 admin/tests/e2e_portal_fixes4.py`, plus `test_roi.py` (Arabic digits, ranges), `test_matcher_other.py` (goals, Traffic), `test_briefsrc.py` (launch window order).

## Fix batch 6 (2026-10-10, branch `portal-fixes-6`): scoring v2, ROI Calculator v3, three campaign types

| Item | Where | How it works |
|---|---|---|
| Campaign types | `fit.py` (`CAMPAIGN_TYPES`, `parts_of`, `canonical`, `blend`), `matcher.py` (`QUESTIONS`, `clean_answers`), `metrics.py` (`objective_of`, `objective_info`, `blend_key`, `brief_goals`) | Only **Awareness, Engagement, Traffic**; several at once, weights averaged. Legacy: a stored `Conversion` (alone or in a "+" blend, a brief answer `conversion`, a campaign objective `conversion`) reads as **Traffic**; `Balanced` reads as the equal blend of the three. A campaign with no objective of its own (or an unknown one) takes its selection's brief goals (a blend key like `awareness+traffic`); `balanced` and `custom` stay admin-only. Creator *roles* (Awareness / Engagement / Conversion / UGC) are a separate list and are unchanged. |
| Peer benchmarks | `benchmarks.py` | Cells per platform x size (nano <20K, micro 20-100K, mid 100-500K, macro 500K-1M, mega 1M+) x metric (`er`, `er_med`, `view_rate`, `view_rate_med`, `spread`) built at run time from `creator_analysis`, cached 10 minutes. `percentile()` answers only with >= 30 peers. Instagram engagement is per follower, TikTok/YouTube per view. Medians (`median_views`, `median_likes`, `median_comments`, `median_er_on_views`, `views_spread` / `views_series`) are preferred when a doc has them; older docs (averages) still work. |
| Scoring v2 | `fit.py` (`score_core`, `WEIGHTS_V2`) | Four parts only: **engagement** and **views** (percentile among same-platform, same-size peers), **consistency** (steadier views than peers; needs a views series, peers only), **interest** (share of the creator's content in the brief's product space: `interest_shares` field when present, else roster tags, hashtags, bio). Size is not scored: `reach_followers` is shown beside the score. Audience (country, gender, age) is a *check*, not a part. Fake-follower share >= the Settings bad bar caps the score at 39. Our own campaign record is a check and moves the number (+/-5) only from 5 posts. Weights x trust (measured 1.0, estimated 0.5, assumed 0.2); a part that fell back to the global estimate in Settings counts as estimated; a part with no benchmark at all is left out. Output adds `confidence` {level, posts, peers_n, source}, `reach_followers`, `limited_data`. |
| Weights | `fit.WEIGHTS_V2` | Awareness: views 3, engagement 1.5, interest 1.5, consistency 1. Engagement: engagement 3, interest 1.5, views 1, consistency 1. Traffic: engagement 2.5, views 2, interest 2, consistency 1. Several types: average. Balanced: average of the three. |
| Confidence | `fit.score_core` | high: >= 20 posts, >= 2 peer-benchmarked parts incl. engagement; medium: >= 6 posts and at least one peer-benchmarked part; low: otherwise (and `limited_data`). |
| ROI v3 | `roi.py`, `connect_api.py`, `connect.js` | Per post: views = the creator's median, else followers x same-size peer-median view rate, else their measured average, else the global guide; interactions = views x their own engagement rate, else peers, else guide; reach = views x reach-per-view and clicks = views x CTR (guide, estimates); all x an **efficiency factor** 0.8 + 0.4 x score/100 (mix input: 1.0). Range per post margin 0.48 x sqrt(20/n); a selection's range = sum +/- sqrt(sum((margin x value)^2)), floor +/-10 %, two significant figures. Trust line "Based on measured data for X of Y creators." No cost, CPM, CPE, CPC, verdict, frequency or advice line anywhere; the market changes nothing; the budget does not change the estimate. |
| Planner | `roi.plan`, `roi.advise` | Input: goals (multi), the client's total budget, platforms. Creators' share (`roi_creator_share`, default 0.6) and planning price per post by size (`roi_planning_prices`, default nano 650, micro 1,300, mid 3,500, macro 6,500, mega 30,000) are internal (Settings -> Client portal -> "ROI planner (internal)"), never sent. Greedy by expected result per planning price with 8 % less per further post in the same platform and size, limited by the roster's supply. With a selection: up to 3 ways to improve (remove the weakest as reserve, add the best-performing creators of the sizes the plan uses, a second post for the top 2, add a platform), ranked by gain / performance, never by price; each has an `action` the drawer shows as one button. Helvi tool `roi_plan` offers add / remove through the existing confirm-before-write `add_creators` / `remove_creators`. |
| Estimate vs actual | `roi.versus` | Views, interactions and clicks against the saved RANGE: above / within / below. Old saved estimates are cleaned on read (`clean_result`). |

Tests: `test_benchmarks.py`, `test_scoring_v2.py`, `test_roi_v3.py`, `test_penduline_backtest.py` (prints old-vs-new tables), `e2e_portal_fixes6.py`; changed: `test_roi.py`, `test_matcher_multi.py`, `test_matcher_other.py`, `e2e_portal_cd.py`, `e2e_portal_fixes3.py`, `e2e_portal_fixes3_gating.py`, `e2e_portal_fixes4.py`, `e2e_portal_fixes5.py`.

## Fix batch 7 (2026-10-10, branch `portal-fixes-7`): ROI Calculator v4, structure vs performance

| Item | Where | How it works |
|---|---|---|
| No budget, no prices, no market | `roi.py`, `connect_api.py` (`_roi_input`), `connect.js`, `assistant.py`, `knowledge.py`, `matcher.roi_seed` | The budget input, the planner (`plan_mix`, `plan`, `settings`, `parse_budget`), the market and the cost of the planner are gone. An old client that still posts `budget` or `market` is ignored. Old saved estimates strip them on read (`clean_result`, `row_view`). |
| Per post | `roi.post_values` | Views = the creator's median, else followers x same-size peer-median view rate, else own measured average, else the guide (Instagram: `IG_VIEW_RATE` nano 12, micro 12, mid 20, macro 12, mega 3 %, calibrated on 39 real reels; ROI only, `plans.LIBRARY` untouched). A median-type figure (own median, a peer cell of medians, the guide) is multiplied by `MEAN_OVER_MEDIAN` = 1.8 so totals are expected views; a measured average, and a peer cell built from creators' averages, are left alone. Interactions = views x engagement rate, reach = views x reach-per-view, clicks = views x CTR (estimates). Efficiency 0.8 + 0.4 x score/100 for a selection's creators (fit score for the selection's objective); 1.0 for the recommended structure's creators. |
| The ideal | `roi.shapes`, `roi.shape_for`, `roi.largest_remainder`, `roi.ideal_counts`, `SHAPES_DEFAULT`, setting `roi_shapes` | Same number of creators and posts as the selection (or the mix, or the brief's count when nothing is chosen), per goal a shape; several goals average; counts by largest remainder; posts spread evenly over the chosen platforms; one post per creator. |
| Selection quality | `roi._quality` | Per goal selection / ideal on the primary figure (Awareness views, Engagement interactions, Traffic clicks), averaged; rounded to 5 %; a band when the two ranges overlap by half or more. Ranges: per-post margin 0.48 x sqrt(20/n), independent errors, floor +/-10 %, two significant figures. |
| Gap | `roi._gap_words`, `roi._on_structure` | A tier more than 10 points off its recommended share of creators is named in words ("No micro creator", "Two nano creators add little"). |
| Ways to improve | `roi.advise` | Up to 3, each scored by re-running the calculator (the gain is the real change in quality): `replace` {remove, add}, `remove` {codes}, `add` {codes}, `second_post` {codes}, `add_platform` {platform}, `use_mix` {mix} (a mix input). Candidates ranked by fit score. Helvi offers add / remove / replace through `add_creators` / `remove_creators` (confirm before write). |
| API | `connect_api.py` | `POST /api/roi/estimate {goals, platforms, token? | mix?, count?}` returns `figures`, `totals`, `selection`, `ideal` (title, creators, posts, by size and platform, ranges, score, mix, shape), `quality`, `gap`, `ways`, `trust`, `note`. Also save, saved, vs. |
| UI | `connect.js` (`resultPanel`, `compareTable`, `compareRows`, `roiCard`, `printPdf`), `connect.css` | Quality stamp, gap sentence, side-by-side table, ways. The profile page works from a size mix; the chat card shows quality and the top advice; the PDF carries the table and the ways. |
| Helvi | `assistant.py` (`roi_estimate`, `roi_compare`), `portal_api.py`, `roi.from_text` | `roi_plan` is replaced by `roi_compare`. A typed "what can 10 creators do for clicks on TikTok?" gets an instant free card with the recommended structure. |
| Estimate vs actual | `roi.versus` | Compares views, interactions and clicks ranges only. |

Tests: `test_roi_v4.py` (replaces `test_roi_v3.py`), `e2e_portal_fixes7.py`, `test_penduline_backtest.py` (v4 table); changed: `test_roi.py`, `test_matcher_multi.py`, `e2e_portal_cd.py`, `e2e_portal_fixes4.py`, `e2e_portal_fixes5.py`, `e2e_portal_fixes6.py`.

### ROI v4.1 (2026-10-11): the client chooses how many creators

| Item | Where | How it works |
|---|---|---|
| Count | `roi.estimate(count=)`, `connect_api._roi_input` | `count` (whole number 1 to 60; 0, nonsense = default) sets the creators the ideal is planned for: the shape by largest remainder, one post per creator per chosen platform. The selection side is unchanged, so quality and the gap are at that number. Saved with the estimate (`input.count`); older estimates have none. |
| Output | `roi.estimate` | `count`, `ideal_count`, `count_default` (what the selection / mix has), `count_range` {low, high, text, min, max}, `compare_line` ("The ideal for 15 creators has 1 macro, 4 mid, 7 micro, 3 nano; you have 6 micro."). |
| Ranges | `roi.COUNT_RANGES_DEFAULT`, `count_ranges`, `count_range_for`, `validate_count_ranges`, setting `roi_count_ranges` | Awareness 12-25, Engagement 15-30, Traffic 8-20; several goals average the lows and the highs, rounded. A hint only: a number outside it is planned for without a warning. |
| UI | `connect.js` (`countBox`), `connect.css` (`.cx-count*`), `portal.js` (`flowIdeal`) | A stepper with the hint in the drawer, on the profile page and on the chat card (which recomputes at once, free); the chat asks goal first, then "How many creators do you want? Awareness campaigns usually run 12-25." |
| Helvi | `assistant._roi_compare_tool` | `roi_compare` takes `creators` (the count); with no selection and no number it returns the question to put to the client. |

Tests: `test_roi_v4.py` (`Count`), `e2e_portal_fixes7.py` (`test_04b`, `test_04c`, tools).


## Fix batch 8 (2026-10-11, branch `portal-fixes-8`): Helvi's working note, sample full analysis, new skills and hand-off

| Item | Where | How it works |
|---|---|---|
| #41 Working note | `portal.js` (`workNote`), `portal.css` (`.hv-wk*`), `assistant.STEP_LABEL` | While Helvi works the chat shows no box and no step list: his avatar, three typing dots and ONE line typed out ("Searching creators…", "Checking engagement…", "Scoring fit…", "Reading your campaign…"). The label comes from the `step` events of `/api/chat/stream` (server labels are plain actions, no numbers, no tool names; the client strips digits and maps older long labels); default "Reading your message…", then a slow rotation. A line stays 0.9 s at least and the answer waits until the note has been up 0.9 s. Reduced motion: no typewriter, static line. `role=status` / `aria-live=polite` with the whole line in a visually hidden span so a screen reader hears it once, not letter by letter. |
| #39 Sample full analysis | `sample_analysis.py`, `GET /api/analysis/sample`, `creator.js`, `creator.css` | On a locked / requested / outside analysis page the dark band gets "See a sample full analysis" (admins see it too, on the open band). Mouse: a small floating card previews the headline numbers and sections; touch: a tap opens (no hover needed). It opens the same page in sample mode (`#c=CODE&sample=1`), drawn by the real analysis renderer, read-only, labelled "Sample · anonymised creator", with "Back to this creator". The endpoint takes NO creator code: it serves only the configured creator (`sample_analysis_code`, default HV-HCPG-003; `sample_analysis_on`, default on), as an allow-list copy: figures as numbers, `creator.code` "SAMPLE", name "Sample creator", no handle, bio, photo, location, source, URL, post cover, caption; brand names become "Brand A…", hashtags "#hashtag1", mentions "@mention1". Nothing is served for a creator with public numbers only. Per-creator gating on `/api/creator` is unchanged (it only adds `gate.sample_full`, and `gate.admin` for admins). The Content ideas button is not drawn in sample mode. |
| #38 explain_score | `assistant.t_explain_score` | One creator's score for the open selection's goals broken into its parts (engagement and views vs similar creators with percentile and peers compared, steady views, product-space match), what each counts for, confidence and what is missing. Uses the score the client sees (the selection context now carries each score's parts) or, outside a selection, a balanced score worked out now. Locked creators: steadiness and measured product-space match are hidden and named as missing. |
| #38 compare_creators | `assistant.t_compare_creators` | Two or three creators side by side on the same parts and one plain recommendation sentence; no prices. |
| #38 campaign_report | `assistant.t_campaign_report` | The client's own live or latest (never draft) campaign: views, interactions, clicks so far against the saved estimate range (`roi.versus`), best creators, what to do next. Team-scoped; another client's campaign token returns the client's own. Costs, CPM and EMV never appear (`metrics.client_report`). |
| #38 roi_walkthrough | `assistant.t_roi_walkthrough`, `knowledge.py` | Six-step plain explanation (structure vs recommended structure, Selection quality, gap, ways to improve, how sure) plus the live `roi_compare` result for the open selection. |
| #38 Hand-off | `assistant.t_handoff` (`handoff_to_manager`), `POST /api/chat/handoff`, `assistant.handoff_event`, `portal.js` (`handoffCard`), `notify.EVENTS["handoff"]` | When Helvi cannot do something (prices, booking, availability, discounts, anything outside his tools) the `done` event carries `handoff: {reason}` (also on the FAQ price answer). The reply shows "Send this to my account manager"; a tap shows a confirm card (Send / Not now); Send posts the thread id, the open selection token and the reason. The server reads the last eight messages from the client's own stored thread (a forged thread or someone else's selection adds nothing), builds one `handoff` notify event (to the KAM and the team list; it follows the `quote` switch for teams that saved an event list earlier) with the snippet and the selection link, and Helvi confirms in one line. Throttled 6 a day with the other hand-offs. |

Credits: every new tool is read-only and free inside the chat message's own charge. No tool returns a price, fee, rate, cost or budget field (tests scan each result).

Tests: `e2e_portal_fixes8.py` (anonymisation, only the configured creator, gating unchanged, off switch, settings card, each tool on a toy roster with 40 peers, locked redaction, campaign scope, hand-off event and forgery, step labels).

## Fix batch 9 (branch `portal-fixes-9`): quote lifecycle chip and admin Create campaign

### #42 Quote lifecycle chip

One chip says where a selection stands: **Draft → Quote requested → Quote ready → Approved → Campaign live → Completed**.
It sits under the title on the selection page (with a small timeline: dates and who did it), in the selections list and
the Campaigns list of the profile, and in Helvi's context (`lifecycle.summary_line`).

| Piece | Where | Notes |
|---|---|---|
| State and timeline | `admin/lifecycle.py` | Derived from existing data: a request for the selection (`selections.request_id`, else the newest request from the same client with the same name) = Quote requested; a linked campaign live / ended = Campaign live / Completed. Added: table `selection_quote` (`ready_*`, `approved_*`, `live_at`, `ended_at`) and `quote_changes`; both `CREATE IF NOT EXISTS`, so the migration is idempotent and legacy selections read correctly with no backfill. |
| Client routes | `lifecycle_api.py`, `server.py` | `/api/selection` carries `lifecycle` (role-aware); `POST /api/selection/quote/approve {token}` is owner only (`selection_role == owner`): a colleague gets 403 `not_owner`, an admin is not the owner, a quote that is not ready gets 409. Requesting a quote is owner-only too (`/api/request`, already). |
| Edit after the request | `api_selection_save`, `assistant._save_codes` | The selection stays editable. Changing the creators while a quote exists records a change (shown in the timeline), the response carries `lifecycle.warn` = "This updates your quote request", and the account manager gets the `quote_changed` email (one per burst, `lifecycle.NOTIFY_DELAY`). A rename is not a change. The state does not regress; the admin sees "changed after the quote was marked ready". |
| Bell only | `inbox.py` | New kinds `quote_requested`, `quote_ready`, `quote_approved` (group Selections). The client is never emailed. The team gets `quote_changed` and `quote_approved` through `notify` (account manager and team addresses). |
| Client UI | `assets/js/connect.js` (`mountLifecycle`), `assets/css/connect.css` (`lc-*`, `cx-lc*`), `catalogue.js` (carries `lifecycle`), `account.js` | The owner sees Approve (two-step, inline); colleagues see "You can follow this. <owner> requests and approves the quote." A note and a link from the account manager show under "From your account manager". |
| Admin | Requests inbox, selection → Client status | Each request shows the selection's state with **Mark quote ready** (optional note up to 500 characters and an optional https link, e.g. a PDF on SharePoint). **Take back** is possible until approval. No price comes from this flow unless the account manager writes it in the note. |

Tests: `python3 admin/tests/e2e_portal_fixes9.py` (every transition, owner-only approve, colleague read-only, bell events,
edit-after-request warning and notify, no client email, legacy states, link validation).

### #43 Create campaign from a selection (admin only)

On a selection with a quote requested or later: **Create campaign** (Client status tab, Campaign tab, or Requests inbox →
Open selection). `GET /campaigns/setup?selection=<id>` is a four-step form (Basics, Creators, Tracking, Dates and review)
pre-filled by `lifecycle_ui.setup_defaults`: name, client (selection client name, else the owner's company, else the
code label), platforms from the brief, goals from the brief (`metrics.brief_goals`; several become a blend via
`metrics.blend_key`, e.g. `awareness+traffic`), creators (the client's approved ones, else everyone not rejected or
unavailable), carried costs, default capture rules (`#<client>`; disclosure `#ad #إعلان`), dates blank, destination optional.
`POST /campaigns/setup` calls the existing `db.create_campaign` (creators, costs, tracking links) and `db.save_campaign`:
the result is a **draft** linked to the selection. Going live and ending are the existing actions; the chip follows them
and the owner's bell rings (`camp_live` / `camp_final`). There is no client-side create button.

## Campaign board (items 174, 176, 177, 182; 2026-10-20, branch `feature/r20-campaign-board`)

Campaign first: a campaign is run by a KAM, filed under a client, and holds many selections (`campaigns.selection_id` is
its first; the rest are in `campaign_selections`). Six stages: Draft, Shortlisting, Client review, Approved, Live,
Completed. Live and Completed are the campaign's status; the four before are `campaigns.stage`, and a campaign nobody
staged is read from its selections (quote approved, requested or ready, creators picked, nothing) so existing data maps
with no migration writes. Logic in `admin/board.py`; routes in `portal_api.py`.

| Route | Who | What |
|---|---|---|
| `GET /api/board` | admin all, KAM hers, client own team's (read-only) | stages + cards (logos, selections, pins; KAM for staff). Never scores, costs or analysis |
| `GET /api/board/targets?s=` | anyone who may file that selection | the campaigns it can go into (pinned first) |
| `POST /api/board/attach {s, t or name}` | same | add the selection to a campaign, or start a Draft with it; the client's KAM holds it and is told (email + bell) |
| `POST /api/board/stage {t or id, to}` | **admins only** (403 otherwise) | move between stages; Live needs dates and a client |
| `POST /api/board/live {t or id, on}` | **admins only** | Live / Unlive (Unlive = back to Approved, off the air) |
| `POST /api/board/pin {t, on}` | anyone who sees it | per-person pin (`campaign_pins`, field `my_pin`; not the team's demo `pinned_campaigns`) |

UI: board and switcher in `assets/js/campaign.js` / `campaign.css` (`mx-bd-*`, `mx-cs-*`); the selection dialog in
`connect.js` / `connect.css` (`cx-camp*`); stage + Live / Unlive on hub campaign rows in `account.js` (`hubStage`).
Scores: a client or KAM never receives scores, fit badges or the publish switch on a selection, published or not.
Profile analysis: never for a client or KAM either (`gating.CLIENTS_SEE_ANALYSIS = False`; grants and publish flags stay
in the database untouched, so flipping it back restores them). Going Live rings the client's bell and push (the existing
`camp_live`); Unlive is silent. Admins on a desktop can also drag a card to another lane; the stage menu stays.
Tests: `python3 admin/tests/test_board.py`.
