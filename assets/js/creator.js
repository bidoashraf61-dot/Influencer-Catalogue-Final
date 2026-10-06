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
  // The analysis mark — bars and a trend line — shared with the roster's button.
  var ICON_ANALYSIS = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h16"/><path d="M7 16v-4M11 16V9M15 16v-6M19 16V6"/><path d="M5 9l5-4 4 3 6-5"/></svg>';
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
  function sig(g, title, words) { return g ? '<span class="pp-sig pp-sig--' + g + '"' + (title ? ' title="' + esc(title) + '"' : "") + ">" + (words || SIG)[g] + "</span>" : ""; }
  // For shares where lower is better (fake followers, fake likers).
  var FAKE = { good: "Healthy", moderate: "Watch", low: "High" };
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

  function ico(d) { return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + d + "</svg>"; }
  var I_LIKE = ico('<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>');
  var I_COMMENT = ico('<path d="M4 5h16v11H9l-5 4z"/>');
  var I_PLAY = ico('<path d="M8 5l11 7-11 7z"/>');
  function render() {
    var c = D.creator, a = D.analysis;
    document.title = c.name + " — Creator analysis — HelloVoice";
    window.scrollTo(0, 0);
    renderId(c, a);
    $("pp-sealed").hidden = !!a;
    $("pp-pages").hidden = !a;
    if (!a) return renderSealed(c);
    renderPerf(c, a);
    renderNetwork(a);
    renderPosts(a);
    renderReal(a);
    renderAudience(a);
  }

  function erPair(c) { return ((D.benchmarks || {}).er || {})[c.band]; }

  /* identity: who, where, the three numbers a brand asks first, and the seal */
  function renderId(c, a) {
    var handles = (c.profiles || []).filter(function (p) { return p.url; }).map(function (p) {
      var mine = a && a.followers && (!a.platform || a.platform === p.platform);
      var n = mine ? a.followers : p.followers;
      return '<a class="pp-handle' + (mine ? " is-analysed" : "") + '" href="' + esc(p.url) + '" target="_blank" rel="noopener">' + icon(p.platform)
        + "<span>" + esc(p.platform) + "</span>" + (n ? "<b>" + num(n) + "</b>" : "") + (mine && a.er != null ? "<em>" + pct(a.er, 2) + " ER</em>" : "") + "</a>";
    }).join("");
    var line = [a && a.handle ? "@" + String(a.handle).replace(/^@/, "") : "", a && a.account_type ? a.account_type + " account" : "", c.city || ""].filter(Boolean);
    var g = a ? grade(a.er, erPair(c)) : null;
    var key = a ? [
      ["Followers", num(a.followers || c.followers), ""],
      ["Avg likes", num(a.avg_likes), ""],
      ["Engagement rate", pct(a.er, 2), sig(g, erPair(c) ? "Strong from " + erPair(c)[0] + "% for " + BANDS[c.band] + " creators" : "")],
      ["Avg views", a.avg_views != null ? num(a.avg_views) : (a.avg_reel_plays != null ? num(a.avg_reel_plays) : "—"), ""]
    ] : [["Followers", num(c.followers), ""], ["Tier", c.tier || BANDS[c.band] || "—", ""], ["Based in", c.city || "—", ""]];
    $("pp-id").innerHTML = '<div class="pp-photo">' + (c.photo_url ? '<img src="' + esc(c.photo_url) + '" alt="' + esc(c.name) + '">'
      : '<span class="pp-photo__none">' + esc(c.code.split("-").pop()) + "</span>") + "</div>"
      + '<div class="pp-fields">'
      + (a ? '<p class="pp-badge pp-badge--ok"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5l2.4 1.8 3 .1.9 2.9 2.4 1.8-.9 2.9.9 2.9-2.4 1.8-.9 2.9-3 .1L12 21.5l-2.4-1.8-3-.1-.9-2.9-2.4-1.8.9-2.9-.9-2.9 2.4-1.8.9-2.9 3-.1z" fill="currentColor"/><path d="M8.2 12.3l2.6 2.6 5-5.2" fill="none" stroke="#e8ff76" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
           + "<span><b>Verified analysis</b>" + (a.updated ? "<small>Data from " + esc(day(a.updated)) + "</small>" : "") + "</span></p>"
         : '<p class="pp-badge pp-badge--locked"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/></svg><span><b>Not analysed yet</b><small>Basics only</small></span></p>')
      + '<h1 class="pp-name">' + esc(c.name) + "</h1>"
      + '<p class="pp-line"><span class="pp-code">' + esc(c.code) + "</span>" + line.map(esc).join(" · ") + (c.tier || c.band ? " · " + esc(c.tier || BANDS[c.band]) + " tier" : "") + "</p>"
      + '<div class="pp-handles">' + handles + "</div>"
      + '<dl class="pp-key">' + key.map(function (k) { return "<div><dt>" + k[0] + "</dt><dd>" + esc(k[1]) + (k[2] ? " " + k[2] : "") + "</dd></div>"; }).join("") + "</dl>"
      + (a ? '<div class="pp-actions"><button type="button" class="pp-btn pp-btn--ink" id="pp-print"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>Download PDF</button></div>' : "")
      + "</div>";
    var pb = $("pp-print"); if (pb) pb.addEventListener("click", function () { window.print(); });
  }
  function day(iso) { var d = new Date(String(iso).slice(0, 10) + "T00:00:00Z"); return isNaN(d) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }); }

  function renderSealed(c) {
    var asked = D.requested;
    $("pp-sealed").innerHTML = '<div class="pp-sealed__icon" aria-hidden="true">' + ICON_ANALYSIS + "</div>"
      + "<div><h2>Full analysis not on file yet</h2><p>The full analysis shows where " + esc(c.name) + "'s audience lives, their age and gender, how much of it is real, how it has grown, how posts perform and the brands they have worked with.</p>"
      + '<ul class="pp-sealed__list"><li>Audience countries, cities, age &amp; gender</li><li>Real vs fake followers</li><li>Engagement against their tier</li><li>Brands &amp; sponsored posts</li></ul>'
      + '<button type="button" class="pp-btn" id="pp-ask"' + (asked ? " disabled" : "") + ">" + (asked ? "Requested ✓" : "Request full analysis") + "</button>"
      + '<p class="pp-sealed__done" id="pp-ask-done"' + (asked ? "" : " hidden") + ">Your request is with the HelloVoice team — we will add it and let you know.</p></div>";
    var btn = $("pp-ask");
    if (btn && !asked) btn.addEventListener("click", function () {
      btn.disabled = true; btn.textContent = "Sending…";
      fetch(API + "/api/creator/request", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: c.code }) })
        .then(function (r) { if (!r.ok) throw 0; btn.textContent = "Requested ✓"; $("pp-ask-done").hidden = false; D.requested = true; })
        .catch(function () { btn.disabled = false; btn.textContent = "Request full analysis"; var n = $("pp-ask-done"); n.textContent = "Could not send the request. Please try again."; n.hidden = false; });
    });
  }

  /* tabs shared by Performance and Audience */
  function tabs(box, pane, list, draw) {
    var on = 0;
    function paint() {
      $(box).innerHTML = list.length > 1 ? list.map(function (t, i) { return '<button type="button" role="tab" aria-selected="' + (i === on) + '" data-i="' + i + '">' + esc(t.label) + "</button>"; }).join("") : "";
      $(pane).innerHTML = list.map(function (t, i) { return '<div class="pp-pane" data-tab="' + esc(t.label) + '"' + (i === on ? "" : " hidden") + ">" + draw(t) + "</div>"; }).join("");
    }
    paint();
    $(box).onclick = function (e) { var b = e.target.closest("button[data-i]"); if (!b) return; on = +b.getAttribute("data-i"); paint(); };
  }

  /* one metric row: label, a bar against the largest in its group, the value */
  function rows(items) {
    var peak = Math.max.apply(null, items.map(function (r) { return r.v || 0; }).concat([1]));
    return '<div class="pp-rows">' + items.map(function (r) {
      return '<div class="pp-row"><span>' + r.label + (r.tip ? ' <i class="pp-tip" tabindex="0" data-tip="' + esc(r.tip) + '">i</i>' : "") + '</span><i class="pp-row__bar"><b style="width:' + Math.max(2, (r.v || 0) / peak * 100).toFixed(1) + '%"></b></i><strong>' + r.text + "</strong></div>";
    }).join("") + "</div>";
  }

  function renderPerf(c, a) {
    var pair = erPair(c), list = [];
    function erBlock(v, label) {
      var g = grade(v, pair);
      return '<div class="pp-er"><span class="pp-er__label">' + label + '</span><b>' + pct(v, 2) + "</b>" + sig(g)
        + (pair ? "<p>" + ({ good: "Above", moderate: "Around", low: "Below" }[g] || "Compared with") + " the usual for " + BANDS[c.band] + " creators — strong from " + pair[0] + "%.</p>" : "") + "</div>";
    }
    var all = [];
    if (a.est_impressions != null) all.push({ label: "Estimated impressions", v: a.est_impressions, text: num(a.est_impressions), tip: "How many times posts are seen, on average." });
    if (a.est_reach != null) all.push({ label: "Estimated reach", v: a.est_reach, text: num(a.est_reach), tip: "How many different people see a post, on average." });
    if (a.avg_views != null) all.push({ label: "Average views", v: a.avg_views, text: num(a.avg_views) });
    if (a.avg_likes != null) all.push({ label: "Average likes", v: a.avg_likes, text: num(a.avg_likes) });
    if (a.avg_comments != null) all.push({ label: "Average comments", v: a.avg_comments, text: num(a.avg_comments) });
    list.push({ label: "All content", html: erBlock(a.er, "Engagement rate") + rows(all) });
    var reels = [];
    if (a.avg_reel_plays != null) reels.push({ label: "Average reel plays", v: a.avg_reel_plays, text: num(a.avg_reel_plays) });
    if (a.avg_reel_likes != null) reels.push({ label: "Average likes", v: a.avg_reel_likes, text: num(a.avg_reel_likes) });
    if (a.avg_reel_comments != null) reels.push({ label: "Average comments", v: a.avg_reel_comments, text: num(a.avg_reel_comments) });
    if (a.avg_reel_shares != null) reels.push({ label: "Average shares", v: a.avg_reel_shares, text: num(a.avg_reel_shares) });
    if (reels.length || a.reels_er != null) list.push({ label: "Reels", html: (a.reels_er != null ? erBlock(a.reels_er, "Reels engagement rate") : "") + rows(reels) });
    var st = [];
    if (a.story_reach != null) st.push({ label: "Estimated reach", v: a.story_reach, text: num(a.story_reach) });
    if (a.story_impressions != null) st.push({ label: "Estimated impressions", v: a.story_impressions, text: num(a.story_impressions) });
    if (st.length) list.push({ label: "Stories", html: rows(st) });
    tabs("pp-perf-tabs", "pp-perf", list, function (t) { return '<div class="pp-perf">' + t.html + "</div>"; });
    // Collaborations: how sponsored posts do against normal ones.
    var co = [];
    if (a.paid_post_performance != null) co.push(["Paid engagement", pct(a.paid_post_performance, 1), "Engagement on sponsored posts compared with normal posts."]);
    if (a.paid_views_pct != null) co.push(["Paid views", pct(a.paid_views_pct, 1), "Views on sponsored posts compared with normal posts."]);
    if (a.posts_count != null) co.push(["Posts on the account", num(a.posts_count), ""]);
    if (co.length) $("pp-perf").insertAdjacentHTML("beforeend", '<div class="pp-collab"><h3 class="pp-h3">Collaborations</h3><div class="pp-tiles">'
      + co.map(function (x) { return "<div><span>" + x[0] + "</span><b>" + x[1] + "</b>" + (x[2] ? "<small>" + x[2] + "</small>" : "") + "</div>"; }).join("") + "</div></div>");
  }

  /* brands as logos, then the sponsored posts, then hashtags and mentions */
  function logo(b) {
    var l = (b.logo || "").trim(), src = "";
    if (/^https:\/\//.test(l)) src = l;
    else if (/^[a-z0-9.-]+\.[a-z]{2,}$/i.test(l)) src = "https://www.google.com/s2/favicons?sz=128&domain=" + encodeURIComponent(l);
    var mono = esc(String(b.name || "?").replace(/[^A-Za-z0-9؀-ۿ ]/g, "").split(/\s+/).map(function (w) { return w[0]; }).join("").slice(0, 2).toUpperCase());
    return '<span class="pp-logo">' + (src ? '<img src="' + esc(src) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.textContent=\'' + mono + '\'">' : mono) + "</span>";
  }
  function renderNetwork(a) {
    var out = "", brands = a.brands || [];
    if (brands.length) out += '<div class="pp-brands">' + brands.slice(0, 12).map(function (b) {
      return '<div class="pp-brand">' + logo(b) + "<b>" + esc(b.name) + "</b>" + (b.count ? "<small>" + b.count + (b.count === 1 ? " post" : " posts") + "</small>" : "") + "</div>";
    }).join("") + (brands.length > 12 ? '<div class="pp-brand"><span class="pp-logo pp-logo--more">+' + (brands.length - 12) + "</span><b>more</b></div>" : "") + "</div>";
    if (a.sponsored_posts && a.sponsored_posts.length) out += '<h3 class="pp-h3">Collaborations</h3>' + postGrid(a.sponsored_posts, true);
    var tags = (a.hashtags || []).filter(function (h) { return String(h.tag).charAt(0) !== "@"; });
    var ments = (a.hashtags || []).filter(function (h) { return String(h.tag).charAt(0) === "@"; });
    function list(title, items) {
      return '<div class="pp-list"><h3 class="pp-h3">' + title + "</h3>" + items.slice(0, 8).map(function (h) {
        return "<div><span>" + esc(h.tag) + "</span><b>" + (h.count == null ? "" : (h.count <= 100 && String(h.count).indexOf(".") >= 0 ? pct(h.count, 1) : h.count + "×")) + "</b></div>"; }).join("") + "</div>";
    }
    if (tags.length || ments.length) out += '<div class="pp-two">' + (tags.length ? list("Popular hashtags", tags) : "") + (ments.length ? list("Popular mentions", ments) : "") + "</div>";
    $("pp-net-sec").hidden = !out;
    $("pp-net").innerHTML = out;
  }

  function brandOf(name) {
    var m = ((D.analysis || {}).brands || []).filter(function (b) { return String(b.name).toLowerCase() === String(name).toLowerCase(); })[0];
    return m || { name: name };
  }
  function postGrid(list, sponsored) {
    return '<div class="pp-posts">' + list.slice(0, 8).map(function (p) {
      return '<a class="pp-post" href="' + esc(p.url) + '" target="_blank" rel="noopener"><span class="pp-post__media">' + ICON_LINK
        + (p.thumb ? '<img src="' + esc(p.thumb) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">' : "")
        + (sponsored && p.brand ? '<span class="pp-post__brand">' + logo(brandOf(p.brand)) + esc(p.brand) + "</span>" : "")
        + '<span class="pp-post__nums">' + (p.likes != null ? "<span>" + I_LIKE + num(p.likes) + "</span>" : "") + (p.comments != null ? "<span>" + I_COMMENT + num(p.comments) + "</span>" : "")
        + (p.views != null ? "<span>" + I_PLAY + num(p.views) + "</span>" : "") + "</span></span>"
        + (p.date ? '<span class="pp-post__date">' + esc(day(p.date)) + "</span>" : "") + "</a>";
    }).join("") + "</div>";
  }
  function renderPosts(a) {
    var has = a.top_posts && a.top_posts.length;
    $("pp-posts-sec").hidden = !has;
    $("pp-posts").innerHTML = has ? postGrid(a.top_posts, false) : "";
  }

  /* audience quality as a small dashboard: the three credibility numbers,
     who the followers are (real / mass / suspicious), reachability, growth */
  function renderReal(a) {
    var cred = a.real_people_pct != null ? +a.real_people_pct : (a.credibility_pct != null ? +a.credibility_pct
      : (a.fake_followers_pct != null ? 100 - a.fake_followers_pct : null));
    var gC = cred == null ? null : cred >= 80 ? "good" : cred >= 65 ? "moderate" : "low";
    var gF = a.fake_followers_pct == null ? null : a.fake_followers_pct <= 15 ? "good" : a.fake_followers_pct <= 30 ? "moderate" : "low";
    var gL = a.fake_likers_pct == null ? null : a.fake_likers_pct <= 15 ? "good" : a.fake_likers_pct <= 30 ? "moderate" : "low";
    var tiles = [];
    if (cred != null) tiles.push(["Real people", pct(cred, 0), gC, "Followers that look like real, active people. Strong from 80%."]);
    if (a.fake_followers_pct != null) tiles.push(["Fake followers", pct(a.fake_followers_pct, 0), gF, "Bots and inactive accounts. Under 15% is healthy.", FAKE]);
    if (a.fake_likers_pct != null) tiles.push(["Fake likers", pct(a.fake_likers_pct, 0), gL, "Likes from bots or inactive accounts. Under 15% is healthy.", FAKE]);
    var out = tiles.length ? '<div class="pp-tiles pp-tiles--big">' + tiles.map(function (t) {
      return '<div class="pp-tile pp-tile--' + t[2] + '"><span>' + t[0] + "</span><b>" + t[1] + "</b>" + sig(t[2], "", t[4]) + "<small>" + t[3] + "</small></div>"; }).join("") + "</div>" : "";
    // breakdown of the followers
    var parts = [["Real people", a.real_people_pct, "#14884a", "Real, active accounts"],
      ["Real mass followers", a.mass_followers_pct, "#b9d400", "Real, but follow 1,500+ accounts — see few posts"],
      ["Suspicious mass", a.suspicious_mass_pct, "#e2780f", "Follow huge numbers of accounts; likely not real"],
      ["Suspicious accounts", a.suspicious_pct, "#ee1515", "Bots and fake accounts"]].filter(function (p) { return p[1] != null; });
    if (parts.length >= 2) {
      var tot = parts.reduce(function (s, p) { return s + (+p[1]); }, 0) || 1;
      out += '<div class="pp-card"><h3 class="pp-h3">Who the followers are</h3><div class="pp-stack" role="img" aria-label="Follower breakdown">'
        + parts.map(function (p) { return '<i style="width:' + (p[1] / tot * 100).toFixed(1) + "%;background:" + p[2] + '"></i>'; }).join("") + "</div>"
        + '<div class="pp-legend">' + parts.map(function (p) { return '<div><span class="pp-sw" style="background:' + p[2] + '"></span><p><b>' + pct(+p[1], 0) + "</b> " + p[0] + "<small>" + p[3] + "</small></p></div>"; }).join("") + "</div></div>";
    }
    var au = a.audience || {}, side = [];
    if (au.reachability && au.reachability.length) side.push('<div class="pp-card"><h3 class="pp-h3">Can they be reached?</h3>'
      + rows(au.reachability.map(function (r) { return { label: "Follow " + esc(r.name), v: r.pct, text: pct(r.pct, 0) }; }))
      + '<p class="pp-note">People who follow fewer accounts see more of each post. Most should follow under 1,000.</p></div>');
    var gr = (a.growth || []).filter(function (x) { return x.followers; });
    if (gr.length >= 2) side.push('<div class="pp-card"><h3 class="pp-h3">Follower growth</h3>' + growth(gr) + "</div>");
    if (side.length) out += '<div class="pp-two">' + side.join("") + "</div>";
    $("pp-real-sec").hidden = !out;
    $("pp-real").innerHTML = out;
  }
  function month(m) { var d = new Date(m + "-01T00:00:00Z"); return isNaN(d) ? m : d.toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" }); }
  function growth(gr) {
    var vals = gr.map(function (x) { return x.followers; }), first = vals[0], last = vals[vals.length - 1];
    var change = (last - first) / first * 100;
    var W = 520, H = 190, L = 8, Rr = 8, T = 14, B = 26, pw = W - L - Rr, ph = H - T - B;
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), pad = (hi - lo) * 0.2 || hi * 0.05, y0 = Math.max(0, lo - pad), y1 = hi + pad;
    function px(i) { return L + pw * i / (gr.length - 1); }
    function py(v) { return T + ph - (v - y0) / (y1 - y0) * ph; }
    var line = gr.map(function (d, i) { return px(i).toFixed(1) + "," + py(d.followers).toFixed(1); }).join(" ");
    var s = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Followers from ' + num(first) + " to " + num(last) + '">'
      + '<polygon points="' + L + "," + (T + ph) + " " + line + " " + (W - Rr) + "," + (T + ph) + '" fill="#e7f7ed"/>'
      + '<polyline fill="none" stroke="#14884a" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" points="' + line + '"/>';
    gr.forEach(function (d, i) { s += '<circle cx="' + px(i).toFixed(1) + '" cy="' + py(d.followers).toFixed(1) + '" r="4" fill="#fff" stroke="#14884a" stroke-width="2"/>'
      + '<text x="' + px(i).toFixed(1) + '" y="' + (H - 6) + '" text-anchor="' + (i === 0 ? "start" : i === gr.length - 1 ? "end" : "middle") + '" font-size="13" fill="#5a5a5a">' + esc(month(d.month)) + "</text>"; });
    s += "</svg>";
    return '<div class="pp-growth"><div class="pp-tiles pp-tiles--sm"><div><span>Now</span><b>' + num(last) + "</b></div><div><span>" + gr.length + " months ago</span><b>" + num(first) + "</b></div>"
      + '<div><span>Change</span><b class="' + (change >= 0 ? "up" : "down") + '">' + (change >= 0 ? "+" : "") + change.toFixed(1) + "%</b></div></div>" + s + "</div>";
  }

  /* audience: followers and, when on file, likers */
  function renderAudience(a) {
    var list = [{ label: "Followers", au: a.audience || {} }];
    if (a.audience_likers && Object.keys(a.audience_likers).length) list.push({ label: "Likers", au: a.audience_likers });
    tabs("pp-aud-tabs", "pp-aud", list, function (t) { return audience(t.au); });
  }
  function bars(items, key, colour) {
    if (!items || !items.length) return "";
    var peak = Math.max.apply(null, items.map(function (r) { return r.pct || 0; })) || 1;
    return items.slice(0, 6).map(function (r) {
      return '<div class="pp-bar"><span>' + key(r) + '</span><i style="--w:' + ((r.pct || 0) / peak * 100).toFixed(1) + "%" + (colour ? ";--c:" + colour : "") + '"></i><b>' + pct(r.pct, 0) + "</b></div>";
    }).join("");
  }
  function audience(au) {
    var out = "", cs = au.countries || [];
    out += cs.length ? '<div class="pp-stamps">' + cs.slice(0, 5).map(function (c, i) {
      return '<div class="pp-stamp' + (i === 0 ? " pp-stamp--lead" : "") + '">' + flag(c.code) + "<b>" + pct(c.pct, 0) + "</b><span>" + esc(countryName(c.code)) + "</span></div>";
    }).join("") + "</div>" : "";
    var panels = [];
    if (au.gender) {
      var f = +au.gender.female || 0, m = +au.gender.male || 0, t = f + m || 1;
      panels.push('<div class="pp-card"><h3 class="pp-h3">Gender</h3><div class="pp-split" role="img" aria-label="' + Math.round(f / t * 100) + '% women">'
        + '<i style="width:' + (f / t * 100) + '%;background:#ff691e">' + Math.round(f / t * 100) + "%</i>"
        + '<i style="width:' + (m / t * 100) + '%;background:#121212">' + Math.round(m / t * 100) + "%</i></div>"
        + '<p class="pp-note"><b style="color:#ff691e">Women</b> · <b>Men</b></p></div>');
    }
    if (au.ages && au.ages.length) {
      var ages = au.ages.slice().sort(function (x, y) { return String(x.name).localeCompare(String(y.name), "en", { numeric: true }); });
      panels.push('<div class="pp-card"><h3 class="pp-h3">Age</h3>' + bars(ages, function (r) { return esc(r.name); }, "#ff691e") + "</div>");
    }
    if (au.cities && au.cities.length) panels.push('<div class="pp-card"><h3 class="pp-h3">Top cities</h3>' + bars(au.cities, function (r) { return esc(r.name); }) + "</div>");
    if (au.languages && au.languages.length) panels.push('<div class="pp-card"><h3 class="pp-h3">Languages</h3>' + bars(au.languages, function (r) { return esc(r.name); }, "#8a7a68") + "</div>");
    if (au.interests && au.interests.length) panels.push('<div class="pp-card"><h3 class="pp-h3">Interests</h3><div class="pp-chips">'
      + au.interests.slice(0, 10).map(function (r) { return '<span class="pp-chip">' + esc(r.name) + " <b>" + pct(r.pct, 0) + "</b></span>"; }).join("") + "</div></div>");
    if (au.brand_affinity && au.brand_affinity.length) panels.push('<div class="pp-card"><h3 class="pp-h3">Brands they love</h3><div class="pp-chips">'
      + au.brand_affinity.slice(0, 10).map(function (r) { return '<span class="pp-chip">' + esc(r.name) + (r.pct != null ? " <b>" + pct(r.pct, 0) + "</b>" : "") + "</span>"; }).join("") + "</div></div>");
    return out + '<div class="pp-grid">' + panels.join("") + "</div>";
  }

  load();
})();
