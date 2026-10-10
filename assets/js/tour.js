/* HELVY Connect onboarding tour v2 (client-approved 2026-10-09).
 *
 * Loaded by connect.js only when a client starts the tour, never with the page.
 *
 * The tour plays the REAL portal pages (catalogue, selection, creator analysis,
 * campaign report, Helvy's chat) inside a frame, on a fictional brand: Northwind
 * Pharma · Ramadan Skincare, eight AI-generated demo creators (assets/demo/).
 * hv-loader.js, the first script on every page, hands the frame to
 * hvTourDemo.install() before any page script runs. From then on the frame:
 *   - answers every /api/ call from the demo world below (nothing reaches the
 *     server, so nothing is saved and no AI or credit is used);
 *   - keeps its storage and cookies in memory (the client's real roster cache,
 *     chat history and preferences are never touched);
 *   - opens no outside link.
 * The only server call the tour itself makes is the existing POST /api/tour
 * (offered / started / later / done; +5 credits once, server-enforced).
 *
 * The journey: 7 stops in 4 chapters, following the real customer path.
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

  /* =========================================================== the demo world */
  var BRAND = "Northwind Pharma", CAMPAIGN = "Ramadan Skincare", SEL_NAME = BRAND + " · " + CAMPAIGN;
  var SEL = "demo-ramadan", CAMP = "demo-ramadan-live";
  // [code, name, handle, tier, city, interest, photo, [[platform, followers]...], er %, licence countries, price]
  var PEOPLE = [
    ["DEMO-01", "Lulwa R.", "lulwa.glow", "Macro", "Riyadh", "Beauty & skincare", 1, [["Instagram", 612000], ["TikTok", 241000]], 4.1, ["SA"], [6500, 9000]],
    ["DEMO-02", "Dr. Adel K.", "dr.adel.health", "HCP - Mid-Tier", "Jeddah", "Health", 2, [["Instagram", 188000], ["Snapchat", 64000]], 5.2, ["SA"], [5000, 7000]],
    ["DEMO-03", "Maha S.", "maha.sips", "Mid-Tier", "Riyadh", "Food & cafés", 3, [["TikTok", 204000], ["Snapchat", 120000]], 3.7, ["SA"], [3000, 4500]],
    ["DEMO-04", "Tariq B.", "tariq.moves", "Micro", "Dammam", "Fitness", 4, [["Instagram", 47000], ["TikTok", 31000]], 7.2, [], [1200, 1800]],
    ["DEMO-05", "Nada H.", "nada.and.noor", "Mid-Tier", "Riyadh", "Parenting", 5, [["Instagram", 151000], ["Snapchat", 88000]], 4.4, ["SA", "AE"], [3500, 5000]],
    ["DEMO-06", "Dr. Ghada M.", "dr.ghada.derm", "HCP - Mid-Tier", "Riyadh", "Dermatology", 6, [["Instagram", 273000], ["TikTok", 96000]], 5.6, ["SA"], [6000, 8000]],
    ["DEMO-07", "Yousef O.", "yousef.drives", "Macro", "Riyadh", "Cars", 7, [["Snapchat", 530000], ["YouTube", 210000]], 2.9, ["SA"], [7000, 10000]],
    ["DEMO-08", "Rana A.", "rana.palette", "Micro", "Jeddah", "Makeup", 8, [["Instagram", 39000], ["TikTok", 52000]], 8.1, [], [1000, 1600]]
  ];
  var BY = {};
  PEOPLE.forEach(function (p) { BY[p[0]] = p; });
  function tierBand(t) { return /macro/i.test(t) ? "macro" : /micro/i.test(t) ? "micro" : "mid"; }

  function rosterRow(p) {
    var prof = p[7].map(function (x) { return { platform: x[0], url: "#demo-profile", followers: x[1] }; });
    return { code: p[0], name: p[1], handle: p[2], platform: p[7].map(function (x) { return x[0]; }).join(", "), followers: p[7][0][1],
      city: p[4], nationality: "Saudi", tier: p[3], interest: p[5], photo: "demo-" + p[6] + ".webp", lowres: false, analysis: true,
      accounts: p[7].map(function (x) { return { platform: x[0], url: "#demo-profile", followers: x[1], tier: p[3], price: p[10] }; }),
      photo_url: photo(p[6]), price: p[10], profiles: prof };
  }
  var TIERS = [{ name: "Micro", from: 1000, to: 1800, reach: "10K – 50K" }, { name: "Mid-Tier", from: 3000, to: 5000, reach: "50K – 500K" },
               { name: "Macro", from: 6500, to: 10000, reach: "500K – 1M" }, { name: "HCP - Mid-Tier", from: 5000, to: 8000, reach: "50K – 500K" }];

  // Fit scores for the selection: what the real score tooltip shows (fit.py's shape).
  function score(code, n, parts, strengths, watchouts, checks) {
    return { score: n, tag: n >= 80 ? "Strong fit" : n >= 60 ? "Good fit" : n >= 40 ? "Possible fit" : "Not recommended", objective: "Engagement",
      platform: BY[code][7][0][0], basic: false,
      parts: parts.map(function (x) { return { key: x[0], label: x[1], s: x[2], w: x[3] }; }),
      strengths: strengths, watchouts: watchouts, checks: checks,
      conclusion: (n >= 80 ? "Strong fit" : "Good fit") + " for engagement (" + n + "/100)." };
  }
  var SCORES = {
    "DEMO-01": score("DEMO-01", 91, [["engagement", "Engagement", 0.88, 0.4], ["reach", "Reach", 0.95, 0.25], ["market", "Audience (measured)", 0.92, 0.35]],
      ["4.1% engagement, above the 1.5% typical for her size", "71% of the measured audience are women", "Works in the skincare space"],
      [], [{ label: "Measured audience", text: "78% of the measured audience is in Saudi Arabia", level: "ok" },
           { label: "Gender", text: "71% of the audience are women", level: "ok" }, { label: "Age", text: "46% of the audience is aged 25-34", level: "ok" }]),
    "DEMO-02": score("DEMO-02", 84, [["engagement", "Engagement", 0.9, 0.4], ["reach", "Reach", 0.7, 0.25], ["market", "Audience (measured)", 0.86, 0.35]],
      ["5.2% engagement, well above typical", "A doctor: trusted voice for health claims"], ["Audience is 52% men"],
      [{ label: "Measured audience", text: "81% of the measured audience is in Saudi Arabia", level: "ok" }, { label: "Gender", text: "48% of the audience are women", level: "warn" }]),
    "DEMO-03": score("DEMO-03", 72, [["engagement", "Engagement", 0.78, 0.4], ["views", "Typical views", 0.74, 0.25], ["market", "Audience (measured)", 0.64, 0.35]],
      ["A typical video gets about 96K views"], ["Little sign of skincare content in her profile"],
      [{ label: "Measured audience", text: "74% of the measured audience is in Saudi Arabia", level: "ok" }]),
    "DEMO-05": score("DEMO-05", 79, [["engagement", "Engagement", 0.82, 0.4], ["reach", "Reach", 0.72, 0.25], ["market", "Audience (measured)", 0.8, 0.35]],
      ["4.4% engagement, above typical", "68% of the audience are women"], [],
      [{ label: "Measured audience", text: "70% of the measured audience is in Saudi Arabia", level: "ok" }, { label: "Gender", text: "68% of the audience are women", level: "ok" }]),
    "DEMO-06": score("DEMO-06", 88, [["engagement", "Engagement", 0.9, 0.4], ["reach", "Reach", 0.78, 0.25], ["market", "Audience (measured)", 0.93, 0.35]],
      ["A dermatologist: the strongest voice for skincare claims", "5.6% engagement, above typical"], [],
      [{ label: "Measured audience", text: "83% of the measured audience is in Saudi Arabia", level: "ok" }, { label: "Gender", text: "74% of the audience are women", level: "ok" },
       { label: "Our campaigns", text: "1.3× the typical engagement per view in 2 of our campaigns", level: "ok" }]),
    "DEMO-07": score("DEMO-07", 41, [["engagement", "Engagement", 0.55, 0.4], ["reach", "Reach", 0.96, 0.25], ["market", "Audience (measured)", 0.18, 0.35]],
      ["Reach of 740K followers"], ["Only 22% of the audience are women", "Little sign of skincare content or audience interest"],
      [{ label: "Gender", text: "22% of the audience are women", level: "bad" }])
  };
  var SEL_CODES = ["DEMO-01", "DEMO-06", "DEMO-02", "DEMO-05", "DEMO-03", "DEMO-07"];

  function analysis(p, o) {
    var f = p[7][0][1], top = [3, 1, 8, 5, 6, 2];
    return {
      platform: p[7][0][0], handle: p[2], updated: iso(NOW - 3 * DAY), account_type: "Creator", location: p[4] + ", Saudi Arabia",
      followers: f, followers_change_pct: 2.4, avg_likes: Math.round(f * p[8] / 100 * 0.9), avg_likes_change_pct: 6.1, er: p[8],
      bio: o.bio, fake_followers_pct: 6.8, fake_likers_pct: 5.1, real_people_pct: 81.4, notable_followers_pct: 2.2, mass_followers_pct: 9.6,
      suspicious_mass_pct: 4.1, suspicious_pct: 6.8, er_note: "above average for creators this size",
      est_impressions: Math.round(f * 0.42), est_reach: Math.round(f * 0.31), avg_comments: Math.round(f * 0.0021),
      reels_er: p[8] + 0.6, avg_reel_plays: Math.round(f * 0.24), avg_reel_likes: Math.round(f * 0.034), avg_reel_comments: Math.round(f * 0.0019),
      avg_reel_shares: Math.round(f * 0.0011), story_reach: Math.round(f * 0.07), story_impressions: Math.round(f * 0.08),
      paid_post_performance: 92.4, paid_views_pct: 96.1, posts_per_week: 4.5, posts_count: 1180, following: 640, last_post: iso(NOW - DAY),
      audience: {
        gender: { female: 71, male: 29 },
        ages: [{ name: "13-17", pct: 3.1 }, { name: "18-24", pct: 27.4 }, { name: "25-34", pct: 46.2 }, { name: "35-44", pct: 17.6 }, { name: "45-64", pct: 5.7 }],
        ages_male: [{ name: "13-17", pct: 1.0 }, { name: "18-24", pct: 8.1 }, { name: "25-34", pct: 12.9 }, { name: "35-44", pct: 5.3 }, { name: "45-64", pct: 1.7 }],
        ages_female: [{ name: "13-17", pct: 2.1 }, { name: "18-24", pct: 19.3 }, { name: "25-34", pct: 33.3 }, { name: "35-44", pct: 12.3 }, { name: "45-64", pct: 4.0 }],
        countries: [{ code: "SA", pct: 78.2 }, { code: "AE", pct: 6.4 }, { code: "KW", pct: 3.9 }, { code: "EG", pct: 3.1 }, { code: "BH", pct: 1.8 }, { code: "QA", pct: 1.5 }],
        cities: [{ name: "Riyadh", pct: 34.6 }, { name: "Jeddah", pct: 17.9 }, { name: "Dammam", pct: 8.2 }, { name: "Mecca", pct: 4.4 }, { name: "Dubai", pct: 3.1 }, { name: "Medina", pct: 2.7 }],
        languages: [{ name: "Arabic", pct: 74.5 }, { name: "English", pct: 22.8 }, { name: "Other", pct: 2.7 }],
        interests: [{ name: "Beauty & cosmetics", pct: 46.2 }, { name: "Clothes, shoes, handbags & accessories", pct: 38.1 }, { name: "Restaurants, food & grocery", pct: 24.7 },
                    { name: "Travel, tourism & aviation", pct: 19.4 }, { name: "Fitness & yoga", pct: 14.2 }],
        brand_affinity: [{ name: "Velora Skin", pct: 12.4 }, { name: "Sahar Beauty", pct: 9.8 }, { name: "Dune Café", pct: 7.1 }, { name: "Oasis Pharmacy", pct: 6.3 }],
        reachability: [{ name: "<500", pct: 41.3 }, { name: "500-1000", pct: 27.2 }, { name: "1000-1500", pct: 12.9 }, { name: ">1500", pct: 18.6 }]
      },
      growth: [5, 4, 3, 2, 1, 0].map(function (k, i) {
        var d = new Date(NOW * 1000); d.setUTCMonth(d.getUTCMonth() - k - 1);
        return { month: d.toISOString().slice(0, 7), followers: Math.round(f * (0.86 + i * 0.028)), avg_likes: Math.round(f * p[8] / 100 * (0.8 + i * 0.04)) };
      }),
      fake_followers_dist: { buckets: [{ label: ">30%", h: 18 }, { label: "25%", h: 26 }, { label: "20%", h: 38 }, { label: "15%", h: 55 }, { label: "12%", h: 74 }, { label: "9%", h: 100 }, { label: "7%", h: 81 }, { label: "<5%", h: 42 }], creator: 6, median: 4 },
      er_dist: { buckets: [{ label: "<0.5%", h: 34 }, { label: "1%", h: 62 }, { label: "1.5%", h: 100 }, { label: "2%", h: 77 }, { label: "3%", h: 48 }, { label: "4%", h: 30 }, { label: "5%", h: 18 }, { label: ">6%", h: 9 }], creator: 5, median: 2 },
      creator_interests: o.interests,
      hashtags: o.tags.map(function (t, i) { return { tag: t, count: [31.2, 22.6, 14.8, 9.7, 6.5][i] || 4 }; }),
      top_posts: top.map(function (n, i) { return { url: "#demo-post", thumb: photo(n), likes: Math.round(f * (0.06 - i * 0.006)), comments: Math.round(f * 0.002 * (6 - i)), views: Math.round(f * (0.9 - i * 0.1)), date: iso(NOW - (6 + i * 9) * DAY), brand: null }; }),
      sponsored_posts: o.brands.map(function (b, i) { return { url: "#demo-post", thumb: photo([1, 8, 6][i] || 1), likes: Math.round(f * (0.04 - i * 0.005)), comments: Math.round(f * 0.0016), views: Math.round(f * (0.62 - i * 0.08)), date: iso(NOW - (20 + i * 30) * DAY), brand: b }; }),
      photo_url: photo(p[6])
    };
  }
  function creatorBody(code) {
    var p = BY[code];
    if (!p) return { ok: false, reason: "unknown" };
    var hl = { followers: p[7].reduce(function (s, x) { return s + x[1]; }, 0), platforms: p[7].map(function (x) { return x[0]; }),
               avg_views: Math.round(p[7][0][1] * 0.24), er: p[8], er_platform: p[7][0][0], er_followers: p[7][0][1], updated: iso(NOW - 3 * DAY) };
    var card = { code: code, name: p[1], tier: p[3], city: p[4], nationality: "Saudi", interest: p[5], followers: p[7][0][1], photo_url: photo(p[6]),
                 profiles: p[7].map(function (x) { return { platform: x[0], url: "#demo-profile", followers: x[1] }; }), band: tierBand(p[3]) };
    var bench = { er: { nano: [4.0, 2.0], micro: [3.0, 1.5], mid: [2.0, 1.0], macro: [1.5, 0.8], mega: [1.0, 0.5] }, video_er: [4.5, 3.0], view_rate: [30.0, 10.0],
                  story_rate: [8.0, 4.0], ctr: [1.0, 0.3], fake_followers: [15.0, 30.0], fake_likers: [15.0, 30.0] };
    var out = { ok: true, creator: card, platforms: p[7].map(function (x) { return x[0]; }), analyses: {}, requested: [], benchmarks: bench };
    if (code === "DEMO-01") {
      var a = {};
      a[p[7][0][0]] = analysis(p, { bio: "Skincare that works in Riyadh heat ☀️\nRoutines · honest reviews · Arabic & English\nFor collaborations: via HelloVoice",
        interests: ["Beauty & Cosmetics", "Healthy Lifestyle", "Fashion"], tags: ["#skincare", "#روتين_العناية", "#ramadanglow", "#spf", "#riyadh"],
        brands: ["Velora Skin", "Oasis Pharmacy", "Sahar Beauty"] });
      out.analyses = a;
      out.gate = { state: "unlocked", granted_at: NOW - 2 * DAY, headline: hl };
    } else {
      out.gate = { state: "locked", selections: [{ token: SEL, name: SEL_NAME }], headline: hl,
        sample: { sample: true, gender: { female: 64, male: 36 }, ages: [["18–24", 31], ["25–34", 42], ["35–44", 18], ["45+", 9]],
          countries: [["Saudi Arabia", 61], ["UAE", 12], ["Egypt", 7]], growth: [40, 42, 45, 47, 52, 55, 58, 60, 63, 67, 70, 74], growth_pct: 85, real_pct: 88,
          brands: ["Brand A", "Brand B", "Brand C", "Brand D", "Brand E"], partnerships: 9, pricing: { low: 3000, high: 12000, pos: 0.5 }, posts: ["420K", "388K", "301K", "276K"] } };
    }
    return out;
  }

  // The live campaign: six creators (the rejected car reviewer swapped for the makeup artist).
  var CREW = [["DEMO-01", 3, 0.9], ["DEMO-06", 3, 1.15], ["DEMO-02", 2, 0.85], ["DEMO-05", 2, 1.0], ["DEMO-08", 2, 1.4], ["DEMO-03", 2, 0.75]];
  function campaignBody() {
    var start = NOW - 12 * DAY, end = NOW + 18 * DAY, posts = [], creators = [], id = 1;
    var kinds = ["reel", "story", "post"];
    CREW.forEach(function (c, ci) {
      var p = BY[c[0]], f = p[7][0][1], plat = p[7][0][0];
      var row = { code: c[0], name: p[1], followers: f, posts: 0, likes: 0, comments: 0, engagement: 0, views: 0, reach: 0, impressions: 0, shares: 0, saves: 0, clicks: 0,
                  planned: c[1], delivered: c[1], pending_status: null, pending_date: null,
                  profiles: p[7].map(function (x) { return { platform: x[0], url: "#demo-profile", followers: x[1] }; }), band: tierBand(p[3]),
                  photo: photo(p[6]), photo_large: photo(p[6]), has_analysis: c[0] === "DEMO-01", hidden_likes: 0 };
      for (var k = 0; k < c[1]; k++) {
        var kind = kinds[(ci + k) % 3], video = kind !== "post", story = kind === "story";
        var views = Math.round(f * (0.32 + 0.11 * k) * c[2]), likes = Math.round(views * (story ? 0 : 0.052) * c[2]), comments = Math.round(likes * 0.06);
        var shares = Math.round(likes * 0.09), saves = Math.round(likes * 0.12), eng = likes + comments + shares + saves, reach = Math.round(views * 0.88);
        var ver = video ? eng / Math.max(views, 1) * 100 : eng / Math.max(reach, 1) * 100;
        var grade = ver >= 4.5 ? "good" : ver >= 3 ? "moderate" : "low";
        var clicks = Math.round(views * 0.006 * c[2]);
        posts.push({ id: id++, code: c[0], platform: plat, kind: kind, url: "#demo-post", posted_at: start + (2 + ci + k * 3) * DAY,
          caption: ["Ramadan routine with Northwind", "Suhoor skincare in 60 seconds", "Glow through the fasting month"][k % 3], thumb: photo([p[6], 1, 8, 6, 5][(k + ci) % 5]),
          section: "campaign", likes: likes, comments: comments, engagement: eng, views: views, reach: reach, impressions: Math.round(views * 1.2),
          shares: shares, saves: saves, er: Math.round(eng / f * 1000) / 10, video_er: video ? ver : null, imp_er: null,
          view_rate: Math.round(views / f * 1000) / 10, story_rate: story ? 7.2 : null, real: k === 0, reach_real: k === 0, impressions_real: false,
          video: video, story: story, health: { metric: video ? "Video ER" : "ER", value: ver, grade: grade, benchmark: video ? [4.5, 3.0] : [2.0, 1.0],
          view_rate: Math.round(views / f * 1000) / 10, view_grade: "good" }, likes_hidden: false, gaps: [], exposure: views, creator: p[1], photo: photo(p[6]), clicks: clicks });
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
      r.parts = { exposure: Math.round(r.views / exposure * 100 * 10) / 10, engagement: Math.round(r.engagement / tot.engagement * 100 * 10) / 10, er: r.er, clicks: Math.round(r.clicks / tot.clicks * 1000) / 10 };
      r.score = Math.round(r.parts.exposure * 0.4 + r.parts.engagement * 0.4 + r.parts.clicks * 0.2);
    });
    creators.sort(function (a, b) { return b.score - a.score; });
    creators.forEach(function (r, i) { r.rank = i + 1; r.badge = ["gold", "silver", "bronze"][i] || null; });
    var total = Object.assign({ seen: exposure, hidden_likes: 0, posts: posts.length, er: 4.6, video_er: tot.engagement / exposure * 100, imp_er: null, exposure: exposure,
      ctr: Math.round(tot.clicks / exposure * 10000) / 100, real_share: 0.4, adjusted: [], planned: 14, delivered: posts.length,
      er_grade: "good", ctr_grade: "good", video_er_grade: "good" }, tot);
    var hist = [], acc = { likes: 0, comments: 0, views: 0 };
    for (var d = 11; d >= 0; d--) {
      var share = (12 - d) / 12;
      hist.push({ d: iso(NOW - d * DAY), likes: Math.round(tot.likes * share), comments: Math.round(tot.comments * share), views: Math.round(tot.views * share) });
    }
    var stepsDef = [["brief", "Briefing & strategy", -30, -26], ["sourcing", "Sourcing & casting", -26, -21], ["approval", "Client approval", -21, -19], ["prep", "Content preparation", -19, -15],
      ["shooting", "Shooting", -15, -11], ["logistics", "Logistics & product delivery", -16, -13], ["review", "Content review", -11, -2], ["publishing", "Publishing", -10, 18], ["reporting", "Reporting", 0, 21]];
    var steps = stepsDef.map(function (s) {
      return { key: s[0], label: s[1], on: true, start: iso(NOW + s[2] * DAY), end: iso(NOW + s[3] * DAY), state: s[3] < 0 ? "done" : s[2] <= 0 ? "active" : "pending" };
    });
    var byDay = [];
    for (var b = 11; b >= 0; b--) byDay.push({ d: iso(NOW - b * DAY), n: Math.round(tot.clicks / 12 * (0.6 + ((11 - b) % 5) * 0.2)) });
    return { ok: true, report: {
      campaign: { id: 1, name: CAMPAIGN, client: BRAND, status: "live", starts_at: start, ends_at: end, platform: null, phase: "Publishing", status_note: null, logos: [], steps: steps },
      total: total, creators: creators, posts: posts, history: hist,
      visibility: { clicks: true, all_content: false, reach: true }, updated_at: NOW - 5 * 3600,
      verdict: { key: "good", label: "On track", grade: "good" },
      objective: { key: "engagement", label: "Engagement", kpis: ["engagement", "er", "clicks"], weights: { exposure: 0.4, engagement: 0.4, er: 0, clicks: 0.2 }, links: true },
      plan: null, gaps: { posts: posts.length, likes_hidden: 0, hidden: [], no_shares: 0, no_saves: 0, reach_estimated: 0 },
      progress: { elapsed: 0.4, overall: 112, due: 40, all_met: false, items: [
        { key: "posts", goal: 14, actual: posts.length, pct: posts.length / 14 * 100, expected: 5.6, grade: "good" },
        { key: "views", goal: 2400000, actual: tot.views, pct: tot.views / 24000, expected: 960000, grade: "good" },
        { key: "engagement", goal: 110000, actual: tot.engagement, pct: tot.engagement / 1100, expected: 44000, grade: "good" },
        { key: "er", goal: 3.5, actual: 4.6, pct: 131, expected: 3.5, grade: "good" },
        { key: "clicks", goal: 18000, actual: tot.clicks, pct: tot.clicks / 180, expected: 7200, grade: "moderate" }] },
      benchmarks: { er: { nano: [4.0, 2.0], micro: [3.0, 1.5], mid: [2.0, 1.0], macro: [1.5, 0.8], mega: [1.0, 0.5] }, video_er: [4.5, 3.0], view_rate: [30.0, 10.0],
        story_rate: [8.0, 4.0], ctr: [1.0, 0.3], bands: { nano: "Nano (<10K)", micro: "Micro (10–50K)", mid: "Mid (50–500K)", macro: "Macro (500K–1M)", mega: "Mega (1M+)" } },
      audience: { countries: [{ code: "SA", pct: 76.4 }, { code: "AE", pct: 7.9 }, { code: "KW", pct: 4.6 }, { code: "EG", pct: 3.2 }, { code: "BH", pct: 2.1 }], coverage: 72, basis: "measured", profiles: 4 },
      reach_basis: { per_view: 0.88 },
      clicks: { clicks: tot.clicks, uniques: Math.round(tot.clicks * 0.81), by_day: byDay,
        by_app: [{ k: "Instagram", n: Math.round(tot.clicks * 0.46) }, { k: "TikTok", n: Math.round(tot.clicks * 0.31) }, { k: "Snapchat", n: Math.round(tot.clicks * 0.23) }],
        by_device: [{ k: "iPhone", n: Math.round(tot.clicks * 0.58) }, { k: "Android", n: Math.round(tot.clicks * 0.37) }, { k: "Desktop", n: Math.round(tot.clicks * 0.05) }],
        by_country: [{ k: "SA", n: Math.round(tot.clicks * 0.79) }, { k: "AE", n: Math.round(tot.clicks * 0.09) }, { k: "KW", n: Math.round(tot.clicks * 0.05) }],
        by_creator: creators.map(function (r) { return { k: r.name, n: r.clicks }; }).sort(function (a, b) { return b.n - a.n; }),
        links: 6, has_destination: true }
    } };
  }

  /* -- the demo state for one run of the tour: decisions made in it live here only -- */
  var STATE = null;
  function freshState(user) {
    var st = {};
    st[SEL_CODES[0]] = { s: "approved", by: user, hv: false, at: NOW - 3 * 3600, reason: "", note: "", replacements: [] };
    st[SEL_CODES[1]] = { s: "approved", by: user, hv: false, at: NOW - 2 * 3600, reason: "", note: "", replacements: [] };
    st["DEMO-07"] = { s: "rejected", by: user, hv: false, at: NOW - 3600, reason: "audience", note: "", replacements: [] };
    return { status: st, notes: [
      { id: 2, kind: "quote", title: "Your quote for " + CAMPAIGN + " is ready", body: "Your account manager sent the quote for 4 approved creators. Open it in your profile.", at: NOW - 600, read: false, link: "account/#selections" },
      { id: 1, kind: "analysis", title: "Full analysis ready: Lulwa R.", body: "The full analysis you requested is open for your team.", at: NOW - 2 * DAY, read: false, link: "creator/#c=DEMO-01" }
    ] };
  }
  function me(user) {
    return { ok: true, signed_in: true, kind: "user", credits: 30, costs: { brief: 5, parse: 1, chat: 1, search: 0, replace: 2, more: 3, alike: 2 }, ai: true, ai_free: null,
      chat_key: "tour-demo", user: { email: "demo@northwind.example", name: user, company: BRAND, job_title: "Brand Manager", phone: "", photo: null, industry: "Pharma",
      markets: ["SA"], language: "en", brands: "Northwind" }, unread: STATE.notes.filter(function (n) { return !n.read; }).length, team: [], monthly_credits: 30, tour: "done" };
  }
  function selectionBody(user) {
    var counts = { creators: 6, influencers: 4, doctors: 2, review: 0, approved: 0, rejected: 0, unavailable: 0 };
    SEL_CODES.forEach(function (c) { var s = (STATE.status[c] || { s: "review" }).s; counts[s]++; });
    var prices = {}; SEL_CODES.forEach(function (c) { prices[c] = BY[c][10]; });
    return { ok: true, name: SEL_NAME, codes: SEL_CODES.slice(), prices: prices, total: null, platform: null, tags: {}, segments: {}, group_by: "",
      brief: { objective: "Engagement", target: { country: "SA", gender: "Women", age: "25-34", category: "skincare" }, client: BRAND },
      scores: clone(SCORES), client_tags: {}, client_platforms: {}, verdicts: {}, currency: "SAR", fx: { SAR: 1.0, AED: 0.9793, USD: 0.2667 }, token: SEL,
      needs_objective: false, status: clone(STATE.status), status_counts: counts, role: "owner", owner: user, kam: null,
      replace_cost: 2, more_cost: 3, alike_cost: 2, ai_free: null, credits: 30 };
  }
  var QUESTIONS = [
    { id: "goal", type: "one", label: "What is the main goal of the campaign?", required: true, options: [{ value: "awareness", label: "Awareness" }, { value: "engagement", label: "Engagement" }, { value: "conversion", label: "Sales" }, { value: "balanced", label: "Balanced" }] },
    { id: "platforms", type: "many", label: "Where should the content run?", required: true, options: [{ value: "Instagram", label: "Instagram" }, { value: "TikTok", label: "TikTok" }, { value: "Snapchat", label: "Snapchat" }, { value: "YouTube", label: "YouTube" }] },
    { id: "market", type: "one", label: "Which market?", required: true, options: [{ value: "SA", label: "Saudi Arabia" }, { value: "AE", label: "UAE" }] },
    { id: "category", type: "many", label: "Which space?", required: false, options: [{ value: "skincare", label: "Skincare" }, { value: "health", label: "Health" }] },
    { id: "budget", type: "one", label: "Budget?", required: false, options: [{ value: "50000", label: "SAR 50,000" }] },
    { id: "count", type: "one", label: "How many creators?", required: false, options: [{ value: "5", label: "5" }] }
  ];
  var PICKS = [["DEMO-06", 91, "Dermatologist: the strongest voice for skincare claims"], ["DEMO-01", 89, "Skincare creator, 71% women, 78% in Saudi Arabia"],
               ["DEMO-02", 84, "A doctor for the medical angle"], ["DEMO-05", 79, "Mums in Riyadh, high trust"], ["DEMO-08", 76, "Makeup artist, 8.1% engagement"]];

  /* =========================================================== the frame shim */
  function json(win, body, status) {
    return new win.Response(JSON.stringify(body), { status: status || 200, headers: { "Content-Type": "application/json" } });
  }
  function later(ms, fn) { return new Promise(function (ok) { setTimeout(function () { ok(fn()); }, REDUCE ? Math.min(ms, 400) : ms); }); }
  function chatStream(win, text) {
    var roi = /sar|riyal|budget|reach\?/i.test(text);
    var events = roi ? [
      [500, { t: "step", text: "Reading your budget" }], [900, { t: "step", text: "Checking Saudi market benchmarks" }], [900, { t: "step", text: "Working out the reach" }],
      [500, { t: "done", thread: "demo", reply: "With **SAR 50,000** on Instagram and TikTok in Saudi Arabia, a mix of 1 macro, 3 mid-tier and 6 micro creators could reach about **1.4M people**. It's an estimate from your own budget and market benchmarks.",
        roi: { goal: "awareness", budget: 50000, platforms: ["Instagram", "TikTok"], summary: "Awareness · 1 macro, 3 mid, 6 micro · Saudi Arabia",
          figures: [{ label: "People reached", value: 1400000 }, { label: "Views", value: 2100000 }, { label: "Engagement rate", value: 4.2, unit: "%" }, { label: "Cost per 1,000 views", value: 24, unit: "SAR" }],
          verdict: { grade: "good", label: "Good value" }, advice: "Arabic-first content usually earns 35–50% more engagement in KSA." },
        next: ["Find creators within my budget", "Talk to a person"] }]]
      : [
      [500, { t: "step", text: "Reading your brief" }], [1000, { t: "step", text: "Scanning the catalogue" }], [1100, { t: "step", text: "Scoring fit for Ramadan skincare" }], [900, { t: "step", text: "Picking the best five" }],
      [400, { t: "delta", text: "Here are **5 creators** for a Ramadan skincare launch in Riyadh, best fit first. " }],
      [300, { t: "delta", text: "Dr. Ghada leads: a dermatologist carries skincare claims best. Lulwa brings reach with a 71% female audience." }],
      [300, { t: "done", thread: "demo", reply: "Here are **5 creators** for a Ramadan skincare launch in Riyadh, best fit first. Dr. Ghada leads: a dermatologist carries skincare claims best. Lulwa brings reach with a 71% female audience.",
        cards: PICKS.map(function (x) { var p = BY[x[0]]; return { code: p[0], name: p[1], photo_url: photo(p[6]), fit: x[1], followers: p[7][0][1], city: p[4], tier: p[3].replace(/^HCP - /, "Doctor · ") }; }),
        next: ["Save all as a selection", "What can my budget reach?"] }]];
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
    if (lic.length) { any = true; rows = rows.filter(function (r) { return BY[r.code][9].some(function (c) { return lic.indexOf(c) !== -1; }); }); }
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
    if (!q.get("cursor")) { out.tiers = TIERS; out.fx = { SAR: 1.0, AED: 0.9793, USD: 0.2667 }; out.exp = NOW + DAY; }
    return out;
  }
  function route(win, url, init) {
    var u = new URL(url, win.location.href), p = u.pathname.replace(/^.*?\/api\//, "/api/"), q = u.searchParams, m = (init.method || "GET").toUpperCase();
    var body = {};
    try { body = init.body ? JSON.parse(init.body) : {}; } catch (e) { body = {}; }
    var user = Demo.user;
    if (p === "/api/me") return Promise.resolve(json(win, me(user)));
    if (p === "/api/roster") return Promise.resolve(json(win, { ok: true, roster: PEOPLE.map(rosterRow), tiers: TIERS, fx: { SAR: 1.0, AED: 0.9793, USD: 0.2667 }, exp: NOW + DAY }));
    // The catalogue in batches (fix batch 3): the demo roster is one batch, filtered and sorted here.
    if (p === "/api/roster/facets") return Promise.resolve(json(win, { ok: true, v: "demo", facets: demoFacets() }));
    if (p === "/api/roster/cards") {
      var want = (q.get("codes") || "").split(",").filter(function (c) { return BY[c]; });
      return Promise.resolve(json(win, { ok: true, cards: want.map(function (c) { return rosterRow(BY[c]); }), tiers: TIERS, fx: { SAR: 1.0, AED: 0.9793, USD: 0.2667 }, exp: NOW + DAY }));
    }
    if (p === "/api/roster/page") return Promise.resolve(json(win, demoPage(q)));
    if (p === "/api/licences") {
      var lic = {};
      PEOPLE.forEach(function (x) { if (x[9].length) lic[x[0]] = x[9].map(function (c) { return { country: c, name: c === "SA" ? "Mawthooq" : "UAE Advertiser Permit", number: "" }; }); });
      return Promise.resolve(json(win, { ok: true, licences: lic }));
    }
    if (p === "/api/notifications") return Promise.resolve(json(win, { ok: true, unread: STATE.notes.filter(function (n) { return !n.read; }).length, items: clone(STATE.notes) }));
    if (p === "/api/notifications/read") { STATE.notes.forEach(function (n) { n.read = true; }); return Promise.resolve(json(win, { ok: true, unread: 0 })); }
    if (p === "/api/brief/scores") { var sc = {}; PEOPLE.forEach(function (x, i) { sc[x[0]] = [[89, 84, 72, 64, 79, 91, 41, 76][i], [89, 84, 72, 64, 79, 91, 41, 76][i] >= 80 ? "Strong fit" : "Good fit", "analysis"]; }); return Promise.resolve(json(win, { ok: true, scores: sc })); }
    if (p === "/api/brief/questions") return Promise.resolve(json(win, { ok: true, questions: QUESTIONS }));
    if (p === "/api/brief/run") return later(7600, function () {
      var ps = {}; PICKS.forEach(function (x) { var pl = {}; BY[x[0]][7].forEach(function (a, k) { pl[a[0]] = x[1] - k * 4; }); ps[x[0]] = pl; });
      return json(win, { ok: true, picks: PICKS.map(function (x) { return { code: x[0], score: x[1], why: x[2] }; }), platform_scores: ps, credits: 30, brief: 1 });
    });
    if (p === "/api/selection" && m === "GET") return Promise.resolve(json(win, selectionBody(user)));
    if (p === "/api/selection/status") {
      var cur = STATE.status[body.code] || { s: "review", by: "", hv: false, at: null, reason: "", note: "", replacements: [] };
      cur = Object.assign({}, cur, { s: body.status, by: user, at: NOW, reason: body.status === "rejected" ? cur.reason : "", note: "" });
      STATE.status[body.code] = cur;
      return Promise.resolve(json(win, { ok: true, status: clone(cur) }));
    }
    if (p === "/api/selection/reason") {
      var r0 = Object.assign({}, STATE.status[body.code] || { s: "rejected" }, { reason: body.reason || "", note: body.note || "" });
      STATE.status[body.code] = r0;
      return Promise.resolve(json(win, { ok: true, status: clone(r0) }));
    }
    if (p === "/api/selection/replace") return later(4200, function () {
      return json(win, { ok: true, spent: 0, credits: 30, replacements: ["DEMO-08", "DEMO-04"].map(function (c) { return rosterRow(BY[c]); }) });
    });
    if (p === "/api/creator") return Promise.resolve(json(win, creatorBody((q.get("c") || "").toUpperCase())));
    if (p === "/api/creator/request") {
      var nowGate = { state: "requested", requested_at: NOW, ready_by: NOW + DAY, selections: [{ token: SEL, name: SEL_NAME }] };
      return later(500, function () { return json(win, { ok: true, gate: nowGate }); });
    }
    if (p === "/api/campaigns") return Promise.resolve(json(win, { ok: true, campaigns: [{ token: CAMP, name: CAMPAIGN, client: BRAND, status: "live", phase: "Publishing", starts_at: NOW - 12 * DAY, ends_at: NOW + 18 * DAY, logos: [] }] }));
    if (p === "/api/campaign") return Promise.resolve(json(win, campaignBody()));
    if (p === "/api/roi/vs") return Promise.resolve(json(win, { ok: true, items: [{ campaign: CAMPAIGN, token: CAMP, saved_at: NOW - 20 * DAY, ended: false, rows: [
      { key: "views", label: "Views", estimate: 1900000, actual: 2310000, sig: { grade: "good", label: "Ahead" }, delta: "+22%" },
      { key: "engagement", label: "Interactions", estimate: 88000, actual: 101000, sig: { grade: "good", label: "Ahead" }, delta: "+15%" },
      { key: "er", label: "Engagement rate", estimate: 4.2, actual: 4.6, sig: { grade: "good", label: "Ahead" }, delta: "+0.4 pts" },
      { key: "clicks", label: "Link clicks", estimate: 14000, actual: 11800, sig: { grade: "moderate", label: "Behind" }, delta: "−16%" }],
      helvy: "Views and engagement are ahead of the estimate. Clicks trail: a swipe-up story in week 3 would help." }] }));
    if (p === "/api/chat/stream") return Promise.resolve(chatStream(win, body.message || ""));
    if (p === "/api/chat/history") return Promise.resolve(json(win, { ok: true, messages: [] }));
    if (p === "/api/request") return later(700, function () { return json(win, { ok: true, id: "demo" }); });
    // Anything else (events, saves, the selection's own POST): accepted and forgotten.
    return Promise.resolve(json(win, m === "GET" ? { ok: true, items: [] } : { ok: true, token: SEL }));
  }
  function memStore(seed) {
    var m = {}; Object.keys(seed || {}).forEach(function (k) { m[k] = String(seed[k]); });
    return { getItem: function (k) { return Object.prototype.hasOwnProperty.call(m, k) ? m[k] : null; }, setItem: function (k, v) { m[k] = String(v); },
             removeItem: function (k) { delete m[k]; }, clear: function () { m = {}; }, key: function (i) { return Object.keys(m)[i] || null; },
             get length() { return Object.keys(m).length; } };
  }
  var Demo = window.hvTourDemo = {
    active: false, user: "Sara Haddad",
    install: function (win) {
      win.hvDemo = true;
      var mem = { local: memStore({ "hv-chat-big": "0" }), session: memStore({ "hv_brief": "demo", "hv-voice-nudged": "1", "cx-offer-shown": "1", "cat-ok": "1" }) };
      try { Object.defineProperty(win, "localStorage", { configurable: true, get: function () { return mem.local; } }); } catch (e) { /* stays real: reads only */ }
      try { Object.defineProperty(win, "sessionStorage", { configurable: true, get: function () { return mem.session; } }); } catch (e) { /* idem */ }
      var jar = "cat-ok=1";
      try { Object.defineProperty(win.document, "cookie", { configurable: true, get: function () { return jar; }, set: function () { /* kept out of the real jar */ } }); } catch (e) { /* idem */ }
      var real = win.fetch ? win.fetch.bind(win) : null;
      win.fetch = function (input, init) {
        var url = typeof input === "string" ? input : (input && input.url) || "";
        if (/\/api\//.test(url)) {
          var o = init || {};
          if (typeof input !== "string" && input && input.method && !o.method) o = Object.assign({ method: input.method }, o);
          return route(win, url, o);
        }
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
      // The catalogue's showreel is not part of the tour: it never downloads in the frame.
      win.document.addEventListener("DOMContentLoaded", function () {
        [].forEach.call(win.document.querySelectorAll(".cat-showreel video"), function (v) { v.removeAttribute("data-src"); v.removeAttribute("src"); v.preload = "none"; });
        // Demo data needs no privacy cover: the page stays visible while the tour's card has focus.
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
  var CHAPTERS = [["Brief Helvy", "chat"], ["Build your shortlist", "list"], ["Check & book", "shield"], ["Track results", "chart"]];
  // A query per view, so two views of one page (open and locked analysis) are two real page loads.
  var PAGES = { catalogue: "?tour=1", selection: "selection/?tour=1#s=" + SEL, analysis: "creator/?tour=open#c=DEMO-01", locked: "creator/?tour=locked#c=DEMO-06", campaign: "campaign/?tour=1#t=" + CAMP };

  // Each stop has beats; Next walks the beats, then the stops.
  var STOPS = [
    { ch: 0, name: "Tell Helvy your campaign", beats: [
      { view: "catalogue", fresh: true, target: "#hv-panel", clip: "thinking", run: "chatBrief", wait: "#hv-panel:not([hidden])",
        t: "Tell Helvy your campaign", p: "Write it the way you'd say it. Helvy reads the brief, scores the roster and hands back a shortlist, with the reasons.", hint: "Watch: “5 skincare creators in Riyadh for a Ramadan launch”" },
      { target: "#hv-panel", clip: "point", run: "chatBudget",
        t: "Ask what your budget can reach", p: "An estimate from your own budget and Saudi market benchmarks: reach, views, engagement. Creator prices come in your quote, never in the chat.", hint: "Watch: “What can 50,000 SAR reach?”" },
      { target: "#ai-sl", clip: "cards", run: "aiCard", pad: 12,
        t: "Or brief Helvy in six taps", p: "The AI shortlist card asks six quick questions. Helvy flips through the creators, scores every one and puts a green check on the best picks." }
    ] },
    { ch: 1, name: "Browse and filter to add more", beats: [
      { view: "catalogue", fresh: true, target: ".cat-controls .cat-bar", also: "#lic-filter", clip: "point",
        t: "Browse and filter", p: "Narrow the roster by platform, size, city, interest or audience. Doctors have their own tiers, and the licence filter keeps only Mawthooq or UAE-licensed creators." },
      { target: ".cat-card[data-code='DEMO-06']", clip: "point", run: "cardHover",
        t: "Read a card in a second", p: "Photo, platforms, follower tier and fee. The stamp shows a verified advertising licence; the % is how well they fit your last brief. Tick a card to add it." }
    ] },
    { ch: 1, name: "Review your shortlist", beats: [
      { view: "selection", fresh: true, target: "#sel-statusbar", clip: "point",
        t: "Your shortlist, at a glance", p: "Everyone starts under review. The chips count approved, rejected and waiting creators, influencers and doctors. Tap one to filter." },
      { target: ".cat-card[data-code='DEMO-01'] .cat-score", clip: "point", run: "scoreTip", pad: 8,
        t: "What the % means", p: "Helvy reads each creator's profile analysis against your campaign objective: engagement, reach, typical views and how much of the audience matches yours. Hover any badge to see it add up." },
      { target: ".cat-card[data-code='DEMO-02']", clip: "point", run: "scrollTo",
        t: "Approve or reject", p: "Only you, the selection's owner, decide. Approved creators go to your account manager for the quote; colleagues can view." },
      { target: ".cat-card[data-code='DEMO-07'] .sel-st", also: ".cat-card[data-code='DEMO-07'] .cat-card__name", clip: "approve", run: "replace",
        t: "Reject, then replace", p: "Tap “?” to say why: price, audience, content style or a competitor. Helvy learns your taste, and “Find a replacement” brings back close matches." }
    ] },
    { ch: 2, name: "Unlock the full analysis", beats: [
      { view: "analysis", fresh: true, target: "#pp-gate-band", clip: "point",
        t: "The full analysis, for your finalists", p: "This one is open. Scroll through it: it's a complete sample, the same as yours will be." },
      { target: "#pp-aud-sec", clip: "point", run: "scrollTo",
        t: "Who is really watching", p: "Age, gender, country and city of the audience, their languages and interests, and the brands they already like." },
      { target: "#pp-real-sec", clip: "point", run: "scrollTo",
        t: "Real people, real growth", p: "The fake-follower check, how reachable the followers are, growth month by month and engagement against creators the same size." },
      { target: "#pp-posts-sec", clip: "point", run: "scrollTo",
        t: "Best posts and brand history", p: "Their strongest posts and the brands they have worked with, so you can spot a competitor early." },
      { view: "locked", fresh: true, target: "#pp-gate-band", clip: "point",
        t: "Request it in one tap", p: "Headline numbers are open for everyone. For creators in your selections the full analysis is free: tap Request and it's ready within 1 working day." }
    ] },
    { ch: 2, name: "Request a quote", beats: [
      { view: "selection", fresh: true, target: "#cat-request", clip: "point", run: "scrollTo", pad: 10,
        t: "Request a quote", p: "Happy with the approved creators? Send the shortlist. Your account manager replies within 1 working day with prices, deliverables and dates." },
      { target: "#hv-bell", also: "#hv-bell-drop", clip: "point", run: "bell", pad: 8,
        t: "The answer lands in your bell", p: "Quotes, finished analyses and campaign updates arrive here, in the portal only. Nothing is booked until you confirm." }
    ] },
    { ch: 3, name: "Track your campaign live", beats: [
      { view: "campaign", fresh: true, target: "#mx-verdict", also: "#mx-scoreline", clip: "point",
        t: "The verdict comes first", p: "On track, behind or ahead, against your targets. The report updates every 24 hours, from start to finish." },
      { target: "#mx-wall", clip: "point", run: "tab:content",
        t: "Every post, live", p: "Each post with its views, engagement and a good, moderate or low signal against the benchmark." },
      { target: "#mx-clicks", clip: "point", run: "tab:clicks",
        t: "Clicks from tracking links", p: "Each creator gets their own link: clicks, unique people and click-through, by creator, app, country and device." },
      { target: "#mx-podium", alt: "#sec-leaderboard", clip: "celebrate", run: "tab:leaderboard",
        t: "Who performed best", p: "Creators ranked against the campaign objective, with the medals and the full table." },
      { target: ".cx-eva", also: "#mx-carousel-wrap", clip: "point", run: "tab:overview",
        t: "Estimate vs actual", p: "The ROI estimate you saved before the campaign, against what really happened. Plus the timeline of every step, from brief to report." }
    ] },
    { ch: 3, name: "Where everything lives", beats: [
      { view: "catalogue", fresh: true, target: "#pt-menu", also: "#pt-avatar", clip: "point", run: "menu", pad: 10,
        t: "Where everything lives", p: "Your circle menu opens your profile: Selections, Analyses, Campaigns, Credits. Campaign tracking is the button beside it. Finish your profile for up to 30 credits." },
      { finish: true, clip: "celebrate", t: "You're all set", p: "That's the whole journey: brief, shortlist, check, book, track." }
    ] }
  ];

  var T = null;   // the running tour
  function flat() { var out = []; STOPS.forEach(function (s, si) { s.beats.forEach(function (b, bi) { out.push({ s: si, b: bi }); }); }); return out; }
  var ORDER = flat();
  function firstOfChapter(c) { for (var i = 0; i < ORDER.length; i++) if (STOPS[ORDER[i].s].ch === c) return i; return 0; }

  function clipNode(name, cls, opts) { return HV.clip ? HV.clip(name, cls, opts) : h("span"); }

  function start(chapter) {
    if (T) return;
    var m = HV.me || {};
    Demo.user = m.user && m.user.name ? m.user.name : "Sara Haddad";
    Demo.active = true;
    STATE = freshState(Demo.user);
    var prevFocus = document.activeElement;
    var root = h("div", { class: "tv", role: "region", "aria-label": "HELVY Connect tour, demo mode" });
    var exit = h("button", { class: "tv-exit", type: "button", html: ic("x") + "<span>Exit demo</span>" });
    var chaps = h("ol", { class: "tv-chaps", "aria-label": "Tour chapters" });
    CHAPTERS.forEach(function (c, i) {
      var b = h("button", { type: "button", class: "tv-chap", "data-ch": String(i), html: ic(c[1]) + "<span><small>" + (i + 1) + "</small>" + c[0] + "</span>" });
      b.addEventListener("click", function () { go(firstOfChapter(i)); });
      chaps.appendChild(h("li", null, b));
    });
    var bar = h("header", { class: "tv-bar" },
      h("div", { class: "tv-bar__id" }, h("span", { class: "tv-badge" }, "Demo"),
        h("p", null, h("b", null, SEL_NAME), h("span", null, "Sample data · nothing you do here is saved"))),
      chaps, exit);
    var stage = h("div", { class: "tv-stage" });
    var frame = h("iframe", { class: "tv-frame", title: "HELVY Connect demo", "data-hv-demo": "1", tabindex: "0" });
    var shutter = h("div", { class: "tv-shutter", "aria-hidden": "true" });
    var spot = h("div", { class: "tv-spot", "aria-hidden": "true", hidden: "" });
    stage.appendChild(frame); stage.appendChild(spot); stage.appendChild(shutter);
    var coach = h("aside", { class: "tv-coach", role: "dialog", "aria-modal": "false", "aria-labelledby": "tv-t", "aria-describedby": "tv-p", tabindex: "-1" });
    var live = h("p", { class: "tv-sr", "aria-live": "polite" });
    root.appendChild(bar); root.appendChild(stage); root.appendChild(coach); root.appendChild(live);
    document.body.appendChild(root);
    var overflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = "hidden";
    T = { root: root, frame: frame, stage: stage, spot: spot, shutter: shutter, coach: coach, live: live, chaps: chaps, i: -1, view: null, prev: prevFocus, overflow: overflow, timers: [], seq: 0 };
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
    requestAnimationFrame(function () { root.classList.add("is-in"); });
    go(chapter != null ? firstOfChapter(chapter) : 0);
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
  function viewOf(i) { for (var k = i; k >= 0; k--) { var b = beat(k); if (b.view) return b.view; if (b.finish) continue; } return "catalogue"; }
  function later_(fn, ms) { var id = setTimeout(fn, ms); if (T) T.timers.push(id); return id; }
  function win() { return T && T.frame.contentWindow; }
  function doc() { try { return T && T.frame.contentDocument; } catch (e) { return null; } }

  // Load a page into the frame (the shutter covers the switch and names the chapter when it changes).
  function load(view, then) {
    var seq = ++T.seq, url = ROOT + PAGES[view];
    T.shutter.classList.add("is-on");
    T.spot.hidden = true;
    var done = false;
    function ready() {
      if (done || !T || seq !== T.seq) return;
      done = true;
      T.view = view;
      later_(function () { if (T && seq === T.seq) { T.shutter.classList.remove("is-on"); then(); } }, 120);
    }
    T.frame.onload = function () {
      var d = doc();
      if (d) d.documentElement.classList.add("tv-demo-frame");
      // The page draws itself after load: wait for its main content.
      var want = { catalogue: ".cat-card[data-code]", selection: "#sel-statusbar", analysis: "#pp-gate-band", locked: "#pp-gate-band", campaign: "#mx-verdict" }[view];
      waitFor(want, 12000, ready);
    };
    if (T.frame.getAttribute("src") === url) T.frame.contentWindow.location.reload();
    else T.frame.setAttribute("src", url);
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
    T.i = i;
    T.timers.forEach(clearTimeout); T.timers = [];
    paintChapters(STOPS[o.s].ch);
    // A new stop reloads its page fresh, so every stop starts from the same demo screen.
    var reload = !T.view || view !== T.view || (o.s !== prevStop && STOPS[o.s].beats[0].fresh && o.b === 0) || (!forward && o.s !== prevStop);
    drawCoach(b, i);
    if (b.finish) {
      T.spot.hidden = true; T.root.classList.add("is-finish");
      var fd = doc(), mm = fd && fd.getElementById("pt-menu");
      if (mm && !mm.hidden) { var av = fd.getElementById("pt-avatar"); if (av) av.click(); }
      return;
    }
    T.root.classList.remove("is-finish");
    if (reload) { T.coach.classList.add("is-wait"); load(view, function () { T.coach.classList.remove("is-wait"); act(b); }); }
    else act(b);
  }
  function paintChapters(c) {
    [].forEach.call(T.chaps.querySelectorAll(".tv-chap"), function (x, k) {
      x.classList.toggle("is-now", k === c); x.classList.toggle("is-done", k < c);
      if (k === c) x.setAttribute("aria-current", "step"); else x.removeAttribute("aria-current");
    });
  }

  /* -- the coach: Helvy (cut-out, looping) beside the words -- */
  function drawCoach(b, i) {
    var o = ORDER[i], stop = STOPS[o.s], c = T.coach;
    c.textContent = "";
    c.className = "tv-coach" + (b.finish ? " tv-coach--finish" : "") + (T.coach.classList.contains("is-wait") ? " is-wait" : "");
    var helvy = h("div", { class: "tv-coach__helvy" }, clipNode(b.clip || "point", "tv-hv", b.clip === "celebrate" ? { once: true, then: "idle" } : null));
    var dots = h("ol", { class: "tv-dots", "aria-hidden": "true" });
    STOPS.forEach(function (s, k) {
      var li = h("li", { class: k < o.s ? "is-done" : k === o.s ? "is-now" : "" });
      if (k === o.s && s.beats.length > 1) { var f = h("i"); f.style.width = Math.round((o.b + 1) / s.beats.length * 100) + "%"; li.appendChild(f); }
      dots.appendChild(li);
    });
    var head = h("div", { class: "tv-coach__prog" }, dots, h("span", null, h("b", null, CHAPTERS[stop.ch][0]), " · " + (o.s + 1) + " of " + STOPS.length));
    var words = h("div", { class: "tv-coach__words" }, head, h("h2", { id: "tv-t" }, b.t), h("p", { id: "tv-p" }, b.p));
    if (b.hint) words.appendChild(h("p", { class: "tv-coach__hint", html: ic("spark") + "<span></span>" })), words.lastChild.querySelector("span").textContent = b.hint;
    if (b.finish) {
      var prize = h("div", { class: "tv-prize" }, h("span", { class: "tv-prize__stamp" }, "+5", h("small", null, "credits")),
        h("p", null, h("b", null, "Added for finishing the tour"), h("span", null, "Spend them on AI shortlists and replacements.")));
      words.appendChild(prize);
      words.appendChild(h("p", { class: "tv-coach__fine", html: ic("help") + "<span>Replay any time from <b>Help</b> or your <b>Profile</b>.</span>" }));
      api("POST", "/api/tour", { action: "done" }).then(function (r) {
        if (!r.b || !r.b.ok) return;
        if (r.b.credits != null && HV.setCredits) HV.setCredits(r.b.credits);
        var p = prize.querySelector("p"); p.textContent = "";
        if (r.b.earned) p.appendChild(h("b", null, "Added for finishing the tour")), p.appendChild(h("span", null, "Your balance is now " + r.b.credits + " credits."));
        else { var stp = prize.querySelector(".tv-prize__stamp"); stp.textContent = "Done"; prize.classList.add("is-replay"); p.appendChild(h("b", null, "Tour replayed")), p.appendChild(h("span", null, "Your 5 credits were added the first time you finished it.")); }
      });
    }
    var nav = h("div", { class: "tv-nav" });
    if (!b.finish) nav.appendChild(h("button", { class: "tv-skip", type: "button", onclick: function () { end("skip"); } }, "Skip tour"));
    else nav.appendChild(h("span", { class: "tv-nav__gap" }));
    if (i > 0) nav.appendChild(h("button", { class: "tv-btn tv-btn--line", type: "button", "aria-label": "Back", html: ic("back") + "<span>Back</span>", onclick: back }));
    var last = i === ORDER.length - 2;
    nav.appendChild(h("button", { class: "tv-btn", type: "button", html: "<span>" + (b.finish ? "Finish tour" : last ? "Finish" : "Next") + "</span>" + ic(b.finish ? "check" : "arrow"), onclick: next }));
    words.appendChild(nav);
    c.appendChild(helvy); c.appendChild(words);
    T.live.textContent = "Stop " + (o.s + 1) + " of " + STOPS.length + ": " + b.t;
    if (!REDUCE) { c.classList.remove("is-pop"); void c.offsetWidth; c.classList.add("is-pop"); }
    setTimeout(function () { if (T && T.coach === c) { var nb = c.querySelector(".tv-nav .tv-btn:last-child"); if (nb) nb.focus({ preventScroll: true, focusVisible: false }); } }, 30);
  }

  /* -- what a beat does in the frame, then where the light goes -- */
  function act(b) {
    var w = win(), d = doc();
    if (!w || !d) return;
    var run = b.run || "";
    var P = w.hvPortal || {};
    // Close anything a previous beat left open.
    if (run.indexOf("chat") !== 0 && P.voiceClose) P.voiceClose();
    if (run !== "menu") { var mm = d.getElementById("pt-menu"); if (mm && !mm.hidden) { var av = d.getElementById("pt-avatar"); if (av) av.click(); } }
    if (run !== "bell") { var bd = d.getElementById("hv-bell-drop"); if (bd && !bd.hidden) { var bl = d.getElementById("hv-bell"); if (bl) bl.click(); } }
    if (run === "chatBrief" || run === "chatBudget") {
      var text = run === "chatBrief" ? "Find me 5 skincare creators in Riyadh for a Ramadan launch" : "What can 50,000 SAR reach?";
      if (P.voiceDemo) P.voiceDemo(text, run === "chatBrief");
      waitFor("#hv-panel:not([hidden])", 4000, function () { light(b); });
      // The panel grows as the answer arrives: keep the light on it.
      for (var k = 1; k < 14; k++) later_(function () { light(b, true); }, k * 700);
      return;
    }
    if (run === "aiCard") {
      var card = d.getElementById("ai-sl");
      if (card) card.scrollIntoView({ block: "center" });
      if (P.aiDemo) later_(function () { P.aiDemo({ goal: "engagement", platforms: ["Instagram", "TikTok"], market: "SA", category: ["skincare"], budget: "50000", count: "5" }, CAMPAIGN); }, 500);
      light(b);
      // The card grows into the director's desk once it starts: bring it into view again, then follow it.
      later_(function () { light(b); }, 900); later_(function () { light(b); }, 1700);
      for (var j = 3; j < 16; j++) later_(function () { light(b, true); }, j * 600);
      return;
    }
    if (run === "scoreTip") {
      waitFor(b.target, 4000, function (el) {
        if (!el) return light(b);
        el.scrollIntoView({ block: "center" });
        later_(function () { el.dispatchEvent(new w.MouseEvent("mouseenter")); light(b, false, d.querySelector(".cat-score-tip")); }, 260);
      });
      return;
    }
    if (run === "cardHover") {
      waitFor(b.target, 4000, function (el) { if (el) el.scrollIntoView({ block: "center" }); later_(function () { light(b); }, 200); });
      return;
    }
    if (run === "replace") {
      waitFor(b.target, 4000, function (el) {
        if (!el) return light(b);
        el.scrollIntoView({ block: "center" });
        var rb = el.querySelector("[data-st-repl]");
        later_(function () { if (rb) rb.click(); }, 900);
        light(b);
        for (var r = 1; r < 12; r++) later_(function () { light(b, true); }, r * 600);
      });
      return;
    }
    if (run === "bell") {
      var bell = d.getElementById("hv-bell");
      // The drop closes on scroll: scroll first, open it once the page has settled, light without scrolling.
      w.scrollTo(0, 0);
      later_(function () { if (bell && d.getElementById("hv-bell-drop").hidden) bell.click(); later_(function () { light(b, true); }, 300); }, 250);
      return;
    }
    if (run === "menu") {
      var avb = d.getElementById("pt-avatar");
      w.scrollTo(0, 0);
      if (avb && d.getElementById("pt-menu").hidden) avb.click();
      if (avb) avb.blur();
      later_(function () { light(b); }, 300);
      return;
    }
    if (run.indexOf("tab:") === 0) {
      var tab = d.getElementById("tab-" + run.slice(4));
      if (tab) { tab.click(); }
      // The tab scrolls smoothly to its section: light once it has landed, then make sure.
      later_(function () { light(b); }, 350); later_(function () { light(b); }, 1100);
      return;
    }
    light(b);
  }

  // The spotlight: the target (and its companion) lit, the rest of the frame dimmed. The frame
  // scrolls so the target sits in the space the coach leaves free.
  function rectOf(el) { var r = el.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom }; }
  function light(b, quiet, extra) {
    if (!T || !b.target) return;
    var d = doc(), w = win();
    if (!d) return;
    var el = d.querySelector(b.target);
    if ((!el || !el.getBoundingClientRect().height) && b.alt) el = d.querySelector(b.alt);
    if (!el || !el.getBoundingClientRect().height) { T.spot.hidden = true; place(); return; }
    var mob = window.innerWidth <= 760;
    var stageR = T.stage.getBoundingClientRect(), coachH = mob ? T.coach.offsetHeight : 0;
    var free = stageR.height - coachH;
    if (!quiet) {
      var r0 = el.getBoundingClientRect();
      var top = 24, bottom = free - 24;
      if (r0.top < top || r0.bottom > bottom) {
        var y = r0.height > bottom - top ? r0.top - top : r0.top - (top + (bottom - top - r0.height) / 2);
        w.scrollBy(0, Math.round(y));
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
    var L = Math.max(4, r.l - pad), Tp = Math.max(4, r.t - pad), R = Math.min(vw - 4, r.r + pad), B = Math.min(vh - 4, r.b + pad);
    T.spot.hidden = false;
    T.spot.style.transform = "translate(" + Math.round(L) + "px," + Math.round(Tp) + "px)";
    T.spot.style.width = Math.max(24, Math.round(R - L)) + "px"; T.spot.style.height = Math.max(24, Math.round(B - Tp)) + "px";
    T.lit = { l: L + stageR.left, t: Tp + stageR.top, r: R + stageR.left, b: B + stageR.top };
    place();
    // Scrolling the frame by hand keeps the light on the target.
    if (w && !w.__tvScroll) {
      w.__tvScroll = true;
      var tick = 0;
      w.addEventListener("scroll", function () { if (tick) return; tick = requestAnimationFrame(function () { tick = 0; if (T && T.i >= 0) light(beat(T.i), true); }); }, { passive: true });
    }
  }
  // Desktop: the coach sits beside the lit area, Helvy facing it. Mobile: docked at the bottom.
  function place() {
    if (!T) return;
    var c = T.coach, vw = window.innerWidth, vh = window.innerHeight;
    if (vw <= 760 || T.root.classList.contains("is-finish") || !T.lit || T.spot.hidden) { c.style.left = c.style.top = c.style.right = c.style.bottom = ""; c.classList.remove("is-flip"); return; }
    var w = c.offsetWidth, hh = c.offsetHeight, L = T.lit, gap = 28, left, top;
    // Room above the card for Helvy, who stands on its top edge.
    var stageTop = T.stage.getBoundingClientRect().top + 96;
    if (vw - L.r - gap >= w + 16) { left = L.r + gap; top = Math.max(stageTop + 16, Math.min(vh - hh - 16, L.t)); }
    else if (L.l - gap >= w + 16) { left = L.l - gap - w; top = Math.max(stageTop + 16, Math.min(vh - hh - 16, L.t)); }
    else if (vh - L.b - gap >= hh + 16) { top = L.b + gap; left = Math.max(16, Math.min(vw - w - 16, L.r - w)); }
    else if (L.t - gap - stageTop >= hh + 16) { top = L.t - gap - hh; left = Math.max(16, Math.min(vw - w - 16, L.r - w)); }
    else { left = vw - w - 24; top = vh - hh - 24; }
    c.style.right = c.style.bottom = "auto";
    c.style.left = Math.round(left) + "px"; c.style.top = Math.round(top) + "px";
    c.classList.toggle("is-flip", left + w / 2 < (L.l + L.r) / 2);
  }

  window.hvTour = { start: start, end: function () { end("skip"); }, key: function (e) { if (T) T.onKey(e); }, chapters: CHAPTERS, stops: STOPS };
})();
