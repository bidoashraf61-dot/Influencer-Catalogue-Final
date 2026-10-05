# Capture agent — the daily Claude job

Once every 24 hours, a scheduled Claude task on the team Mac opens each live
campaign creator's profile in Chrome, reads their new posts and the numbers on
them, and sends them to the admin. It also reads the insight screenshots
creators upload. The admin service never browses anything itself.

Nothing here solves CAPTCHAs, logs in on anyone's behalf or touches a client's
account. If a platform shows a login wall or a check, the run stops and says so.

## One-time setup (team Mac)

1. Chrome with the Claude extension, logged in to **dedicated company accounts**
   on Instagram, TikTok and Snapchat. Never a personal account, never a
   client's. Viewing stories with this account marks them seen — that is fine.
2. Admin → **Settings → Capture job → Create token**. Copy it once.
3. Create `~/.hv_capture`:

   ```
   HV_CAPTURE_URL=https://influencer-catalogue.hellovoice.co.uk/admin
   HV_CAPTURE_TOKEN=hvcap_…
   ```

   `chmod 600 ~/.hv_capture`. It is not in the repo and must never be.
4. Check: `python3 tools/capture.py jobs` prints the live campaigns.
5. Create the scheduled task in Claude (daily, e.g. 06:00 Riyadh) with the
   prompt below. The Mac must be awake and Chrome open at that time.

## The scheduled task's prompt

> Run the HelloVoice campaign capture. Work in
> `~/BlueHolding/Blue Admin/helv-catalogue-deploy`.
>
> 1. `python3 tools/capture.py jobs` — read the JSON. For each campaign, note
>    its dates, platform, rules and creators with their profile URLs, and the
>    posts already known (`known_posts`).
> 2. For each creator profile, in Chrome (use the Claude in Chrome tools):
>    - Open the profile. Read the follower count.
>    - Look at every post, reel, video and **story** published inside the
>      campaign dates (stories only exist for 24h — check them every run).
>    - For each one record: `url` (the post's own link; for a story use the
>      story URL shown in the address bar), `kind` (post | reel | story |
>      video | short), `posted_at` (ISO date-time), `caption` (for a story:
>      the text, @mentions and #tags visible on it, including link and
>      mention stickers), `likes`, `comments`, `views` (reels/videos/TikToks;
>      a story's view count is not public — leave it out), `shares`/`saves`
>      only if shown, `followers`, `thumb` (image URL if easy, else omit).
>    - Numbers exactly as shown, expanded: 12.4K → 12400, 1.2M → 1200000.
>      Hidden likes → leave `likes` out (never 0).
>    - Re-read the numbers of every post in `known_posts` too — each run is a
>      new daily snapshot.
>    - Go slowly: a few seconds between profiles. If a login wall, CAPTCHA or
>      "try again later" appears, stop that platform, note it as an error,
>      and carry on with the others. Never solve a CAPTCHA.
> 3. Write `/tmp/hv_capture.json` as
>    `[{"campaign_id": <id>, "items": [{"code", "platform", "kind", "url",
>    "posted_at", "caption", "likes", "comments", "views", "followers"}, …]}, …]`
>    and run `python3 tools/capture.py push /tmp/hv_capture.json`. Fix and
>    re-push anything refused for a reason you can fix.
> 4. `python3 tools/capture.py shots /tmp/hv_shots` — open each image and
>    read: reach (accounts reached), impressions, views, likes, comments,
>    shares, saves, profile_visits, link_clicks, sticker_taps. Only numbers you
>    can actually see. For each upload write `/tmp/hv_ins_<id>.json` like
>    `{"reach": 18400, "impressions": 25100}` and run
>    `python3 tools/capture.py insight <id> /tmp/hv_ins_<id>.json`.
>    (The admin approves them before any client sees them.)
> 5. `python3 tools/capture.py done --posts <n> --insights <n>` adding
>    `--error "<text>"` for each problem. Then summarise in one short message.

## What the server checks

- Token required on every call (`Authorization: Bearer …`), stored hashed;
  replacing it in Settings cuts off the old one at once.
- Only creators in that campaign, known platforms and kinds, `https://` links,
  and dates inside the campaign (±1 day) are accepted; the rest come back as
  `refused` with a reason.
- A post is keyed by its URL: sending it again updates it. One snapshot per
  post per day — a second run the same day replaces the first.
- Whether a post counts (`campaign`) or not (`All content`) is decided by the
  campaign's rules on its caption; an admin's later move is never undone.
- Each run appears under Settings → Capture job, with its errors.
