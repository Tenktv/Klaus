// Gemeinsam fuer dashboard.html und chat.html: Verbindung zu Python + animierter Orb.

// Python-Objekt `klaus` (siehe fenster.py WebBruecke). Slots mit Rueckgabewert sind asynchron.
window.klausBereit = new Promise((fertig) => {
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
  sprechen: [0, 200, 255], aktion: [61, 255, 168], fehler: [255, 61, 90],
  freigabe: [255, 150, 0], fertig: [61, 255, 168],   // Freigabe immer Bernstein, Ausfuehren/Fertig immer Gruen
};

let aktuellesThema = "jarvis";

// Setzt die CSS-Variablen (--rgb, --rgb2, --bg, --glow, --text) und die Orb-Farben
function wendeThemaAn(name) {
  const t = THEMEN[name] || THEMEN.jarvis;
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

// Holo-Kern: nur Licht, kein Glas und kein Metall - heller Energiekern, gegenlaeufige Leuchtringe, feine Skala.
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
    return { mx: w / 2, my: h / 2, gehaeuse: r * 0.95, linse: r * 0.37 };
  }

  rgba(a, hell = 0) {
    const [r, g, b] = this.farbe.map((w) => w + (255 - w) * hell);
    return `rgba(${r | 0},${g | 0},${b | 0},${Math.max(0, Math.min(1, a))})`;
  }

  tick(jetzt) {
    // Panel verdeckt (Spiel im Vollbild): nichts zeichnen, nur selten nachschauen
    if (window.klausPause || document.hidden) {
      this.letzte = jetzt;
      setTimeout(() => requestAnimationFrame((z) => this.tick(z)), 500);
      return;
    }
    const aktiv = this.zustand !== "aus" || this.burst >= 0 || this.pegelZiel > 0.02;
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
    requestAnimationFrame((z) => this.tick(z));
  }

  // Statische Skala (weiss, dezent) einmal pro Pixelgroesse vorzeichnen; pro Bild nur gedreht eingeblendet
  baueStatisch(px) {
    const c = document.createElement("canvas");
    c.width = c.height = px;
    const x = c.getContext("2d");
    x.scale(px / 600, px / 600);
    const cx = 300, cy = 300, voll = Math.PI * 2;
    x.lineWidth = 1;
    for (const [r, a] of [[284, 0.10], [226, 0.07], [128, 0.08]]) {
      x.beginPath(); x.arc(cx, cy, r, 0, voll); x.strokeStyle = `rgba(255,255,255,${a})`; x.stroke();
    }
    // Skala: 120 Striche, jeder 10. lang
    for (const lang of [true, false]) {
      x.beginPath();
      for (let i = 0; i < 120; i++) {
        if ((i % 10 === 0) !== lang) continue;
        const a = (i / 120) * voll, l = lang ? 11 : 4;
        x.moveTo(cx + Math.cos(a) * (268 - l), cy + Math.sin(a) * (268 - l));
        x.lineTo(cx + Math.cos(a) * 268, cy + Math.sin(a) * 268);
      }
      x.strokeStyle = lang ? "rgba(255,255,255,.38)" : "rgba(255,255,255,.14)";
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

    // Energie des Kerns je Zustand
    let pu;
    if (z === "hoeren" || z === "start") pu = 0.9 + this.pegel * 0.6;
    else if (z === "sprechen") pu = 0.95 + this.pegel * 0.5;
    else if (z === "denken") pu = 1.05 + 0.1 * Math.sin(t * 9);
    else if (z === "freigabe") pu = 1 + 0.2 * (0.5 + 0.5 * Math.sin(t * 5.6));
    else if (z === "aktion" || z === "fertig") pu = 1.1 + 0.05 * Math.sin(t * 4);
    else if (z === "fehler") pu = 0.8 + 0.05 * Math.sin(t * 3);
    else pu = 1 + 0.07 * Math.sin((t * Math.PI * 2) / 5);   // Atmen

    ctx.globalCompositeOperation = "lighter";
    // Skala (statisch, langsam gedreht)
    ctx.save(); ctx.translate(cx, cy); ctx.rotate(this.drehA * 0.3); ctx.translate(-cx, -cy);
    ctx.drawImage(this.statisch.skala, 0, 0, 600, 600);
    ctx.restore();

    // Abtast-Kegel beim Denken/Ausfuehren
    if ((z === "denken" || z === "aktion") && ctx.createConicGradient) {
      const kegel = ctx.createConicGradient(this.drehC * 2, cx, cy);
      kegel.addColorStop(0, rgba(0.22)); kegel.addColorStop(0.12, rgba(0)); kegel.addColorStop(1, rgba(0));
      ctx.fillStyle = kegel; ctx.beginPath(); ctx.arc(cx, cy, 262, 0, voll); ctx.fill();
    }

    // Aeussere Ringe: zwei duenne Boegen, Segmentring, drei lange Lichtboegen
    this.boegen(244, 2, 1.6, -this.drehA * 0.8, 1.4, rgba, 0.55);
    this.segRing(204, 6, 36, 0.78, this.drehA, rgba(1), 0.22 + 0.14 * pu);
    this.segRing(204, 1.2, 36, 0.78, this.drehA, rgba(1, 0.5), 0.55);
    this.boegen(164, 3, 0.9, this.drehB, 3, rgba, 0.85);
    this.segRing(110, 1.5, 60, 0.5, -this.drehB * 1.4, rgba(1, 0.3), 0.5);

    // Kern: weiches Leuchten, heller Mittelpunkt, Rand, Plasma-Boegen
    const r = 150 * pu;
    let g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    g.addColorStop(0, "rgba(255,255,255,1)");
    g.addColorStop(0.07, rgba(1, 0.75));
    g.addColorStop(0.2, rgba(0.85, 0.15));
    g.addColorStop(0.45, rgba(0.28));
    g.addColorStop(1, rgba(0));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, r, 0, voll); ctx.fill();
    ctx.lineWidth = 8; ctx.strokeStyle = rgba(0.12 * pu);
    ctx.beginPath(); ctx.arc(cx, cy, 48 * pu, 0, voll); ctx.stroke();
    ctx.lineWidth = 1.6; ctx.strokeStyle = rgba(0.85, 0.4);
    ctx.beginPath(); ctx.arc(cx, cy, 48 * pu, 0, voll); ctx.stroke();
    this.boegen(72 * (0.9 + pu * 0.1), 3, 1.1, this.drehC * 3, 2.4, (a) => rgba(a, 0.3), 0.8);
    this.boegen(86, 4, 0.35, -this.drehC * 2, 1.2, rgba, 0.6);

    // Ring-Burst bei Ausfuehren/Fertig
    if (this.burst >= 0) {
      const p = (jetzt - this.burst) / 1100;
      if (p > 1) this.burst = -1;
      else {
        const e = 1 - Math.pow(1 - p, 3);
        ctx.beginPath(); ctx.arc(cx, cy, 200 + e * 90, 0, voll); ctx.lineWidth = 6 * (1 - p) + 0.5; ctx.strokeStyle = rgba(1 - p); ctx.stroke();
        ctx.beginPath(); ctx.arc(cx, cy, 200 + e * 56, 0, voll); ctx.lineWidth = 1; ctx.strokeStyle = `rgba(255,255,255,${(1 - p) * 0.8})`; ctx.stroke();
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
