// Offline-Huelle: App-Dateien aus dem Cache, Daten (/api/) immer frisch.
const V = "kalorien-2";
const DATEIEN = ["/", "/app.js", "/style.css", "/vendor/zxing.min.js", "/icon-192.png", "/manifest.webmanifest"];
self.addEventListener("install", e => e.waitUntil(caches.open(V).then(c => c.addAll(DATEIEN)).then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(k => Promise.all(k.filter(x => x !== V).map(x => caches.delete(x)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || u.pathname.startsWith("/api/")) return;
  e.respondWith(fetch(e.request).then(r => { const k = r.clone(); caches.open(V).then(c => c.put(e.request, k)); return r; }).catch(() => caches.match(e.request)));
});
