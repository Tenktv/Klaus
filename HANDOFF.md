# KLAUS — Projekt-Übergabe & Roadmap

> **So benutzt du diese Datei:** Den Block „System-Prompt für die nächste Sitzung“ in einen neuen Claude-Code-Chat
> einfügen (Arbeitsordner: dieses Repo). Alles Nötige steht hier. Stand: 05.10.2026.
> Repo: https://github.com/Tenktv/Klaus

---

## 0. System-Prompt für die nächste Sitzung

```
Du entwickelst KLAUS weiter, einen sprachgesteuerten Desktop-Assistenten für Nikola (Ein-Mann-Webdesign-Studio
"Klesro Web", Göppingen). Lies HANDOFF.md vollständig, bevor du etwas tust.

Regeln:
- Sprich mit Nikola locker auf Deutsch (du). Code-Kommentare deutsch wie im bestehenden Code.
- Arbeite die Roadmap in Abschnitt 5 der Reihe nach ab, außer Nikola sagt etwas anderes.
- Vor jeder Phase: in max. 5 Zeilen sagen, welche Dateien du anfasst. Danach: echte Aufnahme des
  Klaus-Fensters (Abschnitt 3, Regel 5), kurze Zusammenfassung, Git-Commit.
- Halte jede Regel in Abschnitt 3 ein. Sie stammen aus echten Fehlern.
- Claude/Claude Code nur, wenn Nikola ausdrücklich "Claude" sagt. Standard = Gemini + kostenlose Suche.
- Kein bezahltes API-Kontingent in großen Mengen ohne Nachfrage. Keine Mehrfach-Konten für Gratis-Kontingente.
- Alles mit Außenwirkung (senden, drucken, hochladen, handeln, anrufen, löschen, installieren) braucht das
  Freigabe-Gate (src/freigabe.py) - ohne Ausnahme.
```

---

## 1. Was Klaus ist

Eine Python-App, die den **Windows-Desktop ersetzt**: Holo-Panel im Stil „Stark Holo-Tech“ mit Reaktor-Kern in
der Mitte, gesteuert **nur per Stimme** (Weckwort „Klaus“). Sie betreibt außerdem Nikolas Kundengewinnung:
Betriebe ohne Website finden (OpenStreetMap), Konkurrenz prüfen, Briefe mit persönlichem Website-Entwurf und
QR-Code schreiben, Entwürfe hochladen und drucken (beides nur mit Freigabe). Langfristig soll Klaus verkauft
werden (Abschnitt 5, Phase K).

Besitzer: Nikola, info@klesro-web.de. Rechner: Windows 11, RTX 2070 (8 GB), **zwei Monitore**
(DISPLAY2 = Hauptbildschirm x=0, DISPLAY1 links x=-1920), Mikrofon „IC 6010“.

## 2. Aufbau (alles läuft)

| Bereich | Dateien | Hinweise |
|---|---|---|
| App | `src/klaus_app.py` | PySide6 6.11. Tray, Hotkeys (Strg+Alt+K stumm, Strg+Shift+M Mikro aus), Taskleiste ausgeblendet, Autostart, Anwesenheit/Briefing, Log schwärzt Schlüssel (`_SchwaerzendesLog`). Start: `.venv\Scripts\pythonw.exe src\klaus_app.py` |
| Fenster | `src/fenster.py` | `DesktopPanel` (Hauptbildschirm, immer ganz unten), `ZweitFenster` (Bildschirm 2, nur bei Bedarf sichtbar), `WebBruecke` (JS-Objekt `klaus`), `OrbOverlay`, `ChatFenster` |
| Sprach-Schleife | `src/assistent.py` | Weckwort, Absichten (Regex), alle Abläufe: Leads, Briefe, Lagebericht, Globus, Pläne, Widgets, Konkurrenz, Sicherheit, Graph; `_mit_freigabe()` für alles Riskante |
| Gespräch | `src/gemini_live.py` | Gemini Live (`gemini-3.8-live`, Stimme Charon), ~40 Werkzeuge. Freigabe nur aus der **Mitschrift deines Mikrofons** (`input_transcription`) |
| Gehirn / Gedächtnis | `src/gehirn.py` | Persona, Obsidian-Vault `Dokumente\Klaus Gedächtnis` (Nikola.md, Gespraeche/, Briefings/, Plaene/, Aktionen/), Claude nur mit `claude=True` |
| Recherche | `src/recherche.py` | Tavily → kostenlos `ddgs`; Zusammenfassung Gemini-Textmodelle → Ollama; Webinhalte als „fremde Daten“ markiert (Prompt-Injection-Schutz) |
| Freigabe | `src/freigabe.py` | Einmal-Token je Art (hochladen, drucken, loeschen, verschieben, programm, bluetooth, fenster_schliessen, admin, sicherheit), 90 s Wartezeit, 120 s gültig, einmal verwendbar |
| Rechte | `src/rechte.py`, `src/admin.py` | Fenster, Dateien, winget, Lautstärke (pycaw), Bluetooth (WinRT), Bildschirmfoto, Zwischenablage; Admin nur für fest hinterlegte Befehle per UAC. Protokoll im Vault |
| Sicherheit | `src/sicherheit.py` | Defender/Firewall/Bedrohungen, Wächter gegen Basislinie `data/sicherheit_basis.json`, Scan ohne Admin, sonst über Gate + UAC |
| Lagebericht | `src/lage.py`, `src/web/lage.js`, `src/web/globus.js` | Nachrichten ohne KI verortet (Ortstabellen, schwache Hinweise wie „Merz“ zuletzt), Region per Google-News-Suche, Märkte, Kennzahlen; Welt-Station auf dem 3D-Globus |
| Leads | `src/osm_leads.py`, `src/konkurrenz.py` | Overpass (Spiegel-Server) + Nominatim; Website-Check per Domain-Raten + Suche; Konkurrenz-Check (Mitbewerber, Reibungspunkte, Strategie) |
| Briefe | `src/briefe.py`, `src/vorlagen/`, `src/hochladen.py` | DIN-5008-PDF, `--ki gemini`, belegbarer Konkurrenz-Satz im Brief, SFTP-Upload und Druck nur mit Token |
| Pläne / Widgets | `src/planer.py`, `src/web/plan.js` | Plan = Boxen (liste/notiz/zeitplan/zahlen), gespeichert in `data/plaene/` + Vault; Widget-Typ `eigen` |
| Graphen | `src/graphen.py`, `src/web/graph.js` | Gedächtnis-Graph aus dem Vault, Code-Graph über `graphify update <pfad>` (ohne KI, legt `graphify-out/` im Projekt an) |
| Panel | `src/web/dashboard.html` + `klaus.js` (Reaktor-Kern), `core.js` (Zustände, Denk-Graph, Debug-Panel Strg+Alt+D), `holo.js` (Fenster, Rahmen, Neigung), `popups.js` (Pop-ups, Leuchtlinien, Weiterleitung auf Bildschirm 2) | Dieselbe Seite läuft zweimal: Panel und `dashboard.html?zweit=1` auf Bildschirm 2 |
| Daten | `src/daten.py` | Wetter, Nachrichten, Kurse, System, Projekte, Layout (`data/layout.json`, Version 2 = Anteile 0..1) |

Git: Repo auf GitHub. `.env`, Leads, Briefe, Pläne, Layout, Einstellungen, Logs, Browser-Profil und
Sprachmodelle (`data/stimmen/`, über 500 MB) sind in `.gitignore`. Sicherung der Historie vor dem Bereinigen:
`..\klaus-sicherung-vor-github.bundle` (lokal, enthält die alten Sprachmodelle).

## 3. Harte Regeln (aus echten Fehlern)

1. Projekt-venv benutzen: `.venv\Scripts\python.exe`. `python` in Git Bash ist ein anderes (hermes-)venv.
2. **Kein Python mit Backslashes über Bash-Heredocs** (`\n`, `\b` gehen kaputt). Edit/Write nutzen oder ein
   Skript in den Scratchpad schreiben und ausführen. Auch PowerShell-Befehle mit `'\'` oder JS-Pfeilfunktionen
   lösen den Sicherheitsfilter aus → als Datei ablegen.
3. **JSON-Einstellungen nie mit PowerShell `Out-File` schreiben** (BOM). Richtige Werte:
   `{"panel": true, "taskleiste_original": false, "thema": "gold", "autostart": true}`.
4. Nur eine Klaus-Instanz gleichzeitig. Beenden:
   `Get-CimInstance Win32_Process | ? CommandLine -like "*klaus_app.py*" | % { Stop-Process -Id $_.ProcessId -Force }`
5. **UI nur über echte Aufnahmen prüfen, und nur vom Klaus-Fenster**: per `PrintWindow` auf das Fenster
   „Klaus Desktop“ bzw. „Klaus Bildschirm 2“, nie den ganzen Bildschirm. Eine Vollbildaufnahme hat einmal
   Nikolas private ELSTER-Seite erwischt. Meist ist VS Code im Vordergrund.
6. Vor UI-Tests, die Widgets anlegen: `data/layout.json` sichern und danach zurückspielen (Hash vergleichen).
7. Nikola spielt manchmal (League of Legends) → dann Klaus nicht neu starten und nichts aufnehmen.
8. Claude nur auf ausdrücklichen Wunsch. Gemini-Google-Search-Grounding ist im Gratis-Tarif 429.
9. Recht (DE): keine Kalt-Mails, keine automatischen KI-Kaltanrufe (UWG §7) → Briefe. KI muss sich am Telefon
   zu erkennen geben (EU AI Act). DSGVO für gespeicherte Personendaten.
10. Produkt-Lizenzen: Piper-Stimmen (teils GPL), edge-tts (inoffiziell), Marvel-Namen/-Marken → vor dem Verkauf
    ersetzen. Fish-Speech-Gewichte sind **nicht kommerziell** (CC-BY-NC-SA).
11. **Testen über das DevTools-Protokoll:** Klaus mit `QTWEBENGINE_REMOTE_DEBUGGING=9222` starten, JS per CDP
    ausführen. Es gibt **zwei** Seiten mit `dashboard.html` (Panel und `?zweit=1`) → gezielt die richtige wählen.
    Danach Klaus ohne Debug-Port neu starten.
12. Leistung immer messen, nicht raten: Leerlauf-CPU der QtWebEngine-Prozesse, Bildrate per
    `requestAnimationFrame`. **Keine Endlos-CSS-Animationen im Ruhezustand** (erzwingen 60 Bilder/s), Animationen
    nur über `transform`/`opacity`, kein `backdrop-filter` auf Pop-ups über dem animierten Reaktor.
13. Aus Git entfernen mit `git filter-branch`/`git rm --cached` löscht beim Auschecken auch die **lokalen**
    Dateien. Vorher sichern (Bundle) und danach zurückholen.
14. Die Overpass-Server (OpenStreetMap) fallen zeitweise aus (406/504/Timeout). Im Gespräch kurze Timeouts nutzen
    und dem Nutzer ehrlich sagen, dass OSM gerade nicht antwortet.
15. Vollbild-Erkennung: `SHQueryUserNotificationState` meldet „Vollbild“ auch wegen des eigenen Panels. Zählen
    nur Zustand 3/4 oder ein randloses, nicht maximiertes, fremdes Fenster (nicht der Windows-Desktop).

## 4. Was in der Sitzung vom 05.10.2026 passiert ist

- **Phase A, Design:** Stark Holo-Tech im echten Panel (abgeschrägte Glasfenster, SVG-Leuchtrahmen, neue
  Schriften, Telemetrie mit Balken, Bühne mit Lichtkegel und Boden). Nikola mochte die dunkle Glaslinse nicht →
  **Reaktor-Kern** (Portalring, weißer Kern, Lichtstrahlen, Tunnelringe) mit Sternbild im graphify-Stil.
- **Denken als Graph:** Pipeline-Schritte als Knoten im Reaktor, Werkzeuge als Blätter. Gedächtnis- und
  Code-Graph als Fenster.
- **Phase B, Leistung:** Leerlauf 4,5 → 2,8 % CPU, Arbeitsmodus stabil 60 fps.
- **Phase C, Freigabe-Gate.**
- **Phase D:** Lagebericht (Welt → DE → Region → Märkte → Zahlen) und Konkurrenz-Check (Strategie-Kreis, Satz im Brief).
- **Phase F, Rechte:** Fenster, Dateien, winget, System; Admin per UAC.
- **Phase G, Sicherheit:** Defender, Wächter, Widget; Schutz für Klaus (Log, Prompt-Injection, `.env`-Rechte).
- **Neue Wünsche:** 3D-Globus mit Ereignis-Animationen (Krieg, Frieden, Geld, Kriminalität …), zweiter
  Bildschirm, Plan-Board und eigene Widgets auf Zuruf.
- **GitHub:** Historie von Sprachmodellen und Laufzeitdateien bereinigt, README, `.env.example` und Handoff neu.

## 5. Roadmap

Erledigt: **A** Design · **B** Leistung · **C** Freigabe-Gate · **D** Lagebericht + Konkurrenz-Check ·
**F** Rechte · **G** Sicherheit · Globus · Bildschirm 2 · Pläne/Widgets.

### Offene Punkte aus den erledigten Phasen
- Globus und Lagebericht laufen in der Regionsansicht mit ~55 statt 60 fps. GPU und Skript sind es nicht, Ursache
  vermutlich die Qt-Bildzusammensetzung im Hauptthread. Einen Versuch wert: Globus-Punkte in ein Offscreen-Canvas
  je Drehwinkel zwischenspeichern.
- Konkurrenz-Check mit echten OSM-Daten noch nicht im Live-Test (Overpass war ausgefallen, die Logik ist mit
  Testdaten geprüft).
- Helligkeit lässt sich an externen Monitoren nicht steuern (keine WMI-Unterstützung). Möglich wäre DDC/CI über
  die Bibliothek `monitorcontrol`, falls Nikola das will.
- Eigene Widgets lassen sich per Stimme ändern, aber noch nicht per Tastatur bearbeiten (gewollt: „nur Stimme“).

### Phase E — Natürlichere Stimme (wartet auf Nikola)
- Entscheidung: kostenpflichtige **Fish Audio API** (kommerzielle Bedingungen vor dem Verkauf prüfen).
- Offen: Gemini-Live-Stimme behalten oder Gemini-Text + Fish-Stimme (mehr Latenz)? Prototyp + A/B-Test mit
  Nikola. Braucht einen Fish-Audio-Schlüssel.

### Phase H — Kalender & Meetings (wartet auf Nikola)
- Frage: Google Kalender oder Outlook? Dann OAuth, „Was steht morgen an?“, Termine anlegen (mit Freigabe),
  Erinnerungen im Briefing.
- Meetings: zuerst Klaus als **Protokollant** (faster-whisper, Zusammenfassung + Aufgaben in den Vault).
  Mitsprechen nur mit KI-Hinweis (AI Act) und Zustimmung aller.

### Phase I — Markt-Analyse & Trading
- Zuerst nur lesend: Watchlist, Stimmung je Ticker, Indikatoren, Markt-Briefing (Daten: Yahoo, schon vorhanden),
  Papier-Depot.
- Echte Orders nur über dafür gemachte Plattformen. Kandidat: **Liquid** (liquid.trade) → API, Märkte,
  Verfügbarkeit in DE und Gebühren prüfen; Alternative Interactive Brokers.
- **Jede Order über das Freigabe-Gate**, harte Limits, Not-Aus, erst Papier-Trading, Protokoll im Vault.
- Die gespeicherte Warnung zu KI-Trading-Bots zeigen. Kein Auto-Trading ohne ausdrückliches, wiederholtes Ja.

### Phase J — Telefonnummer & Anrufe (verschoben, kostet Geld)
- Twilio-Nummer DE (~1,35 $/Monat), eingehende Anrufe über Gemini Live (Media Streams), Termine in den Kalender.
  Ausgehend nur an Leute mit Einwilligung bzw. Bestandskunden. KI-Hinweis am Anfang.

### Phase K — Produkt / Klaus verkaufen
- Editionen: Basis (Gamer/Power-User) und Pro (Freelancer/kleine Firmen).
- Preis-Ideen: Done-for-you (~4.000 € einmalig + Monatsbeitrag inkl. KI über eigenen Proxy) oder Bring-your-own-API
  (~2.000–3.000 € einmalig, eigene Schlüssel).
- Lizenzschlüssel + Funktions-Schalter je Kunde, eigene Persona/Stimme/Marke.
- Vorher: GPL-/inoffizielle Teile ersetzen, Marvel-Bezüge entfernen, **Setup-Assistent statt fester persönlicher
  Daten** (Name, Ort, Mikrofon, Spiele, „Nikola.md“ sind noch im Code), Installer, DSGVO-Texte, AVV für den
  Proxy, Support-Prozess.
- Kostenlose KI-Kontingente nur zum Testen, nie im verkauften Produkt.

## 6. Offene Fragen an Nikola
- Kalender: Google oder Outlook?
- Fish Audio: Gemini-Stimme im Gespräch behalten oder Gemini-Text + Fish-Stimme?
- Trading: Liquid prüfen + erst Papier-Trading, okay?
- „Video“ (frühere Idee): was genau gemeint ist (Bildschirm/Kamera an Gemini Live, Videoanrufe, Video-Erzeugung)?
- Fehlt noch in `.env`: `KLESRO_ADRESSE`, `KLESRO_TELEFON`, SFTP-Zugang (für Briefe/Upload).
- Das GitHub-Repo ist privat (ohne Anmeldung 404). So lassen, bis der Setup-Assistent (Phase K) die
  persönlichen Daten (Name, Ort, Mikrofon, Spiele) aus dem Code geholt hat.
