/* Essen eintragen: Foto-KI, Beschreiben, Barcode, Von Hand – dazu Schnell-Dialoge fuer Wasser, Gewicht und Cardio. */
import {S, h, api, los, toast, leeren, icon, sheet, zurueck, kopf, zahl, eins, de, MAHLZEITEN, mahlzeitJetzt, verkleinern, linie, tagName} from "./core.js";

export const neuLaden = () => window.dispatchEvent(new HashChangeEvent("hashchange"));
const TITEL = {foto: "Foto-Scan", text: "Beschreiben", barcode: "Barcode", hand: "Von Hand"};

export async function essenSeite(ctx) {
  const modus = ctx.teile[0], inhalt = h("div", {class: "in"});
  leeren(ctx.box, zurueck("#/heute", "Heute"), kopf(TITEL[modus], "Essen eintragen"), inhalt);
  ({foto: fotoModus, text: textModus, barcode: barcodeModus, hand: () => ergebnis(inhalt, [{name: "", menge: "", kcal: "", eiweiss: "", kh: "", fett: ""}], "hand")})[modus](inhalt, ctx);
}

function ki(text) { return h("div", {class: "hinweisbox"}, icon("funke"), text); }

function fotoModus(box) {
  const datei = h("input", {type: "file", accept: "image/*", capture: "environment", hidden: true});
  const hinweis = h("input", {placeholder: "Hinweis (optional), z. B. „mit Hafermilch“", maxlength: 200});
  const knopf = h("button", {class: "btn", onclick: () => datei.click()}, icon("kamera"), "Foto aufnehmen");
  const auswahl = h("button", {class: "btn zweit", onclick: () => { datei.removeAttribute("capture"); datei.click(); datei.setAttribute("capture", "environment"); }}, "Aus Galerie wählen");
  const status = h("p", {class: "mut mitte", style: {minHeight: "24px", marginTop: "14px"}});
  datei.addEventListener("change", () => los(async () => {
    if (!datei.files[0]) return;
    knopf.disabled = auswahl.disabled = true; status.replaceChildren(h("span", {class: "denkt"}, h("i"), h("i"), h("i")), " KI schaut sich dein Essen an …");
    try {
      const bild = await verkleinern(datei.files[0]);
      const r = await api("POST", "schaetzen/bild", {bild: bild.split(",")[1], mime: "image/jpeg", hinweis: hinweis.value});
      if (!r.gerichte.length) { status.textContent = ""; return toast("Darauf erkenne ich nichts Essbares. Versuch ein näheres Foto.", true); }
      ergebnis(box, r.gerichte, "foto", r.hinweis, bild);
    } finally { knopf.disabled = auswahl.disabled = false; status.textContent = ""; datei.value = ""; }
  }));
  leeren(box, h("div", {class: "karte"}, h("div", {class: "feld"}, hinweis), h("div", {class: "raster"}, knopf, auswahl), status),
    ki("Das Foto geht einmal zur Schätzung an die KI und wird nicht gespeichert. Korrigiere die Werte danach, wenn sie nicht passen."));
}

function textModus(box) {
  const t = h("textarea", {placeholder: "Was hast du gegessen? Je genauer, desto besser: „2 Scheiben Vollkornbrot mit 20 g Butter und 3 Scheiben Gouda, dazu ein Kaffee mit Hafermilch“", maxlength: 600, "aria-label": "Mahlzeit beschreiben"});
  const knopf = h("button", {class: "btn", onclick: () => los(async () => {
    knopf.disabled = true;
    try {
      const r = await api("POST", "schaetzen/text", {text: t.value});
      if (!r.gerichte.length) return toast("Dazu konnte ich nichts schätzen.", true);
      ergebnis(box, r.gerichte, "text", r.hinweis);
    } finally { knopf.disabled = false; }
  })}, icon("funke"), "Schätzen");
  leeren(box, h("div", {class: "karte"}, t, h("div", {style: {height: "10px"}}), knopf), ki("Mengen und Zubereitung zu nennen macht die Schätzung deutlich genauer."));
}

function barcodeModus(box, ctx) {
  const video = h("video", {class: "scan-video", playsinline: true, muted: true, autoplay: true});
  const code = h("input", {inputmode: "numeric", placeholder: "oder Nummer eintippen", maxlength: 14, "aria-label": "Barcode-Nummer"});
  const suchen = c => los(async () => {
    if (S.leser) { try { S.leser.reset(); } catch (e) { /* weg */ } }
    toast("Suche Produkt …", false, 1400);
    produkt(box, await api("GET", "barcode/" + c.replace(/\D/g, "")));
  });
  leeren(box, h("div", {class: "karte"}, h("div", {class: "kamera-rahmen"}, video),
    h("div", {class: "zeile", style: {marginTop: "12px"}}, h("div", {class: "fuell"}, code), h("button", {class: "btn klein", onclick: () => suchen(code.value)}, "Suchen"))),
    h("p", {class: "hilfe mitte"}, "Daten: Open Food Facts (Community-Datenbank, nicht immer vollständig)."));
  if (!navigator.mediaDevices || !window.ZXing) { video.replaceWith(h("p", {class: "mut"}, "Kamera-Scan geht hier nicht – tippe die Nummer ein.")); return; }
  const leser = new window.ZXing.BrowserMultiFormatReader(); S.leser = leser;
  ctx.aufraeumen(() => { try { leser.reset(); } catch (e) { /* weg */ } });
  leser.decodeFromConstraints({video: {facingMode: "environment"}}, video, res => { if (res) { navigator.vibrate && navigator.vibrate(60); suchen(res.getText()); } })
    .catch(() => video.replaceWith(h("p", {class: "mut"}, "Kein Kamerazugriff (HTTPS und deine Erlaubnis nötig). Tippe die Nummer ein.")));
}

function produkt(box, p) {
  const gramm = h("input", {type: "number", inputmode: "decimal", value: p.portion_g || 100, min: 1, max: 5000});
  const zeige = h("div", {class: "tacho-fuss", style: {marginTop: "14px"}});
  const rechne = () => {
    const f = (Number(gramm.value) || 0) / 100;
    leeren(zeige, [["kcal", p.pro100.kcal, "var(--txt)"], ["Eiweiß", p.pro100.eiweiss, "var(--volt)"], ["KH", p.pro100.kh, "var(--ice)"], ["Fett", p.pro100.fett, "var(--gold)"]]
      .map(([n, w, c]) => h("div", {}, h("b", {style: {color: c}}, eins(w * f)), h("span", {class: "lab"}, n))));
    zeige.style.gridTemplateColumns = "repeat(4,1fr)";
  };
  gramm.addEventListener("input", rechne); rechne();
  leeren(box, h("div", {class: "karte"}, h("h2", {style: {textTransform: "none", letterSpacing: 0, fontSize: "24px"}}, p.name), h("div", {class: "mut"}, [p.marke, p.menge].filter(Boolean).join(" · ")),
    h("label", {class: "lab f"}, "Menge in Gramm" + (p.portion_g ? " (Portion laut Packung)" : "")), gramm, zeige),
    h("button", {class: "btn", onclick: () => { const f = (Number(gramm.value) || 0) / 100;
      ergebnis(box, [{name: p.name, menge: gramm.value + " g", kcal: p.pro100.kcal * f, eiweiss: p.pro100.eiweiss * f, kh: p.pro100.kh * f, fett: p.pro100.fett * f}], "barcode"); }}, "Weiter"));
}

/* Pruefen & eintragen (gemeinsam fuer alle Wege). Alles bleibt aenderbar. */
export function ergebnis(box, gerichte, quelle, hinweis, vorschau) {
  let mahlzeit = S.mahlzeit || mahlzeitJetzt(); S.mahlzeit = null;
  const num = (w, platz, rund) => h("input", {type: "number", inputmode: "decimal", step: "any", value: w === "" || w == null ? "" : rund(w), placeholder: platz, "aria-label": platz});
  const felder = gerichte.map(g => ({
    name: h("input", {value: g.name, placeholder: "Name", maxlength: 120, "aria-label": "Name"}), menge: h("input", {value: g.menge, placeholder: "Menge", maxlength: 40, "aria-label": "Menge"}),
    kcal: num(g.kcal, "kcal", zahl), eiweiss: num(g.eiweiss, "Eiweiß g", eins), kh: num(g.kh, "KH g", eins), fett: num(g.fett, "Fett g", eins)}));
  const chips = h("div", {class: "seg", style: {margin: "4px 0 14px"}});
  const male = () => leeren(chips, Object.entries(MAHLZEITEN).map(([k, n]) => h("button", {class: mahlzeit === k ? "an" : "", onclick: () => { mahlzeit = k; male(); }}, n)));
  male();
  const senden = h("button", {class: "btn", onclick: () => los(async () => {
    senden.disabled = true;
    try {
      for (const f of felder) await api("POST", "eintrag", {name: f.name.value, menge: f.menge.value, kcal: f.kcal.value, eiweiss: f.eiweiss.value, kh: f.kh.value, fett: f.fett.value, mahlzeit, datum: S.datum, quelle});
      toast("Eingetragen"); location.hash = "#/heute";
    } finally { senden.disabled = false; }
  })}, icon("haken"), "Eintragen");
  leeren(box, quelle === "hand" ? null : ki("Prüfe die Werte, du kannst alles ändern. " + (hinweis || "")),
    vorschau ? h("img", {src: vorschau, alt: "", style: {width: "100%", maxHeight: "200px", objectFit: "cover", borderRadius: "14px", marginBottom: "12px"}}) : null,
    felder.map(f => h("div", {class: "karte ergebnis-karte"}, h("div", {class: "feld"}, f.name), h("div", {class: "feld"}, f.menge),
      h("div", {class: "r2 raster", style: {marginBottom: "10px"}}, f.kcal, f.eiweiss), h("div", {class: "r2 raster"}, f.kh, f.fett))),
    h("div", {class: "lab", style: {margin: "14px 0 6px"}}, "Mahlzeit"), chips, senden);
}

/* ---------- Schnell-Dialoge ---------- */
export async function wasserSheet() {
  const t = await api("GET", "tag?datum=" + S.datum);
  let ml = t.wasser_ml;
  const glas = h("i", {}), zeig = h("b", {class: "zahl", style: {fontSize: "44px", lineHeight: 1}}), unter = h("div", {class: "mut"});
  const male = () => { glas.style.height = Math.min(100, ml / t.ziel_wasser * 100) + "%"; zeig.textContent = de(ml); unter.textContent = `von ${de(t.ziel_wasser)} ml · ${tagName(S.datum, {weekday: "long"})}`; };
  male();
  const add = n => () => los(async () => { ml = (await api("POST", "wasser", {ml: n, datum: S.datum})).ml; male(); });
  sheet("Wasser", zu => [
    h("div", {class: "wasser", style: {margin: "6px 0 18px"}}, h("div", {class: "glas"}, glas), h("div", {}, h("div", {class: "zeile"}, zeig, h("span", {class: "mut"}, "ml")), unter)),
    h("div", {class: "raster r3", style: {marginBottom: "10px"}}, [250, 500, 750].map(n => h("button", {class: "btn zweit", onclick: add(n)}, "+" + n))),
    h("div", {class: "knopfreihe"}, h("button", {class: "btn geist", onclick: add(-250)}, "−250 ml"), h("button", {class: "btn", onclick: () => { zu(); neuLaden(); }}, "Fertig"))]);
}

export function eintragSheet(e) {
  const f = (n, wert, extra = {}) => h("input", {value: wert ?? "", "aria-label": n, ...extra});
  const name = f("Name", e.name, {maxlength: 120}), menge = f("Menge", e.menge, {maxlength: 40, placeholder: "Menge (z. B. 150 g)"});
  const zahlFeld = (n, w) => f(n, w, {type: "number", inputmode: "decimal", step: "0.1"});
  const kcal = zahlFeld("Kalorien", e.kcal), ei = zahlFeld("Eiweiß g", e.eiweiss), kh = zahlFeld("Kohlenhydrate g", e.kh), fe = zahlFeld("Fett g", e.fett);
  let mz = e.mahlzeit;
  const chips = h("div", {class: "chips", style: {marginBottom: "12px"}});
  const male = () => leeren(chips, Object.entries(MAHLZEITEN).map(([k, n]) => h("button", {class: "chip" + (mz === k ? " an" : ""), onclick: () => { mz = k; male(); }}, n)));
  male();
  const lab = (t, x) => h("div", {}, h("label", {class: "lab f-lab"}, t), x);
  sheet("Eintrag bearbeiten", zu => [chips, h("div", {class: "feld"}, lab("Name", name)), h("div", {class: "feld"}, lab("Menge", menge)),
    h("div", {class: "raster r2", style: {marginBottom: "12px"}}, lab("Kalorien", kcal), lab("Eiweiß g", ei), lab("Kohlenhydrate g", kh), lab("Fett g", fe)),
    h("button", {class: "btn", onclick: () => los(async () => {
      await api("PUT", "eintrag/" + e.id, {name: name.value, menge: menge.value, kcal: kcal.value, eiweiss: ei.value, kh: kh.value, fett: fe.value, mahlzeit: mz});
      zu(); toast("Gespeichert"); neuLaden();
    })}, "Speichern")]);
}

export async function gewichtSheet() {
  const verlauf = await api("GET", "gewicht");
  const letzt = verlauf.length ? verlauf[verlauf.length - 1].kg : (S.ich.profil && S.ich.profil.gewicht) || "";
  const eingabe = h("input", {type: "number", inputmode: "decimal", step: "0.1", value: letzt, "aria-label": "Gewicht in kg", style: {fontSize: "34px", fontFamily: "var(--disp)", fontWeight: 700, textAlign: "center", minHeight: "64px"}});
  sheet("Gewicht", zu => [
    verlauf.length > 1 ? h("div", {style: {margin: "0 0 12px"}}, linie(verlauf.map(v => ({x: v.datum, y: v.kg})), "var(--volt)", 110),
      h("div", {class: "zeile zwischen mut klein"}, h("span", {}, tagName(verlauf[0].datum, {day: "numeric", month: "short"})), h("span", {}, `${eins(verlauf[verlauf.length - 1].kg - verlauf[0].kg) > 0 ? "+" : ""}${eins(verlauf[verlauf.length - 1].kg - verlauf[0].kg)} kg`))) : null,
    h("label", {class: "lab"}, "Heute in kg"), eingabe, h("div", {style: {height: "12px"}}),
    h("button", {class: "btn", onclick: () => los(async () => { await api("POST", "gewicht", {kg: eingabe.value, datum: S.datum}); zu(); toast("Gewicht gespeichert"); neuLaden(); })}, "Speichern")]);
}

const CARDIO = {laufen: "Laufen", gehen: "Gehen", radfahren: "Radfahren", schwimmen: "Schwimmen", krafttraining: "Krafttraining", yoga: "Yoga", hiit: "HIIT", fussball: "Fußball", wandern: "Wandern", tanzen: "Tanzen", sonstiges: "Sonstiges"};
export function cardioSheet() {
  let art = "laufen";
  const min = h("input", {type: "number", inputmode: "numeric", placeholder: "Minuten", "aria-label": "Minuten"});
  const kcal = h("input", {type: "number", inputmode: "numeric", placeholder: "kcal (optional)", "aria-label": "Kalorien"});
  const notiz = h("input", {placeholder: "Notiz (optional)", maxlength: 200});
  const chips = h("div", {class: "chips", style: {marginBottom: "12px"}});
  const male = () => leeren(chips, Object.entries(CARDIO).map(([k, n]) => h("button", {class: "chip" + (art === k ? " an" : ""), onclick: () => { art = k; male(); }}, n)));
  male();
  sheet("Cardio & Sport", zu => [chips, h("div", {class: "raster r2", style: {marginBottom: "10px"}}, min, kcal), h("div", {class: "feld"}, notiz),
    h("button", {class: "btn", onclick: () => los(async () => {
      const r = await api("POST", "training", {art, minuten: min.value, kcal: kcal.value, notiz: notiz.value, datum: S.datum});
      zu(); toast(`${CARDIO[r.art]} · ${r.minuten} Min · ${r.kcal} kcal verbrannt`); neuLaden();
    })}, "Eintragen")]);
}
