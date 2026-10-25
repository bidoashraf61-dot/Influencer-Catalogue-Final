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

## Phase 1 — the gate

1. `modules.py`: one declarative registry — per module, its route prefixes, nav
   entries, tables, client-API payload keys and background jobs. The same shape
   as `ui.NAV` / `ui.STAFF_ONLY` / `ui.KAM_HIDDEN`, which already work this way.
2. `tenant_modules` table: tenant, module, on/off, changed_at, changed_by.
3. One gate: a thread-local tenant (as `ui.set_role` does for roles), one check
   in the router, one in the nav builder, one in the client API payload.
4. Switches on the client's page in the admin, with History.
5. Carve out Intelligence end to end as the pilot, then Track module by module.

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

Tenant self-service, per-tenant branding, billing, cross-tenant reporting, and
any split of the roster.
