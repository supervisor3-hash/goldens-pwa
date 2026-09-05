const CACHE = "goldens-pwa-v2-payment";
const APP_SHELL = [
  "/",
  "/static/manifest.webmanifest",
  "/static/goldens-192.png",
  "/static/goldens-512.png",
  "/static/apple-touch-icon.png"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(APP_SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", event => {
  const req = event.request;
  if (req.method !== "GET") return;

  // Network-first for HTML/API so appointments and admin data stay fresh.
  if (req.mode === "navigate" || req.url.includes("/api/") || req.url.includes("/admin")) {
    event.respondWith(
      fetch(req)
        .then(res => {
          const copy = res.clone();
          caches.open(CACHE).then(cache => cache.put(req, copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match(req).then(r => r || caches.match("/")))
    );
    return;
  }

  // Cache-first for static files.
  event.respondWith(
    caches.match(req).then(cached =>
      cached || fetch(req).then(res => {
        const copy = res.clone();
        caches.open(CACHE).then(cache => cache.put(req, copy)).catch(() => {});
        return res;
      })
    )
  );
});
