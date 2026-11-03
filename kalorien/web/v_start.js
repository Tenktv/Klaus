/* Anmeldung / Registrierung und Willkommens-Dialog (Ziele berechnen). */
import {$, S, h, api, toast, leeren, sheet} from "./core.js";
import {zieleFormular} from "./v_ich.js";

export function anmeldeseite() {
  $("#leiste").hidden = true;
  document.body.classList.remove("reels");
  const box = $("#view");
  box.className = "voll";
  let modus = "registrieren";
  const name = h("input", {placeholder: "Name (für alle sichtbar)", autocomplete: "username", maxlength: 24, "aria-label": "Name"});
  const pw = h("input", {type: "password", placeholder: "Passwort (mind. 8 Zeichen)", autocomplete: "current-password", "aria-label": "Passwort"});
  const ok = h("input", {type: "checkbox", id: "zustimmung"});
  const regeln = h("label", {class: "zeile oben kleingedruckt", for: "zustimmung", style: {cursor: "pointer"}}, ok,
    h("span", {}, "Ich bin mindestens 16, bleibe in Forum, Chat und Kommentaren respektvoll und weiß, dass Fotos zur Schätzung an eine KI gehen und nicht gespeichert werden. Meine Daten kann ich jederzeit exportieren und löschen."));
  const knopf = h("button", {class: "btn", onclick: () => senden()}, "Konto erstellen");
  const seg = h("div", {class: "seg", style: {marginBottom: "14px"}},
    h("button", {class: "an", onclick: e => umschalten("registrieren", e.currentTarget)}, "Neu hier"),
    h("button", {onclick: e => umschalten("anmelden", e.currentTarget)}, "Anmelden"));
  function umschalten(m, btn) {
    modus = m;
    seg.querySelectorAll("button").forEach(b => b.classList.toggle("an", b === btn));
    regeln.hidden = m === "anmelden";
    knopf.textContent = m === "anmelden" ? "Anmelden" : "Konto erstellen";
    pw.autocomplete = m === "anmelden" ? "current-password" : "new-password";
  }
  async function senden() {
    if (modus === "registrieren" && !ok.checked) return toast("Bitte bestätige die Regeln.", true);
    knopf.disabled = true;
    try {
      const d = await api("POST", modus, {name: name.value, passwort: pw.value});
      S.token = d.token; localStorage.setItem("kt", d.token);
      window.dispatchEvent(new CustomEvent("fit:angemeldet", {detail: {neu: modus === "registrieren"}}));
    } catch (e) { toast(e.message, true); } finally { knopf.disabled = false; }
  }
  pw.addEventListener("keydown", e => { if (e.key === "Enter") senden(); });
  leeren(box, h("div", {class: "start"},
    h("div", {class: "in"},
      h("div", {class: "marke"}, "Klesro Fit"),
      h("h1", {}, "Essen.", h("br"), "Training.", h("br"), h("em", {}, "Crew.")),
      h("p", {class: "mut", style: {maxWidth: "30ch", fontSize: "18px"}}, "Kalorien per Foto, Workouts mit Rekorden, Reels und Rezepte – alles in einer App."),
      h("div", {class: "karte"}, seg, h("div", {class: "feld"}, name), h("div", {class: "feld"}, pw), regeln, knopf),
      h("p", {class: "kleingedruckt mitte", style: {margin: "0"}}, "Schätzwerte sind Richtwerte, keine medizinische Beratung."))));
}

/* Nach der Registrierung: Ziele einmal berechnen lassen (kann man ueberspringen) */
export function willkommen() {
  sheet("Willkommen. Deine Ziele?", zu => [
    h("p", {class: "mut", style: {marginBottom: "10px"}}, "Gib ein paar Eckdaten ein, dann rechnet die App dir Tagesziele für Kalorien, Eiweiß, Kohlenhydrate und Fett aus. Alles lässt sich später ändern."),
    zieleFormular(async () => { zu(); toast("Ziele gespeichert. Los geht's."); location.hash = "#/heute"; window.dispatchEvent(new HashChangeEvent("hashchange")); }),
    h("button", {class: "btn geist", style: {marginTop: "6px"}, onclick: zu}, "Später")]);
}
