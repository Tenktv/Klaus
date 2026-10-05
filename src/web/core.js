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

    const aktiv = ["THINKING", "EXECUTING", "AWAITING_AUTH", "LISTENING", "DONE"].includes(name)
      || this.teilchen.length || this.wellen.length;
    if (!aktiv || this.ruhig) {
      if (!this.leer) { this.ctx.clearRect(0, 0, this.fx.width, this.fx.height); this.leer = true; }
      setTimeout(() => requestAnimationFrame((t) => this.tick(t)), 120);  // nichts zu zeichnen -> kaum CPU
      return;
    }
    this.leer = false;
    this.zeichne(dt, jetzt);
    requestAnimationFrame((t) => this.tick(t));
  }

  zeichne(dt, jetzt) {
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
    ctx.globalCompositeOperation = "source-over";
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
}
