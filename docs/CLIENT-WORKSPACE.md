# The client workspace: what a company sees and does in each module

Built 28 October 2026 on the model in `docs/SAAS-MODEL.md`. Page: `/workspace/` (`workspace/index.html`,
`assets/js/workspace.js`, `assets/css/workspace.css`). Server: `admin/workspace.py` (company, people, roles,
settings, the page's payload) and `admin/tenant_api.py` (the company's own writes and reads per module).

Decided with Bido by multiple choice: the same five tabs in every module; the Overview leads with a setup
checklist, then usage meters, then the latest outputs; HelloVoice sets the caps and the company's admin
controls everything inside them.

## The page

| Part | What it is |
|---|---|
| Module switcher | Selection, Track, Intelligence. Open, or a dashed card with a lock: *Not on your account* (company does not own it), *Not in your role*, *Paused* |
| Locked page | What the module is, and **Request this module** (to HelloVoice) or **Request access** (to the company's admin). Paused: "your data is safe" |
| Overview | Setup checklist (hidden once done), meters (seats, the module's own counts, AI credits; Intelligence also collections today and spend this month), latest outputs. A meter at 80% offers **Request more** |
| Work | The module's inputs (below) |
| Results | The module's outputs (below) |
| Team | Admins only: people, a role per module, seats used, role requests to approve or decline, invite |
| Settings | Limits HelloVoice set (read-only, **Request more**); admin settings below |

## Each module, standalone

| Module | Work (inputs) | Results (outputs) | When the company does not own the other module |
|---|---|---|---|
| **Track** | Create, edit, go live, end its own campaigns; add creators by profile link (private `PV-` creators, `creators_private.py`); add posts | Its campaigns, each opening the campaign dashboard | Creators come only by link; no roster |
| **Intelligence** | Name competitors (handles per platform), **Collect now** | Evidence by creator: competitors worked with, posts, best views, followers | A roster match is a locked tag *Available through Helvi Selection* (a request); the roster code is not sent |
| **Selection** | The roster and selection pages | Its selections | **Track this campaign** is locked (a request). With Track at manage it starts a campaign with the selection's creators |

Writes need the company at `manage` (set by HelloVoice on the Tenants page) **and** the person at editor or
admin. At `view` the Work tab says HelloVoice runs it for them and offers **Ask to manage your own**.

## Settings a company admin controls

| Setting | Effect |
|---|---|
| Role given when you approve a request | viewer or editor |
| Weekly campaign update (Track) | Off skips the weekly bell/phone note (`weekly.py`); the week is still recorded, so no backlog |
| What your reports show (Track) | Clicks, earned media value, what people said, every post. Off hides it on every report of the company (`metrics.visibility`); on leaves each campaign's own switch in charge |
| Name and colour on reports | The report names the client by it; the dashboard title is underlined in the colour (hex only) |

## People and roles

- A company is a `codes` row. Its colleagues are `users` rows with `company_code_id`; the account holder is
  admin of every module the company has.
- `user_modules` holds one row per invited person per module (none, viewer, editor, admin).
- Effective access: module off is nothing; at `view` an editor reads only; an admin can always manage the
  company's people.
- Requests go to `module_requests` (kinds role, module, limit). Role requests are answered in the Team tab;
  the others reach HelloVoice in the Tenants inbox.
- Inviting is open to every company (`workspace_invites = "all"`, set 28 October 2026 after the attribution
  audit, f0813eb). A list of company code ids in that setting closes it to all others again.

## Endpoints

| Route | Who |
|---|---|
| `GET /api/workspace?m=<module>` | Signed-in person: the whole page |
| `POST /api/workspace/{invite,role,remove,request,decide,pref}` | Judged on the person holding the pass |
| `GET /api/my/campaigns`, `POST /api/my/campaign` (create, edit, live, end, add_creators, remove_creator) | Track at manage, editor+ |
| `GET /api/my/competitors`, `POST /api/my/competitor`, `POST /api/my/competitor/collect` | Intelligence at manage, editor+ |
| `GET /api/my/evidence` | Intelligence on, viewer+ |

HelloVoice staff are never a tenant: with an admin session the `/api/my/*` routes answer "sign in".

## Open

- Private creators have no follower count or photo yet (profile jobs read roster creators only).
- Going live starts paid daily collection; the only brake is the campaigns cap.
- Test company: code 55, `qa.owner@helvi-qa.com` and `qa.member@example.com`, Track and Intelligence at manage.
