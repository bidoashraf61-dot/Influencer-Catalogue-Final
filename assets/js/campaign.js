/* Campaign report — the client's read-only view.

   Everything comes from the admin service: GET /api/campaigns lists what the
   passcode may see, GET /api/campaign?t=<token> returns one report already
   stripped of anything internal (cost, CPM, ratings). The page holds no data
   of its own; a passcode that is revoked stops working on the next request.

   The link a client is sent is /campaign/#t=<token>. Without a token the page
   lists the passcode's campaigns. */
(function () {
  "use strict";

  var CFG = window.CAMPAIGN_CONFIG || {};
  var API = CFG.api || "/admin";
  var REPORT = null;
  var FILTER = { platform: "", kind: "", creator: "", section: "campaign" };

  function $(id) { return document.getElementById(id); }
  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function num(v) {
    if (v == null) return "—";
    var n = Math.round(v);
    if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
    if (Math.abs(n) >= 1e4) return (n / 1e3).toFixed(n >= 1e5 ? 0 : 1).replace(/\.0$/, "") + "K";
    return n.toLocaleString("en-US");
  }
  function full(v) { return v == null ? "—" : Math.round(v).toLocaleString("en-US"); }
  function pct(v) { return v == null ? "—" : v.toFixed(2) + "%"; }
  function sar(v) { return v == null ? "—" : num(v) + " SAR"; }
  function day(t) {
    if (!t) return "";
    return new Date(t * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  }
  function ago(t) {
    if (!t) return "";
    var s = Date.now() / 1000 - t;
    if (s < 3600) return Math.max(1, Math.round(s / 60)) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    return Math.round(s / 86400) + " days ago";
  }
  function token() {
    var m = /(?:^|[#&])t=([A-Za-z0-9_-]+)/.exec(location.hash || "");
    return m ? m[1] : "";
  }
  function get(path) {
    return fetch(API + path, { credentials: "include", cache: "no-store" }).then(function (r) {
      if (r.status === 401) throw { locked: true };
      if (!r.ok) throw { status: r.status };
      return r.json();
    });
  }

  /* ---------------------------------------------------------------- gate */

  function lock(msg) {
    $("cat-app").hidden = true;
    $("cat-gate").hidden = false;
    document.body.classList.add("cat-locked");
    if (msg) { $("cat-gate-error").textContent = msg; $("cat-gate-error").hidden = false; }
    setTimeout(function () { $("cat-code").focus(); }, 50);
  }
  function unlocked() {
    $("cat-gate").hidden = true;
    $("cat-app").hidden = false;
    document.body.classList.remove("cat-locked");
  }

  var REFUSALS = {
    revoked: "This code has been withdrawn.",
    expired: "This code has expired.",
    exhausted: "This code has been used up.",
    devices: "This code is already open on its maximum number of devices.",
    unknown: "That code is not right."
  };

  $("cat-gate-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var btn = this.querySelector("button");
    btn.disabled = true;
    $("cat-gate-error").hidden = true;
    fetch(API + "/api/unlock", {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: $("cat-code").value.trim(), lite: true })
    })
      .then(function (r) { return r.json(); })
      .then(function (b) {
        if (!b || !b.ok) { lock(REFUSALS[b && b.reason] || REFUSALS.unknown); return; }
        $("cat-code").value = "";
        route();
      })
      .catch(function () { lock("Could not reach the server. Please try again."); })
      .then(function () { btn.disabled = false; });
  });

  /* -------------------------------------------------------------- routing */

  function route() {
    var t = token();
    if (t) return openReport(t);
    get("/api/campaigns").then(function (b) {
      unlocked();
      var list = b.campaigns || [];
      if (list.length === 1) { location.hash = "t=" + list[0].token; return; }
      showList(list);
    }).catch(function (err) { if (err && err.locked) lock(); else empty("Could not load your campaigns. Please try again."); });
  }

  function showList(list) {
    $("cmp-report").hidden = true;
    $("cmp-back").hidden = true;
    $("cmp-title").textContent = "Campaigns";
    $("cmp-lead").textContent = list.length ? "Choose a campaign to see its results." : "";
    $("cmp-fresh").textContent = "";
    if (!list.length) { empty("There are no campaign reports for this code yet."); return; }
    $("cmp-empty").hidden = true;
    $("cmp-list").hidden = false;
    $("cmp-list-items").innerHTML = list.map(function (c) {
      return '<a href="#t=' + esc(c.token) + '"><div><strong>' + esc(c.name) + '</strong><div class="cmp-post__meta">'
        + esc(c.client || "") + (c.starts_at ? " · " + day(c.starts_at) + " – " + day(c.ends_at) : "") + '</div></div>'
        + '<span class="cmp-status' + (c.status === "live" ? " cmp-status--live" : "") + '">' + esc(c.status) + '</span></a>';
    }).join("");
  }

  function empty(msg) {
    $("cmp-report").hidden = true;
    $("cmp-list").hidden = true;
    $("cmp-empty").textContent = msg;
    $("cmp-empty").hidden = false;
  }

  function openReport(t) {
    get("/api/campaign?t=" + encodeURIComponent(t)).then(function (b) {
      unlocked();
      REPORT = b.report;
      FILTER = { platform: "", kind: "", creator: "", section: "campaign" };
      render(t);
    }).catch(function (err) {
      if (err && err.locked) return lock();
      unlocked();
      empty("This report is not available with your access code.");
    });
  }

  window.addEventListener("hashchange", route);

  /* --------------------------------------------------------------- render */

  function render(t) {
    var r = REPORT, c = r.campaign, tot = r.total, vis = r.visibility;
    $("cmp-list").hidden = true;
    $("cmp-empty").hidden = true;
    $("cmp-report").hidden = false;
    $("cmp-back").hidden = false;
    document.title = c.name + " — Campaign report — HelloVoice";
    $("cmp-title").textContent = c.name;
    $("cmp-lead").textContent = [c.client, c.starts_at ? day(c.starts_at) + " – " + day(c.ends_at) : "",
      c.status === "live" ? "Live" : (c.status === "ended" ? "Completed" : "")].filter(Boolean).join(" · ");
    $("cmp-fresh").textContent = "Data updated every 24 hours" + (r.updated_at ? " · last update " + ago(r.updated_at) : "");

    var k = [["Creators", r.creators.length], ["Posts", tot.posts], ["Views", num(tot.views)]];
    if (vis.reach) {
      k.push(["Reach", num(tot.reach), tot.real_share >= 0.999 ? "from insights" : (tot.real_share > 0 ? Math.round(tot.real_share * 100) + "% from insights" : "estimated")]);
      k.push(["Impressions", num(tot.impressions), "posts & stories"]);
    }
    k.push(["Engagement", num(tot.engagement)], ["Avg ER", pct(tot.er)]);
    if (tot.video_er != null) k.push(["Video ER", pct(tot.video_er)]);
    if (vis.clicks) k.push(["Link clicks", num(tot.clicks), tot.ctr != null ? "CTR " + tot.ctr.toFixed(2) + "%" : ""]);
    if (vis.emv && tot.emv != null) k.push(["EMV", sar(tot.emv), "earned media value"]);
    $("cmp-kpis").innerHTML = k.map(function (x) {
      return "<div><dt>" + esc(x[0]) + "</dt><dd>" + esc(x[1]) + (x[2] ? "<small>" + esc(x[2]) + "</small>" : "") + "</dd></div>";
    }).join("");
    $("cmp-kpi-note").textContent = "Counts posts that carry the campaign's hashtags, mentions or keywords within the campaign dates.";

    renderChart(r.history);
    renderCreators(r.creators, vis, tot);
    renderFilters();
    renderPosts();
    renderClicks(r.clicks, vis);
    $("cmp-csv").href = API + "/api/campaign.csv?t=" + encodeURIComponent(t);
    $("cmp-method").innerHTML = "Engagement = likes + comments. ER = engagement ÷ followers (videos: ÷ views). "
      + (vis.reach ? "Reach and impressions marked <em>est.</em> are estimates until the creator's own insights are approved; "
         + "video reach is its views. " : "")
      + (vis.emv && tot.emv != null ? "EMV values each view, impression and interaction at agreed SAR rates. " : "")
      + (vis.clicks ? "Clicks count people, not link previews or bots." : "");
  }

  function renderChart(h) {
    var box = $("cmp-chart");
    if (!h || !h.length) { box.innerHTML = '<p class="cmp-post__meta">The chart fills in as posts are captured.</p>'; return; }
    // Drawn at the panel's own width so the labels stay legible on a phone
    // instead of a 960px drawing shrunk to a third.
    var W = Math.max(320, Math.min(960, (box.clientWidth || 960) - 44)), H = W < 600 ? 220 : 260;
    var L = 48, R = 10, T = 14, B = 30, pw = W - L - R, ph = H - T - B;
    var peak = Math.max.apply(null, h.map(function (d) { return Math.max(d.views, d.likes + d.comments); }).concat([1]));
    var mag = Math.pow(10, Math.floor(Math.log10(peak))), top = Math.ceil(peak / mag) * mag;
    function x(i) { return L + (h.length === 1 ? pw / 2 : pw * i / (h.length - 1)); }
    function y(v) { return T + ph - v / top * ph; }
    function line(key, colour) {
      var pts = h.map(function (d, i) { return x(i).toFixed(1) + "," + y(key(d)).toFixed(1); });
      return '<polyline fill="none" stroke="' + colour + '" stroke-width="3" stroke-linejoin="round" points="' + pts.join(" ") + '"/>'
        + h.map(function (d, i) { return '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(key(d)).toFixed(1) + '" r="3.5" fill="' + colour + '"><title>' + esc(d.d) + ": " + full(key(d)) + "</title></circle>"; }).join("");
    }
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Views and engagement over time">';
    for (var g = 0; g <= 4; g++) {
      var v = top * g / 4, yy = y(v).toFixed(1);
      s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + yy + '" y2="' + yy + '" stroke="#e9dcd2"/>'
        + '<text x="' + (L - 8) + '" y="' + (+yy + 4) + '" text-anchor="end" font-size="12" fill="#383838">' + num(v) + "</text>";
    }
    var every = Math.max(1, Math.ceil(h.length / (W < 600 ? 4 : 8)));
    h.forEach(function (d, i) {
      if (i % every && i !== h.length - 1) return;
      s += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 8) + '" text-anchor="middle" font-size="12" fill="#383838">' + esc(d.d.slice(5)) + "</text>";
    });
    s += line(function (d) { return d.views; }, "#121212") + line(function (d) { return d.likes + d.comments; }, "#ff691e") + "</svg>";
    box.className = "cmp-panel cmp-chart";
    box.innerHTML = s + '<div class="cmp-legend"><span><i style="background:#121212"></i>Views</span><span><i style="background:#ff691e"></i>Engagement</span></div>';
  }

  function renderCreators(list, vis, tot) {
    var cols = [["Creator", function (c) { return esc(c.name); }], ["Posts", function (c) { return c.posts; }],
      ["Views", function (c) { return full(c.views); }]];
    if (vis.reach) cols.push(["Reach", function (c) { return full(c.reach); }]);
    cols.push(["Engagement", function (c) { return full(c.engagement); }], ["ER", function (c) { return pct(c.er); }]);
    if (vis.clicks) cols.push(["Clicks", function (c) { return full(c.clicks); }]);
    if (vis.emv && tot.emv != null) cols.push(["EMV", function (c) { return sar(c.emv); }]);
    var foot = { name: "Total", posts: tot.posts, views: tot.views, reach: tot.reach, engagement: tot.engagement,
      er: tot.er, clicks: tot.clicks, emv: tot.emv };
    $("cmp-creators").innerHTML = "<thead><tr>" + cols.map(function (c) { return "<th>" + c[0] + "</th>"; }).join("") + "</tr></thead><tbody>"
      + list.slice().sort(function (a, b) { return (b.views + b.engagement) - (a.views + a.engagement); }).map(function (c) {
        return "<tr>" + cols.map(function (col) { return "<td>" + col[1](c) + "</td>"; }).join("") + "</tr>";
      }).join("") + "</tbody><tfoot><tr>" + cols.map(function (col) { return "<td>" + col[1](foot) + "</td>"; }).join("") + "</tr></tfoot>";
  }

  var KIND = { post: "Post", reel: "Reel", story: "Story", video: "Video", short: "Short" };

  function renderFilters() {
    var posts = REPORT.posts, vis = REPORT.visibility;
    function uniq(f) { var s = {}; posts.forEach(function (p) { s[f(p)] = 1; }); return Object.keys(s).sort(); }
    var groups = [];
    if (vis.all_content) groups.push(["section", [["campaign", "Campaign posts"], ["", "All content"]]]);
    var plats = uniq(function (p) { return p.platform; });
    if (plats.length > 1) groups.push(["platform", [["", "All platforms"]].concat(plats.map(function (p) { return [p, p]; }))]);
    var kinds = uniq(function (p) { return p.kind; });
    if (kinds.length > 1) groups.push(["kind", [["", "All types"]].concat(kinds.map(function (k) { return [k, KIND[k] || k]; }))]);
    $("cmp-filters").innerHTML = groups.map(function (g) {
      return g[1].map(function (o) {
        return '<button type="button" class="cmp-chip" data-k="' + g[0] + '" data-v="' + esc(o[0]) + '" aria-pressed="'
          + (FILTER[g[0]] === o[0]) + '">' + esc(o[1]) + "</button>";
      }).join("");
    }).join('<span style="width:12px"></span>');
  }

  $("cmp-filters").addEventListener("click", function (e) {
    var b = e.target.closest(".cmp-chip");
    if (!b) return;
    FILTER[b.getAttribute("data-k")] = b.getAttribute("data-v");
    renderFilters();
    renderPosts();
  });

  function renderPosts() {
    var vis = REPORT.visibility;
    var list = REPORT.posts.filter(function (p) {
      return (!FILTER.section || p.section === FILTER.section) && (!FILTER.platform || p.platform === FILTER.platform)
        && (!FILTER.kind || p.kind === FILTER.kind);
    });
    if (!list.length) { $("cmp-posts").innerHTML = '<p class="cmp-post__meta">No posts captured yet.</p>'; return; }
    $("cmp-posts").innerHTML = list.map(function (p) {
      var nums = [];
      var est = function (real) { return real ? "" : ' <span class="cmp-est">est.</span>'; };
      if (p.video) nums.push(["Views", num(p.views)]);
      else if (vis.reach) nums.push(["Reach", num(p.reach) + est(p.reach_real)]);
      if (p.story && vis.reach) nums.push(["Impressions", num(p.impressions) + est(p.impressions_real)]);
      if (!p.story) nums.push(["Likes", num(p.likes)], ["Comments", num(p.comments)]);
      if (!p.story) nums.push(["ER", pct(p.video ? p.video_er : p.er)]);
      var img = p.thumb ? '<img src="' + esc(p.thumb) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">' : "";
      return '<article class="cmp-post"><div class="cmp-post__media"><span class="cmp-post__tag">' + esc(p.platform) + " · " + esc(KIND[p.kind] || p.kind)
        + "</span>" + img + esc((p.platform || "").toUpperCase()) + '</div><div class="cmp-post__body"><div><div class="cmp-post__who">'
        + esc(p.creator) + '</div><div class="cmp-post__meta">' + esc(day(p.posted_at)) + "</div></div>"
        + '<dl class="cmp-post__nums">' + nums.slice(0, 6).map(function (n) { return "<div><dt>" + n[0] + "</dt><dd>" + n[1] + "</dd></div>"; }).join("")
        + '</dl><a class="cmp-post__link" href="' + esc(p.url) + '" target="_blank" rel="noopener">View post ↗</a></div></article>';
    }).join("");
  }

  function bars(title, rows) {
    if (!rows || !rows.length) return "";
    var peak = Math.max.apply(null, rows.map(function (r) { return r.n; }));
    return '<div class="cmp-panel cmp-bars"><h3>' + esc(title) + "</h3>" + rows.slice(0, 10).map(function (r) {
      return '<div class="cmp-bar"><span>' + esc(r.k) + '</span><i style="--w:' + (r.n / peak * 100).toFixed(1) + '%"></i><b>' + full(r.n) + "</b></div>";
    }).join("") + "</div>";
  }

  function renderClicks(cl, vis) {
    var wrap = $("cmp-clicks-wrap");
    if (!vis.clicks || !cl || !cl.clicks) { wrap.hidden = true; return; }
    wrap.hidden = false;
    $("cmp-clicks").innerHTML = bars("By creator", cl.by_creator) + bars("By app", cl.by_app)
      + bars("By country", cl.by_country) + bars("By device", cl.by_device);
  }

  $("cmp-print").addEventListener("click", function () { window.print(); });
  $("cmp-back").addEventListener("click", function (e) { e.preventDefault(); location.hash = ""; route(); });

  route();
})();
