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

  // Only what the Modash report carries, in the order it carries it: no
  // grades, benchmarks or derived numbers of our own.
  function ico(d) { return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + d + "</svg>"; }
  var I_LIKE = ico('<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>');
  var I_COMMENT = ico('<path d="M4 5h16v11H9l-5 4z"/>');
  var I_PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z" fill="currentColor"/></svg>';
  var I_DOWN = ico('<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>');
  function pct2(v) { return v == null ? "—" : (+v).toFixed(2) + "%"; }
  function delta(v) {
    if (v == null) return "";
    return '<em class="pp-delta pp-delta--' + (v < 0 ? "down" : "up") + '">' + (v < 0 ? "−" : "+") + Math.abs(v).toFixed(2) + "%</em>";
  }
  function arDir(t) { return /[؀-ۿ]/.test(t) && !/[A-Za-z]{3}/.test(t) ? ' dir="rtl"' : ""; }

  function render() {
    var c = D.creator, a = D.analysis;
    document.title = c.name + " — Creator analysis — HelloVoice";
    window.scrollTo(0, 0);
    renderId(c, a);
    $("pp-sealed").hidden = !!a;
    $("pp-pages").hidden = !a;
    if (!a) return renderSealed(c);
    renderPosts(a);
    renderReal(a);
    renderPerf(a);
    renderNetwork(a);
    renderAudience(a);
    renderTags(a);
    $("pp-source").textContent = "Source: " + (a.source || "Modash") + (a.updated ? " · data from " + day(a.updated) : "");
  }

  /* identity: as the top of the Modash report — who, the three numbers, bio */
  function renderId(c, a) {
    var handles = (c.profiles || []).filter(function (p) { return p.url; }).map(function (p) {
      var mine = a && a.followers && (!a.platform || a.platform === p.platform);
      var n = mine ? a.followers : p.followers;
      return '<a class="pp-handle' + (mine ? " is-analysed" : "") + '" href="' + esc(p.url) + '" target="_blank" rel="noopener">' + icon(p.platform)
        + "<span>" + esc(p.platform) + "</span>" + (n ? "<b>" + num(n) + "</b>" : "") + "</a>";
    }).join("");
    var line = [a && a.handle ? "@" + String(a.handle).replace(/^@/, "") : "", a && a.account_type ? a.account_type + " account" : "",
      (a && a.location) || c.city || ""].filter(Boolean);
    var key = a ? [
      ["Followers", num(a.followers || c.followers), delta(a.followers_change_pct)],
      ["Avg. likes", a.likes_hidden ? "Hidden" : num(a.avg_likes), delta(a.avg_likes_change_pct)],
      ["Engagement rate", pct2(a.er), ""]
    ] : [["Followers", num(c.followers), ""], ["Tier", c.tier || BANDS[c.band] || "—", ""], ["Based in", c.city || "—", ""]];
    // The photo at its own size: never stretched past its pixels, never cropped.
    var src = (a && a.photo_url) || c.photo_url;
    var bio = a && a.bio ? '<div class="pp-bio">' + String(a.bio).split("\n").map(function (l) { return "<p" + arDir(l) + ">" + esc(l) + "</p>"; }).join("") + "</div>" : "";
    $("pp-id").innerHTML = '<div class="pp-photo">' + (src ? '<img src="' + esc(src) + '" alt="' + esc(c.name) + '">'
      : '<span class="pp-photo__none">' + esc(c.code.split("-").pop()) + "</span>") + "</div>"
      + '<div class="pp-fields">'
      + (a ? '<p class="pp-badge pp-badge--ok"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5l2.4 1.8 3 .1.9 2.9 2.4 1.8-.9 2.9.9 2.9-2.4 1.8-.9 2.9-3 .1L12 21.5l-2.4-1.8-3-.1-.9-2.9-2.4-1.8.9-2.9-.9-2.9 2.4-1.8.9-2.9 3-.1z" fill="currentColor"/><path d="M8.2 12.3l2.6 2.6 5-5.2" fill="none" stroke="#e8ff76" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
           + "<span><b>Verified analysis</b>" + (a.updated ? "<small>Data from " + esc(day(a.updated)) + "</small>" : "") + "</span></p>"
         : '<p class="pp-badge pp-badge--locked"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/></svg><span><b>Not analysed yet</b><small>Basics only</small></span></p>')
      + '<h1 class="pp-name">' + esc(c.name) + "</h1>"
      + '<p class="pp-line"><span class="pp-code">' + esc(c.code) + "</span>" + line.map(esc).join(" · ") + (c.tier || c.band ? " · " + esc(c.tier || BANDS[c.band]) + " tier" : "") + "</p>"
      + '<div class="pp-handles">' + handles + "</div>"
      + '<dl class="pp-key">' + key.map(function (k) { return "<div><dt>" + k[0] + "</dt><dd>" + esc(k[1]) + (k[2] ? " " + k[2] : "") + "</dd></div>"; }).join("") + "</dl>"
      + bio
      + (a ? '<div class="pp-actions"><button type="button" class="pp-btn pp-btn--ink" id="pp-print">' + I_DOWN + "Download PDF</button></div>" : "")
      + "</div>";
    var pb = $("pp-print"); if (pb) pb.addEventListener("click", function () { downloadPdf(pb); });
  }
  function day(iso) { var d = new Date(String(iso).slice(0, 10) + "T00:00:00Z"); return isNaN(d) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }); }

  function renderSealed(c) {
    var asked = D.requested;
    $("pp-sealed").innerHTML = '<div class="pp-sealed__icon" aria-hidden="true">' + ICON_ANALYSIS + "</div>"
      + "<div><h2>Full analysis not on file yet</h2><p>The full analysis shows where " + esc(c.name) + "'s audience lives, their age and gender, how much of it is real, how it has grown, how posts perform and the brands they have worked with.</p>"
      + '<ul class="pp-sealed__list"><li>Audience countries, cities, age &amp; gender</li><li>Real vs fake followers</li><li>Engagement and content performance</li><li>Brands &amp; interests</li></ul>'
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

  /* tabs shared by Content and Audience */
  function tabs(box, pane, list, draw) {
    var on = 0;
    function paint() {
      $(box).innerHTML = list.length > 1 ? list.map(function (t, i) { return '<button type="button" role="tab" aria-selected="' + (i === on) + '" data-i="' + i + '">' + esc(t.label) + "</button>"; }).join("") : "";
      $(pane).innerHTML = list.map(function (t, i) { return '<div class="pp-pane" data-tab="' + esc(t.label) + '"' + (i === on ? "" : " hidden") + ">" + draw(t) + "</div>"; }).join("");
      if (pane === "pp-perf") collab();
    }
    paint();
    $(box).onclick = function (e) { var b = e.target.closest("button[data-i]"); if (!b) return; on = +b.getAttribute("data-i"); paint(); };
  }

  /* one metric row: label, a bar against the largest in its group, the value */
  function rows(items, colour) {
    var peak = Math.max.apply(null, items.map(function (r) { return r.v || 0; }).concat([1]));
    return '<div class="pp-rows">' + items.map(function (r) {
      return '<div class="pp-row"><span>' + r.label + '</span><i class="pp-row__bar"><b style="width:' + Math.max(2, (r.v || 0) / peak * 100).toFixed(1) + "%" + (colour ? ";background:" + colour : "") + '"></b></i><strong>' + r.text + "</strong></div>";
    }).join("") + "</div>";
  }

  /* popular posts: the post's own cover; a tap plays it from Instagram */
  function shortcode(u) { var m = /instagram\.com\/(?:[^\/]+\/)?(?:p|reel|reels|tv)\/([A-Za-z0-9_-]+)/.exec(u || ""); return m ? m[1] : null; }
  function postGrid(list, sponsored) {
    return '<div class="pp-posts">' + list.map(function (p, i) {
      return '<a class="pp-post" href="' + esc(p.url) + '" target="_blank" rel="noopener" aria-label="Play post ' + (i + 1) + '" data-post="' + i + '"' + (sponsored ? ' data-sp="1"' : "") + ">"
        + '<span class="pp-post__media"' + (p.thumb ? ' style="background-image:url(\'' + esc(p.thumb) + '\')"' : "") + ">"
        + (p.thumb ? "" : '<span class="pp-post__none">Instagram post</span>')
        + '<span class="pp-post__play">' + I_PLAY + "</span>"
        + (sponsored && p.brand ? '<span class="pp-post__brand">' + esc(p.brand) + "</span>" : "")
        + '<span class="pp-post__nums">' + (p.likes != null ? "<span>" + I_LIKE + num(p.likes) + "</span>" : "") + (p.comments != null ? "<span>" + I_COMMENT + num(p.comments) + "</span>" : "")
        + (p.views != null ? "<span>" + ico('<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>') + num(p.views) + "</span>" : "") + "</span></span>"
        + (p.date ? '<span class="pp-post__date">' + esc(day(p.date)) + "</span>" : "") + "</a>";
    }).join("") + "</div>";
  }
  function renderPosts(a) {
    var top = a.top_posts || [], sp = a.sponsored_posts || [];
    $("pp-posts-sec").hidden = !(top.length || sp.length);
    $("pp-posts").innerHTML = (top.length ? postGrid(top, false) : "") + (sp.length ? '<h3 class="pp-h3">Sponsored posts</h3>' + postGrid(sp, true) : "");
    $("pp-posts").onclick = function (e) {
      var el = e.target.closest("[data-post]"); if (!el) return;
      var list = el.getAttribute("data-sp") ? sp : top, p = list[+el.getAttribute("data-post")], sc = p && shortcode(p.url);
      if (!sc) return;            // not an Instagram post: let the link open it
      e.preventDefault(); openPost(p.url, sc);
    };
  }
  function openPost(url, sc) {
    $("pp-modal-frame").innerHTML = '<iframe src="https://www.instagram.com/p/' + encodeURIComponent(sc) + '/embed/captioned/" title="Instagram post" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen loading="eager"></iframe>';
    $("pp-modal-open").href = url;
    $("pp-modal").hidden = false; document.body.classList.add("pp-modal-on");
    $("pp-modal-close").focus();
  }
  function closePost() { $("pp-modal").hidden = true; $("pp-modal-frame").innerHTML = ""; document.body.classList.remove("pp-modal-on"); }
  $("pp-modal-close").addEventListener("click", closePost);
  $("pp-modal").addEventListener("click", function (e) { if (e.target === this) closePost(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !$("pp-modal").hidden) closePost(); });

  /* followers: followers and fake followers, reachability, growth, distribution */
  function renderReal(a) {
    var out = "", tiles = [];
    if (a.followers != null) tiles.push(["Followers", num(a.followers)]);
    if (a.fake_followers_pct != null) tiles.push(["Fake followers", pct2(a.fake_followers_pct)]);
    if (a.fake_likers_pct != null) tiles.push(["Fake likers", pct2(a.fake_likers_pct)]);
    if (tiles.length) out += '<div class="pp-tiles pp-tiles--big">' + tiles.map(function (t) { return '<div class="pp-tile"><span>' + t[0] + "</span><b>" + t[1] + "</b></div>"; }).join("") + "</div>";
    var au = a.audience || {}, cards = [];
    if (au.reachability && au.reachability.length) {
      var RL = { "<500": "<500 accounts", "500-1000": "500-1k accounts", "1000-1500": "1k-1.5k accounts", ">1500": ">1.5k accounts" };
      cards.push('<div class="pp-card"><h3 class="pp-h3">Audience reachability</h3>'
        + rows(au.reachability.map(function (r) { return { label: esc(RL[r.name] || r.name), v: r.pct, text: pct2(r.pct) }; }), "#5b4bd6") + "</div>");
    }
    if (a.fake_followers_dist) cards.push('<div class="pp-card"><h3 class="pp-h3">Fake followers distribution</h3>' + dist(a.fake_followers_dist, "#ff691e") + "</div>");
    var gr = (a.growth || []).filter(function (x) { return x.followers; });
    if (gr.length >= 2) cards.push('<div class="pp-card"><h3 class="pp-h3">Followers growth</h3>' + chart(gr, "followers", "#14884a", "#e7f7ed") + "</div>");
    var gl = (a.growth || []).filter(function (x) { return x.avg_likes != null; });
    if (gl.length >= 2) cards.push('<div class="pp-card"><h3 class="pp-h3">Likes growth</h3>' + chart(gl, "avg_likes", "#ff691e", "#fff1e8") + "</div>");
    if (cards.length) out += '<div class="pp-two">' + cards.join("") + "</div>";
    $("pp-real-sec").hidden = !out;
    $("pp-real").innerHTML = out;
  }
  function month(m) { var d = new Date(m + "-01T00:00:00Z"); return isNaN(d) ? m : d.toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" }); }
  function chart(gr, key, colour, fill) {
    var vals = gr.map(function (x) { return x[key]; });
    var W = 560, H = 220, L = 12, Rr = 12, T = 30, B = 44, pw = W - L - Rr, ph = H - T - B;
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), pad = (hi - lo) * 0.25 || hi * 0.05 || 1, y0 = Math.max(0, lo - pad), y1 = hi + pad;
    function px(i) { return L + pw * i / (gr.length - 1); }
    function py(v) { return T + ph - (v - y0) / (y1 - y0) * ph; }
    var line = gr.map(function (d, i) { return px(i).toFixed(1) + "," + py(d[key]).toFixed(1); }).join(" ");
    var s = '<svg class="pp-chart" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc(gr.map(function (d) { return month(d.month) + " " + num(d[key]); }).join(", ")) + '">'
      + '<polygon points="' + px(0).toFixed(1) + "," + (T + ph) + " " + line + " " + px(gr.length - 1).toFixed(1) + "," + (T + ph) + '" fill="' + fill + '"/>'
      + '<polyline fill="none" stroke="' + colour + '" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" points="' + line + '"/>';
    function fmt(v) { return v >= 1e4 ? (v / 1e3).toFixed(1).replace(/\.0$/, "") + "K" : num(v); }
    gr.forEach(function (d, i) {
      var x = px(i).toFixed(1), y = py(d[key]), anchor = i === 0 ? "start" : i === gr.length - 1 ? "end" : "middle";
      // a dip carries its label underneath, so it never sits on the line
      var prev = i > 0 ? gr[i - 1][key] : null, next = i < gr.length - 1 ? gr[i + 1][key] : null;
      var dip = (prev == null || d[key] < prev) && (next == null || d[key] < next) && (prev != null || next != null) && i > 0 && i < gr.length - 1;
      s += '<circle cx="' + x + '" cy="' + y.toFixed(1) + '" r="4" fill="#fff" stroke="' + colour + '" stroke-width="2.5"/>'
        + '<text x="' + x + '" y="' + (dip ? y + 20 : y - 10).toFixed(1) + '" text-anchor="' + anchor + '" font-size="12" font-weight="700" fill="#121212">' + fmt(d[key]) + "</text>"
        + '<text x="' + x + '" y="' + (H - 6) + '" text-anchor="' + anchor + '" font-size="12" fill="#5a5a5a">' + esc(month(d.month)) + "</text>";
    });
    return s + "</svg>";
  }
  function dist(d, colour) {
    var b = d.buckets || [];
    return '<div class="pp-dist" role="img" aria-label="Distribution among similar creators">' + b.map(function (x, i) {
      var who = i === d.creator ? " is-creator" : (i === d.median ? " is-median" : "");
      return '<div class="pp-dist__col' + who + '"><i style="height:' + Math.max(3, x.h) + "%" + (who === " is-creator" && colour ? ";background:" + colour : "") + '"></i><span>' + esc(x.label) + "</span></div>";
    }).join("") + '</div><p class="pp-dist__key"><span class="k-creator"' + (colour ? ' style="background:' + colour + '"' : "") + '></span>Creator<span class="k-median"></span>Median<span class="k-other"></span>Other creators</p>';
  }

  /* content: all content / reels / stories, collaborations, ER distribution */
  function renderPerf(a) {
    var list = [];
    function erBlock(v, note, label) {
      return '<div class="pp-er"><span class="pp-er__label">' + label + "</span><b>" + pct2(v) + "</b>" + (note ? "<p>" + esc(note) + "</p>" : "") + "</div>";
    }
    var all = [];
    if (a.est_impressions != null) all.push({ label: "Estimated impressions", v: a.est_impressions, text: num(a.est_impressions) });
    if (a.est_reach != null) all.push({ label: "Estimated reach", v: a.est_reach, text: num(a.est_reach) });
    if (a.avg_views != null) all.push({ label: "Average views", v: a.avg_views, text: num(a.avg_views) });
    if (a.avg_likes != null) all.push({ label: "Average likes", v: a.avg_likes, text: num(a.avg_likes) });
    else if (a.likes_hidden) all.push({ label: "Average likes", v: 0, text: "Hidden" });
    if (a.avg_comments != null) all.push({ label: "Average comments", v: a.avg_comments, text: num(a.avg_comments) });
    list.push({ label: "All content", html: erBlock(a.er, a.er_note, "Engagement rate") + rows(all) });
    var reels = [];
    if (a.avg_reel_plays != null) reels.push({ label: "Average reel plays", v: a.avg_reel_plays, text: num(a.avg_reel_plays) });
    if (a.avg_reel_likes != null) reels.push({ label: "Average likes", v: a.avg_reel_likes, text: num(a.avg_reel_likes) });
    if (a.avg_reel_comments != null) reels.push({ label: "Average comments", v: a.avg_reel_comments, text: num(a.avg_reel_comments) });
    if (a.avg_reel_shares != null) reels.push({ label: "Average shares", v: a.avg_reel_shares, text: num(a.avg_reel_shares) });
    if (reels.length || a.reels_er != null) list.push({ label: "Reels", html: (a.reels_er != null ? erBlock(a.reels_er, a.reels_er_note, "Engagement rate") : "") + rows(reels) });
    var st = [];
    if (a.story_reach != null) st.push({ label: "Estimated reach", v: a.story_reach, text: num(a.story_reach) });
    if (a.story_impressions != null) st.push({ label: "Estimated impressions", v: a.story_impressions, text: num(a.story_impressions) });
    if (st.length) list.push({ label: "Stories", html: rows(st) });
    tabs("pp-perf-tabs", "pp-perf", list, function (t) { return '<div class="pp-perf">' + t.html + "</div>"; });
  }
  function collab() {
    var a = D.analysis, co = [], out = "";
    if (a.paid_post_performance != null) co.push(["Paid engagement", pct2(a.paid_post_performance)]);
    if (a.paid_views_pct != null) co.push(["Paid views", pct2(a.paid_views_pct)]);
    if (co.length) out += '<div class="pp-collab"><h3 class="pp-h3">Collaborations</h3><div class="pp-tiles">'
      + co.map(function (x) { return "<div><span>" + x[0] + "</span><b>" + x[1] + "</b></div>"; }).join("") + "</div></div>";
    if (a.er_dist) out += '<div class="pp-collab pp-card"><h3 class="pp-h3">Engagement rate distribution</h3>' + dist(a.er_dist, "#14884a") + "</div>";
    if (out) $("pp-perf").insertAdjacentHTML("beforeend", out);
  }

  /* creator brand affinity as logos, creator interests */
  function renderNetwork(a) {
    var out = "", brands = a.brands || [], ci = a.creator_interests || [];
    if (brands.length) out += '<div class="pp-card"><h3 class="pp-h3">Creator brand affinity</h3><div class="pp-brands">' + brands.map(function (b) {
      return '<div class="pp-brand">' + (b.logo ? '<span class="pp-logo" role="img" aria-label="' + esc(b.name) + '" style="background-image:url(\'' + esc(b.logo) + '\')"></span>' : "")
        + "<b>" + esc(b.name) + "</b>" + (b.count ? "<small>" + b.count + (b.count === 1 ? " post" : " posts") + "</small>" : "") + "</div>";
    }).join("") + "</div></div>";
    if (ci.length) out += '<div class="pp-card"><h3 class="pp-h3">Creator interests</h3><div class="pp-chips">' + ci.map(function (x) { return '<span class="pp-chip">' + esc(x) + "</span>"; }).join("") + "</div></div>";
    if (out) out = '<div class="pp-two">' + out + "</div>";
    $("pp-net-sec").hidden = !out;
    $("pp-net").innerHTML = out;
  }

  /* hashtags and mentions, as shares of posts */
  function renderTags(a) {
    var tags = (a.hashtags || []).filter(function (h) { return String(h.tag).charAt(0) !== "@"; });
    var ments = (a.hashtags || []).filter(function (h) { return String(h.tag).charAt(0) === "@"; });
    function list(title, items) {
      return '<div class="pp-card pp-list"><h3 class="pp-h3">' + title + "</h3>" + items.map(function (h) {
        return "<div><span" + arDir(h.tag) + ">" + esc(h.tag) + "</span><b>" + (h.count == null ? "" : pct2(h.count)) + "</b></div>"; }).join("") + "</div>";
    }
    var out = (tags.length || ments.length) ? '<div class="pp-two">' + (tags.length ? list("Popular hashtags", tags) : "") + (ments.length ? list("Popular mentions", ments) : "") + "</div>" : "";
    $("pp-tags-sec").hidden = !out;
    $("pp-tags").innerHTML = out;
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
    return items.map(function (r) {
      return '<div class="pp-bar"><span>' + key(r) + '</span><i style="--w:' + ((r.pct || 0) / peak * 100).toFixed(1) + "%" + (colour ? ";--c:" + colour : "") + '"></i><b>' + pct2(r.pct) + "</b></div>";
    }).join("");
  }
  var AGE_ORDER = function (x, y) { return String(x.name).localeCompare(String(y.name), "en", { numeric: true }); };
  function audience(au) {
    var out = "", cs = au.countries || [];
    out += cs.length ? '<div class="pp-stamps">' + cs.slice(0, 5).map(function (c, i) {
      return '<div class="pp-stamp' + (i === 0 ? " pp-stamp--lead" : "") + '">' + flag(c.code) + "<b>" + pct(c.pct, 0) + "</b><span>" + esc(countryName(c.code)) + "</span></div>";
    }).join("") + "</div>" : "";
    var panels = [];
    if (au.gender) {
      var f = +au.gender.female || 0, m = +au.gender.male || 0, t = f + m || 1;
      // Labels sit in the legend, not inside the bar, so a thin slice never
      // has to carry a number it is too narrow for.
      panels.push('<div class="pp-card"><h3 class="pp-h3">Gender</h3><div class="pp-split" role="img" aria-label="Female ' + pct2(f) + ", male " + pct2(m) + '">'
        + '<i style="width:' + (f / t * 100) + '%;background:#ff691e"></i><i style="width:' + (m / t * 100) + '%;background:#121212"></i></div>'
        + '<div class="pp-split__key"><span><i style="background:#ff691e"></i>Female <b>' + pct2(f) + '</b></span><span><i style="background:#121212"></i>Male <b>' + pct2(m) + "</b></span></div></div>");
    }
    if (au.ages && au.ages.length) panels.push('<div class="pp-card"><h3 class="pp-h3">Age</h3>' + bars(au.ages.slice().sort(AGE_ORDER), function (r) { return esc(r.name); }, "#ff691e") + "</div>");
    if ((au.ages_female && au.ages_female.length) || (au.ages_male && au.ages_male.length)) {
      var names = {}; (au.ages_female || []).concat(au.ages_male || []).forEach(function (r) { names[r.name] = 1; });
      var fm = {}, mm = {}; (au.ages_female || []).forEach(function (r) { fm[r.name] = r.pct; }); (au.ages_male || []).forEach(function (r) { mm[r.name] = r.pct; });
      var peak = Math.max.apply(null, Object.keys(names).map(function (n) { return Math.max(fm[n] || 0, mm[n] || 0); })) || 1;
      panels.push('<div class="pp-card"><h3 class="pp-h3">Age by gender</h3>' + Object.keys(names).sort(function (x, y) { return AGE_ORDER({ name: x }, { name: y }); }).map(function (n) {
        return '<div class="pp-pair"><span>' + esc(n) + "</span><div>"
          + '<p><i style="--w:' + ((fm[n] || 0) / peak * 100).toFixed(1) + '%;--c:#ff691e"></i><b>' + pct2(fm[n] || 0) + "</b></p>"
          + '<p><i style="--w:' + ((mm[n] || 0) / peak * 100).toFixed(1) + '%;--c:#121212"></i><b>' + pct2(mm[n] || 0) + "</b></p></div></div>";
      }).join("") + '<div class="pp-split__key"><span><i style="background:#ff691e"></i>Female</span><span><i style="background:#121212"></i>Male</span></div></div>');
    }
    if (cs.length) panels.push('<div class="pp-card"><h3 class="pp-h3">Location by country</h3>' + bars(cs, function (r) { return flag(r.code) + " " + esc(countryName(r.code)); }) + "</div>");
    if (au.cities && au.cities.length) panels.push('<div class="pp-card"><h3 class="pp-h3">Location by city</h3>' + bars(au.cities, function (r) { return esc(r.name); }) + "</div>");
    if (au.languages && au.languages.length) panels.push('<div class="pp-card"><h3 class="pp-h3">Languages</h3>' + bars(au.languages, function (r) { return esc(r.name); }, "#8a7a68") + "</div>");
    var wide = [];
    if (au.interests && au.interests.length) wide.push('<div class="pp-card pp-card--long"><h3 class="pp-h3">Audience interests</h3>' + bars(au.interests, function (r) { return esc(r.name); }, "#14884a") + "</div>");
    if (au.brand_affinity && au.brand_affinity.length) wide.push('<div class="pp-card pp-card--long"><h3 class="pp-h3">Audience brand affinity</h3>' + bars(au.brand_affinity, function (r) { return esc(r.name); }, "#5b4bd6") + "</div>");
    return out + '<div class="pp-grid">' + panels.join("") + "</div>" + (wide.length ? '<div class="pp-two">' + wide.join("") + "</div>" : "");
  }

  /* ------------------------------------------------------------ the PDF */
  // A real file, not the print dialog: each section is drawn on its own and
  // laid onto A4 pages, so a page never cuts through the middle of a chart.
  function script(src) {
    return new Promise(function (ok, bad) { var s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = bad; document.head.appendChild(s); });
  }
  var LIBS = null;
  function libs() {
    return LIBS || (LIBS = Promise.all([
      window.html2canvas ? 0 : script("https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"),
      window.jspdf ? 0 : script("https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js")
    ]));
  }
  function downloadPdf(btn) {
    var label = btn.innerHTML;
    btn.disabled = true; btn.innerHTML = I_DOWN + "Preparing PDF…";
    var root = document.documentElement;
    libs().then(function () {
      root.classList.add("pp-pdf");
      return document.fonts ? document.fonts.ready : 0;
    }).then(function () {
      var JsPDF = window.jspdf.jsPDF, doc = new JsPDF({ unit: "pt", format: "a4", compress: true });
      var PW = doc.internal.pageSize.getWidth(), PH = doc.internal.pageSize.getHeight(), M = 28, CW = PW - 2 * M;
      var blocks = [$("pp-id")].concat([].slice.call(document.querySelectorAll("#pp-pages > .pp-page:not([hidden]), #pp-source")));
      var y = M, first = true;
      return blocks.reduce(function (p, el) {
        return p.then(function () {
          return window.html2canvas(el, { scale: 2, useCORS: true, backgroundColor: "#ffffff", logging: false });
        }).then(function (cv) {
          var h = cv.height * CW / cv.width;
          if (!first && y + Math.min(h, PH - 2 * M) > PH - M) { doc.addPage(); y = M; }
          first = false;
          if (h <= PH - 2 * M) { doc.addImage(cv.toDataURL("image/jpeg", 0.92), "JPEG", M, y, CW, h); y += h + 16; return; }
          // taller than a page: slice it
          var sliceH = Math.floor((PH - 2 * M) * cv.width / CW), off = 0;
          while (off < cv.height) {
            var part = document.createElement("canvas"); part.width = cv.width; part.height = Math.min(sliceH, cv.height - off);
            part.getContext("2d").drawImage(cv, 0, off, cv.width, part.height, 0, 0, cv.width, part.height);
            if (off > 0) { doc.addPage(); y = M; }
            var ph = part.height * CW / cv.width;
            doc.addImage(part.toDataURL("image/jpeg", 0.92), "JPEG", M, y, CW, ph); y += ph + 16; off += sliceH;
          }
        });
      }, Promise.resolve()).then(function () {
        var c = D.creator;
        doc.save((c.name || c.code).replace(/[^\w؀-ۿ -]+/g, "").trim().replace(/\s+/g, "-") + "-" + c.code + "-analysis.pdf");
      });
    }).catch(function () {
      alert("The PDF could not be made. Please try again.");
    }).then(function () {
      root.classList.remove("pp-pdf"); btn.disabled = false; btn.innerHTML = label;
    });
  }

  load();
})();
