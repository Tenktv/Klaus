// Holo-Fenster: freie Fenster (kein Raster) mit Boot-/Schliess-Animation, Ziehen, Groesse, Magnet-Kanten.
// Lage wird als Anteil (0..1) der Arbeitsflaeche gespeichert -> passt sich jeder Bildschirmgroesse an.

const HOLO_RUHIG = matchMedia("(prefers-reduced-motion: reduce)").matches;
const MAGNET_PX = 10;   // so nah an einer Kante rastet das Fenster ein
let holoOben = 10;       // z-index des vordersten Fensters

// Pop-ups liegen immer ueber den Widgets (Basis 1000), untereinander gilt: zuletzt angefasst = vorne
function holoVorne(fenster) {
  ++holoOben;
  fenster.style.zIndex = (fenster.classList.contains("popup") ? 1000 : 0) + holoOben;
  return holoOben;
}

// Bestehende API: Titel sofort lesbar setzen.
function holoTitel(ziel, text, dauer = 520) {
  if (ziel) ziel.textContent = text;
}

// Rahmen (Stark Holo-Tech): abgeschraegte Ecken, Leuchtkante mit Glow, Lichtreflex oben links, zwei Eck-Ticks.
// Als SVG neben dem Glas (.w), weil clip-path am Glas sonst den Glow abschneiden wuerde. Folgt jeder Groessenaenderung.
const RAHMEN_ECKE = 14, RAHMEN_RAND = 12, FENSTER_PADDING = 5;
function holoRahmen(fenster) {
  const glas = fenster.querySelector(":scope > .w");
  if (!glas || glas.classList.contains("frei") || fenster.querySelector(":scope > .rahmen")) return;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "rahmen");
  svg.setAttribute("aria-hidden", "true");
  glas.after(svg);
  const zeichnen = () => {
    const b = glas.offsetWidth, h = glas.offsetHeight;
    if (!b || !h || svg._g === `${b}x${h}`) return;
    svg._g = `${b}x${h}`;
    const c = RAHMEN_ECKE, o = RAHMEN_RAND, x0 = o + 0.5, y0 = o + 0.5, w = b - 1, hh = h - 1;
    svg.setAttribute("width", b + 2 * o); svg.setAttribute("height", h + 2 * o);
    svg.style.left = svg.style.top = `${FENSTER_PADDING - o}px`;
    const d = `M${x0 + c} ${y0}H${x0 + w}V${y0 + hh - c}L${x0 + w - c} ${y0 + hh}H${x0}V${y0 + c}Z`;
    svg.style.setProperty("--len", Math.round(2 * (w + hh) - 4 * c + 2 * c * Math.SQRT2));
    svg.innerHTML = `<path class="r-glow" d="${d}"/><path class="r-kante" d="${d}"/>`
      + `<path class="r-reflex" d="M${o + c + 6} ${y0}H${o + Math.min(b * 0.42, 200)}" style="--len:300"/>`
      + `<path class="r-tick" d="M${o + b - 30} ${o - 3}H${o + b + 3}V${o + 27}" style="--len:70"/>`
      + `<path class="r-tick" d="M${o - 3} ${o + h - 26}V${o + h + 3}H${o + 30}" style="--len:70"/>`;
  };
  zeichnen();
  new ResizeObserver(zeichnen).observe(glas);
}

// Seite fuer die leichte Neigung (3°): Fenster links vom Auge kippen nach rechts und umgekehrt. Web-Widgets nie
// (die echte Browser-Ansicht darueber kann nicht mitkippen).
function holoSeite(fenster, m) {
  if (fenster.classList.contains("popup") || fenster.querySelector(".web-inhalt, .w.frei")) { delete fenster.dataset.seite; return; }
  const mitte = m.x + m.w / 2;
  if (mitte < 0.42) fenster.dataset.seite = "l";
  else if (mitte > 0.58) fenster.dataset.seite = "r";
  else delete fenster.dataset.seite;
}

// Boot: Rahmen zeichnet sich, Glas klappt aus einer Linie auf, Scanline wischt runter, Inhalt blendet ein, Titel entschluesselt
function holoBoot(fenster, verzoegerung = 0) {
  holoRahmen(fenster);
  if (HOLO_RUHIG) return;
  fenster.querySelectorAll(":scope > .hl").forEach((e) => e.remove());
  fenster.append(el("i", "hl hl-scan"));
  fenster.style.setProperty("--v", `${verzoegerung}ms`);
  fenster.style.setProperty("--hoehe", `${fenster.clientHeight}px`);
  fenster.classList.remove("holo-aus");
  fenster.classList.remove("holo-boot"); void fenster.offsetWidth;
  fenster.classList.add("holo-boot");
  const titel = fenster.querySelector(".w-titel");
  if (titel) setTimeout(() => holoTitel(titel, titel.dataset.text || titel.textContent), verzoegerung + 420);
  clearTimeout(fenster._bootEnde);
  fenster._bootEnde = setTimeout(() => {
    fenster.classList.remove("holo-boot");
    fenster.querySelectorAll(":scope > .hl").forEach((e) => e.remove());
  }, verzoegerung + 1500);
}

// Schliessen: rueckwaerts - Inhalt weg, Glas faellt auf eine Linie zusammen, Rahmen zieht sich ein. -> Promise
function holoAus(fenster) {
  if (HOLO_RUHIG) return Promise.resolve();
  fenster.querySelectorAll(":scope > .hl").forEach((e) => e.remove());
  fenster.classList.remove("holo-boot");
  fenster.classList.add("holo-aus");
  return new Promise((fertig) => setTimeout(fertig, 620));
}

// Freies Ziehen am Griff + Groesse an der Ecke. flaeche = Arbeitsflaeche, m = Modell mit x/y/w/h (Anteile).
// optionen: minB/minH (Pixel), andere() -> andere Fenster (fuer Magnet-Kanten), beimStart(), beimEnde()
function holoFrei(fenster, m, griff, ecke, flaeche, optionen) {
  const { minB = 160, minH = 90, andere = () => [], beimStart = () => {}, beimEnde = () => {}, beimAnfassen = () => {} } = optionen;

  const kanten = () => {
    const F = flaeche.getBoundingClientRect();
    const xs = [0, F.width], ys = [0, F.height];
    for (const o of andere()) {
      if (o === fenster) continue;
      const r = o.getBoundingClientRect();
      xs.push(r.left - F.left, r.right - F.left);
      ys.push(r.top - F.top, r.bottom - F.top);
    }
    return { F, xs, ys };
  };
  // Wert so verschieben, dass eine der beiden Kanten (a, a+laenge) an einer Magnet-Kante einrastet
  const einrasten = (a, laenge, liste) => {
    let best = null;
    for (const k of liste) for (const d of [k - a, k - (a + laenge)]) if (Math.abs(d) < MAGNET_PX && (best === null || Math.abs(d) < Math.abs(best))) best = d;
    return best === null ? a : a + best;
  };

  griff.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || e.target.closest(".w-knopf, input, button, a")) return;
    e.preventDefault();
    griff.setPointerCapture(e.pointerId);
    holoVorne(fenster);
    const { F, xs, ys } = kanten();
    const r = fenster.getBoundingClientRect();
    const start = { x: e.clientX, y: e.clientY, l: r.left - F.left, t: r.top - F.top };
    let ziel = { l: start.l, t: start.t };
    fenster.classList.add("zieht");
    beimStart();
    const bewegen = (ev) => {
      let l = Math.max(0, Math.min(F.width - r.width, start.l + ev.clientX - start.x));
      let t = Math.max(0, Math.min(F.height - r.height, start.t + ev.clientY - start.y));
      l = einrasten(l, r.width, xs); t = einrasten(t, r.height, ys);
      ziel = { l, t };
      fenster.style.transform = `translate(${l - start.l}px, ${t - start.t}px)`;  // waehrend des Ziehens nur transform
    };
    const los = () => {
      griff.removeEventListener("pointermove", bewegen);
      griff.removeEventListener("pointerup", los);
      griff.removeEventListener("pointercancel", los);
      fenster.classList.remove("zieht");
      fenster.style.transform = "";
      m.x = ziel.l / F.width; m.y = ziel.t / F.height;
      holoLage(fenster, m);
      beimEnde();
    };
    griff.addEventListener("pointermove", bewegen);
    griff.addEventListener("pointerup", los);
    griff.addEventListener("pointercancel", los);
  });

  ecke.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault(); e.stopPropagation();
    ecke.setPointerCapture(e.pointerId);
    holoVorne(fenster);
    const { F, xs, ys } = kanten();
    const r = fenster.getBoundingClientRect();
    const l = r.left - F.left, t = r.top - F.top, start = { x: e.clientX, y: e.clientY };
    let groesse = { b: r.width, h: r.height };
    fenster.classList.add("zieht");
    beimStart();
    const bewegen = (ev) => {
      let b = Math.max(minB, Math.min(F.width - l, r.width + ev.clientX - start.x));
      let h = Math.max(minH, Math.min(F.height - t, r.height + ev.clientY - start.y));
      b = einrasten(l + b, 0, xs) - l; h = einrasten(t + h, 0, ys) - t;
      groesse = { b, h };
      fenster.style.width = `${b}px`; fenster.style.height = `${h}px`;
    };
    const los = () => {
      ecke.removeEventListener("pointermove", bewegen);
      ecke.removeEventListener("pointerup", los);
      ecke.removeEventListener("pointercancel", los);
      fenster.classList.remove("zieht");
      m.w = groesse.b / F.width; m.h = groesse.h / F.height;
      holoLage(fenster, m);
      beimEnde();
    };
    ecke.addEventListener("pointermove", bewegen);
    ecke.addEventListener("pointerup", los);
    ecke.addEventListener("pointercancel", los);
  });

  fenster.addEventListener("pointerdown", () => { m.z = holoVorne(fenster); beimAnfassen(); }, true);
}

// Modell-Lage (Anteile) aufs Element schreiben - in %, damit es mit der Bildschirmgroesse mitgeht
function holoLage(fenster, m) {
  const s = fenster.style;
  s.left = `${(m.x * 100).toFixed(3)}%`; s.top = `${(m.y * 100).toFixed(3)}%`;
  s.width = `${(m.w * 100).toFixed(3)}%`; s.height = `${(m.h * 100).toFixed(3)}%`;
  holoSeite(fenster, m);
}

// Rechteck-Hilfen (Anteile)
function holoUeberlappt(a, b) { return a.x < b.x + b.w - 1e-4 && b.x < a.x + a.w - 1e-4 && a.y < b.y + b.h - 1e-4 && b.y < a.y + a.h - 1e-4; }
function holoImBild(r) { return r.x >= -1e-4 && r.y >= -1e-4 && r.x + r.w <= 1 + 1e-4 && r.y + r.h <= 1 + 1e-4; }
function holoPlatz(w, h, belegt) {
  for (let y = 0; y + h <= 1 + 1e-4; y += 0.02) {
    for (let x = 0; x + w <= 1 + 1e-4; x += 0.01) {
      const r = { x, y, w, h };
      if (!belegt.some((b) => holoUeberlappt(r, b))) return r;
    }
  }
  return null;
}
