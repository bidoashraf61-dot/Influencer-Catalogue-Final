/* HELVi Connect: what a person sees when a module is not open to them (docs/SAAS-MODEL.md; the screens Bido approved on
   28 Oct 2026). app.js watches every API answer; a 403 that carries {code, module} lands here.

   locked     the company does not have the module   -> "not part of your plan", Request this module
   paused     HelloVoice switched it off              -> "paused, your data is safe", Ask HelloVoice
   no_role    the company has it, this person has no role -> names the company's admin, Request access
   read_only  a viewer tried to change something      -> a short notice, not a page

   Someone with nobody behind them (a forwarded report link) gets a plain "not available right now" with no buttons.
   Nothing about the module's data is ever shown: the server sent none. */
(function () {
  "use strict";
  var API = ((window.CATALOGUE_CONFIG && window.CATALOGUE_CONFIG.api) || "/admin") + "/api/access/";
  var WHAT = {
    "helvi-selection": "Helvi Selection is the creator catalogue: browse the roster, build shortlists and selections, and ask for quotes.",
    "helvi-track": "Track follows a campaign after it goes live: every post, view and comment in one report you can forward.",
    "helvi-intelligence": "Intelligence shows which creators your competitors already worked with, and how those posts did."
  };
  var MARK = {
    "helvi-selection": '<circle cx="8" cy="8" r="3" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="16.5" cy="9" r="2.4" fill="none" stroke="currentColor" stroke-width="2"/><path d="M3 19c.6-3.2 2.7-5 5-5s4.4 1.8 5 5M14 14.5c2.6-.6 5.2.8 6 4.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
    "helvi-track": '<path d="M3 18l5.5-6 4 3.5L21 6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 6h6v6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
    "helvi-intelligence": '<circle cx="10.5" cy="10.5" r="6" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M15 15l5.5 5.5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/><path d="M8 11.5l2-2.5 1.5 1.5L13.5 8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
  };
  var LOCK = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><rect x="5" y="10.5" width="14" height="10" rx="2.5" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>';
  var OK = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="12" cy="12" r="9.5" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M7.8 12.4l2.9 2.9 5.6-6" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  var root = null, toastTimer = null;

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  function css() {
    if (document.getElementById("hva-css")) return;
    var s = document.createElement("style");
    s.id = "hva-css";
    s.textContent =
      ".hva{position:fixed;inset:0;z-index:2147483000;background:#f6f2ec;color:#121212;font-family:'DM Sans',Arial,sans-serif;font-size:15px;line-height:1.55;overflow:auto;display:grid;grid-template-rows:auto 1fr}" +
      ".hva *{box-sizing:border-box}" +
      ".hva__top{display:flex;align-items:center;gap:12px;padding:12px max(16px,env(safe-area-inset-left,0px)) 12px;border-bottom:1px solid rgba(18,18,18,.12);background:#fff}" +
      ".hva__logo{font-family:Bebasneue,'Bebas Neue',Impact,'Arial Narrow',sans-serif;font-size:26px;line-height:1;letter-spacing:.02em}.hva__logo i{font-style:normal;color:#ff691e}" +
      ".hva__chip{display:flex;align-items:center;gap:9px;border:1px solid rgba(18,18,18,.12);border-radius:999px;padding:5px 14px 5px 6px;font-weight:500;background:#fff}" +
      ".hva__mark{width:26px;height:26px;border-radius:8px;display:grid;place-items:center;background:#efece6;color:#8a7a68;flex:none}.hva__mark svg{width:16px;height:16px}" +
      ".hva__body{padding:clamp(20px,4vw,56px) max(16px,env(safe-area-inset-left,0px)) 56px;display:grid;align-content:start;justify-items:start}" +
      ".hva__in{width:100%;max-width:1080px;margin:0 auto;display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:clamp(18px,3vw,40px);align-items:center}" +
      ".hva__in.is-one{grid-template-columns:minmax(0,1fr);max-width:640px}" +
      "@media(max-width:760px){.hva__in{grid-template-columns:minmax(0,1fr)}}" +
      ".hva h2{font-family:Bebasneue,'Bebas Neue',Impact,'Arial Narrow',sans-serif;font-weight:400;font-size:clamp(2.1rem,1.2rem + 2.6vw,3.6rem);line-height:.95;margin:0;max-width:18ch;text-wrap:balance}" +
      ".hva p{margin:0;max-width:58ch;color:#383838}.hva .hva__fine{font-size:13px;color:#8a7a68}" +
      ".hva__col{display:grid;gap:16px}" +
      ".hva__btns{display:flex;gap:10px;flex-wrap:wrap;align-items:center}" +
      ".hva__btn{appearance:none;border:0;border-radius:999px;font-family:Bebasneue,'Bebas Neue',Impact,sans-serif;font-size:20px;letter-spacing:.06em;padding:11px 26px 9px;cursor:pointer;background:#121212;color:#e8ff76;text-decoration:none;display:inline-block}" +
      ".hva__btn.is-ghost{background:transparent;color:#121212;border:1px solid #121212;padding:10px 24px 8px}.hva__btn[disabled]{background:#efece6;color:#383838;cursor:default}" +
      ".hva__btn:focus-visible{outline:3px solid #ff691e;outline-offset:2px}" +
      ".hva__sent{display:none;align-items:center;gap:10px;background:#e7f7ed;color:#14884a;border-radius:12px;padding:10px 14px;font-weight:500;max-width:58ch}.hva__sent.is-on{display:flex}" +
      ".hva__sent svg{flex:none}.hva__err{display:none;color:#c01010;font-size:14px}.hva__err.is-on{display:block}" +
      ".hva__sample{background:#efece6;border-radius:18px;padding:16px;display:grid;gap:10px;position:relative;overflow:hidden}" +
      ".hva__sample i{display:block;border-radius:6px;background:#d9d2c7;height:10px}.hva__sample .t{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.hva__sample .t i{height:54px;border-radius:10px;background:#e0d9ce}.hva__sample .l{height:76px;border-radius:10px;background:#e0d9ce}" +
      ".hva__sample b{position:absolute;right:12px;top:12px;font-size:11px;letter-spacing:.1em;text-transform:uppercase;background:#121212;color:#e8ff76;padding:3px 9px;border-radius:999px}" +
      ".hva__tag{display:inline-flex;gap:6px;align-items:center;background:#efece6;color:#383838;border-radius:999px;padding:4px 11px;font-size:13px;font-weight:500}" +
      ".hva__toast{position:fixed;left:50%;bottom:calc(20px + env(safe-area-inset-bottom,0px));transform:translateX(-50%);z-index:2147483001;background:#121212;color:#fff;border-radius:14px;padding:12px 16px;max-width:min(92vw,520px);font-family:'DM Sans',Arial,sans-serif;font-size:14px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}" +
      ".hva__toast button{appearance:none;border:0;background:#e8ff76;color:#121212;border-radius:999px;padding:6px 14px;font:inherit;font-weight:700;cursor:pointer}" +
      "@media(prefers-reduced-motion:no-preference){.hva__body{animation:hva-in .28s cubic-bezier(.16,1,.3,1)}@keyframes hva-in{from{opacity:.001;transform:translateY(6px)}to{opacity:1;transform:none}}}";
    document.head.appendChild(s);
  }

  function post(path, body) {
    return fetch(API + path, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { return { status: r.status, body: j }; }); });
  }
  function state(module) {
    return fetch(API + "state?module=" + encodeURIComponent(module), { credentials: "include" })
      .then(function (r) { return r.json().then(function (j) { return { status: r.status, body: j }; }); })
      .catch(function () { return { status: 0, body: {} }; });
  }

  function page(inner, one, module, name) {
    css();
    if (root) root.remove();
    var m = MARK[module] || MARK["helvi-selection"];
    root = document.createElement("div");
    root.className = "hva";
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "true");
    root.setAttribute("aria-labelledby", "hva-h");
    root.innerHTML = '<div class="hva__top"><span class="hva__logo">HELVi <i>Connect</i></span>' +
      '<span class="hva__chip"><span class="hva__mark"><svg viewBox="0 0 24 24" aria-hidden="true">' + m + '</svg></span>' + esc(name || "") + '</span></div>' +
      '<div class="hva__body"><div class="hva__in' + (one ? " is-one" : "") + '">' + inner + "</div></div>";
    document.body.appendChild(root);
    document.documentElement.style.overflow = "hidden";
    var first = root.querySelector(".hva__btn");
    if (first) try { first.focus({ preventScroll: true }); } catch (e) { /* ignore */ }
    return root;
  }

  function wire(module, kind, who) {
    var btn = root.querySelector("[data-send]");
    if (!btn) return;
    btn.addEventListener("click", function () {
      btn.disabled = true;
      post("request", { module: module, kind: kind }).then(function (r) {
        if (r.body && r.body.ok) { root.querySelector(".hva__sent").classList.add("is-on"); return; }
        btn.disabled = false;
        var e = root.querySelector(".hva__err");
        e.textContent = r.status === 401 ? "Sign in first, then ask again." : ((r.body && r.body.message) || "That did not send. Try again in a moment.");
        e.classList.add("is-on");
      }).catch(function () { btn.disabled = false; var e = root.querySelector(".hva__err"); e.textContent = "That did not send. Check your connection and try again."; e.classList.add("is-on"); });
    });
  }

  function back() { return '<a class="hva__btn is-ghost" href="/workspace/">Back to my modules</a>'; }

  function unavailable(name) {
    page('<div class="hva__col"><h2 id="hva-h">This is not available right now</h2><p>The company that shared it has paused this service. Ask the sender to contact HelloVoice if you need it again.</p><p class="hva__fine">HelloVoice, info@hellovoice.co.uk</p></div>', true, null, name);
  }

  function toast(text, module) {
    css();
    var t = document.querySelector(".hva__toast");
    if (t) t.remove();
    t = document.createElement("div");
    t.className = "hva__toast";
    t.setAttribute("role", "status");
    t.innerHTML = "<span>" + esc(text) + '</span><button type="button">Ask for editor access</button>';
    document.body.appendChild(t);
    t.querySelector("button").addEventListener("click", function () {
      post("request", { module: module, kind: "role" }).then(function (r) {
        t.querySelector("span").textContent = r.body && r.body.ok ? "Asked your admin. You will get an email when they answer." : "That did not send. Try again in a moment.";
        t.querySelector("button").remove();
      });
    });
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.remove(); }, 12000);
  }

  function show(b) {
    if (!b || !b.code || !b.module) return;
    var module = b.module, name = b.name || "This module";
    if (b.code === "read_only") return toast("Your role here is viewer: you can read, but not change this.", module);
    if (root && root.isConnected && root.dataset.code === b.code && root.dataset.module === module) return;
    state(module).then(function (s) {
      if (s.status === 401) return unavailable(name);                     // nobody signed in: a forwarded report link
      var info = ((s.body && s.body.modules) || [])[0] || {};
      var ask = info.ask ? esc(info.ask) : "";
      var el;
      if (b.code === "locked") {
        el = page('<div class="hva__col"><h2 id="hva-h">' + esc(name) + ' is not part of your plan</h2><p>' + esc(WHAT[module] || "") +
          ' Ask HelloVoice to add it to your account and we will reply within one working day.</p>' +
          '<div class="hva__btns"><button class="hva__btn" type="button" data-send>Request this module</button>' + back() + "</div>" +
          '<div class="hva__sent" role="status">' + OK + "<span>Request sent. HelloVoice will reply to your email.</span></div><div class=\"hva__err\" role=\"alert\"></div></div>" +
          '<div class="hva__sample" aria-hidden="true"><b>Sample</b><i style="width:60%"></i><div class="t"><i></i><i></i><i></i></div><i class="l"></i><i style="width:80%"></i></div>', false, module, name);
        wire(module, "module");
      } else if (b.code === "paused") {
        el = page('<div class="hva__col"><h2 id="hva-h">' + esc(name) + ' is paused for your company</h2><p>Your campaigns, reports and tracking links are safe and come back as they were when it is switched on again. Tell HelloVoice if you want it back sooner.</p>' +
          '<div class="hva__btns"><button class="hva__btn" type="button" data-send>Ask HelloVoice</button>' + back() + "</div>" +
          '<div class="hva__sent" role="status">' + OK + "<span>Message sent to your HelloVoice account manager.</span></div><div class=\"hva__err\" role=\"alert\"></div></div>", true, module, name);
        wire(module, "module");
      } else {
        el = page('<div class="hva__col"><h2 id="hva-h">Your account does not include ' + esc(name) + '</h2><p>Your company has it, but nobody has given you a role yet. ' +
          (ask ? ask + " is the admin for your company and can open it for you." : "Ask the admin at your company, or HelloVoice, to give you a role.") + "</p>" +
          '<div class="hva__btns"><button class="hva__btn" type="button" data-send>Request access</button>' + back() + "</div>" +
          '<div class="hva__sent" role="status">' + OK + "<span>" + (ask ? "Asked " + ask + ". " : "Asked. ") + "You will get an email when you have a role.</span></div><div class=\"hva__err\" role=\"alert\"></div></div>", true, module, name);
        wire(module, "role");
      }
      el.dataset.code = b.code;
      el.dataset.module = module;
    });
  }

  window.hvAccessRefused = show;
  var pending = window.__hvAccessPending;
  window.__hvAccessPending = null;
  if (pending) show(pending);
})();
