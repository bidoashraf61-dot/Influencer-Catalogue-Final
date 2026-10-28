/* Trial share links (item 271): the strip a prospect sees on every page of the BlueHolding demo.

   Loaded by app.js (and market/) only when the hv_trial_on cookie is set by /admin/try/<token>.
   Shows who the trial is for and when it ends, opens a short "Talk to HelloVoice" form that lands in
   the admin Tenants inbox, and turns the trial process's "not in the trial" refusals into a plain note
   instead of a broken button. Every storage access is guarded; nothing here may break the page. */
(function () {
  "use strict";
  if (!/(?:^|;\s*)hv_trial_on=1/.test(document.cookie) || window.__hvTrial) return;
  window.__hvTrial = true;
  var API = ((window.CATALOGUE_CONFIG && window.CATALOGUE_CONFIG.api) || "/admin") + "/api/trial/";
  var REFUSAL = "Not in the trial: this is where HelloVoice would do it for real.";

  var css = [
    ".hvt{position:sticky;top:0;z-index:2147483000;background:#121212;color:#fff;font:500 14px/1.35 \"DM Sans\",Arial,sans-serif;",
    "box-shadow:0 6px 18px -10px rgba(0,0,0,.5)}",
    ".hvt__in{max-width:1320px;margin:0 auto;display:flex;align-items:center;gap:14px;padding:9px 16px;min-height:52px;flex-wrap:wrap}",
    ".hvt__tag{font:400 19px/1 Bebasneue,\"Bebas Neue\",Arial,sans-serif;letter-spacing:.06em;background:#e8ff76;color:#121212;",
    "padding:6px 10px 4px;border-radius:6px;flex:none}",
    ".hvt__txt{flex:1 1 260px;min-width:0}.hvt__txt b{font-weight:700}.hvt__txt span{color:rgba(255,255,255,.72)}",
    ".hvt__btn{font:400 18px/1 Bebasneue,\"Bebas Neue\",Arial,sans-serif;letter-spacing:.06em;background:#fff;color:#121212;border:0;",
    "border-radius:999px;padding:11px 18px 9px;cursor:pointer;min-height:40px;flex:none;transition:background .2s}",
    ".hvt__btn:hover{background:#e8ff76}.hvt__btn:focus-visible,.hvt-sheet :focus-visible{outline:3px solid #ff691e;outline-offset:2px}",
    ".hvt-sheet{position:fixed;inset:0;z-index:2147483001;display:flex;justify-content:flex-end;background:rgba(18,18,18,.42);",
    "opacity:0;transition:opacity .25s cubic-bezier(.16,1,.3,1)}.hvt-sheet.is-on{opacity:1}",
    ".hvt-panel{width:min(440px,100%);height:100%;overflow:auto;background:#fff;color:#121212;padding:28px 26px 32px;",
    "font:400 15px/1.6 \"DM Sans\",Arial,sans-serif;transform:translateX(24px);transition:transform .35s cubic-bezier(.16,1,.3,1);",
    "box-shadow:-18px 0 40px -24px rgba(0,0,0,.45)}.hvt-sheet.is-on .hvt-panel{transform:none}",
    ".hvt-panel h2{font:400 40px/.95 Bebasneue,\"Bebas Neue\",Arial,sans-serif;letter-spacing:.02em;margin:0 0 10px}",
    ".hvt-panel p{margin:0 0 20px;color:#383838}.hvt-panel label{display:block;font-weight:600;font-size:13px;margin:0 0 14px}",
    ".hvt-panel input,.hvt-panel textarea{display:block;width:100%;box-sizing:border-box;margin-top:6px;font:inherit;font-size:16px;",
    "padding:11px 12px;border:1px solid rgba(18,18,18,.28);border-radius:12px;background:#fff;color:#121212}",
    ".hvt-panel textarea{min-height:110px;resize:vertical}.hvt-panel input:focus,.hvt-panel textarea:focus{border-color:#121212;outline:0}",
    ".hvt-row{display:flex;gap:10px;align-items:center;margin-top:6px;flex-wrap:wrap}",
    ".hvt-send{font:400 20px/1 Bebasneue,\"Bebas Neue\",Arial,sans-serif;letter-spacing:.06em;background:#121212;color:#fff;border:0;",
    "border-radius:999px;padding:14px 24px 12px;cursor:pointer;min-height:48px}.hvt-send[disabled]{opacity:.5;cursor:progress}",
    ".hvt-x{position:absolute;top:14px;right:14px;width:44px;height:44px;border:0;border-radius:50%;background:#e9dcd2;cursor:pointer;",
    "display:grid;place-items:center}.hvt-panel{position:relative}",
    ".hvt-msg{font-weight:600;font-size:14px}.hvt-msg.is-err{color:#c01010}.hvt-done{background:#e7f7ed;color:#14884a;border-radius:12px;",
    "padding:16px 18px;font-weight:600}",
    ".hvt-toast{position:fixed;left:50%;bottom:calc(24px + env(safe-area-inset-bottom));transform:translate(-50%,12px);opacity:0;",
    "z-index:2147483002;max-width:min(560px,calc(100% - 32px));background:#121212;color:#fff;border-radius:12px;padding:14px 18px;",
    "font:500 14px/1.45 \"DM Sans\",Arial,sans-serif;box-shadow:0 14px 30px -14px rgba(0,0,0,.55);display:flex;gap:14px;",
    "align-items:center;transition:opacity .25s,transform .35s cubic-bezier(.16,1,.3,1)}.hvt-toast.is-on{opacity:1;transform:translate(-50%,0)}",
    ".hvt-toast button{flex:none;background:#e8ff76;color:#121212;border:0;border-radius:999px;padding:8px 14px;font:700 13px \"DM Sans\",Arial,sans-serif;cursor:pointer}",
    "@media (max-width:640px){.hvt__in{gap:10px;padding:8px 12px}.hvt__txt{flex-basis:100%;order:3;font-size:13px}",
    ".hvt__btn{margin-left:auto;font-size:16px;padding:9px 14px 7px;min-height:36px}}",
    "@media (prefers-reduced-motion:reduce){.hvt-sheet,.hvt-panel,.hvt-toast{transition:none}}"
  ].join("");

  function el(tag, attrs, html) {
    var n = document.createElement(tag);
    for (var k in attrs || {}) n.setAttribute(k, attrs[k]);
    if (html != null) n.innerHTML = html;
    return n;
  }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return "&#" + c.charCodeAt(0) + ";"; }); }

  var ST = { client: "", days_left: null }, bar = null, sheet = null, toastT = null;

  function paintBar() {
    if (!bar) return;
    var left = ST.days_left == null ? "" : ST.days_left <= 1 ? "ends today" : ST.days_left + " days left";
    bar.querySelector(".hvt__txt").innerHTML =
      (ST.client ? "<b>Trial for " + esc(ST.client) + "</b> " : "<b>HELVi Connect trial</b> ") +
      "<span>· sample data only" + (left ? " · " + esc(left) : "") + "</span>";
  }

  function mountBar() {
    if (bar || !document.body) return;
    document.head.appendChild(el("style", { id: "hvt-css" }, css));
    bar = el("div", { class: "hvt", role: "region", "aria-label": "Trial" },
      "<div class='hvt__in'><span class='hvt__tag'>Trial</span><span class='hvt__txt'></span>" +
      "<button type='button' class='hvt__btn'>Talk to HelloVoice</button></div>");
    document.body.insertBefore(bar, document.body.firstChild);
    bar.querySelector(".hvt__btn").addEventListener("click", openSheet);
    paintBar();
  }

  function openSheet() {
    if (sheet) return;
    var last = document.activeElement;
    sheet = el("div", { class: "hvt-sheet", role: "dialog", "aria-modal": "true", "aria-labelledby": "hvt-h" },
      "<div class='hvt-panel'><button type='button' class='hvt-x' aria-label='Close'>" +
      "<svg viewBox='0 0 24 24' width='18' height='18' fill='none' stroke='currentColor' stroke-width='2.2' stroke-linecap='round' aria-hidden='true'><path d='M6 6l12 12M18 6L6 18'/></svg></button>" +
      "<h2 id='hvt-h'>Run this with your brand</h2>" +
      "<p>Everything here is sample data. Tell us what you would like to do for real and HelloVoice replies within one working day.</p>" +
      "<form novalidate><label>Your name<input name='name' autocomplete='name' required maxlength='80'></label>" +
      "<label>Work email<input name='email' type='email' autocomplete='email' maxlength='120'></label>" +
      "<label>Phone or WhatsApp <span style='font-weight:400;color:#383838'>(email or phone)</span><input name='phone' type='tel' autocomplete='tel' maxlength='40'></label>" +
      "<label>What would you like to do?<textarea name='message' maxlength='1000' placeholder='E.g. a creator shortlist for our Ramadan launch in KSA'></textarea></label>" +
      "<div class='hvt-row'><button class='hvt-send' type='submit'>Send to HelloVoice</button><span class='hvt-msg' aria-live='polite'></span></div></form></div>");
    document.body.appendChild(sheet);
    requestAnimationFrame(function () { sheet.classList.add("is-on"); });
    var form = sheet.querySelector("form"), msg = sheet.querySelector(".hvt-msg");
    function close() {
      if (!sheet) return;
      var s = sheet; sheet = null;
      s.classList.remove("is-on");
      setTimeout(function () { s.remove(); }, 260);
      document.removeEventListener("keydown", onKey);
      if (last && last.focus) last.focus();
    }
    function onKey(e) { if (e.key === "Escape") close(); }
    document.addEventListener("keydown", onKey);
    sheet.addEventListener("click", function (e) { if (e.target === sheet) close(); });
    sheet.querySelector(".hvt-x").addEventListener("click", close);
    form.name.focus();
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var b = { name: form.name.value.trim(), email: form.email.value.trim(), phone: form.phone.value.trim(), message: form.message.value.trim() };
      msg.className = "hvt-msg is-err";
      if (!b.name) { msg.textContent = "Add your name."; form.name.focus(); return; }
      if (!b.email && !b.phone) { msg.textContent = "Add an email or a phone number."; form.email.focus(); return; }
      var btn = form.querySelector(".hvt-send");
      btn.disabled = true; msg.className = "hvt-msg"; msg.textContent = "Sending…";
      _fetch(API + "contact", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) })
        .then(function (r) { return r.json().catch(function () { return {}; }); })
        .then(function (j) {
          if (j && j.ok) { form.outerHTML = "<div class='hvt-done' role='status'>" + esc(j.message || "Thanks. We will be in touch.") + "</div>"; return; }
          btn.disabled = false; msg.className = "hvt-msg is-err"; msg.textContent = (j && (j.error || j.message)) || "That did not send. Try again.";
        })
        .catch(function () { btn.disabled = false; msg.className = "hvt-msg is-err"; msg.textContent = "No connection. Try again."; });
    });
  }

  function toast(text) {
    var t = document.querySelector(".hvt-toast");
    if (!t) {
      t = el("div", { class: "hvt-toast", role: "status" }, "<span></span><button type='button'>Ask us</button>");
      document.body.appendChild(t);
      t.querySelector("button").addEventListener("click", function () { t.classList.remove("is-on"); openSheet(); });
    }
    t.querySelector("span").textContent = text;
    requestAnimationFrame(function () { t.classList.add("is-on"); });
    clearTimeout(toastT);
    toastT = setTimeout(function () { t.classList.remove("is-on"); }, 6000);
  }

  // The trial process answers what a trial may not do with 403 {reason: "trial"} and an ended link with 410.
  var _fetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    return _fetch(input, init).then(function (r) {
      if (r.status === 403 || r.status === 410) {
        r.clone().json().then(function (j) {
          if (!j) return;
          if (j.reason === "trial") toast(REFUSAL);
          else if (j.reason === "trial_ended") toast("This trial has ended. Ask HelloVoice for a new link.");
        }).catch(function () {});
      }
      return r;
    });
  };

  function start() {
    mountBar();
    _fetch(API + "state", { credentials: "include", cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (j) { if (j && j.trial) { ST = j; paintBar(); } })
      .catch(function () {});
  }
  if (document.body) start(); else document.addEventListener("DOMContentLoaded", start);
})();
