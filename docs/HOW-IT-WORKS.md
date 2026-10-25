# How the system works, and who does what

Written 25 October 2026, when modules became switchable per tenant. It describes the
product as any company would meet it, then what each role does day to day.

## The shape of it

One platform, three products, many tenants.

- **HELVi Connect** — the core. The roster, selections, quotes, the client's account.
  Every tenant has it; it cannot be switched off.
- **Helvi Intelligence** — competitor evidence. Which creators already worked with a
  client's rivals, and how those posts did.
- **Helvi Track** — campaign tracking. The dashboard, the report, tracking links, posts,
  insights, what people said.

A **tenant is a client company**. Each one is set to `off`, `view` or `manage` on each
module, so two clients can be sold two different products on the same platform.

## The flow, end to end

```
   A brief arrives                      HelloVoice builds              The client decides
   ───────────────                      ─────────────────              ──────────────────
   client or KAM            →   selection from the roster      →   approves, rejects, asks
   says what they need          priced, scored, tagged             for changes on their own page
                                                                             │
                                                                             ▼
   Proof, before the money                                          The campaign runs
   ───────────────────────                                          ─────────────────
   Intelligence: who already        ←───────────────────────→       Track: links, posts,
   worked with their rivals                                         numbers, comments, report
```

Read it as one line: **brief → selection → approval → campaign → report**, with
Intelligence feeding the pitch and Track proving the result.

## The roles

### Owner (Bido)
Configures the platform, not just the business. **Control → Tenants** is yours alone:
which modules each client has, their caps and credits, their branding. You also see every
tenant's configuration and can override any of it; every override is in History with the
value it replaced.

Day to day: set a new client's modules when they sign, watch the collection spend, and
decide when a module moves from `view` to `manage`.

### Admin
Runs the business across every client. Everything an owner has except the team and the
Tenants page: roster, selections, quotes, campaigns, evidence packs, the "Client sees"
switches, scores and analysis.

Day to day: build and price selections, publish scores when a client should see them,
import a competitor study, keep campaigns' content and numbers right.

### Key account manager
The same work, fenced to her own clients. A KAM never opens the pages that read across
every client — the roster, analytics, history, evidence list, access codes — and never
flips a module, a cap or a "Client sees" switch.

Day to day: her clients' selections and campaigns, their quotes, their briefs, the next
step on each account.

### The client (a tenant's people)
What they can do depends on their module levels:

| | `view` | `manage` |
|---|---|---|
| Selections | read, approve or reject, tag, request a creator | the same |
| Helvi Track | read the dashboard and report, start a campaign draft, ask for a refresh | **also** add and fix their own posts and links |
| Helvi Intelligence | read a pack HelloVoice shared, add its creators to a selection | **also** name their own competitors and collect them |

At `manage` nothing waits for approval — what they add is live. The brake is their caps:
how many campaigns and selections, how many collections a day, how many dollars a month.

## Working the new system

1. **When a client signs** — issue their account as before, then open **Tenants** and set
   their modules. Everything starts at `view`, which is how clients have always worked.
2. **When they pay for a module** — move it to `manage` and give them caps in the same
   row. A cap with nothing in it means no limit, so type one for anything that spends.
3. **When they ask for competitor work** — at `view`, HelloVoice studies and imports the
   pack as before. At `manage`, they name the competitor themselves and the collection
   files the pack under their account; the admin sees what they named on `/evidence`.
4. **When a campaign runs** — at `view`, the team keeps the posts and numbers. At
   `manage`, the client can fix their own, and History shows `client: <email>` beside
   each change so the two are never confused.
5. **When something looks wrong** — History and the security log answer who changed what.
   For a module, a cap or branding, the security log names the owner who set it.

## What is not built yet

Seats and branding are stored but not applied anywhere. Collection reads Instagram only.
There is no tenant-facing screen for the `manage` endpoints yet — they answer, but the
client's page does not offer them. The data split (a database per tenant) is phase 2.
