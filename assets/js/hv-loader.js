/* The page loader and Helvi's clips, on every catalogue page.
 *
 * Loader rule (client-approved 2026-10-09, replaces the old "no time limit"):
 *   - the page draws its own shell straight away (header, skeleton cards);
 *     nothing covers it while it is quick;
 *   - the loader (the HELVi Connect logo, breathing) appears only if the page is not ready after 0.6 s,
 *     and it is gone 1.5 s after the page started, ready or not. The page's
 *     skeleton carries on from there;
 *   - "ready" = the window has loaded and none of the page's own requests has
 *     been in flight for a short beat (fetch is counted from here, before any
 *     other script runs), or the page says so with hvLoader.done(). Images are
 *     never waited for: cards load their photos lazily as they scroll in;
 *   - data-tone="dark" is the white logo on ink, "light" the coloured logo on
 *     white;
 *   - clicking a link to another catalogue page brings the loader back only
 *     if that page takes longer than 0.6 s to arrive.
 *
 * HVHelvy (window.HVHelvy) is the ONE place Helvi's files are named. The clips
 * are transparent cut-outs, framed waist-up: VP9 with alpha (.webm) for Chrome,
 * Edge and Firefox, HEVC with alpha (.mov, hvc1) for Safari and every browser
 * on iPhone and iPad, and a transparent still for reduced motion.
 *
 * Autoplay refused is NOT final (fix batch 3, 2026-10-10). Safari refuses every
 * autoplay in macOS / iOS Low Power Mode (NotAllowedError, readyState 0), and the
 * old code swapped the clip for the still for good on that first refusal, so a
 * laptop on battery saw a static Helvi on the sign-in page. Now the still sits
 * under the waiting clip, play is tried again when the clip can play, when the
 * tab comes back, and on the visitor's first tap, click or key anywhere (which
 * every browser accepts as permission); the still is removed the moment the clip
 * is really playing. Only a clip that cannot be decoded at all stays a still.
 *
 * Two sets (fix batch 4, 2026-10-10). "helvy" is the transparent cut-out above. "voice" is
 * Helvi head-and-shoulders on lime (assets/brand/voice/, opaque H.264 .mp4 for Safari and
 * WebKit, VP9 .webm elsewhere): short, expressive reactions (point, thumbs, cheer), a think
 * and a camera "scan" loop, made for the lime circles of the AI shortlist card and the
 * selection's "Add more like these". Opaque H.264 needs no alpha decoding, so it plays in
 * every browser. video(name, {set: "voice"}) picks it; everything else is shared.
 */
(function () {
  "use strict";
  var me = document.currentScript;
  var tone = (me && me.getAttribute("data-tone")) === "light" ? "light" : "dark";
  var base = me && me.src ? me.src.replace(/assets\/js\/hv-loader\.js.*$/, "") : "/";
  // The loader is the HELVi Connect logo alone, breathing (client, 2026-10-10): coloured on light
  // pages, white on ink. "dark" is the file drawn for dark backgrounds.
  var logo = base + "assets/brand/helvy-connect/helvy-connect-" + (tone === "light" ? "light" : "dark") + "-640.webp?v=c4";
  var reduce = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  var T0 = Date.now();
  var SHOW_AFTER = 600, GONE_BY = 1500;

  /* The onboarding tour (tour.js) plays the real pages in a frame on demo data. The frame
     is handed to the tour before any other script runs: from here every /api/ call is
     answered from the demo world and storage stays in memory, so nothing is saved. */
  var DEMO = false;
  try {
    var top_ = window.top;
    if (top_ !== window && top_.hvTourDemo && top_.hvTourDemo.active) { top_.hvTourDemo.install(window); DEMO = true; }
  } catch (e) { DEMO = false; }

  /* ================================================================ Helvi */
  var HELVi = window.HVHelvy = (function () {
    var dir = base + "assets/brand/helvy/";
    var CLIPS = { idle: 1, hello: 1, bye: 1, loader: 1, thinking: 1, celebrate: 1, point: 1, cards: 1, approve: 1 };
    var ua = navigator.userAgent || "";
    // Safari, and every browser on iOS / iPadOS (all WebKit): HEVC with alpha.
    // Safari decodes VP9 but drops its alpha, so it must never get the .webm.
    var apple = /iP(hone|od|ad)/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1) ||
      (/Safari\//.test(ua) && !/Chrome\/|Chromium|CriOS|Edg\/|OPR\/|Firefox\/|Android/.test(ua));
    var still = dir + "helvy-still.webp" + "?v=t3";
    var watching = [], io = null;
    var vdir = base + "assets/brand/voice/";
    var VOICE = { loop: 1, wave: 1, hi: 1, up: 1, "point-act": 1, point: 1, think: 1, "think-act": 1, "thumbs-act": 1, thumbs: 1, "cheer-act": 1, cheer: 1, scan: 1 };
    var vstill = vdir + "voice-hi-poster.webp?v=t5";      // the smiling frame, not the flat first frame of the old loop

    // VER changes whenever the files are replaced: /assets/ is cached for 30 days as immutable.
    var VER = "?v=t3";
    function src(name, set) {
      if (set === "voice") return vdir + "voice-" + (VOICE[name] ? name : "loop") + (apple ? ".mp4" : ".webm") + VER;
      return dir + "helvy-" + (CLIPS[name] ? name : "idle") + (apple ? ".mov" : ".webm") + VER;
    }
    function img(cls, set, poster) {
      var im = document.createElement("img");
      im.className = "hv-clip hv-clip--still" + (cls ? " " + cls : ""); im.alt = ""; im.decoding = "async"; im.src = poster || (set === "voice" ? vstill : still);
      im.setAttribute("aria-hidden", "true");
      return im;
    }
    // A clip the browser cannot decode at all: the still takes its place for good.
    function fallback(v) {
      if (!v.parentNode || v.getAttribute("data-fallback")) return;
      v.setAttribute("data-fallback", "1");
      unwait(v);
      var im = img(v.getAttribute("data-cls"), v.getAttribute("data-set"), v.getAttribute("data-poster"));
      v.parentNode.replaceChild(im, v);
      try { v.removeAttribute("src"); v.load(); } catch (e) { /* gone */ }
    }
    // Autoplay refused for now (Low Power Mode, a strict browser): the clip is hidden
    // (so no native play button ever shows) with the still in its place, and waits.
    var waiting = [];
    function wait(v) {
      if (v.getAttribute("data-wait") || !v.parentNode) return;
      v.setAttribute("data-wait", "1");
      var im = img(v.getAttribute("data-cls"), v.getAttribute("data-set"), v.getAttribute("data-poster"));
      im.setAttribute("data-for-wait", "1");
      v.parentNode.insertBefore(im, v);
      v._still = im;
      waiting.push(v);
      armGesture();
    }
    function unwait(v) {
      if (!v.getAttribute("data-wait")) return;
      v.removeAttribute("data-wait");
      if (v._still && v._still.parentNode) v._still.parentNode.removeChild(v._still);
      v._still = null;
      waiting = waiting.filter(function (x) { return x !== v; });
    }
    // The visitor's first tap, click or key is the permission every browser accepts.
    var gestureOn = false;
    function armGesture() {
      if (gestureOn) return;
      gestureOn = true;
      var go = function () {
        waiting.slice().forEach(function (v) { if (v.isConnected) play(v, true); });
        if (!waiting.length) {
          gestureOn = false;
          ["pointerdown", "keydown", "touchstart"].forEach(function (t) { document.removeEventListener(t, go, true); });
        }
      };
      ["pointerdown", "keydown", "touchstart"].forEach(function (t) { document.addEventListener(t, go, { capture: true, passive: true }); });
    }
    // Ambient clips (launcher, cards) wait until the page has loaded and settled, so they never
    // compete with the roster and the first photos; "eager" ones (loader, reactions) do not.
    var settled = document.readyState === "complete";
    if (!settled) window.addEventListener("load", function () {
      setTimeout(function () { settled = true; watching.forEach(function (v) { if (!v.getAttribute("data-off")) play(v); }); }, 400);
    });
    function play(v, gesture) {
      if (!v.isConnected || v.getAttribute("data-fallback") || document.hidden) return;
      // A waiting clip is hidden (its still shows), so the observer calls it "off screen";
      // it may still be retried.
      if (v.getAttribute("data-off") && !gesture && !v.getAttribute("data-wait")) return;
      if (!settled && !v.hasAttribute("data-eager") && !gesture) return;
      if (!v.getAttribute("src")) { v.src = src(v.getAttribute("data-clip"), v.getAttribute("data-set")); }
      if (!v.paused) return;
      var p;
      try { p = v.play(); } catch (e) { return wait(v); }
      if (p && p.catch) p.catch(function (err) {
        if (err && err.name === "NotAllowedError") wait(v);
        // AbortError: the source changed under it (sequence); the next canplay retries.
      });
    }
    function observe(v) {
      if (!("IntersectionObserver" in window)) { play(v); return; }
      if (!io) io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          var v = en.target;
          if (en.isIntersecting) { v.removeAttribute("data-off"); play(v); }
          else { v.setAttribute("data-off", "1"); if (!v.paused) v.pause(); }
        });
      }, { rootMargin: "120px" });
      io.observe(v);
      watching.push(v);
    }
    document.addEventListener("visibilitychange", function () {
      watching = watching.filter(function (v) { return v.isConnected || !v.getAttribute("data-gone"); });
      watching.forEach(function (v) { if (document.hidden) { if (!v.paused) v.pause(); } else play(v); });
      if (!document.hidden) waiting.slice().forEach(function (v) { if (v.isConnected) play(v); });
    });

    /* video(name, {once, then, seq, cls, eager, set}) -> <video> (or the still under reduced motion).
       once + then: play `name` once, then loop `then` (hello -> idle).
       seq: a list played one after another, round and round (the "cooking" desk). */
    function video(name, o) {
      o = o || {};
      var set = o.set === "voice" ? "voice" : "";
      if (reduce) return img(o.cls, set, o.poster);
      var list = o.seq && o.seq.length ? o.seq.slice() : null;
      var v = document.createElement("video");
      // Every attribute that lets a browser autoplay goes on BEFORE the source.
      v.muted = true; v.defaultMuted = true;
      v.setAttribute("muted", ""); v.setAttribute("playsinline", ""); v.setAttribute("webkit-playsinline", "");
      v.setAttribute("autoplay", ""); v.autoplay = true;
      v.setAttribute("disablepictureinpicture", ""); v.setAttribute("disableremoteplayback", "");
      v.setAttribute("aria-hidden", "true"); v.setAttribute("tabindex", "-1");
      v.controls = false; v.preload = "auto"; v.poster = o.poster || (set ? vstill : still);
      if (o.poster) v.setAttribute("data-poster", o.poster);
      if (set) v.setAttribute("data-set", set);
      v.className = "hv-clip" + (o.cls ? " " + o.cls : "");
      if (o.cls) v.setAttribute("data-cls", o.cls);
      var loopOne = !list && !o.once;
      if (loopOne) { v.loop = true; v.setAttribute("loop", ""); }
      var cur = list ? list[0] : name, i = 0;
      v.setAttribute("data-clip", cur);
      v.addEventListener("ended", function () {
        if (list) { i = (i + 1) % list.length; cur = list[i]; }
        else if (o.once && o.then) { cur = o.then; v.loop = true; v.setAttribute("loop", ""); }
        else return;
        v.setAttribute("data-clip", cur); v.src = src(cur, set); play(v);
      });
      v.addEventListener("canplay", function () { play(v); });
      v.addEventListener("loadeddata", function () { play(v); });
      // Really moving: the waiting still (if any) goes.
      v.addEventListener("playing", function () { unwait(v); });
      // MEDIA_ERR_DECODE / SRC_NOT_SUPPORTED: this browser cannot show the clip at all.
      v.addEventListener("error", function () { var e = v.error; if (!e || e.code >= 3) fallback(v); });
      if (o.eager) { v.setAttribute("data-eager", ""); v.src = src(cur, set); setTimeout(function () { play(v); }, 0); }
      // Off screen it neither downloads nor plays; on screen it plays.
      setTimeout(function () { observe(v); }, 0);
      return v;
    }
    return { dir: dir, still: still, vstill: vstill, wavePoster: vdir + "voice-hi-poster.webp?v=t5", head: base + "assets/brand/helvy-head.webp?v=c3", apple: apple, src: src, video: video, play: play, img: img };
  })();

  /* =============================================================== loader */
  var css = document.createElement("style");
  css.textContent =
    ".hv-clip::-webkit-media-controls,.hv-clip::-webkit-media-controls-start-playback-button,.hv-clip::-webkit-media-controls-overlay-play-button" +
    "{display:none!important;-webkit-appearance:none;opacity:0!important;}" +
    // A clip waiting for permission to play takes no room; its still stands in.
    "video.hv-clip[data-wait]{display:none!important;}" +
    ".hv-loader{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:center;justify-content:center;" +
    "background:#121212;opacity:0;transition:opacity .22s ease;}" +
    ".hv-loader.is-on{opacity:1;}" +
    ".hv-loader--light{background:#fff;}" +
    ".hv-loader__logo{display:block;width:min(260px,62vw);height:auto;" +
      (reduce ? "" : "animation:hv-breathe 2.4s ease-in-out infinite;will-change:transform,opacity;") + "}" +
    "@keyframes hv-breathe{0%,100%{transform:scale(.94);opacity:.55}50%{transform:scale(1.04);opacity:1}}" +
    "html.hv-loading,html.hv-loading body{overflow:hidden;}";
  (document.head || document.documentElement).appendChild(css);

  // data-helvy-only: the admin pages load this file for Helvi's clips (the copilot launcher)
  // and nothing else: no page loader, no request counting.
  if (me && me.hasAttribute("data-helvy-only")) return;

  var cover = null, shown = false, ready = false, timer = null, capTimer = null;
  function build() {
    cover = document.createElement("div");
    cover.className = "hv-loader" + (tone === "light" ? " hv-loader--light" : "");
    cover.setAttribute("role", "status");
    cover.setAttribute("aria-label", "Loading");
    var img = document.createElement("img");
    img.src = logo; img.alt = "HELVi Connect"; img.className = "hv-loader__logo";
    img.width = 320; img.height = 160; img.decoding = "async";
    cover.appendChild(img);
  }
  function show() {
    if (shown) return;
    if (!cover) build();
    shown = true;
    if (!cover.parentNode) document.documentElement.appendChild(cover);
    cover.style.display = "";
    document.documentElement.classList.add("hv-loading");
    requestAnimationFrame(function () { if (shown) cover.classList.add("is-on"); });
  }
  function hide() {
    clearTimeout(timer); clearTimeout(capTimer);
    if (!shown) return;
    shown = false;
    cover.classList.remove("is-on");
    document.documentElement.classList.remove("hv-loading");
    var v = cover.querySelector("video"); if (v && v.pause) { v.setAttribute("data-off", "1"); v.pause(); }
    setTimeout(function () { if (!shown && cover) cover.style.display = "none"; }, 260);
  }
  function arm(from) {
    clearTimeout(timer); clearTimeout(capTimer);
    var elapsed = Date.now() - from;
    timer = setTimeout(function () { if (!ready) show(); }, Math.max(0, SHOW_AFTER - elapsed));
    capTimer = setTimeout(hide, Math.max(0, GONE_BY - elapsed));
  }
  function done() { ready = true; hide(); }
  window.hvLoader = { done: done, show: show, hide: hide };

  /* -- count the page's own requests -- */
  var inflight = 0, lastEnd = Date.now();
  if (window.fetch) {
    var realFetch = window.fetch;
    window.fetch = function () {
      inflight++;
      var fin = function () { inflight = Math.max(0, inflight - 1); lastEnd = Date.now(); };
      try {
        var p = realFetch.apply(this, arguments);
        p.then(fin, fin);
        return p;
      } catch (e) { fin(); throw e; }
    };
  }
  var loaded = document.readyState === "complete";
  window.addEventListener("load", function () { loaded = true; });
  function check() {
    if (ready) return;
    if (!loaded || inflight > 0 || Date.now() - lastEnd < 250) { setTimeout(check, 100); return; }
    done();
  }
  // In the tour's demo frame the tour draws its own cover while the page loads.
  if (DEMO) ready = true; else arm(T0);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { setTimeout(check, 30); });
  else setTimeout(check, 30);

  /* -- moving between pages: the loader returns only if the next page is slow -- */
  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
    var url;
    try { url = new URL(a.getAttribute("href"), location.href); } catch (x) { return; }
    if (url.origin !== location.origin || /^\/admin(\/|$)/.test(url.pathname)) return;
    if (url.pathname === location.pathname && url.search === location.search) return;
    setTimeout(function () {
      if (e.defaultPrevented) return;
      ready = false;
      clearTimeout(timer); clearTimeout(capTimer);
      timer = setTimeout(function () { if (!ready) show(); }, SHOW_AFTER);
    }, 0);
  });
  // Back from the browser's cache: nothing to wait for.
  window.addEventListener("pageshow", function (e) { if (e.persisted) done(); });
})();
