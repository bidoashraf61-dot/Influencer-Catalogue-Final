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
      R = b.report;
      FILTER = { platform: "", kind: "", section: "campaign" };
      render(t);
      show("report");
      window.scrollTo(0, 0);
      get("/api/campaigns").then(function (x) { $("mx-all").hidden = (x.campaigns || []).length < 2; }).catch(function () {});
    }).catch(function (err) {
      if (err && err.locked) return lock();
      unlocked(); empty("This report is not available with your access code.");
    });
  }
  window.addEventListener("hashchange", route);

  /* ---------------------------------------------------------------- render */

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
    $("mx-csv").href = API + "/api/campaign.csv?t=" + encodeURIComponent(t);
  }

  function renderBug(c) {
    var logos = (c.logos || []).map(function (u) { return '<img src="' + esc(u) + '" alt="Brand logo">'; }).join("");
    $("mx-brands").innerHTML = logos ? logos + '<span class="mx-bug__x" aria-hidden="true">×</span><img class="mx-bug__hv" src="../assets/brand/logo-knockout.webp" alt="HelloVoice">' : "";
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

    // delivery strip: one slot per planned post
    var t = R.total, planned = t.planned || 0, got = t.delivered || 0;
    if (planned) {
      var slots = "";
      for (var k = 0; k < Math.max(planned, got); k++) slots += '<i class="' + (k < got ? (k < planned ? "on" : "extra") : "") + '"></i>';
      $("mx-delivery").innerHTML = '<div class="mx-delivery__label"><span>Posts delivered</span><b>' + got + " of " + planned + "</b></div>"
        + '<div class="mx-slots" role="img" aria-label="' + got + " of " + planned + ' planned posts delivered">' + slots + "</div>";
    } else $("mx-delivery").innerHTML = "";
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

  function bars(rows, keyHtml) {
    if (!rows || !rows.length) return '<p class="mx-panel__note">Nothing yet.</p>';
    var peak = Math.max.apply(null, rows.map(function (r) { return r.n; })) || 1;
    return rows.slice(0, 8).map(function (r) {
      return '<div class="mx-bar"><span class="mx-bar__k">' + keyHtml(r) + '</span><i style="--w:' + (r.n / peak * 100).toFixed(1) + '%"></i><b>' + r.label + "</b></div>";
    }).join("");
  }

  function renderCharts() {
    var h = (R.history || []).map(function (d) { return { d: d.d, views: d.views, eng: d.likes + d.comments }; });
    $("mx-charts").innerHTML = h.length
      ? '<div class="mx-chart"><h3>Views so far</h3>' + area(h, "views", "#121212", "Views so far") + "</div>"
        + '<div class="mx-chart"><h3>Engagement so far</h3>' + area(h, "eng", "#ff691e", "Engagement so far") + "</div>"
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
    var t = R.total, parts = [["Likes", t.likes, "#121212"], ["Comments", t.comments, "#ff691e"], ["Saves", t.saves, "#14884a"], ["Shares", t.shares, "#9ea6ae"]]
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
  }

  /* ----------------------------------------------------------- clicks */

  function renderClicks() {
    var vis = R.visibility, cl = R.clicks;
    $("mx-clicks-sec").hidden = !vis.clicks;
    if (!vis.clicks) return;
    if (!cl || !cl.links || !cl.has_destination) {
      $("mx-clicks").innerHTML = '<p class="mx-empty-note">No affiliate links in this campaign.</p>';
      return;
    }
    var t = R.total;
    var heads = '<dl class="mx-clickheads"><div><dt>Clicks</dt><dd>' + full(cl.clicks) + "</dd></div><div><dt>Unique people</dt><dd>"
      + full(cl.uniques) + "</dd></div><div><dt>Click-through</dt><dd>" + pct(t.ctr) + "</dd></div></dl>";
    if (!cl.clicks) { $("mx-clicks").innerHTML = heads + '<p class="mx-empty-note" style="margin-top:18px">No clicks yet.</p>'; return; }
    var lab = function (rows) { return (rows || []).map(function (r) { return { k: r.k, n: r.n, label: full(r.n) }; }); };
    $("mx-clicks").innerHTML = heads + '<div class="mx-clickgrid">'
      + '<div class="mx-panel"><h3>By creator</h3>' + bars(lab(cl.by_creator), function (r) { return esc(r.k); }) + "</div>"
      + '<div class="mx-panel"><h3>By app</h3>' + bars(lab(cl.by_app), function (r) { return (ICONS[r.k] || "") + esc(r.k); }) + "</div>"
      + '<div class="mx-panel"><h3>By country</h3>' + bars(lab(cl.by_country), function (r) {
        return r.k && r.k.length === 2 ? flag(r.k) + esc(countryName(r.k)) : esc(r.k || "Unknown");
      }) + "</div>"
      + '<div class="mx-panel"><h3>By device</h3>' + bars(lab(cl.by_device), function (r) { return esc(r.k); }) + "</div></div>";
  }

  $("mx-print").addEventListener("click", function () { window.print(); });
  route();
})();
