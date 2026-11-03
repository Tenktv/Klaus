/* Heute: Kalorien-Tacho, Makros, Wasser, Gewicht, Training, Mahlzeiten, Rezept-Tipps. */
import {S, h, api, los, leeren, icon, kopf, avatar, tacho, linie, zahl, de, heute, tagName, MAHLZEITEN, proMarke, istPro} from "./core.js";
import {wasserSheet, gewichtSheet, eintragSheet, neuLaden} from "./v_essen.js";
import {rezeptKarte} from "./v_rezepte.js";

export async function heuteSeite(ctx) {
  const [t, woche, profil, gewicht, rezepte] = await Promise.all([
    api("GET", "tag?datum=" + S.datum), api("GET", "woche"), api("GET", "profil/" + encodeURIComponent(S.ich.name)), api("GET", "gewicht"),
    api("GET", "rezepte?art=entdecken").catch(() => [])]);
  if (!ctx.aktuell()) return;
  const ziel = t.ziele.kcal, ist = zahl(t.summe.kcal), verbrannt = t.verbrannt, budget = ziel + verbrannt, uebrig = budget - ist;
  const istHeute = S.datum === heute();

  // Datumsleiste: die letzten 7 Tage, Punkt = an dem Tag wurde etwas eingetragen
  const leiste = h("div", {class: "datumsleiste", role: "tablist"}, woche.map(x => h("button", {class: x.datum === S.datum ? "an" : "", role: "tab", onclick: () => { S.datum = x.datum; neuLaden(); }},
    tagName(x.datum, {weekday: "short"}).replace(".", ""), h("b", {}, new Date(x.datum + "T12:00").getDate()), h("i", {class: x.kcal > 0 ? "da" : ""}))));

  const zahlGross = h("div", {class: "gross"}, de(Math.abs(uebrig)));
  const tachoKarte = h("div", {class: "karte", style: {paddingBottom: "10px"}},
    h("div", {class: "tacho"}, tacho(ist, budget), h("div", {class: "mitte-zahl"}, zahlGross, h("div", {class: "lab unter" + (uebrig < 0 ? " ember" : "")}, uebrig < 0 ? "kcal drüber" : "kcal übrig"))),
    h("div", {class: "tacho-fuss"}, h("div", {}, h("b", {}, de(ist)), h("span", {class: "lab"}, "Gegessen")),
      h("div", {}, h("b", {class: "ember"}, de(verbrannt)), h("span", {class: "lab"}, "Verbrannt")), h("div", {}, h("b", {}, de(ziel)), h("span", {class: "lab"}, "Ziel"))));

  const makro = (name, w, z, farbe) => h("div", {class: "makro" + (w > z * 1.15 ? " ueber" : ""), style: {"--c": farbe}},
    h("div", {class: "kopfz"}, h("span", {class: "lab"}, name), h("span", {}, h("b", {}, zahl(w)), h("span", {class: "mut"}, ` / ${zahl(z)} g`))), h("div", {class: "bar"}, h("i", {style: {width: Math.min(100, z ? w / z * 100 : 0) + "%"}})));
  const makroKarte = h("div", {class: "karte"}, makro("Eiweiß", t.summe.eiweiss, t.ziele.eiweiss, "var(--volt)"), makro("Kohlenhydrate", t.summe.kh, t.ziele.kh, "var(--ice)"), makro("Fett", t.summe.fett, t.ziele.fett, "var(--gold)"));

  const wasserKarte = h("button", {class: "karte klick", style: {textAlign: "left", margin: 0}, onclick: () => los(wasserSheet), "aria-label": "Wasser eintragen"},
    h("div", {class: "lab", style: {marginBottom: "10px"}}, "Wasser"),
    h("div", {class: "wasser"}, h("div", {class: "glas", style: {width: "34px", height: "50px"}}, h("i", {style: {height: Math.min(100, t.wasser_ml / t.ziel_wasser * 100) + "%"}})),
      h("div", {}, h("b", {class: "zahl", style: {fontSize: "30px"}}, de(t.wasser_ml)), h("div", {class: "mut klein"}, `von ${de(t.ziel_wasser)} ml`))));
  const letzt = gewicht.length ? gewicht[gewicht.length - 1] : null;
  const gewichtKarte = h("button", {class: "karte klick", style: {textAlign: "left", margin: 0}, onclick: () => los(gewichtSheet), "aria-label": "Gewicht eintragen"},
    h("div", {class: "lab", style: {marginBottom: "10px"}}, "Gewicht"),
    letzt ? [h("div", {class: "zeile"}, h("b", {class: "zahl", style: {fontSize: "30px"}}, de(letzt.kg, 1)), h("span", {class: "mut"}, "kg")),
      gewicht.length > 1 ? linie(gewicht.slice(-14).map(v => ({x: v.datum, y: v.kg})), "var(--volt)", 46) : h("div", {class: "mut klein"}, "Trag morgen wieder ein.")]
      : [h("div", {class: "mut"}, "Noch kein Eintrag"), h("div", {class: "volt fett", style: {marginTop: "8px"}}, "+ Wiegen")]);

  const trainingKarte = t.training.length
    ? h("div", {class: "karte"}, h("div", {class: "zeile zwischen", style: {marginBottom: "6px"}}, h("div", {class: "lab"}, "Training"), h("b", {class: "ember zahl", style: {fontSize: "20px"}}, `${de(verbrannt)} kcal`)),
      t.training.map(x => h("div", {class: "eintrag"}, h("div", {class: "fuell"}, h("div", {class: "t"}, x.notiz || x.art.charAt(0).toUpperCase() + x.art.slice(1)), h("div", {class: "mut klein"}, `${x.minuten} Min`)),
        h("div", {class: "kcal ember"}, x.kcal), h("button", {class: "ikon ohne", "aria-label": "Löschen", onclick: () => los(async () => { await api("DELETE", "training/" + x.id); neuLaden(); })}, icon("x")))))
    : h("button", {class: "karte klick zeile", style: {width: "100%", textAlign: "left"}, onclick: () => { location.hash = "#/training"; }},
      h("span", {class: "ikon"}, icon("hantel")), h("div", {class: "fuell"}, h("div", {class: "disp", style: {fontSize: "19px"}}, "Noch kein Training"), h("div", {class: "mut klein"}, "Workout starten oder Cardio eintragen")), icon("rechts", 20));

  const mahlzeiten = Object.entries(MAHLZEITEN).map(([k, n]) => {
    const liste = t.eintraege.filter(e => e.mahlzeit === k), summe = liste.reduce((a, e) => a + e.kcal, 0);
    return h("div", {class: "karte"}, h("div", {class: "mahlzeit-kopf"}, h("h2", {}, n), summe ? h("span", {class: "mut fett"}, `${de(summe)} kcal`) : null,
      h("button", {class: "ikon", "aria-label": n + " hinzufügen", onclick: () => { S.mahlzeit = k; location.hash = "#/essen/foto"; }}, icon("plus"))),
      liste.length ? liste.map(e => h("div", {class: "eintrag"}, h("div", {class: "fuell klick", role: "button", tabindex: "0", "aria-label": e.name + " bearbeiten", onclick: () => eintragSheet(e)}, h("div", {class: "t"}, e.name),
        h("div", {class: "kurz"}, e.menge ? h("span", {style: {"--c": "var(--dim)"}}, e.menge) : null, h("span", {style: {"--c": "var(--volt)"}}, `${zahl(e.eiweiss)} E`), h("span", {style: {"--c": "var(--ice)"}}, `${zahl(e.kh)} KH`), h("span", {style: {"--c": "var(--gold)"}}, `${zahl(e.fett)} F`))),
        h("div", {class: "kcal"}, zahl(e.kcal)), h("button", {class: "ikon ohne", "aria-label": "Bearbeiten", onclick: () => eintragSheet(e)}, icon("stift", 18)), h("button", {class: "ikon ohne", "aria-label": "Löschen", onclick: () => los(async () => { await api("DELETE", "eintrag/" + e.id); neuLaden(); })}, icon("x"))))
        : h("div", {class: "mut klein", style: {padding: "6px 0 2px"}}, "Noch nichts eingetragen"));
  });

  const maxK = Math.max(...woche.map(x => x.kcal), ziel);
  const wocheKarte = h("div", {class: "karte"}, h("div", {class: "lab", style: {marginBottom: "12px"}}, "Letzte 7 Tage · Kalorien"),
    h("div", {class: "woche7"}, woche.map(x => h("div", {class: x.datum === heute() ? "heute" : ""}, h("i", {style: {height: Math.max(3, x.kcal / maxK * 70) + "px", background: x.kcal > ziel * 1.1 ? "var(--ember)" : ""}}), tagName(x.datum, {weekday: "narrow"})))));

  const serie = h("div", {class: "serie", title: "Tage in Folge aktiv"}, icon("flamme"), String(profil.serie));
  leeren(ctx.box, h("div", {class: "in"},
    kopf(istHeute ? "Heute" : tagName(S.datum, {weekday: "long"}), tagName(S.datum, {weekday: "long", day: "numeric", month: "long"}).toUpperCase(),
      [serie, h("button", {onclick: () => { location.hash = "#/ich"; }, "aria-label": "Profil und Einstellungen"}, avatar(S.ich.name))]),
    leiste, tachoKarte, makroKarte, h("div", {class: "raster r2", style: {marginBottom: "12px"}}, wasserKarte, gewichtKarte), trainingKarte,
    rezepte.length ? [h("div", {class: "abschnitt"}, h("h2", {}, "Rezepte"), h("a", {href: "#/rezepte"}, "Alle")),
      h("div", {class: "chips"}, rezepte.slice(0, 6).map(r => h("div", {style: {width: "164px", flex: "none"}}, rezeptKarte(r))))] : null,
    istPro() ? null : h("button", {class: "karte pro-held klick", style: {width: "100%", textAlign: "left", marginTop: "14px"}, onclick: () => { location.hash = "#/pro"; }},
      h("div", {class: "zeile"}, proMarke(), h("div", {class: "fuell"}, h("div", {class: "disp", style: {fontSize: "20px"}}, "KI-Coach & eigene KI"), h("div", {class: "mut klein"}, "Frag nach Plänen, Rezepten und Fortschritt"))), null),
    h("div", {class: "abschnitt"}, h("h2", {}, "Mahlzeiten")), mahlzeiten, wocheKarte));
}
