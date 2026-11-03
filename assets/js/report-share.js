/* Client report links (item 291, Bido 2026-11-03).
   Loaded first on the four report pages: Track dashboard, selection, creator analysis, competitor study.

   Opened through a client link (#…&r=<token>): the page is that one report and nothing else. Every request
   to the portal carries the token, the portal's own chrome (account dock, Helvy, app bar, edit mode, sign-in
   gate) never mounts, links into the portal do nothing, and a bar says who it is for, when the data was read
   and when the link ends, with Download PDF.

   Opened by HelloVoice (owner/admin, or the account's KAM): a "Share with client" button beside the page's
   own actions makes, copies and revokes links for this report (/api/report/shares).

   Pages register their PDF with HVReport.pdf = function () {…}; without one, Download PDF prints the page.
   Every PDF carries "Data as of" (HVReport.asOf()). */
(function () {
  "use strict";
  var API = (window.CAMPAIGN_CONFIG || window.CREATOR_CONFIG || window.CATALOGUE_CONFIG || {}).api || "/admin";
  var PAGE = { "/campaign/dashboard/": ["campaign", "t", "helvi-track-logo-v4.png", "Helvi Track"],
               "/selection/": ["selection", "s", "helvi-selection-logo-v4.png", "Helvi Selection"],
               "/creator/": ["creator", "c", "helvi-intelligence-logo-v5.png", "Helvi Intelligence"],
               "/market/": ["study", "s", "helvi-intelligence-logo-v5.png", "Helvi Intelligence"] };
  var path = location.pathname.replace(/index\.html$/, "");
  var here = null;
  Object.keys(PAGE).forEach(function (p) { if (path.slice(-p.length) === p) here = PAGE[p]; });
  var ROOT = here ? path.slice(0, path.length - Object.keys(PAGE).filter(function (p) { return PAGE[p] === here; })[0].length) + "/" : "/";

  function hashArg(k) {
    var m = new RegExp("[#&]" + k + "=([^&]+)").exec(location.hash || "");
    return m ? decodeURIComponent(m[1]) : "";
  }
  var ref = here ? hashArg(here[1]) : "";
  if (here && here[0] === "creator") ref = ref.toUpperCase();

  // The token: in the link, or kept for this tab when the page rewrote its own hash (tabs, filters).
  var tok = hashArg("r");
  var KEY = "hv-report:" + path;
  try {
    if (/^[A-Za-z0-9_-]{16,40}$/.test(tok)) sessionStorage.setItem(KEY, JSON.stringify({ t: tok, ref: ref }));
    else {
      var kept = JSON.parse(sessionStorage.getItem(KEY) || "null");
      tok = kept && kept.ref === ref ? kept.t : "";
    }
  } catch (e) { if (!/^[A-Za-z0-9_-]{16,40}$/.test(tok)) tok = ""; }

  var loadedAt = new Date();
  function stamp(d) {
    try {
      return d.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
    } catch (e) { return d.toISOString().slice(0, 16).replace("T", " "); }
  }
  function day(sec) {
    try { return new Date(sec * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }); }
    catch (e) { return ""; }
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function el(tag, cls, html) { var n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; }
  function ready(fn) { if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn); else fn(); }

  var HV = window.HVReport = window.HVReport || {};
  HV.shared = !!(here && tok);
  HV.kind = here ? here[0] : null;
  HV.ref = ref;
  // When the numbers on screen were read: the moment the page loaded its data.
  HV.asOf = function () { return "Data as of " + stamp(loadedAt); };
  HV.markLoaded = function () { loadedAt = new Date(); var s = document.getElementById("rs-asof"); if (s) s.textContent = HV.asOf(); };

  var I_DOWN = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>';
  var I_LINK = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 14a4.5 4.5 0 0 0 6.4 0l3.2-3.2a4.5 4.5 0 0 0-6.4-6.4L12 5.6"/><path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3.2 3.2a4.5 4.5 0 0 0 6.4 6.4l1.2-1.2"/></svg>';

  // Download PDF: the page's own PDF when it has one (Track's printAll, the analysis), else the page printed
  // as a report: the print head, the whole list, no buttons (report-share.css "print").
  HV.download = function (btn) {
    if (typeof HV.pdf === "function") return HV.pdf(btn);
    var title = (document.getElementById("sel-title") || document.getElementById("ev-mi-t") || {}).textContent || document.title;
    if (here && here[0] === "study") {
      var sname = (document.querySelector(".ev-mi__sel, .ev-mi__sub b") || {}).textContent;
      title = "Competitor study" + (sname ? " · " + sname : "");
    }
    HV.printHead(String(title).trim());
    var root = document.documentElement;
    root.classList.add("rs-printing");
    var done = function () { root.classList.remove("rs-printing"); window.removeEventListener("afterprint", done); };
    window.addEventListener("afterprint", done);
    setTimeout(function () { window.print(); }, 60);
  };

  // A print-only head for pages that print themselves (selection, competitor study): the module mark,
  // the report's name and when its data was read.
  HV.printHead = function (title) {
    var h = document.getElementById("rs-printhead");
    if (!h) { h = el("div", "rs-printhead"); h.id = "rs-printhead"; h.setAttribute("aria-hidden", "true"); document.body.insertBefore(h, document.body.firstChild); }
    h.innerHTML = '<img src="' + ROOT + "assets/brand/modules/" + here[2] + '" alt="">'
      + "<div><b>" + esc(title || document.title) + "</b><span>" + esc(HV.asOf()) + " · Prepared by HelloVoice</span></div>";
  };

  if (!here) return;

  // #…&pdf=1 opens straight into the PDF once the report has drawn (a link to the PDF, and headless checks).
  if (/[#&]pdf=1/.test(location.hash) && here[0] !== "campaign") ready(function () {
    // Drawn, then quiet: the page keeps filling in (cards, the map, totals) for a moment after its first paint.
    var tries = 0, last = Date.now(), mo = new MutationObserver(function () { last = Date.now(); });
    mo.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true });
    var wait = function () {
      var drawn = here[0] === "selection" ? document.querySelectorAll(".cat-card").length
        : here[0] === "study" ? document.querySelectorAll("#ev-market .ev-mi__bd *").length > 20
        : document.getElementById("pp-print");
      if ((drawn && Date.now() - last > 1500) || ++tries > 80) { mo.disconnect(); HV.download(document.getElementById("pp-print")); }
      else setTimeout(wait, 400);
    };
    wait();
  });

  /* ------------------------------------------------------------- shared view (a client link) -- */
  if (HV.shared) {
    window.HV_SHARED = { token: tok, kind: here[0] };
    document.documentElement.classList.add("hv-shared");

    // Every request to the portal carries the link, and only what the link opens answers.
    var nativeFetch = window.fetch;
    if (nativeFetch) {
      window.fetch = function (input, init) {
        if (typeof input === "string" && (input.indexOf(API + "/api/") === 0 || input.indexOf(location.origin + API + "/api/") === 0)
            && !/[?&]r=/.test(input)) {
          input += (input.indexOf("?") < 0 ? "?" : "&") + "r=" + encodeURIComponent(tok);
        }
        return nativeFetch.call(this, input, init);
      };
    }
    var meta = null;
    var asked = (nativeFetch ? nativeFetch.call(window, API + "/api/report?r=" + encodeURIComponent(tok) + "&peek=1", { credentials: "include", cache: "no-store" })
      .then(function (r) { return r.json().then(function (b) { return { st: r.status, b: b }; }); })
      .catch(function () { return { st: 0, b: {} }; }) : Promise.resolve({ st: 0, b: {} }));

    // Nothing leads back into the portal: a click on a link to another portal page does nothing.
    document.addEventListener("click", function (ev) {
      var a = ev.target && ev.target.closest ? ev.target.closest("a[href]") : null;
      if (!a) return;
      var u;
      try { u = new URL(a.getAttribute("href"), location.href); } catch (e) { return; }
      if (u.origin !== location.origin) return;                         // Instagram, TikTok, the post itself
      if (u.pathname === location.pathname && u.hash && !/[#&](t|s|c)=/.test(u.hash)) return;   // a tab or an anchor on this page
      ev.preventDefault();
      ev.stopPropagation();
    }, true);

    ready(function () {
      document.body.setAttribute("data-no-appnav", "");
      var bar = el("div", "rs-bar");
      bar.setAttribute("role", "region");
      bar.setAttribute("aria-label", "Shared report");
      bar.innerHTML = '<div class="rs-bar__in">'
        + '<img class="rs-bar__mark" src="' + ROOT + "assets/brand/modules/" + here[2] + '" alt="' + esc(here[3]) + '">'
        + '<div class="rs-bar__meta"><b id="rs-for">Shared report</b><span id="rs-asof">' + esc(HV.asOf()) + '</span><span id="rs-until"></span></div>'
        // A shared selection is for deciding, not downloading (Bido 2026-11-03): no PDF in its bar.
        + (here[0] === "selection" ? "" : '<button type="button" class="rs-btn rs-btn--lime" id="rs-pdf">' + I_DOWN + "<span>Download PDF</span></button>") + "</div>";
      document.body.insertBefore(bar, document.body.firstChild);
      var pdf = document.getElementById("rs-pdf");
      if (pdf) pdf.addEventListener("click", function () { HV.download(this); });
      asked.then(function (res) {
        meta = res.b || {};
        if (res.st !== 200 || !meta.ok) return ended(meta.reason);
        if (meta.label) document.getElementById("rs-for").textContent = "For " + meta.label;
        else if (meta.title) document.getElementById("rs-for").textContent = meta.title;
        if (meta.expires_at) document.getElementById("rs-until").textContent = "Link open until " + day(meta.expires_at);
      });
    });

    function ended(reason) {
      var msg = reason === "revoked" ? "HelloVoice closed this link." : reason === "ended" ? "This link has ended." : "This link does not open a report.";
      document.documentElement.classList.add("hv-shared--ended");
      var box = el("section", "rs-ended");
      box.setAttribute("role", "alert");
      box.innerHTML = '<img src="' + ROOT + "assets/brand/modules/" + here[2] + '" alt="' + esc(here[3]) + '">'
        + "<h1>This report is not available</h1><p>" + esc(msg) + " Ask your HelloVoice contact for a new link.</p>";
      document.body.appendChild(box);
    }
    return;
  }

  /* ---------------------------------------------------- HelloVoice: Share with client -- */
  if (!ref || !window.fetch) return;
  // The competitor study has no PDF of their own: its Download PDF sits in the same slot. The selection has
  // none: it is shared, not downloaded (Bido 2026-11-03).
  if (here[0] === "study") ready(function () {
    var put = function () {
      var s = slot();
      if (!s || s.querySelector(".rs-pdf")) return !!s;
      var b = el("button", "rs-btn rs-btn--lime rs-pdf", I_DOWN + "<span>Download PDF</span>");
      b.type = "button";
      b.addEventListener("click", function () { HV.download(b); });
      s.insertBefore(b, s.firstChild);
      return true;
    };
    if (!put()) { var mo2 = new MutationObserver(function () { if (put()) mo2.disconnect(); }); mo2.observe(document.body, { childList: true, subtree: true }); }
  });
  var STATE = null, pop = null, scrim = null, btn = null, late = false;
  // The selection's action row (AI, Merge, ROI) is drawn by connect.js a moment after load; if it never comes,
  // the button falls back to the slot under the header.
  setTimeout(function () { late = true; if (STATE && !btn) mount(); }, 6000);

  function api(method, body) {
    var url = API + "/api/report/shares" + (method === "GET" ? "?kind=" + encodeURIComponent(here[0]) + "&ref=" + encodeURIComponent(ref) : "");
    return fetch(url, { method: method, credentials: "include", cache: "no-store",
                        headers: body ? { "Content-Type": "application/json" } : undefined,
                        body: body ? JSON.stringify(body) : undefined })
      .then(function (r) { return r.json().then(function (b) { return { st: r.status, b: b }; }); });
  }

  // Where the button goes on each page: beside the page's own Download PDF.
  function slot() {
    if (here[0] === "campaign") return document.querySelector(".db-head__actions");
    if (here[0] === "creator") { var p = document.getElementById("pp-print"); return p ? p.parentNode : null; }
    if (here[0] === "selection") return document.getElementById("cx-selact") || (late ? document.getElementById("rs-slot-selection") : null);
    var hd = document.querySelector("#ev-market .ev-mi__hd");
    if (!hd) return null;
    var sl = document.getElementById("rs-slot-study");
    if (!sl) { sl = el("div", "rs-slot"); sl.id = "rs-slot-study"; hd.appendChild(sl); }
    return sl;
  }

  function left(r) {
    var d = Math.ceil((r.expires_at - Date.now() / 1000) / 86400);
    return d <= 1 ? "Ends today" : d + " days left";
  }

  function rows() {
    var open = STATE.links.filter(function (x) { return x.state === "open"; });
    var gone = STATE.links.filter(function (x) { return x.state !== "open"; }).slice(0, 4);
    function row(x, fresh) {
      return '<li class="rs-ln' + (x.state !== "open" ? " is-gone" : "") + (fresh ? " is-new" : "") + '">'
        + '<div class="rs-ln__who"><b>' + esc(x.label || "No name") + "</b><small>"
        + (x.state === "open" ? left(x) : x.state === "revoked" ? "Revoked" : "Ended")
        + " · " + (x.opens === 1 ? "1 open" : x.opens + " opens") + (x.prices ? " · with prices" : "") + "</small></div>"
        + (x.state === "open" ? '<div class="rs-ln__acts"><button type="button" class="rs-chip" data-copy="' + esc(x.url) + '">Copy</button>'
          + '<button type="button" class="rs-chip rs-chip--ghost" data-revoke="' + x.id + '">Revoke</button></div>' : "")
        + "</li>";
    }
    return (open.length ? '<ul class="rs-lns">' + open.map(function (x) { return row(x, x.id === STATE.fresh); }).join("") + "</ul>"
      : '<p class="rs-empty">No open links yet. A link opens this report only, live, with no sign-in.</p>')
      + (gone.length ? '<details class="rs-old"><summary>Closed links</summary><ul class="rs-lns">' + gone.map(function (x) { return row(x); }).join("") + "</ul></details>" : "");
  }

  function draw() {
    var days = STATE.days.map(function (d) {
      return '<label class="rs-seg__o"><input type="radio" name="rs-days" value="' + d + '"' + (d === STATE.default_days ? " checked" : "") + "><span>" + d + " days</span></label>";
    }).join("");
    pop.innerHTML = '<div class="rs-pop__h"><h2 id="rs-pop-t">Share with client</h2>'
      + '<button type="button" class="rs-x" data-close aria-label="Close">×</button></div>'
      + '<p class="rs-pop__lede">' + esc(STATE.title) + " — live, read-only, no sign-in and no way into the rest of the portal."
      + (here[0] === "selection" ? " They can approve, reject and comment on each creator; it comes back here." : "") + "</p>"
      + rows()
      + '<form class="rs-new" novalidate><label class="rs-f"><span>For</span><input name="label" maxlength="80" placeholder="e.g. Glamy Lab marketing team" autocomplete="off"></label>'
      + '<fieldset class="rs-seg"><legend>Open for</legend>' + days
      // Any number of days (item 294): typing here takes over from the chips.
      + '<label class="rs-own"><input type="number" name="own_days" min="1" max="365" inputmode="numeric" placeholder="Other" aria-label="Number of days"><span>days</span></label>'
      + "</fieldset>"
      + (here[0] === "selection" ? '<label class="rs-tog"><input type="checkbox" name="prices" checked><span>Show prices</span></label>' : "")
      + '<p class="rs-err" role="alert" hidden></p>'
      + '<button class="rs-btn rs-btn--lime rs-new__go" type="submit">' + I_LINK + "<span>Make link</span></button></form>";
  }

  function open() {
    if (!pop) {
      pop = el("div", "rs-pop");
      pop.setAttribute("role", "dialog");
      pop.setAttribute("aria-modal", "true");
      pop.setAttribute("aria-labelledby", "rs-pop-t");
      pop.hidden = true;
      // A centred dialog over a scrim: it never hangs off the button or runs past the window's edge.
      scrim = el("div", "rs-scrim");
      scrim.hidden = true;
      document.body.appendChild(scrim);
      document.body.appendChild(pop);
      pop.addEventListener("click", onPop);
      pop.addEventListener("submit", onMake);
      pop.addEventListener("input", function (e) {
        if (e.target.name === "own_days" && e.target.value) [].forEach.call(pop.querySelectorAll("input[name=rs-days]"), function (r) { r.checked = false; });
        if (e.target.name === "rs-days") { var o = pop.querySelector("input[name=own_days]"); if (o) o.value = ""; }
      });
      document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !pop.hidden) close(); });
      document.addEventListener("click", function (e) { if (!pop.hidden && !pop.contains(e.target) && !btn.contains(e.target)) close(); });
    }
    draw();
    scrim.hidden = false;
    pop.hidden = false;
    document.documentElement.classList.add("rs-modal-open");
    btn.setAttribute("aria-expanded", "true");
    var f = pop.querySelector("input[name=label]"); if (f) f.focus();
  }
  function close() { pop.hidden = true; scrim.hidden = true; document.documentElement.classList.remove("rs-modal-open"); btn.setAttribute("aria-expanded", "false"); btn.focus(); }

  function copy(text, b) {
    var done = function () { var t = b.textContent; b.textContent = "Copied"; b.classList.add("is-done"); setTimeout(function () { b.textContent = t; b.classList.remove("is-done"); }, 1600); };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, function () { window.prompt("Copy the link", text); });
    else window.prompt("Copy the link", text);
  }

  function onPop(e) {
    var t = e.target;
    if (t.closest("[data-close]")) return close();
    var c = t.closest("[data-copy]");
    if (c) return copy(c.getAttribute("data-copy"), c);
    var rv = t.closest("[data-revoke]");
    if (rv) {
      if (!window.confirm("Revoke this link? It stops working at once.")) return;
      rv.disabled = true;
      api("POST", { revoke: +rv.getAttribute("data-revoke") }).then(function (res) {
        if (res.st === 200) refresh(); else { rv.disabled = false; window.alert("That did not work. Try again."); }
      });
    }
  }

  function onMake(e) {
    e.preventDefault();
    var f = e.target, go = f.querySelector(".rs-new__go"), err = f.querySelector(".rs-err");
    var d = f.querySelector("input[name=rs-days]:checked"), own = parseInt(f.own_days.value, 10);
    if (f.own_days.value && !(own >= 1 && own <= 365)) { err.textContent = "Type a number of days from 1 to 365."; err.hidden = false; f.own_days.focus(); return; }
    go.disabled = true; go.classList.add("is-busy"); err.hidden = true;
    api("POST", { kind: here[0], ref: ref, label: f.label.value, days: own || (d ? +d.value : STATE.default_days),
                  prices: f.prices ? f.prices.checked : false })
      .then(function (res) {
        if (res.st !== 200 || !res.b.ok) throw new Error((res.b && res.b.message) || "The link was not made. Try again.");
        STATE.fresh = res.b.link.id;
        return refresh().then(function () {
          var c = pop.querySelector(".rs-ln.is-new [data-copy]");
          if (c) copy(c.getAttribute("data-copy"), c);
        });
      })
      .catch(function (x) { err.textContent = x.message || "The link was not made. Try again."; err.hidden = false; })
      .then(function () { go.disabled = false; go.classList.remove("is-busy"); });
  }

  function refresh() {
    return api("GET").then(function (res) {
      if (res.st !== 200) return;
      var fresh = STATE && STATE.fresh;
      STATE = res.b; STATE.fresh = fresh;
      if (pop && !pop.hidden) draw();
      if (btn) btn.querySelector("[data-n]").textContent = count();
    });
  }
  function count() { var n = STATE.links.filter(function (x) { return x.state === "open"; }).length; return n ? String(n) : ""; }

  function mount() {
    var s = slot();
    if (!s || btn) return !!btn;
    // On the selection it is one of the header's actions, styled like Merge beside it.
    var inRow = s.id === "cx-selact";
    btn = el("button", (inRow ? "cx-btn cx-btn--line" : "rs-btn rs-btn--line") + " rs-share",
             (inRow ? I_LINK.replace(/16/g, "20") : I_LINK) + "<span>Share with client</span><i data-n>" + count() + "</i>");
    btn.type = "button";
    btn.setAttribute("aria-haspopup", "dialog");
    btn.setAttribute("aria-expanded", "false");
    btn.addEventListener("click", function () { if (pop && !pop.hidden) close(); else open(); });
    var roi = inRow ? s.querySelector(".cx-btn--roi") : null;
    if (roi) s.insertBefore(btn, roi); else s.appendChild(btn);
    return true;
  }

  ready(function () {
    api("GET").then(function (res) {
      if (res.st !== 200 || !res.b.ok) return;          // not someone who makes client links: nothing shows
      STATE = res.b;
      if (mount()) return;
      // The page draws its header after its data arrives: wait for the slot.
      var mo = new MutationObserver(function () { if (mount()) mo.disconnect(); });
      mo.observe(document.body, { childList: true, subtree: true });
    }).catch(function () {});
  });
})();
