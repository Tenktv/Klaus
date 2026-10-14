# Klaus Kontrollzentrum - 14.10.2026

## Design

Web-Oberflaeche: `src/web/command-center.css` und `command-center.js`, zusammen mit Dashboard, Chat und Overlay.
Brief: `src/web/DESIGN.md`. Lokale Schriften und gezeichnete Geometrie; keine bezahlten Bild-/Video-Generierungen.
Hugging Face und Higgsfield wurden recherchiert, nicht zur Generierung verwendet.

Neue Brueckenmethoden: `ladeBetrieb`, `eingabe`, `pcStopp`, `pcTimer`, `protokollBeenden`, `coachBeenden`.
Status wird lokal gelesen; Befehle nutzen die bestehende Queue und Freigaben. Widgets/Zweitbildschirm bleiben angebunden.
Sprach-Overlay: 360 x 390 px, unten rechts. Vorhandene Sichtbarkeitsregel beim Sprechen bleibt erhalten.

## Maus und Tastatur

`src/pc_steuerung.py`, Werkzeug `pc_eingabe`: Bewegen, Klicken, Scrollen, begrenzte Tasten und kurze Unicode-Texte.
JEDE Aktion braucht eine eigene ausdrueckliche Einmal-Freigabe, auch Mausbewegung und Scrollen.
Textvorschau erscheint im Freigabeziel; Werkzeug-/Aktionslogs verbergen eingegebenen Text.
Keine Drags oder dauernd gehaltenen Tasten. Koordinaten: physische Pixel auf dem Hauptmonitor.

Stop/Timer verwerfen wartende Eingaben ueber `Z.abbruch_generation`, auch nach spaeterem Entsperren.
Vor jeder Eingabe: Sperre, Generation, Bildschirmgrenzen, PyAutoGUI-Fail-safe pruefen.
PyAutoGUI wird nur auf dem PC benoetigt, nicht auf dem Telegram-Server.

## Pruefung und Aktivierung

Offline: `.venv\Scripts\python.exe -m unittest discover -s tests`.
Tests fuehren keine echten PC-Eingaben aus und lesen keine Zugangsdaten.
Tatsaechliche Windows-Maus-/Tastatureingabe ist noch nicht live getestet.
PC-App muss neuen Code laden; Telegram-Server ebenfalls fuer die Werkzeugdeklaration aktualisieren.
Laufende Protokolle und Spiele nicht fuer einen UI-Test unterbrechen; kein zweiter Klaus mit gemeinsamem Browserprofil.
