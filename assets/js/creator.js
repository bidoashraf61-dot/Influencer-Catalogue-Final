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
  var PLAT = "";           // the platform tab being read
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
  function wantPlat() { var m = /(?:^|[#&])p=([A-Za-z]+)/.exec(location.hash || ""); return m ? decodeURIComponent(m[1]) : ""; }
  // The tab to open on: the one the link names, else the first platform that
  // has an analysis, else the creator's main platform.
  function choosePlat() {
    var ps = D.platforms || [], w = wantPlat().toLowerCase();
    var hit = ps.filter(function (p) { return p.toLowerCase() === w; })[0];
    if (hit) return hit;
    var an = D.analyses || {};
    return ps.filter(function (p) { return an[p]; })[0] || ps[0] || "";
  }
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

  // Only what the profile report carries, in the order it carries it: no
  // grades, benchmarks or derived numbers of our own.
  function ico(d) { return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + d + "</svg>"; }
  var I_LIKE = ico('<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>');
  var I_COMMENT = ico('<path d="M4 5h16v11H9l-5 4z"/>');
  var I_PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z" fill="currentColor"/></svg>';
  var I_DOWN = ico('<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>');
  /* verdict tags: the number against HelloVoice's own benchmarks (Admin → Settings) */
  var BAND_NAME = { nano: "Nano", micro: "Micro", mid: "Mid-tier", macro: "Macro", mega: "Mega" };
  function bandOf(f) { return f < 1e4 ? "nano" : f < 5e4 ? "micro" : f < 5e5 ? "mid" : f < 1e6 ? "macro" : "mega"; }
  function bench(key, band) { var b = (D.benchmarks || {})[key]; return band ? (b || {})[band] : b; }
  function verdict(v, pair, lower) {
    if (v == null || !pair) return null;
    return lower ? (v <= pair[0] ? "good" : v <= pair[1] ? "moderate" : "low") : (v >= pair[0] ? "good" : v >= pair[1] ? "moderate" : "low");
  }
  var VWORD = { good: "Strong", moderate: "Fair", low: "Low" }, VWORD_LOW = { good: "Healthy", moderate: "Watch", low: "High" };
  function tagFor(g, why, lower) {
    return g ? ' <span class="pp-sig pp-sig--' + g + '" title="' + esc(why) + '">' + (lower ? VWORD_LOW : VWORD)[g] + "</span>" : "";
  }
  function erTag(v, f) {
    var band = bandOf(f || 0), pair = bench("er", band);
    return pair ? tagFor(verdict(v, pair), "Strong from " + pair[0] + "%, fair from " + pair[1] + "% for " + BAND_NAME[band] + " creators — HelloVoice benchmark") : "";
  }
  function fakeTag(v, key) {
    var pair = bench(key); if (!pair) return "";
    return tagFor(verdict(v, pair, true), "Healthy up to " + pair[0] + "%, watch up to " + pair[1] + "%, high above that — HelloVoice benchmark", true);
  }
  function pct2(v) { return v == null ? "—" : (+v).toFixed(2) + "%"; }
  function delta(v) {
    if (v == null) return "";
    return '<em class="pp-delta pp-delta--' + (v < 0 ? "down" : "up") + '">' + (v < 0 ? "−" : "+") + Math.abs(v).toFixed(2) + "%</em>";
  }
  function arDir(t) { return /[؀-ۿ]/.test(t) && !/[A-Za-z]{3}/.test(t) ? ' dir="rtl"' : ""; }

  /* an "i" beside every part, saying what it is and where the number comes from */
  var TIPS = {
    "h2|Popular posts": "The creator's best-performing recent posts, ranked by engagement. Tap one to play it from Instagram.",
    "h2|Followers": "How big the audience is and how much of it is real.",
    "h2|Content": "How the creator's posts perform on average, split by content type.",
    "h2|Creator brand affinity & interests": "What the creator posts about and which brands appear in their content.",
    "h2|Audience data": "Who the audience is. Followers: everyone who follows the account. Likers: only the people who like the posts — the more engaged part of the audience.",
    "h2|Popular hashtags & mentions": "The hashtags and accounts the creator uses most in recent posts.",
    "Followers": "Total followers on the account on the date of the report. The small % is the recent change.",
    "Avg. likes": "Average likes per post over the creator's recent posts. \u201cHidden\u201d means the creator hides like counts on Instagram.",
    "Engagement rate": "Average likes plus comments per post, divided by followers. The note compares it with creators of a similar size.",
    "Fake followers": "Share of followers flagged as bots, inactive or suspicious accounts. The rest are real people.",
    "Fake likers": "Share of the people liking posts that are flagged as bots or suspicious accounts.",
    "Audience reachability": "How many accounts the followers themselves follow. People who follow fewer than 1,000 accounts are more likely to see this creator's posts in their feed.",
    "<500 accounts": "Followers who follow fewer than 500 accounts. Their feed is uncrowded, so they are the most likely to see this creator's posts.",
    "500-1k accounts": "Followers who follow 500 to 1,000 accounts. Still a manageable feed — they are likely to see a good share of the posts.",
    "1k-1.5k accounts": "Followers who follow 1,000 to 1,500 accounts. A busy feed, so they see fewer of this creator's posts.",
    ">1.5k accounts": "Followers who follow more than 1,500 accounts. Their feed is so crowded that they rarely see any one creator's posts — these are called mass followers.",
    "Fake followers distribution": "Where this creator sits among creators of a similar size by share of fake followers. The coloured bar is this creator; the darker grey bar is the median.",
    "Followers growth": "Followers at the end of each month.",
    "Likes growth": "Average likes per post in each month.",
    "Estimated impressions": "An estimate of how many times a typical post is seen, based on followers and engagement — only the creator's own insights give exact figures.",
    "Estimated reach": "An estimate of how many different accounts see a typical post — only the creator's own insights give exact figures.",
    "Stories|Estimated reach": "An estimate of how many different accounts see a typical story — only the creator's own insights give exact figures.",
    "Stories|Estimated impressions": "An estimate of how many times a typical story is seen — only the creator's own insights give exact figures.",
    "Average views": "Average views per video post.",
    "Average likes": "Average likes per post of this type.",
    "Average comments": "Average comments per post of this type.",
    "Average reel plays": "Average number of times a reel is played.",
    "Average shares": "Average number of times a reel is shared.",
    "Collaborations": "How the creator's sponsored posts perform compared with their normal posts.",
    "Paid engagement": "Engagement on sponsored posts as a share of engagement on normal posts. 100% means sponsored posts do as well as normal ones; below 100%, they do less well.",
    "Paid views": "Views on sponsored posts as a share of views on normal posts. 100% means sponsored posts get as many views as normal ones.",
    "Engagement rate distribution": "Where this creator's engagement rate sits among creators of a similar size. The coloured bar is this creator; the darker grey bar is the median.",
    "Creator brand affinity": "Brands the creator mentions or tags in their own posts — not necessarily paid partnerships.",
    "Creator interests": "The topics the creator posts about.",
    "Gender": "Split of the audience by gender.",
    "Age": "Split of the audience by age group.",
    "Age by gender": "Each age group split into women and men, as a share of the whole audience.",
    "Location by country": "Where the audience lives, by country.",
    "Location by city": "Where the audience lives, by city.",
    "Languages": "Languages the audience uses on Instagram.",
    "Audience interests": "Topics the audience is interested in, based on the accounts they follow.",
    "Audience brand affinity": "Brands the audience follows or engages with — useful to check fit with a client's brand. Small lists come from a sample of the audience, so treat close values as equal.",
    "Popular hashtags": "Share of the creator's recent posts that use each hashtag.",
    "Popular mentions": "Share of the creator's recent posts that tag or mention each account.",
    "Sponsored posts": "Recent posts identified as paid partnerships."
  };
  /* How sure each number is, by what kind of number it is — so every
     profile, and every one imported later, carries it without extra work.
       3 bars  Measured   read from the public profile, or simple maths on it
       2 bars  Estimated  worked out from a sample or a model; right in direction
       1 bar   Rough hint few posts behind it; can swing a lot
     A label not listed here (a new field) shows no sign rather than a guess. */
  var TRUST_WORD = { 3: "Measured", 2: "Estimated", 1: "Rough hint" };
  var TRUST_WHY = { 3: "Read from the public profile — reliable.", 2: "Worked out from a sample of the audience or a model — right in direction, not exact.",
                    1: "Based on only a few posts — can swing a lot. Use as a hint only." };
  var TRUST = {
    "Followers": 3, "Avg. likes": 3, "Engagement rate": 3, "Followers growth": 3, "Likes growth": 3,
    "Average views": 3, "Average likes": 3, "Average comments": 3, "Average reel plays": 3, "Average shares": 3,
    "Popular hashtags": 3, "Popular mentions": 3, "Sponsored posts": 3, "Creator brand affinity": 3, "h2|Popular posts": 3,
    "Estimated impressions": 2, "Estimated reach": 2, "Fake followers": 2, "Fake likers": 2, "Audience reachability": 2,
    "Fake followers distribution": 2, "Engagement rate distribution": 2, "Gender": 2, "Age": 2, "Age by gender": 2,
    "Location by country": 2, "Location by city": 2, "Languages": 2, "Audience interests": 2, "Creator interests": 2,
    "Paid engagement": 1, "Paid views": 1, "Audience brand affinity": 1
  };
  function trustSign(n) {
    var t = "How sure: " + TRUST_WORD[n] + " — " + TRUST_WHY[n];
    return ' <i class="pp-trust pp-trust--' + n + '" tabindex="0" role="note" aria-label="' + esc(t) + '" data-tip="' + esc(t) + '"><b></b><b></b><b></b></i>';
  }
  function addTrust(root) {
    [].forEach.call((root || document).querySelectorAll(".pp-h2, .pp-h3, .pp-key dt, .pp-tiles > div > span, .pp-row > span, .pp-er__label"), function (el) {
      if (el.querySelector(".pp-trust")) return;
      var tip = el.querySelector(".pp-tip"), text = (tip ? el.textContent.slice(0, -tip.textContent.length) : el.textContent).trim();
      var n = el.classList.contains("pp-h2") ? TRUST["h2|" + text] : TRUST[text];
      if (n) el.insertAdjacentHTML("beforeend", trustSign(n));
    });
    var leg = $("pp-trust-key");
    if (!leg && $("pp-pages")) {
      $("pp-pages").insertAdjacentHTML("afterbegin", '<p class="pp-trust-key" id="pp-trust-key"><span>How sure is each number?</span>'
        + [3, 2, 1].map(function (n) { return '<span class="pp-trust-key__i"><i class="pp-trust pp-trust--' + n + '"><b></b><b></b><b></b></i><b>' + TRUST_WORD[n] + "</b>" + TRUST_WHY[n].split(" — ")[0].replace(/\.$/, "") + "</span>"; }).join("") + "</p>");
    }
  }
  function addTips(root) {
    addTrust(root);
    [].forEach.call((root || document).querySelectorAll(".pp-h2, .pp-h3, .pp-key dt, .pp-tiles > div > span, .pp-row > span, .pp-er__label"), function (el) {
      if (el.querySelector(".pp-tip")) return;
      var text = el.textContent.trim(), pane = el.closest(".pp-pane"), ctx = pane ? pane.getAttribute("data-tab") : "";
      var tip = TIPS[ctx + "|" + text] || (el.classList.contains("pp-h2") ? TIPS["h2|" + text] : null) || TIPS[text];
      if (!tip) return;
      el.insertAdjacentHTML("beforeend", ' <i class="pp-tip" tabindex="0" role="note" aria-label="' + esc(tip) + '" data-tip="' + esc(tip) + '">i</i>');
    });
  }
  // A tip near the right edge opens leftwards, so it never runs off the screen.
  function placeTip(e) {
    var t = e.target.closest && e.target.closest(".pp-tip"); if (!t) return;
    t.classList.toggle("pp-tip--end", t.getBoundingClientRect().left > window.innerWidth - 280);
  }
  document.addEventListener("mouseover", placeTip);
  document.addEventListener("focusin", placeTip);

  function render() {
    var c = D.creator;
    PLAT = choosePlat();
    var a = (D.analyses || {})[PLAT] || null;
    D.analysis = a;
    document.title = c.name + " — Creator analysis — HelloVoice";
    window.scrollTo(0, 0);
    renderId(c, a);
    renderPlatforms(c);
    $("pp-sealed").hidden = !!a;
    $("pp-pages").hidden = !a;
    if (!a) return renderSealed(c);
    if (a.basic) return renderBasic(a);
    renderPosts(a);
    renderReal(a);
    renderPerf(a);
    renderNetwork(a);
    renderAudience(a);
    renderTags(a);
    $("pp-source").textContent = a.updated ? "Data as of " + day(a.updated) : "";
    addTips();
  }

  /* a basic record: the public numbers we have collected, and every other
     section held back as pending (blurred, with nothing real behind it) */
  function renderBasic(a) {
    var T = [["Followers", a.followers != null ? num(a.followers) : "—"],
             ["Following", a.following != null ? num(a.following) : "—"],
             ["Posts", a.posts_count != null ? num(a.posts_count) : "—"],
             ["Avg likes", a.avg_likes != null ? num(Math.round(a.avg_likes)) : "—"],
             ["Avg comments", a.avg_comments != null ? num(Math.round(a.avg_comments)) : "—"],
             ["Engagement rate", a.er != null ? pct2(a.er) : "—"],
             ["Avg views", a.avg_views != null ? num(Math.round(a.avg_views)) : null],
             ["Posts per week", a.posts_per_week != null ? (+a.posts_per_week).toFixed(1) : "—"],
             ["Last post", a.last_post ? day(a.last_post) : "—"]];
    T = T.filter(function (t) { return t[1] !== null; });
    $("pp-real").innerHTML = '<div class="pp-tiles pp-tiles--big">' + T.map(function (t) {
      return '<div class="pp-tile"><span>' + t[0] + "</span><b>" + t[1] + "</b></div>"; }).join("") + "</div>"
      + (a.sample_posts ? '<p class="pp-basicnote">Worked out from this creator\'s latest ' + a.sample_posts + " public posts." + (a.er_basis === "views" ? " Engagement is measured against views." : "") + "</p>" : "");
    $("pp-h-real").textContent = "Basic numbers";
    $("pp-real-sec").hidden = false;
    var ghost = '<div class="pp-pending"><div class="pp-pending__ghost" aria-hidden="true"><i style="width:82%"></i><i style="width:64%"></i><i style="width:90%"></i><i style="width:48%"></i><i style="width:72%"></i></div>'
      + '<span class="pp-pending__tag"><b>Pending</b><small>Not collected yet</small></span></div>';
    ["pp-posts", "pp-perf", "pp-net", "pp-aud", "pp-tags"].forEach(function (id) { $(id).innerHTML = ghost; });
    ["pp-perf-tabs", "pp-aud-tabs"].forEach(function (id) { $(id).innerHTML = ""; });
    ["pp-posts-sec", "pp-net-sec", "pp-aud-sec", "pp-tags-sec"].forEach(function (id) { $(id).hidden = false; });
    var c = D.creator, asked = (D.requested || []).indexOf(PLAT) !== -1;
    $("pp-real").insertAdjacentHTML("beforeend", '<div class="pp-request"><div><b>Want the full ' + esc(PLAT || "") + ' analysis?</b>'
      + '<p>Audience countries, age and gender, real versus fake followers, content performance and brand affinity are pending for ' + esc(c.name) + ".</p></div>"
      + '<button type="button" class="pp-btn" id="pp-ask"' + (asked ? " disabled" : "") + ">" + (asked ? "Requested ✓" : "Request full analysis") + "</button>"
      + '<p class="pp-sealed__done" id="pp-ask-done"' + (asked ? "" : " hidden") + ">Your request is with the HelloVoice team — we will add it and let you know.</p></div>");
    var ask = $("pp-ask");
    if (ask && !asked) ask.addEventListener("click", function () {
      ask.disabled = true; ask.textContent = "Sending…";
      fetch(API + "/api/creator/request", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: c.code, platform: PLAT }) })
        .then(function (r) { if (!r.ok) throw 0; ask.textContent = "Requested ✓"; $("pp-ask-done").hidden = false; D.requested = (D.requested || []).concat([PLAT]); renderPlatforms(c); })
        .catch(function () { ask.disabled = false; ask.textContent = "Request full analysis"; var n = $("pp-ask-done"); n.textContent = "Could not send the request. Please try again."; n.hidden = false; });
    });
    $("pp-source").textContent = "Basic public numbers" + (a.updated ? " as of " + day(a.updated) : "") + ". Audience, content and brand sections are pending.";
  }

  /* identity: who, the three numbers, bio */
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
      ["Engagement rate", pct2(a.er), erTag(a.er, a.followers || c.followers)]
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

  /* one tab per platform the creator is on; a platform with no analysis is a locked tab */
  function renderPlatforms(c) {
    var box = $("pp-plat"), ps = D.platforms || [], an = D.analyses || {};
    if (ps.length < 2) { box.hidden = true; box.innerHTML = ""; return; }
    box.hidden = false;
    box.innerHTML = '<span class="pp-plat__label">Analysis by platform</span>' + ps.map(function (p) {
      var has = !!an[p], asked = (D.requested || []).indexOf(p) !== -1;
      return '<button type="button" role="tab" data-p="' + esc(p) + '" aria-selected="' + (p === PLAT) + '" class="' + (has ? "is-on" : "is-off") + '">' + icon(p)
        + "<span>" + esc(p) + "</span><small>" + (has ? "Analysed" : asked ? "Requested" : "Not analysed") + "</small></button>";
    }).join("");
    [].forEach.call(box.querySelectorAll("button"), function (b) {
      b.addEventListener("click", function () {
        var p = b.getAttribute("data-p");
        history.replaceState(null, "", "#c=" + encodeURIComponent(c.code) + "&p=" + encodeURIComponent(p));
        render();
      });
    });
  }

  function renderSealed(c) {
    var asked = (D.requested || []).indexOf(PLAT) !== -1;
    $("pp-sealed").innerHTML = '<div class="pp-sealed__icon" aria-hidden="true">' + ICON_ANALYSIS + "</div>"
      + "<div><h2>" + esc(PLAT || "Full") + " analysis not on file yet</h2><p>The " + esc(PLAT || "full") + " analysis shows where " + esc(c.name) + "'s audience lives, their age and gender, how much of it is real, how it has grown, how posts perform and the brands they have worked with.</p>"
      + '<ul class="pp-sealed__list"><li>Audience countries, cities, age &amp; gender</li><li>Real vs fake followers</li><li>Engagement and content performance</li><li>Brands &amp; interests</li></ul>'
      + '<button type="button" class="pp-btn" id="pp-ask"' + (asked ? " disabled" : "") + ">" + (asked ? "Requested ✓" : "Request " + (PLAT || "full") + " analysis") + "</button>"
      + '<p class="pp-sealed__done" id="pp-ask-done"' + (asked ? "" : " hidden") + ">Your request is with the HelloVoice team — we will add it and let you know.</p></div>";
    var btn = $("pp-ask");
    if (btn && !asked) btn.addEventListener("click", function () {
      btn.disabled = true; btn.textContent = "Sending…";
      fetch(API + "/api/creator/request", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: c.code, platform: PLAT }) })
        .then(function (r) { if (!r.ok) throw 0; btn.textContent = "Requested ✓"; $("pp-ask-done").hidden = false; D.requested = (D.requested || []).concat([PLAT]); renderPlatforms(c); })
        .catch(function () { btn.disabled = false; btn.textContent = "Request " + (PLAT || "full") + " analysis"; var n = $("pp-ask-done"); n.textContent = "Could not send the request. Please try again."; n.hidden = false; });
    });
  }

  /* tabs shared by Content and Audience */
  function tabs(box, pane, list, draw) {
    var on = 0;
    function paint() {
      $(box).innerHTML = list.length > 1 ? list.map(function (t, i) { return '<button type="button" role="tab" aria-selected="' + (i === on) + '" data-i="' + i + '">' + esc(t.label) + "</button>"; }).join("") : "";
      $(pane).innerHTML = list.map(function (t, i) { return '<div class="pp-pane" data-tab="' + esc(t.label) + '"' + (i === on ? "" : " hidden") + ">" + draw(t) + "</div>"; }).join("");
      if (pane === "pp-perf") collab();
      addTips($(pane));
    }
    paint();
    $(box).onclick = function (e) { var b = e.target.closest("button[data-i]"); if (!b) return; on = +b.getAttribute("data-i"); paint(); };
  }

  /* one metric row: label, a bar against the largest in its group, the value */
  // Each bar is measured against what a strong creator of this size gets for
  // THAT measure — likes against strong likes, comments against strong
  // comments — not against impressions, which are always far bigger. The
  // tick is the typical level. Guides by size: engagement = likes + comments
  // per 100 followers (strong / typical), comments ≈ 3% of reactions,
  // reach ≈ share of followers who see a post.
  var SIZE_ER = [[10000, 4, 2], [50000, 3, 1.5], [500000, 2, 1], [1000000, 1.5, 0.8], [Infinity, 1, 0.5]];
  function refs(f) {
    if (!f) return null;
    var er = SIZE_ER.filter(function (x) { return f < x[0]; })[0];
    var reach = [f * 0.30, f * 0.10];
    return { likes: [f * er[1] / 100 * 0.97, f * er[2] / 100 * 0.97], comments: [f * er[1] / 100 * 0.03, f * er[2] / 100 * 0.03],
             reach: reach, impressions: [reach[0] * 1.5, reach[1] * 1.5], views: reach, shares: [f * er[1] / 100 * 0.05, f * er[2] / 100 * 0.05],
             story: [f * 0.08, f * 0.04] };
  }
  function scaled(items, colour) {
    return '<div class="pp-rows">' + items.map(function (r) {
      if (!r.ref || r.v == null || r.text === "Hidden") return '<div class="pp-row"><span>' + r.label + '</span><i class="pp-row__bar"></i><strong>' + r.text + "</strong></div>";
      var strong = r.ref[0], typ = r.ref[1], w = Math.min(100, r.v / strong * 100), g = r.v >= strong ? "good" : r.v >= typ ? "ok" : "low";
      return '<div class="pp-row"><span>' + r.label + '</span><i class="pp-row__bar pp-row__bar--ref" title="Compared with a strong result for creators this size: typical ' + num(typ) + ", strong " + num(strong) + '"><b class="' + g + '" style="width:' + Math.max(2, w).toFixed(1) + "%" + (colour ? ";background:" + colour : "") + '"></b><u style="left:' + (typ / strong * 100).toFixed(1) + '%"></u></i><strong>' + r.text + tagFor(g === "ok" ? "moderate" : g, "Compared with a strong result for creators this size — HelloVoice benchmark") + "</strong></div>";
    }).join("") + '<p class="pp-rows__key">Each bar is compared with a strong result for creators this size · the tick is typical</p></div>';
  }
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
    $("pp-posts-sec").hidden = false;
    $("pp-posts").innerHTML = (top.length || sp.length)
      ? (top.length ? postGrid(top, false) : "") + (sp.length ? '<h3 class="pp-h3">Sponsored posts</h3>' + postGrid(sp, true) : "")
      : '<p class="pp-missing">Not in this report.</p>';
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
    if (a.fake_followers_pct != null) tiles.push(["Fake followers", pct2(a.fake_followers_pct), fakeTag(a.fake_followers_pct, "fake_followers")]);
    if (a.fake_likers_pct != null) tiles.push(["Fake likers", pct2(a.fake_likers_pct), fakeTag(a.fake_likers_pct, "fake_likers")]);
    if (a.fake_followers_pct == null && a.fake_likers_pct == null) out += '<p class="pp-missing">Fake-follower data is not in this report.</p>';
    if (tiles.length) out += '<div class="pp-tiles pp-tiles--big">' + tiles.map(function (t) { return '<div class="pp-tile"><span>' + t[0] + "</span><b>" + t[1] + "</b>" + (t[2] || "") + "</div>"; }).join("") + "</div>";
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
  // The source report paints the median bar grey only when the creator is
  // somewhere else; when the creator sits in the median bar it carries the
  // creator's colour and no grey bar is drawn. So no median given = the
  // creator is the median, and the chart says so.
  function dist(d, colour) {
    var b = d.buckets || [], atMedian = d.creator != null && (d.median == null || d.median === d.creator);
    return '<div class="pp-dist" role="img" aria-label="Distribution among similar creators">' + b.map(function (x, i) {
      var who = i === d.creator ? " is-creator" : (i === d.median ? " is-median" : "");
      return '<div class="pp-dist__col' + who + (i === d.creator && atMedian ? " is-both" : "") + '">' + (i === d.creator && atMedian ? '<em class="pp-dist__tag">Median</em>' : "")
        + '<i style="height:' + Math.max(3, x.h) + "%" + (who === " is-creator" && colour ? ";background:" + colour : "") + '"></i><span>' + esc(x.label) + "</span></div>";
    }).join("") + '</div><p class="pp-dist__key"><span class="pp-dist__k"><i class="k-creator"' + (colour ? ' style="background:' + colour + '"' : "") + '></i>Creator</span>'
      + (atMedian ? "" : '<span class="pp-dist__k"><i class="k-median"></i>Median</span>') + '<span class="pp-dist__k"><i class="k-other"></i>Other creators</span></p>'
      + (atMedian ? '<p class="pp-dist__same">This creator sits exactly at the median — typical for this size.</p>' : "");
  }

  /* content: all content / reels / stories, collaborations, ER distribution */
  function renderPerf(a) {
    var list = [];
    function erBlock(v, note, label) {
      return '<div class="pp-er"><span class="pp-er__label">' + label + "</span><b>" + pct2(v) + "</b>" + erTag(v, a.followers || (D.creator && D.creator.followers)) + (note ? "<p>" + esc(note) + "</p>" : "") + "</div>";
    }
    var all = [];
    if (a.est_impressions != null) all.push({ label: "Estimated impressions", v: a.est_impressions, text: num(a.est_impressions) });
    if (a.est_reach != null) all.push({ label: "Estimated reach", v: a.est_reach, text: num(a.est_reach) });
    if (a.avg_views != null) all.push({ label: "Average views", v: a.avg_views, text: num(a.avg_views) });
    if (a.avg_likes != null) all.push({ label: "Average likes", v: a.avg_likes, text: num(a.avg_likes) });
    else if (a.likes_hidden) all.push({ label: "Average likes", v: 0, text: "Hidden" });
    if (a.avg_comments != null) all.push({ label: "Average comments", v: a.avg_comments, text: num(a.avg_comments) });
    var R = refs(a.followers || (D.creator && D.creator.followers));
    function tag(list, map) { if (R) list.forEach(function (x) { x.ref = R[map[x.label]]; }); return list; }
    var M = { "Estimated impressions": "impressions", "Estimated reach": "reach", "Average views": "views", "Average likes": "likes",
              "Average comments": "comments", "Average reel plays": "views", "Average shares": "shares" };
    list.push({ label: "All content", html: erBlock(a.er, a.er_note, "Engagement rate") + (R ? scaled(tag(all, M), "#5b4bd6") : rows(all, "#5b4bd6")) });
    var reels = [];
    if (a.avg_reel_plays != null) reels.push({ label: "Average reel plays", v: a.avg_reel_plays, text: num(a.avg_reel_plays) });
    if (a.avg_reel_likes != null) reels.push({ label: "Average likes", v: a.avg_reel_likes, text: num(a.avg_reel_likes) });
    if (a.avg_reel_comments != null) reels.push({ label: "Average comments", v: a.avg_reel_comments, text: num(a.avg_reel_comments) });
    if (a.avg_reel_shares != null) reels.push({ label: "Average shares", v: a.avg_reel_shares, text: num(a.avg_reel_shares) });
    if (reels.length || a.reels_er != null) list.push({ label: "Reels", html: (a.reels_er != null ? erBlock(a.reels_er, a.reels_er_note, "Engagement rate") : "") + (R ? scaled(tag(reels, M), "#ff691e") : rows(reels, "#ff691e")) });
    var st = [];
    if (a.story_reach != null) st.push({ label: "Estimated reach", v: a.story_reach, text: num(a.story_reach) });
    if (a.story_impressions != null) st.push({ label: "Estimated impressions", v: a.story_impressions, text: num(a.story_impressions) });
    if (st.length) list.push({ label: "Stories", html: R ? scaled(st.map(function (x) { x.ref = x.label === "Estimated reach" ? R.story : [R.story[0] * 1.2, R.story[1] * 1.2]; return x; }), "#14884a") : rows(st, "#14884a") });
    tabs("pp-perf-tabs", "pp-perf", list, function (t) { return '<div class="pp-perf">' + t.html + "</div>"; });
  }
  function collab() {
    var a = D.analysis, co = [], out = "";
    // A plain-words line under each figure: 100% = sponsored posts do as
    // well as the creator's normal posts.
    function said(v, what) {
      if (v >= 110) return ["good", "Ads do better than normal posts"];
      if (v >= 85) return ["good", "Ads do about as well as normal posts"];
      if (v >= 50) return ["ok", "Ads get less " + what + " than normal posts"];
      if (v >= 5) return ["low", "Ads get much less " + what + " than normal posts"];
      return ["low", "Ads get almost no " + what + " compared with normal posts"];
    }
    if (a.paid_post_performance != null) co.push(["Paid engagement", pct2(a.paid_post_performance), said(a.paid_post_performance, "likes and comments")]);
    if (a.paid_views_pct != null) co.push(["Paid views", pct2(a.paid_views_pct), said(a.paid_views_pct, "views")]);
    if (co.length) out += '<div class="pp-collab"><h3 class="pp-h3">Collaborations</h3><div class="pp-tiles">'
      + co.map(function (x) { return "<div><span>" + x[0] + "</span><b>" + x[1] + '</b><small class="pp-said pp-said--' + x[2][0] + '">' + esc(x[2][1]) + "</small></div>"; }).join("") + "</div>"
      + '<p class="pp-rows__key">100% means sponsored posts do as well as the creator\'s normal posts</p></div>';
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
      // The trust key goes right after the creator's identity: on paper there
      // is no hover, so the key is what explains the bars beside each number.
      addTrust();
      var blocks = [$("pp-id"), $("pp-trust-key")].filter(Boolean)
        .concat([].slice.call(document.querySelectorAll("#pp-pages > .pp-page:not([hidden]), #pp-source")));
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
        doc.save((c.name || c.code).replace(/[^\w؀-ۿ -]+/g, "").trim().replace(/\s+/g, "-") + "-" + c.code + "-" + (PLAT || "").toLowerCase() + "-analysis.pdf");
      });
    }).catch(function () {
      alert("The PDF could not be made. Please try again.");
    }).then(function () {
      root.classList.remove("pp-pdf"); btn.disabled = false; btn.innerHTML = label;
    });
  }

  load();
})();
