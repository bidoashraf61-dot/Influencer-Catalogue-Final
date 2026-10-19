/* HELVi Connect service worker (item 168): offline fallback, push alerts, taps.

   Pages always come from the network (client data is private and changes all day);
   the cache only holds the app shell pieces that carry a ?v= stamp, the icons and
   the offline page. Nothing under /admin/ is ever cached. */
const VERSION = "hca-2";
const SHELL = ["/offline.html", "/assets/app/icon-192.png", "/assets/app/badge-96.png",
  "/assets/brand/helvy-connect/helvy-connect-light-320.webp",
  "/assets/ref/68efdbc172d0ac625d40c65f_BebasNeue-Regular.woff2"];
const API = "/admin/api/push/";

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
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
  // Stamped shell files never change under the same URL: cache first.
  const stamped = url.search.includes("v=") && /\/assets\/(css|js|ref|brand|app|icons)\//.test(url.pathname);
  if (stamped || url.pathname.startsWith("/assets/app/") || SHELL.includes(url.pathname)) {
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((res) => {
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
