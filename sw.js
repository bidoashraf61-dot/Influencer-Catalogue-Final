/* HELVi Connect service worker (item 168): offline fallback, push alerts, taps.

   Pages always come from the network (client data is private and changes all day);
   the cache only holds the app shell pieces that carry a content-hash ?v= stamp, the
   app icons and the offline page. Nothing under /admin/ is ever cached.

   Staying current (item 175): deploy/catalogue/stamp_assets.py rewrites VERSION below to a
   hash of the app shell on every publish, so each release is a new worker. It installs at
   once (skipWaiting), drops every older cache and takes over the open app (clients.claim);
   the pages are never cached, so the next load or the update push lands on the new build. */
const VERSION = "hca-3";
const SHELL = ["/offline.html", "/assets/app/icon-192.png", "/assets/app/badge-96.png",
  "/assets/brand/helvy-connect/helvy-connect-light-320.webp",
  "/assets/ref/68efdbc172d0ac625d40c65f_BebasNeue-Regular.woff2"];
const API = "/admin/api/push/";

self.addEventListener("install", (e) => {
  // "reload": the icons sit in the browser's own cache for 30 days; a new worker must not copy an old one.
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL.map((u) => new Request(u, { cache: "reload" }))))
    .then(() => self.skipWaiting()));
});

// The page asks a waiting worker to take over at once ("Update now").
self.addEventListener("message", (e) => {
  if (e.data && e.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin || url.pathname.startsWith("/admin")) return;
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).catch(() => caches.match("/offline.html")));
    return;
  }
  // Video plays by byte ranges (iPhone needs a 206): never answer those from the cache.
  if (req.headers.has("range") || req.destination === "video" || req.destination === "audio") return;
  // Only a content-hash stamp (?v= + 8 hex, written by stamp_assets.py at deploy) promises the
  // URL never changes, so only those are cache first. Hand-set stamps such as ?v=t3 or ?v=c4
  // can outlive an edit; they go to the network like any other file.
  const stamped = /[?&]v=[0-9a-f]{8}(&|$)/.test(url.search) && /\/assets\/(css|js|ref|brand|app|icons)\//.test(url.pathname);
  const appIcon = url.pathname.startsWith("/assets/app/") && /\.(png|webp|jpe?g|svg)$/.test(url.pathname);
  if (stamped || appIcon || SHELL.includes(url.pathname)) {
    // Unstamped icons are revalidated once per release instead of trusting the 30-day browser cache.
    const net = stamped ? req : new Request(req, { cache: "no-cache" });
    e.respondWith(caches.match(req).then((hit) => hit || fetch(net).then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); }
      return res;
    })));
  }
});

function ping(path, body) {
  return fetch(API + path, { method: "POST", credentials: "include", keepalive: true,
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).catch(() => {});
}

self.addEventListener("push", (e) => {
  let m = {};
  try { m = e.data ? e.data.json() : {}; } catch (_) { m = { title: "HELVi Connect", body: e.data ? e.data.text() : "" }; }
  const opts = {
    body: m.body || "",
    icon: "/assets/app/icon-192.png",
    badge: "/assets/app/badge-96.png",
    tag: m.tag || undefined,
    renotify: !!m.tag,
    timestamp: m.at ? m.at * 1000 : Date.now(),
    data: { url: m.url || "/account/", d: m.d, k: m.k },
  };
  const jobs = [self.registration.showNotification(m.title || "HELVi Connect", opts)];
  if (m.d) jobs.push(ping("ack", { d: m.d, k: m.k }));
  if (typeof m.unread === "number" && self.navigator && navigator.setAppBadge) {
    jobs.push((m.unread ? navigator.setAppBadge(m.unread) : navigator.clearAppBadge()).catch(() => {}));
  }
  e.waitUntil(Promise.all(jobs));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const data = e.notification.data || {};
  const target = new URL(data.url || "/account/", location.origin);
  target.searchParams.set("src", "push");
  const jobs = [];
  if (data.d) jobs.push(ping("click", { d: data.d, k: data.k }));
  jobs.push(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((wins) => {
    for (const w of wins) {
      if (new URL(w.url).origin === location.origin && "navigate" in w) {
        return w.focus().then(() => w.navigate(target.href)).catch(() => self.clients.openWindow(target.href));
      }
    }
    return self.clients.openWindow(target.href);
  }));
  e.waitUntil(Promise.all(jobs));
});

// The push service rotated the subscription: hand the new one to the server.
self.addEventListener("pushsubscriptionchange", (e) => {
  const old = e.oldSubscription;
  e.waitUntil(fetch(API + "key").then((r) => r.json()).then((j) =>
    self.registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: j.key }))
    .then((sub) => ping("subscribe", { sub: sub.toJSON(), old: old ? old.endpoint : null, rotated: true })));
});
