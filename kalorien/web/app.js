"use strict";
/* Kalorien-App – eine Seite, reines JavaScript. Nutzertexte kommen nur per textContent in die Seite (nie innerHTML). */
const $ = s => document.querySelector(s);
const MAHLZEITEN = {fruehstueck: "Frühstück", mittag: "Mittag", abend: "Abend", snack: "Snacks"};
const S = {token: localStorage.getItem("kt"), ich: null, datum: heute(), seite: "heute", timer: null, scanner: null};

function heute(d = new Date()) { return new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10); }
function h(tag, att, ...kinder) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(att || {})) {
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kinder.flat()) if (k != null && k !== false) e.append(k.nodeType ? k : document.createTextNode(String(k)));
  return e;
}
function meldung(t, ms = 3500) { const m = $("#meldung"); m.textContent = t; m.classList.add("sichtbar"); clearTimeout(meldung.t); meldung.t = setTimeout(() => m.classList.remove("sichtbar"), ms); }
async function api(methode, pfad, daten) {
  const r = await fetch("/api/" + pfad, {method: methode, headers: {...(S.token ? {Authorization: "Bearer " + S.token} : {}), ...(daten ? {"Content-Type": "application/json"} : {})}, body: daten ? JSON.stringify(daten) : undefined});
  let d = {}; try { d = await r.json(); } catch (e) {}
  if (r.status === 401 && S.token) { abmelden(false); throw new Error("Bitte neu anmelden."); }
  if (!r.ok) throw new Error(d.fehler || "Fehler " + r.status);
  return d;
}
async function los(fn) { try { return await fn(); } catch (e) { meldung(e.message || "Das ging nicht."); } }
function zahl(v) { return Math.round(Number(v) || 0); }
function seite(inhalt) { stopp(); $("#inhalt").replaceChildren(...[].concat(inhalt).flat(Infinity).filter(Boolean)); window.scrollTo(0, 0); }
function stopp() { clearInterval(S.timer); S.timer = null; if (S.scanner) { try { S.scanner.reset(); } catch (e) {} S.scanner = null; } }
function vor(sek) { const d = Math.max(0, Date.now() / 1000 - sek); return d < 60 ? "gerade eben" : d < 3600 ? Math.floor(d / 60) + " Min" : d < 86400 ? Math.floor(d / 3600) + " Std" : Math.floor(d / 86400) + " T"; }

/* ---------------- Anmeldung ---------------- */
function anmeldeseite() {
  $("#leiste").hidden = true;
  const name = h("input", {placeholder: "Name (wird im Forum angezeigt)", autocomplete: "username", maxlength: 24});
  const pw = h("input", {type: "password", placeholder: "Passwort (mind. 8 Zeichen)", autocomplete: "current-password"});
  const ok = h("input", {type: "checkbox", style: "width:auto;margin:0 8px 0 0"});
  const senden = art => () => los(async () => {
    if (art === "registrieren" && !ok.checked) return meldung("Bitte bestätige die Regeln und den Datenschutz.");
    const d = await api("POST", art, {name: name.value, passwort: pw.value});
    S.token = d.token; localStorage.setItem("kt", d.token); start();
  });
  seite(h("div", {}, h("h1", {}, "Kalorien"), h("p", {class: "leise"}, "Essen fotografieren, beschreiben oder scannen – die App schätzt Kalorien und Nährwerte."),
    h("div", {class: "karte"}, name, pw,
      h("label", {class: "reihe", style: "align-items:flex-start;color:var(--text)"}, ok, h("span", {class: "leise"}, "Ich bin mindestens 16, achte in Forum und Chat auf Respekt (keine Beleidigungen, keine Werbung) und habe verstanden, dass Fotos zur Schätzung an eine KI gehen und nicht gespeichert werden. Meine Gesundheitsdaten kann ich jederzeit exportieren und löschen.")),
      h("button", {class: "knopf", onclick: senden("registrieren")}, "Konto erstellen"),
      h("button", {class: "knopf zweit", onclick: senden("anmelden")}, "Ich habe schon ein Konto")),
    h("p", {class: "leise mitte"}, "Die Schätzungen sind Richtwerte, keine medizinische Beratung.")));
}
function abmelden(zeige = true) { S.token = null; S.ich = null; localStorage.removeItem("kt"); if (zeige) anmeldeseite(); else setTimeout(anmeldeseite, 0); }

/* ---------------- Heute ---------------- */
async function heuteSeite() {
  const t = await api("GET", "tag?datum=" + S.datum), woche = await api("GET", "woche");
  const ziel = t.ziele.kcal, ist = zahl(t.summe.kcal), anteil = Math.min(1, ist / ziel), r = 80, u = 2 * Math.PI * r;
  const ring = h("div", {class: "ring"});
  ring.innerHTML = `<svg viewBox="0 0 200 200"><circle cx="100" cy="100" r="${r}" fill="none" stroke="var(--rand)" stroke-width="18"/><circle cx="100" cy="100" r="${r}" fill="none" stroke="${ist > ziel ? "var(--rot)" : "var(--gruen)"}" stroke-width="18" stroke-linecap="round" stroke-dasharray="${u * anteil} ${u}"/></svg>`;
  ring.append(h("div", {class: "zahl"}, h("b", {}, ist > ziel ? "+" + (ist - ziel) : ziel - ist), h("span", {class: "leise"}, ist > ziel ? "kcal drüber" : "kcal übrig"), h("span", {class: "leise"}, `${ist} von ${ziel}`)));
  const makro = (n, w, z) => h("div", {}, h("b", {}, zahl(w) + " g"), h("span", {class: "leise"}, n), h("div", {class: "balken"}, h("i", {style: `width:${Math.min(100, w / z * 100)}%`})));
  const gruppen = Object.entries(MAHLZEITEN).map(([k, n]) => {
    const liste = t.eintraege.filter(e => e.mahlzeit === k); if (!liste.length) return null;
    return h("div", {class: "karte"}, h("div", {class: "reihe"}, h("b", {}, n), h("span", {class: "leise", style: "text-align:right"}, zahl(liste.reduce((a, e) => a + e.kcal, 0)) + " kcal")),
      liste.map(e => h("div", {class: "eintrag"}, h("div", {}, h("div", {}, e.name), h("small", {}, [e.menge, `E ${zahl(e.eiweiss)} · K ${zahl(e.kh)} · F ${zahl(e.fett)}`].filter(Boolean).join(" · "))),
        h("div", {style: "text-align:right"}, h("b", {}, zahl(e.kcal)), h("br"), h("button", {"aria-label": "Löschen", onclick: () => los(async () => { await api("DELETE", "eintrag/" + e.id); heuteSeite(); })}, "×")))));
  });
  const max = Math.max(...woche.map(x => x.kcal), ziel);
  const verschieben = n => () => { const d = new Date(S.datum + "T12:00"); d.setDate(d.getDate() + n); S.datum = heute(d); los(heuteSeite); };
  seite([h("div", {class: "reihe"}, h("button", {class: "knopf zweit schmal", onclick: verschieben(-1)}, "‹"), h("h1", {class: "mitte", style: "margin:0"}, S.datum === heute() ? "Heute" : new Date(S.datum + "T12:00").toLocaleDateString("de-DE", {weekday: "short", day: "numeric", month: "short"})), h("button", {class: "knopf zweit schmal", onclick: verschieben(1)}, "›")),
    h("div", {class: "karte"}, ring, h("div", {class: "makros"}, makro("Eiweiß", t.summe.eiweiss, t.ziele.eiweiss), makro("Kohlenhydrate", t.summe.kh, t.ziele.kh), makro("Fett", t.summe.fett, t.ziele.fett))),
    wasserKarte(t), trainingKarte(t),
    t.eintraege.length ? gruppen : h("div", {class: "karte mitte leise"}, "Noch nichts eingetragen. Tippe unten auf „Essen“."),
    h("div", {class: "karte"}, h("b", {}, "Letzte 7 Tage"), h("div", {class: "tage"}, woche.map(x => h("div", {}, h("i", {style: `height:${x.kcal / max * 70}px;${x.kcal > ziel ? "background:var(--rot)" : ""}`}), new Date(x.datum + "T12:00").toLocaleDateString("de-DE", {weekday: "narrow"})))))]);
}

/* ---------------- Essen hinzufügen ---------------- */
let neuModus = "foto";
function neuSeite() {
  const chips = h("div", {class: "chips zwei"}, [["foto", "📷 Foto"], ["text", "✍️ Beschreiben"], ["barcode", "▥ Barcode"], ["hand", "✎ Von Hand"], ["training", "🏃 Training"]].map(([k, n]) =>
    h("button", {class: neuModus === k ? "an" : "", onclick: () => { neuModus = k; neuSeite(); }}, n)));
  const box = h("div", {});
  seite([h("h1", {}, "Essen eintragen"), chips, box]);
  ({foto: fotoModus, text: textModus, barcode: barcodeModus, hand: () => ergebnis(box, [{name: "", menge: "", kcal: "", eiweiss: "", kh: "", fett: ""}], "hand"), training: trainingModus})[neuModus](box);
}
function fotoModus(box) {
  const datei = h("input", {type: "file", accept: "image/*", capture: "environment", hidden: true});
  const hinweis = h("input", {placeholder: "Hinweis (optional), z. B. „mit Hafermilch“", maxlength: 200});
  const status = h("p", {class: "leise mitte"});
  datei.addEventListener("change", () => los(async () => {
    if (!datei.files[0]) return;
    status.textContent = "Die KI schaut sich dein Essen an …";
    const bild = await verkleinern(datei.files[0]);
    const r = await api("POST", "schaetzen/bild", {bild: bild.split(",")[1], mime: "image/jpeg", hinweis: hinweis.value});
    status.textContent = "";
    if (!r.gerichte.length) return meldung("Ich erkenne darauf nichts Essbares. Versuch ein näheres Foto.");
    ergebnis(box, r.gerichte, "foto", r.hinweis);
  }).finally(() => { status.textContent = status.textContent.startsWith("Die KI") ? "" : status.textContent; }));
  box.replaceChildren(h("div", {class: "karte"}, hinweis, h("button", {class: "knopf", onclick: () => datei.click()}, "Foto machen oder auswählen"), datei, status,
    h("p", {class: "leise"}, "Das Foto wird nur zur Schätzung an die KI geschickt und nicht gespeichert.")));
}
function verkleinern(datei, max = 1280, qualitaet = .82) {
  return new Promise((ok, nein) => {
    const url = URL.createObjectURL(datei), bild = new Image();
    bild.onload = () => { const f = Math.min(1, max / Math.max(bild.width, bild.height)), c = document.createElement("canvas");
      c.width = Math.round(bild.width * f); c.height = Math.round(bild.height * f); c.getContext("2d").drawImage(bild, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url); ok(c.toDataURL("image/jpeg", qualitaet)); };
    bild.onerror = () => nein(new Error("Das Foto konnte nicht gelesen werden."));
    bild.src = url;
  });
}
function textModus(box) {
  const t = h("textarea", {placeholder: "Was hast du gegessen? Je genauer, desto besser: „2 Scheiben Vollkornbrot mit 20 g Butter und 3 Scheiben Gouda, dazu ein Kaffee mit Hafermilch“", maxlength: 600});
  box.replaceChildren(h("div", {class: "karte"}, t, h("button", {class: "knopf", onclick: ev => los(async () => {
    ev.target.disabled = true; try { const r = await api("POST", "schaetzen/text", {text: t.value}); if (!r.gerichte.length) return meldung("Dazu konnte ich nichts schätzen."); ergebnis(box, r.gerichte, "text", r.hinweis); } finally { ev.target.disabled = false; }
  })}, "Schätzen")));
}
function barcodeModus(box) {
  const video = h("video", {playsinline: true, muted: true, autoplay: true});
  const code = h("input", {inputmode: "numeric", placeholder: "oder Nummer unter dem Strichcode eintippen", maxlength: 14});
  const suchen = c => los(async () => {
    stopp(); meldung("Suche Produkt …", 1500);
    const p = await api("GET", "barcode/" + c.replace(/\D/g, ""));
    produkt(box, p);
  });
  box.replaceChildren(h("div", {class: "karte"}, video, h("div", {class: "reihe", style: "margin-top:8px"}, code, h("button", {class: "knopf schmal", style: "margin:0", onclick: () => suchen(code.value)}, "Suchen")),
    h("p", {class: "leise"}, "Daten: Open Food Facts (Community-Datenbank, nicht immer vollständig).")));
  if (!navigator.mediaDevices || !window.ZXing) return video.replaceWith(h("p", {class: "leise"}, "Kamera-Scan geht hier nicht – tippe die Nummer ein."));
  const leser = new ZXing.BrowserMultiFormatReader(); S.scanner = leser;
  leser.decodeFromConstraints({video: {facingMode: "environment"}}, video, (res) => { if (res) { navigator.vibrate && navigator.vibrate(60); suchen(res.getText()); } })
    .catch(() => video.replaceWith(h("p", {class: "leise"}, "Kein Kamerazugriff (die App braucht HTTPS und deine Erlaubnis). Tippe die Nummer ein.")));
}
function produkt(box, p) {
  const gramm = h("input", {type: "number", inputmode: "decimal", value: p.portion_g || 100, min: 1, max: 5000});
  const zeige = h("div", {class: "makros"});
  const rechne = () => { const f = (Number(gramm.value) || 0) / 100;
    zeige.replaceChildren(...[["kcal", p.pro100.kcal], ["Eiweiß", p.pro100.eiweiss], ["Kohlenh.", p.pro100.kh], ["Fett", p.pro100.fett]].map(([n, w]) => h("div", {}, h("b", {}, Math.round(w * f * 10) / 10), h("span", {class: "leise"}, n)))); };
  gramm.addEventListener("input", rechne); rechne();
  box.replaceChildren(h("div", {class: "karte"}, h("b", {}, p.name), h("div", {class: "leise"}, [p.marke, p.menge].filter(Boolean).join(" · ")),
    h("label", {}, "Menge in Gramm" + (p.portion_g ? " (Portion laut Packung)" : "")), gramm, zeige,
    h("button", {class: "knopf", onclick: () => ergebnis(box, [{name: p.name, menge: gramm.value + " g", kcal: p.pro100.kcal * gramm.value / 100, eiweiss: p.pro100.eiweiss * gramm.value / 100, kh: p.pro100.kh * gramm.value / 100, fett: p.pro100.fett * gramm.value / 100}], "barcode")}, "Weiter")));
}
function ergebnis(box, gerichte, quelle, hinweis) {
  stopp();
  let mahlzeit = mahlzeitJetzt();
  const felder = gerichte.map(g => ({
    name: h("input", {value: g.name, placeholder: "Name", maxlength: 120}), menge: h("input", {value: g.menge, placeholder: "Menge", maxlength: 40}),
    kcal: h("input", {type: "number", inputmode: "decimal", value: g.kcal === "" ? "" : Math.round(g.kcal), placeholder: "kcal"}),
    eiweiss: h("input", {type: "number", inputmode: "decimal", value: g.eiweiss === "" ? "" : Math.round(g.eiweiss * 10) / 10, placeholder: "Eiweiß g"}),
    kh: h("input", {type: "number", inputmode: "decimal", value: g.kh === "" ? "" : Math.round(g.kh * 10) / 10, placeholder: "KH g"}),
    fett: h("input", {type: "number", inputmode: "decimal", value: g.fett === "" ? "" : Math.round(g.fett * 10) / 10, placeholder: "Fett g"})}));
  const chips = h("div", {class: "chips vier"});
  const zeichneChips = () => chips.replaceChildren(...Object.entries(MAHLZEITEN).map(([k, n]) => h("button", {class: mahlzeit === k ? "an" : "", onclick: () => { mahlzeit = k; zeichneChips(); }}, n)));
  zeichneChips();
  box.replaceChildren(h("div", {}, quelle === "hand" ? null : h("p", {class: "leise"}, "Prüfe die Werte – du kannst alles ändern. " + (hinweis || "")),
    felder.map(f => h("div", {class: "karte"}, f.name, f.menge, h("div", {class: "reihe"}, f.kcal, f.eiweiss), h("div", {class: "reihe"}, f.kh, f.fett))),
    chips, h("button", {class: "knopf", onclick: ev => los(async () => {
      ev.target.disabled = true;
      try { for (const f of felder) await api("POST", "eintrag", {name: f.name.value, menge: f.menge.value, kcal: f.kcal.value, eiweiss: f.eiweiss.value, kh: f.kh.value, fett: f.fett.value, mahlzeit, datum: S.datum, quelle});
        meldung("Eingetragen ✓"); gehe("heute"); } finally { ev.target.disabled = false; }
    })}, "Eintragen")));
}
function mahlzeitJetzt() { const x = new Date().getHours(); return x < 10 ? "fruehstueck" : x < 15 ? "mittag" : x < 21 ? "abend" : "snack"; }

/* ---------------- Forum ---------------- */
async function forumSeite() {
  const liste = await api("GET", "forum");
  seite([communityChips("forum"), h("h1", {}, "Forum"), h("button", {class: "knopf", onclick: neuesThema}, "Neuer Beitrag"),
    h("div", {class: "karte"}, liste.length ? liste.map(t => h("div", {class: "zeile", onclick: () => los(() => themaSeite(t.id))}, h("div", {class: "name"}, t.titel), h("div", {class: "zeit"}, `${t.name} · ${t.antworten} Antworten · ${vor(t.letzte)}`))) : h("p", {class: "leise mitte"}, "Noch keine Beiträge – schreib den ersten!")),
    regeln()]);
}
function regeln() { return h("p", {class: "leise"}, "Sei freundlich. Beleidigungen, Werbung und gefährliche Diäten (Crash-Diäten, Essstörungs-Tipps) sind nicht erlaubt. Tippe ⚑ zum Melden – Leute kannst du blockieren."); }
function neuesThema() {
  const titel = h("input", {placeholder: "Titel", maxlength: 120}), text = h("textarea", {placeholder: "Was möchtest du fragen oder teilen?", maxlength: 4000});
  seite([h("h1", {}, "Neuer Beitrag"), h("div", {class: "karte"}, titel, text, h("button", {class: "knopf", onclick: () => los(async () => { const r = await api("POST", "forum", {titel: titel.value, text: text.value}); themaSeite(r.id); })}, "Veröffentlichen"),
    h("button", {class: "knopf zweit", onclick: () => gehe("forum")}, "Abbrechen")), regeln()]);
}
async function themaSeite(id) {
  const t = await api("GET", "forum/" + id), antwort = h("textarea", {placeholder: "Deine Antwort …", maxlength: 2000});
  const werkzeuge = (art, x) => h("div", {class: "reihe", style: "justify-content:flex-end;gap:14px;margin-top:4px"},
    h("a", {href: "#", class: "leise", onclick: e => { e.preventDefault(); los(async () => { await api("POST", "melden", {art, id: x.id}); meldung("Danke, wir schauen es uns an."); }); }}, "⚑ melden"),
    x.eigen ? h("a", {href: "#", class: "leise", onclick: e => { e.preventDefault(); if (confirm("Wirklich löschen?")) los(async () => { await api("POST", "loeschen", {art, id: x.id}); art === "thema" ? gehe("forum") : themaSeite(id); }); }}, "löschen")
      : h("a", {href: "#", class: "leise", onclick: e => { e.preventDefault(); if (confirm(x.name + " blockieren?")) los(async () => { await api("POST", "blockieren", {name: x.name}); meldung(x.name + " ist blockiert."); themaSeite(id); }); }}, "blockieren"));
  seite([h("button", {class: "knopf zweit", onclick: () => gehe("forum")}, "‹ Zurück"),
    h("div", {class: "karte"}, h("h1", {style: "font-size:20px"}, t.titel), h("div", {class: "zeit"}, `${t.name} · ${vor(t.erstellt)}`), h("p", {style: "white-space:pre-wrap"}, t.text), werkzeuge("thema", t)),
    t.antworten.map(a => h("div", {class: "karte"}, h("div", {class: "zeit"}, `${a.name} · ${vor(a.erstellt)}`), h("p", {style: "white-space:pre-wrap;margin:6px 0"}, a.text), werkzeuge("antwort", a))),
    h("div", {class: "karte"}, antwort, h("button", {class: "knopf", onclick: () => los(async () => { await api("POST", `forum/${id}/antwort`, {text: antwort.value}); themaSeite(id); })}, "Antworten"))]);
}

/* ---------------- Chat ---------------- */
async function chatSeite() {
  const verlauf = h("div", {id: "chatverlauf"}), eingabe = h("input", {placeholder: "Nachricht …", maxlength: 500, enterkeyhint: "send"});
  let letzte = 0;
  const zeige = msgs => { for (const m of msgs) { letzte = Math.max(letzte, m.id);
    verlauf.append(h("div", {class: "blase" + (m.eigen ? " eigen" : "")}, m.eigen ? null : h("small", {}, m.name), m.text,
      m.eigen ? null : h("small", {}, h("a", {href: "#", style: "color:inherit", onclick: e => { e.preventDefault(); los(async () => { await api("POST", "melden", {art: "chat", id: m.id}); meldung("Danke, wir schauen es uns an."); }); }}, "⚑ melden")))); }
    if (msgs.length) window.scrollTo(0, document.body.scrollHeight); };
  const form = h("form", {onsubmit: e => { e.preventDefault(); const t = eingabe.value.trim(); if (!t) return; eingabe.value = ""; los(async () => { await api("POST", "chat", {text: t}); zeige(await api("GET", "chat?nach=" + letzte)); }); }},
    eingabe, h("button", {class: "knopf", type: "submit"}, "Senden"));
  seite([communityChips("chat"), h("h1", {}, "Community-Chat"), regeln(), verlauf, h("div", {id: "chateingabe"}, form)]);
  zeige(await api("GET", "chat"));
  S.timer = setInterval(() => { if (!document.hidden) api("GET", "chat?nach=" + letzte).then(zeige).catch(() => {}); }, 3500);
}

/* ---------------- Ich ---------------- */
async function ichSeite() {
  S.ich = await api("GET", "ich"); const z = S.ich.ziele, p = S.ich.profil || {};
  const f = (id, label, wert, att = {}) => [h("label", {}, label), h("input", {id, value: wert ?? "", inputmode: "decimal", ...att})];
  const wahl = (id, label, optionen, wert) => [h("label", {}, label), h("select", {id}, Object.entries(optionen).map(([k, n]) => h("option", {value: k, selected: k === wert}, n)))];
  const v = id => document.getElementById(id).value;
  const zugaenge = h("div", {});
  const ladeZugaenge = () => los(async () => { const l = await api("GET", "zugang"); zugaenge.replaceChildren(...l.map(x => h("div", {class: "eintrag"}, h("div", {}, x.name, h("br"), h("small", {}, x.zuletzt ? "zuletzt " + vor(x.zuletzt) + " her" : "noch nie benutzt")), h("button", {onclick: () => los(async () => { await api("DELETE", "zugang/" + x.hash); ladeZugaenge(); })}, "×")))); });
  const zugangsname = h("input", {placeholder: "Name, z. B. Telegram oder Klaus", maxlength: 40}), neuerSchluessel = h("div", {});
  const verlauf = await api("GET", "gewicht"), bio = h("input", {id: "bio", value: S.ich.bio, placeholder: "Über mich (max. 160 Zeichen)", maxlength: 160});
  seite([h("h1", {}, S.ich.name), h("button", {class: "knopf zweit", onclick: () => los(() => profilSeite(S.ich.name))}, "Mein Profil ansehen"),
    h("div", {class: "karte"}, h("b", {}, "Profil"), bio,
      h("label", {class: "reihe", style: "color:var(--text);align-items:center"}, h("input", {id: "rl", type: "checkbox", checked: S.ich.rangliste, style: "width:auto;margin:0 10px 0 0"}), h("span", {}, "In der Wochen-Rangliste mitmachen")),
      h("button", {class: "knopf zweit", onclick: () => los(async () => { await api("PUT", "ich", {bio: bio.value, rangliste: document.getElementById("rl").checked}); meldung("Gespeichert ✓"); })}, "Profil speichern")),
    gewichtKarte(verlauf),
    h("div", {class: "karte"}, h("b", {}, "Tagesziele"), ...f("zk", "Kalorien", z.kcal), h("div", {class: "reihe"}, h("div", {}, ...f("ze", "Eiweiß g", z.eiweiss)), h("div", {}, ...f("zh", "Kohlenh. g", z.kh)), h("div", {}, ...f("zf", "Fett g", z.fett))),
      h("button", {class: "knopf", onclick: () => los(async () => { await api("PUT", "ich", {kcal: v("zk"), eiweiss: v("ze"), kh: v("zh"), fett: v("zf")}); meldung("Gespeichert ✓"); })}, "Speichern")),
    h("div", {class: "karte"}, h("b", {}, "Ziele berechnen lassen"), h("p", {class: "leise"}, "Richtwert nach Mifflin-St-Jeor – keine medizinische Beratung."),
      ...wahl("pg", "Geschlecht", {m: "Männlich", w: "Weiblich"}, p.geschlecht), ...f("pa", "Alter", p.alter), ...f("ph", "Größe (cm)", p.groesse), ...f("pw", "Gewicht (kg)", p.gewicht),
      ...wahl("pt", "Aktivität", {wenig: "Wenig (Bürojob)", leicht: "Leicht (1–3× Sport)", mittel: "Mittel (3–5× Sport)", viel: "Hoch (täglich)"}, p.aktivitaet || "leicht"), ...wahl("pz", "Ziel", {abnehmen: "Abnehmen", halten: "Halten", zunehmen: "Zunehmen"}, p.ziel || "halten"),
      h("button", {class: "knopf zweit", onclick: () => los(async () => { await api("PUT", "ich", {berechnen: {geschlecht: v("pg"), alter: v("pa"), groesse: v("ph"), gewicht: v("pw"), aktivitaet: v("pt"), ziel: v("pz")}}); meldung("Ziele berechnet ✓"); ichSeite(); })}, "Berechnen")),
    h("div", {class: "karte"}, h("b", {}, "Schnittstelle (Telegram, Klaus, Kurzbefehle)"), h("p", {class: "leise"}, "Mit einem Schlüssel können andere Programme in deinem Namen Essen eintragen und deine Tageswerte lesen. Behandle ihn wie ein Passwort."),
      zugaenge, zugangsname, h("button", {class: "knopf zweit", onclick: () => los(async () => { const r = await api("POST", "zugang", {name: zugangsname.value}); neuerSchluessel.replaceChildren(h("p", {class: "leise"}, "Nur jetzt sichtbar – kopieren:"), h("div", {class: "pfad"}, r.token)); zugangsname.value = ""; ladeZugaenge(); })}, "Schlüssel erstellen"), neuerSchluessel),
    h("div", {class: "karte"}, h("b", {}, "Meine Daten"),
      h("button", {class: "knopf zweit", onclick: () => los(async () => { const d = await api("GET", "export"); const a = h("a", {href: URL.createObjectURL(new Blob([JSON.stringify(d, null, 1)], {type: "application/json"})), download: "kalorien-export.json"}); document.body.append(a); a.click(); a.remove(); })}, "Alles exportieren"),
      h("button", {class: "knopf zweit", onclick: () => abmelden()}, "Abmelden"),
      h("button", {class: "knopf gefahr", onclick: () => { if (confirm("Konto und ALLE Daten endgültig löschen?")) los(async () => { await api("DELETE", "ich"); abmelden(); }); }}, "Konto löschen"))]);
  ladeZugaenge();
}

/* ---------------- Start ---------------- */
function gehe(s) { S.seite = s; const nav = {chat: "forum", rangliste: "forum"}[s] || s; document.querySelectorAll("#leiste button").forEach(b => b.classList.toggle("an", b.dataset.seite === nav));
  los(async () => ({heute: heuteSeite, neu: neuSeite, feed: feedSeite, forum: forumSeite, chat: chatSeite, rangliste: ranglisteSeite, ich: ichSeite})[s]()); }
async function start() {
  if (!S.token) return anmeldeseite();
  try { S.ich = await api("GET", "ich"); } catch (e) { return; }
  $("#leiste").hidden = false; gehe("heute");
}
document.querySelectorAll("#leiste button").forEach(b => b.addEventListener("click", () => gehe(b.dataset.seite)));
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
start();

/* ---------------- Wasser, Training, Gewicht ---------------- */
function wasserKarte(t) {
  const plus = ml => () => los(async () => { await api("POST", "wasser", {ml, datum: S.datum}); heuteSeite(); });
  return h("div", {class: "karte"}, h("div", {class: "reihe"}, h("b", {}, "💧 Wasser"), h("span", {class: "leise", style: "text-align:right"}, `${t.wasser_ml} / ${t.ziel_wasser} ml`)),
    h("div", {class: "balken"}, h("i", {style: `width:${Math.min(100, t.wasser_ml / t.ziel_wasser * 100)}%;background:var(--blau)`})),
    h("div", {class: "chips", style: "margin-top:10px"}, h("button", {onclick: plus(-250)}, "−250"), h("button", {onclick: plus(250)}, "+250"), h("button", {onclick: plus(500)}, "+500")));
}
function trainingKarte(t) {
  if (!t.training.length) return h("div", {class: "karte leise mitte"}, "Noch kein Training heute. Unter „Essen“ → 🏃 Training eintragen.");
  return h("div", {class: "karte"}, h("div", {class: "reihe"}, h("b", {}, "🏃 Training"), h("span", {class: "leise", style: "text-align:right"}, `${t.verbrannt} kcal verbrannt`)),
    t.training.map(x => h("div", {class: "eintrag"}, h("div", {}, TRAINING[x.art] || x.art, h("br"), h("small", {}, `${x.minuten} Min${x.notiz ? " · " + x.notiz : ""}`)),
      h("div", {style: "text-align:right"}, h("b", {}, x.kcal), h("br"), h("button", {"aria-label": "Löschen", onclick: () => los(async () => { await api("DELETE", "training/" + x.id); heuteSeite(); })}, "×")))),
    h("p", {class: "leise"}, "Verbrannte Kalorien sind Schätzwerte und zählen nicht zu deinem Essens-Budget."));
}
const TRAINING = {laufen: "Laufen", gehen: "Gehen", radfahren: "Radfahren", schwimmen: "Schwimmen", krafttraining: "Krafttraining", yoga: "Yoga", hiit: "HIIT", fussball: "Fußball", wandern: "Wandern", tanzen: "Tanzen", sonstiges: "Sonstiges"};
function trainingModus(box) {
  const art = h("select", {}, Object.entries(TRAINING).map(([k, n]) => h("option", {value: k}, n)));
  const min = h("input", {type: "number", inputmode: "numeric", placeholder: "Minuten", min: 1, max: 600});
  const kcal = h("input", {type: "number", inputmode: "numeric", placeholder: "Verbrannte kcal (leer = automatisch schätzen)"});
  const notiz = h("input", {placeholder: "Notiz (optional), z. B. „Brust & Trizeps“", maxlength: 200});
  const teilen = h("input", {type: "checkbox", style: "width:auto;margin:0 10px 0 0"});
  box.replaceChildren(h("div", {class: "karte"}, art, min, kcal, notiz,
    h("label", {class: "reihe", style: "color:var(--text);align-items:center"}, teilen, h("span", {}, "Im Feed teilen")),
    h("button", {class: "knopf", onclick: () => los(async () => {
      const r = await api("POST", "training", {art: art.value, minuten: min.value, kcal: kcal.value, notiz: notiz.value, datum: S.datum});
      if (teilen.checked) await api("POST", "beitrag", {art: "training", text: `💪 ${TRAINING[r.art]} · ${r.minuten} Min · ${r.kcal} kcal${notiz.value ? " – " + notiz.value : ""}`});
      meldung("Training eingetragen ✓"); gehe("heute");
    })}, "Eintragen"), h("p", {class: "leise"}, "Ohne Angabe schätze ich die Kalorien aus Sportart, Dauer und deinem Gewicht.")));
}
function gewichtKarte(verlauf) {
  const kg = h("input", {type: "number", inputmode: "decimal", step: "0.1", placeholder: "Gewicht heute in kg"});
  const werte = verlauf.map(x => x.kg), lo = Math.min(...werte), hi = Math.max(...werte);
  let kurve = null;
  if (verlauf.length > 1) {
    const pkt = verlauf.map((x, i) => `${(i / (verlauf.length - 1) * 300).toFixed(1)},${(hi === lo ? 30 : 56 - (x.kg - lo) / (hi - lo) * 52).toFixed(1)}`).join(" ");
    kurve = h("div", {}); kurve.innerHTML = `<svg viewBox="0 0 300 60" style="width:100%;height:70px"><polyline points="${pkt}" fill="none" stroke="var(--gruen)" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
  }
  const delta = verlauf.length > 1 ? Math.round((werte[werte.length - 1] - werte[0]) * 10) / 10 : null;
  return h("div", {class: "karte"}, h("div", {class: "reihe"}, h("b", {}, "⚖️ Gewicht"), h("span", {class: "leise", style: "text-align:right"}, verlauf.length ? `${werte[werte.length - 1]} kg${delta !== null ? ` (${delta > 0 ? "+" : ""}${delta})` : ""}` : "noch nichts")),
    kurve, kg, h("button", {class: "knopf zweit", onclick: () => los(async () => { await api("POST", "gewicht", {kg: kg.value}); meldung("Gespeichert ✓"); ichSeite(); })}, "Gewicht speichern"));
}

/* ---------------- Feed, Profile, Rangliste ---------------- */
function communityChips(aktiv) {
  return h("div", {class: "chips", style: "margin-bottom:8px"}, [["forum", "Forum"], ["chat", "Chat"], ["rangliste", "🏅 Rangliste"]].map(([k, n]) => h("button", {class: aktiv === k ? "an" : "", onclick: () => gehe(k)}, n)));
}
let feedArt = "alle";
async function feedSeite() {
  const liste = await api("GET", "feed?art=" + feedArt);
  const art = h("div", {class: "chips vier"}, [["text", "💬"], ["training", "💪"], ["mahlzeit", "🥗"], ["fortschritt", "📈"]].map(([k, n]) => h("button", {"data-art": k, class: k === "text" ? "an" : "", onclick: e => { art.querySelectorAll("button").forEach(b => b.classList.toggle("an", b === e.currentTarget)); }}, n)));
  const text = h("textarea", {placeholder: "Was gibt’s Neues? Training, Mahlzeit, Fortschritt …", maxlength: 1000, style: "min-height:70px"});
  const datei = h("input", {type: "file", accept: "image/*", hidden: true}), vorschau = h("div", {});
  let bild = null;
  datei.addEventListener("change", () => los(async () => { if (!datei.files[0]) return; bild = await verkleinernBis(datei.files[0]); vorschau.replaceChildren(h("img", {src: bild, style: "width:100%;border-radius:12px;margin-top:6px"})); }));
  const suche = h("input", {placeholder: "Leute suchen …", maxlength: 24}), treffer = h("div", {});
  let tm; suche.addEventListener("input", () => { clearTimeout(tm); tm = setTimeout(() => los(async () => { const r = suche.value.trim().length < 2 ? [] : await api("GET", "suche?q=" + encodeURIComponent(suche.value.trim()));
    treffer.replaceChildren(...r.map(x => h("div", {class: "zeile", onclick: () => los(() => profilSeite(x.name))}, x.name))); }), 300); });
  seite([h("h1", {}, "Feed"),
    h("div", {class: "chips", style: "margin-bottom:8px"}, [["alle", "Alle"], ["folge", "Folge ich"]].map(([k, n]) => h("button", {class: feedArt === k ? "an" : "", onclick: () => { feedArt = k; gehe("feed"); }}, n))),
    h("div", {class: "karte"}, art, text, vorschau, h("div", {class: "reihe"}, h("button", {class: "knopf zweit", onclick: () => datei.click()}, "📷 Foto"),
      h("button", {class: "knopf", onclick: ev => los(async () => { ev.target.disabled = true; try {
        await api("POST", "beitrag", {art: art.querySelector(".an").dataset.art, text: text.value, bild: bild ? bild.split(",")[1] : undefined}); meldung("Veröffentlicht ✓"); feedSeite(); } finally { ev.target.disabled = false; } })}, "Posten")), datei,
      h("p", {class: "leise"}, "Fotos sind für alle Mitglieder sichtbar. Der Standort im Foto wird entfernt.")),
    h("div", {class: "karte"}, suche, treffer),
    liste.length ? liste.map(beitragKarte) : h("div", {class: "karte mitte leise"}, feedArt === "folge" ? "Hier erscheinen Beiträge der Leute, denen du folgst. Such oben nach Leuten." : "Noch keine Beiträge – mach den Anfang!")]);
}
function verkleinernBis(datei, maxBytes = 800 * 1024) {
  return (async () => { for (const [px, q] of [[1080, .82], [1080, .65], [800, .6], [600, .5]]) {
    const url = await verkleinern(datei, px, q); if (url.length * 0.75 <= maxBytes) return url; }
    throw new Error("Das Foto ist zu groß."); })();
}
const ARTSYM = {text: "", training: "💪 Training", mahlzeit: "🥗 Mahlzeit", fortschritt: "📈 Fortschritt"};
function beitragKarte(b, detail = false) {
  const herz = h("button", {class: "knopf zweit", style: "width:auto;flex:0 0 auto;margin:0;padding:8px 18px", onclick: ev => { ev.stopPropagation(); los(async () => { const r = await api("POST", `beitrag/${b.id}/gefaellt`); herz.textContent = `${r.geliked ? "♥" : "♡"} ${r.likes}`; herz.style.color = r.geliked ? "var(--rot)" : ""; }); }}, `${b.geliked ? "♥" : "♡"} ${b.likes}`);
  if (b.geliked) herz.style.color = "var(--rot)";
  return h("div", {class: "karte", onclick: detail ? null : () => los(() => beitragSeite(b.id))},
    h("div", {class: "reihe"}, h("a", {href: "#", class: "name", style: "color:inherit;text-decoration:none", onclick: e => { e.preventDefault(); e.stopPropagation(); los(() => profilSeite(b.name)); }}, b.name), h("span", {class: "zeit", style: "text-align:right"}, [ARTSYM[b.art], vor(b.erstellt)].filter(Boolean).join(" · "))),
    b.text ? h("p", {style: "white-space:pre-wrap;margin:8px 0"}, b.text) : null,
    b.bild ? h("img", {src: b.bild, loading: "lazy", style: "width:100%;border-radius:12px;margin:6px 0;display:block"}) : null,
    h("div", {class: "reihe", style: "justify-content:flex-start;gap:10px;margin-top:6px"}, herz, h("span", {class: "leise schmal"}, `💬 ${b.kommentare}`)));
}
async function beitragSeite(id) {
  const b = await api("GET", "beitrag/" + id), k = h("input", {placeholder: "Kommentar …", maxlength: 500});
  const werkzeug = (art, x) => h("div", {class: "reihe", style: "justify-content:flex-end;gap:14px;margin-top:4px"},
    h("a", {href: "#", class: "leise", onclick: e => { e.preventDefault(); los(async () => { await api("POST", "melden", {art, id: x.id}); meldung("Danke, wir schauen es uns an."); }); }}, "⚑ melden"),
    x.eigen ? h("a", {href: "#", class: "leise", onclick: e => { e.preventDefault(); if (confirm("Wirklich löschen?")) los(async () => { await api("POST", "loeschen", {art, id: x.id}); art === "beitrag" ? gehe("feed") : beitragSeite(id); }); }}, "löschen")
      : h("a", {href: "#", class: "leise", onclick: e => { e.preventDefault(); if (confirm(x.name + " blockieren?")) los(async () => { await api("POST", "blockieren", {name: x.name}); meldung(x.name + " ist blockiert."); gehe("feed"); }); }}, "blockieren"));
  seite([h("button", {class: "knopf zweit", onclick: () => gehe("feed")}, "‹ Zurück"), beitragKarte(b, true), werkzeug("beitrag", b),
    b.kommentar_liste.map(x => h("div", {class: "karte"}, h("div", {class: "zeit"}, `${x.name} · ${vor(x.erstellt)}`), h("p", {style: "white-space:pre-wrap;margin:6px 0"}, x.text), werkzeug("kommentar", x))),
    h("div", {class: "karte"}, k, h("button", {class: "knopf", onclick: () => los(async () => { await api("POST", `beitrag/${id}/kommentar`, {text: k.value}); beitragSeite(id); })}, "Kommentieren"))]);
}
async function profilSeite(name) {
  const p = await api("GET", "profil/" + encodeURIComponent(name)), posts = await api("GET", "feed?von=" + encodeURIComponent(name));
  const stat = (z, n) => h("div", {class: "mitte"}, h("b", {style: "font-size:20px;display:block"}, z), h("span", {class: "leise"}, n));
  seite([h("button", {class: "knopf zweit", onclick: () => gehe(p.ich ? "ich" : "feed")}, "‹ Zurück"),
    h("div", {class: "karte mitte"}, h("h1", {style: "margin:0"}, p.name), p.bio ? h("p", {}, p.bio) : null, h("div", {class: "reihe", style: "margin:12px 0"}, stat(p.serie, "🔥 Serie"), stat(p.woche_min, "Min diese Woche"), stat(p.trainings, "Trainings")),
      h("div", {class: "reihe"}, stat(p.beitraege, "Beiträge"), stat(p.folger, "Folgende"), stat(p.folgt, "Folgt")),
      p.ich ? null : h("button", {class: "knopf" + (p.folgt_ihm ? " zweit" : ""), onclick: () => los(async () => { await api(p.folgt_ihm ? "DELETE" : "POST", "folgen", {name: p.name}); profilSeite(name); })}, p.folgt_ihm ? "Du folgst – entfolgen" : "Folgen"),
      p.abzeichen.length ? h("div", {class: "chips", style: "margin-top:8px;justify-content:center"}, p.abzeichen.map(a => h("span", {class: "karte", style: "padding:6px 10px;margin:0;font-size:13px"}, `${a.icon} ${a.name}`))) : null),
    posts.length ? posts.map(x => beitragKarte(x)) : h("p", {class: "leise mitte"}, "Noch keine Beiträge.")]);
}
async function ranglisteSeite() {
  const r = await api("GET", "rangliste");
  seite([communityChips("rangliste"), h("h1", {}, "Wochen-Rangliste"), h("p", {class: "leise"}, "Aktive Trainingsminuten der letzten 7 Tage (pro Tag zählen höchstens 240 Minuten). Mitmachen kannst du unter Ich → Profil."),
    h("div", {class: "karte"}, r.length ? r.map((x, i) => h("div", {class: "eintrag", style: x.ich ? "font-weight:700" : "", onclick: () => los(() => profilSeite(x.name))},
      h("div", {}, `${["🥇", "🥈", "🥉"][i] || (i + 1) + "."} ${x.name}`), h("div", {}, `${x.minuten} Min · ${x.tage} Tage`))) : h("p", {class: "leise mitte"}, "Diese Woche hat noch niemand trainiert – trag dein Training ein!"))]);
}
