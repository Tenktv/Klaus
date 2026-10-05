// Meeting-Protokoll (Holo-Pop-up "protokoll"): REC + Laufzeit, Live-Mitschrift, am Ende Zusammenfassung + Aufgaben.
// Daten aus assistent.protokoll_* (protokoll.py). Audio wird nie gespeichert.

POPUP_GROESSE.protokoll = [0.3, 0.5];
POPUP_DAUER.protokoll = 4 * 3600;   // bleibt offen, solange aufgenommen wird
POPUP_TITEL.protokoll = "PROTOKOLL";

POPUP_ARTEN.protokoll = function (box) {
  box.classList.add("p-protokoll");
  box.innerHTML = `<div class="pr-kopf"><span class="pr-rec"><i></i>REC</span><b class="pr-zeit">00:00</b>
      <span class="pr-status">MITSCHRIFT LÄUFT</span></div>
    <div class="pr-text"></div><div class="pr-ergebnis"></div>
    <div class="pr-fuss">TON BLEIBT IM SPEICHER · NUR TEXT WIRD GESPEICHERT</div>`;
  const q = (s) => box.querySelector(s), text = q(".pr-text");
  const mmss = (s) => { s = Math.max(0, Math.floor(s)); const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, x = String(s % 60).padStart(2, "0");
    return h ? `${h}:${String(m).padStart(2, "0")}:${x}` : `${String(m).padStart(2, "0")}:${x}`; };
  let start = Date.now(), takt = null;
  const uhr = () => { if (!box.isConnected) return clearInterval(takt); q(".pr-zeit").textContent = mmss((Date.now() - start) / 1000); };
  takt = setInterval(uhr, 1000);

  return {
    update(d) {
      if (d.start) { start = d.start; uhr(); }
      if (d.status) q(".pr-status").textContent = d.status;
      if (d.zeile) {
        const z = el("div", "pr-zeile");
        z.append(el("small", "", mmss(d.t || 0)), el("span", "", d.zeile));
        text.append(z);
        while (text.children.length > 120) text.firstChild.remove();
        text.scrollTop = text.scrollHeight;
      }
      if (d.fertig) {
        clearInterval(takt);
        box.classList.add("fertig");
        q(".pr-rec").lastChild.textContent = "ENDE";
        q(".pr-zeit").textContent = `${d.minuten ?? 0} MIN`;
        q(".pr-status").textContent = (d.datei || "").split(/[\\/]/).pop().replace(/\.md$/, "").toUpperCase();
        const e = q(".pr-ergebnis");
        e.innerHTML = "";
        e.append(el("div", "lbl", "Zusammenfassung"), el("p", "", d.zusammenfassung || "–"));
        if ((d.entscheidungen || []).length) {
          e.append(el("div", "lbl", "Entscheidungen"));
          d.entscheidungen.forEach((x) => e.append(el("div", "pr-punkt", x)));
        }
        if ((d.aufgaben || []).length) {
          e.append(el("div", "lbl", "Aufgaben"));
          d.aufgaben.forEach((a) => e.append(el("div", "pr-aufgabe", `${a.was}${a.wer ? ` — ${a.wer}` : ""}${a.bis ? ` (bis ${a.bis})` : ""}`)));
        }
        q(".pr-fuss").textContent = "GESPEICHERT IM GEDÄCHTNIS · MEETINGS/";
      }
    },
  };
};
