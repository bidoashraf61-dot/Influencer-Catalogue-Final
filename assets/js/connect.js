/* HELVY Connect, phases C + D (approved mockups .impeccable/mockups/portal-v3-cd/).
 *
 *  - The onboarding tour's opener ("Take the 3-minute tour?", four chapters), offered
 *    once after the first sign-in and replayable from Help and the profile. The tour
 *    itself (tour.js / tour.css, loaded on start) plays the real pages on demo data;
 *    finishing pays +5 credits once (server-enforced).
 *  - The ROI Calculator: a drawer inside a selection (its creators' own numbers),
 *    a page in the profile (a tier mix), a compact card in Helvy's chat, the
 *    "Download PDF" (verdict first) and estimate vs actual on the campaign report.
 *    Only ever the client's own budget; never a creator or HelloVoice price.
 *  - AI on selections: "Add more like these" and "Creators like this".
 *
 * Needs portal.js (window.hvPortal: h, api, icon, clip). Everything the server or
 * the client sends is put on the page as text, never as HTML.
 */
(function () {
  "use strict";
  // Pages name this file AND portal.js adds it when it runs first: run once, or every
  // listener here (the look-alike and ideas sheets, the tour) would fire twice.
  if (window.__hvConnect) return;
  window.__hvConnect = true;
  var HV = window.hvPortal = window.hvPortal || {};
  var started = false;

  function ready(fn) { if (HV.h) fn(); else setTimeout(function () { ready(fn); }, 40); }

  ready(function () {
    var h = HV.h, api = HV.api, ROOT = HV.root;
    function ic(n, cls) { return HV.icon(n, "cx-i" + (cls ? " " + cls : "")); }
    function icEl(n) { var s = document.createElement("span"); s.innerHTML = ic(n); return s.firstChild; }
    function clip(n, cls, o) { return HV.clip(n, cls, o); }
    var PAGE = document.body.getAttribute("data-page") || "";

    function big(n) {
      if (n == null) return "–";
      n = Number(n);
      if (n >= 1e6) return (Math.round(n / 1e5) / 10).toString().replace(/\.0$/, "") + "M";
      if (n >= 1e4) return Math.round(n / 1e3) + "K";
      if (n >= 1e3) return (Math.round(n / 1e2) / 10).toString().replace(/\.0$/, "") + "K";
      return String(Math.round(n));
    }
    function money(n) { return Math.round(Number(n) || 0).toLocaleString("en-US"); }
    function sar(n) { return n >= 1000 ? money(n) : String(n); }
    // Fix batch 4 (Bido): the client sees every figure as a range around the estimate
    // ("160K–250K"), never one exact-looking number.
    function fig(f) {
      if (f.range && f.range.length === 2 && f.range[0] !== f.range[1]) {
        var one = function (x) { return f.unit === "SAR" ? (x >= 1000 ? money(x) : String(x)) : f.unit === "%" || f.unit === "×" ? String(x) : big(x); };
        return one(f.range[0]) + "–" + one(f.range[1]);
      }
      if (f.value == null) return "–";
      if (f.unit === "SAR") return String(f.value);
      if (f.unit === "%") return String(f.value);
      if (f.unit === "×") return String(f.value);
      return big(f.value);
    }
    function initials(name) {
      return String(name || "").replace(/^dr\.?\s+/i, "").trim().split(/\s+/).slice(0, 2).map(function (w) { return w.charAt(0); }).join("").toUpperCase() || "?";
    }
    function sig(s) { return s && s.grade ? h("span", { class: "cx-sig cx-sig--" + s.grade }, s.label) : null; }
    function toast(text) {
      if (window.hvSelection && window.hvSelection.toast) { window.hvSelection.toast(text); return; }
      var t = document.getElementById("cx-toast");
      if (!t) { t = h("div", { id: "cx-toast", class: "sel-toast", role: "status" }); document.body.appendChild(t); }
      t.textContent = text; t.hidden = false;
      clearTimeout(t._t); t._t = setTimeout(function () { t.hidden = true; }, 4200);
    }
    function me() { return HV.me || null; }
    function aiFree() { var m = me(); return m && m.ai_free; }

    /* ================================================================ ROI */
    var GOALS = [["awareness", "Awareness", "Reach, views, CPM"], ["engagement", "Engagement", "Interactions, ER, CPE"],
                 ["traffic", "Traffic", "Tracking-link clicks, CPC"]];
    var PLATS = [["Instagram", "ig", "pm--ig"], ["TikTok", "tt", "pm--tt"], ["Snapchat", "sc", "pm--sc"], ["YouTube", "yt", "pm--yt"]];
    var TIERS = [["mega", "Mega", "1M+ followers"], ["macro", "Macro", "500K–1M"], ["mid", "Mid", "100K–500K"], ["micro", "Micro", "20K–100K"], ["nano", "Nano", "Under 20K"]];
    var TITLE = { awareness: "What your budget can reach", engagement: "What your budget can earn", traffic: "What your budget can drive" };

    function seg(state, key, onChange) {
      var box = h("div", { class: "cx-seg", role: "radiogroup", "aria-label": "Goal" });
      GOALS.forEach(function (g) {
        var b = h("button", { type: "button", role: "radio", "aria-checked": String(state.goal === g[0]) }, h("b", null, g[1]), h("small", null, g[2]));
        b.addEventListener("click", function () {
          state.goal = g[0];
          [].forEach.call(box.children, function (x) { x.setAttribute("aria-checked", String(x === b)); });
          onChange();
        });
        box.appendChild(b);
      });
      return box;
    }
    function platToggles(state, onChange) {
      var box = h("div", { class: "cx-tgls" });
      PLATS.forEach(function (p) {
        var b = h("button", { type: "button", class: "cx-tgl", "aria-pressed": String(state.platforms.indexOf(p[0]) > -1) },
          h("span", { class: "cx-pm cx-" + p[2], html: ic(p[1]) }), p[0]);
        b.addEventListener("click", function () {
          var i = state.platforms.indexOf(p[0]);
          if (i > -1 && state.platforms.length === 1) return;            // at least one
          if (i > -1) state.platforms.splice(i, 1); else state.platforms.push(p[0]);
          b.setAttribute("aria-pressed", String(i === -1));
          onChange();
        });
        box.appendChild(b);
      });
      return box;
    }
    function budgetBox(state, onChange) {
      var inp = h("input", { type: "text", inputmode: "numeric", autocomplete: "off", "aria-label": "Your budget in SAR", placeholder: "e.g. 120,000",
        value: state.budget ? money(state.budget) : "" });
      // Arabic-Indic (٠-٩) and Persian (۰-۹) digits count as digits (fix batch 4): the field used
      // to strip everything but 0-9, so a budget typed on an Arabic keyboard vanished. The caret
      // keeps its place among the digits when the grouping commas are redrawn, and nothing is
      // rewritten while an input method is still composing.
      function ascii(s) {
        return String(s).replace(/[٠-٩]/g, function (d) { return String(d.charCodeAt(0) - 0x0660); })
                        .replace(/[۰-۹]/g, function (d) { return String(d.charCodeAt(0) - 0x06F0); });
      }
      function tidy() {
        var raw = ascii(inp.value), caret = inp.selectionStart == null ? raw.length : inp.selectionStart;
        var before = raw.slice(0, caret).replace(/[^0-9]/g, "").length;
        var n = raw.replace(/[^0-9]/g, "").replace(/^0+(?=\d)/, "").slice(0, 10);
        state.budget = n ? Number(n) : 0;
        var out = n ? money(n) : "";
        if (inp.value !== out) {
          inp.value = out;
          var pos = 0, seen = 0;
          while (pos < out.length && seen < Math.min(before, n.length)) { if (/[0-9]/.test(out[pos])) seen++; pos++; }
          if (document.activeElement === inp) { try { inp.setSelectionRange(pos, pos); } catch (e) { /* not a text field */ } }
        }
        onChange();
      }
      inp.addEventListener("input", function (e) { if (!e.isComposing) tidy(); });
      inp.addEventListener("compositionend", tidy);
      return h("label", { class: "cx-money" }, h("span", null, "SAR"), inp, h("em", null, "excl. VAT"));
    }
    function mixBox(state, onChange) {
      var box = h("div", { class: "cx-mix" });
      TIERS.forEach(function (t) {
        var out = h("output", { "aria-live": "polite" }, String(state.mix[t[0]] || 0));
        function set(d) { state.mix[t[0]] = Math.max(0, Math.min(50, (state.mix[t[0]] || 0) + d)); out.textContent = String(state.mix[t[0]]); onChange(); }
        box.appendChild(h("div", null, h("div", null, h("b", null, t[1]), h("small", null, t[2])),
          h("div", { class: "cx-step" },
            h("button", { type: "button", "aria-label": "Fewer " + t[1] + " creators", html: ic("minus"), onclick: function () { set(-1); } }), out,
            h("button", { type: "button", "aria-label": "More " + t[1] + " creators", html: ic("plus"), onclick: function () { set(1); } }))));
      });
      return box;
    }
    function q(label, node, aside) { return h("div", { class: "cx-q" }, h("span", { class: "cx-label" }, label, aside || null), node); }

    var ESTIMATE_LINE = "Estimate, not a result. Real results depend on the content, the timing and the audience.";
    function resultPanel(res, opts) {
      opts = opts || {};
      var box = h("section", { class: "cx-res", "aria-live": "polite" });
      var v = res.verdict || {};
      box.appendChild(h("div", { class: "cx-res__top" },
        h("div", null, h("h3", null, TITLE[res.goal] || TITLE.awareness), h("p", null, res.summary + (res.posts ? " · " + res.posts + " post" + (res.posts === 1 ? "" : "s") : ""))),
        h("div", { class: "cx-verdict cx-verdict--" + (v.grade || "none") }, h("b", null, v.label || "Add a budget"), h("small", null, "against the benchmark"))));
      var dl = h("dl", { class: "cx-figs" });
      (res.figures || []).forEach(function (f) {
        var n = h("span", { class: "cx-n" }, h("span", { class: "cx-v" }, fig(f)));
        if (f.unit) n.appendChild(h("small", null, f.unit === "×" ? "×" : f.unit === "%" ? "%" : " " + f.unit));
        dl.appendChild(h("div", null, h("dt", null, f.label), h("dd", null, n, f.sig ? h("div", null, sig(f.sig)) : null)));
      });
      box.appendChild(dl);
      if (res.split && res.split.length) {
        var tot = res.split.reduce(function (s, x) { return s + x.value; }, 0) || 1, cols = ["var(--go)", "var(--vivid-orange)", "#b9d400", "#8a7a68"];
        var bar = h("div", { class: "cx-mixbar", role: "img", "aria-label": res.split.map(function (x) { return x.label + " " + big(x.value); }).join(", ") });
        var key = h("div", { class: "cx-mixkey" });
        res.split.forEach(function (x, i) {
          var seg_ = h("i"); seg_.style.width = (x.value / tot * 100) + "%"; seg_.style.background = cols[i]; bar.appendChild(seg_);
          var k = h("span", null, x.label + " ", h("b", null, big(x.value))); k.style.setProperty("--c", cols[i]); key.appendChild(k);
        });
        box.appendChild(bar); box.appendChild(key);
      }
      var c = res.cost;
      if (c) {
        var lo = c.scale[0], hi = c.scale[1], span = (hi - lo) || 1;
        var pct = function (x) { return Math.max(0, Math.min(100, (x - lo) / span * 100)); };
        var fair = h("span", { class: "cx-band__fair" }); fair.style.left = pct(c.fair[0]) + "%"; fair.style.width = (pct(c.fair[1]) - pct(c.fair[0])) + "%";
        var cr = c.range && c.range[0] !== c.range[1] ? c.range : [c.value, c.value];
        var yours = "SAR " + (cr[0] === cr[1] ? sar(cr[0]) : sar(cr[0]) + "–" + sar(cr[1]));
        var you = h("span", { class: "cx-band__you" });
        you.style.left = pct(cr[0]) + "%"; you.style.width = Math.max(0, pct(cr[1]) - pct(cr[0])) + "%";
        var fairTxt = "SAR " + sar(c.fair[0]) + "–" + sar(c.fair[1]);
        var band = h("div", { class: "cx-band", "data-grade": (res.verdict && res.verdict.grade) || "none" },
          h("div", { class: "cx-band__hd" }, h("b", null, "Your " + c.label + " against a fair range"), h("span", null, (res.market_label || "KSA") + ", " + res.platforms.join(" and "))),
          h("div", { class: "cx-band__track" }, fair, you),
          h("div", { class: "cx-band__k" }, h("span", null, "SAR " + sar(c.scale[0])), h("span", null, "SAR " + sar(c.scale[1]))),
          h("ul", { class: "cx-band__lg" },
            h("li", { class: "is-fair" }, h("i"), h("span", null, "Fair range"), h("b", null, fairTxt)),
            h("li", { class: "is-you" }, h("i"), h("span", null, "Your " + c.label), h("b", null, yours))));
        box.appendChild(band);
      }
      if (res.skipped && res.skipped.length) box.appendChild(h("p", { class: "cx-skipped" }, "Not on these platforms, so left out: " + res.skipped.slice(0, 6).join(", ") + (res.skipped.length > 6 ? "…" : "") + "."));
      if (!opts.compact) box.appendChild(h("p", { class: "cx-srcs" }, ESTIMATE_LINE + " After the campaign, your report shows estimate vs actual."));
      return box;
    }

    function estimate(body) { return api("POST", "/api/roi/estimate", body).then(function (r) { return r.b && r.b.ok ? r.b.result : null; }); }
    function debounce(fn, ms) { var t; return function () { clearTimeout(t); t = setTimeout(fn, ms); }; }

    /* -- the PDF: a print-ready page, verdict first, saved as PDF from the print dialog -- */
    function printPdf(res, ctx) {
      var w = window.open("", "_blank");
      if (!w) { toast("Allow pop-ups to download the PDF."); return; }
      var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
      var v = res.verdict || {}, col = { good: "#14884a", moderate: "#e2780f", low: "#ee1515" }[v.grade] || "#383838";
      var figs = (res.figures || []).map(function (f) {
        return "<tr><td>" + esc(f.label) + "</td><td class='n'>" + esc(fig(f)) + (f.unit ? " " + esc(f.unit) : "") + "</td><td>" + esc(f.sig ? f.sig.label : "") + "</td></tr>";
      }).join("");
      var html = "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><title>ROI estimate · HELVY Connect</title>" +
        "<style>@page{size:A4;margin:18mm}body{font:14px/1.55 'DM Sans',Arial,sans-serif;color:#121212;margin:0}" +
        "h1{font:400 40px/1 Bebasneue,'Arial Narrow',Arial,sans-serif;margin:18px 0 4px;letter-spacing:.01em}" +
        ".hd{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #121212;padding-bottom:12px}" +
        ".hd img{width:150px}.v{display:inline-block;margin:18px 0 6px;padding:10px 26px 8px;border-radius:999px;color:#fff;background:" + col + ";font:400 34px/1 Bebasneue,'Arial Narrow',Arial,sans-serif;letter-spacing:.04em}" +
        ".muted{color:#4a4a4a}table{width:100%;border-collapse:collapse;margin-top:16px}td{padding:9px 6px;border-bottom:1px solid #ddd}td.n{font-weight:700;text-align:right}" +
        ".fine{margin-top:22px;font-size:11.5px;color:#4a4a4a}</style></head><body>" +
        "<div class='hd'><img src='" + esc(ROOT) + "assets/brand/helvy-connect/helvy-connect-light-640.webp?v=c4' alt='HELVY Connect'><span class='muted'>" + esc(new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })) + "</span></div>" +
        "<div class='v'>" + esc(v.label || "Estimate") + "</div><div class='muted'>Against the benchmark for this mix</div>" +
        "<h1>ROI estimate" + (ctx && ctx.name ? " · " + esc(ctx.name) : "") + "</h1><p class='muted'>" + esc(res.summary) + (res.budget ? " · budget SAR " + esc(money(res.budget)) + " excl. VAT" : "") + "</p>" +
        "<table>" + figs + "</table>" + (res.cost ? "<p class='muted'>Your " + esc(res.cost.label) + " SAR " + esc(res.cost.range ? res.cost.range.join("–") : res.cost.value) + " · fair range SAR " + esc(res.cost.fair[0]) + "–" + esc(res.cost.fair[1]) + "</p>" : "") +
        "<p class='fine'>" + esc(ESTIMATE_LINE) + " Costs use your own budget only; this is not a quote. " +
        "Powered by HelloVoice · A BlueHolding Company.</p><script>window.onload=function(){setTimeout(function(){window.print()},300)}<\/script></body></html>";
      w.document.open(); w.document.write(html); w.document.close();
    }

    /* -- the drawer inside a selection: seeded from the estimate saved with it, if any -- */
    function buildDrawer(S, state, pool, approved, prev) {
      var scrim = h("div", { class: "cx-dr__scrim" });
      var dr = h("aside", { class: "cx-dr", role: "dialog", "aria-modal": "true", "aria-labelledby": "cx-roi-t" });
      var x = h("button", { class: "cx-x", type: "button", "aria-label": "Close the ROI Calculator", html: ic("x") });
      dr.appendChild(h("header", { class: "cx-dr__hd" }, h("h2", { id: "cx-roi-t" }, "ROI Calculator", h("small", null, S.name())),
        h("span", { class: "cx-tag cx-tag--est", html: ic("info") + "Estimate" }), x));
      var body = h("div", { class: "cx-dr__body" });
      var outBox = h("div");
      var last = null;
      var run = debounce(function () {
        outBox.classList.add("cx-busy");
        var b = { goal: state.goal, budget: state.budget, platforms: state.platforms, market: state.market };
        if (state.src === "mix") b.mix = state.mix; else b.token = S.token();
        estimate(b).then(function (res) { outBox.classList.remove("cx-busy"); if (res) { outBox.textContent = ""; outBox.appendChild(resultPanel(res)); last = res; } });
      }, 260);
      var mixWrap = h("div", { hidden: true }, mixBox(state, run));
      var faces = h("span", { class: "cx-faces" });
      pool.slice(0, 6).forEach(function (c) { var cr = S.creator(c); faces.appendChild(h("span", { class: "cx-ph" }, initials(cr ? cr.name : c))); });
      var srcBox = h("div", { class: "cx-src" },
        h("label", null, h("input", { type: "radio", name: "cx-src", checked: true, onchange: function () { state.src = "sel"; mixWrap.hidden = true; run(); } }),
          h("span", null, h("b", null, approved.length ? "This selection’s " + approved.length + " approved creator" + (approved.length === 1 ? "" : "s") : "This selection’s " + pool.length + " creators"),
            h("small", null, "Uses their real followers and engagement. 1 post per creator per platform."), faces)),
        h("label", null, h("input", { type: "radio", name: "cx-src", onchange: function () { state.src = "mix"; mixWrap.hidden = false; run(); } }),
          h("span", null, h("b", null, "A tier mix instead"), h("small", null, "Try a different mix of creator sizes before you choose."))));
      body.appendChild(h("div", { class: "cx-inp" },
        q("Your budget", h("div", null, h("p", { class: "cx-fine", style: "margin:0 0 8px" }, "Your own number. We use it only to work out cost per result."), budgetBox(state, run))),
        q("Goal", seg(state, "goal", run)), q("Platforms", platToggles(state, run)), q("Creators", h("div", { class: "cx-src" }, srcBox, mixWrap))));
      body.appendChild(outBox);
      dr.appendChild(body);
      var saveB = h("button", { class: "cx-btn", type: "button", html: ic("save") + "<span>Save to selection</span>" });
      var pdfB = h("button", { class: "cx-btn cx-btn--line", type: "button", html: ic("dl") + "<span>Download PDF</span>" });
      // Colleagues can run the estimate and download it; saving it to the selection is the owner's.
      var mayEditSel = !S.role || ["owner", "admin"].indexOf(S.role()) > -1;
      dr.appendChild(h("footer", { class: "cx-dr__ft" }, mayEditSel ? saveB : document.createTextNode(""), pdfB));
      saveB.addEventListener("click", function () {
        var b = { token: S.token(), goal: state.goal, budget: state.budget, platforms: state.platforms, market: state.market };
        if (state.src === "mix") b.mix = state.mix;
        saveB.disabled = true;
        api("POST", "/api/roi/save", b).then(function (r) { saveB.disabled = false; toast(r.b && r.b.ok ? "Estimate saved with " + S.name() + ". After the campaign, the report compares it with the results." : "That didn’t save. Please try again."); });
      });
      pdfB.addEventListener("click", function () { if (last) printPdf(last, { name: S.name() }); });
      function close() { scrim.remove(); dr.remove(); document.removeEventListener("keydown", onKey); document.body.classList.remove("pt-lock"); if (prev && prev.focus) prev.focus(); }
      function onKey(e) { if (e.key === "Escape") close(); }
      x.addEventListener("click", close); scrim.addEventListener("click", close);
      document.addEventListener("keydown", onKey);
      document.body.appendChild(scrim); document.body.appendChild(dr); document.body.classList.add("pt-lock");
      run(); x.focus();
      return close;
    }
    function roiForSelection() {
      var S = window.hvSelection;
      if (!S || !S.token()) return;
      var prev = document.activeElement;
      api("GET", "/api/roi/saved?s=" + encodeURIComponent(S.token())).then(function (r) {
        var sv = r.b && r.b.saved && r.b.saved.input;
        var approved = S.codes().filter(function (c) { return S.status(c).s === "approved"; });
        var pool = approved.length ? approved : S.codes().filter(function (c) { var s = S.status(c).s; return s !== "rejected" && s !== "unavailable"; });
        var state = { goal: (sv && sv.goal) || "awareness", budget: (sv && Number(sv.budget)) || 0,
                      platforms: (sv && sv.platforms && sv.platforms.length ? sv.platforms : ["Instagram", "TikTok"]).slice(),
                      mix: { mid: 2, micro: 6 }, src: "sel", market: "SA" };
        buildDrawer(S, state, pool, approved, prev);
      });
    }
    HV.openRoi = roiForSelection;

    /* -- the compact card in Helvy's chat -- */
    HV.roiCard = function (res) {
      var card = h("div", { class: "hv-msg hv-msg--ai cx-rcard" });
      card.appendChild(h("div", { class: "cx-rcard__hd" }, h("b", { html: ic("calc") + "ROI Calculator" }), h("span", { class: "cx-tag cx-tag--est" }, "Estimate")));
      card.appendChild(h("p", null, res.summary + (res.budget ? " · SAR " + money(res.budget) : "")));
      var dl = h("dl", { class: "cx-figs" });
      (res.figures || []).slice(0, 4).forEach(function (f) {
        var n = h("span", { class: "cx-n" }, h("span", { class: "cx-v" }, fig(f)));
        if (f.unit) n.appendChild(h("small", null, f.unit === "SAR" ? " SAR" : f.unit));
        dl.appendChild(h("div", null, h("dt", null, f.label), h("dd", null, n)));
      });
      card.appendChild(dl);
      var v = res.verdict || {};
      card.appendChild(h("div", { class: "cx-rcard__v" }, h("span", { class: "cx-verdict cx-verdict--" + (v.grade || "none") }, h("b", null, v.label || "Estimate")), h("span", null, "against the benchmark")));
      var open = h("button", { class: "cx-btn", type: "button" }, "Open calculator");
      open.addEventListener("click", function () {
        try { sessionStorage.setItem("cx-roi-seed", JSON.stringify({ goal: res.goal, budget: res.budget, platforms: res.platforms, mix: res.mix || null })); } catch (e) { /* blocked */ }
        if (PAGE === "selection" && window.hvSelection && window.hvSelection.token()) roiForSelection(); else location.href = ROOT + "account/#roi";
      });
      var save = h("button", { class: "cx-btn cx-btn--line", type: "button", html: ic("save") + "<span>Save</span>" });
      save.addEventListener("click", function () { open.click(); });
      card.appendChild(h("div", { class: "cx-rcard__go" }, open, save));
      card.appendChild(h("p", { class: "cx-rcard__fine" }, ESTIMATE_LINE + " For creator prices, your account manager prepares a quote."));
      return card;
    };

    /* -- estimate vs actual -- */
    function versusBlock(v, withLink) {
      var box = h("section", { class: "cx-eva", "aria-label": "Estimate vs actual" });
      var when = new Date(v.saved_at * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
      box.appendChild(h("div", { class: "cx-eva__hd" },
        h("div", null, h("h2", null, v.campaign + " · estimate vs actual"), h("p", null, "Saved estimate from " + when + " against the live report." + (v.ended ? " Campaign ended." : " Campaign running."))),
        withLink ? h("a", { href: ROOT + "campaign/#t=" + encodeURIComponent(v.token) }, "Open the report") : null));
      var rows = h("div", { class: "cx-eva__rows" });
      v.rows.forEach(function (r) {
        var mx = Math.max(r.estimate, r.actual) || 1;
        var fmt = function (x) { return r.key === "er" ? x + "%" : big(x); };
        var e = h("i"), a = h("i"), ee = h("em"), ae = h("em");
        ee.style.width = (r.estimate / mx * 100) + "%"; ae.style.width = (r.actual / mx * 100) + "%";
        e.appendChild(ee); a.appendChild(ae);
        rows.appendChild(h("div", { class: "cx-eva__row" }, h("b", null, r.label),
          h("div", { class: "cx-eva__bars" }, h("span", { class: "cx-e" }, "Estimate", e, h("strong", null, fmt(r.estimate))),
                                               h("span", { class: "cx-a" }, "Actual", a, h("strong", null, fmt(r.actual)))),
          h("span", { class: "cx-sig cx-sig--" + r.sig.grade }, r.sig.label + " · " + r.delta)));
      });
      box.appendChild(rows);
      if (v.helvy) {
        var face = h("span", { class: "cx-hd" }); face.appendChild(h("img", { class: "hv-clip", src: HV.helvy, alt: "" }));
        box.appendChild(h("div", { class: "cx-advice" }, face, h("p", { class: "cx-advice__b" }, h("b", null, "Helvy"), v.helvy)));
      }
      return box;
    }

    /* -- the profile page section (account.js calls this for #roi) -- */
    HV.roiPage = function (p) {
      var seed = null;
      try { seed = JSON.parse(sessionStorage.getItem("cx-roi-seed") || "null"); sessionStorage.removeItem("cx-roi-seed"); } catch (e) { seed = null; }
      var state = { goal: (seed && seed.goal) || "engagement", budget: (seed && seed.budget) || 0,
                    platforms: (seed && seed.platforms) || ["Instagram", "TikTok"], mix: (seed && seed.mix) || { macro: 1, mid: 3, micro: 6 }, market: "SA" };
      p.appendChild(h("h1", { class: "cx-roipg__h1" }, "ROI Calculator"));
      p.appendChild(h("p", { class: "cx-roipg__lead" }, "See what your own budget can reach before you brief HelloVoice: reach, interactions or tracking-link clicks, judged against the market."));
      var outBox = h("div"), last = null;
      var run = debounce(function () {
        outBox.classList.add("cx-busy");
        estimate({ goal: state.goal, budget: state.budget, platforms: state.platforms, market: state.market, mix: state.mix }).then(function (res) {
          outBox.classList.remove("cx-busy"); if (!res) return; last = res; outBox.textContent = ""; outBox.appendChild(resultPanel(res)); outBox.appendChild(acts);
        });
      }, 260);
      var markets = h("div", { class: "cx-tgls" });
      [["SA", "Saudi Arabia"], ["AE", "UAE"], ["EG", "Egypt"]].forEach(function (m) {
        var b = h("button", { type: "button", class: "cx-tgl cx-tgl--plain", "aria-pressed": String(state.market === m[0]) }, m[1]);
        b.addEventListener("click", function () { state.market = m[0]; [].forEach.call(markets.children, function (x) { x.setAttribute("aria-pressed", String(x === b)); }); run(); });
        markets.appendChild(b);
      });
      var useSel = h("button", { type: "button", class: "cx-link" }, "use a selection");
      var inBox = h("div", { class: "cx-roipg__in" }, h("div", { class: "cx-inp" },
        q("Your budget", h("div", null, h("p", { class: "cx-fine", style: "margin:0 0 8px" }, "Your own number, used only for cost per result"), budgetBox(state, run))),
        q("Goal", seg(state, "goal", run)), q("Platforms", platToggles(state, run)),
        q("Creators", mixBox(state, run), h("em", null, "or ", useSel)), q("Market", markets)));
      var pick = h("select", { class: "cx-pick", "aria-label": "Selection to save to" });
      var saveB = h("button", { class: "cx-btn", type: "button", html: ic("save") + "<span>Save</span>" });
      var pdfB = h("button", { class: "cx-btn cx-btn--line", type: "button", html: ic("dl") + "<span>PDF</span>" });
      var note = h("p", { class: "cx-note", role: "status" });
      var acts = h("div", null, h("div", { class: "cx-roiact" }, h("span", { class: "cx-pickwrap" }, pick, h("span", { html: ic("down") })), saveB), h("div", { class: "cx-roiact" }, pdfB), note);
      api("GET", "/api/roi/selections").then(function (r) {
        var items = (r.b && r.b.items) || [];
        if (!items.length) { pick.appendChild(h("option", { value: "" }, "No selections yet")); saveB.disabled = true; return; }
        items.forEach(function (s) { pick.appendChild(h("option", { value: s.token }, "Save to " + s.name)); });
      });
      useSel.addEventListener("click", function () { pick.focus(); note.className = "cx-note"; note.textContent = "Pick a selection below to save this estimate with it; inside a selection the calculator uses its real creators."; });
      saveB.addEventListener("click", function () {
        if (!pick.value) return;
        saveB.disabled = true;
        api("POST", "/api/roi/save", { token: pick.value, goal: state.goal, budget: state.budget, platforms: state.platforms, market: state.market, mix: state.mix })
          .then(function (r) { saveB.disabled = false; note.className = "cx-note" + (r.b && r.b.ok ? "" : " cx-note--bad");
            note.textContent = r.b && r.b.ok ? "Saved with " + r.b.selection + "." : "That didn’t save. Please try again."; });
      });
      pdfB.addEventListener("click", function () { if (last) printPdf(last, null); });
      p.appendChild(h("div", { class: "cx-roipg" }, inBox, h("div", { class: "cx-roipg__out" }, outBox)));
      var vs = h("div");
      p.appendChild(vs);
      api("GET", "/api/roi/vs").then(function (r) { ((r.b && r.b.items) || []).forEach(function (v) { vs.appendChild(versusBlock(v, true)); }); });
      run();
    };

    /* -- the campaign report: estimate vs actual, under the goals -- */
    function campaignVersus() {
      var m = /(?:^|[#&])t=([A-Za-z0-9_-]+)/.exec(location.hash || "");
      var host = document.querySelector("#sec-overview .cat-container");
      if (!m || !host || host.querySelector(".cx-eva")) return;
      api("GET", "/api/roi/vs?t=" + encodeURIComponent(m[1])).then(function (r) {
        var v = r.b && r.b.items && r.b.items[0];
        if (v && !host.querySelector(".cx-eva")) host.appendChild(versusBlock(v, false));
      });
    }

    /* =================================================== AI ON SELECTIONS */
    function costTag(cost) {
      return aiFree() || !cost ? h("span", { class: "cx-tag cx-tag--free", html: ic("check") + "Free with your active campaign" })
        : h("span", { class: "cx-tag cx-tag--cost", html: ic("coin") + cost + " credits" });
    }
    function mountSelection() {
      var S = window.hvSelection;
      if (!S || !S.token() || document.getElementById("cx-selact")) return;
      // Bottom row of the selection header, pushed to its right end (CSS), a lime primary button.
      var foot = document.querySelector(".cat-selhead__foot") || document.querySelector(".cat-selhead");
      if (foot) {
        var b = h("button", { class: "cx-btn cx-btn--roi", type: "button", html: ic("calc") + "<span>ROI Calculator</span>", onclick: roiForSelection });
        foot.appendChild(h("div", { class: "cx-selact", id: "cx-selact" }, b));
      }
      var role = S.role();
      if (role !== "owner" && role !== "admin") return;
      var grid = document.querySelector(".cat-grid-section");
      if (!grid) return;
      var tries = 0;
      (function place() {
        if (!document.getElementById("sel-statusbar") && tries++ < 30) { setTimeout(place, 150); return; }
        grid.parentNode.insertBefore(moreCard(S), grid);
      })();
    }
    function moreCard(S) {
      var cur = S.curated() || {};
      var sec = h("section", { class: "cx-moresec", id: "cx-more", "aria-labelledby": "cx-more-t" });
      var inner = h("div", { class: "cat-pad" });
      var cont = h("div", { class: "cat-container" });
      var card = h("div", { class: "cx-more" });
      var count = 5, chips = {};
      var approved = S.codes().filter(function (c) { return S.status(c).s === "approved"; });
      var from = h("div", { class: "cx-more__from" });
      approved.slice(0, 5).forEach(function (c) { var cr = S.creator(c); from.appendChild(h("span", { class: "cx-ph" }, initials(cr ? cr.name : c))); });
      from.appendChild(h("span", null, approved.length ? "Based on your " + approved.length + " approved creator" + (approved.length === 1 ? "" : "s") : "Approve a few creators first, so Helvy knows what you like"));
      // Helvy on his lime disc (fix batch 4), the AI shortlist card's clips: an easy loop at rest,
      // a thumbs-up when a quick pick is tapped, the camera scan while he works, a cheer when the
      // creators land.
      var face = HV.lime ? HV.lime("loop", "cx-more__face") : clip("idle");
      card.appendChild(face);
      card.appendChild(h("div", null, h("h2", { id: "cx-more-t" }, "Add more like these", costTag(cur.moreCost)),
        h("p", null, "Helvy studies the creators you approved, their audience, tone and platforms, and adds more that match to ", h("b", null, "Under review"), " for you to decide."), from));
      var note = h("input", { class: "cx-briefin", type: "text", maxlength: "160", placeholder: "Anything to add? e.g. Jeddah-based, Arabic-first", "aria-label": "Anything to add for Helvy" });
      var quick = h("div", { class: "cx-quick", role: "group", "aria-label": "Quick picks" });
      [["doctors", "More doctors"], ["tiktok", "TikTok first"], ["under100k", "Under 100K followers"], ["women2534", "Women 25–34"]].forEach(function (c) {
        var b = h("button", { type: "button", "aria-pressed": "false" }, c[1]);
        b.addEventListener("click", function () {
          chips[c[0]] = !chips[c[0]]; b.setAttribute("aria-pressed", String(!!chips[c[0]]));
          if (chips[c[0]] && face.react && !card.classList.contains("is-cooking")) face.react("thumbs", "loop");
        });
        quick.appendChild(b);
      });
      var out = h("output", { "aria-live": "polite" }, "5");
      var go = h("button", { class: "cx-btn", type: "button", html: ic("sparkle") + "<span>Add 5 creators</span>" });
      function setN(d) { count = Math.max(1, Math.min(10, count + d)); out.textContent = String(count); go.lastChild.textContent = "Add " + count + " creator" + (count === 1 ? "" : "s"); }
      var cnt = h("div", { class: "cx-cnt" }, h("button", { type: "button", "aria-label": "Fewer", html: ic("minus"), onclick: function () { setN(-1); } }), out,
        h("button", { type: "button", "aria-label": "More", html: ic("plus"), onclick: function () { setN(1); } }));
      var msg = h("p", { class: "cx-more__msg", role: "status" });
      card.appendChild(h("div", { class: "cx-more__form" }, note, quick, h("div", { class: "cx-more__go" }, cnt, go)));
      card.appendChild(msg);
      go.addEventListener("click", function () {
        go.disabled = true; msg.textContent = "";
        // While Helvy works: the director's desk (thinking -> cards -> approve) and the step line.
        var seeds = S.codes().filter(function (c) { return S.status(c).s === "approved"; }).length;
        if (face.loop) face.loop("scan");
        var cook = HV.cooking ? HV.cooking({ dark: true, list: true, helvy: !face.loop, title: "Helvy is finding " + count + " more",
          steps: ["Studying your " + (seeds || "") + " approved creator" + (seeds === 1 ? "" : "s") + "…", "Reading their audience and tone…",
                  "Flipping through the roster…", "Scoring each match…", "Adding the best " + count + " to Under review…"] }) : null;
        if (cook) { card.classList.add("is-cooking"); card.appendChild(cook); cook.scrollIntoView({ block: "center", behavior: HV.reduce ? "auto" : "smooth" }); }
        api("POST", "/api/selection/more", { token: S.token(), note: note.value, count: count,
                                              chips: Object.keys(chips).filter(function (k) { return chips[k]; }) }).then(function (r) {
          var ok = r.b && r.b.ok && (r.b.added || []).length;
          return (cook && ok && cook.finish ? cook.finish() : Promise.resolve()).then(function () { return r; });
        }).then(function (r) {
          go.disabled = false;
          if (cook) { cook.stop(); cook.remove(); card.classList.remove("is-cooking"); }
          if (!r.b || !r.b.ok) { if (face.loop) face.loop("think"); msg.textContent = (r.b && r.b.message) || "Helvy couldn’t look just now. Please try again."; return; }
          var codes = (r.b.added || []).map(function (c) { return c.code; });
          if (!codes.length) { if (face.loop) face.loop("think"); msg.textContent = r.b.message || "Helvy found no one close enough."; return; }
          if (face.react) face.react("cheer", "loop");
          S.add(codes);
          if (r.b.credits != null && HV.setCredits) HV.setCredits(r.b.credits);
          msg.textContent = "Added " + codes.length + " creator" + (codes.length === 1 ? "" : "s") + " to Under review" + (r.b.spent ? " · " + r.b.spent + " credits used." : ".");
          toast(msg.textContent);
        });
      });
      cont.appendChild(card); inner.appendChild(cont); sec.appendChild(inner);
      return sec;
    }

    /* -- One side panel for Helvy's suggestions on a selection: "Creators like this" and, since
       fix batch 3, "Find a replacement" (which used to open a cramped list inside the rejected
       card). Photo, name, tier, followers, platform, city, why, View profile, Add. Added creators
       join the selection as Under review; a replaced creator stays in Rejected. -- */
    function suggestSheet(o) {
      var S = window.hvSelection;
      if (!S) return;
      var prev = document.activeElement;
      var scrim = h("div", { class: "cx-dr__scrim" });
      var sheet = h("aside", { class: "cx-sheet" + (o.kind ? " cx-sheet--" + o.kind : ""), role: "dialog", "aria-modal": "true", "aria-labelledby": "cx-al-t" });
      var x = h("button", { class: "cx-x", type: "button", "aria-label": "Close", html: ic("x") });
      sheet.appendChild(h("header", { class: "cx-sheet__hd" }, clip("point", "cx-hd--head"),
        h("div", null, h("h2", { id: "cx-al-t" }, o.title), h("p", null, o.sub)), x));
      var body = h("div", { class: "cx-sheet__body" });
      body.appendChild(h("div", { class: "cx-sheet__ctx" }, h("span", { html: ic(o.ctxIcon || "target") + o.ctx }), costTag(o.cost)));
      var list = h("div", { class: "cx-sugs" });
      body.appendChild(list);
      sheet.appendChild(body);
      var more = h("button", { class: "cx-btn cx-btn--line", type: "button", html: ic("sparkle") + "<span>Show 3 more</span>" });
      sheet.appendChild(h("footer", { class: "cx-sheet__ft" }, h("span", null, "Added creators join as ", h("b", null, "Under review"), o.foot || ". HelloVoice confirms availability."), more));
      function close() { scrim.remove(); sheet.remove(); document.removeEventListener("keydown", onKey); document.body.classList.remove("pt-lock"); if (prev && prev.focus && prev.isConnected) prev.focus(); }
      function onKey(e) { if (e.key === "Escape") close(); }
      x.addEventListener("click", close); scrim.addEventListener("click", close); document.addEventListener("keydown", onKey);
      document.body.appendChild(scrim); document.body.appendChild(sheet); document.body.classList.add("pt-lock"); x.focus();
      function load(againFlag) {
        list.textContent = "";
        var cook = HV.cooking ? HV.cooking({ steps: o.steps }) : h("div", { class: "cx-sheet__empty" }, "Helvy is looking…");
        list.appendChild(h("div", { class: "cx-sheet__empty cx-sheet__cook" }, cook));
        more.disabled = true;
        o.fetch(!!againFlag).then(function (r) {
          if (cook.stop) cook.stop();
          list.textContent = "";
          more.disabled = false;
          if (!r.b || !r.b.ok) { list.appendChild(h("div", { class: "cx-sheet__empty" }, (r.b && r.b.message) || "Helvy couldn’t look just now.")); return; }
          if (r.b.credits != null && HV.setCredits) HV.setCredits(r.b.credits);
          var found = o.pick(r.b) || [];
          if (o.loaded) o.loaded(found, r.b);
          if (!found.length) { list.appendChild(h("div", { class: "cx-sheet__empty" }, r.b.message || "Helvy found no one else close enough.")); more.disabled = true; return; }
          found.forEach(function (c) {
            var ph = h("span", { class: "cx-ph" }, c.photo_url ? "" : initials(c.name));
            if (c.photo_url) ph.style.backgroundImage = 'url("' + String(c.photo_url).replace(/"/g, "%22") + '")';
            var doc = /^hcp/i.test(c.tier || "");
            var tier = String(c.tier || "").replace(/^hcp\s*-\s*/i, "");
            var inSel = S.codes().indexOf(c.code) > -1;
            var add = h("button", { class: "cx-btn", type: "button", html: ic(inSel ? "check" : "plus") + "<span>" + (inSel ? "Added" : "Add") + "</span>" });
            if (inSel) add.disabled = true;
            add.addEventListener("click", function () {
              var n = S.add([c.code], { creators: [c] });
              var done = function (ok) {
                if (ok) { add.disabled = true; add.innerHTML = ic("check") + "<span>Added</span>"; toast(c.name + " added, under review."); }
                else toast("That creator isn’t in the catalogue right now.");
              };
              if (n && n.then) n.then(done); else done(!!n);
            });
            list.appendChild(h("article", { class: "cx-sug" }, ph,
              h("div", null, h("div", { class: "cx-sug__nm" }, h("h3", null, c.name), tier ? h("span", { class: "cx-sug__tier" + (doc ? " cx-sug__tier--doc" : "") }, doc ? "Doctor" : tier) : null),
                h("div", { class: "cx-sug__stats" }, h("span", null, h("b", null, big(c.followers)), " followers"), c.platform ? h("span", null, c.platform) : null, c.city ? h("span", null, c.city) : null),
                c.why ? h("p", { class: "cx-sug__why" }, h("b", null, "Why: "), c.why) : null),
              h("div", { class: "cx-sug__act" }, add, h("a", { href: ROOT + "creator/#c=" + encodeURIComponent(c.code), target: "_blank", rel: "noopener" }, "View profile"))));
          });
        });
      }
      more.addEventListener("click", function () { load(true); });
      load(!!o.again);
    }
    function alikeSheet(code, again) {
      var S = window.hvSelection;
      if (!S) return;
      var cr = S.creator(code) || { name: code };
      suggestSheet({ kind: "alike", again: again, title: "Creators like " + cr.name, sub: "Same audience and content style, matched to " + S.name() + ".",
        ctx: "Like " + cr.name, cost: (S.curated() || {}).alikeCost,
        steps: ["Reading " + cr.name + "’s profile…", "Flipping through creators…", "Matching audience and style…", "Picking the closest three…"],
        fetch: function (ag) { return api("POST", "/api/selection/alike", { token: S.token(), code: code, again: ag }); },
        pick: function (b) { return b.creators; } });
    }
    // Find a replacement: the same panel. Helvy's three are kept on the rejected creator, so
    // opening it again is free; "Show 3 more" looks again (and costs again).
    HV.replaceSheet = function (code, onFound) {
      var S = window.hvSelection;
      if (!S) return;
      var cr = S.creator(code) || { name: code };
      suggestSheet({ kind: "repl", title: "Replacements for " + cr.name, sub: "Three creators who fit " + S.name() + " in their place.",
        ctx: "Instead of " + cr.name, ctxIcon: "swap", cost: (S.curated() || {}).replaceCost,
        foot: ". " + cr.name + " stays in Rejected.",
        steps: ["Reading why you said no…", "Flipping through creators…", "Scoring fit…", "Picking three for you…"],
        fetch: function (ag) { return api("POST", "/api/selection/replace", { token: S.token(), code: code, again: ag }); },
        pick: function (b) { return b.replacements; },
        loaded: function (list) { if (onFound) onFound(list); } });
    };
    document.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("[data-alike]");
      if (!b) return;
      e.preventDefault(); e.stopPropagation();
      alikeSheet(b.getAttribute("data-alike"));
    }, true);

    /* ======================================================= CONTENT IDEAS (phase E)
       On a selection card and on the creator's page: Helvy drafts 2-3 hooks and concepts,
       English and Saudi Arabic, fitted to that creator's style and the selection's brief.
       Nothing is spent until the client presses "Write ideas"; ideas are kept, so opening
       them again is free. No prices, and no claims beyond the brief. */
    function ideasSheet(code, ctx) {
      ctx = ctx || {};
      var prev = document.activeElement;
      var name = ctx.name || code;
      var scrim = h("div", { class: "cx-dr__scrim" });
      var sheet = h("aside", { class: "cx-sheet cx-ideas", role: "dialog", "aria-modal": "true", "aria-labelledby": "cx-id-t" });
      var x = h("button", { class: "cx-x", type: "button", "aria-label": "Close", html: ic("x") });
      var sub = h("p", null, "Hooks and concepts fitted to their style" + (ctx.selName ? " and the brief of " + ctx.selName : "") + ".");
      sheet.appendChild(h("header", { class: "cx-sheet__hd" }, clip("point", "cx-hd--head"),
        h("div", null, h("h2", { id: "cx-id-t" }, "Content ideas for " + name), sub), x));
      var body = h("div", { class: "cx-sheet__body" });
      var ctxRow = h("div", { class: "cx-sheet__ctx" });
      body.appendChild(ctxRow);
      var list = h("div", { class: "cx-ideas__list", "aria-live": "polite" });
      body.appendChild(list);
      sheet.appendChild(body);
      var again = h("button", { class: "cx-btn cx-btn--line", type: "button", html: ic("redo") + "<span>New ideas</span>" });
      again.hidden = true;
      sheet.appendChild(h("footer", { class: "cx-sheet__ft" }, h("span", null, "Drafts to brief the creator. No prices or new claims: your medical or regulatory team approves every script."), again));
      function close() { scrim.remove(); sheet.remove(); document.removeEventListener("keydown", onKey); document.body.classList.remove("pt-lock"); if (prev && prev.focus) prev.focus(); }
      function onKey(e) { if (e.key === "Escape") close(); }
      x.addEventListener("click", close); scrim.addEventListener("click", close); document.addEventListener("keydown", onKey);
      document.body.appendChild(scrim); document.body.appendChild(sheet); document.body.classList.add("pt-lock"); x.focus();

      var token = ctx.token || "", cost = null;
      function setCtx(info) {
        ctxRow.textContent = "";
        if (info.selection) ctxRow.appendChild(h("span", { html: ic("brief") + "Brief: " }, info.selection.name));
        else ctxRow.appendChild(h("span", { html: ic("info") + "No selection brief: ideas follow their style and your profile" }));
        if ((info.selections || []).length > 1 && !ctx.token) {
          var pickSel = h("select", { class: "cx-ideas__sel", "aria-label": "Write for which selection" });
          info.selections.forEach(function (s2) { var o = h("option", { value: s2.token }, "For " + s2.name); if (info.selection && s2.token === info.selection.token) o.selected = true; pickSel.appendChild(o); });
          pickSel.addEventListener("change", function () { token = pickSel.value; load(); });
          ctxRow.appendChild(pickSel);
        }
        cost = info.cost;
        ctxRow.appendChild(costTag(cost));
      }
      function cards(items, fresh) {
        list.textContent = "";
        items.forEach(function (it, i) {
          var copy = h("button", { class: "cx-idea__copy", type: "button", "aria-label": "Copy idea " + (i + 1), html: ic("copy") + "<span>Copy</span>" });
          copy.addEventListener("click", function () {
            var txt = it.hook_en + "\n" + it.concept_en + "\n\n" + it.hook_ar + "\n" + it.concept_ar;
            var ok = function () { copy.lastChild.textContent = "Copied"; setTimeout(function () { copy.lastChild.textContent = "Copy"; }, 1600); };
            if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(txt).then(ok, function () { toast("Copy didn't work. Select the text instead."); });
            else toast("Copy isn't available here. Select the text instead.");
          });
          var art = h("article", { class: "cx-idea" + (fresh && !HV.reduce ? " is-in" : "") },
            h("div", { class: "cx-idea__top" }, h("span", { class: "cx-idea__n" }, String(i + 1)), h("span", { class: "cx-idea__fmt" }, it.format), copy),
            h("div", { class: "cx-idea__cols" },
              h("div", { class: "cx-idea__en", lang: "en" }, h("p", { class: "cx-idea__hook" }, "“" + it.hook_en + "”"), h("p", { class: "cx-idea__con" }, it.concept_en)),
              h("div", { class: "cx-idea__ar", lang: "ar", dir: "rtl" }, h("p", { class: "cx-idea__hook" }, it.hook_ar), h("p", { class: "cx-idea__con" }, it.concept_ar))));
          if (fresh && !HV.reduce) art.style.animationDelay = (i * 90) + "ms";
          list.appendChild(art);
        });
        again.hidden = false;
        again.querySelector("span").textContent = "New ideas";
        var chip = again.querySelector(".hv-cost");
        if (chip) chip.remove();
        if (cost) again.appendChild(h("span", { class: "hv-cost", html: ic("coin") + cost + " credits" }));
      }
      function intro() {
        list.textContent = "";
        var write = h("button", { class: "cx-btn", type: "button", html: ic("bulb") + "<span>Write ideas</span>" });
        write.addEventListener("click", function () { generate(false); });
        list.appendChild(h("div", { class: "cx-ideas__intro" },
          h("p", null, h("b", null, "Three ideas, in English and Arabic. "), "Helvy reads " + name + "’s platforms, interests and audience size" +
            " (their best posts too, once the full analysis is unlocked) and writes a hook and a concept for each."), write));
      }
      function generate(isAgain) {
        again.disabled = true;
        list.textContent = "";
        var cook = HV.cooking ? HV.cooking({ steps: ["Reading " + name + "’s style…", "Reading the brief…", "Writing hooks in English and Arabic…", "Checking: no prices, no claims…"] }) : null;
        list.appendChild(h("div", { class: "cx-sheet__empty cx-sheet__cook" }, cook || "Helvy is writing…"));
        api("POST", "/api/ideas", { code: code, token: token || undefined, again: !!isAgain }).then(function (r) {
          if (cook && cook.stop) cook.stop();
          again.disabled = false;
          if (r.b && r.b.credits != null && HV.setCredits) HV.setCredits(r.b.credits);
          if (!r.b || !r.b.ok) { list.textContent = ""; list.appendChild(h("div", { class: "cx-sheet__empty" }, (r.b && r.b.message) || "Helvy couldn’t write just now. You weren’t charged.")); if (!isAgain) again.hidden = true; return; }
          if (!(r.b.ideas || []).length) { list.textContent = ""; list.appendChild(h("div", { class: "cx-sheet__empty" }, r.b.message || "No ideas this time. You weren’t charged.")); return; }
          cards(r.b.ideas, true);
          if (r.b.spent) toast(r.b.spent + " credits used.");
        });
      }
      again.addEventListener("click", function () { generate(true); });
      function load() {
        list.textContent = "";
        list.appendChild(h("div", { class: "cx-sheet__empty" }, "Opening…"));
        api("GET", "/api/ideas?c=" + encodeURIComponent(code) + (token ? "&s=" + encodeURIComponent(token) : "")).then(function (r) {
          if (!r.b || !r.b.ok) { list.textContent = ""; list.appendChild(h("div", { class: "cx-sheet__empty" }, "These ideas aren’t available here.")); return; }
          setCtx(r.b);
          if (r.b.selection && !token) token = r.b.selection.token;
          if (!r.b.ai && !(r.b.ideas || []).length) { list.textContent = ""; list.appendChild(h("div", { class: "cx-sheet__empty" }, "Helvy can’t write ideas right now. Please try again later.")); return; }
          if ((r.b.ideas || []).length) cards(r.b.ideas, false); else intro();
        });
      }
      load();
    }
    HV.ideas = ideasSheet;
    document.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("[data-ideas]");
      if (!b) return;
      e.preventDefault(); e.stopPropagation();
      var S = window.hvSelection, code = b.getAttribute("data-ideas");
      var cr = S && S.creator ? S.creator(code) : null;
      ideasSheet(code, { token: S && S.token ? S.token() : "", selName: S && S.name ? S.name() : "", name: (cr && cr.name) || b.getAttribute("data-name") || code });
    }, true);
    // The creator's page: one button under the key numbers (the page redraws itself, so it is re-added).
    function mountCreatorIdeas() {
      var host = document.getElementById("pp-id");
      if (!host) return;
      var place = function () {
        var fields = host.querySelector(".pp-fields");
        var m = /(?:^|[#&])c=([A-Za-z0-9-]+)/.exec(location.hash || "");
        if (!fields || !m || fields.querySelector(".cx-ideabtn")) return;
        var nm = fields.querySelector(".pp-name");
        var b = h("button", { class: "cx-btn cx-btn--line cx-ideabtn", type: "button", "data-ideas": decodeURIComponent(m[1]).toUpperCase(),
                              "data-name": nm ? nm.textContent.trim() : "", html: ic("bulb") + "<span>Content ideas</span>" });
        var key = fields.querySelector(".pp-key");
        if (key && key.nextSibling) fields.insertBefore(b, key.nextSibling); else fields.appendChild(b);
      };
      place();
      if (window.MutationObserver) new MutationObserver(place).observe(host, { childList: true });
    }

    /* ========================================================= NEXT TIME (phase E)
       On an ended campaign's report: who to book again, who to replace, who to test once
       more, with the reasons from the campaign's own results. Deterministic (weekly.py). */
    var NEXT_GROUPS = [["rebook", "Book again", "check", "go"], ["replace", "Replace", "swap", "low"], ["watch", "One more test", "clock", "mid"]];
    function campaignNextTime() {
      var m = /(?:^|[#&])t=([A-Za-z0-9_-]+)/.exec(location.hash || "");
      var host = document.querySelector("#sec-overview .cat-container");
      if (!m || !host || host.querySelector(".cx-next")) return;
      api("GET", "/api/campaign/next?t=" + encodeURIComponent(m[1])).then(function (r) {
        var d = r.b && r.b.next;
        if (!d || host.querySelector(".cx-next")) return;
        var sec = h("section", { class: "cx-next", "aria-labelledby": "cx-next-t" });
        sec.appendChild(h("header", { class: "cx-next__hd" }, clip("point", "cx-next__hv cx-hd--head"),
          h("div", null, h("h2", { id: "cx-next-t" }, "Next time"), h("p", { class: "cx-next__sum" }, d.ai_summary || d.summary))));
        var cols = h("div", { class: "cx-next__cols" });
        NEXT_GROUPS.forEach(function (g) {
          var items = d[g[0]] || [];
          if (!items.length) return;
          var col = h("div", { class: "cx-next__col cx-next__col--" + g[3] });
          col.appendChild(h("h3", { class: "cx-next__h", html: '<span class="cx-next__ic">' + ic(g[2]) + "</span>" }, g[1], h("small", null, String(items.length))));
          var ul = h("ul", { class: "cx-next__list" });
          items.forEach(function (it) {
            ul.appendChild(h("li", null, h("b", null, it.name), h("span", { class: "cx-next__lead" }, it.lead),
              it.why && it.why.length ? h("span", { class: "cx-next__why" }, it.why.join(" · ")) : null));
          });
          col.appendChild(ul);
          cols.appendChild(col);
        });
        sec.appendChild(cols);
        if (d.instead && d.instead.length) {
          var row = h("div", { class: "cx-next__alt" }, h("p", null, h("b", null, "To replace them: "), "creators like " + (d.instead_like || "your best performer") + "."));
          var chipsRow = h("div", { class: "cx-next__alts" });
          d.instead.forEach(function (c) {
            var a = h("a", { class: "cx-next__p", href: ROOT + "creator/#c=" + encodeURIComponent(c.code) });
            var ph = h("span", { class: "cx-ph" }, c.photo_url ? "" : initials(c.name));
            if (c.photo_url) ph.style.backgroundImage = 'url("' + String(c.photo_url).replace(/"/g, "%22") + '")';
            a.appendChild(ph);
            a.appendChild(h("span", null, h("b", null, c.name), h("small", null, [c.followers ? big(c.followers) + " followers" : "", c.city].filter(Boolean).join(" · "))));
            chipsRow.appendChild(a);
          });
          row.appendChild(chipsRow);
          sec.appendChild(row);
        }
        sec.appendChild(h("p", { class: "cx-next__fine" }, "From this campaign’s results against the benchmarks for each creator’s size. Your account manager can rebook or replace anyone."));
        host.insertBefore(sec, host.firstChild ? host.firstChild.nextSibling : null);
      });
    }

    /* ================================================================ TOUR */
    // Tour v2 lives in tour.js + tour.css, fetched only when the client starts it (the demo
    // photos load with the demo pages). Here: the opener card and the loader.
    var TOUR_JS = "assets/js/tour.js?v=t2a", TOUR_CSS = "assets/css/tour.css?v=t2a";
    var tourLoad = null;
    function loadTour() {
      if (window.hvTour) return Promise.resolve(window.hvTour);
      if (tourLoad) return tourLoad;
      tourLoad = new Promise(function (ok, no) {
        var left = 2, fail = function () { tourLoad = null; no(); };
        var one = function () { if (--left === 0) ok(window.hvTour); };
        var l = document.createElement("link"); l.rel = "stylesheet"; l.href = ROOT + TOUR_CSS; l.onload = one; l.onerror = one;
        var sc = document.createElement("script"); sc.src = ROOT + TOUR_JS; sc.onload = one; sc.onerror = fail;
        document.head.appendChild(l); document.head.appendChild(sc);
      });
      return tourLoad;
    }
    // HV.tour() from Help, the profile and the opener; a chapter number jumps straight to it.
    HV.tour = function (chapter) {
      loadTour().then(function (t) { if (t) t.start(typeof chapter === "number" ? chapter : null); })
        .catch(function () { toast("The tour didn't load. Please try again."); });
    };
    var CHAPTERS = [["chat", "Brief Helvy", "Describe your campaign, get a shortlist"],
                    ["list", "Build your shortlist", "Filter, compare, approve or replace"],
                    ["shield", "Check & book", "The full analysis, then a quote"],
                    ["chart", "Track results", "Live posts, clicks and the verdict"]];

    function offerTour() {
      var m = me();
      var shown = false;
      try { shown = sessionStorage.getItem("cx-offer-shown") === "1"; } catch (e) { shown = false; }
      if (!m || m.kind !== "user" || m.tour || document.getElementById("cx-offer") || shown) return;
      if (PAGE !== "catalogue" && PAGE !== "account") return;
      try { sessionStorage.setItem("cx-offer-shown", "1"); } catch (e) { /* blocked */ }
      api("POST", "/api/tour", { action: "offered" });
      var first = m.user && m.user.name ? m.user.name.split(" ")[0] : "";
      var prev = document.activeElement;
      var scrim = h("div", { class: "cx-offer-scrim" });
      function close(then) {
        box.classList.add("is-out"); scrim.classList.add("is-out");
        document.removeEventListener("keydown", onKey, true);
        setTimeout(function () { box.remove(); scrim.remove(); if (then) then(); else if (prev && prev.focus) prev.focus({ preventScroll: true }); }, HV.reduce ? 0 : 180);
      }
      function later() { api("POST", "/api/tour", { action: "later" }); close(); }
      function go(ch) { close(function () { HV.tour(ch); }); }
      var list = h("ol", { class: "cx-offer__chaps", "aria-label": "Chapters. Pick one to jump straight to it." });
      CHAPTERS.forEach(function (c, i) {
        var b = h("button", { type: "button", class: "cx-offer__chap", html: '<span class="cx-offer__ic">' + ic(c[0]) + "</span><span><b></b><small></small></span>" + ic("arrow", "cx-offer__go-i") });
        b.querySelector("b").textContent = (i + 1) + " · " + c[1];
        b.querySelector("small").textContent = c[2];
        b.addEventListener("click", function () { go(i); });
        list.appendChild(h("li", null, b));
      });
      var start = h("button", { class: "cx-btn", type: "button", html: "<span>Start the tour</span>" + '<span class="cx-cost cx-cost--prize">+5 credits</span>' });
      var no = h("button", { class: "cx-btn cx-btn--ghost", type: "button" }, "Later");
      var box = h("aside", { class: "cx-offer", id: "cx-offer", role: "dialog", "aria-modal": "true", "aria-labelledby": "cx-of-t", "aria-describedby": "cx-of-p" },
        h("div", { class: "cx-offer__helvy" }, clip("hello", "cx-hd--edge", { once: true, then: "idle" })),
        h("div", { class: "cx-offer__in" },
          h("h2", { id: "cx-of-t" }, "Take the ", h("span", { class: "cx-nowrap" }, "3-minute"), " tour?"),
          h("p", { id: "cx-of-p", class: "cx-offer__lead" }, (first ? "Welcome, " + first + ". " : "") + "Four short chapters on a sample brand. Nothing you do in it is saved."),
          list,
          h("div", { class: "cx-offer__go" }, start, no),
          h("p", { class: "cx-offer__fine" }, "Replay it any time from Help or your profile.")));
      start.addEventListener("click", function () { go(null); });
      no.addEventListener("click", later);
      scrim.addEventListener("click", later);
      function onKey(e) {
        if (e.key === "Escape") { e.preventDefault(); later(); return; }
        if (e.key !== "Tab") return;
        var f = [].slice.call(box.querySelectorAll("button")), i = f.indexOf(document.activeElement);
        if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); }
        else if (!e.shiftKey && i === f.length - 1) { e.preventDefault(); f[0].focus(); }
      }
      document.addEventListener("keydown", onKey, true);
      document.body.appendChild(scrim); document.body.appendChild(box);
      start.focus({ preventScroll: true, focusVisible: false });
    }

    /* ================================================================ boot */
    function onMe() {
      if (started) return;
      started = true;
      // Wait for the page loader to lift before offering the tour.
      var waitLoader = function (fn, n) { if (document.documentElement.classList.contains("hv-loading") && (n || 0) < 100) setTimeout(function () { waitLoader(fn, (n || 0) + 1); }, 200); else fn(); };
      waitLoader(function () { setTimeout(offerTour, 900); });
      if (PAGE === "campaign") {
        campaignVersus();
        window.addEventListener("hashchange", function () { setTimeout(campaignVersus, 600); setTimeout(campaignNextTime, 700); });
        setTimeout(campaignVersus, 1500);
        setTimeout(campaignNextTime, 1200);
      }
      if (PAGE === "creator") mountCreatorIdeas();
    }
    if (HV.me) onMe(); else document.addEventListener("hv:me", onMe);
    if (window.hvSelection) mountSelection();
    document.addEventListener("hv:selection", function () { setTimeout(mountSelection, 0); });
  });
})();
