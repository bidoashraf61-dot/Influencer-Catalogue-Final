/* The module boards (items 312 + 313, owner 2026-11-03): one page per HELVi module, each a kanban drawn by
 * the shared board (assets/js/hv-board.js).
 *
 *   /selections/    <body data-board="selections">    every selection this person may open, from /api/account;
 *                                                     a card opens the selection and links its campaigns + study
 *   /intelligence/  <body data-board="intelligence">  every competitor study, from /api/evidence/board;
 *                                                     a card opens the study and links its selection + campaigns
 *
 * (Track's board is /campaign/, which predates these.) A module this company does not own answers 403
 * {code: locked}; the app's fetch watcher (assets/js/app.js) then draws the locked page with Request access.
 */
(function () {
  "use strict";

  var API = ((window.CATALOGUE_CONFIG || {}).api || "/admin").replace(/\/$/, "");
  var KIND = document.body.getAttribute("data-board");
  function $(id) { return document.getElementById(id); }

  function api(method, path, body) {
    return fetch(API + path, {
      method: method, credentials: "include", cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (b) { return { s: r.status, b: b }; });
    }, function () { return { s: 0, b: {} }; });
  }

  function closed(title, line) {
    $("mb-loading").hidden = true;
    var c = $("mb-closed");
    c.textContent = "";
    var b = document.createElement("b"); b.textContent = title;
    var p = document.createElement("p"); p.textContent = line;
    var a = document.createElement("a"); a.className = "hc-btn"; a.href = "../"; a.textContent = "Go to the catalogue";
    c.appendChild(b); c.appendChild(p); c.appendChild(a);
    c.hidden = false;
  }

  function say(text, bad) {
    var el = $("mb-say"); if (!el) return;
    el.textContent = text; el.className = "mb-say is-on" + (bad ? " is-bad" : "");
    clearTimeout(say.t); say.t = setTimeout(function () { el.className = "mb-say"; }, 6000);
  }


  // A module this person may not open: the locked page (access.js, through app.js's watcher) takes over. Should it not
  // appear (scripts blocked, an old cached app.js), the page still says why instead of standing empty.
  function refused(b) {
    $("mb-loading").hidden = true;
    setTimeout(function () {
      if (document.querySelector(".hva")) return;
      closed((b && b.name ? b.name : "This module") + " isn't open to you",
        b && b.code === "no_role" ? "Ask your account admin for a role in it." : "Ask HelloVoice to switch it on for your company.");
    }, 2000);
  }

  /* ---------------------------------------------------------- selections */
  var SEL_STAGES = [
    { key: "draft", label: "Draft", hint: "Named, no creators yet" },
    { key: "shortlisting", label: "Shortlisting", hint: "Creators being chosen" },
    { key: "review", label: "Client review", hint: "Being decided, quote asked" },
    { key: "approved", label: "Approved", hint: "Agreed, being set up" },
    { key: "live", label: "Live", hint: "Its campaign is running" },
    { key: "completed", label: "Completed", hint: "Its campaign has ended" }];

  function chip(q) {
    if (!q || !q.key) return null;
    var f = (window.hvPortal || {}).lifecycleChip;
    if (f) return f(q);
    var s = document.createElement("span"); s.className = "lc-chip lc-chip--" + q.key;
    var i = document.createElement("i"); i.setAttribute("aria-hidden", "true");
    s.appendChild(i); s.appendChild(document.createTextNode(q.label));
    return s;
  }

  function selections() {
    return api("GET", "/api/account").then(function (r) {
      if (r.s === 401) { closed("Please sign in", "Sign in on the catalogue to see your selections."); return; }
      if (r.s === 403) { if (!(r.b && r.b.code)) closed("Selections are for signed-in clients", "Sign in with your work email to see every selection on one board."); else refused(r.b); return; }
      if (!r.b.ok) { closed("Something went wrong", "Your selections couldn't be loaded. Please try again shortly."); return; }
      var list = r.b.selections || [];
      var isAdmin = !!(r.b.is_admin || r.b.admin || r.b.role === "admin");
      var studies = list.filter(function (s) { return s.study; }).length;
      var creators = list.reduce(function (n, s) { return n + ((s.counts || {}).creators || 0); }, 0);
      HVBoard.cover($("mb-cover"), {
        mod: "select", title: "Selections", stages: SEL_STAGES,
        lede: "Every creator selection, from the first draft to a live campaign. A card opens the selection; its campaigns and competitor study are one tap away.",
        stats: [[list.length, list.length === 1 ? "selection" : "selections"], [creators, "creators shortlisted"], [studies, studies === 1 ? "with a competitor study" : "with competitor studies"]],
        items: list
      });
      $("mb-loading").hidden = true;
      $("mb-board").hidden = false;
      if (!list.length) { closed("No selections yet", "Shortlist creators on the catalogue and your selections will gather here."); return; }
      draw();
      function draw() {
        var view = HVBoard.viewOf("selections", ["board", "table"]);
        $("mb-host").textContent = "";          // a switch replaces the board; it never stacks a second one under the first
        HVBoard.mount($("mb-host"), {
          stages: SEL_STAGES, noun: "selection", locked: ["live", "completed"], view: view,
          tools: HVBoard.viewSwitch("selections", view, function () { draw(); }, ["board", "table"]),
          items: list.map(function (s) { return HVBoard.fromSelection(s, chip(s.quote)); }),
          say: say,
          bulk: isAdmin ? { archive: function (picked) {
            return api("POST", "/api/board/selection-archive", { tokens: picked.map(function (x) { return x.key; }) }).then(function (x) { return x.b || {}; });
          } } : null,
          onMove: function (it, to) {
            return api("POST", "/api/board/selection-stage", { s: it.key, to: to }).then(function (x) {
              if (x.b && x.b.ok) {
                var s = list.filter(function (y) { return y.token === it.key; })[0];
                if (s) { s.stage = to; s.moves = it.moves.slice(); }
              }
              return x.b || {};
            });
          }
        });
      }
    });
  }

  /* -------------------------------------------------------- intelligence */
  function intelligence() {
    return api("GET", "/api/evidence/board").then(function (r) {
      if (r.s === 401) { closed("Please sign in", "Sign in on the catalogue to see your competitor studies."); return; }
      if (r.s === 403) { refused(r.b); return; }
      if (!r.b.ok) { closed("Something went wrong", "The studies couldn't be loaded. Please try again shortly."); return; }
      var B = r.b, list = B.studies || [];
      var posts = list.reduce(function (a, s) { return a + (s.posts || 0); }, 0);
      var found = list.reduce(function (a, s) { return a + (s.creators || 0); }, 0);
      HVBoard.cover($("mb-cover"), {
        mod: "intelligence", title: "Competitor studies", stages: B.stages, items: list,
        lede: B.role === "admin"
          ? "Every competitor study, from the request to the client link. A card opens the study; its selection and campaigns are one tap away. Drag a card to correct its stage."
          : B.role === "client"
            ? "Who your competitors work with, study by study. Open one to see the creators behind their posts, then jump to your selection or campaign."
            : "Your clients' competitor studies, by stage. A card opens the study; its selection and campaigns are one tap away.",
        stats: [[list.length, list.length === 1 ? "study" : "studies"], [posts, "competitor posts read"], [found, "creators found"]]
      });
      $("mb-loading").hidden = true;
      $("mb-board").hidden = false;
      if (!list.length) { closed("No competitor studies yet", "When HelloVoice studies your competitors' creators, each study appears here, tied to its selection."); return; }
      draw();
      function draw() {
        var view = HVBoard.viewOf("intelligence", ["board", "table"]);
        $("mb-host").textContent = "";
        HVBoard.mount($("mb-host"), {
          stages: B.stages, noun: "study", empty: { requested: "Nothing requested. Ask HelloVoice to study a competitor.", running: "No study is being captured." }, locked: B.can_move ? [] : B.stages.map(function (s) { return s.key; }), view: view,
          tools: HVBoard.viewSwitch("intelligence", view, function () { draw(); }, ["board", "table"]),
          items: list.map(HVBoard.fromStudy), me: B.me || "",
          extra: B.can_move ? function (it) {
            var st = list.filter(function (y) { return String(y.id) === it.key; })[0];
            if (!st || !st.selection || st.stage !== "ready") return null;
            var b = document.createElement("button");
            b.type = "button"; b.className = "hvb-tool hvb-linkbtn"; b.textContent = "Create client link";
            b.addEventListener("click", function () {
              b.disabled = true; b.textContent = "Making…";
              api("POST", "/api/report/shares", { kind: "study", ref: st.selection.token, label: "", days: 30 }).then(function (x) {
                var u = x.b && x.b.link && x.b.link.url;
                if (!u) { b.disabled = false; b.textContent = "Create client link"; say((x.b && x.b.message) || "Couldn’t make the link. Please try again.", true); return; }
                var done = function () { b.textContent = "Link copied · 30 days"; say("Client link made and copied. It opens " + st.title + " for 30 days.", false); };
                (navigator.clipboard ? navigator.clipboard.writeText(u) : Promise.reject()).then(done, function () { b.textContent = "Link made"; say("Client link: " + u, false); });
                st.stage = "shared"; it.stage = "shared";
              });
            });
            return b;
          } : null,
          say: say,
          onMove: function (it, to) {
            return api("POST", "/api/evidence/board/stage", { id: Number(it.key), to: to }).then(function (x) {
              if (x.b && x.b.ok) {
                var st = list.filter(function (y) { return String(y.id) === it.key; })[0];
                if (st) { st.stage = to; st.moves = B.stages.map(function (k) { return k.key; }).filter(function (k) { return k !== to; }); }
              }
              return x.b || {};
            });
          }
        });
      }
    });
  }

  if (!window.HVBoard) { closed("Something went wrong", "The board couldn't start. Please reload the page."); return; }
  // Start once the deferred scripts have run: app.js installs the fetch watcher that draws the locked page, and the
  // first request must pass through it (item 313 client audit: the member's page stood blank).
  function start() { (KIND === "intelligence" ? intelligence : selections)(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
