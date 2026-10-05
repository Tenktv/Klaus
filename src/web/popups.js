// Holo-Pop-ups: Fenster, die rund ums Auge aufgehen, waehrend Klaus arbeitet - mit Leuchtlinie zum Kern.
// Python schickt Befehle als JSON (assistent.holo): {aktion: "oeffne"|"update"|"zu"|"log", id, art, titel, daten, text, dauer}
// Arten: log (Live-Log), pipeline (Phasen-Checkliste), karte (Lead-Karte), entwurf (Brief tippt sich live).

const holoPopups = {};   // id -> { item, m, art, ansicht, linie, zuletzt, dauer, angefasst }
const POPUP_GROESSE = { log: [0.27, 0.3], pipeline: [0.27, 0.38], karte: [0.33, 0.46], entwurf: [0.3, 0.44] };
const POPUP_DAUER = { log: 25, pipeline: 90, karte: 120, entwurf: 120 };  // Sekunden ohne Neuigkeit -> schliesst sich
const POPUP_TITEL = { log: "LIVE LOG", pipeline: "PIPELINE", karte: "LEAD MAP", entwurf: "BRIEF-ENTWURF" };
let popupSchleifeLaeuft = false;
let fokusAn = false;

// Fokus-Modus: Widgets treten zurueck, solange Pop-ups offen sind (Browser-Ansichten mit ausblenden)
function fokusPruefen() {
  const an = Object.keys(holoPopups).length > 0;
  if (an === fokusAn) return;
  fokusAn = an;
  document.body.classList.toggle("fokus", an);
  webVerdecken(an);
}
addEventListener("keydown", (e) => { if (e.key === "Escape") Object.keys(holoPopups).forEach(popupZu); });

function holoBefehl(json) {
  let b;
  try { b = typeof json === "string" ? JSON.parse(json) : json; } catch { return; }
  if (b.aktion === "zu") return popupZu(b.id);
  if (b.aktion === "alle_zu") return Object.keys(holoPopups).forEach(popupZu);
  if (b.aktion === "log") { b = { id: "log", art: "log", daten: { zeile: b.text } }; }
  const p = holoPopups[b.id] || (b.art ? popupOeffnen(b) : null);  // Update fuer ein geschlossenes Fenster ohne Art: ignorieren
  if (!p) return;
  if (b.titel && p.titelEl.dataset.text !== b.titel) { p.titelEl.dataset.text = b.titel; holoTitel(p.titelEl, b.titel); }
  if (b.dauer) p.dauer = b.dauer;
  if (b.daten) p.ansicht.update(b.daten);
  p.zuletzt = Date.now();
}

// Wo sitzt das Auge? (Mitte der Klaus-Buehne in Koordinaten der Arbeitsflaeche) + Radius fuer den Linienstart
function holoKern(flaeche) {
  const F = flaeche.getBoundingClientRect(), auge = document.querySelector(".klaus .auge-platz");
  if (!auge || !auge.isConnected) return { x: F.width / 2, y: F.height / 2, r: 60 };
  const b = auge.getBoundingClientRect();
  return { x: b.left + b.width / 2 - F.left, y: b.top + b.height / 2 - F.top, r: b.width * 0.445 };
}

// Freier Platz rund ums Auge: links/rechts mit deutlichem Abstand zum Gehaeuse (lange Leuchtlinien),
// erst oben, dann unten, dann unter dem Auge; sonst versetzt gestapelt
function popupPlatz(art, flaeche) {
  const [w, h] = POPUP_GROESSE[art] || [0.22, 0.3];
  const F = flaeche.getBoundingClientRect(), k = holoKern(flaeche);
  const kx = k.x / F.width, kr = k.r / F.width, luecke = 0.055;
  const offen = Object.values(holoPopups).map((p) => p.m);
  const links = Math.max(0.005, kx - kr - luecke - w), rechts = Math.min(0.995 - w, kx + kr + luecke);
  const oben = 0.02, unten = Math.max(oben, 0.98 - h);
  const kandidaten = [[links, oben], [rechts, oben], [links, unten], [rechts, unten], [(1 - w) / 2, unten]]
    .map(([x, y]) => ({ x, y, w, h }));
  const frei = kandidaten.find((r) => !offen.some((o) => holoUeberlappt(r, o)));
  if (frei) return frei;
  const n = offen.length;
  return { x: Math.min(1 - w, 0.3 + n * 0.025), y: Math.min(1 - h, 0.12 + n * 0.035), w, h };
}

function popupOeffnen(b) {
  const art = b.art || "log", bauer = POPUP_ARTEN[art];
  if (!bauer) return null;
  const flaeche = document.getElementById("raster");
  const m = popupPlatz(art, flaeche);
  const item = el("div", "fenster popup popup-" + art);
  holoLage(item, m);
  const w = el("div", "w"), innen = el("div", "w-innen"), kopf = el("div", "w-kopf");
  const titel = el("div", "w-titel", b.titel || POPUP_TITEL[art]);
  titel.dataset.text = titel.textContent;
  const weg = el("button", "w-knopf weg", "✕");
  weg.title = "Schließen";
  kopf.append(titel, el("span", "w-id", `klesro://${art}`), el("div", "w-extra"), weg);
  const inhalt = el("div", "w-inhalt p-inhalt");
  innen.append(kopf, inhalt);
  w.append(innen);
  const ecke = el("div", "fenster-ecke");
  item.append(w, ecke);
  flaeche.append(item);
  holoVorne(item);

  const p = { item, m, art, titelEl: titel, zuletzt: Date.now(), dauer: POPUP_DAUER[art] || 60, angefasst: false };
  p.ansicht = bauer(inhalt, p);
  p.linie = popupLinie(flaeche);
  holoFrei(item, m, kopf, ecke, flaeche, {
    minB: 220, minH: 120,
    andere: () => flaeche.querySelectorAll(".fenster"),
    beimAnfassen: () => { p.angefasst = true; },  // angefasst = bleibt offen, bis du es schliesst
    beimStart: () => webVerdecken(true),
    beimEnde: () => setTimeout(() => webVerdecken(false), 60),
  });
  weg.onclick = () => popupZu(b.id);
  holoBoot(item);
  holoPopups[b.id] = p;
  fokusPruefen();
  if (!popupSchleifeLaeuft) { popupSchleifeLaeuft = true; requestAnimationFrame(popupSchleife); }
  return p;
}

async function popupZu(id) {
  const p = holoPopups[id];
  if (!p) return;
  delete holoPopups[id];
  fokusPruefen();
  p.linie.classList.add("weg");
  await holoAus(p.item);
  p.item.remove();
  p.linie.remove();
}

// Leuchtlinie: Grundlinie + darauf laufende Datenpunkte + Knoten am Fenster
function popupLinie(flaeche) {
  let svg = flaeche.querySelector("#holo-linien");
  if (!svg) {
    svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.id = "holo-linien";
    flaeche.append(svg);
  }
  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  g.setAttribute("class", "holo-linie");
  g.innerHTML = `<path class="hl-grund" pathLength="1"/><path class="hl-kern" pathLength="1"/><path class="hl-fluss"/>`
    + `<circle class="hl-knoten" r="4"/><circle class="hl-knoten-i" r="1.6"/><circle class="hl-start" r="4"/><circle class="hl-start-i" r="1.6"/>`;
  svg.append(g);
  return g;
}

// Linien nachfuehren (Fenster koennen gezogen werden) + abgelaufene Pop-ups schliessen. Laeuft nur, solange welche offen sind.
let popupZaehler = 0;
function popupSchleife() {
  const offen = Object.entries(holoPopups);
  if (!offen.length) { popupSchleifeLaeuft = false; return; }
  if (window.klausPause) { setTimeout(() => requestAnimationFrame(popupSchleife), 500); return; }
  const flaeche = document.getElementById("raster"), F = flaeche.getBoundingClientRect(), k = holoKern(flaeche);
  for (const [id, p] of offen) {
    const r = p.item.getBoundingClientRect();
    const l = r.left - F.left + 5, t = r.top - F.top + 5, rr = r.right - F.left - 5, u = r.bottom - F.top - 5;
    // Anker am Fensterrand, der zum Auge zeigt; seitlich mit Knick (erst radial raus, dann waagerecht hinein)
    let ax, ay, knick = null;
    if (rr < k.x - k.r * 0.6 || l > k.x + k.r * 0.6) {
      const rechtsVomAuge = l > k.x;
      ax = rechtsVomAuge ? l : rr;
      ay = Math.max(t + 30, Math.min(u - 30, k.y + ((t + u) / 2 - k.y) * 0.5));
      knick = { x: ax + (rechtsVomAuge ? -46 : 46), y: ay };
    } else {
      ax = Math.max(l + 20, Math.min(rr - 20, k.x));
      ay = t > k.y ? t : u;
    }
    const ziel = knick || { x: ax, y: ay };
    const winkel = Math.atan2(ziel.y - k.y, ziel.x - k.x), sx = k.x + Math.cos(winkel) * k.r, sy = k.y + Math.sin(winkel) * k.r;
    const d = `M${sx.toFixed(1)} ${sy.toFixed(1)}` + (knick ? `L${knick.x.toFixed(1)} ${knick.y.toFixed(1)}` : "") + `L${ax.toFixed(1)} ${ay.toFixed(1)}`;
    if (p.linie._d !== d) {
      p.linie._d = d;
      p.linie.querySelectorAll("path").forEach((pfad) => pfad.setAttribute("d", d));
      const [kn, kni, st, sti] = p.linie.querySelectorAll("circle");
      for (const c of [kn, kni]) { c.setAttribute("cx", ax); c.setAttribute("cy", ay); }
      for (const c of [st, sti]) { c.setAttribute("cx", sx); c.setAttribute("cy", sy); }
    }
    if (++popupZaehler % 30 === 0 && !p.angefasst && Date.now() - p.zuletzt > p.dauer * 1000) popupZu(id);
  }
  requestAnimationFrame(popupSchleife);
}

// ------------------------------------------------------------------ Fenster-Arten
function holoTippen(ziel, text, proSchritt = 2, ms = 16, fertig) {
  clearInterval(ziel._tipp);
  if (HOLO_RUHIG) { ziel.textContent = text; if (fertig) fertig(); return; }
  let i = 0;
  ziel._tipp = setInterval(() => {
    i = Math.min(text.length, i + proSchritt);
    ziel.textContent = text.slice(0, i);
    if (i >= text.length) { clearInterval(ziel._tipp); if (fertig) fertig(); }
  }, ms);
}

const POPUP_ARTEN = {
  // Terminal-Stream mit Zeitstempel, alles mit klesro://-Prefix
  log(box) {
    const liste = el("div", "p-log");
    box.append(liste);
    return {
      update(d) {
        if (!d.zeile) return;
        const z = el("div", "p-zeile");
        const text = d.zeile.replace(/^klesro:\/\//, ""), leer = text.indexOf(" ");
        const pfad = leer < 0 ? text : text.slice(0, leer), rest = leer < 0 ? "" : text.slice(leer);
        const stufe = /fehler|error|fault|abgebrochen/i.test(rest) ? " schlecht" : /wartet|freigabe|auth/i.test(rest) ? " warten"
          : /\bok\b|fertig|erstellt|gefunden|keine website|complete/i.test(rest) ? " gut" : "";
        z.append(el("span", "p-zeit", new Date().toLocaleTimeString("de-DE")), el("span", "p-pfad", `klesro://${pfad}`), el("span", "p-text" + stufe));
        liste.append(z);
        holoTippen(z.lastChild, rest, 2, 12, () => { box.scrollTop = box.scrollHeight; });
        while (liste.children.length > 80) liste.firstChild.remove();
        box.scrollTop = box.scrollHeight;
      },
    };
  },

  // Phasen-Checkliste: PENDING -> RUNNING (Spinner) -> COMPLETE
  pipeline(box) {
    const liste = el("div", "p-pipe"), fuss = el("div", "p-pipe-fuss");
    fuss.innerHTML = '<div class="p-balken"><i></i></div><div class="p-pipe-zahlen"><span></span><span></span></div>';
    box.append(liste, fuss);
    const zeilen = [];
    const TEXT = { pending: "PENDING", running: "RUNNING", complete: "COMPLETE", fehler: "FAULT", warten: "AWAITING AUTH", uebersprungen: "SKIPPED" };
    const fortschritt = (schritte) => {
      const n = schritte.length || 1, fertig = schritte.filter((x) => ["complete", "uebersprungen"].includes(x.status)).length;
      const pct = Math.round(((fertig + (schritte.some((x) => x.status === "running") ? 0.5 : 0)) / n) * 100);
      fuss.querySelector("i").style.width = `${pct}%`;
      const [links, rechts] = fuss.querySelectorAll("span");
      links.textContent = fertig === n ? "ABGESCHLOSSEN" : `${fertig} / ${n} SCHRITTE`;
      rechts.textContent = `${pct} %`;
    };
    return {
      update(d) {
        if (d.schritte) fortschritt(d.schritte);
        (d.schritte || []).forEach((s, i) => {
          let z = zeilen[i];
          if (!z) {
            z = el("div", "p-schritt");
            z.style.animationDelay = `${i * 90}ms`;
            const name = el("span", "p-name");
            name.append(el("span", "p-name-text"), el("small", "p-info"));
            z.append(el("i", "p-punkt"), name, el("b", "p-status"));
            liste.append(z);
            zeilen[i] = z;
          }
          z.querySelector(".p-name-text").textContent = s.name;
          z.querySelector(".p-info").textContent = s.info || "";
          const status = s.status || "pending";
          if (z.dataset.status !== status) {
            z.dataset.status = status;
            z.querySelector(".p-status").textContent = TEXT[status] || status.toUpperCase();
            z.classList.remove("wechsel"); void z.offsetWidth; z.classList.add("wechsel");
          }
        });
      },
    };
  },

  // Brief tippt sich live
  entwurf(box) {
    box.classList.add("p-entwurf");
    const kopf = el("dl", "p-brief-kopf"), text = el("div", "p-brief"), fuss = el("div", "p-brief-fuss");
    kopf.innerHTML = '<dt>BETREFF</dt><dd class="p-betreff"></dd>';
    fuss.innerHTML = "<span>DIN 5008 · A4</span><span></span>";
    box.append(kopf, text, fuss);
    const woerter = fuss.lastChild;
    return {
      update(d) {
        kopf.querySelector(".p-betreff").textContent = d.betreff || "–";
        text.classList.add("tippt");
        holoTippen(text, d.text || "", 3, 16, () => text.classList.remove("tippt"));
        const folgen = setInterval(() => {
          text.scrollTop = text.scrollHeight;
          woerter.textContent = `${text.textContent.split(/\s+/).filter(Boolean).length} WÖRTER`;
          if (!text.classList.contains("tippt") || !box.isConnected) clearInterval(folgen);
        }, 120);
      },
    };
  },

  // Dunkle Karte der Region mit pulsierenden Markern; rechts die Trefferliste
  karte(box) {
    box.classList.add("p-karte");
    const cv = el("canvas", "p-karte-bild"), liste = el("div", "p-karte-liste"), info = el("div", "p-karte-info");
    box.append(cv, liste, info);
    const ctx = cv.getContext("2d");
    const d = { mitte: [48.7035, 9.6524], radius_km: 12 };
    const punkte = [];
    let rgb = "0,229,255", rgbZeit = 0;
    const proj = (lat, lon, w, h) => {
      const pxProKm = Math.min(w, h) / 2 / (d.radius_km * 1.12);
      const dx = (lon - d.mitte[1]) * 111.32 * Math.cos((d.mitte[0] * Math.PI) / 180), dy = (lat - d.mitte[0]) * 110.57;
      return [w / 2 + dx * pxProKm, h / 2 - dy * pxProKm, pxProKm];
    };
    const zeichne = (jetzt) => {
      if (!box.isConnected) return;  // Fenster zu -> Schleife endet
      if (window.klausPause) { setTimeout(() => requestAnimationFrame(zeichne), 500); return; }
      if (jetzt - rgbZeit > 2000) { rgb = getComputedStyle(document.documentElement).getPropertyValue("--rgb").trim() || rgb; rgbZeit = jetzt; }
      const dpr = devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
      if (w && h) {
        if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, w, h);
        const f = (a) => `rgba(${rgb},${a})`, t = jetzt / 1000;
        // Raster
        ctx.strokeStyle = f(0.07); ctx.lineWidth = 1;
        for (let x = (w / 2) % 24; x < w; x += 24) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke(); }
        for (let y = (h / 2) % 24; y < h; y += 24) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }
        const [mx, my, pxKm] = proj(d.mitte[0], d.mitte[1], w, h);
        // Entfernungsringe
        ctx.font = "10px 'JetBrains Mono', Consolas, monospace"; ctx.textAlign = "left"; ctx.textBaseline = "middle";
        for (const km of [5, 10, d.radius_km].filter((v, i, a) => a.indexOf(v) === i && v <= d.radius_km)) {
          ctx.strokeStyle = f(km === d.radius_km ? 0.35 : 0.15);
          ctx.setLineDash(km === d.radius_km ? [] : [3, 5]);
          ctx.beginPath(); ctx.arc(mx, my, km * pxKm, 0, Math.PI * 2); ctx.stroke();
          ctx.fillStyle = f(0.55); ctx.fillText(`${km} KM`, mx + 4, my - km * pxKm - 7);
        }
        ctx.setLineDash([]);
        // Radar-Sweep
        const a = (t * 0.9) % (Math.PI * 2);
        if (ctx.createConicGradient) {
          const kegel = ctx.createConicGradient(a - 0.6, mx, my);
          kegel.addColorStop(0, f(0)); kegel.addColorStop(0.095, f(0.16)); kegel.addColorStop(0.1, f(0));
          ctx.fillStyle = kegel; ctx.beginPath(); ctx.arc(mx, my, d.radius_km * pxKm, 0, Math.PI * 2); ctx.fill();
        }
        // Orte (nur Punkte; die Namen kommen nach den Markern, damit sie lesbar bleiben)
        const orte = [];
        for (const [name, lat, lon] of KARTEN_ORTE) {
          const [x, y] = proj(lat, lon, w, h);
          if (x < 0 || y < 0 || x > w || y > h) continue;
          ctx.fillStyle = "rgba(255,235,230,.45)"; ctx.fillRect(x - 1.5, y - 1.5, 3, 3);
          orte.push([name, x, y]);
        }
        // Fadenkreuz in der Mitte
        ctx.strokeStyle = f(0.6);
        ctx.beginPath(); ctx.moveTo(mx - 8, my); ctx.lineTo(mx + 8, my); ctx.moveTo(mx, my - 8); ctx.lineTo(mx, my + 8); ctx.stroke();
        // Treffer: poppen nacheinander auf und pulsieren
        for (const p of punkte) {
          if (jetzt < p.erscheint || !p.lat) continue;
          const [x, y] = proj(p.lat, p.lon, w, h), alter = (jetzt - p.erscheint) / 1000;
          const pop = Math.min(1, alter * 4), puls = (alter * 0.8) % 1;
          if (p.status === "website") {  // hat doch eine Website -> verworfen
            ctx.strokeStyle = "rgba(150,150,160,.55)"; ctx.lineWidth = 1.2;
            ctx.beginPath(); ctx.moveTo(x - 4, y - 4); ctx.lineTo(x + 4, y + 4); ctx.moveTo(x + 4, y - 4); ctx.lineTo(x - 4, y + 4); ctx.stroke();
            continue;
          }
          const gruen = p.status === "ohne";
          const farbe = gruen ? (a) => `rgba(61,255,168,${a})` : f;
          ctx.strokeStyle = farbe((1 - puls) * 0.8); ctx.lineWidth = 1.2;
          ctx.beginPath(); ctx.arc(x, y, 3 + puls * 14, 0, Math.PI * 2); ctx.stroke();
          ctx.fillStyle = farbe(0.95);
          ctx.beginPath(); ctx.arc(x, y, (gruen ? 3.6 : 3) * (0.4 + pop * 0.6) + (1 - pop) * 6, 0, Math.PI * 2); ctx.fill();
        }
        ctx.font = "500 11px 'Barlow SC', 'Segoe UI', sans-serif"; ctx.textAlign = "center"; ctx.lineJoin = "round";
        ctx.strokeStyle = "rgba(4,2,2,.92)"; ctx.lineWidth = 3.5;
        for (const [name, x, y] of orte) {
          const ty = y < 14 ? y + 14 : y - 8, text = name.toUpperCase();
          ctx.strokeText(text, x, ty);
          ctx.fillStyle = "rgba(240,225,222,.72)"; ctx.fillText(text, x, ty);
        }
      }
      requestAnimationFrame(zeichne);
    };
    requestAnimationFrame(zeichne);
    const infoZeigen = () => {
      const ohne = punkte.filter((p) => p.status === "ohne").length, weg = punkte.filter((p) => p.status === "website").length;
      info.textContent = `${punkte.length} TREFFER · ${ohne} OHNE WEBSITE · ${weg} VERWORFEN · RADIUS ${d.radius_km} KM`;
    };
    return {
      update(neu) {
        if (neu.mitte) d.mitte = neu.mitte;
        if (neu.radius_km) d.radius_km = neu.radius_km;
        let n = 0;
        for (const l of neu.leads || []) {
          if (punkte.some((p) => p.name === l.name)) continue;
          const verz = n++ * 170;
          punkte.push({ ...l, status: l.status || "neu", erscheint: performance.now() + verz });
          setTimeout(() => {
            const z = el("div", "p-treffer");
            z.dataset.name = l.name; z.dataset.status = l.status || "neu";
            z.append(el("b", "", l.name), el("span", "", l.adresse || ""));
            liste.append(z);
            liste.scrollTop = liste.scrollHeight;
          }, verz);
        }
        for (const [name, st] of Object.entries(neu.status || {})) {
          const p = punkte.find((x) => x.name === name);
          if (p) p.status = st;
          const z = [...liste.children].find((x) => x.dataset.name === name);
          if (z) { z.dataset.status = st; z.scrollIntoView({ block: "nearest" }); }
        }
        setTimeout(infoZeigen, n * 170);
        infoZeigen();
      },
    };
  },
};

// Orte rund um Goeppingen fuer die Lead-Karte (Orientierung, ohne Kartenkacheln aus dem Netz)
const KARTEN_ORTE = [
  ["Göppingen", 48.7035, 9.6524], ["Eislingen", 48.695, 9.7043], ["Uhingen", 48.705, 9.59], ["Salach", 48.6917, 9.735],
  ["Süßen", 48.6797, 9.7586], ["Donzdorf", 48.6856, 9.8108], ["Geislingen", 48.6244, 9.8306], ["Ebersbach", 48.7156, 9.5236],
  ["Bad Boll", 48.6436, 9.6122], ["Heiningen", 48.6639, 9.6497], ["Deggingen", 48.5978, 9.7186], ["Börtlingen", 48.7472, 9.6328],
  ["Schorndorf", 48.8053, 9.5275], ["Schwäb. Gmünd", 48.7997, 9.7983], ["Kirchheim", 48.6481, 9.4511], ["Wäschenbeuren", 48.7594, 9.6886],
];

// Debug: Fenster-Demo mit Beispieldaten (Strg+Alt+D -> "▶ FENSTER")
function popupDemo() {
  const log = (t, ms) => setTimeout(() => holoBefehl({ aktion: "log", text: t }), ms);
  const schritte = (stand) => ["Betriebe finden (OSM)", "Websites prüfen", "In Lead-Liste speichern", "Briefe erstellen", "Drucken"]
    .map((name, i) => ({ name, status: stand[i] || "pending" }));
  const pipe = (stand, ms) => setTimeout(() => holoBefehl({ aktion: "update", id: "pipeline", art: "pipeline", titel: "LEAD-PIPELINE · DEMO", daten: { schritte: schritte(stand) } }), ms);
  const demo = [["Demo Schreinerei", 48.712, 9.63], ["Demo Malerbetrieb", 48.699, 9.69], ["Demo Elektro", 48.69, 9.74],
                ["Demo Bäckerei", 48.73, 9.66], ["Demo Fliesenleger", 48.67, 9.61], ["Demo Friseur", 48.705, 9.585]]
    .map(([name, lat, lon]) => ({ name, lat, lon, adresse: "DEMO-DATEN" }));
  log("intent/leads_suchen branchen=handwerk ort=Göppingen", 0);
  pipe(["running"], 300);
  log("osm/overpass query radius=12km", 700);
  setTimeout(() => holoBefehl({ aktion: "oeffne", id: "karte", art: "karte", titel: "LEAD MAP · GÖPPINGEN · DEMO", daten: { mitte: [48.7035, 9.6524], radius_km: 12, leads: demo } }), 1400);
  log("osm/treffer 6 betriebe ohne website-tag", 1600);
  pipe(["complete", "running"], 2600);
  ["website", "ohne", "ohne", "website", "ohne", "ohne"].forEach((st, i) => setTimeout(() => {
    holoBefehl({ aktion: "update", id: "karte", daten: { status: { [demo[i].name]: st } } });
    holoBefehl({ aktion: "log", text: `web/check ${demo[i].name} -> ${st === "website" ? "hat website · verworfen" : "keine website"}` });
  }, 3000 + i * 700));
  pipe(["complete", "complete", "running"], 7400);
  pipe(["complete", "complete", "complete", "running"], 8200);
  setTimeout(() => holoBefehl({ aktion: "oeffne", id: "entwurf", art: "entwurf", daten: {
    betreff: "DEMO · Ein Website-Entwurf für Ihren Betrieb",
    text: "Sehr geehrte Damen und Herren,\n\nbeim Blick auf Betriebe in Göppingen ist mir aufgefallen, dass Sie noch keine eigene Website haben. "
      + "Ich habe mir erlaubt, einen unverbindlichen Entwurf zu gestalten – den QR-Code unten einfach mit dem Handy scannen.\n\n"
      + "Wenn er Ihnen gefällt, freue ich mich über einen kurzen Anruf." } }), 8600);
  pipe(["complete", "complete", "complete", "complete", "warten"], 12500);
  log("auth/drucken wartet auf freigabe", 12600);
}
