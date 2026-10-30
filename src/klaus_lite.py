"""
Klaus Lite - nur Sprache und Chat fuer schwaechere PCs.

Ohne Desktop-Panel, Orb, Overlays, Spielmodus, Stream/Twitch und ohne Qt WebEngine (Chromium): ein kleines Chatfenster aus normalen
Qt-Widgets plus Symbol in der Taskleiste. Spart Arbeitsspeicher (grob 400-700 MB), Grafikkarte und Prozessor, und den
Download von PySide6-Addons (Installer nimmt dann PySide6-Essentials).

Einschalten: KLAUS_LITE=1 in der .env (Installer: Haken "Lite-Version"). klaus_app.py startet dann automatisch dieses Modul.
Gleich bleiben: Sprachgespraech (Gemini Live bzw. lokale Kette), alle Werkzeuge, Telegram, WhatsApp, Kalender, Updates.
Weg: Panel, Orb, Design/Farbrad, Spielmodus, Twitch/OBS/Stream-Overlay, YouTube-Chat, Taskleiste ausblenden, Tastenkuerzel.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QLockFile, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QLineEdit, QMenu, QPlainTextEdit, QPushButton, QSystemTrayIcon,
                               QVBoxLayout, QWidget)

import identitaet

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_PATH = BASE_DIR / "data" / "klaus.log"
AUTOSTART_LNK = Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\Startup\Klaus.lnk"
ZUSTAND = {"aus": "bereit", "start": "startet …", "hoeren": "hört zu …", "denken": "denkt …", "sprechen": "spricht …",
           "aktion": "erledigt …", "fehler": "Fehler – siehe Log", "freigabe": "wartet auf deine Freigabe"}
ROLLE = {"du": "Du", "klaus": identitaet.NAME, "info": "·", "auftrag": "→"}
STIL = """
QWidget { background: #14181d; color: #e6edf3; font-size: 13px; }
QPlainTextEdit { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 6px; }
QLineEdit { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 7px; }
QLineEdit:focus { border-color: #58a6ff; }
QPushButton { background: #21262d; border: 1px solid #30363d; border-radius: 6px; padding: 6px 12px; }
QPushButton:hover { border-color: #58a6ff; }
QLabel#status { color: #8b949e; }
"""


def lite_an() -> bool:
    return identitaet.LITE


def symbol() -> QIcon:
    bild = QPixmap(32, 32)
    bild.fill(Qt.transparent)
    p = QPainter(bild)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(0, 200, 235))
    p.setPen(Qt.NoPen)
    p.drawEllipse(3, 3, 26, 26)
    p.end()
    return QIcon(bild)


def autostart_setzen(an: bool) -> None:
    if not an:
        AUTOSTART_LNK.unlink(missing_ok=True)
        return
    pythonw = BASE_DIR / ".venv" / "Scripts" / "pythonw.exe"
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{AUTOSTART_LNK}');"
          f"$s.TargetPath='{pythonw}';$s.Arguments='\"{BASE_DIR / 'src' / 'klaus_app.py'}\"';"
          f"$s.WorkingDirectory='{BASE_DIR}';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


class ChatFenster(QWidget):
    """Einfaches Chatfenster: Verlauf, Eingabezeile, Statuszeile. Keine Web-Engine."""
    neu = Signal(str, str)      # (Rolle, Text) - aus beliebigen Threads sicher
    status = Signal(str)

    def __init__(self, senden) -> None:
        super().__init__()
        self._senden = senden
        self.setWindowTitle(identitaet.NAME)
        self.setStyleSheet(STIL)
        self.setMinimumSize(380, 460)
        self.verlauf = QPlainTextEdit(readOnly=True)
        self.verlauf.setMaximumBlockCount(500)           # begrenzt den Speicher
        self.zeile = QLineEdit(placeholderText=f"Schreib {identitaet.NAME} …")
        self.zeile.returnPressed.connect(self._abschicken)
        self.knopf = QPushButton("Senden")
        self.knopf.clicked.connect(self._abschicken)
        self.statuszeile = QLabel("bereit", objectName="status")
        unten = QHBoxLayout()
        unten.addWidget(self.zeile, 1)
        unten.addWidget(self.knopf)
        layout = QVBoxLayout(self)
        layout.addWidget(self.statuszeile)
        layout.addWidget(self.verlauf, 1)
        layout.addLayout(unten)
        self.neu.connect(self._zeigen)
        self.status.connect(self.statuszeile.setText)

    def _zeigen(self, rolle: str, text: str) -> None:
        self.verlauf.appendPlainText(f"· {text}" if rolle == "info" else f"{ROLLE.get(rolle, rolle)}: {text}")

    def _abschicken(self) -> None:
        text = self.zeile.text().strip()
        if text:
            self.zeile.clear()
            self._senden(text)

    def zeige(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.zeile.setFocus()

    def closeEvent(self, ereignis) -> None:       # Schliessen = ins Symbol verkleinern, Klaus laeuft weiter
        ereignis.ignore()
        self.hide()


def main() -> None:
    import instanz
    if not instanz.sperren():
        print("Klaus laeuft bereits (Desktop oder Voice).")
        return
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    sperre = QLockFile(str(BASE_DIR / "data" / "klaus.lock"))
    if not sperre.tryLock(100):
        print("Klaus laeuft bereits.")
        return

    import gehirn
    from assistent import Assistent, Bruecke
    from daten import lade_einstellungen, speichere_einstellung

    bruecke = Bruecke()
    assistent = Assistent(bruecke, dry_run="--dry-run" in sys.argv)
    chat = ChatFenster(assistent.eingabe)
    bruecke.nachricht.connect(chat.neu)
    bruecke.zustand.connect(lambda z: chat.status.emit(ZUSTAND.get(z, z)))
    bruecke.nachricht.connect(gehirn.protokolliere)   # Tagesnotiz im Obsidian-Vault, wie in der grossen Version
    if not gehirn.FAKTEN_PATH.exists():
        gehirn._speichern(gehirn.lade_gedaechtnis())

    einstellungen = lade_einstellungen()
    if "autostart" not in einstellungen:
        autostart_setzen(True)
        speichere_einstellung("autostart", True)

    tray = QSystemTrayIcon(symbol())
    tray.setToolTip(f"{identitaet.NAME} Lite – sag „{identitaet.NAME}“")
    menue = QMenu()
    chat_menue = QAction("Chat öffnen")
    chat_menue.triggered.connect(chat.zeige)
    stumm = QAction("Stumm", checkable=True)
    stumm.toggled.connect(assistent.setze_stumm)
    mikro = QAction("Mikrofon aus", checkable=True)
    mikro.toggled.connect(assistent.setze_mikro_aus)

    def haken(aktion: QAction, an: bool) -> None:
        aktion.blockSignals(True)
        aktion.setChecked(an)
        aktion.blockSignals(False)
    bruecke.stumm.connect(lambda an: haken(stumm, an))
    bruecke.mikro_aus.connect(lambda aus: haken(mikro, aus))

    def im_hintergrund(arbeit, vorspann: str = "") -> None:
        def los() -> None:
            try:
                text = arbeit()
            except Exception as e:
                text = f"Das ging nicht: {str(e)[:150]}"
            print(f"[Lite] {text}", flush=True)
            bruecke.meldung.emit(text)
        if vorspann:
            bruecke.meldung.emit(vorspann)
        threading.Thread(target=los, daemon=True).start()

    def meldung(text: str) -> None:
        tray.showMessage(identitaet.NAME, text, tray.icon(), 4000)
    bruecke.meldung.connect(meldung)

    def einstellungen_fenster(bereich: str = "") -> None:
        import verbindungen_fenster
        verbindungen_fenster.zeige_einstellungen(bereich)

    def verbindungen_fenster_zeigen(plattform: str = "") -> None:
        import verbindungen_fenster
        verbindungen_fenster.zeige(plattform)
    bruecke.einstellungen.connect(einstellungen_fenster)
    bruecke.verbindungen.connect(verbindungen_fenster_zeigen)
    bruecke.chat_fenster.connect(lambda auf: chat.zeige() if auf else chat.hide())

    einstellungen_aktion = QAction("Einstellungen …")
    einstellungen_aktion.triggered.connect(lambda: einstellungen_fenster(""))
    verbindungen_aktion = QAction("Verbindungen …")
    verbindungen_aktion.triggered.connect(lambda: verbindungen_fenster_zeigen(""))

    def updates() -> None:
        import pc_update
        im_hintergrund(lambda: pc_update.jetzt_pruefen(assistent), f"Suche nach Updates (installiert: {pc_update.version()}) …")
    update_aktion = QAction("Nach Updates suchen")
    update_aktion.triggered.connect(updates)

    def bericht() -> None:
        import fehlerbericht
        im_hintergrund(lambda: fehlerbericht.senden("von Hand gesendet"))
    bericht_aktion = QAction("Fehlerbericht senden")
    bericht_aktion.triggered.connect(bericht)
    log = QAction("Log öffnen")
    log.triggered.connect(lambda: LOG_PATH.exists() and os.startfile(LOG_PATH))
    autostart = QAction("Mit Windows starten", checkable=True, checked=AUTOSTART_LNK.exists())
    autostart.toggled.connect(lambda an: (autostart_setzen(an), speichere_einstellung("autostart", an)))
    ende = QAction("Beenden")

    def beenden() -> None:
        assistent.laeuft = False
        tray.hide()
        app.quit()
    ende.triggered.connect(beenden)
    for a in (chat_menue, stumm, mikro, einstellungen_aktion, verbindungen_aktion, update_aktion, bericht_aktion, log, autostart):
        menue.addAction(a)
    menue.addSeparator()
    menue.addAction(ende)
    tray.setContextMenu(menue)
    tray.activated.connect(lambda grund: grund == QSystemTrayIcon.Trigger and chat.zeige())
    tray.show()

    threading.Thread(target=assistent.run, daemon=True).start()
    import fernlink
    import telegram_bot

    if fernlink.konfiguriert():   # Verbindung zum Server (Gehirn)
        if fernlink.telegram_auf_server():
            assistent.fern = fernlink.FernProxy(assistent)
        fernlink.starte(assistent)
    if assistent.fern is None and telegram_bot.bereit():
        assistent.fern = telegram_bot.TelegramKlaus(assistent)
        import stimmwahl
        assistent.fern.befehle["/stimmen"] = assistent.fern.befehle["/stimme"] = stimmwahl.befehl
        threading.Thread(target=assistent.fern.run, daemon=True).start()
    import pc_update
    pc_update.starte(assistent)
    app.exec()
    os._exit(0)   # Audio-Thread nicht abwarten


if __name__ == "__main__":
    main()
