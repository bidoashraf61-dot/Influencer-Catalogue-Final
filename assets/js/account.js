/* HELVi Connect: the client's profile (/account/), drawn from /api/account.
 *
 * Sections by hash: #overview (default), #selections, #analyses, #campaigns,
 * #briefs, #notifications, #credits, #account, and for a key account manager
 * #clients (My clients, from /api/account/clients). A side nav on a desktop, a strip
 * of tabs on a phone.
 *
 * Overview leads with Helvi and ONE next step, then the status line, the latest
 * notifications, profile completion (each step priced in what its credits buy)
 * and the invite. Campaigns keep the report's own scorebug.
 *
 * Everything from the server goes on the page with textContent, never HTML.
 * Icons, the notification row and Helvi's picture come from portal.js
 * (window.hvPortal), which has loaded by the time /api/account answers.
 */
(function () {
  "use strict";

  var CFG = window.CATALOGUE_CONFIG || {};
  var API = (CFG.api != null ? CFG.api : "/admin").replace(/\/$/, "");
  var ROOT = "../";
  var DATA = null;
  var FLASH = null;            // a message that must survive the next re-render
  var SECTION = "overview";
  var FILTER = "all";          // the notifications filter chip

  function HV() { return window.hvPortal || {}; }
  function ic(name) { return HV().icon ? HV().icon(name) : ""; }
  function $(id) { return document.getElementById(id); }
  function h(tag, props) {
    var el = document.createElement(tag);
    props = props || {};
    Object.keys(props).forEach(function (k) {
      var v = props[k];
      if (v == null || v === false) return;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k === "html") el.innerHTML = v;           // only our own static strings and icons
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    });
    for (var i = 2; i < arguments.length; i++) add(el, arguments[i]);
    return el;
  }
  function add(el, c) {
    if (c == null || c === false) return;
    if (Array.isArray(c)) { c.forEach(function (x) { add(el, x); }); return; }
    el.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
  }
  function icon(name) { var s = h("span", { class: "hc-icw", "aria-hidden": "true", html: ic(name) }); return s.firstChild || s; }
  function api(method, path, body) {
    return fetch(API + path, {
      method: method, credentials: "include", cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (b) { return { s: r.status, b: b }; });
    }, function () { return { s: 0, b: {} }; });
  }
  function store(k, v) { try { if (v === undefined) return sessionStorage.getItem(k); sessionStorage.setItem(k, v); } catch (e) { return null; } }

  /* ------------------------------------------------------------ formatting */

  function big(n) {
    n = Number(n) || 0;
    if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1).replace(/\.0$/, "") + "K";
    return String(n);
  }
  function day(ts) {
    if (!ts) return "";
    return new Date(ts * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  }
  function shortDay(ts) { return ts ? new Date(ts * 1000).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }) : ""; }
  function dm(ts) { return ts ? new Date(ts * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : ""; }
  function ago(ts) {
    if (!ts) return "";
    var s = Date.now() / 1000 - ts;
    if (s < 3600) return "just now";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    if (s < 86400 * 30) return Math.floor(s / 86400) + "d ago";
    return day(ts);
  }
  function initials(name) {
    return String(name || "").trim().split(/\s+/).slice(0, 2).map(function (w) { return w.charAt(0); }).join("").toUpperCase() || "?";
  }
  function first(name) { return String(name || "").trim().split(/\s+/)[0] || ""; }
  function plural(n, one, many) { return n + " " + (n === 1 ? one : (many || one + "s")); }
  function imgUrl(kind, v) { return API + "/api/me/image?k=" + kind + "&v=" + encodeURIComponent(v || ""); }
  function note(el, text, bad) { el.textContent = text || ""; el.className = "ac-note" + (bad ? " ac-note--bad" : ""); }
  function costs() { return DATA.costs || {}; }
  // What credits buy, in the client's terms: +5 = 1 free AI shortlist.
  function buys(n) {
    var c = costs(), brief = c.brief || 5, rep = c.replace || 2, chat = c.chat || 1;
    if (n >= brief && n % brief === 0) return n === brief ? "1 free AI shortlist" : (n / brief) + " more AI shortlists";
    if (n === rep) return "1 replacement search";
    return Math.floor(n / chat) + " questions to Helvi";
  }
  var SIG = { good: "Strong", moderate: "Fair", low: "Low" };
  function sig(grade, label) { return h("span", { class: "ac-sig ac-sig--" + (grade || "none") }, label || SIG[grade] || "Too early"); }
  function stamp(v) { return h("span", { class: "ac-verdict ac-verdict--" + (v.grade || "none") }, v.label || "Getting started"); }

  /* -------------------------------------------------------------- side nav */

  // The ROI Calculator is switched off for now (Bido, 2026-10-12). Set false here and in connect.js to bring it back.
  var ROI_LOCKED = true;
  var NAV = [["overview", "Overview", "home"], ["selections", "Selections", "list"], ["analyses", "Analyses", "scan"],
             ["campaigns", "Campaigns", "mega"], ["briefs", "Briefs", "brief"], ["roi", "ROI Calculator", "calc"], ["notifications", "Notifications", "bell"],
             ["credits", "Credits", "coin"], ["hr"], ["account", "Account", "user"]];

  function face(u, cls) {
    var f = h("span", { class: cls || "hc-face", "aria-hidden": "true" });
    if (u.photo) f.appendChild(h("img", { src: imgUrl("photo", u.photo), alt: "" }));
    else f.textContent = initials(u.name);
    return f;
  }
  function pending() { return DATA.analyses.filter(function (a) { return a.state === "requested"; }); }
  function countFor(key) {
    if (key === "overview") return DATA.cc && NEEDS.data ? NEEDS.data.total || null : null;
    if (key === "selections") return DATA.selections.length || null;
    if (key === "analyses") return staffInbox() ? (AINBOX.data ? AINBOX.data.filter(function (x) { return x.state === "open"; }).length || null : null) : pending().length || null;
    if (key === "campaigns") return DATA.insights.live_campaigns || null;
    if (key === "notifications") return DATA.notifications.unread || null;
    if (key === "credits") return DATA.credits != null ? DATA.credits : null;
    if (key === "clients") return CLIENTS ? CLIENTS.clients.length || null : null;
    if (key === "companies") return HUB.list ? HUB.list.length || null : null;
    return null;
  }
  function navItems() {
    // A key account manager: her clients sit right under her own overview; staff also get the Companies hub.
    var out = [NAV[0]];
    if (DATA.is_kam) out.push(["clients", "My clients", "users"]);
    if (DATA.hub) out.push(["companies", "Companies", "users"]);
    return out.concat(NAV.slice(1));
  }
  function renderSide() {
    var u = DATA.user, side = $("hc-side");
    side.textContent = "";
    side.appendChild(h("div", { class: "hc-me" }, face(u),
      h("div", null, h("b", null, u.name || u.email), h("small", null, [u.job_title, u.company].filter(Boolean).join(" · ") || u.email))));
    var nav = h("nav", { class: "hc-nav", "aria-label": "Your profile" });
    navItems().forEach(function (it) {
      if (it[0] === "hr") { nav.appendChild(h("hr")); return; }
      var n = countFor(it[0]);
      var lockd = it[0] === "roi" && ROI_LOCKED;
      var a = h("a", { href: lockd ? null : "#" + it[0], "aria-current": it[0] === SECTION ? "page" : null, "data-nav": it[0], class: lockd ? "is-locked" : null,
                       "aria-disabled": lockd ? "true" : null, title: lockd ? "Coming soon: the ROI Calculator is being improved." : null },
                  icon(lockd ? "lock" : it[2]), it[1]);
      if (lockd) a.appendChild(h("span", { class: "n", style: "font-size:11px" }, "Soon"));
      if (n != null) a.appendChild(h("span", { class: "n" + (it[0] === "notifications" || it[0] === "overview" ? " n--new" : it[0] === "credits" ? " n--credit" : ""), "data-count": it[0] }, String(n)));
      else if (it[0] === "overview" && DATA.cc) a.appendChild(h("span", { class: "n n--new", "data-count": "overview", hidden: "" }, ""));
      nav.appendChild(a);
    });
    side.appendChild(nav);
    if (DATA.cc && DATA.cc.admin_links) side.appendChild(controlCentre());
    var out = h("button", { class: "hc-more", type: "button", onclick: signOut }, icon("out"), "Sign out");
    // The onboarding film (item 179) replaces the old 3-minute tour.
    var how = h("a", { class: "hc-more", href: ROOT + "welcome/" }, icon("help"), "How HELVi works");
    side.appendChild(h("div", { class: "hc-out" }, how, out));
    var cur = nav.querySelector('[aria-current="page"]');
    if (cur && window.matchMedia("(max-width: 1100px)").matches) cur.scrollIntoView({ block: "nearest", inline: "center" });
  }
  // Item 209: the system controls stay in the admin, one click from the profile (owners and admins).
  var CC_LINKS = [["Creators", "users", "/roster"], ["Scoring rules", "target", "/reference"], ["Settings and keys", "gear", "/settings"],
                  ["People and access", "key", "/team"], ["History and undo", "redo", "/history"]];
  function controlCentre() {
    var links = h("div", { class: "cc-cc__links" });
    CC_LINKS.forEach(function (c) {
      links.appendChild(h("a", { href: adminUrl(c[2]), target: "_blank", rel: "noopener" }, icon(c[1]), h("span", null, c[0]), icon("ext")));
    });
    return h("section", { class: "cc-cc", "aria-label": "Control Centre" },
      h("a", { class: "cc-cc__open", href: adminUrl("/"), target: "_blank", rel: "noopener" }, icon("grid"),
        h("span", null, h("b", null, "Control Centre"), h("small", null, "System controls open in the admin")), icon("ext")),
      links);
  }
  function signOut() { (function () { try { sessionStorage.removeItem("hv-roster"); } catch (e) { /* blocked */ } })(), api("POST", "/api/auth/logout", {}).then(function (r) { if (r.b && r.b.admin_session) { try { sessionStorage.setItem("hv-admin-still", "1"); } catch (e) { /* blocked */ } } location.href = ROOT; }); }

  // Credits count up when a reward lands, so the reward is seen as well as said.
  function countUp(from, to) {
    DATA.credits = to;
    var el = document.querySelector('[data-count="credits"]');
    if (!el || from === to || window.matchMedia("(prefers-reduced-motion: reduce)").matches) { if (el) el.textContent = String(to); return; }
    var t0 = null, d = 900;
    function step(t) {
      t0 = t0 || t;
      var k = Math.min(1, (t - t0) / d), e = 1 - Math.pow(1 - k, 3);
      el.textContent = String(Math.round(from + (to - from) * e));
      if (k < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  var toastTimer = null;
  function toast(n, text) {
    var t = $("hc-toast");
    t.textContent = "";
    if (n) t.appendChild(h("span", { class: "hc-reward" }, "+" + n));       // 0 = a plain message (e.g. "Selection deleted.")
    t.appendChild(h("span", null, text));
    t.hidden = false;
    t.style.animation = "none"; void t.offsetWidth; t.style.animation = "";
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.hidden = true; }, 5200);
  }
  function celebrate(earned, credits) {
    if (!earned || !earned.length) { if (credits != null) DATA.credits = credits; return; }
    var total = earned.reduce(function (s, e) { return s + e.credits; }, 0);
    var before = DATA.credits;
    toast(total, (earned.length === 1 ? earned[0].label.replace(/^Add your /, "Thanks for your ") : "Profile rewards") + ". That's " + buys(total) + ".");
    countUp(before, credits != null ? credits : before + total);
  }

  /* -------------------------------------------------------------- overview */

  function greeting() {
    var hr = new Date().getHours();
    return hr < 12 ? "Morning" : hr < 17 ? "Afternoon" : "Evening";
  }
  function greet() {
    var u = DATA.user, nx = DATA.next;
    var hi = h("h1", { class: "hc-greet__hi" }, greeting() + ", ", h("span", null, first(u.name) || "there"));
    // Admin access is only a label on this account (the switch for locked data is in the menu).
    if (HV().me && HV().me.staff) hi.appendChild(h("small", { class: "hc-admintag" }, "Administrator"));
    var p = h("p", null, nx.lead, h("b", { class: nx.kind === "profile" ? "hc-credit" : null }, nx.strong), nx.tail);
    var later = "hc-later:" + nx.kind + ":" + nx.href;
    var go = h("div", { class: "hc-bubble__go" });
    if (store(later)) {
      go.appendChild(h("span", { class: "ac-muted" }, "Saved for later. It's here whenever you're ready."));
      go.appendChild(h("a", { class: "hc-more", href: ROOT + nx.href }, nx.cta));
    } else {
      var cta = h("a", { class: "hc-btn", href: ROOT + nx.href }, nx.cta, " ", icon("arrow"));
      if (!nx.href) cta.addEventListener("click", function (e) { if (HV().talk) { e.preventDefault(); HV().talk(); } });
      go.appendChild(cta);
      go.appendChild(h("button", { class: "hc-more", type: "button", onclick: function () { store(later, "1"); renderSection(); } }, "Later"));
    }
    // Helvi's idle loop (transparent, waist-up); the still when motion is reduced or refused.
    var img = HV().clip ? HV().clip("idle", "hc-greet__clip") : h("img", { class: "hv-clip", src: HV().helvy || ROOT + "assets/brand/helvy.webp?v=c2", alt: "", width: "148", height: "148" });
    return h("section", { class: "hc-greet", "aria-label": "Helvi's next step for you" },
      h("div", { class: "hc-greet__helvy" }, img),
      h("div", { class: "hc-greet__body" }, hi,
        h("div", { class: "hc-bubble" }, h("div", { class: "hc-bubble__who" }, h("b", null, "Helvi"), " · your next step"), p, go)));
  }
  function scoreline() {
    var mine = DATA.selections.filter(function (s) { return s.mine && s.counts.review; }).length;
    var pend = pending();
    var soon = pend.map(function (a) { return a.ready_by; }).sort()[0];
    var monthly = DATA.monthly_credits;
    function cell(term, fig, sub, link, href) {
      return h("div", null, h("dt", null, term), h("dd", { class: "hc-score__fig" }, fig),
        h("dd", { class: "hc-score__sub" }, sub), h("dd", { class: "hc-score__go" }, h("a", { class: "hc-more", href: href }, link)));
    }
    return h("dl", { class: "hc-score" },
      cell("Active selections", String(DATA.selections.length),
        mine ? [h("b", null, String(mine)), " waiting for your review"] : "Nothing waiting for you", "Open selections", "#selections"),
      cell("Analyses pending", String(pend.length),
        pend.length ? ["Ready by ", h("b", null, shortDay(soon))] : "Free for creators in your selections", "Track requests", "#analyses"),
      cell("Credits left", [h("span", { class: "hv-credit-num" }, String(DATA.credits)), monthly && DATA.credits <= monthly ? h("small", null, "of " + monthly) : null],
        monthly ? ["Tops up to " + monthly + " on ", h("b", null, dm(DATA.next_refill))] : "Ask your account manager for more", "See credits", "#credits"));
  }
  function latest() {
    var items = DATA.notifications.items.slice(0, 4);
    var list = h("ul", { class: "hc-notes" });
    items.forEach(function (n) { var li = h("li"); li.appendChild(HV().noteRow(n, noteOpened)); list.appendChild(li); });
    return h("section", { class: "hc-panel", "aria-labelledby": "hc-latest" },
      h("div", { class: "hc-sechd" }, h("h2", { class: "hc-h2", id: "hc-latest" }, "Latest"), h("a", { class: "hc-more", href: "#notifications" }, "See all")),
      items.length ? list : h("p", { class: "ac-muted" }, "Nothing yet. When HelloVoice reviews a creator, answers an analysis request or updates a campaign, it shows here and in the bell."));
  }
  function noteOpened() {
    DATA.notifications.unread = Math.max(0, DATA.notifications.unread - 1);
    if (HV().setUnread) HV().setUnread(DATA.notifications.unread);
  }
  var STEP_IC = { photo: "camera", job_title: "case", phone: "phone", logo: "image", brands: "tag", industry_markets: "globe" };
  var STEP_WHY = { brands: "Helvi matches creators to them", industry_markets: "your briefs start filled in" };
  var STEP_FIELD = { photo: "photo", job_title: "job_title", phone: "phone", logo: "logo", brands: "brands", industry_markets: "industry" };
  function ring(pct) {
    var r = 58, c = 2 * Math.PI * r;
    var svg = '<svg viewBox="0 0 136 136" aria-hidden="true"><circle cx="68" cy="68" r="' + r + '" fill="none" stroke="#efede8" stroke-width="12"/>' +
      '<circle cx="68" cy="68" r="' + r + '" fill="none" stroke="#ff691e" stroke-width="12" stroke-linecap="round" stroke-dasharray="' + c.toFixed(1) +
      '" stroke-dashoffset="' + (c * (1 - pct / 100)).toFixed(1) + '"/></svg>';
    return h("div", { class: "hc-ring", role: "img", "aria-label": pct + "% of your profile is complete" },
      h("span", { html: svg }), h("div", { class: "hc-ring__in" }, h("b", null, pct + "%"), h("small", null, "Complete")));
  }
  function stepRow(s) {
    var b = h("button", { class: "hc-step", type: "button", "data-focus": STEP_FIELD[s.key],
      onclick: function () { focusField(STEP_FIELD[s.key]); } },
      h("span", { class: "hc-step__ic" }, icon(STEP_IC[s.key] || "plus")),
      h("span", null, h("b", null, s.label), h("small", null, h("em", null, "= " + buys(s.credits)), STEP_WHY[s.key] ? " · " + STEP_WHY[s.key] : " with Helvi")),
      h("span", { class: "hc-reward" }, "+" + s.credits));
    return h("li", null, b);
  }
  function finish() {
    var c = DATA.completion;
    var open = c.steps.filter(function (s) { return !s.paid; });
    var left = c.steps.filter(function (s) { return !s.done; }).length;
    var lead = c.waiting
      ? h("p", { class: "hc-done__lead" }, h("mark", null, plural(c.waiting, "credit") + " waiting"),
          left ? " for " + plural(left, "quick detail") + ". Helvi uses them to pre-fill your briefs." : ". Save your profile to collect them.")
      : h("p", { class: "hc-done__lead" }, "All profile credits earned. Helvi uses your details to pre-fill your briefs.");
    var steps = h("ul", { class: "hc-steps" });
    open.slice(0, 3).forEach(function (s) { steps.appendChild(stepRow(s)); });
    if (!c.bonus_paid) {
      steps.appendChild(h("li", null, h("div", { class: "hc-step hc-step--bonus" },
        h("span", { class: "hc-step__ic" }, icon("gift")),
        h("span", null, h("b", null, "Reach 100%"), h("small", null, h("em", null, "= " + buys(c.bonus)), " as a bonus")),
        h("span", { class: "hc-reward" }, "+" + c.bonus))));
    }
    var got = h("ul", { class: "hc-got", "aria-label": "Already earned" });
    c.steps.filter(function (s) { return s.paid; }).forEach(function (s) {
      got.appendChild(h("li", null, icon("check"), s.label.replace(/^Add your /, "").replace(/^./, function (x) { return x.toUpperCase(); }) + " +" + s.credits));
    });
    return h("section", { class: "hc-panel", "aria-labelledby": "hc-finish" },
      h("div", { class: "hc-done__top" }, ring(c.pct), h("div", null, h("h2", { class: "hc-h2", id: "hc-finish" }, c.pct >= 100 ? "Profile complete" : "Finish your profile"), lead)),
      steps.children.length ? steps : null, got.children.length ? got : null);
  }
  function inviteLink() { return new URL(ROOT + "?invite=" + encodeURIComponent(DATA.invite.token), location.href).href; }
  function copy(text, btn, done) {
    var ok = function () { var was = btn.textContent; btn.textContent = done || "Copied"; setTimeout(function () { btn.textContent = was; }, 1800); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, function () { window.prompt("Copy this link:", text); });
    else window.prompt("Copy this link:", text);
  }
  function inviteBand() {
    var inv = DATA.invite, worth = Math.floor(inv.credits / (costs().brief || 5));
    var btn = h("button", { class: "hc-btn hc-btn--ink", type: "button" }, icon("link"), " Copy invite link");
    btn.addEventListener("click", function () { copy(inviteLink(), btn, "Link copied"); });
    return h("section", { class: "hc-invite", "aria-labelledby": "hc-inv" },
      h("div", null, h("h2", { class: "hc-h2", id: "hc-inv" }, "Bring a colleague, get " + worth + " AI shortlists"),
        h("p", null, "Share your invite link with someone on your team. When HelloVoice approves their account and they sign in for the first time, you get " + inv.credits + " credits."),
        h("p", { class: "hc-invite__fine" }, "Same company email domain · up to " + inv.max + " paid invites" + (inv.paid ? " · " + inv.left + " left" : ""))),
      h("div", { class: "hc-invite__act" }, h("span", { class: "hc-invite__big", "aria-hidden": "true" }, "+" + inv.credits), btn));
  }
  // "How HELVi works" (item 179): the onboarding film's poster, one line, a way in. The film
  // itself plays on /welcome/, which loads it only when asked.
  var PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M8 5.5v13l11-6.5z" fill="currentColor"/></svg>';
  function howBand() {
    var href = ROOT + "welcome/";
    return h("section", { class: "hc-how", "aria-labelledby": "hc-how-t" },
      h("a", { class: "hc-how__film", href: href, tabindex: "-1", "aria-hidden": "true" },
        h("img", { src: ROOT + "assets/welcome/onboarding-poster.jpg?v=0", alt: "", loading: "lazy", decoding: "async", width: "640", height: "360" }),
        h("span", { class: "hc-how__play", html: PLAY })),
      h("div", { class: "hc-how__txt" },
        h("h2", { class: "hc-h2", id: "hc-how-t" }, "How HELVi works"),
        h("p", null, "A short film, start to finish: brief Helvi, shortlist creators, request a quote and follow every post."),
        h("a", { class: "hc-btn", href: href }, "Watch the film")));
  }
  /* ------------------------------------- the team's Overview (item 209, slice a) */

  // Admins and KAMs land on what is waiting for them; clients keep the Overview above.
  var NEEDS = { data: null, busy: null, err: false, mine: false };
  var NEED_IC = { signups: "users", overdue: "cal", quotes: "brief", analyses: "scan", access: "lock", red: "flag" };
  function adminUrl(path) { return API + path; }
  function loadNeeds() {
    if (NEEDS.busy) return NEEDS.busy;
    NEEDS.busy = api("GET", "/api/needs").then(function (r) {
      NEEDS.busy = null;
      if (r.s !== 200) { NEEDS.err = true; return; }
      NEEDS.err = false; NEEDS.data = r.b;
      var n = document.querySelector('[data-count="overview"]');
      if (n) { n.textContent = String(r.b.total || ""); n.hidden = !r.b.total; }
      if (SECTION === "overview") renderSection();
    });
    return NEEDS.busy;
  }
  function ageOf(ts) {
    if (!ts) return "";
    var s = Date.now() / 1000 - ts;
    return s < 3600 ? Math.max(1, Math.floor(s / 60)) + "m" : s < 86400 ? Math.floor(s / 3600) + "h" : Math.floor(s / 86400) + "d";
  }
  function monogram(name) {
    return h("span", { class: "cc-mono", "aria-hidden": "true" }, initials(name || "?"));
  }
  function teamGreet() {
    var u = DATA.user, q = NEEDS.data, n = q ? q.total : null, first_g = q && q.groups[0];
    var line = n == null ? "Checking what needs you…" : !n ? "Nothing is waiting on you right now." :
      (n === 1 ? "1 thing needs you today." : n + " things need you today.");
    var hi = h("h1", null, greeting() + ", ", h("span", null, first(u.name) || "there"),
      h("small", { class: "hc-admintag" }, DATA.cc.team_role === "owner" ? "Owner" : DATA.cc.role === "kam" ? "Account manager" : "Administrator"));
    var tail = first_g ? " Start with " + first_g.title.toLowerCase() + "." : "";
    var go = first_g ? h("div", { class: "cc-greet__go" }, h("a", { class: "hc-btn", href: "#needs-" + first_g.key,
      onclick: function (e) { var t = document.getElementById("needs-" + first_g.key); if (t) { e.preventDefault(); t.scrollIntoView({ behavior: "smooth", block: "start" }); } } },
      "Start here ", icon("arrow"))) : null;
    var img = h("img", { src: HV().helvy || ROOT + "assets/brand/helvy.webp?v=c2", alt: "", width: "84", height: "84" });
    return h("section", { class: "cc-greet", "aria-label": "Today" }, img,
      h("div", null, hi, h("p", null, h("b", null, line), tail)), go);
  }
  function needAction(g, it) {
    if (g.key === "signups") {
      var msg = h("span", { class: "cc-msg", role: "status" });
      var b = h("button", { class: "hc-btn hc-btn--sm", type: "button" }, "Approve");
      b.addEventListener("click", function () {
        b.disabled = true; b.textContent = "Approving…";
        api("POST", "/api/needs/approve", { id: it.id }).then(function (r) {
          if (r.s === 200) { toast(0, r.b.message || "Approved."); NEEDS.data = null; loadNeeds(); }
          else { b.disabled = false; b.textContent = "Approve"; msg.textContent = (r.b && r.b.message) || "Could not approve. Try again."; }
        });
      });
      return h("div", { class: "cc-act" }, b, msg);
    }
    if (it.act === "company") return h("div", { class: "cc-act" }, h("button", { class: "hc-more", type: "button", onclick: function () { openCompany(it.key); } }, "Open the company"));
    if (g.key === "overdue") return h("div", { class: "cc-act" }, h("a", { class: "hc-more", href: ROOT + "campaign/#t=" + encodeURIComponent(it.token || "") }, "Open the campaign"));
    if (g.key === "analyses") return h("div", { class: "cc-act" }, h("a", { class: "hc-more", href: "#analyses" }, "Open the inbox"));
    if (it.href && DATA.cc.admin_links) return h("div", { class: "cc-act" },
      h("a", { class: "cc-admin", href: adminUrl(it.href), target: "_blank", rel: "noopener" }, "Answer in admin ", icon("ext")));
    return h("div", { class: "cc-act" }, h("span", { class: "ac-muted" }, "An admin answers this"));
  }
  function needsQueue() {
    var q = NEEDS.data;
    var sec = h("section", { "aria-labelledby": "q-h" });
    var seg = h("div", { class: "cc-seg", role: "group", "aria-label": "Whose items" });
    var hd = h("div", { class: "cc-qhead" }, h("div", null, h("h2", { class: "hc-h2", id: "q-h" }, "Needs you"),
      h("p", null, DATA.cc.role === "kam" ? "Your clients only. Oldest first inside each group." : "Every client. Oldest first inside each group.")));
    add(sec, hd);
    if (!q) {
      add(sec, NEEDS.err ? h("div", { class: "hc-empty" }, h("b", null, "The queue did not load."),
        h("p", null, h("button", { class: "hc-more", type: "button", onclick: function () { NEEDS.err = false; loadNeeds(); renderSection(); } }, "Try again")))
        : h("div", { class: "cc-q cc-q--loading", "aria-busy": "true" }, h("div", { class: "cc-skel" }), h("div", { class: "cc-skel" }), h("div", { class: "cc-skel" })));
      return sec;
    }
    if (!q.groups.length) {
      add(sec, h("div", { class: "hc-empty" }, h("b", null, "All clear."),
        h("p", null, "New sign-ups, overdue next steps, unanswered quotes and analysis requests land here as they come in.")));
      return sec;
    }
    var box = h("div", { class: "cc-q" });
    q.groups.forEach(function (g) {
      var ic = h("span", { class: "cc-q__ic" + (g.key === "signups" ? " cc-q__ic--hot" : g.key === "overdue" || g.key === "red" ? " cc-q__ic--red" : "") }, icon(NEED_IC[g.key] || "bell"));
      var rows = h("ul", { class: "cc-q__rows" });
      g.items.forEach(function (it) {
        var late = it.at && (Date.now() / 1000 - it.at) > (g.key === "overdue" ? 0 : 86400);
        rows.appendChild(h("li", null, monogram(it.company || it.title),
          h("div", { class: "cc-q__what" }, h("b", null, it.title), h("small", null, it.sub || "")),
          h("span", { class: "cc-age" + (late ? " cc-age--late" : ""), title: g.key === "overdue" ? "Days late" : "Waiting" }, icon("clock"), ageOf(it.at)),
          needAction(g, it)));
      });
      var more = g.count > g.items.length ? h("p", { class: "cc-q__more ac-muted" }, (g.count - g.items.length) + " more in this group") : null;
      box.appendChild(h("div", { class: "cc-q__grp", id: "needs-" + g.key },
        h("div", { class: "cc-q__hd" }, ic, h("div", null, h("h3", null, g.title), h("small", null, g.hint)), h("span", { class: "cc-q__n" }, String(g.count))),
        rows, more));
    });
    add(sec, box);
    return sec;
  }
  function teamStrip() {
    var k = NEEDS.data && NEEDS.data.kpis;
    if (!k) return null;
    function cell(term, fig, sub, link) {
      return h("div", null, h("dt", null, term), h("dd", { class: "hc-score__fig" }, fig), h("dd", { class: "hc-score__sub" }, sub),
        h("dd", { class: "hc-score__go" }, link));
    }
    var adminLink = DATA.cc.admin_links ? h("a", { class: "cc-admin", href: adminUrl("/portal"), target: "_blank", rel: "noopener" }, "Usage in admin ", icon("ext")) : null;
    return h("section", { "aria-labelledby": "k-h" },
      h("div", { class: "hc-sechd" }, h("h2", { class: "hc-h2", id: "k-h" }, "This month"), DATA.hub ? h("a", { class: "hc-more", href: "#companies" }, "All companies") : null),
      h("dl", { class: "hc-score hc-score--4" },
        cell("Live campaigns", String(k.live), "Running now", h("a", { class: "hc-more", href: ROOT + "campaign/" }, "Open the board")),
        cell("Open quotes", String(k.quotes), k.quotes ? "Waiting for an answer" : "None waiting", DATA.cc.admin_links ? h("a", { class: "cc-admin", href: adminUrl("/requests"), target: "_blank", rel: "noopener" }, "Quotes in admin ", icon("ext")) : null),
        cell("Companies", String(k.companies), k.waiting ? [h("b", null, String(k.waiting)), " sign-ups waiting"] : "No sign-ups waiting", h("a", { class: "hc-more", href: "#companies" }, "Open the list")),
        cell("Client credits used", String(k.credits_used), "Last 30 days · " + plural(k.credit_people, "client"), adminLink)));
  }
  function renderTeamOverview(p) {
    if (!NEEDS.data && !NEEDS.err) loadNeeds();
    add(p, teamGreet());
    add(p, needsQueue());
    add(p, teamStrip());
    add(p, latest());
  }

  /* Step-up (item 209): a fresh emailed code before a sensitive change (suspend, credits, a large push).
     hvStepUp({title, what, sub, ok}) resolves true once the code is right (or the 10-minute window is
     still open), false when the person cancels. Used by the account controls (slice b). */
  function stepUp(o) {
    o = o || {};
    if (DATA.cc && DATA.cc.stepup > 0 && DATA.cc.stepup_at && (Date.now() - DATA.cc.stepup_at) / 1000 < DATA.cc.stepup) return Promise.resolve(true);
    return new Promise(function (resolve) {
      var dlg = h("dialog", { class: "cc-dlg", "aria-labelledby": "su-h" });
      var boxes = [], msg = h("p", { class: "cc-dlg__err", role: "alert" }), timer = h("span", null, "");
      var okBtn = h("button", { class: "hc-btn " + (o.danger ? "hc-btn--danger" : ""), type: "button", disabled: "" }, o.ok || "Confirm");
      var cancel = h("button", { class: "hc-btn hc-btn--line", type: "button" }, "Cancel");
      var resend = h("button", { type: "button" }, "Send a new code");
      var codeRow = h("div", { class: "cc-code", role: "group", "aria-label": "6-digit code" });
      for (var i = 0; i < 6; i++) {
        var inp = h("input", { inputmode: "numeric", autocomplete: i === 0 ? "one-time-code" : "off", maxlength: "6", "aria-label": "Digit " + (i + 1) });
        boxes.push(inp); codeRow.appendChild(inp);
      }
      function code() { return boxes.map(function (b) { return b.value; }).join(""); }
      boxes.forEach(function (b, i) {
        b.addEventListener("input", function () {
          var v = b.value.replace(/\D/g, "");
          if (v.length > 1) { v.split("").slice(0, 6 - i).forEach(function (d, j) { boxes[i + j].value = d; }); }   // a pasted code fills the row
          else b.value = v;
          var nx = boxes[Math.min(5, i + Math.max(1, v.length))];
          if (v && nx) nx.focus();
          okBtn.disabled = code().length !== 6;
        });
        b.addEventListener("keydown", function (e) { if (e.key === "Backspace" && !b.value && boxes[i - 1]) boxes[i - 1].focus(); });
      });
      var left = 0, tick = null;
      function startClock(min) {
        left = (min || 10) * 60; clearInterval(tick);
        tick = setInterval(function () {
          left -= 1;
          timer.textContent = left > 0 ? "Code works for " + Math.floor(left / 60) + ":" + ("0" + (left % 60)).slice(-2) : "This code has expired";
          if (left <= 0) clearInterval(tick);
        }, 1000);
      }
      function send() {
        msg.textContent = ""; resend.disabled = true;
        api("POST", "/api/stepup/send", {}).then(function (r) {
          resend.disabled = false;
          if (r.s === 200) { to.textContent = r.b.to; startClock(r.b.minutes); boxes[0].focus(); }
          else msg.textContent = (r.b && r.b.message) || "The code could not be sent. Try again.";
        });
      }
      function close(v) { clearInterval(tick); dlg.close(); dlg.remove(); resolve(v); }
      okBtn.addEventListener("click", function () {
        okBtn.disabled = true; msg.textContent = "";
        api("POST", "/api/stepup/verify", { code: code() }).then(function (r) {
          if (r.s === 200) { DATA.cc.stepup = r.b.seconds; DATA.cc.stepup_at = Date.now(); close(true); }
          else { okBtn.disabled = false; msg.textContent = (r.b && r.b.message) || "That code is not right."; boxes.forEach(function (b) { b.value = ""; }); boxes[0].focus(); okBtn.disabled = true; }
        });
      });
      cancel.addEventListener("click", function () { close(false); });
      resend.addEventListener("click", send);
      dlg.addEventListener("cancel", function (e) { e.preventDefault(); close(false); });
      var to = h("b", null, DATA.user.email);
      dlg.appendChild(h("div", { class: "cc-dlg__in" },
        h("span", { class: "cc-dlg__ic" }, icon("shield")),
        h("h2", { id: "su-h" }, o.title || "Confirm it's you"),
        h("p", null, (o.why ? o.why + " " : "") + "We emailed a 6-digit code to ", to, "."),
        o.what ? h("div", { class: "cc-what" }, h("div", null, h("b", null, o.what), o.sub ? h("small", null, o.sub) : null)) : null,
        codeRow, h("div", { class: "cc-codemeta" }, timer, resend), msg,
        h("div", { class: "cc-dlg__act" }, cancel, okBtn),
        h("p", { class: "cc-dlg__fine" }, icon("redo"), "Saved in History with undo. One code covers 10 minutes of changes.")));
      document.body.appendChild(dlg);
      dlg.showModal();
      send();
    });
  }
  window.hvStepUp = function (o) { return DATA && DATA.cc ? stepUp(o) : Promise.resolve(false); };

  function renderOverview(p) {
    if (DATA.cc) { renderTeamOverview(p); return; }
    add(p, greet());
    add(p, scoreline());
    add(p, h("div", { class: "hc-cols" }, latest(), finish()));
    add(p, howBand());
    if (DATA.invite.left > 0) add(p, inviteBand());
  }

  /* ------------------------------------------------------------ selections */

  function statusSigs(c) {
    var out = [];
    if (c.approved) out.push(h("span", { class: "hc-sig hc-sig--ok" }, c.approved + " approved"));
    if (c.rejected) out.push(h("span", { class: "hc-sig hc-sig--no" }, c.rejected + " rejected"));
    if (c.review) out.push(h("span", { class: "hc-sig hc-sig--wait" }, c.review + " under review"));
    if (c.unavailable) out.push(h("span", { class: "hc-sig hc-sig--off" }, c.unavailable + " unavailable"));
    return out;
  }
  function head(title, lead, side) {
    return h("div", { class: "hc-head" }, h("div", null, h("h1", { class: "hc-h1" }, title), lead ? h("p", null, lead) : null), side || null);
  }
  /* ------------------------------------------------- delete, with a confirm */

  // The bin, drawn like the portal's icons (portal.js has none to borrow).
  var BIN = '<svg class="hv-i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" ' +
    'stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4.5 6.5h15M9.5 6.5V4.5h5v2M6.5 6.5l1 13h9l1-13M10.5 10.5v6M13.5 10.5v6"/></svg>';
  // Ask before deleting: a real modal (focus kept inside, Escape or Cancel closes, focus goes back
  // to the button that opened it). Cancel has the first focus so Enter never deletes by accident.
  function confirmDelete(opts, opener) {
    var back = h("div", { class: "hc-dlg-back" });
    var msg = h("p", { class: "hc-dlg__err", role: "alert", hidden: true });
    var cancel = h("button", { class: "hc-btn hc-btn--line hc-btn--sm", type: "button" }, "Cancel");
    var go = h("button", { class: "hc-btn hc-btn--sm hc-btn--danger", type: "button" }, h("span", { class: "hc-icw", "aria-hidden": "true", html: BIN }), opts.action);
    var box = h("div", { class: "hc-dlg", role: "dialog", "aria-modal": "true", "aria-labelledby": "hc-dlg-t", "aria-describedby": "hc-dlg-d" },
      h("h2", { class: "hc-dlg__t", id: "hc-dlg-t" }, opts.title),
      h("p", { id: "hc-dlg-d" }, opts.body), msg,
      h("div", { class: "hc-dlg__go" }, cancel, go));
    back.appendChild(box);
    function close() {
      document.removeEventListener("keydown", key, true);
      back.remove();
      document.body.classList.remove("hc-dlg-open");
      if (opener && document.contains(opener)) opener.focus();
    }
    function key(e) {
      if (e.key === "Escape") { e.preventDefault(); close(); return; }
      if (e.key !== "Tab") return;
      var f = [cancel, go].filter(function (b) { return !b.disabled; });
      var i = f.indexOf(document.activeElement);
      if (e.shiftKey ? i <= 0 : i === f.length - 1) { e.preventDefault(); f[e.shiftKey ? f.length - 1 : 0].focus(); }
    }
    back.addEventListener("click", function (e) { if (e.target === back) close(); });
    cancel.addEventListener("click", close);
    go.addEventListener("click", function () {
      go.disabled = cancel.disabled = true;
      msg.hidden = true;
      opts.run().then(function (err) {
        if (!err) { opener = null; close(); return; }
        go.disabled = cancel.disabled = false;
        msg.textContent = err; msg.hidden = false; cancel.focus();
      });
    });
    document.addEventListener("keydown", key, true);
    document.body.classList.add("hc-dlg-open");
    document.body.appendChild(back);
    cancel.focus();
  }
  function delBtn(label, onclick) {
    return h("button", { class: "hc-del", type: "button", "aria-label": label, title: label, onclick: onclick },
      h("span", { class: "hc-icw", "aria-hidden": "true", html: BIN }), h("span", { class: "hc-del__t" }, "Delete"));
  }
  // After a delete the list re-renders: the focus lands on the section heading, the result is said once.
  function afterDelete(text) {
    renderSide(); renderSection();
    var h1 = document.querySelector("#hc-body .hc-h1");
    if (h1) { h1.setAttribute("tabindex", "-1"); h1.focus(); }
    toast(0, text);
  }
  // Admins: delete any selection (History can restore it); one a campaign still uses points to the campaign instead.
  function adminDeleteSelection(s, btn) {
    confirmDelete({ title: "Delete “" + s.name + "”?", action: "Delete selection",
      body: "It leaves every list and its briefs go with it. You can bring it back from History in the admin. A selection a campaign uses can't be deleted here: delete the campaign instead.",
      run: function () {
        return api("POST", "/api/hub/delete", { kind: "selection", ref: s.id }).then(function (r) {
          if (!(r.b && r.b.ok)) return (r.b && r.b.message) || "Couldn't delete it. Please try again.";
          DATA.selections = DATA.selections.filter(function (x) { return x.token !== s.token; });
          HUB.list = null; HUB.detail = {}; ALLC.items = null;
          afterDelete("Selection deleted.");
          return null;
        });
      } }, btn);
  }
  function deleteSelection(s, btn) {
    confirmDelete({ title: "Delete “" + s.name + "”?", action: "Delete selection",
      body: "It leaves your profile and its link stops opening, for you and your colleagues. Your approvals and notes on it go too. HelloVoice keeps a copy for your account manager.",
      run: function () {
        return api("POST", "/api/selection/delete", { token: s.token }).then(function (r) {
          if (!r.b.ok) return r.s === 403 ? "Only selections you made can be deleted."
            : r.b.reason === "in_campaign" ? "The campaign " + (r.b.campaigns || []).map(function (n) { return "“" + n + "”"; }).join(", ") + " uses this selection, so it stays. Ask your account manager to take it out of the campaign first."
            : "Couldn't delete it. Please try again.";
          DATA.selections = DATA.selections.filter(function (x) { return x.token !== s.token; });
          DATA.briefs.forEach(function (b) { if (b.selection === s.token) { b.selection = null; b.selection_name = null; } });
          afterDelete("Selection deleted.");
          return null;
        });
      } }, btn);
  }
  function deleteBrief(b, btn) {
    confirmDelete({ title: "Delete this brief?", action: "Delete brief",
      body: b.selection ? "Its selection stays, but its creators are no longer scored until you give it a campaign objective again." : "It leaves your profile. HelloVoice keeps a copy for your account manager.",
      run: function () {
        return api("POST", "/api/brief/delete", { id: b.id }).then(function (r) {
          if (!r.b.ok) return r.s === 403 ? "Only briefs you wrote can be deleted." : "Couldn't delete it. Please try again.";
          DATA.briefs = DATA.briefs.filter(function (x) { return x.id !== b.id; });
          afterDelete("Brief deleted.");
          return null;
        });
      } }, btn);
  }
  // A row that opens something and may also carry a Delete button: the link covers the row
  // (stretched), the button sits above it, so neither is nested in the other.
  function actRow(href, body, go, del) {
    var link = href ? h("a", { class: "hc-row__go hc-row__link", href: href }, go) : (go ? h("span", { class: "hc-row__go" }, go) : null);
    return h("div", { class: "hc-row hc-row--act" + (href ? " is-link" : "") }, body, h("span", { class: "hc-row__acts" }, del || null, link));
  }

  // The quote lifecycle chip (connect.js draws it once for every page; this is the fallback if
  // that file has not loaded yet).
  function qchip(q) {
    if (!q || !q.key) return null;
    var f = HV().lifecycleChip;
    return f ? f(q) : h("span", { class: "lc-chip lc-chip--" + q.key }, h("i", { "aria-hidden": "true" }), q.label);
  }
  /* ------------------------------------------- the board (item 194, owner 2026-10-20) */
  // Selections and Campaigns open on a six-column board (window.HVBoard, assets/js/hv-board.js), with List
  // beside it. Everyone drags what is theirs between the planning columns; the server decides (admin/board.py).
  var SEL_STAGES = [
    { key: "draft", label: "Draft", hint: "Named, no creators yet" },
    { key: "shortlisting", label: "Shortlisting", hint: "Creators being chosen" },
    { key: "review", label: "Client review", hint: "Being decided, quote asked" },
    { key: "approved", label: "Approved", hint: "Agreed, being set up" },
    { key: "live", label: "Live", hint: "Its campaign is running" },
    { key: "completed", label: "Completed", hint: "Its campaign has ended" }];
  function boardOn() { return !!window.HVBoard; }
  function viewHead(key, rerender) {
    return boardOn() ? HVBoard.viewSwitch(key, HVBoard.viewOf(key), function () { rerender(); }) : null;
  }
  function headTools() {
    var w = h("div", { class: "hc-head__tools" });
    for (var i = 0; i < arguments.length; i++) add(w, arguments[i]);
    return w;
  }
  function renderSelectionBoard(p, view) {
    HVBoard.mount(p, {
      stages: SEL_STAGES, noun: "selection", locked: ["live", "completed"], view: view,
      items: DATA.selections.map(function (s) { return HVBoard.fromSelection(s, qchip(s.quote)); }),
      onMove: function (it, to) {
        return api("POST", "/api/board/selection-stage", { s: it.key, to: to }).then(function (r) {
          if (r.b && r.b.ok) {
            var s = DATA.selections.filter(function (x) { return x.token === it.key; })[0];
            if (s) { s.stage = to; s.moves = it.moves.slice(); }
          }
          return r.b || {};
        });
      }
    });
  }

  function renderSelections(p) {
    var view = boardOn() ? HVBoard.viewOf("selections") : "list";
    add(p, head("Selections", view !== "list"
        ? "Every selection by where it stands. Drag one to another column, or use Move to. Your account manager sees every change."
        : "Approve the creators you want and reject the ones you don't. Your account manager sees every change and quotes the approved list.",
      headTools(DATA.selections.length ? viewHead("selections", renderSection) : null,
        h("a", { class: "hc-btn hc-btn--line hc-btn--sm", href: ROOT + "#cat-roster" }, "Browse creators"))));
    if (DATA.selections.length && view !== "list") { renderSelectionBoard(p, view); return; }
    if (!DATA.selections.length) {
      add(p, h("div", { class: "hc-empty" }, h("b", null, "No selections yet"),
        h("p", null, "Pick creators in the catalogue, or let Helvi build a scored shortlist from a short brief."),
        h("a", { class: "hc-btn", href: ROOT }, "Find creators")));
      return;
    }
    var list = h("ul", { class: "hc-list" });
    DATA.selections.forEach(function (s) {
      var c = s.counts;
      // Delete only on the client's own selections: never a colleague's or one HelloVoice shared.
      var del = s.can_delete ? delBtn("Delete " + s.name, function () { deleteSelection(s, this); })
        : (s.admin_delete ? delBtn("Delete " + s.name, function () { adminDeleteSelection(s, this); }) : null);
      // Rename in place (item 173): the owner only; connect.js draws the control and the field.
      var nm = h("span", { class: "hc-row__name" }, s.name);
      var ren = s.can_rename && HV().renameButton ? HV().renameButton({ shown: nm, token: s.token, size: "row", label: s.name,
        name: function () { return s.name; },
        done: function (n) { s.name = n; DATA.briefs.forEach(function (b) { if (b.selection === s.token) b.selection_name = n; }); nm.textContent = n;
          var sr = nm.closest(".hc-row") && nm.closest(".hc-row").querySelector(".hc-row__link .hc-sr"); if (sr) sr.textContent = " " + n; } }) : null;
      if (ren || del) del = h("span", { class: "hc-row__tools" }, ren, del);
      list.appendChild(h("li", null, actRow(ROOT + "selection/#s=" + encodeURIComponent(s.token),
        h("div", null, nm, " ", qchip(s.quote),
          h("div", { class: "hc-row__meta" },
            h("span", null, plural(c.creators, "creator") + (c.doctors ? " · " + plural(c.doctors, "doctor") : "")),
            statusSigs(c), h("span", null, (s.owner ? s.owner + "'s · " : "") + "updated " + ago(s.updated_at)))),
        [s.mine && c.review ? "Review" : "Open", h("span", { class: "hc-sr" }, " " + s.name), " ", icon("arrow")], del)));
    });
    add(p, list);
  }

  /* -------------------------------------------------------------- analyses */

  /* -------------------------------- the admin's analysis inbox (item 195, owner 2026-10-20) */
  // Admins (every client) and KAMs (their clients) get the requests, not their own: grouped client, then the
  // campaign (or selection) the creator sits in. Approve opens the analysis to the person who asked, only them;
  // Reject tells them, with an optional note. The server checks both (portal_api /api/analysis/*).
  var AINBOX = { data: null, busy: null, filter: "open", err: false };
  function staffInbox() { return DATA.hub === "admin" || DATA.hub === "kam" || DATA.is_kam; }
  function loadInbox() {
    if (AINBOX.busy) return AINBOX.busy;
    AINBOX.busy = api("GET", "/api/analysis/inbox").then(function (r) {
      AINBOX.busy = null;
      AINBOX.err = !(r.b && r.b.ok);
      if (!AINBOX.err) AINBOX.data = r.b.requests;
      var n = document.querySelector('[data-nav="analyses"]');
      if (n && AINBOX.data) {
        var open = AINBOX.data.filter(function (x) { return x.state === "open"; }).length;
        var b = n.querySelector(".n");
        if (!b && open) { b = h("span", { class: "n n--new" }); n.appendChild(b); }
        if (b) { b.textContent = String(open); b.hidden = !open; }
      }
      return AINBOX.data;
    });
    return AINBOX.busy;
  }
  var INBOX_STATES = [["open", "Waiting"], ["approved", "Approved"], ["rejected", "Rejected"], ["all", "All"]];
  function inboxRow(r) {
    var note = h("p", { class: "ai-row__msg", role: "status", "aria-live": "polite" });
    var acts = h("div", { class: "ai-row__acts" });
    function done(b, msg) {
      note.textContent = msg || "";
      note.className = "ai-row__msg" + (b ? "" : " is-bad");
      if (b) { AINBOX.data = null; setTimeout(function () { if (SECTION === "analyses") renderSection(); }, 900); }
    }
    if (r.state === "open") {
      var yes = h("button", { type: "button", class: "hc-btn hc-btn--sm", disabled: !r.has_analysis || null,
        title: r.has_analysis ? "Open " + r.creator + "'s full analysis to " + r.user : "No analysis on file yet" }, "Approve");
      var no = h("button", { type: "button", class: "hc-btn hc-btn--line hc-btn--sm" }, "Reject");
      yes.addEventListener("click", function () {
        yes.disabled = no.disabled = true;
        api("POST", "/api/analysis/decide", { id: r.id, ok: true }).then(function (x) {
          if (!(x.b && x.b.ok)) { yes.disabled = no.disabled = false; }
          done(x.b && x.b.ok, (x.b && x.b.message) || "Couldn't approve it. Please try again.");
        });
      });
      no.addEventListener("click", function () {
        if (acts.querySelector("textarea")) return;
        var ta = h("textarea", { class: "ai-row__note", rows: "2", maxlength: "300", "aria-label": "A note for " + r.user + " (optional)",
                                 placeholder: "A note for " + (r.user || "them") + " (optional)" });
        var send = h("button", { type: "button", class: "hc-btn hc-btn--ink hc-btn--sm" }, "Send rejection");
        var back = h("button", { type: "button", class: "hc-more" }, "Cancel");
        var form = h("div", { class: "ai-row__reject" }, ta, h("div", { class: "ai-row__reject-go" }, send, back));
        acts.appendChild(form); ta.focus();
        back.addEventListener("click", function () { form.remove(); no.focus(); });
        send.addEventListener("click", function () {
          send.disabled = yes.disabled = no.disabled = true;
          api("POST", "/api/analysis/decide", { id: r.id, ok: false, note: ta.value }).then(function (x) {
            if (!(x.b && x.b.ok)) send.disabled = yes.disabled = no.disabled = false;
            done(x.b && x.b.ok, (x.b && x.b.message) || "Couldn't send it. Please try again.");
          });
        });
      });
      add(acts, [yes, no]);
      if (!r.has_analysis) acts.appendChild(h("a", { class: "ai-row__up", href: API + "/analysis?q=" + encodeURIComponent(r.code) }, "Upload the analysis first ", icon("arrow")));
    }
    var status = r.state === "open"
      ? h("span", { class: "hc-sig hc-sig--wait" }, "Due " + shortDay(r.ready_by))
      : r.state === "approved" ? h("span", { class: "hc-sig hc-sig--ok" }, "Approved " + dm(r.handled_at))
        : r.state === "rejected" ? h("span", { class: "hc-sig hc-sig--no" }, "Rejected " + dm(r.handled_at))
          : h("span", { class: "hc-sig hc-sig--off" }, "Closed " + dm(r.handled_at));
    return h("li", { class: "ai-row" + (r.state === "open" ? " is-open" : "") },
      h("span", { class: "ai-row__face", "aria-hidden": "true" }, initials(r.creator)),
      h("div", { class: "ai-row__body" },
        h("a", { class: "ai-row__name", href: ROOT + "creator/#c=" + encodeURIComponent(r.code) }, r.creator),
        h("div", { class: "hc-row__meta" },
          h("span", null, r.code + (r.platform ? " · " + r.platform : "")),
          h("span", null, "Asked by ", h("b", null, r.user || "a client"), " · " + ago(r.at)),
          status),
        r.note && r.state === "rejected" ? h("p", { class: "ai-row__said" }, "Note sent: " + r.note) : null,
        note),
      acts);
  }
  function renderInbox(p) {
    var lead = "Clients asking for a creator's full analysis. Approve opens it to the person who asked, only them. Reject tells them.";
    add(p, head("Analyses", lead));
    if (!AINBOX.data) {
      var wait = h("p", { class: "hc-wait", role: "status" }, AINBOX.err ? "Couldn't load the requests. " : "Loading requests…");
      if (AINBOX.err) wait.appendChild(h("button", { class: "hc-more", type: "button", onclick: function () { AINBOX.err = false; renderSection(); } }, "Try again"));
      add(p, wait);
      if (!AINBOX.err) loadInbox().then(function () { if (SECTION === "analyses") renderSection(); });
      return;
    }
    var all = AINBOX.data;
    var chips = h("div", { class: "hc-chips", role: "group", "aria-label": "Show" });
    INBOX_STATES.forEach(function (c) {
      var n = c[0] === "all" ? all.length : all.filter(function (x) { return x.state === c[0]; }).length;
      chips.appendChild(h("button", { class: "hc-chip", type: "button", "aria-pressed": String(AINBOX.filter === c[0]),
        onclick: function () { AINBOX.filter = c[0]; renderSection(); } }, c[1], " ", h("b", null, String(n))));
    });
    add(p, chips);
    var shown = all.filter(function (x) { return AINBOX.filter === "all" || x.state === AINBOX.filter; });
    if (!shown.length) {
      add(p, h("div", { class: "hc-empty" }, h("b", null, AINBOX.filter === "open" ? "Nothing waiting" : "Nothing here yet"),
        h("p", null, AINBOX.filter === "open" ? "When a client asks for a creator's full analysis from one of their selections, it lands here for you to approve or reject."
          : "Answered requests from the last 30 days show here.")));
      return;
    }
    // client -> campaign (or selection, or neither) -> rows
    var groups = [], byClient = {};
    shown.forEach(function (r) {
      var g = byClient[r.client];
      if (!g) { g = byClient[r.client] = { client: r.client, subs: [], by: {}, open: 0 }; groups.push(g); }
      if (r.state === "open") g.open++;
      var where = r.campaigns.length ? ["campaign", r.campaigns[0].name, r.campaigns[0].status === "live"]
        : r.selections.length ? ["selection", r.selections[0].name, false] : ["none", "Not in a selection now", false];
      var key = where.join("|");
      var sub = g.by[key];
      if (!sub) { sub = g.by[key] = { where: where, rows: [] }; g.subs.push(sub); }
      sub.rows.push(r);
    });
    groups.sort(function (a, b) { return b.open - a.open || a.client.localeCompare(b.client); });
    groups.forEach(function (g) {
      var sec = h("section", { class: "ai-client", "aria-label": g.client },
        h("header", { class: "ai-client__head" },
          h("span", { class: "ai-client__mono", "aria-hidden": "true" }, initials(g.client)),
          h("h2", { class: "ai-client__name" }, g.client),
          g.open ? h("span", { class: "ai-client__n" }, g.open + " waiting") : null));
      g.subs.forEach(function (sub) {
        var w = sub.where;
        sec.appendChild(h("h3", { class: "ai-where" + (w[2] ? " is-live" : "") },
          h("span", { class: "ai-where__k" }, w[0] === "campaign" ? "Campaign" : w[0] === "selection" ? "Selection" : ""), w[1]));
        var ul = h("ul", { class: "ai-rows" });
        sub.rows.forEach(function (r) { ul.appendChild(inboxRow(r)); });
        sec.appendChild(ul);
      });
      add(p, sec);
    });
  }

  function renderAnalyses(p) {
    if (staffInbox()) { renderInbox(p); return; }
    // Clients never get the full profile analysis now (owner, 2026-10-20): this tab lists the creators
    // they asked their account manager about, from the creator page's "Ask your account manager" button.
    add(p, head("Analyses", "Full analyses you requested. HelloVoice reviews each request, usually within one working day."));
    if (!DATA.analyses.length) {
      add(p, h("div", { class: "hc-empty" }, h("b", null, "No requests yet"),
        h("p", null, "Open a creator from one of your selections and press Request the full analysis."),
        h("a", { class: "hc-btn", href: "#selections" }, "Go to my selections")));
      return;
    }
    var list = h("ul", { class: "hc-list" });
    DATA.analyses.forEach(function (a) {
      var open = a.state === "unlocked";
      list.appendChild(h("li", null, h("a", { class: "hc-row", href: ROOT + "creator/#c=" + encodeURIComponent(a.code) },
        h("div", null, h("span", { class: "hc-row__name" }, a.name),
          h("div", { class: "hc-row__meta" }, h("span", null, a.code),
            open ? h("span", { class: "hc-sig hc-sig--ok" }, "Approved " + dm(a.at))
                 : a.state === "declined" ? h("span", { class: "hc-sig hc-sig--no" }, "Not available")
                   : h("span", { class: "hc-sig hc-sig--wait" }, "Asked " + dm(a.at))),
          a.state === "declined" && a.note ? h("p", { class: "ac-muted" }, a.note) : null),
        h("span", { class: "hc-row__go" }, open ? "View full analysis" : "Open creator", " ", icon("arrow")))));
    });
    add(p, list);
  }

  /* ------------------------------------------------------------- campaigns */

  function pace(c) {
    if (!c.planned || !c.starts_at || !c.ends_at) return null;
    var span = c.ends_at - c.starts_at;
    if (span <= 0) return null;
    var ran = Math.max(0, Math.min(1, (Date.now() / 1000 - c.starts_at) / span));
    var done = c.delivered / c.planned;
    if (done >= ran - .1) return { grade: "good", label: "On pace" };
    if (done >= ran - .3) return { grade: "moderate", label: "Slightly behind" };
    return { grade: "low", label: "Behind plan" };
  }
  function scorelineDl(items) {
    var dl = h("dl", { class: "ac-scoreline" });
    items.forEach(function (it) {
      dl.appendChild(h("div", null, h("dt", null, it[0]), h("dd", null, it[1], it[2] ? h("small", null, it[2]) : null),
        it[3] ? h("div", { class: "ac-scoreline__sig" }, it[3]) : null));
    });
    return dl;
  }
  function scorebug(c) {
    var u = DATA.user, p = pace(c), gg = c.goal_grades || {};
    // HelloVoice × the campaign's client logo (owner, 2026-10-20). HelloVoice's own campaigns show our logo once;
    // a campaign with no logo of its own falls back to the account's company logo.
    var brands = h("div", { class: "ac-bug__brands" }), ours = /^\s*hello\s*voice\b/i.test(c.client || "");
    var clientLogos = (c.logos || []).map(function (ref) {
      var n = String(ref).split("/").pop();
      return String(ref).indexOf("clients/") === 0 ? ROOT + "assets/clients/" + n
        : API + "/api/campaign-logo?t=" + encodeURIComponent(c.token) + "&n=" + encodeURIComponent(n);
    });
    if (!clientLogos.length && u.logo && !ours) clientLogos = [imgUrl("logo", u.logo)];
    brands.appendChild(h("img", { class: "ac-bug__hv", src: ROOT + "assets/brand/logo.png", alt: "HelloVoice" }));
    if (!ours && clientLogos.length) {
      brands.appendChild(h("span", { class: "ac-bug__x", "aria-hidden": "true" }, "×"));
      clientLogos.forEach(function (src) { brands.appendChild(h("img", { src: src, alt: c.client || "Client logo" })); });
    }
    return h("section", { class: "ac-bug", "aria-label": c.name },
      h("div", { class: "ac-bug__top" }, brands, h("span", { class: "ac-live" }, "Live"),
        h("span", { class: "ac-muted" }, [day(c.starts_at), day(c.ends_at)].filter(Boolean).join(" – "))),
      h("div", { class: "ac-bug__row" }, h("h2", { class: "ac-bug__title" }, c.name), stamp(c.verdict)),
      scorelineDl([
        ["Views", big(c.views), null, null],
        ["Engagement", (c.engagement || 0).toLocaleString("en-US"), null, null],
        ["Avg eng. rate", c.er != null ? c.er.toFixed(2) : "—", c.er != null ? "%" : null, (gg.er || c.er_grade) ? sig(gg.er || c.er_grade) : null],
        ["Posts live", String(c.delivered), c.planned ? "/" + c.planned : null, gg.posts ? sig(gg.posts) : (p ? sig(p.grade, p.label) : null)]
      ]),
      h("div", { class: "ac-bug__go" }, h("a", { class: "hc-btn", href: ROOT + "campaign/#t=" + encodeURIComponent(c.token) }, "Open the full report")));
  }
  function campaignCard(c) {
    var p = pace(c);
    return h("a", { class: "ac-item ac-item--camp", href: ROOT + "campaign/dashboard/#t=" + encodeURIComponent(c.token) },
      h("div", { class: "ac-item__top" },
        c.status === "live" ? h("span", { class: "ac-live" }, "Live") : h("span", { class: "ac-status" }, c.status === "ended" ? "Ended" : c.status),
        qchip(c.quote),
        h("span", { class: "ac-item__verdict ac-item__verdict--" + (c.verdict.grade || "none") }, c.verdict.label || "Getting started")),
      h("b", { class: "ac-item__name" }, c.name),
      h("span", { class: "ac-muted" }, [day(c.starts_at), day(c.ends_at)].filter(Boolean).join(" – ")),
      h("div", { class: "ac-item__nums" },
        h("span", null, h("b", null, big(c.views)), " views"),
        h("span", null, h("b", null, c.delivered + (c.planned ? "/" + c.planned : "")), " posts"),
        p && c.status === "live" ? sig(p.grade, p.label) : null),
      h("span", { class: "ac-item__go" }, "Open report →"));
  }
  // The campaign board's own data (/api/board): every stage, drafts included, scoped to this person.
  var CBOARD = { data: null, busy: null };
  function loadCampaignBoard() {
    if (CBOARD.busy) return CBOARD.busy;
    CBOARD.busy = api("GET", "/api/board").then(function (r) {
      CBOARD.busy = null;
      if (r.b && r.b.stages) CBOARD.data = r.b;
      return CBOARD.data;
    });
    return CBOARD.busy;
  }
  function renderCampaignBoard(p, view) {
    var B = CBOARD.data;
    if (!B) {
      var wait = h("p", { class: "hc-wait", role: "status" }, "Loading the board…");
      add(p, wait);
      loadCampaignBoard().then(function (b) {
        if (SECTION !== "campaigns" || !document.contains(wait)) return;
        if (b) { renderSection(); return; }
        wait.textContent = "Couldn't load the board. ";
        wait.appendChild(h("button", { class: "hc-more", type: "button", onclick: function () { CBOARD.data = null; renderSection(); } }, "Try again"));
      });
      return;
    }
    if (!B.campaigns.length) return false;
    HVBoard.mount(p, {
      stages: B.stages, noun: "campaign", locked: B.locked_stages || [], view: view, kams: B.kams || [], me: B.me || "",
      onChange: function () { CBOARD.data = null; renderSection(); },
      items: B.campaigns.map(HVBoard.fromCampaign),
      onMove: function (it, to) {
        return api("POST", "/api/board/stage", { t: it.key, to: to }).then(function (r) {
          if (r.b && r.b.ok) CBOARD.data = null;            // the next visit reads the stages fresh
          return r.b || {};
        });
      },
      onPin: function (it, on) {
        return api("POST", "/api/board/pin", { t: it.key, on: on }).then(function (r) {
          if (r.b && r.b.ok) { CBOARD.data = null; renderSection(); }
          return r.b || {};
        });
      }
    });
    return true;
  }

  function renderCampaigns(p) {
    var view = boardOn() ? HVBoard.viewOf("campaigns") : "list";
    add(p, head("Campaigns", view !== "list"
        ? "Every campaign by stage, from the first draft to the final report. Live numbers refresh every 24 hours."
        : "Every campaign HelloVoice runs for your team, with its live report. Numbers refresh every 24 hours.",
      headTools(viewHead("campaigns", renderSection),
        h("a", { class: "hc-btn hc-btn--ink hc-btn--sm", href: ROOT + "campaign/" }, icon("chart"), " Campaign tracking"))));
    if (view !== "list" && renderCampaignBoard(p, view) !== false) return;
    var live = DATA.campaigns.filter(function (c) { return c.status === "live"; });
    var rest = DATA.campaigns.filter(function (c) { return c.status !== "live"; });
    live.forEach(function (c) { add(p, scorebug(c)); });
    if (rest.length) add(p, h("div", null, h("h2", { class: "hc-h2", style: "margin-bottom:14px" }, live.length ? "Earlier campaigns" : "Your campaigns"),
      h("div", { class: "ac-grid" }, rest.map(campaignCard))));
    if (!DATA.campaigns.length) {
      add(p, h("div", { class: "hc-empty" }, h("b", null, "No campaigns yet"),
        h("p", null, "When HelloVoice runs a campaign for you, it goes live here with its report, and your bell tells you."),
        h("button", { class: "hc-btn", type: "button", onclick: talk }, "Ask for a proposal")));
    }
  }
  function talk() { if (HV().talk) HV().talk(); else location.href = ROOT; }

  /* ---------------------------------------------------------------- briefs */

  function renderBriefs(p) {
    add(p, head("Briefs", "The campaign briefs you gave Helvi. Each one scores creators and can be opened as a selection."));
    if (!DATA.briefs.length) {
      add(p, h("div", { class: "hc-empty" }, h("b", null, "No briefs yet"),
        h("p", null, "Answer six quick questions about a campaign and Helvi ranks the roster against them. Your industry and markets fill in for you."),
        h("a", { class: "hc-btn", href: ROOT }, "Start a brief")));
      return;
    }
    var list = h("ul", { class: "hc-list" });
    DATA.briefs.forEach(function (b) {
      var title = b.selection_name || (b.objective ? b.objective + " brief" : "Brief");
      var del = b.can_delete ? delBtn("Delete brief " + title, function () { deleteBrief(b, this); }) : null;
      list.appendChild(h("li", null, actRow(b.selection ? ROOT + "selection/#s=" + encodeURIComponent(b.selection) : null,
        h("div", null, h("span", { class: "hc-row__name" }, title),
          h("div", { class: "hc-row__meta" }, h("span", null, b.summary || ""), h("span", null, day(b.at)))),
        b.selection ? ["Open selection", h("span", { class: "hc-sr" }, " " + title), " ", icon("arrow")] : null, del)));
    });
    add(p, list);
  }

  /* --------------------------------------------------------- notifications */

  var GROUPS = [["selections", "Selections", "Feedback on creators, a selection shared or updated, a creator no longer available"],
                ["analysis", "Analysis", "A full analysis you requested is ready"],
                ["campaigns", "Campaigns", "Goes live, report updated, final report ready"],
                ["account", "Account", "Credits running low, monthly credits added, a colleague joined"],
                ["ideas", "Ideas from HelloVoice", "New creators that match your past briefs, season and congress ideas"]];
  function bucket(ts) {
    var d = new Date(ts * 1000), now = new Date();
    if (d.toDateString() === now.toDateString()) return "Today";
    var y = new Date(now); y.setDate(now.getDate() - 1);
    if (d.toDateString() === y.toDateString()) return "Yesterday";
    if (d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()) return "Earlier this month";
    return "Earlier";
  }
  function renderNotifications(p) {
    var N = DATA.notifications;
    var markAll = N.unread ? h("button", { class: "hc-more", type: "button", onclick: function () {
      api("POST", "/api/notifications/read", {}).then(function (r) {
        if (!r.b.ok) return;
        N.unread = 0; N.items.forEach(function (n) { n.unread = false; });
        if (HV().setUnread) HV().setUnread(0);
        renderSide(); renderSection();
      });
    } }, "Mark all as read") : null;
    add(p, head("Notifications", null, markAll));
    var chips = h("div", { class: "hc-chips", role: "group", "aria-label": "Show" });
    var total = N.items.length;
    [["all", "All", total]].concat(GROUPS.map(function (g) { return [g[0], g[1].replace(" from HelloVoice", ""), N.counts[g[0]] || 0]; }))
      .forEach(function (c) {
        if (c[0] === "ideas" && !c[2]) return;
        chips.appendChild(h("button", { class: "hc-chip", type: "button", "aria-pressed": String(FILTER === c[0]),
          onclick: function () { FILTER = c[0]; renderSection(); } }, c[1], " ", h("b", null, String(c[2]))));
      });
    var feed = h("div", { class: "hc-feed" });
    var shown = N.items.filter(function (n) { return FILTER === "all" || n.group === FILTER; });
    var last = null, ul = null;
    shown.forEach(function (n) {
      var b = bucket(n.at);
      if (b !== last) { feed.appendChild(h("h3", null, b)); ul = h("ul"); feed.appendChild(ul); last = b; }
      var li = h("li"); li.appendChild(HV().noteRow(n, noteOpened)); ul.appendChild(li);
    });
    if (!shown.length) feed.appendChild(h("p", { class: "ac-muted", style: "margin-top:18px" }, total ? "Nothing in this group yet." : "Nothing yet. Updates from HelloVoice land here and in the bell."));
    var prefs = h("ul", { class: "hc-prefs" });
    var msg = h("span", { class: "ac-note", role: "status", "aria-live": "polite" });
    GROUPS.forEach(function (g) {
      var on = !!N.prefs[g[0]];
      var sw = h("button", { class: "hc-sw", type: "button", role: "switch", "aria-checked": String(on), "aria-label": "Show " + g[1] + " in my bell" });
      sw.addEventListener("click", function () {
        var want = sw.getAttribute("aria-checked") !== "true", body = {};
        body[g[0]] = want;
        sw.setAttribute("aria-checked", String(want));
        api("POST", "/api/me/notify", body).then(function (r) {
          if (!r.b.ok) { sw.setAttribute("aria-checked", String(!want)); note(msg, "Couldn't save that. Please try again.", true); return; }
          N.prefs = r.b.prefs; N.unread = r.b.unread;
          if (HV().setUnread) HV().setUnread(r.b.unread);
          note(msg, g[1] + (want ? " now shows" : " no longer shows") + " in your bell.");
          var badge = document.querySelector('[data-count="notifications"]'); if (badge) badge.textContent = String(r.b.unread || "");
        });
      });
      prefs.appendChild(h("li", null, h("span", null, h("b", null, g[1]), h("small", null, g[2])), sw));
    });
    add(p, h("div", { class: "hc-split" }, h("div", null, chips, feed),
      h("aside", { class: "hc-panel", "aria-labelledby": "hc-bellprefs" },
        h("h2", { class: "hc-h2", id: "hc-bellprefs" }, "Show in my bell"),
        h("p", { class: "ac-muted" }, "Updates appear in the bell and here. We don't send them by email; your sign-in code is the only email we send."),
        prefs, msg)));
  }

  /* --------------------------------------------------------------- credits */

  function renderCredits(p) {
    add(p, head("Credits"));
    var monthly = DATA.monthly_credits || 0, bal = DATA.credits || 0;
    var cells = Math.min(60, Math.max(monthly || 30, bal));
    var meter = h("div", { class: "hc-meter", "aria-hidden": "true" });
    for (var i = 0; i < cells; i++) meter.appendChild(h("i", { class: i < Math.min(bal, monthly || cells) ? "on" : (i < bal ? "extra" : null) }));
    var kam = DATA.kam ? first(DATA.kam.split("<")[0]) : null;
    var msg = h("span", { class: "ac-note", role: "status", "aria-live": "polite" });
    var ask = h("div", { class: "hc-ask", hidden: true });
    var amt = h("select", { "aria-label": "How many credits" });
    [50, 200, 500].forEach(function (n) { amt.appendChild(h("option", { value: String(n) }, "+" + n + " credits")); });
    var why = h("input", { type: "text", maxlength: "200", placeholder: "What for? (optional)", "aria-label": "What the credits are for" });
    var send = h("button", { class: "hc-btn hc-btn--sm", type: "button" }, "Send request");
    send.addEventListener("click", function () {
      send.disabled = true;
      api("POST", "/api/credits/request", { amount: +amt.value, note: why.value }).then(function (r) {
        send.disabled = false;
        if (r.s === 429) { note(msg, "You've asked a few times today. Your account manager has your requests.", true); return; }
        note(msg, r.b.message || (r.b.ok ? "Request sent." : "Couldn't send. Please try again."), !r.b.ok);
        if (r.b.ok) ask.hidden = true;
      });
    });
    ask.appendChild(amt); ask.appendChild(why); ask.appendChild(send);
    var reqBtn = h("button", { class: "hc-btn", type: "button", onclick: function () { ask.hidden = !ask.hidden; if (!ask.hidden) amt.focus(); } }, "Request more credits");
    add(p, h("section", { class: "hc-bal", "aria-label": "Your balance" },
      h("div", null, h("div", { class: "hc-bal__fig" }, h("span", { class: "hv-credit-num" }, String(bal)), h("small", null, "Credits left")), meter,
        h("p", { class: "hc-bal__meta" }, monthly ? ["Tops up to ", h("b", null, monthly + " on " + dm(DATA.next_refill)), ". Credits you earn from your profile and invites come on top."]
                                                   : "Credits you earn from your profile and invites are added straight away.")),
      h("div", { class: "hc-bal__ask" }, reqBtn, ask, h("p", null, (kam ? kam + ", your account manager," : "Your HelloVoice team") + " tops you up. Usually the same working day."), msg)));
    var c = costs();
    var rows = [["AI shortlist", "Answer six questions about your campaign; Helvi ranks the roster against them.", c.brief],
                ["Find a replacement", "After you reject a creator: 3 similar creators that fit the same campaign.", c.replace],
                ["A typed question to Helvi", "Tapping Helvi's options is always free.", c.chat],
                ["Full creator analysis", "For any creator in one of your selections. Ready within 1 working day.", 0]];
    var tb = h("tbody");
    rows.forEach(function (r) {
      tb.appendChild(h("tr", null, h("td", null, h("b", null, r[0]), h("small", null, r[1])),
        h("td", null, r[2] ? h("span", { class: "hc-price__c" }, icon("coin"), String(r[2]), h("small", null, r[2] === 1 ? "credit" : "credits")) : h("span", { class: "hc-price__free" }, "Free"))));
    });
    add(p, h("section", { "aria-labelledby": "hc-buy" }, h("h2", { class: "hc-h2", id: "hc-buy", style: "margin-bottom:14px" }, "What credits buy"),
      h("table", { class: "hc-price" }, h("thead", null, h("tr", null, h("th", null, "With Helvi"), h("th", null, "Cost"))), tb)));
    var comp = DATA.completion, inv = DATA.invite;
    var left = comp.steps.filter(function (s) { return !s.done; }).length;
    add(p, h("section", { "aria-labelledby": "hc-earn" }, h("h2", { class: "hc-h2", id: "hc-earn", style: "margin-bottom:14px" }, "Earn more"),
      h("div", { class: "hc-earn" },
        h("a", { href: "#account", "data-focus": "job_title" }, h("span", { class: "hc-earn__ic" }, icon("user")),
          h("span", null, h("b", null, comp.waiting ? "Finish your profile" : "Profile complete"),
            h("small", null, comp.waiting ? (left ? plural(left, "detail") + " left" + (comp.bonus_paid ? "" : ", then a 100% bonus") : "Save your profile to collect them") : "All profile credits earned")),
          comp.waiting ? h("span", { class: "hc-reward" }, "+" + comp.waiting) : null),
        h("a", { href: "#account", "data-focus": "invite" }, h("span", { class: "hc-earn__ic" }, icon("link")),
          h("span", null, h("b", null, "Invite a colleague"), h("small", null, "Paid when they sign in · " + inv.left + " of " + inv.max + " invites left")),
          inv.left ? h("span", { class: "hc-reward" }, "+" + inv.credits) : null))));
    var since = DATA.ledger.length ? new Date(DATA.ledger[DATA.ledger.length - 1].at * 1000).toLocaleDateString("en-GB", { month: "long" }) : "";
    var lt = h("tbody");
    DATA.ledger.forEach(function (l) {
      lt.appendChild(h("tr", null, h("td", null, l.reason, h("small", null, day(l.at))),
        h("td", null, h("span", { class: l.delta > 0 ? "hc-delta up" : "hc-delta" }, (l.delta > 0 ? "+" : "") + l.delta)), h("td", null, String(l.balance))));
    });
    add(p, h("details", { class: "hc-hist" },
      h("summary", null, "History", h("small", null, DATA.ledger.length ? " · " + plural(DATA.ledger.length, "entry", "entries") + (since ? " since " + since : "") : " · nothing yet"), icon("down")),
      DATA.ledger.length ? h("table", { class: "hc-ledger" }, lt) : null));
  }

  /* --------------------------------------------------------------- account */

  function stepOf(key) { return DATA.completion.steps.filter(function (s) { return s.key === key; })[0]; }
  function hint(key) {
    var s = stepOf(key);
    if (!s) return null;
    return h("span", { class: "hc-earnhint" + (s.paid ? " is-paid" : "") }, s.paid ? "Earned +" + s.credits : "+" + s.credits + " credits");
  }
  function readImage(file, kind) {
    // The photo is cropped to a centred square; the logo keeps its shape.
    return new Promise(function (resolve, reject) {
      if (!/^image\/(jpeg|png|webp)$/.test(file.type)) { reject("Please choose a JPG, PNG or WebP image."); return; }
      var img = new Image();
      img.onload = function () {
        var max = kind === "photo" ? 512 : 600;
        var sw = img.naturalWidth, sh = img.naturalHeight, sx = 0, sy = 0, w, hgt;
        if (kind === "photo") { var side = Math.min(sw, sh); sx = (sw - side) / 2; sy = (sh - side) / 2; sw = sh = side; w = hgt = Math.min(max, side); }
        else { var k = Math.min(1, max / Math.max(sw, sh)); w = Math.round(sw * k); hgt = Math.round(sh * k); }
        var cv = document.createElement("canvas"); cv.width = w; cv.height = hgt;
        cv.getContext("2d").drawImage(img, sx, sy, sw, sh, 0, 0, w, hgt);
        URL.revokeObjectURL(img.src);
        resolve(kind === "photo" ? cv.toDataURL("image/jpeg", .9) : cv.toDataURL("image/png"));
      };
      img.onerror = function () { reject("That file couldn't be read as an image."); };
      img.src = URL.createObjectURL(file);
    });
  }
  function flashFor(key) {
    var f = FLASH && FLASH.key === key ? FLASH : null;
    if (f) FLASH = null;
    var el = h("span", { class: "ac-note", role: "status", "aria-live": "polite" });
    if (f) note(el, f.text, f.bad);
    return el;
  }
  function afterSave(b) {
    if (b.completion) DATA.completion = b.completion;
    celebrate(b.earned, b.credits);
  }
  function imageField(kind, label, help) {
    var u = DATA.user, has = !!u[kind];
    var prev = h("div", { class: "ac-img ac-img--" + kind });
    if (has) prev.appendChild(h("img", { src: imgUrl(kind, u[kind]), alt: "" }));
    else prev.appendChild(h("span", null, kind === "photo" ? initials(u.name) : "Logo"));
    var msg = flashFor(kind);
    var input = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", class: "ac-file", "aria-label": (has ? "Change " : "Upload ") + label.toLowerCase() });
    var pick = h("label", { class: "ac-upload" }, input, h("span", null, has ? "Change" : "Upload " + (kind === "photo" ? "a photo" : "a logo")));
    var remove = null;
    if (has) {
      var armed = false;
      remove = h("button", { class: "ac-link", type: "button", onclick: function () {
        if (!armed) { armed = true; remove.textContent = "Confirm remove"; remove.classList.add("is-armed"); return; }
        api("POST", "/api/me/image", { kind: kind, remove: true }).then(function (r) {
          if (!r.b.ok) { note(msg, "Couldn't remove it. Please try again.", true); return; }
          DATA.user[kind] = null;
          FLASH = { key: kind, text: (kind === "photo" ? "Photo" : "Logo") + " removed." };
          if (kind === "photo" && HV().setPhoto) HV().setPhoto(null);
          renderSide(); renderSection();
        });
      } }, "Remove");
    }
    input.addEventListener("change", function () {
      var f = input.files && input.files[0];
      if (!f) return;
      note(msg, "Uploading…");
      readImage(f, kind).then(function (dataUrl) {
        return api("POST", "/api/me/image", { kind: kind, data: dataUrl });
      }).then(function (r) {
        if (!r.b.ok) { note(msg, r.b.message || "Couldn't save that image. Please try again.", true); return; }
        DATA.user[kind] = r.b.version;
        if (kind === "photo" && HV().setPhoto) HV().setPhoto(r.b.version);
        FLASH = { key: kind, text: (kind === "photo" ? "Photo" : "Logo") + " saved." };
        afterSave(r.b);
        renderSide(); renderSection();
      }, function (err) { note(msg, typeof err === "string" ? err : "Couldn't read that image.", true); });
    });
    return h("div", { class: "ac-imgfield", "data-key": kind }, prev,
      h("div", null, h("b", null, label), hint(kind), h("p", { class: "ac-muted" }, help), h("div", { class: "ac-row" }, pick, remove, msg)));
  }
  function field(key, label, type, auto, extra) {
    var id = "hc-f-" + key;
    var inp = h("input", { class: "ac-input", id: id, name: key, type: type || "text", value: DATA.user[key] || "", autocomplete: auto || "off", "data-key": key });
    return [h("div", { class: "ac-field" + (extra ? " " + extra : "") }, h("label", { for: id }, label, hint(key)), inp), inp];
  }
  function profileForm() {
    var u = DATA.user, f = {};
    var form = h("form", { class: "ac-form", novalidate: true });
    [["name", "Name", "text", "name"], ["job_title", "Job title", "text", "organization-title"], ["company", "Company", "text", "organization"], ["phone", "Phone", "tel", "tel"]]
      .forEach(function (x) { var r = field(x[0], x[1], x[2], x[3]); f[x[0]] = r[1]; form.appendChild(r[0]); });
    form.appendChild(h("div", { class: "ac-field" }, h("span", { class: "ac-field__label" }, "Email"), h("p", { class: "ac-static" }, u.email)));
    var msg = flashFor("profile");
    form.appendChild(h("div", { class: "ac-row" }, h("button", { class: "hc-btn hc-btn--sm", type: "submit" }, "Save changes"), msg));
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (f.name.value.trim().length < 2) { note(msg, "Please keep your name on your profile.", true); f.name.focus(); return; }
      note(msg, "Saving…");
      api("POST", "/api/me/update", { name: f.name.value, company: f.company.value, job_title: f.job_title.value, phone: f.phone.value }).then(function (r) {
        if (!r.b.ok) { note(msg, r.b.message || "Couldn't save. Please try again.", true); return; }
        DATA.user = Object.assign(DATA.user, r.b.user);
        afterSave(r.b);
        FLASH = { key: "profile", text: "Saved." };
        renderSide(); renderSection();
      });
    });
    return form;
  }
  function brandForm() {
    var u = DATA.user;
    var form = h("form", { class: "ac-form", novalidate: true });
    var br = field("brands", "Your brands and products", "text", "off", "ac-field--wide");
    br[1].placeholder = "e.g. Cetaphil, Daylong, Spectraban";
    br[1].maxLength = 300;
    form.appendChild(br[0]);
    var ind = h("select", { class: "ac-input", id: "hc-f-industry", "data-key": "industry" });
    ind.appendChild(h("option", { value: "" }, "Choose your industry"));
    DATA.industries.forEach(function (o) { var op = h("option", { value: o.value }, o.label); if (o.value === u.industry) op.selected = true; ind.appendChild(op); });
    form.appendChild(h("div", { class: "ac-field" }, h("label", { for: "hc-f-industry" }, "Industry", hint("industry_markets")), ind));
    var lang = h("select", { class: "ac-input", id: "hc-f-language" });
    lang.appendChild(h("option", { value: "" }, "Choose a language"));
    DATA.languages.forEach(function (l) { var op = h("option", { value: l }, l); if (l === u.language) op.selected = true; lang.appendChild(op); });
    form.appendChild(h("div", { class: "ac-field" }, h("label", { for: "hc-f-language" }, "Campaign language"), lang));
    var picked = (u.markets || []).slice();
    var mk = h("div", { class: "hc-mk", role: "group", "aria-labelledby": "hc-f-markets" });
    DATA.markets.forEach(function (m) {
      var b = h("button", { type: "button", "aria-pressed": String(picked.indexOf(m.value) > -1) }, m.label);
      b.addEventListener("click", function () {
        var i = picked.indexOf(m.value);
        if (i > -1) picked.splice(i, 1); else picked.push(m.value);
        b.setAttribute("aria-pressed", String(i === -1));
      });
      mk.appendChild(b);
    });
    form.appendChild(h("div", { class: "ac-field ac-field--wide" }, h("span", { class: "ac-field__label", id: "hc-f-markets" }, "Markets (your first one leads your briefs)"), mk));
    var msg = flashFor("brand");
    form.appendChild(h("div", { class: "ac-row" }, h("button", { class: "hc-btn hc-btn--sm", type: "submit" }, "Save"), msg));
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      note(msg, "Saving…");
      api("POST", "/api/me/update", { brands: br[1].value, industry: ind.value, markets: picked, language: lang.value }).then(function (r) {
        if (!r.b.ok) { note(msg, r.b.message || "Couldn't save. Please try again.", true); return; }
        DATA.user = Object.assign(DATA.user, r.b.user);
        afterSave(r.b);
        FLASH = { key: "brand", text: "Saved. Your next brief starts from these." };
        renderSide(); renderSection();
      });
    });
    return form;
  }
  function teamSection() {
    var list = h("ul", { class: "ac-people" });
    DATA.team.forEach(function (t) {
      list.appendChild(h("li", null, h("span", { class: "ac-people__ini", "aria-hidden": "true" }, initials(t.name)),
        h("div", null, h("b", null, t.name), t.job_title ? h("span", { class: "ac-muted" }, t.job_title) : null)));
    });
    var inv = DATA.invite;
    var linkIn = h("input", { value: inviteLink(), readonly: true, "aria-label": "Your invite link", "data-key": "invite" });
    var copyBtn = h("button", { class: "hc-btn hc-btn--ink hc-btn--sm", type: "button" }, icon("link"), " Copy invite link");
    copyBtn.addEventListener("click", function () { copy(linkIn.value, copyBtn, "Link copied"); });
    var name = h("input", { class: "ac-input", id: "hc-inv-name", autocomplete: "off" });
    var email = h("input", { class: "ac-input", id: "hc-inv-email", type: "email", autocomplete: "off" });
    var msg = h("span", { class: "ac-note", role: "status", "aria-live": "polite" });
    var form = h("form", { class: "ac-form ac-form--inline", novalidate: true },
      h("div", { class: "ac-field" }, h("label", { for: "hc-inv-name" }, "Colleague's name"), name),
      h("div", { class: "ac-field" }, h("label", { for: "hc-inv-email" }, "Work email"), email),
      h("div", { class: "ac-row" }, h("button", { class: "hc-btn hc-btn--line hc-btn--sm", type: "submit" }, "Ask for their access"), msg));
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (email.value.indexOf("@") < 1) { note(msg, "Please add your colleague's work email.", true); email.focus(); return; }
      note(msg, "Sending…");
      api("POST", "/api/team/invite", { name: name.value, email: email.value }).then(function (r) {
        if (r.s === 429) { note(msg, "You've sent enough requests today. Your account manager has them.", true); return; }
        note(msg, r.b.message || (r.b.ok ? "Sent." : "Couldn't send. Please try again."), !r.b.ok);
        if (r.b.ok) { name.value = ""; email.value = ""; }
      });
    });
    return h("section", { class: "hc-sec", "aria-labelledby": "hc-team" },
      h("h2", { class: "hc-h2", id: "hc-team" }, "Team"),
      h("p", null, "Colleagues from your company with their own account. You see each other's selections and campaigns."),
      DATA.team.length ? list : h("p", { class: "ac-muted" }, "No colleagues yet."),
      h("h3", { class: "ac-h3" }, "Invite a colleague", h("span", { class: "hc-earnhint" + (inv.left ? "" : " is-paid") }, inv.left ? "+" + inv.credits + " credits each" : "All 5 paid invites used")),
      h("p", { class: "ac-muted" }, "Send your link. When HelloVoice approves their account and they sign in for the first time, you get " + inv.credits +
        " credits (same company email domain, up to " + inv.max + " paid invites; " + inv.left + " left)."),
      h("div", { class: "hc-linkbox" }, linkIn, copyBtn),
      h("p", { class: "ac-muted", style: "margin-top:18px" }, "Or ask HelloVoice to set up their access:"), form);
  }
  function privacySection() {
    var msg = h("span", { class: "ac-note", role: "status", "aria-live": "polite" });
    var confirmBox = h("div", { class: "ac-confirm", hidden: true });
    var typed = h("input", { class: "ac-input", id: "ac-del", autocomplete: "off", placeholder: "DELETE" });
    var go = h("button", { class: "cat-btn ac-btn-danger", type: "button", disabled: true }, "Delete my account for good");
    typed.addEventListener("input", function () { go.disabled = typed.value.trim() !== "DELETE"; });
    go.addEventListener("click", function () {
      go.disabled = true;
      api("POST", "/api/me/delete", { confirm: "DELETE" }).then(function (r) {
        if (r.b && r.b.ok !== false && r.s < 400) { location.href = ROOT; return; }
        go.disabled = false; note(msg, (r.b && r.b.message) || "Couldn't delete the account. Please contact your account manager.", true);
      });
    });
    confirmBox.appendChild(h("label", { for: "ac-del" }, "Type DELETE to confirm. Your account and personal data are erased; this can't be undone."));
    confirmBox.appendChild(h("div", { class: "ac-row" }, typed, go,
      h("button", { class: "ac-link", type: "button", onclick: function () { confirmBox.hidden = true; typed.value = ""; go.disabled = true; } }, "Cancel")));
    return h("section", { class: "hc-sec", "aria-labelledby": "hc-priv" },
      h("h2", { class: "hc-h2", id: "hc-priv" }, "Privacy and data"),
      h("div", { class: "ac-action" }, h("div", null, h("b", null, "Download my data"), h("p", { class: "ac-muted" }, "Your profile, briefs and credit history as a file.")),
        h("button", { class: "ac-btn-line", type: "button", onclick: function () {
          note(msg, "Preparing your file…");
          fetch(API + "/api/me/export", { credentials: "include", cache: "no-store" }).then(function (r) {
            if (!r.ok) throw new Error("export");
            return r.blob();
          }).then(function (b) {
            var a = h("a", { href: URL.createObjectURL(b), download: "my-hellovoice-data.json" }); document.body.appendChild(a); a.click(); a.remove();
            note(msg, "Downloaded my-hellovoice-data.json.");
          }).catch(function () { note(msg, "Couldn't prepare the file. Please try again.", true); });
        } }, "Download")),
      h("div", { class: "ac-action" }, h("div", null, h("b", null, "Sign out of other devices"), h("p", { class: "ac-muted" }, "Every other browser loses access. You stay signed in here.")),
        h("button", { class: "ac-btn-line", type: "button", onclick: function () {
          api("POST", "/api/me/signout-others", {}).then(function (r) { note(msg, r.b.ok ? (r.b.removed ? "Signed out of " + plural(r.b.removed, "other device") + "." : "No other devices were signed in.") : "Couldn't do that. Please try again.", !r.b.ok); });
        } }, "Sign out others")),
      msg,
      h("div", { class: "ac-action ac-action--danger" }, h("div", null, h("b", null, "Delete my account"), h("p", { class: "ac-muted" }, "Your account and personal data are erased. Selections and campaigns stay with your company.")),
        h("button", { class: "cat-btn ac-btn-danger", type: "button", onclick: function () { confirmBox.hidden = false; typed.focus(); } }, "Delete account")),
      confirmBox,
      h("div", { class: "ac-action" }, h("div", null, h("b", null, "Sign out"), h("p", { class: "ac-muted" }, "Sign out of HELVi Connect on this browser.")),
        h("button", { class: "ac-btn-line", type: "button", onclick: signOut }, "Sign out")));
  }
  function renderAccount(p) {
    add(p, head("Account", "Who you are and who you work with. A complete profile earns " + (DATA.completion.steps.reduce(function (s, x) { return s + x.credits; }, 0) + DATA.completion.bonus) + " credits, once."));
    add(p, h("section", { class: "hc-sec", "aria-labelledby": "hc-prof" }, h("h2", { class: "hc-h2", id: "hc-prof" }, "Profile"),
      imageField("photo", "Profile photo", "Shown in the menu and on your profile. A square crop is made for you."),
      imageField("logo", "Company logo", "Shown on your live campaign's scoreboard."),
      profileForm()));
    add(p, h("section", { class: "hc-sec", "aria-labelledby": "hc-brand" }, h("h2", { class: "hc-h2", id: "hc-brand" }, "Your brands and markets"),
      h("p", null, "Helvi uses these to pre-fill your briefs, so a new shortlist starts from your industry and market."), brandForm()));
    add(p, teamSection());
    add(p, privacySection());
  }

  /* ------------------------------------------------------------ My clients */
  // Key account managers only (KAM scoped access, 2026-10-11). One card per client account: its
  // selections with the quote stage, campaigns with live results, analysis requests, and activity.
  // Each item opens the way the client sees it; "Open in admin" goes to the account in the admin.
  // Nothing priced is sent here: costs, margins and prices stay in the admin.

  var CLIENTS = null, CLIENTS_ERR = null, KFILTER = "all";

  function needsYou(c) {
    return c.selections.some(function (s) { return s.quote && s.quote.key === "requested"; }) ||
      c.analyses.waiting > 0 || c.handoffs > 0 && c.last_login_at && (Date.now() / 1000 - c.last_login_at) < 86400 * 14;
  }
  function loadClients() {
    return api("GET", "/api/account/clients").then(function (r) {
      if (r.b && r.b.ok) { CLIENTS = r.b; CLIENTS_ERR = null; }
      else CLIENTS_ERR = r.s === 403 ? "My clients is for key account managers." : "Your clients couldn't be loaded. Please try again shortly.";
      if (SECTION === "clients") { renderSide(); renderSection(); }
    });
  }
  function kStat(term, fig, sub) {
    return h("div", null, h("dt", null, term), h("dd", { class: "hc-score__fig" }, fig), h("dd", { class: "hc-score__sub" }, sub));
  }
  function kRow(href, name, side, meta) {
    return h("li", null, h("a", { class: "kc-row", href: href },
      h("span", { class: "kc-row__top" }, h("span", { class: "kc-row__name" }, name), side || null),
      meta ? h("span", { class: "kc-row__meta" }, meta) : null));
  }
  function kCol(id, title, n, body, empty) {
    return h("section", { class: "kc__col", "aria-labelledby": id },
      h("h3", { class: "kc__h", id: id }, title, n ? h("span", { class: "kc__n" }, String(n)) : null),
      body && body.children.length ? body : h("p", { class: "kc__none" }, empty));
  }
  function campStatus(k) {
    if (k.status === "live") return h("span", { class: "ac-live kc-live" }, "Live");
    return h("span", { class: "ac-status" }, k.status === "ended" ? "Ended" : k.status === "draft" ? "Draft" : k.status);
  }
  function clientCard(c, i) {
    var id = "kc" + i;
    var title = c.company || c.name || c.email;
    var who = [c.company ? c.name : null, c.email].filter(Boolean).join(" · ");
    var attn = needsYou(c);

    var sels = h("ul", { class: "kc__rows" });
    c.selections.forEach(function (s) {
      var n = s.counts, meta = [];
      if (n.approved) meta.push(h("span", { class: "hc-sig hc-sig--ok" }, n.approved + " approved"));
      if (n.rejected) meta.push(h("span", { class: "hc-sig hc-sig--no" }, n.rejected + " rejected"));
      if (n.review) meta.push(h("span", null, n.review + " to review"));
      if (!n.creators) meta.push(h("span", null, "No creators yet"));
      sels.appendChild(kRow(ROOT + "selection/#s=" + encodeURIComponent(s.token), s.name, qchip(s.quote), meta));
    });
    var camps = h("ul", { class: "kc__rows" });
    c.campaigns.forEach(function (k) {
      var meta = [h("span", null, h("b", null, k.posts + (k.planned ? "/" + k.planned : "")), (k.planned || k.posts) === 1 ? " post captured" : " posts captured"),
                  h("span", null, h("b", null, big(k.views)), " views")];
      camps.appendChild(kRow(ROOT + "campaign/dashboard/#t=" + encodeURIComponent(k.token), k.name, campStatus(k), meta));
    });
    var a = c.analyses;
    var trio = h("dl", { class: "kc__trio" },
      h("div", null, h("dt", null, "Requested"), h("dd", null, String(a.requested))),
      h("div", null, h("dt", null, "Delivered"), h("dd", null, String(a.delivered))),
      h("div", { class: a.late ? "is-late" : null }, h("dt", null, "Waiting"), h("dd", null, String(a.waiting))));
    var open = h("ul", { class: "kc__rows" });
    a.items.filter(function (x) { return x.state !== "delivered"; }).forEach(function (x) {
      open.appendChild(kRow(ROOT + "creator/#c=" + encodeURIComponent(x.code), x.name,
        x.state === "late" ? h("span", { class: "hc-sig hc-sig--no" }, "Late") : h("span", { class: "hc-sig hc-sig--wait" }, "Due " + shortDay(x.due)),
        [h("span", null, x.code + (x.platform ? " · " + x.platform : "")), h("span", null, "asked " + ago(x.at))]));
    });
    var anCol = h("section", { class: "kc__col", "aria-labelledby": id + "-a" },
      h("h3", { class: "kc__h", id: id + "-a" }, "Analysis requests"),
      a.requested ? trio : null,
      open.children.length ? open : h("p", { class: "kc__none" }, a.requested ? "Nothing waiting. Every request is delivered." : "No analysis requested yet."));

    var act = h("dl", { class: "kc__act" },
      h("div", null, h("dt", null, "Last sign-in"), h("dd", null, c.last_login_at ? ago(c.last_login_at) : "Never")),
      h("div", null, h("dt", null, "Credits left"), h("dd", null, h("span", { class: "hv-credit-num" }, String(c.credits)))),
      h("div", null, h("dt", null, "Helvi chats"), h("dd", null, String(c.chats))),
      h("div", { class: c.handoffs ? "is-attn" : null }, h("dt", null, "Hand-offs"), h("dd", null, String(c.handoffs))));

    return h("li", null, h("article", { class: "kc", "aria-labelledby": id },
      h("header", { class: "kc__hd" },
        h("div", { class: "kc__id" },
          h("h2", { class: "kc__name", id: id }, title, attn ? h("span", { class: "kc__attn" }, "Needs you") : null,
            c.status !== "active" ? h("span", { class: "ac-status" }, c.status) : null),
          h("p", { class: "kc__who" }, who)),
        h("a", { class: "hc-more", href: c.admin, target: "_blank", rel: "noopener" }, "Open in admin", h("span", { class: "hc-sr" }, " for " + title), " ", icon("arrow"))),
      act,
      h("div", { class: "kc__cols" },
        kCol(id + "-s", "Selections", c.selections.length, sels, "No selections yet."),
        kCol(id + "-c", "Campaigns", c.campaigns.length, camps, "No campaigns yet."),
        anCol)));
  }
  function renderClients(p) {
    var doms = CLIENTS && CLIENTS.domains.length ? CLIENTS.domains.join(", ") : null;
    add(p, head("My clients", (doms ? "Your accounts on " + doms + ". " : "Your accounts. ") +
      "Open any selection or report exactly as your client sees it. Pricing and margins stay in the admin.",
      CLIENTS ? h("a", { class: "hc-btn hc-btn--line hc-btn--sm", href: CLIENTS.admin, target: "_blank", rel: "noopener" }, "Open admin ", icon("arrow")) : null));
    if (CLIENTS_ERR) { add(p, h("div", { class: "hc-empty" }, h("b", null, "My clients"), h("p", null, CLIENTS_ERR))); return; }
    if (!CLIENTS) {
      add(p, h("div", { class: "kc-skel", "aria-hidden": "true" }, h("i"), h("i"), h("i")));
      add(p, h("p", { class: "hc-sr", role: "status" }, "Loading your clients"));
      loadClients();
      return;
    }
    var all = CLIENTS.clients;
    if (!all.length) {
      add(p, h("div", { class: "hc-empty" }, h("b", null, "No clients yet"),
        h("p", null, "A client is yours when an owner maps their company domain to you in the admin's Settings. Every new sign-up on that domain then appears here.")));
      return;
    }
    var quotes = 0, waiting = 0, late = 0, live = 0, recent = 0;
    all.forEach(function (c) {
      quotes += c.selections.filter(function (s) { return s.quote && s.quote.key === "requested"; }).length;
      waiting += c.analyses.waiting; late += c.analyses.late;
      live += c.campaigns.filter(function (k) { return k.status === "live"; }).length;
      if (c.last_login_at && Date.now() / 1000 - c.last_login_at < 7 * 86400) recent++;
    });
    add(p, h("dl", { class: "hc-score hc-score--4" },
      kStat("Clients", String(all.length), recent ? [h("b", null, String(recent)), " signed in this week"] : "None signed in this week"),
      kStat("Quotes to prepare", String(quotes), quotes ? "Requested, waiting on you" : "Nothing requested"),
      kStat("Analyses waiting", String(waiting), late ? [h("b", { class: "kc-late" }, late + " late"), " past 1 working day"] : (waiting ? "All on time" : "Nothing to deliver")),
      kStat("Live campaigns", String(live), live ? "Results refresh every 24 hours" : "None live")));
    var need = all.filter(needsYou);
    var bar = h("div", { class: "kc-filter", role: "group", "aria-label": "Show" });
    [["all", "All clients", all.length], ["need", "Needs you", need.length]].forEach(function (f) {
      bar.appendChild(h("button", { class: "kc-chip", type: "button", "aria-pressed": KFILTER === f[0] ? "true" : "false",
        onclick: function () { KFILTER = f[0]; renderSection(); } }, f[1], h("span", null, String(f[2]))));
    });
    add(p, bar);
    var shown = KFILTER === "need" ? need : all;
    // Clients that need something first, then by last sign-in.
    shown = shown.slice().sort(function (x, y) {
      return (needsYou(y) - needsYou(x)) || ((y.last_login_at || 0) - (x.last_login_at || 0));
    });
    var list = h("ul", { class: "kc-list" });
    shown.forEach(function (c, i) { list.appendChild(clientCard(c, i)); });
    add(p, shown.length ? list : h("div", { class: "hc-empty" }, h("b", null, "Nothing needs you"),
      h("p", null, "No quote is waiting, every analysis is delivered and no client handed a chat over. "),
      h("button", { class: "hc-btn hc-btn--line hc-btn--sm", type: "button", onclick: function () { KFILTER = "all"; renderSection(); } }, "Show all clients")));
  }

  /* --------------------------------------------------------- Companies hub */
  // Staff only (item 129, 2026-10-18). Every company for an admin, a key account manager's own for her:
  // company > people > their selections and campaigns. Each item opens as the client sees it and has a
  // Share panel: email a client, hand it to an account manager (admins), copy its link. Nothing priced
  // is shown. Companies load as a list; a company's people and items load when it is opened.

  var HUB = { ctl: null, list: null, kams: [], role: "", err: null, q: "", f: "all", view: "companies", open: {}, openP: {}, detail: {}, share: null, shareMode: "all" };

  function hubLoad() {
    return api("GET", "/api/hub/companies").then(function (r) {
      if (r.b && r.b.ok) { HUB.list = r.b.companies; HUB.kams = r.b.kams || []; HUB.role = r.b.role; HUB.err = null; }
      else HUB.err = r.s === 403 ? "The Companies hub is for HelloVoice staff." : "The companies couldn't be loaded. Please try again shortly.";
      if (SECTION === "companies") { renderSide(); renderSection(); }
    });
  }
  function hubDetail(key) {
    HUB.detail[key] = "loading";
    return api("GET", "/api/hub/company?k=" + encodeURIComponent(key)).then(function (r) {
      HUB.detail[key] = r.b && r.b.ok ? r.b : "error";
      if (SECTION === "companies") renderSection();
    });
  }
  function kamName(email) {
    if (!email) return "";
    var k = HUB.kams.filter(function (x) { return x.email === email; })[0];
    return k ? (k.name || k.email) : email;
  }
  function kamSelect(cur, label, blank, onpick) {
    var sel = h("select", { class: "hb-kam", "aria-label": label },
      h("option", { value: "" }, blank));
    HUB.kams.forEach(function (k) { sel.appendChild(h("option", { value: k.email }, (k.name && k.name !== k.email.split("@")[0] ? k.name + " · " : "") + k.email)); });
    sel.value = cur || "";
    sel.addEventListener("change", function () { onpick(sel.value, sel); });
    return sel;
  }
  function hubSetKam(kind, ref, email, after) {
    api("POST", "/api/hub/kam", { kind: kind, ref: ref, kam: email }).then(function (r) {
      var msg = (r.b && r.b.message) || (r.b && r.b.ok ? "Saved." : "Couldn't save that.");
      if (r.b && r.b.ok) after(); else renderSection();
      hubSay(msg, !(r.b && r.b.ok));
    });
  }
  var hubTimer = null;
  function hubSay(text, bad) {
    var el = $("hb-say"); if (!el) return;
    el.textContent = text; el.className = "hb-say" + (bad ? " hb-say--bad" : "") + " is-on";
    clearTimeout(hubTimer); hubTimer = setTimeout(function () { el.className = "hb-say"; }, 4200);
  }
  function hubFilter(c) {
    var q = HUB.q.trim().toLowerCase();
    if (q && (c.name + " " + c.domain).toLowerCase().indexOf(q) < 0) return false;
    if (HUB.f === "live") return c.live > 0;
    if (HUB.f === "waiting") return c.waiting > 0;
    if (HUB.f === "blocked") return c.blocked > 0;
    if (HUB.f === "nokam") return !c.kam.email && c.key !== "handed" && c.key !== "unassigned" && c.key !== "team";
    return true;
  }
  function itemStatus(kind, it) {
    if (kind === "selection") return h("span", { class: "hb-chip hb-chip--" + (it.status.key || "draft") }, it.status.label || "");
    var lab = it.status === "live" ? "Live" : it.status === "ended" ? "Completed" : (it.draft_by_client ? "Draft · client started" : "Draft");
    return h("span", { class: "hb-chip hb-chip--" + (it.status === "live" ? "live" : it.status === "ended" ? "completed" : "draft") }, lab);
  }
  // Move to another client (item 129 phase 2): search an account, confirm, done. Goes through "Assign to client",
  // so History records it and the client's bell rings.
  function movePanel(kind, it, solo) {
    var box = h("div", { class: "hb-share__col hb-move" }), msg = h("p", { class: "hb-share__msg", role: "status" });
    var q = h("input", { type: "search", autocomplete: "off", placeholder: "Search a client or company", "aria-label": "Move to client" });
    var res = h("ul", { class: "hb-move__res", "aria-label": "Matching clients" }), timer = null, picked = null;
    var confirmBox = h("div", { class: "hb-move__ok", hidden: "" });
    function pick(u) {
      picked = u; res.textContent = ""; q.value = "";
      var tell = h("input", { type: "checkbox", checked: "" });
      var yes = h("button", { class: "hc-btn hc-btn--ink hc-btn--sm", type: "button" }, "Confirm move");
      var no = h("button", { class: "hc-btn hc-btn--line hc-btn--sm", type: "button", onclick: function () { picked = null; confirmBox.hidden = true; confirmBox.textContent = ""; note(msg, ""); } }, "Cancel");
      confirmBox.textContent = ""; confirmBox.hidden = false;
      add(confirmBox, [h("p", null, "Move ", h("b", null, it.name), " to ", h("b", null, u.name || u.email), u.company ? " (" + u.company + ")" : "", "?"),
        h("small", null, "The campaign moves with its selection, brief and everything attached."),
        h("label", { class: "hb-move__opt" }, tell, "Tell the client (bell)"), h("div", { class: "hb-move__btns" }, yes, no)]);
      yes.addEventListener("click", function () {
        yes.disabled = true; note(msg, "Moving…");
        api("POST", "/api/hub/move", { kind: kind, ref: it.id, to: u.id, code: u.kind === "code" ? u.code_id : null, related: true, tell: tell.checked }).then(function (r) {
          yes.disabled = false;
          var ok = !!(r.b && r.b.ok);
          note(msg, (r.b && r.b.message) || (ok ? "Moved." : "Couldn't move that."), !ok);
          if (ok) { HUB.share = null; HUB.detail = {}; HUB.list = null; ALLC.items = null; renderSection(); hubSay((r.b && r.b.message) || "Moved.", false); }
        });
      });
    }
    function search() {
      var v = q.value.trim(); res.textContent = "";
      if (v.length < 2) return;
      api("GET", "/api/hub/people?q=" + encodeURIComponent(v)).then(function (r) {
        var list = (r.b && r.b.people) || [];
        if (!list.length) { res.appendChild(h("li", { class: "hb-none" }, "No client matches.")); return; }
        list.forEach(function (u) {
          res.appendChild(h("li", null, h("button", { type: "button", onclick: function () { pick(u); } },
            h("b", null, u.name || u.email), u.kind === "team" ? h("span", { class: "hb-chip hb-chip--approved" }, "Account manager") : null,
            h("small", null, [u.email, u.company].filter(Boolean).join(" · ")))));
        });
      });
    }
    q.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(search, 250); });
    add(box, [h("b", null, solo ? "Assign this " + kind + " to a client" : "Move to another client"), h("small", null, HUB.role === "admin" ? "Search a client, an access code, or a BlueHolding account manager (to hold it for now and share it with their client later). The campaign moves with its selection, brief and everything attached." : "Pick one of your own clients."), q, res, confirmBox, msg]);
    return box;
  }
  // Delete a campaign: one explicit confirm, then it goes (History can bring it back).
  function deletePanel(kind, it, closeFn) {
    var msg = h("p", { class: "hb-share__msg", role: "status" });
    var both = h("input", { type: "checkbox", checked: "" });
    var yes = h("button", { class: "hc-btn hc-btn--sm hb-danger", type: "button" }, kind === "campaign" ? "Delete campaign" : "Delete selection");
    var no = h("button", { class: "hc-btn hc-btn--line hc-btn--sm", type: "button", onclick: closeFn }, "Cancel");
    yes.addEventListener("click", function () {
      yes.disabled = true; note(msg, "Deleting…");
      api("POST", "/api/hub/delete", { kind: kind, ref: it.id, with_selection: both.checked }).then(function (r) {
        yes.disabled = false;
        var ok = !!(r.b && r.b.ok);
        note(msg, (r.b && r.b.message) || (ok ? "Deleted." : "Couldn't delete that."), !ok);
        if (ok) { HUB.share = null; HUB.detail = {}; HUB.list = null; ALLC.items = null; renderSection(); hubSay((r.b && r.b.message) || "Deleted.", false); }
      });
    });
    return h("div", { class: "hb-share hb-share--solo", role: "alertdialog", "aria-label": "Delete " + it.name },
      h("div", { class: "hb-share__col" }, h("b", null, "Delete “" + it.name + "”?"),
        h("small", null, "Its report and tracking links stop working at once. You can bring it back from History in the admin."),
        kind === "campaign" ? h("label", { class: "hb-move__opt" }, both, "Also delete its selection and brief (unless another campaign uses the selection)") : null,
        h("div", { class: "hb-move__btns" }, yes, no), msg),
      h("button", { class: "hb-share__x", type: "button", "aria-label": "Close", onclick: closeFn }, "×"));
  }
  function sharePanel(kind, it, closeFn, mode) {
    if (mode === "assign") {
      return h("div", { class: "hb-share hb-share--solo", role: "group", "aria-label": "Assign " + it.name }, movePanel(kind, it, true),
        h("button", { class: "hb-share__x", type: "button", "aria-label": "Close", onclick: closeFn }, "×"));
    }
    var admin = HUB.role === "admin", msg = h("p", { class: "hb-share__msg", role: "status" });
    var email = h("input", { type: "email", inputmode: "email", autocomplete: "off", placeholder: "name@company.com", "aria-label": "Client email" });
    var go = h("button", { class: "hc-btn hc-btn--ink hc-btn--sm", type: "submit" }, "Share");
    var role = kind === "campaign" ? h("select", { class: "hb-kam", "aria-label": "Access" }, h("option", { value: "view" }, "View only"), h("option", { value: "edit" }, "View and edit")) : null;
    var form = h("form", { class: "hb-share__form", novalidate: "" }, email, role, go);
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var v = email.value.trim(); if (!v) { note(msg, "Type an email address.", true); email.focus(); return; }
      go.disabled = true; note(msg, "Sending…");
      api("POST", "/api/hub/share", { kind: kind, ref: it.id, email: v, role: role ? role.value : "edit" }).then(function (r) {
        go.disabled = false;
        note(msg, (r.b && r.b.message) || (r.b && r.b.ok ? "Shared." : "Couldn't share that."), !(r.b && r.b.ok));
        if (r.b && r.b.ok) email.value = "";
      });
    });
    var copyBtn = h("button", { class: "hc-btn hc-btn--line hc-btn--sm", type: "button" }, icon("link"), " Copy link");
    copyBtn.addEventListener("click", function () { copy(new URL(ROOT + it.link, location.href).href, copyBtn, "Link copied"); });
    return h("div", { class: "hb-share", role: "group", "aria-label": "Share " + it.name },
      h("div", { class: "hb-share__col" }, h("b", null, "Share with a client"), h("small", null, "They sign in (or sign up) with that email. " + (kind === "campaign" ? "Pick view only or view and edit. Edit also opens its selection. " : "They can view and edit it. ") + "They are emailed the link."), form, msg),
      movePanel(kind, it),
      h("div", { class: "hb-share__col" }, h("b", null, "Copy the client link"), h("small", null, "The link opens for people who already have access."), copyBtn),
      h("button", { class: "hb-share__x", type: "button", "aria-label": "Close sharing", onclick: closeFn }, "×"));
  }
  // Assign KAM (owner, 2026-10-18): pick the account manager; the campaign moves with its selection, brief and everything attached
  // under THEIR account, and an access code it came from is removed when it is left empty.
  function kamPanel(kind, it, closeFn) {
    var msg = h("p", { class: "hb-share__msg", role: "status" }), confirmBox = h("div", { class: "hb-move__ok", hidden: "" }),
        list = h("ul", { class: "hb-move__res", "aria-label": "Account managers" });
    HUB.kams.forEach(function (k) {
      list.appendChild(h("li", null, h("button", { type: "button", onclick: function () { pick(k); } }, h("b", null, k.name || k.email), h("small", null, k.email))));
    });
    function pick(k) {
      var tell = h("input", { type: "checkbox", checked: "" });
      var yes = h("button", { class: "hc-btn hc-btn--ink hc-btn--sm", type: "button" }, "Confirm assign");
      var no = h("button", { class: "hc-btn hc-btn--line hc-btn--sm", type: "button", onclick: function () { confirmBox.hidden = true; confirmBox.textContent = ""; note(msg, ""); } }, "Cancel");
      confirmBox.textContent = ""; confirmBox.hidden = false;
      add(confirmBox, [h("p", null, "Assign ", h("b", null, it.name), " to ", h("b", null, k.name || k.email), "?"),
        h("small", null, "The campaign moves with its selection, brief and everything attached, and is filed under " + (k.name || k.email) + "'s account. " +
          "An access code it came from is removed once nothing else uses it. They can then share it with their client."),
        h("label", { class: "hb-move__opt" }, tell, "Tell them (email and bell)"), h("div", { class: "hb-move__btns" }, yes, no)]);
      yes.addEventListener("click", function () {
        yes.disabled = true; note(msg, "Assigning…");
        api("POST", "/api/hub/assign-kam", { kind: kind, ref: it.id, kam: k.email, tell: tell.checked }).then(function (r) {
          yes.disabled = false;
          var ok = !!(r.b && r.b.ok);
          note(msg, (r.b && r.b.message) || (ok ? "Assigned." : "Couldn't assign that."), !ok);
          if (ok) { HUB.share = null; HUB.detail = {}; HUB.list = null; ALLC.items = null; renderSection(); hubSay((r.b && r.b.message) || "Assigned.", false); }
        });
      });
    }
    return h("div", { class: "hb-share hb-share--solo", role: "group", "aria-label": "Assign a KAM to " + it.name },
      h("div", { class: "hb-share__col" }, h("b", null, "Assign a KAM to this " + kind), h("small", null, "Choose the BlueHolding account manager who will hold it."), list, confirmBox, msg),
      h("button", { class: "hb-share__x", type: "button", "aria-label": "Close", onclick: closeFn }, "×"));
  }
  // Item 177 (owner, 2026-10-20): an admin sets any campaign's board stage and takes it Live / Unlive from here.
  // The server checks the role (POST /api/board/stage and /api/board/live answer 403 to anyone else).
  var STAGES = [["draft", "Draft"], ["shortlisting", "Shortlisting"], ["review", "Client review"], ["approved", "Approved"], ["live", "Live"], ["completed", "Completed"]];
  function hubAfterStage(r) {
    var ok = !!(r.b && r.b.ok);
    if (ok) { HUB.detail = {}; HUB.list = null; ALLC.items = null; renderSection(); }
    else renderSection();
    // The list reloads after a change, so the message is kept for a few seconds and shown again on each redraw.
    HUB.say = { text: ((r.b && r.b.message) || (ok ? "Saved." : "Couldn't change that.")) + (!ok && r.b && r.b.setup ? " Set its dates on the campaign's Setup tab in the admin." : ""),
                bad: !ok, until: Date.now() + 4000 };
    hubSay(HUB.say.text, HUB.say.bad);
  }
  function hubSayAgain() { if (HUB.say && HUB.say.until > Date.now()) setTimeout(function () { hubSay(HUB.say.text, HUB.say.bad); }, 0); }
  function hubStage(it) {
    if (!it.stage) return null;
    if (!it.can_stage) return h("div", { class: "hb-it__grp hb-it__grp--stage" }, h("span", { class: "hb-chip hb-chip--stage" }, it.stage.label));
    var sel = h("select", { class: "hb-kam hb-stage", "aria-label": "Board stage of " + it.name });
    STAGES.forEach(function (s) { sel.appendChild(h("option", { value: s[0] }, s[1])); });
    sel.value = it.stage.key;
    sel.addEventListener("change", function () {
      sel.disabled = true;
      api("POST", "/api/board/stage", { id: it.id, to: sel.value }).then(hubAfterStage);
    });
    var live = it.status === "live";
    var btn = it.status === "ended" ? null : h("button", { class: "hb-assignbtn hb-livebtn" + (live ? "" : " is-primary"), type: "button",
      onclick: function () { btn.disabled = true; api("POST", "/api/board/live", { id: it.id, on: !live }).then(hubAfterStage); } }, live ? "Unlive" : "Go live");
    return h("div", { class: "hb-it__grp hb-it__grp--stage" }, h("label", { class: "hb-lab" }, "Stage", sel), btn);
  }
  // One card per campaign, with its selection inside it: they are one package (move, assign, share and delete act on both).
  function itemRow(kind, it, co) {
    var key = kind + ":" + it.id, mode = HUB.share === key ? HUB.shareMode : "";
    var shown = mode === "all", assigning = mode === "assign", deleting = mode === "delete", kaming = mode === "kam";
    var flagged = !!(co && co.key === "unassigned");
    function toggle(m) { return function () { if (HUB.share === key && HUB.shareMode === m) { HUB.share = null; } else { HUB.share = key; HUB.shareMode = m; } renderSection(); }; }
    var open = h("a", { class: "hb-open", href: ROOT + it.link, target: "_blank", rel: "noopener" }, "Open ", icon("arrow"));
    var openSel = kind === "campaign" && it.package ? h("a", { class: "hb-open", href: ROOT + it.package.link, target: "_blank", rel: "noopener" }, "Open selection ", icon("arrow")) : null;
    var kamBtn = it.can_kam ? h("button", { class: "hb-assignbtn hb-kambtn", type: "button", "aria-expanded": kaming ? "true" : "false", onclick: toggle("kam") }, icon("users"), "Assign KAM") : null;
    var assignBtn = h("button", { class: "hb-assignbtn" + (flagged && !kamBtn ? " is-primary" : ""), type: "button", "aria-expanded": assigning ? "true" : "false", onclick: toggle("assign") }, icon("users"), "Assign client");
    var shareBtn = h("button", { class: "hb-sharebtn", type: "button", "aria-expanded": shown ? "true" : "false", onclick: toggle("all") }, icon("link"), "Share");
    var delBtn = (kind === "campaign" || (kind === "selection" && HUB.role === "admin")) ? h("button", { class: "hb-delbtn", type: "button", "aria-expanded": deleting ? "true" : "false", onclick: toggle("delete") }, "Delete") : null;
    var pkg = kind === "campaign" && it.package;
    var stageCtl = kind === "campaign" ? hubStage(it) : null;
    var row = h("li", { class: "hb-it" },
      h("div", { class: "hb-it__main" },
        h("b", null, it.name), itemStatus(kind, it),
        kind === "selection" ? h("small", null, plural(it.creators, "creator")) : (it.has_selection ? null : h("small", null, "No selection yet")),
        it.kam ? h("small", { class: "hb-it__kam" }, "KAM " + kamName(it.kam)) : null,
        it.owner ? h("small", { class: "hb-it__owner" }, "Filed under " + it.owner.label) : null),
      pkg ? h("div", { class: "hb-it__sel" }, h("span", { class: "hb-it__tag" }, "Selection"), h("b", null, pkg.name), h("small", null, plural(pkg.creators, "creator")),
        h("span", { class: "hb-chip hb-chip--" + (pkg.status.key || "draft") }, pkg.status.label || "")) : null,
      h("div", { class: "hb-it__act" },
        h("div", { class: "hb-it__grp hb-it__grp--view" }, open, openSel),
        stageCtl,
        h("div", { class: "hb-it__grp hb-it__grp--manage" }, kamBtn, assignBtn, shareBtn),
        delBtn ? h("div", { class: "hb-it__grp hb-it__grp--danger" }, delBtn) : null));
    var close = function () { HUB.share = null; renderSection(); };
    if (shown) row.appendChild(sharePanel(kind, it, close, "all"));
    if (assigning) row.appendChild(sharePanel(kind, it, close, "assign"));
    if (kaming) row.appendChild(kamPanel(kind, it, close));
    if (deleting) row.appendChild(deletePanel(kind, it, close));
    return row;
  }
  /* Account controls on a person (item 209, slice b). Approve, hold and reactivate are one click; suspend and
     credits ask for the emailed code first (admins only). The server decides who may do what (p.can). */
  var STATE_LABEL = { waiting: "Waiting", active: "Active", held: "Held", suspended: "Suspended" };
  function acctSay(msg, bad) { var el = $("hb-say"); if (el) { el.textContent = msg; el.className = "hb-say" + (bad ? " hb-say--bad" : "") + " is-on"; } toast(0, msg); }
  function acctRefresh(co) { crmReload(); NEEDS.data = null; delete HUB.detail[co.key]; hubDetail(co.key); hubLoad(); if (DATA.cc) loadNeeds(); }
  function acctDo(p, co, action, extra, nicely) {
    var body = { id: p.id, action: action }; for (var k in (extra || {})) body[k] = extra[k];
    return api("POST", "/api/hub/account", body).then(function (r) {
      if (r.s === 403 && r.b && r.b.reason === "stepup") {
        return stepUp({ title: action === "suspend" ? "Suspend this account?" : "Change credits",
          why: action === "suspend" ? "Suspending signs this person out everywhere." : "A credit change is recorded under your name.",
          what: (action === "suspend" ? "Suspend " : "Change credits for ") + (p.name || p.email), sub: co.name,
          ok: action === "suspend" ? "Suspend account" : "Change credits", danger: action === "suspend" }).then(function (ok) {
          return ok ? acctDo(p, co, action, extra, nicely) : null;
        });
      }
      if (r.s === 200) { acctSay(r.b.message || "Done."); acctRefresh(co); if (nicely) nicely(); }
      else acctSay((r.b && r.b.message) || "That didn't work. Try again.", true);
    });
  }
  function acctControls(p, co) {
    var can = p.can || [], pk = (co.key || "") + ":" + (p.id || p.email);
    var st = p.state || "active";
    var out = h("div", { class: "cc-ctl" }, h("span", { class: "cc-stat cc-stat--" + (st === "suspended" ? "susp" : st === "waiting" ? "wait" : st) }, STATE_LABEL[st] || st),
      p.credits != null && p.id ? h("span", { class: "cc-cred", title: "Credits left" }, icon("coin"), String(p.credits)) : null);
    var acts = h("div", { class: "cc-ctl__acts" });
    function btn(label, action, primary) {
      var b = h("button", { class: "hc-btn hc-btn--sm" + (primary ? "" : " hc-btn--line"), type: "button" }, label);
      b.addEventListener("click", function () { b.disabled = true; acctDo(p, co, action).then(function () { b.disabled = false; }); });
      return b;
    }
    if (can.indexOf("approve") >= 0) acts.appendChild(btn("Approve", "approve", true));
    if (can.indexOf("reactivate") >= 0) acts.appendChild(btn("Reactivate", "reactivate", true));
    if (can.indexOf("hold") >= 0) acts.appendChild(btn("Hold", "hold", false));
    var more = [];
    if (st === "active") more.push(["Push to " + (p.name || p.email).split(" ")[0], "bell", function () { openCompose(co.key, co.name, { people: [p.id] }); }, false, true]);
    if (can.indexOf("suspend") >= 0) more.push(["Suspend account", "ban", function () { acctDo(p, co, "suspend"); }, true]);
    if (can.indexOf("credits") >= 0) more.push(["Change credits", "coin", function () { HUB.ctl = HUB.ctl === pk + ":cr" ? null : pk + ":cr"; renderSection(); }, false]);
    if (more.length) {
      var open = HUB.ctl === pk + ":m";
      var mb = h("button", { class: "cc-rowmenu-btn", type: "button", "aria-expanded": open ? "true" : "false", "aria-label": "More actions for " + (p.name || p.email),
        onclick: function () { HUB.ctl = open ? null : pk + ":m"; renderSection(); } }, icon("dots"));
      acts.appendChild(mb);
      if (open) {
        var pop = h("div", { class: "cc-pop", role: "menu" });
        more.forEach(function (m) {
          pop.appendChild(h("button", { type: "button", role: "menuitem", class: m[3] ? "is-danger" : "", onclick: function () { HUB.ctl = null; m[2](); } }, icon(m[1]), m[0], m[4] ? null : h("span", { class: "cc-lockmark" }, icon("shield"), "Code")));
        });
        pop.appendChild(h("small", null, "\"Code\" asks for a fresh emailed code. Every change is in History with undo."));
        acts.appendChild(pop);
      }
    }
    out.appendChild(acts);
    if (HUB.ctl === pk + ":cr") {
      var amt = h("input", { type: "number", min: "-1000", max: "1000", step: "1", placeholder: "+10 or -5", "aria-label": "Credits to add (negative removes)" });
      var why = h("input", { type: "text", maxlength: "100", placeholder: "Reason (optional)", "aria-label": "Reason" });
      var go = h("button", { class: "hc-btn hc-btn--sm", type: "button" }, "Change credits");
      go.addEventListener("click", function () { go.disabled = true; acctDo(p, co, "credits", { amount: Number(amt.value), reason: why.value }, function () { HUB.ctl = null; }).then(function () { go.disabled = false; }); });
      out.appendChild(h("div", { class: "cc-credform" }, amt, why, go, h("button", { class: "hc-more", type: "button", onclick: function () { HUB.ctl = null; renderSection(); } }, "Cancel")));
    }
    return out;
  }
  function personBlock(p, co) {
    var admin = HUB.role === "admin";
    var pk = (co.key || "") + ":" + (p.id || p.email || p.name), open = !!HUB.openP[pk];
    var pbtn = h("button", { class: "hb-p__btn", type: "button", "aria-expanded": open ? "true" : "false",
      onclick: function () { HUB.openP[pk] = !open; renderSection(); } },
      h("span", { class: "hb-p__who" }, h("b", null, p.name || p.email), h("small", null, [p.job_title, p.email].filter(Boolean).join(" · ")),
        p.last_login_at ? h("small", null, "Last in " + ago(p.last_login_at)) : null),
      h("span", { class: "hb-p__n" }, plural(p.selections.length, "selection") + " · " + plural(p.campaigns.length, "campaign")),
      h("span", { class: "hb-chev", "aria-hidden": "true", html: '<svg viewBox="0 0 12 12"><path d="M3 4.5l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>' }));
    var head = h("div", { class: "hb-p__head" }, pbtn,
      admin && p.id && !p.staff ? h("label", { class: "hb-lab" }, "KAM", kamSelect(p.kam && p.kam !== (co.kam && co.kam.email) ? p.kam : "", "Account manager for " + (p.name || p.email),
        co.kam && co.kam.email ? "Follows the company (" + kamName(co.kam.email) + ")" : "No account manager", function (v) {
          hubSetKam("person", p.id, v, function () { p.kam = v || (co.kam && co.kam.email) || ""; renderSection(); });
        })) : (p.kam ? h("small", { class: "hb-it__kam" }, "KAM " + kamName(p.kam)) : null));
    var ctl = p.id && !p.staff && p.state ? acctControls(p, co) : null;
    if (ctl && (p.phone || true)) {
      var dm_ = h("button", { class: "cc-dm" + (p.decision_maker ? " is-on" : ""), type: "button", "aria-pressed": p.decision_maker ? "true" : "false",
        title: "Mark as a decision maker", onclick: function () { api("POST", "/api/crm/person", { id: p.id, decision_maker: !p.decision_maker }).then(function (r) { if (r.s === 200) { p.decision_maker = !p.decision_maker; renderSection(); } }); } },
        icon("star"), p.decision_maker ? "Decision maker" : "Mark decision maker");
      ctl.insertBefore(h("span", { class: "cc-contact" }, dm_, p.phone ? h("span", { class: "cc-phone-staff", title: "Staff only" }, icon("lock"), p.phone) : null), ctl.querySelector(".cc-ctl__acts"));
    }
    var sels = h("ul", { class: "hb-items" }), camps = h("ul", { class: "hb-items" });
    var loose = p.selections.filter(function (x) { return !x.in_campaign; });
    loose.forEach(function (x) { sels.appendChild(itemRow("selection", x, co)); });
    p.campaigns.forEach(function (x) { camps.appendChild(itemRow("campaign", x, co)); });
    return h("section", { class: "hb-p" + (open ? " is-open" : "") }, head, ctl, open ?
      h("div", { class: "hb-p__cols" },
        h("div", null, h("h4", null, "Campaigns, each with its selection ", h("span", null, String(p.campaigns.length))), p.campaigns.length ? camps : h("p", { class: "hb-none" }, "No campaigns.")),
        h("div", null, h("h4", null, "Selections without a campaign ", h("span", null, String(loose.length))), loose.length ? sels : h("p", { class: "hb-none" }, "None."))) : null);
  }
  function companyBlock(c) {
    var admin = HUB.role === "admin", open = !!HUB.open[c.key], det = HUB.detail[c.key];
    var btn = h("button", { class: "hb-co__btn", type: "button", "aria-expanded": open ? "true" : "false", "aria-controls": "hb-" + c.key.replace(/[^a-z0-9]/gi, "_"),
      onclick: function () { HUB.open[c.key] = !open; if (!open && !HUB.detail[c.key]) hubDetail(c.key); renderSection(); } },
      h("span", { class: "hb-co__name" }, h("b", null, c.name), c.domain ? h("small", null, c.domain) : (c.note ? h("small", null, c.note) : null)),
      h("span", { class: "hb-co__n" }, plural(c.people, "person", "people") + " · " + plural(c.selections, "selection") + " · " + plural(c.campaigns, "campaign") + (c.live ? " · " + c.live + " live" : ""),
        c.waiting ? h("span", { class: "cc-badge" }, c.waiting + " waiting") : null, c.blocked ? h("span", { class: "cc-badge cc-badge--grey" }, c.blocked + " held or suspended") : null),
      h("span", { class: "hb-chev", "aria-hidden": "true", html: '<svg viewBox="0 0 12 12"><path d="M3 4.5l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>' }));
    var kam = admin && c.domain ? h("label", { class: "hb-lab" }, "KAM", kamSelect(c.kam.email, "Account manager for " + c.name, "No account manager", function (v) {
      hubSetKam("company", c.domain, v, function () { c.kam = { email: v, name: kamName(v) }; HUB.detail = {}; renderSection(); if (HUB.open[c.key]) hubDetail(c.key); });
    })) : (c.kam && c.kam.email ? h("small", { class: "hb-it__kam" }, "KAM " + (c.kam.name || kamName(c.kam.email))) : null);
    if (open && !det) hubDetail(c.key);               // reopened after a move: fetch again
    var li = h("li", { class: "hb-co" + (open ? " is-open" : "") + (c.key === "unassigned" ? " hb-co--flag" : "") }, h("div", { class: "hb-co__row" }, btn, kam));
    if (open) {
      var body = h("div", { class: "hb-co__body", id: "hb-" + c.key.replace(/[^a-z0-9]/gi, "_") });
      if (det === "loading" || !det) body.appendChild(h("p", { class: "hb-none", role: "status" }, "Loading…"));
      else if (det === "error") body.appendChild(h("p", { class: "hb-none" }, "This company couldn't be loaded. Please try again."));
      else if (!det.people.length) body.appendChild(h("p", { class: "hb-none" }, "No people yet."));
      else det.people.forEach(function (p) { body.appendChild(personBlock(p, det)); });
      li.appendChild(body);
    }
    return li;
  }
  /* ------------------------------------------------------ All campaigns (flat) */
  // Every campaign in one searchable list, wherever it is filed (a client, a team account, an access code, nobody).
  // Same actions as the tree: Open, Assign client, Share, Delete.
  var ALLC = { q: "", items: null, total: 0, busy: false, timer: null };
  function loadAllCampaigns(more) {
    if (ALLC.busy) return;
    ALLC.busy = true;
    var off = more && ALLC.items ? ALLC.items.length : 0;
    api("GET", "/api/hub/campaigns?q=" + encodeURIComponent(ALLC.q) + "&offset=" + off).then(function (r) {
      ALLC.busy = false;
      if (r.b && r.b.ok) { ALLC.items = (more && ALLC.items ? ALLC.items : []).concat(r.b.items); ALLC.total = r.b.total; HUB.role = r.b.role || HUB.role; }
      else ALLC.items = ALLC.items || [];
      if (SECTION === "companies" && HUB.view === "campaigns") renderSection();
    });
  }
  function renderAllCampaigns(p) {
    var q = h("input", { class: "hb-search", type: "search", placeholder: "Search a campaign, brand, client or who it is filed under", "aria-label": "Search campaigns", value: ALLC.q });
    q.addEventListener("input", function () {
      ALLC.q = q.value; clearTimeout(ALLC.timer);
      ALLC.timer = setTimeout(function () { ALLC.items = null; ALLC.refocus = true; renderSection(); }, 300);
    });
    add(p, h("div", { class: "hb-tools" }, q));
    add(p, h("p", { class: "hb-say", id: "hb-say", role: "status" })); hubSayAgain();
    if (ALLC.refocus) { ALLC.refocus = false; setTimeout(function () { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 0); }
    if (!ALLC.items) {
      add(p, h("div", { class: "kc-skel", "aria-hidden": "true" }, h("i"), h("i"), h("i")));
      add(p, h("p", { class: "hc-sr", role: "status" }, "Loading the campaigns"));
      if (!HUB.kams.length) { hubLoad(); }
      loadAllCampaigns(false);
      return;
    }
    add(p, h("p", { class: "hb-none" }, plural(ALLC.total, "campaign") + (ALLC.q ? " match" : " in all")));
    var list = h("ul", { class: "hb-items hb-items--flat" });
    ALLC.items.forEach(function (c) { list.appendChild(itemRow("campaign", c, null)); });
    add(p, ALLC.items.length ? list : h("div", { class: "hc-empty" }, h("b", null, "No campaign matches"), h("p", null, "Try another search.")));
    if (ALLC.items.length < ALLC.total) {
      add(p, h("button", { class: "hc-btn hc-btn--line", type: "button", onclick: function () { loadAllCampaigns(true); } }, "Show more campaigns"));
    }
  }
  function hubViewBar() {
    var bar = h("div", { class: "kc-filter hb-views", role: "group", "aria-label": "View" });
    [["companies", "Companies"], ["campaigns", "All campaigns"]].forEach(function (v) {
      bar.appendChild(h("button", { class: "kc-chip", type: "button", "aria-pressed": HUB.view === v[0] ? "true" : "false",
        onclick: function () { HUB.view = v[0]; HUB.share = null; if (v[0] === "campaigns") ALLC.items = null; renderSection(); } }, v[1]));
    });
    return bar;
  }


  /* ------------------------------------------- Companies as an account CRM (items 209 + 220) */
  // A table of every company (board by stage as the other view); a row opens the company page: header (KAM, stage,
  // health, next step), then People (with the account controls), Work, Quotes, Notes. Staff only; money, notes, health and
  // phone numbers never reach a client. The server scopes everything; a KAM sees her own companies.
  var CRM = { data: null, kams: [], err: false, busy: false, q: "", f: "all", kam: "", stage: "", health: "", view: "table", sort: "name", dir: 1,
              page: null, tab: "people", det: null, adding: false, say: "" };
  var STAGE_IC = { lead: "seed", engaged: "chat", quote: "quote", active: "live", repeat: "redo", dormant: "moon" };
  var STAGE_HINT = { lead: "Added by us, or signed up with nothing yet", engaged: "A selection or an AI brief", quote: "An open quote request",
                     active: "A campaign is live", repeat: "A second campaign started", dormant: "90 days with no activity" };
  var HEALTH_LABEL = { good: "Healthy", moderate: "Watch", low: "At risk", none: "No signal yet" };
  function crmLoad(force) {
    if (CRM.busy || (CRM.data && !force)) return;
    CRM.busy = true;
    api("GET", "/api/crm/companies").then(function (r) {
      CRM.busy = false;
      if (r.s === 200) { CRM.data = r.b; CRM.err = false; if (r.b.kams) HUB.kams = r.b.kams; }
      else CRM.err = true;
      if (SECTION === "companies") renderSection();
    });
  }
  function crmReload() { CRM.data = null; crmLoad(true); }
  function sar(n) { return n ? big(n) + " SAR" : "—"; }
  function stagePill(c) {
    var s = c.stage;
    return h("span", { class: "cc-st cc-st--" + s, title: STAGE_HINT[s] + (c.stage_override ? " (set by hand)" : "") }, icon(STAGE_IC[s]),
      (CRM.data.stages.filter(function (x) { return x.key === s; })[0] || {}).label || s, c.stage_override ? h("span", { class: "cc-st__ov" }, "set") : null);
  }
  function healthPill(c) {
    var g = c.health;
    return h("span", { class: "ac-sig ac-sig--" + (g === "none" ? "none" : g), title: c.why || "" }, HEALTH_LABEL[g] || g);
  }
  function kamDisc(c) {
    var e = c.kam && c.kam.email;
    return e ? h("span", { class: "cc-kam", title: c.kam.name || e }, initials(c.kam.name || e)) : h("span", { class: "cc-dim" }, "—");
  }
  function logoFor(c, big_) {
    return h("span", { class: "cc-logo" + (big_ ? " cc-logo--lg" : "") }, h("span", null, initials(c.name)));
  }
  function crmFilter(c) {
    var q = CRM.q.trim().toLowerCase();
    if (q && (c.name + " " + c.domain).toLowerCase().indexOf(q) < 0) return false;
    if (CRM.kam === "none" ? !!(c.kam && c.kam.email) : CRM.kam && (c.kam && c.kam.email) !== CRM.kam) return false;
    if (CRM.stage && c.stage !== CRM.stage) return false;
    if (CRM.health && c.health !== CRM.health) return false;
    var me = (DATA.user.email || "").toLowerCase();
    switch (CRM.f) {
      case "mine": return (c.kam && (c.kam.email || "").toLowerCase()) === me;
      case "red": return c.health === "low";
      case "quotes": return c.open_n > 0;
      case "waiting": return c.waiting > 0;
      case "blocked": return c.blocked > 0;
      case "prospects": return c.prospect;
      case "overdue": return c.overdue;
      case "live": return c.live > 0;
    }
    return true;
  }
  var HEALTH_RANK = { low: 0, moderate: 1, good: 2, none: 3 };
  function crmSort(a, b) {
    var k = CRM.sort, d = CRM.dir, r;
    if (k === "stage") r = CRM.data.stages.map(function (x) { return x.key; }).indexOf(a.stage) - CRM.data.stages.map(function (x) { return x.key; }).indexOf(b.stage);
    else if (k === "health") r = HEALTH_RANK[a.health] - HEALTH_RANK[b.health];
    else if (k === "last") r = (a.last || 0) - (b.last || 0);
    else if (k === "approved") r = a.approved_sar - b.approved_sar;
    else if (k === "open") r = a.open_sar - b.open_sar;
    else if (k === "next") r = (a.next_due || 9e12) - (b.next_due || 9e12);
    else r = (a.name || "").toLowerCase() < (b.name || "").toLowerCase() ? -1 : 1;
    return r * d;
  }
  function openCompany(key, tab) {
    CRM.page = key; CRM.tab = tab || "people"; CRM.det = null; CRM.say = "";
    if (!HUB.detail[key] || HUB.detail[key] === "error") hubDetail(key);
    api("GET", "/api/crm/company?k=" + encodeURIComponent(key)).then(function (r) {
      if (CRM.page !== key) return;
      CRM.det = r.s === 200 ? r.b : "error";
      if (SECTION === "companies") renderSection();
    });
    if (location.hash !== "#companies") location.hash = "#companies"; else renderSection();
  }
  function closeCompany() { CRM.page = null; CRM.det = null; renderSection(); window.scrollTo(0, 0); }

  function crmToolbar() {
    var d = CRM.data.rows;
    var me = (DATA.user.email || "").toLowerCase();
    var seg = h("div", { class: "cc-seg", role: "group", "aria-label": "View" });
    [["table", "Table", "filter"], ["board", "Board", "grid"]].forEach(function (v) {
      seg.appendChild(h("button", { type: "button", "aria-pressed": CRM.view === v[0] ? "true" : "false",
        onclick: function () { CRM.view = v[0]; renderSection(); } }, icon(v[2]), v[1]));
    });
    var views = h("div", { class: "cc-views", role: "group", "aria-label": "Saved views" });
    [["all", "All", d.length], ["mine", "Mine", d.filter(function (c) { return (c.kam && (c.kam.email || "").toLowerCase()) === me; }).length],
     ["red", "At risk", d.filter(function (c) { return c.health === "low"; }).length],
     ["quotes", "Quotes waiting", d.filter(function (c) { return c.open_n > 0; }).length],
     ["waiting", "Waiting approval", d.filter(function (c) { return c.waiting > 0; }).length],
     ["blocked", "Held or suspended", d.filter(function (c) { return c.blocked > 0; }).length],
     ["overdue", "Overdue", d.filter(function (c) { return c.overdue; }).length],
     ["live", "Has a live campaign", d.filter(function (c) { return c.live > 0; }).length],
     ["prospects", "Prospects", d.filter(function (c) { return c.prospect; }).length]].forEach(function (v) {
      views.appendChild(h("button", { class: "cc-chip", type: "button", "aria-pressed": CRM.f === v[0] ? "true" : "false",
        onclick: function () { CRM.f = v[0]; renderSection(); } }, v[1], h("em", null, String(v[2]))));
    });
    var q = h("input", { type: "search", placeholder: "Search a company or domain", "aria-label": "Search companies", value: CRM.q });
    q.addEventListener("input", function () { CRM.q = q.value; var pos = q.selectionStart; renderSection(); var n = document.querySelector(".cc-search input"); if (n) { n.focus(); n.setSelectionRange(pos, pos); } });
    function pick(label, cur, opts, on) {
      var sel = h("select", { class: "cc-select", "aria-label": label });
      opts.forEach(function (o) { sel.appendChild(h("option", { value: o[0] }, o[1])); });
      sel.value = cur; sel.addEventListener("change", function () { on(sel.value); renderSection(); });
      return sel;
    }
    var kamOpts = [["", "Any account manager"], ["none", "No account manager"]].concat(HUB.kams.map(function (k) { return [k.email, k.name || k.email]; }));
    var filters = h("div", { class: "cc-filters" }, h("label", { class: "cc-search" }, icon("search"), q),
      pick("Account manager", CRM.kam, kamOpts, function (v) { CRM.kam = v; }),
      pick("Stage", CRM.stage, [["", "Any stage"]].concat(CRM.data.stages.map(function (x) { return [x.key, x.label]; })), function (v) { CRM.stage = v; }),
      pick("Health", CRM.health, [["", "Any health"], ["good", "Healthy"], ["moderate", "Watch"], ["low", "At risk"]], function (v) { CRM.health = v; }));
    var add_ = h("button", { class: "hc-btn hc-btn--sm", type: "button", onclick: function () { CRM.adding = !CRM.adding; renderSection(); } }, icon("plus"), "Add prospect");
    return [h("div", { class: "cc-tools" }, seg, add_), views, filters];
  }
  function prospectForm() {
    var name = h("input", { type: "text", maxlength: "120", placeholder: "Company name", "aria-label": "Company name" });
    var dom = h("input", { type: "text", placeholder: "Website, like avalonpharma.com", "aria-label": "Company website domain" });
    var step = h("input", { type: "text", maxlength: "200", placeholder: "Next step (optional)", "aria-label": "Next step" });
    var due = h("input", { type: "date", "aria-label": "Due date" });
    var msg = h("p", { class: "cc-msg", role: "status" });
    var go = h("button", { class: "hc-btn hc-btn--sm", type: "button" }, "Add as a lead");
    go.addEventListener("click", function () {
      go.disabled = true; msg.textContent = "";
      api("POST", "/api/crm/prospect", { name: name.value, domain: dom.value, next_step: step.value, next_due: due.value ? Math.floor(new Date(due.value + "T00:00:00").getTime() / 1000) : null }).then(function (r) {
        go.disabled = false;
        if (r.s === 200) { CRM.adding = false; toast(0, r.b.message); crmReload(); }
        else msg.textContent = (r.b && r.b.message) || "Could not add it. Try again.";
      });
    });
    return h("form", { class: "cc-credform cc-prosp", onsubmit: function (e) { e.preventDefault(); } }, name, dom, step, due, go,
      h("button", { class: "hc-more", type: "button", onclick: function () { CRM.adding = false; renderSection(); } }, "Cancel"), msg);
  }
  function crmTable(rows) {
    var cols = [["name", "Company"], [null, "KAM"], ["stage", "Stage"], ["health", "Health"], [null, "Accounts"],
                ["open", "Open quotes"], ["approved", "Approved, 12 months"], ["last", "Last activity"], ["next", "Next step"]];
    var tr = h("tr");
    cols.forEach(function (c) {
      var th = h("th", { scope: "col", "aria-sort": c[0] && CRM.sort === c[0] ? (CRM.dir > 0 ? "ascending" : "descending") : null });
      if (c[0]) th.appendChild(h("button", { type: "button", onclick: function () { if (CRM.sort === c[0]) CRM.dir = -CRM.dir; else { CRM.sort = c[0]; CRM.dir = 1; } renderSection(); } },
        c[1], CRM.sort === c[0] ? icon("down") : null));
      else th.textContent = c[1];
      tr.appendChild(th);
    });
    var tb = h("tbody");
    rows.forEach(function (c) {
      var link = h("a", { href: "#companies", onclick: function (e) { e.preventDefault(); openCompany(c.key); } },
        h("b", null, c.name), c.prospect ? h("span", { class: "cc-prospect" }, "Prospect") : null, h("small", null, c.domain));
      var next = c.next_step ? h("div", { class: "cc-next" }, h("b", null, c.next_step), c.next_due ? h("small", { class: c.overdue ? "late" : "" }, (c.overdue ? "Late · " : "") + dm(c.next_due)) : null)
        : h("div", { class: "cc-next" }, h("b", { class: "cc-dim" }, "No next step"));
      var row = h("tr", { onclick: function (e) { if (!e.target.closest("a,button")) openCompany(c.key); } },
        h("td", { class: "cc-m-full" }, h("div", { class: "cc-co" }, logoFor(c), link)),
        h("td", { "data-k": "KAM" }, kamDisc(c)), h("td", { "data-k": "Stage" }, stagePill(c)), h("td", { "data-k": "Health" }, healthPill(c)),
        h("td", { "data-k": "Accounts" }, c.prospect ? h("span", { class: "cc-dim" }, "None yet") : [String(c.people), c.waiting ? h("span", { class: "cc-badge" }, c.waiting + " waiting") : null,
          c.blocked ? h("span", { class: "cc-badge cc-badge--grey" }, c.blocked + " held") : null]),
        h("td", { class: "num", "data-k": "Open quotes" }, c.open_n ? h("span", { class: "cc-sar" }, c.open_sar ? big(c.open_sar) : "?", h("small", null, "SAR")) : h("span", { class: "cc-dim" }, "—")),
        h("td", { class: "num cc-m-hide" }, c.approved_sar ? h("span", { class: "cc-sar" }, big(c.approved_sar), h("small", null, "SAR")) : h("span", { class: "cc-dim" }, "—")),
        h("td", { class: "cc-m-hide cc-dim" }, c.last ? ago(c.last) : "—"),
        h("td", { class: "cc-m-full", "data-k": "Next step" }, next));
      tb.appendChild(row);
    });
    return h("div", { class: "cc-twrap" }, h("table", { class: "cc-t" }, h("thead", null, tr), tb));
  }
  function crmBoard(rows) {
    var board = h("div", { class: "cc-board" });
    CRM.data.stages.forEach(function (st) {
      var mine = rows.filter(function (c) { return c.stage === st.key; });
      var lane = h("section", { class: "cc-lane cc-lane--" + st.key }, h("div", { class: "cc-lane__hd" }, icon(STAGE_IC[st.key]), h("h3", null, st.label), h("span", null, String(mine.length))),
        h("p", { class: "cc-lane__hint" }, STAGE_HINT[st.key]));
      mine.forEach(function (c) {
        lane.appendChild(h("div", { class: "cc-card", tabindex: "0", role: "button", "aria-label": "Open " + c.name,
          onclick: function () { openCompany(c.key); }, onkeydown: function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openCompany(c.key); } } },
          h("div", { class: "cc-card__top" }, logoFor(c), h("b", null, c.name)),
          h("div", { class: "cc-card__meta" }, c.open_n ? h("span", null, (c.open_sar ? big(c.open_sar) + " SAR" : "Quote") + " open") : healthPill(c), kamDisc(c))));
      });
      board.appendChild(lane);
    });
    return board;
  }
  function renderCrm(p) {
    if (CRM.err) { add(p, h("div", { class: "hc-empty" }, h("b", null, "The companies did not load."), h("p", null, h("button", { class: "hc-more", type: "button", onclick: function () { CRM.err = false; crmLoad(true); renderSection(); } }, "Try again")))); return; }
    if (!CRM.data) { add(p, h("div", { class: "kc-skel", "aria-hidden": "true" }, h("i"), h("i"), h("i"))); add(p, h("p", { class: "hc-sr", role: "status" }, "Loading the companies")); crmLoad(); return; }
    crmToolbar().forEach(function (n) { add(p, n); });
    if (CRM.adding) add(p, prospectForm());
    add(p, h("p", { class: "hb-say", id: "hb-say", role: "status" })); hubSayAgain();
    var rows = CRM.data.rows.filter(crmFilter).sort(crmSort);
    if (!rows.length) { add(p, h("div", { class: "hc-empty" }, h("b", null, "No company matches"), h("p", null, "Try another search, or show all companies."))); return; }
    add(p, CRM.view === "board" ? crmBoard(rows) : crmTable(rows));
    add(p, h("div", { class: "cc-tfoot" }, h("span", null, "Showing " + rows.length + " of " + CRM.data.rows.length + " companies"),
      h("span", null, "Money is from portal quotes only, before VAT. Only admins and the company's KAM see it.")));
  }

  /* ---- the company page */
  function crmSave(key, fields, then) {
    return api("POST", "/api/crm/set", Object.assign({ key: key }, fields)).then(function (r) {
      if (r.s === 200) { var i = CRM.data ? CRM.data.rows.map(function (x) { return x.key; }).indexOf(key) : -1; if (i >= 0 && r.b.row) CRM.data.rows[i] = r.b.row; if (CRM.det && CRM.det.row && r.b.row) CRM.det.row = r.b.row; toast(0, "Saved."); if (then) then(); renderSection(); }
      else toast(0, (r.b && r.b.message) || "Could not save that.");
    });
  }
  function companyHeader(c) {
    var admin = HUB.role === "admin";
    var stageSel = h("select", { class: "cc-select cc-select--tight", "aria-label": "Stage" });
    stageSel.appendChild(h("option", { value: "" }, "Automatic: " + ((CRM.data.stages.filter(function (x) { return x.key === c.stage_auto; })[0] || {}).label || c.stage_auto)));
    CRM.data.stages.forEach(function (x) { stageSel.appendChild(h("option", { value: x.key }, x.label)); });
    stageSel.value = c.stage_override ? c.stage : "";
    stageSel.addEventListener("change", function () { crmSave(c.key, { stage: stageSel.value }); });
    var step = h("input", { type: "text", maxlength: "200", value: c.next_step, placeholder: "What happens next?", "aria-label": "Next step" });
    var due = h("input", { type: "date", "aria-label": "Due date", value: c.next_due ? new Date(c.next_due * 1000).toISOString().slice(0, 10) : "" });
    var save = h("button", { class: "hc-btn hc-btn--sm", type: "button" }, "Save");
    save.addEventListener("click", function () {
      save.disabled = true;
      crmSave(c.key, { next_step: step.value, next_due: due.value ? Math.floor(new Date(due.value + "T00:00:00").getTime() / 1000) : null }).then(function () { save.disabled = false; });
    });
    var kam = admin && c.domain && !c.prospect ? kamSelect(c.kam.email, "Account manager for " + c.name, "No account manager", function (v) {
      hubSetKam("company", c.domain, v, function () { crmReload(); delete HUB.detail[c.key]; hubDetail(c.key); });
    }) : (c.kam && c.kam.email ? h("span", { class: "cc-pickpill" }, kamDisc(c), c.kam.name || c.kam.email) : h("span", { class: "cc-dim" }, "No account manager"));
    return h("section", { class: "cc-acct", "aria-labelledby": "cc-name" },
      h("div", { class: "cc-acct__top" }, logoFor(c, true),
        h("div", { class: "cc-acct__name" }, h("h1", { id: "cc-name" }, c.name),
          h("p", null, c.domain ? h("span", { class: "cc-dom" }, c.domain) : null, h("span", null, c.prospect ? "Prospect · nobody has signed up yet" : plural(c.people, "person", "people"))))),
      h("dl", { class: "cc-acct__fields" },
        h("div", null, h("dt", null, "Account manager"), h("dd", null, kam)),
        h("div", null, h("dt", null, "Stage"), h("dd", null, stagePill(c), stageSel)),
        h("div", null, h("dt", null, "Health"), h("dd", { class: "cc-health" }, healthPill(c), h("p", null, c.why || ""))),
        h("div", null, h("dt", null, "Next step"), h("dd", { class: "cc-nextedit" }, step, due, save))),
      h("div", { class: "cc-acts" },
        h("button", { class: "hc-btn hc-btn--sm", type: "button", onclick: function () { CRM.tab = "notes"; renderSection(); } }, icon("note"), "Add note"),
        c.prospect ? null : h("button", { class: "hc-btn hc-btn--sm hc-btn--line", type: "button", onclick: function () { openCompose(c.key, c.name); } }, icon("bell"), "Push to this client"),
        DATA.cc && DATA.cc.admin_links && c.domain && !c.prospect ? h("a", { class: "cc-admin", href: adminUrl("/clients"), target: "_blank", rel: "noopener" }, "Open in admin ", icon("ext")) : null));
  }
  function peopleTab(c) {
    var det = HUB.detail[c.key];
    if (c.prospect) return h("div", { class: "hc-empty" }, h("b", null, "Nobody has signed up yet"), h("p", null, "When someone from " + c.domain + " signs up, this lead becomes an account and their people appear here."));
    if (det === "loading" || !det) return h("p", { class: "hb-none", role: "status" }, "Loading…");
    if (det === "error") return h("p", { class: "hb-none" }, "The people couldn't be loaded. Please try again.");
    var wrap = h("div", { class: "cc-people" });
    det.people.forEach(function (pp) { wrap.appendChild(personBlock(pp, det)); });
    return det.people.length ? wrap : h("p", { class: "hb-none" }, "No people yet.");
  }
  function workTab(c) {
    var det = HUB.detail[c.key];
    if (!det || det === "loading") return h("p", { class: "hb-none", role: "status" }, "Loading…");
    if (det === "error") return h("p", { class: "hb-none" }, "This could not be loaded.");
    var camps = h("ul", { class: "hb-items" }), sels = h("ul", { class: "hb-items" }), nc = 0, ns = 0;
    det.people.forEach(function (pp) {
      pp.campaigns.forEach(function (x) { nc++; camps.appendChild(itemRow("campaign", x, det)); });
      pp.selections.filter(function (x) { return !x.in_campaign; }).forEach(function (x) { ns++; sels.appendChild(itemRow("selection", x, det)); });
    });
    return h("div", { class: "hb-p__cols" },
      h("div", null, h("h4", null, "Campaigns, each with its selection ", h("span", null, String(nc))), nc ? camps : h("p", { class: "hb-none" }, "No campaigns.")),
      h("div", null, h("h4", null, "Selections without a campaign ", h("span", null, String(ns))), ns ? sels : h("p", { class: "hb-none" }, "None.")));
  }
  function quotesTab(c) {
    var d = CRM.det;
    if (!d) return h("p", { class: "hb-none", role: "status" }, "Loading…");
    if (d === "error") return h("p", { class: "hb-none" }, "The quotes could not be loaded.");
    if (!d.quotes.length) return h("div", { class: "hc-empty" }, h("b", null, "No quote requests yet"), h("p", null, "When this company asks for a quote from a selection, it shows here. Type the value when you send it and the approved value when they say yes."));
    var wrap = h("div", { class: "cc-people" });
    d.quotes.forEach(function (q) {
      var v = h("input", { type: "number", min: "0", step: "1", value: q.value_sar == null ? "" : q.value_sar, placeholder: "Quote, SAR", "aria-label": "Quote value in SAR" });
      var ap = h("input", { type: "number", min: "0", step: "1", value: q.approved_sar == null ? "" : q.approved_sar, placeholder: "Approved, SAR", "aria-label": "Approved value in SAR" });
      var msg = h("span", { class: "cc-msg", role: "status" });
      var sv = h("button", { class: "hc-btn hc-btn--sm hc-btn--line", type: "button" }, "Save");
      sv.addEventListener("click", function () {
        sv.disabled = true;
        api("POST", "/api/crm/quote", { id: q.id, value_sar: v.value, approved_sar: ap.value }).then(function (r) {
          sv.disabled = false;
          if (r.s === 200) { toast(0, "Quote saved."); crmReload(); api("GET", "/api/crm/company?k=" + encodeURIComponent(c.key)).then(function (x) { if (x.s === 200) { CRM.det = x.b; renderSection(); } }); }
          else msg.textContent = (r.b && r.b.message) || "Could not save.";
        });
      });
      wrap.appendChild(h("div", { class: "cc-quote" },
        h("div", { class: "cc-q__what" }, h("b", null, (q.selection || "A selection") + (q.creators ? ", " + plural(q.creators, "creator") : "")),
          h("small", null, "Asked " + day(q.at) + (q.who ? " by " + q.who : "") + " · " + (q.handled ? "answered" : "waiting for an answer") + (q.set_by ? " · figures by " + q.set_by : ""))),
        h("div", { class: "cc-quote__f" }, v, ap, sv, msg)));
    });
    return wrap;
  }
  function notesTab(c) {
    var d = CRM.det;
    if (!d) return h("p", { class: "hb-none", role: "status" }, "Loading…");
    if (d === "error") return h("p", { class: "hb-none" }, "The notes could not be loaded.");
    var text = h("textarea", { maxlength: "2000", placeholder: "What happened, what was agreed, what to remember", "aria-label": "Note", rows: "3" });
    var kind = h("select", { class: "cc-select", "aria-label": "Type" }, h("option", { value: "note" }, "Note"), h("option", { value: "call" }, "Call"));
    var msg = h("span", { class: "cc-msg", role: "status" });
    var add_ = h("button", { class: "hc-btn hc-btn--sm", type: "button" }, "Add note");
    add_.addEventListener("click", function () {
      add_.disabled = true;
      api("POST", "/api/crm/note", { key: c.key, text: text.value, kind: kind.value }).then(function (r) {
        add_.disabled = false;
        if (r.s === 200) { d.notes = r.b.notes; text.value = ""; renderSection(); } else msg.textContent = (r.b && r.b.message) || "Could not add it.";
      });
    });
    var list = h("ul", { class: "cc-notes" });
    d.notes.forEach(function (n) { list.appendChild(h("li", null, n.text, h("small", null, [n.author, n.kind === "call" ? "call" : "note", day(n.at)].filter(Boolean).join(" · ")))); });
    return h("div", null, h("div", { class: "cc-noteform" }, text, h("div", { class: "cc-noteform__go" }, kind, add_, msg)),
      d.notes.length ? list : h("p", { class: "hb-none" }, "No notes yet."),
      h("p", { class: "cc-private" }, icon("lock"), "Team only. Clients never see notes, money or phone numbers."));
  }
  function renderCompanyPage(p) {
    if (!CRM.data) { add(p, h("p", { class: "hc-sr", role: "status" }, "Loading the company")); crmLoad(); return; }
    var c = CRM.data.rows.filter(function (x) { return x.key === CRM.page; })[0];
    if (!c) { CRM.page = null; renderSection(); return; }
    if (CRM.det && CRM.det.row && CRM.det.row.key === c.key) c = CRM.det.row;
    add(p, h("nav", { class: "cc-crumb", "aria-label": "Breadcrumb" }, h("a", { href: "#companies", onclick: function (e) { e.preventDefault(); closeCompany(); } }, "Companies"), icon("arrow"), h("span", null, c.name)));
    add(p, companyHeader(c));
    var det = HUB.detail[c.key], nq = CRM.det && CRM.det.quotes ? CRM.det.quotes.length : null, nn = CRM.det && CRM.det.notes ? CRM.det.notes.length : null;
    var tabs = h("div", { class: "cc-tabs", role: "tablist", "aria-label": "Company" });
    [["people", "People", c.waiting ? c.waiting + " waiting" : (det && det.people ? det.people.length : null), !!c.waiting], ["work", "Work", c.selections + c.campaigns || null],
     ["quotes", "Quotes", nq], ["notes", "Notes", nn]].forEach(function (t) {
      tabs.appendChild(h("button", { class: "cc-tab", role: "tab", type: "button", "aria-selected": CRM.tab === t[0] ? "true" : "false",
        onclick: function () { CRM.tab = t[0]; renderSection(); } }, t[1], t[2] != null ? h("em", { class: t[3] ? "hot" : "" }, String(t[2])) : null));
    });
    add(p, tabs);
    var body = CRM.tab === "work" ? workTab(c) : CRM.tab === "quotes" ? quotesTab(c) : CRM.tab === "notes" ? notesTab(c) : peopleTab(c);
    var credits = det && det.people ? det.people.reduce(function (n, x) { return n + (x.credits || 0); }, 0) : null;
    var rail = h("aside", { class: "cc-rail", "aria-label": "At a glance" }, h("section", { class: "hc-panel" }, h("h3", null, "At a glance"),
      h("dl", { class: "cc-dl" }, h("dt", null, "Selections"), h("dd", null, String(c.selections)), h("dt", null, "Campaigns"), h("dd", null, c.campaigns + (c.live ? " · " + c.live + " live" : "")),
        h("dt", null, "Open quotes"), h("dd", null, c.open_n ? (c.open_sar ? big(c.open_sar) + " SAR" : c.open_n + " unpriced") : "None"),
        h("dt", null, "Approved, 12 months"), h("dd", null, c.approved_sar ? big(c.approved_sar) + " SAR" : "—"),
        h("dt", null, "Credits left"), h("dd", null, credits == null ? "…" : String(credits)))));
    add(p, h("div", { class: "cc-split" }, h("section", { "aria-label": "Company details" }, body), rail));
    add(p, h("p", { class: "hb-say", id: "hb-say", role: "status" })); hubSayAgain();
  }


  /* ------------------------------------------- Push composer (item 209 slice c) */
  // A side sheet on a company page (or a person's menu): who gets it, the message, when, how many it will reach and a phone
  // preview. The same queue as the admin's App & alerts, so it lands in each person's bell too; 10 people or more ask for the
  // emailed code first. Everyone at a company, the people on a campaign, or chosen people; "every client" stays in the admin.
  var COMPOSE = null;
  function openCompose(key, name, preset) {
    if (COMPOSE) return;
    COMPOSE = { key: key, name: name, ctx: null, type: preset && preset.people ? "people" : "company", camps: [], people: preset && preset.people ? preset.people.slice() : [],
                title: "", body: "", url: "/account/", when: "now", at: "", reach: null, msg: "", busy: false, timer: null };
    var wrap = h("div", { class: "cc-sheet-wrap", role: "presentation" });
    document.body.appendChild(wrap); document.body.classList.add("cc-sheet-open");
    COMPOSE.wrap = wrap;
    document.addEventListener("keydown", composeKey);
    paintCompose();
    api("GET", "/api/compose/context?k=" + encodeURIComponent(key)).then(function (r) {
      if (!COMPOSE) return;
      if (r.s !== 200) { COMPOSE.msg = "This company can't be pushed to from here."; paintCompose(); return; }
      COMPOSE.ctx = r.b; paintCompose(); composeReach();
    });
  }
  function composeKey(e) { if (e.key === "Escape") closeCompose(); }
  function closeCompose() {
    if (!COMPOSE) return;
    document.removeEventListener("keydown", composeKey);
    COMPOSE.wrap.remove(); COMPOSE = null; document.body.classList.remove("cc-sheet-open");
  }
  function composeAud() {
    var C = COMPOSE;
    return C.type === "company" ? { type: "company", key: C.key } : C.type === "campaign" ? { type: "campaign", campaigns: C.camps } : { type: "people", people: C.people };
  }
  function composeReach() {
    var C = COMPOSE; if (!C) return;
    clearTimeout(C.timer);
    C.timer = setTimeout(function () {
      if (C.type === "campaign" && !C.camps.length || C.type === "people" && !C.people.length) { C.reach = null; paintReach(); return; }
      api("POST", "/api/compose/reach", { aud: composeAud() }).then(function (r) { if (COMPOSE !== C) return; C.reach = r.s === 200 ? r.b : null; paintReach(); });
    }, 180);
  }
  function paintReach() {
    var C = COMPOSE, el = C && C.wrap.querySelector(".cc-reach"); if (!el) return;
    var r = C.reach; el.textContent = "";
    if (!r) { el.appendChild(h("span", null, "Pick who gets it.")); return; }
    el.appendChild(h("b", null, r.push_people + " of " + r.people));
    el.appendChild(h("span", null, r.push_people === r.people ? "will get a phone alert." : "will get a phone alert; the rest see it in the bell."));
    if (r.no_phone_n) el.appendChild(h("small", null, r.no_phone.join(", ") + (r.no_phone_n > r.no_phone.length ? " and " + (r.no_phone_n - r.no_phone.length) + " more" : "") + " have alerts off."));
    if (r.needs_code) el.appendChild(h("small", null, "This is a big push, so you'll confirm with an emailed code."));
  }
  function composeSend(test) {
    var C = COMPOSE; if (!C || C.busy) return;
    var when = null;
    if (!test && C.when === "later") {
      when = C.at ? Math.floor(new Date(C.at).getTime() / 1000) : 0;
      if (!when) { C.msg = "Pick the date and time to send."; paintCompose(); return; }
    }
    function go() {
      C.busy = true; C.msg = ""; paintCompose();
      return api("POST", "/api/compose/send", { aud: composeAud(), title: C.title, body: C.body, url: C.url, send_at: when, test: !!test }).then(function (r) {
        C.busy = false;
        if (r.s === 403 && r.b && r.b.reason === "stepup") {
          return stepUp({ title: "Send this push?", why: "A push to " + (C.reach ? C.reach.people : "many") + " people can't be taken back.", what: C.title || "Push", sub: C.name, ok: "Send push" }).then(function (ok) {
            if (ok) return go(); paintCompose();
          });
        }
        if (r.s === 200) {
          toast(0, r.b.message || "Sent.");
          if (test) { C.msg = r.b.message; paintCompose(); } else closeCompose();
        } else { C.msg = (r.b && r.b.message) || "That didn't send. Try again."; paintCompose(); }
      });
    }
    return go();
  }
  function paintCompose() {
    var C = COMPOSE; if (!C) return;
    var ctx = C.ctx, wrap = C.wrap;
    var keep = wrap.querySelector(".cc-sheet"), top = keep ? keep.scrollTop : 0;
    var aud = h("div", { class: "cc-aud", role: "radiogroup", "aria-label": "Who gets it" });
    function opt(type, title, sub, extra) {
      var rd = h("input", { type: "radio", name: "aud", checked: C.type === type ? "" : null, onchange: function () { C.type = type; paintCompose(); composeReach(); } });
      var lab = h("label", null, rd, h("div", null, h("b", null, title), h("small", null, sub)), h("span"));
      var box = h("div", null, lab);
      if (C.type === type && extra) box.appendChild(extra);
      return box;
    }
    if (ctx) {
      var camps = h("div", { class: "cc-aud__sub" });
      ctx.campaigns.forEach(function (k) {
        camps.appendChild(h("label", null, h("input", { type: "checkbox", checked: C.camps.indexOf(k.id) >= 0 ? "" : null,
          onchange: function () { C.camps = C.camps.indexOf(k.id) >= 0 ? C.camps.filter(function (x) { return x !== k.id; }) : C.camps.concat(k.id);
            if (C.camps.length === 1) { var kk = ctx.campaigns.filter(function (x) { return x.id === C.camps[0]; })[0]; C.url = "/campaign/dashboard/#t=" + kk.token; } else C.url = "/account/";
            composeReach(); paintCompose(); } }), k.name, h("span", { class: "cc-mute" }, k.status)));
      });
      if (!ctx.campaigns.length) camps.appendChild(h("p", { class: "cc-mute" }, "This company has no campaigns."));
      var ppl = h("div", { class: "cc-aud__sub" });
      ctx.people.forEach(function (u) {
        ppl.appendChild(h("label", null, h("input", { type: "checkbox", checked: C.people.indexOf(u.id) >= 0 ? "" : null,
          onchange: function () { C.people = C.people.indexOf(u.id) >= 0 ? C.people.filter(function (x) { return x !== u.id; }) : C.people.concat(u.id); composeReach(); paintCompose(); } }),
          u.name, h("span", { class: "cc-mute" }, u.phone ? "phone alerts on" : "bell only")));
      });
      aud.appendChild(opt("company", "Everyone at " + ctx.name, plural(ctx.people.length, "active person", "active people")));
      aud.appendChild(opt("campaign", "People on a campaign", ctx.campaigns.length ? "Pick one or more campaigns" : "No campaigns yet", camps));
      aud.appendChild(opt("people", "Choose people", "Pick from this company", ppl));
      aud.appendChild(h("div", null, h("label", { class: "is-off" }, h("input", { type: "radio", disabled: "" }), h("div", null, h("b", null, "Every client"), h("small", null, "Admins only, from Control Centre · App & alerts")),
        h("span", { class: "cc-lockmark" }, icon("lock"), "Admin"))));
    } else aud.appendChild(h("p", { class: "ac-muted", role: "status" }, C.msg || "Loading…"));
    var title = h("input", { type: "text", maxlength: "60", value: C.title, placeholder: "What should they see first?", "aria-label": "Title" });
    var body = h("textarea", { maxlength: "180", "aria-label": "Message", placeholder: "One or two lines. No prices." }, C.body);
    var cnt = h("span", null, C.body.length + " / 180");
    title.addEventListener("input", function () { C.title = title.value; var t = C.wrap.querySelector(".cc-note b"); if (t) t.textContent = C.title || "Title"; });
    body.addEventListener("input", function () { C.body = body.value; cnt.textContent = C.body.length + " / 180"; var t = C.wrap.querySelector(".cc-note p"); if (t) t.textContent = C.body; });
    var opens = h("select", { "aria-label": "Opens" }, h("option", { value: "/account/" }, "My profile"));
    if (ctx) ctx.campaigns.forEach(function (k) { opens.appendChild(h("option", { value: "/campaign/dashboard/#t=" + k.token }, k.name + " dashboard")); });
    opens.value = C.url; opens.addEventListener("change", function () { C.url = opens.value; });
    var whenNow = h("button", { class: "cc-chip", type: "button", "aria-pressed": C.when === "now" ? "true" : "false", onclick: function () { C.when = "now"; paintCompose(); } }, "Now");
    var whenLater = h("button", { class: "cc-chip", type: "button", "aria-pressed": C.when === "later" ? "true" : "false", onclick: function () { C.when = "later"; paintCompose(); } }, icon("cal"), "Schedule");
    var at = C.when === "later" ? h("input", { type: "datetime-local", value: C.at, "aria-label": "Send at", onchange: function (e) { C.at = e.target.value; } }) : null;
    var sendB = h("button", { class: "hc-btn", type: "button", disabled: C.busy || !ctx || !C.title.trim() ? "" : null, onclick: function () { composeSend(false); } }, icon("bell"), C.busy ? "Sending…" : (C.when === "later" ? "Schedule push" : "Send push"));
    var testB = h("button", { class: "hc-btn hc-btn--line", type: "button", disabled: C.busy || !C.title.trim() ? "" : null, onclick: function () { composeSend(true); } }, "Send a test to my phone");
    title.addEventListener("input", function () { sendB.disabled = !C.title.trim() || C.busy || !ctx; testB.disabled = !C.title.trim() || C.busy; });
    var phone = h("div", { class: "cc-phone", "aria-label": "iPhone preview" }, h("div", { class: "cc-phone__time" }, "09:41"), h("div", { class: "cc-phone__date" }, new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })),
      h("div", { class: "cc-note" }, h("img", { src: ROOT + "assets/app/icon-192.png", alt: "" }), h("div", null, h("div", { class: "cc-note__top" }, h("span", null, "HELVi"), h("span", null, "now")),
        h("b", null, C.title || "Title"), h("p", null, C.body || "Message"))));
    var sheet = h("section", { class: "cc-sheet", role: "dialog", "aria-modal": "true", "aria-labelledby": "pu-h" },
      h("div", { class: "cc-sheet__hd" }, h("div", null, h("h2", { id: "pu-h" }, "Push to " + C.name), h("p", null, "A phone alert and a bell note. Clients only get pushes about their own work.")),
        h("button", { class: "cc-x", type: "button", "aria-label": "Close", onclick: closeCompose }, icon("x"))),
      h("div", { class: "cc-compose" },
        h("div", null, h("div", { class: "cc-field" }, h("span", null, "Who gets it"), aud),
          h("label", { class: "cc-field" }, h("span", null, "Title"), title),
          h("label", { class: "cc-field" }, h("span", null, "Message"), body, h("div", { class: "cc-field__count" }, h("span", null, "Never prices or costs."), cnt)),
          h("label", { class: "cc-field" }, h("span", null, "Opens"), opens),
          h("div", { class: "cc-field" }, h("span", null, "When"), h("div", { class: "cc-when" }, whenNow, whenLater), at),
          h("div", { class: "cc-reach", "aria-live": "polite" })),
        h("div", null, phone, h("p", { class: "cc-phone__cap" }, "Preview on iPhone. Android looks similar."))),
      h("div", { class: "cc-sheet__go" }, sendB, testB, h("small", null, icon("clock"), "Quiet hours 23:00–08:00 Riyadh hold it until morning."), C.msg ? h("span", { class: "cc-msg", role: "status" }, C.msg) : null));
    wrap.textContent = "";
    wrap.appendChild(h("div", { class: "cc-scrim", onclick: closeCompose }));
    wrap.appendChild(sheet);
    sheet.scrollTop = top; paintReach();
    var f = C.title ? null : title; if (f && !C._focused) { C._focused = true; f.focus(); }
  }

  function renderCompanies(p) {
    if (!DATA.hub) { renderOverview(p); return; }
    if (CRM.page && HUB.view === "companies") { renderCompanyPage(p); return; }
    add(p, head("Companies", "Every company, its people, and their campaigns with their selections. Open anything as the client sees it, assign it to a client, share it, or hand it to an account manager."));
    add(p, hubViewBar());
    if (HUB.view === "campaigns") { renderAllCampaigns(p); return; }
    if (HUB.err) { add(p, h("div", { class: "hc-empty" }, h("b", null, "Companies"), h("p", null, HUB.err))); return; }
    if (!HUB.list) {
      add(p, h("div", { class: "kc-skel", "aria-hidden": "true" }, h("i"), h("i"), h("i")));
      add(p, h("p", { class: "hc-sr", role: "status" }, "Loading the companies"));
      hubLoad();
      return;
    }
    renderCrm(p);
    // Work that is not filed under a client (a KAM's handed items, the team's, loose access codes) keeps its own list.
    var other = HUB.list.filter(function (c) { return c.key === "handed" || c.key === "unassigned" || c.key === "team"; });
    if (other.length) {
      var list = h("ul", { class: "hb-list" });
      other.forEach(function (c) { list.appendChild(companyBlock(c)); });
      add(p, h("div", { class: "hc-sechd" }, h("h2", { class: "hc-h2" }, "Not filed under a client")));
      add(p, list);
    }
  }

  /* ---------------------------------------------------------------- routing */

  var RENDER = { overview: renderOverview, selections: renderSelections, analyses: renderAnalyses, campaigns: renderCampaigns,
                 briefs: renderBriefs, notifications: renderNotifications, credits: renderCredits, account: renderAccount,
                 clients: function (p) { if (DATA.is_kam) renderClients(p); else renderOverview(p); },
                 companies: renderCompanies,
                 // ROI Calculator: drawn by assets/js/connect.js (tier mix, save to a selection, estimate vs actual).
                 roi: function (p) { if (HV().roiPage) HV().roiPage(p); else setTimeout(function () { if (SECTION === "roi") renderSection(); }, 200); } };
  var TITLES = { overview: "My profile", selections: "Selections", analyses: "Analyses", campaigns: "Campaigns", briefs: "Briefs",
                 roi: "ROI Calculator", notifications: "Notifications", credits: "Credits", account: "Account", clients: "My clients", companies: "Companies" };
  function renderSection() {
    var p = $("hc-body");
    p.textContent = "";
    RENDER[SECTION](p);
    document.title = TITLES[SECTION] + " — HELVi Connect";
    var want = store("ac-focus");
    if (want) {
      try { sessionStorage.removeItem("ac-focus"); } catch (e) { /* blocked */ }
      var el = document.querySelector('[data-key="' + want + '"]');
      if (el) {
        el.scrollIntoView({ block: "center" });
        var inp = el.matches("input, select") ? el : el.querySelector("input, select");
        if (inp) inp.focus({ preventScroll: true });
      }
    }
  }
  function focusField(key) { store("ac-focus", key); if (location.hash === "#account") renderSection(); else location.hash = "#account"; }
  function route(scroll) {
    if (!DATA) return;
    var want = (location.hash || "#overview").slice(1).split("/")[0];
    // Old links: #home and #settings became Overview and Account.
    want = { home: "overview", settings: "account" }[want] || want;
    if (want === "roi" && ROI_LOCKED) want = "overview";
    SECTION = RENDER[want] ? want : "overview";
    renderSide();
    renderSection();
    if (scroll) { window.scrollTo(0, 0); $("hc-body").focus({ preventScroll: true }); }
  }
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("[data-focus]");
    if (a && a.tagName === "A") { store("ac-focus", a.getAttribute("data-focus")); if (location.hash === a.getAttribute("href")) { e.preventDefault(); renderSection(); } }
  });

  function closed(title, line) {
    $("ac-loading").hidden = true;
    var c = $("ac-closed");
    c.textContent = "";
    c.appendChild(h("b", null, title));
    c.appendChild(h("p", null, line));
    c.appendChild(h("a", { class: "hc-btn", href: ROOT }, "Go to the catalogue"));
    c.hidden = false;
  }
  function load() {
    return api("GET", "/api/account").then(function (r) {
      if (r.s === 401) { closed("Please sign in", "Sign in on the catalogue to see your profile."); return; }
      if (r.s === 403) { closed("Profiles are for signed-in clients", "You have guest access. Sign in with your work email for your own profile; your campaigns are in campaign tracking."); return; }
      if (!r.b.ok) { closed("Something went wrong", "Your profile couldn't be loaded. Please try again shortly."); return; }
      DATA = r.b;
      if (DATA.cc) DATA.cc.stepup_at = Date.now();      // the step-up window is counted from this answer
      $("ac-loading").hidden = true;
      $("hc-acc").hidden = false;
      // The bell and this page stay in step.
      var hv = window.hvPortal = window.hvPortal || {};
      hv.onUnread = function (n) {
        if (!DATA) return;
        DATA.notifications.unread = n;
        var b = document.querySelector('[data-count="notifications"]');
        if (b) { b.textContent = String(n); b.hidden = !n; }
      };
      hv.onReadAll = function () { if (DATA) { DATA.notifications.items.forEach(function (x) { x.unread = false; }); if (SECTION === "notifications" || SECTION === "overview") renderSection(); } };
      route(false);
      if (DATA.is_kam) loadClients();          // the side nav's count, and the page if it is open
      if (staffInbox()) loadInbox();           // the Analyses count: requests waiting for HelloVoice (item 195)
      if (DATA.cc) loadNeeds();                // the Overview count: what is waiting on the team (item 209)
    });
  }

  window.addEventListener("hashchange", function () { route(true); });
  load();
})();
