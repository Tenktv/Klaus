# Genshin-Modus (experimentell)

Lokales Bildmodell: Ollama `gemma3:4b`. Kein API-Schluessel erforderlich.
Start: `Genshin-Modus.bat` oder in Klaus „oeffne den Genshin-Modus“.
Klaus' Werkzeug oeffnet nur das Panel. Der Spielmodus beginnt erst mit F8/Start.

## Nachgewiesene Ursache auf diesem PC

Am 18.10.2026 hatte Genshin Windows-Integritaetsstufe 12288 (hoch), der Agent
8192 (mittel). Windows UIPI blockiert diese Eingaben. Der bisherige Text
„Testeingabe gesendet“ war kein Nachweis fuer eine Bewegung im Spiel.

Falls dieser Konflikt gemeldet wird: normales Spielpanel schliessen und
`Genshin-Modus-als-Admin.bat` selbst starten. Windows zeigt eine UAC-Abfrage.
Nur der kleine Spielmodus wird erhoeht; die Klaus-Hauptanwendung bleibt normal.
Die UAC-Abfrage muss der Benutzer selbst beantworten. Kein Treiber, keine
Anti-Cheat-Umgehung. Annahme durch Windows garantiert keine Annahme im Spiel.

## Bedienung

- Erst „Bewegung testen“ und binnen fuenf Sekunden ins Spiel wechseln.
- F8 startet bis zu 100 Entscheidungen, maximal zehn Minuten.
- F9/STOP beendet Eingaben. Klaus' PC-Stopp und Timer stoppen auch den Spielmodus.
- Fokuswechsel verwirft die vorbereitete Aktion; gehaltene Tasten werden losgelassen.
- Nur `GenshinImpact.exe` und `YuanShen.exe` sind erlaubt, keine Titel-Aehnlichkeit.
- Ein lokaler Lauf sendet Bilder nur an Ollama auf 127.0.0.1. Keine Bilder werden gespeichert.
- Drei ungueltige Modellantworten beenden den Lauf; eine einzelne fuehrt zu einem neuen Bild.
- Modellentscheidungen aelter als 20 Sekunden werden im Steuerungsmodus verworfen.
- Bei Menues/Unsicherheit stoppen; keine unbeaufsichtigten Kauf- oder Login-Aktionen.

Das Modell kann Wege, Feinde und Dialoge falsch erkennen. Teamnamen an der rechten
Seite gelten ausdruecklich nicht als Gegner. Zuverlaessiger Questabschluss ist noch
nicht nachgewiesen. Die Eingabefunktionen pruefen den Rueckgabewert von SendInput.

Protokolle: `src/genshin_agent/logs/`. Quellcode und Tests enthalten keine Zugangsdaten.
Der bestehende Spiele-Coach und das Freigabe-Gate fuer allgemeine PC-Aktionen bleiben
getrennte Funktionen. Kein automatischer Start beim Windows-Login.

Technische Referenzen:
- https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-sendinput
- https://docs.ollama.com/capabilities/structured-outputs
