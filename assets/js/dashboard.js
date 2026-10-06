/* Campaign dashboard — the client's campaign on one screen. Same data as the
   long report (GET /api/campaign?t=<token>); filters (platform, dates,
   creators) are applied here in the browser and every card recalculates.
   Targets, verdict and audience are whole-campaign by nature and say so. */
(function () {
  "use strict";

  var API = (window.CAMPAIGN_CONFIG || {}).api || "/admin";
  var ICONS = (window.HV_ICONS || {}).icons || {};
  var LINK = (window.HV_ICONS || {}).link || "";
  var R = null, TOKEN = "";
  var F = { platform: "", range: "all", from: "", to: "", creators: [] };
  var ONE = { post: "Photo", reel: "Reel", story: "Story", video: "Video", short: "Short" };
  var KIND = { post: "Photo posts", reel: "Reels", story: "Stories", video: "Videos", short: "Shorts" };
  var COL = ["#14884a", "#ff691e", "#b9d400", "#8a7a68", "#121212"];
  var SIG = { good: "Strong", moderate: "Fair", low: "Low" };
  var countryName = (function () {
    try { var d = new Intl.DisplayNames(["en"], { type: "region" }); return function (c) { return d.of(c) || c; }; }
    catch (e) { return function (c) { return c; }; }
  })();

  function $(id) { return document.getElementById(id); }
  function esc(v) { return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function num(v) {
    if (v == null) return "—";
    var n = Math.round(v), a = Math.abs(n);
    if (a >= 1e6) return (n / 1e6).toFixed(a >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
    if (a >= 1e4) return (n / 1e3).toFixed(a >= 1e5 ? 0 : 1).replace(/\.0$/, "") + "K";
    return n.toLocaleString("en-US");
  }
  function full(v) { return v == null ? "—" : Math.round(v).toLocaleString("en-US"); }
  function pct(v, d) { return v == null || isNaN(v) ? "—" : v.toFixed(d == null ? 2 : d) + "%"; }
  function day(t, y) { if (!t) return ""; var d = typeof t === "number" ? new Date(t * 1000) : new Date(t + "T00:00:00Z");
    return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: y ? "numeric" : undefined, timeZone: "UTC" }); }
  function ago(t) { if (!t) return ""; var s = Date.now() / 1000 - t; return s < 3600 ? Math.max(1, Math.round(s / 60)) + " min ago" : s < 86400 ? Math.round(s / 3600) + " h ago" : Math.round(s / 86400) + " days ago"; }
  function sig(g, tip) { return '<span class="db-sig db-sig--' + (SIG[g] ? g : "none") + '"' + (tip ? ' title="' + esc(tip) + '"' : "") + ">" + (SIG[g] || "—") + "</span>"; }
  function flag(cc) { return '<span class="fi fi-' + esc(String(cc).toLowerCase()) + '" aria-hidden="true"></span>'; }
  function ava(p) { return p ? '<img src="' + esc(p) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : '<span class="db-ava"></span>'; }
  function ico(d) { return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + d + "</svg>"; }
  var IC = {
    posts: ico('<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><path d="M8 12.5l3 3 5-6"/>'),
    views: ico('<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>'),
    reach: ico('<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4.5-6.2"/>'),
    engagement: ico('<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>'),
    er: ico('<path d="M19 5L5 19"/><circle cx="7" cy="7" r="2.5"/><circle cx="17" cy="17" r="2.5"/>'),
    clicks: ico('<path d="M9 3.5v4M3.5 9h4M5 5l2.5 2.5"/><path d="M12 12l8 3-3.5 1.5L15 20z"/>'),
    trend: ico('<path d="M3 20h18"/><path d="M4 16l5-6 4 3 7-8"/>'),
    top: ico('<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M7 6H4a3 3 0 0 0 3 4M17 6h3a3 3 0 0 1-3 4"/>'),
    stage: ico('<rect x="3.5" y="4.5" width="17" height="16" rx="2.5"/><path d="M8 2.5v4M16 2.5v4M3.5 10h17M8 14h3M13 17h3"/>'),
    mix: ico('<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>'),
    geo: ico('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>'),
    plat: ico('<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/>'),
    img: ico('<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><circle cx="9" cy="9" r="1.8"/><path d="M20.5 15l-5-5-11 10.5"/>'),
    goal: ico('<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1"/>')
  };
  function token() { var m = /(?:^|[#&])t=([A-Za-z0-9_-]+)/.exec(location.hash || ""); return m ? m[1] : ""; }
  function get(path) { return fetch(API + path, { credentials: "include", cache: "no-store" }).then(function (r) { if (r.status === 401) throw { locked: true }; if (!r.ok) throw {}; return r.json(); }); }

  /* --------------------------------------------------------------- gate */
  function lock(msg) { $("cat-app").hidden = true; $("cat-gate").hidden = false; if (msg) { $("cat-gate-error").textContent = msg; $("cat-gate-error").hidden = false; } }
  $("cat-gate-form").addEventListener("submit", function (e) {
    e.preventDefault();
    fetch(API + "/api/unlock", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: $("cat-code").value.trim(), lite: true }) })
      .then(function (r) { return r.json(); })
      .then(function (b) { if (!b || !b.ok) lock("That code is not right."); else { $("cat-code").value = ""; load(); } })
      .catch(function () { lock("Could not reach the server. Please try again."); });
  });

  function load() {
    TOKEN = token();
    // No campaign named: one campaign opens straight away; several go to the
    // "My campaigns" list, whose cards come back here.
    var go = TOKEN ? Promise.resolve(TOKEN) : get("/api/campaigns").then(function (b) {
      var l = b.campaigns || [];
      if (l.length !== 1) { location.replace("../#list"); throw { moved: true }; }
      location.replace("#t=" + l[0].token); return l[0].token; });
    get("/api/campaigns").then(function (b) { $("db-all").hidden = (b.campaigns || []).length < 2; }).catch(function () {});
    go.then(function (t) { TOKEN = t; return get("/api/campaign?t=" + encodeURIComponent(t)); })
      .then(function (b) {
        R = b.report;
        $("cat-gate").hidden = true; $("cat-app").hidden = false; document.body.classList.remove("cat-locked");
        setupHeader(); setupFilters(); renderAll();
      })
      .catch(function (err) {
        if (err && err.locked) return lock();
        if (err && err.moved) return;
        $("cat-gate").hidden = true; $("db-empty").hidden = false;
        $("db-empty").textContent = err && err.none ? "No campaign reports for this access code yet." : "This campaign is not available with your access code.";
      });
  }

  /* ------------------------------------------------------------- header */
  function setupHeader() {
    var c = R.campaign;
    document.title = c.name + " — Dashboard — HelloVoice";
    $("db-title").textContent = c.name;
    var logos = (c.logos || []).map(function (u) { return '<img src="' + esc(u) + '" alt="">'; }).join("");
    $("db-brands").innerHTML = logos ? logos + "<span>×</span>" : "";
    var now = Date.now() / 1000, bits = [];
    if (c.status === "live") bits.push('<span class="db-live">LIVE</span>');
    if (c.starts_at && c.ends_at) {
      var total = Math.max(1, Math.round((c.ends_at - c.starts_at) / 86400)), dn = Math.min(total, Math.max(1, Math.ceil((now - c.starts_at) / 86400)));
      bits.push(now < c.starts_at ? "Starts " + day(c.starts_at) : now <= c.ends_at ? "Day " + dn + " of " + total : "Ran " + total + " days");
      bits.push(day(c.starts_at) + " – " + day(c.ends_at, true));
    }
    if (c.client) bits.unshift(esc(c.client));
    $("db-sub").innerHTML = bits.join(" · ");
    var v = R.verdict || {};
    $("db-verdict").innerHTML = v.label ? '<span class="db-verdict' + (v.grade ? " db-verdict--" + v.grade : "") + '" role="status" title="How the campaign is doing against its targets today">' + esc(v.label) + "</span>" : "";
    $("db-report").href = "../#t=" + TOKEN;
    $("db-pdf").href = "../#t=" + TOKEN;
    $("db-pdf").addEventListener("click", function () { try { sessionStorage.setItem("hv_print", "1"); } catch (e) {} });
    $("db-fresh").textContent = "Updated every 24 hours" + (R.updated_at ? " · last " + ago(R.updated_at) : "");
  }

  /* ------------------------------------------------------------ filters */
  function setupFilters() {
    var plats = {}; R.posts.forEach(function (p) { plats[p.platform] = 1; });
    var list = Object.keys(plats).sort();
    $("db-platforms").innerHTML = ['<button type="button" data-p="" aria-pressed="true">All</button>'].concat(list.map(function (p) {
      return '<button type="button" data-p="' + esc(p) + '" aria-pressed="false">' + (ICONS[p] || "") + esc(p) + "</button>";
    })).join("");
    $("db-platforms").addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      F.platform = b.getAttribute("data-p");
      [].forEach.call(this.children, function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
      renderAll();
    });
    $("db-range").addEventListener("change", function () {
      F.range = this.value; $("db-custom").hidden = F.range !== "custom"; renderAll();
    });
    ["db-from", "db-to"].forEach(function (id) { $(id).addEventListener("change", function () { F.from = $("db-from").value; F.to = $("db-to").value; renderAll(); }); });
    $("db-creators").innerHTML = R.creators.map(function (c) {
      return '<label><input type="checkbox" value="' + esc(c.code) + '">' + ava(c.photo) + esc(c.name) + "</label>";
    }).join("");
    $("db-creators-btn").addEventListener("click", function () {
      var m = $("db-creators"), open = m.hidden; m.hidden = !open; this.setAttribute("aria-expanded", open ? "true" : "false");
    });
    $("db-creators").addEventListener("change", function () {
      F.creators = [].map.call(this.querySelectorAll("input:checked"), function (i) { return i.value; });
      $("db-creators-btn").textContent = F.creators.length ? F.creators.length + (F.creators.length === 1 ? " creator" : " creators") : "All creators";
      $("db-creators-btn").classList.toggle("is-on", !!F.creators.length);
      renderAll();
    });
    document.addEventListener("click", function (e) { if (!e.target.closest(".db-pick")) { $("db-creators").hidden = true; $("db-creators-btn").setAttribute("aria-expanded", "false"); } });
    $("db-reset").addEventListener("click", function () {
      F = { platform: "", range: "all", from: "", to: "", creators: [] };
      [].forEach.call($("db-platforms").children, function (x, i) { x.setAttribute("aria-pressed", i === 0 ? "true" : "false"); });
      $("db-range").value = "all"; $("db-custom").hidden = true;
      [].forEach.call($("db-creators").querySelectorAll("input"), function (i) { i.checked = false; });
      $("db-creators-btn").textContent = "All creators"; $("db-creators-btn").classList.remove("is-on");
      renderAll();
    });
  }
  function filtered() { return !!(F.platform || F.range !== "all" || F.creators.length); }
  function inRange(t) {
    if (!t) return F.range === "all";
    if (F.range === "all") return true;
    if (F.range === "custom") {
      var a = F.from ? Date.parse(F.from + "T00:00:00Z") / 1000 : 0, b = F.to ? Date.parse(F.to + "T23:59:59Z") / 1000 : Infinity;
      return t >= a && t <= b;
    }
    return t >= Date.now() / 1000 - parseInt(F.range, 10) * 86400;
  }
  function posts() {
    return R.posts.filter(function (p) {
      return p.section === "campaign" && (!F.platform || p.platform === F.platform) && (!F.creators.length || F.creators.indexOf(p.code) >= 0) && inRange(p.posted_at);
    });
  }
  function sums(list) {
    var t = { posts: list.length, views: 0, reach: 0, engagement: 0, likes: 0, comments: 0, saves: 0, shares: 0, er: null };
    var ers = [];
    list.forEach(function (p) {
      t.views += p.views || 0; t.reach += p.reach || 0; t.engagement += p.engagement || 0; t.likes += p.likes || 0;
      t.comments += p.comments || 0; t.saves += p.saves || 0; t.shares += p.shares || 0;
      var r = p.video ? p.video_er : p.er; if (r != null) ers.push(r);
    });
    if (ers.length) t.er = ers.reduce(function (a, b) { return a + b; }, 0) / ers.length;
    return t;
  }
  function clicksFor() {
    var cl = R.clicks; if (!cl || !cl.links || !cl.has_destination) return null;
    if (!F.creators.length && F.range === "all") return { clicks: cl.clicks, by_creator: cl.by_creator, by_app: cl.by_app, by_country: cl.by_country, by_device: cl.by_device, uniques: cl.uniques, partial: false };
    var by = cl.by_creator.filter(function (r) { return !F.creators.length || F.creators.indexOf(r.code) >= 0; });
    var n = by.reduce(function (a, r) { return a + r.n; }, 0);
    if (F.range !== "all" && !F.creators.length) n = (cl.by_day || []).filter(function (d) { return inRange(Date.parse(d.d + "T12:00:00Z") / 1000); }).reduce(function (a, d) { return a + d.n; }, 0);
    return { clicks: n, by_creator: by, by_app: cl.by_app, by_country: cl.by_country, by_device: cl.by_device, uniques: null, partial: true };
  }

  /* ------------------------------------------------------------- cards */
  function head(icon, title, tip, area) {
    return '<header class="db-card__head"><h2>' + icon + esc(title) + "</h2>" + (tip ? '<span class="db-info" tabindex="0" data-tip="' + esc(tip) + '">i</span>' : "")
      + (area ? '<button type="button" class="db-more" data-area="' + area + '">More ›</button>' : "") + "</header>";
  }
  function spark(vals, colour) {
    if (!vals || vals.length < 2) return "";
    var mx = Math.max.apply(null, vals) || 1, w = 70, h = 22;
    var pts = vals.map(function (v, i) { return (i / (vals.length - 1) * w).toFixed(1) + "," + (h - 2 - v / mx * (h - 4)).toFixed(1); }).join(" ");
    return '<svg class="db-spark" viewBox="0 0 70 22" aria-hidden="true"><polyline fill="none" stroke="' + colour + '" stroke-width="2" points="' + pts + '"/></svg>';
  }
  function series(list) {
    // cumulative views and engagement by posting day, for the filtered posts
    var by = {};
    list.forEach(function (p) { var d = p.posted_at ? new Date(p.posted_at * 1000).toISOString().slice(0, 10) : null; if (!d) return;
      var x = by[d] = by[d] || { views: 0, eng: 0, reach: 0, posts: 0 }; x.views += p.views || 0; x.eng += p.engagement || 0; x.reach += p.reach || 0; x.posts++; });
    var days = Object.keys(by).sort(), cv = 0, ce = 0, cr = 0, cp = 0;
    return days.map(function (d) { cv += by[d].views; ce += by[d].eng; cr += by[d].reach; cp += by[d].posts; return { d: d, views: cv, eng: ce, reach: cr, posts: cp }; });
  }

  function renderAll() {
    $("db-reset").hidden = !filtered();
    var list = posts(), t = sums(list), s = series(list), cl = clicksFor();
    // Whole-campaign totals set by HelloVoice by hand replace the measured
    // ones in the unfiltered view and are always marked as estimates.
    var adj = (!filtered() && R.total && R.total.adjusted) || [];
    function isAdj(k) { return adj.indexOf(k) >= 0; }
    function est(k) { return isAdj(k) ? '<small class="db-est" title="Estimated by HelloVoice: the platform has not shown the exact number yet.">est.</small>' : ""; }
    if (isAdj("views")) t.views = R.total.views;
    if (isAdj("reach")) t.reach = R.total.reach;
    if (isAdj("engagement")) t.engagement = R.total.engagement;
    if (isAdj("er")) t.er = R.total.er;
    if (isAdj("clicks") && cl) cl = Object.assign({}, cl, { clicks: R.total.clicks });
    var whole = !filtered() ? R.total : null;
    renderObjective();
    // KPI cards
    var g = {}; (R.progress.items || []).forEach(function (i) { g[i.key] = i; });
    function goal(k) { return !filtered() && g[k] ? sig(g[k].grade, "Goal " + (k === "er" ? pct(g[k].goal, 1) : num(g[k].goal))) : ""; }
    var cards = [
      ["Posts live", full(t.posts) + (!filtered() && R.total.planned ? "<small>/" + R.total.planned + "</small>" : ""), goal("posts"), spark(s.map(function (x) { return x.posts; }), COL[4]), IC.posts, "kpi"],
      ["Views", num(t.views) + est("views"), goal("views"), spark(s.map(function (x) { return x.views; }), COL[0]), IC.views, "trend"],
      ["Reach", num(t.reach) + (isAdj("reach") ? est("reach") : reachEst() ? '<small class="db-est" title="Instagram does not show reach on reels publicly. Estimated at ' + Math.round(((R.plan && R.plan.benchmark && R.plan.benchmark.reach_per_view) || 0.85) * 100) + '% of views until the creators\' insights arrive.">est.</small>' : ""), goal("reach"), spark(s.map(function (x) { return x.reach; }), COL[3]), IC.reach, "trend"],
      ["Engagement", num(t.engagement) + est("engagement"), goal("engagement"), spark(s.map(function (x) { return x.eng; }), COL[1]), IC.engagement, "trend"],
      ["Avg eng. rate", pct(t.er) + est("er"), !filtered() ? (g.er ? goal("er") : sig(R.total.er_grade)) : "", "", IC.er, "kpi"],
      ["Link clicks", cl ? num(cl.clicks) + est("clicks") : '<span class="db-na">Not tracked</span>', cl && !filtered() ? (g.clicks ? goal("clicks") : sig(R.total.ctr_grade)) : '<span class="db-na__why">No tracking links in this campaign</span>', "", IC.clicks, "clicks"]
    ];
    // Sections the admin switched off are left out, not shown empty.
    var V = R.visibility || {};
    // No tracking links = no clicks anywhere: not a KPI, not a card, not scored.
    var noClicks = V.clicks === false || !(R.objective || {}).links;
    cards = cards.filter(function (k) { return !(k[0] === "Reach" && V.reach === false) && !(k[0] === "Link clicks" && noClicks); });
    $("w-kpis").style.setProperty("--kpis", cards.length);
    $("db-grid").classList.toggle("no-clicks", noClicks);
    $("w-kpis").innerHTML = cards.map(function (k) {
      return '<button type="button" class="db-kpi" data-area="' + k[5] + '"><span class="db-kpi__label">' + k[4] + esc(k[0]) + '</span><span class="db-kpi__value">' + k[1]
        + '</span><span class="db-kpi__foot">' + (k[2] || "<span></span>") + k[3] + "</span></button>";
    }).join("");
    renderTrend(s);
    renderTop(list);
    renderStage();
    renderMix(list);
    renderGeo();
    renderPlat(list);
    renderClicks(cl);
    renderPosts(list);
    renderGaps();
  }
  function reachEst() { var G = R.gaps || {}; return !!G.reach_estimated; }
  // What the public numbers leave out, said once, small, under the cards.
  function renderGaps() {
    var G = R.gaps || {}, bits = [], el = $("db-gaps");
    if (!el) { el = document.createElement("p"); el.id = "db-gaps"; el.className = "db-gaps"; $("db-fresh").parentNode.appendChild(el); }
    if (G.likes_hidden) bits.push("Likes hidden by the creator on " + G.likes_hidden + " of " + G.posts + " posts — engagement there counts comments only");
    var ad = (R.total && R.total.adjusted) || [];
    if (ad.length) bits.push("figures marked est. are estimated by HelloVoice, not measured, until the exact numbers arrive");
    el.hidden = !bits.length;
    el.innerHTML = bits.length ? '<span class="db-gaps__i" aria-hidden="true">i</span>Data note: ' + esc(bits.join(" · ")) + '. <button type="button" class="db-gaps__more" data-area="kpi">Details</button>' : "";
  }

  // Every target counts toward the bar, each capped at its goal: it reads
  // 100% only when views, reach, engagement and rate are all met, so beating
  // one target cannot hide another that is short.
  var KEYN = { posts: "Posts", views: "Views", reach: "Reach", engagement: "Engagement", er: "Eng. rate", clicks: "Clicks" };
  function renderObjective() {
    var o = R.objective || { label: "Balanced", kpis: [] }, P = R.progress || {}, items = P.items || [];
    var box = $("w-objective");
    var goals = '<button type="button" class="db-goals" data-area="kpi">' + IC.goal + "<span>Goals &amp; benchmarks</span><b>›</b></button>";
    if (!items.length) { box.innerHTML = '<span class="db-obj__label">Objective · <b>' + esc(o.label) + "</b> — no targets set yet</span>" + goals; return; }
    var done = P.overall != null ? P.overall : items.reduce(function (a, i) { return a + Math.min(100, i.pct); }, 0) / items.length;
    var due = P.due != null ? P.due : items.reduce(function (a, i) { return a + Math.min(100, i.expected / i.goal * 100); }, 0) / items.length;
    if (!P.all_met) done = Math.min(done, 99);
    var r = due ? done / due : 1, gr = P.all_met ? "good" : r >= 1 ? "good" : r >= 0.7 ? "moderate" : "low";
    box.innerHTML = '<span class="db-obj__label">Objective · <b>' + esc(o.label) + '</b></span><div class="db-obj__track" role="img" aria-label="' + Math.round(done) + '% of all targets achieved">'
      + '<i class="db-obj__fill ' + gr + '" style="width:' + done.toFixed(1) + '%"></i><i class="db-obj__due" style="left:' + due.toFixed(1) + '%" title="Where it should be today"></i></div>'
      + '<span class="db-obj__pct" title="All targets together, each counted up to its goal">' + Math.round(done) + "%</span>" + sig(gr, "Expected by today: " + Math.round(due) + "%")
      + '<span class="db-obj__parts">' + items.map(function (i) { var met = i.actual >= i.goal; return '<span class="' + (met ? "met" : "short") + '" title="' + (met ? "Met" : "Not met yet") + '">' + KEYN[i.key] + " <b>" + Math.round(i.pct) + "%</b></span>"; }).join("") + "</span>"
      + goals;
  }

  function areaChart(pts, keyA, keyB, w, h) {
    if (!pts.length) return '<p class="db-note">Nothing in this view yet.</p>';
    if (pts.length === 1) pts = [{ d: pts[0].d, views: 0, eng: 0 }, pts[0]];
    var L = 40, Rr = 8, T = 8, B = 20, pw = w - L - Rr, ph = h - T - B;
    var peakA = Math.max.apply(null, pts.map(function (d) { return d[keyA]; }).concat([1]));
    var peakB = Math.max.apply(null, pts.map(function (d) { return d[keyB]; }).concat([1]));
    function x(i) { return L + pw * i / (pts.length - 1); }
    function y(v, pk) { return T + ph - v / pk * ph; }
    var s = '<svg viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="none" role="img" aria-label="Views and engagement over time">';
    for (var gI = 0; gI <= 2; gI++) { var yy = (T + ph * gI / 2).toFixed(1); s += '<line x1="' + L + '" x2="' + (w - Rr) + '" y1="' + yy + '" y2="' + yy + '" stroke="#efece6"/>'
      + '<text x="' + (L - 6) + '" y="' + (+yy + 4) + '" text-anchor="end" font-size="11" fill="#6a6a6a">' + num(peakA * (1 - gI / 2)) + "</text>"; }
    function line(key, pk, col, fill) {
      var p = pts.map(function (d, i) { return x(i).toFixed(1) + "," + y(d[key], pk).toFixed(1); });
      return (fill ? '<path d="M' + x(0) + "," + (T + ph) + " L" + p.join(" L") + " L" + x(pts.length - 1) + "," + (T + ph) + ' Z" fill="' + col + '" opacity=".12"/>' : "")
        + '<polyline fill="none" stroke="' + col + '" stroke-width="2.5" stroke-linejoin="round" points="' + p.join(" ") + '"/>';
    }
    s += line(keyA, peakA, COL[0], true) + line(keyB, peakB, COL[1], false);
    var every = Math.max(1, Math.ceil(pts.length / 5));
    pts.forEach(function (d, i) { if (i % every && i !== pts.length - 1) return;
      s += '<text x="' + x(i).toFixed(1) + '" y="' + (h - 5) + '" text-anchor="' + (i === 0 ? "start" : i === pts.length - 1 ? "end" : "middle") + '" font-size="11" fill="#6a6a6a">' + esc(day(d.d)) + "</text>"; });
    return s + "</svg>";
  }

  function renderTrend(s) {
    var useHist = !filtered() && R.history && R.history.length > 1;
    var pts = useHist ? R.history.map(function (d) { return { d: d.d, views: d.views, eng: d.likes + d.comments }; }) : s;
    $("w-trend").innerHTML = head(IC.trend, "Views & engagement", "Total views (green) and engagement — likes and comments (orange) — growing over the campaign. Each line has its own scale.", "trend")
      + '<div class="db-legend"><span><i style="background:' + COL[0] + '"></i>Views</span><span><i style="background:' + COL[1] + '"></i>Engagement</span></div>'
      + '<div class="db-card__body">' + areaChart(pts, "views", "eng", 640, 200) + "</div>";
  }

  var MEDAL = { 1: "#d6a52b", 2: "#9ea6ae", 3: "#b06f3a" };
  function medalBody(n) { return '<path d="M10 0h8l4 14-6 4z" fill="#ff691e"/><path d="M30 0h-8l-4 14 6 4z" fill="#ee1515"/><circle cx="20" cy="32" r="15" fill="' + MEDAL[n] + '"/><text x="20" y="38" text-anchor="middle" font-family="Bebasneue, Arial" font-size="17" fill="#121212">' + n + "</text>"; }
  function medal(n) { return '<svg viewBox="0 0 40 50" role="img" aria-label="Rank ' + n + '">' + medalBody(n) + "</svg>"; }
  // Creator names open their full analysis (the same page as the roster's).
  function who(c) { return '<a class="db-name" href="../../creator/#c=' + encodeURIComponent(c.code) + '" title="Open ' + esc(c.name) + '\'s full analysis">' + esc(c.name) + "</a>"; }
  function ranked(list) {
    if (!filtered()) return R.creators.filter(function (c) { return c.rank; }).map(function (c) { return { c: c, v: c.score, label: c.score.toFixed(0) }; });
    var by = {}; list.forEach(function (p) { by[p.code] = (by[p.code] || 0) + seen(p); });
    return R.creators.filter(function (c) { return by[c.code]; }).map(function (c) { return { c: c, v: by[c.code], label: num(by[c.code]) }; })
      .sort(function (a, b) { return b.v - a.v; });
  }
  function renderTop(list) {
    var rows = ranked(list).slice(0, 5);
    $("w-top").innerHTML = head(IC.top, "Top creators", filtered() ? "Ranked by views in this view." : scoreTip(), "creators")
      + '<div class="db-card__body"><div class="db-top__cols"><span>Creator</span><b>' + (filtered() ? "Reached" : "Score /100") + "</b></div>" + (rows.map(function (r, i) {
                return '<div class="db-rank' + (i === 0 ? " is-1" : "") + '"><span class="db-rank__n">' + (i < 3 ? medal(i + 1) : i + 1) + "</span>" + ava(r.c.photo) + "<span><b>" + who(r.c) + "</b><small>" + r.c.delivered + (r.c.planned ? "/" + r.c.planned : "") + (r.c.delivered === 1 && !r.c.planned ? " post · " : " posts · ") + num(r.c.seen != null ? r.c.seen : r.c.views) + " views" + '</small></span><span class="db-rank__score" title="' + (filtered() ? "People reached in this view" : "Score out of 100") + '">' + r.label + "</span></div>";
      }).join("") || '<p class="db-note">No creators in this view.</p>') + "</div>";
  }

  function renderStage() {
    // Steps can overlap (shooting goes on while publishing): the latest one
    // under way leads, the others are named under it.
    var c = R.campaign, steps = c.steps || [], act = steps.filter(function (s) { return s.state === "active"; }), now = act[act.length - 1];
    var also = act.slice(0, -1).map(function (s) { return s.label; });
    var done = steps.filter(function (s) { return s.state === "done"; }).length;
    $("w-stage").innerHTML = head(IC.stage, "Campaign stage", "Where the work is in the scope of work, updated by HelloVoice.", "stage")
      + '<div class="db-card__body"><div class="db-stage__now">' + esc(now ? now.label : (done === steps.length && steps.length ? "Completed" : "Not started")) + "</div>"
      + '<div class="db-stage__dates">' + (now && now.start ? day(now.start) + " – " + day(now.end, true) : "") + (also.length ? " · " + esc(also.join(", ")) + " also in progress" : "") + "</div>"
      + '<div class="db-steps">' + steps.map(function (s) { return '<i class="' + s.state + '" title="' + esc(s.label) + '"></i>'; }).join("") + "</div>"
      + (now && now.key === "publishing" && R.total.planned ? '<div class="db-stage__pub"><b>' + R.total.delivered + "</b> of " + R.total.planned + " videos published<i style=\"--w:" + Math.min(100, R.total.delivered / R.total.planned * 100).toFixed(1) + '%"></i></div>' : "")
      + '<div class="db-stage__meta"><span>' + done + " of " + steps.length + " steps done</span><span>" + (c.ends_at ? "Ends " + day(c.ends_at) : "") + "</span></div>"
      + (c.status_note ? '<p class="db-stage__note">' + esc(c.status_note) + "</p>" : "") + "</div>";
  }

  function donut(parts) {
    var tot = parts.reduce(function (a, p) { return a + p.n; }, 0) || 1, a0 = -Math.PI / 2, out = "";
    parts.forEach(function (p, i) {
      var a1 = a0 + p.n / tot * Math.PI * 2, large = a1 - a0 > Math.PI ? 1 : 0, r = 40, cx = 50, cy = 50;
      if (parts.length === 1) { out += '<circle cx="50" cy="50" r="40" fill="none" stroke="' + COL[i % COL.length] + '" stroke-width="16"/>'; return; }
      out += '<path d="M' + (cx + r * Math.cos(a0)).toFixed(2) + " " + (cy + r * Math.sin(a0)).toFixed(2) + " A" + r + " " + r + " 0 " + large + " 1 " + (cx + r * Math.cos(a1)).toFixed(2) + " " + (cy + r * Math.sin(a1)).toFixed(2)
        + '" fill="none" stroke="' + COL[i % COL.length] + '" stroke-width="16"/>';
      a0 = a1;
    });
    return '<svg viewBox="0 0 100 100" role="img" aria-label="Content mix">' + out + '<text x="50" y="55" text-anchor="middle" font-family="Bebasneue, Arial" font-size="22" fill="#121212">' + tot + "</text></svg>";
  }
  function renderMix(list) {
    var by = {}; list.forEach(function (p) { by[p.kind] = (by[p.kind] || 0) + 1; });
    var parts = Object.keys(by).map(function (k) { return { k: k, n: by[k] }; }).sort(function (a, b) { return b.n - a.n; });
    $("w-mix").innerHTML = head(IC.mix, "Content mix", "How many of each format was published: photo posts, reels, stories and videos.", "mix")
      + '<div class="db-card__body">' + (parts.length ? '<div class="db-donut">' + donut(parts) + '<div class="db-key">' + parts.map(function (p, i) {
        return '<div><span class="db-sw" style="background:' + COL[i % COL.length] + '"></span>' + esc(KIND[p.k] || p.k) + "<b>" + p.n + "</b></div>"; }).join("") + "</div></div>"
        : '<p class="db-note">No posts in this view.</p>') + "</div>";
  }

  function bars(rows, keyHtml, colourOf) {
    var peak = Math.max.apply(null, rows.map(function (r) { return r.n; }).concat([1]));
    return rows.map(function (r, i) { return '<div class="db-bar"><span>' + keyHtml(r) + '</span><i style="--w:' + (r.n / peak * 100).toFixed(1) + "%;--c:" + (colourOf ? colourOf(i) : COL[i % 4]) + '"></i><b>' + r.label + "</b></div>"; }).join("");
  }
  function renderGeo() {
    var a = R.audience;
    $("w-geo").innerHTML = head(IC.geo, "Audience countries", "Where the campaign's audience is, from the creators' profile analyses, weighted by reach. Shows the whole campaign.", "geo")
      + '<div class="db-card__body">' + (a && a.countries.length ? bars(a.countries.slice(0, 5).map(function (c) { return { k: c.code, n: c.pct, label: c.pct.toFixed(0) + "%" }; }),
        function (r) { return flag(r.k) + esc(countryName(r.k)); }) + '<p class="db-note">' + (a.coverage < 99 ? a.coverage.toFixed(0) + "% of reach covered" : "Weighted by reach") + "</p>"
        : '<p class="db-note">Audience data appears when creators\' full analyses are uploaded.</p>') + "</div>";
  }

  var PCOL = { Instagram: "#d62976", TikTok: "#121212", Snapchat: "#f7d100", YouTube: "#ff0000", X: "#121212" };
  function ring(rows, tot) {
    var a0 = -Math.PI / 2, r = 40, out = '<circle cx="50" cy="50" r="40" fill="none" stroke="#efece6" stroke-width="12"/>';
    rows.forEach(function (p) {
      var share = tot ? p.n / tot : 0, col = PCOL[p.k] || COL[0];
      if (share >= 0.999) { out += '<circle cx="50" cy="50" r="40" fill="none" stroke="' + col + '" stroke-width="12"/>'; return; }
      var a1 = a0 + share * Math.PI * 2, large = a1 - a0 > Math.PI ? 1 : 0;
      out += '<path d="M' + (50 + r * Math.cos(a0)).toFixed(2) + " " + (50 + r * Math.sin(a0)).toFixed(2) + " A40 40 0 " + large + " 1 " + (50 + r * Math.cos(a1)).toFixed(2) + " " + (50 + r * Math.sin(a1)).toFixed(2)
        + '" fill="none" stroke="' + col + '" stroke-width="12"/>';
      a0 = a1;
    });
    return '<svg viewBox="0 0 100 100" aria-hidden="true">' + out + "</svg>";
  }
  function renderPlat(list) {
    var by = {}; list.forEach(function (p) { var x = by[p.platform] = by[p.platform] || { n: 0, posts: 0, eng: 0 }; x.n += seen(p); x.posts++; x.eng += p.engagement || 0; });
    var rows = Object.keys(by).map(function (k) { return { k: k, n: by[k].n, posts: by[k].posts, eng: by[k].eng }; }).sort(function (a, b) { return b.n - a.n; });
    var tot = rows.reduce(function (a, r) { return a + r.n; }, 0), body;
    if (!rows.length) body = '<p class="db-note">No posts in this view.</p>';
    else {
      var lead = rows[0];
      body = '<div class="db-pring"><div class="db-pring__ring">' + ring(rows, tot) + '<span class="db-pring__logo" style="color:' + (PCOL[lead.k] || "#121212") + '">' + (ICONS[lead.k] || "") + "</span></div>"
        + '<div class="db-pring__key">' + rows.map(function (r) {
          return '<div class="db-pring__row"><span class="db-pring__name"><i style="background:' + (PCOL[r.k] || COL[0]) + '"></i>' + (ICONS[r.k] || "") + esc(r.k) + "</span>"
            + "<b>" + num(r.n) + "</b><small>" + Math.round(tot ? r.n / tot * 100 : 0) + "% · " + r.posts + (r.posts === 1 ? " post" : " posts") + " · " + num(r.eng) + " eng.</small></div>";
        }).join("") + "</div></div>";
    }
    $("w-plat").innerHTML = head(IC.plat, "Platforms", "Views on each platform — views for videos, reach for photo posts and stories, never both added together.", "plat")
      + '<div class="db-card__body">' + body + "</div>";
  }

  function renderClicks(cl) {
    $("w-clicks").innerHTML = head(IC.clicks, "Affiliate clicks", "Taps on the creators' own tracking links — people only, not link previews or bots.", cl ? "clicks" : "")
      + '<div class="db-card__body">' + (cl ? '<div class="db-big">' + full(cl.clicks) + (cl.uniques != null ? "<small>" + full(cl.uniques) + " unique</small>" : "") + "</div>"
        + '<div style="margin-top:8px">' + bars((cl.by_app || []).slice(0, 3).map(function (r) { return { k: r.k, n: r.n, label: full(r.n) }; }), function (r) { return (ICONS[r.k] || "") + esc(r.k); }) + "</div>"
        + (cl.partial || F.platform ? '<p class="db-note">' + (F.platform ? "Clicks are per creator link, not per platform — showing all platforms." : "Apps show the whole campaign.") + "</p>" : "")
        : '<div class="db-na-card"><span class="db-na-card__icon">' + IC.clicks + '</span><span class="db-na">Not part of this campaign</span>'
          + "<p>This campaign is about views and reach, so creators were not given tracking links. Ask us to add them for a sales or traffic campaign.</p></div>") + "</div>";
  }

  // People who saw a post: views for a video, reach for a photo or story.
  // Adding the two would count the same viewers twice.
  function seen(p) { return p.exposure != null ? p.exposure : (p.video ? (p.views || 0) : (p.reach || 0)); }
  function topPosts(list) { return list.slice().sort(function (a, b) { return seen(b) - seen(a); }); }
  function weights() { var w = (R.objective || {}).weights || { exposure: 0.35, engagement: 0.25, er: 0.25, clicks: 0.15 }; return w; }
  function scoreTip() {
    var w = weights(), o = (R.objective || {}).label || "Balanced";
    return "Score out of 100, weighted for the " + o + " objective: views & reach " + Math.round(w.exposure * 100) + ", engagement " + Math.round(w.engagement * 100)
      + ", engagement rate against the strong mark for the creator's size " + Math.round(w.er * 100) + (w.clicks > 0 ? ", link clicks " + Math.round(w.clicks * 100) : "")
      + ". Views and engagement are measured against the best creator in the campaign.";
  }
  function renderPosts(list) {
    var top = topPosts(list).slice(0, 3);
    $("w-posts").innerHTML = head(IC.img, "Top posts", "The three posts that reached the most people in this view.", "posts")
      + '<div class="db-card__body"><div class="db-thumbs">' + (top.map(function (p, i) {
        return '<a class="db-thumb" href="' + esc(p.url) + '" target="_blank" rel="noopener">' + fit(p.thumb)
          + '<svg class="db-thumb__n" viewBox="0 0 40 50" aria-hidden="true">' + medalBody(i + 1) + "</svg>"
          + "<span><em>" + esc(p.creator) + "</em><i>" + (ICONS[p.platform] || "") + num(p.video ? p.views : p.reach) + "<small style=\"font:600 10px var(--body);color:#fff;opacity:.7\">" + (p.video ? "views" : "reached") + "</small></i></span></a>";
      }).join("") || '<p class="db-note">No posts in this view.</p>') + "</div></div>";
  }

  /* -------------------------------------------------------------- panel */
  var PANEL = {
    kpi: function () {
      var items = R.progress.items || [], bm = R.benchmarks, t = R.total, P = R.progress || {}, plan = R.plan || {}, pb = plan.benchmark || {};
      var o = R.objective || {}, lead = o.kpis || [];
      function fv(k, v) { return v == null ? "—" : k === "er" ? pct(v) : num(v); }
      // The guide range for each KPI, worked out for this campaign's creators.
      function range(k) {
        var sf = plan.safe || {}, ex = plan.estimate || {};
        if (k !== "posts" && sf[k] != null && ex[k] != null) return fv(k, sf[k]) + " – " + fv(k, ex[k]);
        return "—";
      }
      var head = '<div class="db-goal-sum"><div><span>All targets</span><b>' + Math.round(P.all_met ? 100 : Math.min(99, P.overall || 0)) + '%</b><small>' + (P.all_met ? "Every target met" : "100% only when every target is met") + "</small></div>"
        + "<div><span>Objective</span><b>" + esc(o.label || "Balanced") + "</b><small>" + esc(lead.map(function (k) { return KEYN[k]; }).join(" & ")) + " lead</small></div>"
        + (plan.platform ? "<div><span>Benchmarked for</span><b>" + esc(plan.platform) + "</b><small>" + esc(plan.category || plan.template || "") + "</small></div>" : "") + "</div>";
      var rows = items.map(function (i) {
        var isR = i.key === "er", col = { good: "#14884a", moderate: "#e2780f", low: "#ee1515" }[i.grade], met = i.actual >= i.goal;
        return "<tr" + (lead.indexOf(i.key) >= 0 ? ' class="is-lead"' : "") + "><td><b>" + KEYN[i.key] + "</b>" + (lead.indexOf(i.key) >= 0 ? ' <span class="db-lead">headline</span>' : "") + "</td>"
          + '<td class="r">' + fv(i.key, i.goal) + "</td><td class=\"r\"><b>" + fv(i.key, i.actual) + "</b></td>"
          + '<td><div class="db-goal__track"><i style="width:' + Math.min(100, i.pct) + "%;background:" + col + '"></i>' + (isR ? "" : '<em style="left:' + Math.min(100, i.expected / i.goal * 100) + '%"></em>') + "</div><small>" + Math.round(i.pct) + "%" + (met ? " · met" : "") + "</small></td>"
          + '<td class="r muted">' + range(i.key) + "</td><td>" + sig(met ? "good" : i.grade) + "</td></tr>";
      }).join("");
      var out = head + (items.length ? '<h3>Targets agreed</h3><table class="db-table db-goals-t"><thead><tr><th>KPI</th><th class="r">Minimum agreed</th><th class="r">Now</th><th>Progress</th><th class="r">Benchmark range</th><th></th></tr></thead><tbody>' + rows + "</tbody></table>"
        + '<div class="db-legend2"><span><i class="tick"></i>Where it should be today</span><span><i class="sw" style="background:#14884a"></i>Met / on track</span><span><i class="sw" style="background:#e2780f"></i>Close</span><span><i class="sw" style="background:#ee1515"></i>Behind</span><span class="db-legend2__txt">Minimum agreed = what we commit to · Benchmark = typical for these creators</span></div>'
        : '<p class="db-note">No targets set for this campaign yet.</p>');
      // Benchmarks as gauges: the shaded band is the normal range for these
      // creators, the dot is where the campaign is now.
      function gauge(label, unit, band, now, grade) {
        if (!band) return "";
        var top = Math.max(band[1] * 1.35, (now || 0) * 1.1) || 1, l = band[0] / top * 100, w = (band[1] - band[0]) / top * 100;
        var dot = now != null ? '<i class="db-gauge__dot ' + (grade || "") + '" style="left:' + Math.min(100, now / top * 100).toFixed(1) + '%"><span>' + now.toFixed(now < 10 ? 2 : 1) + "%</span></i>" : "";
        return '<div class="db-gauge"><div class="db-gauge__lbl"><b>' + label + "</b><small>" + unit + '</small></div><div class="db-gauge__bar"><i class="db-gauge__band" style="left:' + l.toFixed(1) + "%;width:" + w.toFixed(1) + '%"></i>' + dot
          + '<em style="left:' + l.toFixed(1) + '%">' + band[0] + '%</em><em style="left:' + (l + w).toFixed(1) + '%">' + band[1] + "%</em></div>"
          + '<div class="db-gauge__sig">' + (now != null ? sig(grade) : '<span class="db-na">Typical</span>') + "</div></div>";
      }
      var vids = R.posts.filter(function (p) { return p.section === "campaign" && p.view_rate != null; });
      var vrNow = vids.length ? vids.reduce(function (a, p) { return a + p.view_rate; }, 0) / vids.length : null;
      var erNow = t.video_er != null ? t.video_er : t.er;
      function gr(v, b) { return v == null ? null : v >= b[1] ? "good" : v >= b[0] ? "moderate" : "low"; }
      var links = (R.objective || {}).links;
      if (pb.view_rate) out += '<h3>Benchmarks for these creators</h3><div class="db-gauges">'
        + gauge("Views per video", "% of followers", pb.view_rate, vrNow, gr(vrNow, pb.view_rate))
        + gauge("Engagement rate", "% of views", pb.eng_rate, erNow, gr(erNow, pb.eng_rate))
        + (links && pb.ctr ? gauge("Click-through", "% of views", pb.ctr, t.ctr, gr(t.ctr, pb.ctr)) : "")
        + '<div class="db-gauge db-gauge--fact"><div class="db-gauge__lbl"><b>Reach</b><small>unique people</small></div><div class="db-fact"><b>' + Math.round((pb.reach_per_view || 0.85) * 100) + "%</b> of views are unique people</div><div></div></div>"
        + '</div><div class="db-legend2"><span><i class="sw band"></i>Normal range for creators this size</span><span><i class="dot"></i>This campaign now</span></div>';
      // Scoring as one bar: each part's share of the 100 points. Clicks only
      // when the campaign tracks links.
      var w = weights(), parts = [["Views & reach", w.exposure, "#14884a", "vs the top creator"], ["Engagement", w.engagement, "#ff691e", "likes + comments vs the top creator"],
        ["Engagement rate", w.er, "#b9d400", "vs the strong mark for their size"]];
      if (w.clicks > 0) parts.push(["Link clicks", w.clicks, "#121212", "vs the top creator"]);
      out += '<h3>How creators are scored · out of 100</h3><div class="db-scorebar">' + parts.map(function (x) {
        return '<i style="flex:' + x[1] + ";background:" + x[2] + '"><b>' + Math.round(x[1] * 100) + "</b></i>"; }).join("") + '</div><div class="db-scorekey">'
        + parts.map(function (x) { return '<div><i style="background:' + x[2] + '"></i><b>' + x[0] + "</b><small>" + x[3] + "</small></div>"; }).join("") + "</div>";
      var G = R.gaps || {};
      // Hidden likes change the numbers the client reads, so they are shown;
      // estimates and missing shares/saves are internal (admin Content tab).
      if (G.likes_hidden) {
        var by = {}; (G.hidden || []).forEach(function (h) { var x = by[h.creator] = by[h.creator] || { n: 0, url: h.url }; x.n++; });
        out += '<h3>About the data</h3><div class="db-hidden"><div class="db-hidden__n"><b>' + G.likes_hidden + "</b><span>of " + G.posts + ' posts hide likes</span><i style="--w:' + (G.likes_hidden / G.posts * 100).toFixed(1) + '%"></i></div>'
          + '<div class="db-hidden__body"><div class="db-hidden__chips">' + Object.keys(by).map(function (k) { return '<a href="' + esc(by[k].url) + '" target="_blank" rel="noopener">' + esc(k) + (by[k].n > 1 ? " <small>×" + by[k].n + "</small>" : "") + "</a>"; }).join("")
          + '</div><p><b>Engagement</b> on these posts = comments only · <b>Engagement rate</b> leaves them out</p></div></div>';
      }
      return out;
    },
    trend: function () {
      var s = series(posts()), useHist = !filtered() && R.history && R.history.length > 1;
      var pts = useHist ? R.history.map(function (d) { return { d: d.d, views: d.views, eng: d.likes + d.comments }; }) : s;
      return "<h3>Views & engagement over time</h3><div style=\"height:240px\">" + areaChart(pts, "views", "eng", 600, 240) + "</div>"
        + '<h3>Day by day</h3><table class="db-table"><thead><tr><th>Day</th><th></th><th>Views</th><th>Engagement</th></tr></thead><tbody>'
        + pts.map(function (d) { return "<tr><td>" + esc(day(d.d, true)) + "</td><td></td><td>" + full(d.views) + "</td><td>" + full(d.eng) + "</td></tr>"; }).join("") + "</tbody></table>";
    },
    creators: function () {
      var list = posts(), by = {}; list.forEach(function (p) { var x = by[p.code] = by[p.code] || { posts: 0, views: 0, reach: 0, eng: 0 }; x.posts++; x.views += p.views || 0; x.reach += p.reach || 0; x.eng += p.engagement || 0; });
      var rows = filtered() ? ranked(list).map(function (r) { return r.c; }) : R.creators;
      return '<table class="db-table"><thead><tr><th>#</th><th>Creator</th><th>Posts</th><th>Views</th>' + (R.visibility.reach === false ? "" : "<th>Reach</th>") + '<th>Eng.</th><th>ER</th>' + (R.visibility.clicks && R.objective.links ? "<th>Clicks</th>" : "") + "<th>Score</th></tr></thead><tbody>"
        + rows.map(function (c, i) { var x = filtered() ? (by[c.code] || {}) : { posts: c.delivered, views: c.views, reach: c.reach, eng: c.engagement };
          var n = filtered() ? i + 1 : c.rank;
          return '<tr' + (n && n <= 3 ? ' class="is-top"' : "") + "><td>" + (n && n <= 3 ? '<span class="db-medal">' + medal(n) + "</span>" : (n || "—")) + '</td><td><span class="db-who">' + ava(c.photo) + "<b>" + who(c) + "</b></span></td><td>" + (x.posts || 0) + (c.planned && !filtered() ? "/" + c.planned : "") + "</td><td>" + num(x.views) + (R.visibility.reach === false ? "" : "</td><td>" + num(x.reach)) + "</td><td>" + num(x.eng)
            + "</td><td>" + pct(c.er != null ? c.er : c.video_er) + "</td>" + (R.visibility.clicks && R.objective.links ? "<td>" + full(c.clicks) + "</td>" : "") + "<td>" + (c.score != null ? c.score.toFixed(0) : "—") + "</td></tr>"; }).join("")
        + '</tbody></table><p class="db-note" style="margin-top:10px">' + esc(scoreTip()) + "</p>"
        + (filtered() ? "" : '<h3>Score breakdown</h3><table class="db-table"><thead><tr><th>Creator</th><th>Views &amp; reach</th><th>Engagement</th><th>Eng. rate</th>' + (weights().clicks > 0 ? "<th>Clicks</th>" : "") + '<th>Score</th></tr></thead><tbody>'
          + R.creators.filter(function (c) { return c.parts; }).map(function (c) { var q = c.parts; return "<tr><td>" + esc(c.name) + "</td><td>" + q.exposure.toFixed(0) + "</td><td>" + q.engagement.toFixed(0) + "</td><td>" + q.er.toFixed(0) + "</td>" + (weights().clicks > 0 ? "<td>" + q.clicks.toFixed(0) + "</td>" : "") + "<td><b>" + c.score.toFixed(0) + "</b></td></tr>"; }).join("")
          + "</tbody></table>");
    },
    stage: function () {
      var c = R.campaign, ST = { done: "Done", active: "In progress", pending: "Not started" };
      return (c.status_note ? "<p>" + esc(c.status_note) + "</p>" : "") + '<h3>Scope of work</h3><div class="db-tl">' + (c.steps || []).map(function (s) {
        var pub = s.key === "publishing" && R.total.planned ? " · " + R.total.delivered + "/" + R.total.planned + " videos" : "";
        return '<div class="' + s.state + '"><b>' + esc(s.label) + esc(pub) + "</b><span>" + (s.start ? day(s.start) + " – " + day(s.end, true) : "Dates to be confirmed") + '</span><span class="db-state">' + ST[s.state] + "</span></div>"; }).join("") + "</div>";
    },
    mix: function () { return PANEL.posts(true); },
    posts: function (byKind) {
      var list = topPosts(posts());
      if (byKind === true) {
        var g = {}; list.forEach(function (p) { (g[p.kind] = g[p.kind] || []).push(p); });
        return Object.keys(g).map(function (k) { return "<h3>" + esc(KIND[k] || k) + " · " + g[k].length + '</h3><div class="db-wall">' + g[k].map(post).join("") + "</div>"; }).join("") + pendingWall();
      }
      return '<div class="db-wall">' + list.map(post).join("") + "</div>";
    },
    geo: function () {
      var a = R.audience; if (!a) return '<p class="db-note">Audience data appears when creators\' full analyses are uploaded.</p>';
      return bars(a.countries.map(function (c) { return { k: c.code, n: c.pct, label: c.pct.toFixed(1) + "%" }; }), function (r) { return flag(r.k) + esc(countryName(r.k)); })
        + '<p class="db-note" style="margin-top:10px">From the creators\' profile analyses, weighted by the reach each delivered; covers ' + a.coverage.toFixed(0) + "% of reach.</p>";
    },
    plat: function () {
      var by = {}; posts().forEach(function (p) { var x = by[p.platform] = by[p.platform] || { posts: 0, views: 0, reach: 0, eng: 0 }; x.posts++; x.views += p.views || 0; x.reach += p.reach || 0; x.eng += p.engagement || 0; });
      return '<table class="db-table"><thead><tr><th>Platform</th><th></th><th>Posts</th><th>Views</th><th>Reach</th><th>Engagement</th></tr></thead><tbody>'
        + Object.keys(by).map(function (k) { var x = by[k]; return "<tr><td>" + (ICONS[k] || "") + " " + esc(k) + "</td><td></td><td>" + x.posts + "</td><td>" + num(x.views) + (R.visibility.reach === false ? "" : "</td><td>" + num(x.reach)) + "</td><td>" + num(x.eng) + "</td></tr>"; }).join("") + "</tbody></table>";
    },
    clicks: function () {
      var cl = clicksFor(); if (!cl) return '<div class="db-na-card"><span class="db-na-card__icon">' + IC.clicks + '</span><span class="db-na">Not part of this campaign</span><p>No tracking links were set up for this campaign, so there are no clicks to count.</p></div>';
      var L = function (rows) { return (rows || []).map(function (r) { return { k: r.k, n: r.n, label: full(r.n) }; }); };
      return '<div class="db-big">' + full(cl.clicks) + " <small>clicks" + (cl.uniques != null ? " · " + full(cl.uniques) + " unique people" : "") + "</small></div>"
        + "<h3>By creator</h3>" + bars(L(cl.by_creator), function (r) { return esc(r.k); })
        + "<h3>By app</h3>" + bars(L(cl.by_app), function (r) { return (ICONS[r.k] || "") + esc(r.k); })
        + "<h3>By country</h3>" + bars(L(cl.by_country), function (r) { return r.k && r.k.length === 2 ? flag(r.k) + esc(countryName(r.k)) : esc(r.k || "Unknown"); })
        + "<h3>By device</h3>" + bars(L(cl.by_device), function (r) { return esc(r.k); });
    }
  };
  function stats(p) {
    var er = p.video ? (p.video_er != null ? p.video_er : p.er) : (p.er != null ? p.er : p.imp_er);
    var out = [];
    if (p.video) out.push(["Views", full(p.views)]);
    if (p.reach != null) out.push([p.story ? "Story views" : "Reach" + (p.reach_real === false && !p.story ? " (est.)" : ""), full(p.reach)]);
    if (!p.video && p.impressions) out.push(["Impressions", full(p.impressions)]);
    out.push(["Likes", p.likes_hidden ? '<span class="db-hid" title="The creator hides the like count on this post">Hidden</span>' : full(p.likes)], ["Comments", full(p.comments)],
      ["Engagement", full(p.engagement) + (p.likes_hidden ? '<span class="db-hid-n">comments only</span>' : "")]);
    if (p.shares != null) out.push(["Shares", full(p.shares)]);
    if (p.saves != null) out.push(["Saves", full(p.saves)]);
    out.push(["Eng. rate", p.likes_hidden ? '<span class="db-hid">n/a</span>' : pct(er)]);
    if (p.view_rate != null && p.video) out.push(["View rate", pct(p.view_rate, 1)]);
    return out;
  }
  // Booked posts not live yet, each a card with where it stands.
  function pendingWall() {
    var out = [];
    (R.creators || []).forEach(function (c) {
      for (var i = (c.delivered || 0); i < (c.planned || 0); i++) out.push({ c: c, n: i + 1 });
    });
    if (!out.length || filtered()) return "";
    return "<h3>Pending · " + out.length + '</h3><div class="db-wall">' + out.map(function (x) {
      var c = x.c, pic = c.photo_large || c.photo;
      return '<div class="db-post db-post--pending"><div class="db-post__img">' + (pic ? '<img src="' + esc(pic) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : "")
        + '<span class="db-kind db-kind--pending">Pending</span></div><div class="db-post__body"><b>' + esc(c.name) + "</b><span>"
        + esc(c.pending_status || "Coming soon") + " · " + esc(c.pending_date ? day(c.pending_date) : "date to be confirmed")
        + " · post " + x.n + " of " + c.planned + "</span></div></div>";
    }).join("") + "</div>";
  }

  // A post's picture is never cropped: the whole frame is fitted in, and a
  // blurred copy of the same picture fills the space a tall reel leaves.
  function fit(src) {
    if (!src) return "";
    var u = esc(src);
    return '<img class="hv-fill" src="' + u + '" alt="" aria-hidden="true" loading="lazy" referrerpolicy="no-referrer"><img class="hv-fit" src="' + u + '" alt="" loading="lazy" referrerpolicy="no-referrer">';
  }
  function post(p) {
    return '<a class="db-post" href="' + esc(p.url) + '" target="_blank" rel="noopener"><div class="db-post__img">' + fit(p.thumb)
      + (p.kind ? '<span class="db-kind">' + esc(ONE[p.kind] || p.kind) + "</span>" : "")
      + '</div><div class="db-post__body"><b>' + esc(p.creator) + "</b><span>" + (ICONS[p.platform] ? "" : "") + esc(p.platform) + " · " + esc(day(p.posted_at, true)) + "</span></div>"
      + (p.caption ? '<p class="db-post__cap">' + esc(p.caption) + "</p>" : "")
      + '<div class="db-post__stats">' + stats(p).map(function (x) { return "<div><small>" + x[0] + "</small><b>" + x[1] + "</b></div>"; }).join("") + "</div></a>";
  }
  var TITLES = { kpi: "Goals & benchmarks", trend: "Views & engagement", creators: "All creators", stage: "Campaign stage", mix: "Content by format", posts: "All posts", geo: "Audience countries", plat: "Platforms", clicks: "Affiliate clicks" };
  var lastFocus = null;
  function openPanel(area) {
    if (!PANEL[area]) return;
    lastFocus = document.activeElement;
    $("db-panel-title").textContent = TITLES[area] + (filtered() && area !== "stage" && area !== "geo" ? " · filtered" : "");
    $("db-panel-body").innerHTML = PANEL[area]();
    $("db-scrim").hidden = false; $("db-panel").hidden = false;
    $("db-panel-close").focus();
  }
  function closePanel() { $("db-scrim").hidden = true; $("db-panel").hidden = true; if (lastFocus) lastFocus.focus(); }
  // Info tips: one floating box placed beside the "i", flipped and clamped
  // so it never runs off the screen or under the next card.
  var tipEl = null;
  function showTip(t) {
    hideTip();
    tipEl = document.createElement("div"); tipEl.className = "db-tip"; tipEl.setAttribute("role", "tooltip");
    tipEl.textContent = t.getAttribute("data-tip"); document.body.appendChild(tipEl);
    var r = t.getBoundingClientRect(), w = tipEl.offsetWidth, h = tipEl.offsetHeight, vw = innerWidth, vh = innerHeight;
    var x = Math.max(8, Math.min(r.left, vw - w - 8)), y = r.bottom + 8;
    if (y + h > vh - 8) y = Math.max(8, r.top - h - 8);
    tipEl.style.left = x + "px"; tipEl.style.top = y + "px";
  }
  function hideTip() { if (tipEl) { tipEl.remove(); tipEl = null; } }
  ["mouseover", "focusin"].forEach(function (ev) { document.addEventListener(ev, function (e) { var t = e.target.closest && e.target.closest(".db-info"); if (t) showTip(t); }); });
  ["mouseout", "focusout"].forEach(function (ev) { document.addEventListener(ev, function (e) { if (e.target.closest && e.target.closest(".db-info")) hideTip(); }); });
  addEventListener("scroll", hideTip, true);
  document.addEventListener("click", function (e) { var b = e.target.closest("[data-area]"); if (b && b.closest("#cat-app")) openPanel(b.getAttribute("data-area")); });
  $("db-panel-close").addEventListener("click", closePanel);
  $("db-scrim").addEventListener("click", closePanel);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !$("db-panel").hidden) closePanel(); });

  load();
})();
