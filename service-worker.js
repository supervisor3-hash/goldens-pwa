const CACHE = "goldens-pwa-v4-no-old-html";

self.addEventListener("install", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k)))));
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const req = event.request;
  if (req.method !== "GET") return;

  // Nunca usar una pantalla HTML vieja guardada.
  if (req.mode === "navigate" || req.url.includes("/api/") || req.url.includes("/admin")) {
    event.respondWith(fetch(req, {cache:"no-store"}));
    return;
  }

  // Archivos estáticos: red primero y cache solo como respaldo.
  event.respondWith(
    fetch(req)
      .then(res => {
        const copy = res.clone();
        caches.open(CACHE).then(cache => cache.put(req, copy)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(req))
  );
});
