/* Schwarzer Bildschirm? Startet die App nicht innerhalb weniger Sekunden (z. B. halb aktualisierte Dateien auf dem iPhone), erscheint ein Knopf,
   der Zwischenspeicher und Service-Worker loescht und neu laedt. Klassisches Skript (kein Modul), damit es auch laeuft, wenn app.js nicht laedt. */
(function () {
  function zeigen() {
    if (window.__fitOk || document.getElementById("rettung")) return;
    var d = document.createElement("div");
    d.id = "rettung";
    d.setAttribute("style", "position:fixed;inset:0;z-index:99999;background:#09090a;color:#f4f4f1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;padding:24px;text-align:center;font:16px/1.4 -apple-system,sans-serif");
    var t = document.createElement("div"); t.textContent = "Die App hat nicht richtig gestartet.";
    var b = document.createElement("button"); b.textContent = "Neu laden und reparieren";
    b.setAttribute("style", "background:#d4ff3a;color:#09090a;border:0;padding:16px 22px;font:700 16px sans-serif;border-radius:10px");
    b.onclick = function () {
      b.disabled = true; b.textContent = "Moment …";
      var fertig = function () { location.reload(); };
      Promise.all([
        navigator.serviceWorker ? navigator.serviceWorker.getRegistrations().then(function (r) { return Promise.all(r.map(function (x) { return x.unregister(); })); }) : null,
        window.caches ? caches.keys().then(function (k) { return Promise.all(k.map(function (x) { return caches.delete(x); })); }) : null
      ]).then(fertig, fertig);
    };
    d.appendChild(t); d.appendChild(b); document.body.appendChild(d);
  }
  setTimeout(zeigen, 6000);
  window.addEventListener("error", function () { setTimeout(zeigen, 1500); }, true);
})();
