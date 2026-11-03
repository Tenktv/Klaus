/* Training: Uebersicht, Workout-Logger (Saetze, Pausen-Timer, Rekorde), Verlauf, Uebungs-Fortschritt, Routinen. */
import {$, S, h, api, los, toast, leeren, icon, sheet, bestaetigen, kopf, zurueck, leer, zahl, de, tagName, mmss, linie, heute} from "./core.js";
import {cardioSheet, neuLaden} from "./v_essen.js";

const G = {Brust: "var(--ember)", Rücken: "var(--ice)", Beine: "var(--volt)", Schultern: "var(--gold)", Arme: "#c58bff", Core: "#ff8fb0"};
export const UEBUNGEN = [
  ["Bankdrücken", "Brust"], ["Schrägbankdrücken", "Brust"], ["Kurzhantel-Bankdrücken", "Brust"], ["Fliegende", "Brust"], ["Dips", "Brust"], ["Liegestütze", "Brust"], ["Cable Crossover", "Brust"],
  ["Klimmzüge", "Rücken"], ["Latziehen", "Rücken"], ["Rudern vorgebeugt", "Rücken"], ["Kabelrudern", "Rücken"], ["Kreuzheben", "Rücken"], ["Face Pulls", "Rücken"], ["T-Bar-Rudern", "Rücken"],
  ["Kniebeuge", "Beine"], ["Frontkniebeuge", "Beine"], ["Beinpresse", "Beine"], ["Rumänisches Kreuzheben", "Beine"], ["Ausfallschritte", "Beine"], ["Beinstrecker", "Beine"], ["Beinbeuger", "Beine"],
  ["Hip Thrust", "Beine"], ["Wadenheben", "Beine"], ["Bulgarian Split Squat", "Beine"],
  ["Schulterdrücken", "Schultern"], ["Seitheben", "Schultern"], ["Frontheben", "Schultern"], ["Reverse Fly", "Schultern"], ["Arnold Press", "Schultern"], ["Shrugs", "Schultern"],
  ["Bizeps-Curls", "Arme"], ["Hammer-Curls", "Arme"], ["Trizepsdrücken", "Arme"], ["Skullcrusher", "Arme"], ["Französisches Drücken", "Arme"], ["Scott-Curls", "Arme"],
  ["Plank", "Core"], ["Crunches", "Core"], ["Beinheben hängend", "Core"], ["Russian Twist", "Core"], ["Ab-Roller", "Core"], ["Cable Crunch", "Core"],
];
const STARTER = [
  {name: "Push", uebungen: ["Bankdrücken", "Schrägbankdrücken", "Schulterdrücken", "Seitheben", "Trizepsdrücken"]},
  {name: "Pull", uebungen: ["Klimmzüge", "Rudern vorgebeugt", "Latziehen", "Face Pulls", "Bizeps-Curls"]},
  {name: "Beine", uebungen: ["Kniebeuge", "Rumänisches Kreuzheben", "Beinpresse", "Ausfallschritte", "Wadenheben"]},
  {name: "Ganzkörper", uebungen: ["Kniebeuge", "Bankdrücken", "Rudern vorgebeugt", "Schulterdrücken", "Plank"]},
];
const gruppeVon = n => (UEBUNGEN.find(u => u[0].toLowerCase() === n.toLowerCase()) || [])[1];
const KEY = "fit_workout";
const laden = () => { try { return JSON.parse(localStorage.getItem(KEY)); } catch (e) { return null; } };
const sichern = w => w ? localStorage.setItem(KEY, JSON.stringify(w)) : localStorage.removeItem(KEY);

/* ---------- Uebersicht ---------- */
export async function trainingSeite(ctx) {
  const [stat, verlauf, routinen, profil] = await Promise.all([api("GET", "trainingsstatistik"), api("GET", "workouts"), api("GET", "routinen"), api("GET", "profil/" + encodeURIComponent(S.ich.name))]);
  if (!ctx.aktuell()) return;
  const lauf = laden(), max = Math.max(...stat.woche.map(x => x.minuten), 30);
  const laufend = lauf ? h("button", {class: "karte klick zeile", style: {width: "100%", textAlign: "left", background: "var(--volt)", color: "var(--ink)", borderColor: "var(--volt)"}, onclick: () => { location.hash = "#/workout"; }},
    h("span", {class: "ikon", style: {background: "rgba(0,0,0,.12)", borderColor: "transparent", color: "var(--ink)"}}, icon("hantel")),
    h("div", {class: "fuell"}, h("div", {class: "disp", style: {fontSize: "21px"}}, "Workout läuft"), h("div", {style: {opacity: .75}}, `${lauf.name} · ${lauf.uebungen.length} Übungen · ${mmss((Date.now() - lauf.start) / 1000)}`)), icon("rechts", 22)) : null;
  const vorlage = r => h("div", {class: "liste-zeile", onclick: () => workoutStarten(r)}, h("span", {class: "ikon"}, icon("hantel")),
    h("div", {class: "fuell"}, h("div", {class: "disp", style: {fontSize: "20px"}}, r.name), h("div", {class: "mut klein"}, r.uebungen.slice(0, 4).join(" · ") + (r.uebungen.length > 4 ? " …" : ""))),
    r.id ? h("button", {class: "ikon ohne", "aria-label": "Routine löschen", onclick: async e => { e.stopPropagation(); if (await bestaetigen(`Routine „${r.name}“ löschen?`, "Löschen", true)) los(async () => { await api("DELETE", "routine/" + r.id); neuLaden(); }); }}, icon("papierkorb")) : icon("rechts", 20));
  leeren(ctx.box, h("div", {class: "in"},
    kopf("Training", "Dein Fortschritt", h("div", {class: "serie"}, icon("flamme"), String(profil.serie))),
    laufend, !lauf ? h("button", {class: "btn", style: {marginBottom: "14px"}, onclick: () => workoutStarten()}, icon("hantel"), "Leeres Workout starten") : null,
    h("div", {class: "karte"}, h("div", {class: "lab", style: {marginBottom: "14px"}}, "Diese Woche · Minuten"),
      h("div", {class: "woche7"}, stat.woche.map(x => h("div", {class: x.datum === heute() ? "heute" : ""}, h("i", {style: {height: Math.max(3, x.minuten / max * 70) + "px"}}), tagName(x.datum, {weekday: "narrow"})))),
      h("div", {class: "tacho-fuss", style: {marginTop: "14px", gridTemplateColumns: "repeat(3,1fr)"}}, h("div", {}, h("b", {}, de(stat.workouts)), h("span", {class: "lab"}, "Workouts")),
        h("div", {}, h("b", {}, de(stat.woche.reduce((a, x) => a + x.minuten, 0))), h("span", {class: "lab"}, "Minuten")), h("div", {}, h("b", {}, de(stat.volumen / 1000, 1)), h("span", {class: "lab"}, "Tonnen gesamt")))),
    h("div", {class: "abschnitt"}, h("h2", {}, "Routinen"), h("button", {onclick: () => cardioSheet()}, "+ Cardio")),
    h("div", {class: "karte", style: {padding: "4px 16px"}}, [...routinen, ...STARTER].map(vorlage)),
    stat.bestleistungen.length ? [h("div", {class: "abschnitt"}, h("h2", {}, "Bestleistungen")),
      h("div", {class: "karte", style: {padding: "4px 16px"}}, stat.bestleistungen.map(b => h("div", {class: "liste-zeile", onclick: () => { location.hash = "#/uebung/" + encodeURIComponent(b.uebung); }},
        h("span", {class: "gruppe-punkt", style: {background: G[gruppeVon(b.uebung)] || "var(--dim)"}}), h("div", {class: "fuell"}, b.uebung), h("b", {class: "zahl gold", style: {fontSize: "22px"}}, `${de(b.einrm, 1)} kg`), icon("rechts", 18))))] : null,
    h("div", {class: "abschnitt"}, h("h2", {}, "Verlauf")),
    verlauf.length ? verlauf.map(w => h("button", {class: "karte klick", style: {width: "100%", textAlign: "left"}, onclick: () => { location.hash = "#/workout/" + w.id; }},
      h("div", {class: "zeile zwischen"}, h("b", {class: "disp", style: {fontSize: "20px"}}, w.name), h("span", {class: "mut klein"}, tagName(w.datum, {weekday: "short", day: "numeric", month: "short"}))),
      h("div", {class: "mut", style: {margin: "4px 0 8px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis"}}, w.uebungen.join(" · ")),
      h("div", {class: "zeile", style: {gap: "16px"}}, h("span", {class: "badge"}, `${w.minuten} Min`), h("span", {class: "badge volt"}, `${de(w.volumen)} kg`), h("span", {class: "badge ember"}, `${w.kcal} kcal`)))) : leer("Noch kein Workout", "Starte oben dein erstes – Sätze, Gewichte und Rekorde werden automatisch festgehalten.")));
}

/* ---------- Workout starten / Logger ---------- */
export async function workoutStarten(vorlage) {
  const lauf = laden();
  if (lauf && !(await bestaetigen("Es läuft schon ein Workout. Verwerfen und neu starten?", "Neu starten", true))) { location.hash = "#/workout"; return; }
  sichern({name: vorlage ? vorlage.name : "Krafttraining", start: Date.now(), uebungen: (vorlage ? vorlage.uebungen : []).map(n => ({name: n, saetze: [{kg: "", wdh: "", fertig: false}]}))});
  location.hash = "#/workout";
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

let pause = null;   // {bis, dauer}
const PAUSE_STD = 90;
function pauseStarten(sek = PAUSE_STD) {
  pause = {bis: Date.now() + sek * 1000, dauer: sek};
  $("#timer").hidden = false; requestAnimationFrame(() => $("#timer").classList.add("an"));
  pauseMalen();
}
function pauseBeenden() { pause = null; const t = $("#timer"); t.classList.remove("an"); setTimeout(() => { if (!pause) t.hidden = true; }, 260); }
function pauseMalen() {
  const t = $("#timer");
  if (!pause) return;
  const rest = Math.max(0, Math.round((pause.bis - Date.now()) / 1000));
  leeren(t, h("span", {class: "lab", style: {color: "var(--ink)", opacity: .7}}, "Pause"), h("b", {class: "zahl"}, mmss(rest)), h("div", {class: "lauf"}, h("i", {style: {width: (rest / pause.dauer * 100) + "%"}})),
    h("button", {onclick: () => { pause.bis += 15000; pause.dauer += 15; pauseMalen(); }}, "+15"), h("button", {onclick: pauseBeenden}, "Skip"));
  if (rest <= 0) { navigator.vibrate && navigator.vibrate([200, 80, 200]); toast("Pause vorbei – nächster Satz!"); pauseBeenden(); }
}

const letzteCache = new Map();
async function letzte(name) {
  const k = name.toLowerCase();
  if (!letzteCache.has(k)) letzteCache.set(k, api("GET", "uebung/letzte?name=" + encodeURIComponent(name)).catch(() => []));
  return letzteCache.get(k);
}

export async function workoutSeite(ctx) {
  let w = laden();
  if (!w) { location.replace("#/training"); return; }
  const speichern = () => sichern(w);
  const uhr = h("div", {class: "uhr"}), uebungsBox = h("div", {});
  const takt = setInterval(() => { uhr.textContent = mmss((Date.now() - w.start) / 1000); if (pause) pauseMalen(); }, 500);
  ctx.aufraeumen(() => { clearInterval(takt); });
  const titel = h("input", {value: w.name, maxlength: 60, "aria-label": "Workout-Name", style: {fontFamily: "var(--disp)", fontWeight: 700, fontSize: "26px", textTransform: "uppercase", minHeight: "52px", background: "transparent", border: 0, padding: 0}});
  titel.addEventListener("input", () => { w.name = titel.value; speichern(); });

  function zeichneUebung(u, idx) {
    const kopfBox = h("div", {class: "uebung-kopf"}, h("span", {class: "gruppe-punkt", style: {background: G[gruppeVon(u.name)] || "var(--dim)"}}),
      h("h2", {onclick: () => { location.hash = "#/uebung/" + encodeURIComponent(u.name); }}, u.name),
      h("button", {class: "ikon ohne", "aria-label": "Übung entfernen", onclick: async () => { if (await bestaetigen(`„${u.name}“ entfernen?`, "Entfernen", true)) { w.uebungen.splice(idx, 1); speichern(); male(); } }}, icon("mehr")));
    const zeilen = h("div", {});
    const male = () => leeren(uebungsBox, w.uebungen.map(zeichneUebung));
    function zeichneSaetze() {
      leeren(zeilen, h("div", {class: "satzkopf lab"}, h("span", {class: "mitte"}, "Satz"), h("span", {}, "Vorher"), h("span", {class: "mitte"}, "kg"), h("span", {class: "mitte"}, "Wdh"), h("span", {})),
        u.saetze.map((s, i) => {
          const vorher = h("span", {class: "vor"}, "–");
          letzte(u.name).then(l => { const v = l[i]; if (v) { vorher.textContent = `${de(v.kg, 1)}×${v.wdh}`; if (s.kg === "" && !s.fertig) kg.placeholder = de(v.kg, 1); if (s.wdh === "" && !s.fertig) wdh.placeholder = String(v.wdh); } });
          const kg = h("input", {type: "number", inputmode: "decimal", step: "0.25", value: s.kg, placeholder: "kg", "aria-label": `Satz ${i + 1} Gewicht`});
          const wdh = h("input", {type: "number", inputmode: "numeric", value: s.wdh, placeholder: "Wdh", "aria-label": `Satz ${i + 1} Wiederholungen`});
          const ok = h("button", {class: "ok", "aria-label": `Satz ${i + 1} abhaken`, onclick: () => {
            if (!s.fertig) { s.kg = kg.value === "" ? (kg.placeholder !== "kg" ? kg.placeholder.replace(",", ".") : "") : kg.value; s.wdh = wdh.value === "" ? (wdh.placeholder !== "Wdh" ? wdh.placeholder : "") : wdh.value;
              if (s.wdh === "") return toast("Trag Wiederholungen ein.", true); s.fertig = true; pauseStarten(); } else s.fertig = false;
            speichern(); zeichneSaetze(); }}, icon("haken"));
          kg.addEventListener("input", () => { s.kg = kg.value; speichern(); }); wdh.addEventListener("input", () => { s.wdh = wdh.value; speichern(); });
          return h("div", {class: "satz" + (s.fertig ? " fertig" : "")}, h("span", {class: "nr"}, i + 1), vorher, kg, wdh, ok);
        }),
        h("div", {class: "knopfreihe", style: {marginTop: "6px"}}, h("button", {class: "btn zweit klein", style: {width: "100%"}, onclick: () => { const l = u.saetze[u.saetze.length - 1]; u.saetze.push({kg: l ? l.kg : "", wdh: l ? l.wdh : "", fertig: false}); speichern(); zeichneSaetze(); }}, "+ Satz"),
          u.saetze.length > 1 ? h("button", {class: "btn geist klein", style: {width: "100%"}, onclick: () => { u.saetze.pop(); speichern(); zeichneSaetze(); }}, "Letzten entfernen") : null));
    }
    zeichneSaetze();
    return h("div", {class: "karte"}, kopfBox, zeilen);
  }
  const malen = () => leeren(uebungsBox, w.uebungen.map(zeichneUebung));
  const hinzu = () => uebungWaehlen(name => { w.uebungen.push({name, saetze: [{kg: "", wdh: "", fertig: false}]}); speichern(); malen(); });
  malen();
  uhr.textContent = mmss((Date.now() - w.start) / 1000);
  leeren(ctx.box, h("div", {class: "in"}, h("div", {class: "zeile zwischen"}, zurueck("#/training", "Minimieren"), h("button", {class: "text-knopf bad", onclick: async () => { if (await bestaetigen("Workout verwerfen? Alle Sätze gehen verloren.", "Verwerfen", true)) { sichern(null); pauseBeenden(); location.hash = "#/training"; } }}, "Verwerfen")),
    h("div", {class: "kopf", style: {paddingTop: 0}}, h("div", {class: "fuell"}, h("div", {class: "lab"}, "Läuft seit"), uhr), h("button", {class: "btn klein", onclick: () => beenden(w, ctx)}, icon("haken"), "Fertig")),
    titel, h("div", {style: {height: "10px"}}), uebungsBox,
    h("button", {class: "btn zweit", onclick: hinzu}, icon("plus"), "Übung hinzufügen")));
}

function uebungWaehlen(gewaehlt) {
  let gruppe = "Alle", q = "";
  const liste = h("div", {}), suche = h("input", {placeholder: "Übung suchen oder neu eintippen", "aria-label": "Übung suchen", maxlength: 40});
  const chips = h("div", {class: "chips", style: {margin: "10px -18px"}});
  let zu;
  const pick = n => { zu(); gewaehlt(n); };
  const male = () => {
    leeren(chips, ["Alle", ...Object.keys(G)].map(g => h("button", {class: "chip" + (gruppe === g ? " an" : ""), onclick: () => { gruppe = g; male(); }}, g)));
    const t = UEBUNGEN.filter(u => (gruppe === "Alle" || u[1] === gruppe) && u[0].toLowerCase().includes(q.toLowerCase()));
    leeren(liste, q.trim() && !UEBUNGEN.some(u => u[0].toLowerCase() === q.trim().toLowerCase()) ? h("div", {class: "liste-zeile", onclick: () => pick(q.trim())}, h("span", {class: "ikon"}, icon("plus")), h("div", {class: "fuell"}, `„${q.trim()}“ als eigene Übung`)) : null,
      t.map(([n, g]) => h("div", {class: "liste-zeile", onclick: () => pick(n)}, h("span", {class: "gruppe-punkt", style: {background: G[g]}}), h("div", {class: "fuell"}, n), h("span", {class: "mut klein"}, g))));
  };
  suche.addEventListener("input", () => { q = suche.value; male(); });
  zu = sheet("Übung wählen", () => [suche, chips, liste]); male();
}

async function beenden(w, ctx) {
  const saetze = [];
  for (const u of w.uebungen) for (const s of u.saetze) if (s.fertig && Number(s.wdh) > 0) saetze.push({uebung: u.name, kg: Number(s.kg) || 0, wdh: Number(s.wdh)});
  if (!saetze.length) return toast("Hake mindestens einen Satz ab (der Haken rechts).", true);
  const minuten = Math.max(1, Math.round((Date.now() - w.start) / 60000));
  const r = await los(() => api("POST", "workout", {name: w.name, minuten, saetze, datum: heute()}));
  if (!r) return;
  sichern(null); pauseBeenden(); letzteCache.clear();
  const text = `${w.name} · ${minuten} Min · ${de(r.volumen)} kg Volumen` + (r.rekorde.length ? ` · Rekord: ${r.rekorde.map(x => `${x.uebung} ${de(x.einrm, 1)} kg`).join(", ")}` : "");
  sheet(null, zu => [h("div", {class: "mitte", style: {padding: "6px 0 14px"}}, h("div", {class: "lab volt"}, "Workout gespeichert"), h("h1", {style: {fontSize: "54px", marginTop: "8px"}}, "Stark."),
    h("div", {class: "tacho-fuss", style: {marginTop: "18px"}}, h("div", {}, h("b", {}, de(r.volumen)), h("span", {class: "lab"}, "kg Volumen")), h("div", {}, h("b", {}, r.saetze), h("span", {class: "lab"}, "Sätze")), h("div", {}, h("b", {class: "ember"}, r.kcal), h("span", {class: "lab"}, "kcal")))),
    r.rekorde.length ? h("div", {class: "karte", style: {borderColor: "rgba(255,200,74,.4)"}}, h("div", {class: "lab gold", style: {marginBottom: "8px"}}, "Neue Rekorde"),
      r.rekorde.map(x => h("div", {class: "zeile zwischen", style: {padding: "5px 0"}}, h("span", {}, icon("pokal", 18), " ", x.uebung), h("b", {class: "gold zahl", style: {fontSize: "20px"}}, `${de(x.einrm, 1)} kg`)))) : null,
    h("div", {class: "knopfreihe", style: {marginBottom: "10px"}},
      h("button", {class: "btn zweit", onclick: () => los(async () => { await api("POST", "beitrag", {art: "training", text}); toast("Im Feed geteilt"); })}, icon("teilen"), "Teilen"),
      h("button", {class: "btn zweit", onclick: () => los(async () => { await api("POST", "routine", {name: w.name, uebungen: [...new Set(saetze.map(s => s.uebung))]}); toast("Als Routine gespeichert"); })}, "Routine")),
    h("button", {class: "btn", onclick: () => { zu(); location.hash = "#/training"; }}, "Fertig")], {zu: () => { location.hash = "#/training"; }});
}

/* ---------- Detail / Fortschritt ---------- */
export async function workoutDetail(ctx) {
  const w = await api("GET", "workout/" + ctx.teile[0]);
  if (!ctx.aktuell()) return;
  const je = new Map();
  for (const s of w.saetze_liste) { if (!je.has(s.uebung)) je.set(s.uebung, []); je.get(s.uebung).push(s); }
  leeren(ctx.box, h("div", {class: "in"}, zurueck("#/training", "Training"), kopf(w.name, tagName(w.datum, {weekday: "long", day: "numeric", month: "long"}).toUpperCase()),
    h("div", {class: "karte"}, h("div", {class: "tacho-fuss"}, h("div", {}, h("b", {}, w.minuten), h("span", {class: "lab"}, "Minuten")), h("div", {}, h("b", {}, de(w.volumen)), h("span", {class: "lab"}, "kg Volumen")), h("div", {}, h("b", {class: "ember"}, w.kcal), h("span", {class: "lab"}, "kcal")))),
    [...je].map(([n, ss]) => h("div", {class: "karte"}, h("div", {class: "uebung-kopf"}, h("span", {class: "gruppe-punkt", style: {background: G[gruppeVon(n)] || "var(--dim)"}}), h("h2", {onclick: () => { location.hash = "#/uebung/" + encodeURIComponent(n); }}, n), icon("rechts", 18)),
      ss.map(s => h("div", {class: "zeile zwischen", style: {padding: "6px 0", borderTop: "1px solid var(--line)"}}, h("span", {class: "mut"}, `Satz ${s.nr}`), h("b", {class: "zahl", style: {fontSize: "21px"}}, `${de(s.kg, 2)} kg × ${s.wdh}`))))),
    h("button", {class: "btn gefahr", style: {marginTop: "10px"}, onclick: async () => { if (await bestaetigen("Dieses Workout löschen?", "Löschen", true)) los(async () => { await api("DELETE", "workout/" + w.id); toast("Gelöscht"); location.hash = "#/training"; }); }}, "Workout löschen")));
}

export async function uebungSeite(ctx) {
  const name = decodeURIComponent(ctx.teile[0]);
  const v = await api("GET", "uebung/verlauf?name=" + encodeURIComponent(name));
  if (!ctx.aktuell()) return;
  leeren(ctx.box, h("div", {class: "in"}, zurueck(null), kopf(name, gruppeVon(name) || "Übung"),
    v.punkte.length ? [h("div", {class: "karte"}, h("div", {class: "zeile zwischen"}, h("div", {class: "lab"}, "Geschätztes Maximum (1RM)"), h("b", {class: "zahl gold", style: {fontSize: "30px"}}, `${de(v.rekord, 1)} kg`)),
      h("div", {style: {marginTop: "10px"}}, linie(v.punkte.map(p => ({x: p.datum, y: p.einrm})), "var(--gold)", 150)),
      h("div", {class: "hilfe"}, "Berechnet aus deinem besten Satz je Training (Epley-Formel). Je höher die Kurve, desto stärker.")),
      h("div", {class: "abschnitt"}, h("h2", {}, "Einheiten")),
      h("div", {class: "karte", style: {padding: "4px 16px"}}, [...v.punkte].reverse().map(p => h("div", {class: "liste-zeile", style: {cursor: "default"}}, h("div", {class: "fuell mut"}, tagName(p.datum, {day: "numeric", month: "short", year: "2-digit"})),
        h("b", {class: "zahl", style: {fontSize: "21px"}}, `${de(p.kg, 2)} kg × ${p.wdh}`), h("span", {class: "mut klein", style: {width: "74px", textAlign: "right"}}, `≈ ${de(p.einrm, 1)}`))))]
      : leer("Noch keine Daten", "Sobald du diese Übung in einem Workout machst, siehst du hier deinen Fortschritt.")));
}
