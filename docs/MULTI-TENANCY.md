# Multi-tenancy and module switches

Brief and plan, agreed with Bido on 25 October 2026. Phase 1 only is specified in
full; later phases are sketched so the seams are cut in the right place now.

## What a tenant is

A **tenant is a client company** — today a row in `codes` (47 of them) with the
portal `users` (21) attached to it. HelloVoice itself is not a tenant: its team
works across every client and keeps doing so.

## What a module is

A module is a product a tenant either has or does not have. Two exist, plus the
core that is never switchable.

| Module | Name in the product | Owns | Routes |
|---|---|---|---|
| `core` | — | creators, selections, codes, quotes, portal, team, gating, fit | everything not listed below |
| `helvi-intelligence` | Helvi Intelligence | `evidence_packs`, `evidence_posts`, `evidence_roster` | `/evidence/*`, the pack on the selection page, its Apify import |
| `helvi-track` | Helvi Track | `campaigns` and ~25 tables (clicks, content, insights, snapshots, comments, `push_*`, roi, sales) | `/campaigns/*`, `/go/`, `/campaign/#t=`, the capture jobs, the weekly digest, push |

### How coupled each one is (measured, not guessed)

| | Intelligence | Track |
|---|--:|--:|
| Files that mention it | 18 | 74 |
| References in `server.py` | 72 | 437 |
| References in `db.py` | 0 | 285 |

Intelligence owns its own `SCHEMA` and touches the roster only to match handles:
it is already a module. Track is the spine — campaigns reach into selections,
creators, the portal, push, KAM scope, the report and the client app. Treat
Intelligence as the pilot and Track as the project.

## Rules

1. **Off is server-side first.** An off module's routes refuse before anything is
   rendered; hiding the nav entry is cosmetic and never the gate.
2. **Off hides, it never deletes.** A tenant whose Track is switched off keeps
   every campaign, report and captured post. Switching it back on restores the
   lot untouched.
3. **HelloVoice owners and admins flip the switches**, on the client's page in
   the admin — the same gate as the "Client sees" switches (`selfilters.can_publish`).
   Never a KAM, never the client.
4. **Every existing client starts with everything on**, so the day the gate ships
   nothing changes for anyone.
5. **The core is not switchable.** A tenant with both modules off still has a
   roster, selections and quotes.

## The super admin dashboard

Everything a tenant has is configured in one place: **Tenants**, a new section in
the admin sidebar. No new role — the existing **owner** holds it, so 2FA, History
and the idle limit apply unchanged. Admins run the business; owners configure the
platform.

One tenant, one page, three panels:

| Panel | What the owner sets |
|---|---|
| **Modules** | Helvi Intelligence and Helvi Track at `off` / `view` / `manage`. Off hides, never deletes. |
| **Limits and credits** | AI credits, seats, campaign and selection caps, capture jobs per day |
| **Branding** | Logo, colours, the name on reports and in the client app; its domain later |

Rules: every value has a **platform default**, and a tenant row only records what
differs from it — so a new tenant works before anyone configures anything, and a
default can be changed in one place. Every change is written to History with who
and when. Nothing here is editable by an admin, a KAM or the tenant.

Limits are enforced **server-side at the point of spend**, the way the AI monthly
caps already are: a cap that only greys out a button is not a cap.

## What a tenant runs themselves

A tenant has **full control of their own data**. There is no approval step: what
they add is live the moment they add it. The brake is the per-tenant caps, and a
cap only counts where it is enforced — at the point of spend, server-side.

So a module switch is **not a boolean**. Each module is set per tenant to one of:

| Level | Means |
|---|---|
| `off` | the routes refuse, nothing is shown, the data is kept |
| `view` | they read what HelloVoice produced (today's behaviour) |
| `manage` | they add, edit and delete their own, inside their caps |

### Track at `manage`

Today every write to a campaign is team-only — `contentedit.py` says so in as
many words: *"Clients and view-only team logins never get these routes."* The
tenant gets their own endpoints, not those: add and edit their posts and links,
add creators to their campaign, trigger a refresh. The existing `pending` queue
stops being an approval gate and becomes the tenant's own draft state.

### Intelligence at `manage`

There is no competitor object today. A pack exists only because somebody ran
`build_evidence_pack.py` offline and uploaded the sheet at `/evidence`. For a
tenant to add their own competitor this has to be built:

1. `competitors` per tenant — name, handles per platform
2. an intake that runs the collection (the Apify path the capture jobs use)
3. the result landing as a pack, filed under that tenant

That run **spends real money**, and with no approval in front of it the per-tenant
monthly cap is the only thing standing between a tenant and the bill. It is
checked before the job is queued, the way the AI helper caps already work.

## What the super admin sees and overrides

The owner sees every tenant's configuration on that tenant's page, and can
override any of it: module levels, caps, credits, branding — and the data the
tenant manages, where it is wrong.

- **See it as they do.** The "View as client" ticket already exists
  (`as_client`): the owner opens the tenant's own surfaces without a second login.
- **Override, with the trail.** Every override is written to History with who,
  when and the value before — a tenant's own change and an owner's override are
  told apart.
- **An override sticks** until it is cleared; it does not get overwritten the
  next time the tenant edits their settings.
- A tenant never sees, and never sets, another tenant's anything.

## Phase 1 — the gate

**Built on 25 October 2026.** `modules.py` (registry, levels, the gate), `tenants.py`
(the page), `tenant_modules` (the table), one check in `_do_get` and one in `_do_post`,
and **Tenants** in the sidebar under Control, owner only. Every client is on `view` for
both modules, which is how they already worked, so nothing changed for anyone on the day
it shipped. Limits, credits and branding are the next slice; `manage` is accepted and
stored but still behaves as `view` until the tenant-side endpoints exist.

### The original plan

1. `modules.py`: one declarative registry — per module, its route prefixes, nav
   entries, tables, client-API payload keys and background jobs. The same shape
   as `ui.NAV` / `ui.STAFF_ONLY` / `ui.KAM_HIDDEN`, which already work this way.
2. `tenant_modules` table: tenant, module, level (`off`/`view`/`manage`), changed_at, changed_by.
3. One gate: a thread-local tenant (as `ui.set_role` does for roles), one check
   in the router, one in the nav builder, one in the client API payload.
4. The **Tenants** section above: one page per tenant, the three panels, History
   on every change, owner only.
5. `tenant_limits` and `tenant_brand` beside `tenant_modules`, each row holding
   only what differs from the platform default.
6. Carve out Intelligence end to end as the pilot, then Track module by module.

## Phase 2 — the data split

`db.connect()` is the single chokepoint: one module-level `DB_PATH`, and only
three files touch `sqlite3.connect` directly (`db.py`, plus `assistant.py` and
`track.py` on unrelated files). So a **database file per tenant** is a change to
one function plus a migration, not a rewrite.

It cannot hold everything, though: the 14k-creator roster, the creator analyses,
the team and the house benchmarks built from every campaign are shared assets and
cannot be copied 47 times. The split is therefore:

- **shared core DB** — creators, analyses, tiers, admins, benchmarks, settings
- **per-tenant DB** — that client's selections, campaigns, evidence packs,
  content, comments, push state, credits, activity

## Out of scope for now

Billing and
invoicing, cross-tenant reporting, per-tenant API keys and background-job
control, and any split of the roster.
