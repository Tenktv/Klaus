// Klaus Core: Zustandsmaschine + Effekte rund um den Orb (Zuhoeren, Denken, Ausfuehren, Freigabe, Fertig).
// Python meldet einfache Zustaende (aus, hoeren, denken, sprechen, aktion, fehler, freigabe, fertig);
// coreSchritt() macht daraus die Core-Zustaende inkl. Uebergaengen. Gezeichnet wird auf einer eigenen
// Canvas ueber dem Orb - nur solange etwas zu sehen ist, und nie, wenn das Panel verdeckt ist.

const CORE_AUS_PYTHON = {
  aus: "IDLE", start: "LISTENING", hoeren: "LISTENING", denken: "THINKING", sprechen: "SPEAKING",
  aktion: "EXECUTING", fehler: "ERROR", freigabe: "AWAITING_AUTH", fertig: "DONE",
};
// orb: Zustand fuer KlausOrb, modus: Kopfzeile, label: grosser Zustandstext; auge: Farbe fuer Halo/Buehne (CSS --eye)
const CORE_ZUSTAENDE = {
  IDLE:          { orb: "aus",      modus: "normal", label: "STANDBY" },
  LISTENING:     { orb: "hoeren",   modus: "normal", label: "LISTENING" },
  THINKING:      { orb: "denken",   modus: "klaus",  label: "THINKING" },
  SPEAKING:      { orb: "sprechen", modus: "klaus",  label: "RESPONDING" },
  EXECUTING:     { orb: "aktion",   modus: "klaus",  label: "EXECUTING" },
  AWAITING_AUTH: { orb: "freigabe", modus: "klaus",  label: "AWAITING AUTH" },
  DONE:          { orb: "fertig",   modus: "klaus",  label: "COMPLETE" },
  ERROR:         { orb: "fehler",   modus: "normal", label: "FAULT" },
};
const DENK_PHASEN = ["PARSING INTENT", "QUERYING", "SYNTHESIZING"];
const PHASE_MS = 1100;
const MIN_AUSFUEHREN_MS = 900;   // "EXECUTING" bleibt mindestens so lange sichtbar
const FERTIG_MS = 1400;          // danach "COMPLETE" mit Ring-Burst


// Reiner Uebergang (zustand, ereignis) -> zustand. Kein DOM, damit er leicht pruefbar bleibt.
// zustand: { name, seit, danach }  ereignis: { typ: "melde", wert, jetzt } | { typ: "zeit", jetzt }
function coreSchritt(z, e) {
  if (e.typ === "melde") {
    const ziel = CORE_AUS_PYTHON[e.wert] || "IDLE";
    if (ziel === z.name && !z.danach) return z;
    if (z.name === "EXECUTING" && ziel !== "EXECUTING") {
      // erst ausfuehren lassen, dann "fertig" zeigen (ausser es geht direkt weiter mit Denken/Freigabe/Fehler)
      if (["THINKING", "AWAITING_AUTH", "ERROR"].includes(ziel)) return { name: ziel, seit: e.jetzt, danach: null };
      if (e.jetzt - z.seit < MIN_AUSFUEHREN_MS) return { ...z, danach: ziel };
      return { name: "DONE", seit: e.jetzt, danach: ziel };
    }
    if (z.name === "DONE" && !["THINKING", "AWAITING_AUTH", "EXECUTING", "ERROR"].includes(ziel)) return { ...z, danach: ziel };
    return { name: ziel, seit: e.jetzt, danach: null };
  }
  if (e.typ === "zeit") {
    if (z.name === "EXECUTING" && z.danach && e.jetzt - z.seit >= MIN_AUSFUEHREN_MS) {
      return { name: "DONE", seit: e.jetzt, danach: z.danach };
    }
    if (z.name === "DONE" && e.jetzt - z.seit >= FERTIG_MS) return { name: z.danach || "IDLE", seit: e.jetzt, danach: null };
  }
  return z;
}

class KlausCore {
  constructor(buehne, orb, platz = 1) {
    this.buehne = buehne;
    this.orb = orb;
    this.platz = platz;
    this.z = { name: "IDLE", seit: performance.now(), danach: null };
    this.ruhig = matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.fx = el("canvas", "core-fx");
    this.ctx = this.fx.getContext("2d");
    const auge = buehne.querySelector(".auge-platz");
    if (auge) auge.after(this.fx); else buehne.append(this.fx);
    this.hud = el("div", "core-hud");
    this.hud.innerHTML = `<div class="core-kopf"><span class="core-name">KLAUS CORE</span><span class="core-trenner">//</span>
      <span class="core-modus" data-text="NORMAL MODE">NORMAL MODE</span></div>
      <div class="core-zustand"></div><div class="core-phasen"></div><div class="core-ziel"></div>`;
    buehne.append(this.hud);
    this.modusEl = this.hud.querySelector(".core-modus");
    this.labelEl = this.hud.querySelector(".core-zustand");
    this.phasenEl = this.hud.querySelector(".core-phasen");
    this.zielEl = this.hud.querySelector(".core-ziel");
    this.sperrText = null;   // "STUMM" / "MIKROFON AUS" ersetzt den Zustandstext
    this.teilchen = [];    // Datenstrom von aussen zum Kern (Denken)
    this.wellen = [];      // Ringe nach aussen (Zuhoeren) bzw. Burst (Fertig)
    this.pegel = 0;
    this.simuliert = false;   // Debug: Mikro-Pegel vortaeuschen
    this.phase = -1;
    this.t = 0;
    this.letzte = performance.now();
    this.letzteWelle = 0;
    this.leer = true;
    this.ruheBild = "";      // Groesse, fuer die das stille Sternbild zuletzt gezeichnet wurde
    // Denken als Graph: Schritte (Knoten im Reaktor) und Werkzeug-Aufrufe (Blaetter weiter aussen)
    this.gedanken = new Map();   // id -> { id, label, status, eltern, geboren, zuletzt, blatt }
    // Stilles Sternbild um den Reaktor (graphify-Look): feste Punkte in Polarkoordinaten, Radius in Reaktor-Radien
    this.sterne = [];
    let saat = 7;
    const zufall = () => ((saat = (saat * 9301 + 49297) % 233280) / 233280);
    while (this.sterne.length < 46) {
      const w = zufall() * Math.PI * 2, r = 1.04 + zufall() * 0.5;
      if (Math.abs(Math.sin(w)) > 0.9 && Math.sin(w) < 0) continue;  // nicht in den Kopf (Zustandstext)
      this.sterne.push({ w, r, g: 0.8 + zufall() * 1.6, f: zufall() < 0.25 ? 1 : zufall() < 0.4 ? 2 : 0 });
    }
    this.sternKanten = [];
    this.sterne.forEach((a, i) => {
      const nah = this.sterne.map((b, j) => [j, Math.hypot(Math.cos(a.w) * a.r - Math.cos(b.w) * b.r, Math.sin(a.w) * a.r - Math.sin(b.w) * b.r)])
        .filter(([j]) => j !== i).sort((x, y) => x[1] - y[1]).slice(0, 2);
      for (const [j, d] of nah) if (d < 0.42 && !this.sternKanten.some(([x, y]) => x === j && y === i)) this.sternKanten.push([i, j]);
    });
    this.anwenden(null);
    requestAnimationFrame((t) => this.tick(t));
  }

  // Stumm/Mikro aus: grosser Text zeigt das statt des Zustands (null = normal)
  sperre(text) {
    if (text === this.sperrText) return;
    this.sperrText = text;
    this.tippe(this.labelEl, text || CORE_ZUSTAENDE[this.z.name].label);
  }

  melde(wert) { this.wechsel(coreSchritt(this.z, { typ: "melde", wert, jetzt: performance.now() })); }
  setPegel(p) { if (!this.simuliert) this.pegel = p; }
  // Woran Klaus gerade arbeitet (z. B. Werkzeugname) - erscheint als klesro://-Zeile
  setZiel(text) { this.tippe(this.zielEl, text ? `klesro://${text}` : ""); }

  wechsel(neu) {
    if (neu === this.z) return;
    const alt = this.z.name;
    this.z = neu;
    if (alt !== neu.name) this.anwenden(alt);
  }

  anwenden(alt) {
    const name = this.z.name, def = CORE_ZUSTAENDE[name];
    this.buehne.dataset.core = name;
    document.body.dataset.core = name;   // CSS: Endlos-Animationen nur, wenn Klaus nicht ruht
    document.body.dataset.eye = { EXECUTING: "ok", DONE: "ok", AWAITING_AUTH: "auth", ERROR: "fehler" }[name] || "basis";
    document.body.classList.toggle("core-auth", name === "AWAITING_AUTH");
    this.orb.setZustand(def.orb);
    const modus = def.modus === "klaus" ? "KLAUS MODE ACTIVE" : "NORMAL MODE";
    if (this.modusEl.dataset.text !== modus) this.glitch(modus);
    this.phase = -1;
    this.phasenEl.classList.toggle("an", name === "THINKING");
    if (name !== "THINKING") this.phasenEl.innerHTML = "";
    this.tippe(this.labelEl, this.sperrText || def.label);
    if (name === "DONE") this.burst();
    if (name === "IDLE") this.setZiel("");
    this.leer = false;
  }

  glitch(text) {
    const m = this.modusEl;
    m.dataset.text = text;
    if (this.ruhig) { m.textContent = text; return; }
    m.classList.remove("glitch"); void m.offsetWidth; m.classList.add("glitch");
    // waehrend des Glitches flackern Zufallszeichen, dann steht der neue Text
    let n = 0;
    clearInterval(this._glitchTimer);
    this._glitchTimer = setInterval(() => {
      n++;
      m.textContent = n < 7 ? text.replace(/[A-Z]/g, (c) => (Math.random() < 0.45 ? "█▓▒░#%&@"[Math.random() * 8 | 0] : c)) : text;
      if (n >= 7) clearInterval(this._glitchTimer);
    }, 55);
    setTimeout(() => m.classList.remove("glitch"), 650);
  }

  tippe(ziel, text) {
    clearInterval(ziel._tipp);
    if (this.ruhig || !text) { ziel.textContent = text; return; }
    let i = 0;
    ziel.textContent = "";
    ziel._tipp = setInterval(() => {
      i += 1;
      ziel.textContent = text.slice(0, i) + (i < text.length ? "▌" : "");
      if (i >= text.length) clearInterval(ziel._tipp);
    }, 24);
  }

  phasenZeile(index) {
    this.phasenEl.innerHTML = DENK_PHASEN.map((p, i) =>
      `<span class="${i < index ? "fertig" : i === index ? "an" : ""}">${p}</span>`).join('<i class="pfeil">→</i>');
  }

  // ------------------------------------------------------------------ Denken als Graph
  // Schritt anlegen/aendern: status pending|running|complete|warten|fehler|uebersprungen
  gedanke(id, label, status = "pending") {
    const g = this.gedanken.get(id);
    if (g) { g.label = label || g.label; if (g.status !== status) { g.status = status; g.wechsel = performance.now(); } g.zuletzt = performance.now(); return; }
    this.gedanken.set(id, { id, label, status, eltern: null, geboren: performance.now(), zuletzt: performance.now(), wechsel: performance.now() });
  }

  // Werkzeug-Aufruf als Blatt am laufenden Schritt (sonst direkt am Kern); haelt hoechstens 4 je Schritt
  gedankeBlatt(text) {
    const pfad = String(text || "").replace(/^klesro:\/\//, "").split(" ")[0].slice(0, 26);
    if (!pfad) return;
    const schritte = [...this.gedanken.values()].filter((g) => !g.blatt);
    const eltern = (schritte.find((g) => g.status === "running") || schritte.at(-1) || null);
    const id = `b${performance.now().toFixed(0)}${Math.random().toString(36).slice(2, 5)}`;
    this.gedanken.set(id, { id, label: pfad, status: "complete", eltern: eltern ? eltern.id : null, blatt: true,
                            geboren: performance.now(), zuletzt: performance.now(), wechsel: performance.now() });
    const geschwister = [...this.gedanken.values()].filter((g) => g.blatt && g.eltern === (eltern ? eltern.id : null));
    while (geschwister.length > 4) this.gedanken.delete(geschwister.shift().id);
  }

  // Alles ausblenden (langsam, ueber "zuletzt")
  gedankenLeeren() { for (const g of this.gedanken.values()) g.weg = performance.now(); }

  burst() { for (let i = 0; i < 3; i++) this.wellen.push({ r: 0, leben: 1, verz: i * 0.14, breit: 3 - i * 0.7, burst: true }); }

  // ------------------------------------------------------------------ Animation
  tick(jetzt) {
    if (window.klausPause || document.hidden) {
      this.letzte = jetzt;
      setTimeout(() => requestAnimationFrame((t) => this.tick(t)), 500);
      return;
    }
    const dt = Math.min(0.05, (jetzt - this.letzte) / 1000);
    this.letzte = jetzt;
    this.t += dt;
    this.wechsel(coreSchritt(this.z, { typ: "zeit", jetzt }));
    const name = this.z.name;

    if (name === "THINKING" && !this.ruhig) {
      const idx = Math.min(DENK_PHASEN.length - 1, Math.floor((jetzt - this.z.seit) / PHASE_MS));
      if (idx !== this.phase) { this.phase = idx; this.phasenZeile(idx); }
      this.orb.setPegel(0.22 + 0.12 * Math.sin(this.t * 5.3) * Math.sin(this.t * 2.1));
    } else if (name === "THINKING" && this.phase < 0) { this.phase = 0; this.phasenZeile(0); }
    if (name === "AWAITING_AUTH") this.orb.setPegel(0.18 + 0.18 * (0.5 + 0.5 * Math.sin(this.t * 5)));
    if (this.simuliert && name === "LISTENING") {
      this.pegel = Math.max(0, 0.35 + 0.3 * Math.sin(this.t * 7.3) * Math.sin(this.t * 2.9) + (Math.random() - 0.5) * 0.25);
      this.orb.setPegel(this.pegel);
    }

    // Blaetter verblassen nach 25 s, ausgeblendete Gedanken nach 1,2 s
    for (const g of this.gedanken.values()) {
      if ((g.weg && jetzt - g.weg > 1200) || (g.blatt && jetzt - g.geboren > 25000)) this.gedanken.delete(g.id);
    }
    const aktiv = ["THINKING", "EXECUTING", "AWAITING_AUTH", "LISTENING", "DONE"].includes(name)
      || this.teilchen.length || this.wellen.length || this.gedanken.size;
    if (!aktiv || this.ruhig) {
      // Ruhe: das Sternbild einmal still zeichnen, dann nichts mehr (kaum CPU) - neu nur bei anderer Groesse
      const groesse = `${this.fx.clientWidth}x${this.fx.clientHeight}`;
      if (!this.leer || this.ruheBild !== groesse) { this.zeichne(0, jetzt, true); this.ruheBild = groesse; this.leer = true; }
      setTimeout(() => requestAnimationFrame((t) => this.tick(t)), 120);
      return;
    }
    this.leer = false;
    this.zeichne(dt, jetzt);
    requestAnimationFrame((t) => this.tick(t));
  }

  zeichne(dt, jetzt, still = false) {
    const c = this.fx, ctx = this.ctx, dpr = Math.min(1.5, window.devicePixelRatio || 1);
    const w = c.clientWidth, h = c.clientHeight;
    if (!w || !h) return;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    // Mitte und Groesse des echten Auges (Canvas des Orbs) relativ zur Effekt-Canvas
    const fr = c.getBoundingClientRect(), or = this.orb.c.getBoundingClientRect(), geo = this.orb.geometrie();
    const mx = or.left - fr.left + geo.mx, my = or.top - fr.top + geo.my, s = geo.gehaeuse / 290;
    // aussen nie ueber den Rand der Canvas hinaus, sonst werden Ringe sichtbar gerade abgeschnitten
    const rand = Math.min(mx, my, w - mx, h - my) - 6;
    const kern = geo.linse, aussen = Math.min(geo.gehaeuse * 1.3, rand / 1.25), voll = Math.PI * 2, name = this.z.name;
    const farbe = (a, hell = 0) => this.orb.rgba(a, hell);
    ctx.globalCompositeOperation = "lighter";

    if (still) {
      this.zeichneNetz(ctx, mx, my, geo, w, h, jetzt, true);
      ctx.globalCompositeOperation = "source-over";
      return;
    }

    // --- Denken: wenige feine Lichtstriche fliessen ins Auge
    if (name === "THINKING" && this.teilchen.length < 26 && Math.random() < dt * 24) {
      this.teilchen.push({ w: Math.random() * voll, r: aussen * (1.05 + Math.random() * 0.35), v: (70 + Math.random() * 90) * s,
                           drall: (Math.random() - 0.5) * 0.6, laenge: (10 + Math.random() * 18) * s });
    }
    ctx.lineCap = "round";
    for (const p of this.teilchen) {
      const zug = 1 + (aussen - p.r) / aussen * 1.6;  // je naeher am Kern, desto schneller
      p.r -= p.v * zug * dt;
      p.w += p.drall * dt;
      const nah = Math.max(0, Math.min(1, (aussen * 1.3 - p.r) / (aussen * 1.3 - kern)));
      ctx.strokeStyle = farbe(0.08 + nah * 0.5, 0.35);
      ctx.lineWidth = (0.7 + nah * 0.9) * s;
      ctx.beginPath();
      ctx.moveTo(mx + Math.cos(p.w) * (p.r + p.laenge), my + Math.sin(p.w) * (p.r + p.laenge));
      ctx.lineTo(mx + Math.cos(p.w) * p.r, my + Math.sin(p.w) * p.r);
      ctx.stroke();
    }
    this.teilchen = this.teilchen.filter((p) => p.r > kern * 1.02);

    // --- Ausfuehren: Scan-Linie von oben nach unten
    if (name === "EXECUTING") {
      const rs = geo.gehaeuse * 0.96;  // nur ueber dem Auge, nicht quer durchs Panel
      const k = ((jetzt - this.z.seit) / 1000 / 0.9) % 1, y = my - rs + k * rs * 2;
      const breite = Math.sqrt(Math.max(0, rs * rs - (y - my) * (y - my)));
      const band = ctx.createLinearGradient(0, y - 26 * s, 0, y + 3 * s);
      band.addColorStop(0, farbe(0)); band.addColorStop(1, farbe(0.32, 0.3));
      ctx.fillStyle = band;
      ctx.fillRect(mx - breite, y - 26 * s, breite * 2, 29 * s);
      ctx.strokeStyle = farbe(0.95, 0.6); ctx.lineWidth = 1.4 * s;
      ctx.beginPath(); ctx.moveTo(mx - breite, y); ctx.lineTo(mx + breite, y); ctx.stroke();
    }

    // --- Freigabe: Schloss-Ring aus drei Segmenten, pulsiert
    if (name === "AWAITING_AUTH") {
      const puls = 0.5 + 0.5 * Math.sin(this.t * 5), r = kern + 48 * s;
      ctx.lineWidth = (3 + puls * 2) * s;
      for (let i = 0; i < 3; i++) {
        const a = this.t * 0.6 + i * (voll / 3);
        ctx.strokeStyle = farbe(0.5 + puls * 0.45, 0.25);
        ctx.beginPath(); ctx.arc(mx, my, r, a, a + voll / 3 - 0.35); ctx.stroke();
      }
      ctx.setLineDash([2 * s, 6 * s]);
      ctx.strokeStyle = farbe(0.35 + puls * 0.3);
      ctx.lineWidth = 1 * s;
      ctx.beginPath(); ctx.arc(mx, my, aussen - 10 * s, 0, voll); ctx.stroke();
      ctx.setLineDash([]);
    }

    // --- Zuhoeren: Wellen im Takt der Stimme / Fertig: Ring-Burst
    if (name === "LISTENING" && this.pegel > 0.22 && jetzt - this.letzteWelle > 240) {
      this.letzteWelle = jetzt;
      this.wellen.push({ r: 0, leben: 1, verz: 0, breit: 1 + this.pegel * 2 });
    }
    for (const welle of this.wellen) {
      if (welle.verz > 0) { welle.verz -= dt; continue; }
      welle.leben -= dt * (welle.burst ? 0.9 : 1.2);
      welle.r = (1 - welle.leben) * (welle.burst ? Math.min(aussen * 1.25, rand - kern) : aussen - kern);
      ctx.strokeStyle = farbe(Math.max(0, welle.leben) * (welle.burst ? 0.95 : 0.5), welle.burst ? 0.6 : 0.2);
      ctx.lineWidth = welle.breit * s * (welle.burst ? 2 : 1);
      ctx.beginPath(); ctx.arc(mx, my, kern + welle.r, 0, voll); ctx.stroke();
    }
    this.wellen = this.wellen.filter((welle) => welle.leben > 0);
    this.zeichneNetz(ctx, mx, my, geo, w, h, jetzt, still);
    ctx.globalCompositeOperation = "source-over";
  }

  // Sternbild um den Reaktor + Gedanken-Graph im Reaktor
  zeichneNetz(ctx, mx, my, geo, w, h, jetzt, still) {
    const R = geo.gehaeuse / 0.95, voll = Math.PI * 2, farbe = (a, hell = 0) => this.orb.rgba(a, hell);
    const dreh = still ? 0 : this.t * 0.012;
    const FARBEN = [(a) => farbe(a, 0.2), (a) => `rgba(255,255,255,${a})`, (a) => `rgba(255,190,90,${a})`];
    // --- Sternbild
    const pos = this.sterne.map((st) => [mx + Math.cos(st.w + dreh) * st.r * R, my + Math.sin(st.w + dreh) * st.r * R]);
    ctx.lineWidth = 0.7;
    ctx.strokeStyle = farbe(0.16, 0.3);
    ctx.beginPath();
    for (const [i, j] of this.sternKanten) { ctx.moveTo(pos[i][0], pos[i][1]); ctx.lineTo(pos[j][0], pos[j][1]); }
    ctx.stroke();
    this.sterne.forEach((st, i) => {
      const funkeln = still ? 1 : 0.7 + 0.3 * Math.sin(this.t * 1.3 + i);
      ctx.fillStyle = FARBEN[st.f](0.55 * funkeln);
      ctx.beginPath(); ctx.arc(pos[i][0], pos[i][1], st.g, 0, voll); ctx.fill();
    });
    if (!this.gedanken.size) return;

    // --- Gedanken: Schritte gleichmaessig im Reaktor (zwischen Portal und Aussenring), Blaetter weiter aussen
    const FARBE = { running: null, complete: "60,245,155", warten: "255,174,43", fehler: "255,61,90" };
    const schritte = [...this.gedanken.values()].filter((g) => !g.blatt);
    const lage = new Map();
    schritte.forEach((g, i) => {
      const winkel = -Math.PI / 2 + ((i + 0.5) / Math.max(schritte.length, 1)) * voll + (still ? 0 : this.t * 0.02);
      lage.set(g.id, [mx + Math.cos(winkel) * R * 0.68, my + Math.sin(winkel) * R * 0.68, winkel]);
    });
    const blaetterJe = new Map();
    for (const g of this.gedanken.values()) if (g.blatt) { const k = g.eltern || "_"; blaetterJe.set(k, [...(blaetterJe.get(k) || []), g]); }
    for (const [eltern, liste] of blaetterJe) {
      const basis = eltern !== "_" && lage.get(eltern) ? lage.get(eltern)[2] : -Math.PI / 2;
      liste.forEach((g, i) => {
        const winkel = basis + (i - (liste.length - 1) / 2) * 0.16;
        lage.set(g.id, [mx + Math.cos(winkel) * R * 0.9, my + Math.sin(winkel) * R * 0.9, winkel]);
      });
    }
    ctx.font = "600 11px 'Barlow SC', 'Segoe UI', sans-serif";
    ctx.textBaseline = "middle";
    for (const g of this.gedanken.values()) {
      const p = lage.get(g.id);
      if (!p) continue;
      const alter = jetzt - g.geboren, ein = Math.min(1, alter / 450), aus = g.weg ? Math.max(0, 1 - (jetzt - g.weg) / 1200) : 1;
      const blattAus = g.blatt ? Math.min(1, Math.max(0, (25000 - alter) / 4000)) : 1;
      const a = ein * aus * blattAus;
      const rgb = FARBE[g.status];
      const c = (al) => (rgb ? `rgba(${rgb},${al})` : farbe(al, 0.3));
      // Verbindung: Schritt <- Portal-Ring, Blatt <- Schritt (waechst beim Entstehen)
      const von = g.blatt && g.eltern && lage.get(g.eltern) ? lage.get(g.eltern)
        : [mx + Math.cos(p[2]) * R * 0.5, my + Math.sin(p[2]) * R * 0.5];
      const zx = von[0] + (p[0] - von[0]) * ein, zy = von[1] + (p[1] - von[1]) * ein;
      ctx.strokeStyle = c(0.5 * a); ctx.lineWidth = g.blatt ? 0.8 : 1.3;
      ctx.beginPath(); ctx.moveTo(von[0], von[1]); ctx.lineTo(zx, zy); ctx.stroke();
      if (ein < 1) continue;
      // Knoten: laufend pulsiert, Wechsel blitzt kurz auf
      const puls = g.status === "running" && !still ? 0.5 + 0.5 * Math.sin(this.t * 6) : 0;
      const blitz = Math.max(0, 1 - (jetzt - g.wechsel) / 600);
      const r = (g.blatt ? 2.4 : 5) + puls * 2 + blitz * 4;
      ctx.fillStyle = c(0.18 * a); ctx.beginPath(); ctx.arc(p[0], p[1], r * 2.6, 0, voll); ctx.fill();
      ctx.fillStyle = g.status === "pending" ? "rgba(0,0,0,.6)" : c(0.95 * a);
      ctx.strokeStyle = c(0.9 * a); ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, voll); ctx.fill(); ctx.stroke();
      // Beschriftung nach aussen (rechte Haelfte links buendig, linke rechts buendig), mit dunkler Kontur
      const rechts = Math.cos(p[2]) >= 0, text = (g.blatt ? g.label : g.label.toUpperCase()).slice(0, 28);
      ctx.textAlign = rechts ? "left" : "right";
      ctx.font = g.blatt ? "10px 'JetBrains Mono', Consolas, monospace" : "600 11px 'Barlow SC', 'Segoe UI', sans-serif";
      const tx = p[0] + (rechts ? 1 : -1) * (r + 7);
      ctx.globalCompositeOperation = "source-over";
      ctx.lineWidth = 3; ctx.strokeStyle = `rgba(0,0,0,${0.75 * a})`; ctx.strokeText(text, tx, p[1]);
      ctx.fillStyle = g.blatt ? `rgba(230,220,215,${0.75 * a})` : `rgba(255,255,255,${0.95 * a})`;
      ctx.fillText(text, tx, p[1]);
      ctx.globalCompositeOperation = "lighter";
    }
  }
}

// ------------------------------------------------------------------ Debug-Panel (Strg+Alt+D)
function coreDebug(core) {
  const box = el("div", "core-debug");
  box.innerHTML = `<b>CORE DEBUG</b><span class="core-debug-zu" title="Schliessen (Strg+Alt+D)">✕</span>`;
  const knopf = (text, fn) => { const k = el("button", "", text); k.onclick = fn; box.append(k); return k; };
  for (const z of ["aus", "hoeren", "denken", "sprechen", "aktion", "freigabe", "fehler"]) {
    knopf(z.toUpperCase(), () => { core.simuliert = z === "hoeren"; core.melde(z); });
  }
  let demo = null;
  const demoKnopf = knopf("▶ DEMO", () => (demo ? stop() : start()));
  knopf("▶ FENSTER", () => popupDemo());
  knopf("✕ FENSTER", () => holoBefehl({ aktion: "alle_zu" }));
  knopf("◉ LAGE", () => typeof klaus !== "undefined" && klaus.lagebericht());
  knopf("◈ GRAPH", () => typeof klaus !== "undefined" && klaus.graph("gedaechtnis", ""));
  const ablauf = [["hoeren", 1800], ["denken", 3600], ["aktion", 1300], ["freigabe", 3200], ["aktion", 1200], ["sprechen", 1600], ["aus", 2500]];
  const start = () => {
    let i = 0;
    demoKnopf.textContent = "■ STOP";
    const weiter = () => {
      const [z, ms] = ablauf[i++ % ablauf.length];
      core.simuliert = z === "hoeren";
      core.melde(z);
      demo = setTimeout(weiter, ms);
    };
    weiter();
  };
  const stop = () => { clearTimeout(demo); demo = null; demoKnopf.textContent = "▶ DEMO"; core.simuliert = false; core.melde("aus"); };
  box.querySelector(".core-debug-zu").onclick = () => box.classList.remove("offen");
  document.body.append(box);
  addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.altKey && e.key.toLowerCase() === "d") box.classList.toggle("offen");
  });
  if (new URLSearchParams(location.search).get("debug") === "1") {
    box.classList.add("offen");
    start();
    setTimeout(popupDemo, 4500);  // nach der Boot-Sequenz
  }
  if (new URLSearchParams(location.search).get("debug") === "graph") {
    setTimeout(() => typeof klaus !== "undefined" && klaus.graph("gedaechtnis", ""), 4500);
  }
}
