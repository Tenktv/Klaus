"""Graphen fuers Panel (Holo-Fenster "graph", siehe web/graph.js).

- gedaechtnis(): Klaus' Obsidian-Vault als Netz - Fakten, Tagesnotizen, Briefings und die Themen, die darin
  immer wieder vorkommen (Themen verbinden Notizen und Fakten miteinander).
- projekt(name): Code-Projekt als Netz ueber graphify (`graphify update <pfad>`, rein strukturell, ohne KI/Kosten).

Format fuer das Panel: {"knoten": [{id, label, gruppe, typ, info}], "kanten": [[a, b]], "gruppen": {nr: name}}
"""
from __future__ import annotations

import collections
import json
import re
import shutil
import subprocess
from pathlib import Path

import daten
import gehirn

MAX_KNOTEN = 2500
STOPP = set("""aber alle allem allen aller alles also auch auf aus bei beim bin bis bist dann das dass dein deine dem den
denn der des dich die dies diese diesem diesen dieser dir doch dort durch ein eine einem einen einer eines etwas euch
fuer für gibt habe haben hast hat hatte ich ihm ihn ihr ihre ihrem ihren im in ist jetzt kann kannst klaus kein keine
mal man mehr mein meine mich mir mit muss nach nicht noch nur oder schon sehr sein seine sich sie sind so soll sollen
ueber über um und uns unser vom von vor war waren warst was weil wenn werden wie wieder will wir wird wo zu zum zur
gerade einfach bitte danke okay heute morgen gestern minuten stunden prozent wichtig nachrichten seit warst
nikola ja nein""".split())


def _knoten(knoten: dict, kid: str, label: str, gruppe: int, typ: str, info: str = "") -> str:
    if kid not in knoten:
        knoten[kid] = {"id": kid, "label": label[:80], "gruppe": gruppe, "typ": typ, "info": info[:240]}
    return kid


def gedaechtnis() -> dict:
    vault = gehirn.VAULT
    gruppen = {0: "Nikola", 1: "Fakten", 2: "Gespräche", 3: "Briefings", 4: "Projekte", 5: "Themen", 6: "Notizen"}
    ordner_gruppe = {"Gespraeche": 2, "Briefings": 3, "Projekte": 4}
    knoten: dict[str, dict] = {}
    kanten: set[tuple[str, str]] = set()
    nikola = _knoten(knoten, "nikola", "Nikola", 0, "Person", "Was Klaus über dich weiß (Nikola.md)")

    # Fakten
    fakten = gehirn.lade_gedaechtnis()
    for f in fakten:
        fid = _knoten(knoten, f"fakt-{f['id']}", f["text"], 1, "Fakt", f"seit {f.get('datum') or '?'}")
        kanten.add((nikola, fid))

    # Notizen im Vault: Datei-Knoten am Ordner-Hub, [[Wikilinks]] als Kanten, Texte fuer die Themen
    texte: list[tuple[str, str]] = [(f"fakt-{f['id']}", f["text"]) for f in fakten]
    for datei in sorted(vault.rglob("*.md")) if vault.exists() else []:
        if datei == gehirn.FAKTEN_PATH or ".obsidian" in datei.parts:
            continue
        rel = datei.relative_to(vault)
        ordner = rel.parts[0] if len(rel.parts) > 1 else ""
        gruppe = ordner_gruppe.get(ordner, 6)
        hub = _knoten(knoten, f"hub-{ordner or 'notizen'}", ordner.replace("Gespraeche", "Gespräche") or "Notizen", gruppe, "Ordner")
        kanten.add((nikola, hub))
        try:
            text = datei.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Tagesnotizen heissen nur nach dem Datum -> Ordner davor ("Briefing 05.10."), sonst doppelte Namen
        name = datei.stem
        if m := re.fullmatch(r"(\d{4})-(\d\d)-(\d\d)", name):
            name = f"{ {2: 'Gespräch', 3: 'Briefing', 4: 'Projekt'}.get(gruppe, 'Notiz')} {m.group(3)}.{m.group(2)}."
        did = _knoten(knoten, f"datei-{rel.as_posix()}", name, gruppe, "Notiz", f"{rel.as_posix()} · {len(text.splitlines())} Zeilen")
        kanten.add((hub, did))
        for link in re.findall(r"\[\[([^\]|#]+)", text):
            ziel = "nikola" if link.strip().lower() == "nikola" else f"datei-{link.strip()}"
            if ziel in knoten:
                kanten.add((did, ziel))
        # Abschnitte (## ...) als eigene kleine Knoten, z. B. einzelne Briefings
        for titel in re.findall(r"^## (.+)$", text, re.M)[:30]:
            aid = _knoten(knoten, f"abschnitt-{rel.as_posix()}-{titel}", titel.strip(), gruppe, "Abschnitt")
            kanten.add((did, aid))
        # Gesprochenes ohne Markdown-Kopf fuer die Themen
        inhalt = re.sub(r"^---.*?---", "", text, flags=re.S)
        inhalt = re.sub(r"\*\*\d\d:\d\d (Du|Klaus):\*\*", " ", inhalt)
        texte.append((did, inhalt))

    # Themen: Woerter, die in mindestens zwei Texten vorkommen, verbinden Notizen und Fakten
    vorkommen: dict[str, set[str]] = collections.defaultdict(set)
    anzeige: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for kid, text in texte:
        for wort in re.findall(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-]{4,}", text):
            klein = wort.lower()
            if klein in STOPP or klein.endswith("-"):
                continue
            vorkommen[klein].add(kid)
            anzeige[klein][wort] += 1
    # nur Substantive/Namen (meist grossgeschrieben) - "bessere", "passiert" usw. fallen raus
    gross = lambda w: sum(n for f, n in anzeige[w].items() if f[0].isupper()) > sum(anzeige[w].values()) * 0.6
    themen = sorted((w for w, k in vorkommen.items() if len(k) >= 2 and gross(w)), key=lambda w: -len(vorkommen[w]))[:90]
    for wort in themen:
        tid = _knoten(knoten, f"thema-{wort}", anzeige[wort].most_common(1)[0][0], 5, "Thema",
                      f"kommt in {len(vorkommen[wort])} Notizen/Fakten vor")
        for kid in vorkommen[wort]:
            kanten.add((tid, kid))

    return {"knoten": list(knoten.values())[:MAX_KNOTEN], "kanten": [list(k) for k in kanten], "gruppen": gruppen,
            "quelle": str(vault)}


def finde_projekt(name: str) -> dict | None:
    """Projekt aus VS-Code-Verlauf und Klaus-Projekten; leerer Name = zuletzt geoeffnetes."""
    liste = daten.projekte()
    alle = liste["vscode"] + liste["klaus"]
    if not alle:
        return None
    if not name.strip():
        return alle[0]
    such = re.sub(r"[^a-z0-9äöüß]", "", name.lower())
    for p in alle:
        if such and such in re.sub(r"[^a-z0-9äöüß]", "", p["name"].lower()):
            return p
    # Pfad direkt angegeben?
    pfad = Path(name)
    if pfad.is_dir():
        return {"name": pfad.name, "pfad": str(pfad)}
    return None


def projekt(name: str = "") -> dict:
    p = finde_projekt(name)
    if not p:
        raise RuntimeError(f"Ich finde kein Projekt namens „{name}“.")
    wurzel = Path(p["pfad"])
    graphify = shutil.which("graphify") or str(Path.home() / ".local" / "bin" / "graphify.exe")
    if not Path(graphify).exists() and not shutil.which("graphify"):
        raise RuntimeError("graphify ist nicht installiert.")
    # Rein strukturell (AST), ohne KI und ohne Kosten; legt <projekt>/graphify-out/ an
    lauf = subprocess.run([graphify, "update", str(wurzel)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=600, cwd=str(wurzel), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    datei = wurzel / "graphify-out" / "graph.json"
    if not datei.exists():
        raise RuntimeError(f"graphify hat keinen Graphen erzeugt: {(lauf.stderr or lauf.stdout)[-200:]}")
    g = json.loads(datei.read_text(encoding="utf-8"))
    roh = g.get("nodes", [])
    grad = collections.Counter()
    for l in g.get("links", []):
        grad[l["source"]] += 1
        grad[l["target"]] += 1
    if len(roh) > MAX_KNOTEN:  # zu gross: die am besten vernetzten behalten
        roh = sorted(roh, key=lambda n: -grad[n["id"]])[:MAX_KNOTEN]
    ids = {n["id"] for n in roh}
    knoten = [{"id": n["id"], "label": n.get("label", n["id"]), "gruppe": n.get("community", 0) or 0,
               "typ": n.get("file_type", "code"), "info": f"{n.get('source_file', '')} {n.get('source_location', '')}".strip()}
              for n in roh]
    kanten = [[l["source"], l["target"]] for l in g.get("links", []) if l["source"] in ids and l["target"] in ids]
    gruppen = {}
    for n in roh:  # Gruppenname = Datei des am besten vernetzten Knotens der Gruppe
        c = n.get("community", 0) or 0
        if c not in gruppen or grad[n["id"]] > grad[gruppen[c][1]]:
            gruppen[c] = (n.get("source_file") or n.get("label", ""), n["id"])
    return {"knoten": knoten, "kanten": kanten, "gruppen": {c: v[0] for c, v in gruppen.items()},
            "quelle": str(wurzel), "name": p["name"]}


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "projekt":
        d = projekt(sys.argv[2] if len(sys.argv) > 2 else "")
    else:
        d = gedaechtnis()
    print(len(d["knoten"]), "Knoten,", len(d["kanten"]), "Kanten,", len(d["gruppen"]), "Gruppen")
    print([k["label"] for k in d["knoten"]][:25])
