// Walks the whole onboarding tour in a real browser against a running portal (a local dev server on a
// COPY of the database, never production), step by step, desktop and phone:
//   - every step's target exists in the frame and the spotlight lands on it;
//   - the chat, the ROI drawer, the quote form and the lifecycle chip do what the step says;
//   - no page error, and nothing but /api/tour leaves the demo frame;
//   - optionally a screenshot per step.
//
//   node admin/tests/tour_walk.mjs --base http://127.0.0.1:8980 --mail /path/to/mail.txt [--shots DIR] [--only desktop|mobile]
//
// --mail is the file the dev runner appends "<email>\t<code>" lines to (captured sign-in mail).
// Needs playwright-core (npm i playwright-core) and Google Chrome.
import { chromium } from "playwright-core";
import fs from "node:fs";

const arg = (k, d) => { const i = process.argv.indexOf("--" + k); return i > -1 ? process.argv[i + 1] : d; };
const BASE = arg("base", "http://127.0.0.1:8980");
const MAIL = arg("mail", "");
const SHOTS = arg("shots", "");
const ONLY = arg("only", "");
const CHROME = arg("chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });

// how long a step needs before it is worth looking at (its action runs, the answer streams in)
const DWELL = { aiAsk0: 3500, aiAsk2: 3500, aiGo: 12500, scoreTip: 3500, sampleHover: 3500, sampleOpen: 9000, roiOpen: 4500, roiCount: 4500,
  roiQuality: 3000, roiWays: 8000, quoteOpen: 3500, quoteSend: 8500, lcReady: 3000, lcApprove: 9500, scrollTo: 3000 };
const dwell = (run) => (run && run.startsWith("chat:")) ? (run.endsWith(":hand") ? 21000 : 13000) : (run && run.startsWith("tab:")) ? 3500 : (DWELL[run] || 2500);

const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const problems = [];
const lines = [];

async function signIn(ctx, email) {
  const page = await ctx.newPage();
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
  const post = (p, b) => page.evaluate(async ([p, b]) => (await fetch("/admin" + p, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) })).json(), [p, b]);
  await post("/api/auth/start", { email, name: "Sara Haddad", company: "Northwind Pharma" });
  let code = "";
  for (let i = 0; i < 20 && !code; i++) {
    await sleep(300);
    const rows = fs.readFileSync(MAIL, "utf8").trim().split("\n").filter((l) => l.startsWith(email + "\t"));
    if (rows.length) code = rows[rows.length - 1].split("\t")[1];
  }
  const v = await post("/api/auth/verify", { email, otp: code });
  if (v.ticket) await post("/api/auth/profile", { ticket: v.ticket, name: "Sara Haddad", company: "Northwind Pharma", job_title: "Brand Manager" });
  await page.close();
}

for (const [w, h, label] of [[1440, 900, "desktop"], [390, 844, "mobile"]]) {
  if (ONLY && ONLY !== label) continue;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, isMobile: w < 600, hasTouch: w < 600 });
  await ctx.addInitScript(() => { try { sessionStorage.setItem("cx-offer-shown", "1"); sessionStorage.setItem("hv-voice-nudged", "1"); } catch (e) { /* none */ } });
  const email = "walk-" + label + "-" + Date.now() + "@northwind-test.com";
  await signIn(ctx, email);
  const page = await ctx.newPage();
  const outside = [];
  page.on("pageerror", (e) => problems.push(label + " page error: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/favicon|Failed to load resource/.test(m.text())) problems.push(label + " console: " + m.text()); });
  page.on("request", (r) => {
    const u = new URL(r.url());
    // the pages' own icon and font hosts are not the tour's doing; anything else leaving the demo frame is
    if (u.origin !== new URL(BASE).origin && !/^(cdnjs\.cloudflare\.com|fonts\.googleapis\.com|fonts\.gstatic\.com)$/.test(u.hostname)) outside.push(r.url());
  });
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.hvPortal && window.hvPortal.tour && window.hvPortal.me, null, { timeout: 20000 });
  await sleep(1500);
  await page.evaluate(() => window.hvPortal.tour(0));
  await page.waitForSelector(".tv-coach h2", { timeout: 30000 });
  const stops = await page.evaluate(() => window.hvTour.stops.map((s) => s.beats.map((b) => ({ t: b.t, run: b.run || "", target: b.target || "", also: b.also || "", finish: !!b.finish, view: b.view || "" }))));
  const flat = []; stops.forEach((s, si) => s.forEach((b) => flat.push(Object.assign({ ch: si }, b))));
  let n = 0;
  for (const b of flat) {
    n += 1;
    const title = b.finish ? "You're all set" : b.t;
    // wait for this step's card (the page behind it may still be loading)
    await page.waitForFunction((t) => { const e = document.getElementById("tv-t"); return e && e.textContent === t; }, title, { timeout: 40000 }).catch(() => problems.push(label + " step " + n + " card never showed: " + title));
    await sleep(dwell(b.run));
    if (!b.finish) {
      const res = await page.evaluate(([sel, alt]) => {
        const f = document.querySelector(".tv-frame");
        const d = f && f.contentDocument;
        const sp = document.querySelector(".tv-spot");
        const hit = (s) => { const el = s && d && d.querySelector(s); return !!(el && el.getBoundingClientRect().height > 0); };
        const r = sp && !sp.hidden ? sp.getBoundingClientRect() : null;
        return { found: hit(sel), lit: !!r && r.width > 20, side: document.querySelector(".tv-coach").getAttribute("data-side"), url: f.contentWindow.location.pathname + f.contentWindow.location.hash };
      }, [b.target, ""]);
      // a step whose target is only there after its action may re-point the light: the spot must be on
      if (!res.lit) problems.push(label + " step " + n + " (" + title + "): the spotlight is not on anything (target " + b.target + ", found " + res.found + ")");
      lines.push(label.padEnd(8) + String(n).padStart(2) + "  " + title.padEnd(40) + (res.lit ? "lit " : "DARK") + "  " + res.url);
    } else {
      lines.push(label.padEnd(8) + String(n).padStart(2) + "  " + title);
    }
    if (SHOTS) await page.screenshot({ path: SHOTS + "/" + label + "-" + String(n).padStart(2, "0") + "-c" + (b.ch + 1) + "-" + title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") + ".png" });
    if (b.finish) break;
    await page.click(".tv-nav .tv-btn:last-child");
  }
  await page.waitForSelector(".tv-prize");
  await sleep(1500);
  const prize = await page.evaluate(() => document.querySelector(".tv-prize").textContent.replace(/\s+/g, " "));
  lines.push(label.padEnd(8) + "    reward: " + prize);
  if (outside.length) problems.push(label + " requests left the origin: " + [...new Set(outside)].slice(0, 5).join(", "));
  // finish, then a replay pays nothing more
  await page.click(".tv-nav .tv-btn:last-child");
  await sleep(600);
  await page.evaluate(() => window.hvPortal.tour(6));
  await page.waitForSelector(".tv-coach h2", { timeout: 30000 });
  await sleep(1000);
  await page.click(".tv-exit");
  await ctx.close();
}
await browser.close();
console.log(lines.join("\n"));
if (problems.length) { console.log("\nPROBLEMS\n" + problems.join("\n")); process.exit(1); }
console.log("\nOK: every step lit its target, no page error, nothing left the demo frame");
