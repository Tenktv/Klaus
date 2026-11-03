/* Rezepte: Entdecken / Gespeichert / Meine, Detail mit Portions-Rechner, Ins-Tagebuch, Anlegen, KI-Generator (Pro). */
import {S, h, api, los, toast, leeren, icon, sheet, bestaetigen, kopf, zurueck, leer, zahl, eins, de, MAHLZEITEN, mahlzeitJetzt, istPro, proMarke, skelett, verkleinernBis} from "./core.js";

const TAGS = {fruehstueck: "Frühstück", mittag: "Mittag", abend: "Abend", snack: "Snack", dessert: "Dessert", "high-protein": "High Protein", "low-carb": "Low Carb", vegan: "Vegan", vegetarisch: "Vegetarisch", "meal-prep": "Meal Prep", schnell: "Schnell"};
const farbton = t => { let x = 0; for (const c of t) x = (x * 33 + c.charCodeAt(0)) % 360; return x; };

export function rezeptKarte(r) {
  return h("div", {class: "rezeptkarte", role: "link", tabindex: 0, onclick: () => { location.hash = "#/rezept/" + r.id; }, onkeydown: e => { if (e.key === "Enter") location.hash = "#/rezept/" + r.id; }},
    h("div", {class: "teller", style: {"--h": String(farbton(r.titel))}}, r.bild ? h("img", {src: r.bild, alt: "", loading: "lazy"}) : null, r.zeit_min ? h("span", {class: "badge zeit"}, icon("uhr", 12), `${r.zeit_min} Min`) : null),
    h("div", {class: "info"}, h("div", {class: "titel"}, r.titel), h("div", {class: "minimakros"}, h("span", {}, r.kcal, h("small", {}, "KCAL")), h("span", {class: "volt"}, r.eiweiss, h("small", {}, "E")), h("span", {class: "ice"}, r.kh, h("small", {}, "KH")))));
}

export async function rezepteSeite(ctx) {
  const tab = ctx.teile[0] || "entdecken";
  let q = "", tag = "";
  const raster = h("div", {}), suche = h("input", {placeholder: "Rezept oder Zutat suchen", "aria-label": "Rezepte suchen", maxlength: 40});
  const chips = h("div", {class: "chips", style: {margin: "10px -18px 12px"}});
  const male = () => leeren(chips, [["", "Alle"], ...Object.entries(TAGS)].map(([k, n]) => h("button", {class: "chip" + (tag === k ? " an" : ""), onclick: () => { tag = k; male(); laden(); }}, n)));
  async function laden() {
    leeren(raster, skelett(2, 180));
    const l = await api("GET", `rezepte?art=${tab}&q=${encodeURIComponent(q)}&tag=${tag}`);
    leeren(raster, l.length ? h("div", {class: "rezeptraster"}, l.map(rezeptKarte)) : leer(tab === "meine" ? "Noch keine eigenen Rezepte" : tab === "gespeichert" ? "Noch nichts gespeichert" : "Nichts gefunden",
      tab === "meine" ? "Leg dein erstes Rezept an – oder lass die KI eins entwerfen." : tab === "gespeichert" ? "Tippe in einem Rezept auf das Herz, dann findest du es hier." : "Versuch einen anderen Begriff oder Filter.",
      tab === "meine" ? h("button", {class: "btn klein", onclick: () => { location.hash = "#/rezept-neu"; }}, "Rezept anlegen") : null));
  }
  let t; suche.addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => { q = suche.value.trim(); laden(); }, 280); });
  const seg = h("div", {class: "seg", style: {marginBottom: "12px"}}, [["entdecken", "Entdecken"], ["gespeichert", "Gespeichert"], ["meine", "Meine"]].map(([k, n]) => h("button", {class: tab === k ? "an" : "", onclick: () => { location.hash = "#/rezepte/" + k; }}, n)));
  male();
  leeren(ctx.box, h("div", {class: "in"}, zurueck("#/heute", "Heute"), kopf("Rezepte", "Kochen für dein Ziel", h("button", {class: "ikon", "aria-label": "Rezept anlegen", onclick: () => { location.hash = "#/rezept-neu"; }}, icon("plus"))),
    seg, suche, chips, raster));
  await laden();
}

/* "150 g" x Faktor. Erste Zahl (auch 1,5 / ½) wird skaliert, der Rest bleibt. */
export function skaliere(menge, f) {
  if (f === 1) return menge;
  const m = /^(\d+(?:[.,]\d+)?|[½¼¾])(.*)$/.exec(menge.trim());
  if (!m) return menge;
  const basis = {"½": .5, "¼": .25, "¾": .75}[m[1]] ?? parseFloat(m[1].replace(",", "."));
  const neu = basis * f, rund = neu >= 20 ? Math.round(neu / 5) * 5 : neu >= 3 ? Math.round(neu * 2) / 2 : Math.round(neu * 4) / 4;
  return de(rund, 2) + m[2];
}

export async function rezeptSeite(ctx) {
  const r = await api("GET", "rezept/" + ctx.teile[0]);
  if (!ctx.aktuell()) return;
  let portionen = r.portionen, gespeichert = r.gespeichert;
  const zutaten = h("div", {}), zahlen = h("div", {class: "tacho-fuss", style: {gridTemplateColumns: "repeat(4,1fr)"}}), anzahl = h("b", {});
  const male = () => {
    const f = portionen / r.portionen;
    anzahl.textContent = de(portionen);
    leeren(zutaten, r.zutaten.map(z => h("div", {class: "zutat"}, h("span", {}, z.name), h("span", {}, z.menge ? skaliere(z.menge, f) : ""))));
  };
  const makros = h("div", {class: "tacho-fuss", style: {gridTemplateColumns: "repeat(4,1fr)", margin: "6px 0 18px"}}, [["kcal", r.kcal, "var(--txt)"], ["Eiweiß", r.eiweiss, "var(--volt)"], ["KH", r.kh, "var(--ice)"], ["Fett", r.fett, "var(--gold)"]]
    .map(([n, w, c]) => h("div", {}, h("b", {style: {color: c}}, w), h("span", {class: "lab"}, n))));
  const herz = h("button", {class: "ikon herz-knopf", style: {width: "56px", height: "52px"}, "aria-label": "Speichern", onclick: () => los(async () => { gespeichert = (await api("POST", `rezept/${r.id}/speichern`, {})).gespeichert; herz.style.color = gespeichert ? "var(--ember)" : ""; herz.firstChild.style.fill = gespeichert ? "var(--ember)" : "none"; toast(gespeichert ? "Gespeichert" : "Entfernt"); })}, icon("herz"));
  herz.style.color = gespeichert ? "var(--ember)" : ""; if (gespeichert) herz.firstChild.style.fill = "var(--ember)";
  const tagebuch = () => {
    let p = 1, mz = mahlzeitJetzt(); const zeig = h("b", {}, "1"), kc = h("div", {class: "mut"}), chips = h("div", {class: "seg", style: {margin: "10px 0 16px"}});
    const m2 = () => { zeig.textContent = de(p, 2); kc.textContent = `${de(r.kcal * p)} kcal · ${de(r.eiweiss * p)} g Eiweiß`; leeren(chips, Object.entries(MAHLZEITEN).map(([k, n]) => h("button", {class: mz === k ? "an" : "", onclick: () => { mz = k; m2(); }}, n))); };
    m2();
    sheet("Ins Tagebuch", zu => [h("div", {class: "disp", style: {fontSize: "22px", marginBottom: "12px"}}, r.titel), h("div", {class: "zeile zwischen"}, h("div", {class: "lab"}, "Portionen"),
      h("div", {class: "stepper"}, h("button", {onclick: () => { p = Math.max(.25, p - (p > 1 ? 1 : .25)); m2(); }, "aria-label": "Weniger"}, "−"), zeig, h("button", {onclick: () => { p = Math.min(20, p + (p >= 1 ? 1 : .25)); m2(); }, "aria-label": "Mehr"}, "+"))), kc, chips,
      h("button", {class: "btn", onclick: () => los(async () => { await api("POST", `rezept/${r.id}/essen`, {portionen: p, mahlzeit: mz, datum: S.datum}); zu(); toast("Im Tagebuch"); location.hash = "#/heute"; })}, icon("haken"), "Eintragen")]);
  };
  male();
  leeren(ctx.box, h("div", {class: "in"},
    h("div", {class: "rezept-held"}, h("div", {class: "teller", style: {"--h": String(farbton(r.titel))}}, r.bild ? h("img", {src: r.bild, alt: ""}) : null), h("button", {class: "zurueck", onclick: () => history.back()}, icon("links", 16), "Zurück")),
    h("div", {style: {padding: "0 18px calc(var(--tab) + var(--bot) + 28px)"}}, h("div", {class: "rezept-titel"}, h("div", {class: "zeile", style: {gap: "8px", marginBottom: "10px", flexWrap: "wrap"}}, r.offiziell ? h("span", {class: "badge volt"}, "Klesro Fit") : h("span", {class: "badge"}, "von " + r.autor),
      r.zeit_min ? h("span", {class: "badge"}, icon("uhr", 12), `${r.zeit_min} Min`) : null, r.tags.slice(0, 2).map(t => h("span", {class: "badge ice"}, TAGS[t] || t))), h("h1", {style: {fontSize: "40px"}}, r.titel)),
      r.beschreibung ? h("p", {class: "mut", style: {margin: "12px 0"}}, r.beschreibung) : null,
      h("div", {class: "lab", style: {marginTop: "14px"}}, "Pro Portion"), makros,
      h("div", {class: "knopfreihe", style: {marginBottom: "6px"}}, h("button", {class: "btn", onclick: tagebuch}, icon("plus"), "Ins Tagebuch"), herz),
      h("div", {class: "abschnitt"}, h("h2", {}, "Zutaten"), h("div", {class: "stepper"}, h("button", {onclick: () => { portionen = Math.max(1, portionen - 1); male(); }, "aria-label": "Weniger Portionen"}, "−"), anzahl, h("span", {class: "mut klein", style: {paddingRight: "12px"}}, "Port."), h("button", {onclick: () => { portionen = Math.min(30, portionen + 1); male(); }, "aria-label": "Mehr Portionen"}, "+"))),
      h("div", {class: "karte", style: {padding: "4px 16px"}}, zutaten),
      h("div", {class: "abschnitt"}, h("h2", {}, "Zubereitung")), r.schritte.map((s, i) => h("div", {class: "schritt"}, h("span", {class: "nr"}, i + 1), h("div", {}, s))),
      h("div", {class: "hilfe"}, r.offiziell ? "Nährwerte sind Richtwerte aus üblichen Tabellenwerten." : "Nährwerte stammen vom Ersteller bzw. einer KI-Schätzung."),
      r.eigen ? h("button", {class: "btn gefahr", style: {marginTop: "16px"}, onclick: async () => { if (await bestaetigen("Rezept löschen?", "Löschen", true)) los(async () => { await api("DELETE", "rezept/" + r.id); toast("Gelöscht"); location.hash = "#/rezepte/meine"; }); }}, "Rezept löschen") : null)));
}

/* ---------- Anlegen / KI ---------- */
export async function rezeptNeu(ctx) {
  const r = {titel: "", beschreibung: "", portionen: 2, zeit_min: 20, zutaten: [{name: "", menge: ""}], schritte: [""], kcal: "", eiweiss: "", kh: "", fett: "", tags: [], oeffentlich: false}; let bild = null;
  const f = (k, o = {}) => { const e = h("input", {value: r[k], ...o}); e.addEventListener("input", () => { r[k] = e.value; }); e.dataset.k = k; return e; };
  const zutBox = h("div", {class: "zutaten-bearbeiten"}), schrBox = h("div", {class: "zutaten-bearbeiten"}), tagBox = h("div", {class: "chips", style: {margin: "0 -18px"}});
  const felder = {};
  ["titel", "beschreibung", "portionen", "zeit_min", "kcal", "eiweiss", "kh", "fett"].forEach(k => {
    const num = !["titel", "beschreibung"].includes(k);
    felder[k] = f(k, {placeholder: {titel: "Titel", beschreibung: "Kurze Beschreibung (optional)", portionen: "Portionen", zeit_min: "Minuten", kcal: "kcal", eiweiss: "Eiweiß g", kh: "KH g", fett: "Fett g"}[k], "aria-label": k, ...(num ? {type: "number", inputmode: "decimal", step: "any"} : {maxlength: k === "titel" ? 80 : 300})});
  });
  const malen = () => {
    leeren(zutBox, r.zutaten.map((z, i) => { const n = h("input", {value: z.name, placeholder: "Zutat", maxlength: 80, "aria-label": "Zutat " + (i + 1)}), m = h("input", {value: z.menge, placeholder: "Menge", maxlength: 40, style: {maxWidth: "36%"}, "aria-label": "Menge " + (i + 1)});
      n.addEventListener("input", () => { z.name = n.value; }); m.addEventListener("input", () => { z.menge = m.value; });
      return h("div", {class: "zeile"}, n, m, h("button", {class: "ikon ohne", "aria-label": "Zutat entfernen", onclick: () => { r.zutaten.splice(i, 1); if (!r.zutaten.length) r.zutaten.push({name: "", menge: ""}); malen(); }}, icon("x"))); }),
      h("button", {class: "btn zweit klein", style: {width: "100%"}, onclick: () => { r.zutaten.push({name: "", menge: ""}); malen(); }}, "+ Zutat"));
    leeren(schrBox, r.schritte.map((s, i) => { const t = h("textarea", {value: s, placeholder: `Schritt ${i + 1}`, maxlength: 600, style: {minHeight: "64px"}, "aria-label": "Schritt " + (i + 1)}); t.addEventListener("input", () => { r.schritte[i] = t.value; });
      return h("div", {class: "zeile oben"}, h("b", {class: "zahl volt", style: {fontSize: "24px", paddingTop: "10px", width: "22px"}}, i + 1), h("div", {class: "fuell"}, t), h("button", {class: "ikon ohne", "aria-label": "Schritt entfernen", onclick: () => { r.schritte.splice(i, 1); if (!r.schritte.length) r.schritte.push(""); malen(); }}, icon("x"))); }),
      h("button", {class: "btn zweit klein", style: {width: "100%"}, onclick: () => { r.schritte.push(""); malen(); }}, "+ Schritt"));
    leeren(tagBox, Object.entries(TAGS).map(([k, n]) => h("button", {class: "chip" + (r.tags.includes(k) ? " an" : ""), onclick: () => { r.tags = r.tags.includes(k) ? r.tags.filter(x => x !== k) : [...r.tags, k]; malen(); }}, n)));
  };
  const fuellen = d => { for (const k of ["titel", "beschreibung", "portionen", "zeit_min", "kcal", "eiweiss", "kh", "fett"]) { r[k] = d[k] ?? r[k]; felder[k].value = r[k]; } r.zutaten = d.zutaten.length ? d.zutaten : r.zutaten; r.schritte = d.schritte.length ? d.schritte : r.schritte; r.tags = d.tags ? d.tags.split ? d.tags.split(",").filter(Boolean) : d.tags : r.tags; malen(); };
  const kiKnopf = h("button", {class: "karte klick zeile", style: {width: "100%", textAlign: "left", borderColor: "rgba(255,200,74,.35)"}, onclick: () => {
    if (!istPro()) { location.hash = "#/pro"; return; }
    const w = h("textarea", {placeholder: "z. B. „High-Protein-Abendessen mit Hähnchen und Reis, 25 Minuten, ohne Milch“", maxlength: 500, style: {minHeight: "100px"}});
    const zu = sheet("KI-Rezept", () => [h("p", {class: "mut", style: {marginBottom: "10px"}}, "Beschreib, was du essen möchtest: Zutaten, Ziel, Zeit, Unverträglichkeiten. Du kannst den Entwurf danach ändern."), w,
      h("button", {class: "btn", style: {marginTop: "12px"}, onclick: ev => los(async () => { ev.currentTarget.disabled = true; try { fuellen(await api("POST", "rezept/ki", {wunsch: w.value})); zu(); toast("Entwurf eingefügt. Prüf die Werte und speichere."); } finally { ev.currentTarget.disabled = false; } })}, icon("funke"), "Entwurf erstellen")]);
  }}, h("span", {class: "ikon", style: {color: "var(--gold)"}}, icon("funke")), h("div", {class: "fuell"}, h("div", {class: "disp", style: {fontSize: "19px"}}, "KI-Rezept erstellen"), h("div", {class: "mut klein"}, "Aus Wunsch oder Zutaten")), istPro() ? icon("rechts", 18) : proMarke());
  const datei = h("input", {type: "file", accept: "image/*", hidden: true}), vorschau = h("div", {});
  datei.addEventListener("change", () => los(async () => { if (!datei.files[0]) return; bild = await verkleinernBis(datei.files[0]); leeren(vorschau, h("img", {src: bild, alt: "", style: {width: "100%", maxHeight: "200px", objectFit: "cover", borderRadius: "12px", margin: "10px 0"}})); }));
  const oeff = h("input", {type: "checkbox", id: "oeff"}); oeff.addEventListener("change", () => { r.oeffentlich = oeff.checked; });
  malen();
  leeren(ctx.box, h("div", {class: "in"}, zurueck("#/rezepte/meine", "Rezepte"), kopf("Neues Rezept", "Selbst gemacht"), kiKnopf, h("div", {style: {height: "12px"}}),
    h("div", {class: "feld"}, felder.titel), h("div", {class: "feld"}, felder.beschreibung),
    h("div", {class: "r2 raster"}, h("div", {}, h("label", {class: "lab f-lab"}, "Portionen"), felder.portionen), h("div", {}, h("label", {class: "lab f-lab"}, "Minuten"), felder.zeit_min)),
    h("div", {class: "lab", style: {margin: "18px 0 8px"}}, "Kategorien"), tagBox, h("div", {class: "lab", style: {margin: "18px 0 8px"}}, "Zutaten"), zutBox,
    h("div", {class: "lab", style: {margin: "18px 0 8px"}}, "Zubereitung"), schrBox, h("div", {class: "lab", style: {margin: "18px 0 8px"}}, "Nährwerte pro Portion"),
    h("div", {class: "r2 raster", style: {marginBottom: "10px"}}, [["kcal", "Kalorien"], ["eiweiss", "Eiweiß g"], ["kh", "Kohlenhydrate g"], ["fett", "Fett g"]].map(([k, n]) => h("div", {}, h("label", {class: "lab f-lab"}, n), felder[k]))), datei, vorschau, h("button", {class: "btn zweit", style: {margin: "6px 0 12px"}, onclick: () => datei.click()}, icon("kamera"), "Foto hinzufügen"),
    h("label", {class: "zeile", for: "oeff", style: {cursor: "pointer", margin: "6px 0 16px"}}, oeff, h("span", {}, "Für alle Mitglieder sichtbar")),
    h("button", {class: "btn", onclick: ev => los(async () => { ev.currentTarget.disabled = true; try { const d = await api("POST", "rezepte", {...r, tags: r.tags, bild: bild ? bild.split(",")[1] : undefined}); toast("Rezept gespeichert"); location.hash = "#/rezept/" + d.id; } finally { ev.currentTarget.disabled = false; } })}, icon("haken"), "Speichern")));
}
