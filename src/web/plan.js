// Plan-Board (Holo-Pop-up "plan") und eigene Widgets (Typ "eigen").
// Plan: {titel, ziel, boxen: [{titel, art, eintraege}]}; art: liste | notiz | zeitplan | zahlen (siehe planer.py).

const PLAN_SYMBOL = { liste: "☐", notiz: "¶", zeitplan: "◷", zahlen: "#" };

// Inhalt einer Box bzw. eines eigenen Widgets zeichnen. eintraege: Text oder {text, erledigt} (Liste)
function eigenInhalt(ziel, art, eintraege, umschalten) {
  ziel.innerHTML = "";
  ziel.className = `eigen eigen-${art}`;
  eintraege.forEach((e, i) => {
    const text = typeof e === "string" ? e : e.text, erledigt = typeof e === "object" && e.erledigt;
    if (art === "liste") {
      const z = el("button", "eigen-punkt" + (erledigt ? " erledigt" : ""));
      z.append(el("i"), el("span", "", text));
      if (umschalten) z.onclick = () => umschalten(i);
      ziel.append(z);
    } else if (art === "zeitplan") {
      const [wann, was] = text.includes("|") ? text.split("|").map((x) => x.trim()) : ["", text];
      const z = el("div", "eigen-zeit");
      z.append(el("b", "", wann), el("span", "", was));
      ziel.append(z);
    } else if (art === "zahlen") {
      const [name, wert] = text.includes(":") ? [text.slice(0, text.indexOf(":")), text.slice(text.indexOf(":") + 1)] : [text, ""];
      const z = el("div", "eigen-zahl");
      z.append(el("span", "", name.trim()), el("b", "", wert.trim()));
      ziel.append(z);
    } else {
      ziel.append(el("p", "eigen-absatz", text));
    }
  });
  if (!eintraege.length) ziel.append(el("div", "leer", "NOCH LEER · „KLAUS, SCHREIB … IN DIESES WIDGET“"));
}

// ------------------------------------------------------------------ Plan-Board
POPUP_GROESSE.plan = [0.62, 0.86];
POPUP_DAUER.plan = 1800;
POPUP_TITEL.plan = "PLAN";

POPUP_ARTEN.plan = function (box) {
  box.classList.add("p-plan");
  box.innerHTML = `<div class="plan-kopf"><div><b class="plan-titel"></b><span class="plan-ziel"></span></div>
      <button class="hud-knopf plan-anheften" title="Jede Box als eigenes Widget ins Panel">⇲ Als Widgets anheften</button></div>
    <div class="plan-boxen"><svg class="plan-linien"></svg></div>`;
  const boxen = box.querySelector(".plan-boxen"), linien = box.querySelector(".plan-linien");
  let plan = null;
  const verbinden = () => {   // Leuchtlinien von Box zu Box (Ablauf)
    const k = [...boxen.querySelectorAll(".plan-box")], B = boxen.getBoundingClientRect();
    linien.setAttribute("viewBox", `0 0 ${B.width} ${B.height}`);
    linien.innerHTML = k.slice(1).map((b, i) => {
      const a = k[i].getBoundingClientRect(), c = b.getBoundingClientRect();
      const x1 = a.left + a.width / 2 - B.left, y1 = a.top + a.height / 2 - B.top, x2 = c.left + c.width / 2 - B.left, y2 = c.top + c.height / 2 - B.top;
      return `<path d="M${x1} ${y1} C${(x1 + x2) / 2} ${y1} ${(x1 + x2) / 2} ${y2} ${x2} ${y2}" style="animation-delay:${(i + 1) * 0.35}s"/>`;
    }).join("");
  };
  new ResizeObserver(verbinden).observe(boxen);
  box.querySelector(".plan-anheften").onclick = () => {
    if (!plan || typeof klaus === "undefined") return;
    klaus.planAnheften(JSON.stringify(plan));
    box.querySelector(".plan-anheften").textContent = "✓ Angeheftet";
  };
  return {
    update(d) {
      if (!d.boxen) return;
      plan = d;
      box.querySelector(".plan-titel").textContent = d.titel || "Plan";
      box.querySelector(".plan-ziel").textContent = d.ziel ? `ZIEL · ${d.ziel}` : "";
      boxen.querySelectorAll(".plan-box").forEach((b) => b.remove());
      d.boxen.forEach((b, i) => {   // Boxen erscheinen nacheinander
        const k = el("section", "plan-box");
        k.style.animationDelay = `${i * 0.35}s`;
        const kopf = el("div", "plan-box-kopf");
        kopf.append(el("i", "", PLAN_SYMBOL[b.art] || "◆"), el("span", "", b.titel), el("small", "", String(i + 1).padStart(2, "0")));
        const inhalt = el("div");
        eigenInhalt(inhalt, b.art, b.eintraege || []);
        k.append(kopf, inhalt);
        boxen.append(k);
      });
      setTimeout(verbinden, 60);
    },
  };
};

// ------------------------------------------------------------------ Eigene Widgets (Panel)
if (typeof TYPEN !== "undefined") {
  TYPEN.eigen = {
    titel: "Eigenes Widget", info: "Checkliste, Notiz, Zeitplan oder Kennzahlen – Klaus füllt es per Stimme", w: 3, h: 7, minW: 2, minH: 3, mehrfach: true,
    bauen(c) {
      const e = c.einst;
      e.art = e.art || "liste";
      e.eintraege = (e.eintraege || []).map((x) => (typeof x === "string" && e.art === "liste" ? { text: x, erledigt: false } : x));
      c.setTitel(e.titel || "Eigenes Widget");
      const titel = c.inhalt.closest(".w").querySelector(".w-titel");
      if (titel) titel.dataset.text = e.titel || "Eigenes Widget";
      const ziel = el("div");   // eigenes Kind-Element: c.inhalt behaelt seine Klasse (Abstand, Scrollen)
      c.inhalt.append(ziel);
      const zeichnen = () => eigenInhalt(ziel, e.art, e.eintraege, (i) => { e.eintraege[i].erledigt = !e.eintraege[i].erledigt; c.speichern(); zeichnen(); });
      c.modell.neuZeichnen = zeichnen;
      zeichnen();
    },
  };
}

// Sprach-Aenderung an einem eigenen Widget: {titel, unteraktion: hinzufuegen|abhaken|entfernen|ersetzen, text, eintraege}
function eigenAendern(a) {
  const such = (a.titel || "").toLowerCase();
  const m = modelle.find((x) => x.typ === "eigen" && (x.einst.titel || "").toLowerCase().includes(such))
    || [...modelle].reverse().find((x) => x.typ === "eigen");
  if (!m) return false;
  const e = m.einst, passt = (x) => (typeof x === "string" ? x : x.text).toLowerCase().includes((a.text || "").toLowerCase());
  if (a.unteraktion === "hinzufuegen") e.eintraege.push(e.art === "liste" ? { text: a.text, erledigt: false } : a.text);
  else if (a.unteraktion === "abhaken") { const x = e.eintraege.find((y) => typeof y === "object" && passt(y)); if (x) x.erledigt = true; }
  else if (a.unteraktion === "entfernen") e.eintraege = e.eintraege.filter((x) => !passt(x));
  else if (a.unteraktion === "ersetzen") e.eintraege = (a.eintraege || []).map((x) => (e.art === "liste" ? { text: x, erledigt: false } : x));
  if (m.neuZeichnen) m.neuZeichnen();
  speichern();
  hervorheben(m.id);
  return true;
}
