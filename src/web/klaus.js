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
    this.sog = 0;       // 0..1: Partikel werden beim Zuhoeren zur Mitte gezogen
    this.letzte = performance.now();
    this.ruhig = matchMedia("(prefers-reduced-motion: reduce)").matches;
    // Orbit-Partikel: Bahnradius als Faktor von r0, eigenes Tempo und Neigung
    this.teilchen = Array.from({ length: 48 }, () => ({
      winkel: Math.random() * Math.PI * 2,
      bahn: 1.35 + Math.random() * 0.9,
      tempo: (0.25 + Math.random() * 0.6) * (Math.random() < 0.5 ? -1 : 1),
      groesse: 0.6 + Math.random() * 1.6,
      neigung: 0.55 + Math.random() * 0.45,  // elliptische Bahn = leichter 3D-Eindruck
      phase: Math.random() * 6.3,
    }));
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

    const tempo = { aus: 0.12, start: 0.6, hoeren: 0.5, denken: 2.6, sprechen: 0.9, aktion: 1.6, fehler: 0.3 }[this.zustand] ?? 0.3;
    this.drehung += dt * tempo * (this.ruhig ? 0.2 : 1);
    this.sog += ((this.zustand === "hoeren" ? 0.35 + this.pegel * 0.4 : 0) - this.sog) * 0.06;

    for (const p of this.teilchen) p.winkel += dt * p.tempo * (0.4 + tempo * 1.4 + this.pegel * 2.5);
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
    const r0 = (60 + this.pegel * 20 + atem * 3) * s;
    const voll = Math.PI * 2;

    ctx.globalCompositeOperation = "lighter";

    // 1) Weiter Lichtschein
    let g = ctx.createRadialGradient(mx, my, r0 * 0.4, mx, my, r0 * 3.4);
    g.addColorStop(0, this.rgba(0.32 * energie));
    g.addColorStop(0.35, this.rgba(0.1 * energie));
    g.addColorStop(1, this.rgba(0));
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(mx, my, r0 * 3.4, 0, voll); ctx.fill();

    // 2) Orbit-Partikel mit Leuchtspur (elliptische Bahnen, beim Zuhoeren nach innen gezogen)
    for (const p of this.teilchen) {
      const bahn = r0 * (p.bahn - this.sog * (p.bahn - 1.05)) + Math.sin(this.t * 2 + p.phase) * 3 * s;
      const spur = 0.22 * Math.sign(p.tempo);
      const helligkeit = (aktiv ? 0.55 : 0.28) * (0.6 + 0.4 * Math.sin(this.t * 3 + p.phase));
      ctx.strokeStyle = this.rgba(helligkeit, 0.3);
      ctx.lineWidth = p.groesse * s;
      ctx.lineCap = "round";
      ctx.beginPath();
      for (let k = 0; k <= 6; k++) {
        const a = p.winkel - spur * (k / 6);
        const x = mx + Math.cos(a) * bahn, y = my + Math.sin(a) * bahn * p.neigung;
        k ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      }
      ctx.stroke();
      ctx.fillStyle = this.rgba(helligkeit * 1.4, 0.6);
      ctx.beginPath();
      ctx.arc(mx + Math.cos(p.winkel) * bahn, my + Math.sin(p.winkel) * bahn * p.neigung, p.groesse * 1.1 * s, 0, voll);
      ctx.fill();
    }

    // 2b) Radar-Sweep: ein rotierender Lichtfaecher hinter allem
    const sweepR = r0 + 118 * s, sweepWinkel = this.t * (aktiv ? 1.4 : 0.5);
    if (ctx.createConicGradient) {
      const kegel = ctx.createConicGradient(sweepWinkel, mx, my);
      kegel.addColorStop(0, this.rgba(aktiv ? 0.16 : 0.07));
      kegel.addColorStop(0.12, this.rgba(0));
      kegel.addColorStop(1, this.rgba(0));
      ctx.fillStyle = kegel;
      ctx.beginPath(); ctx.arc(mx, my, sweepR, 0, voll); ctx.fill();
      ctx.strokeStyle = this.rgba(aktiv ? 0.5 : 0.22, 0.3);
      ctx.lineWidth = 1 * s;
      ctx.beginPath(); ctx.moveTo(mx, my);
      ctx.lineTo(mx + Math.cos(sweepWinkel) * sweepR, my + Math.sin(sweepWinkel) * sweepR); ctx.stroke();
    }

    // 2c) Beschriftung: Gradzahlen und Sektor-Namen am Aussenrand (nur bei genug Platz)
    if (s > 0.55) {
      ctx.fillStyle = this.rgba(aktiv ? 0.7 : 0.4, 0.2);
      ctx.font = `${Math.round(9 * s)}px Consolas, monospace`;
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      const textR = r0 + 128 * s;
      for (let grad = 0; grad < 360; grad += 30) {
        const a = (grad / 180) * Math.PI - Math.PI / 2 + this.drehung * 0.25;
        ctx.fillText(String(grad).padStart(3, "0"), mx + Math.cos(a) * textR, my + Math.sin(a) * textR);
      }
      ctx.font = `bold ${Math.round(10 * s)}px Consolas, monospace`;
      ["AUDIO", "NEURAL", "UPLINK", "CORE"].forEach((name, i) => {
        const a = (i / 4) * voll + Math.PI / 4 - this.drehung * 0.12;
        ctx.fillStyle = this.rgba(aktiv ? 0.85 : 0.45, 0.3);
        ctx.fillText(name, mx + Math.cos(a) * (r0 + 97 * s), my + Math.sin(a) * (r0 + 97 * s));
      });
    }

    // 3) Skala aussen (90 Striche, jeder 5. lang)
    const skala = r0 + 86 * s;
    ctx.lineWidth = 1 * s;
    for (let i = 0; i < 90; i++) {
      const a = (i / 90) * voll + this.drehung * 0.25, lang = i % 5 === 0;
      ctx.strokeStyle = this.rgba(lang ? 0.5 : 0.18);
      ctx.beginPath();
      ctx.moveTo(mx + Math.cos(a) * skala, my + Math.sin(a) * skala);
      ctx.lineTo(mx + Math.cos(a) * (skala + (lang ? 10 : 4) * s), my + Math.sin(a) * (skala + (lang ? 10 : 4) * s));
      ctx.stroke();
    }

    // 4) Gegenlaeufige Boegen mit Endpunkten
    [[r0 + 62 * s, 1, 1.1, 2.2], [r0 + 70 * s, -1.4, 0.7, 1.4], [r0 + 104 * s, 0.6, 0.45, 1]].forEach(([r, v, spanne, breite], i) => {
      ctx.strokeStyle = this.rgba(aktiv ? 0.75 - i * 0.18 : 0.32 - i * 0.07);
      ctx.lineWidth = breite * s;
      for (const versatz of [0, Math.PI]) {
        const a = this.drehung * v + versatz;
        ctx.beginPath(); ctx.arc(mx, my, r, a, a + spanne); ctx.stroke();
        ctx.fillStyle = this.rgba(aktiv ? 0.9 : 0.4, 0.4);
        ctx.beginPath(); ctx.arc(mx + Math.cos(a + spanne) * r, my + Math.sin(a + spanne) * r, 2.2 * s, 0, voll); ctx.fill();
      }
    });
    ctx.setLineDash([3 * s, 7 * s]);
    ctx.lineDashOffset = -this.drehung * 30 * s;
    ctx.strokeStyle = this.rgba(aktiv ? 0.35 : 0.14);
    ctx.lineWidth = 1 * s;
    ctx.beginPath(); ctx.arc(mx, my, r0 + 112 * s, 0, voll); ctx.stroke();
    ctx.setLineDash([]);

    // 5) Reaktor-Ring: 48 Segmente wie ein Equalizer
    const ringR = r0 + 30 * s, segBreite = (voll / this.segmente.length) * 0.62;
    for (let i = 0; i < this.segmente.length; i++) {
      const wert = this.segmente[i];
      const a = (i / this.segmente.length) * voll - this.drehung * 0.6;
      ctx.strokeStyle = this.rgba(0.12 + wert * 0.85, wert * 0.5);
      ctx.lineWidth = (5 + wert * 9) * s;
      ctx.beginPath(); ctx.arc(mx, my, ringR + wert * 5 * s, a, a + segBreite); ctx.stroke();
    }

    // 5b) Klang-Blob: gefuellte Flaeche Hauptfarbe -> Zweitfarbe, waechst mit der Stimme
    const blobAusschlag = (aktiv ? 4 + this.pegel * 42 : 2 + atem * 2) * s;
    const zweit = ORB_FARBEN.denken;
    const verlauf = ctx.createLinearGradient(mx - r0 * 1.4, my - r0 * 1.4, mx + r0 * 1.4, my + r0 * 1.4);
    verlauf.addColorStop(0, this.rgba(aktiv ? 0.34 : 0.12));
    verlauf.addColorStop(1, `rgba(${zweit[0]},${zweit[1]},${zweit[2]},${aktiv ? 0.3 : 0.08})`);
    ctx.fillStyle = verlauf;
    ctx.beginPath();
    for (let k = 0; k <= 90; k++) {
      const a = (k / 90) * voll;
      const v = Math.sin(a * 2 + this.t * 1.7) * 0.55 + Math.sin(a * 4 - this.t * 2.9) * 0.3 + Math.sin(a * 7 + this.t * 4.3) * 0.15;
      const r = r0 + 14 * s + Math.max(0, v) * blobAusschlag;
      k ? ctx.lineTo(mx + Math.cos(a) * r, my + Math.sin(a) * r) : ctx.moveTo(mx + Math.cos(a) * r, my + Math.sin(a) * r);
    }
    ctx.closePath();
    ctx.fill();

    // 6) Stimm-Welle: glühende, sich verformende Kontur um den Kern
    for (const [versatz, alpha, breite] of [[0, 0.16, 9], [0, 0.95, 2.4], [1.7, 0.45, 1.2]]) {
      ctx.strokeStyle = this.rgba(aktiv ? alpha : alpha * 0.45, 0.35);
      ctx.lineWidth = breite * s;
      ctx.beginPath();
      for (let k = 0; k <= 120; k++) {
        const a = (k / 120) * voll;
        const verformung = Math.sin(a * 3 + this.t * 2.3 + versatz) * 0.5 + Math.sin(a * 5 - this.t * 3.7 + versatz) * 0.35
          + Math.sin(a * 9 + this.t * 6.1) * 0.15;
        const ausschlag = (aktiv ? 2 + this.pegel * 20 : 1.5 + atem * 1.5) * s;
        const r = r0 + 10 * s + verformung * ausschlag;
        const x = mx + Math.cos(a) * r, y = my + Math.sin(a) * r;
        k ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();
    }

    // 6b) Fadenkreuz-Klammern links/rechts mit Datenpunkt + Audio-Pegel als Segmentbalken (nur bei genug Platz)
    if (s > 0.4) {
      const ax = r0 + 150 * s;
      ctx.strokeStyle = this.rgba(aktiv ? 0.75 : 0.4, 0.2);
      ctx.fillStyle = this.rgba(aktiv ? 0.9 : 0.5, 0.4);
      ctx.lineWidth = 1.2 * s;
      for (const seite of [-1, 1]) {
        const x = mx + seite * ax;
        ctx.beginPath();  // Klammer [ bzw. ]
        ctx.moveTo(x - seite * 8 * s, my - 22 * s); ctx.lineTo(x, my - 22 * s); ctx.lineTo(x, my + 22 * s); ctx.lineTo(x - seite * 8 * s, my + 22 * s);
        ctx.stroke();
        ctx.beginPath(); ctx.arc(x - seite * 22 * s, my, 3 * s, 0, voll); ctx.fill();  // Datenpunkt
        ctx.beginPath(); ctx.moveTo(x - seite * 22 * s, my); ctx.lineTo(x - seite * 46 * s, my); ctx.stroke();
      }
      // Audio-Pegel: 24 Segmente unter dem Orb
      const segmente = 24, breite = (this.pegelAbstand ? 120 : 150) * s, an = Math.round(this.pegel * segmente);
      const y = this.pegelAbstand ? my + Math.min(w, h) * this.pegelAbstand - 6 * s : my + r0 + 156 * s;
      for (let i = 0; i < segmente; i++) {
        ctx.fillStyle = i < an ? this.rgba(0.95, i / segmente * 0.5) : this.rgba(0.14);
        ctx.fillRect(mx - breite / 2 + (i * breite) / segmente, y, breite / segmente - 2 * s, 7 * s);
      }
      ctx.fillStyle = this.rgba(aktiv ? 0.7 : 0.4, 0.2);
      ctx.font = `${Math.round(8.5 * s)}px Consolas, monospace`;
      ctx.textAlign = "center";
      ctx.fillText(`AUDIO LEVEL · ${String(Math.round(this.pegel * 100)).padStart(3, "0")}`, mx, y + 17 * s);
    }

    // 7) Plasma-Kern: Grundkugel + drei kreisende Lichtwolken, auf den Kreis beschnitten
    ctx.save();
    ctx.beginPath(); ctx.arc(mx, my, r0, 0, voll); ctx.clip();
    ctx.globalCompositeOperation = "source-over";
    g = ctx.createRadialGradient(mx, my, 0, mx, my, r0);
    g.addColorStop(0, this.rgba(0.95, 0.55));
    g.addColorStop(0.55, this.rgba(0.75));
    g.addColorStop(1, this.rgba(0.35, -0.6));
    ctx.fillStyle = g;
    ctx.fillRect(mx - r0, my - r0, r0 * 2, r0 * 2);
    ctx.globalCompositeOperation = "lighter";
    for (let i = 0; i < 3; i++) {
      const a = this.t * (0.7 + i * 0.45) * (i % 2 ? -1 : 1) + i * 2.1;
      const versatz = r0 * (0.32 + 0.12 * Math.sin(this.t * 1.3 + i));
      const bx = mx + Math.cos(a) * versatz, by = my + Math.sin(a) * versatz;
      const wolke = ctx.createRadialGradient(bx, by, 0, bx, by, r0 * 0.75);
      wolke.addColorStop(0, this.rgba(0.55 * energie + 0.15, 0.7));
      wolke.addColorStop(1, this.rgba(0));
      ctx.fillStyle = wolke;
      ctx.fillRect(mx - r0, my - r0, r0 * 2, r0 * 2);
    }
    // heller Kernpunkt
    g = ctx.createRadialGradient(mx - r0 * 0.18, my - r0 * 0.22, 0, mx, my, r0 * 0.55);
    g.addColorStop(0, `rgba(255,255,255,${0.75 + this.pegel * 0.25})`);
    g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g;
    ctx.fillRect(mx - r0, my - r0, r0 * 2, r0 * 2);
    ctx.restore();

    // Arc-Reactor-Dreieck (Mark VI, Spitze nach unten) im Kern: aussen kraeftig, innen fein
    const dreieck = (rad) => {
      ctx.beginPath();
      for (let k = 0; k < 3; k++) {
        const a = Math.PI / 2 + (k * voll) / 3;
        k ? ctx.lineTo(mx + Math.cos(a) * rad, my + Math.sin(a) * rad) : ctx.moveTo(mx + Math.cos(a) * rad, my + Math.sin(a) * rad);
      }
      ctx.closePath();
    };
    dreieck(r0 * 0.7);
    ctx.fillStyle = this.rgba(0.16 + this.pegel * 0.2, 0.6);
    ctx.fill();
    ctx.strokeStyle = this.rgba(0.95, 0.75);
    ctx.lineWidth = 3.2 * s;
    ctx.lineJoin = "round";
    ctx.stroke();
    dreieck(r0 * 0.44);
    ctx.strokeStyle = this.rgba(0.7, 0.6);
    ctx.lineWidth = 1.3 * s;
    ctx.stroke();

    // Kernrand
    ctx.strokeStyle = this.rgba(0.85, 0.5);
    ctx.lineWidth = 1.5 * s;
    ctx.beginPath(); ctx.arc(mx, my, r0, 0, voll); ctx.stroke();

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
