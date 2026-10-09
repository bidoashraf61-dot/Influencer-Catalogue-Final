/* The page loader, on every catalogue page (Bido, 2026-10-08).
 *
 * The HelloVoice logo breathes on a full-screen cover until the page is
 * ready, with Helvy's loader clip beside it (HELVY Connect, phase D: the
 * clip starts and ends on his smile; reduced motion shows the still), and
 * the page is never shown half-built:
 *   - loaded here, synchronously, in <head>, so the cover is up before the
 *     page draws anything;
 *   - data-tone="dark" is the white logo on ink (catalogue, account),
 *     data-tone="light" the coloured logo on white (selection, campaign
 *     report and dashboard, creator analysis);
 *   - "ready" means: the window has loaded, none of the page's own requests
 *     is still in flight (fetch is counted from here, before any other script
 *     runs), and every image on the first screen has loaded or failed. A
 *     page that ends on its passcode screen or an error message is ready
 *     too, because its requests have finished;
 *   - data-wait="all" (selection, campaign report and dashboard) waits for the
 *     whole page instead of the first screen: every displayed image, lazy
 *     ones included, and every displayed CSS background photo (the creator
 *     cards). Hidden cards (creators outside a selection) are not waited for;
 *   - there is no time limit (Bido's call); a request that fails still ends,
 *     so a broken network shows the page's own error, not an endless logo;
 *   - clicking a link to another catalogue page brings the cover back at
 *     once, so moving between pages always goes logo -> finished page.
 */
(function () {
  "use strict";
  var me = document.currentScript;
  var tone = (me && me.getAttribute("data-tone")) === "light" ? "light" : "dark";
  var waitAll = (me && me.getAttribute("data-wait")) === "all";
  var base = me && me.src ? me.src.replace(/assets\/js\/hv-loader\.js.*$/, "") : "/";
  var logo = base + (tone === "light" ? "assets/brand/logo.png" : "assets/brand/logo-knockout.webp");
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  var css = document.createElement("style");
  css.textContent =
    ".hv-loader{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:center;justify-content:center;" +
    "background:#121212;opacity:1;transition:opacity .28s ease;}" +
    ".hv-loader--light{background:#fff;}" +
    ".hv-loader__in{display:flex;flex-direction:column;align-items:center;gap:28px;}" +
    ".hv-loader__pair{display:flex;align-items:center;gap:28px;}" +
    ".hv-loader__logo{width:150px;height:auto;" + (reduce ? "" : "animation:hv-breathe 1.4s ease-in-out infinite;") + "}" +
    ".hv-loader__line{width:1px;height:64px;background:rgba(255,255,255,.18);}" +
    ".hv-loader--light .hv-loader__line{background:rgba(18,18,18,.14);}" +
    ".hv-loader__helvy{position:relative;width:120px;height:120px;border-radius:50%;overflow:hidden;background:#e4fb78;box-shadow:0 0 0 6px rgba(232,255,118,.14);}" +
    ".hv-loader__helvy video,.hv-loader__helvy img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:50% 30%;}" +
    ".hv-loader p{margin:0;font:14px/1.4 'DM Sans',Arial,sans-serif;letter-spacing:.02em;color:rgba(255,255,255,.66);}" +
    ".hv-loader--light p{color:#4a4a4a;}" +
    "@media (max-width:600px){.hv-loader__pair{flex-direction:column;gap:20px;}.hv-loader__line{width:64px;height:1px;}}" +
    ".hv-loader.is-gone{opacity:0;pointer-events:none;}" +
    "@keyframes hv-breathe{50%{opacity:.35}}" +
    "html.hv-loading,html.hv-loading body{overflow:hidden;}";
  (document.head || document.documentElement).appendChild(css);

  var cover = document.createElement("div");
  cover.className = "hv-loader" + (tone === "light" ? " hv-loader--light" : "");
  cover.setAttribute("role", "status");
  cover.setAttribute("aria-label", "Loading");
  var img = document.createElement("img");
  img.src = logo; img.alt = "HelloVoice"; img.className = "hv-loader__logo";
  var pair = document.createElement("div");
  pair.className = "hv-loader__pair";
  var line = document.createElement("span");
  line.className = "hv-loader__line"; line.setAttribute("aria-hidden", "true");
  var disc = document.createElement("span");
  disc.className = "hv-loader__helvy"; disc.setAttribute("aria-hidden", "true");
  var hdir = base + "assets/brand/helvy/";
  if (reduce) {
    var still = document.createElement("img");
    still.src = hdir + "helvy-smile-full.webp"; still.alt = "";
    disc.appendChild(still);
  } else {
    var clip = document.createElement("video");
    clip.muted = true; clip.loop = true; clip.autoplay = true;
    clip.setAttribute("muted", ""); clip.setAttribute("playsinline", ""); clip.poster = hdir + "helvy-poster.webp";
    clip.innerHTML = '<source src="' + hdir + 'helvy-loader.webm" type="video/webm"/><source src="' + hdir + 'helvy-loader.mp4" type="video/mp4"/>';
    disc.appendChild(clip);
    var pp = clip.play && clip.play(); if (pp && pp.catch) pp.catch(function () { /* the poster stays */ });
  }
  pair.appendChild(img); pair.appendChild(line); pair.appendChild(disc);
  var words = document.createElement("p");
  words.textContent = "Getting your creators ready";
  var holder = document.createElement("div");
  holder.className = "hv-loader__in";
  holder.appendChild(pair); holder.appendChild(words);
  cover.appendChild(holder);
  document.documentElement.appendChild(cover);
  document.documentElement.classList.add("hv-loading");

  /* -- count the page's own requests -- */
  var inflight = 0, lastEnd = Date.now();
  if (window.fetch) {
    var realFetch = window.fetch;
    window.fetch = function () {
      inflight++;
      var done = function () { inflight = Math.max(0, inflight - 1); lastEnd = Date.now(); };
      try {
        var p = realFetch.apply(this, arguments);
        p.then(done, done);
        return p;
      } catch (e) { done(); throw e; }
    };
  }

  function firstScreenImages() {
    var out = [], h = window.innerHeight || 800, w = window.innerWidth || 1200;
    var imgs = document.images;
    for (var i = 0; i < imgs.length; i++) {
      var el = imgs[i];
      if (el === img || !el.getAttribute("src") || el.closest(".hv-loader")) continue;
      var r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > h || r.right < 0 || r.left > w) continue;
      if (getComputedStyle(el).visibility === "hidden") continue;
      out.push(el);
    }
    return out;
  }

  // The whole page: every displayed <img> (lazy ones switched to eager so
  // they actually load) and every displayed element's inline background photo.
  function shown(el) {
    if (el.closest(".hv-loader")) return false;
    if (el.offsetParent === null && getComputedStyle(el).position !== "fixed") return false;
    return getComputedStyle(el).visibility !== "hidden";
  }
  function wholePage() {
    var waits = [];
    Array.prototype.forEach.call(document.images, function (el) {
      if (el === img || !el.getAttribute("src") || !shown(el)) return;
      if (el.loading === "lazy") el.loading = "eager";
      if (!el.complete) waits.push(el);
    });
    var seen = {};
    Array.prototype.forEach.call(document.querySelectorAll("[style*='background-image']"), function (el) {
      if (!shown(el)) return;
      var m = /url\((['"]?)(.*?)\1\)/.exec(el.style.backgroundImage || "");
      if (!m || !m[2] || seen[m[2]]) return;
      seen[m[2]] = 1;
      var probe = new Image();
      probe.src = m[2];
      if (!probe.complete) waits.push(probe);
    });
    return waits;
  }

  var loaded = document.readyState === "complete", gone = false;
  window.addEventListener("load", function () { loaded = true; });

  function hide() {
    if (gone) return;
    gone = true;
    cover.classList.add("is-gone");
    document.documentElement.classList.remove("hv-loading");
    var v = cover.querySelector("video"); if (v && v.pause) v.pause();
    setTimeout(function () { if (gone) cover.style.display = "none"; }, 320);
  }
  function show() {
    gone = false;
    cover.style.display = "";
    cover.classList.remove("is-gone");
    document.documentElement.classList.add("hv-loading");
    var v = cover.querySelector("video"); if (v && v.play) { var q = v.play(); if (q && q.catch) q.catch(function () {}); }
  }

  // Ready = loaded, no request in flight for a short beat (pages often chain
  // a second request off the first), and the first screen's images settled.
  function check() {
    if (gone) return;
    if (!loaded || inflight > 0 || Date.now() - lastEnd < 350) { setTimeout(check, 120); return; }
    var pending = waitAll ? wholePage() : firstScreenImages().filter(function (el) { return !el.complete; });
    if (!pending.length) { hide(); return; }
    var left = pending.length;
    pending.forEach(function (el) {
      var one = function () { if (--left <= 0) check(); };
      el.addEventListener("load", one, { once: true });
      el.addEventListener("error", one, { once: true });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { setTimeout(check, 60); });
  else setTimeout(check, 60);

  /* -- moving between pages: the cover comes back before the next page -- */
  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
    var url;
    try { url = new URL(a.getAttribute("href"), location.href); } catch (x) { return; }
    if (url.origin !== location.origin || /^\/admin(\/|$)/.test(url.pathname)) return;
    // A jump within this page (or only the #fragment changing) is not a page move.
    if (url.pathname === location.pathname && url.search === location.search) return;
    // Let the page's own handlers run first; a link they took over stays put.
    setTimeout(function () { if (!e.defaultPrevented) show(); }, 0);
  });
  // Coming back with the browser's Back button from its cache: drop the cover.
  window.addEventListener("pageshow", function (e) { if (e.persisted) hide(); });
})();
