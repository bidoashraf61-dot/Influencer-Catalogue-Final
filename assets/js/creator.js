/* Creator analysis — the talent passport. GET /api/creator?c=<code> returns
   the creator's card facts always and their full analysis when one is on
   file; without one the page is sealed and offers "Request full analysis"
   (POST /api/creator/request), which lands in the admin's inbox.
   Link: /creator/#c=HV-MC-001 */
(function () {
  "use strict";

  var API = (window.CREATOR_CONFIG || {}).api || "/admin";
  // Opened inside the roster's side panel: no page chrome, and links leave
  // the panel for the full window.
  if (/[?&]embed=1\b/.test(location.search)) {
    document.documentElement.classList.add("pp-embed");
    var base = document.createElement("base"); base.target = "_top"; document.head.appendChild(base);
    // Keep the roster's frost-on-leave working while focus is in here.
    try {
      var host = window.parent.document.body;
      window.addEventListener("blur", function () { setTimeout(function () { if (!window.parent.document.hasFocus()) host.classList.add("cat-away"); }, 0); });
      window.addEventListener("focus", function () { host.classList.remove("cat-away"); });
    } catch (e) {}
  }
  var ICONS = (window.HV_ICONS || {}).icons || {};
  var ICON_LINK = (window.HV_ICONS || {}).link || "";
  var D = null;
  var BANDS = { nano: "Nano", micro: "Micro", mid: "Mid-tier", macro: "Macro", mega: "Mega" };
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
    if (v == null || v === "") return "—";
    var n = Math.round(v), a = Math.abs(n);
    if (a >= 1e6) return (n / 1e6).toFixed(a >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
    if (a >= 1e4) return (n / 1e3).toFixed(a >= 1e5 ? 0 : 1).replace(/\.0$/, "") + "K";
    return n.toLocaleString("en-US");
  }
  function pct(v, d) { return v == null ? "—" : (+v).toFixed(d == null ? 1 : d) + "%"; }
  function grade(v, pair) { if (v == null || !pair) return null; return v >= pair[0] ? "good" : (v >= pair[1] ? "moderate" : "low"); }
  function sig(g, title) { return g ? '<span class="pp-sig pp-sig--' + g + '"' + (title ? ' title="' + esc(title) + '"' : "") + ">" + SIG[g] + "</span>" : ""; }
  function flag(cc) { return '<span class="fi fi-' + esc(String(cc).toLowerCase()) + '" aria-hidden="true"></span>'; }
  function icon(p) { return ICONS[p] || ICON_LINK; }
  function code() { var m = /(?:^|[#&])c=([A-Za-z0-9-]+)/.exec(location.hash || ""); return m ? decodeURIComponent(m[1]).toUpperCase() : ""; }

  /* gate */
  var REFUSALS = { revoked: "This code has been withdrawn.", expired: "This code has expired.", exhausted: "This code has been used up.",
    devices: "This code is already open on its maximum number of devices.", unknown: "That code is not right." };
  function lock(msg) {
    $("cat-app").hidden = true; $("cat-gate").hidden = false; document.body.classList.add("cat-locked");
    if (msg) { $("cat-gate-error").textContent = msg; $("cat-gate-error").hidden = false; }
  }
  function unlocked() { $("cat-gate").hidden = true; $("cat-app").hidden = false; document.body.classList.remove("cat-locked"); }
  $("cat-gate-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var btn = this.querySelector("button"); btn.disabled = true;
    fetch(API + "/api/unlock", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: $("cat-code").value.trim(), lite: true }) })
      .then(function (r) { return r.json(); })
      .then(function (b) { if (!b || !b.ok) lock(REFUSALS[b && b.reason] || REFUSALS.unknown); else { $("cat-code").value = ""; load(); } })
      .catch(function () { lock("Could not reach the server. Please try again."); })
      .then(function () { btn.disabled = false; });
  });
  if (document.referrer && document.referrer.indexOf(location.origin) === 0) {
    $("pp-back").addEventListener("click", function (e) { e.preventDefault(); history.back(); });
  }

  function load() {
    var c = code();
    if (!c) { unlocked(); $("pp-empty").textContent = "No creator chosen. Open one from the catalogue."; $("pp-empty").hidden = false; return; }
    fetch(API + "/api/creator?c=" + encodeURIComponent(c), { credentials: "include", cache: "no-store" })
      .then(function (r) {
        if (r.status === 401) { lock(); return null; }
        if (!r.ok) { unlocked(); $("pp-empty").textContent = "That creator is not in the catalogue."; $("pp-empty").hidden = false; return null; }
        return r.json();
      })
      .then(function (b) { if (b) { D = b; unlocked(); render(); } })
      .catch(function () { unlocked(); $("pp-empty").textContent = "Could not load this creator. Please try again."; $("pp-empty").hidden = false; });
  }
  window.addEventListener("hashchange", load);

  /* --------------------------------------------------------------- render */

  function render() {
    var c = D.creator, a = D.analysis;
    document.title = c.name + " — Creator analysis — HelloVoice";
    window.scrollTo(0, 0);
    renderId(c, a);
    $("pp-sealed").hidden = !!a;
    $("pp-pages").hidden = !a;
    if (!a) return renderSealed(c);
    renderStats(c, a);
    renderAudience(a);
    renderReal(a);
    renderContent(a);
    renderNetwork(a);
    $("pp-source").textContent = "Data: " + (a.source || "HelloVoice analysis") + (a.updated ? ", " + a.updated : "")
      + ". Benchmarks are industry guides by creator size.";
  }

  function renderId(c, a) {
    // One follower count per platform: the analysed figure where the
    // analysis covers that platform, the catalogue's otherwise.
    var handles = (c.profiles || []).filter(function (p) { return p.url; }).map(function (p) {
      var n = (a && a.followers && (!a.platform || a.platform === p.platform)) ? a.followers : p.followers;
      return '<a class="pp-handle" href="' + esc(p.url) + '" target="_blank" rel="noopener">' + icon(p.platform) + esc(p.platform)
        + (n ? " · " + num(n) : "") + "</a>";
    }).join("");
    var fields = [["Code", c.code], ["Tier", c.tier || BANDS[c.band]], ["Based in", c.city || "—"],
      ["Followers", num(a && a.followers || c.followers)]];
    if (c.interest) fields.push(["Interests", String(c.interest).split(/[,،]/).slice(0, 3).join(", ")]);
    $("pp-id").innerHTML = '<div class="pp-photo">' + (c.photo_url ? '<img src="' + esc(c.photo_url) + '" alt="' + esc(c.name) + '">'
      : '<span class="pp-photo__none">' + esc(c.code.split("-").pop()) + "</span>") + "</div>"
      + '<div class="pp-fields"><h1 class="pp-name">' + esc(c.name) + "</h1>"
      + '<div class="pp-handles">' + handles + '</div><dl class="pp-dl">'
      + fields.map(function (f) { return "<div><dt>" + f[0] + "</dt><dd>" + esc(f[1]) + "</dd></div>"; }).join("") + "</dl></div>"
      + (a ? '<div class="pp-seal pp-seal--ok" aria-label="Fully analysed">Analysed<small>' + esc(a.updated || "") + "</small></div>"
         : '<div class="pp-seal pp-seal--locked" aria-label="Analysis not on file">Sealed<small>not analysed</small></div>');
  }

  function renderSealed(c) {
    var asked = D.requested;
    $("pp-sealed").innerHTML = '<div class="pp-cover"><div><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/></svg><br>Talent<br>passport</div></div>'
      + "<div><h2>Full analysis not on file yet</h2><p>We have " + esc(c.name) + "'s basics above. The full analysis adds audience countries and cities, age and gender, how much of the audience is real, follower growth, top and sponsored posts and the brands they have worked with.</p>"
      + '<button type="button" class="pp-btn" id="pp-ask"' + (asked ? " disabled" : "") + ">" + (asked ? "Requested" : "Request full analysis") + "</button>"
      + '<p class="pp-sealed__done" id="pp-ask-done"' + (asked ? "" : " hidden") + ">Your request is with the HelloVoice team — we will add it and let you know.</p></div>";
    var btn = $("pp-ask");
    if (btn && !asked) btn.addEventListener("click", function () {
      btn.disabled = true; btn.textContent = "Sending…";
      fetch(API + "/api/creator/request", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: c.code }) })
        .then(function (r) { if (!r.ok) throw 0; btn.textContent = "Requested"; $("pp-ask-done").hidden = false; D.requested = true; })
        .catch(function () { btn.disabled = false; btn.textContent = "Request full analysis"; var n = $("pp-ask-done"); n.textContent = "Could not send the request. Please try again."; n.hidden = false; });
    });
  }

  function renderStats(c, a) {
    var bm = D.benchmarks || {}, pair = (bm.er || {})[c.band], items = [];
    items.push(["Followers", num(a.followers || c.followers), a.following ? num(a.following) + " following" : ""]);
    items.push(["Engagement rate", pct(a.er, 2), sig(grade(a.er, pair), pair ? "Strong from " + pair[0] + "% for " + BANDS[c.band] + " creators" : "")
      + (pair ? " <span>" + BANDS[c.band] + " benchmark " + pair[0] + "%</span>" : "")]);
    if (a.avg_likes != null) items.push(["Avg likes", num(a.avg_likes), ""]);
    if (a.avg_comments != null) items.push(["Avg comments", num(a.avg_comments), ""]);
    if (a.avg_views != null) items.push(["Avg views", num(a.avg_views), a.followers ? Math.round(a.avg_views / a.followers * 100) + "% of followers" : ""]);
    if (a.avg_reel_plays != null) items.push(["Avg reel plays", num(a.avg_reel_plays), ""]);
    if (a.paid_post_performance != null) items.push(["Sponsored vs organic", pct(a.paid_post_performance, 1), "engagement on paid posts vs normal posts"]);
    if (a.posts_count != null) items.push(["Posts", num(a.posts_count), ""]);
    $("pp-stats").innerHTML = items.map(function (i) {
      return "<div><dt>" + i[0] + "</dt><dd>" + esc(i[1]) + (i[2] ? "<small>" + i[2] + "</small>" : "") + "</dd></div>";
    }).join("");
  }

  function bars(rows, key, colour) {
    if (!rows || !rows.length) return "";
    var peak = Math.max.apply(null, rows.map(function (r) { return r.pct || 0; })) || 1;
    return rows.slice(0, 8).map(function (r) {
      return '<div class="pp-bar"><span>' + key(r) + '</span><i style="--w:' + ((r.pct || 0) / peak * 100).toFixed(1) + "%"
        + (colour ? ";--c:" + colour : "") + '"></i><b>' + pct(r.pct, 0) + "</b></div>";
    }).join("");
  }

  function renderAudience(a) {
    var au = a.audience || {}, panels = [];
    var cs = au.countries || [];
    $("pp-stamps").innerHTML = cs.slice(0, 6).map(function (c, i) {
      return '<div class="pp-stamp' + (i === 0 ? " pp-stamp--lead" : "") + '">' + flag(c.code) + "<b>" + pct(c.pct, 0) + "</b><span>"
        + esc(countryName(c.code)) + "</span></div>";
    }).join("") || '<p class="pp-panel">No audience countries on file.</p>';
    if (au.cities && au.cities.length) panels.push('<div class="pp-panel"><h3>Top cities</h3>' + bars(au.cities, function (r) { return esc(r.name); }) + "</div>");
    if (au.gender) {
      var f = +au.gender.female || 0, m = +au.gender.male || 0, t = f + m || 1;
      panels.push('<div class="pp-panel"><h3>Gender</h3><div class="pp-split" role="img" aria-label="' + Math.round(f / t * 100) + '% women">'
        + '<i style="width:' + (f / t * 100) + '%;background:#ff691e">' + Math.round(f / t * 100) + "%</i>"
        + '<i style="width:' + (m / t * 100) + '%;background:#121212">' + Math.round(m / t * 100) + "%</i></div>"
        + "<p><b style=\"color:#ff691e\">Women</b> · <b>Men</b></p></div>");
    }
    if (au.ages && au.ages.length) {
      var ages = au.ages.slice().sort(function (x, y) { return String(x.name).localeCompare(String(y.name), "en", { numeric: true }); });
      panels.push('<div class="pp-panel"><h3>Age</h3>' + bars(ages, function (r) { return esc(r.name); }, "#ff691e") + "</div>");
    }
    if (au.languages && au.languages.length) panels.push('<div class="pp-panel"><h3>Languages</h3>' + bars(au.languages, function (r) { return esc(r.name); }) + "</div>");
    if (au.reachability && au.reachability.length) panels.push('<div class="pp-panel"><h3>Reachability</h3>' + bars(au.reachability, function (r) { return esc(r.name) + " following"; })
      + "<p>Followers who follow fewer accounts see more of each post.</p></div>");
    if (au.interests && au.interests.length) panels.push('<div class="pp-panel"><h3>Audience interests</h3><div class="pp-chips">'
      + au.interests.slice(0, 12).map(function (r) { return '<span class="pp-chip">' + esc(r.name) + " <b>" + pct(r.pct, 0) + "</b></span>"; }).join("") + "</div></div>");
    if (au.brand_affinity && au.brand_affinity.length) panels.push('<div class="pp-panel"><h3>Brands the audience loves</h3><div class="pp-chips">'
      + au.brand_affinity.slice(0, 12).map(function (r) { return '<span class="pp-chip">' + esc(r.name) + (r.pct != null ? " <b>" + pct(r.pct, 0) + "</b>" : "") + "</span>"; }).join("") + "</div></div>");
    $("pp-aud").innerHTML = panels.join("");
  }

  function gauge(value, g) {
    var v = Math.max(0, Math.min(100, value || 0)), ang = Math.PI * (1 - v / 100);
    var x = 100 + 80 * Math.cos(ang), y = 100 - 80 * Math.sin(ang);
    var col = { good: "#14884a", moderate: "#e2780f", low: "#ee1515" }[g] || "#121212";
    return '<svg viewBox="0 0 200 112" role="img" aria-label="Audience credibility ' + v + '%">'
      + '<path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke="#efece6" stroke-width="18" stroke-linecap="round"/>'
      + '<path d="M20 100 A80 80 0 0 1 ' + x.toFixed(1) + " " + y.toFixed(1) + '" fill="none" stroke="' + col + '" stroke-width="18" stroke-linecap="round"/></svg>';
  }

  function renderReal(a) {
    var cred = a.credibility_pct != null ? +a.credibility_pct : (a.audience && a.audience.credibility_pct != null ? +a.audience.credibility_pct
      : (a.fake_followers_pct != null ? 100 - a.fake_followers_pct : null));
    if (cred == null) $("pp-cred").innerHTML = '<p class="pp-panel">Credibility not on file.</p>';
    else {
      var g = cred >= 80 ? "good" : (cred >= 65 ? "moderate" : "low");
      $("pp-cred").innerHTML = '<div class="pp-gauge">' + gauge(cred, g) + '<div class="pp-gauge__txt"><b>' + pct(cred, 0) + "</b>" + sig(g)
        + "<p>Share of followers that look like real people" + (a.fake_followers_pct != null ? " — " + pct(a.fake_followers_pct, 0) + " look like bots or inactive accounts" : "")
        + ". Strong from 80%.</p></div></div>";
    }
    var gr = (a.growth || []).filter(function (x) { return x.followers; });
    if (gr.length < 2) { $("pp-growth").innerHTML = '<p class="pp-panel">Growth history not on file.</p>'; return; }
    var W = 520, H = 200, L = 52, Rr = 10, T = 12, B = 28, pw = W - L - Rr, ph = H - T - B;
    var vals = gr.map(function (x) { return x.followers; }), lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var pad = (hi - lo) * 0.15 || hi * 0.05, y0 = Math.max(0, lo - pad), y1 = hi + pad;
    function px(i) { return L + pw * i / (gr.length - 1); }
    function py(v) { return T + ph - (v - y0) / (y1 - y0) * ph; }
    var pts = gr.map(function (d, i) { return px(i).toFixed(1) + "," + py(d.followers).toFixed(1); });
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Follower growth">';
    for (var g2 = 0; g2 <= 2; g2++) { var vv = y0 + (y1 - y0) * g2 / 2, yy = py(vv).toFixed(1);
      s += '<line x1="' + L + '" x2="' + (W - Rr) + '" y1="' + yy + '" y2="' + yy + '" stroke="#ece6dc"/><text x="' + (L - 8) + '" y="' + (+yy + 4) + '" text-anchor="end" font-size="12" fill="#5a5a5a">' + num(vv) + "</text>"; }
    s += '<polyline fill="none" stroke="#121212" stroke-width="3" stroke-linejoin="round" points="' + pts.join(" ") + '"/>';
    gr.forEach(function (d, i) { if (i % Math.max(1, Math.ceil(gr.length / 6)) && i !== gr.length - 1) return;
      s += '<text x="' + px(i).toFixed(1) + '" y="' + (H - 8) + '" text-anchor="middle" font-size="12" fill="#5a5a5a">' + esc(d.month) + "</text>"; });
    s += "</svg>";
    var change = (vals[vals.length - 1] - vals[0]) / vals[0] * 100;
    $("pp-growth").innerHTML = '<div class="pp-chart">' + s + "<p>" + (change >= 0 ? "+" : "") + change.toFixed(1) + "% followers over "
      + gr.length + " months</p></div>";
  }

  function posts(list, sponsored) {
    return '<div class="pp-posts">' + list.slice(0, 8).map(function (p) {
      return '<article class="pp-post"><div class="pp-post__media">' + ICON_LINK + (p.thumb ? '<img src="' + esc(p.thumb) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">' : "")
        + (sponsored && p.brand ? '<span class="pp-post__brand">' + esc(p.brand) + "</span>" : "") + '</div><div class="pp-post__body"><div class="pp-post__nums">'
        + (p.likes != null ? "<span><b>" + num(p.likes) + "</b> likes</span>" : "") + (p.comments != null ? "<span><b>" + num(p.comments) + "</b> comments</span>" : "")
        + (p.views != null ? "<span><b>" + num(p.views) + "</b> views</span>" : "") + "</div>"
        + (p.date ? '<span style="color:#5a5a5a">' + esc(p.date) + "</span>" : "")
        + '<a class="pp-post__go" href="' + esc(p.url) + '" target="_blank" rel="noopener">View post ↗</a></div></article>';
    }).join("") + "</div>";
  }

  function renderContent(a) {
    var out = "";
    if (a.top_posts && a.top_posts.length) out += '<h3 class="pp-h3">Top posts</h3>' + posts(a.top_posts, false);
    if (a.sponsored_posts && a.sponsored_posts.length) out += '<h3 class="pp-h3">Sponsored posts</h3>' + posts(a.sponsored_posts, true);
    $("pp-content-sec").hidden = !out;
    $("pp-content").innerHTML = out;
  }

  function renderNetwork(a) {
    var panels = [];
    if (a.brands && a.brands.length) panels.push('<div class="pp-panel"><h3>Brands worked with</h3><div class="pp-chips">'
      + a.brands.map(function (b) { return '<span class="pp-chip">' + esc(b.name) + (b.count ? " <b>×" + b.count + "</b>" : "") + "</span>"; }).join("") + "</div></div>");
    if (a.hashtags && a.hashtags.length) panels.push('<div class="pp-panel"><h3>Hashtags &amp; mentions</h3><div class="pp-chips">'
      + a.hashtags.map(function (b) { return '<span class="pp-chip">' + esc(b.tag) + (b.count ? " <b>" + b.count + "</b>" : "") + "</span>"; }).join("") + "</div></div>");
    function people(list) { return '<div class="pp-people">' + list.slice(0, 10).map(function (p) {
      var name = p.code ? '<a href="#c=' + encodeURIComponent(p.code) + '">' + esc(p.name || p.handle) + "</a>" : "<b>" + esc(p.name || p.handle) + "</b>";
      return '<div class="pp-person"><span>' + name + (p.handle ? ' <span style="color:#5a5a5a">@' + esc(String(p.handle).replace(/^@/, "")) + "</span>" : "") + "</span><span>" + num(p.followers) + "</span></div>";
    }).join("") + "</div>"; }
    if (a.notable_followers && a.notable_followers.length) panels.push('<div class="pp-panel"><h3>Notable followers</h3>' + people(a.notable_followers) + "</div>");
    if (a.lookalikes && a.lookalikes.length) panels.push('<div class="pp-panel"><h3>Similar creators</h3>' + people(a.lookalikes) + "</div>");
    $("pp-net-sec").hidden = !panels.length;
    $("pp-net").innerHTML = panels.join("");
  }

  load();
})();
