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
               "/campaign/": ["campaign", "t", "helvi-track-logo-v4.png", "Helvi Track"],
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
        : here[0] === "study" ? (HV.shared && typeof HV.studyReady === "function" ? HV.studyReady() : document.querySelectorAll("#ev-market .ev-mi__bd *").length > 20)
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
      // Pages with their own sticky bar sit it under this one (campaign.css .hv-shared .mx-tabs).
      var barH = function () { document.documentElement.style.setProperty("--rs-bar-h", bar.offsetHeight + "px"); };
      barH(); window.addEventListener("resize", barH);
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
  setTimeout(function () { late = true; if (STATE && !btn) mount(); }, 8000);

  function api(method, body) {
    var url = API + "/api/report/shares" + (method === "GET" ? "?kind=" + encodeURIComponent(here[0]) + "&ref=" + encodeURIComponent(ref) : "");
    return fetch(url, { method: method, credentials: "include", cache: "no-store",
                        headers: body ? { "Content-Type": "application/json" } : undefined,
                        body: body ? JSON.stringify(body) : undefined })
      .then(function (r) { return r.json().then(function (b) { return { st: r.status, b: b }; }); });
  }

  // Where the button goes on each page: beside the page's own Download PDF.
  function slot() {
    if (here[0] === "campaign") return document.querySelector(".db-head__actions") || document.querySelector(".mx-top__links");
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
  function ago(sec) {
    if (!sec) return "";
    var m = Math.max(0, Math.round((Date.now() / 1000 - sec) / 60));
    return m < 2 ? "just now" : m < 60 ? m + " min ago" : m < 1440 ? Math.round(m / 60) + " h ago" : Math.round(m / 1440) + " d ago";
  }
  // Who the link is for, filled in from the page: the selection's "Prepared for …" line.
  function forWhom() {
    var c = document.getElementById("sel-client");
    var t = c && !c.hidden ? c.textContent.replace(/^\s*Prepared for\s*/i, "").trim() : "";
    return t.length > 80 ? "" : t;
  }

  /* Item 296 (Bido 2026-11-03): the panel leads with making a link; each open link shows its use (opens, last
     open, and on a selection what the client decided) and is managed in place: Copy, Preview, +7 days, Edit
     (name, prices), Revoke. Closed links fold into one line. */
  function fb(x) {
    var f = x.feedback;
    if (!f) return "";
    var bits = [["approved", f.approved, "approved"], ["rejected", f.rejected, "rejected"], ["", f.notes, f.notes === 1 ? "note" : "notes"]]
      .filter(function (b) { return b[1]; });
    if (!bits.length) return '<p class="rs-fb rs-fb--none">' + (x.opens ? "Opened, no decisions yet" : "Not opened yet") + "</p>";
    return '<p class="rs-fb">' + bits.map(function (b) {
      return b[0] ? '<button type="button" class="rs-fb__b rs-fb__b--' + b[0] + '" data-see="' + b[0] + '" title="Show the ' + b[2] + ' creators"><b>' + b[1] + "</b> " + b[2] + "</button>"
                  : '<span class="rs-fb__b"><b>' + b[1] + "</b> " + b[2] + "</span>";
    }).join("") + "</p>";
  }
  function row(x) {
    var on = x.state === "open", meta = [];
    meta.push(on ? left(x) + " · until " + day(x.expires_at) : x.state === "revoked" ? "Revoked" : "Ended " + day(x.expires_at));
    meta.push(x.opens === 1 ? "1 open" : x.opens + " opens");
    if (x.last_open_at) meta.push("last " + ago(x.last_open_at));
    if (x.prices) meta.push("with prices");
    var editing = STATE.editing === x.id;
    // Item 300: each link is one line until it is opened (the new one and the one being edited open by themselves).
    var shut = !on || (STATE.openId !== x.id && !editing && x.id !== STATE.fresh);
    if (shut) return '<li class="rs-ln rs-ln--shut' + (on ? "" : " is-gone") + '" data-id="' + x.id + '">'
      + (on ? '<button type="button" class="rs-ln__row" data-open="' + x.id + '" aria-expanded="false">' : '<div class="rs-ln__row">')
      + '<b>' + esc(x.label || "No name") + "</b><small>" + esc(meta.slice(0, 2).join(" · ")) + "</small>"
      + (on ? '<span class="rs-ln__chev" aria-hidden="true"></span></button>' : "</div>") + "</li>";
    return '<li class="rs-ln' + (x.id === STATE.fresh ? " is-new" : "") + '" data-id="' + x.id + '">'
      + '<button type="button" class="rs-ln__row" data-open="' + x.id + '" aria-expanded="true"><b>' + esc(x.label || "No name") + "</b><small>"
      + esc(meta.join(" · ")) + '</small><span class="rs-ln__chev" aria-hidden="true"></span></button>'
      + (on ? fb(x) : "")
      + (on && !editing ? '<div class="rs-ln__acts">'
          + '<button type="button" class="rs-chip" data-copy="' + esc(x.url) + '">Copy link</button>'
          + '<a class="rs-chip rs-chip--line" href="' + esc(x.page) + '" target="_blank" rel="noopener">Preview</a>'
          + '<button type="button" class="rs-chip rs-chip--line" data-extend="' + x.id + '" title="Keep it open 7 more days">+7 days</button>'
          + '<button type="button" class="rs-chip rs-chip--line" data-edit="' + x.id + '">Edit</button>'
          + '<button type="button" class="rs-chip rs-chip--ghost" data-revoke="' + x.id + '">Revoke</button></div>' : "")
      + (on && editing ? '<div class="rs-ed"><label class="rs-f"><span>For</span><input name="ed_label" maxlength="80" value="' + esc(x.label) + '"></label>'
          + (here[0] === "selection" ? '<label class="rs-tog"><input type="checkbox" name="ed_prices"' + (x.prices ? " checked" : "") + "><span>Show prices</span></label>" : "")
          + '<div class="rs-ln__acts"><button type="button" class="rs-chip" data-save="' + x.id + '">Save</button>'
          + '<button type="button" class="rs-chip rs-chip--line" data-cancel>Cancel</button></div></div>' : "")
      + "</li>";
  }
  function rows() {
    var open = STATE.links.filter(function (x) { return x.state === "open"; });
    var gone = STATE.links.filter(function (x) { return x.state !== "open"; }).slice(0, 6);
    // Item 300: the links stay folded behind their count; many links get a search and scroll inside the panel.
    var shown = STATE.listOpen || STATE.fresh || STATE.editing;
    var q = (STATE.q || "").trim().toLowerCase(), list = q ? open.filter(function (x) { return (x.label || "No name").toLowerCase().indexOf(q) >= 0; }) : open;
    return '<section class="rs-links" aria-label="Links">'
      + (open.length ? '<button type="button" class="rs-sub rs-sub--btn" data-list aria-expanded="' + (shown ? "true" : "false") + '">Open links <i>' + open.length
          + '</i><span class="rs-ln__chev" aria-hidden="true"></span></button>' : '<h3 class="rs-sub">Open links</h3>')
      + (!open.length ? '<p class="rs-empty">None yet. Each link opens this ' + (here[0] === "selection" ? "selection" : "report") + " only.</p>"
        : !shown ? ""
        : (open.length > 5 ? '<label class="rs-find"><input type="search" name="find" placeholder="Find a link by name" aria-label="Find a link by name" value="' + esc(STATE.q || "") + '"></label>' : "")
          + '<ul class="rs-lns' + (open.length > 5 ? " rs-lns--many" : "") + '">' + (list.length ? list.map(row).join("") : '<li class="rs-empty">No link with that name.</li>') + "</ul>")
      + (gone.length ? '<details class="rs-old"><summary>' + gone.length + " closed link" + (gone.length === 1 ? "" : "s") + '</summary><ul class="rs-lns">'
        + gone.map(row).join("") + "</ul></details>" : "")
      + "</section>";
  }

  function draw() {
    var keep = pop.querySelector("form.rs-new"), was = keep ? { label: keep.label.value, own: keep.own_days.value,
      d: (keep.querySelector("input[name=rs-days]:checked") || {}).value, p: keep.prices ? keep.prices.checked : null } : null;
    var days = STATE.days.map(function (d) {
      return '<label class="rs-seg__o"><input type="radio" name="rs-days" value="' + d + '"' + (d === STATE.default_days ? " checked" : "") + "><span>" + d + " days</span></label>";
    }).join("");
    pop.innerHTML = '<div class="rs-pop__h"><h2 id="rs-pop-t">Share with client</h2>'
      + '<button type="button" class="rs-x" data-close aria-label="Close">×</button></div>'
      + '<p class="rs-pop__lede">' + esc(STATE.title) + " · live, read-only, no sign-in."
      + (here[0] === "selection" ? " Their approvals, rejections and notes come back here." : "") + "</p>"
      + '<form class="rs-new" novalidate><label class="rs-f"><span>For</span><input name="label" maxlength="80" placeholder="e.g. Glamy Lab marketing team" autocomplete="off"></label>'
      + '<fieldset class="rs-seg"><legend>Open for <em class="rs-until" aria-live="polite"></em></legend>' + days
      // Any number of days (item 294): typing here takes over from the chips.
      + '<label class="rs-own"><input type="number" name="own_days" min="1" max="365" inputmode="numeric" placeholder="Other" aria-label="Number of days"><span>days</span></label>'
      + "</fieldset>"
      + (here[0] === "selection" ? '<label class="rs-tog"><input type="checkbox" name="prices" checked><span>Show prices</span></label>' : "")
      + '<p class="rs-err" role="alert" hidden></p>'
      + '<button class="rs-btn rs-btn--lime rs-new__go" type="submit">' + I_LINK + "<span>Make link</span></button></form>"
      + rows();
    var f = pop.querySelector("form.rs-new");
    if (was) {
      f.label.value = was.label; f.own_days.value = was.own;
      if (was.d) { var r = f.querySelector("input[name=rs-days][value='" + was.d + "']"); if (r) r.checked = true; }
      else if (was.own) [].forEach.call(f.querySelectorAll("input[name=rs-days]"), function (r) { r.checked = false; });
      if (f.prices && was.p !== null) f.prices.checked = was.p;
    } else f.label.value = forWhom();
    if (was && !was.label && !STATE.typed) f.label.value = forWhom();
    until();
  }
  // The end date beside "Open for", following the chips and the typed number.
  function until() {
    var f = pop && pop.querySelector("form.rs-new"), u = f && f.querySelector(".rs-until");
    if (!u) return;
    var own = parseInt(f.own_days.value, 10), d = f.querySelector("input[name=rs-days]:checked");
    var n = own >= 1 && own <= 365 ? own : d ? +d.value : 0;
    u.textContent = n ? "· until " + day(Date.now() / 1000 + n * 86400) : "";
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
        if (e.target.name === "label") STATE.typed = true;
        if (e.target.name === "find") {         // filter in place, so the field keeps its focus
          STATE.q = e.target.value; var q = STATE.q.trim().toLowerCase();
          [].forEach.call(pop.querySelectorAll(".rs-lns--many > .rs-ln"), function (li) {
            var b = li.querySelector("b"); li.hidden = !!q && (b ? b.textContent.toLowerCase().indexOf(q) < 0 : true);
          });
          return;
        }
        until();
      });
      document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !pop.hidden) close(); });
      // A click inside the panel that redrew it (Edit, Cancel) leaves its target detached: that is not "outside".
      document.addEventListener("click", function (e) {
        if (!pop.hidden && e.target.isConnected && !pop.contains(e.target) && !btn.contains(e.target)) close();
      });
    }
    STATE.editing = null; STATE.typed = false;
    var old = pop.querySelector("form.rs-new"); if (old) old.remove();      // a fresh form each time it opens
    draw();
    refresh();                                                                 // opens and decisions as they are now
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
    var lst = t.closest("[data-list]");
    if (lst) { STATE.listOpen = lst.getAttribute("aria-expanded") !== "true"; STATE.fresh = STATE.listOpen ? STATE.fresh : null; STATE.editing = STATE.listOpen ? STATE.editing : null; return draw(); }
    var opn = t.closest("[data-open]");
    if (opn) { var id = +opn.getAttribute("data-open"); var was = STATE.openId === id || STATE.fresh === id;
      STATE.openId = was ? null : id; if (STATE.fresh === id) STATE.fresh = null; STATE.listOpen = true; return draw(); }
    var see = t.closest("[data-see]");
    if (see) {
      // The page's own status filter (Approved / Rejected) on the selection, then the list.
      close();
      var chip = document.querySelector('[data-st-filter="' + see.getAttribute("data-see") + '"]');
      if (chip) { if (chip.getAttribute("aria-pressed") !== "true") chip.click(); chip.scrollIntoView({ behavior: "smooth", block: "center" }); }
      return;
    }
    var ed = t.closest("[data-edit]");
    if (ed) { STATE.editing = +ed.getAttribute("data-edit"); draw(); var i = pop.querySelector("input[name=ed_label]"); if (i) i.focus(); return; }
    if (t.closest("[data-cancel]")) { STATE.editing = null; return draw(); }
    var sv = t.closest("[data-save]");
    if (sv) {
      var li = sv.closest(".rs-ln"), pr = li.querySelector("input[name=ed_prices]");
      var body = { edit: +sv.getAttribute("data-save"), label: li.querySelector("input[name=ed_label]").value };
      if (pr) body.prices = pr.checked;
      return change(sv, body, function () { STATE.editing = null; });
    }
    var ex = t.closest("[data-extend]");
    if (ex) return change(ex, { edit: +ex.getAttribute("data-extend"), extend: 7 });
    var rv = t.closest("[data-revoke]");
    if (rv) {
      if (!window.confirm("Revoke this link? It stops working at once.")) return;
      rv.disabled = true;
      api("POST", { revoke: +rv.getAttribute("data-revoke") }).then(function (res) {
        if (res.st === 200) refresh(); else { rv.disabled = false; window.alert("That did not work. Try again."); }
      });
    }
  }

  function change(b, body, after) {
    b.disabled = true;
    api("POST", body).then(function (res) {
      if (res.st !== 200 || !res.b.ok) throw new Error((res.b && res.b.message) || "That did not work. Try again.");
      if (after) after();
      return refresh();
    }).catch(function (x) { b.disabled = false; window.alert(x.message); });
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
        f.label.value = ""; f.own_days.value = "";
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
      var keep = STATE || {};
      STATE = res.b; STATE.fresh = keep.fresh; STATE.editing = keep.editing; STATE.typed = keep.typed;
      if (pop && !pop.hidden) draw();
      if (btn) btn.querySelector("[data-n]").textContent = count();
    });
  }
  function count() { var n = STATE.links.filter(function (x) { return x.state === "open"; }).length; return n ? String(n) : ""; }

  // Returns true once the button is in its final place. On a slow selection the fallback slot can come first: the
  // button then moves into the action row when connect.js draws it.
  function mount() {
    var s = slot();
    if (!s) return false;
    var inRow = s.id === "cx-selact";
    if (btn) {
      if (btn.parentNode === s) return here[0] !== "selection" || inRow;
      btn.className = "cx-btn cx-btn--line rs-share";
      btn.querySelector("svg").outerHTML = I_LINK.replace(/16/g, "20");
      btn.querySelector("span").textContent = "Share with client";
      place(s);
      return true;
    }
    // One Share button (item 294): it makes the client link; the dashboard's old invite-by-email Share goes.
    HV.canShare = true;
    ["db-share", "db-share-pop"].forEach(function (id) { var o = document.getElementById(id); if (o) o.remove(); });
    // On the selection it is one of the header's actions, styled like Merge beside it.
    btn = el("button", (inRow ? "cx-btn cx-btn--line" : "rs-btn rs-btn--line") + " rs-share",
             (inRow ? I_LINK.replace(/16/g, "20") : I_LINK) + "<span>" + (inRow ? "Share with client" : "Share") + "</span><i data-n>" + count() + "</i>");
    btn.type = "button";
    btn.setAttribute("aria-haspopup", "dialog");
    btn.setAttribute("aria-expanded", "false");
    btn.addEventListener("click", function () { if (pop && !pop.hidden) close(); else open(); });
    place(s);
    return here[0] !== "selection" || inRow;
  }
  function place(s) {
    var after = s.id === "cx-selact" ? document.getElementById("mg-btn") || document.getElementById("aa-btn") : null;
    if (after && after.parentNode === s) s.insertBefore(btn, after.nextSibling); else s.appendChild(btn);
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
