/* Competitor evidence on the selection page (admin/evidence.py → GET /api/evidence?s=<token>).
 * Shown only when HelloVoice shared a pack on this selection: which creators already worked with
 * the brand's competitors, and how each post performed, every number linked to the post itself.
 * Everything is drawn with textContent; nothing from the server is parsed as HTML. */
(function () {
  "use strict";
  var CFG = window.CATALOGUE_CONFIG || {};
  var sec = document.getElementById("sel-evidence");
  var root = document.getElementById("ev-root");
  if (!sec || !root) return;
  var data = null, brandIx = 0, loadedFor = null;

  function token() {
    var m = /(?:^|[#&])s=([A-Za-z0-9_-]+)/.exec(location.hash || "");
    return m ? m[1] : "";
  }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function num(v) {
    if (v == null) return "—";
    if (v >= 1e6) return (v / 1e6).toFixed(1) + "M";
    if (v >= 1e4) return Math.round(v / 1e3) + "K";
    if (v >= 1e3) return (v / 1e3).toFixed(1) + "K";
    return String(Math.round(v));
  }
  function pct(v, hidden) { return v == null ? (hidden ? "Likes hidden" : "—") : (v * 100).toFixed(1) + "%"; }
  function link(href, text) {
    var a = el("a", "ev-link", text);
    if (/^https:\/\//.test(href || "")) { a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer"; }
    return a;
  }
  function table(head, rows) {
    var wrap = el("div", "ev-wrap"), t = el("table", "ev-t"), tr = el("tr");
    head.forEach(function (h) { var th = el("th", h.n ? "n" : "", h.t); tr.appendChild(th); });
    t.appendChild(tr);
    rows.forEach(function (r) {
      var row = el("tr");
      r.forEach(function (c, i) {
        var td = el("td", head[i].n ? "n" : "");
        if (c instanceof Node) td.appendChild(c); else td.textContent = c == null ? "" : c;
        row.appendChild(td);
      });
      t.appendChild(row);
    });
    wrap.appendChild(t);
    return wrap;
  }

  function draw() {
    root.textContent = "";
    var ev = data;
    var head = el("div", "ev-head");
    head.appendChild(el("p", "ev-eyebrow", ev.preview ? "Competitor evidence · preview (not shared with the client yet)" : "Competitor evidence"));
    var h = el("h2", "ev-title", "Who already works with your competitors"); h.id = "ev-title";
    head.appendChild(h);
    head.appendChild(el("p", "ev-lede", "Every collaboration post we found between creators and your competitors, with its real numbers. " +
      "Medians leave out paid-boosted posts (very high views with almost no engagement). Engagement = (likes + comments) ÷ views."));
    root.appendChild(head);

    if (ev.brands.length > 1) {
      var tabs = el("div", "ev-tabs");
      tabs.setAttribute("role", "tablist");
      ev.brands.forEach(function (b, i) {
        var t = el("button", "ev-tab", b.brand);
        t.type = "button";
        t.setAttribute("role", "tab");
        t.setAttribute("aria-selected", i === brandIx ? "true" : "false");
        t.addEventListener("click", function () { brandIx = i; draw(); });
        tabs.appendChild(t);
      });
      root.appendChild(tabs);
    }
    var b = ev.brands[brandIx] || ev.brands[0];
    if (!b) return;
    if (b.product) root.appendChild(el("p", "ev-product", b.product));

    b.competitors.forEach(function (c) {
      var card = el("article", "ev-card");
      var top = el("div", "ev-card__top");
      top.appendChild(el("h3", "ev-card__name", c.competitor));
      if (c.fit) top.appendChild(el("span", "ev-chip", c.fit));
      card.appendChild(top);
      var kv = el("div", "ev-kv");
      [[c.posts, "collab posts"], [c.creators, "creators"], [num(c.total_views), "total views"],
       [num(c.median_views), "median views"], [pct(c.median_er), "median engagement"]].forEach(function (x) {
        var d = el("div"); d.appendChild(el("b", "", String(x[0]))); d.appendChild(el("span", "", x[1])); kv.appendChild(d);
      });
      card.appendChild(kv);

      if (c.top.length) {
        card.appendChild(el("h4", "ev-sub", "Best creators with " + c.competitor));
        card.appendChild(table(
          [{t: "Creator"}, {t: "Followers", n: 1}, {t: "Posts", n: 1}, {t: "Median views", n: 1}, {t: "Engagement", n: 1}, {t: "Best post", n: 1}],
          c.top.map(function (t) {
            var who = el("div");
            who.appendChild(el("b", "", t.name || ("@" + t.handle)));
            var meta = el("span", "ev-mut", "@" + t.handle + (t.city ? " · " + t.city : ""));
            who.appendChild(document.createElement("br"));
            who.appendChild(meta);
            if (t.in_selection) { who.appendChild(document.createTextNode(" ")); who.appendChild(el("span", "ev-chip ev-chip--in", "In this selection")); }
            return [who, num(t.followers), t.posts, num(t.median_views), pct(t.median_er, t.likes_hidden), link(t.best_url, num(t.best_views) + " views")];
          })));
      }
      if (c.rows.length) {
        var det = el("details", "ev-posts");
        det.appendChild(el("summary", "", "See the " + c.rows.length + " posts"));
        det.appendChild(table(
          [{t: "Post"}, {t: "Creator"}, {t: "Type"}, {t: "Views", n: 1}, {t: "Likes", n: 1}, {t: "Comments", n: 1}, {t: "Engagement", n: 1}],
          c.rows.map(function (r) {
            var cell = el("div");
            cell.appendChild(link(r.url, r.date || "Open post"));
            if (r.same_category) { cell.appendChild(document.createTextNode(" ")); cell.appendChild(el("span", "ev-chip ev-chip--cat", "Same category")); }
            if (r.paid_boost) { cell.appendChild(document.createTextNode(" ")); cell.appendChild(el("span", "ev-chip ev-chip--paid", "Paid-boosted")); }
            return [cell, "@" + r.handle, r.collab, num(r.views), r.likes == null ? "Hidden" : num(r.likes), num(r.comments), pct(r.er, r.likes == null)];
          })));
        card.appendChild(det);
      }
      root.appendChild(card);
    });
    sec.hidden = false;
  }

  function load() {
    var t = token();
    if (!t || t === loadedFor) return;
    loadedFor = t;
    fetch((CFG.api || "") + "/api/evidence?s=" + encodeURIComponent(t), { credentials: "include" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!j || !j.ok || !j.evidence || !j.evidence.brands || !j.evidence.brands.length) { sec.hidden = true; loadedFor = null; return; }
        data = j.evidence; brandIx = 0; draw();
      })
      .catch(function () { loadedFor = null; });
  }

  // The page opens behind an access code: load once the app is shown, and again if the link changes.
  var app = document.getElementById("cat-app");
  if (app && app.hidden && window.MutationObserver) {
    new MutationObserver(function () { if (!app.hidden) load(); }).observe(app, { attributes: true, attributeFilter: ["hidden"] });
  }
  window.addEventListener("hashchange", function () { loadedFor = null; load(); });
  if (!app || !app.hidden) load();
})();
