/* Lets the account pill and the Helvi launcher be dragged anywhere on the page with the mouse (or a finger).
   A click still clicks: it only counts as a drag after the pointer has moved a few pixels. The spot is
   remembered in this browser. */
(function () {
  var KEY = "hv-pos:";
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function make(el, handle, key, after) {
    var saved = null;
    try { saved = JSON.parse(localStorage.getItem(KEY + key) || "null"); } catch (e) {}
    function place(x, y) {
      var r = el.getBoundingClientRect();
      x = clamp(x, 6, Math.max(6, window.innerWidth - r.width - 6));
      y = clamp(y, 6, Math.max(6, window.innerHeight - r.height - 6));
      el.style.left = x + "px"; el.style.top = y + "px"; el.style.right = "auto"; el.style.bottom = "auto";
      el.classList.add("hv-moved"); if (after) after();
    }
    if (saved && typeof saved.x === "number") place(saved.x, saved.y);
    var sx = 0, sy = 0, ox = 0, oy = 0, down = false, moved = false, id = null;
    handle.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      var r = el.getBoundingClientRect();
      id = e.pointerId; sx = e.clientX; sy = e.clientY; ox = r.left; oy = r.top; down = true; moved = false;
    });
    window.addEventListener("pointermove", function (e) {
      if (!down || e.pointerId !== id) return;
      var dx = e.clientX - sx, dy = e.clientY - sy;
      if (!moved && Math.abs(dx) + Math.abs(dy) < 6) return;
      if (!moved) { moved = true; el.classList.add("hv-dragging"); try { handle.setPointerCapture(id); } catch (_) {} }
      place(ox + dx, oy + dy); e.preventDefault();
    });
    function end(e) {
      if (!down || e.pointerId !== id) return;
      down = false;
      if (moved) {
        el.classList.remove("hv-dragging");
        var r = el.getBoundingClientRect();
        try { localStorage.setItem(KEY + key, JSON.stringify({ x: r.left, y: r.top })); } catch (_) {}
      }
    }
    window.addEventListener("pointerup", end); window.addEventListener("pointercancel", end);
    handle.addEventListener("click", function (e) { if (moved) { e.stopPropagation(); e.preventDefault(); moved = false; } }, true);
    // Double-click puts it back in its own place.
    handle.addEventListener("dblclick", function () {
      try { localStorage.removeItem(KEY + key); } catch (_) {}
      ["left", "top", "right", "bottom"].forEach(function (p) { el.style.removeProperty(p); });
      el.style.removeProperty("--hv-dx"); el.style.removeProperty("--hv-ph");
      el.classList.remove("hv-moved", "hv-at-left", "hv-at-top");
    });
    window.addEventListener("resize", function () { if (el.style.left) { var r = el.getBoundingClientRect(); place(r.left, r.top); } });
  }
  function scan() {
    var pill = document.getElementById("pt-dock");
    if (pill && pill.classList.contains("pt-dock--fixed") && !pill.__hvd) { pill.__hvd = 1; make(pill, pill, "pill"); }
    var bot = document.querySelector(".hv-voice"), l = bot && bot.querySelector(".hv-launch");
    if (bot && l && !bot.__hvd) { bot.__hvd = 1; botEl = bot; make(bot, l, "bot", fit); new MutationObserver(function () { if (bot.classList.contains("is-open")) fit(); }).observe(bot, { attributes: true, attributeFilter: ["class"] }); }
  }
  // The chat window opens on the side of the launcher that has room: right or left, above or below, kept on screen.
  var botEl = null;
  function fit() {
    var root = botEl; if (!root || !root.classList.contains("hv-moved")) return;
    var vw = window.innerWidth, vh = window.innerHeight;
    if (vw <= 560) { root.style.removeProperty("--hv-dx"); root.style.removeProperty("--hv-ph"); return; }     // full screen on phones
    var r = root.getBoundingClientRect(), left = r.left + r.width / 2 < vw / 2, top = r.top + r.height / 2 < vh / 2;
    root.classList.toggle("hv-at-left", left); root.classList.toggle("hv-at-top", top);
    var pw = Math.min(root.classList.contains("is-big") ? 640 : 392, vw - 24), dx = 0;
    if (left) dx = Math.min(0, vw - 12 - (r.left + pw)); else dx = Math.max(0, 12 - (r.right - pw));
    var avail = top ? vh - r.bottom - 14 - 16 : r.bottom - 98 - 16;
    root.style.setProperty("--hv-dx", Math.round(dx) + "px");
    root.style.setProperty("--hv-ph", Math.max(260, Math.min(root.classList.contains("is-big") ? 860 : 640, Math.round(avail))) + "px");
  }
  var st = document.createElement("style");
  st.textContent = ".hv-voice.hv-moved .hv-panel { height: var(--hv-ph, auto); right: calc(0px - var(--hv-dx, 0px)); transform-origin: 100% 100%; }"
    + ".hv-voice.hv-moved.hv-at-left .hv-panel { left: var(--hv-dx, 0px); right: auto; transform-origin: 0 100%; }"
    + ".hv-voice.hv-moved.hv-at-top .hv-panel { top: calc(100% + 14px); bottom: auto; transform-origin: 100% 0; }"
    + ".hv-voice.hv-moved.hv-at-top.hv-at-left .hv-panel { transform-origin: 0 0; }"
    + "@media (max-width: 560px) { .hv-voice.hv-moved .hv-panel { height: auto; left: auto; right: auto; top: auto; } }";
  document.head.appendChild(st);
  window.addEventListener("resize", fit);
  scan();
  new MutationObserver(scan).observe(document.documentElement, { childList: true, subtree: true });
})();
