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
    brief: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>',
    pen: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M14 6l4 4"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
    flag: '<path d="M5 21V4h11l-1.5 4L16 12H5"/>',
    // Item 219: the Activity control, and one drawn mark per stage (same 24 grid, 1.8 stroke as the rest).
    history: '<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1"/><path d="M3 4.5v4h4"/><path d="M12 8v4.2l2.8 1.8"/>',
    st_draft: '<path d="M4.5 19.5h15"/><path d="M14.6 4.6l3.8 3.8L9.6 17.2H5.8v-3.8z"/>',
    st_shortlisting: '<path d="M4 5h16l-6.2 7.4v5.8l-3.6 1.8v-7.6z"/>',
    st_review: '<path d="M2.5 12S6 5.8 12 5.8 21.5 12 21.5 12 18 18.2 12 18.2 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.7"/>',
    st_approved: '<circle cx="12" cy="12" r="8.6"/><path d="M8.3 12.3l2.5 2.5 5-5.2"/>',
    st_live: '<circle cx="12" cy="12" r="1.9"/><path d="M8.2 8.2a5.4 5.4 0 0 0 0 7.6M15.8 8.2a5.4 5.4 0 0 1 0 7.6M5.3 5.3a9.5 9.5 0 0 0 0 13.4M18.7 5.3a9.5 9.5 0 0 1 0 13.4"/>',
    st_completed: '<path d="M8 4h8v5.2a4 4 0 0 1-8 0z"/><path d="M8 6H5.2a3 3 0 0 0 3.1 4M16 6h2.8a3 3 0 0 1-3.1 4M12 13.2V17M8.5 20h7M9.8 17h4.4"/>',
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
  // Item 219: a stage's mark, a small disc in the stage's colour. Decorative: the stage name is always written beside it.
  function stageIcon(key, cls) {
    if (!ICON["st_" + key]) return null;
    return h("span", { class: "hvb-stico hvb-lane--" + key + (cls ? " " + cls : ""), "aria-hidden": "true" }, svg("st_" + key));
  }

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
      briefs: c.briefs || [], canEdit: !!c.can_edit, edit: c.edit || null,
      next: c.next || null, activity: c.activity || [], kamEmail: c.kam && c.kam.email ? c.kam.email.toLowerCase() : "",
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
    // Item 214: our own work, or a card with no client known and no logo, shows HelloVoice once (no dangling ×).
    if (ours(it.client) || (!it.client && !it.logos.length)) return lock;
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

  // Item 205: the one next step and when it is due; late ones turn red.
  function nextLine(n) {
    return h("p", { class: "hvb-next" + (n.overdue ? " is-late" : "") }, svg("flag"),
      h("span", null, h("b", null, "Next: "), n.text || "Set a next step"),
      n.due ? h("span", { class: "hvb-due" + (n.overdue ? " is-late" : "") }, (n.overdue ? "Was due " : "Due ") + dm(n.due)) : null);
  }
  function trackPill(t) { return h("span", { class: "hvb-track hvb-track--" + t.grade, title: "Against the campaign's goal, as the dashboard reads it" }, t.label); }
  // Item 203: "Open selection" (a short list when the campaign holds several) and "Open dashboard".
  function goButtons(it, B) {
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
    // Item 204: the brief, anchored to the campaign card; item 197: every edit from the card.
    if (B && it.briefs && it.briefs.length) {
      var has = it.briefs.some(function (x) { return x.brief; });
      var bb = h("button", { type: "button", class: "hvb-go" + (has ? "" : " is-missing"), title: has ? "Read or edit the brief" : "No brief yet" },
        svg("brief"), "Brief", h("span", { class: "hvb-sr" }, ": " + it.name));
      bb.addEventListener("click", function () { panel(it, B, "brief", bb); });
      out.push(bb);
    }
    if (B && it.canEdit) {
      var eb = h("button", { type: "button", class: "hvb-go hvb-go--edit", "aria-label": "Edit " + it.name, title: "Edit this campaign" }, svg("pen"), "Edit");
      eb.addEventListener("click", function () { panel(it, B, "details", eb); });
      out.push(eb);
    }
    return out;
  }

  /* --------------------------------- the campaign panel: brief + edits (items 197, 204, 206) */
  function call(method, path, body) {
    return fetch(API_BASE + path, { method: method, credentials: "include", cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { s: r.status, b: b }; }); },
            function () { return { s: 0, b: {} }; });
  }
  function ymd(ts) { if (!ts) return ""; var d = new Date(ts * 1000); return d.toISOString().slice(0, 10); }
  var OBJ = [["balanced", "Balanced"], ["awareness", "Awareness"], ["engagement", "Engagement"], ["traffic", "Traffic"]];
  var TGT = [["posts", "Posts"], ["views", "Views"], ["reach", "Reach"], ["engagement", "Engagement"], ["er", "Eng. rate %"], ["clicks", "Clicks"]];
  function panel(it, B, focus, opener) {
    var old = document.querySelector(".hvb-panel-back"); if (old) old.remove();
    var c = it.raw, changed = false;
    var back = h("div", { class: "hvb hvb-panel-back" });         // .hvb: the board's tokens and icon strokes
    var box = h("aside", { class: "hvb-panel", role: "dialog", "aria-modal": "true", "aria-labelledby": "hvb-panel-t" });
    var shut = h("button", { type: "button", class: "hvb-panel__x", "aria-label": "Close" }, svg("x"));
    box.appendChild(h("header", { class: "hvb-panel__head" }, brand(it),
      h("h2", { id: "hvb-panel-t", class: "hvb-panel__t" }, it.name), shut));
    var bodyEl = h("div", { class: "hvb-panel__body" });
    box.appendChild(bodyEl);
    function note(sec, text, bad) {
      var n = sec.querySelector(".hvb-panel__msg");
      n.textContent = text || ""; n.className = "hvb-panel__msg" + (bad ? " is-bad" : "");
    }
    function section(key, title, kids, lead) {
      var sec = h("section", { class: "hvb-panel__sec", "data-sec": key }, h("h3", null, title), lead ? h("p", { class: "hvb-panel__lead" }, lead) : null);
      add(sec, kids);
      sec.appendChild(h("p", { class: "hvb-panel__msg", role: "status", "aria-live": "polite" }));
      bodyEl.appendChild(sec);
      return sec;
    }
    // Logo and selections act at once (an upload, a link); everything else waits for the one Save.
    function save(sec, path, payload, okText) {
      note(sec, "Saving…");
      return call("POST", path, payload).then(function (r) {
        var ok = r.b && r.b.ok;
        note(sec, ok ? (okText || r.b.message || "Saved.") : ((r.b && r.b.message) || "Couldn't save that. Please try again."), !ok);
        if (ok) changed = true;
        return ok;
      });
    }
    function field(label, input, hint) { return h("label", { class: "hvb-field" }, h("span", null, label), input, hint || null); }

    /* -- items 211-213: one brief per campaign, every question the AI shortlister asks -- */
    var S = { q: null, ans: {}, ans0: {}, sug: {}, plan: null, tg: {}, tg0: {}, typed: {}, typed0: {}, d: {}, d0: {} };
    var tgSec = it.canEdit ? section("goal", "Objective and targets", h("p", { class: "is-muted" }, "Working out the targets…")) : null;
    var briefSec = section("brief", "Brief", h("p", { class: "is-muted" }, "Opening the brief…"));
    var bar = null, barText = null, barBtn = null, savedAt = null, touched = false;
    box.addEventListener("input", function () { touched = true; }, true);
    box.addEventListener("click", function (e) { if (e.target.closest && e.target.closest(".hvb-opt, .hvb-sug, .hvb-goal__o, .hvb-go--ai, .hvb-link--ink")) touched = true; }, true);

    function same(a, b) { return JSON.stringify(a == null ? null : a) === JSON.stringify(b == null ? null : b); }
    function list(v) { return v == null || v === "" ? [] : Array.isArray(v) ? v : [v]; }
    function labelOf(q, v) {
      var m = {}; (q.options || []).forEach(function (o) { m[o.value] = o.label; });
      return list(v).map(function (x) { return m[x] || String(x).replace(/^other:/, ""); }).join(", ");
    }
    function num(v) { return v == null || v === "" ? "" : Number(v).toLocaleString("en-US"); }

    function dirty() {
      var n = 0;
      Object.keys(S.d0).forEach(function (k) { if (!same(S.d[k], S.d0[k])) n++; });
      var qs = {}; Object.keys(S.ans).concat(Object.keys(S.ans0)).forEach(function (k) { qs[k] = 1; });
      Object.keys(qs).forEach(function (k) { if (!same(list(S.ans[k]), list(S.ans0[k]))) n++; });
      TGT.forEach(function (t) { if (!same(S.tg[t[0]] || null, S.tg0[t[0]] || null)) n++; });
      return n;
    }
    function paint(state, text) {
      if (!bar) return;
      var n = dirty();
      bar.className = "hvb-savebar" + (state ? " is-" + state : n ? " is-dirty" : " is-clean");
      var onlyAi = n && !touched;
      barText.textContent = text || (onlyAi ? "Helvi filled the targets. Save to keep them." : n ? n + " unsaved change" + (n === 1 ? "" : "s")
        : savedAt ? "All changes saved · " + savedAt : "No changes yet");
      barBtn.disabled = state === "busy" || !n;
      barBtn.textContent = state === "busy" ? "Saving…" : !n && savedAt ? "Saved" : "Save changes";
    }

    function chip(q, value, label, on, single) {
      var b = h("button", { type: "button", class: "hvb-opt", "aria-pressed": on ? "true" : "false" }, label);
      b.addEventListener("click", function () {
        var cur = list(S.ans[q.id]);
        if (single) cur = on ? [] : [value];
        else cur = on ? cur.filter(function (x) { return x !== value; }) : cur.concat([value]);
        S.ans[q.id] = q.type === "many" ? cur : (cur[0] || null);
        if (!list(S.ans[q.id]).length) delete S.ans[q.id];
        answered(q);
      });
      return b;
    }
    // One question as a row: its answer at a glance; open it to pick, or take Helvi's suggestion.
    var rows = {};
    function row(q) {
      var r = rows[q.id] = h("div", { class: "hvb-q", "data-q": q.id });
      var head = h("button", { type: "button", class: "hvb-q__head", "aria-expanded": "false" });
      var body = h("div", { class: "hvb-q__body", hidden: true });
      r.appendChild(head); r.appendChild(body);
      head.addEventListener("click", function () {
        var open = head.getAttribute("aria-expanded") !== "true";
        head.setAttribute("aria-expanded", open ? "true" : "false");
        body.hidden = !open;
      });
      draw(q);
      return r;
    }
    function draw(q) {
      var r = rows[q.id]; if (!r) return;
      var head = r.firstChild, body = r.lastChild, v = S.ans[q.id], sg = S.sug[q.id];
      var has = list(v).length > 0, ro = !it.canEdit;
      var sugSame = sg && same(list(sg.value).slice().sort(), list(v).slice().sort());
      r.classList.toggle("is-set", has);
      head.textContent = "";
      add(head, [h("span", { class: "hvb-q__l" }, q.label, q.required ? h("i", { class: "hvb-q__req", title: "Needed to update the selections" }, " *") : null),
        h("span", { class: "hvb-q__a" + (has ? "" : " is-empty") }, has ? (q.type === "text" ? String(v) : labelOf(q, v))
          : sg && !ro ? [h("i", { class: "hvb-q__hv" }, "Helvi"), " " + labelOf(q, sg.value)] : "Not set"),
        ro ? null : svg("chev", "hvb-q__chev")]);
      if (ro) { head.disabled = true; return; }
      body.textContent = "";
      if (sg && !sugSame) {
        var take = h("button", { type: "button", class: "hvb-sug" }, h("b", null, "Use Helvi’s: " + labelOf(q, sg.value)), h("small", null, sg.why));
        take.addEventListener("click", function () { S.ans[q.id] = Array.isArray(sg.value) || q.type !== "many" ? sg.value : [sg.value]; answered(q); });
        body.appendChild(take);
      } else if (sg) body.appendChild(h("p", { class: "hvb-q__why" }, "Matches Helvi: " + sg.why));
      if (q.type === "text") {
        var inp = h("input", { type: "text", value: v || "", maxlength: String(q.max || 200), "aria-label": q.label });
        inp.addEventListener("input", function () { if (inp.value.trim()) S.ans[q.id] = inp.value; else delete S.ans[q.id]; paint(); var a = head.querySelector(".hvb-q__a"); a.textContent = inp.value.trim() || "Not set"; a.classList.toggle("is-empty", !inp.value.trim()); });
        body.appendChild(inp);
      } else {
        var opts = h("div", { class: "hvb-opts", role: "group", "aria-label": q.label });
        var cur = list(v);
        q.options.forEach(function (o) { opts.appendChild(chip(q, o.value, o.label, cur.indexOf(o.value) >= 0, q.type === "one")); });
        body.appendChild(opts);
      }
    }
    function answered(q) {
      draw(q);
      var r = rows[q.id];
      if (r) { r.firstChild.setAttribute("aria-expanded", "true"); r.lastChild.hidden = false; }
      if (q.id === "goal") drawGoal();
      if (["goal", "platforms", "category"].indexOf(q.id) >= 0) replan();
      paint();
    }

    function drawBrief(b) {
      briefSec.textContent = "";
      briefSec.appendChild(h("h3", null, "Brief"));
      if (!it.canEdit) {
        if (!b.answers || !b.answers.length) briefSec.appendChild(h("p", { class: "is-muted" }, "No brief yet. Your account manager adds it here."));
        (b.answers || []).forEach(function (g) {
          briefSec.appendChild(h("h4", { class: "hvb-qg" }, g.label));
          g.items.forEach(function (x) { briefSec.appendChild(h("div", { class: "hvb-q is-set" }, h("div", { class: "hvb-q__head" }, h("span", { class: "hvb-q__l" }, x.label), h("span", { class: "hvb-q__a" }, x.answer)))); });
        });
        return;
      }
      var open = S.q.reduce(function (n, g) { return n + g.items.filter(function (q) { return q.id !== "goal" && !list(S.ans[q.id]).length && S.sug[q.id]; }).length; }, 0);
      var lead = h("div", { class: "hvb-brief__lead" },
        h("p", null, b.meta && b.meta.seeded ? "Started from this campaign’s selections. Tap a question to change it." : "Tap a question to change it."));
      if (open) {
        var all = h("button", { type: "button", class: "hvb-go hvb-go--ai" }, "Use Helvi’s suggestions (" + open + ")");
        all.addEventListener("click", function () {
          S.q.forEach(function (g) { g.items.forEach(function (q) { if (q.id !== "goal" && !list(S.ans[q.id]).length && S.sug[q.id]) { S.ans[q.id] = S.sug[q.id].value; draw(q); } }); });
          all.remove(); replan(); paint();
        });
        lead.appendChild(all);
      }
      briefSec.appendChild(lead);
      S.q.forEach(function (g) {
        var qs = g.items.filter(function (q) { return q.id !== "goal"; });        // the goal is the objective, below
        if (!qs.length) return;
        briefSec.appendChild(h("h4", { class: "hvb-qg" }, g.label));
        qs.forEach(function (q) { briefSec.appendChild(row(q)); });
      });
      briefSec.appendChild(h("p", { class: "hvb-panel__msg", role: "status", "aria-live": "polite" }));
    }

    /* -- item 211: the objective fills the targets; any number can be typed over -- */
    var goalQ = null, tIn = {};
    function drawGoal() {
      var g = tgSec.querySelector(".hvb-goal"); if (!g || !goalQ) return;
      g.textContent = "";
      var cur = list(S.ans.goal);
      goalQ.options.forEach(function (o) {
        var on = cur.indexOf(o.value) >= 0;
        var b = h("button", { type: "button", class: "hvb-goal__o", "aria-pressed": on ? "true" : "false" }, h("b", null, o.label), o.hint ? h("small", null, o.hint) : null);
        b.addEventListener("click", function () {
          var now = list(S.ans.goal);
          S.ans.goal = on ? now.filter(function (x) { return x !== o.value; }) : now.concat([o.value]);
          answered(goalQ);
        });
        g.appendChild(b);
      });
    }
    function drawTargets() {
      var grid = tgSec.querySelector(".hvb-tg"); if (!grid) return;
      grid.textContent = "";
      var P = S.plan || { targets: {}, likely: {}, why: {}, headline: [] };
      var keys = TGT.map(function (t) { return t[0]; }).filter(function (k) { return P.targets[k] != null || S.tg[k] != null; });
      keys.sort(function (a, b) { return (P.headline.indexOf(a) < 0) - (P.headline.indexOf(b) < 0); });
      if (!keys.length) { grid.appendChild(h("p", { class: "is-muted" }, (P.why && P.why.posts) || "Pick an objective to fill the targets.")); return; }
      keys.forEach(function (k) {
        var lab = TGT.filter(function (t) { return t[0] === k; })[0][1], ai = P.targets[k];
        var inp = tIn[k] = h("input", { type: "number", min: "0", step: k === "er" ? "0.01" : "1", inputmode: "decimal", value: S.tg[k] != null ? String(S.tg[k]) : "", "aria-label": lab });
        var mine = S.typed[k] && ai != null && Number(S.tg[k]) !== Number(ai);
        var tag = h("span", { class: "hvb-tgt__tag" + (mine ? " is-mine" : "") }, mine ? "Your number" : "Helvi");
        var useAi = mine ? h("button", { type: "button", class: "hvb-link hvb-link--ink" }, "Use Helvi’s: " + num(ai) + (k === "er" ? "%" : "")) : null;
        if (useAi) useAi.addEventListener("click", function () { S.tg[k] = ai; delete S.typed[k]; drawTargets(); paint(); });
        inp.addEventListener("input", function () {
          S.tg[k] = inp.value === "" ? null : Number(inp.value);
          if (ai != null && Number(inp.value) === Number(ai)) delete S.typed[k]; else S.typed[k] = 1;
          var m = S.typed[k] && ai != null;
          tag.textContent = m ? "Your number" : "Helvi"; tag.classList.toggle("is-mine", !!m);
          paint();
        });
        var why = P.why[k] ? h("details", { class: "hvb-tgt__why" }, h("summary", null, "Where this comes from"), h("p", null, P.why[k])) : null;
        grid.appendChild(h("div", { class: "hvb-tgt" + (P.headline.indexOf(k) >= 0 ? " is-lead" : "") },
          h("div", { class: "hvb-tgt__top" }, h("span", { class: "hvb-tgt__l" }, lab), tag),
          inp,
          P.likely && P.likely[k] != null ? h("small", { class: "hvb-tgt__likely" }, "Likely " + num(P.likely[k]) + (k === "er" ? "%" : "")) : null,
          useAi, why));
      });
    }
    // Helvi's numbers follow the objective, the platforms and the space; typed ones stay.
    var planSeq = 0, planT = null;
    function applyPlan(p, first) {
      S.plan = p;
      TGT.forEach(function (t) {
        var k = t[0];
        if (S.typed[k]) return;
        if (first && S.tg0[k] != null) return;          // a saved target the page has no reason to touch
        if (p.targets[k] != null) S.tg[k] = p.targets[k]; else delete S.tg[k];
      });
      drawTargets(); paint();
    }
    function replan() {
      if (!tgSec) return;
      clearTimeout(planT);
      var seq = ++planSeq;
      planT = setTimeout(function () {
        tgSec.classList.add("is-busy");
        call("POST", "/api/board/plan", { t: c.token, answers: S.ans }).then(function (r) {
          if (seq !== planSeq) return;
          tgSec.classList.remove("is-busy");
          if (r.b && r.b.ok) applyPlan(r.b);
          else note(tgSec, (r.b && r.b.message) || "Couldn’t work out the targets just now.", true);
        });
      }, 250);
    }

    call("GET", "/api/board/brief?t=" + encodeURIComponent(c.token)).then(function (r) {
      var b = r.b || {};
      if (!b.ok) { briefSec.textContent = ""; briefSec.appendChild(h("h3", null, "Brief")); briefSec.appendChild(h("p", { class: "is-muted" }, "Couldn’t open the brief just now. Close and try again.")); return; }
      if (!it.canEdit) { drawBrief(b); return; }
      S.q = b.questions; S.sug = b.suggest || {};
      S.ans = JSON.parse(JSON.stringify(b.answers || {})); S.ans0 = JSON.parse(JSON.stringify(b.answers || {}));
      S.tg = JSON.parse(JSON.stringify(b.targets || {})); S.tg0 = JSON.parse(JSON.stringify(b.targets || {}));
      ((b.meta && b.meta.typed) || []).forEach(function (k) { S.typed[k] = 1; });
      S.typed0 = JSON.parse(JSON.stringify(S.typed));
      if (b.meta && b.meta.saved_at) savedAt = when(b.meta.saved_at);
      S.q.forEach(function (g) { g.items.forEach(function (q) { if (q.id === "goal") goalQ = q; }); });
      drawBrief(b);
      tgSec.textContent = "";
      add(tgSec, [h("h3", null, "Objective and targets"),
        h("p", { class: "hvb-panel__lead" }, "Pick the objective. Helvi fills the targets from this campaign’s creators; change any number you like."),
        h("div", { class: "hvb-goal", role: "group", "aria-label": "Objective" }),
        h("div", { class: "hvb-tg" }),
        h("p", { class: "hvb-panel__msg", role: "status", "aria-live": "polite" })]);
      drawGoal();
      applyPlan(b.plan || { targets: {}, likely: {}, why: {}, headline: [] }, true);
    });
    function when(ts) { var d = new Date(ts * 1000); return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) + (new Date().toDateString() === d.toDateString() ? "" : ", " + d.toLocaleDateString([], { day: "numeric", month: "short" })); }

    if (it.canEdit) {
      var f = {};
      f.name = h("input", { type: "text", value: it.name, maxlength: "120", required: true });
      f.client = h("input", { type: "text", value: c.client || "", maxlength: "120" });
      f.starts = h("input", { type: "date", value: ymd(c.starts_at) });
      f.ends = h("input", { type: "date", value: ymd(c.ends_at) });
      f.next = h("input", { type: "text", value: (it.edit && it.edit.next) || "", maxlength: "140", placeholder: "e.g. Send the quote to the client" });
      f.due = h("input", { type: "date", value: ymd(it.edit && it.edit.due) });
      section("details", "Details", [field("Name", f.name), field("Client", f.client),
        h("div", { class: "hvb-panel__two" }, field("First day", f.starts), field("Last day", f.ends)),
        field("Next step", f.next), field("Next step due", f.due)]);
      if (B.opts.kams && B.opts.kams.length) {
        f.kam = h("select", null, [h("option", { value: "" }, "No account manager")].concat(B.opts.kams.map(function (k) {
          return h("option", { value: k.email, selected: (c.kam && c.kam.email === k.email) || null }, k.name);
        })));
        section("kam", "Account manager", [field("Account manager", f.kam)]);
      }
      Object.keys(f).forEach(function (k) {
        S.d0[k] = S.d[k] = f[k].value;
        f[k].addEventListener(f[k].tagName === "SELECT" ? "change" : "input", function () { S.d[k] = f[k].value; paint(); });
      });
      var file = h("input", { type: "file", accept: "image/png,image/jpeg,image/webp" });
      var lsec = section("logo", "Client logo", [h("div", { class: "hvb-panel__logo" }, brand(it)), field("Upload a new logo (PNG, JPG or WebP)", file)],
        "Saves as soon as you pick a file.");
      file.addEventListener("change", function () {
        var fl = file.files && file.files[0];
        if (!fl) return;
        if (fl.size > 700 * 1024) { note(lsec, "Use a logo under 700 KB.", true); return; }
        var rd = new FileReader();
        rd.onload = function () { save(lsec, "/api/board/logo", { t: c.token, data: rd.result }, "Logo saved. It shows on the card when you close this."); };
        rd.readAsDataURL(fl);
      });
      // Selections: take one out, or add another of the client's.
      var cur = h("ul", { class: "hvb-panel__sels" });
      (c.selections || []).forEach(function (x) {
        var rm = h("button", { type: "button", class: "hvb-link" }, "Remove");
        var li = h("li", null, h("a", { href: ROOT + "selection/#s=" + encodeURIComponent(x.token) }, x.name), h("small", null, x.creators + " creators"), rm);
        rm.addEventListener("click", function () {
          rm.disabled = true;
          save(ssec, "/api/board/detach", { t: c.token, s: x.token }).then(function (ok) { if (ok) { li.remove(); replan(); } else rm.disabled = false; });
        });
        cur.appendChild(li);
      });
      var pick = h("select", { "aria-label": "A selection to add" }, h("option", { value: "" }, "Loading the client's selections…"));
      var addB = h("button", { type: "button", class: "hvb-btn hvb-btn--ghost" }, "Add to campaign");
      var ssec = section("sels", "Selections", [cur, h("div", { class: "hvb-panel__row" }, pick, addB)], "Adding or removing one saves at once and updates Helvi’s targets.");
      call("GET", "/api/board/attachable?t=" + encodeURIComponent(c.token)).then(function (r) {
        var lst = (r.b && r.b.selections) || [];
        pick.textContent = "";
        pick.appendChild(h("option", { value: "" }, lst.length ? "Pick a selection" : "No other selections for this client"));
        lst.forEach(function (x) { pick.appendChild(h("option", { value: x.token }, x.name + " · " + x.creators + " creators")); });
      });
      addB.addEventListener("click", function () {
        if (!pick.value) { note(ssec, "Pick a selection first.", true); return; }
        var label = pick.options[pick.selectedIndex].textContent.split(" · ")[0];
        save(ssec, "/api/board/attach", { s: pick.value, t: c.token }).then(function (ok) {
          if (ok) { cur.appendChild(h("li", null, h("span", null, label), h("small", null, "added"))); pick.remove(pick.selectedIndex); replan(); }
        });
      });

      // Item 212: one Save for everything above, with a state that always says where the panel is.
      barText = h("p", { class: "hvb-savebar__t", role: "status", "aria-live": "polite" });
      barBtn = h("button", { type: "button", class: "hvb-btn hvb-savebar__go" }, "Save changes");
      bar = h("footer", { class: "hvb-savebar is-clean" }, barText, barBtn);
      box.appendChild(bar);
      box.classList.add("has-bar");
      barBtn.addEventListener("click", saveAll);
    }
    var D_KEY = { name: "name", client: "client", starts: "starts", ends: "ends", next: "next", due: "due" };
    function saveAll() {
      if (!dirty()) return;
      unask();
      var p = { t: c.token };
      Object.keys(D_KEY).forEach(function (k) { if (!same(S.d[k], S.d0[k])) p[D_KEY[k]] = S.d[k]; });
      if ((p.starts != null || p.ends != null)) { p.starts = S.d.starts; p.ends = S.d.ends; }
      if (S.d0.kam != null && !same(S.d.kam, S.d0.kam)) p.kam = S.d.kam;
      var qs = {}; Object.keys(S.ans).concat(Object.keys(S.ans0)).forEach(function (k) { qs[k] = 1; });
      var briefChanged = Object.keys(qs).some(function (k) { return !same(list(S.ans[k]), list(S.ans0[k])); });
      var tgChanged = TGT.some(function (t) { return !same(S.tg[t[0]] || null, S.tg0[t[0]] || null); });
      if (briefChanged) { p.brief = { answers: S.ans }; }
      if (tgChanged || briefChanged) {
        p.targets = {}; TGT.forEach(function (t) { if (S.tg[t[0]] != null) p.targets[t[0]] = S.tg[t[0]]; });
        p.typed = Object.keys(S.typed);
      }
      paint("busy", "Saving…");
      call("POST", "/api/board/save", p).then(function (r) {
        var ok = r.b && r.b.ok;
        if (!ok) {
          paint("bad", (r.b && r.b.message) || "Couldn’t save. Nothing was changed; please try again.");
          var fk = r.b && r.b.field, at = fk === "goal" ? tgSec : fk === "kam" ? bodyEl.querySelector('[data-sec="kam"]') : null;
          if (at) at.scrollIntoView({ block: "start", behavior: "smooth" });
          return;
        }
        changed = true;
        S.d0 = JSON.parse(JSON.stringify(S.d)); S.ans0 = JSON.parse(JSON.stringify(S.ans));
        S.tg0 = JSON.parse(JSON.stringify(S.tg)); S.typed0 = JSON.parse(JSON.stringify(S.typed));
        savedAt = when((r.b && r.b.saved_at) || Date.now() / 1000);
        paint("saved", r.b.message && r.b.message !== "Saved." ? r.b.message + " · " + savedAt : "All changes saved · " + savedAt);
        if (p.name) { box.querySelector(".hvb-panel__t").textContent = p.name; }
      });
    }
    back.appendChild(box);
    function close(force) {
      if (bar && !force && dirty()) { ask(); return; }
      document.removeEventListener("keydown", key, true);
      back.remove();
      document.body.classList.remove("hvb-panel-open");
      if (changed && B.opts.onChange) B.opts.onChange();
      else if (opener && document.contains(opener)) opener.focus();
    }
    // Closing with unsaved edits asks once, in the bar, never in a browser dialog.
    function ask() {
      if (bar.querySelector(".hvb-savebar__ask")) return;
      var keep = h("button", { type: "button", class: "hvb-btn hvb-btn--ghost" }, "Keep editing");
      var drop = h("button", { type: "button", class: "hvb-link" }, "Discard");
      var q = h("div", { class: "hvb-savebar__ask", role: "alertdialog", "aria-label": "Unsaved changes" }, h("p", null, "Close without saving " + dirty() + " change" + (dirty() === 1 ? "" : "s") + "?"), keep, drop, barBtn);
      bar.textContent = ""; bar.className = "hvb-savebar is-ask"; bar.appendChild(q);
      keep.addEventListener("click", function () { unask(); barBtn.focus(); });
      drop.addEventListener("click", function () { close(true); });
      keep.focus();
    }
    function unask() { if (!bar.querySelector(".hvb-savebar__ask")) return; bar.textContent = ""; bar.appendChild(barText); bar.appendChild(barBtn); paint(); }
    function key(e) {
      if (e.key === "Escape") { e.preventDefault(); close(); return; }
      if (e.key !== "Tab") return;
      var f = box.querySelectorAll("button:not([disabled]), a[href], input, select, textarea, summary");
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
    shut.addEventListener("click", function () { close(); });
    back.addEventListener("click", function (e) { if (e.target === back) close(); });
    document.addEventListener("keydown", key, true);
    document.body.classList.add("hvb-panel-open");
    document.body.appendChild(back);
    paint();
    var target = bodyEl.querySelector('[data-sec="' + focus + '"]') || bodyEl.firstChild;
    requestAnimationFrame(function () {
      target.scrollIntoView({ block: "start" });
      var first = target.querySelector("input, select, button, a[href]");
      (first || shut).focus({ preventScroll: true });
    });
  }

  /* ------------------------------- item 219: the Activity panel (a card's full history, floating) */
  var ACT = null;                                   // the open panel: {key, el, opener, close}
  function dayOf(ts) {
    var d = new Date(ts * 1000), t = new Date(), y = new Date(); y.setDate(t.getDate() - 1);
    var same = function (a, b) { return a.toDateString() === b.toDateString(); };
    if (same(d, t)) return "Today";
    if (same(d, y)) return "Yesterday";
    return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: d.getFullYear() === t.getFullYear() ? undefined : "numeric" });
  }
  function clock(ts) { return new Date(ts * 1000).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }); }
  function activityPanel(it, B, opener) {
    var key = B.noun + ":" + it.key;
    if (ACT && ACT.key === key) { ACT.close(); return; }      // the same button shuts it
    if (ACT) ACT.close(true);
    var shut = h("button", { type: "button", class: "hvb-actp__x", "aria-label": "Close activity" }, svg("x"));
    var body = h("div", { class: "hvb-actp__body", "aria-busy": "true" }, h("p", { class: "hvb-actp__state" }, "Loading the history…"));
    var box = h("aside", { id: "hvb-actp", class: "hvb hvb-actp", role: "dialog", "aria-modal": "false", "aria-labelledby": "hvb-actp-t" },
      h("header", { class: "hvb-actp__head" },
        h("div", { class: "hvb-actp__who" }, brand(it), h("h2", { id: "hvb-actp-t", class: "hvb-actp__t" }, "Activity"),
          h("p", { class: "hvb-actp__name" }, it.name)), shut),
      body);
    var scrim = h("div", { class: "hvb-actp-scrim" });
    function setOpener(on) {
      document.querySelectorAll(".hvb-actb.is-on").forEach(function (b) { b.classList.remove("is-on"); b.setAttribute("aria-expanded", "false"); });
      if (on && opener) { opener.classList.add("is-on"); opener.setAttribute("aria-expanded", "true"); }
    }
    function close(quiet) {
      document.removeEventListener("keydown", esc, true);
      box.remove(); scrim.remove();
      document.body.classList.remove("hvb-actp-open");
      setOpener(false);
      ACT = null;
      if (!quiet && opener && document.contains(opener)) opener.focus();
    }
    function esc(e) { if (e.key === "Escape" && ACT && ACT.el === box) { e.preventDefault(); close(); } }
    shut.addEventListener("click", function () { close(); });
    scrim.addEventListener("click", function () { close(); });
    document.addEventListener("keydown", esc, true);
    document.body.appendChild(scrim);
    document.body.appendChild(box);
    document.body.classList.add("hvb-actp-open");
    ACT = { key: key, el: box, opener: opener, close: close };
    setOpener(true);
    requestAnimationFrame(function () { shut.focus({ preventScroll: true }); });
    var q = (B.noun === "selection" ? "s=" : "t=") + encodeURIComponent(it.key);
    call("GET", "/api/board/activity?" + q).then(function (r) {
      if (!ACT || ACT.el !== box) return;
      body.textContent = "";
      body.removeAttribute("aria-busy");
      var items = (r.b && r.b.ok && r.b.items) || null;
      if (!items) {
        body.appendChild(h("p", { class: "hvb-actp__state is-bad", role: "status" },
          r.s === 401 ? "Sign in again to see the history." : "Couldn’t load the history. Close this and try again."));
        return;
      }
      if (!items.length) {
        body.appendChild(h("p", { class: "hvb-actp__state" }, "Nothing has changed here yet. Every move and edit will be listed here, newest first."));
        return;
      }
      body.appendChild(h("p", { class: "hvb-actp__count" }, items.length + (items.length === 1 ? " change" : " changes") + (items.length >= 200 ? " (the latest 200)" : "")));
      var day = null, ol = null;
      items.forEach(function (a) {
        var d = dayOf(a.at);
        if (d !== day) {
          day = d;
          body.appendChild(h("h3", { class: "hvb-actp__day" }, d));
          ol = h("ol", { class: "hvb-actp__list" });
          body.appendChild(ol);
        }
        ol.appendChild(h("li", null,
          h("time", { datetime: new Date(a.at * 1000).toISOString(), title: ago(a.at) }, clock(a.at)),
          h("span", { class: "hvb-actp__w" }, a.what), h("small", null, a.who)));
      });
    });
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
    }
    // (Item 214: no grip in the top row any more; a movable card shows the grab cursor and lifts on hover.)
    // Item 219: the card's history lives in its own floating panel, one tap away.
    var actOn = ACT && ACT.key === B.noun + ":" + it.key;
    var actB = h("button", { type: "button", class: "hvb-actb" + (actOn ? " is-on" : ""), "aria-label": "Activity: " + it.name, title: "Activity",
                             "aria-haspopup": "dialog", "aria-expanded": actOn ? "true" : "false", "aria-controls": "hvb-actp" }, svg("history"));
    actB.addEventListener("click", function () { activityPanel(it, B, actB); });
    // Item 214: the top row is the logos and the arrow only, so HelloVoice × the client's logo always has room.
    // Pin and Activity sit at the end of the button row instead.
    var tools = h("span", { class: "hvb-card__tools" }, pin || null, actB);
    top.appendChild(tog);
    el.appendChild(top);
    el.appendChild(h("h3", { class: "hvb-card__name" }, it.href ? h("a", { href: it.href }, it.name) : it.name));
    // The one-line summary a collapsed card keeps: on-track colour or Live mark, the key number, the client.
    el.appendChild(h("p", { class: "hvb-card__sum" },
      it.next && it.next.overdue ? h("span", { class: "hvb-due is-late" }, "Overdue") : null,
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
    if (it.next) put(nextLine(it.next));
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
    var go = goButtons(it, B);
    el.appendChild(h("div", { class: "hvb-card__go" }, go, tools));
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
    // Item 205: search and filters (this visit only): text, client, account manager, Mine, Pinned, Overdue.
    var F = { q: "", client: "", kam: "", chips: {} };
    try { F = JSON.parse(sessionStorage.getItem("hvb-filter-" + noun) || "null") || F; } catch (e) { /* blocked */ }
    F.chips = F.chips || {};
    function keepF() { try { sessionStorage.setItem("hvb-filter-" + noun, JSON.stringify(F)); } catch (e) { /* blocked */ } }
    function uniq(f) { var o = {}; items.forEach(function (x) { var v = f(x); if (v) o[v] = 1; }); return Object.keys(o).sort(); }
    var me = (opts.me || "").toLowerCase();
    function shown() {
      var q = (F.q || "").trim().toLowerCase();
      return items.filter(function (it) {
        if (q && (it.name + " " + (it.client || "") + " " + (it.kam || "")).toLowerCase().indexOf(q) < 0) return false;
        if (F.client && (it.client || "") !== F.client) return false;
        if (F.kam && (it.kam || "") !== F.kam) return false;
        if (F.chips.mine && !(it.kamEmail && it.kamEmail === me)) return false;
        if (F.chips.pinned && !it.pinned) return false;
        if (F.chips.overdue && !(it.next && it.next.overdue)) return false;
        return true;
      });
    }
    B.shown = shown;
    var search = h("input", { type: "search", class: "hvb-search__in", value: F.q || "", placeholder: "Search " + noun + "s, clients, KAMs",
                              "aria-label": "Search " + noun + "s" });
    var t0 = null;
    search.addEventListener("input", function () { clearTimeout(t0); t0 = setTimeout(function () { F.q = search.value; keepF(); redraw(); }, 160); });
    function picker(label, key, values) {
      if (values.length < 2) return null;
      var sel = h("select", { class: "hvb-filter", "aria-label": label },
        [h("option", { value: "" }, label)].concat(values.map(function (v) { return h("option", { value: v, selected: F[key] === v || null }, v); })));
      sel.addEventListener("change", function () { F[key] = sel.value; keepF(); redraw(); });
      return sel;
    }
    function chip(key, label, show) {
      if (!show) return null;
      var b = h("button", { type: "button", class: "hvb-chipf", "aria-pressed": F.chips[key] ? "true" : "false" }, label);
      b.addEventListener("click", function () {
        F.chips[key] = !F.chips[key]; if (!F.chips[key]) delete F.chips[key]; keepF();
        b.setAttribute("aria-pressed", F.chips[key] ? "true" : "false"); redraw();
      });
      return b;
    }
    var filters = h("div", { class: "hvb-filters" },
      h("label", { class: "hvb-search" }, svg("search"), search),
      picker("All clients", "client", uniq(function (x) { return x.client; })),
      picker("All account managers", "kam", uniq(function (x) { return x.kam; })),
      chip("mine", "Mine", !!me && items.some(function (x) { return x.kamEmail; })),
      chip("pinned", "Pinned", !!opts.onPin),
      chip("overdue", "Overdue", items.some(function (x) { return x.next && x.next.due; })));
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
      var head = h("header", { class: "hvb-lane__head" }, stageIcon(s.key, "hvb-stico--head"),
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
      var tab = h("button", { type: "button", role: "tab", class: "hvb-tab" + (s.key === "live" ? " hvb-tab--live" : "") + (ICON["st_" + s.key] ? " has-ico" : ""), "data-i": i, "aria-selected": i === 0 ? "true" : "false" },
        stageIcon(s.key, "hvb-stico--tab"), s.label, h("b", null, "0"));
      tab.addEventListener("click", function () { B.jump(i); });
      tabs[s.key] = tab;
      tabBar.appendChild(tab);
    });
    var bands = h("div", { class: "hvb-bands" });
    var tbl = h("div", { class: "hvb-table" });
    root.appendChild(status);
    root.appendChild(tools);
    root.appendChild(filters);
    root.appendChild(tabBar);
    // One scroller holds the stage heads and the client bands, so they slide sideways together.
    root.appendChild(h("div", { class: "hvb-scroll" }, grid, bands));
    root.appendChild(tbl);

    function draw() {
      Object.keys(lanes).forEach(function (k) { lanes[k].cards.textContent = ""; });
      var by = {};
      var list0 = shown();
      list0.forEach(function (it) { (by[it.stage] = by[it.stage] || []).push(it); });
      var cols = [];
      opts.stages.forEach(function (s) {
        var L = lanes[s.key], list = by[s.key] || [];
        list.forEach(function (it) { L.cards.appendChild(card(it, B)); });
        if (!list.length) L.cards.appendChild(h("p", { class: "hvb-empty" }, list0.length < items.length ? "None match" : "No " + noun + "s here"));
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
      shown().forEach(function (it) {
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
          // Item 221: each stage named, never colour alone: its mark, the count, a tooltip and screen-reader text.
          h("span", { class: "hvb-band__dots" }, opts.stages.map(function (s) {
            var n = c.items.filter(function (x) { return x.stage === s.key; }).length;
            return h("span", { class: "hvb-band__dot hvb-lane--" + s.key + (n ? " is-on" : ""), title: s.label + ": " + n },
              stageIcon(s.key, "hvb-stico--mini"), n ? h("b", { "aria-hidden": "true" }, String(n)) : null,
              h("span", { class: "hvb-sr" }, ", " + s.label + " " + n));
          })));
        var row = h("div", { class: "hvb-band__row" });
        opts.stages.forEach(function (s) {
          var mine = c.items.filter(function (x) { return x.stage === s.key; });
          var cell = h("div", { class: "hvb-cell hvb-lane--" + s.key + (mine.length ? "" : " is-empty") + (FOLD[s.key] && (byStage[s.key] || []).length ? " is-folded" : ""),
                                "data-drop": s.key, "data-stage": s.key },
            h("span", { class: "hvb-cell__k" }, stageIcon(s.key, "hvb-stico--mini"), s.label, mine.length ? h("b", null, String(mine.length)) : null));
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
            var wrap = h("span", { class: "hvb-t__stage hvb-lane--" + it.stage }, stageIcon(it.stage, "hvb-stico--mini") || h("i", { "aria-hidden": "true" }), lab);
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
      c.push({ k: "go", t: "", cell: function (it) { return h("span", { class: "hvb-card__go" }, goButtons(it, B)); } });
      return c;
    }
    function num(it, k) { var c = (it.raw && it.raw.counts) || {}; return c[k] || 0; }
    function table() {
      grid.hidden = tabBar.hidden = true;
      bands.textContent = "";
      tbl.textContent = "";
      var C = cols();
      var col = C.filter(function (c) { return c.k === SORT.k; })[0] || C[2];
      var rows = shown().sort(function (a, b) {
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
