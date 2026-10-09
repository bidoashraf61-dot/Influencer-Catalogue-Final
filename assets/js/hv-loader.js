/* The page loader and Helvy's clips, on every catalogue page.
 *
 * Loader rule (client-approved 2026-10-09, replaces the old "no time limit"):
 *   - the page draws its own shell straight away (header, skeleton cards);
 *     nothing covers it while it is quick;
 *   - the Helvy loader appears only if the page is not ready after 0.6 s,
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
 * HVHelvy (window.HVHelvy) is the ONE place Helvy's files are named. The clips
 * are transparent cut-outs, framed waist-up: VP9 with alpha (.webm) for Chrome,
 * Edge and Firefox, HEVC with alpha (.mov, hvc1) for Safari and every browser
 * on iPhone and iPad, and a transparent still for reduced motion and for any
 * browser that refuses to autoplay (never the native play button).
 */
(function () {
  "use strict";
  var me = document.currentScript;
  var tone = (me && me.getAttribute("data-tone")) === "light" ? "light" : "dark";
  var base = me && me.src ? me.src.replace(/assets\/js\/hv-loader\.js.*$/, "") : "/";
  var logo = base + (tone === "light" ? "assets/brand/logo.png" : "assets/brand/logo-knockout.webp");
  var reduce = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  var T0 = Date.now();
  var SHOW_AFTER = 600, GONE_BY = 1500;

  /* ================================================================ Helvy */
  var HELVY = window.HVHelvy = (function () {
    var dir = base + "assets/brand/helvy/";
    var CLIPS = { idle: 1, hello: 1, bye: 1, loader: 1, thinking: 1, celebrate: 1, point: 1, cards: 1, stamp: 1 };
    var ua = navigator.userAgent || "";
    // Safari, and every browser on iOS / iPadOS (all WebKit): HEVC with alpha.
    // Safari decodes VP9 but drops its alpha, so it must never get the .webm.
    var apple = /iP(hone|od|ad)/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1) ||
      (/Safari\//.test(ua) && !/Chrome\/|Chromium|CriOS|Edg\/|OPR\/|Firefox\/|Android/.test(ua));
    var still = dir + "helvy-still.webp";
    var watching = [], io = null;

    function src(name) { return dir + "helvy-" + (CLIPS[name] ? name : "idle") + (apple ? ".mov" : ".webm"); }
    function img(cls) {
      var im = document.createElement("img");
      im.className = "hv-clip hv-clip--still" + (cls ? " " + cls : ""); im.alt = ""; im.decoding = "async"; im.src = still;
      im.setAttribute("aria-hidden", "true");
      return im;
    }
    // Autoplay refused (Low Power Mode, data saver, a strict browser): the still
    // takes the video's place, so a play button is never on screen.
    function fallback(v) {
      if (!v.parentNode || v.getAttribute("data-fallback")) return;
      v.setAttribute("data-fallback", "1");
      var im = img(v.getAttribute("data-cls"));
      v.parentNode.replaceChild(im, v);
      try { v.removeAttribute("src"); v.load(); } catch (e) { /* gone */ }
    }
    function play(v) {
      if (!v.isConnected || v.getAttribute("data-fallback") || v.getAttribute("data-off") || document.hidden) return;
      if (!v.getAttribute("src")) { v.src = src(v.getAttribute("data-clip")); }
      if (!v.paused) return;
      var p;
      try { p = v.play(); } catch (e) { return fallback(v); }
      if (p && p.catch) p.catch(function (err) {
        if (err && err.name === "NotAllowedError") fallback(v);
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
    });

    /* video(name, {once, then, seq, cls, eager}) -> <video> (or the still under reduced motion).
       once + then: play `name` once, then loop `then` (hello -> idle).
       seq: a list played one after another, round and round (the "cooking" desk). */
    function video(name, o) {
      o = o || {};
      if (reduce) return img(o.cls);
      var list = o.seq && o.seq.length ? o.seq.slice() : null;
      var v = document.createElement("video");
      // Every attribute that lets a browser autoplay goes on BEFORE the source.
      v.muted = true; v.defaultMuted = true;
      v.setAttribute("muted", ""); v.setAttribute("playsinline", ""); v.setAttribute("webkit-playsinline", "");
      v.setAttribute("autoplay", ""); v.autoplay = true;
      v.setAttribute("disablepictureinpicture", ""); v.setAttribute("disableremoteplayback", "");
      v.setAttribute("aria-hidden", "true"); v.setAttribute("tabindex", "-1");
      v.controls = false; v.preload = "auto"; v.poster = still;
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
        v.setAttribute("data-clip", cur); v.src = src(cur); play(v);
      });
      v.addEventListener("canplay", function () { play(v); });
      v.addEventListener("loadeddata", function () { play(v); });
      v.addEventListener("error", function () { fallback(v); });
      if (o.eager) { v.src = src(cur); setTimeout(function () { play(v); }, 0); }
      // Off screen it neither downloads nor plays; on screen it plays.
      setTimeout(function () { observe(v); }, 0);
      return v;
    }
    return { dir: dir, still: still, head: base + "assets/brand/helvy.webp", apple: apple, src: src, video: video, play: play, img: img };
  })();

  /* =============================================================== loader */
  var css = document.createElement("style");
  css.textContent =
    ".hv-clip::-webkit-media-controls,.hv-clip::-webkit-media-controls-start-playback-button,.hv-clip::-webkit-media-controls-overlay-play-button" +
    "{display:none!important;-webkit-appearance:none;opacity:0!important;}" +
    ".hv-loader{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:center;justify-content:center;" +
    "background:#121212;opacity:0;transition:opacity .22s ease;}" +
    ".hv-loader.is-on{opacity:1;}" +
    ".hv-loader--light{background:#fff;}" +
    ".hv-loader__in{display:flex;flex-direction:column;align-items:center;gap:22px;}" +
    ".hv-loader__pair{display:flex;align-items:flex-end;gap:28px;}" +
    ".hv-loader__logo{width:150px;height:auto;align-self:center;" + (reduce ? "" : "animation:hv-breathe 1.4s ease-in-out infinite;") + "}" +
    ".hv-loader__line{align-self:center;width:1px;height:64px;background:rgba(255,255,255,.18);}" +
    ".hv-loader--light .hv-loader__line{background:rgba(18,18,18,.14);}" +
    ".hv-loader__helvy{position:relative;width:150px;height:150px;}" +
    ".hv-loader__helvy .hv-clip{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;object-position:50% 100%;" +
    "filter:drop-shadow(0 10px 14px rgba(0,0,0,.28));-webkit-mask-image:linear-gradient(#000 80%,transparent);mask-image:linear-gradient(#000 80%,transparent);}" +
    ".hv-loader p{margin:0;font:14px/1.4 'DM Sans',Arial,sans-serif;letter-spacing:.02em;color:rgba(255,255,255,.7);}" +
    ".hv-loader--light p{color:#383838;}" +
    "@media (max-width:600px){.hv-loader__pair{flex-direction:column;align-items:center;gap:16px;}.hv-loader__line{width:64px;height:1px;}}" +
    "@keyframes hv-breathe{50%{opacity:.35}}" +
    "html.hv-loading,html.hv-loading body{overflow:hidden;}";
  (document.head || document.documentElement).appendChild(css);

  var cover = null, shown = false, ready = false, timer = null, capTimer = null;
  function build() {
    cover = document.createElement("div");
    cover.className = "hv-loader" + (tone === "light" ? " hv-loader--light" : "");
    cover.setAttribute("role", "status");
    cover.setAttribute("aria-label", "Loading");
    var img = document.createElement("img");
    img.src = logo; img.alt = "HelloVoice"; img.className = "hv-loader__logo";
    var pair = document.createElement("div");
    pair.className = "hv-loader__pair";
    var line = document.createElement("span");
    line.className = "hv-loader__line"; line.setAttribute("aria-hidden", "true");
    var spot = document.createElement("span");
    spot.className = "hv-loader__helvy"; spot.setAttribute("aria-hidden", "true");
    spot.appendChild(HELVY.video("loader", { eager: true }));
    pair.appendChild(img); pair.appendChild(line); pair.appendChild(spot);
    var words = document.createElement("p");
    words.textContent = "Getting your creators ready";
    var holder = document.createElement("div");
    holder.className = "hv-loader__in";
    holder.appendChild(pair); holder.appendChild(words);
    cover.appendChild(holder);
  }
  function show() {
    if (shown) return;
    if (!cover) build();
    shown = true;
    if (!cover.parentNode) document.documentElement.appendChild(cover);
    cover.style.display = "";
    document.documentElement.classList.add("hv-loading");
    requestAnimationFrame(function () { if (shown) cover.classList.add("is-on"); });
    var v = cover.querySelector("video"); if (v) { v.removeAttribute("data-off"); HELVY.play(v); }
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
  arm(T0);
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
