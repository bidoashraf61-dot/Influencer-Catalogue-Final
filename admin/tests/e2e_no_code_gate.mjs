// Item 181 (2026-10-20): the old ACCESS CODE page must never appear. Everyone signs in with their
// work email (HELVi Connect), so the gate is the email sign-in or, while the page asks the server,
// the logo alone. This drives the real page scripts (catalogue.js, portal.js, campaign.js) in
// Chrome against a MOCK admin API whose answers and timings each scenario sets, and samples the page
// every 40 ms: a visible password field, a #cat-code field or the words "access code" fail the run.
//
//   node admin/tests/e2e_no_code_gate.mjs [--chrome "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
//
// Needs playwright-core (npm i playwright-core, or PLAYWRIGHT_CORE=/path/to/node_modules/playwright-core)
// and Google Chrome. No server, database or network: the static pages come from this checkout.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
let pw;
try { pw = require("playwright-core"); } catch (e) { pw = require(process.env.PLAYWRIGHT_CORE || "playwright-core"); }
const arg = (k, d) => { const i = process.argv.indexOf("--" + k); return i > -1 ? process.argv[i + 1] : d; };
const CHROME = arg("chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome");
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ------------------------------------------------------------ mock admin API --
   S is the current scenario: { me: {status, signedIn, delay}, roster: [answer...] (one per call, the
   last repeats), campaign: answer }. An answer is { status, delay }. */
let S = null;
const calls = { roster: 0 };
function answer(res, a, body) {
  setTimeout(() => {
    if (!a.status) { res.socket.destroy(); return; }          // no answer at all (connection dropped)
    if (a.status === 502) { res.writeHead(502, { "Content-Type": "text/html" }); res.end("<html>Bad Gateway</html>"); return; }
    res.writeHead(a.status, { "Content-Type": "application/json" });
    res.end(JSON.stringify(a.status === 200 ? body : { ok: false, reason: "locked" }));
  }, a.delay || 0);
}
const ROSTER_OK = { ok: true, items: [], cards: [], has_more: false, cursor: null, v: "t", facets: {}, tiers: {}, fx: {}, exp: 0 };
const TYPES = { ".html": "text/html", ".js": "application/javascript", ".css": "text/css", ".webp": "image/webp", ".png": "image/png", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".jpg": "image/jpeg" };
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://x");
  const p = url.pathname;
  if (p.startsWith("/admin/")) {
    if (p === "/admin/api/me") {
      const m = S.me;
      return answer(res, { status: m.status || 200, delay: m.delay }, m.signedIn
        ? { ok: true, signed_in: true, kind: "user", user: { name: "Sara Haddad", email: "sara@northwind.com" }, credits: 5 }
        : { ok: true, signed_in: false, ai: false, signup: "open", email_signin: m.mail !== false, passcodes: false });
    }
    if (/^\/admin\/api\/roster\/(page|facets|cards)$/.test(p)) {
      const list = S.roster, a = list[Math.min(calls.roster, list.length - 1)];
      calls.roster++;
      return answer(res, a, ROSTER_OK);
    }
    if (p === "/admin/api/campaign" || p === "/admin/api/campaigns" || p === "/admin/api/creator") return answer(res, S.campaign || { status: 401 }, { ok: true, campaigns: [] });
    res.writeHead(404, { "Content-Type": "application/json" }); return res.end('{"ok":false}');
  }
  let f = path.join(ROOT, decodeURIComponent(p));
  if (!f.startsWith(ROOT)) { res.writeHead(403); return res.end(); }
  if (p.endsWith("/")) f = path.join(f, "index.html");
  fs.readFile(f, (err, buf) => {
    if (err) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { "Content-Type": TYPES[path.extname(f)] || "application/octet-stream", "Cache-Control": "no-store" });
    res.end(buf);
  });
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const BASE = "http://127.0.0.1:" + server.address().port;

/* --------------------------------------------------------------- the probe -- */
// What the visitor can see of the gate right now.
const PROBE = () => {
  const vis = (el) => !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== "hidden";
  const gate = document.getElementById("cat-gate");
  const text = gate && vis(gate) ? (gate.innerText || "") : "";
  const pw = Array.from(document.querySelectorAll('input[type="password"], #cat-code')).filter(vis).length;
  return {
    codeForm: pw > 0 || /access code|enter the code|unlock/i.test(text),
    signIn: !!gate && vis(gate) && gate.classList.contains("cx-gate") && vis(gate.querySelector('input[type="email"]')),
    gateShown: !!gate && vis(gate),
    appShown: vis(document.getElementById("cat-app")),
    note: (document.getElementById("cat-gate-note") && vis(document.getElementById("cat-gate-note")) ? document.getElementById("cat-gate-note").innerText : "")
      + (document.querySelector(".cat-loadfail") ? document.querySelector(".cat-loadfail").innerText : ""),
    okCookie: /(?:^|; )cat-ok=1/.test(document.cookie),
  };
};

const browser = await pw.chromium.launch({ executablePath: CHROME, headless: true });
const results = [];
async function run(name, scenario, url, opts, check) {
  S = scenario; calls.roster = 0;
  const ctx = await browser.newContext();
  if (opts.okCookie) await ctx.addCookies([{ name: "cat-ok", value: "1", url: BASE }]);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  const seen = [];
  const t0 = Date.now();
  await page.goto(BASE + url, { waitUntil: "commit" });
  while (Date.now() - t0 < opts.watch) {
    try { seen.push(await page.evaluate(PROBE)); } catch (e) { /* navigating */ }
    await sleep(40);
  }
  const last = seen[seen.length - 1] || {};
  const problems = [];
  if (seen.some((s) => s.codeForm)) problems.push("an access-code form was visible");
  problems.push(...check(last, seen));
  results.push({ name, ok: !problems.length, problems, samples: seen.length, errors: errors.slice(0, 3) });
  await ctx.close();
}

const W = 2600;
// 1. Signed out; the roster says 401 at once, /api/me is slow: the old code showed the code form
//    until portal.js caught up. Now: logo, then the email sign-in.
await run("catalogue: signed out, slow /api/me", { me: { delay: 900 }, roster: [{ status: 401 }] }, "/", { watch: W },
  (l) => (l.signIn ? [] : ["the email sign-in never appeared"]));
// 2. Signed out; /api/me fast, the roster slow.
await run("catalogue: signed out, slow roster", { me: {}, roster: [{ status: 401, delay: 900 }] }, "/", { watch: W },
  (l) => (l.signIn ? [] : ["the email sign-in never appeared"]));
// 3. The old "until the mail key is saved, keep the access-code gate": email_signin false must
//    still give the email sign-in, never the code form.
await run("catalogue: signed out, mail not configured", { me: { mail: false }, roster: [{ status: 401 }] }, "/", { watch: W },
  (l) => (l.signIn ? [] : ["the email sign-in never appeared"]));
// 4. Signed in; the admin service restarts (two 502s, then fine): the old code dropped the pass hint
//    and put the code form back. Now: the shell stays, then the catalogue.
await run("catalogue: signed in, 502 then OK", { me: { signedIn: true }, roster: [{ status: 502 }, { status: 502 }, { status: 200 }] }, "/",
  { watch: 6500, okCookie: true },
  (l, seen) => [].concat(seen.some((s) => s.gateShown) ? ["the gate showed for a signed-in client"] : [],
    l.appShown ? [] : ["the catalogue never opened"], l.okCookie ? [] : ["the pass hint was forgotten"]));
// 5. Signed in; the server never answers properly: a "could not reach" message, the hint kept.
await run("catalogue: signed in, server down", { me: { signedIn: true }, roster: [{ status: 503 }] }, "/",
  { watch: 12500, okCookie: true },
  (l, seen) => [].concat(seen.some((s) => s.gateShown) ? ["the gate showed for a signed-in client"] : [],
    /couldn.t reach/i.test(l.note) ? [] : ["no 'could not reach' message: " + JSON.stringify(l.note)],
    l.okCookie ? [] : ["the pass hint was forgotten"]));
// 6. Signed out but the browser kept the hint (shell first), the network drops (no answer at all).
await run("catalogue: hint kept, connection refused then 401", { me: {}, roster: [{ status: 0 }, { status: 401 }] }, "/",
  { watch: 4500, okCookie: true }, (l) => (l.signIn ? [] : ["the email sign-in never appeared"]));
// 7. /api/me says signed in but the roster refuses (a pass that just lapsed): sign-in, not a bare gate.
await run("catalogue: /api/me signed in, roster 401", { me: { signedIn: true }, roster: [{ status: 401 }] }, "/", { watch: W },
  (l) => (l.signIn ? [] : ["the email sign-in never appeared"]));
// 8. A shared selection link, signed out: sign-in (the page reloads on the same #s= link afterwards).
await run("selection link: signed out", { me: { delay: 600 }, roster: [{ status: 401 }] }, "/selection/#s=AbC123", { watch: W },
  (l) => (l.signIn ? [] : ["the email sign-in never appeared"]));
// 9. A shared campaign report link, signed out (the server answers 401 with passcodes off).
await run("campaign link: signed out", { me: { delay: 600 }, roster: [{ status: 401 }], campaign: { status: 401 } }, "/campaign/#t=tok123", { watch: W },
  (l) => (l.signIn ? [] : ["the email sign-in never appeared"]));
// 10. The campaign dashboard and the creator page, signed out.
await run("campaign dashboard: signed out", { me: {}, roster: [{ status: 401 }], campaign: { status: 401 } }, "/campaign/dashboard/#t=tok123", { watch: W },
  (l) => (l.signIn ? [] : ["the email sign-in never appeared"]));

await run("creator page: signed out", { me: { delay: 600 }, roster: [{ status: 401 }], campaign: { status: 401 } }, "/creator/#c=HV-MI-001", { watch: W },
  (l) => (l.signIn ? [] : ["the email sign-in never appeared"]));

await browser.close();
server.close();
let bad = 0;
for (const r of results) {
  if (!r.ok) bad++;
  console.log((r.ok ? "ok   " : "FAIL ") + r.name + (r.ok ? "" : "  -> " + r.problems.join("; ")) + (r.errors.length ? "  [page errors: " + r.errors.join(" | ").slice(0, 200) + "]" : ""));
}
console.log(results.length - bad + "/" + results.length + " passed");
process.exit(bad ? 1 : 0);
