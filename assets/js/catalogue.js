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
    var out = { name: "", codes: [], token: "" };
    raw.split("&").forEach(function (pair) {
      var i = pair.indexOf("=");
      if (i === -1) return;
      var k = pair.slice(0, i), v = pair.slice(i + 1);
      try { v = decodeURIComponent(v); } catch (e) { /* leave raw */ }
      if (k === "n") out.name = v;
      if (k === "c") out.codes = v.split(",").map(function (x) { return x.trim(); }).filter(Boolean);
      if (k === "s") out.token = v;
    });
    return out;
  }

  // A link for a client. With a token the shortlist is on the server, so the
  // link is just that token — the long form listed every code and ran past a
  // hundred characters before the name. `full` is for links that stay inside
  // the site (going back to the catalogue to add someone), where the codes
  // save a round trip.
  function buildFragment(name, codes, full) {
    var token = (CURATED && CURATED.token) || CARRIED_TOKEN || "";
    if (token && !full) return "#s=" + encodeURIComponent(token);
    return "#n=" + encodeURIComponent(name) + "&c=" + codes.join(",") +
      (token ? "&s=" + encodeURIComponent(token) : "");
  }

  // A selection prepared and priced in the dashboard. Set on the selection
  // page when its link carries a token; its prices beat everything else.
  var CURATED = null;

  // The shortlist being edited, when the client came back from its page to add
  // or remove creators. Saving again updates that shortlist.
  var CARRIED_TOKEN = "";

  // Tell the service about a shortlist a client just named. Answers with the
  // token that identifies it, or nothing when there is no service to tell.
  function register(name, codes, token) {
    if (!CFG.api || !codes.length) return Promise.resolve("");
    return fetch(CFG.api + "/api/selection", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ name: name, codes: codes, token: token || "" })
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (b) {
        var t = (b && b.ok && b.token) || "";
        // Tell the portal layer (portal.js) a shortlist was saved, so it can offer the brief questions.
        if (t) { try { window.dispatchEvent(new CustomEvent("hv:selection-saved", { detail: { token: t, name: name, codes: codes } })); } catch (e) { /* old browser */ } }
        return t;
      })
      .catch(function () { return ""; });
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

  var unlocked = false;
  function unlock() {
    if (unlocked) return;
    unlocked = true;
    document.body.classList.remove("cat-locked", "cat-shell");
    var gate = $("cat-gate"); if (gate) gate.remove();
    var app = $("cat-app");
    app.hidden = false;
    var go = function () {
      initApp();
      backToTop();
      welcome();
      try { document.dispatchEvent(new CustomEvent("cat:unlocked")); } catch (e) {}
    };
    if (CFG.api && ROSTER) renderRoster(ROSTER, go); else go();
    // The catalogue is "ready" the moment its first screen of cards is drawn; the selection
    // page still waits for its own requests (the loader's generic check).
    if (PAGE === "catalogue" && window.hvLoader) window.hvLoader.done();
  }

  /* -- the page shell while the roster is on its way -- */
  // A browser that has been in before (the session hint or a kept roster) sees the page at
  // once: header, filters and skeleton cards, never the sign-in flashing up. If the server
  // then says no, the gate comes back.
  function skeletons(n) {
    var one = '<div class="cat-skel" aria-hidden="true"><span class="cat-skel__media"></span><span class="cat-skel__line"></span>' +
      '<span class="cat-skel__line cat-skel__line--short"></span><span class="cat-skel__line"></span></div>';
    return new Array(n + 1).join(one);
  }
  function showShell() {
    var app = $("cat-app"), grid = $("cat-grid"), gate = $("cat-gate");
    if (!app || !grid || unlocked) return;
    document.body.classList.add("cat-shell");
    document.body.classList.remove("cat-locked");
    if (gate) gate.hidden = true;
    app.hidden = false;
    if (PAGE === "catalogue" && !grid.children.length) grid.innerHTML = skeletons(8);
  }
  function hideShell() {
    if (unlocked || !document.body.classList.contains("cat-shell")) return;
    var app = $("cat-app"), grid = $("cat-grid"), gate = $("cat-gate");
    document.body.classList.remove("cat-shell");
    document.body.classList.add("cat-locked");
    if (grid) grid.innerHTML = "";
    if (app) app.hidden = true;
    if (gate) gate.hidden = false;
  }

  /* -- the whole roster used to be kept for this tab (sessionStorage "hv-roster"); the page is
     now served in batches, and an old copy is dropped on sight and on sign-out. -- */
  var RKEY = "hv-roster";
  function dropRoster() { try { sessionStorage.removeItem(RKEY); } catch (e) { /* blocked */ } }
  window.hvRosterDrop = dropRoster;

  /* The cover tag greets a signed-in client by first name; access-code
     guests and anyone the service does not know keep the plain "Welcome". */
  function welcome() {
    var tag = $("cat-welcome");
    if (!tag || !CFG.api) return;
    fetch(CFG.api + "/api/me", { credentials: "include" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (me) {
        var name = me && me.user && me.user.name ? String(me.user.name).trim().split(/\s+/)[0] : "";
        if (name) tag.textContent = "Welcome, " + name;
      })
      .catch(function () {});
  }

  /* --------------------------------------------------------- back to top */

  // A round arrow, bottom right, once the reader is a screen or so down. It
  // sits above the selection tray when the tray is showing, rather than on
  // top of its buttons.
  function backToTop() {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cat-top";
    btn.setAttribute("aria-label", "Back to top");
    btn.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg>';
    $("cat-app").appendChild(btn);

    var tray = $("cat-tray");
    // Cheap enough to run on every scroll event: one class toggle, and one
    // measurement only while the tray is up.
    function place() {
      var lift = (tray && !tray.hidden) ? tray.getBoundingClientRect().height : 0;
      btn.style.bottom = Math.ceil(lift + 20) + "px";
      btn.classList.toggle("is-shown", window.scrollY > window.innerHeight * 0.8);
    }
    window.addEventListener("scroll", place, { passive: true });
    window.addEventListener("resize", place);
    // The tray appears and grows as creators are picked, without a scroll.
    if (tray && "MutationObserver" in window) {
      new MutationObserver(place).observe(tray, { attributes: true, childList: true, subtree: true });
    }
    btn.addEventListener("click", function () {
      var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top: 0, behavior: still ? "auto" : "smooth" });
    });
    place();
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
  // Which shared link this page is: each one asks for its own access code once
  // in this browser (a selection by its token, otherwise the catalogue).
  var LINK = (function () {
    var m = /(?:^|[#&])s=([A-Za-z0-9_-]+)/.exec(location.hash || "");
    return /\/selection\/?/.test(location.pathname) && m ? "s:" + m[1] : "cat";
  })();

  var REFUSALS = {
    otherlink: "That code is for a different link. Use the code that came with this one.",
    expired: "That code has expired. Ask us for a new one.",
    revoked: "That code is no longer active. Ask us for a new one.",
    exhausted: "That code has already been used its maximum number of times.",
    // The code is fine but already open on as many devices as it allows —
    // the usual sign it was passed on.
    device_limit: "This code is already in use on its maximum number of devices. " +
      "Please contact us for your own access code.",
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
      body: JSON.stringify({ code: val, link: LINK, lite: true })
    })
      .then(function (r) { return r.json().then(function (b) { return { r: r, b: b }; }); })
      .then(function (res) {
        if (!res.b || !res.b.ok) {
          gateFail(REFUSALS[res.b && res.b.reason] || "That code is not right.");
          return;
        }
        // The pass is set; the roster itself comes the same way as on any visit (bootApi).
        remember();
        bootApi(true);
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

  // The tier the service worked out for one account of this creator.
  function accountTier(c, profile) {
    var list = c.accounts || [];
    for (var i = 0; i < list.length; i++) {
      if (list[i].url === profile.url && list[i].tier) return list[i].tier;
    }
    return "";
  }

  function metaRows(c, label) {
    var counted = (c.profiles || []).filter(function (p) { return p.followers; });
    // A selection quoted for one platform shows that account only: the client
    // is buying it, and the others would price the card against the wrong one.
    if (CURATED && CURATED.platform) {
      var only = counted.filter(function (p) {
        return (p.platform || "").toLowerCase() === CURATED.platform.toLowerCase();
      });
      if (only.length) {
        counted = only;
        var t = accountTier(c, only[0]);
        if (t) label = tierLabel(t);
      }
    }
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
        // Each account carries its own tier: 120K on Instagram and 20K on
        // TikTok are two different audiences, and a campaign booking one of
        // them is buying that one.
        var t = accountTier(c, p);
        rows.push("<li><span>" + tag + "</span><strong><b>" + commas(p.followers) +
                  "</b>" + (t ? "<em class=\"cat-card__band\">" + esc(tierLabel(t)) + "</em>" : "") +
                  "</strong></li>");
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
    // Nationality is held back from the cards until the roster's values have
    // been checked in the dashboard. The data still arrives; it is not drawn.
    rows.push("<li><span>City</span><strong>" + esc(c.city || "Unspecified") +
              "</strong></li>");
    rows.push("<li><span>Tier</span><strong>" + esc(label) + "</strong></li>");
    return rows.join("");
  }

  // Everyone who follows this creator, across the accounts we know counts
  // for — what "most followers" sorts on. Falls back to the headline figure.
  function totalFollowers(c) {
    var sum = (c.profiles || []).reduce(function (t, p) {
      return t + (Number(p.followers) || 0);
    }, 0);
    return sum || Number(c.followers) || 0;
  }

  function cardMarkup(c, i) {
    var label = tierLabel(c.tier);
    if (CURATED && CURATED.platform) {
      (c.accounts || []).forEach(function (a) {
        if (a.tier && (a.platform || "").toLowerCase() === CURATED.platform.toLowerCase()) {
          label = tierLabel(a.tier);
        }
      });
    }
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
    // A real <img>: loaded only as it nears the screen, decoded off the main thread, sized by
    // the card. (It used to be a CSS background, which the browser cannot lazy-load.)
    var photo = src
      ? '<div class="cat-card__photo' + soft + '"><img class="cat-card__img" src="' + esc(src) +
        '" alt="" loading="lazy" decoding="async" width="330" height="330" fetchpriority="' + (i < 8 ? "high" : "low") + '"></div>'
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
      (c.price && c.price.length ? '" data-price="' + esc(c.price.join("-")) : "") +
      '" data-followers="' + totalFollowers(c) + '" data-name="' + esc(c.name) +
      '" data-idx="' + (i || 0) +
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
      // The creator's passport: their full analysis, or a locked page that
      // lets the client ask for one. Only where the server is behind the page
      // — the static build has no passport to open.
      (CFG.api ? '<a class="cat-card__analysis' + (c.analysis ? " is-ready" : "") + '" href="' +
        (document.body.getAttribute("data-page") === "selection" ? "../" : "") + "creator/#c=" +
        encodeURIComponent(c.code) + '" data-noselect data-analysis="' + esc(c.code) + '" data-name="' + esc(c.name) + '">' +
        (c.analysis ? "Profile analysis" : "Analysis — request") +
        ' <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" ' +
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h16"/><path d="M7 16v-4M11 16V9M15 16v-6M19 16V6"/><path d="M5 9l5-4 4 3 6-5"/></svg></a>' : "") +
      "</div></article>";
  }

  // The first screen of cards at once, the rest in small slices while the browser is idle,
  // then `done` (filters, sort and selection are wired on the full set). On the selection
  // page every card starts hidden: only the selection's own are shown, by initSelection.
  var FIRST = 48;
  function renderRoster(list, done) {
    var grid = $("cat-grid");
    if (!grid) { if (done) done(); return; }
    var hide = PAGE === "selection";
    var mark = function (c, i) { var html = cardMarkup(c, i); return hide ? html.replace("<article ", "<article hidden ") : html; };
    if (PAGE !== "catalogue" || list.length <= FIRST) {
      grid.innerHTML = list.map(mark).join("");
      if (done) done();
      return;
    }
    grid.innerHTML = list.slice(0, FIRST).map(mark).join("");
    var i = FIRST;
    var later = window.requestIdleCallback ? function (fn) { requestIdleCallback(fn, { timeout: 120 }); } : function (fn) { setTimeout(fn, 16); };
    (function slice() {
      var t0 = Date.now(), html = [];
      while (i < list.length && (html.length < 40 || Date.now() - t0 < 10)) { html.push(mark(list[i], i)); i++; if (html.length >= 160) break; }
      grid.insertAdjacentHTML("beforeend", html.join(""));
      if (i < list.length) later(slice); else if (done) done();
    })();
  }

  /* ------------------------------------------------------ places, by country */

  // The roster holds a city, sometimes a country, sometimes a note typed into
  // the field. Filters group the cities under their country so Riyadh and
  // Jeddah sit under Saudi Arabia rather than between Dubai and Cairo.
  // Matching still uses the raw value on the card; this is only how it reads.

  /* Small drawn flags for the "Where they are" panel. Simplified on purpose:
     at 30x20 the colour bands are what people recognise. */
  function serrated(color, n) {
    var pts = ["0,0", "8,0"], step = 20 / (2 * n);
    for (var i = 1; i < 2 * n; i++) pts.push((i % 2 ? 11 : 8) + "," + (i * step).toFixed(2));
    pts.push("8,20", "0,20");
    return '<rect width="30" height="20" fill="' + color + '"/><polygon fill="#fff" points="' + pts.join(" ") + '"/>';
  }
  function bands(a, b, c) {
    return '<rect width="30" height="6.7" fill="' + a + '"/><rect y="6.6" width="30" height="6.8" fill="' + b +
      '"/><rect y="13.3" width="30" height="6.7" fill="' + c + '"/>';
  }
  var FLAGS = {
    "Egypt": bands("#ce1126", "#fff", "#111") + '<circle cx="15" cy="10" r="2" fill="#c09300"/>',
    "Saudi Arabia": '<rect width="30" height="20" fill="#006c35"/><rect x="8" y="6.5" width="14" height="1.7" rx=".8" fill="#fff"/>' +
      '<rect x="9" y="12" width="12" height="1" fill="#fff"/><rect x="20" y="11.2" width="1.2" height="2.6" fill="#fff"/>',
    "UAE": bands("#00732f", "#fff", "#111") + '<rect width="8" height="20" fill="#ff0000"/>',
    "Kuwait": bands("#007a3d", "#fff", "#ce1126") + '<polygon points="0,0 8,6.7 8,13.3 0,20" fill="#111"/>',
    "Qatar": serrated("#8a1538", 9),
    "Bahrain": serrated("#ce1126", 5),
    "Oman": '<rect width="30" height="20" fill="#db161b"/><rect x="8" width="22" height="6.7" fill="#fff"/><rect x="8" y="13.3" width="22" height="6.7" fill="#008000"/>',
    "Jordan": bands("#111", "#fff", "#007a3d") + '<polygon points="0,0 14,10 0,20" fill="#ce1126"/><circle cx="4.6" cy="10" r="1.3" fill="#fff"/>',
    "Lebanon": '<rect width="30" height="20" fill="#ed1c24"/><rect y="5" width="30" height="10" fill="#fff"/><polygon points="15,6 19.5,13.5 10.5,13.5" fill="#00a651"/>',
    "Iraq": bands("#ce1126", "#fff", "#111") + '<rect x="10" y="9.2" width="10" height="1.6" rx=".8" fill="#007a3d"/>',
    "Morocco": '<rect width="30" height="20" fill="#c1272d"/><polygon points="15,5.5 16.3,9.3 20.3,9.3 17.1,11.7 18.3,15.5 15,13.2 11.7,15.5 12.9,11.7 9.7,9.3 13.7,9.3" fill="none" stroke="#006233" stroke-width="1"/>'
  };
  var ICON_GLOBE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.4 3.6 5.2 3.6 8.5s-1.2 6.1-3.6 8.5c-2.4-2.4-3.6-5.2-3.6-8.5S9.6 5.9 12 3.5z"/></svg>';
  function flagOf(country) {
    var f = FLAGS[country];
    return f ? '<svg class="cat-flag" viewBox="0 0 30 20" aria-hidden="true">' + f + "</svg>"
             : '<span class="cat-flag cat-flag--none">' + ICON_GLOBE + "</span>";
  }
  var STAT_ICONS = {
    "Creators": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="9" cy="8.5" r="3.2"/><path d="M3.5 19c.6-3.2 2.8-5 5.5-5s4.9 1.8 5.5 5"/><circle cx="16.8" cy="9.5" r="2.5"/><path d="M15.6 14.2c2.4-.3 4.3 1.2 4.9 4"/></svg>',
    "Indicative range": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 12.6V4.5a1 1 0 0 1 1-1h8.1l8 8a1.5 1.5 0 0 1 0 2.1l-6.9 6.9a1.5 1.5 0 0 1-2.1 0z"/><circle cx="8.3" cy="8.3" r="1.5"/></svg>',
    "Quoted for": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="6" y="2.8" width="12" height="18.4" rx="2.6"/><path d="M10.5 18h3"/></svg>',
    "Not in this roster": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v5.5M12 16.4v.1"/></svg>'
  };

  function shareBar(n, total) {
    var pct = total ? Math.round(100 * n / total) : 0;
    return '<span class="cat-meter" role="img" aria-label="' + pct + '% of the selection"><i style="width:' + pct + '%"></i></span>' +
      '<span class="cat-meter__pct">' + pct + "%</span>";
  }
  var COUNTRY_ORDER = ["Saudi Arabia", "UAE", "Egypt", "Kuwait", "Qatar", "Bahrain",
                       "Oman", "Jordan", "Lebanon"];
  var PLACES = {
    "Saudi Arabia": ["riyadh", "jeddah", "jedda", "dammam", "khobar", "al khobar", "dhahran",
      "taif", "makkah", "mecca", "madinah", "medina", "elmadina elmonawara", "al madinah",
      "najran", "abha", "khamis mushait", "tabuk", "jazan", "jizan", "hail", "qassim",
      "buraidah", "al ahsa", "hofuf", "jubail", "yanbu", "al kharj", "ksa", "saudi arabia",
      "saudi", "saudi arabia not specified yet"],
    "UAE": ["dubai", "abu dhabi", "sharjah", "ajman", "al ain", "ras al khaimah",
      "umm al quwain", "fujairah", "uae", "united arab emirates", "emirates"],
    "Egypt": ["cairo", "giza", "alexandria", "mansora", "mansoura", "boursaeed", "port said",
      "tanta", "zagazig", "egypt"],
    "Kuwait": ["kuwait", "kuwait city"],
    "Qatar": ["qatar", "doha"],
    "Bahrain": ["bahrain", "manama"],
    "Oman": ["oman", "muscat"],
    "Jordan": ["jordan", "amman"],
    "Lebanon": ["lebanon", "beirut"]
  };
  // Spellings in the roster that read better another way.
  var PLACE_LABEL = {
    "elmadina elmonawara": "Madinah", "al madinah": "Madinah", "medina": "Madinah",
    "mecca": "Makkah", "jedda": "Jeddah", "al khobar": "Khobar", "boursaeed": "Port Said",
    "mansora": "Mansoura", "jizan": "Jazan"
  };
  // Values that name a country and no city.
  var COUNTRY_WORDS = ["ksa", "saudi", "saudi arabia", "saudi arabia not specified yet", "uae", "united arab emirates",
    "emirates", "egypt", "kuwait", "qatar", "bahrain", "oman", "jordan", "lebanon"];
  var COUNTRY_OF = {};
  Object.keys(PLACES).forEach(function (country) {
    PLACES[country].forEach(function (p) { COUNTRY_OF[p] = country; });
  });

  function titleCase(s) {
    return s.replace(/\b[a-z]/g, function (ch) { return ch.toUpperCase(); });
  }

  // One raw city value -> {country, label, key}. A value that is a country
  // on its own ("UAE") is a creator in that country whose city we lack.
  function place(raw) {
    // "Kuwait Not Specified yet": a creator in that country whose city we
    // do not have yet. Filed under the country as "City not specified".
    var pending = String(raw || "").match(/^\s*(.+?)\s+not specified yet\s*$/i);
    if (pending) {
      var named = pending[1].toLowerCase();
      var land = COUNTRY_OF[named] ||
        COUNTRY_ORDER.filter(function (c) { return c.toLowerCase() === named; })[0] ||
        titleCase(named);
      return { country: land, label: "City not specified", key: land + "|City not specified" };
    }
    var clean = String(raw || "").replace(/\(([^)]*)\)?/g, " ").replace(/[()]/g, " ")
      .replace(/\s+/g, " ").trim();
    var k = clean.toLowerCase();
    // "UAE (Ajman)": a city named in the brackets is more exact than the
    // country outside them.
    var inner = ((String(raw).match(/\(([^)]*)/) || [])[1] || "").toLowerCase().trim();
    if (COUNTRY_OF[inner] && (!COUNTRY_OF[k] || COUNTRY_WORDS.indexOf(k) !== -1)) k = inner;
    var country = COUNTRY_OF[k];
    if (!country) {
      var other = titleCase(clean.toLowerCase()) || "Other";
      return { country: "Other", label: other, key: "Other|" + other };
    }
    var label = COUNTRY_WORDS.indexOf(k) !== -1 ? "City not specified"
      : (PLACE_LABEL[k] || titleCase(k));
    return { country: country, label: label, key: country + "|" + label };
  }

  /* ------------------------------------------------------ filters and sort */

  var CHEVRON = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>';
  var CROSS = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';

  var SORTS = [
    ["", "Recommended"],
    ["followers-desc", "Most followers"],
    ["followers-asc", "Fewest followers"],
    ["tier-desc", "Tier: largest first"],
    ["tier-asc", "Tier: smallest first"],
    ["name", "Name A–Z"]
  ];

  // How big a tier is. HCP tiers rank alongside the band they mirror, so
  // "HCP - Macro" sorts with Macro rather than after Mega.
  var TIER_SIZE = ["nano", "micro", "mid-tier", "mid", "macro", "mega"];
  function tierRank(name) {
    var base = String(name || "").replace(/^hcp\s*-\s*/i, "").toLowerCase();
    var i = TIER_SIZE.indexOf(base);
    if (i === 3) i = 2;
    if (i === -1) i = Object.keys(TIER_PRICE).indexOf(name);
    return i * 2 + (/^hcp/i.test(name) ? 1 : 0);
  }

  // Text for matching: lower case, accents and styled letters (the 𝓓𝓻 some
  // names use) folded to plain ones, Arabic hamza forms on alef unified, and
  // spaces squeezed — so "dr hala" finds "𝓓𝓻.𝓗𝓪𝓵𝓪".
  function fold(text) {
    var t = String(text || "");
    try { t = t.normalize("NFKD"); } catch (e) { /* very old browser */ }
    return t.replace(/[̀-ًͯ-ٟ]/g, "")
      .replace(/[أإآ]/g, "ا").replace(/ى/g, "ي").replace(/ة/g, "ه")
      .toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  }

  // "50K", "1.2m", "50,000" -> a number; anything else -> null.
  function readCount(text) {
    var m = String(text || "").replace(/[,\s]/g, "").toLowerCase().match(/^(\d+(?:\.\d+)?)([km]?)$/);
    if (!m) return null;
    var n = parseFloat(m[1]) * (m[2] === "m" ? 1e6 : m[2] === "k" ? 1e3 : 1);
    return n > 0 ? Math.round(n) : null;
  }
  // 1200000 -> "1.2M", 50000 -> "50K".
  function short(n) {
    if (n >= 1e6) return (Math.round(n / 1e5) / 10).toString().replace(/\.0$/, "") + "M";
    if (n >= 1e3) return (Math.round(n / 1e2) / 10).toString().replace(/\.0$/, "") + "K";
    return String(n);
  }
  function rangeLabel(r) {
    if (r[0] && r[1]) return "Followers " + short(r[0]) + " – " + short(r[1]);
    if (r[0]) return "Followers " + short(r[0]) + "+";
    return "Followers up to " + short(r[1]);
  }

  // One filter bar for a set of cards: Tier, Platform, Location, Interest,
  // each a dropdown of checkboxes, plus a sort. OR within a dimension, AND
  // across them. Built from the cards themselves, so the selection page gets
  // options for exactly the creators in that selection.
  // `facets` (the catalogue served page by page): the options come from the server
  // (/api/roster/facets, most common first) instead of from cards on the page, and
  // filtering, sorting and grouping happen on the server; query() hands it the state.
  function Controls(host, cards, onChange, extras, facets) {
    // followers: [] for no limit, else [min, max] with either end null.
    // The catalogue opens most-followed first (all platforms added up); a selection keeps
    // the order its link gives. "Recommended" is still there to pick.
    var DEFAULT_SORT = extras ? "" : "followers-desc";
    var state = { tier: [], platform: [], place: [], interest: [], followers: [], sort: DEFAULT_SORT, q: "" };
    // `extras` (the selection page): more filters of the same kind, in their own colour (fit,
    // role, tags), and the matching score to sort on.
    var xdims = extras ? extras.dims : [];
    xdims.forEach(function (d) { state[d] = []; });

    cards.forEach(function (card) {
      card._tier = card.dataset.tier ? [card.dataset.tier] : [];
      card._platform = values(card.dataset.platform);
      card._interest = values(card.dataset.interest);
      card._place = values(card.dataset.city).filter(function (v) {
        return !/^unspecified$/i.test(v);
      }).map(function (v) { return place(v).key; });
    });

    function tally(field) {
      var out = {};
      if (facets) {
        // Only the order matters to the bar (it shows no counts): first is most common.
        var list = facets[field] || [];
        list.forEach(function (v, i) { out[v] = list.length - i; });
        return out;
      }
      cards.forEach(function (c) {
        c["_" + field].forEach(function (v) { out[v] = (out[v] || 0) + 1; });
      });
      return out;
    }

    function option(dim, value, label) {
      return '<label class="cat-opt"><input type="checkbox" data-dim="' + dim +
        '" value="' + esc(value) + '"/><span class="cat-opt__box" aria-hidden="true"></span>' +
        '<span class="cat-opt__label">' + esc(label) + "</span></label>";
    }

    function dropdown(dim, title, body, wide, cls) {
      return '<div class="cat-dd' + (wide ? " cat-dd--wide" : "") + (cls ? " " + cls : "") + '" data-dim="' + dim + '">' +
        '<button type="button" class="cat-dd__btn" aria-expanded="false">' +
        '<span>' + title + '</span>' + CHEVRON + "</button>" +
        '<div class="cat-dd__panel" role="group" aria-label="' + title + '" hidden>' +
        '<div class="cat-dd__head"><span>' + title + '</span>' +
        '<button type="button" class="cat-dd__close" aria-label="Close">' + CROSS + "</button></div>" +
        '<div class="cat-dd__body">' + body + "</div>" +
        '<div class="cat-dd__foot"><button type="button" class="cat-dd__clear">Clear</button>' +
        '<button type="button" class="cat-dd__done">Show creators</button></div></div></div>';
    }

    var html = "";

    // Tier: follower bands first, healthcare professionals as their own group.
    var tiers = tally("tier");
    var tierKeys = Object.keys(tiers).sort(function (a, b) { return tierRank(a) - tierRank(b); });
    var reg = tierKeys.filter(function (t) { return !/^hcp/i.test(t); });
    var hcp = tierKeys.filter(function (t) { return /^hcp/i.test(t); });
    if (tierKeys.length > 1) {
      var tb = "";
      if (reg.length) {
        tb += '<div class="cat-dd__group">' + (hcp.length ? '<p class="cat-dd__title">Creators</p>' : "") +
          reg.map(function (t) { return option("tier", t, tierLabel(t), tiers[t]); }).join("") + "</div>";
      }
      if (hcp.length) {
        tb += '<div class="cat-dd__group"><p class="cat-dd__title">Healthcare professionals</p>' +
          hcp.map(function (t) {
            return option("tier", t, tierLabel(t.replace(/^hcp\s*-\s*/i, "")), tiers[t]);
          }).join("") + "</div>";
      }
      html += dropdown("tier", "Tier", tb);
    }

    // Followers: any range, typed as 50K, 1.2M or 50,000. Counted across all
    // of a creator's accounts — the same figure "Most followers" sorts on.
    html += dropdown("followers", "Followers",
      '<div class="cat-range">' +
      '<label class="cat-range__field"><span>From</span><input type="text" inputmode="decimal" ' +
      'data-range="min" placeholder="e.g. 50K" autocomplete="off"/></label>' +
      '<span class="cat-range__dash" aria-hidden="true">–</span>' +
      '<label class="cat-range__field"><span>To</span><input type="text" inputmode="decimal" ' +
      'data-range="max" placeholder="no limit" autocomplete="off"/></label></div>' +
      '<p class="cat-dd__title">Quick picks</p><div class="cat-range__presets">' +
      [["Under 10K", 0, 10000], ["10K – 100K", 10000, 100000], ["100K – 1M", 100000, 1000000],
       ["50K+", 50000, null], ["500K+", 500000, null], ["1M+", 1000000, null]].map(function (q) {
        return '<button type="button" class="cat-range__preset" data-min="' + (q[1] || "") +
          '" data-max="' + (q[2] || "") + '">' + q[0] + "</button>";
      }).join("") + "</div>");

    var plats = tally("platform");
    var platKeys = Object.keys(plats).sort(function (a, b) { return plats[b] - plats[a]; });
    if (platKeys.length > 1) {
      html += dropdown("platform", "Platform", '<div class="cat-dd__group">' +
        platKeys.map(function (p) { return option("platform", p, p, plats[p]); }).join("") + "</div>");
    }

    // Location: countries in a fixed order, each with its cities by size.
    var places = tally("place");
    var byCountry = {};
    Object.keys(places).forEach(function (key) {
      var country = key.split("|")[0];
      (byCountry[country] = byCountry[country] || []).push(key);
    });
    var countries = Object.keys(byCountry).sort(function (a, b) {
      var ia = COUNTRY_ORDER.indexOf(a), ib = COUNTRY_ORDER.indexOf(b);
      if (a === "Other") return 1;
      if (b === "Other") return -1;
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib) || a.localeCompare(b);
    });
    if (Object.keys(places).length > 1) {
      var lb = countries.map(function (country) {
        var keys = byCountry[country].sort(function (a, b) {
          var na = /\|City not specified$/.test(a), nb = /\|City not specified$/.test(b);
          return (na - nb) || (places[b] - places[a]);
        });
        return '<div class="cat-dd__group cat-dd__group--country">' +
          '<label class="cat-opt cat-opt--country"><input type="checkbox" data-country="' +
          esc(country) + '"/><span class="cat-opt__box" aria-hidden="true"></span>' +
          '<span class="cat-opt__label">' + esc(country === "Other" ? "Other locations" : country) +
          "</span></label>" +
          '<div class="cat-dd__cities">' +
          keys.map(function (k) { return option("place", k, k.split("|")[1], places[k]); }).join("") +
          "</div></div>";
      }).join("");
      html += dropdown("place", "Location", lb, true);
    }

    // Interest only when it separates anyone — one value across the roster
    // is a claim, not a filter.
    var ints = tally("interest");
    var intKeys = Object.keys(ints).sort(function (a, b) { return ints[b] - ints[a]; });
    if (intKeys.length > 1) {
      html += dropdown("interest", "Interest", '<div class="cat-dd__group cat-dd__group--cols">' +
        intKeys.map(function (v) { return option("interest", v, v, ints[v]); }).join("") + "</div>",
        intKeys.length > 8);
    }

    var sortList = SORTS.concat(extras ? [["fit-desc", "Best fit first"], ["fit-asc", "Lowest fit first"]] : []);
    var sort = '<label class="cat-sort"><span class="cat-sort__label">Sort</span>' +
      '<select class="cat-sort__select" aria-label="Sort creators">' +
      sortList.map(function (s) { return '<option value="' + s[0] + '"' + (s[0] === DEFAULT_SORT ? " selected" : "") + ">" + s[1] + "</option>"; }).join("") +
      "</select>" + CHEVRON + "</label>";

    var bar = document.createElement("div");
    bar.className = "cat-bar";
    // Search by name (or code), above the filters. Matching ignores case and
    // the decorative letters some creators use in their display names.
    bar.innerHTML = '<label class="cat-search"><svg viewBox="0 0 24 24" width="18" height="18" ' +
      'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">' +
      '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>' +
      '<input type="search" class="cat-search__input" placeholder="Search creators by name" ' +
      'aria-label="Search creators by name" autocomplete="off" spellcheck="false"/></label>' +
      '<div class="cat-bar__row"><div class="cat-bar__filters">' +
      '<span class="cat-bar__label">Filter</span>' + html +
      (extras ? '<span class="cat-bar__sep" aria-hidden="true"></span><div class="cat-bar__match" hidden></div>' : "") +
      "</div>" + sort + "</div>" +
      '<div class="cat-active" hidden></div>';
    host.insertBefore(bar, host.firstChild);

    var active = bar.querySelector(".cat-active");
    function ddList() { return all(".cat-dd", bar); }

    function close(dd) {
      if (!dd) return;
      dd.classList.remove("is-open");
      dd.querySelector(".cat-dd__btn").setAttribute("aria-expanded", "false");
      dd.querySelector(".cat-dd__panel").hidden = true;
      document.body.classList.remove("cat-sheet-open");
    }
    function closeAll(except) { ddList().forEach(function (d) { if (d !== except) close(d); }); }
    function open(dd) {
      closeAll(dd);
      dd.classList.add("is-open");
      dd.querySelector(".cat-dd__btn").setAttribute("aria-expanded", "true");
      var panel = dd.querySelector(".cat-dd__panel");
      panel.hidden = false;
      // Keep the panel on screen when its button sits near the right edge.
      panel.style.left = ""; panel.style.right = "";
      if (window.innerWidth > 767) {
        var r = panel.getBoundingClientRect();
        if (r.right > window.innerWidth - 12) { panel.style.left = "auto"; panel.style.right = "0"; }
      } else {
        document.body.classList.add("cat-sheet-open");
      }
    }

    function labelOf(dim, v) {
      if (dim === "place") return v.split("|")[1] === "City not specified"
        ? v.split("|")[0] : v.split("|")[1];
      if (dim === "tier") return /^hcp/i.test(v) ? "HCP " + tierLabel(v.replace(/^hcp\s*-\s*/i, "")) : tierLabel(v);
      return v;
    }

    function sync() {
      // The range boxes, unless someone is typing in them.
      all("input[data-range]", bar).forEach(function (box) {
        if (box === document.activeElement) return;
        var v = state.followers[box.dataset.range === "min" ? 0 : 1];
        box.value = v ? short(v) : "";
      });
      // Checkboxes, counts on the buttons, country tri-state, active pills.
      all("input[data-dim]", bar).forEach(function (box) {
        box.checked = state[box.dataset.dim].indexOf(box.value) !== -1;
      });
      all("input[data-country]", bar).forEach(function (box) {
        var cities = all('input[data-dim="place"]', box.closest(".cat-dd__group"));
        var on = cities.filter(function (c) { return c.checked; }).length;
        box.checked = on > 0 && on === cities.length;
        box.indeterminate = on > 0 && on < cities.length;
      });
      ddList().forEach(function (dd) {
        var n = state[dd.dataset.dim].length;
        dd.classList.toggle("has-value", n > 0);
        // How many options are picked, inside the button: "Tier 2".
        var btn = dd.querySelector(".cat-dd__btn"), badge = btn && btn.querySelector(".cat-dd__n");
        if (btn && !badge) { badge = document.createElement("b"); badge.className = "cat-dd__n"; btn.insertBefore(badge, btn.lastElementChild); }
        if (badge) { badge.textContent = n ? String(n) : ""; badge.hidden = !n; }
      });
      var pills = [];
      ["tier", "platform", "place", "interest"].concat(xdims).forEach(function (dim) {
        // A whole country picked reads as the country, not ten cities.
        var shown = state[dim].slice();
        if (dim === "place") {
          all("input[data-country]", bar).forEach(function (box) {
            if (!box.checked) return;
            var cities = all('input[data-dim="place"]', box.closest(".cat-dd__group"))
              .map(function (c) { return c.value; });
            if (cities.length < 2) return;
            shown = shown.filter(function (v) { return cities.indexOf(v) === -1; });
            pills.push('<button type="button" class="cat-pill-x" data-country="' + esc(box.dataset.country) +
              '">' + esc(box.dataset.country === "Other" ? "Other locations" : box.dataset.country) +
              CROSS + "</button>");
          });
        }
        shown.forEach(function (v) {
          pills.push('<button type="button" class="cat-pill-x" data-dim="' + dim + '" data-value="' +
            esc(v) + '" aria-label="Remove ' + esc(labelOf(dim, v)) + '">' + esc(labelOf(dim, v)) +
            CROSS + "</button>");
        });
      });
      if (state.followers.length) {
        pills.push('<button type="button" class="cat-pill-x" data-range-pill="1">' +
          esc(rangeLabel(state.followers)) + CROSS + "</button>");
      }
      active.hidden = !pills.length;
      active.innerHTML = pills.join("") +
        (pills.length ? '<button type="button" class="cat-active__clear">Clear all</button>' : "");
    }

    function changed() { sync(); onChange(); }

    bar.addEventListener("click", function (e) {
      var btn = e.target.closest(".cat-dd__btn");
      if (btn) {
        var dd = btn.closest(".cat-dd");
        if (dd.classList.contains("is-open")) close(dd); else open(dd);
        return;
      }
      if (e.target.closest(".cat-dd__done, .cat-dd__close")) { close(e.target.closest(".cat-dd")); return; }
      if (e.target.closest(".cat-dd__clear")) {
        state[e.target.closest(".cat-dd").dataset.dim] = [];
        changed(); return;
      }
      var preset = e.target.closest(".cat-range__preset");
      if (preset) {
        setRange(Number(preset.dataset.min) || null, Number(preset.dataset.max) || null);
        return;
      }
      var pill = e.target.closest(".cat-pill-x");
      if (pill && pill.dataset.rangePill) { state.followers = []; changed(); return; }
      if (pill) {
        if (pill.dataset.country) {
          var group = bar.querySelector('input[data-country="' + pill.dataset.country + '"]')
            .closest(".cat-dd__group");
          var drop = all('input[data-dim="place"]', group).map(function (c) { return c.value; });
          state.place = state.place.filter(function (v) { return drop.indexOf(v) === -1; });
        } else {
          state[pill.dataset.dim] = state[pill.dataset.dim].filter(function (v) {
            return v !== pill.dataset.value;
          });
        }
        changed(); return;
      }
      if (e.target.closest(".cat-active__clear")) {
        state.tier = []; state.platform = []; state.place = []; state.interest = [];
        state.followers = []; xdims.forEach(function (d) { state[d] = []; });
        state.q = "";
        var sbox = bar.querySelector(".cat-search__input");
        if (sbox) sbox.value = "";
        changed();
      }
    });

    function setRange(min, max) {
      if (min && max && max < min) { var t = min; min = max; max = t; }
      state.followers = (min || max) ? [min || null, max || null] : [];
      changed();
    }
    // Typing narrows the cards as you go; the pill and button follow.
    bar.addEventListener("input", function (e) {
      if (e.target.classList && e.target.classList.contains("cat-search__input")) {
        state.q = fold(e.target.value);
        onChange();
        return;
      }
      if (!e.target.dataset || !e.target.dataset.range) return;
      var lo = readCount(bar.querySelector('input[data-range="min"]').value);
      var hi = readCount(bar.querySelector('input[data-range="max"]').value);
      setRange(lo, hi);
    });

    bar.addEventListener("change", function (e) {
      var box = e.target;
      if (box.dataset.dim) {
        var list = state[box.dataset.dim], at = list.indexOf(box.value);
        if (box.checked && at === -1) list.push(box.value);
        if (!box.checked && at !== -1) list.splice(at, 1);
        changed();
      } else if (box.dataset.country) {
        // A country picks or clears every city under it.
        var cities = all('input[data-dim="place"]', box.closest(".cat-dd__group"))
          .map(function (c) { return c.value; });
        state.place = state.place.filter(function (v) { return cities.indexOf(v) === -1; });
        if (box.checked) state.place = state.place.concat(cities);
        changed();
      } else if (box.classList.contains("cat-sort__select") && !box.closest(".cat-group-by")) {   // not the Group menu
        state.sort = box.value;
        onChange();
      }
    });

    document.addEventListener("click", function (e) {
      if (!e.target.closest || !e.target.closest(".cat-dd")) closeAll();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeAll();
    });

    sync();

    return {
      matches: function (card) {
        if (state.q) {
          if (card._search === undefined) {
            card._search = fold((card.dataset.name || "") + " " + (card.dataset.code || ""));
          }
          if (card._search.indexOf(state.q) === -1) return false;
        }
        if (state.followers.length) {
          var f = Number(card.dataset.followers) || 0;
          if (state.followers[0] && f < state.followers[0]) return false;
          if (state.followers[1] && f > state.followers[1]) return false;
        }
        if (!["tier", "platform", "place", "interest"].every(function (dim) {
          if (!state[dim].length) return true;
          return card["_" + dim].some(function (v) { return state[dim].indexOf(v) !== -1; });
        })) return false;
        return xdims.every(function (dim) {
          if (!state[dim].length) return true;
          return extras.of(card, dim).some(function (v) { return state[dim].indexOf(v) !== -1; });
        });
      },
      filtering: function () {
        return !!(state.tier.length || state.platform.length || state.place.length ||
                  state.interest.length || state.followers.length || !!state.q ||
                  xdims.some(function (d) { return state[d].length; }));
      },
      // Rebuild the extra dropdowns from what the cards say now (scores load late, tags change).
      refresh: function () {
        if (!extras) return;
        var holder = bar.querySelector(".cat-bar__match");
        var any = false;
        xdims.forEach(function (dim) {
          var vals = extras.values(dim);
          state[dim] = state[dim].filter(function (v) { return vals.some(function (x) { return x[0] === v; }); });
          var body = vals.length ? '<div class="cat-dd__group">' + vals.map(function (x) {
            return '<label class="cat-opt"><input type="checkbox" data-dim="' + dim + '" value="' + esc(x[0]) +
              '"/><span class="cat-opt__box" aria-hidden="true"></span>' +
              (extras.dot && extras.dot(dim, x[0]) ? '<i class="cat-dot cat-dot--' + extras.dot(dim, x[0]) + '"></i>' : "") +
              '<span class="cat-opt__label">' + esc(x[0]) + '</span><span class="cat-opt__n">' + x[1] + "</span></label>";
          }).join("") + "</div>" : "";
          var dd = holder.querySelector('.cat-dd[data-dim="' + dim + '"]');
          if (!vals.length) { if (dd) dd.remove(); return; }
          any = true;
          if (!dd) {
            holder.insertAdjacentHTML("beforeend", dropdown(dim, extras.titles[dim], body, vals.length > 8, "cat-dd--match"));
          } else if (dd.dataset.sig !== body) {
            // Only when the options really changed: rewriting them under a finger loses focus.
            dd.querySelector(".cat-dd__body").innerHTML = body;
          }
          holder.querySelector('.cat-dd[data-dim="' + dim + '"]').dataset.sig = body;
        });
        holder.hidden = !any;
        bar.querySelector(".cat-bar__sep").hidden = !any;
        sync();
      },
      // Sorted copy of `list`; with no sort chosen, the list as given.
      order: function (list) {
        var s = state.sort;
        if (!s) return list.slice();
        var f = function (c) { return Number(c.dataset.followers) || 0; };
        var name = function (c) { return (c.dataset.name || "").toLowerCase(); };
        return list.slice().sort(function (a, b) {
          if (s === "followers-desc") return f(b) - f(a);
          if (s === "followers-asc") return f(a) - f(b);
          if (s === "tier-desc") return (tierRank(b.dataset.tier) - tierRank(a.dataset.tier)) || f(b) - f(a);
          if (s === "tier-asc") return (tierRank(a.dataset.tier) - tierRank(b.dataset.tier)) || f(b) - f(a);
          if (s === "name") return name(a).localeCompare(name(b));
          if (extras && (s === "fit-desc" || s === "fit-asc")) {
            var sa = extras.score(a), sb = extras.score(b);        // not scored sorts last either way
            if (sa == null && sb == null) return 0;
            if (sa == null) return 1;
            if (sb == null) return -1;
            return s === "fit-desc" ? sb - sa : sa - sb;
          }
          return 0;
        });
      },
      sorted: function () { return !!state.sort; },
      // The catalogue's server mode: the state to send, and to put back on return.
      query: function () {
        return { tier: state.tier.slice(), platform: state.platform.slice(), place: state.place.slice(),
                 interest: state.interest.slice(), followers: state.followers.slice(), sort: state.sort, q: state.q,
                 text: (bar.querySelector(".cat-search__input") || {}).value || "" };
      },
      restore: function (st) {
        ["tier", "platform", "place", "interest", "followers"].forEach(function (d) { if (st && Array.isArray(st[d])) state[d] = st[d].slice(); });
        if (st && typeof st.sort === "string") state.sort = st.sort;
        if (st && typeof st.q === "string") state.q = st.q;
        var sbox = bar.querySelector(".cat-search__input");
        if (sbox && st && typeof st.text === "string") sbox.value = st.text;
        var sel = bar.querySelector(".cat-sort:not(.cat-group-by) .cat-sort__select");
        if (sel) sel.value = state.sort;
        sync();
      }
    };
  }

  /* ------------------------------------------------------------- the app */

  function initApp() {
    if (PAGE === "selection") { initSelection(); return; }
    var grid = $("cat-grid");
    // With the service behind the page the roster arrives in batches (FEED, from the loader at
    // the bottom of this file); the static build still carries every card in its HTML.
    var SERVER = !!(CFG.api && FEED);
    var cards = SERVER ? [] : all(".cat-card");
    var host = document.querySelector(".cat-controls .cat-container");
    var controls = host ? Controls(host, cards, apply, null, SERVER ? FEED.facets : null) : null;

    /* -- group by: the roster split into sections by one parameter -- */
    var G_DIMS = [["", "None"], ["tier", "Creator size"], ["platform", "Platform"], ["country", "Country"], ["interest", "Interest"]];
    var G_NONE = { tier: "No tier", platform: "No platform", country: "Location not specified", interest: "No interest listed" };
    var byCodeAll = {};
    cards.forEach(function (c) { byCodeAll[c.dataset.code] = c; });
    function gKeys(card, dim) {
      var out = [];
      if (dim === "tier") out = card.dataset.tier ? [card.dataset.tier] : [];
      else if (dim === "platform") out = values(card.dataset.platform);
      else if (dim === "interest") out = values(card.dataset.interest);
      else if (dim === "country") values(card.dataset.city).forEach(function (v) {
        if (/^unspecified$/i.test(v)) return;
        var c = place(v).country;
        if (out.indexOf(c) < 0) out.push(c);
      });
      return out.length ? out : [G_NONE[dim]];
    }
    var gStore = "hv-group:catalogue", gBy = "";
    try { gBy = sessionStorage.getItem(gStore) || ""; } catch (e) {}
    if (controls) {
      var gRow = document.querySelector(".cat-bar__row");
      var gSort = gRow && gRow.querySelector(".cat-sort");
      if (gRow) {
        var gLab = document.createElement("label");
        gLab.className = "cat-sort cat-group-by";
        gLab.innerHTML = '<span class="cat-sort__label">Group</span><select class="cat-sort__select" aria-label="Group creators by">' +
          G_DIMS.map(function (d) { return '<option value="' + d[0] + '"' + (d[0] === gBy ? " selected" : "") + ">" + d[1] + "</option>"; }).join("") +
          "</select>" + CHEVRON;
        var gWrap = document.createElement("div");
        gWrap.className = "cat-bar__order";
        if (gSort) { gRow.insertBefore(gWrap, gSort); gWrap.appendChild(gLab); gWrap.appendChild(gSort); }
        else { gWrap.appendChild(gLab); gRow.appendChild(gWrap); }
        gLab.querySelector("select").addEventListener("change", function (e) {
          gBy = e.target.value;
          try { sessionStorage.setItem(gStore, gBy); } catch (x) {}
          apply();
        });
      }
    }
    function gOrder(names, count) {
      var fixed = gBy === "tier" ? Object.keys(TIER_PRICE) : gBy === "country" ? COUNTRY_ORDER : null;
      return names.sort(function (a, b) {
        var na = a === G_NONE[gBy], nb = b === G_NONE[gBy];
        if (na !== nb) return na ? 1 : -1;
        if (fixed) {
          var ia = fixed.indexOf(a), ib = fixed.indexOf(b);
          if (ia !== ib) return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
        }
        return (count[b] - count[a]) || a.localeCompare(b);
      });
    }
    // A creator in two groups shows in both; the copy passes its clicks to the
    // real card, so picking from either one picks the creator.
    function layoutGroups(list) {
      all(".cat-group", grid).forEach(function (g) { g.remove(); });
      grid.classList.toggle("is-grouped", !!gBy);
      if (!gBy) return;
      var members = {}, count = {};
      list.forEach(function (card) {
        if (card.hidden) return;
        gKeys(card, gBy).forEach(function (k) { (members[k] = members[k] || []).push(card); count[k] = (count[k] || 0) + 1; });
      });
      var placed = {};
      gOrder(Object.keys(members), count).forEach(function (k) {
        var sec = document.createElement("section");
        sec.className = "cat-group";
        var flag = gBy === "country" && k !== G_NONE.country ? flagOf(k) : "";
        var mark = gBy === "platform" && ICONS[k] ? '<span class="cat-places__mark ' + (BRAND[k] || "") + '">' + ICONS[k] + "</span>" : "";
        sec.innerHTML = '<header class="cat-group__head">' + flag + mark + '<h2 class="cat-group__name">' + esc(k) + "</h2></header>";
        var inner = document.createElement("div");
        inner.className = "cat-grid cat-group__grid";
        members[k].forEach(function (card) {
          var code = card.dataset.code;
          if (!placed[code]) { placed[code] = true; inner.appendChild(card); return; }
          var cp = card.cloneNode(true);
          cp.classList.add("cat-card--copy");
          cp.addEventListener("click", function (e) {
            if (e.target.closest && e.target.closest("[data-noselect]")) return;
            toggle(byCodeAll[code]);
          });
          cp.addEventListener("keydown", function (e) {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(byCodeAll[code]); }
          });
          inner.appendChild(cp);
        });
        sec.appendChild(inner);
        grid.appendChild(sec);
      });
    }

    /* -- the catalogue served page by page (fix batch 3, item 16) --
       The page used to download the whole roster and filter, sort and group it here. Now the
       server does that (admin/paging.py) and hands over 48 cards at a time: the next batch is
       asked for as the reader nears the end of the grid. What is on screen is kept for this
       tab (filters, group, picks, how far they scrolled), so coming back from a creator's
       profile lands on the same card. */
    var feed = { gen: 0, cursor: null, more: false, busy: false, n: 0, match: null, v: "", seen: {}, lastG: null, lastInner: null,
                 pinned: null, waiters: [] };
    var EXTRA = { lic: [], disc: null, dplat: null };
    var VIEW = "hv-cat-view", VIEW_TTL = 30 * 60 * 1000;
    function feedParams() {
      var st = controls ? controls.query() : { tier: [], platform: [], place: [], interest: [], followers: [], sort: "followers-desc", q: "" };
      var p = new URLSearchParams();
      p.set("link", LINK);
      ["tier", "platform", "place", "interest"].forEach(function (d) { st[d].forEach(function (v) { p.append(d, v); }); });
      if (st.q) p.set("q", st.q);
      if (st.followers[0]) p.set("fmin", st.followers[0]);
      if (st.followers[1]) p.set("fmax", st.followers[1]);
      p.set("sort", st.sort || "");
      if (gBy) p.set("group", gBy);
      EXTRA.lic.forEach(function (v) { p.append("lic", v); });
      if (EXTRA.disc) { p.set("disc", JSON.stringify(EXTRA.disc)); if (EXTRA.dplat) p.set("dplat", EXTRA.dplat); }
      return p;
    }
    function feedGet(path, p) {
      return fetch(CFG.api + path + "?" + p.toString(), { credentials: "include" }).then(function (r) {
        // The pass ended (12 hours, a revoked code): back to the gate, as /api/roster did.
        if (r.status === 401 || r.status === 403) { forget(); try { sessionStorage.removeItem(VIEW); } catch (e) { /* blocked */ } location.reload(); return null; }
        return r.ok ? r.json() : null;
      });
    }
    // "Loading more": Helvy flipping through cards, and a row of skeleton cards, under the grid.
    var moreRow = document.createElement("div");
    moreRow.className = "cat-more";
    moreRow.hidden = true;
    moreRow.setAttribute("role", "status");
    moreRow.innerHTML = '<div class="cat-more__bar"><span class="cat-more__helvy" aria-hidden="true"></span>' +
      '<p class="cat-more__txt">Loading more creators</p></div><div class="cat-grid cat-more__skel" aria-hidden="true">' + skeletons(4) + "</div>";
    var sentinel = document.createElement("div");
    sentinel.className = "cat-sentinel";
    sentinel.setAttribute("aria-hidden", "true");
    function mountMore() {
      if (!grid || moreRow.parentNode) return;
      grid.parentNode.insertBefore(moreRow, grid.nextSibling);
      grid.parentNode.insertBefore(sentinel, moreRow);
      var slot = moreRow.querySelector(".cat-more__helvy");
      if (window.HVHelvy && window.HVHelvy.video) slot.appendChild(window.HVHelvy.video("cards", { cls: "cat-more__clip" }));
      else slot.innerHTML = '<span class="cat-more__dot"></span>';
    }
    function settleWaiters() { var w = feed.waiters; feed.waiters = []; w.forEach(function (fn) { try { fn(); } catch (e) { /* a listener */ } }); }
    function paintItems(items) {
      var html = [], target = grid, flush = function () {
        if (html.length) target.insertAdjacentHTML("beforeend", html.join(""));
        html = [];
      };
      items.forEach(function (c) {
        if (gBy && c.g !== feed.lastG) {
          flush();
          feed.lastG = c.g;
          var sec = document.createElement("section");
          sec.className = "cat-group";
          var flag = gBy === "country" && c.g !== G_NONE.country ? flagOf(c.g) : "";
          var mark = gBy === "platform" && ICONS[c.g] ? '<span class="cat-places__mark ' + (BRAND[c.g] || "") + '">' + ICONS[c.g] + "</span>" : "";
          sec.innerHTML = '<header class="cat-group__head">' + flag + mark + '<h2 class="cat-group__name">' + esc(c.g) + "</h2></header>";
          var inner = document.createElement("div");
          inner.className = "cat-grid cat-group__grid";
          sec.appendChild(inner);
          grid.appendChild(sec);
          feed.lastInner = inner;
        }
        if (gBy) target = feed.lastInner;
        var markup = cardMarkup(c, feed.n++);
        // A creator in two groups shows in both: the second is a copy; any click on either picks the creator.
        if (feed.seen[c.code]) markup = markup.replace('class="cat-card"', 'class="cat-card cat-card--copy"');
        feed.seen[c.code] = 1;
        if (selected.indexOf(c.code) !== -1) markup = markup.replace('aria-pressed="false"', 'aria-pressed="true"');
        html.push(markup);
      });
      flush();
    }
    function feedTake(b, gen) {
      if (gen !== feed.gen || !b) return false;
      feed.cursor = b.cursor || null;
      feed.more = !!b.has_more;
      feed.v = b.v || feed.v;
      paintItems(b.items || []);
      return true;
    }
    function feedReset(first, opts) {
      opts = opts || {};
      var gen = ++feed.gen;
      feed.pinned = null;
      feed.cursor = null; feed.more = false; feed.busy = true; feed.n = 0; feed.seen = {}; feed.lastG = null; feed.lastInner = null;
      grid.classList.toggle("is-grouped", !!gBy);
      var draw = function (b) {
        if (gen !== feed.gen) return;
        feed.busy = false;
        moreRow.hidden = true;
        if (!b || !b.ok) { feed.match = null; settleWaiters(); return; }
        grid.innerHTML = "";
        feed.match = b.match != null ? b.match : null;
        feedTake(b, gen);
        $("cat-empty").hidden = !!(b.items && b.items.length);
        if (opts.then) opts.then();
        settleWaiters();
        watchEnd();
      };
      if (first) { draw(first); return; }
      // The old cards stay until the new ones arrive (no flash); the grid dims meanwhile.
      grid.classList.add("is-loading");
      var p = feedParams();
      if (opts.limit) p.set("limit", opts.limit);
      feedGet("/api/roster/page", p).then(function (b) { if (gen === feed.gen) grid.classList.remove("is-loading"); draw(b); })
        .catch(function () { if (gen === feed.gen) { grid.classList.remove("is-loading"); feed.busy = false; settleWaiters(); } });
    }
    function feedMore() {
      if (feed.busy || !feed.more || !feed.cursor || feed.pinned) return;
      var gen = feed.gen;
      feed.busy = true;
      moreRow.hidden = false;
      var p = feedParams();
      p.set("cursor", feed.cursor);
      feedGet("/api/roster/page", p).then(function (b) {
        if (gen !== feed.gen) return;
        feed.busy = false;
        moreRow.hidden = true;
        if (b && b.ok) { feedTake(b, gen); watchEnd(); }
      }).catch(function () { if (gen === feed.gen) { feed.busy = false; moreRow.hidden = true; } });
    }
    // The next batch is asked for about two screens before the end, so a steady scroll never waits.
    var endWatch = null;
    function watchEnd() {
      mountMore();
      if (!("IntersectionObserver" in window)) {
        if (!endWatch) { endWatch = true; window.addEventListener("scroll", function () { if (sentinel.getBoundingClientRect().top < window.innerHeight * 3) feedMore(); }, { passive: true }); }
        return;
      }
      if (!endWatch) endWatch = new IntersectionObserver(function (en) { if (en[0].isIntersecting) feedMore(); }, { rootMargin: "0px 0px 1600px 0px" });
      // Observe afresh: still in view after a batch landed means "load the next one too".
      endWatch.unobserve(sentinel); endWatch.observe(sentinel);
    }
    var feedTimer = null;
    function feedApply() {
      if (!SERVER) return;
      clearTimeout(feedTimer);
      // Typing in the search box waits for a pause; a click on a filter goes at once.
      var typing = document.activeElement && document.activeElement.classList && document.activeElement.classList.contains("cat-search__input");
      feedTimer = setTimeout(function () { feedTimer = null; feedReset(null); }, typing ? 220 : 0);
    }
    /* -- where the reader was, kept for this tab -- */
    // The first card on screen and how far it sits from the top: the page above the grid can
    // change height between visits (the AI card, the licence row), a card cannot move.
    function viewAnchor() {
      var list = grid.querySelectorAll(".cat-card");
      for (var i = 0; i < list.length; i++) {
        var r = list[i].getBoundingClientRect();
        if (r.bottom > 80) return { code: list[i].dataset.code, copy: list[i].classList.contains("cat-card--copy"), top: Math.round(r.top) };
      }
      return null;
    }
    function viewSave() {
      if (!SERVER || feed.pinned) return;
      try {
        sessionStorage.setItem(VIEW, JSON.stringify({ t: Date.now(), q: controls ? controls.query() : null, g: gBy, x: EXTRA,
          n: feed.n, y: Math.round(window.scrollY), a: window.scrollY > 200 ? viewAnchor() : null,
          sel: selected, name: selectionName, tok: CARRIED_TOKEN }));
      } catch (e) { /* full or blocked */ }
    }
    function viewGo(k) {
      var go = function () {
        var el = k.a && grid.querySelector('.cat-card' + (k.a.copy ? ".cat-card--copy" : ":not(.cat-card--copy)") + '[data-code="' + String(k.a.code).replace(/"/g, "") + '"]');
        if (el) window.scrollTo(0, Math.max(0, window.scrollY + el.getBoundingClientRect().top - k.a.top));
        else window.scrollTo(0, k.y || 0);
      };
      requestAnimationFrame(go);
      // Once more after the parts above the grid have settled, unless the reader has moved since.
      var at = null;
      setTimeout(function () { at = window.scrollY; }, 60);
      setTimeout(function () { if (at === null || Math.abs(window.scrollY - at) < 4) go(); }, 900);
    }
    function viewKept() {
      try {
        var k = JSON.parse(sessionStorage.getItem(VIEW) || "null");
        return k && Date.now() - k.t < VIEW_TTL ? k : null;
      } catch (e) { return null; }
    }
    if (SERVER) {
      // pagehide, not unload: the page stays eligible for the back/forward cache, which brings
      // it back exactly as it was without asking the server for anything.
      window.addEventListener("pagehide", viewSave);
      document.addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden") viewSave(); });
      document.addEventListener("click", function (e) { if (e.target.closest && e.target.closest("a[href]")) viewSave(); }, true);
      try { if ("scrollRestoration" in history) history.scrollRestoration = "manual"; } catch (e) { /* old browser */ }
    }
    function cardsByCode(codes) {
      if (!codes.length) return Promise.resolve([]);
      var p = new URLSearchParams();
      p.set("link", LINK);
      p.set("codes", codes.slice(0, 200).join(","));
      return feedGet("/api/roster/cards", p).then(function (b) { return (b && b.ok && b.cards) || []; });
    }
    // portal.js reaches the server-side feed through this: the licence chips, the AI shortlist
    // (which shows only its picks, fetched by code), the assistant's "show me" and its counts.
    if (SERVER) window.hvCatalogue = {
      server: true,
      filter: function (key, value) { EXTRA[key] = value; feedApply(); },
      get: function (key) { return EXTRA[key]; },
      matched: function () { return feed.match; },
      loaded: function () { return feed.n; },
      settled: function () { return new Promise(function (ok) { if (!feed.busy && !feedTimer) ok(); else feed.waiters.push(ok); }); },
      cards: cardsByCode,
      pin: function (codes) {
        var gen = ++feed.gen;
        feed.busy = true;
        return cardsByCode(codes).then(function (list) {
          if (gen !== feed.gen) return [];
          feed.busy = false; feed.pinned = codes.slice(); feed.more = false; feed.cursor = null;
          feed.n = 0; feed.seen = {}; feed.lastG = null; feed.lastInner = null;
          grid.classList.remove("is-grouped");
          grid.innerHTML = "";
          var keep = gBy; gBy = ""; paintItems(list); gBy = keep;
          feed.match = list.length;
          moreRow.hidden = true;
          $("cat-empty").hidden = list.length > 0;
          settleWaiters();
          return list.map(function (c) { return c.code; });
        });
      },
      unpin: function () { if (feed.pinned) feedReset(null); }
    };

    /* -- filtering and sorting -- */

    function apply() {
      if (SERVER) { feedApply(); return; }
      var shown = 0;
      cards.forEach(function (card) {
        var ok = !controls || controls.matches(card);
        card.hidden = !ok;
        if (ok) shown++;
      });
      if (controls) {
        var list = controls.sorted() ? controls.order(cards)
          : cards.slice().sort(function (a, b) { return a.dataset.idx - b.dataset.idx; });
        list.forEach(function (c) { grid.appendChild(c); });
        layoutGroups(list);
      }
      // How many creators exist, and how many a filter leaves, is commercial
      // information: it belongs in the dashboard, not on the client page. Only
      // the empty state is still announced, so a filter that matches nobody
      // does not read as a broken page.
      $("cat-empty").hidden = shown !== 0;
    }

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
      all('.cat-card[data-code="' + code.replace(/"/g, "") + '"]').forEach(function (cp) { cp.setAttribute("aria-pressed", i === -1 ? "true" : "false"); });
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
    // Batches keep arriving, so the grid listens once for every card in it, now and later.
    if (SERVER) {
      grid.addEventListener("click", function (e) {
        var card = e.target.closest && e.target.closest(".cat-card");
        if (!card || (e.target.closest("[data-noselect]"))) return;
        toggle(card);
      });
      grid.addEventListener("keydown", function (e) {
        var card = e.target.classList && e.target.classList.contains("cat-card") ? e.target : null;
        if (card && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); toggle(card); }
      });
    }

    $("cat-clear").addEventListener("click", function () {
      selected = [];
      all(".cat-card").forEach(function (c) { c.setAttribute("aria-pressed", "false"); });
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
      var codes = selected.slice();
      var btn = e.target.querySelector("button");
      if (btn) btn.disabled = true;
      // Record it so it reaches the dashboard on its own, and so coming back
      // to add a creator updates the same shortlist rather than making a new
      // one. If that call fails the link still works, just unpriced.
      register(name, codes, CARRIED_TOKEN).then(function (token) {
        CARRIED_TOKEN = token || CARRIED_TOKEN;
        if (token) CURATED = { token: token, name: name, codes: codes, prices: {},
                               total: null, platform: "" };
        // Resolved against this page, not the origin: under a base path such as
        // GitHub Pages' /<repo>/ an origin-rooted URL points outside the site.
        var url = new URL("selection/", location.href).href + buildFragment(name, codes);
        $("cat-share-url").value = url;
        $("cat-share-open").href = url;
        e.target.hidden = true;
        $("cat-save-out").hidden = false;
        $("cat-share-url").focus();
        $("cat-share-url").select();
        if (btn) btn.disabled = false;
        // Straight to the selection, in a new tab so the catalogue and the
        // shortlist they just built are both still there.
        window.open(url, "_blank", "noopener");
      });
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

    // Coming back from a shortlist to add or remove creators: the link says
    // which ones are already in it, so the catalogue opens with them picked
    // and saving again updates that same shortlist.
    function carryIn(codes, name, token) {
      // Served page by page, most of the shortlist is not on screen yet: keep the codes, and
      // let the server drop any creator who has left the roster since.
      selected = SERVER ? codes.slice() : codes.filter(function (c) { return !!byCode(c); });
      if (SERVER) cardsByCode(codes).then(function (list) {
        var on = {};
        list.forEach(function (c) { on[c.code] = 1; });
        selected = selected.filter(function (c) { return on[c]; });
        renderTray();
      });
      selectionName = name || "";
      CARRIED_TOKEN = token || "";
      selected.forEach(function (c) {
        var card = byCode(c);
        if (card) card.setAttribute("aria-pressed", "true");
      });
      var nameField = $("cat-save-form") && $("cat-save-form").querySelector("[name=selname]");
      if (nameField) nameField.value = selectionName;
      if (selected.length) {
        var first = byCode(selected[0]);
        if (first) first.scrollIntoView({ block: "center" });
      }
    }

    var back = readFragment();
    // Back on the catalogue in this tab (from a creator's page, a refresh): the same filters,
    // group, picks and batches, then the same scroll position.
    var kept = SERVER && !back.codes.length && !back.token ? viewKept() : null;
    var plain = SERVER ? feedParams().toString() : "";
    if (kept) {
      if (controls && kept.q) controls.restore(kept.q);
      if (kept.x) { EXTRA.lic = kept.x.lic || []; EXTRA.disc = kept.x.disc || null; EXTRA.dplat = kept.x.dplat || null; }
      if (kept.g !== undefined && kept.g !== gBy) {
        gBy = kept.g || "";
        var gSel = document.querySelector(".cat-group-by select");
        if (gSel) gSel.value = gBy;
      }
      selected = (kept.sel || []).slice();
      selectionName = kept.name || "";
      CARRIED_TOKEN = kept.tok || "";
      var nf = $("cat-save-form") && $("cat-save-form").querySelector("[name=selname]");
      if (nf && selectionName) nf.value = selectionName;
    }
    if (back.codes.length) {
      carryIn(back.codes, back.name, back.token);
    } else if (back.token && CFG.api) {
      // Only a token: the shortlist is on the server. Ask for it, so a client
      // who opened a short link and then came here to add someone still finds
      // their creators picked rather than an empty catalogue.
      fetch(CFG.api + "/api/selection?s=" + encodeURIComponent(back.token),
            { credentials: "include" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (b) {
          if (!b || !b.ok) return;
          carryIn(b.codes || [], b.name, b.token || back.token);
          if (SERVER) all(".cat-card").forEach(function (c) { c.setAttribute("aria-pressed", selected.indexOf(c.dataset.code) !== -1 ? "true" : "false"); });
          else apply();
          renderTray();
        })
        .catch(function () { /* the catalogue still works, just unpicked */ });
    }

    if (!SERVER) apply();
    else if (kept && (kept.n > FIRST || kept.y > 0 || feedParams().toString() !== plain)) {
      // Every batch they had, in one request (the server allows up to ten), then their place.
      feedReset(null, { limit: Math.min(480, Math.max(FIRST, kept.n || 0)), then: function () { viewGo(kept); } });
    } else feedReset(FEED.key === feedParams().toString() ? FEED.first : null);
    renderTray();
  }

  function byCode(code) {
    return document.querySelector('.cat-card[data-code="' + code.replace(/"/g, "") + '"]');
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
        var band = priceOf(code, card);
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
          "   Price      " + priceText(band)
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
        var p = priceOf(code, card);
        if (p) { lo += p[0]; hi += p[1]; }
      });
      var fixed = curatedTotal();
      if (fixed) { lo = fixed[0]; hi = fixed[1]; }
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
        indicative_total: lo ? priceText([lo, hi]) : "—",
        currency: CURRENCY,
        price_note: "Indicative only, not a final price. Excludes taxes.",
        selection: lines.join("\n\n"),
        submitted_at: new Date().toISOString(),
        catalogue: "HelloVoice Creator Roster"
      };

      btn.disabled = true;
      status.className = "cat-form__status";
      status.textContent = "Sending…";

      function fail() {
        status.className = "cat-form__status is-error";
        status.textContent = "That did not send. Please try again, or contact us directly.";
      }

      // The email. FormSubmit answers 200 with {"success":"false"} for a
      // rejected submission — an unactivated address, a bad origin — so the
      // status code alone is not enough to call it sent.
      function sendMail() {
        if (!CFG.endpoint) return Promise.reject(new Error("no endpoint"));
        return fetch(CFG.endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/json" },
          // The page sets <meta name="referrer" content="no-referrer"> so a
          // click out to a creator's profile does not tell Instagram where it
          // came from. FormSubmit identifies the form BY the referrer, and
          // without one rejects every submission. Send the origin — and only
          // the origin — for this one request.
          referrerPolicy: "strict-origin",
          body: JSON.stringify(payload)
        }).then(function (r) {
          return r.json().catch(function () { return null; }).then(function (body) {
            if (!r.ok) throw new Error("HTTP " + r.status);
            if (body && String(body.success) === "false") {
              throw new Error(body.message || "rejected");
            }
            return body;
          });
        });
      }

      if (!CFG.api) {
        sendMail()
          .then(function () { succeed(payload.selection_link); })
          .catch(fail)
          .then(function () { btn.disabled = false; });
        return;
      }

      // API mode does BOTH. It used to store the request and stop there, so
      // the dashboard filled up while info@ received nothing — the email call
      // below was only ever reached by the static build. The stored copy is
      // the record; the email is how anyone finds out it arrived.
      var stored = fetch(CFG.api + "/api/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          name: data.get("name"), company: data.get("company"),
          email: data.get("email"), phone: data.get("phone"),
          selection_name: selectionName || null,
          // The saved selection this quote is for: the server checks the sender owns it.
          token: (CURATED && CURATED.token) || null,
          selection: selected.slice()
        })
      })
        .then(function (r) { return r.json().catch(function () { return null; }); })
        .then(function (b) {
          if (!b || !b.ok) throw new Error((b && b.reason) || "failed");
          return true;
        })
        .catch(function () { return false; });

      var mailed = sendMail()
        .then(function () { return { ok: true, why: "" }; })
        .catch(function (err) { return { ok: false, why: String(err && err.message || err) }; });

      Promise.all([stored, mailed]).then(function (res) {
        var mail = res[1];
        // Tell the dashboard what happened to the email. This server cannot
        // reach FormSubmit itself, so this is the only way a rejected email
        // shows up anywhere.
        fetch(CFG.api + "/api/event", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            kind: mail.ok ? "mail_sent" : "mail_failed",
            detail: mail.ok ? (selectionName || "quote") : mail.why
          })
        }).catch(function () {});

        // Either one reaching us is enough to tell the client it arrived.
        if (res[0] || mail.ok) succeed(payload.selection_link);
        else fail();
      }).then(function () { btn.disabled = false; });
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

  // Currencies: prices arrive in SAR; FX is "1 SAR = x" for each currency
  // the admin enabled in Settings. CURRENCY is what this page shows — the
  // selection's own currency, or the one the client picked.
  var FX = { SAR: 1 };
  var CURRENCY = "SAR";
  function adoptFx(rates) { if (rates && rates.SAR) FX = rates; }
  function inCur(n) {
    var r = FX[CURRENCY];
    if (!r || CURRENCY === "SAR") return n;
    var step = CURRENCY === "USD" ? 5 : CURRENCY === "EGP" ? 50 : 10;
    return Math.round(n * r / step) * step || Math.ceil(n * r);
  }

  // What one creator costs: the price a prepared selection set, else the
  // creator's own rate, else their tier's band.
  function priceOf(code, card) {
    if (CURATED && CURATED.prices[code]) return CURATED.prices[code];
    card = card || document.querySelector('.cat-card[data-code="' + code + '"]');
    if (card && card.dataset.price) {
      var p = card.dataset.price.split("-").map(Number);
      if (p[0]) return [p[0], p[1] || p[0]];
    }
    return card ? TIER_PRICE[card.dataset.tier] : null;
  }
  function priceText(p) {
    if (!p) return "—";
    var a = inCur(p[0]), b = inCur(p[1]);
    return (a === b ? money(a) : money(a) + " – " + money(b)) + " " + CURRENCY;
  }

  // The admin's total applies only while the client is looking at exactly the
  // creators it was set for; remove one and the page adds up what is left.
  function curatedTotal() {
    if (!CURATED || !CURATED.total) return null;
    // A total of 0 is a box left at zero in the dashboard, not a price:
    // showing "0 SAR" would tell the client the shortlist is free.
    if (!(Number(CURATED.total[1]) > 0)) return null;
    if (selected.length !== CURATED.codes.length) return null;
    for (var i = 0; i < selected.length; i++) {
      if (CURATED.codes.indexOf(selected[i]) === -1) return null;
    }
    return CURATED.total;
  }

  function initSelection() {
    var frag = readFragment();
    var token = frag.token;
    // Ask whether this selection has been priced for the client — by token,
    // or, for the link the client made themselves, by its name and creators.
    // Re-pricing then shows on the link the client already has.
    if (CFG.api && !CURATED && (token || frag.codes.length)) {
      var ask = token ? "s=" + encodeURIComponent(token)
        : "n=" + encodeURIComponent(frag.name) + "&c=" + encodeURIComponent(frag.codes.join(","));
      fetch(CFG.api + "/api/selection?" + ask, { credentials: "include" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (b) {
          if (b && b.ok) {
            token = b.token || token;
            adoptFx(b.fx);
            if (b.currency && FX[b.currency]) CURRENCY = b.currency;
            CURATED = { token: token, name: b.name, codes: b.codes || [],
                        prices: b.prices || {}, total: b.total,
                        tags: b.tags || {}, verdicts: b.verdicts || {}, clientTags: b.client_tags || {}, scores: b.scores || {}, brief: b.brief || null, clientPlatforms: b.client_platforms || {},
                        segments: b.segments || {}, groupBy: b.group_by || "",
                        platform: b.platform || "",
                        status: b.status || {}, statusCounts: b.status_counts || null, role: b.role || "viewer",
                        owner: b.owner || "", kam: b.kam || "", credits: b.credits,
                        // 0 while AI is free (active campaign); null only on an old server.
                        replaceCost: b.replace_cost != null ? b.replace_cost : 2, moreCost: b.more_cost != null ? b.more_cost : 3,
                        alikeCost: b.alike_cost != null ? b.alike_cost : 2, aiFree: b.ai_free || null,
                        // No campaign objective yet: nothing is scored, the page asks for it.
                        needsObjective: !!b.needs_objective };
            history.replaceState(null, "", buildFragment(b.name, CURATED.codes));
          }
          withCards(startSelection);
        })
        .catch(function () { withCards(startSelection); });
      return;
    }
    withCards(startSelection);
  }
  // The selection's creators the page does not hold yet (a link that is only a token names
  // none of them up front): fetched by code, then the page starts.
  function withCards(then) {
    var want = readFragment().codes.concat((CURATED && CURATED.codes) || []);
    var have = {};
    all(".cat-card").forEach(function (c) { have[c.dataset.code] = 1; });
    var miss = want.filter(function (c, i) { return !have[c] && want.indexOf(c) === i; });
    if (!CFG.api || !miss.length) { then(); return; }
    fetchCards(miss).then(function (list) { addCards(list); then(); }, function () { then(); });
  }

  function startSelection() {
    var cards = all(".cat-card");
    var byCode = {};
    cards.forEach(function (c) { byCode[c.dataset.code] = c; });

    var frag = readFragment();
    selectionName = frag.name || (CURATED && CURATED.name) || "Selection";
    // A link is now usually just a token, and the creators come back from the
    // service with it. The fragment still wins when it lists them: that is a
    // client who went back to the catalogue and added someone, and their list
    // is newer than the one the token was saved with.
    var want = frag.codes.length ? frag.codes : ((CURATED && CURATED.codes) || []);
    // Keep only codes this build actually knows about — a stale link naming a
    // creator who has since left the roster should drop that card, not break.
    selected = want.filter(function (code) { return !!byCode[code]; });
    var dropped = want.length - selected.length;

    // The same filters and sort as the catalogue, offered over the creators
    // in this selection only. Filtering narrows what is on screen; it does not
    // take anyone out of the selection or change its total.
    var host = document.querySelector(".cat-controls .cat-container");
    var controls = (host && selected.length > 1)
      ? Controls(host, selected.map(function (c) { return byCode[c]; }), function () { render(); }, {
          dims: ["fit", "role", "tag"],
          titles: { fit: "Fit", role: "Role", tag: "Tags" },
          of: function (card, dim) {
            var code = card.dataset.code;
            return dim === "fit" ? (fitOf(code) ? [fitOf(code)] : []) : dim === "role" ? rolesOf(code) : allTagsOf(code);
          },
          values: function (dim) {
            var n = {}, order = [];
            selected.forEach(function (code) {
              (dim === "fit" ? (fitOf(code) ? [fitOf(code)] : []) : dim === "role" ? rolesOf(code) : allTagsOf(code)).forEach(function (v) {
                if (!n[v]) { n[v] = 0; order.push(v); }
                n[v]++;
              });
            });
            var fixed = dim === "fit" ? ["Strong fit", "Good fit", "Possible fit", "Not recommended"]
              : dim === "role" ? ["Awareness", "Engagement", "Conversion", "UGC content"] : null;
            var list = fixed ? fixed.filter(function (v) { return n[v]; })
              : order.sort(function (a, b) { return a.toLowerCase().localeCompare(b.toLowerCase()); });
            return list.map(function (v) { return [v, n[v]]; });
          },
          dot: function (dim, v) { return dim === "fit" ? (FIT_CLASS[v] || "maybe") : ""; },
          score: function (card) { var s = scoreOf(card.dataset.code); return s && s.score != null ? s.score : null; }
        })
      : null;
    if (!controls && host) host.closest(".cat-controls").hidden = true;

    // Group by: the same creators split into sections by one parameter. The
    // admin picks how the page opens; the client can switch or turn it off.
    var GROUP_DIMS = [["", "None"], ["segment", "Segment"], ["tier", "Creator size"], ["platform", "Platform"],
                      ["country", "Country"], ["interest", "Interest"], ["fit", "Fit"], ["role", "Role"], ["tag", "Tags"]];
    var NONE_LABEL = { segment: "No segment", country: "Location not specified", interest: "No interest listed",
                       fit: "Not rated", role: "No role set", tag: "Untagged", platform: "No platform", tier: "No tier" };
    function groupKeys(code, dim) {
      var card = byCode[code], out = [];
      if (!card) return out;
      if (dim === "segment") out = (CURATED && CURATED.segments && CURATED.segments[code]) || [];
      else if (dim === "tier") out = card.dataset.tier ? [card.dataset.tier] : [];
      else if (dim === "platform") out = values(card.dataset.platform);
      else if (dim === "interest") out = values(card.dataset.interest);
      else if (dim === "fit") out = fitOf(code) ? [fitOf(code)] : [];
      else if (dim === "role") out = rolesOf(code);
      else if (dim === "tag") out = allTagsOf(code);
      else if (dim === "status") out = [stLabel(statusOf(code).s)];
      else if (dim === "country") {
        values(card.dataset.city).forEach(function (v) {
          if (/^unspecified$/i.test(v)) return;
          var c = place(v).country;
          if (out.indexOf(c) < 0) out.push(c);
        });
      }
      return out.length ? out : [NONE_LABEL[dim]];
    }
    function groupHas(dim) {
      if (!dim) return true;
      return selected.some(function (code) { return groupKeys(code, dim)[0] !== NONE_LABEL[dim]; });
    }
    var groupKey = "hv-group:" + ((CURATED && CURATED.token) || selectionName);
    var groupBy = (CURATED && CURATED.groupBy) || "";
    try { var gb = sessionStorage.getItem(groupKey); if (gb !== null) groupBy = gb; } catch (e) {}
    if (!groupHas(groupBy)) groupBy = "";
    var groupSel = null;
    if (controls) {
      var row = document.querySelector(".cat-bar__row");
      var sortEl = row && row.querySelector(".cat-sort");
      var opts = GROUP_DIMS.filter(function (d) { return !d[0] || groupHas(d[0]); });
      if (row && opts.length > 1) {
        var lab = document.createElement("label");
        lab.className = "cat-sort cat-group-by";
        lab.innerHTML = '<span class="cat-sort__label">Group</span><select class="cat-sort__select" aria-label="Group creators by">' +
          opts.map(function (d) { return '<option value="' + d[0] + '"' + (d[0] === groupBy ? " selected" : "") + ">" + d[1] + "</option>"; }).join("") +
          "</select>" + CHEVRON + "";
        var order = document.createElement("div");
        order.className = "cat-bar__order";
        if (sortEl) { row.insertBefore(order, sortEl); order.appendChild(lab); order.appendChild(sortEl); }
        else { order.appendChild(lab); row.appendChild(order); }
        groupSel = lab.querySelector("select");
        groupSel.addEventListener("change", function () {
          groupBy = groupSel.value;
          try { sessionStorage.setItem(groupKey, groupBy); } catch (e) {}
          render();
        });
      }
    }
    function groupOrder(dim, names, count) {
      var fixed = dim === "tier" ? Object.keys(TIER_PRICE)
        : dim === "status" ? ST_ORDER.map(function (k) { return ST_LABEL[k]; })
        : dim === "fit" ? ["Strong fit", "Good fit", "Possible fit", "Not recommended"]
        : dim === "country" ? COUNTRY_ORDER : null;
      return names.sort(function (a, b) {
        var na = a === NONE_LABEL[dim], nb = b === NONE_LABEL[dim];
        if (na !== nb) return na ? 1 : -1;
        if (fixed) {
          var ia = fixed.indexOf(a), ib = fixed.indexOf(b);
          if (ia !== ib) return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
        }
        return (count[b] - count[a]) || a.localeCompare(b);
      });
    }
    // Lay the visible cards out in sections. A creator in two groups shows in
    // both (the second is a copy); clicks are handled on the grid, so copies work.
    function layoutGroups(grid, ordered) {
      all(".cat-group", grid).forEach(function (g) { g.remove(); });
      grid.classList.toggle("is-grouped", !!groupBy);
      if (!groupBy) return;
      var members = {}, count = {};
      ordered.forEach(function (card) {
        if (card.hidden) return;
        groupKeys(card.dataset.code, groupBy).forEach(function (k) {
          (members[k] = members[k] || []).push(card);
          count[k] = (count[k] || 0) + 1;
        });
      });
      var placed = {};
      var total = selected.length;
      groupOrder(groupBy, Object.keys(members), count).forEach(function (k) {
        var sec = document.createElement("section");
        sec.className = "cat-group";
        var pct = total ? Math.round(100 * count[k] / total) : 0;
        var flag = groupBy === "country" && k !== NONE_LABEL.country ? flagOf(k) : "";
        var mark = groupBy === "platform" && ICONS[k] ? '<span class="cat-places__mark ' + (BRAND[k] || "") + '">' + ICONS[k] + "</span>" : "";
        if (groupBy === "status") {
          // Under review 4 · Waiting for your yes or no.
          sec.className = "cat-group sel-grp";
          sec.innerHTML = '<header class="sel-grp__hd"><h2>' + esc(k) + '</h2><span class="sel-grp__n">' + count[k] + "</span><p>" +
            esc(ST_SUB[ST_KEY[k]] ? ST_SUB[ST_KEY[k]]() : "") + "</p></header>";
        } else
        sec.innerHTML = '<header class="cat-group__head">' + flag + mark + '<h2 class="cat-group__name">' + esc(k) + "</h2>" +
          '<span class="cat-group__n">' + count[k] + (count[k] === 1 ? " creator" : " creators") + "</span>" +
          '<span class="cat-group__pct">' + pct + "% of the selection</span></header>";
        var inner = document.createElement("div");
        inner.className = "cat-grid cat-group__grid";
        members[k].forEach(function (card) {
          var code = card.dataset.code;
          if (!placed[code]) { placed[code] = true; inner.appendChild(card); }
          else { var cp = card.cloneNode(true); cp.classList.add("cat-card--copy"); cp.removeAttribute("id"); inner.appendChild(cp); }
        });
        sec.appendChild(inner);
        grid.appendChild(sec);
      });
    }

    // Where the creators in this selection are: each country with how many
    // creators, and the cities under it. A creator serving two cities counts
    // in both cities but once in the country. Always the whole selection —
    // the filters narrow the cards, not this.
    // The client can see the shortlist in any currency the admin enabled;
    // their pick is kept for this selection in this browser.
    var curKey = "hv-cur:" + ((CURATED && CURATED.token) || selectionName);
    try { var mine = sessionStorage.getItem(curKey); if (mine && FX[mine]) CURRENCY = mine; } catch (e) {}
    // The header: who it is for, what the brief is, and the numbers at a glance.
    var COUNTRY_NAME = { SA: "Saudi Arabia", AE: "UAE", EG: "Egypt", KW: "Kuwait", QA: "Qatar", BH: "Bahrain", OM: "Oman", JO: "Jordan", LB: "Lebanon", IQ: "Iraq", MA: "Morocco" };
    function renderHead(lo, hi) {
      var br = CURATED && CURATED.brief;
      var cl = $("sel-client");
      if (cl) { cl.hidden = !(br && br.client); cl.textContent = br && br.client ? "Prepared for " + br.client : ""; }
      var bx = $("sel-brief");
      var scored = !!(CURATED && CURATED.scores && Object.keys(CURATED.scores).length);
      if (bx) {
        if (!br && !scored) { bx.hidden = true; }
        else if (!br) { bx.hidden = false; bx.textContent = ""; }
        else {
          var t = br.target || {}, chips = [["Objective", br.objective]];
          if (t.country) chips.push(["Market", COUNTRY_NAME[t.country] || t.country]);
          if (t.gender && t.gender !== "Any") chips.push(["Audience", t.gender]);
          if (t.age && t.age !== "Any") chips.push(["Age", t.age]);
          var cats = String(t.category || "").split("|").filter(function (x) { return x && x !== "Any"; });
          if (cats.length) chips.push(["Category", cats.join(", ")]);
          // The objective leads and is named as the campaign objective; the
          // targeting reads after it as plain facts.
          bx.hidden = false;
          bx.textContent = "";
          chips.forEach(function (c, i) {
            if (!c[1]) return;
            var el = document.createElement("span");
            if (i === 0) {
              el.className = "cat-selhead__obj";
              var k = document.createElement("small"); k.textContent = "Campaign objective";
              var v = document.createElement("strong"); v.textContent = c[1];
              el.appendChild(k); el.appendChild(v);
            } else {
              el.className = "cat-selhead__fact";
              el.title = c[0];
              el.textContent = c[1];
            }
            bx.appendChild(el);
          });
        }
        // What the fit scores on the cards mean, in one quiet line.
        if (scored) {
          var note = document.createElement("span");
          note.className = "cat-selhead__note";
          note.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>';
          note.appendChild(document.createTextNode("Scores compare each creator's profile analysis with your campaign objectives."));
          bx.appendChild(note);
        }
      }
      var st = $("sel-headstats");
      if (!st) return;
      var n = {}, any = false;
      selected.forEach(function (code) { var f = fitOf(code); if (f) { n[f] = (n[f] || 0) + 1; any = true; } });
      var cell = function (label, val, cls) { return '<div class="' + (cls || "") + '"><dt>' + label + "</dt><dd>" + val + "</dd></div>"; };
      var html = cell("Creators", selected.length);
      if (any) {
        html += cell("Strong fit", n["Strong fit"] || 0, "is-strong") + cell("Good fit", n["Good fit"] || 0, "is-good");
        var rest = (n["Possible fit"] || 0) + (n["Not recommended"] || 0);
        if (rest) html += cell("Lower fit", rest, "is-low");
      }
      if (selected.length) html += cell("Indicative range", priceText([lo, hi]), "is-range");
      st.innerHTML = html;
    }
    function renderCurrency() {
      var have = Object.keys(FX);
      var box = $("sel-currency");
      if (have.length < 2) { if (box) box.hidden = true; return; }
      if (!box) {
        box = document.createElement("div");
        box.id = "sel-currency"; box.className = "cat-cur"; box.setAttribute("role", "group");
        box.setAttribute("aria-label", "Currency");
        $("sel-summary").insertAdjacentElement("beforebegin", box);
        box.addEventListener("click", function (e) {
          var b = e.target.closest("button[data-cur]"); if (!b) return;
          CURRENCY = b.getAttribute("data-cur");
          try { sessionStorage.setItem(curKey, CURRENCY); } catch (x) {}
          render();
        });
      }
      box.innerHTML = '<span class="cat-cur__label">Currency</span>' + ["SAR", "AED", "USD", "EGP"].filter(function (c) {
        return FX[c];
      }).map(function (c) {
        return '<button type="button" data-cur="' + c + '" aria-pressed="' + (c === CURRENCY) + '">' + c + "</button>";
      }).join("");
    }

    // The tier mix as one bar: how the shortlist splits by size, at a glance.
    function renderTiers(tiers) {
      var box = $("sel-tiers");
      if (!box) {
        box = document.createElement("div");
        box.id = "sel-tiers";
        box.className = "cat-tiers";
        $("sel-summary").insertAdjacentElement("afterend", box);
      }
      var names = Object.keys(tiers).filter(function (t) { return tiers[t] && t && t !== "undefined"; });
      var total = names.reduce(function (s, t) { return s + tiers[t]; }, 0);
      box.hidden = !total;
      if (!total) { box.innerHTML = ""; return; }
      // One labelled row per tier, creators and HCPs side by side; bars share
      // one scale so a longer bar is always more creators.
      var SIZES = ["nano", "micro", "mid", "macro", "mega"];
      var rank = function (t) {
        var x = t.toLowerCase();
        for (var i = 0; i < SIZES.length; i++) if (x.indexOf(SIZES[i]) > -1) return i;
        return 9;
      };
      var max = Math.max.apply(null, names.map(function (t) { return tiers[t]; }));
      var panel = function (title, list, hcp) {
        if (!list.length) return "";
        var sum = list.reduce(function (s, t) { return s + tiers[t]; }, 0);
        list.sort(function (a, b) { return rank(a) - rank(b); });
        return '<div class="cat-tiers__panel' + (hcp ? " is-hcp" : "") + '"><p class="cat-tiers__title">' + title +
          " <b>" + sum + "</b></p><ul>" + list.map(function (t) {
            var label = t.replace(/^\s*hcp\s*[-–—:]?\s*/i, "");
            var pct = Math.round(100 * tiers[t] / total);
            return '<li class="cat-tier"><span class="cat-tier__name">' + esc(label) + '</span><b class="cat-tier__n">' + tiers[t] +
              '</b><span class="cat-tier__pct">' + pct + '% of selection</span><i class="cat-tier__meter" aria-hidden="true"><i style="width:' +
              Math.max(3, Math.round(100 * tiers[t] / max)) + '%"></i></i></li>';
          }).join("") + "</ul></div>";
      };
      var hcpList = names.filter(function (t) { return /hcp/i.test(t); });
      var plainList = names.filter(function (t) { return !/hcp/i.test(t); });
      box.innerHTML = '<p class="cat-places__label">Creator size</p><div class="cat-tiers__panels">' +
        panel("Influencers", plainList, false) + panel("HCPs", hcpList, true) + "</div>";
    }

    function renderPlaces() {
      var box = $("sel-places");
      if (!box) {
        box = document.createElement("div");
        box.id = "sel-places";
        box.className = "cat-places";
        ($("sel-tiers") || $("sel-summary")).insertAdjacentElement("afterend", box);
      }
      var countries = {}, several = 0, multiCity = 0;
      selected.forEach(function (code) {
        var card = byCode[code];
        if (!card) return;
        var seen = {};
        var cityCount = values(card.dataset.city).filter(function (v) {
          return !/^unspecified$/i.test(v);
        }).length;
        if (cityCount > 1) multiCity++;
        var list = values(card.dataset.city).filter(function (v) { return !/^unspecified$/i.test(v); });
        if (!list.length) list = ["Location not specified"];
        list.forEach(function (v) {
          var p = v === "Location not specified"
            ? { country: "Location not specified", label: "" } : place(v);
          var c = countries[p.country] = countries[p.country] || { n: 0, cities: {} };
          if (!seen[p.country]) { c.n++; seen[p.country] = true; }
          if (p.label) c.cities[p.label] = (c.cities[p.label] || 0) + 1;
        });
        if (Object.keys(seen).length > 1) several++;
      });
      var names = Object.keys(countries).sort(function (a, b) {
        var ia = COUNTRY_ORDER.indexOf(a), ib = COUNTRY_ORDER.indexOf(b);
        var late = function (x) { return x === "Other" || x === "Location not specified"; };
        if (late(a) !== late(b)) return late(a) ? 1 : -1;
        return ((ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)) ||
               (countries[b].n - countries[a].n) || a.localeCompare(b);
      });
      // Creators per platform: a creator on Instagram and TikTok counts on
      // both, so these can add up to more than the selection too.
      var plats = {}, multiPlat = 0;
      selected.forEach(function (code) {
        var card = byCode[code];
        if (!card) return;
        var mine = values(card.dataset.platform);
        if (mine.length > 1) multiPlat++;
        mine.forEach(function (pl) { plats[pl] = (plats[pl] || 0) + 1; });
      });
      var platNames = Object.keys(plats).sort(function (a, b) {
        return (plats[b] - plats[a]) || a.localeCompare(b);
      });
      var platHtml = platNames.length
        ? '<p class="cat-places__label cat-places__label--next">On each platform</p>' +
          '<ul class="cat-places__list cat-places__list--platforms">' +
          platNames.map(function (pl) {
            return '<li><p class="cat-places__country"><span class="cat-places__mark ' +
              (BRAND[pl] || "") + '">' + (ICONS[pl] || ICON_LINK) + "</span><span>" + esc(pl) +
              "</span><b>" + plats[pl] + "</b></p>" +
              '<div class="cat-places__bar">' + shareBar(plats[pl], selected.length) + "</div></li>";
          }).join("") + "</ul>" +
          (multiPlat ? '<p class="cat-places__note">' + multiPlat +
            (multiPlat === 1 ? " creator is" : " creators are") +
            " on more than one platform, so " + (multiPlat === 1 ? "is" : "are") +
            " counted on each.</p>" : "")
        : "";
      box.hidden = !names.length && !platNames.length;
      box.innerHTML = '<p class="cat-places__label">Where they are</p><ul class="cat-places__list">' +
        names.map(function (name) {
          var c = countries[name];
          var cities = Object.keys(c.cities).sort(function (a, b) {
            var na = a === "City not specified", nb = b === "City not specified";
            return (na - nb) || (c.cities[b] - c.cities[a]) || a.localeCompare(b);
          });
          return '<li><p class="cat-places__country">' + flagOf(name) + "<span>" +
            esc(name === "Other" ? "Other locations" : name) + "</span><b>" + c.n + "</b></p>" +
            '<div class="cat-places__bar">' + shareBar(c.n, selected.length) + "</div>" +
            (cities.length ? '<ul class="cat-places__cities">' + cities.map(function (city) {
              return "<li>" + esc(city) + " <b>" + c.cities[city] + "</b></li>";
            }).join("") + "</ul>" : "") + "</li>";
        }).join("") + "</ul>" +
        // Say why the counts add up to more than the selection, when they do.
        ((several || multiCity) ? '<p class="cat-places__note">' +
          (several ? several + (several === 1 ? " creator works" : " creators work") +
            " in more than one country, so " + (several === 1 ? "is" : "are") +
            " counted in each. " : "") +
          (multiCity ? "A creator listed in more than one city is counted in each city." : "") +
          "</p>" : "") + platHtml;
    }

    // What the admin said about each creator of this selection: how well they
    // fit, the part they play, why, and any labels of their own. All of it
    // belongs to the selection, so it shows here and nowhere else.
    var FIT_CLASS = { "Strong fit": "strong", "Good fit": "good", "Possible fit": "maybe", "Not recommended": "no" };
    function tagsOf(code) {
      var t = CURATED && CURATED.tags && CURATED.tags[code];
      return t && t.length ? t : [];
    }
    // Labels the client puts on creators themselves. Kept on the server with the
    // selection when it has a link of its own; otherwise only in this browser.
    var PLAT_KEY = "hv-myplat:" + ((CURATED && CURATED.token) || selectionName);
    var LOCAL_PLAT = {};
    try { LOCAL_PLAT = JSON.parse(localStorage.getItem(PLAT_KEY) || "{}") || {}; } catch (e) { LOCAL_PLAT = {}; }
    var MINE_KEY = "hv-mytags:" + ((CURATED && CURATED.token) || selectionName);
    var LOCAL_MINE = {};
    try { LOCAL_MINE = JSON.parse(localStorage.getItem(MINE_KEY) || "{}") || {}; } catch (e) { LOCAL_MINE = {}; }
    function mineOf(code) {
      var t = CURATED && CURATED.token ? (CURATED.clientTags || {})[code] : LOCAL_MINE[code];
      return t && t.length ? t : [];
    }
    function allTagsOf(code) {
      var out = tagsOf(code).slice();
      mineOf(code).forEach(function (t) {
        if (!out.some(function (x) { return x.toLowerCase() === t.toLowerCase(); })) out.push(t);
      });
      return out;
    }
    function saveMine(code, tags) {
      tags = tags.slice(0, 8);
      if (CURATED && CURATED.token) {
        CURATED.clientTags = CURATED.clientTags || {};
        if (tags.length) CURATED.clientTags[code] = tags; else delete CURATED.clientTags[code];
        fetch(CFG.api + "/api/selection/tags", { method: "POST", credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: CURATED.token, code: code, tags: tags }) })
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (b) { if (b && b.ok) { CURATED.clientTags = b.client_tags || CURATED.clientTags; render(); } })
          .catch(function () { /* the tags stay on screen; they are saved next time */ });
      } else {
        if (tags.length) LOCAL_MINE[code] = tags; else delete LOCAL_MINE[code];
        try { localStorage.setItem(MINE_KEY, JSON.stringify(LOCAL_MINE)); } catch (e) { /* private mode */ }
      }
      render();
    }
    function verdictOf(code) {
      var v = CURATED && CURATED.verdicts && CURATED.verdicts[code];
      return v || null;
    }
    function rolesOf(code) { var v = verdictOf(code); return v && v.roles ? v.roles : []; }
    // The matching score is worked out by the server from the creator's analysis; a fit
    // tag the admin chose by hand wins over the one the score implies.
    function rawScore(code) { return (CURATED && CURATED.scores && CURATED.scores[code]) || null; }
    // The platform to read a creator's score from: the client's own pick, else the admin's
    // assignment, else (none) the best one the server chose.
    function pickOf(code) {
      var mine = CURATED && CURATED.token ? (CURATED.clientPlatforms || {})[code] : LOCAL_PLAT[code];
      if (mine) return mine;
      var s = rawScore(code);
      return s && s.assigned && s.assigned !== "Auto" ? s.assigned : "";
    }
    function withBase(base, x) {
      var o = {}; for (var k in x) o[k] = x[k];
      o.assigned = base.assigned; o.available = base.available; o.platforms = base.platforms;
      return o;
    }
    // "Both": two scores side by side, no combined number.
    function bothOf(code) {
      var base = rawScore(code);
      if (!base || pickOf(code) !== "Both" || !base.platforms) return null;
      var list = Object.keys(base.platforms).sort().map(function (pl) { return withBase(base, base.platforms[pl]); });
      return list.length > 1 ? list : null;
    }
    function scoreOf(code) {
      var base = rawScore(code);
      if (!base) return null;
      var pick = pickOf(code);
      if (pick && pick !== "Both" && base.platforms && base.platforms[pick]) return withBase(base, base.platforms[pick]);
      var both = bothOf(code);
      if (both) return both.reduce(function (a, b) { return (b.score < a.score ? b : a); });   // ranked by the weaker
      return base;
    }
    function savePlatform(code, pl) {
      if (CURATED && CURATED.token) {
        CURATED.clientPlatforms = CURATED.clientPlatforms || {};
        CURATED.clientPlatforms[code] = pl;
        fetch(CFG.api + "/api/selection/platform", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: CURATED.token, code: code, platform: pl }) })
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (b) { if (b && b.ok) CURATED.clientPlatforms = b.client_platforms || CURATED.clientPlatforms; })
          .catch(function () { /* stays on screen */ });
      } else {
        LOCAL_PLAT[code] = pl;
        try { localStorage.setItem(PLAT_KEY, JSON.stringify(LOCAL_PLAT)); } catch (e) { /* private mode */ }
      }
      render();
    }
    var PLAT_SHORT = { Instagram: "IG", TikTok: "TT", Snapchat: "SC", YouTube: "YT" };
    function fitOf(code) {
      var v = verdictOf(code), s = scoreOf(code);
      return (v && v.fit) ? v.fit : (s && s.score != null ? s.tag : "");
    }
    // The stamp on the photo: the score, coloured by band; hover or focus explains it.
    var tip = null;
    function bandOf(n) { return n >= 80 ? "g" : n >= 60 ? "l" : n >= 40 ? "a" : "r"; }
    // No audience report: the audience part of the score is an assumption.
    function audienceEstimated(sc) {
      return !!(sc && (sc.parts || []).some(function (p) { return /assumed|estimated/i.test(p.label) && /audience/i.test(p.label); }));
    }
    function showTip(el, sc) {
      if (!tip) { tip = document.createElement("div"); tip.className = "cat-score-tip"; tip.setAttribute("role", "tooltip"); document.body.appendChild(tip); }
      var bars = (sc.parts || []).map(function (p) {
        return '<div class="cst-bar"><span>' + esc(p.label) + '</span><i><b class="' + bandOf(p.s * 100) + '" style="width:' + Math.round(p.s * 100) + '%"></b></i></div>';
      }).join("");
      tip.innerHTML = '<div class="cst-head"><b class="' + bandOf(sc.score) + '">' + sc.score + '%</b><div><strong>' + esc(sc.tag) +
        '</strong><small>' + (sc.basic ? "Screening score · " : "") + 'Match for ' + esc((sc.objective || "").toLowerCase()) + (sc.platform ? " · on " + esc(sc.platform) : "") + "</small>" +
        (audienceEstimated(sc) ? "<small>Audience estimated: no audience report yet, so it counts lightly</small>" : "") +
        (sc.others && sc.others.length ? "<small>Also: " + sc.others.map(function (o) { return esc(o.platform) + " " + o.score; }).join(", ") + "</small>" : "") + "</div></div>" +
        (sc.strengths && sc.strengths.length ? '<p class="cst-h">Strengths</p><ul class="cst-g">' + sc.strengths.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>" : "") +
        (sc.watchouts && sc.watchouts.length ? '<p class="cst-h">Watch-outs</p><ul class="cst-w">' + sc.watchouts.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>" : "") +
        '<p class="cst-h">How it adds up</p>' + bars +
        (sc.checks && sc.checks.length ? '<p class="cst-h">Verified by the full analysis</p><ul class="cst-c">' + sc.checks.map(function (c) {
          return '<li class="' + esc(c.level) + '">' + esc(c.text) + "</li>"; }).join("") + "</ul>" : "") +
        (sc.basic ? '<p class="cst-basic' + (sc.score >= 60 ? " cst-basic--warn" : "") + '"><b>Screening score, not proof.</b> It uses public numbers only, so fake followers and the real audience are not checked. Request the full analysis before booking.</p>' : "");
      tip.hidden = false;
      var r = el.getBoundingClientRect(), tw = Math.min(320, window.innerWidth - 24);
      tip.style.width = tw + "px";
      var left = Math.max(12, Math.min(r.left, window.innerWidth - tw - 12));
      tip.style.left = left + "px";
      // Below the stamp when it fits, else above it, else pinned inside the window.
      var th = tip.offsetHeight, room = window.innerHeight - 12;
      var top = r.bottom + 10;
      if (top + th > room) top = r.top - th - 10;
      if (top < 8) top = Math.max(8, room - th);
      tip.style.top = top + "px";
      tip.style.bottom = "auto";
    }
    function hideTip() { if (tip) tip.hidden = true; }
    function stampItem(code, i) { var both = bothOf(code); return both ? both[i] : scoreOf(code); }
    function renderStamp(card, sc) {
      var media = card.querySelector(".cat-card__media");
      if (!media) return;
      var code = card.dataset.code;
      var list = bothOf(code) || (sc ? [sc] : []);
      var have = [].slice.call(media.querySelectorAll(".cat-score"));
      for (var k = list.length; k < have.length; k++) have[k].remove();
      list.forEach(function (item, i) {
        var st = have[i];
        if (!st) {
          st = document.createElement("button");
          st.type = "button"; st.className = "cat-score"; st.setAttribute("data-noselect", ""); st.setAttribute("data-i", i);
          media.appendChild(st);
          st.addEventListener("mouseenter", function () { var s = stampItem(code, i); if (s && s.score != null) showTip(st, s); });
          st.addEventListener("focus", function () { var s = stampItem(code, i); if (s && s.score != null) showTip(st, s); });
          st.addEventListener("mouseleave", hideTip);
          st.addEventListener("blur", hideTip);
          st.addEventListener("click", function (e) {
            e.preventDefault(); e.stopPropagation();
            var s = stampItem(code, i);
            if (s && s.score != null) { if (tip && !tip.hidden) hideTip(); else showTip(st, s); }
          });
        }
        var multi = list.length > 1;
        if (item.score == null) {
          st.className = "cat-score cat-score--none";
          st.innerHTML = "<b>—</b><small>Not scored</small>";
          st.setAttribute("aria-label", "Not scored yet: not enough analysis data");
          st.title = "Not scored yet — the full analysis is needed.";
        } else {
          st.className = "cat-score cat-score--" + bandOf(item.score) + (item.basic ? " cat-score--basic" : "") + (multi ? " cat-score--multi" : "");
          st.innerHTML = "<b>" + item.score + '<i class="cat-score__pct">%</i></b><small>' + (multi ? (PLAT_SHORT[item.platform] || item.platform) : (item.basic ? "Basic" : "Match")) + "</small>" +
            "";
          st.setAttribute("aria-label", item.score + "% match on " + (item.platform || "the platform") + ", " + item.tag + ". Show why.");
          st.removeAttribute("title");
        }
      });
    }
    // The platform switch on a card: which platform to read this creator's match from.
    function renderPlat(card) {
      var base = rawScore(card.dataset.code), body = card.querySelector(".cat-card__body");
      var box = card.querySelector(".cat-plat");
      var have = base && base.platforms ? Object.keys(base.platforms).sort() : [];
      if (!body || have.length < 2) { if (box) box.remove(); return; }
      var shown = pickOf(card.dataset.code) || scoreOf(card.dataset.code).platform;
      if (!box) {
        box = document.createElement("div");
        box.className = "cat-plat"; box.setAttribute("data-noselect", ""); box.setAttribute("role", "group");
        box.setAttribute("aria-label", "Platform this creator is scored on");
        body.insertBefore(box, body.firstChild);
      }
      box.innerHTML = '<span class="cat-plat__label">Score on</span>' + have.concat(["Both"]).map(function (pl) {
        return '<button type="button" data-plat="' + esc(pl) + '" aria-pressed="' + (pl === shown) + '"' + (mayEdit() ? "" : ' disabled title="Only the selection’s owner can change this"') + ">" + esc(pl) + "</button>";
      }).join("");
    }
    window.addEventListener("scroll", hideTip, { passive: true });

    // A tag keeps the same colour wherever it appears: one of six, chosen from its letters.
    function tone(t) {
      var h = 0; t = String(t).toLowerCase();
      for (var i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) % 6;
      return h;
    }
    // Colleagues on the same company see a selection but never change it: tags, the "score on"
    // platform and the objective belong to its owner (and HelloVoice). Unsaved local lists are theirs.
    function mayEdit() { return !(CURATED && CURATED.token) || CURATED.role === "owner" || CURATED.role === "admin"; }
    function renderTags() {
      var back = (CURATED && CURATED.platform) ? "&p=" + encodeURIComponent(CURATED.platform) : "";
      selCards().forEach(function (c) {
        var body = c.querySelector(".cat-card__body");
        if (!body) return;
        var link = c.querySelector("a.cat-card__analysis");
        if (link && back && link.href.indexOf("&p=") === -1) link.href = link.href + back;
        var v = verdictOf(c.dataset.code), mine = tagsOf(c.dataset.code);
        var sc = scoreOf(c.dataset.code), fitNow = fitOf(c.dataset.code);
        var why = (v && v.reason) || "";     // the generated conclusion is in the hover on the stamp
        renderStamp(c, sc);
        renderPlat(c);
        renderStatus(c);
        var box = c.querySelector(".cat-verdict");
        if (!fitNow && !(v && (v.roles || []).length) && !why) { if (box) box.remove(); }
        else {
          if (!box) {
            box = document.createElement("div");
            box.className = "cat-verdict";
            body.insertBefore(box, body.firstChild);
          }
          box.innerHTML = '<div class="cat-verdict__chips">' +
            (fitNow ? '<span class="cat-fit cat-fit--' + (FIT_CLASS[fitNow] || "maybe") + '">' + esc(fitNow) + "</span>" : "") +
            ((v && v.roles) || []).map(function (r) { return '<span class="cat-role">' + esc(r) + "</span>"; }).join("") + "</div>" +
            (why ? '<p class="cat-verdict__why">' + esc(why) + "</p>" : "");
        }
        var tbox = c.querySelector(".cat-tags");
        var mt = mineOf(c.dataset.code);
        var typing = c.querySelector(".cat-tags__in");
        // One strip: the admin's labels, then the client's own (removable), then the add button.
        if (!tbox) {
          tbox = document.createElement("div");
          tbox.className = "cat-tags";
          tbox.setAttribute("data-noselect", "");
          var lk = c.querySelector("a.cat-card__analysis");
          if (lk) lk.insertAdjacentElement("beforebegin", tbox); else body.appendChild(tbox);
        }
        if (!typing) {
          tbox.innerHTML = '<span class="cat-tags__label">Tags</span>' + mine.map(function (t) {
            return '<span class="cat-tag cat-tag--t' + tone(t) + '"><i></i>' + esc(t) + "</span>";
          }).join("") + mt.map(function (t) {
            return '<span class="cat-tag cat-tag--mine cat-tag--t' + tone(t) + '"><i></i>' + esc(t) + (mayEdit() ? '<button type="button" data-tag-x="' + esc(t) +
              '" aria-label="Remove tag ' + esc(t) + '">&times;</button>' : "") + "</span>";
          }).join("") + (mt.length < 8 && mayEdit() ? '<button type="button" class="cat-tag cat-tag--add" data-tag-add>+ Tag</button>' : "");
        }
      });
      if (controls) controls.refresh();
    }

    /* ---- selection status (HELVY Connect v3) ----------------------------
       Every creator is Under review until the selection's owner approves or
       rejects them; HelloVoice can set any status, and only HelloVoice marks a
       creator Unavailable. Colleagues see the same statuses and cannot change
       them. The summary bar's chips filter the cards; "Group by status" lays
       them out in the four groups. */
    var ST_ORDER = ["review", "approved", "rejected", "unavailable"];
    var ST_LABEL = { review: "Under review", approved: "Approved", rejected: "Rejected", unavailable: "Unavailable" };
    var ST_KEY = { "Under review": "review", "Approved": "approved", "Rejected": "rejected", "Unavailable": "unavailable" };
    var ST_SIG = { review: "wait", approved: "ok", rejected: "no", unavailable: "off" };
    var REASONS = [["price", "Price"], ["audience", "Audience"], ["style", "Content style"], ["competitor", "Worked with a competitor"], ["other", "Other"]];
    var ST_ICON = { review: "clock", approved: "check", rejected: "x", unavailable: "ban" };
    var justRejected = {};           // codes rejected in this visit: their "?" pulses once
    function reasonText(st) {
      if (!st || !st.reason) return "";
      var lab = (REASONS.filter(function (r) { return r[0] === st.reason; })[0] || ["", ""])[1];
      return st.reason === "other" ? (st.note || "Other") : lab + (st.note ? " · " + st.note : "");
    }
    // The credit cost, one look everywhere: an orange chip with a coin (or "Free").
    function costChip(cost) {
      return cost ? '<span class="hv-cost">' + hvIcon("coin") + cost + " credit" + (cost === 1 ? "" : "s") + "</span>"
                  : '<span class="hv-cost hv-cost--free">Free</span>';
    }
    var ROLE = (CURATED && CURATED.role) || "viewer";
    var KAM = (CURATED && CURATED.kam) || "";
    var ST_SUB = {
      review: function () { return ROLE === "owner" ? "Waiting for your yes or no." : "Waiting for " + ((CURATED && CURATED.owner) ? CURATED.owner.split(" ")[0] : "the owner") + "'s yes or no."; },
      approved: function () { return "These go to " + (KAM ? KAM.split(" ")[0] : "HelloVoice") + " for the quote."; },
      rejected: function () { return ROLE === "owner" ? "Tell Helvy why and it finds a better fit." : "Left out of the quote."; },
      unavailable: function () { return "Set by HelloVoice when a creator can't take the job."; }
    };
    var STATUS_ON = !!(CURATED && CURATED.token && CFG.api && CURATED.status);
    var stFilter = "";               // "", a status, "influencers" or "doctors"
    function stLabel(k) { return { review: "Under review", approved: "Approved", rejected: "Rejected", unavailable: "Unavailable" }[k] || k; }
    function hvIcon(n) { return window.hvPortal && window.hvPortal.icon ? window.hvPortal.icon(n) : ""; }
    function statusOf(code) { return (STATUS_ON && CURATED.status[code]) || { s: "review", by: "", hv: false, at: null, reason: "", note: "", replacements: [] }; }
    function isDoctor(code) { var c = byCode[code]; return !!(c && /^hcp/i.test(c.dataset.tier || "")); }
    function stDay(ts) {
      if (!ts) return "";
      var d = new Date(ts * 1000), s = Date.now() / 1000 - ts;
      if (s < 120) return "just now";
      return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" }) + (s < 86400 * 2 ? ", " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }) : "");
    }
    function stCounts() {
      var n = { creators: selected.length, influencers: 0, doctors: 0, review: 0, approved: 0, rejected: 0, unavailable: 0 };
      selected.forEach(function (code) { n[statusOf(code).s]++; n[isDoctor(code) ? "doctors" : "influencers"]++; });
      return n;
    }
    function stMatches(code) {
      if (!stFilter) return true;
      if (stFilter === "doctors") return isDoctor(code);
      if (stFilter === "influencers") return !isDoctor(code);
      return statusOf(code).s === stFilter;
    }
    // A decision shows at once (fix batch 3): the card is redrawn before the server answers, and
    // put back if the save fails. Before, every Approve / Reject / Undo waited a full round trip
    // to the server (Riyadh -> the server and back) before anything moved.
    function stSave(code, body, then) {
      body.token = CURATED.token; body.code = code;
      var prev = CURATED.status[code], optimistic = body.status !== undefined;
      if (optimistic) {
        var was = statusOf(code);
        CURATED.status[code] = { s: body.status, by: was.by && was.s === body.status ? was.by : "You", hv: ROLE === "admin", at: Math.floor(Date.now() / 1000),
                                 reason: body.status === "rejected" ? was.reason || "" : "", note: "", replacements: was.replacements || [] };
        if (then) then({ ok: true, status: CURATED.status[code], pending: true });
        render();
      }
      var undo = function (text) {
        if (optimistic) { if (prev === undefined) delete CURATED.status[code]; else CURATED.status[code] = prev; render(); }
        stToast(text);
      };
      return fetch(CFG.api + (body.reason !== undefined && body.status === undefined ? "/api/selection/reason" : "/api/selection/status"),
        { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
        .then(function (r) { return r.json().catch(function () { return {}; }); })
        .then(function (b) {
          if (b && b.ok) {
            var keepRepl = (CURATED.status[code] || {}).replacements;
            CURATED.status[code] = b.status;
            if (keepRepl && keepRepl.length && !(b.status.replacements || []).length) b.status.replacements = keepRepl;
            if (then && !optimistic) then(b);
            render();
          } else undo((b && b.message) || "That didn't save. Please try again.");
        })
        .catch(function () { undo("Couldn't reach the server. Please try again."); });
    }
    var toastEl = null;
    function stToast(text) {
      if (!toastEl) { toastEl = document.createElement("div"); toastEl.className = "sel-toast"; toastEl.setAttribute("role", "status"); document.body.appendChild(toastEl); }
      toastEl.textContent = text; toastEl.hidden = false;
      clearTimeout(toastEl._t); toastEl._t = setTimeout(function () { toastEl.hidden = true; }, 4200);
    }
    function whoLine(st) {
      if (!st.at) return st.s === "review" ? (ROLE === "owner" ? "Your call." : "Not decided yet.") : "";
      var by = st.hv ? "<b>" + esc(st.by || "HelloVoice") + "</b> · HelloVoice" : "<b>" + esc(st.by || "Client") + "</b>";
      var lead = st.s === "review" ? "Set back by " : st.s === "unavailable" ? "Marked by " : "by ";
      return lead + by + " · " + esc(stDay(st.at)) + (st.s === "review" && st.note ? " · " + esc(st.note) : "");
    }
    function replButton(code, st) {
      var have = (st.replacements || []).length;
      var cost = CURATED && CURATED.replaceCost != null ? CURATED.replaceCost : 2;
      if (have) return '<button type="button" class="sel-repl sel-repl--ink" data-st-repl="' + esc(code) + '">' + hvIcon("swap") + " See " + have + " replacement" + (have === 1 ? "" : "s") + " from Helvy</button>";
      var helvy = window.hvPortal && window.hvPortal.helvy ? '<img src="' + esc(window.hvPortal.helvy) + '" alt="" aria-hidden="true">' : "";
      // A compact one-line pill: Helvy's face, the action, the cost inline.
      return '<button type="button" class="sel-repl" data-st-repl="' + esc(code) + '" aria-label="Find a replacement with Helvy, ' + (cost ? cost + " credits" : "free") + '">' +
        helvy + "<span>Find a replacement</span>" + costChip(cost) + "</button>";
    }
    /* -- why a creator was rejected: a "?" beside the status, a small pop-up to answer -- */
    var whyTip = null, whyPop = null, whyBack = null;
    function placeFloat(el, anchor, gap) {
      var r = anchor.getBoundingClientRect(), w = el.offsetWidth, hgt = el.offsetHeight;
      var left = Math.max(10, Math.min(r.left + r.width / 2 - w / 2, window.innerWidth - w - 10));
      var top = r.bottom + gap;
      if (top + hgt > window.innerHeight - 10) top = Math.max(10, r.top - hgt - gap);
      el.style.left = left + "px"; el.style.top = top + "px";
    }
    function showWhyTip(q, code) {
      var st = statusOf(code), txt = reasonText(st);
      if (!txt && !(ROLE === "owner" || ROLE === "admin")) return;
      if (whyPop) return;
      if (!whyTip) { whyTip = document.createElement("div"); whyTip.className = "sel-whytip"; whyTip.setAttribute("role", "tooltip"); whyTip.id = "sel-whytip"; document.body.appendChild(whyTip); }
      whyTip.innerHTML = txt ? "<b>Why rejected</b>" + esc(txt) : "<b>Why rejected?</b>Add a reason (optional). It helps Helvy suggest better.";
      whyTip.hidden = false;
      q.setAttribute("aria-describedby", "sel-whytip");
      placeFloat(whyTip, q, 8);
    }
    function hideWhyTip() { if (whyTip) whyTip.hidden = true; }
    function closeWhyPop(back) {
      if (!whyPop) return;
      whyPop.remove(); whyPop = null;
      document.removeEventListener("keydown", whyKey, true);
      document.removeEventListener("mousedown", whyOut, true);
      window.removeEventListener("scroll", whyScroll, true);
      if (back && whyBack && whyBack.isConnected) whyBack.focus();
    }
    function whyKey(e) { if (e.key === "Escape") { e.preventDefault(); closeWhyPop(true); } }
    function whyOut(e) { if (whyPop && !whyPop.contains(e.target) && !(e.target.closest && e.target.closest("[data-st-whyq]"))) closeWhyPop(false); }
    function whyScroll(e) { if (whyPop && !whyPop.contains(e.target)) closeWhyPop(false); }
    function openWhyPop(q, code) {
      closeWhyPop(false);
      whyBack = q;
      var st = statusOf(code), pick = st.reason || "";
      var card = byCode[code], nm = card && card.querySelector(".cat-card__name");
      var pop = document.createElement("div");
      pop.className = "sel-whypop"; pop.setAttribute("role", "dialog"); pop.setAttribute("aria-labelledby", "sel-whypop-t");
      pop.innerHTML = '<p class="sel-whypop__t" id="sel-whypop-t">Why not ' + esc(nm ? nm.textContent.trim() : code) + "?</p>" +
        '<p class="sel-whypop__s">Optional. It helps Helvy suggest better.</p>' +
        '<div class="sel-whypop__chips" role="group" aria-label="Reason">' + REASONS.map(function (r) {
          return '<button type="button" aria-pressed="' + (pick === r[0]) + '" data-why="' + r[0] + '">' + esc(r[1]) + "</button>";
        }).join("") + "</div>" +
        '<input class="sel-whypop__other" type="text" maxlength="200" placeholder="In a few words" aria-label="The reason, in a few words"' + (pick === "other" ? "" : " hidden") + ' value="' + esc(pick === "other" ? st.note || "" : "") + '">' +
        '<div class="sel-whypop__ft"><button type="button" class="sel-whypop__skip">Skip</button><button type="button" class="sel-whypop__save"' + (pick ? "" : " disabled") + ">Save</button></div>";
      document.body.appendChild(pop);
      whyPop = pop;
      var other = pop.querySelector(".sel-whypop__other"), save = pop.querySelector(".sel-whypop__save");
      pop.addEventListener("click", function (e) {
        var b = e.target.closest("button");
        if (!b) return;
        if (b.hasAttribute("data-why")) {
          pick = b.getAttribute("data-why");
          [].forEach.call(pop.querySelectorAll("[data-why]"), function (x) { x.setAttribute("aria-pressed", String(x === b)); });
          other.hidden = pick !== "other"; save.disabled = false;
          if (pick === "other") other.focus();
          placeFloat(pop, q, 8);
        } else if (b.classList.contains("sel-whypop__skip")) {
          delete justRejected[code]; closeWhyPop(true); render();
        } else if (b === save && pick) {
          save.disabled = true;
          stSave(code, { reason: pick, note: pick === "other" ? other.value.replace(/\s+/g, " ").trim() : "" }, function () {
            delete justRejected[code];
            stToast("Thanks. Helvy will remember that.");
          });
          closeWhyPop(false);
          setTimeout(function () { var nq = document.querySelector('[data-st-whyq="' + code + '"]'); if (nq) nq.focus(); }, 60);
        }
      });
      other.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); save.click(); } });
      placeFloat(pop, q, 8);
      document.addEventListener("keydown", whyKey, true);
      document.addEventListener("mousedown", whyOut, true);
      window.addEventListener("scroll", whyScroll, true);
      var first = pop.querySelector('[aria-pressed="true"]') || pop.querySelector("[data-why]");
      if (first) first.focus();
    }
    function renderStatus(card) {
      var body = card.querySelector(".cat-card__body");
      if (!body) return;
      var box = card.querySelector(".sel-st");
      if (!STATUS_ON) { if (box) box.remove(); return; }
      var code = card.dataset.code, st = statusOf(code);
      if (!box) { box = document.createElement("div"); box.className = "sel-st"; box.setAttribute("data-noselect", ""); body.appendChild(box); }
      card.classList.toggle("is-no", st.s === "rejected");
      card.classList.toggle("is-off", st.s === "unavailable");
      var canDecide = ROLE === "owner" || ROLE === "admin";
      var why = st.s === "rejected" && (canDecide || st.reason) ? '<button type="button" class="sel-whyq' + (st.reason ? " has-reason" : "") + (justRejected[code] ? " is-new" : "") +
          '" data-st-whyq="' + esc(code) + '" aria-haspopup="dialog" aria-label="' + esc(reasonText(st) ? "Why rejected: " + reasonText(st) : "Add a reason (optional)") + '">?</button>' : "";
      var html = '<div class="sel-st__line"><span class="sel-sig sel-sig--' + ST_SIG[st.s] + '">' + hvIcon(ST_ICON[st.s]) + ST_LABEL[st.s] + "</span>" + why +
        (canDecide && st.s !== "review" && (st.s !== "unavailable" || ROLE === "admin") ? '<button type="button" class="sel-st__change" data-st-set="review" data-st-code="' + esc(code) + '">' + (st.s === "rejected" ? "Undo" : "Change") + "</button>" : "") +
        "</div>";
      var who = whoLine(st);
      if (who) html += '<p class="sel-st__by">' + who + "</p>";
      if (st.s === "unavailable" && st.note) html += '<p class="sel-offnote">' + esc(st.note) + "</p>";
      if (canDecide && st.s === "review") {
        html += '<div class="sel-st__acts"><button type="button" class="sel-dec sel-dec--yes" data-st-set="approved" data-st-code="' + esc(code) + '">' + hvIcon("check") + " Approve</button>" +
          '<button type="button" class="sel-dec sel-dec--no" data-st-set="rejected" data-st-code="' + esc(code) + '">' + hvIcon("x") + " Reject</button></div>";
        if (ROLE === "admin") html += '<button type="button" class="sel-st__change sel-st__off" data-st-set="unavailable" data-st-code="' + esc(code) + '">Mark unavailable (HelloVoice)</button>';
      }
      // Find a replacement opens Helvy's side panel (connect.js), like Creators like this.
      if (canDecide && (st.s === "rejected" || st.s === "unavailable")) html += replButton(code, st);
      // "Creators like this" (Helvy look-alikes): on every card the owner has not turned down.
      if (canDecide && st.s !== "rejected" && st.s !== "unavailable") {
        var ac = CURATED.alikeCost != null ? CURATED.alikeCost : 2;
        html += '<button type="button" class="sel-alike" data-alike="' + esc(code) + '" title="' + (ac ? "Helvy finds 3 creators like this one · " + ac + " credits" : "Free with your active campaign") + '">' +
          hvIcon("spark") + "<span>Creators like this</span></button>";
      }
      // Phase E: Helvy's content ideas for this creator (hooks and concepts, AR + EN), for anyone who can open the selection.
      if (st.s !== "rejected" && st.s !== "unavailable") {
        html += '<button type="button" class="sel-ideas" data-ideas="' + esc(code) + '" title="Helvy drafts hooks and concepts for this creator, in English and Arabic">' +
          hvIcon("bulb") + "<span>Content ideas</span></button>";
      }
      box.innerHTML = html;
    }
    // The selection's campaign objective, in one bar above the creators. Without one nothing is
    // scored (the server sends no scores) and the bar asks for it: Helvy's objective studio
    // (portal.js) scores THIS selection only, it never builds a new shortlist. With one, the bar
    // shrinks to a done line (Objective added ✓ · Awareness, Engagement · Edit).
    function objectiveWords(o) { return String(o || "").split("+").filter(Boolean).join(", "); }
    function renderObjective() {
      var host = $("sel-objective");
      var need = !!(CURATED && CURATED.needsObjective && selected.length);
      var have = !!(CURATED && !CURATED.needsObjective && CURATED.brief && CURATED.brief.objective && CURATED.token && selected.length);
      if (!need && !have) { if (host) host.remove(); return; }
      if (!host) {
        host = document.createElement("section");
        host.id = "sel-objective"; host.setAttribute("aria-label", "Campaign objective");
        var anchor = document.querySelector(".cat-grid-section");
        anchor.parentNode.insertBefore(host, anchor);
        host.addEventListener("click", function (e) {
          var go = e.target.closest(".sel-obj__go, .sel-obj__edit");
          if (!go) return;
          if (window.hvPortal && window.hvPortal.scoreBrief) window.hvPortal.scoreBrief(CURATED.token, { edit: go.classList.contains("sel-obj__edit") });
        });
      }
      var canAct = ROLE === "owner" || ROLE === "admin";
      host.className = "sel-obj" + (have ? " sel-obj--done" : "");
      if (have) {
        host.innerHTML = '<div class="cat-pad"><div class="cat-container sel-obj__in"><span class="sel-obj__ic sel-obj__ic--done">' + hvIcon("check") + "</span>" +
          '<p class="sel-obj__tx"><b>Objective added</b><span class="sel-obj__what">' + esc(objectiveWords(CURATED.brief.objective)) + "</span>" +
          '<span class="sel-obj__note">Each creator here is scored for it.</span></p>' +
          (canAct ? '<button type="button" class="sel-obj__edit">Edit</button>' : "") + "</div></div>";
        return;
      }
      host.innerHTML = '<div class="cat-pad"><div class="cat-container sel-obj__in"><span class="sel-obj__ic">' + hvIcon("target") + "</span>" +
        '<p class="sel-obj__tx"><b>Add your campaign objective to score these creators</b>' +
        "<span>" + (canAct ? "Six quick questions. Helvy scores the creators already in this selection: it doesn’t build a new shortlist or change who is in it. Free."
                           : "Scores appear once the selection’s owner adds the campaign objective.") + "</span></p>" +
        (canAct ? '<button type="button" class="sel-obj__go">Add objective' + hvIcon("arrow") + "</button>" : "") + "</div></div>";
    }
    function renderStatusBar() {
      var host = $("sel-statusbar");
      if (!STATUS_ON || !selected.length) { if (host) host.hidden = true; return; }
      if (!host) {
        host = document.createElement("section");
        host.id = "sel-statusbar"; host.className = "sel-sbar"; host.setAttribute("aria-label", "Creators by status");
        var anchor = document.querySelector(".cat-grid-section");
        anchor.parentNode.insertBefore(host, anchor);
        host.addEventListener("click", function (e) {
          var b = e.target.closest("[data-st-filter]");
          if (b) { var v = b.getAttribute("data-st-filter"); stFilter = stFilter === v ? "" : v; render(); return; }
          var g = e.target.closest("[data-st-group]");
          if (g) {
            groupBy = groupBy === "status" ? "" : "status";
            try { sessionStorage.setItem(groupKey, groupBy); } catch (x) {}
            if (groupSel) groupSel.value = groupBy === "status" ? "" : groupBy;
            render();
          }
        });
      }
      host.hidden = false;
      var n = stCounts();
      var chip = function (key, label, ico, all) {
        if (!all && !n[key] && key !== "approved" && key !== "review") return "";
        return '<button type="button" class="sel-chip' + (all ? " sel-chip--all" : "") + (ico ? " sel-chip--" + key : "") + '" aria-pressed="' + (all ? !stFilter : stFilter === key) + '" data-st-filter="' + (all ? "" : key) + '">' +
          (ico ? '<span class="sel-ci">' + hvIcon(ico) + "</span>" : "") + label + "</button>";
      };
      var kinds = (n.doctors && n.influencers) ? chip("influencers", n.influencers + " influencer" + (n.influencers === 1 ? "" : "s"), "user") + chip("doctors", n.doctors + " doctor" + (n.doctors === 1 ? "" : "s"), "steth") : "";
      host.innerHTML = '<div class="cat-pad"><div class="cat-container sel-sbar__in"><div class="sel-sum" role="group" aria-label="Show">' +
        chip("", n.creators + " creator" + (n.creators === 1 ? "" : "s"), null, true) + kinds +
        '<span class="sel-sum__sep" aria-hidden="true"></span>' +
        chip("approved", n.approved + " approved", "check") + chip("rejected", n.rejected + " rejected", "x") +
        chip("review", n.review + " under review", "clock") + chip("unavailable", n.unavailable + " unavailable", "ban") +
        '</div><div class="sel-sbar__tools"><button type="button" class="sel-swrow" data-st-group role="switch" aria-checked="' + (groupBy === "status") + '"><span class="sel-sw" aria-hidden="true"></span>Group by status</button></div></div></div>';
    }
    // HELVY Connect phase D (assets/js/connect.js): the ROI Calculator, "Add more like these"
    // and "Creators like this" read the selection through this small hook and add creators
    // the same way the replacement's Add button does.
    window.hvSelection = {
      token: function () { return CURATED && CURATED.token; },
      name: function () { return (CURATED && CURATED.name) || ""; },
      role: function () { return ROLE; },
      curated: function () { return CURATED; },
      codes: function () { return selected.slice(); },
      status: function (code) { return statusOf(code); },
      creator: function (code) {
        var c = byCode[code]; if (!c) return null;
        var nm = c.querySelector(".cat-card__name");
        return { code: code, name: nm ? nm.textContent.trim() : code, tier: c.dataset.tier || "", doctor: isDoctor(code) };
      },
      // Creators the page does not hold yet are fetched by code first (the page holds only
      // the selection's own cards); the answer is how many were taken in.
      add: function (codes) {
        var want = (codes || []).filter(function (c, i, a) { return c && selected.indexOf(c) === -1 && a.indexOf(c) === i; });
        if (!want.length) return 0;
        withCodes(want, function () {
          var n = 0;
          want.forEach(function (c) { if (byCode[c] && selected.indexOf(c) === -1) { selected.push(c); n++; } });
          if (n) { render(); saveShortlist(); }
          if (n < want.length) stToast(want.length - n === 1 ? "One creator isn't in the catalogue right now." : (want.length - n) + " creators aren't in the catalogue right now.");
        });
        return want.length;
      },
      toast: function (t) { stToast(t); },
      rerender: function () { render(); },
      // After the objective studio: the selection's scores, objective and statuses again, then
      // one redraw of its cards (no page reload).
      refresh: function () {
        if (!CURATED || !CURATED.token) return Promise.resolve();
        return fetch(CFG.api + "/api/selection?s=" + encodeURIComponent(CURATED.token), { credentials: "include", cache: "no-store" })
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (b) {
            if (!b || !b.ok) return;
            CURATED.scores = b.scores || {}; CURATED.brief = b.brief || null; CURATED.verdicts = b.verdicts || CURATED.verdicts;
            CURATED.needsObjective = !!b.needs_objective;
            if (b.status) CURATED.status = b.status;
            render();
          })
          .catch(function () { /* the old view stays */ });
      }
    };
    try { document.dispatchEvent(new CustomEvent("hv:selection")); } catch (e) { /* old browser */ }
    if (STATUS_ON) {
      // A selection that has statuses opens grouped by them, unless the client chose otherwise.
      var gbStored = null;
      try { gbStored = sessionStorage.getItem(groupKey); } catch (e) {}
      if (gbStored === null && !(CURATED && CURATED.groupBy)) groupBy = "status";
    }
    $("cat-grid").addEventListener("click", function (e) {
      var t = e.target.closest && e.target.closest("[data-st-set], [data-st-whyq], [data-st-repl], [data-st-add]");
      if (!t || !STATUS_ON) return;
      e.preventDefault(); e.stopPropagation();
      var code = t.getAttribute("data-st-code") || t.getAttribute("data-st-whyq") || t.getAttribute("data-st-repl");
      if (t.hasAttribute("data-st-set")) {
        var to = t.getAttribute("data-st-set");
        t.disabled = true;
        stSave(code, { status: to }, function () {
          if (to === "rejected") justRejected[code] = true; else delete justRejected[code];
        });
      } else if (t.hasAttribute("data-st-whyq")) {
        hideWhyTip();
        if (ROLE === "owner" || ROLE === "admin") openWhyPop(t, code); else showWhyTip(t, code);
      } else if (t.hasAttribute("data-st-repl")) {
        if (!(window.hvPortal && window.hvPortal.replaceSheet)) { stToast("Helvy couldn't look just now."); return; }
        window.hvPortal.replaceSheet(code, function (list) {
          var st = statusOf(code);
          st.replacements = (list || []).map(function (c) { return c.code; });
          CURATED.status[code] = st;
          render();
        });
      } else if (t.hasAttribute("data-st-add")) {
        var add = t.getAttribute("data-st-add");
        withCodes([add], function () {
          if (byCode[add] && selected.indexOf(add) === -1) {
            selected.push(add);
            render(); saveShortlist();
            stToast("Added to this selection, under review.");
          } else if (!byCode[add]) stToast("That creator isn't in the catalogue right now.");
        });
      }
    }, true);
    // The saved reason reads on hover or focus of the "?"; the card itself stays compact.
    $("cat-grid").addEventListener("mouseover", function (e) {
      var q = e.target.closest && e.target.closest("[data-st-whyq]");
      if (q) showWhyTip(q, q.getAttribute("data-st-whyq"));
    });
    $("cat-grid").addEventListener("mouseout", function (e) {
      var q = e.target.closest && e.target.closest("[data-st-whyq]");
      if (q && !q.contains(e.relatedTarget)) hideWhyTip();
    });
    $("cat-grid").addEventListener("focusin", function (e) {
      var q = e.target.closest && e.target.closest("[data-st-whyq]");
      if (q) showWhyTip(q, q.getAttribute("data-st-whyq"));
    });
    $("cat-grid").addEventListener("focusout", function (e) {
      if (e.target.closest && e.target.closest("[data-st-whyq]")) hideWhyTip();
    });

    $("cat-grid").addEventListener("click", function (e) {
      var pb = e.target.closest && e.target.closest("[data-plat]");
      if (pb) {
        e.preventDefault(); e.stopPropagation();
        if (!mayEdit()) return;
        savePlatform(pb.closest(".cat-card").dataset.code, pb.getAttribute("data-plat"));
        return;
      }
      var card = e.target.closest && e.target.closest(".cat-card");
      if (!card) return;
      var code = card.dataset.code;
      var x = e.target.closest("[data-tag-x]");
      if (x) {
        e.preventDefault(); e.stopPropagation();
        var gone = x.getAttribute("data-tag-x");
        saveMine(code, mineOf(code).filter(function (t) { return t !== gone; }));
        return;
      }
      if (e.target.closest("[data-tag-add]")) {
        e.preventDefault(); e.stopPropagation();
        var box = card.querySelector(".cat-tags");
        box.querySelector("[data-tag-add]").remove();
        var inp = document.createElement("input");
        inp.type = "text"; inp.className = "cat-tags__in"; inp.maxLength = 24;
        inp.placeholder = "Type a tag, press Enter"; inp.setAttribute("aria-label", "New tag");
        box.appendChild(inp);
        // Tags already used anywhere in this selection, one click to reuse.
        var have = allTagsOf(code).map(function (t) { return t.toLowerCase(); });
        var pool = {};
        selected.forEach(function (c2) { allTagsOf(c2).forEach(function (t) { if (have.indexOf(t.toLowerCase()) < 0) pool[t.toLowerCase()] = pool[t.toLowerCase()] || t; }); });
        var picks = Object.keys(pool).map(function (k) { return pool[k]; }).sort(function (x, y) { return x.localeCompare(y); }).slice(0, 14);
        var pickBox = null;
        if (picks.length) {
          pickBox = document.createElement("div");
          pickBox.className = "cat-tags__picks";
          pickBox.innerHTML = '<span>Reuse:</span>' + picks.map(function (t) {
            return '<button type="button" class="cat-tag cat-tag--t' + tone(t) + '" data-tag-pick="' + esc(t) + '"><i></i>' + esc(t) + "</button>";
          }).join("");
          pickBox.addEventListener("mousedown", function (ev) {
            var b = ev.target.closest("[data-tag-pick]");
            if (!b) return;
            ev.preventDefault(); ev.stopPropagation();
            inp.value = b.getAttribute("data-tag-pick");
            commit(true);
          });
          pickBox.addEventListener("click", function (ev) { ev.stopPropagation(); });
          box.appendChild(pickBox);
        }
        inp.focus();
        var done = false;
        function commit(keep) {
          if (done) return; done = true;
          var v = inp.value.replace(/[<>]/g, "").replace(/\s+/g, " ").trim();
          inp.remove();
          if (pickBox) pickBox.remove();
          if (keep && v && !allTagsOf(code).some(function (t) { return t.toLowerCase() === v.toLowerCase(); })) {
            saveMine(code, mineOf(code).concat([v]));
          } else render();
        }
        inp.addEventListener("keydown", function (ev) {
          if (ev.key === "Enter") { ev.preventDefault(); commit(true); }
          else if (ev.key === "Escape") { commit(false); }
        });
        inp.addEventListener("blur", function () { commit(true); });
      }
    }, true);

    // Only the selection's own cards are on the page (fix batch 3). The page used to keep every
    // roster card in the grid, hidden, and every render (each Approve, Reject, tag, add) walked,
    // restyled and re-appended all ~2,000 of them: 150-190 ms of main-thread work per click on a
    // fast laptop. Cards outside the selection now wait off the page until they are added.
    // A creator's card, fetched by code when the page does not hold it (an add from a replacement,
    // "Creators like this", "Add more like these"): it joins `cards` and `byCode` like the others.
    function withCodes(codes, then) {
      var miss = codes.filter(function (c) { return !byCode[c]; });
      if (!miss.length || !CFG.api) { then(); return; }
      fetchCards(miss).then(function (list) {
        addCards(list).forEach(function (el) { cards.push(el); byCode[el.dataset.code] = el; });
        then();
      }, function () { then(); });
    }
    function selCards() { return selected.map(function (code) { return byCode[code]; }).filter(Boolean); }
    function render() {
      if (window.hvGateQuote) window.hvGateQuote();
      var grid = $("cat-grid");
      var keep = {};
      selected.forEach(function (code) { keep[code] = 1; });
      cards.forEach(function (c) { if (!keep[c.dataset.code] && c.parentNode) c.parentNode.removeChild(c); });
      var inOrder = selCards();
      inOrder.forEach(addRemove);
      renderTags();
      var shown = 0;
      inOrder.forEach(function (c) {
        var ok = (!controls || controls.matches(c)) && stMatches(c.dataset.code);
        c.hidden = !ok;
        if (ok) shown++;
      });

      // Order the visible cards the way the link lists them, or by the sort
      // the client picked.
      var ordered = controls ? controls.order(inOrder) : inOrder;
      inOrder.forEach(function (card) { grid.appendChild(card); });   // back out of any sections first
      ordered.forEach(function (card) { grid.appendChild(card); });
      layoutGroups(grid, ordered);

      $("sel-title").textContent = selectionName;
      document.title = selectionName + " — HELVY Connect";
      $("cat-empty").textContent = selected.length
        ? (stFilter ? "No creators in this selection are " + (ST_LABEL[stFilter] || stFilter).toLowerCase() + " right now." : "No creators in this selection match those filters.")
        : "This link does not name any creators.";
      $("cat-empty").hidden = shown !== 0;

      // summary: count, per-tier split, indicative total range
      var tiers = {}, lo = 0, hi = 0;
      selected.forEach(function (code) {
        var t = byCode[code].dataset.tier;
        tiers[t] = (tiers[t] || 0) + 1;
        var p = priceOf(code, byCode[code]);
        if (p) { lo += p[0]; hi += p[1]; }
      });
      var fixed = curatedTotal();
      if (fixed) { lo = fixed[0]; hi = fixed[1]; }
      var rows = [
        ["Creators", String(selected.length)],
        ["Indicative range", selected.length ? priceText([lo, hi]) : "—"]
      ];
      if (CURATED && CURATED.platform) rows.splice(1, 0, ["Quoted for", CURATED.platform]);
      if (dropped) rows.push(["Not in this roster", String(dropped)]);
      $("sel-summary").innerHTML = rows.map(function (r) {
        return '<div class="cat-stat' + (r[0] === "Indicative range" ? " cat-stat--range" : "") + '"><dt>' +
          '<span class="cat-stat__icon">' + (STAT_ICONS[r[0]] || "") + "</span>" + r[0] + "</dt><dd>" + r[1] + "</dd></div>";
      }).join("");
      renderTiers(tiers);
      renderPlaces();
      renderCurrency();
      renderHead(lo, hi);
      renderStatusBar();
      renderObjective();

      // keep the URL in step so what they see is what they can re-share
      // The short link only while the server holds exactly these creators.
      var saved = CURATED && CURATED.codes &&
        CURATED.codes.slice().sort().join() === selected.slice().sort().join();
      var want = buildFragment(selectionName, selected, !saved);
      if (location.hash !== want) history.replaceState(null, "", want);
      // The link back into the catalogue carries the codes, not just the
      // token: it has to arrive with these creators already picked, and the
      // long form says so without another round trip. Sharing uses `want`.
      var carrying = buildFragment(selectionName, selected, true);
      all(".cat-back, .cat-tray__edit, .cat-close__actions a.cat-btn--ghost[href*='#']").forEach(function (a) {
        if (a.href.indexOf("#") > -1) a.href = a.href.split("#")[0] + carrying;
      });

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

    // Prices are quoted for the shortlist as a whole, never per creator: a
    // client reading a price against each face compares them against each
    // other. Only the range in the summary is shown, and a total typed in the
    // dashboard replaces it there.

    // Removing a creator saves the shortlist on the server, so the short link
    // (#s=<token>) opens exactly what is on screen — before this a copied
    // link quietly reopened the original list. Until the save comes back, and
    // if it fails, the link carries the creators itself (#n=…&c=…&s=…), which
    // the page also reads, so no copy of the link is ever stale.
    var saving = null;
    function saveShortlist() {
      history.replaceState(null, "", buildFragment(selectionName, selected, true));
      clearTimeout(saving);
      saving = setTimeout(function () {
        var codes = selected.slice();
        register(selectionName, codes, (CURATED && CURATED.token) || CARRIED_TOKEN)
          .then(function (token) {
            if (!token || codes.join() !== selected.join()) return;
            if (!CURATED) CURATED = { prices: {}, platform: "" };
            CURATED.token = token;
            CURATED.name = selectionName;
            // The server drops a total typed for the old list; so does the page.
            if (CURATED.codes && CURATED.codes.slice().sort().join() !== codes.slice().sort().join()) {
              CURATED.total = null;
            }
            CURATED.codes = codes;
            history.replaceState(null, "", buildFragment(selectionName, selected));
          });
      }, 400);
    }

    // A remove control per card, added here rather than in the markup so the
    // catalogue and the selection page can share one card template. Added when
    // a card joins the page (render), not to every roster card up front.
    function addRemove(card) {
      if (card.getAttribute("data-rm")) return;
      card.setAttribute("data-rm", "1");
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cat-card__remove";
      btn.setAttribute("data-noselect", "");
      btn.setAttribute("aria-label", "Remove " + card.dataset.code + " from this selection");
      btn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M5 5l14 14M19 5L5 19"/></svg>';
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var i = selected.indexOf(card.dataset.code);
        if (i !== -1) { selected.splice(i, 1); render(); saveShortlist(); }
      });
      card.querySelector(".cat-card__media").appendChild(btn);
      // cards are not togglable here — the selection is the content
      card.removeAttribute("tabindex");
      card.removeAttribute("role");
      card.removeAttribute("aria-pressed");
    }

    // Back to the catalogue carrying this shortlist, so a client who forgot
    // someone can add them and save the same selection again.
    var carry = buildFragment(selectionName, selected, true);
    all(".cat-back, .cat-tray__edit, .cat-close__actions a[href='../'], .cat-close__actions a[href='/']")
      .forEach(function (a) {
        a.href = new URL("../", location.href).href + carry;
        if (a.classList.contains("cat-btn")) a.textContent = "Add more creators";
      });

    // A colleague on the same company can view a selection but not ask for its quote: that is the
    // owner's call (the server checks it too). Local, unsaved lists are always the sender's own.
    function gateQuote() {
      if (!(CURATED && CURATED.token) || mayEdit()) return;
      ["cat-request", "cat-request-2", "sel-head-quote"].forEach(function (id) { var b = $(id); if (b) b.hidden = true; });
    }
    window.hvGateQuote = gateQuote;
    wireQuoteForm(function () { selected = []; render(); });
    gateQuote();
    var second = $("cat-request-2");
    if (second) second.addEventListener("click", function () { $("cat-request").click(); });
    var hq = $("sel-head-quote"); if (hq) hq.addEventListener("click", function () { $("cat-request").click(); });
    var hc = $("sel-head-copy");
    if (hc) hc.addEventListener("click", function () {
      copyText(location.href, function () { hc.textContent = "Link copied"; setTimeout(function () { hc.textContent = "Copy link"; }, 2200); },
        function () { hc.textContent = "Copy failed"; setTimeout(function () { hc.textContent = "Copy link"; }, 2200); });
    });

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
      // Moving between a prepared selection and any other link changes where
      // the prices come from; start the page over rather than patch the cards.
      if ((f.token || "") !== (CURATED ? CURATED.token : "")) { location.reload(); return; }
      selectionName = f.name || "Selection";
      selected = f.codes.filter(function (c) { return !!byCode[c]; });
      render();
    });
    render();
    // The selection's cards are drawn: the page is ready. Without this the loader waited for
    // every request on the page (account, licences, the bell) to go quiet, and on a slow line
    // its cover came up over a page that was already there.
    if (window.hvLoader) window.hvLoader.done();
  }

  /* ------------------------------------------- the roster, from the service */

  // Fix batch 3, item 16: the page never downloads the whole roster any more. The catalogue
  // asks for its filter options and its first 48 cards (admin/paging.py does the filtering,
  // sorting and grouping); the selection page asks only for its own creators, by code. Either
  // answer is also the "is this browser in?" check /api/roster used to be.
  var FEED = null;
  function firstParams() {
    var p = new URLSearchParams(), g = "";
    p.set("link", LINK);
    p.set("sort", "followers-desc");
    try { g = sessionStorage.getItem("hv-group:catalogue") || ""; } catch (e) { /* blocked */ }
    if (g) p.set("group", g);
    return p;
  }
  function viewWaiting() {
    try { var k = JSON.parse(sessionStorage.getItem("hv-cat-view") || "null"); return !!(k && Date.now() - k.t < 30 * 60 * 1000); } catch (e) { return false; }
  }
  function apiJson(path, p) {
    return fetch(CFG.api + path + "?" + p.toString(), { credentials: "include" })
      .then(function (r) { return r.ok ? r.json() : { ok: false, status: r.status }; });
  }
  // The named creators that are on the roster, in that order (at most 200 a call).
  function fetchCards(codes) {
    var list = (codes || []).filter(Boolean), out = [], calls = [];
    for (var i = 0; i < list.length; i += 200) {
      var p = new URLSearchParams();
      p.set("link", LINK);
      p.set("codes", list.slice(i, i + 200).join(","));
      calls.push(apiJson("/api/roster/cards", p));
    }
    return Promise.all(calls).then(function (all_) {
      all_.forEach(function (b) { if (b && b.ok) out = out.concat(b.cards || []); });
      return out;
    });
  }
  // Cards fetched by code, added to the selection page's grid (hidden: render() shows them).
  function addCards(list) {
    var grid = $("cat-grid"), have = {}, made = [];
    if (!grid) return made;
    all(".cat-card", grid).forEach(function (c) { have[c.dataset.code] = 1; });
    var html = list.filter(function (c) { return !have[c.code] && (have[c.code] = 1); })
      .map(function (c, i) { return cardMarkup(c, i).replace("<article ", "<article hidden "); }).join("");
    var box = document.createElement("div");
    box.innerHTML = html;
    while (box.firstChild) { made.push(box.firstChild); grid.appendChild(box.firstChild); }
    return made;
  }
  function bootApi(fromGate) {
    var settle = function () { document.body.classList.remove("cat-checking"); };
    var refused = function () { settle(); forget(); if (!fromGate) hideShell(); };
    dropRoster();
    if (!fromGate) {
      // A browser that has been in before sees the page shell at once; a new one sees nothing
      // until the server answers (never the gate flashing up).
      if (wasUnlocked || viewWaiting()) showShell(); else document.body.classList.add("cat-checking");
    }
    if (PAGE === "catalogue") {
      var fp = firstParams(), lp = new URLSearchParams();
      lp.set("link", LINK);
      // Back on this tab with a view kept: its own batches load in initApp, so only the options
      // (and the pass check that comes with them) are asked for here.
      var skipFirst = viewWaiting() && !/[#&](c|s)=/.test(location.hash || "");
      if (skipFirst) fp.set("limit", "1");
      Promise.all([apiJson("/api/roster/page", fp), apiJson("/api/roster/facets", lp)]).then(function (res) {
        settle();
        var a = res[0], f = res[1];
        if (!a || !a.ok || !f || !f.ok) { refused(); return; }
        if (skipFirst) fp.delete("limit");
        FEED = { first: skipFirst ? null : a, key: skipFirst ? "" : fp.toString(), facets: f.facets || {} };
        adoptTiers(a.tiers); adoptFx(a.fx); remember(); unlock();
      }).catch(function () { settle(); if (!fromGate) hideShell(); });
      return;
    }
    // The selection page: the creators its link names now; the rest of the selection (a link that
    // is only a token) once /api/selection has answered (initSelection).
    var lp2 = new URLSearchParams();
    lp2.set("link", LINK);
    lp2.set("codes", readFragment().codes.slice(0, 200).join(","));
    apiJson("/api/roster/cards", lp2).then(function (b) {
      settle();
      if (!b || !b.ok) { refused(); return; }
      ROSTER = b.cards || [];
      adoptTiers(b.tiers); adoptFx(b.fx); remember(); unlock();
    }).catch(function () { settle(); if (!fromGate) hideShell(); });
  }

  /* --------------------------------------------------------- deterrence */

  ["contextmenu", "dragstart", "selectstart", "copy", "cut"].forEach(function (evt) {
    document.addEventListener(evt, function (e) {
      if (e.target.closest && e.target.closest(".cat-form, .cat-gate__form, .cat-range, .cat-search, [data-noselect]")) return;
      e.preventDefault();
    });
  });

  document.addEventListener("keydown", function (e) {
    var k = (e.key || "").toLowerCase();
    var mod = e.ctrlKey || e.metaKey;
    if (mod && ["s", "p", "u", "c", "x", "a"].indexOf(k) !== -1) {
      if (e.target.closest && e.target.closest(".cat-form, .cat-gate__form, .cat-range, .cat-search")) return;
      e.preventDefault();
    }
    if (k === "f12") e.preventDefault();
    if (mod && e.shiftKey && ["i", "j", "c"].indexOf(k) !== -1) e.preventDefault();
  });

  // Frost the page when the window loses focus — makes over-the-shoulder
  // screen capture from a second app noticeably harder to do cleanly.
  // Focus moving into the profile-analysis panel is not leaving the page;
  // the panel frosts this page itself when the window really loses focus.
  window.addEventListener("blur", function () {
    setTimeout(function () {
      var f = document.activeElement;
      if (f && f.classList && f.classList.contains("cat-pp__frame")) return;
      document.body.classList.add("cat-away");
    }, 0);
  });
  window.addEventListener("focus", function () { document.body.classList.remove("cat-away"); });

  // Last thing in the file, deliberately — see the note by `wasUnlocked`.
  if (CFG.api) {
    // Ask the server whether this browser is already in, every time — not
    // only when the page's own "unlocked" cookie survives. That one ends
    // when the browser closes, while the server's pass lasts 12 hours, so a
    // client coming back or hopping to the selection page was asked for a
    // code the server would have accepted anyway. The server still decides:
    // a revoked or expired code lands back on the gate.
    //
    // While asking, the gate form is hidden (cat-checking), so nobody sees
    // an access-code screen flash up on every page change.
    bootApi(false);
  } else if (wasUnlocked) {
    unlock();
  }

  /* ------------------------------------------- profile analysis side panel */

  // The card's analysis button opens the creator's page in a panel over the
  // roster, so the client keeps their place and their picks. Ctrl/cmd-click
  // or a middle click still opens it as a page of its own.
  (function () {
    var panel = null, frame = null, title = null, full = null, lastFocus = null;
    function build() {
      var wrap = document.createElement("div");
      wrap.innerHTML = '<div class="cat-pp-scrim" hidden></div>' +
        '<aside class="cat-pp" role="dialog" aria-modal="true" aria-labelledby="cat-pp-title" hidden>' +
        '<header class="cat-pp__head"><p class="cat-pp__eyebrow">Profile analysis</p><h2 id="cat-pp-title"></h2>' +
        '<button type="button" class="cat-pp__pick" aria-pressed="false"></button>' +
        '<a class="cat-pp__full" target="_blank" rel="noopener">Open as page <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17L17 7M9 7h8v8"/></svg></a>' +
        '<button type="button" class="cat-pp__close" aria-label="Close"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M5 5l14 14M19 5L5 19"/></svg></button></header>' +
        '<iframe class="cat-pp__frame" title="Creator profile analysis"></iframe></aside>';
      while (wrap.firstChild) document.body.appendChild(wrap.firstChild);
      panel = document.querySelector(".cat-pp"); frame = panel.querySelector("iframe");
      title = $("cat-pp-title"); full = panel.querySelector(".cat-pp__full");
      panel.querySelector(".cat-pp__close").addEventListener("click", close);
      // Add to / remove from the selection without leaving the panel: it
      // presses the creator's own card, so the tray stays the one source.
      panel.querySelector(".cat-pp__pick").addEventListener("click", function () {
        var card = document.querySelector('.cat-card[data-code="' + panel.getAttribute("data-code") + '"]');
        if (card) { card.click(); pick(); }
      });
      document.querySelector(".cat-pp-scrim").addEventListener("click", close);
      document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !panel.hidden) close(); });
    }
    function pick() {
      var b = panel.querySelector(".cat-pp__pick");
      var card = document.querySelector('.cat-card[data-code="' + panel.getAttribute("data-code") + '"]');
      b.hidden = !card;
      var on = !!card && card.getAttribute("aria-pressed") === "true";
      b.setAttribute("aria-pressed", on ? "true" : "false");
      b.textContent = on ? "✓ In your selection" : "+ Add to selection";
    }
    function open(a) {
      if (!panel) build();
      lastFocus = a;
      panel.setAttribute("data-code", a.getAttribute("data-analysis"));
      pick();
      var href = a.getAttribute("href"), url = href.replace("creator/#", "creator/?embed=1#");
      title.textContent = a.getAttribute("data-name") || "";
      full.href = href;
      frame.src = url;
      document.querySelector(".cat-pp-scrim").hidden = false; panel.hidden = false;
      document.documentElement.classList.add("cat-pp-open");
      panel.querySelector(".cat-pp__close").focus();
    }
    function close() {
      panel.hidden = true; document.querySelector(".cat-pp-scrim").hidden = true;
      document.documentElement.classList.remove("cat-pp-open");
      frame.src = "about:blank";
      if (lastFocus) lastFocus.focus();
    }
    document.addEventListener("click", function (e) {
      var a = e.target.closest && e.target.closest("a[data-analysis]");
      if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
      e.preventDefault(); e.stopPropagation();
      open(a);
    }, true);
  })();
})();

/* Cover header: the poster is the first paint. The 720p reel gets its source only once the
   app is on screen and the browser is idle, and never on a phone, on Save-Data or under
   reduced motion (the poster stays). It pauses whenever it scrolls out of view. */
(function () {
  var v = document.querySelector('.cat-cover__video');
  var still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)');
  var conn = navigator.connection || {};
  var small = window.matchMedia && window.matchMedia('(max-width: 767px), (pointer: coarse)').matches;
  var posterOnly = (still && still.matches) || conn.saveData || /(^|-)2g$/.test(conn.effectiveType || '') || small;
  if (v && !posterOnly) {
    var started = false;
    var play = function () { var p = v.play(); if (p && p.catch) p.catch(function () {}); };
    var start = function () {
      if (started) return;
      started = true;
      if (!v.getAttribute('src') && v.getAttribute('data-src')) { v.preload = 'auto'; v.src = v.getAttribute('data-src'); }
      play();
      if ('IntersectionObserver' in window) new IntersectionObserver(function (en) {
        if (en[0].isIntersecting) play(); else v.pause();
      }).observe(v);
    };
    var later = function () {
      // after the first frame of the app, then when the main thread is free
      requestAnimationFrame(function () { setTimeout(function () {
        if (window.requestIdleCallback) requestIdleCallback(start, { timeout: 2500 }); else setTimeout(start, 400);
      }, 0); });
    };
    var app = document.getElementById('cat-app');
    if (app && !app.hidden) later();
    else if (app && window.MutationObserver) {
      var mo = new MutationObserver(function () { if (!app.hidden) { mo.disconnect(); later(); } });
      mo.observe(app, { attributes: true, attributeFilter: ['hidden'] });
    }
  }
  var cue = document.querySelector('.cat-cover__cue');
  if (cue) cue.addEventListener('click', function (ev) {
    var to = document.getElementById('cat-roster');
    if (!to) return;
    ev.preventDefault();
    to.scrollIntoView({ behavior: still && still.matches ? 'auto' : 'smooth', block: 'start' });
  });
})();

/* The showreel starts only once the creator grid is drawn, so its download
   does not compete with the roster and the first photos. Reduced motion keeps
   the poster. */
(function () {
  var v = document.querySelector('.cat-showreel__video'), grid = document.getElementById('cat-grid');
  if (!v || (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches)) return;
  var started = false;
  function go() {
    if (started || !grid || !grid.children.length) return;
    started = true;
    setTimeout(function () { var p = v.play(); if (p && p.catch) p.catch(function () {}); }, 600);
  }
  if (grid && window.MutationObserver) new MutationObserver(go).observe(grid, { childList: true });
  go();
})();

/* The roster count and Group / Sort sit at the end of the filter row: one
   compact toolbar. The count is the headline number ("2,137 creators", or
   "128 of 2,137" while filtered); Group and Sort read as plain text menus. */
(function () {
  function fmt(n) { return Number(n).toLocaleString("en-US"); }
  function count(grid, num, of, lab) {
    var paged = window.hvCatalogue && window.hvCatalogue.server;
    if (paged) {
      // Served in batches: the server says how many match, and only while a filter or a search is on.
      var m = window.hvCatalogue.matched();
      num.parentNode.hidden = m == null;
      num.textContent = fmt(m || 0);
      of.textContent = ""; of.hidden = true;
      lab.textContent = m === 1 ? "creator matches" : "creators match";
      return;
    }
    // What is actually on screen: the catalogue's own filters hide cards with
    // [hidden], the licence filter and the AI shortlist with classes.
    // Read from classes, not getComputedStyle: 2,000+ style reads on every grid change was a
    // forced style recalculation each time.
    var cards = grid.querySelectorAll(".cat-card:not(.cat-card--copy)"), n = 0, ai = grid.classList.contains("ai-on");
    for (var i = 0; i < cards.length; i++) {
      var c = cards[i];
      if (!c.hidden && !c.classList.contains("lic-out") && !(ai && c.classList.contains("ai-out"))) n++;
    }
    // The size of the roster is never shown (Bido, 2026-10-08): only how many a filter leaves,
    // and nothing at all while nothing is filtered.
    var tally = num.parentNode, filtered = n < cards.length;
    tally.hidden = !filtered;
    num.textContent = fmt(n);
    of.textContent = ""; of.hidden = true;
    lab.textContent = n === 1 ? "creator matches" : "creators match";
  }
  function mount() {
    var row = document.querySelector(".cat-bar__row");
    var grid = document.getElementById("cat-grid");
    var order = document.querySelector(".cat-bar__order") || (row && row.querySelector(".cat-sort"));
    if (!row || !grid || !order || document.querySelector(".cat-tally")) return false;
    var side = document.createElement("div");
    side.className = "cat-bar__side";
    var tally = document.createElement("p");
    tally.className = "cat-tally";
    tally.setAttribute("aria-live", "polite");
    var num = document.createElement("b"), of = document.createElement("span"), lab = document.createElement("small");
    of.className = "cat-tally__of";
    tally.appendChild(num); tally.appendChild(of); tally.appendChild(lab);
    side.appendChild(tally);
    side.appendChild(order);
    row.appendChild(side);
    count(grid, num, of, lab);
    var t = null;
    new MutationObserver(function () { clearTimeout(t); t = setTimeout(function () { count(grid, num, of, lab); }, 180); })
      .observe(grid, { subtree: true, childList: true, attributes: true, attributeFilter: ["hidden", "class"] });
    return true;
  }
  if (mount()) return;
  var tries = 0, mo = new MutationObserver(function () { if (mount() || ++tries > 400) mo.disconnect(); });
  mo.observe(document.body, { childList: true, subtree: true });
})();
