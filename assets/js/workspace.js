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
    return m.state === "open" ? "Your role: " + m.role : m.state === "norole" ? "Not in your role" : m.state === "paused" ? "Paused" : "Not on your account";
  }

  /* -------------------------------------------------------------- locked */
  function lockedPage(m) {
    var norole = m.state === "norole";
    if (m.state === "paused") return h("div", { class: "ws-lockpage" }, m.logo ? h("img", { src: m.logo, alt: "" }) : null,
      h("h2", null, m.name + " is paused"), h("p", null, "HelloVoice paused it for your company. Your data is safe. Contact your account manager to switch it back on."));
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
      h("div", null, h("b", null, (m.unit === "$" ? "$" : "") + m.used.toLocaleString()),
        h("small", null, m.cap ? "of " + (m.unit === "$" ? "$" : "") + m.cap.toLocaleString() : "no limit")));
    if (pct !== null) {
      card.appendChild(h("div", { class: "ws-bar" + (pct >= 85 ? " is-hot" : ""), role: "img", "aria-label": pct + " percent used" }, h("i", { style: "width:" + pct + "%" })));
      if (pct >= 80) card.appendChild(requestMore(m.label, m.key));
    }
    return card;
  }
  function requestMore(label, key) {
    var b = h("button", { class: "ws-btn ws-btn--sm ws-btn--ghost", type: "button", onclick: function () {
      b.disabled = true;
      api("POST", "/api/workspace/request", { module: D.current, kind: "limit", limit: key || "", note: label }).then(function (r) { toast(r.b.message || "Sent."); });
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
    if (D.current === "helvi-track") return trackWork(p);
    if (D.current === "helvi-intelligence") return intelWork(p);
    var k = D.current, c = {
      "helvi-selection": ["Open the roster", "Browse creators, shortlist them and build a selection.", "../", "Open the roster"],
      "helvi-intelligence": ["Name a competitor", "Competitors you name are studied and filed here.", "../market/", "Open competitor evidence"]
    }[k];
    p.appendChild(h("div", { class: "ws-card" }, h("h2", null, c[0]), h("p", null, c[1]), h("a", { class: "ws-btn", href: c[2] }, c[3])));
  }

  /* ---------------------------------------------------- Track: campaigns */
  function readOnlyNote(p, what) {
    var b = h("button", { class: "ws-btn ws-btn--sm", type: "button", onclick: function () {
      b.disabled = true;
      api("POST", "/api/workspace/request", { module: D.current, kind: "module", level: "manage", note: "Manage our own " + what }).then(function (r) { toast(r.b.message || "Sent."); });
    } }, "Ask to manage your own");
    p.appendChild(h("div", { class: "ws-card ws-note" }, h("h2", null, "HelloVoice runs these for you"),
      h("p", null, "Your plan shows the " + what + " HelloVoice sets up. To create and run your own, ask for it."), b));
  }
  function field(label, el, help) {
    if (!el.id) el.id = "f" + Math.random().toString(36).slice(2, 8);
    return h("div", { class: "ws-field" }, h("label", { for: el.id }, label), el, help ? h("small", null, help) : null);
  }
  function campaignForm(c, plats, onSave, saveLabel) {
    var f = {
      name: h("input", { value: c.name || "", maxlength: "120" }),
      client: h("input", { value: c.client || "", maxlength: "120" }),
      platform: h("select"),
      starts: h("input", { type: "date", value: c.starts || "" }),
      ends: h("input", { type: "date", value: c.ends || "" }),
      hashtags: h("input", { value: c.hashtags || "", placeholder: "#launch #brand" }),
      mentions: h("input", { value: c.mentions || "", placeholder: "@brand" })
    };
    f.platform.appendChild(h("option", { value: "" }, "All platforms"));
    plats.forEach(function (x) { var o = h("option", { value: x }, x); if (x === c.platform) o.selected = true; f.platform.appendChild(o); });
    var go = h("button", { class: "ws-btn", type: "button", onclick: function () {
      var body = {}; Object.keys(f).forEach(function (k) { body[k] = f[k].value; });
      go.disabled = true; onSave(body).then(function () { go.disabled = false; });
    } }, saveLabel);
    return h("div", null, h("div", { class: "ws-invite" },
      field("Campaign name", f.name), field("Brand", f.client), field("Platform", f.platform),
      field("Starts", f.starts), field("Ends", f.ends),
      field("Hashtags", f.hashtags, "Posts carrying these count."), field("Mentions", f.mentions)), go);
  }
  function trackWork(p) {
    var canWrite = D.module.level === "manage" && (D.module.role === "editor" || D.module.role === "admin");
    if (D.module.level !== "manage") readOnlyNote(p, "campaigns");
    var box = h("div", { class: "ws-sec" }, h("p", { class: "ws-muted" }, "Loading your campaigns…"));
    p.appendChild(box);
    api("GET", "/api/my/campaigns").then(function (r) {
      box.textContent = "";
      if (!r.b.ok) { box.appendChild(h("div", { class: "ws-empty" }, h("b", null, "Campaigns are read-only on your plan"), r.b.message || "")); return; }
      var R = r.b;
      box.appendChild(h("div", { class: "ws-headrow" }, h("h2", null, "Your campaigns"),
        h("span", { class: "ws-pill" }, R.count + (R.cap ? " of " + R.cap : "") + (R.count === 1 && !R.cap ? " campaign" : " campaigns"))));
      if (canWrite) {
        var full = R.cap != null && R.count >= R.cap;
        var nc = h("details", { class: "ws-card ws-new", open: R.items.length ? false : "open" },
          h("summary", null, h("b", null, "New campaign")));
        if (full) nc.appendChild(h("p", null, "Your plan's campaigns are all in use. ", requestMore("Campaigns", "campaigns_max")));
        else nc.appendChild(campaignForm({}, R.platforms, function (body) {
          body.op = "create";
          return api("POST", "/api/my/campaign", body).then(function (x) { toast(x.b.message || "Done."); if (x.b.ok) draw(); });
        }, "Create campaign"));
        box.appendChild(nc);
      }
      if (!R.items.length) {
        box.appendChild(h("div", { class: "ws-empty" }, h("b", null, "No campaigns yet"),
          canWrite ? "Create your first campaign above: name it, set its dates, add creators and go live." : "Campaigns HelloVoice runs for you appear here."));
        return;
      }
      R.items.forEach(function (c) { box.appendChild(campaignCard(c, R, canWrite)); });
    });
  }
  function campaignCard(c, R, canWrite) {
    var card = h("article", { class: "ws-card ws-camp" });
    card.appendChild(h("div", { class: "ws-headrow" },
      h("div", null, h("h2", null, c.name), h("p", { class: "ws-muted" },
        [c.client, c.platform || "All platforms", c.starts && c.ends ? c.starts + " → " + c.ends : "No dates yet"].filter(Boolean).join(" · "))),
      h("span", { class: "ws-status ws-status--" + c.status }, c.status)));
    card.appendChild(h("p", null, c.creators.length + (c.creators.length === 1 ? " creator · " : " creators · ") + c.posts + (c.posts === 1 ? " post" : " posts")));
    var row = h("div", { class: "ws-row" }, h("a", { class: "ws-btn ws-btn--sm ws-btn--ghost", href: "../campaign/dashboard/?t=" + encodeURIComponent(c.t) }, "Open dashboard"));
    card.appendChild(row);
    if (!canWrite) return card;
    function act(op, label, cls) {
      var b = h("button", { class: "ws-btn ws-btn--sm" + (cls || ""), type: "button", onclick: function () {
        b.disabled = true;
        api("POST", "/api/my/campaign", { op: op, t: c.t }).then(function (x) { toast(x.b.message || "Done."); b.disabled = false; if (x.b.ok) draw(); });
      } }, label);
      return b;
    }
    if (c.status === "draft") row.appendChild(act("live", "Go live"));
    if (c.status === "live") row.appendChild(act("end", "End campaign", " ws-btn--ghost"));
    var edit = h("details", { class: "ws-more" }, h("summary", null, "Edit details"));
    edit.appendChild(campaignForm(c, R.platforms, function (body) {
      body.op = "edit"; body.t = c.t;
      return api("POST", "/api/my/campaign", body).then(function (x) { toast(x.b.message || "Saved."); if (x.b.ok) draw(); });
    }, "Save"));
    card.appendChild(edit);
    var cr = h("details", { class: "ws-more", open: c.creators.length ? false : "open" }, h("summary", null, "Creators (" + c.creators.length + ")"));
    if (c.creators.length) {
      var cl = h("ul", { class: "ws-list" });
      c.creators.forEach(function (x) {
        var rm = h("button", { class: "ws-btn ws-btn--sm ws-btn--ghost", type: "button", onclick: function () {
          api("POST", "/api/my/campaign", { op: "remove_creator", t: c.t, code: x.code }).then(function (r) { toast(r.b.message || ""); if (r.b.ok) draw(); });
        } }, "Remove");
        cl.appendChild(h("li", null, h("div", { class: "ws-who" }, h("b", null, x.name), h("span", null, x.platform + (x.handle ? " · @" + x.handle.replace(/^@/, "") : ""))), rm));
      });
      cr.appendChild(cl);
    }
    var links = h("textarea", { rows: "3", placeholder: "https://www.instagram.com/handle\nhttps://www.tiktok.com/@handle" });
    var addc = h("button", { class: "ws-btn", type: "button", onclick: function () {
      addc.disabled = true;
      api("POST", "/api/my/campaign", { op: "add_creators", t: c.t, links: links.value }).then(function (r) { toast(r.b.message || ""); addc.disabled = false; if (r.b.ok) draw(); });
    } }, "Add creators");
    cr.appendChild(field("Profile links, one a line", links, "They stay private to your company."));
    cr.appendChild(addc);
    card.appendChild(cr);
    var post = h("details", { class: "ws-more" }, h("summary", null, "Add a post"));
    if (!c.creators.length) post.appendChild(h("p", { class: "ws-muted" }, "Add a creator to this campaign first."));
    else {
      var who = h("select"); c.creators.forEach(function (x) { who.appendChild(h("option", { value: x.code }, x.name + (x.handle ? " (@" + x.handle.replace(/^@/, "") + ")" : ""))); });
      var url = h("input", { type: "url", placeholder: "https://www.instagram.com/p/…" });
      var add = h("button", { class: "ws-btn", type: "button", onclick: function () {
        add.disabled = true;
        api("POST", "/api/my/post", { t: c.t, code: who.value, url: url.value }).then(function (x) { toast(x.b.message || "Done."); add.disabled = false; if (x.b.ok) draw(); });
      } }, "Add post");
      post.appendChild(h("div", { class: "ws-invite" }, field("Creator", who), field("Post link", url)));
      post.appendChild(add);
    }
    card.appendChild(post);
    return card;
  }
  function results(p) {
    if (D.current === "helvi-intelligence") return intelResults(p);
    if (D.current === "helvi-selection") return selectionResults(p);
    p.appendChild(h("div", { class: "ws-sec" }, h("h2", null, "Results"), outputsList(D.overview.outputs, "No results yet", "Reports show up here as campaigns run.")));
  }
  function mod(key) { return D.modules.filter(function (m) { return m.key === key; })[0]; }
  function canEdit(m) { return m && m.state === "open" && m.level === "manage" && (m.role === "editor" || m.role === "admin"); }

  /* ------------------------------------- Selection: the Track hand-off */
  function selectionResults(p) {
    var outs = D.overview.outputs, track = mod("helvi-track");
    var sec = h("div", { class: "ws-sec" }, h("h2", null, "Your selections"));
    p.appendChild(sec);
    if (!outs.length) { sec.appendChild(h("div", { class: "ws-empty" }, h("b", null, "No selections yet"), "Build one from the roster; it shows up here.")); return; }
    var ul = h("ul", { class: "ws-list" });
    outs.forEach(function (o) {
      var btn;
      if (canEdit(track)) {
        btn = h("button", { class: "ws-btn ws-btn--sm", type: "button", onclick: function () {
          btn.disabled = true;
          api("POST", "/api/my/campaign", { op: "create", name: o.title, s: o.token }).then(function (r) {
            toast(r.b.message || "Done."); btn.disabled = false;
            if (r.b.ok) { tab = "work"; load("helvi-track"); history.replaceState(null, "", "#helvi-track"); }
          });
        } }, "Track this campaign");
      } else {
        btn = h("button", { class: "ws-btn ws-btn--sm ws-btn--ghost ws-locked", type: "button", title: "Available through Helvi Track", onclick: function () {
          btn.disabled = true;
          api("POST", "/api/workspace/request", { module: "helvi-track", kind: track && track.state === "norole" ? "role" : "module",
            note: "Track this campaign: " + o.title }).then(function (r) { toast(r.b.message || "Sent."); });
        } }, lockIcon(), "Track this campaign");
      }
      ul.appendChild(h("li", null, h("a", { href: o.href }, o.title), btn));
    });
    sec.appendChild(ul);
    if (!canEdit(track)) sec.appendChild(h("p", { class: "ws-muted" }, "Tracking a campaign is part of Helvi Track. The lock sends a request to HelloVoice."));
  }

  /* -------------------------------------- Intelligence: competitors, evidence */
  function intelWork(p) {
    var me = mod("helvi-intelligence");
    if (me.level !== "manage") { readOnlyNote(p, "competitor studies"); return; }
    if (!canEdit(me)) { p.appendChild(h("div", { class: "ws-empty" }, h("b", null, "Your role reads only"), "Ask your account admin for editor access to name competitors.")); return; }
    var box = h("div", { class: "ws-sec" }, h("p", { class: "ws-muted" }, "Loading your competitors…"));
    p.appendChild(box);
    api("GET", "/api/my/competitors").then(function (r) {
      box.textContent = "";
      if (!r.b.ok) { box.appendChild(h("div", { class: "ws-empty" }, h("b", null, "Not available"), r.b.message || "")); return; }
      var plats = r.b.platforms || ["Instagram", "TikTok"];
      box.appendChild(h("div", { class: "ws-headrow" }, h("h2", null, "Your competitors"), h("span", { class: "ws-pill" }, r.b.items.length + " of 40")));
      var f = { name: h("input", { maxlength: "80" }) }, hs = {};
      plats.forEach(function (pl) { hs[pl] = h("input", { placeholder: "@handle or link" }); });
      var grid = h("div", { class: "ws-invite" }, field("Competitor brand", f.name));
      plats.forEach(function (pl) { grid.appendChild(field(pl, hs[pl])); });
      var add = h("button", { class: "ws-btn", type: "button", onclick: function () {
        var handles = {}; plats.forEach(function (pl) { if (hs[pl].value.trim()) handles[pl] = hs[pl].value.trim(); });
        add.disabled = true;
        api("POST", "/api/my/competitor", { op: "add", name: f.name.value, handles: handles }).then(function (x) {
          toast(x.b.message || (x.b.ok ? "Added." : "Could not add.")); add.disabled = false; if (x.b.ok) draw();
        });
      } }, "Add competitor");
      box.appendChild(h("details", { class: "ws-card ws-new", open: r.b.items.length ? false : "open" }, h("summary", null, h("b", null, "Name a competitor")), grid, add));
      if (!r.b.items.length) { box.appendChild(h("div", { class: "ws-empty" }, h("b", null, "No competitors yet"), "Name one above, then collect: the creators they worked with land in Results.")); return; }
      var ul = h("ul", { class: "ws-list ws-card" });
      r.b.items.forEach(function (c) {
        var hl = Object.keys(c.handles || {}).map(function (k) { return k + " @" + String(c.handles[k]).replace(/^@/, ""); }).join(" · ");
        var run = h("button", { class: "ws-btn ws-btn--sm", type: "button", onclick: function () {
          run.disabled = true;
          api("POST", "/api/my/competitor/collect", { id: c.id }).then(function (x) { toast(x.b.message || "Done."); run.disabled = false; });
        } }, "Collect now");
        var rm = h("button", { class: "ws-btn ws-btn--sm ws-btn--ghost", type: "button", onclick: function () {
          if (!confirm("Remove " + c.name + "?")) return;
          api("POST", "/api/my/competitor", { op: "remove", id: c.id }).then(function (x) { toast(x.b.ok ? "Removed." : (x.b.message || "")); draw(); });
        } }, "Remove");
        ul.appendChild(h("li", null, h("div", { class: "ws-who" }, h("b", null, c.name), h("span", null, hl),
          h("span", null, c.last_run_at ? "Last collected " + new Date(c.last_run_at * 1000).toLocaleDateString() + (c.last_note ? " · " + c.last_note : "") : "Not collected yet")),
          h("span", { class: "ws-row" }, run, rm)));
      });
      box.appendChild(ul);
    });
  }
  function fmt(n) { return n == null ? "–" : n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? Math.round(n / 1e3) + "K" : String(n); }
  function intelResults(p) {
    var box = h("div", { class: "ws-sec" }, h("p", { class: "ws-muted" }, "Loading your evidence…"));
    p.appendChild(box);
    api("GET", "/api/my/evidence").then(function (r) {
      box.textContent = "";
      if (!r.b.ok) { box.appendChild(h("div", { class: "ws-empty" }, h("b", null, "Not available"), r.b.message || "")); return; }
      if (!r.b.packs.length) { box.appendChild(h("div", { class: "ws-empty" }, h("b", null, "No evidence yet"), "Name a competitor in Work and collect; what they posted with creators lands here.")); return; }
      r.b.packs.forEach(function (pk) {
        var tb = h("table", { class: "ws-table ws-table--cards" }, h("thead", null, h("tr", null, h("th", null, "Creator"), h("th", null, "Worked with"),
          h("th", null, "Posts"), h("th", null, "Best views"), h("th", null, "Followers"), h("th", null, "HelloVoice roster"))));
        var body = h("tbody");
        pk.creators.forEach(function (c) {
          var tag = null;
          if (c.on_roster) {
            if (r.b.selection_open && c.code) tag = h("a", { class: "ws-tag ws-tag--open", href: "../creator/?c=" + encodeURIComponent(c.code) }, "On the roster");
            else {
              tag = h("button", { class: "ws-tag ws-tag--locked", type: "button", title: "Available through Helvi Selection", onclick: function () {
                tag.disabled = true;
                api("POST", "/api/workspace/request", { module: "helvi-selection", kind: mod("helvi-selection").state === "norole" ? "role" : "module",
                  note: "Roster creator @" + c.handle }).then(function (x) { toast(x.b.message || "Sent."); });
              } }, lockIcon(), "Available through Helvi Selection");
            }
          }
          body.appendChild(h("tr", null, h("td", { class: "ws-who" }, h("b", null, c.name), h("span", null, c.platform + (c.handle ? " · @" + c.handle.replace(/^@/, "") : ""))),
            h("td", { "data-label": "Worked with" }, c.competitors.join(", ")), h("td", { "data-label": "Posts" }, String(c.posts)),
            h("td", { "data-label": "Best views" }, fmt(c.best_views)), h("td", { "data-label": "Followers" }, fmt(c.followers)),
            h("td", { "data-label": "Roster", class: "ws-td-tag" }, tag || h("span", { class: "ws-dash", "aria-label": "Not on the roster" }, "–"))));
        });
        tb.appendChild(body);
        box.appendChild(h("article", { class: "ws-card ws-pack" }, h("div", { class: "ws-headrow" }, h("h2", null, pk.title),
          h("span", { class: "ws-pill" }, pk.posts + " posts · " + pk.competitors.join(", "))), h("div", { class: "ws-scroll" }, tb),
          pk.more ? h("p", { class: "ws-muted" }, "+" + pk.more + " more creators") : null));
      });
    });
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
      h("p", null, used + (cap ? " of " + cap : "") + (used === 1 && !cap ? " seat" : " seats") + " used. Roles are set per module: none, viewer, editor or admin."));
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

    if (!T.invites) {
      p.appendChild(h("div", { class: "ws-card ws-note" }, h("h2", null, "Inviting colleagues opens soon"),
        h("p", null, "Until then your account manager can add colleagues to your account for you.")));
      return;
    }
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
    var track = D.current === "helvi-track";
    p.appendChild(h("div", { class: "ws-sec" }, h("h2", null, "Settings"), h("div", { class: "ws-card" },
      pref("Role given when you approve a request", "default_role", S.default_role, [["viewer", "Viewer"], ["editor", "Editor"]]),
      track ? pref("Weekly campaign update", "digest", S.digest, [["on", "On"], ["off", "Off"]],
                   "One bell and phone note a week per live campaign, for everyone on your account.") : null,
      text("Name on reports", "brand_name", S.brand_name, "Empty uses your account name."),
      text("Colour on reports", "brand_colour", S.brand_colour, "A hex colour such as #1b9b52."))));
    if (track && S.report && S.report.length) {
      var box = h("div", { class: "ws-card ws-switches" });
      S.report.forEach(function (r) {
        var cb = h("input", { type: "checkbox", id: "rs-" + r.key });
        cb.checked = r.value !== "off";
        cb.addEventListener("change", function () {
          api("POST", "/api/workspace/pref", { module: D.current, key: r.key, value: cb.checked ? "on" : "off" }).then(function (x) { toast(x.b.message); });
        });
        box.appendChild(h("label", { class: "ws-toggle", for: "rs-" + r.key }, cb, h("span", null, r.label)));
      });
      p.appendChild(h("div", { class: "ws-sec" }, h("h2", null, "What your reports show"),
        h("p", { class: "ws-muted" }, "Switched off here, a section is hidden on every campaign report of your account, including links you share."), box));
    }
  }

  var start = (location.hash || "").slice(1);
  load(start);
})();
