# International influencer portals: benchmark for the HelloVoice revamp

Researched 2026-10-07/08 from public pages only (homepages, product and pricing pages, help centres,
G2/Capterra/Trustpilot). No sign-ups, no logins. **[U]** = unverified, third-party or self-reported.
Input for the `/brainstorming` requirements session; designs are then executed with `/impeccable`.
This file holds no client or creator data and is safe for the public repo.

---

## 0. The 12 insights that matter most

1. **We sit in an empty gap.** Marketplaces (Collabstr, JoinBrands, Insense) sell priced creators with no real
   audience data; SaaS tools (Modash, HypeAuditor, Favikon) sell data with no vetted, priced roster; agencies
   (Whalar, Viral Nation, Socially Powerful) show **no roster at all**. Nobody combines a vetted, priced,
   regional roster + audience data + managed production for KSA/GCC. That is our positioning.
2. **Show, don't tell, from the first screen.** The strongest homepages (JoinBrands, Heepsy, Kolsquare) put a
   **live search box or real creator cards in the hero**. Agencies that hide everything rely on logo walls.
3. **One dominant CTA + one role split.** "Send a brief" / "Book a 30-min call" as primary; a separate
   "I'm a brand / I'm a creator" fork (Billo, Favikon, Captiv8).
4. **Licence status is the unclaimed trust signal in MENA.** KSA Mawthooq (SAR 15k / 3 yrs, GAMR) and the UAE
   Advertiser Permit (mandatory since **1 Feb 2026**, permit number shown on profiles) are legal requirements.
   **No platform shows licence status on creator cards.** We should.
5. **Pharma compliance is a gap across all 12 enterprise platforms.** None documents MLR routing, adverse-event
   (AE) monitoring or claims checks. Only specialists (Veeva/MarketBeam, LiveWorld, Real Chemistry) do it.
   With ~⅔ of HelloVoice work in healthcare, a visible compliance layer is our biggest differentiator.
6. **One labelled quality score beats ten numbers.** HypeAuditor AQS (>70 good / 40–70 check / <40 bad),
   Favikon "91.4 Genuine", Kolsquare Credibility, Sprout Brand Fit, Traackr VIT. Score + a word + a colour.
7. **The brief is the contract.** Aspire/Later bundle deliverables, dates, compensation, **usage-rights duration**
   (3/6/12 months, clock starts at approval), **ad access** (Spark Ads, Partnership Ads, allowlisting) and
   disclosure terms into one object the creator accepts.
8. **Approval vocabulary has converged to three outcomes:** *Approved / Approved with corrections / Needs work*,
   with **creator-facing vs internal comments**, **comments anchored to a frame or line**, **one named approver per
   step**, and an **SLA with auto-approve** (Aspire: 3 business days).
9. **Trust devices that remove fear:** escrow ("pay on approval"), delivery guarantee or refund (Trend, JoinBrands),
   **stated SLAs** (Insense: applications in 48 h, content in 14 days), revisions per plan (JoinBrands 1/2/3/10).
10. **Proof = metric-first case cards + live counters.** Viral Nation: challenge → 3 numbers → approach → tags.
    Obviously: exact running counters (152,562 collaborations…). Not adjectives.
11. **AI is now sold as "jobs done", not dashboards.** GRIN's Gia ("10 jobs off your plate"), Traackr's Abigail,
    Favikon's Favy. Our AI brief + chat + copilot already fit this; it needs a name and a jobs framing.
12. **Shareable reporting is weak everywhere except** Brandwatch (white-label dashboards, live links), Linqia
    (public brief link) and JoinBrands Max (white-label share links). Our `/campaign/#t=` client report is ahead —
    make it a headline feature.

---

## 1. Who we studied

| Group | Platforms | What to borrow |
|---|---|---|
| Self-serve marketplaces | Collabstr, JoinBrands, Insense, Billo, Trend.io, Popular Pays | Priced cards, escrow, SLAs, ratings + jobs done, fixed packs |
| Discovery / analytics SaaS | Modash, HypeAuditor, Heepsy, Influencity, Favikon, Kolsquare, Upfluence | Filters, profile report anatomy, quality score, lookalikes, overlap |
| Enterprise IRM | CreatorIQ, GRIN, Aspire, Traackr, Later (Mavrck), Influential/Captiv8, Sprout (Tagger), Linqia, Dash Social, Skeepers, Brandwatch Influence, Meltwater (Klear) | Stage pipeline, brief-as-contract, approvals, reporting, EMV |
| Agencies | Whalar, Billion Dollar Boy, Viral Nation, Influential, Obviously, The Goat Agency, Socially Powerful | Case cards, counters, named tech, single CTA |
| MENA | ITP Live, Vamp, Sociata, Arabia Talents (ArabiaInsights portal), Flicron, Talent Plus, MoonTech, Kliq | Regional proof, licensing, Arabic-first |
| Health specialists | WEGO/Health Union, Lumanity, Real Chemistry, Socially Powerful Pharma | Compliance copy, HCP vetting, fair-market pay |

Closest regional analogue to our portal: **Arabia Talents' ArabiaInsights** (shortlist + live tracking for brands) **[U]**.
Names checked and **not found**: Arabhaus, Influencers.ae/Brandz, Fluence, Ayoub Tech. Mawahib/Nawy are unrelated.

---

## 2. Client journey: the benchmark blueprint

The canonical end-to-end pipeline across vendors:

```
Land → Explore (no login) → Sign in → Brief → Shortlist → Compare → Request quote / Book
  → Contract (brief-as-contract, usage rights) → Product shipped → Draft → Draft review
  → Live post → Post review → Track → Pay (on approval) → Report → Rebook
```

| Stage | Best-in-class pattern | Source |
|---|---|---|
| Land | Hero = search bar or real creator cards; one primary CTA; role fork | JoinBrands, Heepsy, Billo |
| Explore | Browse before sign-up; lock deep data (audience, price) behind sign-in | Modash (metered unlocks), Heepsy free tier |
| Sign in | No credit card, no demo for the first value moment | Modash, Heepsy, Collabstr |
| Brief | Templates; brief = deliverables + dates + rights + ad access + disclosure | Aspire Standard Brief, Insense |
| Shortlist | AI-built list *or* hand-built list with status/notes; inbound applications as alternative | Favikon Favy, Modash CRM, Insense |
| Compare | Side-by-side; **audience overlap detection** between shortlisted creators | Influencity |
| Quote / book | Fixed package prices, no negotiation; "price from" on cards | Collabstr, Trend.io |
| Contract | Usage rights 3/6/12 mo; clock starts at approval | Aspire |
| Draft review | 3 outcomes; external vs internal comments; anchored comments; one approver; SLA + auto-approve | Later, Linqia, Aspire |
| Live / track | Auto-capture posts in campaign window; refresh cadence stated (CreatorIQ: 8 h) | CreatorIQ, Modash (no creator login) |
| Pay | Released on approval; escrow; refund if no delivery | Collabstr, JoinBrands |
| Report | Shareable live link, white-label, PDF export; metric definitions published | Brandwatch, JoinBrands Max |
| Rebook | "Rehire", performance bonus, ambassador programme | JoinBrands, Aspire |

**Friction the reviews punish:** demo-gated access, opaque pricing, annual lock-in, auto-renewal, weak in-app
messaging, inaccurate discovery, payment delays, data gaps outside US/EU (nobody publishes GCC coverage).

**Insense's SLA line is the model for us:** state turnaround on the page (e.g. "shortlist in 24 h, content in 14 days").

---

## 3. Information architecture

### Public site (marketing)
Nearly universal order:
**Hero (2 CTAs) → logo wall → problem → modules/steps → numbers → testimonials & case cards → pricing teaser → FAQ → closing CTA.**

- Nav patterns: *Platform / Solutions (by role or industry) / Customers / Pricing / Resources / Log in / primary CTA*.
- Traackr splits Solutions by **role** (exec, programme owner, practitioner); Socially Powerful adds a
  **Procurement** nav item and publishes a **$50k minimum** — transparency as a filter.
- Industry pages with real compliance copy (Socially Powerful Pharma) outperform generic "Healthcare" pages (Obviously).
- Free tools/rankings as SEO magnets: HypeAuditor calculators, Favikon weekly **top-200 by niche/country**, Kolsquare Kolculator.

### App (client portal), standard modules
`Discover · Lists/Selections · Briefs · Campaigns (stages) · Content (review) · Reports · Payments · Account`
Plus an AI layer across all of them.

---

## 4. Creator card and profile anatomy

### Card (scan in 2 seconds)
| Always | Marketplaces add | Analytics tools add | **HelloVoice should add** |
|---|---|---|---|
| Photo, name/handle, platform icons, niche, city, followers, ER | Price from, rating, jobs completed, "Top creator" badge | One quality score with a label | **Licence badge** (Mawthooq ✓ / UAE permit), **HCP/healthcare tag**, fit score for the client's brief |

JoinBrands example: "1,415 jobs · 4.9". Heepsy: "845K · 7.1%". Favikon: "91.4 Genuine".

### Profile report sections (standard order)
1. Header: identity, platforms, scores, CTA (add to list)
2. Performance: ER vs tier benchmark, avg views, growth chart with **anomaly flags**
3. Audience: country/city, age, gender, language, interests, **real vs suspicious** split
4. Content: recent posts, sponsored posts, **brand affinity**, past brands
5. Fit: why this creator fits the brief (score + reasons)
6. Lookalikes
7. Export (PDF)

### Filters (standard set)
Platform · niche · creator location · follower range · ER · audience country/age/gender · language ·
creator gender/age · price band. Newer: AI prompt search, lookalikes, content search.
**MENA must-haves:** **Snapchat as a first-class platform** (KSA ~25M users, ~84% of internet users),
Arabic/English/dialect, nationality of audience, licence status, healthcare/HCP.

---

## 5. Brief and approval

### Brief fields (Aspire Standard Brief, best documented)
Deliverables (count, review date, go-live date) · content guidelines (features, key messages, captions,
hashtags, mentions, do's/don'ts) · compensation (cash/product/commission) · **usage rights** (3/6/12 mo/custom) ·
**ad access** (IG Partnership Ads, allowlisting, TikTok Spark, YouTube) · disclosure/FTC terms.

### Approval (Later + Linqia, best UX)
- Statuses: **Approved / Approved with corrections / Needs work** (Linqia: *Revise & resubmit*, then *Finalized*)
- Two comment boxes: **"Feedback for the creator"** vs **"Internal comments"**
- Comments anchored to highlighted text or a video frame, with "Suggest replacement"
- Multi-step: one **Approver**, several **Reviewers**, optional **Spectators** per step
- Brief exportable to PDF and shareable by public link
- Aspire: review window 3 business days, unactioned content auto-approved
- **For pharma, add an MLR step** where the client's medical/regulatory team is the final approver
  ("MLR teams retain final authority", Socially Powerful); timelines 6–12 weeks.

---

## 6. Reporting and metrics

### What clients see
Reach, impressions, views, ER, clicks/CTR, EMV, CPM/CPE/CPV, conversions/ROAS. EMV and ROAS dominate screens.
Shareable live links, white-label, 8-hour refresh (CreatorIQ), PDF export. **Publish your metric definitions
inside the report**: every source warns that ER and EMV are not standardised.

### Glossary (standard definitions)
| Metric | Definition |
|---|---|
| Reach | Unique accounts that saw it |
| Impressions | Total views incl. repeats |
| ER | (likes+comments+saves+shares) ÷ followers × 100 — **state the denominator** (followers / reach / views) |
| EMV | Σ action × market value; **no industry standard** (Later uses Ayzenberg values; CreatorIQ proprietary) |
| CPM | Cost ÷ impressions × 1,000 |
| CPE | Cost ÷ engagements |
| CPV | Cost ÷ video views (preferred for Reels/TikTok/Snap) |
| ROAS | Attributed revenue ÷ spend |
| VIT (Traackr) | (Visibility + Impact) × Trust |

Our own definitions are in `CAMPAIGN-TRACKER-BRIEF.md` §11; they are consistent with the above.

### Benchmarks (directional; sources conflict)
| Tier | Instagram ER (by followers) | TikTok ER |
|---|---|---|
| Nano (<10K) | ~4–8% (Qoruz 6.0%) | ~10% |
| Micro (10–50/100K) | ~2–4% (3.5%) | ~7.5–8.7% |
| Mid (50–500K) | ~1.5–3% (2.5%) | ~6–7.5% |
| Macro (500K–1M) | ~1–2% (1.5%) | ~3.5–4.5% |
| Mega/celebrity | ~0.5–1% | ~2–3% |

CPM (practitioner estimates **[U]**): IG Stories $20–50, Reels $15–45, TikTok $7–25.
No reliable public CPE/CPV benchmarks — build ours from campaign actuals.

### KSA creator rates per post (vendor estimates **[U]**)
Nano SAR 750–3k · Micro SAR 3k–15k · Macro SAR 15k–75k · Mega SAR 75k–300k+.
TikTok 10–20% below Instagram; Snapchat ≈ IG Stories; **+~40% in Ramadan/peak seasons**. No public UAE rate card.

### Market context
Global influencer marketing ~$32.6B (2025, IMH). GCC ~$315M (2025) → $772M (2032), **KSA ≈ 40% of GCC** (Kolsquare).
KSA influencer ad spend ~$96M (2025, Statista). MENA: ~60% of spend on macro/mega; **Arabic-first content gets
35–50% more engagement** than translated English; only 37% of MENA brands use AI for discovery.
Kolsquare counts **35% fewer active Saudi creators since Mawthooq (2022)** — licensing is reshaping supply.

---

## 7. Trust and compliance

| Device | Who | HelloVoice fit |
|---|---|---|
| Escrow / pay on approval | Collabstr, JoinBrands, Heepsy | Medium: we invoice; "you approve before it posts" carries the same promise |
| Delivery guarantee / refund | Trend.io, JoinBrands | High: "replace or refund" on a no-show creator |
| Stated SLAs | Insense | High |
| Usage rights stated up front | Aspire, Trend (100% rights) | High: default in every quote |
| Partner badges | Insense, Whalar (Meta/TikTok/Snap) | If we qualify (Snap is key in KSA) |
| ISO 27001 / GDPR / PDPL | Modash, CreatorIQ | Medium: Saudi PDPL statement |
| **Licence badge** | **nobody** | **Very high, first in market** |
| **Pharma/MLR layer** | **nobody on-platform** | **Very high: ⅔ of revenue** |

### Licensing facts
- **KSA Mawthooq** (GAMR, formerly GCAM): required for paid promotion on any social platform; SAR 15,000 / 3 years;
  ads only from the registered account; **non-Saudi creators must go through licensed Saudi agencies**;
  fines up to SAR 1M (Arab News). No public lookup tool found.
- **UAE Advertiser Permit** (UAE Media Council, Federal Law 55/2023): mandatory from 1 Feb 2026, paid and gifted,
  no follower threshold, **permit number displayed on profile**, annual report; health/finance need extra approvals;
  fines up to AED 1M (2M repeat).
- **Egypt**: 5k+ followers need a licence (E£50k).

### Pharma compliance checklist (synthesised; nobody publishes all of it)
FDA/SFDA/MOH health-ad approval · fair balance and ISI in briefs · HCP **licence verification** (SCFHS in KSA) ·
past-content scan for off-label claims · disclosure (#ad / إعلان) · **MLR final approval step** ·
**adverse-event detection in comments → pharmacovigilance alert** · audit trail · fair-market-value creator pay
(Lumanity "Patient Promise") · no confidentiality gag on sponsorship (WEGO was criticised for this).

---

## 8. Pricing models seen

| Model | Examples | Numbers |
|---|---|---|
| Take-rate marketplace | Collabstr 10%→5%, JoinBrands 15%→8%, Insense 20%→7% | Fee falls as subscription rises |
| Seats + metered unlocks | Modash $199/$499, Heepsy $0–299, Favikon $199/$299 credits | "Profile views / unlocks / tracked creators" per month |
| Fixed content packs | Trend.io $550 (6 videos) → $3,872 (56) | Per-unit price shown |
| Credit-based AI SaaS | GRIN $0/$200/$500/$1,000 | Moved from $25k+/yr to self-serve in 2026 |
| Enterprise annual | CreatorIQ ~$30–90k, Traackr ~$17–55k, Upfluence 12-mo minimum **[U]** | Demo-gated; most complaints |
| Agency minimum | Socially Powerful $50k project | Published openly |

**Our current model** (per-tier price bands, one indicative total per shortlist, AI credits) is closest to
fixed packs + credits. Benchmark says: show a **"from" price**, state what's included (revisions, usage rights,
SLA), and publish the Ramadan uplift.

---

## 9. HelloVoice today vs benchmark

What we already have (from `PORTAL.md`, `CATALOGUE.md`, `CAMPAIGN-TRACKER-BRIEF.md`):
email OTP sign-in · 11-question brief → AI-scored, budget-aware shortlist · fit badges · chat assistant ·
selections shared with colleagues · printable quotation · campaign tracker with `/go/` links and client report
link · creator insights upload · Arabic RTL · AI credits · admin copilot.

| Area | Benchmark | Us | Gap |
|---|---|---|---|
| First screen | Search/cards in hero, one CTA | Gate before roster | **Let visitors see a teaser roster before sign-in** |
| Card | Price from, rating, jobs done, quality score | No price, no rating | Quality score + licence badge + jobs done |
| Profile | Full audience report, lookalikes | Analysis exists for ~2.1k creators | Structure it in the standard order; add lookalikes |
| Filters | Standard set + AI | Have core + AI brief | Snapchat first-class, licence, HCP, audience nationality |
| Compare | Side-by-side, overlap | None | Compare view on a selection |
| Brief | Brief-as-contract | Brief = matching input | Add deliverables, dates, usage rights, ad access |
| Approval | 3 outcomes, two comment types, MLR | Not in portal | **Draft review in the portal** (+ MLR step) |
| Reporting | Live link, white-label, definitions | Have live link | Add definitions panel, PDF, benchmarks vs tier |
| Trust | SLAs, guarantee, rights | Not stated | Publish SLAs, replacement guarantee |
| Compliance | Gap in market | Healthcare-tier ranking exists | **Compliance page + licence + MLR + AE monitoring** |
| Proof | Case cards, counters | Website has posts/logos | Metric-first case cards inside the portal |
| AI | Named agent, jobs framing | Unnamed | Name it; "jobs it does for you" |

---

## 10. Revamp candidates (ranked, for brainstorming, not decisions)

**P1: differentiators nobody else has**
1. Licence badge on cards and profiles (Mawthooq / UAE permit, number + linked handle, verified date).
2. Healthcare compliance layer: compliance page, HCP-verified tag, MLR approval step, AE flagging in comments.
3. Draft review in the portal: Approved / Approved with corrections / Needs work, creator vs internal comments, SLA.

**P2: journey and conversion**
4. Teaser roster before sign-in (blurred handles/prices; full data after sign-in).
5. Card redesign: one quality score with a label, fit score, jobs completed with HelloVoice, licence, "price from".
6. Brief → contract: deliverables, dates, usage rights (default 3 months), Spark/Partnership Ads access, disclosure.
7. Stated SLAs and a replacement guarantee on the quote.
8. Compare + audience-overlap on selections.

**P3: proof and growth**
9. Metric-first case cards and live counters (creators, films, campaigns, views).
10. Named AI assistant framed as jobs done.
11. Public rankings (top creators by niche/city, opt-in) as SEO; Arabic-first.
12. Report: metric definitions panel, tier benchmarks, PDF, white-label.

---

## 11. Questions for the `/brainstorming` session

1. Who is the primary user: brand manager, agency, or pharma brand + MLR reviewer? Do we design for all three?
2. Open teaser vs fully gated roster: how much can a visitor see before signing in (creator data is confidential)?
3. Show prices on cards ("from" band) or keep the single indicative total?
4. Do we verify and store licence numbers for every creator? Who owns that data and how often is it refreshed?
5. How far do we go on pharma: compliance page only, or MLR step + AE monitoring in the product?
6. Is draft review in scope now, or after the campaign tracker is deployed?
7. Quality score: build our own (from the 2.1k analyses) or show vendor numbers?
8. Which SLAs and guarantee can operations actually keep?
9. Self-serve booking vs "request a quote → KAM" — where does the KAM enter the journey?
10. Arabic-first or bilingual-equal for the revamp?

---

## Sources

**Enterprise:** creatoriq.com · creatoriq.com/creator-marketing-benchmarks · grin.co · grin.co/pricing ·
aspire.io · help.aspireiq.com (Standard Briefs, Custom Stages) · intercom.help/aspireiq_elevate (Review Content) ·
traackr.com · traackr.com/resources/emv-vit-how-brands-measure-influencer-marketing · later.com/influencer-marketing ·
help-influence.later.com (stages, Draft Review, EMV) · captiv8.io · mediapost.com/publications/article/406049 ·
sproutsocial.com/influencer-marketing · linqia.com · linqia-resonate.helpscoutdocs.com/article/159-creator-brief-v2 ·
dashsocial.com · influencermarketinghub.com/skeepers · brandwatch.com/products/influence · explore.meltwater.com/klear ·
intuitionlabs.ai (Veeva MarketBeam) · archive.com/blog (pricing estimates) · vendr.com · g2.com · capterra.com

**Marketplaces / SaaS:** insense.pro (+/pricing) · billo.app · modash.io (+/pricing) · hypeauditor.com ·
heepsy.com (+/pricing) · influencity.com · knowledge.influencity.com · favikon.com (+/pricing) · upfluence.com ·
kolsquare.com · joinbrands.com (+/pricing) · trend.io (+/pricing) · collabstr.com (snippets) ·
trustpilot.com/review/collabstr.com · g2.com/products/insense · creator-hero.com · influencer-hero.com

**Agencies / MENA / health:** whalar.com · billiondollarboy.com · viralnation.com · influential.co · obvious.ly ·
goatagency.com · sociallypowerful.com (+/industries/pharma) · itp.com/brands/itp-live · vamp.com/blog ·
absolutegeeks.com (Arabia Talents) · app.dealroom.co/companies/flicron · influencermarketinghub.com/mena-influencer-marketing-report ·
influencermarketinghub.com/influencer-marketing-in-saudi-arabia-guide · kolsquare.com/en/blog (Middle East 2026) ·
arabnews.com/node/2176661 · saudipedia.com (Mawthooq) · clydeco.com · gulfnews.com (UAE Advertiser Permit) ·
middleeastbriefing.com · fiercepharma.com · healthaffairs.org · lumanity.com/patient-engagement ·
later.com/blog/healthcare-influencer-marketing · agbi.com (Snap KSA) · statista.com · qoruz.com · emplicit.co ·
dashsocial.com/blog/tiktok-benchmarks · favikon.com/blog · starngage.com · modash.io/blog (CPM)
