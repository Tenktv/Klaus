// Gemeinsam fuer dashboard.html und chat.html: Verbindung zu Python + animierter Orb.

// Python-Objekt `klaus` (siehe fenster.py WebBruecke). Slots mit Rueckgabewert sind asynchron.
// Ausserhalb von Qt (Stream-Overlay in OBS) gibt es keinen Kanal: dann bleibt das Versprechen einfach offen.
window.klausBereit = new Promise((fertig) => {
  if (typeof QWebChannel === "undefined" || typeof qt === "undefined") return;
  new QWebChannel(qt.webChannelTransport, (kanal) => fertig(kanal.objects.klaus));
});

// Design-Varianten (Namen wie in fenster.py THEMEN). haupt = Linien/Text, zweit = Nachdenken/Hinweise.
const THEMEN = {
  jarvis:    { titel: "Jarvis",    haupt: [0, 229, 255],   zweit: [255, 179, 0],  bg: "#02060c", glow: "#04202c", text: "#cfefff" },
  ironman:   { titel: "Iron Man",  haupt: [255, 59, 48],   zweit: [255, 196, 0],  bg: "#080202", glow: "#2a0707", text: "#ffe2dc" },
  matrix:    { titel: "Matrix",    haupt: [0, 255, 120],   zweit: [180, 255, 0],  bg: "#010603", glow: "#03200f", text: "#d4ffe4" },
  synthwave: { titel: "Synthwave", haupt: [190, 90, 255],  zweit: [255, 60, 170], bg: "#06020c", glow: "#1d0832", text: "#efe0ff" },
  gold:      { titel: "Gold",      haupt: [255, 176, 0],   zweit: [255, 90, 40],  bg: "#070400", glow: "#241600", text: "#fff0d0" },
  arktis:    { titel: "Arktis",    haupt: [200, 235, 255], zweit: [120, 180, 255], bg: "#05080c", glow: "#16263a", text: "#eef6ff" },
};

const ORB_FARBEN = {
  aus: [0, 229, 255], start: [0, 229, 255], hoeren: [0, 229, 255], denken: [0, 229, 255],
  sprechen: [0, 200, 255], aktion: [157, 197, 170], fehler: [237, 156, 145],
  freigabe: [226, 184, 119], fertig: [157, 197, 170],   // Freigabe immer Bernstein, Ausfuehren/Fertig immer Gruen
};

let aktuellesThema = "jarvis";

// Setzt die CSS-Variablen (--rgb, --rgb2, --bg, --glow, --text) und die Orb-Farben
function wendeThemaAn(name) {
  const accent = { jarvis: [189, 199, 190], ironman: [217, 166, 148], matrix: [171, 194, 164], synthwave: [193, 179, 199], gold: [213, 186, 133], arktis: [188, 200, 208] };
  const t = { ...(THEMEN[name] || THEMEN.jarvis), haupt: accent[name] || accent.gold, zweit: [226, 184, 119], bg: "#191918", glow: "#35302a", text: "#f1ede4" };
  aktuellesThema = THEMEN[name] ? name : "jarvis";
  const s = document.documentElement.style;
  const hex = (rgb) => "#" + rgb.map((w) => w.toString(16).padStart(2, "0")).join("");
  s.setProperty("--rgb", t.haupt.join(", "));
  s.setProperty("--rgb2", t.zweit.join(", "));
  s.setProperty("--cyan", hex(t.haupt));
  s.setProperty("--bernstein", hex(t.zweit));
  s.setProperty("--bg", t.bg);
  s.setProperty("--glow", t.glow);
  s.setProperty("--text", t.text);
  for (const z of ["aus", "start", "hoeren"]) ORB_FARBEN[z] = t.haupt;
  ORB_FARBEN.sprechen = t.haupt.map((w) => Math.round(w * 0.88));
  ORB_FARBEN.denken = t.haupt;   // Stark: das Auge bleibt beim Denken in der Hauptfarbe
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", t.bg);
}

// Reaktor-Kern: Portal aus Licht - Tunnel-Ringe mit Tiefe, Lichtstrahlen, gluehender Hauptring, weisser Kern.
// Gezeichnet in 600er-Einheiten und auf die Canvas skaliert; die Skala ist statisch (Offscreen-Canvas).
class KlausOrb {
  // platz < 1: Auge kleiner zeichnen (Rand fuer Effekte)
  constructor(canvas, { platz = 1 } = {}) {
    this.platz = platz;
    this.c = canvas;
    this.ctx = canvas.getContext("2d");
    this.zustand = "aus";
    this.farbe = [...ORB_FARBEN.aus];
    this.pegel = 0;
    this.pegelZiel = 0;
    this.t = 0;
    this.drehA = 0; this.drehB = 0; this.drehC = 0;
    this.burst = -1;
    this.letzte = performance.now();
    this.ruhig = matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.statisch = null;   // { px, skala }
    requestAnimationFrame((z) => this.tick(z));
  }

  setZustand(z) {
    if ((z === "fertig" || z === "aktion") && z !== this.zustand) this.burst = performance.now();
    this.zustand = z;
  }

  setPegel(p) { this.pegelZiel = Math.max(0, Math.min(1, p)); }
  funkenregen() { this.burst = performance.now(); }  // alte Schnittstelle

  // Lage des Kerns in CSS-Pixeln der Canvas: Mitte, aeusserer Ring (gehaeuse) und innerer Ring (linse)
  geometrie() {
    const w = this.c.clientWidth, h = this.c.clientHeight, r = (Math.min(w, h) / 2) * this.platz;
    return { mx: w / 2, my: h / 2, gehaeuse: r * 0.95, linse: r * 0.5 };
  }

  rgba(a, hell = 0) {
    const [r, g, b] = this.farbe.map((w) => w + (255 - w) * hell);
    return `rgba(${r | 0},${g | 0},${b | 0},${Math.max(0, Math.min(1, a))})`;
  }

  tick(jetzt) {
    // Panel verdeckt (Spiel im Vollbild): nichts zeichnen, nur selten nachschauen
    if (!this.c.isConnected) return;
    if (window.klausPause || document.hidden) {
      this.letzte = jetzt;
      setTimeout(() => this.tick(performance.now()), 500);
      return;
    }
    const aktiv = this.zustand !== "aus" || this.burst >= 0 || this.pegelZiel > 0.02;
    // Ruhe und reduzierte Bewegung: nur bei Groesse, Farbe, Zustand oder Pegel neu zeichnen.
    if (!aktiv || this.ruhig) {
      const ziel = ORB_FARBEN[this.zustand] || ORB_FARBEN.aus;
      const bild = `${this.c.clientWidth}x${this.c.clientHeight}|${devicePixelRatio}|${this.zustand}|${ziel}|${this.ruhig ? this.pegelZiel.toFixed(1) : 0}`;
      this.farbe = [...ziel]; this.pegel = this.pegelZiel; this.letzte = jetzt;
      if (this.ruheBild !== bild) { this.ruheBild = bild; this.zeichne(jetzt); }
      if (this.ruhig) this.burst = -1;
      setTimeout(() => this.tick(performance.now()), 150);
      return;
    }
    this.ruheBild = null;
    if (jetzt - this.letzte < (this.ruhig ? 110 : aktiv ? 15 : 48)) {  // Ruhe: ~20 Bilder/s reichen fuers Atmen
      requestAnimationFrame((z) => this.tick(z));
      return;
    }
    const dt = Math.min(0.064, (jetzt - this.letzte) / 1000);
    this.letzte = jetzt;
    this.t += dt;
    this.pegel += (this.pegelZiel - this.pegel) * 0.3;
    const ziel = ORB_FARBEN[this.zustand] || ORB_FARBEN.aus, k = Math.min(1, dt * 4);
    this.farbe = this.farbe.map((w, i) => w + (ziel[i] - w) * k);
    const tempo = { aus: 1, start: 1.4, hoeren: 1.6, denken: 7, sprechen: 2, aktion: 3.2, freigabe: 0.6, fertig: 2, fehler: 0.4 }[this.zustand] ?? 1;
    if (!this.ruhig) { this.drehA += dt * 0.10 * tempo; this.drehB -= dt * 0.16 * tempo; this.drehC += dt * 0.42 * tempo; }
    this.zeichne(jetzt);
    // Ruhe: per Timer warten statt jedes Bild abzufragen - sonst muss der Browser dauernd 60 Bilder/s erzeugen
    if (aktiv) requestAnimationFrame((z) => this.tick(z));
    else setTimeout(() => requestAnimationFrame((z) => this.tick(z)), 55);
  }

  // Statische Teile (weiss, dezent) einmal pro Pixelgroesse vorzeichnen: Skala, Tunnel-Ringe, Lichtstrahlen.
  // Pro Bild wird das nur gedreht eingeblendet und farbig ueberstrahlt.
  baueStatisch(px) {
    const c = document.createElement("canvas");
    c.width = c.height = px;
    const x = c.getContext("2d");
    x.scale(px / 600, px / 600);
    const cx = 300, cy = 300, voll = Math.PI * 2;
    // Tunnel: Ringe ruecken zur Mitte hin enger zusammen und werden heller (Tiefe)
    for (let i = 0; i < 9; i++) {
      const k = i / 9, r = 62 + 214 * Math.pow(1 - k, 1.5);
      x.beginPath(); x.arc(cx, cy, r, 0, voll);
      x.lineWidth = 1; x.strokeStyle = `rgba(255,255,255,${0.05 + k * 0.12})`; x.stroke();
    }
    // Lichtstrahlen in den Tunnel hinein
    const strahl = x.createRadialGradient(cx, cy, 30, cx, cy, 250);
    strahl.addColorStop(0, "rgba(255,255,255,.55)"); strahl.addColorStop(0.45, "rgba(255,255,255,.10)"); strahl.addColorStop(1, "rgba(255,255,255,0)");
    x.strokeStyle = strahl;
    for (const [n, b] of [[72, 0.8], [18, 2.2]]) {
      x.beginPath();
      for (let i = 0; i < n; i++) {
        const a = (i / n) * voll + (b > 1 ? 0.09 : 0), innen = 34 + (i % 3) * 8;
        x.moveTo(cx + Math.cos(a) * innen, cy + Math.sin(a) * innen);
        x.lineTo(cx + Math.cos(a) * 250, cy + Math.sin(a) * 250);
      }
      x.lineWidth = b; x.stroke();
    }
    // Skala aussen: 120 Striche, jeder 10. lang
    for (const lang of [true, false]) {
      x.beginPath();
      for (let i = 0; i < 120; i++) {
        if ((i % 10 === 0) !== lang) continue;
        const a = (i / 120) * voll, l = lang ? 11 : 4;
        x.moveTo(cx + Math.cos(a) * (284 - l), cy + Math.sin(a) * (284 - l));
        x.lineTo(cx + Math.cos(a) * 284, cy + Math.sin(a) * 284);
      }
      x.lineWidth = 1; x.strokeStyle = lang ? "rgba(255,255,255,.4)" : "rgba(255,255,255,.15)";
      x.stroke();
    }
    this.statisch = { px, skala: c };
  }

  // Segmentring als zwei Pfade (jedes 6. Segment heller)
  segRing(r, breite, n, fuell, dreh, farbe, alpha) {
    const ctx = this.ctx, schritt = (Math.PI * 2) / n;
    ctx.save(); ctx.translate(300, 300); ctx.rotate(dreh);
    ctx.lineWidth = breite; ctx.strokeStyle = farbe;
    for (const hell of [true, false]) {
      ctx.globalAlpha = alpha * (hell ? 1 : 0.55);
      ctx.beginPath();
      for (let i = hell ? 0 : 1; i < n; i += hell ? 6 : 1) {
        if (!hell && i % 6 === 0) continue;
        const a = i * schritt;
        ctx.moveTo(Math.cos(a) * r, Math.sin(a) * r);
        ctx.arc(0, 0, r, a, a + schritt * fuell);
      }
      ctx.stroke();
    }
    ctx.restore(); ctx.globalAlpha = 1;
  }

  // Leuchtende Boegen: breiter weicher Schein + duenne helle Linie
  boegen(r, anzahl, spanne, dreh, breite, farbe, alpha) {
    const ctx = this.ctx, schritt = (Math.PI * 2) / anzahl;
    for (const [b, a] of [[breite * 4, alpha * 0.14], [breite, alpha]]) {
      ctx.beginPath();
      for (let i = 0; i < anzahl; i++) {
        const s = dreh + i * schritt;
        ctx.moveTo(300 + Math.cos(s) * r, 300 + Math.sin(s) * r);
        ctx.arc(300, 300, r, s, s + spanne);
      }
      ctx.lineWidth = b; ctx.strokeStyle = farbe(a); ctx.stroke();
    }
  }

  // Ring als leuchtende Roehre: mehrere Striche von breit/schwach nach duenn/weiss
  roehre(r, staerke, rgba) {
    const ctx = this.ctx;
    for (const [b, a, hell] of [[36, 0.08, 0], [16, 0.22, 0], [7, 0.75, 0.35], [2, 0.95, 0.85]]) {
      ctx.beginPath(); ctx.arc(300, 300, r, 0, Math.PI * 2);
      ctx.lineWidth = b * staerke; ctx.strokeStyle = rgba(a, hell); ctx.stroke();
    }
  }

  zeichne(jetzt) {
    const { c, ctx } = this;
    const dpr = Math.min(1.5, window.devicePixelRatio || 1);
    const w = c.clientWidth, h = c.clientHeight;
    if (!w || !h) return;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
    const groesse = Math.min(w, h) * this.platz, px = Math.max(64, Math.round(groesse * dpr));
    if (!this.statisch || this.statisch.px !== px) this.baueStatisch(px);
    const u = (groesse / 600) * dpr;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.setTransform(u, 0, 0, u, (w * dpr - groesse * dpr) / 2, (h * dpr - groesse * dpr) / 2);
    const cx = 300, cy = 300, voll = Math.PI * 2, t = this.t, z = this.zustand;
    const col = this.farbe;
    const rgba = (a, hell = 0) => `rgba(${(col[0] + (255 - col[0]) * hell) | 0},${(col[1] + (255 - col[1]) * hell) | 0},${(col[2] + (255 - col[2]) * hell) | 0},${Math.max(0, Math.min(1, a))})`;

    // Energie des Reaktors je Zustand
    let pu;
    if (z === "hoeren" || z === "start") pu = 0.9 + this.pegel * 0.6;
    else if (z === "sprechen") pu = 0.95 + this.pegel * 0.5;
    else if (z === "denken") pu = 1.05 + 0.1 * Math.sin(t * 9);
    else if (z === "freigabe") pu = 1 + 0.2 * (0.5 + 0.5 * Math.sin(t * 5.6));
    else if (z === "aktion" || z === "fertig") pu = 1.1 + 0.05 * Math.sin(t * 4);
    else if (z === "fehler") pu = 0.8 + 0.05 * Math.sin(t * 3);
    else pu = 1 + 0.07 * Math.sin((t * Math.PI * 2) / 5);   // Atmen

    ctx.globalCompositeOperation = "lighter";
    // Tiefes Leuchten im Tunnel
    let g = ctx.createRadialGradient(cx, cy, 0, cx, cy, 290);
    g.addColorStop(0, rgba(0.35 * pu)); g.addColorStop(0.5, rgba(0.08)); g.addColorStop(1, rgba(0));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, 290, 0, voll); ctx.fill();
    // Tunnel, Strahlen, Skala (statisch, langsam gedreht)
    ctx.save(); ctx.translate(cx, cy); ctx.rotate(this.drehA * 0.3); ctx.translate(-cx, -cy);
    ctx.drawImage(this.statisch.skala, 0, 0, 600, 600);
    ctx.restore();

    // Abtast-Kegel beim Denken/Ausfuehren
    if ((z === "denken" || z === "aktion") && ctx.createConicGradient) {
      const kegel = ctx.createConicGradient(this.drehC * 2, cx, cy);
      kegel.addColorStop(0, rgba(0.25)); kegel.addColorStop(0.12, rgba(0)); kegel.addColorStop(1, rgba(0));
      ctx.fillStyle = kegel; ctx.beginPath(); ctx.arc(cx, cy, 270, 0, voll); ctx.fill();
    }

    // Aussenstruktur: Plattenring + duenne Kante, gegenlaeufige Tunnel-Segmente
    this.segRing(244, 12, 24, 0.86, this.drehA, "rgba(255,255,255,1)", 0.07);
    this.segRing(244, 1.2, 24, 0.86, this.drehA, rgba(1, 0.5), 0.5);
    this.segRing(206, 4, 48, 0.6, -this.drehB, rgba(1, 0.2), 0.3 + 0.12 * pu);
    this.segRing(96, 2, 36, 0.5, this.drehB * 1.6, rgba(1, 0.4), 0.45);
    this.boegen(226, 3, 0.7, this.drehB * 0.7, 2, rgba, 0.75);
    // Warnlichter auf dem Plattenring
    ctx.fillStyle = `rgba(255,150,60,${0.55 + 0.25 * Math.sin(t * 2)})`;
    for (let i = 0; i < 8; i++) {
      const a = this.drehA + (i / 8) * voll + 0.12;
      ctx.beginPath(); ctx.arc(cx + Math.cos(a) * 244, cy + Math.sin(a) * 244, 2.4, 0, voll); ctx.fill();
    }

    // Portal: dicker gluehender Hauptring + innerer Ring
    this.roehre(150 * (0.97 + pu * 0.03), 0.8 + pu * 0.25, rgba);
    this.roehre(122, 0.35, rgba);
    this.boegen(150, 4, 0.5, -this.drehC * 1.5, 2.5, (a) => rgba(a, 0.9), 0.6);

    // Weisser Kern
    const r = 120 * pu;
    g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    g.addColorStop(0, "rgba(255,255,255,1)");
    g.addColorStop(0.14, "rgba(255,255,255,.9)");
    g.addColorStop(0.32, rgba(0.75, 0.45));
    g.addColorStop(0.65, rgba(0.18));
    g.addColorStop(1, rgba(0));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, r, 0, voll); ctx.fill();

    // Ring-Burst bei Ausfuehren/Fertig
    if (this.burst >= 0) {
      const p = (jetzt - this.burst) / 1100;
      if (p > 1) this.burst = -1;
      else {
        const e = 1 - Math.pow(1 - p, 3);
        ctx.beginPath(); ctx.arc(cx, cy, 150 + e * 140, 0, voll); ctx.lineWidth = 6 * (1 - p) + 0.5; ctx.strokeStyle = rgba(1 - p); ctx.stroke();
        ctx.beginPath(); ctx.arc(cx, cy, 150 + e * 90, 0, voll); ctx.lineWidth = 1; ctx.strokeStyle = `rgba(255,255,255,${(1 - p) * 0.8})`; ctx.stroke();
      }
    }
    ctx.globalCompositeOperation = "source-over";
  }
}

function el(tag, klasse, text) {
  const e = document.createElement(tag);
  if (klasse) e.className = klasse;
  if (text !== undefined) e.textContent = text;
  return e;
}
