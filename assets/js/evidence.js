/* Competitor evidence on the selection page (admin/evidence.py → GET /api/evidence?s=<token>).
 * Shown only when HelloVoice shared a pack on this selection: which creators already worked with
 * the brand's competitors, and how each post performed, every number linked to the post itself.
 * Everything is drawn with textContent; nothing from the server is parsed as HTML. */
(function () {
  "use strict";
  var CFG = window.CATALOGUE_CONFIG || {};
  var sec = document.getElementById("sel-evidence");
  var root = document.getElementById("ev-root");
  var marketPage = !!document.getElementById("ev-market");
  if (!marketPage && (!sec || !root)) return;
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
        if (!j || !j.ok || !j.evidence || !j.evidence.brands || !j.evidence.brands.length) { if (sec) sec.hidden = true; loadedFor = null; return; }
        data = j.evidence; brandIx = 0; decorate(); miButton();
      })
      .catch(function () { loadedFor = null; });
  }

  /* ---------------- Track record: a button on each creator card, opening a side panel ---------------- */

  var grid = document.getElementById("cat-grid");
  var panel = null, lastFocus = null;

  function sel() { return window.hvSelection || null; }

  function decorate() {
    if (!grid || !data || !data.by_code) return;
    [].forEach.call(grid.querySelectorAll("article.cat-card[data-code]"), function (card) {
      var code = card.getAttribute("data-code"), info = data.by_code[code];
      var have = card.querySelector(".ev-tr");
      if (!info) { if (have) have.remove(); return; }
      if (have) return;
      var b = el("button", "ev-tr");
      b.type = "button";
      b.setAttribute("data-noselect", "");
      b.setAttribute("aria-haspopup", "dialog");
      b.appendChild(el("span", "ev-tr__ic", "▤"));
      b.appendChild(el("span", "", "Track record"));
      b.appendChild(el("span", "ev-tr__n", info.brands + (info.brands === 1 ? " brand" : " brands")));
      b.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); openPanel(code, b); });
      var body = card.querySelector(".cat-card__body"), st = body && body.querySelector(".sel-st");
      if (!body) return;
      if (st) body.insertBefore(b, st); else body.appendChild(b);
    });
  }

  function closePanel() {
    if (!panel) return;
    panel.scrim.remove(); panel.aside.remove(); panel = null;
    document.body.classList.remove("pt-lock");
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function tile(v, label) {
    var d = el("div"); d.appendChild(el("b", "", String(v))); d.appendChild(el("span", "", label)); return d;
  }

  function openPanel(code, from) {
    closePanel();
    lastFocus = from || document.activeElement;
    var S = sel(), who = S && S.creator ? S.creator(code) : null;
    var scrim = el("div", "ev-pn__scrim");
    var aside = el("aside", "ev-pn");
    aside.setAttribute("role", "dialog"); aside.setAttribute("aria-modal", "true"); aside.setAttribute("aria-labelledby", "ev-pn-t");
    var hd = el("header", "ev-pn__hd");
    var ttl = el("div");
    var h = el("h2", "ev-pn__t", (who && who.name) || code); h.id = "ev-pn-t";
    ttl.appendChild(el("p", "ev-eyebrow", "Brand track record"));
    ttl.appendChild(h);
    var x = el("button", "ev-pn__x", "×"); x.type = "button"; x.setAttribute("aria-label", "Close");
    x.addEventListener("click", closePanel);
    hd.appendChild(ttl); hd.appendChild(x);
    var bd = el("div", "ev-pn__bd"); bd.appendChild(el("p", "ev-mut", "Loading…"));
    aside.appendChild(hd); aside.appendChild(bd);
    scrim.addEventListener("click", closePanel);
    document.body.appendChild(scrim); document.body.appendChild(aside);
    document.body.classList.add("pt-lock");
    panel = { scrim: scrim, aside: aside, code: code };
    x.focus();
    fetch((CFG.api || "") + "/api/evidence/creator?s=" + encodeURIComponent(token()) + "&c=" + encodeURIComponent(code), { credentials: "include" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!panel || panel.code !== code) return;
        bd.textContent = "";
        if (!j || !j.ok || !j.creator) { bd.appendChild(el("p", "ev-mut", "No competitor posts found for this creator.")); return; }
        fill(bd, code, j.creator, j.preview);
      })
      .catch(function () { if (panel) { bd.textContent = ""; bd.appendChild(el("p", "ev-mut", "Could not load. Try again.")); } });
  }

  /* Charts and post cards, drawn as DOM / SVG (never parsed HTML). */
  var SVGNS = "http://www.w3.org/2000/svg";
  var PALETTE = ["#121212", "#ff691e", "#14884a", "#b9d400", "#8a7a68", "#ee1515", "#e2780f"];
  function svg(tag, attrs) {
    var n = document.createElementNS(SVGNS, tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    return n;
  }
  function colourOf(map, name) {
    if (!(name in map)) map[name] = PALETTE[Object.keys(map).length % PALETTE.length];
    return map[name];
  }
  function chartCard(title, note) {
    var box = el("section", "ev-viz");
    box.appendChild(el("h4", "ev-sub", title));
    if (note) box.appendChild(el("p", "ev-viz__note", note));
    return box;
  }

  // Horizontal bars: [{label, v, colour, text}]
  function hbars(items) {
    var max = Math.max.apply(null, items.map(function (i) { return i.v || 0; }).concat([1]));
    var wrap = el("div", "ev-hb");
    items.forEach(function (i) {
      var row = el("div", "ev-hb__row");
      row.appendChild(el("span", "ev-hb__l", i.label));
      var track = el("span", "ev-hb__t"), bar = el("i");
      bar.style.width = Math.max(2, Math.round(100 * (i.v || 0) / max)) + "%";
      bar.style.background = i.colour || "#121212";
      track.appendChild(bar); row.appendChild(track);
      row.appendChild(el("b", "ev-hb__v", i.text));
      wrap.appendChild(row);
    });
    return wrap;
  }

  // Stacked share bar + key: [{label, n, colour}]
  function share(items) {
    var tot = items.reduce(function (a, i) { return a + i.n; }, 0) || 1;
    var wrap = el("div"), bar = el("div", "ev-split");
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", items.map(function (i) { return i.label + " " + Math.round(100 * i.n / tot) + "%"; }).join(", "));
    items.forEach(function (i) { var seg = el("i"); seg.style.width = (100 * i.n / tot) + "%"; seg.style.background = i.colour; bar.appendChild(seg); });
    wrap.appendChild(bar);
    var key = el("div", "ev-key");
    items.forEach(function (i) {
      var k = el("span"), dot = el("i"); dot.style.background = i.colour;
      k.appendChild(dot); k.appendChild(document.createTextNode(i.label + " · " + i.n + " (" + Math.round(100 * i.n / tot) + "%)"));
      key.appendChild(k);
    });
    wrap.appendChild(key);
    return wrap;
  }

  // Views per post, oldest to newest, one column per post coloured by brand, with the median line.
  function viewsChart(posts, colours, median, reach) {
    var ps = posts.filter(function (p) { return p.views != null; }).slice().sort(function (a, b) { return (a.date || "") < (b.date || "") ? -1 : 1; });
    var W = 640, H = 220, pad = { l: 46, r: 10, t: 14, b: 34 };
    var top = Math.max.apply(null, ps.map(function (p) { return p.views; }).concat([reach || 0, 1]));
    var g = svg("svg", { viewBox: "0 0 " + W + " " + H, class: "ev-chart", role: "img",
      "aria-label": "Views per competitor post over time. Median " + num(median) + (reach ? ", their normal median " + num(reach) : "") });
    var y = function (v) { return pad.t + (H - pad.t - pad.b) * (1 - v / top); };
    [0, 0.5, 1].forEach(function (f) {
      var v = top * f, yy = y(v);
      g.appendChild(svg("line", { x1: pad.l, x2: W - pad.r, y1: yy, y2: yy, class: "ev-chart__grid" }));
      var t = svg("text", { x: pad.l - 6, y: yy + 4, "text-anchor": "end", class: "ev-chart__ax" }); t.textContent = num(v); g.appendChild(t);
    });
    var bw = (W - pad.l - pad.r) / Math.max(ps.length, 1);
    ps.forEach(function (p, i) {
      var x = pad.l + i * bw + bw * 0.15, w = Math.max(3, bw * 0.7), yy = y(p.views);
      var r = svg("rect", { x: x, y: yy, width: w, height: Math.max(1, H - pad.b - yy), rx: 3, fill: colours[p.competitor] || "#121212",
        opacity: p.paid_boost ? 0.35 : 1 });
      var tt = svg("title"); tt.textContent = (p.date || "") + " · " + p.competitor + " · " + num(p.views) + " views" + (p.paid_boost ? " (paid-boosted)" : "");
      r.appendChild(tt); g.appendChild(r);
      if (ps.length <= 14 || i === 0 || i === ps.length - 1) {
        var lab = svg("text", { x: x + w / 2, y: H - pad.b + 14, "text-anchor": "middle", class: "ev-chart__ax" });
        lab.textContent = (p.date || "").slice(2, 7); g.appendChild(lab);
      }
    });
    var used = [];
    function line(v, cls, text) {
      if (v == null) return;
      var yy = y(v), ty = yy - 5;
      used.forEach(function (u) { if (Math.abs(u - ty) < 14) ty = u + 14; });   // keep two close labels apart
      used.push(ty);
      g.appendChild(svg("line", { x1: pad.l, x2: W - pad.r, y1: yy, y2: yy, class: cls }));
      var bg = svg("rect", { x: pad.l + 4, y: ty - 11, width: text.length * 6.4 + 8, height: 15, rx: 3, class: "ev-chart__labbg" });
      var t = svg("text", { x: pad.l + 8, y: ty, class: "ev-chart__lab" }); t.textContent = text;
      g.appendChild(bg); g.appendChild(t);
    }
    line(median, "ev-chart__med", "Median " + num(median));
    line(reach, "ev-chart__reach", "Normal reach " + num(reach));
    return g;
  }

  // The post player, in place, like the profile analysis.
  function player(url) {
    var m = /instagram\.com\/(?:[^\/]+\/)?(?:p|reel|reels|tv)\/([A-Za-z0-9_-]+)/.exec(url || "");
    var t = /tiktok\.com\/@[^\/]+\/video\/(\d+)/.exec(url || "");
    if (m) return "https://www.instagram.com/p/" + m[1] + "/embed/captioned/";
    if (t) return "https://www.tiktok.com/player/v1/" + t[1] + "?music_info=1&description=1&controls=1";
    return null;
  }
  function playIn(host, p) {
    var src = player(p.url);
    if (!src) { window.open(p.url, "_blank", "noopener"); return; }
    var box = el("div", "ev-play");
    var fr = el("iframe"); fr.src = src; fr.title = "Post by " + (p.competitor || "") + " creator"; fr.setAttribute("allow", "autoplay; encrypted-media; picture-in-picture"); fr.setAttribute("loading", "lazy");
    var bar = el("div", "ev-play__bar");
    bar.appendChild(link(p.url, "Open on " + (p.platform === "tiktok" ? "TikTok" : "Instagram")));
    var x = el("button", "ev-act", "Close player"); x.type = "button";
    x.addEventListener("click", function () { box.remove(); });
    bar.appendChild(x);
    box.appendChild(fr); box.appendChild(bar);
    var old = host.querySelector(".ev-play"); if (old) old.remove();
    host.insertBefore(box, host.firstChild);
    box.scrollIntoView({ block: "nearest" });
  }

  function metric(v, label, tone) {
    var d = el("div", "ev-m" + (tone ? " ev-m--" + tone : "")); d.appendChild(el("b", "", v)); d.appendChild(el("span", "", label)); return d;
  }
  var HIDDEN = "\u2014";

  function postCard(p, colours, reach, host) {
    var card = el("article", "ev-post");
    var media = el("button", "ev-post__media"); media.type = "button";
    media.setAttribute("aria-label", "Play the " + p.competitor + " post from " + (p.date || ""));
    if (p.id != null) {
      var img = el("img"); img.src = (CFG.api || "") + "/api/evidence/thumb?s=" + encodeURIComponent(token()) + "&p=" + encodeURIComponent(p.id);
      img.alt = ""; img.loading = "lazy";
      img.addEventListener("error", function () { img.remove(); media.classList.add("ev-post__media--none"); });
      media.appendChild(img);
    } else { media.classList.add("ev-post__media--none"); }
    media.appendChild(el("span", "ev-post__none", p.platform === "tiktok" ? "TikTok post" : "Instagram post"));
    media.appendChild(el("span", "ev-post__play", "▶"));
    var brand = el("span", "ev-post__brand ev-post__brand--logo"); brand.style.borderColor = colours[p.competitor] || "#121212";
    brand.appendChild(logoEl(p.competitor, (logosNow || {})[p.competitor], "ev-logo--badge"));
    media.appendChild(brand);
    if (p.paid_boost) media.appendChild(el("span", "ev-post__flag", "Paid-boosted"));
    media.addEventListener("click", function () { playIn(host, p); });
    card.appendChild(media);
    var meta = el("p", "ev-post__meta", (p.date || "") + " · " + (p.collab || ""));
    card.appendChild(meta);
    var ms = el("div", "ev-post__ms");
    ms.appendChild(metric(num(p.views), "views"));
    ms.appendChild(metric(p.likes == null ? HIDDEN : num(p.likes), p.likes == null ? "likes hidden" : "likes"));
    ms.appendChild(metric(num(p.comments), "comments"));
    ms.appendChild(metric(p.er == null ? HIDDEN : pct(p.er), p.er == null ? "engagement n/a" : "engagement"));
    if (reach && p.views != null) {
      var x = p.views / reach;
      ms.appendChild(metric((x >= 10 ? Math.round(x) : x.toFixed(1)) + "×", "vs normal reach", x >= 1 ? "up" : "down"));
    }
    if (p.same_category) ms.appendChild(metric("✓", "same category", "up"));
    card.appendChild(ms);
    return card;
  }

  var logosNow = null;
  function fill(bd, code, c, preview) {
    logosNow = c.logos || (data && data.logos) || {};
    var S = sel();
    if (preview) bd.appendChild(el("p", "ev-chip ev-chip--paid", "Preview — not shared with the client yet"));
    var meta = "@" + c.handle + (c.type === "hcp" ? " · Doctor / pharmacist" : " · Influencer");
    bd.appendChild(el("p", "ev-mut", meta));

    var colours = {};
    c.competitors.forEach(function (k) { colourOf(colours, k.name); });

    // Normal reach: the platform they post on most, preferring Instagram.
    var reachV = null, reachP = null;
    ["Instagram", "TikTok"].concat(Object.keys(c.reach || {})).some(function (p) {
      var r = (c.reach || {})[p]; if (!r) return false;
      var v = r.median_views != null ? r.median_views : (r.avg_reel_plays != null ? r.avg_reel_plays : r.avg_views);
      if (v != null) { reachV = v; reachP = p; return true; } return false;
    });

    var kv = el("div", "ev-kv");
    kv.appendChild(tile(c.kpis.posts, "collab posts"));
    kv.appendChild(tile(num(c.kpis.median_views), "median views"));
    kv.appendChild(tile(num(c.kpis.best_views), "best post"));
    kv.appendChild(tile(c.kpis.median_er == null ? HIDDEN : pct(c.kpis.median_er), c.kpis.median_er == null ? "engagement (likes hidden)" : "engagement"));
    kv.appendChild(tile(c.kpis.last || "—", "last collab"));
    bd.appendChild(kv);

    // Score vs the brief, from the page's own scores.
    var cur = S && S.curated ? S.curated() : null;
    var sc = cur && cur.scores ? cur.scores[code] : null, vd = cur && cur.verdicts ? cur.verdicts[code] : null;
    var fitTxt = (vd && vd.fit) || (sc && sc.tag) || "";
    var sb = el("div", "ev-pn__score");
    sb.appendChild(el("h4", "ev-sub", "Score vs the brief"));
    sb.appendChild(el("p", "", (sc && sc.score != null ? sc.score + " / 100" : "Needs data") + (fitTxt ? " · " + fitTxt : "")));
    bd.appendChild(sb);

    var grid = el("div", "ev-viz-grid");
    var r1 = chartCard("Brand posts vs normal reach", reachV != null ? "Median views on their competitor posts against their own " + reachP + " posts." : "Their own-post views are not in yet.");
    var items = [{ label: "Competitor posts", v: c.kpis.median_views || 0, colour: "#ff691e", text: num(c.kpis.median_views) }];
    if (reachV != null) items.push({ label: "Their own posts", v: reachV, colour: "#121212", text: num(reachV) });
    r1.appendChild(hbars(items));
    if (reachV) {
      var lift = (c.kpis.median_views || 0) / reachV;
      r1.appendChild(el("p", "ev-viz__said", lift >= 1.1 ? "Brand posts reach " + lift.toFixed(1) + "× their normal views." : lift <= 0.9 ? "Brand posts reach " + Math.round(lift * 100) + "% of their normal views." : "Brand posts reach about their normal views."));
    }
    grid.appendChild(r1);

    var r2 = chartCard("Posts by competitor");
    r2.appendChild(share(c.competitors.map(function (k) { return { label: k.name, n: k.posts, colour: colours[k.name] }; })));
    var mix = {};
    c.posts.forEach(function (p) { var k = p.collab || "Other"; mix[k] = (mix[k] || 0) + 1; });
    r2.appendChild(el("h4", "ev-sub", "Collab type"));
    var mc = {};
    r2.appendChild(share(Object.keys(mix).map(function (k) { return { label: k, n: mix[k], colour: colourOf(mc, k) }; })));
    grid.appendChild(r2);
    bd.appendChild(grid);

    var r3 = chartCard("Views per post over time", "Each column is one post, coloured by brand. Faded columns are paid-boosted.");
    var chartHost = el("div", "ev-chart-host");
    r3.appendChild(chartHost);
    bd.appendChild(r3);

    // Brand strip: filters the chart and the posts.
    var strip = el("div", "ev-pn__brands"), active = null;
    c.competitors.forEach(function (k) {
      var b = el("button", "ev-brand"); b.type = "button"; b.setAttribute("aria-pressed", "false");
      var dot = el("i", "ev-brand__dot"); dot.style.background = colours[k.name];
      b.appendChild(dot); b.appendChild(logoEl(k.name, (c.logos || {})[k.name], "ev-logo--chip")); b.appendChild(document.createTextNode(" \u00B7 " + k.posts));
      b.setAttribute("aria-label", k.name + ", " + k.posts + " posts");
      b.addEventListener("click", function () {
        active = active === k.name ? null : k.name;
        [].forEach.call(strip.children, function (x) { x.setAttribute("aria-pressed", x === b && active ? "true" : "false"); });
        redraw();
      });
      strip.appendChild(b);
    });

    var postsHead = el("div", "ev-posts-hd");
    postsHead.appendChild(el("h4", "ev-sub", "Posts"));
    postsHead.appendChild(strip);
    bd.appendChild(postsHead);
    var postsHost = el("div", "ev-posts-host");
    var postGrid = el("div", "ev-postgrid");
    postsHost.appendChild(postGrid);
    bd.appendChild(postsHost);

    function redraw() {
      var ps = c.posts.filter(function (p) { return !active || p.competitor === active; });
      chartHost.textContent = "";
      var org = ps.filter(function (p) { return !p.paid_boost && p.views != null; }).map(function (p) { return p.views; }).sort(function (a, b) { return a - b; });
      var med = org.length ? (org.length % 2 ? org[(org.length - 1) / 2] : (org[org.length / 2 - 1] + org[org.length / 2]) / 2) : null;
      chartHost.appendChild(viewsChart(ps, colours, med, reachV));
      postGrid.textContent = "";
      ps.forEach(function (p) { postGrid.appendChild(postCard(p, colours, reachV, postsHost)); });
    }
    redraw();

    // Keep or remove: the page's own approve / reject, for the selection's owner and HelloVoice.
    var role = S && S.role ? S.role() : "viewer";
    if (role === "admin" || role === "owner") {
      var st = S.status ? (S.status(code) || {}).s : "";
      var ft = el("footer", "ev-pn__ft");
      ft.appendChild(el("p", "ev-mut", st === "approved" ? "Kept in this selection." : st === "rejected" ? "Removed from this selection." : "Not decided yet."));
      [["approved", "Keep in selection"], ["rejected", "Remove from selection"]].forEach(function (o) {
        var b = el("button", "ev-act" + (o[0] === "approved" ? " ev-act--yes" : ""), o[1]); b.type = "button";
        if (st === o[0]) b.disabled = true;
        b.addEventListener("click", function () { setStatus(code, o[0], b); });
        ft.appendChild(b);
      });
      bd.appendChild(ft);
    }
  }

  function setStatus(code, status, btn) {
    btn.disabled = true;
    fetch((CFG.api || "") + "/api/selection/status", {
      method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: token(), code: code, status: status })
    }).then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (j) {
        var S = sel();
        if (j && j.ok) {
          if (S && S.toast) S.toast(status === "approved" ? "Kept in the selection." : "Removed from the selection.");
          if (S && S.refresh) S.refresh();
          closePanel();
        } else { btn.disabled = false; if (S && S.toast) S.toast("That did not save. Try again."); }
      }).catch(function () { btn.disabled = false; });
  }

  /* ---------------- Market Intelligence v2: map, ranking list, creator panel ---------------- */

  var mi = null, miData = null, miFilter = { type: "all", platform: "all" }, miFocus = null, miView = { k: 1, x: 0, y: 0 }, miListN = 20;
  var TYPE_RING = { hcp: "#14884a", influencer: "#121212" };
  var XLINK = "http://www.w3.org/1999/xlink";

  function miButton() {
    if (document.getElementById("ev-mi-btn")) return;
    var title = document.getElementById("sel-title");
    if (!title || !title.parentNode) return;
    var b = el("a", "ev-mi-btn"); b.id = "ev-mi-btn";
    b.href = "/market/#s=" + encodeURIComponent(token());
    b.appendChild(el("span", "ev-mi-btn__ic", "\u25CE"));
    b.appendChild(document.createTextNode("Market Intelligence"));
    title.parentNode.insertBefore(b, title.nextSibling);
  }

  // A brand is always its logo; the name stays as the accessible label and only shows when no logo is approved yet.
  function logoEl(name, url, cls) {
    if (url) {
      var i = el("img", "ev-logo" + (cls ? " " + cls : "")); i.src = (CFG.api || "") + url; i.alt = name; i.title = name; i.decoding = "async";
      return i;
    }
    return el("span", "ev-logo ev-logo--txt" + (cls ? " " + cls : ""), name);
  }
  function compLogo(name) {
    var c = miData && miData.competitors.filter(function (x) { return x.name === name; })[0];
    return c ? c.logo : (data && data.logos ? data.logos[name] : null);
  }
  function rankText(p) { return miData.rank_by === "interactions" ? num(p.rank_value) + " interactions" : num(p.rank_value) + " views"; }
  function rankLabel() { return miData.rank_by === "interactions" ? "likes + comments" : "views"; }
  function typeOf(p) { return p.type === "hcp" ? "hcp" : "influencer"; }
  function kept(p) {
    return (miFilter.type === "all" || typeOf(p) === miFilter.type) && (miFilter.platform === "all" || p.platforms.indexOf(miFilter.platform) >= 0);
  }

  function closeMI() { location.href = "/selection/#s=" + encodeURIComponent(token()); }

  // Market Intelligence has its own page: /market/#s=<selection token> (market/index.html).
  function openMI() {
    var root = document.getElementById("ev-market");
    if (!root) return;
    root.textContent = "";
    var hd = el("header", "ev-mi__hd");
    var backSel = el("a", "ev-act", "\u2190 Back to selection"); backSel.href = "/selection/#s=" + encodeURIComponent(token());
    hd.appendChild(backSel);
    var t = el("div", "ev-mi__title");
    t.appendChild(el("p", "ev-eyebrow", "Market Intelligence"));
    var h = el("h1", "ev-mi__t", "Who works with your competitors"); h.id = "ev-mi-t"; t.appendChild(h);
    hd.appendChild(t);
    var body = el("div", "ev-mi__bd"); body.appendChild(el("p", "ev-mut", "Loading the map\u2026"));
    root.appendChild(hd); root.appendChild(body);
    mi = { root: root, body: body };
    var go = function (d) { miData = d; miFocus = null; miView = { k: 1, x: 0, y: 0 }; miListN = 20; drawMI(); };
    fetch((CFG.api || "") + "/api/evidence/map?s=" + encodeURIComponent(token()), { credentials: "include" })
      .then(function (r) { return r.status === 401 ? { locked: true } : r.ok ? r.json() : null; })
      .then(function (j) {
        if (j && j.ok && j.map) return go(j.map);
        body.textContent = "";
        body.appendChild(el("p", "ev-mut", j && j.locked ? "Open this from your selection page first (it asks for your access code)." : "Market Intelligence is not available for this selection."));
      })
      .catch(function () { body.textContent = ""; body.appendChild(el("p", "ev-mut", "Could not load the map.")); });
    // The Track record button inside a creator's panel needs the per-creator counts.
    fetch((CFG.api || "") + "/api/evidence?s=" + encodeURIComponent(token()), { credentials: "include" })
      .then(function (r) { return r.ok ? r.json() : null; }).then(function (j) { if (j && j.ok && j.evidence) data = j.evidence; }).catch(function () {});
  }

  function chips(label, opts, key) {
    var g = el("div", "ev-mi__chips"); g.setAttribute("role", "group"); g.setAttribute("aria-label", label);
    opts.forEach(function (o) {
      var b = el("button", "ev-brand", o[1]); b.type = "button";
      b.setAttribute("aria-pressed", miFilter[key] === o[0] ? "true" : "false");
      if (o[2]) { b.disabled = true; b.title = o[2]; }
      b.addEventListener("click", function () { miFilter[key] = o[0]; miListN = 20; drawMI(); });
      g.appendChild(b);
    });
    return g;
  }

  // The creators the map shows: everyone in focus mode, else each competitor's best 5 (by the objective's measure).
  function visible(people) {
    if (miFocus) return people.filter(function (p) { return p.competitors[miFocus]; }).slice(0, 30);
    var pick = {};
    miData.competitors.forEach(function (c) {
      people.filter(function (p) { return p.competitors[c.name]; }).slice(0, 5).forEach(function (p) { pick[p.handle] = true; });
    });
    return people.filter(function (p) { return pick[p.handle]; });
  }

  function drawMI() {
    var d = miData, body = mi.body;
    body.textContent = "";
    if (d.preview) body.appendChild(el("p", "ev-chip ev-chip--paid", "Preview — not shared with the client yet"));
    var bar = el("div", "ev-mi__bar");
    var hasTT = d.creators.some(function (c) { return c.platforms.indexOf("tiktok") >= 0; });
    bar.appendChild(chips("Platform", [["all", "All platforms"], ["instagram", "Instagram"], ["tiktok", "TikTok", hasTT ? "" : "TikTok study not in yet"]], "platform"));
    bar.appendChild(chips("Creator type", [["all", "Everyone"], ["hcp", "Doctors / pharmacists"], ["influencer", "Influencers"]], "type"));
    var leg = el("div", "ev-key");
    [["hcp", "Doctors / pharmacists"], ["influencer", "Influencers"]].forEach(function (k) { var s2 = el("span"), i = el("i"); i.style.border = "3px solid " + TYPE_RING[k[0]]; s2.appendChild(i); s2.appendChild(document.createTextNode(k[1])); leg.appendChild(s2); });
    leg.appendChild(el("span", "", "Bigger photo = more " + rankLabel()));
    bar.appendChild(leg);
    body.appendChild(bar);

    var people = d.creators.filter(kept);
    var layout = el("div", "ev-mi__layout");
    var stage = el("div", "ev-mi__stage");
    var tools = el("div", "ev-mi__tools");
    if (miFocus) {
      var back = el("button", "ev-act ev-act--yes", "← All competitors"); back.type = "button";
      back.addEventListener("click", function () { miFocus = null; miView = { k: 1, x: 0, y: 0 }; miListN = 20; drawMI(); });
      tools.appendChild(back);
    }
    [["+", 1.25, "Zoom in"], ["−", 0.8, "Zoom out"], ["↺", 0, "Reset view"]].forEach(function (z) {
      var b = el("button", "ev-zoom", z[0]); b.type = "button"; b.setAttribute("aria-label", z[2]);
      b.addEventListener("click", function () { if (!z[1]) miView = { k: 1, x: 0, y: 0 }; else miView.k = Math.max(0.6, Math.min(4, miView.k * z[1])); applyView(); });
      tools.appendChild(b);
    });
    stage.appendChild(tools);
    var svgEl = mapSvg(d, people, stage);
    stage.appendChild(svgEl);
    layout.appendChild(stage);
    layout.appendChild(rankList(people));
    body.appendChild(layout);
    body.appendChild(el("p", "ev-viz__note", miFocus
      ? "Showing the best " + Math.min(30, people.filter(function (p) { return p.competitors[miFocus]; }).length) + " creators of this competitor. The full list is on the right."
      : "Each competitor shows its best 5 creators by " + rankLabel() + ". Click a logo to see all of its creators; click a photo to open the creator."));
    mi.svg = svgEl;
    applyView();
  }

  function applyView() {
    if (!mi || !mi.svg) return;
    var g = mi.svg.querySelector(".ev-map__world");
    if (g) g.setAttribute("transform", "translate(" + miView.x + " " + miView.y + ") scale(" + miView.k + ")");
  }

  function mapSvg(d, people, stage) {
    var W = 1400, H = 820, cx = W / 2, cy = H / 2;
    var g = svg("svg", { viewBox: "0 0 " + W + " " + H, class: "ev-map", role: "img",
      "aria-label": "Your brand in the centre and its competitors around it, each with its best creators." });
    var defs = svg("defs"); g.appendChild(defs);
    var world = svg("g", { class: "ev-map__world" }); g.appendChild(world);
    var links2 = svg("g"), nodes = svg("g");
    world.appendChild(links2); world.appendChild(nodes);
    var vis = visible(people);
    var maxR = Math.max.apply(null, vis.map(function (p) { return p.rank_value || 0; }).concat([1]));
    var dotR = function (p) { return (miFocus ? 26 : 22) + 14 * Math.sqrt((p.rank_value || 0) / maxR); };
    var placed = [], pos = {};
    function free(x, y, r) { return placed.every(function (q) { var dx = q.x - x, dy = q.y - y; return dx * dx + dy * dy >= (q.r + r + 4) * (q.r + r + 4); }); }
    function place(x, y, r) {
      for (var k = 0; k < 260; k++) {
        var ang = k * 2.4, rad = k * 2.1, xx = x + rad * Math.cos(ang), yy = y + rad * Math.sin(ang);
        if (xx > r + 6 && xx < W - r - 6 && yy > r + 6 && yy < H - r - 6 && free(xx, yy, r)) { placed.push({ x: xx, y: yy, r: r }); return { x: xx, y: yy }; }
      }
      placed.push({ x: x, y: y, r: r }); return { x: x, y: y };
    }
    function bubble(name, url, x, y, r, big) {
      var gg = svg("g", { class: "ev-map__comp" + (big ? " ev-map__comp--hub" : ""), tabindex: "0", role: "button", "aria-label": name });
      var id = "evl" + (++dotSeq);
      var clip = svg("clipPath", { id: id }); clip.appendChild(svg("circle", { cx: x, cy: y, r: r - 3 })); defs.appendChild(clip);
      gg.appendChild(svg("circle", { cx: x, cy: y, r: r }));
      if (url) {
        var im = svg("image", { x: x - r * 0.72, y: y - r * 0.72, width: r * 1.44, height: r * 1.44, preserveAspectRatio: "xMidYMid meet", "clip-path": "url(#" + id + ")" });
        im.setAttributeNS(XLINK, "href", (CFG.api || "") + url); im.setAttribute("href", (CFG.api || "") + url);
        gg.appendChild(im);
      } else {
        var fs = Math.min(22, (2 * r - 16) / Math.max(name.length * 0.52, 1));
        var t = svg("text", { x: x, y: y + fs * 0.35, "text-anchor": "middle", class: "ev-map__cname", "font-size": fs.toFixed(1) }); t.textContent = name; gg.appendChild(t);
      }
      var tt = svg("title"); tt.textContent = name; gg.appendChild(tt);
      return gg;
    }

    if (!miFocus) {
      // Competitors on a wide oval so the whole screen is used; every creator gets ONE home (the competitor
      // they did most posts for) and fans out around it, so no area is crowded or empty. Lines to their
      // other competitors light up on hover.
      var n = d.competitors.length, RX = n > 1 ? 470 : 0, RY = n > 1 ? 262 : 0;
      var maxV = Math.max.apply(null, d.competitors.map(function (c) { return c.views; }).concat([1]));
      d.competitors.forEach(function (c, i) {
        var a = -Math.PI / 2 + i * 2 * Math.PI / Math.max(n, 1);
        pos[c.name] = { x: cx + RX * Math.cos(a), y: cy + RY * Math.sin(a), a: a, r: 44 + 16 * Math.sqrt(c.views / maxV) };
      });
      placed.push({ x: cx, y: cy, r: 78 });
      d.competitors.forEach(function (c) { var p = pos[c.name]; [-60, -30, 0, 30, 60].forEach(function (dx) { placed.push({ x: p.x + dx, y: p.y + p.r + 16, r: 14 }); }); placed.push({ x: p.x, y: p.y, r: p.r + 4 }); links2.appendChild(svg("line", { x1: cx, y1: cy, x2: p.x, y2: p.y, class: "ev-map__spoke" })); });
      var homes = {};
      vis.forEach(function (p) {
        var ks = Object.keys(p.competitors).filter(function (k) { return pos[k]; });
        var home = ks.sort(function (a, b) { return (p.competitors[b] - p.competitors[a]) || ((homes[a] || []).length - (homes[b] || []).length); })[0];
        (homes[home] = homes[home] || []).push(p);
      });
      Object.keys(homes).forEach(function (k) {
        var cp = pos[k], list = homes[k], m = list.length;
        var out = Math.atan2((cp.y - cy) / RY, (cp.x - cx) / RX);
        list.forEach(function (p, i) {
          var r = dotR(p), ring = i < 7 ? 0 : 1, j = ring ? i - 7 : i, cnt = ring ? Math.max(m - 7, 1) : Math.min(m, 7);
          var spread = Math.min(2.6, 0.55 * cnt), a = out + (cnt > 1 ? (j / (cnt - 1) - 0.5) * spread : 0);
          var dist = cp.r + r + 26 + ring * 70;
          var at = place(cp.x + dist * Math.cos(a), cp.y + dist * Math.sin(a), r);
          var ks = Object.keys(p.competitors).filter(function (k2) { return pos[k2]; });
          var mine = ks.map(function (k2) { var l = svg("line", { x1: at.x, y1: at.y, x2: pos[k2].x, y2: pos[k2].y, class: k2 === k ? "ev-map__own" : "ev-map__share" }); links2.appendChild(l); return l; });
          nodes.appendChild(dot(p, at, r, defs, stage, ks.length > 1, mine));
        });
      });
      nodes.appendChild(bubble(d.brand, d.brand_logo, cx, cy, 74, true));
      d.competitors.forEach(function (c) {
        var p = pos[c.name], b = bubble(c.name, c.logo, p.x, p.y, p.r);
        var all = people.filter(function (q) { return q.competitors[c.name]; }).length;
        var more = svg("text", { x: p.x, y: p.y + p.r + 18, "text-anchor": "middle", class: "ev-map__cnum" });
        more.textContent = num(c.views) + " views · " + all + " creators →"; b.appendChild(more);
        var go = function () { miFocus = c.name; miView = { k: 1, x: 0, y: 0 }; miListN = 30; drawMI(); };
        b.addEventListener("click", go);
        b.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
        nodes.appendChild(b);
      });
    } else {
      // Focus: one competitor in the centre, its creators in rings, names under the photos.
      var fc = d.competitors.filter(function (c) { return c.name === miFocus; })[0] || { name: miFocus };
      placed.push({ x: cx, y: cy, r: 84 });
      vis.forEach(function (p, i) {
        var r = dotR(p), ring = i < 8 ? 0 : i < 20 ? 1 : 2, idx = ring === 0 ? i : ring === 1 ? i - 8 : i - 20, cnt = ring === 0 ? 8 : 12;
        var a = -Math.PI / 2 + idx * 2 * Math.PI / cnt + (ring === 1 ? 0.26 : 0), rad = 175 + ring * 120;
        var at = place(cx + rad * 1.55 * Math.cos(a), cy + rad * Math.sin(a), r);
        links2.appendChild(svg("line", { x1: at.x, y1: at.y, x2: cx, y2: cy, class: "ev-map__own" }));
        var dd = dot(p, at, r, defs, stage, Object.keys(p.competitors).length > 1, []);
        var nm = svg("text", { x: at.x, y: at.y + r + 13, "text-anchor": "middle", class: "ev-map__nm" });
        nm.textContent = (p.name || p.handle).replace(/[|•·].*$/, "").trim().slice(0, 18); dd.appendChild(nm);
        nodes.appendChild(dd);
      });
      nodes.appendChild(bubble(fc.name, fc.logo, cx, cy, 80, true));
    }

    // Pan by dragging, zoom with the wheel.
    var drag = null;
    g.addEventListener("wheel", function (e) { e.preventDefault(); miView.k = Math.max(0.6, Math.min(4, miView.k * (e.deltaY < 0 ? 1.1 : 0.9))); applyView(); }, { passive: false });
    g.addEventListener("pointerdown", function (e) { if (e.target.closest && e.target.closest(".ev-map__dot, .ev-map__comp")) return; drag = { x: e.clientX, y: e.clientY, ox: miView.x, oy: miView.y }; g.setPointerCapture(e.pointerId); });
    g.addEventListener("pointermove", function (e) {
      if (!drag) return; var s = W / g.getBoundingClientRect().width;
      miView.x = drag.ox + (e.clientX - drag.x) * s; miView.y = drag.oy + (e.clientY - drag.y) * s; applyView();
    });
    g.addEventListener("pointerup", function () { drag = null; });
    return g;
  }

  var dotSeq = 0;
  function dot(p, at, r, defs, stage, shared, lines) {
    var gg = svg("g", { class: "ev-map__dot" + (p.paid_only ? " ev-map__dot--paid" : ""), tabindex: "0", role: "button",
      "aria-label": (p.name || p.handle) + ", " + rankText(p) + ". Open creator." });
    var id = "evc" + (++dotSeq);
    var clip = svg("clipPath", { id: id }); clip.appendChild(svg("circle", { cx: at.x, cy: at.y, r: r })); defs.appendChild(clip);
    gg.appendChild(svg("circle", { cx: at.x, cy: at.y, r: r, class: "ev-map__bg" }));
    if (p.photo) {
      var im = svg("image", { x: at.x - r, y: at.y - r, width: 2 * r, height: 2 * r, "clip-path": "url(#" + id + ")", preserveAspectRatio: "xMidYMid slice" });
      im.setAttributeNS(XLINK, "href", p.photo); im.setAttribute("href", p.photo);
      gg.appendChild(im);
    } else {
      var ini = svg("text", { x: at.x, y: at.y + 5, "text-anchor": "middle", class: "ev-map__ini" });
      ini.textContent = ((p.name || p.handle || "?").replace(/[^\p{L}\p{N} ]/gu, "").trim().split(/\s+/).map(function (w) { return w.charAt(0); }).slice(0, 2).join("") || "?").toUpperCase();
      gg.appendChild(ini);
    }
    gg.appendChild(svg("circle", { cx: at.x, cy: at.y, r: r, class: "ev-map__ring", stroke: TYPE_RING[typeOf(p)] }));
    if (shared) gg.appendChild(svg("circle", { cx: at.x + r * 0.72, cy: at.y - r * 0.72, r: 6, class: "ev-map__badge" }));
    var lit = function (on) { (lines || []).forEach(function (l) { l.classList.toggle("ev-map__lit", on); }); };
    gg.addEventListener("mouseenter", function () { tip(p, gg, stage); lit(true); });
    gg.addEventListener("focus", function () { tip(p, gg, stage); lit(true); });
    gg.addEventListener("mouseleave", function () { untip(stage); lit(false); });
    gg.addEventListener("blur", function () { untip(stage); lit(false); });
    gg.addEventListener("click", function () { untip(stage); openCreator(p); });
    gg.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openCreator(p); } });
    return gg;
  }

  function tip(p, node, stage) {
    untip(stage);
    var b = node.getBoundingClientRect(), s0 = stage.getBoundingClientRect();
    var t = el("div", "ev-tip"); t.setAttribute("role", "tooltip");
    t.appendChild(el("b", "", p.name || ("@" + p.handle)));
    t.appendChild(el("span", "", "@" + p.handle + (p.followers ? " · " + num(p.followers) + " followers" : "")));
    t.appendChild(el("span", "", rankText(p) + " (median)"));
    var lg = el("span", "ev-tip__logos");
    Object.keys(p.competitors).forEach(function (k) { lg.appendChild(logoEl(k, compLogo(k), "ev-logo--tip")); });
    t.appendChild(lg);
    t.style.left = Math.min(s0.width - 250, Math.max(0, b.left - s0.left + b.width / 2 - 120)) + "px";
    t.style.top = (b.top - s0.top + b.height + 8) + "px";
    stage.appendChild(t);
  }
  function untip(stage) { var o = stage.querySelector(".ev-tip"); if (o) o.remove(); }

  function rankList(people) {
    var box = el("aside", "ev-rank");
    var list = miFocus ? people.filter(function (p) { return p.competitors[miFocus]; }) : people;
    var hd = el("div", "ev-rank__hd");
    if (miFocus) hd.appendChild(logoEl(miFocus, compLogo(miFocus), "ev-logo--rank"));
    hd.appendChild(el("h3", "ev-sub", (miFocus ? "Creators" : "All creators") + " · ranked by " + rankLabel()));
    box.appendChild(hd);
    var ol = el("ol", "ev-rank__list");
    list.slice(0, miListN).forEach(function (p, i) {
      var li = el("li"), b = el("button", "ev-rank__row"); b.type = "button";
      b.appendChild(el("span", "ev-rank__n", String(i + 1)));
      var ph = el("span", "ev-rank__ph"); ph.style.borderColor = TYPE_RING[typeOf(p)];
      if (p.photo) { var im = el("img"); im.src = p.photo; im.alt = ""; im.loading = "lazy"; ph.appendChild(im); }
      b.appendChild(ph);
      var who = el("span", "ev-rank__who");
      who.appendChild(el("b", "", p.name || ("@" + p.handle)));
      var lg = el("span", "ev-rank__logos");
      Object.keys(p.competitors).forEach(function (k) { lg.appendChild(logoEl(k, compLogo(k), "ev-logo--mini")); });
      who.appendChild(lg);
      b.appendChild(who);
      b.appendChild(el("span", "ev-rank__v", num(p.rank_value)));
      b.addEventListener("click", function () { openCreator(p); });
      li.appendChild(b); ol.appendChild(li);
    });
    box.appendChild(ol);
    if (list.length > miListN) {
      var more = el("button", "ev-act", "Show more (" + (list.length - miListN) + ")"); more.type = "button";
      more.addEventListener("click", function () { miListN += 20; drawMI(); });
      box.appendChild(more);
    }
    return box;
  }

  /* The creator panel: the campaign-dashboard look, a posts grid with every figure under each post. */
  var cpanel = null;
  function closeCreator() { if (cpanel) { cpanel.scrim.remove(); cpanel.aside.remove(); cpanel = null; } }

  function openCreator(p) {
    closeCreator();
    var scrim = el("div", "ev-pn__scrim ev-pn__scrim--top"), aside = el("aside", "ev-pn ev-pn--top ev-cp");
    aside.setAttribute("role", "dialog"); aside.setAttribute("aria-modal", "true"); aside.setAttribute("aria-label", p.name || p.handle);
    scrim.addEventListener("click", closeCreator);
    var hd = el("header", "ev-cp__hd");
    var ph = el("span", "ev-cp__ph"); ph.style.borderColor = TYPE_RING[typeOf(p)];
    if (p.photo_large || p.photo) { var im = el("img"); im.src = p.photo_large || p.photo; im.alt = ""; ph.appendChild(im); }
    hd.appendChild(ph);
    var who = el("div", "ev-cp__who");
    who.appendChild(el("h2", "ev-pn__t", p.name || ("@" + p.handle)));
    who.appendChild(el("p", "ev-mut", "@" + p.handle + " · " + (typeOf(p) === "hcp" ? "Doctor / pharmacist" : "Influencer") + (p.followers ? " · " + num(p.followers) + " followers" : "")));
    var acts = el("div", "ev-cp__acts");
    if (p.code && data && data.by_code && data.by_code[p.code]) {
      var tr = el("button", "ev-act", "Track record"); tr.type = "button";
      tr.addEventListener("click", function () { closeCreator(); openPanel(p.code, tr); });
      acts.appendChild(tr);
    }
    if (p.in_selection) acts.appendChild(el("span", "ev-chip ev-chip--in", "In this selection"));
    else if (miData.can_add && p.on_roster) {
      var add = el("button", "ev-act ev-act--yes", "+ Add to selection"); add.type = "button";
      add.addEventListener("click", function () { addToSelection(p, add); });
      acts.appendChild(add);
    }
    who.appendChild(acts);
    hd.appendChild(who);
    var x = el("button", "ev-pn__x", "×"); x.type = "button"; x.setAttribute("aria-label", "Close"); x.addEventListener("click", closeCreator);
    hd.appendChild(x);
    aside.appendChild(hd);

    var bd = el("div", "ev-pn__bd");
    var organic = p.posts.filter(function (q) { return !q.paid_boost; });
    var views = organic.map(function (q) { return q.views || 0; });
    var kv = el("div", "ev-kv");
    kv.appendChild(tile(p.posts.length, "collab posts"));
    kv.appendChild(tile(num(median(views)), "median views"));
    kv.appendChild(tile(num(Math.max.apply(null, views.concat([0]))), "best post"));
    kv.appendChild(tile(p.median_er == null ? HIDDEN : pct(p.median_er), p.median_er == null ? "engagement (likes hidden)" : "engagement"));
    kv.appendChild(tile(num(p.interactions), "likes + comments (median)"));
    bd.appendChild(kv);

    var active = null, shown = 6;
    var strip = el("div", "ev-pn__brands");
    Object.keys(p.competitors).forEach(function (k) {
      var b = el("button", "ev-brand ev-brand--logo"); b.type = "button"; b.setAttribute("aria-pressed", "false"); b.setAttribute("aria-label", k + ", " + p.competitors[k] + " posts");
      b.appendChild(logoEl(k, compLogo(k), "ev-logo--chip")); b.appendChild(el("span", "", "· " + p.competitors[k]));
      b.addEventListener("click", function () {
        active = active === k ? null : k; shown = 6;
        [].forEach.call(strip.children, function (c2) { c2.setAttribute("aria-pressed", c2 === b && active ? "true" : "false"); });
        draw2();
      });
      strip.appendChild(b);
    });
    bd.appendChild(strip);
    var host = el("div", "ev-posts-host"), gridEl = el("div", "ev-dgrid"), moreBtn = el("button", "ev-act ev-more", ""); moreBtn.type = "button";
    host.appendChild(gridEl); bd.appendChild(host); bd.appendChild(moreBtn);
    moreBtn.addEventListener("click", function () { shown += 6; draw2(); });
    function draw2() {
      var ps = p.posts.filter(function (q) { return !active || q.competitor === active; });
      gridEl.textContent = "";
      ps.slice(0, shown).forEach(function (q) { gridEl.appendChild(dashPost(q, host)); });
      moreBtn.hidden = ps.length <= shown;
      moreBtn.textContent = "See more posts (" + (ps.length - shown) + ")";
    }
    draw2();
    aside.appendChild(bd);
    document.body.appendChild(scrim); document.body.appendChild(aside);
    cpanel = { scrim: scrim, aside: aside };
    x.focus();
  }

  function median(xs) {
    xs = xs.filter(function (v) { return v != null; }).sort(function (a, b) { return a - b; });
    if (!xs.length) return null;
    return xs.length % 2 ? xs[(xs.length - 1) / 2] : (xs[xs.length / 2 - 1] + xs[xs.length / 2]) / 2;
  }

  // One post, the campaign-dashboard card: picture (whole frame, blurred fill), brand logo, play; figures under it.
  function dashPost(q, host) {
    var card = el("article", "ev-dpost");
    var media = el("button", "ev-dpost__img"); media.type = "button"; media.setAttribute("aria-label", "Play the post from " + (q.date || ""));
    var src = (CFG.api || "") + "/api/evidence/thumb?s=" + encodeURIComponent(token()) + "&p=" + encodeURIComponent(q.id);
    var fill = el("img", "ev-fill"); fill.src = src; fill.alt = ""; fill.loading = "lazy"; fill.setAttribute("aria-hidden", "true");
    var fitI = el("img", "ev-fit"); fitI.src = src; fitI.alt = ""; fitI.loading = "lazy";
    fitI.addEventListener("error", function () { fill.remove(); fitI.remove(); media.classList.add("ev-dpost__img--none"); });
    media.appendChild(fill); media.appendChild(fitI);
    var badge = el("span", "ev-dpost__brand"); badge.appendChild(logoEl(q.competitor, compLogo(q.competitor), "ev-logo--badge")); media.appendChild(badge);
    if (q.paid_boost) media.appendChild(el("span", "ev-post__flag", "Paid-boosted"));
    media.appendChild(el("span", "ev-post__play", "▶"));
    media.addEventListener("click", function () { playIn(host, q); });
    card.appendChild(media);
    var b2 = el("div", "ev-dpost__body");
    b2.appendChild(el("b", "", q.collab || "Collab post"));
    b2.appendChild(el("span", "", (q.platform === "tiktok" ? "TikTok" : "Instagram") + " · " + (q.date || "")));
    card.appendChild(b2);
    var st = el("div", "ev-dpost__stats");
    [["Views", num(q.views)], ["Likes", q.likes == null ? "Hidden" : num(q.likes)], ["Comments", num(q.comments)], ["Eng. rate", q.er == null ? "n/a" : pct(q.er)]]
      .forEach(function (s2) { var dv = el("div"); dv.appendChild(el("small", "", s2[0])); dv.appendChild(el("b", "", s2[1])); st.appendChild(dv); });
    card.appendChild(st);
    return card;
  }

  function addToSelection(p, btn) {
    btn.disabled = true;
    fetch((CFG.api || "") + "/api/evidence/add", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: token(), handle: p.handle }) })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (j) {
        var S = sel();
        if (j && j.ok) {
          p.in_selection = true; p.code = j.code;
          btn.replaceWith(el("span", "ev-chip ev-chip--in", "Added to this selection"));
          if (S && S.refresh) S.refresh();
        } else { btn.disabled = false; if (S && S.toast) S.toast("Could not add this creator."); }
      }).catch(function () { btn.disabled = false; });
  }

  document.addEventListener("keydown", function (e) { if (e.key !== "Escape") return; if (panel) closePanel(); else if (cpanel) closeCreator(); });
  if (grid && window.MutationObserver) {
    // Cards are redrawn on every render; put the button back when they are.
    var pending = false;
    new MutationObserver(function () {
      if (pending) return; pending = true;
      requestAnimationFrame(function () { pending = false; decorate(); });
    }).observe(grid, { childList: true, subtree: true });
  }
  document.addEventListener("hv:selection", function () { decorate(); });

  // The page opens behind an access code: load once the app is shown, and again if the link changes.
  var app = document.getElementById("cat-app");
  if (app && app.hidden && window.MutationObserver) {
    new MutationObserver(function () { if (!app.hidden) load(); }).observe(app, { attributes: true, attributeFilter: ["hidden"] });
  }
  window.addEventListener("hashchange", function () { loadedFor = null; load(); });
  if (marketPage) openMI();
  else if (!app || !app.hidden) load();
})();
