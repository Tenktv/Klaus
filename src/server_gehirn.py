"""
Klaus - Gehirn auf dem Server (ohne Fenster, Mikro und Lautsprecher). Laeuft als systemd-Dienst `klaus-gehirn`.

- Telegram-Bot rund um die Uhr (Gemini + Werkzeuge), auch wenn der PC aus ist.
- Werkzeuge, die nur Daten im Netz brauchen (Kalender, Recherche, Markt-Analyse), laufen hier.
- Alles andere (Apps, Dateien, Drucken, Gedaechtnis, Panel ...) bittet den PC ueber den Tunnel (fernlink.py);
  ist der PC nicht erreichbar, sagt Klaus das ehrlich und fuehrt nichts aus.
- Freigaben fuer PC-Aktionen kommen vom PC (Knopf in Telegram + PIN) und gehen auch dorthin zurueck.
"""
import hmac
import json
import os
import sys
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

# --- Attrappe fuer PySide6 (assistent.py nutzt nur QObject/Signal; hier gibt es kein Fenster) ---
_pyside, _qtcore = types.ModuleType("PySide6"), types.ModuleType("PySide6.QtCore")


class _QObject:
    def __init__(self, *a, **k):
        pass


class _Signal:
    def __init__(self, *a):
        pass

    def emit(self, *a):
        pass

    def connect(self, *a):
        pass


_qtcore.QObject, _qtcore.Signal = _QObject, lambda *a, **k: _Signal()
_pyside.QtCore = _qtcore
sys.modules["PySide6"], sys.modules["PySide6.QtCore"] = _pyside, _qtcore

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.chdir(BASE_DIR)

import requests
from dotenv import load_dotenv

load_dotenv(BASE_DIR / ".env")

import assistent as A
import freigabe
import telegram_bot as TB

TOKEN = os.getenv("KLAUS_LINK_TOKEN", "").strip()
RUECK_PORT, SERVER_PORT = 7701, 7702
LOKAL = {"kalender_lesen", "termin_eintragen", "zeit_frei", "recherche", "markt_analyse"}
GEDAECHTNIS = BASE_DIR / "data" / "gedaechtnis_cache.txt"


def pc_post(pfad: str, daten: dict, frist: float = 6):
    r = requests.post(f"http://127.0.0.1:{RUECK_PORT}{pfad}", json=daten, headers={"X-Token": TOKEN}, timeout=frist)
    r.raise_for_status()
    return r.json()


class LazyOhr:
    """Whisper erst laden, wenn die erste Sprachnachricht kommt (spart Arbeitsspeicher)."""
    _modell = None
    geraet = None
    schwelle = 0.0002

    @property
    def model(self):
        if self._modell is None:
            from faster_whisper import WhisperModel
            self._modell = WhisperModel(os.getenv("WHISPER_MODEL_SERVER", "small"), device="cpu", compute_type="int8")
        return self._modell


class ServerAssistent(A.Assistent):
    """Der Assistent ohne Fenster: Antworten gehen immer an Telegram."""

    erinnerungen_aus = False   # der Server erinnert aufs Handy

    def __init__(self) -> None:
        self.telegram = None
        super().__init__(A.Bruecke(), dry_run=False)
        self.ohr = LazyOhr()

    def sage(self, text: str, zustand: str = "sprechen", quelle: str = "antwort") -> None:
        if self.telegram:
            self.telegram.senden(text)

    def zeige(self, zustand, text=None) -> None:
        pass

    def verschwinde(self, nach: float = 0.0) -> None:
        pass

    def log(self, text: str) -> None:
        print(f"[log] {text}")

    def setze_mikro_aus(self, aus: bool) -> None:
        pc_werkzeug("mikrofon", {"an": not aus})


def pc_an(frist: float = 3) -> bool:
    """Ist der PC ueber den Tunnel erreichbar? (GET auf den PC-Link, antwortet {"pc": true})"""
    try:
        r = requests.get(f"http://127.0.0.1:{RUECK_PORT}/", headers={"X-Token": TOKEN}, timeout=frist)
        return r.ok and bool(r.json().get("pc"))
    except Exception:
        return False


def pc_werkzeug(name: str, args: dict) -> str:
    try:
        return pc_post("/tool", {"name": name, "args": args}, frist=240)["ergebnis"]
    except Exception:
        return ("Dein PC ist gerade nicht erreichbar (aus oder nicht verbunden). Ich habe nichts ausgeführt – "
                "sag Nikola, dass diese Funktion den PC braucht.")


def bauen(innen: bool = True):
    """Verdrahtet Assistent + Telegram + Tunnel-Gegenstellen. innen=False: ohne den Server fuer Meldungen vom PC (Tests)."""
    if not TOKEN:
        sys.exit("KLAUS_LINK_TOKEN fehlt")
    a = ServerAssistent()
    tg = TB.TelegramKlaus(a)
    a.telegram = tg
    remote_ids: set[str] = set()

    # Werkzeuge: Daten-Werkzeuge hier, Rest auf dem PC; dazu das Selbst-Update (nur auf dem Server)
    import selbst_update

    tg.deklarationen.append({"name": "update_einspielen", "description": "Klaus' eigenen Code auf dem Server aktualisieren (neuer Stand "
                             "aus GitHub). Zeigt die neuen Aenderungen, braucht Nikolas Freigabe (Knopf + PIN), testet vor dem "
                             "Uebernehmen und bleibt bei einem Fehler auf der alten Version. Nur wenn Nikola ein Update will.",
                             "parameters": {"type": "OBJECT", "properties": {}}})

    def update_werkzeug() -> str:
        try:
            neu = selbst_update.pruefen()
        except Exception as e:
            return f"Ich konnte nicht nach Updates schauen: {str(e)[:120]}"
        if not neu:
            return "Klaus ist auf dem neuesten Stand, es gibt kein Update."
        liste = "; ".join(z.split(" ", 1)[-1] for z in neu[:5])
        return a._mit_freigabe("update", f"Update einspielen ({len(neu)} Änderung{'en' if len(neu) != 1 else ''}: {liste[:180]})",
                               selbst_update.einspielen, an="Klaus-Server")

    import briefing
    import server_sicherheit as sicherheit

    def pc_sicherheit() -> str:
        t = pc_werkzeug("sicherheit_status", {})
        return "💻 PC: nicht erreichbar (aus oder nicht verbunden)" if t.startswith("Dein PC ist gerade nicht erreichbar") else f"💻 PC: {t}"

    def sicherheit_befehl(eingabe: str) -> str:
        """/sicherheit [scan|basis] - Server und PC zusammen"""
        arg = eingabe.strip().split(maxsplit=1)[1].strip().lower() if len(eingabe.split()) > 1 else ""
        if arg == "scan":
            sicherheit.auftrag("scan")
            pc = pc_werkzeug("sicherheit_scan", {"art": "schnell"})
            return ("🦠 Ich starte den Virenscan auf dem Server (ClamAV, ein paar Minuten) und auf dem PC (Defender). "
                    "Die Ergebnisse kommen als Nachricht.\n💻 PC: " + pc)
        if arg == "basis":
            return a._mit_freigabe("sicherheit_basis", "Server-Normalzustand neu setzen (aktuellen Zustand als sicher übernehmen)",
                                   lambda token: (freigabe.pruefe(token, "sicherheit_basis"), sicherheit.auftrag("basis"))[0] or
                                   "Ich übernehme den Zustand als Normalzustand, die Bestätigung kommt gleich.", an="Server-Wächter")
        neu = sicherheit.auftrag("pruefen", warte_s=45)   # frischer Bericht
        return (neu or sicherheit.text()) + "\n\n" + pc_sicherheit()

    tg.befehle["/sicherheit"] = sicherheit_befehl

    import watchlist
    tg.befehle["/watchlist"] = watchlist.watchlist_befehl
    tg.befehle["/alarm"] = tg.befehle["/alarme"] = watchlist.alarm_befehl
    tg.deklarationen += [
        {"name": "watchlist_verwalten", "description": "Watchlist: zeigen (mit Kursen), Wert hinzufuegen oder entfernen. Fuer 'setz Nvidia auf die Watchlist', 'was beobachte ich'.",
         "parameters": {"type": "OBJECT", "properties": {"aktion": {"type": "STRING", "description": "zeigen, hinzufuegen oder entfernen"},
                                                        "name": {"type": "STRING", "description": "Name oder Kuerzel, z. B. Nvidia"}}, "required": ["aktion"]}},
        {"name": "alarm_verwalten", "description": "Kurs-Alarm: 'Sag Bescheid, wenn Nvidia unter 200 faellt'. Setzt einen Einmal-Alarm (Meldung per Telegram), zeigt oder loescht Alarme.",
         "parameters": {"type": "OBJECT", "properties": {"aktion": {"type": "STRING", "description": "setzen, zeigen oder loeschen"},
                                                        "name": {"type": "STRING"}, "richtung": {"type": "STRING", "description": "unter (faellt unter) oder ueber (steigt ueber)"},
                                                        "preis": {"type": "NUMBER", "description": "Schwelle in der Waehrung der Aktie"},
                                                        "nummer": {"type": "INTEGER", "description": "Nummer des Alarms beim Loeschen"}}, "required": ["aktion"]}}]
    tg.deklarationen.append({"name": "sicherheit_gesamt", "description": "Sicherheitszustand von Server UND PC (Abweichungen, Angriffe, "
                             "Updates, Virenscan). Fuer 'wie sicher ist alles', 'Sicherheitscheck'. Scan starten: einstellung=scan.",
                             "parameters": {"type": "OBJECT", "properties": {"einstellung": {"type": "STRING", "description": "leer = Bericht; scan = Virenscan starten"}}}})
    # Alpaca (US-Aktien/ETFs/Krypto): Papier-Konto (Standard) ohne Freigabe; Echtgeld (ALPACA_LIVE=1) jede Order mit Knopf + PIN
    import alpaca_handel as alpaca

    def alpaca_lesen(_eingabe: str = "") -> str:
        """/alpaca - Kontostand, Positionen, offene Orders"""
        try:
            return alpaca.konto_text()
        except alpaca.HandelFehler as e:
            return str(e)

    def alpaca_order(args: dict) -> str:
        try:
            auftrag = alpaca.vorbereiten(args.get("aktion") or "", args.get("name") or "", args.get("stueck"),
                                         args.get("betrag_usd"), args.get("limit"), args.get("order_nr") or "")
        except (alpaca.HandelFehler, ValueError, TypeError) as e:
            return f"Die Order geht so nicht: {str(e)[:200]}"
        if not alpaca.live():   # Papier-Konto: Spielgeld, sofort ohne Freigabe
            try:
                return alpaca.papier_direkt(auftrag)
            except alpaca.HandelFehler as e:
                return f"Die Order ging nicht: {str(e)[:200]}"
        return a._mit_freigabe(alpaca.ART, auftrag.text, lambda token: alpaca.ausfuehren(token, auftrag),
                               an=f"Alpaca {alpaca.modus()}-Konto")

    tg.befehle["/alpaca"] = alpaca_lesen
    tg.befehle["/hebel"] = lambda e: (alpaca.hebel_setzen(e.split()[1]) if len(e.split()) > 1 else
                                     "So: /hebel 1 (aus), /hebel 2 oder /hebel 4 (Daytrading). Aktuell siehst du ihn bei /alpaca.")
    # Mit Alpaca ersetzt das Papier-Konto von Alpaca das alte Spielgeld-Depot des PCs (das ging nur bei laufendem PC)
    if alpaca.konfiguriert():
        tg.deklarationen[:] = [d for d in tg.deklarationen if d["name"] not in ("papier_order", "depot_status")]
    tg.befehle["/alpaca_schluessel"] = lambda eingabe: alpaca.schluessel_setzen(eingabe, TB._env_setzen)
    tg.geheime_befehle.add("/alpaca_schluessel")
    tg.deklarationen += [
        {"name": "alpaca_konto", "description": "Echtes Broker-Konto bei Alpaca (Standard: Papier-Konto von Alpaca): Kontostand, "
         "Positionen, offene Orders mit Nummer. Fuer 'wie steht mein Alpaca-Depot', 'was habe ich bei Alpaca'.",
         "parameters": {"type": "OBJECT", "properties": {}}},
        {"name": "alpaca_hebel", "description": "Margin-Hebel des Alpaca-Papier-Kontos einstellen: 1 (aus), 2 oder 4 (Daytrading, "
         "ab 25.000 $). Bestimmt die Kaufkraft fuer gehebelte Orders. Nur wenn Nikola Hebel will.",
         "parameters": {"type": "OBJECT", "properties": {"faktor": {"type": "INTEGER", "description": "1, 2 oder 4"}}, "required": ["faktor"]}},
        {"name": "alpaca_order", "description": "Order bei Alpaca (US-Aktien, ETFs, Krypto in USD): kaufen, verkaufen oder stornieren. "
         "Auf dem Papier-Konto (Spielgeld) wird sie sofort ausgefuehrt; nur bei Echtgeld braucht sie Nikolas Freigabe. Entweder stueck "
         "ODER betrag_usd. Ohne limit = Marktpreis. Kein Leerverkauf. Stornieren braucht order_nr aus alpaca_konto.",
         "parameters": {"type": "OBJECT", "properties": {
             "aktion": {"type": "STRING", "description": "kaufen, verkaufen oder stornieren"},
             "name": {"type": "STRING", "description": "Name oder US-Kuerzel, z. B. Nvidia, SPY, Bitcoin"},
             "stueck": {"type": "NUMBER", "description": "Anzahl Stueck (Bruchteile moeglich)"},
             "betrag_usd": {"type": "NUMBER", "description": "Betrag in US-Dollar statt Stueckzahl"},
             "limit": {"type": "NUMBER", "description": "Limitpreis in USD (optional)"},
             "order_nr": {"type": "STRING", "description": "Nummer der Order beim Stornieren"}}, "required": ["aktion"]}}]

    # Eigene Strategien (nur Papier-Konto): testen, einschalten, fortsetzen ohne Freigabe; danach handeln sie selbst
    import strategien

    def strategie_params(args: dict) -> dict:
        return {k: args.get(k) for k in ("kurz", "lang", "unter", "ueber", "tage", "tp_proz", "sl_proz")}

    def strategie_werkzeug(args: dict) -> str:
        akt = (args.get("aktion") or "zeigen").lower()
        typ = (args.get("typ") or "").lower()
        try:
            if akt.startswith("test"):
                return strategien.testen(typ, args.get("name") or "", strategie_params(args), args.get("betrag_usd"), args.get("budget_usd"))
            if akt.startswith(("anleg", "start", "aktiv", "einschalt")):
                e = strategien.vorbereiten(typ, args.get("name") or "", strategie_params(args), args.get("betrag_usd") or 0,
                                           args.get("budget_usd"), args.get("titel") or "")
                return e["test"] + "\n\n" + strategien.anlegen(e)
            if akt.startswith("fortsetz"):
                return strategien.fortsetzen(args.get("nummer") or "")
            if akt.startswith("paus"):
                return strategien.pausieren(args.get("nummer") or "")
            if akt.startswith(("stop", "alle")):
                return strategien.alle_stoppen()
            if akt.startswith(("loesch", "lösch")):
                return strategien.loeschen(args.get("nummer") or "")
            return strategien.liste()
        except (strategien.StrategieFehler, alpaca.HandelFehler, LookupError, ValueError, TypeError) as e:
            return f"Das geht so nicht: {str(e)[:200]}"

    tg.befehle["/strategien"] = tg.befehle["/strategie"] = strategien.befehl

    # Analysen: Depot-Analyse, Markt-Scanner, Wochenbericht (nur lesend)
    import analysen

    tg.befehle["/depotcheck"] = lambda _e: analysen.depot_analyse()
    tg.befehle["/scanner"] = lambda e: analysen.scanner(e.split(maxsplit=1)[1] if len(e.split()) > 1 else "alle")
    tg.befehle["/wochenbericht"] = lambda _e: analysen.wochenbericht()
    tg.deklarationen += [
        {"name": "depot_analyse", "description": "Analyse des Alpaca-Depots: Verteilung, Klumpenrisiko, Streuung, Gewinner/Verlierer, "
         "was heute runterzieht, letzter Monat gegen den S&P 500. Fuer 'wie gut ist mein Depot aufgestellt', 'was zieht runter'.",
         "parameters": {"type": "OBJECT", "properties": {}}},
        {"name": "markt_scanner", "description": "Durchsucht ca. 50 grosse US-Werte, ETFs, Krypto und die Watchlist nach Signalen: "
         "ueberverkauft/ueberkauft (RSI), frischer Auf-/Abwaertstrend (SMA20/50-Kreuz), 52-Wochen-Hoch/Tief. Fuer 'wo tut sich was', "
         "'such mir Kandidaten'. Danach kannst du Treffer mit markt_analyse oder strategie (testen) vertiefen. Dauert ~20 s.",
         "parameters": {"type": "OBJECT", "properties": {"art": {"type": "STRING", "description":
                        "alle, ueberverkauft, ueberkauft, trend_auf, trend_ab, hoch oder tief"}}}},
        {"name": "wochenbericht", "description": "Wochenbericht jetzt: Depot gegen S&P 500, Strategien (Trades, Gewinn/Verlust), "
         "aktuelle Signale. Kommt sonst automatisch freitags nach Boersenschluss.", "parameters": {"type": "OBJECT", "properties": {}}}]
    tg.deklarationen.append(
        {"name": "strategie", "description": "Eigene Handelsstrategien fuer das Alpaca-PAPIER-Konto. Du darfst Strategien selbst "
         "entwerfen: mit aktion=testen Varianten an 2 Jahren Kursdaten pruefen (mehrere Parameter ausprobieren, mit Kaufen+Halten "
         "vergleichen) und Nikola die beste ehrlich vorschlagen. aktion=anlegen schaltet sie sofort ein (nur Papier-Konto), "
         "danach handelt sie selbst. Arten: trend (kurz/lang Tage, SMA), rsi (unter/ueber), sparplan "
         "(tage). Optional tp_proz (Gewinnmitnahme), sl_proz (Stopp). Weitere Aktionen: zeigen, pausieren, fortsetzen, loeschen, stop "
         "(alle anhalten). Backtests sind Vergangenheit, keine Garantie.",
         "parameters": {"type": "OBJECT", "properties": {
             "aktion": {"type": "STRING", "description": "testen, anlegen, zeigen, pausieren, fortsetzen, loeschen oder stop"},
             "typ": {"type": "STRING", "description": "trend, rsi oder sparplan"},
             "name": {"type": "STRING", "description": "Wert, z. B. Nvidia, SPY, Bitcoin"},
             "kurz": {"type": "INTEGER"}, "lang": {"type": "INTEGER"},
             "unter": {"type": "NUMBER"}, "ueber": {"type": "NUMBER"}, "tage": {"type": "INTEGER"},
             "tp_proz": {"type": "NUMBER"}, "sl_proz": {"type": "NUMBER"},
             "betrag_usd": {"type": "NUMBER", "description": "Dollar je Order"},
             "budget_usd": {"type": "NUMBER", "description": "hoechstens so viel investiert (Sparplan: Summe aller Raten)"},
             "titel": {"type": "STRING"}, "nummer": {"type": "STRING", "description": "Nummer der Strategie"}},
             "required": ["aktion"]}})

    # Claude: PC an -> Claude am PC (wie bisher), PC aus -> Claude Code in der Cloud (hier auf dem Server)
    import server_claude

    def claude_fertig(text: str, daten: bytes | None, dateiname: str) -> None:
        tg.senden(text)
        if daten:
            tg.datei(daten, dateiname, "Projekt von Claude (Server)")

    def claude_werkzeug(name: str, args: dict) -> str:
        if pc_an():
            return pc_werkzeug(name, args)
        if name == "frage_claude":
            return server_claude.frage(args.get("frage") or "")
        return server_claude.bauen(args.get("auftrag") or "", args.get("name") or "projekt", claude_fertig)

    def pc_status_text() -> str:
        return ("💻 Dein PC ist an und verbunden." if pc_an() else
                "💻 Dein PC ist aus oder nicht verbunden. Claude-Aufträge laufen dann über die Cloud (Server).") + \
               "\n☁️ " + server_claude.status()

    tg.befehle["/claude"] = lambda _e: server_claude.status()
    tg.befehle["/pc"] = lambda _e: pc_status_text()
    tg.befehle["/claude_token"] = lambda e: server_claude.token_setzen(e, TB._env_setzen)
    tg.geheime_befehle.add("/claude_token")
    tg.deklarationen.append({"name": "pc_status", "description": "Prueft, ob Nikolas PC gerade an und verbunden ist, und ob "
                             "Claude in der Cloud (Server) bereit ist. Vor PC-Aufgaben nutzen, wenn unklar ist, ob der PC laeuft.",
                             "parameters": {"type": "OBJECT", "properties": {}}})

    tg.befehle["/briefing"] = briefing.befehl
    tg.deklarationen.append({"name": "briefing", "description": "Morgen-Briefing jetzt (Wetter, Termine heute, Nachrichten) oder "
                             "Uhrzeit/an/aus einstellen. Fuer 'Briefing', 'was steht heute an und wie ist das Wetter'.",
                             "parameters": {"type": "OBJECT", "properties": {"einstellung": {"type": "STRING",
                                            "description": "leer = jetzt; '7:30' = Uhrzeit; 'aus' oder 'an'"}}}})

    # PC-Zugriff (Shell/Browser/Bildschirm): /status, /timer, /stop gehen direkt an den PC - nie ueber die KI
    abbruch = {"bis": 0.0}

    def pc_zugriff_befehl(eingabe: str) -> str:
        if eingabe.strip().lower().startswith("/stop"):
            abbruch["bis"] = time.time() + 30   # laufende Antwort darf keine Werkzeuge mehr aufrufen
        try:
            return pc_post("/pc_zugriff", {"befehl": eingabe.strip()[:100]}, frist=30)["text"]
        except Exception:
            if eingabe.strip().lower().startswith("/stop"):
                return "🛑 Gestoppt (hier auf dem Server). Der PC ist gerade nicht erreichbar – dort läuft also auch nichts."
            return ("🖥 PC-Zugriff\n• Shell: getrennt\n• Browser: getrennt\n• Bildschirm: getrennt\n"
                    "Der PC ist gerade nicht erreichbar (aus oder nicht verbunden).")
    for b in ("/status", "/timer", "/stop"):
        tg.befehle[b] = pc_zugriff_befehl
    def ruhe_befehl(text):
        try:
            return pc_post('/betrieb', {'befehl': text}, frist=8)['text']
        except Exception:
            return 'PC nicht erreichbar. Ruhemodus konnte dort nicht geaendert werden.'
    tg.befehle['/ruhe'] = ruhe_befehl
    def ki_befehl(text):
        import ki_kosten
        return ki_kosten.status_text()
    tg.befehle['/ki'] = ki_befehl

    def werkzeug(name, args):
        if time.time() < abbruch["bis"]:
            return "Abgebrochen: Nikola hat /stop geschickt. Mach nichts weiter, sag nur kurz, dass du gestoppt hast."
        if name == "update_einspielen":
            return update_werkzeug()
        if name in ("frage_claude", "projekt_bauen"):
            return claude_werkzeug(name, args)
        if name == "pc_status":
            return pc_status_text()
        if name in ("papier_order", "depot_status") and alpaca.konfiguriert():   # alte Namen -> Alpaca-Papier-Konto
            name = "alpaca_order" if name == "papier_order" else "alpaca_konto"
            if args.get("betrag_eur") and not args.get("betrag_usd"):
                args = {**args, "betrag_usd": args["betrag_eur"]}
        if name == "alpaca_konto":
            return alpaca_lesen()
        if name == "alpaca_order":
            return alpaca_order(args)
        if name == "alpaca_hebel":
            try:
                return alpaca.hebel_setzen(args.get("faktor"))
            except alpaca.HandelFehler as e:
                return str(e)
        if name == "strategie":
            return strategie_werkzeug(args)
        if name == "depot_analyse":
            return analysen.depot_analyse()
        if name == "markt_scanner":
            return analysen.scanner(args.get("art") or "alle")
        if name == "wochenbericht":
            return analysen.wochenbericht()
        if name == "briefing":
            return briefing.befehl(f"/briefing {args.get('einstellung') or ''}")
        if name == "sicherheit_gesamt":
            return sicherheit_befehl(f"/sicherheit {args.get('einstellung') or ''}")
        if name == "watchlist_verwalten":
            akt, nm = (args.get("aktion") or "zeigen").lower(), (args.get("name") or "").strip()
            if akt.startswith("hinzu") and nm:
                return watchlist.hinzu(nm)
            if akt.startswith(("entfern", "weg", "loesch", "lösch")) and nm:
                return watchlist.weg(nm)
            return watchlist.liste()
        if name == "alarm_verwalten":
            akt = (args.get("aktion") or "zeigen").lower()
            if akt.startswith("setz") and args.get("name") and args.get("preis") is not None:
                return watchlist.alarm_setzen(args["name"], args.get("richtung") or "unter", float(args["preis"]))
            if akt.startswith(("loesch", "lösch", "weg")) and args.get("nummer"):
                return watchlist.alarm_loeschen(int(args["nummer"]))
            return watchlist.alarme_text()
        return a.gemini._werkzeug(name, args) if name in LOKAL else pc_werkzeug(name, args)
    tg.werkzeug_aufruf = werkzeug

    # Gedaechtnis kommt vom PC (zuletzt bekannter Stand, wenn der PC aus ist)
    def gedaechtnis() -> str:
        try:
            text = pc_post("/gedaechtnis", {}, frist=4)["text"]
            GEDAECHTNIS.parent.mkdir(exist_ok=True)
            GEDAECHTNIS.write_text(text, encoding="utf-8")
            return text
        except Exception:
            return GEDAECHTNIS.read_text(encoding="utf-8") if GEDAECHTNIS.exists() else ""
    tg.gedaechtnis_fn = gedaechtnis

    # Freigaben: PC-Anfragen werden auf dem PC entschieden, eigene (Kalender) hier
    def entscheider(fid, ok, wie):
        if fid in remote_ids:
            try:
                return bool(pc_post("/entscheide", {"id": fid, "ok": ok, "wie": wie}, frist=8)["ok"])
            except Exception:
                return False
        return freigabe.entscheide(fid, ok, wie)
    tg.entscheider = entscheider

    # Chat-Zeilen ans Panel des PCs (best effort, blockiert nie)
    tg.ereignis_fn = lambda art, text: threading.Thread(
        target=lambda: _versuche(lambda: pc_post("/ereignis", {"art": art, "text": text}, frist=3)), daemon=True).start()

    freigabe.melden = lambda ereignis, anfrage: tg.freigabe_melden(ereignis, anfrage)

    class Innen(BaseHTTPRequestHandler):
        """Nimmt Meldungen vom PC an (nur 127.0.0.1, ueber den Tunnel)."""
        def log_message(self, *x):
            pass

        def do_POST(self):
            if not hmac.compare_digest(self.headers.get("X-Token", ""), TOKEN):
                self.send_response(403); self.end_headers(); return
            if self.path == "/backup":   # verschluesseltes PC-Archiv (der Server kann es nicht lesen)
                laenge = int(self.headers.get("Content-Length", "0"))
                if not 0 < laenge <= 50 * 1024 * 1024:
                    self.send_response(413); self.end_headers(); return
                roh = self.rfile.read(laenge)
                ziel = Path("/home/klaus/backup-pc"); ziel.mkdir(exist_ok=True)
                datei = ziel / f"pc-{time.strftime('%Y-%m-%d')}.tar.gz.age"
                (datei.with_suffix(".tmp")).write_bytes(roh); datei.with_suffix(".tmp").replace(datei)
                for alt in sorted(ziel.glob("pc-*.age"))[:-7]:
                    alt.unlink()
                antwort = json.dumps({"ok": True, "bytes": len(roh)}).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(antwort))); self.end_headers(); self.wfile.write(antwort)
                print(f"[Backup] PC-Archiv erhalten: {len(roh) // 1024} KB", flush=True)
                return
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
            if self.path == "/senden":
                tg.senden(str(d.get("text", ""))[:4000], **({"reply_markup": d["reply_markup"]} if d.get("reply_markup") else {}))
            elif self.path == "/datei":   # Datei vom PC (datei_senden.py)
                import base64
                tg.datei(base64.b64decode(d.get("inhalt", "")), str(d.get("name", "datei"))[:120], str(d.get("text", ""))[:1000])
            elif self.path == "/foto":   # Bildschirmfoto vom PC (pc_zugriff.bildschirm)
                import base64
                tg.foto(base64.b64decode(d.get("bild", "")), str(d.get("text", ""))[:1000])
            elif self.path == "/freigabe":
                if d["ereignis"] == "auf":
                    remote_ids.add(d["id"])
                tg.freigabe_melden(d["ereignis"], SimpleNamespace(**{k: d.get(k) for k in ("id", "art", "was", "an", "anzahl", "ok", "wie")}))
                if d["ereignis"] != "auf":
                    remote_ids.discard(d["id"])
            roh = b'{"ok": true}'
            self.send_response(200); self.send_header("Content-Length", str(len(roh))); self.end_headers(); self.wfile.write(roh)

    if innen:
        threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", SERVER_PORT), Innen).serve_forever, daemon=True).start()
    return a, tg


def main() -> None:
    a, tg = bauen()
    print(f"[Server] Klaus-Gehirn laeuft (Telegram, Werkzeuge lokal: {sorted(LOKAL)})", flush=True)
    import briefing

    briefing.starte(tg.senden)
    import watchlist
    watchlist.starte(tg.senden)   # alle 10 Minuten Kurse pruefen: Alarme und starke Tagesbewegungen
    import strategien
    strategien.starte(tg.senden)   # alle 5 Minuten: eigene Strategien (nur Papier-Konto)
    import analysen
    analysen.starte(tg.senden)     # Wochenbericht freitags nach US-Boersenschluss
    try:
        import selbst_update
        meldung = selbst_update.nach_neustart()
        if meldung:
            tg.senden(meldung)
    except Exception as e:
        print(f"[Update] Meldung nach Neustart: {e}", flush=True)
    try:   # automatisch aus GitHub, nur wenn Klaus gerade nichts tut (keine Antwort/Freigabe/Claude-Bau, 5 min Ruhe)
        import selbst_update
        import server_claude

        selbst_update.starte_auto(lambda: (freigabe.offen() or tg._sperre.locked() or server_claude._bau_sperre.locked()
                                           or time.time() - tg.zuletzt < 5 * 60), tg.senden)
    except Exception as e:
        print(f"[Update] Auto-Update nicht gestartet: {e}", flush=True)
    tg.run()   # blockiert


def _versuche(f):
    try:
        f()
    except Exception:
        pass


if __name__ == "__main__":
    main()
