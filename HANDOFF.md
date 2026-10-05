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
**F** Rechte · **G** Sicherheit · Globus · Bildschirm 2 · Pläne/Widgets ·
**E** Fish Audio (Code fertig, wartet auf Schlüssel) · **H** Apple Kalender (Code fertig, wartet auf Zugang) +
Meeting-Protokollant · **I** Markt-Analyse + Papier-Depot (nur lesend).
Konkurrenz-Check am 05.10.2026 live geprüft (Bäckerei in Göppingen: 36 Mitbewerber im 5-km-Umkreis, 11 online,
0,9 s). Die Abfrage nutzt jetzt ein Rechteck statt `around`; mit `around` lief sie auf den Spiegel-Servern in den Timeout.

### Offene Punkte aus den erledigten Phasen
- Globus und Lagebericht laufen in der Regionsansicht mit ~55 statt 60 fps. GPU und Skript sind es nicht, Ursache
  vermutlich die Qt-Bildzusammensetzung im Hauptthread. Einen Versuch wert: Globus-Punkte in ein Offscreen-Canvas
  je Drehwinkel zwischenspeichern.
- Helligkeit lässt sich an externen Monitoren nicht steuern (keine WMI-Unterstützung). Möglich wäre DDC/CI über
  die Bibliothek `monitorcontrol`, falls Nikola das will.
- Eigene Widgets lassen sich per Stimme ändern, aber noch nicht per Tastatur bearbeiten (gewollt: „nur Stimme“).

### Phase E — Natürlichere Stimme: Fish Audio (gebaut, wartet auf Schlüssel)
- Entscheidung Nikola (05.10.2026): **Fish Audio**. `src/fish.py`: `POST https://api.fish.audio/v1/tts`
  (Bearer, Header `model` = `s2.1-pro`, `format=pcm`, 24 kHz, `latency=balanced`). In `gemini_live.py`
  denkt Gemini weiter, Klaus spricht aber Geminis Mitschrift satzweise mit Fish (`_fish_sprecher`); Geminis
  eigenes Audio wird verworfen. Unterbrechen verwirft angefangene Sätze. **Fällt Fish aus (401/402/Netz),
  schaltet die Sitzung automatisch auf die Gemini-Stimme zurück.** Lokale Kette: `KLAUS_STIMME=fish`.
- Stimme: **eigene per Voice Design** (`python src/fish.py entwerfen "<Beschreibung>"` → Kandidaten anhören →
  `anlegen <nr>` schreibt `FISH_STIMME` in die .env). Community-Stimmen sind oft Nachbildungen echter Personen
  (Persönlichkeitsrecht!), nur 1 deutsche Stimme ist als lizenziert markiert → fürs Produkt nur eigene Stimmen.
- Kosten: ca. 15 $ / 1 Mio. Zeichen; kommerzielle Nutzung nur mit Plus/Pro-Abo. Gemini erzeugt weiter Audio
  (kleine Zusatzkosten); später ggf. Gemini-Live im TEXT-Modus testen, falls das Modell es kann.
- Noch zu tun mit Nikola: Schlüssel eintragen, Stimme entwerfen, A/B gegen Gemini „Charon“, Latenz messen.

### Phase H — Kalender & Meetings
- Entscheidung Nikola: **Apple Kalender** → `src/kalender.py` über CalDAV (`caldav.icloud.com`, Bibliothek caldav
  unter Apache-2.0). Braucht `APPLE_ID` + **App-spezifisches Passwort** (`APPLE_APP_PASSWORT`, appleid.apple.com).
  Fertig: „Was steht morgen/Freitag/am 24.12. an?“, Gemini-Werkzeuge `kalender_lesen`, `termin_eintragen`
  (Freigabe-Art „kalender“, warnt bei Überschneidung), `zeit_frei`; Kalender-Widget (7 Tage); Termine im
  „Seit du weg warst“-Briefing; Erinnerung 15 min vorher (still, wenn stumm). Auswertung offline getestet
  (Zeitzone, ganztägig, Dauer). **iCloud-Zugang seit 05.10.2026 eingerichtet**: Anmeldung ok, Kalender „Privat“
  und „Arbeit“ (+ „Erinnerungen“, nur Aufgaben) gefunden; Test-Termin per Gate angelegt
  und wieder gelesen (ok). Die Erinnerungen-Liste (nur Aufgaben) wird ausgefiltert.
- **Protokollant fertig (05.10.2026):** `src/protokoll.py` + Holo-Fenster `web/protokoll.js`. „Klaus, starte ein
  Protokoll für Kunde Maier“ → Freigabe-Art **„aufnahme“** (Nikola bestätigt die Zustimmung aller, § 201 StGB) →
  Klaus sagt die Aufnahme laut an (steht damit auch in der Mitschrift). Mikrofon → 25-s-Happen (Schnitt an leiser
  Stelle) → faster-whisper (dasselbe Modell wie `voice.Ohr`, Titel als Namens-Hinweis). **Ton wird nie
  gespeichert**, die Notiz `Vault/Meetings/<Datum Uhrzeit> <Titel>.md` wird laufend geschrieben (absturzsicher).
  „Klaus, Protokoll beenden“ → 1 Gemini-Textaufruf: Zusammenfassung, Entscheidungen, Aufgaben (`- [ ]`).
  Höchstens 3 h. Gemini-Werkzeuge `protokoll_starten` / `protokoll_beenden`. Mit TTS-Audio getestet, **mit
  echtem Gespräch noch nicht**. Offen: Online-Meetings (Teams/Zoom) bräuchten System-Ton (WASAPI-Loopback,
  z. B. `pyaudiowpatch`) – bisher nur Mikrofon. Wer im Meeting „Klaus“ sagt, weckt ihn auf.
- Mitsprechen im Meeting nur mit KI-Hinweis (AI Act) und Zustimmung aller – noch nicht gebaut.

### Phase I — Markt-Analyse & Trading
- **Lesender Teil fertig (05.10.2026):** `src/markt.py` (Yahoo Chart/Suche, RSI 14, SMA 20/50, EMA, MACD,
  Nachrichten-Stimmung über Google News + 1 Gemini-Textaufruf) und das **Papier-Depot** (`data/depot.json`,
  10.000 € Spielgeld, max. 25 % je Order). Panel: Holo-Fenster `markt` (`web/markt.js`, Kurs- + RSI-Chart,
  geht auf Bildschirm 2) und das Widget „Papier-Depot“. Sprache: „analysier Nvidia“, „wie steht der Dax“,
  „kauf für 1000 Euro Nvidia im Papierdepot“, „wie läuft mein Depot“. Gemini-Werkzeuge: `markt_analyse`,
  `papier_order`, `depot_status`. Echte Orders gibt es **nicht**.
- **Liquid geprüft (05.10.2026):** LiquidX AI, Inc. (Delaware), gegründet 2025. **Keine Lizenz/Regulierung**
  gefunden. Nicht-verwahrend; Gelder liegen auf Hyperliquid/Lighter (Krypto-Perps) bzw. Ostium/Arbitrum
  (Aktien/FX/Rohstoffe als Perps) → Risiko dieser DeFi-Plattformen. Bis 40x (Krypto) / 50x (FX, Indizes) Hebel,
  24/7. Gebühren z. B. 0,095 % Taker bei Krypto-Perps (Hyperliquid 0,045 % + Liquid 0,05 %), Auszahlung 1 $.
  Für Agenten: MCP-Server `https://coinvest.liquid.trade/mcp` (OAuth 2.1, Scopes `read` / `trade`, Trades mit
  Bestätigungsschritt) + REST-API mit Schlüsseln; **Paper-Trading-Modus** vorhanden.
  **EU/DE:** ESMA (Feb. 2026): Perpetual Futures fallen unter die CFD-Regeln → für Privatkunden Hebel max. 30:1
  (FX-Majors) … 2:1 (Krypto), 5:1 (Einzelaktien), Nachschusspflicht verboten. Liquids 40-50x entsprechen dem
  nicht; deutscher Anlegerschutz/Einlagensicherung fehlt.
- Empfehlung: Liquid höchstens **lesend + Paper-Trading** (Scope `read`) für Klaus' Markt-Analyse. Echtgeld,
  wenn überhaupt, nur über einen in der EU regulierten Broker mit API (z. B. Interactive Brokers) und nur über
  das Freigabe-Gate. Nikola entscheidet.
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
- Fish Audio: Schlüssel (Plus-Abo wegen kommerzieller Nutzung) eintragen, dann Stimme gemeinsam entwerfen.
- Apple Kalender: Apple-ID + App-spezifisches Passwort in die .env (nicht in den Chat schreiben).
- Trading: Liquid nur lesend + Paper-Trading, Echtgeld nur über regulierten Broker - einverstanden?
- „Video“ (frühere Idee): was genau gemeint ist (Bildschirm/Kamera an Gemini Live, Videoanrufe, Video-Erzeugung)?
- Fehlt noch in `.env`: `KLESRO_ADRESSE`, `KLESRO_TELEFON`, SFTP-Zugang (für Briefe/Upload).
- Das GitHub-Repo ist privat (ohne Anmeldung 404). So lassen, bis der Setup-Assistent (Phase K) die
  persönlichen Daten (Name, Ort, Mikrofon, Spiele) aus dem Code geholt hat.
