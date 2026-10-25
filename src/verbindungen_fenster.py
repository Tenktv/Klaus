"""
Klaus - Fenster "Verbindungen": Twitch, YouTube, X, Instagram, Discord und andere Plattformen selbst eintragen.

Oeffnet sich ueber das Taskleisten-Menue oder per Sprache ("Klaus, verbinde Twitch"). Schluessel tippt man nur hier ein -
sie gehen in die .env auf diesem PC, nie an die KI.
"""
from __future__ import annotations

import threading
import webbrowser

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QVBoxLayout, QWidget)

import identitaet
import verbindungen as V

ZEICHEN = {"ja": "●", "teilweise": "◐", "nein": "○"}
STIL = """
QDialog { background: #0d1117; color: #e6edf3; }
QLabel { color: #e6edf3; }
QLabel#titel { font-size: 18px; font-weight: 600; }
QLabel#leise { color: #8b949e; }
QLabel#code { font-size: 26px; font-weight: 700; letter-spacing: 4px; color: #58a6ff; }
QListWidget { background: #161b22; border: 1px solid #30363d; border-radius: 8px; color: #e6edf3; font-size: 14px; }
QListWidget::item { padding: 8px; }
QListWidget::item:selected { background: #1f6feb; border-radius: 6px; }
QLineEdit { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 6px; color: #e6edf3; }
QLineEdit:focus { border-color: #58a6ff; }
QPushButton { background: #21262d; border: 1px solid #30363d; border-radius: 6px; padding: 7px 14px; color: #e6edf3; }
QPushButton:hover { border-color: #58a6ff; }
QPushButton#haupt { background: #1f6feb; border-color: #1f6feb; }
"""


class VerbindungenFenster(QDialog):
    meldung = Signal(str)       # aus Hintergrund-Threads (Testen, Twitch-Anmeldung)
    code = Signal(str, str)     # Twitch: Adresse, Code

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Verbindungen – {identitaet.NAME}")
        self.setMinimumSize(820, 560)
        self.setStyleSheet(STIL)
        self.felder: dict[str, QLineEdit] = {}
        self.pid = "twitch"

        self.liste = QListWidget()
        self.liste.setFixedWidth(210)
        for pid, p in V.PLATTFORMEN.items():
            eintrag = QListWidgetItem(p.name)
            eintrag.setData(Qt.UserRole, pid)
            self.liste.addItem(eintrag)
        self.liste.currentRowChanged.connect(self._gewaehlt)

        self.titel = QLabel(objectName="titel")
        self.kann = QLabel(wordWrap=True)
        self.anleitung = QLabel(wordWrap=True, objectName="leise")
        self.anleitung.setTextFormat(Qt.RichText)
        self.anleitung.setOpenExternalLinks(True)
        self.formular = QWidget()
        self.form = QFormLayout(self.formular)
        self.codezeile = QLabel(objectName="code", alignment=Qt.AlignCenter)
        self.codezeile.hide()
        self.status = QLabel(wordWrap=True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.k_anleitung = QPushButton("Anleitung öffnen")
        self.k_speichern = QPushButton("Speichern", objectName="haupt")
        self.k_testen = QPushButton("Testen")
        self.k_twitch = QPushButton("Bei Twitch anmelden")
        self.k_trennen = QPushButton("Trennen")
        self.k_anleitung.clicked.connect(lambda: webbrowser.open(V.PLATTFORMEN[self.pid].link))
        self.k_speichern.clicked.connect(self._speichern)
        self.k_testen.clicked.connect(self._testen)
        self.k_twitch.clicked.connect(self._twitch_anmelden)
        self.k_trennen.clicked.connect(self._trennen)
        knoepfe = QHBoxLayout()
        for k in (self.k_anleitung, self.k_twitch, self.k_trennen):
            knoepfe.addWidget(k)
        knoepfe.addStretch()
        knoepfe.addWidget(self.k_testen)
        knoepfe.addWidget(self.k_speichern)

        rechts = QVBoxLayout()
        for w in (self.titel, self.kann, self.anleitung, self.formular, self.codezeile, self.status):
            rechts.addWidget(w)
        rechts.addStretch()
        rechts.addLayout(knoepfe)
        hinweis = QLabel("Deine Schlüssel bleiben auf diesem PC (.env) – die KI sieht sie nie. "
                         "Posten geht immer erst nach deiner Freigabe.", objectName="leise", wordWrap=True)
        rechts.addWidget(hinweis)
        haupt = QHBoxLayout(self)
        haupt.addWidget(self.liste)
        haupt.addLayout(rechts, 1)

        self.meldung.connect(self._melden)
        self.code.connect(self._code_zeigen)
        self.zeige("twitch")

    # ---------------------------------------------------------------- Anzeige
    def zeige(self, pid: str = "") -> None:
        gefunden = V.finde(pid).split(":", 1)[0]
        pid = gefunden or ("webhook" if pid else self.pid)   # TikTok, LinkedIn ... -> "Andere Plattform"
        ids = list(V.PLATTFORMEN)
        self._listen_zeichen()
        self.liste.setCurrentRow(ids.index(pid))
        self._gewaehlt(ids.index(pid))
        self.show()
        self.raise_()
        self.activateWindow()

    def _listen_zeichen(self) -> None:
        for i, (pid, p) in enumerate(V.PLATTFORMEN.items()):
            self.liste.item(i).setText(f"{ZEICHEN[V.zustand(pid)]}  {p.name}")

    def _gewaehlt(self, zeile: int) -> None:
        if zeile < 0:
            return
        self.pid = list(V.PLATTFORMEN)[zeile]
        p = V.PLATTFORMEN[self.pid]
        self.titel.setText(p.name)
        self.kann.setText(p.kann)
        schritte = "".join(f"<li>{s}</li>" for s in p.anleitung)
        self.anleitung.setText(f"<ol style='margin-left:-20px'>{schritte}</ol>"
                               f"<a href='{p.link}' style='color:#58a6ff'>{p.link}</a>")
        while self.form.rowCount():
            self.form.removeRow(0)
        self.felder = {}
        for f in p.felder:
            feld = QLineEdit()
            jetzt = "" if f.env.startswith("_") else V._wert(f.env)
            if f.geheim:
                feld.setEchoMode(QLineEdit.Password)
                feld.setPlaceholderText("gespeichert – leer lassen = behalten" if jetzt else f.hinweis)
            else:
                feld.setText(jetzt)
                feld.setPlaceholderText(f.hinweis)
            self.felder[f.env] = feld
            self.form.addRow(f.label + ":", feld)
        self.k_twitch.setVisible(self.pid == "twitch")
        self.k_trennen.setVisible(self.pid != "webhook" and V.zustand(self.pid) != "nein")
        self.codezeile.hide()
        if self.pid == "webhook" and V.webhooks():
            self.status.setText("Schon verbunden: " + ", ".join(V.webhooks()) + ". Neuer Name = weitere Plattform.")
        else:
            self.status.setText({"ja": "Verbunden.", "teilweise": "Halb eingerichtet.", "nein": ""}[V.zustand(self.pid)])

    def _melden(self, text: str) -> None:
        self.status.setText(text)
        self._listen_zeichen()
        self.k_trennen.setVisible(self.pid != "webhook" and V.zustand(self.pid) != "nein")

    def _code_zeigen(self, adresse: str, code: str) -> None:
        self.codezeile.setText(code)
        self.codezeile.show()
        self.status.setText(f"Im Browser ({adresse}) diesen Code bestätigen. Ich warte …")

    # ---------------------------------------------------------------- Knoepfe
    def _speichern(self) -> None:
        try:
            text = V.speichern(self.pid, {env: feld.text() for env, feld in self.felder.items()})
        except ValueError as e:
            self.status.setText(str(e))
            return
        for f in V.PLATTFORMEN[self.pid].felder:
            if f.geheim:
                self.felder[f.env].clear()
        self._gewaehlt(self.liste.currentRow())
        self._melden(text)

    def _im_hintergrund(self, arbeit) -> None:
        def los() -> None:
            try:
                self.meldung.emit(arbeit())
            except Exception as e:
                self.meldung.emit(f"Das ging nicht: {str(e)[:200]}")
        threading.Thread(target=los, daemon=True).start()

    def _testen(self) -> None:
        self.status.setText("Teste …")
        pid = self.pid
        self._im_hintergrund(lambda: V.testen(pid))

    def _trennen(self) -> None:
        self._melden(V.trennen(self.pid))
        self._gewaehlt(self.liste.currentRow())

    def _twitch_anmelden(self) -> None:
        import stream

        if self.felder.get("TWITCH_CLIENT_ID") and self.felder["TWITCH_CLIENT_ID"].text().strip() != stream.CLIENT_ID:
            self._speichern()   # frisch eingetragene Client-ID zuerst uebernehmen
        self.status.setText("Hole einen Code von Twitch …")

        def arbeit() -> str:
            d = stream.geraete_code()
            self.code.emit(d["verification_uri"], d["user_code"])
            webbrowser.open(d["verification_uri"])
            return stream.geraete_code_warten(d)
        self._im_hintergrund(arbeit)


_fenster: VerbindungenFenster | None = None


def zeige(pid: str = "") -> None:
    """Aus dem Qt-Hauptthread aufrufen (klaus_app.Steuerung)."""
    global _fenster
    if _fenster is None:
        _fenster = VerbindungenFenster()
    _fenster.zeige(pid)
