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

  function count(n, one, many) { return n + " " + (n === 1 ? one : many); }

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
      if (r.s === 403) { if (!(r.b && r.b.code)) closed("Selections are for signed-in clients", "Sign in with your work email to see every selection on one board."); else $("mb-loading").hidden = true; return; }
      if (!r.b.ok) { closed("Something went wrong", "Your selections couldn't be loaded. Please try again shortly."); return; }
      var list = r.b.selections || [];
      var studies = list.filter(function (s) { return s.study; }).length;
      var live = list.filter(function (s) { return (s.campaigns || []).some(function (c) { return c.live; }); }).length;
      $("mb-sum").textContent = list.length
        ? [count(list.length, "selection", "selections"), count(live, "with a live campaign", "with a live campaign"), count(studies, "with a competitor study", "with a competitor study")].join(" · ")
        : "";
      $("mb-loading").hidden = true;
      $("mb-board").hidden = false;
      if (!list.length) { closed("No selections yet", "Shortlist creators on the catalogue and your selections will gather here."); return; }
      draw();
      function draw() {
        var view = HVBoard.viewOf("selections");
        HVBoard.mount($("mb-host"), {
          stages: SEL_STAGES, noun: "selection", locked: ["live", "completed"], view: view,
          tools: HVBoard.viewSwitch("selections", view, function () { draw(); }),
          items: list.map(function (s) { return HVBoard.fromSelection(s, chip(s.quote)); }),
          say: say,
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
      if (r.s === 403) { $("mb-loading").hidden = true; return; }      // the locked page (app.js) takes over
      if (!r.b.ok) { closed("Something went wrong", "The studies couldn't be loaded. Please try again shortly."); return; }
      var B = r.b, list = B.studies || [];
      var shared = list.filter(function (s) { return s.stage === "shared"; }).length;
      var posts = list.reduce(function (a, s) { return a + (s.posts || 0); }, 0);
      $("mb-sum").textContent = list.length
        ? [count(list.length, "study", "studies"), count(posts, "competitor post read", "competitor posts read"), count(shared, "shared with the client", "shared with clients")].join(" · ")
        : "";
      $("mb-lede").textContent = B.role === "admin"
        ? "Every competitor study, from the request to the client link. A card opens the study; its selection and campaigns are one tap away. Drag a card to correct its stage."
        : B.role === "client"
          ? "Who your competitors work with, study by study. Open one to see the creators behind their posts, then jump to your selection or campaign."
          : "Your clients' competitor studies, by stage. A card opens the study; its selection and campaigns are one tap away.";
      $("mb-loading").hidden = true;
      $("mb-board").hidden = false;
      if (!list.length) { closed("No competitor studies yet", "When HelloVoice studies your competitors' creators, each study appears here, tied to its selection."); return; }
      draw();
      function draw() {
        var view = HVBoard.viewOf("intelligence", ["board", "table"]);
        HVBoard.mount($("mb-host"), {
          stages: B.stages, noun: "study", locked: B.can_move ? [] : B.stages.map(function (s) { return s.key; }), view: view,
          tools: HVBoard.viewSwitch("intelligence", view, function () { draw(); }, ["board", "table"]),
          items: list.map(HVBoard.fromStudy), me: B.me || "",
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
  (KIND === "intelligence" ? intelligence : selections)();
})();
