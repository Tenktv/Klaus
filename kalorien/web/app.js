/* Klesro Fit – Start, Router (Hash, damit die iPhone-Wischgeste "zurück" geht), Tab-Leiste, "+"-Sheet. */
import {$, S, h, icon, api, los, sheet, leeren, skelett} from "./core.js";
import {anmeldeseite, willkommen} from "./v_start.js";
import {heuteSeite} from "./v_heute.js";
import {essenSeite, wasserSheet, gewichtSheet, cardioSheet} from "./v_essen.js";
import {trainingSeite, workoutSeite, workoutDetail, uebungSeite, workoutStarten} from "./v_training.js";
import {reelsSeite, reelHochladen} from "./v_reels.js";
import {communitySeite, profilSeite, beitragSeite, beitragNeu, forumThema, chatSeite} from "./v_community.js";
import {rezepteSeite, rezeptSeite, rezeptNeu} from "./v_rezepte.js";
import {ichSeite, proSeite, kiSeite, coachSeite, adminSeite, schnittstelleSeite, appleHealthSeite, zieleSeite} from "./v_ich.js";

const TABS = [
  {id: "heute", name: "Heute", ikon: "home", hash: "#/heute"},
  {id: "training", name: "Training", ikon: "hantel", hash: "#/training"},
  {id: "plus"},
  {id: "reels", name: "Reels", ikon: "reel", hash: "#/reels"},
  {id: "community", name: "Community", ikon: "leute", hash: "#/community"},
];
// Muster -> [Ansicht, aktiver Tab, Vollbild?]
const ROUTEN = [
  [/^\/heute$/, heuteSeite, "heute"], [/^\/training$/, trainingSeite, "training"], [/^\/reels$/, reelsSeite, "reels", true],
  [/^\/community(?:\/(\w+))?$/, communitySeite, "community"],
  [/^\/essen\/(foto|text|barcode|hand)$/, essenSeite, "heute"],
  [/^\/rezepte(?:\/(\w+))?$/, rezepteSeite, "heute"], [/^\/rezept\/(\d+)$/, rezeptSeite, "heute", true], [/^\/rezept-neu$/, rezeptNeu, "heute"],
  [/^\/workout$/, workoutSeite, "training"], [/^\/workout\/(\d+)$/, workoutDetail, "training"], [/^\/uebung\/(.+)$/, uebungSeite, "training"],
  [/^\/profil\/(.+)$/, profilSeite, "community"], [/^\/beitrag\/(\d+)$/, beitragSeite, "community"], [/^\/forum\/(\d+)$/, forumThema, "community"],
  [/^\/chat$/, chatSeite, "community"],
  [/^\/ich$/, ichSeite, "heute"], [/^\/pro$/, proSeite, "heute"], [/^\/ki$/, kiSeite, "heute"], [/^\/coach$/, coachSeite, "heute"],
  [/^\/admin$/, adminSeite, "heute"], [/^\/schnittstelle$/, schnittstelleSeite, "heute"], [/^\/apple-health$/, appleHealthSeite, "heute"], [/^\/ziele$/, zieleSeite, "heute"],
];
let aufraeumen = null, zaehler = 0;

function leiste(aktiv) {
  const nav = $("#leiste");
  leeren(nav, TABS.map(t => t.id === "plus"
    ? h("button", {class: "plus", "aria-label": "Hinzufügen", onclick: plusSheet}, h("span", {}, icon("plus")))
    : h("button", {class: t.id === aktiv ? "an" : "", onclick: () => { if (location.hash === t.hash) window.scrollTo(0, 0); else location.hash = t.hash; }}, icon(t.ikon), t.name)));
  nav.hidden = false;
}

async function navigieren() {
  if (!S.token) return anmeldeseite();
  if (!S.ich) {
    try { S.ich = await api("GET", "ich"); } catch (e) { return; }
  }
  const pfad = decodeURIComponent((location.hash || "#/heute").replace(/^#/, "")).split("?")[0] || "/heute";
  const treffer = ROUTEN.map(r => [r, r[0].exec(pfad)]).find(([, m]) => m);
  if (!treffer) { location.replace("#/heute"); return; }
  const [[, ansicht, tab, voll], m] = treffer;
  if (aufraeumen) { try { aufraeumen(); } catch (e) { /* egal */ } aufraeumen = null; }
  const mein = ++zaehler;
  const box = $("#view");
  box.className = voll ? "voll" : "";
  document.body.classList.toggle("reels", tab === "reels");
  leeren(box, skelett(3));
  leiste(tab);
  window.scrollTo(0, 0);
  const ctx = {box, teile: m.slice(1), abfrage: new URLSearchParams((location.hash.split("?")[1]) || ""),
    aufraeumen: fn => { aufraeumen = fn; }, aktuell: () => mein === zaehler};
  try { await ansicht(ctx); } catch (e) {
    if (mein === zaehler) { leeren(box, h("div", {class: "leer"}, h("b", {}, "Das hat nicht geklappt"), e.message || "Unbekannter Fehler")); }
  }
}

/* ---------- "+" ---------- */
function plusSheet() {
  const kachel = (ikon, titel, sub, tun, c = "") => h("button", {class: "karte klick kachel " + c, onclick: () => { schliessen(); tun(); }},
    h("div", {style: {color: c === "ki" ? "var(--volt)" : "var(--txt)", marginBottom: "9px"}}, icon(ikon, 24)), h("div", {class: "disp"}, titel), h("div", {class: "mut klein"}, sub));
  const gehe = hash => () => { location.hash = hash; };
  const gruppe = (name, ...kacheln) => [h("div", {class: "lab", style: {margin: "0 0 8px"}}, name), h("div", {class: "raster r2", style: {marginBottom: "16px"}}, kacheln)];
  const schliessen = sheet("Hinzufügen", () => [
    gruppe("Essen", kachel("kamera", "Foto-Scan", "KI schätzt dein Essen", gehe("#/essen/foto"), "ki"), kachel("funke", "Beschreiben", "Text → Nährwerte", gehe("#/essen/text"), "ki"),
      kachel("scan", "Barcode", "Produkt scannen", gehe("#/essen/barcode")), kachel("buch", "Rezept", "Aus der Sammlung", gehe("#/rezepte")),
      kachel("stift", "Von Hand", "Werte selbst eintragen", gehe("#/essen/hand")), kachel("tropfen", "Wasser", "Glas hinzufügen", () => los(() => wasserSheet()))),
    gruppe("Training & Körper", kachel("hantel", "Workout", "Sätze & Gewichte", workoutStarten), kachel("blitz", "Cardio", "Laufen, Rad, HIIT …", () => cardioSheet()),
      kachel("waage", "Gewicht", "Heute wiegen", () => gewichtSheet()), kachel("ziel", "Rezept anlegen", "Eigenes oder per KI", gehe("#/rezept-neu"))),
    gruppe("Teilen", kachel("video", "Reel", "Kurzes Video, 60 Sek.", reelHochladen), kachel("kamera", "Foto-Beitrag", "Zeig deinen Fortschritt", () => beitragNeu())),
  ]);
}

/* ---------- Start ---------- */
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
window.addEventListener("hashchange", navigieren);
window.addEventListener("fit:angemeldet", async e => {
  S.ich = null; location.hash = "#/heute";
  if (e.detail && e.detail.neu) { await navigieren(); willkommen(); } else navigieren();
});
navigieren();
