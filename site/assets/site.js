/* HelloVoice — behaviour.
   Mirrors the reference's stack: Lenis smooth scroll driving GSAP ScrollTrigger,
   with the three pinned tracks (year rail, work stack, showreel mask).
   Everything degrades: if GSAP or Lenis fail to load the page is still complete
   and scrollable, and the pinned sections fall back to ordinary flow. */
(function () {
  "use strict";

  var reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  var hasGSAP = typeof window.gsap !== "undefined" &&
    typeof window.ScrollTrigger !== "undefined";

  /* ------------------------------------------------------------ preloader */
  var pre = document.querySelector(".preloader");
  if (pre) {
    requestAnimationFrame(function () { pre.classList.add("go"); });
    var dismiss = function () {
      pre.classList.add("done");
      setTimeout(function () { if (pre.parentNode) pre.parentNode.removeChild(pre); }, 700);
    };
    if (reduce) dismiss();
    else {
      addEventListener("load", function () { setTimeout(dismiss, 480); });
      /* never let a stalled asset trap the page behind the curtain */
      setTimeout(dismiss, 3200);
    }
  }

  /* ----------------------------------------------- smooth scroll + trigger */
  var lenis = null;
  if (typeof window.Lenis !== "undefined" && !reduce) {
    lenis = new window.Lenis({ smoothWheel: true, lerp: 0.1 });
    if (hasGSAP) {
      lenis.on("scroll", window.ScrollTrigger.update);
      window.gsap.ticker.add(function (t) { lenis.raf(t * 1000); });
      window.gsap.ticker.lagSmoothing(0);
    } else {
      requestAnimationFrame(function raf(t) { lenis.raf(t); requestAnimationFrame(raf); });
    }
  }

  /* ------------------------------------------------------------------ nav */
  var nav = document.querySelector(".nav");
  var lastY = 0;
  function onScroll() {
    var y = window.scrollY;
    if (nav) {
      nav.classList.toggle("solid", y > 40);
      nav.classList.toggle("hide", y > 320 && y > lastY + 4 && !canvasOpen());
    }
    lastY = y;
  }
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  var burger = document.querySelector(".burger");
  var canvas = document.querySelector(".canvas");
  function canvasOpen() { return canvas && canvas.classList.contains("open"); }
  function setCanvas(open) {
    if (!canvas || !burger) return;
    canvas.classList.toggle("open", open);
    burger.setAttribute("aria-expanded", open ? "true" : "false");
    document.documentElement.style.overflow = open ? "hidden" : "";
    if (lenis) open ? lenis.stop() : lenis.start();
  }
  if (burger) burger.addEventListener("click", function () { setCanvas(!canvasOpen()); });
  if (canvas) canvas.addEventListener("click", function (e) {
    if (e.target.tagName === "A") setCanvas(false);
  });
  addEventListener("keydown", function (e) {
    if (e.key === "Escape") { setCanvas(false); closeLB(); }
  });

  /* -------------------------------------------------------- reveal on scroll */
  var revealables = document.querySelectorAll("[data-rise],[data-stagger]");
  function reveal(el) {
    if (el.hasAttribute("data-stagger")) {
      [].forEach.call(el.children, function (c, i) {
        c.style.animationDelay = (i * 70) + "ms";
      });
    }
    el.classList.add("in");
  }
  if ("IntersectionObserver" in window && !reduce) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        io.unobserve(e.target);
        var el = e.target;
        requestAnimationFrame(function () {
          requestAnimationFrame(function () { reveal(el); });
        });
      });
    }, { rootMargin: "0px 0px -10% 0px", threshold: 0.06 });
    revealables.forEach(function (el) { io.observe(el); });
    /* Failsafe. Content must never stay invisible because an animation misfired
       or the observer never ran. Forces the end state inline. */
    setTimeout(function () {
      revealables.forEach(function (el) {
        reveal(el);
        var targets = el.hasAttribute("data-stagger") ? [].slice.call(el.children) : [el];
        targets.forEach(function (t) {
          var cs = getComputedStyle(t);
          if (parseFloat(cs.opacity) < 0.9 ||
              (cs.transform !== "none" && cs.transform !== "matrix(1, 0, 0, 1, 0, 0)")) {
            t.style.opacity = "1"; t.style.transform = "none";
          }
        });
      });
    }, 2800);
  } else {
    revealables.forEach(reveal);
  }

  /* ------------------------------------------------------- the pinned tracks
     Registered through gsap.matchMedia so the three tracks build and tear down
     as the viewport crosses the breakpoint, rather than being decided once at
     load. Below 861px the CSS unpins them and they scroll as ordinary flow. */
  if (hasGSAP) {
    window.gsap.registerPlugin(window.ScrollTrigger);
    window.gsap.matchMedia().add(
      "(min-width: 861px) and (prefers-reduced-motion: no-preference)",
      function () { buildScrollScenes(); }
    );
  }

  function buildScrollScenes() {

    /* 1 — hero wordmark: characters rise in sequence */
    var h1 = document.querySelector(".hero_heading h1");
    if (h1 && !h1.dataset.split) {
      h1.dataset.split = "1";
      var html = "";
      [].forEach.call(h1.childNodes, function (n) {
        if (n.nodeType === 3) {
          html += n.nodeValue.replace(/\S/g, function (ch) {
            return '<span class="ch" style="display:inline-block">' + ch + "</span>";
          });
        } else {
          html += n.outerHTML.replace(/>([^<]+)</, function (m, txt) {
            return ">" + txt.replace(/\S/g, function (ch) {
              return '<span class="ch" style="display:inline-block">' + ch + "</span>";
            }) + "<";
          });
        }
      });
      h1.innerHTML = html;
      window.gsap.from(h1.querySelectorAll(".ch"), {
        yPercent: 108, opacity: 0, duration: 1.05, ease: "expo.out",
        stagger: 0.028, delay: pre ? 0.75 : 0.15
      });
    }

    /* 2 — the year rail translates horizontally across the pinned viewport */
    var rail = document.querySelector(".year_rail");
    var aboutTrack = document.querySelector(".about_track");
    if (rail && aboutTrack) {
      window.gsap.to(rail, {
        x: function () { return -(rail.scrollWidth - window.innerWidth + 64); },
        ease: "none",
        scrollTrigger: {
          trigger: aboutTrack, start: "top top", end: "bottom bottom",
          scrub: 0.6, invalidateOnRefresh: true
        }
      });
    }

    /* 3 — the showreel mask grows from a small rounded rect to full bleed */
    var mask = document.querySelector(".showreel_mask");
    var reelTrack = document.querySelector(".showreel_track");
    if (mask && reelTrack) {
      window.gsap.to(mask, {
        width: "100vw", height: "100svh", borderRadius: 0, ease: "none",
        scrollTrigger: {
          trigger: reelTrack, start: "top top", end: "60% bottom",
          scrub: 0.5, invalidateOnRefresh: true
        }
      });
      var words = document.querySelectorAll(".showreel_word");
      if (words.length) {
        window.gsap.to(words[0], { xPercent: -60, ease: "none", scrollTrigger: {
          trigger: reelTrack, start: "top top", end: "60% bottom", scrub: 0.5 } });
        window.gsap.to(words[1], { xPercent: 60, ease: "none", scrollTrigger: {
          trigger: reelTrack, start: "top top", end: "60% bottom", scrub: 0.5 } });
      }
    }

    /* 4 — work items scale down slightly as the next one covers them */
    [].forEach.call(document.querySelectorAll(".work_item"), function (item, i, all) {
      if (i === all.length - 1) return;
      window.gsap.to(item, {
        scale: 0.955, opacity: 0.55, ease: "none",
        scrollTrigger: { trigger: all[i + 1], start: "top bottom", end: "top top", scrub: 0.4 }
      });
    });

    /* 5 — the orbiting client circles drift with scroll */
    var ring = document.querySelector(".leader_ring");
    if (ring) {
      window.gsap.to(ring.children, {
        y: function (i) { return (i % 2 ? -1 : 1) * 46; }, ease: "none",
        scrollTrigger: { trigger: ring.parentNode, start: "top bottom", end: "bottom top",
          scrub: 0.8 }
      });
    }
  }

  /* --------------------------------------------------------------- lightbox */
  var lb = document.getElementById("lb");
  function openLB(id, title) {
    if (!lb || !id) return;
    lb.querySelector(".box").insertAdjacentHTML("beforeend",
      '<iframe src="https://player.vimeo.com/video/' + id +
      '?autoplay=1&title=0&byline=0&portrait=0&dnt=1" allow="autoplay; fullscreen; ' +
      'picture-in-picture" allowfullscreen title="' + (title || "Film") + '"></iframe>');
    lb.classList.add("on");
    document.documentElement.style.overflow = "hidden";
    if (lenis) lenis.stop();
    var x = lb.querySelector(".x"); if (x) x.focus();
  }
  function closeLB() {
    if (!lb || !lb.classList.contains("on")) return;
    lb.classList.remove("on");
    var f = lb.querySelector("iframe"); if (f) f.remove();
    document.documentElement.style.overflow = "";
    if (lenis) lenis.start();
  }
  document.addEventListener("click", function (e) {
    var p = e.target.closest && e.target.closest("[data-vimeo]");
    if (p) { e.preventDefault(); openLB(p.dataset.vimeo, p.dataset.title); return; }
    if (e.target.closest && e.target.closest(".lb .x")) closeLB();
    else if (lb && lb.classList.contains("on") && e.target === lb) closeLB();
  });
  document.addEventListener("keydown", function (e) {
    var p = e.target.closest && e.target.closest("[data-vimeo]");
    if (p && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault(); openLB(p.dataset.vimeo, p.dataset.title);
    }
  });

  /* ---------------------------------------------------------------- filters */
  var filters = document.getElementById("filters");
  var grid = document.getElementById("workgrid");
  var countEl = document.getElementById("count");
  if (filters && grid) {
    filters.addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      var f = b.dataset.f, n = 0;
      [].forEach.call(filters.querySelectorAll("button"), function (x) {
        x.setAttribute("aria-pressed", x === b ? "true" : "false");
      });
      [].forEach.call(grid.children, function (it) {
        var show = f === "all" || it.dataset.svc === f || it.dataset.ind === f;
        it.hidden = !show;
        if (show) n++;
      });
      if (countEl) countEl.textContent = n + (n === 1 ? " film" : " films");
      if (hasGSAP) window.ScrollTrigger.refresh();
    });
  }

  /* ------------------------------------------------- contact form prefill */
  var sel = document.getElementById("service");
  if (sel) {
    var q = new URLSearchParams(location.search).get("service");
    if (q) [].forEach.call(sel.options, function (o) { if (o.value === q) sel.value = q; });
  }

  /* ------------------------------------------------------- the character
     The hero slot takes a scrubbed video: cursor X drives playback position,
     cursor Y applies a subtle tilt. Wired now so the asset drops straight in.
     Does nothing until a <video data-scrub> is present. */
  var scrub = document.querySelector(".hero_image video[data-scrub]");
  if (scrub) {
    var stage = scrub.parentNode;
    var dur = 0, target = 0, current = 0, tilt = 0, tiltTarget = 0, raf = null;
    scrub.pause();
    scrub.addEventListener("loadedmetadata", function () { dur = scrub.duration || 0; });
    function tick() {
      current += (target - current) * 0.09;
      tilt += (tiltTarget - tilt) * 0.08;
      if (dur) {
        var t = Math.max(0, Math.min(dur - 0.02, current * dur));
        if (Math.abs(t - scrub.currentTime) > 0.008) scrub.currentTime = t;
      }
      stage.style.transform = "perspective(1400px) rotateX(" + (-tilt * 3.2).toFixed(3) +
        "deg) translateY(" + (tilt * 9).toFixed(2) + "px)";
      raf = requestAnimationFrame(tick);
    }
    if (!reduce) {
      addEventListener("pointermove", function (e) {
        target = Math.max(0, Math.min(1, e.clientX / window.innerWidth));
        tiltTarget = (e.clientY / window.innerHeight) - 0.5;
      }, { passive: true });
      target = current = 0.5;
      tick();
      /* pause the loop while the hero is off screen */
      if ("IntersectionObserver" in window) {
        new IntersectionObserver(function (es) {
          if (es[0].isIntersecting) { if (!raf) tick(); }
          else if (raf) { cancelAnimationFrame(raf); raf = null; }
        }, { threshold: 0 }).observe(stage);
      }
    } else {
      scrub.addEventListener("loadedmetadata", function () {
        scrub.currentTime = (scrub.duration || 0) / 2;
      });
    }
  }
})();
