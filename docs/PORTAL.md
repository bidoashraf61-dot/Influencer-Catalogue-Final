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
- **Insights → AI copilot** (`/ai`): ask about the data; ask for changes. A
  change is queued as a plain sentence and only runs when you press **Confirm**.
  It is recorded in **History & undo** like any other edit.
- The selection page shows **Client brief** when the shortlist came from the AI.
- Access codes can carry their own **AI credits** at creation.

## How it works

| Piece | File | Notes |
|---|---|---|
| Abuse controls | `guard.py` | Rate limiter, CSRF origin check, company-email rules |
| Accounts, OTP, credits, briefs, chat store | `portal.py` | Tables created by `portal.init()` (additive) |
| Gemini over HTTPS | `gemini.py` | Key in `.gemini-key`, audit table, monthly token ceiling |
| Email over HTTPS | `mailer.py` | Resend; key in `.mail-key` |
| Brief → ranked shortlist | `matcher.py` | Deterministic scoring with `fit.py`; Gemini only parses text and writes reasons |
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

1. **Resend**: create an account, verify the `hellovoice.co.uk` sending domain
   (DNS records), create an API key. Admin → Client portal → Settings & keys →
   *Email (Resend)* key, and check "Send email from".
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
