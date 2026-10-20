/* HELVi Connect: "How HELVi works" (portal item 179, /welcome/).
 *
 * The onboarding film is lazy: the <video> has no src and preload="none" until the visitor
 * presses play or picks a chapter, so the page costs only its poster. Chapters are the notes
 * on what the portal does; once the real film is in, each one also jumps to its moment.
 *
 * The film (Bido, 2026-10-20, 5:45) lives ONLY on the server at assets/welcome/onboarding-film.mp4:
 * it shows real creators, and this repo is public, so it is gitignored. Chapter times (t, seconds)
 * match that cut; re-time them if the film is re-edited.
 */
(function () {
  "use strict";
  var TIMED = true;
  var CHAPTERS = [
    { t: 0,   name: "Meet HELVi",               note: "Why finding the right creators is hard, and the portal that fixes it." },
    { t: 49,  name: "One portal, five steps",   note: "Browse, shortlist, score, quote and track: from search to a live campaign." },
    { t: 66,  name: "Browse and filter",        note: "Vetted creators across every platform. Filter by tier, platform, location, interest and licence." },
    { t: 96,  name: "Look closer at a creator", note: "Followers by platform, recent posts and the audience behind them." },
    { t: 132, name: "Build a shortlist with AI", note: "Answer a few questions and Helvi picks the creators that fit your brief." },
    { t: 166, name: "Ask Helvi",                note: "Chat with Helvi to find creators, change your selection or ask for a quote." },
    { t: 180, name: "Your selection",           note: "Approve creators, add more like them, and get content ideas for each one." },
    { t: 204, name: "Market intelligence",      note: "See which creators work with your competitors, and the views they get." },
    { t: 240, name: "Request a quote",          note: "Happy with the selection? Send it for one clear quote." },
    { t: 252, name: "Track results",            note: "Every campaign gets its own dashboard: posts, views, engagement and top creators." },
    { t: 282, name: "What people say",          note: "Comments read for mood and buying questions, and the full report against your goals." }
  ];

  var video = document.getElementById("wl-video");
  var film = document.getElementById("wl-film");
  var play = document.getElementById("wl-play");
  var err = document.getElementById("wl-err");
  var list = document.getElementById("wl-chaps");
  if (!video || !list) return;

  function clock(s) { s = Math.max(0, Math.round(s)); return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2); }
  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }

  /* -- the chapter list: numbered because the order is the story -- */
  var buttons = [];
  CHAPTERS.forEach(function (c, i) {
    var li = el("li", "wl-chap");
    var b = el("button", "wl-chap__b");
    b.type = "button";
    b.appendChild(el("span", "wl-chap__n", String(i + 1)));
    var txt = el("span", "wl-chap__txt");
    var top = el("span", "wl-chap__top");
    top.appendChild(el("b", "wl-chap__name", c.name));
    if (TIMED) top.appendChild(el("span", "wl-chap__time", clock(c.t)));
    txt.appendChild(top);
    txt.appendChild(el("span", "wl-chap__note", c.note));
    b.appendChild(txt);
    b.setAttribute("aria-label", c.name + (TIMED ? ", from " + clock(c.t) : "") + ". " + c.note);
    b.addEventListener("click", function () { start(TIMED ? c.t : 0); });
    li.appendChild(b);
    list.appendChild(li);
    buttons.push(b);
  });

  /* -- loading and playing -- */
  var loaded = false, pendingSeek = null;
  function load() {
    if (loaded) return;
    loaded = true;
    film.classList.add("is-loading");
    video.src = video.getAttribute("data-src");
    video.preload = "auto";
    video.load();
  }
  function start(t) {
    err.hidden = true;
    film.classList.remove("has-error");
    film.classList.add("is-on");
    video.controls = true;
    if (!loaded) { pendingSeek = t; load(); }
    else seek(t);
    var p = video.play();
    if (p && p.catch) p.catch(function () { /* autoplay refused: the controls are there */ });
    try { video.focus({ preventScroll: true }); } catch (e) { /* old browser */ }
  }
  function seek(t) {
    if (t == null) return;
    if (video.readyState >= 1) { if (!video.duration || t < video.duration) video.currentTime = t; pendingSeek = null; }
    else pendingSeek = t;
  }
  video.addEventListener("loadedmetadata", function () { if (pendingSeek != null) seek(pendingSeek); });
  video.addEventListener("playing", function () { film.classList.remove("is-loading"); });
  video.addEventListener("canplay", function () { film.classList.remove("is-loading"); });
  video.addEventListener("error", function () {
    film.classList.remove("is-loading", "is-on");
    film.classList.add("has-error");
    video.controls = false;
    loaded = false;
    video.removeAttribute("src");
    err.hidden = false;
  });
  play.addEventListener("click", function () { start(null); });
  var retry = document.getElementById("wl-retry");
  if (retry) retry.addEventListener("click", function () { start(null); });

  /* -- the chapter on screen, kept lit as the film plays -- */
  var cur = -1;
  function mark() {
    var i = -1;
    if (TIMED) for (var k = 0; k < CHAPTERS.length; k++) if (video.currentTime + 0.25 >= CHAPTERS[k].t) i = k;
    if (i === cur) return;
    if (cur >= 0) { buttons[cur].classList.remove("is-now"); buttons[cur].removeAttribute("aria-current"); }
    cur = i;
    if (cur >= 0) { buttons[cur].classList.add("is-now"); buttons[cur].setAttribute("aria-current", "step"); }
  }
  video.addEventListener("timeupdate", mark);
  video.addEventListener("seeked", mark);
  video.addEventListener("ended", function () { film.classList.add("is-ended"); });
  video.addEventListener("play", function () { film.classList.remove("is-ended"); });

  // Leaving the page or the app going to the background: the film pauses rather than plays to no one.
  document.addEventListener("visibilitychange", function () { if (document.hidden && !video.paused) video.pause(); });
})();
