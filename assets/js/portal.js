/* Client portal layer for the catalogue pages.
 *
 *  - Gate: email sign-in with a one-time code (company addresses only), then a
 *    one-time profile step. The old access-code form stays one click away.
 *    Success reloads the page; the page's own script then finds the session
 *    cookie and unlocks itself, so every page that has a gate works unchanged.
 *  - Account circle: initials top right, opening a menu (profile, campaigns,
 *    credits, admin, sign out), shown once signed in.
 *  - Voice: the character in the corner; a chat that greets, then gets tasks done.
 *  - Brief wizard: a few multiple-choice questions (or one sentence the AI turns
 *    into answers), then a scored shortlist saved as a real selection.
 *
 * Everything the user or the server sends is put on the page with textContent,
 * never as HTML. The API key lives on the server; this file holds no secrets.
 */
(function () {
  "use strict";

  var script = document.currentScript;
  var SRC = script && script.src ? script.src : "";
  var ROOT = SRC ? SRC.replace(/assets\/js\/portal\.js.*$/, "") : "./";
  var CFGS = window.CATALOGUE_CONFIG || window.CAMPAIGN_CONFIG || {};
  var API = (CFGS.api != null ? CFGS.api : "/admin").replace(/\/$/, "");
  var ME = null;
  // A few hooks other pages use (the account page): talk, setPhoto, icon, noteRow, when.
  var HV = window.hvPortal = window.hvPortal || {};

  /* ------------------------------------------------------------ ui icons */
  // One drawn set (24px grid, 1.8 stroke) for the bell, the profile page, selection
  // statuses and the analysis lock, so every page speaks the same marks.
  var UI_PATHS = {
    bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l1.6 2H4.4z"/><path d="M10 20.5a2.2 2.2 0 0 0 4 0"/>',
    check: '<path d="M4.5 12.5l5 5 10-11"/>', x: '<path d="M6 6l12 12M18 6L6 18"/>',
    lock: '<rect x="4.5" y="10.5" width="15" height="10" rx="2.5"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/><path d="M12 14.5v2.5"/>',
    unlock: '<rect x="4.5" y="10.5" width="15" height="10" rx="2.5"/><path d="M8 10.5V8a4 4 0 0 1 7.6-1.7"/><path d="M12 14.5v2.5"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>', arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    back: '<path d="M15 5l-7 7 7 7"/>', chart: '<path d="M4 19V10M10 19V5M16 19v-6M22 19H2"/>',
    home: '<path d="M4 11l8-6.5 8 6.5"/><path d="M6 9.5V19h12V9.5"/>',
    list: '<rect x="3.5" y="4.5" width="7" height="7" rx="2"/><rect x="13.5" y="4.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><path d="M14 17h6M17 14v6"/>',
    scan: '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.4-4.4"/><path d="M8.5 12.5V11M11 12.5V9M13.5 12.5v-2.5"/>',
    mega: '<path d="M4 10v4h3l7 4.5V5.5L7 10z"/><path d="M17.5 9a4 4 0 0 1 0 6"/>',
    brief: '<path d="M7 3.5h7l4.5 4.5v12.5h-11.5z"/><path d="M14 3.5V8h4.5M9.5 12.5h6M9.5 16h4"/>',
    coin: '<circle cx="12" cy="12" r="8.5"/><path d="M14.6 9.2c-.5-.8-1.5-1.2-2.6-1.2-1.6 0-2.7.8-2.7 2s1.1 1.7 2.7 2 2.8.8 2.8 2-1.2 2-2.8 2c-1.2 0-2.2-.5-2.7-1.3M12 6.5v1.5M12 16v1.5"/>',
    user: '<circle cx="12" cy="8.5" r="3.8"/><path d="M4.5 20c.8-3.6 3.8-5.6 7.5-5.6s6.7 2 7.5 5.6"/>',
    steth: '<path d="M5.5 3.5H4.8v4.8a4.2 4.2 0 0 0 8.4 0V3.5h-.7"/><path d="M9 12.5v2.2a5 5 0 0 0 10 0v-2.4"/><circle cx="19" cy="10.3" r="2"/>',
    out: '<path d="M14 4.5H6.5v15H14"/><path d="M10.5 12H20M16.5 8.5L20 12l-3.5 3.5"/>',
    camera: '<path d="M4 8.5h3l1.6-2.5h6.8L17 8.5h3V19H4z"/><circle cx="12" cy="13.2" r="3.4"/>',
    "case": '<rect x="3.5" y="7.5" width="17" height="12" rx="2.5"/><path d="M9 7.5V5.5h6v2M3.5 12.5h17"/>',
    phone: '<rect x="7" y="3" width="10" height="18" rx="2.5"/><path d="M11 17.5h2"/>',
    image: '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><circle cx="9" cy="10" r="1.8"/><path d="M20.5 16l-5-5-8.5 8.5"/>',
    tag: '<path d="M3.5 12.2V4.5h7.7l9.3 9.3-7.7 7.7z"/><circle cx="8" cy="9" r="1.5"/>',
    globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.4 3.5 5.2 3.5 8.5s-1.1 6.1-3.5 8.5c-2.4-2.4-3.5-5.2-3.5-8.5s1.1-6.1 3.5-8.5z"/>',
    gift: '<rect x="4" y="10" width="16" height="10" rx="1.5"/><path d="M3 7h18v3H3zM12 7v13M12 7c-1-2.6-4.6-3.6-5-1.4C6.6 7.4 10 7 12 7zM12 7c1-2.6 4.6-3.6 5-1.4.4 1.8-3 1.4-5 1.4z"/>',
    info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.6v.2"/>', down: '<path d="M6 9l6 6 6-6"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    link: '<path d="M10 13.5a3.5 3.5 0 0 0 5 0l3-3a3.5 3.5 0 0 0-5-5l-1 1"/><path d="M14 10.5a3.5 3.5 0 0 0-5 0l-3 3a3.5 3.5 0 0 0 5 5l1-1"/>',
    swap: '<path d="M4 8.5h13.5M14 5l3.5 3.5L14 12M20 15.5H6.5M10 19l-3.5-3.5L10 12"/>',
    ban: '<circle cx="12" cy="12" r="8.5"/><path d="M6 6l12 12"/>',
    spark: '<path d="M12 3.5v4M12 16.5v4M3.5 12h4M16.5 12h4M6 6l2.6 2.6M15.4 15.4L18 18M6 18l2.6-2.6M15.4 8.6L18 6"/>',
    // HELVY Connect C + D
    shield: '<path d="M12 3.5l7 2.8v5.2c0 4.4-3 7.9-7 9-4-1.1-7-4.6-7-9V6.3z"/><path d="M9 12l2.2 2.2L15.5 10"/>',
    mail: '<rect x="3.5" y="5.5" width="17" height="13" rx="2.5"/><path d="M4.5 7l7.5 6 7.5-6"/>',
    calc: '<rect x="5" y="3" width="14" height="18" rx="2.5"/><path d="M8.5 7h7M8.5 11h.01M12 11h.01M15.5 11h.01M8.5 14.5h.01M12 14.5h.01M15.5 14.5v3M8.5 17.5h.01M12 17.5h.01"/>',
    save: '<path d="M6 3.5h9.5l3 3V20.5H6z"/><path d="M9 3.5v5h6v-5M9 20.5v-6h6v6"/>',
    dl: '<path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 19.5h14"/>',
    help: '<circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.5a2.5 2.5 0 0 1 4.8.8c0 1.7-2.4 2.1-2.4 3.6M12 17v.2"/>',
    minus: '<path d="M5 12h14"/>', chat: '<path d="M4.5 5.5h15v10.5h-8.2l-4.3 3.5V16h-2.5z"/><path d="M8.5 10.8h.01M12 10.8h.01M15.5 10.8h.01"/>', search: '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.4-4.4"/>',
    filter: '<path d="M4 6h16M7 12h10M10 18h4"/>',
    // HELVY Connect phase E
    upload: '<path d="M12 15.5V4.5M7.5 9L12 4.5 16.5 9"/><path d="M4.5 15v4.5h15V15"/>',
    cal: '<rect x="3.5" y="5" width="17" height="15.5" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/><path d="M7.5 14h3v3h-3z"/>',
    bulb: '<path d="M9 17.5h6M10 21h4"/><path d="M12 3.5a6 6 0 0 0-3.6 10.8c.7.6 1.1 1.4 1.1 2.2v1h5v-1c0-.8.4-1.6 1.1-2.2A6 6 0 0 0 12 3.5z"/>',
    copy: '<rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5"/>',
    redo: '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4h-4"/>',
    flag: '<path d="M5.5 21V4M5.5 4.5h11l-2 4 2 4h-11"/>',
    mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
    target: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1" fill="currentColor"/>',
    sparkle: '<path d="M12 3.5l1.9 5.1 5.1 1.9-5.1 1.9-1.9 5.1-1.9-5.1-5.1-1.9 5.1-1.9z"/><path d="M18.5 16l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/>',
    ig: '<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4.1"/><circle cx="17.3" cy="6.7" r="1.15" fill="currentColor" stroke="none"/>',
    tt: '<path d="M14.2 3v11.6a3.6 3.6 0 1 1-3.6-3.6"/><path d="M14.2 3.2c.45 2.7 2.05 4.3 4.75 4.6"/>',
    sc: '<path d="M12 3.2c2.4 0 4 1.7 4 4.1 0 1 .1 1.7.3 2.1.3.4.9.4 1.4.3.4-.1.8.2.8.6 0 .5-.6.8-1.2 1-.3.1-.4.3-.3.6.4 1.2 1.6 2.4 3 2.7.3.1.4.4.2.6-.5.6-1.6.9-2.5 1-.2.5-.3 1-.9 1-.5 0-1-.3-1.8-.3-1.1 0-1.6 1.1-3 1.1s-1.9-1.1-3-1.1c-.8 0-1.3.3-1.8.3-.6 0-.7-.5-.9-1-.9-.1-2-.4-2.5-1-.2-.2-.1-.5.2-.6 1.4-.3 2.6-1.5 3-2.7.1-.3 0-.5-.3-.6-.6-.2-1.2-.5-1.2-1 0-.4.4-.7.8-.6.5.1 1.1.1 1.4-.3.2-.4.3-1.1.3-2.1 0-2.4 1.6-4.1 4-4.1z"/>',
    yt: '<rect x="2.5" y="5.5" width="19" height="13" rx="4"/><path d="M10 9.2v5.6l4.8-2.8z"/>'
  };
  function icon(name, cls) {
    return '<svg class="hv-i' + (cls ? " " + cls : "") + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + (UI_PATHS[name] || "") + "</svg>";
  }
  HV.icon = icon;
  // Helvy's files are named in ONE place: window.HVHelvy in hv-loader.js (every page loads it first).
  // Transparent cut-outs framed waist-up; HV.helvy is the transparent head still (small avatars).
  var HVH = window.HVHelvy || null;
  HV.helvy = HVH ? HVH.head : ROOT + "assets/brand/helvy.webp?v=c2";
  var REDUCE = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  // clip(name, cls, {once, then, seq, still}) -> a frame holding Helvy. Autoplay and loop are
  // forced (muted, playsinline, set before the source) and a refused autoplay shows the still.
  function clip(name, cls, opts) {
    opts = opts || {};
    var box = document.createElement("span");
    box.className = "cx-hd" + (cls ? " " + cls : "");
    box.setAttribute("aria-hidden", "true");
    if (!HVH || REDUCE || opts.still) {
      var im = document.createElement("img");
      im.className = "hv-clip hv-clip--still"; im.alt = ""; im.decoding = "async";
      im.src = HVH ? HVH.still : ROOT + "assets/brand/helvy/helvy-still.webp";
      box.appendChild(im);
      return box;
    }
    box.appendChild(HVH.video(name, { once: opts.once, then: opts.then, seq: opts.seq }));
    return box;
  }
  HV.clip = clip;
  // lime(kind, cls) -> Helvy head-and-shoulders on a lime disc, from the "voice" set (fix batch 4).
  // Used where he reacts to what the client does: the AI shortlist card, its "Building" stage and
  // the selection's "Add more like these". Expressive, short clips instead of the cut-out's slow
  // idle, and opaque H.264 / VP9, so they play in Safari and Chrome alike.
  //   frame.loop(kind)          loop one clip (no-op when it already loops)
  //   frame.react(kind, then)   play a reaction once, then loop `then` ON THE SAME <video>: an
  //                             element a tap has started stays allowed to play in Safari's Low
  //                             Power Mode, so the loop after a reaction never freezes there
  //   onEnd                     optional callback when the reaction has played
  // A new clip is laid over the old one, which goes once the new one draws (a source swap on a
  // visible element flashed blank frames in Chrome). Reduced motion: the lime still.
  var LIME = { loop: "loop", wave: "loop", idle: "loop", point: "point-act", think: "think", thumbs: "thumbs-act",
               cheer: "cheer-act", celebrate: "cheer", scan: "scan" };
  function lime(kind, cls, opts) {
    opts = opts || {};
    var frame = document.createElement("span");
    frame.className = "hv-lime" + (cls ? " " + cls : "");
    frame.setAttribute("aria-hidden", "true");
    if (!HVH || REDUCE) {
      var im = document.createElement("img");
      im.className = "hv-clip hv-clip--still"; im.alt = ""; im.decoding = "async";
      im.src = HVH ? HVH.vstill : ROOT + "assets/brand/voice/voice-loop-poster.webp";
      frame.appendChild(im);
      frame.loop = frame.react = function (k, t, cb) { if (typeof t === "function") cb = t; if (cb) setTimeout(cb, 0); };
      frame.reset = function () {};
      return frame;
    }
    var now = null, looping = false;
    function put(name, o) {
      var v = HVH.video(LIME[name] || name, { set: "voice", once: o.once, then: o.then ? (LIME[o.then] || o.then) : null, eager: true });
      var old = [].slice.call(frame.querySelectorAll("video, img"));
      var gone = false;
      var drop = function () { if (gone) return; gone = true; old.forEach(function (x) { if (x.pause) try { x.pause(); } catch (e) { /* gone */ } x.remove(); }); };
      v.addEventListener("playing", drop, { once: true });
      setTimeout(drop, 900);
      frame.appendChild(v);
      HVH.play(v);                              // inside the tap that asked for it, when there is one
      return v;
    }
    frame.loop = function (name) {
      if (looping && now === (LIME[name] || name)) return;
      now = LIME[name] || name; looping = true;
      put(name, {});
    };
    frame.react = function (name, then, onEnd) {
      if (typeof then === "function") { onEnd = then; then = null; }
      then = then || "loop";
      now = LIME[then] || then; looping = true;      // what the same element loops once the reaction ends
      var v = put(name, { once: true, then: then }), fired = false;
      var fin = function () { if (fired) return; fired = true; if (onEnd) onEnd(); };
      v.addEventListener("ended", fin, { once: true });
      setTimeout(fin, 3600);                       // a reaction that never started still hands over
    };
    frame.reset = function () { looping = false; now = null; };   // paused by the page: the next loop() starts afresh
    if (kind) frame.loop(kind);
    return frame;
  }
  HV.lime = lime;
  // "Cooking": Helvy at the director's desk while the AI works (thinking -> flipping through
  // creator cards -> pressing a green check on a card, round and round) with a rotating step line. Used by
  // Add more like these, Creators like this and Find a replacement; the AI shortlist card has
  // the same sequence in its own stage.
  var COOK_SEQ = ["thinking", "cards", "approve"];   // the director's desk, the one definition
  var COOK_STEPS = ["Reading your brief…", "Flipping through creators…", "Scoring fit…", "Approving your picks…"];
  HV.cooking = function (opts) {
    opts = opts || {};
    if (opts.list) return cookingSteps(opts);
    var steps = opts.steps || COOK_STEPS, i = 0, seen = false;
    var el = document.createElement("div");
    el.className = "cx-cook" + (opts.compact ? " cx-cook--compact" : "") + (opts.dark ? " cx-cook--dark" : "");
    el.setAttribute("role", "status"); el.setAttribute("aria-live", "polite");
    el.appendChild(clip("thinking", "cx-cook__hv", { seq: COOK_SEQ }));
    var tx = document.createElement("div"); tx.className = "cx-cook__tx";
    var now = document.createElement("p"); now.className = "cx-think__now cx-cook__now"; now.textContent = steps[0];
    var dots = document.createElement("ol"); dots.className = "cx-cook__dots"; dots.setAttribute("aria-hidden", "true");
    steps.forEach(function (_, k) { var li = document.createElement("li"); if (!k) li.className = "is-now"; dots.appendChild(li); });
    tx.appendChild(now); tx.appendChild(dots); el.appendChild(tx);
    var t = setInterval(function () {
      if (el.isConnected) seen = true; else if (seen) { clearInterval(t); return; }
      if (i >= steps.length - 1 && opts.hold) return;
      i = (i + 1) % steps.length; now.textContent = steps[i];
      [].forEach.call(dots.children, function (li, k) { li.className = k < i ? "is-done" : k === i ? "is-now" : ""; });
    }, 1700);
    el.stop = function () { clearInterval(t); };
    return el;
  };
  // The bigger "cooking" (fix batch 3, Add more like these): the AI shortlist card's wait in
  // small. Helvy at his desk (thinking -> cards -> approve) beside named steps that light up one
  // by one, a live line and a bar. The last step holds until the work is done; finish() lights
  // everything and returns a promise that settles once the client has seen it.
  function cookingSteps(opts) {
    var steps = opts.steps || COOK_STEPS, k = 0, seen = false;
    var el = document.createElement("div");
    el.className = "cx-cook cx-cook--steps" + (opts.dark ? " cx-cook--dark" : "") + (opts.helvy === false ? " cx-cook--bare" : "");
    el.setAttribute("role", "status"); el.setAttribute("aria-live", "polite");
    // helvy: false when the caller's own Helvy acts out the work beside it (Add more like these).
    if (opts.helvy !== false) el.appendChild(clip("thinking", "cx-cook__hv", { seq: COOK_SEQ }));
    var tx = document.createElement("div"); tx.className = "cx-cook__tx";
    if (opts.title) { var t = document.createElement("p"); t.className = "cx-cook__title"; t.textContent = opts.title; tx.appendChild(t); }
    var list = document.createElement("ol"); list.className = "ai-sl__list cx-cook__list";
    steps.forEach(function (s) {
      var li = document.createElement("li"); li.className = "ai-sl__st";
      li.innerHTML = '<span class="ai-sl__st-dot"></span><span></span>'; li.lastChild.textContent = s;
      list.appendChild(li);
    });
    var bar = document.createElement("div"); bar.className = "ai-sl__bar"; bar.appendChild(document.createElement("i"));
    tx.appendChild(list); tx.appendChild(bar); el.appendChild(tx);
    function paint() {
      [].forEach.call(list.children, function (li, i) { li.className = "ai-sl__st" + (i < k ? " is-done" : i === k ? " is-now" : ""); });
      bar.firstChild.style.width = Math.max(4, Math.round(Math.min(k, steps.length) / steps.length * 100)) + "%";
    }
    paint();
    var timer = setInterval(function () {
      if (el.isConnected) seen = true; else if (seen) { clearInterval(timer); return; }
      if (k < steps.length - 1) { k++; paint(); }
    }, REDUCE ? 400 : 1400);
    el.stop = function () { clearInterval(timer); };
    el.finish = function () {
      clearInterval(timer);
      return new Promise(function (res) {
        (function next() {
          if (k < steps.length) { k++; paint(); setTimeout(next, REDUCE ? 0 : 260); } else setTimeout(res, REDUCE ? 0 : 450);
        })();
      });
    };
    return el;
  }
  HV.reduce = REDUCE;
  HV.root = ROOT; HV.apiBase = API;
  HV.h = function () { return h.apply(null, arguments); };
  HV.api = function (m, p, b) { return api(m, p, b); };
  HV.followers = function (n) { return followers(n); };
  HV.setCredits = function (n) { return setCredits(n); };
  // connect.css / connect.js (HELVY Connect C + D) ride along with this file on every page.
  (function () {
    var v = (/[?&]v=([0-9a-z]+)/.exec(SRC) || [])[1];
    if (!document.querySelector('link[href*="assets/css/connect.css"]')) {
      var l = document.createElement("link"); l.rel = "stylesheet"; l.href = ROOT + "assets/css/connect.css" + (v ? "?p=" + v : "");
      document.head.appendChild(l);
    }
    if (!document.querySelector('script[src*="assets/js/connect.js"]')) {
      var sc = document.createElement("script"); sc.src = ROOT + "assets/js/connect.js" + (v ? "?p=" + v : ""); sc.defer = true;
      document.head.appendChild(sc);
    }
  })();

  /* ------------------------------------------------------- notifications */
  var NOTE_ICON = { selections: ["list", "sel"], analysis: ["scan", "ana"], campaigns: ["mega", "cmp"], account: ["coin", "acc"], ideas: ["spark", "sug"] };
  var KIND_ICON = { unavailable: "ban", colleague: "user" };
  function when(ts) {
    var s = Date.now() / 1000 - ts;
    if (s < 60) return "now";
    if (s < 3600) return Math.floor(s / 60) + " min";
    var d = new Date(ts * 1000), today = new Date();
    if (s < 86400 && d.getDate() === today.getDate()) return Math.floor(s / 3600) + " h";
    var y = new Date(today); y.setDate(today.getDate() - 1);
    if (d.toDateString() === y.toDateString()) return "Yesterday";
    return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  }
  HV.when = when;
  // One notification row, the same in the bell, on Overview and in the full list.
  // Server text goes in as text, never HTML.
  function noteRow(n, onOpen) {
    var ic = NOTE_ICON[n.group] || NOTE_ICON.account;
    var a = document.createElement(n.href ? "a" : "div");
    a.className = "hv-note" + (n.unread ? " is-new" : "");
    if (n.href) a.href = ROOT + n.href;
    var icn = document.createElement("span");
    icn.className = "hv-note__ic hv-note__ic--" + ic[1];
    icn.innerHTML = icon(KIND_ICON[n.kind] || ic[0]);
    var tx = document.createElement("span");
    tx.className = "hv-note__tx";
    var b = document.createElement("b"); b.textContent = n.title; tx.appendChild(b);
    if (n.rest) tx.appendChild(document.createTextNode(n.rest));
    if (n.body) { var sm = document.createElement("small"); sm.textContent = n.body; tx.appendChild(sm); }
    var w = document.createElement("span");
    w.className = "hv-note__when";
    w.textContent = when(n.at);
    if (n.unread) { var dot = document.createElement("span"); dot.className = "hv-note__unread"; dot.setAttribute("role", "img"); dot.setAttribute("aria-label", "Unread"); w.appendChild(dot); }
    a.appendChild(icn); a.appendChild(tx); a.appendChild(w);
    a.addEventListener("click", function (e) {
      if (!n.unread) return;
      n.unread = false;
      var go = a.href;
      if (go) e.preventDefault();
      fetch(API + "/api/notifications/read", { method: "POST", credentials: "include", keepalive: true,
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids: [n.id] }) })
        .catch(function () {}).then(function () { if (onOpen) onOpen(n); if (go) location.href = go; });
    });
    return a;
  }
  HV.noteRow = noteRow;

  /* ------------------------------------------------------------- language */
  // English by default, Arabic for an Arabic browser or when chosen. Every static string goes
  // through T() inside h(), so a missing translation simply stays English.
  // The portal is English only for now (Bido, 2026-10-08). The chat assistant still replies in
  // whatever language the client writes. The Arabic table below is kept for later: set LANG to "ar".
  var LANG = "en";
  try { localStorage.removeItem("hv_lang"); } catch (e) { /* blocked */ }
  var AR = {
    "Sign in with your work email. We'll send a one-time code. No password needed.": "سجّل الدخول ببريد العمل. سنرسل لك رمزاً لمرة واحدة، بدون كلمة مرور.",
    "Email me a code": "أرسل لي الرمز", "Work email": "بريد العمل", "Verify and continue": "تحقق وتابع",
    "Send a new code": "أرسل رمزاً جديداً", "Use a different email": "استخدم بريداً آخر", "Your name": "الاسم",
    "Company": "الشركة", "Job title (optional)": "المسمى الوظيفي (اختياري)", "Phone (optional)": "الجوال (اختياري)",
    "Create my account": "أنشئ حسابي", "I have an access code instead": "لديّ رمز دخول بدلاً من ذلك",
    "Sign in with email instead": "الدخول بالبريد بدلاً من ذلك", "Enter a valid work email address.": "أدخل بريد عمل صحيحاً.",
    "Email confirmed. Tell us who you are.": "تم تأكيد البريد. عرّفنا بنفسك.", "Welcome. Opening the catalogue…": "أهلاً بك. جارٍ فتح الكتالوج…",
    "Please wait…": "يرجى الانتظار…", "Enter the 6-digit code.": "أدخل الرمز المكوّن من 6 أرقام.",
    "Too many requests. Please wait a few minutes.": "طلبات كثيرة. انتظر بضع دقائق.", "Too many attempts. Please wait a few minutes.": "محاولات كثيرة. انتظر بضع دقائق.",
    "Find creators": "ابحث عن مؤثرين", "Ask": "اسأل", "Account": "الحساب", "Admin": "المسؤول", "My account": "حسابي",
    "Review your brief": "راجع الملخص", "Describe your campaign in a sentence and our AI will fill the questions. Or answer them yourself below.":
      "صف حملتك في جملة وسيملأ الذكاء الاصطناعي الأسئلة، أو أجب عنها بنفسك بالأسفل.",
    "Fill it in for me": "املأها عني", "Reading your brief…": "جارٍ قراءة طلبك…", "or answer a few questions": "أو أجب عن بعض الأسئلة",
    "Back": "رجوع", "Next": "التالي", "Next / skip": "التالي / تخطَّ", "Review": "مراجعة", "Show my creators": "اعرض المؤثرين",
    "Matching creators…": "جارٍ مطابقة المؤثرين…", "Edit": "تعديل", "change": "تغيير", "Please choose an answer to continue.": "اختر إجابة للمتابعة.",
    "This is what we'll match creators against.": "هذا ما سنطابق المؤثرين عليه.", "We read your brief. Check it and change anything that's off.":
      "قرأنا طلبك. راجعه وعدّل ما يلزم.", "Not answered": "لم تتم الإجابة", "Describe the campaign in a sentence or two.": "صف الحملة في جملة أو جملتين.",
    "Close": "إغلاق", "Your shortlist": "قائمتك المختصرة", "Open as selection": "افتحها كقائمة", "Refine brief": "عدّل الطلب",
    "Measured": "مُقاس", "Public data": "بيانات عامة", "Estimated": "تقديري", "Price on request": "السعر عند الطلب",
    "Scores come from our data. Written reasons weren't generated this time.": "الدرجات من بياناتنا. لم تُكتب الأسباب هذه المرة.",
    "Ask HelloVoice AI": "اسأل مساعد هلا فويس", "Send": "إرسال", "Ask about creators, prices or your campaign…": "اسأل عن المؤثرين أو الأسعار أو حملتك…",
    "Thinking…": "جارٍ التفكير…", "Build my shortlist": "ابنِ قائمتي", "Ask the assistant": "اسأل المساعد", "Change answers": "غيّر الإجابات",
    "Your brief": "ملخص طلبك", "Skip": "تخطَّ", "Plan a campaign with me": "خطط حملة معي",
    "Suggest creators for a skincare launch in KSA": "اقترح مؤثرين لإطلاق منتج عناية بالبشرة في السعودية",
    "What does a campaign cost?": "كم تكلفة الحملة؟", "What happens after I pick a selection?": "ماذا يحدث بعد اختيار القائمة؟",
    "AI credits": "رصيد الذكاء الاصطناعي", "credits left": "رصيد متبقٍ", "My briefs": "طلباتي", "My campaigns": "حملاتي",
    "Open campaign tracking": "افتح متابعة الحملات", "My details": "بياناتي", "Name": "الاسم", "Job title": "المسمى الوظيفي", "Phone": "الجوال",
    "Save": "حفظ", "Saved": "تم الحفظ", "Sign out": "تسجيل الخروج", "My team": "فريقي", "Team selections": "قوائم الفريق",
    "Request more credits": "اطلب رصيداً إضافياً", "Download my data": "حمّل بياناتي", "Delete my account": "احذف حسابي", "Open": "فتح",
    "Score this selection": "قيّم هذه القائمة", "Answer a few quick questions about the campaign and we'll score every creator in it. Free.":
      "أجب عن أسئلة سريعة عن الحملة وسنقيّم كل مؤثر في القائمة. مجاناً.", "Not now": "ليس الآن", "Answer questions": "أجب عن الأسئلة",
    "Score my selection": "قيّم قائمتي", "Fit scores shown": "درجات الملاءمة ظاهرة", "Hide scores": "إخفاء الدرجات",
    "Request sent. The HelloVoice team will top you up shortly.": "تم إرسال الطلب. سيضيف فريق هلا فويس الرصيد قريباً.",
    "You're out of AI credits. Contact the HelloVoice team to top up.": "نفد رصيدك. تواصل مع فريق هلا فويس لإعادة الشحن.",
    "That code isn't right.": "الرمز غير صحيح.", "That code has expired. Request a new one.": "انتهت صلاحية الرمز. اطلب رمزاً جديداً.",
    "Too many wrong tries. Request a new code.": "محاولات خاطئة كثيرة. اطلب رمزاً جديداً.",
    "Please use your company email address. Personal addresses such as Gmail or Outlook can't be used.": "استخدم بريد شركتك. لا يمكن استخدام البريد الشخصي مثل Gmail أو Outlook.",
    "Please enter your name and company.": "أدخل اسمك واسم الشركة.", "Colleagues": "الزملاء", "Language": "اللغة"
  };
  function T(s) { return LANG === "ar" && AR[s] ? AR[s] : s; }
  // Question and option labels from the server, by id and value.
  var QAR = {
    goal: ["ما الهدف الرئيسي من الحملة؟", { awareness: "الوصول لأكبر عدد من الناس", engagement: "زيادة التفاعل", traffic: "زيارات ونقرات على الرابط", conversion: "زيادة المبيعات أو التسجيلات", balanced: "مزيج متوازن" }],
    platforms: ["أين سيُنشر المحتوى؟", { any: "لا تفضيل" }],
    market: ["في أي دولة الجمهور؟", { SA: "السعودية", AE: "الإمارات", EG: "مصر", KW: "الكويت", QA: "قطر", BH: "البحرين", OM: "عُمان", JO: "الأردن" }],
    gender: ["من الجمهور؟", { Any: "الجميع", Women: "غالباً نساء", Men: "غالباً رجال" }],
    age: ["الفئة العمرية الرئيسية", { Any: "كل الأعمار", "45-54": "45+" }],
    category: ["في أي مجال المنتج؟", { "health care": "الرعاية الصحية / الأدوية", skincare: "العناية بالبشرة والجلدية", beauty: "التجميل", "hair care": "العناية بالشعر",
      fragrance: "العطور", "mother & baby": "الأم والطفل", food: "الأغذية والمشروبات", fitness: "اللياقة والصحة", fashion: "الأزياء", lifestyle: "أسلوب الحياة",
      technology: "التقنية", automotive: "السيارات", travel: "السفر", finance: "المال", gaming: "الألعاب" }],
    budget: ["ميزانية المؤثرين (ريال، قبل الضريبة)", { "50": "أقل من 50,000", "150": "50,000 – 150,000", "400": "150,000 – 400,000", "400+": "أكثر من 400,000", open: "لم تُحدد بعد" }],
    count: ["كم عدد المؤثرين؟", { "25": "20 أو أكثر" }],
    deliverable: ["ما المطلوب منهم؟", { reels: "ريلز / فيديوهات قصيرة", ugc: "محتوى UGC لقنواتنا", stories: "ستوري", event: "حضور فعالية أو متجر", review: "مراجعة منتج" }],
    timing: ["متى تبدأ؟", { asap: "خلال أسبوعين", month: "خلال 6 أسابيع", quarter: "الربع القادم", later: "نستكشف فقط" }],
    notes: ["هل هناك ما يجب أن نعرفه؟", {}]
  };
  function localise(qs) {
    if (LANG !== "ar") return qs;
    return qs.map(function (q) {
      var t = QAR[q.id];
      if (!t) return q;
      return Object.assign({}, q, { label: t[0], options: (q.options || []).map(function (o) { return Object.assign({}, o, { label: t[1][o.value] || o.label }); }) });
    });
  }
  function setLang(l) { try { localStorage.setItem("hv_lang", l); } catch (e) { /* blocked */ } location.reload(); }
  var ICON = {
    spark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z"/></svg>',
    chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>',
    user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="3.6"/><path d="M5 20c.6-3.8 3.4-5.8 7-5.8s6.4 2 7 5.8"/></svg>'
  };

  /* --------------------------------------------------------------- helpers */

  function h(tag, props) {
    var node = document.createElement(tag);
    props = props || {};
    Object.keys(props).forEach(function (k) {
      var v = props[k];
      if (v == null || v === false) return;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = T(v);
      else if (k === "html") node.innerHTML = v;            // only ever our own static strings
      else if (k.slice(0, 2) === "on") node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : (k === "placeholder" || k === "aria-label" || k === "title") ? T(v) : v);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null || c === false) continue;
      node.appendChild(typeof c === "string" ? document.createTextNode(T(c)) : c);
    }
    return node;
  }

  function $(id) { return document.getElementById(id); }
  function bg(node, url) { if (url) node.style.backgroundImage = 'url("' + String(url).replace(/"/g, "%22") + '")'; }

  function api(method, path, body) {
    var opts = { method: method, credentials: "include", headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(API + path, opts)
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (b) { return { s: r.status, b: b || {} }; });
      })
      .catch(function () { return { s: 0, b: { message: "Could not reach the server. Please try again." } }; });
  }

  function money(n) { return Math.round(n).toLocaleString("en-US"); }
  function price(p) { return p && p.length ? "SAR " + money(p[0]) + (p[1] && p[1] !== p[0] ? " – " + money(p[1]) : "") : "Price on request"; }
  function followers(n) { return n >= 1e6 ? (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M" : n >= 1e3 ? Math.round(n / 1e3) + "K" : String(n || 0); }
  function ago(ts) {
    var d = Math.max(0, Date.now() / 1000 - ts);
    return d < 3600 ? Math.max(1, Math.round(d / 60)) + " min ago" : d < 86400 ? Math.round(d / 3600) + " h ago" : Math.round(d / 86400) + " d ago";
  }

  var openLayers = [];
  function layer(node, drawer) {
    if (LANG === "ar") { node.setAttribute("dir", "rtl"); node.setAttribute("lang", "ar"); }
    var scrim = drawer ? node : h("div", { class: "pt-scrim", role: "presentation" }, node);
    var prev = document.activeElement;
    function close() {
      scrim.remove();
      openLayers = openLayers.filter(function (l) { return l !== close; });
      if (!openLayers.length) document.body.classList.remove("pt-lock");
      document.removeEventListener("keydown", onKey);
      if (prev && prev.focus) prev.focus();
    }
    function onKey(e) { if (e.key === "Escape" && openLayers[openLayers.length - 1] === close) close(); }
    if (!drawer) scrim.addEventListener("mousedown", function (e) { if (e.target === scrim) close(); });
    document.addEventListener("keydown", onKey);
    document.body.appendChild(scrim);
    document.body.classList.add("pt-lock");
    openLayers.push(close);
    var focusable = scrim.querySelector("input, textarea, button.pt-opt, button.pt-btn, .pt-x");
    if (focusable) focusable.focus();
    return close;
  }

  function creditsLine(cost) {
    if (!ME || ME.credits == null) return "";
    if (LANG === "ar") return cost + " رصيد · متبقٍ " + ME.credits;
    return cost + " credit" + (cost === 1 ? "" : "s") + " · " + ME.credits + " left";
  }

  /* ------------------------------------------------------------------ gate */

  // HELVY Connect sign-in (simplified 2026-10-09, client-approved). One scene on a blurred wall
  // of HelloVoice's own film stills: the logo and one line, then the sign-in card with Helvy
  // standing on its top edge (a transparent cut-out, waving hello, then idling), and one small,
  // quiet row of client logos at the foot. Client sign-in only: work email -> 6-digit code ->
  // first-time name, company, job title. There is no team door; HelloVoice reaches the admin by
  // its own address. A selection or campaign link that still needs its access code shows
  // "Opened a shared link?" under the card, and ?access=code brings the same form up.
  // The sign-in "Trusted by" strip. The third number is each logo's drawn height in px (fix batch 4):
  // the same optical size for every logo, worked out once from the files in assets/clients/:
  // equal ink AREA (height = sqrt(2200 / aspect)), nudged by how dense the mark is (a solid
  // block like CeraVe draws smaller, a hairline wordmark like SkinCeuticals larger), kept
  // between 16 and 32 px. A wide wordmark and a square monogram now read at the same weight.
  var LOGOS = [["avalon-pharma", "Avalon Pharma", 18], ["alpha-plus", "Alpha Plus", 28], ["penduline", "Penduline", 31],
               ["parkville", "Parkville", 18], ["svr", "SVR", 32], ["ivatherm", "Ivatherm", 20],
               ["l-oreal-dermatological-beauty", "L'Oréal Dermatological Beauty", 32], ["abbott", "Abbott", 22],
               ["biotech-cigalah", "Biotech Cigalah", 32], ["nahdi", "Nahdi", 32], ["whites", "Whites", 19], ["la-roche-posay", "La Roche-Posay", 32],
               ["vichy", "Vichy", 28], ["cerave", "CeraVe", 24], ["uriage", "Uriage", 28], ["skinceuticals", "SkinCeuticals", 21],
               ["jamjoom-pharma", "Jamjoom Pharma", 22], ["spc", "SPC", 32], ["orchidia", "Orchidia", 26]];
  var PERSONAL = /@(gmail|googlemail|hotmail|outlook|live|msn|yahoo|ymail|icloud|me|mac|aol|proton|protonmail|gmx|yandex|mail|zoho)\.[a-z.]+$/i;

  function enhanceGate() {
    var gate = $("cat-gate");
    if (!gate || gate.getAttribute("data-pt")) return;
    gate.setAttribute("data-pt", "1");
    var inner = gate.querySelector(".cat-gate__inner");
    if (!inner) return;
    var oldForm = inner.querySelector(".cat-gate__form");
    var oldErr = inner.querySelector(".cat-gate__error");
    var page = document.body.getAttribute("data-page");
    var sharedOk = page !== "catalogue" || /[?&]access=code\b/.test(location.search || "");
    gate.classList.add("cx-gate");

    var scene = h("main", { class: "cx-scene" });
    scene.appendChild(h("div", { class: "cx-wall", "aria-hidden": "true" }));
    var wrap = h("div", { class: "cx-wrap cx-scene__in" });

    /* -- the name and one line -- */
    var pitch = h("section", { class: "cx-pitch", "aria-label": "About HELVY Connect" });
    pitch.appendChild(h("h1", { class: "cx-vh" }, "HELVY Connect"));
    pitch.appendChild(h("img", { class: "cx-pitch__logo", src: ROOT + "assets/brand/helvy-connect/helvy-connect-dark-640.webp?v=c4", alt: "HELVY Connect", width: "440", height: "220", fetchpriority: "high" }));
    pitch.appendChild(h("p", { class: "cx-pitch__tag" }, "Connecting Brands with the Right Voices"));

    /* -- the card, Helvy standing on it -- */
    var door = h("section", { class: "cx-door", "aria-label": "Sign in" });
    var helvy = h("div", { class: "cx-door__helvy" }, clip("hello", "cx-hd--edge", { once: true, then: "idle" }));
    var bubble = h("span", { class: "cx-door__say", "aria-hidden": "true" }, "Hi, I’m Helvy");
    var pane = h("div", { id: "cx-pane", "aria-live": "polite" });
    var card = h("div", { class: "cx-door__card" }, pane);
    door.appendChild(helvy); door.appendChild(bubble); door.appendChild(card);
    var sharedLine = null;
    if (sharedOk && oldForm) {
      sharedLine = h("p", { class: "cx-shared" }, "Opened a shared link with an access code? ",
        h("button", { type: "button", class: "cx-link", onclick: function () { show("shared"); } }, "Enter the code"));
      door.appendChild(sharedLine);
    }
    wrap.appendChild(pitch); wrap.appendChild(door);
    scene.appendChild(wrap);

    /* -- one quiet row of client logos -- */
    // A slow marquee: the list is drawn twice and slides by half its width, so it loops seamlessly.
    var track = h("div", { class: "cx-logos__track" });
    [0, 1].forEach(function (copy) {
      LOGOS.forEach(function (l) {
        var img = h("img", { src: ROOT + "assets/clients/" + l[0] + ".webp?v=c3", srcset: ROOT + "assets/clients/" + l[0] + "@2x.webp?v=c3 2x", alt: copy ? "" : l[1], loading: "lazy", decoding: "async", height: String(l[2] || 22) });
        img.style.setProperty("--h", (l[2] || 22) + "px");
        if (copy) img.setAttribute("aria-hidden", "true");
        track.appendChild(img);
      });
    });
    var logos = h("div", { class: "cx-logos__row" }, track);
    scene.appendChild(h("div", { class: "cx-logos" }, h("div", { class: "cx-wrap" }, h("p", null, "Trusted by"), logos)));

    var foot = h("footer", { class: "cx-scene__foot" });
    var fw = h("div", { class: "cx-wrap" });
    fw.appendChild(h("span", null, "© " + new Date().getFullYear() + " HELVY Connect · ", h("a", { href: ROOT + "privacy/" }, "Privacy"), " · ", h("a", { href: ROOT + "terms/" }, "Terms")));
    fw.appendChild(h("span", { class: "cx-by" }, h("span", null, "Powered by"),
      h("img", { src: ROOT + "assets/brand/logo-knockout.webp", alt: "HelloVoice", width: "104", height: "23" }), h("span", null, "A BlueHolding Company")));
    foot.appendChild(fw);
    scene.appendChild(foot);
    gate.appendChild(scene);

    /* -- the steps -- */
    var st = { step: "email", email: "", ticket: "", expires: 0, resendAt: 0, timer: null, company: "" };
    var SAY = { email: "Hi, I’m Helvy", blocked: "Work email, please", code: "It’s on its way",
                details: "Nice to meet you", shared: "Got a code?", pending: "Almost there" };
    function setSay(k) { bubble.textContent = SAY[k] || SAY.email; }
    function errLine(text) { return h("p", { class: "cx-err", role: "alert", html: icon("info", "cx-i") }, h("span", null, text)); }
    function goBtn(label, ink) {
      return h("button", { class: "cx-btn cx-go" + (ink ? " cx-btn--ink" : ""), type: "submit", html: "<span></span>" + icon("arrow", "cx-i") }, null);
    }
    function label(btn, text) { btn.firstChild.textContent = text; return btn; }
    function wait(btn, on, text) { btn.disabled = on; label(btn, on ? "One moment…" : text); }
    function mmss(s) { s = Math.max(0, Math.round(s)); return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2); }

    function show(step, opts) {
      opts = opts || {};
      clearInterval(st.timer);
      st.step = step;
      setSay(opts.blocked ? "blocked" : step);
      pane.textContent = "";
      ({ email: paneEmail, code: paneCode, details: paneDetails, shared: paneShared, pending: panePending }[step] || paneEmail)(opts);
      if (sharedLine) sharedLine.hidden = step === "shared";
    }

    function paneEmail(opts) {
      pane.appendChild(h("h2", { class: "cx-vh" }, "Sign in or join"));
      var input = h("input", { type: "email", name: "email", autocomplete: "email", inputmode: "email", spellcheck: "false", required: true,
        placeholder: "name@yourcompany.com", value: st.email || "", "aria-describedby": "cx-email-err" });
      var fld = h("label", { class: "cx-fld" }, h("span", null, "Work email"), input);
      var err = h("div", { id: "cx-email-err" });
      var btn = label(goBtn(), "Email me a code");
      var form = h("form", { novalidate: true }, fld, err, btn);
      var fine = h("p", { class: "cx-fine" }, "We email you a one-time code. No password, and new accounts are made in the same step.");
      pane.appendChild(form); pane.appendChild(fine);
      function bad(text, personal) {
        fld.classList.add("cx-fld--err"); input.setAttribute("aria-invalid", "true");
        err.textContent = ""; err.appendChild(errLine(text));
        if (personal) { setSay("blocked"); fine.textContent = "No work email? Ask your HelloVoice account manager to invite you."; }
        input.focus();
      }
      if (opts.error) bad(opts.error, opts.blocked);
      input.addEventListener("input", function () { fld.classList.remove("cx-fld--err"); input.removeAttribute("aria-invalid"); err.textContent = ""; });
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var v = input.value.trim().toLowerCase();
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(v)) { bad("Enter your work email, like name@yourcompany.com."); return; }
        if (PERSONAL.test(v)) { bad("That’s a personal address. Use your work email so we can link you to your company’s selections and campaigns.", true); return; }
        st.email = v;
        wait(btn, true, "Email me a code");
        sendCode().then(function (r) {
          wait(btn, false, "Email me a code");
          if (r.error) bad(r.error, r.personal);
        });
      });
      if (!opts.keepFocus) setTimeout(function () { input.focus({ preventScroll: true }); }, 30);
    }

    function sendCode() {
      return api("POST", "/api/auth/start", { email: st.email }).then(function (r) {
        if (r.s === 429) return { error: "Too many requests. Please wait a few minutes and try again." };
        if (r.b.reason === "mail_not_configured") return { error: r.b.message || "Email sign-in isn’t available yet." };
        if (!r.b.ok) return { error: r.b.message || "We couldn’t send the code. Please try again.", personal: r.b.reason === "personal" };
        var now = Date.now() / 1000;
        if (r.b.sent !== false || !st.expires) st.expires = now + (r.b.minutes || 10) * 60;
        st.resendAt = now + (r.b.resend_in || r.b.wait || 30);
        show("code", { resent: r.b.sent === false });
        return {};
      });
    }

    function paneCode(opts) {
      pane.appendChild(h("h2", { class: "cx-door__title" }, "Check your inbox"));
      pane.appendChild(h("p", { class: "cx-door__lead" }, "We sent a 6-digit code to ", h("b", null, st.email), ". Enter it below."));
      var input = h("input", { type: "text", inputmode: "numeric", autocomplete: "one-time-code", maxlength: "6", pattern: "[0-9]*",
        "aria-label": "6-digit code", spellcheck: "false" });
      var boxes = h("div", { class: "cx-otp__boxes", "aria-hidden": "true" });
      for (var i = 0; i < 6; i++) boxes.appendChild(h("span"));
      var otp = h("div", { class: "cx-otp", role: "group", "aria-label": "6-digit code" }, boxes, input);
      var clock = h("b");
      var again = h("span");
      var meta = h("div", { class: "cx-otp__meta" }, h("span", { class: "cx-clock", html: icon("clock", "cx-i") }, "Expires in ", clock), again);
      var err = h("div");
      var btn = label(goBtn(), "Sign in");
      btn.disabled = true;
      var form = h("form", { novalidate: true }, otp, meta, err, btn);
      var who = h("div", { class: "cx-who", html: icon("mail", "cx-i") }, h("span", null, "Nothing in your inbox? Check spam."),
        h("button", { type: "button", class: "cx-link", onclick: function () { st.expires = 0; show("email"); } }, "Change email"));
      pane.appendChild(form); pane.appendChild(who);
      if (opts.resent) err.appendChild(h("p", { class: "cx-ok" }, "A code was sent a moment ago. Use the one in your inbox."));
      function paint() {
        var v = input.value, cur = Math.min(v.length, 5);
        [].forEach.call(boxes.children, function (b, k) {
          b.textContent = v.charAt(k); b.classList.toggle("is-on", k < v.length); b.classList.toggle("is-cur", k === cur && v.length < 6 || (v.length === 6 && k === 5));
        });
        btn.disabled = v.length !== 6;
      }
      function tick() {
        var now = Date.now() / 1000, left = st.expires - now;
        clock.textContent = " " + mmss(left);
        again.textContent = "";
        if (st.resendAt > now) again.appendChild(document.createTextNode("New code in ")), again.appendChild(h("b", null, mmss(st.resendAt - now)));
        else again.appendChild(h("button", { type: "button", onclick: function () {
          err.textContent = "";
          sendCode().then(function (r) { if (r.error) { err.textContent = ""; err.appendChild(errLine(r.error)); } });
        } }, "Send a new code"));
        if (left <= 0) { clearInterval(st.timer); err.textContent = ""; err.appendChild(errLine("That code has expired. Send a new one.")); btn.disabled = true; }
      }
      input.addEventListener("input", function () {
        input.value = input.value.replace(/\D/g, "").slice(0, 6);
        otp.classList.remove("is-bad"); err.textContent = "";
        paint();
        if (input.value.length === 6) form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit", { cancelable: true }));
      });
      input.addEventListener("focus", function () { otp.classList.add("is-focus"); });
      input.addEventListener("blur", function () { otp.classList.remove("is-focus"); });
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        if (input.value.length !== 6 || btn.getAttribute("data-busy")) return;
        btn.setAttribute("data-busy", "1"); wait(btn, true, "Sign in");
        api("POST", "/api/auth/verify", { email: st.email, otp: input.value }).then(function (r) {
          btn.removeAttribute("data-busy"); wait(btn, false, "Sign in");
          if (r.s === 429) { err.textContent = ""; err.appendChild(errLine("Too many tries. Please wait a few minutes.")); return; }
          if (!r.b.ok) {
            otp.classList.add("is-bad"); err.textContent = ""; err.appendChild(errLine(r.b.message || "That code isn’t right."));
            input.value = ""; paint(); input.focus(); return;
          }
          done(r.b);
        });
      });
      paint(); tick();
      st.timer = setInterval(tick, 1000);
      setTimeout(function () { input.focus({ preventScroll: true }); }, 30);
    }

    function done(b) {
      if (b.step === "profile") { st.ticket = b.ticket; st.company = b.suggested_company || ""; show("details"); }
      else if (b.step === "pending") show("pending", { message: b.message });
      else if (b.step === "done") { setSay("details"); location.reload(); }
    }

    function paneDetails() {
      pane.appendChild(h("h2", { class: "cx-door__title" }, "One last thing"));
      pane.appendChild(h("p", { class: "cx-door__lead" }, "First time here. Tell us who you are so HelloVoice can set up your account."));
      var name = h("input", { type: "text", name: "name", autocomplete: "name", required: true });
      var company = h("input", { type: "text", name: "company", autocomplete: "organization", required: true, value: st.company });
      var title = h("input", { type: "text", name: "job_title", autocomplete: "organization-title", required: true, placeholder: "e.g. Brand Manager" });
      var err = h("div");
      var btn = label(goBtn(), "Enter HELVY Connect");
      var form = h("form", { novalidate: true },
        h("label", { class: "cx-fld" }, h("span", null, "Full name"), name),
        h("div", { class: "cx-row2" }, h("label", { class: "cx-fld" }, h("span", null, "Company"), company),
                                       h("label", { class: "cx-fld" }, h("span", null, "Job title"), title)),
        err, btn);
      pane.appendChild(form);
      pane.appendChild(h("div", { class: "cx-who", html: icon("check", "cx-i") }, h("span", null, "Signed in as " + st.email)));
      pane.appendChild(h("p", { class: "cx-fine" }, "That’s all for now. Your photo, brands and markets are optional later, and each one earns credits."));
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        err.textContent = "";
        var miss = [[name, "your name"], [company, "your company"], [title, "your job title"]].filter(function (x) { return x[0].value.trim().length < 2; });
        if (miss.length) { err.appendChild(errLine("Please add " + miss.map(function (x) { return x[1]; }).join(", ") + ".")); miss[0][0].focus(); return; }
        wait(btn, true, "Enter HELVY Connect");
        api("POST", "/api/auth/profile", { ticket: st.ticket, name: name.value, company: company.value, job_title: title.value,
                                           invite: inviteToken() || undefined }).then(function (r) {
          wait(btn, false, "Enter HELVY Connect");
          if (!r.b.ok) { err.appendChild(errLine(r.b.message || "We couldn’t create the account. Please try again.")); return; }
          done(r.b);
        });
      });
      setTimeout(function () { name.focus({ preventScroll: true }); }, 30);
    }

    function paneShared() {
      pane.appendChild(h("h2", { class: "cx-door__title" }, "Shared link"));
      pane.appendChild(h("p", { class: "cx-door__lead" }, "This link was sent with its own access code. Enter it to open it. To keep everything in one place, sign in with your work email next time."));
      var box = h("div", { class: "cx-codeform" });
      if (oldForm) { oldForm.hidden = false; box.appendChild(oldForm); }
      if (oldErr) box.appendChild(oldErr);
      pane.appendChild(box);
      pane.appendChild(h("p", { class: "cx-fine" }, h("button", { type: "button", class: "cx-link", onclick: function () { show("email"); } }, "Sign in with your work email instead")));
      var inp = oldForm && oldForm.querySelector("input");
      if (inp) setTimeout(function () { inp.focus({ preventScroll: true }); }, 30);
    }

    function panePending(opts) {
      pane.appendChild(h("h2", { class: "cx-door__title" }, "Almost there"));
      pane.appendChild(h("p", { class: "cx-door__lead" }, opts.message || "Your account is waiting for approval by the HelloVoice team. We’ll email you as soon as it’s ready."));
    }

    show(/[?&]access=code\b/.test(location.search || "") && oldForm ? "shared" : "email", { keepFocus: true });
  }

  // A colleague's invite link (?invite=...) is kept for this visit and sent with the new
  // account, so the colleague who invited is paid when this one is in.
  function inviteToken() {
    var m = /[?&]invite=([0-9]+\.[0-9a-f]+)/.exec(location.search || "");
    try {
      if (m) sessionStorage.setItem("hv_invite", m[1]);
      return sessionStorage.getItem("hv_invite");
    } catch (e) { return m ? m[1] : null; }
  }
  inviteToken();

  // The brief can start from the profile: the client's industry and first market.
  function profileAnswers() {
    var u = ME && ME.user, out = {};
    if (!u) return out;
    if (u.markets && u.markets.length) out.market = u.markets[0];
    if (u.industry) out.category = [u.industry];
    return out;
  }
  HV.profileAnswers = profileAnswers;

  /* ------------------------------------------------------------------ dock */

  // The account circle, top right: initials on lime, opening a small menu.
  // Ask and Find creators live in Helvy (the chat) now, and admin moves into
  // the menu, so the bar keeps only the site's own links and this circle.
  function mountDock() {
    if (!ME || !ME.signed_in || $("pt-dock")) return;
    var cat = document.querySelector(".cat-topbar__links");
    var dock = h("div", { id: "pt-dock", class: "pt-dock" + (cat ? "" : " pt-dock--fixed") });
    var u = ME.user;
    var name = u && u.name ? u.name : ME.kind === "admin" ? "HelloVoice team" : "Guest access";
    var initials = u && u.name ? u.name.trim().split(/\s+/).slice(0, 2).map(function (w) { return w.charAt(0); }).join("").toUpperCase()
      : ME.kind === "admin" ? "HV" : "G";
    var btn = h("button", { class: "pt-avatar", type: "button", id: "pt-avatar", "aria-haspopup": "menu", "aria-expanded": "false", "aria-controls": "pt-menu", "aria-label": "Account menu" });
    btn.appendChild(h("span", { id: "pt-chip-name", class: "pt-avatar__ini" }, initials));
    function setPhoto(v) {
      var old = btn.querySelector("img");
      if (old) old.remove();
      btn.classList.toggle("has-photo", !!v);
      if (v) btn.appendChild(h("img", { class: "pt-avatar__img", alt: "", src: API + "/api/me/image?k=photo&v=" + encodeURIComponent(v) }));
    }
    HV.setPhoto = setPhoto;
    if (u && u.photo) setPhoto(u.photo);
    var menu = h("div", { class: "pt-menu", id: "pt-menu", role: "menu", "aria-labelledby": "pt-avatar", hidden: true });
    var head = h("div", { class: "pt-menu__head" }, h("b", { class: "pt-menu__name" }, name));
    var sub = u ? [u.job_title, u.company].filter(Boolean).join(" · ") || u.email : ME.kind === "admin" ? "Administrator" : "Signed in with an access code";
    if (sub) head.appendChild(h("span", { class: "pt-menu__sub" }, sub));
    menu.appendChild(head);
    function item(label, act, extra, cls) {
      var el = act.href ? h("a", { class: "pt-menu__item" + (cls ? " " + cls : ""), role: "menuitem", href: act.href })
                        : h("button", { class: "pt-menu__item" + (cls ? " " + cls : ""), role: "menuitem", type: "button" });
      el.appendChild(h("span", null, label));
      if (extra) el.appendChild(extra);
      if (act.go) el.addEventListener("click", function () { toggle(false); act.go(); });
      else el.addEventListener("click", function () { toggle(false); });
      menu.appendChild(el);
      return el;
    }
    function rule() { menu.appendChild(h("div", { class: "pt-menu__rule", role: "separator" })); }
    var credits = ME.credits != null ? h("span", { class: "pt-menu__badge hv-cost", id: "pt-chip-credits" }, ME.credits + " cr") : null;
    var ACC = ROOT + "account/";
    if (u) {
      // Account holders: their own space, then help, then out.
      item("My profile", { href: ACC + "#overview" });
      item("Selections", { href: ACC + "#selections" });
      item("Analyses", { href: ACC + "#analyses" });
      item("Campaigns", { href: ACC + "#campaigns" });
      if (credits) item("Credits", { href: ACC + "#credits" }, credits);
      item("Account", { href: ACC + "#account" });
      rule();
      item("Help", { go: function () { if (HV.talk) HV.talk(); else location.href = ACC + "#overview"; } });
      item("Take the tour", { go: function () { if (HV.tour) HV.tour(true); } });
    } else if (ME.kind === "admin") {
      item("Preview as client", { go: openAccount });
      item("My campaigns", { href: ROOT + "campaign/dashboard/" });
      rule();
      item("Open admin", { href: API + "/" });
    } else {
      // Access-code guests: no profile for now, just their campaigns and credits.
      item("My campaigns", { href: ROOT + "campaign/dashboard/" });
      if (credits) item("AI credits", { go: openAccount }, credits);
      rule();
    }
    item("Sign out", { go: function () { (function () { try { sessionStorage.removeItem("hv-roster"); } catch (e) { /* blocked */ } })(), api("POST", "/api/auth/logout", {}).then(function () { location.href = ROOT; }); } }, null, "pt-menu__item--quiet");

    function toggle(open) {
      menu.hidden = !open;
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) { var first = menu.querySelector(".pt-menu__item"); if (first) first.focus(); }
    }
    btn.addEventListener("click", function (e) { e.stopPropagation(); toggle(menu.hidden); });
    document.addEventListener("click", function (e) { if (!menu.hidden && !dock.contains(e.target)) toggle(false); });
    document.addEventListener("keydown", function (e) {
      if (menu.hidden) return;
      if (e.key === "Escape") { toggle(false); btn.focus(); return; }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      var items = Array.prototype.slice.call(menu.querySelectorAll(".pt-menu__item"));
      var i = items.indexOf(document.activeElement);
      items[(i + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus();
      e.preventDefault();
    });
    if (u) dock.appendChild(mountBell());
    dock.appendChild(btn);
    dock.appendChild(menu);
    if (cat) cat.appendChild(dock); else { document.body.appendChild(dock); document.body.classList.add("has-pt-dock"); }
  }

  // The bell: account holders only, between Campaign tracking and the account circle.
  // In-portal only; nothing here is emailed. The list is the latest five the client's
  // toggles allow; "See all" opens the full history on their profile.
  function mountBell() {
    var wrap = h("div", { class: "hv-bellwrap" });
    var bell = h("button", { class: "hv-bell", type: "button", id: "hv-bell", "aria-haspopup": "dialog", "aria-expanded": "false",
                             "aria-controls": "hv-bell-drop", "aria-label": "Notifications" });
    bell.innerHTML = icon("bell") + '<span class="hv-bell__dot" hidden></span>';
    var drop = h("div", { class: "hv-drop", id: "hv-bell-drop", role: "dialog", "aria-label": "Notifications", hidden: true });
    var hd = h("div", { class: "hv-drop__hd" });
    var title = h("h2", null, "Notifications");
    var fresh = h("span", { class: "hv-drop__new", hidden: true });
    var all = h("button", { class: "hv-drop__all", type: "button" }, "Mark all as read");
    hd.appendChild(title); hd.appendChild(fresh); hd.appendChild(all);
    var list = h("ul", { class: "hv-drop__list" });
    var foot = h("div", { class: "hv-drop__ft" });
    var see = h("a", { href: ROOT + "account/#notifications" }, "See all in your profile ");
    see.insertAdjacentHTML("beforeend", icon("arrow"));
    foot.appendChild(see);
    drop.appendChild(hd); drop.appendChild(list);
    drop.appendChild(h("p", { class: "hv-drop__note" }, "Updates show here only. We don't send them by email."));
    drop.appendChild(foot);
    wrap.appendChild(bell); wrap.appendChild(drop);
    var unread = ME.unread || 0;
    function paintCount(n) {
      unread = n || 0;
      bell.querySelector(".hv-bell__dot").hidden = !unread;
      bell.setAttribute("aria-label", unread ? "Notifications, " + unread + " unread" : "Notifications");
      fresh.hidden = !unread; fresh.textContent = unread + " new";
      all.hidden = !unread;
      if (HV.onUnread) HV.onUnread(unread);
    }
    HV.setUnread = paintCount;
    function load() {
      return api("GET", "/api/notifications?limit=5").then(function (r) {
        if (!r.b || !r.b.ok) return;
        paintCount(r.b.unread);
        list.textContent = "";
        if (!r.b.items.length) {
          list.appendChild(h("li", { class: "hv-drop__empty" }, "Nothing yet. When HelloVoice answers a request, reviews a creator or updates a campaign, it shows here."));
        }
        r.b.items.forEach(function (n) {
          var li = document.createElement("li");
          li.appendChild(noteRow(n, function () { paintCount(Math.max(0, unread - 1)); }));
          list.appendChild(li);
        });
      });
    }
    // Fixed to the window, under the bell: some page headers clip what overflows them.
    function place() {
      if (window.innerWidth <= 767) { drop.style.top = drop.style.right = drop.style.position = ""; return; }
      var r = bell.getBoundingClientRect();
      drop.style.position = "fixed";
      drop.style.top = Math.round(r.bottom + 12) + "px";
      drop.style.right = Math.max(10, Math.round(window.innerWidth - r.right - 58)) + "px";
    }
    window.addEventListener("resize", function () { if (!drop.hidden) place(); });
    window.addEventListener("scroll", function () { if (!drop.hidden && window.innerWidth > 767) toggle(false); }, { passive: true });
    function toggle(open) {
      if (open) place();
      drop.hidden = !open;
      bell.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) { load(); var m = $("pt-menu"); if (m && !m.hidden) $("pt-avatar").click(); }
    }
    bell.addEventListener("click", function (e) { e.stopPropagation(); toggle(drop.hidden); });
    document.addEventListener("click", function (e) { if (!drop.hidden && !wrap.contains(e.target)) toggle(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !drop.hidden) { toggle(false); bell.focus(); } });
    all.addEventListener("click", function () {
      api("POST", "/api/notifications/read", {}).then(function (r) {
        if (r.b && r.b.ok) {
          paintCount(0);
          [].forEach.call(list.querySelectorAll(".is-new"), function (x) { x.classList.remove("is-new"); var d = x.querySelector(".hv-note__unread"); if (d) d.remove(); });
        }
        if (HV.onReadAll) HV.onReadAll();
      });
    });
    paintCount(unread);
    // A quiet check while the page is open, only when it is on screen.
    setInterval(function () {
      if (document.hidden || !drop.hidden) return;
      api("GET", "/api/notifications?limit=1").then(function (r) { if (r.b && r.b.ok) paintCount(r.b.unread); });
    }, 90000);
    return wrap;
  }

  function setCredits(n) {
    if (n == null) return;
    ME.credits = n;
    var c = $("pt-chip-credits");
    if (c) c.textContent = n + " cr";
  }

  /* ---------------------------------------------------------- brief wizard */

  var QUESTIONS = null;
  function loadQuestions() {
    if (QUESTIONS) return Promise.resolve(QUESTIONS);
    return api("GET", "/api/brief/questions").then(function (r) { QUESTIONS = localise(r.b.questions || []); return QUESTIONS; });
  }

  function openWizard() {
    loadQuestions().then(function (qs) { wizard(qs, profileAnswers(), 0); });
  }

  var currentClose = null;
  function wizard(qs, answers, step, prefillNote, opts) {
    opts = opts || {};
    if (currentClose) currentClose();
    var total = qs.length + 1;                        // questions + review
    var onReview = step >= qs.length;
    var title = h("h2", { class: "pt-title", id: "pt-wiz-title" }, onReview ? "Review your brief" : opts.attach ? "Score this selection" : "Find creators");
    var modal = h("div", { class: "pt-modal", role: "dialog", "aria-modal": "true", "aria-labelledby": "pt-wiz-title" });
    var close;
    var x = h("button", { class: "pt-x", type: "button", "aria-label": "Close", onclick: function () { close(); } }, "×");
    modal.appendChild(h("div", { class: "pt-head" }, title, x));
    modal.appendChild(h("div", { class: "pt-progress" }, h("i", { style: "transform:scaleX(" + ((step + 1) / total).toFixed(3) + ")" })));
    var body = h("div", { class: "pt-body" });
    modal.appendChild(body);
    var err = h("div", { class: "pt-err", hidden: true, role: "alert" });

    function fail(text) { err.textContent = T(text || ""); err.hidden = !text; }
    function go(n) { wizard(qs, answers, Math.max(0, Math.min(n, qs.length)), prefillNote, opts); }

    if (!onReview) {
      var q = qs[step];
      if (step === 0 && HV.briefSource) {
        // Phase E: start from what the client already has: a product page or their own brief.
        body.appendChild(HV.briefSource({
          lead: opts.attach ? "Have a product page or a brief? Helvy can answer these questions from it." : "Start from what you have",
          onUse: function (got, res) {
            Object.keys(got).forEach(function (k) { if (k !== "notes" || !opts.attach) answers[k] = got[k]; });
            if (opts.attach && got.notes) answers.notes = got.notes;
            var src = res.source || {};
            wizard(qs, answers, qs.length, "Helvy filled this from " + (src.kind === "file" ? "your brief" : src.label || "the page") +
              ". Check every answer and change anything that's off.", Object.assign({}, opts, { source: res }));
          }
        }));
        body.appendChild(h("div", { class: "pt-or" }, opts.attach ? "or answer the questions" : "or describe it in a sentence"));
      }
      if (step === 0 && !opts.attach) {
        // The one-sentence shortcut lives on the first screen only.
        var free = h("textarea", { class: "pt-text", placeholder: "e.g. We're launching a sunscreen in Riyadh and want 8 micro-creators on Instagram, budget around 100k SAR.", maxlength: "1500", "aria-label": "Describe your campaign" });
        var fillBtn = h("button", { class: "pt-btn pt-btn--ghost", type: "button" }, "Fill it in for me");
        var cost = ME && ME.costs ? ME.costs.parse : 1;
        if (ME && ME.ai) {
          body.appendChild(h("p", { class: "pt-sub", style: "margin-top:0" }, "Our AI fills the questions from a sentence. Or answer them yourself below."));
          body.appendChild(h("div", { style: "margin-top:14px" }, free));
          body.appendChild(h("div", { class: "pt-actions", style: "margin-top:12px" }, h("span", { class: "pt-note", style: "margin:0" }, creditsLine(cost)), fillBtn));
          body.appendChild(h("div", { class: "pt-or" }, "or answer a few questions"));
          fillBtn.addEventListener("click", function () {
            if (free.value.trim().length < 8) { fail("Describe the campaign in a sentence or two."); return; }
            fillBtn.disabled = true; fillBtn.textContent = "Reading your brief…";
            api("POST", "/api/brief/parse", { text: free.value }).then(function (r) {
              if (r.b.ok) { setCredits(r.b.credits); Object.keys(r.b.answers || {}).forEach(function (k) { answers[k] = r.b.answers[k]; }); wizard(qs, answers, qs.length, "We read your brief. Check it and change anything that's off."); }
              else { fillBtn.disabled = false; fillBtn.textContent = "Fill it in for me"; fail(r.b.message || "That didn't work. Please answer the questions instead."); }
            });
          });
        }
      }
      body.appendChild(h("p", { class: "pt-note", style: "margin-top:0" }, LANG === "ar" ? "سؤال " + (step + 1) + " من " + qs.length + (q.required ? "" : " · اختياري")
        : "Question " + (step + 1) + " of " + qs.length + (q.required ? "" : " · optional")));
      body.appendChild(h("h3", { class: "pt-q" }, q.label));
      if (q.type === "text") {
        var ta = h("textarea", { class: "pt-text", maxlength: String(q.max || 500), "aria-label": q.label, placeholder: "A city, a product name, a tone, anything that helps." }, answers[q.id] || "");
        ta.value = answers[q.id] || "";
        ta.addEventListener("input", function () { if (ta.value.trim()) answers[q.id] = ta.value.trim(); else delete answers[q.id]; });
        body.appendChild(ta);
      } else {
        var many = q.type === "many";
        var grid = h("div", { class: "pt-opts", role: many ? "group" : "radiogroup", "aria-label": q.label });
        q.options.forEach(function (o) {
          var cur = answers[q.id];
          var on = many ? (cur || []).indexOf(o.value) > -1 : cur === o.value;
          var btn = h("button", { class: "pt-opt", type: "button", "aria-pressed": on ? "true" : "false" }, h("span", { class: "pt-tick" }), o.label);
          btn.addEventListener("click", function () {
            if (many) {
              var list = answers[q.id] || [];
              var i = list.indexOf(o.value);
              if (o.value === "any") list = i > -1 ? [] : ["any"];
              else { list = list.filter(function (v) { return v !== "any"; }); if (i > -1) list.splice(list.indexOf(o.value), 1); else list.push(o.value); }
              if (list.length) answers[q.id] = list; else delete answers[q.id];
              Array.prototype.forEach.call(grid.children, function (b, bi) { if (q.options[bi]) b.setAttribute("aria-pressed", (answers[q.id] || []).indexOf(q.options[bi].value) > -1 ? "true" : "false"); });
              if (o.value === "any" && oIn) { oIn.value = ""; oIn.hidden = true; oBtn.setAttribute("aria-pressed", "false"); }
            } else {
              answers[q.id] = o.value;
              setTimeout(function () { go(step + 1); }, 140);
            }
          });
          grid.appendChild(btn);
        });
        body.appendChild(grid);
        var oBtn = null, oIn = null;
        if (q.other) {
          // "Other": a free answer the options don't list.
          var own = otherOf(answers[q.id]);
          oBtn = h("button", { class: "pt-opt", type: "button", "aria-pressed": own ? "true" : "false" }, h("span", { class: "pt-tick" }), "Other");
          oIn = otherInput(q, own, function (txt) {
            var nv = withOther(q, answers[q.id], txt);
            if (nv) answers[q.id] = nv; else delete answers[q.id];
            Array.prototype.forEach.call(grid.children, function (b, bi) {
              if (q.options[bi]) b.setAttribute("aria-pressed", (many ? (answers[q.id] || []).indexOf(q.options[bi].value) > -1 : answers[q.id] === q.options[bi].value) ? "true" : "false");
            });
            oBtn.setAttribute("aria-pressed", txt.trim() ? "true" : "false");
          }, function () { next.click(); });
          oIn.hidden = !own;
          oBtn.addEventListener("click", function () { oIn.hidden = false; oIn.focus(); });
          grid.appendChild(oBtn);
          body.appendChild(oIn);
        }
      }
      body.appendChild(err);
      var back = h("button", { class: "pt-btn pt-btn--ghost", type: "button", onclick: function () { go(step - 1); } }, "Back");
      if (step === 0) back.style.visibility = "hidden";
      var next = h("button", { class: "pt-btn", type: "button" }, step === qs.length - 1 ? "Review" : q.required ? "Next" : "Next / skip");
      next.addEventListener("click", function () {
        if (q.required && !(answers[q.id] && answers[q.id].length)) { fail("Please choose an answer to continue."); return; }
        go(step + 1);
      });
      body.appendChild(h("div", { class: "pt-actions" }, back, next));
    } else {
      body.appendChild(h("p", { class: "pt-sub" }, prefillNote || "This is what we'll match creators against."));
      if (opts.source) {
        // What Helvy flagged in the link or file, and when to launch, stay in view while the client checks.
        (opts.source.flags || []).filter(function (f) { return f.kind !== "claims_found"; }).forEach(function (f) {
          body.appendChild(h("div", { class: "bs-flag bs-flag--" + f.kind + " bs-flag--slim" }, h("span", { class: "bs-flag__ic", html: icon(f.kind === "licence" ? "shield" : "flag") }),
            h("p", null, h("b", null, f.title + ". "), f.text)));
        });
        var tl0 = timingLine(opts.source.timing, { short: true });
        if (tl0) body.appendChild(tl0);
      }
      var list = h("ul", { class: "pt-review" });
      qs.forEach(function (q, i) {
        var v = answers[q.id];
        if (!v || (v.length === 0)) { if (!q.required) return; }
        var label = q.type === "text" ? (v || "") : (q.type === "many" ? (v || []) : [v]).map(function (val) {
          return optionLabel(q, val);
        }).join(", ");
        list.appendChild(h("li", null, h("span", null, q.label.replace(/\?$/, "")), h("span", null, h("b", null, label || "Not answered"), " ",
          h("button", { type: "button", onclick: function () { go(i); } }, "change"))));
      });
      body.appendChild(list);
      body.appendChild(err);
      var missing = qs.filter(function (q) { return q.required && !(answers[q.id] && answers[q.id].length); });
      var cost = ME && ME.costs ? ME.costs.brief : 5;
      var run = h("button", { class: "pt-btn pt-btn--lime", type: "button" }, opts.attach ? "Score my selection" : "Show my creators");
      var freeLine = (ME && ME.costs && !ME.costs.search && ME.credits != null)
        ? (ME.credits >= cost ? creditsLine(cost) + " · free without written reasons" : "Free · written reasons need " + cost + " credits")
        : creditsLine(cost);
      body.appendChild(h("div", { class: "pt-actions" }, h("span", { class: "pt-note", style: "margin:0" }, opts.attach ? "Free" : freeLine),
        h("span", null, h("button", { class: "pt-btn pt-btn--ghost", type: "button", onclick: function () { go(0); }, style: "margin-right:8px" }, "Edit"), run)));
      if (missing.length) { run.disabled = true; fail("Still needed: " + missing.map(function (q) { return q.label.replace(/\?$/, ""); }).join("; ") + "."); }
      run.addEventListener("click", function () {
        run.disabled = true; run.textContent = T("Matching creators…"); fail("");
        var call = opts.attach ? api("POST", "/api/brief/attach", { token: opts.attach, answers: answers })
                               : api("POST", "/api/brief/run", { answers: answers });
        call.then(function (r) {
          if (r.b.ok && !r.b.empty) {
            if (r.b.credits != null) setCredits(r.b.credits);
            rememberBrief(r.b.brief_id);
            close(); results(r.b, qs, answers, opts); return;
          }
          run.disabled = false; run.textContent = T(opts.attach ? "Score my selection" : "Show my creators");
          fail(r.b.empty ? r.b.message : r.s === 429 ? "Too many requests. Please wait a few minutes." : (r.b.message || "Something went wrong. You weren't charged."));
        });
      });
    }
    close = layer(modal);
    currentClose = close;
    var base = close;
    close = function () { base(); if (currentClose === close) currentClose = null; };
    currentClose = close;
    x.onclick = function () { close(); };
  }

  /* ------------------------------------- brief from a link or a file (phase E)
     "Paste a product link" / "Upload a brief (PDF or Word)". The server reads it (public
     pages only; an uploaded file is read and dropped, never kept), Helvy fills the brief
     with a confidence for every field, copies only claims the source itself makes and
     flags regulated products. Nothing is used until the client presses "Use this brief",
     and every answer can still be changed after. One component for the brief window, the
     AI shortlist card and the chat. */
  var SRC_ROWS = [["product", "Product"], ["category", "Space"], ["audience", "Audience"], ["market", "Market"], ["goal", "Objective"], ["timing", "Timing"]];
  var CONF = { high: ["Found", "hi"], medium: ["Check", "md"], low: ["A guess", "lo"], missing: ["Not found", "no"] };
  var SRC_MAX = 4 * 1024 * 1024;
  function srcCostTag(kind) {
    if (ME && ME.kind === "admin") return null;
    if (ME && ME.ai_free) return h("span", { class: "hv-cost hv-cost--free" }, "Free with your campaign");
    if (!(ME && ME.ai)) return h("span", { class: "hv-cost hv-cost--free" }, "Free");
    var c = ME.costs && ME.costs[kind || "source"] != null ? ME.costs[kind || "source"] : 5;
    return h("span", { class: "hv-cost", html: icon("coin") + c + " credits" });
  }
  // "Saudi Derm Congress is in 14 weeks: cast now." The first window leads; two more follow, quieter.
  function timingLine(t, opts) {
    opts = opts || {};
    if (!t || !t.windows || !t.windows.length) return null;
    var box = h("div", { class: "bs-time" + (opts.dark ? " bs-time--dark" : "") });
    box.appendChild(h("span", { class: "bs-time__ic", html: icon("cal") }));
    var tx = h("div", { class: "bs-time__tx" });
    tx.appendChild(h("p", { class: "bs-time__lead" }, h("span", { class: "bs-time__k" }, "Best launch window"), t.windows[0].message));
    if (!opts.short && t.windows.length > 1) {
      var more = h("ul", { class: "bs-time__more" });
      t.windows.slice(1, 3).forEach(function (w) { more.appendChild(h("li", null, w.message)); });
      tx.appendChild(more);
    }
    if (!opts.short) tx.appendChild(h("p", { class: "bs-time__note" }, "Creator content needs 6–8 weeks from brief to posting." +
      (t.windows[0].dates && t.windows[0].dates !== "fixed" ? " Dates " + t.windows[0].dates + "." : "")));
    box.appendChild(tx);
    return box;
  }
  HV.timingLine = timingLine;

  function srcValue(id, res, qs) {
    var a = res.answers || {}, f = res.fields || {}, q = (qs || []).filter(function (x) { return x.id === id; })[0];
    var lab = function (qid, v) { var qq = (qs || []).filter(function (x) { return x.id === qid; })[0]; return qq ? optionLabel(qq, v) : v; };
    if (id === "category") return (a.category || []).map(function (v) { return lab("category", v); }).join(", ");
    if (id === "market") return (f.markets && f.markets.length ? f.markets : a.market ? [a.market] : []).map(function (v) { return lab("market", v); }).join(", ");
    if (id === "goal") return a.goal ? lab("goal", a.goal) : "";
    if (id === "timing") return [f.launch ? "Launch " + f.launch : "", a.timing ? lab("timing", a.timing) : ""].filter(Boolean).join(" · ");
    if (id === "audience") return [f.audience, a.gender && a.gender !== "Any" ? lab("gender", a.gender) : "", a.age && a.age !== "Any" ? lab("age", a.age) : ""].filter(Boolean).join(" · ");
    return q ? "" : (f[id] || "");
  }
  // The notes the server wrote, re-made from the fields the client edited (the "From ..." part stays).
  function srcNotes(res, product, audience) {
    var f = res.fields || {}, bits = [];
    var from = /(?:^|\. )(From .*)$/.exec((res.answers && res.answers.notes) || "");
    if (product) bits.push("Product: " + product + (f.brand && product.toLowerCase().indexOf(f.brand.toLowerCase()) < 0 ? " (" + f.brand + ")" : ""));
    if (audience) bits.push("Audience: " + audience);
    if (f.markets && f.markets.length > 1) bits.push("Markets: " + f.markets.join(", "));
    if (f.launch) bits.push("Launch: " + f.launch);
    if (from) bits.push(from[1]);
    return bits.join(". ").slice(0, 600);
  }

  HV.briefSource = function (opts) {
    opts = opts || {};
    var dark = !!opts.dark;
    var root = h("div", { class: "bs" + (dark ? " bs--dark" : "") + (opts.chat ? " bs--chat" : "") });
    var file = h("input", { type: "file", class: "bs__file", accept: ".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain", tabindex: "-1", "aria-hidden": "true" });
    var linkBtn = h("button", { class: "bs__opt", type: "button", "aria-expanded": "false", html: icon("link") + "<span>Paste a product link</span>" });
    var fileBtn = h("button", { class: "bs__opt", type: "button", html: icon("upload") + "<span>Upload a brief <small>PDF or Word</small></span>" });
    var pick = h("div", { class: "bs__pick", role: "group", "aria-label": "Start from a link or a file" }, linkBtn, fileBtn, file);
    var urlIn = h("input", { class: "bs__url", type: "url", inputmode: "url", autocomplete: "off", spellcheck: "false", maxlength: "2000",
                             placeholder: "https://brand.com/product", "aria-label": "Product page link" });
    var go = h("button", { class: "bs__go", type: "submit" }, "Read it");
    var form = h("form", { class: "bs__link", hidden: "" }, urlIn, go);
    var fine = h("p", { class: "bs__fine" });
    var tag = srcCostTag("source");
    if (tag) fine.appendChild(tag);
    fine.appendChild(h("span", null, "Helvy reads the page or file and fills the brief for you to check. Files are read, never kept."));
    var err = h("p", { class: "bs__err", role: "alert", hidden: "" });
    var out = h("div", { class: "bs__out", "aria-live": "polite" });
    if (opts.lead) root.appendChild(h("p", { class: "bs__lead" }, opts.lead));
    root.appendChild(pick); root.appendChild(form); root.appendChild(fine); root.appendChild(err); root.appendChild(out);

    function fail(t) { err.hidden = !t; err.textContent = t || ""; }
    function busy(on, label) {
      linkBtn.disabled = fileBtn.disabled = go.disabled = urlIn.disabled = on;
      root.classList.toggle("is-busy", on);
      out.textContent = "";
      if (on && HV.cooking) {
        var cook = HV.cooking({ compact: true, dark: dark, hold: true, steps: [label, "Finding the product and who it's for…", "Filling your brief…", "Checking claims and timing…"] });
        out.appendChild(h("div", { class: "bs__cook" }, cook));
        root._cook = cook;
      } else if (root._cook) { root._cook.stop(); root._cook = null; }
    }
    function send(body, label) {
      fail("");
      busy(true, label);
      return api("POST", "/api/brief/source", body).then(function (r) {
        busy(false);
        if (r.b && r.b.ok) {
          if (r.b.credits != null) setCredits(r.b.credits);
          loadQuestions().then(function (qs) { show(r.b, qs); });
          return;
        }
        fail(r.s === 429 ? "Too many tries. Please wait a few minutes." : r.s === 413 ? "That file is too large. Briefs up to 4 MB can be read." :
             (r.b && r.b.message) || "That couldn't be read. Please try again.");
      });
    }
    linkBtn.addEventListener("click", function () {
      var open = form.hidden;
      form.hidden = !open; linkBtn.setAttribute("aria-expanded", String(open));
      linkBtn.classList.toggle("is-on", open);
      if (open) urlIn.focus();
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var v = urlIn.value.trim();
      if (v.length < 4 || /\s/.test(v)) { fail("Paste the product page's full address."); urlIn.focus(); return; }
      send({ url: v }, "Opening the page…");
    });
    fileBtn.addEventListener("click", function () { file.value = ""; file.click(); });
    file.addEventListener("change", function () {
      var f = file.files && file.files[0];
      if (!f) return;
      if (/\.doc$/i.test(f.name)) { fail("Old Word files (.doc) can't be read. Save it as .docx or PDF and upload again."); return; }
      if (f.size > SRC_MAX) { fail("That file is too large. Briefs up to 4 MB can be read."); return; }
      var rd = new FileReader();
      rd.onload = function () { send({ file: { name: f.name, data: rd.result } }, "Reading " + f.name + "…"); };
      rd.onerror = function () { fail("That file couldn't be opened."); };
      rd.readAsDataURL(f);
    });

    function show(res, qs) {
      out.textContent = "";
      var card = h("section", { class: "bs-res", "aria-label": "What Helvy read" });
      var src = res.source || {};
      card.appendChild(h("header", { class: "bs-res__hd" },
        h("span", { class: "bs-res__ic", html: icon(src.kind === "file" ? "brief" : "link") }),
        h("div", null, h("h3", { class: "bs-res__t" }, "Helvy read " + (src.kind === "file" ? "your brief" : src.label || "the page")),
          h("p", { class: "bs-res__s" }, src.kind === "file" ? src.label + " · not kept" : "Check each line. Anything Helvy wasn't sure of is marked.")),
        res.spent ? h("span", { class: "bs-res__spent" }, res.spent + " credits used") : null));
      if (!res.ai) card.appendChild(h("p", { class: "bs-res__warn" }, "Helvy's AI is resting, so only the plain facts were picked out. Check every answer."));
      var dl = h("dl", { class: "bs-rows" });
      var edits = {};
      SRC_ROWS.forEach(function (r) {
        var conf = (res.confidence || {})[r[0]] || "missing", c = CONF[conf] || CONF.missing;
        var val = srcValue(r[0], res, qs), dd;
        if (r[0] === "product" || r[0] === "audience") {
          var inp = h("input", { class: "bs-rows__in", type: "text", maxlength: r[0] === "product" ? "80" : "160", "aria-label": r[1],
                                 placeholder: r[0] === "product" ? "Product name" : "Who it's for" });
          inp.value = r[0] === "product" ? ((res.fields || {}).product || "") : ((res.fields || {}).audience || "");
          edits[r[0]] = inp;
          dd = h("dd", null, inp);
          if (r[0] === "audience" && val && val !== inp.value) dd.appendChild(h("small", null, val.replace(inp.value, "").replace(/^ · /, "")));
        } else dd = h("dd", null, val || "—");
        dl.appendChild(h("div", { class: "bs-rows__r" }, h("dt", null, r[1]), dd,
          h("span", { class: "bs-conf bs-conf--" + c[1], title: conf === "missing" ? "Not in the source: answer it in the next step" : "How sure Helvy is" }, c[0])));
      });
      card.appendChild(dl);
      (res.flags || []).filter(function (f) { return f.kind !== "claims_found" || !(res.claims && res.claims.length); }).forEach(function (f) {
        card.appendChild(h("div", { class: "bs-flag bs-flag--" + f.kind }, h("span", { class: "bs-flag__ic", html: icon(f.kind === "licence" ? "shield" : "flag") }),
          h("p", null, h("b", null, f.title + ". "), f.text)));
      });
      if (res.claims && res.claims.length) {
        var cl = h("ul", { class: "bs-claims" });
        res.claims.forEach(function (c) { cl.appendChild(h("li", null, "“" + c + "”")); });
        card.appendChild(h("div", { class: "bs-claims__w" }, h("p", { class: "bs-claims__h" }, "Claims your source makes (Helvy adds none)"), cl));
      }
      var tl = timingLine(res.timing, { dark: false });
      if (tl) card.appendChild(tl);
      var use = h("button", { class: "bs__use", type: "button", html: "<span>Use this brief</span>" + icon("arrow") });
      var again = h("button", { class: "bs__again", type: "button" }, "Try another link or file");
      card.appendChild(h("div", { class: "bs-res__go" }, again, use));
      out.appendChild(card);
      again.addEventListener("click", function () { out.textContent = ""; pick.hidden = false; fine.hidden = false; urlIn.value = ""; urlIn.focus(); });
      use.addEventListener("click", function () {
        var answers = {};
        Object.keys(res.answers || {}).forEach(function (k) { answers[k] = res.answers[k]; });
        answers.notes = srcNotes(res, edits.product.value.trim(), edits.audience.value.trim());
        if (!answers.notes) delete answers.notes;
        if (opts.onUse) opts.onUse(answers, res);
      });
      pick.hidden = true; form.hidden = true; fine.hidden = true;
      linkBtn.classList.remove("is-on"); linkBtn.setAttribute("aria-expanded", "false");
      try { card.scrollIntoView({ block: "nearest", behavior: REDUCE ? "auto" : "smooth" }); } catch (e) { /* old browser */ }
      if (opts.onShow) opts.onShow(res);
    }
    root.reset = function () { out.textContent = ""; pick.hidden = false; fine.hidden = false; fail(""); };
    return root;
  };

  var BASIS = { analysis: ["Measured", "pt-tag--good"], basic: ["Public data", ""], roster: ["Estimated", "pt-tag--warn"] };
  function scoreClass(tag) { return /Strong/.test(tag) ? "strong" : /Good/.test(tag) ? "good" : /Possible/.test(tag) ? "possible" : "no"; }

  function creatorCard(p) {
    var c = p.creator || {};
    var photo = h("div", { class: "pt-photo" });
    bg(photo, c.photo_url);
    var tags = h("div", { class: "pt-tags" });
    var b = BASIS[p.basis] || BASIS.roster;
    tags.appendChild(h("span", { class: "pt-tag " + b[1], title: p.basis === "roster" ? "Estimated from what we hold on file. A full analysis confirms it." : "" }, b[0]));
    (p.strengths || []).slice(0, 2).forEach(function (s) { tags.appendChild(h("span", { class: "pt-tag pt-tag--good" }, s)); });
    (p.watchouts || []).slice(0, 1).forEach(function (s) { tags.appendChild(h("span", { class: "pt-tag pt-tag--warn" }, s)); });
    var meta = [c.platform, followers(c.followers) + " followers", c.city, price(p.price)].filter(Boolean).join(" · ");
    return h("article", { class: "pt-card" }, photo,
      h("div", null, h("p", { class: "pt-name" }, c.name || p.code), h("p", { class: "pt-meta" }, meta),
        p.why ? h("p", { class: "pt-why" }, p.why) : null, tags),
      h("div", { class: "pt-score pt-score--" + scoreClass(p.tag) }, h("b", null, String(p.score)), h("span", null, p.tag)));
  }

  /* -- "Other": every option question also takes a short answer the client types.
     It is sent as "other:<text>"; the server reads it into the brief (a number of
     creators, a budget, a country...) and passes the words on in the notes. -- */
  var OTHER = "other:";
  function isOther(v) { return typeof v === "string" && v.indexOf(OTHER) === 0; }
  function otherOf(v) {
    var list = Array.isArray(v) ? v : [v];
    for (var i = 0; i < list.length; i++) if (isOther(list[i])) return list[i].slice(OTHER.length);
    return "";
  }
  // The answer with the typed words in place of any earlier ones; null when nothing is left.
  function withOther(q, v, text) {
    text = String(text || "").replace(/\s+/g, " ").trim().slice(0, 80);
    if (q.type === "many") {
      var list = (Array.isArray(v) ? v : []).filter(function (x) { return !isOther(x) && (!text || x !== "any"); });
      if (text) list.push(OTHER + text);
      return list.length ? list : null;
    }
    return text ? OTHER + text : null;
  }
  function otherInput(q, value, onInput, onEnter) {
    var inp = h("input", { class: "pt-other", type: "text", maxlength: "80", placeholder: "Type your answer", "aria-label": "Other answer" });
    inp.value = value || "";
    inp.addEventListener("input", function () { onInput(inp.value); });
    if (onEnter) inp.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); onEnter(); } });
    return inp;
  }

  /* -- naming an AI selection: the AI saves it under a made-up name, so before
     it opens the client can type their own (the same creators, re-saved). -- */
  function nameForm(current, label, onSave) {
    var form = h("form", { class: "pt-namer" });
    var inp = h("input", { class: "pt-namer__in", type: "text", maxlength: "100", "aria-label": "Name this selection" });
    inp.value = current || "";
    var btn = h("button", { class: "pt-namer__go", type: "submit" }, label || "Save and open");
    form.appendChild(h("span", { class: "pt-namer__l" }, "Name this selection"));
    form.appendChild(h("span", { class: "pt-namer__row" }, inp, btn));
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var v = inp.value.replace(/\s+/g, " ").trim() || current;
      inp.disabled = btn.disabled = true; btn.textContent = T("Saving…");
      onSave(v, function () { inp.disabled = btn.disabled = false; btn.textContent = T(label || "Save and open"); });
    });
    setTimeout(function () { try { inp.focus({ preventScroll: false }); inp.select(); } catch (e) { /* old browser */ } }, 30);
    return form;
  }
  function renameThenOpen(token, codes, current, name) {
    var open = function () { location.href = ROOT + "selection/#s=" + encodeURIComponent(token); };
    if (!name || name === current || !codes || !codes.length) { open(); return; }
    api("POST", "/api/selection", { token: token, codes: codes, name: name }).then(open);
  }
  function codesOf(picks) { return (picks || []).map(function (p) { return p.code; }); }

  function results(res, qs, answers, opts) {
    opts = opts || {};
    var modal = h("div", { class: "pt-modal pt-modal--wide", role: "dialog", "aria-modal": "true", "aria-labelledby": "pt-res-title" });
    var close;
    modal.appendChild(h("div", { class: "pt-head" }, h("h2", { class: "pt-title", id: "pt-res-title" }, "Your shortlist"),
      h("button", { class: "pt-x", type: "button", "aria-label": "Close", onclick: function () { close(); } }, "×")));
    var body = h("div", { class: "pt-body" });
    var sum = h("div", { class: "pt-summary" }, res.summary || (opts.attach
        ? (LANG === "ar" ? "قيّمنا " + res.picks.length + " مؤثرين في قائمتك مقابل هذا الطلب، الأفضل أولاً." : "We scored the " + res.picks.length + " creators in your selection against this brief, best fit first.")
        : (LANG === "ar" ? res.picks.length + " مؤثرين يطابقون طلبك، مرتبين حسب الملاءمة." : res.picks.length + " creators matched your brief, ranked by fit.")),
      h("small", null, res.brief));
    body.appendChild(sum);
    var tlr = timingLine(res.timing, { short: true });
    if (tlr) body.appendChild(tlr);
    var list = h("div", { class: "pt-list" });
    res.picks.forEach(function (p) { list.appendChild(creatorCard(p)); });
    body.appendChild(list);
    if (!res.narrated) body.appendChild(h("p", { class: "pt-note" }, "Scores come from our data. Written reasons weren't generated this time."));
    if (res.alternates && res.alternates.length) {
      var d = h("details", { class: "pt-alt" }, h("summary", null, res.alternates.length + " close runners-up"));
      var ul = h("ul");
      res.alternates.forEach(function (a) {
        ul.appendChild(h("li", null, h("span", null, (a.creator && a.creator.name) || a.code), h("span", null, a.score + " · " + price(a.price))));
      });
      d.appendChild(ul); body.appendChild(d);
    }
    modal.appendChild(body);
    var t = res.totals || {};
    var total = h("div", { class: "pt-total" }, t.from ? "Estimated creator fees " : "", t.from ? h("b", null, "SAR " + money(t.from) + (t.to && t.to !== t.from ? " – " + money(t.to) : "")) : "",
      t.unpriced ? " (+" + t.unpriced + " on request)" : "", t.from ? " · 15% VAT extra" : "");
    var open = h("a", { class: "pt-btn pt-btn--lime", href: ROOT + "selection/#s=" + encodeURIComponent(res.token), style: "text-decoration:none;display:inline-block" }, "Open as selection");
    var refine = h("button", { class: "pt-btn pt-btn--ghost", type: "button", onclick: function () { close(); wizard(qs, answers, 0, null, opts); } }, "Refine brief");
    if (opts.attach && /selection/.test(location.pathname) && location.hash.indexOf(encodeURIComponent(res.token)) > -1) {
      open.addEventListener("click", function (e) { e.preventDefault(); location.reload(); });
    } else if (!opts.attach) {
      // A new AI shortlist: the client names it before it opens.
      open.addEventListener("click", function (e) {
        e.preventDefault();
        if (modal.querySelector(".pt-namer")) return;
        var current = res.name || "AI shortlist";
        body.appendChild(nameForm(current, "Save and open", function (v) { renameThenOpen(res.token, codesOf(res.picks), current, v); }));
      });
    }
    modal.appendChild(h("div", { class: "pt-bar" }, total, h("span", null, refine, " ", open)));
    close = layer(modal);
  }

  /* ------------------------------------------ brief for a hand-built selection */

  var offered = {};
  function offerBrief(token) {
    if (!ME || !ME.signed_in || !token || offered[token]) return;
    offered[token] = 1;
    api("GET", "/api/brief/for?s=" + encodeURIComponent(token)).then(function (r) {
      if (!r.b.ok || r.b.brief) return;
      var box = h("div", { class: "pt-toast", role: "dialog", "aria-label": "Score this selection" },
        h("p", { class: "pt-toast__t" }, "Score this selection"),
        h("p", { class: "pt-toast__b" }, "Six quick questions about the campaign, and Helvy scores the creators already in this selection. It doesn't add anyone. Free."));
      if (LANG === "ar") box.setAttribute("dir", "rtl");
      var later = h("button", { class: "pt-btn pt-btn--ghost", type: "button", onclick: function () { box.remove(); } }, "Not now");
      var go = h("button", { class: "pt-btn pt-btn--lime", type: "button", onclick: function () {
        // Scoring needs only who the audience is and what the product is: six questions, not eleven.
        box.remove(); objectiveStudio(token, {});
      } }, "Answer questions");
      box.appendChild(h("div", { class: "pt-actions", style: "margin-top:12px" }, later, go));
      document.body.appendChild(box);
    });
  }
  window.addEventListener("hv:selection-saved", function (e) { offerBrief(e.detail && e.detail.token); });
  // The selection page's "Add your campaign objective" (and its Edit): the objective studio,
  // fix batch 3. Same world as the AI shortlist card (ink, lime, Helvy reacting to every
  // answer over a campaign-power meter), but it only SCORES the creators already in this
  // selection: nothing is added, removed or rebuilt. The goal takes several answers. On the
  // last answer the meter hits full power, Helvy works through named steps, and the page
  // comes back with the round score stamps on the cards.
  var OB_STEPS = {
    goal: ["Goal", '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r=".6" fill="currentColor"/>'],
    platforms: ["Platforms", '<rect x="7" y="3" width="10" height="18" rx="2.5"/><path d="M11 17.5h2"/>'],
    market: ["Country", '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.6 2.6 2.6 14.4 0 17M12 3.5c-2.6 2.6-2.6 14.4 0 17"/>'],
    gender: ["Audience", '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c.6-3.8 3.3-6 7-6s6.4 2.2 7 6"/>'],
    age: ["Age", '<rect x="4" y="5" width="16" height="15" rx="2.5"/><path d="M4 10h16M9 3v4M15 3v4"/>'],
    category: ["Space", '<path d="M3.5 12.5l8-8h7v7l-8 8z"/><circle cx="15" cy="9" r="1.3"/>']
  };
  var OB_HINT = {
    goal: "Pick one or more. Each one counts in every creator’s score.",
    platforms: "Pick every platform the content runs on.",
    market: "Where the people you want to reach live.",
    gender: "Leave it if the product is for everyone.",
    age: "Leave it if every age group matters.",
    category: "Pick one or more."
  };
  function obPoints(q) { return q.required ? 200 : 100; }
  function objectiveStudio(token, start) {
    start = start || {};
    var S = window.hvSelection;
    var selName = S && S.name ? S.name() : "this selection";
    var nIn = S && S.codes ? S.codes().length : 0;
    loadQuestions().then(function (all) {
      var qs = all.filter(function (q) { return q.required || q.id === "gender" || q.id === "age"; });
      var answers = {};
      Object.keys(start.answers || {}).forEach(function (k) { if (qs.some(function (q) { return q.id === k; })) answers[k] = start.answers[k]; });
      if (typeof answers.goal === "string") answers.goal = [answers.goal];
      var step = 0, busy = false;
      var reduce = REDUCE;
      var card = h("div", { class: "ai-sl is-open ob", role: "dialog", "aria-modal": "true", "aria-labelledby": "ob-t" });
      var x = h("button", { class: "ai-sl__quit ob__x", type: "button", "aria-label": "Close" });
      x.innerHTML = aiSvg('<path d="M6 6l12 12M18 6L6 18"/>', 18);
      card.appendChild(h("header", { class: "ob__hd" },
        h("div", null, h("h2", { class: "ai-sl__title", id: "ob-t" }, start.edit ? "Edit this selection’s objective" : "Score this selection"),
          h("p", { class: "ob__lead" }, "Helvy scores the " + (nIn ? nIn + " creator" + (nIn === 1 ? "" : "s") + " already in " : "creators already in ") + "“" + selName +
            "” against your campaign. Nothing is added, removed or changed. Free.")), x));
      var run = h("div", { class: "ai-sl__run ob__run" });
      var coach = h("div", { class: "ai-sl__coach", "aria-hidden": "true" });
      var cring = h("div", { class: "ai-sl__cring" });
      var power = h("div", { class: "ai-sl__power" });
      power.innerHTML = '<p class="ai-sl__pw-h">Campaign power</p><p class="ai-sl__pw-n"><b>0</b><small> / 1000</small></p>' +
        '<div class="ai-sl__pw-bar"><i></i></div><p class="ai-sl__pw-lvl">Draft</p>';
      coach.appendChild(cring); coach.appendChild(power);
      var main = h("div", { class: "ai-sl__main" });
      var head = h("div", { class: "ai-sl__head ob__head" });
      var track = h("ol", { class: "ai-sl__track ob__track", "aria-label": "Objective progress" });
      track.style.gridTemplateColumns = "repeat(" + qs.length + ", 1fr)";
      qs.forEach(function (q, i) {
        var d = OB_STEPS[q.id] || [q.id, ""];
        var li = h("li", { class: "ai-sl__node", "data-i": String(i) });
        li.innerHTML = '<span class="ai-sl__dot">' + aiSvg(d[1], 18) + '<i class="ai-sl__tick">' + aiSvg('<path d="M5 12.5l4.2 4.2L19 7"/>', 16) + '</i></span><span class="ai-sl__lbl">' + d[0] + "</span>";
        li.addEventListener("click", function () { if (!busy && (i <= step || answered(qs[i - 1] || q))) show(i); });
        track.appendChild(li);
      });
      var fill = h("span", { class: "ai-sl__fill", "aria-hidden": "true" });
      track.appendChild(fill);
      head.appendChild(track);
      var stage = h("div", { class: "ai-sl__stage ob__stage" });
      main.appendChild(head); main.appendChild(stage);
      run.appendChild(coach); run.appendChild(main);
      card.appendChild(run);
      var close = layer(card);
      x.addEventListener("click", function () { close(); });

      /* -- Helvy: a reaction plays once, then he waits (thinking) -- */
      var CLIPS = { point: "point", think: "thinking", yes: "approve", cheer: "celebrate", idle: "idle" };
      function react(kind, loop, seq) {
        if (reduce || !HVH) { if (!cring.firstChild) cring.appendChild(clip("idle", "ob__still", { still: true })); return; }
        var v = HVH.video(CLIPS[kind] || "idle", { once: !loop && !seq, then: !loop && !seq ? "thinking" : null, seq: seq, cls: "ai-sl__cvid", eager: true });
        var old = [].slice.call(cring.querySelectorAll("video, img"));
        var swap = function () { old.forEach(function (o) { o.remove(); }); };
        v.addEventListener("playing", swap, { once: true });
        setTimeout(swap, 900);
        cring.appendChild(v);
        HVH.play(v);
        cring.classList.remove("is-bump"); void cring.offsetWidth; cring.classList.add("is-bump");
      }
      function say(text) {
        if (reduce) return;
        var old = coach.querySelector(".ai-sl__say"); if (old) old.remove();
        coach.appendChild(h("span", { class: "ai-sl__say" }, text));
      }

      /* -- campaign power: every answered question fills the meter -- */
      function answered(q) { var v = answers[q.id]; return Array.isArray(v) ? v.length > 0 : !!v; }
      var shown = 0;
      function score() { return qs.reduce(function (t, q) { return t + (answered(q) ? obPoints(q) : 0); }, 0); }
      function paintPower(gain) {
        var n = Math.min(1000, score() + (qs.some(function (q) { return !q.required; }) ? 0 : 200));
        var lvl = n >= 1000 ? "Full power" : n >= 600 ? "Strong" : n >= 300 ? "Good" : "Draft";
        var b = power.querySelector("b");
        if (gain && n > shown) { power.classList.remove("is-gain"); void power.offsetWidth; power.classList.add("is-gain"); }
        shown = n; b.textContent = String(n);
        power.querySelector("i").style.width = (n / 10) + "%";
        power.querySelector(".ai-sl__pw-lvl").textContent = lvl;
        power.classList.toggle("is-full", n >= 1000);
        [].forEach.call(track.querySelectorAll(".ai-sl__node"), function (li, i) {
          li.classList.toggle("is-done", answered(qs[i]) && i !== step);
          li.classList.toggle("is-now", i === step);
        });
        fill.style.setProperty("--p", (qs.length > 1 ? Math.min(100, step / (qs.length - 1) * 100) : 100) + "%");
      }
      function plus(btn, pts) {
        if (reduce || !btn) return;
        var s2 = h("span", { class: "ai-sl__plus", "aria-hidden": "true" }, "+" + pts);
        btn.appendChild(s2); setTimeout(function () { s2.remove(); }, 800);
      }

      /* -- one question -- */
      function show(i) {
        step = Math.max(0, Math.min(i, qs.length - 1));
        var q = qs[step], many = q.type === "many" || q.id === "goal";
        stage.textContent = "";
        var panel = h("div", { class: "ai-sl__panel ai-sl__q" });
        panel.appendChild(h("p", { class: "ob__count" }, "Question " + (step + 1) + " of " + qs.length + (q.required ? "" : " · optional")));
        panel.appendChild(h("h3", { class: "ai-sl__ask", id: "ob-q" }, q.id === "goal" ? "What are the campaign’s goals?" : q.label));
        panel.appendChild(h("p", { class: "ai-sl__hint" }, OB_HINT[q.id] || ""));
        var opts = h("div", { class: "ai-sl__opts", role: many ? "group" : "radiogroup", "aria-labelledby": "ob-q" });
        var cur = function () { var v = answers[q.id]; return Array.isArray(v) ? v : v ? [v] : []; };
        q.options.forEach(function (o) {
          var b = h("button", { class: "ai-sl__opt", type: "button", "aria-pressed": String(cur().indexOf(o.value) > -1) }, o.label);
          if (!many) b.setAttribute("role", "radio"), b.setAttribute("aria-checked", String(cur().indexOf(o.value) > -1));
          b.addEventListener("click", function () {
            var was = answered(q);
            if (many) {
              var list = cur().slice(), k = list.indexOf(o.value);
              if (o.value === "any") list = k > -1 ? [] : ["any"];
              else { list = list.filter(function (v) { return v !== "any"; }); if (k > -1) list.splice(k, 1); else list.push(o.value); }
              if (q.id === "goal" && o.value === "balanced" && k === -1) list = ["balanced"];
              else if (q.id === "goal") list = list.filter(function (v) { return v !== "balanced" || list.length === 1; });
              if (list.length) answers[q.id] = list; else delete answers[q.id];
              [].forEach.call(opts.children, function (bb, bi) { bb.setAttribute("aria-pressed", String(cur().indexOf(q.options[bi].value) > -1)); });
              next.disabled = q.required && !answered(q);
            } else {
              answers[q.id] = o.value;
              [].forEach.call(opts.children, function (bb, bi) { var on = q.options[bi].value === o.value; bb.setAttribute("aria-pressed", String(on)); bb.setAttribute("aria-checked", String(on)); });
            }
            if (!was && answered(q)) { plus(b, obPoints(q)); react("yes"); say(["Nice", "Got it", "Good one", "Noted"][step % 4]); }
            paintPower(true);
            if (!many) setTimeout(function () { if (step === qs.indexOf(q)) advance(); }, 260);
          });
          opts.appendChild(b);
        });
        panel.appendChild(opts);
        var nav = h("div", { class: "ai-sl__nav" });
        var back = h("button", { class: "ai-sl__back", type: "button" }, "Back");
        back.addEventListener("click", function () { show(step - 1); react("point"); });
        if (step === 0) back.hidden = true;
        var last = step === qs.length - 1;
        var next = h("button", { class: "ai-sl__next", type: "button" }, last ? "Score this selection" : q.required ? "Next" : "Next / skip");
        next.disabled = q.required && !answered(q);
        next.addEventListener("click", advance);
        nav.appendChild(back); nav.appendChild(next);
        panel.appendChild(nav);
        if (step === 0 && HV.briefSource) {
          // Phase E: answer from a product page or the client's own brief file (costs credits).
          var srcBox = h("div", { class: "ob__src", hidden: "" });
          var srcBtn = h("button", { class: "ob__srcb", type: "button", "aria-expanded": "false", html: icon("link") + "<span>Fill these from a product page or brief</span>" });
          srcBtn.addEventListener("click", function () {
            var open = srcBox.hidden; srcBox.hidden = !open; srcBtn.setAttribute("aria-expanded", String(open));
            if (open && !srcBox.firstChild) srcBox.appendChild(HV.briefSource({ dark: true, onUse: function (got) {
              qs.forEach(function (qq) { if (got[qq.id] != null && got[qq.id] !== "") answers[qq.id] = qq.id === "goal" && !Array.isArray(got.goal) ? [got.goal] : got[qq.id]; });
              react("yes"); say("Filled in"); paintPower(true);
              var miss = qs.filter(function (qq) { return qq.required && !answered(qq); })[0];
              show(miss ? qs.indexOf(miss) : qs.length - 1);
            } }));
          });
          panel.appendChild(h("div", { class: "ob__srcrow" }, srcBtn));
          panel.appendChild(srcBox);
        }
        stage.appendChild(panel);
        paintPower(false);
        var first = opts.querySelector('[aria-pressed="true"]') || opts.firstChild;
        if (first) first.focus({ preventScroll: true });
      }
      function advance() {
        var q = qs[step];
        if (q.required && !answered(q)) return;
        if (step < qs.length - 1) { show(step + 1); react("point"); return; }
        finish();
      }

      /* -- full power: Helvy scores the selection -- */
      function finish() {
        var miss = qs.filter(function (q) { return q.required && !answered(q); })[0];
        if (miss) { show(qs.indexOf(miss)); return; }
        busy = true;
        qs.forEach(function (q) { if (!answered(q) && !q.required) answers[q.id] = q.id === "gender" || q.id === "age" ? "Any" : answers[q.id]; });
        shown = 0; paintPower(true);
        power.querySelector("b").textContent = "1000"; power.querySelector("i").style.width = "100%";
        power.querySelector(".ai-sl__pw-lvl").textContent = "Full power"; power.classList.add("is-full");
        [].forEach.call(track.querySelectorAll(".ai-sl__node"), function (li) { li.classList.add("is-done"); li.classList.remove("is-now"); });
        fill.style.setProperty("--p", "100%");
        x.disabled = true;
        react("think", false, COOK_SEQ);
        say("Full power");
        var goals = (answers.goal || []).map(function (g) { return optionLabel(qs[0], g); });
        var STEPS = ["Reading your " + (goals.length > 1 ? "goals" : "goal") + "…", "Checking audiences…", "Scoring each creator…", "Putting the scores on your cards…"];
        stage.textContent = "";
        var list = h("ol", { class: "ai-sl__list ob__steps", "aria-live": "polite" });
        STEPS.forEach(function (t) { list.appendChild(h("li", { class: "ai-sl__st" }, h("span", { class: "ai-sl__st-dot" }), h("span", null, t))); });
        var bar = h("div", { class: "ai-sl__bar" }, h("i"));
        stage.appendChild(h("div", { class: "ai-sl__panel ob__wait", role: "status" },
          h("h3", { class: "ai-sl__ask" }, "Scoring " + (nIn ? nIn + " creator" + (nIn === 1 ? "" : "s") : "your selection")),
          h("p", { class: "ai-sl__hint" }, "For " + (goals.join(" and ") || "your campaign").toLowerCase() + ". Only the creators already in “" + selName + "”."), list, bar));
        var k = 0, t0 = Date.now(), res = null, done = false;
        function light() {
          [].forEach.call(list.children, function (li, i) { li.className = "ai-sl__st" + (i < k ? " is-done" : i === k ? " is-now" : ""); });
          bar.firstChild.style.width = Math.max(4, Math.round(k / STEPS.length * 100)) + "%";
        }
        light();
        var tick = setInterval(function () {
          if (k < STEPS.length - 1) { k++; light(); }
          else if (res) { clearInterval(tick); k = STEPS.length; light(); end(); }
        }, reduce ? 300 : 850);
        api("POST", "/api/brief/attach", { token: token, answers: answers }).then(function (r) { res = r; if (!r.b || !r.b.ok) { clearInterval(tick); fail(r); } });
        function fail(r) {
          busy = false; x.disabled = false;
          stage.textContent = "";
          var again = h("button", { class: "ai-sl__next", type: "button" }, "Try again");
          again.addEventListener("click", finish);
          stage.appendChild(h("div", { class: "ai-sl__panel" }, h("h3", { class: "ai-sl__ask" }, "That didn’t go through"),
            h("p", { class: "ai-sl__hint" }, (r.b && r.b.message) || (r.s === 429 ? "Too many tries. Please wait a few minutes." : "Nothing was changed. Please try again.")),
            h("div", { class: "ai-sl__nav" }, again)));
          react("idle", true);
        }
        function end() {
          if (done) return; done = true;
          if (res.b.brief_id) rememberBrief(res.b.brief_id);
          react("cheer"); say("Scored!");
          stage.appendChild(h("p", { class: "ob__done" }, icon("check"), "Scores are on your cards."));
          var refresh = S && S.refresh ? S.refresh() : Promise.resolve();
          Promise.resolve(refresh).then(function () {
            setTimeout(function () {
              close();
              if (S && S.toast) S.toast("Objective added. Each creator now shows their score for it.");
              if (!(S && S.refresh)) location.reload();
            }, reduce ? 200 : 1300);
          });
        }
      }

      react("point"); say(start.edit ? "Let’s tweak it" : "Let’s score it");
      // Edit opens on the first question, answers filled in, the meter already up.
      show(0);
    });
  }
  // The selection page's "Add your campaign objective" action, and Edit on its done state.
  HV.scoreBrief = function (token, o) {
    if (!token) return;
    offered[token] = 1;
    o = o || {};
    if (!o.edit) { objectiveStudio(token, {}); return; }
    api("GET", "/api/brief/for?s=" + encodeURIComponent(token)).then(function (r) {
      objectiveStudio(token, { edit: true, answers: (r.b && r.b.brief && r.b.brief.answers) || {} });
    });
  };

  // No fit scores on the catalogue (client, 2026-10-10): scoring happens only inside a selection,
  // once its campaign objective is set, on the round stamp. The catalogue used to paint a
  // "FIT x%" pill on every card for the last brief (a MutationObserver repainting them on every
  // DOM change, plus a /api/brief/scores call); all of that is gone. The last brief is still
  // remembered for the chat and the AI card.
  function rememberBrief(id) { if (id) { try { sessionStorage.setItem("hv_brief", String(id)); } catch (e) { /* blocked */ } } }

  /* ------------------------------------------------------------------ chat */

  var chatThread = null;
  var chatBrief = null;                // the answers gathered for free in this chat
  var IDEAS = ["Plan a campaign with me", "Suggest creators for a skincare launch in KSA", "What can SAR 80,000 reach on Instagram?", "What happens after I pick a selection?"];
  // A message that asks for creators or a campaign gets the free questions first, so the one paid
  // call that follows has everything it needs.
  var REQUEST = /campaign|creator|influencer|shortlist|launch|recommend|suggest|find|looking for|need .*(people|creators)|ugc|حمل|مؤثر|إطلاق|اطلاق|ابحث|أبحث|اقترح/i;
  var FLOW = ["goal", "platforms", "market", "category", "budget", "count"];
  var SHORT = { goal: "Goal", platforms: "Platforms", market: "Audience", category: "Product space", budget: "Budget (SAR)", count: "Creators" };

  function optionLabel(q, v) {
    if (isOther(v)) return v.slice(OTHER.length);
    var o = (q.options || []).filter(function (x) { return x.value === v; })[0];
    return o ? o.label : v;
  }

  function openChat() {
    var log = h("div", { class: "pt-log", role: "log", "aria-live": "polite" });
    var drawer = h("aside", { class: "pt-drawer", role: "dialog", "aria-label": "Ask HelloVoice AI" });
    var close;
    drawer.appendChild(h("div", { class: "pt-head" }, h("h2", { class: "pt-title" }, "Ask HelloVoice AI"),
      h("button", { class: "pt-x", type: "button", "aria-label": "Close", onclick: function () { close(); } }, "×")));
    drawer.appendChild(log);
    var ta = h("textarea", { rows: "1", placeholder: "Ask about creators, prices or your campaign…", "aria-label": "Your message", maxlength: "800" });
    var send = h("button", { class: "pt-btn pt-btn--lime", type: "button", style: "padding:12px 20px 10px" }, "Send");
    var foot = h("div", { class: "pt-foot" });
    function refreshFoot() {
      foot.textContent = (ME && ME.credits != null ? "Questions are free · 1 credit per AI answer · " + ME.credits + " left. " : "") +
        "The assistant can be wrong; final quotes come from our team.";
    }
    refreshFoot();
    drawer.appendChild(h("div", { class: "pt-compose" }, ta, send));
    drawer.appendChild(foot);

    function scroll() { log.scrollTop = log.scrollHeight; }
    function bubble(kind, text) { var b = h("div", { class: "pt-msg-b pt-msg-b--" + kind }, text); log.appendChild(b); scroll(); return b; }
    function cards(list) {
      if (!list || !list.length) return;
      var wrap = h("div", { class: "pt-cards" });
      list.forEach(function (c) {
        var ph = h("div", { class: "pt-photo" });
        bg(ph, c.photo_url);
        var m = h("button", { class: "pt-mini", type: "button" }, ph, h("div", null, h("b", null, c.name), h("span", null, [c.fit != null ? "Fit " + c.fit + "/100" : "", followers(c.followers), c.city, price(c.price)].filter(Boolean).join(" · "))));
        m.addEventListener("click", function () {
          var card = document.querySelector('.cat-card[data-code="' + c.code + '"]');
          if (card) { close(); card.scrollIntoView({ behavior: "smooth", block: "center" }); card.style.outline = "3px solid var(--lime)"; setTimeout(function () { card.style.outline = ""; }, 2400); }
        });
        wrap.appendChild(m);
      });
      log.appendChild(wrap); scroll();
    }
    var busyNow = false;
    function lock(on) { busyNow = on; send.disabled = on; ta.disabled = on; }

    function askAI(text, brief) {
      lock(true);
      var wait = bubble("ai", "Thinking…");
      api("POST", "/api/chat", { message: text, thread: chatThread, brief: brief || undefined }).then(function (r) {
        lock(false);
        if (r.b.ok) { chatThread = r.b.thread; wait.textContent = r.b.reply; setCredits(r.b.credits); refreshFoot(); cards(r.b.cards); }
        else { wait.className = "pt-msg-b pt-msg-b--err"; wait.textContent = r.s === 429 ? "You're sending messages too fast. Wait a moment." : (r.b.message || "That didn't work. You weren't charged."); }
        ta.focus();
      });
    }

    function ask(text) {
      text = (text || "").trim();
      if (!text || busyNow) return;
      var ideas = log.querySelector(".pt-ideas"); if (ideas) ideas.remove();
      bubble("me", text); ta.value = "";
      if (!chatBrief && REQUEST.test(text)) guided(text); else askAI(text);
    }

    /* The free questions, asked inside the chat. */
    function guided(text) {
      lock(true);
      Promise.all([loadQuestions(), api("POST", "/api/brief/guess", { text: text })]).then(function (res) {
        lock(false);
        var qs = res[0], answers = Object.assign(profileAnswers(), (res[1].b && res[1].b.answers) || {});
        var byId = {}; qs.forEach(function (q) { byId[q.id] = q; });
        var todo = FLOW.filter(function (id) { return byId[id] && !(answers[id] && answers[id].length); });
        var known = FLOW.filter(function (id) { return answers[id] && answers[id].length; });
        bubble("ai", (known.length ? "Got it. " : "") + "To find the right creators I need " + (todo.length ? todo.length + " quick detail" + (todo.length === 1 ? "" : "s") : "nothing more") +
          ". Tap to answer — this part is free.");
        var i = 0;
        function next() {
          if (i >= todo.length) return summary();
          var q = byId[todo[i]], many = q.type === "many";
          var card = h("div", { class: "pt-msg-b pt-msg-b--ai", style: "white-space:normal;max-width:100%" });
          card.appendChild(h("p", { style: "margin:0 0 10px;font-weight:600" }, q.label));
          var opts = h("div", { class: "pt-ideas" });
          var picked = [];
          q.options.forEach(function (o) {
            var b = h("button", { class: "pt-idea", type: "button", "aria-pressed": "false" }, o.label);
            b.addEventListener("click", function () {
              if (!many) { answers[q.id] = o.value; done(o.label); return; }
              var k = picked.indexOf(o.value);
              if (o.value === "any") picked = k > -1 ? [] : ["any"];
              else { picked = picked.filter(function (v) { return v !== "any"; }); if (k > -1) picked.splice(picked.indexOf(o.value), 1); else picked.push(o.value); }
              Array.prototype.forEach.call(opts.children, function (x, xi) {
                if (!q.options[xi]) return;
                var on = picked.indexOf(q.options[xi].value) > -1;
                x.setAttribute("aria-pressed", on ? "true" : "false");
                x.style.background = on ? "var(--lime)" : ""; x.style.borderColor = on ? "var(--ink)" : "";
              });
            });
            opts.appendChild(b);
          });
          card.appendChild(opts);
          var row = h("div", { style: "margin-top:10px;display:flex;gap:8px" });
          if (q.other) {
            // "Other": the client types an answer the options don't list.
            var oIn = otherInput(q, "", function (txt) {
              if (many) picked = withOther(q, picked, txt) || [];
            }, function () { (many ? row.firstChild : oSend).click(); });
            oIn.hidden = true;
            var oSend = h("button", { class: "pt-idea", type: "button", hidden: true, style: "background:var(--ink);color:var(--white)", onclick: function () {
              var nv = withOther(q, null, oIn.value); if (!nv) return; answers[q.id] = nv; done(optionLabel(q, nv));
            } }, "Send");
            opts.appendChild(h("button", { class: "pt-idea", type: "button", onclick: function () {
              oIn.hidden = false; if (!many) oSend.hidden = false; oIn.focus();
            } }, "Other"));
            card.appendChild(oIn);
          }
          if (many) row.appendChild(h("button", { class: "pt-idea", type: "button", style: "background:var(--ink);color:var(--white)", onclick: function () {
            if (!picked.length) return; answers[q.id] = picked.slice(); done(picked.map(function (v) { return optionLabel(q, v); }).join(", "));
          } }, "Next"));
          if (oSend) row.appendChild(oSend);
          if (!q.required) row.appendChild(h("button", { class: "pt-idea", type: "button", onclick: function () { done("Skip"); } }, "Skip"));
          if (row.children.length) card.appendChild(row);
          log.appendChild(card); scroll();
          function done(label) { card.remove(); bubble("me", label); i += 1; next(); }
        }
        function summary() {
          chatBrief = answers;
          var lines = FLOW.filter(function (id) { return byId[id] && answers[id] && answers[id].length; }).map(function (id) {
            var v = answers[id]; return (SHORT[id] || byId[id].label.replace(/\?$/, "")) + ": " + (Array.isArray(v) ? v : [v]).map(function (x) { return optionLabel(byId[id], x); }).join(", ");
          });
          var card = h("div", { class: "pt-msg-b pt-msg-b--ai", style: "white-space:normal;max-width:100%" },
            h("p", { style: "margin:0 0 8px;font-weight:600" }, "Your brief"), h("p", { style: "margin:0 0 12px;white-space:pre-line" }, lines.join("\n")));
          var costs = (ME && ME.costs) || { brief: 5, chat: 1 };
          var freeBuild = !costs.search && ME && ME.credits != null && ME.credits < costs.brief;
          // Credit amounts wear the orange coin chip (.hv-cost), the one look for credits everywhere.
          var build = h("button", { class: "pt-idea", type: "button", style: "background:var(--lime);border-color:var(--ink);font-weight:600" }, "Build my shortlist ",
            freeBuild ? h("span", { class: "hv-cost hv-cost--free" }, "Free")
                      : h("span", { class: "hv-cost", html: icon("coin") + costs.brief + " credits" }), !freeBuild && !costs.search ? " (free without reasons)" : null);
          var talk = h("button", { class: "pt-idea", type: "button" }, "Ask the assistant ",
            h("span", { class: "hv-cost", html: icon("coin") + costs.chat + " credit" + (costs.chat === 1 ? "" : "s") }));
          var redo = h("button", { class: "pt-idea", type: "button" }, "Change answers");
          card.appendChild(h("div", { class: "pt-ideas" }, build, talk, redo));
          log.appendChild(card); scroll();
          build.addEventListener("click", function () {
            card.remove(); bubble("me", "Build my shortlist");
            lock(true);
            var wait = bubble("ai", "Matching creators…");
            api("POST", "/api/brief/run", { answers: answers, name: "Chat shortlist" }).then(function (r) {
              lock(false);
              if (!r.b.ok || r.b.empty) { wait.className = "pt-msg-b pt-msg-b--err"; wait.textContent = r.b.message || "That didn't work. You weren't charged."; return; }
              setCredits(r.b.credits); refreshFoot(); rememberBrief(r.b.brief_id);
              wait.textContent = (r.b.summary || (r.b.picks.length + " creators match your brief, best fit first.")) + " Scores are out of 100.";
              cards(r.b.picks.map(function (p) { var c = Object.assign({ code: p.code, name: p.code }, p.creator || {}); c.fit = p.score; return c; }));
              var a = h("a", { class: "pt-idea", href: ROOT + "selection/#s=" + encodeURIComponent(r.b.token), style: "text-decoration:none;background:var(--ink);color:var(--white)" }, "Open as selection");
              a.addEventListener("click", function (e) {
                e.preventDefault(); a.parentNode.remove();
                var current = r.b.name || "Chat shortlist";
                log.appendChild(h("div", { class: "pt-msg-b pt-msg-b--ai", style: "white-space:normal;max-width:100%" },
                  nameForm(current, "Save and open", function (v) { renameThenOpen(r.b.token, codesOf(r.b.picks), current, v); })));
                scroll();
              });
              log.appendChild(h("div", { class: "pt-ideas" }, a)); scroll();
            });
          });
          talk.addEventListener("click", function () { card.remove(); askAI(text, answers); });
          redo.addEventListener("click", function () { card.remove(); chatBrief = null; answers = {}; guided(text); });
        }
        next();
      });
    }

    send.addEventListener("click", function () { ask(ta.value); });
    ta.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(ta.value); } });

    bubble("ai", "Hi" + (ME && ME.user ? " " + ME.user.name.split(" ")[0] : "") + ". Tell me what you're planning and I'll ask a few quick questions (free), then build a scored shortlist or answer anything about how we work.");
    var ideas = h("div", { class: "pt-ideas" });
    IDEAS.forEach(function (i) { ideas.appendChild(h("button", { class: "pt-idea", type: "button", onclick: function () { ask(i); } }, i)); });
    log.appendChild(ideas);
    if (chatThread) {
      api("GET", "/api/chat/history?t=" + chatThread).then(function (r) {
        (r.b.messages || []).forEach(function (m) { bubble(m.role === "user" ? "me" : "ai", m.text); });
      });
    }
    close = layer(drawer, true);
    ta.focus();
  }

  /* --------------------------------------------------------------- account */

  function openAccount() {
    var modal = h("div", { class: "pt-modal", role: "dialog", "aria-modal": "true", "aria-labelledby": "pt-acc-title" });
    var close;
    var u = ME && ME.user;
    modal.appendChild(h("div", { class: "pt-head" }, h("h2", { class: "pt-title", id: "pt-acc-title" }, u ? u.name : ME.kind === "admin" ? "Admin preview" : "Guest access"),
      h("button", { class: "pt-x", type: "button", "aria-label": "Close", onclick: function () { close(); } }, "×")));
    var body = h("div", { class: "pt-body" });
    modal.appendChild(body);
    if (u) body.appendChild(h("p", { class: "pt-sub" }, [u.company, u.email].filter(Boolean).join(" · ")));
    else body.appendChild(h("p", { class: "pt-sub" }, ME.kind === "admin" ? "You're viewing as an administrator. AI is free for you." : "You're using an access code. Sign in with your work email for your own profile, campaigns and credits."));

    if (ME.credits != null) {
      var bal = h("div", { class: "pt-sec" }, h("h3", null, "AI credits"),
        h("div", { class: "pt-balance" }, h("b", { id: "pt-bal", class: "hv-credit-num" }, String(ME.credits)), h("span", { class: "pt-sub", style: "margin:0" }, "credits left")),
        h("p", { class: "pt-sub" }, LANG === "ar" ? "القائمة مع الأسباب تكلف " + ME.costs.brief + "، والرسالة " + ME.costs.chat + ". أسئلة الملخص مجانية."
          : "A shortlist with written reasons costs " + ME.costs.brief + ", a chat message " + ME.costs.chat + ". Brief questions are free."));
      var ask = h("div", { class: "pt-actions", style: "margin-top:10px;justify-content:flex-start" });
      var amt = h("select", { class: "pt-field", style: "width:auto", "aria-label": "Credits" });
      [50, 200, 500].forEach(function (n) { amt.appendChild(h("option", { value: String(n) }, "+" + n)); });
      var note = h("input", { class: "pt-field", style: "flex:1;min-width:160px", placeholder: LANG === "ar" ? "ملاحظة (اختياري)" : "Note (optional)" });
      var reqBtn = h("button", { class: "pt-btn pt-btn--ghost", type: "button" }, "Request more credits");
      var reqMsg = h("span", { class: "pt-note", style: "margin:0" });
      reqBtn.addEventListener("click", function () {
        reqBtn.disabled = true;
        api("POST", "/api/credits/request", { amount: +amt.value, note: note.value }).then(function (r) {
          reqMsg.textContent = r.s === 429 ? (LANG === "ar" ? "أرسلت طلبات كافية اليوم." : "You've sent enough requests today.") : T(r.b.message || "");
        });
      });
      ask.appendChild(amt); ask.appendChild(note); ask.appendChild(reqBtn);
      bal.appendChild(ask); bal.appendChild(reqMsg);
      var led = h("table", { class: "pt-ledger" });
      bal.appendChild(led);
      body.appendChild(bal);
      api("GET", "/api/credits").then(function (r) {
        if (!r.b.ok) return;
        $("pt-bal").textContent = r.b.balance; setCredits(r.b.balance);
        r.b.ledger.slice(0, 8).forEach(function (l) { led.appendChild(h("tr", null, h("td", null, l.reason + " · " + ago(l.at)), h("td", null, (l.delta > 0 ? "+" : "") + l.delta))); });
      });
    }

    var briefs = h("div", { class: "pt-sec" }, h("h3", null, "My briefs"));
    var bl = h("ul", { class: "pt-brieflist" });
    briefs.appendChild(bl); body.appendChild(briefs);
    api("GET", "/api/briefs").then(function (r) {
      var list = r.b.briefs || [];
      if (!list.length) { bl.appendChild(h("li", null, h("span", { class: "pt-sub", style: "margin:0" }, "None yet. Use Find creators to start one."))); return; }
      list.slice(0, 8).forEach(function (b) {
        bl.appendChild(h("li", null, h("span", null, b.summary + " · " + ago(b.at)), b.selection ? h("a", { href: ROOT + "selection/#s=" + encodeURIComponent(b.selection) }, "Open") : null));
      });
    });

    if (u) {
      var team = h("div", { class: "pt-sec" }, h("h3", null, "My team"));
      var tl = h("ul", { class: "pt-brieflist" });
      team.appendChild(tl); body.appendChild(team);
      api("GET", "/api/team").then(function (r) {
        var members = r.b.members || [], sels = r.b.selections || [];
        if (!members.length) { tl.appendChild(h("li", null, h("span", { class: "pt-sub", style: "margin:0" },
          LANG === "ar" ? "عندما ينضم زملاء من شركتك سترى قوائمهم هنا." : "When colleagues from your company join, their selections appear here."))); return; }
        tl.appendChild(h("li", null, h("span", null, members.map(function (m) { return m.name + (m.job_title ? " (" + m.job_title + ")" : ""); }).join(", "))));
        sels.slice(0, 8).forEach(function (x) {
          tl.appendChild(h("li", null, h("span", null, x.name + " · " + x.owner + " · " + ago(x.at)), h("a", { href: ROOT + "selection/#s=" + encodeURIComponent(x.token) }, "Open")));
        });
      });
    }

    body.appendChild(h("div", { class: "pt-sec" }, h("h3", null, "My campaigns"),
      h("p", { class: "pt-sub", style: "margin:0" }, h("a", { href: ROOT + "campaign/dashboard/" }, "Open campaign tracking"), " to see results for the campaigns we run for you.")));

    if (u) {
      var f = {}; var form = h("form", { class: "pt-sec" }, h("h3", null, "My details"));
      [["name", "Name"], ["company", "Company"], ["job_title", "Job title"], ["phone", "Phone"]].forEach(function (pair) {
        f[pair[0]] = h("input", { class: "pt-field", name: pair[0], value: u[pair[0]] || "", autocomplete: "off" });
        form.appendChild(h("div", { style: "margin-bottom:12px" }, h("label", { class: "pt-label" }, pair[1]), f[pair[0]]));
      });
      var saved = h("span", { class: "pt-note", style: "margin:0" });
      form.appendChild(h("div", { class: "pt-actions", style: "margin-top:4px" }, saved, h("button", { class: "pt-btn pt-btn--ghost", type: "submit" }, "Save")));
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        api("POST", "/api/me/update", { name: f.name.value, company: f.company.value, job_title: f.job_title.value, phone: f.phone.value }).then(function (r) {
          saved.textContent = r.b.ok ? "Saved" : "Couldn't save";
          if (r.b.ok) { ME.user = r.b.user; var n = $("pt-chip-name"); if (n) n.textContent = r.b.user.name.trim().split(/\s+/).slice(0, 2).map(function (w) { return w.charAt(0); }).join("").toUpperCase(); }
        });
      });
      body.appendChild(form);
    }

    var extra = h("span");
    if (u) {
      extra.appendChild(h("button", { class: "pt-link", type: "button", style: "color:var(--ink)", onclick: function () {
        fetch(API + "/api/me/export", { credentials: "include" }).then(function (r) { return r.blob(); }).then(function (b) {
          var a = h("a", { href: URL.createObjectURL(b), download: "my-hellovoice-data.json" }); document.body.appendChild(a); a.click(); a.remove();
        });
      } }, "Download my data"));
      extra.appendChild(document.createTextNode(" · "));
      extra.appendChild(h("button", { class: "pt-link", type: "button", style: "color:var(--red-text)", onclick: function () {
        var typed = window.prompt(LANG === "ar" ? "سيُحذف حسابك وبياناتك الشخصية نهائياً. اكتب DELETE للتأكيد." : "Your account and personal data will be erased. Type DELETE to confirm.");
        if (typed !== "DELETE") return;
        api("POST", "/api/me/delete", { confirm: "DELETE" }).then(function () { location.reload(); });
      } }, "Delete my account"));
    }
    body.appendChild(h("div", { class: "pt-actions" }, extra, h("button", { class: "pt-btn pt-btn--ghost", type: "button", onclick: function () {
      (function () { try { sessionStorage.removeItem("hv-roster"); } catch (e) { /* blocked */ } })(), api("POST", "/api/auth/logout", {}).then(function () { location.reload(); });
    } }, "Sign out")));
    close = layer(modal);
  }

  /* ----------------------------------------------------------------- voice */
  // "Voice": the HelloVoice character in the bottom-right corner. Opens a chat
  // that greets the client, then routes them through tap-to-answer flows that
  // get things done (find creators, filter the page, edit a selection, quote,
  // talk to a person). Typing goes to the AI assistant (credits, as in "Ask").
  // Every write is a button the client presses; the AI itself only answers.

  var VOICE_PAGES = { catalogue: 1, selection: 1, creator: 1, account: 1, campaign: 1 };
  var V_ICON = {
    send: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h13M13 6l6 6-6 6"/></svg>',
    close: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    minimize: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 13h12"/></svg>',
    fresh: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 4v4h4"/></svg>',
    grow: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/></svg>',
    shrink: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 14h6v6M20 10h-6V4M14 10l7-7M10 14l-7 7"/></svg>',
    mic: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
    check: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    plus: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>'
  };

  function mountVoice() {
    var page = document.body.getAttribute("data-page");
    if (!VOICE_PAGES[page] || $("hv-voice")) return;
    // Inside the profile-analysis side panel (an iframe of the creator page) the page around it already has the assistant.
    // The onboarding tour plays this page in a demo frame (tour.js): there the chat runs, on demo answers.
    if ((window.self !== window.top && !window.hvDemo) || /[?&]embed=1\b/.test(location.search)) return;
    var first = ME && ME.user ? ME.user.name.split(" ")[0] : "";
    // One conversation per access (signed-in client or access code), carried across pages for a week.
    var STORE = "hv-chat:" + ((ME && ME.chat_key) || (ME && ME.user ? ME.user.email : ME && ME.kind) || "guest");
    var KEEP_MS = 7 * 24 * 3600 * 1000;
    // On a selection's page the assistant works on that selection: its brief, its scores.
    // What is on screen, sent with each question so the assistant knows where the client is.
    function pageCtx() {
      var out = { page: page };
      var m;
      if (page === "creator" && (m = /(?:^|[#&])c=([A-Za-z0-9-]+)/.exec(location.hash || ""))) out.creator = decodeURIComponent(m[1]).toUpperCase();
      if (page === "campaign" && (m = /(?:^|[#&])t=([A-Za-z0-9_-]+)/.exec(location.hash || ""))) out.campaign = m[1];
      if (page === "catalogue") {
        var bar = document.querySelector(".cat-bar");
        if (bar) out.filters = Array.prototype.map.call(bar.querySelectorAll("input[data-dim]:checked"), function (box) {
          var l = box.closest("label"); return ((l && l.textContent) || box.value).replace(/\s+/g, " ").trim().slice(0, 40);
        }).filter(Boolean).slice(0, 15);
        if ((window.hvCatalogue && window.hvCatalogue.server)) { if (window.hvCatalogue.matched() != null) out.shown = window.hvCatalogue.matched(); }   // only while filtered
        else out.shown = Array.prototype.filter.call(document.querySelectorAll(".cat-card"), function (c) { return !c.hidden && !c.classList.contains("cat-card--copy"); }).length;
      }
      return out;
    }
    function selToken() { var m = page === "selection" && /(?:^|[#&])s=([A-Za-z0-9_-]+)/.exec(location.hash || ""); return m ? m[1] : ""; }
    var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

    /* -- launcher -- */
    var root = h("div", { id: "hv-voice", class: "hv-voice" });
    var launch = h("button", { class: "hv-launch cx-launch", type: "button", "aria-label": "Chat with Helvy, your AI assistant", "aria-expanded": "false", "aria-controls": "hv-panel" });
    // Helvy rises out of an ink disc: the transparent idle loop, cut at the disc's curve.
    // Reduced motion, or a browser that refuses autoplay, gets the transparent still instead.
    launch.innerHTML = '<span class="hv-launch__disc" aria-hidden="true"></span>' +
      '<span class="hv-launch__x" aria-hidden="true">' + V_ICON.close + "</span>" +
      '<span class="hv-launch__dot" aria-hidden="true" hidden></span>';
    var face = HVH && !reduce ? HVH.video("idle", { cls: "hv-launch__vid" }) : h("img", { class: "hv-launch__vid hv-clip--still", src: HVH ? HVH.still : HV.helvy, alt: "", decoding: "async" });
    launch.insertBefore(face, launch.children[1]);
    var nudge = h("div", { class: "hv-nudge", role: "status", hidden: "" });
    nudge.innerHTML = "<span><b>Need a hand?</b>Ask me to shortlist creators or check what your budget can reach.</span>";
    var nudgeX = h("button", { class: "hv-nudge__x", type: "button", "aria-label": "Dismiss" });
    nudgeX.innerHTML = V_ICON.close;
    nudge.appendChild(nudgeX);

    /* -- panel -- */
    var panel = h("section", { id: "hv-panel", class: "hv-panel", role: "dialog", "aria-modal": "false", "aria-labelledby": "hv-name", hidden: "" });
    var head = h("header", { class: "hv-head" });
    head.classList.add("cx-chathead");
    // Helvy in the header: idle at rest; while he works on an answer (thinking, then the words
    // streaming in) he sits at his desk (thinking -> cards -> approve) so he never reads as a still.
    var headHelvy = clip("idle", "hv-head__helvy");
    head.appendChild(headHelvy);
    function headWorking(on) {
      if (!!on === !!headHelvy._busy) return;
      var nx = on ? clip("thinking", "hv-head__helvy", { seq: COOK_SEQ }) : clip("idle", "hv-head__helvy");
      nx._busy = !!on;
      if (headHelvy.parentNode) headHelvy.parentNode.replaceChild(nx, headHelvy);
      headHelvy = nx;
      var v = nx.querySelector("video"); if (v && HVH) HVH.play(v);
    }
    head.insertAdjacentHTML("beforeend", '<div class="hv-head__id"><h2 class="hv-head__name" id="hv-name">Helvy</h2>' +
      '<p class="hv-head__role"><span class="hv-head__on"><i aria-hidden="true"></i>Your AI assistant · online</span></p></div>');
    var freshBtn = h("button", { class: "hv-head__btn", type: "button", "aria-label": "Start a new chat", title: "New chat" });
    freshBtn.innerHTML = V_ICON.fresh;
    var closeBtn = h("button", { class: "hv-head__btn", type: "button", "aria-label": "Close chat", title: "Close" });
    closeBtn.innerHTML = V_ICON.close;
    var growBtn = h("button", { class: "hv-head__btn hv-head__grow", type: "button", "aria-label": "Make the chat bigger", "aria-pressed": "false", title: "Bigger" });
    growBtn.innerHTML = V_ICON.grow;
    // Minimize folds the chat down to its round launcher; the conversation stays.
    var minBtn = h("button", { class: "hv-head__btn", type: "button", "aria-label": "Minimize chat", title: "Minimize" });
    minBtn.innerHTML = V_ICON.minimize;
    head.appendChild(h("div", { class: "hv-head__tools" }, growBtn, freshBtn, minBtn, closeBtn));
    var log = h("div", { class: "hv-log", role: "log", "aria-live": "polite", "aria-relevant": "additions" });
    var ta = h("textarea", { class: "hv-input", rows: "1", maxlength: "800", placeholder: "Type a message…", "aria-label": "Message Helvy" });
    var send = h("button", { class: "hv-send", type: "button", "aria-label": "Send" });
    send.innerHTML = V_ICON.send;
    // Voice (phase E): the browser's own speech-to-text, Arabic (Saudi) or English. Nothing is
    // recorded or uploaded by HelloVoice; the words become a normal typed message and Helvy
    // answers in text. Browsers without speech recognition get no mic, just a tooltip.
    var Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
    var VLANG = { "ar-SA": ["ع", "Arabic (Saudi)"], "en-US": ["EN", "English"] };
    var vlang = "en-US";
    try { vlang = localStorage.getItem("hv-voice-lang") || (/^ar/i.test(navigator.language || "") ? "ar-SA" : "en-US"); } catch (e) { /* private */ }
    if (!VLANG[vlang]) vlang = "en-US";
    var mic = Speech ? h("button", { class: "hv-mic", type: "button", "aria-label": "Speak your message", "aria-pressed": "false", title: "Speak to Helvy" }) : null;
    if (mic) mic.innerHTML = V_ICON.mic;
    var langBtn = Speech ? h("button", { class: "hv-vlang", type: "button", title: "Voice language" }) : null;
    function paintLang() {
      if (!langBtn) return;
      langBtn.textContent = VLANG[vlang][0];
      langBtn.setAttribute("lang", vlang.slice(0, 2));
      langBtn.setAttribute("aria-label", "Voice language: " + VLANG[vlang][1] + ". Switch to " + VLANG[vlang === "ar-SA" ? "en-US" : "ar-SA"][1]);
    }
    paintLang();
    if (!Speech) ta.title = "Voice messages work in Chrome, Edge and Safari";
    var heard = h("div", { class: "hv-heard", role: "status", "aria-live": "polite", hidden: "" });
    var compose = h("div", { class: "hv-compose" + (Speech ? " hv-compose--voice" : "") }, ta, langBtn || document.createTextNode(""), mic || document.createTextNode(""), send);
    // Creators added from the chat's cards, waiting to be saved as a selection.
    var picksBar = h("div", { class: "hv-picks", hidden: "" });
    var foot = h("p", { class: "hv-foot" });
    panel.appendChild(head); panel.appendChild(log); panel.appendChild(picksBar); panel.appendChild(heard); panel.appendChild(compose);
    root.appendChild(panel); root.appendChild(nudge); root.appendChild(launch);
    document.body.appendChild(root);
    document.body.classList.add("has-voice");

    function refreshFoot() {
      foot.textContent = ME && ME.ai
        ? "Tapping options is free · typed questions use 1 credit" + (ME.credits != null ? " · " + ME.credits + " left" : "")
        : "Tap an option, or ask for your account manager.";
    }
    refreshFoot();

    // Keep clear of the selection tray when it is open.
    var tray = $("cat-tray");
    function lift() {
      var hgt = tray && !tray.hidden ? tray.getBoundingClientRect().height : 0;
      document.body.style.setProperty("--hv-lift", Math.ceil(hgt) + "px");
    }
    if (tray && window.MutationObserver) new MutationObserver(lift).observe(tray, { attributes: true, childList: true, subtree: true });
    window.addEventListener("resize", lift);
    lift();

    /* -- transcript -- */
    var msgs = [], kept = null;
    try { kept = JSON.parse(localStorage.getItem(STORE) || "null"); } catch (e) { kept = null; }
    if (kept && kept.at && Date.now() - kept.at < KEEP_MS && Array.isArray(kept.msgs)) msgs = kept.msgs; else kept = null;
    function save() {
      try { localStorage.setItem(STORE, JSON.stringify({ at: Date.now(), thread: thread, msgs: msgs.slice(-60) })); } catch (e) { /* private */ }
    }
    function scroll() { log.scrollTop = log.scrollHeight; }
    function row(kind, node) {
      var r = h("div", { class: "hv-row hv-row--" + kind });
      if (kind === "ai") { var ava = h("span", { class: "hv-row__ava cx-ava", "aria-hidden": "true" }); bg(ava, HV.helvy); r.appendChild(ava); }
      r.appendChild(node); log.appendChild(r); scroll(); return r;
    }
    // The AI writes light markdown: **bold** and "* " bullets. Rendered as text nodes, never as HTML.
    function rich(text) {
      var box = document.createDocumentFragment();
      String(text).replace(/^\s*[*-]\s+/gm, "• ").split(/(\*\*[^*]+\*\*)/).forEach(function (part) {
        var m = /^\*\*([^*]+)\*\*$/.exec(part);
        box.appendChild(m ? h("b", null, m[1]) : document.createTextNode(part));
      });
      return box;
    }
    function bubble(kind, text, keep) {
      var b = h("div", { class: "hv-msg hv-msg--" + kind });
      b.appendChild(kind === "ai" ? rich(text) : document.createTextNode(text));
      row(kind, b);
      if (keep !== false) { msgs.push({ from: kind, text: text }); save(); }
      if (kind === "ai" && panel.hidden) launch.querySelector(".hv-launch__dot").hidden = false;
      return b;
    }
    // Text that types itself out: a steady pace that speeds up when a long answer is waiting,
    // so it reads like typing and never falls far behind the stream. Instant under reduced motion.
    function typer(node) {
      var target = "", shown = 0, raf = 0, last = 0, ended = false, after = null;
      node.classList.add("is-live");
      function visible(txt) {                   // never show half of a **bold** marker
        var n = (txt.match(/\*\*/g) || []).length;
        return n % 2 ? txt.slice(0, txt.lastIndexOf("**")) : txt;
      }
      function paint() { node.textContent = ""; node.appendChild(rich(visible(target.slice(0, shown)))); scroll(); }
      function finish() { node.classList.remove("is-live"); var f = after; after = null; if (f) f(); }
      function frame(t) {
        var dt = last ? Math.min(64, t - last) : 16; last = t;
        var backlog = target.length - shown;
        shown = Math.min(target.length, shown + Math.max(1, Math.round((0.05 + backlog * 0.0007) * dt)));
        paint();
        if (shown < target.length) { raf = tick(frame); return; }
        raf = 0; last = 0;
        if (ended) finish();
      }
      // Animation frames stop while the tab is in the background; a timer keeps the text coming,
      // so an answer never stalls (and nothing queued behind it waits) when the client looks away.
      function tick(fn) { return document.hidden ? setTimeout(function () { fn(performance.now()); }, 50) : requestAnimationFrame(fn); }
      function kick() { if (reduce) { shown = target.length; paint(); if (ended) finish(); return; } if (!raf) raf = tick(frame); }
      return {
        push: function (more) { target += more; kick(); },
        end: function (full, then) {
          if (typeof full === "string" && full.length >= target.length) target = full;
          ended = true; after = then || null; kick();
        }
      };
    }
    // The assistant's own messages: a short "typing" pause, then the words type out.
    var queue = Promise.resolve();
    function say(text, then) {
      queue = queue.then(function () {
        return new Promise(function (done) {
          var dots = row("ai", h("div", { class: "hv-msg hv-msg--ai hv-typing", "aria-label": "Helvy is typing" }, h("i"), h("i"), h("i")));
          setTimeout(function () {
            dots.remove();
            var b = bubble("ai", text); b.textContent = "";
            typer(b).end(text, function () { if (then) then(); done(); });
          }, reduce ? 0 : Math.min(500, 200 + text.length * 3));
        });
      });
      return queue;
    }
    function chips(list, opts) {
      opts = opts || {};
      queue = queue.then(function () {
        // Options arrive one by one (60 ms apart); reduced motion shows them at once.
        var wrap = h("div", { class: "hv-chips" + (opts.stack ? " hv-chips--stack" : "") + (REDUCE ? "" : " cx-stagger") });
        var many = list.some(function (c) { return c.toggle; });
        wrap.appendChild(h("p", { class: "hv-chips__hint" }, opts.hint || (many ? "Pick any, then confirm" : "Tap to choose")));
        list.forEach(function (c) {
          var b = h("button", { class: "hv-chip" + (c.primary ? " hv-chip--lime" : "") + (c.ghost ? " hv-chip--ghost" : ""), type: "button" }, c.label);
          if (c.pressed != null) b.setAttribute("aria-pressed", String(!!c.pressed));
          b.style.setProperty("--i", String(wrap.querySelectorAll(".hv-chip").length));
          b.addEventListener("click", function () {
            if (c.toggle) { c.toggle(b); return; }
            if (!opts.keep) wrap.remove();
            if (c.echo !== false) bubble("me", c.label);
            c.go();
          });
          wrap.appendChild(b);
        });
        log.appendChild(wrap); scroll();
      });
      return queue;
    }
    var expecting = null;               // a function waiting for the next typed message
    function askFor(text, placeholder, fn) {
      say(text, function () { ta.placeholder = placeholder || "Type here…"; expecting = fn; ta.focus(); });
    }

    /* -- a brief question: options fill the message box; the client sends --
       Tapping an option writes its label into the box (tap again to take it
       out), several can be combined, and the client can add their own words.
       Nothing moves on until they press Send. */
    function question(q, idx, total, how) {
      queue = queue.then(function () {
        var many = q.type === "many";
        var card = h("div", { class: "hv-msg hv-msg--ai hv-q", role: "group", "aria-label": q.label });
        card.appendChild(h("p", { class: "hv-q__count" }, "Question " + (idx + 1) + " of " + total));
        card.appendChild(h("p", { class: "hv-q__label" }, q.label));
        var grid = h("div", { class: "hv-q__opts" });
        // Read the box: which options it names (whole labels, which may hold commas) and the client's own words.
        var byLen = q.options.slice().sort(function (a, b) { return b.label.length - a.label.length; });
        function read(text) {
          var rest = " " + text + " ", hit = [];
          byLen.forEach(function (o) {
            var k = rest.toLowerCase().indexOf(o.label.toLowerCase());
            if (k > -1) { hit.push(o); rest = rest.slice(0, k) + " " + rest.slice(k + o.label.length); }
          });
          hit.sort(function (a, b) { return text.toLowerCase().indexOf(a.label.toLowerCase()) - text.toLowerCase().indexOf(b.label.toLowerCase()); });
          return { opts: hit, own: rest.replace(/^[\s;,،+·-]+|[\s;,،+·-]+$/g, "").replace(/\s*[;،]\s*[;،]+\s*/g, "; ").replace(/\s{2,}/g, " ") };
        }
        function sync() {
          var on = read(ta.value).opts.map(function (o) { return o.label; });
          grid.querySelectorAll(".hv-opt").forEach(function (b) { b.setAttribute("aria-pressed", String(on.indexOf(b.dataset.label) > -1)); });
        }
        q.options.forEach(function (o) {
          var b = h("button", { class: "hv-opt", type: "button", "aria-pressed": "false", "data-label": o.label },
            h("span", { class: "hv-opt__tick", "aria-hidden": "true" }), h("span", null, o.label));
          b.querySelector(".hv-opt__tick").innerHTML = V_ICON.check;
          b.addEventListener("click", function () {
            var now = read(ta.value), mine = now.opts.map(function (x) { return x.label; });
            if (mine.indexOf(o.label) > -1) mine = mine.filter(function (x) { return x !== o.label; });
            else mine = many ? mine.concat([o.label]) : [o.label];
            ta.value = mine.concat(now.own ? [now.own] : []).join("; ");
            grow(); sync();
            if (window.matchMedia && !matchMedia("(pointer: coarse)").matches) ta.focus();
          });
          grid.appendChild(b);
        });
        card.appendChild(grid);
        var foot = h("div", { class: "hv-q__foot" },
          h("span", { class: "hv-q__hint" }, many ? "Pick one or more, add your own words, then Send" : "Pick one or type your answer, then Send"));
        if (how.back) foot.appendChild(h("button", { class: "hv-q__link", type: "button", onclick: function () { finish(); bubble("me", "Back", false); how.back(); } }, "Back"));
        if (how.skip) foot.appendChild(h("button", { class: "hv-q__link", type: "button", onclick: function () { finish(); bubble("me", "Skip"); how.skip(); } }, "Skip"));
        card.appendChild(foot);
        row("ai", card);
        ta.placeholder = "Tap above or type your answer";
        ta.addEventListener("input", sync);
        function finish() {
          card.classList.add("is-done");
          grid.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
          foot.remove(); ta.removeEventListener("input", sync);
          expecting = null; ta.placeholder = "Type a message…";
        }
        expecting = function (text) {
          var got = read(text), vals = got.opts.map(function (o) { return o.value; }), own = got.own ? [got.own] : [];
          if (!many && vals.length > 1) vals = vals.slice(-1);
          card.classList.add("is-done");
          grid.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
          foot.remove(); ta.removeEventListener("input", sync); ta.placeholder = "Type a message…";
          how.done(vals, own.join(", "));
        };
      });
      return queue;
    }

    /* -- the menu -- */
    function menu(lead) {
      if (lead) say(lead);
      var list = selToken()
        ? [{ label: "About this selection", go: aboutSelection }, { label: "Find more creators", go: flowFind }]
        : [{ label: "Find creators for a campaign", go: flowFind }];
      if (document.querySelector(".cat-bar")) list.push({ label: "Show creators on this page", go: flowShow });
      list.push({ label: "Work on my selection", go: flowSelection },
                { label: "What can my budget reach?", go: flowBudget },
                { label: "Get a quote", go: flowQuote },
                { label: "Talk to my account manager", go: flowHuman },
                { label: "Just browsing", ghost: true, go: function () { say("Sure. I'll be right here in the corner whenever you need me."); } });
      chips(list, { stack: true });
    }
    // After every answer: the likely next requests as options, with the box below still open for typing.
    function nextUp(lead) {
      if (lead) say(lead);
      var list = [{ label: "Find creators", go: flowFind }];
      if (document.querySelector(".cat-bar")) list.push({ label: "Filter this page", go: flowShow });
      list.push({ label: "My selection", go: flowSelection }, { label: "Get a quote", go: flowQuote },
                { label: "Talk to a person", go: flowHuman });
      chips(list, { hint: "Tap to choose · or type below" });
    }
    // "What can my budget reach?": the client's own budget, answered with the ROI card (free).
    function flowBudget() {
      askFor("What's your budget in SAR, and what matters most: reach, engagement or clicks?", "e.g. 80,000 for reach on Instagram", function (text) {
        var n = /(\d[\d,.]*)\s*(k|m|thousand|million|ألف)?/i.exec(text);
        if (!n) { say("I need a number, like 80,000."); flowBudget(); return; }
        submit("What can SAR " + n[1] + (n[2] ? n[2] : "") + " reach " + text.replace(n[0], "").trim(), true);
      });
    }
    function greet() {
      say("Hi" + (first ? " " + first : "") + ", I'm Helvy 👋");
      if (selToken()) { aboutSelection(); return; }
      menu("How can I help you?");
    }
    // The selection on this page: its brief if one was recorded, else an offer to score it.
    function aboutSelection() {
      api("GET", "/api/voice/selection?s=" + encodeURIComponent(selToken())).then(function (r) {
        var x = r.b;
        if (!x || !x.ok) { menu("How can I help you?"); return; }
        if (x.brief) {
          say("This is “" + x.name + "” (" + x.count + " creator" + (x.count === 1 ? "" : "s") + "). Its brief is on file:\n" +
              x.brief.answers.map(function (a) { return "• " + a.q.replace(/\?$/, "") + ": **" + a.a + "**"; }).join("\n"));
          if (x.scores && x.scores.length) say("Everyone is scored against it. Best fit: " + x.scores.slice(0, 3).map(function (c) { return c.name + " (" + c.score + ")"; }).join(", ") + ".");
          chips([{ label: "Why do the top creators fit?", echo: true, go: function () { ta.value = "Why do the top creators in this selection fit my brief?"; submit(); } },
                 { label: "Change the brief and rescore", go: function () { flowFind("", { attach: x.token, name: x.name }); } },
                 { label: "Get a quote for it", go: function () { quoteFor({ name: x.name, token: x.token }); } },
                 { label: "Something else", ghost: true, go: function () { menu("What would you like to do?"); } }]);
        } else {
          say("This is “" + x.name + "” (" + x.count + " creator" + (x.count === 1 ? "" : "s") + "). It doesn't have a brief yet, so the creators aren't scored against your campaign.");
          say("Answer a few quick questions (free) and I'll score every creator in it.");
          chips([{ label: "Score this selection", primary: true, go: function () { flowFind("", { attach: x.token, name: x.name }); } },
                 { label: "Not now", ghost: true, go: function () { menu("What would you like to do?"); } }]);
        }
      });
    }

    /* -- 1. find creators: the brief questions, free, then one paid shortlist -- */
    var FLOW_IDS = ["goal", "platforms", "market", "category", "budget", "count"];
    // Phase E: a product page or the client's own brief, read into the brief right here in the chat.
    function flowSource(which, mode) {
      say(which === "file" ? "Choose the brief file. I'll read it and fill the questions; the file isn't kept." :
          "Paste the product page. I'll read it and fill the questions for you to check.", function () {
        var box = HV.briefSource({ chat: true, onUse: function (got, res) {
          box.classList.add("is-done");
          [].forEach.call(box.querySelectorAll("button, input"), function (b) { b.disabled = true; });
          bubble("me", "Use this brief");
          flowFind("", mode, got, res);
        } });
        row("ai", h("div", { class: "hv-msg hv-msg--ai hv-msg--wide hv-src" }, box));
        var b = box.querySelectorAll(".bs__opt")[which === "file" ? 1 : 0];
        if (b) b.click();
      });
    }
    function flowFind(seed, mode, preset, srcRes) {
      var text = typeof seed === "string" ? seed : "";
      var attach = mode && mode.attach;
      if (!text && !preset) {
        // Three ways in: quick taps (free), a product link or a brief file.
        say(attach ? "How would you like to give me the campaign?" : "Let's find the right creators. How would you like to start?");
        chips([{ label: "Answer a few quick taps · free", primary: true, go: function () { flowFind("", mode, {}); } },
               { label: "Paste a product link", go: function () { flowSource("link", mode); } },
               { label: "Upload a brief (PDF or Word)", go: function () { flowSource("file", mode); } }]);
        return;
      }
      // Scoring an existing selection needs the campaign, not a budget or a head count.
      var ids = attach ? ["goal", "platforms", "market", "gender", "category"] : FLOW_IDS;
      var fromSrc = preset && Object.keys(preset).length;
      say(fromSrc ? "Thanks. I filled what your " + (srcRes && srcRes.source && srcRes.source.kind === "file" ? "brief" : "page") + " says. Just a few taps for the rest." :
          attach ? "A few quick taps about the campaign, all free." :
          text ? "Got it. A few quick taps and I'll match the roster. This part is free." : "A few quick taps, all free.");
      Promise.all([loadQuestions(), text ? api("POST", "/api/brief/guess", { text: text }) : Promise.resolve({ b: {} })]).then(function (res) {
        var qs = res[0], answers = Object.assign(profileAnswers(), (res[1].b && res[1].b.answers) || {}, preset || {});
        var byId = {}; qs.forEach(function (q) { byId[q.id] = q; });
        var todo = ids.filter(function (id) { return byId[id] && !(answers[id] && answers[id].length); });
        var i = 0;
        function next() {
          if (i >= todo.length) return review();
          var q = byId[todo[i]];
          question(q, i, todo.length, {
            back: i > 0 ? function () { i--; delete answers[todo[i]]; next(); } : null,
            skip: q.required ? null : function () { i++; next(); },
            done: function (vals, note) {
              // Words that match no option are the client's "Other" answer: the server reads
              // them into the brief (e.g. "40" creators) and keeps them in the notes.
              if (note && q.other && (q.type === "many" || !vals.length)) {
                var nv = withOther(q, q.type === "many" ? vals : null, note);
                if (nv) { answers[q.id] = nv; note = ""; vals = []; }
              }
              if (vals.length) answers[q.id] = q.type === "many" ? vals : vals[0];
              else if (q.type === "many" && !answers[q.id]) answers[q.id] = ["any"];
              if (note) answers.notes = (answers.notes ? answers.notes + "; " : "") + note;
              i++; next();
            }
          });
        }
        function review() {
          var costs = (ME && ME.costs) || { brief: 5 };
          var lines = ids.filter(function (id) { return byId[id] && answers[id] && answers[id].length; }).map(function (id) {
            var v = answers[id]; return (byId[id].label.replace(/\?$/, "")) + ": " + (Array.isArray(v) ? v : [v]).map(function (x) { return optionLabel(byId[id], x); }).join(", ");
          });
          say("Here's your brief:\n" + lines.join("\n"));
          sayTiming(answers, srcRes);
          var list = [];
          if (!attach && selToken()) {
            // They are on a selection: score it against these answers (free), or start a separate list.
            chips([{ label: "Score this selection · free", primary: true, go: function () { scoreSelection(selToken(), answers); } },
                   { label: "Build a separate new shortlist" + (ME && ME.ai ? " · " + costs.brief + " credits" : ""), go: function () { if (ME && ME.ai) build(answers); else handoff("handoff", "Brief from the chat:\n" + lines.join("\n")); } },
                   { label: "Change answers", ghost: true, go: function () { flowFind(text, null, {}); } }]);
            return;
          }
          if (attach) {
            chips([{ label: "Score “" + (mode.name || "this selection") + "” · free", primary: true, go: function () { scoreSelection(attach, answers); } },
                   { label: "Change answers", ghost: true, go: function () { flowFind("", mode, {}); } }]);
            return;
          }
          if (ME && ME.ai) list.push({ label: "Build my shortlist · " + costs.brief + " credits", primary: true, go: function () { build(answers); } });
          list.push({ label: "Change answers", ghost: true, go: function () { flowFind(text, null, {}); } });
          if (!(ME && ME.ai)) list.push({ label: "Send it to my account manager", primary: true, go: function () { handoff("handoff", "Brief from Voice:\n" + lines.join("\n")); } });
          chips(list);
        }
        next();
      });
    }
    // Timing advisor in the chat: the best launch window from the occasions calendar, one line, free.
    function sayTiming(answers, srcRes) {
      var t = srcRes && srcRes.timing;
      var put = function (tm) { if (tm && tm.headline) say("**Timing:** " + tm.headline + " Creator content needs 6–8 weeks from brief to posting."); };
      if (t) { put(t); return; }
      var cats = (answers.category || []).filter(function (c) { return typeof c === "string" && c.indexOf("other:") !== 0 && c !== "any"; });
      queue = queue.then(function () {
        return api("GET", "/api/timing?c=" + encodeURIComponent(cats.join(",")) + "&m=" + encodeURIComponent(answers.market || "SA") +
                   (answers.timing ? "&t=" + encodeURIComponent(answers.timing) : "")).then(function (r) { if (r.b && r.b.ok) put(r.b); });
      });
    }
    function scoreSelection(token, answers) {
      say("Scoring every creator in it against your brief…");
      api("POST", "/api/brief/attach", { token: token, answers: answers }).then(function (r) {
        if (!r.b.ok) { say(r.b.reason === "missing" ? "A required answer is missing. Let's go through it again." : "That didn't work. Please try again."); chips([{ label: "Try again", go: function () { flowFind("", { attach: token }); } }]); return; }
        var picks = r.b.picks || [];
        say("Done. Every creator now has a score out of 100 for this brief." + (picks.length ? " Best fit: " + picks.slice(0, 3).map(function (p) { return ((p.creator && p.creator.name) || p.code) + " (" + p.score + ")"; }).join(", ") + "." : ""));
        queue = queue.then(function () { creatorCards(picks.slice(0, 8).map(function (p) { var c = Object.assign({ code: p.code, name: p.code }, p.creator || {}); c.fit = p.score; return c; })); });
        chips([{ label: "Show the scores on this page", primary: true, echo: false, go: function () { location.reload(); } },
               { label: "Why do the top creators fit?", go: function () { ta.value = "Why do the top creators in this selection fit my brief?"; submit(); } }]);
      });
    }
    function build(answers) {
      say("Matching the roster to your brief…");
      api("POST", "/api/brief/run", { answers: answers, name: "Voice shortlist" }).then(function (r) {
        if (!r.b.ok || r.b.empty) { say(r.b.message || "That didn't work and you weren't charged. Want to try again?"); menu(); return; }
        setCredits(r.b.credits); refreshFoot();
        if (typeof rememberBrief === "function") rememberBrief(r.b.brief_id);
        say((r.b.summary || (r.b.picks.length + " creators match your brief.")) + " Best fit first, scored out of 100.");
        queue = queue.then(function () { creatorCards(r.b.picks.slice(0, 6).map(function (p) { var c = Object.assign({ code: p.code, name: p.code }, p.creator || {}); c.fit = p.score; return c; })); });
        say("I've saved them as a selection for you.");
        chips([{ label: "Open the selection", primary: true, echo: false, go: function () {
                 var current = r.b.name || "Voice shortlist";
                 row("ai", h("div", { class: "hv-msg hv-msg--ai hv-act" },
                   nameForm(current, "Save and open", function (v) { renameThenOpen(r.b.token, codesOf(r.b.picks), current, v); })));
               } },
               { label: "Get a quote for it", go: function () { quoteFor({ name: "Voice shortlist", token: r.b.token }); } },
               { label: "Something else", ghost: true, go: function () { menu("What next?"); } }]);
      });
    }
    var picked = [];                      // codes added from the chat's cards
    function drawPicks() {
      picksBar.innerHTML = "";
      if (!picked.length) { picksBar.hidden = true; return; }
      picksBar.hidden = false;
      picksBar.appendChild(h("span", { class: "hv-picks__n" }, picked.length + " added"));
      picksBar.appendChild(h("button", { class: "hv-picks__save", type: "button", onclick: savePicks }, "Save as a selection"));
      picksBar.appendChild(h("button", { class: "hv-picks__clear", type: "button", "aria-label": "Clear the added creators", onclick: function () {
        picked = []; drawPicks(); log.querySelectorAll(".hv-card__add").forEach(function (b) { b.setAttribute("aria-pressed", "false"); });
      } }, "Clear"));
    }
    function savePicks() {
      if (!picked.length) return;
      // The client names it before it is saved; "Chat shortlist" is only the suggestion.
      var old = log.querySelector(".hv-namer-row");
      if (old) old.remove();
      var box = row("ai", h("div", { class: "hv-msg hv-msg--ai hv-act" }, nameForm("Chat shortlist", "Save", function (name, retry) {
        var codes = picked.slice();
        if (!codes.length) { box.remove(); return; }
        api("POST", "/api/selection", { name: name, codes: codes }).then(function (r) {
          if (!r.b.ok) { retry(); say("I couldn't save that just now. Please try again."); return; }
          box.remove();
          picked = []; drawPicks();
          log.querySelectorAll(".hv-card__add").forEach(function (b) { b.setAttribute("aria-pressed", "false"); });
          say("Saved " + codes.length + " creator" + (codes.length === 1 ? "" : "s") + " as “" + name + "”.");
          chips([{ label: "Open the selection", primary: true, echo: false, go: function () { location.href = ROOT + "selection/#s=" + encodeURIComponent(r.b.token); } },
                 { label: "Get a quote for it", go: function () { quoteFor({ name: name, token: r.b.token, codes: codes }); } }]);
        });
      })));
      box.classList.add("hv-namer-row");
    }
    function togglePick(code, btn) {
      var k = picked.indexOf(code);
      if (k > -1) picked.splice(k, 1); else picked.push(code);
      log.querySelectorAll('.hv-card__add[data-code="' + code + '"]').forEach(function (b) { b.setAttribute("aria-pressed", String(k === -1)); });
      drawPicks();
    }
    function openProfile(c) {
      var card = document.querySelector('.cat-card[data-code="' + c.code + '"]');
      var pp = card && card.querySelector("a.cat-card__analysis[data-analysis]");      // opens the side panel over the roster
      if (pp) { pp.click(); return; }
      window.open(ROOT + "creator/#c=" + encodeURIComponent(c.code), "_blank", "noopener");
    }
    function creatorCards(list, keep) {
      if (!list || !list.length) return;
      if (keep !== false) { msgs.push({ from: "cards", list: list.map(function (c) { return { code: c.code, name: c.name, photo_url: c.photo_url, fit: c.fit, followers: c.followers, city: c.city, tier: c.tier }; }) }); save(); }
      var wrap = h("div", { class: "hv-cards", role: "list", "aria-label": "Creators" });
      list.forEach(function (c) {
        var ph = h("span", { class: "hv-card__photo" }); bg(ph, c.photo_url);
        if (c.fit != null) ph.appendChild(h("span", { class: "hv-card__fit" }, String(c.fit)));
        var open = h("button", { class: "hv-card__open", type: "button", "aria-label": "Open " + c.name + "'s profile" }, ph,
          h("span", { class: "hv-card__txt" }, h("b", null, c.name),
            h("span", null, [c.tier, c.followers ? followers(c.followers) : "", c.city].filter(Boolean).join(" · "))));
        open.addEventListener("click", function () { openProfile(c); });
        var add = h("button", { class: "hv-card__add", type: "button", "data-code": c.code, "aria-pressed": String(picked.indexOf(c.code) > -1),
                                "aria-label": "Add " + c.name + " to my shortlist" });
        add.innerHTML = V_ICON.plus + "<span>Add</span>" + V_ICON.check.replace("<svg", '<svg class="hv-card__ok"') + "<span class=\"hv-card__added\">Added</span>";
        add.addEventListener("click", function () { togglePick(c.code, add); });
        wrap.appendChild(h("div", { class: "hv-card", role: "listitem" }, open, add));
      });
      log.appendChild(wrap); scroll();
      lastCards = list;
    }
    var lastCards = [];

    /* -- 2. show creators on this page: a sentence becomes the page's filters -- */
    function flowShow() {
      askFor("Describe who you'd like to see, e.g. “micro skincare creators in Jeddah on TikTok”.", "Who should I show?", runShow);
    }
    function runShow(text) {
        api("POST", "/api/discover/parse", { text: text }).then(function (r) {
          var p = (r.b && r.b.filters) || {};
          var done = applyFilters(p);
          if (!done.length) { say("I couldn't pick out filters from that. Try naming a platform, city, size or topic."); chips([{ label: "Try again", go: flowShow }, { label: "Back to the menu", ghost: true, go: function () { menu("What would you like to do?"); } }]); return; }
          // The catalogue counts on the server: wait for the filtered batch, then read its match count.
          ((window.hvCatalogue && window.hvCatalogue.server) ? window.hvCatalogue.settled() : Promise.resolve()).then(function () {
          var shown = (window.hvCatalogue && window.hvCatalogue.server) ? (window.hvCatalogue.matched() || 0)
            : Array.prototype.filter.call(document.querySelectorAll(".cat-card"), function (c) { return !c.hidden && !c.classList.contains("cat-card--copy"); }).length;
          say("Done. The page now shows " + done.join(", ") + ". " + (shown ? shown + " creator" + (shown === 1 ? "" : "s") + " match." : "Nobody matches all of that yet, so try loosening one filter."));
          chips([{ label: "Clear the filters", go: function () { clearFilters(); nextUp("Filters cleared. You're seeing the whole roster again."); } },
                 { label: "Build a scored shortlist instead", go: function () { flowFind(text); } },
                 { label: "Close chat", ghost: true, echo: false, go: function () { toggle(false); } }]);
          });
        });
    }
    function fold(t) { return String(t || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "").trim(); }
    function pick(sel) { var b = document.querySelector(sel); if (b && !b.checked) b.click(); return !!b; }
    function clearFilters() { var c = document.querySelector(".cat-active__clear"); if (c) c.click(); }
    function applyFilters(p) {
      clearFilters();
      var bar = document.querySelector(".cat-bar"); if (!bar) return [];
      var out = [];
      function each(dim, test, label) {
        var hit = false;
        Array.prototype.forEach.call(bar.querySelectorAll('input[data-dim="' + dim + '"]'), function (box) {
          if (test(box.value) && !box.checked) { box.click(); hit = true; }
        });
        if (hit) out.push(label);
      }
      (p.platform || []).forEach(function (pl) { each("platform", function (v) { return v === pl; }, pl); });
      var sizes = (p.tier || []).map(function (t) { return fold(t).replace("-tier", ""); });
      if (sizes.length || p.hcp) each("tier", function (v) {
        var hcp = /^hcp/i.test(v), base = fold(v.replace(/^hcp\s*-\s*/i, "")).replace("-tier", "");
        return (p.hcp ? hcp : !hcp) && (!sizes.length || sizes.some(function (s) { return base.indexOf(s) === 0; }));
      }, p.hcp ? "healthcare professionals" + (sizes.length ? " (" + p.tier.join(", ") + ")" : "") : p.tier.join(", ") + " creators");
      if ((p.city || []).length) {
        (p.city || []).forEach(function (city) { each("place", function (v) { return fold(v.split("|")[1]).indexOf(fold(city)) === 0; }, city); });
      } else if ((p.country || []).length) {
        p.country.forEach(function (c) { if (pick('input[data-country="' + c + '"]')) out.push(c); });
      }
      if ((p.interest_words || []).length) {
        var words = p.interest_words.map(fold).filter(Boolean);
        each("interest", function (v) { var f = " " + fold(v) + " "; return words.some(function (w) { return f.indexOf(w) !== -1; }); }, "the topics you named");
      }
      return out;
    }

    /* -- 3. work on my selection -- */
    // The roster is never downloaded whole any more: the creators a flow names are fetched by
    // code (/api/roster/cards), and typed names are searched on the server (/api/roster/page?q=).
    function roster(codes, words) {
      var calls = [];
      if (codes && codes.length) calls.push(api("GET", "/api/roster/cards?codes=" + encodeURIComponent(codes.slice(0, 200).join(","))).then(function (r) { return (r.b && r.b.cards) || []; }));
      (words || []).slice(0, 12).forEach(function (w) {
        calls.push(api("GET", "/api/roster/page?limit=20&sort=name&q=" + encodeURIComponent(w)).then(function (r) { return (r.b && r.b.items) || []; }));
      });
      return Promise.all(calls).then(function (lists) { return [].concat.apply([], lists); });
    }
    function byCode(list, code) { return list.filter(function (c) { return c.code === code; })[0]; }
    function flowSelection() {
      say("Let me pull up your selections…");
      api("GET", "/api/voice/selections").then(function (r) {
        var sels = (r.b && r.b.selections) || [];
        if (!sels.length) {
          say("You don't have a saved selection yet. Pick creators on the catalogue and press Save, or let me build one for you.");
          chips([{ label: "Find creators for a campaign", primary: true, go: flowFind }, { label: "Back to the menu", ghost: true, go: function () { menu("What else can I do?"); } }]);
          return;
        }
        say("Which one?");
        chips(sels.slice(0, 8).map(function (s) {
          return { label: s.name + " · " + s.codes.length + (s.mine ? "" : " (team)"), go: function () { selActions(s); } };
        }), { stack: true });
      });
    }
    function selActions(s) {
      say("“" + s.name + "” has " + s.codes.length + " creator" + (s.codes.length === 1 ? "" : "s") + ". What should I do?");
      chips([{ label: "Open it", echo: false, go: function () { location.href = ROOT + "selection/#s=" + encodeURIComponent(s.token); } },
             { label: "Add creators", go: function () { selAdd(s); } },
             { label: "Remove creators", go: function () { selRemove(s); } },
             { label: "Rename it", go: function () { selRename(s); } },
             { label: "Compare two creators", go: function () { selCompare(s); } },
             { label: "Get a quote for it", go: function () { quoteFor(s); } }]);
    }
    function saveSel(s, codes, name, msg) {
      return api("POST", "/api/selection", { token: s.token, name: name || s.name, codes: codes }).then(function (r) {
        if (!r.b.ok) { say(r.b.reason === "empty" ? "A selection needs at least one creator, so I left it as it was." : "I couldn't save that just now. Please try again."); return; }
        s.codes = codes; s.name = name || s.name; s.token = r.b.token || s.token;
        say(msg);
        chips([{ label: "Open it", primary: true, echo: false, go: function () { location.href = ROOT + "selection/#s=" + encodeURIComponent(s.token); } },
               { label: "More changes", go: function () { selActions(s); } },
               { label: "Done", ghost: true, go: function () { nextUp("Anything else?"); } }]);
      });
    }
    function selAdd(s) {
      askFor("Type the creators' names or codes, separated by commas.", "e.g. Sara A., HV-MI-014", function (text) {
        var want = text.split(/[,،\n]+/).map(fold).filter(Boolean), found = [], miss = [];
        roster(null, want).then(function (list) {
          want.forEach(function (w) {
            var c = list.filter(function (x) { return fold(x.code) === w || fold(x.name) === w; })[0] ||
                    list.filter(function (x) { return fold(x.name).indexOf(w) === 0; })[0];
            if (c && s.codes.indexOf(c.code) === -1 && found.indexOf(c) === -1) found.push(c); else if (!c) miss.push(w);
          });
          if (!found.length) { say("I couldn't find " + (miss.length ? "“" + miss.join("”, “") + "”" : "anyone new") + " on the roster. Check the spelling, or use the code on the card."); chips([{ label: "Try again", go: function () { selAdd(s); } }, { label: "Back", ghost: true, go: function () { selActions(s); } }]); return; }
          say("Add " + found.map(function (c) { return c.name; }).join(", ") + " to “" + s.name + "”?" + (miss.length ? " (I couldn't find: " + miss.join(", ") + ")" : ""));
          chips([{ label: "Yes, add " + (found.length === 1 ? "them" : "all " + found.length), primary: true, go: function () {
            saveSel(s, s.codes.concat(found.map(function (c) { return c.code; })), null, "Added. “" + s.name + "” now has " + (s.codes.length + found.length) + " creators.");
          } }, { label: "Cancel", ghost: true, go: function () { selActions(s); } }]);
        });
      });
    }
    function selRemove(s) {
      roster(s.codes).then(function (list) {
        var drop = [];
        say("Tap the creators to remove, then confirm.");
        chips(s.codes.map(function (code) {
          var c = byCode(list, code) || { name: code };
          return { label: c.name, pressed: false, toggle: function (b) {
            var k = drop.indexOf(code); if (k > -1) drop.splice(k, 1); else drop.push(code);
            b.setAttribute("aria-pressed", String(k === -1));
          } };
        }).concat([{ label: "Remove selected", primary: true, echo: false, go: function () {
          if (!drop.length) { say("Nothing picked, so nothing changed."); return; }
          bubble("me", "Remove " + drop.length);
          saveSel(s, s.codes.filter(function (c) { return drop.indexOf(c) === -1; }), null, "Removed " + drop.length + ". “" + s.name + "” now has " + (s.codes.length - drop.length) + " creators.");
        } }]), { keep: true });
        queue = queue.then(function () {
          var sets = log.querySelectorAll(".hv-chips"); var last = sets[sets.length - 1];
          last.addEventListener("click", function (e) { if (e.target.closest(".hv-chip--lime")) last.remove(); });
        });
      });
    }
    function selRename(s) {
      askFor("What should “" + s.name + "” be called?", "New name", function (text) {
        var name = text.trim().slice(0, 120);
        if (!name) return;
        saveSel(s, s.codes.slice(), name, "Renamed to “" + name + "”.");
      });
    }
    function selCompare(s) {
      roster(s.codes).then(function (list) {
        var two = [];
        say("Tap two creators to compare.");
        chips(s.codes.map(function (code) {
          var c = byCode(list, code) || { name: code, code: code };
          return { label: c.name, pressed: false, toggle: function (b) {
            if (two.indexOf(c) > -1) return;
            two.push(c); b.setAttribute("aria-pressed", "true");
            if (two.length === 2) { b.closest(".hv-chips").remove(); bubble("me", two[0].name + " vs " + two[1].name); compare(two); }
          } };
        }), { keep: true });
      });
    }
    function compare(two) {
      queue = queue.then(function () {
        var rows = [["Size", function (c) { return c.tier || "—"; }], ["Followers", function (c) { return c.followers ? followers(c.followers) : "—"; }],
                    ["Platform", function (c) { return c.platform || "—"; }], ["City", function (c) { return c.city || "—"; }],
                    ["Niche", function (c) { return c.interest || "—"; }], ["Full analysis", function (c) { return c.analysis ? "On file" : "Not yet"; }]];
        var t = h("table", { class: "hv-compare" });
        var hr = h("tr", null, h("th", null, ""));
        two.forEach(function (c) { hr.appendChild(h("th", { scope: "col" }, c.name)); });
        t.appendChild(hr);
        rows.forEach(function (r) {
          var tr = h("tr", null, h("th", { scope: "row" }, r[0]));
          two.forEach(function (c) { tr.appendChild(h("td", null, r[1](c))); });
          t.appendChild(tr);
        });
        row("ai", h("div", { class: "hv-msg hv-msg--ai hv-msg--wide" }, t));
      });
      var missing = two.filter(function (c) { return !c.analysis; });
      var list = two.filter(function (c) { return c.analysis; }).map(function (c) {
        return { label: "Open " + c.name.split(" ")[0] + "'s analysis", echo: false, go: function () { location.href = ROOT + "creator/#c=" + encodeURIComponent(c.code); } };
      });
      missing.forEach(function (c) {
        list.push({ label: "Request " + c.name.split(" ")[0] + "'s analysis", go: function () {
          api("POST", "/api/creator/request", { code: c.code }).then(function (r) {
            nextUp(r.b.ok ? "Requested. The team will add " + c.name + "'s full analysis and you'll see it on their card." : "That request didn't go through. Please try again.");
          });
        } });
      });
      list.push({ label: "Done", ghost: true, go: function () { nextUp("Anything else?"); } });
      chips(list);
    }

    /* -- 4 & 5. quote and a person -- */
    function flowQuote() {
      api("GET", "/api/voice/selections").then(function (r) {
        var sels = (r.b && r.b.selections) || [];
        if (!sels.length) { handoffAsk("quote", null, "Tell me what you'd like quoted (creators, deliverables, dates) and I'll send it to your account manager."); return; }
        say("Which selection should we quote?");
        chips(sels.slice(0, 6).map(function (s) { return { label: s.name + " · " + s.codes.length, go: function () { quoteFor(s); } }; })
          .concat([{ label: "Something else", ghost: true, go: function () { handoffAsk("quote", null, "Tell me what you'd like quoted and I'll pass it on."); } }]), { stack: true });
      });
    }
    function quoteFor(s) { handoffAsk("quote", s, "Anything to add for the quote, like deliverables, dates or budget? Or tap Send as is."); }
    function handoffAsk(topic, sel, prompt) {
      askFor(prompt, "Add a note…", function (text) { handoff(topic, text, sel); });
      if (sel) chips([{ label: "Send as is", primary: true, go: function () { expecting = null; ta.placeholder = "Type a message…"; handoff(topic, "", sel); } }]);
    }
    function flowHuman() { handoffAsk("handoff", null, "What would you like to discuss? I'll send it to your account manager with our chat."); }
    function handoff(topic, note, sel) {
      api("POST", "/api/voice/handoff", { topic: topic, message: note, selection: sel ? sel.name + " (" + sel.token + ")" : "", transcript: msgs.slice(-30) }).then(function (r) {
        if (r.s === 429) { say("You've sent a few requests already today. The team has them and will be in touch."); return; }
        if (!r.b.ok) { say("That didn't go through. Please try again in a moment."); return; }
        say((topic === "quote" ? "Quote request sent" : "Sent") + (r.b.kam ? " to your account manager" : " to the HelloVoice team") +
            ". They usually reply within one working day, by email" + (ME && ME.user && ME.user.phone ? " or phone" : "") + ".");
        nextUp("Anything else?");
      });
    }

    /* -- an action the assistant prepared: nothing happens until the client confirms -- */
    function actionCard(a) {
      var box = h("div", { class: "hv-msg hv-msg--ai hv-act", role: "group", "aria-label": "Confirm this change" });
      box.appendChild(h("p", { class: "hv-act__what" }, a.text + "?"));
      // A new selection: the client can type its name here before confirming.
      var nameIn = null;
      if (a.tool === "save_as_selection") {
        nameIn = h("input", { class: "pt-namer__in hv-act__name", type: "text", maxlength: "100", "aria-label": "Name this selection" });
        nameIn.value = a.name || "Chat shortlist";
        box.appendChild(h("label", { class: "pt-namer" }, h("span", { class: "pt-namer__l" }, "Name this selection"), h("span", { class: "pt-namer__row" }, nameIn)));
      }
      var yes = h("button", { class: "hv-act__yes", type: "button" }, "Confirm");
      var no = h("button", { class: "hv-act__no", type: "button" }, "Cancel");
      var row_ = h("div", { class: "hv-act__btns" }, yes, no);
      box.appendChild(row_);
      function settle(label) { row_.remove(); box.classList.add("is-done"); box.appendChild(h("p", { class: "hv-act__state" }, label)); }
      yes.addEventListener("click", function () {
        yes.disabled = no.disabled = true; yes.textContent = "Working…";
        var body = { token: a.token };
        if (nameIn) { body.name = nameIn.value.replace(/\s+/g, " ").trim(); nameIn.disabled = true; }
        api("POST", "/api/chat/confirm", body).then(function (r) {
          var res = r.b || {};
          if (!res.ok) { settle("Not done"); say(res.message || "That didn't go through. Please try again."); return; }
          settle("Done");
          say(res.message || "Done.");
          if (res.open) chips([{ label: "Open the new selection", primary: true, echo: false, go: function () { location.href = ROOT + "selection/#s=" + encodeURIComponent(res.open); } }]);
          else if (res.reload && selToken()) { say("Updating the page…"); queue = queue.then(function () { setTimeout(function () { location.reload(); }, 700); }); }
        });
      });
      no.addEventListener("click", function () {
        settle("Cancelled"); api("POST", "/api/chat/dismiss", { token: a.token });
      });
      row("ai", box);
    }

    /* -- a calculated answer: how it was worked out, per creator, on tap -- */
    function breakdown(b) {
      var pct = /%/.test(b.label), money = /SAR/.test(b.label);
      function fmt(v) { return pct ? (Math.round(v * 10) / 10) + "%" : money ? "SAR " + money_(v) : followers(v); }
      function money_(v) { return Math.round(v).toLocaleString("en-US"); }
      var box = h("details", { class: "hv-msg hv-msg--ai hv-break" });
      box.appendChild(h("summary", null, "See breakdown · " + b.covered + " of " + b.of + " creators"));
      var ol = h("ol", { class: "hv-break__list" });
      b.rows.forEach(function (r) { ol.appendChild(h("li", null, h("span", null, r.name), h("b", null, fmt(r.value)))); });
      box.appendChild(ol);
      var how = (b.label.replace(/\s*\(.*\)/, "")) + ": " + (b.total != null ? "total " + fmt(b.total) + " · " : "") + "average " + fmt(b.average) +
                " across the " + b.covered + " creator" + (b.covered === 1 ? "" : "s") + " with figures on their analysis page.";
      box.appendChild(h("p", { class: "hv-break__how" }, how));
      if (b.missing && b.missing.length) box.appendChild(h("p", { class: "hv-break__miss" }, "No analysis yet: " + b.missing.join(", ") + "."));
      row("ai", box);
    }

    /* -- after an answer: the likely next asks, one tap each -- */
    function followUps(list) {
      var acts = { "Find creators": flowFind, "Find creators within my budget": flowFind, "Get a quote": flowQuote,
                   "What can my budget reach?": flowBudget,
                   "Talk to a person": flowHuman,
                   "Save all as a selection": function () { (lastCards || []).forEach(function (c) { if (picked.indexOf(c.code) === -1) picked.push(c.code); }); drawPicks(); savePicks(); } };
      chips((list || []).map(function (label) {
        return acts[label] ? { label: label, go: acts[label] } : { label: label, echo: false, go: function () { ta.value = label; submit(); } };
      }), { hint: "Suggested next · or type below" });
    }

    /* -- streamed answers: one JSON object per line -- */
    function stream(path, body, onEvent) {
      return fetch(API + path, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
        .then(function (r) {
          var type = r.headers.get("Content-Type") || "";
          if (!r.ok || type.indexOf("ndjson") === -1 || !r.body || !r.body.getReader) {
            return r.json().catch(function () { return {}; }).then(function (b) {
              if (r.ok && b && b.t) { onEvent(b); return; }
              onEvent({ t: "error", status: r.status, message: (b && b.message) || "", reason: b && b.reason });
            });
          }
          var reader = r.body.getReader(), dec = new TextDecoder(), buf = "";
          function pump() {
            return reader.read().then(function (res) {
              if (res.done) { if (buf.trim()) try { onEvent(JSON.parse(buf)); } catch (e) { /* cut */ } return; }
              buf += dec.decode(res.value, { stream: true });
              var lines = buf.split("\n"); buf = lines.pop();
              lines.forEach(function (l) { if (l.trim()) try { onEvent(JSON.parse(l)); } catch (e) { /* skip */ } });
              return pump();
            });
          }
          return pump();
        })
        .catch(function () { onEvent({ t: "error", status: 0, message: "Could not reach the server. Please try again." }); });
    }

    /* -- typing: answers a pending question, or goes to the AI -- */
    var REQ = /campaign|creator|influencer|shortlist|launch|recommend|suggest|find|looking for|ugc|حمل|مؤثر|إطلاق|اطلاق|ابحث|أبحث|اقترح/i;
    var thread = null, busy = false;
    function submit(given, silent) {
      var typed = typeof given !== "string";
      var text = typed ? ta.value.trim() : given;
      if (!text || busy) return;
      if (typed) { ta.value = ""; grow(); }
      if (!silent) bubble("me", text);
      Array.prototype.forEach.call(log.querySelectorAll(".hv-chips"), function (c) { c.remove(); });
      if (expecting) { var fn = expecting; expecting = null; ta.placeholder = "Type a message…"; fn(text); return; }
      if (/account manager|talk to (a )?(person|human|someone)|call me/i.test(text)) { handoff("handoff", text); return; }
      if (/\bquot(e|ation)|عرض سعر|تسعير/i.test(text)) { flowQuote(); return; }
      if (!selToken() && /my selection|my shortlist|\b(add|remove|rename|compare)\b|قائمتي/i.test(text)) { flowSelection(); return; }
      if (document.querySelector(".cat-bar") && /^(show|filter|only|display|اعرض|أظهر)\b/i.test(text)) { runShow(text); return; }
      // On a selection's page the client is discussing THAT selection: the assistant answers with its
      // brief and scores. Only elsewhere does a campaign description start the free find-creators taps.
      // Typed questions go to the assistant with the page as context; it decides (it can build a
      // shortlist itself). The free tap-through questions stay one tap away in the menu.
      // "What can SAR 60,000 reach?" is answered on the server with the ROI card: free, no AI needed.
      var roiAsk = /(sar|sr|riyals?|ريال)\s*\d|\d[\d,.]*\s*(k|thousand|ألف)?\s*(sar|sr|riyals?|ريال)/i.test(text);
      if (!roiAsk && !(ME && ME.ai) && !selToken() && REQ.test(text) && !/how much|price|cost/i.test(text)) { flowFind(text); return; }
      if (!roiAsk && !(ME && ME.ai)) { say("I can't answer typed questions on this access yet. Tap an option, or I can pass your question to your account manager."); chips([{ label: "Send it to my account manager", primary: true, go: function () { handoff("handoff", text); } }, { label: "Show the menu", ghost: true, go: function () { menu(); } }]); return; }
      busy = true; send.disabled = true;
      // While it works: what it is doing right now, then the answer as it is written.
      // Helvy thinks: the thinking clip beside one live step line with a light sweep across it.
      // Until the server names its steps, the line rotates every 1.4 s; each real step then ticks.
      var now = h("p", { class: "cx-think__now" }, "Reading your message…");
      var steps = h("ol", { class: "cx-think__steps" });
      var work = h("div", { class: "hv-msg hv-msg--ai cx-think", role: "status", "aria-label": "Helvy is working on it" }, clip("thinking", null, { seq: COOK_SEQ }), h("div", null, now, steps));
      headWorking(true);
      var workRow = row("ai", work), out = null, ty = null, acc = "", ended = false, real = false;
      var ROT = ["Reading your message…", "Checking the catalogue…", "Thinking it through…", "Writing your answer…"], ri = 0;
      var rot = setInterval(function () { if (!real) { ri = (ri + 1) % ROT.length; now.textContent = ROT[ri]; } }, 1400);
      function step(label) {
        real = true;
        steps.querySelectorAll("li.is-now").forEach(function (li) { li.classList.remove("is-now"); li.classList.add("is-done"); });
        steps.appendChild(h("li", { class: "is-now" }, label));
        now.textContent = label + "…"; scroll();
      }
      function stop() { busy = false; send.disabled = false; ended = true; clearInterval(rot); }
      stream("/api/chat/stream", Object.assign({ message: text, thread: thread, selection: selToken() || undefined }, pageCtx()), function (ev) {
        if (ev.t === "step") { step(ev.text); return; }
        if (ev.t === "delta") {
          if (!out) { workRow.remove(); out = h("div", { class: "hv-msg hv-msg--ai" }); row("ai", out); ty = typer(out); }
          acc += ev.text; ty.push(ev.text);
          return;
        }
        if (ev.t === "done") {
          stop();
          if (!out) { workRow.remove(); out = h("div", { class: "hv-msg hv-msg--ai" }); row("ai", out); ty = typer(out); }
          msgs.push({ from: "ai", text: ev.reply }); thread = ev.thread || thread; save();
          if (ev.credits != null) { setCredits(ev.credits); refreshFoot(); }
          // Cards and next steps follow once the answer has finished typing.
          ty.end(ev.reply, function () {
            headWorking(false);                    // he keeps working until the last word is typed
            if (ev.roi && HV.roiCard) { row("ai", HV.roiCard(ev.roi)); msgs.push({ from: "roi", roi: ev.roi }); save(); }
            if (ev.breakdown && ev.breakdown.rows && ev.breakdown.rows.length) breakdown(ev.breakdown);
            (ev.actions || []).forEach(actionCard);
            if (ev.cards && ev.cards.length) creatorCards(ev.cards);
            followUps(ev.next);
          });
          return;
        }
        if (ev.t === "error") {
          stop(); workRow.remove(); headWorking(false);
          if (out && ty) ty.end(acc);
          if (ev.reason === "no_credits") { say(ev.message || "You're out of AI credits."); chips([{ label: "Talk to a person", go: flowHuman }]); return; }
          say(ev.status === 429 ? "One moment, that was quick. Try again in a few seconds." : (ev.message || "That didn't work, and you weren't charged."));
          if (ev.credits != null) { setCredits(ev.credits); refreshFoot(); }
        }
      }).then(function () { if (!ended) { stop(); headWorking(false); if (!out) workRow.remove(); } });
    }
    function grow() { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 120) + "px"; }
    ta.addEventListener("input", grow);
    ta.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } });
    send.addEventListener("click", submit);

    /* -- open and close -- */
    var started = false;
    function toggle(on) {
      if (on === undefined) on = panel.hidden;
      if (on) {
        panel.hidden = false;
        (document.hidden ? setTimeout : requestAnimationFrame)(function () { root.classList.add("is-open"); });
        launch.setAttribute("aria-expanded", "true");
        launch.querySelector(".hv-launch__dot").hidden = true;
        hideNudge(true);
        if (!started) {
          started = true;
          if (msgs.length) {
            thread = (kept && kept.thread) || thread;
            msgs.forEach(function (m) {
              if (m.from === "cards") creatorCards(m.list, false);
              else if (m.from === "roi") { if (HV.roiCard) row("ai", HV.roiCard(m.roi)); }
              else bubble(m.from, m.text, false);
            });
            log.appendChild(h("p", { class: "hv-sep" }, "Earlier in this chat"));
            if (selToken()) aboutSelection(); else menu("Welcome back. What would you like to do?");
          }
          else greet();
        }
        setTimeout(function () { ta.focus({ preventScroll: true }); }, 60);
      } else {
        root.classList.remove("is-open");
        launch.setAttribute("aria-expanded", "false");
        setTimeout(function () { if (!root.classList.contains("is-open")) panel.hidden = true; }, reduce ? 0 : 220);
        launch.focus({ preventScroll: true });
      }
    }
    launch.addEventListener("click", function () { toggle(); });
    closeBtn.addEventListener("click", function () { toggle(false); });
    minBtn.addEventListener("click", function () { toggle(false); });
    // The account page's "Message your account manager" opens straight onto the hand-off.
    HV.talk = function () { toggle(true); setTimeout(flowHuman, 400); };
    // Tour demo only: Helvy is briefed on screen, letter by letter, then answers from the demo world.
    if (window.hvDemo) {
      HV.voiceDemo = function (text, fresh) {
        var wasOpen = root.classList.contains("is-open");
        toggle(true);
        if (fresh) { log.innerHTML = ""; msgs = []; queue = Promise.resolve(); }
        var i = 0;
        (function type() {
          if (busy) { setTimeout(type, 200); return; }
          if (i === 0 && fresh && !wasOpen) { i = -1; setTimeout(type, reduce ? 0 : 1300); return; }
          if (i < 0) i = 0;
          if (i <= text.length) { ta.value = text.slice(0, i); grow(); i += 1; setTimeout(type, reduce ? 0 : 26); return; }
          setTimeout(function () { submit(); ta.blur(); }, reduce ? 0 : 260);
        })();
      };
      HV.voiceClose = function () { if (root.classList.contains("is-open")) toggle(false); };
    }
    freshBtn.addEventListener("click", function () {
      msgs = []; thread = null; save(); expecting = null; ta.placeholder = "Type a message…"; ta.value = ""; grow();
      picked = []; drawPicks(); log.innerHTML = ""; queue = Promise.resolve(); greet();
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && root.classList.contains("is-open")) toggle(false); });

    /* -- bigger window -- */
    var BIG = "hv-chat-big";
    function setBig(on) {
      root.classList.toggle("is-big", on);
      growBtn.setAttribute("aria-pressed", String(on));
      growBtn.setAttribute("aria-label", on ? "Make the chat smaller" : "Make the chat bigger");
      growBtn.innerHTML = on ? V_ICON.shrink : V_ICON.grow;
      try { localStorage.setItem(BIG, on ? "1" : "0"); } catch (e) { /* private */ }
      scroll();
    }
    growBtn.addEventListener("click", function () { setBig(!root.classList.contains("is-big")); });
    try { if (localStorage.getItem(BIG) === "1") setBig(true); } catch (e) { /* private */ }

    /* -- speak to Helvy: what is heard shows live above the box; when the client stops,
       it is sent as a normal message. Tap the mic again to stop early. -- */
    if (mic) {
      var rec = null, said = "", base = "", hideT = 0;
      function strip(state, text) {
        clearTimeout(hideT);
        heard.hidden = false;
        heard.className = "hv-heard hv-heard--" + state;
        heard.textContent = "";
        heard.appendChild(h("span", { class: "hv-heard__dot", "aria-hidden": "true" }));
        heard.appendChild(h("span", { class: "hv-heard__k" }, state === "on" ? "Listening · " + VLANG[vlang][1] : state === "err" ? "Voice" : "Heard"));
        var t = h("span", { class: "hv-heard__t", dir: "auto", lang: vlang.slice(0, 2) }, text || (state === "on" ? "Speak now…" : ""));
        heard.appendChild(t);
        if (state !== "on") hideT = setTimeout(function () { heard.hidden = true; }, state === "err" ? 4200 : 1200);
      }
      langBtn.addEventListener("click", function () {
        vlang = vlang === "ar-SA" ? "en-US" : "ar-SA";
        try { localStorage.setItem("hv-voice-lang", vlang); } catch (e) { /* private */ }
        paintLang();
        if (rec) { rec.abort(); }
      });
      mic.addEventListener("click", function () {
        if (rec) { rec.stop(); return; }
        rec = new Speech();
        rec.lang = vlang;
        rec.interimResults = true; rec.continuous = false; rec.maxAlternatives = 1;
        said = ""; base = ta.value ? ta.value.replace(/\s*$/, " ") : "";
        mic.classList.add("is-on"); mic.setAttribute("aria-pressed", "true"); mic.setAttribute("aria-label", "Stop listening");
        compose.classList.add("is-listening");
        strip("on", "");
        var errored = false;
        rec.onresult = function (e) {
          var fin = "", live = "";
          for (var k = 0; k < e.results.length; k++) { if (e.results[k].isFinal) fin += e.results[k][0].transcript; else live += e.results[k][0].transcript; }
          said = fin;
          strip("on", (fin + " " + live).trim());
        };
        rec.onerror = function (e) {
          errored = true;
          var why = e && e.error;
          strip("err", why === "not-allowed" || why === "service-not-allowed" ? "Allow the microphone for this site to speak to Helvy." :
                why === "no-speech" ? "Didn't catch that. Tap the mic and try again." : why === "aborted" ? "Stopped." : "Voice didn't work this time. You can type instead.");
        };
        rec.onend = function () {
          mic.classList.remove("is-on"); mic.setAttribute("aria-pressed", "false"); mic.setAttribute("aria-label", "Speak your message");
          compose.classList.remove("is-listening");
          rec = null;
          var text = (base + said).replace(/\s+/g, " ").trim();
          if (said.trim()) { strip("done", said.trim()); ta.value = text; grow(); submit(); }
          else if (!errored) strip("err", "Didn't catch that. Tap the mic and try again.");
          if (!expecting) ta.placeholder = "Type a message…";
        };
        try { rec.start(); } catch (e) { rec = null; mic.classList.remove("is-on"); compose.classList.remove("is-listening"); strip("err", "Voice didn't start. You can type instead."); }
      });
    }

    /* -- the nudge: once per visit, after the client has had a look around -- */
    var NUDGE = "hv-voice-nudged";
    function hideNudge(forever) {
      nudge.classList.remove("is-in");
      setTimeout(function () { nudge.hidden = true; }, 200);
      if (forever) { try { sessionStorage.setItem(NUDGE, "1"); } catch (e) { /* private */ } }
    }
    nudge.addEventListener("click", function (e) { if (e.target.closest(".hv-nudge__x")) { hideNudge(true); return; } toggle(true); });
    var nudged = false;
    try { nudged = sessionStorage.getItem(NUDGE) === "1"; } catch (e) { /* private */ }
    if (!nudged) {
      setTimeout(function () {
        if (root.classList.contains("is-open")) return;
        nudge.hidden = false;
        requestAnimationFrame(function () { nudge.classList.add("is-in"); launch.classList.add("is-waving"); });
        setTimeout(function () { launch.classList.remove("is-waving"); }, 1600);
        setTimeout(function () { if (!root.classList.contains("is-open")) hideNudge(true); }, 9000);
      }, 4500);
    }
  }

  /* ---------------------------------------------------- AI shortlist card */
  // "Build a shortlist with AI": a card beside the catalogue's filters. Six
  // taps fill a brief (free), the server scores the whole roster, and the grid
  // narrows to the picks, best first, each with one score per platform. The
  // wait is staged: the character scouts with his camera while named steps
  // tick off, so the client watches their campaign list being made.

  var AI_STEPS = [
    ["goal", "Goal", '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r=".6" fill="currentColor"/>'],
    ["platforms", "Platforms", '<rect x="7" y="3" width="10" height="18" rx="2.5"/><path d="M11 17.5h2"/>'],
    ["market", "Audience", '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.6 2.6 2.6 14.4 0 17M12 3.5c-2.6 2.6-2.6 14.4 0 17"/>'],
    ["category", "Space", '<path d="M3.5 12.5l8-8h7v7l-8 8z"/><circle cx="15" cy="9" r="1.3"/>'],
    ["budget", "Budget", '<rect x="3.5" y="6.5" width="17" height="12" rx="2.5"/><path d="M15.5 12.5h2.5M3.5 10h17"/>'],
    ["count", "Creators", '<circle cx="9" cy="8.5" r="3"/><circle cx="16.5" cy="9.5" r="2.4"/><path d="M3.5 19c.5-3 2.7-4.6 5.5-4.6s5 1.6 5.5 4.6M15 14.6c2.6 0 4.6 1.4 5 4.4"/>']
  ];
  var AI_SHORT = { Instagram: "IG", TikTok: "TT", Snapchat: "SC", YouTube: "YT" };
  var AI_MARKET = { SA: "KSA", AE: "UAE", EG: "Egypt", KW: "Kuwait", QA: "Qatar", BH: "Bahrain", OM: "Oman", JO: "Jordan" };
  var AI_GOAL = { awareness: "Awareness", engagement: "Engagement", traffic: "Traffic", conversion: "Conversion", balanced: "Balanced" };
  function aiSvg(path, size) {
    return '<svg viewBox="0 0 24 24" width="' + (size || 20) + '" height="' + (size || 20) + '" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + path + "</svg>";
  }

  function mountAiCard() {
    if (document.body.getAttribute("data-page") !== "catalogue" || $("ai-sl")) return;
    var tries = 0;
    (function wait() {
      var host = document.querySelector(".cat-controls .cat-container");
      if (host && host.querySelector(".cat-bar")) return buildAiCard(host);
      if (++tries < 60) setTimeout(wait, 250);
    })();
  }

  // Setup above, results below: the client-logo band moves above the setup, the setup
  // gets its own heading and frame, and the roster opens with a Results header.
  function frameSetup(host) {
    var controls = host.closest(".cat-controls"), clients = document.querySelector(".cat-clients"), grid = $("cat-grid");
    if (!controls || controls.classList.contains("is-setup")) return;
    if (clients && controls.compareDocumentPosition(clients) & Node.DOCUMENT_POSITION_FOLLOWING) controls.parentNode.insertBefore(clients, controls);
    controls.classList.add("is-setup");
    var head = h("div", { class: "setup-head" });
    head.innerHTML = '<h2 class="setup-head__title">Find your creators</h2>' +
      '<p class="setup-head__sub">Filter the roster yourself, or let AI build the list. Your results open just below.</p>';
    host.insertBefore(head, host.firstChild);
    if (grid && !$("results-head")) {
      var rh = h("div", { id: "results-head", class: "results-head" });
      rh.innerHTML = '<h2 class="results-head__title">Results</h2><p class="results-head__sub" id="results-sub">Every creator that matches your filters. Tick the ones you want.</p>';
      // Above the roster's own count/sort row when there is one, so "Results" opens the section.
      var bar = grid.previousElementSibling, anchor = bar && bar.classList.contains("cat-results") ? bar : grid;
      grid.parentNode.insertBefore(rh, anchor);
    }
  }
  function buildAiCard(host) {
    frameSetup(host);
    var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
    host.classList.add("ai-host");
    var card = h("section", { id: "ai-sl", class: "ai-sl", "aria-labelledby": "ai-sl-title" });
    var roster = document.querySelectorAll(".cat-card").length;
    // Helvy on lime (fix batch 4): the "voice" set's expressive clips, as this card had before the
    // transparent cut-out replaced them (his idle and think barely move, so he read as a still).

    // Collapsed: the invitation.
    var intro = h("div", { class: "ai-sl__intro" });
    intro.innerHTML = '<div class="ai-sl__face"></div>' +
      '<div class="ai-sl__copy"><h2 class="ai-sl__title" id="ai-sl-title">Build a shortlist with AI</h2>' +
      "<p>Six quick taps, and Helvy picks the creators that fit your campaign best.</p></div>";
    var start = h("button", { class: "ai-sl__start", type: "button" }, "Start");
    start.insertAdjacentHTML("beforeend", aiSvg('<path d="M5 12h13M13 6l6 6-6 6"/>', 18));
    intro.appendChild(start);
    // Phase E: or start from a product page or the client's own brief file.
    var altLink = h("button", { class: "ai-sl__alt-b", type: "button", html: icon("link") + "<span>Product link</span>" });
    var altFile = h("button", { class: "ai-sl__alt-b", type: "button", html: icon("upload") + "<span>Brief file</span>" });
    intro.appendChild(h("div", { class: "ai-sl__alt" }, h("span", null, "Or start from"), altLink, altFile));
    intro.querySelector(".ai-sl__face").appendChild(lime("loop"));

    // Expanded: the journey.
    var run = h("div", { class: "ai-sl__run", hidden: "" });
    var head = h("div", { class: "ai-sl__head" });
    var level = h("p", { class: "ai-sl__level", "aria-live": "polite" });
    var quit = h("button", { class: "ai-sl__quit", type: "button", "aria-label": "Close the AI shortlist" });
    quit.innerHTML = aiSvg('<path d="M6 6l12 12M18 6L6 18"/>', 18);
    var track = h("ol", { class: "ai-sl__track", "aria-label": "Brief progress" });
    AI_STEPS.forEach(function (s, i) {
      var li = h("li", { class: "ai-sl__node", "data-i": String(i) });
      li.innerHTML = '<span class="ai-sl__dot">' + aiSvg(s[2], 18) + '<i class="ai-sl__tick">' + aiSvg('<path d="M5 12.5l4.2 4.2L19 7"/>', 16) + "</i></span><span class=\"ai-sl__lbl\">" + s[1] + "</span>";
      track.appendChild(li);
    });
    var fill = h("span", { class: "ai-sl__fill", "aria-hidden": "true" });
    track.appendChild(fill);
    head.appendChild(track); head.appendChild(level); head.appendChild(quit);
    var stage = h("div", { class: "ai-sl__stage" });
    // The coach: the character reacts to every step (points at a new question, thinks
    // while you choose, thumbs-up on an answer, cheers at the end), over a power meter.
    var coach = h("div", { class: "ai-sl__coach", "aria-hidden": "true" });
    // The lime frame (HV.lime) lays each new clip over the last and plays a reaction's follow-up
    // loop on the same element, so it keeps moving in Safari too.
    var cring = h("div", { class: "ai-sl__cring" });
    var cframe = lime(null, "ai-sl__cframe");
    cring.appendChild(cframe);
    // Trimmed to the action itself, so a reaction starts the instant the client taps.
    var CLIP = { point: "point", think: "think", thumbs: "thumbs", cheer: "cheer", wave: "loop" };
    var IDLE = { think: 1, wave: 1 };
    var power = h("div", { class: "ai-sl__power" });
    power.innerHTML = '<p class="ai-sl__pw-h">Campaign power</p><p class="ai-sl__pw-n"><b>0</b><small> / ' + 1000 + '</small></p>' +
      '<div class="ai-sl__pw-bar"><i></i></div><p class="ai-sl__pw-lvl">Draft</p>';
    coach.appendChild(cring); coach.appendChild(power);
    var main = h("div", { class: "ai-sl__main" });
    main.appendChild(head); main.appendChild(stage);
    run.appendChild(coach); run.appendChild(main);
    card.appendChild(intro); card.appendChild(run);
    host.appendChild(card);

    var qs = null, byId = {}, answers = {}, step = 0, busy = false, last = null, srcRes = null;
    // Tour demo only: skip the six taps and go straight to the director's desk.
    if (window.hvDemo) HV.aiDemo = function (ans, name) { answers = ans || {}; card.classList.add("is-open"); intro.hidden = true; run.hidden = false; go(name); };

    /* -- the game layer: coach animations and campaign power -- */
    // The coach: idle poses loop; reactions (thumbs, cheer, point) play once, in full, then hand
    // over to whatever is waiting, so a tap is always answered before the next pose.
    var coachTimer = null, reacting = false, queued = null;
    function coachShow(kind, loop, onEnd, then) {
      if (loop) cframe.loop(CLIP[kind]);
      else cframe.react(CLIP[kind], CLIP[then] || "think", onEnd);
    }
    function coachPlay(kind, then) {
      if (reduce) return;
      clearTimeout(coachTimer);
      if (IDLE[kind]) { reacting = false; queued = null; coachShow(kind, true); return; }
      reacting = true; queued = then || "think";
      cring.classList.remove("is-bump"); void cring.offsetWidth; cring.classList.add("is-bump");
      var done = false;
      coachShow(kind, false, function () {
        if (done) return; done = true; clearTimeout(coachTimer);
        reacting = false;
        var next = queued; queued = null;
        if (next === "point") coachPlay("point", "think"); else coachPlay(next || "think");
      }, IDLE[queued] ? queued : "think");
    }
    // A new question asks for a point, unless the coach is still celebrating: then it waits its turn.
    function coachCue(kind) { if (reacting) queued = kind; else coachPlay(kind, "think"); }
    function coachSay(text) {
      if (reduce) return;
      var b = h("span", { class: "ai-sl__say" }, text);
      cring.parentNode.appendChild(b); setTimeout(function () { b.remove(); }, 1500);
    }
    // A complete brief is worth exactly 1000: every answered question counts in full,
    // whatever was picked (one platform or three, "not decided yet" included).
    var POINTS = { goal: 150, platforms: 150, market: 150, category: 250, budget: 150, count: 150 };
    var LEVELS = [[0, "Draft"], [250, "Focused"], [500, "Sharp"], [800, "Ready to launch"]];
    function scoreOf(id) {
      var v = answers[id];
      if (v == null || (Array.isArray(v) && !v.length)) return 0;
      return POINTS[id] || 0;
    }
    function powerNow() { return AI_STEPS.reduce(function (t, s) { return t + scoreOf(s[0]); }, 0); }
    function levelOf(n) { var l = LEVELS[0][1]; LEVELS.forEach(function (x) { if (n >= x[0]) l = x[1]; }); return l; }
    var shown = 0;
    function paintPower(gain) {
      var n = Math.min(1000, powerNow()), before = levelOf(shown);
      power.querySelector("b").textContent = n;
      power.querySelector(".ai-sl__pw-bar i").style.width = (n / 10) + "%";
      var lvl = levelOf(n);
      power.querySelector(".ai-sl__pw-lvl").textContent = lvl;
      var leveled = !!(gain && lvl !== before);
      if (leveled) {
        var up = h("span", { class: "ai-sl__lvlup" }, "Level up · " + lvl);
        power.appendChild(up); setTimeout(function () { up.remove(); }, 1800);
      }
      if (gain && n > shown) { power.classList.remove("is-gain"); void power.offsetWidth; power.classList.add("is-gain"); }
      shown = n;
      return leveled;
    }
    // Every answer gets a reaction: a thumbs-up and the points, or a cheer on a level-up.
    function reward(pts) {
      var leveled = paintPower(true);
      coachSay(leveled ? "Level up!" : "+" + pts);
      coachPlay(leveled ? "cheer" : "thumbs", "think");
    }

    function setTrack(at, done) {
      Array.prototype.forEach.call(track.querySelectorAll(".ai-sl__node"), function (n, i) {
        n.classList.toggle("is-done", i < at || !!done);
        n.classList.toggle("is-now", i === at && !done);
      });
      var pct = done ? 100 : Math.round(at / (AI_STEPS.length - 1) * 100);
      fill.style.setProperty("--p", pct + "%");
      level.innerHTML = done ? "<b>Brief</b> complete" : "<b>Brief " + Math.min(at + 1, AI_STEPS.length) + "</b> / " + AI_STEPS.length;
    }
    function open() {
      card.classList.add("is-open"); intro.hidden = true; run.hidden = false; run.classList.remove("is-staging");
      shown = 0;
      loadQuestions().then(function (list) {
        qs = list; byId = {}; qs.forEach(function (q) { byId[q.id] = q; });
        ask(0);
      });
    }
    function close() {
      card.classList.remove("is-open"); run.hidden = true; intro.hidden = false;
    }
    start.addEventListener("click", function () { answers = profileAnswers(); srcRes = null; open(); });
    // From a link or a file: Helvy fills the six answers, the client lands on the review to check them.
    function fromSource(which) {
      card.classList.add("is-open"); intro.hidden = true; run.hidden = false; run.classList.remove("is-staging");
      shown = 0; setTrack(0); paintPower(false); coachCue("point");
      loadQuestions().then(function (list) {
        qs = list; byId = {}; qs.forEach(function (q) { byId[q.id] = q; });
        var p = h("div", { class: "ai-sl__q ai-sl__src" });
        p.appendChild(h("p", { class: "ai-sl__ask" }, "Start from what you have"));
        p.appendChild(h("p", { class: "ai-sl__hint" }, "A product page or your brief. Helvy fills the brief, you check it."));
        var bs = HV.briefSource({ dark: true, onUse: function (got, res) {
          answers = Object.assign(profileAnswers(), got); srcRes = res;
          review();
        } });
        p.appendChild(bs);
        p.appendChild(h("div", { class: "ai-sl__nav" }, h("button", { class: "ai-sl__back", type: "button", onclick: function () { answers = profileAnswers(); srcRes = null; ask(0); } }, "Answer the questions instead")));
        swap(p);
        var b = bs.querySelectorAll(".bs__opt")[which === "file" ? 1 : 0];
        if (b) b.click();
      });
    }
    altLink.addEventListener("click", function () { fromSource("link"); });
    altFile.addEventListener("click", function () { fromSource("file"); });
    quit.addEventListener("click", close);

    function swap(node) {
      stage.innerHTML = "";
      node.classList.add("ai-sl__panel");
      stage.appendChild(node);
      var f = node.querySelector("button, input");
      if (f) f.focus({ preventScroll: true });
    }
    function ask(i) {
      step = i; setTrack(i); paintPower(false);
      coachCue("point");
      var id = AI_STEPS[i][0], q = byId[id];
      if (!q) return i + 1 < AI_STEPS.length ? ask(i + 1) : review();
      // The goal takes several (fix batch 4, as the selection objective does): stored as a list,
      // scored on the server as "Awareness+Engagement".
      var multiGoal = !!q.multi_ok;
      var many = q.type === "many" || multiGoal;
      if (multiGoal && q.type !== "many") q = Object.assign({}, q, { type: "many" });
      var picked = Array.isArray(answers[id]) ? answers[id].slice() : answers[id] ? [answers[id]] : [];
      var p = h("div", { class: "ai-sl__q" });
      p.appendChild(h("p", { class: "ai-sl__ask" }, multiGoal ? "What are the campaign’s goals?" : q.label));
      p.appendChild(h("p", { class: "ai-sl__hint" }, multiGoal ? "Pick one or more, then Next" : many ? "Pick any, then Next" : "Tap one"));
      var opts = h("div", { class: "ai-sl__opts" + (q.options.length > 6 ? " ai-sl__opts--many" : "") });
      q.options.forEach(function (o) {
        var on = many ? picked.indexOf(o.value) > -1 : answers[id] === o.value;
        var b = h("button", { class: "ai-sl__opt", type: "button", "aria-pressed": String(on) }, o.label);
        b.addEventListener("click", function () {
          if (!many) { answers[id] = o.value; b.setAttribute("aria-pressed", "true"); pop(b, scoreOf(id)); reward(scoreOf(id)); setTimeout(function () { next(); }, reduce ? 0 : 750); return; }
          var k = picked.indexOf(o.value);
          if (o.value === "any") picked = k > -1 ? [] : ["any"];
          else { picked = picked.filter(function (v) { return v !== "any"; }); if (k > -1) picked.splice(picked.indexOf(o.value), 1); else picked.push(o.value); }
          Array.prototype.forEach.call(opts.children, function (x, xi) { if (q.options[xi]) x.setAttribute("aria-pressed", String(picked.indexOf(q.options[xi].value) > -1)); });
          if (o.value === "any" && oIn) { oIn.value = ""; oIn.hidden = true; oBtn.setAttribute("aria-pressed", "false"); }
          nextBtn.disabled = !picked.length;
        });
        opts.appendChild(b);
      });
      p.appendChild(opts);
      // "Other": the client's own answer when no option fits (e.g. 40 creators).
      var oBtn = null, oIn = null, oNext = null;
      if (q.other) {
        var own = otherOf(answers[id]);
        oBtn = h("button", { class: "ai-sl__opt", type: "button", "aria-pressed": String(!!own) }, "Other");
        oIn = otherInput(q, own, function (txt) {
          oBtn.setAttribute("aria-pressed", String(!!txt.trim()));
          if (many) {
            picked = withOther(q, picked, txt) || [];
            Array.prototype.forEach.call(opts.children, function (x, xi) { if (q.options[xi]) x.setAttribute("aria-pressed", String(picked.indexOf(q.options[xi].value) > -1)); });
            nextBtn.disabled = !picked.length;
          } else {
            Array.prototype.forEach.call(opts.children, function (x, xi) { if (q.options[xi]) x.setAttribute("aria-pressed", "false"); });
            oNext.disabled = !txt.trim();
          }
        }, function () { (many ? nextBtn : oNext).click(); });
        oIn.hidden = !own;
        oBtn.addEventListener("click", function () {
          oIn.hidden = false; oIn.focus();
          if (!many) oNext.hidden = false;
        });
        opts.appendChild(oBtn);
        p.appendChild(oIn);
        if (!many) {
          oNext = h("button", { class: "ai-sl__next", type: "button", onclick: function () {
            var nv = withOther(q, null, oIn.value);
            if (!nv) return;
            answers[id] = nv; pop(oNext, scoreOf(id)); reward(scoreOf(id)); setTimeout(next, reduce ? 0 : 750);
          } }, "Next");
          oNext.hidden = !own; oNext.disabled = !own;
        }
      }
      var nav = h("div", { class: "ai-sl__nav" });
      if (i > 0) nav.appendChild(h("button", { class: "ai-sl__back", type: "button", onclick: function () { ask(i - 1); } }, "Back"));
      if (!q.required && !many) nav.appendChild(h("button", { class: "ai-sl__skip", type: "button", onclick: function () { delete answers[id]; next(); } }, "Skip"));
      var nextBtn = h("button", { class: "ai-sl__next", type: "button", onclick: function () { answers[id] = picked.slice(); pop(nextBtn, scoreOf(id)); reward(scoreOf(id)); setTimeout(next, reduce ? 0 : 750); } }, "Next");
      if (many) { nextBtn.disabled = !picked.length; nav.appendChild(nextBtn); }
      if (oNext) nav.appendChild(oNext);
      p.appendChild(nav);
      swap(p);
      function next() { if (i + 1 < AI_STEPS.length) ask(i + 1); else review(); }
    }
    function pop(el, pts) {
      if (reduce) return;
      var s = h("span", { class: "ai-sl__plus", "aria-hidden": "true" }, "+" + (pts || 100));
      el.appendChild(s); setTimeout(function () { s.remove(); }, 700);
    }
    function label(id) {
      var v = answers[id], q = byId[id];
      if (v == null || (Array.isArray(v) && !v.length)) return "Any";
      return (Array.isArray(v) ? v : [v]).map(function (x) { return optionLabel(q, x); }).join(", ");
    }
    function nameFor() {
      var cat = Array.isArray(answers.category) && answers.category[0] && answers.category[0] !== "any" ? optionLabel(byId.category, answers.category[0]).split(/ [&\/] /)[0] : "Creators";
      var goals = (Array.isArray(answers.goal) ? answers.goal : [answers.goal]).map(function (g) { return AI_GOAL[g]; }).filter(Boolean);
      return [cat, AI_MARKET[answers.market] || "", goals.join(" + ")].filter(Boolean).join(" · ");
    }
    function costLine() {
      var c = (ME && ME.costs) || { brief: 5, search: 0 };
      if (ME && ME.kind === "admin") return "Admin preview · free";
      if (ME && ME.ai_free) return "Free with your active campaign · includes AI reasons";
      if (ME && ME.ai && c.brief && (ME.credits == null || ME.credits >= c.brief)) return c.brief + " credits · includes AI reasons";
      return c.search ? c.search + " credits" : "Free";
    }
    function review() {
      setTrack(AI_STEPS.length, true);
      var p = h("div", { class: "ai-sl__review" });
      var ticket = h("div", { class: "ai-sl__ticket" });
      ticket.appendChild(h("p", { class: "ai-sl__tk-h" }, "Campaign brief"));
      paintPower(true); coachSay("Ready!"); coachPlay("cheer", "wave");
      var pw = Math.min(1000, powerNow());
      ticket.appendChild(h("span", { class: "ai-sl__tk-score" }, h("b", null, String(pw)), h("small", null, levelOf(pw))));
      var nameIn = h("input", { class: "ai-sl__name", type: "text", maxlength: "80", value: nameFor(), "aria-label": "Name this shortlist" });
      ticket.appendChild(nameIn);
      var dl = h("dl", { class: "ai-sl__rows" });
      AI_STEPS.forEach(function (s, i) {
        var row = h("div", { class: "ai-sl__row" });
        row.appendChild(h("dt", null, s[1]));
        row.appendChild(h("dd", null, label(s[0])));
        var edit = h("button", { class: "ai-sl__edit", type: "button", "aria-label": "Change " + s[1] }, "Change");
        edit.addEventListener("click", function () { ask(i); });
        row.appendChild(edit);
        dl.appendChild(row);
      });
      ticket.appendChild(dl);
      p.appendChild(ticket);
      var side = h("div", { class: "ai-sl__go" });
      side.appendChild(h("p", { class: "ai-sl__ask" }, "Ready when you are."));
      if (srcRes) {
        (srcRes.flags || []).filter(function (f) { return f.kind !== "licence"; }).slice(0, 1).forEach(function (f) {
          side.appendChild(h("div", { class: "bs-flag bs-flag--dark bs-flag--slim" }, h("span", { class: "bs-flag__ic", html: icon("flag") }), h("p", null, h("b", null, f.title + ". "), f.text)));
        });
        var tls = timingLine(srcRes.timing, { short: true, dark: true });
        if (tls) side.appendChild(tls);
      }
      side.appendChild(h("p", { class: "ai-sl__hint" }, "We score every creator on each platform, fit your budget and explain each pick."));
      var build = h("button", { class: "ai-sl__build", type: "button" }, "Build my shortlist");
      var cl = costLine();
      // A price in credits is the orange coin chip; "Free" and the admin preview stay plain words.
      build.appendChild(/^\d+ credits/.test(cl) ? h("small", null, h("span", { class: "hv-cost", html: icon("coin") + cl.split(" · ")[0] }),
                                                        cl.indexOf(" · ") > 0 ? " " + cl.split(" · ").slice(1).join(" · ") : null)
                                                   : h("small", null, cl));
      build.addEventListener("click", function () { if (!busy) go(nameIn.value.trim() || nameFor()); });
      side.appendChild(build);
      p.appendChild(side);
      swap(p);
    }

    /* -- the wait, staged -- */
    var STAGES = ["Reading your brief", "Flipping through creators", "Scoring fit", "Approving your picks"];
    function go(name) {
      busy = true;
      run.classList.add("is-staging"); clearTimeout(coachTimer);
      [].slice.call(cring.querySelectorAll("video")).forEach(function (o) { try { o.pause(); } catch (e) { /* none */ } });
      cframe.reset();
      var p = h("div", { class: "ai-sl__wait", role: "status", "aria-live": "polite" });
      var scene = h("div", { class: "ai-sl__scene", "aria-hidden": "true" });
      scene.innerHTML = '<div class="ai-sl__orbit ai-sl__orbit--a"><i></i><i></i><i></i></div>' +
        '<div class="ai-sl__orbit ai-sl__orbit--b"><i></i><i></i></div>' +
        '<div class="ai-sl__orbit ai-sl__orbit--c">' + ["Instagram", "TikTok", "Snapchat"].map(function (pl) {
          var ic = window.HV_ICONS && window.HV_ICONS.icons && window.HV_ICONS.icons[pl];
          return '<b class="ai-sl__mark ai-sl__mark--' + pl.toLowerCase() + '">' + (ic || '<em>' + AI_SHORT[pl] + "</em>") + "</b>";
        }).join("") + "</div>" +
        '<div class="ai-sl__lens"></div>' +
        '<span class="ai-sl__spark ai-sl__spark--1"></span><span class="ai-sl__spark ai-sl__spark--2"></span><span class="ai-sl__spark ai-sl__spark--3"></span>';
      // Helvy scouts with his camera while the steps tick off (the scan clip, looping). Created in
      // the Build tap, so the browser lets it play.
      scene.querySelector(".ai-sl__lens").appendChild(lime("scan"));
      p.appendChild(scene);
      var side = h("div", { class: "ai-sl__steps" });
      side.appendChild(h("p", { class: "ai-sl__ask" }, "Building “" + name + "”"));
      var list = h("ol", { class: "ai-sl__list" });
      var counter = h("b", { class: "ai-sl__count" }, "0%");
      STAGES.forEach(function (t, i) {
        var li = h("li", { class: "ai-sl__st" }, h("span", { class: "ai-sl__st-dot", "aria-hidden": "true" }), h("span", null, t));
        if (i === 1) li.appendChild(counter);
        list.appendChild(li);
      });
      side.appendChild(list);
      var bar = h("div", { class: "ai-sl__bar", "aria-hidden": "true" }, h("i"));
      side.appendChild(bar);
      p.appendChild(side);
      swap(p);
      var items = list.children, total = Math.max(roster, 1), t0 = Date.now(), done = false, at = 0;
      function mark(i) {
        Array.prototype.forEach.call(items, function (li, k) { li.classList.toggle("is-done", k < i); li.classList.toggle("is-now", k === i); });
        at = i;
      }
      mark(0);
      var timer = setInterval(function () {
        var s = (Date.now() - t0) / 1000;
        if (!done) {
          if (s > 1.2 && at < 1) mark(1);
          if (at === 1) counter.textContent = Math.round(100 * Math.min(1, (s - 1.2) / 4)) + "%";   // progress, never the roster size
          if (s > 5.4 && at < 2) mark(2);
          if (s > 7.4 && at < 3) mark(3);
          bar.firstChild.style.width = Math.min(92, 8 + s * 4) + "%";
        }
      }, 120);
      api("POST", "/api/brief/run", { answers: answers, name: name }).then(function (r) {
        done = true; clearInterval(timer); busy = false;
        if (!r.b.ok || r.b.empty || !(r.b.picks || []).length) {
          var err = h("div", { class: "ai-sl__q" }, h("p", { class: "ai-sl__ask" }, r.b.empty ? "No creators matched that brief." : "That didn't work."),
            h("p", { class: "ai-sl__hint" }, (r.b.message || "Nothing was charged. Try again in a moment.")));
          err.appendChild(h("div", { class: "ai-sl__nav" }, h("button", { class: "ai-sl__next", type: "button", onclick: review }, "Change the brief")));
          swap(err); return;
        }
        counter.textContent = "100%";
        mark(STAGES.length); bar.firstChild.style.width = "100%";
        setCredits(r.b.credits);
        last = r.b;
        setTimeout(function () { celebrate(r.b, name); }, reduce ? 0 : 500);
      });
    }
    function celebrate(res, name) {
      var p = h("div", { class: "ai-sl__done" });
      var burst = h("div", { class: "ai-sl__burst", "aria-hidden": "true" });
      for (var i = 0; i < 18; i++) { var c = h("i"); c.style.setProperty("--a", (i * 20) + "deg"); c.style.setProperty("--d", (60 + (i % 3) * 26) + "px"); burst.appendChild(c); }
      p.appendChild(burst);
      if (!reduce) { var cheer = lime(null); p.appendChild(h("div", { class: "ai-sl__cheer" }, cheer)); cheer.react("celebrate", "loop"); }
      p.appendChild(h("p", { class: "ai-sl__big" }, h("b", null, String(res.picks.length)), " creators picked"));
      p.appendChild(h("p", { class: "ai-sl__hint" }, "Best fit first, scored per platform. They're ticked in your tray: add or remove anyone, then save."));
      swap(p);
      showResult(res, name);
      setTimeout(function () {
        close();
        var bar = $("ai-result");
        if (bar) bar.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
      }, reduce ? 300 : 1900);
    }

    /* -- the grid, narrowed to the picks -- */
    function bandOf(n) { return n >= 80 ? "g" : n >= 60 ? "l" : n >= 40 ? "a" : "r"; }
    function clearResult(keep) {
      var grid = $("cat-grid");
      if (grid) grid.classList.remove("ai-on");
      // The catalogue served in batches showed only the picks: back to the reader's own view.
      if (keep !== true && window.hvCatalogue && window.hvCatalogue.server) window.hvCatalogue.unpin();
      Array.prototype.forEach.call(document.querySelectorAll(".cat-card.ai-pick, .cat-card.ai-out"), function (c) {
        c.classList.remove("ai-pick", "ai-out"); c.style.order = "";
        var x = c.querySelector(".ai-badges"); if (x) x.remove();
      });
      var bar = $("ai-result"); if (bar) bar.remove();
      document.body.classList.remove("ai-mode");
      var sub = $("results-sub"); if (sub) sub.textContent = "Every creator that matches your filters. Tick the ones you want.";
    }
    // The catalogue is served in batches, so the picks may not be on the page yet: it is asked
    // to show exactly them (fetched by code, in rank order), then they are marked as before.
    function showResult(res, name) {
      if (window.hvCatalogue && window.hvCatalogue.server) {
        clearResult(true);
        window.hvCatalogue.pin(codesOf(res.picks)).then(function () { paintResult(res, name); });
        return;
      }
      paintResult(res, name);
    }
    function paintResult(res, name) {
      clearResult(true);
      var grid = $("cat-grid");
      if (!grid) return;
      var rank = {}, why = {};
      res.picks.forEach(function (p, i) { rank[p.code] = i + 1; why[p.code] = p.why || ""; });
      grid.classList.add("ai-on");
      document.body.classList.add("ai-mode");
      Array.prototype.forEach.call(grid.querySelectorAll(".cat-card[data-code]"), function (c) {
        var code = c.getAttribute("data-code"), n = rank[code];
        if (!n) { c.classList.add("ai-out"); return; }
        c.classList.add("ai-pick"); c.style.order = String(n);
        var media = c.querySelector(".cat-card__media") || c;
        var box = h("div", { class: "ai-badges", "data-noselect": "" });
        box.appendChild(h("span", { class: "ai-rank", title: why[code] || "" }, "#" + n));
        var ps = (res.platform_scores || {})[code] || {};
        var plats = Object.keys(ps);
        if (!plats.length) { var only = res.picks[n - 1]; if (only && only.score != null) { ps = { Match: only.score }; plats = ["Match"]; } }
        plats.sort(function (a, b) { return ps[b] - ps[a]; }).forEach(function (pl) {
          var s = h("span", { class: "ai-pscore ai-pscore--" + bandOf(ps[pl]), title: pl + " match " + ps[pl] + " / 100" });
          s.appendChild(h("small", null, AI_SHORT[pl] || pl)); s.appendChild(h("b", null, ps[pl] + "%"));
          box.appendChild(s);
        });
        media.appendChild(box);
        if (c.getAttribute("aria-pressed") !== "true") c.click();
      });
      var bar = h("div", { id: "ai-result", class: "ai-result" });
      var txt = h("div", { class: "ai-result__txt" });
      txt.appendChild(h("p", { class: "ai-result__name" }, name));
      txt.appendChild(h("p", { class: "ai-result__sum" }, res.summary || (res.picks.length + " creators match your brief, best fit first.")));
      var tlb = timingLine(res.timing, { short: true });
      if (tlb) txt.appendChild(tlb);
      bar.appendChild(txt);
      var acts = h("div", { class: "ai-result__acts" });
      var openSel = h("a", { class: "ai-result__btn ai-result__btn--lime", href: ROOT + "selection/#s=" + encodeURIComponent(res.token) }, "Open as selection");
      // The client names the selection before it opens (prefilled with the brief's name).
      openSel.addEventListener("click", function (e) {
        e.preventDefault();
        if (bar.querySelector(".pt-namer")) return;
        var current = res.name || name;
        txt.appendChild(nameForm(current, "Save and open", function (v) {
          renameThenOpen(res.token, codesOf(res.picks), current, v);
        }));
      });
      acts.appendChild(openSel);
      acts.appendChild(h("a", { class: "ai-result__btn", href: ROOT + "selection/#s=" + encodeURIComponent(res.token) + "&quote=1" }, "Request a quote"));
      acts.appendChild(h("button", { class: "ai-result__btn ai-result__btn--ghost", type: "button", onclick: clearResult }, "Show all creators"));
      acts.appendChild(h("button", { class: "ai-result__btn ai-result__btn--ghost", type: "button", onclick: function () { clearResult(); answers = {}; open(); card.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" }); } }, "New brief"));
      bar.appendChild(acts);
      grid.parentNode.insertBefore(bar, grid);
      var sub = $("results-sub");
      if (sub) sub.textContent = "AI shortlist: " + res.picks.length + " creators, best fit first. Show all creators to go back to the full roster.";
    }
  }

  /* ------------------------------------------------------- licence stamps */
  // Advertising licences on the creator cards: Saudi Mawthooq, the UAE
  // Advertiser Permit, Egypt's SCMR licence. "In bio" is the creator's own
  // statement; "Verified" means HelloVoice checked it on the regulator's portal.
  var LIC = null, licObserver = null;
  var LIC_SHORT = { SA: "Mawthooq", AE: "UAE permit", EG: "Egypt licence" };
  function paintLicences() {
    if (!LIC) return;
    Array.prototype.forEach.call(document.querySelectorAll(".cat-card[data-code]"), function (card) {
      var list = LIC[card.getAttribute("data-code")];
      var box = card.querySelector(".lic-stamps");
      if (!list || !list.length) { if (box) box.remove(); return; }
      var sig = JSON.stringify(list);
      if (box && box.getAttribute("data-sig") === sig) return;
      if (!box) { box = h("div", { class: "lic-stamps", "data-noselect": "" }); (card.querySelector(".cat-card__media") || card).appendChild(box); }
      box.setAttribute("data-sig", sig);
      box.innerHTML = "";
      list.forEach(function (l) {
        // One white 'Verified' stamp for everyone with the licence.
        var st = h("span", { class: "lic-stamp", tabindex: "0",
          title: l.name + (l.number ? " no. " + l.number : ""),
          "aria-label": (LIC_SHORT[l.country] || l.name) + " licence, verified" });
        st.appendChild(h("b", null, LIC_SHORT[l.country] || l.name));
        st.appendChild(h("small", null, "Verified ✓"));
        box.appendChild(st);
      });
    });
  }
  // The licence filter: "License:" and two chips, Mawthooq (KSA) and UAE.
  // Pick one, both (either licence passes) or none (everyone). It works over
  // the catalogue's own filters: a card has to pass both. No counts are shown.
  var licWant = [];
  function licMatch(code) {
    if (!licWant.length) return true;
    var list = (LIC && LIC[code]) || [];
    return list.some(function (l) { return licWant.indexOf(l.country) !== -1; });
  }
  function applyLicFilter() {
    // The catalogue served in batches filters on the server; the selection page holds all its cards.
    if ((window.hvCatalogue && window.hvCatalogue.server)) { window.hvCatalogue.filter("lic", licWant.slice()); return; }
    Array.prototype.forEach.call(document.querySelectorAll(".cat-card[data-code]"), function (card) {
      card.classList.toggle("lic-out", !licMatch(card.getAttribute("data-code")));
    });
  }
  function mountLicFilter(tries) {
    if (document.body.getAttribute("data-page") !== "catalogue" || $("lic-filter")) return;
    var bar = document.querySelector(".cat-controls .cat-bar");
    // The licences can arrive before the catalogue has drawn its filter bar: wait for it.
    if (!bar) { if ((tries || 0) < 80) setTimeout(function () { mountLicFilter((tries || 0) + 1); }, 250); return; }
    if ((window.hvCatalogue && window.hvCatalogue.server)) licWant = (window.hvCatalogue.get("lic") || []).slice();     // the view the reader came back to
    var box = h("div", { id: "lic-filter", class: "lic-filter", role: "group", "aria-label": "License" });
    box.appendChild(h("span", { class: "lic-filter__label" }, "License"));
    [["SA", "Mawthooq license"], ["AE", "UAE license"]].forEach(function (o) {
      var chip = h("button", { class: "lic-chip", type: "button", "aria-pressed": String(licWant.indexOf(o[0]) !== -1), "data-lic": o[0] }, o[1]);
      chip.addEventListener("click", function () {
        var i = licWant.indexOf(o[0]);
        if (i === -1) licWant.push(o[0]); else licWant.splice(i, 1);
        chip.setAttribute("aria-pressed", String(i === -1));
        applyLicFilter();
      });
      box.appendChild(chip);
    });
    bar.parentNode.insertBefore(box, bar.nextSibling);
  }
  function mountLicences() {
    var page = document.body.getAttribute("data-page");
    if (page !== "catalogue" && page !== "selection") return;
    api("GET", "/api/licences").then(function (r) {
      if (!r.b || !r.b.ok) return;
      LIC = r.b.licences || {};
      paintLicences();
      mountLicFilter();
      if (!licObserver && "MutationObserver" in window) {
        var t = null, app = document.getElementById("cat-grid") || document.body;
        licObserver = new MutationObserver(function () { clearTimeout(t); t = setTimeout(function () { paintLicences(); if (licWant.length && !(window.hvCatalogue && window.hvCatalogue.server)) applyLicFilter(); }, 150); });
        licObserver.observe(app, { childList: true, subtree: true });
      }
    });
  }

  /* ------------------------------------------------------------------ boot */

  function boot() {
    api("GET", "/api/me").then(function (r) {
      if (r.b && r.b.signed_in) {
        ME = r.b; HV.me = ME; mountDock(); mountVoice(); mountAiCard(); mountLicences();
        try { document.dispatchEvent(new CustomEvent("hv:me", { detail: ME })); } catch (e) { /* old browser */ }
        var m = /[#&]s=([^&]+)/.exec(location.hash || "");
        // (The selection page asks for a missing objective in its own bar: catalogue.js renderObjective.)
        // Arriving from the AI shortlist's "Request a quote": open the quote form straight away.
        if (document.body.getAttribute("data-page") === "selection" && /[#&]quote=1/.test(location.hash)) setTimeout(function () {
          var q = document.getElementById("cat-request") || document.getElementById("cat-request-2"); if (q) q.click();
        }, 1600);
        return;
      }
      // Only replace the access-code gate once the server can actually send the email.
      if (r.b && r.b.email_signin) enhanceGate();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
  // A passcode typed into the gate unlocks without a reload, so look again
  // then: the account circle and the assistant appear straight away.
  document.addEventListener("cat:unlocked", function () { if (!ME) boot(); });
})();
