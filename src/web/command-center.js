/* Kontrollzentrum: ausschliesslich echte Qt-Aktionen, Ansichtseinstellungen nur lokal. */
(() => {
  if (new URLSearchParams(location.search).get("zweit") === "1") return;
  let bridge = null, state = null, polling = false, suspended = false, lastGood = 0;
  let returnFocus = null, selected = 0, results = [], messageTimer;
  const $ = (id) => document.getElementById(id);
  const preferences = { focus: false, compact: false };
  try { Object.assign(preferences, JSON.parse(localStorage.getItem("klaus.command-center.v1") || "{}")); } catch {}
  const palette = el("div", "cc-layer"); palette.hidden = true;
  palette.innerHTML = `<section class="cc-dialog" role="dialog" aria-modal="true" aria-labelledby="cc-palette-title">
    <header><h2 id="cc-palette-title">Was möchtest du tun?</h2><button class="cc-close" aria-label="Schließen">×</button></header>
    <label for="cc-search">Aktionen suchen oder Klaus einen Auftrag schreiben</label>
    <input id="cc-search" class="cc-search" autocomplete="off" maxlength="4000" placeholder="Zum Beispiel: Was steht morgen an?">
    <div class="cc-results" id="cc-results"></div><p class="cc-footer">↑ ↓ Auswählen · Enter Ausführen · Esc Schließen. Aufträge nutzen dieselben Freigaben wie Sprache.</p>
  </section>`;
  const control = el("div", "cc-layer"); control.hidden = true;
  control.innerHTML = `<section class="cc-dialog" role="dialog" aria-modal="true" aria-labelledby="cc-control-title">
    <header><h2 id="cc-control-title">Kontrollzentrum</h2><button class="cc-close" aria-label="Schließen">×</button></header>
    <p id="cc-freshness">Betriebsstatus wird geladen …</p>
    <div class="cc-row"><div><strong>Stimme & Mikrofon</strong><small id="cc-audio-detail">Status ausstehend</small></div><div class="quick-actions"><button class="hud-knopf" data-bridge="stummUmschalten">Stumm</button><button class="hud-knopf" data-bridge="mikroUmschalten">Mikro aus</button></div></div>
    <div class="cc-row"><div><strong>Ruhemodus</strong><small id="cc-quiet-detail">Status ausstehend</small><small id="cc-speech-detail"></small></div><button class="hud-knopf" data-bridge="ruheUmschalten" id="cc-quiet-toggle" aria-pressed="false" disabled>Umschalten</button></div>
    <div class="cc-row"><div><strong>Meeting-Protokoll</strong><small id="cc-record-detail">Status ausstehend</small></div><button class="hud-knopf" data-bridge="protokollBeenden" id="cc-end-record" disabled>Beenden</button></div>
    <p id="cc-record-warning" class="cc-warning" hidden></p>
    <div class="cc-row"><div><strong>Spiel-Coach</strong><small id="cc-coach-detail">Status ausstehend</small></div><button class="hud-knopf" data-bridge="coachBeenden" id="cc-end-coach" disabled>Beenden</button></div>
    <div class="cc-row"><div><strong>PC-Zugriff</strong><small id="cc-pc-detail">Status ausstehend</small></div><button class="hud-knopf cc-danger" data-bridge="pcStopp">PC stoppen</button></div>
    <div class="cc-row"><div><strong>Freigabe</strong><small id="cc-auth-detail">Status ausstehend</small></div><span class="lbl">Einmal pro Aktion</span></div>
    <section class="cc-budget" aria-label="KI-Budget"><strong>KI-Budget</strong><small id="cc-ai-mode">Status ausstehend</small><p id="cc-ai-day"></p><p id="cc-ai-month"></p><small>Reservierungen belegen Budget; sie sind noch nicht abgerechnet.</small></section>
    <form id="cc-timer-form"><label for="cc-timer" style="margin-top:20px">PC-Zeitlimit in Minuten (1–240)</label><div class="cc-timer"><input id="cc-timer" type="number" min="1" max="240" step="1" value="15" required><button class="hud-knopf" type="submit">Limit setzen</button><button class="hud-knopf" id="cc-timer-off" type="button">Limit aus</button></div></form>
    <p class="cc-footer">PC stoppen beendet laufende PC-Aktionen und den Coach direkt. Status wird alle 5 Sekunden abgefragt, solange dieses Panel sichtbar ist.</p>
  </section>`;
  const message = el("div", "cc-message"); message.setAttribute("role", "status");
  document.body.append(palette, control, message);

  function notify(text) {
    clearTimeout(messageTimer); message.textContent = text;
    messageTimer = setTimeout(() => { message.textContent = ""; }, 4500);
  }
  function available(method) { return bridge && typeof bridge[method] === "function"; }
  function call(method, args = []) {
    if (!available(method)) { notify("Diese Aktion ist mit der aktuellen Verbindung nicht verfügbar."); return false; }
    try { bridge[method](...args); return true; }
    catch { notify("Die Aktion konnte nicht an Klaus übergeben werden."); return false; }
  }
  function syncViews() {
    document.body.classList.toggle("user-focus", !!preferences.focus);
    document.body.classList.toggle("compact", !!preferences.compact);
    $("cc-focus").setAttribute("aria-pressed", String(!!preferences.focus));
    $("cc-compact").setAttribute("aria-pressed", String(!!preferences.compact));
    if (bridge && typeof webVerdecken === "function") webVerdecken(false);
  }
  function toggle(key) {
    preferences[key] = !preferences[key]; syncViews();
    try { localStorage.setItem("klaus.command-center.v1", JSON.stringify(preferences)); } catch { notify("Ansicht geändert; lokale Speicherung ist nicht verfügbar."); }
  }
  syncViews();
  $("cc-focus").onclick = () => toggle("focus"); $("cc-compact").onclick = () => toggle("compact");
  function close() {
    palette.hidden = control.hidden = true;
    if (bridge) webVerdecken(false);
    if (returnFocus?.isConnected) returnFocus.focus(); returnFocus = null;
  }
  function open(layer) {
    if (palette.hidden && control.hidden) returnFocus = document.activeElement;
    palette.hidden = control.hidden = true; layer.hidden = false;
    if (bridge) webVerdecken(true);
    if (layer === palette) { $("cc-search").value = ""; selected = 0; renderResults(); $("cc-search").focus(); }
    else { updateState(); layer.querySelector(".cc-close").focus(); }
  }
  [palette, control].forEach((layer) => {
    layer.querySelector(".cc-close").onclick = close;
    layer.addEventListener("click", (e) => { if (e.target === layer) close(); });
  });
  $("cc-launch").onclick = () => open(palette); $("cc-control").onclick = () => open(control);
  document.querySelectorAll("[data-control]").forEach((b) => { b.onclick = () => open(control); });
  $("cc-memory").onclick = () => call("graph", ["gedaechtnis", ""]);
  document.querySelectorAll("[data-bridge]").forEach((b) => {
    b.disabled = true;
    b.onclick = () => { if (call(b.dataset.bridge)) notify(b.dataset.bridge === "pcStopp" ? "Stopp an Klaus übergeben." : "Aktion an Klaus übergeben."); };
  });
  $("cc-timer-form").onsubmit = (e) => {
    e.preventDefault(); const n = Number($("cc-timer").value);
    if (!Number.isInteger(n) || n < 1 || n > 240) { notify("Bitte 1 bis 240 ganze Minuten eingeben."); return; }
    if (call("pcTimer", [n])) notify(`PC-Zeitlimit von ${n} Minuten übergeben.`);
  };
  $("cc-timer-off").onclick = () => { if (call("pcTimer", [0])) notify("Aufheben des Zeitlimits übergeben."); };

  function actions() {
    const fresh = state && Date.now() - lastGood < 12000;
    return [
      { title: "Lagebericht", info: "Nachrichten, Region und Märkte", method: "lagebericht", args: [] },
      { title: "Gedächtnis öffnen", info: "Dein Wissen als Graph", method: "graph", args: ["gedaechtnis", ""] },
      { title: "Gespräch öffnen", info: "Mit Klaus sprechen oder schreiben", method: "chat", args: [] },
      { title: "Kontrollzentrum", info: "Audio, Protokoll, Coach und PC-Zugriff", run: () => open(control) },
      { title: "Fokus umschalten", info: "Widgets vorübergehend ausblenden", run: () => toggle("focus") },
      { title: "Kompakt umschalten", info: "Mehr Inhalt im gleichen Raum", run: () => toggle("compact") },
      { title: "Widget hinzufügen", info: "Arbeitsbereich erweitern", run: () => katalogZeigen() },
      { title: "Stumm umschalten", info: "Sprachausgabe steuern", method: "stummUmschalten", args: [] },
      { title: "Ruhemodus umschalten", info: "Antworten nur als Text oder direkte Sprachantworten erlauben", method: "ruheUmschalten", args: [] },
      { title: "Mikrofon umschalten", info: "Mikrofon vollständig an oder aus", method: "mikroUmschalten", args: [] },
      { title: "PC stoppen", info: "Laufende PC-Aktionen und Coach direkt stoppen", method: "pcStopp", args: [] },
      ...(fresh && state.protokoll?.aktiv ? [{ title: "Protokoll beenden", info: state.protokoll.titel || "Laufende Mitschrift beenden", method: "protokollBeenden", args: [] }] : []),
      ...(fresh && state.coach?.aktiv ? [{ title: "Coach beenden", info: "Laufenden Coach stoppen", method: "coachBeenden", args: [] }] : []),
    ];
  }
  function actionAvailable(action) {
    return (!action.method || available(action.method)) && (action.method !== "ruheUmschalten"
      || (state && typeof state.ruhe === "boolean" && Date.now() - lastGood < 12000));
  }
  function runAction(action) {
    if (!actionAvailable(action)) { notify("Diese Aktion ist mit dem aktuellen Status nicht verfügbar."); return; }
    close();
    if (action.run) action.run();
    else if (call(action.method, action.args)) notify(action.method === "eingabe" ? "Auftrag an Klaus übergeben." : "Aktion an Klaus übergeben.");
  }
  function renderResults() {
    const text = $("cc-search").value.trim(), query = text.toLocaleLowerCase("de");
    results = actions().filter((a) => `${a.title} ${a.info}`.toLocaleLowerCase("de").includes(query));
    if (text && available("eingabe")) results.push({ title: "An Klaus senden", info: text, method: "eingabe", args: [text] });
    selected = Math.max(0, Math.min(selected, results.length - 1));
    const list = $("cc-results"); list.replaceChildren();
    results.forEach((a, i) => {
      const b = el("button", "cc-result" + (i === selected ? " selected" : ""));
      const label = el("span"); label.append(el("b", "", a.title), el("small", "", a.info));
      b.append(label, el("span", "", a.method === "eingabe" ? "SENDEN" : "↵"));
      b.disabled = !actionAvailable(a); b.onclick = () => runAction(a);
      b.onfocus = () => { selected = i; list.querySelectorAll(".cc-result").forEach((row, n) => row.classList.toggle("selected", n === i)); };
      list.append(b);
    });
    if (!results.length) list.append(el("p", "", "Keine passende Aktion. Die Verbindung zu Klaus ist noch nicht verfügbar."));
  }
  $("cc-search").oninput = () => { selected = 0; renderResults(); };
  $("cc-search").onkeydown = (e) => {
    if (["ArrowDown", "ArrowUp"].includes(e.key)) {
      e.preventDefault(); selected = (selected + (e.key === "ArrowDown" ? 1 : -1) + results.length) % (results.length || 1);
      renderResults(); $("cc-results").children[selected]?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter" && results[selected]) { e.preventDefault(); runAction(results[selected]); }
  };
  // Capture verhindert, dass Escape im Dialog bestehende Freigabe-Pop-ups schliesst.
  addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); e.stopImmediatePropagation(); palette.hidden ? open(palette) : close(); return; }
    const layer = !palette.hidden ? palette : !control.hidden ? control : null;
    if (!layer) return;
    if (e.key === "Escape") { e.preventDefault(); e.stopImmediatePropagation(); close(); }
    if (e.key === "Tab") {
      const focusable = [...layer.querySelectorAll("button:not(:disabled), input:not(:disabled)")];
      const first = focusable[0], last = focusable.at(-1);
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  }, true);

  function strip(id, value, tone = "") { const b = $(id); b.querySelector("b").textContent = value; b.className = tone; }
  function updateState() {
    const fresh = state && Date.now() - lastGood < 12000;
    strip("cc-connection", !bridge ? "Verbinde …" : fresh ? "Lokal verbunden" : "Status ausstehend", fresh ? "" : "attention");
    $("cc-freshness").textContent = fresh ? `Letzte Abfrage ${new Date(lastGood).toLocaleTimeString("de-DE")} · lokal` : "Kein aktueller Betriebsstatus verfügbar.";
    document.querySelectorAll("[data-bridge]").forEach((b) => { b.disabled = !available(b.dataset.bridge); });
    $("cc-memory").disabled = !available("graph");
    $("cc-timer").disabled = $("cc-timer-off").disabled = !available("pcTimer");
    $("cc-timer-form").querySelector('[type="submit"]').disabled = !available("pcTimer");
    $("cc-end-record").disabled = !fresh || !state?.protokoll?.aktiv || !available("protokollBeenden");
    $("cc-end-coach").disabled = !fresh || !state?.coach?.aktiv || !available("coachBeenden");
    const quietKnown = fresh && typeof state.ruhe === "boolean";
    $("cc-quiet-toggle").disabled = !quietKnown || !available("ruheUmschalten");
    $("cc-quiet-toggle").setAttribute("aria-pressed", String(quietKnown && state.ruhe));
    $("cc-quiet-toggle").textContent = quietKnown ? state.ruhe ? "Ruhe aus" : "Ruhe an" : "Umschalten";
    $("cc-record-warning").hidden = true;
    $("cc-record-warning").textContent = "";
    $("cc-ai-day").textContent = $("cc-ai-month").textContent = $("cc-speech-detail").textContent = "";
    if (!fresh) {
      ["cc-audio", "cc-recording", "cc-pc"].forEach((id) => strip(id, "Status ausstehend"));
      ["cc-audio-detail", "cc-record-detail", "cc-coach-detail", "cc-pc-detail", "cc-auth-detail", "cc-quiet-detail", "cc-ai-mode"].forEach((id) => { $(id).textContent = "Kein aktueller Status"; });
      return;
    }
    const p = state.protokoll || {}, pc = state.pc || {};
    const audio = state.mikroAus ? "Mikrofon aus" : state.stumm ? "Klaus stumm" : "Mikrofon an";
    strip("cc-audio", audio, state.mikroAus || state.stumm ? "attention" : "");
    $("cc-audio-detail").textContent = audio;
    $("cc-quiet-detail").textContent = quietKnown ? state.ruhe ? "Aktiv · Antworten nur als Text" : "Aus · direkte Antworten dürfen sprechen" : "Ruhemodus-Status nicht verfügbar";
    if (quietKnown && state.ruhe) strip("cc-audio", `${audio} · Ruhe`, "attention");
    const speech = state.sprachausgabe;
    if (speech && typeof speech.gesprochen === "boolean") {
      const timestamp = typeof speech.zeit === "number" && Number.isFinite(speech.zeit) ? new Date(speech.zeit * 1000) : null;
      const time = timestamp && Number.isFinite(timestamp.getTime()) ? timestamp.toLocaleTimeString("de-DE") : "";
      $("cc-speech-detail").textContent = [speech.gesprochen ? "Letzte Ausgabe: gesprochen" : "Letzte Ausgabe: Versuch unterdrückt", speech.quelle ? `Anlass: ${speech.quelle}` : "", time ? `Zeit: ${time}` : ""].filter(Boolean).join(" · ");
    }
    const money = (v) => typeof v === "number" && Number.isFinite(v) && v >= 0 ? `${v.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 4 })} USD` : "nicht gemeldet";
    const ai = state.ki;
    const errors = ai?.fehlers || ai?.fehler;
    const blocked = Array.isArray(errors) ? errors.length > 0 : !!errors;
    $("cc-ai-mode").textContent = blocked ? "KI-Budget nicht verfügbar · blockiert" : ai && typeof ai.premium_aktiv === "boolean" ? ai.premium_aktiv ? "Premium-KI aktiv" : "Premium-KI deaktiviert" : "KI-Budget nicht verfügbar";
    if (ai && !blocked) {
      // Budgetwerte koennen Reservierungen enthalten: ohne getrennte Buchung keine Rechnung behaupten.
      const summary = (label, used, limit, reserved) => `${label}: Budgetbelegung ${money(used)} / Limit ${money(limit)} · davon reserviert ${money(reserved)}`;
      $("cc-ai-day").textContent = summary("Heute", ai.tag_usd, ai.tageslimit_usd, ai.tag_reserviert);
      $("cc-ai-month").textContent = summary("Monat", ai.monat_usd, ai.monatslimit_usd, ai.monat_reserviert);
    }
    // Schaltertexte folgen dem echten Zustand statt dem letzten Klick.
    control.querySelector('[data-bridge="stummUmschalten"]').textContent = state.stumm ? "Ton an" : "Stumm";
    control.querySelector('[data-bridge="mikroUmschalten"]').textContent = state.mikroAus ? "Mikro an" : "Mikro aus";
    $("knopf-stumm").setAttribute("aria-pressed", String(!!state.stumm)); $("knopf-mikro").setAttribute("aria-pressed", String(!!state.mikroAus));
    const duration = `${Math.floor((p.sekunden || 0) / 60)} min`;
    strip("cc-recording", p.aktiv ? `Aufnahme · ${duration}` : "Keine Aufnahme", p.aktiv ? "attention" : "");
    $("cc-record-detail").textContent = p.aktiv ? `${p.titel || "Meeting"} · ${duration} · ${p.zeilen || 0} Zeilen` : "Keine Aufnahme aktiv";
    if (p.aktiv && p.gesundheit?.warnung) {
      const seconds = p.gesundheit.sekunden_ohne_text;
      $("cc-record-warning").hidden = false;
      $("cc-record-warning").textContent = ["Mitschrift prüfen", p.gesundheit.grund || "Aufnahme meldet eine Warnung", typeof seconds === "number" && Number.isFinite(seconds) ? `${Math.max(0, Math.floor(seconds))} s ohne Text` : ""].filter(Boolean).join(" · ");
      strip("cc-recording", "Aufnahme · Warnung", "attention");
    }
    $("cc-coach-detail").textContent = state.coach?.aktiv ? "Coach aktiv" : "Coach beendet";
    strip("cc-pc", pc.gesperrt ? "Gesperrt" : pc.aktiv ? "Wird benutzt" : "Frei", pc.aktiv ? "attention" : pc.gesperrt ? "danger" : "");
    $("cc-pc-detail").textContent = [pc.gesperrt ? "Gesperrt" : pc.aktiv ? "Aktiv" : "PC ist frei", (pc.arten || []).join(", "), pc.aktiv ? pc.was : "", pc.restzeit ? `Zeitlimit: ${pc.restzeit}` : ""].filter(Boolean).join(" · ");
    $("cc-auth-detail").textContent = state.freigabe ? "Eine Aktion wartet auf deine Freigabe." : "Keine Freigabe ausstehend";
  }
  function poll() {
    if (document.hidden || suspended || window.klausPause || !available("ladeBetrieb")) return;
    updateState(); if (polling) return;
    polling = true;
    const timeout = setTimeout(() => { polling = false; lastGood = 0; updateState(); }, 4500);
    try {
      bridge.ladeBetrieb((raw) => {
        clearTimeout(timeout); polling = false;
        try { const next = JSON.parse(raw); if (!next || typeof next !== "object" || typeof next.mikroAus !== "boolean") throw new Error("status"); state = next; lastGood = Date.now(); }
        catch { lastGood = 0; }
        updateState();
      });
    } catch { clearTimeout(timeout); polling = false; lastGood = 0; updateState(); }
  }
  updateState();
  klausBereit.then((k) => {
    bridge = k;
    k.sichtbar?.connect((visible) => { suspended = !visible; });
    poll(); syncViews();
  }).catch(() => { strip("cc-connection", "Nicht verbunden", "danger"); });
  setInterval(poll, 5000);
})();
