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
  // Official platform marks (simple-icons, CC0): solid glyphs in each brand's own colours, over the shared outline set.
  var BRAND = {"Instagram": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path fill=\"url(#hv-ig)\" d=\"M7.0301.084c-1.2768.0602-2.1487.264-2.911.5634-.7888.3075-1.4575.72-2.1228 1.3877-.6652.6677-1.075 1.3368-1.3802 2.127-.2954.7638-.4956 1.6365-.552 2.914-.0564 1.2775-.0689 1.6882-.0626 4.947.0062 3.2586.0206 3.6671.0825 4.9473.061 1.2765.264 2.1482.5635 2.9107.308.7889.72 1.4573 1.388 2.1228.6679.6655 1.3365 1.0743 2.1285 1.38.7632.295 1.6361.4961 2.9134.552 1.2773.056 1.6884.069 4.9462.0627 3.2578-.0062 3.668-.0207 4.9478-.0814 1.28-.0607 2.147-.2652 2.9098-.5633.7889-.3086 1.4578-.72 2.1228-1.3881.665-.6682 1.0745-1.3378 1.3795-2.1284.2957-.7632.4966-1.636.552-2.9124.056-1.2809.0692-1.6898.063-4.948-.0063-3.2583-.021-3.6668-.0817-4.9465-.0607-1.2797-.264-2.1487-.5633-2.9117-.3084-.7889-.72-1.4568-1.3876-2.1228C21.2982 1.33 20.628.9208 19.8378.6165 19.074.321 18.2017.1197 16.9244.0645 15.6471.0093 15.236-.005 11.977.0014 8.718.0076 8.31.0215 7.0301.0839m.1402 21.6932c-1.17-.0509-1.8053-.2453-2.2287-.408-.5606-.216-.96-.4771-1.3819-.895-.422-.4178-.6811-.8186-.9-1.378-.1644-.4234-.3624-1.058-.4171-2.228-.0595-1.2645-.072-1.6442-.079-4.848-.007-3.2037.0053-3.583.0607-4.848.05-1.169.2456-1.805.408-2.2282.216-.5613.4762-.96.895-1.3816.4188-.4217.8184-.6814 1.3783-.9003.423-.1651 1.0575-.3614 2.227-.4171 1.2655-.06 1.6447-.072 4.848-.079 3.2033-.007 3.5835.005 4.8495.0608 1.169.0508 1.8053.2445 2.228.408.5608.216.96.4754 1.3816.895.4217.4194.6816.8176.9005 1.3787.1653.4217.3617 1.056.4169 2.2263.0602 1.2655.0739 1.645.0796 4.848.0058 3.203-.0055 3.5834-.061 4.848-.051 1.17-.245 1.8055-.408 2.2294-.216.5604-.4763.96-.8954 1.3814-.419.4215-.8181.6811-1.3783.9-.4224.1649-1.0577.3617-2.2262.4174-1.2656.0595-1.6448.072-4.8493.079-3.2045.007-3.5825-.006-4.848-.0608M16.953 5.5864A1.44 1.44 0 1 0 18.39 4.144a1.44 1.44 0 0 0-1.437 1.4424M5.8385 12.012c.0067 3.4032 2.7706 6.1557 6.173 6.1493 3.4026-.0065 6.157-2.7701 6.1506-6.1733-.0065-3.4032-2.771-6.1565-6.174-6.1498-3.403.0067-6.156 2.771-6.1496 6.1738M8 12.0077a4 4 0 1 1 4.008 3.9921A3.9996 3.9996 0 0 1 8 12.0077\"/></svg>", "TikTok": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path fill=\"#25f4ee\" transform=\"translate(-.55 -.45)\" d=\"M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z\"/><path fill=\"#fe2c55\" transform=\"translate(.55 .45)\" d=\"M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z\"/><path fill=\"currentColor\" d=\"M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z\"/></svg>", "Snapchat": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path fill=\"#fffc00\" stroke=\"#121212\" stroke-width=\".9\" stroke-linejoin=\"round\" d=\"M12.206.793c.99 0 4.347.276 5.93 3.821.529 1.193.403 3.219.299 4.847l-.003.06c-.012.18-.022.345-.03.51.075.045.203.09.401.09.3-.016.659-.12 1.033-.301.165-.088.344-.104.464-.104.182 0 .359.029.509.09.45.149.734.479.734.838.015.449-.39.839-1.213 1.168-.089.029-.209.075-.344.119-.45.135-1.139.36-1.333.81-.09.224-.061.524.12.868l.015.015c.06.136 1.526 3.475 4.791 4.014.255.044.435.27.42.509 0 .075-.015.149-.045.225-.24.569-1.273.988-3.146 1.271-.059.091-.12.375-.164.57-.029.179-.074.36-.134.553-.076.271-.27.405-.555.405h-.03c-.135 0-.313-.031-.538-.074-.36-.075-.765-.135-1.273-.135-.3 0-.599.015-.913.074-.6.104-1.123.464-1.723.884-.853.599-1.826 1.288-3.294 1.288-.06 0-.119-.015-.18-.015h-.149c-1.468 0-2.427-.675-3.279-1.288-.599-.42-1.107-.779-1.707-.884-.314-.045-.629-.074-.928-.074-.54 0-.958.089-1.272.149-.211.043-.391.074-.54.074-.374 0-.523-.224-.583-.42-.061-.192-.09-.389-.135-.567-.046-.181-.105-.494-.166-.57-1.918-.222-2.95-.642-3.189-1.226-.031-.063-.052-.15-.055-.225-.015-.243.165-.465.42-.509 3.264-.54 4.73-3.879 4.791-4.02l.016-.029c.18-.345.224-.645.119-.869-.195-.434-.884-.658-1.332-.809-.121-.029-.24-.074-.346-.119-1.107-.435-1.257-.93-1.197-1.273.09-.479.674-.793 1.168-.793.146 0 .27.029.383.074.42.194.789.3 1.104.3.234 0 .384-.06.465-.105l-.046-.569c-.098-1.626-.225-3.651.307-4.837C7.392 1.077 10.739.807 11.727.807l.419-.015h.06z\"/></svg>", "YouTube": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path fill=\"#ff0000\" d=\"M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z\"/></svg>", "Facebook": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path fill=\"#0866ff\" d=\"M9.101 23.691v-7.98H6.627v-3.667h2.474v-1.58c0-4.085 1.848-5.978 5.858-5.978.401 0 .955.042 1.468.103a8.68 8.68 0 0 1 1.141.195v3.325a8.623 8.623 0 0 0-.653-.036 26.805 26.805 0 0 0-.733-.009c-.707 0-1.259.096-1.675.309a1.686 1.686 0 0 0-.679.622c-.258.42-.374.995-.374 1.752v1.297h3.919l-.386 2.103-.287 1.564h-3.246v8.245C19.396 23.238 24 18.179 24 12.044c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.628 3.874 10.35 9.101 11.647Z\"/></svg>", "X": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path fill=\"currentColor\" d=\"M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z\"/></svg>"};
  ICONS = (function (base) { var o = {}, k; for (k in base) o[k] = base[k]; for (k in BRAND) o[k] = BRAND[k]; return o; })(ICONS);
  if (document.body && !document.getElementById("hv-ig")) document.body.insertAdjacentHTML("beforeend", "<svg width=\"0\" height=\"0\" style=\"position:absolute\" aria-hidden=\"true\"><defs><linearGradient id=\"hv-ig\" x1=\"0\" y1=\"1\" x2=\"1\" y2=\"0\"><stop offset=\"0\" stop-color=\"#feda75\"/><stop offset=\".25\" stop-color=\"#fa7e1e\"/><stop offset=\".5\" stop-color=\"#d62976\"/><stop offset=\".75\" stop-color=\"#962fbf\"/><stop offset=\"1\" stop-color=\"#4f5bd5\"/></linearGradient></defs></svg>");
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

  function post(path, body) {
    return fetch(API + path, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { j.status = r.status; return j; }); });
  }
  var CAN_START = false;

  /* ---------------------------------------------------------------- gate */

  var REFUSALS = { revoked: "This code has been withdrawn.", expired: "This code has expired.",
    exhausted: "This code has been used up.", devices: "This code is already open on its maximum number of devices.",
    otherlink: "That code is for a different campaign. Use the code that came with this link.",
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
      body: JSON.stringify({ code: $("cat-code").value.trim(), lite: true, link: token() ? "c:" + token() : "c:list" }) })
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
    // "Back to dashboard" belongs to one campaign's report, not to the list.
    if (which !== "report") $("mx-dash").hidden = true;
  }
  function empty(msg) { $("mx-empty").textContent = msg; show("empty"); }

  function route() {
    var t = token();
    if (t) return openReport(t);
    // Item 176: campaign tracking opens on the board (owner, 2026-10-20). /api/campaigns still says whether this
    // reader may start a campaign themselves; the board is /api/board.
    Promise.all([get("/api/board"), get("/api/campaigns").catch(function () { return {}; })]).then(function (r) {
      unlocked();
      CAN_START = !!r[1].can_start && r[0].role === "client";
      $("mx-all").hidden = true;
      BOARD = r[0];
      showBoard();
    }).catch(function (err) { if (err && err.locked) lock(); else empty("Could not load your campaigns. Please try again."); });
  }

  /* ------------------------------------------------------- campaign board */
  // Items 174, 176, 177, 182 (owner, 2026-10-20). Six columns, one card per campaign with its client's logo and the
  // selections it holds. Admins move a campaign between columns and set it Live / Unlive; everyone else reads.
  // Pins are per person and float a campaign to the top of its column and of the switcher.
  var BOARD = null, LANE = 0;
  var SVG = {
    pin: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4h6l-1 5 3 3v2H7v-2l3-3-1-5z"/><path d="M12 14v6"/></svg>',
    chev: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>',
    arrow: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
    search: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/></svg>',
    list: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h10"/></svg>'
  };
  function initials(s) {
    return String(s || "?").trim().split(/\s+/).slice(0, 2).map(function (w) { return w.charAt(0); }).join("").toUpperCase() || "?";
  }
  function brand(c, size) {
    var cls = "mx-bd-logo" + (size ? " mx-bd-logo--" + size : "");
    if (c.logos && c.logos.length) {
      return '<span class="' + cls + '"><img src="' + esc(c.logos[0]) + '" alt="' + esc(c.client || c.name) + '" loading="lazy" '
        + 'onerror="this.parentNode.classList.add(\'is-mono\');this.parentNode.textContent=\'' + esc(initials(c.client || c.name)) + '\'"></span>';
    }
    return '<span class="' + cls + ' is-mono" aria-hidden="true">' + esc(initials(c.client || c.name)) + "</span>";
  }
  function stageLabel(key) {
    var s = (BOARD.stages || []).filter(function (x) { return x.key === key; })[0];
    return s ? s.label : key;
  }
  function when(c) {
    if (!c.starts_at || !c.ends_at) return "";
    var now = Date.now() / 1000, span = Math.max(1, Math.round((c.ends_at - c.starts_at) / 86400));
    if (now < c.starts_at) return "Starts " + day(c.starts_at, false);
    if (now <= c.ends_at) return "Day " + Math.min(span, Math.max(1, Math.ceil((now - c.starts_at) / 86400))) + " of " + span;
    return day(c.starts_at, false) + " – " + day(c.ends_at, false);
  }
  function openHref(c) {
    if (c.report) return "dashboard/#t=" + encodeURIComponent(c.token);
    return c.selections.length ? "../selection/#s=" + encodeURIComponent(c.selections[0].token) : "";
  }
  function bdCard(c) {
    var href = openHref(c), can = BOARD.can_move;
    var sels = c.selections.length ? '<ul class="mx-bd-sels" aria-label="Selections in ' + esc(c.name) + '">' + c.selections.map(function (s) {
      return '<li><a href="../selection/#s=' + encodeURIComponent(s.token) + '"><span class="mx-bd-sel__n">' + esc(s.name) + "</span>"
        + '<span class="mx-bd-sel__c">' + s.creators + (s.creators === 1 ? " creator" : " creators") + "</span></a></li>";
    }).join("") + "</ul>" : '<p class="mx-bd-none">No selection yet.</p>';
    var meta = [c.client, when(c)].filter(Boolean).join(" · ");
    var admin = "";
    if (can) {
      var opts = BOARD.stages.map(function (s) { return '<option value="' + s.key + '"' + (s.key === c.stage ? " selected" : "") + ">" + esc(s.label) + "</option>"; }).join("");
      admin = '<div class="mx-bd-admin"><label class="mx-bd-move"><span class="mx-sr">Stage of ' + esc(c.name) + '</span><select data-stage="' + esc(c.token) + '">' + opts + "</select>" + SVG.chev + "</label>"
        + (c.status === "live" ? '<button type="button" class="mx-bd-live is-on" data-live="0" data-t="' + esc(c.token) + '">Unlive</button>'
          : (c.status === "draft" ? '<button type="button" class="mx-bd-live" data-live="1" data-t="' + esc(c.token) + '">Go live</button>' : "")) + "</div>";
    }
    return '<article class="mx-bd-card' + (c.my_pin ? " is-pinned" : "") + (c.demo ? " is-demo" : "") + '" data-token="' + esc(c.token) + '">'
      + '<div class="mx-bd-card__top">' + brand(c) + '<button type="button" class="mx-bd-pin' + (c.my_pin ? " is-on" : "") + '" data-pin="' + esc(c.token) + '" aria-pressed="' + (c.my_pin ? "true" : "false")
      + '" title="' + (c.my_pin ? "Unpin" : "Pin to the top") + '" aria-label="' + (c.my_pin ? "Unpin " : "Pin ") + esc(c.name) + '">' + SVG.pin + "</button></div>"
      + '<h3 class="mx-bd-card__name">' + (href ? '<a href="' + href + '">' + esc(c.name) + "</a>" : esc(c.name)) + "</h3>"
      + (meta ? '<p class="mx-bd-card__meta">' + esc(meta) + "</p>" : "")
      + (c.demo ? '<span class="mx-bd-tag mx-bd-tag--demo" title="The team\'s demo campaign">Demo</span>' : "")
      + (c.kam ? '<p class="mx-bd-card__kam">KAM ' + esc(c.kam.name || c.kam.email) + "</p>" : "")
      + sels + admin
      + (c.report ? '<a class="mx-bd-open" href="dashboard/#t=' + encodeURIComponent(c.token) + '">Open dashboard ' + SVG.arrow + "</a>" : "")
      + "</article>";
  }
  function showBoard() {
    document.title = "My campaigns — HELVi Connect";
    var list = BOARD.campaigns || [];
    if (!list.length) { showNone(); return; }
    $("mx-list-lede").textContent = BOARD.role === "client"
      ? "Every campaign HelloVoice runs for you, from the first draft to the final report. Pin the ones you follow most."
      : BOARD.can_move ? "Every campaign, by stage. Move a campaign with its stage menu; Go live and Unlive are yours alone."
        : "Your clients' campaigns, by stage. HelloVoice admins move them between stages.";
    var by = {};
    BOARD.stages.forEach(function (s) { by[s.key] = []; });
    list.forEach(function (c) { (by[c.stage] || (by[c.stage] = [])).push(c); });
    var tabs = '<div class="mx-bd-tabs" role="tablist" aria-label="Stages">' + BOARD.stages.map(function (s, i) {
      return '<button type="button" role="tab" class="mx-bd-tab' + (s.key === "live" ? " mx-bd-tab--live" : "") + '" data-lane="' + i + '" aria-selected="' + (i === LANE ? "true" : "false") + '">'
        + esc(s.label) + "<b>" + by[s.key].length + "</b></button>";
    }).join("") + "</div>";
    var lanes = '<div class="mx-bd" id="mx-bd">' + BOARD.stages.map(function (s, i) {
      var cards = by[s.key];
      return '<section class="mx-bd-lane mx-bd-lane--' + s.key + '" data-i="' + i + '" aria-labelledby="mx-bd-h-' + s.key + '">'
        + '<header class="mx-bd-lane__head"><h2 id="mx-bd-h-' + s.key + '">' + esc(s.label) + "</h2><b>" + cards.length + "</b>"
        + '<p class="mx-bd-lane__hint">' + esc(s.hint) + "</p></header>"
        + '<div class="mx-bd-lane__cards">' + (cards.length ? cards.map(bdCard).join("") : '<p class="mx-bd-empty">Nothing here.</p>') + "</div></section>";
    }).join("") + "</div>";
    $("mx-list-sum").innerHTML = "";
    $("mx-list-items").innerHTML = '<div class="mx-bd-bar" id="mx-bd-bar">' + startPanel() + "</div>"
      + '<p class="mx-bd-say" id="mx-bd-say" role="status" aria-live="polite"></p>' + tabs + lanes;
    show("list");
    wireStart();
    wireBoard();
    mountSwitcher(list, "");
  }
  function say(text, bad) {
    var el = $("mx-bd-say"); if (!el) return;
    el.innerHTML = text; el.className = "mx-bd-say is-on" + (bad ? " is-bad" : "");
    clearTimeout(say.t); say.t = setTimeout(function () { el.className = "mx-bd-say"; }, 6000);
  }
  function reloadBoard(msg, bad) {
    get("/api/board").then(function (b) { BOARD = b; showBoard(); if (msg) say(msg, bad); });
  }
  function wireBoard() {
    var bd = $("mx-bd"), host = $("mx-list-items");
    // Phones: the lanes swipe; the stage tabs follow the swipe and jump to a lane.
    host.querySelectorAll(".mx-bd-tab").forEach(function (b) {
      b.addEventListener("click", function () {
        LANE = +b.getAttribute("data-lane");
        var lane = bd.querySelector('.mx-bd-lane[data-i="' + LANE + '"]');
        jumping = Date.now();
        bd.scrollLeft = lane.offsetLeft - bd.offsetLeft;
        mark();
      });
    });
    function mark() {
      host.querySelectorAll(".mx-bd-tab").forEach(function (b) {
        var on = +b.getAttribute("data-lane") === LANE;
        b.setAttribute("aria-selected", on ? "true" : "false");
        if (on && b.parentNode.scrollWidth > b.parentNode.clientWidth) b.parentNode.scrollLeft = b.offsetLeft - b.parentNode.offsetLeft - 16;
      });
    }
    var tick = null, jumping = 0;
    bd.addEventListener("scroll", function () {
      clearTimeout(tick);
      tick = setTimeout(function () {
        if (Date.now() - jumping < 900) return;          // a tab jump is still gliding there
        var w = bd.querySelector(".mx-bd-lane").offsetWidth || 1;
        var i = Math.round(bd.scrollLeft / (w + 12));
        if (i !== LANE) { LANE = Math.max(0, Math.min(5, i)); mark(); }
      }, 80);
    }, { passive: true });
    if (LANE && matchMedia("(max-width: 899px)").matches) {
      var lane = bd.querySelector('.mx-bd-lane[data-i="' + LANE + '"]');
      if (lane) bd.scrollLeft = lane.offsetLeft - bd.offsetLeft;
    }
    host.querySelectorAll("[data-pin]").forEach(function (b) {
      b.addEventListener("click", function () {
        var on = b.getAttribute("aria-pressed") !== "true";
        b.disabled = true;
        post("/api/board/pin", { t: b.getAttribute("data-pin"), on: on }).then(function (j) {
          if (j && j.ok) reloadBoard(on ? "Pinned to the top." : "Unpinned.");
          else { b.disabled = false; say("Couldn't change that pin. Please try again.", true); }
        });
      });
    });
    host.querySelectorAll("[data-stage]").forEach(function (sel) {
      var was = sel.value;
      sel.addEventListener("change", function () {
        sel.disabled = true;
        post("/api/board/stage", { t: sel.getAttribute("data-stage"), to: sel.value }).then(function (j) {
          if (j && j.ok) { reloadBoard(esc(j.message)); return; }
          sel.disabled = false; sel.value = was;
          say(esc((j && j.message) || "Couldn't move that campaign.") + (j && j.setup ? ' <a href="' + esc(j.setup) + '">Open its setup</a>' : ""), true);
        });
      });
    });
    host.querySelectorAll("[data-live]").forEach(function (b) {
      b.addEventListener("click", function () {
        b.disabled = true;
        post("/api/board/live", { t: b.getAttribute("data-t"), on: b.getAttribute("data-live") === "1" }).then(function (j) {
          if (j && j.ok) { reloadBoard(esc(j.message)); return; }
          b.disabled = false;
          say(esc((j && j.message) || "Couldn't change that.") + (j && j.setup ? ' <a href="' + esc(j.setup) + '">Open its setup</a>' : ""), true);
        });
      });
    });
  }

  /* ------------------------------------------------------ campaign switcher */
  function reportBar() {
    var bar = $("mx-csbar");
    if (!bar) {
      bar = document.createElement("div");
      bar.className = "cat-pad mx-csbar";
      bar.innerHTML = '<div class="cat-container mx-csbar__in" id="mx-csbar"><a class="mx-csbar__back" href="#list">' + SVG.arrow + "Campaign board</a></div>";
      var bug = document.querySelector("#mx-report .mx-bug");
      bug.parentNode.insertBefore(bar, bug);
      bar = $("mx-csbar");
    }
    return bar;
  }
  // Item 176: jump between my campaigns from the board or from inside a report. Pinned first, then by stage order.
  function mountSwitcher(list, current) {
    var old = $("mx-cs"); if (old) old.remove();
    var links = current ? reportBar() : $("mx-bd-bar");
    if (!links || !list.length) return;
    var order = { live: 0, approved: 1, review: 2, shortlisting: 3, draft: 4, completed: 5 };
    var items = list.slice().sort(function (a, b) {
      return (a.my_pin ? 0 : 1) - (b.my_pin ? 0 : 1) || (order[a.stage] - order[b.stage]);
    });
    var cur = items.filter(function (c) { return c.token === current; })[0];
    var wrap = document.createElement("div");
    wrap.className = "mx-cs"; wrap.id = "mx-cs";
    wrap.innerHTML = '<button type="button" class="mx-link mx-cs__btn" aria-haspopup="dialog" aria-expanded="false" aria-controls="mx-cs-pop">'
      + (cur ? brand(cur, "xs") + '<span class="mx-cs__cur">' + esc(cur.name) + "</span>" : SVG.list + "<span>Switch campaign</span>") + SVG.chev + "</button>"
      + '<div class="mx-cs__pop" id="mx-cs-pop" role="dialog" aria-label="Switch campaign" hidden>'
      + '<label class="mx-cs__q">' + SVG.search + '<input type="search" placeholder="Find a campaign" aria-label="Find a campaign" autocomplete="off"></label>'
      + '<ul class="mx-cs__list"></ul>'
      + '<a class="mx-cs__all" href="#list">All campaigns on the board ' + SVG.arrow + "</a></div>";
    links.appendChild(wrap);
    var btn = wrap.querySelector(".mx-cs__btn"), pop = wrap.querySelector(".mx-cs__pop"), q = wrap.querySelector("input"), ul = wrap.querySelector("ul");
    function draw() {
      var v = q.value.trim().toLowerCase();
      var hits = items.filter(function (c) { return !v || (c.name + " " + c.client).toLowerCase().indexOf(v) >= 0; });
      ul.innerHTML = hits.length ? hits.map(function (c) {
        var href = c.report ? "#t=" + encodeURIComponent(c.token) : openHref(c);
        return '<li><a href="' + esc(href || "#list") + '"' + (c.token === current ? ' aria-current="true"' : "") + ">" + brand(c, "xs")
          + '<span class="mx-cs__n"><b>' + esc(c.name) + "</b><small>" + esc([c.client, stageLabel(c.stage)].filter(Boolean).join(" · ")) + "</small></span>"
          + (c.my_pin ? '<span class="mx-cs__pin" title="Pinned">' + SVG.pin + "</span>" : "")
          + (c.stage === "live" ? '<span class="mx-cs__live" aria-label="Live"></span>' : "") + "</a></li>";
      }).join("") : '<li class="mx-cs__none">No campaign matches.</li>';
    }
    function open(on) {
      pop.hidden = !on; btn.setAttribute("aria-expanded", on ? "true" : "false");
      if (on) { q.value = ""; draw(); setTimeout(function () { q.focus(); }, 0); }
    }
    btn.addEventListener("click", function () { open(pop.hidden); });
    q.addEventListener("input", draw);
    wrap.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { open(false); btn.focus(); }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        var as = [].slice.call(ul.querySelectorAll("a")); if (!as.length) return;
        var i = as.indexOf(document.activeElement), dir = e.key === "ArrowDown" ? 1 : -1;
        e.preventDefault();
        as[i < 0 ? (dir > 0 ? 0 : as.length - 1) : (i + dir + as.length) % as.length].focus();
      }
    });
    ul.addEventListener("click", function () { open(false); });
    document.addEventListener("click", function (e) { if (!wrap.contains(e.target)) open(false); });
  }

  // Start a campaign (owner, 2026-10-17): a signed-in client names it; it lands as a draft their
  // account manager approves. One button, one small inline form.
  function startPanel() {
    if (!CAN_START) return "";
    return '<section class="mx-start" aria-label="Start a campaign"><button type="button" class="mx-start__open" aria-expanded="false" aria-controls="mx-start-form">+ Start a campaign</button>'
      + '<form class="mx-start__form" id="mx-start-form" hidden novalidate><label for="mx-start-name">Campaign name</label>'
      + '<input id="mx-start-name" maxlength="120" autocomplete="off" placeholder="e.g. Ramadan sun care 2027">'
      + '<label for="mx-start-note">What do you want it to do? <small>(optional)</small></label>'
      + '<textarea id="mx-start-note" maxlength="500" rows="2" placeholder="Goal, dates, creators you have in mind"></textarea>'
      + '<div class="mx-start__act"><button type="submit" class="mx-camp__go">Send to my account manager</button></div>'
      + '<p class="mx-start__msg" role="status"></p></form></section>';
  }
  function wireStart() {
    var host = $("mx-list-items");
    var open = host.querySelector(".mx-start__open"), form = host.querySelector(".mx-start__form");
    if (open && form) {
      open.addEventListener("click", function () {
        var on = form.hidden; form.hidden = !on; open.setAttribute("aria-expanded", on ? "true" : "false");
        if (on) $("mx-start-name").focus();
      });
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var msg = form.querySelector(".mx-start__msg"), btn = form.querySelector("button[type=submit]");
        var name = $("mx-start-name").value.trim();
        if (name.length < 3) { msg.textContent = "Give the campaign a name (3 letters or more)."; $("mx-start-name").focus(); return; }
        btn.disabled = true; msg.textContent = "Sending…";
        post("/api/campaign/start", { name: name, note: $("mx-start-note").value.trim() }).then(function (j) {
          if (j && j.ok) { route(); return; }
          btn.disabled = false; msg.textContent = (j && j.message) || "Couldn't start that. Please try again.";
        }).catch(function () { btn.disabled = false; msg.textContent = "Couldn't reach the server. Please try again."; });
      });
    }
    host.querySelectorAll("[data-build]").forEach(function (b) {
      b.addEventListener("click", function () {
        b.disabled = true; var was = b.textContent; b.textContent = "Opening…";
        post("/api/campaign/build-selection", { t: b.getAttribute("data-build") }).then(function (j) {
          if (j && j.ok && j.token) {
            var base = new URL("../", location.href).href;
            location.href = j.existing ? base + "selection/#s=" + encodeURIComponent(j.token)
              : base + "#n=" + encodeURIComponent(j.name || "") + "&c=&s=" + encodeURIComponent(j.token);
            return;
          }
          b.disabled = false; b.textContent = was;
        }).catch(function () { b.disabled = false; b.textContent = was; });
      });
    });
  }

  // No campaigns yet: say what will appear here and how to get started,
  // with a full-strength preview of a campaign card.
  function showNone() {
    $("mx-list-sum").innerHTML = "";
    $("mx-list-lede").textContent = CAN_START ? "Start a campaign yourself, or it will appear here when HelloVoice starts one for you."
      : "Your campaigns will appear here as soon as HelloVoice starts one for you.";
    $("mx-list-items").innerHTML = startPanel() + '<section class="mx-none"><div class="mx-none__copy"><h2>No campaigns yet</h2>'
      + "<p>Each campaign gets a live dashboard here: posts going live, people reached, engagement, and how far it is towards its objective, updated every day.</p>"
      + '<ol class="mx-none__steps"><li><b>1</b><span>Pick creators from the catalogue and send us your shortlist.</span></li>'
      + "<li><b>2</b><span>We agree the brief, the targets and the dates with you.</span></li>"
      + "<li><b>3</b><span>The campaign goes live and you follow it here, day by day.</span></li></ol>"
      + '<div class="mx-none__actions"><a class="mx-camp__go" href="../">Browse the creators →</a><a class="mx-none__mail" href="https://hellovoice.co.uk/service/influencer-campaigns/" target="_blank" rel="noopener">See our influencer work ↗</a></div></div>'
      + '<div class="mx-none__ghost" aria-hidden="true"><div class="mx-none__brands"><img src="../assets/brand/logo.png" alt=""><span>×</span><b>Your brand</b><span class="mx-camp__state mx-camp__state--live">Live</span></div>'
      + '<p class="mx-none__sub">Track your campaign performance, day by day.</p>'
      + '<div class="mx-camp__prog"><div class="mx-tl__head"><div><span class="mx-tl__label">Campaign timeline</span><b class="mx-tl__stage">Publishing</b></div><div class="mx-tl__count"><b>Day 6 of 20</b><em>14 days left</em></div></div>'
      + '<div class="mx-tl__track">' + "ddddddda.".split("").map(function (k) { return '<span class="mx-tl__seg mx-tl__seg--' + ({ d: "done", a: "active", ".": "pending" })[k] + '"></span>'; }).join("") + "</div>"
      + '<div class="mx-tl__foot"><span></span><span>7 of 9 steps done</span><span></span></div></div><p class="mx-none__tag">Example</p></div></section>';
    show("list");
    wireStart();
  }
  // Where an audience number came from: the creators' own analyses, the average
  // of every analysed profile, or a mix of the two.
  function audNote(a) {
    var s = "Creators' profile audience, weighted by reach";
    if (a.basis === "partial") s += " · " + a.coverage.toFixed(0) + "% of reach analysed so far, the rest not yet analysed";
    return s;
  }
  function tile(label, value, tone) { return '<div class="mx-sum__tile' + (tone ? " mx-sum__tile--" + tone : "") + '"><b>' + value + "</b><span>" + label + "</span></div>"; }
  // The campaign's timeline: one segment per scope-of-work step, in order,
  // coloured done / in progress / to come, with the current stage and the
  // day count above it.
  function progress(R, ended) {
    var c = R.campaign || {}, steps = (c.steps || []).filter(function (x) { return x.on !== false; });
    var now = Date.now() / 1000, span = c.starts_at && c.ends_at ? Math.max(1, Math.round((c.ends_at - c.starts_at) / 86400)) : 0;
    var dn = span ? Math.min(span, Math.max(0, Math.ceil((now - c.starts_at) / 86400))) : 0;
    var done = ended ? steps.length : steps.filter(function (x) { return x.state === "done"; }).length;
    var cur = steps.filter(function (x) { return x.state === "active"; })[0];
    var stage = ended || (steps.length && done === steps.length) ? "Completed" : cur ? cur.label : steps.length && !done ? "Not started" : "In progress";
    var count = !span ? "" : ended || now > c.ends_at ? "Ran " + span + " days" : now < c.starts_at ? "Starts " + day(c.starts_at) : "Day " + dn + " of " + span;
    var left = span && !ended && now >= c.starts_at && now <= c.ends_at ? Math.max(0, span - dn) : null;
    var ST = { done: "Done", active: "In progress", pending: "To come" };
    var seg = steps.length ? steps.map(function (x) {
      var st = ended ? "done" : x.state;
      return '<span class="mx-tl__seg mx-tl__seg--' + st + '" title="' + esc(x.label + " · " + ST[st] + (x.start ? " · " + day(x.start, false) + " – " + day(x.end, false) : "")) + '"></span>';
    }).join("") : '<span class="mx-tl__seg mx-tl__seg--' + (ended ? "done" : "active") + '" style="flex:' + (span ? Math.max(1, dn) : 1) + '"></span>' + (span && !ended ? '<span class="mx-tl__seg mx-tl__seg--pending" style="flex:' + Math.max(0, span - dn) + '"></span>' : "");
    return '<div class="mx-tl__head"><div><span class="mx-tl__label">Campaign timeline</span><b class="mx-tl__stage' + (stage === "Completed" ? " is-done" : "") + '">' + esc(stage) + "</b></div>"
      + '<div class="mx-tl__count">' + (count ? "<b>" + esc(count) + "</b>" : "") + (left != null ? "<em>" + left + (left === 1 ? " day left" : " days left") + "</em>" : "") + "</div></div>"
      + '<div class="mx-tl__track" role="img" aria-label="' + esc((steps.length ? done + " of " + steps.length + " steps done. " : "") + "Now: " + stage) + '">' + seg + "</div>"
      + '<div class="mx-tl__foot"><span>' + (c.starts_at ? day(c.starts_at, false) : "") + "</span><span>" + (steps.length ? done + " of " + steps.length + " steps done" : "") + "</span><span>" + (c.ends_at ? day(c.ends_at, false) : "") + "</span></div>";
  }



  function openReport(t) {
    get("/api/campaign?t=" + encodeURIComponent(t)).then(function (b) {
      unlocked();
      var same = R && R.campaign && R._t === t;
      R = b.report; R._t = t;
      // No tracking links = no clicks anywhere on the report: no tab, no
      // column, no share of the score (the server already scored without it).
      if (R.objective && R.objective.links === false) R.visibility.clicks = false;
      if (!same || !FILTER) FILTER = { platform: "", kind: "", section: "campaign" };      // a refresh keeps the reader's filters
      render(t);
      show("report");
      pollReport();
      if (!same) window.scrollTo(0, 0);
      get("/api/board").then(function (x) {
        BOARD = x;
        $("mx-all").hidden = !(x.campaigns || []).length;
        mountSwitcher(x.campaigns || [], t);
      }).catch(function () {});
    }).catch(function (err) {
      if (err && err.locked) return lock();
      unlocked(); empty("This report is not available with your access code.");
    });
  }
  window.addEventListener("hashchange", route);
  // New numbers appear without a reload (owner, 2026-10-18): while the report is open and visible it asks for the
  // report every five minutes, and redraws it only when something changed (the reader's filters and place are kept).
  var POLL_ID = null;
  function pollReport() {
    if (POLL_ID) return;
    POLL_ID = setInterval(function () {
      if (document.hidden || !R || !R._t) return;
      get("/api/campaign?t=" + encodeURIComponent(R._t)).then(function (b) {
        var n = b && b.report; if (!n) return;
        var sig = function (r) { return [r.updated_at, r.total && r.total.views, r.total && r.total.likes, r.total && r.total.comments, (r.posts || []).length].join("|"); };
        if (sig(n) !== sig(R)) openReport(R._t);
      }).catch(function () {});
    }, window.__pollMs || 300000);
  }

  /* ---------------------------------------------------------------- render */

  /* ------------------------------------------------------------- icons */

  // One line-icon set for the report chrome, same stroke as the platform marks.
  function ico(d) { return '<svg class="mx-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + d + "</svg>"; }
  var IC = {
    overview: ico('<rect x="3" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5"/>'),
    leaderboard: ico('<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M7 6H4a3 3 0 0 0 3 4M17 6h3a3 3 0 0 1-3 4"/>'),
    content: ico('<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><circle cx="9" cy="9" r="1.8"/><path d="M20.5 15l-5-5-11 10.5"/>'),
    performance: ico('<path d="M3 20h18"/><path d="M5 16l5-5 4 3 6-7"/><path d="M16 7h4v4"/>'),
    clicks: ico('<path d="M9 3.5v4M3.5 9h4M5 5l2.5 2.5"/><path d="M12 12l8 3-3.5 1.5L15 20z"/>'),
    timeline: ico('<rect x="3.5" y="4.5" width="17" height="16" rx="2.5"/><path d="M8 2.5v4M16 2.5v4M3.5 10h17M8 14h3M13 17h3"/>'),
    posts: ico('<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><path d="M8 12.5l3 3 5-6"/>'),
    views: ico('<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>'),
    reach: ico('<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4.5-6.2"/>'),
    engagement: ico('<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>'),
    er: ico('<path d="M19 5L5 19"/><circle cx="7" cy="7" r="2.5"/><circle cx="17" cy="17" r="2.5"/>'),
    platform: ico('<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/>'),
    mix: ico('<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>'),
    did: ico('<path d="M7 11V5.5a1.5 1.5 0 0 1 3 0V11M10 10V4a1.5 1.5 0 0 1 3 0v6M13 10V5.5a1.5 1.5 0 0 1 3 0V13a7 7 0 0 1-7 7h-.5A5.5 5.5 0 0 1 4 16l-1-3.5a1.5 1.5 0 0 1 2.7-1.2L7 13"/>'),
    country: ico('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>'),
    creator: ico('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>'),
    device: ico('<rect x="2.5" y="4" width="13" height="10" rx="1.5"/><rect x="17" y="8" width="4.5" height="12" rx="1.2"/><path d="M6 18h6"/>'),
    app: ico('<rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2"/>'),
    unique: ico('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/><path d="M17 3.5l1.5 1.5 3-3"/>'),
    ctr: ico('<path d="M4 20L20 4M8 4h12v12"/>'),
    chart: ico('<path d="M3 20h18"/><path d="M4 16l5-6 4 3 7-8"/>')
  };
  // Panel and bench titles get the matching mark.
  var H3IC = { "Reached by platform": "platform", "Content mix": "mix", "What people did": "did", "Who was reached": "country",
    "By creator": "creator", "By app": "app", "By country": "country", "By device": "device",
    "Engagement rate": "er", "Video engagement": "views", "Click-through": "ctr" };
  function h3ic(title) { return IC[H3IC[title]] ? IC[H3IC[title]] : ""; }

  /* ------------------------------------------------------ section jump bar */

  // Every section is on the page; the bar only scrolls to one. It must not
  // touch the URL hash, which carries the report token.
  var SECS = ["overview", "leaderboard", "content", "performance", "clicks", "timeline"];
  var LOCK = 0;
  SECS.forEach(function (k) {
    var a = $("tab-" + k); if (a && !a.querySelector(".mx-ico")) a.insertAdjacentHTML("afterbegin", IC[k]);
    var h = document.querySelector("#sec-" + k + " .mx-h2");
    if (h && !h.querySelector(".mx-h2__ic")) h.insertAdjacentHTML("afterbegin", '<span class="mx-h2__ic">' + IC[k] + "</span>");
  });
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

  // One row per video the creator published, a chip for each platform it went out on, nothing counted twice.
  function creatorVideos(c) {
    var mine = mergePieces((R.posts || []).filter(function (p) { return p.code === c.code && p.section === "campaign"; }))
      .sort(function (a, b) { return (a.posted_at || 0) - (b.posted_at || 0); });
    function v(p) { return p.exposure != null ? p.exposure : (p.video ? (p.views || 0) : (p.reach || 0)); }
    var rows = mine.map(function (p, i) {
      return '<div class="mx-cc__vid"><b>Video ' + (i + 1) + (c.planned ? " of " + c.planned : "") + "</b><span>" + num(v(p)) + ' views</span><div class="mx-cc__chips">'
        + (p.parts || [p]).map(function (x) {
          return '<a href="' + esc(x.url) + '" target="_blank" rel="noopener" aria-label="' + esc(x.platform) + '">' + icon(x.platform) + num(v(x)) + "</a>";
        }).join("") + "</div></div>";
    });
    for (var i = mine.length; i < (c.planned || 0); i++) rows.push('<div class="mx-cc__vid is-owed"><b>Video ' + (i + 1) + " of " + c.planned + "</b><span>Not published yet</span></div>");
    return rows.length ? '<div class="mx-cc__vids">' + rows.join("") + "</div>" : "";
  }
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
        + '</span><span class="mx-cc__meta">' + c.delivered + (c.planned ? " of " + c.planned : "") + " videos live</span>"
        + creatorVideos(c)
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
    document.title = c.name + " — Campaign report — HELVi Connect";
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
    $("mx-dash").href = $("mx-dash-end").href = "dashboard/#t=" + encodeURIComponent(t); $("mx-dash").hidden = false;
    // Arriving from the dashboard's "Download PDF": open the print dialog.
    try { if (sessionStorage.getItem("hv_print")) { sessionStorage.removeItem("hv_print"); setTimeout(function () { window.print(); }, 900); } } catch (e) {}
  }

  function renderBug(c) {
    var logos = (c.logos || []).map(function (u) { return '<img src="' + esc(u) + '" alt="Brand logo">'; }).join("");
    $("mx-brands").innerHTML = logos ? logos + '<span class="mx-bug__x" aria-hidden="true">×</span><img class="mx-bug__hv" src="../assets/brand/logo.png" alt="HelloVoice">' : "";
    $("mx-title").textContent = c.name;
    $("mx-sub").textContent = [c.client, c.platform ? c.platform + " campaign" : ""].filter(Boolean).join(" · ");
    // Every selection the campaign holds (item 174), one tap away.
    var sl = $("mx-sels") || (function () { var p = document.createElement("p"); p.id = "mx-sels"; p.className = "mx-bug__sels"; $("mx-sub").insertAdjacentElement("afterend", p); return p; })();
    sl.innerHTML = (c.selections || []).length ? '<span>' + ((c.selections.length === 1) ? "Selection" : "Selections") + "</span>" + c.selections.map(function (x) {
      return '<a href="../selection/#s=' + encodeURIComponent(x.token) + '">' + esc(x.name) + "</a>";
    }).join("") : "";
    sl.hidden = !(c.selections || []).length;
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
    // Every target counts: 100% only when all of them are met.
    var mine = items, P = R.progress || {};
    var box = $("mx-delivery");
    if (!mine.length) {
      box.innerHTML = '<div class="mx-obj"><div class="mx-obj__label"><span>Campaign objective · <b>' + esc(o.label)
        + '</b></span><span class="mx-obj__pct">No targets set yet</span></div></div>';
      return;
    }
    var done = P.overall != null ? P.overall : mine.reduce(function (s, i) { return s + Math.min(100, i.pct); }, 0) / mine.length;
    var due = P.due != null ? P.due : mine.reduce(function (s, i) { return s + Math.min(100, i.expected / i.goal * 100); }, 0) / mine.length;
    if (!P.all_met) done = Math.min(done, 99);
    var ratio = due ? done / due : 1, g = P.all_met || ratio >= 1 ? "good" : (ratio >= 0.7 ? "moderate" : "low");
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
    var adj = t.adjusted || [];
    function est(k) { return adj.indexOf(k) >= 0 ? ' <small class="mx-est" title="Estimated by HelloVoice: the platform has not shown the exact number yet.">est.</small>' : ""; }
    function goal(key, val) { var i = g[key]; return i ? sig(i.grade, "Goal " + (key === "er" ? pct(i.goal, 1) : num(i.goal))) : ""; }
    cells.push(["Posts live", full(t.delivered) + (t.planned ? "<small>/" + t.planned + "</small>" : ""), goal("posts"), "posts"]);
    cells.push(["Views", num(t.views) + est("views"), goal("views"), "views"]);
    if (vis.reach && t.reach != null) cells.push(["Reach" + (t.real_share >= 0.999 || adj.indexOf("reach") >= 0 ? "" : " (est.)"), num(t.reach) + est("reach"), goal("reach"), "reach"]);
    cells.push(["Engagement", num(t.engagement) + est("engagement"), goal("engagement"), "engagement"]);
    cells.push(["Avg eng. rate", pct(t.er) + est("er"), g.er ? goal("er") : sig(t.er_grade, "Against each creator's tier benchmark"), "er"]);
    if (vis.clicks && R.clicks && R.clicks.links && R.clicks.has_destination)
      cells.push(["Link clicks", num(t.clicks) + est("clicks"), g.clicks ? goal("clicks") : sig(t.ctr_grade, "Strong from " + bm.ctr[0] + "% click-through"), "clicks"]);
    $("mx-scoreline").innerHTML = cells.map(function (c) {
      return "<div><dt>" + (c[3] ? IC[c[3]] : "") + esc(c[0]) + "</dt><dd>" + c[1] + "</dd>" + (c[2] ? "<div class=\"mx-score-line__sig\">" + c[2] + "</div>" : "") + "</div>";
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

  // One video the creator pushed to several platforms is one card: the numbers of every platform
  // added together, a mark for each platform, and a link to each.
  function mergePieces(list) {
    var by = {}, order = [];
    list.forEach(function (p) {
      var k = p.piece_size > 1 ? "g" + p.pk : "s" + p.id;
      if (!by[k]) { by[k] = []; order.push(k); }
      by[k].push(p);
    });
    return order.map(function (k) {
      var g = by[k];
      if (g.length === 1) return g[0];
      var m = {}, lead = g[0];
      Object.keys(lead).forEach(function (f) { m[f] = lead[f]; });
      ["likes", "comments", "views", "reach", "impressions", "saves", "shares", "engagement", "exposure"].forEach(function (f) {
        var vals = g.map(function (x) { return x[f]; }).filter(function (v) { return v != null; });
        m[f] = vals.length ? vals.reduce(function (a, b) { return a + b; }, 0) : null;
      });
      m.video = g.some(function (x) { return x.video; });
      m.parts = g;
      m.reach_real = g.every(function (x) { return x.reach_real; });
      var ers = g.map(function (x) { return m.video ? x.video_er : x.er; }).filter(function (v) { return v != null; });
      m.er = m.video_er = ers.length ? ers.reduce(function (a, b) { return a + b; }, 0) / ers.length : null;
      return m;
    });
  }

  function renderWall() {
    var vis = R.visibility;
    var list = mergePieces(R.posts.filter(function (p) {
      return (!FILTER.section || p.section === FILTER.section) && (!FILTER.platform || p.platform === FILTER.platform)
        && (!FILTER.kind || p.kind === FILTER.kind);
    }));
    var owed = pendingCards();
    if (!list.length && !owed.length) { $("mx-wall").innerHTML = '<p class="mx-empty-note">No posts yet. They appear here within 24 hours of going live.</p>'; return; }
    $("mx-wall").innerHTML = owed.length && !list.length ? owed.map(pendingCard).join("") : list.map(function (p) {
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
      // Never cropped: the whole frame fitted over a blurred copy of itself.
      var img = p.thumb ? '<img class="hv-fill" src="' + esc(p.thumb) + '" alt="" aria-hidden="true" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">'
        + '<img class="hv-fit" src="' + esc(p.thumb) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">' : "";
      return '<article class="mx-post"><div class="mx-post__media"><div class="mx-post__plate">' + icon(p.platform) + "</div>" + img
        + '<span class="mx-post__tag">' + (p.parts ? p.parts.map(function (x) { return icon(x.platform); }).join("") + "<span class=\"mx-post__one\">One video · </span>" + p.parts.length + " platforms"
          : icon(p.platform) + esc(KIND[p.kind] || p.kind)) + '</span><span class="mx-post__sig">'
        + sig(h.grade, healthTitle(h)) + '</span></div><div class="mx-post__body"><div class="mx-who">' + ava(p.photo)
        + "<div><b>" + esc(p.creator) + "</b><span>" + esc(day(p.posted_at)) + '</span></div></div><dl class="mx-nums">'
        + n.slice(0, 6).map(function (x) { return "<div><dt>" + x[0] + "</dt><dd>" + x[1] + "</dd></div>"; }).join("")
        + '</dl>' + (p.parts ? '<p class="mx-post__plats">Combined across ' + p.parts.map(function (x) { return esc(x.platform); }).join(", ") + "</p>" : "")
        + (p.parts || [p]).map(function (x) {
          return '<a class="mx-post__go" href="' + esc(x.url) + '" target="_blank" rel="noopener">View on ' + esc(x.platform)
            + (p.parts && x.video && x.views != null ? " · " + num(x.views) + " views" : "")
            + ' <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17L17 7M9 7h8v8"/></svg></a>';
        }).join("") + '</div></article>';
    }).join("") + (list.length && owed.length ? pendingStrip(owed) : "");
  }

  // A card for every booked post that is not live yet: the creator, where
  // the post stands and when it is expected, so the client sees the whole
  // plan and not only what has gone out.
  function pendingCards() {
    if (FILTER.section === "other" || FILTER.kind) return [];
    var out = [];
    (R.creators || []).forEach(function (c) {
      if (FILTER.platform && !(c.profiles || []).some(function (p) { return p.platform === FILTER.platform; })) return;
      var owed = (c.planned || 0) - (c.delivered || 0);
      for (var i = 0; i < owed; i++) out.push({ c: c, n: (c.delivered || 0) + i + 1 });
    });
    return out;
  }
  // With posts already live, the ones still to come fold into one short
  // "Coming next" list instead of a full card each (mobile audit 2026-10-19).
  function pendingStrip(owed) {
    return '<section class="mx-next" aria-label="Coming next"><h3 class="mx-next__h">Coming next · ' + owed.length + (owed.length === 1 ? " video" : " videos") + "</h3><ul>"
      + owed.map(function (x) {
        var c = x.c, when = c.pending_date ? "Expected " + day(c.pending_date) : "Date to be confirmed";
        return "<li>" + ava(c.photo) + "<span><b>" + esc(c.name) + "</b><small>Post " + x.n + " of " + c.planned + "</small></span><em>" + esc(when) + "</em></li>";
      }).join("") + "</ul></section>";
  }
  function pendingCard(x) {
    var c = x.c, when = c.pending_date ? "Expected " + day(c.pending_date) : "Date to be confirmed";
    var pic = c.photo_large || c.photo;
    return '<article class="mx-post mx-post--pending"><div class="mx-post__media"><div class="mx-post__plate"></div>'
      + (pic ? '<img src="' + esc(pic) + '" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">' : "")
      + '<span class="mx-post__pending">Pending</span></div><div class="mx-post__body"><div class="mx-who">' + ava(c.photo)
      + "<div><b>" + esc(c.name) + "</b><span>Post " + x.n + " of " + c.planned + '</span></div></div><dl class="mx-nums">'
      + "<div><dt>Status</dt><dd>" + esc(c.pending_status || "Coming soon") + "</dd></div>"
      + "<div><dt>When</dt><dd>" + esc(when) + "</dd></div></dl>"
      + '<p class="mx-post__soon">Not live yet — its numbers appear here once it is posted.</p></div></article>';
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
      + (w.er > 0 ? Math.round(w.er * 100) + "% engagement rate, " : "")
      + (w.clicks > 0 ? "and " + Math.round(w.clicks * 100) + "% affiliate clicks (compared with the best)" : "and no clicks — this campaign has no tracking links") + ". It rewards the results each creator delivered for the campaign, not their follower count. The top three get gold, silver and bronze; creators who have not posted yet are listed last.");
    var tag = $("mx-objective");
    if (tag) tag.textContent = "Scored for " + o.label;
    var ranked = cs.filter(function (c) { return c.rank; });
    $("mx-podium").innerHTML = ranked.slice(0, 3).map(function (c) {
      return '<div class="mx-pod mx-pod--' + c.rank + '" style="--medal:' + MEDAL[c.badge] + '"><svg class="mx-medal" viewBox="0 0 40 50" aria-hidden="true">'
        + medalBody(c.badge, c.rank) + "</svg>"
        + (c.photo ? '<img class="mx-pod__photo" src="' + esc(c.photo) + '" alt="">' : '<span class="mx-pod__photo"></span>')
        + '<div class="mx-pod__name">' + creatorLink(c, "") + '</div><div class="mx-pod__score">' + c.score.toFixed(0)
        + "<small>score out of 100</small></div><div class=\"mx-pod__line\">" + num(c.seen != null ? c.seen : (c.views || 0)) + " views · "
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
        "<td>" + pct(rate) + "</td>");
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
      ? ""
      : "";
    $("mx-bullets").innerHTML = p.items.length ? p.items.map(function (i) {
      var isRate = i.key === "er", fill = Math.min(100, i.pct), mark = Math.min(100, i.expected / i.goal * 100);
      return '<div class="mx-bullet"><div class="mx-bullet__name">' + (IC[i.key] || "") + TLABEL[i.key] + " " + sig(i.grade) + "</div>"
        + '<div class="mx-bullet__track" role="img" aria-label="' + TLABEL[i.key] + " " + Math.round(i.pct) + '% of goal">'
        + '<div class="mx-bullet__fill ' + i.grade + '" style="width:' + fill + '%"></div>'
        + (isRate ? "" : '<div class="mx-bullet__mark" style="left:' + mark + '%"><span>by today</span></div>') + "</div>"
        + '<div class="mx-bullet__num"><b>' + (isRate ? pct(i.actual) : num(i.actual)) + "</b>of " + (isRate ? pct(i.goal, 1) : num(i.goal)) + " goal</div></div>";
    }).join("") : "";
    var ex = [];
    // One rule: with a campaign ER goal, the card grades against it, like the score line (owner, 2026-10-19).
    var erT = (p.items || []).filter(function (i) { return i.key === "er"; })[0];
    ex.push(["Engagement rate", t.er, erT ? erT.grade : t.er_grade, erT ? "Against the campaign goal of " + pct(erT.goal, 1) + " · industry guide " + bm.er.micro[0] + "% (micro creators)" : "Strong from " + bm.er.micro[0] + "% (micro creators)"]);
    if (t.video_er != null) ex.push(["Video engagement", t.video_er, t.video_er_grade, "Strong from " + bm.video_er[0] + "%"]);
    if (R.visibility.clicks && t.ctr != null && R.clicks && R.clicks.links) ex.push(["Click-through", t.ctr, t.ctr_grade, "Strong from " + bm.ctr[0] + "%"]);
    $("mx-bench").innerHTML = ex.map(function (x) {
      return '<div class="mx-bench__item"><h3>' + h3ic(x[0]) + x[0] + '</h3><div class="mx-bench__val">' + pct(x[1]) + " " + sig(x[2]) + "</div><p>" + x[3] + "</p></div>";
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

  // Bars take turns through the brand's colours rather than all ink:
  // green, orange, lime, then a warm grey — the order repeats.
  var PALETTE = ["#14884a", "#ff691e", "#b9d400", "#8a7a68"];
  function bars(rows, keyHtml) {
    if (!rows || !rows.length) return '<p class="mx-panel__note">Nothing yet.</p>';
    var peak = Math.max.apply(null, rows.map(function (r) { return r.n; })) || 1;
    return rows.slice(0, 8).map(function (r, i) {
      return '<div class="mx-bar"><span class="mx-bar__k">' + keyHtml(r) + '</span><i style="--w:' + (r.n / peak * 100).toFixed(1)
        + "%;--c:" + PALETTE[i % PALETTE.length] + '"></i><b>' + r.label + "</b></div>";
    }).join("");
  }

  function renderCharts() {
    var h = (R.history || []).map(function (d) { return { d: d.d, views: d.views, eng: d.likes + d.comments }; });
    $("mx-charts").innerHTML = h.length
      ? '<div class="mx-chart"><h3>' + IC.views + 'Views so far</h3>' + area(h, "views", "#14884a", "Views so far") + "</div>"
        + '<div class="mx-chart"><h3>' + IC.engagement + 'Engagement so far</h3>' + area(h, "eng", "#ff691e", "Engagement so far") + "</div>"
      : '<p class="mx-empty-note">The charts fill in as posts are captured, once every 24 hours.</p>';

    var posts = R.posts.filter(function (p) { return p.section === "campaign"; }), mix = [];
    var byPlat = {}, byKind = {};
    var seenPiece = {};
    posts.forEach(function (p) {
      var a = byPlat[p.platform] = byPlat[p.platform] || { n: 0, x: 0 }; a.n++; a.x += p.exposure != null ? p.exposure : (p.video ? (p.views || 0) : (p.reach || 0));
      byKind[p.kind] = (byKind[p.kind] || 0) + 1;
    });
    var plats = Object.keys(byPlat).map(function (k) { return { k: k, n: byPlat[k].x || byPlat[k].n, label: num(byPlat[k].x) }; })
      .sort(function (a, b) { return b.n - a.n; });
    if (plats.length) mix.push('<div class="mx-panel"><h3>Reached by platform</h3>' + bars(plats, function (r) { return icon(r.k) + esc(r.k); }) + "</div>");
    var kinds = Object.keys(byKind).map(function (k) { return { k: k, n: byKind[k], label: byKind[k] + (byKind[k] === 1 ? " post" : " posts") }; })
      .sort(function (a, b) { return b.n - a.n; });
    if (kinds.length) mix.push('<div class="mx-panel"><h3>Content mix</h3>' + bars(kinds, function (r) { return esc(KIND[r.k] || r.k); }) + "</div>");
    var t = R.total, parts = [["Likes", t.likes, "#14884a"], ["Comments", t.comments, "#ff691e"], ["Saves", t.saves, "#b9d400"], ["Shares", t.shares, "#8a7a68"]]
      .filter(function (p) { return p[1]; });
    var sum = parts.reduce(function (s, p) { return s + p[1]; }, 0);
    if (sum) mix.push('<div class="mx-panel"><h3>What people did</h3><div class="mx-stack" role="img" aria-label="Interactions breakdown">'
      + parts.map(function (p) { return '<i style="width:' + (p[1] / sum * 100) + "%;background:" + p[2] + '"></i>'; }).join("")
      + '</div><div class="mx-key">' + parts.map(function (p) {
        return '<div><span class="mx-cs" style="background:' + p[2] + '"></span>' + p[0] + "<b>" + full(p[1]) + "</b></div>";
      }).join("") + "</div></div>");
    if (R.audience && R.audience.countries.length) {
      mix.push('<div class="mx-panel"><h3>Creators\' audience</h3>' + (R.audience ? '<p class="aud-target">' + (R.audience.target ? flag(R.audience.target.code) + '<span>Target market <b>' + esc(countryName(R.audience.target.code)) + '</b></span>' : '<span>Target market</span>') + '</p>' + '<div class="aud-stamp" role="img" aria-label="Audience not analysed yet"><span>Not analysed</span><span>yet</span></div>' : '') + '</div>');
    }
    $("mx-mix").innerHTML = mix.join("");
    decorateH3("mx-mix");
  }

  /* ----------------------------------------------------------- clicks */

  function renderClicks() {
    var vis = R.visibility, cl = R.clicks;
    $("sec-clicks").hidden = !vis.clicks;
    if (!vis.clicks) return;
    if (!cl || !cl.links || !cl.has_destination) {
      $("mx-clicks").innerHTML = '<p class="mx-empty-note"><span class="mx-na">Not part of this campaign</span> No tracking links were set up, so there are no clicks to count.</p>';
      return;
    }
    var t = R.total;
    var heads = '<dl class="mx-clickheads"><div><dt>' + IC.clicks + 'Clicks</dt><dd>' + full(cl.clicks) + '</dd></div><div><dt>' + IC.unique + 'Unique people</dt><dd>'
      + full(cl.uniques) + '</dd></div><div><dt>' + IC.ctr + 'Click-through</dt><dd>' + pct(t.ctr) + "</dd></div></dl>";
    if (!cl.clicks) { $("mx-clicks").innerHTML = heads + '<p class="mx-empty-note" style="margin-top:18px">No clicks yet.</p>'; return; }
    var lab = function (rows) { return (rows || []).map(function (r) { return { k: r.k, n: r.n, label: full(r.n) }; }); };
    $("mx-clicks").innerHTML = heads + '<div class="mx-clickgrid">'
      + '<div class="mx-panel"><h3>By creator</h3>' + bars(lab(cl.by_creator), function (r) { return esc(r.k); }) + "</div>"
      + '<div class="mx-panel"><h3>By app</h3>' + bars(lab(cl.by_app), function (r) { return (ICONS[r.k] || "") + esc(r.k); }) + "</div>"
      + '<div class="mx-panel"><h3>By country</h3>' + bars(lab(cl.by_country), function (r) {
        return r.k && r.k.length === 2 ? flag(r.k) + esc(countryName(r.k)) : esc(r.k || "Unknown");
      }) + "</div>"
      + '<div class="mx-panel"><h3>By device</h3>' + bars(lab(cl.by_device), function (r) { return esc(r.k); }) + "</div></div>";
    decorateH3("mx-clicks");
  }

  function decorateH3(id) {
    var box = $(id); if (!box) return;
    box.querySelectorAll(".mx-panel > h3").forEach(function (h) {
      if (!h.querySelector(".mx-ico")) h.insertAdjacentHTML("afterbegin", h3ic(h.textContent.trim()));
    });
  }

  $("mx-print").addEventListener("click", function () { window.print(); });
  route();
})();
