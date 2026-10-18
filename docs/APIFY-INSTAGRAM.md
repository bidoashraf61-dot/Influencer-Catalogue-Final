# Instagram post and reel numbers (Apify)

**One actor: `data-slayer/instagram-post-details`** (constant `INSTAGRAM_POST_ACTOR` in `admin/apify.py`, preset `post_ig`).
Input: `{"postUrls": [<post links>]}`. Decided 2026-10-18; use it for any Instagram post or reel test.

## Why this one
Instagram's app shows a combined "Views" number: Instagram plays plus the Facebook plays of a cross-posted reel.
The public Instagram counter that most scrapers read leaves the Facebook part out, so they come out far lower.
This actor returns the full metrics object (`play_count`, `ig_play_count`, `fb_play_count`, likes, comments, shares, saves).

Tested 2026-10-18 on three reels of one creator (app showed 1.1M / 5.8M / 4.6M views):

| Actor | Views for the 1.1M reel | Time | Cost |
|---|---|---|---|
| codenest/instagram-reels-scraper (old) | 208K | ~10 s | $0.0013 |
| apify/instagram-reel-scraper, apify/instagram-scraper | 209K | ~10 s | ~$0.001 to $0.008 |
| apidojo/instagram-scraper-api, hpix/ig-reels-scraper | 210K | 5 to 10 s | ~$0 to $0.0013 |
| instaprism/instagram-reels-scraper | 1.21M | 6 to 7 min | ~$0.11 per run |
| patient_discovery/instagram-reel-analytics-by-url | 1.23M | 31 s | $0.0063 per 3 reels (likes off on one old reel) |
| **data-slayer/instagram-post-details** | **1.24M** | **44 s** | **$0.004 per run** |

The app's own numbers for that reel: 1.1M views, 14.4K likes, 402 comments, 4,225 shares, 5,562 saves.
Stored by the job: 1,236,502 / 14,970 / 417 / 4,259 / 5,598.

## Rules
- The number reader (`post_numbers`) takes `play_count` (combined views), `like_count`, `comment_count`, `share_count`, `save_count`.
- Jobs for campaign posts are `kind: post_urls`, one run per platform per campaign, matched to posts by the id in the link.
- Not used for Instagram post numbers: the other actors in the table. They stay valid for profile numbers and analyses.
