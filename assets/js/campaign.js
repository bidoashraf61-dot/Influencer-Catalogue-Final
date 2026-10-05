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
    $("mx-list-items").innerHTML = list.map(function (c) {
      return '<a class="mx-camp" href="#t=' + esc(c.token) + '"><div class="mx-camp__logos">'
        + (c.logos || []).map(function (u) { return '<img src="' + esc(u) + '" alt="">'; }).join("") + "</div>"
        + '<div><div class="mx-camp__name">' + esc(c.name) + '</div><div class="mx-camp__meta">'
        + esc([c.client, c.starts_at ? day(c.starts_at) + " – " + day(c.ends_at) : "", c.status === "live" ? "Live" : "Completed"].filter(Boolean).join(" · "))
        + '</div></div><span class="mx-camp__go">Open report →</span></a>';
    }).join("");
    show("list");
    window.scrollTo(0, 0);
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

  /* ------------------------------------------------------ section jump bar */

  // Every section is on the page; the bar only scrolls to one. It must not
  // touch the URL hash, which carries the report token.
  var SECS = ["overview", "leaderboard", "content", "performance", "clicks", "timeline"];
  var LOCK = 0;
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
    cells.push(["Posts live", full(t.delivered) + (t.planned ? "<small>/" + t.planned + "</small>" : ""), goal("posts")]);
    cells.push(["Views", num(t.views), goal("views")]);
    if (vis.reach && t.reach != null) cells.push(["Reach" + (t.real_share >= 0.999 ? "" : " (est.)"), num(t.reach), goal("reach")]);
    cells.push(["Engagement", num(t.engagement), goal("engagement")]);
    cells.push(["Avg eng. rate", pct(t.er), g.er ? goal("er") : sig(t.er_grade, "Against each creator's tier benchmark")]);
    if (vis.clicks && R.clicks && R.clicks.links && R.clicks.has_destination)
      cells.push(["Link clicks", num(t.clicks), g.clicks ? goal("clicks") : sig(t.ctr_grade, "Strong from " + bm.ctr[0] + "% click-through")]);
    $("mx-scoreline").innerHTML = cells.map(function (c) {
      return "<div><dt>" + esc(c[0]) + "</dt><dd>" + c[1] + "</dd>" + (c[2] ? "<div class=\"mx-score-line__sig\">" + c[2] + "</div>" : "") + "</div>";
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
        "<td>" + pct(rate) + " " + sig(g, bench ? "Strong from " + bench[0] + "%, fair from " + bench[1] + "% (" + (R.benchmarks.bands[c.band] || "") + ")" : "") + "</td>");
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
      ? "Line = where it should be today (" + ran + "% of the campaign has run)."
      : "";
    $("mx-bullets").innerHTML = p.items.length ? p.items.map(function (i) {
      var isRate = i.key === "er", fill = Math.min(100, i.pct), mark = Math.min(100, i.expected / i.goal * 100);
      return '<div class="mx-bullet"><div class="mx-bullet__name">' + TLABEL[i.key] + " " + sig(i.grade) + "</div>"
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
      return '<div class="mx-bench__item"><h3>' + x[0] + '</h3><div class="mx-bench__val">' + pct(x[1]) + " " + sig(x[2]) + "</div><p>" + x[3] + "</p></div>";
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

  // Data colours are the brand pair, so they never compete with the green /
  // amber / red verdicts: ink = people who saw it, lime = what people did.
  // These two sections sit on black: white = people who saw it, lime = what
  // people did.
  var C1 = "#ffffff", C2 = "#e8ff76";
  function bars(rows, keyHtml, colour) {
    if (!rows || !rows.length) return '<p class="mx-panel__note">Nothing yet.</p>';
    var peak = Math.max.apply(null, rows.map(function (r) { return r.n; })) || 1;
    return rows.slice(0, 8).map(function (r) {
      return '<div class="mx-bar"><span class="mx-bar__k">' + keyHtml(r) + '</span><i style="--w:' + (r.n / peak * 100).toFixed(1)
        + "%;--c:" + (colour || C1) + '"></i><b>' + r.label + "</b></div>";
    }).join("");
  }

  // Drawn marks for formats, actions and devices, one stroke weight.
  var G = function (d) { return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + d + "</svg>"; };
  var MARK = {
    reel: G('<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 9h18M8 4l2.5 5M14 4l2.5 5"/><path d="M10.5 12.5v4l3.5-2z"/>'),
    story: G('<circle cx="12" cy="12" r="8.5" stroke-dasharray="3.4 2.2"/><circle cx="12" cy="12" r="4.5"/>'),
    post: G('<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><circle cx="9" cy="9" r="1.8"/><path d="M20.5 15l-5-5-11 10.5"/>'),
    video: G('<rect x="2.5" y="5" width="19" height="14" rx="3"/><path d="M10 9.3l5 2.7-5 2.7z"/>'),
    short: G('<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 9.5l3 2-3 2z"/>'),
    likes: G('<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>'),
    comments: G('<path d="M20 12a7.5 7.5 0 0 1-11 6.6L4 20l1.4-4.4A7.5 7.5 0 1 1 20 12z"/>'),
    saves: G('<path d="M7 3.5h10a1 1 0 0 1 1 1V21l-6-4-6 4V4.5a1 1 0 0 1 1-1z"/>'),
    shares: G('<path d="M21 3L10 14M21 3l-7 18-4-7-7-4z"/>'),
    views: G('<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>'),
    clicks: G('<path d="M9 3.5v4M3.5 9h4M5 5l2.5 2.5M13 13l7 3-3 1-1 3z"/>'),
    Mobile: G('<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/>'),
    Desktop: G('<rect x="2.5" y="4" width="19" height="13" rx="2"/><path d="M8.5 21h7M12 17v4"/>'),
    Tablet: G('<rect x="4" y="2.5" width="16" height="19" rx="2.5"/><path d="M11 18.5h2"/>')
  };
  function tiles(items) {
    return '<div class="mx-tiles">' + items.map(function (t) {
      return '<div class="mx-tile mx-tile--' + (t.tone || "seen") + '"><span class="mx-tile__ic">' + t.icon + "</span><b>" + t.value + "</b><span>" + esc(t.label)
        + (t.sub ? "<small>" + esc(t.sub) + "</small>" : "") + "</span></div>";
    }).join("") + "</div>";
  }

  function renderCharts() {
    var h = (R.history || []).map(function (d) { return { d: d.d, views: d.views, eng: d.likes + d.comments }; });
    $("mx-charts").innerHTML = h.length
      ? '<div class="mx-chart"><h3>Views so far</h3>' + area(h, "views", "#ffffff", "Views so far") + "</div>"
        + '<div class="mx-chart"><h3>Engagement so far</h3>' + area(h, "eng", "#e8ff76", "Engagement so far") + "</div>"
      : '<p class="mx-empty-note">The charts fill in as posts are captured, once every 24 hours.</p>';

    var posts = R.posts.filter(function (p) { return p.section === "campaign"; }), mix = [], t = R.total;
    // per post, and the best post
    var n = posts.length || 1, vids = posts.filter(function (p) { return p.video; });
    mix.push('<div class="mx-panel"><h3>Per post</h3>' + tiles([
      { icon: MARK.views, value: num(vids.length ? t.views / vids.length : 0), label: "Views per video", tone: "seen" },
      { icon: MARK.likes, value: num(t.engagement / n), label: "Engagement per post", tone: "did" },
      { icon: MARK.post, value: num(posts.length), label: "Posts counted", tone: "plain" }
    ]) + "</div>");
    // reached by platform (green bars)
    var byPlat = {}, byKind = {};
    posts.forEach(function (p) {
      var a2 = byPlat[p.platform] = byPlat[p.platform] || { n: 0, x: 0 }; a2.n++; a2.x += (p.views || 0) + (p.reach || 0);
      var k = byKind[p.kind] = byKind[p.kind] || { n: 0, x: 0 }; k.n++; k.x += (p.views || 0) + (p.reach || 0);
    });
    var plats = Object.keys(byPlat).map(function (k) { return { k: k, n: byPlat[k].x || byPlat[k].n, label: num(byPlat[k].x) }; })
      .sort(function (a2, b2) { return b2.n - a2.n; });
    if (plats.length) mix.push('<div class="mx-panel"><h3>Reached by platform</h3>' + bars(plats, function (r) { return icon(r.k) + esc(r.k); }) + "</div>");
    // content mix: icon tiles
    var kinds = Object.keys(byKind).sort(function (a2, b2) { return byKind[b2].n - byKind[a2].n; });
    if (kinds.length) mix.push('<div class="mx-panel"><h3>Content mix</h3>' + tiles(kinds.map(function (k) {
      return { icon: MARK[k] || MARK.post, value: byKind[k].n, label: byKind[k].n === 1 ? (KIND[k] || k) : (PLURAL[k] || (KIND[k] || k) + "s"), tone: "plain" };
    })) + "</div>");
    // what people did: icon tiles
    var acts = [["likes", "Likes", t.likes], ["comments", "Comments", t.comments], ["saves", "Saves", t.saves], ["shares", "Shares", t.shares]]
      .filter(function (x) { return x[2]; });
    if (acts.length) mix.push('<div class="mx-panel"><h3>What people did</h3>' + tiles(acts.map(function (x, i) {
      return { icon: MARK[x[0]], value: num(x[2]), label: x[1], tone: "did" };
    })) + "</div>");
    // reach by creator size
    var bySize = {};
    R.creators.forEach(function (c) { if (!c.posts) return; var b2 = c.band || "nano"; bySize[b2] = (bySize[b2] || 0) + (c.views || 0) + (c.reach || 0); });
    var sizes = ["mega", "macro", "mid", "micro", "nano"].filter(function (k) { return bySize[k]; })
      .map(function (k) { return { k: k, n: bySize[k], label: num(bySize[k]) }; });
    if (sizes.length > 1) mix.push('<div class="mx-panel"><h3>Reached by creator size</h3>' + bars(sizes, function (r) { return esc((R.benchmarks.bands[r.k] || r.k).replace(/ \(.*/, "")); }) + "</div>");
    if (R.audience && R.audience.countries.length) {
      mix.push('<div class="mx-panel"><h3>Who was reached</h3>' + bars(R.audience.countries.map(function (c) {
        return { k: c.code, n: c.pct, label: c.pct.toFixed(0) + "%" };
      }), function (r) { return flag(r.k) + esc(countryName(r.k)); })
        + '<p class="mx-panel__note">Weighted by reach' + (R.audience.coverage < 99 ? " · " + R.audience.coverage.toFixed(0) + "% of reach covered" : "") + "</p></div>");
    }
    $("mx-mix").innerHTML = '<p class="mx-key-line"><span><i class="seen"></i><b class="k-screen">White</b><b class="k-print">Black</b> — people who saw it (views, reach)</span>'
      + '<span><i class="did"></i>Lime — what people did (likes, comments, saves, shares, clicks)</span></p>' + mix.join("");
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
    var heads = tiles([{ icon: MARK.clicks, value: full(cl.clicks), label: "Clicks", tone: "did" },
      { icon: MARK.views, value: full(cl.uniques), label: "Unique people", tone: "did" },
      { icon: G('<path d="M4 20L20 4M7 4h13v13"/>'), value: pct(t.ctr), label: "Click-through", sub: t.ctr != null ? (SIG[t.ctr_grade] || "") : "", tone: "did" }]);
    if (!cl.clicks) { $("mx-clicks").innerHTML = heads + '<p class="mx-empty-note" style="margin-top:18px">No clicks yet.</p>'; return; }
    var lab = function (rows) { return (rows || []).map(function (r) { return { k: r.k, n: r.n, label: full(r.n) }; }); };
    $("mx-clicks").innerHTML = heads + '<div class="mx-clickgrid">'
      + '<div class="mx-panel"><h3>By creator</h3>' + bars(lab(cl.by_creator), function (r) { return esc(r.k); }, C2) + "</div>"
      + '<div class="mx-panel"><h3>By app</h3>' + tiles((cl.by_app || []).slice(0, 6).map(function (r) {
        return { icon: ICONS[r.k] || MARK.clicks, value: full(r.n), label: r.k, tone: "did" };
      })) + "</div>"
      + '<div class="mx-panel"><h3>By country</h3>' + bars(lab(cl.by_country), function (r) {
        return r.k && r.k.length === 2 ? flag(r.k) + esc(countryName(r.k)) : esc(r.k || "Unknown");
      }, C2) + "</div>"
      + '<div class="mx-panel"><h3>By device</h3>' + tiles((cl.by_device || []).map(function (r) {
        return { icon: MARK[r.k] || MARK.Mobile, value: full(r.n), label: r.k, tone: "did" };
      })) + "</div></div>";
  }

  $("mx-print").addEventListener("click", function () { window.print(); });
  route();
})();
