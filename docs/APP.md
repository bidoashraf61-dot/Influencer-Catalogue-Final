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

- **Desktop, once:** a welcome dialog with a personal QR (Account holders, first computer visit, never over the tour or another dialog). Then a quiet "HELVi on your phone" card on Account → Overview until a phone has the app with alerts on, the QR on the tour's finish card, and "Get the app on your phone" / "Install on this computer" (Chrome, Edge) / "Alerts on this computer" in the account menu.
- **The QR** (`admin/qr.py`, stdlib, checked against the qrcode package) points at `/admin/api/push/qr?h=<token>`: one use, 15 minutes, max 20 an hour per person, signs that phone in (same pass as email sign-in, counted against the device limit) and lands on `/account/?src=qr`.
- **Phones:** after a QR scan the Home Screen guide opens at once (iPhone: Safari Share steps; Android: Chrome's install, or the ⋮ → Add to Home screen steps). Always reachable from the account menu ("Add HELVi to Home Screen") and Account → Notifications.
