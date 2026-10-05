---
name: HelloVoice Influencer Catalogue
description: Passcode-gated creator roster, campaign report and creator analysis in HelloVoice's ink, lime and linen world.
colors:
  ink: "#121212"
  black: "#000000"
  graphite: "#383838"
  white: "#ffffff"
  linen: "#e9dcd2"
  lime: "#e8ff76"
  vivid-orange: "#ff691e"
  vivid-red: "#ee1515"
  go-green: "#14884a"
  go-green-soft: "#e7f7ed"
  amber: "#e2780f"
  amber-soft: "#fff1e2"
  amber-text: "#a85507"
  red-soft: "#fde9e9"
  red-text: "#c01010"
  track-stone: "#efece6"
  pending-stone: "#efede8"
  rule: "rgba(18,18,18,.12)"
  rule-soft: "rgba(18,18,18,.07)"
  medal-gold: "#d6a52b"
  medal-silver: "#9ea6ae"
  medal-bronze: "#b06f3a"
typography:
  display:
    fontFamily: "Bebasneue, Arial, sans-serif"
    fontSize: "clamp(3.25rem, 1rem + 9vw, 9.5rem)"
    fontWeight: 400
    lineHeight: 0.9
  headline:
    fontFamily: "Bebasneue, Arial, sans-serif"
    fontSize: "clamp(2.75rem, 1.6rem + 3.6vw, 5.5rem)"
    fontWeight: 400
    lineHeight: 0.9
  title:
    fontFamily: "Bebasneue, Arial, sans-serif"
    fontSize: "clamp(2rem, 1.4rem + 1.8vw, 3rem)"
    fontWeight: 400
    lineHeight: 1
  numeral:
    fontFamily: "Bebasneue, Arial, sans-serif"
    fontSize: "clamp(2.4rem, 1.7rem + 1.8vw, 3.4rem)"
    fontWeight: 400
    lineHeight: 0.95
  body:
    fontFamily: "\"DM Sans\", Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
  body-lead:
    fontFamily: "\"DM Sans\", Arial, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "\"DM Sans\", Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "0.12em"
  action:
    fontFamily: "Bebasneue, Arial, sans-serif"
    fontSize: "20px"
    fontWeight: 400
    lineHeight: 1
    letterSpacing: "0.06em"
rounded:
  bar: "6px"
  track: "8px"
  sm: "12px"
  md: "20px"
  lg: "28px"
  pill: "999px"
spacing:
  page-pad: "5%"
  gap-sm: "10px"
  gap-md: "18px"
  gap-lg: "24px"
  section: "72px"
  section-mobile: "52px"
components:
  button-lime:
    backgroundColor: "{colors.lime}"
    textColor: "{colors.ink}"
    typography: "{typography.action}"
    rounded: "{rounded.pill}"
    padding: "16px 32px"
    height: "44px"
  button-lime-hover:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.lime}"
  button-line:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.action}"
    rounded: "{rounded.pill}"
    padding: "16px 32px"
  button-line-hover:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.lime}"
  link-pill:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "0 18px"
    height: "44px"
  chip:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "0 16px"
    height: "42px"
  chip-active:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.lime}"
  signal-good:
    backgroundColor: "{colors.go-green-soft}"
    textColor: "{colors.go-green}"
    rounded: "{rounded.pill}"
    padding: "3px 10px 3px 8px"
  signal-moderate:
    backgroundColor: "{colors.amber-soft}"
    textColor: "{colors.amber-text}"
    rounded: "{rounded.pill}"
    padding: "3px 10px 3px 8px"
  signal-low:
    backgroundColor: "{colors.red-soft}"
    textColor: "{colors.red-text}"
    rounded: "{rounded.pill}"
    padding: "3px 10px 3px 8px"
  scorebug:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.white}"
    padding: "48px 0 40px"
  verdict-pill:
    backgroundColor: "{colors.lime}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "14px 28px"
  verdict-pill-good:
    backgroundColor: "{colors.go-green}"
    textColor: "{colors.white}"
  verdict-pill-moderate:
    backgroundColor: "{colors.amber}"
    textColor: "{colors.white}"
  verdict-pill-low:
    backgroundColor: "{colors.vivid-red}"
    textColor: "{colors.white}"
  post-card:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
  post-view-button:
    backgroundColor: "{colors.lime}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    height: "46px"
  data-page:
    backgroundColor: "{colors.linen}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "clamp(24px, 4vw, 48px)"
  stamp:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "14px 18px 12px"
  stamp-lead:
    backgroundColor: "{colors.lime}"
    textColor: "{colors.ink}"
  seal-analysed:
    backgroundColor: "{colors.lime}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    size: "128px"
  input-gate:
    backgroundColor: "transparent"
    textColor: "{colors.white}"
    rounded: "{rounded.pill}"
    padding: "16px 24px"
    width: "260px"
---

# Design System: HelloVoice Influencer Catalogue

## Overview

**Creative North Star: "The Broadcast Desk"**

A client-facing world built from three materials: solid ink (#121212) bars that behave like broadcast graphics, warm linen (#e9dcd2) bands that hold data, and a single acid lime (#e8ff76) that marks the thing to act on or the thing that won. Display is set in Bebas Neue at poster scale with tight leading; everything read rather than glanced at is DM Sans. Numbers are typeset as headlines, not tiles: a figure in Bebas over a small tracked uppercase label, ruled off from its neighbours by hairlines.

Every surface opens behind the same dark passcode gate, then alternates white, ink and linen full-bleed sections. The catalogue roster is the incumbent; the campaign report (a match-day results package) and the creator analysis (a talent passport) extend it without new hues, only new devices: the scorebug, the stage rail, the medal podium, the bullet bar, the double-ruled stamp and the round seal. Rotation is the world's one gesture of hand: verdict pills, seals and stamps sit a few degrees off true, as if pressed onto the page.

Motion is nearly absent. The marquees on the catalogue roster and the LIVE pulse on the campaign scorebug are the only continuous animation; everything else is short colour transitions on hover (.2 to .25s ease). All of it stops under reduced motion.

**Key Characteristics:**
- Ink, lime and linen carry the brand; green, amber and red carry judgement.
- Bebas Neue for every name, number and action; DM Sans for every sentence and label.
- Full-bleed alternating bands (white, ink, linen) instead of boxed dashboards.
- Pill geometry for every interactive control; 20px and 28px radii for containers.
- Pressed, slightly rotated marks (verdict, seal, stamps) as the signature gesture.
- Flat by default; shadow only for hover lift, floating panels and the active gantt bar.

## Colors

A high-contrast ink-and-paper palette with one acid accent and a strictly scoped verdict trio.

### Primary
- **Broadcast Lime** (lime): the act-and-win colour. Primary buttons, "View on <platform>" buttons, the active chip text on ink, the lead audience stamp, the "Analysed" seal, scores and figures on ink panels, the top podium spot's tint, the active stage's title, the 1st-place podium score.

### Secondary
- **Vivid Orange** (vivid-orange): the catalogue's ticker band between hero and filters. A brand band only; it is never a data colour and never a verdict.
- **Vivid Red** (vivid-red): focus rings (3px outline, 2px offset) on light surfaces, the LIVE dot, the gantt "today" line, error text, and the Low verdict. A "now / attention" signal, never decoration.

### Tertiary (verdict set)
- **Go Green** (go-green) with its soft tint (go-green-soft): Strong verdicts, completed stages and completed gantt bars, the submitted-state panel.
- **Amber** (amber) with soft tint and darkened text tone (amber-soft, amber-text): Fair / moderate verdicts only. Distinct from vivid orange on purpose.
- **Signal Red tints** (red-soft, red-text): Low verdicts on light surfaces.
- On ink, the signal pills switch to translucent fills (25% of the hue) with light text tones (#7debac, #ffbb75, #ff9393 in the scorebug; #6fe3a0, #ffb469, #ff8a8a in ink sections).

### Neutral
- **Ink** (ink): text, scorebug, leaderboard section, gate, sealed state, footer, chips at rest on the catalogue, bar fills.
- **Linen** (linen): data bands (catalogue filters and grid, campaign headline and performance bands, the passport data page).
- **Graphite** (graphite): secondary text, labels, notes.
- **White** (white): the default page and every card on linen.
- **Stone tracks** (track-stone, pending-stone, plus #f4f2ee and #e5e1d9 in the rail and gantt): empty bar tracks, pending stages and pending chips.
- **Rules** (rule, rule-soft): 1px hairlines between sections, rows and card borders. On ink, white at 8 to 16%.
- **Medal metals** (medal-gold, medal-silver, medal-bronze): podium photo rings and drawn medals, ranks 1 to 3 only.

### Named Rules
**The Verdict Hues Rule.** Green, amber and red mean good, moderate and low. On data surfaces they appear only in signal pills, verdict pills, bullet-bar fills and completed-stage marks; a chart, bar or panel that is not making a judgement is drawn in ink, lime or stone.

**The One Acid Rule.** Lime is the only saturated brand colour inside the report and passport. It marks the action or the winner; if two lime elements compete in one band, one of them is wrong.

## Typography

**Display Font:** Bebas Neue (self-hosted as `Bebasneue`, fallback Arial)
**Body Font:** DM Sans variable (fallback Arial)

**Character:** A condensed all-caps poster face that makes every number feel like a scoreline, against a calm geometric sans that keeps notes and labels quiet.

### Hierarchy
- **Display** (400, up to clamp(3.25rem, 1rem + 9vw, 9.5rem) on the scorebug and up to 20rem on the catalogue hero, line-height 0.9 to 1): page titles, campaign and creator names. Long names wrap anywhere rather than overflow.
- **Headline** (400, clamp(2.75rem, 1.6rem + 3.6vw, 5.5rem), 0.9): section heads in the report; the passport uses clamp(2.4rem, 1.4rem + 2.8vw, 4.2rem).
- **Title** (400, clamp(2rem, 1.4rem + 1.8vw, 3rem), 1): sub-sections, chart titles (30px), podium names (28px), bullet-bar names (28px).
- **Numeral** (400, clamp(2.4rem, 1.7rem + 1.8vw, 3.4rem), 0.95, no wrap): every headline figure, with units in a `small` at 0.5em.
- **Body** (400, 15px, 1.6; ledes up to 56 to 70ch): notes, ledes, table cells. Lead text 17 to 18px.
- **Label** (500 to 600, 12 to 13px, 0.12em, uppercase, graphite): the term above a figure in a definition list, panel headings, table heads.
- **Action** (Bebas 400, 19 to 22px, 0.06em): every button and the "View on <platform>" link.

### Named Rules
**The Figure-Over-Term Rule.** A metric is a Bebas figure under a small uppercase DM Sans term, in a definition list, separated by hairlines. Never a tile with an icon.

**The Two Faces Rule.** Bebas for names, numbers and actions; DM Sans for anything read as a sentence. No third family.

## Layout

Full-bleed bands stacked vertically, each holding a centred container with 5% side padding. Containers narrow by reading load: 1680px for the catalogue roster, 1440px for the campaign report, 1280px for the creator passport. Report sections breathe at 72px top and bottom (52px under 700px); band-to-band contrast (white, ink, linen) does the separating, so sections carry no cards around them.

Grids are intrinsic: `auto-fit` / `auto-fill` with minmax floors (150px scoreline cells, 170px headline figures, 260px post cards, 280 to 320px panels and charts). Gaps step through 10, 16 to 18, and 24px. The scoreline is a single ruled row of cells divided by 1px verticals.

Responsive rules observed:
- **Under 1000px:** the gantt label column narrows to 170px; bullet bars stack name, track and number.
- **Under 700px:** the scoreline becomes 2 columns; the gantt drops its axis, lanes and today line and becomes a list of stage rows with dates; the podium becomes a single column; the highlights wall is 2 columns (1 under 420px).
- **Under 820px (passport):** the data page goes single column, the seal moves into flow at 92px, analysis split pages stack.
- **Catalogue:** steps at 991, 767 and 560px.

Print: gate, top bar, filters and end actions are hidden; colours print exactly (`print-color-adjust: exact`); sections and post cards avoid page breaks; the wall prints at 4 columns without "View on" buttons; the scorebug title drops to 64px; the passport hides its buttons and keeps each analysis page unbroken.

## Elevation & Depth

Flat by default. Depth comes from tonal bands (ink against white against linen) and hairline rules, not from shadow. Shadows appear only on state or on floating layers.

### Shadow Vocabulary
- **Hover lift** (`box-shadow: 0 14px 30px rgba(18,18,18,.18)` with `translateY(-2px)`): campaign list rows on hover; the catalogue card uses `0 12px 32px rgba(18,18,18,.1)`.
- **Floating panel** (`box-shadow: 0 24px 60px rgba(18,18,18,.22), 0 2px 8px rgba(18,18,18,.08)`): filter dropdown panels.
- **Active marker** (`box-shadow: 0 6px 16px rgba(18,18,18,.18)`): the current-stage gantt bar only.
- **Media tag** (`box-shadow: 0 2px 8px rgba(0,0,0,.18)`): white platform tags sitting on photos.
- **Ruled impression** (`box-shadow: inset 0 0 0 3px <paper>, inset 0 0 0 4px currentColor`): the double rule inside stamps and seals. Not elevation; it is the printed-ink border.

### Named Rules
**The Flat-At-Rest Rule.** Nothing on a band carries a resting drop shadow beyond a 1 to 2px whisper; lift is a hover response.

## Shapes

Two families. Every control is a full pill (999px): buttons, chips, signal pills, verdict pill, links, handles, inputs. Containers use soft rectangles: 20px for cards, panels, podium blocks and campaign rows; 28px for the large surfaces (passport data page, sealed state, catalogue cards, modals); 12px for stamps, rail steps and logo plates; 6 to 8px for bar tracks and gantt bars. Avatars and seals are circles.

Borders are 1px hairlines in the rule colour; the passport's analysis pages open on a 2px ink rule. Stamps use a 2px border plus an inset double rule. Rotation is reserved for pressed marks: the verdict pill (-3deg), seal (-12deg, -8deg on mobile), stamps (alternating -3, 2, -1deg).

## Components

### Buttons
Confident and loud, always Bebas, always pill.
- **Shape:** full pill (999px), minimum 44px tall (46 to 54px for the big ones).
- **Primary (lime):** lime fill, ink text, 16px 32px. Hover inverts to ink fill with lime text.
- **Line:** transparent with a 1px ink border; hover fills ink with lime text.
- **Ghost on ink:** transparent, white text, white 35% border; hover turns border and text lime.
- **Focus:** 3px vivid-red outline, 2 to 3px offset (lime outline on ink surfaces).
- **"View on <platform>":** a full-width lime pill at the foot of each post card (46px, Bebas 19px) with the drawn platform mark; inverts on hover; hidden in print.

### Chips
- **Report filters:** white pill, 1px rule border, 42px tall, 14px DM Sans with optional platform mark. Pressed state: ink fill, lime text.
- **Catalogue filters:** ink pill at rest, lime with ink text when active or holding a value.

### Signal Pill (signature)
The only verdict device at row level. A small DM Sans 12px/600 pill with an 8px dot in currentColor before the word (Strong / Fair / Low). Soft tint backgrounds on light surfaces, translucent fills on ink. A neutral "none" variant in stone and graphite covers metrics without a benchmark.

### Scorebug (signature)
The ink opening band of the campaign report. Client logos on white 14px plates, an "x" in lime, then the HelloVoice mark; the campaign name at display size; a sub line in white at 70%. Beneath: a lime-outlined pill ticker (Bebas 22px, lime with white separators) carrying the LIVE marker, and the verdict pill. The verdict pill is Bebas up to 3rem, rotated -3deg, lime when ungraded and green, amber or red once judged, with a small uppercase caption "overall, against target".
- **LIVE pulse:** a 10px vivid-red dot whose ring expands from 0 to 12px and fades over 1.8s, `cubic-bezier(.2,.8,.2,1)`, infinite. The one animation in the report; removed under reduced motion.

### Scoreline
The results bar inside the scorebug: a ruled row (white 16% top and bottom) of definition cells, each a 12px uppercase term over a Bebas figure, divided by white 12% verticals, each with an optional signal pill. Two columns under 700px.

### Stage Rail and Gantt
- **Rail:** a horizontal row of 12px-radius stage cells (Bebas 19px name over 13px detail). Pending: stone. Done: green tint, green text. Active: ink with lime title. Scrolls horizontally when tight.
- **Gantt:** a 260px name column and a dated lane; 22px bars at 6px radius. Pending stone, done green, active ink with lime text and the active shadow. A 2px vivid-red "today" line with an uppercase label. Under 700px the lanes go and each stage becomes a list row with its dates.
- **Delivery slots:** one 14px block per contracted post: ink when delivered, lime for extras, stone when pending (inverted to lime and white on the scorebug).

### Post Card
White card, 20px radius, 1px rule border, 4:5 media in ink. A white platform tag pinned top-left on the photo, the signal pill top-right. Body: avatar and handle, a three-up figure list (11px label over 17px bold), then the "View on <platform>" button pinned to the bottom. A lime drawn platform mark stands in when there is no thumbnail.

### Leaderboard and Podium
Set on an ink section. Three podium blocks (1fr 1.15fr 1fr, winner centre and taller) on translucent white; the winner carries a lime 10% tint and lime 40% border. Each has a circular photo ringed in its medal metal, a drawn SVG medal hanging over the top edge, a Bebas name and a 52px lime score. Below, a horizontally scrolling table: uppercase 12px heads, right-aligned figures, drawn SVG medals for ranks 1 to 3, a 90px lime score bar per row.

### Bullet Bar (against target)
Three columns (200px name, track, 220px figure): a 26px stone track at 8px radius, a fill coloured by verdict, and a 3px ink target mark extending 6px above and below with its value labelled. Stacks under 1000px.

### Panels and Panel Bars
White panels at 20px radius on linen (or ruled on white), headed by an uppercase 12 to 13px label. Rows are label, 10px pill track with ink fill (custom colour in the passport), and a bold figure. Rows carry drawn platform marks or real flag images (flag-icons, 22x16 with 2px radius). Stacked share bars are 18 to 26px pills with a swatch key.

### Passport Data Page (signature)
A linen block at 28px radius with a faint concentric security pattern (repeating radial rule at 3.5% ink). Photo at 4:5 on the left (180 to 280px), fields on the right: a 13px uppercase type line, the name at display size, white handle pills with platform marks (inverting to ink and lime on hover), and a ruled definition list of Bebas 28px values. Single column under 820px.

### Seal
A 128px circle rotated -12deg in the data page's top-right, Bebas 20px with a small DM Sans date. A 3px border plus an inset double rule. "Analysed": lime fill, ink rules. "Sealed": linen with ink rules. In flow at 92px under 820px.

### Sealed State
When no analysis is on file: an ink block at 28px radius with a dark cover card (200px, 3:4, lime 25% border, drawn lock mark, "Talent passport" in lime Bebas), a headline, a note in white at 72%, and a 54px lime "Request" pill. Once requested the button disables to lime 25% and a lime confirmation line appears.

### Audience Stamps (signature)
One stamp per audience country: white, 12px radius, 2px ink border with an inset double rule, a real flag image (38x28) spanning two rows, a Bebas 34px share and a 12px uppercase country name. Alternating rotation (-3, 2, -1deg). The leading country is lime, wider (210px) and set at 46px.

### Inputs / Fields
- **Gate input:** transparent pill on ink, white 30% border, centred text tracked 0.12em, 260px; focus turns the border lime with no outline glow.
- **Form inputs (catalogue modal):** white, 1px ink 20% border, 12px radius; focus darkens the border to ink.

### Navigation
A top bar with the HelloVoice logo (132px) left and outlined white link pills right (44px, 15px DM Sans 500, rule border darkening to ink on hover). Under 820px the passport's links scroll horizontally in one row.

### Platform Marks
Drawn line icons (24 viewBox, 1.6 to 1.7 stroke, currentColor) for Instagram, TikTok, Snapchat, YouTube and others, shared via `assets/js/hv-icons.js`. On catalogue cards they sit in brand-coloured circles; in the report and passport they inherit text colour.

## Do's and Don'ts

### Do:
- **Do** open every client surface with the ink passcode gate and a Bebas title, then alternate white, ink and linen full-bleed bands.
- **Do** set every figure in Bebas over a 12 to 13px uppercase DM Sans term, ruled off by 1px hairlines.
- **Do** use green, amber and red only to state a verdict (signal pill, verdict pill, bullet fill) or a completed stage; draw neutral data in ink, lime or stone.
- **Do** keep every control a full pill at 44px minimum, with lime-to-ink inversion on hover and a 3px vivid-red focus outline on light surfaces.
- **Do** use drawn platform marks from the shared icon set and real flag images for countries.
- **Do** keep the LIVE pulse the only continuous animation in the report and stop it under reduced motion.
- **Do** keep reports printable: exact colours, gate and controls hidden, sections unbroken.

### Don't:
- **Don't** put a kicker or eyebrow label above a heading; the heading names the section on its own.
- **Don't** mark cards, rows or panels with a coloured side border; separation is by band colour and hairlines.
- **Don't** use green, amber or red as decoration, chart series colour or brand accent; vivid orange is the catalogue ticker's band, not a "moderate" colour.
- **Don't** build metrics as icon tiles or a tabbed analytics dashboard; use the scoreline, ruled figure lists, bullet bars and panel bars.
- **Don't** use emoji or text glyphs for platforms or countries.
- **Don't** add resting drop shadows or hard offset shadows to cards; lift appears only on hover or floating panels.
- **Don't** introduce a third typeface or set body sentences in Bebas.
