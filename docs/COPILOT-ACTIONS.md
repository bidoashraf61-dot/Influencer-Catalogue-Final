# Helvy's hands — the copilot acts in the portal

Asked for on 2026-10-27: *"make the portal fully accessible to take any actions …
I want the chat bot to do everything"*. The copilot could already read everything
and write nine specific things; it can now **do** the portal's own actions.

## How it works

`admin/actions.py` is one bridge. A confirmed call goes back in through the
portal's own door on `127.0.0.1`, carrying the admin's session cookie, so the
handler that runs is the handler a click runs — same permission checks, same
validation, the same History entry, and the same sentence back. An action whose
rules change in the portal changes here for free.

```
admin types  →  Gemini picks list_actions, then do_action
             →  actions.check()      refuses an unknown action or field
             →  actions.describe()   one sentence on a Confirm card
             →  admin presses Confirm
             →  actions.run()        POST to the portal, as them
             →  the portal's own ?ok= / ?e= message comes back
```

## What keeps it safe

- **Nothing runs from the model.** Every call waits for Confirm, like the older
  write tools. The cookie comes from that Confirm request and is never stored.
- **A closed list.** Only `REGISTRY` entries can be called, each with the fields
  its own form submits. An unknown action, an unknown field or a missing required
  one is refused before anything is queued, so the model cannot invent a route.
- **No whole-page forms.** `/campaigns/save` replaces every field it is sent, so
  a partial submit would quietly blank the dates or the brief. It is deliberately
  not exposed; a campaign's own fields go through `update_campaign`, which merges.
- **Only the portal may declare success.** A redirect without `?ok=` is how these
  handlers refuse a bad id, and an expired session lands on the sign-in page.
  Neither is reported as done — the bridge says the portal did not confirm it.
- **The taint rule still applies.** After a tool that returns client-written text
  (`sql_query`, `client_overview`, `list_clients`, `list_selections`), no write may
  be queued in the same turn. The admin asks again in a fresh message. This is what
  stops text a client typed from steering an action.
- **Owners and admins only.** `do_action` sits in `ADMIN_WRITE`, which key account
  managers are already blocked from. The website chat (Helvi) gets the same two
  tools only when `Handler.chat_admin_email()` finds that the portal sign-in belongs
  to an active admin account with role owner or admin, and not a key account
  manager or someone viewing as a client. Everyone else sees no trace of them.

## Two chat bots, one bridge

- **Admin copilot** (`/admin/ai`): as before.
- **Website chat** (the catalogue's Helvi bubble): an owner or admin who signs in
  to the portal with their work email gets `list_actions` + `do_action`, and the
  prompt says they are staff. Confirm goes to `/api/chat/confirm`, which runs the
  action as their admin account. If they also have an admin session open it uses
  that; otherwise `Handler.loopback_admin_cookie()` mints a 5-minute session for the
  one call and deletes it. With two-step sign-in on and no admin session open it
  refuses and asks them to sign in to the admin once.
- Anything the portal asks a fresh sign-in for (Team, deleting a code, tiers) comes
  back as "confirm it is you first": open the admin, confirm, ask again.

## What it covers today

33 actions. Campaigns end to end, 13 actions: create a campaign, take it live / offline /
ended, pull in creators from its selection, delete it; add one post or paste many,
edit, hide, delete, group, and record what is still expected; edit, add and switch
tracking links; approve or reject a creator's screenshot numbers.

Added 2026-10-27: **client access codes** (issue with the passcode read back,
rename, limits, passcode, revoke, restore, archive, unarchive, delete), **selections**
(create empty, rename, delete), **team** (invite, role, remove/restore access,
sign out, resend invite, reset two-step) and **creator industry** (confirm / hide).
The code handlers now answer with `?ok=` / `?e=` like the rest, and the roster
review and selection delete refuse an id that does not exist.

## Adding more

Add a row to `REGISTRY` with the path, the fields that form submits, a one-line
description and a sentence template. No other code changes. The areas not yet
covered — analysis, evidence, alerts, settings, tenants, tiers, quotes, and
creator edits beyond industry (use `update_creator`; `/roster/save` is a whole-page
form and stays out) — are the same shape of work; `/campaigns/save`-style whole-page
forms need a prefill-merge first, or they stay out.

## Checking it

    python3 admin/tests/test_actions.py

35 checks over the guard rails and the read-back protocol. The last hop — Confirm
with a live admin session — can only be exercised by a signed-in admin.
