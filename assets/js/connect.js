/* HELVi Connect, phases C + D (approved mockups .impeccable/mockups/portal-v3-cd/).
 *
 *  - The ROI Calculator (v4, structure vs performance): a drawer inside a selection (its
 *    creators' own numbers), a page in the profile (a mix of sizes), a compact card in
 *    Helvi's chat, the "Download PDF" and estimate vs actual on the campaign report. A
 *    side-by-side table of HelloVoice's recommended structure for the same number of creators
 *    and the client's selection, the Selection quality, the gap in words and up to three ranked
 *    "Ways to improve". Results are RANGES. No budget, no cost per result, no market verdict,
 *    never a creator or HelloVoice price.
 *  - AI on selections: "Add more like these" and "Creators like this".
 *
 * Needs portal.js (window.hvPortal: h, api, icon, clip). Everything the server or
 * the client sends is put on the page as text, never as HTML.
 */
(function () {
  "use strict";
  // Pages name this file AND portal.js adds it when it runs first: run once, or every
  // listener here (the look-alike and ideas sheets) would fire twice.
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
    var GOALS = [["awareness", "Awareness", "Views and reach"], ["engagement", "Engagement", "Interactions"],
                 ["traffic", "Traffic", "Clicks on your link"]];
    var PLATS = [["Instagram", "ig", "pm--ig"], ["TikTok", "tt", "pm--tt"], ["Snapchat", "sc", "pm--sc"], ["YouTube", "yt", "pm--yt"]];
    var TIERS = [["mega", "Mega", "1M+ followers"], ["macro", "Macro", "500K–1M"], ["mid", "Mid", "100K–500K"], ["micro", "Micro", "20K–100K"], ["nano", "Nano", "Under 20K"]];
    var TITLE = { awareness: "What you can reach", engagement: "What you can earn", traffic: "What you can drive" };
    function titleOf(res) { var g = res.goals || [res.goal]; return g.length > 1 ? "What you can achieve" : TITLE[g[0]] || TITLE.awareness; }

    // One or several campaign types at once (Awareness, Engagement, Traffic), at least one.
    function seg(state, key, onChange) {
      var box = h("div", { class: "cx-seg", role: "group", "aria-label": "Campaign type, pick one or more" });
      if (!state.goals || !state.goals.length) state.goals = [state.goal || "awareness"];
      GOALS.forEach(function (g) {
        var b = h("button", { type: "button", "aria-pressed": String(state.goals.indexOf(g[0]) > -1) }, h("b", null, g[1]), h("small", null, g[2]));
        b.addEventListener("click", function () {
          var i = state.goals.indexOf(g[0]);
          if (i > -1 && state.goals.length === 1) return;           // at least one
          if (i > -1) state.goals.splice(i, 1); else state.goals.push(g[0]);
          state.goals = GOALS.map(function (x) { return x[0]; }).filter(function (x) { return state.goals.indexOf(x) > -1; });
          state.goal = state.goals[0];
          [].forEach.call(box.children, function (x, n) { x.setAttribute("aria-pressed", String(state.goals.indexOf(GOALS[n][0]) > -1)); });
          onChange();
        });
        box.appendChild(b);
      });
      return box;
    }
    function platToggles(state, onChange) {
      var box = h("div", { class: "cx-tgls" });
      PLATS.forEach(function (p) {
        var b = h("button", { type: "button", class: "cx-tgl", "data-plat": p[0], "aria-pressed": String(state.platforms.indexOf(p[0]) > -1) },
          h("span", { class: "cx-pm cx-" + p[2], html: ic(p[1]) }), p[0]);
        b.addEventListener("click", function () {
          var i = state.platforms.indexOf(p[0]);
          if (i > -1 && state.platforms.length === 1) return;            // at least one
          if (i > -1) state.platforms.splice(i, 1); else state.platforms.push(p[0]);
          state.mixP = null;                                              // a suggested per-platform mix no longer fits
          b.setAttribute("aria-pressed", String(i === -1));
          onChange();
        });
        box.appendChild(b);
      });
      box.sync = function () { [].forEach.call(box.children, function (b) { b.setAttribute("aria-pressed", String(state.platforms.indexOf(b.getAttribute("data-plat")) > -1)); }); };
      return box;
    }
    function mixBox(state, onChange) {
      var box = h("div", { class: "cx-mix" });
      TIERS.forEach(function (t) {
        var out = h("output", { "aria-live": "polite" }, String(state.mix[t[0]] || 0));
        function set(d) { state.mixP = null; state.mix[t[0]] = Math.max(0, Math.min(50, (state.mix[t[0]] || 0) + d)); out.textContent = String(state.mix[t[0]]); onChange(); }
        box.appendChild(h("div", null, h("div", null, h("b", null, t[1]), h("small", null, t[2])),
          h("div", { class: "cx-step" },
            h("button", { type: "button", "aria-label": "Fewer " + t[1] + " creators", html: ic("minus"), onclick: function () { set(-1); } }), out,
            h("button", { type: "button", "aria-label": "More " + t[1] + " creators", html: ic("plus"), onclick: function () { set(1); } }))));
      });
      return box;
    }
    // "How many creators?": any whole number 1-60. The usual range for the goal is a quiet hint, never a
    // warning; a number outside it is simply planned for. state.count 0 = the default (the selection's
    // creators, the mix's, or the brief's), shown once a result has said what that is.
    function countBox(state, onChange) {
      var MIN = 1, MAX = 60;
      var inp = h("input", { type: "text", inputmode: "numeric", autocomplete: "off", class: "cx-count__in", "aria-label": "How many creators" });
      var hint = h("p", { class: "cx-fine cx-count__hint", "aria-live": "polite" });
      function ascii(v) {
        return String(v).replace(/[٠-٩]/g, function (d) { return String(d.charCodeAt(0) - 0x0660); }).replace(/[۰-۹]/g, function (d) { return String(d.charCodeAt(0) - 0x06F0); });
      }
      function commit(n) {
        n = Math.max(MIN, Math.min(MAX, Math.round(Number(n) || 0)));
        if (!n) return;
        state.count = n; inp.value = String(n); onChange();
      }
      var minus = h("button", { type: "button", "aria-label": "Fewer creators", html: ic("minus"), onclick: function () { commit((state.count || Number(inp.value) || MIN) - 1); } });
      var plus = h("button", { type: "button", "aria-label": "More creators", html: ic("plus"), onclick: function () { commit((state.count || Number(inp.value) || 0) + 1); } });
      inp.addEventListener("input", function (e) {
        if (e.isComposing) return;
        var d = ascii(inp.value).replace(/[^0-9]/g, "").slice(0, 2);
        if (inp.value !== d) inp.value = d;
      });
      inp.addEventListener("change", function () { var d = ascii(inp.value).replace(/[^0-9]/g, ""); if (d) commit(Number(d)); else { state.count = 0; onChange(); } });
      inp.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); inp.blur(); } });
      var box = h("div", { class: "cx-count" }, h("div", { class: "cx-count__row" }, minus, inp, plus), hint);
      // after every result: the hint for the goal and the number in play
      box.setFrom = function (res) {
        var r = res.count_range;
        hint.textContent = r ? (res.goal_label || "Campaigns") + " campaigns usually run " + r.text + " creators." : "";
        if (document.activeElement !== inp) inp.value = String(state.count || res.count || "");
      };
      return box;
    }
    function q(label, node, aside) { return h("div", { class: "cx-q" }, h("span", { class: "cx-label" }, label, aside || null), node); }

    var ESTIMATE_LINE = "Estimate, not a result. Real results depend on the content, the timing and the audience.";
    var WAY_BUTTON = {
      replace: function () { return "Swap"; },
      remove: function (a) { return "Remove " + a.codes.length; },
      add: function (a) { return "Add " + a.codes.length; },
      second_post: function () { return "Count second posts"; },
      add_platform: function (a) { return "Add " + a.platform; },
      use_mix: function () { return "Use this mix"; }
    };
    var GOAL_FIG = { awareness: "views", engagement: "interactions", traffic: "clicks" };
    function rangeText(r) { return r && r.range && r.range.length === 2 && r.range[0] !== r.range[1] ? big(r.range[0]) + "–" + big(r.range[1]) : (r && r.value != null ? big(r.value) : "–"); }
    // The rows of the comparison: [label, recommended, yours, kind]; shared by the table and the PDF.
    function compareRows(res) {
      var I = res.ideal || {}, S = res.selection || {}, rows = [];
      rows.push(["Creators", String(I.creators || 0), String(S.creators || 0), "n"]);
      rows.push(["Posts", String(I.posts || 0), String(S.posts || 0), "n"]);
      var sizes = {}; (S.by_size || []).forEach(function (x) { sizes[x.size] = x; });
      var st = S.on_structure || {};
      if ((I.by_size || []).some(function (x) { return x.n || (sizes[x.size] && sizes[x.size].n); })) rows.push(["Creators by size (share of creators)", "", "", "n", "head"]);
      (I.by_size || []).forEach(function (x) {
        var m = sizes[x.size] || { n: 0, pct: 0 };
        if (!x.n && !m.n) return;
        var mark = S.posts ? (st[x.size] === "short" ? "short" : st[x.size] === "over" ? "over" : "n") : "n";
        rows.push([x.label, x.n + " (" + x.pct + "%)", S.creators ? m.n + " (" + m.pct + "%)" : "–", mark, "size"]);
      });
      var plats = res.platforms || [];
      if (plats.length > 1) {
        var bp = {}; (S.by_platform || []).forEach(function (x) { bp[x.platform] = x.posts; });
        (I.by_platform || []).forEach(function (x) { rows.push([x.platform + " posts", String(x.posts), String(bp[x.platform] || 0), "n", "size"]); });
      }
      var goalKeys = (res.goals || [res.goal]).map(function (g) { return GOAL_FIG[g]; });
      [["views", "Expected views"], ["interactions", "Expected interactions"], ["clicks", "Expected clicks"]].forEach(function (k) {
        var a = (I.ranges || {})[k[0]], b = (S.ranges || {})[k[0]];
        rows.push([k[1], rangeText(a), S.posts ? rangeText(b) : "–", goalKeys.indexOf(k[0]) > -1 ? "goal" : "n"]);
      });
      rows.push(["Average creator score", I.score != null ? I.score + " (typical)" : "–", S.score != null ? String(S.score) : "–", "n"]);
      return rows;
    }
    function qualityChip(q) {
      if (!q) return null;
      var txt = q.met ? "100%" : q.band ? q.low + "–" + q.high + "%" : q.pct + "%";
      return h("div", { class: "cx-quality", title: "Selection quality: your selection’s expected result as a share of HelloVoice’s recommended structure for the same number of creators" },
        h("b", null, txt), h("small", null, q.met ? "meets the recommended structure" : "of the ideal"), goalSplit(q));
    }
    // Several goals chosen: each goal's own quality beside the average, so a strong result on one
    // goal never hides a weak one ("Awareness 80% · Traffic 50%").
    var GOAL_NAME = { awareness: "Awareness", engagement: "Engagement", traffic: "Traffic" };
    function goalSplit(q) {
      var g = q && q.by_goal ? Object.keys(q.by_goal) : [];
      if (g.length < 2) return null;
      return h("span", { class: "cx-quality__goals" }, g.map(function (k) { return (GOAL_NAME[k] || k) + " " + q.by_goal[k] + "%"; }).join(" · "));
    }
    function compareTable(res) {
      var I = res.ideal || {};
      var t = h("table", { class: "cx-cmp" });
      t.appendChild(h("caption", { class: "cx-sr" }, "HelloVoice’s recommended structure compared with your selection"));
      t.appendChild(h("thead", null, h("tr", null, h("th", { scope: "col" }, ""),
        h("th", { scope: "col" }, "Recommended", h("small", null, I.title || "")),
        h("th", { scope: "col" }, "Your selection", h("small", null, res.creators ? res.creators + " creator" + (res.creators === 1 ? "" : "s") : "nothing chosen yet")))));
      var tb = h("tbody");
      compareRows(res).forEach(function (r) {
        if (r[4] === "head") {
          tb.appendChild(h("tr", { class: "cx-cmp__head" }, h("th", { scope: "rowgroup", colspan: "3" }, r[0])));
          return;
        }
        var tr = h("tr", { class: (r[3] === "goal" ? "cx-cmp__goal " : "") + (r[4] === "size" ? "cx-cmp__size" : "") });
        tr.appendChild(h("th", { scope: "row" }, r[0]));
        tr.appendChild(h("td", null, r[1]));
        tr.appendChild(h("td", { class: r[3] === "short" ? "cx-cmp__short" : r[3] === "over" ? "cx-cmp__over" : "" }, r[2]));
        tb.appendChild(tr);
      });
      t.appendChild(tb);
      return h("div", { class: "cx-cmpwrap" }, t);
    }
    // The comparison: the quality headline, the gap in words, the side-by-side table, up to three
    // ranked ways to improve with one button each. opts.onWay(action) runs a way; without it none is shown.
    function resultPanel(res, opts) {
      opts = opts || {};
      var box = h("section", { class: "cx-res", "aria-live": "polite" });
      var t = res.trust || {};
      var q = res.quality;
      box.appendChild(h("div", { class: "cx-res__top" },
        h("div", null, h("h3", null, q ? (t.of ? "Selection quality" : "Quality of your mix") : "Recommended structure"),
          h("p", null, res.summary + (res.posts ? " · " + res.posts + " post" + (res.posts === 1 ? "" : "s") : ""))),
        qualityChip(q)));
      if (q) {
        var gap = res.gap || [];
        if (res.compare_line) box.appendChild(h("p", { class: "cx-gap" }, res.compare_line));
        box.appendChild(h("p", { class: "cx-gap" }, gap.length ? h("span", null, h("b", null, "The gap: "), gap.join("; ") + ".")
          : "Your selection is close to HelloVoice’s recommended structure."));
      } else if (!res.creators) {
        box.appendChild(h("p", { class: "cx-gap" }, "HelloVoice’s recommended structure for this goal. Choose creators to see how your selection compares."));
      }
      box.appendChild(compareTable(res));
      if (q) box.appendChild(h("p", { class: "cx-fine cx-cmpnote" }, "A tier within ±" + ((res.ideal && res.ideal.tolerance) || 10) + " points of its recommended share of creators counts as on structure."));
      if (res.skipped && res.skipped.length) box.appendChild(h("p", { class: "cx-skipped" }, "Not on these platforms, so left out: " + res.skipped.slice(0, 6).join(", ") + (res.skipped.length > 6 ? "…" : "") + "."));
      var ways = (res.ways || []).slice(0, 3);
      if (opts.onWay && ways.length) {
        var ol = h("ol", { class: "cx-ways" });
        ways.forEach(function (w, i) {
          var label = (WAY_BUTTON[w.action && w.action.type] || function () { return "Apply"; })(w.action || {});
          var b = h("button", { class: "cx-btn cx-btn--line", type: "button" }, label);
          b.addEventListener("click", function () { b.disabled = true; opts.onWay(w.action, w); });
          ol.appendChild(h("li", null, h("span", { class: "cx-ways__n", "aria-hidden": "true" }, String(i + 1)), h("p", null, w.text), b));
        });
        box.appendChild(h("div", { class: "cx-waysbox" }, h("h4", null, "Ways to improve"), ol));
      }
      if (!opts.compact) {
        box.appendChild(h("p", { class: "cx-srcs" }, (t.line ? t.line + " " : "") + "The recommended structure is HelloVoice’s proposal for this campaign type. " + ESTIMATE_LINE + " After the campaign, your report compares it with what happened."));
      }
      return box;
    }

    function estimate(body) { return api("POST", "/api/roi/estimate", body).then(function (r) { return r.b && r.b.ok ? r.b.result : null; }); }
    function debounce(fn, ms) { var t; return function () { clearTimeout(t); t = setTimeout(fn, ms); }; }

    /* -- the PDF: a print-ready page, ranges first, saved as PDF from the print dialog -- */
    function printPdf(res, ctx) {
      var w = window.open("", "_blank");
      if (!w) { toast("Allow pop-ups to download the PDF."); return; }
      var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
      var q = res.quality;
      var rows = compareRows(res).map(function (r) {
        if (r[4] === "head") return "<tr><th colspan='3' style='padding-top:14px;font-size:12px;color:#4a4a4a'>" + esc(r[0]) + "</th></tr>";
        return "<tr><th>" + esc(r[0]) + "</th><td>" + esc(r[1]) + "</td><td>" + esc(r[2]) + "</td></tr>";
      }).join("");
      var qTxt = q ? (q.band ? q.low + "–" + q.high + "%" : q.pct + "%") : "";
      var head = q ? "<p class='q'><b>" + esc(qTxt) + "</b> Selection quality: your selection’s expected result as a share of HelloVoice’s recommended structure for the same number of creators.</p>" +
        ((res.gap || []).length ? "<p><b>The gap:</b> " + esc(res.gap.join("; ")) + ".</p>" : "") : "";
      var ways = (res.ways || []).slice(0, 3).map(function (w) { return "<li>" + esc(w.text) + "</li>"; }).join("");
      if (res.compare_line) head += "<p>" + esc(res.compare_line) + "</p>";
      var html = "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><title>ROI estimate · HELVi Connect</title>" +
        "<style>@page{size:A4;margin:18mm}body{font:14px/1.55 'DM Sans',Arial,sans-serif;color:#121212;margin:0}" +
        "h1{font:400 40px/1 Bebasneue,'Arial Narrow',Arial,sans-serif;margin:18px 0 4px;letter-spacing:.01em}" +
        ".hd{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #121212;padding-bottom:12px}" +
        ".hd img{width:150px}.muted{color:#4a4a4a}table{width:100%;border-collapse:collapse;margin-top:16px}th,td{padding:9px 6px;border-bottom:1px solid #ddd;text-align:left}td{font-weight:700;text-align:right}thead th{font-size:12px;color:#4a4a4a;text-align:right}thead th:first-child{text-align:left}.q b{font:400 44px/1 Bebasneue,'Arial Narrow',Arial,sans-serif;margin-right:10px}" +
        ".fine{margin-top:22px;font-size:11.5px;color:#4a4a4a}</style></head><body>" +
        "<div class='hd'><img src='" + esc(ROOT) + "assets/brand/helvy-connect/helvy-connect-light-640.webp?v=c5' alt='HELVi Connect'><span class='muted'>" + esc(new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })) + "</span></div>" +
        "<h1>ROI estimate" + (ctx && ctx.name ? " · " + esc(ctx.name) : "") + "</h1><p class='muted'>" + esc(res.summary) + "</p>" +
        head + "<table><thead><tr><th></th><th>Recommended structure<br>" + esc((res.ideal && res.ideal.title) || "") + "</th><th>Your selection</th></tr></thead><tbody>" + rows + "</tbody></table>" +
        (ways ? "<h3>Ways to improve</h3><ol>" + ways + "</ol>" : "") +
        "<p class='muted'>" + esc((res.trust && res.trust.line) || "") + "</p>" +
        "<p class='fine'>" + esc(ESTIMATE_LINE) + " Ranges show what is likely, not a promise. The recommended structure is HelloVoice’s proposal for this campaign type. " +
        "Powered by HelloVoice · A BlueHolding Company.</p><script>window.onload=function(){setTimeout(function(){window.print()},300)}<\/script></body></html>";
      w.document.open(); w.document.write(html); w.document.close();
    }

    /* -- the drawer inside a selection: seeded from the estimate saved with it, if any -- */
    function mixSentence(mix) {
      var W = { mega: "mega", macro: "macro", mid: "mid-size", micro: "micro", nano: "nano" }, out = [];
      Object.keys(mix || {}).forEach(function (p) {
        var bits = ["mega", "macro", "mid", "micro", "nano"].filter(function (t) { return mix[p][t]; }).map(function (t) { return mix[p][t] + " " + W[t]; });
        if (bits.length) out.push(bits.join(", ") + " on " + p);
      });
      return out.join("; ");
    }
    function buildDrawer(S, state, pool, approved, prev) {
      var scrim = h("div", { class: "cx-dr__scrim" });
      var dr = h("aside", { class: "cx-dr", role: "dialog", "aria-modal": "true", "aria-labelledby": "cx-roi-t" });
      var x = h("button", { class: "cx-x", type: "button", "aria-label": "Close the ROI Calculator", html: ic("x") });
      dr.appendChild(h("header", { class: "cx-dr__hd" }, h("h2", { id: "cx-roi-t" }, "ROI Calculator", h("small", null, S.name())),
        h("span", { class: "cx-tag cx-tag--est", html: ic("info") + "Estimate" }), x));
      var body = h("div", { class: "cx-dr__body" });
      var outBox = h("div");
      var last = null, platBox = null, mixNote = h("p", { class: "cx-fine cx-mixnote", hidden: true });
      function request() {
        var b = { goal: state.goals[0], goals: state.goals, platforms: state.platforms };
        if (state.count) b.count = state.count;
        if (state.second && state.second.length) b.second_posts = state.second;
        if (state.src === "mix") b.mix = state.mixP || state.mix; else { b.token = S.token(); b.which = state.which; }
        return b;
      }
      function way(a) {
        if (!a) return;
        if (a.type === "remove") {
          var n = S.remove ? S.remove(a.codes) : 0;
          toast(n ? "Removed " + n + " creator" + (n === 1 ? "" : "s") + " from " + S.name() + "." : "Those creators could not be removed.");
        } else if (a.type === "replace") {
          if (S.remove) S.remove(a.remove);
          state.which = "all";
          S.add(a.add);
          toast("Swapped in " + S.name() + "; the new creator is under review.");
        } else if (a.type === "add") {
          state.which = "all";                                           // the new ones are under review: count them
          S.add(a.codes);
          toast("Added to " + S.name() + ", under review.");
        } else if (a.type === "second_post") {
          state.second = (state.second || []).concat(a.codes.filter(function (c) { return (state.second || []).indexOf(c) === -1; }));
          toast("Counted a second post for " + a.codes.length + " creator" + (a.codes.length === 1 ? "" : "s") + " in this estimate.");
        } else if (a.type === "add_platform") {
          if (state.platforms.indexOf(a.platform) === -1) state.platforms.push(a.platform);
          state.mixP = null;
          if (platBox) platBox.sync();
        } else if (a.type === "use_mix") {
          state.mixP = a.mix;
          mixNote.hidden = false; mixNote.textContent = "Suggested mix: " + mixSentence(a.mix) + ".";
          state.platforms = Object.keys(a.mix);
          if (platBox) platBox.sync();
        }
        run(true);
      }
      var run = debounce(function () {
        outBox.classList.add("cx-busy");
        estimate(request()).then(function (res) {
          outBox.classList.remove("cx-busy");
          if (res) { outBox.textContent = ""; outBox.appendChild(resultPanel(res, { onWay: way })); last = res; countB.setFrom(res); }
        });
      }, 260);
      var mixWrap = h("div", { hidden: true }, mixBox(state, run), mixNote);
      var faces = h("span", { class: "cx-faces" });
      pool.slice(0, 6).forEach(function (c) { var cr = S.creator(c); faces.appendChild(h("span", { class: "cx-ph" }, initials(cr ? cr.name : c))); });
      var srcBox = h("div", { class: "cx-src" },
        h("label", null, h("input", { type: "radio", name: "cx-src", checked: true, onchange: function () { state.src = "sel"; mixWrap.hidden = true; run(); } }),
          h("span", null, h("b", null, approved.length ? "This selection’s " + approved.length + " approved creator" + (approved.length === 1 ? "" : "s") : "This selection’s " + pool.length + " creators"),
            h("small", null, "Uses their own numbers. 1 post per creator per platform."), faces)),
        h("label", null, h("input", { type: "radio", name: "cx-src", onchange: function () { state.src = "mix"; mixWrap.hidden = false; run(); } }),
          h("span", null, h("b", null, "A mix of sizes instead"), h("small", null, "Try a different mix of creator sizes before you choose."))));
      platBox = platToggles(state, run);
      var countB = countBox(state, run);
      body.appendChild(h("div", { class: "cx-inp" },
        state.seeded ? h("p", { class: "cx-fine", style: "margin:0" }, "Pre-filled from this selection’s brief; change anything.") : null,
        q("Campaign type", seg(state, "goal", run), h("em", null, "pick one or more")), q("Platforms", platBox), q("Creators", h("div", { class: "cx-src" }, srcBox, mixWrap)), q("How many creators?", countB)));
      body.appendChild(outBox);
      dr.appendChild(body);
      var saveB = h("button", { class: "cx-btn", type: "button", html: ic("save") + "<span>Save to selection</span>" });
      var pdfB = h("button", { class: "cx-btn cx-btn--line", type: "button", html: ic("dl") + "<span>Download PDF</span>" });
      // Colleagues can run the estimate and download it; saving it to the selection is the owner's.
      var mayEditSel = !S.role || ["owner", "admin"].indexOf(S.role()) > -1;
      dr.appendChild(h("footer", { class: "cx-dr__ft" }, mayEditSel ? saveB : document.createTextNode(""), pdfB));
      saveB.addEventListener("click", function () {
        var b = request();
        b.token = S.token();
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
    var ROI_LOCKED = true;
    window.hvRoiLocked = ROI_LOCKED;
    function roiForSelection() {
      var S = window.hvSelection;
      if (!S || !S.token()) return;
      var prev = document.activeElement;
      api("GET", "/api/roi/saved?s=" + encodeURIComponent(S.token())).then(function (r) {
        var sv = r.b && r.b.saved && r.b.saved.input;
        // No estimate saved yet: start from the brief that built or scored this selection (fix batch 5).
        var seeded = !sv && r.b && r.b.seed;
        if (seeded) sv = r.b.seed;
        var approved = S.codes().filter(function (c) { return S.status(c).s === "approved"; });
        var pool = approved.length ? approved : S.codes().filter(function (c) { var s = S.status(c).s; return s !== "rejected" && s !== "unavailable"; });
        var goals = (sv && sv.goals && sv.goals.length ? sv.goals : sv && sv.goal ? [sv.goal] : ["awareness"]).filter(function (g) { return g !== "conversion"; });
        var state = { goals: goals.length ? goals : ["traffic"], goal: (goals[0] || "traffic"), count: (sv && Number(sv.count)) || 0,
                      platforms: (sv && sv.platforms && sv.platforms.length ? sv.platforms : ["Instagram", "TikTok"]).slice(),
                      mix: { mid: 2, micro: 6 }, mixP: null, second: [], which: "approved", src: "sel", seeded: !!seeded };
        buildDrawer(S, state, pool, approved, prev);
      });
    }
    HV.openRoi = roiForSelection;

    /* -- the compact card in Helvi's chat -- */
    HV.roiCard = function (res) {
      var card = h("div", { class: "hv-msg hv-msg--ai cx-rcard" });
      var head = h("div", { class: "cx-rcard__hd" });
      var body = h("div");
      var cur = res;
      var state = { count: res.ideal_only ? (res.count || 0) : 0, goals: res.goals || [res.goal], platforms: res.platforms || ["Instagram"] };
      var cb = null;
      function render(r) {
        cur = r;
        head.textContent = "";
        head.appendChild(h("b", { html: ic("calc") + "ROI Calculator" }));
        if (r.quality) head.appendChild(qualityChip(r.quality));
        head.appendChild(h("span", { class: "cx-tag cx-tag--est" }, "Estimate"));
        body.textContent = "";
        var I = r.ideal || {};
        body.appendChild(h("p", { class: "cx-rcard__lead" }, r.ideal_only ? (I.title || r.summary || "") : (r.summary || "")));
        var dl = h("dl", { class: "cx-figs" });
        var figs = r.ideal_only ? (I.figures || r.figures || []) : (r.figures || []);
        figs.filter(function (f) { return ["cpm", "cpe", "cpc", "frequency", "reach", "er"].indexOf(f.key) === -1; }).slice(0, 4).forEach(function (f) {
          var n = h("span", { class: "cx-n" }, h("span", { class: "cx-v" }, fig(f)));
          dl.appendChild(h("div", null, h("dt", null, (r.ideal_only ? "Recommended " : "") + f.label.toLowerCase()), h("dd", null, n)));
        });
        body.appendChild(dl);
        var gap = (r.gap || []).slice(0, 2).join("; ");
        var top = r.ways && r.ways[0];
        if (r.quality && r.compare_line) body.appendChild(h("p", { class: "cx-rcard__plan" }, r.compare_line));
        if (r.quality && gap) body.appendChild(h("p", { class: "cx-rcard__plan" }, h("b", null, "Gap: "), gap + "."));
        if (top) body.appendChild(h("p", { class: "cx-rcard__plan" }, h("b", null, "Best next step: "), top.text));
        if (r.ideal_only) {
          var mix = r.mix || I.mix;
          var txt = mixSentence(mix);
          if (txt) body.appendChild(h("p", { class: "cx-rcard__plan" }, "HelloVoice’s recommended structure: " + txt + "."));
        }
        if (cb) cb.setFrom(r);
      }
      if (res.ideal_only) {
        cb = countBox(state, function () {
          card.classList.add("cx-busy");
          estimate({ goals: state.goals, goal: state.goals[0], platforms: state.platforms, count: state.count || undefined }).then(function (r) {
            card.classList.remove("cx-busy");
            if (!r) return;
            r.ideal_only = true; r.mix = r.ideal && r.ideal.mix;
            render(r);
          });
        });
      }
      card.appendChild(head);
      if (cb) { card.appendChild(h("p", { class: "cx-rcard__q" }, "How many creators?")); card.appendChild(cb); }
      card.appendChild(body);
      render(res);
      var open = h("button", { class: "cx-btn", type: "button" }, "Open calculator");
      open.addEventListener("click", function () {
        try { sessionStorage.setItem("cx-roi-seed", JSON.stringify({ goal: cur.goal, goals: cur.goals || [cur.goal], platforms: cur.platforms, mix: cur.ideal_only ? null : (cur.mix || null), count: cur.count || 0 })); } catch (e) { /* blocked */ }
        if (PAGE === "selection" && window.hvSelection && window.hvSelection.token()) roiForSelection(); else location.href = ROOT + "account/#roi";
      });
      card.appendChild(h("div", { class: "cx-rcard__go" }, open));
      card.appendChild(h("p", { class: "cx-rcard__fine" }, ESTIMATE_LINE + " For creator prices, your account manager prepares a quote."));
      return card;
    };

    /* -- estimate vs actual: the saved RANGE against what happened -- */
    function versusBlock(v, withLink) {
      var box = h("section", { class: "cx-eva", "aria-label": "Estimate vs actual" });
      var when = new Date(v.saved_at * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
      box.appendChild(h("div", { class: "cx-eva__hd" },
        h("div", null, h("h2", null, v.campaign + " · estimate vs actual"), h("p", null, "Saved estimate from " + when + " against the live report." + (v.ended ? " Campaign ended." : " Campaign running."))),
        withLink ? h("a", { href: ROOT + "campaign/#t=" + encodeURIComponent(v.token) }, "Open the report") : null));
      var rows = h("div", { class: "cx-eva__rows" });
      (v.rows || []).filter(function (r) { return r.key !== "er" && r.key !== "reach"; }).forEach(function (r) {
        var rng = r.range && r.range.length === 2 ? r.range : [r.estimate * 0.8, r.estimate * 1.2];
        var mx = Math.max(rng[1], r.actual) * 1.05 || 1;
        var track = h("i", { class: "cx-eva__track", role: "img", "aria-label": "Estimated range " + big(rng[0]) + " to " + big(rng[1]) + ", actual " + big(r.actual) });
        var band = h("em", { class: "cx-eva__band" }); band.style.left = (rng[0] / mx * 100) + "%"; band.style.width = ((rng[1] - rng[0]) / mx * 100) + "%";
        var dot = h("u", { class: "cx-eva__dot" }); dot.style.left = (r.actual / mx * 100) + "%";
        track.appendChild(band); track.appendChild(dot);
        rows.appendChild(h("div", { class: "cx-eva__row" }, h("b", null, r.label),
          h("div", { class: "cx-eva__bars" },
            h("span", { class: "cx-e" }, "Estimated", h("strong", null, big(rng[0]) + "–" + big(rng[1]))),
            track,
            h("span", { class: "cx-a" }, "Actual", h("strong", null, big(r.actual)))),
          r.sig ? h("span", { class: "cx-sig cx-sig--" + r.sig.grade }, r.sig.label) : null));
      });
      box.appendChild(rows);
      if (v.helvy) {
        var face = h("span", { class: "cx-hd" }); face.appendChild(h("img", { class: "hv-clip", src: HV.helvy, alt: "" }));
        box.appendChild(h("div", { class: "cx-advice" }, face, h("p", { class: "cx-advice__b" }, h("b", null, "Helvi"), v.helvy)));
      }
      return box;
    }

    /* -- the profile page section (account.js calls this for #roi) -- */
    HV.roiPage = function (p) {
      var seed = null;
      try { seed = JSON.parse(sessionStorage.getItem("cx-roi-seed") || "null"); sessionStorage.removeItem("cx-roi-seed"); } catch (e) { seed = null; }
      var flatSeed = seed && seed.mix && Object.keys(seed.mix).every(function (k) { return typeof seed.mix[k] !== "object"; });
      var goals = (seed && seed.goals && seed.goals.length ? seed.goals : seed && seed.goal ? [seed.goal] : ["engagement"]).filter(function (g) { return g !== "conversion"; });
      var state = { goals: goals.length ? goals : ["traffic"], goal: goals[0] || "traffic",
                    platforms: (seed && seed.platforms) || ["Instagram", "TikTok"], mix: (flatSeed && seed.mix) || { macro: 1, mid: 3, micro: 6 },
                    mixP: seed && seed.mix && !flatSeed ? seed.mix : null, second: [], count: (seed && Number(seed.count)) || 0 };
      p.appendChild(h("h1", { class: "cx-roipg__h1" }, "ROI Calculator"));
      p.appendChild(h("p", { class: "cx-roipg__lead" }, "Try a mix of creator sizes before you brief HelloVoice and see how it compares with HelloVoice’s recommended structure for the same number of creators: views, interactions and tracking-link clicks, as honest ranges."));
      var outBox = h("div"), last = null, platBox = null;
      function way(a) {
        if (!a) return;
        if (a.type === "use_mix") { state.mixP = a.mix; state.platforms = Object.keys(a.mix); if (platBox) platBox.sync(); }
        run();
      }
      var run = debounce(function () {
        outBox.classList.add("cx-busy");
        estimate({ goal: state.goals[0], goals: state.goals, platforms: state.platforms, mix: state.mixP || state.mix, count: state.count || undefined }).then(function (res) {
          outBox.classList.remove("cx-busy"); if (!res) return; last = res; countB.setFrom(res); outBox.textContent = ""; outBox.appendChild(resultPanel(res, { onWay: way })); outBox.appendChild(acts);
        });
      }, 260);
      var useSel = h("button", { type: "button", class: "cx-link" }, "use a selection");
      platBox = platToggles(state, run);
      var countB = countBox(state, run);
      var inBox = h("div", { class: "cx-roipg__in" }, h("div", { class: "cx-inp" },
        q("Campaign type", seg(state, "goal", run), h("em", null, "pick one or more")), q("Platforms", platBox),
        q("Creators", mixBox(state, run), h("em", null, "or ", useSel)), q("How many creators?", countB)));
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
        api("POST", "/api/roi/save", { token: pick.value, goal: state.goals[0], goals: state.goals, platforms: state.platforms, mix: state.mixP || state.mix, count: state.count || undefined })
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
      mountLifecycle();
      var S = window.hvSelection;
      if (!S || !S.token() || document.getElementById("cx-selact")) return;
      // Bottom row of the selection header, pushed to its right end (CSS), a lime primary button.
      var foot = document.querySelector(".cat-selhead__foot") || document.querySelector(".cat-selhead");
      if (foot) {
        // ROI_LOCKED: the calculator is switched off for now (Bido, 2026-10-12) until it is fixed. Set false to bring it back.
        var b = h("button", { class: "cx-btn cx-btn--roi" + (ROI_LOCKED ? " is-locked" : ""), type: "button",
                              html: ic(ROI_LOCKED ? "lock" : "calc") + "<span>ROI Calculator</span>" + (ROI_LOCKED ? "<small>Coming soon</small>" : ""),
                              onclick: ROI_LOCKED ? null : roiForSelection });
        if (ROI_LOCKED) { b.setAttribute("aria-disabled", "true"); b.title = "Coming soon: the ROI Calculator is being improved."; }
        foot.appendChild(h("div", { class: "cx-selact", id: "cx-selact" }, b));
      }
      var role = S.role();
      var grid = document.querySelector(".cat-grid-section");
      if (role !== "owner" && role !== "admin") {
        // A colleague (same company) or a link holder: the AI tools belong to the owner, so say so
        // and offer a copy they own, instead of a card that is simply missing.
        if (grid && !document.getElementById("cx-viewer")) {
          var tries0 = 0;
          (function placeNote() {
            if (!document.getElementById("sel-statusbar") && tries0++ < 30) { setTimeout(placeNote, 150); return; }
            if (!document.getElementById("cx-viewer")) grid.parentNode.insertBefore(viewerNote(S), grid);
          })();
        }
        return;
      }
      if (!grid) return;
      var tries = 0;
      (function place() {
        if (!document.getElementById("sel-statusbar") && tries++ < 30) { setTimeout(place, 150); return; }
        grid.parentNode.insertBefore(moreCard(S), grid);
      })();
    }
    // What a colleague sees where the owner's AI card sits.
    function viewerNote(S) {
      var cur = S.curated() || {};
      var owner = (cur.owner || "").trim();
      var who = owner ? h("b", null, owner) : document.createTextNode("the person who made it");
      var msg = h("p", { class: "cx-viewer__msg" }, who, " owns this selection. Only they can add more creators, score it with an objective or request its quote. You can look at everything here.");
      var go = h("button", { class: "cx-btn", type: "button", html: ic("save") + "<span>Make my own copy</span>" });
      var note = h("p", { class: "cx-viewer__note", "aria-live": "polite" }, "A copy is yours to score, add to and quote. Your colleague’s selection stays as it is.");
      go.addEventListener("click", function () {
        go.disabled = true;
        var name = ("Copy of " + (S.name() || "selection")).slice(0, 120);
        api("POST", "/api/selection", { name: name, codes: S.codes() }).then(function (r) {
          if (r.b && r.b.ok && r.b.token) { location.href = ROOT + "selection/#s=" + encodeURIComponent(r.b.token); location.reload(); return; }
          go.disabled = false; note.textContent = "Couldn’t make the copy just now. Try again in a moment.";
        });
      });
      var card = h("div", { class: "cx-viewer" }, h("div", { class: "cx-viewer__tx" }, h("h2", null, "Viewing a colleague’s selection"), msg, note), go);
      return h("section", { class: "cx-moresec", id: "cx-viewer" }, h("div", { class: "cat-pad" }, h("div", { class: "cat-container" }, card)));
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
      from.appendChild(h("span", null, approved.length ? "Based on your " + approved.length + " approved creator" + (approved.length === 1 ? "" : "s") : "Approve a few creators first, so Helvi knows what you like"));
      // Helvi on his lime disc (fix batch 4), the AI shortlist card's clips: an easy loop at rest,
      // a thumbs-up when a quick pick is tapped, the camera scan while he works, a cheer when the
      // creators land.
      var face = HV.lime ? HV.lime("loop", "cx-more__face") : clip("idle");
      card.appendChild(face);
      card.appendChild(h("div", null, h("h2", { id: "cx-more-t" }, "Add more like these", costTag(cur.moreCost)),
        h("p", null, "Helvi studies the creators you approved, their audience, tone and platforms, and adds more that match to ", h("b", null, "Under review"), " for you to decide."), from));
      var note = h("input", { class: "cx-briefin", type: "text", maxlength: "160", placeholder: "Anything to add? e.g. Jeddah-based, Arabic-first", "aria-label": "Anything to add for Helvi" });
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
        // While Helvi works: the director's desk (thinking -> cards -> approve) and the step line.
        var seeds = S.codes().filter(function (c) { return S.status(c).s === "approved"; }).length;
        if (face.loop) face.loop("scan");
        var cook = HV.cooking ? HV.cooking({ dark: true, list: true, helvy: !face.loop, title: "Helvi is finding " + count + " more",
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
          if (!r.b || !r.b.ok) { if (face.loop) face.loop("think"); msg.textContent = (r.b && r.b.message) || "Helvi couldn’t look just now. Please try again."; return; }
          var codes = (r.b.added || []).map(function (c) { return c.code; });
          if (!codes.length) { if (face.loop) face.loop("think"); msg.textContent = r.b.message || "Helvi found no one close enough."; return; }
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

    /* -- One side panel for Helvi's suggestions on a selection: "Creators like this" and, since
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
      // Looking again asks Helvi's AI again, so the button says what it costs (or that it is free).
      var free = aiFree() || !o.cost;
      var more = h("button", { class: "cx-btn cx-btn--ink cx-more-btn", type: "button", html: ic("sparkle") + "<span>Show 3 more</span>" });
      more.appendChild(h("span", { class: "hv-cost" + (free ? " hv-cost--free" : ""), html: free ? "Free" : ic("coin") + o.cost + " credit" + (o.cost === 1 ? "" : "s") }));
      sheet.appendChild(h("footer", { class: "cx-sheet__ft" },
        h("div", { class: "cx-sheet__fn" },
          h("span", null, "Added creators join as ", h("b", null, "Under review"), o.foot || ". HelloVoice confirms availability."),
          h("small", null, free ? "Looking again is free with your active campaign." : "Looking again uses Helvi’s AI: " + o.cost + " credit" + (o.cost === 1 ? "" : "s") + ".")),
        more));
      function close() { scrim.remove(); sheet.remove(); document.removeEventListener("keydown", onKey); document.body.classList.remove("pt-lock"); if (prev && prev.focus && prev.isConnected) prev.focus(); }
      function onKey(e) { if (e.key === "Escape") close(); }
      x.addEventListener("click", close); scrim.addEventListener("click", close); document.addEventListener("keydown", onKey);
      document.body.appendChild(scrim); document.body.appendChild(sheet); document.body.classList.add("pt-lock"); x.focus();
      function load(againFlag) {
        list.textContent = "";
        var cook = HV.cooking ? HV.cooking({ steps: o.steps }) : h("div", { class: "cx-sheet__empty" }, "Helvi is looking…");
        list.appendChild(h("div", { class: "cx-sheet__empty cx-sheet__cook" }, cook));
        more.disabled = true;
        o.fetch(!!againFlag).then(function (r) {
          if (cook.stop) cook.stop();
          list.textContent = "";
          more.disabled = false;
          if (!r.b || !r.b.ok) { list.appendChild(h("div", { class: "cx-sheet__empty" }, (r.b && r.b.message) || "Helvi couldn’t look just now.")); return; }
          if (r.b.credits != null && HV.setCredits) HV.setCredits(r.b.credits);
          var found = o.pick(r.b) || [];
          if (o.loaded) o.loaded(found, r.b);
          if (!found.length) { list.appendChild(h("div", { class: "cx-sheet__empty" }, r.b.message || "Helvi found no one else close enough.")); more.disabled = true; return; }
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
    // Find a replacement: the same panel. Helvi's three are kept on the rejected creator, so
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
       On a selection card and on the creator's page: Helvi drafts 2-3 hooks and concepts,
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
      // Before the campaign starts: a lock and one dummy example of what Helvi will write.
      function lockedView(sample) {
        list.textContent = ""; ctxRow.textContent = ""; again.hidden = true;
        list.appendChild(h("div", { class: "cx-ideas__lock" },
          h("span", { class: "cx-ideas__lockic", html: ic("lock") }),
          h("div", null, h("b", null, "Content ideas unlock when your campaign starts"),
            h("p", null, "They open once your quote is released and approved and HelloVoice sets the campaign live. Until then, this is an example of what Helvi writes for each creator."))));
        sample.forEach(function (it) {
          list.appendChild(h("article", { class: "cx-idea cx-idea--sample" },
            h("div", { class: "cx-idea__top" }, h("span", { class: "cx-idea__n" }, "Example"), h("span", { class: "cx-idea__fmt" }, it.format)),
            h("div", { class: "cx-idea__cols" },
              h("div", { class: "cx-idea__en", lang: "en" }, h("p", { class: "cx-idea__hook" }, "“" + it.hook_en + "”"), h("p", { class: "cx-idea__con" }, it.concept_en)),
              h("div", { class: "cx-idea__ar", lang: "ar", dir: "rtl" }, h("p", { class: "cx-idea__hook" }, it.hook_ar), h("p", { class: "cx-idea__con" }, it.concept_ar)))));
        });
      }
      function intro() {
        list.textContent = "";
        var write = h("button", { class: "cx-btn", type: "button", html: ic("bulb") + "<span>Write ideas</span>" });
        write.addEventListener("click", function () { generate(false); });
        list.appendChild(h("div", { class: "cx-ideas__intro" },
          h("p", null, h("b", null, "Three ideas, in English and Arabic. "), "Helvi reads " + name + "’s platforms, interests and audience size" +
            " (their best posts too, once the full analysis is unlocked) and writes a hook and a concept for each."), write));
      }
      function generate(isAgain) {
        again.disabled = true;
        list.textContent = "";
        var cook = HV.cooking ? HV.cooking({ steps: ["Reading " + name + "’s style…", "Reading the brief…", "Writing hooks in English and Arabic…", "Checking: no prices, no claims…"] }) : null;
        list.appendChild(h("div", { class: "cx-sheet__empty cx-sheet__cook" }, cook || "Helvi is writing…"));
        api("POST", "/api/ideas", { code: code, token: token || undefined, again: !!isAgain }).then(function (r) {
          if (cook && cook.stop) cook.stop();
          again.disabled = false;
          if (r.b && r.b.credits != null && HV.setCredits) HV.setCredits(r.b.credits);
          if (!r.b || !r.b.ok) { list.textContent = ""; list.appendChild(h("div", { class: "cx-sheet__empty" }, (r.b && r.b.message) || "Helvi couldn’t write just now. You weren’t charged.")); if (!isAgain) again.hidden = true; return; }
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
          if (r.b.locked) { lockedView(r.b.sample || []); return; }
          setCtx(r.b);
          if (r.b.selection && !token) token = r.b.selection.token;
          if (!r.b.ai && !(r.b.ideas || []).length) { list.textContent = ""; list.appendChild(h("div", { class: "cx-sheet__empty" }, "Helvi can’t write ideas right now. Please try again later.")); return; }
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
        if (!fields || !m || fields.querySelector(".cx-ideabtn") || /[#&]sample=1\b/.test(location.hash || "")) return;   // none on the sample analysis
        var nm = fields.querySelector(".pp-name");
        var b = h("button", { class: "cx-btn cx-btn--line cx-ideabtn", type: "button", "data-ideas": decodeURIComponent(m[1]).toUpperCase(),
                              "data-name": nm ? nm.textContent.trim() : "", html: ic("lock") + "<span>Content ideas</span>" });
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

    /* ================================================== quote lifecycle (fix batch 9, #42)
     * One chip says where a selection stands: Draft, Quote requested, Quote ready, Approved,
     * Campaign live, Completed. On the selection page it sits in the header and opens into a small
     * timeline with dates and who did it. The owner approves a ready quote here; colleagues look.
     * The server decides everything (/api/selection -> lifecycle); this only draws it. */
    // portal.js's h() takes children one by one; the timeline passes lists, so flatten here.
    function lh(tag, props) {
      var el = h(tag, props), kids = [].slice.call(arguments, 2);
      (function put(list) {
        list.forEach(function (x) {
          if (x == null || x === false) return;
          if (Array.isArray(x)) { put(x); return; }
          el.appendChild(typeof x === "string" || typeof x === "number" ? document.createTextNode(String(x)) : x);
        });
      })(kids);
      return el;
    }
    function lcDay(ts) {
      if (!ts) return "";
      var d = new Date(ts * 1000), y = new Date().getFullYear() !== d.getFullYear();
      return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: y ? "numeric" : undefined });
    }
    function lcChip(lc, extra) {
      if (!lc || !lc.key) return null;
      return lh("span", { class: "lc-chip lc-chip--" + lc.key + (extra ? " " + extra : ""), title: lc.hint || "" },
        lh("i", { "aria-hidden": "true" }), lc.label);
    }
    HV.lifecycleChip = lcChip;
    var lcBound = false;
    function lcRender(cur) {
      var lc = cur.lifecycle, S = window.hvSelection;
      var old = document.getElementById("cx-lc"), oldChip = document.getElementById("cx-lc-chip");
      if (oldChip) oldChip.remove();
      if (!lc) { if (old) old.remove(); return; }
      // The chip sits under the selection's title, in the header (both header builds: the cover
      // header's .cat-selhead__lock and the older .cat-hero__head).
      var title = document.getElementById("sel-title"), host = title && title.parentNode;
      if (host) {
        var chip = lcChip(lc, "lc-chip--hero"); chip.id = "cx-lc-chip";
        host.appendChild(chip);
      }
      var steps = lh("ol", { class: "cx-lc__steps", "aria-label": "Quote progress" }, lc.steps.map(function (st) {
        var who = [lcDay(st.at), st.at && st.by ? st.by : ""].filter(Boolean).join(" · ");
        return lh("li", { class: "is-" + st.state, "aria-current": st.state === "current" ? "step" : null },
          lh("span", { class: "cx-lc__dot", "aria-hidden": "true" }),
          lh("b", null, st.label),
          lh("small", null, who || (st.state === "current" ? "Now" : "")));
      }));
      // The timeline stays folded: the status tag says where the selection is, and the dated steps
      // open on demand (Bido, 2026-10-11: no timeline open on every selection).
      var tl = lh("div", { class: "cx-lc__tl", id: "cx-lc-tl", hidden: "" }, steps);
      var tg = lh("button", { type: "button", class: "cx-lc__tg", "aria-expanded": "false", "aria-controls": "cx-lc-tl" }, "Show timeline");
      tg.addEventListener("click", function () {
        var open = tl.hasAttribute("hidden");
        if (open) tl.removeAttribute("hidden"); else tl.setAttribute("hidden", "");
        tg.setAttribute("aria-expanded", open ? "true" : "false");
        tg.textContent = open ? "Hide timeline" : "Show timeline";
      });
      var kids = [lh("div", { class: "cx-lc__top" }, lh("h2", { class: "cx-lc__t" }, "Quote status"), lcChip(lc)),
                  lh("p", { class: "cx-lc__hint" }, lc.hint), tg, tl];
      if (lc.note || lc.link) {
        kids.push(lh("div", { class: "cx-lc__note" },
          lh("b", null, "From your account manager"),
          lc.note ? lh("p", null, lc.note) : null,
          lc.link ? lh("a", { class: "cx-btn cx-btn--line cx-lc__open", href: lc.link, target: "_blank", rel: "noopener noreferrer" }, icEl("arrow"), "Open the quote") : null));
      }
      if (lc.can_approve) {
        var box = lh("div", { class: "cx-lc__act" });
        var ask = function () {
          box.textContent = "";
          var yes = lh("button", { type: "button", class: "cx-btn" }, "Yes, approve");
          var no = lh("button", { type: "button", class: "cx-btn cx-btn--line" }, "Not yet");
          box.appendChild(lh("p", { class: "cx-lc__ask", role: "alert" }, "Approve this quote? Your account manager is told and sets up the campaign."));
          box.appendChild(yes); box.appendChild(no);
          yes.focus({ preventScroll: true });
          no.addEventListener("click", rest);
          yes.addEventListener("click", function () {
            yes.disabled = no.disabled = true;
            api("POST", "/api/selection/quote/approve", { token: cur.token }).then(function (r) {
              if (r.b && r.b.ok) { cur.lifecycle = r.b.lifecycle; toast("Quote approved. HelloVoice is setting up the campaign."); lcRender(cur); return; }
              yes.disabled = no.disabled = false;
              toast((r.b && r.b.message) || "Couldn't approve it. Please try again.");
            });
          });
        };
        var rest = function () {
          box.textContent = "";
          var b = lh("button", { type: "button", class: "cx-btn" }, icEl("check"), "Approve quote");
          b.addEventListener("click", ask);
          box.appendChild(b);
        };
        rest();
        kids.push(box);
      } else if (lc.key === "draft" && lc.role === "owner" && document.getElementById("cat-request")) {
        var rq = lh("button", { type: "button", class: "cx-btn cx-btn--line" }, "Request a quote");
        rq.addEventListener("click", function () { document.getElementById("cat-request").click(); });
        kids.push(lh("div", { class: "cx-lc__act" }, rq));
      }
      if (lc.warn) {
        kids.push(lh("p", { class: "cx-lc__warn" }, icEl("info"), lh("span", null, lh("b", null, lc.warn + ". "),
          "You can keep changing creators; your account manager is told.")));
      }
      if (lc.changes && lc.changes.length) {
        kids.push(lh("ul", { class: "cx-lc__chg" }, lc.changes.map(function (c) {
          var bits = [c.added ? "+" + c.added + " added" : "", c.removed ? c.removed + " removed" : ""].filter(Boolean).join(", ");
          return lh("li", null, (c.by || "The creators") + " changed the creators on " + lcDay(c.at) + (bits ? " (" + bits + ")" : ""));
        })));
      }
      // From the selection straight into its campaign's dashboard (owner, 2026-10-15); the full report is
      // one click away, here and on the dashboard's own "Full report" button.
      if (lc.campaign && (lc.key === "live" || lc.key === "completed")) {
        var ct = encodeURIComponent(lc.campaign.token);
        kids.push(lh("div", { class: "cx-lc__go" },
          lh("a", { class: "cx-btn", href: ROOT + "campaign/dashboard/#t=" + ct }, icEl("arrow"), lc.key === "live" ? "Open the campaign dashboard" : "Open the final dashboard"),
          lh("a", { class: "cx-btn cx-btn--line", href: ROOT + "campaign/#t=" + ct }, lc.key === "live" ? "Full report" : "Final report")));
      }
      if (lc.role === "viewer") kids.push(lh("p", { class: "cx-lc__ro" }, "You can follow this. " + (lc.owner || "The owner") + " requests and approves the quote."));
      // The card only appears when it has something to do or say (approve, the account manager's note
      // or link, a changes warning, the campaign report). Draft and a plain "quote requested" show
      // just the status tag in the header (Bido, 2026-10-11: remove this section from the selection page).
      var actionable = false;          // Bido, 2026-10-16: the "Quote status" section is gone from the selection page for everyone
      if (!actionable) { if (old) old.remove(); return; }
      var sec = lh("section", { id: "cx-lc", class: "cx-lc cx-lc--" + lc.key, "aria-label": "Quote status" },
        lh("div", { class: "cat-pad" }, lh("div", { class: "cat-container" }, lh("div", { class: "cx-lc__card" }, kids))));
      if (old) { old.replaceWith(sec); return; }
      var anchor = document.querySelector(".cat-summary");
      if (anchor) anchor.insertAdjacentElement("afterend", sec);
    }
    function mountLifecycle() {
      var S = window.hvSelection, cur = S && S.curated && S.curated();
      if (!cur || !cur.token) return;
      lcRender(cur);
      if (lcBound) return;
      lcBound = true;
      // A save that touched a live quote: the server says so; show the new timeline and tell them once.
      window.addEventListener("hv:selection-saved", function (ev) {
        var d = ev.detail || {}, c = S.curated && S.curated();
        if (!c || !d.lifecycle) return;
        c.lifecycle = d.lifecycle;
        lcRender(c);
        if (d.lifecycle.warn) toast(d.lifecycle.warn + ". Your account manager has been told.");
      });
    }

    /* ================================================================ boot */
    function onMe() {
      if (started) return;
      started = true;
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
