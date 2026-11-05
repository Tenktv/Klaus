/* Ich: Profil, Ziele, Pro, eigene KI, KI-Coach, Schnittstelle, Admin. */
import {S, h, api, los, toast, leeren, icon, sheet, bestaetigen, kopf, zurueck, leer, avatar, de, tagName, vor, istPro, proMarke, abmelden} from "./core.js";
import {verbrauchSheet, VERBRAUCH} from "./v_essen.js";

const row = (ikon, titel, sub, tun, rechts) => h("div", {class: "liste-zeile", onclick: tun}, h("span", {class: "ikon"}, icon(ikon)), h("div", {class: "fuell"}, h("div", {class: "fett"}, titel), sub ? h("div", {class: "mut klein"}, sub) : null), rechts || icon("rechts", 18));

export async function ichSeite(ctx) {
  const [p, ich] = await Promise.all([api("GET", "profil/" + encodeURIComponent(S.ich.name)), api("GET", "ich")]);
  if (!ctx.aktuell()) return;
  S.ich = ich;
  const bio = h("input", {value: ich.bio, placeholder: "Über mich (max. 160 Zeichen)", maxlength: 160, "aria-label": "Über mich"});
  const speichern = () => los(async () => { await api("PUT", "ich", {bio: bio.value}); toast("Gespeichert"); });
  bio.addEventListener("change", speichern);
  const rang = h("input", {type: "checkbox", checked: ich.rangliste, id: "rang"}); rang.addEventListener("change", () => los(async () => { await api("PUT", "ich", {rangliste: rang.checked}); toast(rang.checked ? "Du bist in der Rangliste" : "Du bist nicht mehr in der Rangliste"); }));
  const z = ich.ziele, plan = ich.plan;
  leeren(ctx.box, h("div", {class: "in"}, zurueck("#/heute", "Heute"),
    h("div", {class: "profil-kopf", style: {marginTop: "8px"}}, avatar(ich.name, "gross"), h("div", {class: "fuell"}, h("h1", {style: {fontSize: "32px"}}, ich.name), h("div", {style: {marginTop: "8px"}}, plan.pro ? proMarke() : h("span", {class: "badge"}, "Free")))),
    h("div", {class: "karte"}, h("div", {class: "zahlen3", style: {margin: 0}}, h("div", {}, h("b", {class: "ember"}, p.serie), h("span", {class: "lab"}, "Serie")), h("div", {}, h("b", {}, de(p.trainings)), h("span", {class: "lab"}, "Trainings")), h("div", {}, h("b", {}, de(p.folger)), h("span", {class: "lab"}, "Follower")), h("div", {}, h("b", {}, de(p.beitraege)), h("span", {class: "lab"}, "Beiträge"))),
      p.abzeichen.length ? h("div", {class: "abzeichen", style: {marginTop: "14px"}}, p.abzeichen.map(a => h("span", {class: "badge gold"}, a.name))) : null,
      h("div", {class: "trenner"}), bio, h("label", {class: "zeile", for: "rang", style: {marginTop: "14px", cursor: "pointer"}}, rang, h("span", {}, "In der Wochen-Rangliste mitmachen")),
      h("button", {class: "btn zweit klein", style: {width: "100%", marginTop: "14px"}, onclick: () => { location.hash = "#/profil/" + encodeURIComponent(ich.name); }}, "Öffentliches Profil ansehen")),
    h("div", {class: "abschnitt"}, h("h2", {}, "Einstellungen")),
    h("div", {class: "karte", style: {padding: "4px 16px"}},
      row("ziel", "Tagesziele", `${de(z.kcal)} kcal · ${z.eiweiss} g Eiweiß`, () => { location.hash = "#/ziele"; }),
      row("blitz", "Klesro Fit Pro", plan.pro ? (plan.admin ? "Aktiv (Admin)" : "Aktiv bis " + tagName(new Date(plan.bis * 1000).toISOString().slice(0, 10), {day: "numeric", month: "long", year: "numeric"})) : "Coach, eigene KI, mehr Reels", () => { location.hash = "#/pro"; }, plan.pro ? null : proMarke()),
      row("funke", "KI-Coach", "Fragen zu Training & Ernährung", () => { location.hash = "#/coach"; }, plan.pro ? null : proMarke()),
      row("schluessel", "Eigene KI", ich.ki || plan.pro ? "Eigenen API-Schlüssel nutzen" : "Gemini, OpenAI, Claude …", () => { location.hash = "#/ki"; }, plan.pro ? null : proMarke()),
      row("schuh", "Apple Health", "Schritte automatisch übernehmen", () => { location.hash = "#/apple-health"; }),
      row("regler", "Schnittstelle", "Für Klaus, Telegram, Kurzbefehle", () => { location.hash = "#/schnittstelle"; })),
    ich.admin ? h("div", {class: "karte", style: {padding: "4px 16px"}}, row("sperren", "Admin", "Nutzer, Pro-Codes, Meldungen", () => { location.hash = "#/admin"; })) : null,
    h("div", {class: "abschnitt"}, h("h2", {}, "Daten & Konto")),
    h("div", {class: "karte", style: {padding: "4px 16px"}},
      row("hoch", "Daten exportieren", "Alles als Datei (DSGVO)", () => los(async () => { const d = await api("GET", "export"); const a = h("a", {href: URL.createObjectURL(new Blob([JSON.stringify(d, null, 2)], {type: "application/json"})), download: "klesro-fit-export.json"}); document.body.append(a); a.click(); a.remove(); })),
      row("info", "Datenschutz", "Was mit deinen Daten passiert", () => sheet("Datenschutz", () => [h("p", {class: "mut", style: {marginBottom: "10px"}}, "Gesundheitsdaten (Essen, Gewicht, Training) sind besonders geschützt. Sie bleiben privat: Nur Name, Bio, Serie und Trainingsminuten sind öffentlich sichtbar, wenn du sie teilst."),
        h("p", {class: "mut", style: {marginBottom: "10px"}}, "Fotos zur Essens-Schätzung gehen einmal an eine KI und werden nicht gespeichert. Feed-Fotos und Reels liegen auf dem Server, Standort-Daten werden entfernt. Ein eigener KI-Schlüssel wird nur serverseitig gespeichert und nie angezeigt."),
        h("p", {class: "mut"}, "Du kannst alles exportieren oder dein Konto samt aller Daten jederzeit löschen.")])),
      row("papierkorb", "Konto löschen", "Löscht alle deine Daten endgültig", async () => { if (await bestaetigen("Konto und ALLE Daten endgültig löschen?", "Endgültig löschen", true)) los(async () => { await api("DELETE", "ich"); abmelden(); }); }),
      row("links", "Abmelden", null, abmelden))));
}

/* ---------- Ziele ---------- */
export function zieleFormular(fertig) {
  const w = {geschlecht: "m", aktivitaet: "leicht", ziel: "halten"};
  const alter = h("input", {type: "number", inputmode: "numeric", placeholder: "Alter", "aria-label": "Alter"}), gr = h("input", {type: "number", inputmode: "numeric", placeholder: "Größe in cm", "aria-label": "Größe"}), ge = h("input", {type: "number", inputmode: "decimal", placeholder: "Gewicht in kg", "aria-label": "Gewicht"});
  if (S.ich && S.ich.profil) { alter.value = S.ich.profil.alter || ""; gr.value = S.ich.profil.groesse || ""; ge.value = S.ich.profil.gewicht || ""; w.geschlecht = S.ich.profil.geschlecht || "m"; w.aktivitaet = S.ich.profil.aktivitaet || "leicht"; w.ziel = S.ich.profil.ziel || "halten"; }
  const seg = (opts, k) => { const b = h("div", {class: "seg"}); const m = () => leeren(b, opts.map(([v, n]) => h("button", {class: w[k] === v ? "an" : "", onclick: () => { w[k] = v; m(); }}, n))); m(); return b; };
  return h("div", {}, h("div", {class: "lab", style: {margin: "4px 0 6px"}}, "Geschlecht (für die Berechnung)"), seg([["m", "Männlich"], ["w", "Weiblich"]], "geschlecht"),
    h("div", {class: "r3 raster", style: {margin: "12px 0"}}, alter, gr, ge),
    h("div", {class: "lab", style: {margin: "4px 0 6px"}}, "Aktivität im Alltag"), seg([["wenig", "Wenig"], ["leicht", "Leicht"], ["mittel", "Mittel"], ["viel", "Viel"]], "aktivitaet"),
    h("div", {class: "lab", style: {margin: "14px 0 6px"}}, "Ziel"), seg([["abnehmen", "Abnehmen"], ["halten", "Halten"], ["zunehmen", "Aufbauen"]], "ziel"),
    h("button", {class: "btn", style: {marginTop: "16px"}, onclick: () => los(async () => { await api("PUT", "ich", {berechnen: {...w, alter: alter.value, groesse: gr.value, gewicht: ge.value}}); S.ich = await api("GET", "ich"); fertig && fertig(); })}, "Ziele berechnen"));
}

export async function zieleSeite(ctx) {
  const z = S.ich.ziele, f = {};
  const feld = (k, n, c) => { f[k] = h("input", {type: "number", inputmode: "numeric", value: z[k], "aria-label": n}); return h("div", {}, h("label", {class: "lab", style: {color: c}}, n), f[k]); };
  leeren(ctx.box, h("div", {class: "in"}, zurueck("#/ich", "Ich"), kopf("Tagesziele", "Dein Plan"),
    h("div", {class: "karte"}, h("div", {class: "lab", style: {marginBottom: "10px"}}, "Berechnen lassen"), zieleFormular(() => { toast("Ziele aktualisiert"); location.hash = "#/ich"; })),
    h("div", {class: "karte"}, h("div", {class: "lab", style: {marginBottom: "10px"}}, "Oder selbst festlegen"), h("div", {class: "r2 raster"}, feld("kcal", "Kalorien"), feld("eiweiss", "Eiweiß g", "var(--volt)"), feld("kh", "Kohlenhydrate g", "var(--ice)"), feld("fett", "Fett g", "var(--gold)")),
      h("button", {class: "btn zweit", style: {marginTop: "14px"}, onclick: () => los(async () => { await api("PUT", "ich", {kcal: f.kcal.value, eiweiss: f.eiweiss.value, kh: f.kh.value, fett: f.fett.value}); S.ich = await api("GET", "ich"); toast("Gespeichert"); location.hash = "#/ich"; })}, "Speichern")),
    h("div", {class: "karte"}, h("div", {class: "lab", style: {marginBottom: "10px"}}, "Verbrannte Kalorien (Training, Schritte)"),
      h("div", {class: "mut klein", style: {marginBottom: "10px"}}, "Sollen sie dein Tagesbudget erhöhen? Unbewusstes „Zurückessen“ bremst den Fortschritt."),
      h("button", {class: "btn zweit", onclick: () => verbrauchSheet((S.ich.profil || {}).verbrauch || "nein", () => window.dispatchEvent(new HashChangeEvent("hashchange")))}, VERBRAUCH[(S.ich.profil || {}).verbrauch || "nein"])),
    h("p", {class: "hilfe"}, "Richtwerte nach Mifflin-St-Jeor, keine medizinische Beratung. Unter 1.200 kcal am Tag rechnet die App nie.")));
}

/* ---------- Pro ---------- */
export async function proSeite(ctx) {
  const plan = (S.ich = await api("GET", "ich")).plan, g = plan.grenzen;
  if (!ctx.aktuell()) return;
  const code = h("input", {placeholder: "FIT-XXXX-XXXX-XXXX", maxlength: 20, autocapitalize: "characters", "aria-label": "Pro-Code", style: {textTransform: "uppercase", letterSpacing: ".1em"}});
  const v = (t, s) => h("div", {class: "vorteil"}, icon("haken"), h("div", {}, h("div", {class: "fett"}, t), s ? h("div", {class: "mut klein"}, s) : null));
  leeren(ctx.box, h("div", {class: "in"}, zurueck("#/ich", "Ich"),
    h("div", {class: "karte pro-held"}, proMarke(), h("h1", {style: {fontSize: "44px", margin: "12px 0 6px"}}, "Klesro Fit", h("br"), h("span", {class: "gold"}, "Pro")),
      h("p", {class: "mut", style: {maxWidth: "30ch"}}, plan.pro ? (plan.admin ? "Du bist Admin und hast Pro unbegrenzt." : "Pro ist aktiv bis " + tagName(new Date(plan.bis * 1000).toISOString().slice(0, 10), {day: "numeric", month: "long", year: "numeric"}) + ".") : "Mehr KI, mehr Reels und dein eigener KI-Anbieter.")),
    h("div", {class: "karte", style: {marginTop: "14px"}}, v("KI-Coach", "Fragt dich aus, kennt deine Daten, gibt Pläne und Tipps"), v("Eigene KI", "Nutze deinen eigenen API-Schlüssel (Gemini, OpenAI, Claude, Groq, OpenRouter) – ohne Tageslimit"),
      v("KI-Rezeptgenerator", "Rezepte aus Wunsch oder Zutaten, mit Nährwerten"), v(`${g.ki > 8 ? g.ki : 60} statt 8 KI-Schätzungen pro Tag`, "Foto- und Text-Erkennung über den Server"), v("20 statt 3 Reels pro Tag"), v("Pro-Abzeichen im Profil")),
    plan.pro ? null : h("div", {class: "karte"}, h("div", {class: "lab", style: {marginBottom: "8px"}}, "Code einlösen"), code, h("button", {class: "btn", style: {marginTop: "10px"}, onclick: () => los(async () => { const d = await api("POST", "pro/einloesen", {code: code.value}); toast(d.text); S.ich = await api("GET", "ich"); location.hash = "#/pro"; window.dispatchEvent(new HashChangeEvent("hashchange")); })}, "Freischalten"),
      h("p", {class: "hilfe"}, "Pro gibt es derzeit mit Einladungs-Code. Bezahlen im Abo folgt später.")),
    plan.pro ? h("div", {class: "knopfreihe"}, h("button", {class: "btn zweit", onclick: () => { location.hash = "#/coach"; }}, "KI-Coach"), h("button", {class: "btn zweit", onclick: () => { location.hash = "#/ki"; }}, "Eigene KI")) : null));
}

function sperre(text) {
  return h("div", {class: "karte pro-held"}, proMarke(), h("div", {class: "disp", style: {fontSize: "26px", margin: "10px 0 6px"}}, text), h("p", {class: "mut"}, "Das gibt es mit Pro."), h("button", {class: "btn", style: {marginTop: "12px"}, onclick: () => { location.hash = "#/pro"; }}, "Pro ansehen"));
}

/* ---------- Eigene KI ---------- */
export async function kiSeite(ctx) {
  const st = await api("GET", "ki");
  if (!ctx.aktuell()) return;
  let auswahl = st.eigene ? st.eigene.anbieter : st.anbieter[0].id;
  const key = h("input", {type: "password", placeholder: st.eigene ? "Neuer Schlüssel (leer = unverändert nicht möglich)" : "API-Schlüssel einfügen", autocomplete: "off", autocapitalize: "off", spellcheck: false, "aria-label": "API-Schlüssel"});
  const modell = h("input", {placeholder: "Modell (leer = Standard)", value: st.eigene ? st.eigene.modell : "", maxlength: 80, "aria-label": "Modell"});
  const liste = h("div", {}), hilfe = h("p", {class: "hilfe"});
  const male = () => {
    leeren(liste, st.anbieter.map(a => h("div", {class: "anbieter" + (auswahl === a.id ? " an" : ""), onclick: () => { auswahl = a.id; if (!st.eigene || st.eigene.anbieter !== a.id) modell.value = ""; modell.placeholder = `Standard: ${a.modell}`; male(); }}, h("span", {class: "punkt"}), h("div", {class: "fuell"}, h("div", {class: "fett"}, a.name), h("div", {class: "mut klein"}, `Standard: ${a.modell}`)))));
    const a = st.anbieter.find(x => x.id === auswahl); leeren(hilfe, "Schlüssel erstellen: ", h("a", {href: "https://" + a.hilfe, target: "_blank", rel: "noopener noreferrer", class: "volt"}, a.hilfe));
  };
  male();
  const gesperrt = !istPro();
  leeren(ctx.box, h("div", {class: "in"}, zurueck("#/ich", "Ich"), kopf("Eigene KI", "Dein Anbieter, dein Schlüssel", proMarke()),
    gesperrt ? sperre("Eigene KI nutzen") : null,
    h("div", {class: "sperre" + (gesperrt ? " zu" : "")}, h("div", {class: "hinweisbox"}, icon("schloss"), "Der Schlüssel wird nur auf dem Server gespeichert und nie wieder angezeigt. Anfragen gehen direkt von dort an deinen Anbieter und werden von dir bezahlt – ohne Tageslimit. Du kannst den Schlüssel bei deinem Anbieter jederzeit widerrufen."),
      st.eigene ? h("div", {class: "karte", style: {borderColor: "rgba(212,255,58,.35)"}}, h("div", {class: "zeile zwischen"}, h("div", {}, h("div", {class: "lab volt"}, "Aktiv"), h("div", {class: "fett", style: {marginTop: "4px"}}, `${st.anbieter.find(a => a.id === st.eigene.anbieter).name} · ${st.eigene.modell}`), h("div", {class: "mut klein"}, "Schlüssel " + st.eigene.schluessel)),
        h("button", {class: "btn klein", onclick: ev => los(async () => { const knopf = ev.currentTarget; knopf.disabled = true; try { toast((await api("POST", "ki/test", {})).text); } finally { knopf.disabled = false; } })}, "Testen"))) : null,
      h("div", {class: "lab", style: {margin: "6px 0 8px"}}, "Anbieter"), liste, h("div", {class: "feld"}, key), h("div", {class: "feld"}, modell), hilfe,
      h("button", {class: "btn", style: {margin: "14px 0 10px"}, onclick: () => los(async () => { const d = await api("PUT", "ki", {anbieter: auswahl, schluessel: key.value, modell: modell.value}); key.value = ""; toast(d.text, false, 4500); window.dispatchEvent(new HashChangeEvent("hashchange")); })}, "Speichern"),
      st.eigene ? h("button", {class: "btn gefahr", onclick: async () => { if (await bestaetigen("Eigene KI entfernen und den Schlüssel löschen?", "Entfernen", true)) los(async () => { toast((await api("DELETE", "ki")).text); window.dispatchEvent(new HashChangeEvent("hashchange")); }); }}, "Entfernen und Schlüssel löschen") : null)));
}

/* ---------- Coach ---------- */
export async function coachSeite(ctx) {
  const verlauf = [], blasen = h("div", {style: {paddingBottom: "96px"}}), eingabe = h("input", {placeholder: "Frag deinen Coach …", maxlength: 500, "aria-label": "Frage an den Coach"});
  const VORSCHLAEGE = ["Wie komme ich auf mein Eiweiß-Ziel?", "Plan für 3 Trainingstage pro Woche", "Was esse ich vor dem Training?", "Warum stagniert mein Gewicht?"];
  const zeichne = () => leeren(blasen, verlauf.length ? verlauf.map(n => h("div", {class: "blase" + (n.rolle === "du" ? " eigen" : "")}, n.rolle === "coach" ? h("small", {}, "Coach") : null, n.text))
    : [h("p", {class: "mut", style: {marginBottom: "12px"}}, "Der Coach kennt deine Ziele, deine letzten Tage, dein Gewicht und deine Bestleistungen."), VORSCHLAEGE.map(v => h("button", {class: "chip", style: {marginRight: "8px", marginBottom: "8px"}, onclick: () => frage(v)}, v))]);
  async function frage(text) {
    if (!text.trim()) return; eingabe.value = "";
    const bisher = verlauf.slice(-6); verlauf.push({rolle: "du", text}); zeichne();
    const denkt = h("div", {class: "blase"}, h("small", {}, "Coach"), h("span", {class: "denkt"}, h("i"), h("i"), h("i"))); blasen.append(denkt); window.scrollTo(0, document.body.scrollHeight);
    try { const d = await api("POST", "coach", {frage: text, verlauf: bisher}); verlauf.push({rolle: "coach", text: d.antwort}); }
    catch (e) { verlauf.pop(); toast(e.message, true); eingabe.value = text; }
    zeichne(); window.scrollTo(0, document.body.scrollHeight);
  }
  eingabe.addEventListener("keydown", e => { if (e.key === "Enter") frage(eingabe.value); });
  zeichne();
  leeren(ctx.box, h("div", {class: "in"}, zurueck("#/ich", "Ich"), kopf("Coach", "KI · kennt deine Daten", proMarke()), istPro() ? blasen : sperre("KI-Coach")),
    istPro() ? h("div", {class: "eingabeleiste"}, eingabe, h("button", {class: "btn", onclick: () => frage(eingabe.value), "aria-label": "Senden"}, icon("senden"))) : null,
    istPro() ? h("p", {class: "hilfe mitte", style: {padding: "0 18px"}}, "Dein Training und deine Ernährung gehen als Zusammenfassung an die KI. Keine medizinische Beratung.") : null);
}

/* ---------- Schnittstelle ---------- */
export async function schnittstelleSeite(ctx) {
  const l = await api("GET", "zugang");
  if (!ctx.aktuell()) return;
  const neu = h("input", {placeholder: "Name, z. B. Klaus oder Kurzbefehl", maxlength: 40, "aria-label": "Name des Schlüssels"});
  leeren(ctx.box, h("div", {class: "in"}, zurueck("#/ich", "Ich"), kopf("Schnittstelle", "Klaus, Telegram, Kurzbefehle"),
    h("div", {class: "hinweisbox"}, icon("schluessel"), "Mit einem Schlüssel kann zum Beispiel Klaus (Telegram: /kalorien, /essen 2 Eier) oder ein iPhone-Kurzbefehl in deinem Namen Essen eintragen. Der Schlüssel wird nur einmal angezeigt."),
    h("div", {class: "karte"}, h("div", {class: "feld"}, neu), h("button", {class: "btn", onclick: () => los(async () => {
      const d = await api("POST", "zugang", {name: neu.value});
      sheet("Dein Schlüssel", zu => [h("p", {class: "mut", style: {marginBottom: "10px"}}, "Kopiere ihn jetzt – er wird nie wieder angezeigt."), h("div", {class: "karte", style: {wordBreak: "break-all", fontFamily: "monospace", fontSize: "14px"}}, d.token),
        h("button", {class: "btn", onclick: () => navigator.clipboard.writeText(d.token).then(() => toast("Kopiert"), () => toast("Markiere den Text und kopiere ihn von Hand.", true))}, "Kopieren")], {zu: () => window.dispatchEvent(new HashChangeEvent("hashchange"))});
    })}, "Schlüssel erstellen")),
    l.length ? h("div", {class: "karte", style: {padding: "4px 16px"}}, l.map(z => h("div", {class: "liste-zeile", style: {cursor: "default"}}, h("span", {class: "ikon"}, icon("schluessel")), h("div", {class: "fuell"}, h("div", {class: "fett"}, z.name), h("div", {class: "mut klein"}, z.zuletzt ? "Zuletzt " + vor(z.zuletzt) : "Noch nie benutzt")),
      h("button", {class: "ikon ohne", "aria-label": "Schlüssel löschen", onclick: async () => { if (await bestaetigen(`Schlüssel „${z.name}“ löschen?`, "Löschen", true)) los(async () => { await api("DELETE", "zugang/" + z.hash); window.dispatchEvent(new HashChangeEvent("hashchange")); }); }}, icon("papierkorb")))))
      : leer("Noch kein Schlüssel", "Erstelle einen, wenn du Klaus oder einen Kurzbefehl verbinden willst.")));
}

/* ---------- Apple Health (iPhone-Kurzbefehl) ---------- */
export async function appleHealthSeite(ctx) {
  const url = location.origin + "/api/schritte";
  const kopier = (text, name) => h("button", {class: "btn zweit klein", onclick: () => navigator.clipboard.writeText(text).then(() => toast(name + " kopiert"), () => toast("Markiere den Text und kopiere ihn von Hand.", true))}, "Kopieren");
  const zeile = (n, titel, text, extra) => h("div", {class: "karte", style: {marginBottom: "10px"}}, h("div", {class: "zeile", style: {gap: "12px", alignItems: "flex-start"}},
    h("b", {class: "disp volt", style: {fontSize: "22px", minWidth: "22px"}}, String(n)), h("div", {class: "fuell"}, h("div", {class: "fett"}, titel), h("div", {class: "mut klein", style: {marginTop: "3px"}}, text), extra || null)));
  const schluesselBox = h("div", {});
  const erstellen = h("button", {class: "btn", onclick: () => los(async () => {
    const d = await api("POST", "zugang", {name: "Apple Health"});
    leeren(schluesselBox, h("div", {class: "karte", style: {wordBreak: "break-all", fontFamily: "monospace", fontSize: "13px", margin: "10px 0"}}, "Bearer " + d.token), kopier("Bearer " + d.token, "Schlüssel"),
      h("div", {class: "mut klein", style: {marginTop: "6px"}}, "Nur jetzt sichtbar – kopiere ihn gleich in den Kurzbefehl."));
  })}, "Schlüssel für Apple Health erstellen");
  leeren(ctx.box, h("div", {class: "in"}, zurueck("#/heute", "Heute"), kopf("Apple Health", "Schritte automatisch"),
    h("div", {class: "hinweisbox"}, icon("schuh"), "Eine Web-App darf Apple Health nicht direkt lesen – das erlaubt Apple nur echten App-Store-Apps. Mit einem Kurzbefehl schickt dein iPhone deine Schritte aber jeden Tag von allein hierher."),
    zeile(1, "Schlüssel erstellen", "Er gehört nur zu deinem Konto und darf nur Daten eintragen, die du auch selbst eintragen könntest.", h("div", {style: {marginTop: "10px"}}, erstellen, schluesselBox)),
    zeile(2, "Kurzbefehle-App → Automation → „+“", "„Tageszeit“ wählen, z. B. 22:00 täglich, „Sofort ausführen“ einschalten."),
    zeile(3, "Aktion „Health-Beispiele finden“", "Typ: Schritte · Startdatum: ist heute · Sortieren egal. Danach „Statistik berechnen“ → Summe."),
    zeile(4, "Aktion „Inhalte von URL abrufen“", "Methode POST · Anfragetext JSON · Feld „schritte“ = Ergebnis der Statistik.", h("div", {style: {marginTop: "10px"}}, h("div", {class: "karte", style: {wordBreak: "break-all", fontFamily: "monospace", fontSize: "13px", margin: "0 0 8px"}}, url), kopier(url, "Adresse"))),
    zeile(5, "Kopfzeile hinzufügen", "Name „Authorization“, Wert: der kopierte Schlüssel („Bearer kt_…“). Für mehr Aktualität eine zweite Automation um 12:00 anlegen."),
    h("div", {class: "mut klein", style: {padding: "4px 4px 24px"}}, "Der Tageswert wird bei jedem Senden überschrieben, nicht addiert. Die Kalorien aus Schritten sind eine grobe Schätzung (ca. 0,04 kcal je Schritt bei 70 kg). Läufe und Spaziergänge, die du als Training einträgst, zählt die App an Tagen mit Schrittdaten nicht doppelt.")));
}

/* ---------- Admin ---------- */
export async function adminSeite(ctx) {
  if (!S.ich.admin) { location.replace("#/heute"); return; }
  const [nutzer, meldungen] = await Promise.all([api("GET", "admin/nutzer"), api("GET", "meldungen")]);
  if (!ctx.aktuell()) return;
  const tage = h("input", {type: "number", inputmode: "numeric", value: 30, "aria-label": "Tage"});
  const jetzt = Date.now() / 1000;
  leeren(ctx.box, h("div", {class: "in"}, zurueck("#/ich", "Ich"), kopf("Admin", "Betreiber"),
    h("div", {class: "karte"}, h("div", {class: "lab", style: {marginBottom: "8px"}}, "Pro-Code erstellen"), h("div", {class: "zeile"}, h("div", {class: "fuell"}, tage), h("span", {class: "mut"}, "Tage"),
      h("button", {class: "btn klein", onclick: () => los(async () => { const d = await api("POST", "pro/code", {tage: tage.value}); sheet("Code", zu => [h("p", {class: "mut", style: {marginBottom: "8px"}}, `${d.tage} Tage Pro – einmal einlösbar:`), h("div", {class: "karte mitte disp", style: {fontSize: "30px", letterSpacing: ".08em", userSelect: "all"}}, d.code),
        h("button", {class: "btn", onclick: () => navigator.clipboard.writeText(d.code).then(() => toast("Kopiert"))}, "Kopieren")]); })}, "Erstellen"))),
    h("div", {class: "abschnitt"}, h("h2", {}, `Nutzer (${nutzer.length})`)),
    h("div", {class: "karte", style: {padding: "4px 16px"}}, nutzer.map(n => h("div", {class: "liste-zeile", style: {cursor: "default"}}, avatar(n.name, "mittel"), h("div", {class: "fuell"}, h("div", {class: "fett"}, n.name, n.gesperrt ? h("span", {class: "badge ember", style: {marginLeft: "8px"}}, "gesperrt") : null),
      h("div", {class: "mut klein"}, `${n.eintraege} Einträge · ${n.beitraege} Beiträge · Pro ${n.pro_bis > jetzt ? "bis " + tagName(new Date(n.pro_bis * 1000).toISOString().slice(0, 10), {day: "numeric", month: "short"}) : "–"}`)),
      h("button", {class: "btn klein zweit", onclick: () => los(async () => { toast((await api("POST", "pro/vergeben", {name: n.name, tage: Number(tage.value) || 30})).text); window.dispatchEvent(new HashChangeEvent("hashchange")); })}, "+ Pro")))),
    h("div", {class: "abschnitt"}, h("h2", {}, `Meldungen (${meldungen.length})`)),
    meldungen.length ? meldungen.map(m => h("div", {class: "karte"}, h("div", {class: "zeile zwischen"}, h("b", {}, `${m.art} #${m.ziel}`), h("span", {class: "mut klein"}, vor(m.erstellt))), m.grund ? h("div", {class: "mut klein", style: {margin: "4px 0 8px"}}, m.grund) : null,
      h("button", {class: "btn klein zweit", onclick: async () => { if (await bestaetigen(`${m.art} #${m.ziel} ausblenden?`, "Ausblenden", true)) los(async () => { toast((await api("POST", "loeschen", {art: m.art, id: m.ziel})).text); }); }}, "Inhalt ausblenden"))) : leer("Keine Meldungen", "Alles ruhig.")));
}
