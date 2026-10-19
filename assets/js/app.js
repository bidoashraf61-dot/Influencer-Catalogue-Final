/* HELVi Connect app (item 168): makes the portal an installable phone app.

   - registers /sw.js (offline page, push alerts, taps)
   - the fixed bottom bar on phones: Home · Catalogue · Selections · Campaigns · Alerts
   - install help: Chrome's own install (Android), a Share -> Add to Home Screen guide (iPhone)
   - the soft "turn on alerts" card, then the browser's real permission prompt
   - reports installs and permission state to /api/push/event for Admin -> App & alerts

   Waits for portal.js ("hv:me") to know who is signed in. Every storage access is
   guarded: private mode or blocked storage must never break the page. */
(function () {
  "use strict";
  var API = ((window.CATALOGUE_CONFIG && window.CATALOGUE_CONFIG.api) || "/admin") + "/api/push/";
  var ICON = "/assets/app/icon-192.png";
  var LOGO = "/assets/brand/helvy-connect/helvy-connect-light-320.webp";
  var HEAD = "/assets/brand/helvy-connect/helvy-icon-180.png";
  var DAY = 864e5, SNOOZE = 14 * DAY;
  var ua = navigator.userAgent || "";
  var ANDROID = /Android/.test(ua);
  var IOS = !ANDROID && (/iPhone|iPad|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1 && /Safari/.test(ua)));
  var PLATFORM = IOS ? "ios" : (ANDROID ? "android" : "desktop");
  var STANDALONE = (window.matchMedia && matchMedia("(display-mode: standalone)").matches) || navigator.standalone === true;
  var IOS_SAFARI = IOS && /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS|GSA\//.test(ua);
  var iosVer = (function () { var m = /OS (\d+)[_.](\d+)/.exec(ua); return m ? parseFloat(m[1] + "." + m[2]) : 0; })();
  var PUSH_OK = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window && (!IOS || STANDALONE);
  var ME = null, deferred = null, reg = null;

  // ---------------------------------------------------------------- utils --
  function get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function put(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage off */ } }
  function sget(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }
  function sput(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* storage off */ } }
  // Another layer is open (the tour, Helvi's next-step bubble, a dialog): wait for it to close.
  function busy() {
    var q = ":popover-open, dialog[open], .tv, .cx-offer, .cx-dr, .cx-sheet, .pt-scrim, .hca-sheet, .hca-bar, .hca-card";
    try { return !!document.querySelector(q); } catch (e) { return !!document.querySelector("dialog[open], .tv, .cx-offer, .cx-dr, .cx-sheet, .pt-scrim, .hca-sheet, .hca-bar, .hca-card"); }
  }
  function whenFree(fn, tries) {
    tries = tries == null ? 20 : tries;
    if (!busy()) return fn();
    if (tries > 0) setTimeout(function () { whenFree(fn, tries - 1); }, 4000);
  }
  function snoozed(k) { var t = +get(k) || 0; return Date.now() - t < SNOOZE; }
  function deviceKey() {
    var k = get("hca-dk");
    if (!k) { k = (Date.now().toString(36) + Math.random().toString(36).slice(2, 12)); put("hca-dk", k); }
    return k;
  }
  function perm() {
    if (!("Notification" in window)) return "unsupported";
    if (IOS && !STANDALONE) return iosVer && iosVer < 16.4 ? "unsupported" : "default";
    return Notification.permission;
  }
  function osName() { return IOS ? "iOS " + (iosVer || "") : (ANDROID ? "Android " + ((/Android (\d+)/.exec(ua) || [])[1] || "") : ""); }
  function post(op, body) {
    return fetch(API + op, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body) }).then(function (r) { return r.json().catch(function () { return {}; }); }).catch(function () { return {}; });
  }
  function track(e, extra) {
    var b = { k: deviceKey(), e: e, p: PLATFORM, os: osName(), sa: STANDALONE, perm: perm() };
    for (var x in extra || {}) b[x] = extra[x];
    return post("event", b);
  }
  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    for (var a in attrs || {}) {
      if (a === "class") n.className = attrs[a];
      else if (a === "html") n.innerHTML = attrs[a];
      else if (a.slice(0, 2) === "on") n.addEventListener(a.slice(2), attrs[a]);
      else if (attrs[a] != null) n.setAttribute(a, attrs[a]);
    }
    [].concat(kids || []).forEach(function (k) { if (k != null) n.appendChild(typeof k === "string" ? document.createTextNode(k) : k); });
    return n;
  }
  var SVG = {
    home: '<path d="M3.5 10.5 12 3.5l8.5 7"/><path d="M5.5 9v11h13V9"/><path d="M10 20v-6h4v6"/>',
    grid: '<circle cx="8" cy="8" r="3.2"/><circle cx="16.5" cy="8" r="3.2"/><path d="M2.8 20c.6-3.4 2.7-5.4 5.2-5.4s4.6 2 5.2 5.4"/><path d="M13.8 15.3c.8-.5 1.7-.7 2.7-.7 2.5 0 4.6 2 5.2 5.4"/>',
    list: '<rect x="4" y="3.5" width="16" height="17" rx="3"/><path d="M8 9l1.6 1.6L12.5 7.7"/><path d="M8 15h8"/><path d="M14.5 9.5H16"/>',
    camp: '<path d="M4 19V11"/><path d="M9.3 19V6"/><path d="M14.7 19v-9"/><path d="M20 19V4"/>',
    bell: '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
    help: '<path d="M4.5 5.5h15v10h-8l-4 3.5v-3.5h-3z"/><path d="M10 9.2a2 2 0 1 1 2.6 1.9c-.4.2-.6.5-.6.9v.4"/><path d="M12 14h0"/>',
    admin: '<rect x="3.5" y="4" width="17" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
    share: '<path d="M12 3v12"/><path d="M8 7l4-4 4 4"/><path d="M8 11H6v10h12V11h-2"/>',
    plus: '<rect x="3.5" y="3.5" width="17" height="17" rx="4"/><path d="M12 8v8M8 12h8"/>',
    x: '<path d="M3 3l8 8M11 3l-8 8"/>'
  };
  function svg(name, vb) { return '<svg viewBox="' + (vb || "0 0 24 24") + '" aria-hidden="true">' + SVG[name] + "</svg>"; }

  // ------------------------------------------------------- service worker --
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).then(function (r) { reg = r; }).catch(function () { /* no worker */ });
  }
  window.addEventListener("beforeinstallprompt", function (e) { e.preventDefault(); deferred = e; if (ME) whenFree(maybeInstall); });
  window.addEventListener("appinstalled", function () { track("installed"); closeBar(); });

  // --------------------------------------------------------- bottom bar --
  var nav, badge;
  function tabs() {
    var u = ME && ME.user, kind = ME && ME.kind;
    if (u) return [["home", "Home", "/account/#overview", "home"], ["grid", "Catalogue", "/", "cat"],
      ["list", "Selections", "/account/#selections", "sel"], ["camp", "Campaigns", "/account/#campaigns", "camp"],
      ["bell", "Alerts", "/account/#notifications", "alerts"]];
    var out = [["grid", "Catalogue", "/", "cat"], ["camp", "Campaigns", "/campaign/dashboard/", "camp"]];
    if (kind === "admin" || (ME && ME.staff)) out.push(["admin", "Admin", ((window.CATALOGUE_CONFIG && window.CATALOGUE_CONFIG.api) || "/admin") + "/", "admin"]);
    else out.push(["help", "Help", null, "help"]);
    return out;
  }
  function current() {
    var p = location.pathname, h = (location.hash || "").slice(1).split("/")[0];
    if (/^\/account\/?$/.test(p)) return { selections: "sel", campaigns: "camp", notifications: "alerts" }[h] || "home";
    if (/^\/selection\//.test(p)) return "sel";
    if (/^\/campaign\//.test(p)) return "camp";
    if (p === "/" || /^\/creator\//.test(p)) return "cat";
    return "";
  }
  function paintNav() {
    if (!nav) return;
    var cur = current();
    [].forEach.call(nav.children, function (a) {
      if (a.getAttribute("data-k") === cur) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
  }
  function mountNav() {
    if (nav || document.body.getAttribute("data-no-appnav") != null) return;
    nav = el("nav", { class: "hca-nav", "aria-label": "App" });
    tabs().forEach(function (t) {
      var inner = '<span class="hca-pill">' + svg(t[0]) + "</span><span>" + t[1] + "</span>";
      var item = t[2] ? el("a", { href: t[2], "data-k": t[3], html: inner }) : el("button", { type: "button", "data-k": t[3], html: inner,
        onclick: function () { var hv = window.hvPortal || {}; if (hv.talk) hv.talk(); } });
      if (t[3] === "alerts") { badge = el("span", { class: "hca-badge", hidden: "" }); item.appendChild(badge); }
      // The account page switches section on the hash; tapping the tab you are on scrolls to the top.
      item.addEventListener("click", function () { if (item.getAttribute("aria-current")) window.scrollTo({ top: 0, behavior: "smooth" }); });
      nav.appendChild(item);
    });
    document.body.appendChild(nav);
    document.body.classList.add("hca-nav-on");
    paintNav();
    window.addEventListener("hashchange", paintNav);
    setUnread(ME.unread || 0);
  }
  function setUnread(n) {
    n = +n || 0;
    if (badge) { badge.hidden = !n; badge.textContent = n > 99 ? "99+" : String(n); if (badge.parentNode) badge.parentNode.setAttribute("aria-label", "Alerts" + (n ? ", " + n + " unread" : "")); }
    if (STANDALONE && navigator.setAppBadge) (n ? navigator.setAppBadge(n) : navigator.clearAppBadge()).catch(function () {});
  }
  function pollUnread() {
    if (!(ME && ME.user)) return;
    var api = ((window.CATALOGUE_CONFIG && window.CATALOGUE_CONFIG.api) || "/admin");
    fetch(api + "/api/notifications?limit=1", { credentials: "include" }).then(function (r) { return r.json(); })
      .then(function (r) { if (r && r.ok) setUnread(r.unread); }).catch(function () {});
  }

  // ------------------------------------------------------- install help --
  var bar, sheet, scrim, pointer;
  function closeBar() { if (bar) { bar.remove(); bar = null; } }
  function closeSheet() { [sheet, scrim, pointer].forEach(function (n) { if (n) n.remove(); }); sheet = scrim = pointer = null; }
  function visits() { var n = (+get("hca-visits") || 0); if (!sget("hca-counted")) { n += 1; put("hca-visits", n); sput("hca-counted", "1"); } return n; }
  function maybeInstall() {
    if (STANDALONE || PLATFORM === "desktop" || snoozed("hca-install-x") || sget("hca-install-shown")) return;
    if (visits() < 2) return;
    if (ANDROID && deferred) return showBar();
    if (IOS) return showGuide();
  }
  function showBar() {
    if (bar) return;
    sput("hca-install-shown", "1");
    track("guide");
    bar = el("div", { class: "hca-bar", role: "dialog", "aria-label": "Install the HELVi Connect app" }, [
      el("img", { src: ICON, alt: "" }),
      el("div", null, [el("b", null, "Get the app"), el("span", null, "Full screen + campaign alerts")]),
      el("button", { class: "hca-btn hca-btn--lime", type: "button", onclick: function () {
        if (!deferred) return closeBar();
        deferred.prompt();
        deferred.userChoice.then(function (c) { track(c && c.outcome === "accepted" ? "installed" : "guide_closed"); deferred = null; closeBar(); });
      } }, "Install"),
      el("button", { class: "hca-x", type: "button", "aria-label": "Not now", html: svg("x", "0 0 14 14"),
        onclick: function () { put("hca-install-x", Date.now()); track("guide_closed"); closeBar(); } })
    ]);
    document.body.appendChild(bar);
  }
  function showGuide() {
    if (sheet) return;
    sput("hca-install-shown", "1");
    track("guide");
    var safari = IOS_SAFARI;
    scrim = el("div", { class: "hca-scrim", onclick: snoozeGuide });
    var steps = safari ? el("ol", { class: "hca-steps" }, [
      el("li", { html: "<i>1</i><span>Tap <b>Share</b> in Safari's bar</span><span class=\"hca-ic\">" + svg("share") + "</span>" }),
      el("li", { html: "<i>2</i><span>Choose <b>Add to Home Screen</b></span><span class=\"hca-ic\">" + svg("plus") + "</span>" }),
      el("li", { html: "<i>3</i><span>Tap <b>Add</b>, then open HELVi from your Home Screen</span>" })
    ]) : el("ol", { class: "hca-steps" }, [
      el("li", { html: "<i>1</i><span>Open this page in <b>Safari</b></span>" }),
      el("li", { html: "<i>2</i><span>Tap <b>Share</b>, then <b>Add to Home Screen</b></span><span class=\"hca-ic\">" + svg("share") + "</span>" })
    ]);
    sheet = el("div", { class: "hca-sheet" + (safari ? " hca-sheet--ios" : ""), role: "dialog", "aria-modal": "true", "aria-labelledby": "hca-guide-t" }, [
      el("div", { class: "hca-id" }, [el("img", { src: ICON, alt: "" }), el("div", null, [el("b", null, "HELVi Connect"), el("span", null, "Add it to your Home Screen")])]),
      el("h2", { id: "hca-guide-t" }, "Your campaigns, one tap away"),
      el("p", null, iosVer && iosVer < 16.4 ? "Opens full screen, like an app."
        : "Opens full screen, and it is the only way iPhone can send you campaign alerts."),
      steps,
      el("div", { class: "hca-foot" }, [
        el("button", { class: "hca-btn hca-btn--quiet", type: "button", onclick: snoozeGuide }, "Remind me later"),
        el("button", { class: "hca-btn hca-btn--line", type: "button", onclick: function () { track("guide_closed"); closeSheet(); } }, "Got it")
      ])
    ]);
    document.body.appendChild(scrim);
    document.body.appendChild(sheet);
    if (safari) { pointer = el("div", { class: "hca-pointer", html: '<svg viewBox="0 0 26 34" aria-hidden="true"><path d="M13 2v28M4 22l9 9 9-9"/></svg>' }); document.body.appendChild(pointer); }
    var first = sheet.querySelector("button:last-child"); if (first) first.focus({ preventScroll: true });
    document.addEventListener("keydown", function esc(e) { if (e.key === "Escape") { snoozeGuide(); document.removeEventListener("keydown", esc); } });
  }
  function snoozeGuide() { put("hca-install-x", Date.now()); track("guide_closed"); closeSheet(); }

  // ------------------------------------------------------- alerts opt-in --
  var card;
  function keyBytes(b64) {
    var pad = "=".repeat((4 - b64.length % 4) % 4), raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
    var out = new Uint8Array(raw.length); for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i); return out;
  }
  function ready() { return reg ? Promise.resolve(reg) : navigator.serviceWorker.ready; }
  function subscribe() {
    return ready().then(function (r) {
      return r.pushManager.getSubscription().then(function (s) {
        if (s) return s;
        return fetch(API + "key", { credentials: "include" }).then(function (x) { return x.json(); })
          .then(function (j) { return r.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(j.key) }); });
      });
    }).then(function (s) {
      put("hca-sub-at", Date.now());
      return post("subscribe", { sub: s.toJSON(), k: deviceKey(), sa: STANDALONE });
    });
  }
  function enable() {
    if (!PUSH_OK) return Promise.resolve("unsupported");
    track("prompted");
    var ask = Notification.requestPermission();
    return Promise.resolve(ask).then(function (p) {
      if (p === "granted") return subscribe().then(function () { track("granted"); return "granted"; });
      track(p === "denied" ? "denied" : "seen");
      return p;
    });
  }
  function hasValue() {
    // Worth hearing about: an account with a campaign or selection, or a team member.
    return ME && (ME.staff || ME.kind === "admin" || ME.user);
  }
  function maybeCard() {
    if (card || !PUSH_OK || perm() !== "default" || !hasValue() || snoozed("hca-card-x") || sget("hca-card-shown")) return;
    if (sheet || bar) return;
    sput("hca-card-shown", "1");
    track("asked");
    var msg = el("div", { class: "hca-msg", role: "status", hidden: "" });
    card = el("div", { class: "hca-card", role: "dialog", "aria-labelledby": "hca-card-t" }, [
      el("img", { src: HEAD, alt: "" }),
      el("b", { id: "hca-card-t" }, "Hear it first"),
      el("button", { class: "hca-x", type: "button", "aria-label": "Not now", html: svg("x", "0 0 14 14"), onclick: dismissCard }),
      el("p", null, "Helvi can tap you when your campaign hits a milestone. A few alerts a week, never at night."),
      el("div", { class: "hca-acts" }, [
        el("button", { class: "hca-btn hca-btn--ink", type: "button", onclick: function () {
          enable().then(function (p) {
            if (p === "granted") { card.remove(); card = null; return; }
            msg.hidden = false;
            msg.textContent = p === "denied" ? "Alerts are blocked for this site. Turn them on in your phone's settings to get them."
              : "Alerts were not turned on. You can do it any time from your profile.";
            setTimeout(dismissCard, 4000);
          });
        } }, "Turn on alerts"),
        el("button", { class: "hca-btn hca-btn--quiet", type: "button", onclick: dismissCard }, "Not now")
      ]),
      msg
    ]);
    document.body.appendChild(card);
  }
  function dismissCard() { put("hca-card-x", Date.now()); if (card) { card.remove(); card = null; } }

  // Account -> Notifications gains a "Phone alerts" row.
  function mountPhoneRow() {
    if (!(ME && ME.user) || document.getElementById("hca-phone")) return;
    var host = document.querySelector('[data-section="notifications"], #notifications, .ac-panel[data-panel="notifications"]');
    if (!host || !/notifications/.test(location.hash)) return;
    var status = el("span"), btn = el("button", { class: "hca-btn hca-btn--ink", type: "button" });
    var row = el("div", { class: "hca-phone", id: "hca-phone" }, [el("div", null, [el("b", null, "Phone alerts"), status]), btn]);
    function paint(on) {
      var p = perm();
      if (!PUSH_OK) {
        status.textContent = IOS && !STANDALONE ? "Add HELVi Connect to your Home Screen to get alerts on this iPhone." : "This browser cannot show alerts.";
        btn.hidden = !(IOS && !STANDALONE); btn.textContent = "How"; btn.onclick = function () { sput("hca-install-shown", ""); put("hca-install-x", 0); showGuide(); };
        return;
      }
      if (p === "denied") { status.textContent = "Blocked in this browser's settings."; btn.hidden = true; return; }
      if (p === "granted" && on) { status.textContent = "On for this phone. Pick which groups below."; btn.textContent = "Turn off"; btn.className = "hca-btn hca-btn--line"; btn.hidden = false;
        btn.onclick = function () { post("phone", { on: false }).then(function () { paint(false); }); }; return; }
      status.textContent = "Milestones, new posts and shared selections, on this phone."; btn.textContent = "Turn on"; btn.className = "hca-btn hca-btn--ink"; btn.hidden = false;
      btn.onclick = function () { post("phone", { on: true }); enable().then(function (r) { paint(r === "granted"); }); };
    }
    fetch(API + "state", { credentials: "include" }).then(function (r) { return r.json(); }).then(function (s) { paint(s.phone !== false); })
      .catch(function () { paint(true); });
    host.insertBefore(row, host.firstChild);
  }

  // ---------------------------------------------------------------- boot --
  function boot(me) {
    if (ME) return;
    ME = me || {};
    // The app opens on the profile; someone without one (access code, team preview) starts at the catalogue.
    if (STANDALONE && /^\/account\/?$/.test(location.pathname) && /[?&]src=app/.test(location.search) && !ME.user) { location.replace("/"); return; }
    mountNav();
    track("seen");
    if (STANDALONE && !sget("hca-launch")) { sput("hca-launch", "1"); track("launch"); }
    // Already allowed: keep this phone's subscription fresh (once a day) and tied to whoever is signed in.
    if (PUSH_OK && perm() === "granted" && Date.now() - (+get("hca-sub-at") || 0) > DAY) subscribe().catch(function () {});
    setTimeout(function () { whenFree(maybeInstall); }, 3000);
    setTimeout(function () { whenFree(maybeCard); }, 8000);
    setInterval(function () { if (!document.hidden) pollUnread(); }, 90000);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) pollUnread(); });
    window.addEventListener("hashchange", function () { setTimeout(mountPhoneRow, 400); });
    setTimeout(mountPhoneRow, 900);
    // The bell elsewhere on the page marks things read: follow it.
    document.addEventListener("click", function (e) { if (e.target.closest && e.target.closest(".hv-bell, .hv-note, .pt-bell")) setTimeout(pollUnread, 1200); });
  }
  window.HCApp = { enable: enable, perm: perm, standalone: STANDALONE, platform: PLATFORM, guide: function () { put("hca-install-x", 0); sput("hca-install-shown", ""); IOS ? showGuide() : (deferred ? showBar() : null); } };
  var hv = window.hvPortal;
  if (hv && hv.me) boot(hv.me);
  else document.addEventListener("hv:me", function (e) { boot(e.detail); });
})();
