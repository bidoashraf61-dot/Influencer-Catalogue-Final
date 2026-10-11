/* HELVY Connect onboarding tour v3 (Bido, 2026-10-11, item 40).
 *
 * Loaded by connect.js only when a client starts the tour, never with the page.
 *
 * ONE CLIENT'S FIRST CAMPAIGN, from brief to results, played on the REAL portal pages inside a
 * frame: seven chapters, one action per step, one sentence per step, about three minutes.
 *   1 Brief          the AI shortlist card: several goals, several countries
 *   2 Shortlist      Helvy's picks, the fit score and how much data stands behind it
 *   3 Check a creator  open headline numbers, locked sections, the anonymised sample analysis
 *   4 Plan           the ROI calculator: how many creators, quality, the gap, ways to improve
 *   5 Ask Helvy      explain a score, compare creators, hand off to the account manager
 *   6 Quote          request it, the lifecycle chip, "Quote ready", the owner approves, live
 *   7 Follow         the campaign report (verdict, estimate vs actual) and the profile
 *
 * The demo world is a fixed, invented roster (assets/demo/demo-roster.json, written by
 * tools/gen_demo_roster.py): eight invented creators with realistic numbers drawn from the shape
 * of the real roster, on AI-generated portraits (assets/demo/). No real name, handle or photo is
 * in it, and nothing here reads the catalogue database. hv-loader.js, the first script on every
 * page, hands the frame to hvTourDemo.install() before any page script runs. From then on the
 * frame:
 *   - answers every /api/ call from the demo world below (nothing reaches the server, so nothing
 *     is saved and no AI or credit is used);
 *   - answers any other cross-origin call (the quote form's mail endpoint) with a harmless OK;
 *   - keeps its storage and cookies in memory (the client's real roster cache, chat history and
 *     preferences are never touched);
 *   - opens no outside link.
 * The only server calls the tour itself makes are POST /api/tour (offered / started / later /
 * done; +5 credits once, server-enforced) and one GET of the static roster file.
 */
(function () {
  "use strict";
  var HV = window.hvPortal || {};
  var ROOT = HV.root || "/";
  var REDUCE = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  var NOW = Math.floor(Date.now() / 1000), DAY = 86400;
  function iso(ts) { return new Date(ts * 1000).toISOString().slice(0, 10); }
  function photo(n) { return ROOT + "assets/demo/demo-" + n + ".webp"; }
  function clone(x) { return JSON.parse(JSON.stringify(x)); }
  function r1(x) { return Math.round(x * 10) / 10; }

  /* ================================================================== copy, EN and AR */
  // The portal is English only for now (the Arabic table is kept for later); the tour's copy
  // is ready in both, and follows the page language the day the portal switches it on.
  var IS_AR = typeof document !== "undefined" && /^ar/i.test(document.documentElement.getAttribute("lang") || "");
  var AR = {
    "Demo": "تجريبي", "Sample data · nothing you do here is saved": "بيانات تجريبية · لا يُحفظ شيء مما تفعله هنا", "Exit demo": "إنهاء العرض",
    "Next": "التالي", "Back": "السابق", "Finish": "إنهاء", "Finish tour": "إنهاء الجولة", "Skip tour": "تخطَّ الجولة", "Step": "الخطوة", "of": "من",
    "Chapter": "الفصل", "Setting up the demo…": "جارٍ تجهيز العرض…", "You're all set": "أنت جاهز", "Tour replayed": "أُعيدت الجولة",
    "Added for finishing the tour": "أُضيفت لإكمال الجولة", "Spend them on AI shortlists and replacements.": "استخدمها في القوائم الذكية والبدائل.",
    "Replay any time from": "أعد التشغيل في أي وقت من", "Help": "المساعدة", "or your": "أو", "Profile": "ملفك",
    "Brief": "الطلب", "Shortlist": "القائمة", "Check a creator": "افحص مؤثراً", "Plan": "خطّط", "Ask Helvy": "اسأل هيلفي", "Quote": "عرض السعر", "Follow": "تابع",
    "Tell Helvy what the campaign is.": "أخبر هيلفي بما تريده من الحملة.", "Helvy scores the roster for you.": "هيلفي يقيّم كل المؤثرين لك.",
    "See what is open and what is locked.": "اعرف ما هو مفتوح وما هو مقفل.", "Test the structure before you book.": "جرّب التركيبة قبل الحجز.",
    "Questions answered, with a person behind him.": "إجابات فورية، ومعها شخص حقيقي خلفه.", "Request it, approve it, go live.": "اطلبه، اعتمده، وانطلق.",
    "Results, estimate vs actual, your profile.": "النتائج، التقدير مقابل الفعلي، وملفك.",
    "Set the campaign goals": "حدّد أهداف الحملة", "Pick one goal or several; Helvy weighs them together.": "اختر هدفاً أو أكثر؛ هيلفي يوازن بينها معاً.",
    "Awareness and Engagement are both on.": "الوعي والتفاعل مفعّلان معاً.",
    "Choose the countries": "اختر الدول", "Add every country your audience lives in.": "أضف كل دولة يعيش فيها جمهورك.",
    "Saudi Arabia and the UAE are picked.": "السعودية والإمارات مختارتان.",
    "Helvy builds the shortlist": "هيلفي يبني القائمة", "He scores the whole roster against your brief and returns the best fits.": "يقيّم كل المؤثرين وفق طلبك ويعيد الأنسب.",
    "Every creator carries a fit score": "لكل مؤثر درجة ملاءمة", "Hover the score to see why, and how much data stands behind it.": "مرّر على الدرجة لترى السبب وحجم البيانات خلفها.",
    "Thin data is labelled": "البيانات القليلة موسومة", "Where Helvy has little to read, the score says Limited data: a first look, not a verdict.": "حين تقلّ البيانات تقول الدرجة «بيانات محدودة»: نظرة أولى لا حكم.",
    "Headline numbers are free": "الأرقام الرئيسية مجانية", "Followers, platforms, views and engagement are open; the rest stays locked until you ask.": "المتابعون والمنصات والمشاهدات والتفاعل مفتوحة؛ والباقي مقفل حتى تطلبه.",
    "See a sample first": "شاهد نموذجاً أولاً", "One tap opens a sample full analysis of an anonymised creator.": "بنقرة واحدة تفتح تحليلاً كاملاً نموذجياً لمؤثر مجهول الهوية.",
    "What a full analysis holds": "ماذا يحوي التحليل الكامل", "Audience, authenticity, growth, content and brand history.": "الجمهور، المصداقية، النمو، المحتوى وتاريخ العلامات.",
    "Plan with the ROI calculator": "خطّط بحاسبة العائد", "Open it from your selection to test the structure before you book.": "افتحها من قائمتك لتجرّب التركيبة قبل الحجز.",
    "Choose how many creators": "اختر عدد المؤثرين", "Set the number you want to run; the recommended structure updates for it.": "حدّد العدد الذي تريده؛ وتتحدّث التركيبة الموصى بها.",
    "Selection quality and the gap": "جودة القائمة والفجوة", "Quality compares your picks with the recommended structure, and the gap says what is missing.": "الجودة تقارن اختياراتك بالتركيبة الموصى بها، والفجوة تقول ما ينقص.",
    "Up to three ways to improve": "حتى ثلاث طرق للتحسين", "Each way is one tap; the quality updates at once.": "كل طريقة بنقرة واحدة؛ وتتحدّث الجودة فوراً.",
    "Ask why a creator scored what it did": "اسأل لماذا حصل مؤثر على درجته", "Helvy explains a score in plain words, from the creator's own numbers.": "هيلفي يشرح الدرجة بكلمات بسيطة من أرقام المؤثر نفسه.",
    "While he works you see what he is doing: dots and one plain line.": "أثناء عمله ترى ما يفعله: نقاط وسطر واحد بسيط.",
    "Compare two creators": "قارن بين مؤثرين", "Ask for two side by side; he reads both analyses for you.": "اطلب مؤثرين جنباً إلى جنب؛ يقرأ التحليلين عنك.",
    "A person behind him": "شخص حقيقي خلفه", "When Helvy can't answer, one tap hands the chat to your account manager.": "حين لا يستطيع هيلفي الإجابة، نقرة واحدة تحوّل المحادثة إلى مدير حسابك.",
    "Request a quote": "اطلب عرض سعر", "When you are happy with the picks, send the selection to your account manager.": "راضٍ عن الاختيارات؟ أرسل القائمة إلى مدير حسابك.",
    "One form, then it is sent": "نموذج واحد ثم يُرسل", "Confirm your details; the quote is requested and the chip follows it.": "أكّد بياناتك؛ يُطلب العرض وتتبعه الشارة.",
    "The quote has a timeline": "لعرض السعر مسار", "Draft, Quote requested, Quote ready, Approved, Campaign live, Completed.": "مسودة، طُلب العرض، العرض جاهز، معتمد، الحملة مباشرة، مكتملة.",
    "Approve it": "اعتمده", "Only the selection's owner approves; HelloVoice then sets up the campaign.": "مالك القائمة وحده يعتمد؛ ثم تجهّز هيلو فويس الحملة.",
    "The verdict comes first": "الحكم أولاً", "Behind, on track or ahead, against your targets, refreshed every 24 hours.": "متأخر أو على المسار أو متقدّم مقابل أهدافك، ويتجدّد كل ٢٤ ساعة.",
    "Estimate vs actual": "التقدير مقابل الفعلي", "The estimate you saved before the campaign, against what really happened.": "التقدير الذي حفظته قبل الحملة مقابل ما حدث فعلاً.",
    "Your profile": "ملفك", "Selections, campaigns, credits and invites live here; invite a colleague and earn credits.": "القوائم والحملات والرصيد والدعوات هنا؛ ادعُ زميلاً واكسب رصيداً.",
    "That's the whole story: brief, shortlist, check, plan, ask, approve, follow.": "هذه القصة كاملة: طلب، قائمة، فحص، تخطيط، سؤال، اعتماد، متابعة."
  };
  function TT(s) { return IS_AR && AR[s] ? AR[s] : s; }

  /* ============================================================ the demo world (data) */
  var BRAND = "Northwind Pharma", CAMPAIGN = "Ramadan Skincare", SEL_NAME = BRAND + " · " + CAMPAIGN;
  var SEL = "demo-ramadan", CAMP = "demo-ramadan-live";
  var GOALS = ["awareness", "engagement"], PLATS = ["Instagram", "TikTok"];
  var FX = { SAR: 1.0, AED: 0.9793, USD: 0.2667 };
  var PICKS = ["DEMO-01", "DEMO-06", "DEMO-02", "DEMO-05", "DEMO-08"];       // the selection's creators (re-ordered by score below)
  var APPROVED0 = ["DEMO-01", "DEMO-06", "DEMO-02", "DEMO-05"];              // the owner has approved four; one is under review
  var R = null, PEOPLE = [], BY = {};

  function sizeOf(f) { return f < 20000 ? "nano" : f < 100000 ? "micro" : f < 500000 ? "mid" : f < 1000000 ? "macro" : "mega"; }
  function bandOfTier(t) { return /macro/i.test(t) ? "macro" : /micro/i.test(t) ? "micro" : /nano/i.test(t) ? "nano" : "mid"; }
  function prim(p) { return p.platforms[0]; }
  function setRoster(doc) {
    R = doc; PEOPLE = doc.people; BY = {};
    PEOPLE.forEach(function (p) { BY[p.code] = p; });
    PICKS = PICKS.slice().sort(function (a, b) { return BY[b].score.overall - BY[a].score.overall; });
  }
  function fOn(p, platform) { var x = p.platforms.filter(function (q) { return q.platform === platform; })[0]; return x ? x.followers : 0; }

  function rosterRow(p) {
    var pr = prim(p);
    return { code: p.code, name: p.name, handle: p.handle, platform: p.platforms.map(function (x) { return x.platform; }).join(", "), followers: pr.followers,
      city: p.city, nationality: p.nationality, tier: p.tier, interest: p.interest, photo: "demo-" + p.photo + ".webp", lowres: false, analysis: true,
      accounts: p.platforms.map(function (x) { return { platform: x.platform, url: "#demo-profile", followers: x.followers, tier: p.tier, price: p.price }; }),
      photo_url: photo(p.photo), price: p.price,
      profiles: p.platforms.map(function (x) { return { platform: x.platform, url: "#demo-profile", followers: x.followers }; }) };
  }
  var TIERS = [{ name: "Nano", from: 600, to: 900, reach: "Under 20K" }, { name: "Micro", from: 1000, to: 1800, reach: "20K – 100K" },
               { name: "Mid-Tier", from: 3000, to: 5000, reach: "100K – 500K" }, { name: "Macro", from: 6500, to: 10000, reach: "500K – 1M" },
               { name: "HCP - Mid-Tier", from: 5000, to: 8000, reach: "100K – 500K" }];

  // The fit score the selection page and its tooltip read (fit.py's shape).
  var PART_LABEL = { engagement: "Engagement", reach: "Reach", audience: "Audience (measured)" }, PART_W = { engagement: 0.4, reach: 0.25, audience: 0.35 };
  function tagOf(n) { return n >= 80 ? "Strong fit" : n >= 60 ? "Good fit" : n >= 40 ? "Possible fit" : "Not recommended"; }
  function scoreFor(p) {
    var s = p.score, pl = prim(p).platform;
    var parts = ["engagement", "reach", "audience"].map(function (k) { return { label: PART_LABEL[k], s: s.parts[k], key: k, w: PART_W[k] }; });
    var one = function (platform, delta) {
      var n = Math.max(0, s.overall + delta), t = tagOf(n);
      return { score: n, tag: t, strengths: s.strengths.slice(), watchouts: s.watchouts.slice(),
        conclusion: t + " for awareness + engagement (" + n + "/100)." + (s.limited_data ? " Limited data: read it as a first look." : ""),
        parts: parts.map(function (x) { return { label: x.label, s: x.s }; }), platform: platform, objective: "Awareness+Engagement", basic: false,
        checks: s.checks.slice(), confidence: clone(s.confidence), reach_followers: fOn(p, platform) || null, limited_data: !!s.limited_data };
    };
    var out = one(pl, 0);
    out.assigned = "Auto"; out.available = p.platforms.map(function (x) { return x.platform; });
    out.platforms = {};
    p.platforms.forEach(function (x, i) { out.platforms[x.platform] = one(x.platform, -3 * i); });
    return out;
  }

  /* -- a creator's full analysis, as the analysis page draws it (analysis.py's shape) -- */
  function analysisCore(p, pl, anon) {
    var f = pl.followers, a = p.audience, au = p.authenticity;
    var top = [3, 1, 8, 5, 6, 2];
    var mkBrand = function (b, i) { return anon ? "Brand " + "ABCDEFGH"[i] : b; };
    var out = {
      platform: pl.platform, updated: iso(NOW - 3 * DAY), account_type: "Creator", followers: f, followers_change_pct: p.growth_pct,
      avg_likes: Math.round(f * pl.er / 100 * 0.9), avg_likes_change_pct: 6.1, er: pl.er, avg_views: pl.avg_views, median_views: pl.median_views, sample_posts: pl.posts,
      fake_followers_pct: au.fake_followers_pct, fake_likers_pct: au.fake_likers_pct, real_people_pct: au.real_people_pct,
      notable_followers_pct: au.notable_followers_pct, mass_followers_pct: au.mass_followers_pct, suspicious_mass_pct: r1(au.mass_followers_pct * 0.45), suspicious_pct: au.suspicious_pct,
      est_impressions: Math.round(f * 0.42), est_reach: Math.round(f * 0.31), avg_comments: Math.round(f * 0.0021),
      reels_er: r1(pl.er + 0.6), avg_reel_plays: pl.avg_views, avg_reel_likes: Math.round(f * 0.034), avg_reel_comments: Math.round(f * 0.0019),
      avg_reel_shares: Math.round(f * 0.0011), story_reach: Math.round(f * 0.07), story_impressions: Math.round(f * 0.08),
      paid_post_performance: 92.4, paid_views_pct: 96.1, posts_per_week: p.posts_per_week, posts_count: 1180, following: 640, last_post: iso(NOW - DAY),
      audience: {
        gender: { female: a.female, male: a.male }, ages: a.ages.map(function (x) { return { name: x.name, pct: x.pct }; }),
        ages_male: a.ages.map(function (x) { return { name: x.name, pct: r1(x.pct * a.male / 100) }; }),
        ages_female: a.ages.map(function (x) { return { name: x.name, pct: r1(x.pct * a.female / 100) }; }),
        countries: a.countries.map(function (c) { return { code: c.code, pct: c.pct }; }), cities: a.cities.map(function (c) { return { name: c.name, pct: c.pct }; }),
        languages: a.languages.map(function (c) { return { name: c.name, pct: c.pct }; }),
        interests: [{ name: "Beauty & cosmetics", pct: 46.2 }, { name: "Clothes, shoes, handbags & accessories", pct: 38.1 }, { name: "Restaurants, food & grocery", pct: 24.7 },
                    { name: "Travel, tourism & aviation", pct: 19.4 }, { name: "Fitness & yoga", pct: 14.2 }],
        brand_affinity: R.brands.slice(0, 4).map(function (b, i) { return { name: mkBrand(b, i), pct: r1(12.4 - i * 2.6) }; }),
        reachability: [{ name: "<500", pct: 41.3 }, { name: "500-1000", pct: 27.2 }, { name: "1000-1500", pct: 12.9 }, { name: ">1500", pct: 18.6 }]
      },
      growth: [5, 4, 3, 2, 1, 0].map(function (k, i) {
        var d = new Date(NOW * 1000); d.setUTCMonth(d.getUTCMonth() - k - 1);
        return { month: d.toISOString().slice(0, 7), followers: Math.round(f * (0.86 + i * 0.028)), avg_likes: Math.round(f * pl.er / 100 * (0.8 + i * 0.04)) };
      }),
      fake_followers_dist: { buckets: [{ label: ">30%", h: 18 }, { label: "25%", h: 26 }, { label: "20%", h: 38 }, { label: "15%", h: 55 }, { label: "12%", h: 74 }, { label: "9%", h: 100 }, { label: "7%", h: 81 }, { label: "<5%", h: 42 }], creator: 6, median: 4 },
      er_dist: { buckets: [{ label: "<0.5%", h: 34 }, { label: "1%", h: 62 }, { label: "1.5%", h: 100 }, { label: "2%", h: 77 }, { label: "3%", h: 48 }, { label: "4%", h: 30 }, { label: "5%", h: 18 }, { label: ">6%", h: 9 }], creator: 5, median: 2 },
      top_posts: top.map(function (n, i) { return { url: "#demo-post", thumb: anon ? null : photo(n), likes: Math.round(f * (0.06 - i * 0.006)), comments: Math.round(f * 0.002 * (6 - i)), views: Math.round(f * (0.9 - i * 0.1)), date: iso(NOW - (6 + i * 9) * DAY) }; }),
      sponsored_posts: p.brands.map(function (b, i) { return { url: "#demo-post", thumb: anon ? null : photo([1, 8, 6][i] || 1), likes: Math.round(f * (0.04 - i * 0.005)), comments: Math.round(f * 0.0016), views: Math.round(f * (0.62 - i * 0.08)), date: iso(NOW - (20 + i * 30) * DAY), brand: mkBrand(b, i) }; }),
      hashtags: ["#skincare", "#routine", "#ramadanglow", "#spf", "#riyadh"].map(function (t, i) { return { tag: anon ? "#hashtag" + (i + 1) : t, count: [31.2, 22.6, 14.8, 9.7, 6.5][i] }; }),
      brands: p.brands.map(function (b, i) { return { name: mkBrand(b, i), count: 4 - i, logo: null }; }),
      creator_interests: ["Beauty & Cosmetics", "Healthy Lifestyle", "Fashion"]
    };
    if (anon) {
      // admin/sample_analysis.py copies figures from an allow-list only: nothing else is in the sample
      delete out.posts_per_week; delete out.last_post;
      out.audience_likers = clone(out.audience);
      out.sample = true;
    }
    else { out.handle = p.handle; out.location = p.city + ", Saudi Arabia"; out.photo_url = photo(p.photo);
           out.bio = "Honest routines, tested in the Riyadh heat.\nArabic & English · collaborations via HelloVoice"; }
    return out;
  }
  var BENCH = { er: { nano: [4.0, 2.0], micro: [3.0, 1.5], mid: [2.0, 1.0], macro: [1.5, 0.8], mega: [1.0, 0.5] }, video_er: [4.5, 3.0], view_rate: [30.0, 10.0],
                story_rate: [8.0, 4.0], ctr: [1.0, 0.3], fake_followers: [15.0, 30.0], fake_likers: [15.0, 30.0] };
  function headline(p) {
    var pr = prim(p);
    return { followers: p.platforms.reduce(function (s, x) { return s + x.followers; }, 0), platforms: p.platforms.map(function (x) { return x.platform; }),
             avg_views: pr.avg_views, er: pr.er, er_platform: pr.platform, er_followers: pr.followers, updated: iso(NOW - 3 * DAY) };
  }
  function lockedSample() {
    return { sample: true, gender: { female: 64, male: 36 }, ages: [["18–24", 31], ["25–34", 42], ["35–44", 18], ["45+", 9]],
      countries: [["Saudi Arabia", 61], ["UAE", 12], ["Egypt", 7]], growth: [40, 42, 45, 47, 52, 55, 58, 60, 63, 67, 70, 74], growth_pct: 85, real_pct: 88,
      brands: ["Brand A", "Brand B", "Brand C", "Brand D", "Brand E"], partnerships: 9, pricing: { low: 3000, high: 12000, pos: 0.5 }, posts: ["420K", "388K", "301K", "276K"] };
  }
  function creatorCard(p) {
    return { code: p.code, name: p.name, tier: p.tier, city: p.city, nationality: p.nationality, interest: p.interest, followers: prim(p).followers, photo_url: photo(p.photo),
             profiles: p.platforms.map(function (x) { return { platform: x.platform, url: "#demo-profile", followers: x.followers }; }), band: bandOfTier(p.tier) };
  }
  function creatorBody(code) {
    var p = BY[code];
    if (!p) return { ok: false, reason: "unknown" };
    var out = { ok: true, creator: creatorCard(p), platforms: p.platforms.map(function (x) { return x.platform; }), analyses: {}, requested: [], benchmarks: BENCH };
    var asked = STATE.asked[code];
    if (code === "DEMO-01") {
      p.platforms.forEach(function (pl) { out.analyses[pl.platform] = analysisCore(p, pl, false); });
      out.gate = { state: "unlocked", granted_at: NOW - 2 * DAY, headline: headline(p), sample_full: true };
    } else if (asked) {
      out.gate = { state: "requested", requested_at: asked, ready_by: asked + DAY, selections: [{ token: SEL, name: SEL_NAME }], headline: headline(p), sample: lockedSample(), sample_full: true };
    } else {
      out.gate = { state: "locked", selections: [{ token: SEL, name: SEL_NAME }], headline: headline(p), sample: lockedSample(), sample_full: true };
    }
    return out;
  }
  // The anonymised sample full analysis (admin/sample_analysis.py): no name, handle, photo, link or cover.
  function sampleBody() {
    var base = BY["DEMO-06"];
    var big = { platform: "Instagram", followers: 1342610, er: 2.9, avg_views: 276400, median_views: 214800, posts: 41 };
    var p = Object.assign({}, base, { brands: ["x", "y", "z"], growth_pct: 3.2, posts_per_week: 4.6 });
    var a = analysisCore(p, big, true);
    return { ok: true, sample: true, label: "Sample · anonymised creator",
      creator: { code: "SAMPLE", name: "Sample creator", tier: "HCP - Mega", city: null, nationality: null, interest: null, followers: big.followers, photo_url: null,
                 profiles: [{ platform: "Instagram", url: null, followers: big.followers }], band: "mega" },
      platforms: ["Instagram"], analyses: { Instagram: a }, requested: [], gate: { state: "unlocked", sample: true }, benchmarks: BENCH };
  }

  /* ============================================ the ROI calculator (a port of admin/roi.py, v4.1)
   * Same inputs, same keys, the same recommended-structure shapes and the same rules (quality is
   * capped at 100 %, sizes outside the structure and surplus add no credit; no budget, price,
   * CPM or market anywhere). The numbers are planning figures for the demo roster. */
  var TIER_ORDER = ["mega", "macro", "mid", "micro", "nano"];
  var TIER_NAME = { mega: ["Mega", "1M+ followers"], macro: ["Macro", "500K–1M"], mid: ["Mid", "100K–500K"], micro: ["Micro", "20K–100K"], nano: ["Nano", "Under 20K"] };
  var SIZE_WORD = { mega: "mega", macro: "macro", mid: "mid-size", micro: "micro", nano: "nano" };
  var GOAL_LABEL = { awareness: "Awareness", engagement: "Engagement", traffic: "Traffic" };
  var PRIMARY = { awareness: "views", engagement: "interactions", traffic: "clicks" };
  var SHAPES = { awareness: { macro: 10, mid: 25, micro: 45, nano: 20 }, engagement: { macro: 3, mid: 20, micro: 45, nano: 32 }, traffic: { mid: 25, micro: 55, nano: 20 } };
  var COUNT_RANGES = { awareness: [12, 25], engagement: [15, 30], traffic: [8, 20] };
  var TIER_F = { nano: 6000, micro: 35000, mid: 200000, macro: 700000, mega: 1500000 };
  var VIEW_RATE = { Instagram: { nano: 12, micro: 12, mid: 20, macro: 12, mega: 3 }, TikTok: { nano: 32, micro: 25, mid: 17, macro: 12, mega: 8.5 },
                    Snapchat: { nano: 11.5, micro: 10, mid: 8.5, macro: 7, mega: 5.5 }, YouTube: { nano: 10.5, micro: 8.5, mid: 7, macro: 5.5, mega: 4 } };
  var ENG_RATE = { Instagram: { nano: 4.2, micro: 3.5, mid: 2.7, macro: 2.1, mega: 1.5 }, TikTok: { nano: 5.7, micro: 4.7, mid: 4, macro: 3.5, mega: 2.7 },
                   Snapchat: { nano: 0.85, micro: 0.75, mid: 0.65, macro: 0.55, mega: 0.45 }, YouTube: { nano: 3, micro: 2.6, mid: 2.2, macro: 1.8, mega: 1.5 } };
  var CTR = { Instagram: 0.55, TikTok: 0.4, Snapchat: 0.7, YouTube: 0.6 };
  var REACH_PV = { Instagram: 0.4, TikTok: 0.8, Snapchat: 0.95, YouTube: 0.85 };
  var MEAN_OVER_MEDIAN = 1.8, MARGIN_BASE = 0.48, MARGIN_N = 20, FLOOR = 0.1, TOL = 10, SECOND = 0.8, GOOD_ENOUGH = 0.01;
  var ESTIMATE_LINE = "Estimate, not a result. Real results depend on the content, the timing and the audience.";

  function sig2(v, up) {
    if (!v || v <= 0) return 0;
    var e = Math.floor(Math.log10(v)) - 1, q = Math.pow(10, e);
    return Math.round((up ? Math.ceil(v / q - 1e-9) : Math.floor(v / q + 1e-9)) * q);
  }
  function sig2n(v) { if (!v || v <= 0) return 0; var e = Math.floor(Math.log10(v)) - 1, q = Math.pow(10, e); return Math.round(Math.round(v / q) * q); }
  function goalList(goals) {
    var g = (goals || []).map(function (x) { return x === "conversion" ? "traffic" : x; }).filter(function (x) { return GOAL_LABEL[x]; });
    g = g.filter(function (x, i) { return g.indexOf(x) === i; });
    return g.length ? g : ["awareness"];
  }
  function shapeFor(gl) {
    var acc = {};
    gl.forEach(function (g) { Object.keys(SHAPES[g]).forEach(function (t) { acc[t] = (acc[t] || 0) + SHAPES[g][t] / gl.length; }); });
    return acc;
  }
  function largestRemainder(weights, n) {
    var tot = 0, k; for (k in weights) if (weights[k] > 0) tot += weights[k];
    if (!n || !tot) return {};
    var quota = {}, out = {}, left = n;
    for (k in weights) if (weights[k] > 0) { quota[k] = weights[k] / tot * n; out[k] = Math.floor(quota[k] + 1e-9); left -= out[k]; }
    Object.keys(quota).sort(function (a, b) { return (quota[b] - out[b]) - (quota[a] - out[a]) || TIER_ORDER.indexOf(a) - TIER_ORDER.indexOf(b); })
      .slice(0, left).forEach(function (t) { out[t] += 1; });
    Object.keys(out).forEach(function (t) { if (!out[t]) delete out[t]; });
    return out;
  }
  function postValues(platform, followers, doc, score) {
    var size = sizeOf(followers), f = followers, eff = score == null ? 1 : 0.8 + 0.4 * Math.max(0, Math.min(100, score)) / 100;
    var measured = !!(doc && doc.median_views), n = measured ? doc.posts : 0;
    var margin = n ? MARGIN_BASE * Math.sqrt(MARGIN_N / n) : MARGIN_BASE;
    var v = measured ? doc.median_views : f * VIEW_RATE[platform][size] / 100;
    var vexp = v * MEAN_OVER_MEDIAN;
    var rate = ENG_RATE[platform][size], ctr = CTR[platform] / 100;
    var views = vexp * eff;
    return { platform: platform, size: size, followers: f, views: views, interactions: vexp * rate / 100 * eff, reach: views * REACH_PV[platform], clicks: vexp * ctr * eff,
             m_views: margin, m_inter: Math.sqrt(margin * margin + MARGIN_BASE * MARGIN_BASE), m_clicks: Math.sqrt(margin * margin + MARGIN_BASE * MARGIN_BASE), measured: measured };
  }
  function half(posts, key, mkey) {
    var tot = 0, sq = 0; posts.forEach(function (p) { tot += p[key]; sq += Math.pow(p[mkey] * p[key], 2); });
    if (!tot) return [0, 0];
    return [tot, Math.max(Math.sqrt(sq), FLOOR * tot)];
  }
  var FIG = { views: ["Views", "views", "m_views"], reach: ["Reach", "reach", "m_views"], interactions: ["Interactions", "interactions", "m_inter"], clicks: ["Clicks", "clicks", "m_clicks"] };
  var FIG_ORDER = { awareness: ["views", "reach"], engagement: ["interactions", "views"], traffic: ["clicks", "views"] };
  function combine(posts, key, mkey) {
    var h2 = half(posts, key, mkey), tot = h2[0];
    if (!tot) return [0, 0, 0];
    return [tot, sig2(Math.max(tot - h2[1], 0), false), sig2(tot + h2[1], true)];
  }
  function sideOf(posts, gl, nCreators, bySize, plats) {
    var raw = {}, totals = {};
    Object.keys(FIG).forEach(function (k) {
      var c = combine(posts, FIG[k][1], FIG[k][2]);
      raw[k] = { key: k, label: FIG[k][0], value: sig2n(c[0]), range: [c[1], c[2]], unit: "" };
      totals[k === "interactions" ? "engagement" : k] = Math.round(c[0]);
    });
    var vt = totals.views, it = totals.engagement, ct = totals.clicks;
    var er = vt ? it / vt * 100 : null, ctr = vt ? ct / vt * 100 : null;
    if (er != null) totals.er = er < 1 ? Math.round(er * 100) / 100 : r1(er);
    if (ctr != null) totals.ctr = ctr < 1 ? Math.round(ctr * 100) / 100 : r1(ctr);
    totals.landing = Math.round(ct * 0.8);
    totals.impressions = Math.round(posts.reduce(function (s, p) { return s + p.views * 1.3; }, 0));
    var order = []; gl.forEach(function (g) { FIG_ORDER[g].forEach(function (k) { if (order.indexOf(k) === -1) order.push(k); }); });
    var figures = order.filter(function (k) { return raw[k].value || posts.length; }).map(function (k) { return raw[k]; });
    if (order.indexOf("interactions") > -1 && er != null) figures.push({ key: "er", label: "Engagement rate", value: totals.er, unit: "%", range: [r1(er * 0.8), r1(er * 1.2)] });
    var scores = posts.filter(function (p) { return p.score != null && !p.second; }).map(function (p) { return p.score; });
    var total = bySize ? Object.keys(bySize).reduce(function (s, k) { return s + bySize[k]; }, 0) || 1 : 1;
    return { creators: nCreators, posts: posts.length,
      by_size: TIER_ORDER.map(function (t) { return { size: t, label: TIER_NAME[t][0], n: (bySize || {})[t] || 0, pct: Math.round(((bySize || {})[t] || 0) / total * 100) }; }),
      by_platform: plats.map(function (p) { return { platform: p, posts: posts.filter(function (x) { return x.platform === p && !x.second; }).length }; }),
      figures: figures, totals: totals,
      ranges: { views: { value: raw.views.value, range: raw.views.range }, interactions: { value: raw.interactions.value, range: raw.interactions.range }, clicks: { value: raw.clicks.value, range: raw.clicks.range } },
      score: scores.length ? Math.round(scores.reduce(function (a, b) { return a + b; }, 0) / scores.length) : null, _raw: raw };
  }
  function creditedPosts(sel, ideal, vk) {
    var idealN = {}, by = {}, out = [];
    ideal.forEach(function (p) { var k = p.platform + "|" + p.size; idealN[k] = (idealN[k] || 0) + 1; });
    sel.forEach(function (p) { var k = p.platform + "|" + p.size; (by[k] = by[k] || []).push(p); });
    Object.keys(by).forEach(function (k) { out = out.concat(by[k].sort(function (a, b) { return b[vk] - a[vk]; }).slice(0, idealN[k] || 0)); });
    return out;
  }
  var PRIMARY_FIELD = { awareness: ["views", "m_views"], engagement: ["interactions", "m_inter"], traffic: ["clicks", "m_clicks"] };
  function qualityOf(selPosts, idealPosts, gl) {
    var ratios = {}, rels = [], any = false;
    gl.forEach(function (g) {
      var vk = PRIMARY_FIELD[g][0], mk = PRIMARY_FIELD[g][1];
      var s = half(creditedPosts(selPosts, idealPosts, vk), vk, mk), o = half(idealPosts, vk, mk);
      if (!s[0] || !o[0]) return;
      any = true;
      var r = s[0] / o[0]; ratios[g] = Math.min(r, 1);
      rels.push(ratios[g] * Math.sqrt(Math.pow(s[1] / s[0], 2) + Math.pow(o[1] / o[0], 2)));
    });
    if (!any) return null;
    var keys = Object.keys(ratios), q = keys.reduce(function (s, k) { return s + ratios[k]; }, 0) / keys.length;
    var hf = rels.reduce(function (a, b) { return a + b; }, 0) / rels.length;
    var lo = Math.max(q - hf, 0), hi = Math.min(q + hf, 1);
    var vk0 = PRIMARY_FIELD[gl[0]][0], mk0 = PRIMARY_FIELD[gl[0]][1];
    var s0 = half(creditedPosts(selPosts, idealPosts, vk0), vk0, mk0), o0 = half(idealPosts, vk0, mk0), overlap = 0;
    if (s0[0] && o0[0]) {
      var alo = s0[0] - s0[1], ahi = s0[0] + s0[1], blo = o0[0] - o0[1], bhi = o0[0] + o0[1];
      overlap = Math.max(0, Math.min(ahi, bhi) - Math.max(alo, blo)) / Math.max(Math.min(ahi - alo, bhi - blo), 1e-9);
    }
    var r5 = function (x) { return 5 * Math.round(x * 100 / 5); };
    var met = q >= 0.995, band = overlap >= 0.5 && !met;
    var pct = Math.min(r5(q), 100), plo = Math.min(r5(lo), 100), phi = Math.min(r5(hi), 100);
    var text = met ? "meets the recommended structure" : (band && plo !== phi ? plo + "–" + phi + "%" : "about " + pct + "%");
    var by_goal = {}; keys.forEach(function (g) { by_goal[g] = Math.min(r5(ratios[g]), 100); });
    return { pct: pct, low: plo, high: phi, band: band && plo !== phi, met: met, overlap: Math.round(overlap * 100) / 100, text: text, by_goal: by_goal, _q: q };
  }
  function sizeList(c) { var b = TIER_ORDER.filter(function (t) { return c[t]; }).map(function (t) { return c[t] + " " + t; }); return b.length ? b.join(", ") : "none"; }
  function wordOf(n) { return { 1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six" }[n] || String(n); }
  function onStructure(sel, ideal) {
    var ns = Object.keys(sel).reduce(function (s, k) { return s + sel[k]; }, 0) || 1, ni = Object.keys(ideal).reduce(function (s, k) { return s + ideal[k]; }, 0) || 1, out = {};
    TIER_ORDER.forEach(function (t) { var d = (sel[t] || 0) / ns * 100 - (ideal[t] || 0) / ni * 100; out[t] = d < -TOL ? "short" : d > TOL ? "over" : "on"; });
    return out;
  }
  function gapWords(sel, ideal, unit, n) {
    var st = onStructure(sel, ideal), out = [];
    var avg = n ? TIER_ORDER.reduce(function (s, t) { return s + (ideal[t] || 0) * (unit[t] || 0); }, 0) / n : 0;
    TIER_ORDER.forEach(function (t) {
      var want = ideal[t] || 0, have = sel[t] || 0, w = SIZE_WORD[t];
      if (st[t] === "short") { var k = Math.max(want - have, 1); out.push([k, have === 0 ? "No " + w + " creator" : wordOf(k) + " " + w + " creator" + (k === 1 ? "" : "s") + " short"]); }
      else if (st[t] === "over") {
        var extra = Math.max(have - want, 1);
        if ((unit[t] || 0) < 0.6 * avg) out.push([extra * 0.5, wordOf(extra) + " " + w + " creator" + (extra === 1 ? "" : "s") + " add little"]);
        else out.push([extra * 0.3, wordOf(extra) + " more " + w + " creator" + (extra === 1 ? "" : "s") + " than recommended"]);
      }
    });
    return out.sort(function (a, b) { return b[0] - a[0]; }).slice(0, 3).map(function (x) { return x[1]; });
  }
  function unitBySize(platform, gl) {
    var out = {}; TIER_ORDER.forEach(function (t) { out[t] = 0; });
    gl.forEach(function (g) {
      var vk = PRIMARY_FIELD[g][0], raw = {}, top = 0;
      TIER_ORDER.forEach(function (t) { raw[t] = postValues(platform, TIER_F[t], null, null)[vk]; top = Math.max(top, raw[t]); });
      TIER_ORDER.forEach(function (t) { out[t] += raw[t] / (top || 1) / gl.length; });
    });
    return out;
  }
  function creatorsFor(codes, plats) {
    return codes.filter(function (c) { return BY[c]; }).map(function (c) {
      var p = BY[c], f = {}, docs = {};
      p.platforms.forEach(function (x) { f[x.platform] = x.followers; docs[x.platform] = { median_views: x.median_views, posts: x.posts }; });
      return { code: c, name: p.name, followers: f, docs: docs, score: p.score.overall, limited: p.score.limited_data };
    });
  }
  function estimate(inp) {
    var gl = goalList(inp.goals || [inp.goal]);
    var plats = ["Instagram", "TikTok", "Snapchat", "YouTube"].filter(function (p) { return (inp.platforms || []).indexOf(p) > -1; });
    if (!plats.length) plats = ["Instagram"];
    var posts = [], skipped = [], selBySize = {}, nCreators = 0, chosen = false;
    if (inp.codes) {
      chosen = inp.codes.length > 0;
      var second = inp.second || [];
      creatorsFor(inp.codes, plats).forEach(function (c) {
        var on = plats.filter(function (p) { return c.followers[p]; });
        if (!on.length) { skipped.push(c.name); return; }
        nCreators += 1;
        var mx = Math.max.apply(null, on.map(function (p) { return c.followers[p]; })), t = sizeOf(mx);
        selBySize[t] = (selBySize[t] || 0) + 1;
        on.forEach(function (p) {
          var v = postValues(p, c.followers[p], c.docs[p], c.score);
          v.code = c.code; v.name = c.name; v.score = c.score;
          posts.push(v);
          if (second.indexOf(c.code) > -1) { var s2 = Object.assign({}, v, { second: true, views: v.views * SECOND, interactions: v.interactions * SECOND, reach: v.reach * SECOND, clicks: v.clicks * SECOND }); posts.push(s2); }
        });
      });
    } else {
      var mix = inp.mix || {};
      plats.forEach(function (p) {
        var m = mix[p] || mix;
        TIER_ORDER.forEach(function (t) {
          var k = Math.max(0, Math.min(200, Math.round(+(m[t] || 0))));
          for (var i = 0; i < k; i++) posts.push(Object.assign(postValues(p, TIER_F[t], null, null), { code: null, score: null }));
          if (k) selBySize[t] = Math.max(selBySize[t] || 0, k);
        });
      });
      nCreators = Math.max.apply(null, plats.map(function (p) { return posts.filter(function (x) { return x.platform === p; }).length; }).concat([0]));
    }
    var first = posts.filter(function (p) { return !p.second; });
    var n = Math.round(+inp.count || 0); n = n ? Math.max(1, Math.min(60, n)) : 0;
    // The recommended structure for the same number of creators and posts, or the number chosen:
    // one post per creator per chosen platform (the selection's posts are split evenly across platforms).
    var per = {};
    if (n) plats.forEach(function (p) { per[p] = n; });
    else if (first.length && inp.codes) {
      var base = Math.floor(first.length / plats.length), extra = first.length % plats.length;
      plats.forEach(function (p, k) { per[p] = base + (k < extra ? 1 : 0); });
    } else plats.forEach(function (p) { per[p] = first.filter(function (x) { return x.platform === p; }).length; });
    var nIdeal = n || (first.length ? nCreators : 0);
    nIdeal = Math.max(0, Math.min(400, nIdeal));
    var shape = shapeFor(gl), counts = {};
    plats.forEach(function (p) { counts[p] = per[p] ? largestRemainder(shape, per[p]) : {}; });
    var idealPosts = [];
    plats.forEach(function (p) { Object.keys(counts[p]).forEach(function (t) { for (var i = 0; i < counts[p][t]; i++) idealPosts.push(Object.assign(postValues(p, TIER_F[t], null, null), { code: null, score: null })); }); });
    var lead = plats[0], idealBySize = counts[lead] || {};
    var sel = sideOf(posts, gl, nCreators, selBySize, plats), ideal = sideOf(idealPosts, gl, nIdeal, idealBySize, plats);
    ideal.score = idealPosts.length ? 50 : null;
    var quality = first.length && idealPosts.length ? qualityOf(posts, idealPosts, gl) : null;
    var lo = Math.round(gl.reduce(function (s, g) { return s + COUNT_RANGES[g][0]; }, 0) / gl.length), hi = Math.round(gl.reduce(function (s, g) { return s + COUNT_RANGES[g][1]; }, 0) / gl.length);
    var measuredC = {}; first.forEach(function (p) { if (p.measured && p.code) measuredC[p.code] = 1; });
    var mc = Object.keys(measuredC).length;
    var trust = inp.codes && first.length ? "Based on measured data for " + mc + " of " + nCreators + " creator" + (nCreators === 1 ? "" : "s") + "."
      : "Based on what similar creators of each size deliver; no individual creator measured.";
    var unit = unitBySize(lead, gl);
    var gap = first.length && nIdeal ? gapWords(selBySize, idealBySize, unit, nIdeal) : [];
    var goalLabel = gl.map(function (g) { return GOAL_LABEL[g]; }).join(" + ");
    var shapeRows = TIER_ORDER.filter(function (t) { return shape[t]; }).map(function (t) { return { size: t, label: TIER_NAME[t][0], pct: Math.round(shape[t]) }; });
    var res = {
      goal: gl[0], goals: gl, goal_label: goalLabel, platforms: plats, creators: nCreators, posts: posts.length, skipped: skipped,
      measured_posts: posts.filter(function (p) { return p.measured; }).length, measured_creators: mc,
      figures: sel.figures, totals: sel.totals,
      selection: Object.assign({}, strip(sel), { on_structure: first.length && nIdeal ? onStructure(selBySize, idealBySize) : {} }),
      ideal: Object.assign({}, strip(ideal), { title: "Ideal for " + goalLabel + " with " + nIdeal + " creator" + (nIdeal === 1 ? "" : "s"), shape: shapeRows, tolerance: TOL, mix: counts, name: "HelloVoice’s recommended structure" }),
      quality: quality ? strip(quality) : null, gap: gap, ways: [],
      count: nIdeal, ideal_count: nIdeal, count_default: nCreators,
      count_range: { low: lo, high: Math.max(lo, hi), text: lo + "–" + Math.max(lo, hi), min: 1, max: 60 },
      compare_line: nIdeal ? "The ideal for " + nIdeal + " creator" + (nIdeal === 1 ? "" : "s") + " has " + sizeList(idealBySize) + (nCreators ? "; you have " + sizeList(selBySize) + "." : ".") : "",
      trust: { line: trust, measured: mc, of: inp.codes && first.length ? nCreators : 0 }, note: ESTIMATE_LINE,
      summary: goalLabel + " · " + plats.join(" and ") + " · " + (nCreators ? nCreators + " creator" + (nCreators === 1 ? "" : "s") : "no creators yet"),
      estimate: true, version: 4,
      _q: quality ? quality._q : null, _posts: posts, _ideal: idealPosts, _selBySize: selBySize, _idealBySize: idealBySize, _gl: gl, _plats: plats
    };
    void chosen;
    return res;
  }
  function strip(o) { var out = {}; Object.keys(o).forEach(function (k) { if (k.charAt(0) !== "_") out[k] = o[k]; }); return out; }
  function sizeOfCreator(c, plats) {
    var fol = plats.filter(function (p) { return c.followers[p]; }).map(function (p) { return c.followers[p]; });
    return fol.length ? sizeOf(Math.max.apply(null, fol)) : null;
  }
  // "Ways to improve": each is scored by re-running the estimate, ranked by the quality points it adds.
  function advise(inp, res) {
    var q0 = res._q, gl = res._gl, plats = res._plats, items = [];
    if (!inp.codes) {
      if (q0 != null && q0 < 0.9) {
        var pts = Math.round((1 - q0) * 100);
        items.push({ id: "use_mix", gain: 1 - q0, points: pts, text: "Your mix reaches about " + 5 * Math.round(q0 * 20) + "% of the recommended structure.", action: { type: "use_mix", mix: res.ideal.mix } });
      }
      return items.slice(0, 3);
    }
    if (q0 == null || !inp.codes.length) return items;
    var creators = creatorsFor(inp.codes, plats), byCode = {}; creators.forEach(function (c) { byCode[c.code] = c; });
    var qOf = function (codes, p2, sec) { var r = estimate(Object.assign({}, inp, { codes: codes, platforms: p2 || plats, second: sec || inp.second })); return r._q; };
    var contrib = {};
    creators.forEach(function (c) { var rest = inp.codes.filter(function (x) { return x !== c.code; }); var q = rest.length ? qOf(rest) : 0; contrib[c.code] = q0 - (q == null ? 0 : q); });
    var ranked = creators.slice().sort(function (a, b) { return contrib[a.code] - contrib[b.code]; });
    var sel = res._selBySize, idl = res._idealBySize;
    var missing = TIER_ORDER.filter(function (t) { return (idl[t] || 0) > (sel[t] || 0); });
    var surplus = TIER_ORDER.filter(function (t) { return (sel[t] || 0) > (idl[t] || 0); });
    var pool = PEOPLE.map(function (p) { return p.code; }).filter(function (c) { return inp.codes.indexOf(c) === -1; })
      .map(function (c) { return creatorsFor([c], plats)[0]; }).filter(function (c) { return c && sizeOfCreator(c, plats); })
      .map(function (c) { var t = sizeOfCreator(c, plats); return { c: c, t: t, miss: missing.indexOf(t) > -1, val: c.score }; })
      .sort(function (a, b) { return (b.miss - a.miss) || (b.val - a.val); }).slice(0, 6);
    var who = function (c) { return c.name + " (" + c.code + ")"; };
    var weak = ranked.filter(function (c) { return surplus.indexOf(sizeOfCreator(c, plats)) > -1; }).slice(0, 2);
    if (!weak.length) weak = ranked.slice(0, 1);
    var best = null;
    weak.forEach(function (w) {
      pool.slice(0, 3).forEach(function (m) {
        if (!m.miss) return;
        var q = qOf(inp.codes.filter(function (x) { return x !== w.code; }).concat([m.c.code]));
        if (q != null && (!best || q > best.q)) best = { q: q, w: w, m: m };
      });
    });
    if (best && best.q - q0 >= GOOD_ENOUGH) {
      items.push({ id: "replace", gain: best.q - q0, points: Math.round((best.q - q0) * 100),
        text: "Swap " + who(best.w) + ", a " + SIZE_WORD[sizeOfCreator(best.w, plats)] + " creator who adds little, for " + who(best.m.c) + ", a " + SIZE_WORD[best.m.t] + " creator.",
        action: { type: "replace", remove: [best.w.code], add: [best.m.c.code] } });
    }
    if (creators.length > 1) {
      var wk = ranked[0], qr = qOf(inp.codes.filter(function (x) { return x !== wk.code; }));
      if (qr != null && qr - q0 >= GOOD_ENOUGH) items.push({ id: "remove", gain: qr - q0, points: Math.round((qr - q0) * 100), text: who(wk) + " adds the least. Keep as reserve or remove.", action: { type: "remove", codes: [wk.code] } });
    }
    var bestAdd = null;
    pool.slice(0, 3).forEach(function (m) { var q = qOf(inp.codes.concat([m.c.code])); if (q != null && (!bestAdd || q > bestAdd.q)) bestAdd = { q: q, m: m }; });
    if (bestAdd && bestAdd.q - q0 >= GOOD_ENOUGH) {
      items.push({ id: "add", gain: bestAdd.q - q0, points: Math.round((bestAdd.q - q0) * 100),
        text: "Add " + who(bestAdd.m.c) + ", a " + SIZE_WORD[bestAdd.m.t] + " creator and a strong performer.", action: { type: "add", codes: [bestAdd.m.c.code] } });
    }
    var sec0 = inp.second || [];
    var top = ranked.slice().reverse().map(function (c) { return c.code; }).filter(function (c) { return sec0.indexOf(c) === -1; }).slice(0, 2);
    if (top.length) {
      var q2 = qOf(inp.codes, plats, sec0.concat(top));
      if (q2 != null && q2 - q0 >= GOOD_ENOUGH) items.push({ id: "second", gain: q2 - q0, points: Math.round((q2 - q0) * 100),
        text: "A second post from your top " + top.length + " creator" + (top.length === 1 ? "" : "s") + " adds about " + Math.round((q2 - q0) * 100) + " points.", action: { type: "second_post", codes: top } });
    }
    ["Instagram", "TikTok", "Snapchat", "YouTube"].forEach(function (p) {
      if (plats.indexOf(p) > -1) return;
      var on = creators.filter(function (c) { return c.followers[p]; }).length;
      if (on < Math.max(1, Math.floor(creators.length / 2))) return;
      var q3 = qOf(inp.codes, plats.concat([p]));
      if (q3 != null && q3 - q0 >= GOOD_ENOUGH) items.push({ id: "platform", gain: q3 - q0, points: Math.round((q3 - q0) * 100), text: "Add " + p + ": " + on + " of your " + creators.length + " creators are there.", action: { type: "add_platform", platform: p } });
    });
    items.sort(function (a, b) { return b.gain - a.gain; });
    return items.slice(0, 3).map(function (i) { return { id: i.id, text: i.text, gain: i.gain, points: i.points, action: i.action }; });
  }
  function roiAnswer(body) {
    var inp = { goals: body.goals || [body.goal], platforms: body.platforms || PLATS, count: body.count, second: body.second_posts || [] };
    if (body.mix) inp.mix = body.mix;
    else {
      var pool = (STATE.codes || []).filter(function (c) { return (STATE.status[c] || { s: "review" }).s !== "rejected"; });
      var approved = pool.filter(function (c) { return (STATE.status[c] || { s: "review" }).s === "approved"; });
      inp.codes = (body.which === "all" || !approved.length) ? pool : approved;
    }
    var res = estimate(inp);
    res.ways = advise(inp, res);
    return strip(res);
  }

  /* ===================================================== quote lifecycle (admin/lifecycle.py) */
  var LC_STATES = ["draft", "requested", "ready", "approved", "live", "completed"];
  var LC_LABEL = { draft: "Draft", requested: "Quote requested", ready: "Quote ready", approved: "Approved", live: "Campaign live", completed: "Completed" };
  var LC_HINT = {
    draft: "Edit freely. When it is ready, request a quote and your account manager prices it.",
    requested: "HelloVoice is preparing your quote, usually within one working day. You can still change the creators.",
    ready: "Your quote is ready. Approve it to start setting up the campaign.",
    approved: "Approved. HelloVoice is setting up the campaign.",
    live: "The campaign is live. Its report refreshes every 24 hours.",
    completed: "The campaign has ended and the final report is ready."
  };
  function lifecycle() {
    var k = STATE.lc, here = LC_STATES.indexOf(k), t = STATE.lcAt, user = Demo.user;
    var by = { draft: user, requested: user, ready: "Marwa M.", approved: user, live: "HelloVoice", completed: "HelloVoice" };
    var steps = LC_STATES.map(function (s, i) {
      var at = t[s] || null;
      return { key: s, label: LC_LABEL[s], at: i <= here ? at : null, by: i <= here && at ? by[s] : "",
               state: i === here ? "current" : (i < here ? "done" : "todo"), note: s === "ready" && i <= here ? "Quote for the approved creators: deliverables, dates and the terms are in the document." : "" };
    });
    return { key: k, label: LC_LABEL[k], role: "owner", steps: steps, hint: LC_HINT[k],
      note: ["ready", "approved", "live", "completed"].indexOf(k) > -1 ? "Quote for the approved creators: deliverables, dates and the terms are in the document." : "",
      link: ["ready", "approved", "live", "completed"].indexOf(k) > -1 ? "#demo-quote" : "",
      can_approve: k === "ready", warn: ["requested", "ready", "approved"].indexOf(k) > -1 ? "This updates your quote request" : "", changes: [],
      campaign: k === "live" || k === "completed" ? { name: CAMPAIGN, token: CAMP } : null, owner: user };
  }
  function setLc(k) {
    STATE.lc = k;
    var i = LC_STATES.indexOf(k);
    LC_STATES.forEach(function (s, j) { if (j <= i && !STATE.lcAt[s]) STATE.lcAt[s] = NOW - (i - j) * 3600 * 5; });
    LC_STATES.forEach(function (s, j) { if (j > i) delete STATE.lcAt[s]; });
  }

  /* -- the demo state for one run of the tour: decisions made in it live here only -- */
  var STATE = null;
  function freshState(user) {
    var st = {};
    APPROVED0.forEach(function (c, i) { st[c] = { s: "approved", by: user, hv: false, at: NOW - (i + 1) * 3600, reason: "", note: "", replacements: [] }; });
    var s = { status: st, codes: PICKS.slice(), asked: {}, lc: "draft", lcAt: {}, credits: 30, handoff: false,
      notes: [{ id: 1, kind: "analysis", group: "analysis", title: "Full analysis ready:", rest: " Lulwa R.", body: "The full analysis you requested is open for your team.", at: NOW - 2 * DAY, unread: true, href: "creator/#c=DEMO-01" }] };
    return s;
  }
  function resetSelection() {
    var st = {}; APPROVED0.forEach(function (c, i) { st[c] = { s: "approved", by: Demo.user, hv: false, at: NOW - (i + 1) * 3600, reason: "", note: "", replacements: [] }; });
    STATE.status = st; STATE.codes = PICKS.slice();
  }
  function me() {
    return { ok: true, signed_in: true, kind: "user", credits: STATE.credits, costs: { brief: 5, parse: 1, chat: 1, search: 0, replace: 2, more: 3, alike: 2 }, ai: true, ai_free: null,
      chat_key: "tour-demo", user: { email: "demo@northwind.example", name: Demo.user, company: BRAND, job_title: "Brand Manager", phone: "", photo: null, industry: "Pharma",
      markets: ["SA"], language: "en", brands: "Northwind" }, unread: STATE.notes.filter(function (n) { return n.unread; }).length, team: [], monthly_credits: 30, tour: "done" };
  }
  var BRIEF_TARGET = { country: "SA|AE", gender: "Women", age: "25-34|35-44", category: "skincare" };
  function selectionBody() {
    var codes = STATE.codes.slice(), counts = { creators: codes.length, influencers: 0, doctors: 0, review: 0, approved: 0, rejected: 0, unavailable: 0 };
    var prices = {}, scores = {};
    codes.forEach(function (c) {
      var p = BY[c], s = (STATE.status[c] || { s: "review" }).s;
      counts[s] += 1; if (/HCP/.test(p.tier)) counts.doctors += 1; else counts.influencers += 1;
      prices[c] = p.price; scores[c] = scoreFor(p);
    });
    var statuses = {}; codes.forEach(function (c) { if (STATE.status[c]) statuses[c] = clone(STATE.status[c]); });
    return { ok: true, name: SEL_NAME, codes: codes, prices: prices, total: null, platform: null, tags: {}, segments: {}, group_by: "",
      brief: { objective: "Awareness + Engagement", target: BRIEF_TARGET, client: BRAND }, scores: scores, client_tags: {}, client_platforms: {}, verdicts: {},
      currency: "SAR", fx: FX, token: SEL, needs_objective: false, status: statuses, status_counts: counts, role: "owner", lifecycle: lifecycle(), owner: Demo.user, kam: "Marwa M.",
      replace_cost: 2, more_cost: 3, alike_cost: 2, ai_free: null, credits: STATE.credits };
  }
  // GET /api/voice/selection: what Helvy knows about the selection on the page (brief on file, scores).
  function voiceSelection() {
    var scored = STATE.codes.map(function (c) { return { code: c, name: BY[c].name, score: BY[c].score.overall, tag: tagOf(BY[c].score.overall) }; })
      .sort(function (a, b) { return b.score - a.score; });
    var details = {}; STATE.codes.forEach(function (c) { var s = scoreFor(BY[c]); details[c] = { score: s.score, tag: s.tag, parts: s.parts, confidence: s.confidence, platform: s.platform, limited_data: s.limited_data, basic: false, note: null }; });
    return { ok: true, token: SEL, name: SEL_NAME, count: STATE.codes.length, objective: "Awareness+Engagement", quote: "Quote status: " + LC_LABEL[STATE.lc] + ".",
      brief: { summary: "A Ramadan skincare launch in the Gulf.", source: "ai",  at: NOW - 2 * DAY, answers: [
        { q: "What are the campaign’s goals", a: "Awareness, Engagement" }, { q: "Where should the content run", a: "Instagram, TikTok" },
        { q: "Which countries is the audience in", a: "Saudi Arabia, UAE" }, { q: "Which space is the product in", a: "Skincare & dermatology" } ] },
      scores: scored, details: details };
  }

  /* ===================================================== the live campaign and the profile */
  // The campaign the approved selection became: the same creators, five posts' worth of results.
  var CREW = [["DEMO-01", 3, 0.9], ["DEMO-06", 3, 1.15], ["DEMO-02", 2, 0.85], ["DEMO-05", 2, 1.0], ["DEMO-08", 2, 1.4]];
  function campaignBody() {
    var start = NOW - 12 * DAY, end = NOW + 18 * DAY, posts = [], creators = [], id = 1, kinds = ["reel", "story", "post"];
    CREW.forEach(function (c, ci) {
      var p = BY[c[0]], pl = prim(p), f = pl.followers, plat = pl.platform;
      var row = { code: c[0], name: p.name, followers: f, posts: 0, likes: 0, comments: 0, engagement: 0, views: 0, reach: 0, impressions: 0, shares: 0, saves: 0, clicks: 0,
                  planned: c[1], delivered: c[1], pending_status: null, pending_date: null,
                  profiles: p.platforms.map(function (x) { return { platform: x.platform, url: "#demo-profile", followers: x.followers }; }), band: bandOfTier(p.tier),
                  photo: photo(p.photo), photo_large: photo(p.photo), has_analysis: c[0] === "DEMO-01", hidden_likes: 0 };
      for (var k = 0; k < c[1]; k++) {
        var kind = kinds[(ci + k) % 3], video = kind !== "post", story = kind === "story";
        var views = Math.round(f * (0.32 + 0.11 * k) * c[2]), likes = Math.round(views * (story ? 0 : 0.052) * c[2]), comments = Math.round(likes * 0.06);
        var shares = Math.round(likes * 0.09), saves = Math.round(likes * 0.12), eng = likes + comments + shares + saves, reach = Math.round(views * 0.88);
        var ver = video ? eng / Math.max(views, 1) * 100 : eng / Math.max(reach, 1) * 100;
        var grade = ver >= 4.5 ? "good" : ver >= 3 ? "moderate" : "low";
        var clicks = Math.round(views * 0.006 * c[2]);
        posts.push({ id: id++, code: c[0], platform: plat, kind: kind, url: "#demo-post", posted_at: start + (2 + ci + k * 3) * DAY,
          caption: ["Ramadan routine with Northwind", "Suhoor skincare in 60 seconds", "Glow through the fasting month"][k % 3], thumb: photo([p.photo, 1, 8, 6, 5][(k + ci) % 5]),
          section: "campaign", likes: likes, comments: comments, engagement: eng, views: views, reach: reach, impressions: Math.round(views * 1.2),
          shares: shares, saves: saves, er: Math.round(eng / f * 1000) / 10, video_er: video ? ver : null, imp_er: null,
          view_rate: Math.round(views / f * 1000) / 10, story_rate: story ? 7.2 : null, real: k === 0, reach_real: k === 0, impressions_real: false,
          video: video, story: story, health: { metric: video ? "Video ER" : "ER", value: ver, grade: grade, benchmark: video ? [4.5, 3.0] : [2.0, 1.0], view_rate: Math.round(views / f * 1000) / 10, view_grade: "good" },
          likes_hidden: false, gaps: [], exposure: views, creator: p.name, photo: photo(p.photo), clicks: clicks });
        row.posts++; row.likes += likes; row.comments += comments; row.engagement += eng; row.views += views; row.reach += reach;
        row.shares += shares; row.saves += saves; row.clicks += clicks; row.impressions += Math.round(views * 1.2);
      }
      row.er = Math.round(row.engagement / f / row.posts * 1000) / 10; row.video_er = row.engagement / Math.max(row.views, 1) * 100;
      row.er_grade = row.er >= 3 ? "good" : "moderate"; row.video_er_grade = row.video_er >= 4.5 ? "good" : "moderate"; row.seen = row.views;
      creators.push(row);
    });
    var tot = { likes: 0, comments: 0, engagement: 0, views: 0, reach: 0, impressions: 0, shares: 0, saves: 0, clicks: 0 };
    creators.forEach(function (r) { for (var k in tot) tot[k] += r[k]; });
    var exposure = tot.views;
    creators.forEach(function (r) {
      r.parts = { exposure: Math.round(r.views / exposure * 1000) / 10, engagement: Math.round(r.engagement / tot.engagement * 1000) / 10, er: r.er, clicks: Math.round(r.clicks / tot.clicks * 1000) / 10 };
      r.score = Math.round(r.parts.exposure * 0.4 + r.parts.engagement * 0.4 + r.parts.clicks * 0.2);
    });
    creators.sort(function (a, b) { return b.score - a.score; });
    creators.forEach(function (r, i) { r.rank = i + 1; r.badge = ["gold", "silver", "bronze"][i] || null; });
    var planned = CREW.reduce(function (s, c) { return s + c[1]; }, 0);
    var total = Object.assign({ seen: exposure, hidden_likes: 0, posts: posts.length, er: 4.6, video_er: tot.engagement / exposure * 100, imp_er: null, exposure: exposure,
      ctr: Math.round(tot.clicks / exposure * 10000) / 100, real_share: 0.4, adjusted: [], planned: planned, delivered: posts.length, er_grade: "good", ctr_grade: "good", video_er_grade: "good" }, tot);
    var hist = [];
    for (var d = 11; d >= 0; d--) {
      var share = (12 - d) / 12;
      hist.push({ d: iso(NOW - d * DAY), likes: Math.round(tot.likes * share), comments: Math.round(tot.comments * share), views: Math.round(tot.views * share) });
    }
    var stepsDef = [["brief", "Briefing & strategy", -30, -26], ["sourcing", "Sourcing & casting", -26, -21], ["approval", "Client approval", -21, -19], ["prep", "Content preparation", -19, -15],
      ["shooting", "Shooting", -15, -11], ["logistics", "Logistics & product delivery", -16, -13], ["review", "Content review", -11, -2], ["publishing", "Publishing", -10, 18], ["reporting", "Reporting", 0, 21]];
    var steps = stepsDef.map(function (s) { return { key: s[0], label: s[1], on: true, start: iso(NOW + s[2] * DAY), end: iso(NOW + s[3] * DAY), state: s[3] < 0 ? "done" : s[2] <= 0 ? "active" : "pending" }; });
    var byDay = [];
    for (var b = 11; b >= 0; b--) byDay.push({ d: iso(NOW - b * DAY), n: Math.round(tot.clicks / 12 * (0.6 + ((11 - b) % 5) * 0.2)) });
    return { ok: true, report: {
      campaign: { id: 1, name: CAMPAIGN, client: BRAND, status: "live", starts_at: start, ends_at: end, platform: null, phase: "Publishing", status_note: null, logos: [], steps: steps },
      total: total, creators: creators, posts: posts, history: hist, visibility: { clicks: true, all_content: false, reach: true }, updated_at: NOW - 5 * 3600,
      verdict: { key: "good", label: "On track", grade: "good" },
      objective: { key: "engagement", label: "Awareness + Engagement", kpis: ["engagement", "er", "clicks"], weights: { exposure: 0.4, engagement: 0.4, er: 0, clicks: 0.2 }, links: true },
      plan: null, gaps: { posts: posts.length, likes_hidden: 0, hidden: [], no_shares: 0, no_saves: 0, reach_estimated: 0 },
      progress: { elapsed: 0.4, overall: 112, due: 40, all_met: false, items: [
        { key: "posts", goal: planned, actual: posts.length, pct: posts.length / planned * 100, expected: planned * 0.4, grade: "good" },
        { key: "views", goal: 2400000, actual: tot.views, pct: tot.views / 24000, expected: 960000, grade: "good" },
        { key: "engagement", goal: 110000, actual: tot.engagement, pct: tot.engagement / 1100, expected: 44000, grade: "good" },
        { key: "er", goal: 3.5, actual: 4.6, pct: 131, expected: 3.5, grade: "good" },
        { key: "clicks", goal: 18000, actual: tot.clicks, pct: tot.clicks / 180, expected: 7200, grade: "moderate" }] },
      benchmarks: { er: BENCH.er, video_er: BENCH.video_er, view_rate: BENCH.view_rate, story_rate: BENCH.story_rate, ctr: BENCH.ctr,
        bands: { nano: "Nano (<20K)", micro: "Micro (20–100K)", mid: "Mid (100–500K)", macro: "Macro (500K–1M)", mega: "Mega (1M+)" } },
      audience: { countries: [{ code: "SA", pct: 76.4 }, { code: "AE", pct: 7.9 }, { code: "KW", pct: 4.6 }, { code: "EG", pct: 3.2 }, { code: "BH", pct: 2.1 }], coverage: 72, basis: "measured", profiles: 4 },
      reach_basis: { per_view: 0.88 },
      clicks: { clicks: tot.clicks, uniques: Math.round(tot.clicks * 0.81), by_day: byDay,
        by_app: [{ k: "Instagram", n: Math.round(tot.clicks * 0.46) }, { k: "TikTok", n: Math.round(tot.clicks * 0.31) }, { k: "Snapchat", n: Math.round(tot.clicks * 0.23) }],
        by_device: [{ k: "iPhone", n: Math.round(tot.clicks * 0.58) }, { k: "Android", n: Math.round(tot.clicks * 0.37) }, { k: "Desktop", n: Math.round(tot.clicks * 0.05) }],
        by_country: [{ k: "SA", n: Math.round(tot.clicks * 0.79) }, { k: "AE", n: Math.round(tot.clicks * 0.09) }, { k: "KW", n: Math.round(tot.clicks * 0.05) }],
        by_creator: creators.map(function (r) { return { k: r.name, n: r.clicks }; }).sort(function (a, b) { return b.n - a.n; }), links: 6, has_destination: true }
    } };
  }
  function versus() {
    return { ok: true, items: [{ campaign: CAMPAIGN, token: CAMP, saved_at: NOW - 20 * DAY, ended: false, rows: [
      { key: "views", label: "Views", estimate: 1900000, range: [1500000, 2300000], actual: 2310000, position: "above", sig: { grade: "good", label: "Above the range" }, delta: "+22%" },
      { key: "engagement", label: "Interactions", estimate: 88000, range: [70000, 110000], actual: 101000, position: "within", sig: { grade: "good", label: "Within the range" }, delta: "+15%" },
      { key: "clicks", label: "Link clicks", estimate: 14000, range: [11000, 17000], actual: 9800, position: "below", sig: { grade: "low", label: "Below the range" }, delta: "−30%" }],
      helvy: "Views came in above the estimated range. Link clicks fell below it: a swipe-up story in week 3 would help." }] };
  }
  var STEPS_DONE = { job_title: 1, brands: 1, industry_markets: 1 };
  function accountBody() {
    var sels = [], camps = [], codes = STATE.codes, n = { review: 0, approved: 0, rejected: 0, unavailable: 0 };
    codes.forEach(function (c) { n[(STATE.status[c] || { s: "review" }).s] += 1; });
    var chip = { key: STATE.lc, label: LC_LABEL[STATE.lc] };
    sels.push({ name: SEL_NAME, token: SEL, creators: codes.length, updated_at: NOW - 600, mine: true, owner: null, can_delete: false,
                counts: { creators: codes.length, influencers: codes.length - 2, doctors: 2, review: n.review, approved: n.approved, rejected: n.rejected, unavailable: 0 }, quote: chip });
    var cb = (STATE.lc === "live" || STATE.lc === "completed") ? campaignBody().report : null;
    if (cb) camps.push({ token: CAMP, name: CAMPAIGN, status: "live", starts_at: cb.campaign.starts_at, ends_at: cb.campaign.ends_at, verdict: { label: "On track", grade: "good" },
      exposure: cb.total.exposure, reach: cb.total.reach, views: cb.total.views, er: cb.total.er, er_grade: "good", delivered: cb.total.delivered, planned: cb.total.planned,
      updated_at: cb.updated_at, quote: chip });
    var steps = [["photo", 2, "Add your photo"], ["job_title", 2, "Add your job title"], ["phone", 3, "Add your phone number"], ["logo", 3, "Add your company logo"],
                 ["brands", 5, "Add your brands and products"], ["industry_markets", 5, "Add your industry and markets"]].map(function (s) {
      return { key: s[0], credits: s[1], label: s[2], done: !!STEPS_DONE[s[0]], paid: !!STEPS_DONE[s[0]] };
    });
    return { ok: true,
      user: { email: "demo@northwind.example", name: Demo.user, company: BRAND, job_title: "Brand Manager", phone: "", created_at: NOW - 20 * DAY, photo: null, logo: null,
              brands: "Northwind", industry: "Pharma", markets: ["SA"], language: "English" },
      completion: { pct: 70, steps: steps, bonus: 10, bonus_paid: false, waiting: 18, fields: {}, missing: steps.filter(function (s) { return !s.done; }).map(function (s) { return { key: s.key, label: s.label }; }) },
      credits: STATE.credits, monthly_credits: 30, next_refill: NOW + 9 * DAY, costs: { brief: 5, parse: 1, chat: 1, search: 0, replace: 2, more: 3, alike: 2 }, kam: "Marwa M.",
      insights: { live_campaigns: camps.length, exposure: cb ? cb.total.exposure : 0, reach: cb ? cb.total.reach : 0, views: cb ? cb.total.views : 0, er: cb ? cb.total.er : null, er_grade: cb ? "good" : null,
                  delivered: cb ? cb.total.delivered : 0, planned: cb ? cb.total.planned : 0, shortlisted: codes.length, tiers: { "Macro": 1, "Mid-Tier": 2, "HCP - Mid-Tier": 2 } },
      campaigns: camps, selections: sels, analyses: [], briefs: [{ id: 1, can_delete: false, summary: "A Ramadan skincare launch in the Gulf.", objective: "Awareness+Engagement", source: "ai", at: NOW - 2 * DAY, selection: SEL, selection_name: SEL_NAME }],
      notifications: { items: clone(STATE.notes), unread: STATE.notes.filter(function (x) { return x.unread; }).length,
                       prefs: { analysis: true, selections: true, campaigns: true, account: true, ideas: false }, counts: { analysis: 1, selections: STATE.notes.length - 1 } },
      ledger: [{ delta: 30, reason: "Welcome credits", at: NOW - 20 * DAY, balance: 30 }],
      invite: { token: "demo", credits: 20, max: 5, paid: 0, left: 5, list: [] },
      next: { kind: "profile", lead: "Add your phone number and earn ", strong: "+3 credits", tail: ". Helvy uses it to reach you about quotes.", cta: "Finish your profile", href: "account/#account" },
      markets: [{ value: "SA", label: "Saudi Arabia" }, { value: "AE", label: "UAE" }, { value: "EG", label: "Egypt" }], industries: [{ value: "Pharma", label: "Pharma" }, { value: "Beauty", label: "Beauty" }],
      languages: ["Arabic", "English", "Arabic and English"], team: [] };
  }

  /* ============================================================ questions, briefs and chat */
  // The brief questions exactly as the server serves them (matcher.public_questions()).
  var QUESTIONS = [{"id":"goal","type":"one","multi_ok":true,"label":"What is the main goal of the campaign?","required":true,"options":[{"value":"awareness","label":"Awareness"},{"value":"engagement","label":"Engagement"},{"value":"traffic","label":"Traffic"}],"other":true},{"id":"platforms","type":"many","label":"Where should the content run?","required":true,"options":[{"value":"Instagram","label":"Instagram"},{"value":"TikTok","label":"TikTok"},{"value":"Snapchat","label":"Snapchat"},{"value":"YouTube","label":"YouTube"},{"value":"any","label":"No preference"}],"other":true},{"id":"market","type":"one","multi_ok":true,"multi_max":4,"label":"Which countries is the audience in?","required":true,"options":[{"value":"SA","label":"Saudi Arabia"},{"value":"AE","label":"UAE"},{"value":"EG","label":"Egypt"},{"value":"KW","label":"Kuwait"},{"value":"QA","label":"Qatar"},{"value":"BH","label":"Bahrain"},{"value":"OM","label":"Oman"},{"value":"JO","label":"Jordan"}],"other":true},{"id":"gender","type":"one","multi_ok":true,"multi_max":2,"label":"Who is the audience?","required":false,"options":[{"value":"Any","label":"Everyone"},{"value":"Women","label":"Mostly women"},{"value":"Men","label":"Mostly men"}],"other":true},{"id":"age","type":"one","multi_ok":true,"multi_max":4,"label":"Main age groups","required":false,"options":[{"value":"Any","label":"All ages"},{"value":"18-24","label":"18–24"},{"value":"25-34","label":"25–34"},{"value":"35-44","label":"35–44"},{"value":"45-54","label":"45+"}],"other":true},{"id":"category","type":"many","label":"Which space is the product in?","required":true,"options":[{"value":"health care","label":"Healthcare / pharma"},{"value":"skincare","label":"Skincare & dermatology"},{"value":"beauty","label":"Beauty"},{"value":"hair care","label":"Hair care"},{"value":"fragrance","label":"Fragrance"},{"value":"mother & baby","label":"Mother & baby"},{"value":"food","label":"Food & drink"},{"value":"fitness","label":"Fitness & wellness"},{"value":"fashion","label":"Fashion"},{"value":"lifestyle","label":"Lifestyle"},{"value":"technology","label":"Technology"},{"value":"automotive","label":"Automotive"},{"value":"travel","label":"Travel"},{"value":"finance","label":"Finance"},{"value":"gaming","label":"Gaming"}],"other":true},{"id":"budget","type":"one","label":"Budget for creators (SAR, before VAT)","required":false,"options":[{"value":"50","label":"Under 50,000"},{"value":"150","label":"50,000 – 150,000"},{"value":"400","label":"150,000 – 400,000"},{"value":"400+","label":"Over 400,000"},{"value":"open","label":"Not decided yet"}],"other":true},{"id":"count","type":"one","label":"How many creators?","required":false,"options":[{"value":"5","label":"3 – 5"},{"value":"8","label":"6 – 10"},{"value":"15","label":"11 – 20"},{"value":"25","label":"20 or more"}],"other":true},{"id":"deliverable","type":"many","label":"What should they make?","required":false,"options":[{"value":"reels","label":"Reels / short videos"},{"value":"ugc","label":"UGC content for our own channels"},{"value":"stories","label":"Stories"},{"value":"event","label":"Event or store attendance"},{"value":"review","label":"Product reviews"}],"other":true},{"id":"timing","type":"one","label":"When does it start?","required":false,"options":[{"value":"asap","label":"Within 2 weeks"},{"value":"month","label":"Within 6 weeks"},{"value":"quarter","label":"Next quarter"},{"value":"later","label":"Just exploring"}],"other":true},{"id":"notes","type":"text","label":"Anything else we should know?","required":false,"max":600,"options":[],"other":false}];
  var ANSWERS_ON_FILE = { goal: ["awareness", "engagement"], platforms: ["Instagram", "TikTok"], market: ["SA", "AE"], category: ["skincare"], count: "5" };
  function briefRun() {
    var ps = {}, picks = PICKS.map(function (c, i) {
      var p = BY[c], s = scoreFor(p), pl = {};
      p.platforms.forEach(function (x, k) { pl[x.platform] = s.score - 3 * k; });
      ps[c] = pl;
      return { code: c, score: s.score, why: (p.score.strengths[0] || "A close fit for the brief") + (i === 0 ? "" : "") };
    });
    return { ok: true, picks: picks, platform_scores: ps, credits: STATE.credits, brief: 1, token: SEL, name: "Skincare · KSA + UAE · Awareness + Engagement",
             summary: picks.length + " creators match your brief, best fit first.", timing: null };
  }
  function findPerson(text, skip) {
    var t = String(text || "").toLowerCase();
    return PEOPLE.filter(function (p) {
      var first = p.name.replace(/^Dr\.\s*/i, "").split(" ")[0].toLowerCase();
      return (t.indexOf(first) > -1) && (!skip || p.code !== skip);
    });
  }
  function cardOf(c) {
    var p = BY[c];
    return { code: p.code, name: p.name, photo_url: photo(p.photo), fit: p.score.overall, followers: prim(p).followers, city: p.city, tier: p.tier.replace(/^HCP - /, "Doctor · ") };
  }
  // What Helvy says, as the streamed events the real chat sends (step* delta* done).
  function chatEvents(text) {
    var t = String(text || ""), ev = [], reply, extra = {};
    var step = function (ms, s) { ev.push([ms, { t: "step", text: s }]); };
    var names = findPerson(t);
    if (/discount|rate|price|cost|cheap|budget|negotiat|fee/i.test(t)) {
      step(500, "Reading your message"); step(900, "Reading your campaign");
      reply = "I don't quote or negotiate prices. Your account manager prepares the quote and can discuss rates; I can send them this chat and your selection in one tap.";
      extra = { handoff: { reason: "pricing" }, next: [] };
    } else if (/compare|versus|\bvs\b|side by side/i.test(t) && names.length >= 1) {
      var a = names[0], b = names[1] || BY[a.code === "DEMO-05" ? "DEMO-01" : "DEMO-05"];
      step(500, "Reading your message"); step(900, "Comparing creators"); step(900, "Scoring fit");
      var line = function (k, x, y) { return "• " + k + ": **" + x + "** vs **" + y + "**"; };
      var A = prim(a), B = prim(b);
      reply = "**" + a.name + " vs " + b.name + "**\n" +
        line("Fit score", a.score.overall, b.score.overall) + "\n" + line("Engagement", A.er + "%", B.er + "%") + "\n" +
        line("Women in the audience", a.audience.female + "%", b.audience.female + "%") + "\n" +
        (function () {
          var fit = a.score.overall >= b.score.overall ? a : b, reach = A.followers > B.followers ? a : b;
          return fit === reach ? fit.name + " leads on fit and brings more reach." : fit.name + " leads on fit; " + reach.name + " brings more reach.";
        })();
      extra = { next: ["Why did " + a.name.replace(/^Dr\.\s*/, "").split(" ")[0] + " score " + a.score.overall + "?", "Talk to a person"] };
    } else if (/why|explain|score|fit/i.test(t) && names.length) {
      var p = names[0], s = p.score;
      step(500, "Reading your message"); step(900, "Scoring fit"); step(900, "Checking engagement");
      reply = "**" + p.name + " scores " + s.overall + "/100** for your brief. What helps: " + s.strengths.slice(0, 2).join("; ") + ". " +
        "Confidence is **" + s.confidence.level + "**: " + s.confidence.posts + " posts measured" + (s.limited_data ? ", so read it as a first look." : ".");
      extra = { next: ["Compare " + p.name.replace(/^Dr\.\s*/, "").split(" ")[0] + " with Nada", "Talk to a person"] };
    } else if (/\d+\s*creators?/i.test(t) && /reach|what can|ideal|mix|structure/i.test(t)) {
      step(500, "Reading your request"); step(900, "Building the recommended structure"); step(900, "Working out the views");
      var r = roiAnswer({ goals: ["awareness"], platforms: PLATS, count: 10, mix: { macro: 0 } });
      reply = "For **10 creators** on Instagram and TikTok, HelloVoice's recommended structure for awareness is below. It's an estimate, not a result.";
      extra = { roi: Object.assign({ ideal_only: true, creators: 0 }, r), next: ["Find creators", "Talk to a person"] };
    } else {
      step(500, "Reading your brief"); step(1000, "Searching creators"); step(1100, "Scoring fit"); step(900, "Picking the best five");
      var top = PICKS.slice(0, 5);
      reply = "Here are **5 creators** for a Ramadan skincare launch, best fit first. " + BY[top[0]].name + " leads: " + (BY[top[0]].score.strengths[0] || "a close fit") + ".";
      extra = { cards: top.map(cardOf), next: ["Save all as a selection", "What is the ideal creator mix?"] };
    }
    var cut = reply.indexOf(". ", 40) + 2 || reply.length;
    ev.push([300, { t: "delta", text: reply.slice(0, cut) }]);
    ev.push([300, { t: "delta", text: reply.slice(cut) }]);
    ev.push([100, Object.assign({ t: "done", thread: "demo", reply: reply }, extra)]);
    return ev;
  }

  /* ================================================================ the demo's API */
  var DEMO_PLACE = { Riyadh: "Saudi Arabia|Riyadh", Jeddah: "Saudi Arabia|Jeddah", Dammam: "Saudi Arabia|Dammam" };
  function demoFacets() {
    var rows = PEOPLE.map(rosterRow);
    function order(fn) {
      var n = {}, keys = [];
      rows.forEach(function (r) { fn(r).forEach(function (v) { if (!n[v]) { n[v] = 0; keys.push(v); } n[v]++; }); });
      return keys.sort(function (a, b) { return n[b] - n[a]; });
    }
    return { tier: order(function (r) { return [r.tier]; }), platform: order(function (r) { return r.platform.split(", "); }),
             place: order(function (r) { return [DEMO_PLACE[r.city]]; }), interest: order(function (r) { return [r.interest]; }) };
  }
  function demoPage(q) {
    var rows = PEOPLE.map(rosterRow), any = false;
    var total = function (r) { return r.profiles.reduce(function (t, x) { return t + x.followers; }, 0); };
    [["tier", function (r) { return [r.tier]; }], ["platform", function (r) { return r.platform.split(", "); }],
     ["place", function (r) { return [DEMO_PLACE[r.city]]; }], ["interest", function (r) { return [r.interest]; }]].forEach(function (d) {
      var want = q.getAll(d[0]);
      if (!want.length) return;
      any = true;
      rows = rows.filter(function (r) { return d[1](r).some(function (v) { return want.indexOf(v) !== -1; }); });
    });
    var lic = q.getAll("lic");
    if (lic.length) { any = true; rows = rows.filter(function (r) { return BY[r.code].licences.some(function (c) { return lic.indexOf(c) !== -1; }); }); }
    var text = (q.get("q") || "").toLowerCase();
    if (text) { any = true; rows = rows.filter(function (r) { return (r.name + " " + r.code).toLowerCase().indexOf(text) !== -1; }); }
    var lo = +q.get("fmin") || 0, hi = +q.get("fmax") || 0;
    if (lo || hi) { any = true; rows = rows.filter(function (r) { var f = total(r); return (!lo || f >= lo) && (!hi || f <= hi); }); }
    var sort = q.has("sort") ? q.get("sort") : "followers-desc";
    if (sort === "followers-desc") rows.sort(function (a, b) { return total(b) - total(a); });
    if (sort === "followers-asc") rows.sort(function (a, b) { return total(a) - total(b); });
    if (sort === "name") rows.sort(function (a, b) { return a.name.localeCompare(b.name); });
    var g = q.get("group");
    if (g) {
      var gk = function (r) { return g === "tier" ? r.tier : g === "platform" ? r.platform.split(", ")[0] : g === "country" ? "Saudi Arabia" : r.interest; };
      rows = rows.map(function (r) { return Object.assign({}, r, { g: gk(r) }); });
      rows.sort(function (a, b) { return a.g < b.g ? -1 : a.g > b.g ? 1 : 0; });
    }
    var out = { ok: true, items: rows, has_more: false, cursor: null, v: "demo" };
    if (any) out.match = rows.length;
    if (!q.get("cursor")) { out.tiers = TIERS; out.fx = FX; out.exp = NOW + DAY; }
    return out;
  }
  // answer(method, path, query, body) -> { s, b, wait?, stream? }: the one place the demo's API lives,
  // so the tests can ask it the same questions the pages do and compare its shapes with the server's.
  function ok(b, wait) { return { s: 200, b: b, wait: wait || 0 }; }
  function answer(method, p, q, body) {
    var m = String(method || "GET").toUpperCase(), user = Demo.user;
    body = body || {};
    if (p === "/api/me") return ok(me());
    if (p === "/api/roster") return ok({ ok: true, roster: PEOPLE.map(rosterRow), tiers: TIERS, fx: FX, exp: NOW + DAY });
    // The catalogue in batches: the demo roster is one batch, filtered and sorted here.
    if (p === "/api/roster/facets") return ok({ ok: true, v: "demo", facets: demoFacets() });
    if (p === "/api/roster/cards") {
      var want = (q.get("codes") || "").split(",").filter(function (c) { return BY[c]; });
      return ok({ ok: true, cards: want.map(function (c) { return rosterRow(BY[c]); }), tiers: TIERS, fx: FX, exp: NOW + DAY });
    }
    if (p === "/api/roster/page") return ok(demoPage(q));
    if (p === "/api/licences") {
      var lic = {};
      PEOPLE.forEach(function (x) { if (x.licences.length) lic[x.code] = x.licences.map(function (c) { return { country: c, name: c === "SA" ? "Mawthooq" : "UAE Advertiser Permit", number: "" }; }); });
      return ok({ ok: true, licences: lic });
    }
    if (p === "/api/notifications") return ok({ ok: true, unread: STATE.notes.filter(function (n) { return n.unread; }).length, items: clone(STATE.notes) });
    if (p === "/api/notifications/read") { STATE.notes.forEach(function (n) { n.unread = false; }); return ok({ ok: true, unread: 0 }); }
    if (p === "/api/brief/scores") {
      var sc = {}; PEOPLE.forEach(function (x) { sc[x.code] = [x.score.overall, tagOf(x.score.overall), "analysis"]; });
      return ok({ ok: true, scores: sc });
    }
    if (p === "/api/brief/questions") return ok({ ok: true, questions: QUESTIONS });
    // the selection has its brief on file (the page would otherwise offer to score it)
    if (p === "/api/brief/for") return ok({ ok: true, brief: { id: 1, summary: "A Ramadan skincare launch in the Gulf.", objective: "Awareness+Engagement", source: "ai", at: NOW - 2 * DAY, answers: ANSWERS_ON_FILE } });
    if (p === "/api/brief/run") return ok(briefRun(), 7000);
    if (p === "/api/selection" && m === "GET") return ok(selectionBody());
    if (p === "/api/selection" && m === "POST") {
      // the page saved its shortlist (add / remove): kept for this run only, and the new ones start under review
      var codes = (body.codes || []).filter(function (c) { return BY[c]; });
      if (codes.length) STATE.codes = codes;
      var lc = lifecycle();
      return ok({ ok: true, token: SEL, lifecycle: lc.warn ? lc : null });
    }
    if (p === "/api/selection/status") {
      var cur = STATE.status[body.code] || { s: "review", by: "", hv: false, at: null, reason: "", note: "", replacements: [] };
      cur = Object.assign({}, cur, { s: body.status, by: user, at: NOW, reason: body.status === "rejected" ? cur.reason : "", note: "" });
      STATE.status[body.code] = cur;
      return ok({ ok: true, status: clone(cur) });
    }
    if (p === "/api/selection/reason") {
      var r0 = Object.assign({}, STATE.status[body.code] || { s: "rejected" }, { reason: body.reason || "", note: body.note || "" });
      STATE.status[body.code] = r0;
      return ok({ ok: true, status: clone(r0) });
    }
    if (p === "/api/selection/replace") return ok({ ok: true, spent: 0, credits: STATE.credits, replacements: ["DEMO-08", "DEMO-04"].map(function (c) { return rosterRow(BY[c]); }) }, 4200);
    if (p === "/api/selection/quote/approve") {
      setLc("approved");
      return ok({ ok: true, lifecycle: lifecycle() });
    }
    if (p === "/api/voice/selection") return ok(voiceSelection());
    if (p === "/api/voice/selections") return ok({ ok: true, selections: [{ token: SEL, name: SEL_NAME, codes: STATE.codes.slice(), mine: true }] });
    if (p === "/api/roi/saved") return ok({ ok: true, saved: null, seed: { goals: GOALS.slice(), platforms: PLATS.slice(), count: 0 } });
    if (p === "/api/roi/estimate") return ok({ ok: true, result: roiAnswer(body) }, 250);
    if (p === "/api/roi/save") return ok({ ok: true });
    if (p === "/api/roi/vs") return ok(versus());
    if (p === "/api/roi/selections") return ok({ ok: true, selections: [{ token: SEL, name: SEL_NAME }] });
    if (p === "/api/analysis/sample") return ok(sampleBody(), 150);
    if (p === "/api/creator") return ok(creatorBody(String(q.get("c") || "").toUpperCase()));
    if (p === "/api/creator/request") {
      var code = String(body.code || "").toUpperCase();
      STATE.asked[code] = NOW;
      return ok({ ok: true, gate: { state: "requested", requested_at: NOW, ready_by: NOW + DAY, selections: [{ token: SEL, name: SEL_NAME }] } }, 500);
    }
    if (p === "/api/campaigns") return ok({ ok: true, campaigns: [{ token: CAMP, name: CAMPAIGN, client: BRAND, status: "live", phase: "Publishing", starts_at: NOW - 12 * DAY, ends_at: NOW + 18 * DAY, logos: [] }] });
    if (p === "/api/campaign") return ok(campaignBody());
    // the profile page draws with the portal layer's helpers, which load after it: a real server is never this quick
    if (p === "/api/account") return ok(accountBody(), 450);
    if (p === "/api/chat/stream") return { s: 200, stream: chatEvents(body.message || "") };
    if (p === "/api/chat/history") return ok({ ok: true, messages: [] });
    if (p === "/api/chat/handoff") { STATE.handoff = true; return ok({ ok: true, message: "Sent to your account manager with this chat and your selection. They usually reply within one working day." }, 700); }
    if (p === "/api/voice/handoff") { STATE.handoff = true; return ok({ ok: true, kam: "Marwa M." }, 700); }
    if (p === "/api/request") {
      if (STATE.lc === "draft") setLc("requested");
      return ok({ ok: true, id: "demo" }, 700);
    }
    // Anything else (events, saves, the selection's own POST): accepted and forgotten.
    return ok(m === "GET" ? { ok: true, items: [] } : { ok: true, token: SEL });
  }

  /* ============================================================== the frame's shim */
  function json(win, body, status) {
    return new win.Response(JSON.stringify(body), { status: status || 200, headers: { "Content-Type": "application/json" } });
  }
  function later(ms, fn) { return new Promise(function (done) { setTimeout(function () { done(fn()); }, REDUCE ? Math.min(ms, 400) : ms); }); }
  function streamOf(win, events) {
    var enc = new TextEncoder();
    var body = new win.ReadableStream({
      start: function (ctl) {
        var i = 0;
        (function next() {
          if (i >= events.length) { ctl.close(); return; }
          var e = events[i++];
          setTimeout(function () { ctl.enqueue(enc.encode(JSON.stringify(e[1]) + "\n")); next(); }, REDUCE ? 60 : e[0]);
        })();
      }
    });
    return new win.Response(body, { status: 200, headers: { "Content-Type": "application/x-ndjson" } });
  }
  function route(win, url, init) {
    var u = new URL(url, win.location.href), p = u.pathname.replace(/^.*?\/api\//, "/api/");
    var body = {};
    try { body = init.body ? JSON.parse(init.body) : {}; } catch (e) { body = {}; }
    var a = answer(init.method || "GET", p, u.searchParams, body);
    if (a.stream) return Promise.resolve(streamOf(win, a.stream));
    if (a.wait) return later(a.wait, function () { return json(win, a.b, a.s); });
    return Promise.resolve(json(win, a.b, a.s));
  }
  function memStore(seed) {
    var m = {}; Object.keys(seed || {}).forEach(function (k) { m[k] = String(seed[k]); });
    return { getItem: function (k) { return Object.prototype.hasOwnProperty.call(m, k) ? m[k] : null; }, setItem: function (k, v) { m[k] = String(v); },
             removeItem: function (k) { delete m[k]; }, clear: function () { m = {}; }, key: function (i) { return Object.keys(m)[i] || null; },
             get length() { return Object.keys(m).length; } };
  }
  var Demo = window.hvTourDemo = {
    active: false, user: "Sara Haddad", answer: answer, setRoster: setRoster, reset: function (user) { Demo.user = user || Demo.user; STATE = freshState(Demo.user); return STATE; },
    state: function () { return STATE; }, estimate: roiAnswer, lifecycle: lifecycle, setLc: setLc, QUESTIONS: QUESTIONS,
    install: function (win) {
      win.hvDemo = true;
      var mem = { local: memStore({ "hv-chat-big": "0" }), session: memStore({ "hv_brief": "demo", "hv-tip:catalogue": "1", "hv-tip:creator": "1", "hv-tip:selection": "1", "hv-tip:campaign": "1", "hv-tip:account": "1", "cx-offer-shown": "1", "cat-ok": "1" }) };
      try { Object.defineProperty(win, "localStorage", { configurable: true, get: function () { return mem.local; } }); } catch (e) { /* stays real: reads only */ }
      try { Object.defineProperty(win, "sessionStorage", { configurable: true, get: function () { return mem.session; } }); } catch (e) { /* idem */ }
      var jar = "cat-ok=1";
      try { Object.defineProperty(win.document, "cookie", { configurable: true, get: function () { return jar; }, set: function () { /* kept out of the real jar */ } }); } catch (e) { /* idem */ }
      var real = win.fetch ? win.fetch.bind(win) : null;
      win.fetch = function (input, init) {
        var url = typeof input === "string" ? input : (input && input.url) || "";
        var o = init || {};
        if (typeof input !== "string" && input && input.method && !o.method) o = Object.assign({ method: input.method }, o);
        if (/\/api\//.test(url)) return route(win, url, o);
        // The quote form also posts to a mail endpoint on another site: in the demo that is answered
        // here, so a demo request can never send an email.
        var to = null;
        try { to = new URL(url, win.location.href); } catch (e) { to = null; }
        if (to && to.origin !== win.location.origin) return Promise.resolve(json(win, { success: "true", ok: true }));
        return real(input, init);
      };
      win.open = function () { return null; };
      // Outside links and placeholder links stay put; portal pages open inside the demo.
      win.document.addEventListener("click", function (e) {
        var a = e.target && e.target.closest && e.target.closest("a[href]");
        if (!a) return;
        var href = a.getAttribute("href") || "", to;
        try { to = new URL(href, win.location.href); } catch (x) { e.preventDefault(); return; }
        if (/^#demo/.test(href) || to.origin !== win.location.origin || /^\/admin(\/|$)/.test(to.pathname) || a.target === "_blank" || a.hasAttribute("download")) {
          e.preventDefault(); e.stopPropagation();
        }
      }, true);
      win.document.addEventListener("DOMContentLoaded", function () {
        // The catalogue's showreel is not part of the tour: it never downloads in the frame.
        [].forEach.call(win.document.querySelectorAll(".cat-showreel video"), function (v) { v.removeAttribute("data-src"); v.removeAttribute("src"); v.preload = "none"; });
        var st = win.document.createElement("style");
        st.textContent = "body.cat-away::after{content:none!important;display:none!important}" +
          // on a phone the tour card and its Helvy sit where the chat launcher is
          "@media (max-width:760px){.hv-launch,.hv-nudge{display:none!important}}";
        win.document.head.appendChild(st);
      });
      // The tour's keys work while the frame has focus too (Esc, arrows; not while typing).
      win.document.addEventListener("keydown", function (e) {
        var t = e.target, typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
        if (typing || !window.hvTour || !window.hvTour.key) return;
        if (e.key === "Escape" || e.key === "ArrowRight" || e.key === "ArrowLeft") window.hvTour.key(e);
      });
      win.document.addEventListener("submit", function (e) { if (!/cat-gate/.test((e.target && e.target.id) || "")) return; e.preventDefault(); }, true);
    }
  };

  /* ================================================================= the tour */
  var h = HV.h, api = HV.api;
  function ic(n) { return HV.icon ? HV.icon(n, "tv-i") : ""; }
  function clipNode(name, cls, opts) { return HV.clip ? HV.clip(name, cls, opts) : h("span"); }
  // name, icon, the chapter's one line
  var CHAPTERS = [["Brief", "chat", "Tell Helvy what the campaign is."], ["Shortlist", "list", "Helvy scores the roster for you."],
                  ["Check a creator", "shield", "See what is open and what is locked."], ["Plan", "calc", "Test the structure before you book."],
                  ["Ask Helvy", "sparkle", "Questions answered, with a person behind him."], ["Quote", "mail", "Request it, approve it, go live."],
                  ["Follow", "chart", "Results, estimate vs actual, your profile."]];
  // A query per view, so two views of one page are two real page loads.
  var PAGES = { catalogue: "?tour=1", selection: "selection/?tour=1#s=" + SEL, creator: "creator/?tour=1#c=DEMO-05", campaign: "campaign/?tour=1#t=" + CAMP, account: "account/?tour=1#overview" };
  var WAIT_FOR = { catalogue: ".cat-card[data-code]", selection: "#sel-statusbar", creator: "#pp-gate-band", campaign: "#mx-verdict", account: ".hc-score" };
  var ANS = { goal: ["awareness", "engagement"], platforms: ["Instagram", "TikTok"], market: ["SA", "AE"], category: ["skincare"], budget: "open", count: "5" };

  // One chapter = one stop; each beat is one sentence and one action. Next walks the beats, then the chapters.
  var STOPS = [
    { ch: 0, name: "Brief", beats: [
      { view: "catalogue", fresh: true, target: "#ai-sl", clip: "hello", run: "aiAsk0", pad: 10,
        t: "Set the campaign goals", p: "Pick one goal or several; Helvy weighs them together.", hint: "Awareness and Engagement are both on." },
      { target: "#ai-sl", clip: "point", run: "aiAsk2", pad: 10,
        t: "Choose the countries", p: "Add every country your audience lives in.", hint: "Saudi Arabia and the UAE are picked." }
    ] },
    { ch: 1, name: "Shortlist", beats: [
      { target: "#ai-sl", clip: "thinking", run: "aiGo", pad: 10,
        t: "Helvy builds the shortlist", p: "He scores the whole roster against your brief and returns the best fits." },
      { view: "selection", fresh: true, target: ".cat-card[data-code='DEMO-06'] .cat-score", clip: "point", run: "scoreTip", pad: 8,
        t: "Every creator carries a fit score", p: "Hover the score to see why, and how much data stands behind it." },
      { target: ".cat-card[data-code='DEMO-08'] .cat-score", clip: "point", run: "scoreTip", pad: 8,
        t: "Thin data is labelled", p: "Where Helvy has little to read, the score says Limited data: a first look, not a verdict." }
    ] },
    { ch: 2, name: "Check a creator", beats: [
      { view: "creator", fresh: true, target: "#pp-gate-band", clip: "point",
        t: "Headline numbers are free", p: "Followers, platforms, views and engagement are open; the rest stays locked until you ask." },
      { target: ".pp-gbtn--sample", also: ".pp-sample", clip: "point", run: "sampleHover", pad: 10,
        t: "See a sample first", p: "One tap opens a sample full analysis of an anonymised creator." },
      { target: "#pp-gate-band", clip: "point", run: "sampleOpen",
        t: "What a full analysis holds", p: "Audience, authenticity, growth, content and brand history." }
    ] },
    { ch: 3, name: "Plan", beats: [
      { view: "selection", fresh: true, target: ".cx-btn--roi", clip: "point", run: "roiOpen", pad: 10, narrow: true,
        t: "Plan with the ROI calculator", p: "Open it from your selection to test the structure before you book." },
      { target: ".cx-count", clip: "point", run: "roiCount", pad: 10, narrow: true,
        t: "Choose how many creators", p: "Set the number you want to run; the recommended structure updates for it." },
      { target: ".cx-res__top", also: ".cx-gap", clip: "point", run: "roiQuality", pad: 10, narrow: true,
        t: "Selection quality and the gap", p: "Quality compares your picks with the recommended structure, and the gap says what is missing." },
      { target: ".cx-waysbox", clip: "approve", run: "roiWays", pad: 10, narrow: true,
        t: "Up to three ways to improve", p: "Each way is one tap; the quality updates at once." }
    ] },
    { ch: 4, name: "Ask Helvy", beats: [
      { view: "selection", fresh: true, target: "#hv-panel", clip: "thinking", run: "chat:Why did Dr. Ghada score 88?:fresh",
        t: "Ask why a creator scored what it did", p: "Helvy explains a score in plain words, from the creator's own numbers.", hint: "While he works you see what he is doing: dots and one plain line." },
      { target: "#hv-panel", clip: "point", run: "chat:Compare Lulwa and Nada",
        t: "Compare two creators", p: "Ask for two side by side; he reads both analyses for you." },
      { target: "#hv-panel", clip: "approve", run: "chat:Can you get me a better rate?:hand",
        t: "A person behind him", p: "When Helvy can't answer, one tap hands the chat to your account manager." }
    ] },
    { ch: 5, name: "Quote", beats: [
      { view: "selection", fresh: true, lc: "draft", target: "#cat-request", clip: "point", run: "quoteOpen", pad: 10,
        t: "Request a quote", p: "When you are happy with the picks, send the selection to your account manager." },
      { target: ".cat-modal__panel", clip: "point", run: "quoteSend", pad: 8,
        t: "One form, then it is sent", p: "Confirm your details; the quote is requested and the chip follows it." },
      { lc: "ready", target: "#cx-lc", clip: "point", run: "lcReady", pad: 10,
        t: "The quote has a timeline", p: "Draft, Quote requested, Quote ready, Approved, Campaign live, Completed." },
      { lc: "ready", target: "#cx-lc", clip: "approve", run: "lcApprove", pad: 10,
        t: "Approve it", p: "Only the selection's owner approves; HelloVoice then sets up the campaign." }
    ] },
    { ch: 6, name: "Follow", beats: [
      { view: "campaign", fresh: true, lc: "live", target: "#mx-verdict", also: "#mx-scoreline", clip: "celebrate",
        t: "The verdict comes first", p: "Behind, on track or ahead, against your targets, refreshed every 24 hours." },
      { target: ".cx-eva", also: "#mx-carousel-wrap", clip: "point", run: "tab:overview", top: 104,
        t: "Estimate vs actual", p: "The estimate you saved before the campaign, against what really happened." },
      { view: "account", fresh: true, target: ".hc-cols", also: ".hc-invite", clip: "point", run: "scrollTo",
        t: "Your profile", p: "Selections, campaigns, credits and invites live here; invite a colleague and earn credits." },
      { finish: true, clip: "celebrate", t: "You're all set", p: "That's the whole story: brief, shortlist, check, plan, ask, approve, follow." }
    ] }
  ];

  var T = null;   // the running tour
  function flat() { var out = []; STOPS.forEach(function (s, si) { s.beats.forEach(function (b, bi) { out.push({ s: si, b: bi }); }); }); return out; }
  var ORDER = flat();
  var TOTAL = ORDER.length - 1;           // the finish card is not a step
  function firstOfChapter(c) { for (var i = 0; i < ORDER.length; i++) if (STOPS[ORDER[i].s].ch === c) return i; return 0; }

  function start(chapter) {
    if (T) return;
    var m = HV.me || {};
    Demo.user = m.user && m.user.name ? m.user.name : "Sara Haddad";
    Demo.active = true;
    STATE = freshState(Demo.user);
    var prevFocus = document.activeElement;
    var root = h("div", { class: "tv", role: "region", "aria-label": "HELVY Connect tour, demo mode" });
    if (IS_AR) root.setAttribute("dir", "rtl");
    var exit = h("button", { class: "tv-exit", type: "button", html: ic("x") + "<span></span>" });
    exit.querySelector("span").textContent = TT("Exit demo");
    var chaps = h("ol", { class: "tv-chaps", "aria-label": "Chapters" });
    CHAPTERS.forEach(function (c, i) {
      var b = h("button", { type: "button", class: "tv-chap", "data-ch": String(i), "aria-label": (i + 1) + ". " + TT(c[0]), html: ic(c[1]) + "<span><small>" + (i + 1) + "</small></span>" });
      b.querySelector("span").appendChild(document.createTextNode(TT(c[0])));
      b.addEventListener("click", function () { go(firstOfChapter(i)); });
      chaps.appendChild(h("li", null, b));
    });
    var idp = h("p", null, h("b", null, SEL_NAME), h("span", null, TT("Sample data · nothing you do here is saved")));
    var bar = h("header", { class: "tv-bar" }, h("div", { class: "tv-bar__id" }, h("span", { class: "tv-badge" }, TT("Demo")), idp), chaps, exit);
    var stage = h("div", { class: "tv-stage" });
    var frame = h("iframe", { class: "tv-frame", title: "HELVY Connect demo", "data-hv-demo": "1", tabindex: "0" });
    var shutter = h("div", { class: "tv-shutter", "aria-hidden": "true" });
    var spot = h("div", { class: "tv-spot", "aria-hidden": "true", hidden: "" });
    var pin = h("span", { class: "tv-pin" }, "1");
    spot.appendChild(pin);
    var cursor = h("div", { class: "tv-cursor", "aria-hidden": "true", hidden: "", html: '<svg viewBox="0 0 24 24" width="30" height="30"><path d="M5 3l14 8-6.2 1.6L10 19z" fill="#121212" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg><i></i>' });
    stage.appendChild(frame); stage.appendChild(spot); stage.appendChild(cursor); stage.appendChild(shutter);
    var coach = h("aside", { class: "tv-coach", role: "dialog", "aria-modal": "false", "aria-labelledby": "tv-t", "aria-describedby": "tv-p", tabindex: "-1" });
    var live = h("p", { class: "tv-sr", "aria-live": "polite" });
    root.appendChild(bar); root.appendChild(stage); root.appendChild(coach); root.appendChild(live);
    document.body.appendChild(root);
    var overflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = "hidden";
    T = { root: root, frame: frame, stage: stage, spot: spot, pin: pin, cursor: cursor, shutter: shutter, coach: coach, live: live, chaps: chaps, i: -1, view: null, ch: -1,
          prev: prevFocus, overflow: overflow, timers: [], seq: 0 };
    exit.addEventListener("click", function () { end("skip"); });
    T.onKey = function (e) {
      if (!T) return;
      if (e.key === "Escape") { e.preventDefault(); end("skip"); }
      else if (e.key === "ArrowRight" && !inField(e)) { e.preventDefault(); next(); }
      else if (e.key === "ArrowLeft" && !inField(e)) { e.preventDefault(); back(); }
    };
    document.addEventListener("keydown", T.onKey);
    T.onResize = function () { place(); };
    window.addEventListener("resize", T.onResize);
    api("POST", "/api/tour", { action: "started" });
    setTimeout(function () { root.classList.add("is-in"); }, 20);
    var seq0 = T;
    // The invented roster is one static file; the first page waits for it.
    var ready = R ? Promise.resolve() : fetch(ROOT + "assets/demo/demo-roster.json", { credentials: "same-origin", cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("roster"); return r.json(); }).then(setRoster);
    ready.then(function () { if (T === seq0) go(chapter != null ? firstOfChapter(chapter) : 0); })
      .catch(function () { if (T === seq0) { end("skip"); if (HV.toast) HV.toast("The tour didn't load. Please try again."); } });
  }
  function inField(e) { var t = e.target; return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable); }
  function end(reason) {
    if (!T) return;
    var t = T; T = null;
    t.timers.forEach(clearTimeout);
    document.removeEventListener("keydown", t.onKey);
    window.removeEventListener("resize", t.onResize);
    document.documentElement.style.overflow = t.overflow;
    t.root.classList.remove("is-in");
    setTimeout(function () { t.root.remove(); Demo.active = false; }, REDUCE ? 0 : 220);
    if (reason === "skip") api("POST", "/api/tour", { action: "later" });
    if (t.prev && t.prev.focus) try { t.prev.focus({ preventScroll: true }); } catch (e) { /* gone */ }
  }
  function next() { if (!T) return; var b = beat(T.i); if (b.finish) { end("done"); return; } go(T.i + 1); }
  function back() { if (T && T.i > 0) go(T.i - 1); }
  function beat(i) { var o = ORDER[i]; return STOPS[o.s].beats[o.b]; }
  function viewOf(i) { for (var k = i; k >= 0; k--) { var b = beat(k); if (b.view) return b.view; } return "catalogue"; }
  function later_(fn, ms) { var id = setTimeout(fn, ms); if (T) T.timers.push(id); return id; }
  function win() { return T && T.frame.contentWindow; }
  function doc() { try { return T && T.frame.contentDocument; } catch (e) { return null; } }

  // The shutter covers a page switch: a new chapter shows its card (number, name, its one line),
  // a switch inside a chapter only says the demo is setting up.
  function shutterFor(ch) {
    var s = T.shutter;
    s.textContent = "";
    if (ch != null && ch !== T.ch) {
      s.classList.add("is-chapter");
      var n = h("b", { class: "tv-chcard__n" }, String(ch + 1));
      var nm = h("b", { class: "tv-chcard__t" }, TT(CHAPTERS[ch][0]));
      var ln = h("span", { class: "tv-chcard__l" }, TT(CHAPTERS[ch][2]));
      s.appendChild(h("div", { class: "tv-chcard", role: "presentation" }, n, nm, ln));
    } else {
      s.classList.remove("is-chapter");
      s.appendChild(h("span", { class: "tv-wait" }, TT("Setting up the demo…")));
    }
  }
  // Load a page into the frame.
  function load(view, ch, then) {
    var seq = ++T.seq, url = ROOT + PAGES[view];
    shutterFor(ch);
    T.shutter.classList.add("is-on");
    T.spot.hidden = true; T.cursor.hidden = true;
    var done = false, t0 = Date.now(), card = ch != null && ch !== T.ch;
    function ready() {
      if (done || !T || seq !== T.seq) return;
      done = true;
      T.view = view;
      // a chapter card stays long enough to be read; other switches lift as soon as the page is drawn
      var hold = card && !REDUCE ? Math.max(0, 1100 - (Date.now() - t0)) : 0;
      later_(function () { if (T && seq === T.seq) { T.shutter.classList.remove("is-on"); then(); } }, 120 + hold);
    }
    T.frame.onload = function () {
      var d = doc();
      if (d) d.documentElement.classList.add("tv-demo-frame");
      waitFor(WAIT_FOR[view], 12000, ready);
    };
    if (T.frame.getAttribute("src") === url) {
      try { T.frame.contentWindow.location.reload(); } catch (e) { T.frame.setAttribute("src", url); }
    } else T.frame.setAttribute("src", url);
  }
  function waitFor(sel, ms, fn) {
    var t0 = Date.now(), seq = T.seq;
    (function poll() {
      if (!T || seq !== T.seq) return;
      var d = doc(), el = d && sel ? d.querySelector(sel) : null;
      if (el && el.getBoundingClientRect().height > 0) { fn(el); return; }
      if (Date.now() - t0 > ms) { fn(null); return; }
      later_(poll, 120);
    })();
  }

  function go(i) {
    if (!T) return;
    i = Math.max(0, Math.min(ORDER.length - 1, i));
    var prevStop = T.i >= 0 ? ORDER[T.i].s : -1, b = beat(i), o = ORDER[i];
    var view = b.finish ? T.view : viewOf(i);
    var forward = i === T.i + 1;
    T.i = i; T.eff = null;
    T.timers.forEach(clearTimeout); T.timers = [];
    var ch = STOPS[o.s].ch;
    paintChapters(ch);
    if (b.lc) Demo.setLc(b.lc);
    // A new chapter reloads its page fresh, so it starts from the same demo screen.
    var reload = !T.view || view !== T.view || (o.s !== prevStop && STOPS[o.s].beats[0].fresh && o.b === 0) || (!forward && o.s !== prevStop);
    drawCoach(b, i);
    if (b.finish) {
      T.spot.hidden = true; T.cursor.hidden = true; T.root.classList.add("is-finish");
      var fd = doc();
      if (fd) { var bd = fd.getElementById("hv-bell-drop"); if (bd && !bd.hidden) { var bl = fd.getElementById("hv-bell"); if (bl) bl.click(); } }
      T.ch = ch;
      return;
    }
    T.root.classList.remove("is-finish");
    if (reload) {
      if (view === "selection" || view === "creator") { STATE.asked = {}; if (view === "selection") resetSelection(); }
      T.coach.classList.add("is-wait");
      load(view, ch, function () { T.ch = ch; T.coach.classList.remove("is-wait"); act(b); });
    } else { T.ch = ch; act(b); }
  }
  function paintChapters(c) {
    [].forEach.call(T.chaps.querySelectorAll(".tv-chap"), function (x, k) {
      x.classList.toggle("is-now", k === c); x.classList.toggle("is-done", k < c);
      if (k === c) x.setAttribute("aria-current", "step"); else x.removeAttribute("aria-current");
    });
  }

  /* -- the coach: Helvy (cut-out, looping) over a card of one title and one sentence -- */
  function drawCoach(b, i) {
    var o = ORDER[i], stop = STOPS[o.s], c = T.coach;
    c.textContent = "";
    c.className = "tv-coach" + (b.finish ? " tv-coach--finish" : "") + (b.narrow ? " tv-coach--narrow" : "") + (T.coach.classList.contains("is-wait") ? " is-wait" : "");
    var helvy = h("div", { class: "tv-coach__helvy" }, clipNode(b.clip || "point", "tv-hv", b.clip === "celebrate" || b.clip === "hello" ? { once: true, then: "idle" } : null));
    var n = b.finish ? TOTAL : i + 1;
    var meter = h("div", { class: "tv-meter", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": String(TOTAL), "aria-valuenow": String(n), "aria-label": "Tour progress" });
    var fill = h("i"); fill.style.width = Math.round(n / TOTAL * 100) + "%";
    meter.appendChild(fill);
    STOPS.forEach(function (s, k) {
      if (k === 0) return;
      var first = ORDER.map(function (q, qi) { return q.s === k && q.b === 0 ? qi : -1; }).filter(function (q) { return q >= 0; })[0];
      var tick = h("u"); tick.style.left = Math.round(first / TOTAL * 100) + "%"; meter.appendChild(tick);
    });
    var stepTxt = b.finish ? TT("Chapter") + " " + CHAPTERS.length + " " + TT("of") + " " + CHAPTERS.length
      : TT("Step") + " " + n + " " + TT("of") + " " + TOTAL;
    var head = h("div", { class: "tv-coach__prog" }, h("span", { class: "tv-coach__ch" }, h("b", null, String(stop.ch + 1)), " " + TT(CHAPTERS[stop.ch][0])), h("span", { class: "tv-coach__n" }, stepTxt));
    var words = h("div", { class: "tv-coach__words" }, head, meter, h("h2", { id: "tv-t" }, TT(b.t)), h("p", { id: "tv-p" }, TT(b.p)));
    if (b.hint) words.appendChild(h("p", { class: "tv-coach__hint", html: ic("spark") + "<span></span>" })), words.lastChild.querySelector("span").textContent = TT(b.hint);
    if (b.finish) {
      var prize = h("div", { class: "tv-prize" }, h("span", { class: "tv-prize__stamp" }, "+5", h("small", null, "credits")),
        h("p", null, h("b", null, TT("Added for finishing the tour")), h("span", null, TT("Spend them on AI shortlists and replacements."))));
      words.appendChild(prize);
      words.appendChild(h("p", { class: "tv-coach__fine", html: ic("help") + "<span></span>" }));
      words.lastChild.querySelector("span").textContent = TT("Replay any time from") + " " + TT("Help") + " " + TT("or your") + " " + TT("Profile") + ".";
      api("POST", "/api/tour", { action: "done" }).then(function (r) {
        if (!r.b || !r.b.ok) return;
        if (r.b.credits != null && HV.setCredits) HV.setCredits(r.b.credits);
        var p = prize.querySelector("p"); p.textContent = "";
        if (r.b.earned) p.appendChild(h("b", null, TT("Added for finishing the tour"))), p.appendChild(h("span", null, "Your balance is now " + r.b.credits + " credits."));
        else { var stp = prize.querySelector(".tv-prize__stamp"); stp.textContent = "Done"; prize.classList.add("is-replay"); p.appendChild(h("b", null, TT("Tour replayed"))), p.appendChild(h("span", null, "Your 5 credits were added the first time you finished it.")); }
      });
    }
    var nav = h("div", { class: "tv-nav" });
    if (!b.finish) nav.appendChild(h("button", { class: "tv-skip", type: "button", onclick: function () { end("skip"); } }, TT("Skip tour")));
    else nav.appendChild(h("span", { class: "tv-nav__gap" }));
    if (i > 0) nav.appendChild(h("button", { class: "tv-btn tv-btn--line", type: "button", "aria-label": TT("Back"), html: ic("back") + "<span></span>", onclick: back }));
    if (i > 0) nav.lastChild.querySelector("span").textContent = TT("Back");
    var lastStep = i === ORDER.length - 2;
    var nb = h("button", { class: "tv-btn", type: "button", html: "<span></span>" + ic(b.finish ? "check" : "arrow"), onclick: next });
    nb.querySelector("span").textContent = TT(b.finish ? "Finish tour" : lastStep ? "Finish" : "Next");
    nav.appendChild(nb);
    words.appendChild(nav);
    c.appendChild(helvy); c.appendChild(words);
    T.live.textContent = (b.finish ? "" : stepTxt + ": ") + TT(b.t);
    T.pin.textContent = String(n);
    if (!REDUCE) { c.classList.remove("is-pop"); void c.offsetWidth; c.classList.add("is-pop"); }
    setTimeout(function () { if (T && T.coach === c) { var x = c.querySelector(".tv-nav .tv-btn:last-child"); if (x) x.focus({ preventScroll: true, focusVisible: false }); } }, 30);
  }
  // Helvy changes pose when something happens (the quote is approved, the answer is in).
  function helvyTo(name, opts) {
    if (!T) return;
    var box = T.coach.querySelector(".tv-coach__helvy");
    if (!box) return;
    box.textContent = "";
    box.appendChild(clipNode(name, "tv-hv", opts || { once: true, then: "idle" }));
  }

  /* -- the ghost cursor: shows what the tour is about to tap, then taps it -- */
  function cursorTo(el, then) {
    if (!T || !el) { if (then) then(null); return; }
    var c = T.cursor, r = el.getBoundingClientRect();
    var x = Math.round(r.left + Math.min(r.width / 2, 90)), y = Math.round(r.top + Math.min(r.height / 2, 30));
    c.hidden = false;
    if (REDUCE) { c.style.transform = "translate(" + x + "px," + y + "px)"; later_(function () { c.hidden = true; if (then) then(el); }, 220); return; }
    c.style.transform = "translate(" + x + "px," + y + "px)";
    later_(function () {
      c.classList.add("is-press");
      later_(function () { c.classList.remove("is-press"); if (then) then(el); later_(function () { if (T) T.cursor.hidden = true; }, 700); }, 170);
    }, 760);
  }
  function press(sel, fn, delay) {
    var d = doc(), el = typeof sel === "string" ? (d && d.querySelector(sel)) : sel;
    if (!el) { if (fn) fn(null); return; }
    try { el.scrollIntoView({ block: "center" }); } catch (e) { /* none */ }
    later_(function () { cursorTo(el, function (x) { if (fn) fn(x); }); }, delay != null ? delay : 380);
  }
  function pushLifecycle(w) {
    if (!w) return;
    var lc = Demo.lifecycle();
    lc.warn = "";                       // the demo says nothing about "updating" a quote it has just sent
    try { w.dispatchEvent(new w.CustomEvent("hv:selection-saved", { detail: { token: SEL, name: SEL_NAME, codes: STATE.codes.slice(), lifecycle: lc } })); } catch (e) { /* none */ }
  }

  /* -- what a beat does in the frame, then where the light goes -- */
  function act(b) {
    var w = win(), d = doc();
    if (!w || !d) return;
    var run = b.run || "";
    var P = w.hvPortal || {};
    // Close anything a previous beat left open.
    if (run.indexOf("chat") !== 0 && P.voiceClose) P.voiceClose();
    var mm = d.getElementById("pt-menu"); if (mm && !mm.hidden) { var av = d.getElementById("pt-avatar"); if (av) av.click(); }
    var bd = d.getElementById("hv-bell-drop");
    if (run !== "lcReady" && bd && !bd.hidden) { var bl = d.getElementById("hv-bell"); if (bl) bl.click(); }
    // Arriving at a calculator step without the drawer (Back from a later chapter): open it, set the count.
    if (/^roi(Count|Quality|Ways)$/.test(run) && !d.querySelector(".cx-dr .cx-res") && !b._opened) {
      if (P.openRoi) P.openRoi();
      var again = Object.assign({}, b, { _opened: true });
      waitFor(".cx-dr .cx-res", 6000, function () {
        var ci = d.querySelector(".cx-count__in");
        if (ci && run !== "roiCount") { ci.value = "15"; ci.dispatchEvent(new w.Event("change", { bubbles: true })); }
        later_(function () { act(again); }, 700);
      });
      return;
    }
    if (run === "aiAsk0" || run === "aiAsk2") {
      var card = d.getElementById("ai-sl");
      if (card) card.scrollIntoView({ block: "center" });
      later_(function () { if (P.aiDemo) P.aiDemo(clone(ANS), "Skincare · KSA + UAE · Awareness + Engagement", { ask: run === "aiAsk0" ? 0 : 2 }); }, 450);
      light(b);
      // The card grows into the question once it opens: bring it into view again, then follow it.
      later_(function () { light(b); }, 900); later_(function () { light(b); }, 1700);
      for (var k = 1; k < 8; k++) later_(function () { light(b, true); }, 500 + k * 380);
      return;
    }
    if (run === "aiGo") {
      var cd = d.getElementById("ai-sl");
      if (cd) cd.scrollIntoView({ block: "center" });
      if (P.aiDemo) later_(function () { P.aiDemo(clone(ANS), "Skincare · KSA + UAE · Awareness + Engagement"); }, 400);
      light(b);
      // The card plays its staged wait (Helvy scouts with his camera), then the results bar opens.
      var seen = false;
      for (var j = 2; j < 30; j++) later_(function () {
        var rb = d.getElementById("ai-result");
        if (rb && !seen) { seen = true; helvyTo("celebrate"); }
        light(rb ? Object.assign({}, b, { target: "#ai-result" }) : b, seen);
      }, j * 500);
      return;
    }
    if (run === "scoreTip") {
      waitFor(b.target, 4000, function (el) {
        if (!el) return light(b);
        el.scrollIntoView({ block: "center" });
        // The tooltip is the page's own: it hides when the frame scrolls, so it is shown after the
        // scroll has settled and the light never scrolls again; a few re-shows keep it up.
        var show = function () {
          var tip0 = d.querySelector(".cat-score-tip");
          if (!tip0 || tip0.hidden) el.dispatchEvent(new w.MouseEvent("mouseenter"));
          light(b, true, d.querySelector(".cat-score-tip:not([hidden])"));
        };
        light(b);
        for (var q0 = 0; q0 < 60; q0++) later_(show, 650 + q0 * 500);
      });
      return;
    }
    if (run === "sampleHover") {
      waitFor(b.target, 4000, function (el) {
        if (!el) return light(b);
        el.scrollIntoView({ block: "center" });
        later_(function () { var wrap = el.closest(".pp-sample") || el; wrap.dispatchEvent(new w.MouseEvent("mouseenter")); light(b); }, 400);
        later_(function () { light(b, true, d.querySelector(".pp-sample__card:not([hidden])")); }, 1200);
      });
      return;
    }
    if (run === "sampleOpen") {
      var sb = d.getElementById("pp-sample-btn");
      var card0 = d.getElementById("pp-sample-card"); if (card0) card0.hidden = true;
      press(sb, function () {
        if (sb) sb.click();
        // The analysis opens on its sample band; the light then walks down its sections, one at a time.
        waitFor("#pp-gate-band.pp-samplebar", 6000, function () {
          w.scrollTo(0, 0);
          var walk = ["#pp-gate-band", "#pp-real-sec", "#pp-aud-sec", "#pp-posts-sec"];
          walk.forEach(function (sel, k) {
            later_(function () { light(Object.assign({}, b, { target: sel, pad: 8 }), k === 0); }, 500 + k * 2600);
            if (k) later_(function () { light(Object.assign({}, b, { target: sel, pad: 8 }), true); }, 1300 + k * 2600);
          });
        });
      }, 150);
      return;
    }
    if (run === "roiOpen") {
      light(b);
      press(".cx-btn--roi", function (btn) {
        if (btn) btn.click();
        waitFor(".cx-dr .cx-res", 6000, function () { later_(function () { light(Object.assign({}, b, { target: ".cx-dr__hd", pad: 6 })); }, 250); });
      }, 500);
      return;
    }
    if (run === "roiCount") {
      var inp = d.querySelector(".cx-count__in");
      light(b);
      press(inp, function (x) {
        if (!x) return;
        x.focus(); x.value = "15";
        x.dispatchEvent(new w.Event("change", { bubbles: true }));
        for (var q = 1; q < 6; q++) later_(function () { light(b, true); }, q * 300);
      }, 500);
      return;
    }
    if (run === "roiQuality") {
      var res = d.querySelector(".cx-res__top");
      if (res) res.scrollIntoView({ block: "center" });
      later_(function () { light(b); }, 250);
      return;
    }
    if (run === "roiWays") {
      var wb = d.querySelector(".cx-waysbox");
      if (wb) wb.scrollIntoView({ block: "center" });
      later_(function () { light(b); }, 250);
      // The ways stay in view long enough to read; then the first is tapped and the light moves to
      // the quality, which is where the answer shows.
      press(".cx-ways li button", function (x) {
        if (!x) return;
        x.click();
        helvyTo("celebrate");
        var top = Object.assign({}, b, { target: ".cx-res__top", also: ".cx-gap" });
        [0, 1, 2, 3, 4, 5, 6, 7].forEach(function (qq) { later_(function () { light(top, qq > 0); }, 300 + qq * 350); });
      }, 3200);
      return;
    }
    if (run.indexOf("chat") === 0) {
      var parts = run.split(":"), text = parts[1], mode = parts[2] || "";
      if (P.voiceDemo) P.voiceDemo(text, mode === "fresh");
      waitFor("#hv-panel:not([hidden])", 4000, function () { light(b); });
      // The panel grows as the answer arrives: keep the light on it.
      for (var k2 = 1; k2 < 16; k2++) later_(function () { light(b, true); }, k2 * 700);
      if (mode === "hand") {
        var tries = 0;
        (function hand() {
          if (!T || tries++ > 40) return;
          var hb = d.querySelector(".hv-hand__btn");
          if (!hb) return later_(hand, 500);
          later_(function () {
            press(hb, function (x) {
              if (!x) return;
              x.click();
              later_(function () {
                var yes = d.querySelector(".hv-act__yes");
                press(yes, function (y) { if (y) y.click(); helvyTo("approve"); }, 200);
              }, 500);
            }, 700);
          }, 600);
        })();
      }
      return;
    }
    if (run === "quoteOpen") {
      light(b);
      press("#cat-request", function (btn) {
        if (btn) btn.click();
        var f = d.getElementById("cat-form");
        if (f) { var vals = { name: Demo.user, company: BRAND, email: "demo@northwind.example", phone: "+966 5• ••• ••••" };
          Object.keys(vals).forEach(function (k) { var i = f.elements[k]; if (i) i.value = vals[k]; }); }
        later_(function () { light(Object.assign({}, b, { target: ".cat-modal__panel" }), true); }, 350);
      }, 500);
      return;
    }
    if (run === "quoteSend") {
      var modal = d.getElementById("cat-modal");
      if (modal && modal.hidden) { var rq = d.getElementById("cat-request"); if (rq) rq.click(); var fm = d.getElementById("cat-form");
        if (fm) { fm.elements.name.value = Demo.user; fm.elements.company.value = BRAND; fm.elements.email.value = "demo@northwind.example"; fm.elements.phone.value = "+966 5• ••• ••••"; } }
      light(b);
      press(".cat-form__submit", function (btn) {
        if (btn) { var f2 = d.getElementById("cat-form"); if (f2 && f2.requestSubmit) f2.requestSubmit(); else btn.click(); }
        var n = 0;
        (function sent() {
          var dn = d.getElementById("cat-done");
          if (dn && !dn.hidden) {
            helvyTo("approve");
            // Close the panel here: the page's own close would also empty the shortlist.
            later_(function () { var m2 = d.getElementById("cat-modal"); if (m2) { m2.hidden = true; m2.classList.remove("is-done"); }
              Demo.setLc("requested"); pushLifecycle(w); later_(function () { light(Object.assign({}, b, { target: "#cx-lc" })); }, 400); }, 1300);
            return;
          }
          if (n++ < 30) later_(sent, 250);
        })();
      }, 900);
      return;
    }
    if (run === "lcReady") {
      Demo.setLc("ready");
      STATE.notes.unshift({ id: 9, kind: "quote_ready", group: "selections", title: "Your quote is ready:", rest: " " + SEL_NAME, body: "Open the selection to read it and approve.", at: NOW, unread: true, href: "selection/#s=" + SEL });
      if (P.setUnread) P.setUnread(STATE.notes.filter(function (n) { return n.unread; }).length);
      pushLifecycle(w);
      later_(function () { var c0 = d.getElementById("cx-lc"); if (c0) c0.scrollIntoView({ block: "center" }); light(b); }, 500);
      later_(function () { light(b, true); }, 1300);
      return;
    }
    if (run === "lcApprove") {
      Demo.setLc("ready"); pushLifecycle(w);
      later_(function () { var c1 = d.getElementById("cx-lc"); if (c1) c1.scrollIntoView({ block: "center" }); light(b); }, 400);
      later_(function () {
        press("#cx-lc .cx-lc__act .cx-btn", function (a1) {
          if (!a1) return;
          a1.click();
          later_(function () {
            press("#cx-lc .cx-lc__act .cx-btn:not(.cx-btn--line)", function (yes) {
              if (!yes) return;
              yes.click();
              helvyTo("approve");
              // HelloVoice sets the campaign up: the chip moves on to "Campaign live".
              later_(function () { Demo.setLc("live"); pushLifecycle(w); light(b, true); helvyTo("celebrate"); }, 2200);
            }, 200);
          }, 500);
        }, 200);
      }, 1700);
      return;
    }
    if (run.indexOf("tab:") === 0) {
      var tab = d.getElementById("tab-" + run.slice(4));
      if (tab) tab.click();
      // The tab scrolls smoothly to its section: light once it has landed, then make sure.
      later_(function () { light(b); }, 350); later_(function () { light(b); }, 1100); later_(function () { light(b, true); }, 2000);
      return;
    }
    if (run === "scrollTo") {
      waitFor(b.target, 6000, function (el) { if (el) el.scrollIntoView({ block: "center" }); later_(function () { light(b); }, 250); });
      return;
    }
    light(b);
  }

  // The spotlight: the target (and its companion) lit, the rest of the frame dimmed. The frame
  // scrolls so the target sits in the space the coach leaves free.
  function scrollerOf(el, w) {
    for (var n = el.parentElement; n && n !== el.ownerDocument.body && n !== el.ownerDocument.documentElement; n = n.parentElement) {
      var oy = w.getComputedStyle(n).overflowY;
      if ((oy === "auto" || oy === "scroll") && n.scrollHeight > n.clientHeight + 4) return n;
    }
    return null;
  }
  function rectOf(el) { var r = el.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom }; }
  function light(b, quiet, extra) {
    if (!T || !b.target) return;
    T.eff = b;                        // what the light is on now, so scrolling the frame keeps it there
    var d = doc(), w = win();
    if (!d) return;
    var el = d.querySelector(b.target);
    if ((!el || !el.getBoundingClientRect().height) && b.alt) el = d.querySelector(b.alt);
    if (!el || !el.getBoundingClientRect().height) { T.spot.hidden = true; place(); return; }
    var mob = window.innerWidth <= 760;
    // A wide lit area leaves no room beside it: the coach docks below it, so keep that room free
    // (phone: the docked card; desktop: the card plus the head-room Helvy stands in).
    var padW = b.pad != null ? b.pad : 14, wide = !mob && el.getBoundingClientRect().width + 2 * padW > window.innerWidth - T.coach.offsetWidth - 100;
    var stageR = T.stage.getBoundingClientRect(), coachH = mob ? T.coach.offsetHeight : wide ? T.coach.offsetHeight + 96 : 0;
    var free = stageR.height - coachH;
    if (!quiet) {
      var r0 = el.getBoundingClientRect();
      var top = b.top != null ? b.top : 40, bottom = free - 24;
      if (r0.top < top || r0.bottom > bottom) {
        var y = r0.height > bottom - top ? r0.top - top : r0.top - (top + (bottom - top - r0.height) / 2);
        // inside a drawer or panel that scrolls on its own, the element's own scroller moves; else the page
        var sc = scrollerOf(el, w);
        if (sc) sc.scrollTop += Math.round(y); else w.scrollBy(0, Math.round(y));
      }
    }
    var r = rectOf(el), list = [extra, b.also ? d.querySelector(b.also) : null];
    list.forEach(function (x) {
      if (!x || !x.getBoundingClientRect().height || x.hidden) return;
      var q = rectOf(x);
      // Only join a companion that sits close by; a far one would light the whole page.
      if (Math.abs(q.t - r.b) < 420 && Math.abs(r.t - q.b) < 600) { r.l = Math.min(r.l, q.l); r.t = Math.min(r.t, q.t); r.r = Math.max(r.r, q.r); r.b = Math.max(r.b, q.b); }
    });
    var pad = b.pad != null ? b.pad : 14;
    var vw = T.frame.clientWidth, vh = T.frame.clientHeight;
    var L = Math.max(18, r.l - pad), Tp = Math.max(18, r.t - pad), R_ = Math.min(vw - 8, r.r + pad), B = Math.min(vh - 6, r.b + pad);   // 18: the pin sits on the corner and must stay in the frame
    T.spot.hidden = false;
    T.spot.style.transform = "translate(" + Math.round(L) + "px," + Math.round(Tp) + "px)";
    T.spot.style.width = Math.max(24, Math.round(R_ - L)) + "px"; T.spot.style.height = Math.max(24, Math.round(B - Tp)) + "px";
    T.lit = { l: L + stageR.left, t: Tp + stageR.top, r: R_ + stageR.left, b: B + stageR.top };
    place();
    // Scrolling the frame by hand keeps the light on the target.
    if (w && !w.__tvScroll) {
      w.__tvScroll = true;
      var tick = 0;
      w.addEventListener("scroll", function () { if (tick) return; tick = requestAnimationFrame(function () { tick = 0; if (T && T.i >= 0) light(T.eff || beat(T.i), true); }); }, { passive: true });
    }
  }
  // Desktop: the coach sits beside the lit area, Helvy facing it, a notch pointing back. Phone: docked at the bottom.
  function place() {
    if (!T) return;
    var c = T.coach, vw = window.innerWidth, vh = window.innerHeight;
    c.removeAttribute("data-side");
    if (vw <= 760 || T.root.classList.contains("is-finish") || !T.lit || T.spot.hidden) { c.style.left = c.style.top = c.style.right = c.style.bottom = ""; c.classList.remove("is-flip"); return; }
    var w = c.offsetWidth, hh = c.offsetHeight, L = T.lit, gap = 30, left, top, side = "";
    var stageTop = T.stage.getBoundingClientRect().top + 96;      // room above the card for Helvy, who stands on its top edge
    var eff = T.eff || (T.i >= 0 ? beat(T.i) : {});
    if (eff.narrow && L.l - gap >= w + 16) { left = L.l - gap - w; top = Math.max(stageTop + 16, Math.min(vh - hh - 16, L.t)); side = "left"; }   // beside a drawer: in the strip it leaves
    else if (vw - L.r - gap >= w + 16) { left = L.r + gap; top = Math.max(stageTop + 16, Math.min(vh - hh - 16, L.t)); side = "right"; }
    else if (L.l - gap >= w + 16) { left = L.l - gap - w; top = Math.max(stageTop + 16, Math.min(vh - hh - 16, L.t)); side = "left"; }
    else if (vh - L.b - 112 >= hh + 12) { top = L.b + 112; left = Math.max(16, Math.min(vw - w - 16, L.r - w - 24)); side = "below"; }
    else if (L.t - gap - stageTop >= hh + 16) { top = L.t - gap - hh; left = Math.max(16, Math.min(vw - w - 16, L.r - w)); side = "above"; }
    else { left = vw - w - 24; top = vh - hh - 24; }
    c.style.right = c.style.bottom = "auto";
    c.style.left = Math.round(left) + "px"; c.style.top = Math.round(top) + "px";
    if (side) c.setAttribute("data-side", side);
    c.classList.toggle("is-flip", left + w / 2 < (L.l + L.r) / 2);
  }

  window.hvTour = { start: start, end: function () { end("skip"); }, key: function (e) { if (T) T.onKey(e); }, chapters: CHAPTERS, stops: STOPS };
})();
