/* Edit mode on the campaign dashboard (item 209, slice c). For the HelloVoice team only: owners and admins edit any
 * campaign, a key account manager her own clients'. The server decides (GET /api/edit/campaign answers 403 / 404 for
 * anyone else), so for a client nothing here ever appears.
 *
 * An "Edit" button joins the header; it opens a side sheet: Content (each creator's posts: add a link, paste many, type
 * numbers, hide, delete, who is still to post) and Insights (approve or reject the numbers creators sent). Every
 * change saves at once and shows "Saved"; closing the sheet reloads the report once, if anything changed.
 * Everything from the server goes on the page with textContent, never HTML.
 *
 * Item 218 adds a Checks tab: posts flagged for disclosure, tags or claim wording (clients never see flags). A link
 * with #t=<token>&edit=checks opens the sheet on that tab.
 */
(function () {
  "use strict";
  var API = ((window.CAMPAIGN_CONFIG || {}).api != null ? window.CAMPAIGN_CONFIG.api : "/admin").replace(/\/$/, "");
  var D = null, TAB = "content", CHANGED = false, WRAP = null, SAY = null, OPEN_PASTE = false, TOKEN = "";
  var ICON = { ig: "Instagram", tt: "TikTok", sc: "Snapchat", yt: "YouTube" };
  var PIC = { Instagram: "ig", TikTok: "tt", Snapchat: "sc", YouTube: "yt" };
  var NUM = [["views", "Views"], ["likes", "Likes"], ["comments", "Comments"], ["shares", "Shares"], ["saves", "Saves"]];

  function $(id) { return document.getElementById(id); }
  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v == null || v === false) return;
      if (k === "class") el.className = v;
      else if (k.slice(0, 2) === "on" && typeof v === "function") el.addEventListener(k.slice(2), v);
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
  function icon(name, cls) {
    var hv = window.hvPortal;
    var s = h("span", { class: "dbe-ic" + (cls ? " " + cls : ""), "aria-hidden": "true" });
    s.innerHTML = hv && hv.icon ? hv.icon(name) : "";
    return s;
  }
  function token() { var m = /(?:^|[#&])t=([A-Za-z0-9_-]+)/.exec(location.hash || ""); return m ? m[1] : ""; }
  function api(method, path, body) {
    return fetch(API + path, { method: method, credentials: "include", cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (b) { return { s: r.status, b: b }; }); },
            function () { return { s: 0, b: {} }; });
  }
  function dayStr(ts) { return ts ? new Date(ts * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : ""; }
  function short(url) { return String(url || "").replace(/^https?:\/\/(www\.)?/, "").replace(/[?#].*$/, "").replace(/\/$/, ""); }
  function plural(n, one, many) { return n + " " + (n === 1 ? one : (many || one + "s")); }

  // The sheet is redrawn after every save, so the message is kept and shown again on the new bar.
  var LAST = null;
  function show() {
    if (!SAY || !LAST) return;
    SAY.textContent = LAST.text; SAY.className = "dbe-say" + (LAST.bad ? " dbe-say--bad" : " is-on");
  }
  function say(text, bad) {
    LAST = { text: text, bad: bad };
    show();
    clearTimeout(say.t); say.t = setTimeout(function () { LAST = null; if (SAY) SAY.className = "dbe-say"; }, 4500);
  }
  function load() {
    return api("GET", "/api/edit/campaign?t=" + encodeURIComponent(TOKEN)).then(function (r) {
      if (r.s === 200) { D = r.b; if (WRAP) paint(); return true; }
      return false;
    });
  }
  // One call, then re-read the campaign so the sheet shows what the server now holds.
  function act(path, body, ok) {
    body = body || {}; body.t = TOKEN;
    return api("POST", path, body).then(function (r) {
      if (r.s === 200 && r.b.ok) { CHANGED = true; say(r.b.message || "Saved."); return load().then(function () { if (ok) ok(r.b); return r.b; }); }
      say((r.b && r.b.message) || "That did not save. Try again.", true);
      return null;
    });
  }

  /* ------------------------------------------------------------------ sheet */
  function open() {
    if (WRAP) return;
    CHANGED = false;
    WRAP = h("div", { class: "dbe-wrap", role: "presentation" });
    document.body.appendChild(WRAP);
    document.body.classList.add("dbe-open");
    document.addEventListener("keydown", onKey);
    paint();
    var close = WRAP.querySelector(".dbe-x"); if (close) close.focus();
  }
  function onKey(e) { if (e.key === "Escape") closeSheet(); }
  function closeSheet() {
    if (!WRAP) return;
    document.removeEventListener("keydown", onKey);
    WRAP.remove(); WRAP = null; SAY = null; OPEN_PASTE = false;
    document.body.classList.remove("dbe-open");
    if (CHANGED) {                            // the report open in another tab redraws at once (2026-10-23)
      try { localStorage.setItem("hv_campaign_changed", TOKEN + "|" + Date.now()); } catch (e) {}
      location.reload();
    }
  }
  function toFix() {
    var n = 0;
    D.creators.forEach(function (c) { c.posts.forEach(function (p) { if (!p.hidden && p.views == null && p.likes == null) n++; }); });
    return n;
  }
  function paint() {
    var fix = toFix(), ni = D.insights.filter(function (i) { return i.status !== "approved"; }).length;
    var nf = flagCount();
    var tabs = h("div", { class: "dbe-tabs", role: "tablist", "aria-label": "Edit" });
    [["content", "Content", fix ? fix + " to fix" : null], ["insights", "Insights", ni ? String(ni) : null],
     ["checks", "Checks", nf ? nf + " flagged" : null]].forEach(function (t) {
      tabs.appendChild(h("button", { class: "dbe-tab", role: "tab", type: "button", "aria-selected": TAB === t[0] ? "true" : "false",
        onclick: function () { TAB = t[0]; paint(); } }, t[1], t[2] ? h("em", null, t[2]) : null));
    });
    SAY = h("span", { class: "dbe-say", role: "status" });
    var bar = h("div", { class: "dbe-bar" }, h("b", null, icon("pen"), "Edit mode"), h("span", null, "Team only. Clients see the report without these controls."), SAY,
      h("div", { class: "dbe-bar__go" },
        TAB === "content" ? h("button", { class: "dbe-btn dbe-btn--ghost", type: "button", onclick: function () { OPEN_PASTE = !OPEN_PASTE; paint(); } }, icon("link"), "Paste many links") : null,
        h("button", { class: "dbe-btn", type: "button", onclick: closeSheet }, "Done editing")));
    var body = TAB === "insights" ? insightsTab() : TAB === "checks" ? checksTab() : contentTab();
    var sheet = h("section", { class: "dbe-sheet", role: "dialog", "aria-modal": "true", "aria-label": "Edit " + D.campaign.name },
      h("div", { class: "dbe-hd" }, h("div", null, h("h2", null, D.campaign.name), h("p", null, "Fix the posts and numbers behind this report.")),
        h("button", { class: "dbe-x", type: "button", "aria-label": "Close edit mode", onclick: closeSheet }, icon("x"))),
      bar, tabs, body);
    var keep = WRAP.querySelector(".dbe-sheet"), top = keep ? keep.scrollTop : 0;
    WRAP.textContent = "";
    WRAP.appendChild(h("div", { class: "dbe-scrim", onclick: closeSheet }));
    WRAP.appendChild(sheet);
    sheet.scrollTop = top; show();
    var on = tabs.querySelector('[aria-selected="true"]');      // the chosen tab stays in sight on a phone
    if (on) tabs.scrollLeft = Math.max(0, on.offsetLeft - tabs.offsetLeft - 16);
  }

  /* ---------------------------------------------------------------- content */
  function contentTab() {
    var box = h("div", { class: "dbe-body" });
    if (OPEN_PASTE) box.appendChild(pasteForm());
    if (!D.creators.length) box.appendChild(h("p", { class: "dbe-none" }, "This campaign has no creators yet. Add them in the admin first."));
    D.creators.forEach(function (c) { box.appendChild(creatorCard(c)); });
    return box;
  }
  function pasteForm() {
    var sel = h("select", { class: "dbe-input", "aria-label": "Creator" });
    D.creators.forEach(function (c) { sel.appendChild(h("option", { value: c.code }, c.name + " (" + c.code + ")")); });
    var ta = h("textarea", { class: "dbe-input", rows: "4", placeholder: "One https:// link per line. The platform is read from each link.", "aria-label": "Post links" });
    var go = h("button", { class: "dbe-btn", type: "button" }, "Add the links");
    go.addEventListener("click", function () {
      go.disabled = true;
      act("/api/edit/bulk", { code: sel.value, text: ta.value }, function () { OPEN_PASTE = false; paint(); }).then(function () { go.disabled = false; });
    });
    return h("div", { class: "dbe-paste" }, h("label", null, h("span", null, "For"), sel), ta, go);
  }
  function creatorCard(c) {
    var posted = c.posts.filter(function (p) { return !p.hidden; }).length;
    var planned = c.platforms && c.platforms.length ? c.platforms.slice(0, 3).join(" · ") : "";
    var slots = h("span", { class: "dbe-slots", "aria-label": plural(posted, "post") + " posted" });
    for (var i = 0; i < Math.max(posted, c.planned || 0, 1); i++) slots.appendChild(h("i", { class: i < posted ? (c.planned && i >= c.planned ? "x" : "d") : "" }));
    var st = h("select", { class: "dbe-input dbe-input--sm", "aria-label": "Who is still to post: " + c.name });
    st.appendChild(h("option", { value: "" }, "Nothing pending"));
    D.statuses.forEach(function (s) { st.appendChild(h("option", { value: s }, s)); });
    st.value = c.pending_status || "";
    var dt = h("input", { class: "dbe-input dbe-input--sm", type: "date", value: c.pending_date || "", "aria-label": "Expected date" });
    function savePending() { act("/api/edit/pending", { code: c.code, status: st.value, date: dt.value }); }
    st.addEventListener("change", savePending); dt.addEventListener("change", savePending);
    var list = h("ul", { class: "dbe-posts" });
    c.posts.forEach(function (p) { list.appendChild(postRow(p)); });
    if (!c.posts.length) list.appendChild(h("li", { class: "dbe-none" }, "No posts yet."));
    var url = h("input", { class: "dbe-input", type: "url", placeholder: "Paste a post link. The platform is read from the link.", "aria-label": "Add a post link for " + c.name });
    var addB = h("button", { class: "dbe-btn", type: "button" }, icon("plus"), "Add post");
    function addPost() {
      if (!url.value.trim()) { url.focus(); return; }
      addB.disabled = true;
      act("/api/edit/post", { code: c.code, url: url.value.trim() }).then(function () { addB.disabled = false; });
    }
    addB.addEventListener("click", addPost);
    url.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); addPost(); } });
    return h("article", { class: "dbe-cr" },
      h("div", { class: "dbe-cr__hd" }, h("span", { class: "dbe-mono", "aria-hidden": "true" }, c.name.slice(0, 2).toUpperCase()),
        h("div", null, h("b", null, c.name), h("small", null, c.code + (planned ? " · on " + planned : "") + " · " + plural(posted, "post") + " posted")), slots),
      h("div", { class: "dbe-pending" }, h("span", null, "Still to post"), st, dt),
      list, h("div", { class: "dbe-add" }, url, addB));
  }
  function postRow(p) {
    var pic = PIC[p.platform];
    var inputs = {}, row = h("li", { class: "dbe-post" + (p.hidden ? " is-hidden" : "") + (p.views == null && p.likes == null ? " is-pending" : "") });
    var nums = h("div", { class: "dbe-nums" });
    NUM.forEach(function (n) {
      var inp = h("input", { class: "dbe-num", type: "text", inputmode: "numeric", value: p[n[0]] == null ? "" : String(p[n[0]]), placeholder: "Add", "aria-label": n[1] + " for " + short(p.url) });
      inp.addEventListener("input", function () { save.hidden = false; });
      inputs[n[0]] = inp;
      nums.appendChild(h("label", null, h("small", null, n[1]), inp));
    });
    var save = h("button", { class: "dbe-btn dbe-btn--sm", type: "button", hidden: "" }, "Save numbers");
    save.addEventListener("click", function () {
      var body = { post: p.id }; NUM.forEach(function (n) { body[n[0]] = inputs[n[0]].value; });
      save.disabled = true; act("/api/edit/numbers", body).then(function () { save.disabled = false; });
    });
    var more = h("div", { class: "dbe-more" });
    function ask() {
      more.textContent = "";
      var yes = h("button", { class: "dbe-btn dbe-btn--sm dbe-btn--danger", type: "button", onclick: function () { act("/api/edit/update", { post: p.id, do: "delete" }); } }, "Delete it");
      var no = h("button", { class: "dbe-link", type: "button", onclick: function () { drawMore(); } }, "Keep");
      more.appendChild(h("span", { class: "dbe-ask" }, "Delete this post and its numbers?"));
      more.appendChild(yes); more.appendChild(no);
    }
    function drawMore() {
      more.textContent = "";
      more.appendChild(h("button", { class: "dbe-link", type: "button", onclick: function () { act("/api/edit/update", { post: p.id, do: p.hidden ? "unhide" : "hide" }); } }, p.hidden ? "Show again" : "Hide"));
      more.appendChild(h("button", { class: "dbe-link dbe-link--danger", type: "button", onclick: ask }, "Delete"));
    }
    drawMore();
    add(row, [h("span", { class: "dbe-plat", title: p.platform }, pic ? icon(pic) : icon("link")),
      h("div", { class: "dbe-post__link" }, h("a", { href: p.url, target: "_blank", rel: "noopener" }, short(p.url)), checkPill(p.check),
        h("small", null, [p.platform, p.kind !== "post" ? p.kind : "", p.posted_at ? "posted " + dayStr(p.posted_at) : "", p.hidden ? "hidden from the report" : (p.views == null && p.likes == null ? "numbers missing" : "numbers " + (p.source === "manual" ? "typed" : "captured"))].filter(Boolean).join(" · "))),
      nums, save, more]);
    return row;
  }

  /* --------------------------------------------------------------- insights */
  function insightsTab() {
    var box = h("div", { class: "dbe-body" });
    var list = D.insights;
    if (!list.length) { box.appendChild(h("p", { class: "dbe-none" }, "No insights from creators yet. When a creator sends a screenshot of their insights, it shows here to approve.")); return box; }
    list.forEach(function (i) {
      var posts = [];
      D.creators.forEach(function (c) { if (c.code === i.code) posts = c.posts; });
      var sel = h("select", { class: "dbe-input dbe-input--sm", "aria-label": "Which post" });
      sel.appendChild(h("option", { value: "" }, "Choose the post"));
      posts.forEach(function (p) { sel.appendChild(h("option", { value: p.id }, p.platform + " · " + short(p.url))); });
      if (i.content_id) sel.value = String(i.content_id);
      var vals = {}, fields = h("div", { class: "dbe-nums" });
      D.insight_fields.forEach(function (f) {
        var inp = h("input", { class: "dbe-num", type: "text", inputmode: "numeric", value: i.values && i.values[f] != null ? String(i.values[f]) : "", placeholder: "—", "aria-label": f.replace(/_/g, " ") });
        vals[f] = inp; fields.appendChild(h("label", null, h("small", null, f.replace(/_/g, " ")), inp));
      });
      var ok = h("button", { class: "dbe-btn dbe-btn--sm", type: "button" }, i.status === "approved" ? "Update numbers" : "Use these numbers");
      ok.addEventListener("click", function () {
        var body = { id: i.id, do: "approve", post: sel.value || null, values: {} };
        Object.keys(vals).forEach(function (f) { body.values[f] = vals[f].value; });
        ok.disabled = true; act("/api/edit/insight", body).then(function () { ok.disabled = false; });
      });
      var no = h("button", { class: "dbe-btn dbe-btn--sm dbe-btn--ghost", type: "button", onclick: function () { act("/api/edit/insight", { id: i.id, do: "reject" }); } }, "Reject");
      box.appendChild(h("article", { class: "dbe-ins" },
        h("div", { class: "dbe-ins__hd" }, icon("scan"), h("div", null, h("b", null, i.name + " sent insights"),
          h("small", null, (i.status === "approved" ? "Approved" : "Waiting for review") + (i.uploaded_at ? " · " + dayStr(i.uploaded_at) : "") + (i.note ? " · " + i.note : "")))),
        h("label", { class: "dbe-ins__post" }, h("span", null, "Belongs to"), sel), fields, h("div", { class: "dbe-ins__go" }, ok, i.status === "approved" ? null : no)));
    });
    return box;
  }

  /* ----------------------------------------------------------- checks (218) */
  var CHECK_WORD = { fail: "Needs a look", warn: "Worth a glance", ok: "Marked OK", pass: "Passes", none: "Nothing to read" };
  function flagCount() {
    var n = 0;
    D.creators.forEach(function (c) { c.posts.forEach(function (p) { if (!p.hidden && p.check && p.check.status === "fail") n++; }); });
    return n;
  }
  function checkPill(c) {
    if (!c || c.status === "pass") return null;
    return h("button", { class: "dbe-chk dbe-chk--" + c.status, type: "button", title: (c.reasons[0] || {}).text || "",
      onclick: function () { TAB = "checks"; paint(); } }, CHECK_WORD[c.status] || c.status);
  }
  function checksTab() {
    var box = h("div", { class: "dbe-body" });
    var groups = { fail: [], warn: [], ok: [] }, fine = 0, unread = 0, blank = 0;
    D.creators.forEach(function (c) {
      c.posts.forEach(function (p) {
        if (p.hidden) return;
        var st = p.check ? p.check.status : null;
        if (st && groups[st]) groups[st].push({ c: c, p: p });
        else if (st === "pass") fine++;
        else if (st === "none") blank++;
        else unread++;
      });
    });
    var ai = D.checks_on || {};
    box.appendChild(h("div", { class: "dbe-tally", role: "status" },
      h("span", { class: "dbe-tally__n dbe-tally__n--fail" }, h("b", null, String(groups.fail.length)), "need a look"),
      h("span", { class: "dbe-tally__n dbe-tally__n--warn" }, h("b", null, String(groups.warn.length)), "worth a glance"),
      h("span", { class: "dbe-tally__n dbe-tally__n--pass" }, h("b", null, String(fine)), "pass"),
      h("p", { class: "dbe-tally__note" }, icon("shield"),
        "Disclosure and required tags are checked on every post. " + (ai.ai ? "Helvi also reads each caption for claim wording."
          : "Claim wording is not being read (" + (ai.why_not || "switched off") + "). An admin turns it on in Admin, Client portal, Settings & keys, Team AI.")
        + (blank ? " " + plural(blank, "post") + " had no caption or on-screen text to read." : "")
        + (unread ? " " + plural(unread, "post") + " still to check; checks run every 10 minutes." : ""))));
    if (!groups.fail.length && !groups.warn.length && !groups.ok.length) {
      box.appendChild(h("p", { class: "dbe-none" }, "No flags. Every checked post passes."));
      return box;
    }
    [["fail", "Needs a look"], ["warn", "Worth a glance"], ["ok", "Marked OK"]].forEach(function (g) {
      if (!groups[g[0]].length) return;
      box.appendChild(h("h3", { class: "dbe-h3" }, g[1], h("em", null, String(groups[g[0]].length))));
      var list = h("ul", { class: "dbe-flags" });
      groups[g[0]].forEach(function (x) { list.appendChild(flagRow(x.c, x.p, g[0])); });
      box.appendChild(list);
    });
    return box;
  }
  function flagRow(c, p, st) {
    var pic = PIC[p.platform];
    var reasons = h("ul", { class: "dbe-why" });
    (p.check.reasons || []).forEach(function (r) {
      reasons.appendChild(h("li", { class: "dbe-why--" + (r.level || "warn") }, r.text));
    });
    var go = h("div", { class: "dbe-flag__go" });
    if (st === "ok") {
      go.appendChild(h("span", { class: "dbe-flag__by" }, "OK'd by " + (p.check.cleared_by || "the team") + (p.check.cleared_at ? " · " + dayStr(p.check.cleared_at) : "")));
      go.appendChild(h("button", { class: "dbe-link", type: "button", onclick: function () { act("/api/edit/check", { post: p.id, do: "undo" }); } }, "Flag again"));
    } else {
      go.appendChild(h("button", { class: "dbe-btn dbe-btn--sm", type: "button", onclick: function () { act("/api/edit/check", { post: p.id, do: "clear" }); } }, icon("check"), "OK as is"));
      go.appendChild(h("button", { class: "dbe-btn dbe-btn--sm dbe-btn--ghost", type: "button", onclick: function () { act("/api/edit/check", { post: p.id, do: "recheck" }); } }, icon("redo"), "Check again"));
    }
    return h("li", { class: "dbe-flag dbe-flag--" + st },
      h("span", { class: "dbe-plat", title: p.platform }, pic ? icon(pic) : icon("link")),
      h("div", { class: "dbe-flag__main" },
        h("div", { class: "dbe-flag__hd" }, h("b", null, c.name), h("a", { href: p.url, target: "_blank", rel: "noopener" }, short(p.url))),
        reasons, go));
  }

  /* ------------------------------------------------------------------- boot */
  function mount() {
    var host = document.querySelector(".db-head__actions");
    if (!host || $("dbe-open")) return;
    var b = h("button", { class: "db-btn db-btn--lime", id: "dbe-open", type: "button" }, "Edit");
    b.addEventListener("click", function () { load().then(function (ok) { if (ok) open(); }); });
    host.insertBefore(b, host.firstChild);
  }
  function wanted() { var m = /[#&]edit=(checks|insights|content)/.exec(location.hash || ""); return m ? m[1] : null; }
  function start() {
    TOKEN = token();
    if (!TOKEN) return;
    api("GET", "/api/edit/campaign?t=" + encodeURIComponent(TOKEN)).then(function (r) {
      if (r.s !== 200) return;
      D = r.b; mount();
      var w = wanted();                       // a "Needs you" or bell link: open straight on that tab
      if (w) { TAB = w; open(); }
    });
  }
  // The report draws after the campaign loads; the header is there once #cat-app is shown.
  var app = $("cat-app");
  if (app && app.hidden) {
    var mo = new MutationObserver(function () { if (!app.hidden) { mo.disconnect(); start(); } });
    mo.observe(app, { attributes: true, attributeFilter: ["hidden"] });
  } else start();
})();
