// Offline-Huelle: App-Dateien netzwerk-zuerst (Updates kommen sofort), bei Funkloch aus dem Cache. Daten (/api/), Videos und Fotos nie cachen.
const V = "fit-2";
self.addEventListener("install", e => { self.skipWaiting(); });
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(k => Promise.all(k.filter(x => x !== V).map(x => caches.delete(x)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || u.pathname.startsWith("/api/") || u.pathname.startsWith("/video/") || u.pathname.startsWith("/bild/")) return;
  e.respondWith(fetch(e.request).then(r => { if (r.ok) { const k = r.clone(); caches.open(V).then(c => c.put(e.request, k)); } return r; }).catch(() => caches.match(e.request).then(r => r || caches.match("/"))));
});
