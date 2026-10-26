/* Campaign dashboard — the client's campaign on one screen. Same data as the
   long report (GET /api/campaign?t=<token>); filters (platform, dates,
   creators) are applied here in the browser and every card recalculates.
   Targets, verdict and audience are whole-campaign by nature and say so. */
(function () {
  "use strict";

  var API = (window.CAMPAIGN_CONFIG || {}).api || "/admin";
  var ICONS = (window.HV_ICONS || {}).icons || {};
  // Official platform marks (simple-icons, CC0): solid glyphs in each brand's own colours, over the shared outline set.
  var BRAND = {"Instagram": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path fill=\"url(#hv-ig)\" d=\"M7.0301.084c-1.2768.0602-2.1487.264-2.911.5634-.7888.3075-1.4575.72-2.1228 1.3877-.6652.6677-1.075 1.3368-1.3802 2.127-.2954.7638-.4956 1.6365-.552 2.914-.0564 1.2775-.0689 1.6882-.0626 4.947.0062 3.2586.0206 3.6671.0825 4.9473.061 1.2765.264 2.1482.5635 2.9107.308.7889.72 1.4573 1.388 2.1228.6679.6655 1.3365 1.0743 2.1285 1.38.7632.295 1.6361.4961 2.9134.552 1.2773.056 1.6884.069 4.9462.0627 3.2578-.0062 3.668-.0207 4.9478-.0814 1.28-.0607 2.147-.2652 2.9098-.5633.7889-.3086 1.4578-.72 2.1228-1.3881.665-.6682 1.0745-1.3378 1.3795-2.1284.2957-.7632.4966-1.636.552-2.9124.056-1.2809.0692-1.6898.063-4.948-.0063-3.2583-.021-3.6668-.0817-4.9465-.0607-1.2797-.264-2.1487-.5633-2.9117-.3084-.7889-.72-1.4568-1.3876-2.1228C21.2982 1.33 20.628.9208 19.8378.6165 19.074.321 18.2017.1197 16.9244.0645 15.6471.0093 15.236-.005 11.977.0014 8.718.0076 8.31.0215 7.0301.0839m.1402 21.6932c-1.17-.0509-1.8053-.2453-2.2287-.408-.5606-.216-.96-.4771-1.3819-.895-.422-.4178-.6811-.8186-.9-1.378-.1644-.4234-.3624-1.058-.4171-2.228-.0595-1.2645-.072-1.6442-.079-4.848-.007-3.2037.0053-3.583.0607-4.848.05-1.169.2456-1.805.408-2.2282.216-.5613.4762-.96.895-1.3816.4188-.4217.8184-.6814 1.3783-.9003.423-.1651 1.0575-.3614 2.227-.4171 1.2655-.06 1.6447-.072 4.848-.079 3.2033-.007 3.5835.005 4.8495.0608 1.169.0508 1.8053.2445 2.228.408.5608.216.96.4754 1.3816.895.4217.4194.6816.8176.9005 1.3787.1653.4217.3617 1.056.4169 2.2263.0602 1.2655.0739 1.645.0796 4.848.0058 3.203-.0055 3.5834-.061 4.848-.051 1.17-.245 1.8055-.408 2.2294-.216.5604-.4763.96-.8954 1.3814-.419.4215-.8181.6811-1.3783.9-.4224.1649-1.0577.3617-2.2262.4174-1.2656.0595-1.6448.072-4.8493.079-3.2045.007-3.5825-.006-4.848-.0608M16.953 5.5864A1.44 1.44 0 1 0 18.39 4.144a1.44 1.44 0 0 0-1.437 1.4424M5.8385 12.012c.0067 3.4032 2.7706 6.1557 6.173 6.1493 3.4026-.0065 6.157-2.7701 6.1506-6.1733-.0065-3.4032-2.771-6.1565-6.174-6.1498-3.403.0067-6.156 2.771-6.1496 6.1738M8 12.0077a4 4 0 1 1 4.008 3.9921A3.9996 3.9996 0 0 1 8 12.0077\"/></svg>", "TikTok": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path fill=\"#25f4ee\" transform=\"translate(-.55 -.45)\" d=\"M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z\"/><path fill=\"#fe2c55\" transform=\"translate(.55 .45)\" d=\"M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z\"/><path fill=\"currentColor\" d=\"M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z\"/></svg>", "Snapchat": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path fill=\"#fffc00\" stroke=\"#121212\" stroke-width=\".9\" stroke-linejoin=\"round\" d=\"M12.206.793c.99 0 4.347.276 5.93 3.821.529 1.193.403 3.219.299 4.847l-.003.06c-.012.18-.022.345-.03.51.075.045.203.09.401.09.3-.016.659-.12 1.033-.301.165-.088.344-.104.464-.104.182 0 .359.029.509.09.45.149.734.479.734.838.015.449-.39.839-1.213 1.168-.089.029-.209.075-.344.119-.45.135-1.139.36-1.333.81-.09.224-.061.524.12.868l.015.015c.06.136 1.526 3.475 4.791 4.014.255.044.435.27.42.509 0 .075-.015.149-.045.225-.24.569-1.273.988-3.146 1.271-.059.091-.12.375-.164.57-.029.179-.074.36-.134.553-.076.271-.27.405-.555.405h-.03c-.135 0-.313-.031-.538-.074-.36-.075-.765-.135-1.273-.135-.3 0-.599.015-.913.074-.6.104-1.123.464-1.723.884-.853.599-1.826 1.288-3.294 1.288-.06 0-.119-.015-.18-.015h-.149c-1.468 0-2.427-.675-3.279-1.288-.599-.42-1.107-.779-1.707-.884-.314-.045-.629-.074-.928-.074-.54 0-.958.089-1.272.149-.211.043-.391.074-.54.074-.374 0-.523-.224-.583-.42-.061-.192-.09-.389-.135-.567-.046-.181-.105-.494-.166-.57-1.918-.222-2.95-.642-3.189-1.226-.031-.063-.052-.15-.055-.225-.015-.243.165-.465.42-.509 3.264-.54 4.73-3.879 4.791-4.02l.016-.029c.18-.345.224-.645.119-.869-.195-.434-.884-.658-1.332-.809-.121-.029-.24-.074-.346-.119-1.107-.435-1.257-.93-1.197-1.273.09-.479.674-.793 1.168-.793.146 0 .27.029.383.074.42.194.789.3 1.104.3.234 0 .384-.06.465-.105l-.046-.569c-.098-1.626-.225-3.651.307-4.837C7.392 1.077 10.739.807 11.727.807l.419-.015h.06z\"/></svg>", "YouTube": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path fill=\"#ff0000\" d=\"M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z\"/></svg>", "Facebook": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path fill=\"#0866ff\" d=\"M9.101 23.691v-7.98H6.627v-3.667h2.474v-1.58c0-4.085 1.848-5.978 5.858-5.978.401 0 .955.042 1.468.103a8.68 8.68 0 0 1 1.141.195v3.325a8.623 8.623 0 0 0-.653-.036 26.805 26.805 0 0 0-.733-.009c-.707 0-1.259.096-1.675.309a1.686 1.686 0 0 0-.679.622c-.258.42-.374.995-.374 1.752v1.297h3.919l-.386 2.103-.287 1.564h-3.246v8.245C19.396 23.238 24 18.179 24 12.044c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.628 3.874 10.35 9.101 11.647Z\"/></svg>", "X": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path fill=\"currentColor\" d=\"M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z\"/></svg>"};
  ICONS = (function (base) { var o = {}, k; for (k in base) o[k] = base[k]; for (k in BRAND) o[k] = BRAND[k]; return o; })(ICONS);
  if (document.body && !document.getElementById("hv-ig")) document.body.insertAdjacentHTML("beforeend", "<svg width=\"0\" height=\"0\" style=\"position:absolute\" aria-hidden=\"true\"><defs><linearGradient id=\"hv-ig\" x1=\"0\" y1=\"1\" x2=\"1\" y2=\"0\"><stop offset=\"0\" stop-color=\"#feda75\"/><stop offset=\".25\" stop-color=\"#fa7e1e\"/><stop offset=\".5\" stop-color=\"#d62976\"/><stop offset=\".75\" stop-color=\"#962fbf\"/><stop offset=\"1\" stop-color=\"#4f5bd5\"/></linearGradient></defs></svg>");
  var LINK = (window.HV_ICONS || {}).link || "";
  var R = null, TOKEN = "", PRINT_W = 0;
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
  function shareTok() { var m = /(?:^|[#&])share=([A-Za-z0-9_-]+)/.exec(location.hash || ""); return m ? m[1] : ""; }
  function token() { var m = /(?:^|[#&])t=([A-Za-z0-9_-]+)/.exec(location.hash || ""); return m ? m[1] : ""; }
  function get(path) { return fetch(API + path, { credentials: "include", cache: "no-store" }).then(function (r) { if (r.status === 401) throw { locked: true }; if (!r.ok) throw { status: r.status }; return r.json(); }); }

  // Report sync (2026-10-23). The server's rev fingerprints everything the page shows: while the dashboard is open it
  // checks every five minutes and when its tab comes back, and redraws only on a change. A change made here (an
  // update, the team's edits) is announced to the report open in another tab, which then checks at once.
  var WATCH = null;
  function watch() {
    if (WATCH) return;
    function check() {
      if (document.hidden || !R || !TOKEN) return;
      get("/api/campaign?t=" + encodeURIComponent(TOKEN) + (shareTok() ? "&share=" + encodeURIComponent(shareTok()) : "")).then(function (b) {
        if (b && b.report && b.report.rev && b.report.rev !== R.rev) { CMB.items = null; load(); }
      }).catch(function () {});
    }
    WATCH = setInterval(check, window.__pollMs || 300000);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) check(); });
  }
  function changed() { try { localStorage.setItem("hv_campaign_changed", TOKEN + "|" + Date.now()); } catch (e) {} }
  // With an ER goal every ER verdict grades against it, as the server grades the creators and posts (metrics.goal_grading).
  function erGoal() { var sc = scope(), it = sc.mode === "plat" ? (sc.bp.progress.items || []).filter(function (i) { return i.key === "er"; })[0] : null; return it ? it.goal : (R.benchmarks || {}).er_goal || null; }
  function goalGrade(v) { var gl = erGoal(); return v == null || !gl ? null : v >= gl ? "good" : v >= 0.7 * gl ? "moderate" : "low"; }

  /* --------------------------------------------------------------- gate */
  // Not signed in (401): the gate, which portal.js turns into the email sign-in. No access-code
  // form any more (item 181); signing in reloads this same #t= link.
  function lock() {
    var gate = $("cat-gate");
    $("cat-app").hidden = true; gate.hidden = false; document.body.classList.add("cat-locked");
    if (!gate.classList.contains("cx-gate")) document.body.classList.add("cat-checking");
    try { document.dispatchEvent(new CustomEvent("cat:locked")); } catch (e) { /* old browser */ }
  }

  function load() {
    TOKEN = token();
    // No campaign named: one campaign opens straight away; several go to the
    // "My campaigns" list, whose cards come back here.
    var go = TOKEN ? Promise.resolve(TOKEN) : get("/api/campaigns").then(function (b) {
      var l = b.campaigns || [];
      location.replace("../#list"); throw { moved: true }; });
    get("/api/campaigns").then(function (b) { $("db-all").hidden = !(b.campaigns || []).length; }).catch(function () {});
    go.then(function (t) { TOKEN = t; return get("/api/campaign?t=" + encodeURIComponent(t) + (shareTok() ? "&share=" + encodeURIComponent(shareTok()) : "")); })
      .then(function (b) {
        R = b.report;
        $("cat-gate").hidden = true; $("cat-app").hidden = false; document.body.classList.remove("cat-locked", "cat-checking");
        setupHeader(); setupFilters(); renderAll(); setupShare(); watch();
        // The report's "Download PDF" comes here with &pdf=1: the PDF is built from this page's panels.
        if (/[#&]pdf=1/.test(location.hash)) { history.replaceState(null, "", location.pathname + location.hash.replace(/&pdf=1/, "")); printAll(); }
      })
      .catch(function (err) {
        if (err && err.locked) return lock();
        if (err && err.moved) return;
        $("cat-gate").hidden = true; $("db-empty").hidden = false;
        $("db-empty").textContent = err && err.status === 404 ? "This campaign is not available to the account signed in here."
          : "Could not load this campaign. Please try again in a moment.";
      });
  }

  /* ------------------------------------------------------------- header */
  function setupHeader() {
    var c = R.campaign;
    document.title = c.name + " — Dashboard — HELVi Connect";
    $("db-title").textContent = c.name;
    var logos = (c.logos || []).map(function (u) { return '<img src="' + esc(u) + '" alt="">'; }).join("");
    $("db-brands").innerHTML = logos ? "<span>×</span>" + logos : "";   // HELVi × brand (mobile audit 2026-10-19)
    var now = Date.now() / 1000, bits = [];
    if (c.status === "live") bits.push('<span class="db-live">LIVE</span>');
    if (c.starts_at && c.ends_at) {
      var total = Math.max(1, Math.round((c.ends_at - c.starts_at) / 86400)), dn = Math.min(total, Math.max(1, Math.ceil((now - c.starts_at) / 86400)));
      bits.push(now < c.starts_at ? "Starts " + day(c.starts_at) : now <= c.ends_at ? "Day " + dn + " of " + total : "Ran " + total + " days");
      bits.push(day(c.starts_at) + " – " + day(c.ends_at, true));
    }
    if (c.client) bits.unshift(esc(c.client));
    $("db-sub").innerHTML = bits.map(function (b) { return '<span class="db-sub__i">' + b + "</span>"; }).join("");
    var v = R.verdict || {};
    // The verdict, big and solid, with how much of the goals is reached.
    var P = R.progress || {}, pc = P.overall != null ? Math.round(P.all_met ? 100 : Math.min(99, P.overall)) : null;
    $("db-verdict").innerHTML = v.label ? '<span class="db-verdict' + (v.grade ? " db-verdict--" + v.grade : "") + '" role="status" title="How the campaign is doing against its targets today">'
      + esc(v.label) + (pc != null ? '<b class="db-verdict__pct">' + pc + "%</b>" : "") + "</span>" : "";
    $("db-report").href = "../#t=" + TOKEN;
    // The PDF is built here, from every panel of this dashboard, so it always holds all of it (2026-10-23).
    $("db-pdf").href = "#t=" + TOKEN;
    if (!$("db-pdf").getAttribute("data-wired")) { $("db-pdf").setAttribute("data-wired", "1"); $("db-pdf").addEventListener("click", function (e) { e.preventDefault(); printAll(); }); }
    renderFresh();
  }

  // When the data was last captured, and a live countdown to the next capture.
  function renderFresh() {
    var el = $("db-fresh"), next = R.next_update_at || null;
    function p(n) { return (n < 10 ? "0" : "") + n; }
    if (window.__cdIv) { clearInterval(window.__cdIv); window.__cdIv = null; }
    if (!next) { el.className = "db-fresh db-fresh--live"; el.innerHTML = '<span class="db-fresh__txt">' + esc(R.updated_at ? "Updated " + ago(R.updated_at) : "Waiting for the first capture") + "</span>"; mountUpdate(el); return; }
    el.className = "db-fresh db-fresh--live";
    el.innerHTML = '<span class="db-fresh__txt"><span class="db-fresh__live"><i class="db-fresh__dot"></i>Live data</span>'
      + (R.updated_at ? "Updated " + esc(ago(R.updated_at)) : "Waiting for the first capture") + "</span>"
      + '<span class="db-fresh__lbl">Next update in</span>'
      + '<span class="db-cd" role="timer" aria-label="Time until the next update" title="Next update in (hours : minutes : seconds)"><b id="cd-h">00</b><i>:</i><b id="cd-m">00</b><i>:</i><b id="cd-s"><span>00</span></b></span>';
    var lastSec = -1;
    function tick() {
      var left = Math.max(0, next * 1000 - Date.now()), s = Math.floor(left / 1000), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
      $("cd-h").textContent = p(h); $("cd-m").textContent = p(m);
      var sp = $("cd-s").firstChild;
      if (sec !== lastSec) { lastSec = sec; sp.textContent = p(sec); sp.classList.remove("is-tick"); void sp.offsetWidth; sp.classList.add("is-tick"); }
      if (left === 0 && window.__cdIv) { clearInterval(window.__cdIv); window.__cdIv = null; setTimeout(function () { location.reload(); }, 120000); }
    }
    window.__cdIv = setInterval(tick, 1000); tick();
    mountUpdate(el);
  }

  /* "Update posts" and "Update comments" (item 223, owner 2026-10-21; was one "Update now"): post numbers and comments are
     fetched on different schedules, so each has its own control. A control opens a small panel with the schedule in plain
     words, the last and next run, and Fetch now. Clients share one count of free fetches across both; the team has no
     limit and sees what a fetch costs on Apify. Posts keep Helvi's fetch screen; comments are read in the background. */
  var UPD_IC = {
    posts: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 11a8 8 0 0 0-14.5-4.2M4 4v3.8h3.8"/><path d="M4 13a8 8 0 0 0 14.5 4.2M20 20v-3.8h-3.8"/></svg>',
    comments: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 12.5a7.5 7.5 0 0 1-11 6.6L4 20.5l1.4-4.6A7.5 7.5 0 1 1 20 12.5z"/><path d="M9 11.5h6M9 14.5h3.5"/></svg>'
  };
  var UPD_W = { posts: ["Update posts", "Post numbers", "Views, likes, comments, shares and saves on every post."],
                comments: ["Update comments", "Comments", "What people write under the videos, read and sorted into moods and topics."] };
  function riyadh(t, withDay) {
    var d = new Date(t * 1000), o = { timeZone: "Asia/Riyadh", hour: "numeric", minute: "2-digit", hour12: true };
    var hm = d.toLocaleTimeString("en-US", o).replace(/\s?([AP])M$/i, function (_m, x) { return " " + x.toLowerCase() + "m"; }), k = function (x) { return new Date(x * 1000).toLocaleDateString("en-CA", { timeZone: "Asia/Riyadh" }); };
    var now = Date.now() / 1000, dd = k(t) === k(now) ? "Today" : k(t) === k(now + 86400) ? "Tomorrow" : d.toLocaleDateString("en-GB", { timeZone: "Asia/Riyadh", weekday: "short", day: "numeric", month: "short" });
    return (withDay === false ? "" : dd + ", ") + hm;
  }
  function soon(t) { var s = t - Date.now() / 1000; return s <= 60 ? "any minute" : s < 3600 ? "in " + Math.round(s / 60) + " min" : s < 86400 ? "in " + Math.round(s / 3600) + " h" : (Math.round(s / 86400) === 1 ? "tomorrow" : "in " + Math.round(s / 86400) + " days"); }
  function usd(v) { return "$" + (v < 0.1 ? v.toFixed(3).replace(/0$/, "") : v.toFixed(2)); }
  function mountUpdate(host) {
    var box = document.createElement("div"); box.className = "db-upd";
    box.innerHTML = '<div class="db-upd__cap" role="group" aria-label="Update the data">' + ["posts", "comments"].map(function (w) {
      return '<button type="button" class="db-upd__side" data-upd="' + w + '" aria-haspopup="dialog" aria-expanded="false">' + UPD_IC[w]
        + '<span class="db-upd__t"><b>' + UPD_W[w][0] + '</b><small data-upd-line="' + w + '">&nbsp;</small></span></button>'; }).join("") + "</div>";
    host.appendChild(box);
    var S = null, pop = null, openW = "", cpoll = null;
    var btn = box.querySelector('[data-upd="posts"]'), label = {};      // request() writes "Request sent" here; the panel says it instead
    function out() { return S && !S.unlimited && S.left === 0; }
    function leftText() { return !S || S.unlimited ? "" : S.left + " of " + S.limit + " free updates left"; }
    function line(w) {
      var x = S && S[w]; if (S && S.demo) return "Sample data";
      if (!x) return "";
      if (x.running) return w === "posts" ? "Updating now…" : "Reading now…";
      if (w === "comments" && x.next_at) return "Weekly · next " + soon(x.next_at);     // read once a week (owner, 2026-10-23)
      return x.next_at ? "Next " + soon(x.next_at) : x.last_at ? "Last " + ago(x.last_at) : "Not scheduled";
    }
    function paint(s) {
      if (!s) return; S = s;
      ["posts", "comments"].forEach(function (w) {
        var b = box.querySelector('[data-upd="' + w + '"]'), x = s[w] || {};
        box.querySelector('[data-upd-line="' + w + '"]').textContent = line(w);
        b.classList.toggle("is-busy", !!x.running); b.classList.toggle("is-out", out());
      });
      if (pop && openW) fill(openW);
    }
    function state() { return get("/api/campaign/refresh?t=" + encodeURIComponent(TOKEN)).then(function (s) { paint(s); return s; }); }
    state().catch(function () {});
    function shut() {
      if (!pop) return; pop.remove(); pop = null;
      var b = box.querySelector('[data-upd="' + openW + '"]'); if (b) { b.setAttribute("aria-expanded", "false"); b.focus({ preventScroll: true }); }
      openW = "";
    }
    function place(b) {
      if (!pop) return;
      if (window.innerWidth < 600) { pop.classList.add("is-sheet"); pop.style.left = pop.style.top = ""; return; }
      pop.classList.remove("is-sheet");
      var r = b.getBoundingClientRect(), w = pop.offsetWidth;
      pop.style.left = Math.max(12, Math.min(window.innerWidth - w - 12, r.left + r.width / 2 - w / 2)) + "px";
      pop.style.top = Math.min(r.bottom + 10, window.innerHeight - pop.offsetHeight - 12) + "px";
    }
    function fill(w) {
      var x = (S && S[w]) || {}, team = S && S.unlimited && !S.demo, busy = !!x.running, msg = pop.querySelector(".db-pop__msg"), keep = msg ? msg.textContent : "";
      var go = S && S.demo ? '<p class="db-pop__note">This is a demo campaign: its numbers are sample data, so there is nothing to fetch.</p>'
        : out() ? '<button type="button" class="db-upd__btn db-pop__go" data-go="more">Request more updates</button>'
        : '<button type="button" class="db-upd__btn db-pop__go" data-go="' + w + '"' + (busy ? " disabled" : "") + ">" + UPD_IC[w]
          + "<span>" + (busy ? (w === "posts" ? "Updating…" : "Reading comments…") : "Fetch now" + (team && x.est != null ? " · about " + usd(x.est) : "")) + "</span></button>";
      pop.innerHTML = '<div class="db-pop__h">' + UPD_IC[w] + "<h3>" + UPD_W[w][1] + '</h3><button type="button" class="db-pop__x" aria-label="Close">×</button></div>'
        + '<p class="db-pop__what">' + UPD_W[w][2] + "</p>"
        + '<p class="db-pop__s">' + esc(x.schedule || "Not scheduled") + "</p>"
        + '<dl class="db-pop__dl"><div><dt>Last update</dt><dd>' + (x.last_at ? esc(riyadh(x.last_at)) + "<small>" + esc(ago(x.last_at)) + "</small>" : "Not yet") + "</dd></div>"
        + "<div><dt>Next update</dt><dd>" + (busy ? "Running now" : x.next_at ? esc(riyadh(x.next_at)) + "<small>" + esc(soon(x.next_at)) + "</small>" : "Nothing planned") + "</dd></div></dl>"
        + (team && x.est != null ? '<p class="db-pop__cost">Fetching now costs about <b>' + usd(x.est) + "</b> on Apify" + (x.cost != null ? ". Last manual fetch: <b>" + usd(x.cost) + "</b>." : ".")
          + (x.budget_left != null ? " Apify budget left this month: <b>" + usd(x.budget_left) + "</b>" + (x.est > x.budget_left ? " — not enough, the fetch would wait for next month." : ".") : "") + "</p>" : "")
        + (S && !S.unlimited && !S.demo ? '<p class="db-pop__left"><b>' + S.left + " of " + S.limit + "</b> free updates left, shared by posts and comments.</p>" : "")
        + go + '<p class="db-pop__msg" role="status">' + esc(keep) + "</p>";
    }
    function openPop(w, b) {
      if (pop && openW === w) return shut();
      shut();
      pop = document.createElement("div"); pop.className = "db-pop"; pop.setAttribute("role", "dialog"); pop.setAttribute("aria-label", UPD_W[w][0]);
      document.body.appendChild(pop); openW = w; b.setAttribute("aria-expanded", "true");
      fill(w); place(b);
      var f = pop.querySelector(".db-pop__go") || pop.querySelector(".db-pop__x"); if (f) f.focus({ preventScroll: true });
      state().catch(function () {});
    }
    function say(t) { var m = pop && pop.querySelector(".db-pop__msg"); if (m) m.textContent = t; }
    box.addEventListener("click", function (e) { var b = e.target.closest("[data-upd]"); if (b) openPop(b.getAttribute("data-upd"), b); });
    document.addEventListener("click", function (e) {
      if (!pop) return;
      if (e.target.closest(".db-pop__x")) return shut();
      var go = e.target.closest(".db-pop__go");
      if (go) { var w = go.getAttribute("data-go"); if (w === "more") { shut(); request(); } else if (w === "posts" || w === "comments") { shut(); run(w); } return; }
      if (!e.target.closest(".db-pop") && !e.target.closest("[data-upd]")) shut();
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && pop) shut(); });
    window.addEventListener("resize", function () { if (pop) place(box.querySelector('[data-upd="' + openW + '"]')); });
    function modal(extra) {
      var o = document.createElement("div"); o.className = "db-fetch"; o.setAttribute("role", "dialog"); o.setAttribute("aria-modal", "true");
      var card = document.createElement("div"); card.className = "db-fetch__card" + (extra ? " " + extra : ""); o.appendChild(card);
      document.body.appendChild(o);
      return { card: card, close: function () { o.remove(); } };
    }
    // The wait, for both kinds: Helvi, the steps, a real progress bar, the green tick (comments: owner, 2026-10-21).
    var RUN = {
      posts: { title: "Helvi is fetching the latest numbers", plain: "Fetching the latest numbers…", tau: 18000, max: 5,
               steps: ["Finding the posts on this campaign…", "Asking Instagram, TikTok and Facebook…", "Asking YouTube and Snapchat…", "Adding up the numbers…"],
               busy: function (s) { return s.running; }, ok: "Numbers updated successfully",
               late: "Still working. The new numbers will appear on their own." },
      comments: { title: "Helvi is reading the new comments", plain: "Reading the new comments…", tau: 70000, max: 8,
               steps: ["Asking Instagram, TikTok, YouTube and Facebook…", "Collecting the new comments…", "Reading moods, topics and buying questions…", "Adding them to your dashboard…"],
               busy: function (s) { return s.comments && (s.comments.running || s.comments.pending_ai > 0); }, ok: "Comments updated successfully",
               late: "Still reading. The new comments will appear on their own in a few minutes." }
    };
    function postJSON(path, body) {
      return fetch(API + path, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
        .then(function (r) { return r.json().then(function (b) { return { s: r.status, b: b }; }); });
    }
    // The wait: Helvi, the steps, the balance.
    function run(kind) {
      kind = kind === "comments" ? "comments" : "posts";
      var K = RUN[kind], m = modal(), cook = null, t0 = Date.now(), poll = null, before = S && S.comments ? S.comments.stored : null;
      var btn = box.querySelector('[data-upd="' + kind + '"]');
      try { if (window.hvPortal && window.hvPortal.cooking) cook = window.hvPortal.cooking({ list: true, dark: false, title: K.title, steps: K.steps }); } catch (e) { cook = null; }
      if (cook) m.card.appendChild(cook); else m.card.innerHTML = '<p class="db-fetch__plain">' + K.plain + "</p>";
      // A real progress bar: it fills as the update runs and reaches 100% when the numbers are in.
      if (cook && cook.stop) cook.stop();                // the steps are lit from the percentage, below
      var prog = document.createElement("div"); prog.className = "db-prog";
      prog.innerHTML = '<div class="db-pbar"><i></i></div><b class="db-pct">0%</b>'; m.card.appendChild(prog);
      var fill = prog.querySelector("i"), pctEl = prog.querySelector("b"), P = 0, finishing = false;
      function show(p) {
        P = Math.max(P, Math.min(100, p)); fill.style.width = P + "%"; pctEl.textContent = Math.floor(P) + "%";
        var items = cook ? cook.querySelectorAll(".ai-sl__st") : [], cuts = [0, 22, 50, 78];
        [].forEach.call(items, function (li, i) { li.className = "ai-sl__st" + (P >= (cuts[i + 1] == null ? 101 : cuts[i + 1]) ? " is-done" : P >= cuts[i] ? " is-now" : ""); });
      }
      var tick = setInterval(function () { if (!finishing) show(95 * (1 - Math.exp(-(Date.now() - t0) / K.tau))); }, 120);
      show(0);
      var msg = document.createElement("p"); msg.className = "db-fetch__msg"; msg.setAttribute("role", "status"); m.card.appendChild(msg);
      var bal = document.createElement("p"); bal.className = "db-fetch__bal"; bal.textContent = leftText(); m.card.appendChild(bal);
      btn.classList.add("is-busy");
      function leave(reload) {
        clearInterval(tick); if (cook && cook.stop) cook.stop(); m.close(); btn.classList.remove("is-busy");
        if (reload) { if (kind === "comments") CMB.items = null; changed(); load(); } else state().catch(function () {});
      }
      function fail(text) {
        if (poll) clearInterval(poll); clearInterval(tick);
        prog.hidden = true; bal.hidden = true; if (cook) cook.hidden = true;        // nothing is running: say why, plainly
        msg.className = "db-fetch__msg db-fetch__msg--big"; msg.textContent = text; setTimeout(function () { leave(false); }, 2800);
      }
      var got = null;
      function done(s) {
        if (poll) clearInterval(poll); finishing = true;
        if (kind === "comments" && s && s.comments && before != null) got = Math.max(0, s.comments.stored - before);
        var from = P, t1 = Date.now();
        (function ramp() {
          var k = Math.min(1, (Date.now() - t1) / 900); show(from + (100 - from) * k);
          if (k < 1) return requestAnimationFrame(ramp);
          clearInterval(tick);
          setTimeout(function () {
            m.card.innerHTML = '<div class="db-ok"><svg class="db-ok__tick" viewBox="0 0 52 52" aria-hidden="true"><circle class="db-ok__c" cx="26" cy="26" r="23"/><path class="db-ok__p" d="M15 27.5l8 8 14.5-17"/></svg>'
              + '<h3 role="status">' + K.ok + "</h3>" + (got != null ? "<p>" + (got > 0 ? full(got) + " new comment" + (got === 1 ? "" : "s") : "No new comments since the last read") + "</p>" : "")
              + (leftText() ? "<p>" + esc(leftText()) + "</p>" : "") + "</div>";
            setTimeout(function () { leave(true); }, 2400);
          }, 500);
        })();
      }
      postJSON("/api/campaign/refresh", { t: TOKEN, what: kind }).then(function (r) {
        if (!r.b || !r.b.ok) return fail((r.b && r.b.message) || "Could not start the update. Try again.");
        paint(r.b); bal.textContent = leftText();
        poll = setInterval(function () {
          get("/api/campaign/refresh?t=" + encodeURIComponent(TOKEN)).then(function (s) {
            paint(s); bal.textContent = leftText();
            if (!K.busy(s)) done(s); else if (Date.now() - t0 > K.max * 60 * 1000) fail(K.late);
          }).catch(function () {});
        }, kind === "comments" ? 5000 : 3000);
      }).catch(function () { fail("Could not reach the server. Try again."); });
    }
    // All free updates used: ask the team for more.
    function request() {
      var m = modal("db-fetch__card--light");
      m.card.innerHTML = '<h3 class="db-req__h">You have used all your free updates</h3><p class="db-req__p">Ask for more and your account manager will add them to this campaign.</p>'
        + '<textarea class="db-req__t" id="db-req-note" rows="3" maxlength="400" placeholder="How many extra updates do you need? (optional)"></textarea>'
        + '<div class="db-req__row"><button type="button" class="db-upd__btn" id="db-req-send">Send request</button><button type="button" class="db-req__x" id="db-req-x">Cancel</button></div><p class="db-fetch__msg db-req__msg" id="db-req-msg" role="status"></p>';
      var send = m.card.querySelector("#db-req-send"), msg = m.card.querySelector("#db-req-msg");
      m.card.querySelector("#db-req-x").addEventListener("click", m.close);
      send.addEventListener("click", function () {
        send.classList.add("is-busy"); msg.textContent = "";
        postJSON("/api/campaign/refresh-request", { t: TOKEN, note: m.card.querySelector("#db-req-note").value }).then(function (r) {
          send.classList.remove("is-busy");
          if (!r.b || !r.b.ok) { msg.textContent = r.s === 429 ? "You already asked today. We will be in touch." : "Could not send. Try again."; return; }
          msg.textContent = r.b.message; send.hidden = true; label.textContent = "Request sent";
          setTimeout(m.close, 2600);
        }).catch(function () { send.classList.remove("is-busy"); msg.textContent = "Could not reach the server. Try again."; });
      });
    }
  }

  /* -------------------------------------------------------------- share */
  // The team (and invitees with the edit role) get a Share button: invite emails with View or View & edit, or a view-only link.
  function setupShare() {
    ["db-share", "db-share-pop"].forEach(function (id) { var o = document.getElementById(id); if (o) o.remove(); });
    var S = R.share; if (!S || !S.can) return;
    var pdf = $("db-pdf"), btn = document.createElement("button");
    btn.type = "button"; btn.className = "db-btn"; btn.id = "db-share"; btn.setAttribute("aria-expanded", "false"); btn.setAttribute("aria-haspopup", "dialog");
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16" style="vertical-align:-3px;margin-right:6px"><circle cx="18" cy="5" r="2.6"/><circle cx="6" cy="12" r="2.6"/><circle cx="18" cy="19" r="2.6"/><path d="M8.3 10.8l7.4-4.3M8.3 13.2l7.4 4.3"/></svg>Share';
    pdf.parentNode.insertBefore(btn, pdf);
    var pop = document.createElement("div"); pop.className = "db-share"; pop.id = "db-share-pop"; pop.setAttribute("role", "dialog"); pop.setAttribute("aria-label", "Share this dashboard"); pop.hidden = true;
    document.body.appendChild(pop);
    function say(t) { var m = document.getElementById("db-share-msg"); if (m) m.textContent = t || ""; }
    var note = "";
    function post(action, extra) {
      var body = { t: TOKEN, action: action }; for (var k in (extra || {})) body[k] = extra[k];
      return fetch(API + "/api/campaign/share", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
        .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, b: b }; }); })
        .then(function (x) {
          if (!x.b || !x.b.ok) { say((x.b && x.b.message) || "That did not work. Try again."); return; }
          S.enabled = !!x.b.enabled; S.url = x.b.url; if (x.b.people) S.people = x.b.people; note = x.b.message || ""; paint();
        })
        .catch(function () { say("That did not work. Try again."); });
    }
    function roleSel(cls, v, em) {
      return '<select class="' + cls + '" data-e="' + esc(em || "") + '" aria-label="Access level"><option value="view"' + (v === "view" ? " selected" : "") + '>View only</option><option value="edit"' + (v === "edit" ? " selected" : "") + '>View &amp; edit</option></select>';
    }
    function paint() {
      var ppl = S.people || [];
      pop.innerHTML = "<h3>Share this dashboard</h3>"
        + '<p>Invite people by email. They sign in (or sign up) with that email and see this campaign and nothing else.</p>'
        + '<div class="db-share__inv"><input id="db-inv-email" type="email" placeholder="name@company.com" autocomplete="off" aria-label="Email to invite">' + roleSel("db-inv-role", "view") + '<button class="db-btn db-btn--lime" id="db-inv-go" type="button">Invite</button></div>'
        + '<p class="db-share__hint"><b>View only</b>: read the dashboard and report. <b>View &amp; edit</b>: also unlimited Update now and can invite others.</p>'
        + (ppl.length ? '<ul class="db-share__ppl">' + ppl.map(function (p) {
            return '<li><span class="db-share__em" title="' + esc(p.email) + '">' + esc(p.email) + '<small>' + (p.state === "joined" ? "Joined" : "Invited") + '</small></span>' + roleSel("db-ppl-role", p.role, p.email)
              + '<button class="db-share__x" type="button" data-e="' + esc(p.email) + '" aria-label="Remove ' + esc(p.email) + '" title="Remove">&times;</button></li>';
          }).join("") + "</ul>" : "")
        + '<div class="db-share__sep"></div><h4>Or share a link</h4><p>Anyone with the link can open it, view only, after they sign in or sign up.</p>'
        + (S.enabled ? '<div class="db-share__row"><input id="db-share-url" readonly aria-label="Share link" value="' + esc(S.url) + '"><button class="db-btn db-btn--lime" id="db-share-copy" type="button">Copy link</button></div>'
            + '<button class="db-share__off" id="db-share-off" type="button">Turn off the link</button>'
          : '<button class="db-btn" id="db-share-on" type="button">Create share link</button>')
        + '<p class="db-share__msg" id="db-share-msg" role="status">' + esc(note) + '</p>';
      note = "";
      var on = document.getElementById("db-share-on"), off = document.getElementById("db-share-off"), cp = document.getElementById("db-share-copy");
      var em = document.getElementById("db-inv-email"), go = document.getElementById("db-inv-go");
      function invite() { var v = (em.value || "").trim(); if (!v) { say("Type an email first."); em.focus(); return; } post("invite", { email: v, role: pop.querySelector(".db-inv-role").value }); }
      if (go) go.addEventListener("click", invite);
      if (em) em.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); invite(); } });
      Array.prototype.forEach.call(pop.querySelectorAll(".db-ppl-role"), function (sel) { sel.addEventListener("change", function () { post("invite", { email: sel.getAttribute("data-e"), role: sel.value }); }); });
      Array.prototype.forEach.call(pop.querySelectorAll(".db-share__x"), function (x) { x.addEventListener("click", function () { post("remove", { email: x.getAttribute("data-e") }); }); });
      if (on) on.addEventListener("click", function () { post("on"); });
      if (off) off.addEventListener("click", function () { post("off"); });
      if (cp) cp.addEventListener("click", function () {
        var inp = document.getElementById("db-share-url");
        function done() { cp.textContent = "Copied"; say("Link copied."); setTimeout(function () { cp.textContent = "Copy link"; }, 1800); }
        if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(S.url).then(done, function () { inp.select(); try { document.execCommand("copy"); done(); } catch (e) { say("Press Ctrl+C to copy."); } });
        else { inp.select(); try { document.execCommand("copy"); done(); } catch (e) { say("Press Ctrl+C to copy."); } }
      });
      if (!pop.hidden) place();
    }
    function place() { var r = btn.getBoundingClientRect(); pop.style.top = Math.round(r.bottom + 8) + "px"; pop.style.left = Math.max(12, Math.min(window.innerWidth - pop.offsetWidth - 12, r.right - pop.offsetWidth)) + "px"; }
    function toggle(open) { pop.hidden = !open; btn.setAttribute("aria-expanded", open ? "true" : "false"); if (open) { paint(); place(); } }
    btn.addEventListener("click", function (e) { e.stopPropagation(); toggle(pop.hidden); });
    document.addEventListener("click", function (e) { if (!pop.hidden && !pop.contains(e.target) && e.target !== btn) toggle(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !pop.hidden) { toggle(false); btn.focus(); } });
    window.addEventListener("resize", function () { if (!pop.hidden) place(); });
  }

  /* ------------------------------------------------------------ filters */
  function setupFilters() {
    var plats = {}; R.posts.forEach(function (p) { plats[p.platform] = 1; });
    // a goal platform nobody has posted on yet still gets its chip, so its targets can be read at zero
    ((R.goals || {}).platforms || []).forEach(function (p) { plats[p] = 1; });
    var list = Object.keys(plats).sort();
    $("db-platforms").innerHTML = ['<button type="button" data-p="" aria-pressed="true">All</button>'].concat(list.map(function (p) {
      return '<button type="button" data-p="' + esc(p) + '" aria-pressed="false" aria-label="' + esc(p) + '" title="' + esc(p) + '">' + (ICONS[p] || "") + '<span class="db-seg__t">' + esc(p) + "</span></button>";
    })).join("");
    $("db-platforms").addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      F.platform = b.getAttribute("data-p");
      [].forEach.call(this.children, function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
      renderAll();
      if (curArea === "kpi" && !$("db-panel").hidden) openPanel("kpi");
    });
    $("db-range").addEventListener("change", function () {
      F.range = this.value; $("db-custom").hidden = F.range !== "custom"; renderAll();
    });
    ["db-from", "db-to"].forEach(function (id) { $(id).addEventListener("change", function () { F.from = $("db-from").value; F.to = $("db-to").value; renderAll(); }); });
    $("db-creators").innerHTML = '<button type="button" class="db-pick__all" id="db-creators-all">All creators</button>' + R.creators.map(function (c) {
      return '<label><input type="checkbox" value="' + esc(c.code) + '">' + ava(c.photo) + esc(c.name) + "</label>";
    }).join("");
    creatorBtn();
    $("db-creators-all").addEventListener("click", function () {
      [].forEach.call($("db-creators").querySelectorAll("input:checked"), function (i) { i.checked = false; });
      $("db-creators").dispatchEvent(new Event("change"));
    });
    $("db-creators-btn").addEventListener("click", function () {
      var m = $("db-creators"), open = m.hidden; m.hidden = !open; this.setAttribute("aria-expanded", open ? "true" : "false");
    });
    $("db-creators").addEventListener("change", function () {
      F.creators = [].map.call(this.querySelectorAll("input:checked"), function (i) { return i.value; });
      creatorBtn();
      renderAll();
    });
    document.addEventListener("click", function (e) { if (!e.target.closest(".db-pick")) { $("db-creators").hidden = true; $("db-creators-btn").setAttribute("aria-expanded", "false"); } });
  }
  function filtered() { return !!(F.platform || F.range !== "all" || F.creators.length); }
  // The creators filter shows who it covers (owner, 2026-10-19): overlapping photos (the chosen ones, or everyone),
  // then "All 11", the one name, or "3 selected".
  function creatorBtn() {
    var sel = F.creators, all = R.creators || [], list = sel.length ? all.filter(function (c) { return sel.indexOf(c.code) >= 0; }) : all;
    var stack = list.slice(0, 4).map(function (c) { return '<span class="db-stack__i">' + ava(c.photo) + "</span>"; }).join("")
      + (list.length > 4 ? '<span class="db-stack__i db-stack__more">+' + (list.length - 4) + "</span>" : "");
    var txt = !sel.length ? "All " + all.length : sel.length === 1 ? list[0].name : sel.length + " selected";
    var b = $("db-creators-btn");
    b.innerHTML = '<span class="db-stack" aria-hidden="true">' + stack + '</span><span class="db-pick__t">' + esc(txt) + "</span>"
      + '<svg class="db-pick__chev" viewBox="0 0 12 12" aria-hidden="true"><path d="M3 4.5 6 7.5 9 4.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    b.setAttribute("aria-label", "Creators filter: " + (sel.length ? txt : "all " + all.length + " creators"));
    b.title = sel.length ? list.map(function (c) { return c.name; }).join(", ") : "Showing all " + all.length + " creators. Pick one or more to filter the dashboard.";
    b.classList.toggle("is-on", !!sel.length);
    var a = $("db-creators-all"); if (a) a.classList.toggle("is-on", !sel.length);
  }
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
    var t = { posts: pieceCount(list), views: 0, reach: 0, engagement: 0, likes: 0, comments: 0, saves: 0, shares: 0, er: null };
    var ers = [];
    t.views_hidden = list.length > 0 && list.every(function (p) { return p.video && p.views_hidden; });
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
  // The "i" mark: hover, keyboard focus or a tap shows the note; Esc or a tap elsewhere closes it.
  function info(tip, what) { return '<button type="button" class="db-info" data-tip="' + esc(tip) + '" aria-label="' + esc("About " + (what || "this")) + '">i</button>'; }
  function head(icon, title, tip, area) {
    return '<header class="db-card__head"><h2>' + icon + esc(title) + "</h2>" + (tip ? info(tip, title) : "")
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
      var x = by[d] = by[d] || { views: 0, eng: 0, reach: 0, posts: 0 }; x.views += p.views || 0; x.eng += p.engagement || 0; x.reach += p.reach || 0; if (p.piece_size <= 1 || p.id === p.pk) x.posts++; });
    var days = Object.keys(by).sort(), cv = 0, ce = 0, cr = 0, cp = 0;
    return days.map(function (d) { cv += by[d].views; ce += by[d].eng; cr += by[d].reach; cp += by[d].posts; return { d: d, views: cv, eng: ce, reach: cr, posts: cp }; });
  }

  // Every curve starts from zero on the campaign's first day, so the day before the first video reads 0.
  function fromStart(pts) {
    var st = R.campaign && R.campaign.starts_at; if (!st || !pts.length) return pts;
    var d = new Date(st * 1000).toISOString().slice(0, 10);
    return d < pts[0].d ? [{ d: d, views: 0, eng: 0, reach: 0, posts: 0 }].concat(pts) : pts;
  }
  function renderAll() {
    var list = posts(), t = sums(list), s = fromStart(series(list)), cl = clicksFor();
    // Whole-campaign totals set by HelloVoice by hand replace the measured
    // ones in the unfiltered view and are always marked as estimates.
    var adj = (!filtered() && R.total && R.total.adjusted) || [];
    function isAdj(k) { return adj.indexOf(k) >= 0; }
    function est(k) { return isAdj(k) ? '<small class="db-est" title="Estimated by HelloVoice: the platform has not shown the exact number yet.">est.</small>' : ""; }
    if (isAdj("views")) t.views = R.total.views;
    if (isAdj("reach")) t.reach = R.total.reach;
    if (isAdj("engagement")) t.engagement = R.total.engagement;
    // Unfiltered, the server's rate, as on the report: the one the ER goal measures, else the campaign's video ER / ER.
    var erItem = ((R.progress || {}).items || []).filter(function (i) { return i.key === "er"; })[0];
    if (!filtered()) t.er = erItem ? erItem.actual : R.total.video_er != null ? R.total.video_er : R.total.er;
    if (isAdj("clicks") && cl) cl = Object.assign({}, cl, { clicks: R.total.clicks });
    var whole = !filtered() ? R.total : null;
    renderObjective();
    // KPI cards
    // A platform filter on its own keeps the goal pills, measured on that platform's own targets;
    // a platform with no goal says so instead of leaving the foot of the card empty.
    var psc = !F.creators.length && F.range === "all" ? scope() : { mode: "none" }, pm = psc.mode === "plat", bonus = psc.mode === "bonus";
    var g = {}; ((pm ? psc.bp.progress : R.progress).items || []).forEach(function (i) { g[i.key] = i; });
    function goal(k) {
      if (bonus && k !== "clicks") return '<span class="db-na__why">No goal on ' + esc(psc.pl) + " (bonus)</span>";
      return (!filtered() || pm) && g[k] ? sig(g[k].grade, "Goal " + (k === "er" ? pct(g[k].goal, 1) : num(g[k].goal))) : "";
    }
    var cards = [
      ["Posts live", full(t.posts) + (pm && g.posts ? "<small>/" + g.posts.goal + "</small>" : !filtered() && R.total.planned ? "<small>/" + R.total.planned + "</small>" : ""), goal("posts"), spark(s.map(function (x) { return x.posts; }), COL[4]), IC.posts, "kpi"],
      ["Views", t.views_hidden ? '<span class="db-na" title="This platform does not show view counts">Not shown</span>' : num(t.views) + est("views"), goal("views"), spark(s.map(function (x) { return x.views; }), COL[0]), IC.views, "trend"],
      ["Reach", t.views_hidden ? '<span class="db-na" title="Reach is worked out from views, which this platform does not show">Not shown</span>' : num(t.reach) + (isAdj("reach") ? est("reach") : reachEst() ? '<small class="db-est" title="Instagram does not show reach on reels publicly. Placeholder at ' + Math.round(((R.reach_basis && R.reach_basis.per_view) || 0.9) * 100) + '% of views (a small margin below) until the creators\' insights arrive.">est.</small>' : ""), goal("reach"), spark(s.map(function (x) { return x.reach; }), COL[3]), IC.reach, "trend"],
      ["Engagement", num(t.engagement) + est("engagement"), goal("engagement"), spark(s.map(function (x) { return x.eng; }), COL[1]), IC.engagement, "trend"],
      ["Avg eng. rate", pct(t.er) + est("er"), pm || bonus ? goal("er") : !filtered() ? (g.er ? goal("er") : sig(R.total.er_grade)) : "", "", IC.er, "kpi"],
      ["Link clicks", cl ? num(cl.clicks) + est("clicks") : '<span class="db-na">Not tracked</span>', cl && !filtered() ? (g.clicks ? goal("clicks") : sig(R.total.ctr_grade)) : '<span class="db-na__why">This campaign does not contain affiliate links</span>', "", IC.clicks, "clicks"]
    ];
    // Sections the admin switched off are left out, not shown empty.
    var V = R.visibility || {};
    // The clicks slot stays where it is even for a campaign with no tracking
    // links — it then says so. Only a section the admin switched off goes.
    var noClicks = V.clicks === false;
    cards = cards.filter(function (k) { return !(k[0] === "Reach" && V.reach === false) && !(k[0] === "Link clicks" && noClicks); });
    $("w-kpis").style.setProperty("--kpis", cards.length);
    $("db-grid").classList.toggle("no-clicks", noClicks);
    $("db-grid").classList.toggle("no-links", !cl);   // phones hide the empty clicks tile + card (mobile audit 2026-10-19)
    $("w-kpis").innerHTML = cards.map(function (k) {
      return '<button type="button" class="db-kpi" data-area="' + k[5] + '"><span class="db-kpi__label">' + k[4] + esc(k[0]) + '</span><span class="db-kpi__value">' + k[1]
        + '</span><span class="db-kpi__foot">' + (k[2] || "<span></span>") + k[3] + "</span></button>";
    }).join("");
    renderTrend(s);
    renderTop(list);
    renderStage();
    renderMix(list);
    renderGeo();
    renderDid(list);   // What people did ring (2026-10-23)
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
    box.innerHTML = '<span class="db-obj__label">Objective · <b>' + esc(o.label) + '</b>'
      + (R.targets_auto ? '<span class="db-obj__auto" title="No targets were agreed for this campaign yet, so these come from what its creators usually deliver for the posts booked.">Suggested targets</span>' : "")
      + '</span><div class="db-obj__track" role="img" aria-label="' + Math.round(done) + '% of all targets achieved">'
      + '<i class="db-obj__fill ' + gr + '" style="width:' + done.toFixed(1) + '%"></i><i class="db-obj__due" style="left:' + due.toFixed(1) + '%" title="Where it should be today"></i></div>'
      + '<span class="db-obj__pct" title="All targets together, each counted up to its goal">' + Math.round(done) + "%</span>" + sig(gr, "Expected by today: " + Math.round(due) + "%")
      + '<span class="db-obj__parts">' + items.map(function (i) { var met = i.actual >= i.goal; return '<span class="' + (met ? "met" : "short") + '" title="' + (met ? "Met" : "Not met yet") + '">' + KEYN[i.key] + " <b>" + Math.round(i.pct) + "%</b></span>"; }).join("") + "</span>"
      + goals;
  }

  // The width the panel's content really has, so a chart drawn for it is not stretched.
  function panelW() {
    if (PRINT_W) return PRINT_W;     // the PDF draws every chart at the A4 column width (2026-10-23)
    var b = $("db-panel-body"), cs = getComputedStyle(b), w = b.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    return Math.max(280, Math.round(w) || 600);
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
    var pts = fromStart(useHist ? R.history.map(function (d) { return { d: d.d, views: d.views, eng: d.engagement != null ? d.engagement : d.likes + d.comments }; }) : s);
    $("w-trend").innerHTML = head(IC.trend, "Views & engagement", "Total views (green) and engagement — likes and comments (orange) — growing over the campaign. Each line has its own scale.", "trend")
      + '<div class="db-legend"><span><i style="background:' + COL[0] + '"></i>Views</span><span><i style="background:' + COL[1] + '"></i>Engagement</span></div>'
      + '<div class="db-card__body">' + areaChart(pts, "views", "eng", 640, 200) + "</div>";
  }

  var MEDAL = { 1: "#d6a52b", 2: "#9ea6ae", 3: "#b06f3a" };
  function medalBody(n) { return '<path d="M10 0h8l4 14-6 4z" fill="#ff691e"/><path d="M30 0h-8l-4 14 6 4z" fill="#ee1515"/><circle cx="20" cy="32" r="15" fill="' + MEDAL[n] + '"/><text x="20" y="38" text-anchor="middle" font-family="Bebasneue, Arial" font-size="17" fill="#121212">' + n + "</text>"; }
  function medal(n) { return '<svg viewBox="0 0 40 50" role="img" aria-label="Rank ' + n + '">' + medalBody(n) + "</svg>"; }
  // Creator names open their full analysis (the same page as the roster's).
  function who(c) { return '<a class="db-name" href="../../creator/#c=' + encodeURIComponent(c.code) + '" title="Open ' + esc(c.name) + '\'s full analysis">' + esc(c.name) + "</a>"; }
  // The same 0-100 score the campaign uses, worked out on the posts in the current view: each part is a
  // creator's result as a share of the best creator's in this view (clicks are per creator link, not per platform).
  var viewScore = {};
  // A score as a % of the best creator: one decimal under 1 so a small share never reads as 0 (owner, 2026-10-19).
  function scoreTxt(v, html) {
    if (v == null || isNaN(v)) return "—";
    var n = v > 0 && v < 1 ? v.toFixed(1) : String(Math.round(v));
    return n + (html ? '<small class="db-pct">%</small>' : "%");
  }
  function ranked(list) {
    viewScore = {};
    if (!filtered()) return R.creators.filter(function (c) { return c.rank; }).map(function (c) { return { c: c, v: c.score, label: scoreTxt(c.score, true) }; });
    var w = weights(), by = {}; list.forEach(function (p) {
      var x = by[p.code] = by[p.code] || { n: 0, eng: 0, vw: 0, er: [] }; x.n += seen(p); x.eng += p.engagement || 0;
      if (p.video_er != null) x.er.push(p.video_er);
    });
    var rows = R.creators.filter(function (c) { return by[c.code] && (by[c.code].n || by[c.code].eng); });
    function peak(f) { return Math.max.apply(null, rows.map(f).concat([0])) || 1; }
    function q(c) { var e = by[c.code].er; return e.length ? e.reduce(function (a, b) { return a + b; }, 0) / e.length : 0; }
    var pn = peak(function (c) { return by[c.code].n; }), pe = peak(function (c) { return by[c.code].eng; }), pq = peak(q), pc = peak(function (c) { return c.clicks || 0; });
    return rows.map(function (c) {
      var x = by[c.code], sc = 100 * ((w.exposure || 0) * x.n / pn + (w.engagement || 0) * x.eng / pe + (w.er || 0) * q(c) / pq + (w.clicks || 0) * (c.clicks || 0) / pc);
      viewScore[c.code] = sc;
      return { c: c, v: sc, label: scoreTxt(sc, true) };
    }).sort(function (a, b) { return b.v - a.v; });
  }
  function renderTop(list) {
    var rows = ranked(list).slice(0, 5);
    $("w-top").innerHTML = head(IC.top, "Creators leaderboard", (filtered() ? "Score out of 100, worked out on the posts in this view. " : "") + scoreTip(), "creators")
      + '<div class="db-card__body">' + (rows.length ? '<div class="db-top__how">' + scoreBar(true) + "</div>" : "") + (rows.map(function (r, i) {
                return '<div class="db-rank' + (i === 0 ? " is-1" : "") + '"><span class="db-rank__n">' + (i < 3 ? medal(i + 1) : i + 1) + "</span>" + ava(r.c.photo) + "<span><b>" + who(r.c) + "</b><small>" + r.c.delivered + (r.c.planned ? "/" + r.c.planned : "") + (r.c.delivered === 1 && !r.c.planned ? " video · " : " videos · ") + num(r.c.seen != null ? r.c.seen : r.c.views) + " views" + '</small></span><span class="db-rank__score" title="' + "Score out of 100" + '">' + r.label + "</span></div>";
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
    $("w-mix").innerHTML = head(IC.mix, "Content mix", "How many of each format was published, on every platform: photo posts, reels, stories, videos and shorts.", "mix")
      + '<div class="db-card__body">' + (parts.length ? '<div class="db-donut">' + donut(parts) + '<div class="db-key">' + parts.map(function (p, i) {
        return '<div><span class="db-sw" style="background:' + COL[i % COL.length] + '"></span>' + esc(KIND[p.k] || p.k) + "<b>" + p.n + "</b></div>"; }).join("") + "</div></div>"
        : '<p class="db-note">No posts in this view.</p>') + "</div>";
  }

  function bars(rows, keyHtml, colourOf) {
    var peak = Math.max.apply(null, rows.map(function (r) { return r.n; }).concat([1]));
    return rows.map(function (r, i) { return '<div class="db-bar"><span>' + keyHtml(r) + '</span><i style="--w:' + (r.n / peak * 100).toFixed(1) + "%;--c:" + (colourOf ? colourOf(i) : COL[i % 4]) + '"></i><b>' + r.label + "</b></div>"; }).join("");
  }
  // The creators' own profile audience, not who saw the campaign (owner, 2026-10-18): say so, and show
  // where the campaign's target market sits.
  function audNote(a) {
    var s = "Creators' profile audience, weighted by reach";
    if (a.basis === "partial") s += " · " + a.coverage.toFixed(0) + "% of reach analysed so far, the rest not yet analysed";
    return s;
  }
  function audTarget(a) {
    var t = a && a.target; if (!t) return "";
    return '<p class="db-note db-note--target"><b>Target market: ' + esc(countryName(t.code)) + "</b> · " + t.pct.toFixed(0) + "% of these creators' audience" + (t.rank ? " (#" + t.rank + ")" : "") + "</p>";
  }
  /* What people said (owner, 2026-10-19; v20 same day): viewers' comments, read by AI once a week (every 7 days from the first video, since 2026-10-23).
     It takes the audience-countries slot. Totals come per creator and platform, so the page's filters apply. */
  var CMI = ico('<path d="M4 5.5h16v10.5H9l-5 4z"/><path d="M8.5 9.5h7M8.5 12.5h4.5"/>');
  var CM_TIP = "What viewers wrote in the comments under the campaign videos, read by AI once a week, every 7 days from the first video. Commenters' names are never stored.";
  var CM_COL = { pos: "#14884a", neu: "#ff691e", neg: "#ee1515" };
  // One drawn icon per theme, picked from the words of the AI's label.
  var CM_TI = [
    [/avail|where|find|stock|pharmac|store|shop|country|egypt|kuwait|saudi/i, '<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0C18.5 15.4 12 21 12 21z"/><circle cx="12" cy="10" r="2.4"/>'],
    [/price|cost|pric|cheap|expens|money|purchas|buy|order/i, '<path d="M20.5 13.5l-7 7a1.8 1.8 0 0 1-2.5 0l-7.5-7.5V4h8.5l8.5 8.5a1.8 1.8 0 0 1 0 1z"/><circle cx="8" cy="8" r="1.4"/>'],
    [/dos|usage|use|how to|capsule|pill|tablet|supplement|vitamin|all-in-one/i, '<rect x="3.2" y="8.6" width="17.6" height="6.8" rx="3.4" transform="rotate(-35 12 12)"/><path d="M9.2 7.9l5.6 8.2"/>'],
    [/medic|safety|side|health|condition|disease|doctor|pregnan|risk/i, '<path d="M12 3l7.5 3v5.5c0 4.6-3.2 8.2-7.5 9.5-4.3-1.3-7.5-4.9-7.5-9.5V6z"/><path d="M12 9v6M9 12h6"/>'],
    [/humou?r|joke|banter|funny|laugh/i, '<circle cx="12" cy="12" r="8.5"/><path d="M8.5 14a4.2 4.2 0 0 0 7 0"/><path d="M9 9.6h.01M15 9.6h.01"/>'],
    [/prais|thank|love|appreciat|compliment|creator|support/i, '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>'],
    [/quality|effect|result|work|review|experience/i, '<path d="M12 3l2.6 5.6 6 .7-4.5 4.1 1.2 6-5.3-3-5.3 3 1.2-6L3.4 9.3l6-.7z"/>'],
    [/deliver|ship|amazon|online/i, '<path d="M3 7h11v9H3zM14 10h4l3 3v3h-7z"/><circle cx="7" cy="17.5" r="1.8"/><circle cx="17.5" cy="17.5" r="1.8"/>'],
    [/age|old|young|women|men|kid|child|baby|fertil/i, '<circle cx="12" cy="7.5" r="3.5"/><path d="M5 20.5a7 7 0 0 1 14 0"/>'],
    [/skin|hair|beauty|makeup|derm/i, '<path d="M12 3.5s6 6.4 6 10.5a6 6 0 0 1-12 0c0-4.1 6-10.5 6-10.5z"/>']
  ];
  function cmIcon(label) {
    var hit = CM_TI.filter(function (r) { return r[0].test(label || ""); })[0];
    return ico(hit ? hit[1] : '<path d="M4 5.5h16v10.5H9l-5 4z"/>');
  }
  // Sentiment faces, drawn in the mood's colour (smile / flat / frown), as listening tools show them.
  var CM_FACE = (function () { var f = function (m) { return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">'
      + '<circle cx="12" cy="12" r="9.2" fill="currentColor" fill-opacity=".12"/><circle cx="9" cy="10" r=".9" fill="currentColor"/><circle cx="15" cy="10" r=".9" fill="currentColor"/>' + m + "</svg>"; };
    return { pos: f('<path d="M8.3 13.6a4.2 4.2 0 0 0 7.4 0"/>'), neu: f('<path d="M8.8 14.8h6.4"/>'), neg: f('<path d="M8.3 16.4a4.2 4.2 0 0 1 7.4 0"/>') }; })();
  function cmPick() {
    var C = R.comments || {}, t = { n: 0, pos: 0, neu: 0, neg: 0, intent: 0, videos: 0, asks: {}, themes: {}, by: {}, plats: {}, tp: {}, days: {} };
    (C.buckets || []).forEach(function (b) {
      if ((F.platform && b.platform !== F.platform) || (F.creators.length && F.creators.indexOf(b.code) < 0)) return;
      ["n", "pos", "neu", "neg", "intent", "videos"].forEach(function (k) { t[k] += b[k] || 0; });
      Object.keys(b.asks || {}).forEach(function (q) { var x = t.asks[q] = t.asks[q] || { n: 0, en: b.asks[q].en }; x.n += b.asks[q].n; });
      Object.keys(b.themes || {}).forEach(function (q) { t.themes[q] = (t.themes[q] || 0) + b.themes[q];
        var tp = t.tp[q] = t.tp[q] || {}; tp[b.platform] = (tp[b.platform] || 0) + b.themes[q]; });
      Object.keys(b.days || {}).forEach(function (d) { t.days[d] = (t.days[d] || 0) + b.days[d]; });
      var w = t.by[b.code] = t.by[b.code] || { n: 0, pos: 0, neu: 0, neg: 0, intent: 0, plats: [], themes: {} };
      ["n", "pos", "neu", "neg", "intent"].forEach(function (k) { w[k] += b[k] || 0; });
      if (w.plats.indexOf(b.platform) < 0) w.plats.push(b.platform);
      Object.keys(b.themes || {}).forEach(function (q) { w.themes[q] = (w.themes[q] || 0) + b.themes[q]; });
      var pl = t.plats[b.platform] = t.plats[b.platform] || { n: 0, pos: 0, neu: 0, neg: 0, intent: 0 };
      ["n", "pos", "neu", "neg", "intent"].forEach(function (k) { pl[k] += b[k] || 0; });
    });
    t.small = t.n < ((R.comments || {}).min_sample || 30);
    return t;
  }
  function cmPct(x, n) { return n ? Math.round(x / n * 100) : 0; }
  function cmTop(o, k) { return Object.keys(o).sort(function (a, b) { return (k ? o[b][k] - o[a][k] : o[b] - o[a]); }); }
  function cmParts(t) { var p = cmPct(t.pos, t.n), z = cmPct(t.neg, t.n); return [["pos", p, "positive"], ["neu", Math.max(0, 100 - p - z), "neutral"], ["neg", z, "negative"]]; }
  // Mood ring: the three moods round a circle, the main mood (biggest share) written in the middle.
  function cmMain(t) { return cmParts(t).slice().sort(function (a, b) { return b[1] - a[1]; })[0]; }
  function cmRing(t, cls) {
    var off = 25, segs = cmParts(t).filter(function (s) { return s[1] > 0; }).map(function (s) {
      var c = '<circle cx="21" cy="21" r="15.915" fill="none" stroke="' + CM_COL[s[0]] + '" stroke-width="5.2" stroke-dasharray="' + s[1] + " " + (100 - s[1]) + '" stroke-dashoffset="' + off + '"/>';
      off -= s[1]; return c; }).join("");
    return '<div class="cm-ring' + (cls ? " " + cls : "") + '"><svg viewBox="0 0 42 42" role="img" aria-label="' + cmParts(t).map(function (s) { return s[1] + "% " + s[2]; }).join(", ") + '">'
      + '<circle cx="21" cy="21" r="15.915" fill="none" stroke="#efece6" stroke-width="5.2"/>' + segs + '</svg><span><b>' + cmMain(t)[1] + "%</b>" + cmMain(t)[2] + "</span></div>";
  }
  function cmMood(t, big) {
    return '<div class="cm-mood' + (big ? " cm-mood--big" : "") + '" role="img" aria-label="' + cmParts(t).map(function (s) { return s[1] + "% " + s[2]; }).join(", ") + '">'
      + cmParts(t).map(function (s) { return '<i class="' + s[0] + '" style="width:' + s[1] + '%">' + (big && s[1] >= 9 ? s[1] + "%" : "") + "</i>"; }).join("") + "</div>";
  }
  function cmKey(t, short) {
    var v = function (x) { return t.small ? x : cmPct(x, t.n) + "%"; };
    return '<div class="cm-key">' + [["pos", t.pos, short ? "pos." : "positive"], ["neu", t.neu, "neutral"], ["neg", t.neg, short ? "neg." : "negative"]].filter(function (s) { return s[1] || s[0] !== "neg"; })
      .map(function (s) { return '<span class="has-face" style="--c:' + CM_COL[s[0]] + '">' + '<i class="cm-face">' + CM_FACE[s[0]] + '</i><b>' + v(s[1]) + "</b> " + s[2] + "</span>"; }).join("") + "</div>";
  }
  function cmVerdict(t) {
    if (t.small) return ["none", "Too few to judge"];
    var p = t.pos / t.n, z = t.neg / t.n;
    return z >= 0.3 ? ["low", "Mixed to negative"] : p >= 0.6 && z < 0.15 ? ["good", "Mostly positive"] : z < 0.1 && t.intent / t.n >= 0.3 ? ["good", "Ready to buy"] : ["moderate", "Mixed"];
  }
  function cmDay(t) { return t ? day(t) : "—"; }
  function cmWait(C) {
    if (C.status === "none" || !C.first_post) return '<div class="cm-wait"><p>No videos are live yet. Once creators post, the comments under them are read here.</p></div>';
    // Read once a week (owner, 2026-10-23): every 7 days from the first video, all videos together.
    var now = Date.now() / 1000, fp = C.first_post, wk = 7 * 86400, r1 = fp + wk, nx = C.next_read || C.next_week || r1;
    return '<div class="cm-wait"><p>Comments are read once a week, every 7 days from the first video. The ' + (now >= r1 ? "next" : "first") + " reading lands on <b>" + cmDay(nx) + "</b>.</p>"
      + '<div class="cm-steps"><div class="on"><b>First video</b>' + cmDay(fp) + '</div><div class="' + (now >= r1 ? "on" : "next") + '"><b>Week 1 read</b>' + cmDay(r1)
      + '</div><div class="' + (now >= r1 ? "next" : "") + '"><b>Then weekly</b>' + (now >= r1 ? cmDay(nx) : cmDay(r1 + wk)) + "</div></div></div>";
  }
  function renderGeo() {
    var C = R.comments, t = cmPick(), body;
    if (!C || !t.n) body = cmWait(C || { status: "none" });
    else {
      body = '<div class="cm-hero">' + cmRing(t, "cm-ring--card") + '<div class="cm-legend">'
        + cmParts(t).map(function (s) { var n = t[s[0]]; return '<div class="cm-legend__r" style="--c:' + CM_COL[s[0]] + '">' + '<i class="cm-face">' + CM_FACE[s[0]] + '</i><b>' + (t.small ? n : s[1] + "%") + "</b><span>" + s[2] + "</span><small>" + full(n) + "</small></div>"; }).join("")
        + '<p class="cm-legend__n">' + full(t.n) + " comments · " + t.videos + " video" + (t.videos === 1 ? "" : "s") + "</p></div></div>";
    }
    $("w-geo").innerHTML = head(CMI, "What people say", CM_TIP, C && t.n ? "geo" : null) + '<div class="db-card__body cm">' + body + "</div>";
  }
  // Share of all comments by platform: one donut in the platforms' own colours, the leader in the middle.
  function cmShare(plats, t) {
    var off = 25, segs = plats.map(function (k) { var s = t.n ? t.plats[k].n / t.n * 100 : 0;
      var c = '<circle cx="21" cy="21" r="15.915" fill="none" stroke="' + (PCOL[k] || "#121212") + '" stroke-width="6" stroke-dasharray="' + s.toFixed(2) + " " + (100 - s).toFixed(2) + '" stroke-dashoffset="' + off.toFixed(2) + '"/>';
      off -= s; return c; }).join("");
    var top = plats[0];
    return '<div class="cmp-share"><div class="cm-ring cm-ring--share"><svg viewBox="0 0 42 42" role="img" aria-label="' + plats.map(function (k) { return k + " " + cmPct(t.plats[k].n, t.n) + "%"; }).join(", ") + '">'
      + '<circle cx="21" cy="21" r="15.915" fill="none" stroke="#efece6" stroke-width="6"/>' + segs + '</svg><span><b style="color:' + (PCOL[top] || "#121212") + '">' + cmPct(t.plats[top].n, t.n) + "%</b>from " + esc(top) + "</span></div>"
      + '<ul class="cmp-share__k">' + plats.map(function (k) { return '<li style="--pc:' + (PCOL[k] || "#121212") + '">' + (ICONS[k] || "") + "<span>" + esc(k) + "</span><b>" + cmPct(t.plats[k].n, t.n) + "%</b><small>" + full(t.plats[k].n) + "</small></li>"; }).join("") + "</ul></div>";
  }
  // Squarified treemap in a 160 x 100 box: [x, y, w, h] per value, biggest first.
  function cmSquarify(vals, x, y, w, h) {
    var out = [], tot = vals.reduce(function (a, b) { return a + b; }, 0); if (!tot) return out;
    var area = vals.map(function (v) { return v / tot * w * h; }), i = 0;
    var sum = function (r) { return r.reduce(function (a, b) { return a + b; }, 0); };
    while (i < area.length) {
      var side = Math.min(w, h), row = [area[i]], j = i + 1;
      var worst = function (r) { var s = sum(r); return Math.max(side * side * Math.max.apply(null, r) / (s * s), s * s / (side * side * Math.min.apply(null, r))); };
      while (j < area.length && worst(row.concat(area[j])) <= worst(row)) { row.push(area[j]); j++; }
      var s = sum(row);
      if (w >= h) { var cw = s / h, cy = y; row.forEach(function (a) { out.push([x, cy, cw, a / cw]); cy += a / cw; }); x += cw; w -= cw; }
      else { var ch = s / w, cx = x; row.forEach(function (a) { out.push([cx, y, a / ch, ch]); cx += a / ch; }); y += ch; h -= ch; }
      i = j;
    }
    return out;
  }
  // A smooth curve through the points (Catmull-Rom as cubic Beziers).
  function cmCurve(pts) {
    if (pts.length < 2) return "";
    var d = "M" + pts[0][0].toFixed(1) + " " + pts[0][1].toFixed(1);
    for (var i = 0; i < pts.length - 1; i++) {
      var p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
      d += " C" + (p1[0] + (p2[0] - p0[0]) / 6).toFixed(1) + " " + (p1[1] + (p2[1] - p0[1]) / 6).toFixed(1) + " " + (p2[0] - (p3[0] - p1[0]) / 6).toFixed(1) + " "
        + (p2[1] - (p3[1] - p1[1]) / 6).toFixed(1) + " " + p2[0].toFixed(1) + " " + p2[1].toFixed(1);
    }
    return d;
  }
  // Good / middle / bad, for a number worth judging: share asking to buy, share positive.
  function cmTone(k, r) {
    if (k === "buy") return r >= 0.4 ? "is-good" : r >= 0.15 ? "is-mid" : "is-bad";
    return r >= 0.6 ? "is-good" : r >= 0.3 ? "is-mid" : "is-bad";
  }
  /* The comment browser (owner, 2026-10-19; v15): every comment in its own language, grouped by doctor then video,
     filtered by doctor, video, mood, platform (icons), topic, buying questions and search, and exported as CSV. */
  var CMB = { closed: {}, items: null, busy: false, waits: [], f: { doc: "", vid: "", mood: "", plat: "", platPrev: "", theme: "", buy: false, q: "" }, open: {} };
  var CM_MOOD = { p: "pos", n: "neu", x: "neg" }, CM_MOOD_W = { p: "Positive", n: "Neutral", x: "Negative" };
  var CM_HEART = ico('<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>');
  var CM_CHEV = '<i class="cmp-chev" aria-hidden="true"></i>';
  // Every section of the panel is a drop-down: its heading is the toggle; "Collapse all / Expand all" sits above the first.
  function cmSections(html) {
    var parts = html.split("<h3>"), out = parts[0] + '<div class="cmp-secbar"><button type="button" onclick="document.querySelectorAll(\'.cmp-sec\').forEach(function(d){d.open=false})">Collapse all</button>'
      + '<button type="button" onclick="document.querySelectorAll(\'.cmp-sec\').forEach(function(d){d.open=true})">Expand all</button></div>';
    for (var i = 1; i < parts.length; i++) { var j = parts[i].indexOf("</h3>");
      out += '<details class="cmp-sec" open><summary><span>' + parts[i].slice(0, j) + "</span>" + CM_CHEV + '</summary><div class="cmp-sec__b">' + parts[i].slice(j + 5) + "</div></details>"; }
    return out;
  }
  var CM_LOCK = ico('<rect x="5" y="11" width="14" height="9.5" rx="2"/><path d="M8.5 11V8a3.5 3.5 0 0 1 7 0v3"/>');
  var CM_DL = ico('<path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 19.5h14"/>');
  function cmLoad(cb) {
    if (CMB.items) return cb();
    CMB.waits.push(cb); if (CMB.busy) return; CMB.busy = true;
    get("/api/campaign/comments?t=" + encodeURIComponent(TOKEN) + (shareTok() ? "&share=" + encodeURIComponent(shareTok()) : ""))
      .then(function (b) { CMB.items = b.items || []; }).catch(function () { CMB.items = []; })
      .then(function () { CMB.busy = false; var w = CMB.waits; CMB.waits = []; w.forEach(function (f) { f(); }); });
  }
  function cmInPage(it) { return (!F.platform || it[2] === F.platform) && (!F.creators.length || F.creators.indexOf(it[1]) >= 0); }
  function cmPeople() { var names = {}, pics = {}; (R.creators || []).forEach(function (c) { names[c.code] = c.name; pics[c.code] = c.photo; }); return { names: names, pics: pics }; }
  function cmPosts() { var posts = {}; (R.posts || []).forEach(function (p) { posts[p.id] = p; }); return posts; }
  function cmVidName(p, it) { return (KIND[p.kind] || p.kind || "Video") + " · " + (p.platform || it[2]) + (p.posted_at ? " · " + day(p.posted_at) : ""); }
  function cmRow(it) {
    var m = CM_MOOD[it[3]] || "neu";
    return '<div class="cmb-c"><i class="cm-face" style="--c:' + CM_COL[m] + '" title="' + CM_MOOD_W[it[3]] + '">' + CM_FACE[m] + '</i><div class="cmb-c__b"><q dir="auto">' + esc(it[7]) + "</q>"
      + '<p class="cmb-c__m">' + (it[5] ? '<span class="cmb-tag">' + cmIcon(it[5]) + esc(it[5]) + "</span>" : "")
      + (it[4] ? '<span class="cmb-buy">Asks to buy' + (it[6] ? ' · <q dir="auto">' + esc(it[6]) + "</q>" : "") + "</span>" : "")
      + (it[9] ? '<span class="cmb-likes">' + CM_HEART + it[9] + "</span>" : "") + "</p></div></div>";
  }
  function cmSamples() {
    [].forEach.call(document.querySelectorAll(".cmp-tl__s[data-theme]"), function (el) {
      var th = el.getAttribute("data-theme"), got = (CMB.items || []).filter(function (it) { return it[5] === th && cmInPage(it); }).slice(0, 3);
      el.innerHTML = got.length ? got.map(cmRow).join("") : '<p class="cmb__load">No comments to show.</p>';
    });
  }
  function cmPick2(skipVid) {
    var f = CMB.f, q = f.q.trim().toLowerCase();
    return (CMB.items || []).filter(function (it) { return cmInPage(it) && (!f.doc || it[1] === f.doc) && (skipVid || !f.vid || String(it[0]) === String(f.vid))
      && (!f.mood || it[3] === f.mood) && (!f.plat || it[2] === f.plat) && (!f.theme || it[5] === f.theme) && (!f.buy || it[4])
      && (!q || (it[7] + " " + it[6]).toLowerCase().indexOf(q) >= 0); });
  }
  // The video filter: one button showing the chosen video, a list of video cards (thumbnail, platform, type, date, comments).
  function cmVidPicker(vids, all, P, posts) {
    var f = CMB.f, ids = Object.keys(vids).sort(function (a, b) { return vids[b] - vids[a]; }), total = 0;
    ids.forEach(function (i) { total += vids[i]; });
    var card = function (id) {
      var p = posts[id] || {}, it = all.filter(function (x) { return String(x[0]) === id; })[0] || [];
      return '<span class="cmv__th">' + (p.thumb ? fit(p.thumb) : "") + '<i class="cmv__pl">' + (ICONS[p.platform || it[2]] || "") + '</i></span><span class="cmv__t"><b>' + esc((KIND[p.kind] || p.kind || "Video") + " · " + (p.platform || it[2]))
        + "</b><small>" + (f.doc ? "" : esc(P.names[it[1]] || it[1]) + " · ") + (p.posted_at ? day(p.posted_at) + " · " : "") + full(vids[id]) + " comments</small></span>";
    };
    var allCard = '<span class="cmv__all">' + IC.posts + '</span><span class="cmv__t"><b>All videos</b><small>' + ids.length + " video" + (ids.length === 1 ? "" : "s") + " · " + full(total) + " comments</small></span>";
    var cur = f.vid && vids[f.vid] ? card(f.vid) : allCard;
    return '<div class="cmv"><button type="button" class="cmv__btn" data-cmv="1" aria-haspopup="listbox" aria-expanded="false" aria-label="Choose a video">' + cur + '<span class="cmv__chev" aria-hidden="true"></span></button>'
      + '<ul class="cmv__list" role="listbox" aria-label="Videos" hidden><li role="option" aria-selected="' + (!f.vid) + '"><button type="button" data-vid="">' + allCard + "</button></li>"
      + ids.map(function (id) { return '<li role="option" aria-selected="' + (f.vid === id) + '"><button type="button" data-vid="' + id + '">' + card(id) + "</button></li>"; }).join("") + "</ul></div>";
  }
  // The doctor filter: the same picker as the video filter, with each doctor's photo, name and comment count.
  function cmDocPicker(docs, docKeys, P) {
    var f = CMB.f, total = 0; docKeys.forEach(function (c) { total += docs[c]; });
    var card = function (c) { return '<span class="cmv__av">' + ava(P.pics[c]) + '</span><span class="cmv__t"><b>' + esc(P.names[c] || c) + "</b><small>" + full(docs[c]) + " comments</small></span>"; };
    var allCard = '<span class="cmv__all">' + IC.reach + '</span><span class="cmv__t"><b>All doctors</b><small>' + docKeys.length + " doctor" + (docKeys.length === 1 ? "" : "s") + " · " + full(total) + " comments</small></span>";
    return '<div class="cmv cmv--doc"><button type="button" class="cmv__btn" data-cmv="1" aria-haspopup="listbox" aria-expanded="false" aria-label="Choose a doctor">' + (f.doc && docs[f.doc] ? card(f.doc) : allCard) + '<span class="cmv__chev" aria-hidden="true"></span></button>'
      + '<ul class="cmv__list" role="listbox" aria-label="Doctors" hidden><li role="option" aria-selected="' + (!f.doc) + '"><button type="button" data-docpick="">' + allCard + "</button></li>"
      + docKeys.map(function (c) { return '<li role="option" aria-selected="' + (f.doc === c) + '"><button type="button" data-docpick="' + esc(c) + '">' + card(c) + "</button></li>"; }).join("") + "</ul></div>";
  }
  // Item 222 (owner, 2026-10-21): a video lives on one platform, so picking it sets the platform filter to that platform and
  // locks the others (with a note); "All videos" unlocks it and puts back the platform chosen before. Counts follow the picks.
  function cmVidPlat(id) {
    var p = cmPosts()[id]; if (p && p.platform) return p.platform;
    var it = (CMB.items || []).filter(function (x) { return String(x[0]) === String(id); })[0];
    return it ? it[2] : "";
  }
  function cmPickVid(id) {
    var f = CMB.f;
    if (id && !f.vid) f.platPrev = f.plat;
    f.vid = id;
    f.plat = id ? cmVidPlat(id) : (f.platPrev || "");
    if (!id) f.platPrev = "";
  }
  function cmFilters() {
    var f = CMB.f, all = (CMB.items || []).filter(cmInPage), P = cmPeople(), posts = cmPosts(), docs = {}, vids = {}, th = {}, pl = {};
    var lock = f.vid ? cmVidPlat(f.vid) : "";
    all.forEach(function (it) {
      docs[it[1]] = (docs[it[1]] || 0) + 1;
      var inDoc = !f.doc || it[1] === f.doc;
      if (inDoc && (lock || !f.plat || it[2] === f.plat)) vids[it[0]] = (vids[it[0]] || 0) + 1;
      if (inDoc && (!f.vid || String(it[0]) === String(f.vid))) pl[it[2]] = (pl[it[2]] || 0) + 1;
      if (it[5]) th[it[5]] = (th[it[5]] || 0) + 1;
    });
    var moods = [["", "All"], ["p", "Positive"], ["n", "Neutral"], ["x", "Negative"]];
    var docKeys = Object.keys(docs).sort(function (a, b) { return docs[b] - docs[a]; });
    return '<div class="cmb-f">'
      + '<div class="cmb-f__row cmb-f__docs">' + cmDocPicker(docs, docKeys, P)
      + cmVidPicker(vids, all, P, posts) + "</div>"
      + '<div class="cmb-f__row"><div class="cmb-seg" role="group" aria-label="Mood">' + moods.map(function (m) {
          return '<button type="button" data-mood="' + m[0] + '" aria-pressed="' + (f.mood === m[0]) + '"' + (m[0] ? ' title="' + m[1] + '"' : "") + ">" + (m[0] ? '<i class="cm-face" style="--c:' + CM_COL[CM_MOOD[m[0]]] + '">' + CM_FACE[CM_MOOD[m[0]]] + '</i><span class="cmb-seg__t">' + m[1] + "</span>" : m[1]) + "</button>"; }).join("") + "</div>"
      + '<div class="cmb-seg cmb-seg--pl' + (lock ? " is-locked" : "") + '" role="group" aria-label="Platform"' + (lock ? ' aria-describedby="cmb-lock"' : "") + '><button type="button" data-plat="" aria-pressed="' + (!f.plat) + '"' + (lock ? " disabled" : "") + ">All</button>"
      + Object.keys(pl).sort(function (a, b) { return pl[b] - pl[a]; }).map(function (k) { var off = lock && k !== lock; return '<button type="button" data-plat="' + esc(k) + '" aria-pressed="' + (f.plat === k) + '"' + (off ? " disabled" : "") + ' title="' + esc(k) + " · " + pl[k] + ' comments" aria-label="' + esc(k) + " · " + pl[k] + ' comments">' + (ICONS[k] || esc(k)) + "<small>" + pl[k] + "</small></button>"; }).join("") + "</div>"
      + '<button type="button" class="cmb-export" data-export="1">' + CM_DL + "Export CSV</button></div>"
      + (lock ? '<p class="cmb-lock" id="cmb-lock">' + CM_LOCK + "<span>Showing <b>" + esc(lock) + "</b> only: this video is on " + esc(lock) + '. <button type="button" data-vid="">Show all videos</button> to choose another platform.</span></p>' : "")
      + '<div class="cmb-f__row"><select data-f="theme" aria-label="Topic"><option value="">All topics</option>' + Object.keys(th).sort(function (a, b) { return th[b] - th[a]; }).map(function (q) { return '<option value="' + esc(q) + '"' + (f.theme === q ? " selected" : "") + ">" + esc(q) + " (" + th[q] + ")</option>"; }).join("") + "</select>"
      + '<label class="cmb-f__buy"><input type="checkbox" data-f="buy"' + (f.buy ? " checked" : "") + "> Buying questions only</label>"
      + '<input type="search" data-f="q" placeholder="Search the comments" value="' + esc(f.q) + '" aria-label="Search the comments"></div></div>';
  }
  function cmList() {
    var list = cmPick2(), total = (CMB.items || []).filter(cmInPage).length, P = cmPeople(), posts = cmPosts(), by = {}, order = [];
    list.forEach(function (it) { if (!by[it[1]]) { by[it[1]] = {}; order.push(it[1]); } (by[it[1]][it[0]] = by[it[1]][it[0]] || []).push(it); });
    var head = '<p class="cmb-count">Showing <b>' + full(list.length) + "</b> of " + full(total) + " comments</p>";
    if (!list.length) return head + '<p class="cmb__load">No comment matches these filters.</p>';
    return head + order.map(function (code) {
      var vids = Object.keys(by[code]).sort(function (a, b) { return by[code][b].length - by[code][a].length; }), n = 0;
      vids.forEach(function (v) { n += by[code][v].length; });
      return '<details class="cmb-d" data-key="d:' + esc(code) + '"' + (CMB.closed["d:" + code] ? "" : " open") + '><summary class="cmb-d__h">' + ava(P.pics[code]) + "<b>" + esc(P.names[code] || code) + "</b><span>" + full(n) + " comment" + (n === 1 ? "" : "s") + " · " + vids.length + " video" + (vids.length === 1 ? "" : "s") + "</span>" + CM_CHEV + '</summary><div class="cmb-d__b">'
        + vids.map(function (vid) { var cs = by[code][vid], p = posts[vid] || {}, open = CMB.open[vid], show = open ? cs : cs.slice(0, 10);
          return '<details class="cmb-v" data-key="v:' + vid + '"' + (CMB.closed["v:" + vid] ? "" : " open") + '><summary class="cmb-v__h"><a class="cmb-v__th" href="' + esc(p.url || "#") + '" target="_blank" rel="noopener">' + (p.thumb ? fit(p.thumb) : "") + "</a>"
            + '<span class="cmb-v__t">' + (ICONS[p.platform || cs[0][2]] || "") + "<b>" + esc((KIND[p.kind] || p.kind || "Video") + " · " + (p.platform || cs[0][2])) + "</b><small>" + (p.posted_at ? day(p.posted_at) + " · " : "") + full(cs.length) + " comments</small></span>"
            + (p.url ? '<a class="cmb-v__go" href="' + esc(p.url) + '" target="_blank" rel="noopener">Open video ›</a>' : "") + CM_CHEV + '</summary><div class="cmb-v__body">'
            + '<div class="cmb-v__l">' + show.map(cmRow).join("") + "</div>"
            + (cs.length > 10 ? '<button type="button" class="cmb-more" data-more="' + vid + '">' + (open ? "Show fewer" : "Show all " + cs.length) + "</button>" : "") + "</div></details>"; }).join("")
        + "</div></details>";
    }).join("");
  }
  function cmExport() {
    var list = cmPick2(), P = cmPeople(), posts = cmPosts();
    var cell = function (v) { v = String(v == null ? "" : v); return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    var rows = [["Doctor", "Platform", "Video", "Video link", "Mood", "Topic", "Asks to buy", "Buying question", "Comment", "Likes", "Comment date"]];
    list.forEach(function (it) { var p = posts[it[0]] || {};
      rows.push([P.names[it[1]] || it[1], it[2], cmVidName(p, it), p.url || "", CM_MOOD_W[it[3]] || "", it[5], it[4] ? "Yes" : "", it[6], it[7], it[9], it[10] ? new Date(it[10] * 1000).toISOString().slice(0, 10) : ""]); });
    var csv = "﻿" + rows.map(function (r) { return r.map(cell).join(","); }).join("\r\n");
    var a = document.createElement("a"), url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    a.href = url; a.download = ((R.campaign && R.campaign.name) || "campaign").replace(/[^\w؀-ۿ -]+/g, "").trim().replace(/\s+/g, "-") + "-comments.csv";
    document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(url); a.remove(); }, 500);
  }
  function cmBind() {
    var box = $("cmb"); if (!box) return;
    cmLoad(function () {
      if (!$("cmb")) return;
      cmSamples();
      var draw = function () { box.innerHTML = cmFilters() + '<div class="cmb-l">' + cmList() + "</div>"; };
      var list = function () { box.querySelector(".cmb-l").innerHTML = cmList(); }, timer;
      draw();
      box.addEventListener("toggle", function (e) { var d = e.target; if (d.dataset && d.dataset.key) CMB.closed[d.dataset.key] = !d.open; }, true);
      var shut = function () { var any = false; [].forEach.call(box.querySelectorAll(".cmv__list"), function (x) { if (!x.hidden) { any = true; x.hidden = true; x.parentNode.querySelector(".cmv__btn").setAttribute("aria-expanded", "false"); } }); return any; };
      document.addEventListener("click", function (e) { if (!e.target.closest(".cmv")) shut(); });
      box.addEventListener("keydown", function (e) { if (e.key === "Escape" && shut()) e.stopPropagation(); });
      box.addEventListener("click", function (e) {
        var tv = e.target.closest("[data-cmv]"), dc = e.target.closest("[data-docpick]"), ov = e.target.closest("[data-vid]"), b = e.target.closest("[data-mood]"), pl = e.target.closest("[data-plat]"), m = e.target.closest("[data-more]");
        if (tv) { var ul = tv.parentNode.querySelector(".cmv__list"), was = ul.hidden; [].forEach.call(box.querySelectorAll(".cmv__list"), function (x) { x.hidden = true; x.parentNode.querySelector(".cmv__btn").setAttribute("aria-expanded", "false"); }); if (was) { ul.hidden = false; tv.setAttribute("aria-expanded", "true"); } return; }
        if (dc) { CMB.f.doc = dc.getAttribute("data-docpick"); if (CMB.f.vid) cmPickVid(""); draw(); return; }
        if (ov) { cmPickVid(ov.getAttribute("data-vid")); draw(); return; }
        if (b) { CMB.f.mood = b.getAttribute("data-mood"); draw(); return; }
        if (pl) { if (pl.disabled) return; CMB.f.plat = pl.getAttribute("data-plat"); draw(); return; }
        if (m) { var v = m.getAttribute("data-more"); CMB.open[v] = !CMB.open[v]; list(); return; }
        if (e.target.closest("[data-export]")) cmExport();
      });
      box.addEventListener("change", function (e) { var k = e.target.getAttribute("data-f"); if (!k || k === "q") return; CMB.f[k] = e.target.type === "checkbox" ? e.target.checked : e.target.value; if (k === "doc") { CMB.f.vid = ""; draw(); } else list(); });
      box.addEventListener("input", function (e) { if (e.target.getAttribute("data-f") !== "q") return; CMB.f.q = e.target.value; clearTimeout(timer); timer = setTimeout(list, 200); });
    });
  }

  var PCOL = { Instagram: "#d62976", TikTok: "#121212", Snapchat: "#f7d100", YouTube: "#ff0000", Facebook: "#0866ff", X: "#121212" };
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
    var by = {}; list.forEach(function (p) { var x = by[p.platform] = by[p.platform] || { n: 0, posts: 0, eng: 0, hid: true }; x.n += seen(p); x.posts++; x.eng += p.engagement || 0; if (!(p.video && p.views_hidden)) x.hid = false; });
    var rows = Object.keys(by).map(function (k) { return { k: k, n: by[k].n, posts: by[k].posts, eng: by[k].eng, hid: by[k].hid }; }).sort(function (a, b) { return b.n - a.n; });
    var tot = rows.reduce(function (a, r) { return a + r.n; }, 0), peak = rows.length ? Math.max(rows[0].n, 1) : 1, body;
    if (!rows.length) body = '<p class="db-note">No posts in this view.</p>';
    else {
      // One line per platform, all visible: its views, a bar against the biggest platform, its share of all views and its engagement rate.
      body = rows.map(function (r) {
        var share = tot ? Math.round(r.n / tot * 100) : 0;
        return '<div class="db-plr" title="' + esc(r.k) + ": " + num(r.n) + " views, " + share + '% of all views"><span class="db-plr__n" aria-label="' + esc(r.k) + '">' + (ICONS[r.k] || esc(r.k)) + "</span>"
          + '<i style="--w:' + (r.n / peak * 100).toFixed(1) + "%;--c:" + (PCOL[r.k] || COL[0]) + '"></i>'
          + (r.hid ? '<b class="db-plr__na" title="' + esc(r.k) + ' does not show view counts">n/a</b><span>—</span></div>' : "<b>" + num(r.n) + "</b><span>" + share + "%</span></div>");
      }).join("");
    }
    $("w-plat").innerHTML = head(IC.plat, "Platforms", "Views on each platform: the bar is against the biggest platform, the number is its views and the % is its share of all views. Open More for posts and engagement rate. Views for videos, reach for photo posts and stories, never both added together.", "plat")
      + '<div class="db-card__body">' + body + "</div>";
  }

  function renderClicks(cl) {
    if (R.sales && R.sales.totals) return renderSales(cl);
    $("w-clicks").innerHTML = head(IC.clicks, "Affiliate clicks", "Taps on the creators' own tracking links — people only, not link previews or bots.", cl ? "clicks" : "")
      + '<div class="db-card__body">' + (cl ? '<div class="db-big">' + full(cl.clicks) + (cl.uniques != null ? "<small>" + full(cl.uniques) + " unique</small>" : "") + "</div>"
        + '<div style="margin-top:8px">' + bars((cl.by_app || []).slice(0, 3).map(function (r) { return { k: r.k, n: r.n, label: full(r.n) }; }), function (r) { return (ICONS[r.k] || "") + esc(r.k); }) + "</div>"
        + (cl.partial || F.platform ? '<p class="db-note">' + (F.platform ? "Clicks are per creator link, not per platform — showing all platforms." : "Apps show the whole campaign.") + "</p>" : "")
        : '<div class="db-na-card"><span class="db-na-card__icon">' + IC.clicks + '</span><span class="db-na">Not part of this campaign</span>'
          + "<p>This campaign does not contain affiliate links, so there are no clicks to show.</p></div>") + "</div>";
  }

  /* Clicks to sales (owner, 2026-10-20): when a campaign has sales data (R.sales: promo-code and retailer reports,
     tracked links), the affiliate-clicks slot tells the sales story; the drawer keeps the click breakdowns at the end. */
  var SLI = ico('<path d="M5 8h14l-1.2 11.2a2 2 0 0 1-2 1.8H8.2a2 2 0 0 1-2-1.8z"/><path d="M9 8V6.5a3 3 0 0 1 6 0V8"/>');
  var SLCOL = ["#121212", "#ff691e", "#14884a", "#b9d400", "#8a8278", "#d4560a"];
  function money(v, cur) { return (cur || "SAR") + " " + num(v); }
  function roasTxt(v) { return v == null ? "—" : v.toFixed(1) + "×"; }
  function renderSales(cl) {
    var S = R.sales, T = S.totals || {}, src = (S.sources || []).slice().sort(function (a, b) { return b.revenue - a.revenue; });
    var tot = src.reduce(function (a, s) { return a + s.revenue; }, 0) || 1;
    $("w-clicks").innerHTML = head(SLI, "Clicks to sales", "Sales the campaign drove: promo codes, retailer reports and the creators' tracked links. " + (S.basis || ""), "clicks")
      + '<div class="db-card__body sl-card"><div class="sl-card__top"><div class="sl-card__rev"><b>' + money(T.revenue, S.currency) + "</b><span>in sales</span></div>"
      + '<div class="sl-card__roas" title="Sales per riyal spent on the campaign"><b>' + roasTxt(T.roas) + "</b><span>return</span></div></div>"
      + '<div class="sl-stack" role="img" aria-label="Sales by retailer: ' + esc(src.map(function (s) { return s.label + " " + Math.round(s.revenue / tot * 100) + "%"; }).join(", ")) + '">'
      + src.map(function (s, i) { return '<i style="flex:' + s.revenue + ";background:" + SLCOL[i % SLCOL.length] + '"></i>'; }).join("") + "</div>"
      + '<div class="sl-legend">' + src.slice(0, 3).map(function (s, i) { return '<span><i style="background:' + SLCOL[i] + '"></i>' + esc(s.label) + " <b>" + Math.round(s.revenue / tot * 100) + "%</b></span>"; }).join("") + "</div>"
      + '<p class="sl-card__foot"><b>' + full(T.orders) + "</b> orders" + (T.conv != null ? " · <b>" + pct(T.conv, 1) + "</b> of link clicks bought" : "") + "</p></div>";
  }
  function salesDays() {
    var S = R.sales, ds = S.days || [], W = 640, H = 230, L = 10, Rr = 10, T = 30, B = 34;
    if (ds.length < 2) return "";
    var mx = Math.max.apply(null, ds.map(function (d) { return d.revenue; })) || 1, n = ds.length;
    var x = function (i) { return L + i * (W - L - Rr) / (n - 1); }, y = function (v) { return T + (1 - v / mx) * (H - T - B); };
    var pts = ds.map(function (d, i) { return [x(i), y(d.revenue)]; }), line = cmCurve(pts);
    var area = line + " L" + pts[n - 1][0].toFixed(1) + " " + (H - B) + " L" + pts[0][0].toFixed(1) + " " + (H - B) + " Z";
    var first = ds.findIndex ? ds.findIndex(function (d) { return !d.before; }) : 0; if (first < 0) first = 0;
    var postsBy = {}; posts().forEach(function (p) { if (p.posted_at) { var k = new Date((p.posted_at + 3 * 3600) * 1000).toISOString().slice(0, 10); postsBy[k] = (postsBy[k] || 0) + 1; } });
    var pmx = Math.max.apply(null, Object.keys(postsBy).map(function (k) { return postsBy[k]; }).concat([1]));
    var base = S.baseline && S.baseline.daily ? y(S.baseline.daily) : null, step = Math.ceil(n / 7), pk = 0;
    ds.forEach(function (d, i) { if (d.revenue > ds[pk].revenue) pk = i; });
    return '<div class="sl-days"><svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Sales per day: ' + esc(ds.map(function (d) { return day(d.d) + " " + money(d.revenue, S.currency); }).join(", ")) + '">'
      + '<defs><linearGradient id="sl-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#14884a" stop-opacity=".22"/><stop offset="1" stop-color="#14884a" stop-opacity=".02"/></linearGradient></defs>'
      + (first > 0 ? '<rect x="' + L + '" y="' + T + '" width="' + (x(first) - L).toFixed(1) + '" height="' + (H - T - B) + '" class="sl-days__before"/><text x="' + (L + 6) + '" y="' + (T + 14) + '" class="sl-days__lbl">Before the campaign</text>' : "")
      + ds.map(function (d, i) { var c = postsBy[d.d]; return c ? '<rect class="sl-days__post" x="' + (x(i) - 2.5).toFixed(1) + '" y="' + (H - B - 4 - c / pmx * 26).toFixed(1) + '" width="5" height="' + (c / pmx * 26 + 4).toFixed(1) + '" rx="2"><title>' + day(d.d) + ": " + c + " videos posted</title></rect>" : ""; }).join("")
      + '<line x1="' + L + '" y1="' + (H - B) + '" x2="' + (W - Rr) + '" y2="' + (H - B) + '" stroke="#e6e2db" stroke-width="1.5"/>'
      + (base != null ? '<line x1="' + L + '" y1="' + base.toFixed(1) + '" x2="' + (W - Rr) + '" y2="' + base.toFixed(1) + '" class="sl-days__base"/><text x="' + (L + 6) + '" y="' + (base - 7).toFixed(1) + '" text-anchor="start" class="sl-days__lbl">Usual day: ' + money(S.baseline.daily, S.currency) + "</text>" : "")
      + '<path d="' + area + '" fill="url(#sl-fill)"/><path d="' + line + '" fill="none" stroke="#14884a" stroke-width="3" stroke-linecap="round"/>'
      + '<circle cx="' + pts[pk][0].toFixed(1) + '" cy="' + pts[pk][1].toFixed(1) + '" r="6" class="sl-days__pk"/><text x="' + Math.min(W - 60, Math.max(60, pts[pk][0])).toFixed(1) + '" y="' + (pts[pk][1] - 12).toFixed(1) + '" text-anchor="middle" class="sl-days__v">' + money(ds[pk].revenue, S.currency) + "</text>"
      + ds.map(function (d, i) { if (i % step && i !== n - 1) return ""; if (i !== n - 1 && n - 1 - i < step * 0.8) return "";
          return '<text x="' + x(i).toFixed(1) + '" y="' + (H - 10) + '" text-anchor="' + (i === 0 ? "start" : i === n - 1 ? "end" : "middle") + '" class="cmp-curve__d">' + day(d.d) + "</text>"; }).join("")
      + "</svg></div>"
      + '<p class="db-note"><span class="sl-key sl-key--line"></span>Sales per day <span class="sl-key sl-key--post"></span>Videos posted that day' + (base != null ? ' <span class="sl-key sl-key--base"></span>Usual day before the campaign' : "") + "</p>";
  }
  function salesPanel() {
    var S = R.sales, T = S.totals || {}, cur = S.currency, cl = clicksFor();
    var src = (S.sources || []).slice().sort(function (a, b) { return b.revenue - a.revenue; }), stot = src.reduce(function (a, s) { return a + s.revenue; }, 0) || 1;
    var box = function (n, l, cls) { return '<div class="cmp-box' + (cls ? " " + cls : "") + '"><b>' + n + "</b><span>" + l + "</span></div>"; };
    var lift = S.baseline && S.baseline.lift != null ? S.baseline.lift : null;
    var out = '<div class="sl-hero"><span class="sl-hero__ic">' + SLI + '</span><div><p class="sl-hero__t">Every ' + esc(cur) + " 1 spent brought back <mark>" + esc(cur) + " " + (T.roas || 0).toFixed(2) + "</mark></p>"
      + "<p>" + money(T.revenue, cur) + " in sales from " + full(T.orders) + " orders" + (lift != null ? ", <b>" + (lift >= 0 ? "+" : "") + Math.round(lift) + "%</b> above a usual day before the campaign" : "") + ".</p></div></div>"
      + '<div class="cmp-boxes sl-boxes">' + box(money(T.revenue, cur), "sales", "is-hot") + box(full(T.orders), "orders") + box(roasTxt(T.roas), "return on spend")
      + box(money(T.cpo, cur), "cost per order") + box(money(T.aov, cur), "average basket") + (T.new_share != null ? box(Math.round(T.new_share * 100) + "%", "new customers") : "") + "</div>";
    var FN = S.funnel || [], fmx = Math.log10(Math.max.apply(null, FN.map(function (f) { return f.n; }).concat([10])));
    if (FN.length) out += sec("sl-funnel", "From view to order", "Each step as people moved from a video to a purchase. Bars use a log scale so every step stays visible. Orders here are the ones tracked from a link; promo-code orders in stores are counted in the totals above.",
      '<ol class="sl-funnel">' + FN.map(function (f, i) {
        var prev = i ? FN[i - 1].n : null, r = prev ? f.n / prev * 100 : null;
        return '<li style="--w:' + Math.max(6, Math.log10(Math.max(1, f.n)) / fmx * 100).toFixed(1) + '%"><span class="sl-funnel__k">' + esc(f.k) + "</span><i></i><b>" + num(f.n) + "</b>"
          + (r != null ? '<small>' + (r < 1 ? r.toFixed(2) : r < 10 ? r.toFixed(1) : Math.round(r)) + "% of the step before</small>" : "<small>&nbsp;</small>") + "</li>"; }).join("") + "</ol>");
    out += sec("sl-src", "Where people bought", "Revenue by store and how it was measured: promo-code reports, retailer attribution reports and tracked links.",
      '<div class="sl-src">' + src.map(function (s, i) {
        return '<div class="sl-src__r"><span class="sl-src__dot" style="background:' + SLCOL[i % SLCOL.length] + '"></span><div class="sl-src__n"><b>' + esc(s.label) + "</b><small>" + esc(s.via || "") + '</small></div>'
          + '<div class="sl-src__bar"><i style="--w:' + (s.revenue / src[0].revenue * 100).toFixed(1) + "%;--c:" + SLCOL[i % SLCOL.length] + '"></i></div>'
          + '<div class="sl-src__m"><b>' + money(s.revenue, cur) + "</b><small>" + full(s.orders) + " orders · " + Math.round(s.revenue / stot * 100) + "%</small></div></div>"; }).join("") + "</div>");
    if ((S.days || []).length > 1) out += sec("sl-days", "Sales by day", "Daily sales across every store, with the days videos went live. The shaded part is the two weeks before the campaign.", salesDays());
    var names = {}, pics = {}; (R.creators || []).forEach(function (c) { names[c.code] = c.name; pics[c.code] = c.photo; });
    var cr = (S.creators || []).slice(0, 10), cmx = cr.length ? cr[0].revenue : 1;
    if (cr.length) out += sec("sl-cr", "Creators who sold the most", "Sales from each creator's own promo code and tracking link.",
      '<ol class="sl-cr">' + cr.map(function (c, i) {
        return '<li><span class="sl-cr__i">' + (i + 1) + "</span>" + ava(pics[c.code]) + '<span class="sl-cr__n"><b>' + esc(names[c.code] || c.name || c.code) + '</b><small><span class="sl-code">' + esc(c.promo) + "</span>" + full(c.orders) + " orders</small></span>"
          + '<span class="sl-cr__bar"><i style="--w:' + (c.revenue / cmx * 100).toFixed(1) + '%"></i></span><b class="sl-cr__v">' + money(c.revenue, cur) + "</b></li>"; }).join("") + "</ol>");
    var C = S.customers || {}, ct = (C["new"] || 0) + (C.returning || 0) || 1;
    var L = function (rows, fmt) { return (rows || []).map(function (r) { return { k: r.k, n: r.n, label: fmt(r.n) }; }); };
    var hasC = (C["new"] || 0) + (C.returning || 0) > 0, hasCt = (S.cities || []).length > 0, hasP = (S.products || []).length > 0;
    var who = (hasC || hasCt) ? sec("sl-who", "Who bought", "New customers had not bought the brand before, as the retailers report it.",
        (hasC ? '<div class="sl-split"><i style="flex:' + (C["new"] || 0) + '"><b>' + Math.round((C["new"] || 0) / ct * 100) + '%</b> new</i><i style="flex:' + (C.returning || 0) + '"><b>' + Math.round((C.returning || 0) / ct * 100) + "%</b> returning</i></div>" : "")
        + (hasCt ? "<h4 class=\"sl-h4\">Top cities</h4>" + bars(L(S.cities, function (n) { return money(n, cur); }), function (r) { return esc(r.k); }, function (i) { return SLCOL[i % SLCOL.length]; }) : "")) : "";
    var sku = hasP ? sec("sl-sku", "What sold", "Revenue by product, from the retailers' reports.", bars(L(S.products, function (n) { return money(n, cur); }), function (r) { return esc(r.k); }, function (i) { return SLCOL[i % SLCOL.length]; })) : "";
    if (who || sku) out += (who && sku ? '<div class="sl-two">' + who + sku + "</div>" : who + sku);
    if (cl) {
      var B = function (rows) { return (rows || []).map(function (r) { return { k: r.k, n: r.n, label: full(r.n) }; }); };
      out += sec("sl-clk", "Link clicks", "Taps on the creators' own tracking links — people only, not link previews or bots.",
        '<div class="db-big">' + full(cl.clicks) + " <small>clicks" + (cl.uniques != null ? " · " + full(cl.uniques) + " unique people" : "") + "</small></div>"
        + '<div class="sl-two sl-two--flat"><div><h4 class="sl-h4">By app</h4>' + bars(B(cl.by_app), function (r) { return (ICONS[r.k] || "") + esc(r.k); })
        + '</div><div><h4 class="sl-h4">By country</h4>' + bars(B((cl.by_country || []).slice(0, 6)), function (r) { return r.k && r.k.length === 2 ? flag(r.k) + esc(countryName(r.k)) : esc(r.k || "Unknown"); }) + "</div></div>");
    }
    return out + (S.basis ? '<p class="db-note">' + esc(S.basis) + "</p>" : "");
  }

  // People who saw a post: views for a video, reach for a photo or story.
  // Adding the two would count the same viewers twice.
  // One video the creator published on several platforms is one piece: it counts once as a post.
  function pieceKey(p) { return p.piece_size > 1 ? "g" + p.pk : "s" + p.id; }
  function pieceCount(l) { var s = {}; l.forEach(function (p) { s[pieceKey(p)] = 1; }); return Object.keys(s).length; }
  // The same video on several platforms as one card: numbers added up, a mark for each platform.
  function mergePieces(list) {
    var by = {}, order = [];
    list.forEach(function (p) { var k = pieceKey(p); if (!by[k]) { by[k] = []; order.push(k); } by[k].push(p); });
    return order.map(function (k) {
      var g = by[k]; if (g.length === 1) return g[0];
      var m = {}, lead = g[0];
      Object.keys(lead).forEach(function (f) { m[f] = lead[f]; });
      ["likes", "comments", "views", "reach", "impressions", "saves", "shares", "engagement", "exposure"].forEach(function (f) {
        var v = g.map(function (x) { return x[f]; }).filter(function (x) { return x != null; });
        m[f] = v.length ? v.reduce(function (a, b) { return a + b; }, 0) : null;
      });
      m.video = g.some(function (x) { return x.video; });
      m.thumb = (g.filter(function (x) { return x.thumb; })[0] || lead).thumb;
      m.parts = g; return m;
    });
  }
  function platIcons(p) { return (p.parts || [p]).map(function (x) { return ICONS[x.platform] || ""; }).join(""); }
  function seen(p) { return p.exposure != null ? p.exposure : (p.video ? (p.views || 0) : (p.reach || 0)); }
  function topPosts(list) { return list.slice().sort(function (a, b) { return seen(b) - seen(a); }); }
  function weights() { var w = (R.objective || {}).weights || { exposure: 0.35, engagement: 0.25, er: 0.25, clicks: 0.15 }; return w; }
  // The scoring as one bar: each part's share of the 100 points. Clicks only
  // when the campaign tracks links. `small` is the compact form for the card.
  var SCORECOL = { exposure: "#14884a", engagement: "#ff691e", er: "#b9d400", clicks: "#121212" };
  function scoreParts() {
    var w = weights(), parts = [["Views", w.exposure, SCORECOL.exposure, "what they delivered, vs the top creator"], ["Engagement", w.engagement, SCORECOL.engagement, "likes + comments delivered, vs the top creator"]];
    if (w.er > 0) parts.push(["Engagement rate", w.er, SCORECOL.er, "reactions per view vs the best creator"]);
    if (w.clicks > 0) parts.push(["Link clicks", w.clicks, SCORECOL.clicks, "vs the top creator"]);
    return parts;
  }
  function scoreBar(small) {
    var parts = scoreParts();
    return '<div class="db-scorebar' + (small ? " db-scorebar--s" : "") + '">' + parts.map(function (x) {
      // Text colour follows the segment (owner, 2026-10-20): ink only on the light lime, white on green, orange and black.
      return '<i style="flex:' + x[1] + ";background:" + x[2] + '"><b' + (x[2] === SCORECOL.er ? ' class="is-ink"' : "") + ">" + Math.round(x[1] * 100) + "<small>%</small></b></i>"; }).join("") + '</div><div class="db-scorekey' + (small ? " db-scorekey--s" : "") + '">'
      + parts.map(function (x) { return '<div><i style="background:' + x[2] + '"></i><b>' + x[0] + "</b>" + (small ? "" : "<small>" + x[3] + "</small>") + "</div>"; }).join("") + "</div>";
  }
  // The campaign's objective as shares: how much of a creator's score is
  // awareness, engagement and clicks.
  function objectiveBox() {
    var w = weights(), o = R.objective || {}, links = !!o.links;
    var tiles = [["Awareness", w.exposure || 0, "views", SCORECOL.exposure], ["Engagement", (w.engagement || 0) + (w.er || 0), "likes & comments", SCORECOL.engagement],
      ["Clicks", w.clicks || 0, links ? "link clicks" : "no tracking links in this campaign", SCORECOL.clicks]];
    return sec("for", "What this campaign is for", "Objective: " + (o.label || "Balanced") + ". Each share is what that part is worth in a creator's score out of 100.",
      '<div class="db-obj">' + tiles.map(function (t) {
        return '<div class="db-obj__t"><i style="background:' + t[3] + '"></i><b>' + Math.round(t[1] * 100) + "%</b><span>" + t[0] + "</span><small>" + t[2] + "</small></div>"; }).join("") + "</div>");
  }
  function scoreTip() {
    var w = weights(), o = (R.objective || {}).label || "Balanced";
    return "Score out of 100, weighted for the " + o + " objective: views " + Math.round(w.exposure * 100) + ", engagement " + Math.round(w.engagement * 100)
      + (w.er > 0 ? ", engagement rate " + Math.round(w.er * 100) : "") + (w.clicks > 0 ? ", link clicks " + Math.round(w.clicks * 100) : "")
      + ". Each is the creator's result as a share of the best creator's: it rewards what they delivered for the campaign, not their follower count.";
  }
  function renderPosts(list) {
    var top = topPosts(mergePieces(list)).slice(0, 3);
    $("w-posts").innerHTML = head(IC.img, "Top videos", "The three videos that reached the most people in this view. A video on several platforms counts once, with every platform added together.", "posts")
      + '<div class="db-card__body"><div class="db-thumbs">' + (top.map(function (p, i) {
        return '<a class="db-thumb" href="' + esc(p.url) + '" target="_blank" rel="noopener">' + fit(p.thumb)
          + '<svg class="db-thumb__n" viewBox="0 0 40 50" aria-hidden="true">' + medalBody(i + 1) + "</svg>"
          + "<span><em>" + esc(p.creator) + "</em>" + (p.parts ? '<b class="db-thumb__plats">' + platIcons(p) + "</b>" : "") + "<i>" + (p.parts ? "" : (ICONS[p.platform] || "")) + (p.views_hidden && !p.parts ? num(p.likes) : num(p.parts ? seen(p) : (p.video ? p.views : p.reach))) + "<small style=\"font:600 10px var(--body);color:#fff;opacity:.7\">" + (p.views_hidden && !p.parts ? "likes" : p.video || p.parts ? "views" : "reached") + "</small></i></span></a>";
      }).join("") || '<p class="db-note">No posts in this view.</p>') + "</div></div>";
  }

  // Each creator's videos, one row per video, a chip for every platform it went out on.
  function videosByCreator(list, rows) {
    var pieces = mergePieces(list), by = {};
    pieces.forEach(function (p) { (by[p.code] = by[p.code] || []).push(p); });
    var out = rows.map(function (c) {
      var mine = (by[c.code] || []).slice().sort(function (a, b) { return (a.posted_at || 0) - (b.posted_at || 0); });
      if (!mine.length && !c.planned) return "";
      var tot = mine.reduce(function (a, p) { return a + seen(p); }, 0);
      var rowsHtml = mine.map(function (p, i) {
        var parts = p.parts || [p];
        return '<div class="db-vid"><div class="db-vid__t"><b>Video ' + (i + 1) + (c.planned ? " of " + c.planned : "") + "</b><small>" + esc(day(p.posted_at)) + "</small></div>"
          + '<div class="db-vid__n">' + num(seen(p)) + "<small>views</small></div>"
          + '<div class="db-vid__chips">' + parts.map(function (x) {
            return '<a class="db-chip" href="' + esc(x.url) + '" target="_blank" rel="noopener">' + (ICONS[x.platform] || "") + esc(x.platform) + " · " + num(seen(x)) + "</a>";
          }).join("") + "</div></div>";
      }).join("");
      var owed = []; for (var i = mine.length; i < (c.planned || 0); i++) owed.push('<div class="db-vid is-owed"><div class="db-vid__t"><b>Video ' + (i + 1) + " of " + c.planned + "</b><small>Not published yet</small></div></div>");
      return '<div class="db-vids"><h4>' + ava(c.photo) + "<span>" + who(c) + "</span><b>" + mine.length + (c.planned ? "/" + c.planned : "") + " videos · " + num(tot) + " views</b></h4>" + rowsHtml + owed.join("") + "</div>";
    }).join("");
    return out ? "<h3>Videos by creator</h3>" + out : "";
  }

  /* ------------------------------------------- goals: targets, forecast, benchmarks */
  // The Goals & benchmarks tab, for the client. One list of targets (achieved, benchmark range, where it
  // should be today, a status in words); click a row for its pace chart, which follows the publishing plan.
  // One headline per section, with its description in the "i" beside it rather than a paragraph under it.
  function sec(id, title, tip, body, aside) {
    return '<section class="db-sec" aria-labelledby="sec-' + id + '"><header class="db-sec__h"><h3 class="db-sec__t" id="sec-' + id + '">' + esc(title) + "</h3>" + (tip ? info(tip, title) : "")
      + (aside ? '<span class="db-sec__aside">' + aside + "</span>" : "") + "</header>" + body + "</section>";
  }
  function subsec(title, tip, body) {
    return '<div class="db-sub2"><div class="db-sec__h db-sec__h--s"><h4 class="db-sec__s">' + esc(title) + "</h4>" + (tip ? info(tip, title) : "") + "</div>" + body + "</div>";
  }
  var TV_COL = { good: "#14884a", moderate: "#e2780f", low: "#ee1515" };
  var STW = { good: "On track", moderate: "Close", low: "Behind" };
  function tvFmt(k, v) { return v == null ? "—" : k === "er" ? pct(v) : num(v); }
  // The Goals tab follows the page's platform filter (not the date filter: it is always measured from the start).
  // "all": every goal platform together. "plat": one goal platform, on its own targets. "bonus": a platform
  // with no goal. An older plan that kept no per-platform estimate shows the whole campaign ("whole").
  function scope() {
    var g = R.goals, pl = F.platform;
    if (!g || !pl) return { mode: "all" };
    if (g.platforms.indexOf(pl) < 0) return { mode: "bonus", pl: pl };
    if (g.platforms.length === 1) return { mode: "all" };
    var bp = g.by_platform && g.by_platform[pl];
    return bp ? { mode: "plat", pl: pl, bp: bp } : { mode: "whole", pl: pl };
  }
  function GL() {
    var g = R.goals; if (!g) return null;
    var sc = scope();
    return sc.mode === "plat" ? Object.assign({}, g, { creators: sc.bp.creators, forecast: sc.bp.forecast, pace: sc.bp.pace, aim: sc.bp.aim }) : g;
  }
  function SP() { var sc = scope(); return sc.mode === "plat" ? sc.bp.progress : R.progress; }
  function goalPlats() { var g = R.goals, sc = scope(); return g ? (sc.mode === "plat" ? [sc.pl] : g.platforms) : []; }
  // The platforms a plan was benchmarked for, always one entry each so every one gets its own icon.
  function planPlats() {
    var g = R.goals, plan = R.plan || {};
    if (g && g.platforms && g.platforms.length) return g.platforms;
    if (plan.platforms && plan.platforms.length) return plan.platforms;
    return String(plan.platform || "").split("+").map(function (x) { return x.trim(); }).filter(Boolean);
  }
  function stPill(cls, word) { return '<span class="db-st db-st--' + cls + '">' + esc(word) + "</span>"; }
  // Status in words as well as colour: Met / On track / Close / Behind.
  function tvStatus(i) { return i.actual >= i.goal ? ["good", "Met"] : [i.grade || "low", STW[i.grade] || "Behind"]; }
  function planRange(k) {
    var p = R.plan || {}, sf = p.safe || {}, ex = p.estimate || {}, sc = scope();
    if (sc.mode === "plat") { var o = (p.by_platform || {})[sc.pl] || {}; sf = o.safe || {}; ex = o.expected || {}; }
    return k !== "posts" && sf[k] != null && ex[k] != null ? tvFmt(k, sf[k]) + " – " + tvFmt(k, ex[k]) : "";
  }
  function tvRows(items, lead) {
    return items.map(function (i) {
      var met = i.actual >= i.goal, col = TV_COL[met ? "good" : i.grade] || TV_COL.low, isR = i.key === "er", st = tvStatus(i);
      var w = Math.min(100, i.pct), exp = isR || !i.goal ? null : Math.min(100, i.expected / i.goal * 100);
      var over = met && i.pct > 100.5 ? Math.round(i.pct - 100) : 0;
      var togo = met ? (over ? "Target met, " + over + "% over" : "Target met")
        : tvFmt(i.key, i.goal - i.actual) + (isR ? " points" : "") + " to go";
      var today = exp == null ? "" : " · should be at " + tvFmt(i.key, i.expected) + " by today";
      var rng = planRange(i.key), can = !isR, id = "tv-" + i.key;
      var label = KEYN[i.key] + ": " + tvFmt(i.key, i.actual) + " of " + tvFmt(i.key, i.goal) + ", " + Math.round(i.pct) + "% of the target" + (exp == null ? "" : ", expected " + Math.round(exp) + "% by today") + ", " + st[1];
      var inner = '<span class="db-tv__top"><b>' + KEYN[i.key] + "</b>" + (lead.indexOf(i.key) >= 0 ? ' <span class="db-lead">headline</span>' : "") + stPill(st[0], st[1])
        + '<span class="db-tv__nums"><strong>' + tvFmt(i.key, i.actual) + "</strong> of " + tvFmt(i.key, i.goal) + "</span></span>"
        + '<span class="db-tv__track" role="img" aria-label="' + esc(label) + '"><i style="--w:' + w.toFixed(1) + "%;background:" + col + '"></i>'
        + (exp == null ? "" : '<em style="left:' + exp.toFixed(1) + '%"><u>today</u></em>') + (over ? '<s style="color:' + col + '">+' + over + "%</s>" : "") + "</span>"
        + '<span class="db-tv__sub"><span class="db-tv__pct" style="color:' + col + '">' + Math.round(i.pct) + "% met</span>" + esc(togo + today)
        + (can ? '<svg class="db-tv__chev" viewBox="0 0 12 12" aria-hidden="true"><path d="M3 4.5l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>' : "") + "</span>"
        + (rng ? '<span class="db-tv__rng">Benchmark range for these creators <b>' + esc(rng) + "</b></span>" : "");
      return '<div class="db-tv__row" data-k="' + i.key + '">'
        + (can ? '<button type="button" class="db-tv__btn" aria-expanded="false" aria-controls="' + id + '">' + inner + "</button>" : '<div class="db-tv__btn db-tv__btn--static">' + inner + "</div>")
        + (can ? '<div class="db-tv__pace" id="' + id + '" hidden></div>' : "") + "</div>";
    }).join("");
  }
  function tvInfographic(items, lead) {
    var tip = "Each row is one target: what is achieved so far, where the plan says it should be today, and the benchmark range, which is what creators of this size typically get. The low end is what we commit to, the high end is what we aim for. Select a row to see its pace over time.";
    if (!items.length) return sec("targets", "Targets", tip, '<p class="db-empty">No targets set for this campaign yet.</p>');
    return sec("targets", "Targets", tip, '<div class="db-tv" id="db-tv">' + tvRows(items, lead) + "</div>"
      + '<div class="db-legend2"><span><i class="sw" style="background:#14884a"></i>Met / on track</span><span><i class="sw" style="background:#e2780f"></i>Close</span><span><i class="sw" style="background:#ee1515"></i>Behind</span>'
      + '<span><i class="tick"></i>Where it should be today</span><span class="db-tv__hint">Select a row for its pace</span></div>');
  }

  // The pace curve follows the publishing plan: the share of the target the videos due so far should have reached.
  function paceArr(item) { var P = (GL() || {}).pace; return P ? (item.key === "posts" ? P.posts : P.mature) : null; }
  function paceFrac(item, t) {
    var P = (GL() || {}).pace; if (!P) return null;
    var arr = paceArr(item);
    if (!arr || !arr.length) return Math.min(1, Math.max(0, (t - P.start) / Math.max(1, P.end - P.start)));
    if (t <= arr[0][0]) return item.key === "posts" ? arr[0][1] : 0;
    for (var n = 1; n < arr.length; n++) if (t <= arr[n][0]) { var a = arr[n - 1], b = arr[n]; return item.key === "posts" ? a[1] : a[1] + (b[1] - a[1]) * (t - a[0]) / Math.max(1, b[0] - a[0]); }
    return arr[arr.length - 1][1];
  }
  function goalPosts() { var g = GL(), pls = goalPlats(); return R.posts.filter(function (p) { return p.section === "campaign" && (!g || pls.indexOf(p.platform) >= 0); }); }
  // Chart geometry is kept on the svg so the hover and arrow-key readout draw on the same scale as the chart.
  function paceGeom(svg) {
    var g = {}; ["w", "h", "l", "r", "t", "b", "t0", "t1", "ymax", "now"].forEach(function (k) { g[k] = +svg.getAttribute("data-" + k); }); return g;
  }
  // The pace chart for one target: cumulative achieved by posting day against the pace the publishing plan sets.
  function tvPace(item, W) {
    var c = R.campaign || {}, P = (GL() || {}).pace || (c.starts_at && c.ends_at ? { start: c.starts_at, end: c.ends_at } : null);
    if (!P) return '<p class="db-empty">The pace appears once the publishing dates are set.</p>';
    var steps = item.key === "posts", key = item.key === "engagement" ? "eng" : item.key;
    W = Math.max(260, Math.min(720, Math.round(W || 600)));
    var H = 196, L = 10, Rr = W - 12, T = 26, B = 158;
    var data = series(goalPosts()).map(function (r) { return { t: Date.parse(r.d + "T12:00:00Z") / 1000, v: r[key] || 0 }; });
    var nowRaw = Date.now() / 1000;
    var t0 = Math.min(P.start, data.length ? data[0].t - 86400 : P.start), t1 = Math.max(P.end, data.length ? data[data.length - 1].t : P.end);
    var now = Math.min(nowRaw, t1), span = Math.max(1, t1 - t0), ymax = Math.max(item.goal, item.actual) * 1.08 || 1;
    function X(t) { return L + (Math.min(Math.max(t, t0), t1) - t0) / span * (Rr - L); }
    function Y(v) { return B - v / ymax * (B - T); }
    function f1(n) { return n.toFixed(1); }
    function path(points) {   // [[t, v]...] -> svg points; videos land on a day, so a count steps up instead of sloping
      var o = [], prev = null;
      points.forEach(function (q) { var x = X(q[0]), y = Y(q[1]); if (steps && prev) o.push(f1(x) + "," + f1(prev)); o.push(f1(x) + "," + f1(y)); prev = y; });
      return o.join(" ");
    }
    // achieved: rises from zero the day before the first data, so a single day still draws a line
    var pts = data.length ? [{ t: data[0].t - 86400, v: 0 }].concat(data) : [];
    pts = pts.filter(function (q) { return q.t <= now + 86400; });
    if (pts.length) pts.push({ t: Math.max(now, pts[pts.length - 1].t), v: pts[pts.length - 1].v });
    var line = path(pts.map(function (q) { return [q.t, q.v]; }));
    var col = TV_COL[item.actual >= item.goal ? "good" : item.grade] || TV_COL.low;
    var arr = paceArr(item), pp;
    if (arr && arr.length) {
      var a2 = arr.map(function (q) { return [q[0], item.goal * q[1]]; });
      if (a2[0][0] > t0) a2.unshift([t0, 0]);
      if (a2[a2.length - 1][0] < t1) a2.push([t1, a2[a2.length - 1][1]]);
      pp = path(a2);
    } else { steps = false; pp = path([[P.start, 0], [P.end, item.goal]]); }
    var area = pts.length > 1 ? "M" + f1(X(pts[0].t)) + "," + B + " L" + line.split(" ").join(" L") + " L" + f1(X(pts[pts.length - 1].t)) + "," + B + " Z" : "";
    var dots = data.length <= 16 ? data.filter(function (q) { return q.t <= now + 86400; }).map(function (q) { return '<circle cx="' + f1(X(q.t)) + '" cy="' + f1(Y(q.v)) + '" r="4.5" fill="' + col + '" stroke="#fff" stroke-width="2"/>'; }).join("") : "";
    var nx = X(now), anc = nx > Rr - 46 ? "end" : nx < L + 46 ? "start" : "middle";
    var attrs = ' data-w="' + W + '" data-h="' + H + '" data-l="' + L + '" data-r="' + Rr + '" data-t="' + T + '" data-b="' + B + '" data-t0="' + t0 + '" data-t1="' + t1 + '" data-ymax="' + ymax + '" data-now="' + now + '"';
    var svg = '<svg class="db-tv__svg" viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="' + esc(KEYN[item.key] + " achieved so far against the pace set by the publishing plan, target " + tvFmt(item.key, item.goal)) + '"' + attrs + ">"
      + '<line x1="' + L + '" y1="' + B + '" x2="' + Rr + '" y2="' + B + '" class="ax"/><line x1="' + L + '" y1="' + f1(Y(item.goal)) + '" x2="' + Rr + '" y2="' + f1(Y(item.goal)) + '" class="gl"/>'
      + '<polyline points="' + pp + '" class="pace" fill="none"/>'
      + (area ? '<path d="' + area + '" fill="' + col + '" opacity=".12"/>' : "") + (pts.length > 1 ? '<polyline points="' + line + '" fill="none" stroke="' + col + '" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>' : "") + dots
      + '<line x1="' + f1(nx) + '" y1="' + (T - 6) + '" x2="' + f1(nx) + '" y2="' + B + '" class="now"/><text x="' + f1(nx) + '" y="' + (T - 10) + '" text-anchor="' + anc + '" class="lb lb--now">Today</text>'
      + '<text x="' + Rr + '" y="' + f1(Y(item.goal) - 6) + '" text-anchor="end" class="lb">Target ' + esc(tvFmt(item.key, item.goal)) + "</text>"
      + '<text x="' + L + '" y="' + (H - 8) + '" class="lb">' + esc(day(t0)) + '</text><text x="' + Rr + '" y="' + (H - 8) + '" text-anchor="end" class="lb">' + esc(day(t1)) + "</text>"
      + '<line class="cur" x1="0" y1="' + T + '" x2="0" y2="' + B + '" style="display:none"/><circle class="dot" r="6" cx="0" cy="0" data-c="' + col + '" fill="' + col + '" stroke="#fff" stroke-width="2" style="display:none"/></svg>';
    var last = pts.length ? pts[pts.length - 1].v : 0, ahead = item.expected != null ? last - item.expected : null;
    var read = esc(KEYN[item.key]) + ": <b>" + esc(tvFmt(item.key, last)) + "</b> so far"
      + (ahead == null ? "" : ahead >= 0 ? " · " + esc(tvFmt(item.key, ahead)) + " ahead of the pace" : " · " + esc(tvFmt(item.key, -ahead)) + " behind the pace");
    return '<div class="db-tv__chart" tabindex="0" role="group" aria-label="' + esc(KEYN[item.key] + " pace chart. Use the left and right arrow keys to read each day.") + '" data-k="' + item.key + '" data-f="' + ((now - t0) / span).toFixed(4) + '" data-i="'
      + esc(JSON.stringify(pts.map(function (q) { return [Math.round(q.t), q.v]; }))) + '">' + svg
      + '<p class="db-tv__read" aria-live="polite">' + read + '</p><p class="db-tv__key"><span><i class="ln" style="background:' + col + '"></i>Achieved so far</span><span><i class="ln dash"></i>Pace set by the publishing plan</span><span><i class="ln now"></i>Today</span></p></div>';
  }
  function bindTV() {
    var box = $("db-tv"); if (!box) return;
    requestAnimationFrame(function () { requestAnimationFrame(function () { box.classList.add("is-in"); }); });
    var items = {}; (SP().items || []).forEach(function (i) { items[i.key] = i; });
    box.addEventListener("click", function (e) {
      var b = e.target.closest(".db-tv__btn:not(.db-tv__btn--static)"); if (!b) return;
      var row = b.parentNode, pace = row.querySelector(".db-tv__pace"), open = b.getAttribute("aria-expanded") === "true";
      box.querySelectorAll(".db-tv__btn[aria-expanded=true]").forEach(function (o) { if (o !== b) { o.setAttribute("aria-expanded", "false"); o.parentNode.querySelector(".db-tv__pace").hidden = true; } });
      b.setAttribute("aria-expanded", open ? "false" : "true");
      pace.hidden = open;
      // drawn once visible, at the width it will be shown at
      if (!open && !pace.firstChild) pace.innerHTML = tvPace(items[row.getAttribute("data-k")], pace.clientWidth - 28);
    });
    // hover, touch or arrow keys over a pace chart read the value on that day
    function readAt(chart, frac) {
      var pts = JSON.parse(chart.getAttribute("data-i")), svg = chart.querySelector("svg"), k = chart.getAttribute("data-k"), it = items[k], G = paceGeom(svg);
      frac = Math.min(1, Math.max(0, frac));
      var t = G.t0 + frac * (G.t1 - G.t0), future = t > G.now + 43200, v = 0;
      pts.forEach(function (q) { if (q[0] <= t) v = q[1]; });
      var pf = paceFrac(it, t), pace = it.goal * (pf == null ? frac : pf), x = G.l + frac * (G.r - G.l);
      var y = G.b - (future ? pace : v) / G.ymax * (G.b - G.t), cur = svg.querySelector(".cur"), dot = svg.querySelector(".dot");
      cur.setAttribute("x1", x); cur.setAttribute("x2", x); cur.style.display = ""; dot.setAttribute("cx", x); dot.setAttribute("cy", y); dot.style.display = "";
      dot.setAttribute("fill", future ? "#fff" : dot.getAttribute("data-c")); dot.setAttribute("stroke", future ? "#1b1b1b" : "#fff");
      chart.setAttribute("data-f", frac);
      chart.querySelector(".db-tv__read").innerHTML = esc(day(Math.round(t))) + (future ? ": pace " + esc(tvFmt(k, pace)) + " <span class=\"db-dim\">· not reached yet</span>"
        : ": <b>" + esc(tvFmt(k, v)) + "</b> achieved · pace " + esc(tvFmt(k, pace)));
    }
    function fromPointer(chart, e) {
      var svg = chart.querySelector("svg"), G = paceGeom(svg), r = svg.getBoundingClientRect(), x = (e.clientX - r.left) * (G.w / r.width);
      return (x - G.l) / (G.r - G.l);
    }
    box.addEventListener("pointermove", function (e) { var chart = e.target.closest(".db-tv__chart"); if (chart) readAt(chart, fromPointer(chart, e)); });
    box.addEventListener("pointerdown", function (e) { var chart = e.target.closest(".db-tv__chart"); if (chart) readAt(chart, fromPointer(chart, e)); });
    box.addEventListener("focusin", function (e) { var chart = e.target.classList && e.target.classList.contains("db-tv__chart") ? e.target : null; if (chart && !chart.querySelector(".cur").style.display) readAt(chart, +chart.getAttribute("data-f")); });
    box.addEventListener("keydown", function (e) {
      var chart = e.target.closest && e.target.closest(".db-tv__chart"); if (!chart || ["ArrowLeft", "ArrowRight", "Home", "End"].indexOf(e.key) < 0) return;
      var G = paceGeom(chart.querySelector("svg")), day1 = 86400 / Math.max(1, G.t1 - G.t0), f = +chart.getAttribute("data-f");
      f = e.key === "Home" ? 0 : e.key === "End" ? 1 : f + (e.key === "ArrowRight" ? day1 : -day1);
      readAt(chart, f); e.preventDefault();
    });
  }

  // "On pace for X – Y": the low end keeps today's average per video, the high end has the videos still to come
  // match what creators of their size typically get.
  function forecastBox() {
    var g = GL(), FC = g && g.forecast; if (!FC) return "";
    var VW = { ahead: ["good", "Ahead"], ontrack: ["good", "On track"], behind: ["low", "Behind"] };
    var tip = "Where the campaign is heading by the end. Low end: the videos still to come do as well as the average so far. High end: they reach what creators of their size typically get.";
    if (!FC.live) return sec("forecast", "Forecast to the end", tip, '<p class="db-empty">The forecast appears once the first videos are live.</p>');
    var cards = [["views", "Views"], ["engagement", "Engagement"]].filter(function (k) { return FC[k[0]]; }).map(function (k) {
      var f = FC[k[0]], v = VW[f.verdict] || VW.behind, top = Math.max(f.high, f.target) * 1.1 || 1, lo = f.low / top * 100, hi = f.high / top * 100, tg = f.target / top * 100;
      return '<div class="db-fc"><div class="db-fc__h"><b>' + k[1] + "</b>" + stPill(v[0], v[1]) + "</div>"
        + '<div class="db-fc__big">' + (f.low === f.high ? num(f.low) : num(f.low) + " – " + num(f.high)) + "</div>"
        + '<div class="db-fc__sub">on pace by the end · target ' + num(f.target) + "</div>"
        + '<div class="db-fc__bar" role="img" aria-label="' + esc(k[1] + " forecast " + num(f.low) + " to " + num(f.high) + ", target " + num(f.target)) + '"><i class="db-fc__band db-fc__band--' + v[0] + '" style="left:' + lo.toFixed(1) + "%;width:" + Math.max(1.5, hi - lo).toFixed(1) + '%"></i><em style="left:' + tg.toFixed(1) + '%"><u>target</u></em></div></div>';
    }).join("");
    return sec("forecast", "Forecast to the end", tip, '<div class="db-fcs">' + cards + "</div>"
      + (FC.early ? '<p class="db-flag">Early estimate: based on ' + FC.live + " of " + FC.planned + " videos so far. It firms up as more go live.</p>" : ""));
  }

  var SW = { met: ["good", "Met"], close: ["moderate", "Close"], behind: ["low", "Behind"], ontrack: ["good", "On track"] };
  function platChip(p) { return '<span class="db-pc">' + (ICONS[p.platform] || "") + "<b>" + num(p.followers) + "</b></span>"; }
  // Item 217: a creator's results count on every platform they posted on; the line under the result says where.
  function bySplit(c) {
    var sp = c.by_platform || [];
    if (!sp.length || (sp.length === 1 && sp[0].booked)) return "";
    return '<span class="db-cb__split">' + sp.map(function (p) {
      return '<span class="db-cb__sp' + (p.booked ? "" : " is-bonus") + '" title="' + esc(p.platform + ": " + num(p.views) + " views, " + num(p.engagement) + " engagement, " + p.videos + (p.videos === 1 ? " video" : " videos") + (p.booked ? "" : " (not booked here, still counted)")) + '">'
        + (ICONS[p.platform] || "") + "<b>" + num(p.views) + "</b>" + (p.booked ? "" : "<i>+</i>") + "</span>";
    }).join("") + "</span>";
  }
  // One row per creator: their size, what creators like them typically get per video, and what they got.
  function creatorBench() {
    var g = GL(); if (!g || !g.creators.length) return "";
    var rows = g.creators.map(function (c) {
      var soon = !c.live, st = c.status && SW[c.status], when = c.next && c.next.at ? day(c.next.at) : "";
      var res = soon ? '<span class="db-cb__soon">Coming soon · ' + (when ? esc(when) : "date to be confirmed") + "</span>"
        : '<strong>' + num(c.views_per_video) + "</strong><small>views per video" + (bySplit(c) ? ", all platforms" : "") + "</small>" + bySplit(c);
      var link = who({ code: c.code, name: c.name });
      return '<div class="db-cb__row' + (soon ? " is-soon" : "") + '"><div class="db-cb__who">' + ava(c.photo) + "<span><b>" + link + "</b><small>" + (c.live || 0) + " of " + (c.planned || "?") + ((c.planned || 0) === 1 ? " video live" : " videos live") + "</small></span></div>"
        + '<div class="db-cb__size"><span class="db-cb__lbl">Followers</span><span class="db-cb__chips">' + c.platforms.map(platChip).join("") + "</span><small>" + esc(c.size) + "</small></div>"
        + '<div class="db-cb__exp"><span class="db-cb__lbl">Typical per video</span><b>' + (c.exp_views ? esc(num(c.exp_views[0]) + " – " + num(c.exp_views[1])) : "—") + "</b><small>views</small></div>"
        + '<div class="db-cb__act"><span class="db-cb__lbl">This campaign</span>' + res + "</div>"
        + '<div class="db-cb__st">' + (st ? stPill(st[0], st[1]) : soon ? '<span class="db-st db-st--none">Not live yet</span>' : "") + "</div></div>";
    }).join("");
    return subsec("Creator by creator", "Typical per video is what creators of that size usually get on these platforms: the low end is what we commit to, the high end is what we aim for.", '<div class="db-cb">' + rows + "</div>");
  }
  function platformSplit() {
    var g = GL(); if (!g || !g.split.length) return "";
    var goals = g.split.filter(function (p) { return p.goal; }), extra = g.split.filter(function (p) { return !p.goal; });
    function line(label, got, safe, aim, status) {
      var st = SW[status] || SW.behind, col = TV_COL[st[0]];
      if (!safe) return '<div class="db-ps__l"><span class="db-ps__lb">' + label + '</span><span class="db-ps__n"><strong>' + num(got) + "</strong></span></div>";
      var w = Math.min(100, got / safe * 100);
      return '<div class="db-ps__l"><span class="db-ps__lb">' + label + '</span><span class="db-ps__n"><strong>' + num(got) + "</strong> of " + num(safe) + '</span><span class="db-ps__bar" role="img" aria-label="' + esc(label + " " + num(got) + " of " + num(safe) + ", " + st[1]) + '"><i style="width:' + w.toFixed(1) + "%;background:" + col + '"></i></span>'
        + stPill(st[0], st[1]) + "<small>Typical range " + num(safe) + " – " + num(aim) + "</small></div>";
    }
    var sel = F.platform || "";
    var cards = goals.map(function (p) {
      return '<div class="db-ps' + (sel === p.platform ? " is-sel" : sel ? " is-dim" : "") + '"><div class="db-ps__h">' + (ICONS[p.platform] || "") + "<b>" + esc(p.platform) + "</b><small>" + (p.videos ? p.videos + (p.videos === 1 ? " video live" : " videos live") : "Nothing posted yet") + "</small></div>"
        + line("Views", p.views, p.views_safe, p.views_aim, p.views_status) + line("Engagement", p.engagement, p.eng_safe, p.eng_aim, p.eng_status) + "</div>";
    }).join("");
    if (extra.length) {
      var v = 0, e = 0; extra.forEach(function (p) { v += p.views; e += p.engagement; });
      cards += '<div class="db-ps db-ps--add' + (sel && !goals.some(function (p) { return p.platform === sel; }) ? " is-sel" : sel ? " is-dim" : "") + '"><div class="db-ps__h"><b>Bonus platforms</b><span class="db-st db-st--none">No goal set</span></div>'
        + extra.map(function (p) { return '<p class="db-ps__add">' + (ICONS[p.platform] || "") + "<b>" + esc(p.platform) + "</b><span><strong>" + num(p.views) + "</strong> views · <strong>" + num(p.engagement) + "</strong> engagement · " + p.videos + (p.videos === 1 ? " video" : " videos") + "</span></p>"; }).join("")
        + (extra.length > 1 ? '<p class="db-ps__add db-ps__add--tot"><b>Total</b><span><strong>' + num(v) + "</strong> views · <strong>" + num(e) + "</strong> engagement</span></p>" : "") + "</div>";
    }
    return sec("platforms", "Platform split", "Views and engagement on each platform the goals were set for, against what is typical there. Bonus platforms are tracked too, but have no goal and do not count towards the targets or the All targets %.",
      '<div class="db-pss' + (goals.length + (extra.length ? 1 : 0) === 1 ? " db-pss--one" : "") + '">' + cards + "</div>");
  }
  function stillToCome() {
    var g = GL(); if (!g) return "";
    var tip = "The videos not yet published, with the planned date when one is set.";
    if (!g.owed.length) return g.creators.some(function (c) { return c.planned; }) ? sec("owed", "Still to come", tip, '<p class="db-empty">Every planned video is live.</p>') : "";
    var by = {}; (R.creators || []).forEach(function (c) { by[c.code] = c; });
    return sec("owed", "Still to come", tip, '<div class="db-owed">' + g.owed.map(function (o) {
      var c = by[o.code] || {};
      return '<div class="db-owed__r">' + ava(c.photo) + "<span><b>" + esc(o.name) + "</b><small>Video " + o.n + " of " + o.of + "</small></span><em>"
        + (o.at ? esc(day(o.at)) + (o.confirmed ? "" : " <small>planned</small>") : "Date to be confirmed") + "</em></div>";
    }).join("") + "</div>", g.owed.length + (g.owed.length === 1 ? " video" : " videos"));
  }
  function dataNotes() {
    var g = GL(); if (!g || !g.notes.length) return "";
    return sec("notes", "Data notes", "Only the things that change how to read the numbers above.", '<ul class="db-dn">' + g.notes.map(function (n) { return "<li>" + esc(n) + "</li>"; }).join("") + "</ul>");
  }

  // What the tab is showing, in one line, when the page's platform filter changes it.
  function scopeNote(sc) {
    var ic = sc.pl ? (ICONS[sc.pl] || "") : "";
    if (sc.mode === "plat") return '<p class="db-scope" role="status">' + ic + "<span>Showing <b>" + esc(sc.pl) + "</b> only: its own targets and results, from the start of the campaign. Choose All for every goal platform together.</span></p>";
    if (sc.mode === "whole") return '<p class="db-scope" role="status">' + ic + "<span>This campaign has one set of targets for all its platforms, so it is shown whole.</span></p>";
    return "";
  }
  // A platform the goals were not set for: no targets to measure, only what it brought as a bonus.
  function bonusCard(pl) {
    var list = R.posts.filter(function (p) { return p.section === "campaign" && p.platform === pl; }), pcs = {};
    list.forEach(function (p) { pcs[p.pk || p.id] = 1; });
    var v = list.reduce(function (a, p) { return a + (p.views || 0); }, 0), e = list.reduce(function (a, p) { return a + (p.engagement || 0); }, 0), n = Object.keys(pcs).length;
    return '<section class="db-sec db-bonus" aria-labelledby="sec-bonus"><header class="db-sec__h"><h3 class="db-sec__t" id="sec-bonus">Bonus platform: ' + esc(pl) + "</h3></header>"
      + '<p class="db-bonus__msg">' + (ICONS[pl] || "") + "<span>No goal on " + esc(pl) + "; its numbers count as bonus.</span></p>"
      + '<div class="db-bonus__nums"><div><span>Views</span><b>' + num(v) + "</b></div><div><span>Engagement</span><b>" + num(e) + "</b></div><div><span>Videos</span><b>" + n + "</b></div></div></section>";
  }

  var PANEL = {
    kpi: function () {
      var sc = scope(), P = SP() || {}, items = P.items || [], t = R.total, plan = R.plan || {}, pb = sc.mode === "plat" ? (sc.bp.bench || {}) : (plan.benchmark || {}), g = GL();
      var o = R.objective || {}, lead = o.kpis || [];
      var plats = sc.mode === "plat" ? [sc.pl] : planPlats();
      var head = '<div class="db-goal-sum" role="group" aria-label="Summary"><div><span>' + (sc.mode === "plat" ? esc(sc.pl) + " targets" : "All targets") + '</span><b>' + (items.length ? Math.round(P.all_met ? 100 : Math.min(99, P.overall || 0)) + "%" : "—") + '</b><small>' + (!items.length ? "No targets set yet" : P.all_met ? "Every target met" : "100% only when every target is met") + "</small></div>"
        + "<div><span>Objective</span><b>" + esc(o.label || "Balanced") + "</b><small>" + esc(lead.map(function (k) { return KEYN[k]; }).join(" & ")) + " lead</small></div>"
        + (plats.length ? "<div><span>Benchmarked for</span><b class=\"db-goal-plat\">" + plats.map(function (p) { return '<span class="db-goal-plat__p"><span class="db-goal-plat__ic" style="color:' + (PCOL[p] || "#121212") + '">' + (ICONS[p] || "") + "</span><i>" + esc(p) + "</i></span>"; }).join("") + "</b><small>" + esc(plan.category || plan.template || "") + "</small></div>" : "") + "</div>";
      var out = head + scopeNote(sc);
      if (sc.mode === "bonus") return out + bonusCard(sc.pl) + platformSplit() + dataNotes();
      out += objectiveBox() + tvInfographic(items, lead) + forecastBox();
      // Benchmarks as gauges: the shaded band is the normal range for these
      // creators, the dot is where the campaign is now.
      function gauge(label, unit, band, now, grade) {
        if (!band) return "";
        var top = Math.max(band[1] * 1.35, (now || 0) * 1.1) || 1, l = band[0] / top * 100, w = (band[1] - band[0]) / top * 100;
        var dot = now != null ? '<i class="db-gauge__dot ' + (grade || "") + '" style="left:' + Math.min(100, now / top * 100).toFixed(1) + '%"><span>' + now.toFixed(now < 10 ? 2 : 1) + "%</span></i>" : "";
        return '<div class="db-gauge"><div class="db-gauge__lbl"><b>' + label + "</b><small>" + unit + '</small></div><div class="db-gauge__bar"><i class="db-gauge__band" style="left:' + l.toFixed(1) + "%;width:" + w.toFixed(1) + '%"></i>' + dot
          + '<em style="left:' + l.toFixed(1) + '%">' + band[0] + '%</em><em style="left:' + (l + w).toFixed(1) + '%">' + band[1] + "%</em></div>"
          + '<div class="db-gauge__sig">' + (now != null ? sig(grade) : '<span class="db-na">Not measured yet</span>') + "</div></div>";
      }
      // Only the platforms the goals were set for feed the gauges; add-ons are tracked beside them.
      var vids = goalPosts().filter(function (p) { return p.view_rate != null; });
      var vrNow = vids.length ? vids.reduce(function (a, p) { return a + p.view_rate; }, 0) / vids.length : null;
      var erNow = sc.mode === "plat" ? sc.bp.now.er : t.video_er != null ? t.video_er : t.er;
      function gr(v, b) { return v == null ? null : v >= b[1] ? "good" : v >= b[0] ? "moderate" : "low"; }
      var links = (R.objective || {}).links;
      var gauges = pb.view_rate ? '<div class="db-gauges">'
        + gauge("Views per video", "% of followers", pb.view_rate, vrNow, gr(vrNow, pb.view_rate))
        + gauge("Engagement rate", "% of views", pb.eng_rate, erNow, erGoal() ? goalGrade(erNow) : gr(erNow, pb.eng_rate))
        + (links && pb.ctr && sc.mode !== "plat" ? gauge("Click-through", "% of views", pb.ctr, t.ctr, gr(t.ctr, pb.ctr)) : "")
        + '</div><div class="db-legend2"><span><i class="sw band"></i>Normal range for creators this size</span><span><i class="dot"></i>This campaign now</span></div>' : "";
      var cb = creatorBench();
      if (gauges || cb) out += sec("bench", "Benchmarks for these creators", "What creators of these sizes typically get on these platforms. The shaded range is normal, the dot is where this campaign is now. The low end of a range is what we commit to, the high end is what we aim for.", gauges + cb);
      return out + platformSplit() + stillToCome() + dataNotes();
    },
    trend: function () {
      var s = series(posts()), useHist = !filtered() && R.history && R.history.length > 1;
      var pts = fromStart(useHist ? R.history.map(function (d) { return { d: d.d, views: d.views, eng: d.engagement != null ? d.engagement : d.likes + d.comments }; }) : s);
      return "<h3>Views & engagement over time</h3><div class=\"db-trendbox\">" + areaChart(pts, "views", "eng", panelW(), 240) + "</div>"
        + '<h3>Day by day</h3><table class="db-table"><thead><tr><th>Day</th><th></th><th>Views</th><th>Engagement</th></tr></thead><tbody>'
        + pts.map(function (d) { return "<tr><td>" + esc(day(d.d, true)) + "</td><td></td><td>" + full(d.views) + "</td><td>" + full(d.eng) + "</td></tr>"; }).join("") + "</tbody></table>";
    },
    creators: function () {
      var list = posts(), by = {}; list.forEach(function (p) { var x = by[p.code] = by[p.code] || { posts: 0, views: 0, reach: 0, eng: 0, keys: {} }; if (!x.keys[pieceKey(p)]) { x.keys[pieceKey(p)] = 1; x.posts++; } x.views += p.views || 0; x.reach += p.reach || 0; x.eng += p.engagement || 0; });
      var rows = filtered() ? ranked(list).map(function (r) { return r.c; }) : R.creators;
      var tot = rows.reduce(function (a, c) { var x = filtered() ? (by[c.code] || {}) : { views: c.views, eng: c.engagement }; a.v += x.views || 0; a.e += x.eng || 0; return a; }, { v: 0, e: 0 });
      function share(v, t) { return t ? Math.round((v || 0) / t * 100) + "%" : "—"; }
      return '<h3 style="margin-top:0">How creators are scored · out of 100</h3>' + scoreBar() + '<table class="db-table"><thead><tr><th>#</th><th>Creator</th><th>Posts</th><th>Views</th>' + (R.visibility.reach === false ? "" : "<th>Reach</th>") + '<th>Eng.</th><th>% of views</th><th>% of eng.</th><th>ER</th>' + (R.visibility.clicks && R.objective.links ? "<th>Clicks</th>" : "") + "<th>Score</th></tr></thead><tbody>"
        + rows.map(function (c, i) { var x = filtered() ? (by[c.code] || {}) : { posts: c.delivered, views: c.views, reach: c.reach, eng: c.engagement };
          var n = filtered() ? i + 1 : c.rank;
          return '<tr' + (n && n <= 3 ? ' class="is-top"' : "") + "><td>" + (n && n <= 3 ? '<span class="db-medal">' + medal(n) + "</span>" : (n || "—")) + '</td><td><span class="db-who">' + ava(c.photo) + "<b>" + who(c) + "</b></span></td><td>" + (x.posts || 0) + (c.planned && !filtered() ? "/" + c.planned : "") + "</td><td>" + num(x.views) + (R.visibility.reach === false ? "" : "</td><td>" + num(x.reach)) + "</td><td>" + num(x.eng)
            + "</td><td>" + share(x.views, tot.v) + "</td><td>" + share(x.eng, tot.e) + "</td><td>" + pct(c.video_er != null ? c.video_er : c.er) + "</td>" + (R.visibility.clicks && R.objective.links ? "<td>" + full(c.clicks) + "</td>" : "") + "<td>" + (filtered() && viewScore[c.code] != null ? scoreTxt(viewScore[c.code]) : scoreTxt(c.score)) + "</td></tr>"; }).join("")
        + '</tbody></table><p class="db-note" style="margin-top:10px">' + esc(scoreTip()) + "</p>" + videosByCreator(list, rows)
        + (filtered() ? "" : '<h3>Score breakdown</h3><table class="db-table"><thead><tr><th>Creator</th><th>Views</th><th>Engagement</th>' + (weights().er > 0 ? "<th>Eng. rate</th>" : "") + '' + (weights().clicks > 0 ? "<th>Clicks</th>" : "") + '<th>Score</th></tr></thead><tbody>'
          + R.creators.filter(function (c) { return c.parts; }).map(function (c) { var q = c.parts; return "<tr><td>" + esc(c.name) + "</td><td>" + q.exposure.toFixed(0) + "</td><td>" + q.engagement.toFixed(0) + "</td>" + (weights().er > 0 ? "<td>" + q.er.toFixed(0) + "</td>" : "") + (weights().clicks > 0 ? "<td>" + q.clicks.toFixed(0) + "</td>" : "") + "<td><b>" + scoreTxt(c.score) + "</b></td></tr>"; }).join("")
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
      return creatorWalls(list);
    },
    geo: function () {
      var C = R.comments, t = cmPick();
      if (!C || !t.n) return cmWait(C || { status: "none" });
      var share = t.intent / t.n, p = t.pos / t.n, z = t.neg / t.n, th = cmTop(t.themes);
      var mood = z >= 0.3 ? "Viewers are divided" : p >= 0.6 ? "Viewers are warm" : share >= 0.3 ? "Viewers are mostly asking questions" : "Viewers are mostly neutral";
      var buy = share >= 0.15 ? ", and <mark>1 in " + Math.max(2, Math.round(1 / share)) + " wants to buy</mark>" : share >= 0.04 ? ", and some ask how to buy" : ", and few ask about buying";
      var verdict = t.small ? "Only " + t.n + " comments so far: too few to judge." : mood + buy + (th[0] ? ". The talk is mostly about <mark>" + esc(th[0].toLowerCase()) + "</mark>." : ".");
      var asks = cmTop(t.asks, "n").slice(0, 6), apeak = asks.length ? t.asks[asks[0]].n : 1;
      var names = {}, pics = {}; (R.creators || []).forEach(function (c) { names[c.code] = c.name; pics[c.code] = c.photo; });
      var quotes = (C.quotes || []).filter(function (q) { return (!F.platform || q.platform === F.platform) && (!F.creators.length || F.creators.indexOf(q.code) >= 0); });
      var who = Object.keys(t.by).sort(function (a, b) { return t.by[b].n - t.by[a].n; });
      var silent = (R.creators || []).filter(function (c) { return !t.by[c.code] && (!F.creators.length || F.creators.indexOf(c.code) >= 0); });
      var plats = cmTop(t.plats, "n");
      var TA = C.theme_asks || {}, AR = C.theme_ar || {};
      var ar = function (q) { return AR[q] ? '<span class="cm-ar" dir="rtl" lang="ar">' + esc(AR[q]) + "</span>" : ""; };
      var v = function (x, n) { var q = cmPct(x, n || t.n); return t.small ? x : (x && !q ? "<1%" : q + "%"); };
      var box = function (n, l, cls) { return '<div class="cmp-box' + (cls ? " " + cls : "") + '"><b>' + n + "</b><span>" + l + "</span></div>"; };
      var asksOf = function (q, k) { return (TA[q] || []).slice(0, k).map(function (a) {
        return '<span class="cmp-chip" title="' + esc(a[1] || "") + '"><q dir="auto">' + esc(a[0]) + "</q><b>×" + a[2] + "</b></span>"; }).join(""); };
      var mainT = th[0], restT = th.slice(1, 7), topA = cmTop(t.asks, "n")[0];
      // One line, the strongest finding first (owner: shorter, the insight highlighted).
      var head1 = t.small ? "Only " + t.n + " comments so far" : share >= 0.15 ? "<mark>1 in " + Math.max(2, Math.round(1 / share)) + " want to buy</mark>"
        : z >= 0.3 ? "<mark>Viewers are divided</mark>" : p >= 0.6 ? "<mark>Viewers love it</mark>" : "<mark>Mostly neutral</mark>";
      var sub1 = topA ? 'Most ask <q dir="auto">' + esc(topA) + "</q>" + (t.asks[topA].en ? " (" + esc(t.asks[topA].en.replace(/\?$/, "")) + ")" : "") + " · " + t.asks[topA].n + " times"
        : mainT ? "The talk is mostly about " + esc(mainT.toLowerCase()) : "";
      return cmSections('<section class="cmp-top"><div class="cmp-boxes">'
        + box(full(t.n), "comments read") + box(v(t.intent), "ask how to buy", "is-hot " + (t.small ? "" : cmTone("buy", share))) + box(v(t.pos), "positive", t.small ? "" : cmTone("pos", p)) + box(t.videos, "video" + (t.videos === 1 ? "" : "s"))
        + '</div><aside class="cmp-say" aria-label="The insight from the comments"><img class="cmp-say__av" src="../../assets/brand/helvy-connect/helvy-icon-180.png" alt="" width="48" height="48">'
        + '<div class="cmp-say__b"><p class="cmp-say__k">Helvi read the comments</p><p class="cmp-say__t">' + head1 + "</p>" + (sub1 ? '<p class="cmp-say__s">' + sub1 + "</p>" : "")
        + (C.next_read || C.last_read ? '<p class="cmp-say__d">' + (C.last_read ? "Read " + cmDay(C.last_read) : "") + (C.next_read ? (C.last_read ? " · " : "") + "next read " + cmDay(C.next_read) : "") + "</p>" : "")
        + "</div></aside></section>"
        + "<h3>The mood</h3>" + '<div class="cmp-mood">' + cmRing(t, "cm-ring--hero") + '<div class="cmp-mood__k">'
        + cmParts(t).map(function (s) { var n = t[s[0]]; return '<div class="cmp-mood__r" style="--c:' + CM_COL[s[0]] + '">' + '<i class="cm-face">' + CM_FACE[s[0]] + '</i><b>' + (t.small ? n : s[1] + "%") + "</b><span>" + s[2] + "</span><small><em>" + full(n) + "</em> comments</small></div>"; }).join("")
        + "</div></div>"
        + (plats.length ? "<h3>Where the comments came from</h3>" + '<div class="cmp-src">' + cmShare(plats, t) + '<div class="cmp-plats">' + plats.map(function (k) { var x = t.plats[k]; x.small = x.n < 30;
            return '<div class="cmp-plat" style="--pc:' + (PCOL[k] || "#121212") + '"><p class="cmp-plat__n">' + (ICONS[k] || "") + "<b>" + esc(k) + "</b><em>" + cmPct(x.n, t.n) + "%</em></p>" + cmRing(x, "cm-ring--plat")
              + '<p class="cmp-plat__s"><span><b>' + full(x.n) + "</b>comments</span><span class=\"" + (x.small ? "" : cmTone("buy", x.intent / x.n)) + "\"><b>" + cmPct(x.intent, x.n) + "%</b>ask to buy</span></p></div>"; }).join("") + "</div></div>" : "")
        + (mainT ? "<h3>What people talk about</h3>" + '<div class="cmp-insight"><span class="cmp-insight__ic">' + cmIcon(mainT) + '</span><div class="cmp-insight__b">'
            + '<p class="cmp-insight__k">The biggest topic · <b>' + v(t.themes[mainT]) + "</b> of comments</p><p class=\"cmp-insight__t\">" + esc(mainT) + "</p>" + (AR[mainT] ? '<p class="cmp-insight__ar" dir="rtl" lang="ar">' + esc(AR[mainT]) + "</p>" : "")
            + ((TA[mainT] || []).length ? '<p class="cmp-insight__l">What they ask about it</p><div class="cmp-chips">' + asksOf(mainT, 4) + "</div>" : "") + "</div></div>"
            + (restT.length ? '<div class="cmp-tl">' + restT.map(function (q) {
                return '<details class="cmp-tl__r" style="--w:' + (t.themes[q] / t.themes[mainT] * 100).toFixed(1) + '%"><summary><span class="cmp-tl__ic">' + cmIcon(q) + '</span><span class="cmp-tl__t"><b>' + esc(q) + "</b>"
                  + (AR[q] ? '<span class="cmp-tl__ar" dir="rtl" lang="ar">' + esc(AR[q]) + "</span>" : "") + '</span><span class="cmp-tl__bar"><i></i></span><span class="cmp-tl__p">' + v(t.themes[q]) + "</span>"
                  + '<span class="cmp-tl__n">' + full(t.themes[q]) + "<small>comments</small></span><span class=\"cmp-tl__chev\" aria-hidden=\"true\"></span></summary><div class=\"cmp-tl__body\">"
                  + ((TA[q] || []).length ? '<p class="cmp-tl__l">What they ask</p><div class="cmp-chips">' + asksOf(q, 4) + "</div>" : "")
                  + '<p class="cmp-tl__l">What they say</p><div class="cmp-tl__s" data-theme="' + esc(q) + '"><p class="cmb__load">Loading the comments…</p></div></div></details>'; }).join("") + "</div>" : "")
            + (plats.length > 1 ? "<h3>Which topics come from which platform</h3>" + (function () { var list = th.slice(0, 7), mx = 1;
                list.forEach(function (q) { plats.forEach(function (k) { mx = Math.max(mx, (t.tp[q] || {})[k] || 0); }); });
                return '<div class="cmp-heat" style="--cols:' + plats.length + '"><span></span>' + plats.map(function (k) { return '<span class="cmp-heat__h">' + (ICONS[k] || "") + "<small>" + esc(k) + "</small></span>"; }).join("")
                  + list.map(function (q) { return '<span class="cmp-heat__r">' + cmIcon(q) + "<span>" + esc(q) + ar(q) + "</span></span>" + plats.map(function (k) { var n = (t.tp[q] || {})[k] || 0, f = n / mx;
                      return '<span class="cmp-heat__c' + (f > .55 ? " is-hot" : "") + '" style="--a:' + (n ? (0.1 + 0.9 * f).toFixed(2) : 0) + '" title="' + esc(q) + " · " + esc(k) + ": " + n + ' comments">' + (n || "") + "</span>"; }).join(""); }).join("") + "</div>"; })() : "") : "")
        + (asks.length ? "<h3>What buyers asked</h3>" + (function () { var all = cmTop(t.asks, "n"), top = all.slice(0, 8), more = all.slice(8, 22), mx = t.asks[all[0]].n;
            return '<ol class="cmp-rank">' + top.map(function (q, i) { var n = t.asks[q].n;
                return '<li style="--w:' + (n / mx * 100).toFixed(1) + '%"' + (i ? "" : ' class="is-1"') + '><span class="cmp-rank__i">' + (i + 1) + '</span><span class="cmp-rank__q"><q dir="auto">' + esc(q) + "</q><small>" + esc(t.asks[q].en || "") + '</small></span><b>' + n + "</b></li>"; }).join("") + "</ol>"
              + (more.length ? '<p class="cmp-rank__more"><span>Also asked</span>' + more.map(function (q) { return '<span class="cmp-chip" title="' + esc(t.asks[q].en || "") + '"><q dir="auto">' + esc(q) + "</q><b>×" + t.asks[q].n + "</b></span>"; }).join("") + "</p>" : ""); })() : "")
        + (Object.keys(t.days).length > 1 ? "<h3>Comments per day</h3>" + (function () { var ds = Object.keys(t.days).sort(), mx = Math.max.apply(null, ds.map(function (d) { return t.days[d]; })),
              pk = ds.filter(function (d) { return t.days[d] === mx; })[0], W = 640, H = 220, L = 24, Rr = 24, T = 34, B = 34;
            var pts = ds.map(function (d, i) { return [L + (ds.length === 1 ? 0 : i * (W - L - Rr) / (ds.length - 1)), T + (1 - t.days[d] / mx) * (H - T - B)]; });
            var line = cmCurve(pts), area = line + " L" + pts[pts.length - 1][0].toFixed(1) + " " + (H - B) + " L" + pts[0][0].toFixed(1) + " " + (H - B) + " Z";
            return '<div class="cmp-curve"><svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Comments per day: ' + ds.map(function (d) { return day(d) + " " + t.days[d]; }).join(", ") + '">'
              + '<defs><linearGradient id="cm-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff691e" stop-opacity=".22"/><stop offset="1" stop-color="#ff691e" stop-opacity=".02"/></linearGradient></defs>'
              + '<line x1="' + L + '" y1="' + (H - B) + '" x2="' + (W - Rr) + '" y2="' + (H - B) + '" stroke="#e6e2db" stroke-width="1.5"/>'
              + '<path class="cmp-curve__a" d="' + area + '" fill="url(#cm-fill)"/><path class="cmp-curve__l" d="' + line + '" fill="none" stroke="#ff691e" stroke-width="3.5" stroke-linecap="round"/>'
              + (function () {
                  // Many days (owner, 2026-10-20): numbers only on the top peaks, a date tick every few days,
                  // small dots; every day keeps its number in a hover title. Up to 12 days: every label, as before.
                  var n = ds.length, dense = n > 12, step = dense ? Math.ceil(n / 7) : 1, lab = {}, ticks = {};
                  if (dense) {
                    var gap = Math.max(2, Math.ceil(n / 6)), order = ds.map(function (d, i) { return i; })
                      .sort(function (a, b) { return t.days[ds[b]] - t.days[ds[a]]; });
                    order.forEach(function (i) {
                      if (Object.keys(lab).length >= 3) return;
                      if (Object.keys(lab).some(function (j) { return Math.abs(j - i) < gap; })) return;
                      lab[i] = 1;
                    });
                    for (var i = 0; i < n; i += step) ticks[i] = 1;
                    if (!ticks[n - 1]) { if ((n - 1) % step && (n - 1) % step < step * 0.8) delete ticks[(n - 1) - (n - 1) % step]; ticks[n - 1] = 1; }
                  }
                  return pts.map(function (p, i) { var d = ds[i], isPk = d === pk, showV = !dense || lab[i], showD = !dense || ticks[i];
                    return '<g class="cmp-curve__p' + (isPk ? " is-pk" : "") + (dense ? " is-dense" : "") + '"><title>' + day(d) + ": " + t.days[d] + " comments</title>"
                      + '<circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="' + (isPk ? (dense ? 6.5 : 8) : (dense ? 3 : 5.5)) + '"/>'
                      + (dense ? '<circle class="cmp-curve__hit" cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="' + Math.max(6, (W - L - Rr) / n / 2).toFixed(1) + '"/>' : "")
                      + (showV ? '<text x="' + p[0].toFixed(1) + '" y="' + (p[1] - (dense ? 12 : 14)).toFixed(1) + '" text-anchor="middle" class="cmp-curve__v">' + t.days[d] + "</text>" : "")
                      + (showD ? '<text x="' + p[0].toFixed(1) + '" y="' + (H - 10) + '" text-anchor="' + (dense && i === 0 ? "start" : dense && i === n - 1 ? "end" : "middle") + '" class="cmp-curve__d">' + day(d) + "</text>" : "")
                      + "</g>"; }).join("");
                })()
              + '</svg></div><p class="cmp-days__n">The conversation peaked on <b>' + day(pk) + "</b> with " + mx + " comments.</p>"; })() : "")
        + (quotes.length ? "<h3>In their words</h3>" + '<div class="cmp-quotes">' + quotes.map(function (q) {
            return '<article class="cmp-quote"><q dir="auto">' + esc(q.text) + "</q>" + ""
              + "<footer>" + ava(pics[q.code]) + "<b>" + esc(names[q.code] || q.code || "") + "</b><span>" + (ICONS[q.platform] || esc(q.platform)) + "</span></footer></article>"; }).join("") + "</div>" : "")
        + "<h3>By creator</h3>" + '<div class="cmp-who">' + who.map(function (c) { var w = t.by[c], few = w.n < ((C.min_sample) || 30), top = cmTop(w.themes)[0]; w.small = few;
            return '<div class="cmp-who__r">' + ava(pics[c]) + '<span class="cmp-who__n"><b>' + esc(names[c] || c) + "</b><small>" + w.plats.map(function (x) { return ICONS[x] || esc(x); }).join("") + "</small></span>"
              + cmRing(w, "cm-ring--who") + '<span class="cmp-who__c cmp-who__c--n"><b>' + full(w.n) + "</b><small>comments</small></span>"
              + '<span class="cmp-who__c cmp-who__c--b ' + (few ? "" : cmTone("buy", w.intent / w.n)) + '"><b>' + (few ? w.intent : cmPct(w.intent, w.n) + "%") + "</b><small>" + (few ? "of " + w.n + " ask" : "ask to buy") + "</small></span>"
              + '<span class="cmp-who__t">' + (few ? "<small>Too few to say</small>" : cmIcon(top) + "<span>" + esc(top || "—") + ar(top) + "</span>") + "</span></div>"; }).join("")
        + silent.map(function (c) { return '<div class="cmp-who__r is-quiet">' + ava(c.photo) + '<span class="cmp-who__n"><b>' + esc(c.name) + "</b></span><span class=\"cmp-who__wait\">" + (c.posts ? "Comments not read yet" : "No video yet") + "</span></div>"; }).join("")
        + "</div>"
        + "<h3>All comments</h3>" + '<div id="cmb" class="cmb"><p class="cmb__load">Loading the comments…</p></div>' + (setTimeout(cmBind, 0) && "")
        + "");
    },
    plat: function () {
      // One ledger row per platform, biggest first: its views and share of all views lead, a bar against the biggest
      // platform, then reach, engagement and engagement rate against what is typical there (same rule as the gauges).
      var by = {}, tot = 0;
      posts().forEach(function (p) {
        var x = by[p.platform] = by[p.platform] || { k: p.platform, posts: 0, views: 0, reach: 0, eng: 0, shown: 0 };
        x.posts++; x.reach += p.reach || 0; x.eng += p.engagement || 0;
        if (!p.views_hidden) { x.views += p.views || 0; x.shown++; }
      });
      var rows = Object.keys(by).map(function (k) { tot += by[k].views; return by[k]; }).sort(function (a, b) { return b.views - a.views; });
      if (!rows.length) return '<div class="db-na-card"><span class="db-na-card__icon">' + IC.plat + '</span><span class="db-na">Nothing posted yet</span><p>Each platform appears here with its views, reach and engagement once its first post is live.</p></div>';
      // reach only when a platform has some: reels and videos are counted by views, so a column of dashes says nothing
      var peak = rows[0].views || 1, showReach = R.visibility.reach !== false && rows.some(function (x) { return x.reach > 0; });
      function band(k) {
        var bp = R.goals && R.goals.by_platform && R.goals.by_platform[k];
        var v = (R.benchmarks || {}).video_er;       // the built-in guide, [good, moderate], when no plan sets a range
        return (bp && bp.bench && bp.bench.eng_rate) || ((R.plan || {}).benchmark || {}).eng_rate || (v && v.length === 2 ? [Math.min(v[0], v[1]), Math.max(v[0], v[1])] : null);
      }
      function share(x) { return tot && x.shown ? Math.round(x.views / tot * 100) : null; }
      var strip = '<div class="db-pl__strip" role="img" aria-label="' + esc(rows.map(function (x) { var s = share(x); return x.k + " " + (s == null ? "views not shown" : s + "% of views"); }).join(", ")) + '">'
        + rows.map(function (x) { var s = share(x); return s ? '<i data-p="' + esc(x.k) + '" style="flex:' + s + ";--c:" + (PCOL[x.k] || COL[0]) + '">' + (s >= 22 ? "<span>" + esc(x.k) + " " + s + "%</span>" : "") + "</i>" : ""; }).join("") + "</div>";
      var list = rows.map(function (x) {
        var s = share(x), er = x.shown && x.views ? x.eng / x.views * 100 : null, b = band(x.k);
        var grade = er == null ? null : erGoal() ? goalGrade(er) : !b ? null : er >= b[1] ? "good" : er >= b[0] ? "moderate" : "low";
        var c = PCOL[x.k] || COL[0];
        return '<article class="db-pl" style="--c:' + c + '">'
          + '<header class="db-pl__h"><span class="db-pl__ic" aria-hidden="true">' + (ICONS[x.k] || "") + '</span><span class="db-pl__nm"><b>' + esc(x.k) + "</b><small>" + x.posts + (x.posts === 1 ? " post" : " posts") + "</small></span>"
          + '<span class="db-pl__v">' + (x.shown ? "<b>" + num(x.views) + "</b><small>views" + (s != null ? " · " + s + "% of all" : "") + "</small>" : '<b class="db-pl__na">n/a</b><small>' + esc(x.k) + " does not show views</small>") + "</span></header>"
          + '<div class="db-pl__bar" aria-hidden="true"><i style="width:' + (x.shown ? Math.max(2, x.views / peak * 100) : 0).toFixed(1) + '%"></i></div>'
          + '<dl class="db-pl__st' + (showReach ? "" : " db-pl__st--2") + '">'
          + (showReach ? "<div><dt>Reach</dt><dd>" + (x.reach ? num(x.reach) : "—") + "</dd></div>" : "")
          + "<div><dt>Engagement</dt><dd>" + num(x.eng) + "</dd></div>"
          + "<div><dt>Eng. rate</dt><dd>" + pct(er) + (grade ? " " + sig(grade, "Typical on " + x.k + ": " + b[0] + "% – " + b[1] + "%") : "") + "</dd>"
          + (b ? "<small>Typical " + b[0] + "% – " + b[1] + "%</small>" : "") + "</div></dl></article>";
      }).join("");
      return (rows.length > 1 ? strip : "") + '<div class="db-pls">' + list + "</div>"
        + '<p class="db-note">Views count videos; reach counts photo posts and stories, so the two are never added together. Engagement rate is engagement ÷ views.</p>';
    },
    clicks: function () {
      if (R.sales && R.sales.totals) return salesPanel();
      var cl = clicksFor(); if (!cl) return '<div class="db-na-card"><span class="db-na-card__icon">' + IC.clicks + '</span><span class="db-na">Not part of this campaign</span><p>This campaign does not contain affiliate links, so there are no clicks to count.</p></div>';
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
    if (p.video) out.push(["Views", p.views_hidden ? '<span class="db-hid" title="This platform does not show view counts">Not shown</span>' : full(p.views)]);
    if (p.reach != null && !p.views_hidden) out.push([p.story ? "Story views" : "Reach" + (p.reach_real === false && !p.story ? " (est.)" : ""), full(p.reach)]);
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
  // All posts, grouped by creator (owner, 2026-10-19): a creator index on top, then each creator in leaderboard
  // order with their photo, profiles, totals, their posts and the videos they still owe.
  function pendingCard(c, n) {
    var pic = c.photo_large || c.photo;
    return '<div class="db-post db-post--pending"><div class="db-post__img">' + (pic ? '<img src="' + esc(pic) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : "")
      + '<span class="db-kind db-kind--pending">Pending</span></div><div class="db-post__body"><b>' + esc(c.name) + "</b><span>"
      + esc(c.pending_status || "Coming soon") + " · " + esc(c.pending_date ? day(c.pending_date) : "date to be confirmed")
      + " · video " + n + " of " + c.planned + "</span></div></div>";
  }
  function creatorWalls(list) {
    var by = {}; list.forEach(function (p) { (by[p.code] = by[p.code] || []).push(p); });
    var known = {}, order = (R.creators || []).slice().sort(function (a, b) {
      return (a.rank == null) - (b.rank == null) || (a.rank || 0) - (b.rank || 0) || (b.views || 0) - (a.views || 0); });
    order.forEach(function (c) { known[c.code] = 1; });
    Object.keys(by).forEach(function (k) { if (!known[k]) order.push({ code: k, name: by[k][0].creator, photo: by[k][0].photo, profiles: [] }); });
    var shown = order.filter(function (c) { return by[c.code] || (!filtered() && (c.planned || 0) > (c.delivered || 0)); });
    if (!shown.length) return '<p class="db-note">Nothing in this view yet.</p>';
    var nav = shown.length > 1 ? '<nav class="db-cw__nav" aria-label="Jump to a creator">' + shown.map(function (c) {
      return '<button type="button" data-cw="' + esc(c.code) + '">' + ava(c.photo) + "<span>" + esc(c.name) + "</span><b>" + pieceCount(by[c.code] || []) + "</b></button>"; }).join("") + "</nav>" : "";
    return nav + shown.map(function (c) {
      var mine = topPosts(by[c.code] || []), vids = pieceCount(mine);
      var v = 0, e = 0, ve = 0; mine.forEach(function (p) { v += seen(p); e += p.engagement || 0; if (p.video && !p.views_hidden) ve += p.views || 0; });
      var er = ve ? mine.filter(function (p) { return p.video && !p.views_hidden; }).reduce(function (a, p) { return a + (p.engagement || 0); }, 0) / ve * 100 : null;
      var rank = !filtered() && c.rank ? (c.rank <= 3 ? '<span class="db-cw__medal">' + medal(c.rank) + "</span>" : '<span class="db-cw__rk">#' + c.rank + "</span>") : "";
      var profs = (c.profiles || []).filter(function (x) { return x.url; }).map(function (x) {
        return '<a class="db-chip" href="' + esc(x.url) + '" target="_blank" rel="noopener" style="--pc:' + (PCOL[x.platform] || "#121212") + '">' + (ICONS[x.platform] || "") + esc(x.platform) + (x.followers ? " · " + num(x.followers) : "") + "</a>"; }).join("");
      var owed = []; if (!filtered()) for (var i = (c.delivered || 0); i < (c.planned || 0); i++) owed.push(pendingCard(c, i + 1));
      return '<section class="db-cw" id="cw-' + esc(c.code) + '"><header class="db-cw__h">'
        + '<span class="db-cw__pic">' + ((c.photo_large || c.photo) ? '<img src="' + esc(c.photo_large || c.photo) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : '<span class="db-ava"></span>') + rank + "</span>"
        + '<div class="db-cw__id"><h4>' + (known[c.code] ? who(c) : esc(c.name)) + "</h4>" + (profs ? '<div class="db-cw__prof">' + profs + "</div>" : "") + "</div>"
        + '<dl class="db-cw__st"><div><dt>Videos</dt><dd>' + vids + (c.planned && !filtered() ? "<small>/" + c.planned + "</small>" : "") + "</dd></div>"
        + "<div><dt>Views</dt><dd>" + num(v) + "</dd></div><div><dt>Engagement</dt><dd>" + num(e) + "</dd></div>"
        + "<div><dt>Eng. rate</dt><dd>" + pct(er) + "</dd></div></dl></header>"
        + (mine.length || owed.length ? '<div class="db-wall">' + mine.map(post).join("") + owed.join("") + "</div>" : "")
        + "</section>";
    }).join("");
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-cw]"); if (!b) return;
    var t = document.getElementById("cw-" + b.getAttribute("data-cw"));
    if (t) t.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  });
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
      + '<span class="db-pbadge" style="color:' + (PCOL[p.platform] || "#121212") + '" title="Published on ' + esc(p.platform) + '">' + (ICONS[p.platform] || "") + "</span>"
      + '</div><div class="db-post__body"><b>' + esc(p.creator) + '</b><span class="db-post__on"><i style="color:' + (PCOL[p.platform] || "#121212") + '">' + (ICONS[p.platform] || "") + "</i>" + esc(p.platform) + " · " + esc(day(p.posted_at, true)) + "</span></div>"
      + (p.caption ? '<p class="db-post__cap">' + esc(p.caption) + "</p>" : "")
      + '<div class="db-post__stats">' + stats(p).map(function (x) { return "<div><small>" + x[0] + "</small><b>" + x[1] + "</b></div>"; }).join("") + "</div>"
      + '<span class="db-post__open">Open on ' + esc(p.platform) + " ↗</span></a>";      // shown in the PDF, where the card is a link
  }
  var TITLES = { kpi: "Goals & benchmarks", trend: "Views & engagement", creators: "All creators", stage: "Campaign stage", mix: "Content by format", posts: "All posts", geo: "What people say", plat: "Platforms", clicks: "Affiliate clicks" };
  var lastFocus = null, curArea = null;
  function openPanel(area) {
    if (!PANEL[area]) return;
    lastFocus = document.activeElement;
    $("db-panel-title").textContent = (area === "clicks" && R.sales && R.sales.totals ? "Clicks to sales" : TITLES[area]) + (area === "kpi" ? (F.platform ? " · " + F.platform : "") : filtered() && area !== "stage" ? " · filtered" : "");
    $("db-scrim").hidden = false; $("db-panel").hidden = false;      // shown first: charts are drawn at the panel's real width
    $("db-panel-body").innerHTML = PANEL[area]();
    curArea = area;
    if (area === "kpi") bindTV();
    $("db-scrim").hidden = false; $("db-panel").hidden = false;
    $("db-panel-close").focus();
  }
  function closePanel() { curArea = null; $("db-scrim").hidden = true; $("db-panel").hidden = true; if (lastFocus) lastFocus.focus(); }
  // Info tips: one floating box placed beside the "i", flipped and clamped
  // so it never runs off the screen or under the next card.
  var tipEl = null, tipFor = null, tipPinned = false;
  function showTip(t) {
    hideTip();
    tipEl = document.createElement("div"); tipEl.className = "db-tip"; tipEl.setAttribute("role", "tooltip"); tipEl.id = "db-tip"; tipFor = t;
    tipEl.textContent = t.getAttribute("data-tip"); document.body.appendChild(tipEl); t.setAttribute("aria-describedby", "db-tip");
    var r = t.getBoundingClientRect(), w = tipEl.offsetWidth, h = tipEl.offsetHeight, vw = innerWidth, vh = innerHeight;
    var x = Math.max(8, Math.min(r.left, vw - w - 8)), y = r.bottom + 8;
    if (y + h > vh - 8) y = Math.max(8, r.top - h - 8);
    tipEl.style.left = x + "px"; tipEl.style.top = y + "px";
  }
  function hideTip() { if (tipEl) { tipEl.remove(); tipEl = null; } if (tipFor) { tipFor.removeAttribute("aria-describedby"); tipFor = null; } tipPinned = false; }
  ["mouseover", "focusin"].forEach(function (ev) { document.addEventListener(ev, function (e) { var t = e.target.closest && e.target.closest(".db-info"); if (t && !tipPinned) showTip(t); }); });
  ["mouseout", "focusout"].forEach(function (ev) { document.addEventListener(ev, function (e) { if (!tipPinned && e.target.closest && e.target.closest(".db-info")) hideTip(); }); });
  // a tap (or a click) keeps the note open; a second tap on the mark, a tap elsewhere, or Esc closes it
  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest(".db-info");
    if (t) { if (tipPinned && tipFor === t) hideTip(); else { showTip(t); tipPinned = true; } e.preventDefault(); e.stopPropagation(); }
    else if (tipEl) hideTip();
  }, true);
  addEventListener("scroll", hideTip, true);
  document.addEventListener("click", function (e) { var b = e.target.closest("[data-area]"); if (b && b.closest("#cat-app")) openPanel(b.getAttribute("data-area")); });
  $("db-panel-close").addEventListener("click", closePanel);
  $("db-scrim").addEventListener("click", closePanel);
  document.addEventListener("keydown", function (e) { if (e.key !== "Escape") return; if (tipEl) { hideTip(); return; } if (!$("db-panel").hidden) closePanel(); });

  /* What people did ring (2026-10-23): the report's "What people did" stack as a ring (owner). Likes, comments,
     saves and shares of the posts in the current view, each in its fixed colour; the drawer splits them by
     platform and by creator. A platform that does not show a number (saves on Facebook and YouTube) reads "—". */
  var DID = [["likes", "Likes", "#14884a"], ["comments", "Comments", "#ff691e"], ["saves", "Saves", "#b9d400"], ["shares", "Shares", "#7048e8"]];
  var DID_IC = ico('<path d="M7 11V5.5a1.5 1.5 0 0 1 3 0V11M10 10V4a1.5 1.5 0 0 1 3 0v6M13 10V5.5a1.5 1.5 0 0 1 3 0V13a7 7 0 0 1-7 7h-.5A5.5 5.5 0 0 1 4 16l-1-3.5a1.5 1.5 0 0 1 2.7-1.2L7 13"/>');
  var DID_TIP = "Everything people did on the posts in this view: likes, comments, saves and shares, the four parts of engagement. The ring shows each one's share; the middle is the total.";
  function didSum(list) {
    var t = { likes: 0, comments: 0, saves: 0, shares: 0, n: 0, seen: {} };
    list.forEach(function (p) { DID.forEach(function (d) { var v = p[d[0]]; if (v != null && !(d[0] === "likes" && p.likes_hidden)) { t[d[0]] += v; t.seen[d[0]] = 1; } }); });
    t.n = t.likes + t.comments + t.saves + t.shares;
    return t;
  }
  function didPct(v, n) { if (!n || !v) return "0%"; var x = v / n * 100; return x < 1 ? "<1%" : Math.round(x) + "%"; }
  function didRing(t, cls) {
    // a hair of white between the parts, so four colours read as four parts and not as one band
    var off = 25, live = DID.filter(function (d) { return t[d[0]] > 0; }), gap = live.length > 1 ? 0.6 : 0;
    var segs = live.map(function (d) {
      var s = t[d[0]] / t.n * 100, c = '<circle cx="21" cy="21" r="15.915" fill="none" stroke="' + d[2] + '" stroke-width="5.6" stroke-dasharray="' + Math.max(0.3, s - gap).toFixed(2) + " " + (100 - Math.max(0.3, s - gap)).toFixed(2) + '" stroke-dashoffset="' + off.toFixed(2) + '"><title>' + d[1] + ": " + full(t[d[0]]) + " (" + didPct(t[d[0]], t.n) + ")</title></circle>";
      off -= s; return c; }).join("");
    return '<div class="wpd-ring' + (cls ? " " + cls : "") + '"><svg viewBox="0 0 42 42" role="img" aria-label="' + esc(DID.map(function (d) { return d[1] + " " + full(t[d[0]]) + ", " + didPct(t[d[0]], t.n); }).join("; ")) + '">'
      + '<circle cx="21" cy="21" r="15.915" fill="none" stroke="#efece6" stroke-width="5.6"/>' + segs + "</svg><span><b>" + num(t.n) + "</b>interactions</span></div>";
  }
  function didLegend(t) {
    return '<div class="wpd-legend">' + DID.map(function (d) {
      return '<div class="wpd-legend__r" style="--c:' + d[2] + '"><i></i><span>' + d[1] + "</span><b>" + (t.seen[d[0]] ? full(t[d[0]]) : "—") + "</b><small>" + (t.seen[d[0]] ? didPct(t[d[0]], t.n) : "") + "</small></div>"; }).join("") + "</div>";
  }
  function renderDid(list) {
    var t = didSum(list), el = $("w-did"); if (!el) return;
    el.innerHTML = head(DID_IC, "What people did", DID_TIP, t.n ? "did" : null)
      + '<div class="db-card__body">' + (t.n ? '<div class="wpd-hero">' + didRing(t, "wpd-ring--card") + didLegend(t) + "</div>"
        : '<p class="db-note wpd-none">No likes, comments, saves or shares in this view yet.</p>') + "</div>";
  }
  // One row per platform or creator: a stacked bar against the biggest row, the total, then the four numbers.
  function didRows(groups, label, peak) {
    return '<div class="wpd-rows">' + groups.map(function (g) {
      var t = g.t;
      return '<div class="wpd-row"><div class="wpd-row__top"><span class="wpd-row__who">' + label(g) + "</span><b>" + full(t.n) + "</b></div>"
        + '<div class="wpd-row__bar" style="--w:' + (t.n / peak * 100).toFixed(1) + '%">' + DID.map(function (d) { return t[d[0]] ? '<i style="flex-grow:' + t[d[0]] + ";background:" + d[2] + '" title="' + d[1] + ": " + full(t[d[0]]) + '"></i>' : ""; }).join("") + "</div>"
        + '<dl class="wpd-row__nums">' + DID.map(function (d) { return '<div style="--c:' + d[2] + '"><dt>' + d[1] + "</dt><dd>" + (t.seen[d[0]] ? num(t[d[0]]) : '<span title="Not shown by this platform">—</span>') + "</dd></div>"; }).join("") + "</dl></div>";
    }).join("") + "</div>";
  }
  function didGroup(list, key) {
    var by = {}, order = [];
    list.forEach(function (p) { var k = p[key]; if (!by[k]) { by[k] = []; order.push(k); } by[k].push(p); });
    var out = order.map(function (k) { return { k: k, p: by[k][0], t: didSum(by[k]) }; }).sort(function (a, b) { return b.t.n - a.t.n; });
    return { rows: out, peak: Math.max.apply(null, out.map(function (g) { return g.t.n; }).concat([1])) };
  }
  PANEL.did = function () {
    var list = posts(), t = didSum(list);
    if (!t.n) return '<p class="db-note">No likes, comments, saves or shares in this view yet.</p>';
    var hid = list.filter(function (p) { return p.likes_hidden; }).length;
    var per = t.likes ? "For every <mark>100 likes</mark>, people left <b>" + Math.round(t.comments / t.likes * 100) + "</b> comments, saved <b>" + Math.round(t.saves / t.likes * 100) + "</b> times and shared <b>" + Math.round(t.shares / t.likes * 100) + "</b> times." : "";
    var keep = t.saves + t.shares, ks = keep / t.n;
    var why = keep ? " Saves and shares are <mark>" + didPct(keep, t.n) + "</mark> of everything: " + (ks >= 0.2 ? "people kept the videos or passed them on, a strong sign." : "most people stopped at a like.") : "";
    var pl = didGroup(list, "platform"), cr = didGroup(list, "code");
    return '<div class="wpd-panel-hero">' + didRing(t, "wpd-ring--hero") + didLegend(t) + "</div>"
      + (per || why ? '<p class="wpd-insight">' + per + why + "</p>" : "")
      + "<h3>By platform</h3>" + didRows(pl.rows, function (g) { return '<i class="wpd-ic" style="color:' + (PCOL[g.k] || "#121212") + '">' + (ICONS[g.k] || "") + "</i>" + esc(g.k); }, pl.peak)
      + "<h3>By creator</h3>" + didRows(cr.rows, function (g) { return ava(g.p.photo) + who({ code: g.k, name: g.p.creator }); }, cr.peak)
      + '<p class="db-note wpd-foot">Engagement counts all four. A dash means the platform does not show that number' + (hid ? "; " + hid + " post" + (hid === 1 ? " hides its" : "s hide their") + " likes, so those likes are not counted" : "") + ".</p>";
  };
  TITLES.did = "What people did";
  /* end What people did ring */

  /* PDF print (2026-10-23): the client field stays on the dashboard and report, never in the PDF (owner). The PDF is built from this dashboard, every panel opened out behind a cover, so it holds
     all the data the dashboard can show. A4, no browser header or footer (page margin 0); a table's repeating head and
     foot keep the space for our own running header and footer on every page. Post and video links stay clickable. */
  // The report belongs to Helvi Track, so it is Track's mark on the cover and in the running
  // header, beside the client's own (Bido, 26 Oct 2026).
  var PP_LOGO = "../../assets/brand/modules/helvi-track-480.png?v=1";
  function ppName(n) {   // "Dr Name | د. الاسم" → the Latin part leads, the Arabic part is kept beside it
    var s = String(n || ""), i = s.search(/[؀-ۿ]/);
    if (i <= 0) return { en: s.replace(/\s*\|\s*$/, ""), ar: "" };
    return { en: s.slice(0, i).replace(/[\s|]+$/, ""), ar: s.slice(i).trim() };
  }
  function ppSec(n, title, lede, body, cls) {
    return '<section class="pp-sec' + (cls ? " " + cls : "") + '"><header class="pp-h"><span class="pp-h__n">' + n + "</span><div><h2>" + esc(title) + "</h2>"
      + (lede ? "<p>" + lede + "</p>" : "") + '</div></header><div class="db-panel__body pp-b">' + body + "</div></section>";
  }
  function ppPodium() {
    var top = (R.creators || []).filter(function (c) { return c.rank; }).slice(0, 3);
    if (!top.length) return "";
    var order = top.length === 3 ? [top[1], top[0], top[2]] : top;
    return '<div class="pp-pod">' + order.map(function (c) {
      var nm = ppName(c.name), pic = c.photo_large || c.photo;
      return '<div class="pp-pod__c pp-pod__c--' + c.rank + '"><span class="pp-pod__pic">' + (pic ? '<img src="' + esc(pic) + '" alt="">' : "") + '<i>' + medal(c.rank) + "</i></span>"
        + "<b>" + esc(nm.en) + "</b>" + (nm.ar ? '<span class="pp-ar" dir="rtl" lang="ar">' + esc(nm.ar) + "</span>" : "")
        + '<strong>' + scoreTxt(c.score) + "</strong><small>" + num(c.seen != null ? c.seen : c.views) + " views · " + num(c.engagement) + " engagements</small></div>";
    }).join("") + "</div>";
  }
  // Comment highlights: the most-liked comments, with the buying questions among them, each with its English line.
  function ppHighlights() {
    var items = (CMB.items || []).filter(function (it) { return it[7] && it[7].length >= 12 && it[7].length <= 280; });
    if (!items.length) return "";
    var byLikes = items.slice().sort(function (a, b) { return (b[9] || 0) - (a[9] || 0); });
    var pick = [], seen = {};
    var per = {};      // at most two per creator, so the highlights speak for the whole campaign
    function add(list, n) { list.forEach(function (it) { if (n > 0 && !seen[it[0] + it[7]] && (per[it[1]] || 0) < 2) { seen[it[0] + it[7]] = 1; per[it[1]] = (per[it[1]] || 0) + 1; pick.push(it); n--; } }); }
    add(byLikes.filter(function (it) { return it[3] === "p"; }), 4);
    add(byLikes.filter(function (it) { return it[4]; }), 2);
    add(byLikes, 8 - pick.length); if (pick.length < 8) { per = {}; add(byLikes, 8 - pick.length); }
    var P = cmPeople();
    return '<div class="pp-quotes">' + pick.slice(0, 8).map(function (it) {
      var m = CM_MOOD[it[3]] || "neu", nm = ppName(P.names[it[1]] || "");
      return '<article class="pp-q" style="--c:' + CM_COL[m] + '"><i class="cm-face" style="--c:' + CM_COL[m] + '">' + CM_FACE[m] + '</i><div><q dir="auto">' + esc(it[7]) + "</q>"
        + (it[8] && it[8] !== it[7] ? '<p class="pp-q__en">' + esc(it[8]) + "</p>" : "")
        + '<p class="pp-q__m">' + (ICONS[it[2]] || "") + "<span>" + esc(nm.en || it[2]) + "</span>" + (it[4] ? '<em>Asks to buy</em>' : "") + (it[9] ? '<span class="pp-q__l">' + CM_HEART + it[9] + "</span>" : "") + "</p></div></article>";
    }).join("") + "</div>";
  }
  // Every campaign video with its link, so the PDF opens each one.
  function ppLinks() {
    var list = R.posts.filter(function (p) { return p.section === "campaign" && p.url; }).sort(function (a, b) { return (a.creator || "").localeCompare(b.creator || "") || (a.posted_at || 0) - (b.posted_at || 0); });
    if (!list.length) return "";
    return '<table class="db-table pp-links"><thead><tr><th>Creator</th><th>Platform</th><th>Posted</th><th>Views</th><th>Open</th></tr></thead><tbody>' + list.map(function (p) {
      var u = String(p.url), short = u.replace(/^https?:\/\/(www\.)?/, "").replace(/\?.*$/, ""); if (short.length > 46) short = short.slice(0, 44) + "…";
      return "<tr><td>" + esc(ppName(p.creator).en) + '</td><td><span class="pp-links__p">' + (ICONS[p.platform] || "") + esc(p.platform) + "</span></td><td>" + esc(day(p.posted_at, true)) + "</td><td>"
        + (p.views_hidden ? "—" : num(seen(p))) + '</td><td><a href="' + esc(u) + '" target="_blank" rel="noopener">' + esc(short) + " ↗</a></td></tr>";
    }).join("") + "</tbody></table>";
  }
  function printAll() {
    if (!R) return;
    var keep = { platform: F.platform, range: F.range, from: F.from, to: F.to, creators: F.creators.slice() };
    F.platform = ""; F.range = "all"; F.from = ""; F.to = ""; F.creators = [];      // the PDF is always the whole campaign
    PRINT_W = 660;
    var old = $("pp"); if (old) old.remove();
    document.body.classList.add("pp-busy");
    cmLoad(function () {
      var n = 0, num2 = function () { n++; return (n < 10 ? "0" : "") + n; };
      var mixT = (function () { var by = {}; posts().forEach(function (p) { by[p.kind] = (by[p.kind] || 0) + 1; });
        var parts = Object.keys(by).map(function (k) { return { k: k, n: by[k] }; }).sort(function (a, b) { return b.n - a.n; });
        return parts.length ? '<div class="db-donut pp-mix">' + donut(parts) + '<div class="db-key">' + parts.map(function (p, i) { return '<div><span class="db-sw" style="background:' + COL[i % COL.length] + '"></span>' + esc(KIND[p.k] || p.k) + "<b>" + p.n + "</b></div>"; }).join("") + "</div></div>" : ""; })();
      var geo = R.comments && cmPick().n ? PANEL.geo() : "";
      // No cover page (owner, 2026-10-23): the PDF opens on its first section; every section starts on a new page.
      var body = ppSec(num2(), "Goals & benchmarks", "Every target, where it should be today, the forecast and the benchmarks for creators of this size.", PANEL.kpi())
        + ppSec(num2(), "Creators leaderboard", "Score out of 100 for the campaign's objective, what each creator delivered and every video.", ppPodium() + PANEL.creators())
        + ppSec(num2(), "Views & engagement", "How the campaign grew, day by day.", PANEL.trend())
        + (PANEL.did ? ppSec(num2(), "What people did", "Likes, comments, saves and shares, by platform and by creator.", PANEL.did()) : "")
        + ppSec(num2(), "Platforms & content", "Views, reach and engagement rate on each platform, and the formats published.", PANEL.plat() + (mixT ? "<h3>Content mix</h3>" + mixT : ""))
        + (geo ? ppSec(num2(), "What people say", "Viewers' comments under the campaign videos, read by AI. Commenters' names are never stored.", geo + (ppHighlights() ? "<h3>Comment highlights</h3>" + ppHighlights() : ""), "pp-sec--geo") : "")
        + ppSec(num2(), "Every post", "Each creator's posts with their numbers. Every card opens the post.", PANEL.posts())
        + (R.visibility.clicks === false || (!clicksFor() && !(R.sales && R.sales.totals)) ? "" : ppSec(num2(), R.sales && R.sales.totals ? "Clicks to sales" : "Affiliate clicks", "", PANEL.clicks()))
        + ppSec(num2(), "Campaign stage", "The scope of work, step by step.", PANEL.stage())
        + (ppLinks() ? ppSec(num2(), "Video links", "Open any campaign video straight from this PDF.", ppLinks()) : "");
      var c = R.campaign;
      var wrap = document.createElement("div"); wrap.id = "pp"; wrap.className = "pp";
      wrap.innerHTML = '<div class="pp-run pp-run--h"><img src="' + PP_LOGO + '" alt=""><span>' + esc(c.name) + " · Campaign report</span><span>" + esc(day(Date.now() / 1000, true)) + "</span></div>"
        + '<div class="pp-run pp-run--f"><span>HelloVoice · hellovoice.co.uk · info@hellovoice.co.uk</span><span>Confidential</span></div>'
        + '<table class="pp-frame"><thead><tr><td><div class="pp-sp pp-sp--h"></div></td></tr></thead><tfoot><tr><td><div class="pp-sp pp-sp--f"></div></td></tr></tfoot><tbody><tr><td>' + body + "</td></tr></tbody></table>";
      document.body.appendChild(wrap);
      // drawers that open on a tap are opened: pace charts drawn, every section and topic shown, the comment browser left out
      var it = {}; (SP().items || []).forEach(function (i) { it[i.key] = i; });
      wrap.querySelectorAll(".db-tv__row").forEach(function (row) { var pace = row.querySelector(".db-tv__pace"), k = row.getAttribute("data-k");
        if (pace && it[k]) { pace.hidden = false; pace.innerHTML = tvPace(it[k], PRINT_W - 40); } });
      wrap.querySelectorAll("details").forEach(function (d) { d.open = true; });
      var cmb = wrap.querySelector("#cmb"); if (cmb) { var d = cmb.closest("details") || cmb; d.remove(); }
      var tv = wrap.querySelector("#db-tv"); if (tv) { tv.id = "pp-tv"; tv.classList.add("is-in"); }
      cmSamples();
      wrap.querySelectorAll("img").forEach(function (i) { i.loading = "eager"; });
      var waits = [].slice.call(wrap.querySelectorAll("img")).filter(function (i) { return !i.complete; }).map(function (i) {
        return new Promise(function (ok) { i.addEventListener("load", ok); i.addEventListener("error", function () { i.remove(); ok(); }); }); });
      if (document.fonts && document.fonts.ready) waits.push(document.fonts.ready);
      var done = false, title = document.title;
      function go() {
        if (done) return; done = true;
        document.body.classList.remove("pp-busy"); document.body.classList.add("pp-on");
        document.title = c.name + " — Campaign report";        // the PDF's file name
        window.print();
      }
      window.addEventListener("afterprint", function once() {
        window.removeEventListener("afterprint", once);
        document.body.classList.remove("pp-on"); document.title = title; PRINT_W = 0;
        F.platform = keep.platform; F.range = keep.range; F.from = keep.from; F.to = keep.to; F.creators = keep.creators;
        var w = $("pp"); if (w && !window.__ppKeep) w.remove();
      });
      Promise.all(waits).then(go, go); setTimeout(go, 12000);
    });
  }
  window.__hvPrintAll = printAll;
  /* end PDF print */

  load();
})();
