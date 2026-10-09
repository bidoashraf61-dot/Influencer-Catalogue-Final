/* HELVY Connect: the client's profile (/account/), drawn from /api/account.
 *
 * Sections by hash: #overview (default), #selections, #analyses, #campaigns,
 * #briefs, #notifications, #credits, #account. A side nav on a desktop, a strip
 * of tabs on a phone.
 *
 * Overview leads with Helvy and ONE next step, then the status line, the latest
 * notifications, profile completion (each step priced in what its credits buy)
 * and the invite. Campaigns keep the report's own scorebug.
 *
 * Everything from the server goes on the page with textContent, never HTML.
 * Icons, the notification row and Helvy's picture come from portal.js
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
    return Math.floor(n / chat) + " questions to Helvy";
  }
  var SIG = { good: "Strong", moderate: "Fair", low: "Low" };
  function sig(grade, label) { return h("span", { class: "ac-sig ac-sig--" + (grade || "none") }, label || SIG[grade] || "Too early"); }
  function stamp(v) { return h("span", { class: "ac-verdict ac-verdict--" + (v.grade || "none") }, v.label || "Getting started"); }

  /* -------------------------------------------------------------- side nav */

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
    if (key === "selections") return DATA.selections.length || null;
    if (key === "analyses") return pending().length || null;
    if (key === "campaigns") return DATA.insights.live_campaigns || null;
    if (key === "notifications") return DATA.notifications.unread || null;
    if (key === "credits") return DATA.credits != null ? DATA.credits : null;
    return null;
  }
  function renderSide() {
    var u = DATA.user, side = $("hc-side");
    side.textContent = "";
    side.appendChild(h("div", { class: "hc-me" }, face(u),
      h("div", null, h("b", null, u.name || u.email), h("small", null, [u.job_title, u.company].filter(Boolean).join(" · ") || u.email))));
    var nav = h("nav", { class: "hc-nav", "aria-label": "Your profile" });
    NAV.forEach(function (it) {
      if (it[0] === "hr") { nav.appendChild(h("hr")); return; }
      var n = countFor(it[0]);
      var a = h("a", { href: "#" + it[0], "aria-current": it[0] === SECTION ? "page" : null, "data-nav": it[0] }, icon(it[2]), it[1]);
      if (n != null) a.appendChild(h("span", { class: "n" + (it[0] === "notifications" ? " n--new" : ""), "data-count": it[0] }, String(n)));
      nav.appendChild(a);
    });
    side.appendChild(nav);
    var out = h("button", { class: "hc-more", type: "button", onclick: signOut }, icon("out"), "Sign out");
    // The 3-minute tour, replayable any time (HELVY Connect phase C).
    var tourB = h("button", { class: "hc-more", type: "button", onclick: function () { if (HV().tour) HV().tour(); } }, icon("help"), "Take the tour");
    side.appendChild(h("div", { class: "hc-out" }, tourB, out));
    var cur = nav.querySelector('[aria-current="page"]');
    if (cur && window.matchMedia("(max-width: 1100px)").matches) cur.scrollIntoView({ block: "nearest", inline: "center" });
  }
  function signOut() { (function () { try { sessionStorage.removeItem("hv-roster"); } catch (e) { /* blocked */ } })(), api("POST", "/api/auth/logout", {}).then(function () { location.href = ROOT; }); }

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
    t.appendChild(h("span", { class: "hc-reward" }, "+" + n));
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
    var p = h("p", null, nx.lead, h("b", null, nx.strong), nx.tail);
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
    // Helvy's idle loop (transparent, waist-up); the still when motion is reduced or refused.
    var img = HV().clip ? HV().clip("idle", "hc-greet__clip") : h("img", { class: "hv-clip", src: HV().helvy || ROOT + "assets/brand/helvy.webp?v=c2", alt: "", width: "148", height: "148" });
    return h("section", { class: "hc-greet", "aria-label": "Helvy's next step for you" },
      h("div", { class: "hc-greet__helvy" }, img),
      h("div", { class: "hc-greet__body" }, hi,
        h("div", { class: "hc-bubble" }, h("div", { class: "hc-bubble__who" }, h("b", null, "Helvy"), " · your next step"), p, go)));
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
      cell("Credits left", [String(DATA.credits), monthly && DATA.credits <= monthly ? h("small", null, "of " + monthly) : null],
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
  var STEP_WHY = { brands: "Helvy matches creators to them", industry_markets: "your briefs start filled in" };
  var STEP_FIELD = { photo: "photo", job_title: "job_title", phone: "phone", logo: "logo", brands: "brands", industry_markets: "industry" };
  function ring(pct) {
    var r = 58, c = 2 * Math.PI * r;
    var svg = '<svg viewBox="0 0 136 136" aria-hidden="true"><circle cx="68" cy="68" r="' + r + '" fill="none" stroke="#efede8" stroke-width="12"/>' +
      '<circle cx="68" cy="68" r="' + r + '" fill="none" stroke="#121212" stroke-width="12" stroke-linecap="round" stroke-dasharray="' + c.toFixed(1) +
      '" stroke-dashoffset="' + (c * (1 - pct / 100)).toFixed(1) + '"/></svg>';
    return h("div", { class: "hc-ring", role: "img", "aria-label": pct + "% of your profile is complete" },
      h("span", { html: svg }), h("div", { class: "hc-ring__in" }, h("b", null, pct + "%"), h("small", null, "Complete")));
  }
  function stepRow(s) {
    var b = h("button", { class: "hc-step", type: "button", "data-focus": STEP_FIELD[s.key],
      onclick: function () { focusField(STEP_FIELD[s.key]); } },
      h("span", { class: "hc-step__ic" }, icon(STEP_IC[s.key] || "plus")),
      h("span", null, h("b", null, s.label), h("small", null, h("em", null, "= " + buys(s.credits)), STEP_WHY[s.key] ? " · " + STEP_WHY[s.key] : " with Helvy")),
      h("span", { class: "hc-reward" }, "+" + s.credits));
    return h("li", null, b);
  }
  function finish() {
    var c = DATA.completion;
    var open = c.steps.filter(function (s) { return !s.paid; });
    var left = c.steps.filter(function (s) { return !s.done; }).length;
    var lead = c.waiting
      ? h("p", { class: "hc-done__lead" }, h("mark", null, plural(c.waiting, "credit") + " waiting"),
          left ? " for " + plural(left, "quick detail") + ". Helvy uses them to pre-fill your briefs." : ". Save your profile to collect them.")
      : h("p", { class: "hc-done__lead" }, "All profile credits earned. Helvy uses your details to pre-fill your briefs.");
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
  function renderOverview(p) {
    add(p, greet());
    add(p, scoreline());
    add(p, h("div", { class: "hc-cols" }, latest(), finish()));
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
  function renderSelections(p) {
    add(p, head("Selections", "Approve the creators you want and reject the ones you don't. Your account manager sees every change and quotes the approved list.",
      h("a", { class: "hc-btn hc-btn--line hc-btn--sm", href: ROOT + "#cat-roster" }, "Browse creators")));
    if (!DATA.selections.length) {
      add(p, h("div", { class: "hc-empty" }, h("b", null, "No selections yet"),
        h("p", null, "Pick creators in the catalogue, or let Helvy build a scored shortlist from a short brief."),
        h("a", { class: "hc-btn", href: ROOT }, "Find creators")));
      return;
    }
    var list = h("ul", { class: "hc-list" });
    DATA.selections.forEach(function (s) {
      var c = s.counts;
      list.appendChild(h("li", null, h("a", { class: "hc-row", href: ROOT + "selection/#s=" + encodeURIComponent(s.token) },
        h("div", null, h("span", { class: "hc-row__name" }, s.name),
          h("div", { class: "hc-row__meta" },
            h("span", null, plural(c.creators, "creator") + (c.doctors ? " · " + plural(c.doctors, "doctor") : "")),
            statusSigs(c), h("span", null, (s.owner ? s.owner + "'s · " : "") + "updated " + ago(s.updated_at)))),
        h("span", { class: "hc-row__go" }, s.mine && c.review ? "Review" : "Open", " ", icon("arrow")))));
    });
    add(p, list);
  }

  /* -------------------------------------------------------------- analyses */

  function renderAnalyses(p) {
    add(p, head("Analyses", "A full analysis opens a creator's audience, growth, fake-follower check, brand history, best posts and a pricing benchmark. It is free for any creator in one of your selections and ready within 1 working day."));
    if (!DATA.analyses.length) {
      add(p, h("div", { class: "hc-empty" }, h("b", null, "No analyses requested yet"),
        h("p", null, "Open a creator from one of your selections and press Request full analysis. Helvy rings your bell when it opens."),
        h("a", { class: "hc-btn", href: "#selections" }, "Go to my selections")));
      return;
    }
    var list = h("ul", { class: "hc-list" });
    DATA.analyses.forEach(function (a) {
      var open = a.state === "unlocked";
      list.appendChild(h("li", null, h("a", { class: "hc-row", href: ROOT + "creator/#c=" + encodeURIComponent(a.code) },
        h("div", null, h("span", { class: "hc-row__name" }, a.name),
          h("div", { class: "hc-row__meta" }, h("span", null, a.code),
            open ? h("span", { class: "hc-sig hc-sig--ok" }, "Unlocked " + dm(a.at))
                 : h("span", { class: "hc-sig hc-sig--wait" }, "Requested · ready by " + shortDay(a.ready_by)))),
        h("span", { class: "hc-row__go" }, open ? "View full analysis" : "See what's free now", " ", icon("arrow")))));
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
    var u = DATA.user, p = pace(c);
    var brands = h("div", { class: "ac-bug__brands" });
    if (u.logo) { brands.appendChild(h("img", { src: imgUrl("logo", u.logo), alt: u.company || "" })); brands.appendChild(h("span", { class: "ac-bug__x", "aria-hidden": "true" }, "×")); }
    brands.appendChild(h("img", { class: "ac-bug__hv", src: ROOT + "assets/brand/logo.png", alt: "HelloVoice" }));
    return h("section", { class: "ac-bug", "aria-label": c.name },
      h("div", { class: "ac-bug__top" }, brands, h("span", { class: "ac-live" }, "Live"),
        h("span", { class: "ac-muted" }, [day(c.starts_at), day(c.ends_at)].filter(Boolean).join(" – "))),
      h("div", { class: "ac-bug__row" }, h("h2", { class: "ac-bug__title" }, c.name), stamp(c.verdict)),
      scorelineDl([
        ["Views", big(c.views), null, null],
        ["Reach", big(c.reach), null, h("span", { class: "ac-muted" }, "people reached")],
        ["Engagement", c.er != null ? c.er.toFixed(1) : "—", c.er != null ? "%" : null, c.er_grade ? sig(c.er_grade) : null],
        ["Posts live", String(c.delivered), c.planned ? "/" + c.planned : null, p ? sig(p.grade, p.label) : null]
      ]),
      h("div", { class: "ac-bug__go" }, h("a", { class: "hc-btn", href: ROOT + "campaign/#t=" + encodeURIComponent(c.token) }, "Open the full report")));
  }
  function campaignCard(c) {
    var p = pace(c);
    return h("a", { class: "ac-item ac-item--camp", href: ROOT + "campaign/#t=" + encodeURIComponent(c.token) },
      h("div", { class: "ac-item__top" },
        c.status === "live" ? h("span", { class: "ac-live" }, "Live") : h("span", { class: "ac-status" }, c.status === "ended" ? "Ended" : c.status),
        h("span", { class: "ac-item__verdict ac-item__verdict--" + (c.verdict.grade || "none") }, c.verdict.label || "Getting started")),
      h("b", { class: "ac-item__name" }, c.name),
      h("span", { class: "ac-muted" }, [day(c.starts_at), day(c.ends_at)].filter(Boolean).join(" – ")),
      h("div", { class: "ac-item__nums" },
        h("span", null, h("b", null, big(c.views)), " views"),
        h("span", null, h("b", null, c.delivered + (c.planned ? "/" + c.planned : "")), " posts"),
        p && c.status === "live" ? sig(p.grade, p.label) : null),
      h("span", { class: "ac-item__go" }, "Open report →"));
  }
  function renderCampaigns(p) {
    add(p, head("Campaigns", "Every campaign HelloVoice runs for your team, with its live report. Numbers refresh every 24 hours.",
      h("a", { class: "hc-btn hc-btn--ink hc-btn--sm", href: ROOT + "campaign/dashboard/" }, icon("chart"), " Campaign tracking")));
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
    add(p, head("Briefs", "The campaign briefs you gave Helvy. Each one scores creators and can be opened as a selection."));
    if (!DATA.briefs.length) {
      add(p, h("div", { class: "hc-empty" }, h("b", null, "No briefs yet"),
        h("p", null, "Answer six quick questions about a campaign and Helvy ranks the roster against them. Your industry and markets fill in for you."),
        h("a", { class: "hc-btn", href: ROOT }, "Start a brief")));
      return;
    }
    var list = h("ul", { class: "hc-list" });
    DATA.briefs.forEach(function (b) {
      var inner = [h("div", null, h("span", { class: "hc-row__name" }, b.selection_name || (b.objective ? b.objective + " brief" : "Brief")),
        h("div", { class: "hc-row__meta" }, h("span", null, b.summary || ""), h("span", null, day(b.at)))),
        b.selection ? h("span", { class: "hc-row__go" }, "Open selection ", icon("arrow")) : null];
      list.appendChild(h("li", null, b.selection
        ? h("a", { class: "hc-row", href: ROOT + "selection/#s=" + encodeURIComponent(b.selection) }, inner)
        : h("div", { class: "hc-row" }, inner)));
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
      h("div", null, h("div", { class: "hc-bal__fig" }, String(bal), h("small", null, "Credits left")), meter,
        h("p", { class: "hc-bal__meta" }, monthly ? ["Tops up to ", h("b", null, monthly + " on " + dm(DATA.next_refill)), ". Credits you earn from your profile and invites come on top."]
                                                   : "Credits you earn from your profile and invites are added straight away.")),
      h("div", { class: "hc-bal__ask" }, reqBtn, ask, h("p", null, (kam ? kam + ", your account manager," : "Your HelloVoice team") + " tops you up. Usually the same working day."), msg)));
    var c = costs();
    var rows = [["AI shortlist", "Answer six questions about your campaign; Helvy ranks the roster against them.", c.brief],
                ["Find a replacement", "After you reject a creator: 3 similar creators that fit the same campaign.", c.replace],
                ["A typed question to Helvy", "Tapping Helvy's options is always free.", c.chat],
                ["Full creator analysis", "For any creator in one of your selections. Ready within 1 working day.", 0]];
    var tb = h("tbody");
    rows.forEach(function (r) {
      tb.appendChild(h("tr", null, h("td", null, h("b", null, r[0]), h("small", null, r[1])),
        h("td", null, r[2] ? h("span", { class: "hc-price__c" }, String(r[2]), h("small", null, r[2] === 1 ? "credit" : "credits")) : h("span", { class: "hc-price__free" }, "Free"))));
    });
    add(p, h("section", { "aria-labelledby": "hc-buy" }, h("h2", { class: "hc-h2", id: "hc-buy", style: "margin-bottom:14px" }, "What credits buy"),
      h("table", { class: "hc-price" }, h("thead", null, h("tr", null, h("th", null, "With Helvy"), h("th", null, "Cost"))), tb)));
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
        h("td", { class: l.delta > 0 ? "up" : null }, (l.delta > 0 ? "+" : "") + l.delta), h("td", null, String(l.balance))));
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
      h("div", { class: "ac-action" }, h("div", null, h("b", null, "Sign out"), h("p", { class: "ac-muted" }, "Sign out of HELVY Connect on this browser.")),
        h("button", { class: "ac-btn-line", type: "button", onclick: signOut }, "Sign out")));
  }
  function renderAccount(p) {
    add(p, head("Account", "Who you are and who you work with. A complete profile earns " + (DATA.completion.steps.reduce(function (s, x) { return s + x.credits; }, 0) + DATA.completion.bonus) + " credits, once."));
    add(p, h("section", { class: "hc-sec", "aria-labelledby": "hc-prof" }, h("h2", { class: "hc-h2", id: "hc-prof" }, "Profile"),
      imageField("photo", "Profile photo", "Shown in the menu and on your profile. A square crop is made for you."),
      imageField("logo", "Company logo", "Shown on your live campaign's scoreboard."),
      profileForm()));
    add(p, h("section", { class: "hc-sec", "aria-labelledby": "hc-brand" }, h("h2", { class: "hc-h2", id: "hc-brand" }, "Your brands and markets"),
      h("p", null, "Helvy uses these to pre-fill your briefs, so a new shortlist starts from your industry and market."), brandForm()));
    add(p, teamSection());
    add(p, privacySection());
  }

  /* ---------------------------------------------------------------- routing */

  var RENDER = { overview: renderOverview, selections: renderSelections, analyses: renderAnalyses, campaigns: renderCampaigns,
                 briefs: renderBriefs, notifications: renderNotifications, credits: renderCredits, account: renderAccount,
                 // ROI Calculator: drawn by assets/js/connect.js (tier mix, save to a selection, estimate vs actual).
                 roi: function (p) { if (HV().roiPage) HV().roiPage(p); else setTimeout(function () { if (SECTION === "roi") renderSection(); }, 200); } };
  var TITLES = { overview: "My profile", selections: "Selections", analyses: "Analyses", campaigns: "Campaigns", briefs: "Briefs",
                 roi: "ROI Calculator", notifications: "Notifications", credits: "Credits", account: "Account" };
  function renderSection() {
    var p = $("hc-body");
    p.textContent = "";
    RENDER[SECTION](p);
    document.title = TITLES[SECTION] + " — HELVY Connect";
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
      if (r.s === 403) { closed("Profiles are for signed-in clients", "You're using an access code. Your campaigns are in campaign tracking."); return; }
      if (!r.b.ok) { closed("Something went wrong", "Your profile couldn't be loaded. Please try again shortly."); return; }
      DATA = r.b;
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
    });
  }

  window.addEventListener("hashchange", function () { route(true); });
  load();
})();
