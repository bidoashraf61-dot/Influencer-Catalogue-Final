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
        data = j.evidence; brandIx = 0; draw(); decorate();
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
    var brand = el("span", "ev-post__brand", p.competitor); brand.style.background = colours[p.competitor] || "#121212";
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

  function fill(bd, code, c, preview) {
    var S = sel();
    if (preview) bd.appendChild(el("p", "ev-chip ev-chip--paid", "Preview — not shared with the client yet"));
    var meta = "@" + c.handle + (c.type === "hcp" ? " · Doctor / pharmacist" : c.type === "ugc" ? " · UGC creator" : "");
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
      b.appendChild(dot); b.appendChild(document.createTextNode(k.name + " · " + k.posts));
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

  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && panel) closePanel(); });
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
  if (!app || !app.hidden) load();
})();
