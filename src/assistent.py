"""
Klaus - Assistent (Logik ohne Oberflaeche)
Hoert auf "Klaus", versteht Befehle, fuehrt Gespraeche, plant Projekte und
uebergibt sie an Claude. Die Oberflaeche haengt sich ueber die Signale in
`Bruecke` an; getippte Eingaben und Knopfdruecke kommen ueber `eingabe()`.
"""

import datetime as dt
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import traceback

from PySide6.QtCore import QObject, Signal

import apps
import gehirn
import gemini_live
import llm
import voice

# "Klaus, ..." am Anfang oder "..., Klaus" am Ende. Whisper schreibt den Namen manchmal anders.
NAME = r"(?:klaus|claus|klaas|kraus|klause)"
WECKWORT_VORNE = re.compile(rf"^\W*(?:(?:hey|hallo|hi|ok|okay|he|du)\W+)?{NAME}\b\W*(?P<rest>.*)$", re.I | re.S)
WECKWORT_HINTEN = re.compile(rf"^(?P<rest>.*?)\W+{NAME}\W*$", re.I | re.S)

# Whisper hoert oft "oeffnet"/"oeffnen" oder "kannst du Steam aufmachen" -> alles abdecken
VERB = r"(?:öffne|öffnet|öffnen|oeffne|oeffnet|oeffnen|starte|startet|starten|zeig|zeige)"
OEFFNE = [
    re.compile(rf"\b{VERB}\s+(?:(?:wir|mir|mal|bitte|doch|du|uns)\s+)*(?P<ziel>.+?)[\s.!?]*$", re.I),
    re.compile(r"\bmach\w*\s+(?:(?:mir|mal|bitte|doch)\s+)*(?P<ziel>.+?)\s+auf\b", re.I),
    re.compile(rf"(?:kannst du|könntest du|bitte)?\s*(?:(?:mir|mal)\s+)*(?P<ziel>.+?)\s+(?:aufmachen|{VERB})[\s.!?]*$", re.I),
]
SUCHE = re.compile(r"^(?:kannst du\s+)?(?:such|suche|google|googel)\s+(?:mal\s+)?(?:nach\s+)?(?P<was>.+?)[.!?]*$", re.I)
PLANEN = re.compile(r"\b(website|webseite|homepage|landing ?page|onlineshop|planen|bauen|programmier\w*)\b", re.I)
STILL = re.compile(r"^\W*(danke|nichts|schon gut|stopp?|vergiss es|egal|tsch(ü|ue)ss|bis sp(ä|ae)ter)\b", re.I)
DESIGN = re.compile(r"\b(farb\w*|design\w*|thema|theme|look|stil|modus|palette)\b", re.I)
# Gesprochene Woerter -> Design-Variante (Namen wie in fenster.THEMEN)
DESIGN_WOERTER = [
    (r"jarvis|cyan|t(ü|ue)rkis|blau|standard|normal", "jarvis", "Jarvis"),
    (r"iron ?man|rot", "ironman", "Iron Man"),
    (r"matrix|gr(ü|ue)n|hacker", "matrix", "Matrix"),
    (r"synth\w*|lila|violett|pink|neon", "synthwave", "Synthwave"),
    (r"gold\w*|gelb|orange|bernstein", "gold", "Gold"),
    (r"ar(k|c)tis|wei(ß|ss)|eis|hell|silber", "arktis", "Arktis"),
    (r"n(ä|ae)chst\w*|ander\w*|neu\w*|wechsel\w*|(ä|ae)nder\w*", "weiter", ""),
]
# Widgets im Desktop-Panel per Sprache steuern (Typen wie in web/dashboard.html TYPEN)
WIDGET_WOERTER = [
    (r"uhr|zeit", "uhr", "Uhr"),
    (r"schnellstart|kacheln", "schnellstart", "Schnellstart"),
    (r"projekte?|projekt-widget", "projekte", "Projekte"),
    (r"wetter", "wetter", "Wetter"),
    (r"b(ö|oe)rse|aktien|kurse", "boerse", "Börse"),
    (r"nachrichten|news", "nachrichten", "Nachrichten"),
    (r"system|auslastung", "system", "System-Widget"),
    (r"notiz\w*", "notizen", "Notizen"),
    (r"lesezeichen", "lesezeichen", "Lesezeichen"),
    (r"web-?widget|browser-?widget", "web", "Web-Widget"),
    (r"klesro|leads", "klesro", "Klesro-Widget"),
    (r"ged(ä|ae)chtnis", "gedaechtnis", "Gedächtnis"),
]
WIDGET_AKTIONEN = [  # Reihenfolge zaehlt: "klapp ... ein" vor "oeffne"
    (r"einklapp\w*|klapp\w*\b.*\bein|zuklapp\w*|minimier\w*", "einklappen", "{} eingeklappt."),
    (r"ausklapp\w*|aufklapp\w*|klapp\w*\b.*\bauf|maximier\w*", "ausklappen", "{} ausgeklappt."),
    (r"schlie(ß|ss)\w*|entfern\w*|weg|l(ö|oe)sch\w*|ausblend\w*", "entfernen", "{} geschlossen."),
    (r"gr(ö|oe)(ß|ss)er|vergr(ö|oe)(ß|ss)er\w*", "groesser", "{} vergrößert."),
    (r"kleiner|verkleiner\w*", "kleiner", "{} verkleinert."),
    (r"verschieb\w*|schieb\w*|beweg\w*|pack\w*|setz\w*", "verschieben", "{} verschoben."),
    (r"hinzu\w*|f(ü|ue)g\w*|(ö|oe)ffne\w*|zeig\w*|hol\w*|brauch\w*", "hinzufuegen", "{} eingeblendet."),
]
RICHTUNGEN = [(r"links", "links"), (r"rechts", "rechts"), (r"oben", "oben"), (r"unten", "unten"), (r"mitte", "mitte")]
IM_PANEL = re.compile(r"\b(im|ins|auf (dem|den|meinem|meinen))\s+(panel|widget|desktop|hintergrund)\b", re.I)
PANEL_STANDARD = re.compile(
    r"\b(panel|desktop|layout|widgets?)\b.*\b(zur(ü|ue)ck\w*|standard|aufr(ä|ae)um\w*)\b"
    r"|\br(ä|ae)um\w*\b.*\b(panel|desktop|layout|widgets?)\b.*\bauf\b", re.I)
PLAN_ENDE = re.compile(r"\b(abbrechen|stopp|beenden|tsch(ü|ue)ss|das wars|das war's|fertig f(ü|ue)r heute)\b", re.I)

# Stummschaltung: z. B. waehrend eines Kundengespraechs
STUMM = re.compile(r"\b(sei (mal |bitte |jetzt )?(still|ruhig|leise)|stumm|ruhe|halt die klappe|klappe halten|"
                   r"h(ö|oe)r (mal )?(auf|weg)|nicht (mehr )?zuh(ö|oe)ren)\b", re.I)
WIEDER_AN = re.compile(r"\b(wieder (an|da|zuh(ö|oe)ren|reden|aktiv)|aufwachen|wach (wieder )?auf|"
                       r"du (kannst|darfst) wieder|stumm aus|nicht mehr stumm)\b", re.I)

VERPASST = re.compile(r"was (hab|habe) ich verpasst|was ist (so |denn )?passiert|lagebericht|(morgen-?)?briefing|"
                      r"update f(ü|ue)r mich|was gibt'?s neues", re.I)

# Gedaechtnis per Sprache
MERKEN = re.compile(r"^\W*(?:bitte\s+)?(?:merk|merke|notier|speicher)\w*\s+(?:dir\b)?\s*(?:bitte\s+)?[,:]?\s*(?:dass\s+)?(?P<was>.+)$", re.I)
VERGISS = re.compile(r"^\W*(?:bitte\s+)?vergiss\s+(?:bitte\s+)?[,:]?\s*(?:dass\s+|das mit\s+|alles (?:über|zu)\s+)?(?P<was>(?!es\W*$).+)$", re.I)
# "zeig dein Gedaechtnis als Graph", "zeig Projekt Klaus als Netz", "Graph von meinem Projekt …"
GRAPH = re.compile(r"\b(graph\w*|netz\w*|wissensnetz)\b", re.I)
GRAPH_PROJEKT = re.compile(r"projekt\w*\s+(?:von\s+)?(?P<name>.+?)(?:\s+als\s+.*)?$", re.I)
WISSEN = re.compile(r"was (wei(ß|ss)t|hast) du (alles |eigentlich |so )?((ü|ue)ber mich|von mir)|was hast du dir (alles )?gemerkt", re.I)
NACHFRAGE_SEK = 8  # so lange hoert Klaus nach einer Antwort ohne Weckwort weiter
VERLAUF_VERGESSEN_SEK = 180


class Bruecke(QObject):
    """Signale vom Assistenten-Thread zur Oberflaeche."""

    zustand = Signal(str)  # aus/start/hoeren/denken/sprechen/aktion/fehler
    text = Signal(str)  # Untertitel unter dem Orb
    pegel = Signal(float)  # Lautstaerke 0..1
    meldung = Signal(str)  # Windows-Benachrichtigung
    thema = Signal(str)  # Design-Variante wechseln ("weiter" = naechste)
    panel = Signal(str)  # Widget-Befehl als JSON, z. B. {"aktion": "entfernen", "typ": "nachrichten"}
    gedaechtnis = Signal()  # Gedaechtnis hat sich geaendert -> Widget neu laden
    stumm = Signal(bool)  # Stummschaltung an/aus (Knopf, Orb, Taskleiste)
    mikro_aus = Signal(bool)  # Mikrofon komplett aus/an
    nachricht = Signal(str, str)  # (rolle, text) fuers Chat-Fenster: du/klaus/info/auftrag
    holo = Signal(str)  # Pop-up-Fenster rund ums Auge als JSON: {aktion, id, art, titel, daten} (web/popups.js)


class Pipeline:
    """Phasen-Checkliste im Panel (Pop-up "pipeline"): pending -> running -> complete / warten / fehler."""

    def __init__(self, assistent: "Assistent", titel: str, schritte: list[str]) -> None:
        self.a = assistent
        self.titel = titel
        self.schritte = [{"name": n, "status": "pending", "info": ""} for n in schritte]
        self._senden("oeffne")

    def _senden(self, aktion: str = "update") -> None:
        self.a.holo(aktion, "pipeline", art="pipeline", titel=self.titel, daten={"schritte": self.schritte})

    def setze(self, i: int, status: str, info: str | None = None) -> None:
        self.schritte[i]["status"] = status
        if info is not None:
            self.schritte[i]["info"] = info
        self._senden()

    def fehler(self, info: str) -> None:
        for s in self.schritte:
            if s["status"] == "running":
                s.update(status="fehler", info=info)
        self._senden()


class Assistent:
    def __init__(self, bruecke: Bruecke, dry_run: bool) -> None:
        self.b = bruecke
        self.dry_run = dry_run
        self.laeuft = True
        self.pausiert = False
        self.ohr: voice.Ohr | None = None
        self.sprech_sperre = threading.Lock()
        self.eingaben: queue.Queue[str] = queue.Queue()  # getippt / Knoepfe
        self.verlauf: list[dict] = []
        self.letzte_aktivitaet = 0.0
        self.claude = gehirn.ClaudeGehirn()
        self.letztes_briefing = ""  # "Seit du weg warst" zum Vorlesen (setzt klaus_app.Anwesenheit)
        self.zuletzt_aktiv = time.time()  # Gespraeche zaehlen als Anwesenheit, auch ohne Maus/Tastatur
        self.ist_stumm = False  # stumm: reagiert nur noch auf "Klaus, wieder an" (lokal erkannt, nichts geht raus)
        # Mit Gemini-Schluessel fuehrt Gemini Live das Gespraech; sonst die lokale Kette (Whisper -> Modell -> Stimme)
        self.gemini = gemini_live.GeminiGespraech(self) if gemini_live.bereit() else None

    # ---------------------------------------------------------------- von aussen
    def eingabe(self, text: str) -> None:
        """Getippter Befehl oder Knopf aus Panel/Chat - braucht kein Weckwort."""
        if text.strip():
            self.eingaben.put(text.strip())

    def setze_stumm(self, an: bool) -> None:
        """Stumm schalten (Stimme, Strg+Alt+K, Knopf im Panel, Taskleiste)."""
        if an == self.ist_stumm:
            return
        self.ist_stumm = an
        if an and self.gemini:
            self.gemini.ende = True  # laufendes Gespraech sofort beenden
        print(f"[Klaus] Stumm: {'an' if an else 'aus'}")
        self.b.stumm.emit(an)

    def briefe_starten(self, anzahl: int = 0) -> str:
        """Brief-Generator im Hintergrund; meldet sich, wenn die PDFs fertig sind."""
        import daten

        import briefe
        import hochladen

        leads = daten.BASE_DIR / "data" / "leads.csv"
        if daten.leads()["leads"] == 0:
            return "In der Lead-Liste sind noch keine Firmen. Erst muss die Lead-Suche wieder laufen."
        fehlt = [n for n, w in [("deine Adresse", briefe.ABSENDER["adresse"]), ("deine Telefonnummer", briefe.ABSENDER["telefon"])] if not w]
        if fehlt:
            return f"Vorher fehlt noch {' und '.join(fehlt)} in der .env (KLESRO_ADRESSE, KLESRO_TELEFON), sonst sind die Briefe unvollständig."

        pipe = Pipeline(self, "BRIEF-PIPELINE", ["Leads laden", "Briefe + Entwürfe erstellen", "Entwürfe hochladen", "Drucken"])

        def los() -> None:
            pipe.setze(0, "complete", f"{daten.leads()['leads']} Firmen")
            pipe.setze(1, "running")
            befehl = [sys.executable, str(daten.BASE_DIR / "src" / "briefe.py"), "--leads", str(leads), "--ki", "gemini"]
            if anzahl:
                befehl += ["--nur", str(anzahl)]
            start = time.time()
            prozess = subprocess.Popen(befehl, cwd=daten.BASE_DIR, creationflags=subprocess.CREATE_NO_WINDOW)
            gezeigt: set = set()
            while prozess.poll() is None:  # neue Briefe live im Entwurf-Fenster zeigen
                time.sleep(2)
                gezeigt |= self._neue_briefe(daten.BASE_DIR / "data" / "briefe", start, gezeigt, pipe)
            self._neue_briefe(daten.BASE_DIR / "data" / "briefe", start, gezeigt, pipe)
            pipe.setze(1, "complete" if gezeigt else "fehler", f"{len(gezeigt)} Briefe")
            # Entwuerfe gleich online stellen, damit die QR-Codes funktionieren
            if hochladen.eingerichtet():
                pipe.setze(2, "running")
                online = hochladen.entwuerfe()
                pipe.setze(2, "complete")
            else:
                online = "Die Entwürfe sind noch nicht online (Webspace-Zugang fehlt in der .env)."
                pipe.setze(2, "uebersprungen", "Webspace-Zugang fehlt")
            pipe.setze(3, "warten", "sag: Klaus, druck die Briefe")
            self.log(f"briefe/fertig {len(gezeigt)} · {online}")
            print(f"[Klaus] Briefe: {online}")
            self.b.meldung.emit("Briefe fertig – " + online)
            os.startfile(daten.BASE_DIR / "data" / "briefe")
            self.sage(f"Die Briefe sind fertig. {online} Schau sie dir an und sag dann: Klaus, druck die Briefe.", zustand="aktion")
            self.verschwinde(nach=1.0)

        threading.Thread(target=los, daemon=True).start()
        return "Ich erstelle die Briefe im Hintergrund und öffne den Ordner, wenn sie fertig sind."

    def _neue_briefe(self, ordner, seit: float, gezeigt: set, pipe: "Pipeline") -> set:
        """Briefe, die seit `seit` fertig geworden sind: Text ins Entwurf-Fenster, Zaehler in die Pipeline."""
        neu = set()
        for datei in sorted(ordner.glob("*/brief.html"), key=lambda p: p.stat().st_mtime):
            if datei.parent.name in gezeigt or datei.stat().st_mtime < seit:
                continue
            neu.add(datei.parent.name)
            html = datei.read_text(encoding="utf-8", errors="replace")
            betreff = re.search(r'class="betreff">(.*?)</div>', html, re.S)
            koerper = re.search(r'class="betreff">.*?</div>(.*?)<div class="gruss">', html, re.S)
            text = re.sub(r"</p>\s*", "\n\n", koerper.group(1)) if koerper else ""
            text = re.sub(r"<[^>]+>", "", text).strip()
            self.holo("oeffne", "entwurf", art="entwurf", titel=f"BRIEF · {datei.parent.name.upper()[:28]}",
                      daten={"betreff": re.sub(r"<[^>]+>", "", betreff.group(1)).strip() if betreff else "", "text": text})
            self.log(f"briefe/pdf {datei.parent.name}")
        if neu:
            pipe.setze(1, "running", f"{len(gezeigt) + len(neu)} fertig")
        return neu

    # ---------------------------------------------------------------- Holo-Fenster im Panel
    def holo(self, aktion: str, fid: str, **felder) -> None:
        """Pop-up rund ums Auge: aktion oeffne/update/zu, art log/pipeline/karte/entwurf (siehe web/popups.js)."""
        self.b.holo.emit(json.dumps({"aktion": aktion, "id": fid, **felder}, ensure_ascii=False, default=str))

    def log(self, text: str) -> None:
        """Zeile im Live-Log-Fenster (klesro://...)."""
        self.b.holo.emit(json.dumps({"aktion": "log", "text": text}, ensure_ascii=False))

    def graph_zeigen(self, was: str = "gedaechtnis", projekt: str = "") -> str:
        """Wissensnetz im Panel (web/graph.js): Gedaechtnis-Vault oder Code-Projekt (graphify, ohne KI/Kosten)."""
        import graphen

        was = "projekt" if was.startswith("proj") or was == "code" else "gedaechtnis"

        def los() -> None:
            try:
                if was == "gedaechtnis":
                    self.log("graph/gedaechtnis vault lesen")
                    d = graphen.gedaechtnis()
                    titel = "GEDÄCHTNIS · WISSENSNETZ"
                else:
                    self.log(f"graph/projekt graphify update {projekt or '(zuletzt geoeffnet)'}")
                    d = graphen.projekt(projekt)
                    titel = f"CODE-GRAPH · {d.get('name', '').upper()[:30]}"
                self.holo("oeffne", f"graph-{was}", art="graph", titel=titel, daten=d)
                self.log(f"graph/fertig {len(d['knoten'])} knoten · {len(d['kanten'])} kanten · {len(d['gruppen'])} gruppen")
            except Exception as e:
                print(f"[Klaus] Graph: {e}")
                self.log(f"graph/fehler {str(e)[:80]}")
                self.sage(f"Den Graphen konnte ich nicht bauen: {str(e)[:120]}")

        threading.Thread(target=los, daemon=True).start()
        if was == "gedaechtnis":
            return "Hier ist mein Gedächtnis als Netz."
        return f"Ich baue den Code-Graphen{' für ' + projekt if projekt else ' für dein letztes Projekt'}, einen Moment."

    def leads_suchen(self, branchen: str, ort: str = "Göppingen", radius_km: float = 12) -> str:
        """OSM-Lead-Suche im Hintergrund - mit Lead-Karte und Pipeline im Panel. Meldet sich, wenn sie fertig ist."""
        import osm_leads

        liste = [x.strip() for x in re.split(r",|;|\bund\b", branchen) if x.strip()]
        if not liste:
            return "Welche Branchen soll ich suchen, zum Beispiel Schreiner, Maler oder Friseure?"
        ort = ort or "Göppingen"
        pipe = Pipeline(self, f"LEAD-PIPELINE · {ort.upper()}", ["Betriebe finden (OpenStreetMap)", "Websites prüfen",
                                                                  "In Lead-Liste speichern", "Briefe erstellen"])

        def los() -> None:
            try:
                pipe.setze(0, "running", ", ".join(liste))
                self.log(f"osm/suche {', '.join(liste)} · {ort} · {radius_km:g} km")
                lat, lon, ortname = osm_leads.koordinaten(ort)
                gefunden = osm_leads.suche(liste, ort, radius_km)
                self.holo("oeffne", "karte", art="karte", titel=f"LEAD MAP · {ortname.upper()}", daten={
                    "mitte": [lat, lon], "radius_km": radius_km,
                    "leads": [{"name": l["name"], "lat": l.get("lat"), "lon": l.get("lon"), "adresse": l["adresse"]} for l in gefunden]})
                pipe.setze(0, "complete", f"{len(gefunden)} ohne Website-Eintrag")
                pipe.setze(1, "running")

                def geprueft(lead: dict, website: str | None, sicher: bool) -> None:
                    status = "website" if website else ("ohne" if sicher else "neu")
                    self.holo("update", "karte", daten={"status": {lead["name"]: status}})
                    self.log(f"web/check {lead['name']} -> {website or ('keine website' if sicher else 'unklar')}")

                ohne = osm_leads.websites_pruefen(gefunden, fortschritt=geprueft)
                pipe.setze(1, "complete", f"{len(gefunden) - len(ohne)} verworfen")
                pipe.setze(2, "running")
                neu = osm_leads.speichern(ohne)
                pipe.setze(2, "complete", f"{neu} neu")
                pipe.setze(3, "warten", "sag: Klaus, erstell die Briefe")
                namen = ", ".join(l["name"] for l in ohne[:3])
                self.sage(f"Fertig: {len(ohne)} Betriebe ohne Website, {neu} davon neu in der Lead-Liste."
                          + (f" Zum Beispiel {namen}." if namen else ""), zustand="aktion")
            except Exception as e:
                print(f"[Klaus] Lead-Suche: {e}")
                pipe.fehler(str(e)[:80])
                self.sage(f"Die Lead-Suche hat nicht geklappt: {str(e)[:120]}")
            self.verschwinde(nach=1.0)

        threading.Thread(target=los, daemon=True).start()
        return f"Ich suche {', '.join(liste)} rund um {ort}. Das dauert ein paar Minuten, die Karte siehst du im Panel."

    def setze_mikro_aus(self, aus: bool) -> None:
        """Mikrofon komplett aus: Klaus hoert gar nichts (auch kein "Klaus"). Nur Taste/Knopf schaltet es wieder an."""
        if aus == self.pausiert:
            return
        self.pausiert = aus  # Hauptschleife oeffnet das Mikro dann nicht mehr
        if aus and self.gemini:
            self.gemini.ende = True
        print(f"[Klaus] Mikrofon: {'AUS' if aus else 'an'}")
        self.b.mikro_aus.emit(aus)

    # ---------------------------------------------------------------- Bausteine
    def zeige(self, zustand: str, text: str | None = None) -> None:
        if text is not None:
            self.b.text.emit(text)
        self.b.zustand.emit(zustand)

    def sage(self, text: str, zustand: str = "sprechen") -> None:
        self.b.nachricht.emit("klaus", text)
        self.zeige(zustand, text)
        with self.sprech_sperre:
            voice.sprich(text, False, on_pegel=self.b.pegel.emit)
        self.b.pegel.emit(0.0)

    def hoere(self, timeout: float) -> str:
        """Wartet auf Sprache (ohne Weckwort) oder eine getippte Eingabe."""
        self.zeige("hoeren")
        if not self.eingaben.empty():
            text = self.eingaben.get()
        else:
            text = self.ohr._hoere_frei(
                timeout=timeout,
                abbruch=lambda: not self.laeuft or not self.eingaben.empty(),
                on_pegel=self.b.pegel.emit,
            )
            if not text and not self.eingaben.empty():
                text = self.eingaben.get()
        self.b.pegel.emit(0.0)
        if text:
            self.b.nachricht.emit("du", text)
            self.zeige("denken", f"„{text}“")
        return text

    def verschwinde(self, nach: float = 0.0) -> None:
        time.sleep(nach)
        self.b.text.emit("")
        self.b.zustand.emit("aus")

    @staticmethod
    def weckwort(text: str) -> str | None:
        """Gibt den Befehl nach/vor dem Namen zurueck ("" = nur Name), sonst None."""
        for muster in (WECKWORT_VORNE, WECKWORT_HINTEN):
            m = muster.match(text.strip())
            if m:
                return m.group("rest").strip(" ,.!?")
        return None

    @staticmethod
    def oeffnen_ziel(befehl: str):
        """Findet "oeffne X" in allen Varianten -> (Name, starten) oder None."""
        for muster in OEFFNE:
            m = muster.search(befehl)
            if m:
                treffer = apps.finde(m.group("ziel"))
                if treffer:
                    return treffer
        return None

    # ---------------------------------------------------------------- Ablauf
    def run(self) -> None:
        try:
            self.zeige("start", "Klaus startet ...")
            if not llm.ist_verfuegbar():
                self.zeige("start", "Starte Ollama ...")
                subprocess.Popen(["ollama", "serve"], creationflags=subprocess.CREATE_NO_WINDOW)
                for _ in range(30):
                    time.sleep(1)
                    if llm.ist_verfuegbar():
                        break
            self.zeige("start", "Lade Spracherkennung ...")
            self.ohr = voice.Ohr(freihand=True)
            self.zeige("aktion", "Bereit – sag „Klaus“")
            self.b.nachricht.emit("info", "Klaus ist bereit. Sag „Klaus“ oder tippe hier.")
            self.verschwinde(nach=2.0)
        except Exception:
            traceback.print_exc()
            self.zeige("fehler", "Klaus konnte nicht starten – siehe data/klaus.log")
            return

        while self.laeuft:
            if self.pausiert and self.eingaben.empty():
                time.sleep(0.3)
                continue
            try:
                befehl = self.warte_auf_befehl()
                if befehl is None:
                    continue
                self.zuletzt_aktiv = time.time()
                if STUMM.search(befehl):  # "Klaus, sei still" - sofort, ohne Gemini zu fragen
                    self.setze_stumm(True)
                    self.zeige("aktion", "Stumm")
                    self.verschwinde(nach=1.0)
                    continue
                if self.gemini:
                    try:
                        self.zeige("hoeren", "")
                        self.gemini.fuehre(befehl)
                        self.zuletzt_aktiv = time.time()
                        self.verschwinde()
                        continue
                    except Exception:  # kein Netz, Schluessel ungueltig, Limit ... -> lokal weiter
                        traceback.print_exc()
                        self.b.nachricht.emit("info", "Gemini nicht erreichbar – ich antworte lokal.")
                        if not befehl:
                            self.verschwinde()
                            continue
                self.gespraech(befehl)
            except Exception:
                traceback.print_exc()
                self.zeige("fehler", "Da ist etwas schiefgelaufen.")
                self.verschwinde(nach=2.5)

    def warte_auf_befehl(self) -> str | None:
        """Ruhezustand: hoert im Hintergrund, reagiert nur auf "Klaus" oder Getipptes."""
        if not self.eingaben.empty():
            text = self.eingaben.get()
            self.b.nachricht.emit("du", text)
            self.zeige("denken", f"„{text}“")
            return text
        gehoert = self.ohr._hoere_frei(
            abbruch=lambda: self.pausiert or not self.laeuft or not self.eingaben.empty()
        )
        if not gehoert:
            return None
        befehl = self.weckwort(gehoert)
        if befehl is None:
            return None  # nicht mit Klaus gesprochen
        if self.ist_stumm:
            if WIEDER_AN.search(befehl) or not befehl:
                self.setze_stumm(False)
                self.sage("Ich bin wieder da.", zustand="aktion")
                self.verschwinde(nach=0.5)
            return None
        print(f"[{dt.datetime.now():%H:%M:%S}] Befehl: {befehl!r}")
        if not befehl:
            if self.gemini:
                return ""  # nur "Klaus" gesagt: Gemini meldet sich selbst mit "Ja?"
            self.zeige("hoeren", "")
            self.sage("Ja?")
            befehl = self.hoere(timeout=7)
            if not befehl:
                self.verschwinde()
                return None
            return befehl
        self.b.nachricht.emit("du", befehl)
        self.zeige("denken", f"„{befehl}“")
        return befehl

    def gespraech(self, befehl: str) -> None:
        """Bearbeitet den Befehl und hoert danach weiter zu, bis eine Pause kommt."""
        while befehl and self.laeuft:
            if STILL.match(befehl):
                self.sage("Alles klar.")
                break
            self.bearbeite(befehl)
            self.zeige("hoeren", "Ich höre weiter zu …")
            befehl = self.hoere(timeout=NACHFRAGE_SEK)
        self.verschwinde()

    @staticmethod
    def design_wunsch(befehl: str) -> tuple[str, str] | None:
        """"mach das Design rot" -> ("ironman", "Iron Man"); "anderes Design" -> ("weiter", "")."""
        if not DESIGN.search(befehl):
            return None
        for muster, name, anzeige in DESIGN_WOERTER:
            if re.search(rf"\b({muster})\b", befehl, re.I):
                return name, anzeige
        return None

    @staticmethod
    def panel_wunsch(befehl: str) -> tuple[dict, str] | None:
        """Widget-Befehle -> (Aktion fuers Panel, gesprochene Bestaetigung) oder None."""
        if PANEL_STANDARD.search(befehl):
            return {"aktion": "standard"}, "Das Panel ist zurückgesetzt."

        # "zeig YouTube im Panel" -> Website im Web-Widget
        if IM_PANEL.search(befehl):
            rest = IM_PANEL.sub(" ", befehl)
            rest = re.sub(r"\b(zeig\w*|(ö|oe)ffne\w*|lade\w*|mach\w*|bitte|mir|mal|die|das|den|auf)\b", " ", rest, flags=re.I)
            ziel = apps._norm(rest)
            if ziel:
                url = apps.WEBSEITEN.get(ziel)
                if not url:
                    domain = re.sub(r"\s*punkt\s*", ".", ziel).replace(" ", "")
                    url = f"https://{domain}" if "." in domain else "https://www.google.com/search?q=" + ziel.replace(" ", "+")
                return {"aktion": "web", "url": url}, "Ist im Panel geöffnet."

        widget = next(((typ, name) for muster, typ, name in WIDGET_WOERTER
                       if re.search(rf"\b({muster})\b", befehl, re.I)), None)
        if not widget:
            return None
        aktion = next(((a, satz) for muster, a, satz in WIDGET_AKTIONEN if re.search(rf"\b({muster})\b", befehl, re.I)), None)
        if not aktion:
            return None
        typ, name = widget
        befehl_dict = {"aktion": aktion[0], "typ": typ}
        if aktion[0] == "verschieben":
            befehl_dict["richtung"] = next((r for muster, r in RICHTUNGEN if re.search(rf"\b{muster}\b", befehl, re.I)), "")
        return befehl_dict, aktion[1].format(name)

    def gedaechtnis_befehl(self, befehl: str) -> bool:
        """merken / vergessen / was weisst du ueber mich. True, wenn erledigt."""
        if WISSEN.search(befehl):
            eintraege = gehirn.lade_gedaechtnis()
            if not eintraege:
                self.sage("Ich habe mir noch nichts über dich gemerkt. Sag einfach: Klaus, merk dir …")
            else:
                saetze = " ".join(e["text"].rstrip(".") + "." for e in eintraege[-6:])
                mehr = f" Insgesamt sind es {len(eintraege)} Dinge, alle stehen im Gedächtnis-Widget." if len(eintraege) > 6 else ""
                self.sage(f"{saetze}{mehr}")
            return True

        m = VERGISS.match(befehl)
        if m:
            was = m.group("was")
            if re.fullmatch(r"\W*alles\W*", was, re.I):
                anzahl = len(gehirn.lade_gedaechtnis())
                for e in gehirn.lade_gedaechtnis():
                    gehirn.vergiss_id(e["id"])
            else:
                anzahl = gehirn.vergiss(was)
            self.b.gedaechtnis.emit()
            self.sage("Okay, vergessen." if anzahl else "Dazu hatte ich mir nichts gemerkt.", zustand="aktion" if anzahl else "sprechen")
            return True

        m = MERKEN.match(befehl)
        if m:
            fakt = self.als_fakt(m.group("was"))
            gehirn.merke(fakt)
            self.b.gedaechtnis.emit()
            self.b.nachricht.emit("info", f"Gemerkt: {fakt}")
            self.sage("Okay, hab ich mir gemerkt.", zustand="aktion")
            return True
        return False

    @staticmethod
    def als_fakt(text: str) -> str:
        """"ich trinke keinen Kaffee" -> "Nikola trinkt keinen Kaffee." (lokal, schnell; sonst Originaltext)"""
        name = voice.ABSENDER_NAME.split()[0]
        try:
            fakt = llm.frage(
                f"Formuliere als kurzen Fakt in der dritten Person über {name}, ohne Einleitung, ein Satz:\n{text}",
                system="Du formulierst Notizen um. Gib nur den einen Satz aus.", temperatur=0,
            ).strip().strip('"')
            return fakt if 3 < len(fakt) < 300 else text
        except Exception:
            return text

    def briefing_text(self) -> str:
        """Das letzte "Seit du weg warst" - oder, falls keins da ist, die letzten Stunden."""
        if self.letztes_briefing:
            return self.letztes_briefing
        import daten

        d = daten.verpasst({"zeit": time.time() - 4 * 3600, "kurse": {}})
        return daten.verpasst_text(d, einleitung="Aus den letzten Stunden:")

    def bearbeite(self, befehl: str) -> None:
        self.zuletzt_aktiv = time.time()
        if STUMM.search(befehl):
            self.sage("Okay, ich bin still. Sag Klaus, wieder an, wenn du mich brauchst.")
            self.setze_stumm(True)
            return
        if VERPASST.search(befehl):
            self.zeige("denken", "Ich schaue nach …")
            self.sage(self.briefing_text())
            self.letztes_briefing = ""  # einmal erzaehlt reicht; danach gibt's den aktuellen Stand
            return

        if GRAPH.search(befehl) and re.search(r"ged(ä|ae)chtnis|erinnerung|projekt|code", befehl, re.I):
            if re.search(r"ged(ä|ae)chtnis|erinnerung", befehl, re.I):
                self.sage(self.graph_zeigen("gedaechtnis"), zustand="aktion")
            else:
                m = GRAPH_PROJEKT.search(befehl)
                name = re.sub(r"\b(als|graph\w*|netz\w*|zeigen|anzeigen)\b", "", m.group("name"), flags=re.I).strip(" .,") if m else ""
                self.sage(self.graph_zeigen("projekt", name), zustand="aktion")
            return

        if self.gedaechtnis_befehl(befehl):
            return

        panel = self.panel_wunsch(befehl)
        if panel:
            aktion, antwort = panel
            self.b.panel.emit(json.dumps(aktion))
            self.zeige("aktion", antwort)
            self.sage(antwort, zustand="aktion")
            return

        design = self.design_wunsch(befehl)
        if design:
            name, anzeige = design
            self.b.thema.emit(name)
            self.zeige("aktion", f"Design: {anzeige or 'gewechselt'}")
            self.sage(f"Design {anzeige} ist aktiv." if anzeige else "Neues Design.", zustand="aktion")
            return

        treffer = self.oeffnen_ziel(befehl)
        if treffer:
            name, starten = treffer
            starten()
            self.zeige("aktion", f"Öffne {name}")
            self.sage(f"Öffne {name}.", zustand="aktion")
            return

        m = SUCHE.search(befehl)
        if m:
            apps.suche(m.group("was"))
            self.zeige("aktion", f"Suche: {m.group('was')}")
            self.sage("Hier sind die Ergebnisse.", zustand="aktion")
            return

        if PLANEN.search(befehl):
            self.planen(befehl)
            return

        self.frage(befehl)

    def frage(self, befehl: str) -> None:
        if time.time() - self.letzte_aktivitaet > VERLAUF_VERGESSEN_SEK:
            self.verlauf = []
        self.letzte_aktivitaet = time.time()
        self.verlauf.append({"role": "user", "content": befehl})

        antwort = ""
        mit_claude = gehirn.soll_claude(befehl)
        if mit_claude or gehirn.soll_recherchieren(befehl):
            self.zeige("denken", "Ich frage Claude …" if mit_claude else "Ich recherchiere …")
            try:
                antwort = self.claude.frage(befehl, claude=mit_claude)
            except Exception as e:  # kein Netz, Kontingent leer ... -> lokal weiter
                print(f"Recherche nicht moeglich ({e}) - antworte lokal.")
        if not antwort:
            jetzt = dt.datetime.now().strftime("%A, %d.%m.%Y, %H:%M Uhr")
            system = {"role": "system", "content": f"{gehirn.PERSONA}\n\nJetzt ist {jetzt}.{gehirn.gedaechtnis_text()}"}
            antwort = llm.chat([system] + self.verlauf[-12:], temperatur=0.5)
        self.verlauf.append({"role": "assistant", "content": antwort})
        self.sage(antwort)

    # ---------------------------------------------------------------- Planen
    def planen(self, erster_satz: str) -> None:
        """Gespraech ohne Weckwort, bis der Plan an Claude geht oder 30 s Ruhe ist."""
        planer = voice.Planer()
        self.b.nachricht.emit("info", "Planungsmodus – sag „an Claude geben“, wenn der Plan steht.")
        self.sage(planer.antworte(erster_satz))
        while self.laeuft:
            gesagt = self.hoere(timeout=30)
            if not gesagt:
                self.sage("Ich pausiere hier. Sag einfach Klaus, wenn es weitergeht.")
                return
            if PLAN_ENDE.search(gesagt):
                self.sage("Alles klar, Planung beendet.")
                return
            if voice.BEFEHL_UEBERGEBEN.search(gesagt):
                if self.uebergeben(planer):
                    return
                continue
            self.zeige("denken")
            self.sage(planer.antworte(gesagt))

    def uebergeben(self, planer: "voice.Planer") -> bool:
        self.zeige("denken", "Schreibe den Auftrag für Claude ...")
        auftrag = planer.auftrag()
        self.b.nachricht.emit("auftrag", auftrag)
        self.sage("Der Auftrag steht im Klaus-Fenster. Soll Claude loslegen?")
        if not voice.ist_ja(self.hoere(timeout=30)):
            self.sage("Gut, dann feilen wir weiter am Plan.")
            return False
        name = planer.projektname
        self.sage(f"Claude baut jetzt {name}. Ich sage Bescheid, wenn es fertig ist.", zustand="aktion")
        threading.Thread(target=self.bauen, args=(auftrag, name), daemon=True).start()
        return True

    def bauen(self, auftrag: str, name: str) -> None:
        self.b.meldung.emit(f"Claude baut: {name}")
        self.b.nachricht.emit("info", f"Claude baut „{name}“ …")
        try:
            ordner = voice.an_claude(auftrag, name, self.dry_run)
        except Exception:
            traceback.print_exc()
            self.sage(f"Beim Bauen von {name} gab es einen Fehler.", zustand="fehler")
            self.verschwinde(nach=2)
            return
        self.b.meldung.emit(f"Fertig: {name}")
        gehirn.notiere_projekt(name, auftrag, ordner)
        index = next(ordner.rglob("index.html"), None)
        os.startfile(index or ordner)
        self.sage(f"Claude ist fertig mit {name}. Ich habe es dir geöffnet.", zustand="aktion")
        self.verschwinde(nach=1.0)
