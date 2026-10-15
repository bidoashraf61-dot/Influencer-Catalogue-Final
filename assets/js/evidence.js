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
    head.appendChild(el("p", "ev-eyebrow", "Competitor evidence"));
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
        if (window.hvSelection && window.hvSelection.setTrack && data.by_code) window.hvSelection.setTrack(Object.keys(data.by_code));
      })
      .catch(function () { loadedFor = null; });
  }


  /* ---------------- Track record: a button on each creator card, opening the posts panel ---------------- */

  var grid = document.getElementById("cat-grid");
  var panel = null, lastFocus = null;

  function sel() { return window.hvSelection || null; }

  function decorate() {
    if (!grid || !data || !data.by_code) return;
    [].forEach.call(grid.querySelectorAll("article.cat-card[data-code]"), function (card) {
      var code = card.getAttribute("data-code"), info = data.by_code[code];
      var have = card.querySelector(".ev-tr");
      var badge = card.querySelector(".ev-trbadge");
      if (!info) { if (have) have.remove(); if (badge) badge.remove(); return; }
      if (!badge) {
        // On the card itself, not only in Details (owner, 2026-10-15): who already posted for a competitor.
        badge = el("span", "ev-trbadge", "Track record");
        badge.title = "Posted for " + info.brands + (info.brands === 1 ? " competitor" : " competitors") + " of this brand";
        var bd = card.querySelector(".cat-card__body");
        if (bd) bd.insertBefore(badge, bd.firstChild); else card.appendChild(badge);
      }
      if (have) return;
      var b = el("button", "ev-tr");
      b.type = "button";
      b.setAttribute("data-noselect", "");
      b.setAttribute("aria-haspopup", "dialog");
      b.appendChild(icon("posts", "ev-tr__ic"));
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

  /* Drawn icons (one stroke family), never glyphs. */
  var SVGNS = "http://www.w3.org/2000/svg";
  var ICON = {
    posts: "M4 5h16v14H4zM4 15l4-4 4 4 3-3 5 5",
    lock: "M7 11V8a5 5 0 0 1 10 0v3M5.5 11h13v9h-13z",
    plus: "M12 5v14M5 12h14",
    chart: "M4 20h16M7 16v-4M11 16V9M15 16v-6M19 16V6",
    send: "M4 12l16-8-6 16-2.5-6.5z",
    check: "M5 12.5l4.5 4.5L19 7.5",
    back: "M15 5l-7 7 7 7",
    zin: "M12 6v12M6 12h12", zout: "M6 12h12", reset: "M5 12a7 7 0 1 0 2-5M5 4v4h4",
    play: "M8 5.5v13l11-6.5z"
  };
  function icon(name, cls) {
    var s = document.createElementNS(SVGNS, "svg");
    s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("aria-hidden", "true");
    s.setAttribute("class", "ev-ic" + (cls ? " " + cls : ""));
    var p = document.createElementNS(SVGNS, "path"); p.setAttribute("d", ICON[name]);
    if (name === "play") p.setAttribute("fill", "currentColor");
    s.appendChild(p);
    return s;
  }
  function btn(cls, ic, text) {
    var b = el("button", cls); b.type = "button";
    if (ic) b.appendChild(icon(ic));
    b.appendChild(el("span", "", text));
    return b;
  }
  function linkBtn(cls, ic, text, href) {
    var a = el("a", cls); a.href = href;
    if (ic) a.appendChild(icon(ic));
    a.appendChild(el("span", "", text));
    return a;
  }
  function svg(tag, attrs) {
    var n = document.createElementNS(SVGNS, tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    return n;
  }
  function median(xs) {
    xs = xs.filter(function (v) { return v != null; }).sort(function (a, b) { return a - b; });
    if (!xs.length) return null;
    return xs.length % 2 ? xs[(xs.length - 1) / 2] : (xs[xs.length / 2 - 1] + xs[xs.length / 2]) / 2;
  }
  var HIDDEN = "—";

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

  // A brand is always its logo; the name stays as the accessible label and only shows when no logo is approved yet.
  function logoEl(name, url, cls) {
    if (url) {
      var i = el("img", "ev-logo" + (cls ? " " + cls : "")); i.src = (CFG.api || "") + url; i.alt = name; i.title = name; i.decoding = "async";
      return i;
    }
    return el("span", "ev-logo ev-logo--txt" + (cls ? " " + cls : ""), name);
  }

  /* One panel for both doors (owner, 2026-10-15): the Track record button on a selection card and a photo
     on the map open the same thing, the creator's posts for competitors and how each one did. No charts,
     no score: a few headline figures, the brand chips, the posts. */
  function postsBlock(bd, posts, comps, logoOf) {
    var organic = posts.filter(function (q) { return !q.paid_boost; });
    var views = organic.map(function (q) { return q.views; }).filter(function (v) { return v != null; });
    var ers = organic.map(function (q) { return q.er; }).filter(function (v) { return v != null; });
    var kv = el("div", "ev-kv ev-kv--4");
    kv.appendChild(tile(posts.length, posts.length === 1 ? "post with a competitor" : "posts with competitors"));
    kv.appendChild(tile(num(median(views)), "typical views"));
    kv.appendChild(tile(num(views.length ? Math.max.apply(null, views) : null), "best post"));
    kv.appendChild(tile(ers.length ? pct(median(ers)) : HIDDEN, ers.length ? "engagement" : "engagement (likes hidden)"));
    bd.appendChild(kv);

    var active = null, shown = 6;
    var names = Object.keys(comps);
    var strip = el("div", "ev-pn__brands"); strip.setAttribute("role", "group"); strip.setAttribute("aria-label", "Show posts for");
    function chip(name) {
      var b = el("button", "ev-brand ev-brand--logo" + (name ? "" : " ev-brand--all")); b.type = "button";
      if (name) {
        b.setAttribute("aria-label", name + ", " + comps[name] + (comps[name] === 1 ? " post" : " posts"));
        b.appendChild(logoEl(name, logoOf(name), "ev-logo--chip"));
        b.appendChild(el("span", "ev-brand__n", String(comps[name])));
      } else {
        b.appendChild(el("span", "", "All brands"));
        b.appendChild(el("span", "ev-brand__n", String(posts.length)));
      }
      b.addEventListener("click", function () { active = name; shown = 6; paint(); draw2(); });
      strip.appendChild(b);
      return b;
    }
    if (names.length > 1) { chip(null); names.forEach(chip); }
    function paint() {
      strip.classList.toggle("is-picked", !!active);
      [].forEach.call(strip.children, function (c2, i) {
        var nm = i === 0 ? null : names[i - 1];
        c2.setAttribute("aria-pressed", nm === active ? "true" : "false");
      });
    }
    paint();
    if (names.length > 1) bd.appendChild(strip);
    var host = el("div", "ev-posts-host"), gridEl = el("div", "ev-dgrid"), moreBtn = el("button", "ev-act ev-more", ""); moreBtn.type = "button";
    host.appendChild(gridEl); bd.appendChild(host); bd.appendChild(moreBtn);
    moreBtn.addEventListener("click", function () { shown += 6; draw2(); });
    function draw2() {
      var ps = posts.filter(function (q) { return !active || q.competitor === active; });
      gridEl.textContent = "";
      ps.slice(0, shown).forEach(function (q) { gridEl.appendChild(dashPost(q, host, logoOf)); });
      LIVEPOST.watch(gridEl);
      moreBtn.hidden = ps.length <= shown;
      moreBtn.textContent = "See more posts (" + (ps.length - shown) + ")";
    }
    draw2();
  }

  // The panel's frame: photo, name, one line of who they are, the actions; the body is filled by the caller.
  function panelFrame(o) {
    var scrim = el("div", "ev-pn__scrim" + (o.top ? " ev-pn__scrim--top" : "")), aside = el("aside", "ev-pn ev-cp" + (o.top ? " ev-pn--top" : ""));
    aside.setAttribute("role", "dialog"); aside.setAttribute("aria-modal", "true"); aside.setAttribute("aria-labelledby", "ev-cp-t");
    var hd = el("header", "ev-cp__hd");
    var ph = el("span", "ev-cp__ph" + (o.hcp ? " is-hcp" : "") + (o.locked ? " is-locked" : ""));
    if (o.photo) { var im = el("img"); im.src = o.photo; im.alt = ""; ph.appendChild(im); }
    else ph.appendChild(el("span", "ev-cp__ini", initials(o.name)));
    hd.appendChild(ph);
    var who = el("div", "ev-cp__who");
    var h = el("h2", "ev-pn__t", o.name); h.id = "ev-cp-t";
    who.appendChild(h);
    who.appendChild(el("p", "ev-mut", o.meta));
    var acts = el("div", "ev-cp__acts");
    who.appendChild(acts);
    hd.appendChild(who);
    var x = el("button", "ev-pn__x"); x.type = "button"; x.setAttribute("aria-label", "Close"); x.appendChild(el("span", "", "×"));
    hd.appendChild(x);
    aside.appendChild(hd);
    var bd = el("div", "ev-pn__bd");
    aside.appendChild(bd);
    document.body.appendChild(scrim); document.body.appendChild(aside);
    return { scrim: scrim, aside: aside, acts: acts, bd: bd, x: x };
  }
  function initials(name) {
    return ((name || "?").replace(/[^\p{L}\p{N} ]/gu, "").trim().split(/\s+/).map(function (w) { return w.charAt(0); }).slice(0, 2).join("") || "?").toUpperCase();
  }
  function analysisHref(code) { return "/creator/#c=" + encodeURIComponent(code); }

  function openPanel(code, from) {
    closePanel();
    lastFocus = from || document.activeElement;
    var S = sel(), who = S && S.creator ? S.creator(code) : null;
    var f = panelFrame({ name: (who && who.name) || code, meta: "Loading…", hcp: who && who.doctor });
    f.x.addEventListener("click", closePanel);
    f.scrim.addEventListener("click", closePanel);
    document.body.classList.add("pt-lock");
    panel = { scrim: f.scrim, aside: f.aside, code: code };
    f.x.focus();
    f.bd.appendChild(el("p", "ev-mut", "Loading the posts…"));
    fetch((CFG.api || "") + "/api/evidence/creator?s=" + encodeURIComponent(token()) + "&c=" + encodeURIComponent(code), { credentials: "include" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!panel || panel.code !== code) return;
        f.bd.textContent = "";
        if (!j || !j.ok || !j.creator) { f.aside.querySelector(".ev-mut").textContent = ""; f.bd.appendChild(el("p", "ev-mut", "No competitor posts found for this creator.")); return; }
        fill(f, code, j.creator);
      })
      .catch(function () { if (panel) { f.bd.textContent = ""; f.bd.appendChild(el("p", "ev-mut", "Could not load the posts. Close and try again.")); } });
  }

  function fill(f, code, c) {
    var logos = c.logos || (data && data.logos) || {};
    var S = sel();
    var hcp = c.type === "hcp";
    f.aside.querySelector(".ev-cp__who .ev-mut").textContent = "@" + c.handle + " · " + (hcp ? "Doctor / pharmacist" : "Influencer") + " · posts with your competitors";
    if (c.photo) {
      var ph = f.aside.querySelector(".ev-cp__ph"); ph.textContent = "";
      var im = el("img"); im.src = c.photo; im.alt = ""; ph.appendChild(im);
    }
    f.aside.querySelector(".ev-cp__ph").classList.toggle("is-hcp", hcp);
    f.acts.appendChild(linkBtn("ev-act", "chart", "Profile analysis", analysisHref(code)));
    var comps = {};
    c.competitors.forEach(function (k) { comps[k.name] = k.posts; });
    postsBlock(f.bd, c.posts, comps, function (n) { return logos[n]; });

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
      f.bd.appendChild(ft);
    }
  }

  function setStatus(code, status, btn2) {
    btn2.disabled = true;
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
        } else { btn2.disabled = false; if (S && S.toast) S.toast("That did not save. Try again."); }
      }).catch(function () { btn2.disabled = false; });
  }

  /* ---------------- Market Intelligence: map, ranking list, creator panel ---------------- */

  var mi = null, miData = null, miFilter = { type: "all", platform: "all" }, miFocus = null, miView = { k: 1, x: 0, y: 0 }, miListN = 20, miIntro = true;
  var XLINK = "http://www.w3.org/1999/xlink";
  var CALM = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // In the header's action row, beside the ROI Calculator (owner, 2026-10-15). That row is drawn by
  // connect.js and can arrive a moment later; without it the button sits under the title as before.
  function miButton(tries) {
    if (document.getElementById("ev-mi-btn")) return;
    var row = document.getElementById("cx-selact");
    var title = document.getElementById("sel-title");
    if (!row && (tries || 0) < 40) { setTimeout(function () { miButton((tries || 0) + 1); }, 150); return; }
    if (!row && (!title || !title.parentNode)) return;
    var b = el("a", "ev-mi-btn"); b.id = "ev-mi-btn";
    b.href = "/market/#s=" + encodeURIComponent(token());
    b.appendChild(el("span", "ev-mi-btn__ic", "\u25CE"));
    b.appendChild(document.createTextNode("Market Intelligence"));
    if (row) row.appendChild(b);
    else title.parentNode.insertBefore(b, title.nextSibling);
  }

  function compLogo(name) {
    var c = miData && miData.competitors.filter(function (x) { return x.name === name; })[0];
    return c ? c.logo : (data && data.logos ? data.logos[name] : null);
  }
  function rankText(p) { return miData.rank_by === "interactions" ? num(p.rank_value) + " interactions" : num(p.rank_value) + " views"; }
  // Estimated range per post from the creator's competitor work (owner, 2026-10-15): views for awareness,
  // likes + comments for engagement / conversion.
  function estUnit() { return miData.rank_by === "interactions" ? "engagements" : "views"; }
  function estText(p) {
    var e = p.estimate;
    if (!e) return "";
    return (e.lo === e.hi ? "~" + num(e.mid) : num(e.lo) + "\u2013" + num(e.hi)) + " " + estUnit() + " / post";
  }
  function rankLabel() { return miData.rank_by === "interactions" ? "likes + comments" : "views"; }
  function typeOf(p) { return p.type === "hcp" ? "hcp" : "influencer"; }
  function kept(p) {
    return (miFilter.type === "all" || typeOf(p) === miFilter.type) && (miFilter.platform === "all" || p.platforms.indexOf(miFilter.platform) >= 0);
  }

  // Market Intelligence has its own page: /market/#s=<selection token> (market/index.html).
  function openMI() {
    var root = document.getElementById("ev-market");
    if (!root) return;
    root.textContent = "";
    var hd = el("header", "ev-mi__hd");
    var backSel = linkBtn("ev-act", "back", "Back to selection", "/selection/#s=" + encodeURIComponent(token()));
    hd.appendChild(backSel);
    var t = el("div", "ev-mi__title");
    var h = el("h1", "ev-mi__t", "Who works with your competitors"); h.id = "ev-mi-t"; t.appendChild(h);
    var scope = el("p", "ev-mi__scope"); scope.id = "ev-mi-scope"; t.appendChild(scope);
    hd.appendChild(t);
    var body = el("div", "ev-mi__bd"); body.appendChild(el("p", "ev-mut", "Loading the map…"));
    root.appendChild(hd); root.appendChild(body);
    mi = { root: root, body: body, scope: scope };
    var go = function (d) { miData = d; miFocus = null; miView = { k: 1, x: 0, y: 0 }; miListN = 20; drawMI(); };
    fetch((CFG.api || "") + "/api/evidence/map?s=" + encodeURIComponent(token()), { credentials: "include" })
      .then(function (r) { return r.status === 401 ? { locked: true } : r.ok ? r.json() : null; })
      .then(function (j) {
        if (j && j.ok && j.map) return go(j.map);
        body.textContent = "";
        body.appendChild(el("p", "ev-mut", j && j.locked ? "Open this from your selection page first (it asks for your access code)." : "Market Intelligence is not available for this selection."));
      })
      .catch(function () { body.textContent = ""; body.appendChild(el("p", "ev-mut", "Could not load the map.")); });
  }

  // Platform marks instead of the words (owner, 2026-10-15); the same drawings as the creator cards.
  var TT_G = '<path d="M14.2 3v11.6a3.6 3.6 0 1 1-3.6-3.6"/><path d="M14.2 3.2c.45 2.7 2.05 4.3 4.75 4.6"/>';
  var PLAT_SVG = {
    instagram: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4.1"/><circle cx="17.3" cy="6.7" r="1.15" fill="currentColor" stroke="none"/></svg>',
    tiktok: '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><g stroke="#25f4ee" transform="translate(-1,-.85)">' + TT_G +
      '</g><g stroke="#fe2c55" transform="translate(1,.85)">' + TT_G + '</g><g stroke="currentColor">' + TT_G + "</g></svg>"
  };
  function chips(label, opts, key) {
    var g = el("div", "ev-mi__chips"); g.setAttribute("role", "group"); g.setAttribute("aria-label", label);
    opts.forEach(function (o) {
      var b = el("button", "ev-brand ev-brand--txt", PLAT_SVG[o[0]] ? "" : o[1]); b.type = "button";
      if (PLAT_SVG[o[0]]) { b.innerHTML = PLAT_SVG[o[0]]; b.classList.add("ev-brand--ic", "ev-brand--" + o[0]); b.setAttribute("aria-label", o[1]); b.title = o[1]; }
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

  // Photo size by views on a log scale (owner, 2026-10-15): views run from thousands to millions, so a
  // square-root scale left almost every photo the same size. Brand logos stay the biggest thing on the map
  // (owner, 2026-10-15): photos run 24 to 38 (focus: 28 to 44), under the smallest competitor logo (56) and
  // the centre brand (96 / 104), and the gap between a small and a big creator is kept narrow.
  function sizer(list) {
    var vs = list.map(function (p) { return p.rank_value || 0; }).filter(function (v) { return v > 0; });
    var lo = vs.length ? Math.min.apply(null, vs) : 1, hi = vs.length ? Math.max.apply(null, vs) : 1;
    var a = miFocus ? 28 : 24, b = miFocus ? 44 : 38;
    var L = function (v) { return Math.log10(Math.max(v, 1)); };
    var f = function (v) { return hi > lo ? (L(v) - L(lo)) / (L(hi) - L(lo)) : 0.5; };
    var r = function (p) { return a + (b - a) * Math.max(0, Math.min(1, f(p.rank_value || lo))); };
    r.lo = lo; r.hi = hi; r.a = a; r.b = b;
    return r;
  }

  function sizeLegend(r) {
    var box = el("span", "ev-legend__size");
    var s = svg("svg", { viewBox: "0 0 92 40", width: "92", height: "40", "aria-hidden": "true" });
    s.appendChild(svg("circle", { cx: 9, cy: 30, r: 8, class: "ev-legend__dot" }));
    s.appendChild(svg("circle", { cx: 34, cy: 26, r: 12, class: "ev-legend__dot" }));
    s.appendChild(svg("circle", { cx: 70, cy: 20, r: 18, class: "ev-legend__dot" }));
    box.appendChild(s);
    box.appendChild(el("span", "", "Photo size = " + rankLabel() + ", " + num(r.lo) + " to " + num(r.hi)));
    return box;
  }

  function drawMI() {
    var d = miData, body = mi.body;
    // Smooth filtering (owner, 2026-10-15): remember where each creator was, so after the redraw the ones
    // still on show glide from there, new ones pop in, and the projected figure counts to its new value.
    var prev = {};
    if (mi.svg && mi.svg.__dots) mi.svg.__dots.forEach(function (dd) { prev[dd.__h] = { x: dd.__x, y: dd.__y }; });
    var prevProj = mi.projMid;
    body.textContent = "";
    // Which of the selection's creators are on the map, and why the others are not (owner, 2026-10-15).
    if (mi.scope) {
      var n = d.on_map || 0, tot = d.selection_size || n;
      mi.scope.textContent = n + " of " + tot + " creators in this selection have posted with your competitors. Only they appear on the map; the rest of the selection has no competitor posts.";
    }
    var people = d.creators.filter(kept);
    var size = sizer(visible(people));
    var bar = el("div", "ev-mi__bar");
    var hasTT = d.creators.some(function (c) { return c.platforms.indexOf("tiktok") >= 0; });
    bar.appendChild(chips("Platform", [["all", "All platforms"], ["instagram", "Instagram"], ["tiktok", "TikTok", hasTT ? "" : "TikTok study not in yet"]], "platform"));
    bar.appendChild(chips("Creator type", [["all", "Everyone"], ["hcp", "Doctors / pharmacists"], ["influencer", "Influencers"]], "type"));
    // Projected range for the creators on show (owner, 2026-10-15): one post each, from their competitor
    // work: typical (median) in the middle, lowest to highest around it. Follows the filters and the objective.
    var pj = { lo: 0, mid: 0, hi: 0, n: 0 };
    people.forEach(function (p) { var e = p.estimate; if (!e || p.locked) return; pj.lo += e.lo; pj.mid += e.mid; pj.hi += e.hi; pj.n++; });
    if (pj.n) {
      var pjb = el("div", "ev-proj"); pjb.setAttribute("role", "status");
      pjb.appendChild(el("small", "", "Projected " + estUnit()));
      var pjv = el("b", "", num(pj.mid));
      pjb.appendChild(pjv);
      countUp(pjv, prevProj, pj.mid);
      mi.projMid = pj.mid;
      pjb.appendChild(el("span", "", num(pj.lo) + " \u2013 " + num(pj.hi) + " · " + pj.n + (pj.n === 1 ? " creator" : " creators") + " · one post each"));
      pjb.title = "Typical " + estUnit() + " if each creator shown posts once, from their posts with your competitors; range = their lowest to highest.";
      bar.appendChild(pjb);
    }
    var leg = el("div", "ev-legend");
    var hk = el("span", "ev-legend__item"); hk.appendChild(el("i", "ev-legend__hcp")); hk.appendChild(document.createTextNode("Doctor / pharmacist"));
    leg.appendChild(hk);
    if (d.creators.some(function (p) { return p.locked; })) {
      var lk = el("span", "ev-legend__item"); var li = el("i", "ev-legend__lock"); li.appendChild(icon("lock")); lk.appendChild(li); lk.appendChild(document.createTextNode("Unavailable, ask us"));
      leg.appendChild(lk);
    }
    leg.appendChild(sizeLegend(size));
    bar.appendChild(leg);
    body.appendChild(bar);

    var layout = el("div", "ev-mi__layout");
    var stage = el("div", "ev-mi__stage" + (miIntro && !CALM ? " is-intro" : ""));
    if (miIntro) setTimeout(function () { stage.classList.remove("is-intro"); }, 1400);
    miIntro = false;
    var tools = el("div", "ev-mi__tools");
    if (miFocus) {
      var back = btn("ev-act ev-act--yes", "back", "All competitors");
      back.addEventListener("click", function () { miFocus = null; miView = { k: 1, x: 0, y: 0 }; miListN = 20; drawMI(); });
      tools.appendChild(back);
    }
    [["zin", 1.25, "Zoom in"], ["zout", 0.8, "Zoom out"], ["reset", 0, "Reset view"]].forEach(function (z) {
      var b = el("button", "ev-zoom"); b.type = "button"; b.setAttribute("aria-label", z[2]); b.title = z[2]; b.appendChild(icon(z[0]));
      b.addEventListener("click", function () { if (!z[1]) miView = { k: 1, x: 0, y: 0 }; else miView.k = Math.max(0.6, Math.min(4, miView.k * z[1])); applyView(); });
      tools.appendChild(b);
    });
    stage.appendChild(tools);
    var svgEl = mapSvg(d, people, stage, size);
    stage.appendChild(svgEl);
    layout.appendChild(stage);
    layout.appendChild(rankList(people));
    body.appendChild(layout);
    if (d.outside && d.outside.length) body.appendChild(outsideStrip(d.outside));
    mi.svg = svgEl;
    applyView();
    glide(svgEl, prev);
  }

  function glide(svgEl, prev) {
    var dots = svgEl.__dots || [];
    if (CALM || !Object.keys(prev).length) return;
    dots.forEach(function (dd) {
      var o = prev[dd.__h];
      if (o) { dd.style.transition = "none"; dd.style.transform = "translate(" + (o.x - dd.__x).toFixed(1) + "px," + (o.y - dd.__y).toFixed(1) + "px)"; }
      else dd.classList.add("is-new");
    });
    var lines = svgEl.querySelector(".ev-map__links");
    if (lines) lines.classList.add("is-fresh");
    void svgEl.getBoundingClientRect();
    requestAnimationFrame(function () {
      dots.forEach(function (dd) { if (prev[dd.__h]) { dd.style.transition = "transform .7s cubic-bezier(.16, 1, .3, 1), opacity .3s ease"; dd.style.transform = ""; } });
      setTimeout(function () { dots.forEach(function (dd) { dd.style.transition = ""; }); }, 750);
    });
  }

  function countUp(node, from, to) {
    if (CALM || from == null || from === to) { node.textContent = num(to); return; }
    var t0 = null, dur = 700;
    var step = function (t) {
      if (t0 === null) t0 = t;
      var k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      node.textContent = num(Math.round(from + (to - from) * e));
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  // One view update per frame, and no hover transitions while the map is being dragged or zoomed.
  var viewRaf = 0, moveT = 0;
  function applyViewSoon() { if (!viewRaf) viewRaf = requestAnimationFrame(function () { viewRaf = 0; applyView(); }); }
  function moving() {
    if (!mi || !mi.svg) return;
    mi.svg.classList.add("is-moving");
    clearTimeout(moveT); moveT = setTimeout(function () { if (mi && mi.svg) mi.svg.classList.remove("is-moving"); }, 160);
  }
  function applyView() {
    if (!mi || !mi.svg) return;
    var g = mi.svg.querySelector(".ev-map__world");
    if (g) g.setAttribute("transform", "translate(" + miView.x + " " + miView.y + ") scale(" + miView.k + ")");
  }

  function mapSvg(d, people, stage, dotR) {
    var W = 1400, H = 820, cx = W / 2, cy = H / 2;
    var g = svg("svg", { viewBox: "0 0 " + W + " " + H, class: "ev-map", role: "img",
      "aria-label": "Your brand in the centre and its competitors around it, each with its best creators." });
    var defs = svg("defs"); g.appendChild(defs);
    // A soft lift under the brand discs and photos, in place of a hard outline.
    var sh = svg("filter", { id: "ev-lift", x: "-30%", y: "-30%", width: "160%", height: "160%" });
    sh.appendChild(svg("feDropShadow", { dx: 0, dy: 6, stdDeviation: 7, "flood-color": "#121212", "flood-opacity": 0.16 }));
    defs.appendChild(sh);
    var sh2 = svg("filter", { id: "ev-lift-s", x: "-30%", y: "-30%", width: "160%", height: "160%" });
    sh2.appendChild(svg("feDropShadow", { dx: 0, dy: 3, stdDeviation: 3.5, "flood-color": "#121212", "flood-opacity": 0.22 }));
    defs.appendChild(sh2);
    var grey = svg("filter", { id: "ev-grey" });
    grey.appendChild(svg("feColorMatrix", { type: "saturate", values: "0" }));
    defs.appendChild(grey);
    var world = svg("g", { class: "ev-map__world" }); g.appendChild(world);
    var links2 = svg("g", { class: "ev-map__links" }), nodes = svg("g", { class: "ev-map__nodes" }), hubs = svg("g", { class: "ev-map__hubs" });
    world.appendChild(links2); world.appendChild(nodes); world.appendChild(hubs);
    var vis = visible(people);
    var placed = [], pos = {}, dots = [], compEls = {};
    function free(x, y, r) { return placed.every(function (q) { var dx = q.x - x, dy = q.y - y; return dx * dx + dy * dy >= (q.r + r + 4) * (q.r + r + 4); }); }
    function place(x, y, r) {
      for (var k = 0; k < 320; k++) {
        var ang = k * 2.4, rad = k * 2.1, xx = x + rad * Math.cos(ang), yy = y + rad * Math.sin(ang);
        if (xx > r + 6 && xx < W - r - 6 && yy > r + 6 && yy < H - r - 6 && free(xx, yy, r)) { placed.push({ x: xx, y: yy, r: r }); return { x: xx, y: yy }; }
      }
      placed.push({ x: x, y: y, r: r }); return { x: x, y: y };
    }
    function bubble(name, url, x, y, r, big) {
      var gg = svg("g", { class: "ev-map__comp" + (big ? " ev-map__comp--hub" : ""), tabindex: big ? "-1" : "0", role: big ? "img" : "button", "aria-label": name });
      var id = "evl" + (++dotSeq);
      var clip = svg("clipPath", { id: id }); clip.appendChild(svg("circle", { cx: x, cy: y, r: r - 3 })); defs.appendChild(clip);
      // Speed (owner, 2026-10-15): a soft offset disc stands in for the blur filter, which the browser
      // recomputed on every repaint.
      gg.appendChild(svg("circle", { cx: x, cy: y + 5, r: r + 2, class: "ev-map__shadow" }));
      gg.appendChild(svg("circle", { cx: x, cy: y, r: r, class: "ev-map__disc" }));
      if (big) gg.appendChild(svg("circle", { cx: x, cy: y, r: r + 9, class: "ev-map__halo" }));
      gg.appendChild(svg("circle", { cx: x, cy: y, r: r + 4, class: "ev-map__focus" }));
      if (url) {
        var im = svg("image", { x: x - r * 0.78, y: y - r * 0.78, width: r * 1.56, height: r * 1.56, preserveAspectRatio: "xMidYMid meet", "clip-path": "url(#" + id + ")" });
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
      // they did most posts for) and fans out around it. Lines to their other competitors light up on hover.
      var n = d.competitors.length, RX = n > 1 ? 470 : 0, RY = n > 1 ? 262 : 0;
      var maxV = Math.max.apply(null, d.competitors.map(function (c) { return c.views; }).concat([1]));
      d.competitors.forEach(function (c, i) {
        var a = -Math.PI / 2 + i * 2 * Math.PI / Math.max(n, 1);
        pos[c.name] = { x: cx + RX * Math.cos(a), y: cy + RY * Math.sin(a), a: a, r: 56 + 20 * Math.sqrt(c.views / maxV) };
      });
      placed.push({ x: cx, y: cy, r: 106 });
      d.competitors.forEach(function (c) { var p = pos[c.name]; [-60, -30, 0, 30, 60].forEach(function (dx) { placed.push({ x: p.x + dx, y: p.y + p.r + 19, r: 15 }); }); placed.push({ x: p.x, y: p.y, r: p.r + 6 }); links2.appendChild(svg("line", { x1: cx, y1: cy, x2: p.x, y2: p.y, class: "ev-map__spoke", "data-comp": c.name })); });
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
          var dist = cp.r + r + 26 + ring * 80;
          var at = place(cp.x + dist * Math.cos(a), cp.y + dist * Math.sin(a), r);
          var ks = Object.keys(p.competitors).filter(function (k2) { return pos[k2]; });
          var mine = ks.map(function (k2) { var l = svg("line", { x1: at.x, y1: at.y, x2: pos[k2].x, y2: pos[k2].y, class: k2 === k ? "ev-map__own" : "ev-map__share" }); links2.appendChild(l); return l; });
          var dd = dot(p, at, r, defs, stage, ks.length > 1, mine);
          dd.__comps = ks; dd.__lines = mine; dots.push(dd);
          nodes.appendChild(dd);
        });
      });
      hubs.appendChild(bubble(d.brand, d.brand_logo, cx, cy, 96, true));
      d.competitors.forEach(function (c) {
        var p = pos[c.name], b = bubble(c.name, c.logo, p.x, p.y, p.r);
        var all = people.filter(function (q) { return q.competitors[c.name]; }).length;
        var more = svg("text", { x: p.x, y: p.y + p.r + 25, "text-anchor": "middle", class: "ev-map__cnum" });
        more.textContent = num(c.views) + " views · " + all + (all === 1 ? " creator" : " creators");
        b.appendChild(more);
        var go = function () { miFocus = c.name; miView = { k: 1, x: 0, y: 0 }; miListN = 30; drawMI(); };
        b.addEventListener("click", go);
        b.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
        // Pointing at a brand lights its creators and dims the rest.
        b.addEventListener("mouseenter", function () { spot(function (dd) { return dd.__comps.indexOf(c.name) >= 0; }, c.name); });
        b.addEventListener("focus", function () { spot(function (dd) { return dd.__comps.indexOf(c.name) >= 0; }, c.name); });
        b.addEventListener("mouseleave", unspot); b.addEventListener("blur", unspot);
        compEls[c.name] = b;
        hubs.appendChild(b);
      });
    } else {
      // Focus: one competitor in the centre, its creators in rings, names under the photos.
      var fc = d.competitors.filter(function (c) { return c.name === miFocus; })[0] || { name: miFocus };
      placed.push({ x: cx, y: cy, r: 114 });
      vis.forEach(function (p, i) {
        var r = dotR(p), ring = i < 8 ? 0 : i < 20 ? 1 : 2, idx = ring === 0 ? i : ring === 1 ? i - 8 : i - 20, cnt = ring === 0 ? 8 : 12;
        var a = -Math.PI / 2 + idx * 2 * Math.PI / cnt + (ring === 1 ? 0.26 : 0), rad = 205 + ring * 125;
        var at = place(cx + rad * 1.55 * Math.cos(a), cy + rad * Math.sin(a), r);
        links2.appendChild(svg("line", { x1: at.x, y1: at.y, x2: cx, y2: cy, class: "ev-map__own" }));
        var dd = dot(p, at, r, defs, stage, Object.keys(p.competitors).length > 1, []);
        dd.__comps = [miFocus]; dots.push(dd);
        var nm = svg("text", { x: at.x, y: at.y + r + 15, "text-anchor": "middle", class: "ev-map__nm" });
        nm.textContent = (p.name || p.handle).replace(/[|•·].*$/, "").trim().slice(0, 18); dd.appendChild(nm);
        nodes.appendChild(dd);
      });
      hubs.appendChild(bubble(fc.name, fc.logo, cx, cy, 104, true));
    }

    function spot(test, comp) {
      stage.classList.add("is-spot");
      dots.forEach(function (dd) { dd.classList.toggle("is-hot", test(dd)); });
      [].forEach.call(links2.querySelectorAll(".ev-map__spoke"), function (l) { l.classList.toggle("is-hot", l.getAttribute("data-comp") === comp); });
    }
    function unspot() {
      stage.classList.remove("is-spot");
      dots.forEach(function (dd) { dd.classList.remove("is-hot"); });
      [].forEach.call(links2.querySelectorAll(".is-hot"), function (l) { l.classList.remove("is-hot"); });
    }
    g.__spot = spot; g.__unspot = unspot; g.__dots = dots;

    // Pan by dragging, zoom with the wheel.
    var drag = null;
    g.addEventListener("wheel", function (e) { e.preventDefault(); miView.k = Math.max(0.6, Math.min(4, miView.k * (e.deltaY < 0 ? 1.1 : 0.9))); moving(); applyViewSoon(); }, { passive: false });
    g.addEventListener("pointerdown", function (e) { if (e.target.closest && e.target.closest(".ev-map__dot, .ev-map__comp")) return; drag = { x: e.clientX, y: e.clientY, ox: miView.x, oy: miView.y }; g.setPointerCapture(e.pointerId); });
    g.addEventListener("pointermove", function (e) {
      if (!drag) return; var s = W / g.getBoundingClientRect().width;
      miView.x = drag.ox + (e.clientX - drag.x) * s; miView.y = drag.oy + (e.clientY - drag.y) * s; moving(); applyViewSoon();
    });
    g.addEventListener("pointerup", function () { drag = null; });
    return g;
  }

  var dotSeq = 0;
  function dot(p, at, r, defs, stage, shared, lines) {
    var lockd = !!p.locked;
    var gg = svg("g", { class: "ev-map__dot" + (p.paid_only ? " ev-map__dot--paid" : "") + (lockd ? " is-locked" : ""), tabindex: "0", role: "button",
      "aria-label": (p.name || p.handle) + ", " + rankText(p) + (p.estimate ? ", estimated " + estText(p) : "") + (lockd ? ", unavailable" : "") + ". Open creator.",
      style: "transform-origin:" + at.x.toFixed(1) + "px " + at.y.toFixed(1) + "px;--d:" + Math.round(Math.random() * 260) + "ms" });
    gg.__h = p.handle; gg.__x = at.x; gg.__y = at.y;
    var hint = svg("title"); hint.textContent = (p.name || "@" + p.handle) + (p.estimate ? "\nEst. " + estText(p) : ""); gg.appendChild(hint);
    var id = "evc" + (++dotSeq);
    var clip = svg("clipPath", { id: id }); clip.appendChild(svg("circle", { cx: at.x, cy: at.y, r: r })); defs.appendChild(clip);
    gg.appendChild(svg("circle", { cx: at.x, cy: at.y + 2.5, r: r + 3, class: "ev-map__shadow ev-map__shadow--s" }));
    gg.appendChild(svg("circle", { cx: at.x, cy: at.y, r: r + 2.5, class: "ev-map__bg" }));
    if (p.photo) {
      var im = svg("image", { x: at.x - r, y: at.y - r, width: 2 * r, height: 2 * r, "clip-path": "url(#" + id + ")", preserveAspectRatio: "xMidYMid slice" });
      if (lockd) im.setAttribute("filter", "url(#ev-grey)");
      im.setAttributeNS(XLINK, "href", p.photo); im.setAttribute("href", p.photo);
      gg.appendChild(im);
    } else {
      gg.appendChild(svg("circle", { cx: at.x, cy: at.y, r: r, class: "ev-map__inibg" }));
      var ini = svg("text", { x: at.x, y: at.y + Math.max(4, r * 0.18), "text-anchor": "middle", class: "ev-map__ini", "font-size": Math.max(11, r * 0.5).toFixed(0) });
      ini.textContent = initials(p.name || p.handle);
      gg.appendChild(ini);
    }
    gg.appendChild(svg("circle", { cx: at.x, cy: at.y, r: r + 1.5, class: "ev-map__ring" }));
    // Doctors and pharmacists carry a green cross; influencers carry nothing. One mark, one meaning.
    var bx = at.x + r * 0.7, by = at.y + r * 0.7, br = Math.max(7, Math.min(11, r * 0.26));
    if (typeOf(p) === "hcp") {
      var hb = svg("g", { class: "ev-map__hcp" });
      hb.appendChild(svg("circle", { cx: bx, cy: by, r: br }));
      hb.appendChild(svg("path", { d: "M" + (bx - br * 0.5) + " " + by + "H" + (bx + br * 0.5) + "M" + bx + " " + (by - br * 0.5) + "V" + (by + br * 0.5) }));
      gg.appendChild(hb);
    }
    if (lockd) {
      var lb = svg("g", { class: "ev-map__lock" });
      var lx = at.x - r * 0.7, ly = at.y - r * 0.7, lr = Math.max(8, Math.min(12, r * 0.28));
      lb.appendChild(svg("circle", { cx: lx, cy: ly, r: lr }));
      lb.appendChild(svg("path", { d: "M" + (lx - lr * 0.42) + " " + (ly - lr * 0.05) + "h" + (lr * 0.84) + "v" + (lr * 0.62) + "h" + (-lr * 0.84) + "z" +
        "M" + (lx - lr * 0.26) + " " + (ly - lr * 0.05) + "v" + (-lr * 0.2) + "a" + (lr * 0.26) + " " + (lr * 0.26) + " 0 0 1 " + (lr * 0.52) + " 0v" + (lr * 0.2) }));
      gg.appendChild(lb);
    }
    if (shared) gg.appendChild(svg("circle", { cx: at.x + r * 0.72, cy: at.y - r * 0.72, r: 5.5, class: "ev-map__badge" }));
    var lit = function (on) { (lines || []).forEach(function (l) { l.classList.toggle("ev-map__lit", on); }); };
    gg.addEventListener("mouseenter", function () { tip(p, gg, stage); lit(true); stage.classList.add("is-point"); gg.classList.add("is-near"); });
    gg.addEventListener("focus", function () { tip(p, gg, stage); lit(true); });
    gg.addEventListener("mouseleave", function () { untip(stage); lit(false); stage.classList.remove("is-point"); gg.classList.remove("is-near"); });
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
    t.appendChild(el("span", "", rankText(p) + " (typical post)"));
    if (p.locked) t.appendChild(el("span", "ev-tip__lock", "Unavailable right now. Open to ask us."));
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
      var li = el("li"), b = el("button", "ev-rank__row" + (p.locked ? " is-locked" : "")); b.type = "button";
      // Scoreboard medals for the top three (owner, 2026-10-15).
      var medal = ["gold", "silver", "bronze"][i];
      var nn = el("span", "ev-rank__n" + (medal ? " ev-rank__n--" + medal : ""), String(i + 1));
      if (medal) nn.setAttribute("aria-label", medal.charAt(0).toUpperCase() + medal.slice(1) + ", number " + (i + 1));
      b.appendChild(nn);
      var ph = el("span", "ev-rank__ph" + (typeOf(p) === "hcp" ? " is-hcp" : ""));
      if (p.photo) { var im = el("img"); im.src = p.photo; im.alt = ""; im.loading = "lazy"; ph.appendChild(im); }
      else ph.appendChild(el("span", "ev-cp__ini", initials(p.name || p.handle)));
      b.appendChild(ph);
      var who = el("span", "ev-rank__who");
      who.appendChild(el("b", "", p.name || ("@" + p.handle)));
      var lg = el("span", "ev-rank__logos");
      Object.keys(p.competitors).forEach(function (k) { lg.appendChild(logoEl(k, compLogo(k), "ev-logo--mini")); });
      who.appendChild(lg);
      if (p.estimate) who.appendChild(el("small", "ev-rank__est", "Est. " + estText(p)));
      b.appendChild(who);
      b.appendChild(el("span", "ev-rank__v", num(p.rank_value)));
      b.addEventListener("click", function () { openCreator(p); });
      b.addEventListener("mouseenter", function () { if (mi.svg && mi.svg.__spot) mi.svg.__spot(function (dd) { return dd.__h === p.handle; }); });
      b.addEventListener("mouseleave", function () { if (mi.svg && mi.svg.__unspot) mi.svg.__unspot(); });
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

  // Competitor creators HelloVoice does not have yet: nothing to pick, only a request (owner, 2026-10-15).
  function outsideStrip(list) {
    var sec = el("section", "ev-out");
    sec.setAttribute("aria-labelledby", "ev-out-t");
    var hd = el("div", "ev-out__hd");
    var h = el("h2", "ev-out__t", "Not on our roster yet"); h.id = "ev-out-t";
    hd.appendChild(h);
    hd.appendChild(el("p", "ev-mut", "Creators who posted with your competitors and are not HelloVoice creators. Ask and we will try to sign them for you."));
    sec.appendChild(hd);
    var row = el("div", "ev-out__row");
    list.forEach(function (p) {
      var card = el("article", "ev-out__card");
      var top = el("div", "ev-out__top");
      var ph = el("span", "ev-out__ph" + (p.type === "hcp" ? " is-hcp" : "")); ph.appendChild(el("span", "ev-cp__ini", initials(p.name || p.handle)));
      top.appendChild(ph);
      var who = el("div", "ev-out__who");
      who.appendChild(el("b", "", p.name || ("@" + p.handle)));
      who.appendChild(el("span", "ev-mut", "@" + p.handle + (p.followers ? " · " + num(p.followers) + " followers" : "")));
      top.appendChild(who);
      card.appendChild(top);
      var lg = el("div", "ev-out__logos");
      Object.keys(p.competitors).forEach(function (k) { lg.appendChild(logoEl(k, compLogo(k), "ev-logo--mini")); });
      card.appendChild(lg);
      card.appendChild(el("p", "ev-out__v", num(p.median_views) + " typical views · " + p.posts + (p.posts === 1 ? " post" : " posts")));
      var rq = btn("ev-act ev-act--ask", "send", "Request");
      rq.addEventListener("click", function () { requestCreator(p, "roster", rq); });
      card.appendChild(rq);
      row.appendChild(card);
    });
    sec.appendChild(row);
    return sec;
  }

  function requestCreator(p, kind, b) {
    b.disabled = true;
    fetch((CFG.api || "") + "/api/evidence/request", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: token(), handle: p.handle, kind: kind }) })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (j) {
        if (j && j.ok) {
          p.requested = true;
          b.textContent = ""; b.appendChild(icon("check")); b.appendChild(el("span", "", "Requested"));
          b.classList.add("is-done");
        } else { b.disabled = false; b.lastChild.textContent = "Try again"; }
      }).catch(function () { b.disabled = false; b.lastChild.textContent = "Try again"; });
  }

  /* The creator panel from the map: their competitor posts, with Add to selection (or Request when they
     are unavailable) and Profile analysis. */
  var cpanel = null;
  function closeCreator() { if (cpanel) { cpanel.scrim.remove(); cpanel.aside.remove(); cpanel = null; } }

  function openCreator(p) {
    closeCreator();
    var f = panelFrame({ top: true, name: p.name || ("@" + p.handle), photo: p.photo_large || p.photo, hcp: typeOf(p) === "hcp", locked: !!p.locked,
      meta: "@" + p.handle + " · " + (typeOf(p) === "hcp" ? "Doctor / pharmacist" : "Influencer") + (p.followers ? " · " + num(p.followers) + " followers" : "") });
    f.scrim.addEventListener("click", closeCreator);
    f.x.addEventListener("click", closeCreator);
    if (p.locked) {
      f.acts.appendChild(el("span", "ev-chip ev-chip--off", "Unavailable right now"));
      var rq = btn("ev-act ev-act--ask", "send", p.requested ? "Requested" : "Request");
      if (p.requested) { rq.disabled = true; rq.classList.add("is-done"); }
      rq.addEventListener("click", function () { requestCreator(p, "unavailable", rq); });
      f.acts.appendChild(rq);
    } else if (p.in_selection) {
      f.acts.appendChild(el("span", "ev-chip ev-chip--in", "In this selection"));
    } else if (miData.can_add && p.on_roster) {
      var add = btn("ev-act ev-act--yes", "plus", "Add to selection");
      add.addEventListener("click", function () { addToSelection(p, add); });
      f.acts.appendChild(add);
    }
    if (p.code) f.acts.appendChild(linkBtn("ev-act", "chart", "Profile analysis", analysisHref(p.code)));
    var comps = {};
    Object.keys(p.competitors).forEach(function (k) { comps[k] = p.competitors[k]; });
    if (p.estimate) {
      var es = el("div", "ev-est");
      es.appendChild(el("small", "", "Estimated " + estUnit() + " per post"));
      es.appendChild(el("b", "", p.estimate.lo === p.estimate.hi ? "~" + num(p.estimate.mid) : num(p.estimate.lo) + " \u2013 " + num(p.estimate.hi)));
      es.appendChild(el("span", "", "Typical " + num(p.estimate.mid) + " · from " + p.estimate.n + " competitor " + (p.estimate.n === 1 ? "post" : "posts")));
      f.bd.appendChild(es);
    }
    postsBlock(f.bd, p.posts, comps, compLogo);
    cpanel = { scrim: f.scrim, aside: f.aside };
    f.x.focus();
  }

  /* TikTok and Instagram posts show the platform's own embed over the saved picture (owner, 2026-10-15); the same queue,
     ready check and fallback as the creator page (assets/js/creator.js LIVEPOST), TikTok and Instagram. */
  var LIVEPOST = (function () {
    // One queue per platform, so neither throttles us: TikTok one per 400 ms (6 loading at most), Instagram one per
    // second (3 at most; its embed is heavy). The card nearest the middle of the screen goes first.
    var KIND = {
      tt: { gap: 400, max: 6, wait: 8000, grace: 2000, origin: /^https:\/\/([a-z0-9-]+\.)*tiktok\.com$/,
            src: function (id) { return "https://www.tiktok.com/player/v1/" + encodeURIComponent(id) + "?controls=0&progress_bar=0&play_button=0" +
              "&volume_control=0&fullscreen_button=0&timestamp=0&music_info=0&description=0&rel=0&native_context_menu=0&closed_caption=0&autoplay=0&loop=0"; } },
      ig: { gap: 1000, max: 3, wait: 30000, grace: 0, origin: /^https:\/\/([a-z0-9-]+\.)*instagram\.com$/,
            src: function (id) { return "https://www.instagram.com/p/" + encodeURIComponent(id) + "/embed/"; } }
    };
    var Q = { tt: [], ig: [] }, loading = { tt: [], ig: [] }, timer = { tt: null, ig: null }, all = [], near = null, far = null;
    if (!window.IntersectionObserver) return { watch: function () {} };
    function kindOf(box) { return (box.getAttribute("data-live") || "").split(":")[0]; }
    function idOf(box) { return (box.getAttribute("data-live") || "").split(":").slice(1).join(":"); }
    function state(box, s) { if (s) box.setAttribute("data-live-state", s); return box.getAttribute("data-live-state"); }
    function fit(box) { box.style.setProperty("--lv-s", (box.clientWidth / 340).toFixed(4)); }   // Instagram's frame is laid out 340 wide, then scaled
    function start(box) {
      var k = kindOf(box), K = KIND[k], f = document.createElement("iframe");
      f.className = "lv-frame lv-" + k; f.src = K.src(idOf(box));
      f.title = (k === "tt" ? "TikTok" : "Instagram") + " preview"; f.setAttribute("aria-hidden", "true"); f.tabIndex = -1;
      f.setAttribute("allow", "encrypted-media"); f.setAttribute("scrolling", "no");
      f.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
      if (k === "ig") fit(box);
      box.__lv = { f: f, t: setTimeout(function () { fail(box); }, K.wait) };
      // Shown a moment after the frame loads (TikTok reports a missing video in that time); a ready message shows it sooner.
      // Instagram waits for its own MEASURE message with a real height: an unavailable post loads an empty frame.
      if (K.grace) f.addEventListener("load", function () { setTimeout(function () { ready(box); }, K.grace); });
      state(box, "loading"); loading[k].push(box);
      box.appendChild(f);
    }
    function settle(box) {
      var k = kindOf(box);
      clearTimeout(box.__lv && box.__lv.t);
      loading[k] = loading[k].filter(function (b) { return b !== box; });
      pump(k);
    }
    function ready(box) {
      if (state(box) !== "loading") return;
      state(box, "live"); box.classList.add("is-live", "is-live-" + kindOf(box)); settle(box);
    }
    // Failed, timed out or missing: the frame goes, the card stays with its picture or placeholder.
    function fail(box) {
      if (box.__lv && box.__lv.f) box.__lv.f.remove();
      box.classList.remove("is-live", "is-live-tt", "is-live-ig"); state(box, "off");      // not tried again on this page
      settle(box);
    }
    function unload(box) {
      if (state(box) !== "live") return;
      if (box.__lv && box.__lv.f) box.__lv.f.remove();
      box.classList.remove("is-live", "is-live-tt", "is-live-ig"); state(box, "idle");
    }
    function pump(k) {
      if (timer[k] || !Q[k].length) return;
      timer[k] = setTimeout(function () {
        timer[k] = null;
        Q[k] = Q[k].filter(function (b) { return b.isConnected && b.__near && state(b) === "idle"; });
        if (Q[k].length && loading[k].length < KIND[k].max) {
          var mid = window.innerHeight / 2;
          Q[k].sort(function (a, b) {
            var ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
            return Math.abs(ra.top + ra.height / 2 - mid) - Math.abs(rb.top + rb.height / 2 - mid);
          });
          start(Q[k].shift());
        }
        pump(k);
      }, KIND[k].gap);
    }
    window.addEventListener("message", function (e) {
      var o = e.origin || "", box = all.filter(function (b) { return b.__lv && b.__lv.f.isConnected && b.__lv.f.contentWindow === e.source; })[0];
      if (!box || !KIND[kindOf(box)].origin.test(o)) return;
      var d = e.data;
      if (typeof d === "string") { try { d = JSON.parse(d); } catch (x) { return; } }
      if (!d || !d.type) return;
      if (d.type === "onPlayerReady" || (d.type === "MEASURE" && d.details && d.details.height >= 200)) setTimeout(function () { ready(box); }, 250);
      else if (/error/i.test(d.type)) fail(box);          // TikTok onPlayerError (INVALID_VIDEO for a deleted post), even after it showed
    });
    window.addEventListener("resize", function () { all.forEach(function (b) { if (kindOf(b) === "ig") fit(b); }); }, { passive: true });
    function watch(root) {
      var boxes = [].slice.call((root || document).querySelectorAll("[data-live]"));
      if (!boxes.length) return;
      near = near || new IntersectionObserver(function (es) {
        es.forEach(function (en) {
          var box = en.target, k = kindOf(box); box.__near = en.isIntersecting;
          if (en.isIntersecting && state(box) === "idle" && Q[k].indexOf(box) < 0) { Q[k].push(box); pump(k); }
        });
      }, { rootMargin: "300px 0px" });
      far = far || new IntersectionObserver(function (es) {
        if (all.filter(function (b) { return b.isConnected; }).length <= 12) return;     // a short page keeps its embeds
        es.forEach(function (en) { if (!en.isIntersecting) unload(en.target); });
      }, { rootMargin: "1600px 0px" });
      boxes.forEach(function (b) {
        if (b.__lvWatched || !KIND[kindOf(b)]) return;
        b.__lvWatched = true; state(b, "idle"); all.push(b);
        near.observe(b); far.observe(b);
      });
    }
    return { watch: watch };
  })();
  function ttId(u) { var m = /tiktok\.com\/@[^\/]+\/video\/(\d+)/.exec(u || ""); return m ? m[1] : null; }
  // An Instagram shortcode, never a numeric id (instagram.com/p/<digits> are posts that no longer open).
  function igCode(u) { var m = /instagram\.com\/(?:[^\/]+\/)?(?:p|reel|reels|tv)\/([A-Za-z0-9_-]+)/.exec(u || ""); return m && !/^\d+$/.test(m[1]) ? m[1] : null; }
  function liveAttr(u) { var t = ttId(u), g = !t && igCode(u); return t ? "tt:" + t : g ? "ig:" + g : ""; }

  // One post, the campaign-dashboard card: picture (whole frame, blurred fill), brand logo, play; figures under it.
  function dashPost(q, host, logoOf) {
    var card = el("article", "ev-dpost");
    var media = el("button", "ev-dpost__img"); media.type = "button"; media.setAttribute("aria-label", "Play the post from " + (q.date || ""));
    if (liveAttr(q.url)) media.setAttribute("data-live", liveAttr(q.url));
    var src = (CFG.api || "") + "/api/evidence/thumb?s=" + encodeURIComponent(token()) + "&p=" + encodeURIComponent(q.id);
    var fillI = el("img", "ev-fill"); fillI.src = src; fillI.alt = ""; fillI.loading = "lazy"; fillI.setAttribute("aria-hidden", "true");
    var fitI = el("img", "ev-fit"); fitI.src = src; fitI.alt = ""; fitI.loading = "lazy";
    fitI.addEventListener("error", function () { fillI.remove(); fitI.remove(); media.classList.add("ev-dpost__img--none"); });
    media.appendChild(fillI); media.appendChild(fitI);
    var badge = el("span", "ev-dpost__brand"); badge.appendChild(logoEl(q.competitor, (logoOf || compLogo)(q.competitor), "ev-logo--badge")); media.appendChild(badge);
    if (q.paid_boost) media.appendChild(el("span", "ev-post__flag", "Paid-boosted"));
    var pl = el("span", "ev-post__play"); pl.appendChild(icon("play")); media.appendChild(pl);
    media.addEventListener("click", function () { playIn(host, q); });
    card.appendChild(media);
    var b2 = el("div", "ev-dpost__body");
    b2.appendChild(el("b", "", q.collab || "Collab post"));
    b2.appendChild(el("span", "", (q.platform === "tiktok" ? "TikTok" : "Instagram") + " · " + (q.date || "")));
    card.appendChild(b2);
    var st = el("div", "ev-dpost__stats");
    // TikTok study entries carry the creator's MEDIAN figures across competitor videos, not this video's.
    (q.summary
      ? [["Median views", num(q.views)], ["Eng. rate (median)", q.er == null ? "n/a" : pct(q.er)], ["Save rate", q.save_rate == null ? "n/a" : pct(q.save_rate)], ["Platform", "TikTok"]]
      : [["Views", num(q.views)], ["Likes", q.likes == null ? "Hidden" : num(q.likes)], ["Comments", num(q.comments)], ["Eng. rate", q.er == null ? "n/a" : pct(q.er)]])
      .forEach(function (s2) { var dv = el("div"); dv.appendChild(el("small", "", s2[0])); dv.appendChild(el("b", "", s2[1])); st.appendChild(dv); });
    card.appendChild(st);
    return card;
  }

  function addToSelection(p, b) {
    b.disabled = true;
    fetch((CFG.api || "") + "/api/evidence/add", { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: token(), handle: p.handle }) })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (j) {
        var S = sel();
        if (j && j.ok) {
          p.in_selection = true; p.code = j.code;
          b.replaceWith(el("span", "ev-chip ev-chip--in", "Added to this selection"));
          if (S && S.refresh) S.refresh();
        } else { b.disabled = false; if (S && S.toast) S.toast("Could not add this creator."); }
      }).catch(function () { b.disabled = false; });
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
