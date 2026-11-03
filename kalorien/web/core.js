/* Klesro Fit – Kern: Zustand, Anfragen, DOM-Helfer, Icons, Sheets, Toast, Diagramme.
   Nutzertexte kommen NUR per textContent in die Seite (h() setzt Strings immer als Text, nie als HTML). */
export const $ = (s, w = document) => w.querySelector(s);
export const MAHLZEITEN = {fruehstueck: "Frühstück", mittag: "Mittag", abend: "Abend", snack: "Snacks"};
export const S = {token: localStorage.getItem("kt"), ich: null, datum: heute(), sauber: [], ton: false};

export function heute(d = new Date()) { return new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10); }
export const zahl = v => Math.round(Number(v) || 0);
export const eins = v => Math.round((Number(v) || 0) * 10) / 10;
export const de = (v, n = 0) => Number(v || 0).toLocaleString("de-DE", {maximumFractionDigits: n});
export const tagName = (d, opt) => new Date(d + "T12:00").toLocaleDateString("de-DE", opt);
export function vor(sek) {
  const d = Math.max(0, Date.now() / 1000 - sek);
  return d < 60 ? "gerade eben" : d < 3600 ? `${Math.floor(d / 60)} Min` : d < 86400 ? `${Math.floor(d / 3600)} Std` : `${Math.floor(d / 86400)} T`;
}
export const mahlzeitJetzt = () => { const x = new Date().getHours(); return x < 10 ? "fruehstueck" : x < 15 ? "mittag" : x < 21 ? "abend" : "snack"; };
export const mmss = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/* ---------- DOM ---------- */
export function h(tag, att, ...kinder) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(att || {})) {
    if (k === "class") e.className = v;
    else if (k === "style" && v && typeof v === "object") { for (const [sk, sv] of Object.entries(v)) { if (sk.startsWith("--")) e.style.setProperty(sk, sv); else e.style[sk] = sv; } }
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "value") e.value = v;
    else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kinder.flat(Infinity)) if (k != null && k !== false) e.append(k.nodeType ? k : document.createTextNode(String(k)));
  return e;
}
export const leeren = (box, ...inhalt) => box.replaceChildren(...inhalt.flat(Infinity).filter(x => x != null && x !== false));

/* ---------- Icons (eigene, feste Pfade - nie Nutzerdaten) ---------- */
const P = {
  home: '<path d="M4 11.5 12 4l8 7.5V20a1 1 0 0 1-1 1h-4.5v-6h-5v6H5a1 1 0 0 1-1-1z"/>',
  hantel: '<path d="M2.8 9.5v5M6 7v10M18 7v10M21.2 9.5v5M6 12h12"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  reel: '<rect x="3.5" y="3.5" width="17" height="17" rx="4"/><path d="m10 8.6 5 3.4-5 3.4z" fill="currentColor"/>',
  leute: '<circle cx="9" cy="8.6" r="3.2"/><path d="M3 20c.5-3.6 3-5.5 6-5.5s5.5 1.9 6 5.5"/><path d="M16 5.7a3.2 3.2 0 0 1 0 5.8M18 14.9c1.8.7 3 2.4 3.3 5.1"/>',
  herz: '<path d="M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.4a4.3 4.3 0 0 1 7.5 2.4C19.5 15.4 12 20 12 20z"/>',
  kommentar: '<path d="M4 5.5h16v10.5H9.5L5 20v-4H4z"/>',
  flamme: '<path d="M12.6 2.8c.5 3.2-1.4 4.4-3 6.5C8 11.3 7 13 7 15.2a5 5 0 0 0 10 0c0-1.8-.7-3.2-1.8-4.4-.3 1.4-1 2.1-1.9 2.5.6-3.1-.1-6.6-.7-10.5z"/>',
  tropfen: '<path d="M12 3.5c3.2 4 6 6.8 6 10.2a6 6 0 0 1-12 0c0-3.4 2.8-6.2 6-10.2z"/>',
  kamera: '<path d="M4 8h3.2l1.6-2.5h6.4L16.8 8H20v11H4z"/><circle cx="12" cy="13.2" r="3.4"/>',
  scan: '<path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2M8 8v8M11.5 8v8M15 8v8"/>',
  stift: '<path d="M4 20h4L18.5 9.5l-4-4L4 16z"/><path d="m13 7 4 4"/>',
  buch: '<path d="M5 4.5h9.5A3.5 3.5 0 0 1 18 8v12H8.5A3.5 3.5 0 0 1 5 16.5z"/><path d="M8.5 8.5H14M8.5 12H14"/>',
  nutzer: '<circle cx="12" cy="8.4" r="3.7"/><path d="M4.5 20.5c.6-4 3.6-6 7.5-6s6.9 2 7.5 6"/>',
  pokal: '<path d="M8 4h8v5a4 4 0 0 1-8 0zM8 6H5v1a3 3 0 0 0 3 3M16 6h3v1a3 3 0 0 1-3 3M12 13v4M8.5 20h7"/>',
  chart: '<path d="M4 19V5M4 19h16M8 15v-4M12 15V8M16 15v-6"/>',
  haken: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  links: '<path d="m14.5 5-7 7 7 7"/>',
  rechts: '<path d="m9.5 5 7 7-7 7"/>',
  runter: '<path d="m5 9.5 7 7 7-7"/>',
  suche: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  teilen: '<path d="M12 15V4M8 7.5 12 4l4 3.5M5 12v7.5h14V12"/>',
  mehr: '<circle cx="5.5" cy="12" r="1.6" fill="currentColor"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="18.5" cy="12" r="1.6" fill="currentColor"/>',
  papierkorb: '<path d="M5 7h14M10 7V4.5h4V7M7 7l.8 12.5h8.4L17 7M10.3 10.5v6M13.7 10.5v6"/>',
  funke: '<path d="M12 3.2l1.9 5.4L19.3 10.5l-5.4 1.9L12 17.8l-1.9-5.4L4.7 10.5l5.4-1.9z"/><path d="M18.5 16.5l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/>',
  schloss: '<rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>',
  regler: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  waage: '<path d="M5 5h14l1 15H4z"/><path d="M9 10.5a3.2 3.2 0 0 1 6 0"/><path d="m12 10.5 1.4-2"/>',
  uhr: '<circle cx="12" cy="12" r="8"/><path d="M12 7.5V12l3 2"/>',
  hoch: '<path d="M12 19V6M7 10.5 12 5.5l5 5M5 20h14"/>',
  video: '<rect x="3.5" y="6" width="12" height="12" rx="2.5"/><path d="m15.5 10.5 5-2.5v8l-5-2.5z"/>',
  fahne: '<path d="M6 21V4M6 5h11l-2.5 3.8L17 12.5H6"/>',
  sperren: '<circle cx="12" cy="12" r="8"/><path d="m6.4 6.4 11.2 11.2"/>',
  senden: '<path d="M4 12 20 4l-4 16-4.2-6z"/><path d="m11.8 14 4.7-6"/>',
  schluessel: '<circle cx="8" cy="15" r="3.8"/><path d="m10.8 12.3 8.2-8.2M15.5 7.7l2.3 2.3M13.2 10l2 2"/>',
  ton: '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11"/>',
  stumm: '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"/><path d="m16 9.5 5 5M21 9.5l-5 5"/>',
  tag: '<path d="M4 12.5V5h7.5L20 13.5 13.5 20z"/><circle cx="8.5" cy="9" r="1.2" fill="currentColor"/>',
  schuh: '<path d="M8 3c2 0 3 2 3 5s-1 4-3 4-3-1-3-4 1-5 3-5z"/><path d="M16 11c2 0 3 2 3 4.5S18 20 16 20s-3-2-3-4.5 1-4.5 3-4.5z"/>',
  blitz: '<path d="M13 3 5.5 13.5H11L10 21l7.5-10.5H12z"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 7.8v.2"/>',
  ziel: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r=".8" fill="currentColor"/>',
};
export function icon(name, groesse) {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("fill", "none"); s.setAttribute("stroke", "currentColor");
  s.setAttribute("stroke-width", "1.9"); s.setAttribute("stroke-linecap", "round"); s.setAttribute("stroke-linejoin", "round");
  s.setAttribute("aria-hidden", "true");
  if (groesse) { s.style.width = s.style.height = groesse + "px"; }
  s.innerHTML = P[name] || "";   // nur feste Pfade aus P
  return s;
}

/* ---------- Anfragen ---------- */
export class AbmeldeFehler extends Error {}
export async function api(methode, pfad, daten) {
  const r = await fetch("/api/" + pfad, {method: methode, headers: {...(S.token ? {Authorization: "Bearer " + S.token} : {}), ...(daten ? {"Content-Type": "application/json"} : {})},
    body: daten ? JSON.stringify(daten) : undefined});
  let d = {}; try { d = await r.json(); } catch (e) { /* leere Antwort */ }
  if (r.status === 401 && S.token) { abmelden(); throw new AbmeldeFehler("Bitte neu anmelden."); }
  if (!r.ok) { const f = new Error(d.fehler || "Fehler " + r.status); f.status = r.status; throw f; }
  return d;
}
export function hochladen(pfad, datei, bei) {   // Video-Upload mit Fortschritt (fetch kann das nicht)
  return new Promise((ok, nein) => {
    const x = new XMLHttpRequest();
    x.open("POST", "/api/" + pfad);
    x.setRequestHeader("Authorization", "Bearer " + S.token);
    x.setRequestHeader("Content-Type", "application/octet-stream");
    x.upload.onprogress = e => e.lengthComputable && bei && bei(e.loaded / e.total);
    x.onload = () => { let d = {}; try { d = JSON.parse(x.responseText); } catch (e) { /* leer */ } x.status < 300 ? ok(d) : nein(new Error(d.fehler || "Upload fehlgeschlagen (" + x.status + ")")); };
    x.onerror = () => nein(new Error("Der Upload ist abgebrochen. Prüfe deine Verbindung."));
    x.send(datei);
  });
}
export async function los(fn) { try { return await fn(); } catch (e) { if (!(e instanceof AbmeldeFehler)) toast(e.message || "Das ging nicht.", true); } }
export function abmelden() { S.token = null; S.ich = null; localStorage.removeItem("kt"); location.hash = ""; location.reload(); }

/* ---------- Toast / Sheet ---------- */
export function toast(text, fehler = false, ms = 3200) {
  const t = $("#toast"); t.textContent = text; t.className = "an" + (fehler ? " fehler" : "");
  clearTimeout(toast.t); toast.t = setTimeout(() => { t.className = ""; }, ms);
}
export function sheet(titel, inhalt, optionen = {}) {
  const wurzel = $("#sheets");
  const deckel = h("div", {class: "deckel"}), blatt = h("div", {class: "sheet", role: "dialog", "aria-modal": "true"});
  let zu = false;
  const schliessen = () => { if (zu) return; zu = true; deckel.classList.remove("offen"); blatt.classList.remove("offen"); setTimeout(() => { deckel.remove(); blatt.remove(); if (optionen.zu) optionen.zu(); }, 300); };
  deckel.addEventListener("click", schliessen);
  blatt.append(...[h("div", {class: "griff"}), titel ? h("h2", {}, titel) : null, ...[].concat(typeof inhalt === "function" ? inhalt(schliessen) : inhalt)].flat(Infinity).filter(x => x != null && x !== false));
  wurzel.append(deckel, blatt);
  requestAnimationFrame(() => requestAnimationFrame(() => { deckel.classList.add("offen"); blatt.classList.add("offen"); }));
  return schliessen;
}
export function bestaetigen(frage, jaText = "Ja", gefahr = false) {
  return new Promise(ok => sheet(null, zu => [h("h2", {}, frage), h("div", {class: "knopfreihe"},
    h("button", {class: "btn zweit", onclick: () => { zu(); ok(false); }}, "Abbrechen"),
    h("button", {class: "btn" + (gefahr ? " gefahr" : ""), onclick: () => { zu(); ok(true); }}, jaText))], {zu: () => ok(false)}));
}

/* ---------- Bausteine ---------- */
export function avatar(name, groesse = "") {
  let x = 0; for (const c of name || "?") x = (x * 31 + c.charCodeAt(0)) % 360;
  const a = h("span", {class: "avatar " + groesse, style: {"--h": String(x)}}, (name || "?").trim().slice(0, 1));
  return a;
}
export function kopf(titel, kicker, rechts) {
  return h("div", {class: "kopf"}, h("div", {}, kicker ? h("div", {class: "lab"}, kicker) : null, h("h1", {}, titel)), h("div", {class: "kopf-r"}, rechts));
}
export function zurueck(ziel, text = "Zurück") {
  return h("button", {class: "zurueck", onclick: () => ziel ? (location.hash = ziel) : history.back()}, icon("links", 16), text);
}
export function leer(titel, text, aktion) { return h("div", {class: "leer"}, h("b", {}, titel), text, aktion ? h("div", {style: {marginTop: "14px"}}, aktion) : null); }
export function skelett(n = 3, hoehe = 92) { return Array.from({length: n}, () => h("div", {class: "skel", style: {height: hoehe + "px", marginBottom: "12px"}})); }
export function proMarke() { return h("span", {class: "pro-marke"}, "PRO"); }
export const istPro = () => !!(S.ich && S.ich.plan && S.ich.plan.pro);

/* Kalorien-Tacho: 270-Grad-Bogen aus Strichen (wie ein Drehzahlmesser). Volt = im Rahmen, Glut = ueber dem Ziel. */
export function tacho(ist, ziel) {
  const n = 54, start = -225, spanne = 270, cx = 150, cy = 150, r1 = 118, r2 = 138;
  const anteil = ziel > 0 ? ist / ziel : 0;
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 300 262"); svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `${zahl(ist)} von ${zahl(ziel)} Kalorien`);
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1), w = (start + t * spanne) * Math.PI / 180, lang = i % 9 === 0;
    const l = document.createElementNS(ns, "line");
    const ra = lang ? r1 - 8 : r1;
    l.setAttribute("x1", cx + Math.cos(w) * ra); l.setAttribute("y1", cy + Math.sin(w) * ra);
    l.setAttribute("x2", cx + Math.cos(w) * r2); l.setAttribute("y2", cy + Math.sin(w) * r2);
    const voll = t <= Math.min(anteil, 1) + 0.0001 && anteil > 0;
    const ueber = anteil > 1 && t > 1 / Math.max(anteil, 1.0001) - 0.0001;
    l.setAttribute("stroke", ueber ? "var(--ember)" : voll ? "var(--volt)" : "var(--line2)");
    l.setAttribute("stroke-width", lang ? "4.2" : "3.2"); l.setAttribute("stroke-linecap", "butt");
    svg.append(l);
  }
  return svg;
}

/* Mini-Liniendiagramm (Gewicht, Uebungsfortschritt). punkte: [{x:Label, y:Zahl}] */
export function linie(punkte, farbe = "var(--volt)", hoehe = 120) {
  const ns = "http://www.w3.org/2000/svg", B = 300, H = hoehe, rand = 8;
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${B} ${H}`); svg.setAttribute("class", "plot");
  if (punkte.length < 2) return svg;
  const ys = punkte.map(p => p.y), lo = Math.min(...ys), hi = Math.max(...ys), sp = hi - lo || 1;
  const X = i => rand + i * (B - 2 * rand) / (punkte.length - 1), Y = v => H - rand - 14 - (v - lo) / sp * (H - 2 * rand - 28);
  const d = punkte.map((p, i) => `${i ? "L" : "M"}${X(i).toFixed(1)} ${Y(p.y).toFixed(1)}`).join(" ");
  const flaeche = document.createElementNS(ns, "path");
  flaeche.setAttribute("d", `${d} L${X(punkte.length - 1)} ${H} L${X(0)} ${H} Z`); flaeche.setAttribute("fill", farbe); flaeche.setAttribute("opacity", ".1");
  const pfad = document.createElementNS(ns, "path");
  pfad.setAttribute("d", d); pfad.setAttribute("fill", "none"); pfad.setAttribute("stroke", farbe); pfad.setAttribute("stroke-width", "2.6");
  pfad.setAttribute("stroke-linejoin", "round"); pfad.setAttribute("stroke-linecap", "round");
  svg.append(flaeche, pfad);
  const letzter = document.createElementNS(ns, "circle");
  letzter.setAttribute("cx", X(punkte.length - 1)); letzter.setAttribute("cy", Y(ys[ys.length - 1])); letzter.setAttribute("r", "4.5"); letzter.setAttribute("fill", farbe);
  svg.append(letzter);
  return svg;
}

/* Foto verkleinern (JPEG, Exif/GPS fliegt dabei raus, weil neu gezeichnet) */
export function verkleinern(datei, max = 1280, qualitaet = .82) {
  return new Promise((ok, nein) => {
    const url = URL.createObjectURL(datei), bild = new Image();
    bild.onload = () => {
      const f = Math.min(1, max / Math.max(bild.width, bild.height)), c = document.createElement("canvas");
      c.width = Math.round(bild.width * f); c.height = Math.round(bild.height * f);
      c.getContext("2d").drawImage(bild, 0, 0, c.width, c.height); URL.revokeObjectURL(url); ok(c.toDataURL("image/jpeg", qualitaet));
    };
    bild.onerror = () => nein(new Error("Das Foto konnte nicht gelesen werden."));
    bild.src = url;
  });
}
export async function verkleinernBis(datei, maxBytes = 800 * 1024) {
  for (const [grenze, q] of [[1280, .82], [1100, .74], [900, .66], [720, .6]]) {
    const d = await verkleinern(datei, grenze, q);
    if (d.length * 0.75 <= maxBytes) return d;
  }
  throw new Error("Das Foto ist zu groß. Nimm ein anderes.");
}
