// Offline-Huelle: App-Dateien netzwerk-zuerst (Updates kommen sofort), bei Funkloch aus dem Cache. Daten (/api/), Videos und Fotos nie cachen.
const V = "fit-3";
self.addEventListener("install", e => { self.skipWaiting(); });
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(k => Promise.all(k.filter(x => x !== V).map(x => caches.delete(x)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || u.pathname.startsWith("/api/") || u.pathname.startsWith("/video/") || u.pathname.startsWith("/bild/")) return;
  e.respondWith(fetch(e.request).then(r => { if (r.ok) { const k = r.clone(); caches.open(V).then(c => c.put(e.request, k)); } return r; }).catch(() => caches.match(e.request).then(r => r || caches.match("/"))));
});

// Push: Nachricht anzeigen (iOS verlangt, dass jede Push-Nachricht sichtbar ist) und beim Antippen die App oeffnen
self.addEventListener("push", e => {
  let d = {}; try { d = e.data ? e.data.json() : {}; } catch (x) { d = {text: e.data ? e.data.text() : ""}; }
  e.waitUntil(self.registration.showNotification(d.titel || "Klesro Fit", {body: d.text || "", icon: "/icon-192.png", badge: "/icon-192.png", data: {link: d.link || "/"}}));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const link = (e.notification.data && e.notification.data.link) || "/";
  e.waitUntil(self.clients.matchAll({type: "window", includeUncontrolled: true}).then(l => { for (const c of l) if ("focus" in c) return c.focus(); return self.clients.openWindow(link); }));
});
