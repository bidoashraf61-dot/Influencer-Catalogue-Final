/* HELVi Connect workspace (/workspace/): module switcher, Overview / Work / Results / Team / Settings.
   Everything is drawn from /api/workspace; text is always set as text, never as markup. */
(function () {
  "use strict";
  var API = (window.CATALOGUE_CONFIG && window.CATALOGUE_CONFIG.api) || "";
  var TABS = [["overview", "Overview"], ["work", "Work"], ["results", "Results"], ["team", "Team"], ["settings", "Settings"]];
  var D = null, tab = "overview";

  function $(id) { return document.getElementById(id); }
  function h(tag, attrs) {
    var el = document.createElement(tag), i, c;
    for (var k in (attrs || {})) {
      if (k === "class") el.className = attrs[k];
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] !== false && attrs[k] != null) el.setAttribute(k, attrs[k]);
    }
    for (i = 2; i < arguments.length; i++) {
      c = arguments[i];
      if (c == null || c === false) continue;
      el.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
    }
    return el;
  }
  function api(method, path, body) {
    return fetch(API + path, { method: method, credentials: "include", cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { s: r.status, b: b }; }); },
            function () { return { s: 0, b: {} }; });
  }
  var tt;
  function toast(msg) {
    var t = $("hc-toast"); t.textContent = msg; t.hidden = false; clearTimeout(tt); tt = setTimeout(function () { t.hidden = true; }, 3800);
  }
  function closed(title, line) {
    $("ws-loading").hidden = true; $("ws").hidden = true;
    var c = $("ws-closed"); c.hidden = false; c.textContent = "";
    c.appendChild(h("h1", null, title)); c.appendChild(h("p", null, line));
  }
  var LOCK = '<svg class="ws-lock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/></svg>';
  function lockIcon() { var s = document.createElement("span"); s.innerHTML = LOCK; return s.firstChild; }

  function load(m) {
    return api("GET", "/api/workspace" + (m ? "?m=" + encodeURIComponent(m) : "")).then(function (r) {
      if (r.s === 401) return closed("Please sign in", "Sign in on the catalogue with your work email to open your workspace.");
      if (r.s === 403) return closed("Workspaces are for signed-in clients", "Sign in with your work email to open yours.");
      if (!r.b.ok) return closed("Something went wrong", "Your workspace could not be loaded. Please try again shortly.");
      D = r.b; $("ws-loading").hidden = true; $("ws-closed").hidden = true; $("ws").hidden = false;
      if (D.module.state !== "open" || (tab === "team" && !D.team && false)) tab = "overview";
      draw();
    });
  }

  function draw() {
    var sw = $("ws-switch"); sw.textContent = "";
    D.modules.forEach(function (m) {
      var mark = h("span", { class: "ws-mod__mark" }, m.logo ? h("img", { src: m.logo, alt: "" }) : m.short.charAt(0));
      var b = h("button", { class: "ws-mod", type: "button", "data-state": m.state, "aria-current": m.key === D.current ? "true" : "false",
        onclick: function () { tab = "overview"; load(m.key); history.replaceState(null, "", "#" + m.key); } },
        mark, h("span", { class: "ws-mod__t" }, h("b", null, m.name), h("span", null, stateLabel(m))));
      if (m.state !== "open") b.appendChild(lockIcon());
      sw.appendChild(b);
    });
    var cur = D.module, hd = $("ws-head"); hd.textContent = "";
    hd.appendChild(h("div", null, h("h1", null, cur.name), h("p", null, cur.what)));
    if (cur.state === "open") hd.appendChild(h("span", { class: "ws-role" }, "Your role: " + cur.role));
    var tabs = $("ws-tabs"); tabs.textContent = "";
    if (cur.state === "open") TABS.forEach(function (t) {
      tabs.appendChild(h("button", { class: "ws-tab", type: "button", role: "tab", "aria-selected": t[0] === tab ? "true" : "false",
        onclick: function () { tab = t[0]; draw(); } }, t[1]));
    });
    var p = $("ws-panel"); p.textContent = "";
    if (cur.state !== "open") return p.appendChild(lockedPage(cur));
    ({ overview: overview, work: work, results: results, team: team, settings: settings })[tab](p);
  }
  function stateLabel(m) {
    return m.state === "open" ? "Your role: " + m.role : m.state === "norole" ? "Not in your role" : "Not on your account";
  }

  /* -------------------------------------------------------------- locked */
  function lockedPage(m) {
    var norole = m.state === "norole";
    var btn = h("button", { class: "ws-btn", type: "button", onclick: function () {
      btn.disabled = true;
      api("POST", "/api/workspace/request", { module: m.key, kind: norole ? "role" : "module" }).then(function (r) {
        toast(r.b.message || "Sent."); btn.textContent = "Requested";
      });
    } }, norole ? "Request access" : "Request this module");
    return h("div", { class: "ws-lockpage" }, m.logo ? h("img", { src: m.logo, alt: "" }) : null,
      h("h2", null, m.name), h("p", null, m.what),
      h("p", null, norole ? "Your account does not include it. Ask your account admin for access."
                          : "It is not part of your account yet. HelloVoice will set it up with you."), btn);
  }

  /* ------------------------------------------------------------ overview */
  function meter(m) {
    var pct = m.cap ? Math.min(100, Math.round(m.used * 100 / m.cap)) : null;
    var card = h("div", { class: "ws-card ws-meter" }, h("span", { class: "ws-lab" }, m.label),
      h("div", null, h("b", null, m.used.toLocaleString()), h("small", null, m.cap ? "of " + m.cap.toLocaleString() : "no limit")));
    if (pct !== null) {
      card.appendChild(h("div", { class: "ws-bar" + (pct >= 85 ? " is-hot" : ""), role: "img", "aria-label": pct + " percent used" }, h("i", { style: "width:" + pct + "%" })));
      if (pct >= 80) card.appendChild(requestMore(m.label));
    }
    return card;
  }
  function requestMore(label) {
    var b = h("button", { class: "ws-btn ws-btn--sm ws-btn--ghost", type: "button", onclick: function () {
      b.disabled = true;
      api("POST", "/api/workspace/request", { module: D.current, kind: "limit", note: label }).then(function (r) { toast(r.b.message || "Sent."); });
    } }, "Request more");
    return b;
  }
  function outputsList(items, emptyTitle, emptyLine) {
    if (!items.length) return h("div", { class: "ws-empty" }, h("b", null, emptyTitle), emptyLine);
    var ul = h("ul", { class: "ws-list" });
    items.forEach(function (o) {
      ul.appendChild(h("li", null, o.href ? h("a", { href: o.href }, o.title) : h("b", null, o.title), h("span", null, o.sub)));
    });
    return ul;
  }
  function overview(p) {
    var o = D.overview, left = o.checklist.filter(function (c) { return !c.done; });
    if (left.length) {
      var ul = h("ul", { class: "ws-check" });
      o.checklist.forEach(function (c) { ul.appendChild(h("li", { class: c.done ? "is-done" : "" }, c.label)); });
      p.appendChild(h("div", { class: "ws-sec" }, h("h2", null, "Get set up"), ul));
    }
    var g = h("div", { class: "ws-grid" }); o.meters.forEach(function (m) { g.appendChild(meter(m)); });
    p.appendChild(h("div", { class: "ws-sec" }, h("h2", null, "Your plan"), g));
    p.appendChild(h("div", { class: "ws-sec" }, h("h2", null, "Latest"), outputsList(o.outputs, "Nothing here yet", "Your first result appears here.")));
  }

  /* -------------------------------------------------------- work, results */
  function work(p) {
    var k = D.current, c = {
      "helvi-selection": ["Open the roster", "Browse creators, shortlist them and build a selection.", "../", "Open the roster"],
      "helvi-track": ["Your campaigns", "Open a campaign to add posts, creators and tracking links.", "../campaign/dashboard/", "Open campaign tracking"],
      "helvi-intelligence": ["Name a competitor", "Competitors you name are studied and filed here.", "../market/", "Open competitor evidence"]
    }[k];
    p.appendChild(h("div", { class: "ws-card" }, h("h2", null, c[0]), h("p", null, c[1]), h("a", { class: "ws-btn", href: c[2] }, c[3])));
  }
  function results(p) {
    p.appendChild(h("div", { class: "ws-sec" }, h("h2", null, "Results"), outputsList(D.overview.outputs, "No results yet", "Reports and selections show up here as they are made.")));
  }

  /* ---------------------------------------------------------------- team */
  function team(p) {
    if (!D.team) {
      p.appendChild(h("div", { class: "ws-empty" }, h("b", null, "Only admins manage people"),
        "Ask your account admin to change roles or invite colleagues."));
      return;
    }
    var T = D.team, used = T.seats[0], cap = T.seats[1];
    var head = h("div", { class: "ws-sec" }, h("h2", null, "People"),
      h("p", null, used + (cap ? " of " + cap : "") + " seats used. Roles are set per module: none, viewer, editor or admin."));
    p.appendChild(head);

    if (T.pending.length) {
      var pl = h("ul", { class: "ws-list" });
      T.pending.forEach(function (r) {
        pl.appendChild(h("li", null, h("span", null, r.name + " asks for access to " + r.module.replace("helvi-", "Helvi ")),
          h("span", { class: "ws-row" },
            h("button", { class: "ws-btn ws-btn--sm", type: "button", onclick: function () { decide(r.id, true); } }, "Approve"),
            h("button", { class: "ws-btn ws-btn--sm ws-btn--ghost", type: "button", onclick: function () { decide(r.id, false); } }, "Decline"))));
      });
      p.appendChild(h("div", { class: "ws-sec" }, h("h2", null, "Waiting for you"), pl));
    }

    var tb = h("table", { class: "ws-table" }), tr = h("tr", null, h("th", null, "Person"));
    T.modules.forEach(function (m) { if (m.on) tr.appendChild(h("th", null, m.name)); });
    tr.appendChild(h("th", null, ""));
    tb.appendChild(h("thead", null, tr));
    var body = h("tbody");
    T.people.forEach(function (u) {
      var row = h("tr", null, h("td", { class: "ws-who" }, h("b", null, u.name || u.email), h("span", null, u.name ? u.email : ""),
        u.owner ? h("span", { class: "ws-pill" }, "Owner") : (u.status !== "active" ? h("span", { class: "ws-pill" }, u.status) : null)));
      T.modules.forEach(function (m) {
        if (!m.on) return;
        if (u.owner) return row.appendChild(h("td", null, "admin"));
        var sel = h("select", { "aria-label": "Role in " + m.name, onchange: function () {
          api("POST", "/api/workspace/role", { user: u.id, module: modKey(m.name), role: sel.value }).then(function (r) { toast(r.b.message || "Saved."); if (!r.b.ok) reload(); });
        } });
        T.roles.forEach(function (r) { var o = h("option", { value: r.key, title: r.help }, r.key); if (u.roles[modKey(m.name)] === r.key) o.selected = true; sel.appendChild(o); });
        row.appendChild(h("td", null, sel));
      });
      row.appendChild(h("td", null, u.owner || u.id === D.me.id ? "" : h("button", { class: "ws-btn ws-btn--sm ws-btn--ghost", type: "button", onclick: function () {
        if (confirm("Remove " + (u.name || u.email) + "? Their seat is freed.")) api("POST", "/api/workspace/remove", { user: u.id }).then(function (r) { toast(r.b.message); reload(); });
      } }, "Remove")));
      body.appendChild(row);
    });
    tb.appendChild(body);
    p.appendChild(h("div", { class: "ws-sec ws-scroll" }, tb));

    var f = { name: h("input", { id: "iv-n", autocomplete: "off" }), email: h("input", { id: "iv-e", type: "email", autocomplete: "off" }) }, rs = {};
    var fields = h("div", { class: "ws-invite" },
      h("div", { class: "ws-field" }, h("label", { for: "iv-n" }, "Name"), f.name),
      h("div", { class: "ws-field" }, h("label", { for: "iv-e" }, "Work email"), f.email));
    T.modules.forEach(function (m) {
      if (!m.on) return;
      var s = h("select", { id: "iv-" + m.key }); T.roles.forEach(function (r) {
        var o = h("option", { value: r.key }, r.key); if (r.key === (m.key === D.current ? "viewer" : "none")) o.selected = true; s.appendChild(o);
      });
      rs[m.key] = s; fields.appendChild(h("div", { class: "ws-field" }, h("label", { for: "iv-" + m.key }, m.name), s));
    });
    var go = h("button", { class: "ws-btn", type: "button", onclick: function () {
      var roles = {}; Object.keys(rs).forEach(function (k) { roles[k] = rs[k].value; });
      go.disabled = true;
      api("POST", "/api/workspace/invite", { name: f.name.value, email: f.email.value, roles: roles }).then(function (r) {
        toast(r.b.message || "Done."); go.disabled = false; if (r.b.ok) reload();
      });
    } }, "Send invite");
    p.appendChild(h("div", { class: "ws-card" }, h("h2", null, "Invite someone"), fields, go));
  }
  function modKey(name) { return { Selection: "helvi-selection", Track: "helvi-track", Intelligence: "helvi-intelligence" }[name]; }
  function decide(id, ok) { api("POST", "/api/workspace/decide", { id: id, approve: ok }).then(function (r) { toast(r.b.message); reload(); }); }
  function reload() { load(D.current); }

  /* ------------------------------------------------------------ settings */
  function settings(p) {
    var S = D.settings, admin = D.module.role === "admin";
    var lim = h("ul", { class: "ws-list" });
    D.limits.forEach(function (l) {
      lim.appendChild(h("li", null, h("span", null, l.label), h("b", null, l.value == null ? "No limit" : l.value.toLocaleString())));
    });
    p.appendChild(h("div", { class: "ws-sec" }, h("h2", null, "Your limits"),
      h("div", { class: "ws-card" }, lim, h("p", null, "Set by HelloVoice for your account. "), requestMore("Limits"))));
    if (!admin) return p.appendChild(h("p", null, "Only an admin of this module can change its settings."));
    function pref(label, key, val, opts, help) {
      var s = h("select", { id: "pf-" + key }); opts.forEach(function (o) { var e = h("option", { value: o[0] }, o[1]); if (o[0] === val) e.selected = true; s.appendChild(e); });
      s.addEventListener("change", function () { api("POST", "/api/workspace/pref", { module: D.current, key: key, value: s.value }).then(function (r) { toast(r.b.message); }); });
      return h("div", { class: "ws-field" }, h("label", { for: "pf-" + key }, label), s, help ? h("small", null, help) : null);
    }
    function text(label, key, val, help) {
      var i = h("input", { id: "pf-" + key, value: val || "" });
      i.addEventListener("change", function () { api("POST", "/api/workspace/pref", { module: D.current, key: key, value: i.value }).then(function (r) { toast(r.b.message); }); });
      return h("div", { class: "ws-field" }, h("label", { for: "pf-" + key }, label), i, help ? h("small", null, help) : null);
    }
    p.appendChild(h("div", { class: "ws-sec" }, h("h2", null, "Settings"), h("div", { class: "ws-card" },
      pref("Role given when you approve a request", "default_role", S.default_role, [["viewer", "Viewer"], ["editor", "Editor"]]),
      pref("Weekly digest email", "digest", S.digest, [["on", "On"], ["off", "Off"]]),
      text("Name on reports", "brand_name", S.brand_name, "Empty uses your account name."),
      text("Colour on reports", "brand_colour", S.brand_colour, "A hex colour such as #1b9b52."))));
  }

  var start = (location.hash || "").slice(1);
  load(start);
})();
