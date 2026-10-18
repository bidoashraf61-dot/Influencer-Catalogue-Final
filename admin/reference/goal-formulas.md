# Campaign Goals — Formulas and Benchmarks

One reference for every goal formula and every benchmark we hold. Source of the rates: the portal's benchmark library (`admin/plans.py`, `BENCHMARKS-AND-ROI.md`). Ranges are written **[safe – expected]** and sit at the low end of published 2025 reports (HypeAuditor, Favikon, Emplicit, Influencer Marketing Hub, Kolsquare MENA), so a target built on them is one we can beat. They are planning guides, not verified per-figure citations. Last updated 2026-10-18 (consolidated: guidance, Facebook research, multi-platform calculation, decisions).

## 0. Guidance — how to use this file

**This file is the single reference for every goal, benchmark and ROI calculation.** Any report, dashboard, planner screen, quote or feature that computes or shows a goal must follow it. If code and this file disagree, decide which is right, fix one, and log the change in the decision log below.

**Rules**
1. **Targets come from formulas, never typed by hand:** §1 for views, engagements and clicks; §2 for value floor and ROI; §14 for campaigns on several platforms.
2. **Rates come from §4** (Instagram, TikTok, Snapchat, YouTube) and **§13** (Facebook, provisional). They are planning assumptions set at the low end of published reports. Label them as guides wherever they are shown.
3. **Safe = what we commit to, expected = what we aim for.** Pass/fail uses safe; "beaten" uses expected.
4. **Reach is not a goal and is never shown to clients** (owner decision, 2026-10-18). Do not add it back to targets, KPIs, gauges or reports.
5. **Clicks are a goal only when each creator has a tracked link.** No tracking = the clicks weight is dropped and the others scale to 100% (§10).
6. **Client-safe output:** never show the budget, the value floor or cost ratios (CPM, CPE, CPC) to a client. The ranges, targets and progress are fine.
7. **Achieved counts only on goal platforms:** the numbers measured against the targets include only the platforms the plan sets goals on; add-on platforms are tracked and shown but not counted towards the targets.
8. **A platform carries goals only when we hold its rates (§4/§13) and the creators' followers on it.** Platforms without goals are tracked as add-ons. Facebook is an add-on until §13's values are approved and added to the library.
8. **Followers per platform per creator** are needed for every platform with goals. Every post must carry its follower count, otherwise its view rate cannot be computed and the benchmark gauge shows "Typical".
9. **Stories are not tracked** unless a campaign says so; only Snapchat has Story rates.
10. **Weights (§10) rank creators and set headline KPIs; they never set target numbers.** Achievement is scored with §11.
0. **The dashboard is one template for every campaign.** The Jamjoom campaign's dashboard (structure, sections, features, buttons) is the default for any campaign, so every edit to the campaign dashboard is a **global** change in shared code, never campaign-specific. No per-campaign flags, ids or hard-coded values; every section reads from the report payload and must work for any campaign shape (one or many platforms, no tracking, unpublished creators, no targets). Campaign-specific data (targets, dates, creators, visibility) lives in the campaign record, not in code.
11. **Publishing plan ("should be today"):** each creator's videos are spread over the Publishing step, first video due on the first publishing day, last on the last day. A creator whose video date is not known carries a placeholder next-video date (the last publishing day) until the real date is known, and then it is replaced.
12. **Deploys must go through `origin/main`.** The site's `update.sh` resets the server's source repo to `origin/main` and republishes the static files (dashboard JS, CSS, pages), so a hand-copied static file is overwritten the next time anyone updates the site. Admin `.py` files are not touched by it. Any change that matters must be in `origin/main`, otherwise treat it as temporary.

**Conventions used on Jamjoom Wave 1** (confirm before reusing)
- The saved client target is the **safe estimate**. The planner's default "target to agree" is the lower of the value floor and the safe estimate; the floor is kept internally.
- Each video counts on every platform where the doctor has an account, at their follower count there (§14).

**Status of each part**

| Part | Status | Where |
|---|---|---|
| Views, engagements, engagement rate formulas | In use | Planner, Jamjoom targets |
| Link clicks | Defined; off for Jamjoom (no tracking) | Planner |
| Multi-platform calculation and per-platform estimates (`by_platform`) | **Deployed 2026-10-18** | Planner, plan data |
| Reach removed from every dashboard | **Deployed 2026-10-18** | Dashboard, targets, KPIs |
| Weights by campaign type and combinations | In code (blend); table in §10 | Dashboard, creator score |
| Achievement formulas and weighted campaign score | Defined here; **the weighted score is not in code yet** | — |
| Rates: Instagram, TikTok, Snapchat, YouTube | In the planner library | `admin/plans.py` |
| Rates: Facebook | Provisional values in §13.4, **not in the library** | — |
| Goals tab redesign (merged targets, per-creator benchmarks, forecast, platform split with bonus platforms) | **Deployed 2026-10-18** (spec: `Goals Tab - Page Spec.md`) | Dashboard Goals tab |
| Publishing-plan due rule | **Deployed** (in the merged code) | `metrics.py` |

**Still to gather**
- Client budget confirmation per campaign (Jamjoom: SAR 33,000 is in the saved plan).
- Real per-creator view rates from their recent posts, to replace library rates where available.
- Facebook influencer view rate, engagement on views, click rate, creator cost: see §13.6 (best next source: the MMA MENA guide, or the doctors' own Page Insights).
- Real publish dates for the four Jamjoom doctors not yet live (placeholder 31 Oct until sent).
- Fake-follower limit and minimum engagement for the Jamjoom brief.

**Decision log**

| Date | Decision |
|---|---|
| 2026-10-13 | Budget removed from the client brief form; Conversion goal merged into Traffic (owner-approved) |
| 2026-10-18 | Reach removed from goals and every client dashboard |
| 2026-10-18 | Jamjoom goal mix = Awareness + Traffic; no tracking, so 69.2% Views / 30.8% Engagements |
| 2026-10-18 | Jamjoom goals on Instagram + TikTok only; Snapchat, Facebook, YouTube are add-ons |
| 2026-10-18 | Jamjoom targets saved at the safe estimate: 1,082,000 views, 14,200 engagements, 1.31% |
| 2026-10-18 | First video due on the first publishing day (publishing-plan rule) |
| 2026-10-18 | Jamjoom campaign start kept at 17 Oct 00:00 Riyadh |
| 2026-10-18 | The Jamjoom dashboard is the default template for all campaigns; dashboard edits are global, not campaign-specific |
| 2026-10-18 | Deployed branch `merged/goals-tab-on-live` (8 files: admin db, matcher, metrics, plans, server, views; dashboard.js, dashboard.css; version tag `goalstab1018`). It was built on `baseline/live-2026-10-18`, a git snapshot of the live server code, so git now matches live. Backups: `/home/ubuntu/deploy-backup-goalstab-2026-10-17-2328/` |
| 2026-10-18 | A teammate's site update (23:43) republished `origin/main`'s older static files and reverted the new Goals tab on the live page. Restored at 23:47 with the design polish (info marks, section headlines, pace chart fixes) merged with a live-only audience-card change. Backups `/home/ubuntu/deploy-backup-goalstab2-2026-10-17-2347/`. Pull request branch `pr/goals-tab-on-main` (2 commits on top of `origin/main` 2275c05, not pushed) makes it durable |
| 2026-10-18 | Achieved numbers count towards targets only on the platforms the plan sets goals on (add-on platforms are tracked, not counted). Live on the server (`goal_platforms` in `metrics.py`); campaigns whose plan names no platform are unchanged |
| 2026-10-18 | Reach hidden for every campaign on the live server (visibility forced off); `Views & reach` labels renamed `Views` |

**Related files** (same folder): `Wave 1 - Campaign Goals Calculations.md` (Jamjoom working), `Goals Tab - Page Spec.md` (dashboard tab design), `LOCKED BRIEF - Jamjoom Wave 1.md` (client brief).

## 1. Goal formulas

Each is worked per creator, then added up. `posts` = videos delivered by that creator on that platform.

| Goal | Formula | Notes |
|---|---|---|
| Views | followers × view rate (by tier, safe/expected) × posts | Use the creator's follower count on the posting platform |
| Engagements | views × engagement rate (by tier) × industry factor | Likes + comments + shares + saves. Shares and saves are private; they come only from creator insights |
| Engagement rate | engagements ÷ views × 100 | Reported as % of views |
| Link clicks | views × click-through rate | Only when each creator has a tracked link. Without tracking the goal is dropped |
| Reach (reference only) | views × unique-viewer share | **Removed from our goals.** The share is an unverified assumption (see §4); real reach needs creator Insights screenshots |

**Safe** = low rate of each range (what we commit to). **Expected** = high rate (what we aim for).

## 2. Value floor, ROI and the target

| Step | Formula |
|---|---|
| Value floor, views | budget ÷ CPM ceiling (acceptable) × 1000 |
| Value floor, engagements | budget ÷ CPE ceiling (acceptable) |
| Value floor, clicks | budget ÷ CPC ceiling (acceptable) |
| Fair-value budget from views | views ÷ 1000 × CPM ceiling (acceptable = most we can fairly charge, good = strong value) |
| Cost per result | CPM = budget ÷ views × 1000; CPE = budget ÷ engagements; CPC = budget ÷ clicks |
| Value rating | cost ≤ good ceiling = strong value; ≤ acceptable = fair value; above = poor value |
| **Target to agree** | the **lower** of the value floor and the safe estimate. We commit to it and beat it |

If the safe estimate is below the value floor, the plan needs more or better-value creators, or a lower fee.

## 3. Measurements by campaign type

| Campaign type | Headline measurements | Score weights (views / engagement / clicks) | Needs |
|---|---|---|---|
| Awareness | Views | 70 / 20 / 10 | Public view counts |
| Engagement (UGC, reviews) | Engagements, engagement rate | 20 / 70 / 10 | Likes visible, or insights |
| Traffic / sales | Link clicks, views | 20 / 20 / 60 | A tracked link per creator |
| Balanced | Views, engagements, engagement rate | 45 / 35 / 20 | Clicks count only with tracked links |

No tracked links = the clicks weight is dropped and the other parts scale up to 100. Creator score (0–100) rewards each creator's delivered results as a share of the best creator's result; it is not compared with followers or outside benchmarks.

## 4. Benchmarks per platform and creator tier [safe – expected]

### Instagram

Reels. Feed photos reach about half a reel's audience; stories 4–8% of followers.

| Creator size | View rate (% of followers per video) | Engagement rate (% of views) |
|---|--:|--:|
| Nano (<10K) | 12–25% | 3.0–5.5% |
| Micro (10–100K) | 10–22% | 2.5–4.5% |
| Mid (100–500K) | 8–18% | 2.0–3.5% |
| Macro (500K–1M) | 5–12% | 1.5–2.8% |
| Mega (1M+) | 3–8% | 1.0–2.0% |

| Factor | Safe / Acceptable | Expected / Good |
|---|--:|--:|
| Link click-through (% of views) | 0.3% | 0.8% |
| CPM ceiling (SAR) | 70 | 40 |
| CPE ceiling (SAR) | 8.0 | 4.0 |
| CPC ceiling (SAR) | 15 | 8 |
| Unique viewers ÷ views (reference, reach removed) | 0.4 | |

### TikTok

Views swing more than on Instagram — one post can travel far beyond followers.

| Creator size | View rate (% of followers per video) | Engagement rate (% of views) |
|---|--:|--:|
| Nano (<10K) | 20–45% | 4.0–7.5% |
| Micro (10–100K) | 15–35% | 3.5–6.0% |
| Mid (100–500K) | 10–25% | 3.0–5.0% |
| Macro (500K–1M) | 7–18% | 2.5–4.5% |
| Mega (1M+) | 5–12% | 2.0–3.5% |

| Factor | Safe / Acceptable | Expected / Good |
|---|--:|--:|
| Link click-through (% of views) | 0.2% | 0.6% |
| CPM ceiling (SAR) | 50 | 25 |
| CPE ceiling (SAR) | 6.0 | 3.0 |
| CPC ceiling (SAR) | 12 | 6 |
| Unique viewers ÷ views (reference, reach removed) | 0.8 | |

### Snapchat

Story views. Snapchat shows no public likes, so judge it on views and swipe-ups.

| Creator size | View rate (% of followers per video) | Engagement rate (% of views) |
|---|--:|--:|
| Nano (<10K) | 8–15% | 0.5–1.2% |
| Micro (10–100K) | 7–13% | 0.5–1.0% |
| Mid (100–500K) | 6–11% | 0.4–0.9% |
| Macro (500K–1M) | 5–9% | 0.3–0.8% |
| Mega (1M+) | 4–7% | 0.3–0.6% |

| Factor | Safe / Acceptable | Expected / Good |
|---|--:|--:|
| Link click-through (% of views) | 0.4% | 1.0% |
| CPM ceiling (SAR) | 50 | 30 |
| CPE ceiling (SAR) | 12.0 | 6.0 |
| CPC ceiling (SAR) | 12 | 6 |
| Unique viewers ÷ views (reference, reach removed) | 0.95 | |

### YouTube

Long videos and Shorts. Views keep coming for weeks; judge at 30 days.

| Creator size | View rate (% of followers per video) | Engagement rate (% of views) |
|---|--:|--:|
| Nano (<10K) | 6–15% | 2.0–4.0% |
| Micro (10–100K) | 5–12% | 1.8–3.5% |
| Mid (100–500K) | 4–10% | 1.5–3.0% |
| Macro (500K–1M) | 3–8% | 1.2–2.5% |
| Mega (1M+) | 2–6% | 1.0–2.0% |

| Factor | Safe / Acceptable | Expected / Good |
|---|--:|--:|
| Link click-through (% of views) | 0.3% | 0.9% |
| CPM ceiling (SAR) | 60 | 35 |
| CPE ceiling (SAR) | 8.0 | 4.0 |
| CPC ceiling (SAR) | 15 | 8 |
| Unique viewers ÷ views (reference, reach removed) | 0.85 | |

### Facebook (add-on, provisional)

Not in the planner library. No published influencer-tier Facebook benchmarks exist; the values in **§13.3 / §13.4** are low-confidence planning estimates with safe margins (view rate 0.05–4% of followers by tier, engagement 2–3.5% of views, click rate 0.2–0.5%, CPM SAR 55 / 30, CPE 3.0 / 1.5, CPC 8 / 4). At safe rates Facebook adds almost nothing, which is why it stays an add-on with no goals. Do not add it to the library until the values are approved.

## 5. Industry factor (engagement only)

| Industry | Factor |
|---|--:|
| Pharma / OTC / healthcare | 0.8 |
| Baby & mother care | 1.0 |
| Beauty & skincare | 1.0 |
| FMCG / food & drink | 1.05 |
| Retail / pharmacy / e-commerce | 0.95 |
| Tech & telecom | 0.85 |
| Automotive | 0.9 |
| Other | 1.0 |

Jamjoom is pharma / OTC (0.8). Baby & mother content would use 1.0 (decision pending for Omega and Prolife Baby).

## 6. Our own actuals (HelloVoice)

From SEMAK, 18 Instagram reels, as of 2026-10-06: median view rate **13.1%** of followers, median engagement **1.74%** of views, CPM **SAR 30**. These show the safe range is beatable; replace library rates with real per-creator numbers when available.

## 7. Cross-checks (YouTube research, 2026-10-18)

Engagement by channel size: ~5.4% (nano) to ~2.8% (mega) (Upfluence 2024); 4.5% to 1.5% (Elev8or 2026); flat 3.3–3.7% (OverseerOS, 67 channels). Views ÷ subscribers: median 11.9% (OverseerOS); 3.77% (1–10K) to 2.56% (1M+) (CreatorDB). The library YouTube ranges sit at or below these.

## 8. Data rules

- Reach on reels is estimated; Instagram shows plays, not unique people. Our first 5 reels with real insights showed 22% overall (20–22% on big creators, 59–79% on small).
- Hidden likes: engagement for that post counts comments only and the post is left out of rates.
- Stories are not tracked in Jamjoom Wave 1; the library has Story rates for Snapchat only.
- Tiers: Nano <10K · Micro 10–100K · Mid 100–500K · Macro 500K–1M · Mega 1M+.
- Every post needs its follower count at capture, otherwise the view rate and the benchmark gauge cannot be computed.
- Platforms without goals (add-ons) are tracked but never feed the goals or the gauges.
- Reach is not collected as a goal and not shown to clients.

## 9. Worked example

Jamjoom Wave 1 (5 doctors, 11 videos, Instagram + TikTok with each doctor's followers per platform, pharma, no tracking, budget SAR 33,000): safe 1,082,000 views and 14,200 engagements (1.31%); expected 2,766,000 views and 66,600 engagements (2.41%). Saved as the client targets (safe). At SAR 33,000: CPM SAR 30.5 and CPE SAR 2.33 at the safe estimate, inside the blended good ceilings (35.5 / 3.5). Full working: `Wave 1 - Campaign Goals Calculations.md`.

## 10. Campaign type vs goal mix (score weights)

Pick Awareness, Engagement and/or Traffic. With several picked, the weights are the average of the chosen types' rows. Reach and engagement rate carry 0%.

| Campaign type | Views | Engagements | Link clicks |
|---|--:|--:|--:|
| Awareness | 70% | 20% | 10% |
| Engagement | 20% | 70% | 10% |
| Traffic | 20% | 20% | 60% |
| Awareness + Engagement | 45% | 45% | 10% |
| Awareness + Traffic | 45% | 20% | 35% |
| Engagement + Traffic | 20% | 45% | 35% |
| All three | 36.7% | 36.7% | 26.7% |

**No tracked links:** the clicks weight is dropped and the others scale up to 100%.

| Campaign type | Views | Engagements |
|---|--:|--:|
| Awareness | 77.8% | 22.2% |
| Engagement | 22.2% | 77.8% |
| Traffic | 50% | 50% |
| Awareness + Engagement | 50% | 50% |
| Awareness + Traffic | 69.2% | 30.8% |
| Engagement + Traffic | 30.8% | 69.2% |
| All three | 50% | 50% |

Note: the admin-only "Balanced" template is 45 / 35 / 20, which differs from the average of all three (36.7 / 36.7 / 26.7). Weights rank creators; the targets themselves come from the rates in §4.

## 11. Achievement formulas (from the achieved numbers)

| Target | Target (before) | Achieved rate (after) | Achievement % |
|---|---|---|---|
| Views | followers × view rate × posts | actual views ÷ followers | actual views ÷ target views × 100 |
| Engagements | views × engagement rate × industry factor | actual engagements ÷ actual views | actual engagements ÷ target engagements × 100 |
| Link clicks | views × click rate | actual clicks ÷ actual views | actual clicks ÷ target clicks × 100 |

- Each goal's achievement is capped at 100% for the score. At or above the safe target = met; at or above expected = beaten; below safe = missed.
- **Campaign score (proposed, not yet in the code):** Σ (weight × capped achievement) over the goals tracked.
- The portal's progress bar already caps each target at its goal and reads 100% only when all targets are met.
- **Example, Jamjoom Wave 1** (Awareness + Traffic, no tracking → 69.2% Views, 30.8% Engagements): safe views target 837,510, actual 1,200,000 → 143%, counts as 100%. Safe engagements target 8,250, actual 6,000 → 72.7%. Score = 0.692 × 100 + 0.308 × 72.7 = **91.6%**.

## 12. Click-rate references (searched 2026-10-18)

Vendor and paid-ad figures only; no creator-specific dataset exists. Our safe values sit at or below all of them.

| Platform | Published (clicks ÷ views) | Ours (safe – expected) | Source |
|---|---|---|---|
| Instagram | 0.22–0.88% general; 1.08% average; Story link stickers 0.5–3% | 0.3 – 0.8% | Scrumball, InfluencerFee |
| TikTok | 0.49–0.73% link CTR (ads); 0.5–1.5% guide; Spark Ads 3%+ | 0.2 – 0.6% | Influee, Billo |
| Snapchat | Swipe-up 0.35–1.5% (ads) | 0.4 – 1.0% | BeProfit |
| YouTube | Dedicated video 1–5%; integrated 0.5–2.5% | 0.3 – 0.9% | InfluencerFee |
| Facebook | Organic link posts 0.3–0.4% of reach or impressions in 2026 roundups; 2.2% (<1K followers) to 0.8% (500K+) in a 2021 analysis; ad link CTR ~1.7–2.5% (context only) | 0.2 – 0.5% (§13, low confidence) | Fan Page Karma, Benchmarketing, Triple Whale |

Suggested (not applied to the planner library): lower the Snapchat safe rate from 0.4% to 0.35% to match the published floor. Caveats: Reels have no clickable link, Story stickers click far more than Reels, and some sources divide by impressions instead of views. SEMAK tracked links are the best real check.

## 13. Facebook research (deep search, round 2, 2026-10-18)

Facebook has **no published influencer-tier benchmarks** in any form we can cite. What exists is brand-page data from Socialinsider (the only dataset with views by size band), vendor-blog restatements, and paid-ad costs. Denominators differ across sources and are stated below. Facebook stays an add-on with **no goals** and is **not in the planner library**. The values in the second table are planning values with safe margins, **not applied to code**.

### 13.1 Sources and what they give

| Measure | Figure | Denominator / basis | Source (type) |
|---|---|---|---|
| Reels average views per post, by page size | 1–5K: 264 · 5–10K: 480 · 10–50K: 1,000 · 50–100K: 2,500 · 100K–1M: 6,500 | Views per post. 111K videos, brand pages, Jan–Jun 2026, all platforms pooled (no Facebook-only n) | [Socialinsider video statistics](https://www.socialinsider.io/social-media-benchmarks/social-media-video-statistics) (vendor dataset) |
| Reels average views per post, same size bands | 10 · 50 · 100 · 200 · 620 | Views per post. 25M posts, 130,683 pages, 2024–25 (page says its "2026" values are 2025 data; methodology text has typos) | [Socialinsider Facebook benchmarks](https://www.socialinsider.io/social-media-benchmarks/facebook) (vendor dataset) |
| Reels engagement, by size | 1–5K 0.30% · 5–10K 0.25% · 10–50K 0.20% · 50–100K 0.18% · 100K–1M 0.15% | **% of followers** (reactions+comments+shares ÷ followers) | Socialinsider video statistics (as above) |
| Reels engagement, overall | 0.13% (2024), 0.18% (2025); all formats 0.15% | % of followers | Socialinsider Facebook benchmarks |
| Organic reach per post | ~1.25% of followers (872K posts); small pages ~4.35%, large ~0.50% | Reach ÷ followers | [Webtonic](https://www.webtonic.io/blog/social-media-reach-statistics) citing Socialinsider (vendor blog) |
| Facebook Reels reach | ~0.55% | Reach ÷ followers; one vendor, method unverified | [Edgar](https://meetedgar.com/blog/social-media-organic-reach-benchmarks) |
| Engagement by tier (blended) | <1K 0.50–1.20% · 1–10K 0.30–0.80% · 10–100K 0.15–0.45% · 100K–1M 0.08–0.20% · 1M+ 0.04–0.12% | Mostly % of followers; no per-cell source, tier cut-offs differ from ours | [PostEverywhere](https://posteverywhere.ai/blog/social-media-engagement-rate-benchmarks) (blog restating Socialinsider/Dash Social; unverified) |
| Engagement, video, impressions basis | Video median 4.84% | % of impressions, not comparable to followers | PostEverywhere citing Buffer |
| Influencer engagement tiers | nano 2.25% falling to mega 0.17%; Rival IQ influencer figure 0.164% | Unclear / followers; secondary restatements | [Big Eye Agency](https://www.bigeyeagency.com/insights/influencer-engagement-metrics-guide), [Adrevival](https://www.adrevival.io/blog/what-is-good-engagement-rate-on-facebook) (blogs, not verified at source) |
| Organic link CTR | 2021 analysis, ~96K profiles: <1K followers 2.2%, 500K+ 0.8%; 2026 roundups: 0.4% average, 1.21% average, 0.3–0.7% of impressions for link posts | Link clicks ÷ reach or impressions (varies) | [Fan Page Karma 2021](https://blog.fanpagekarma.com/2021/07/22/click-through-rates-facebook/) (read via search summary only; page certificate expired), [Benchmarketing](https://www.benchmarketing.org/benchmarks/organic-social) and [Linkdrip](https://www.linkdrip.com/blog/what-good-click-performance-looks-like-in-2026-benchmarks-for-ctr-time-to-click-and-funnel-drop-off) (search summaries only; pages not read) |
| Facebook link clicks, ads | Link-click CTR ~1.7%; global ad CTR 2.2–2.5%; Saudi 1.65% | Paid ads, context only | [Focus Digital](https://focus-digital.co/facebook-ads-ctr-benchmarks-2026-data/), [Triple Whale](https://www.triplewhale.com/blog/facebook-ads-benchmarks), [StateGlobe](https://data.stateglobe.com/saudi-arabia/facebook-ads-cost-statistics) |
| Saudi ad CPM | USD 4–15 (SAR 15–56); SAR 15–60 | Paid ads | [Lebesgue](https://lebesgue.io/facebook-ads/facebook-cpm-by-country), [BIMO](https://www.bimogroup.co/blog/meta-ads-benchmarks-gulf), [Altasweeqi](https://altasweeqi.org/facebook-ads-pricing-saudi-arabia/) |
| Saudi ad CPC | SAR 0.4–4; SAR 1.5–3; USD 0.45 (SAR 1.7); USD 2.30 (SAR 8.6) | Paid ads; sources disagree several-fold | [Altasweeqi](https://altasweeqi.org/facebook-ads-pricing-saudi-arabia/), [Local City Solutions](https://localcitysolutions.com/facebook-marketing-cost-in-saudi-arabia-2025/), [StateGlobe](https://data.stateglobe.com/saudi-arabia/facebook-ads-cost-statistics), [Groturn](https://www.groturn.com/facebook-ads-cost-saudi-arabia/) (agency blogs) |
| Cost per engagement | USD 0.01–0.05 (SAR 0.04–0.18) up to 0.25; Arabic-language blogs, region not Saudi-specific | Paid engagement ads | [Trendaak](https://trendaak.com/blog/facebook-ads-cost-2026-middle-east) and others found via Arabic search (blogs; not verified) |
| Influencer rates, KSA (all platforms) | Nano SAR 750–3,000 · micro 3,000–15,000 · macro 15,000–75,000 · mega 75,000+ per post | Starngage estimates, **not Facebook-specific** | [Influencer Marketing Hub](https://influencermarketinghub.com/influencer-marketing-in-saudi-arabia-guide/) |

### 13.2 Conversion to our formula basis

- **View rate (% of followers per video):** Socialinsider gives views per post by **size band**, not per follower. Converting needs an average follower count per band, which neither page publishes. We used the geometric middle of each band (1–5K ≈ 2.2K, 5–10K ≈ 7K, 10–50K ≈ 22K, 50–100K ≈ 71K, 100K–1M ≈ 316K; macro ≈ 700K). Brand pages are skewed to the low end of a band, so true rates are probably a little higher.
  - Dataset A (2026 video page): ≈ 12% · 6.9% · 4.5% · 3.5% · 2.1% (macro ≈ 0.9%).
  - Dataset B (25M posts, 2024–25): ≈ 0.45% · 0.7% · 0.45% · 0.28% · 0.20% (macro ≈ 0.09%).
  - The two differ 6–26× and neither page explains why. Reach-based figures (0.5–4.35% of followers) sit between them. **Safe = dataset B, expected = well below dataset A, near the reach benchmarks.**
- **Engagement as % of views:** Socialinsider's rate is per **follower**. Within dataset A, engagements ÷ views = (rate × band-middle followers) ÷ views, which gives ≈ 2.5% · 3.6% · 4.4% · 5.1% · 7.3% across the five bands. The upward trend probably comes from the band-middle assumption, so we use a flat range. Cross-check: Buffer's video median 4.84% is on impressions. **Not convertible with confidence; the range below is an estimate.** Dataset B cannot be converted (its views are too low for the follower-based rate, which implies an impossible ratio).
- **CTR:** the figures are on reach or impressions; reach ≈ views for video within a factor of ~1–2, so we treat them as % of views and keep the safe value low.
- **CPE ceiling:** no source for creator content. Derived as CPM ceiling ÷ (1000 × engagement rate): SAR 55 ÷ (1000 × 2%) = 2.75; SAR 30 ÷ (1000 × 2%) = 1.5.

### 13.3 Recommended safe-margin values [safe – expected]

| Tier | View rate (% of followers per video) | Basis | Engagement (% of views) | Basis |
|---|--:|---|--:|---|
| Nano <10K | 0.5 – 4% | Safe: dataset B (0.45–0.7%). Expected: small-page reach 4.35%; below dataset A (7–12%) | 2.0 – 3.5% | Safe below implied 2.5%. Expected below Buffer 4.84% (impressions) |
| Micro 10–100K | 0.3 – 2.5% | Safe: dataset B (0.28–0.45%). Expected: below dataset A (3.5–4.5%) | 2.0 – 3.5% | As above |
| Mid 100–500K | 0.2 – 1.5% | Safe: dataset B (0.20%). Expected: below dataset A (2.1%) | 2.0 – 3.5% | As above |
| Macro 500K–1M | 0.1 – 0.8% | Safe: dataset B (≈0.09%). Expected: dataset A (≈0.9%) | 2.0 – 3.5% | As above |
| Mega 1M+ | 0.05 – 0.4% | **Extrapolated**: no data above 1M; large-page reach 0.50% as ceiling | 2.0 – 3.5% | As above |

| Factor | Safe / Acceptable | Expected / Good | Basis |
|---|--:|--:|---|
| Link click-through (% of views) | 0.2% | 0.5% | Below the lowest 2026 figure (0.3–0.4%); no tier split in current data. Reels carry no clickable link, so link posts only |
| CPM ceiling (SAR) | 55 | 30 | Saudi paid-ad CPM SAR 15–56; unchanged from the earlier provisional value |
| CPE ceiling (SAR) | 3.0 | 1.5 | **Derived** (see 13.2); paid CPE SAR 0.04–0.94 is a floor, not a creator price |
| CPC ceiling (SAR) | 8 | 4 | Top of published ad range (SAR 8.6); influencer clicks cost more than ad clicks. Note CPM 55 with 0.2% CTR implies ≈ SAR 27 per click, so clicks are the binding value floor |

With pharma factor 0.8, safe engagement per video = followers × view rate × 2.0% × 0.8. Example, a 50K-follower doctor: 50,000 × 0.3% = 150 safe views, about 2 engagements per video. Facebook adds almost nothing at safe rates, which is the reason to keep it an add-on.

### 13.4 Ready-to-use dict (NOT applied; same shape as section 4, % units, reach_per_view omitted)

```python
"facebook": {
    "view_rate": {            # % of followers per video, [safe, expected]
        "nano":  [0.5, 4.0],
        "micro": [0.3, 2.5],
        "mid":   [0.2, 1.5],
        "macro": [0.1, 0.8],
        "mega":  [0.05, 0.4],  # extrapolated
    },
    "eng_rate": {             # % of views, [safe, expected]; estimate, low confidence
        "nano":  [2.0, 3.5],
        "micro": [2.0, 3.5],
        "mid":   [2.0, 3.5],
        "macro": [2.0, 3.5],
        "mega":  [2.0, 3.5],
    },
    "ctr": [0.2, 0.5],        # % of views [safe, expected]
    "cpm": [55, 30],          # SAR [acceptable, good]
    "cpe": [3.0, 1.5],        # SAR [acceptable, good]; derived
    "cpc": [8, 4],            # SAR [acceptable, good]
},
```

### 13.5 Saudi / MENA factors

| Factor | Finding | Use |
|---|---|---|
| Facebook audience in KSA | 37.4M "users" = 96.6% of population (Sep 2026); 65% men, 35% women; 25–34 is 45.4%, 35–44 23.2%, 18–24 19%. These are Meta addressable-audience estimates and look inflated ([NapoleonCat](https://napoleoncat.com/stats/facebook-users-in-saudi-arabia/)) | Reach exists, skewed male and 25–44. Not an engagement figure |
| Platform mix | KSA is described as a TikTok and Snapchat market (TikTok 38.6M, Snapchat 25.3M, Instagram ~18M); Facebook is called "Facebook-first" only for Egypt ([Kolsquare, Apr 2026](https://www.kolsquare.com/en/blog/influencer-marketing-in-the-middle-east-in-2026-high-stakes-high-spend-and-the-arabic-first-imperative)). One guide lists Facebook as declining in KSA (search summary, source not verified) | Supports keeping Facebook secondary for Jamjoom |
| Arabic content uplift | "35–50% higher engagement than translated English" in GCC, attributed to Boomerang.ae via Kolsquare and Influencer Marketing Hub; not Facebook-specific | **Not applied.** Treat as upside only |
| Ramadan | Ad CPM +50–80% (BIMO, Stackmatix); 72% say social is the most effective Ramadan channel (Kolsquare); no organic Facebook Ramadan data | Raise CPM ceilings in Ramadan; do not raise rates |
| MMA MENA Influencer Marketing Guide (May 2026) | Has a regional rate card and platform benchmarks ([Campaign ME](https://campaignme.com/mma-mena-publishes-a-standardised-influencer-marketing-guide/)); form-gated at [MMA](https://mmaglobal.com/documents/mma-influencer-marketing-guide). Contents not obtained | Best remaining source |

### 13.6 Still missing

- **Influencer-specific Facebook view rate by tier:** no public figure. Only brand-page data, and the two Socialinsider datasets disagree 6–26×.
- **Engagement as % of views:** no source states it; our range is an estimate from a follower-based rate.
- **Click-through on influencer posts, by tier:** no 2026 tier data; the tier trend (2.2% down to 0.8%) is from a 2021 source read via search summary only. Fan Page Karma and Benchmarketing pages were not read in full.
- **Saudi cost per click and per engagement:** only agency blogs, several-fold spread; no Saudi cost per engagement at all; creator CPE is derived.
- **Mega tier (1M+):** extrapolated.
- **Saudi Arabic uplift and Ramadan effect on Facebook:** no Facebook-specific figure.
- **Next steps for real numbers:** download the MMA MENA guide (form on the MMA page), or pull Facebook Page Insights (views, reach, link clicks) from the doctors' own pages.

## 14. Multi-platform calculation (planner, built 2026-10-18)

For a campaign on several platforms, each creator's planned posts count on every chosen platform where they have an account, at their follower count on that platform. Each platform uses its own library rates, then views and engagements are added. The value floor uses CPM/CPE/CPC ceilings blended by each platform's share of the safe estimate. One platform gives exactly the single-platform result. Facebook is excluded until its rates are confirmed. Jamjoom check: Instagram + TikTok gives 1,082,000 views and 14,200 engagements (safe), 2,766,000 and 66,600 (expected), matching the live targets.
