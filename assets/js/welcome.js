/* HELVi Connect: "How HELVi works" (portal item 179, /welcome/).
 *
 * The onboarding film is lazy: the <video> has no src and preload="none" until the visitor
 * presses play or picks a chapter, so the page costs only its poster. Chapters are the notes
 * on what the portal does; once the real film is in, each one also jumps to its moment.
 *
 * When the final film lands at assets/welcome/onboarding.mp4: set each chapter's start (t, in
 * seconds) and TIMED = true. Until then the chapters play the film from the start and show no
 * times, so a placeholder never promises a moment it does not have.
 */
(function () {
  "use strict";
  var TIMED = false;
  var CHAPTERS = [
    { t: 0,  name: "Meet HELVi",        note: "HelloVoice's creator portal, and Helvi, the assistant who works it with you." },
    { t: 10, name: "Brief Helvi",       note: "Type it, say it, or paste your product link. Helvi reads the brief and builds a shortlist of vetted creators." },
    { t: 24, name: "Browse and filter", note: "Platform, size, city, audience and licence. Every creator is checked by HelloVoice." },
    { t: 36, name: "Your shortlist",    note: "Approve or reject each creator, and Helvi finds a replacement in seconds." },
    { t: 50, name: "Full analysis",     note: "Real audience, authenticity, growth and brand history for your finalists, ready within one working day." },
    { t: 62, name: "Request a quote",   note: "Your account manager replies within one working day, right in your bell." },
    { t: 74, name: "Track results",     note: "Every post, its views and engagement, verdict first, updated every 24 hours." },
    { t: 87, name: "Take it with you",  note: "Selections, campaigns and credits live in your profile, and on your phone as the HELVi app." }
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
