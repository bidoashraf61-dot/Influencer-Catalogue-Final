/* Client portal layer for the catalogue pages.
 *
 *  - Gate: email sign-in with a one-time code (company addresses only), then a
 *    one-time profile step. The old access-code form stays one click away.
 *    Success reloads the page; the page's own script then finds the session
 *    cookie and unlocks itself, so every page that has a gate works unchanged.
 *  - Dock: "Find creators" (AI brief), "Ask" (chat) and the account chip, shown
 *    once signed in.
 *  - Brief wizard: a few multiple-choice questions (or one sentence the AI turns
 *    into answers), then a scored shortlist saved as a real selection.
 *
 * Everything the user or the server sends is put on the page with textContent,
 * never as HTML. The API key lives on the server; this file holds no secrets.
 */
(function () {
  "use strict";

  var script = document.currentScript;
  var SRC = script && script.src ? script.src : "";
  var ROOT = SRC ? SRC.replace(/assets\/js\/portal\.js.*$/, "") : "./";
  var CFGS = window.CATALOGUE_CONFIG || window.CAMPAIGN_CONFIG || {};
  var API = (CFGS.api != null ? CFGS.api : "/admin").replace(/\/$/, "");
  var ME = null;
  var ICON = {
    spark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z"/></svg>',
    chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>',
    user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="3.6"/><path d="M5 20c.6-3.8 3.4-5.8 7-5.8s6.4 2 7 5.8"/></svg>'
  };

  /* --------------------------------------------------------------- helpers */

  function h(tag, props) {
    var node = document.createElement(tag);
    props = props || {};
    Object.keys(props).forEach(function (k) {
      var v = props[k];
      if (v == null || v === false) return;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k === "html") node.innerHTML = v;            // only ever our own static strings
      else if (k.slice(0, 2) === "on") node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null || c === false) continue;
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return node;
  }

  function $(id) { return document.getElementById(id); }
  function bg(node, url) { if (url) node.style.backgroundImage = 'url("' + String(url).replace(/"/g, "%22") + '")'; }

  function api(method, path, body) {
    var opts = { method: method, credentials: "include", headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(API + path, opts)
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (b) { return { s: r.status, b: b || {} }; });
      })
      .catch(function () { return { s: 0, b: { message: "Could not reach the server. Please try again." } }; });
  }

  function money(n) { return Math.round(n).toLocaleString("en-US"); }
  function price(p) { return p && p.length ? "SAR " + money(p[0]) + (p[1] && p[1] !== p[0] ? " – " + money(p[1]) : "") : "Price on request"; }
  function followers(n) { return n >= 1e6 ? (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M" : n >= 1e3 ? Math.round(n / 1e3) + "K" : String(n || 0); }
  function ago(ts) {
    var d = Math.max(0, Date.now() / 1000 - ts);
    return d < 3600 ? Math.max(1, Math.round(d / 60)) + " min ago" : d < 86400 ? Math.round(d / 3600) + " h ago" : Math.round(d / 86400) + " d ago";
  }

  var openLayers = [];
  function layer(node, drawer) {
    var scrim = drawer ? node : h("div", { class: "pt-scrim", role: "presentation" }, node);
    var prev = document.activeElement;
    function close() {
      scrim.remove();
      openLayers = openLayers.filter(function (l) { return l !== close; });
      if (!openLayers.length) document.body.classList.remove("pt-lock");
      document.removeEventListener("keydown", onKey);
      if (prev && prev.focus) prev.focus();
    }
    function onKey(e) { if (e.key === "Escape" && openLayers[openLayers.length - 1] === close) close(); }
    if (!drawer) scrim.addEventListener("mousedown", function (e) { if (e.target === scrim) close(); });
    document.addEventListener("keydown", onKey);
    document.body.appendChild(scrim);
    document.body.classList.add("pt-lock");
    openLayers.push(close);
    var focusable = scrim.querySelector("input, textarea, button.pt-opt, button.pt-btn, .pt-x");
    if (focusable) focusable.focus();
    return close;
  }

  function creditsLine(cost) {
    if (!ME || ME.credits == null) return "";
    return cost + " credit" + (cost === 1 ? "" : "s") + " · " + ME.credits + " left";
  }

  /* ------------------------------------------------------------------ gate */

  function enhanceGate() {
    var gate = $("cat-gate");
    if (!gate || gate.getAttribute("data-pt")) return;
    gate.setAttribute("data-pt", "1");
    var inner = gate.querySelector(".cat-gate__inner");
    if (!inner) return;
    var note = inner.querySelector(".cat-gate__note");
    var oldForm = inner.querySelector(".cat-gate__form");
    var oldErr = inner.querySelector(".cat-gate__error");

    var msg = h("p", { class: "pt-msg", role: "status", "aria-live": "polite" });
    function say(text, kind) { msg.textContent = text || ""; msg.className = "pt-msg" + (kind ? " is-" + kind : ""); }

    var email = h("input", { class: "pt-input", type: "email", name: "email", placeholder: "you@yourcompany.com", autocomplete: "email",
      "aria-label": "Work email", required: true, inputmode: "email", spellcheck: "false" });
    var emailBtn = h("button", { class: "cat-btn cat-btn--lime", type: "submit" }, "Email me a code");
    var formEmail = h("form", { class: "pt-form", novalidate: true }, email, emailBtn);

    var code = h("input", { class: "pt-input pt-input--code", type: "text", inputmode: "numeric", autocomplete: "one-time-code", maxlength: "6",
      placeholder: "000000", "aria-label": "6-digit code", pattern: "[0-9]*" });
    var codeBtn = h("button", { class: "cat-btn cat-btn--lime", type: "submit" }, "Verify and continue");
    var resend = h("button", { class: "pt-link", type: "button" }, "Send a new code");
    var other = h("button", { class: "pt-link", type: "button" }, "Use a different email");
    var formCode = h("form", { class: "pt-form", hidden: true }, code, codeBtn, h("div", null, resend, other));

    var pName = h("input", { class: "pt-input", name: "name", placeholder: "Your name", autocomplete: "name", required: true });
    var pCompany = h("input", { class: "pt-input", name: "company", placeholder: "Company", autocomplete: "organization", required: true });
    var pTitle = h("input", { class: "pt-input", name: "job_title", placeholder: "Job title (optional)", autocomplete: "organization-title" });
    var pPhone = h("input", { class: "pt-input", name: "phone", placeholder: "Phone (optional)", autocomplete: "tel", type: "tel" });
    var pBtn = h("button", { class: "cat-btn cat-btn--lime", type: "submit" }, "Create my account");
    var formProfile = h("form", { class: "pt-form", hidden: true }, pName, pCompany, h("div", { class: "pt-row" }, pTitle, pPhone), pBtn);

    var toCodeLink = h("button", { class: "pt-link", type: "button" }, "I have an access code instead");
    var panel = h("div", { class: "pt-gate" },
      h("p", { class: "pt-gate__lead" }, "Sign in with your work email. We'll send a one-time code. No password needed."),
      formEmail, formCode, formProfile, msg, h("div", { class: "pt-gate__alt" }, toCodeLink));

    inner.insertBefore(panel, note || oldForm);
    if (note) note.hidden = true;
    if (oldForm) oldForm.hidden = true;
    if (oldErr) oldErr.style.display = "none";
    var showingCode = false;
    toCodeLink.addEventListener("click", function () {
      showingCode = !showingCode;
      if (oldForm) oldForm.hidden = !showingCode;
      if (note) note.hidden = !showingCode;
      if (oldErr) oldErr.style.display = "";
      [formEmail, formCode, formProfile].forEach(function (f) { if (showingCode) f.hidden = true; });
      if (!showingCode) { formEmail.hidden = false; say(""); }
      toCodeLink.textContent = showingCode ? "Sign in with email instead" : "I have an access code instead";
      var first = (showingCode ? oldForm : email);
      var inp = first && first.querySelector ? (first.querySelector("input") || first) : first;
      if (inp && inp.focus) inp.focus();
    });

    var state = { email: "", ticket: "", timer: null };
    function busy(btn, on, label) {
      btn.disabled = on;
      btn.textContent = on ? "Please wait…" : label;
    }
    function countdown(secs) {
      clearInterval(state.timer);
      resend.disabled = true;
      var left = secs;
      resend.textContent = "Send a new code in " + left + "s";
      state.timer = setInterval(function () {
        left -= 1;
        if (left <= 0) { clearInterval(state.timer); resend.disabled = false; resend.textContent = "Send a new code"; }
        else resend.textContent = "Send a new code in " + left + "s";
      }, 1000);
    }
    function sendCode(fromResend) {
      say("");
      busy(emailBtn, true, "Email me a code");
      return api("POST", "/api/auth/start", { email: state.email }).then(function (r) {
        busy(emailBtn, false, "Email me a code");
        if (r.s === 429) { say("Too many requests. Please wait a few minutes.", "err"); return; }
        if (r.b.reason === "mail_not_configured") { say(r.b.message, "err"); toCodeLink.click(); return; }
        if (!r.b.ok) { say(r.b.message || "Couldn't send the code.", "err"); return; }
        formEmail.hidden = true; formCode.hidden = false; formProfile.hidden = true;
        say(r.b.sent === false ? "A code was sent a moment ago. Check your inbox." : "We sent a 6-digit code to " + state.email + ". It lasts " + (r.b.minutes || 10) + " minutes.", "ok");
        countdown(r.b.resend_in || r.b.wait || 30);
        code.value = ""; code.focus();
      });
    }
    formEmail.addEventListener("submit", function (e) {
      e.preventDefault();
      state.email = email.value.trim().toLowerCase();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(state.email)) { say("Enter a valid work email address.", "err"); return; }
      sendCode(false);
    });
    resend.addEventListener("click", function () { sendCode(true); });
    other.addEventListener("click", function () {
      clearInterval(state.timer); formCode.hidden = true; formEmail.hidden = false; say(""); email.focus();
    });
    code.addEventListener("input", function () {
      code.value = code.value.replace(/\D/g, "").slice(0, 6);
      if (code.value.length === 6) formCode.requestSubmit();
    });
    formCode.addEventListener("submit", function (e) {
      e.preventDefault();
      if (code.value.length !== 6) { say("Enter the 6-digit code.", "err"); return; }
      busy(codeBtn, true, "Verify and continue");
      api("POST", "/api/auth/verify", { email: state.email, otp: code.value }).then(function (r) {
        busy(codeBtn, false, "Verify and continue");
        if (r.s === 429) { say("Too many attempts. Please wait a few minutes.", "err"); return; }
        if (!r.b.ok) { say(r.b.message || "That code isn't right.", "err"); code.value = ""; code.focus(); return; }
        finish(r.b);
      });
    });
    function finish(b) {
      if (b.step === "profile") {
        state.ticket = b.ticket;
        formCode.hidden = true; formProfile.hidden = false;
        pCompany.value = b.suggested_company || ""; say("Email confirmed. Tell us who you are.", "ok"); pName.focus();
      } else if (b.step === "pending") {
        formCode.hidden = true; formProfile.hidden = true; say(b.message, "ok");
      } else if (b.step === "done") {
        say("Welcome. Opening the catalogue…", "ok"); location.reload();
      }
    }
    formProfile.addEventListener("submit", function (e) {
      e.preventDefault();
      busy(pBtn, true, "Create my account");
      api("POST", "/api/auth/profile", { ticket: state.ticket, name: pName.value, company: pCompany.value, job_title: pTitle.value, phone: pPhone.value })
        .then(function (r) {
          busy(pBtn, false, "Create my account");
          if (!r.b.ok) { say(r.b.message || "Couldn't create the account.", "err"); return; }
          finish(r.b);
        });
    });
  }

  /* ------------------------------------------------------------------ dock */

  function mountDock() {
    if (!ME || !ME.signed_in || $("pt-dock")) return;
    var cat = document.querySelector(".cat-topbar__links");
    var dock = h("div", { id: "pt-dock", class: "pt-dock" + (cat ? "" : " pt-dock--fixed") });
    if (ME.kind !== "guest" || ME.ai) {
      dock.appendChild(h("button", { class: "pt-chip pt-chip--lime", type: "button", html: ICON.spark + "<span>Find creators</span>", onclick: openWizard }));
    }
    if (ME.ai) dock.appendChild(h("button", { class: "pt-chip", type: "button", html: ICON.chat + "<span>Ask</span>", onclick: openChat }));
    var chip = h("button", { class: "pt-chip", type: "button", "aria-label": "My account", onclick: openAccount });
    chip.innerHTML = ICON.user;
    chip.appendChild(h("span", { id: "pt-chip-name" }, ME.user ? ME.user.name.split(" ")[0] : ME.kind === "admin" ? "Admin" : "Account"));
    if (ME.credits != null) chip.appendChild(h("span", { class: "pt-credits", id: "pt-chip-credits" }, ME.credits + " cr"));
    dock.appendChild(chip);
    if (cat) cat.insertBefore(dock, cat.firstChild); else document.body.appendChild(dock);
  }

  function setCredits(n) {
    if (n == null) return;
    ME.credits = n;
    var c = $("pt-chip-credits");
    if (c) c.textContent = n + " cr";
  }

  /* ---------------------------------------------------------- brief wizard */

  var QUESTIONS = null;
  function loadQuestions() {
    if (QUESTIONS) return Promise.resolve(QUESTIONS);
    return api("GET", "/api/brief/questions").then(function (r) { QUESTIONS = r.b.questions || []; return QUESTIONS; });
  }

  function openWizard() {
    loadQuestions().then(function (qs) { wizard(qs, {}, 0); });
  }

  var currentClose = null;
  function wizard(qs, answers, step, prefillNote) {
    if (currentClose) currentClose();
    var total = qs.length + 1;                        // questions + review
    var onReview = step >= qs.length;
    var title = h("h2", { class: "pt-title", id: "pt-wiz-title" }, onReview ? "Review your brief" : "Find creators");
    var modal = h("div", { class: "pt-modal", role: "dialog", "aria-modal": "true", "aria-labelledby": "pt-wiz-title" });
    var close;
    var x = h("button", { class: "pt-x", type: "button", "aria-label": "Close", onclick: function () { close(); } }, "×");
    modal.appendChild(h("div", { class: "pt-head" }, title, x));
    modal.appendChild(h("div", { class: "pt-progress" }, h("i", { style: "transform:scaleX(" + ((step + 1) / total).toFixed(3) + ")" })));
    var body = h("div", { class: "pt-body" });
    modal.appendChild(body);
    var err = h("div", { class: "pt-err", hidden: true, role: "alert" });

    function fail(text) { err.textContent = text; err.hidden = !text; }
    function go(n) { wizard(qs, answers, Math.max(0, Math.min(n, qs.length)), prefillNote); }

    if (!onReview) {
      var q = qs[step];
      if (step === 0) {
        // The one-sentence shortcut lives on the first screen only.
        var free = h("textarea", { class: "pt-text", placeholder: "e.g. We're launching a sunscreen in Riyadh and want 8 micro-creators on Instagram, budget around 100k SAR.", maxlength: "1500", "aria-label": "Describe your campaign" });
        var fillBtn = h("button", { class: "pt-btn pt-btn--ghost", type: "button" }, "Fill it in for me");
        var cost = ME && ME.costs ? ME.costs.parse : 1;
        if (ME && ME.ai) {
          body.appendChild(h("p", { class: "pt-sub" }, "Describe your campaign in a sentence and our AI will fill the questions. Or answer them yourself below."));
          body.appendChild(h("div", { style: "margin-top:14px" }, free));
          body.appendChild(h("div", { class: "pt-actions", style: "margin-top:12px" }, h("span", { class: "pt-note", style: "margin:0" }, creditsLine(cost)), fillBtn));
          body.appendChild(h("div", { class: "pt-or" }, "or answer a few questions"));
          fillBtn.addEventListener("click", function () {
            if (free.value.trim().length < 8) { fail("Describe the campaign in a sentence or two."); return; }
            fillBtn.disabled = true; fillBtn.textContent = "Reading your brief…";
            api("POST", "/api/brief/parse", { text: free.value }).then(function (r) {
              if (r.b.ok) { setCredits(r.b.credits); Object.keys(r.b.answers || {}).forEach(function (k) { answers[k] = r.b.answers[k]; }); wizard(qs, answers, qs.length, "We read your brief. Check it and change anything that's off."); }
              else { fillBtn.disabled = false; fillBtn.textContent = "Fill it in for me"; fail(r.b.message || "That didn't work. Please answer the questions instead."); }
            });
          });
        }
      }
      body.appendChild(h("p", { class: "pt-note", style: "margin-top:0" }, "Question " + (step + 1) + " of " + qs.length + (q.required ? "" : " · optional")));
      body.appendChild(h("h3", { class: "pt-q" }, q.label));
      if (q.type === "text") {
        var ta = h("textarea", { class: "pt-text", maxlength: String(q.max || 500), "aria-label": q.label, placeholder: "A city, a product name, a tone, anything that helps." }, answers[q.id] || "");
        ta.value = answers[q.id] || "";
        ta.addEventListener("input", function () { if (ta.value.trim()) answers[q.id] = ta.value.trim(); else delete answers[q.id]; });
        body.appendChild(ta);
      } else {
        var many = q.type === "many";
        var grid = h("div", { class: "pt-opts", role: many ? "group" : "radiogroup", "aria-label": q.label });
        q.options.forEach(function (o) {
          var cur = answers[q.id];
          var on = many ? (cur || []).indexOf(o.value) > -1 : cur === o.value;
          var btn = h("button", { class: "pt-opt", type: "button", "aria-pressed": on ? "true" : "false" }, h("span", { class: "pt-tick" }), o.label);
          btn.addEventListener("click", function () {
            if (many) {
              var list = answers[q.id] || [];
              var i = list.indexOf(o.value);
              if (o.value === "any") list = i > -1 ? [] : ["any"];
              else { list = list.filter(function (v) { return v !== "any"; }); if (i > -1) list.splice(list.indexOf(o.value), 1); else list.push(o.value); }
              if (list.length) answers[q.id] = list; else delete answers[q.id];
              Array.prototype.forEach.call(grid.children, function (b, bi) { b.setAttribute("aria-pressed", (answers[q.id] || []).indexOf(q.options[bi].value) > -1 ? "true" : "false"); });
            } else {
              answers[q.id] = o.value;
              setTimeout(function () { go(step + 1); }, 140);
            }
          });
          grid.appendChild(btn);
        });
        body.appendChild(grid);
      }
      body.appendChild(err);
      var back = h("button", { class: "pt-btn pt-btn--ghost", type: "button", onclick: function () { go(step - 1); } }, "Back");
      if (step === 0) back.style.visibility = "hidden";
      var next = h("button", { class: "pt-btn", type: "button" }, step === qs.length - 1 ? "Review" : q.required ? "Next" : "Next / skip");
      next.addEventListener("click", function () {
        if (q.required && !(answers[q.id] && answers[q.id].length)) { fail("Please choose an answer to continue."); return; }
        go(step + 1);
      });
      body.appendChild(h("div", { class: "pt-actions" }, back, next));
    } else {
      body.appendChild(h("p", { class: "pt-sub" }, prefillNote || "This is what we'll match creators against."));
      var list = h("ul", { class: "pt-review" });
      qs.forEach(function (q, i) {
        var v = answers[q.id];
        if (!v || (v.length === 0)) { if (!q.required) return; }
        var label = q.type === "text" ? (v || "") : (q.type === "many" ? (v || []) : [v]).map(function (val) {
          var o = q.options.filter(function (op) { return op.value === val; })[0]; return o ? o.label : val;
        }).join(", ");
        list.appendChild(h("li", null, h("span", null, q.label.replace(/\?$/, "")), h("span", null, h("b", null, label || "Not answered"), " ",
          h("button", { type: "button", onclick: function () { go(i); } }, "change"))));
      });
      body.appendChild(list);
      body.appendChild(err);
      var missing = qs.filter(function (q) { return q.required && !(answers[q.id] && answers[q.id].length); });
      var cost = ME && ME.costs ? ME.costs.brief : 5;
      var run = h("button", { class: "pt-btn pt-btn--lime", type: "button" }, "Show my creators");
      body.appendChild(h("div", { class: "pt-actions" }, h("span", { class: "pt-note", style: "margin:0" }, creditsLine(cost)),
        h("span", null, h("button", { class: "pt-btn pt-btn--ghost", type: "button", onclick: function () { go(0); }, style: "margin-right:8px" }, "Edit"), run)));
      if (missing.length) { run.disabled = true; fail("Still needed: " + missing.map(function (q) { return q.label.replace(/\?$/, ""); }).join("; ") + "."); }
      run.addEventListener("click", function () {
        run.disabled = true; run.textContent = "Matching creators…"; fail("");
        api("POST", "/api/brief/run", { answers: answers }).then(function (r) {
          if (r.b.ok && !r.b.empty) { setCredits(r.b.credits); close(); results(r.b, qs, answers); return; }
          run.disabled = false; run.textContent = "Show my creators";
          fail(r.b.empty ? r.b.message : r.s === 429 ? "Too many requests. Please wait a few minutes." : (r.b.message || "Something went wrong. You weren't charged."));
        });
      });
    }
    close = layer(modal);
    currentClose = close;
    var base = close;
    close = function () { base(); if (currentClose === close) currentClose = null; };
    currentClose = close;
    x.onclick = function () { close(); };
  }

  var BASIS = { analysis: ["Measured", "pt-tag--good"], basic: ["Public data", ""], roster: ["Estimated", "pt-tag--warn"] };
  function scoreClass(tag) { return /Strong/.test(tag) ? "strong" : /Good/.test(tag) ? "good" : /Possible/.test(tag) ? "possible" : "no"; }

  function creatorCard(p) {
    var c = p.creator || {};
    var photo = h("div", { class: "pt-photo" });
    bg(photo, c.photo_url);
    var tags = h("div", { class: "pt-tags" });
    var b = BASIS[p.basis] || BASIS.roster;
    tags.appendChild(h("span", { class: "pt-tag " + b[1], title: p.basis === "roster" ? "Estimated from what we hold on file. A full analysis confirms it." : "" }, b[0]));
    (p.strengths || []).slice(0, 2).forEach(function (s) { tags.appendChild(h("span", { class: "pt-tag pt-tag--good" }, s)); });
    (p.watchouts || []).slice(0, 1).forEach(function (s) { tags.appendChild(h("span", { class: "pt-tag pt-tag--warn" }, s)); });
    var meta = [c.platform, followers(c.followers) + " followers", c.city, price(p.price)].filter(Boolean).join(" · ");
    return h("article", { class: "pt-card" }, photo,
      h("div", null, h("p", { class: "pt-name" }, c.name || p.code), h("p", { class: "pt-meta" }, meta),
        p.why ? h("p", { class: "pt-why" }, p.why) : null, tags),
      h("div", { class: "pt-score pt-score--" + scoreClass(p.tag) }, h("b", null, String(p.score)), h("span", null, p.tag)));
  }

  function results(res, qs, answers) {
    var modal = h("div", { class: "pt-modal pt-modal--wide", role: "dialog", "aria-modal": "true", "aria-labelledby": "pt-res-title" });
    var close;
    modal.appendChild(h("div", { class: "pt-head" }, h("h2", { class: "pt-title", id: "pt-res-title" }, "Your shortlist"),
      h("button", { class: "pt-x", type: "button", "aria-label": "Close", onclick: function () { close(); } }, "×")));
    var body = h("div", { class: "pt-body" });
    var sum = h("div", { class: "pt-summary" }, res.summary || (res.picks.length + " creators matched your brief, ranked by fit."),
      h("small", null, res.brief));
    body.appendChild(sum);
    var list = h("div", { class: "pt-list" });
    res.picks.forEach(function (p) { list.appendChild(creatorCard(p)); });
    body.appendChild(list);
    if (!res.narrated) body.appendChild(h("p", { class: "pt-note" }, "Scores come from our data. Written reasons weren't generated this time."));
    if (res.alternates && res.alternates.length) {
      var d = h("details", { class: "pt-alt" }, h("summary", null, res.alternates.length + " close runners-up"));
      var ul = h("ul");
      res.alternates.forEach(function (a) {
        ul.appendChild(h("li", null, h("span", null, (a.creator && a.creator.name) || a.code), h("span", null, a.score + " · " + price(a.price))));
      });
      d.appendChild(ul); body.appendChild(d);
    }
    modal.appendChild(body);
    var t = res.totals || {};
    var total = h("div", { class: "pt-total" }, t.from ? "Estimated creator fees " : "", t.from ? h("b", null, "SAR " + money(t.from) + (t.to && t.to !== t.from ? " – " + money(t.to) : "")) : "",
      t.unpriced ? " (+" + t.unpriced + " on request)" : "", t.from ? " · 15% VAT extra" : "");
    var open = h("a", { class: "pt-btn pt-btn--lime", href: ROOT + "selection/#s=" + encodeURIComponent(res.token), style: "text-decoration:none;display:inline-block" }, "Open as selection");
    var refine = h("button", { class: "pt-btn pt-btn--ghost", type: "button", onclick: function () { close(); wizard(qs, answers, 0); } }, "Refine brief");
    modal.appendChild(h("div", { class: "pt-bar" }, total, h("span", null, refine, " ", open)));
    close = layer(modal);
  }

  /* ------------------------------------------------------------------ chat */

  var chatThread = null;
  var IDEAS = ["Suggest creators for a skincare launch in KSA", "Who are your best micro-creators in Riyadh?", "What does a campaign cost?", "What happens after I pick a selection?"];

  function openChat() {
    var log = h("div", { class: "pt-log", role: "log", "aria-live": "polite" });
    var drawer = h("aside", { class: "pt-drawer", role: "dialog", "aria-label": "Ask HelloVoice AI" });
    var close;
    drawer.appendChild(h("div", { class: "pt-head" }, h("h2", { class: "pt-title" }, "Ask HelloVoice AI"),
      h("button", { class: "pt-x", type: "button", "aria-label": "Close", onclick: function () { close(); } }, "×")));
    drawer.appendChild(log);
    var ta = h("textarea", { rows: "1", placeholder: "Ask about creators, prices or your campaign…", "aria-label": "Your message", maxlength: "800" });
    var send = h("button", { class: "pt-btn pt-btn--lime", type: "button", style: "padding:12px 20px 10px" }, "Send");
    var foot = h("div", { class: "pt-foot" });
    function refreshFoot() { foot.textContent = ME && ME.credits != null ? "1 credit per message · " + ME.credits + " left. The assistant can be wrong; final quotes come from our team." : "The assistant can be wrong; final quotes come from our team."; }
    refreshFoot();
    drawer.appendChild(h("div", { class: "pt-compose" }, ta, send));
    drawer.appendChild(foot);

    function bubble(kind, text) { var b = h("div", { class: "pt-msg-b pt-msg-b--" + kind }, text); log.appendChild(b); log.scrollTop = log.scrollHeight; return b; }
    function cards(list) {
      if (!list || !list.length) return;
      var wrap = h("div", { class: "pt-cards" });
      list.forEach(function (c) {
        var ph = h("div", { class: "pt-photo" });
        bg(ph, c.photo_url);
        var m = h("button", { class: "pt-mini", type: "button" }, ph, h("div", null, h("b", null, c.name), h("span", null, [followers(c.followers), c.city, price(c.price)].filter(Boolean).join(" · "))));
        m.addEventListener("click", function () {
          var card = document.querySelector('.cat-card[data-code="' + c.code + '"]');
          if (card) { close(); card.scrollIntoView({ behavior: "smooth", block: "center" }); card.style.outline = "3px solid var(--lime)"; setTimeout(function () { card.style.outline = ""; }, 2400); }
        });
        wrap.appendChild(m);
      });
      log.appendChild(wrap); log.scrollTop = log.scrollHeight;
    }
    var busyNow = false;
    function ask(text) {
      text = (text || "").trim();
      if (!text || busyNow) return;
      busyNow = true; send.disabled = true;
      var ideas = log.querySelector(".pt-ideas"); if (ideas) ideas.remove();
      bubble("me", text); ta.value = "";
      var wait = bubble("ai", "Thinking…");
      api("POST", "/api/chat", { message: text, thread: chatThread }).then(function (r) {
        busyNow = false; send.disabled = false;
        if (r.b.ok) { chatThread = r.b.thread; wait.textContent = r.b.reply; setCredits(r.b.credits); refreshFoot(); cards(r.b.cards); }
        else { wait.className = "pt-msg-b pt-msg-b--err"; wait.textContent = r.s === 429 ? "You're sending messages too fast. Wait a moment." : (r.b.message || "That didn't work. You weren't charged."); }
        ta.focus();
      });
    }
    send.addEventListener("click", function () { ask(ta.value); });
    ta.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(ta.value); } });

    bubble("ai", "Hi" + (ME && ME.user ? " " + ME.user.name.split(" ")[0] : "") + ". I can search our creators, build a shortlist for your campaign and answer questions about how we work. What are you planning?");
    var ideas = h("div", { class: "pt-ideas" });
    IDEAS.forEach(function (i) { ideas.appendChild(h("button", { class: "pt-idea", type: "button", onclick: function () { ask(i); } }, i)); });
    log.appendChild(ideas);
    if (chatThread) {
      api("GET", "/api/chat/history?t=" + chatThread).then(function (r) {
        (r.b.messages || []).forEach(function (m) { bubble(m.role === "user" ? "me" : "ai", m.text); });
      });
    }
    close = layer(drawer, true);
    ta.focus();
  }

  /* --------------------------------------------------------------- account */

  function openAccount() {
    var modal = h("div", { class: "pt-modal", role: "dialog", "aria-modal": "true", "aria-labelledby": "pt-acc-title" });
    var close;
    var u = ME && ME.user;
    modal.appendChild(h("div", { class: "pt-head" }, h("h2", { class: "pt-title", id: "pt-acc-title" }, u ? u.name : ME.kind === "admin" ? "Admin preview" : "Guest access"),
      h("button", { class: "pt-x", type: "button", "aria-label": "Close", onclick: function () { close(); } }, "×")));
    var body = h("div", { class: "pt-body" });
    modal.appendChild(body);
    if (u) body.appendChild(h("p", { class: "pt-sub" }, [u.company, u.email].filter(Boolean).join(" · ")));
    else body.appendChild(h("p", { class: "pt-sub" }, ME.kind === "admin" ? "You're viewing as an administrator. AI is free for you." : "You're using an access code. Sign in with your work email for your own profile, campaigns and credits."));

    if (ME.credits != null) {
      var bal = h("div", { class: "pt-sec" }, h("h3", null, "AI credits"),
        h("div", { class: "pt-balance" }, h("b", { id: "pt-bal" }, String(ME.credits)), h("span", { class: "pt-sub", style: "margin:0" }, "credits left")),
        h("p", { class: "pt-sub" }, "A shortlist with written reasons costs " + ME.costs.brief + ", a chat message " + ME.costs.chat + ". Need more? ",
          h("a", { href: "mailto:info@hellovoice.co.uk?subject=" + encodeURIComponent("AI credits top-up") }, "Ask the team.")));
      var led = h("table", { class: "pt-ledger" });
      bal.appendChild(led);
      body.appendChild(bal);
      api("GET", "/api/credits").then(function (r) {
        if (!r.b.ok) return;
        $("pt-bal").textContent = r.b.balance; setCredits(r.b.balance);
        r.b.ledger.slice(0, 8).forEach(function (l) { led.appendChild(h("tr", null, h("td", null, l.reason + " · " + ago(l.at)), h("td", null, (l.delta > 0 ? "+" : "") + l.delta))); });
      });
    }

    var briefs = h("div", { class: "pt-sec" }, h("h3", null, "My briefs"));
    var bl = h("ul", { class: "pt-brieflist" });
    briefs.appendChild(bl); body.appendChild(briefs);
    api("GET", "/api/briefs").then(function (r) {
      var list = r.b.briefs || [];
      if (!list.length) { bl.appendChild(h("li", null, h("span", { class: "pt-sub", style: "margin:0" }, "None yet. Use Find creators to start one."))); return; }
      list.slice(0, 8).forEach(function (b) {
        bl.appendChild(h("li", null, h("span", null, b.summary + " · " + ago(b.at)), b.selection ? h("a", { href: ROOT + "selection/#s=" + encodeURIComponent(b.selection) }, "Open") : null));
      });
    });

    body.appendChild(h("div", { class: "pt-sec" }, h("h3", null, "My campaigns"),
      h("p", { class: "pt-sub", style: "margin:0" }, h("a", { href: ROOT + "campaign/dashboard/" }, "Open campaign tracking"), " to see results for the campaigns we run for you.")));

    if (u) {
      var f = {}; var form = h("form", { class: "pt-sec" }, h("h3", null, "My details"));
      [["name", "Name"], ["company", "Company"], ["job_title", "Job title"], ["phone", "Phone"]].forEach(function (pair) {
        f[pair[0]] = h("input", { class: "pt-field", name: pair[0], value: u[pair[0]] || "", autocomplete: "off" });
        form.appendChild(h("div", { style: "margin-bottom:12px" }, h("label", { class: "pt-label" }, pair[1]), f[pair[0]]));
      });
      var saved = h("span", { class: "pt-note", style: "margin:0" });
      form.appendChild(h("div", { class: "pt-actions", style: "margin-top:4px" }, saved, h("button", { class: "pt-btn pt-btn--ghost", type: "submit" }, "Save")));
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        api("POST", "/api/me/update", { name: f.name.value, company: f.company.value, job_title: f.job_title.value, phone: f.phone.value }).then(function (r) {
          saved.textContent = r.b.ok ? "Saved" : "Couldn't save";
          if (r.b.ok) { ME.user = r.b.user; var n = $("pt-chip-name"); if (n) n.textContent = r.b.user.name.split(" ")[0]; }
        });
      });
      body.appendChild(form);
    }

    body.appendChild(h("div", { class: "pt-actions" }, h("span"), h("button", { class: "pt-btn pt-btn--ghost", type: "button", onclick: function () {
      api("POST", "/api/auth/logout", {}).then(function () { location.reload(); });
    } }, "Sign out")));
    close = layer(modal);
  }

  /* ------------------------------------------------------------------ boot */

  function boot() {
    api("GET", "/api/me").then(function (r) {
      if (r.b && r.b.signed_in) { ME = r.b; mountDock(); return; }
      // Only replace the access-code gate once the server can actually send the email.
      if (r.b && r.b.email_signin) enhanceGate();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
