// Loads assets/js/tour.js in a bare sandbox (no DOM), seeds it with the demo roster file and prints what
// the demo API answers to every endpoint the tour's steps use, as one JSON document on stdout.
// Used by admin/tests/e2e_tour_v3.py to compare the demo's response shapes with the server's.
//   node admin/tests/tour_demo_dump.js <repo root>
const vm = require("vm"), fs = require("fs"), path = require("path");
const root = process.argv[2] || path.resolve(__dirname, "../..");
const win = { hvPortal: {} };
win.window = win;
const ctx = vm.createContext(Object.assign(win, { console, Date, JSON, Math, URL, URLSearchParams, setTimeout, clearTimeout, TextEncoder }));
vm.runInContext(fs.readFileSync(path.join(root, "assets/js/tour.js"), "utf8"), ctx, { filename: "tour.js" });
const D = win.hvTourDemo;
D.setRoster(JSON.parse(fs.readFileSync(path.join(root, "assets/demo/demo-roster.json"), "utf8")));
D.reset("Sara Haddad");
const Q = (o) => new URLSearchParams(o || {});
const A = (m, p, q, b) => D.answer(m, p, Q(q), b || {});
const out = {};
out.me = A("GET", "/api/me").b;
out.selection = A("GET", "/api/selection", { s: "demo-ramadan" }).b;
out.roster = A("GET", "/api/roster").b;
out.page = A("GET", "/api/roster/page").b;
out.scores = A("GET", "/api/brief/scores").b;
out.questions = A("GET", "/api/brief/questions").b;
out.briefRun = A("POST", "/api/brief/run", {}, { answers: {} }).b;
out.briefFor = A("GET", "/api/brief/for", { s: "demo-ramadan" }).b;
const est = (body) => A("POST", "/api/roi/estimate", {}, Object.assign({ goals: ["awareness", "engagement"], goal: "awareness", platforms: ["Instagram", "TikTok"], token: "demo-ramadan", which: "approved" }, body)).b;
out.estimate = est({});
out.estimateCount = est({ count: 15 });
out.estimateSingle = est({ goals: ["traffic"], goal: "traffic", count: 8 });
out.estimateMix = est({ token: undefined, mix: { macro: 1, mid: 3, micro: 6 }, platforms: ["Instagram"] });
out.roiSaved = A("GET", "/api/roi/saved", { s: "demo-ramadan" }).b;
out.roiVs = A("GET", "/api/roi/vs").b;
out.sample = A("GET", "/api/analysis/sample").b;
out.creatorLocked = A("GET", "/api/creator", { c: "DEMO-05" }).b;
out.creatorOpen = A("GET", "/api/creator", { c: "DEMO-01" }).b;
out.creatorRequest = A("POST", "/api/creator/request", {}, { code: "DEMO-05" }).b;
out.voiceSelection = A("GET", "/api/voice/selection", { s: "demo-ramadan" }).b;
out.account = A("GET", "/api/account").b;
out.campaign = A("GET", "/api/campaign", { t: "demo-ramadan-live" }).b;
out.handoff = A("POST", "/api/chat/handoff", {}, { thread: "demo" }).b;
// the lifecycle at each step of the story
out.lifecycle = {};
["draft", "requested", "ready", "approved", "live", "completed"].forEach((k) => { D.setLc(k); out.lifecycle[k] = D.lifecycle(); });
D.setLc("ready");
out.approve = A("POST", "/api/selection/quote/approve", {}, { token: "demo-ramadan" }).b;
// chat: the events each scripted question streams
const chat = (text) => A("POST", "/api/chat/stream", {}, { message: text }).stream.map((e) => e[1]);
out.chat = {
  explain: chat("Why did Dr. Ghada score 88?"), compare: chat("Compare Lulwa and Nada"),
  hand: chat("Can you get me a better rate?"), find: chat("Find me 5 skincare creators in Riyadh"),
  roi: chat("What can 10 creators do for awareness?")
};
process.stdout.write(JSON.stringify(out));
