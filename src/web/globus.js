// Globus: 3D-Punktgitter-Erde (aus vendor/weltkarte.js), dreht sich zu einem Ort und spielt je nach Art der Meldung
// eine Animation ab: krieg (Explosionswellen), frieden (helle Ringe), geld (Muenzen), dieb (Alarm), katastrophe (Beben),
// politik (Puls), tech (Funken), gesundheit (Kreuz), sport, sonst (Ping).
// Nutzung: const g = new KlausGlobus(canvas); g.zeige({lat, lon, art, titel, ort}); g.ereignisse([...]) fuer mehrere Punkte.

const GLOBUS_ARTEN = {
  krieg:       { farbe: "255,60,50",   symbol: "✕", name: "KONFLIKT" },
  frieden:     { farbe: "140,255,200", symbol: "☮", name: "FRIEDEN" },
  geld:        { farbe: "255,200,60",  symbol: "€", name: "WIRTSCHAFT" },
  dieb:        { farbe: "255,150,40",  symbol: "!", name: "KRIMINALITÄT" },
  katastrophe: { farbe: "255,120,40",  symbol: "≋", name: "KATASTROPHE" },
  politik:     { farbe: "120,170,255", symbol: "◆", name: "POLITIK" },
  tech:        { farbe: "80,230,255",  symbol: "⌁", name: "TECHNIK" },
  gesundheit:  { farbe: "120,255,140", symbol: "+", name: "GESUNDHEIT" },
  sport:       { farbe: "200,255,90",  symbol: "◎", name: "SPORT" },
  sonst:       { farbe: "255,255,255", symbol: "•", name: "MELDUNG" },
};

// Art einer Schlagzeile ohne KI erkennen
function globusArt(titel) {
  const t = (titel || "").toLowerCase();
  // kurze Woerter nur als ganzes Wort (sonst trifft "ki" auch "Kiew")
  const passt = (muster) => muster.some((m) => (m.length <= 3 ? new RegExp(`(^|[^a-zäöüß])${m.trim()}([^a-zäöüß]|$)`).test(t) : t.includes(m)));
  // Frieden zuerst: "Waffenruhe" enthaelt "waffen"
  if (passt(["frieden", "waffenruhe", "waffenstillstand", "abkommen", "einigung", "versöhn", "friedens"])) return "frieden";
  if (passt(["krieg", "angriff", "rakete", "drohne", "bomb", "soldat", "gefecht", "militär", "armee", "front", "beschuss", "luftangriff", "anschlag", "terror", "waffen"])) return "krieg";
  if (passt(["diebstahl", "gestohlen", "raub", "betrug", "hacker", "einbruch", "festgenommen", "polizei", "ermittl", "diebe", "kriminell", "mafia", "cyberangriff"])) return "dieb";
  if (passt(["erdbeben", "flut", "hochwasser", "sturm", "hurrikan", "taifun", "brand", "feuer", "unwetter", "vulkan", "dürre", "lawine", "tote bei", "unglück"])) return "katastrophe";
  if (passt(["milliard", "millionen", "euro", "dollar", "börse", "dax", "zins", "inflation", "wirtschaft", "aktie", "konzern", "umsatz", "steuer", "haushalt", "zölle", "zoll"])) return "geld";
  if (passt(["ki", "künstliche intelligenz", "software", "chip", "apple", "google", "microsoft", "update", "sicherheitslücke", "tech", "rakete ins all", "satellit"])) return "tech";
  if (passt(["wahl", "präsident", "regierung", "parlament", "kanzler", "minister", "partei", "koalition", "gipfel", "bundestag", "senat"])) return "politik";
  if (passt(["virus", "krankheit", "klinik", "gesundheit", "impf", "pandemie", "krankenhaus"])) return "gesundheit";
  if (passt(["fußball", "bundesliga", "handball", "tennis", "olympia", "sieg gegen", "meister", "wm", "em"])) return "sport";
  return "sonst";
}

class KlausGlobus {
  constructor(canvas) {
    this.c = canvas;
    this.ctx = canvas.getContext("2d");
    this.drehL = -10; this.drehB = 20;        // aktuelle Blickrichtung (Laenge/Breite der Mitte)
    this.zielL = this.drehL; this.zielB = this.drehB;
    this.zoom = 1; this.zielZoom = 1;
    this.punkte = [];                          // Landpunkte [lon, lat]
    if (typeof WELTKARTE !== "undefined") {
      const k = WELTKARTE.welt;
      k.zeilen.forEach((z, j) => { for (let i = 0; i < z.length; i++) if (z[i] === "1") this.punkte.push([k.lon0 + (i + 0.5) * k.schritt, k.lat0 - (j + 0.5) * k.schritt]); });
    }
    this.ereignis = [];                        // aktive Meldungen mit Animation
    this.fokus = null;
    this.teilchen = [];
    this.t = 0; this.letzte = performance.now(); this.laeuft = false;
    this.ruhig = matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.start();
  }

  // Mehrere Meldungen als Punkte (ohne Fokus)
  ereignisse(liste) {
    this.ereignis = liste.filter((e) => e.lat !== undefined).map((e, i) => ({ ...e, art: e.art || globusArt(e.titel), geboren: performance.now() + i * 120 }));
  }

  // Zu einem Ort drehen, heranzoomen und die Animation der Art abspielen
  zeige(e) {
    const art = e.art || globusArt(e.titel);
    const neu = { ...e, art, geboren: performance.now(), fokus: true };
    this.ereignis = this.ereignis.filter((x) => !(Math.abs(x.lat - e.lat) < 0.01 && Math.abs(x.lon - e.lon) < 0.01));
    this.ereignis.push(neu);
    this.fokus = neu;
    this.zielL = e.lon; this.zielB = Math.max(-50, Math.min(60, e.lat));
    this.zielZoom = e.zoom || 1.18;   // naeher ran, aber die Kugel bleibt im Fenster
    this.teilchen = [];
    return neu;
  }

  uebersicht() { this.fokus = null; this.zielZoom = 1; }

  start() {
    if (this.laeuft) return;
    this.laeuft = true;
    const schleife = (jetzt) => {
      if (!this.c.isConnected) { this.laeuft = false; return; }
      if (window.klausPause) { setTimeout(() => requestAnimationFrame(schleife), 500); return; }
      requestAnimationFrame(schleife);
      if (jetzt - this.letzte < 30) return;    // ~30 Bilder/s
      const dt = Math.min(0.1, (jetzt - this.letzte) / 1000);
      this.letzte = jetzt; this.t += dt;
      this.bewegen(dt);
      this.zeichne(jetzt);
    };
    requestAnimationFrame(schleife);
  }

  bewegen(dt) {
    if (!this.fokus) this.zielL += dt * 6;      // ohne Fokus langsam weiterdrehen
    let d = ((this.zielL - this.drehL + 540) % 360) - 180;  // kuerzester Weg
    const k = Math.min(1, dt * 2.2);
    this.drehL += d * k;
    this.drehB += (this.zielB - this.drehB) * k;
    this.zoom += (this.zielZoom - this.zoom) * Math.min(1, dt * 1.6);
  }

  // Orthografische Projektion -> [x, y, sichtbar(z>0)]
  proj(lon, lat, mx, my, r) {
    const l = (lon - this.drehL) * Math.PI / 180, b = lat * Math.PI / 180, b0 = this.drehB * Math.PI / 180;
    const x = Math.cos(b) * Math.sin(l);
    const y = Math.cos(b0) * Math.sin(b) - Math.sin(b0) * Math.cos(b) * Math.cos(l);
    const z = Math.sin(b0) * Math.sin(b) + Math.cos(b0) * Math.cos(b) * Math.cos(l);
    return [mx + x * r, my - y * r, z];
  }

  zeichne(jetzt) {
    const { c, ctx } = this, dpr = Math.min(1.5, devicePixelRatio || 1), w = c.clientWidth, h = c.clientHeight;
    if (!w || !h) return;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const rgb = getComputedStyle(document.documentElement).getPropertyValue("--rgb").trim() || "255,59,48";
    const f = (a) => `rgba(${rgb},${a})`, voll = Math.PI * 2;
    const mx = w / 2, my = h / 2, r = Math.min(w, h) * 0.37 * this.zoom;

    // Atmosphaere + Kugel
    let g = ctx.createRadialGradient(mx, my, r * 0.9, mx, my, r * 1.25);
    g.addColorStop(0, f(0.25)); g.addColorStop(1, f(0));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(mx, my, r * 1.25, 0, voll); ctx.fill();
    g = ctx.createRadialGradient(mx - r * 0.35, my - r * 0.4, r * 0.1, mx, my, r);
    g.addColorStop(0, "rgba(40,30,30,.85)"); g.addColorStop(1, "rgba(6,3,3,.95)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(mx, my, r, 0, voll); ctx.fill();
    ctx.strokeStyle = f(0.5); ctx.lineWidth = 1.2; ctx.beginPath(); ctx.arc(mx, my, r, 0, voll); ctx.stroke();

    // Gradnetz (alle 30 Grad), nur Vorderseite
    ctx.strokeStyle = f(0.12); ctx.lineWidth = 0.8;
    for (let lon = -180; lon < 180; lon += 30) {
      ctx.beginPath(); let an = false;
      for (let lat = -85; lat <= 85; lat += 5) { const [x, y, z] = this.proj(lon, lat, mx, my, r); if (z > 0) { an ? ctx.lineTo(x, y) : ctx.moveTo(x, y); an = true; } else an = false; }
      ctx.stroke();
    }
    for (let lat = -60; lat <= 60; lat += 30) {
      ctx.beginPath(); let an = false;
      for (let lon = -180; lon <= 180; lon += 5) { const [x, y, z] = this.proj(lon, lat, mx, my, r); if (z > 0) { an ? ctx.lineTo(x, y) : ctx.moveTo(x, y); an = true; } else an = false; }
      ctx.stroke();
    }
    // Land: Punkte, zum Rand hin dunkler (Kugelwirkung)
    const groesse = Math.max(1.2, r / 150);
    for (const [lon, lat] of this.punkte) {
      const [x, y, z] = this.proj(lon, lat, mx, my, r);
      if (z <= 0.02) continue;
      ctx.fillStyle = f(0.15 + z * 0.55);
      ctx.fillRect(x - groesse / 2, y - groesse / 2, groesse, groesse);
    }
    // Lichtkante oben links
    ctx.strokeStyle = "rgba(255,255,255,.18)"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(mx, my, r - 1, Math.PI * 1.05, Math.PI * 1.45); ctx.stroke();

    // Meldungen
    ctx.globalCompositeOperation = "lighter";
    for (const e of this.ereignis) {
      if (jetzt < e.geboren) continue;
      const [x, y, z] = this.proj(e.lon, e.lat, mx, my, r);
      if (z <= 0) continue;
      const alter = (jetzt - e.geboren) / 1000, a = GLOBUS_ARTEN[e.art] || GLOBUS_ARTEN.sonst, farbe = (al) => `rgba(${a.farbe},${al * z})`;
      if (e.fokus && e === this.fokus) this.animation(e, x, y, alter, farbe, r);
      const puls = (alter * 0.8) % 1;
      ctx.strokeStyle = farbe((1 - puls) * 0.7); ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.arc(x, y, 3 + puls * 12, 0, voll); ctx.stroke();
      ctx.fillStyle = farbe(1); ctx.beginPath(); ctx.arc(x, y, e === this.fokus ? 4.5 : 3, 0, voll); ctx.fill();
    }
    // Teilchen (Explosionen, Muenzen, Funken)
    for (const p of this.teilchen) {
      p.x += p.vx; p.y += p.vy; p.vy += p.g; p.leben -= 0.02;
      if (p.leben <= 0) continue;
      ctx.fillStyle = `rgba(${p.farbe},${p.leben})`;
      if (p.text) { ctx.font = `700 ${p.groesse}px 'Chakra Petch', sans-serif`; ctx.textAlign = "center"; ctx.fillText(p.text, p.x, p.y); }
      else { ctx.beginPath(); ctx.arc(p.x, p.y, p.groesse * p.leben, 0, voll); ctx.fill(); }
    }
    this.teilchen = this.teilchen.filter((p) => p.leben > 0);
    ctx.globalCompositeOperation = "source-over";

    // Beschriftung der Fokus-Meldung: Linie nach aussen + Kasten
    if (this.fokus) {
      const e = this.fokus, [x, y, z] = this.proj(e.lon, e.lat, mx, my, r);
      if (z > 0) {
        // Beschriftung fest in der oberen Ecke gegenueber vom Punkt - nie abgeschnitten
        const a = GLOBUS_ARTEN[e.art] || GLOBUS_ARTEN.sonst, rechts = x < mx;
        const ex = rechts ? w - 22 : 22, ey = 78;
        ctx.strokeStyle = `rgba(${a.farbe},.8)`; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + (ex - x) * 0.4, ey); ctx.lineTo(ex, ey); ctx.stroke();
        ctx.font = "600 12px 'Chakra Petch', sans-serif"; ctx.textAlign = rechts ? "right" : "left";
        ctx.fillStyle = `rgba(${a.farbe},1)`; ctx.fillText(`${a.symbol} ${a.name}${e.ort ? " · " + String(e.ort).toUpperCase() : ""}`, ex, ey - 8);
        const titel = (e.titel || "").slice(0, 70);
        ctx.font = "500 14px 'Barlow SC', sans-serif"; ctx.fillStyle = "#fff";
        ctx.lineWidth = 3; ctx.strokeStyle = "rgba(0,0,0,.85)"; ctx.strokeText(titel, ex, ey + 12); ctx.fillText(titel, ex, ey + 12);
      }
    }
  }

  // Art-spezifische Animation am Fokus-Punkt
  animation(e, x, y, alter, farbe, r) {
    const ctx = this.ctx, voll = Math.PI * 2, a = GLOBUS_ARTEN[e.art] || GLOBUS_ARTEN.sonst;
    const neu = (n, opt) => { for (let i = 0; i < n; i++) this.teilchen.push({ x, y, leben: 1, farbe: a.farbe, g: 0, ...opt(i) }); };
    const takt = Math.floor(alter * 2), schonGemacht = e._takt === takt;
    e._takt = takt;
    switch (e.art) {
      case "krieg": {  // Explosionswellen + Funken + Fadenkreuz
        for (let k = 0; k < 3; k++) {
          const p = ((alter * 0.9 + k / 3) % 1);
          ctx.strokeStyle = farbe((1 - p) * 0.9); ctx.lineWidth = 2.5 * (1 - p) + 0.5;
          ctx.beginPath(); ctx.arc(x, y, 6 + p * r * 0.22, 0, voll); ctx.stroke();
        }
        if (!schonGemacht && !this.ruhig) neu(14, () => { const w = Math.random() * voll, v = 1 + Math.random() * 3; return { vx: Math.cos(w) * v, vy: Math.sin(w) * v, groesse: 2.5, farbe: Math.random() < 0.5 ? "255,200,80" : a.farbe }; });
        ctx.strokeStyle = farbe(0.9); ctx.lineWidth = 1;
        const k = 14 + Math.sin(alter * 6) * 3;
        ctx.beginPath(); ctx.moveTo(x - k * 2, y); ctx.lineTo(x - k, y); ctx.moveTo(x + k, y); ctx.lineTo(x + k * 2, y);
        ctx.moveTo(x, y - k * 2); ctx.lineTo(x, y - k); ctx.moveTo(x, y + k); ctx.lineTo(x, y + k * 2); ctx.stroke();
        break;
      }
      case "frieden": {  // ruhige, helle Ringe + Taube-Symbol
        for (let k = 0; k < 2; k++) {
          const p = ((alter * 0.35 + k / 2) % 1);
          ctx.strokeStyle = farbe((1 - p) * 0.8); ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.arc(x, y, 8 + p * r * 0.3, 0, voll); ctx.stroke();
        }
        ctx.font = "700 26px 'Segoe UI Symbol', sans-serif"; ctx.textAlign = "center"; ctx.fillStyle = farbe(0.6 + 0.4 * Math.sin(alter * 2));
        ctx.fillText("☮", x, y - 22);
        break;
      }
      case "geld": {  // Muenzen steigen auf
        if (!schonGemacht && !this.ruhig) neu(5, () => ({ vx: (Math.random() - 0.5) * 1.2, vy: -1.5 - Math.random() * 1.5, g: 0.02, text: Math.random() < 0.6 ? "€" : "$", groesse: 14 + Math.random() * 8 }));
        ctx.strokeStyle = farbe(0.7); ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, 12 + Math.sin(alter * 4) * 2, 0, voll); ctx.stroke();
        break;
      }
      case "dieb": {  // Alarm: blinkendes Warndreieck + Scan-Kreis
        const an = Math.floor(alter * 4) % 2 === 0;
        ctx.fillStyle = farbe(an ? 0.95 : 0.25); ctx.beginPath(); ctx.moveTo(x, y - 34); ctx.lineTo(x - 14, y - 10); ctx.lineTo(x + 14, y - 10); ctx.closePath(); ctx.fill();
        ctx.fillStyle = "rgba(0,0,0,.85)"; ctx.font = "800 14px 'Chakra Petch', sans-serif"; ctx.textAlign = "center"; ctx.fillText("!", x, y - 14);
        const w0 = alter * 3;
        ctx.strokeStyle = farbe(0.8); ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, 22, w0, w0 + 1.2); ctx.stroke();
        ctx.beginPath(); ctx.arc(x, y, 22, w0 + Math.PI, w0 + Math.PI + 1.2); ctx.stroke();
        break;
      }
      case "katastrophe": {  // Erschuetterung: verzerrte Wellen
        for (let k = 0; k < 4; k++) {
          const p = ((alter * 0.6 + k / 4) % 1), rr = 6 + p * r * 0.25;
          ctx.strokeStyle = farbe((1 - p) * 0.8); ctx.lineWidth = 1.5; ctx.beginPath();
          for (let i = 0; i <= 40; i++) { const w = (i / 40) * voll, q = rr + Math.sin(w * 8 + alter * 10) * 3 * (1 - p); i ? ctx.lineTo(x + Math.cos(w) * q, y + Math.sin(w) * q) : ctx.moveTo(x + Math.cos(w) * q, y + Math.sin(w) * q); }
          ctx.stroke();
        }
        break;
      }
      case "tech": {
        if (!schonGemacht && !this.ruhig) neu(10, () => { const w = Math.random() * voll; return { vx: Math.cos(w) * 2.5, vy: Math.sin(w) * 2.5, groesse: 1.8 }; });
        ctx.strokeStyle = farbe(0.8); ctx.lineWidth = 1; const s = 16;
        ctx.strokeRect(x - s, y - s, s * 2, s * 2); ctx.strokeRect(x - s / 2, y - s / 2, s, s);
        break;
      }
      default: {  // Politik, Gesundheit, Sport, sonst: Puls + Symbol
        const p = (alter * 0.7) % 1;
        ctx.strokeStyle = farbe((1 - p) * 0.9); ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, 8 + p * r * 0.18, 0, voll); ctx.stroke();
        ctx.font = "700 20px 'Chakra Petch', 'Segoe UI Symbol', sans-serif"; ctx.textAlign = "center"; ctx.fillStyle = farbe(0.9);
        ctx.fillText(a.symbol, x, y - 18);
      }
    }
  }
}

// ------------------------------------------------------------------ Holo-Pop-up "globus"
// Python schickt {ereignisse: [...]} einmal und dann {fokus: {lat, lon, art, titel, ort}} pro erzaehlter Meldung.
if (typeof POPUP_GROESSE !== "undefined") {
  POPUP_GROESSE.globus = [0.42, 0.9];
  POPUP_DAUER.globus = 90;
  POPUP_TITEL.globus = "GLOBUS · WELTLAGE";
  POPUP_ARTEN.globus = function (box) {
    box.classList.add("p-globus");
    box.innerHTML = `<canvas class="g-kugel"></canvas><div class="g-legende"></div><div class="g-unterzeile"></div>`;
    const g = new KlausGlobus(box.querySelector("canvas"));
    const legende = box.querySelector(".g-legende"), unter = box.querySelector(".g-unterzeile");
    return {
      update(d) {
        if (d.ereignisse) {
          g.ereignisse(d.ereignisse);
          const arten = [...new Set(g.ereignis.map((e) => e.art))];
          legende.innerHTML = arten.map((a) => `<span style="--g: rgb(${GLOBUS_ARTEN[a].farbe})"><i></i>${GLOBUS_ARTEN[a].name}</span>`).join("");
        }
        if (d.fokus) {
          const e = g.zeige(d.fokus);
          unter.textContent = e.titel || "";
          unter.style.setProperty("--g", `rgb(${(GLOBUS_ARTEN[e.art] || GLOBUS_ARTEN.sonst).farbe})`);
        }
        if (d.uebersicht) { g.uebersicht(); unter.textContent = ""; }
      },
    };
  };
}
