/* Competitor study through a client link (item 303, Bido 2026-11-03): "Who to book, already proven on your
 * competitors". Drawn on /market/ only when report-share.js says the page was opened with a study link
 * (window.HV_SHARED.kind === "study"); HelloVoice's Market Intelligence view (evidence.js) steps aside.
 *
 * One read of /api/evidence/map (the same payload the staff view uses, money already stripped for a link),
 * then: cover, ranked tiers (Proven / Strong / Worth a look), competitor scoreboard and best content type,
 * the 12 best posts, a posting timeline, the competitors' creators HelloVoice has not signed yet, and a
 * dossier per creator with notes and "Ask HelloVoice". Download PDF builds its own A4 pages (HVReport.pdf).
 *
 * Rules (Bido): brands are logos, posts are thumbnails, platforms are icons, every post links to the post.
 * Paid-boosted posts are shown, badged, and never counted. Everything is drawn with textContent. */
(function () {
  "use strict";
  var SH = window.HV_SHARED;
  if (!SH || SH.kind !== "study" || !document.getElementById("ev-market")) return;
  var API = (window.CATALOGUE_CONFIG || {}).api || "/admin";
  var HV = window.HVReport = window.HVReport || {};
  var m = /(?:^|[#&])s=([A-Za-z0-9_-]+)/.exec(location.hash || "");
  var SEL = m ? m[1] : "";
  if (!SEL) return;
  var ROOT = location.pathname.replace(/market\/(index\.html)?$/, "");
  document.documentElement.classList.add("ss-on");

  /* ---------- helpers ---------- */
  var SVG = "http://www.w3.org/2000/svg";
  var ICONS = {
    ig: '<rect x="3.5" y="3.5" width="17" height="17" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.2" cy="6.8" r=".6" fill="currentColor"/>',
    tt: '<path d="M14 4v10.5a3.5 3.5 0 11-3.5-3.5M14 4c.4 2.6 2.2 4.3 5 4.5"/>',
    reel: '<rect x="3.5" y="3.5" width="17" height="17" rx="4"/><path d="M3.5 8.5h17M8 3.5l3 5M13.5 3.5l3 5M10 12v5l4.5-2.5z"/>',
    post: '<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><circle cx="9" cy="9" r="1.8"/><path d="M20.5 15l-5-5-9.5 10"/>',
    story: '<circle cx="12" cy="12" r="8.5" stroke-dasharray="3 2.4"/><path d="M10 9v6l5-3z"/>',
    play: '<path d="M7 4.5v15l12.5-7.5z"/>',
    send: '<path d="M4 12l16-8-6 16-2.5-6.5L4 12z"/>', ok: '<path d="M5 12.5l4.5 4.5L19 7.5"/>', x: '<path d="M6 6l12 12M18 6L6 18"/>',
    lock: '<rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8 10.5V8a4 4 0 018 0v2.5"/>',
    steth: '<path d="M6 3.5v5a4 4 0 008 0v-5M10 12.5v2a5 5 0 0010 0v-1"/><circle cx="20" cy="11.5" r="2"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    boost: '<path d="M12 3.5l2.4 5.2 5.6.6-4.2 3.8 1.2 5.5L12 15.8l-5 2.8 1.2-5.5L4 9.3l5.6-.6z"/>'
  };
  function icon(id, label) {
    var s = document.createElementNS(SVG, "svg");
    s.setAttribute("class", "ss-ic"); s.setAttribute("viewBox", "0 0 24 24");
    if (label) { s.setAttribute("role", "img"); s.setAttribute("aria-label", label); } else s.setAttribute("aria-hidden", "true");
    s.innerHTML = ICONS[id] || "";
    return s;
  }
  function el(t, c, txt) { var n = document.createElement(t); if (c) n.className = c; if (txt != null) n.textContent = txt; return n; }
  function med(a) { a = a.filter(function (x) { return typeof x === "number" && !isNaN(x); }).sort(function (x, y) { return x - y; }); var k = a.length >> 1; return a.length ? (a.length % 2 ? a[k] : (a[k - 1] + a[k]) / 2) : null; }
  function num(v) { if (v == null) return "—"; if (v >= 1e6) return (v / 1e6).toFixed(1).replace(/\.0$/, "") + "M"; if (v >= 1e4) return Math.round(v / 1e3) + "K"; if (v >= 1e3) return (v / 1e3).toFixed(1).replace(/\.0$/, "") + "K"; return String(Math.round(v)); }
  function pct(v) { return v == null ? "—" : (v * 100).toFixed(1) + "%"; }
  function safeUrl(u) { return /^https:\/\//.test(u || "") ? u : null; }
  function day(d) { var t = Date.parse(String(d || "").slice(0, 10)); return isNaN(t) ? null : t; }
  function fmtDate(d) { var t = day(d); return t == null ? "" : new Date(t).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }); }
  // "Layan" from "Layan Fahad", "Dr. Amal" from "Dr. Amal Derm", "@handle" when there is no name.
  function shortName(c) {
    var w = String(c.name || "").trim().split(/\s+/).filter(Boolean);
    if (!w.length) return "@" + c.handle;
    return /^dr\.?$/i.test(w[0]) && w[1] ? "Dr. " + w[1] : w[0];
  }
  function initials(n) { return String(n || "?").replace(/^dr\.?\s*/i, "").split(/\s+/).slice(0, 2).map(function (w) { return w.charAt(0); }).join("").toUpperCase() || "?"; }
  var PNAME = { instagram: "Instagram", tiktok: "TikTok" };
  function platIcons(list) {
    var w = el("span", "ss-plat");
    (list || []).forEach(function (p) { var s = el("span"); s.appendChild(icon(p === "tiktok" ? "tt" : "ig", PNAME[p] || p)); w.appendChild(s); });
    return w;
  }
  // A brand is its logo; the name only when HelloVoice has no approved logo for it yet (rule 1).
  var LOGO = {};
  function logo(name, big) {
    var s = el("span", "ss-logo" + (big ? " ss-logo--lg" : "")), u = LOGO[name];
    s.title = name || "";
    if (u) {
      var i = el("img"); i.src = API + u; i.alt = name || ""; i.decoding = "async";
      i.addEventListener("error", function () { s.className += " ss-logo--txt"; s.textContent = name || ""; });
      s.appendChild(i);
    }
    else { s.className += " ss-logo--txt"; s.textContent = name || ""; }
    return s;
  }
  // What a post is, from what was fetched (as evidence.js): story, TikTok video, Instagram reel or post.
  function kindOf(q) {
    var u = q.url || "";
    if (/\/stories\//.test(u)) return "story";
    if (q.platform === "tiktok" || /tiktok\.com/.test(u)) return "video";
    return /\/reel\//.test(u) || q.views ? "reel" : "post";
  }
  var KNAME = { reel: "Instagram reel", post: "Instagram post", video: "TikTok video", story: "Story" };
  var KPLURAL = { reel: "Instagram reels", post: "Instagram posts", video: "TikTok videos", story: "Stories" };
  var KICON = { reel: "reel", post: "post", video: "tt", story: "story" };
  function thumbSrc(id) { return API + "/api/evidence/thumb?s=" + encodeURIComponent(SEL) + "&p=" + encodeURIComponent(id) + "&r=" + encodeURIComponent(SH.token); }
  function api(method, path, body) {
    return fetch(API + path, { method: method, credentials: "include", cache: "no-store",
                               headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { st: r.status, b: b }; }); })
      .catch(function () { return { st: 0, b: {} }; });
  }

  /* ---------- state ---------- */
  var D = null, NOTES = {}, ASKED = {};
  var state = { comp: "all", plat: "all", kind: "all", ctype: "all", sort: "rank", open: {} };
  var TIER_CAP = 12;
  var BY_ENG = false;
  function measure(q) { return BY_ENG ? (q.likes == null ? null : (q.likes || 0) + (q.comments || 0)) : q.views; }
  var NOW = Date.now();

  // One creator through the current filters. Boosted posts are shown but never counted (Bido 2026-11-03).
  function view(c) {
    if (state.ctype !== "all" && c.type !== state.ctype) return null;
    var ps = (c.posts || []).filter(function (q) {
      return (state.comp === "all" || q.competitor === state.comp) && (state.plat === "all" || q.platform === state.plat)
        && (state.kind === "all" || kindOf(q) === state.kind);
    });
    if (!ps.length) return null;
    var org = ps.filter(function (q) { return !q.paid_boost; });
    var comps = {}; ps.forEach(function (q) { comps[q.competitor] = (comps[q.competitor] || 0) + 1; });
    var views = org.map(function (q) { return q.views; }).filter(function (v) { return typeof v === "number"; });
    var latest = null;
    ps.forEach(function (q) { var t = day(q.date); if (t != null && (latest == null || t > latest.t)) latest = { t: t, comp: q.competitor }; });
    var ago = latest ? Math.floor((NOW - latest.t) / 864e5) : null;
    return { c: c, posts: ps, organic: org, comps: comps, best: views.length ? Math.max.apply(null, views) : null,
             typical: med(org.map(measure)) || 0, er: med(org.map(function (q) { return q.er; })),
             recent: ago != null && ago >= 0 && ago <= 90 ? { comp: latest.comp, days: ago } : null };
  }
  function tiered(list) {
    var vals = list.map(function (v) { return v.typical; }).sort(function (a, b) { return b - a; });
    var q1 = vals[Math.max(0, Math.ceil(vals.length / 4) - 1)], q2 = vals[Math.max(0, Math.ceil(vals.length / 2) - 1)];
    list.forEach(function (v) { v.tier = v.typical > 0 && v.typical >= q1 && v.organic.length >= 2 ? 1 : v.typical > 0 && v.typical >= q2 ? 2 : 3; });
    return list;
  }
  function TIERS() {
    var u = BY_ENG ? "engagement (likes + comments)" : "views";
    return { 1: ["Proven", "Top quarter on " + u + ", with two or more competitor posts."], 2: ["Strong", "Top half on " + u + "."],
             3: ["Worth a look", "Worked with your competitors; smaller results or less to go on."] };
  }
  function unit() { return BY_ENG ? "engagements" : "views"; }
  function why(v) {
    var n = Object.keys(v.comps).length, k = v.posts.length;
    if (v.tier === 1) return k + " posts for " + (n > 1 ? n + " of your competitors" : "one competitor") + ", typically " + num(v.typical) + " " + unit() + " each.";
    if (v.tier === 2) return BY_ENG ? "Typically " + num(v.typical) + " engagements per competitor post." : "Best competitor post reached " + num(v.best) + " views.";
    return "Posted for a competitor " + (k > 1 ? k + " times" : "once") + "; smaller reach so far.";
  }
  function recentBadge(r) {
    var b = el("span", "ss-badge ss-badge--recent");
    b.appendChild(icon("clock")); b.appendChild(logo(r.comp)); b.appendChild(document.createTextNode(r.days + "d ago"));
    b.title = "Posted for " + r.comp + " " + r.days + " days ago: check exclusivity before booking";
    return b;
  }
  function allPosts() { var out = []; (D.creators || []).forEach(function (c) { (c.posts || []).forEach(function (q) { out.push({ q: q, c: c }); }); }); return out; }
  function photoEl(c, cls, large) {
    var u = c.photo_large || c.photo;          // the large photo everywhere: thumbs pixelate at card size
    var fb = el("span", cls || "ss-av", initials(c.name || c.handle));
    if (!u) return fb;
    var i = el("img"); i.src = u; i.alt = ""; i.loading = "lazy"; i.decoding = "async";
    i.addEventListener("error", function () { if (i.parentNode) i.parentNode.replaceChild(fb, i); });
    return i;
  }

  // One post as a linked thumbnail (rules 2 + 4).
  function thumb(q, who) {
    var u = safeUrl(q.url), a = el(u ? "a" : "div", "ss-thumb"), k = kindOf(q);
    if (u) { a.href = u; a.target = "_blank"; a.rel = "noopener noreferrer";
             a.setAttribute("aria-label", "Watch " + (who ? who + "’s " : "the ") + KNAME[k].toLowerCase() + " for " + q.competitor + ", " + num(q.views) + " views"); }
    var im = el("img"); im.src = thumbSrc(q.id); im.alt = ""; im.loading = "lazy"; im.decoding = "async";
    im.addEventListener("error", function () { im.remove(); a.classList.add("ss-thumb--none"); });
    a.appendChild(im);
    var top = el("span", "ss-thumb__top"); top.appendChild(platIcons([q.platform])); top.appendChild(logo(q.competitor)); a.appendChild(top);
    if (q.paid_boost) { var bb = el("span", "ss-badge ss-badge--boost"); bb.appendChild(icon("boost")); bb.appendChild(document.createTextNode("Likely boosted")); a.appendChild(bb); }
    var pl = el("span", "ss-thumb__play"); pl.appendChild(icon("play")); a.appendChild(pl);
    var bt = el("span", "ss-thumb__bt"); bt.appendChild(el("b", null, q.views != null ? num(q.views) : (q.likes != null ? num(q.likes) + " likes" : "")));
    if (who) { var w2 = el("span", "ss-thumb__who", who); w2.dir = "auto"; bt.appendChild(w2); }
    var t0 = day(q.date);
    bt.appendChild(el("span", "ss-thumb__meta", [q.er != null ? pct(q.er) + " eng." : "", t0 == null ? "" : new Date(t0).toLocaleDateString("en-GB", { month: "short", year: "numeric" })].filter(Boolean).join(" · ")));
    a.appendChild(bt);
    return a;
  }

  /* ---------- page ---------- */
  var root = el("div", "ss"); root.id = "ss";
  root.appendChild(el("p", "ss-load", "Loading the competitor study…"));
  function mount() { var mk = document.getElementById("ev-market"); mk.parentNode.insertBefore(root, mk); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();

  Promise.all([api("GET", "/api/evidence/map?s=" + encodeURIComponent(SEL)), api("GET", "/api/evidence/notes?s=" + encodeURIComponent(SEL))])
    .then(function (res) {
      var mp = res[0];
      if (mp.st !== 200 || !mp.b.map) {
        root.textContent = "";
        if (mp.st !== 401 && mp.st !== 410) root.appendChild(el("p", "ss-load", "This competitor study is not available. Ask your HelloVoice contact for a new link."));
        return;
      }
      D = mp.b.map;
      NOTES = (res[1].b && res[1].b.notes) || {};
      BY_ENG = D.rank_by === "interactions";
      LOGO = {}; (D.competitors || []).forEach(function (c) { if (c.logo) LOGO[c.name] = c.logo; });
      if (D.brand && D.brand_logo) LOGO[D.brand] = D.brand_logo;
      draw();
      if (typeof HV.markLoaded === "function") HV.markLoaded();
    });

  var refs = {};
  // The competitors studied, as logos (cover and PDF cover).
  function comps() {
    var w = el("div", "ss-comps"), row = el("div", "ss-comps__row");
    w.appendChild(el("span", "ss-comps__k", "Competitors studied"));
    (D.competitors || []).forEach(function (c) { row.appendChild(logo(c.name, true)); });
    w.appendChild(row); return w;
  }
  function draw() {
    root.textContent = "";
    // cover
    var hero = el("section", "ss-hero"); hero.setAttribute("aria-labelledby", "ss-h1");
    var tx = el("div", "ss-hero__txt"), br = el("div", "ss-brand");
    if (D.brand) br.appendChild(logo(D.brand, true));
    br.appendChild(el("span", null, "Competitor study · " + (D.objective || "Awareness")));
    tx.appendChild(br);
    var h1 = el("h1"); h1.id = "ss-h1";
    h1.appendChild(document.createTextNode("Who to book, ")); h1.appendChild(el("em", null, "already proven")); h1.appendChild(document.createTextNode(" on your competitors"));
    tx.appendChild(h1);
    // the cover is the detective alone (item 309) with the brands he studied: competitor logos only, no machines
    tx.appendChild(comps()); hero.appendChild(tx);
    var art = el("img", "ss-hero__art ss-hero__char");
    art.src = ROOT + "assets/brand/modules/helvi-intel-character-480.webp";
    art.srcset = ROOT + "assets/brand/modules/helvi-intel-character-480.webp 1x, " + ROOT + "assets/brand/modules/helvi-intel-character-960.webp 2x";
    art.width = 267; art.height = 480;
    art.alt = "Helvy the detective, magnifier in hand";
    hero.appendChild(art); root.appendChild(hero);
    requestAnimationFrame(function () { art.classList.add("in"); });
    // answer + facts
    var cs = D.creators || [], posts = 0, views = 0;
    cs.forEach(function (c) { (c.posts || []).forEach(function (q) { posts++; if (!q.paid_boost && q.views) views += q.views; }); });
    var f = el("div", "ss-facts");
    [[(D.competitors || []).length, "Competitors studied"], [cs.length, "Creators in your selection"], [posts, "Competitor posts found"], [num(views), "Views on those posts"]]
      .forEach(function (x) { var d = el("div"); d.appendChild(el("b", null, String(x[0]))); d.appendChild(el("span", null, x[1])); f.appendChild(d); });
    root.appendChild(f);
    // tabs + board (sticky only over the board)
    var wrap = el("div", "ss-boardwrap"), nav = el("nav", "ss-tabs-wrap"); nav.setAttribute("aria-label", "Competitors and filters");
    refs.tabs = el("div", "ss-tabs"); refs.tabs.setAttribute("role", "tablist"); nav.appendChild(refs.tabs);
    var tools = el("div", "ss-tools");
    refs.plat = seg("Platform", [["all", "All"], ["instagram", null, "ig", "Instagram"], ["tiktok", null, "tt", "TikTok"]], "plat");
    var kinds = {}; allPosts().forEach(function (x) { kinds[kindOf(x.q)] = 1; });
    refs.kind = seg("Content type", [["all", "All content"]].concat(["reel", "post", "video", "story"].filter(function (k) { return kinds[k]; })
      .map(function (k) { return [k, { reel: "Reels", post: "Posts", video: "Videos", story: "Stories" }[k], KICON[k]]; })), "kind");
    var hasHcp = cs.some(function (c) { return c.type === "hcp"; });
    tools.appendChild(refs.plat); tools.appendChild(refs.kind);
    if (hasHcp) tools.appendChild(seg("Creator type", [["all", "Everyone"], ["influencer", "Creators"], ["hcp", "Doctors", "steth"]], "ctype"));
    var lab = el("label", "ss-sort", "Sort by "), sel = el("select");
    [["rank", "Best results"], ["er", "Engagement"], ["posts", "Most competitor posts"]].forEach(function (o) { var op = el("option", null, o[1]); op.value = o[0]; sel.appendChild(op); });
    sel.addEventListener("change", function () { state.sort = sel.value; drawBoard(true); });
    lab.appendChild(sel); tools.appendChild(lab); nav.appendChild(tools);
    wrap.appendChild(nav);
    refs.board = el("main", "ss-board"); refs.board.setAttribute("aria-live", "polite"); wrap.appendChild(refs.board);
    root.appendChild(wrap);
    drawTabs(); drawBoard(true);
    // insights
    root.appendChild(sectionScore());
    var w = wallSection(); if (w) root.appendChild(w);
    var t = timelineSection(); if (t) root.appendChild(t);
    if ((D.outside || []).length) root.appendChild(gapsSection());
    root.appendChild(el("div", "ss-end"));
  }
  function seg(label, opts, key) {
    var g = el("div", "ss-seg"); g.setAttribute("role", "group"); g.setAttribute("aria-label", label);
    function paint() {
      g.textContent = "";
      opts.forEach(function (o) {
        var b = el("button"); b.type = "button"; b.setAttribute("aria-pressed", String(state[key] === o[0]));
        if (o[2]) b.appendChild(icon(o[2], o[1] ? null : o[3]));
        if (o[1]) b.appendChild(document.createTextNode(o[1])); else b.setAttribute("aria-label", o[3]);
        b.addEventListener("click", function () { state[key] = o[0]; state.open = {}; paint(); drawBoard(true); });
        g.appendChild(b);
      });
    }
    paint();
    return g;
  }
  function drawTabs() {
    var t = refs.tabs; t.textContent = "";
    [{ name: "all" }].concat(D.competitors || []).forEach(function (c) {
      var n = (D.creators || []).filter(function (x) { return c.name === "all" || (x.posts || []).some(function (q) { return q.competitor === c.name; }); }).length;
      var b = el("button", "ss-tab"); b.type = "button"; b.setAttribute("role", "tab"); b.setAttribute("aria-selected", String(state.comp === c.name));
      if (c.name === "all") {
        b.appendChild(el("span", "ss-tab__all", "All"));
        var tx = el("span", "ss-tab__t"); tx.appendChild(el("b", null, "All competitors")); tx.appendChild(el("small", null, n + " creators")); b.appendChild(tx);
      } else { b.appendChild(logo(c.name)); b.appendChild(el("small", null, n + (n === 1 ? " creator" : " creators"))); b.setAttribute("aria-label", c.name + ", " + n + " creators"); }
      b.addEventListener("click", function () { state.comp = c.name; state.open = {}; drawTabs(); drawBoard(true); });
      t.appendChild(b);
    });
  }
  function drawBoard(deal) {
    var b = refs.board; b.textContent = "";
    var list = tiered((D.creators || []).map(view).filter(Boolean)), T = TIERS();
    if (!list.length) {
      var e = el("div", "ss-empty"); e.appendChild(el("b", null, "No posts match these filters")); e.appendChild(el("span", null, "Try All content, All platforms or Everyone."));
      b.appendChild(e); return;
    }
    var key = { rank: function (v) { return v.typical; }, er: function (v) { return v.er || 0; }, posts: function (v) { return v.posts.length * 1e12 + v.typical; } }[state.sort];
    [1, 2, 3].forEach(function (t) {
      var items = list.filter(function (v) { return v.tier === t; }).sort(function (x, y) { return key(y) - key(x); });
      if (!items.length) return;
      var sec = el("section", "ss-tier ss-tier--" + t); sec.setAttribute("aria-labelledby", "ss-tier" + t);
      var hd = el("div", "ss-tier__hd"), st = el("h2", "ss-stamp ss-stamp--" + t + (deal ? " press" : ""), T[t][0]);
      st.id = "ss-tier" + t; st.style.animationDelay = (t - 1) * 120 + "ms";
      hd.appendChild(st); hd.appendChild(el("span", "ss-tier__rule", T[t][1])); hd.appendChild(el("span", "ss-tier__n", items.length + (items.length === 1 ? " creator" : " creators")));
      sec.appendChild(hd);
      var g = el("div", "ss-grid"), cap = state.open[t] ? items.length : TIER_CAP;
      items.slice(0, cap).forEach(function (v, i) { g.appendChild(card(v, i, deal)); });
      sec.appendChild(g);
      if (items.length > cap) {
        var more = el("button", "ss-btn ss-btn--sm ss-moreall", "Show all " + items.length + " " + T[t][0].toLowerCase());
        more.type = "button";
        more.addEventListener("click", function () { state.open[t] = true; drawBoard(false); var s2 = document.getElementById("ss-tier" + t); if (s2) s2.scrollIntoView({ block: "start" }); });
        sec.appendChild(more);
      }
      b.appendChild(sec);
    });
  }
  function card(v, i, deal) {
    var c = v.c, T = TIERS(), dim = c.status === "rejected" || !!c.locked;
    var a = el("button", "ss-card" + (deal ? " deal" : "") + (dim ? " is-dim" : "")); a.type = "button"; a.style.setProperty("--i", Math.min(i, 20));
    a.setAttribute("aria-label", (c.name || "@" + c.handle) + ", " + T[v.tier][0] + ". Open their competitor posts.");
    var ph = el("div", "ss-card__ph"); ph.appendChild(photoEl(c)); ph.appendChild(platIcons(c.platforms));
    var bd = el("div", "ss-badges");
    if (c.locked) { var lk = el("span", "ss-badge"); lk.appendChild(icon("lock")); lk.appendChild(document.createTextNode("Unavailable")); bd.appendChild(lk); }
    else if (c.status === "rejected") bd.appendChild(el("span", "ss-badge ss-badge--off", "Not chosen"));
    else if (c.status === "approved") { var ap = el("span", "ss-badge"); ap.appendChild(icon("ok")); ap.appendChild(document.createTextNode("Approved")); bd.appendChild(ap); }
    else { var ins = el("span", "ss-badge"); ins.appendChild(el("i")); ins.appendChild(document.createTextNode("In your selection")); bd.appendChild(ins); }
    if (c.type === "hcp") { var hc = el("span", "ss-badge ss-badge--hcp"); hc.appendChild(icon("steth")); hc.appendChild(document.createTextNode("Doctor")); bd.appendChild(hc); }
    if (v.recent) bd.appendChild(recentBadge(v.recent));
    ph.appendChild(bd); a.appendChild(ph);
    var body = el("div", "ss-card__b"), nm = el("div", "ss-card__nm");
    var nb = el("b", null, c.name || "@" + c.handle); nb.title = c.name || "@" + c.handle; nm.appendChild(nb);
    var hs = el("span", null, "@" + c.handle + (c.followers ? " · " + num(c.followers) + " followers" : "")); hs.title = "@" + c.handle; nm.appendChild(hs);
    body.appendChild(nm);
    var ns = el("div", "ss-nums");
    [[num(v.best), "Best views"], [pct(v.er), "Engagement"], [String(v.posts.length), v.posts.length === 1 ? "Post" : "Posts"]]
      .forEach(function (x) {
        var d = el("div"), lb = el("span", null, x[1]); d.appendChild(el("b", null, x[0]));
        if (x[1] === "Engagement") lb.setAttribute("data-short", "Eng. rate");          // phones (study-share.css)
        d.appendChild(lb); ns.appendChild(d);
      });
    body.appendChild(ns); body.appendChild(el("p", "ss-why", why(v)));
    var lg = el("div", "ss-logos"), names = Object.keys(v.comps);
    names.slice(0, 3).forEach(function (n) { lg.appendChild(logo(n)); });
    if (names.length > 3) lg.appendChild(el("span", "ss-more", "+" + (names.length - 3)));
    body.appendChild(lg); a.appendChild(body);
    a.addEventListener("click", function () { openDos(v, a); });
    return a;
  }

  /* ---------- insights ---------- */
  function compStats() {
    return (D.competitors || []).map(function (c) {
      var byK = {};
      allPosts().forEach(function (x) { if (x.q.competitor === c.name && !x.q.paid_boost) { var k = kindOf(x.q), v = measure(x.q); if (typeof v === "number") (byK[k] = byK[k] || []).push(v); } });
      var bk = Object.keys(byK).sort(function (a, b) { return med(byK[b]) - med(byK[a]); })[0];
      return { name: c.name, creators: c.creators, posts: c.posts, views: c.views, bestKind: bk, bestVal: bk ? med(byK[bk]) : null };
    });
  }
  function scoreTable(st) {
    var max = Math.max.apply(null, st.map(function (s) { return s.views || 0; }).concat([1]));
    var t = el("table", "ss-score"), hr = el("tr");
    [["Competitor"], ["Creators", "n"], ["Posts", "n hide-m"], ["Views", "n"], ["", "hide-m"], ["Worked best", "hide-m"]].forEach(function (h) { hr.appendChild(el("th", h[1] || "", h[0])); });
    t.appendChild(hr);
    st.forEach(function (s, i) {
      var tr = el("tr", i === 0 ? "lead" : ""), c0 = el("td"); c0.appendChild(logo(s.name, true)); tr.appendChild(c0);
      tr.appendChild(el("td", "n", String(s.creators))); tr.appendChild(el("td", "n hide-m", String(s.posts))); tr.appendChild(el("td", "n", num(s.views)));
      var cb = el("td", "hide-m"), vb = el("div", "ss-vbar"), fi = el("i"); fi.style.width = ((s.views || 0) / max * 100).toFixed(1) + "%"; vb.appendChild(fi); cb.appendChild(vb); tr.appendChild(cb);
      var ck = el("td", "hide-m"), bk = el("span", "ss-best");
      if (s.bestKind) { bk.appendChild(icon(KICON[s.bestKind])); bk.appendChild(document.createTextNode(KPLURAL[s.bestKind] + " · " + num(s.bestVal) + " typical")); }
      ck.appendChild(bk); tr.appendChild(ck); t.appendChild(tr);
    });
    return t;
  }
  function kindTiles() {
    var byK = {};
    allPosts().forEach(function (x) { if (!x.q.paid_boost) { var v = measure(x.q); if (typeof v === "number") (byK[kindOf(x.q)] = byK[kindOf(x.q)] || []).push(v); } });
    var ks = Object.keys(byK).map(function (k) { return { k: k, typ: med(byK[k]) || 0, n: byK[k].length }; });
    if (ks.length < 2) return null;
    var win = ks.slice().sort(function (a, b) { return b.typ - a.typ; })[0].k, w = el("div", "ss-kinds");
    ks.sort(function (a, b) { return ["reel", "post", "video", "story"].indexOf(a.k) - ["reel", "post", "video", "story"].indexOf(b.k); }).forEach(function (x) {
      var d = el("div", "ss-kind" + (x.k === win ? " win" : "")), h = el("div", "ss-kind__hd");
      h.appendChild(icon(KICON[x.k])); h.appendChild(document.createTextNode(KPLURAL[x.k]));
      if (x.k === win) h.appendChild(el("span", "ss-crown", "Works best"));
      d.appendChild(h); d.appendChild(el("b", null, num(x.typ))); d.appendChild(el("small", null, "typical " + unit() + " per post · " + x.n + " posts")); w.appendChild(d);
    });
    return w;
  }
  function sectionScore() {
    var s = el("section", "ss-sec"), hd = el("div", "ss-sec__hd"), h = el("h2", null, "Your competitors on creators"); h.id = "ss-sc";
    s.setAttribute("aria-labelledby", "ss-sc");
    hd.appendChild(h); hd.appendChild(el("p", null, "Who uses creators the most, what they got for it, and which kind of content worked best for each brand."));
    s.appendChild(hd); s.appendChild(scoreTable(compStats()));
    var k = kindTiles(); if (k) s.appendChild(k);
    return s;
  }
  function topPosts(n, comp) {
    return allPosts().filter(function (x) { return !x.q.paid_boost && typeof x.q.views === "number" && (!comp || x.q.competitor === comp); })
      .sort(function (a, b) { return b.q.views - a.q.views; }).slice(0, n);
  }
  function wallSection() {
    var tp = topPosts(12);
    if (!tp.length) return null;
    var s = el("section", "ss-sec"), hd = el("div", "ss-sec__hd"), h = el("h2", null, "Their " + tp.length + " best posts"); h.id = "ss-wall";
    s.setAttribute("aria-labelledby", "ss-wall");
    hd.appendChild(h); hd.appendChild(el("p", null, "The competitor posts with the most views. Tap one to watch it on the platform."));
    s.appendChild(hd);
    var w = el("div", "ss-wall"); tp.forEach(function (x) { w.appendChild(thumb(x.q, x.c.name || "@" + x.c.handle)); }); s.appendChild(w);
    return s;
  }
  function timeline() {
    var ts = allPosts().map(function (x) { return day(x.q.date); }).filter(function (t) { return t != null; });
    if (ts.length < 3) return null;
    var last = new Date(Math.max.apply(null, ts)), months = [];
    for (var i = 7; i >= 0; i--) months.push(new Date(Date.UTC(last.getUTCFullYear(), last.getUTCMonth() - i, 1)));
    var key = function (d) { return d.getUTCFullYear() * 12 + d.getUTCMonth(); }, k0 = key(months[0]);
    var tl = el("div", "ss-tl"); tl.style.setProperty("--m", months.length);
    tl.appendChild(el("div", "mh", "")); months.forEach(function (d) { tl.appendChild(el("div", "mh", d.toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" }))); });
    (D.competitors || []).forEach(function (c) {
      var cnt = months.map(function () { return 0; });
      allPosts().forEach(function (x) { if (x.q.competitor !== c.name) return; var t = day(x.q.date); if (t == null) return; var j = key(new Date(t)) - k0; if (j >= 0 && j < cnt.length) cnt[j]++; });
      var peak = Math.max.apply(null, cnt), lc = el("div"); lc.appendChild(logo(c.name)); tl.appendChild(lc);
      cnt.forEach(function (n, j) {
        var cell = el("div", "cell");
        if (n) { var d = el("span", "ss-dot" + (n === peak && peak > 1 ? " hot" : ""), String(n)), sz = Math.min(18 + n * 3, 32) + "px"; d.style.width = d.style.height = sz;
                 d.title = n + (n === 1 ? " post in " : " posts in ") + months[j].toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }); cell.appendChild(d); }
        tl.appendChild(cell);
      });
    });
    return tl;
  }
  function timelineSection() {
    var tl = timeline(); if (!tl) return null;
    var s = el("section", "ss-sec"), hd = el("div", "ss-sec__hd"), h = el("h2", null, "When they post"); h.id = "ss-tl";
    s.setAttribute("aria-labelledby", "ss-tl");
    hd.appendChild(h); hd.appendChild(el("p", null, "Creator posts per month for each competitor. The bigger the dot, the more posts; orange marks each brand’s busiest month."));
    s.appendChild(hd); s.appendChild(tl);
    return s;
  }
  function gapCards(rootEl, print, cap) {
    rootEl.textContent = "";
    (D.outside || []).slice(0, cap || 999).forEach(function (o) {
      var g = el("div", "ss-gap"), hd = el("div", "ss-gap__hd");
      if (o.post_id != null) {
        var u = safeUrl(o.post_url), pic = el(u ? "a" : "div", "ss-gap__pic");
        if (u) { pic.href = u; pic.target = "_blank"; pic.rel = "noopener noreferrer"; pic.setAttribute("aria-label", "Watch @" + o.handle + "\u2019s best competitor post"); }
        var pim = el("img"); pim.src = thumbSrc(o.post_id); pim.alt = ""; pim.loading = print ? "eager" : "lazy"; pim.decoding = "async";
        pim.addEventListener("error", function () { pic.classList.add("is-none"); pim.remove(); });
        pic.appendChild(pim); pic.appendChild(platIconsFor(o)); g.appendChild(pic);
      }
      hd.appendChild(el("span", "ss-gap__av", initials(o.name || o.handle)));
      var nm = el("div"); nm.appendChild(el("b", null, o.name || "@" + o.handle)); nm.appendChild(el("span", null, "@" + o.handle + (o.followers ? " · " + num(o.followers) + " followers" : "")));
      hd.appendChild(nm); g.appendChild(hd);
      var row = el("div", "ss-logos"); Object.keys(o.competitors || {}).forEach(function (n) { row.appendChild(logo(n)); }); g.appendChild(row);
      var ns = el("div", "ss-gap__n");
      [[num(o.median_views), "Typical views"], [String(o.posts || 0), (o.posts === 1 ? "Competitor post" : "Competitor posts")]]
        .forEach(function (x) { var d = el("div"); d.appendChild(el("b", null, x[0])); d.appendChild(el("span", null, x[1])); ns.appendChild(d); });
      g.appendChild(ns);
      if (!print) g.appendChild(askButton(o, "roster", "Ask us to sign them", "Asked. We will come back to you.", true));
      rootEl.appendChild(g);
    });
  }
  function platIconsFor(o) { return platIcons(o.post_url && /tiktok\.com/.test(o.post_url) ? ["tiktok"] : ["instagram"]); }
  function gapsSection() {
    var s = el("section", "ss-sec"), hd = el("div", "ss-sec__hd"), h = el("h2", null, "Not on our roster yet"); h.id = "ss-gap";
    s.setAttribute("aria-labelledby", "ss-gap");
    hd.appendChild(h); hd.appendChild(el("p", null, "Strong creators your competitors use who are not with HelloVoice yet. Ask, and we will try to sign them for you."));
    s.appendChild(hd);
    var g = el("div", "ss-gaps"); gapCards(g, false); s.appendChild(g);
    return s;
  }
  // POST /api/evidence/request: book a creator in the selection, check an unavailable one again, or sign a new one.
  function askButton(c, kind, label, done, small) {
    var box = el("div");
    function paint() {
      box.textContent = "";
      if (ASKED[kind + ":" + c.handle]) { var s = el("div", "ss-sent"); s.appendChild(icon("ok")); s.appendChild(document.createTextNode(done)); box.appendChild(s); return; }
      var b = el("button", "ss-btn" + (small ? " ss-btn--sm" : " ss-btn--lime")); b.type = "button"; b.appendChild(icon("send")); b.appendChild(document.createTextNode(label));
      b.addEventListener("click", function () {
        b.disabled = true; b.lastChild.textContent = "Sending…";
        api("POST", "/api/evidence/request", { token: SEL, handle: c.handle, kind: kind }).then(function (r) {
          if (r.st === 200 && r.b.ok) { ASKED[kind + ":" + c.handle] = true; paint(); }
          else { b.disabled = false; b.lastChild.textContent = "That did not send. Try again"; }
        });
      });
      box.appendChild(b);
    }
    paint();
    box.style.display = "contents";
    return box;
  }

  /* ---------- dossier ---------- */
  var dos = null, scrim = null, lastFocus = null;
  function ensureDos() {
    if (dos) return;
    scrim = el("div", "ss-scrim"); scrim.hidden = true;
    dos = el("aside", "ss-dos"); dos.hidden = true; dos.setAttribute("role", "dialog"); dos.setAttribute("aria-modal", "true"); dos.setAttribute("aria-labelledby", "ss-dos-n");
    document.body.appendChild(scrim); document.body.appendChild(dos);
    scrim.addEventListener("click", closeDos);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !dos.hidden) closeDos(); });
    var y0 = null;
    dos.addEventListener("touchstart", function (e) { if (e.target.closest && e.target.closest(".ss-dos__hd, .ss-handle")) y0 = e.touches[0].clientY; }, { passive: true });
    dos.addEventListener("touchmove", function (e) { if (y0 != null) dos.style.transform = "translateY(" + Math.max(0, e.touches[0].clientY - y0) + "px)"; }, { passive: true });
    dos.addEventListener("touchend", function (e) { if (y0 == null) return; var d = e.changedTouches[0].clientY - y0; dos.style.transform = ""; y0 = null; if (d > 90) closeDos(); });
  }
  function openDos(v, from) {
    ensureDos(); lastFocus = from;
    var c = v.c, T = TIERS(), nm = c.name || "@" + c.handle, first = shortName(c);
    dos.textContent = "";
    dos.appendChild(el("span", "ss-handle"));
    var hd = el("div", "ss-dos__hd"), av = el("div", "ss-dos__av"); av.appendChild(photoEl(c, "ss-av", true)); hd.appendChild(av);
    var ht = el("div"), h2 = el("h2", null, nm); h2.id = "ss-dos-n"; ht.appendChild(h2);
    var sub = el("p", null, "@" + c.handle + (c.followers ? " · " + num(c.followers) + " followers" : "")); sub.appendChild(platIcons(c.platforms));
    if (c.type === "hcp") { var hb = el("span", "ss-badge ss-badge--hcp"); hb.appendChild(icon("steth")); hb.appendChild(document.createTextNode("Doctor")); sub.appendChild(hb); }
    ht.appendChild(sub); hd.appendChild(ht);
    var x = el("button", "ss-x"); x.type = "button"; x.setAttribute("aria-label", "Close"); x.appendChild(icon("x")); x.addEventListener("click", closeDos); hd.appendChild(x);
    dos.appendChild(hd);
    var body = el("div", "ss-dos__sc");
    var vd = el("div", "ss-verdict"); vd.appendChild(el("span", "ss-stamp ss-stamp--" + v.tier, T[v.tier][0])); vd.appendChild(el("p", null, why(v) + " " + T[v.tier][1])); body.appendChild(vd);
    if (v.recent) {
      var fl = el("div", "ss-flag"); fl.appendChild(icon("clock")); fl.appendChild(document.createTextNode("Posted for")); fl.appendChild(logo(v.recent.comp));
      fl.appendChild(document.createTextNode(v.recent.days + (v.recent.days === 1 ? " day" : " days") + " ago. Check exclusivity before booking.")); body.appendChild(fl);
    }
    var dn = el("div", "ss-dnums");
    [[num(v.best), "Best views"], [num(v.typical), BY_ENG ? "Typical engagement" : "Typical views"], [pct(v.er), "Avg engagement"]]
      .forEach(function (y) { var d = el("div"); d.appendChild(el("b", null, y[0])); d.appendChild(el("span", null, y[1])); dn.appendChild(d); });
    body.appendChild(dn);
    body.appendChild(el("h3", null, v.posts.length + (v.posts.length === 1 ? " competitor post" : " competitor posts")));
    var dw = el("div", "ss-dwall"); v.posts.forEach(function (q) { dw.appendChild(thumb(q)); }); body.appendChild(dw);
    body.appendChild(el("h3", null, "Notes from your team"));
    var nb = el("div"); body.appendChild(nb); drawNotes(nb, c, first);
    dos.appendChild(body);
    var ft = el("div", "ss-dos__ft");
    if (c.status === "rejected") ft.appendChild(el("small", null, "Not chosen for this selection. Ask your HelloVoice contact to bring them back."));
    else {
      ft.appendChild(askButton(c, c.locked ? "unavailable" : "book", c.locked ? "Ask HelloVoice to check again" : "Ask HelloVoice for " + first,
                               "Sent. Your HelloVoice contact will reply within one working day.", false));
      ft.appendChild(el("small", null, c.locked ? "Marked unavailable; we will check again." : "Goes to your account manager. Nothing changes in your selection."));
    }
    dos.appendChild(ft);
    scrim.hidden = false; dos.hidden = false;
    requestAnimationFrame(function () { scrim.classList.add("on"); dos.classList.add("on"); x.focus(); });
  }
  function drawNotes(box, c, first) {
    box.textContent = "";
    (NOTES[c.handle] || []).forEach(function (n) {
      var d = el("div", "ss-note", n.t);
      d.appendChild(el("small", null, (n.by || (n.staff ? "HelloVoice" : "Your team")) + (n.at ? " · " + new Date(n.at * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "")));
      box.appendChild(d);
    });
    var f = el("form", "ss-note-form"), ta = el("textarea"); ta.placeholder = "Add a note about " + first + "…"; ta.maxLength = 280; ta.setAttribute("aria-label", "Note about " + (c.name || c.handle));
    var row = el("div", "row"), b = el("button", "ss-btn ss-btn--sm"); b.type = "submit"; b.textContent = "Save note";
    var hint = el("span", null, "Your team and your HelloVoice contact see notes.");
    row.appendChild(hint); row.appendChild(b); f.appendChild(ta); f.appendChild(row);
    f.addEventListener("submit", function (e) {
      e.preventDefault();
      var t = ta.value.trim(); if (!t) { ta.focus(); return; }
      b.disabled = true;
      api("POST", "/api/evidence/note", { token: SEL, handle: c.handle, note: t }).then(function (r) {
        if (r.st === 200 && r.b.ok) { (NOTES[c.handle] = NOTES[c.handle] || []).push(r.b.note); drawNotes(box, c, first); }
        else { b.disabled = false; hint.className = "ss-err"; hint.textContent = "That note did not save. Try again."; }
      });
    });
    box.appendChild(f);
  }
  function closeDos() {
    if (!dos) return;
    scrim.classList.remove("on"); dos.classList.remove("on");
    setTimeout(function () { scrim.hidden = true; dos.hidden = true; }, 350);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  /* ---------- PDF: its own A4 pages, links stay live in the saved file ---------- */
  function buildPdf() {
    var pr = document.querySelector(".ss-print");
    if (!pr) { pr = el("div", "ss-print"); pr.setAttribute("aria-hidden", "true"); document.body.appendChild(pr); }
    pr.textContent = "";
    var keep = { comp: state.comp, plat: state.plat, kind: state.kind, ctype: state.ctype };
    state.comp = state.plat = state.kind = state.ctype = "all";
    var all = tiered((D.creators || []).map(view).filter(Boolean)).sort(function (a, b) { return a.tier - b.tier || b.typical - a.typical; }), n = 0;
    var asOf = typeof HV.asOf === "function" ? HV.asOf() : "";
    function page(cls) { var p = el("section", "ss-page" + (cls ? " " + cls : "")); pr.appendChild(p); return p; }
    function foot(pg) {
      var f = el("div", "ss-page__ft"), l = el("span");
      l.appendChild(document.createTextNode("HELVi Intelligence · Prepared by HelloVoice for")); if (D.brand) l.appendChild(logo(D.brand)); l.appendChild(document.createTextNode(asOf ? "· " + asOf : ""));
      f.appendChild(l); f.appendChild(el("span", null, "Page " + (++n))); pg.appendChild(f);
    }
    var cv = page("ss-pcover"), ct = el("div", "ss-pcover__top"), mk = el("img", "ss-pcover__mark");
    mk.src = ROOT + "assets/brand/modules/helvi-intelligence-logo-v5.png"; mk.alt = "HELVi Intelligence"; ct.appendChild(mk);
    if (D.brand) ct.appendChild(logo(D.brand, true));
    cv.appendChild(ct);
    var h = el("h1"); h.appendChild(document.createTextNode("Who to book, ")); h.appendChild(el("em", null, "already proven")); h.appendChild(document.createTextNode(" on your competitors")); cv.appendChild(h);
    cv.appendChild(el("p", null, "Competitor study · " + (D.objective || "Awareness") + ". The creators in your selection who already posted for your competitors, ranked by the "
      + (BY_ENG ? "likes and comments" : "views") + " those posts got. Tap any view count or post to open it."));
    var crow = el("div", "ss-pcover__row"), art = el("img", "ss-pcover__char");
    art.src = ROOT + "assets/brand/modules/helvi-intel-character-960.webp"; art.alt = "";
    crow.appendChild(comps()); crow.appendChild(art); cv.appendChild(crow);
    var pf = el("div", "ss-pfacts"), posts = 0, views = 0;
    all.forEach(function (v) { posts += v.posts.length; v.organic.forEach(function (q) { views += q.views || 0; }); });
    [[(D.competitors || []).length, "Competitors studied"], [all.length, "Creators in your selection"], [posts, "Competitor posts found"], [num(views), "Views on those posts"]]
      .forEach(function (x) { var d = el("div"); d.appendChild(el("b", null, String(x[0]))); d.appendChild(el("span", null, x[1])); pf.appendChild(d); });
    cv.appendChild(pf); foot(cv);
    // shortlist, 20 rows a page
    var T = TIERS();
    var ROWS = 18;
    for (var i = 0; i < all.length; i += ROWS) {
      var p2 = page(); p2.appendChild(el("h2", null, i ? "Your shortlist, continued" : "Your shortlist, ranked"));
      if (!i) p2.appendChild(el("p", "lede", T[1][0] + ": " + T[1][1] + " " + T[2][0] + ": " + T[2][1] + " " + T[3][0] + ": the rest. Boosted posts are left out of the numbers."));
      p2.appendChild(ptable(all.slice(i, i + ROWS), true, i)); foot(p2);
    }
    // competitors + content + timeline
    var p3 = page(); p3.appendChild(el("h2", null, "Your competitors on creators"));
    p3.appendChild(el("p", "lede", "Creators used, posts and views per competitor, with the content type that worked best for each brand."));
    p3.appendChild(scoreTable(compStats()));
    var kt = kindTiles(); if (kt) { kt.className = "ss-pkinds"; p3.appendChild(kt); }
    foot(p3);
    var tl = timeline();
    if (tl) {
      var p3b = page(); p3b.appendChild(el("h2", null, "When they post"));
      p3b.appendChild(el("p", "lede", "Creator posts per month for each competitor. The bigger the dot, the more posts; orange marks each brand\u2019s busiest month."));
      p3b.appendChild(tl); foot(p3b);
    }
    // best posts
    var tp = topPosts(12);
    if (tp.length) {
      var p4 = page(); p4.appendChild(el("h2", null, "Their " + tp.length + " best posts")); p4.appendChild(el("p", "lede", "Tap any post to watch it on the platform."));
      var pw = el("div", "ss-pwall"); tp.forEach(function (x) { pw.appendChild(thumb(x.q, x.c.name || "@" + x.c.handle)); }); p4.appendChild(pw); foot(p4);
    }
    // one page per competitor
    (D.competitors || []).forEach(function (c) {
      state.comp = c.name;
      var list = tiered((D.creators || []).map(view).filter(Boolean)).sort(function (a, b) { return b.typical - a.typical; });
      if (!list.length) return;
      var pg = page(), hh = el("h2"); hh.appendChild(logo(c.name, true)); hh.appendChild(document.createTextNode("Creators who posted for them")); hh.style.fontSize = "28px"; pg.appendChild(hh);
      var cp = el("div", "ss-pcomp");
      [[c.creators, "Creators"], [c.posts, "Posts"], [num(c.views), "Views"]].forEach(function (x) { var d = el("div"); d.appendChild(el("b", null, String(x[0]))); d.appendChild(el("span", null, x[1])); cp.appendChild(d); });
      pg.appendChild(cp);
      var cw = topPosts(4, c.name);
      if (cw.length) { var tw = el("div", "ss-pwall"); cw.forEach(function (x) { tw.appendChild(thumb(x.q, x.c.name || "@" + x.c.handle)); }); pg.appendChild(tw); }
      pg.appendChild(ptable(list.slice(0, 10), false, 0));
      if (list.length > 10) pg.appendChild(el("p", "lede", "+ " + (list.length - 10) + " more creators who posted for them: see the shortlist."));
      foot(pg);
    });
    // roster gaps
    if ((D.outside || []).length) {
      var p6 = page(); p6.appendChild(el("h2", null, "Not on our roster yet"));
      p6.appendChild(el("p", "lede", "Strong creators your competitors use who are not with HelloVoice yet. Ask your HelloVoice contact and we will try to sign them."));
      var gg = el("div", "ss-pgaps"); gapCards(gg, true, 10); p6.appendChild(gg); foot(p6);
    }
    state.comp = keep.comp; state.plat = keep.plat; state.kind = keep.kind; state.ctype = keep.ctype;
    return pr;
  }
  function ptable(list, withTier, start) {
    var T = TIERS(), t = el("table", "ss-ptable"), hr = el("tr");
    var cols = ["#", "Creator", withTier ? "Tier" : "On", "Competitors", "Best views", BY_ENG ? "Typical eng." : "Typical", "Engagement", "Posts"];
    var w = ["7mm", "44mm", withTier ? "22mm" : "16mm", "auto", "18mm", "16mm", "18mm", "11mm"];
    cols.forEach(function (x, i) { var th = el("th", i > 3 ? "n" : "", x); th.style.width = w[i]; hr.appendChild(th); });
    t.appendChild(hr);
    list.forEach(function (v, i) {
      var tr = el("tr"); tr.appendChild(el("td", null, String(start + i + 1)));
      var nm = el("td"); nm.appendChild(el("b", null, v.c.name || "@" + v.c.handle)); nm.appendChild(el("div", null, "@" + v.c.handle)); tr.appendChild(nm);
      var t3 = el("td"); if (withTier) t3.appendChild(el("span", "ss-ptier ss-ptier--" + v.tier, T[v.tier][0])); else t3.appendChild(platIcons(v.c.platforms)); tr.appendChild(t3);
      var t4 = el("td"), lg = el("span", "ss-logos"); Object.keys(v.comps).slice(0, 3).forEach(function (nn) { lg.appendChild(logo(nn)); }); t4.appendChild(lg); tr.appendChild(t4);
      var bp = v.organic.filter(function (q) { return typeof q.views === "number"; }).sort(function (a, b) { return b.views - a.views; })[0], bv = el("td", "n");
      if (bp && safeUrl(bp.url)) { var a = el("a", null, num(v.best)); a.href = bp.url; a.target = "_blank"; a.rel = "noopener noreferrer"; bv.appendChild(a); } else bv.textContent = num(v.best);
      tr.appendChild(bv); tr.appendChild(el("td", "n", num(v.typical))); tr.appendChild(el("td", "n", pct(v.er))); tr.appendChild(el("td", "n", String(v.posts.length)));
      t.appendChild(tr);
    });
    return t;
  }
  HV.pdf = function (btn) {
    if (!D) return;
    if (btn) btn.disabled = true;
    var pr = buildPdf(), html = document.documentElement;
    // rs-printing lifts catalogue.css's "cannot be printed" block, as for every report's own Download PDF.
    html.classList.add("ss-printing", "rs-printing");
    var imgs = Array.prototype.slice.call(pr.querySelectorAll("img"));
    imgs.forEach(function (i) { i.loading = "eager"; });
    var waitAll = Promise.all(imgs.map(function (i) { return i.complete ? 0 : new Promise(function (ok) { i.addEventListener("load", ok); i.addEventListener("error", ok); }); }));
    var done = function () { html.classList.remove("ss-printing", "rs-printing"); if (btn) btn.disabled = false; window.removeEventListener("afterprint", done); };
    window.addEventListener("afterprint", done);
    Promise.race([waitAll, new Promise(function (ok) { setTimeout(ok, 6000); })]).then(function () {
      api("POST", "/api/report/ping", { what: "pdf" });          // the KAM hears once a day that the PDF was saved
      setTimeout(function () { window.print(); }, 80);
    });
  };
  HV.studyReady = function () { return !!(D && refs.board && refs.board.querySelector(".ss-card")); };
})();
