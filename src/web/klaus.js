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
  aus: [0, 229, 255], start: [0, 229, 255], hoeren: [0, 229, 255], denken: [255, 179, 0],
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
  ORB_FARBEN.denken = t.zweit;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", t.bg);
}

class KlausOrb {
  // platz < 1: Orb kleiner zeichnen, z. B. damit aussen noch der Segment-Ring passt
  // pegelAbstand: Audio-Pegel bei dieser Hoehe (Anteil von min(Breite, Hoehe)) zeichnen, z. B. in der Luecke des Segment-Rings
  constructor(canvas, { platz = 1, pegelAbstand = null } = {}) {
    this.platz = platz;
    this.pegelAbstand = pegelAbstand;
    this.c = canvas;
    this.ctx = canvas.getContext("2d");
    this.zustand = "aus";
    this.farbe = [...ORB_FARBEN.aus];
    this.pegel = 0;
    this.pegelZiel = 0;
    this.blitz = 0;
    this.t = 0;
    this.drehung = 0;   // gemeinsamer Drehwinkel der Ringe, Tempo haengt vom Zustand ab
    this.letzte = performance.now();
    this.ruhig = matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.funken = [];
    // Equalizer-Werte fuer den Reaktor-Ring (geglaettet)
    this.segmente = new Float32Array(48);
    requestAnimationFrame((z) => this.tick(z));
  }

  setZustand(z) {
    if (z === "aktion" || (this.zustand === "aus" && z !== "aus")) {
      this.blitz = 1;
      this.funkenregen(z === "aktion" ? 60 : 28);
    }
    this.zustand = z;
  }

  setPegel(p) { this.pegelZiel = Math.max(0, Math.min(1, p)); }

  funkenregen(anzahl) {
    for (let i = 0; i < anzahl; i++) {
      const w = Math.random() * Math.PI * 2;
      this.funken.push({ w, r: 1, v: 2.2 + Math.random() * 3.5, leben: 1, g: 0.6 + Math.random() * 1.4 });
    }
  }

  tick(jetzt) {
    // Panel verdeckt (Spiel im Vollbild): nichts zeichnen, nur selten nachschauen
    if (window.klausPause) {
      this.letzte = jetzt;
      setTimeout(() => requestAnimationFrame((z) => this.tick(z)), 500);
      return;
    }
    // Ruhezustand: 30 statt 60 Bilder pro Sekunde reichen fuers Atmen
    if (this.zustand === "aus" && this.pegelZiel < 0.02 && !this.blitz && jetzt - this.letzte < 30) {
      requestAnimationFrame((z) => this.tick(z));
      return;
    }
    const dt = Math.min(0.05, (jetzt - this.letzte) / 1000);
    this.letzte = jetzt;
    this.t += dt;
    this.pegel += (this.pegelZiel - this.pegel) * 0.3;
    this.blitz = Math.max(0, this.blitz - dt * 1.3);
    const ziel = ORB_FARBEN[this.zustand] || ORB_FARBEN.aus;
    this.farbe = this.farbe.map((w, i) => w + (ziel[i] - w) * 0.08);

    const tempo = { aus: 0.12, start: 0.6, hoeren: 0.5, denken: 2.6, sprechen: 0.9, aktion: 1.6, fehler: 0.3, freigabe: 0.45, fertig: 1.1 }[this.zustand] ?? 0.3;
    this.drehung += dt * tempo * (this.ruhig ? 0.2 : 1);

    for (const f of this.funken) { f.r += f.v * dt * 60 * 0.9; f.v *= 0.965; f.leben -= dt * 1.1; }
    this.funken = this.funken.filter((f) => f.leben > 0);

    // Equalizer: jedes Segment folgt einer eigenen Welle, skaliert mit der Lautstaerke
    for (let i = 0; i < this.segmente.length; i++) {
      const welle = 0.5 + 0.5 * Math.sin(i * 0.9 + this.t * 7) * Math.sin(i * 0.37 - this.t * 3.1);
      let zielwert = this.pegel * (0.35 + 0.65 * welle);
      if (this.zustand === "denken") zielwert = 0.5 + 0.5 * Math.sin(i * 0.52 - this.t * 9);
      if (this.zustand === "aus") zielwert = 0.12 + 0.1 * Math.sin(i * 0.26 + this.t * 1.2);
      this.segmente[i] += (zielwert - this.segmente[i]) * 0.25;
    }
    this.zeichne();
    requestAnimationFrame((z) => this.tick(z));
  }

  rgba(a, hell = 0) {
    const [r, g, b] = this.farbe.map((w) => w + (255 - w) * hell);
    return `rgba(${r | 0},${g | 0},${b | 0},${Math.max(0, Math.min(1, a))})`;
  }

  zeichne() {
    const { c, ctx } = this;
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth, h = c.clientHeight;
    if (!w || !h) return;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    // Aeusserstes Element (Gradzahlen) liegt bei ca. 225 Einheiten -> so skalieren, dass es gerade in die Flaeche passt
    const mx = w / 2, my = h / 2, s = (Math.min(w, h) / 460) * this.platz;
    const aktiv = this.zustand !== "aus";
    const atem = 0.5 + 0.5 * Math.sin(this.t * 1.4);
    const energie = aktiv ? 0.55 + this.pegel * 0.45 : 0.28 + atem * 0.08;
    const r0 = 60 * s;
    const voll = Math.PI * 2;

    ctx.globalCompositeOperation = "lighter";

    // 1) Weiter Lichtschein
    let g = ctx.createRadialGradient(mx, my, r0 * 0.4, mx, my, r0 * 3.4);
    g.addColorStop(0, this.rgba(0.24 * energie));
    g.addColorStop(0.35, this.rgba(0.1 * energie));
    g.addColorStop(1, this.rgba(0));
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(mx, my, r0 * 3.4, 0, voll); ctx.fill();

    // 2) Ruhiger Rahmen ums Auge: ein feiner Fuehrungsring, zwei langsame Boegen, dezenter Radar-Schein
    const ring1 = r0 + 44 * s, ring2 = r0 + 78 * s;
    ctx.strokeStyle = this.rgba(aktiv ? 0.16 : 0.08);
    ctx.lineWidth = 1 * s;
    ctx.beginPath(); ctx.arc(mx, my, ring2, 0, voll); ctx.stroke();
    if (aktiv && ctx.createConicGradient) {
      const a = this.t * 1.1, kegel = ctx.createConicGradient(a, mx, my);
      kegel.addColorStop(0, this.rgba(0.12)); kegel.addColorStop(0.1, this.rgba(0)); kegel.addColorStop(1, this.rgba(0));
      ctx.fillStyle = kegel;
      ctx.beginPath(); ctx.arc(mx, my, ring2, 0, voll); ctx.fill();
    }
    [[ring1, 0.8, 1.6], [ring2, -0.5, 0.9]].forEach(([r, v, spanne], i) => {
      ctx.strokeStyle = this.rgba(aktiv ? 0.7 - i * 0.2 : 0.3 - i * 0.08, 0.15);
      ctx.lineWidth = (i ? 1.2 : 1.8) * s;
      ctx.lineCap = "round";
      for (const versatz of [0, Math.PI]) {
        const a = this.drehung * v + versatz;
        ctx.beginPath(); ctx.arc(mx, my, r, a, a + spanne); ctx.stroke();
      }
    });

    // 3) Audio-Pegel: feine Balken unter dem Auge
    if (s > 0.4) {
      const balken = 32, breite = 120 * s, an = this.pegel * balken;
      const y = this.pegelAbstand ? my + Math.min(w, h) * this.pegelAbstand - 6 * s : my + r0 + 120 * s;
      for (let i = 0; i < balken; i++) {
        const voll_ = i < an, hoehe = (voll_ ? 4 + Math.min(1, an - i) * 6 : 2) * s;
        ctx.fillStyle = voll_ ? this.rgba(0.9, 0.3) : this.rgba(0.14);
        ctx.fillRect(mx - breite / 2 + (i * breite) / balken, y - hoehe / 2, 1.6 * s, hoehe);
      }
    }

    // 7) HAL-Auge: Spektrum-Kranz, Metallgehaeuse, Glaslinse mit gluehender Pupille, Reflexe
    const gehaeuse = r0 + 16 * s, linse = r0;
    // Spektrum-Kranz: 64 feine Striche ums Gehaeuse, Laenge = Stimme bzw. Denk-Welle
    ctx.lineCap = "round";
    for (let i = 0; i < 64; i++) {
      const wert = this.segmente[i % this.segmente.length];
      const a = (i / 64) * voll - Math.PI / 2;
      const innen = gehaeuse + 7 * s, laenge = (2 + wert * 20) * s;
      ctx.strokeStyle = this.rgba(0.18 + wert * 0.8, wert * 0.4);
      ctx.lineWidth = 1.6 * s;
      ctx.beginPath();
      ctx.moveTo(mx + Math.cos(a) * innen, my + Math.sin(a) * innen);
      ctx.lineTo(mx + Math.cos(a) * (innen + laenge), my + Math.sin(a) * (innen + laenge));
      ctx.stroke();
    }

    ctx.globalCompositeOperation = "source-over";
    // Gehaeuse: dunkles gebuerstetes Metall
    g = ctx.createRadialGradient(mx, my - gehaeuse * 0.3, gehaeuse * 0.2, mx, my, gehaeuse);
    g.addColorStop(0, "#2a2b30"); g.addColorStop(0.75, "#141519"); g.addColorStop(1, "#060607");
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(mx, my, gehaeuse, 0, voll); ctx.fill();
    // Chromkante: oben hell, unten dunkel
    const chrom = ctx.createLinearGradient(mx, my - gehaeuse, mx, my + gehaeuse);
    chrom.addColorStop(0, "rgba(255,255,255,0.55)"); chrom.addColorStop(0.5, "rgba(120,120,130,0.25)"); chrom.addColorStop(1, "rgba(0,0,0,0.6)");
    ctx.strokeStyle = chrom; ctx.lineWidth = 2.4 * s;
    ctx.beginPath(); ctx.arc(mx, my, gehaeuse - 1.2 * s, 0, voll); ctx.stroke();
    ctx.strokeStyle = "rgba(0,0,0,0.9)"; ctx.lineWidth = 3 * s;
    ctx.beginPath(); ctx.arc(mx, my, linse + 1.5 * s, 0, voll); ctx.stroke();

    // Linse: schwarzes Glas, innen gluehend. Pupille weitet sich mit der Stimme, pulsiert beim Denken.
    const denkPuls = this.zustand === "denken" ? 0.5 + 0.5 * Math.sin(this.t * 7) : 0;
    const pupille = Math.min(0.62, 0.2 + this.pegel * 0.3 + atem * 0.03 + denkPuls * 0.1 + (aktiv ? 0.05 : 0));
    const dunkel = (f, a) => `rgba(${this.farbe[0] * f | 0},${this.farbe[1] * f | 0},${this.farbe[2] * f | 0},${a})`;
    g = ctx.createRadialGradient(mx, my, 0, mx, my, linse);
    g.addColorStop(0, this.rgba(1, 0.75));
    g.addColorStop(pupille * 0.35, this.rgba(1, 0.35));
    g.addColorStop(pupille, dunkel(0.95, 1));
    g.addColorStop(Math.min(0.9, pupille + 0.25), dunkel(0.35, 1));
    g.addColorStop(0.92, dunkel(0.08, 1));
    g.addColorStop(1, "rgba(0,0,0,1)");
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(mx, my, linse, 0, voll); ctx.fill();

    // Linsen-Elemente: feine konzentrische Ringe im Glas
    ctx.globalCompositeOperation = "lighter";
    for (const [f, a] of [[0.34, 0.16], [0.55, 0.1], [0.76, 0.07]]) {
      ctx.strokeStyle = this.rgba(a * (0.7 + energie * 0.6), 0.2);
      ctx.lineWidth = 1 * s;
      ctx.beginPath(); ctx.arc(mx, my, linse * f, 0, voll); ctx.stroke();
    }
    // Lichtschein der Pupille
    g = ctx.createRadialGradient(mx, my, 0, mx, my, linse * (pupille + 0.15));
    g.addColorStop(0, this.rgba(0.55 + energie * 0.35, 0.5));
    g.addColorStop(1, this.rgba(0));
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(mx, my, linse, 0, voll); ctx.fill();

    // Glasreflexe: weicher Glanz oben, heller Bogen links oben, zwei Lichtpunkte
    ctx.globalCompositeOperation = "source-over";
    ctx.save();
    ctx.beginPath(); ctx.arc(mx, my, linse, 0, voll); ctx.clip();
    g = ctx.createLinearGradient(mx, my - linse, mx, my);
    g.addColorStop(0, "rgba(255,255,255,0.13)"); g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.ellipse(mx, my - linse * 0.42, linse * 0.82, linse * 0.5, 0, 0, voll); ctx.fill();
    ctx.restore();
    ctx.strokeStyle = "rgba(255,255,255,0.38)"; ctx.lineWidth = 2.6 * s; ctx.lineCap = "round";
    ctx.beginPath(); ctx.arc(mx, my, linse * 0.8, Math.PI * 1.08, Math.PI * 1.36); ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255,0.75)";
    ctx.beginPath(); ctx.arc(mx - linse * 0.36, my - linse * 0.5, 2.6 * s, 0, voll); ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,0.3)";
    ctx.beginPath(); ctx.arc(mx + linse * 0.42, my + linse * 0.4, 1.6 * s, 0, voll); ctx.fill();
    ctx.globalCompositeOperation = "lighter";

    // 8) Schockwelle + Funken bei Aktionen
    if (this.blitz > 0) {
      ctx.strokeStyle = `rgba(255,255,255,${this.blitz * 0.8})`;
      ctx.lineWidth = (6 * this.blitz + 1) * s;
      ctx.beginPath(); ctx.arc(mx, my, r0 + (1 - this.blitz) * 170 * s, 0, voll); ctx.stroke();
    }
    for (const f of this.funken) {
      const r = r0 + f.r * s * 3;
      ctx.fillStyle = this.rgba(f.leben, 0.6);
      ctx.beginPath(); ctx.arc(mx + Math.cos(f.w) * r, my + Math.sin(f.w) * r, f.g * f.leben * 1.6 * s, 0, voll); ctx.fill();
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
