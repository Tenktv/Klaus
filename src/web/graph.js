// Graph-Fenster (Holo-Pop-up "graph"): Wissensnetz im graphify-Look - Gedaechtnis-Vault oder Code-Projekt.
// Daten von Python (graphen.py): {knoten: [{id, label, gruppe, typ, info}], kanten: [[a, b]], gruppen: {nr: name}}
// Kraft-Layout mit Raster-Abstossung (O(n) statt O(n²)), danach steht das Bild still -> nur bei Maus neu zeichnen.

const GRAPH_FARBEN = ["#ff6b6b", "#ffa94d", "#ffd43b", "#69db7c", "#38d9a9", "#4dabf7", "#748ffc", "#da77f2",
                      "#f783ac", "#e9ecef", "#ff922b", "#a9e34b", "#3bc9db", "#9775fa", "#faa2c1", "#ced4da"];

POPUP_GROESSE.graph = [0.36, 0.94];   // links neben dem Reaktor, fast volle Hoehe
POPUP_DAUER.graph = 900;   // bleibt lange offen (15 min ohne Neuigkeit)
POPUP_TITEL.graph = "GRAPH";

POPUP_ARTEN.graph = function (box) {
  box.classList.add("p-graph");
  box.innerHTML = `<div class="g-flaeche"><canvas></canvas><div class="g-tipp"></div></div>
    <aside class="g-seite"><input class="feld g-suche" spellcheck="false" autocomplete="off" placeholder="Knoten suchen …" aria-label="Knoten suchen">
      <div class="g-info"><div class="lbl">Knoten-Info</div><div class="g-info-inhalt leer">Maus auf einen Knoten</div></div>
      <div class="g-gruppen"><div class="lbl">Gruppen</div><div class="g-gruppen-liste"></div></div>
      <div class="g-fuss"></div></aside>`;
  const cv = box.querySelector("canvas"), ctx = cv.getContext("2d"), tipp = box.querySelector(".g-tipp");
  const info = box.querySelector(".g-info-inhalt"), gruppenListe = box.querySelector(".g-gruppen-liste");
  const fuss = box.querySelector(".g-fuss"), suche = box.querySelector(".g-suche");
  let knoten = [], kanten = [], nachbarn = new Map(), gruppenFarbe = new Map(), gruppenName = {};
  let hitze = 0, ansicht = { x: 0, y: 0, z: 1 }, schwebt = null, gewaehlt = null, gruppeAn = null, treffer = new Set();
  let laeuft = false;

  const farbe = (n) => gruppenFarbe.get(n.gruppe) || "#adb5bd";
  const zuWelt = (sx, sy) => [(sx - cv.clientWidth / 2) / ansicht.z - ansicht.x, (sy - cv.clientHeight / 2) / ansicht.z - ansicht.y];

  function laden(d) {
    const alt = new Map(knoten.map((n) => [n.id, n]));
    knoten = (d.knoten || []).map((k) => {
      const v = alt.get(k.id);
      const w = Math.random() * Math.PI * 2, r = Math.sqrt(Math.random()) * 260;
      return { ...k, x: v ? v.x : Math.cos(w) * r, y: v ? v.y : Math.sin(w) * r, vx: 0, vy: 0, grad: 0 };
    });
    const index = new Map(knoten.map((n, i) => [n.id, i]));
    kanten = (d.kanten || []).map(([a, b]) => [index.get(a), index.get(b)]).filter(([a, b]) => a !== undefined && b !== undefined && a !== b);
    nachbarn = new Map(knoten.map((_, i) => [i, []]));
    for (const [a, b] of kanten) { knoten[a].grad++; knoten[b].grad++; nachbarn.get(a).push(b); nachbarn.get(b).push(a); }
    // Gruppen nach Groesse sortiert einfaerben
    const groesse = new Map();
    for (const n of knoten) groesse.set(n.gruppe, (groesse.get(n.gruppe) || 0) + 1);
    gruppenFarbe = new Map([...groesse.keys()].sort((a, b) => groesse.get(b) - groesse.get(a)).map((g, i) => [g, GRAPH_FARBEN[i % GRAPH_FARBEN.length]]));
    gruppenName = d.gruppen || {};
    gruppenListe.innerHTML = "";
    for (const [g] of [...groesse.entries()].sort((a, b) => b[1] - a[1]).slice(0, 14)) {
      const z = el("button", "g-gruppe");
      z.style.setProperty("--g", gruppenFarbe.get(g));
      z.append(el("i"), el("span", "", String(gruppenName[g] ?? `Gruppe ${g}`)), el("small", "", String(groesse.get(g))));
      z.onclick = () => { gruppeAn = gruppeAn === g ? null : g; zeichnen(); };
      gruppenListe.append(z);
    }
    fuss.textContent = `${knoten.length} KNOTEN · ${kanten.length} KANTEN · ${groesse.size} GRUPPEN`;
    ansicht = { x: 0, y: 0, z: 1 };
    hitze = 1;
    starten();
  }

  // ------------------------------------------------------------------ Layout
  function schritt() {
    const n = knoten.length, zelle = 46, raster = new Map();
    knoten.forEach((k, i) => {
      const s = `${Math.floor(k.x / zelle)},${Math.floor(k.y / zelle)}`;
      (raster.get(s) || raster.set(s, []).get(s)).push(i);
    });
    // Abstossung nur in den Nachbarzellen
    for (let i = 0; i < n; i++) {
      const a = knoten[i], cx = Math.floor(a.x / zelle), cy = Math.floor(a.y / zelle);
      for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
        for (const j of raster.get(`${cx + dx},${cy + dy}`) || []) {
          if (j <= i) continue;
          const b = knoten[j];
          let ex = a.x - b.x, ey = a.y - b.y, d2 = ex * ex + ey * ey;
          if (d2 < 0.01) { ex = Math.random() - 0.5; ey = Math.random() - 0.5; d2 = 0.5; }
          if (d2 > zelle * zelle) continue;
          const f = (420 / d2) * hitze;
          a.vx += ex * f; a.vy += ey * f; b.vx -= ex * f; b.vy -= ey * f;
        }
      }
    }
    // Federn entlang der Kanten
    for (const [i, j] of kanten) {
      const a = knoten[i], b = knoten[j], ex = b.x - a.x, ey = b.y - a.y, d = Math.sqrt(ex * ex + ey * ey) || 1;
      const f = ((d - 26) / d) * 0.045 * hitze;
      a.vx += ex * f; a.vy += ey * f; b.vx -= ex * f; b.vy -= ey * f;
    }
    // sanft zur Mitte, Gruppen halten zusammen
    const mitte = new Map();
    for (const k of knoten) { const m = mitte.get(k.gruppe) || mitte.set(k.gruppe, [0, 0, 0]).get(k.gruppe); m[0] += k.x; m[1] += k.y; m[2]++; }
    // Form des Fensters: im hohen Fenster zieht es seitlich staerker zusammen -> Netz fuellt die Flaeche
    const seite = Math.sqrt((cv.clientHeight || 1) / (cv.clientWidth || 1));
    for (const k of knoten) {
      const m = mitte.get(k.gruppe);
      k.vx += (-k.x * 0.004 * seite + (m[0] / m[2] - k.x) * 0.006) * hitze;
      k.vy += (-k.y * 0.004 / seite + (m[1] / m[2] - k.y) * 0.006) * hitze;
      k.vx *= 0.82; k.vy *= 0.82;
      k.x += Math.max(-12, Math.min(12, k.vx)); k.y += Math.max(-12, Math.min(12, k.vy));
    }
    hitze *= 0.985;
  }

  // Ansicht so zoomen, dass alles hineinpasst
  function einpassen() {
    if (!knoten.length) return;
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const k of knoten) { x0 = Math.min(x0, k.x); x1 = Math.max(x1, k.x); y0 = Math.min(y0, k.y); y1 = Math.max(y1, k.y); }
    const w = cv.clientWidth || 1, h = cv.clientHeight || 1;
    ansicht.z = Math.min(2.5, 0.9 * Math.min(w / (x1 - x0 + 40), h / (y1 - y0 + 40)));
    ansicht.x = -(x0 + x1) / 2; ansicht.y = -(y0 + y1) / 2;
  }

  // ------------------------------------------------------------------ Zeichnen
  function zeichnen() {
    const dpr = Math.min(1.5, devicePixelRatio || 1), w = cv.clientWidth, h = cv.clientHeight;
    if (!w || !h) return;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.setTransform(dpr * ansicht.z, 0, 0, dpr * ansicht.z, dpr * (w / 2 + ansicht.x * ansicht.z), dpr * (h / 2 + ansicht.y * ansicht.z));
    const fokus = schwebt ?? gewaehlt;
    const nah = fokus !== null ? new Set([fokus, ...nachbarn.get(fokus)]) : null;
    const sichtbar = (i) => (!nah || nah.has(i)) && (gruppeAn === null || knoten[i].gruppe === gruppeAn) && (!treffer.size || treffer.has(i));
    const z = ansicht.z;
    // Kanten nach Farbe gebuendelt
    ctx.globalCompositeOperation = "lighter";
    const buendel = new Map();
    for (const [i, j] of kanten) {
      const an = sichtbar(i) && sichtbar(j);
      const schl = (an ? farbe(knoten[i]) : "#555") + (an ? "" : "|aus");
      (buendel.get(schl) || buendel.set(schl, []).get(schl)).push([i, j]);
    }
    for (const [schl, liste] of buendel) {
      const aus = schl.endsWith("|aus");
      ctx.strokeStyle = aus ? "rgba(140,140,150,.05)" : schl;
      ctx.globalAlpha = aus ? 1 : nah ? 0.75 : 0.22;
      ctx.lineWidth = (nah && !aus ? 1.1 : 0.6) / z;
      ctx.beginPath();
      for (const [i, j] of liste) { ctx.moveTo(knoten[i].x, knoten[i].y); ctx.lineTo(knoten[j].x, knoten[j].y); }
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    // Knoten mit Leuchten
    knoten.forEach((k, i) => {
      const an = sichtbar(i), r = (1.6 + Math.sqrt(k.grad) * 0.9) / Math.sqrt(z);
      ctx.fillStyle = an ? farbe(k) : "rgba(120,120,130,.18)";
      if (an) { ctx.globalAlpha = 0.18; ctx.beginPath(); ctx.arc(k.x, k.y, r * 2.8, 0, Math.PI * 2); ctx.fill(); ctx.globalAlpha = 1; }
      ctx.beginPath(); ctx.arc(k.x, k.y, i === fokus ? r * 1.8 : r, 0, Math.PI * 2); ctx.fill();
    });
    ctx.globalCompositeOperation = "source-over";
    // Beschriftung: wichtigste Knoten bzw. Nachbarn des Fokus
    const beschriften = nah ? [...nah] : knoten.map((_, i) => i).filter(sichtbar).sort((a, b) => knoten[b].grad - knoten[a].grad).slice(0, 14);
    ctx.font = `500 ${11 / z}px 'Barlow SC', 'Segoe UI', sans-serif`;
    ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.lineJoin = "round";
    for (const i of beschriften) {
      const k = knoten[i], r = (1.6 + Math.sqrt(k.grad) * 0.9) / Math.sqrt(z), text = k.label.slice(0, 36);
      ctx.lineWidth = 3 / z; ctx.strokeStyle = "rgba(0,0,0,.85)"; ctx.strokeText(text, k.x, k.y + r + 3 / z);
      ctx.fillStyle = i === fokus ? "#fff" : "rgba(235,230,228,.85)"; ctx.fillText(text, k.x, k.y + r + 3 / z);
    }
  }

  function infoZeigen(i) {
    if (i === null) { info.className = "g-info-inhalt leer"; info.textContent = "Maus auf einen Knoten"; return; }
    const k = knoten[i];
    info.className = "g-info-inhalt";
    info.innerHTML = "";
    info.append(el("b", "", k.label), el("div", "", `Typ: ${k.typ || "–"}`),
      el("div", "", `Gruppe: ${gruppenName[k.gruppe] ?? k.gruppe}`), el("div", "", `Verbindungen: ${k.grad}`));
    if (k.info) info.append(el("div", "g-quelle", k.info));
    const liste = el("div", "g-nachbarn");
    for (const j of nachbarn.get(i).slice(0, 12)) {
      const z = el("button", "g-nachbar", knoten[j].label.slice(0, 40));
      z.style.setProperty("--g", farbe(knoten[j]));
      z.onclick = () => { gewaehlt = j; infoZeigen(j); zeichnen(); };
      liste.append(z);
    }
    info.append(el("div", "lbl", `Nachbarn (${nachbarn.get(i).length})`), liste);
  }

  // Layout laufen lassen, bis es abgekuehlt ist; danach steht alles still
  function starten() {
    if (laeuft) return;
    laeuft = true;
    let bilder = 0;
    const lauf = () => {
      if (!box.isConnected) { laeuft = false; return; }
      if (window.klausPause) { setTimeout(() => requestAnimationFrame(lauf), 500); return; }
      const proBild = knoten.length > 1200 ? 1 : 3;
      for (let s = 0; s < proBild && hitze > 0.02; s++) schritt();
      if (bilder++ % 20 === 0) einpassen();
      zeichnen();
      if (hitze > 0.02) requestAnimationFrame(lauf); else { einpassen(); zeichnen(); laeuft = false; }
    };
    requestAnimationFrame(lauf);
  }

  // ------------------------------------------------------------------ Maus: schweben, waehlen, zoomen, schieben
  const naechster = (sx, sy) => {
    const [wx, wy] = zuWelt(sx, sy);
    let best = null, bestD = (10 / ansicht.z) ** 2;
    knoten.forEach((k, i) => { const d = (k.x - wx) ** 2 + (k.y - wy) ** 2; if (d < bestD) { bestD = d; best = i; } });
    return best;
  };
  let zieht = null;
  cv.addEventListener("pointerdown", (e) => { zieht = { x: e.clientX, y: e.clientY, ax: ansicht.x, ay: ansicht.y, bewegt: false }; cv.setPointerCapture(e.pointerId); });
  cv.addEventListener("pointermove", (e) => {
    const r = cv.getBoundingClientRect();
    if (zieht) {
      const dx = e.clientX - zieht.x, dy = e.clientY - zieht.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) zieht.bewegt = true;
      ansicht.x = zieht.ax + dx / ansicht.z; ansicht.y = zieht.ay + dy / ansicht.z;
      zeichnen(); return;
    }
    const i = naechster(e.clientX - r.left, e.clientY - r.top);
    if (i !== schwebt) {
      schwebt = i;
      if (i !== null) { tipp.textContent = knoten[i].label; tipp.style.left = `${e.clientX - r.left + 12}px`; tipp.style.top = `${e.clientY - r.top + 12}px`; }
      tipp.classList.toggle("an", i !== null);
      infoZeigen(i ?? gewaehlt);
      zeichnen();
    }
  });
  cv.addEventListener("pointerup", (e) => {
    if (zieht && !zieht.bewegt) { const r = cv.getBoundingClientRect(); gewaehlt = naechster(e.clientX - r.left, e.clientY - r.top); infoZeigen(gewaehlt); zeichnen(); }
    zieht = null;
  });
  cv.addEventListener("pointerleave", () => { schwebt = null; tipp.classList.remove("an"); infoZeigen(gewaehlt); zeichnen(); });
  cv.addEventListener("wheel", (e) => {
    e.preventDefault();
    const r = cv.getBoundingClientRect(), sx = e.clientX - r.left, sy = e.clientY - r.top, [wx, wy] = zuWelt(sx, sy);
    ansicht.z = Math.max(0.15, Math.min(8, ansicht.z * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
    ansicht.x = (sx - cv.clientWidth / 2) / ansicht.z - wx; ansicht.y = (sy - cv.clientHeight / 2) / ansicht.z - wy;
    zeichnen();
  }, { passive: false });
  suche.addEventListener("input", () => {
    const q = suche.value.trim().toLowerCase();
    treffer = new Set(q ? knoten.map((k, i) => (k.label.toLowerCase().includes(q) ? i : -1)).filter((i) => i >= 0) : []);
    if (q && !treffer.size) treffer = new Set([-1]);
    zeichnen();
  });
  new ResizeObserver(() => { if (!laeuft) { einpassen(); zeichnen(); } }).observe(cv);

  return { update(d) { if (d.knoten) laden(d); } };
};
