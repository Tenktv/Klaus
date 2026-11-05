/* Reels: Vollbild-Feed (Scroll-Snap), Autoplay, Likes, Kommentare, Upload mit Fortschritt. */
import {$, S, h, api, hochladen, los, toast, leeren, icon, sheet, bestaetigen, avatar, vor, de} from "./core.js";

export async function reelsSeite(ctx) {
  let art = "alle", ende = false, laden = false, merk = null;
  const feed = h("div", {class: "reels"});
  const ton = h("button", {class: "ikon", "aria-label": "Ton an oder aus", onclick: () => { S.ton = !S.ton; tonAnzeige(); feed.querySelectorAll("video").forEach(v => { v.muted = !S.ton; }); }});
  const tonAnzeige = () => leeren(ton, icon(S.ton ? "ton" : "stumm"));
  tonAnzeige();
  const tabs = h("div", {class: "tabs"}, [["alle", "Für dich"], ["folge", "Folge ich"]].map(([k, n]) => h("button", {class: art === k ? "an" : "", onclick: () => { art = k; ende = false; kopfMalen(); neu(); }}, n)));
  const kopfMalen = () => tabs.querySelectorAll("button").forEach((b, i) => b.classList.toggle("an", (i === 0) === (art === "alle")));
  const kopf = h("div", {class: "reels-kopf"}, tabs, h("div", {class: "kopf-r"}, ton, h("button", {class: "ikon", "aria-label": "Reel hochladen", onclick: reelHochladen}, icon("video"))));
  leeren(ctx.box, feed, kopf);

  const beob = new IntersectionObserver(eintraege => {
    for (const e of eintraege) {
      const v = e.target.querySelector("video"), r = e.target;
      if (e.isIntersecting && e.intersectionRatio > .6) {
        if (!v.src) v.src = v.dataset.quelle;
        v.muted = !S.ton; v.play().catch(() => { v.muted = true; v.play().catch(() => {}); });
        // Naechste Reels nachladen, wenn man sich dem Ende naehert
        const alle = [...feed.children]; if (alle.indexOf(r) >= alle.length - 3) mehr();
      } else { v.pause(); }
    }
  }, {root: feed, threshold: [0, .6]});
  ctx.aufraeumen(() => { beob.disconnect(); feed.querySelectorAll("video").forEach(v => { v.pause(); v.removeAttribute("src"); v.load(); }); });

  function reelKarte(r) {
    const v = h("video", {playsinline: true, loop: true, muted: true, preload: "none", poster: r.poster || undefined, "data-quelle": r.video, "aria-label": "Reel von " + r.name});
    const bar = h("i", {}); v.addEventListener("timeupdate", () => { if (v.duration) bar.style.width = (v.currentTime / v.duration * 100) + "%"; });
    const gefaellt = h("button", {class: r.geliked ? "an" : "", "aria-label": "Gefällt mir", onclick: () => like()}, icon("herz"), h("span", {}, de(r.likes)));
    const like = () => los(async () => { const d = await api("POST", `beitrag/${r.id}/gefaellt`, {}); r.geliked = d.geliked; r.likes = d.likes; gefaellt.classList.toggle("an", d.geliked); gefaellt.lastChild.textContent = de(d.likes); });
    let letzterTipp = 0;
    const flaeche = h("div", {style: {position: "absolute", inset: 0, zIndex: 1}, onclick: e => {
      const jetzt = Date.now();
      if (jetzt - letzterTipp < 320) {   // Doppeltipp = Like
        letzterTipp = 0; if (!r.geliked) like();
        const herz = icon("herz"); herz.setAttribute("class", "herz-flug"); e.currentTarget.parentNode.append(herz); setTimeout(() => herz.remove(), 800);
      } else { letzterTipp = jetzt; setTimeout(() => { if (letzterTipp === jetzt) { S.ton = !S.ton; tonAnzeige(); feed.querySelectorAll("video").forEach(x => { x.muted = !S.ton; }); toast(S.ton ? "Ton an" : "Ton aus", false, 900); } }, 330); }
    }});
    const kommBtn = h("button", {"aria-label": "Kommentare", onclick: () => kommentare(r, k => { r.kommentare = k; kommBtn.lastChild.textContent = de(k); })}, icon("kommentar"), h("span", {}, de(r.kommentare)));
    const folgen = !r.eigen ? h("button", {class: "folgen" + (r.folgt ? " an" : ""), onclick: e => { const knopf = e.currentTarget; los(async () => { const d = await api(r.folgt ? "DELETE" : "POST", "folgen", {name: r.name}); r.folgt = d.folgt; knopf.classList.toggle("an", r.folgt); knopf.textContent = r.folgt ? "Folge ich" : "Folgen"; }); }}, r.folgt ? "Folge ich" : "Folgen") : null;
    return h("div", {class: "reel"}, v, flaeche,
      h("div", {class: "unten"}, h("div", {class: "autor"}, h("button", {onclick: () => { location.hash = "#/profil/" + encodeURIComponent(r.name); }, "aria-label": "Profil von " + r.name}, avatar(r.name, "mittel")),
        h("b", {}, r.name), folgen), r.text ? h("div", {class: "text"}, r.text) : null),
      h("div", {class: "schiene"}, gefaellt, kommBtn,
        h("button", {"aria-label": "Teilen", onclick: () => teilen(r)}, icon("teilen"), h("span", {}, "Senden")), h("button", {"aria-label": "Mehr", onclick: () => mehrMenue(r, () => neu())}, icon("mehr"))),
      h("div", {class: "fortschritt"}, bar));
  }
  async function neu() {
    leeren(feed, h("div", {class: "reel-leer"}, h("span", {class: "denkt"}, h("i"), h("i"), h("i"))));
    merk = null; const liste = await api("GET", "reels?art=" + art);
    if (!ctx.aktuell()) return;
    ende = liste.length < 1;
    if (!liste.length) {
      leeren(feed, h("div", {class: "reel-leer"}, h("div", {}, icon("video", 44), h("h1", {style: {margin: "14px 0 8px", fontSize: "34px"}}, art === "folge" ? "Noch nichts von deiner Crew" : "Noch keine Reels"),
        h("p", {class: "mut", style: {maxWidth: "28ch", margin: "0 auto 20px"}}, art === "folge" ? "Folge Leuten, dann erscheinen ihre Reels hier." : "Sei der Erste: Zeig dein Training, dein Essen oder deinen Fortschritt in 60 Sekunden."),
        h("button", {class: "btn", style: {width: "auto", margin: "0 auto"}, onclick: reelHochladen}, icon("hoch"), "Reel hochladen"))));
      return;
    }
    leeren(feed, liste.map(reelKarte)); merk = liste[liste.length - 1].id;
    feed.querySelectorAll(".reel").forEach(el => beob.observe(el));
  }
  async function mehr() {
    if (laden || ende || !merk) return; laden = true;
    try {
      const liste = await api("GET", `reels?art=${art}&vor=${merk}`);
      if (!liste.length) { ende = true; return; }
      for (const r of liste) { const k = reelKarte(r); feed.append(k); beob.observe(k); } merk = liste[liste.length - 1].id;
    } finally { laden = false; }
  }
  await neu();
}

function teilen(r) {
  const url = location.origin + "/#/beitrag/" + r.id;
  if (navigator.share) navigator.share({title: "Reel von " + r.name, url}).catch(() => {});
  else navigator.clipboard.writeText(url).then(() => toast("Link kopiert"), () => toast(url));
}

function mehrMenue(r, danach) {
  const zeile = (ikon, text, tun, c = "") => h("button", {class: "liste-zeile " + c, style: {width: "100%", textAlign: "left"}, onclick: () => { zu(); tun(); }}, icon(ikon, 22), h("div", {class: "fuell"}, text));
  const zu = sheet(null, () => [h("div", {class: "mut", style: {marginBottom: "6px"}}, `Reel von ${r.name}`),
    r.eigen ? zeile("papierkorb", "Reel löschen", async () => { if (await bestaetigen("Dieses Reel löschen?", "Löschen", true)) los(async () => { await api("POST", "loeschen", {art: "beitrag", id: r.id}); toast("Gelöscht"); danach(); }); }, "ember")
      : [zeile("fahne", "Melden", () => los(async () => { const d = await api("POST", "melden", {art: "beitrag", id: r.id, grund: "Reel gemeldet"}); toast(d.text); })),
        zeile("sperren", `${r.name} blockieren`, async () => { if (await bestaetigen(`${r.name} blockieren? Du siehst nichts mehr von dieser Person.`, "Blockieren", true)) los(async () => { const d = await api("POST", "blockieren", {name: r.name}); toast(d.text); danach(); }); })]]);
}

export async function kommentare(r, aktualisiert) {
  const d = await api("GET", "beitrag/" + r.id);
  const liste = h("div", {}), eingabe = h("input", {placeholder: "Kommentieren …", maxlength: 500, "aria-label": "Kommentar"});
  const male = () => leeren(liste, d.kommentar_liste.length ? d.kommentar_liste.map(k => h("div", {class: "kommentar"}, avatar(k.name, "klein"),
    h("div", {class: "fuell"}, h("div", {}, h("b", {}, k.name), h("span", {class: "mut klein"}, vor(k.erstellt)), k.eigen ? h("button", {class: "mut klein", style: {marginLeft: "10px"}, onclick: () => los(async () => { await api("POST", "loeschen", {art: "kommentar", id: k.id}); d.kommentar_liste = d.kommentar_liste.filter(x => x.id !== k.id); male(); aktualisiert && aktualisiert(d.kommentar_liste.length); })}, "Löschen") : null),
      h("div", {style: {whiteSpace: "pre-wrap", wordBreak: "break-word"}}, k.text)))) : h("p", {class: "mut mitte", style: {padding: "22px 0"}}, "Noch keine Kommentare. Schreib den ersten."));
  male();
  const senden = () => los(async () => {
    if (!eingabe.value.trim()) return;
    await api("POST", `beitrag/${r.id}/kommentar`, {text: eingabe.value});
    const neu = await api("GET", "beitrag/" + r.id); d.kommentar_liste = neu.kommentar_liste; eingabe.value = ""; male(); aktualisiert && aktualisiert(d.kommentar_liste.length);
  });
  eingabe.addEventListener("keydown", e => { if (e.key === "Enter") senden(); });
  sheet(`Kommentare`, () => [liste, h("div", {class: "zeile", style: {marginTop: "10px"}}, h("div", {class: "fuell"}, eingabe), h("button", {class: "btn klein", onclick: senden, "aria-label": "Senden"}, icon("senden")))]);
}

/* ---------- Upload ---------- */
export function reelHochladen() {
  if (!S.ich.video) return toast("Videos sind auf diesem Server noch nicht eingerichtet.", true);
  const datei = h("input", {type: "file", accept: "video/*", hidden: true});
  document.body.append(datei);
  datei.addEventListener("change", () => {
    const f = datei.files[0]; datei.remove();
    if (!f) return;
    if (f.size > 250 * 1024 * 1024) return toast("Das Video ist über 250 MB. Kürze es auf höchstens 60 Sekunden.", true);
    const text = h("textarea", {placeholder: "Beschreibung (optional) – Übung, Ziel, Tipp …", maxlength: 300, style: {minHeight: "80px"}});
    const balken = h("i", {}), status = h("div", {class: "mut klein"}, `${f.name} · ${(f.size / 1048576).toFixed(1)} MB`);
    const los_ = h("button", {class: "btn", onclick: () => los(async () => {
      los_.disabled = true; text.disabled = true; status.textContent = "Wird hochgeladen …";
      try {
        const d = await hochladen("reel?text=" + encodeURIComponent(text.value), f, p => { balken.style.width = (p * 100) + "%"; if (p >= 1) status.textContent = "Wird für alle Geräte umgewandelt …"; });
        for (let i = 0; i < 120; i++) {   // bis zu 4 Minuten auf die Umwandlung warten
          const s = await api("GET", `reel/${d.id}/status`);
          if (s.status === "fertig") { zu(); toast("Dein Reel ist online"); if (location.hash === "#/reels") window.dispatchEvent(new HashChangeEvent("hashchange")); else location.hash = "#/reels"; return; }
          if (s.status === "fehler") { await api("POST", "loeschen", {art: "beitrag", id: d.id}).catch(() => {}); throw new Error("Das Video konnte nicht verarbeitet werden. Versuch ein anderes (MP4 oder MOV)."); }
          await new Promise(ok => setTimeout(ok, 2000));
        }
        throw new Error("Die Verarbeitung dauert ungewöhnlich lange. Schau später in den Reels nach.");
      } catch (e) { los_.disabled = false; text.disabled = false; throw e; }
    })}, icon("hoch"), "Veröffentlichen");
    const zu = sheet("Neues Reel", () => [text, h("div", {class: "hochladen-ring"}, balken), status, h("div", {style: {height: "12px"}}), los_,
      h("p", {class: "hilfe"}, "Hochkant-Videos sehen am besten aus. Länger als 60 Sekunden wird gekürzt; Standort und andere Metadaten werden entfernt.")]);
  });
  datei.click();
}
