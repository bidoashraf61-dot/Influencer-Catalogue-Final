/* Client portal layer for the catalogue pages.
 *
 *  - Gate: email sign-in with a one-time code (company addresses only), then a
 *    one-time profile step. The old access-code form stays one click away.
 *    Success reloads the page; the page's own script then finds the session
 *    cookie and unlocks itself, so every page that has a gate works unchanged.
 *  - Account circle: initials top right, opening a menu (profile, campaigns,
 *    credits, admin, sign out), shown once signed in.
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
  // A few hooks other pages use (the account page): talk, setPhoto.
  var HV = window.hvPortal = window.hvPortal || {};

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

  // The account circle, top right: initials on lime, opening a small menu.
  // Ask and Find creators live in the HELV Assistant now, and admin moves into
  // the menu, so the bar keeps only the site's own links and this circle.
  function mountDock() {
    if (!ME || !ME.signed_in || $("pt-dock")) return;
    var cat = document.querySelector(".cat-topbar__links");
    var dock = h("div", { id: "pt-dock", class: "pt-dock" + (cat ? "" : " pt-dock--fixed") });
    var u = ME.user;
    var name = u && u.name ? u.name : ME.kind === "admin" ? "HelloVoice team" : "Guest access";
    var initials = u && u.name ? u.name.trim().split(/\s+/).slice(0, 2).map(function (w) { return w.charAt(0); }).join("").toUpperCase()
      : ME.kind === "admin" ? "HV" : "G";
    var btn = h("button", { class: "pt-avatar", type: "button", id: "pt-avatar", "aria-haspopup": "menu", "aria-expanded": "false", "aria-controls": "pt-menu", "aria-label": "Account menu" });
    btn.appendChild(h("span", { id: "pt-chip-name", class: "pt-avatar__ini" }, initials));
    function setPhoto(v) {
      var old = btn.querySelector("img");
      if (old) old.remove();
      btn.classList.toggle("has-photo", !!v);
      if (v) btn.appendChild(h("img", { class: "pt-avatar__img", alt: "", src: API + "/api/me/image?k=photo&v=" + encodeURIComponent(v) }));
    }
    HV.setPhoto = setPhoto;
    if (u && u.photo) setPhoto(u.photo);
    var menu = h("div", { class: "pt-menu", id: "pt-menu", role: "menu", "aria-labelledby": "pt-avatar", hidden: true });
    var head = h("div", { class: "pt-menu__head" }, h("b", { class: "pt-menu__name" }, name));
    var sub = u ? [u.job_title, u.company].filter(Boolean).join(" · ") || u.email : ME.kind === "admin" ? "Administrator" : "Signed in with an access code";
    if (sub) head.appendChild(h("span", { class: "pt-menu__sub" }, sub));
    menu.appendChild(head);
    function item(label, act, extra, cls) {
      var el = act.href ? h("a", { class: "pt-menu__item" + (cls ? " " + cls : ""), role: "menuitem", href: act.href })
                        : h("button", { class: "pt-menu__item" + (cls ? " " + cls : ""), role: "menuitem", type: "button" });
      el.appendChild(h("span", null, label));
      if (extra) el.appendChild(extra);
      if (act.go) el.addEventListener("click", function () { toggle(false); act.go(); });
      else el.addEventListener("click", function () { toggle(false); });
      menu.appendChild(el);
      return el;
    }
    function rule() { menu.appendChild(h("div", { class: "pt-menu__rule", role: "separator" })); }
    var credits = ME.credits != null ? h("span", { class: "pt-menu__badge", id: "pt-chip-credits" }, ME.credits + " cr") : null;
    var ACC = ROOT + "account/";
    if (u) {
      // Account holders: their own space, then help, then out.
      item("My home", { href: ACC + "#home" });
      item("My selections", { href: ACC + "#selections" });
      item("My campaigns", { href: ACC + "#campaigns" });
      if (credits) item("AI credits", { go: openAccount }, credits);
      item("Settings", { href: ACC + "#settings" });
      rule();
      item("Help · contact my account manager", { go: function () { if (HV.talk) HV.talk(); else location.href = ACC + "#home"; } });
    } else if (ME.kind === "admin") {
      item("Preview as client", { go: openAccount });
      item("My campaigns", { href: ROOT + "campaign/dashboard/" });
      rule();
      item("Open admin", { href: API + "/" });
    } else {
      // Access-code guests: no profile for now, just their campaigns and credits.
      item("My campaigns", { href: ROOT + "campaign/dashboard/" });
      if (credits) item("AI credits", { go: openAccount }, credits);
      rule();
    }
    item("Sign out", { go: function () { api("POST", "/api/auth/logout", {}).then(function () { location.href = ROOT; }); } }, null, "pt-menu__item--quiet");

    function toggle(open) {
      menu.hidden = !open;
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) { var first = menu.querySelector(".pt-menu__item"); if (first) first.focus(); }
    }
    btn.addEventListener("click", function (e) { e.stopPropagation(); toggle(menu.hidden); });
    document.addEventListener("click", function (e) { if (!menu.hidden && !dock.contains(e.target)) toggle(false); });
    document.addEventListener("keydown", function (e) {
      if (menu.hidden) return;
      if (e.key === "Escape") { toggle(false); btn.focus(); return; }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      var items = Array.prototype.slice.call(menu.querySelectorAll(".pt-menu__item"));
      var i = items.indexOf(document.activeElement);
      items[(i + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus();
      e.preventDefault();
    });
    dock.appendChild(btn);
    dock.appendChild(menu);
    if (cat) cat.appendChild(dock); else document.body.appendChild(dock);
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
      var freeLine = (ME && ME.costs && !ME.costs.search && ME.credits != null)
        ? (ME.credits >= cost ? creditsLine(cost) + " · free without written reasons" : "Free · written reasons need " + cost + " credits")
        : creditsLine(cost);
      body.appendChild(h("div", { class: "pt-actions" }, h("span", { class: "pt-note", style: "margin:0" }, opts.attach ? "Free" : freeLine),
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
          var label = (!costs.search && ME && ME.credits != null && ME.credits < costs.brief) ? "Build my shortlist · free"
            : "Build my shortlist · " + costs.brief + " credits" + (!costs.search ? " (free without reasons)" : "");
          var build = h("button", { class: "pt-idea", type: "button", style: "background:var(--lime);border-color:var(--ink);font-weight:600" }, label);
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
          if (r.b.ok) { ME.user = r.b.user; var n = $("pt-chip-name"); if (n) n.textContent = r.b.user.name.trim().split(/\s+/).slice(0, 2).map(function (w) { return w.charAt(0); }).join("").toUpperCase(); }
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

  var VOICE_PAGES = { catalogue: 1, selection: 1, creator: 1, account: 1 };
  var V_IMG = ROOT + "assets/brand/voice/";
  var V_ICON = {
    send: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h13M13 6l6 6-6 6"/></svg>',
    close: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    minimize: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 13h12"/></svg>',
    fresh: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 4v4h4"/></svg>',
    grow: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/></svg>',
    shrink: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 14h6v6M20 10h-6V4M14 10l7-7M10 14l-7 7"/></svg>',
    mic: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
    check: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    plus: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>'
  };

  function mountVoice() {
    var page = document.body.getAttribute("data-page");
    if (!VOICE_PAGES[page] || $("hv-voice")) return;
    var first = ME && ME.user ? ME.user.name.split(" ")[0] : "";
    // One conversation per access (signed-in client or access code), carried across pages for a week.
    var STORE = "hv-chat:" + ((ME && ME.chat_key) || (ME && ME.user ? ME.user.email : ME && ME.kind) || "guest");
    var KEEP_MS = 7 * 24 * 3600 * 1000;
    // On a selection's page the assistant works on that selection: its brief, its scores.
    function selToken() { var m = page === "selection" && /(?:^|[#&])s=([A-Za-z0-9_-]+)/.exec(location.hash || ""); return m ? m[1] : ""; }
    var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

    /* -- launcher -- */
    var root = h("div", { id: "hv-voice", class: "hv-voice" });
    var launch = h("button", { class: "hv-launch", type: "button", "aria-label": "Chat with HELV Assistant", "aria-expanded": "false", "aria-controls": "hv-panel" });
    launch.innerHTML = '<span class="hv-launch__disc" aria-hidden="true"></span>' +
      '<img class="hv-launch__face" src="' + V_IMG + 'voice-head-160.webp" srcset="' + V_IMG + 'voice-head-320.webp 2x" alt="" width="84" height="84" decoding="async"/>' +
      (reduce ? "" : '<video class="hv-launch__vid" muted loop playsinline autoplay preload="auto" aria-hidden="true" poster="' + V_IMG + 'voice-loop-poster.webp">' +
        '<source src="' + V_IMG + 'voice-loop.webm" type="video/webm"/><source src="' + V_IMG + 'voice-loop.mp4" type="video/mp4"/></video>') +
      '<span class="hv-launch__x" aria-hidden="true">' + V_ICON.close + "</span>" +
      '<span class="hv-launch__dot" aria-hidden="true" hidden></span>';
    // The waving loop (made with Higgsfield) replaces the still once it can play; the still stays if it can't.
    var vid = launch.querySelector(".hv-launch__vid");
    if (vid) {
      // Autoplay can start before this listener exists, so check the clock too.
      var live = function () { launch.classList.add("has-video"); };
      vid.addEventListener("playing", live);
      vid.addEventListener("timeupdate", live, { once: true });
      // If the browser stops the loop (power saving, background tab), fall back to the still.
      vid.addEventListener("pause", function () { launch.classList.remove("has-video"); });
      if (!vid.paused && vid.readyState > 2) live();
      vid.addEventListener("error", function () { vid.remove(); }, true);
      var p = vid.play && vid.play(); if (p && p.catch) p.catch(function () { /* autoplay blocked: keep the still */ });
    }
    var nudge = h("div", { class: "hv-nudge", role: "status", hidden: "" });
    nudge.innerHTML = "<span>Need a hand finding creators?</span>";
    var nudgeX = h("button", { class: "hv-nudge__x", type: "button", "aria-label": "Dismiss" });
    nudgeX.innerHTML = V_ICON.close;
    nudge.appendChild(nudgeX);

    /* -- panel -- */
    var panel = h("section", { id: "hv-panel", class: "hv-panel", role: "dialog", "aria-modal": "false", "aria-labelledby": "hv-name", hidden: "" });
    var head = h("header", { class: "hv-head" });
    head.innerHTML = '<img class="hv-head__fig" src="' + V_IMG + 'voice-figure-360.webp" srcset="' + V_IMG + 'voice-figure-720.webp 2x" alt="" width="120" height="192" decoding="async"/>' +
      '<div class="hv-head__id"><h2 class="hv-head__name" id="hv-name">HELV Assistant</h2>' +
      '<p class="hv-head__role"><span class="hv-head__on"><i aria-hidden="true"></i>Online</span><span class="hv-tag">Replies instantly</span></p></div>';
    var freshBtn = h("button", { class: "hv-head__btn", type: "button", "aria-label": "Start a new chat", title: "New chat" });
    freshBtn.innerHTML = V_ICON.fresh;
    var closeBtn = h("button", { class: "hv-head__btn", type: "button", "aria-label": "Close chat", title: "Close" });
    closeBtn.innerHTML = V_ICON.close;
    var growBtn = h("button", { class: "hv-head__btn hv-head__grow", type: "button", "aria-label": "Make the chat bigger", "aria-pressed": "false", title: "Bigger" });
    growBtn.innerHTML = V_ICON.grow;
    // Minimize folds the chat down to its round launcher; the conversation stays.
    var minBtn = h("button", { class: "hv-head__btn", type: "button", "aria-label": "Minimize chat", title: "Minimize" });
    minBtn.innerHTML = V_ICON.minimize;
    head.appendChild(h("div", { class: "hv-head__tools" }, growBtn, freshBtn, minBtn, closeBtn));
    var log = h("div", { class: "hv-log", role: "log", "aria-live": "polite", "aria-relevant": "additions" });
    var ta = h("textarea", { class: "hv-input", rows: "1", maxlength: "800", placeholder: "Type a message…", "aria-label": "Message HELV Assistant" });
    var send = h("button", { class: "hv-send", type: "button", "aria-label": "Send" });
    send.innerHTML = V_ICON.send;
    var Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
    var mic = Speech ? h("button", { class: "hv-mic", type: "button", "aria-label": "Speak your message", "aria-pressed": "false", title: "Speak" }) : null;
    if (mic) mic.innerHTML = V_ICON.mic;
    var compose = h("div", { class: "hv-compose" }, ta, mic || document.createTextNode(""), send);
    // Creators added from the chat's cards, waiting to be saved as a selection.
    var picksBar = h("div", { class: "hv-picks", hidden: "" });
    var foot = h("p", { class: "hv-foot" });
    panel.appendChild(head); panel.appendChild(log); panel.appendChild(picksBar); panel.appendChild(compose);
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
      document.body.style.setProperty("--hv-lift", Math.ceil(hgt) + "px");
    }
    if (tray && window.MutationObserver) new MutationObserver(lift).observe(tray, { attributes: true, childList: true, subtree: true });
    window.addEventListener("resize", lift);
    lift();

    /* -- transcript -- */
    var msgs = [], kept = null;
    try { kept = JSON.parse(localStorage.getItem(STORE) || "null"); } catch (e) { kept = null; }
    if (kept && kept.at && Date.now() - kept.at < KEEP_MS && Array.isArray(kept.msgs)) msgs = kept.msgs; else kept = null;
    function save() {
      try { localStorage.setItem(STORE, JSON.stringify({ at: Date.now(), thread: thread, msgs: msgs.slice(-60) })); } catch (e) { /* private */ }
    }
    function scroll() { log.scrollTop = log.scrollHeight; }
    function row(kind, node) {
      var r = h("div", { class: "hv-row hv-row--" + kind });
      if (kind === "ai") { var ava = h("span", { class: "hv-row__ava", "aria-hidden": "true" }); bg(ava, V_IMG + "voice-head-160.webp"); r.appendChild(ava); }
      r.appendChild(node); log.appendChild(r); scroll(); return r;
    }
    // The AI writes light markdown: **bold** and "* " bullets. Rendered as text nodes, never as HTML.
    function rich(text) {
      var box = document.createDocumentFragment();
      String(text).replace(/^\s*[*-]\s+/gm, "• ").split(/(\*\*[^*]+\*\*)/).forEach(function (part) {
        var m = /^\*\*([^*]+)\*\*$/.exec(part);
        box.appendChild(m ? h("b", null, m[1]) : document.createTextNode(part));
      });
      return box;
    }
    function bubble(kind, text, keep) {
      var b = h("div", { class: "hv-msg hv-msg--" + kind });
      b.appendChild(kind === "ai" ? rich(text) : document.createTextNode(text));
      row(kind, b);
      if (keep !== false) { msgs.push({ from: kind, text: text }); save(); }
      if (kind === "ai" && panel.hidden) launch.querySelector(".hv-launch__dot").hidden = false;
      return b;
    }
    // Text that types itself out: a steady pace that speeds up when a long answer is waiting,
    // so it reads like typing and never falls far behind the stream. Instant under reduced motion.
    function typer(node) {
      var target = "", shown = 0, raf = 0, last = 0, ended = false, after = null;
      node.classList.add("is-live");
      function visible(txt) {                   // never show half of a **bold** marker
        var n = (txt.match(/\*\*/g) || []).length;
        return n % 2 ? txt.slice(0, txt.lastIndexOf("**")) : txt;
      }
      function paint() { node.textContent = ""; node.appendChild(rich(visible(target.slice(0, shown)))); scroll(); }
      function finish() { node.classList.remove("is-live"); var f = after; after = null; if (f) f(); }
      function frame(t) {
        var dt = last ? Math.min(64, t - last) : 16; last = t;
        var backlog = target.length - shown;
        shown = Math.min(target.length, shown + Math.max(1, Math.round((0.05 + backlog * 0.0007) * dt)));
        paint();
        if (shown < target.length) { raf = requestAnimationFrame(frame); return; }
        raf = 0; last = 0;
        if (ended) finish();
      }
      function kick() { if (reduce) { shown = target.length; paint(); if (ended) finish(); return; } if (!raf) raf = requestAnimationFrame(frame); }
      return {
        push: function (more) { target += more; kick(); },
        end: function (full, then) {
          if (typeof full === "string" && full.length >= target.length) target = full;
          ended = true; after = then || null; kick();
        }
      };
    }
    // The assistant's own messages: a short "typing" pause, then the words type out.
    var queue = Promise.resolve();
    function say(text, then) {
      queue = queue.then(function () {
        return new Promise(function (done) {
          var dots = row("ai", h("div", { class: "hv-msg hv-msg--ai hv-typing", "aria-label": "The assistant is typing" }, h("i"), h("i"), h("i")));
          setTimeout(function () {
            dots.remove();
            var b = bubble("ai", text); b.textContent = "";
            typer(b).end(text, function () { if (then) then(); done(); });
          }, reduce ? 0 : Math.min(500, 200 + text.length * 3));
        });
      });
      return queue;
    }
    function chips(list, opts) {
      opts = opts || {};
      queue = queue.then(function () {
        var wrap = h("div", { class: "hv-chips" + (opts.stack ? " hv-chips--stack" : "") });
        var many = list.some(function (c) { return c.toggle; });
        wrap.appendChild(h("p", { class: "hv-chips__hint" }, opts.hint || (many ? "Pick any, then confirm" : "Tap to choose")));
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

    /* -- a brief question: options fill the message box; the client sends --
       Tapping an option writes its label into the box (tap again to take it
       out), several can be combined, and the client can add their own words.
       Nothing moves on until they press Send. */
    function question(q, idx, total, how) {
      queue = queue.then(function () {
        var many = q.type === "many";
        var card = h("div", { class: "hv-msg hv-msg--ai hv-q", role: "group", "aria-label": q.label });
        card.appendChild(h("p", { class: "hv-q__count" }, "Question " + (idx + 1) + " of " + total));
        card.appendChild(h("p", { class: "hv-q__label" }, q.label));
        var grid = h("div", { class: "hv-q__opts" });
        // Read the box: which options it names (whole labels, which may hold commas) and the client's own words.
        var byLen = q.options.slice().sort(function (a, b) { return b.label.length - a.label.length; });
        function read(text) {
          var rest = " " + text + " ", hit = [];
          byLen.forEach(function (o) {
            var k = rest.toLowerCase().indexOf(o.label.toLowerCase());
            if (k > -1) { hit.push(o); rest = rest.slice(0, k) + " " + rest.slice(k + o.label.length); }
          });
          hit.sort(function (a, b) { return text.toLowerCase().indexOf(a.label.toLowerCase()) - text.toLowerCase().indexOf(b.label.toLowerCase()); });
          return { opts: hit, own: rest.replace(/^[\s;,،+·-]+|[\s;,،+·-]+$/g, "").replace(/\s*[;،]\s*[;،]+\s*/g, "; ").replace(/\s{2,}/g, " ") };
        }
        function sync() {
          var on = read(ta.value).opts.map(function (o) { return o.label; });
          grid.querySelectorAll(".hv-opt").forEach(function (b) { b.setAttribute("aria-pressed", String(on.indexOf(b.dataset.label) > -1)); });
        }
        q.options.forEach(function (o) {
          var b = h("button", { class: "hv-opt", type: "button", "aria-pressed": "false", "data-label": o.label },
            h("span", { class: "hv-opt__tick", "aria-hidden": "true" }), h("span", null, o.label));
          b.querySelector(".hv-opt__tick").innerHTML = V_ICON.check;
          b.addEventListener("click", function () {
            var now = read(ta.value), mine = now.opts.map(function (x) { return x.label; });
            if (mine.indexOf(o.label) > -1) mine = mine.filter(function (x) { return x !== o.label; });
            else mine = many ? mine.concat([o.label]) : [o.label];
            ta.value = mine.concat(now.own ? [now.own] : []).join("; ");
            grow(); sync();
            if (window.matchMedia && !matchMedia("(pointer: coarse)").matches) ta.focus();
          });
          grid.appendChild(b);
        });
        card.appendChild(grid);
        var foot = h("div", { class: "hv-q__foot" },
          h("span", { class: "hv-q__hint" }, many ? "Pick one or more, add your own words, then Send" : "Pick one or type your answer, then Send"));
        if (how.back) foot.appendChild(h("button", { class: "hv-q__link", type: "button", onclick: function () { finish(); bubble("me", "Back", false); how.back(); } }, "Back"));
        if (how.skip) foot.appendChild(h("button", { class: "hv-q__link", type: "button", onclick: function () { finish(); bubble("me", "Skip"); how.skip(); } }, "Skip"));
        card.appendChild(foot);
        row("ai", card);
        ta.placeholder = "Tap above or type your answer";
        ta.addEventListener("input", sync);
        function finish() {
          card.classList.add("is-done");
          grid.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
          foot.remove(); ta.removeEventListener("input", sync);
          expecting = null; ta.placeholder = "Type a message…";
        }
        expecting = function (text) {
          var got = read(text), vals = got.opts.map(function (o) { return o.value; }), own = got.own ? [got.own] : [];
          if (!many && vals.length > 1) vals = vals.slice(-1);
          card.classList.add("is-done");
          grid.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
          foot.remove(); ta.removeEventListener("input", sync); ta.placeholder = "Type a message…";
          how.done(vals, own.join(", "));
        };
      });
      return queue;
    }

    /* -- the menu -- */
    function menu(lead) {
      if (lead) say(lead);
      var list = selToken()
        ? [{ label: "About this selection", go: aboutSelection }, { label: "Find more creators", go: flowFind }]
        : [{ label: "Find creators for a campaign", go: flowFind }];
      if (document.querySelector(".cat-bar")) list.push({ label: "Show creators on this page", go: flowShow });
      list.push({ label: "Work on my selection", go: flowSelection },
                { label: "Get a quote", go: flowQuote },
                { label: "Talk to my account manager", go: flowHuman },
                { label: "Just browsing", ghost: true, go: function () { say("Sure. I'll be right here in the corner whenever you need me."); } });
      chips(list, { stack: true });
    }
    // After every answer: the likely next requests as options, with the box below still open for typing.
    function nextUp(lead) {
      if (lead) say(lead);
      var list = [{ label: "Find creators", go: flowFind }];
      if (document.querySelector(".cat-bar")) list.push({ label: "Filter this page", go: flowShow });
      list.push({ label: "My selection", go: flowSelection }, { label: "Get a quote", go: flowQuote },
                { label: "Talk to a person", go: flowHuman });
      chips(list, { hint: "Tap to choose · or type below" });
    }
    function greet() {
      say("Hi" + (first ? " " + first : "") + ", I'm here to help you 👋");
      if (selToken()) { aboutSelection(); return; }
      menu("How can I help you?");
    }
    // The selection on this page: its brief if one was recorded, else an offer to score it.
    function aboutSelection() {
      api("GET", "/api/voice/selection?s=" + encodeURIComponent(selToken())).then(function (r) {
        var x = r.b;
        if (!x || !x.ok) { menu("How can I help you?"); return; }
        if (x.brief) {
          say("This is “" + x.name + "” (" + x.count + " creator" + (x.count === 1 ? "" : "s") + "). Its brief is on file:\n" +
              x.brief.answers.map(function (a) { return "• " + a.q.replace(/\?$/, "") + ": **" + a.a + "**"; }).join("\n"));
          if (x.scores && x.scores.length) say("Everyone is scored against it. Best fit: " + x.scores.slice(0, 3).map(function (c) { return c.name + " (" + c.score + ")"; }).join(", ") + ".");
          chips([{ label: "Why do the top creators fit?", echo: true, go: function () { ta.value = "Why do the top creators in this selection fit my brief?"; submit(); } },
                 { label: "Change the brief and rescore", go: function () { flowFind("", { attach: x.token, name: x.name }); } },
                 { label: "Get a quote for it", go: function () { quoteFor({ name: x.name, token: x.token }); } },
                 { label: "Something else", ghost: true, go: function () { menu("What would you like to do?"); } }]);
        } else {
          say("This is “" + x.name + "” (" + x.count + " creator" + (x.count === 1 ? "" : "s") + "). It doesn't have a brief yet, so the creators aren't scored against your campaign.");
          say("Answer a few quick questions (free) and I'll score every creator in it.");
          chips([{ label: "Score this selection", primary: true, go: function () { flowFind("", { attach: x.token, name: x.name }); } },
                 { label: "Not now", ghost: true, go: function () { menu("What would you like to do?"); } }]);
        }
      });
    }

    /* -- 1. find creators: the brief questions, free, then one paid shortlist -- */
    var FLOW_IDS = ["goal", "platforms", "market", "category", "budget", "count"];
    function flowFind(seed, mode) {
      var text = typeof seed === "string" ? seed : "";
      var attach = mode && mode.attach;
      // Scoring an existing selection needs the campaign, not a budget or a head count.
      var ids = attach ? ["goal", "platforms", "market", "gender", "category"] : FLOW_IDS;
      say(attach ? "A few quick taps about the campaign, all free." :
          text ? "Got it. A few quick taps and I'll match the roster. This part is free." : "Let's find the right creators. A few quick taps, all free.");
      Promise.all([loadQuestions(), text ? api("POST", "/api/brief/guess", { text: text }) : Promise.resolve({ b: {} })]).then(function (res) {
        var qs = res[0], answers = (res[1].b && res[1].b.answers) || {};
        var byId = {}; qs.forEach(function (q) { byId[q.id] = q; });
        var todo = ids.filter(function (id) { return byId[id] && !(answers[id] && answers[id].length); });
        var i = 0;
        function next() {
          if (i >= todo.length) return review();
          var q = byId[todo[i]];
          question(q, i, todo.length, {
            back: i > 0 ? function () { i--; delete answers[todo[i]]; next(); } : null,
            skip: q.required ? null : function () { i++; next(); },
            done: function (vals, note) {
              if (vals.length) answers[q.id] = q.type === "many" ? vals : vals[0];
              else if (q.type === "many") answers[q.id] = ["any"];
              if (note) answers.notes = (answers.notes ? answers.notes + "; " : "") + note;
              i++; next();
            }
          });
        }
        function review() {
          var costs = (ME && ME.costs) || { brief: 5 };
          var lines = ids.filter(function (id) { return byId[id] && answers[id] && answers[id].length; }).map(function (id) {
            var v = answers[id]; return (byId[id].label.replace(/\?$/, "")) + ": " + (Array.isArray(v) ? v : [v]).map(function (x) { return optionLabel(byId[id], x); }).join(", ");
          });
          say("Here's your brief:\n" + lines.join("\n"));
          var list = [];
          if (!attach && selToken()) {
            // They are on a selection: score it against these answers (free), or start a separate list.
            chips([{ label: "Score this selection · free", primary: true, go: function () { scoreSelection(selToken(), answers); } },
                   { label: "Build a separate new shortlist" + (ME && ME.ai ? " · " + costs.brief + " credits" : ""), go: function () { if (ME && ME.ai) build(answers); else handoff("handoff", "Brief from the chat:\n" + lines.join("\n")); } },
                   { label: "Change answers", ghost: true, go: function () { flowFind(text); } }]);
            return;
          }
          if (attach) {
            chips([{ label: "Score “" + (mode.name || "this selection") + "” · free", primary: true, go: function () { scoreSelection(attach, answers); } },
                   { label: "Change answers", ghost: true, go: function () { flowFind("", mode); } }]);
            return;
          }
          if (ME && ME.ai) list.push({ label: "Build my shortlist · " + costs.brief + " credits", primary: true, go: function () { build(answers); } });
          list.push({ label: "Change answers", ghost: true, go: function () { flowFind(text); } });
          if (!(ME && ME.ai)) list.push({ label: "Send it to my account manager", primary: true, go: function () { handoff("handoff", "Brief from Voice:\n" + lines.join("\n")); } });
          chips(list);
        }
        next();
      });
    }
    function scoreSelection(token, answers) {
      say("Scoring every creator in it against your brief…");
      api("POST", "/api/brief/attach", { token: token, answers: answers }).then(function (r) {
        if (!r.b.ok) { say(r.b.reason === "missing" ? "A required answer is missing. Let's go through it again." : "That didn't work. Please try again."); chips([{ label: "Try again", go: function () { flowFind("", { attach: token }); } }]); return; }
        var picks = r.b.picks || [];
        say("Done. Every creator now has a score out of 100 for this brief." + (picks.length ? " Best fit: " + picks.slice(0, 3).map(function (p) { return ((p.creator && p.creator.name) || p.code) + " (" + p.score + ")"; }).join(", ") + "." : ""));
        queue = queue.then(function () { creatorCards(picks.slice(0, 8).map(function (p) { var c = Object.assign({ code: p.code, name: p.code }, p.creator || {}); c.fit = p.score; return c; })); });
        chips([{ label: "Show the scores on this page", primary: true, echo: false, go: function () { location.reload(); } },
               { label: "Why do the top creators fit?", go: function () { ta.value = "Why do the top creators in this selection fit my brief?"; submit(); } }]);
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
    var picked = [];                      // codes added from the chat's cards
    function drawPicks() {
      picksBar.innerHTML = "";
      if (!picked.length) { picksBar.hidden = true; return; }
      picksBar.hidden = false;
      picksBar.appendChild(h("span", { class: "hv-picks__n" }, picked.length + " added"));
      picksBar.appendChild(h("button", { class: "hv-picks__save", type: "button", onclick: savePicks }, "Save as a selection"));
      picksBar.appendChild(h("button", { class: "hv-picks__clear", type: "button", "aria-label": "Clear the added creators", onclick: function () {
        picked = []; drawPicks(); log.querySelectorAll(".hv-card__add").forEach(function (b) { b.setAttribute("aria-pressed", "false"); });
      } }, "Clear"));
    }
    function savePicks() {
      if (!picked.length) return;
      var codes = picked.slice();
      api("POST", "/api/selection", { name: "Chat shortlist", codes: codes }).then(function (r) {
        if (!r.b.ok) { say("I couldn't save that just now. Please try again."); return; }
        picked = []; drawPicks();
        log.querySelectorAll(".hv-card__add").forEach(function (b) { b.setAttribute("aria-pressed", "false"); });
        say("Saved " + codes.length + " creator" + (codes.length === 1 ? "" : "s") + " as “Chat shortlist”.");
        chips([{ label: "Open the selection", primary: true, echo: false, go: function () { location.href = ROOT + "selection/#s=" + encodeURIComponent(r.b.token); } },
               { label: "Get a quote for it", go: function () { quoteFor({ name: "Chat shortlist", token: r.b.token, codes: codes }); } }]);
      });
    }
    function togglePick(code, btn) {
      var k = picked.indexOf(code);
      if (k > -1) picked.splice(k, 1); else picked.push(code);
      log.querySelectorAll('.hv-card__add[data-code="' + code + '"]').forEach(function (b) { b.setAttribute("aria-pressed", String(k === -1)); });
      drawPicks();
    }
    function openProfile(c) {
      var card = document.querySelector('.cat-card[data-code="' + c.code + '"]');
      var pp = card && card.querySelector("a.cat-card__analysis[data-analysis]");      // opens the side panel over the roster
      if (pp) { pp.click(); return; }
      window.open(ROOT + "creator/#c=" + encodeURIComponent(c.code), "_blank", "noopener");
    }
    function creatorCards(list, keep) {
      if (!list || !list.length) return;
      if (keep !== false) { msgs.push({ from: "cards", list: list.map(function (c) { return { code: c.code, name: c.name, photo_url: c.photo_url, fit: c.fit, followers: c.followers, city: c.city, tier: c.tier }; }) }); save(); }
      var wrap = h("div", { class: "hv-cards", role: "list", "aria-label": "Creators" });
      list.forEach(function (c) {
        var ph = h("span", { class: "hv-card__photo" }); bg(ph, c.photo_url);
        if (c.fit != null) ph.appendChild(h("span", { class: "hv-card__fit" }, String(c.fit)));
        var open = h("button", { class: "hv-card__open", type: "button", "aria-label": "Open " + c.name + "'s profile" }, ph,
          h("span", { class: "hv-card__txt" }, h("b", null, c.name),
            h("span", null, [c.tier, c.followers ? followers(c.followers) : "", c.city].filter(Boolean).join(" · "))));
        open.addEventListener("click", function () { openProfile(c); });
        var add = h("button", { class: "hv-card__add", type: "button", "data-code": c.code, "aria-pressed": String(picked.indexOf(c.code) > -1),
                                "aria-label": "Add " + c.name + " to my shortlist" });
        add.innerHTML = V_ICON.plus + "<span>Add</span>" + V_ICON.check.replace("<svg", '<svg class="hv-card__ok"') + "<span class=\"hv-card__added\">Added</span>";
        add.addEventListener("click", function () { togglePick(c.code, add); });
        wrap.appendChild(h("div", { class: "hv-card", role: "listitem" }, open, add));
      });
      log.appendChild(wrap); scroll();
      lastCards = list;
    }
    var lastCards = [];

    /* -- 2. show creators on this page: a sentence becomes the page's filters -- */
    function flowShow() {
      askFor("Describe who you'd like to see, e.g. “micro skincare creators in Jeddah on TikTok”.", "Who should I show?", runShow);
    }
    function runShow(text) {
        api("POST", "/api/discover/parse", { text: text }).then(function (r) {
          var p = (r.b && r.b.filters) || {};
          var done = applyFilters(p);
          if (!done.length) { say("I couldn't pick out filters from that. Try naming a platform, city, size or topic."); chips([{ label: "Try again", go: flowShow }, { label: "Back to the menu", ghost: true, go: function () { menu("What would you like to do?"); } }]); return; }
          var shown = Array.prototype.filter.call(document.querySelectorAll(".cat-card"), function (c) { return !c.hidden && !c.classList.contains("cat-card--copy"); }).length;
          say("Done. The page now shows " + done.join(", ") + ". " + (shown ? shown + " creator" + (shown === 1 ? "" : "s") + " match." : "Nobody matches all of that yet, so try loosening one filter."));
          chips([{ label: "Clear the filters", go: function () { clearFilters(); nextUp("Filters cleared. You're seeing the whole roster again."); } },
                 { label: "Build a scored shortlist instead", go: function () { flowFind(text); } },
                 { label: "Close chat", ghost: true, echo: false, go: function () { toggle(false); } }]);
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
               { label: "Done", ghost: true, go: function () { nextUp("Anything else?"); } }]);
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
            nextUp(r.b.ok ? "Requested. The team will add " + c.name + "'s full analysis and you'll see it on their card." : "That request didn't go through. Please try again.");
          });
        } });
      });
      list.push({ label: "Done", ghost: true, go: function () { nextUp("Anything else?"); } });
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
        nextUp("Anything else?");
      });
    }

    /* -- a calculated answer: how it was worked out, per creator, on tap -- */
    function breakdown(b) {
      var pct = /%/.test(b.label), money = /SAR/.test(b.label);
      function fmt(v) { return pct ? (Math.round(v * 10) / 10) + "%" : money ? "SAR " + money_(v) : followers(v); }
      function money_(v) { return Math.round(v).toLocaleString("en-US"); }
      var box = h("details", { class: "hv-msg hv-msg--ai hv-break" });
      box.appendChild(h("summary", null, "See breakdown · " + b.covered + " of " + b.of + " creators"));
      var ol = h("ol", { class: "hv-break__list" });
      b.rows.forEach(function (r) { ol.appendChild(h("li", null, h("span", null, r.name), h("b", null, fmt(r.value)))); });
      box.appendChild(ol);
      var how = (b.label.replace(/\s*\(.*\)/, "")) + ": " + (b.total != null ? "total " + fmt(b.total) + " · " : "") + "average " + fmt(b.average) +
                " across the " + b.covered + " creator" + (b.covered === 1 ? "" : "s") + " with figures on their analysis page.";
      box.appendChild(h("p", { class: "hv-break__how" }, how));
      if (b.missing && b.missing.length) box.appendChild(h("p", { class: "hv-break__miss" }, "No analysis yet: " + b.missing.join(", ") + "."));
      row("ai", box);
    }

    /* -- after an answer: the likely next asks, one tap each -- */
    function followUps(list) {
      var acts = { "Find creators": flowFind, "Find creators within my budget": flowFind, "Get a quote": flowQuote,
                   "Talk to a person": flowHuman,
                   "Save all as a selection": function () { (lastCards || []).forEach(function (c) { if (picked.indexOf(c.code) === -1) picked.push(c.code); }); drawPicks(); savePicks(); } };
      chips((list || []).map(function (label) {
        return acts[label] ? { label: label, go: acts[label] } : { label: label, echo: false, go: function () { ta.value = label; submit(); } };
      }), { hint: "Suggested next · or type below" });
    }

    /* -- streamed answers: one JSON object per line -- */
    function stream(path, body, onEvent) {
      return fetch(API + path, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
        .then(function (r) {
          var type = r.headers.get("Content-Type") || "";
          if (!r.ok || type.indexOf("ndjson") === -1 || !r.body || !r.body.getReader) {
            return r.json().catch(function () { return {}; }).then(function (b) {
              if (r.ok && b && b.t) { onEvent(b); return; }
              onEvent({ t: "error", status: r.status, message: (b && b.message) || "", reason: b && b.reason });
            });
          }
          var reader = r.body.getReader(), dec = new TextDecoder(), buf = "";
          function pump() {
            return reader.read().then(function (res) {
              if (res.done) { if (buf.trim()) try { onEvent(JSON.parse(buf)); } catch (e) { /* cut */ } return; }
              buf += dec.decode(res.value, { stream: true });
              var lines = buf.split("\n"); buf = lines.pop();
              lines.forEach(function (l) { if (l.trim()) try { onEvent(JSON.parse(l)); } catch (e) { /* skip */ } });
              return pump();
            });
          }
          return pump();
        })
        .catch(function () { onEvent({ t: "error", status: 0, message: "Could not reach the server. Please try again." }); });
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
      if (/\bquot(e|ation)|عرض سعر|تسعير/i.test(text)) { flowQuote(); return; }
      if (!selToken() && /my selection|my shortlist|\b(add|remove|rename|compare)\b|قائمتي/i.test(text)) { flowSelection(); return; }
      if (document.querySelector(".cat-bar") && /^(show|filter|only|display|اعرض|أظهر)\b/i.test(text)) { runShow(text); return; }
      // On a selection's page the client is discussing THAT selection: the assistant answers with its
      // brief and scores. Only elsewhere does a campaign description start the free find-creators taps.
      if (!selToken() && REQ.test(text) && !/how much|price|cost/i.test(text)) { flowFind(text); return; }
      if (!(ME && ME.ai)) { say("I can't answer typed questions on this access yet. Tap an option, or I can pass your question to your account manager."); chips([{ label: "Send it to my account manager", primary: true, go: function () { handoff("handoff", text); } }, { label: "Show the menu", ghost: true, go: function () { menu(); } }]); return; }
      busy = true; send.disabled = true;
      // While it works: what it is doing right now, then the answer as it is written.
      var work = h("div", { class: "hv-msg hv-msg--ai hv-work", "aria-label": "The assistant is working" },
        h("span", { class: "hv-work__dots", "aria-hidden": "true" }, h("i"), h("i"), h("i")), h("ol", { class: "hv-work__steps" }));
      var workRow = row("ai", work), out = null, ty = null, acc = "", ended = false;
      function step(label) {
        var ol = work.querySelector(".hv-work__steps");
        ol.querySelectorAll("li:not(.is-done)").forEach(function (li) { li.classList.add("is-done"); });
        var li = h("li", null, label + "…"); ol.appendChild(li); scroll();
      }
      function stop() { busy = false; send.disabled = false; ended = true; }
      stream("/api/chat/stream", { message: text, thread: thread, selection: selToken() || undefined }, function (ev) {
        if (ev.t === "step") { step(ev.text); return; }
        if (ev.t === "delta") {
          if (!out) { workRow.remove(); out = h("div", { class: "hv-msg hv-msg--ai" }); row("ai", out); ty = typer(out); }
          acc += ev.text; ty.push(ev.text);
          return;
        }
        if (ev.t === "done") {
          stop();
          if (!out) { workRow.remove(); out = h("div", { class: "hv-msg hv-msg--ai" }); row("ai", out); ty = typer(out); }
          msgs.push({ from: "ai", text: ev.reply }); thread = ev.thread || thread; save();
          if (ev.credits != null) { setCredits(ev.credits); refreshFoot(); }
          // Cards and next steps follow once the answer has finished typing.
          ty.end(ev.reply, function () {
            if (ev.breakdown && ev.breakdown.rows && ev.breakdown.rows.length) breakdown(ev.breakdown);
            if (ev.cards && ev.cards.length) creatorCards(ev.cards);
            followUps(ev.next);
          });
          return;
        }
        if (ev.t === "error") {
          stop(); workRow.remove();
          if (out && ty) ty.end(acc);
          if (ev.reason === "no_credits") { say(ev.message || "You're out of AI credits."); chips([{ label: "Talk to a person", go: flowHuman }]); return; }
          say(ev.status === 429 ? "One moment, that was quick. Try again in a few seconds." : (ev.message || "That didn't work, and you weren't charged."));
          if (ev.credits != null) { setCredits(ev.credits); refreshFoot(); }
        }
      }).then(function () { if (!ended) { stop(); if (!out) workRow.remove(); } });
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
          if (msgs.length) {
            thread = (kept && kept.thread) || thread;
            msgs.forEach(function (m) { if (m.from === "cards") creatorCards(m.list, false); else bubble(m.from, m.text, false); });
            log.appendChild(h("p", { class: "hv-sep" }, "Earlier in this chat"));
            if (selToken()) aboutSelection(); else menu("Welcome back. What would you like to do?");
          }
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
    minBtn.addEventListener("click", function () { toggle(false); });
    // The account page's "Message your account manager" opens straight onto the hand-off.
    HV.talk = function () { toggle(true); setTimeout(flowHuman, 400); };
    freshBtn.addEventListener("click", function () {
      msgs = []; thread = null; save(); expecting = null; ta.placeholder = "Type a message…"; ta.value = ""; grow();
      picked = []; drawPicks(); log.innerHTML = ""; queue = Promise.resolve(); greet();
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && root.classList.contains("is-open")) toggle(false); });

    /* -- bigger window -- */
    var BIG = "hv-chat-big";
    function setBig(on) {
      root.classList.toggle("is-big", on);
      growBtn.setAttribute("aria-pressed", String(on));
      growBtn.setAttribute("aria-label", on ? "Make the chat smaller" : "Make the chat bigger");
      growBtn.innerHTML = on ? V_ICON.shrink : V_ICON.grow;
      try { localStorage.setItem(BIG, on ? "1" : "0"); } catch (e) { /* private */ }
      scroll();
    }
    growBtn.addEventListener("click", function () { setBig(!root.classList.contains("is-big")); });
    try { if (localStorage.getItem(BIG) === "1") setBig(true); } catch (e) { /* private */ }

    /* -- speak instead of typing: the words land in the box to check, then Send -- */
    if (mic) {
      var rec = null, base = "";
      mic.addEventListener("click", function () {
        if (rec) { rec.stop(); return; }
        rec = new Speech();
        rec.lang = /[\u0600-\u06FF]/.test(ta.value) || /^ar/i.test(document.documentElement.lang || navigator.language || "") ? "ar-SA" : (navigator.language || "en-US");
        rec.interimResults = true; rec.continuous = false;
        base = ta.value ? ta.value.replace(/\s*$/, " ") : "";
        mic.classList.add("is-on"); mic.setAttribute("aria-pressed", "true"); ta.placeholder = "Listening…";
        rec.onresult = function (e) {
          var said = ""; for (var k = 0; k < e.results.length; k++) said += e.results[k][0].transcript;
          ta.value = base + said; grow();
          ta.dispatchEvent(new Event("input"));
        };
        rec.onend = rec.onerror = function () {
          mic.classList.remove("is-on"); mic.setAttribute("aria-pressed", "false"); rec = null;
          if (!expecting) ta.placeholder = "Type a message…";
          ta.focus();
        };
        try { rec.start(); } catch (e) { rec = null; mic.classList.remove("is-on"); }
      });
    }

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

  /* ---------------------------------------------------- AI shortlist card */
  // "Build a shortlist with AI": a card beside the catalogue's filters. Six
  // taps fill a brief (free), the server scores the whole roster, and the grid
  // narrows to the picks, best first, each with one score per platform. The
  // wait is staged: the character scouts with his camera while named steps
  // tick off, so the client watches their campaign list being made.

  var AI_STEPS = [
    ["goal", "Goal", '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r=".6" fill="currentColor"/>'],
    ["platforms", "Platforms", '<rect x="7" y="3" width="10" height="18" rx="2.5"/><path d="M11 17.5h2"/>'],
    ["market", "Audience", '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.6 2.6 2.6 14.4 0 17M12 3.5c-2.6 2.6-2.6 14.4 0 17"/>'],
    ["category", "Space", '<path d="M3.5 12.5l8-8h7v7l-8 8z"/><circle cx="15" cy="9" r="1.3"/>'],
    ["budget", "Budget", '<rect x="3.5" y="6.5" width="17" height="12" rx="2.5"/><path d="M15.5 12.5h2.5M3.5 10h17"/>'],
    ["count", "Creators", '<circle cx="9" cy="8.5" r="3"/><circle cx="16.5" cy="9.5" r="2.4"/><path d="M3.5 19c.5-3 2.7-4.6 5.5-4.6s5 1.6 5.5 4.6M15 14.6c2.6 0 4.6 1.4 5 4.4"/>']
  ];
  var AI_SHORT = { Instagram: "IG", TikTok: "TT", Snapchat: "SC", YouTube: "YT" };
  var AI_MARKET = { SA: "KSA", AE: "UAE", EG: "Egypt", KW: "Kuwait", QA: "Qatar", BH: "Bahrain", OM: "Oman", JO: "Jordan" };
  var AI_GOAL = { awareness: "Reach", engagement: "Engagement", conversion: "Sales", balanced: "Balanced" };
  function aiSvg(path, size) {
    return '<svg viewBox="0 0 24 24" width="' + (size || 20) + '" height="' + (size || 20) + '" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + path + "</svg>";
  }

  function mountAiCard() {
    if (document.body.getAttribute("data-page") !== "catalogue" || $("ai-sl")) return;
    var tries = 0;
    (function wait() {
      var host = document.querySelector(".cat-controls .cat-container");
      if (host && host.querySelector(".cat-bar")) return buildAiCard(host);
      if (++tries < 60) setTimeout(wait, 250);
    })();
  }

  // Setup above, results below: the client-logo band moves above the setup, the setup
  // gets its own heading and frame, and the roster opens with a Results header.
  function frameSetup(host) {
    var controls = host.closest(".cat-controls"), clients = document.querySelector(".cat-clients"), grid = $("cat-grid");
    if (!controls || controls.classList.contains("is-setup")) return;
    if (clients && controls.compareDocumentPosition(clients) & Node.DOCUMENT_POSITION_FOLLOWING) controls.parentNode.insertBefore(clients, controls);
    controls.classList.add("is-setup");
    var head = h("div", { class: "setup-head" });
    head.innerHTML = '<h2 class="setup-head__title">Find your creators</h2>' +
      '<p class="setup-head__sub">Filter the roster yourself, or let AI build the list. Your results open just below.</p>';
    host.insertBefore(head, host.firstChild);
    if (grid && !$("results-head")) {
      var rh = h("div", { id: "results-head", class: "results-head" });
      rh.innerHTML = '<h2 class="results-head__title">Results</h2><p class="results-head__sub" id="results-sub">Every creator that matches your filters. Tick the ones you want.</p>';
      // Above the roster's own count/sort row when there is one, so "Results" opens the section.
      var bar = grid.previousElementSibling, anchor = bar && bar.classList.contains("cat-results") ? bar : grid;
      grid.parentNode.insertBefore(rh, anchor);
    }
  }
  function buildAiCard(host) {
    frameSetup(host);
    var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
    var V = ROOT + "assets/brand/voice/";
    host.classList.add("ai-host");
    var card = h("section", { id: "ai-sl", class: "ai-sl", "aria-labelledby": "ai-sl-title" });
    var roster = document.querySelectorAll(".cat-card").length;
    function loop(name) {
      return reduce ? '<img src="' + V + 'voice-loop-poster.webp" alt="" width="120" height="120"/>'
        : '<video muted loop playsinline autoplay preload="metadata" poster="' + V + 'voice-loop-poster.webp" aria-hidden="true">' +
          '<source src="' + V + name + '.webm" type="video/webm"/><source src="' + V + name + '.mp4" type="video/mp4"/></video>';
    }

    // Collapsed: the invitation.
    var intro = h("div", { class: "ai-sl__intro" });
    intro.innerHTML = '<div class="ai-sl__face">' + loop("voice-loop") + "</div>" +
      '<div class="ai-sl__copy"><h2 class="ai-sl__title" id="ai-sl-title">Build a shortlist with AI</h2>' +
      "<p>Six quick taps. We score every creator in the roster against your campaign and pick the best.</p></div>";
    var start = h("button", { class: "ai-sl__start", type: "button" }, "Start");
    start.insertAdjacentHTML("beforeend", aiSvg('<path d="M5 12h13M13 6l6 6-6 6"/>', 18));
    intro.appendChild(start);

    // Expanded: the journey.
    var run = h("div", { class: "ai-sl__run", hidden: "" });
    var head = h("div", { class: "ai-sl__head" });
    var level = h("p", { class: "ai-sl__level", "aria-live": "polite" });
    var quit = h("button", { class: "ai-sl__quit", type: "button", "aria-label": "Close the AI shortlist" });
    quit.innerHTML = aiSvg('<path d="M6 6l12 12M18 6L6 18"/>', 18);
    var track = h("ol", { class: "ai-sl__track", "aria-label": "Brief progress" });
    AI_STEPS.forEach(function (s, i) {
      var li = h("li", { class: "ai-sl__node", "data-i": String(i) });
      li.innerHTML = '<span class="ai-sl__dot">' + aiSvg(s[2], 18) + '<i class="ai-sl__tick">' + aiSvg('<path d="M5 12.5l4.2 4.2L19 7"/>', 16) + "</i></span><span class=\"ai-sl__lbl\">" + s[1] + "</span>";
      track.appendChild(li);
    });
    var fill = h("span", { class: "ai-sl__fill", "aria-hidden": "true" });
    track.appendChild(fill);
    head.appendChild(track); head.appendChild(level); head.appendChild(quit);
    var stage = h("div", { class: "ai-sl__stage" });
    // The coach: the character reacts to every step (points at a new question, thinks
    // while you choose, thumbs-up on an answer, cheers at the end), over a power meter.
    var coach = h("div", { class: "ai-sl__coach", "aria-hidden": "true" });
    // Each reaction is a fresh video element laid over the last one, which is removed once the
    // new one is drawing. Re-using one element (swapping its source, or hiding and showing
    // several) left blank or half-painted frames in Chrome.
    var cring = h("div", { class: "ai-sl__cring" });
    // Trimmed to the action itself, so a reaction starts the instant the client taps.
    var CLIP = { point: "voice-point-act", think: "voice-think-act", thumbs: "voice-thumbs-act", cheer: "voice-cheer-act", wave: "voice-loop" };
    var IDLE = { think: 1, wave: 1 };
    var power = h("div", { class: "ai-sl__power" });
    power.innerHTML = '<p class="ai-sl__pw-h">Campaign power</p><p class="ai-sl__pw-n"><b>0</b><small> / ' + 1000 + '</small></p>' +
      '<div class="ai-sl__pw-bar"><i></i></div><p class="ai-sl__pw-lvl">Draft</p>';
    coach.appendChild(cring); coach.appendChild(power);
    var main = h("div", { class: "ai-sl__main" });
    main.appendChild(head); main.appendChild(stage);
    run.appendChild(coach); run.appendChild(main);
    card.appendChild(intro); card.appendChild(run);
    host.appendChild(card);

    var qs = null, byId = {}, answers = {}, step = 0, busy = false, last = null;

    /* -- the game layer: coach animations and campaign power -- */
    // The coach: idle poses loop; reactions (thumbs, cheer, point) play once, in full, then hand
    // over to whatever is waiting, so a tap is always answered before the next pose.
    var coachTimer = null, reacting = false, queued = null;
    function coachShow(kind, loop, onEnd) {
      var v = document.createElement("video");
      v.className = "ai-sl__cvid"; v.muted = true; v.loop = !!loop; v.autoplay = true;
      v.setAttribute("muted", ""); v.setAttribute("playsinline", ""); v.setAttribute("aria-hidden", "true");
      v.innerHTML = '<source src="' + V + CLIP[kind] + '.webm" type="video/webm"/><source src="' + V + CLIP[kind] + '.mp4" type="video/mp4"/>';
      var old = [].slice.call(cring.querySelectorAll("video"));
      var swap = function () { old.forEach(function (o) { o.remove(); }); };
      v.addEventListener("playing", swap, { once: true });
      setTimeout(swap, 900);
      if (onEnd) { v.addEventListener("ended", onEnd, { once: true }); coachTimer = setTimeout(onEnd, 3200); }
      cring.appendChild(v);
      var pr = v.play(); if (pr && pr.catch) pr.catch(function () { /* autoplay blocked: last frame stays */ });
    }
    function coachPlay(kind, then) {
      if (reduce) return;
      clearTimeout(coachTimer);
      if (IDLE[kind]) { reacting = false; queued = null; coachShow(kind, true); return; }
      reacting = true; queued = then || "think";
      cring.classList.remove("is-bump"); void cring.offsetWidth; cring.classList.add("is-bump");
      var done = false;
      coachShow(kind, false, function () {
        if (done) return; done = true; clearTimeout(coachTimer);
        reacting = false;
        var next = queued; queued = null;
        if (next === "point") coachPlay("point", "think"); else coachPlay(next || "think");
      });
    }
    // A new question asks for a point, unless the coach is still celebrating: then it waits its turn.
    function coachCue(kind) { if (reacting) queued = kind; else coachPlay(kind, "think"); }
    function coachSay(text) {
      if (reduce) return;
      var b = h("span", { class: "ai-sl__say" }, text);
      cring.parentNode.appendChild(b); setTimeout(function () { b.remove(); }, 1500);
    }
    // A complete brief is worth exactly 1000: every answered question counts in full,
    // whatever was picked (one platform or three, "not decided yet" included).
    var POINTS = { goal: 150, platforms: 150, market: 150, category: 250, budget: 150, count: 150 };
    var LEVELS = [[0, "Draft"], [250, "Focused"], [500, "Sharp"], [800, "Ready to launch"]];
    function scoreOf(id) {
      var v = answers[id];
      if (v == null || (Array.isArray(v) && !v.length)) return 0;
      return POINTS[id] || 0;
    }
    function powerNow() { return AI_STEPS.reduce(function (t, s) { return t + scoreOf(s[0]); }, 0); }
    function levelOf(n) { var l = LEVELS[0][1]; LEVELS.forEach(function (x) { if (n >= x[0]) l = x[1]; }); return l; }
    var shown = 0;
    function paintPower(gain) {
      var n = Math.min(1000, powerNow()), before = levelOf(shown);
      power.querySelector("b").textContent = n;
      power.querySelector(".ai-sl__pw-bar i").style.width = (n / 10) + "%";
      var lvl = levelOf(n);
      power.querySelector(".ai-sl__pw-lvl").textContent = lvl;
      var leveled = !!(gain && lvl !== before);
      if (leveled) {
        var up = h("span", { class: "ai-sl__lvlup" }, "Level up · " + lvl);
        power.appendChild(up); setTimeout(function () { up.remove(); }, 1800);
      }
      if (gain && n > shown) { power.classList.remove("is-gain"); void power.offsetWidth; power.classList.add("is-gain"); }
      shown = n;
      return leveled;
    }
    // Every answer gets a reaction: a thumbs-up and the points, or a cheer on a level-up.
    function reward(pts) {
      var leveled = paintPower(true);
      coachSay(leveled ? "Level up!" : "+" + pts);
      coachPlay(leveled ? "cheer" : "thumbs", "think");
    }

    function setTrack(at, done) {
      Array.prototype.forEach.call(track.querySelectorAll(".ai-sl__node"), function (n, i) {
        n.classList.toggle("is-done", i < at || !!done);
        n.classList.toggle("is-now", i === at && !done);
      });
      var pct = done ? 100 : Math.round(at / (AI_STEPS.length - 1) * 100);
      fill.style.setProperty("--p", pct + "%");
      level.innerHTML = done ? "<b>Brief</b> complete" : "<b>Brief " + Math.min(at + 1, AI_STEPS.length) + "</b> / " + AI_STEPS.length;
    }
    function open() {
      card.classList.add("is-open"); intro.hidden = true; run.hidden = false; run.classList.remove("is-staging");
      shown = 0;
      loadQuestions().then(function (list) {
        qs = list; byId = {}; qs.forEach(function (q) { byId[q.id] = q; });
        ask(0);
      });
    }
    function close() {
      card.classList.remove("is-open"); run.hidden = true; intro.hidden = false;
    }
    start.addEventListener("click", function () { answers = {}; open(); });
    quit.addEventListener("click", close);

    function swap(node) {
      stage.innerHTML = "";
      node.classList.add("ai-sl__panel");
      stage.appendChild(node);
      var f = node.querySelector("button, input");
      if (f) f.focus({ preventScroll: true });
    }
    function ask(i) {
      step = i; setTrack(i); paintPower(false);
      coachCue("point");
      var id = AI_STEPS[i][0], q = byId[id];
      if (!q) return i + 1 < AI_STEPS.length ? ask(i + 1) : review();
      var many = q.type === "many";
      var picked = Array.isArray(answers[id]) ? answers[id].slice() : [];
      var p = h("div", { class: "ai-sl__q" });
      p.appendChild(h("p", { class: "ai-sl__ask" }, q.label));
      p.appendChild(h("p", { class: "ai-sl__hint" }, many ? "Pick any, then Next" : "Tap one"));
      var opts = h("div", { class: "ai-sl__opts" + (q.options.length > 6 ? " ai-sl__opts--many" : "") });
      q.options.forEach(function (o) {
        var on = many ? picked.indexOf(o.value) > -1 : answers[id] === o.value;
        var b = h("button", { class: "ai-sl__opt", type: "button", "aria-pressed": String(on) }, o.label);
        b.addEventListener("click", function () {
          if (!many) { answers[id] = o.value; b.setAttribute("aria-pressed", "true"); pop(b, scoreOf(id)); reward(scoreOf(id)); setTimeout(function () { next(); }, reduce ? 0 : 750); return; }
          var k = picked.indexOf(o.value);
          if (o.value === "any") picked = k > -1 ? [] : ["any"];
          else { picked = picked.filter(function (v) { return v !== "any"; }); if (k > -1) picked.splice(picked.indexOf(o.value), 1); else picked.push(o.value); }
          Array.prototype.forEach.call(opts.children, function (x, xi) { x.setAttribute("aria-pressed", String(picked.indexOf(q.options[xi].value) > -1)); });
          nextBtn.disabled = !picked.length;
        });
        opts.appendChild(b);
      });
      p.appendChild(opts);
      var nav = h("div", { class: "ai-sl__nav" });
      if (i > 0) nav.appendChild(h("button", { class: "ai-sl__back", type: "button", onclick: function () { ask(i - 1); } }, "Back"));
      if (!q.required && !many) nav.appendChild(h("button", { class: "ai-sl__skip", type: "button", onclick: function () { delete answers[id]; next(); } }, "Skip"));
      var nextBtn = h("button", { class: "ai-sl__next", type: "button", onclick: function () { answers[id] = picked.slice(); pop(nextBtn, scoreOf(id)); reward(scoreOf(id)); setTimeout(next, reduce ? 0 : 750); } }, "Next");
      if (many) { nextBtn.disabled = !picked.length; nav.appendChild(nextBtn); }
      p.appendChild(nav);
      swap(p);
      function next() { if (i + 1 < AI_STEPS.length) ask(i + 1); else review(); }
    }
    function pop(el, pts) {
      if (reduce) return;
      var s = h("span", { class: "ai-sl__plus", "aria-hidden": "true" }, "+" + (pts || 100));
      el.appendChild(s); setTimeout(function () { s.remove(); }, 700);
    }
    function label(id) {
      var v = answers[id], q = byId[id];
      if (v == null || (Array.isArray(v) && !v.length)) return "Any";
      return (Array.isArray(v) ? v : [v]).map(function (x) { return optionLabel(q, x); }).join(", ");
    }
    function nameFor() {
      var cat = Array.isArray(answers.category) && answers.category[0] && answers.category[0] !== "any" ? optionLabel(byId.category, answers.category[0]).split(/ [&\/] /)[0] : "Creators";
      return [cat, AI_MARKET[answers.market] || "", AI_GOAL[answers.goal] || ""].filter(Boolean).join(" · ");
    }
    function costLine() {
      var c = (ME && ME.costs) || { brief: 5, search: 0 };
      if (ME && ME.kind === "admin") return "Admin preview · free";
      if (ME && ME.ai && c.brief && (ME.credits == null || ME.credits >= c.brief)) return c.brief + " credits · includes AI reasons";
      return c.search ? c.search + " credits" : "Free";
    }
    function review() {
      setTrack(AI_STEPS.length, true);
      var p = h("div", { class: "ai-sl__review" });
      var ticket = h("div", { class: "ai-sl__ticket" });
      ticket.appendChild(h("p", { class: "ai-sl__tk-h" }, "Campaign brief"));
      paintPower(true); coachSay("Ready!"); coachPlay("cheer", "wave");
      var pw = Math.min(1000, powerNow());
      ticket.appendChild(h("span", { class: "ai-sl__tk-score" }, h("b", null, String(pw)), h("small", null, levelOf(pw))));
      var nameIn = h("input", { class: "ai-sl__name", type: "text", maxlength: "80", value: nameFor(), "aria-label": "Name this shortlist" });
      ticket.appendChild(nameIn);
      var dl = h("dl", { class: "ai-sl__rows" });
      AI_STEPS.forEach(function (s, i) {
        var row = h("div", { class: "ai-sl__row" });
        row.appendChild(h("dt", null, s[1]));
        row.appendChild(h("dd", null, label(s[0])));
        var edit = h("button", { class: "ai-sl__edit", type: "button", "aria-label": "Change " + s[1] }, "Change");
        edit.addEventListener("click", function () { ask(i); });
        row.appendChild(edit);
        dl.appendChild(row);
      });
      ticket.appendChild(dl);
      p.appendChild(ticket);
      var side = h("div", { class: "ai-sl__go" });
      side.appendChild(h("p", { class: "ai-sl__ask" }, "Ready when you are."));
      side.appendChild(h("p", { class: "ai-sl__hint" }, "We score every creator on each platform, fit your budget and explain each pick."));
      var build = h("button", { class: "ai-sl__build", type: "button" }, "Build my shortlist");
      build.appendChild(h("small", null, costLine()));
      build.addEventListener("click", function () { if (!busy) go(nameIn.value.trim() || nameFor()); });
      side.appendChild(build);
      p.appendChild(side);
      swap(p);
    }

    /* -- the wait, staged -- */
    var STAGES = ["Reading your brief", "Scoring every creator", "Fitting your budget", "Writing the reasons"];
    function go(name) {
      busy = true;
      run.classList.add("is-staging"); clearTimeout(coachTimer);
      [].slice.call(cring.querySelectorAll("video")).forEach(function (o) { try { o.pause(); } catch (e) { /* none */ } });
      var p = h("div", { class: "ai-sl__wait", role: "status", "aria-live": "polite" });
      var scene = h("div", { class: "ai-sl__scene", "aria-hidden": "true" });
      scene.innerHTML = '<div class="ai-sl__orbit ai-sl__orbit--a"><i></i><i></i><i></i></div>' +
        '<div class="ai-sl__orbit ai-sl__orbit--b"><i></i><i></i></div>' +
        '<div class="ai-sl__orbit ai-sl__orbit--c">' + ["Instagram", "TikTok", "Snapchat"].map(function (pl) {
          var ic = window.HV_ICONS && window.HV_ICONS.icons && window.HV_ICONS.icons[pl];
          return '<b class="ai-sl__mark ai-sl__mark--' + pl.toLowerCase() + '">' + (ic || '<em>' + AI_SHORT[pl] + "</em>") + "</b>";
        }).join("") + "</div>" +
        '<div class="ai-sl__lens">' + loop("voice-scan") + "</div>" +
        '<span class="ai-sl__spark ai-sl__spark--1"></span><span class="ai-sl__spark ai-sl__spark--2"></span><span class="ai-sl__spark ai-sl__spark--3"></span>';
      p.appendChild(scene);
      var side = h("div", { class: "ai-sl__steps" });
      side.appendChild(h("p", { class: "ai-sl__ask" }, "Building “" + name + "”"));
      var list = h("ol", { class: "ai-sl__list" });
      var counter = h("b", { class: "ai-sl__count" }, "0%");
      STAGES.forEach(function (t, i) {
        var li = h("li", { class: "ai-sl__st" }, h("span", { class: "ai-sl__st-dot", "aria-hidden": "true" }), h("span", null, t));
        if (i === 1) li.appendChild(counter);
        list.appendChild(li);
      });
      side.appendChild(list);
      var bar = h("div", { class: "ai-sl__bar", "aria-hidden": "true" }, h("i"));
      side.appendChild(bar);
      p.appendChild(side);
      swap(p);
      var items = list.children, total = Math.max(roster, 1), t0 = Date.now(), done = false, at = 0;
      function mark(i) {
        Array.prototype.forEach.call(items, function (li, k) { li.classList.toggle("is-done", k < i); li.classList.toggle("is-now", k === i); });
        at = i;
      }
      mark(0);
      var timer = setInterval(function () {
        var s = (Date.now() - t0) / 1000;
        if (!done) {
          if (s > 1.2 && at < 1) mark(1);
          if (at === 1) counter.textContent = Math.round(100 * Math.min(1, (s - 1.2) / 4)) + "%";   // progress, never the roster size
          if (s > 5.4 && at < 2) mark(2);
          if (s > 7.4 && at < 3) mark(3);
          bar.firstChild.style.width = Math.min(92, 8 + s * 4) + "%";
        }
      }, 120);
      api("POST", "/api/brief/run", { answers: answers, name: name }).then(function (r) {
        done = true; clearInterval(timer); busy = false;
        if (!r.b.ok || r.b.empty || !(r.b.picks || []).length) {
          var err = h("div", { class: "ai-sl__q" }, h("p", { class: "ai-sl__ask" }, r.b.empty ? "No creators matched that brief." : "That didn't work."),
            h("p", { class: "ai-sl__hint" }, (r.b.message || "Nothing was charged. Try again in a moment.")));
          err.appendChild(h("div", { class: "ai-sl__nav" }, h("button", { class: "ai-sl__next", type: "button", onclick: review }, "Change the brief")));
          swap(err); return;
        }
        counter.textContent = "100%";
        mark(STAGES.length); bar.firstChild.style.width = "100%";
        setCredits(r.b.credits);
        last = r.b;
        setTimeout(function () { celebrate(r.b, name); }, reduce ? 0 : 500);
      });
    }
    function celebrate(res, name) {
      var p = h("div", { class: "ai-sl__done" });
      var burst = h("div", { class: "ai-sl__burst", "aria-hidden": "true" });
      for (var i = 0; i < 18; i++) { var c = h("i"); c.style.setProperty("--a", (i * 20) + "deg"); c.style.setProperty("--d", (60 + (i % 3) * 26) + "px"); burst.appendChild(c); }
      p.appendChild(burst);
      if (!reduce) p.insertAdjacentHTML("beforeend", '<div class="ai-sl__cheer"><video muted autoplay playsinline loop>' +
        '<source src="' + V + 'voice-cheer.webm" type="video/webm"/><source src="' + V + 'voice-cheer.mp4" type="video/mp4"/></video></div>');
      p.appendChild(h("p", { class: "ai-sl__big" }, h("b", null, String(res.picks.length)), " creators picked"));
      p.appendChild(h("p", { class: "ai-sl__hint" }, "Best fit first, scored per platform. They're ticked in your tray: add or remove anyone, then save."));
      swap(p);
      showResult(res, name);
      setTimeout(function () {
        close();
        var bar = $("ai-result");
        if (bar) bar.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
      }, reduce ? 300 : 1900);
    }

    /* -- the grid, narrowed to the picks -- */
    function bandOf(n) { return n >= 80 ? "g" : n >= 60 ? "l" : n >= 40 ? "a" : "r"; }
    function clearResult() {
      var grid = $("cat-grid");
      if (grid) grid.classList.remove("ai-on");
      Array.prototype.forEach.call(document.querySelectorAll(".cat-card.ai-pick, .cat-card.ai-out"), function (c) {
        c.classList.remove("ai-pick", "ai-out"); c.style.order = "";
        var x = c.querySelector(".ai-badges"); if (x) x.remove();
      });
      var bar = $("ai-result"); if (bar) bar.remove();
      document.body.classList.remove("ai-mode");
      var sub = $("results-sub"); if (sub) sub.textContent = "Every creator that matches your filters. Tick the ones you want.";
    }
    function showResult(res, name) {
      clearResult();
      var grid = $("cat-grid");
      if (!grid) return;
      var rank = {}, why = {};
      res.picks.forEach(function (p, i) { rank[p.code] = i + 1; why[p.code] = p.why || ""; });
      grid.classList.add("ai-on");
      document.body.classList.add("ai-mode");
      Array.prototype.forEach.call(grid.querySelectorAll(".cat-card[data-code]"), function (c) {
        var code = c.getAttribute("data-code"), n = rank[code];
        if (!n) { c.classList.add("ai-out"); return; }
        c.classList.add("ai-pick"); c.style.order = String(n);
        var media = c.querySelector(".cat-card__media") || c;
        var box = h("div", { class: "ai-badges", "data-noselect": "" });
        box.appendChild(h("span", { class: "ai-rank", title: why[code] || "" }, "#" + n));
        var ps = (res.platform_scores || {})[code] || {};
        var plats = Object.keys(ps);
        if (!plats.length) { var only = res.picks[n - 1]; if (only && only.score != null) { ps = { Match: only.score }; plats = ["Match"]; } }
        plats.sort(function (a, b) { return ps[b] - ps[a]; }).forEach(function (pl) {
          var s = h("span", { class: "ai-pscore ai-pscore--" + bandOf(ps[pl]), title: pl + " match " + ps[pl] + " / 100" });
          s.appendChild(h("small", null, AI_SHORT[pl] || pl)); s.appendChild(h("b", null, String(ps[pl])));
          box.appendChild(s);
        });
        media.appendChild(box);
        if (c.getAttribute("aria-pressed") !== "true") c.click();
      });
      var bar = h("div", { id: "ai-result", class: "ai-result" });
      var txt = h("div", { class: "ai-result__txt" });
      txt.appendChild(h("p", { class: "ai-result__name" }, name));
      txt.appendChild(h("p", { class: "ai-result__sum" }, res.summary || (res.picks.length + " creators match your brief, best fit first.")));
      bar.appendChild(txt);
      var acts = h("div", { class: "ai-result__acts" });
      acts.appendChild(h("a", { class: "ai-result__btn ai-result__btn--lime", href: ROOT + "selection/#s=" + encodeURIComponent(res.token) }, "Open as selection"));
      acts.appendChild(h("a", { class: "ai-result__btn", href: ROOT + "selection/#s=" + encodeURIComponent(res.token) + "&quote=1" }, "Request a quote"));
      acts.appendChild(h("button", { class: "ai-result__btn ai-result__btn--ghost", type: "button", onclick: clearResult }, "Show all creators"));
      acts.appendChild(h("button", { class: "ai-result__btn ai-result__btn--ghost", type: "button", onclick: function () { clearResult(); answers = {}; open(); card.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" }); } }, "New brief"));
      bar.appendChild(acts);
      grid.parentNode.insertBefore(bar, grid);
      var sub = $("results-sub");
      if (sub) sub.textContent = "AI shortlist: " + res.picks.length + " creators, best fit first. Show all creators to go back to the full roster.";
    }
  }

  /* ------------------------------------------------------- licence stamps */
  // Advertising licences on the creator cards: Saudi Mawthooq, the UAE
  // Advertiser Permit, Egypt's SCMR licence. "In bio" is the creator's own
  // statement; "Verified" means HelloVoice checked it on the regulator's portal.
  var LIC = null, licObserver = null;
  var LIC_SHORT = { SA: "Mawthooq", AE: "UAE permit", EG: "Egypt licence" };
  function paintLicences() {
    if (!LIC) return;
    Array.prototype.forEach.call(document.querySelectorAll(".cat-card[data-code]"), function (card) {
      var list = LIC[card.getAttribute("data-code")];
      var box = card.querySelector(".lic-stamps");
      if (!list || !list.length) { if (box) box.remove(); return; }
      var sig = JSON.stringify(list);
      if (box && box.getAttribute("data-sig") === sig) return;
      if (!box) { box = h("div", { class: "lic-stamps", "data-noselect": "" }); (card.querySelector(".cat-card__media") || card).appendChild(box); }
      box.setAttribute("data-sig", sig);
      box.innerHTML = "";
      list.forEach(function (l) {
        // One white 'Verified' stamp for everyone with the licence.
        var st = h("span", { class: "lic-stamp", tabindex: "0",
          title: l.name + (l.number ? " no. " + l.number : ""),
          "aria-label": (LIC_SHORT[l.country] || l.name) + " licence, verified" });
        st.appendChild(h("b", null, LIC_SHORT[l.country] || l.name));
        st.appendChild(h("small", null, "Verified ✓"));
        box.appendChild(st);
      });
    });
  }
  // The licence filter: "License:" and two chips, Mawthooq (KSA) and UAE.
  // Pick one, both (either licence passes) or none (everyone). It works over
  // the catalogue's own filters: a card has to pass both. No counts are shown.
  var licWant = [];
  function licMatch(code) {
    if (!licWant.length) return true;
    var list = (LIC && LIC[code]) || [];
    return list.some(function (l) { return licWant.indexOf(l.country) !== -1; });
  }
  function applyLicFilter() {
    Array.prototype.forEach.call(document.querySelectorAll(".cat-card[data-code]"), function (card) {
      card.classList.toggle("lic-out", !licMatch(card.getAttribute("data-code")));
    });
  }
  function mountLicFilter(tries) {
    if (document.body.getAttribute("data-page") !== "catalogue" || $("lic-filter")) return;
    var bar = document.querySelector(".cat-controls .cat-bar");
    // The licences can arrive before the catalogue has drawn its filter bar: wait for it.
    if (!bar) { if ((tries || 0) < 80) setTimeout(function () { mountLicFilter((tries || 0) + 1); }, 250); return; }
    var box = h("div", { id: "lic-filter", class: "lic-filter", role: "group", "aria-label": "License" });
    box.appendChild(h("span", { class: "lic-filter__label" }, "License"));
    [["SA", "Mawthooq license"], ["AE", "UAE license"]].forEach(function (o) {
      var chip = h("button", { class: "lic-chip", type: "button", "aria-pressed": "false", "data-lic": o[0] }, o[1]);
      chip.addEventListener("click", function () {
        var i = licWant.indexOf(o[0]);
        if (i === -1) licWant.push(o[0]); else licWant.splice(i, 1);
        chip.setAttribute("aria-pressed", String(i === -1));
        applyLicFilter();
      });
      box.appendChild(chip);
    });
    bar.parentNode.insertBefore(box, bar.nextSibling);
  }
  function mountLicences() {
    var page = document.body.getAttribute("data-page");
    if (page !== "catalogue" && page !== "selection") return;
    api("GET", "/api/licences").then(function (r) {
      if (!r.b || !r.b.ok) return;
      LIC = r.b.licences || {};
      paintLicences();
      mountLicFilter();
      if (!licObserver && "MutationObserver" in window) {
        var t = null, app = document.getElementById("cat-grid") || document.body;
        licObserver = new MutationObserver(function () { clearTimeout(t); t = setTimeout(function () { paintLicences(); if (licWant.length) applyLicFilter(); }, 150); });
        licObserver.observe(app, { childList: true, subtree: true });
      }
    });
  }

  /* ------------------------------------------------------------------ boot */

  function boot() {
    api("GET", "/api/me").then(function (r) {
      if (r.b && r.b.signed_in) {
        ME = r.b; mountDock(); mountVoice(); mountAiCard(); mountLicences();
        var m = /[#&]s=([^&]+)/.exec(location.hash || "");
        if (document.body.getAttribute("data-page") === "selection" && m) setTimeout(function () { offerBrief(decodeURIComponent(m[1])); }, 1200);
        // Arriving from the AI shortlist's "Request a quote": open the quote form straight away.
        if (document.body.getAttribute("data-page") === "selection" && /[#&]quote=1/.test(location.hash)) setTimeout(function () {
          var q = document.getElementById("cat-request") || document.getElementById("cat-request-2"); if (q) q.click();
        }, 1600);
        if (storedBrief()) applyFit();
        return;
      }
      // Only replace the access-code gate once the server can actually send the email.
      if (r.b && r.b.email_signin) enhanceGate();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
  // A passcode typed into the gate unlocks without a reload, so look again
  // then: the account circle and the assistant appear straight away.
  document.addEventListener("cat:unlocked", function () { if (!ME) boot(); });
})();
