/* Ariyana Studio clone — behaviour layer.
 *
 * The reference runs two Webflow runtimes: IX2 (the older interaction engine,
 * which drives the hovers) and IX3 (Webflow's newer GSAP-backed scroll
 * animations, hooked through the data-* attributes in the markup). Neither is
 * portable, so both are rebuilt here.
 *
 * Nothing below is guessed. Hover values come from the live IX2 config
 * (`Webflow.require('ix2').store.getState().ixData`); the scroll tracks come
 * from measured progress -> transform curves; the element list comes from the
 * reference's own pre-paint hide rule, which enumerates every animated hook.
 * See docs/REFERENCE-ANIMATIONS.md for the full table.
 */
(function () {
  "use strict";

  var html = document.documentElement;
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var DESKTOP = "(min-width: 992px)";          // Webflow's `main` breakpoint
  var desktop = window.matchMedia(DESKTOP);

  gsap.registerPlugin(ScrollTrigger);
  var hasSplit = typeof SplitText !== "undefined";
  if (hasSplit) gsap.registerPlugin(SplitText);

  /* The stylesheet keeps every animated element at visibility:hidden until
   * html carries .w-mod-ix3. Reveal as soon as initial states are set, and
   * again on a failsafe timer so a script error can never strand the page. */
  function reveal() { html.classList.add("w-mod-ix3"); }
  setTimeout(reveal, 2000);
  if (reduced) reveal();

  /* Webflow's named easings. */
  var EASE = {
    "": "none", ease: "power1.inOut", outBack: "back.out(1.7)", outSine: "sine.out",
    outQuad: "power1.out", outCubic: "power2.out", outQuart: "power3.out",
    inOutCubic: "power2.inOut", inOutQuart: "power3.inOut"
  };
  var e = function (k) { return EASE[k] || k || "none"; };

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  function hover(el, over, out) {
    el.addEventListener("mouseenter", over);
    el.addEventListener("mouseleave", out);
    el.addEventListener("focusin", over);
    el.addEventListener("focusout", out);
  }

  /* ------------------------------------------------------------ smooth scroll
   * The reference's own Lenis configuration, verbatim. */
  var lenis = null;
  if (!reduced && typeof Lenis !== "undefined") {
    lenis = new Lenis({ smooth: true, lerp: 0.1, wheelMultiplier: 1, infinite: false });
    lenis.on("scroll", ScrollTrigger.update);
    gsap.ticker.add(function (t) { lenis.raf(t * 1000); });
    gsap.ticker.lagSmoothing(0);
  }

  /* --------------------------------------------------------------- splitting
   * SplitText, wrapped so a failure degrades to "no animation" rather than
   * "invisible text". */
  function split(el, type, mask) {
    if (!hasSplit || reduced) return null;
    try {
      /* Characters are split as "words,chars", never "chars" alone. Each
       * character becomes an inline-block, so without word wrappers around
       * them the browser may break a line between any two letters — which is
       * how ARIYANA STUDI/O ended up with its O on the next line. The word
       * elements keep each word atomic. It is also what the reference does:
       * its four-word heading reports 28 split nodes, 4 words + 24 chars.
       *
       * Masking is per-call. The reference's *scroll* headings compute
       * overflow:visible and their characters visibly cross the line above as
       * they drop in — so no mask there. The load intro is the opposite: its
       * timeline declares splitText {type:"chars", mask:"chars"}, so those
       * characters rise out from behind a clip. */
      var s = new SplitText(el, {
        type: type === "chars" ? "words,chars" : type,
        mask: mask || undefined,
        wordsClass: "gsap_split_word", charsClass: "gsap_split_letter",
        linesClass: "gsap_split_line"
      });
      return s[type] && s[type].length ? s : null;
    } catch (err) { return null; }
  }

  /* ---------------------------------------------------------- reveal safety
   * Reveals start at opacity 0, so one that never runs leaves its content
   * invisible rather than merely unanimated. Every one registers here.
   *
   * The rescue has to be narrow. An earlier version force-completed anything
   * within 1.5 viewports at the four second mark, which meant a visitor who
   * scrolled during those first seconds arrived at sections already revealed —
   * the animation was not lost, it had been skipped. So the only thing that
   * counts as stuck is a reveal whose trigger has *already passed its start*
   * while its timeline is still sitting at zero. Anything merely approaching
   * the viewport is left alone to play normally.
   *
   * A scroll-driven reveal has no trigger to consult only when it is the hero
   * intro, which plays on load; that one is snapped on the plain timer. */
  var reveals = [];
  function reveal_(el, tl, onLoad) {
    reveals.push({ el: el, tl: tl, onLoad: !!onLoad });
  }

  function rescueReveals() {
    reveals.forEach(function (r) {
      if (r.tl.progress() !== 0) return;
      if (r.onLoad) { r.tl.progress(1); return; }
      var st = r.tl.scrollTrigger;
      if (st && st.progress > 0) r.tl.progress(1);
    });
  }
  /* check a few times: a trigger can be created late, and a slow connection
     can delay the fonts the split depends on */
  [4000, 8000, 14000].forEach(function (t) { setTimeout(rescueReveals, t); });

  /* ------------------------------------------------- preloader + hero intro
   * One timeline, read verbatim from the reference's IX3 timeline t-45657481,
   * fired by its interaction i-99a118f3 on `wf:load` (home page only). Every
   * position, duration, stagger and ease below is the reference's own; the
   * ease indices resolve against Webflow's ordered ease table, where 15 is
   * back.inOut, 8 power3.out, 6 power2.inOut, 3 power1.inOut and 2 power1.out.
   *
   *   0.05  [data-preloader-logo]  chars, masked   y -100% -> 0
   *                                dur 1,   stagger amount .4,  back.inOut
   *   1.44  .preloader                             y 0% -> -120%
   *                                dur 1,                        power2.inOut
   *   1.60  .hero_image   — REMOVED, see below: the character is static
   *   2.57  [data-hero-title]      chars, masked   y -100% -> natural
   *                                dur 1,   stagger amount .5,  back.inOut
   *   3.46  [data-hero-subtitle]   chars, masked   y -100% -> natural
   *                                dur 1,   stagger amount .5,  back.inOut
   *   4.06  [data-hero-text]       chars, masked   y -100% -> natural
   *                                dur .8,  stagger amount .4,  power3.out
   *   4.89  .hero_social_links                     opacity 0, y 30 -> natural
   *   5.05  .hero_stat                             opacity 0, y 30 -> natural
   *
   * The panel is the only part that gets extra safety the reference does not
   * have: it is a full-screen black cover, so a stalled ticker or a thrown
   * error anywhere above must never be able to leave it in place. A plain
   * setTimeout (which keeps running when rAF does not) hides it outright.
   */
  (function pageIntro() {
    var pre = $(".preloader");
    var title = $("[data-hero-title]");
    var image = $("[data-hero-image], .hero_image");
    if (!pre && !title) return;

    function hardHide() {
      if (!pre) return;
      pre.style.display = "none";
      html.classList.remove("is-loading");
    }

    if (reduced) {                       // no motion: show the page, skip it all
      hardHide();
      return;
    }

    if (pre) {
      gsap.set(pre, { yPercent: 0, visibility: "visible" });
      html.classList.add("is-loading");
    }

    var tl = gsap.timeline({
      onComplete: function () { hardHide(); ScrollTrigger.refresh(); }
    });

    /* The reference splits its wordmark into characters and rises them in.
       HelloVoice's loading mark is the brand's own animation instead, so the
       panel holds while that plays and the film fades up rather than type
       sliding. Everything after this keeps the reference's beats. */
    var logo = $("[data-preloader-logo]");
    var vid = $(".preloader_video");
    if (vid) {
      tl.from(vid, { opacity: 0, scale: 0.94, duration: 0.5, ease: "power2.out" }, 0.05);
      var endorse = $(".preloader_endorse");
      if (endorse) tl.from(endorse, { opacity: 0, y: 10, duration: 0.5 }, 0.5);
    } else if (logo) {
      logo.style.overflow = "hidden";
      var art0 = logo.firstElementChild || logo;
      tl.from(art0, { yPercent: -100, duration: 1, ease: "back.inOut" }, 0.05);
    }

    /* The reference lifts the panel at 1.44s. Ours waits for the logo film:
       HOLD is when the panel starts moving and SHIFT carries every later beat
       with it, so the hero sequence keeps the reference's rhythm relative to
       the panel rather than to the clock. Capped at 3.4s — a loading screen
       that outstays the content it covers is the worse failure. */
    var HOLD = vid ? 3.4 : 1.44;
    var SHIFT = HOLD - 1.44;
    if (pre) tl.to(pre, { yPercent: -120, duration: 1, ease: "power2.inOut" }, HOLD);

    /* The reference blooms its hero image open from a sliver here — scaleX .3
       / scaleY .2 over 1.5s, as the panel lifts off it. The client's call is
       that the character does not animate: he is simply there when the panel
       goes. The beat is left empty rather than retimed, so everything after it
       keeps the reference's rhythm. */

    /* SplitText rebuilds each heading and stamps its own aria-label from the
       raw text, which runs the lockup together as "HELLOVOICEStudio". Keep the
       authored label and put it back afterwards. */
    function chars(sel, at, dur, amount, ease) {
      var el = $(sel);
      if (!el) return;
      var label = el.getAttribute("aria-label");
      var sp = split(el, "chars", "chars");
      if (label) el.setAttribute("aria-label", label);
      if (!sp) return;
      tl.from(sp.chars, {
        yPercent: -100, duration: dur, stagger: { amount: amount }, ease: ease
      }, at);
    }

    chars("[data-hero-title]", 2.57 + SHIFT, 1, 0.5, "back.inOut");
    chars("[data-hero-subtitle]", 3.46 + SHIFT, 1, 0.5, "back.inOut");
    chars("[data-hero-text]", 4.06 + SHIFT, 0.8, 0.4, "power3.out");

    var social = $(".hero_social_links"), stat = $(".hero_stat");
    if (social) tl.from(social, { opacity: 0, y: 30, duration: 0.5, ease: "power1.out" }, 4.89 + SHIFT);
    if (stat) tl.from(stat, { opacity: 0, y: 30, duration: 0.5, ease: "power1.out" }, 5.05 + SHIFT);

    /* plays on load, so it has no trigger to consult */
    reveal_(title || image || pre, tl, true);

    /* Exposed for verification only — the page never reads this. It is the
       only way to check the intro's keyframes in a throttled/headless context,
       where rAF does not advance and the timeline cannot be observed live. */
    window.__intro = tl;

    /* Last resort, deliberately outside GSAP. */
    setTimeout(hardHide, 9000);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && tl.progress() === 0) tl.progress(1);
    });
  })();


  /* ------------------------------------------------------- works grid
   * Two-column masonry with true aspect ratios — measured off
   * vimeo.com/hellovoice, which is the layout the client asked for.
   *
   * What that page actually does (measured, not assumed): two columns at 571px
   * on a 1710px viewport, every tile at its own natural ratio — 16:9 and 9:16
   * both present, object-fit cover with rendered ratio equal to natural, so
   * nothing is cropped — and the occasional tile spanning both columns.
   *
   * Cards are placed into whichever column is currently shortest rather than
   * alternating. That is what keeps the two columns near the same length, and
   * it is the difference between a tidy bottom edge and the ragged one a naive
   * masonry produces.
   *
   * Absolute positioning rather than CSS columns: columns reflow content in
   * document order down each column in turn, which would scatter a section's
   * films rather than reading across, and it gives no control over balancing.
   */
  (function worksGrid() {
    var lists = $$(".project_listing");
    if (!lists.length) return;

    function ratioOf(card) {
      var r = card.getAttribute("data-ratio");
      if (r === "9:16") return 9 / 16;
      if (r === "16:9") return 16 / 9;
      var img = $("img", card);
      if (img && img.naturalWidth) return img.naturalWidth / img.naturalHeight;
      return 16 / 9;
    }

    function layout(list) {
      var cards = $$(".project_item", list).filter(function (c) {
        return !c.hasAttribute("hidden");
      });
      if (!cards.length) return;

      var cs = getComputedStyle(list);
      var gap = parseFloat(cs.columnGap || cs.gap) || 24;
      var W = list.clientWidth;
      if (!W) return;

      var n = W < 700 ? 1 : 2;                    /* Vimeo runs two */
      var colW = Math.floor((W - gap * (n - 1)) / n);
      var heights = new Array(n).fill(0);

      cards.forEach(function (card) {
        /* shortest column wins — this is what balances the two */
        var col = heights.indexOf(Math.min.apply(null, heights));
        var media = $(".project_image", card);
        var mediaH = Math.round(colW / ratioOf(card));

        card.style.position = "absolute";
        card.style.width = colW + "px";
        card.style.left = (col * (colW + gap)) + "px";
        card.style.top = heights[col] + "px";
        if (media) media.style.height = mediaH + "px";

        /* the caption's height is only knowable once it has wrapped */
        heights[col] += card.offsetHeight + gap;
      });

      list.style.position = "relative";
      list.style.height = (Math.max.apply(null, heights) - gap) + "px";
      list.classList.add("is-justified");
    }

    function layoutAll() { lists.forEach(layout); }

    layoutAll();
    window.addEventListener("load", layoutAll);
    $$(".project_listing img").forEach(function (img) {
      if (!img.complete) img.addEventListener("load", layoutAll, { once: true });
    });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(layoutAll);
    var t;
    window.addEventListener("resize", function () {
      clearTimeout(t); t = setTimeout(layoutAll, 120);
    }, { passive: true });
    document.addEventListener("click", function (e) {
      if (e.target.closest(".works_filter_button")) setTimeout(layoutAll, 60);
    });
  })();

  /* --------------------------------------------------------- hero character
   * Deliberately still.
   *
   * This used to lean and turn toward the cursor and breathe on a slow idle.
   * The client's call is that the hero character does not move at all — so the
   * cursor tracking, the idle float and their ScrollTrigger gate are gone
   * rather than merely disabled, and nothing here listens to pointermove.
   *
   * The cutout is a flat image, and the tracking never had real parallax on
   * his own features, which is what made it read as a skew rather than a turn.
   * If a moving character comes back it should come back as geometry, not as a
   * transformed photograph. */

  /* ------------------------------------------------------------ text reveals
   * data-text-reveal — the big statement. Word opacity scrubs across the
   * heading's own travel: start when its top hits the viewport bottom, finish
   * when its bottom reaches centre. scrub 1.2. (ScrollTrigger read live.) */
  $$("[data-text-reveal]").forEach(function (el) {
    var s = split(el, "words");
    if (!s) return;
    gsap.set(s.words, { opacity: 0.15 });
    gsap.to(s.words, {
      opacity: 1, stagger: 0.4, ease: "none", force3D: true, overwrite: false,
      scrollTrigger: { trigger: el, start: "clamp(top bottom)", end: "clamp(bottom center)", scrub: 1.2 }
    });
  });

  /* data-title-anim and data-text-anim — both split to words *and* chars, and
   * drop the CHARS in from one line-height above. No fade, and no clipping
   * mask: the reference's split wrappers compute overflow:visible, so the
   * characters visibly cross the line above on the way down.
   *
   * Sampled at 70ms across the trigger crossing, from a cold load. The
   * reference's own node counts give the split away: 28 for a four-word
   * heading (4 words + 24 characters), 53 for an eleven-word paragraph.
   *
   *   heading   y -68 (= -100%) -> dips to -71 -> overshoots +3 -> 0 by 910ms.
   *             Symmetric ±4.4% anticipation and overshoot: a back.inOut.
   *             Adjacent characters lag ~7px mid-flight, so stagger ~0.02s.
   *   paragraph y -28 (= -100%) -> 0 by ~630ms, no overshoot. The curve fits
   *             power2.out over ~0.53s with a much tighter stagger.
   *
   * Both fire at start "clamp(top 90%)", matching the reference's triggers. */
  /* CLIENT CHANGE — the reference holds opacity at 1 through the drop; the
   * brief asks every title to fade up from 0 as it falls. Logged as a
   * deliberate divergence in REFERENCE-AUDIT.md. The fade runs over the first
   * ~55% of the drop so the character has settled before it reaches full
   * strength, which keeps the back.inOut overshoot readable. */
  var FADE_IN = true;

  $$("[data-title-anim]").forEach(function (el) {
    /* Masked, and dropping in from ABOVE — the reference's direction.
     *
     * This was briefly flipped to +100. The reason at the time was that
     * characters travelling a full line height upward escaped into the section
     * overhead. That was true, but only because the mask did not exist yet.
     *
     * The mask is the actual fix: .gsap_split_letter-mask is overflow:clip, so
     * a character at yPercent -100 is clipped to its own line box and cannot
     * cross a section boundary by construction. Once that was in place the
     * direction flip was redundant, and all it did was invert the motion
     * against the reference — measured side by side, every unplayed heading
     * there parks at -100 while ours parked at +100. Same split, same masks,
     * same letter heights (239px and 102px on the service page); only the sign
     * differed. So it goes back. */
    var s = split(el, "chars", "chars");
    if (!s) return;
    var tl = gsap.timeline({
      scrollTrigger: { trigger: el, start: "clamp(top 90%)", once: true }
    });
    /* CLIENT CHANGE — rises from below rather than dropping from above.
     *
     * The reference drops its headings in from one line-height overhead, and
     * the mask clips each character to its own line box so it cannot cross a
     * section boundary. That is sound in the middle of a page. It is not sound
     * directly under a full-bleed film: the heading's line box begins a few
     * pixels below the video, so a character falling into place reads as
     * sliding out from behind the footage. Measured at 19px of clearance on
     * Influencer Campaigns before the section gained its own top padding.
     *
     * Rising from below starts the character at the bottom of its own line box
     * — away from whatever sits above the section — so the reveal reads as
     * content arriving rather than as something emerging from under the film.
     * Logged as a divergence from the reference in REFERENCE-AUDIT.md. */
    tl.from(s.chars, {
      yPercent: 100, duration: 0.9, ease: "power3.out", stagger: 0.022
    }, 0);
    if (FADE_IN) tl.from(s.chars, {
      opacity: 0, duration: 0.54, ease: "power1.out", stagger: 0.022
    }, 0);
    reveal_(el, tl);
  });

  $$("[data-text-anim]").forEach(function (el) {
    var s = split(el, "chars");
    if (!s) return;
    var tl = gsap.timeline({
      scrollTrigger: { trigger: el, start: "clamp(top 90%)", once: true }
    });
    /* Follows the heading's direction — a paragraph falling while the heading
       above it rises reads as two unrelated effects. */
    tl.from(s.chars, {
      yPercent: 100, duration: 0.55, ease: "power2.out", stagger: 0.008
    }, 0);
    if (FADE_IN) tl.from(s.chars, {
      opacity: 0, duration: 0.32, ease: "power1.out", stagger: 0.008
    }, 0);
    reveal_(el, tl);
  });

  /* The rotated annotation labels get slapped on over their heading.
   *
   * Two things were wrong before. It selected [data-floating-badge], but only
   * some of these carry that attribute — ten badges on the home page, four
   * with it — so most of them never animated at all. And the CSS rest state
   * carried `transform: ... !important`, which beats GSAP's inline style, so
   * even the selected ones ran a timeline against a property they could not
   * write. Both are fixed: every .floating_text is selected, and the rest
   * transform now wins on specificity instead.
   *
   * Timing is tied to the heading rather than to the badge's own position.
   * They overlap — the badge sits *on* the words — so triggering each
   * separately meant the sticker could land before the letters it covers had
   * arrived. Sharing the heading's trigger and its "top 90%" start, then
   * waiting 0.34s, puts the badge down just as the first characters finish
   * rising: the words appear, then the sticker goes on top of them. */
  $$(".floating_text").forEach(function (el) {
    /* The off-canvas menu carries one of these too. It has its own open/close
       reveal, so a scroll-triggered entrance would fight it — and the menu is
       closed at the moment the trigger fires anyway. */
    if (el.closest(".canvas_menu, .canvas_logo_wrapper")) return;

    var head = el.closest(".section_header, .tech_bank_head, .year_text_wrapper");
    var title = head && $("h1, h2, h3", head);

    var tl = gsap.timeline({
      scrollTrigger: {
        trigger: title || el,
        start: "clamp(top 90%)",     /* the headings' own start */
        once: true
      }
    });

    /* Rotating in from the other side of vertical is what sells it as a
       sticker being pressed on rather than a box fading up. GSAP reads the
       -15deg rest angle off the element and animates back to it. */
    tl.from(el, {
      scale: 0.55,
      rotation: "+=22",
      opacity: 0,
      duration: 0.62,
      ease: e("outBack"),
      transformOrigin: "50% 50%"
    }, title ? 0.34 : 0);

    reveal_(el, tl);
  });

  /* data-counter — the about page's stat columns roll up. */
  $$("[data-counter]").forEach(function (el) {
    var col = $(".stats_column", el) || el.firstElementChild;
    if (!col) return;
    gsap.from(col, {
      yPercent: -100, duration: 1.9, ease: "cubic-bezier(0.784,0.325,0.222,0.98)",
      scrollTrigger: { trigger: el, start: "clamp(top 90%)", once: true }
    });
  });

  /* --------------------------------------------------------- the year track
   * .about_track is 300vh with a sticky child; .year_wrapper slides left.
   * Measured at 1440x900: x runs +640 -> -2716, linear, scrub 0.8, across
   * start "top top" -> end "bottom 130%". Written against the viewport so it
   * holds at any width: the run opens with the first year at 44.44vw and
   * closes with the last year's right edge at 80.83vw. */
  (function yearTrack() {
    var track = $(".about_track"), wrap = $(".year_wrapper");
    if (!track || !wrap) return;
    gsap.matchMedia().add(DESKTOP, function () {
      gsap.fromTo(wrap,
        { x: function () { return window.innerWidth * 0.4444; } },
        {
          x: function () { return window.innerWidth * 0.8083 - wrap.scrollWidth; },
          ease: "none",
          scrollTrigger: {
            trigger: track, start: "clamp(top top)", end: "clamp(bottom 130%)",
            scrub: 0.8, invalidateOnRefresh: true
          }
        });
    });
  })();

  /* ------------------------------------------------- the why-choose track
   * The about page builds the same thing the year track does: a 300vh parent,
   * a sticky child, and a row of cards wider than the viewport that is
   * scrubbed left. Each .why_choose_item is width:100% in a nowrap flex row,
   * so three of them span ~3920px. The reference drives it with a
   * ScrollTrigger reading start "clamp(top top)", end "clamp(bottom 130%)",
   * scrub 0.8 — the year track's configuration exactly.
   *
   * Without it the section pins for 2700px showing only the first card, which
   * is why its corner graphic reads as oversized: it is the only thing on
   * screen. Unlike the year track this one starts flush left and ends with the
   * last card's right edge at the container's right edge. */
  (function whyChooseTrack() {
    var track = $(".why_choose_track");
    var row = $(".why_choose_items");
    if (!track || !row) return;
    gsap.matchMedia().add(DESKTOP, function () {
      var overflow = function () {
        return Math.max(0, row.scrollWidth - row.parentElement.clientWidth);
      };
      gsap.fromTo(row, { x: 0 }, {
        x: function () { return -overflow(); },
        ease: "none",
        scrollTrigger: {
          trigger: track, start: "clamp(top top)", end: "clamp(bottom 130%)",
          scrub: 0.8, invalidateOnRefresh: true
        }
      });
      return function () { gsap.set(row, { clearProps: "transform" }); };
    });
  })();

  /* ------------------------------------------------------- the team track
   * The about page's team section is another 300vh parent with a sticky
   * child, and nothing was driving it — 2700px of scroll with the cards
   * sitting still, which reads as the page having jammed.
   *
   * On the reference each card carries a static residual of exactly its own
   * height (`y = [0, 296, 196, 96]` against heights `[396, 296, 196, 96]`),
   * i.e. a `yPercent: 100` from-state: every card starts pushed down by one
   * of itself and rises into the staircase its margin-top defines. Scrubbed
   * across the track with the same `start / end / scrub` the other tracks
   * use, staggered so they arrive in sequence. */
  (function teamTrack() {
    var cards = $$(".team_card");
    if (!cards.length) return;

    gsap.matchMedia().add(DESKTOP, function () {
      /* Slide up on arrival — no pin, no scrub, and no opacity.
       *
       * The reference scrubs four cards inside a pinned 300vh track. That
       * frame is a fixed 100vh, so it can hold one row; with six people in two
       * rows the second row fell outside it and the last name was cropped by
       * the following section. Releasing the pin costs the scrubbed feel and
       * buys a layout that cannot crop.
       *
       * Each card still rises into place as it enters, staggered along its
       * row, and never changes opacity — the client's call is that a card must
       * always be visible, only ever moving. */
      var st = ScrollTrigger.batch(cards, {
        start: "top 88%",
        once: true,
        onEnter: function (batch) {
          gsap.from(batch, {
            yPercent: 40, duration: 0.85, ease: "power3.out",
            stagger: 0.09, overwrite: "auto"
          });
        }
      });
      return function () {
        st.forEach(function (t) { t.kill(); });
        gsap.set(cards, { clearProps: "transform" });
      };
    });
  })();

  /* --------------------------------------------------------- the work stack
   * data-work-item x4 under a 1500px perspective. Resting state is
   * y = 40i, scale = 1 - 0.06i. The scrubbed timeline holds for 1/16, then
   * runs three equal linear steps of 5/16 each. Per step the front card
   * rotates away (rotateX 0 -> 45deg, y 0 -> -792px), the next takes the front
   * slot (y 0, scale 1) and everything behind creeps up 20px / +0.06 scale.
   * Every number here was measured off the live site at 1/16 resolution. */
  (function workStack() {
    var track = $(".work_items_track");
    var cards = $$("[data-work-item]");
    if (!track || cards.length < 2) return;

    gsap.matchMedia().add(DESKTOP, function () {
      var state = cards.map(function (c, i) {
        var v = { y: 40 * i, scale: 1 - 0.06 * i };
        gsap.set(c, v);
        return { y: v.y, scale: v.scale };
      });

      var tl = gsap.timeline({
        defaults: { ease: "none", duration: 5 },
        scrollTrigger: {
          trigger: track, start: "clamp(top top)", end: "clamp(bottom bottom)",
          scrub: 0.8, invalidateOnRefresh: true
        }
      });

      for (var k = 0; k < cards.length - 1; k++) {
        var at = 1 + k * 5;                       // the 1/16 lead-in, then 5/16 per step
        tl.to(cards[k], { rotateX: 45, y: -792 }, at);
        tl.to(cards[k + 1], { y: 0, scale: 1 }, at);
        state[k + 1] = { y: 0, scale: 1 };
        for (var j = k + 2; j < cards.length; j++) {
          state[j] = { y: state[j].y - 20, scale: state[j].scale + 0.06 };
          tl.to(cards[j], { y: state[j].y, scale: state[j].scale }, at);
        }
      }
      tl.set({}, {}, 16);                          // hold the full 16 units

      /* Close the tail under the stack.
       *
       * The four card frames are not the same height — 907, 907, 488, 565 here,
       * because the projects carry a mix of landscape and 9:16 media. The
       * sticky frame takes its height from the first of them, so it is as tall
       * as the tallest card; but the card left resting in it at the end is the
       * last one. A 565px card in a 907px frame leaves 342px of empty frame
       * under it, and the section's own 150px of padding sits below that — the
       * white band between the last work card and the client logos.
       *
       * The frame is sized to the card that actually ends up in it, and the
       * track loses the same height so the scrub distance is unchanged. The
       * earlier, taller cards overflow the frame while they are on screen,
       * which costs nothing: they are absolutely positioned, the frame paints
       * nothing, and each has rotated and translated away before the frame's
       * bottom edge matters.
       *
       * Re-measured on refresh rather than computed once, so it survives a
       * resize and a font swap. */
      var frame = $(".work_items_wrapper");
      var frames = $$(".work_collection_list_wrapper");
      if (frame && frames.length) {
        var last = frames[frames.length - 1];
        var scrub = null;
        var fit = function () {
          frame.style.height = "";
          track.style.height = "";
          var h = last.offsetHeight;
          if (!h) return;
          if (scrub === null) scrub = track.offsetHeight - frame.offsetHeight;
          frame.style.height = h + "px";
          track.style.height = (scrub + h) + "px";
        };
        fit();
        ScrollTrigger.addEventListener("refreshInit", fit);
        ScrollTrigger.refresh();
      }
    });
  })();

  /* ----------------------------------------------------------- the showreel
   * IX2 a-17, SCROLL_PROGRESS over .showreel_track:
   *   32%  mask 50vw x 40vh, radius 40px; text at x 0, y -50%, opacity 0
   *   42%  text opacity 1
   *   60%  mask 100vw x 100vh, radius 0; text split to +/-34vw
   * held at the end value past 60%.
   *
   * Webflow measures that progress across the element's whole traversal —
   * 0% when its top is at the viewport bottom, 100% when its bottom is at the
   * viewport top — not across the pinned range. Confirmed against the live
   * site: the mask starts growing at scroll 12643 and finishes at 13519,
   * which is exactly 32% and 60% of that traversal. */
  (function showreel() {
    var track = $(".showreel_track"), mask = $(".showreel_video_mask");
    if (!track || !mask) return;
    var t1 = $(".showreel_text._1"), t2 = $(".showreel_text._2");

    /* IX2 event e-16 is registered for the `main` breakpoint only, and below
     * 991px the stylesheet lays the mask out as width:100% / height:auto.
     * Guard with matchMedia so the inline sizes are reverted on resize. */
    gsap.matchMedia().add(DESKTOP, function () {

      /* the split distance is a breakpoint value in the reference stylesheet
       * (34vw at main, then 25 / 22 / 15) — read it rather than hard-code it */
      function restX(el) {
        var m = /matrix\(([^)]+)\)/.exec(getComputedStyle(el).transform);
        return m ? parseFloat(m[1].split(",")[4]) : 0;
      }
      var x1 = t1 ? restX(t1) : 0, x2 = t2 ? restX(t2) : 0;

      /* Clamp the travel to the words we actually have.
       *
       * The reference splits "Play" and "Reel" — four letters each — so 34vw of
       * travel from opposite edges lands them either side of the frame with
       * room to spare. "Hello Voice" and "Behind the Scene" are 424px and
       * 633px at this size, and the same 34vw drove them 509px through each
       * other: the two lines rendered on top of one another as
       * "HELLO VOIBEHIND THE SCENE".
       *
       * `_1` sits at left:0 and travels right; `_2` at right:0 travelling left.
       * At a travel of t they span [t, t+w1] and [vw-t-w2, vw-t], so they stay
       * clear while 2t <= vw - w1 - w2 - gutter. Measured, not assumed, so it
       * holds for whatever the two words are changed to next. */
      if (t1 && t2) {
        var GUTTER = 96;
        var w1 = t1.getBoundingClientRect().width;
        var w2 = t2.getBoundingClientRect().width;
        var room = (window.innerWidth - w1 - w2 - GUTTER) / 2;
        if (room < Math.abs(x1)) {
          /* Below zero the pair cannot sit side by side at this size at all —
           * pin them to the edges and let the type scale down instead of
           * letting them cross. */
          var t = Math.max(0, room);
          x1 = t;
          x2 = -t;
        }
      }

      var tl = gsap.timeline({
        defaults: { ease: "none" },
        scrollTrigger: { trigger: track, start: "top bottom", end: "bottom top", scrub: true }
      });
      /* Clipped, not resized. The reference grows the mask's box from
         50vw x 40vh to 100vw x 100vh — but the wrapper, the player box and the
         iframe inside it all stay a constant 1710x962 the whole way, so the
         box change was only ever revealing more of something that never moved.
         Animating width/height to do that costs a layout on every scroll
         frame, and the thing being laid out contains a cross-origin iframe, so
         Vimeo's own document relayouts 60 times a second with it. That is the
         drag you feel scrolling through this section.

         Holding the mask at its final size and animating a centred inset
         instead produces the identical window — same centre, same edges, same
         corner radius — with no layout at all. Units match end to end so GSAP
         interpolates the numbers rather than swapping the strings. */
      /* Driven as one number, not as a clip-path string. Tweening the string
         directly does not survive: the browser normalises a symmetric
         `inset(a b a b)` down to the two-value `inset(a b)` in computed style,
         so GSAP read a two-value start and a four-value end, matched them up
         positionally and produced `inset(111px 177px 16px 0px)` halfway —
         the window sliding off centre with the corner radius dropped.
         `--reel-open` goes 1 -> 0 and the stylesheet composes the clip from
         it, so there is one number to interpolate and nothing to parse. */
      gsap.set(mask, { width: "100vw", height: "100vh", borderRadius: 0,
                       "--reel-open": 1 });
      tl.to(mask, { "--reel-open": 0, duration: 28 }, 32);
      if (t1 && t2) {
        gsap.set([t1, t2], { yPercent: -50, x: 0, opacity: 0 });
        tl.to([t1, t2], { opacity: 1, duration: 10 }, 32);
        tl.to(t1, { x: x1, duration: 28 }, 32);
        tl.to(t2, { x: x2, duration: 28 }, 32);
      }
      tl.set({}, {}, 100);          // hold the end state through the last 40%

      return function () {          // matchMedia cleanup: hand layout back to CSS
        gsap.set(mask, { clearProps: "width,height,borderRadius,--reel-open" });
        if (t1 && t2) gsap.set([t1, t2], { clearProps: "transform,opacity" });
      };
    });
  })();

  /* --------------------------------------------------------- the logo fan
   * IX2 a-3: the wrapper rotates 0 -> 360deg across the section's traversal.
   * IX2 a-7 / a-8: on entry each circle swings out to -36deg per index over
   * 1000ms inOutCubic. IX2 a-5 / a-6: hovering the copy lifts it to full
   * opacity and shrinks the fan to 0.8 over 500ms inOutQuart. */
  (function logoFan() {
    var sec = $(".leader_section"), wrap = $(".leader_circle_wrapper");
    if (!sec || !wrap) return;

    gsap.fromTo(wrap, { rotate: 0 }, {
      rotate: 360, ease: "none",
      scrollTrigger: { trigger: sec, start: "top bottom", end: "bottom top", scrub: true }
    });

    var fan = $$(".leader_circle_item");
    if (fan.length) {
      gsap.set(fan, { rotate: 0 });
      ScrollTrigger.create({
        trigger: sec, start: "top 80%", once: true,
        onEnter: function () {
          fan.forEach(function (el, i) {
            if (!i) return;
            gsap.to(el, { rotate: -36 * (fan.length - i), duration: 1, ease: e("inOutCubic") });
          });
        }
      });
    }

    /* The copy sits at opacity .5 on desktop and 1 below 991px — the
     * stylesheet's own values — and IX2 registers the hover for `main` only. */
    var content = $(".leader_section_content");
    if (content) {
      gsap.matchMedia().add(DESKTOP, function () {
        var over = function () {
          gsap.to(content, { opacity: 1, duration: 0.5 });
          gsap.to(wrap, { scale: 0.8, duration: 0.5, ease: e("inOutQuart") });
        };
        var out = function () {
          gsap.to(content, { opacity: 0.5, duration: 0.5 });
          gsap.to(wrap, { scale: 1, duration: 0.5, ease: e("inOutQuart") });
        };
        hover(content, over, out);
        return function () {
          content.removeEventListener("mouseenter", over);
          content.removeEventListener("mouseleave", out);
          content.removeEventListener("focusin", over);
          content.removeEventListener("focusout", out);
          gsap.set([content, wrap], { clearProps: "opacity,scale" });
        };
      });
    }
  })();

  /* ------------------------------------------------------------- marquees
   * Measured live: the solid CTA row runs -180.1 px/s, the stroked row
   * +180.1 px/s, the brands ticker +81.7 px/s. Each row holds two copies of
   * its content, so one copy's width is the loop distance. */
  function marquee(el, span, pxPerSec) {
    if (!span) return;
    var dir = pxPerSec < 0 ? -1 : 1;
    var from = dir < 0 ? 0 : -span;
    gsap.fromTo(el, { x: from },
      { x: from + dir * span, duration: span / Math.abs(pxPerSec), ease: "none", repeat: -1 });
  }
  /* width of one repeated copy, given how many copies the element holds */
  function copySpan(el, copies) {
    var kids = Array.prototype.slice.call(el.children);
    var n = Math.ceil(kids.length / copies), span = 0;
    for (var i = 0; i < n; i++) {
      span += kids[i].getBoundingClientRect().width +
        parseFloat(getComputedStyle(kids[i]).marginRight || 0);
    }
    return span;
  }
  if (!reduced) {
    /* The CTA rows each hold two copies of the headline: data-stroke="no" is
     * the solid row, "yes" the outlined one, running opposite ways. */
    var solid = $('[data-stroke="no"]'), stroke = $('[data-stroke="yes"]');
    if (solid && solid.parentElement) marquee(solid.parentElement, copySpan(solid.parentElement, 2), -180.1);
    if (stroke && stroke.parentElement) marquee(stroke.parentElement, copySpan(stroke.parentElement, 2), 180.1);

    /* The brands ticker repeats at the row level: two identical
     * .brands_ticker_row siblings sit end to end inside a clipped box, so one
     * row's width is the loop distance and both rows carry the same x. */
    $$(".brands_ticker_row").forEach(function (r) {
      marquee(r, r.getBoundingClientRect().width, 81.7);
    });

    /* ADDED — the works page's service banner. One row holding the service
     * list twice, so the loop distance is half the row's own scroll width.
     * Measured from scrollWidth, not the bounding box: the row overflows its
     * container, and the box would only report the visible slice. */
    $$(".project_ticker_row").forEach(function (r) {
      marquee(r, r.scrollWidth / 2, -90);
    });

    /* ADDED — the client logo banner. Same two-copy construction, run at the
     * brands ticker's speed so the page has one marquee tempo. Pauses on
     * hover so a visitor can actually look at a mark. */
    var track = $(".client_banner_track");
    if (track && track.children.length >= 2) {
      var span = track.children[0].getBoundingClientRect().width;
      marquee(track, span, -81.7);
      var tw = gsap.getTweensOf(track)[0];
      if (tw) {
        track.addEventListener("mouseenter", function () { tw.pause(); });
        track.addEventListener("mouseleave", function () { tw.resume(); });
      }
    }
  }

  /* --------------------------------------------------------------- hovers */

  /* IX2 a-20 / a-21 — a step icon scales to 1.05 over 500ms, ease, and the
   * step's info panel opens with it. The reference keeps that panel at
   * height 0 on desktop and lets it stand open below 991px, where there is no
   * hover; IX2 registers the event for `main` only. */
  gsap.matchMedia().add(DESKTOP, function () {
    var offs = [];
    $$(".step_item").forEach(function (item) {
      var icon = $(".step_icon", item);
      var info = $(".step_item_info_wrap", item);
      /* the collapsed state is CSS (see clone.css) so it cannot be reverted
       * out from under us; this only drives the open and close */
      /* The whole card is the hover target, not just the 60px icon — the
       * reference opens the panel from anywhere on the step, and a disc that
       * small is easy to miss. The icon still rotates so it reads as the
       * control it is. */
      var target = item;
      var over = function () {
        if (icon) gsap.to(icon, { scale: 1.05, rotate: 180, duration: 0.5, ease: e("ease") });
        if (info) gsap.to(info, { height: "auto", duration: 0.5, ease: e("outQuad") });
      };
      var out = function () {
        if (icon) gsap.to(icon, { scale: 1, rotate: 0, duration: 0.5, ease: e("ease") });
        if (info) gsap.to(info, { height: 0, duration: 0.5, ease: e("outQuad") });
      };
      hover(target, over, out);
      if (icon) {
        icon.setAttribute("tabindex", "0");
        icon.setAttribute("role", "button");
        icon.setAttribute("aria-expanded", "false");
        icon.addEventListener("click", function () {
          var open = icon.getAttribute("aria-expanded") === "true";
          icon.setAttribute("aria-expanded", open ? "false" : "true");
          (open ? out : over)();
        });
      }
      offs.push(function () {
        target.removeEventListener("mouseenter", over);
        target.removeEventListener("mouseleave", out);
        target.removeEventListener("focusin", over);
        target.removeEventListener("focusout", out);
        if (info) gsap.set(info, { clearProps: "height" });
        if (icon) gsap.set(icon, { clearProps: "transform" });
      });
    });
    return function () { offs.forEach(function (f) { f(); }); };
  });

  /* IX2 a-9 … a-16 (testimonials) and a-73 … a-80 (life images) — the pile.
   * Hovering a card lifts it to scale 1.1 / rotate 0 over 800ms outBack and
   * shoulders its neighbours aside by the offsets read from IX2. Leaving
   * settles everything over 600ms. Resting rotations alternate -3 / +5 deg. */
  /* The resting tilt is the reference stylesheet's own — .testimonial_card is
   * rotated -3deg and .card_two +5deg in CSS, which is why the entrance
   * timeline animates *to null* and still lands tilted. So it is read off the
   * elements rather than hard-coded: hover-out then returns each card to the
   * angle its own rule gives it, whatever that is, and nothing needs to be
   * re-listed here if the CSS changes. Populated by pile(). */
  var REST_ROT = [];
  var NUDGE = [                       // NUDGE[hovered][other] in px
    [null, 7, 5, 5],
    [-10, null, 8, 8],
    [-15, -8, null, 10],
    [-10, -8, -10, null]
  ];
  function pile(sel) {
    var items = $$(sel);
    /* The reference ships four cards and the IX2 nudge matrix is 4x4.
     * HelloVoice has three, so an exact-length test silently disabled the
     * whole hover behaviour; the matrix is read defensively instead. */
    if (items.length < 2) return;
    var nudge = function (i, j) { return (NUDGE[i] || [])[j] || 0; };
    /* Read before anything animates them, so this is the CSS angle. */
    REST_ROT = items.map(function (c) { return gsap.getProperty(c, "rotation") || 0; });
    /* Below 991px the stylesheet flattens the pile (transform: none) and IX2
     * does not register these events, so the rest rotations are desktop-only. */
    gsap.matchMedia().add(DESKTOP, function () {
      return function () { gsap.set(items, { clearProps: "transform" }); };
    });
    items.forEach(function (card, i) {
      hover(card, function () {
        if (!desktop.matches) return;
        gsap.to(card, { scale: 1.1, rotate: 0, duration: 0.8, ease: e("outBack") });
        items.forEach(function (o, j) {
          if (j !== i) gsap.to(o, { x: nudge(i, j), rotate: REST_ROT[j], duration: 0.8, ease: e("outBack") });
        });
      }, function () {
        if (!desktop.matches) return;
        gsap.to(card, { scale: 1, duration: 0.6, ease: e("outBack") });
        gsap.to(card, { rotate: REST_ROT[i], duration: 0.6, ease: e("ease") });
        items.forEach(function (o, j) {
          if (j !== i) gsap.to(o, { x: 0, duration: 0.6, ease: e("outBack") });
        });
      });
    });
  }
  pile("[data-slide-card]");

  /* data-slide-card entrance — read verbatim from the reference's own IX3
   * timeline t-f0abf957, not estimated:
   *
   *   targets  [data-slide-card]
   *   from     x 100vw, rotation 40deg, transformOrigin 100% 100%
   *   to       null (the element's natural resting state)
   *   timing   duration 1, stagger {amount: .4}, ease 14
   *   trigger  wf:scroll, start "top center", end "bottom top",
   *            scrub null, enter "play", enterBack/leave/leaveBack "none"
   *   gate     conditionalPlayback dont-animate on medium|small|tiny
   *
   * Ease 14 resolves to back.out against Webflow's own ordered ease table.
   * Two details that are easy to get wrong: the cards come in from the RIGHT
   * pivoting about their bottom-right corner (so they swing in like dealt
   * cards rather than sliding), and it PLAYS ONCE on enter — scrub is null, so
   * it is not tied to scroll position. Below 992px it must not run at all.
   */
  var pileWrap = $(".testimonial_cards") || $("[data-slide-cards]");
  if (pileWrap && !reduced && $$("[data-slide-card]").length) {
    gsap.matchMedia().add(DESKTOP, function () {
      var pileCards = $$("[data-slide-card]");
      var pileTl = gsap.timeline({
        scrollTrigger: { trigger: pileWrap, start: "clamp(top center)", once: true }
      });
      pileTl.from(pileCards, {
        x: "100vw", rotation: 40, transformOrigin: "100% 100%",
        duration: 1, stagger: { amount: 0.4 }, ease: "back.out"
      });
      reveal_(pileWrap, pileTl);
      return function () { gsap.set(pileCards, { clearProps: "transform" }); };
    });
    /* Under 992px nothing runs and nothing needs un-hiding: the cards are not
       in the stylesheet's pre-paint hide list, so they paint as laid out. */
  }

  /* --------------------------------------------------- sequential card entry
   * The catalogue, the campaign grid and the step lists had no entrance of
   * their own. Their headings animated, the content under them did not, so a
   * section arrived in two unrelated pieces — which is what reads as "the
   * timing is off" rather than any single animation being wrong.
   *
   * ScrollTrigger.batch is the right tool: it groups whatever crosses the
   * threshold in the same frame and staggers that group, so a row of cards
   * arrives as a row. Without it each card owns a trigger and they fire in
   * scroll order regardless of layout, which is what produced the overlapping,
   * out-of-sequence feel.
   *
   * once: true — these are entrances, not scrubbed states. Replaying them on
   * scroll-back is what makes a long page feel busy.
   */
  (function cardEntrances() {
    if (reduced || !ScrollTrigger.batch) return;

    [".tech_card", ".ig_card", ".ig_step", ".svc_tech_card", ".svc_cat_item"]
      .forEach(function (sel) {
        var items = $$(sel);
        if (!items.length) return;

        /* Anything already at or above the fold is shown outright. Hiding it
           and waiting for a trigger meant a visitor landing mid-page — or
           following an anchor — saw an empty section, and a fast scroll
           outran the batch entirely. Only what is genuinely below the fold
           gets an entrance. */
        var below = items.filter(function (el) {
          return el.getBoundingClientRect().top > innerHeight * 0.9;
        });
        if (!below.length) return;

        gsap.set(below, { opacity: 0, y: 26 });

        ScrollTrigger.batch(below, {
          start: "top 92%",
          once: true,
          batchMax: 8,
          onEnter: function (batch) {
            gsap.to(batch, {
              opacity: 1, y: 0, duration: 0.6, ease: "power3.out",
              stagger: 0.06, overwrite: true
            });
          }
        });

        /* Two safety nets, because "content you cannot see" is the worst
           failure mode on the page and a trigger is not a guarantee:
           - a sweep on scroll catches anything the batch skipped when the
             viewport jumped further than one screen;
           - a timer catches the case where triggers never ran at all. */
        function sweep() {
          var late = below.filter(function (el) {
            return +getComputedStyle(el).opacity < 0.05 &&
                   el.getBoundingClientRect().top < innerHeight;
          });
          if (late.length) {
            gsap.to(late, { opacity: 1, y: 0, duration: 0.4, stagger: 0.03, overwrite: true });
          }
        }
        var queued = false;
        addEventListener("scroll", function () {
          if (queued) return;
          queued = true;
          requestAnimationFrame(function () { queued = false; sweep(); });
        }, { passive: true });
        [1500, 4000, 9000].forEach(function (t) { setTimeout(sweep, t); });

        /* Posters and thumbnails change section heights as they decode, which
           moves every trigger below them. Without this the start positions are
           measured against a shorter page than the one the visitor scrolls. */
        window.addEventListener("load", function () { ScrollTrigger.refresh(); });

        window.addEventListener("hv:revealed", function () {
          gsap.to($$(sel).filter(function (el) {
            return !el.hidden && +getComputedStyle(el).opacity < 0.05;
          }), { opacity: 1, y: 0, duration: 0.4, stagger: 0.04, overwrite: true });
        });
      });
  })();

  /* ------------------------------------------------------------------ forms
   * Every form on the site is addressed to info@hellovoice.co.uk.
   *
   * A static site cannot send mail by itself — there is no server to post to.
   * Until an endpoint exists, submitting composes the message in the visitor's
   * own mail client, correctly addressed and with every field already filled
   * in. Nothing is silently dropped, and no third party sees the lead.
   *
   * To switch to a real backend later: set FORM_ENDPOINT to the POST URL and
   * this handler steps aside. The destination address lives in one place.
   */
  var FORM_TO = "info@hellovoice.co.uk";
  var FORM_ENDPOINT = "";        /* set this to a POST url to use a backend */

  $$("form").forEach(function (form) {
    if (FORM_ENDPOINT) {
      form.setAttribute("action", FORM_ENDPOINT);
      form.setAttribute("method", "post");
      return;
    }
    form.setAttribute("data-mailto", FORM_TO);
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var lines = [], subject = "Website enquiry — HelloVoice";
      $$("input,select,textarea", form).forEach(function (f) {
        if (!f.name || f.type === "submit" || f.type === "hidden") return;
        var label = (f.getAttribute("placeholder") || f.name).trim();
        var val = (f.value || "").trim();
        if (val) lines.push(label + ": " + val);
        if (/name/i.test(f.name) && val) subject = "Website enquiry — " + val;
      });
      if (!lines.length) return;
      var href = "mailto:" + FORM_TO
        + "?subject=" + encodeURIComponent(subject)
        + "&body=" + encodeURIComponent(lines.join("\n"));
      window.location.href = href;
      var note = form.querySelector(".form_sent");
      if (!note) {
        note = document.createElement("p");
        note.className = "form_sent";
        form.appendChild(note);
      }
      note.textContent = "Opening your mail app, addressed to " + FORM_TO + ".";
    });
  });

  /* ------------------------------------------------------- media scheduling
   * The video section stuttered on approach, and the cause was simple
   * over-subscription: the home page mounts two Vimeo background players (the
   * full-bleed film and the PLAY/REEL block, both the same reel) and four
   * looping service films, and every one of them was decoding from load
   * regardless of where the viewport was. Six simultaneous decodes while a
   * scrubbed transform runs is what a scroll janks on.
   *
   * So media is scheduled against the viewport:
   *   - local <video> plays only while on screen, and pauses when it leaves;
   *   - Vimeo iframes mount their src when they come within a screen of the
   *     viewport and unmount when they are two screens away, which frees the
   *     player process entirely rather than just pausing it.
   *
   * rootMargin is generous on entry so nothing is ever seen mid-buffer, and
   * hysteresis (1 screen in, 2 screens out) stops a player thrashing when a
   * visitor scrubs back and forth across the boundary. */
  (function mediaSchedule() {
    if (!("IntersectionObserver" in window)) return;

    /* --- local films: play in view, pause out of view --- */
    var vids = $$("video").filter(function (v) { return !v.closest(".preloader"); });
    if (vids.length) {
      var vio = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          var v = en.target;
          if (en.isIntersecting) {
            if (v.paused) { var q = v.play(); if (q && q.catch) q.catch(function () {}); }
          } else if (!v.paused) {
            v.pause();
          }
        });
      }, { rootMargin: "200px 0px" });
      vids.forEach(function (v) {
        v.preload = "none";        /* nothing downloads until it is wanted */
        vio.observe(v);
      });
    }

    /* --- Vimeo: mount and unmount the iframe --- */
    var frames = $$("iframe[src*='player.vimeo.com']").filter(function (f) {
      return !f.closest(".reel_lightbox");     /* the lightbox manages its own */
    });
    frames.forEach(function (f) {
      f.setAttribute("data-src", f.src);
      f.removeAttribute("src");
    });
    if (frames.length) {
      var fio = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          var f = en.target;
          if (en.isIntersecting) {
            if (!f.getAttribute("src")) f.src = f.getAttribute("data-src");
          }
        });
      }, { rootMargin: "300% 0px" });
      /* Three screens of lead-in, not one.
       *
       * Setting an iframe's src spins up a whole cross-origin player process:
       * document, network, codec init, first decode. At one screen of lead-in
       * that work landed while the section was arriving on screen, so the cost
       * was paid during the exact scroll it had to not disturb — felt as a
       * short stall over the showreel. Mounting three screens out moves the
       * expense to a moment when nothing is watching. */

      /* Unmounting is for pages that carry a lot of players. It is not worth it
       * for a handful.
       *
       * Widening the band to 600% was meant to stop a player being re-paid for
       * on every pass, and within one section it does. It cannot help when the
       * players are far apart: the home page has exactly two, the film section
       * at ~1.5k and the reel at ~16k, so any trip between them clears six
       * screens by a wide margin and unmounts the one behind you. Scrolling
       * back up then reboots the whole cross-origin player — document,
       * network, codec init, first decode — right as that section arrives.
       * That is the stall over the second video section.
       *
       * A background player that is already warm costs little to leave alone,
       * so below the threshold nothing is ever unmounted and the trip back up
       * is free. The catalogue pages, which carry dozens, keep the observer. */
      var UNMOUNT_ABOVE = 3;
      if (frames.length > UNMOUNT_ABOVE) {
        var off = new IntersectionObserver(function (entries) {
          entries.forEach(function (en) {
            if (!en.isIntersecting && en.target.getAttribute("src")) {
              en.target.removeAttribute("src");  /* frees the player process */
            }
          });
        }, { rootMargin: "600% 0px" });
        frames.forEach(function (f) { off.observe(f); });
      }

      frames.forEach(function (f) { fio.observe(f); });

      /* The showreel sits high on the home page — third section — so a visitor
         reaches it within a second or two of landing, often before an observer
         with a 300% margin has had a chance to fire on a short first paint.
         Mounting it on the first idle slot after load takes the cost while the
         page is still settling rather than mid-flick. */
      var idle = window.requestIdleCallback || function (fn) { return setTimeout(fn, 400); };
      idle(function () {
        var first = frames[0];
        if (first && !first.getAttribute("src")) {
          first.src = first.getAttribute("data-src");
        }
      }, { timeout: 2000 });

      /* Belt and braces. An IntersectionObserver callback is not guaranteed to
         run promptly in every context — a backgrounded or throttled tab can
         defer it — and the failure mode here is the showreel never appearing
         at all. A cheap geometric check on scroll covers that; it only ever
         mounts, never unmounts, so it cannot fight the observers above. */
      var pending = false;
      function sweep() {
        pending = false;
        frames.forEach(function (f) {
          if (f.getAttribute("src")) return;
          var r = f.getBoundingClientRect();
          if (r.top < innerHeight * 2 && r.bottom > -innerHeight) {
            f.src = f.getAttribute("data-src");
          }
        });
      }
      addEventListener("scroll", function () {
        if (!pending) { pending = true; requestAnimationFrame(sweep); }
      }, { passive: true });
      [1200, 3000, 6000].forEach(function (t) { setTimeout(sweep, t); });
    }
  })();

  /* ------------------------------------- influencer: campaign filter + more
   * One module because the two interact: "show more" reveals the next batch
   * *of whatever is currently filtered*, so the two cannot keep separate
   * counts. The grid holds all 86 tiles; `hidden` is the single source of
   * truth for what is on screen.
   *
   * Chips are real buttons carrying aria-pressed, so the announced state and
   * the painted state come from the same attribute and cannot drift. */
  (function influencerGrid() {
    var grid = $("#ig-grid");
    var more = $("[data-ig-more]");
    if (!grid) return;

    var cards = $$(".ig_card", grid);
    var chips = $$(".ig_chip");
    var step = more ? (parseInt(more.getAttribute("data-step"), 10) || 24) : cards.length;
    var count = more ? $(".ig_more_count", more) : null;
    var filter = "all";
    var shown = step;

    var empty = document.createElement("p");
    empty.className = "ig_empty";
    empty.hidden = true;
    empty.textContent = "No films in that campaign yet.";
    grid.parentNode.insertBefore(empty, grid.nextSibling);

    function matching() {
      return cards.filter(function (c) {
        return filter === "all" || c.getAttribute("data-campaign") === filter;
      });
    }

    function render() {
      var m = matching();
      cards.forEach(function (c) { c.hidden = true; });
      m.slice(0, shown).forEach(function (c) { c.hidden = false; });
      var left = Math.max(0, m.length - shown);
      empty.hidden = m.length !== 0;
      /* tell the entrance module that new tiles are now on screen */
      window.dispatchEvent(new Event("hv:revealed"));
      if (more) {
        more.hidden = left === 0;
        if (count) count.textContent = "(" + left + " left)";
      }
      ScrollTrigger.refresh();
    }

    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        filter = chip.getAttribute("data-campaign");
        shown = step;                       /* a new filter starts a new page */
        chips.forEach(function (c) {
          var on = c === chip;
          c.setAttribute("aria-pressed", on ? "true" : "false");
          c.classList.toggle("is-on", on);
        });
        render();
      });
    });

    if (more) {
      more.addEventListener("click", function () {
        shown += step;
        render();
      });
    }

    render();
  })();

  /* IX2 a / a-2 — a brands-grid cell washes to rgba(255,255,255,.8) over
   * 500ms and back to transparent black. */
  $$(".brands_grid .box").forEach(function (box) {
    hover(box,
      function () { if (desktop.matches) gsap.to(box, { backgroundColor: "rgba(255,255,255,0.8)", duration: 0.5 }); },
      function () { if (desktop.matches) gsap.to(box, { backgroundColor: "rgba(0,0,0,1)", duration: 0.5 }); });
  });

  /* The label swap. Every button in the reference prints its label twice
   * inside a `.button_text_wrapper` that clips: the first copy sits in place,
   * the second is absolutely positioned at top:100% just below it, and — for
   * the primary button — is coloured white. Hovering slides the pair up by one
   * line so the second copy takes the first's place.
   *
   * This is what makes the primary button legible once its ground turns
   * black. Without it the black first copy simply stays put and the label
   * disappears, which is exactly what happened here. */
  function labelSwap(btn) {
    var wraps = $$(".button_text_wrapper", btn);
    if (!wraps.length) return { over: function () {}, out: function () {} };
    var copies = wraps.map(function (w) {
      return Array.prototype.slice.call(w.children);
    });
    return {
      over: function () {
        copies.forEach(function (pair) {
          gsap.to(pair, { yPercent: -100, duration: 0.4, ease: e("outQuad") });
        });
      },
      out: function () {
        copies.forEach(function (pair) {
          gsap.to(pair, { yPercent: 0, duration: 0.4, ease: e("outQuad") });
        });
      }
    };
  }

  /* IX2 a-34 / a-35 — the primary button. Ground goes black over 350ms while
   * the underline flips white and sweeps to 1.3 over 500ms inOutCubic; the
   * return is delayed 500ms, exactly as IX2 has it. */
  $$("[data-button-primary], [data-button-primary-v2], .button_primary").forEach(function (btn) {
    var line = $("[data-button-line], [data-button-line-v2], .button_line", btn);
    var label = labelSwap(btn);
    /* The ground goes black on hover, so the label has to go white with it.
     *
     * IX2 never animated the label because the reference's buttons sit on pale
     * linen, where the CSS default already reads. On the work cards — which
     * ship a saturated colour behind them — the label stayed #121212 and
     * disappeared into the black fill at exactly the moment the pointer said
     * the thing was interactive.
     *
     * Driven here rather than in CSS because the fill itself is a GSAP tween:
     * keeping both halves of the same state change in one place means they
     * cannot fall out of step, and a stylesheet rule would have to out-specify
     * an inline style written every frame.
     *
     * Every copy of the label is collected — the template prints the word twice
     * for its roll, and styling only the first leaves the incoming copy dark. */
    var texts = $$("[data-button-text], [data-button-text-v2], .button_text, .button_text_v2", btn);
    hover(btn, function () {
      label.over();
      gsap.to(btn, { backgroundColor: "#000", duration: 0.35, ease: e("ease") });
      if (texts.length) gsap.to(texts, { color: "#fff", duration: 0.35, ease: e("ease") });
      if (line) {
        gsap.to(line, { backgroundColor: "#fff", duration: 0.35, ease: e("ease") });
        gsap.to(line, { scaleX: 1.3, duration: 0.5, ease: e("inOutCubic") });
      }
    }, function () {
      label.out();
      gsap.to(btn, { backgroundColor: "rgba(255,255,255,0)", duration: 0.35, delay: 0.5, ease: e("ease") });
      /* clearProps, not a hard-coded black: these buttons appear on light and
         dark grounds and each takes its resting colour from CSS. Setting a
         literal here would repaint a dark-ground button the wrong colour the
         first time the pointer left it. */
      if (texts.length) gsap.to(texts, { clearProps: "color", delay: 0.5 });
      if (line) {
        gsap.to(line, { scaleX: 1, duration: 0.5, delay: 0.5, ease: e("inOutQuart") });
        gsap.to(line, { backgroundColor: "#000", duration: 0.35, delay: 0.5, ease: e("ease") });
      }
    });
  });

  /* The CTA button keeps its pale-lime ground — nothing in IX2 darkens it, and
   * both copies of its label are black. Its hover is the label swap plus the
   * arrow rolling over inside its clipped black disc. */
  $$(".cta_button").forEach(function (btn) {
    var label = labelSwap(btn);
    var arrows = $$(".cta_button_icon_wrap", btn);
    hover(btn, function () {
      label.over();
      if (arrows.length > 1) gsap.to(arrows, { yPercent: -100, duration: 0.4, ease: e("outQuad") });
    }, function () {
      label.out();
      if (arrows.length > 1) gsap.to(arrows, { yPercent: 0, duration: 0.4, ease: e("outQuad") });
    });
  });

  /* The header links. Each prints its label twice inside a clipping
   * `.nav_link_text_wrap`, the second copy absolutely positioned beneath —
   * the same construction as the buttons. Hovering slides the pair up one
   * line. The 12px bullet fills at the same time.
   *
   * This was the missing piece of the header: the markup and the clip were
   * both there, but nothing moved. */
  $$(".nav_link").forEach(function (link) {
    var wrap = $(".nav_link_text_wrap", link);
    var dot = $(".nav_link_circle", link);
    if (!wrap) return;
    var copies = Array.prototype.slice.call(wrap.children);
    var ink = getComputedStyle(link).color;

    hover(link, function () {
      gsap.to(copies, { yPercent: -100, duration: 0.42, ease: e("outQuad") });
      if (dot) gsap.to(dot, { backgroundColor: ink, scale: 1.25, duration: 0.35, ease: e("outQuad") });
    }, function () {
      gsap.to(copies, { yPercent: 0, duration: 0.42, ease: e("outQuad") });
      if (dot) gsap.to(dot, { backgroundColor: "rgba(0,0,0,0)", scale: 1, duration: 0.35, ease: e("outQuad") });
    });
  });

  /* The header itself settles in on load, under the hero's own intro. */
  (function headerIntro() {
    var brand = $(".brand");
    var links = $$(".nav_link");
    var burger = $(".hamburger_menu_icon:not(.is-close)");
    var bits = [brand].concat(links, [burger]).filter(Boolean);
    if (!bits.length || reduced) return;
    gsap.from(bits, {
      y: -18, opacity: 0, duration: 0.7, stagger: 0.06,
      ease: "power3.out", delay: 0.15, clearProps: "transform,opacity"
    });
  })();

  /* IX2 a-22 / a-23 — social icons dip to 0.9 over 350ms. */
  $$(".hero_social_icon_link").forEach(function (a) {
    hover(a,
      function () { gsap.to(a, { scale: 0.9, duration: 0.35, ease: e("ease") }); },
      function () { gsap.to(a, { scale: 1, duration: 0.35, ease: e("ease") }); });
  });

  /* IX2 a-71 / a-72 — the reference pushes a card's cover image to 1.15 on
   * hover. REMOVED at the client's repeated request: nothing moves when the
   * pointer is over a video.
   *
   * This is the zoom they kept reporting after it had supposedly been fixed.
   * Earlier passes killed it in CSS, which was the wrong place to look — GSAP
   * writes the transform inline on every frame of a tween, so no stylesheet
   * rule was ever going to stop it. The handler had to go, not be overridden.
   *
   * Left as a comment rather than deleted so the next person does not "restore
   * the reference behaviour" and reintroduce it. */

  /* IX2 a-36 / a-37 — award rows wipe a ground up over 750ms outCubic and
   * invert their text over 250ms. */
  $$(".award_item").forEach(function (row) {
    var bg = $(".award_item_background", row);
    var name = $(".award_name", row), status = $(".award_status", row);
    if (bg) gsap.set(bg, { scaleY: 0, transformOrigin: "50% 100%" });
    hover(row, function () {
      if (bg) gsap.to(bg, { scaleY: 1, duration: 0.75, ease: e("outCubic") });
      if (name) gsap.to(name, { x: 1, duration: 0.5, ease: e("ease") });
      if (status) gsap.to(status, { x: -1, duration: 0.5, ease: e("ease") });
      gsap.to(row, { color: "#fff", duration: 0.25, ease: e("ease") });
    }, function () {
      if (bg) gsap.to(bg, { scaleY: 0, duration: 0.6, ease: e("outCubic") });
      if (name) gsap.to(name, { x: 0, duration: 0.5, ease: e("ease") });
      if (status) gsap.to(status, { x: 0, duration: 0.5, ease: e("ease") });
      gsap.to(row, { color: "#121212", duration: 0.25, ease: e("ease") });
    });
  });

  /* -------------------------------------------------- the fullscreen menu
   * .canvas_menu parks at translateY(-100dvh) and drops in. IX2 a-27 / a-28
   * cross the burger into an X over 300ms outSine. */
  (function menu() {
    var burger = $("[data-menu-icon], .hamburger_menu_icon:not(.is-close)");
    var closeBtn = $(".hamburger_menu_icon.is-close");
    var canvas = $(".canvas_menu");
    if (!burger || !canvas) return;

    var lines = $$("[data-menu-line], .hamburger_menu_icon_line", burger);
    var open = false;
    /* Parked by its own height, not by a pixel count.
     *
     * This used to park at y: -window.innerHeight, read once. The panel is
     * 100dvh, so the two agree only until the window is resized — make it
     * taller and the panel grows while the parked offset does not, leaving it
     * hanging into the top of the page. At 1440x1300 it was 1300 tall and
     * parked at -841, so 459px of flat #121212 sat across the hero and took
     * the wordmark with it.
     *
     * yPercent is resolved against the element's own box every render, so it
     * cannot drift out of step with the viewport.
     *
     * y is zeroed alongside it. The stylesheet already parks the panel with
     * transform: translateY(-100dvh); GSAP reads that as a starting y of -1300
     * and would add yPercent on top, parking it at -200% and — worse — opening
     * it to -100%, which is still entirely above the viewport. Stating y: 0
     * discards the inherited offset so yPercent alone controls the panel. */
    gsap.set(canvas, { y: 0, yPercent: -100, visibility: "visible" });

    function setMenu(v) {
      open = v;
      html.classList.toggle("menu-open", v);
      gsap.to(canvas, { y: 0, yPercent: v ? 0 : -100, duration: 0.6, ease: e("inOutCubic") });
      if (lines.length >= 3) {
        gsap.to(lines[1], { opacity: v ? 0 : 1, duration: 0.3, ease: e("outSine") });
        gsap.to(lines[0], { y: v ? 8 : 0, rotate: v ? 45 : 0, duration: 0.3, ease: e("outSine") });
        gsap.to(lines[2], { y: v ? -8 : 0, rotate: v ? -45 : 0, duration: 0.3, ease: e("outSine") });
      }
      if (lenis) { v ? lenis.stop() : lenis.start(); }
    }

    burger.addEventListener("click", function () { setMenu(!open); });
    if (closeBtn) closeBtn.addEventListener("click", function () { setMenu(false); });
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape" && open) setMenu(false); });

    /* The orange ground behind each label is driven by CSS :hover now, not by
     * GSAP. Sliding the panel in moves the links under a stationary cursor,
     * which fires mouseenter with no matching mouseleave — so the JS-held
     * state stuck on and several rows stayed lit at once. CSS cannot desync.
     * Clear anything GSAP may already have written to them. */
    $$(".canvas_menu_link").forEach(function (a) {
      var bg = $(".canvas_menu_active_bg", a);
      if (bg) gsap.set(bg, { clearProps: "all" });
      a.addEventListener("click", function () { setMenu(false); });
    });
  })();

  /* ------------------------------------------------- background video keys
   * Webflow renders a play/pause control over each background video and
   * drives it from its runtime. data-autoplay says whether it starts. */
  $$(".w-background-video").forEach(function (box) {
    var vid = $("video", box), btn = $("button", box);
    if (!vid) return;
    var wants = box.getAttribute("data-autoplay") !== "false";
    vid.muted = true; vid.playsInline = true;
    vid.loop = box.getAttribute("data-loop") !== "false";

    function sync() {
      box.classList.toggle("w-background-video--paused", vid.paused);
      if (btn) btn.setAttribute("aria-label", vid.paused ? "Play video" : "Pause video");
    }
    if (btn) btn.addEventListener("click", function () {
      if (vid.paused) { vid.play(); } else { vid.pause(); }
      sync();
    });
    vid.addEventListener("play", sync);
    vid.addEventListener("pause", sync);

    if (wants) {
      var p = vid.play();
      if (p && p.catch) p.catch(sync);
    } else {
      sync();
    }
  });

  /* ------------------------------------------------------- the film player
   * Any link or button carrying data-vimeo opens the film in a player on this
   * page rather than navigating to vimeo.com. The frame takes the film's own
   * ratio — a 9:16 vertical is not letterboxed into a 16:9 box.
   *
   * The href stays on the markup as the fallback: without JS, or on a
   * middle-click, the link still works. */
  (function filmPlayer() {
    /* Two kinds of hook share one lightbox: [data-vimeo] for HelloVoice's own
     * films, and [data-ig-embed] for the influencer reposts. The Instagram
     * ones carry a full /embed/ URL rather than an id, because Instagram's
     * embed is a page, not a player API — and it is only ever fetched on
     * click, so no third-party frame loads with the page. */
    var hooks = $$("[data-vimeo], [data-ig-embed]");
    if (!hooks.length) return;

    var box = document.createElement("div");
    box.className = "reel_lightbox";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-label", "Video player");
    box.innerHTML =
      '<div class="reel_frame">' +
      '<p class="reel_caption"></p>' +
      '<button type="button" class="reel_close" aria-label="Close video">' +
      '<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">' +
      '<path d="M18.3 5.7 12 12l6.3 6.3-1.4 1.4L10.6 13.4 4.3 19.7 2.9 18.3 9.2 12 2.9 5.7l1.4-1.4 6.3 6.3 6.3-6.3z"/>' +
      "</svg></button></div>";
    document.body.appendChild(box);

    var frame = $(".reel_frame", box);
    var caption = $(".reel_caption", box);
    var closeBtn = $(".reel_close", box);
    var opener = null;

    function close() {
      box.classList.remove("is-visible");
      /* Every kind of media, not just the iframe.
       *
       * This removed `iframe` only, which was right while Vimeo was the only
       * source. Self-hosted films play in a <video>, and that element survived
       * the close — left in the DOM, still playing, still audible — and the
       * next open stacked another one on top of it. Pause first: removing a
       * <video> stops it in every browser that matters, but pausing makes the
       * intent explicit and covers the case where something else holds a
       * reference to the node. */
      frame.querySelectorAll("iframe, video").forEach(function (el) {
        if (el.tagName === "VIDEO") { try { el.pause(); } catch (e) {} }
        el.remove();
      });
      setTimeout(function () { box.classList.remove("is-open"); }, 280);
      html.classList.remove("menu-open");
      if (lenis) lenis.start();
      if (opener) opener.focus();
    }

    function open(src, ratio, title) {
      frame.classList.toggle("is-9-16", ratio === "9:16");
      caption.textContent = title || "";
      /* A film we host ourselves plays in a <video>, not an <iframe>. Some of
         the technology catalogue never made it to Vimeo — the register in the
         handover records IDs that 404 and others whose embed permission is
         refused — so those are served from this site instead, and the lightbox
         has to take both. */
      if (/^\/assets\/.*\.(mp4|webm)$/i.test(src)) {
        var v = document.createElement("video");
        v.src = src;
        v.controls = true;
        v.autoplay = true;
        v.playsInline = true;
        v.setAttribute("playsinline", "");
        v.title = title || "Video";
        frame.appendChild(v);
      } else {
        var iframe = document.createElement("iframe");
        iframe.src = src;
        iframe.title = title || "Video";
        iframe.allow = "autoplay; fullscreen; picture-in-picture";
        iframe.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
        frame.appendChild(iframe);
      }
      box.classList.add("is-open");
      requestAnimationFrame(function () { box.classList.add("is-visible"); });
      html.classList.add("menu-open");        /* reuse the scroll lock */
      if (lenis) lenis.stop();
      closeBtn.focus();
    }

    hooks.forEach(function (el) {
      /* Most hooks are real <button>s, which fire click on Enter and Space for
         free. The showreel wrap is not: it is a <div role="button"
         tabindex="0">, and the browser synthesises no click for it — so a
         keyboard user could focus it, hear it announced as a button, press
         Enter and get nothing. Anything that is not a native button gets the
         keyboard behaviour its role promises. */
      if (!el.matches("button, a") && el.getAttribute("role") === "button") {
        el.addEventListener("keydown", function (ev) {
          if (ev.key !== "Enter" && ev.key !== " " && ev.key !== "Spacebar") return;
          ev.preventDefault();          /* Space would otherwise scroll */
          el.click();
        });
      }

      el.addEventListener("click", function (ev) {
        var ig = el.getAttribute("data-ig-embed");
        var id = el.getAttribute("data-vimeo");
        if ((!id && !ig) || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button > 0) return;
        ev.preventDefault();
        opener = el;
        /* Unlisted films carry a privacy hash. Without ?h= on the embed
           Vimeo refuses them as private, so the lightbox opens on an error
           rather than the film. Public films have no hash and are unaffected. */
        var vh = el.getAttribute("data-vimeo-h");
        var src = ig || ("https://player.vimeo.com/video/" + id +
          "?autoplay=1&title=0&byline=0&portrait=0&dnt=1" +
          (vh ? "&h=" + encodeURIComponent(vh) : ""));
        /* An explicit data-ratio wins. `data-ig-embed` began life meaning "an
           Instagram reel", which is always vertical — but the technology cards
           reuse the same attribute to hand this lightbox a full player URL,
           and their films are 16:9. Forcing 9:16 on the strength of the
           attribute alone opened those in a tall frame with the picture
           letterboxed into a band across the middle.

           So: the ratio the element states, then a vertical default only for a
           real Instagram embed that did not state one, then the 16:9 default
           inside open(). */
        var ratio = el.getAttribute("data-ratio")
          || (ig && /instagram\.com/.test(ig) ? "9:16" : null);
        open(src, ratio,
             el.getAttribute("data-title"));
      });
    });

    closeBtn.addEventListener("click", close);
    box.addEventListener("click", function (ev) { if (ev.target === box) close(); });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && box.classList.contains("is-open")) close();
    });
  })();



  /* ------------------------------------------- the service stack, levelled
   * The cards are sticky and pile up at the same offset, so a card that is
   * shorter than the one behind it leaves that one's bottom strip showing —
   * the previous discipline's headline peeking out under the current card.
   * They therefore have to share a height.
   *
   * That height was a hard-coded 560px, which was too tall for seven of the
   * eight (their content needs 473) and too short for the one whose tag rows
   * wrap furthest. Measuring instead means no card carries dead space it does
   * not need, and none is left uncovered — at any width, with any copy. */
  (function equaliseServiceCards() {
    var cards = $$(".service_section .service_item");
    if (cards.length < 2) return;

    function level() {
      cards.forEach(function (c) { c.style.minHeight = ""; });
      var tallest = 0;
      cards.forEach(function (c) {
        var h = c.getBoundingClientRect().height;
        if (h > tallest) tallest = h;
      });
      if (!tallest) return;
      cards.forEach(function (c) { c.style.minHeight = Math.ceil(tallest) + "px"; });
    }

    /* Below the breakpoint the stylesheet drops the stack to a plain flow and
       min-height with it, so levelling there would reintroduce the gaps the
       stack needed it for. */
    gsap.matchMedia().add(DESKTOP, function () {
      level();
      /* Fonts land after first paint and change how the tag rows wrap. */
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(level);
      var t;
      function onResize() { clearTimeout(t); t = setTimeout(function () {
        level(); ScrollTrigger.refresh();
      }, 180); }
      addEventListener("resize", onResize);
      return function () {
        removeEventListener("resize", onResize);
        clearTimeout(t);
        cards.forEach(function (c) { c.style.minHeight = ""; });
      };
    });
  })();


  /* ------------------------------------------- the campaign run, drawn in
   * The five stations sit on a rule. Static, the rule reads as a border and
   * the stations as five unrelated blocks; the order — which is the whole
   * point of the section — has to be inferred from the numerals.
   *
   * So it draws: the rule wipes left to right and each station lands as the
   * line reaches it. scaleX on a transform-only property, and the stations
   * move on transform and opacity, so nothing here costs a layout.
   *
   * Not scrubbed. A sequence that runs backwards when you scroll up stops
   * reading as a sequence — it plays once, forwards, on arrival. */
  (function drawCampaignRun() {
    var list = $(".ig_steps");
    if (!list) return;
    var steps = $$(".ig_step", list);
    if (!steps.length) return;

    gsap.matchMedia().add(DESKTOP, function () {
      /* The rule is the list's own ::before, which cannot be tweened directly.
         A custom property it reads gives GSAP something to drive. */
      gsap.set(list, { "--run-draw": 0 });
      gsap.set(steps, { opacity: 0, y: 18 });

      var tl = gsap.timeline({
        scrollTrigger: { trigger: list, start: "top 78%", once: true }
      });
      tl.to(list, { "--run-draw": 1, duration: 0.9, ease: "power2.inOut" }, 0);
      tl.to(steps, {
        opacity: 1, y: 0, duration: 0.5, ease: "power2.out",
        stagger: 0.9 / steps.length     /* each lands as the rule reaches it */
      }, 0.12);

      return function () {
        gsap.set(list, { clearProps: "--run-draw" });
        gsap.set(steps, { clearProps: "opacity,transform" });
      };
    });
  })();


  /* ------------------------------------------- in-page anchors, via Lenis
   * Lenis owns the scroll position, so a plain hash jump fights it: the
   * browser sets scrollTop, Lenis reads its own target on the next frame and
   * pulls straight back. Hand the destination to Lenis instead.
   *
   * Offset by the header height so the section's own heading is not parked
   * underneath the fixed nav on arrival.
   */
  (function anchorScroll() {
    var links = $$("[data-scroll-to]");
    if (!links.length) return;
    var nav = $(".navigation");

    links.forEach(function (a) {
      a.addEventListener("click", function (ev) {
        var sel = a.getAttribute("data-scroll-to");
        var target = sel && document.querySelector(sel);
        if (!target || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button > 0) return;
        ev.preventDefault();
        var offset = -((nav && nav.offsetHeight) || 0) - 12;
        if (window.lenis && typeof window.lenis.scrollTo === "function") {
          window.lenis.scrollTo(target, { offset: offset, duration: 1.1 });
        } else {
          var y = target.getBoundingClientRect().top + window.scrollY + offset;
          window.scrollTo({ top: y, behavior: reduced ? "auto" : "smooth" });
        }
        /* Move focus so a keyboard user lands where the page just went —
           without it the next Tab continues from the button in the hero. */
        target.setAttribute("tabindex", "-1");
        target.focus({ preventScroll: true });
      });
    });
  })();


  /* ------------------------------------------------ exclusive projects pager
   * Two films in view, an arrow either side. The track is a scroll container,
   * so the arrows move it by exactly one page rather than by a fixed pixel
   * count — that keeps them correct when the viewport changes the number of
   * tiles on screen, and it means the same code serves the two-up desktop and
   * the one-up phone with no branching.
   *
   * Arrows disable at each end rather than wrapping. A shortlist is short: a
   * carousel that loops back to the first film gives no sense of how much is
   * there, and the client's point in asking for a carousel was that the row
   * should feel picked over.
   */
  (function exclusiveCarousel() {
    /* Two films in view, scrollable, looping.
     *
     * The track is a real scroll container, so a trackpad swipe, a shift-wheel,
     * a drag and the arrows all drive the same thing — and with JS off it stays
     * scrollable rather than becoming a dead strip showing the first two.
     *
     * The loop is done by jumping the scroll position rather than by cloning
     * tiles. Clones were how the old drift worked and they cost a duplicate of
     * every film in the DOM, aria-hidden and out of the tab order but still
     * loading four more posters. Here, reaching either end silently moves the
     * scroll to the opposite end — with snap and smooth scrolling off for that
     * one frame, so the jump is invisible rather than animated.
     */
    var box = $("[data-exclusive]");
    if (!box) return;
    var track = $("[data-exclusive-track]", box);
    if (!track) return;

    function page() {
      var first = track.children[0];
      if (!first) return track.clientWidth;
      var gap = parseFloat(getComputedStyle(track).columnGap ||
                           getComputedStyle(track).gap) || 0;
      return (first.getBoundingClientRect().width + gap) * 2;   /* two at a time */
    }

    function maxScroll() { return track.scrollWidth - track.clientWidth; }

    function jump(to) {
      /* snap and smooth both fight an instant reposition, so they come off for
         the frame in which the wrap happens and go straight back on */
      var snap = track.style.scrollSnapType;
      var behav = track.style.scrollBehavior;
      track.style.scrollSnapType = "none";
      track.style.scrollBehavior = "auto";
      track.scrollLeft = to;
      requestAnimationFrame(function () {
        track.style.scrollSnapType = snap;
        track.style.scrollBehavior = behav;
      });
    }

    function step(dir) {
      var max = maxScroll();
      if (dir > 0 && track.scrollLeft >= max - 4) { jump(0); return; }
      if (dir < 0 && track.scrollLeft <= 4) { jump(max); return; }
      track.scrollBy({ left: page() * dir, behavior: reduced ? "auto" : "smooth" });
    }

    $$(".exclusive_arrow", box).forEach(function (btn) {
      btn.addEventListener("click", function () {
        step(btn.classList.contains("is-prev") ? -1 : 1);
      });
    });

    /* No wrap on the scroll event.
     *
     * The first version wrapped as soon as the track *reached* either end,
     * which meant one press of Next travelled to the end and was instantly
     * thrown back to the start — the row looked frozen because every move was
     * being undone in the same breath.
     *
     * Wrapping belongs to the intent to go further, not to arriving. step()
     * already handles that: pressing Next while parked at the end jumps to the
     * start. A swipe simply stops at the end, which is what a scroll container
     * should do — the reader is driving, and taking the position away from
     * them mid-gesture is the wrong move. */
  })();


  /* ------------------------------------------- header ink follows the hero
   * The nav is white while it sits over a dark hero and ink once the page's
   * own ground is behind it. The stylesheet keys that on .is-scrolled, which
   * nothing was setting — so on the film-hero pages the nav stayed white all
   * the way down, over white content.
   *
   * Switched on the hero's own height rather than a fixed offset: the heroes
   * here are not all the same depth, and a magic number would be right on one
   * page and wrong on the rest. An IntersectionObserver on a sentinel placed
   * at the hero's bottom edge does it without measuring on every frame.
   */
  (function headerInk() {
    var nav = $(".navigation");
    var hero = $("[class*='hero_section']");
    if (!nav || !hero) return;

    function set(on) { nav.classList.toggle("is-scrolled", on); }

    /* Measured from the hero's own bottom edge, not from whether a sentinel is
     * on screen.
     *
     * The sentinel version was wrong in a way that looked right: an element
     * below the fold is "not intersecting" for the same reason one above it
     * is, so a hero taller than the viewport reported scrolled-past while the
     * page was still at the top. The nav came up ink over a dark hero.
     *
     * Comparing the hero's bottom against the header height says the one thing
     * that actually matters — is the hero still behind the nav. */
    var raf = 0;
    function check() {
      raf = 0;
      set(hero.getBoundingClientRect().bottom <= (nav.offsetHeight || 80));
    }
    function queue() { if (!raf) raf = requestAnimationFrame(check); }

    addEventListener("scroll", queue, { passive: true });
    addEventListener("resize", queue);
    if (lenis) lenis.on("scroll", queue);   /* Lenis drives the scroll here */
    check();
  })();


  /* ------------------------------------------- the menu trigger, by keyboard
   * The hamburger is a div with a click handler — Webflow's own construction.
   * A div does not fire click on Enter or Space the way a button does, so the
   * menu was unreachable without a pointer. These two keys are what a button
   * would have given for free, and aria-expanded is kept in step so a screen
   * reader knows whether the panel is open.
   */
  (function menuKeyboard() {
    var trigger = $(".hamburger_menu_icon");
    if (!trigger) return;
    trigger.addEventListener("keydown", function (ev) {
      if (ev.key !== "Enter" && ev.key !== " " && ev.key !== "Spacebar") return;
      ev.preventDefault();          /* Space would scroll the page */
      trigger.click();
    });
    /* the class the overlay toggles is the honest source for the state */
    var sync = function () {
      var open = html.classList.contains("menu-open");
      trigger.setAttribute("aria-expanded", open ? "true" : "false");
      trigger.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    };
    trigger.addEventListener("click", function () { setTimeout(sync, 60); });
    sync();
  })();

  /* --------------------------------------------------- technology: the pager
   * An application with more than one film used to list them as numbered chips
   * under the poster. The still plays now, and this moves it between films.
   * It only rewrites the attribute the lightbox already reads, so there is one
   * player and one code path — nothing here opens anything itself. */
  (function techPager() {
    var stills = $$(".tech_still.has-film[data-tech-films]");
    if (!stills.length) return;

    stills.forEach(function (still) {
      var films = (still.getAttribute("data-tech-films") || "").split("|")
                    .filter(Boolean);
      if (films.length < 2) return;
      var play = still.querySelector("[data-tech-play]");
      var count = still.querySelector("[data-tech-count]");
      var i = 0;

      function show(next) {
        i = (next + films.length) % films.length;
        still.setAttribute("data-tech-index", String(i));
        if (play) play.setAttribute("data-ig-embed", films[i]);
        if (count) count.textContent = (i + 1) + " / " + films.length;
      }

      var prev = still.querySelector("[data-tech-prev]");
      var nxt = still.querySelector("[data-tech-next]");
      /* stopPropagation, not preventDefault: the pager sits inside the still,
         and without it a tap on an arrow would also trip the play button
         underneath and open the film the visitor was trying to skip past. */
      if (prev) prev.addEventListener("click", function (ev) {
        ev.stopPropagation(); show(i - 1);
      });
      if (nxt) nxt.addEventListener("click", function (ev) {
        ev.stopPropagation(); show(i + 1);
      });
    });
  })();

  /* ----------------------------------------------------- the full-bleed film
   * ADDED. Autoplays muted and loops, pausing only while off screen, with a
   * corner control to stop it. The markup carries `autoplay` so the browser
   * starts it without waiting on this script.
   *
   * Play is attempted on every update rather than once on entry. A one-shot
   * onEnter is not enough: a browser can reject autoplay while the tab is
   * backgrounded, a restored scroll position starts the page already past the
   * trigger, and a scroll that jumps the whole section can skip the callback.
   * Any of those left the film sitting on its poster. A visitor who presses
   * pause is respected — `userPaused` stops it being restarted underneath
   * them — as is a reduced-motion preference. */
  (function fullBleedFilm() {
    var wrap = $(".about_video_wrap");
    if (!wrap) return;
    var vid = $(".about_video", wrap);
    var btn = $("[data-video-toggle]", wrap);
    if (!vid) return;

    var userPaused = reduced;
    if (reduced) vid.removeAttribute("autoplay");

    function sync() {
      var playing = !vid.paused && !vid.ended;
      wrap.classList.toggle("is-playing", playing);
      if (btn) btn.setAttribute("aria-label", playing ? "Pause video" : "Play video");
    }
    vid.addEventListener("play", sync);
    vid.addEventListener("pause", sync);

    if (btn) btn.addEventListener("click", function () {
      if (vid.paused) { userPaused = false; vid.play().catch(sync); }
      else { userPaused = true; vid.pause(); }
    });

    function want(on) {
      if (on) {
        if (!userPaused && vid.paused) { var p = vid.play(); if (p && p.catch) p.catch(sync); }
      } else if (!vid.paused) {
        vid.pause();
      }
    }

    ScrollTrigger.create({
      trigger: wrap, start: "top bottom", end: "bottom top",
      onToggle: function (self) { want(self.isActive); },
      onUpdate: function (self) { want(self.isActive); }
    });

    /* and once the tab comes back to the foreground */
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) {
        var r = wrap.getBoundingClientRect();
        want(r.bottom > 0 && r.top < window.innerHeight);
      }
    });
    sync();
  })();

  /* ------------------------------------------------------- the works filter
   * ADDED. Filters .project_item by the tags stamped on it at build time.
   * Cards leave the grid rather than fading in place, so the layout reflows,
   * and the reference's every-other-card offset is re-applied to whatever
   * remains visible. */
  (function worksFilter() {
    /* Multi-select across one row of sectors.
     *
     * The bar used to carry two rows — sector and type — and picking from one
     * wiped the other, so "pharma corporate films" was unaskable. Type is gone
     * from the bar entirely: it was the weaker cut (two of its slices hold
     * under six films, where every sector holds eight or more) and the coloured
     * bands below already group by type, so scrolling does that job.
     *
     * Selecting two sectors is a union, not an intersection — an agency that
     * does pharma and automotive wants to see both bodies of work, not the
     * films that are somehow both.
     */
    var bar = $(".works_filter");
    var grid = $(".project_listing");
    if (!bar || !grid) return;

    var buttons = $$(".works_filter_button", bar);
    var items = $$(".project_item");
    var groups = $$(".work_group");
    var resultBar = $("[data-result-bar]");
    var count = $(".works_result_count");
    var activeChips = $("[data-active-chips]");
    var clearBtn = $("[data-clear-filters]");
    var listing = $(".projects_listing");

    var active = [];                 /* empty means "all work" */

    function labelFor(value) {
      var b = buttons.filter(function (x) { return x.getAttribute("data-filter") === value; })[0];
      return b ? b.textContent.trim() : value;
    }

    function apply() {
      var shown = [];
      items.forEach(function (item) {
        var tags = (item.getAttribute("data-tags") || "").split(" ");
        var on = !active.length || active.some(function (f) { return tags.indexOf(f) !== -1; });
        item.hidden = !on;
        item.classList.remove("is-offset");
        if (on) shown.push(item);
      });

      groups.forEach(function (g) {
        if (g.hasAttribute("data-exclusive-group")) {
          g.hidden = active.length > 0;      /* the pick is not a sector */
          return;
        }
        g.hidden = !$$(".project_item", g).some(function (it) { return !it.hidden; });
      });

      /* A separator band belongs to the group it introduces, so it has to go
       * when that group does. Without this a filtered view left every band
       * standing while only some groups did — two orange bands with nothing
       * between them, which is what the client reported as a duplicated
       * banner. It was two bands, not one drawn twice.
       *
       * Walked in document order rather than by DOM sibling, because the bands
       * are inserted between sections and the listing wrapper sits in between. */
      $$(".project_ticker.is-separator").forEach(function (band) {
        var next = band.nextElementSibling;
        while (next && !next.classList.contains("work_group")) {
          next = next.nextElementSibling;
        }
        band.hidden = !next || next.hidden;
      });

      if (listing) listing.classList.toggle("is-results", active.length > 0);
      grid.classList.toggle("is-filtered", active.length > 0);
      shown.forEach(function (item, i) {
        if (i % 2 === 1) item.classList.add("is-offset");
      });

      buttons.forEach(function (b) {
        var v = b.getAttribute("data-filter");
        var on = v === "all" ? !active.length : active.indexOf(v) !== -1;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });

      if (resultBar) resultBar.hidden = !active.length;
      /* The count reads only while a filter is on. Unfiltered it was a running
       * total of the whole portfolio under the controls, which is inventory
       * rather than navigation — the client's call is that it goes. Filtered it
       * stays, because a visitor who has narrowed to a handful needs to know
       * whether that handful is the answer or a failure. */
      if (count) {
        count.textContent = active.length
          ? shown.length + (shown.length === 1 ? " film" : " films")
          : "";
      }
      if (activeChips) {
        activeChips.innerHTML = "";
        active.forEach(function (v) {
          var chip = document.createElement("button");
          chip.type = "button";
          chip.className = "works_active_chip";
          chip.setAttribute("aria-label", "Remove " + labelFor(v) + " filter");
          chip.innerHTML = '<span>' + labelFor(v) + '</span>' +
            '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" ' +
            'stroke="currentColor" stroke-width="2.5" aria-hidden="true">' +
            '<path d="M6 6l12 12M18 6L6 18"/></svg>';
          chip.addEventListener("click", function () { toggle(v); });
          activeChips.appendChild(chip);
        });
      }

      /* An empty result needs somewhere to say so — a grid that simply stops
         reads as a loading failure rather than as an answer. */
      var empty = $(".works_empty");
      if (!empty && grid.parentElement) {
        empty = document.createElement("p");
        empty.className = "works_empty";
        empty.setAttribute("role", "status");
        grid.parentElement.insertBefore(empty, grid);
      }
      if (empty) {
        empty.hidden = shown.length !== 0;
        empty.textContent = "No films match those filters together. " +
                            "Try removing one.";
      }

      if (!reduced && shown.length) {
        gsap.fromTo(shown, { opacity: 0, y: 16 },
          { opacity: 1, y: 0, duration: 0.4, ease: "power2.out",
            stagger: 0.04, overwrite: true });
      }
      ScrollTrigger.refresh();
    }

    function toggle(value) {
      if (value === "all") { active = []; apply(); return; }
      var i = active.indexOf(value);
      if (i === -1) active.push(value); else active.splice(i, 1);
      apply();
    }

    buttons.forEach(function (b) {
      b.addEventListener("click", function () {
        toggle(b.getAttribute("data-filter"));
      });
    });
    if (clearBtn) clearBtn.addEventListener("click", function () { active = []; apply(); });

    apply();
  })();

  /* --------------------------------------------------------------- forms
   * The reference posts to Webflow. There is nothing to post to here, so keep
   * the success block wired and stop the navigation. */
  $$("form").forEach(function (form) {
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var block = form.closest(".w-form") || form.parentElement;
      var done = $(".w-form-done", block), fail = $(".w-form-fail", block);
      if (done) { form.style.display = "none"; done.style.display = "block"; }
      if (fail) fail.style.display = "none";
    });
  });

  /* --------------------------------------------------------------- tabs
   * The contact page uses Webflow tabs; without its runtime, wire them. */
  $$(".w-tabs").forEach(function (tabs) {
    var links = $$(".w-tab-link", tabs), panes = $$(".w-tab-pane", tabs);
    if (!links.length) return;
    links.forEach(function (link, i) {
      link.addEventListener("click", function (ev) {
        ev.preventDefault();
        links.forEach(function (l) { l.classList.remove("w--current"); });
        panes.forEach(function (p) { p.classList.remove("w--tab-active"); });
        link.classList.add("w--current");
        if (panes[i]) panes[i].classList.add("w--tab-active");
      });
    });
  });

  /* ------------------------------------------------------- scrollbar width
   * Full-bleed bands are sized from the viewport so they can escape the
   * container. The catch is that 100vw counts the scrollbar and the content box
   * does not, so on any browser with a classic scrollbar every band lands wider
   * than the page and pushes horizontal scroll — 7px of it on the works page at
   * 390px, which is how this was found.
   *
   * Measured here rather than guessed, because the width varies by platform and
   * is 0 wherever scrollbars overlay the content.
   *
   * Measuring once at startup is not enough, and reads 0: at that point the
   * page is short enough not to need a scrollbar, and the scrollbar that
   * appears when the content finishes loading fires no resize event. So the
   * value is also refreshed on load and whenever the document's own width
   * changes, which is exactly when a scrollbar appears or goes away. */
  (function scrollbarWidth() {
    function set() {
      var w = window.innerWidth - document.documentElement.clientWidth;
      html.style.setProperty("--sbw", (w > 0 ? w : 0) + "px");
    }
    set();
    window.addEventListener("resize", set, { passive: true });
    window.addEventListener("load", set);
    if (window.ResizeObserver) new ResizeObserver(set).observe(document.documentElement);
  })();

  /* ------------------------------------------------- menu label duplicates
   * Each menu link carries its label twice — one copy visible, one held at
   * opacity 0 for the swap animation. Opacity leaves the copy in the
   * accessibility tree, so a screen reader announces every item twice: "Home
   * Home", "About us About us". Hiding it from assistive tech costs nothing
   * visually, since it is already invisible. */
  $$(".canvas_menu_text .hidden[data-menu-text]").forEach(function (dupe) {
    dupe.setAttribute("aria-hidden", "true");
  });

  /* ------------------------------------------------------------- hero film
   * The hero character is an 8-second film and the scroll position drives it:
   * the page is the transport. At the top of the document he is on his first
   * frame; by the time the hero has cleared the viewport the film has run out.
   *
   * It used to be the cursor. That was abandoned because a pre-rendered clip
   * only contains the gaze directions that were rendered into it, and the
   * lookup that picked the nearest one ignored where in the film it sat — so
   * neighbouring points on screen could be seconds apart in the take, and his
   * eyes ran through the whole performance on the way between them. Scroll has
   * none of that problem: it is monotonic, so the film runs in its own order
   * and every frame is seen once, in the order it was shot.
   *
   * Range is the hero's own height, so the scrub is self-scaling — a tall
   * viewport gets a long scrub and a short one a short scrub, and neither needs
   * a magic number. */
  (function heroFilm() {
    var film = $("[data-hero-film]");
    var hero = film && film.closest(".hero_section");
    if (!film || !hero) return;

    /* Reduced motion keeps the first frame and never seeks. The poster is cut
     * from frame 0, so what is shown is what the film would show anyway — the
     * character is still there, he simply does not move. */
    if (reduced) {
      film.classList.add("is-ready");
      return;
    }

    var shownT = 0;   // where the film is, so a seek is only issued on a change
    var state = { p: 0 };

    /* Seeking a video the browser has never decoded returns a blank frame on
     * iOS. Playing it muted for one instant and pausing forces the decoder up
     * without the visitor seeing motion. */
    function prime() {
      var q = film.play();
      if (q && q.then) q.then(function () { film.pause(); }, function () {});
      else film.pause();
    }

    /* Only paint once a real frame is decoded, so the poster does not flick to
     * black in the handover. "seeked" alone is not enough: at the top of the
     * page the film is already at 0 and the first seek asks it to go to 0,
     * which is not a move and emits no event. */
    function markReady() { film.classList.add("is-ready"); }
    film.addEventListener("seeked", markReady, { once: true });
    film.addEventListener("loadeddata", markReady, { once: true });
    if (film.readyState >= 2) markReady();

    film.addEventListener("loadedmetadata", prime);
    if (film.readyState >= 1) prime();

    function apply() {
      /* Read the duration from the element rather than caching it at startup.
       * A cached copy set in a load handler is 0 whenever that handler missed —
       * metadata already in when the script ran, or still absent — and then
       * every seek is skipped and the film holds one frame for the whole
       * scroll. That failure is not reproducible after load, which is why the
       * cached version survived several passes of testing. */
      var duration = film.duration;
      if (!duration || !isFinite(duration)) return;
      var t = state.p * duration;
      if (t < 0) t = 0;
      else if (t > duration) t = duration;
      /* One frame of the source is 1/24s. Seeking for less than that decodes a
       * 4K frame to show the same picture — the whole cost and none of the
       * benefit. */
      if (Math.abs(t - shownT) < 1 / 24) return;
      shownT = t;
      try { film.currentTime = t; } catch (err) { /* not seekable yet */ }
    }

    /* Pinned, so the film gets the screen to itself.
     *
     * Without the pin the hero scrolls away while the film is still running and
     * the last third of the take plays off the top of the viewport — the part
     * nobody sees is the part he finishes on. Pinning holds the section still
     * until the film has run out, then releases the page into the section
     * below, so the whole eight seconds happens in front of the viewer.
     *
     * The distance is a viewport and a half rather than a fixed pixel count.
     * Scroll speed scales with screen size, so a number that feels unhurried on
     * a laptop feels interminable on a large display; expressing it in screens
     * keeps the pace the same everywhere. It is a function so a resize
     * remeasures instead of keeping the height the page loaded at.
     *
     * Scrubbed through a proxy value rather than seeking straight from the
     * scroll position. scrub carries the film on for a beat after the wheel
     * stops, so he coasts to a halt instead of freezing on the exact frame the
     * scroll ended on. */
    gsap.to(state, {
      p: 1,
      ease: "none",
      onUpdate: apply,
      scrollTrigger: {
        trigger: hero,
        start: "top top",
        end: function () { return "+=" + Math.round(window.innerHeight * 1.5); },
        pin: true,
        pinSpacing: true,
        /* Pins taken at speed can show one frame of the unpinned position
         * before the pin engages. Pinning a beat early costs nothing and
         * removes the flash. */
        anticipatePin: 1,
        scrub: 0.6,
        invalidateOnRefresh: true
      }
    });
  })();

  /* Initial states are in place — let the stylesheet show them. */
  reveal();
  ScrollTrigger.refresh();
  window.addEventListener("load", function () { ScrollTrigger.refresh(); });
})();
