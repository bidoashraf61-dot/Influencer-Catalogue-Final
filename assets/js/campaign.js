/* Campaign report — the client's read-only view, as a match-day results
   package. All data comes from the admin service:
     GET /api/campaigns           the passcode's campaigns (never drafts)
     GET /api/campaign?t=<token>  one report, already stripped of anything
                                  internal (cost, CPM, EMV, ratings, notes)
   Links: /campaign/ lists campaigns (one campaign opens directly),
   /campaign/#list always lists, /campaign/#t=<token> opens one. */
(function () {
  "use strict";

  var CFG = window.CAMPAIGN_CONFIG || {};
  var API = CFG.api || "/admin";
  var ICONS = (window.HV_ICONS || {}).icons || {};
  var ICON_LINK = (window.HV_ICONS || {}).link || "";
  var R = null;
  var FILTER = { platform: "", kind: "", section: "campaign" };
  var KIND = { post: "Post", reel: "Reel", story: "Story", video: "Video", short: "Short" };
  var PLURAL = { post: "Posts", reel: "Reels", story: "Stories", video: "Videos", short: "Shorts" };
  var SIG = { good: "Strong", moderate: "Fair", low: "Low" };
  var countryName = (function () {
    try { var d = new Intl.DisplayNames(["en"], { type: "region" }); return function (c) { return d.of(c) || c; }; }
    catch (e) { return function (c) { return c; }; }
  })();

  function $(id) { return document.getElementById(id); }
  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function num(v) {
    if (v == null) return "—";
    var n = Math.round(v), a = Math.abs(n);
    if (a >= 1e6) return (n / 1e6).toFixed(a >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
    if (a >= 1e4) return (n / 1e3).toFixed(a >= 1e5 ? 0 : 1).replace(/\.0$/, "") + "K";
    return n.toLocaleString("en-US");
  }
  function full(v) { return v == null ? "—" : Math.round(v).toLocaleString("en-US"); }
  function pct(v, d) { return v == null ? "—" : v.toFixed(d == null ? 2 : d) + "%"; }
  function day(t, withYear) {
    if (!t) return "";
    var d = typeof t === "number" ? new Date(t * 1000) : new Date(t + "T00:00:00Z");
    return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: withYear === false ? undefined : "numeric", timeZone: "UTC" });
  }
  function ago(t) {
    if (!t) return "";
    var s = Date.now() / 1000 - t;
    if (s < 3600) return Math.max(1, Math.round(s / 60)) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    return Math.round(s / 86400) + " days ago";
  }
  function icon(p) { return ICONS[p] || ICON_LINK; }
  function sig(grade, title) {
    var g = SIG[grade] ? grade : "none";
    return '<span class="mx-sig mx-sig--' + g + '"' + (title ? ' title="' + esc(title) + '"' : "") + ">"
      + (SIG[grade] || "No data") + "</span>";
  }
  function flag(cc) { return '<span class="fi fi-' + esc(String(cc).toLowerCase()) + '" aria-hidden="true"></span>'; }
  function ava(photo) {
    return photo ? '<img src="' + esc(photo) + '" alt="" loading="lazy" referrerpolicy="no-referrer">'
      : '<span class="mx-ava" aria-hidden="true"></span>';
  }
  function token() { var m = /(?:^|[#&])t=([A-Za-z0-9_-]+)/.exec(location.hash || ""); return m ? m[1] : ""; }
  function utc(dateStr, endOfDay) { return Date.parse(dateStr + "T00:00:00Z") / 1000 + (endOfDay ? 86399 : 0); }
  function get(path) {
    return fetch(API + path, { credentials: "include", cache: "no-store" }).then(function (r) {
      if (r.status === 401) throw { locked: true };
      if (!r.ok) throw { status: r.status };
      return r.json();
    });
  }

  /* ---------------------------------------------------------------- gate */

  var REFUSALS = { revoked: "This code has been withdrawn.", expired: "This code has expired.",
    exhausted: "This code has been used up.", devices: "This code is already open on its maximum number of devices.",
    unknown: "That code is not right." };

  function lock(msg) {
    $("cat-app").hidden = true; $("cat-gate").hidden = false;
    document.body.classList.add("cat-locked");
    if (msg) { $("cat-gate-error").textContent = msg; $("cat-gate-error").hidden = false; }
    setTimeout(function () { $("cat-code").focus(); }, 50);
  }
  function unlocked() { $("cat-gate").hidden = true; $("cat-app").hidden = false; document.body.classList.remove("cat-locked"); }

  $("cat-gate-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var btn = this.querySelector("button");
    btn.disabled = true; $("cat-gate-error").hidden = true;
    fetch(API + "/api/unlock", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: $("cat-code").value.trim(), lite: true }) })
      .then(function (r) { return r.json(); })
      .then(function (b) {
        if (!b || !b.ok) { lock(REFUSALS[b && b.reason] || REFUSALS.unknown); return; }
        $("cat-code").value = ""; route();
      })
      .catch(function () { lock("Could not reach the server. Please try again."); })
      .then(function () { btn.disabled = false; });
  });

  /* -------------------------------------------------------------- routing */

  function show(which) {
    $("mx-list").hidden = which !== "list";
    $("mx-report").hidden = which !== "report";
    $("mx-empty").hidden = which !== "empty";
  }
  function empty(msg) { $("mx-empty").textContent = msg; show("empty"); }

  function route() {
    var t = token();
    if (t) return openReport(t);
    get("/api/campaigns").then(function (b) {
      unlocked();
      var list = b.campaigns || [];
      $("mx-all").hidden = true;
      // A single campaign opens straight away — but only on arrival, never
      // when the client asked for the list.
      if (list.length === 1 && location.hash !== "#list") { location.replace("#t=" + list[0].token); return; }
      showList(list);
    }).catch(function (err) { if (err && err.locked) lock(); else empty("Could not load your campaigns. Please try again."); });
  }

  function showList(list) {
    document.title = "My campaigns — HelloVoice";
    if (!list.length) { empty("There are no campaign reports for this access code yet."); return; }
    var live = list.filter(function (c) { return c.status === "live"; }).length;
    $("mx-list-sum").innerHTML = tile("Campaigns", list.length, "") + tile("Live now", live, live ? "go" : "")
      + tile("Completed", list.length - live, "") + '<span id="mx-sum-totals" class="mx-sum__rest"></span>';
    $("mx-list-items").innerHTML = list.map(function (c, i) {
      var now = Date.now() / 1000, span = c.starts_at && c.ends_at ? Math.max(1, Math.round((c.ends_at - c.starts_at) / 86400)) : 0;
      var dn = span ? Math.min(span, Math.max(0, Math.ceil((now - c.starts_at) / 86400))) : 0;
      var when = !span ? "" : now < c.starts_at ? "Starts " + day(c.starts_at) : now <= c.ends_at ? "Day " + dn + " of " + span : "Ran " + span + " days";
      return '<article class="mx-camp" data-i="' + i + '"><div class="mx-camp__head"><div class="mx-camp__logos">'
        + (c.logos || []).map(function (u) { return '<img src="' + esc(u) + '" alt="">'; }).join("") + "</div>"
        + '<div class="mx-camp__id"><h2 class="mx-camp__name">' + esc(c.name) + '</h2><div class="mx-camp__meta">'
        + esc([c.client, c.starts_at ? day(c.starts_at) + " – " + day(c.ends_at) : "", when].filter(Boolean).join(" · ")) + "</div></div>"
        + '<div class="mx-camp__tags"><span class="mx-camp__state mx-camp__state--' + (c.status === "live" ? "live" : "done") + '">' + (c.status === "live" ? "Live" : "Completed") + '</span><span class="mx-camp__verdict" hidden></span></div></div>'
        + '<div class="mx-camp__body"><div class="mx-camp__prog"><p class="mx-camp__wait">Loading progress…</p></div><div class="mx-camp__stats"></div></div>'
        + '<div class="mx-camp__foot"><span class="mx-camp__time">' + (span ? '<span>Campaign time</span><i><b style="width:' + (dn / span * 100).toFixed(1) + '%"></b></i><em>' + Math.round(dn / span * 100) + "%</em>" : "") + "</span>"
        + '<a class="mx-camp__alt" href="#t=' + esc(c.token) + '">Full report</a><a class="mx-camp__go" href="dashboard/#t=' + esc(c.token) + '">Open dashboard →</a></div></article>';
    }).join("");
    show("list");
    window.scrollTo(0, 0);
    var agg = { reach: 0, eng: 0, posts: 0, clicks: 0 }, left = list.length;
    list.forEach(function (c, i) {
      get("/api/campaign?t=" + encodeURIComponent(c.token)).then(function (b) {
        var R = b.report, t = R.total || {}, card = document.querySelector('.mx-camp[data-i="' + i + '"]');
        agg.reach += (t.views || 0) + (t.reach || 0); agg.eng += t.engagement || 0; agg.posts += t.posts || 0; agg.clicks += t.clicks || 0;
        card.querySelector(".mx-camp__prog").innerHTML = progress(R);
        card.querySelector(".mx-camp__stats").innerHTML = stat("Posts live", full(t.posts) + (t.planned ? "<small>/" + t.planned + "</small>" : ""))
          + stat("Reached", num((t.views || 0) + (t.reach || 0))) + stat("Engagement", num(t.engagement))
          + (R.visibility && R.visibility.clicks ? stat("Link clicks", num(t.clicks)) : stat("Avg eng. rate", pct(t.er)));
        var v = R.verdict || {}, vb = card.querySelector(".mx-camp__verdict");
        if (v.label) { vb.textContent = v.label; vb.className = "mx-camp__verdict mx-camp__verdict--" + (v.grade || "none"); vb.hidden = false; }
      }).catch(function () { var card = document.querySelector('.mx-camp[data-i="' + i + '"]'); card.querySelector(".mx-camp__prog").innerHTML = '<p class="mx-camp__wait">Progress is not available right now.</p>'; })
        .then(function () {
          if (--left) return;
          $("mx-sum-totals").innerHTML = tile("People reached", num(agg.reach), "") + tile("Posts live", full(agg.posts), "") + tile("Engagement", num(agg.eng), "");
        });
    });
  }
  function tile(label, value, tone) { return '<div class="mx-sum__tile' + (tone ? " mx-sum__tile--" + tone : "") + '"><b>' + value + "</b><span>" + label + "</span></div>"; }
  function stat(label, value) { return '<div><span>' + label + "</span><b>" + value + "</b></div>"; }
  // The objective as one bar: achieved vs where it should be today, then
  // each of its goals as a chip coloured by how it is doing.
  function progress(R) {
    var o = R.objective || { label: "Balanced", kpis: [] }, items = (R.progress && R.progress.items) || [];
    var mine = items.filter(function (x) { return (o.kpis || []).indexOf(x.key) >= 0; }); if (!mine.length) mine = items;
    if (!mine.length) return '<div class="mx-camp__obj"><span>Objective · <b>' + esc(o.label) + '</b></span></div><p class="mx-camp__wait">No targets set for this campaign.</p>';
    var done = mine.reduce(function (a, x) { return a + Math.min(100, x.pct); }, 0) / mine.length;
    var due = mine.reduce(function (a, x) { return a + Math.min(100, x.expected / x.goal * 100); }, 0) / mine.length;
    var r = due ? done / due : 1, gr = r >= 1 ? "good" : r >= 0.7 ? "moderate" : "low";
    var NAME = { posts: "Posts", views: "Views", reach: "Reach", engagement: "Engagement", er: "Eng. rate", clicks: "Clicks" };
    return '<div class="mx-camp__obj"><span>Objective · <b>' + esc(o.label) + '</b></span><em class="mx-camp__pct mx-camp__pct--' + gr + '">' + Math.round(done) + "%</em></div>"
      + '<div class="mx-camp__bar" role="img" aria-label="' + Math.round(done) + "% of the objective achieved; " + Math.round(due) + '% expected by today"><b class="' + gr + '" style="width:' + done.toFixed(1) + '%"></b>'
      + (due < 100 ? '<i style="left:' + due.toFixed(1) + '%" title="Where it should be today"></i>' : "") + "</div>"
      + '<div class="mx-camp__chips">' + mine.map(function (x) { return '<span class="mx-camp__chip mx-camp__chip--' + (x.grade || "none") + '">' + NAME[x.key] + " <b>" + Math.round(x.pct) + "%</b></span>"; }).join("")
      + (due < 100 ? '<span class="mx-camp__due">│ expected today ' + Math.round(due) + "%</span>" : "") + "</div>";
  }

  function openReport(t) {
    get("/api/campaign?t=" + encodeURIComponent(t)).then(function (b) {
      unlocked();
      var same = R && R.campaign && R._t === t;
      R = b.report; R._t = t;
      FILTER = { platform: "", kind: "", section: "campaign" };
      render(t);
      show("report");
      if (!same) window.scrollTo(0, 0);
      get("/api/campaigns").then(function (x) { $("mx-all").hidden = (x.campaigns || []).length < 2; }).catch(function () {});
    }).catch(function (err) {
      if (err && err.locked) return lock();
      unlocked(); empty("This report is not available with your access code.");
    });
  }
  window.addEventListener("hashchange", route);

  /* ---------------------------------------------------------------- render */

  /* ------------------------------------------------------------- icons */

  // One line-icon set for the report chrome, same stroke as the platform marks.
  function ico(d) { return '<svg class="mx-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + d + "</svg>"; }
  var IC = {
    overview: ico('<rect x="3" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5"/>'),
    leaderboard: ico('<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M7 6H4a3 3 0 0 0 3 4M17 6h3a3 3 0 0 1-3 4"/>'),
    content: ico('<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><circle cx="9" cy="9" r="1.8"/><path d="M20.5 15l-5-5-11 10.5"/>'),
    performance: ico('<path d="M3 20h18"/><path d="M5 16l5-5 4 3 6-7"/><path d="M16 7h4v4"/>'),
    clicks: ico('<path d="M9 3.5v4M3.5 9h4M5 5l2.5 2.5"/><path d="M12 12l8 3-3.5 1.5L15 20z"/>'),
    timeline: ico('<rect x="3.5" y="4.5" width="17" height="16" rx="2.5"/><path d="M8 2.5v4M16 2.5v4M3.5 10h17M8 14h3M13 17h3"/>'),
    posts: ico('<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><path d="M8 12.5l3 3 5-6"/>'),
    views: ico('<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>'),
    reach: ico('<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4.5-6.2"/>'),
    engagement: ico('<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>'),
    er: ico('<path d="M19 5L5 19"/><circle cx="7" cy="7" r="2.5"/><circle cx="17" cy="17" r="2.5"/>'),
    platform: ico('<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/>'),
    mix: ico('<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>'),
    did: ico('<path d="M7 11V5.5a1.5 1.5 0 0 1 3 0V11M10 10V4a1.5 1.5 0 0 1 3 0v6M13 10V5.5a1.5 1.5 0 0 1 3 0V13a7 7 0 0 1-7 7h-.5A5.5 5.5 0 0 1 4 16l-1-3.5a1.5 1.5 0 0 1 2.7-1.2L7 13"/>'),
    country: ico('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>'),
    creator: ico('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>'),
    device: ico('<rect x="2.5" y="4" width="13" height="10" rx="1.5"/><rect x="17" y="8" width="4.5" height="12" rx="1.2"/><path d="M6 18h6"/>'),
    app: ico('<rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2"/>'),
    unique: ico('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/><path d="M17 3.5l1.5 1.5 3-3"/>'),
    ctr: ico('<path d="M4 20L20 4M8 4h12v12"/>'),
    chart: ico('<path d="M3 20h18"/><path d="M4 16l5-6 4 3 7-8"/>')
  };
  // Panel and bench titles get the matching mark.
  var H3IC = { "Reached by platform": "platform", "Content mix": "mix", "What people did": "did", "Who was reached": "country",
    "By creator": "creator", "By app": "app", "By country": "country", "By device": "device",
    "Engagement rate": "er", "Video engagement": "views", "Click-through": "ctr" };
  function h3ic(title) { return IC[H3IC[title]] ? IC[H3IC[title]] : ""; }

  /* ------------------------------------------------------ section jump bar */

  // Every section is on the page; the bar only scrolls to one. It must not
  // touch the URL hash, which carries the report token.
  var SECS = ["overview", "leaderboard", "content", "performance", "clicks", "timeline"];
  var LOCK = 0;
  SECS.forEach(function (k) {
    var a = $("tab-" + k); if (a && !a.querySelector(".mx-ico")) a.insertAdjacentHTML("afterbegin", IC[k]);
    var h = document.querySelector("#sec-" + k + " .mx-h2");
    if (h && !h.querySelector(".mx-h2__ic")) h.insertAdjacentHTML("afterbegin", '<span class="mx-h2__ic">' + IC[k] + "</span>");
  });
  document.querySelector(".mx-tabs__in").addEventListener("click", function (e) {
    var a = e.target.closest(".mx-tab"); if (!a) return;
    e.preventDefault();
    var key = a.getAttribute("data-tab"), sec = $("sec-" + key);
    LOCK = Date.now() + 900;          // let the scroll finish before the observer takes over
    markTab(key);
    if (sec) sec.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  });
  function markTab(key) {
    SECS.forEach(function (k) { var a = $("tab-" + k); if (a) a.classList.toggle("is-on", k === key); });
    var on = $("tab-" + key); if (on && on.scrollIntoView && on.parentNode.scrollWidth > on.parentNode.clientWidth)
      on.parentNode.scrollLeft = on.offsetLeft - 16;
  }
  // The current section is the last one whose top has passed under the
  // sticky bar — simple, and right inside tall dark sections too.
  var ticking = false;
  window.addEventListener("scroll", function () {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () {
      ticking = false;
      if (Date.now() < LOCK) return;
      var cur = null;
      SECS.forEach(function (k) { var el = $("sec-" + k); if (el && !el.hidden && el.getBoundingClientRect().top <= 120) cur = k; });
      if (cur) markTab(cur);
    });
  }, { passive: true });

  /* ------------------------------------------------------- "i" explanations */

  document.addEventListener("click", function (e) {
    var b = e.target.closest(".mx-info");
    document.querySelectorAll(".mx-pop").forEach(function (p) { if (!b || p.previousSibling !== b) { p.previousSibling.setAttribute("aria-expanded", "false"); p.remove(); } });
    if (!b) return;
    if (b.nextSibling && b.nextSibling.className === "mx-pop") { b.nextSibling.remove(); b.setAttribute("aria-expanded", "false"); return; }
    var pop = document.createElement("span");
    pop.className = "mx-pop"; pop.setAttribute("role", "note");
    pop.textContent = b.getAttribute("data-info");
    b.parentNode.insertBefore(pop, b.nextSibling);
    b.setAttribute("aria-expanded", "true");
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") document.querySelectorAll(".mx-pop").forEach(function (p) { p.previousSibling.setAttribute("aria-expanded", "false"); p.remove(); });
  });

  /* ---------------------------------------------------------- carousel */

  function renderCarousel() {
    var cs = R.creators || [];
    $("mx-carousel-wrap").hidden = !cs.length;
    $("mx-carousel").innerHTML = cs.map(function (c) {
      var marks = (c.profiles || []).filter(function (p) { return p.url; }).map(function (p) {
        return '<a href="' + esc(p.url) + '" target="_blank" rel="noopener" aria-label="' + esc(c.name) + " on " + esc(p.platform) + '">' + icon(p.platform) + "</a>";
      }).join("");
      return '<article class="mx-cc"><a class="mx-cc__photo" href="../creator/#c=' + encodeURIComponent(c.code) + '">'
        + (c.photo_large || c.photo ? '<img src="' + esc(c.photo_large || c.photo) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : "")
        + '</a><div class="mx-cc__body"><a class="mx-cc__name" href="../creator/#c=' + encodeURIComponent(c.code) + '">' + esc(c.name) + "</a>"
        + '<span class="mx-cc__meta">' + esc((R.benchmarks.bands[c.band] || "").replace(/ \(.*/, "")) + (c.followers ? " · " + num(c.followers) + " followers" : "")
        + '</span><span class="mx-cc__meta">' + c.delivered + (c.planned ? " of " + c.planned : "") + " posts live</span>"
        + '<div class="mx-tc__links">' + marks + "</div></div></article>";
    }).join("");
  }
  function slide(dir) {
    var t = $("mx-carousel"); t.scrollBy({ left: dir * Math.max(240, t.clientWidth * 0.8), behavior: "smooth" });
  }
  $("mx-car-prev").addEventListener("click", function () { slide(-1); });
  $("mx-car-next").addEventListener("click", function () { slide(1); });

  function render(t) {
    var c = R.campaign;
    document.title = c.name + " — Campaign report — HelloVoice";
    renderBug(c);
    renderScoreline();
    renderProgress(c);
    renderFilters(); renderWall();
    renderBoard();
    renderTargets();
    renderCharts();
    renderClicks();
    renderCarousel();
    $("tab-clicks").hidden = !R.visibility.clicks;
    markTab("overview");
    $("mx-csv").href = API + "/api/campaign.csv?t=" + encodeURIComponent(t);
    $("mx-dash").href = $("mx-dash-end").href = "dashboard/#t=" + encodeURIComponent(t); $("mx-dash").hidden = false;
    // Arriving from the dashboard's "Download PDF": open the print dialog.
    try { if (sessionStorage.getItem("hv_print")) { sessionStorage.removeItem("hv_print"); setTimeout(function () { window.print(); }, 900); } } catch (e) {}
  }

  function renderBug(c) {
    var logos = (c.logos || []).map(function (u) { return '<img src="' + esc(u) + '" alt="Brand logo">'; }).join("");
    $("mx-brands").innerHTML = logos ? logos + '<span class="mx-bug__x" aria-hidden="true">×</span><img class="mx-bug__hv" src="../assets/brand/logo.png" alt="HelloVoice">' : "";
    $("mx-title").textContent = c.name;
    $("mx-sub").textContent = [c.client, c.platform ? c.platform + " campaign" : ""].filter(Boolean).join(" · ");
    var start = c.starts_at, end = c.ends_at, now = Date.now() / 1000, bits = [];
    if (c.status === "live") bits.push('<span class="mx-live">Live</span>');
    else if (c.status === "ended") bits.push("<span>Completed</span>");
    if (start && end) {
      var total = Math.max(1, Math.round((end - start) / 86400)), dn = Math.min(total, Math.max(1, Math.ceil((now - start) / 86400)));
      if (now < start) bits.push("<span>Starts " + day(start, false) + "</span>");
      else if (now <= end) bits.push("Day " + dn + " <span>of " + total + "</span>");
      else bits.push("<span>Ran " + total + " days</span>");
    }
    bits.push("<span>Updated every 24 hours" + (R.updated_at ? " · last " + ago(R.updated_at) : "") + "</span>");
    $("mx-ticker").innerHTML = bits.join(" · ");
    var v = R.verdict || {};
    $("mx-verdict").className = "mx-verdict" + (v.grade ? " mx-verdict--" + v.grade : "");
    $("mx-verdict").innerHTML = esc(v.label || "") + "<small>overall, against target</small>";
  }

  function renderProgress(c) {
    var steps = c.steps || [];
    $("mx-dates").innerHTML = c.starts_at ? "<b>" + day(c.starts_at) + "</b> → <b>" + day(c.ends_at) + "</b>" : "";
    $("mx-note").hidden = !c.status_note;
    $("mx-note").textContent = c.status_note || "";
    if ($("mx-rail")) $("mx-rail").innerHTML = steps.map(function (s) {
      return '<li class="is-' + s.state + '"' + (s.state === "active" ? ' aria-current="step"' : "") + "><b>" + esc(s.label) + "</b>"
        + (s.start ? "<span>" + short(s.start, s.end) + "</span>" : "") + "</li>";
    }).join("");
    var lo = [], hi = [];
    steps.forEach(function (s) { if (s.start && s.end) { lo.push(utc(s.start)); hi.push(utc(s.end, true)); } });
    if (c.starts_at) lo.push(c.starts_at);
    if (c.ends_at) hi.push(c.ends_at);
    var a = lo.length ? Math.min.apply(null, lo) : 0, b = hi.length ? Math.max.apply(null, hi) : 0;
    var span = b - a, now = Date.now() / 1000;
    function x(t) { return span > 0 ? Math.max(0, Math.min(100, (t - a) / span * 100)) : 0; }
    function at(p) { return "left:calc(var(--gl) + (100% - var(--gl)) * " + (p / 100).toFixed(4) + ")"; }
    var STATE = { done: "Done", active: "In progress", pending: "Not started" };
    var axis = "";
    if (span > 0) for (var i = 0; i <= 4; i++) axis += '<span style="left:' + (i * 25) + '%">' + day(a + span * i / 4, false) + "</span>";
    var rows = steps.map(function (s) {
      var lane;
      if (s.start && s.end && span > 0) {
        var s0 = x(utc(s.start)), s1 = x(utc(s.end, true));
        var w = Math.max(1.2, s1 - s0), label = short(s.start, s.end), inside = w >= 16;
        lane = '<div class="mx-gantt__bar is-' + s.state + '" style="left:' + s0 + "%;width:" + w + '%">' + (inside ? label : "") + "</div>"
          + (inside ? "" : '<span class="mx-gantt__out" style="' + (s0 + w > 78
            ? "right:calc(" + (100 - s0) + "% + 8px)"          // near the right edge: label before the bar
            : "left:calc(" + (s0 + w) + "% + 8px)") + '">' + label + "</span>");
      } else lane = '<span class="mx-gantt__undated">Dates to be confirmed</span>';
      return '<div class="mx-gantt__row"><div class="mx-gantt__name"><b>' + esc(s.label) + '</b><span class="mx-state mx-state--'
        + s.state + '">' + STATE[s.state] + '</span><span class="mx-gantt__mdates" hidden>'
        + (s.start ? day(s.start) + " – " + day(s.end) : "Dates to be confirmed") + '</span></div><div class="mx-gantt__lane">' + lane + "</div></div>";
    }).join("");
    var today = (span > 0 && now >= a && now <= b) ? '<div class="mx-gantt__today" style="' + at(x(now)) + '"><span>Today</span></div>' : "";
    $("mx-gantt").innerHTML = steps.length ? '<div class="mx-gantt__axis" aria-hidden="true">' + axis + "</div>" + rows + today : "";

    renderObjectiveBar();
  }

  // The objective bar: how far the campaign is towards the targets its
  // objective cares about (awareness → views and reach, and so on), with a
  // marker for where it should be by today.
  var KLABEL = { posts: "Posts", views: "Views", reach: "Reach", engagement: "Engagement", er: "Avg ER", clicks: "Clicks" };
  function renderObjectiveBar() {
    var o = R.objective || { label: "Balanced", kpis: [] }, items = (R.progress && R.progress.items) || [];
    var mine = items.filter(function (i) { return (o.kpis || []).indexOf(i.key) >= 0; });
    if (!mine.length) mine = items;
    var box = $("mx-delivery");
    if (!mine.length) {
      box.innerHTML = '<div class="mx-obj"><div class="mx-obj__label"><span>Campaign objective · <b>' + esc(o.label)
        + '</b></span><span class="mx-obj__pct">No targets set yet</span></div></div>';
      return;
    }
    var done = mine.reduce(function (s, i) { return s + Math.min(100, i.pct); }, 0) / mine.length;
    var due = mine.reduce(function (s, i) { return s + Math.min(100, i.expected / i.goal * 100); }, 0) / mine.length;
    var ratio = due ? done / due : 1, g = ratio >= 1 ? "good" : (ratio >= 0.7 ? "moderate" : "low");
    box.innerHTML = '<div class="mx-obj"><div class="mx-obj__label"><span>Campaign objective · <b>' + esc(o.label) + "</b></span>"
      + '<span class="mx-obj__pct"><b>' + Math.round(done) + "%</b> achieved " + sig(g, "Where it should be by today: " + Math.round(due) + "%") + "</span></div>"
      + '<div class="mx-obj__track" role="img" aria-label="' + Math.round(done) + "% of the " + esc(o.label) + ' objective achieved; ' + Math.round(due) + '% expected by today">'
      + '<i class="mx-obj__fill ' + g + '" style="width:' + done.toFixed(1) + '%"></i>'
      + '<i class="mx-obj__due" style="left:' + due.toFixed(1) + '%"><span>today</span></i></div>'
      + '<div class="mx-obj__parts">' + mine.map(function (i) {
        return '<span><span class="mx-sw ' + i.grade + '"></span>' + KLABEL[i.key] + " <b>" + Math.round(i.pct) + "%</b></span>";
      }).join("") + "</div></div>";
  }


  function short(a, b) {
    // "6–10 Sept" when both days share a month, else "28 Sept – 3 Oct"
    var x = new Date(a + "T00:00:00Z"), y = new Date(b + "T00:00:00Z");
    var m = function (d) { return d.toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" }); };
    return x.getUTCMonth() === y.getUTCMonth() ? x.getUTCDate() + "–" + y.getUTCDate() + " " + m(y)
      : x.getUTCDate() + " " + m(x) + " – " + y.getUTCDate() + " " + m(y);
  }

  function renderScoreline() {
    var t = R.total, vis = R.visibility, bm = R.benchmarks, cells = [];
    var g = {}; (R.progress.items || []).forEach(function (i) { g[i.key] = i; });
    function goal(key, val) { var i = g[key]; return i ? sig(i.grade, "Goal " + (key === "er" ? pct(i.goal, 1) : num(i.goal))) : ""; }
    cells.push(["Posts live", full(t.delivered) + (t.planned ? "<small>/" + t.planned + "</small>" : ""), goal("posts"), "posts"]);
    cells.push(["Views", num(t.views), goal("views"), "views"]);
    if (vis.reach && t.reach != null) cells.push(["Reach" + (t.real_share >= 0.999 ? "" : " (est.)"), num(t.reach), goal("reach"), "reach"]);
    cells.push(["Engagement", num(t.engagement), goal("engagement"), "engagement"]);
    cells.push(["Avg eng. rate", pct(t.er), g.er ? goal("er") : sig(t.er_grade, "Against each creator's tier benchmark"), "er"]);
    if (vis.clicks && R.clicks && R.clicks.links && R.clicks.has_destination)
      cells.push(["Link clicks", num(t.clicks), g.clicks ? goal("clicks") : sig(t.ctr_grade, "Strong from " + bm.ctr[0] + "% click-through"), "clicks"]);
    $("mx-scoreline").innerHTML = cells.map(function (c) {
      return "<div><dt>" + (c[3] ? IC[c[3]] : "") + esc(c[0]) + "</dt><dd>" + c[1] + "</dd>" + (c[2] ? "<div class=\"mx-score-line__sig\">" + c[2] + "</div>" : "") + "</div>";
    }).join("");
  }

  /* -------------------------------------------------------------- wall */

  function renderFilters() {
    var posts = R.posts, vis = R.visibility, groups = [];
    function uniq(f) { var s = {}; posts.forEach(function (p) { s[f(p)] = 1; }); return Object.keys(s).sort(); }
    if (vis.all_content) groups.push(["section", [["campaign", "Campaign posts", ""], ["", "All posts", ""]]]);
    var plats = uniq(function (p) { return p.platform; });
    if (plats.length > 1) groups.push(["platform", [["", "All platforms", ""]].concat(plats.map(function (p) { return [p, p, icon(p)]; }))]);
    var kinds = uniq(function (p) { return p.kind; });
    if (kinds.length > 1) groups.push(["kind", [["", "All types", ""]].concat(kinds.map(function (k) { return [k, KIND[k] || k, ""]; }))]);
    $("mx-filters").innerHTML = groups.map(function (g) {
      return '<div class="mx-fgroup">' + g[1].map(function (o) {
        return '<button type="button" class="mx-chip" data-k="' + g[0] + '" data-v="' + esc(o[0]) + '" aria-pressed="'
          + (FILTER[g[0]] === o[0]) + '">' + o[2] + esc(o[1]) + "</button>";
      }).join("") + "</div>";
    }).join("");
  }
  $("mx-filters").addEventListener("click", function (e) {
    var b = e.target.closest(".mx-chip"); if (!b) return;
    FILTER[b.getAttribute("data-k")] = b.getAttribute("data-v");
    renderFilters(); renderWall();
  });

  function healthTitle(h) {
    if (!h || h.value == null || !h.benchmark) return "";
    return h.metric + " " + h.value.toFixed(2) + "% — strong from " + h.benchmark[0] + "%, fair from " + h.benchmark[1] + "%"
      + (h.band ? " for " + (R.benchmarks.bands[h.band] || h.band) + " creators" : "");
  }

  function renderWall() {
    var vis = R.visibility;
    var list = R.posts.filter(function (p) {
      return (!FILTER.section || p.section === FILTER.section) && (!FILTER.platform || p.platform === FILTER.platform)
        && (!FILTER.kind || p.kind === FILTER.kind);
    });
    if (!list.length) { $("mx-wall").innerHTML = '<p class="mx-empty-note">No posts yet. They appear here within 24 hours of going live.</p>'; return; }
    $("mx-wall").innerHTML = list.map(function (p) {
      var est = function (real) { return real ? "" : '<span class="mx-est">est.</span>'; };
      var n = [];
      if (p.video) n.push(["Views", num(p.views)]);
      else if (vis.reach && p.reach != null) n.push(["Reach", num(p.reach) + est(p.reach_real)]);
      if (p.story) { if (vis.reach && p.impressions != null) n.push(["Impressions", num(p.impressions) + est(p.impressions_real)]); }
      else n.push(["Likes", num(p.likes)], ["Comments", num(p.comments)]);
      if (!p.story) n.push([p.video ? "Video ER" : "ER", pct(p.video ? p.video_er : p.er)]);
      if (p.saves) n.push(["Saves", num(p.saves)]);
      if (p.shares) n.push(["Shares", num(p.shares)]);
      var h = p.health || {};
      var img = p.thumb ? '<img src="' + esc(p.thumb) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">' : "";
      return '<article class="mx-post"><div class="mx-post__media"><div class="mx-post__plate">' + icon(p.platform) + "</div>" + img
        + '<span class="mx-post__tag">' + icon(p.platform) + esc(KIND[p.kind] || p.kind) + '</span><span class="mx-post__sig">'
        + sig(h.grade, healthTitle(h)) + '</span></div><div class="mx-post__body"><div class="mx-who">' + ava(p.photo)
        + "<div><b>" + esc(p.creator) + "</b><span>" + esc(day(p.posted_at)) + '</span></div></div><dl class="mx-nums">'
        + n.slice(0, 6).map(function (x) { return "<div><dt>" + x[0] + "</dt><dd>" + x[1] + "</dd></div>"; }).join("")
        + '</dl><a class="mx-post__go" href="' + esc(p.url) + '" target="_blank" rel="noopener">View on ' + esc(p.platform)
        + ' <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17L17 7M9 7h8v8"/></svg></a></div></article>';
    }).join("");
  }

  /* -------------------------------------------------------- leaderboard */

  var MEDAL = { gold: "#d6a52b", silver: "#9ea6ae", bronze: "#b06f3a" };
  function medalBody(b, n) {
    return '<path d="M10 0h8l4 14-6 4z" fill="#ff691e"/><path d="M30 0h-8l-4 14 6 4z" fill="#ee1515"/>'
      + '<circle cx="20" cy="32" r="15" fill="' + MEDAL[b] + '"/><circle cx="20" cy="32" r="11" fill="none" stroke="rgba(255,255,255,.55)" stroke-width="1.5"/>'
      + '<text x="20" y="38" text-anchor="middle" font-family="Bebasneue, Arial, sans-serif" font-size="17" fill="#121212">' + n + "</text>";
  }
  function medal(b, n) {
    return b ? '<svg viewBox="0 0 40 50" role="img" aria-label="' + b + ' medal, rank ' + n + '">' + medalBody(b, n) + "</svg>" : "";
  }
  function profileLinks(c) {
    return (c.profiles || []).filter(function (p) { return p.url; }).map(function (p) {
      return '<a href="' + esc(p.url) + '" target="_blank" rel="noopener" aria-label="' + esc(c.name) + " on " + esc(p.platform) + '">' + icon(p.platform) + "</a>";
    }).join("");
  }
  function creatorLink(c, cls) {
    return '<a class="' + cls + '" href="../creator/#c=' + encodeURIComponent(c.code) + '" title="Open full analysis">' + esc(c.name) + "</a>";
  }

  function renderBoard() {
    var cs = R.creators, vis = R.visibility, bm = R.benchmarks;
    // The (i) says how this campaign's score was weighted.
    var o = R.objective || { label: "Balanced", weights: { exposure: .35, engagement: .25, er: .25, clicks: .15 } }, w = o.weights;
    var info = document.querySelector("#sec-leaderboard .mx-info");
    if (info) info.setAttribute("data-info", "Scored for this campaign's objective: " + o.label + ". Each creator gets a score out of 100 — "
      + Math.round(w.exposure * 100) + "% reach and views (compared with the best in the campaign), "
      + Math.round(w.engagement * 100) + "% engagement (compared with the best), "
      + Math.round(w.er * 100) + "% engagement rate against the benchmark for creators of their size, and "
      + Math.round(w.clicks * 100) + "% affiliate clicks (compared with the best). The top three get gold, silver and bronze; creators who have not posted yet are listed last.");
    var tag = $("mx-objective");
    if (tag) tag.textContent = "Scored for " + o.label;
    var ranked = cs.filter(function (c) { return c.rank; });
    $("mx-podium").innerHTML = ranked.slice(0, 3).map(function (c) {
      return '<div class="mx-pod mx-pod--' + c.rank + '" style="--medal:' + MEDAL[c.badge] + '"><svg class="mx-medal" viewBox="0 0 40 50" aria-hidden="true">'
        + medalBody(c.badge, c.rank) + "</svg>"
        + (c.photo ? '<img class="mx-pod__photo" src="' + esc(c.photo) + '" alt="">' : '<span class="mx-pod__photo"></span>')
        + '<div class="mx-pod__name">' + creatorLink(c, "") + '</div><div class="mx-pod__score">' + c.score.toFixed(0)
        + "<small>score out of 100</small></div><div class=\"mx-pod__line\">" + num((c.views || 0) + (c.reach || 0)) + " reached · "
        + num(c.engagement) + " engagements" + (vis.clicks && c.clicks ? " · " + num(c.clicks) + " clicks" : "") + "</div></div>";
    }).join("");
    var head = ["#", "Creator", "Posts", "Views"].concat(vis.reach ? ["Reach"] : []).concat(["Engagement", "Eng. rate"])
      .concat(vis.clicks ? ["Clicks"] : []).concat(["Score"]);
    var rows = cs.map(function (c) {
      var rate = c.er != null ? c.er : c.video_er, g = c.er != null ? c.er_grade : c.video_er_grade;
      var bench = c.er != null ? bm.er[c.band] : bm.video_er;
      var tds = ['<td class="mx-rank">' + (c.badge ? medal(c.badge, c.rank) : (c.rank || "—")) + "</td>",
        '<td><div class="mx-tc">' + ava(c.photo) + "<div>" + creatorLink(c, "mx-tc__name") + '<div class="mx-tc__links">' + profileLinks(c) + "</div></div></div></td>",
        "<td>" + c.delivered + (c.planned ? " / " + c.planned : "") + "</td>", "<td>" + full(c.views) + "</td>"];
      if (vis.reach) tds.push("<td>" + full(c.reach) + "</td>");
      tds.push("<td>" + full(c.engagement) + "</td>",
        "<td>" + pct(rate) + "</td>");
      if (vis.clicks) tds.push("<td>" + full(c.clicks) + "</td>");
      tds.push('<td><span class="mx-score"><i style="--w:' + c.score + '%"></i>' + c.score.toFixed(0) + "</span></td>");
      return "<tr>" + tds.join("") + "</tr>";
    }).join("");
    $("mx-table").innerHTML = "<thead><tr>" + head.map(function (h) { return "<th>" + h + "</th>"; }).join("") + "</tr></thead><tbody>" + rows + "</tbody>";
  }

  /* ---------------------------------------------------------- targets */

  var TLABEL = { posts: "Posts", views: "Views", reach: "Reach", engagement: "Engagement", er: "Avg ER", clicks: "Affiliate clicks" };
  function renderTargets() {
    var p = R.progress || { items: [] }, bm = R.benchmarks, t = R.total;
    var ran = Math.round((p.elapsed || 0) * 100);
    $("mx-targets-lede").textContent = p.items.length
      ? ""
      : "";
    $("mx-bullets").innerHTML = p.items.length ? p.items.map(function (i) {
      var isRate = i.key === "er", fill = Math.min(100, i.pct), mark = Math.min(100, i.expected / i.goal * 100);
      return '<div class="mx-bullet"><div class="mx-bullet__name">' + (IC[i.key] || "") + TLABEL[i.key] + " " + sig(i.grade) + "</div>"
        + '<div class="mx-bullet__track" role="img" aria-label="' + TLABEL[i.key] + " " + Math.round(i.pct) + '% of goal">'
        + '<div class="mx-bullet__fill ' + i.grade + '" style="width:' + fill + '%"></div>'
        + (isRate ? "" : '<div class="mx-bullet__mark" style="left:' + mark + '%"><span>by today</span></div>') + "</div>"
        + '<div class="mx-bullet__num"><b>' + (isRate ? pct(i.actual) : num(i.actual)) + "</b>of " + (isRate ? pct(i.goal, 1) : num(i.goal)) + " goal</div></div>";
    }).join("") : "";
    var ex = [];
    ex.push(["Engagement rate", t.er, t.er_grade, "Strong from " + bm.er.micro[0] + "% (micro creators)"]);
    if (t.video_er != null) ex.push(["Video engagement", t.video_er, t.video_er_grade, "Strong from " + bm.video_er[0] + "%"]);
    if (R.visibility.clicks && t.ctr != null && R.clicks && R.clicks.links) ex.push(["Click-through", t.ctr, t.ctr_grade, "Strong from " + bm.ctr[0] + "%"]);
    $("mx-bench").innerHTML = ex.map(function (x) {
      return '<div class="mx-bench__item"><h3>' + h3ic(x[0]) + x[0] + '</h3><div class="mx-bench__val">' + pct(x[1]) + " " + sig(x[2]) + "</div><p>" + x[3] + "</p></div>";
    }).join("");
  }

  /* ----------------------------------------------------------- charts */

  function area(points, key, colour, label) {
    var W = 560, H = 210, L = 46, Rr = 10, T = 12, B = 28, pw = W - L - Rr, ph = H - T - B;
    var peak = Math.max.apply(null, points.map(function (d) { return d[key]; }).concat([1]));
    var mag = Math.pow(10, Math.floor(Math.log10(peak))), top = Math.ceil(peak / mag) * mag;
    function x(i) { return L + (points.length === 1 ? pw / 2 : pw * i / (points.length - 1)); }
    function y(v) { return T + ph - v / top * ph; }
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc(label) + '">';
    for (var g = 0; g <= 3; g++) {
      var yy = y(top * g / 3).toFixed(1);
      s += '<line x1="' + L + '" x2="' + (W - Rr) + '" y1="' + yy + '" y2="' + yy + '" stroke="#ece6dc"/>'
        + '<text x="' + (L - 8) + '" y="' + (+yy + 4) + '" text-anchor="end" font-size="12" fill="#5a5a5a">' + num(top * g / 3) + "</text>";
    }
    var line = points.map(function (d, i) { return x(i).toFixed(1) + "," + y(d[key]).toFixed(1); });
    s += '<path d="M' + x(0).toFixed(1) + "," + (T + ph) + " L" + line.join(" L") + " L" + x(points.length - 1).toFixed(1) + "," + (T + ph)
      + ' Z" fill="' + colour + '" opacity=".16"/><polyline fill="none" stroke="' + colour + '" stroke-width="3" stroke-linejoin="round" points="' + line.join(" ") + '"/>';
    var every = Math.max(1, Math.ceil(points.length / 6));
    points.forEach(function (d, i) {
      if (i % every && i !== points.length - 1) return;
      var anchor = i === 0 ? "start" : (i === points.length - 1 ? "end" : "middle");
      s += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 8) + '" text-anchor="' + anchor + '" font-size="12" fill="#5a5a5a">' + esc(day(d.d, false)) + "</text>";
    });
    var last = points[points.length - 1];
    s += '<circle cx="' + x(points.length - 1).toFixed(1) + '" cy="' + y(last[key]).toFixed(1) + '" r="5" fill="' + colour + '"/>';
    return s + "</svg>";
  }

  // Bars take turns through the brand's colours rather than all ink:
  // green, orange, lime, then a warm grey — the order repeats.
  var PALETTE = ["#14884a", "#ff691e", "#b9d400", "#8a7a68"];
  function bars(rows, keyHtml) {
    if (!rows || !rows.length) return '<p class="mx-panel__note">Nothing yet.</p>';
    var peak = Math.max.apply(null, rows.map(function (r) { return r.n; })) || 1;
    return rows.slice(0, 8).map(function (r, i) {
      return '<div class="mx-bar"><span class="mx-bar__k">' + keyHtml(r) + '</span><i style="--w:' + (r.n / peak * 100).toFixed(1)
        + "%;--c:" + PALETTE[i % PALETTE.length] + '"></i><b>' + r.label + "</b></div>";
    }).join("");
  }

  function renderCharts() {
    var h = (R.history || []).map(function (d) { return { d: d.d, views: d.views, eng: d.likes + d.comments }; });
    $("mx-charts").innerHTML = h.length
      ? '<div class="mx-chart"><h3>' + IC.views + 'Views so far</h3>' + area(h, "views", "#14884a", "Views so far") + "</div>"
        + '<div class="mx-chart"><h3>' + IC.engagement + 'Engagement so far</h3>' + area(h, "eng", "#ff691e", "Engagement so far") + "</div>"
      : '<p class="mx-empty-note">The charts fill in as posts are captured, once every 24 hours.</p>';

    var posts = R.posts.filter(function (p) { return p.section === "campaign"; }), mix = [];
    var byPlat = {}, byKind = {};
    posts.forEach(function (p) {
      var a = byPlat[p.platform] = byPlat[p.platform] || { n: 0, x: 0 }; a.n++; a.x += (p.views || 0) + (p.reach || 0);
      byKind[p.kind] = (byKind[p.kind] || 0) + 1;
    });
    var plats = Object.keys(byPlat).map(function (k) { return { k: k, n: byPlat[k].x || byPlat[k].n, label: num(byPlat[k].x) }; })
      .sort(function (a, b) { return b.n - a.n; });
    if (plats.length) mix.push('<div class="mx-panel"><h3>Reached by platform</h3>' + bars(plats, function (r) { return icon(r.k) + esc(r.k); }) + "</div>");
    var kinds = Object.keys(byKind).map(function (k) { return { k: k, n: byKind[k], label: byKind[k] + (byKind[k] === 1 ? " post" : " posts") }; })
      .sort(function (a, b) { return b.n - a.n; });
    if (kinds.length) mix.push('<div class="mx-panel"><h3>Content mix</h3>' + bars(kinds, function (r) { return esc(KIND[r.k] || r.k); }) + "</div>");
    var t = R.total, parts = [["Likes", t.likes, "#14884a"], ["Comments", t.comments, "#ff691e"], ["Saves", t.saves, "#b9d400"], ["Shares", t.shares, "#8a7a68"]]
      .filter(function (p) { return p[1]; });
    var sum = parts.reduce(function (s, p) { return s + p[1]; }, 0);
    if (sum) mix.push('<div class="mx-panel"><h3>What people did</h3><div class="mx-stack" role="img" aria-label="Interactions breakdown">'
      + parts.map(function (p) { return '<i style="width:' + (p[1] / sum * 100) + "%;background:" + p[2] + '"></i>'; }).join("")
      + '</div><div class="mx-key">' + parts.map(function (p) {
        return '<div><span class="mx-sw" style="background:' + p[2] + '"></span>' + p[0] + "<b>" + full(p[1]) + "</b></div>";
      }).join("") + "</div></div>");
    if (R.audience && R.audience.countries.length) {
      mix.push('<div class="mx-panel"><h3>Who was reached</h3>' + bars(R.audience.countries.map(function (c) {
        return { k: c.code, n: c.pct, label: c.pct.toFixed(0) + "%" };
      }), function (r) { return flag(r.k) + esc(countryName(r.k)); })
        + '<p class="mx-panel__note">Weighted by reach' + (R.audience.coverage < 99 ? " · " + R.audience.coverage.toFixed(0) + "% of reach covered" : "") + "</p></div>");
    }
    $("mx-mix").innerHTML = mix.join("");
    decorateH3("mx-mix");
  }

  /* ----------------------------------------------------------- clicks */

  function renderClicks() {
    var vis = R.visibility, cl = R.clicks;
    $("sec-clicks").hidden = !vis.clicks;
    if (!vis.clicks) return;
    if (!cl || !cl.links || !cl.has_destination) {
      $("mx-clicks").innerHTML = '<p class="mx-empty-note">No affiliate links in this campaign.</p>';
      return;
    }
    var t = R.total;
    var heads = '<dl class="mx-clickheads"><div><dt>' + IC.clicks + 'Clicks</dt><dd>' + full(cl.clicks) + '</dd></div><div><dt>' + IC.unique + 'Unique people</dt><dd>'
      + full(cl.uniques) + '</dd></div><div><dt>' + IC.ctr + 'Click-through</dt><dd>' + pct(t.ctr) + "</dd></div></dl>";
    if (!cl.clicks) { $("mx-clicks").innerHTML = heads + '<p class="mx-empty-note" style="margin-top:18px">No clicks yet.</p>'; return; }
    var lab = function (rows) { return (rows || []).map(function (r) { return { k: r.k, n: r.n, label: full(r.n) }; }); };
    $("mx-clicks").innerHTML = heads + '<div class="mx-clickgrid">'
      + '<div class="mx-panel"><h3>By creator</h3>' + bars(lab(cl.by_creator), function (r) { return esc(r.k); }) + "</div>"
      + '<div class="mx-panel"><h3>By app</h3>' + bars(lab(cl.by_app), function (r) { return (ICONS[r.k] || "") + esc(r.k); }) + "</div>"
      + '<div class="mx-panel"><h3>By country</h3>' + bars(lab(cl.by_country), function (r) {
        return r.k && r.k.length === 2 ? flag(r.k) + esc(countryName(r.k)) : esc(r.k || "Unknown");
      }) + "</div>"
      + '<div class="mx-panel"><h3>By device</h3>' + bars(lab(cl.by_device), function (r) { return esc(r.k); }) + "</div></div>";
    decorateH3("mx-clicks");
  }

  function decorateH3(id) {
    var box = $(id); if (!box) return;
    box.querySelectorAll(".mx-panel > h3").forEach(function (h) {
      if (!h.querySelector(".mx-ico")) h.insertAdjacentHTML("afterbegin", h3ic(h.textContent.trim()));
    });
  }

  $("mx-print").addEventListener("click", function () { window.print(); });
  route();
})();
