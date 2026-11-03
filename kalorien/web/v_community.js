/* Community: Feed, Folge-ich, Rangliste, Forum, Chat, Profile, Beitraege, Suche. */
import {$, h, api, los, toast, leeren, icon, sheet, bestaetigen, kopf, zurueck, leer, avatar, vor, de, tagName, skelett, verkleinernBis} from "./core.js";

const ART = {training: ["Training", "ember"], mahlzeit: ["Mahlzeit", "volt"], fortschritt: ["Fortschritt", "gold"]};
const TABS = [["feed", "Feed"], ["folge", "Folge ich"], ["rangliste", "Rangliste"], ["forum", "Forum"], ["chat", "Chat"]];

export async function communitySeite(ctx) {
  const tab = ctx.teile[0] || "feed";
  if (tab === "chat") { location.replace("#/chat"); return; }
  const chips = h("div", {class: "chips", style: {marginBottom: "10px"}}, TABS.map(([k, n]) => h("button", {class: "chip" + (tab === k ? " an" : ""), onclick: () => { location.hash = k === "chat" ? "#/chat" : "#/community/" + k; }}, n)));
  const inhalt = h("div", {}, skelett(3, 200));
  leeren(ctx.box, h("div", {class: "in"}, kopf("Community", "Die Crew", [h("button", {class: "ikon", "aria-label": "Leute suchen", onclick: suche}, icon("suche")),
    h("button", {class: "ikon", "aria-label": "Beitrag schreiben", onclick: () => beitragNeu()}, icon("plus"))]), chips, inhalt));
  if (tab === "feed" || tab === "folge") {
    const liste = await api("GET", "feed" + (tab === "folge" ? "?art=folge" : ""));
    if (!ctx.aktuell()) return;
    leeren(inhalt, liste.length ? liste.map(b => beitragKarte(b)) : leer(tab === "folge" ? "Noch nichts von deiner Crew" : "Noch keine Beiträge",
      tab === "folge" ? "Folge Leuten über die Suche, dann erscheinen ihre Beiträge hier." : "Teile dein Training, dein Essen oder deinen Fortschritt.", h("button", {class: "btn klein", onclick: () => beitragNeu()}, "Ersten Beitrag schreiben")));
  } else if (tab === "rangliste") {
    const r = await api("GET", "rangliste");
    if (!ctx.aktuell()) return;
    leeren(inhalt, h("div", {class: "hinweisbox"}, icon("pokal"), "Aktive Trainingsminuten der letzten 7 Tage (pro Tag höchstens 240 gezählt). Mitmachen kannst du unter Ich → Rangliste."),
      r.length ? h("div", {class: "karte"}, r.map((x, i) => h("div", {class: "rang" + (x.ich ? " ich" : ""), onclick: () => { location.hash = "#/profil/" + encodeURIComponent(x.name); }, style: {cursor: "pointer"}},
        h("span", {class: "nr"}, i + 1), avatar(x.name, "mittel"), h("div", {class: "fuell"}, h("div", {class: "disp", style: {fontSize: "20px"}}, x.name), h("div", {class: "mut klein"}, `${x.tage} Trainingstage`)),
        h("b", {class: "zahl", style: {fontSize: "26px"}}, de(x.minuten), h("span", {class: "mut klein"}, " Min"))))) : leer("Noch niemand in der Rangliste", "Trag ein Training ein und mach mit."));
  } else if (tab === "forum") {
    const t = await api("GET", "forum");
    if (!ctx.aktuell()) return;
    leeren(inhalt, h("button", {class: "btn", style: {marginBottom: "12px"}, onclick: neuesThema}, icon("plus"), "Neues Thema"),
      t.length ? t.map(x => h("button", {class: "karte klick", style: {width: "100%", textAlign: "left"}, onclick: () => { location.hash = "#/forum/" + x.id; }},
        h("div", {class: "disp", style: {fontSize: "21px", marginBottom: "6px"}}, x.titel), h("div", {class: "mut klein"}, `${x.name} · ${x.antworten} Antworten · ${vor(x.letzte)}`))) : leer("Noch keine Themen", "Stell eine Frage oder teile einen Tipp."));
  }
}

export function beitragKarte(b, detail = false) {
  const gefaellt = h("button", {class: b.geliked ? "an" : "", "aria-label": "Gefällt mir", onclick: () => los(async () => { const d = await api("POST", `beitrag/${b.id}/gefaellt`, {}); b.geliked = d.geliked; gefaellt.classList.toggle("an", d.geliked); gefaellt.lastChild.textContent = de(d.likes); })}, icon("herz"), h("span", {}, de(b.likes)));
  const art = ART[b.art];
  const karte = h("div", {class: "karte beitrag flach"},
    h("div", {class: "kopfz"}, h("button", {onclick: () => { location.hash = "#/profil/" + encodeURIComponent(b.name); }, "aria-label": "Profil von " + b.name}, avatar(b.name, "mittel")),
      h("div", {class: "fuell"}, h("b", {}, b.name), h("span", {class: "mut klein"}, vor(b.erstellt))), art ? h("span", {class: "badge " + art[1]}, art[0]) : null,
      h("button", {class: "ikon ohne", "aria-label": "Mehr", onclick: () => menue(b)}, icon("mehr"))),
    b.video ? h("video", {src: b.video, poster: b.poster || undefined, controls: true, playsinline: true, preload: "metadata", style: {width: "100%", maxHeight: "70vh", background: "#000", display: "block"}}) : null,
    b.bild ? h("img", {class: "bild", src: b.bild, alt: "Foto von " + b.name, loading: "lazy", onclick: () => { if (!detail) location.hash = "#/beitrag/" + b.id; }}) : null,
    b.text ? h("div", {class: "text"}, b.text) : null,
    h("div", {class: "aktionen"}, gefaellt, h("button", {"aria-label": "Kommentare", onclick: () => detail ? null : (location.hash = "#/beitrag/" + b.id)}, icon("kommentar"), h("span", {}, de(b.kommentare)))));
  return karte;
}

function menue(b) {
  const zeile = (ikon, text, tun, c = "") => h("button", {class: "liste-zeile " + c, style: {width: "100%", textAlign: "left"}, onclick: () => { zu(); tun(); }}, icon(ikon, 22), h("div", {class: "fuell"}, text));
  const zu = sheet(null, () => b.eigen ? [zeile("papierkorb", "Beitrag löschen", async () => { if (await bestaetigen("Diesen Beitrag löschen?", "Löschen", true)) los(async () => { await api("POST", "loeschen", {art: "beitrag", id: b.id}); toast("Gelöscht"); window.dispatchEvent(new HashChangeEvent("hashchange")); }); }, "ember")]
    : [zeile("fahne", "Melden", () => los(async () => toast((await api("POST", "melden", {art: "beitrag", id: b.id, grund: "Beitrag gemeldet"})).text))),
      zeile("sperren", `${b.name} blockieren`, async () => { if (await bestaetigen(`${b.name} blockieren?`, "Blockieren", true)) los(async () => { toast((await api("POST", "blockieren", {name: b.name})).text); window.dispatchEvent(new HashChangeEvent("hashchange")); }); })]);
}

export function beitragNeu() {
  let art = "text", bild = null;
  const text = h("textarea", {placeholder: "Was gibt's Neues? Training, Mahlzeit, Fortschritt …", maxlength: 1000, style: {minHeight: "110px"}});
  const datei = h("input", {type: "file", accept: "image/*", hidden: true}), vorschau = h("div", {});
  datei.addEventListener("change", () => los(async () => {
    if (!datei.files[0]) return; bild = await verkleinernBis(datei.files[0]);
    leeren(vorschau, h("img", {src: bild, alt: "", style: {width: "100%", maxHeight: "220px", objectFit: "cover", borderRadius: "12px", margin: "10px 0"}}));
  }));
  const chips = h("div", {class: "chips", style: {margin: "10px -18px"}});
  const male = () => leeren(chips, [["text", "Allgemein"], ["training", "Training"], ["mahlzeit", "Mahlzeit"], ["fortschritt", "Fortschritt"]].map(([k, n]) => h("button", {class: "chip" + (art === k ? " an" : ""), onclick: () => { art = k; male(); }}, n)));
  male();
  sheet("Neuer Beitrag", zu => [text, chips, vorschau, datei, h("div", {class: "knopfreihe"}, h("button", {class: "btn zweit", onclick: () => datei.click()}, icon("kamera"), "Foto"),
    h("button", {class: "btn", onclick: () => los(async () => { await api("POST", "beitrag", {art, text: text.value, bild: bild ? bild.split(",")[1] : undefined}); zu(); toast("Gepostet"); location.hash = "#/community/feed"; window.dispatchEvent(new HashChangeEvent("hashchange")); })}, "Posten"))]);
}

export async function beitragSeite(ctx) {
  const b = await api("GET", "beitrag/" + ctx.teile[0]);
  if (!ctx.aktuell()) return;
  const liste = h("div", {}), eingabe = h("input", {placeholder: "Kommentieren …", maxlength: 500, "aria-label": "Kommentar"});
  const male = () => leeren(liste, b.kommentar_liste.length ? b.kommentar_liste.map(k => h("div", {class: "kommentar"}, avatar(k.name, "klein"), h("div", {class: "fuell"}, h("div", {}, h("b", {}, k.name), h("span", {class: "mut klein"}, vor(k.erstellt)),
    k.eigen ? h("button", {class: "mut klein", style: {marginLeft: "10px"}, onclick: () => los(async () => { await api("POST", "loeschen", {art: "kommentar", id: k.id}); b.kommentar_liste = b.kommentar_liste.filter(x => x.id !== k.id); male(); })}, "Löschen") : null),
    h("div", {style: {whiteSpace: "pre-wrap", wordBreak: "break-word"}}, k.text)))) : h("p", {class: "mut", style: {padding: "10px 0"}}, "Noch keine Kommentare."));
  male();
  const senden = () => los(async () => { if (!eingabe.value.trim()) return; await api("POST", `beitrag/${b.id}/kommentar`, {text: eingabe.value}); b.kommentar_liste = (await api("GET", "beitrag/" + b.id)).kommentar_liste; eingabe.value = ""; male(); });
  eingabe.addEventListener("keydown", e => { if (e.key === "Enter") senden(); });
  leeren(ctx.box, h("div", {class: "in"}, zurueck(null), beitragKarte(b, true), h("div", {class: "abschnitt"}, h("h2", {}, "Kommentare")), liste,
    h("div", {class: "zeile", style: {marginTop: "10px"}}, h("div", {class: "fuell"}, eingabe), h("button", {class: "btn klein", onclick: senden, "aria-label": "Senden"}, icon("senden")))));
}

/* ---------- Profil ---------- */
export async function profilSeite(ctx) {
  const name = decodeURIComponent(ctx.teile[0]);
  const [p, posts, reels] = await Promise.all([api("GET", "profil/" + encodeURIComponent(name)), api("GET", "feed?von=" + encodeURIComponent(name)), api("GET", "reels?von=" + encodeURIComponent(name)).catch(() => [])]);
  if (!ctx.aktuell()) return;
  let folgt = p.folgt_ihm, folger = p.folger;
  const knopf = h("button", {class: "btn" + (folgt ? " zweit" : ""), style: {marginTop: "14px"}, onclick: () => los(async () => {
    const d = await api(folgt ? "DELETE" : "POST", "folgen", {name}); folgt = d.folgt; folger += folgt ? 1 : -1; knopf.textContent = folgt ? "Folge ich" : "Folgen"; knopf.classList.toggle("zweit", folgt); zahlF.textContent = de(folger); })}, folgt ? "Folge ich" : "Folgen");
  const zahlF = h("b", {}, de(folger));
  let ansicht = reels.length ? "reels" : "posts";
  const gitter = h("div", {class: "gitter"});
  const male = () => {
    const liste = ansicht === "reels" ? reels : posts;
    leeren(gitter, liste.length ? liste.map(x => h("a", {href: "#/beitrag/" + x.id, "aria-label": ansicht === "reels" ? "Reel ansehen" : "Beitrag ansehen"},
      x.poster || x.bild ? h("img", {src: x.poster || x.bild, alt: "", loading: "lazy"}) : h("div", {style: {padding: "10px", fontSize: "14px", color: "var(--mut)", overflow: "hidden"}}, x.text),
      ansicht === "reels" ? h("span", {class: "dauer"}, icon("herz", 14), de(x.likes)) : null)) : [h("div", {style: {gridColumn: "1 / -1", aspectRatio: "auto", padding: "28px", background: "none"}, class: "mut mitte"}, "Noch nichts da.")]);
  };
  const seg = h("div", {class: "seg", style: {margin: "16px 0 10px"}}, [["reels", "Reels"], ["posts", "Beiträge"]].map(([k, n]) => h("button", {class: ansicht === k ? "an" : "", onclick: e => { ansicht = k; seg.querySelectorAll("button").forEach(b => b.classList.toggle("an", b === e.currentTarget)); male(); }}, n)));
  male();
  leeren(ctx.box, h("div", {class: "in"}, zurueck(null),
    h("div", {class: "profil-kopf"}, avatar(p.name, "gross"), h("div", {class: "fuell"}, h("h1", {style: {fontSize: "32px"}}, p.name), h("div", {class: "mut klein", style: {marginTop: "6px"}}, "Dabei seit " + tagName(new Date(p.seit * 1000).toISOString().slice(0, 10), {month: "short", year: "numeric"})))),
    p.bio ? h("p", {style: {marginBottom: "4px"}}, p.bio) : null,
    h("div", {class: "zahlen3"}, h("div", {}, h("b", {class: "ember"}, p.serie), h("span", {class: "lab"}, "Serie")), h("div", {}, h("b", {}, de(p.trainings)), h("span", {class: "lab"}, "Trainings")), h("div", {}, zahlF, h("span", {class: "lab"}, "Follower")), h("div", {}, h("b", {}, de(p.folgt)), h("span", {class: "lab"}, "Folgt"))),
    p.abzeichen.length ? h("div", {class: "abzeichen"}, p.abzeichen.map(a => h("span", {class: "badge gold"}, a.name))) : null,
    p.ich ? h("button", {class: "btn zweit", style: {marginTop: "14px"}, onclick: () => { location.hash = "#/ich"; }}, "Profil bearbeiten") : knopf, seg, gitter));
}

/* ---------- Suche ---------- */
function suche() {
  const eingabe = h("input", {placeholder: "Name suchen (mind. 2 Buchstaben)", maxlength: 24, "aria-label": "Name suchen", autofocus: true}), liste = h("div", {style: {marginTop: "10px"}});
  let t;
  eingabe.addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => los(async () => {
    const r = eingabe.value.trim().length >= 2 ? await api("GET", "suche?q=" + encodeURIComponent(eingabe.value.trim())) : [];
    leeren(liste, r.map(x => h("div", {class: "liste-zeile", onclick: () => { zu(); location.hash = "#/profil/" + encodeURIComponent(x.name); }}, avatar(x.name, "mittel"), h("div", {class: "fuell disp", style: {fontSize: "20px"}}, x.name), icon("rechts", 18))));
  }), 250); });
  const zu = sheet("Leute finden", () => [eingabe, liste]);
}

/* ---------- Forum ---------- */
function neuesThema() {
  const titel = h("input", {placeholder: "Titel", maxlength: 120, "aria-label": "Titel"}), text = h("textarea", {placeholder: "Deine Frage oder dein Tipp …", maxlength: 4000});
  sheet("Neues Thema", zu => [h("div", {class: "feld"}, titel), h("div", {class: "feld"}, text), h("p", {class: "hilfe", style: {marginBottom: "12px"}}, "Sei freundlich. Beleidigungen, Werbung und gefährliche Diäten (Crash-Diäten, Essstörungs-Tipps) sind nicht erlaubt."),
    h("button", {class: "btn", onclick: () => los(async () => { const d = await api("POST", "forum", {titel: titel.value, text: text.value}); zu(); location.hash = "#/forum/" + d.id; })}, "Veröffentlichen")]);
}

export async function forumThema(ctx) {
  const t = await api("GET", "forum/" + ctx.teile[0]);
  if (!ctx.aktuell()) return;
  const eingabe = h("textarea", {placeholder: "Antworten …", maxlength: 2000, style: {minHeight: "80px"}});
  const post = (art, id, text, eigen, name, zeit) => h("div", {class: "kommentar"}, avatar(name, "klein"), h("div", {class: "fuell"}, h("div", {}, h("b", {}, name), h("span", {class: "mut klein"}, vor(zeit)),
    h("button", {class: "mut klein", style: {marginLeft: "10px"}, onclick: () => eigen ? los(async () => { await api("POST", "loeschen", {art, id}); window.dispatchEvent(new HashChangeEvent("hashchange")); }) : los(async () => toast((await api("POST", "melden", {art, id, grund: "gemeldet"})).text))}, eigen ? "Löschen" : "Melden")),
    h("div", {style: {whiteSpace: "pre-wrap", wordBreak: "break-word"}}, text)));
  leeren(ctx.box, h("div", {class: "in"}, zurueck("#/community/forum", "Forum"), h("h1", {style: {fontSize: "30px", margin: "6px 0 14px"}}, t.titel),
    h("div", {class: "karte"}, post("thema", t.id, t.text, t.eigen, t.name, t.erstellt)),
    h("div", {class: "abschnitt"}, h("h2", {}, `${t.antworten.length} Antworten`)), t.antworten.map(a => post("antwort", a.id, a.text, a.eigen, a.name, a.erstellt)),
    h("div", {style: {marginTop: "14px"}}, eingabe, h("button", {class: "btn", style: {marginTop: "10px"}, onclick: () => los(async () => { await api("POST", `forum/${t.id}/antwort`, {text: eingabe.value}); window.dispatchEvent(new HashChangeEvent("hashchange")); })}, "Antworten"))));
}

/* ---------- Chat ---------- */
export async function chatSeite(ctx) {
  let letzte = 0, nachrichten = [];
  const verlauf = h("div", {style: {minHeight: "50vh", paddingBottom: "120px"}}), eingabe = h("input", {placeholder: "Nachricht an alle …", maxlength: 500, "aria-label": "Nachricht"});
  const zeichne = () => leeren(verlauf, nachrichten.length ? nachrichten.map(n => h("div", {class: "blase" + (n.eigen ? " eigen" : "")}, n.eigen ? null : h("small", {}, n.name), n.text)) : h("p", {class: "mut mitte", style: {padding: "40px 0"}}, "Noch keine Nachrichten. Sag Hallo."));
  const hole = async () => {
    const neu = await api("GET", "chat?nach=" + letzte);
    if (neu.length) { nachrichten.push(...neu); letzte = nachrichten[nachrichten.length - 1].id; zeichne(); window.scrollTo(0, document.body.scrollHeight); }
  };
  const takt = setInterval(() => hole().catch(() => {}), 4000); ctx.aufraeumen(() => clearInterval(takt));
  const senden = () => los(async () => { if (!eingabe.value.trim()) return; const text = eingabe.value; eingabe.value = ""; await api("POST", "chat", {text}); await hole(); });
  eingabe.addEventListener("keydown", e => { if (e.key === "Enter") senden(); });
  leeren(ctx.box, h("div", {class: "in"}, zurueck("#/community/feed", "Community"), kopf("Chat", "Live · alle Mitglieder"), verlauf),
    h("div", {class: "eingabeleiste"}, eingabe, h("button", {class: "btn", onclick: senden, "aria-label": "Senden"}, icon("senden"))));
  await hole();
}
