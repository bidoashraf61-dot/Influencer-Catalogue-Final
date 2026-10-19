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
  // A score as a % of the best creator: one decimal under 1 so a small share never reads as 0 (owner, 2026-10-19).
  function scoreTxt(v, html) {
    if (v == null || isNaN(v)) return "—";
    var n = v > 0 && v < 1 ? v.toFixed(1) : String(Math.round(v));
    return n + (html ? '<small class="db-pct">%</small>' : "%");
  }
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
  function get(path) { return fetch(API + path, { credentials: "include", cache: "no-store" }).then(function (r) { if (r.status === 401) throw { locked: true }; if (!r.ok) throw {}; return r.json(); }); }

  /* --------------------------------------------------------------- gate */
  function lock(msg) { $("cat-app").hidden = true; $("cat-gate").hidden = false; if (msg) { $("cat-gate-error").textContent = msg; $("cat-gate-error").hidden = false; } }
  $("cat-gate-form").addEventListener("submit", function (e) {
    e.preventDefault();
    fetch(API + "/api/unlock", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: $("cat-code").value.trim(), lite: true, link: token() ? "c:" + token() : "c:list" }) })
      .then(function (r) { return r.json(); })
      .then(function (b) {
        if (!b || !b.ok) lock(b && b.reason === "otherlink" ? "That code is for a different campaign. Use the code that came with this link." : "That code is not right.");
        else { $("cat-code").value = ""; load(); } })
      .catch(function () { lock("Could not reach the server. Please try again."); });
  });

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
        $("cat-gate").hidden = true; $("cat-app").hidden = false; document.body.classList.remove("cat-locked");
        setupHeader(); setupFilters(); renderAll(); setupShare();
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
    document.title = c.name + " — Dashboard — HELVi Connect";
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
    // The verdict, big and solid, with how much of the goals is reached.
    var P = R.progress || {}, pc = P.overall != null ? Math.round(P.all_met ? 100 : Math.min(99, P.overall)) : null;
    $("db-verdict").innerHTML = v.label ? '<span class="db-verdict' + (v.grade ? " db-verdict--" + v.grade : "") + '" role="status" title="How the campaign is doing against its targets today">'
      + esc(v.label) + (pc != null ? '<b class="db-verdict__pct">' + pc + "%</b>" : "") + "</span>" : "";
    $("db-report").href = "../#t=" + TOKEN;
    $("db-pdf").href = "../#t=" + TOKEN;
    $("db-pdf").addEventListener("click", function () { try { sessionStorage.setItem("hv_print", "1"); } catch (e) {} });
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

  // "Update now": runs the campaign's capture jobs for the posts it has, with Helvi on screen while the numbers come in,
  // a green tick when they are in, the balance of free updates, and a request for more when they are used up.
  function mountUpdate(host) {
    var box = document.createElement("span"); box.className = "db-upd";
    box.innerHTML = '<button type="button" class="db-upd__btn" id="db-upd"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 11a8 8 0 0 0-14.5-4.2M4 4v3.8h3.8"/><path d="M4 13a8 8 0 0 0 14.5 4.2M20 20v-3.8h-3.8"/></svg><span>Update now</span></button><small class="db-upd__left"></small>';
    host.appendChild(box);
    var btn = box.querySelector("button"), label = btn.querySelector("span"), left = box.querySelector("small"), S = null;
    function leftText() { return !S || S.unlimited ? "" : S.left + " of " + S.limit + " free updates left"; }
    function paint(s) {
      if (!s) return; S = s;
      left.textContent = s.unlimited ? "Unlimited for you" : leftText();
      var out = !s.unlimited && s.left === 0;
      btn.classList.toggle("is-out", out); label.textContent = out ? "Request more updates" : "Update now";
    }
    function state() { return get("/api/campaign/refresh?t=" + encodeURIComponent(TOKEN)).then(function (s) { paint(s); return s; }); }
    state().catch(function () {});
    function modal(extra) {
      var o = document.createElement("div"); o.className = "db-fetch"; o.setAttribute("role", "dialog"); o.setAttribute("aria-modal", "true");
      var card = document.createElement("div"); card.className = "db-fetch__card" + (extra ? " " + extra : ""); o.appendChild(card);
      document.body.appendChild(o);
      return { card: card, close: function () { o.remove(); } };
    }
    var STEPS = ["Finding the posts on this campaign…", "Asking Instagram, TikTok and Facebook…", "Asking YouTube and Snapchat…", "Adding up the numbers…"];
    function postJSON(path, body) {
      return fetch(API + path, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
        .then(function (r) { return r.json().then(function (b) { return { s: r.status, b: b }; }); });
    }
    // The wait: Helvi, the steps, the balance.
    function run() {
      var m = modal(), cook = null, t0 = Date.now(), poll = null;
      try { if (window.hvPortal && window.hvPortal.cooking) cook = window.hvPortal.cooking({ list: true, dark: false, title: "Helvi is fetching the latest numbers", steps: STEPS }); } catch (e) { cook = null; }
      if (cook) m.card.appendChild(cook); else m.card.innerHTML = '<p class="db-fetch__plain">Fetching the latest numbers…</p>';
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
      var tick = setInterval(function () { if (!finishing) show(95 * (1 - Math.exp(-(Date.now() - t0) / 18000))); }, 120);
      show(0);
      var msg = document.createElement("p"); msg.className = "db-fetch__msg"; msg.setAttribute("role", "status"); m.card.appendChild(msg);
      var bal = document.createElement("p"); bal.className = "db-fetch__bal"; bal.textContent = leftText(); m.card.appendChild(bal);
      btn.classList.add("is-busy");
      function leave(reload) { clearInterval(tick); if (cook && cook.stop) cook.stop(); m.close(); btn.classList.remove("is-busy"); if (reload) load(); else state().catch(function () {}); }
      function fail(text) {
        if (poll) clearInterval(poll); clearInterval(tick);
        prog.hidden = true; bal.hidden = true; if (cook) cook.hidden = true;        // nothing is running: say why, plainly
        msg.className = "db-fetch__msg db-fetch__msg--big"; msg.textContent = text; setTimeout(function () { leave(false); }, 2800);
      }
      function done() {
        if (poll) clearInterval(poll); finishing = true;
        var from = P, t1 = Date.now();
        (function ramp() {
          var k = Math.min(1, (Date.now() - t1) / 900); show(from + (100 - from) * k);
          if (k < 1) return requestAnimationFrame(ramp);
          clearInterval(tick);
          setTimeout(function () {
            m.card.innerHTML = '<div class="db-ok"><svg class="db-ok__tick" viewBox="0 0 52 52" aria-hidden="true"><circle class="db-ok__c" cx="26" cy="26" r="23"/><path class="db-ok__p" d="M15 27.5l8 8 14.5-17"/></svg>'
              + '<h3 role="status">Numbers updated successfully</h3>' + (leftText() ? "<p>" + esc(leftText()) + "</p>" : "") + "</div>";
            setTimeout(function () { leave(true); }, 2400);
          }, 500);
        })();
      }
      postJSON("/api/campaign/refresh", { t: TOKEN }).then(function (r) {
        if (!r.b || !r.b.ok) return fail((r.b && r.b.message) || "Could not start the update. Try again.");
        paint(r.b); bal.textContent = leftText();
        poll = setInterval(function () {
          get("/api/campaign/refresh?t=" + encodeURIComponent(TOKEN)).then(function (s) {
            paint(s); bal.textContent = leftText();
            if (!s.running) done(); else if (Date.now() - t0 > 5 * 60 * 1000) fail("Still working. The new numbers will appear on their own.");
          }).catch(function () {});
        }, 3000);
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
    btn.addEventListener("click", function () {
      if (btn.classList.contains("is-busy")) return;
      if (btn.classList.contains("is-out")) request(); else run();
    });
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
    $("db-reset").addEventListener("click", function () {
      F = { platform: "", range: "all", from: "", to: "", creators: [] };
      [].forEach.call($("db-platforms").children, function (x, i) { x.setAttribute("aria-pressed", i === 0 ? "true" : "false"); });
      $("db-range").value = "all"; $("db-custom").hidden = true;
      [].forEach.call($("db-creators").querySelectorAll("input"), function (i) { i.checked = false; });
      creatorBtn();
      renderAll();
    });
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
      var x = by[d] = by[d] || { views: 0, eng: 0, reach: 0, posts: 0 }; x.views += p.views || 0; x.eng += p.engagement || 0; x.reach += p.reach || 0; if (p.piece_size <= 1 || p.id === p.pk) x.posts++; });
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
      ["Views", t.views_hidden ? '<span class="db-na" title="This platform does not show view counts">Not shown</span>' : num(t.views) + est("views"), goal("views"), spark(s.map(function (x) { return x.views; }), COL[0]), IC.views, "trend"],
      ["Reach", t.views_hidden ? '<span class="db-na" title="Reach is worked out from views, which this platform does not show">Not shown</span>' : num(t.reach) + (isAdj("reach") ? est("reach") : reachEst() ? '<small class="db-est" title="Instagram does not show reach on reels publicly. Placeholder at ' + Math.round(((R.reach_basis && R.reach_basis.per_view) || 0.9) * 100) + '% of views (a small margin below) until the creators\' insights arrive.">est.</small>' : ""), goal("reach"), spark(s.map(function (x) { return x.reach; }), COL[3]), IC.reach, "trend"],
      ["Engagement", num(t.engagement) + est("engagement"), goal("engagement"), spark(s.map(function (x) { return x.eng; }), COL[1]), IC.engagement, "trend"],
      ["Avg eng. rate", pct(t.er) + est("er"), !filtered() ? (g.er ? goal("er") : sig(R.total.er_grade)) : "", "", IC.er, "kpi"],
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
    box.innerHTML = '<span class="db-obj__label">Objective · <b>' + esc(o.label) + '</b>'
      + (R.targets_auto ? '<span class="db-obj__auto" title="No targets were agreed for this campaign yet, so these come from what its creators usually deliver for the posts booked.">Suggested targets</span>' : "")
      + '</span><div class="db-obj__track" role="img" aria-label="' + Math.round(done) + '% of all targets achieved">'
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
    if (!filtered()) return R.creators.filter(function (c) { return c.rank; }).map(function (c) { return { c: c, v: c.score, label: scoreTxt(c.score, true) }; });
    // Where a platform shows no views (Snapchat) the creator is ranked by engagement instead of being left out.
    var by = {}; list.forEach(function (p) {
      var x = by[p.code] = by[p.code] || { n: 0, eng: 0, hid: true }; x.n += seen(p); x.eng += p.engagement || 0; if (!(p.video && p.views_hidden)) x.hid = false;
    });
    return R.creators.filter(function (c) { var x = by[c.code]; return x && (x.n || (x.hid && x.eng)); }).map(function (c) {
      var x = by[c.code], useEng = !x.n && x.hid;
      return { c: c, v: useEng ? x.eng : x.n, label: useEng ? num(x.eng) + " eng." : num(x.n) };
    }).sort(function (a, b) { return b.v - a.v; });
  }
  function renderTop(list) {
    var rows = ranked(list).slice(0, 5);
    $("w-top").innerHTML = head(IC.top, "Creators leaderboard", filtered() ? "Ranked by views in this view." : scoreTip(), "creators")
      + '<div class="db-card__body">' + (filtered() ? "" : '<div class="db-top__how">' + scoreBar(true) + "</div>") + (filtered() ? '<div class="db-top__cols"><span>Creator</span><b>Reached</b></div>' : "") + (rows.map(function (r, i) {
                return '<div class="db-rank' + (i === 0 ? " is-1" : "") + '"><span class="db-rank__n">' + (i < 3 ? medal(i + 1) : i + 1) + "</span>" + ava(r.c.photo) + "<span><b>" + who(r.c) + "</b><small>" + r.c.delivered + (r.c.planned ? "/" + r.c.planned : "") + (r.c.delivered === 1 && !r.c.planned ? " video · " : " videos · ") + num(r.c.seen != null ? r.c.seen : r.c.views) + " views" + '</small></span><span class="db-rank__score" title="' + (filtered() ? "People reached in this view" : "Score out of 100") + '">' + r.label + "</span></div>";
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
  /* What people said (owner, 2026-10-19; v11 same day): viewers' comments, read by AI 2 and 7 days after each video.
     It takes the audience-countries slot. Totals come per creator and platform, so the page's filters apply. */
  var CMI = ico('<path d="M4 5.5h16v10.5H9l-5 4z"/><path d="M8.5 9.5h7M8.5 12.5h4.5"/>');
  var CM_TIP = "What viewers wrote in the comments under the campaign videos, read by AI 2 and 7 days after each video. Commenters' names are never stored.";
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
    var now = Date.now() / 1000, d = C.read_days || [2, 7], fp = C.first_post, r1 = C.next_read || fp + d[0] * 86400, r2 = C.final_read || fp + d[1] * 86400;
    return '<div class="cm-wait"><p>Comments are read ' + d[0] + " and " + d[1] + " days after each video. The first reading lands on <b>" + cmDay(r1) + "</b>.</p>"
      + '<div class="cm-steps"><div class="on"><b>Posted</b>' + cmDay(fp) + '</div><div class="' + (now >= r1 ? "on" : "next") + '"><b>First read</b>' + cmDay(r1)
      + '</div><div class="' + (now >= r1 ? "next" : "") + '"><b>Final read</b>' + cmDay(r2) + "</div></div></div>";
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
    $("w-clicks").innerHTML = head(IC.clicks, "Affiliate clicks", "Taps on the creators' own tracking links — people only, not link previews or bots.", cl ? "clicks" : "")
      + '<div class="db-card__body">' + (cl ? '<div class="db-big">' + full(cl.clicks) + (cl.uniques != null ? "<small>" + full(cl.uniques) + " unique</small>" : "") + "</div>"
        + '<div style="margin-top:8px">' + bars((cl.by_app || []).slice(0, 3).map(function (r) { return { k: r.k, n: r.n, label: full(r.n) }; }), function (r) { return (ICONS[r.k] || "") + esc(r.k); }) + "</div>"
        + (cl.partial || F.platform ? '<p class="db-note">' + (F.platform ? "Clicks are per creator link, not per platform — showing all platforms." : "Apps show the whole campaign.") + "</p>" : "")
        : '<div class="db-na-card"><span class="db-na-card__icon">' + IC.clicks + '</span><span class="db-na">Not part of this campaign</span>'
          + "<p>This campaign does not contain affiliate links, so there are no clicks to show.</p></div>") + "</div>";
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
      return '<i style="flex:' + x[1] + ";background:" + x[2] + '"><b>' + Math.round(x[1] * 100) + "</b></i>"; }).join("") + '</div><div class="db-scorekey' + (small ? " db-scorekey--s" : "") + '">'
      + parts.map(function (x) { return '<div><i style="background:' + x[2] + '"></i><b>' + x[0] + "</b>" + (small ? "" : "<small>" + x[3] + "</small>") + "</div>"; }).join("") + "</div>";
  }
  // The campaign's objective as shares: how much of a creator's score is
  // awareness, engagement and clicks.
  function objectiveBox() {
    var w = weights(), o = R.objective || {}, links = !!o.links;
    var tiles = [["Awareness", w.exposure || 0, "views", SCORECOL.exposure], ["Engagement", (w.engagement || 0) + (w.er || 0), "likes & comments", SCORECOL.engagement],
      ["Clicks", w.clicks || 0, links ? "link clicks" : "no tracking links in this campaign", SCORECOL.clicks]];
    return '<h3>What this campaign is for</h3><div class="db-obj">' + tiles.map(function (t) {
      return '<div class="db-obj__t"><i style="background:' + t[3] + '"></i><b>' + Math.round(t[1] * 100) + "%</b><span>" + t[0] + "</span><small>" + t[2] + "</small></div>"; }).join("")
      + '</div><p class="db-note">Objective: ' + esc(o.label || "Balanced") + ". Each share is what that part is worth in a creator's score out of 100.</p>";
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

  /* ------------------------------------------- target vs achieved (goals) */
  // One row per agreed target: a track for the target, a bar for what is achieved, a tick for where
  // it should be today. Click a row (not Eng. rate) for the pace chart: achieved so far against the
  // straight line to the target. Whole-campaign by nature, so it ignores the page filters.
  var TV_COL = { good: "#14884a", moderate: "#e2780f", low: "#ee1515" };
  function tvFmt(k, v) { return v == null ? "—" : k === "er" ? pct(v) : num(v); }
  function tvRows(items, lead) {
    return items.map(function (i) {
      var met = i.actual >= i.goal, col = TV_COL[met ? "good" : i.grade] || TV_COL.low, isR = i.key === "er";
      var w = Math.min(100, i.pct), exp = isR || !i.goal ? null : Math.min(100, i.expected / i.goal * 100);
      var over = met && i.pct > 100.5 ? Math.round(i.pct - 100) : 0;
      var togo = met ? (over ? "Target met, " + over + "% over" : "Target met")
        : tvFmt(i.key, i.goal - i.actual) + (isR ? " points" : "") + " to go";
      var today = exp == null ? "" : " · should be at " + tvFmt(i.key, i.expected) + " by today";
      var can = !isR, id = "tv-" + i.key;
      var label = KEYN[i.key] + ": " + tvFmt(i.key, i.actual) + " of " + tvFmt(i.key, i.goal) + ", " + Math.round(i.pct) + "% of the target" + (exp == null ? "" : ", expected " + Math.round(exp) + "% by today");
      var inner = '<span class="db-tv__top"><b>' + KEYN[i.key] + "</b>" + (lead.indexOf(i.key) >= 0 ? ' <span class="db-lead">headline</span>' : "")
        + '<span class="db-tv__nums"><strong>' + tvFmt(i.key, i.actual) + "</strong> of " + tvFmt(i.key, i.goal) + "</span></span>"
        + '<span class="db-tv__track" role="img" aria-label="' + esc(label) + '"><i style="--w:' + w.toFixed(1) + "%;background:" + col + '"></i>'
        + (exp == null ? "" : '<em style="left:' + exp.toFixed(1) + '%"><u>today</u></em>') + (over ? '<s style="color:' + col + '">+' + over + "%</s>" : "") + "</span>"
        + '<span class="db-tv__sub"><span class="db-tv__pct" style="color:' + col + '">' + Math.round(i.pct) + "% met</span>" + esc(togo + today)
        + (can ? '<svg class="db-tv__chev" viewBox="0 0 12 12" aria-hidden="true"><path d="M3 4.5l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>' : "") + "</span>";
      return '<div class="db-tv__row" data-k="' + i.key + '">'
        + (can ? '<button type="button" class="db-tv__btn" aria-expanded="false" aria-controls="' + id + '">' + inner + "</button>" : '<div class="db-tv__btn db-tv__btn--static">' + inner + "</div>")
        + (can ? '<div class="db-tv__pace" id="' + id + '" hidden></div>' : "") + "</div>";
    }).join("");
  }
  function tvInfographic(items, lead) {
    if (!items.length) return "";
    return '<h3>Target vs achieved</h3><div class="db-tv" id="db-tv">' + tvRows(items, lead) + "</div>"
      + '<div class="db-legend2"><span><i class="sw" style="background:#14884a"></i>Met / on track</span><span><i class="sw" style="background:#e2780f"></i>Close</span><span><i class="sw" style="background:#ee1515"></i>Behind</span>'
      + '<span><i class="tick"></i>Where it should be today</span><span class="db-tv__hint">Select a row for its pace</span></div>';
  }
  // The pace chart for one KPI: cumulative achieved by posting day against the straight line to the target.
  function tvPace(item) {
    var c = R.campaign || {};
    if (!c.starts_at || !c.ends_at) return '<p class="db-note">Set the campaign dates to see its pace.</p>';
    var all = R.posts.filter(function (p) { return p.section === "campaign"; });
    var ser = series(all), key = item.key === "engagement" ? "eng" : item.key;
    var t0 = c.starts_at, t1 = c.ends_at, now = Math.min(Date.now() / 1000, t1), W = 600, H = 190, L = 8, Rr = 592, T = 14, B = 164;
    var span = Math.max(1, t1 - t0), ymax = Math.max(item.goal, item.actual) * 1.08 || 1;
    function X(t) { return L + (Math.min(Math.max(t, t0), t1) - t0) / span * (Rr - L); }
    function Y(v) { return B - v / ymax * (B - T); }
    var pts = [{ t: t0, v: 0 }].concat(ser.map(function (r) { return { t: Date.parse(r.d + "T12:00:00Z") / 1000, v: r[key] || 0, d: r.d }; }));
    pts = pts.filter(function (q) { return q.t <= now + 86400; });
    if (pts.length) pts.push({ t: now, v: pts[pts.length - 1].v });
    var line = pts.map(function (q) { return X(q.t).toFixed(1) + "," + Y(q.v).toFixed(1); }).join(" ");
    var area = pts.length > 1 ? "M" + X(pts[0].t).toFixed(1) + "," + B + " L" + line.split(" ").join(" L") + " L" + X(pts[pts.length - 1].t).toFixed(1) + "," + B + " Z" : "";
    var col = TV_COL[item.actual >= item.goal ? "good" : item.grade] || TV_COL.low;
    var svg = '<svg class="db-tv__svg" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc(KEYN[item.key] + " achieved so far against the pace to the target of " + tvFmt(item.key, item.goal)) + '" data-t0="' + t0 + '" data-t1="' + t1 + '">'
      + '<line x1="' + L + '" y1="' + B + '" x2="' + Rr + '" y2="' + B + '" class="ax"/><line x1="' + L + '" y1="' + Y(item.goal).toFixed(1) + '" x2="' + Rr + '" y2="' + Y(item.goal).toFixed(1) + '" class="gl"/>'
      + '<line x1="' + X(t0).toFixed(1) + '" y1="' + Y(0).toFixed(1) + '" x2="' + X(t1).toFixed(1) + '" y2="' + Y(item.goal).toFixed(1) + '" class="pace"/>'
      + (area ? '<path d="' + area + '" fill="' + col + '" opacity=".12"/>' : "") + (pts.length > 1 ? '<polyline points="' + line + '" fill="none" stroke="' + col + '" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>' : "")
      + '<line x1="' + X(now).toFixed(1) + '" y1="' + T + '" x2="' + X(now).toFixed(1) + '" y2="' + B + '" class="now"/>'
      + '<text x="' + Rr + '" y="' + (Y(item.goal) - 5).toFixed(1) + '" text-anchor="end" class="lb">Target ' + esc(tvFmt(item.key, item.goal)) + "</text>"
      + '<text x="' + L + '" y="' + (H - 6) + '" class="lb">' + esc(day(c.starts_at)) + '</text><text x="' + Rr + '" y="' + (H - 6) + '" text-anchor="end" class="lb">' + esc(day(c.ends_at)) + "</text>"
      + '<line class="cur" x1="0" y1="' + T + '" x2="0" y2="' + B + '" style="display:none"/><circle class="dot" r="6" cx="0" cy="0" fill="' + col + '" style="display:none"/></svg>';
    var last = pts.length ? pts[pts.length - 1].v : 0;
    var ahead = item.expected != null ? last - item.expected : null;
    var read = esc(KEYN[item.key]) + ": <b>" + esc(tvFmt(item.key, last)) + "</b> so far"
      + (ahead == null ? "" : ahead >= 0 ? " · " + esc(tvFmt(item.key, ahead)) + " ahead of the pace" : " · " + esc(tvFmt(item.key, -ahead)) + " behind the pace");
    return '<div class="db-tv__chart" tabindex="0" data-i="' + esc(JSON.stringify(pts.map(function (q) { return [Math.round(q.t), q.v]; }))) + '" data-k="' + item.key + '">' + svg
      + '<p class="db-tv__read" aria-live="polite">' + read + '</p><p class="db-tv__key"><span><i class="ln" style="background:' + col + '"></i>Achieved so far</span><span><i class="ln dash"></i>Pace to the target</span><span><i class="ln now"></i>Today</span></p></div>';
  }
  function bindTV() {
    var box = $("db-tv"); if (!box) return;
    requestAnimationFrame(function () { requestAnimationFrame(function () { box.classList.add("is-in"); }); });
    var items = {}; (R.progress.items || []).forEach(function (i) { items[i.key] = i; });
    box.addEventListener("click", function (e) {
      var b = e.target.closest(".db-tv__btn:not(.db-tv__btn--static)"); if (!b) return;
      var row = b.parentNode, pace = row.querySelector(".db-tv__pace"), open = b.getAttribute("aria-expanded") === "true";
      box.querySelectorAll(".db-tv__btn[aria-expanded=true]").forEach(function (o) { if (o !== b) { o.setAttribute("aria-expanded", "false"); o.parentNode.querySelector(".db-tv__pace").hidden = true; } });
      b.setAttribute("aria-expanded", open ? "false" : "true");
      if (!open && !pace.firstChild) pace.innerHTML = tvPace(items[row.getAttribute("data-k")]);
      pace.hidden = open;
    });
    // hover or arrow keys over a pace chart read the value on that day
    function readAt(chart, frac) {
      var pts = JSON.parse(chart.getAttribute("data-i")), svg = chart.querySelector("svg"), k = chart.getAttribute("data-k"), it = items[k];
      var t0 = +svg.getAttribute("data-t0"), t1 = +svg.getAttribute("data-t1"), t = t0 + frac * (t1 - t0), v = 0;
      pts.forEach(function (q) { if (q[0] <= t) v = q[1]; });
      var vb = svg.viewBox.baseVal, L = 8, Rr = 592, B = 164, T = 14, ymax = Math.max(it.goal, it.actual) * 1.08 || 1;
      var x = L + frac * (Rr - L), y = B - v / ymax * (B - T), cur = svg.querySelector(".cur"), dot = svg.querySelector(".dot");
      cur.setAttribute("x1", x); cur.setAttribute("x2", x); cur.style.display = ""; dot.setAttribute("cx", x); dot.setAttribute("cy", y); dot.style.display = "";
      var pace = it.goal * frac;
      chart.querySelector(".db-tv__read").innerHTML = esc(day(Math.round(t))) + ": <b>" + esc(tvFmt(k, v)) + "</b> achieved · pace " + esc(tvFmt(k, pace));
    }
    box.addEventListener("pointermove", function (e) {
      var chart = e.target.closest(".db-tv__chart"); if (!chart) return;
      var r = chart.querySelector("svg").getBoundingClientRect(); readAt(chart, Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)));
    });
    box.addEventListener("keydown", function (e) {
      var chart = e.target.closest && e.target.closest(".db-tv__chart"); if (!chart || (e.key !== "ArrowLeft" && e.key !== "ArrowRight")) return;
      var f = +(chart.getAttribute("data-f") || 1) + (e.key === "ArrowRight" ? 0.05 : -0.05); f = Math.min(1, Math.max(0, f));
      chart.setAttribute("data-f", f); readAt(chart, f); e.preventDefault();
    });
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
        + (plan.platform ? "<div><span>Benchmarked for</span><b class=\"db-goal-plat\">" + (ICONS[plan.platform] || "") + esc(plan.platform) + "</b><small>" + esc(plan.category || plan.template || "") + "</small></div>" : "") + "</div>";
      var rows = items.map(function (i) {
        var isR = i.key === "er", col = { good: "#14884a", moderate: "#e2780f", low: "#ee1515" }[i.grade], met = i.actual >= i.goal;
        return "<tr" + (lead.indexOf(i.key) >= 0 ? ' class="is-lead"' : "") + "><td><b>" + KEYN[i.key] + "</b>" + (lead.indexOf(i.key) >= 0 ? ' <span class="db-lead">headline</span>' : "") + "</td>"
          + '<td class="r">' + fv(i.key, i.goal) + "</td><td class=\"r\"><b>" + fv(i.key, i.actual) + "</b></td>"
          + '<td><div class="db-goal__track"><i style="width:' + Math.min(100, i.pct) + "%;background:" + col + '"></i>' + (isR ? "" : '<em style="left:' + Math.min(100, i.expected / i.goal * 100) + '%"></em>') + "</div><small>" + Math.round(i.pct) + "%" + (met ? " · met" : "") + "</small></td>"
          + '<td class="r muted">' + range(i.key) + "</td><td>" + sig(met ? "good" : i.grade) + "</td></tr>";
      }).join("");
      var out = head + objectiveBox() + tvInfographic(items, lead) + (items.length ? '<h3>Targets agreed</h3><table class="db-table db-goals-t"><thead><tr><th>KPI</th><th class="r">Minimum agreed</th><th class="r">Now</th><th>Progress</th><th class="r">Benchmark range</th><th></th></tr></thead><tbody>' + rows + "</tbody></table>"
        + '<div class="db-legend2"><span><i class="tick"></i>Where it should be today</span><span><i class="sw" style="background:#14884a"></i>Met / on track</span><span><i class="sw" style="background:#e2780f"></i>Close</span><span><i class="sw" style="background:#ee1515"></i>Behind</span></div>'
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
        + '</div><div class="db-legend2"><span><i class="sw band"></i>Normal range for creators this size</span><span><i class="dot"></i>This campaign now</span></div>';
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
      var list = posts(), by = {}; list.forEach(function (p) { var x = by[p.code] = by[p.code] || { posts: 0, views: 0, reach: 0, eng: 0, keys: {} }; if (!x.keys[pieceKey(p)]) { x.keys[pieceKey(p)] = 1; x.posts++; } x.views += p.views || 0; x.reach += p.reach || 0; x.eng += p.engagement || 0; });
      var rows = filtered() ? ranked(list).map(function (r) { return r.c; }) : R.creators;
      var tot = rows.reduce(function (a, c) { var x = filtered() ? (by[c.code] || {}) : { views: c.views, eng: c.engagement }; a.v += x.views || 0; a.e += x.eng || 0; return a; }, { v: 0, e: 0 });
      function share(v, t) { return t ? Math.round((v || 0) / t * 100) + "%" : "—"; }
      return (filtered() ? "" : '<h3 style="margin-top:0">How creators are scored · out of 100</h3>' + scoreBar()) + '<table class="db-table"><thead><tr><th>#</th><th>Creator</th><th>Posts</th><th>Views</th>' + (R.visibility.reach === false ? "" : "<th>Reach</th>") + '<th>Eng.</th><th>% of views</th><th>% of eng.</th><th>ER</th>' + (R.visibility.clicks && R.objective.links ? "<th>Clicks</th>" : "") + "<th>Score</th></tr></thead><tbody>"
        + rows.map(function (c, i) { var x = filtered() ? (by[c.code] || {}) : { posts: c.delivered, views: c.views, reach: c.reach, eng: c.engagement };
          var n = filtered() ? i + 1 : c.rank;
          return '<tr' + (n && n <= 3 ? ' class="is-top"' : "") + "><td>" + (n && n <= 3 ? '<span class="db-medal">' + medal(n) + "</span>" : (n || "—")) + '</td><td><span class="db-who">' + ava(c.photo) + "<b>" + who(c) + "</b></span></td><td>" + (x.posts || 0) + (c.planned && !filtered() ? "/" + c.planned : "") + "</td><td>" + num(x.views) + (R.visibility.reach === false ? "" : "</td><td>" + num(x.reach)) + "</td><td>" + num(x.eng)
            + "</td><td>" + share(x.views, tot.v) + "</td><td>" + share(x.eng, tot.e) + "</td><td>" + pct(c.er != null ? c.er : c.video_er) + "</td>" + (R.visibility.clicks && R.objective.links ? "<td>" + full(c.clicks) + "</td>" : "") + "<td>" + (c.score != null ? c.score.toFixed(0) : "—") + "</td></tr>"; }).join("")
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
      return '<section class="cmp-top"><div class="cmp-boxes">'
        + box(full(t.n), "comments read") + box(v(t.intent), "ask how to buy", "is-hot " + (t.small ? "" : cmTone("buy", share))) + box(v(t.pos), "positive", t.small ? "" : cmTone("pos", p)) + box(t.videos, "video" + (t.videos === 1 ? "" : "s"))
        + '</div><aside class="cmp-say" aria-label="The insight from the comments"><img class="cmp-say__av" src="../../assets/brand/helvy-connect/helvy-icon-180.png" alt="" width="48" height="48">'
        + '<div class="cmp-say__b"><p class="cmp-say__k">Helvi read the comments</p><p class="cmp-say__t">' + head1 + "</p>" + (sub1 ? '<p class="cmp-say__s">' + sub1 + "</p>" : "")
        + (C.next_read || C.last_read ? '<p class="cmp-say__d">' + (C.last_read ? "Read " + cmDay(C.last_read) : "") + (C.next_read ? (C.last_read ? " · " : "") + "next read " + cmDay(C.next_read) : "") + "</p>" : "")
        + "</div></aside></section>"
        + "<h3>The mood</h3>" + '<div class="cmp-mood">' + cmRing(t, "cm-ring--hero") + '<div class="cmp-mood__k">'
        + cmParts(t).map(function (s) { var n = t[s[0]]; return '<div class="cmp-mood__r" style="--c:' + CM_COL[s[0]] + '">' + '<i class="cm-face">' + CM_FACE[s[0]] + '</i><b>' + (t.small ? n : s[1] + "%") + "</b><span>" + s[2] + "</span><small>" + full(n) + " comments</small></div>"; }).join("")
        + "</div></div>"
        + (plats.length ? "<h3>Where the comments came from</h3>" + '<div class="cmp-src">' + cmShare(plats, t) + '<div class="cmp-plats">' + plats.map(function (k) { var x = t.plats[k]; x.small = x.n < 30;
            return '<div class="cmp-plat" style="--pc:' + (PCOL[k] || "#121212") + '"><p class="cmp-plat__n">' + (ICONS[k] || "") + "<b>" + esc(k) + "</b><em>" + cmPct(x.n, t.n) + "%</em></p>" + cmRing(x, "cm-ring--plat")
              + '<p class="cmp-plat__s"><span><b>' + full(x.n) + "</b>comments</span><span class=\"" + (x.small ? "" : cmTone("buy", x.intent / x.n)) + "\"><b>" + cmPct(x.intent, x.n) + "%</b>ask to buy</span></p></div>"; }).join("") + "</div></div>" : "")
        + (mainT ? "<h3>What people talk about</h3>" + '<div class="cmp-insight"><span class="cmp-insight__ic">' + cmIcon(mainT) + '</span><div class="cmp-insight__b">'
            + '<p class="cmp-insight__k">The biggest topic · <b>' + v(t.themes[mainT]) + "</b> of comments</p><p class=\"cmp-insight__t\">" + esc(mainT) + "</p>" + (AR[mainT] ? '<p class="cmp-insight__ar" dir="rtl" lang="ar">' + esc(AR[mainT]) + "</p>" : "")
            + ((TA[mainT] || []).length ? '<p class="cmp-insight__l">What they ask about it</p><div class="cmp-chips">' + asksOf(mainT, 4) + "</div>" : "") + "</div></div>"
            + (restT.length ? '<div class="cmp-insights">' + restT.map(function (q) {
                return '<div class="cmp-insight cmp-insight--sm" style="--w:' + (t.themes[q] / t.themes[mainT] * 100).toFixed(1) + '%"><span class="cmp-insight__ic">' + cmIcon(q) + '</span><div class="cmp-insight__b">'
                  + '<p class="cmp-insight__k"><b>' + v(t.themes[q]) + "</b> of comments</p><p class=\"cmp-insight__t\">" + esc(q) + "</p>" + (AR[q] ? '<p class="cmp-insight__ar" dir="rtl" lang="ar">' + esc(AR[q]) + "</p>" : "")
                  + '<i class="cmp-insight__bar"></i>' + ((TA[q] || []).length ? '<div class="cmp-chips">' + asksOf(q, 2) + "</div>" : "") + "</div></div>"; }).join("") + "</div>" : "")
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
              + '<defs><linearGradient id="cm-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0f5e63" stop-opacity=".22"/><stop offset="1" stop-color="#0f5e63" stop-opacity=".02"/></linearGradient></defs>'
              + '<line x1="' + L + '" y1="' + (H - B) + '" x2="' + (W - Rr) + '" y2="' + (H - B) + '" stroke="#e6e2db" stroke-width="1.5"/>'
              + '<path class="cmp-curve__a" d="' + area + '" fill="url(#cm-fill)"/><path class="cmp-curve__l" d="' + line + '" fill="none" stroke="#0f5e63" stroke-width="3.5" stroke-linecap="round"/>'
              + pts.map(function (p, i) { var d = ds[i], isPk = d === pk;
                  return '<g class="cmp-curve__p' + (isPk ? " is-pk" : "") + '"><circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="' + (isPk ? 8 : 5.5) + '"/>'
                    + '<text x="' + p[0].toFixed(1) + '" y="' + (p[1] - 14).toFixed(1) + '" text-anchor="middle" class="cmp-curve__v">' + t.days[d] + "</text>"
                    + '<text x="' + p[0].toFixed(1) + '" y="' + (H - 10) + '" text-anchor="middle" class="cmp-curve__d">' + day(d) + "</text></g>"; }).join("")
              + '</svg></div><p class="cmp-days__n">The conversation peaked on <b>' + day(pk) + "</b> with " + mx + " comments.</p>"; })() : "")
        + (quotes.length ? "<h3>In their words</h3>" + '<div class="cmp-quotes">' + quotes.map(function (q) {
            return '<article class="cmp-quote"><q dir="auto">' + esc(q.text) + "</q>" + (q.gloss ? "<p>“" + esc(q.gloss) + "”</p>" : "")
              + "<footer>" + ava(pics[q.code]) + "<b>" + esc(names[q.code] || q.code || "") + "</b><span>" + (ICONS[q.platform] || esc(q.platform)) + "</span></footer></article>"; }).join("") + "</div>" : "")
        + "<h3>By creator</h3>" + '<div class="cmp-who">' + who.map(function (c) { var w = t.by[c], few = w.n < ((C.min_sample) || 30), top = cmTop(w.themes)[0]; w.small = few;
            return '<div class="cmp-who__r">' + ava(pics[c]) + '<span class="cmp-who__n"><b>' + esc(names[c] || c) + "</b><small>" + w.plats.map(function (x) { return ICONS[x] || esc(x); }).join("") + "</small></span>"
              + cmRing(w, "cm-ring--who") + '<span class="cmp-who__c cmp-who__c--n"><b>' + full(w.n) + "</b><small>comments</small></span>"
              + '<span class="cmp-who__c cmp-who__c--b ' + (few ? "" : cmTone("buy", w.intent / w.n)) + '"><b>' + (few ? w.intent : cmPct(w.intent, w.n) + "%") + "</b><small>" + (few ? "of " + w.n + " ask" : "ask to buy") + "</small></span>"
              + '<span class="cmp-who__t">' + (few ? "<small>Too few to say</small>" : cmIcon(top) + "<span>" + esc(top || "—") + ar(top) + "</span>") + "</span></div>"; }).join("")
        + silent.map(function (c) { return '<div class="cmp-who__r is-quiet">' + ava(c.photo) + '<span class="cmp-who__n"><b>' + esc(c.name) + "</b></span><span class=\"cmp-who__wait\">" + (c.posts ? "Comments not read yet" : "No video yet") + "</span></div>"; }).join("")
        + "</div>"
        + "";
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
        var grade = er == null || !b ? null : er >= b[1] ? "good" : er >= b[0] ? "moderate" : "low";
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
      + '<div class="db-post__stats">' + stats(p).map(function (x) { return "<div><small>" + x[0] + "</small><b>" + x[1] + "</b></div>"; }).join("") + "</div></a>";
  }
  var TITLES = { kpi: "Goals & benchmarks", trend: "Views & engagement", creators: "All creators", stage: "Campaign stage", mix: "Content by format", posts: "All posts", geo: "What people say", plat: "Platforms", clicks: "Affiliate clicks" };
  var lastFocus = null;
  function openPanel(area) {
    if (!PANEL[area]) return;
    lastFocus = document.activeElement;
    $("db-panel-title").textContent = TITLES[area] + (filtered() && area !== "stage" ? " · filtered" : "");
    $("db-panel-body").innerHTML = PANEL[area]();
    if (area === "kpi") bindTV();
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
