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
  function all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }

  // Mirrors simple_hash() in the Python builder (djb2-xor, 32-bit).
  function hash(s) {
    var h = 5381;
    for (var i = 0; i < s.length; i++) h = (Math.imul(h, 33) ^ s.charCodeAt(i)) >>> 0;
    return ("0000000" + h.toString(16)).slice(-8);
  }

  /* ---------------------------------------------------------------- gate */

  function unlock() {
    document.body.classList.remove("cat-locked");
    $("cat-gate").remove();
    var app = $("cat-app");
    app.hidden = false;
    initApp();
  }

  var gateForm = $("cat-gate-form");
  gateForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var val = $("cat-code").value.trim();
    if (hash(val) === CFG.passHash) {
      try { sessionStorage.setItem("cat-ok", "1"); } catch (err) { /* private mode */ }
      unlock();
    } else {
      var err = $("cat-gate-error");
      err.hidden = false;
      $("cat-code").value = "";
      $("cat-code").focus();
    }
  });

  // Survive a refresh within the same tab, not across sessions. The actual
  // unlock happens at the very bottom of this file: everything it reaches for
  // must already be assigned, and `var` hoists the declaration but not the
  // value. Unlocking here silently broke the selection page on any revisit.
  var wasUnlocked = false;
  try { wasUnlocked = sessionStorage.getItem("cat-ok") === "1"; } catch (e) { /* private mode */ }

  /* ------------------------------------------------------------- the app */

  function initApp() {
    if (PAGE === "selection") { initSelection(); return; }
    var grid = $("cat-grid");
    var cards = all(".cat-card");
    // Derived from whatever chips the builder rendered, so adding a filter
    // dimension is a builder change alone — this stays correct untouched.
    var filters = {};
    all(".cat-chip").forEach(function (c) { filters[c.dataset.filter] = ""; });

    /* -- filtering -- */

    function apply() {
      var shown = 0;
      cards.forEach(function (card) {
        var ok = Object.keys(filters).every(function (k) {
          return !filters[k] || card.dataset[k] === filters[k];
        });
        card.hidden = !ok;
        if (ok) shown++;
      });
      $("cat-count").textContent = shown + (shown === 1 ? " creator" : " creators");
      $("cat-empty").hidden = shown !== 0;
    }

    all(".cat-chip").forEach(function (chip) {
      chip.addEventListener("click", function () {
        var name = chip.dataset.filter;
        filters[name] = chip.dataset.value;
        all('.cat-chip[data-filter="' + name + '"]').forEach(function (c) {
          var active = c === chip;
          c.classList.toggle("is-active", active);
          c.setAttribute("aria-pressed", active ? "true" : "false");
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

    wireQuoteForm(function () {
      selected = [];
      cards.forEach(function (c) { c.setAttribute("aria-pressed", "false"); });
      renderTray();
    });

    /* -- name a selection and share it -- */

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

    $("cat-request").addEventListener("click", openModal);
    $("cat-modal-close").addEventListener("click", closeModal);
    modal.addEventListener("click", function (e) { if (e.target === modal) closeModal(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !modal.hidden) closeModal();
    });

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

      // FormSubmit renders top-level keys as rows in the email, so the payload
      // is flat and human-readable rather than a nested JSON blob. The
      // selection is spelled out — a list of bare codes would mean cross-
      // referencing the private key by hand for every enquiry.
      var lines = selected.map(function (code) {
        var card = document.querySelector('.cat-card[data-code="' + code + '"]');
        if (!card) return code;
        var nameEl = card.querySelector(".cat-card__name");
        var who = nameEl ? " — " + nameEl.textContent.trim() : "";
        return code + who + "  (" + card.dataset.platform + ", " +
               card.dataset.tier + ", " + card.dataset.city + ")";
      });

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
        creators_selected: selected.length,
        selection: lines.join("\n"),
        submitted_at: new Date().toISOString(),
        catalogue: "HelloVoice Creator Roster"
      };

      btn.disabled = true;
      status.className = "cat-form__status";
      status.textContent = "Sending…";

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
          status.className = "cat-form__status is-ok";
          status.textContent = "Sent. We will come back to you with a full quote.";
          e.target.reset();
          setTimeout(function () {
            closeModal();
            if (typeof onCleared === "function") onCleared();
            status.textContent = "";
          }, 2200);
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

  // Tier price ranges, mirrored from TIERS in the Python builder so the page
  // can total a selection without another data file.
  var TIER_PRICE = {
    "Nano":     [435, 870],
    "Micro":    [870, 1740],
    "Mid-Tier": [1450, 2900],
    "Macro":    [2175, 4350]
  };

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
  if (wasUnlocked) unlock();
})();
