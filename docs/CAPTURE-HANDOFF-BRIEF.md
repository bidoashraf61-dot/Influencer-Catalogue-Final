# Capture hand-off brief — finding campaign posts and their analytics

**For:** a new Claude session that will run (and first set up) the daily
capture job for HelloVoice campaigns.
**Written:** 2026-10-06. **Live version:** `6109eb0` on
`influencer-catalogue.hellovoice.co.uk`.
**Companion docs:** `docs/CAPTURE-AGENT.md` (the scheduled task's prompt and
setup), `docs/ADMIN.md` §Content/Insights, `docs/CAMPAIGN-TRACKER-BRIEF.md`.

No secrets are in this file. The capture token lives only in `~/.hv_capture`
on the team Mac.

---

## 1. What the job is for

For every **live** campaign, find every post each booked creator published
inside the campaign dates, record it with its public numbers, re-read those
numbers every day, and read the insight screenshots creators upload. The
admin service never browses: **the session does the looking, the service
does the storing, scoring and reporting.**

The client report is built from what you send. Anything you miss, the
client never sees; anything wrong, the client sees wrong.

## 2. Ground rules (non-negotiable)

- Browse only with **dedicated company accounts** on Instagram, TikTok and
  Snapchat, in Chrome with the Claude extension. Never a personal account,
  never a client's.
- **Never** solve a CAPTCHA, log in for anyone, or bypass a login wall. If a
  platform shows a check, a wall or "try again later": stop that platform,
  record it as an error, carry on with the others.
- Go slowly: a few seconds between profiles, no rapid-fire scrolling.
- Read only what is **visible**. Never guess, never fill 0 for a hidden
  number — leave the field out.
- Never type the capture token anywhere but `~/.hv_capture`; never print it.
- The server (AWS, shared BlueHolding box) is out of scope for this job. You
  talk to it only through `tools/capture.py`.

## 3. The loop, each run (daily, e.g. 06:00 Riyadh)

1. `python3 tools/capture.py jobs` → JSON per campaign that is **Live and inside its dates** (from its first day until 7 days after its last, for late numbers): `campaign_id`,
   `name`, `platform` (null = every platform), `starts_at`/`ends_at`,
   `rules` (hashtags, mentions, keywords, required disclosure), `creators`
   (code, name, profile URLs — already filtered to the campaign's platform),
   `known_posts` (URLs already stored), and pending insight uploads.
2. For each creator × profile: open it, find **every** post/reel/video/short/
   story published between `starts_at` and `ends_at` (±1 day is accepted).
3. Re-read the numbers of **every URL in `known_posts`** — each run is that
   day's snapshot (one per post per day; a second run the same day replaces it).
4. Write `/tmp/hv_capture.json` and `python3 tools/capture.py push /tmp/hv_capture.json`.
   Fix and re-push anything refused for a fixable reason.
5. `python3 tools/capture.py shots /tmp/hv_shots` → read each insight
   screenshot → `python3 tools/capture.py insight <id> /tmp/hv_ins_<id>.json`.
6. `python3 tools/capture.py done --posts N --insights N [--error "…"]`, then
   a short summary: posts found per campaign, new vs re-read, refusals,
   anything blocked.

## 4. Per post — what to record

| Field | Required | Rules |
|---|---|---|
| `code` | yes | The creator's roster code from `jobs` (e.g. `HV-MC-108`) |
| `platform` | yes | One of `Instagram, TikTok, Snapchat, YouTube, X, Facebook, Threads` |
| `kind` | yes | One of `post, reel, story, video, short` (see §5) |
| `url` | yes | The post's own `https://` link — this is its identity. Same URL again = update |
| `posted_at` | yes | ISO date-time, e.g. `2026-10-12T19:04:00+03:00`. Outside the campaign dates ±1 day is refused |
| `caption` | yes | Full text. For a story: all visible text, @mentions, #tags, link/mention stickers. **The rules read this to decide if the post counts** |
| `likes` | if shown | Hidden likes → leave out (never 0) |
| `comments` | if shown | |
| `views` | video kinds | Reels, TikToks, YouTube, shorts. A story's view count is not public — leave out |
| `shares`, `saves` | if shown | Usually only visible on TikTok |
| `followers` | yes | The account's follower count **on that day** (drives ER and estimated reach) |
| `thumb` | optional | Image URL, if easy |

**Numbers exactly as shown, expanded:** `12.4K` → `12400`, `1.2M` → `1200000`,
`3,456` → `3456`. Integers only.

Batch file shape:

```json
[{"campaign_id": 3, "items": [
  {"code": "HV-MC-108", "platform": "Instagram", "kind": "reel",
   "url": "https://www.instagram.com/reel/XXXX/", "posted_at": "2026-10-12T19:04:00+03:00",
   "caption": "…#svr @svr_ksa #إعلان", "likes": 18400, "comments": 312,
   "views": 402000, "followers": 646000}
]}]
```

The server refuses: creator not in that campaign, unknown platform/kind,
non-`https` URL, date outside the campaign. It reports each refusal with the
reason.

## 5. Platform by platform — where posts hide

| Platform | Look in | `kind` | Notes |
|---|---|---|---|
| Instagram | Grid (posts), **Reels tab**, **Tagged tab** (collabs posted from the brand's account), **Stories** (ring on the avatar), Highlights (only if a story was missed and saved there) | post / reel / story | Collab posts appear on both accounts — record once, under the booked creator. Carousel = one `post`. Likes may be hidden |
| TikTok | Profile video grid, **Reposts**, pinned videos at the top (check their dates) | video | Shares/saves often visible. Photo-mode posts = `post` |
| Snapchat | Public profile: **Stories**, **Spotlight**, saved Stories | story / video | Stories vanish in 24h — **every run must check**. View counts usually not public |
| YouTube | Videos tab, **Shorts tab** | video / short | Views always public |
| X / Facebook / Threads | Profile timeline | post / video | Only if the creator is booked on it |

A story that expires before a run is lost unless the creator sends its
insight screenshot — so flag any creator whose story you could see the ring
for but could not open.

## 6. Does it count? (decided by the server, informed by you)

The campaign's rules (hashtags, @mentions, keywords) are matched against
the **caption** you send. Matching posts count toward the campaign; others go
to "All content" (still stored). The required disclosure (e.g. `#ad`,
`#إعلان`) is checked separately and flagged if missing. An admin can move a
post either way, and a later capture never undoes that. So: **send the
whole caption, including every #tag and @mention, and for stories every
sticker's text.**

## 7. Insight screenshots — the real numbers

Creators upload screenshots of their own insights (link on the Insights tab,
or an admin uploads on their behalf). From each image read only what is
visible:

`reach` (accounts reached), `impressions`, `views`, `likes`, `comments`,
`shares`, `saves`, `profile_visits`, `link_clicks`, `sticker_taps`.

Write e.g. `{"reach": 18400, "impressions": 25100, "link_clicks": 312}` and send it.
An admin compares it with the screenshot, picks the post and approves;
approved numbers replace the estimates in the client's report.

## 8. What the report does with your numbers (so you know what matters)

- **Engagement** = likes + comments.
- **ER** (feed posts) = engagement ÷ followers; **video ER** = engagement ÷ views;
  **view rate** = views ÷ followers; **story reach rate** = reach ÷ followers.
- **Reach**, until real insights are approved, is estimated: video = views;
  feed post = engagement × a factor, capped at followers; story = followers ×
  a story view rate. Impressions likewise. Factors are in Admin → Settings.
- Daily snapshots draw "How it grew"; tracking-link clicks (`/go/…`) are
  counted by the server itself.

→ The numbers that move the report most: **views, likes, comments,
followers, and the full caption.** Approved **reach/impressions** from
insights beat every estimate.

## 9. Before the first run — checklist

- [ ] Team Mac: Chrome + Claude extension, signed in to the **company**
      Instagram, TikTok and Snapchat accounts.
- [ ] Admin → Settings → Capture job → **Create token**; save it in
      `~/.hv_capture` (`HV_CAPTURE_URL=https://influencer-catalogue.hellovoice.co.uk/admin`,
      `HV_CAPTURE_TOKEN=…`), `chmod 600`.
- [ ] `python3 tools/capture.py jobs` lists at least one campaign.
- [ ] Each campaign is **Live**, with first/last day, rules (hashtags /
      mentions / keywords) and disclosure set, and every creator has the
      profile links for the platforms tracked.
- [ ] Scheduled task created in Claude with the prompt in
      `docs/CAPTURE-AGENT.md`; the Mac is awake and Chrome open at that time.

**State on 2026-10-06:** one campaign (id 1, 14 creators, all with profile
links, rules set, dates set) — but **still Draft**, so `jobs` returns nothing
for it yet. It appears once it is set Live and its first day has come. No capture token, no runs, no content, no insight uploads.

## 10. Hard cases — decide, don't guess

- **Post deleted or made private** after capture: record nothing new; note it
  in the run summary (the stored post stays with its last snapshot).
- **Creator posted from another account** (brand account, a second
  profile): add that profile to the creator on the roster first (admin), then
  it shows up in `jobs`.
- **Several posts in one Instagram carousel or a TikTok series**: one item
  per URL.
- **Story with a link sticker**: put the sticker's destination text in the
  caption; clicks come from `/go/` links or insights (`link_clicks`).
- **Numbers in Arabic numerals or "ألف/مليون"**: convert (١٢٫٤ ألف → 12400).
- **Profile not found / renamed**: report it; an admin fixes the link on the
  roster.
