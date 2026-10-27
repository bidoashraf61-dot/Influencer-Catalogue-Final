# HELVi Connect as SaaS: modules, access and journeys

Agreed with Bido, 28 October 2026. Builds on `docs/MULTI-TENANCY.md` (phase 1 is live: the gate, the
Tenants page, limits, branding, the tenant write endpoints). This file is the model the next three
pieces of work are built to: **(1)** the module split and access (this spec), **(2)** the admin
Tenants table and company pages, **(3)** the client dashboard of each module.

## Words

| Word | Means |
|---|---|
| **Company** (tenant) | A client business: a `codes` row plus its people. Individuals are a company of one. |
| **Module** | A product a company can own: **Helvi Selection**, **Helvi Track**, **Helvi Intelligence**. |
| **Entitlement** | What the company owns: module on or off, level (`view` / `manage`), limits. HelloVoice owner sets it. |
| **Role** | What one person may do in one module: `none` / `viewer` / `editor` / `admin`. The company's admin sets it. |
| **Gate** | The one server-side check on every request. |

Effective access = the lower of the company's level and the person's role. Company `off` means none for
everyone, whatever their role. `viewer` = reads; `editor` = adds and edits inside the caps; `admin` = also
invites people and sets roles for that module inside the company.

## The three modules (each works alone, all three connect)

| Module | Is | Owns |
|---|---|---|
| **Helvi Selection** | The catalogue: browse the HelloVoice roster, creator pages and analysis, shortlists, selections, quotes, AI shortlist, licence badges. | the roster view, `selections`, quotes |
| **Helvi Track** | Campaign tracking: dashboard and report, posts, links, insights, comments. | `campaigns` and its tables |
| **Helvi Intelligence** | Competitor evidence: which creators competitors used and how those posts did. | `evidence_*`, `competitors` |

The **platform** under all three is never sold and never switched off: sign in, account, people and roles,
the module switcher, History, branding, limits, the access-request inbox.

### How independence works

`creators` gets an owner. **No owner = the HelloVoice roster** (what Selection sells). **An owner = a
private creator of that company**, invisible to everyone else. Track and Intelligence already point at a
creator by code, so they work on either kind unchanged.

| The company owns | Creators come from | Connection when it owns more |
|---|---|---|
| Track only | **Add by handle**: paste a profile link, the portal reads followers and photo. Private. | Buys Selection later: private creators stay, roster creators join them. |
| Intelligence only | The study lists the creators a competitor used. A creator who is on our roster carries a **locked tag**: "Available through Helvi Selection", with a request button. | With Selection: the tag opens the creator card. |
| Selection only | The roster. After a selection, **Track this campaign** is shown **locked**, with a request button. | With Track: one click starts a campaign from the selection. |

## Journeys: what a person sees, every case

P is a person of company C who opens module M. The gate answers in this order.

| # | Situation | P sees | Notes |
|---|---|---|---|
| 1 | Not signed in | Sign-in, then back to the page they asked for | Then rows 2 to 9 apply. |
| 2 | C owns M, P's role is enough | The module | Viewer reads; editor changes; admin also manages people. |
| 3 | C owns M, **P's role is `none`** | **Locked page**: what M is, "Your account does not include it", **Request access** | Request goes to C's admin; if C has none, to HelloVoice. |
| 4 | **C does not own M** | **Locked page**: what M is, a sample, **Request this module** | Request goes to HelloVoice (the owner and the account KAM). No data of M is sent to the browser. |
| 5 | C owns M but HelloVoice switched it **off** | "Paused for your company. Your data is safe. Contact HelloVoice." | Off hides, never deletes. |
| 6 | A **limit** is reached (credits, campaigns, captures, spend) | The module works; the action that would spend is refused with the reason and **Request more** | Checked at the point of spend. |
| 7 | Subscription ended | Read-only with a banner for a grace period, then row 5 | Data kept. |
| 8 | A link to an object of **another company** | "Not found", identical to a link that never existed | Never confirms it exists. |
| 9 | A link to an object of **their own company** in a module they lack | The locked page of that module (row 3 or 4) | They already know it exists. |
| 10 | A public share link (client report token) | The report, read-only, while M is on for C | Off or ended: "Unavailable". No sign-in needed. |
| 11 | An API call (the app, the assistant) | `403` with `{code: locked | no_role | off | limit}` | Never a partial `200`. |
| 12 | The Helvi assistant | Offers only what P's modules and role allow; when asked for more, says so and offers **Request access** | |
| 13 | HelloVoice staff | Never gated. **View as client** shows exactly what that person would see, role included | |
| 14 | P's role is changed while they are in the module | Next request re-checks; a banner says access changed | The gate runs on every request. |
| 15 | P belongs to two companies | A company switcher; each has its own modules | Later phase. |

The module switcher shows all three marks. Owned modules open; the others show a lock and lead to row 3 or 4.

## Data

New: `users.company_code_id` (NULL = the person's own code; a colleague's row points at the company's code,
and the gate resolves the tenant as COALESCE(company_code_id, code_id), so every person keeps their own login);
`user_modules (user_id, code_id, module, role, changed_at, changed_by)`, primary key (user_id, module);
`module_requests (id, code_id, user_id, module, kind module|role|limit, status, note, detail, created_at,
decided_at, decided_by)` filed with `tenant_requests.file_request(...)` (the older `access_requests` is the
selection-access table and stays as it is); `creators.owner_code_id` (NULL = roster).

Today every portal user has a code of their own (23 users, no shared code), so a company of several people
starts as a single-person company and grows by invites that set `company_code_id`.
Kept: `tenant_modules` (company level), `tenant_settings` (limits and branding), History for every change.
Rules that do not move: off hides and never deletes; only HelloVoice owner and admin set entitlements;
a private creator is never visible outside its company; the roster total is never shown to clients.

## Order of work

1. **Gate and split (this session):** register `helvi-selection`, move its routes behind the gate, add
   `user_modules` and `access_requests`, the module switcher and the locked pages, private creators.
2. **Admin Tenants table (own session):** one table of every company with all its details, a page per
   company to edit every parameter, and the access-request inbox.
3. **Client dashboards (own session):** per module, the company's own inputs, outputs and controls, and
   the company admin's people-and-roles screen.

Design work follows the rule: requirements through brainstorming with Bido, execution through impeccable.
