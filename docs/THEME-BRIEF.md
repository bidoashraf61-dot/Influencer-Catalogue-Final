# HelloVoice — theme brief

Everything below is read from the built site, not invented. Give this to whoever
(or whatever) builds the next page and it should come out matching.

---

## 1. Type

| role | face | notes |
|---|---|---|
| Headings | **Bebas Neue** (`Bebasneue, Arial, sans-serif`) | condensed, all-caps by nature, very tight |
| Body | **DM Sans** (`"DM Sans", Arial, sans-serif`) | |
| Embedded | `HV Display` / `HV Text` | base64 in `assets/css/type.css` |

Scale — all fluid, all `clamp()`:

```
h1            19vw                                        /* viewport-driven, enormous */
h2            clamp(3.75rem, -0.1942rem + 16.8285vw, 20rem)
h3            clamp(2.75rem,  1.4757rem +  5.4369vw,  8rem)
h4            clamp(2rem,     1.2112rem +  3.3657vw,  5.25rem)
h5            clamp(1.75rem,  1.5376rem +  0.9061vw,  2.625rem)
display-200   clamp(3rem,     0.6942rem +  9.8382vw, 12.5rem)
```

Weights available: 400, 500, 600, 700, 800, 900. Heading line-height is `1`.

**The single most important type rule:** headings are *huge* — an h2 renders at
285px on desktop. Anything placed beside a heading must be scaled to match, or it
reads as a stray sticker. This has been the source of the most rework on this project.

---

## 2. Colour

```css
--black-primary:   #000000
--black-secondary: #121212   /* "ink" — the working dark */
--gray:            #383838
--white:           #ffffff
--linen:           #e9dcd2   /* the warm light neutral */
--vivid-red:       #ee1515   /* section accent */
--vivid-red-active:#d10000
--vivid-orange:    #ff691e   /* ticker bands */
--yellow:          #fdbc53
                   #e8ff76   /* lime — tags and active filter chips (not yet a var) */
--section-accent:     #ee1515
--section-accent-ink: #c11212
```

**Alternating section grounds:** sections alternate `#FFFFFF` and `#E9DCD2`
(`GROUP_TONES` in `build/helv_content.py`). Keep this rhythm on new pages.

Lime `#e8ff76` is only ever used on ink or another dark ground — it is unreadable
on white or linen. Ink text on a lime pill is the standard tag treatment.

---

## 3. Layout

```css
--_layout---container:      1680px
--_layout---padding-global: 5%
```

Every section follows:

```html
<section class="my_section">
  <div class="padding_global">
    <div class="container">
      …
    </div>
  </div>
</section>
```

Full-bleed elements (ticker bands, separators) break out with:

```css
width: 100vw; margin-left: calc(50% - 50vw);
```

**Spacing primitives** — use these, don't invent values:
`0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 60, 64, 68, 72, 76, 80, 100, 120px`

**Radii:** `sm 12–20 · md 16–30 · lg 16–40 · xl 32–100 · 999px pill · 100% circle`

**Breakpoints:** `991px` (tablet) · `767px` (mobile) · `600 / 560px` (small phone).
There is no desktop-up breakpoint — desktop is the base, and everything is a
`max-width` override.

---

## 4. Page skeleton

```
nav.nav_menu
  └ nav_menu_wrapper › nav_link_circle + nav_link_text_wrap
section  (hero — stamps data-hero-tone="dark|light")
section  (× n, alternating #FFFFFF / #E9DCD2)
section.client_banner_section   (logo marquee)
section.cta_section
footer.footer
  └ footer_top_wrapper › footer_links › footer_link_col × 3
  └ footer_cta · footer_socials · footer_bottom_wrapper · footer_legal_corner
```

`data-hero-tone` on `<body>` tells the nav whether to start in white or ink. It
must be stamped **last** in the build, after all other passes.

---

## 5. Components

**Section heading** — a lime rotated pill above a giant title:
```html
<div class="section_header">
  <div class="floating_text">FILM &amp; IMMERSIVE</div>
  <h2>Our Work</h2>
</div>
```
The pill is ink text on `#e8ff76`, rotated ~-15°. Scale it to the title — 40px
against a 285px heading is too small.

**Group heading** — the red-rule idiom used down the works page:
```css
.work_group_head::before { content:""; width:3rem; height:3px;
  border-radius:2px; background: var(--section-accent); }
.work_group_title { color: var(--section-accent); }
```

**Cards** — ratio-driven, stamped `data-ratio="16:9"` or `"9:16"`:
```css
.project_image.is-16-9 { aspect-ratio: 16/9 }
.project_image.is-9-16 { aspect-ratio: 9/16 }
```
Never force a portrait film into a landscape box — it letterboxes and the client
will (correctly) call it cropped.

**Filter chips** — pill (`999px`), ink panel ground, lime when active, `aria-pressed`.

**Ticker / marquee bands** — orange `#ff691e`, full-bleed, Bebas caps, asterisk
separators between phrases.

**Buttons** — `.link-primary` / `.link-secondary`, pill, fill animation on hover
with the label colour animating alongside the fill.

---

## 6. Motion

GSAP + ScrollTrigger + Lenis smooth scroll, all in `assets/js/motion.js`.

- scroll reveals, split-character heading animation, marquee tickers, odometer counters
- `prefers-reduced-motion: reduce` is honoured in 13 separate blocks — match this
- **no hover zoom on thumbnails.** This is deliberate and was asked for explicitly.
  Avoid GSAP handlers that write inline transforms on cards; CSS cannot outrank them.

---

## 7. Accessibility floor

- **44×44px minimum tap target** below 991px — enforced on tags, links, footer
  links, social icons, the menu trigger
- 4.5:1 contrast minimum
- `aria-pressed` on filters, `aria-expanded` on the menu, keyboard (Enter/Space) on
  the hamburger
- no horizontal scroll at any width

---

## 8. Build

```bash
python3 build/clone.py
```

Regenerates `site/` from the reference. Content lives in `build/helv_content.py`
(sections, tones, tags, cards) and `content/projects.json`. CSS and JS are
cache-busted with a sha1 `?v=` stamp — **the browser will happily serve a stale
stylesheet**, so always verify with a fresh query string.

Add a new page by writing its builder alongside `service_page.py` /
`influencer_page.py` / `technology_page.py` and registering it in `clone.py`.

---

## 9. Voice

Confident, short, declarative. Headings are one or two words in caps. No
exclamation marks. Arabic appears alongside English in client work and must not be
transliterated or reordered.
