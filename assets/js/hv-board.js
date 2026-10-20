/* The kanban board (item 194, owner 2026-10-20), shared by the account page (Selections and Campaigns tabs)
 * and campaign tracking (/campaign/). Six columns, the campaign board's stages: Draft, Shortlisting,
 * Client review, Approved, Live, Completed.
 *
 *   HVBoard.mount(host, {
 *     stages:  [{key, label, hint}],            from /api/board
 *     items:   [card, ...],                     HVBoard.fromCampaign(c) / HVBoard.fromSelection(s)
 *     locked:  ["live", "completed"],           columns this viewer can't drop into (drawn with a lock)
 *     noun:    "campaign" | "selection",
 *     onMove:  function (item, to) -> Promise<{ok, message, setup?}>,
 *     onPin:   function (item, on) -> Promise<{ok}>        (optional; campaigns)
 *     extra:   function (item) -> Node | null              (optional; the admin's Go live / Unlive)
 *     say:     function (html|text, bad)                   (optional; else the board's own status line)
 *   })
 *
 * Moving: every card that may move has a "Move to" pill menu (keyboard, phones) and, on a desktop with a
 * mouse, drags to a column it may go to. Columns it may not go to dim while it is held. The move shows at
 * once and is put back if the server says no. The server checks every move (admin/board.py); the menu and
 * the drag only offer what it allows.
 *
 * Phones (under 900px): one column per screen, swiped, with stage pills above that follow the swipe.
 * Empty columns fold to a slim rail on a desktop so six fit beside the profile's side nav.
 * Server text always goes on the page as text, never as HTML.
 */
(function () {
  "use strict";

  var ROOT = "../";
  var HV_LOGO = ROOT + "assets/brand/logo.png";
  var API_BASE = (((window.CATALOGUE_CONFIG || {}).api != null ? window.CATALOGUE_CONFIG.api : "/admin") + "").replace(/\/$/, "");
  var ICON = {
    pin: '<path d="M9 4h6l-1 5 3 3v2H7v-2l3-3-1-5z"/><path d="M12 14v6"/>',
    chev: '<path d="M6 9l6 6 6-6"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    fold: '<path d="M15 6l-6 6 6 6"/>',
    unfold: '<path d="M9 6l6 6-6 6"/>',
    chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    list: '<path d="M4 6h16M4 12h16M4 18h10"/>',
    grip: '<circle cx="9" cy="7" r="1.2"/><circle cx="15" cy="7" r="1.2"/><circle cx="9" cy="12" r="1.2"/><circle cx="15" cy="12" r="1.2"/><circle cx="9" cy="17" r="1.2"/><circle cx="15" cy="17" r="1.2"/>'
  };

  function svg(name, cls) {
    var s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    s.setAttribute("viewBox", "0 0 24 24");
    s.setAttribute("aria-hidden", "true");
    s.setAttribute("focusable", "false");
    if (cls) s.setAttribute("class", cls);
    s.innerHTML = ICON[name];
    return s;
  }
  function h(tag, props) {
    var el = document.createElement(tag);
    props = props || {};
    Object.keys(props).forEach(function (k) {
      var v = props[k];
      if (v == null || v === false) return;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    });
    for (var i = 2; i < arguments.length; i++) add(el, arguments[i]);
    return el;
  }
  function add(el, c) {
    if (c == null || c === false) return;
    if (Array.isArray(c)) { c.forEach(function (x) { add(el, x); }); return; }
    el.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
  }

  /* ------------------------------------------------------------ formatting */
  function big(n) {
    n = Number(n) || 0;
    if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1).replace(/\.0$/, "") + "K";
    return String(n);
  }
  function dm(ts) { return ts ? new Date(ts * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : ""; }
  function ago(ts) {
    if (!ts) return "";
    var s = Date.now() / 1000 - ts;
    if (s < 3600) return "just now";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    if (s < 86400 * 30) return Math.floor(s / 86400) + "d ago";
    return dm(ts);
  }
  function initials(s) {
    return String(s || "?").trim().split(/\s+/).slice(0, 2).map(function (w) { return w.charAt(0); }).join("").toUpperCase() || "?";
  }
  // Where a campaign is in its run: "Starts 3 Nov", "Day 4 of 21", "3 Oct – 24 Oct".
  function when(a, b) {
    if (!a || !b) return a ? "From " + dm(a) : "";
    var now = Date.now() / 1000, span = Math.max(1, Math.round((b - a) / 86400));
    if (now < a) return "Starts " + dm(a);
    if (now <= b) return "Day " + Math.min(span, Math.max(1, Math.ceil((now - a) / 86400))) + " of " + span;
    return dm(a) + " – " + dm(b);
  }
  var SIG = { good: "Strong", moderate: "Fair", low: "Low" };
  var TRACK = { good: "On track", moderate: "Slightly behind", low: "Behind target" };
  function ours(client) { return /^\s*hello\s*voice\b/i.test(client || ""); }

  /* ------------------------------------------------------- normalised cards */
  // A campaign from /api/board.
  function fromCampaign(c) {
    var n = c.numbers, p = c.posts, k = c.counts || {};
    var figs = n ? [["Views", big(n.views)], ["Engaged", big(n.engagement)],
                    ["Eng. rate", n.er != null ? Number(n.er).toFixed(2) : "–", n.er != null ? "%" : ""]]
                 : [["Creators", String(k.creators || 0)], ["Approved", String(k.approved || 0)], ["To review", String(k.review || 0)]];
    return {
      key: c.token, name: c.name, stage: c.stage, moves: c.moves || [], client: c.client || "", logos: c.logos || [],
      href: c.report ? ROOT + "campaign/dashboard/#t=" + encodeURIComponent(c.token)
        : (c.selections && c.selections.length ? ROOT + "selection/#s=" + encodeURIComponent(c.selections[0].token) : ""),
      open: c.report ? "Open dashboard" : (c.selections && c.selections.length ? "Open selection" : ""),
      when: when(c.starts_at, c.ends_at), kam: c.kam ? c.kam.name || c.kam.email : "",
      pinned: !!c.my_pin, demo: !!c.demo, live: c.status === "live",
      figures: figs, signal: n && n.er_grade ? { grade: n.er_grade, label: SIG[n.er_grade] } : null,
      // Item 208: the dashboard's own verdict as an on-track colour (green / amber / red) on live cards.
      track: c.status === "live" && n && n.verdict && n.verdict.grade ? { grade: n.verdict.grade, label: TRACK[n.verdict.grade] || n.verdict.label } : null,
      key1: n ? [big(n.views), "views"] : [String(k.creators || 0), (k.creators === 1 ? "creator" : "creators")],
      // Item 203: every campaign card opens its selection(s) and its dashboard.
      sels: (c.selections || []).map(function (s) { return { label: s.name, href: ROOT + "selection/#s=" + encodeURIComponent(s.token) }; }),
      dash: c.report ? ROOT + "campaign/dashboard/#t=" + encodeURIComponent(c.token) : "",
      progress: p && p.planned ? { done: p.live || 0, of: p.planned } : null,
      links: (c.selections || []).map(function (s) {
        return { label: s.name, sub: s.creators + (s.creators === 1 ? " creator" : " creators"), href: ROOT + "selection/#s=" + encodeURIComponent(s.token) };
      }),
      linksLabel: "Selections in this campaign", empty: "No selection yet.",
      updated: c.updated_at, raw: c
    };
  }
  // A selection from /api/account.
  function fromSelection(s, badge) {
    var k = s.counts || {};
    return {
      key: s.token, name: s.name, stage: s.stage, moves: s.moves || [], client: s.client || "",
      logos: (s.logos || []).map(function (u) { return u.charAt(0) === "@" ? API_BASE + u.slice(1) : u; }),
      href: ROOT + "selection/#s=" + encodeURIComponent(s.token), open: s.mine && k.review ? "Review" : "Open selection",
      key1: [String(k.creators || 0), k.creators === 1 ? "creator" : "creators"],
      sels: [{ label: s.name, button: s.mine && k.review ? "Review" : "Open", href: ROOT + "selection/#s=" + encodeURIComponent(s.token) }],
      dash: (s.campaigns || []).filter(function (c) { return c.live; }).map(function (c) { return ROOT + "campaign/dashboard/#t=" + encodeURIComponent(c.token); })[0] || "",
      when: s.owner ? s.owner + "’s" : "", kam: s.kam || "", badge: badge || null,
      figures: [["Creators", String(k.creators || 0)], ["Approved", String(k.approved || 0)], ["To review", String(k.review || 0)]],
      links: (s.campaigns || []).map(function (c) {
        return { label: c.name, sub: c.live ? "Live" : "Campaign", live: c.live, href: c.live ? ROOT + "campaign/dashboard/#t=" + encodeURIComponent(c.token) : ROOT + "campaign/" };
      }),
      linksLabel: "Campaigns using this selection", empty: "",
      updated: s.updated_at, raw: s
    };
  }

  /* ----------------------------------------------------------------- card */
  function brand(it) {
    var lock = h("span", { class: "hvb-brand" });
    lock.appendChild(h("img", { class: "hvb-brand__hv", src: HV_LOGO, alt: "HelloVoice", width: "84", height: "18", decoding: "async" }));
    if (ours(it.client)) return lock;
    lock.appendChild(h("span", { class: "hvb-brand__x", "aria-hidden": "true" }, "×"));
    if (it.logos.length) {
      var img = h("img", { class: "hvb-brand__cl", src: it.logos[0], alt: it.client || it.name, loading: "lazy", decoding: "async" });
      img.addEventListener("error", function () {
        img.replaceWith(h("span", { class: "hvb-brand__mono", title: it.client || it.name }, initials(it.client || it.name)));
      });
      lock.appendChild(img);
    } else {
      lock.appendChild(h("span", { class: "hvb-brand__mono", title: it.client || it.name, "aria-label": it.client || "Client" }, initials(it.client || it.name)));
    }
    return lock;
  }
  function figures(it) {
    var dl = h("dl", { class: "hvb-figs" });
    it.figures.forEach(function (f) {
      dl.appendChild(h("div", null, h("dt", null, f[0]), h("dd", null, f[1], f[2] ? h("small", null, f[2]) : null)));
    });
    return dl;
  }
  function progress(p) {
    var pct = Math.max(0, Math.min(100, Math.round(p.done / p.of * 100)));
    var bar = h("div", { class: "hvb-prog", role: "img", "aria-label": p.done + " of " + p.of + " posts live" },
      h("span", { class: "hvb-prog__t" }, h("i", { style: "width:" + pct + "%" })),
      h("span", { class: "hvb-prog__n" }, h("b", null, String(p.done)), "/" + p.of + " posts live"));
    return bar;
  }
  function moveMenu(it, stages, onPick) {
    var sel = h("select", { "aria-label": "Move " + it.name + " to another stage" });
    sel.appendChild(h("option", { value: "", selected: true }, "Move to…"));
    stages.forEach(function (s) { if (it.moves.indexOf(s.key) >= 0) sel.appendChild(h("option", { value: s.key }, s.label)); });
    sel.addEventListener("change", function () { if (sel.value) onPick(sel.value, sel); });
    return h("label", { class: "hvb-move" }, sel, svg("chev"));
  }

  function trackPill(t) { return h("span", { class: "hvb-track hvb-track--" + t.grade, title: "Against the campaign's goal, as the dashboard reads it" }, t.label); }
  // Item 203: "Open selection" (a short list when the campaign holds several) and "Open dashboard".
  function goButtons(it) {
    var out = [];
    if (it.sels && it.sels.length === 1) {
      out.push(h("a", { class: "hvb-go", href: it.sels[0].href }, svg("list"), it.sels[0].button || "Selection",
        h("span", { class: "hvb-sr" }, ": " + it.name)));
    } else if (it.sels && it.sels.length > 1) {
      var d = h("details", { class: "hvb-pick" });
      d.appendChild(h("summary", { class: "hvb-go" }, svg("list"), "Selections", h("b", null, String(it.sels.length))));
      var ul = h("ul", { class: "hvb-pick__list" });
      it.sels.forEach(function (x) { ul.appendChild(h("li", null, h("a", { href: x.href }, x.label))); });
      d.appendChild(ul);
      document.addEventListener("click", function (e) { if (d.open && !d.contains(e.target)) d.open = false; });
      out.push(d);
    }
    if (it.dash) out.push(h("a", { class: "hvb-go hvb-go--dash", href: it.dash }, svg("chart"), "Dashboard", h("span", { class: "hvb-sr" }, ": " + it.name)));
    return out;
  }

  function card(it, B) {
    var can = it.moves.length > 0;
    var open = B.isOpen(it.key);
    var bodyId = "hvb-b-" + B.noun + "-" + String(it.key).replace(/[^A-Za-z0-9_-]/g, "");
    var el = h("article", { class: "hvb-card" + (it.pinned ? " is-pinned" : "") + (it.demo ? " is-demo" : "") + (can ? " can-move" : "") + (open ? "" : " is-collapsed")
                              + (it.track ? " is-track-" + it.track.grade : ""),
                            "data-key": it.key, "data-stage": it.stage, "aria-label": it.name });
    var tog = h("button", { type: "button", class: "hvb-tog", "aria-expanded": open ? "true" : "false", "aria-controls": bodyId,
                            "aria-label": (open ? "Collapse " : "Expand ") + it.name, title: open ? "Show less" : "Show details" }, svg("chev"));
    tog.addEventListener("click", function () { B.toggle(it.key, el, tog); });
    var top = h("div", { class: "hvb-card__top" }, brand(it));
    if (B.opts.onPin) {
      var pin = h("button", { type: "button", class: "hvb-pin" + (it.pinned ? " is-on" : ""), "aria-pressed": it.pinned ? "true" : "false",
                              "aria-label": (it.pinned ? "Unpin " : "Pin ") + it.name, title: it.pinned ? "Unpin" : "Pin to the top" }, svg("pin"));
      pin.addEventListener("click", function () {
        pin.disabled = true;
        B.opts.onPin(it, !it.pinned).then(function (j) { if (!(j && j.ok)) { pin.disabled = false; B.say("Couldn’t change that pin. Please try again.", true); } });
      });
      top.appendChild(pin);
    }
    if (can && B.drag) top.insertBefore(h("span", { class: "hvb-grip", title: "Drag to another stage" }, svg("grip")), top.firstChild.nextSibling);
    top.appendChild(tog);
    el.appendChild(top);
    el.appendChild(h("h3", { class: "hvb-card__name" }, it.href ? h("a", { href: it.href }, it.name) : it.name));
    // The one-line summary a collapsed card keeps: on-track colour or Live mark, the key number, the client.
    el.appendChild(h("p", { class: "hvb-card__sum" },
      it.track ? trackPill(it.track) : (it.live ? h("span", { class: "hvb-live" }, "Live") : null),
      it.key1 ? h("span", { class: "hvb-card__k" }, h("b", null, it.key1[0]), " " + it.key1[1]) : null,
      it.when ? h("span", null, it.when) : null));
    var body = h("div", { class: "hvb-card__body", id: bodyId });
    el.appendChild(body);
    var put = function (x) { body.appendChild(x); };
    var meta = [it.client && !ours(it.client) ? it.client : "", it.when].filter(Boolean).join(" · ");
    if (meta || it.badge || it.live || it.demo || it.track) {
      put(h("div", { class: "hvb-card__meta" },
        it.live ? h("span", { class: "hvb-live" }, "Live") : null,
        it.track ? trackPill(it.track) : null,
        it.demo ? h("span", { class: "hvb-tag hvb-tag--demo", title: "The team’s demo campaign" }, "Demo") : null,
        it.badge, meta ? h("span", null, meta) : null));
    }
    put(figures(it));
    if (it.signal || it.progress) {
      put(h("div", { class: "hvb-card__perf" }, it.progress ? progress(it.progress) : null,
        it.signal ? h("span", { class: "hvb-sig hvb-sig--" + it.signal.grade, title: "Engagement rate against the campaign goal" }, it.signal.label) : null));
    }
    if (it.links.length) {
      var shown = it.links.slice(0, 3);
      var ul = h("ul", { class: "hvb-links", "aria-label": it.linksLabel });
      shown.forEach(function (l) {
        ul.appendChild(h("li", null, h("a", { href: l.href }, h("span", { class: "hvb-links__n" }, l.live ? h("i", { class: "hvb-dot", "aria-hidden": "true" }) : null, l.label),
          h("span", { class: "hvb-links__c" }, l.sub))));
      });
      if (it.links.length > shown.length) ul.appendChild(h("li", { class: "hvb-links__more" }, "+" + (it.links.length - shown.length) + " more"));
      put(ul);
    } else if (it.empty) {
      put(h("p", { class: "hvb-none" }, it.empty));
    }
    var foot = h("div", { class: "hvb-card__foot" },
      it.kam ? h("span", { class: "hvb-kam", title: "Account manager" }, h("span", { class: "hvb-kam__face", "aria-hidden": "true" }, initials(it.kam)), it.kam)
             : h("span", { class: "hvb-kam hvb-kam--none" }, "HelloVoice team"),
      it.updated ? h("span", { class: "hvb-ago" }, "Updated " + ago(it.updated)) : null);
    put(foot);
    var acts = h("div", { class: "hvb-card__acts" });
    if (can) acts.appendChild(moveMenu(it, B.opts.stages, function (to, sel) { B.move(it, to, sel); }));
    var x = B.opts.extra ? B.opts.extra(it) : null;
    if (x) acts.appendChild(x);
    if (acts.childNodes.length) put(acts);
    var go = goButtons(it);
    if (go.length) el.appendChild(h("div", { class: "hvb-card__go" }, go));
    if (can && B.drag) el.setAttribute("draggable", "true");
    return el;
  }

  /* ---------------------------------------------------------------- board */
  function mount(host, opts) {
    var B = { opts: opts, drag: matchMedia("(min-width: 900px) and (pointer: fine)").matches, lane: 0 };
    var locked = opts.locked || [];
    var noun = opts.noun || "item";
    B.noun = noun;
    // Items 197/198: cards open collapsed to one line; the arrow opens one. What is open, and which columns are
    // folded (item 201), is remembered in this browser only.
    function remember(k, fallback) { try { return JSON.parse(localStorage.getItem(k) || "null") || fallback; } catch (e) { return fallback; } }
    function keep(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } }
    var OPEN = remember("hvb-open-" + noun, {}), FOLD = remember("hvb-fold-" + noun, {});
    B.isOpen = function (key) { return !!OPEN[key]; };
    B.toggle = function (key, el, tog) {
      var on = !OPEN[key];
      if (on) OPEN[key] = 1; else delete OPEN[key];
      keep("hvb-open-" + noun, OPEN);
      el.classList.toggle("is-collapsed", !on);
      tog.setAttribute("aria-expanded", on ? "true" : "false");
      tog.setAttribute("aria-label", (on ? "Collapse " : "Expand ") + el.getAttribute("aria-label"));
      tog.title = on ? "Show less" : "Show details";
      allBtn.textContent = items.every(function (x) { return OPEN[x.key]; }) ? "Collapse all" : "Expand all";
    };
    var status = h("p", { class: "hvb-say", role: "status", "aria-live": "polite" });
    B.say = function (text, bad) {
      if (opts.say) { opts.say(text, bad); return; }
      status.textContent = text || ""; status.className = "hvb-say is-on" + (bad ? " is-bad" : "");
      clearTimeout(B.sayT); B.sayT = setTimeout(function () { status.className = "hvb-say"; }, 6000);
    };
    var items = opts.items.slice();
    var lanes = {}, tabs = {};

    var root = h("div", { class: "hvb" });
    var allBtn = h("button", { type: "button", class: "hvb-tool" }, items.length && items.every(function (x) { return OPEN[x.key]; }) ? "Collapse all" : "Expand all");
    allBtn.addEventListener("click", function () {
      var expand = allBtn.textContent === "Expand all";
      items.forEach(function (x) { if (expand) OPEN[x.key] = 1; else delete OPEN[x.key]; });
      keep("hvb-open-" + noun, OPEN);
      allBtn.textContent = expand ? "Collapse all" : "Expand all";
      draw();
    });
    // Item 200: Group by client — one band per client across the six stages (a toggle, remembered).
    B.group = !!remember("hvb-group-" + noun, false);
    var grpBtn = h("button", { type: "button", class: "hvb-tool hvb-tool--switch", "aria-pressed": B.group ? "true" : "false" }, h("i", { "aria-hidden": "true" }), "Group by client");
    grpBtn.addEventListener("click", function () {
      B.group = !B.group; keep("hvb-group-" + noun, B.group);
      grpBtn.setAttribute("aria-pressed", B.group ? "true" : "false");
      if (opts.view === "table") table(); else draw();
    });
    var tools = h("div", { class: "hvb-tools" });
    if (opts.tools) add(tools, opts.tools);
    tools.appendChild(h("span", { class: "hvb-tools__gap" }));
    tools.appendChild(grpBtn);
    if (opts.view !== "table") tools.appendChild(allBtn);
    var tabBar = h("div", { class: "hvb-tabs", role: "tablist", "aria-label": "Stages" });
    var grid = h("div", { class: "hvb-grid" });
    opts.stages.forEach(function (s, i) {
      var isLock = locked.indexOf(s.key) >= 0;
      var count = h("b", { class: "hvb-lane__n" });
      var cards = h("div", { class: "hvb-lane__cards" });
      var fold = h("button", { type: "button", class: "hvb-fold", "aria-label": "Fold the " + s.label + " column", title: "Fold column" }, svg("fold"));
      var head = h("header", { class: "hvb-lane__head" },
        h("h2", { id: "hvb-h-" + noun + "-" + s.key }, s.label), count, fold,
        h("p", { class: "hvb-lane__hint" }, s.hint, isLock ? h("span", { class: "hvb-lane__lock" }, svg("lock"), "Set by HelloVoice") : null));
      var lane = h("section", { class: "hvb-lane hvb-lane--" + s.key + (isLock ? " is-locked" : ""), "data-stage": s.key, "data-drop": s.key, "data-i": i,
                                "aria-labelledby": "hvb-h-" + noun + "-" + s.key }, head, cards);
      lanes[s.key] = { el: lane, cards: cards, count: count };
      // Item 201: a column folds to a rail with its count; the rail (or its arrow) opens it again.
      function setFold(on) {
        if (on) FOLD[s.key] = 1; else delete FOLD[s.key];
        keep("hvb-fold-" + noun, FOLD);
        draw();
      }
      fold.addEventListener("click", function (e) { e.stopPropagation(); setFold(!FOLD[s.key]); });
      lane.addEventListener("click", function (e) {
        if (lane.classList.contains("is-folded") && !e.target.closest("a, button, select")) setFold(false);
      });
      grid.appendChild(lane);
      var tab = h("button", { type: "button", role: "tab", class: "hvb-tab" + (s.key === "live" ? " hvb-tab--live" : ""), "data-i": i, "aria-selected": i === 0 ? "true" : "false" },
        s.label, h("b", null, "0"));
      tab.addEventListener("click", function () { B.jump(i); });
      tabs[s.key] = tab;
      tabBar.appendChild(tab);
    });
    var bands = h("div", { class: "hvb-bands" });
    var tbl = h("div", { class: "hvb-table" });
    root.appendChild(status);
    root.appendChild(tools);
    root.appendChild(tabBar);
    // One scroller holds the stage heads and the client bands, so they slide sideways together.
    root.appendChild(h("div", { class: "hvb-scroll" }, grid, bands));
    root.appendChild(tbl);

    function draw() {
      Object.keys(lanes).forEach(function (k) { lanes[k].cards.textContent = ""; });
      var by = {};
      items.forEach(function (it) { (by[it.stage] = by[it.stage] || []).push(it); });
      var cols = [];
      opts.stages.forEach(function (s) {
        var L = lanes[s.key], list = by[s.key] || [];
        list.forEach(function (it) { L.cards.appendChild(card(it, B)); });
        if (!list.length) L.cards.appendChild(h("p", { class: "hvb-empty" }, "No " + noun + "s here"));
        L.count.textContent = String(list.length);
        tabs[s.key].querySelector("b").textContent = String(list.length);
        var folded = !!FOLD[s.key];
        L.el.classList.toggle("is-empty", !list.length);
        L.el.classList.toggle("is-folded", folded && !!list.length);
        var fb = L.el.querySelector(".hvb-fold");
        fb.innerHTML = ""; fb.appendChild(svg(folded ? "unfold" : "fold"));
        fb.setAttribute("aria-label", (folded ? "Open the " : "Fold the ") + s.label + " column");
        fb.setAttribute("aria-expanded", folded ? "false" : "true");
        fb.title = folded ? "Open column" : "Fold column";
        cols.push(list.length && !folded ? "minmax(248px, 1fr)" : "minmax(76px, .32fr)");
      });
      grid.style.setProperty("--hvb-cols", cols.join(" "));
      root.classList.toggle("is-grouped", B.group);
      bands.textContent = "";
      if (B.group) drawBands(by, cols);
      if (B.drag) wireDrag();
      if (B.edges) requestAnimationFrame(B.edges);
    }

    // Swimlanes: the stage heads stay on top (the lanes, with their cards hidden), then a band per client.
    var BANDS = remember("hvb-band-" + noun, {});
    function clients() {
      var order = [], by = {};
      items.forEach(function (it) {
        var c = it.client || "No client";
        if (!by[c]) { by[c] = []; order.push(c); }
        by[c].push(it);
      });
      order.sort(function (a, b) { return by[b].length - by[a].length || a.localeCompare(b); });
      return order.map(function (c) { return { name: c, items: by[c] }; });
    }
    function drawBands(byStage, cols) {
      bands.style.setProperty("--hvb-cols", cols.join(" "));
      clients().forEach(function (c) {
        var shut = !!BANDS[c.name];
        var first = c.items[0];
        var head = h("button", { type: "button", class: "hvb-band__head", "aria-expanded": shut ? "false" : "true" },
          svg("chev"), brand({ client: c.name, name: c.name, logos: first.logos || [] }),
          h("b", { class: "hvb-band__name" }, c.name),
          h("span", { class: "hvb-band__n" }, c.items.length + " " + noun + (c.items.length === 1 ? "" : "s")),
          h("span", { class: "hvb-band__dots", "aria-hidden": "true" }, opts.stages.map(function (s) {
            var n = c.items.filter(function (x) { return x.stage === s.key; }).length;
            return h("i", { class: "hvb-band__dot hvb-lane--" + s.key + (n ? " is-on" : ""), title: s.label + ": " + n }, n ? String(n) : "");
          })));
        var row = h("div", { class: "hvb-band__row" });
        opts.stages.forEach(function (s) {
          var mine = c.items.filter(function (x) { return x.stage === s.key; });
          var cell = h("div", { class: "hvb-cell hvb-lane--" + s.key + (mine.length ? "" : " is-empty") + (FOLD[s.key] && (byStage[s.key] || []).length ? " is-folded" : ""),
                                "data-drop": s.key, "data-stage": s.key },
            h("span", { class: "hvb-cell__k" }, s.label));
          mine.forEach(function (it) { cell.appendChild(card(it, B)); });
          if (FOLD[s.key] && mine.length) cell.appendChild(h("span", { class: "hvb-cell__n" }, String(mine.length)));
          row.appendChild(cell);
        });
        var band = h("section", { class: "hvb-band" + (shut ? " is-shut" : ""), "aria-label": c.name }, head, row);
        head.addEventListener("click", function () {
          if (BANDS[c.name]) delete BANDS[c.name]; else BANDS[c.name] = 1;
          keep("hvb-band-" + noun, BANDS);
          band.classList.toggle("is-shut", !!BANDS[c.name]);
          head.setAttribute("aria-expanded", BANDS[c.name] ? "false" : "true");
        });
        bands.appendChild(band);
      });
    }

    /* ------------------------------------------------- the CRM table (item 199) */
    var SORT = remember("hvb-sort-" + noun, { k: "stage", d: 1 });
    var STAGE_I = {};
    opts.stages.forEach(function (s, i) { STAGE_I[s.key] = i; });
    function cols() {
      var camp = noun === "campaign";
      var c = [
        { k: "client", t: "Client", v: function (it) { return (it.client || "").toLowerCase(); }, cell: function (it) {
            return h("span", { class: "hvb-t__client" }, brand(it), h("span", null, it.client || "–")); } },
        { k: "name", t: camp ? "Campaign" : "Selection", v: function (it) { return it.name.toLowerCase(); }, cell: function (it) {
            return h("span", { class: "hvb-t__name" }, it.href ? h("a", { href: it.href }, it.name) : it.name, it.demo ? h("span", { class: "hvb-tag hvb-tag--demo" }, "Demo") : null); } },
        { k: "stage", t: "Stage", v: function (it) { return STAGE_I[it.stage]; }, cell: function (it) {
            var lab = (opts.stages.filter(function (s) { return s.key === it.stage; })[0] || {}).label || it.stage;
            var wrap = h("span", { class: "hvb-t__stage hvb-lane--" + it.stage }, h("i", { "aria-hidden": "true" }), lab);
            if (!it.moves.length) return wrap;
            return h("span", { class: "hvb-t__stagecell" }, wrap, moveMenu(it, opts.stages, function (to) { B.move(it, to); })); } },
        { k: "kam", t: "KAM", v: function (it) { return (it.kam || "").toLowerCase(); }, cell: function (it) { return it.kam || "HelloVoice team"; } },
        { k: "when", t: camp ? "Dates" : "Updated", v: function (it) { return camp ? (it.raw.starts_at || 0) : (it.updated || 0); }, cell: function (it) {
            var range = it.raw.starts_at ? dm(it.raw.starts_at) + " – " + dm(it.raw.ends_at) : "–";
            return camp ? h("span", null, range, it.when && it.when !== range ? h("small", null, it.when) : null) : ago(it.updated); } },
        { k: "creators", t: "Creators", n: 1, v: function (it) { return num(it, "creators"); }, cell: function (it) { return String(num(it, "creators")); } },
        { k: "approved", t: "Approved", n: 1, v: function (it) { return num(it, "approved"); }, cell: function (it) { return String(num(it, "approved")); } },
        { k: "review", t: "To review", n: 1, v: function (it) { return num(it, "review"); }, cell: function (it) { return String(num(it, "review")); } }];
      if (camp) c = c.concat([
        { k: "views", t: "Views", n: 1, v: function (it) { return (it.raw.numbers || {}).views || 0; }, cell: function (it) { return it.raw.numbers ? big(it.raw.numbers.views) : "–"; } },
        { k: "eng", t: "Engaged", n: 1, v: function (it) { return (it.raw.numbers || {}).engagement || 0; }, cell: function (it) { return it.raw.numbers ? big(it.raw.numbers.engagement) : "–"; } },
        { k: "er", t: "Eng. rate", n: 1, v: function (it) { var n = it.raw.numbers; return n && n.er != null ? n.er : -1; }, cell: function (it) {
            var n = it.raw.numbers; return n && n.er != null ? Number(n.er).toFixed(2) + "%" : "–"; } },
        { k: "posts", t: "Posts live", n: 1, v: function (it) { return it.progress ? it.progress.done / it.progress.of : -1; }, cell: function (it) {
            return it.progress ? it.progress.done + "/" + it.progress.of : "–"; } },
        { k: "track", t: "On track", v: function (it) { return it.track ? ({ good: 0, moderate: 1, low: 2 })[it.track.grade] : 9; }, cell: function (it) {
            return it.track ? trackPill(it.track) : "–"; } }]);
      else c.push({ k: "camps", t: "Campaigns", v: function (it) { return it.links.length; }, cell: function (it) {
            return it.links.length ? it.links.map(function (l) { return l.label; }).join(", ") : "–"; } });
      c.push({ k: "go", t: "", cell: function (it) { return h("span", { class: "hvb-card__go" }, goButtons(it)); } });
      return c;
    }
    function num(it, k) { var c = (it.raw && it.raw.counts) || {}; return c[k] || 0; }
    function table() {
      grid.hidden = tabBar.hidden = true;
      bands.textContent = "";
      tbl.textContent = "";
      var C = cols();
      var col = C.filter(function (c) { return c.k === SORT.k; })[0] || C[2];
      var rows = items.slice().sort(function (a, b) {
        var x = col.v(a), y = col.v(b);
        return (x < y ? -1 : x > y ? 1 : 0) * SORT.d || STAGE_I[a.stage] - STAGE_I[b.stage] || a.name.localeCompare(b.name);
      });
      var t = h("table", { class: "hvb-t" });
      var tr = h("tr");
      C.forEach(function (c) {
        if (!c.v) { tr.appendChild(h("th", { scope: "col" }, h("span", { class: "hvb-sr" }, "Open"))); return; }
        var on = c.k === SORT.k;
        var b = h("button", { type: "button", class: "hvb-t__sort" }, c.t, on ? svg("chev", SORT.d > 0 ? "is-up" : "is-down") : null);
        b.addEventListener("click", function () {
          SORT = { k: c.k, d: on ? -SORT.d : (c.n ? -1 : 1) }; keep("hvb-sort-" + noun, SORT); table();
        });
        tr.appendChild(h("th", { scope: "col", class: c.n ? "is-num" : null, "aria-sort": on ? (SORT.d > 0 ? "ascending" : "descending") : null }, b));
      });
      t.appendChild(h("thead", null, tr));
      function body(list, label) {
        var tb = h("tbody");
        if (label) {
          tb.appendChild(h("tr", { class: "hvb-t__group" }, h("th", { scope: "rowgroup", colspan: String(C.length) },
            h("span", { class: "hvb-t__client" }, brand({ client: label, name: label, logos: list[0].logos || [] }), h("b", null, label)),
            h("small", null, list.length + " " + noun + (list.length === 1 ? "" : "s")))));
        }
        list.forEach(function (it) {
          var r = h("tr", { class: it.track ? "is-track-" + it.track.grade : null });
          C.forEach(function (c, i) { r.appendChild(h(i === 1 ? "th" : "td", { scope: i === 1 ? "row" : null, class: c.n ? "is-num" : null }, c.cell(it))); });
          tb.appendChild(r);
        });
        t.appendChild(tb);
      }
      if (B.group) {
        var by = {};
        rows.forEach(function (it) { var c = it.client || "No client"; (by[c] = by[c] || []).push(it); });
        clients().forEach(function (c) { body(by[c.name], c.name); });
      } else body(rows, null);
      tbl.appendChild(h("div", { class: "hvb-t__wrap", tabindex: "0", role: "region", "aria-label": (noun === "campaign" ? "Campaigns" : "Selections") + " table" }, t));
    }

    // Optimistic: the card moves at once; the server's no puts it back with the reason.
    B.move = function (it, to, sel) {
      if (it.moves.indexOf(to) < 0) return;
      var from = it.stage, label = (opts.stages.filter(function (s) { return s.key === to; })[0] || {}).label || to;
      it.stage = to;
      it.moves = it.moves.filter(function (k) { return k !== to; }).concat([from]);
      redraw();
      B.say("Moving " + it.name + " to " + label + "…");
      opts.onMove(it, to).then(function (j) {
        if (j && j.ok) { B.say(j.message || (it.name + " moved to " + label + ".")); return; }
        it.stage = from;
        it.moves = it.moves.filter(function (k) { return k !== from; }).concat([to]);
        redraw();
        B.say((j && j.message) || ("Couldn’t move " + it.name + ". Please try again."), true);
      });
    };

    function wireDrag() {
      root.querySelectorAll(".hvb-card[draggable]").forEach(function (el) {
        el.addEventListener("dragstart", function (e) {
          var held = B.held = items.filter(function (x) { return x.key === el.getAttribute("data-key"); })[0];
          if (!held) return;
          el.classList.add("is-dragging");
          root.classList.add("is-dragging");
          root.querySelectorAll("[data-drop]").forEach(function (t) { t.classList.toggle("can-drop", held.moves.indexOf(t.getAttribute("data-drop")) >= 0); });
          e.dataTransfer.effectAllowed = "move";
          try { e.dataTransfer.setData("text/plain", held.key); } catch (x) { /* old browsers */ }
        });
        el.addEventListener("dragend", function () {
          el.classList.remove("is-dragging"); root.classList.remove("is-dragging"); B.held = null;
          root.querySelectorAll("[data-drop]").forEach(function (l) { l.classList.remove("can-drop", "is-over"); });
        });
      });
      root.querySelectorAll("[data-drop]").forEach(function (L) {
        var key = L.getAttribute("data-drop");
        if (L.hvbWired) return;
        L.hvbWired = true;
        L.addEventListener("dragover", function (e) {
          if (!B.held || B.held.moves.indexOf(key) < 0) return;
          e.preventDefault(); e.dataTransfer.dropEffect = "move"; L.classList.add("is-over");
        });
        L.addEventListener("dragleave", function (e) { if (!L.contains(e.relatedTarget)) L.classList.remove("is-over"); });
        L.addEventListener("drop", function (e) {
          e.preventDefault(); L.classList.remove("is-over");
          if (B.held && B.held.moves.indexOf(key) >= 0) B.move(B.held, key);
        });
      });
    }

    // Phones: the columns swipe one per screen; the stage pills follow and jump.
    var jumping = 0, tick = null;
    B.jump = function (i) {
      B.lane = i; jumping = Date.now();
      var lane = grid.querySelector('.hvb-lane[data-i="' + i + '"]');
      if (lane) grid.scrollTo({ left: lane.offsetLeft - grid.offsetLeft, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
      mark();
    };
    function mark() {
      tabBar.querySelectorAll(".hvb-tab").forEach(function (b) {
        var on = +b.getAttribute("data-i") === B.lane;
        b.setAttribute("aria-selected", on ? "true" : "false");
        if (on && tabBar.scrollWidth > tabBar.clientWidth) tabBar.scrollLeft = b.offsetLeft - tabBar.offsetLeft - 16;
      });
    }
    function edges() {
      var max = grid.scrollWidth - grid.clientWidth;
      grid.classList.toggle("more-right", max > 4 && grid.scrollLeft < max - 4);
      grid.classList.toggle("more-left", grid.scrollLeft > 4);
    }
    B.edges = edges;
    window.addEventListener("resize", edges, { passive: true });
    grid.addEventListener("scroll", edges, { passive: true });
    grid.addEventListener("scroll", function () {
      if (!matchMedia("(max-width: 899px)").matches) return;
      clearTimeout(tick);
      tick = setTimeout(function () {
        if (Date.now() - jumping < 900) return;
        var first = grid.querySelector(".hvb-lane");
        var w = (first && first.offsetWidth) || 1;
        var i = Math.max(0, Math.min(opts.stages.length - 1, Math.round(grid.scrollLeft / (w + 12))));
        if (i !== B.lane) { B.lane = i; mark(); }
      }, 80);
    }, { passive: true });

    function redraw() { if (opts.view === "table") table(); else draw(); }
    redraw();
    host.appendChild(root);
    if (opts.view === "table") return B;
    requestAnimationFrame(edges);
    // Open on the first column that holds something, so a phone never lands on an empty Draft.
    var firstFull = 0;
    for (var i = 0; i < opts.stages.length; i++) { if (items.some(function (it) { return it.stage === opts.stages[i].key; })) { firstFull = i; break; } }
    if (firstFull && matchMedia("(max-width: 899px)").matches) { B.lane = firstFull; requestAnimationFrame(function () { B.jump(firstFull); }); }
    else mark();
    return B;
  }

  /* ------------------------------------------------------- Board | List */
  // The view switch in a section head. The choice is remembered per section in this browser only.
  // Board | Table | List (item 199). The choice is remembered per section in this browser only.
  var VIEWS = [["board", "Board"], ["table", "Table"], ["list", "List"]];
  function viewSwitch(key, current, onPick, only) {
    var wrap = h("div", { class: "hvb-view", role: "group", "aria-label": "View" });
    VIEWS.filter(function (v) { return !only || only.indexOf(v[0]) >= 0; }).forEach(function (v) {
      wrap.appendChild(h("button", { type: "button", "aria-pressed": v[0] === current ? "true" : "false", onclick: function () {
        try { localStorage.setItem("hvb-view-" + key, v[0]); } catch (e) { /* private mode */ }
        onPick(v[0]);
      } }, v[1]));
    });
    return wrap;
  }
  function viewOf(key, only) {
    var v = null;
    try { v = localStorage.getItem("hvb-view-" + key); } catch (e) { /* private mode */ }
    return v && (!only || only.indexOf(v) >= 0) && VIEWS.some(function (x) { return x[0] === v; }) ? v : "board";
  }

  window.HVBoard = { mount: mount, fromCampaign: fromCampaign, fromSelection: fromSelection, viewSwitch: viewSwitch, viewOf: viewOf };
})();
