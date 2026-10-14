"""
Klaus - Hintergrund-App
Verbindet Assistent (assistent.py), Orb-Overlay, Desktop-Panel und
Klaus-Fenster (fenster.py) und sitzt mit einem Symbol in der Taskleiste.

    "Klaus, oeffne Steam / TFT / CS2 / Edge"  -> App, Webseite oder Ordner
    "Klaus, such nach Wetter Goeppingen"      -> Google-Suche
    "Klaus, Website fuer Schreinerei Maier"   -> Planungsgespraech, danach baut Claude
    "Klaus, wie spaet ist es?"                -> kurze Antwort, danach hoert er weiter zu
    "Klaus" (allein)                          -> "Ja?" und wartet auf den Befehl

Start ohne Konsolenfenster:
    .venv/Scripts/pythonw.exe src/klaus_app.py
Optionen:
    --dry-run      Claude nicht wirklich starten
    --ohne-panel   Desktop-Panel beim Start nicht anzeigen
"""

import ctypes
import json
import re
import time
import traceback
from ctypes import wintypes
import os
import subprocess
import sys
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_PATH = BASE_DIR / "data" / "klaus.log"

class _SchwaerzendesLog:
    """Schreibt ins Log, aber nie Schluessel/Passwoerter: Werte aus .env (*KEY, *PASS, *TOKEN, *SECRET) und typische Muster."""

    MUSTER = re.compile(r"AIza[0-9A-Za-z_\-]{30,}|AQ\.[0-9A-Za-z_\-]{20,}|tvly-[0-9A-Za-z_\-]{20,}|sk-[0-9A-Za-z_\-]{20,}|ghp_[0-9A-Za-z]{30,}")

    def __init__(self, datei) -> None:
        self.datei = datei
        self.geheim = []
        try:
            for zeile in (BASE_DIR / ".env").read_text(encoding="utf-8").splitlines():
                name, _, wert = zeile.partition("=")
                if re.search(r"(KEY|PASS|TOKEN|SECRET)", name.upper()) and len(wert.strip()) >= 6:
                    self.geheim.append(wert.strip().strip('"'))
        except OSError:
            pass

    def write(self, text: str) -> int:
        for g in self.geheim:
            text = text.replace(g, "***")
        return self.datei.write(self.MUSTER.sub("***", text))

    def flush(self) -> None:
        self.datei.flush()

    def __getattr__(self, name):
        return getattr(self.datei, name)


# Ohne Konsole (pythonw) gibt es kein stdout -> alles ins Log (geschwaerzt)
if sys.stdout is None or sys.stderr is None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _log = _SchwaerzendesLog(open(LOG_PATH, "a", encoding="utf-8", buffering=1))
    sys.stdout = sys.stderr = _log

from PySide6.QtCore import QAbstractNativeEventFilter, QLockFile, QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import apps
import daten
import gehirn
from assistent import Assistent, Bruecke
from daten import lade_einstellungen, speichere_einstellung
from fenster import (ChatFenster, DesktopPanel, OrbOverlay, PcNutzungHinweis, WebBruecke, ZweitFenster, setze_thema, taskleiste_verstecken,
                     taskleiste_versteckt)

AUTOSTART_LNK = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup\Klaus.lnk"


def tray_symbol() -> QIcon:
    bild = QPixmap(64, 64)
    bild.fill(Qt.transparent)
    p = QPainter(bild)
    p.setRenderHint(QPainter.Antialiasing)
    g = QRadialGradient(26, 24, 30)
    g.setColorAt(0, QColor(255, 255, 255))
    g.setColorAt(0.4, QColor(0, 220, 255))
    g.setColorAt(1, QColor(110, 60, 255))
    p.setBrush(g)
    p.setPen(Qt.NoPen)
    p.drawEllipse(4, 4, 56, 56)
    p.end()
    return QIcon(bild)


def setze_autostart(an: bool) -> None:
    if not an:
        AUTOSTART_LNK.unlink(missing_ok=True)
        return
    pythonw = BASE_DIR / ".venv" / "Scripts" / "pythonw.exe"
    ps = (
        f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{AUTOSTART_LNK}');"
        f"$s.TargetPath='{pythonw}';$s.Arguments='\"{BASE_DIR / 'src' / 'klaus_app.py'}\"';"
        f"$s.WorkingDirectory='{BASE_DIR}';$s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=subprocess.CREATE_NO_WINDOW)


class Steuerung(QObject):
    """Empfaengt Signale aus dem Assistenten-Thread und fasst Fenster nur im GUI-Thread an."""

    def __init__(self, chat: ChatFenster, panel: DesktopPanel, orb: OrbOverlay) -> None:
        super().__init__()
        self.chat = chat
        self.panel = panel
        self.orb = orb
        self.tray: QSystemTrayIcon | None = None
        self.schalter: tuple | None = None  # (Stumm-, Mikro-aus-Eintrag) im Taskleisten-Menue
        self.panel_bruecke: WebBruecke | None = None

    def _panel_in_mitte(self) -> bool:
        """True, wenn in der Bildschirmmitte gerade das Desktop-Panel zu sehen ist."""
        if not self.panel.an:
            return False
        user32 = ctypes.windll.user32
        mitte = wintypes.POINT(user32.GetSystemMetrics(0) // 2, user32.GetSystemMetrics(1) // 2)
        oben = user32.GetAncestor(user32.WindowFromPoint(mitte), 2)  # GA_ROOT: das Hauptfenster dort
        return oben == int(self.panel.winId())

    def panel_verdeckt(self) -> bool:
        """True, wenn ein anderes Fenster (Spiel, maximierte App) den ganzen Bildschirm einnimmt."""
        user32 = ctypes.windll.user32
        vorne = user32.GetForegroundWindow()
        if not vorne or vorne in (int(self.panel.winId()), int(self.chat.winId()), int(self.orb.winId())):
            return False
        if user32.IsIconic(vorne):
            return False
        # Nur Fenster auf DEM Bildschirm zaehlen, auf dem das Panel liegt (sonst friert das Panel ein,
        # sobald auf dem zweiten Monitor etwas maximiert ist)
        if user32.MonitorFromWindow(vorne, 2) != user32.MonitorFromWindow(int(self.panel.winId()), 2):
            return False
        r = wintypes.RECT()
        user32.GetWindowRect(vorne, ctypes.byref(r))
        breite, hoehe = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        return (r.right - r.left) >= breite * 0.95 and (r.bottom - r.top) >= hoehe * 0.85

    @Slot(str)
    def zustand(self, zustand: str) -> None:
        # Mitte-Overlay nur, wenn du in einer anderen App bist (sonst waere der Orb doppelt da)
        chat_vorne = ctypes.windll.user32.GetForegroundWindow() == int(self.chat.winId())
        if zustand != "aus" and (chat_vorne or self._panel_in_mitte()):
            zustand = "aus"
        # Wunsch Nikola (14.10.2026, Meetings): der Orb nur, solange Klaus spricht - nicht beim Zuhoeren/Denken/Stummsein
        if zustand not in ("sprechen", "aktion"):
            zustand = "aus"
        self.orb.setze_zustand(zustand)

    @Slot(str, str)
    def nachricht(self, rolle: str, _text: str) -> None:
        # Kein Chat auf dem Bildschirm (Gespraeche stehen im Obsidian-Vault). Nur ein Claude-Auftrag
        # holt das Klaus-Fenster nach vorne, wenn du gerade in einer anderen App bist.
        if rolle == "auftrag" and not self._panel_in_mitte():
            self.chat.zeige()

    @Slot(str)
    def thema(self, name: str) -> None:
        setze_thema(name)

    @Slot(bool)
    def stumm_geaendert(self, an: bool) -> None:
        self._setze_haken(0, an)
        self.panel_bruecke.stummStatus.emit(an)
        if self.tray:
            self.tray.setToolTip("Klaus – STUMM (sag „Klaus, wieder an“)" if an else "Klaus – sag „Klaus“")

    @Slot(bool)
    def mikro_geaendert(self, aus: bool) -> None:
        self._setze_haken(1, aus)
        self.panel_bruecke.mikroStatus.emit(aus)
        if self.tray:
            self.tray.setToolTip("Klaus – MIKROFON AUS (Strg+Shift+M)" if aus else "Klaus – sag „Klaus“")

    def _setze_haken(self, nr: int, an: bool) -> None:
        if self.schalter:
            aktion = self.schalter[nr]
            aktion.blockSignals(True)  # sonst loest das Setzen den Schalter gleich wieder aus
            aktion.setChecked(an)
            aktion.blockSignals(False)

    @Slot(str)
    def meldung(self, text: str) -> None:
        if self.tray:
            self.tray.showMessage("Klaus", text, self.tray.icon(), 4000)


class Tastenkuerzel(QAbstractNativeEventFilter):
    """Globale Tastenkuerzel ueber Windows RegisterHotKey."""

    WM_HOTKEY, MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x0312, 0x1, 0x2, 0x4, 0x4000

    def __init__(self, aktionen: dict) -> None:
        super().__init__()
        self.aktionen = aktionen

    def registriere(self, nr: int, taste: str, shift: bool = False) -> None:
        zusatz = (self.MOD_CONTROL | self.MOD_SHIFT) if shift else (self.MOD_CONTROL | self.MOD_ALT)
        if not ctypes.windll.user32.RegisterHotKey(None, nr, zusatz | self.MOD_NOREPEAT, ord(taste)):
            print(f"Tastenkuerzel {'Strg+Shift' if shift else 'Strg+Alt'}+{taste} ist schon belegt.")

    def nativeEventFilter(self, typ, nachricht):
        if typ in (b"windows_generic_MSG", "windows_generic_MSG"):
            msg = wintypes.MSG.from_address(int(nachricht))
            if msg.message == self.WM_HOTKEY and msg.wParam in self.aktionen:
                self.aktionen[msg.wParam]()
                return True, 0
        return False, 0


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class Anwesenheit(QObject):
    """Merkt, wenn du weg bist, und zeigt beim Zurueckkommen "Seit du weg warst".

    Solange du da bist, werden alle 5 Minuten Zeit + Kurse gesichert (data/zuletzt.json).
    Das ist die Vergleichsbasis - auch ueber Nacht, wenn der PC aus war.
    """

    WEG_AB_SEK = 15 * 60
    SICHERN_SEK = 5 * 60
    fertig = Signal(str)  # Briefing als JSON, kommt aus einem Hintergrund-Thread

    def __init__(self, assistent: Assistent, panel_bruecke: WebBruecke) -> None:
        super().__init__()
        self.assistent = assistent
        self.panel_bruecke = panel_bruecke
        self.tray: QSystemTrayIcon | None = None
        self.weg_seit: float | None = None
        self.letzte_sicherung = 0.0
        basis = daten.lade_anwesenheit()
        # PC war aus oder Klaus lief nicht: beim ersten Lebenszeichen gibt's das Briefing
        self.ausstehend = basis if basis and time.time() - basis["zeit"] >= self.WEG_AB_SEK else None
        self.fertig.connect(self._zeigen)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.pruefe)
        self.timer.start(20_000)
        QTimer.singleShot(15_000, self.pruefe)  # kurz nach dem Start, wenn das Panel geladen ist

    @staticmethod
    def _leerlauf_sek() -> float:
        info = LASTINPUTINFO(cbSize=ctypes.sizeof(LASTINPUTINFO))
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
        return (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000

    def pruefe(self) -> None:
        jetzt = time.time()
        leerlauf = min(self._leerlauf_sek(), jetzt - self.assistent.zuletzt_aktiv)
        if leerlauf < 60:  # du bist da
            basis = self.ausstehend or (daten.lade_anwesenheit() if self.weg_seit else None)
            self.ausstehend, self.weg_seit = None, None
            if basis:
                threading.Thread(target=self._erstellen, args=(basis,), daemon=True).start()
            elif jetzt - self.letzte_sicherung > self.SICHERN_SEK:
                self.letzte_sicherung = jetzt
                threading.Thread(target=daten.merke_anwesenheit, daemon=True).start()
        elif leerlauf >= self.WEG_AB_SEK and self.weg_seit is None:
            self.weg_seit = jetzt - leerlauf

    def _erstellen(self, basis: dict) -> None:
        try:
            d = daten.verpasst(basis)
            if d["dauer_min"] >= self.WEG_AB_SEK // 60:
                d["text"] = daten.verpasst_text(d)
                self.assistent.letztes_briefing = d["text"]
                gehirn.notiere_briefing(d["text"])
                self.fertig.emit(json.dumps(d, ensure_ascii=False))
        except Exception:
            traceback.print_exc()
        finally:
            daten.merke_anwesenheit()  # neue Basis ab jetzt
            self.letzte_sicherung = time.time()

    @Slot(str)
    def _zeigen(self, briefing: str) -> None:
        self.panel_bruecke.nachricht.emit("briefing", briefing)
        if self.tray:
            d = json.loads(briefing)
            h, m = divmod(d["dauer_min"], 60)
            self.tray.showMessage("Klaus · Seit du weg warst", f"{h} h {m} min weg · {len(d['nachrichten'])} Meldungen · "
                                  "sag „Klaus, was hab ich verpasst?“", self.tray.icon(), 8000)


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Nur ein Klaus gleichzeitig (sonst streiten sich zwei ums Mikrofon)
    sperre = QLockFile(str(BASE_DIR / "data" / "klaus.lock"))
    if not sperre.tryLock(100):
        print("Klaus laeuft bereits.")
        return

    symbol = tray_symbol()
    bruecke = Bruecke()
    assistent = Assistent(bruecke, dry_run="--dry-run" in sys.argv)


    chat: ChatFenster | None = None

    def zeige_chat() -> None:
        chat.zeige()

    panel_bruecke = WebBruecke(assistent, zeige_chat)
    chat_bruecke = WebBruecke(assistent, zeige_chat)
    for web in (panel_bruecke, chat_bruecke):
        bruecke.zustand.connect(web.zustand)
        bruecke.pegel.connect(web.pegel)
        bruecke.nachricht.connect(web.nachricht)
    chat = ChatFenster(chat_bruecke, symbol)
    orb = OrbOverlay(WebBruecke(assistent, zeige_chat))
    bruecke.text.connect(orb.setze_text)
    bruecke.pegel.connect(orb.setze_pegel)
    panel = DesktopPanel(panel_bruecke)
    # Zweiter Bildschirm: eigene Seite, bekommt Holo-Befehle nur vom Panel weitergereicht (wenn Platz gebraucht wird)
    zweit_bruecke = WebBruecke(assistent, zeige_chat)
    zweit = ZweitFenster(zweit_bruecke)
    panel_bruecke.zweit_fenster, panel_bruecke.zweit_bruecke = zweit, zweit_bruecke
    zweit_bruecke.panel_ziel = panel_bruecke  # "Als Widgets anheften" auf Bildschirm 2 -> Widgets im Panel
    steuerung = Steuerung(chat, panel, orb)
    bruecke.nachricht.connect(steuerung.nachricht)
    bruecke.zustand.connect(steuerung.zustand)
    bruecke.thema.connect(steuerung.thema)
    bruecke.thema.connect(zweit_bruecke.thema)
    bruecke.panel.connect(panel_bruecke.panelBefehl)
    bruecke.holo.connect(panel_bruecke.holo)
    pc_hinweis = PcNutzungHinweis()   # "Klaus benutzt gerade den PC" (pc_zugriff.py)
    bruecke.pc_nutzung.connect(pc_hinweis.setze)
    steuerung.panel_bruecke = panel_bruecke
    bruecke.nachricht.connect(gehirn.protokolliere)  # Tagesnotiz im Obsidian-Vault
    bruecke.gedaechtnis.connect(lambda: panel_bruecke.lade("gedaechtnis", ""))  # nur Thread-Start, kein Fenster

    # Obsidian-Vault gleich anlegen, damit Nikola.md sofort zum Bearbeiten da ist
    if not gehirn.FAKTEN_PATH.exists():
        gehirn._speichern(gehirn.lade_gedaechtnis())

    einstellungen = lade_einstellungen()
    # Mit Windows starten ist Standard; wer es im Menue abschaltet, bleibt dabei
    if "autostart" not in einstellungen:
        setze_autostart(True)
        speichere_einstellung("autostart", True)
        einstellungen = lade_einstellungen()
    # Zustand vor dem allerersten Klaus-Start merken (ueberlebt auch einen Absturz)
    if "taskleiste_original" not in einstellungen:
        speichere_einstellung("taskleiste_original", taskleiste_versteckt())
        einstellungen = lade_einstellungen()
    taskleiste_vorher = einstellungen["taskleiste_original"]
    taskleiste_verstecken(einstellungen.get("taskleiste_aus", True))
    panel.einschalten(einstellungen.get("panel", True) and "--ohne-panel" not in sys.argv)

    # ---------------------------------------------------------------- Taskleiste
    tray = QSystemTrayIcon(symbol)
    tray.setToolTip("Klaus – sag „Klaus“")
    menue = QMenu()
    chat_oeffnen = QAction("Klaus-Fenster öffnen")
    chat_oeffnen.triggered.connect(zeige_chat)
    panel_an = QAction("Desktop-Panel", checkable=True, checked=panel.an)

    def panel_umschalten(an: bool) -> None:
        panel.einschalten(an)
        speichere_einstellung("panel", an)

    panel_an.toggled.connect(panel_umschalten)
    taskleiste_aus = QAction("Taskleiste ausblenden", checkable=True, checked=taskleiste_versteckt())

    def taskleiste_umschalten(an: bool) -> None:
        taskleiste_verstecken(an)
        speichere_einstellung("taskleiste_aus", an)
        panel.einschalten(panel.an)  # Groesse an die neue Bildschirmflaeche anpassen

    taskleiste_aus.toggled.connect(taskleiste_umschalten)
    stumm = QAction("Stumm  (Strg+Alt+K)", checkable=True)
    stumm.toggled.connect(assistent.setze_stumm)
    mikro_aus = QAction("Mikrofon aus  (Strg+Shift+M)", checkable=True)
    mikro_aus.toggled.connect(assistent.setze_mikro_aus)
    steuerung.schalter = (stumm, mikro_aus)
    bruecke.stumm.connect(steuerung.stumm_geaendert)
    bruecke.mikro_aus.connect(steuerung.mikro_geaendert)
    # Globale Tastenkuerzel - funktionieren auch, wenn ein Spiel oder eine andere App vorne ist
    tasten = Tastenkuerzel({1: lambda: assistent.setze_stumm(not assistent.ist_stumm),
                            2: lambda: assistent.setze_mikro_aus(not assistent.pausiert)})
    tasten.registriere(1, "K")
    tasten.registriere(2, "M", shift=True)  # Strg+Alt+M ist bei dir schon belegt
    app.installNativeEventFilter(tasten)
    autostart = QAction("Mit Windows starten", checkable=True, checked=AUTOSTART_LNK.exists())
    autostart.toggled.connect(lambda an: (setze_autostart(an), speichere_einstellung("autostart", an)))
    stimme = QAction("Stimme wählen …")
    stimme.triggered.connect(lambda: os.startfile(BASE_DIR / "Stimme-waehlen.bat"))
    projekte = QAction("Projekte-Ordner öffnen")
    projekte.triggered.connect(lambda: apps.oeffne("klaus projekte"))
    log = QAction("Log öffnen")
    log.triggered.connect(lambda: LOG_PATH.exists() and os.startfile(LOG_PATH))
    ende = QAction("Klaus beenden")

    def beenden() -> None:
        assistent.laeuft = False
        taskleiste_verstecken(taskleiste_vorher)  # ohne Klaus die Taskleiste wie vorher
        tray.hide()
        app.quit()

    ende.triggered.connect(beenden)
    for eintrag in (stumm, mikro_aus, chat_oeffnen, panel_an, taskleiste_aus, autostart, stimme, projekte, log):
        menue.addAction(eintrag)
    menue.addSeparator()
    menue.addAction(ende)
    tray.setContextMenu(menue)
    tray.activated.connect(lambda grund: grund == QSystemTrayIcon.Trigger and zeige_chat())
    tray.show()
    steuerung.tray = tray
    bruecke.meldung.connect(steuerung.meldung)
    anwesenheit = Anwesenheit(assistent, panel_bruecke)
    anwesenheit.tray = tray

    # Spart Grafikkarte: Panel-Animationen anhalten, solange ein Vollbild-Fenster (z. B. ein Spiel) davor ist
    zuletzt_sichtbar = [True]

    def sicht_pruefen() -> None:
        sichtbar = not steuerung.panel_verdeckt()
        if sichtbar != zuletzt_sichtbar[0]:
            zuletzt_sichtbar[0] = sichtbar
            panel_bruecke.sichtbar.emit(sichtbar)

    sicht_timer = QTimer()
    sicht_timer.timeout.connect(sicht_pruefen)
    sicht_timer.start(2000)

    threading.Thread(target=assistent.run, daemon=True).start()
    import fernlink
    import telegram_bot

    if fernlink.konfiguriert():   # Verbindung zum Server (Gehirn): Tunnel + Werkzeug-Server nur auf 127.0.0.1
        if fernlink.telegram_auf_server():
            assistent.fern = fernlink.FernProxy(assistent)   # der Bot laeuft auf dem Server, der PC meldet nur dorthin
        fernlink.starte(assistent)
    if assistent.fern is None and telegram_bot.bereit():   # Chat von unterwegs (nur dein Konto, Freigaben mit PIN)
        assistent.fern = telegram_bot.TelegramKlaus(assistent)
        import pc_zugriff
        for befehl in ("/status", "/timer", "/stop"):   # Bot laeuft lokal: PC-Zugriff direkt steuern
            assistent.fern.befehle[befehl] = pc_zugriff.telegram_befehl
        threading.Thread(target=assistent.fern.run, daemon=True).start()
    app.exec()
    os._exit(0)  # Audio-Thread nicht abwarten


if __name__ == "__main__":
    main()
