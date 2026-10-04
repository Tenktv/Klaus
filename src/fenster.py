"""
Klaus - Fenster
    DesktopPanel  ersetzt den Desktop: Vollbild, liegt immer ganz unten hinter allen Apps
    ChatFenster   das Klaus-Fenster fuer Gespraeche, mit Maus und Tastatur bedienbar
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
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileIconProvider, QWidget

import apps
import daten

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
    untertitel = Signal(str)  # Text unter dem Orb im Overlay
    sichtbar = Signal(bool)  # False = Panel ist von einem Vollbild-Fenster verdeckt -> Animationen pausieren
    stummStatus = Signal(bool)  # Klaus stumm (hoert nur noch auf "Klaus, wieder an")
    mikroStatus = Signal(bool)  # Mikrofon komplett aus
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

    @Slot(str)
    def vergissEintrag(self, eintrag_id: str) -> None:
        import gehirn

        gehirn.vergiss_id(int(eintrag_id))
        self.lade("gedaechtnis", "")

    @Slot(str)
    def papierkorb(self, pfad: str) -> None:
        import dateien

        print(f"[Klaus] Papierkorb: {dateien.in_papierkorb(pfad)}")
        self.lade("projekte", "")

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


# Design-Varianten: (Hauptfarbe, Zweitfarbe beim Nachdenken). Die vollen Paletten stehen in web/klaus.js.
THEMEN = {
    "jarvis": ((0, 229, 255), (255, 179, 0)),
    "ironman": ((255, 59, 48), (255, 196, 0)),
    "matrix": ((0, 255, 120), (180, 255, 0)),
    "synthwave": ((190, 90, 255), (255, 60, 170)),
    "gold": ((255, 176, 0), (255, 90, 40)),
    "arktis": ((200, 235, 255), (120, 180, 255)),
}


def setze_thema(name: str) -> str:
    """Design wechseln, speichern und an alle offenen Klaus-Seiten melden. "weiter" = naechstes."""
    if name == "weiter":
        namen = list(THEMEN)
        jetzt = daten.lade_einstellungen().get("thema", "jarvis")
        name = namen[(namen.index(jetzt) + 1) % len(namen)] if jetzt in namen else namen[0]
    if name not in THEMEN:
        return ""
    daten.speichere_einstellung("thema", name)
    for b in WebBruecke.alle:
        b.thema.emit(name)
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


def _web_ansicht(ansicht: QWebEngineView, seite: str, bruecke: WebBruecke) -> None:
    ansicht.setPage(LogSeite(ansicht))
    kanal = QWebChannel(ansicht.page())
    kanal.registerObject("klaus", bruecke)
    ansicht.page().setWebChannel(kanal)
    ansicht.page().setBackgroundColor(Qt.transparent)
    ansicht.setContextMenuPolicy(Qt.NoContextMenu)
    ansicht.load(QUrl.fromLocalFile(str(WEB_DIR / seite)))
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


# ------------------------------------------------------------------ Orb-Overlay
class OrbOverlay(QWebEngineView):
    """Der Orb in der Bildschirmmitte, wenn du in einer anderen App bist: durchsichtig, klick-durchlaessig.
    Gleicher Orb wie im Panel (web/klaus.js), damit beide gleich aussehen."""

    BREITE, HOEHE = 640, 660

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
                self.move(bild.center().x() - self.BREITE // 2, bild.center().y() - self.HOEHE // 2)
                self.show()
        elif self.isVisible():
            self.ausblenden.start()
        self.bruecke.zustand.emit(zustand)

    def setze_text(self, text: str) -> None:
        self.bruecke.untertitel.emit(text)

    def setze_pegel(self, pegel: float) -> None:
        self.bruecke.pegel.emit(pegel)


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
