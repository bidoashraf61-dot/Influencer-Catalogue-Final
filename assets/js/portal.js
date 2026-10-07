/* Client portal layer for the catalogue pages.
 *
 *  - Gate: email sign-in with a one-time code (company addresses only), then a
 *    one-time profile step. The old access-code form stays one click away.
 *    Success reloads the page; the page's own script then finds the session
 *    cookie and unlocks itself, so every page that has a gate works unchanged.
 *  - Dock: "Find creators" (AI brief), "Ask" (chat) and the account chip, shown
 *    once signed in.
 *  - Voice: the character in the corner; a chat that greets, then gets tasks done.
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

  /* ------------------------------------------------------------- language */
  // English by default, Arabic for an Arabic browser or when chosen. Every static string goes
  // through T() inside h(), so a missing translation simply stays English.
  // The portal is English only for now (Bido, 2026-10-08). The chat assistant still replies in
  // whatever language the client writes. The Arabic table below is kept for later: set LANG to "ar".
  var LANG = "en";
  try { localStorage.removeItem("hv_lang"); } catch (e) { /* blocked */ }
  var AR = {
    "Sign in with your work email. We'll send a one-time code. No password needed.": "سجّل الدخول ببريد العمل. سنرسل لك رمزاً لمرة واحدة، بدون كلمة مرور.",
    "Email me a code": "أرسل لي الرمز", "Work email": "بريد العمل", "Verify and continue": "تحقق وتابع",
    "Send a new code": "أرسل رمزاً جديداً", "Use a different email": "استخدم بريداً آخر", "Your name": "الاسم",
    "Company": "الشركة", "Job title (optional)": "المسمى الوظيفي (اختياري)", "Phone (optional)": "الجوال (اختياري)",
    "Create my account": "أنشئ حسابي", "I have an access code instead": "لديّ رمز دخول بدلاً من ذلك",
    "Sign in with email instead": "الدخول بالبريد بدلاً من ذلك", "Enter a valid work email address.": "أدخل بريد عمل صحيحاً.",
    "Email confirmed. Tell us who you are.": "تم تأكيد البريد. عرّفنا بنفسك.", "Welcome. Opening the catalogue…": "أهلاً بك. جارٍ فتح الكتالوج…",
    "Please wait…": "يرجى الانتظار…", "Enter the 6-digit code.": "أدخل الرمز المكوّن من 6 أرقام.",
    "Too many requests. Please wait a few minutes.": "طلبات كثيرة. انتظر بضع دقائق.", "Too many attempts. Please wait a few minutes.": "محاولات كثيرة. انتظر بضع دقائق.",
    "Find creators": "ابحث عن مؤثرين", "Ask": "اسأل", "Account": "الحساب", "Admin": "المسؤول", "My account": "حسابي",
    "Review your brief": "راجع الملخص", "Describe your campaign in a sentence and our AI will fill the questions. Or answer them yourself below.":
      "صف حملتك في جملة وسيملأ الذكاء الاصطناعي الأسئلة، أو أجب عنها بنفسك بالأسفل.",
    "Fill it in for me": "املأها عني", "Reading your brief…": "جارٍ قراءة طلبك…", "or answer a few questions": "أو أجب عن بعض الأسئلة",
    "Back": "رجوع", "Next": "التالي", "Next / skip": "التالي / تخطَّ", "Review": "مراجعة", "Show my creators": "اعرض المؤثرين",
    "Matching creators…": "جارٍ مطابقة المؤثرين…", "Edit": "تعديل", "change": "تغيير", "Please choose an answer to continue.": "اختر إجابة للمتابعة.",
    "This is what we'll match creators against.": "هذا ما سنطابق المؤثرين عليه.", "We read your brief. Check it and change anything that's off.":
      "قرأنا طلبك. راجعه وعدّل ما يلزم.", "Not answered": "لم تتم الإجابة", "Describe the campaign in a sentence or two.": "صف الحملة في جملة أو جملتين.",
    "Close": "إغلاق", "Your shortlist": "قائمتك المختصرة", "Open as selection": "افتحها كقائمة", "Refine brief": "عدّل الطلب",
    "Measured": "مُقاس", "Public data": "بيانات عامة", "Estimated": "تقديري", "Price on request": "السعر عند الطلب",
    "Scores come from our data. Written reasons weren't generated this time.": "الدرجات من بياناتنا. لم تُكتب الأسباب هذه المرة.",
    "Ask HelloVoice AI": "اسأل مساعد هلا فويس", "Send": "إرسال", "Ask about creators, prices or your campaign…": "اسأل عن المؤثرين أو الأسعار أو حملتك…",
    "Thinking…": "جارٍ التفكير…", "Build my shortlist": "ابنِ قائمتي", "Ask the assistant": "اسأل المساعد", "Change answers": "غيّر الإجابات",
    "Your brief": "ملخص طلبك", "Skip": "تخطَّ", "Plan a campaign with me": "خطط حملة معي",
    "Suggest creators for a skincare launch in KSA": "اقترح مؤثرين لإطلاق منتج عناية بالبشرة في السعودية",
    "What does a campaign cost?": "كم تكلفة الحملة؟", "What happens after I pick a selection?": "ماذا يحدث بعد اختيار القائمة؟",
    "AI credits": "رصيد الذكاء الاصطناعي", "credits left": "رصيد متبقٍ", "My briefs": "طلباتي", "My campaigns": "حملاتي",
    "Open campaign tracking": "افتح متابعة الحملات", "My details": "بياناتي", "Name": "الاسم", "Job title": "المسمى الوظيفي", "Phone": "الجوال",
    "Save": "حفظ", "Saved": "تم الحفظ", "Sign out": "تسجيل الخروج", "My team": "فريقي", "Team selections": "قوائم الفريق",
    "Request more credits": "اطلب رصيداً إضافياً", "Download my data": "حمّل بياناتي", "Delete my account": "احذف حسابي", "Open": "فتح",
    "Score this selection": "قيّم هذه القائمة", "Answer a few quick questions about the campaign and we'll score every creator in it. Free.":
      "أجب عن أسئلة سريعة عن الحملة وسنقيّم كل مؤثر في القائمة. مجاناً.", "Not now": "ليس الآن", "Answer questions": "أجب عن الأسئلة",
    "Score my selection": "قيّم قائمتي", "Fit scores shown": "درجات الملاءمة ظاهرة", "Hide scores": "إخفاء الدرجات",
    "Request sent. The HelloVoice team will top you up shortly.": "تم إرسال الطلب. سيضيف فريق هلا فويس الرصيد قريباً.",
    "You're out of AI credits. Contact the HelloVoice team to top up.": "نفد رصيدك. تواصل مع فريق هلا فويس لإعادة الشحن.",
    "That code isn't right.": "الرمز غير صحيح.", "That code has expired. Request a new one.": "انتهت صلاحية الرمز. اطلب رمزاً جديداً.",
    "Too many wrong tries. Request a new code.": "محاولات خاطئة كثيرة. اطلب رمزاً جديداً.",
    "Please use your company email address. Personal addresses such as Gmail or Outlook can't be used.": "استخدم بريد شركتك. لا يمكن استخدام البريد الشخصي مثل Gmail أو Outlook.",
    "Please enter your name and company.": "أدخل اسمك واسم الشركة.", "Colleagues": "الزملاء", "Language": "اللغة"
  };
  function T(s) { return LANG === "ar" && AR[s] ? AR[s] : s; }
  // Question and option labels from the server, by id and value.
  var QAR = {
    goal: ["ما الهدف الرئيسي من الحملة؟", { awareness: "الوصول لأكبر عدد من الناس", engagement: "زيادة التفاعل", conversion: "زيادة المبيعات أو الزيارات أو التسجيلات", balanced: "مزيج متوازن" }],
    platforms: ["أين سيُنشر المحتوى؟", { any: "لا تفضيل" }],
    market: ["في أي دولة الجمهور؟", { SA: "السعودية", AE: "الإمارات", EG: "مصر", KW: "الكويت", QA: "قطر", BH: "البحرين", OM: "عُمان", JO: "الأردن" }],
    gender: ["من الجمهور؟", { Any: "الجميع", Women: "غالباً نساء", Men: "غالباً رجال" }],
    age: ["الفئة العمرية الرئيسية", { Any: "كل الأعمار", "45-54": "45+" }],
    category: ["في أي مجال المنتج؟", { "health care": "الرعاية الصحية / الأدوية", skincare: "العناية بالبشرة والجلدية", beauty: "التجميل", "hair care": "العناية بالشعر",
      fragrance: "العطور", "mother & baby": "الأم والطفل", food: "الأغذية والمشروبات", fitness: "اللياقة والصحة", fashion: "الأزياء", lifestyle: "أسلوب الحياة",
      technology: "التقنية", automotive: "السيارات", travel: "السفر", finance: "المال", gaming: "الألعاب" }],
    budget: ["ميزانية المؤثرين (ريال، قبل الضريبة)", { "50": "أقل من 50,000", "150": "50,000 – 150,000", "400": "150,000 – 400,000", "400+": "أكثر من 400,000", open: "لم تُحدد بعد" }],
    count: ["كم عدد المؤثرين؟", { "25": "20 أو أكثر" }],
    deliverable: ["ما المطلوب منهم؟", { reels: "ريلز / فيديوهات قصيرة", ugc: "محتوى UGC لقنواتنا", stories: "ستوري", event: "حضور فعالية أو متجر", review: "مراجعة منتج" }],
    timing: ["متى تبدأ؟", { asap: "خلال أسبوعين", month: "خلال 6 أسابيع", quarter: "الربع القادم", later: "نستكشف فقط" }],
    notes: ["هل هناك ما يجب أن نعرفه؟", {}]
  };
  function localise(qs) {
    if (LANG !== "ar") return qs;
    return qs.map(function (q) {
      var t = QAR[q.id];
      if (!t) return q;
      return Object.assign({}, q, { label: t[0], options: (q.options || []).map(function (o) { return Object.assign({}, o, { label: t[1][o.value] || o.label }); }) });
    });
  }
  function setLang(l) { try { localStorage.setItem("hv_lang", l); } catch (e) { /* blocked */ } location.reload(); }
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
      else if (k === "text") node.textContent = T(v);
      else if (k === "html") node.innerHTML = v;            // only ever our own static strings
      else if (k.slice(0, 2) === "on") node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : (k === "placeholder" || k === "aria-label" || k === "title") ? T(v) : v);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null || c === false) continue;
      node.appendChild(typeof c === "string" ? document.createTextNode(T(c)) : c);
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
    if (LANG === "ar") { node.setAttribute("dir", "rtl"); node.setAttribute("lang", "ar"); }
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
    if (LANG === "ar") return cost + " رصيد · متبقٍ " + ME.credits;
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
    function say(text, kind) { msg.textContent = T(text || ""); msg.className = "pt-msg" + (kind ? " is-" + kind : ""); }

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
    if (LANG === "ar") { panel.setAttribute("dir", "rtl"); panel.setAttribute("lang", "ar"); }

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
      toCodeLink.textContent = T(showingCode ? "Sign in with email instead" : "I have an access code instead");
      var first = (showingCode ? oldForm : email);
      var inp = first && first.querySelector ? (first.querySelector("input") || first) : first;
      if (inp && inp.focus) inp.focus();
    });

    var state = { email: "", ticket: "", timer: null };
    function busy(btn, on, label) {
      btn.disabled = on;
      btn.textContent = T(on ? "Please wait…" : label);
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
        say(r.b.sent === false ? (LANG === "ar" ? "أُرسل رمز قبل لحظات. تحقق من بريدك." : "A code was sent a moment ago. Check your inbox.")
          : (LANG === "ar" ? "أرسلنا رمزاً من 6 أرقام إلى " + state.email + ". صالح لمدة " + (r.b.minutes || 10) + " دقائق."
             : "We sent a 6-digit code to " + state.email + ". It lasts " + (r.b.minutes || 10) + " minutes."), "ok");
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
      dock.appendChild(h("button", { class: "pt-chip pt-chip--lime", type: "button", html: ICON.spark + "<span>" + T("Find creators") + "</span>", onclick: openWizard }));
    }
    if (ME.ai) dock.appendChild(h("button", { class: "pt-chip", type: "button", html: ICON.chat + "<span>" + T("Ask") + "</span>", onclick: openChat }));
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
    return api("GET", "/api/brief/questions").then(function (r) { QUESTIONS = localise(r.b.questions || []); return QUESTIONS; });
  }

  function openWizard() {
    loadQuestions().then(function (qs) { wizard(qs, {}, 0); });
  }

  var currentClose = null;
  function wizard(qs, answers, step, prefillNote, opts) {
    opts = opts || {};
    if (currentClose) currentClose();
    var total = qs.length + 1;                        // questions + review
    var onReview = step >= qs.length;
    var title = h("h2", { class: "pt-title", id: "pt-wiz-title" }, onReview ? "Review your brief" : opts.attach ? "Score this selection" : "Find creators");
    var modal = h("div", { class: "pt-modal", role: "dialog", "aria-modal": "true", "aria-labelledby": "pt-wiz-title" });
    var close;
    var x = h("button", { class: "pt-x", type: "button", "aria-label": "Close", onclick: function () { close(); } }, "×");
    modal.appendChild(h("div", { class: "pt-head" }, title, x));
    modal.appendChild(h("div", { class: "pt-progress" }, h("i", { style: "transform:scaleX(" + ((step + 1) / total).toFixed(3) + ")" })));
    var body = h("div", { class: "pt-body" });
    modal.appendChild(body);
    var err = h("div", { class: "pt-err", hidden: true, role: "alert" });

    function fail(text) { err.textContent = T(text || ""); err.hidden = !text; }
    function go(n) { wizard(qs, answers, Math.max(0, Math.min(n, qs.length)), prefillNote, opts); }

    if (!onReview) {
      var q = qs[step];
      if (step === 0 && !opts.attach) {
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
      body.appendChild(h("p", { class: "pt-note", style: "margin-top:0" }, LANG === "ar" ? "سؤال " + (step + 1) + " من " + qs.length + (q.required ? "" : " · اختياري")
        : "Question " + (step + 1) + " of " + qs.length + (q.required ? "" : " · optional")));
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
      var run = h("button", { class: "pt-btn pt-btn--lime", type: "button" }, opts.attach ? "Score my selection" : "Show my creators");
      body.appendChild(h("div", { class: "pt-actions" }, h("span", { class: "pt-note", style: "margin:0" }, opts.attach ? (LANG === "ar" ? "مجاناً" : "Free") : creditsLine(cost)),
        h("span", null, h("button", { class: "pt-btn pt-btn--ghost", type: "button", onclick: function () { go(0); }, style: "margin-right:8px" }, "Edit"), run)));
      if (missing.length) { run.disabled = true; fail("Still needed: " + missing.map(function (q) { return q.label.replace(/\?$/, ""); }).join("; ") + "."); }
      run.addEventListener("click", function () {
        run.disabled = true; run.textContent = T("Matching creators…"); fail("");
        var call = opts.attach ? api("POST", "/api/brief/attach", { token: opts.attach, answers: answers })
                               : api("POST", "/api/brief/run", { answers: answers });
        call.then(function (r) {
          if (r.b.ok && !r.b.empty) {
            if (r.b.credits != null) setCredits(r.b.credits);
            rememberBrief(r.b.brief_id);
            close(); results(r.b, qs, answers, opts); return;
          }
          run.disabled = false; run.textContent = T(opts.attach ? "Score my selection" : "Show my creators");
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

  function results(res, qs, answers, opts) {
    opts = opts || {};
    var modal = h("div", { class: "pt-modal pt-modal--wide", role: "dialog", "aria-modal": "true", "aria-labelledby": "pt-res-title" });
    var close;
    modal.appendChild(h("div", { class: "pt-head" }, h("h2", { class: "pt-title", id: "pt-res-title" }, "Your shortlist"),
      h("button", { class: "pt-x", type: "button", "aria-label": "Close", onclick: function () { close(); } }, "×")));
    var body = h("div", { class: "pt-body" });
    var sum = h("div", { class: "pt-summary" }, res.summary || (opts.attach
        ? (LANG === "ar" ? "قيّمنا " + res.picks.length + " مؤثرين في قائمتك مقابل هذا الطلب، الأفضل أولاً." : "We scored the " + res.picks.length + " creators in your selection against this brief, best fit first.")
        : (LANG === "ar" ? res.picks.length + " مؤثرين يطابقون طلبك، مرتبين حسب الملاءمة." : res.picks.length + " creators matched your brief, ranked by fit.")),
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
    var refine = h("button", { class: "pt-btn pt-btn--ghost", type: "button", onclick: function () { close(); wizard(qs, answers, 0, null, opts); } }, "Refine brief");
    if (opts.attach && /selection/.test(location.pathname) && location.hash.indexOf(encodeURIComponent(res.token)) > -1) {
      open.addEventListener("click", function (e) { e.preventDefault(); location.reload(); });
    }
    modal.appendChild(h("div", { class: "pt-bar" }, total, h("span", null, refine, " ", open)));
    close = layer(modal);
  }

  /* ------------------------------------------ brief for a hand-built selection */

  var offered = {};
  function offerBrief(token) {
    if (!ME || !ME.signed_in || !token || offered[token]) return;
    offered[token] = 1;
    api("GET", "/api/brief/for?s=" + encodeURIComponent(token)).then(function (r) {
      if (!r.b.ok || r.b.brief) return;
      var box = h("div", { class: "pt-toast", role: "dialog", "aria-label": "Score this selection" },
        h("p", { class: "pt-toast__t" }, "Score this selection"),
        h("p", { class: "pt-toast__b" }, "Answer a few quick questions about the campaign and we'll score every creator in it. Free."));
      if (LANG === "ar") box.setAttribute("dir", "rtl");
      var later = h("button", { class: "pt-btn pt-btn--ghost", type: "button", onclick: function () { box.remove(); } }, "Not now");
      var go = h("button", { class: "pt-btn pt-btn--lime", type: "button", onclick: function () {
        // Scoring needs only who the audience is and what the product is: six questions, not eleven.
        box.remove(); loadQuestions().then(function (qs) {
          wizard(qs.filter(function (q) { return q.required || q.id === "gender" || q.id === "age"; }), {}, 0, null, { attach: token });
        });
      } }, "Answer questions");
      box.appendChild(h("div", { class: "pt-actions", style: "margin-top:12px" }, later, go));
      document.body.appendChild(box);
    });
  }
  window.addEventListener("hv:selection-saved", function (e) { offerBrief(e.detail && e.detail.token); });

  function rememberBrief(id) { if (id) { try { sessionStorage.setItem("hv_brief", String(id)); } catch (e) { /* blocked */ } applyFit(); } }
  function storedBrief() { try { return sessionStorage.getItem("hv_brief"); } catch (e) { return null; } }

  // Fit badges on the catalogue cards for the last brief, so the whole roster reads against it.
  var FIT = null, fitObserver = null;
  function applyFit() {
    var id = storedBrief();
    if (!id || !document.querySelector(".cat-card")) { if (id && !fitObserver) watchCards(); return; }
    var paint = function () {
      if (!FIT) return;
      Array.prototype.forEach.call(document.querySelectorAll(".cat-card[data-code]"), function (card) {
        var v = FIT.scores[card.getAttribute("data-code")];
        var b = card.querySelector(".pt-fit");
        if (!v) { if (b) b.remove(); return; }
        if (!b) { b = h("span", { class: "pt-fit" }); card.classList.add("pt-has-fit"); card.appendChild(b); }
        b.className = "pt-fit pt-fit--" + scoreClass(v[1]);
        b.textContent = (LANG === "ar" ? "ملاءمة " : "Fit ") + v[0];
        b.title = v[1] + (v[2] === "roster" ? " · " + T("Estimated") : "");
      });
    };
    if (FIT && FIT.id === id) { paint(); return; }
    api("GET", "/api/brief/scores?b=" + encodeURIComponent(id)).then(function (r) {
      if (!r.b.ok) return;
      FIT = { id: id, scores: r.b.scores };
      paint(); watchCards(paint); fitChip();
    });
  }
  function watchCards(paint) {
    if (fitObserver || !("MutationObserver" in window)) return;
    var app = document.getElementById("cat-app") || document.body, t = null;
    fitObserver = new MutationObserver(function () { clearTimeout(t); t = setTimeout(function () { if (FIT) (paint || applyFit)(); else applyFit(); }, 150); });
    fitObserver.observe(app, { childList: true, subtree: true });
  }
  function fitChip() {
    var dock = $("pt-dock");
    if (!dock || $("pt-fitchip")) return;
    dock.insertBefore(h("button", { id: "pt-fitchip", class: "pt-chip", type: "button", title: "Hide scores", onclick: function () {
      try { sessionStorage.removeItem("hv_brief"); } catch (e) { /* blocked */ }
      FIT = null; Array.prototype.forEach.call(document.querySelectorAll(".pt-fit"), function (b) { b.remove(); });
      var c = $("pt-fitchip"); if (c) c.remove();
    } }, "Fit scores shown", " ×"), dock.firstChild ? dock.firstChild.nextSibling : null);
  }

  /* ------------------------------------------------------------------ chat */

  var chatThread = null;
  var chatBrief = null;                // the answers gathered for free in this chat
  var IDEAS = ["Plan a campaign with me", "Suggest creators for a skincare launch in KSA", "What does a campaign cost?", "What happens after I pick a selection?"];
  // A message that asks for creators or a campaign gets the free questions first, so the one paid
  // call that follows has everything it needs.
  var REQUEST = /campaign|creator|influencer|shortlist|launch|recommend|suggest|find|looking for|need .*(people|creators)|ugc|حمل|مؤثر|إطلاق|اطلاق|ابحث|أبحث|اقترح/i;
  var FLOW = ["goal", "platforms", "market", "category", "budget", "count"];
  var SHORT = { goal: "Goal", platforms: "Platforms", market: "Audience", category: "Product space", budget: "Budget (SAR)", count: "Creators" };

  function optionLabel(q, v) {
    var o = (q.options || []).filter(function (x) { return x.value === v; })[0];
    return o ? o.label : v;
  }

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
    function refreshFoot() {
      foot.textContent = (ME && ME.credits != null ? "Questions are free · 1 credit per AI answer · " + ME.credits + " left. " : "") +
        "The assistant can be wrong; final quotes come from our team.";
    }
    refreshFoot();
    drawer.appendChild(h("div", { class: "pt-compose" }, ta, send));
    drawer.appendChild(foot);

    function scroll() { log.scrollTop = log.scrollHeight; }
    function bubble(kind, text) { var b = h("div", { class: "pt-msg-b pt-msg-b--" + kind }, text); log.appendChild(b); scroll(); return b; }
    function cards(list) {
      if (!list || !list.length) return;
      var wrap = h("div", { class: "pt-cards" });
      list.forEach(function (c) {
        var ph = h("div", { class: "pt-photo" });
        bg(ph, c.photo_url);
        var m = h("button", { class: "pt-mini", type: "button" }, ph, h("div", null, h("b", null, c.name), h("span", null, [c.fit != null ? "Fit " + c.fit + "/100" : "", followers(c.followers), c.city, price(c.price)].filter(Boolean).join(" · "))));
        m.addEventListener("click", function () {
          var card = document.querySelector('.cat-card[data-code="' + c.code + '"]');
          if (card) { close(); card.scrollIntoView({ behavior: "smooth", block: "center" }); card.style.outline = "3px solid var(--lime)"; setTimeout(function () { card.style.outline = ""; }, 2400); }
        });
        wrap.appendChild(m);
      });
      log.appendChild(wrap); scroll();
    }
    var busyNow = false;
    function lock(on) { busyNow = on; send.disabled = on; ta.disabled = on; }

    function askAI(text, brief) {
      lock(true);
      var wait = bubble("ai", "Thinking…");
      api("POST", "/api/chat", { message: text, thread: chatThread, brief: brief || undefined }).then(function (r) {
        lock(false);
        if (r.b.ok) { chatThread = r.b.thread; wait.textContent = r.b.reply; setCredits(r.b.credits); refreshFoot(); cards(r.b.cards); }
        else { wait.className = "pt-msg-b pt-msg-b--err"; wait.textContent = r.s === 429 ? "You're sending messages too fast. Wait a moment." : (r.b.message || "That didn't work. You weren't charged."); }
        ta.focus();
      });
    }

    function ask(text) {
      text = (text || "").trim();
      if (!text || busyNow) return;
      var ideas = log.querySelector(".pt-ideas"); if (ideas) ideas.remove();
      bubble("me", text); ta.value = "";
      if (!chatBrief && REQUEST.test(text)) guided(text); else askAI(text);
    }

    /* The free questions, asked inside the chat. */
    function guided(text) {
      lock(true);
      Promise.all([loadQuestions(), api("POST", "/api/brief/guess", { text: text })]).then(function (res) {
        lock(false);
        var qs = res[0], answers = (res[1].b && res[1].b.answers) || {};
        var byId = {}; qs.forEach(function (q) { byId[q.id] = q; });
        var todo = FLOW.filter(function (id) { return byId[id] && !(answers[id] && answers[id].length); });
        var known = FLOW.filter(function (id) { return answers[id] && answers[id].length; });
        bubble("ai", (known.length ? "Got it. " : "") + "To find the right creators I need " + (todo.length ? todo.length + " quick detail" + (todo.length === 1 ? "" : "s") : "nothing more") +
          ". Tap to answer — this part is free.");
        var i = 0;
        function next() {
          if (i >= todo.length) return summary();
          var q = byId[todo[i]], many = q.type === "many";
          var card = h("div", { class: "pt-msg-b pt-msg-b--ai", style: "white-space:normal;max-width:100%" });
          card.appendChild(h("p", { style: "margin:0 0 10px;font-weight:600" }, q.label));
          var opts = h("div", { class: "pt-ideas" });
          var picked = [];
          q.options.forEach(function (o) {
            var b = h("button", { class: "pt-idea", type: "button", "aria-pressed": "false" }, o.label);
            b.addEventListener("click", function () {
              if (!many) { answers[q.id] = o.value; done(o.label); return; }
              var k = picked.indexOf(o.value);
              if (o.value === "any") picked = k > -1 ? [] : ["any"];
              else { picked = picked.filter(function (v) { return v !== "any"; }); if (k > -1) picked.splice(picked.indexOf(o.value), 1); else picked.push(o.value); }
              Array.prototype.forEach.call(opts.children, function (x, xi) {
                var on = picked.indexOf(q.options[xi].value) > -1;
                x.setAttribute("aria-pressed", on ? "true" : "false");
                x.style.background = on ? "var(--lime)" : ""; x.style.borderColor = on ? "var(--ink)" : "";
              });
            });
            opts.appendChild(b);
          });
          card.appendChild(opts);
          var row = h("div", { style: "margin-top:10px;display:flex;gap:8px" });
          if (many) row.appendChild(h("button", { class: "pt-idea", type: "button", style: "background:var(--ink);color:var(--white)", onclick: function () {
            if (!picked.length) return; answers[q.id] = picked.slice(); done(picked.map(function (v) { return optionLabel(q, v); }).join(", "));
          } }, "Next"));
          if (!q.required) row.appendChild(h("button", { class: "pt-idea", type: "button", onclick: function () { done("Skip"); } }, "Skip"));
          if (row.children.length) card.appendChild(row);
          log.appendChild(card); scroll();
          function done(label) { card.remove(); bubble("me", label); i += 1; next(); }
        }
        function summary() {
          chatBrief = answers;
          var lines = FLOW.filter(function (id) { return byId[id] && answers[id] && answers[id].length; }).map(function (id) {
            var v = answers[id]; return (SHORT[id] || byId[id].label.replace(/\?$/, "")) + ": " + (Array.isArray(v) ? v : [v]).map(function (x) { return optionLabel(byId[id], x); }).join(", ");
          });
          var card = h("div", { class: "pt-msg-b pt-msg-b--ai", style: "white-space:normal;max-width:100%" },
            h("p", { style: "margin:0 0 8px;font-weight:600" }, "Your brief"), h("p", { style: "margin:0 0 12px;white-space:pre-line" }, lines.join("\n")));
          var costs = (ME && ME.costs) || { brief: 5, chat: 1 };
          var build = h("button", { class: "pt-idea", type: "button", style: "background:var(--lime);border-color:var(--ink);font-weight:600" }, "Build my shortlist · " + costs.brief + " credits");
          var talk = h("button", { class: "pt-idea", type: "button" }, "Ask the assistant · " + costs.chat + " credit");
          var redo = h("button", { class: "pt-idea", type: "button" }, "Change answers");
          card.appendChild(h("div", { class: "pt-ideas" }, build, talk, redo));
          log.appendChild(card); scroll();
          build.addEventListener("click", function () {
            card.remove(); bubble("me", "Build my shortlist");
            lock(true);
            var wait = bubble("ai", "Matching creators…");
            api("POST", "/api/brief/run", { answers: answers, name: "Chat shortlist" }).then(function (r) {
              lock(false);
              if (!r.b.ok || r.b.empty) { wait.className = "pt-msg-b pt-msg-b--err"; wait.textContent = r.b.message || "That didn't work. You weren't charged."; return; }
              setCredits(r.b.credits); refreshFoot(); rememberBrief(r.b.brief_id);
              wait.textContent = (r.b.summary || (r.b.picks.length + " creators match your brief, best fit first.")) + " Scores are out of 100.";
              cards(r.b.picks.map(function (p) { var c = Object.assign({ code: p.code, name: p.code }, p.creator || {}); c.fit = p.score; return c; }));
              var a = h("a", { class: "pt-idea", href: ROOT + "selection/#s=" + encodeURIComponent(r.b.token), style: "text-decoration:none;background:var(--ink);color:var(--white)" }, "Open as selection");
              log.appendChild(h("div", { class: "pt-ideas" }, a)); scroll();
            });
          });
          talk.addEventListener("click", function () { card.remove(); askAI(text, answers); });
          redo.addEventListener("click", function () { card.remove(); chatBrief = null; answers = {}; guided(text); });
        }
        next();
      });
    }

    send.addEventListener("click", function () { ask(ta.value); });
    ta.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(ta.value); } });

    bubble("ai", "Hi" + (ME && ME.user ? " " + ME.user.name.split(" ")[0] : "") + ". Tell me what you're planning and I'll ask a few quick questions (free), then build a scored shortlist or answer anything about how we work.");
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
        h("p", { class: "pt-sub" }, LANG === "ar" ? "القائمة مع الأسباب تكلف " + ME.costs.brief + "، والرسالة " + ME.costs.chat + ". أسئلة الملخص مجانية."
          : "A shortlist with written reasons costs " + ME.costs.brief + ", a chat message " + ME.costs.chat + ". Brief questions are free."));
      var ask = h("div", { class: "pt-actions", style: "margin-top:10px;justify-content:flex-start" });
      var amt = h("select", { class: "pt-field", style: "width:auto", "aria-label": "Credits" });
      [50, 200, 500].forEach(function (n) { amt.appendChild(h("option", { value: String(n) }, "+" + n)); });
      var note = h("input", { class: "pt-field", style: "flex:1;min-width:160px", placeholder: LANG === "ar" ? "ملاحظة (اختياري)" : "Note (optional)" });
      var reqBtn = h("button", { class: "pt-btn pt-btn--ghost", type: "button" }, "Request more credits");
      var reqMsg = h("span", { class: "pt-note", style: "margin:0" });
      reqBtn.addEventListener("click", function () {
        reqBtn.disabled = true;
        api("POST", "/api/credits/request", { amount: +amt.value, note: note.value }).then(function (r) {
          reqMsg.textContent = r.s === 429 ? (LANG === "ar" ? "أرسلت طلبات كافية اليوم." : "You've sent enough requests today.") : T(r.b.message || "");
        });
      });
      ask.appendChild(amt); ask.appendChild(note); ask.appendChild(reqBtn);
      bal.appendChild(ask); bal.appendChild(reqMsg);
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

    if (u) {
      var team = h("div", { class: "pt-sec" }, h("h3", null, "My team"));
      var tl = h("ul", { class: "pt-brieflist" });
      team.appendChild(tl); body.appendChild(team);
      api("GET", "/api/team").then(function (r) {
        var members = r.b.members || [], sels = r.b.selections || [];
        if (!members.length) { tl.appendChild(h("li", null, h("span", { class: "pt-sub", style: "margin:0" },
          LANG === "ar" ? "عندما ينضم زملاء من شركتك سترى قوائمهم هنا." : "When colleagues from your company join, their selections appear here."))); return; }
        tl.appendChild(h("li", null, h("span", null, members.map(function (m) { return m.name + (m.job_title ? " (" + m.job_title + ")" : ""); }).join(", "))));
        sels.slice(0, 8).forEach(function (x) {
          tl.appendChild(h("li", null, h("span", null, x.name + " · " + x.owner + " · " + ago(x.at)), h("a", { href: ROOT + "selection/#s=" + encodeURIComponent(x.token) }, "Open")));
        });
      });
    }

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

    var extra = h("span");
    if (u) {
      extra.appendChild(h("button", { class: "pt-link", type: "button", style: "color:var(--ink)", onclick: function () {
        fetch(API + "/api/me/export", { credentials: "include" }).then(function (r) { return r.blob(); }).then(function (b) {
          var a = h("a", { href: URL.createObjectURL(b), download: "my-hellovoice-data.json" }); document.body.appendChild(a); a.click(); a.remove();
        });
      } }, "Download my data"));
      extra.appendChild(document.createTextNode(" · "));
      extra.appendChild(h("button", { class: "pt-link", type: "button", style: "color:var(--red-text)", onclick: function () {
        var typed = window.prompt(LANG === "ar" ? "سيُحذف حسابك وبياناتك الشخصية نهائياً. اكتب DELETE للتأكيد." : "Your account and personal data will be erased. Type DELETE to confirm.");
        if (typed !== "DELETE") return;
        api("POST", "/api/me/delete", { confirm: "DELETE" }).then(function () { location.reload(); });
      } }, "Delete my account"));
    }
    body.appendChild(h("div", { class: "pt-actions" }, extra, h("button", { class: "pt-btn pt-btn--ghost", type: "button", onclick: function () {
      api("POST", "/api/auth/logout", {}).then(function () { location.reload(); });
    } }, "Sign out")));
    close = layer(modal);
  }

  /* ----------------------------------------------------------------- voice */
  // "Voice": the HelloVoice character in the bottom-right corner. Opens a chat
  // that greets the client, then routes them through tap-to-answer flows that
  // get things done (find creators, filter the page, edit a selection, quote,
  // talk to a person). Typing goes to the AI assistant (credits, as in "Ask").
  // Every write is a button the client presses; the AI itself only answers.

  var VOICE_PAGES = { catalogue: 1, selection: 1, creator: 1 };
  var V_IMG = ROOT + "assets/brand/voice/";
  var V_ICON = {
    send: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h13M13 6l6 6-6 6"/></svg>',
    close: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    fresh: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 4v4h4"/></svg>'
  };

  function mountVoice() {
    var page = document.body.getAttribute("data-page");
    if (!VOICE_PAGES[page] || $("hv-voice")) return;
    var first = ME && ME.user ? ME.user.name.split(" ")[0] : "";
    var STORE = "hv-voice:" + (ME && ME.user ? ME.user.email : ME && ME.kind) + ":" + page;
    var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

    /* -- launcher -- */
    var root = h("div", { id: "hv-voice", class: "hv-voice" });
    var launch = h("button", { class: "hv-launch", type: "button", "aria-label": "Chat with Voice, the HelloVoice assistant", "aria-expanded": "false", "aria-controls": "hv-panel" });
    launch.innerHTML = '<span class="hv-launch__disc" aria-hidden="true"></span>' +
      '<img class="hv-launch__face" src="' + V_IMG + 'voice-head-160.webp" srcset="' + V_IMG + 'voice-head-320.webp 2x" alt="" width="84" height="84" decoding="async"/>' +
      '<span class="hv-launch__x" aria-hidden="true">' + V_ICON.close + "</span>" +
      '<span class="hv-launch__dot" aria-hidden="true" hidden></span>';
    var nudge = h("div", { class: "hv-nudge", role: "status", hidden: "" });
    nudge.innerHTML = "<span>Need a hand finding creators?</span>";
    var nudgeX = h("button", { class: "hv-nudge__x", type: "button", "aria-label": "Dismiss" });
    nudgeX.innerHTML = V_ICON.close;
    nudge.appendChild(nudgeX);

    /* -- panel -- */
    var panel = h("section", { id: "hv-panel", class: "hv-panel", role: "dialog", "aria-modal": "false", "aria-labelledby": "hv-name", hidden: "" });
    var head = h("header", { class: "hv-head" });
    head.innerHTML = '<img class="hv-head__fig" src="' + V_IMG + 'voice-figure-360.webp" srcset="' + V_IMG + 'voice-figure-720.webp 2x" alt="" width="120" height="192" decoding="async"/>' +
      '<div class="hv-head__id"><h2 class="hv-head__name" id="hv-name">Voice</h2>' +
      '<p class="hv-head__role"><i aria-hidden="true"></i>HelloVoice assistant · replies instantly</p></div>';
    var freshBtn = h("button", { class: "hv-head__btn", type: "button", "aria-label": "Start a new chat", title: "New chat" });
    freshBtn.innerHTML = V_ICON.fresh;
    var closeBtn = h("button", { class: "hv-head__btn", type: "button", "aria-label": "Close chat", title: "Close" });
    closeBtn.innerHTML = V_ICON.close;
    head.appendChild(h("div", { class: "hv-head__tools" }, freshBtn, closeBtn));
    var log = h("div", { class: "hv-log", role: "log", "aria-live": "polite", "aria-relevant": "additions" });
    var ta = h("textarea", { class: "hv-input", rows: "1", maxlength: "800", placeholder: "Type a message…", "aria-label": "Message Voice" });
    var send = h("button", { class: "hv-send", type: "button", "aria-label": "Send" });
    send.innerHTML = V_ICON.send;
    var compose = h("div", { class: "hv-compose" }, ta, send);
    var foot = h("p", { class: "hv-foot" });
    panel.appendChild(head); panel.appendChild(log); panel.appendChild(compose); panel.appendChild(foot);
    root.appendChild(panel); root.appendChild(nudge); root.appendChild(launch);
    document.body.appendChild(root);
    document.body.classList.add("has-voice");

    function refreshFoot() {
      foot.textContent = ME && ME.ai
        ? "Tapping options is free · typed questions use 1 credit" + (ME.credits != null ? " · " + ME.credits + " left" : "")
        : "Tap an option, or ask for your account manager.";
    }
    refreshFoot();

    // Keep clear of the selection tray when it is open.
    var tray = $("cat-tray");
    function lift() {
      var hgt = tray && !tray.hidden ? tray.getBoundingClientRect().height : 0;
      root.style.setProperty("--hv-lift", Math.ceil(hgt) + "px");
    }
    if (tray && window.MutationObserver) new MutationObserver(lift).observe(tray, { attributes: true, childList: true, subtree: true });
    window.addEventListener("resize", lift);
    lift();

    /* -- transcript -- */
    var msgs = [];
    try { msgs = JSON.parse(sessionStorage.getItem(STORE) || "[]") || []; } catch (e) { msgs = []; }
    function save() { try { sessionStorage.setItem(STORE, JSON.stringify(msgs.slice(-60))); } catch (e) { /* private */ } }
    function scroll() { log.scrollTop = log.scrollHeight; }
    function row(kind, node) {
      var r = h("div", { class: "hv-row hv-row--" + kind });
      if (kind === "ai") r.appendChild(h("img", { class: "hv-row__ava", src: V_IMG + "voice-head-160.webp", alt: "", width: "32", height: "32" }));
      r.appendChild(node); log.appendChild(r); scroll(); return r;
    }
    function bubble(kind, text, keep) {
      var b = h("div", { class: "hv-msg hv-msg--" + kind }, text);
      row(kind, b);
      if (keep !== false) { msgs.push({ from: kind, text: text }); save(); }
      if (kind === "ai" && panel.hidden) launch.querySelector(".hv-launch__dot").hidden = false;
      return b;
    }
    // Voice "types" for a moment before each message: short, so it reads as a reply, not a wait.
    var queue = Promise.resolve();
    function say(text, then) {
      queue = queue.then(function () {
        return new Promise(function (done) {
          var dots = row("ai", h("div", { class: "hv-msg hv-msg--ai hv-typing", "aria-label": "Voice is typing" }, h("i"), h("i"), h("i")));
          setTimeout(function () {
            dots.remove(); bubble("ai", text); if (then) then(); done();
          }, reduce ? 0 : Math.min(900, 280 + text.length * 9));
        });
      });
      return queue;
    }
    function chips(list, opts) {
      opts = opts || {};
      queue = queue.then(function () {
        var wrap = h("div", { class: "hv-chips" + (opts.stack ? " hv-chips--stack" : "") });
        list.forEach(function (c) {
          var b = h("button", { class: "hv-chip" + (c.primary ? " hv-chip--lime" : "") + (c.ghost ? " hv-chip--ghost" : ""), type: "button" }, c.label);
          if (c.pressed != null) b.setAttribute("aria-pressed", String(!!c.pressed));
          b.addEventListener("click", function () {
            if (c.toggle) { c.toggle(b); return; }
            if (!opts.keep) wrap.remove();
            if (c.echo !== false) bubble("me", c.label);
            c.go();
          });
          wrap.appendChild(b);
        });
        log.appendChild(wrap); scroll();
      });
      return queue;
    }
    var expecting = null;               // a function waiting for the next typed message
    function askFor(text, placeholder, fn) {
      say(text, function () { ta.placeholder = placeholder || "Type here…"; expecting = fn; ta.focus(); });
    }

    /* -- the menu -- */
    function menu(lead) {
      if (lead) say(lead);
      var list = [{ label: "Find creators for a campaign", go: flowFind }];
      if (document.querySelector(".cat-bar")) list.push({ label: "Show creators on this page", go: flowShow });
      list.push({ label: "Work on my selection", go: flowSelection },
                { label: "Get a quote", go: flowQuote },
                { label: "Talk to my account manager", go: flowHuman },
                { label: "Just browsing", ghost: true, go: function () { say("Sure. I'll be right here in the corner whenever you need me."); } });
      chips(list, { stack: true });
    }
    function greet() {
      var hour = new Date().getHours();
      var part = hour >= 5 && hour < 12 ? "Good morning" : hour >= 12 && hour < 17 ? "Good afternoon" : hour >= 17 && hour < 23 ? "Good evening" : "Hi";
      say(part + (first ? ", " + first : "") + " 👋 I'm Voice, HelloVoice's assistant.");
      menu("I can find creators for your campaign, filter this page, update your selection or get you a quote. What can I help you with today?");
    }

    /* -- 1. find creators: the brief questions, free, then one paid shortlist -- */
    var FLOW_IDS = ["goal", "platforms", "market", "category", "budget", "count"];
    function flowFind(seed) {
      var text = typeof seed === "string" ? seed : "";
      say(text ? "Got it. A few quick taps and I'll match the roster. This part is free." : "Let's find the right creators. A few quick taps, all free.");
      Promise.all([loadQuestions(), text ? api("POST", "/api/brief/guess", { text: text }) : Promise.resolve({ b: {} })]).then(function (res) {
        var qs = res[0], answers = (res[1].b && res[1].b.answers) || {};
        var byId = {}; qs.forEach(function (q) { byId[q.id] = q; });
        var todo = FLOW_IDS.filter(function (id) { return byId[id] && !(answers[id] && answers[id].length); });
        var i = 0;
        function next() {
          if (i >= todo.length) return review();
          var q = byId[todo[i]], many = q.type === "many", picked = [];
          say(q.label);
          var list = q.options.map(function (o) {
            return many ? { label: o.label, pressed: false, toggle: function (b) {
              var k = picked.indexOf(o.value);
              if (k > -1) picked.splice(k, 1); else picked.push(o.value);
              b.setAttribute("aria-pressed", String(k === -1));
            } } : { label: o.label, go: function () { answers[q.id] = o.value; i++; next(); } };
          });
          if (many) list.push({ label: "Next", primary: true, echo: false, go: function () {
            answers[q.id] = picked.length ? picked.slice() : ["any"];
            bubble("me", picked.length ? picked.map(function (v) { return optionLabel(q, v); }).join(", ") : "Any");
            i++; next();
          } });
          if (!q.required) list.push({ label: "Skip", ghost: true, go: function () { i++; next(); } });
          chips(list, { keep: many });
          if (many) queue = queue.then(function () {
            // The "Next" press removes the whole option set.
            var sets = log.querySelectorAll(".hv-chips"); var last = sets[sets.length - 1];
            last.addEventListener("click", function (e) { if (e.target.closest(".hv-chip--lime")) last.remove(); });
          });
        }
        function review() {
          var costs = (ME && ME.costs) || { brief: 5 };
          var lines = FLOW_IDS.filter(function (id) { return byId[id] && answers[id] && answers[id].length; }).map(function (id) {
            var v = answers[id]; return (byId[id].label.replace(/\?$/, "")) + ": " + (Array.isArray(v) ? v : [v]).map(function (x) { return optionLabel(byId[id], x); }).join(", ");
          });
          say("Here's your brief:\n" + lines.join("\n"));
          var list = [];
          if (ME && ME.ai) list.push({ label: "Build my shortlist · " + costs.brief + " credits", primary: true, go: function () { build(answers); } });
          list.push({ label: "Change answers", ghost: true, go: function () { flowFind(text); } });
          if (!(ME && ME.ai)) list.push({ label: "Send it to my account manager", primary: true, go: function () { handoff("handoff", "Brief from Voice:\n" + lines.join("\n")); } });
          chips(list);
        }
        next();
      });
    }
    function build(answers) {
      say("Matching the roster to your brief…");
      api("POST", "/api/brief/run", { answers: answers, name: "Voice shortlist" }).then(function (r) {
        if (!r.b.ok || r.b.empty) { say(r.b.message || "That didn't work and you weren't charged. Want to try again?"); menu(); return; }
        setCredits(r.b.credits); refreshFoot();
        if (typeof rememberBrief === "function") rememberBrief(r.b.brief_id);
        say((r.b.summary || (r.b.picks.length + " creators match your brief.")) + " Best fit first, scored out of 100.");
        queue = queue.then(function () { creatorCards(r.b.picks.slice(0, 6).map(function (p) { var c = Object.assign({ code: p.code, name: p.code }, p.creator || {}); c.fit = p.score; return c; })); });
        say("I've saved them as a selection for you.");
        chips([{ label: "Open the selection", primary: true, echo: false, go: function () { location.href = ROOT + "selection/#s=" + encodeURIComponent(r.b.token); } },
               { label: "Get a quote for it", go: function () { quoteFor({ name: "Voice shortlist", token: r.b.token }); } },
               { label: "Something else", ghost: true, go: function () { menu("What next?"); } }]);
      });
    }
    function creatorCards(list) {
      if (!list || !list.length) return;
      var wrap = h("div", { class: "hv-cards" });
      list.forEach(function (c) {
        var ph = h("span", { class: "hv-card__photo" }); bg(ph, c.photo_url);
        var b = h("button", { class: "hv-card", type: "button" }, ph,
          h("span", { class: "hv-card__txt" }, h("b", null, c.name),
            h("span", null, [c.fit != null ? "Fit " + c.fit : "", c.followers ? followers(c.followers) : "", c.city].filter(Boolean).join(" · "))));
        b.addEventListener("click", function () {
          var card = document.querySelector('.cat-card[data-code="' + c.code + '"]');
          if (card) { card.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" }); card.classList.add("hv-flash"); setTimeout(function () { card.classList.remove("hv-flash"); }, 2400); }
        });
        wrap.appendChild(b);
      });
      log.appendChild(wrap); scroll();
    }

    /* -- 2. show creators on this page: a sentence becomes the page's filters -- */
    function flowShow() {
      askFor("Describe who you'd like to see, e.g. “micro skincare creators in Jeddah on TikTok”.", "Who should I show?", function (text) {
        api("POST", "/api/discover/parse", { text: text }).then(function (r) {
          var p = (r.b && r.b.filters) || {};
          var done = applyFilters(p);
          if (!done.length) { say("I couldn't pick out filters from that. Try naming a platform, city, size or topic."); chips([{ label: "Try again", go: flowShow }, { label: "Back to the menu", ghost: true, go: function () { menu("What would you like to do?"); } }]); return; }
          var shown = Array.prototype.filter.call(document.querySelectorAll(".cat-card"), function (c) { return !c.hidden && !c.classList.contains("cat-card--copy"); }).length;
          say("Done. The page now shows " + done.join(", ") + ". " + (shown ? shown + " creator" + (shown === 1 ? "" : "s") + " match." : "Nobody matches all of that yet, so try loosening one filter."));
          chips([{ label: "Clear the filters", go: function () { clearFilters(); say("Filters cleared. You're seeing the whole roster again."); } },
                 { label: "Build a scored shortlist instead", go: function () { flowFind(text); } },
                 { label: "Close chat", ghost: true, echo: false, go: function () { toggle(false); } }]);
        });
      });
    }
    function fold(t) { return String(t || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "").trim(); }
    function pick(sel) { var b = document.querySelector(sel); if (b && !b.checked) b.click(); return !!b; }
    function clearFilters() { var c = document.querySelector(".cat-active__clear"); if (c) c.click(); }
    function applyFilters(p) {
      clearFilters();
      var bar = document.querySelector(".cat-bar"); if (!bar) return [];
      var out = [];
      function each(dim, test, label) {
        var hit = false;
        Array.prototype.forEach.call(bar.querySelectorAll('input[data-dim="' + dim + '"]'), function (box) {
          if (test(box.value) && !box.checked) { box.click(); hit = true; }
        });
        if (hit) out.push(label);
      }
      (p.platform || []).forEach(function (pl) { each("platform", function (v) { return v === pl; }, pl); });
      var sizes = (p.tier || []).map(function (t) { return fold(t).replace("-tier", ""); });
      if (sizes.length || p.hcp) each("tier", function (v) {
        var hcp = /^hcp/i.test(v), base = fold(v.replace(/^hcp\s*-\s*/i, "")).replace("-tier", "");
        return (p.hcp ? hcp : !hcp) && (!sizes.length || sizes.some(function (s) { return base.indexOf(s) === 0; }));
      }, p.hcp ? "healthcare professionals" + (sizes.length ? " (" + p.tier.join(", ") + ")" : "") : p.tier.join(", ") + " creators");
      if ((p.city || []).length) {
        (p.city || []).forEach(function (city) { each("place", function (v) { return fold(v.split("|")[1]).indexOf(fold(city)) === 0; }, city); });
      } else if ((p.country || []).length) {
        p.country.forEach(function (c) { if (pick('input[data-country="' + c + '"]')) out.push(c); });
      }
      if ((p.interest_words || []).length) {
        var words = p.interest_words.map(fold).filter(Boolean);
        each("interest", function (v) { var f = " " + fold(v) + " "; return words.some(function (w) { return f.indexOf(w) !== -1; }); }, "the topics you named");
      }
      return out;
    }

    /* -- 3. work on my selection -- */
    var ROSTER = null;
    function roster() {
      if (ROSTER) return Promise.resolve(ROSTER);
      return api("GET", "/api/roster").then(function (r) { ROSTER = (r.b && r.b.roster) || []; return ROSTER; });
    }
    function byCode(list, code) { return list.filter(function (c) { return c.code === code; })[0]; }
    function flowSelection() {
      say("Let me pull up your selections…");
      api("GET", "/api/voice/selections").then(function (r) {
        var sels = (r.b && r.b.selections) || [];
        if (!sels.length) {
          say("You don't have a saved selection yet. Pick creators on the catalogue and press Save, or let me build one for you.");
          chips([{ label: "Find creators for a campaign", primary: true, go: flowFind }, { label: "Back to the menu", ghost: true, go: function () { menu("What else can I do?"); } }]);
          return;
        }
        say("Which one?");
        chips(sels.slice(0, 8).map(function (s) {
          return { label: s.name + " · " + s.codes.length + (s.mine ? "" : " (team)"), go: function () { selActions(s); } };
        }), { stack: true });
      });
    }
    function selActions(s) {
      say("“" + s.name + "” has " + s.codes.length + " creator" + (s.codes.length === 1 ? "" : "s") + ". What should I do?");
      chips([{ label: "Open it", echo: false, go: function () { location.href = ROOT + "selection/#s=" + encodeURIComponent(s.token); } },
             { label: "Add creators", go: function () { selAdd(s); } },
             { label: "Remove creators", go: function () { selRemove(s); } },
             { label: "Rename it", go: function () { selRename(s); } },
             { label: "Compare two creators", go: function () { selCompare(s); } },
             { label: "Get a quote for it", go: function () { quoteFor(s); } }]);
    }
    function saveSel(s, codes, name, msg) {
      return api("POST", "/api/selection", { token: s.token, name: name || s.name, codes: codes }).then(function (r) {
        if (!r.b.ok) { say(r.b.reason === "empty" ? "A selection needs at least one creator, so I left it as it was." : "I couldn't save that just now. Please try again."); return; }
        s.codes = codes; s.name = name || s.name; s.token = r.b.token || s.token;
        say(msg);
        chips([{ label: "Open it", primary: true, echo: false, go: function () { location.href = ROOT + "selection/#s=" + encodeURIComponent(s.token); } },
               { label: "More changes", go: function () { selActions(s); } },
               { label: "Done", ghost: true, go: function () { say("Anytime."); } }]);
      });
    }
    function selAdd(s) {
      askFor("Type the creators' names or codes, separated by commas.", "e.g. Sara A., HV-MI-014", function (text) {
        roster().then(function (list) {
          var want = text.split(/[,،\n]+/).map(fold).filter(Boolean), found = [], miss = [];
          want.forEach(function (w) {
            var c = list.filter(function (x) { return fold(x.code) === w || fold(x.name) === w; })[0] ||
                    list.filter(function (x) { return fold(x.name).indexOf(w) === 0; })[0];
            if (c && s.codes.indexOf(c.code) === -1 && found.indexOf(c) === -1) found.push(c); else if (!c) miss.push(w);
          });
          if (!found.length) { say("I couldn't find " + (miss.length ? "“" + miss.join("”, “") + "”" : "anyone new") + " on the roster. Check the spelling, or use the code on the card."); chips([{ label: "Try again", go: function () { selAdd(s); } }, { label: "Back", ghost: true, go: function () { selActions(s); } }]); return; }
          say("Add " + found.map(function (c) { return c.name; }).join(", ") + " to “" + s.name + "”?" + (miss.length ? " (I couldn't find: " + miss.join(", ") + ")" : ""));
          chips([{ label: "Yes, add " + (found.length === 1 ? "them" : "all " + found.length), primary: true, go: function () {
            saveSel(s, s.codes.concat(found.map(function (c) { return c.code; })), null, "Added. “" + s.name + "” now has " + (s.codes.length + found.length) + " creators.");
          } }, { label: "Cancel", ghost: true, go: function () { selActions(s); } }]);
        });
      });
    }
    function selRemove(s) {
      roster().then(function (list) {
        var drop = [];
        say("Tap the creators to remove, then confirm.");
        chips(s.codes.map(function (code) {
          var c = byCode(list, code) || { name: code };
          return { label: c.name, pressed: false, toggle: function (b) {
            var k = drop.indexOf(code); if (k > -1) drop.splice(k, 1); else drop.push(code);
            b.setAttribute("aria-pressed", String(k === -1));
          } };
        }).concat([{ label: "Remove selected", primary: true, echo: false, go: function () {
          if (!drop.length) { say("Nothing picked, so nothing changed."); return; }
          bubble("me", "Remove " + drop.length);
          saveSel(s, s.codes.filter(function (c) { return drop.indexOf(c) === -1; }), null, "Removed " + drop.length + ". “" + s.name + "” now has " + (s.codes.length - drop.length) + " creators.");
        } }]), { keep: true });
        queue = queue.then(function () {
          var sets = log.querySelectorAll(".hv-chips"); var last = sets[sets.length - 1];
          last.addEventListener("click", function (e) { if (e.target.closest(".hv-chip--lime")) last.remove(); });
        });
      });
    }
    function selRename(s) {
      askFor("What should “" + s.name + "” be called?", "New name", function (text) {
        var name = text.trim().slice(0, 120);
        if (!name) return;
        saveSel(s, s.codes.slice(), name, "Renamed to “" + name + "”.");
      });
    }
    function selCompare(s) {
      roster().then(function (list) {
        var two = [];
        say("Tap two creators to compare.");
        chips(s.codes.map(function (code) {
          var c = byCode(list, code) || { name: code, code: code };
          return { label: c.name, pressed: false, toggle: function (b) {
            if (two.indexOf(c) > -1) return;
            two.push(c); b.setAttribute("aria-pressed", "true");
            if (two.length === 2) { b.closest(".hv-chips").remove(); bubble("me", two[0].name + " vs " + two[1].name); compare(two); }
          } };
        }), { keep: true });
      });
    }
    function compare(two) {
      queue = queue.then(function () {
        var rows = [["Size", function (c) { return c.tier || "—"; }], ["Followers", function (c) { return c.followers ? followers(c.followers) : "—"; }],
                    ["Platform", function (c) { return c.platform || "—"; }], ["City", function (c) { return c.city || "—"; }],
                    ["Niche", function (c) { return c.interest || "—"; }], ["Full analysis", function (c) { return c.analysis ? "On file" : "Not yet"; }]];
        var t = h("table", { class: "hv-compare" });
        var hr = h("tr", null, h("th", null, ""));
        two.forEach(function (c) { hr.appendChild(h("th", { scope: "col" }, c.name)); });
        t.appendChild(hr);
        rows.forEach(function (r) {
          var tr = h("tr", null, h("th", { scope: "row" }, r[0]));
          two.forEach(function (c) { tr.appendChild(h("td", null, r[1](c))); });
          t.appendChild(tr);
        });
        row("ai", h("div", { class: "hv-msg hv-msg--ai hv-msg--wide" }, t));
      });
      var missing = two.filter(function (c) { return !c.analysis; });
      var list = two.filter(function (c) { return c.analysis; }).map(function (c) {
        return { label: "Open " + c.name.split(" ")[0] + "'s analysis", echo: false, go: function () { location.href = ROOT + "creator/#c=" + encodeURIComponent(c.code); } };
      });
      missing.forEach(function (c) {
        list.push({ label: "Request " + c.name.split(" ")[0] + "'s analysis", go: function () {
          api("POST", "/api/creator/request", { code: c.code }).then(function (r) {
            say(r.b.ok ? "Requested. The team will add " + c.name + "'s full analysis and you'll see it on their card." : "That request didn't go through. Please try again.");
          });
        } });
      });
      list.push({ label: "Done", ghost: true, go: function () { say("Anytime."); } });
      chips(list);
    }

    /* -- 4 & 5. quote and a person -- */
    function flowQuote() {
      api("GET", "/api/voice/selections").then(function (r) {
        var sels = (r.b && r.b.selections) || [];
        if (!sels.length) { handoffAsk("quote", null, "Tell me what you'd like quoted (creators, deliverables, dates) and I'll send it to your account manager."); return; }
        say("Which selection should we quote?");
        chips(sels.slice(0, 6).map(function (s) { return { label: s.name + " · " + s.codes.length, go: function () { quoteFor(s); } }; })
          .concat([{ label: "Something else", ghost: true, go: function () { handoffAsk("quote", null, "Tell me what you'd like quoted and I'll pass it on."); } }]), { stack: true });
      });
    }
    function quoteFor(s) { handoffAsk("quote", s, "Anything to add for the quote, like deliverables, dates or budget? Or tap Send as is."); }
    function handoffAsk(topic, sel, prompt) {
      askFor(prompt, "Add a note…", function (text) { handoff(topic, text, sel); });
      if (sel) chips([{ label: "Send as is", primary: true, go: function () { expecting = null; ta.placeholder = "Type a message…"; handoff(topic, "", sel); } }]);
    }
    function flowHuman() { handoffAsk("handoff", null, "What would you like to discuss? I'll send it to your account manager with our chat."); }
    function handoff(topic, note, sel) {
      api("POST", "/api/voice/handoff", { topic: topic, message: note, selection: sel ? sel.name + " (" + sel.token + ")" : "", transcript: msgs.slice(-30) }).then(function (r) {
        if (r.s === 429) { say("You've sent a few requests already today. The team has them and will be in touch."); return; }
        if (!r.b.ok) { say("That didn't go through. Please try again in a moment."); return; }
        say((topic === "quote" ? "Quote request sent" : "Sent") + (r.b.kam ? " to your account manager" : " to the HelloVoice team") +
            ". They usually reply within one working day, by email" + (ME && ME.user && ME.user.phone ? " or phone" : "") + ".");
        chips([{ label: "Back to the menu", ghost: true, go: function () { menu("Anything else?"); } }]);
      });
    }

    /* -- typing: answers a pending question, or goes to the AI -- */
    var REQ = /campaign|creator|influencer|shortlist|launch|recommend|suggest|find|looking for|ugc|حمل|مؤثر|إطلاق|اطلاق|ابحث|أبحث|اقترح/i;
    var thread = null, busy = false;
    function submit() {
      var text = ta.value.trim();
      if (!text || busy) return;
      ta.value = ""; grow();
      bubble("me", text);
      Array.prototype.forEach.call(log.querySelectorAll(".hv-chips"), function (c) { c.remove(); });
      if (expecting) { var fn = expecting; expecting = null; ta.placeholder = "Type a message…"; fn(text); return; }
      if (/account manager|talk to (a )?(person|human|someone)|call me/i.test(text)) { handoff("handoff", text); return; }
      if (REQ.test(text) && !/how much|price|cost/i.test(text)) { flowFind(text); return; }
      if (!(ME && ME.ai)) { say("I can't answer typed questions on this access yet. Tap an option, or I can pass your question to your account manager."); chips([{ label: "Send it to my account manager", primary: true, go: function () { handoff("handoff", text); } }, { label: "Show the menu", ghost: true, go: function () { menu(); } }]); return; }
      busy = true; send.disabled = true;
      var dots = row("ai", h("div", { class: "hv-msg hv-msg--ai hv-typing", "aria-label": "Voice is typing" }, h("i"), h("i"), h("i")));
      api("POST", "/api/chat", { message: text, thread: thread }).then(function (r) {
        busy = false; send.disabled = false; dots.remove();
        if (r.b.ok) {
          thread = r.b.thread; bubble("ai", r.b.reply); setCredits(r.b.credits); refreshFoot();
          if (r.b.cards && r.b.cards.length) creatorCards(r.b.cards);
        } else {
          say(r.s === 429 ? "One moment, that was quick. Try again in a few seconds." : (r.b.message || "That didn't work, and you weren't charged."));
        }
      });
    }
    function grow() { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 120) + "px"; }
    ta.addEventListener("input", grow);
    ta.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } });
    send.addEventListener("click", submit);

    /* -- open and close -- */
    var started = false;
    function toggle(on) {
      if (on === undefined) on = panel.hidden;
      if (on) {
        panel.hidden = false;
        requestAnimationFrame(function () { root.classList.add("is-open"); });
        launch.setAttribute("aria-expanded", "true");
        launch.querySelector(".hv-launch__dot").hidden = true;
        hideNudge(true);
        if (!started) {
          started = true;
          if (msgs.length) { msgs.forEach(function (m) { bubble(m.from, m.text, false); }); menu("Welcome back" + (first ? ", " + first : "") + ". What's next?"); }
          else greet();
        }
        setTimeout(function () { ta.focus({ preventScroll: true }); }, 60);
      } else {
        root.classList.remove("is-open");
        launch.setAttribute("aria-expanded", "false");
        setTimeout(function () { if (!root.classList.contains("is-open")) panel.hidden = true; }, reduce ? 0 : 220);
        launch.focus({ preventScroll: true });
      }
    }
    launch.addEventListener("click", function () { toggle(); });
    closeBtn.addEventListener("click", function () { toggle(false); });
    freshBtn.addEventListener("click", function () {
      msgs = []; save(); thread = null; expecting = null; log.innerHTML = ""; queue = Promise.resolve(); greet();
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && root.classList.contains("is-open")) toggle(false); });

    /* -- the nudge: once per visit, after the client has had a look around -- */
    var NUDGE = "hv-voice-nudged";
    function hideNudge(forever) {
      nudge.classList.remove("is-in");
      setTimeout(function () { nudge.hidden = true; }, 200);
      if (forever) { try { sessionStorage.setItem(NUDGE, "1"); } catch (e) { /* private */ } }
    }
    nudge.addEventListener("click", function (e) { if (e.target.closest(".hv-nudge__x")) { hideNudge(true); return; } toggle(true); });
    var nudged = false;
    try { nudged = sessionStorage.getItem(NUDGE) === "1"; } catch (e) { /* private */ }
    if (!nudged) {
      setTimeout(function () {
        if (root.classList.contains("is-open")) return;
        nudge.hidden = false;
        requestAnimationFrame(function () { nudge.classList.add("is-in"); launch.classList.add("is-waving"); });
        setTimeout(function () { launch.classList.remove("is-waving"); }, 1600);
        setTimeout(function () { if (!root.classList.contains("is-open")) hideNudge(true); }, 9000);
      }, 4500);
    }
  }

  /* ------------------------------------------------------------------ boot */

  function boot() {
    api("GET", "/api/me").then(function (r) {
      if (r.b && r.b.signed_in) {
        ME = r.b; mountDock(); mountVoice();
        var m = /[#&]s=([^&]+)/.exec(location.hash || "");
        if (document.body.getAttribute("data-page") === "selection" && m) setTimeout(function () { offerBrief(decodeURIComponent(m[1])); }, 1200);
        if (storedBrief()) applyFit();
        return;
      }
      // Only replace the access-code gate once the server can actually send the email.
      if (r.b && r.b.email_signin) enhanceGate();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
