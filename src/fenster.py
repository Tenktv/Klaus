"""
Klaus - Fenster
    DesktopPanel  ersetzt den Desktop: Vollbild, liegt immer ganz unten hinter allen Apps
    ChatFenster   das Klaus-Fenster fuer Gespraeche, mit Maus und Tastatur bedienbar
    MiniOrb       Spielmodus: kleiner verschiebbarer Kreis mit Mute-Knopf statt Panel (ohne Browser-Engine)
Beide zeigen HTML aus src/web/ und sprechen ueber QWebChannel mit Python (WebBruecke).
"""

import base64
import configparser
import ctypes
import json
import os
import re
import subprocess
import threading
import webbrowser
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QBuffer, QFileInfo, QIODevice, QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QFileIconProvider, QWidget

import apps
import daten
import identitaet

WEB_DIR = Path(__file__).resolve().parent / "web"
STARTMENUE = [
    Path(os.environ.get("PROGRAMDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
    Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs",
]

WM_WINDOWPOSCHANGING = 0x0046
HWND_BOTTOM = 1
SWP_NOZORDER = 0x0004


class WINDOWPOS(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("hwndInsertAfter", wintypes.HWND), ("x", ctypes.c_int),
                ("y", ctypes.c_int), ("cx", ctypes.c_int), ("cy", ctypes.c_int), ("flags", ctypes.c_uint)]


# ------------------------------------------------------------------ Taskleiste
class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uCallbackMessage", wintypes.UINT),
                ("uEdge", wintypes.UINT), ("rc", wintypes.RECT), ("lParam", wintypes.LPARAM)]


ABM_GETSTATE, ABM_SETSTATE, ABS_AUTOHIDE = 0x4, 0xA, 0x1


def _appbar(nachricht: int, lparam: int = 0) -> int:
    daten_ = APPBARDATA(cbSize=ctypes.sizeof(APPBARDATA), hWnd=ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None),
                        lParam=lparam)
    return ctypes.windll.shell32.SHAppBarMessage(nachricht, ctypes.byref(daten_))


def taskleiste_versteckt() -> bool:
    return bool(_appbar(ABM_GETSTATE) & ABS_AUTOHIDE)


def taskleiste_verstecken(an: bool) -> None:
    """Windows-Funktion "Taskleiste automatisch ausblenden" ein/aus."""
    _appbar(ABM_SETSTATE, ABS_AUTOHIDE if an else 0)


# ------------------------------------------------------------------ App-Icons
_verknuepfungen: dict[str, Path] | None = None
_icon_cache: dict[str, str] = {}


def _verknuepfung(name: str) -> Path | None:
    global _verknuepfungen
    if _verknuepfungen is None:
        _verknuepfungen = {}
        for wurzel in STARTMENUE:
            if wurzel.exists():
                for p in list(wurzel.rglob("*.lnk")) + list(wurzel.rglob("*.url")):
                    _verknuepfungen.setdefault(p.stem.lower(), p)
    return _verknuepfungen.get(name.lower())


def app_icon(name: str) -> str:
    """Icon einer Startmenue-App als data:-URL ("" wenn keins gefunden)."""
    if name in _icon_cache:
        return _icon_cache[name]
    pfad = _verknuepfung(name)
    datei = None
    if pfad and pfad.suffix == ".url":  # Steam-/Riot-Spiele: Icon steht in der .url-Datei
        ini = configparser.ConfigParser(interpolation=None)
        try:
            ini.read(pfad, encoding="utf-8")
            datei = ini.get("InternetShortcut", "IconFile", fallback=None)
        except configparser.Error:
            datei = None
    elif pfad:
        datei = str(pfad)
    url = ""
    if datei and Path(datei).exists():
        bild = QFileIconProvider().icon(QFileInfo(datei)).pixmap(64, 64)
        if not bild.isNull():
            puffer = QBuffer()
            puffer.open(QIODevice.WriteOnly)
            bild.save(puffer, "PNG")
            url = "data:image/png;base64," + base64.b64encode(bytes(puffer.data())).decode()
    _icon_cache[name] = url
    return url


# ------------------------------------------------------------------ Bruecke
class WebBruecke(QObject):
    """Wird im JavaScript als `klaus` sichtbar."""

    daten = Signal(str, str)  # art, json
    nachricht = Signal(str, str)  # rolle, text
    zustand = Signal(str)
    pegel = Signal(float)
    thema = Signal(str)  # Design-Variante (siehe THEMEN in web/klaus.js)
    webUrl = Signal(str, str)  # Web-Widget id, neue Adresse
    panelBefehl = Signal(str)  # Widget-Befehl von Klaus als JSON (siehe assistent.panel_wunsch)
    holo = Signal(str)  # Pop-up-Fenster rund ums Auge als JSON (siehe assistent.holo / web/popups.js)
    untertitel = Signal(str)  # Text unter dem Orb im Overlay
    sichtbar = Signal(bool)  # False = Panel ist von einem Vollbild-Fenster verdeckt -> Animationen pausieren
    minimieren = Signal()  # Knopf oben rechts im Panel -> klaus_app blendet das Panel aus
    stummStatus = Signal(bool)  # Klaus stumm (hoert nur noch auf "Klaus, wieder an")
    mikroStatus = Signal(bool)  # Mikrofon komplett aus
    mini = Signal(bool)  # Spielmodus: Panel ist weg -> alle Holo-Fenster auf Bildschirm 2 (bzw. ueber das Spiel)
    _fertig = Signal(str, str)  # intern: Worker-Thread -> GUI-Thread

    alle: list["WebBruecke"] = []  # damit ein Design-Wechsel Panel und Popup gleichzeitig trifft

    def __init__(self, assistent, zeige_chat, fenster=None) -> None:
        super().__init__()
        self.assistent = assistent
        self.zeige_chat = zeige_chat
        self.fenster = fenster  # das QWidget, in dem die Seite laeuft
        self.web: WebWidgets | None = None
        self._fertig.connect(self.daten.emit)
        WebBruecke.alle.append(self)

    # ---------------------------------------------------------------- Design
    @Slot(result=str)
    def ladeThema(self) -> str:
        return daten.lade_einstellungen().get("thema", "jarvis")

    @Slot(result=str)
    def ladeEigeneFarbe(self) -> str:
        """Zuletzt im Farbrad gewaehlte Farbe ("#rrggbb") oder ""."""
        return daten.lade_einstellungen().get("eigene_farbe", "")

    @Slot(str)
    def setzeThema(self, name: str) -> None:
        setze_thema(name)

    # ---------------------------------------------------------------- Popup ohne Rahmen
    @Slot()
    def fensterZiehen(self) -> None:
        if self.fenster and self.fenster.windowHandle():
            self.fenster.windowHandle().startSystemMove()

    @Slot()
    def fensterZu(self) -> None:
        if self.fenster:
            self.fenster.hide()

    # ---------------------------------------------------------------- Web-Widgets
    @Slot(str, str, int, int, int, int, bool)
    def webSetze(self, wid: str, url: str, x: int, y: int, b: int, h: int, sichtbar: bool) -> None:
        if self.web:
            self.web.setze(wid, url, x, y, b, h, sichtbar)

    @Slot(str)
    def webWeg(self, wid: str) -> None:
        if self.web:
            self.web.weg(wid)

    @Slot(str, str)
    def webAktion(self, wid: str, aktion: str) -> None:
        if self.web:
            self.web.aktion(wid, aktion)

    @Slot(bool)
    def webAlle(self, sichtbar: bool) -> None:
        if self.web:
            self.web.alle(sichtbar)

    @Slot(str, str)
    def lade(self, art: str, wert: str) -> None:
        """Holt Daten im Hintergrund. Antwort kommt als daten("art|wert", json)."""
        quelle = daten.QUELLEN.get(art)
        if not quelle:
            return
        schluessel = f"{art}|{wert}" if wert else art

        def holen() -> None:
            try:
                ergebnis = quelle(wert) if wert else quelle()
            except Exception as e:  # ein kaputter Dienst darf das Panel nicht stoppen
                ergebnis = {"fehler": str(e)[:120]}
            self._fertig.emit(schluessel, json.dumps(ergebnis, ensure_ascii=False))

        threading.Thread(target=holen, daemon=True).start()

    @Slot(result=str)
    def ladeLayout(self) -> str:
        return daten.lade_layout()

    @Slot(str)
    def speichereLayout(self, text: str) -> None:
        daten.speichere_layout(text)

    @Slot(str, result=str)
    def icon(self, name: str) -> str:
        return app_icon(name)

    @Slot(str)
    def oeffne(self, name: str) -> None:
        threading.Thread(target=apps.oeffne, args=(name,), daemon=True).start()

    @Slot(str)
    def ordner(self, pfad: str) -> None:
        os.startfile(pfad)

    @Slot(str)
    def link(self, url: str) -> None:
        if url.startswith(("http://", "https://")):
            webbrowser.open(url)

    @Slot(str)
    def vscode(self, pfad: str) -> None:
        subprocess.Popen(["cmd", "/c", "code", pfad], creationflags=subprocess.CREATE_NO_WINDOW)

    @Slot(str, str)
    def graph(self, was: str, wert: str) -> None:
        """Graph-Fenster aus dem Panel heraus (Knopf im Gedaechtnis-/Projekte-Widget)."""
        if self.assistent:
            self.assistent.graph_zeigen(was, wert)

    @Slot(str)
    def vergissEintrag(self, eintrag_id: str) -> None:
        import gehirn

        gehirn.vergiss_id(int(eintrag_id))
        self.lade("gedaechtnis", "")

    @Slot(str)
    def papierkorb(self, pfad: str) -> None:
        """Loeschen aus dem Panel: laeuft wie per Stimme ueber das Freigabe-Gate."""
        if self.assistent:
            print(f"[Klaus] Papierkorb: {self.assistent.loeschen_starten(pfad)}")
            threading.Timer(95, lambda: self.lade("projekte", "")).start()

    @Slot(str, result=bool)
    def zweit(self, befehl: str) -> bool:
        """Panel -> zweiter Bildschirm: Holo-Befehl dorthin weiterreichen. False = nicht verfuegbar (lokal oeffnen)."""
        ziel = getattr(self, "zweit_fenster", None)
        if not ziel or not getattr(self.zweit_bruecke, "seite_bereit", False) or not ziel.verfuegbar():
            print(f"[Klaus] Bildschirm 2 nicht verfuegbar (Fenster: {bool(ziel)}, Bildschirm: {bool(_zweiter_bildschirm())})")
            return False
        if '"oeffne"' in befehl or '"art"' in befehl:
            ziel.zeigen()
        self.zweit_bruecke.holo.emit(befehl)
        return True

    @Slot(str)
    def planAnheften(self, plan_json: str) -> None:
        """Plan-Board: jede Box als eigenes Widget ins Panel (vom zweiten Bildschirm aus ueber die Panel-Bruecke)."""
        ziel = getattr(self, "panel_ziel", self)
        plan = json.loads(plan_json)
        for box in plan.get("boxen", []):
            ziel.panelBefehl.emit(json.dumps({"aktion": "eigen", "einst": {"titel": box["titel"], "art": box["art"],
                                                                            "eintraege": box["eintraege"], "plan": plan.get("titel", "")}},
                                             ensure_ascii=False))

    @Slot()
    def zweitBereit(self) -> None:
        """Seite auf Bildschirm 2 ist geladen und hoert auf Holo-Befehle."""
        self.seite_bereit = True

    @Slot()
    def zweitLeer(self) -> None:
        """Zweiter Bildschirm: letztes Fenster zu -> Buehne ausblenden."""
        if isinstance(self.fenster, ZweitFenster):
            self.fenster.hide()

    @Slot(str, str)
    def sicherheit(self, aktion: str, wert: str) -> None:
        """Sicherheits-Widget: scan (wert schnell/voll) oder bestaetigen (Basislinie uebernehmen)."""
        if not self.assistent:
            return
        if aktion == "scan":
            threading.Thread(target=lambda: print(f"[Klaus] Sicherheit: {self.assistent.sicherheit_scan(wert or 'schnell')}"), daemon=True).start()
        elif aktion == "bestaetigen":
            threading.Thread(target=self.assistent.sicherheit_bestaetigen, daemon=True).start()

    @Slot()
    def lagebericht(self) -> None:
        """Lagebericht aus dem Panel (Debug-Knopf): ohne Ton, Stationen im festen Takt."""
        if self.assistent:
            threading.Thread(target=self.assistent.lagebericht_zeigen, args=(False,), daemon=True).start()

    @Slot(str, bool)
    def freigabe(self, anfrage_id: str, ok: bool) -> None:
        """Klick auf Freigeben/Abbrechen im Freigabe-Fenster."""
        import freigabe

        freigabe.entscheide(anfrage_id, ok, "Klick im Panel")

    @Slot()
    def panelMinimieren(self) -> None:
        self.minimieren.emit()

    @Slot()
    def stummUmschalten(self) -> None:
        self.assistent.setze_stumm(not self.assistent.ist_stumm)

    @Slot()
    def mikroUmschalten(self) -> None:
        self.assistent.setze_mikro_aus(not self.assistent.pausiert)

    @Slot(result=str)
    def ladeSchalter(self) -> str:
        return json.dumps({"stumm": self.assistent.ist_stumm, "mikroAus": self.assistent.pausiert})

    @Slot()
    def chat(self) -> None:
        self.zeige_chat()

    @Slot(result=str)
    def ladeBootStatus(self) -> str:
        """Echte Zeilen fuer die Boot-Sequenz (nur lokale Pruefungen, kein Netz, keine KI): [[name, status, ok], ...]"""
        zeilen = [["HUD-RENDERER", "OK", True]]
        a = self.assistent
        try:
            zeilen.append(["MIKROFON", "AUS" if getattr(a, "pausiert", False) else "BEREIT", not getattr(a, "pausiert", False)])
            zeilen.append(["GEMINI LIVE", "BEREIT" if getattr(a, "gemini", None) else "NICHT EINGERICHTET", bool(getattr(a, "gemini", None))])
            import gehirn
            zeilen.append(["GEDÄCHTNISKERN", "GELADEN" if gehirn.FAKTEN_PATH.exists() else "LEER", gehirn.FAKTEN_PATH.exists()])
            import fernlink
            zeilen.append(["SERVER-LINK", "VERBINDET" if fernlink.konfiguriert() else "AUS", fernlink.konfiguriert()])
            import stream
            if stream.KANAL:
                zeilen.append(["TWITCH-CHAT", f"#{stream.KANAL.upper()}", True])
        except Exception as e:
            zeilen.append(["STATUS", str(e)[:30].upper(), False])
        return json.dumps(zeilen, ensure_ascii=False)

    @Slot(result=str)
    def ladeBetrieb(self) -> str:
        """Lokaler Live-Zustand fuer das Kontrollzentrum, ohne Netz-/KI-Aufruf."""
        import freigabe
        import pc_zugriff
        import spiel_coach
        import betrieb
        import ki_kosten
        try:
            ki_status = ki_kosten.status()
        except Exception:
            ki_status = {'premium_aktiv': False, 'fehler': 'KI-Kostenstatus nicht verfuegbar.'}

        a = self.assistent
        p = getattr(a, "protokoll", None)
        return json.dumps({
            "mikroAus": bool(getattr(a, "pausiert", True)),
            "stumm": bool(getattr(a, "ist_stumm", False)),
            "ruhe": betrieb.ruhe(),
            "sprachausgabe": betrieb.status(),
            "ki": ki_status,
            "protokoll": {"aktiv": bool(p and p.laeuft),
                          "titel": p.titel if p else "",
                          "sekunden": int(p.dauer()) if p else 0,
                          "zeilen": len(p.saetze) if p else 0,
                          "gesundheit": p.gesundheit() if p and hasattr(p, 'gesundheit') else {}},
            "coach": {"aktiv": spiel_coach.laeuft()},
            "pc": pc_zugriff.status(),
            "freigabe": freigabe.offen(),
        }, ensure_ascii=False)

    @Slot(str)
    def eingabe(self, text: str) -> None:
        """Manuelle Eingabe nutzt dieselbe Queue und Freigaben wie Sprache."""
        if self.assistent and text.strip():
            self.assistent.eingabe(text.strip()[:4000])

    @Slot()
    def ruheUmschalten(self) -> None:
        import betrieb
        self.assistent.setze_ruhe(not betrieb.ruhe())

    @Slot()
    def pcStopp(self) -> None:
        """Not-Aus ohne KI; blockierende Prozessbeendigung ausserhalb der GUI."""
        def stoppen() -> None:
            import pc_zugriff
            import spiel_coach
            spiel_coach.stoppen()
            self.nachricht.emit("info", pc_zugriff.stoppen())
        threading.Thread(target=stoppen, daemon=True).start()

    @Slot(int)
    def pcTimer(self, minuten: int) -> None:
        if not 0 <= minuten <= 240:
            self.nachricht.emit("info", "Zeitlimit: 1 bis 240 Minuten oder aus.")
            return
        import pc_zugriff
        threading.Thread(target=lambda: self.nachricht.emit("info", pc_zugriff.timer(minuten or None)), daemon=True).start()

    @Slot()
    def protokollBeenden(self) -> None:
        a = self.assistent
        if a and getattr(a, "protokoll", None):
            threading.Thread(target=lambda: self.nachricht.emit("info", a.protokoll_beenden()), daemon=True).start()

    @Slot()
    def coachBeenden(self) -> None:
        import spiel_coach
        self.nachricht.emit("info", spiel_coach.stoppen())


# Design-Varianten: (Hauptfarbe, Zweitfarbe beim Nachdenken). Die vollen Paletten stehen in web/klaus.js.
THEMEN = {
    "jarvis": ((0, 229, 255), (255, 179, 0)),
    "ironman": ((255, 59, 48), (255, 196, 0)),
    "matrix": ((0, 255, 120), (180, 255, 0)),
    "synthwave": ((190, 90, 255), (255, 60, 170)),
    "gold": ((255, 176, 0), (255, 90, 40)),
    "arktis": ((200, 235, 255), (120, 180, 255)),
}


# Gedaempfte Hauptfarben, wie sie das Panel wirklich zeigt (klaus.js wendeThemaAn "accent") - fuer den Mini-Orb
AKZENT = {"jarvis": (189, 199, 190), "ironman": (217, 166, 148), "matrix": (171, 194, 164), "synthwave": (193, 179, 199),
          "gold": (213, 186, 133), "arktis": (188, 200, 208)}
EIGENE_FARBE = re.compile(r"^#[0-9a-fA-F]{6}$")


def thema_farbe(name: str) -> tuple:
    """Hauptfarbe (r, g, b) eines Themas oder einer eigenen Farbe "#rrggbb"."""
    if EIGENE_FARBE.match(name or ""):
        return tuple(int(name[i:i + 2], 16) for i in (1, 3, 5))
    return AKZENT.get(name, AKZENT["gold"])


def setze_thema(name: str) -> str:
    """Design wechseln, speichern und an alle offenen Klaus-Seiten melden. "weiter" = naechstes.
    name: Thema aus THEMEN oder eigene Farbe "#rrggbb" (Farbrad). Gilt auch fuer Mini-Orb und Stream-Overlay."""
    if name == "weiter":
        namen = list(THEMEN)
        jetzt = daten.lade_einstellungen().get("thema", "jarvis")
        name = namen[(namen.index(jetzt) + 1) % len(namen)] if jetzt in namen else namen[0]
    if EIGENE_FARBE.match(name or ""):
        name = name.lower()
        daten.speichere_einstellung("eigene_farbe", name)   # damit das Farbrad sie beim naechsten Oeffnen wieder zeigt
    elif name not in THEMEN:
        return ""
    daten.speichere_einstellung("thema", name)
    for b in WebBruecke.alle:
        b.thema.emit(name)
    MiniOrb.HAUPT = thema_farbe(name)
    for orb in MiniOrb.alle:
        orb.update()
    try:
        import stream_overlay
        stream_overlay.senden("thema", name)
    except Exception:
        pass
    return name


# ------------------------------------------------------------------ Web-Widgets
class FolgeSeite(QWebEnginePage):
    """Links mit target=_blank im selben Widget oeffnen statt ins Leere."""

    def createWindow(self, _typ):
        return self


class WebWidgets:
    """Echte Browser-Ansichten, die ueber den Web-Widgets des Panels liegen.

    Websites wie YouTube oder ChatGPT verbieten das Einbetten per iframe; deshalb
    legt Python hier eine eigene Chromium-Ansicht passgenau ueber den Platzhalter.
    Logins bleiben im Profil data/browser gespeichert.
    """

    def __init__(self, panel: QWidget, bruecke: "WebBruecke") -> None:
        self.panel = panel
        self.bruecke = bruecke
        self.ansichten: dict[str, QWebEngineView] = {}
        self.profil = QWebEngineProfile("klaus-web", panel)
        speicher = daten.BASE_DIR / "data" / "browser"
        self.profil.setPersistentStoragePath(str(speicher))
        self.profil.setCachePath(str(speicher / "cache"))
        self.profil.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        # Wie normales Chrome auftreten: mit "QtWebEngine" im User-Agent halten Cloudflare &
        # Co. den Browser fuer einen Bot und haengen in der Sicherheitspruefung fest
        self.profil.setHttpUserAgent(re.sub(r"\s*QtWebEngine/\S+", "", self.profil.httpUserAgent()))

    def setze(self, wid: str, url: str, x: int, y: int, b: int, h: int, sichtbar: bool) -> None:
        ansicht = self.ansichten.get(wid)
        if ansicht is None:
            ansicht = QWebEngineView(self.panel)
            # Eigenes natives Fenster: sonst zeichnet Windows nachgeladene Seiten nicht ueber das Panel
            ansicht.setAttribute(Qt.WA_NativeWindow)
            ansicht.setPage(FolgeSeite(self.profil, ansicht))
            ansicht.ziel = ""
            ansicht.urlChanged.connect(lambda u, wid=wid, a=ansicht: self._neue_adresse(wid, a, u))
            ansicht.loadFinished.connect(lambda ok, a=ansicht: print(f"[Web] geladen={ok} {a.url().toString()}"))
            self.ansichten[wid] = ansicht
            print(f"[Web] Ansicht angelegt fuer {wid}")
        if url and url != ansicht.ziel:
            ansicht.ziel = url
            ansicht.load(QUrl(url))
        zeigen = sichtbar and b > 20 and h > 20
        ansicht.setGeometry(x, y, b, h)
        ansicht.setVisible(zeigen)
        if zeigen:
            ansicht.raise_()  # immer ueber der Panel-Seite liegen

    def _neue_adresse(self, wid: str, ansicht: QWebEngineView, url: QUrl) -> None:
        ansicht.ziel = url.toString()  # damit die Rueckmeldung aus JS nicht neu laedt
        self.bruecke.webUrl.emit(wid, ansicht.ziel)

    def weg(self, wid: str) -> None:
        ansicht = self.ansichten.pop(wid, None)
        if ansicht:
            ansicht.deleteLater()

    def aktion(self, wid: str, aktion: str) -> None:
        ansicht = self.ansichten.get(wid)
        if not ansicht:
            return
        if aktion == "zurueck":
            ansicht.back()
        elif aktion == "neu":
            ansicht.reload()
        elif aktion == "extern":
            webbrowser.open(ansicht.url().toString())

    def alle(self, sichtbar: bool) -> None:
        """Fuer Dialoge im Panel (z. B. Widget-Katalog), die sonst unter den Ansichten laegen."""
        for ansicht in self.ansichten.values():
            ansicht.setVisible(sichtbar and ansicht.width() > 20)


class LogSeite(QWebEnginePage):
    """Schreibt JavaScript-Warnungen und -Fehler ins Klaus-Log."""

    def javaScriptConsoleMessage(self, stufe, text, zeile, quelle) -> None:
        if stufe != QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel:
            print(f"[JS] {Path(quelle).name}:{zeile} {text}")


# Eigener Name (KLAUS_NAME, z. B. "Lumine") und eigener Nutzername (KLAUS_NUTZER): ueberall in der Oberflaeche statt
# "Klaus"/"Nikola" - Texte, Tooltips, Platzhalter, auch was spaeter dazukommt. Nur sichtbarer Text; Code, Klassen, IDs bleiben.
NAME_SKRIPT = """
(() => {
  const PAARE = %s.map(([muster, ersatz]) => [new RegExp(muster, "g"), ersatz]);
  const ersetze = s => PAARE.reduce((t, [r, e]) => t.replace(r, e), s);
  const knoten = n => {
    if (n.nodeType === 3) { const t = ersetze(n.nodeValue); if (t !== n.nodeValue) n.nodeValue = t; return; }
    if (n.nodeType !== 1 || n.tagName === "SCRIPT" || n.tagName === "STYLE") return;
    for (const a of ["title", "placeholder", "aria-label"]) {
      const v = n.getAttribute(a);
      if (v && ersetze(v) !== v) n.setAttribute(a, ersetze(v));
    }
    n.childNodes.forEach(knoten);
  };
  const los = () => {
    document.title = ersetze(document.title);
    const stil = document.createElement("style");
    stil.textContent = %s;
    document.head.append(stil);
    const logo = document.querySelector(".logo");
    if (logo && %s) logo.textContent = %s;   // K.L.A.U.S. im Kopf (einzelne Buchstaben-Knoten) -> eigener Name
    knoten(document.body);
    new MutationObserver(liste => liste.forEach(m => m.type === "childList" ? m.addedNodes.forEach(knoten) : knoten(m.target)))
      .observe(document.body, {childList: true, subtree: true, characterData: true,
                               attributes: true, attributeFilter: ["title", "placeholder", "aria-label"]});
  };
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", los) : los();
})();
"""


def name_skript() -> str:
    """JavaScript fuer die Web-Seiten - "" wenn alles beim Standard (Klaus / Nikola) bleibt."""
    paare, stil, logo = [], "", ""
    if identitaet.NAME != identitaet.STANDARD_NAME:
        logo = identitaet.NAME.upper()
        gross = identitaet.NAME.upper()
        paare += [[r"\bKlaus\b", identitaet.NAME], [r"\bKLAUS\b", gross], [r"K\.L\.A\.U\.S\.", ".".join(gross) + "."]]
        stil = (f".klaus::before {{ content: {json.dumps(gross)} !important; }} "
                ".boot-unter { visibility: hidden; }")   # "KLESRO LOGISTIC AUTONOMOUS UTILITY SYSTEM" passt nur zu K.L.A.U.S.
    if identitaet.fremder_nutzer():
        paare += [[r"\bNikola\b", identitaet.NUTZER], [r"\bNIKOLA\b", identitaet.NUTZER.upper()]]
        stil += " .logo-unter { display: none; }"   # "KLESRO WEB · GÖPPINGEN" ist Nikolas Firma
    if not paare:
        return ""
    return NAME_SKRIPT % (json.dumps(paare, ensure_ascii=False), json.dumps(stil), json.dumps(logo), json.dumps(logo))


def _name_einsetzen(seite: QWebEnginePage) -> None:
    quelle = name_skript()
    if not quelle:
        return
    skript = QWebEngineScript()
    skript.setName("klaus-name")
    skript.setSourceCode(quelle)
    skript.setInjectionPoint(QWebEngineScript.DocumentReady)
    skript.setWorldId(QWebEngineScript.MainWorld)
    skript.setRunsOnSubFrames(False)
    seite.scripts().insert(skript)


def _web_ansicht(ansicht: QWebEngineView, seite: str, bruecke: WebBruecke, abfrage: str = "") -> None:
    ansicht.setPage(LogSeite(ansicht))
    _name_einsetzen(ansicht.page())
    kanal = QWebChannel(ansicht.page())
    kanal.registerObject("klaus", bruecke)
    ansicht.page().setWebChannel(kanal)
    ansicht.page().setBackgroundColor(Qt.transparent)
    ansicht.setContextMenuPolicy(Qt.NoContextMenu)
    url = QUrl.fromLocalFile(str(WEB_DIR / seite))
    if abfrage:
        url.setQuery(abfrage)
    elif os.getenv("KLAUS_CORE_DEBUG") in ("1", "graph"):  # Debug-Panel offen + Demo-Ablauf (graph = Gedaechtnis-Graph)
        url.setQuery(f"debug={os.getenv('KLAUS_CORE_DEBUG')}")
    ansicht.load(url)
    ansicht._kanal, ansicht._bruecke = kanal, bruecke  # Referenzen halten, sonst raeumt Python sie weg


# ------------------------------------------------------------------ Desktop-Panel
class DesktopPanel(QWidget):
    """Vollbild ueber dem echten Desktop, aber immer unter allen anderen Fenstern.

    Ein schlichter Container: unten die Panel-Seite, darueber als Geschwister die
    Browser-Ansichten der Web-Widgets. (Als Kinder *in* der Panel-Seite wuerden sie
    auf dem Bildschirm von ihr uebermalt.)
    """

    def __init__(self, bruecke: WebBruecke) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnBottomHint)
        self.setWindowTitle("Klaus Desktop")
        self.ansicht = QWebEngineView(self)
        _web_ansicht(self.ansicht, "dashboard.html", bruecke)
        bruecke.fenster = self
        bruecke.web = WebWidgets(self, bruecke)
        self.an = True
        self.wache = QTimer(self)  # "Desktop anzeigen" (Win+D) minimiert auch uns -> zurueckholen
        self.wache.timeout.connect(self._pruefe)
        self.wache.start(1500)

    @staticmethod
    def _flaeche():
        # Bei ausgeblendeter Taskleiste den ganzen Bildschirm nutzen
        bildschirm = QApplication.primaryScreen()
        return bildschirm.geometry() if taskleiste_versteckt() else bildschirm.availableGeometry()

    def einschalten(self, an: bool) -> None:
        self.an = an
        if an:
            self.setGeometry(self._flaeche())
            self.showNormal()
        else:
            self.hide()

    def _pruefe(self) -> None:
        if not self.an:
            return
        bild = self._flaeche()
        if self.isMinimized() or not self.isVisible() or self.geometry() != bild:
            self.setGeometry(bild)
            self.showNormal()

    def resizeEvent(self, ereignis) -> None:
        self.ansicht.setGeometry(self.rect())
        super().resizeEvent(ereignis)

    def nativeEvent(self, typ, nachricht):
        if typ in (b"windows_generic_MSG", "windows_generic_MSG"):
            msg = wintypes.MSG.from_address(int(nachricht))
            if msg.message == WM_WINDOWPOSCHANGING:
                pos = WINDOWPOS.from_address(msg.lParam)
                pos.hwndInsertAfter = HWND_BOTTOM  # nie vor andere Fenster springen
                pos.flags &= ~SWP_NOZORDER
        return super().nativeEvent(typ, nachricht)


# ------------------------------------------------------------------ Zweiter Bildschirm
def _zweiter_bildschirm():
    """Der Bildschirm, der nicht der Hauptbildschirm ist (oder None)."""
    haupt = QApplication.primaryScreen().name()   # Namen vergleichen: PySide liefert jedes Mal neue Objekte
    return next((s for s in QApplication.screens() if s.name() != haupt), None)


def _vollbild_auf(bildschirm) -> bool:
    """Laeuft gerade ein echtes Vollbild-Programm (Spiel, Praesentation)? Dann nicht stoeren.
    Windows-eigene Erkennung - ein nur maximiertes Fenster (z. B. VS Code bei versteckter Taskleiste) zaehlt nicht."""
    try:
        import win32api
        import win32gui
        import win32process

        zustand = ctypes.c_int(0)
        ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(zustand))
        if zustand.value not in (2, 3, 4):  # 2 = "Vollbild-App" (auch unser Panel), 3 = exklusives D3D-Vollbild, 4 = Praesentation
            return False
        h = win32gui.GetForegroundWindow()
        eigenes = not h or win32process.GetWindowThreadProcessId(h)[1] == os.getpid()
        if eigenes:
            return zustand.value in (3, 4)
        monitor = win32api.GetMonitorInfo(win32api.MonitorFromWindow(h, 2))
        if bildschirm is not None and monitor["Device"] != bildschirm.name():
            return False             # das Vollbild laeuft auf dem anderen Bildschirm (Spiel vorne, Bildschirm 2 frei)
        if zustand.value in (3, 4):
            return True
        if ctypes.windll.user32.IsZoomed(h):
            return False             # nur maximiert (z. B. VS Code) -> kein Vollbild
        if win32gui.GetClassName(h) in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            return False             # Windows-Desktop/Taskleiste ist bildschirmgross, aber kein Spiel
        return tuple(win32gui.GetWindowRect(h)) == tuple(monitor["Monitor"])  # randloses Vollbild (Spiel im Fenstermodus)
    except Exception:
        return False


class ZweitFenster(QWidget):
    """Holo-Buehne auf dem zweiten Bildschirm: erscheint nur, wenn Klaus Platz braucht (grosse Ansichten oder
    Hauptbildschirm voll), liegt halbtransparent ueber den Programmen dort und verschwindet, wenn alles zu ist."""

    def __init__(self, bruecke: WebBruecke) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Klaus Bildschirm 2")
        self.ansicht = QWebEngineView(self)
        _web_ansicht(self.ansicht, "dashboard.html", bruecke, abfrage="zweit=1")
        bruecke.fenster = self
        self.mini = False   # Spielmodus: das Panel ist weg -> notfalls auf dem Hauptbildschirm ueber dem Spiel zeigen

    def ziel(self):
        """Bildschirm 2, wenn dort kein Vollbild laeuft; im Spielmodus sonst der Hauptbildschirm."""
        b = _zweiter_bildschirm()
        if b is not None and not _vollbild_auf(b):
            return b
        return QApplication.primaryScreen() if self.mini else None

    def verfuegbar(self) -> bool:
        return self.ziel() is not None

    def zeigen(self) -> None:
        b = self.ziel()
        if not b:
            return
        self.setGeometry(b.geometry())
        self.show()
        self.raise_()

    def resizeEvent(self, ereignis) -> None:
        self.ansicht.setGeometry(self.rect())
        super().resizeEvent(ereignis)


# ------------------------------------------------------------------ Orb-Overlay
class PcNutzungHinweis(QWidget):
    """Leiste oben auf dem Hauptbildschirm, solange Klaus Shell/Browser/Bildschirm benutzt (pc_zugriff.py).
    Immer im Vordergrund, klick-durchlaessig, ohne WebView (kaum CPU)."""

    def __init__(self) -> None:
        from PySide6.QtWidgets import QLabel, QHBoxLayout

        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.label = QLabel(self)
        self.label.setStyleSheet("QLabel { background: rgba(24, 25, 28, 250); color: #f4ede1; border: 1px solid #bd805a;"
                                 " border-radius: 10px; padding: 10px 18px; font: 600 13px 'Segoe UI'; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.label)

    @Slot(str)
    def setze(self, roh: str) -> None:
        d = json.loads(roh)
        if not d.get("aktiv"):
            self.hide()
            return
        teile = ["●  Klaus benutzt gerade den PC"]
        if d.get("arten"):
            teile.append(" · ".join(d["arten"]))
        if d.get("rest") is not None:
            teile.append(f"noch {d['rest'] // 60}:{d['rest'] % 60:02d}")
        self.label.setText("   ·   ".join(teile) + "   ·   /stop beendet alles")
        self.adjustSize()
        bild = QApplication.primaryScreen().geometry()
        self.move(bild.center().x() - self.width() // 2, bild.top() + 6)
        if not self.isVisible():
            self.show()
        self.raise_()


class OrbOverlay(QWebEngineView):
    """Der Orb in der Bildschirmmitte, wenn du in einer anderen App bist: durchsichtig, klick-durchlaessig.
    Gleicher Orb wie im Panel (web/klaus.js), damit beide gleich aussehen."""

    BREITE, HOEHE = 360, 390

    def __init__(self, bruecke: WebBruecke) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.resize(self.BREITE, self.HOEHE)
        self.bruecke = bruecke
        _web_ansicht(self, "overlay.html", bruecke)
        self.ausblenden = QTimer(self, singleShot=True, interval=250)  # nach der Ausblend-Animation
        self.ausblenden.timeout.connect(self.hide)

    def setze_zustand(self, zustand: str) -> None:
        if zustand != "aus":
            self.ausblenden.stop()
            if not self.isVisible():
                bild = QApplication.primaryScreen().availableGeometry()
                self.move(bild.right() - self.BREITE - 24, bild.bottom() - self.HOEHE - 24)
                self.show()
        elif self.isVisible():
            self.ausblenden.start()
        self.bruecke.zustand.emit(zustand)

    def setze_text(self, text: str) -> None:
        self.bruecke.untertitel.emit(text)

    def setze_pegel(self, pegel: float) -> None:
        self.bruecke.pegel.emit(pegel)


# ------------------------------------------------------------------ Spielmodus: Mini-Orb
class MiniBlase(QWidget):
    """Sprechblase neben dem Mini-Orb (z. B. Twitch-Chat). Klick-durchlaessig, verschwindet nach ein paar Sekunden."""

    def __init__(self) -> None:
        from PySide6.QtWidgets import QHBoxLayout, QLabel

        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
                            | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.label = QLabel(self)
        self.label.setTextFormat(Qt.PlainText)   # Chat-Text ist fremd: nie als HTML darstellen
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(320)
        self.label.setStyleSheet("QLabel { background: rgba(24, 25, 28, 235); color: #f4ede1; border: 1px solid #bd805a;"
                                 " border-radius: 10px; padding: 7px 12px; font: 600 12px 'Segoe UI'; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.label)
        self.weg = QTimer(self, singleShot=True, interval=7000)
        self.weg.timeout.connect(self.hide)

    def zeige(self, text: str, orb: QWidget) -> None:
        self.label.setText(text[:220])
        self.adjustSize()
        g = orb.frameGeometry()
        bild = (orb.screen() or QApplication.primaryScreen()).availableGeometry()
        links = g.center().x() > bild.center().x()   # Orb rechts -> Blase links daneben
        self.move(g.left() - self.width() - 6 if links else g.right() + 6, g.center().y() - self.height() // 2)
        self.show()
        self.weg.start()


class MiniOrb(QWidget):
    """Spielmodus: statt Panel nur ein kleiner Kreis, immer im Vordergrund, frei verschiebbar.
    Knopf unten rechts = Mikrofon aus/an, Rechtsklick = Menue (Panel zurueck nur dort - ein Doppelklick passierte
    beim Zocken versehentlich, und das Panel liegt hinter dem Spiel).
    Reines QPainter (keine Browser-Engine) und nur Neuzeichnen bei Aenderungen -> kostet beim Zocken praktisch nichts."""

    GROESSE, ORB = 104, 96   # Fenster / Reaktor (gezeichnet in 600er-Einheiten wie web/klaus.js)
    # Farben wie im Panel (klaus.js, Thema gold): Hauptfarbe, Ausfuehren gruen, Fehler rot, gedimmt bei stumm/Mikro aus
    HAUPT = (213, 186, 133)   # wird von setze_thema() auf das gewaehlte Design / die eigene Farbe gesetzt
    alle: list["MiniOrb"] = []
    FARBEN = {"aktion": (157, 197, 170), "fertig": (157, 197, 170), "fehler": (237, 156, 145),
              "freigabe": (226, 184, 119)}
    GEDIMMT = (120, 120, 128)
    TEMPO = {"aus": 1, "start": 1.4, "hoeren": 1.6, "denken": 7, "sprechen": 2, "aktion": 3.2, "freigabe": 0.6, "fehler": 0.4}
    mute_klick = Signal()    # Mikrofon aus/an
    stumm_klick = Signal()   # Stumm an/aus
    zurueck = Signal()       # Spielmodus beenden

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("Klaus Mini")
        self.setFixedSize(self.GROESSE, self.GROESSE)
        self.setToolTip("Klaus · ziehen = verschieben · Knopf = Mikro aus/an · Rechtsklick = Menü (Stumm, Panel zurück)")
        self.zustand, self.pegel, self.pegel_ziel, self.stumm, self.mikro_aus = "aus", 0.0, 0.0, False, False
        self.t = self.dreh_a = self.dreh_b = self.dreh_c = 0.0
        self._skala = None   # vorgezeichnete statische Teile (Tunnel, Strahlen, Skala)
        self._druck = self._start = None
        self._gezogen = False
        self.blase = MiniBlase()
        MiniOrb.HAUPT = thema_farbe(daten.lade_einstellungen().get("thema", "jarvis"))
        MiniOrb.alle.append(self)
        self.dreh = QTimer(self, interval=50)   # 20 Bilder/s (~2,8 ms je Bild), nur solange Klaus hoert/denkt/spricht; in Ruhe steht das Bild
        self.dreh.timeout.connect(self._drehen)
        self.oben = QTimer(self, interval=3000)  # randlose Spiele schieben sich gern davor -> wieder nach vorne
        self.oben.timeout.connect(self._nach_oben)

    # ---------------------------------------------------------------- an/aus
    def zeigen(self) -> None:
        pos = daten.lade_einstellungen().get("mini_pos")
        bild = QApplication.primaryScreen().availableGeometry()
        if not (isinstance(pos, list) and len(pos) == 2 and any(s.availableGeometry().contains(pos[0] + 40, pos[1] + 40)
                                                                  for s in QApplication.screens())):
            pos = [bild.right() - self.GROESSE - 20, bild.top() + 90]   # Standard: oben rechts
        self.move(pos[0], pos[1])
        self.show()
        self._nach_oben()
        self.oben.start()

    def verstecken(self) -> None:
        self.oben.stop()
        self.dreh.stop()
        self.blase.hide()
        self.hide()

    def _nach_oben(self) -> None:
        # HWND_TOPMOST, ohne Fokus zu nehmen (SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
        ctypes.windll.user32.SetWindowPos(int(self.winId()), -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)

    # ---------------------------------------------------------------- Zustand
    def _aktiv(self) -> bool:
        return self.zustand != "aus" or self.pegel_ziel > 0.02 or self.pegel > 0.02

    def _takt_pruefen(self) -> None:
        if self.isVisible() and self._aktiv():
            if not self.dreh.isActive():
                self.dreh.start()
        else:
            self.dreh.stop()
            self.update()   # Ruhebild

    def setze_zustand(self, zustand: str) -> None:
        self.zustand = zustand
        self._takt_pruefen()

    def setze_pegel(self, pegel: float) -> None:
        self.pegel_ziel = max(0.0, min(1.0, pegel))
        if self.isVisible() and not self.dreh.isActive() and self._aktiv():
            self.dreh.start()

    def setze_stumm(self, an: bool) -> None:
        self.stumm = an
        self.update()

    def setze_mikro(self, aus: bool) -> None:
        self.mikro_aus = aus
        self.update()

    def sprechblase(self, text: str) -> None:
        if self.isVisible():
            self.blase.zeige(text, self)

    def _drehen(self) -> None:
        dt = 0.05
        self.t += dt
        self.pegel += (self.pegel_ziel - self.pegel) * 0.3
        tempo = self.TEMPO.get(self.zustand, 1)
        self.dreh_a += dt * 0.10 * tempo
        self.dreh_b -= dt * 0.16 * tempo
        self.dreh_c += dt * 0.42 * tempo
        if not self._aktiv():
            self.dreh.stop()
        self.update()

    # ---------------------------------------------------------------- Zeichnen
    def _knopf(self):
        from PySide6.QtCore import QRectF
        return QRectF(self.GROESSE - 31, self.GROESSE - 31, 27, 27)

    def _farbe(self) -> tuple:
        if self.stumm or self.mikro_aus:
            return self.GEDIMMT
        if self.zustand == "sprechen":   # wie im Panel: Hauptfarbe etwas dunkler
            return tuple(int(w * 0.88) for w in self.HAUPT)
        return self.FARBEN.get(self.zustand, self.HAUPT)

    @staticmethod
    def _rgba(farbe: tuple, a: float, hell: float = 0.0) -> QColor:
        r, g, b = (int(w + (255 - w) * hell) for w in farbe)
        return QColor(r, g, b, int(255 * max(0.0, min(1.0, a))))

    def _statisch(self, px: int):
        """Tunnel-Ringe, Lichtstrahlen und Skala (weiss) einmal vorzeichnen - wie baueStatisch() in klaus.js."""
        import math

        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QBrush, QPixmap

        if self._skala is not None and self._skala.width() == px:
            return self._skala
        bild = QPixmap(px, px)
        bild.fill(Qt.transparent)
        q = QPainter(bild)
        q.setRenderHint(QPainter.Antialiasing)
        q.scale(px / 600, px / 600)
        m, dick = QPointF(300, 300), 600 / px   # dick = 1 Bildpunkt (feine Linien bleiben im Kleinen sichtbar)
        q.setBrush(Qt.NoBrush)
        for i in range(9):
            k = i / 9
            r = 62 + 214 * (1 - k) ** 1.5
            q.setPen(QPen(QColor(255, 255, 255, int(255 * (0.08 + k * 0.16))), dick))
            q.drawEllipse(m, r, r)
        strahl = QRadialGradient(m, 250)
        strahl.setColorAt(30 / 250, QColor(255, 255, 255, 150))
        strahl.setColorAt(0.45, QColor(255, 255, 255, 30))
        strahl.setColorAt(1.0, QColor(255, 255, 255, 0))
        for n, b in ((72, 0.8 * dick), (18, 2.2 * dick)):
            q.setPen(QPen(QBrush(strahl), b))
            for i in range(n):
                a = i / n * 2 * math.pi + (0.09 if n == 18 else 0)
                innen = 34 + (i % 3) * 8
                q.drawLine(QPointF(300 + math.cos(a) * innen, 300 + math.sin(a) * innen),
                           QPointF(300 + math.cos(a) * 250, 300 + math.sin(a) * 250))
        for i in range(120):
            lang = i % 10 == 0
            a, l = i / 120 * 2 * math.pi, (22 if lang else 9)
            q.setPen(QPen(QColor(255, 255, 255, 110 if lang else 45), dick))
            q.drawLine(QPointF(300 + math.cos(a) * (284 - l), 300 + math.sin(a) * (284 - l)),
                       QPointF(300 + math.cos(a) * 284, 300 + math.sin(a) * 284))
        q.end()
        self._skala = bild
        return bild

    def _segring(self, p, r, breite, n, fuell, dreh, farbe, alpha, hell=0.0) -> None:
        import math

        from PySide6.QtCore import QRectF

        feld, schritt = QRectF(300 - r, 300 - r, 2 * r, 2 * r), 360 / n
        for i in range(n):
            p.setPen(QPen(self._rgba(farbe, alpha * (1 if i % 6 == 0 else 0.55), hell), breite, Qt.SolidLine, Qt.FlatCap))
            p.drawArc(feld, int((-math.degrees(dreh) - i * schritt) * 16), int(-schritt * fuell * 16))

    def _boegen(self, p, r, anzahl, spanne, dreh, breite, farbe, alpha, hell=0.0) -> None:
        import math

        from PySide6.QtCore import QRectF

        feld = QRectF(300 - r, 300 - r, 2 * r, 2 * r)
        for b, a in ((breite * 4, alpha * 0.14), (breite, alpha)):
            p.setPen(QPen(self._rgba(farbe, a, hell), b, Qt.SolidLine, Qt.FlatCap))
            for i in range(anzahl):
                start = -math.degrees(dreh + i * 2 * math.pi / anzahl)
                p.drawArc(feld, int(start * 16), int(-math.degrees(spanne) * 16))

    def _roehre(self, p, r, staerke, farbe) -> None:
        from PySide6.QtCore import QPointF

        p.setBrush(Qt.NoBrush)
        for b, a, hell in ((36, 0.08, 0), (16, 0.22, 0), (7, 0.75, 0.35), (2.5, 0.95, 0.85)):
            p.setPen(QPen(self._rgba(farbe, a, hell), b * staerke))
            p.drawEllipse(QPointF(300, 300), r, r)

    def _reaktor(self, p) -> None:
        """Reaktor-Kern wie im Panel (web/klaus.js zeichne): Tunnel, Plattenring, gluehendes Portal, weisser Kern."""
        import math

        from PySide6.QtCore import QPointF, QRectF

        dpr = self.devicePixelRatioF()
        farbe, t, z, m = self._farbe(), self.t, self.zustand, QPointF(300, 300)
        if z in ("hoeren", "start"):
            pu = 0.9 + self.pegel * 0.6
        elif z == "sprechen":
            pu = 0.95 + self.pegel * 0.5
        elif z == "denken":
            pu = 1.05 + 0.1 * math.sin(t * 9)
        elif z in ("aktion", "fertig"):
            pu = 1.1 + 0.05 * math.sin(t * 4)
        elif z == "fehler":
            pu = 0.8
        else:
            pu = 1.0
        p.save()
        p.scale(self.ORB / 600, self.ORB / 600)
        p.setCompositionMode(QPainter.CompositionMode_Plus)   # "lighter" wie im Canvas
        p.setPen(Qt.NoPen)
        g = QRadialGradient(m, 290)
        g.setColorAt(0, self._rgba(farbe, 0.35 * pu))
        g.setColorAt(0.5, self._rgba(farbe, 0.08))
        g.setColorAt(1, self._rgba(farbe, 0))
        p.setBrush(g)
        p.drawEllipse(m, 290, 290)
        p.save()
        p.translate(300, 300)
        p.rotate(math.degrees(self.dreh_a * 0.3))
        p.translate(-300, -300)
        p.drawPixmap(QRectF(0, 0, 600, 600), self._statisch(max(64, round(self.ORB * dpr))), QRectF())
        p.restore()
        if z in ("denken", "aktion"):   # Abtast-Kegel
            from PySide6.QtGui import QConicalGradient
            kegel = QConicalGradient(m, -math.degrees(self.dreh_c * 2))
            kegel.setColorAt(0, self._rgba(farbe, 0.3))
            kegel.setColorAt(0.12, self._rgba(farbe, 0))
            kegel.setColorAt(1, self._rgba(farbe, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(kegel)
            p.drawEllipse(m, 270, 270)
        dick = 600 / self.ORB   # 1 Bildpunkt
        self._segring(p, 244, 12, 24, 0.86, self.dreh_a, (255, 255, 255), 0.09)
        self._segring(p, 244, max(1.2, dick), 24, 0.86, self.dreh_a, farbe, 0.55, 0.5)
        self._segring(p, 206, 6, 48, 0.6, -self.dreh_b, farbe, 0.3 + 0.12 * pu, 0.2)
        self._segring(p, 96, max(2, dick), 36, 0.5, self.dreh_b * 1.6, farbe, 0.5, 0.4)
        self._boegen(p, 226, 3, 0.7, self.dreh_b * 0.7, max(2, dick * 1.4), farbe, 0.75)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 150, 60, int(255 * (0.55 + 0.25 * math.sin(t * 2)))))   # Warnlichter
        for i in range(8):
            a = self.dreh_a + i / 8 * 2 * math.pi + 0.12
            p.drawEllipse(QPointF(300 + math.cos(a) * 244, 300 + math.sin(a) * 244), 6, 6)
        self._roehre(p, 150 * (0.97 + pu * 0.03), 0.8 + pu * 0.25, farbe)
        self._roehre(p, 122, 0.35, farbe)
        self._boegen(p, 150, 4, 0.5, -self.dreh_c * 1.5, 3.5, farbe, 0.6, 0.9)
        r = 120 * pu
        g = QRadialGradient(m, r)
        g.setColorAt(0, QColor(255, 255, 255, 255))
        g.setColorAt(0.14, QColor(255, 255, 255, 230))
        g.setColorAt(0.32, self._rgba(farbe, 0.75, 0.45))
        g.setColorAt(0.65, self._rgba(farbe, 0.18))
        g.setColorAt(1, self._rgba(farbe, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(m, r, r)
        p.restore()

    def paintEvent(self, _ereignis) -> None:
        from PySide6.QtCore import QPointF, QRectF

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._reaktor(p)
        farbe = QColor(*self._farbe())
        # Mute-Knopf
        kn = self._knopf()
        p.setPen(QPen(QColor(255, 90, 90) if self.mikro_aus else farbe, 1.6))
        p.setBrush(QColor(170, 40, 40, 245) if self.mikro_aus else QColor(24, 25, 28, 240))
        p.drawEllipse(kn)
        c = kn.center()
        p.setPen(QPen(QColor(244, 237, 225), 1.7))
        p.setBrush(QColor(244, 237, 225))
        p.drawRoundedRect(QRectF(c.x() - 2.6, c.y() - 7.5, 5.2, 9), 2.6, 2.6)   # Mikrofon
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(c.x() - 5, c.y() - 4.5, 10, 9), 200 * 16, 140 * 16)
        p.drawLine(QPointF(c.x(), c.y() + 4.5), QPointF(c.x(), c.y() + 7))
        if self.mikro_aus:
            p.setPen(QPen(QColor(255, 255, 255), 2))
            p.drawLine(QPointF(c.x() - 6, c.y() + 6), QPointF(c.x() + 6, c.y() - 6))
        p.end()

    # ---------------------------------------------------------------- Maus
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._druck, self._start, self._gezogen = e.globalPosition().toPoint(), self.pos(), False
        elif e.button() == Qt.RightButton:
            self._menue(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e) -> None:
        if self._druck is None:
            return
        weg = e.globalPosition().toPoint() - self._druck
        if weg.manhattanLength() > 4:
            self._gezogen = True
        if self._gezogen:
            self.move(self._start + weg)
            self.blase.hide()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.LeftButton or self._druck is None:
            return
        self._druck = None
        if self._gezogen:
            daten.speichere_einstellung("mini_pos", [self.x(), self.y()])
        elif self._knopf().contains(e.position()):
            self.mute_klick.emit()

    def _menue(self, wo) -> None:
        from PySide6.QtWidgets import QMenu

        menue = QMenu()
        menue.addAction("Mikrofon an" if self.mikro_aus else "Mikrofon aus", self.mute_klick.emit)
        menue.addAction("Wieder an (nicht stumm)" if self.stumm else "Stumm", self.stumm_klick.emit)
        menue.addSeparator()
        menue.addAction("Panel zurück (Spielmodus aus)", self.zurueck.emit)
        menue.exec(wo)


# ------------------------------------------------------------------ Chat-Fenster
class ChatFenster(QWebEngineView):
    """HUD-Popup ohne Windows-Rahmen; erscheint nur, wenn du gerade in einer anderen App bist."""

    BREITE, HOEHE = 420, 600

    def __init__(self, bruecke: WebBruecke, symbol) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("Klaus")
        self.setWindowIcon(symbol)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.resize(self.BREITE, self.HOEHE)
        _web_ansicht(self, "chat.html", bruecke)
        bruecke.fenster = self
        self.page().setBackgroundColor(Qt.black)

    def zeige(self) -> None:
        if not self.isVisible():
            bild = QApplication.primaryScreen().availableGeometry()
            self.move(bild.right() - self.BREITE - 24, bild.bottom() - self.HOEHE - 24)
        self.showNormal()
        self.raise_()

    def closeEvent(self, ereignis) -> None:
        ereignis.ignore()
        self.hide()
