# HELVi Connect app (PWA + push alerts)

Item 168 (2026-10-19). The portal installs as a phone app and sends push alerts.

## Pieces

| Where | What |
|---|---|
| `manifest.webmanifest`, `sw.js`, `offline.html` (site root) | Install metadata, service worker (offline page, push, taps), offline fallback |
| `assets/app/` | Lime app icons (any + maskable), status-bar badge, iPhone splash screens |
| `assets/js/app.js`, `assets/css/app.css` | Bottom bar on phones (<900px), install guides (Android Chrome prompt, iPhone Safari Share guide), soft alerts card, "Phone alerts" row in Account → Notifications, install/permission tracking |
| `admin/webpush.py` | Stdlib Web Push: VAPID (ES256) + RFC 8291 aes128gcm. Key in `admin/.vapid-key` (mode 600, never in git) |
| `admin/push.py` | Subscriptions, tracking tables, rules, milestones, sender loop (5 s), reporting |
| `admin/push_api.py` | `/api/push/*` for the app and the service worker |
| `admin/push_views.py` | Admin → App & alerts (Overview, Send a push, History, Automatic rules) — owners/admins only |

## How an alert travels

`inbox.emit` (the bell) and `notify.send` (team email) hand every event to `push`'s in-memory queue;
the loop groups it into a message, applies rules (master switch, per-rule switch, the person's
"Phone alerts" switch, quiet hours 23:00–08:00 Riyadh, max 3 automatic a day), creates one delivery per
phone, and sends. The service worker reports delivery (`/api/push/ack`) and taps (`/api/push/click`).

Milestones (every 10 min, live campaigns): views thresholds, goal steps (25/50/75/100 %), first post and
bundled new posts. A campaign seen for the first time is only recorded, so a deploy never bursts old milestones.

Manual pushes also land in the bell (kind `announce`) so people without the app still see them.

## Platforms

Android Chrome/Edge/Samsung and desktop browsers: push works in the browser and the installed app.
iPhone: push only from the Home Screen app on iOS 16.4+; Safari shows the Add to Home Screen guide.

## Tests

`admin/tests/test_webpush.py` (RFC 8291 vector, GCM vectors, OpenSSL cross-check) and
`admin/tests/test_push.py` (tracking, subscribe, bell → push, quiet hours, cap, manual, milestones, team, admin, roles).

## Setup prompts (item 169)

- **Desktop, once:** a welcome dialog with a personal QR (Account holders, first computer visit, never over another dialog). Then a quiet "HELVi on your phone" card on Account → Overview until a phone has the app with alerts on, and "Get the app on your phone" / "Install on this computer" (Chrome, Edge) / "Alerts on this computer" in the account menu.
- **The QR** (`admin/qr.py`, stdlib, checked against the qrcode package) points at `/admin/api/push/qr?h=<token>`: one use, 15 minutes, max 20 an hour per person, signs that phone in (same pass as email sign-in, counted against the device limit) and lands on `/account/?src=qr`.
- **Phones:** after a QR scan the Home Screen guide opens at once (iPhone: Safari Share steps; Android: Chrome's install, or the ⋮ → Add to Home screen steps). Always reachable from the account menu ("Add HELVi to Home Screen") and Account → Notifications.

## Staying current (item 175)

The installed app must run the build that is live, never an older one.

- **Pages** are `no-store` (nginx) and the worker never caches them: every launch, tap and reload fetches the current HTML.
- **Scripts and styles** are cached by URL. A `?v=` with 8 hex characters is served immutable for a year and the worker answers it from its own cache, so that stamp **must** be the file's content hash. `deploy/catalogue/stamp_assets.py` (run by `update.sh`) stamps every `src`/`href` to an `assets/js|css` file on every page (no list of files or pages to keep), the `?v=` URLs inside js files (connect.js → tour), then checks itself (`--check`). Hand-set stamps (`?v=t3`, `?v=c4`) are not cache-first in the worker.
- **The worker** gets `VERSION = "hca-<hash of scripts, styles, app icons, offline page, manifest, sw.js>"` at every publish, so a release is a new worker: it installs at once (`skipWaiting`), deletes the older caches and takes over the open app (`clients.claim`). It fills its cache past the browser's 30-day copy (`cache: "reload"` / `"no-cache"`) and never answers video byte-range requests.
- **An open app** sees new scripts/styles through `/api/push/version` (the "Update now" bar, installed app only) and the "HELVi has been updated" push (rule App updated, max one a day, after 10 min settle). A page-only change is picked up on the next launch, or when the app comes back after 6+ hours in the background (it reloads unless something is being typed).
- **Never copy a page or asset to the server by hand without stamping.** If you must hot-copy, run `python3 /home/ubuntu/influencer-catalogue-src/deploy/catalogue/stamp_assets.py /home/ubuntu/influencer-catalogue/site` afterwards. Check any time with `--check` (read-only).
