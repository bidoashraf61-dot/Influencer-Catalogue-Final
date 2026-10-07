# Brief: discovery revamp (filters, sourcing, grouping)

Stage 1 output of `/brainstorming`, 2026-10-08. Reference: `PORTAL-BENCHMARK.md` §3–4.
Design and build run through `/impeccable:impeccable` (hard rule).

```
=== BRIEF ===
PROJECT:     Catalogue discovery revamp — influencer-catalogue.hellovoice.co.uk (/ and /selection/)
FORMAT:      UI/UX + structure change to the roster page; cards, profile, campaign pages untouched
USER:        Brand marketer (pharma / FMCG), signed in. Roster stays fully gated.
PRICING:     Unchanged: no price per creator, one indicative total per shortlist.
TAKEAWAY:    "I can narrow 2,000+ creators to the right 20 in under a minute, the way Modash/HypeAuditor do it."
LOOK:        HelloVoice theme (THEME-BRIEF.md, DESIGN.md, admin revamp tokens). References give structure, not colours.
```

## Locked decisions

1. **Layout: left filter sidebar, grouped and collapsible** (Modash / HypeAuditor / Heepsy).
   - Live result count, active-filter chips above the grid, Clear and Save (saved search) at the foot.
   - Search box and Sort above the grid.
   - Mobile: the sidebar becomes a bottom sheet behind a "Filters (n)" button.
2. **Filter groups: every option we hold data for.**
   - **Creator**: platform (Instagram, TikTok, **Snapchat**, YouTube, X), size/tier with HCP group, followers range +
     quick picks, location country → city, nationality, niche/interest, account type, language (if on file),
     healthcare professional.
   - **Audience** (from analyses): audience country, city, gender split, age band, language, interests,
     brand affinity, real-audience % (100 − fake followers %).
   - **Performance** (from analyses): ER range, reels ER, average views, average likes/comments, follower growth %,
     posts per week, last post recency, sponsored-post share, brands worked with.
   - Creators without an analysis: audience/performance filters exclude them by default, with a visible toggle
     "Include creators not yet measured (n)".
3. **Sourcing menu = search modes** (Modash): a switch in the search bar.
   - **Filters**: the default; the sidebar described above.
   - **AI search**: a prompt that writes the filters. This reuses the existing brief/AI parser and spends credits
     as today.
   - **Lookalike**: "Similar to @creator", built from a name typed or a "More like this" link on cards.
4. **Grouping: a Group-by control on the catalogue**, as on the selection page.
   - Groups: None · Size · Platform · Country · Niche · Audience country.
   - Collapsible group headers with counts.

## Assumptions (correct me if any is wrong)

- "Same theme colours" = **our** HelloVoice theme, not the references' colours.
- "HelloVoice history" filters (worked with us, campaigns count) are **out** for now. They weren't selected, and
  history is internal. Easy to add later.
- Filter logic stays as today: **OR within a group, AND across groups.** URL state is kept, so a filtered view is shareable.
- The selection page gets the same sidebar. Its extra filters (fit, role, tags) become a fourth group, **Selection**.
- Arabic RTL: the sidebar mirrors to the right.
- **Data/security:** audience and performance values are not on the cards today. Filtering on them needs a compact
  per-creator summary sent to signed-in clients (numbers only, no handles beyond what the card already shows) or a
  server-side filter endpoint. Recommendation: **server-side filter endpoint**, so the full analysis never leaves the server.
- Counts beside every option (Heepsy pattern) are **not** shown. The current code deliberately hides roster
  counts as commercial information; only the total result count shows.

## Out of scope

Card design, creator profile/analysis page, campaign pages, pricing display, public teaser, brief-as-contract,
draft review, licence badges.
```

=== WORKFLOW PLAN ===
TASK TYPE:   UI/UX revamp of an existing product surface
ROUTE:       brainstorming (done) → impeccable shape → impeccable craft (build) → impeccable audit/polish → deploy via update.sh
SKILLS IN:   impeccable:impeccable — layout, sidebar component, search-mode switch, group-by, mobile sheet, RTL
SKILLS OUT:  film-workflow stages (2A–3b) — not a film task; frontend-design / ui-ux-pro-max — replaced by impeccable (hard rule)
NEXT STEP:   /impeccable:impeccable (shape the discovery screen in our theme)
```
