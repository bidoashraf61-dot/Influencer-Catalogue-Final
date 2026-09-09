/* Influencer proposal catalogue — gate, filters, selection, request.
 *
 * On the security model, so nobody is misled later: the page now carries
 * names and exact follower counts, so the only withheld field is the @handle
 * — which a name plus a follower count makes easy to find anyway. Everything
 * below is deterrence against casual copying. It does not defeat a determined
 * technical user and is not meant to. Rebuild with CATALOGUE_ANON=1 to return
 * to codes and follower bands.
 */
(function () {
  "use strict";

  var CFG = window.CATALOGUE_CONFIG || {};
  var PAGE = document.body.getAttribute("data-page") || "catalogue";
  var selected = [];
  var selectionName = "";
  var ROSTER = null;

  // A selection travels entirely in the URL fragment — #n=<name>&c=<codes>.
  // The fragment never reaches the server, so this works on any static host
  // with no backend, and the link IS the selection: nothing is stored.
  function readFragment() {
    var raw = (location.hash || "").replace(/^#/, "");
    var out = { name: "", codes: [] };
    raw.split("&").forEach(function (pair) {
      var i = pair.indexOf("=");
      if (i === -1) return;
      var k = pair.slice(0, i), v = pair.slice(i + 1);
      try { v = decodeURIComponent(v); } catch (e) { /* leave raw */ }
      if (k === "n") out.name = v;
      if (k === "c") out.codes = v.split(",").map(function (x) { return x.trim(); }).filter(Boolean);
    });
    return out;
  }

  function buildFragment(name, codes) {
    return "#n=" + encodeURIComponent(name) + "&c=" + codes.join(",");
  }

  /* ------------------------------------------------------------- helpers */

  function $(id) { return document.getElementById(id); }
  function all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  // Mirrors simple_hash() in the Python builder (djb2-xor, 32-bit).
  function hash(s) {
    var h = 5381;
    for (var i = 0; i < s.length; i++) h = (Math.imul(h, 33) ^ s.charCodeAt(i)) >>> 0;
    return ("0000000" + h.toString(16)).slice(-8);
  }

  /* ------------------------------------------------- remembering a unlock */

  // A session cookie, not sessionStorage. sessionStorage is scoped to ONE tab,
  // and the selection page opens in a new one — so the client unlocked the
  // catalogue and was then asked for the very same code again on the page they
  // had just been sent to. A cookie with no Max-Age is shared by every tab on
  // this origin and still disappears when the browser closes, which is the
  // behaviour that was wanted all along.
  //
  // sessionStorage stays as the fallback for when cookies are refused, where
  // one prompt per tab beats no memory at all.
  var OK = "cat-ok";

  function remember() {
    try { document.cookie = OK + "=1; Path=/; SameSite=Lax"; } catch (e) { /* blocked */ }
    try { sessionStorage.setItem(OK, "1"); } catch (e) { /* private mode */ }
  }

  function forget() {
    try {
      document.cookie = OK + "=; Path=/; SameSite=Lax; Max-Age=0";
    } catch (e) { /* blocked */ }
    try { sessionStorage.removeItem(OK); } catch (e) { /* private mode */ }
  }

  function remembered() {
    try {
      if (("; " + document.cookie).indexOf("; " + OK + "=1") !== -1) return true;
    } catch (e) { /* blocked */ }
    try { return sessionStorage.getItem(OK) === "1"; } catch (e) { return false; }
  }

  /* ---------------------------------------------------------------- gate */

  function unlock() {
    document.body.classList.remove("cat-locked");
    $("cat-gate").remove();
    var app = $("cat-app");
    app.hidden = false;
    if (CFG.api && ROSTER) renderRoster(ROSTER);
    initApp();
  }

  function gateFail(message) {
    var err = $("cat-gate-error");
    err.textContent = message || "That code is not right.";
    err.hidden = false;
    $("cat-code").value = "";
    $("cat-code").focus();
  }

  // What the server says when it refuses. "expired" is worth telling an honest
  // client plainly — they can ask for a new code instead of retyping.
  var REFUSALS = {
    expired: "That code has expired. Ask us for a new one.",
    revoked: "That code is no longer active. Ask us for a new one.",
    exhausted: "That code has already been used its maximum number of times.",
    unknown: "That code is not right."
  };

  var gateForm = $("cat-gate-form");
  gateForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var val = $("cat-code").value.trim();
    var btn = gateForm.querySelector("button");

    if (!CFG.api) {
      if (hash(val) === CFG.passHash) {
        remember();
        unlock();
      } else {
        gateFail();
      }
      return;
    }

    btn.disabled = true;
    fetch(CFG.api + "/api/unlock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ code: val })
    })
      .then(function (r) { return r.json().then(function (b) { return { r: r, b: b }; }); })
      .then(function (res) {
        if (!res.b || !res.b.ok) {
          gateFail(REFUSALS[res.b && res.b.reason] || "That code is not right.");
          return;
        }
        ROSTER = res.b.roster || [];
        adoptTiers(res.b.tiers);
        remember();
        unlock();
      })
      .catch(function () {
        gateFail("Could not reach the server. Please try again.");
      })
      .then(function () { btn.disabled = false; });
  });

  // Survive a refresh and a hop to the selection page, not a browser restart.
  // The actual unlock happens at the very bottom of this file: everything it
  // reaches for must already be assigned, and `var` hoists the declaration but
  // not the value. Unlocking here silently broke the selection page on any
  // revisit.
  var wasUnlocked = remembered();


  /* ------------------------------------------------------- roster from API */

  // In API mode the page ships no roster: it arrives as JSON once the server
  // has accepted the code. These build the markup the static build would have
  // emitted, so everything downstream — filters, tray, selection — is unchanged.

  // Only the short label the chip shows; the money comes from TIER_PRICE so
  // there is one table to keep right rather than two.
  var TIER_LABEL = { "Mid-Tier": "Mid" };
  function tierLabel(name) { return TIER_LABEL[name] || name; }

  // Mirrors PLATFORM_ICONS in the Python builder: the brand colour is the pill
  // behind the glyph (CSS, off the --ig/--tt modifier) because Instagram's is a
  // gradient and an in-SVG gradient needs an id repeated on every card.
  var TT = '<path d="M14.2 3v11.6a3.6 3.6 0 1 1-3.6-3.6"/><path d="M14.2 3.2c.45 2.7 2.05 4.3 4.75 4.6"/>';
  var ICONS = {
    Instagram: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4.1"/><circle cx="17.3" cy="6.7" r="1.15" fill="currentColor" stroke="none"/></svg>',
    TikTok: '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<g stroke="#25f4ee" transform="translate(-1,-.85)">' + TT + '</g>' +
      '<g stroke="#fe2c55" transform="translate(1,.85)">' + TT + '</g>' +
      '<g stroke="currentColor">' + TT + '</g></svg>'
  };
  ICONS.Snapchat = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3.2c2.4 0 4 1.7 4 4.1 0 1 .1 1.7.3 2.1.3.4.9.4 1.4.3.4-.1.8.2.8.6 0 .5-.6.8-1.2 1-.3.1-.4.3-.3.6.4 1.2 1.6 2.4 3 2.7.3.1.4.4.2.6-.5.6-1.6.9-2.5 1-.2.5-.3 1-.9 1-.5 0-1-.3-1.8-.3-1.1 0-1.6 1.1-3 1.1s-1.9-1.1-3-1.1c-.8 0-1.3.3-1.8.3-.6 0-.7-.5-.9-1-.9-.1-2-.4-2.5-1-.2-.2-.1-.5.2-.6 1.4-.3 2.6-1.5 3-2.7.1-.3 0-.5-.3-.6-.6-.2-1.2-.5-1.2-1 0-.4.4-.7.8-.6.5.1 1.1.1 1.4-.3.2-.4.3-1.1.3-2.1 0-2.4 1.6-4.1 4-4.1z"/></svg>';
  ICONS.YouTube = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><rect x="2.5" y="5.5" width="19" height="13" rx="4"/><path d="M10.2 9.3l5 2.7-5 2.7z" fill="currentColor" stroke="none"/></svg>';
  ICONS.X = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M4.5 4.5l15 15M19.5 4.5l-15 15"/></svg>';
  ICONS.Facebook = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15.2 4.2h-2.1a3.4 3.4 0 0 0-3.4 3.4V10H7.9v3h1.8v7"/><path d="M9.7 13h4.1"/></svg>';
  var ICON_LINK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13.5a3.5 3.5 0 0 0 5 0l2.5-2.5a3.5 3.5 0 0 0-5-5L11 7.5"/><path d="M14 10.5a3.5 3.5 0 0 0-5 0L6.5 13a3.5 3.5 0 0 0 5 5l1.5-1.5"/></svg>';

  var BRAND = {
    Instagram: "cat-card__platform--ig",
    TikTok: "cat-card__platform--tt",
    Snapchat: "cat-card__platform--sc",
    YouTube: "cat-card__platform--yt",
    X: "cat-card__platform--x",
    Facebook: "cat-card__platform--fb"
  };

  function esc(v) {
    return String(v === null || v === undefined ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // Split a possibly multi-valued data attribute. Mirrors split_cities() in
  // the builder and in admin/db.py — one separator set across all three.
  function values(text) {
    if (!text) return [];
    return text.split(/[,;\u060c\u061b/]/)
      .map(function (v) { return v.trim(); })
      .filter(Boolean);
  }

  function commas(n) {
    return (n === null || n === undefined || n === "") ? "—" : Number(n).toLocaleString("en-US");
  }

  function profileUrl(platform, handle) {
    if (!handle) return "";
    return platform === "TikTok"
      ? "https://www.tiktok.com/@" + handle
      : "https://www.instagram.com/" + handle + "/";
  }

  // A creator on three platforms has three audiences. One "Followers" row
  // would have to pick one or invent a total the client cannot check, so each
  // platform gets its own line and a total appears only when there is more
  // than one to add up.
  function handleFromUrl(url) {
    var text = String(url || "").trim().replace(/\/+$/, "").split("?")[0].split("#")[0];
    return text ? text.split("/").pop().replace(/^@/, "") : "";
  }

  function metaRows(c, label) {
    var counted = (c.profiles || []).filter(function (p) { return p.followers; });
    var rows = [];
    // Always name the platform a number belongs to. "Followers 9,575" on a
    // creator who is on Instagram says less than "Instagram 9,575", and the
    // moment a second platform is added the rows read the same way rather than
    // changing shape.
    if (counted.length) {
      // Two accounts on one platform need telling apart, so the handle is
      // added — but only where it is doing that work, or every row grows a
      // tail the reader does not need.
      var repeated = {};
      counted.forEach(function (p) {
        repeated[p.platform] = (repeated[p.platform] || 0) + 1;
      });
      counted.forEach(function (p) {
        var tag = esc(p.platform);
        if (repeated[p.platform] > 1) {
          var who = handleFromUrl(p.url);
          if (who) tag += " @" + esc(who);
        }
        rows.push("<li><span>" + tag + "</span><strong>" +
                  commas(p.followers) + "</strong></li>");
      });
      // The sum of the rows above, not the stored headline. Adding a platform
      // to a creator whose headline was typed for one account left a total
      // smaller than the numbers listed right above it.
      // A total only when there is more than one number to add up; on a
      // single platform it would just repeat the line above it.
      if (counted.length > 1) {
        var sum = counted.reduce(function (t, p) { return t + (Number(p.followers) || 0); }, 0);
        rows.push("<li><span>Total reach</span><strong>" + commas(sum) +
                  "</strong></li>");
      }
    } else {
      rows.push("<li><span>Followers</span><strong>" + commas(c.followers) +
                "</strong></li>");
    }
    if (c.nationality) {
      rows.push("<li><span>Nationality</span><strong>" + esc(c.nationality) +
                "</strong></li>");
    }
    rows.push("<li><span>City</span><strong>" + esc(c.city || "Unspecified") +
              "</strong></li>");
    rows.push("<li><span>Tier</span><strong>" + esc(label) + "</strong></li>");
    return rows.join("");
  }

  function cardMarkup(c) {
    var label = tierLabel(c.tier);
    // The static build marks 100px sources so the card shows a small sharp
    // circle over a blurred backdrop instead of a 3x upscale. API mode drew
    // them raw, so the same roster looked worse served from the service than
    // built into the page.
    var soft = c.lowres ? " cat-card__photo--soft" : "";
    // photo_url is a signed link the service issued for this roster. The
    // photographs used to sit at a guessable address — every code is
    // HV-XX-NNN — so the whole set could be walked without the passcode.
    // photoBase remains the fallback for a page built with the roster inside
    // it, where there is no service to sign anything.
    var src = c.photo_url || (c.photo ? (CFG.photoBase || "assets/catalogue/") + c.photo : "");
    var photo = src
      ? '<div class="cat-card__photo' + soft + '" style="background-image:url(' +
        esc(src) + ')"></div>'
      : '<div class="cat-card__photo cat-card__photo--fallback" data-plate="' +
        esc(String(c.code).split("-").pop()) + '"></div>';

    var url = profileUrl(c.platform, c.handle);
    // One mark per platform the creator is on, each linking to its own
    // profile. Falls back to the single platform+handle guess for a roster
    // served by a service that predates stored profiles.
    var list = (c.profiles && c.profiles.length) ? c.profiles
      : (url ? [{platform: c.platform, url: url}] : []);
    var marks = list.map(function (prof) {
      return '<a class="cat-card__mark ' + (BRAND[prof.platform] || "") + '" href="' +
        esc(prof.url) + '" target="_blank" rel="noopener noreferrer nofollow" ' +
        'data-noselect aria-label="Visit ' + esc(prof.platform) + ' profile" title="' +
        esc(prof.platform) + '">' + (ICONS[prof.platform] || ICON_LINK) + "</a>";
    });
    if (!marks.length) {
      marks = values(c.platform).map(function (name) {
        return '<span class="cat-card__mark ' + (BRAND[name] || "") + '" title="' +
          esc(name) + '">' + (ICONS[name] || ICON_LINK) + "</span>";
      });
    }
    var mark = '<div class="cat-card__platform">' +
      (list.length ? '<span class="cat-card__platform-hint">Visit profile</span>' : "") +
      '<div class="cat-card__marks">' + marks.join("") + "</div></div>";

    return '<article class="cat-card" data-tier="' + esc(c.tier) +
      '" data-platform="' + esc(c.platform) + '" data-city="' + esc(c.city || "Unspecified") +
      '" data-interest="' + esc(c.interest || "") + '" data-code="' + esc(c.code) +
      '" tabindex="0" role="button" aria-pressed="false"' +
      ' aria-label="' + esc(c.name) + ", " + esc(c.code) + ", " + esc(label) +
      " tier, " + esc(c.city || "Unspecified") + ", " + esc(c.platform) + ", " +
      commas(c.followers) + ' followers">' +
      '<div class="cat-card__media">' + photo +
      '<span class="cat-card__shield" aria-hidden="true"></span>' +
      '<span class="cat-card__tier">' + esc(label) + "</span>" + mark +
      '<span class="cat-card__check" aria-hidden="true"></span></div>' +
      '<div class="cat-card__body"><p class="cat-card__code">' + esc(c.code) + "</p>" +
      '<h3 class="cat-card__name">' + esc(c.name) + "</h3>" +
      '<ul class="cat-card__meta">' + metaRows(c, label) + "</ul>" +
      "</div></article>";
  }

  function chipGroup(label, key, counts) {
    var keys = Object.keys(counts);
    if (!keys.length) return "";
    // Tier reads in size order; everything else by how many there are.
    var order = ["Nano", "Micro", "Mid-Tier", "Macro"];
    keys.sort(key === "tier"
      ? function (a, b) { return order.indexOf(a) - order.indexOf(b); }
      : function (a, b) { return counts[b] - counts[a]; });
    var chips = '<button type="button" class="cat-chip is-active" data-filter="' + key +
      '" data-value="" aria-pressed="true">All</button>';
    keys.forEach(function (v) {
      chips += '<button type="button" class="cat-chip" data-filter="' + key +
        '" data-value="' + esc(v) + '" aria-pressed="false">' + esc(v) +
        "</button>";
    });
    return '<div class="cat-filter"><span class="cat-filter__label">' + esc(label) +
      '</span><div class="cat-filter__chips">' + chips + "</div></div>";
  }

  function renderRoster(list) {
    var grid = $("cat-grid");
    if (!grid) return;
    grid.innerHTML = list.map(cardMarkup).join("");

    var controls = document.querySelector(".cat-controls .cat-container");
    if (controls && PAGE !== "selection") {
      var tally = function (field) {
        var out = {};
        list.forEach(function (c) {
          // city, interest and platform all hold several values per creator,
          // so a creator counts under each one — the number on a chip is how
          // many cards it shows. Platform was missing from this list, which
          // turned a creator on three of them into a chip literally labelled
          // "Instagram, Snapchat, TikTok" that matched only her.
          var multi = (field === "city" || field === "interest" ||
                       field === "platform");
          var raw = c[field] || (field === "city" ? "Unspecified" : "");
          var each = multi ? values(raw) : (raw ? [raw] : []);
          if (!each.length && field === "city") each = ["Unspecified"];
          each.forEach(function (v) { out[v] = (out[v] || 0) + 1; });
        });
        return out;
      };
      var interests = tally("interest");
      var html = chipGroup("Tier", "tier", tally("tier")) +
                 chipGroup("Platform", "platform", tally("platform")) +
                 chipGroup("City", "city", tally("city"));
      // Only offer the interest filter when it actually separates anyone —
      // one value across the whole roster is a claim, not a filter.
      if (Object.keys(interests).length > 1) {
        html += chipGroup("Interest", "interest", interests);
      }
      controls.insertAdjacentHTML("afterbegin", html);
    }
  }

  /* ------------------------------------------------------------- the app */

  function initApp() {
    if (PAGE === "selection") { initSelection(); return; }
    var grid = $("cat-grid");
    var cards = all(".cat-card");
    // Derived from whatever chips the builder rendered, so adding a filter
    // dimension is a builder change alone — this stays correct untouched.
    // Each dimension holds a SET of chosen values, not one. "Instagram or
    // Snapchat" is a real question — a client wants both kinds of creator in
    // front of them — and a single-choice filter could only ask it one platform
    // at a time.
    var filters = {};
    all(".cat-chip").forEach(function (c) { filters[c.dataset.filter] = []; });

    /* -- filtering -- */

    function apply() {
      var shown = 0;
      cards.forEach(function (card) {
        var ok = Object.keys(filters).every(function (k) {
          // Nothing chosen in a dimension means that dimension is not asking.
          // Otherwise the card has to carry at least one of the chosen values —
          // OR within a dimension, AND across them, which is how people read a
          // set of filters.
          if (!filters[k].length) return true;
          var mine = values(card.dataset[k]);
          return filters[k].some(function (want) {
            return mine.indexOf(want) !== -1;
          });
        });
        card.hidden = !ok;
        if (ok) shown++;
      });
      // How many creators exist, and how many a filter leaves, is commercial
      // information: it belongs in the dashboard, not on the client page. Only
      // the empty state is still announced, so a filter that matches nobody
      // does not read as a broken page.
      $("cat-empty").hidden = shown !== 0;
    }

    all(".cat-chip").forEach(function (chip) {
      chip.addEventListener("click", function () {
        var name = chip.dataset.filter;
        var value = chip.dataset.value;
        if (!value) {
          filters[name] = [];                 // the All chip clears the set
        } else {
          var at = filters[name].indexOf(value);
          if (at === -1) filters[name].push(value); else filters[name].splice(at, 1);
        }
        all('.cat-chip[data-filter="' + name + '"]').forEach(function (c) {
          var on = c.dataset.value
            ? filters[name].indexOf(c.dataset.value) !== -1
            : filters[name].length === 0;     // All lights up when none are
          c.classList.toggle("is-active", on);
          c.setAttribute("aria-pressed", on ? "true" : "false");
        });
        apply();
      });
    });

    /* -- selection -- */

    function renderTray() {
      var tray = $("cat-tray");
      tray.hidden = selected.length === 0;
      $("cat-tray-n").textContent = selected.length;
      $("cat-tray-codes").innerHTML = selected
        .map(function (c) { return "<span>" + c + "</span>"; })
        .join("");
      // Reserve the tray's real height, not a guess. It wraps to ~169px on a
      // narrow screen, and a fixed 120px left the last card half-covered.
      if (!selected.length) {
        document.body.style.paddingBottom = "";
      } else {
        requestAnimationFrame(function () {
          document.body.style.paddingBottom =
            Math.ceil(tray.getBoundingClientRect().height + 16) + "px";
        });
      }
    }

    function toggle(card) {
      var code = card.dataset.code;
      var i = selected.indexOf(code);
      if (i === -1) selected.push(code); else selected.splice(i, 1);
      card.setAttribute("aria-pressed", i === -1 ? "true" : "false");
      renderTray();

      // Only additions are recorded, and only the code. It answers "which
      // creators draw interest" without tracking the person browsing.
      if (CFG.api && i === -1) {
        fetch(CFG.api + "/api/event", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ kind: "shortlist", detail: code })
        }).catch(function () { /* analytics must never break selecting */ });
      }
    }

    cards.forEach(function (card) {
      card.addEventListener("click", function (e) {
        // The platform mark is a real link out; clicking it must not also
        // toggle the card it sits on.
        if (e.target.closest && e.target.closest("[data-noselect]")) return;
        toggle(card);
      });
      card.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(card); }
      });
    });

    $("cat-clear").addEventListener("click", function () {
      selected = [];
      cards.forEach(function (c) { c.setAttribute("aria-pressed", "false"); });
      renderTray();
    });

    /* -- name a selection and review it -- */

    // Quoting happens on the selection page, not here. The roster is for
    // picking; the total and the request live where the shortlist is settled.

    var saveModal = $("cat-save-modal");
    function closeSave() { saveModal.hidden = true; }
    $("cat-save").addEventListener("click", function () {
      if (!selected.length) return;
      $("cat-save-n").textContent = selected.length;
      $("cat-save-out").hidden = true;
      $("cat-save-form").hidden = false;
      saveModal.hidden = false;
      saveModal.querySelector("input").focus();
    });
    $("cat-save-close").addEventListener("click", closeSave);
    saveModal.addEventListener("click", function (e) { if (e.target === saveModal) closeSave(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !saveModal.hidden) closeSave();
    });

    $("cat-save-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var name = new FormData(e.target).get("selname").trim() || "Selection";
      // Resolved against this page, not the origin: under a base path such as
      // GitHub Pages' /<repo>/ an origin-rooted URL points outside the site.
      var url = new URL("selection/", location.href).href + buildFragment(name, selected);
      $("cat-share-url").value = url;
      $("cat-share-open").href = url;
      e.target.hidden = true;
      $("cat-save-out").hidden = false;
      $("cat-share-url").focus();
      $("cat-share-url").select();
      // Straight to the selection, in a new tab so the catalogue and the
      // shortlist they just built are both still there.
      window.open(url, "_blank", "noopener");
    });

    $("cat-share-copy").addEventListener("click", function () {
      var btn = $("cat-share-copy");
      copyText($("cat-share-url").value,
        function () { btn.textContent = "Copied";
          setTimeout(function () { btn.textContent = "Copy"; }, 1800); },
        function () { btn.textContent = "Copy failed"; });
    });

    /* -- marquees only animate while they are on screen -- */

    // Both bands are very wide layers. Left running off-screen they keep the
    // compositor busy for no visible benefit, which is most of the time on a
    // 30,000px page.
    if ("IntersectionObserver" in window) {
      var tracks = all(".cat-ticker__track, .cat-clients__row");
      tracks.forEach(function (t) { t.style.animationPlayState = "paused"; });
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          en.target.style.animationPlayState = en.isIntersecting ? "running" : "paused";
        });
      }, { rootMargin: "200px 0px" });
      tracks.forEach(function (t) { io.observe(t); });
    }

    apply();
    renderTray();
  }


  /* ------------------------------------------------- quote request form */

  // Shared by the catalogue and the selection page. Both submit the same
  // payload; the selection page adds the name the selection was saved under.
  function wireQuoteForm(onCleared) {
    /* -- request modal -- */

    var modal = $("cat-modal");

    function openModal() {
      if (!selected.length) return;
      $("cat-modal-n").textContent = selected.length;
      modal.hidden = false;
      modal.querySelector("input").focus();
    }
    function closeModal() { modal.hidden = true; }

    var form = $("cat-form");
    var done = $("cat-done");

    // Set on a successful submission and read by the copy button, because the
    // selection is cleared the moment the panel closes — reading location.href
    // then would hand back an emptied link.
    var doneLink = "";

    function closeAfterDone() {
      closeModal();
      modal.classList.remove("is-done");
      form.hidden = false;
      done.hidden = true;
      $("cat-form-status").textContent = "";
      $("cat-done-note").textContent = "";
      if (typeof onCleared === "function") onCleared();
    }

    $("cat-request").addEventListener("click", openModal);
    $("cat-modal-close").addEventListener("click", function () {
      if (done && !done.hidden) closeAfterDone(); else closeModal();
    });
    modal.addEventListener("click", function (e) {
      if (e.target !== modal) return;
      if (done && !done.hidden) closeAfterDone(); else closeModal();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape" || modal.hidden) return;
      if (done && !done.hidden) closeAfterDone(); else closeModal();
    });

    if (done) {
      $("cat-done-copy").addEventListener("click", function () {
        var btn = $("cat-done-copy");
        var note = $("cat-done-note");
        copyText(doneLink,
          function () {
            btn.textContent = "Copied";
            note.textContent = "Anyone with this link and the access code sees this selection.";
            setTimeout(function () { btn.textContent = "Copy selection link"; }, 2200);
          },
          function () { note.textContent = "Could not copy automatically: " + doneLink; });
      });
    }

    function succeed(link) {
      doneLink = link;
      form.reset();
      form.hidden = true;
      $("cat-form-status").textContent = "";
      // The heading, the count and the pricing caveat all belong to the form
      // that has just gone. Leaving "Request a quote" above "Thank you for
      // your submission" reads as though it did not send.
      modal.classList.add("is-done");
      done.hidden = false;
      $("cat-done-copy").focus();
    }

    $("cat-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var status = $("cat-form-status");
      var btn = e.target.querySelector("button[type=submit]");
      var data = new FormData(e.target);

      if (!CFG.endpoint) {
        status.className = "cat-form__status is-error";
        status.textContent = "Submission endpoint is not configured yet. Nothing was sent.";
        return;
      }

      // Every field the card carries, spelled out per creator. A list of bare
      // codes meant cross-referencing the private key by hand for every
      // enquiry; this is enough to act on without opening anything else.
      function detail(code, i) {
        var card = document.querySelector('.cat-card[data-code="' + code + '"]');
        if (!card) return (i + 1) + ". " + code + " (not found in this build)";

        function metaValue(label) {
          var row = all(".cat-card__meta li", card).filter(function (li) {
            var k = li.querySelector("span");
            return k && k.textContent.trim().toLowerCase() === label;
          })[0];
          var v = row && row.querySelector("strong");
          return v ? v.textContent.trim() : "—";
        }

        var nameEl = card.querySelector(".cat-card__name");
        var link = card.querySelector("a.cat-card__platform");
        // The card no longer shows a price — the client sees a total for the
        // shortlist and nothing per creator. This email goes to HelloVoice, so
        // it still carries the per-creator band, read from the tier table.
        var band = TIER_PRICE[card.dataset.tier];
        var profile = link ? link.getAttribute("href") : "";
        var handle = profile
          ? "@" + profile.replace(/\/$/, "").split("/").pop().replace(/^@/, "")
          : "";

        return [
          (i + 1) + ". " + code + (nameEl ? " — " + nameEl.textContent.trim() : ""),
          "   Platform   " + card.dataset.platform + (handle ? "  " + handle : ""),
          profile ? "   Profile    " + profile : null,
          "   Followers  " + metaValue("followers"),
          "   City       " + card.dataset.city,
          "   Tier       " + card.dataset.tier,
          "   Price      " + (band ? money(band[0]) + " – " + money(band[1]) + " SAR" : "—")
        ].filter(Boolean).join("\n");
      }

      var lines = selected.map(detail);

      // tier split and the indicative total, so the quote has a starting point
      var tally = {}, lo = 0, hi = 0;
      selected.forEach(function (code) {
        var card = document.querySelector('.cat-card[data-code="' + code + '"]');
        if (!card) return;
        var t = card.dataset.tier;
        tally[t] = (tally[t] || 0) + 1;
        var p = TIER_PRICE[t];
        if (p) { lo += p[0]; hi += p[1]; }
      });
      var split = Object.keys(tally).map(function (t) {
        return t + " " + tally[t];
      }).join(", ");

      var payload = {
        _subject: (selectionName ? selectionName + " — " : "Catalogue quote request — ") +
                  (data.get("company") || "unknown"),
        _template: "table",
        _captcha: "false",
        name: data.get("name"),
        company: data.get("company"),
        email: data.get("email"),
        phone: data.get("phone"),
        selection_name: selectionName || "(unnamed)",
        // The exact shortlist the client was looking at, reopenable. On the
        // selection page that is simply this URL; from the roster it is the
        // same link the Save panel would have produced. The fragment never
        // reaches a server on its own, but it travels fine inside the payload.
        selection_link: (PAGE === "selection")
          ? location.href
          : new URL("selection/", location.href).href +
            buildFragment(selectionName || (data.get("company") || "Client") + " selection", selected),
        creators_selected: selected.length,
        tier_split: split || "—",
        indicative_total: lo ? lo.toLocaleString("en-US") + " – " + hi.toLocaleString("en-US") + " SAR" : "—",
        selection: lines.join("\n\n"),
        submitted_at: new Date().toISOString(),
        catalogue: "HelloVoice Creator Roster"
      };

      btn.disabled = true;
      status.className = "cat-form__status";
      status.textContent = "Sending…";

      if (CFG.api) {
        // Stored against the access code that opened the catalogue, so the
        // dashboard can show who asked without an inbox in the loop.
        fetch(CFG.api + "/api/request", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            name: data.get("name"), company: data.get("company"),
            email: data.get("email"), phone: data.get("phone"),
            selection_name: selectionName || null,
            selection: selected.slice()
          })
        })
          .then(function (r) { return r.json().catch(function () { return null; }); })
          .then(function (b) {
            if (!b || !b.ok) throw new Error((b && b.reason) || "failed");
            succeed(payload.selection_link);
          })
          .catch(function () {
            status.className = "cat-form__status is-error";
            status.textContent = "That did not send. Please try again, or contact us directly.";
          })
          .then(function () { btn.disabled = false; });
        return;
      }

      fetch(CFG.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        // The page sets <meta name="referrer" content="no-referrer"> so a click
        // out to a creator's profile does not tell Instagram where it came
        // from. FormSubmit identifies the form BY the referrer, and without one
        // rejects every submission with "open this page through a web server".
        // Send the origin — and only the origin — for this one request.
        referrerPolicy: "strict-origin",
        body: JSON.stringify(payload)
      })
        .then(function (r) {
          // FormSubmit answers 200 with {"success":"false"} for a rejected
          // submission — an unactivated address, a bad origin. Trusting the
          // status code alone told the client "Sent" when nothing was.
          return r.json().catch(function () { return null; }).then(function (body) {
            if (!r.ok) throw new Error("HTTP " + r.status);
            if (body && String(body.success) === "false") {
              throw new Error(body.message || "rejected");
            }
            return body;
          });
        })
        .then(function () {
          succeed(payload.selection_link);
        })
        .catch(function () {
          status.className = "cat-form__status is-error";
          status.textContent = "That did not send. Please try again, or contact us directly.";
        })
        .then(function () { btn.disabled = false; });
    });

  }

  /* ---------------------------------------------------------- selection */

  // navigator.clipboard is unavailable on plain http, which is exactly how
  // this is reviewed locally, so fall back to a hidden field + execCommand.
  function copyText(text, done, fail) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { legacy(); });
    } else { legacy(); }
    function legacy() {
      var t = document.createElement("textarea");
      t.value = text;
      t.setAttribute("readonly", "");
      t.style.cssText = "position:fixed;top:-1000px;opacity:0";
      document.body.appendChild(t);
      t.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      t.remove();
      ok ? done() : fail();
    }
  }

  // Tier price ranges. The builder writes today's bands in as a fallback, and
  // in API mode the server sends the live ones with the roster — so editing a
  // band in the dashboard re-prices every selection immediately, without
  // rebuilding the page. Without that, a rate changed in the dashboard would
  // show one number here and another in the quote.
  var TIER_PRICE = CFG.tierPrice || {
    "Nano":     [435, 870],
    "Micro":    [870, 1740],
    "Mid-Tier": [1450, 2900],
    "Macro":    [2175, 4350]
  };

  function adoptTiers(list) {
    if (!list || !list.length) return;
    var next = {};
    list.forEach(function (t) {
      if (t && t.name) next[t.name] = [Number(t.from) || 0, Number(t.to) || 0];
    });
    if (Object.keys(next).length) TIER_PRICE = next;
  }

  function money(n) { return n.toLocaleString("en-US"); }

  function initSelection() {
    var cards = all(".cat-card");
    var byCode = {};
    cards.forEach(function (c) { byCode[c.dataset.code] = c; });

    var frag = readFragment();
    selectionName = frag.name || "Selection";
    // Keep only codes this build actually knows about — a stale link naming a
    // creator who has since left the roster should drop that card, not break.
    selected = frag.codes.filter(function (code) { return !!byCode[code]; });
    var dropped = frag.codes.length - selected.length;

    function render() {
      cards.forEach(function (c) { c.hidden = selected.indexOf(c.dataset.code) === -1; });

      // Order the visible cards the way the link lists them.
      var grid = $("cat-grid");
      selected.forEach(function (code) {
        var card = byCode[code];
        if (card) grid.appendChild(card);
      });

      $("sel-title").textContent = selectionName;
      document.title = selectionName + " — HelloVoice";
      $("cat-empty").hidden = selected.length !== 0;

      // summary: count, per-tier split, indicative total range
      var tiers = {}, lo = 0, hi = 0;
      selected.forEach(function (code) {
        var t = byCode[code].dataset.tier;
        tiers[t] = (tiers[t] || 0) + 1;
        var p = TIER_PRICE[t];
        if (p) { lo += p[0]; hi += p[1]; }
      });
      var rows = [
        ["Creators", String(selected.length)],
        ["Indicative range", selected.length ? money(lo) + " – " + money(hi) + " SAR" : "—"]
      ];
      Object.keys(TIER_PRICE).forEach(function (t) {
        if (tiers[t]) rows.push([t, String(tiers[t])]);
      });
      if (dropped) rows.push(["Not in this roster", String(dropped)]);
      $("sel-summary").innerHTML = rows.map(function (r) {
        return "<div><dt>" + r[0] + "</dt><dd>" + r[1] + "</dd></div>";
      }).join("");

      // keep the URL in step so what they see is what they can re-share
      var want = buildFragment(selectionName, selected);
      if (location.hash !== want) history.replaceState(null, "", want);

      var closing = $("cat-close");
      if (closing) closing.hidden = selected.length === 0;

      var tray = $("cat-tray");
      tray.hidden = selected.length === 0;
      $("cat-tray-n").textContent = selected.length;
      $("cat-tray-codes").innerHTML = "";
      if (!selected.length) { document.body.style.paddingBottom = ""; return; }
      requestAnimationFrame(function () {
        document.body.style.paddingBottom =
          Math.ceil(tray.getBoundingClientRect().height + 16) + "px";
      });
    }

    // A remove control per card, added here rather than in the markup so the
    // catalogue and the selection page can share one card template.
    cards.forEach(function (card) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cat-card__remove";
      btn.setAttribute("data-noselect", "");
      btn.setAttribute("aria-label", "Remove " + card.dataset.code + " from this selection");
      btn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M5 5l14 14M19 5L5 19"/></svg>';
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var i = selected.indexOf(card.dataset.code);
        if (i !== -1) { selected.splice(i, 1); render(); }
      });
      card.querySelector(".cat-card__media").appendChild(btn);
      // cards are not togglable here — the selection is the content
      card.removeAttribute("tabindex");
      card.removeAttribute("role");
      card.removeAttribute("aria-pressed");
    });

    wireQuoteForm(function () { selected = []; render(); });
    var second = $("cat-request-2");
    if (second) second.addEventListener("click", function () { $("cat-request").click(); });

    var copyBtn = $("cat-copy-link");
    if (copyBtn) copyBtn.addEventListener("click", function () {
      var note = $("cat-copied");
      copyText(location.href,
        function () {
          copyBtn.textContent = "Copied";
          if (note) note.textContent = "Link copied. Anyone with it and the access code sees this selection.";
          setTimeout(function () { copyBtn.textContent = "Copy link"; }, 2200);
        },
        function () {
          if (note) note.textContent = "Could not copy automatically — the link is in the address bar.";
        });
    });
    window.addEventListener("hashchange", function () {
      var f = readFragment();
      selectionName = f.name || "Selection";
      selected = f.codes.filter(function (c) { return !!byCode[c]; });
      render();
    });
    render();
  }

  /* --------------------------------------------------------- deterrence */

  ["contextmenu", "dragstart", "selectstart", "copy", "cut"].forEach(function (evt) {
    document.addEventListener(evt, function (e) {
      if (e.target.closest && e.target.closest(".cat-form, .cat-gate__form, [data-noselect]")) return;
      e.preventDefault();
    });
  });

  document.addEventListener("keydown", function (e) {
    var k = (e.key || "").toLowerCase();
    var mod = e.ctrlKey || e.metaKey;
    if (mod && ["s", "p", "u", "c", "x", "a"].indexOf(k) !== -1) {
      if (e.target.closest && e.target.closest(".cat-form, .cat-gate__form")) return;
      e.preventDefault();
    }
    if (k === "f12") e.preventDefault();
    if (mod && e.shiftKey && ["i", "j", "c"].indexOf(k) !== -1) e.preventDefault();
  });

  // Frost the page when the window loses focus — makes over-the-shoulder
  // screen capture from a second app noticeably harder to do cleanly.
  window.addEventListener("blur", function () { document.body.classList.add("cat-away"); });
  window.addEventListener("focus", function () { document.body.classList.remove("cat-away"); });

  // Last thing in the file, deliberately — see the note by `wasUnlocked`.
  if (wasUnlocked && CFG.api) {
    // The tab remembers unlocking, but the server decides. A revoked or expired
    // code lands back on the gate rather than on an empty page.
    fetch(CFG.api + "/api/roster", { credentials: "include" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (b) {
        if (b && b.ok) { ROSTER = b.roster || []; adoptTiers(b.tiers); unlock(); }
        else { forget(); }
      })
      .catch(function () { /* leave the gate up */ });
  } else if (wasUnlocked) {
    unlock();
  }
})();
