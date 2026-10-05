// Lagebericht (Holo-Pop-up "lage"): Welt -> Deutschland -> Region -> Maerkte -> Kennzahlen.
// Python (assistent.lagebericht) schickt einmal alle Daten und schaltet dann mit {station: "..."} weiter, waehrend Klaus spricht.
// Karte: Punktraster aus vendor/weltkarte.js (offline), Kamera gleitet zwischen den Stationen.

POPUP_GROESSE.lage = [0.72, 0.95];
POPUP_DAUER.lage = 180;
POPUP_TITEL.lage = "LAGEBERICHT";

const LAGE_STATIONEN = [["welt", "WELT"], ["de", "DEUTSCHLAND"], ["region", "REGION"], ["maerkte", "MÄRKTE"], ["zahlen", "KENNZAHLEN"]];

POPUP_ARTEN.lage = function (box) {
  box.classList.add("p-lage");
  box.innerHTML = `<div class="lage-kopf">${LAGE_STATIONEN.map(([k, n], i) => `<span data-st="${k}"><i>0${i + 1}</i>${n}</span>`).join("")}</div>
    <div class="lage-haupt"><div class="lage-buehne"><canvas></canvas><div class="lage-maerkte"></div><div class="lage-zahlen"></div>
      <div class="lage-ort"></div></div><aside class="lage-liste"></aside></div>`;
  const cv = box.querySelector("canvas"), ctx = cv.getContext("2d");
  const liste = box.querySelector(".lage-liste"), ortEl = box.querySelector(".lage-ort");
  const maerkteEl = box.querySelector(".lage-maerkte"), zahlenEl = box.querySelector(".lage-zahlen");
  let d = null, station = "", seit = performance.now(), laeuft = false;
  const ANSICHT = { welt: [-170, 190, -56, 82], de: [4.8, 16.2, 46.9, 55.4] };
  let kamera = [...ANSICHT.welt], start = [...kamera], ziel = [...kamera], fahrt = 1;
  const karteCache = { cv: document.createElement("canvas"), schluessel: "" };

  // Raster einmal in Koordinaten umrechnen
  const raster = (k) => {
    const aus = [];
    k.zeilen.forEach((z, j) => { for (let i = 0; i < z.length; i++) if (z[i] === "1") aus.push([k.lon0 + (i + 0.5) * k.schritt, k.lat0 - (j + 0.5) * k.schritt]); });
    return aus;
  };
  const weltPunkte = typeof WELTKARTE !== "undefined" ? raster(WELTKARTE.welt) : [];
  const dePunkte = typeof WELTKARTE !== "undefined" ? raster(WELTKARTE.de) : [];
  const rgb = () => getComputedStyle(document.documentElement).getPropertyValue("--rgb").trim() || "255,59,48";

  function regionAnsicht() {
    const [lat, lon] = d.mitte;
    return [lon - 0.21, lon + 0.21, lat - 0.135, lat + 0.135];
  }

  function zeigeStation(neu) {
    if (!d || neu === station) return;
    station = neu; seit = performance.now();
    box.querySelectorAll(".lage-kopf span").forEach((s) => {
      const i = LAGE_STATIONEN.findIndex(([k]) => k === s.dataset.st), j = LAGE_STATIONEN.findIndex(([k]) => k === station);
      s.className = i < j ? "fertig" : i === j ? "an" : "";
    });
    const karte = { welt: ANSICHT.welt, de: ANSICHT.de, region: regionAnsicht() }[station];
    if (karte) { start = [...kamera]; ziel = [...karte]; fahrt = 0; }
    box.classList.toggle("ohne-karte", station === "maerkte" || station === "zahlen");
    maerkteEl.classList.toggle("an", station === "maerkte");
    zahlenEl.classList.toggle("an", station === "zahlen");
    ortEl.textContent = { welt: "GLOBAL · NACHRICHTENLAGE", de: "DEUTSCHLAND", region: `REGION ${String(d.ort).toUpperCase()}`, maerkte: "MÄRKTE · HEUTE", zahlen: "KLESRO WEB · KENNZAHLEN" }[station];
    liste.innerHTML = "";
    const punkte = d[station] || [];
    if (station === "maerkte") (d.maerkte || []).forEach((m, i) => zeile(i, m.name, `${m.aenderung >= 0 ? "▲" : "▼"} ${Math.abs(m.aenderung).toFixed(2).replace(".", ",")} %`, m.aenderung >= 0 ? "plus" : "minus"));
    else if (station === "zahlen") { liste.append(el("div", "leer", d.text?.zahlen || "")); }
    else punkte.forEach((p, i) => zeile(i, p.titel, `${p.quelle === "google" ? "GN" : p.quelle === "heise" ? "HS" : "TS"}${p.alter ? " · VOR " + p.alter.toUpperCase() : ""}`, "", p.link));
    if (!liste.children.length) liste.append(el("div", "leer", "KEINE MELDUNGEN"));
  }

  function zeile(i, titel, unter, klasse, link) {
    const z = el("button", "lage-zeile " + (klasse || ""));
    z.style.animationDelay = `${i * 140}ms`;
    z.append(el("b", "", String(i + 1).padStart(2, "0")), el("span", "", titel), el("small", "", unter));
    if (link) z.onclick = () => webOeffnen(link);
    liste.append(z);
  }

  function maerkteBauen() {
    maerkteEl.innerHTML = "";
    for (const m of (d.maerkte || []).slice(0, 6)) {
      const k = el("div", "lage-kurs");
      const wert = new Intl.NumberFormat("de-DE", { maximumFractionDigits: m.preis > 1000 ? 0 : 2 }).format(m.preis);
      k.innerHTML = `<div class="lk-kopf"><b></b><span class="${m.aenderung >= 0 ? "plus" : "minus"}">${m.aenderung >= 0 ? "▲" : "▼"} ${Math.abs(m.aenderung).toFixed(2).replace(".", ",")} %</span></div>
        <div class="lk-wert">${wert} <small>${m.waehrung || ""}</small></div>`;
      k.querySelector("b").textContent = m.name;
      const svg = kurve(m.verlauf, m.aenderung >= 0);
      svg.setAttribute("preserveAspectRatio", "none");
      k.append(svg);
      maerkteEl.append(k);
    }
  }

  function zahlenBauen() {
    const z = d.zahlen || {}, w = d.wetter || {};
    const kachel = (zahl, name, neu) => `<div class="lage-zahl"><b data-ziel="${zahl}">0</b><span>${name}</span>${neu ? `<em>+${neu} NEU</em>` : ""}</div>`;
    zahlenEl.innerHTML = kachel(z.leads ?? 0, "Leads", z.neu?.leads) + kachel(z.briefe ?? 0, "Briefe", z.neu?.briefe)
      + kachel(z.zu_drucken ?? 0, "Zu drucken") + kachel(z.projekte ?? 0, "Projekte", z.neu?.projekte)
      + (w.temp !== undefined ? `<div class="lage-zahl"><b data-ziel="${w.temp}">0</b><span>°C · ${w.text || ""}</span></div>` : "");
  }

  // ------------------------------------------------------------------ Karte
  function zeichnen(jetzt) {
    if (!box.isConnected) { laeuft = false; return; }
    if (window.klausPause) { setTimeout(() => requestAnimationFrame(zeichnen), 500); return; }
    requestAnimationFrame(zeichnen);
    if (jetzt - (zeichnen.letzte || 0) < 32) return;   // ~30 Bilder/s
    zeichnen.letzte = jetzt;
    const dpr = Math.min(1.5, devicePixelRatio || 1), w = cv.clientWidth, h = cv.clientHeight;
    if (!w || !h) return;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    // Kamera gleiten lassen (Zoom wirkt logarithmisch -> gleichmaessig)
    if (fahrt < 1) {
      fahrt = Math.min(1, fahrt + 0.022);
      const e = fahrt < 0.5 ? 4 * fahrt ** 3 : 1 - (-2 * fahrt + 2) ** 3 / 2;
      const breite = Math.exp(Math.log(start[1] - start[0]) * (1 - e) + Math.log(ziel[1] - ziel[0]) * e);
      const mx = (start[0] + start[1]) / 2 * (1 - e) + (ziel[0] + ziel[1]) / 2 * e;
      const hoehe = Math.exp(Math.log(start[3] - start[2]) * (1 - e) + Math.log(ziel[3] - ziel[2]) * e);
      const my = (start[2] + start[3]) / 2 * (1 - e) + (ziel[2] + ziel[3]) / 2 * e;
      kamera = [mx - breite / 2, mx + breite / 2, my - hoehe / 2, my + hoehe / 2];
    }
    // Projektion: Laengengrade mit cos(Breite) stauchen, Seitenverhaeltnis halten
    const [x0, x1, y0, y1] = kamera, mittelBreite = ((y0 + y1) / 2) * Math.PI / 180;
    const kx = Math.cos(mittelBreite), massstab = Math.min(w / ((x1 - x0) * kx), h / (y1 - y0));
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const P = (lon, lat) => [w / 2 + (lon - cx) * kx * massstab, h / 2 - (lat - cy) * massstab];
    const farbe = rgb(), f = (a) => `rgba(${farbe},${a})`, t = jetzt / 1000;
    const pxProGrad = massstab;

    // Statische Karte (Raster, Umriss, Orte, Leads) nur neu malen, wenn sich Kamera, Groesse oder Farbe aendern
    const schluessel = `${kamera.map((v) => v.toFixed(4)).join()}|${w}x${h}|${farbe}|${dpr}`;
    if (karteCache.schluessel !== schluessel) {
      karteCache.schluessel = schluessel;
      const kc = karteCache.cv;
      if (kc.width !== cv.width || kc.height !== cv.height) { kc.width = cv.width; kc.height = cv.height; }
      const sx = kc.getContext("2d");
      sx.setTransform(dpr, 0, 0, dpr, 0, 0);
      sx.clearRect(0, 0, w, h);
      // Welt-Raster (blendet beim Hineinzoomen aus)
      const weltA = Math.max(0.12, Math.min(1, 1 - (pxProGrad - 10) / 50));
      if (weltA > 0.02) {
        const g = Math.max(1.2, Math.min(3, pxProGrad * 1.1));
        sx.fillStyle = f(0.35 * weltA);
        for (const [lon, lat] of weltPunkte) { const [x, y] = P(lon, lat); if (x > -4 && y > -4 && x < w + 4 && y < h + 4) sx.fillRect(x - g / 2, y - g / 2, g, g); }
      }
      // Deutschland: feines Raster + Umriss, sobald man naeher dran ist
      const deA = Math.max(0, Math.min(1, (pxProGrad - 8) / 30));
      if (deA > 0.02 && typeof WELTKARTE !== "undefined") {
        const g = Math.max(1.2, Math.min(4, pxProGrad * 0.11));
        sx.fillStyle = f(0.3 * deA);
        for (const [lon, lat] of dePunkte) { const [x, y] = P(lon, lat); if (x > -4 && y > -4 && x < w + 4 && y < h + 4) sx.fillRect(x - g / 2, y - g / 2, g, g); }
        sx.strokeStyle = f(0.75 * deA); sx.lineWidth = 1.2;
        for (const ring of WELTKARTE.de.umriss) {
          sx.beginPath();
          ring.forEach(([lon, lat], i) => { const [x, y] = P(lon, lat); i ? sx.lineTo(x, y) : sx.moveTo(x, y); });
          sx.closePath(); sx.stroke();
        }
      }
      // Region: Orte, Entfernungsringe, Leads
      const regA = Math.max(0, Math.min(1, (pxProGrad - 300) / 600));
      if (regA > 0.02) {
        const [mx, my] = P(d.mitte[1], d.mitte[0]), kmPx = pxProGrad / 111;
        sx.setLineDash([3, 5]);
        for (const km of [5, 10, 15]) { sx.strokeStyle = f(0.25 * regA); sx.beginPath(); sx.arc(mx, my, km * kmPx * 1, 0, Math.PI * 2); sx.stroke(); }
        sx.setLineDash([]);
        for (const l of d.leads || []) {
          const [x, y] = P(l.lon, l.lat);
          sx.fillStyle = `rgba(60,245,155,${0.85 * regA})`; sx.beginPath(); sx.arc(x, y, 3, 0, Math.PI * 2); sx.fill();
        }
        sx.font = "500 12px 'Barlow SC', sans-serif"; sx.textAlign = "center"; sx.lineJoin = "round";
        for (const [name, lat, lon] of KARTEN_ORTE) {
          const [x, y] = P(lon, lat);
          if (x < 0 || y < 0 || x > w || y > h) continue;
          sx.fillStyle = `rgba(255,235,230,${0.6 * regA})`; sx.fillRect(x - 2, y - 2, 4, 4);
          sx.lineWidth = 3.5; sx.strokeStyle = `rgba(0,0,0,${0.85 * regA})`; sx.strokeText(name.toUpperCase(), x, y - 9);
          sx.fillStyle = `rgba(240,225,222,${0.8 * regA})`; sx.fillText(name.toUpperCase(), x, y - 9);
        }
      }
    }
    ctx.drawImage(karteCache.cv, 0, 0, w, h);
    // Nachrichtenpunkte der aktuellen Station: tauchen nacheinander auf, pulsieren, Nummer daneben
    const punkte = d[station] || [];
    if (Array.isArray(punkte) && station !== "maerkte") {
      ctx.font = "600 11px 'Chakra Petch', sans-serif"; ctx.textAlign = "left";
      punkte.forEach((p, i) => {
        const alter = (jetzt - seit) / 1000 - 1.2 - i * 0.14;
        if (alter < 0 || p.lat === undefined) return;
        const [x, y] = P(p.lon + ((i * 37) % 7 - 3) * (station === "welt" ? 0.6 : 0.02), p.lat + ((i * 53) % 5 - 2) * (station === "welt" ? 0.5 : 0.015));
        const puls = (alter * 0.7 + i * 0.13) % 1, pop = Math.min(1, alter * 4);
        const c = station === "region" ? "255,255,255" : station === "de" ? "255,194,74" : farbe;
        ctx.strokeStyle = `rgba(${c},${(1 - puls) * 0.8})`; ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.arc(x, y, 3 + puls * 16, 0, Math.PI * 2); ctx.stroke();
        ctx.fillStyle = `rgba(${c},.95)`; ctx.beginPath(); ctx.arc(x, y, 3.2 * pop + (1 - pop) * 7, 0, Math.PI * 2); ctx.fill();
        ctx.lineWidth = 3; ctx.strokeStyle = "rgba(0,0,0,.85)"; ctx.strokeText(String(i + 1).padStart(2, "0"), x + 7, y - 7);
        ctx.fillStyle = "#fff"; ctx.fillText(String(i + 1).padStart(2, "0"), x + 7, y - 7);
      });
    }
    // Abtastlinie
    const sy = ((t * 0.25) % 1) * h;
    const band = ctx.createLinearGradient(0, sy - 40, 0, sy);
    band.addColorStop(0, f(0)); band.addColorStop(1, f(0.12));
    ctx.fillStyle = band; ctx.fillRect(0, sy - 40, w, 40);
    // Zahlen hochzaehlen
    if (station === "zahlen") {
      const k = Math.min(1, (jetzt - seit) / 1400), e = 1 - (1 - k) ** 3;
      zahlenEl.querySelectorAll("b[data-ziel]").forEach((b) => { b.textContent = Math.round(Number(b.dataset.ziel) * e); });
    }
  }

  return {
    update(neu) {
      if (neu.welt) { d = neu; maerkteBauen(); zahlenBauen(); station = ""; }
      if (!d) return;
      zeigeStation(neu.station || station || "welt");
      if (!laeuft) { laeuft = true; requestAnimationFrame(zeichnen); }
    },
  };
};
