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

### Telegram (05.10.2026, Wunsch Nikola: „Klaus auf eine Chat-Plattform“)
- Entscheidung: **Telegram** (WhatsApp nur über Meta-Business + zweite Nummer, inoffizielle Wege = Sperr-Risiko).
- `src/telegram_bot.py`: Long Polling (kein offener Port), nur `requests`. Gemini-**Textmodell** mit denselben
  Werkzeugen wie Gemini Live (ohne `gespraech_beenden`/`stumm_schalten`), Verlauf ~12 Wortwechsel.
  Sprachnachricht rein → lokales Whisper (`ohr.model`) → Antwort als Sprachnachricht (Edge/Piper → OGG/Opus mit PyAV,
  **nie Fish** wegen Credits).
- Sicherheit: nur `TELEGRAM_NUTZER`; Koppeln einmalig mit `/start <TELEGRAM_KOPPELCODE>`, danach PIN (sha256 in der
  .env, PIN-Nachrichten werden gelöscht). Freigabe-Anfragen gehen als Knopf an Telegram, wenn du dort aktiv bist
  (15 min) oder ≥10 min keine Eingabe am PC war; „Freigeben“ → PIN → `freigabe.entscheide(id, True, "Telegram + PIN")`.
  3 falsche PINs → abgebrochen + 15 min Sperre. Freitext „Freigeben“ zählt nicht.
- `assistent.sage()` schickt an Telegram statt zu sprechen, solange du zuletzt per Telegram (nicht per Stimme)
  geschrieben hast. Termin-Erinnerungen gehen zusätzlich aufs Handy, wenn du weg bist.
- Getestet: Werkzeug-Schleife (Kalender, Depot), OGG-Erzeugung, Whisper auf OGG. **Mit echtem Bot noch nicht**
  (Token fehlt). Anrufe kann die Bot-API nicht; dafür bräuchte Klaus ein eigenes Konto/eine eigene Nummer.

### Server-Gehirn (06.10.2026): Telegram läuft auf dem IONOS-Server
- **Aufteilung:** Der Server (`217.154.85.0`, Benutzer `klaus`, `/home/klaus/klaus`, systemd-Dienst `klaus-gehirn`) beantwortet
  Telegram rund um die Uhr (`src/server_gehirn.py`, headless; PySide6 wird dort durch eine Attrappe ersetzt). Der PC ist der
  „Körper“ (Panel, Mikro, Apps, Drucken, Gedächtnis).
- **Verbindung** (`src/fernlink.py`): PC baut per SSH zwei Tunnel auf (`klaus_tunnel`-Schlüssel, auf dem Server nur
  Weiterleitung, keine Shell): Server `127.0.0.1:7701` → PC-Werkzeug-Server `:7700`; PC `:7702` → Server-Meldungen. Jede Anfrage
  braucht `KLAUS_LINK_TOKEN`. Der SSH-Prozess hängt in einem Windows-Job (stirbt mit Klaus), alte Reste werden beim Start beendet.
- **Werkzeuge:** nur Kalender, Recherche, Markt-Analyse laufen auf dem Server; alles andere (Gedächtnis, Depot, Apps, Mikro,
  Drucken, Protokoll …) geht über den Tunnel an den PC. Ist der PC aus, sagt Klaus das ehrlich und führt nichts aus.
  Gedächtnis-Kontext holt der Server vom PC (Cache `data/gedaechtnis_cache.txt`).
- **Freigaben:** PC-Aktionen fragen auf dem PC an; `FernProxy` meldet sie dem Server → Telegram-Knopf + PIN → Server ruft
  `/entscheide` am PC. Die PIN-Prüfung liegt auf dem Server (Hash in dessen `.env`).
- **Schalter:** PC-`.env` `TELEGRAM_AUF_SERVER=1` (PC startet keinen eigenen Bot, Erinnerungen laut aus). **Rückfall:** Wert auf `0`
  setzen oder Zeile löschen, Klaus neu starten, auf dem Server `systemctl stop klaus-gehirn` (nur ein Bot darf abfragen!).
- Server-`.env` (nur Gemini, Telegram, Apple-Kalender, Link-Token; kein Fish/SFTP), `TELEGRAM_MODELLE` mit schnellen Modellen
  zuerst, `KLAUS_ERINNERUNG_NICHT=Frühstück|Mittagessen|Abendessen`. Werkzeug-Ergebnisse werden bei Modellwechsel nicht doppelt
  ausgeführt. Whisper (small, CPU) lädt erst bei der ersten Sprachnachricht.
- **Backup** (`server/klaus-backup.sh` → `/usr/local/sbin/`, Timer 03:30): verschlüsselt (age) nach `Tenktv/Klaus-back-up-`
  (Repo wird jedes Mal neu aufgebaut, nur aktuelle Stände). Täglich Datenbank + Konfiguration + Server-`.env`/`data`, sonntags die
  Website (45-MB-Stücke), dazu das **PC-Archiv** (`src/pc_backup.py`: Vault, `data/` ohne `stimmen`/`browser`, `.env` – der PC
  verschlüsselt selbst mit `KLAUS_BACKUP_OEFFENTLICH`, schickt es täglich über den Tunnel an `/backup`, der Server hält die
  letzten 7). Bei einem Fehler meldet das Skript per Telegram. Wiederherstellen: `WIEDERHERSTELLEN.md` im Backup-Repo; der
  geheime Schlüssel liegt nur bei Nikola (`KLAUS-BACKUP-SCHLUESSEL.txt`). **Falle:** Der Klaus-Ordner auf dem Server enthält
  `.venv` (hunderte MB) - nie komplett sichern (GitHub-Grenze 100 MB je Datei).
- **Selbst-Update** (`src/selbst_update.py`, 06.10.2026): Telegram „Update dich“ → Werkzeug `update_einspielen` (nur Server) zeigt
  neue Commits aus `origin/main` → Freigabe-Art „update“ (Knopf + PIN) → `git merge --ff-only`, danach Test (alle Module
  kompilieren + `server_gehirn` laden). Schlägt der Test fehl: `git reset --hard` auf den alten Stand + Meldung. Klappt er:
  Marker schreiben, Prozess beendet sich, systemd startet neu, beim Start Meldung „Wieder da, Update alt → neu“ mit Liste.
  Nur der Server wird aktualisiert (der PC ist die Entwicklungs-Kopie). Neue Python-Pakete muss man auf dem Server von Hand
  nachinstallieren.
- Gesicherte Werkzeuge (PC): `claude_remote_starten` (Terminal mit `claude --remote-control` in „Neuer Ordner (5)“) und
  `pc_ausschalten` (herunterfahren/neustart mit 60 s Vorlauf, `abbrechen` ohne Freigabe) - beide nur mit Knopf + PIN.
- **Nicht gebaut:** Bildschirm sehen, Maus/Tastatur/Browser bedienen, freie Shell, Claude Code auf dem Server mit Zugriff auf
  PCs. Zwei Anläufe am 06.10.2026 wurden vom Sicherheitsfilter gestoppt; Nikola hat Einspruch bei Anthropic eingereicht.
  Erst nach dessen Antwort einen einzigen neuen Versuch, sonst nicht wieder anfangen.
- Gegen „bei Claude abgemeldet“: `claude setup-token` (langlebiger Token) als Umgebungsvariable `CLAUDE_CODE_OAUTH_TOKEN`.
- **Morgen-Briefing** (`src/briefing.py`, Server): täglich 07:00 (deutsche Zeit) Wetter, Termine heute, 5 Schlagzeilen –
  ohne Gemini (spart Kontingent). `/briefing` jetzt, `/briefing 7:30`, `/briefing aus|an`; Einstellung `data/briefing.json`.
  Eigene Telegram-Befehle registriert der Server über `tg.befehle`.
- **Foto → Kalender** (`telegram_bot.termine_aus_bild`, `_foto`): Foto eines Plans per Telegram → Gemini liest die Termine →
  Liste zur Kontrolle → Freigabe (Knopf + PIN) → `kalender.anlegen_mehrere` (eine Freigabe für alle, Doppelte mit gleichem Titel
  und Beginn werden übersprungen). „Arbeit“/„Privat“ im Foto-Text wählt den Kalender. Erkennung am Seminarplan: erster Versuch
  nur 1 von 5 Tagen → Anweisung für Wochenpläne nachgeschärft, **Nachtest offen** (Gemini-Kontingent war aufgebraucht).
- **Watchlist + Alarme** (`src/watchlist.py`, Server, 07.10.2026, ohne KI-Anfragen): `/watchlist` (Kurse), `/watchlist add|weg <Name>`,
  `/alarm <Name> unter|über <Preis>`, `/alarm` (Liste), `/alarm weg <Nr>`; dazu Werkzeuge `watchlist_verwalten`/`alarm_verwalten` für normale
  Sprache. Alle 10 Minuten (`TAKT_S`) ein Yahoo-Abruf je Wert; Alarm löst **einmal** aus (Telegram) und ist danach „erledigt“;
  automatische Meldung bei Tagesbewegung ≥ 5 % (`SPRUNG_PROZ`, einmal je Wert und Tag); Watchlist-Zeile im Morgen-Briefing. Schwellen gelten in
  der Währung des Wertes (USD bei US-Aktien). Wert von der Watchlist nehmen löscht dessen Alarme. Daten `data/watchlist.json` (im Backup).
  Nur Information, keine Anlageberatung, keine Orders. Getestet: Parser (deutsche Zahlen), Einmal-Auslösung, echte Kurse (NVDA, SAP, BTC, DAX).
- **Lebenszeichen im Chat** (`telegram_bot._Lebenszeichen`): „Klaus schreibt …“ dauerhaft, ab 8 s eine stille Statusmeldung je Werkzeug
  (`STATUS_TEXTE`), die nach der Antwort gelöscht wird. **Tempo:** einfache Textaufgaben zuerst über Groq (`ERSATZ_ZUERST=0` schaltet ab),
  Gemini höchstens 2 Modelle à 25 s, jedes Werkzeug max. 150 s (`_werkzeug_sicher`).
- **Ersatz-KI** (`src/ersatz_ki.py`, 07.10.2026): Fällt Gemini aus (503/504/Zeitlimit/429), fragt Klaus Groq (`GROQ_API_KEY`, OpenAI-Format,
  austauschbar über `ERSATZ_KI_URL`). Chat mit Werkzeugen (`_antworten_ersatz`), Foto→Termine (`bild_json`, am Seminarplan alle 5 Tage/28
  Termine in 4 s), Textfragen (`recherche.gemini`). **Groq-Grenzen (kostenlos): 8.000 Token/Min je Modell** → nur passende Werkzeuge senden
  (`_passende_werkzeuge`, Stichwortgruppen, 5–16 statt 53), Beschreibungen gekürzt, alle Modelle der Reihe nach (gpt-oss-120b zuerst; dieses
  Konto sieht: gpt-oss-120b/20b, qwen3.8-27b, allam-2-7b). `recherche.GEMINI_AUS_BIS`: nach einem Ausfall 180 s lang gleich Ersatz-KI
  (Nvidia-Analyse 4,6 s statt 69 s). Gemini-Zeitlimit 45 s je Anfrage, 200 s je Nachricht (zuvor blockierte eine hängende Anfrage den Chat).
  Ersatz-Antworten haben dieselben Freigaben. Der Schlüssel liegt in den `.env` von Server und PC (nie im Repo).
- **Server-Sicherheit** (07.10.2026): `fail2ban` (SSH: 4 Fehlversuche/10 min → 24 h Sperre, Journal-Backend, nftables; Test mit RFC-5737-Adresse),
  `clamav` (kein Dauerdienst, Datenbank per `klaus-freshclam.timer` täglich 04:30 UTC; `clamav-freshclam`-Daemon bleibt AUS: 650 MB RAM),
  2 GB Swapfile (`vm.swappiness=10`), **Klaus-Wächter** (`server/klaus-waechter.py` → `/usr/local/sbin`, root, nur Standardbibliothek):
  täglich 05:00 UTC Zustand gegen `/var/lib/klaus-sicherheit/basis.json` vergleichen (Konten, UID 0, SSH-Schlüssel als Prüfsumme, offene Ports,
  aktivierte Dienste, Container, SUID-Dateien, Prüfsummen wichtiger Dateien: sshd, sudoers, cron, Caddyfile, compose, klaus-Skripte, ufw),
  Klaus-Code lokal verändert?, neue Anmelde-Adressen, Firewall aus, Virendatenbank > 72 h; bei Abweichung Telegram (nur einmal je Befund).
  ClamAV-Wochenscan sonntags 02:00 UTC über /var/www, /opt/klesro, /home/sftpuser, klaus/data, /tmp (erster Lauf: 9.051 Dateien, 123 s, 0 Funde,
  Spitze 1,1 GB RAM). Bericht `report.json` (keine Geheimnisse). **Klaus-Seite** (`src/server_sicherheit.py`): `/sicherheit` (Server + PC über
  `sicherheit_status`), `/sicherheit scan` (ClamAV + Defender-Schnellscan), `/sicherheit basis` (Normalzustand neu setzen, nur mit Freigabe
  Knopf + PIN), Werkzeug `sicherheit_gesamt`. Der Benutzer `klaus` kann nur eines von `pruefen|scan|basis` in `/var/lib/klaus-sicherheit/auftrag`
  schreiben; ein systemd-Pfad (`klaus-auftrag.path`) startet dann den Wächter als root (feste Whitelist).
  **Nach jeder Server-Wartung** (neue Dienste, Pakete, Konfig): `/usr/local/sbin/klaus-waechter.py basis` oder `/sicherheit basis`.
  Offen: sftpuser hat noch Passwort-Login (Match-Block, nur SFTP im chroot) - fail2ban schützt jetzt; ggf. auf Schlüssel umstellen.
- **Markt-Analyse erweitert** (`markt.py`, 07.10.2026): Rechnung auf 1 Jahr Kursdaten (Panel zeigt die letzten 130 Tage). Neu: Bollinger-Bänder
  (20, 2σ, %B, Squeeze), ATR-Schwankung, Unterstützung/Widerstand (Umkehrpunkte, 1,5 % zusammengefasst, Berührungen), Volumen-Verhältnis,
  Golden/Death Cross (SMA 50/200, nur wenn ≤ 30 Tage her), 52-Wochen-Abstand → `signale` (Texte) und `niveaus`; Vorlesetext nennt die ersten drei.
  Nachrichten aus Google News + Yahoo Finance (abwechselnd, ohne Doppelte); mit `NEWSAPI_KEY` in der `.env` kommt NewsAPI.org dazu (optional,
  Free-Tarif nur Entwicklung/verzögert). Panel (`markt.js`): Bänder gestrichelt, Niveaus als Linien (U/W), neue Kennzahlen, Hinweisliste, Quelle je Meldung.
  Getestet: Bollinger/52W an synthetischen Daten nachgerechnet, echte Werte (NVDA, SAP, BTC), Panel-Foto nur vom Klaus-Fenster.
- **Zeitzone:** Der Dienst läuft mit `TZ=Europe/Berlin` (vorher UTC → Erinnerungen kamen 2 h zu spät, behoben 06.10.).
- `kalender.loeschen`: iCloud lehnt die UID-Suche ab (412) → Rückfall über Zeitraum-Suche.
- **Gemini-Kontingent:** kostenlos nur **20 Anfragen pro Tag und Modell** (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`).
  Telegram nutzt mehrere Modelle nacheinander, `flash-lite` als Letztes. Mit Abrechnung bei Google AI Studio wären die Grenzen viel
  höher (Kosten für Klaus' Nutzung: Cent-Bereich) – Entscheidung Nikola. Tests sparsam machen!
- Offen: Angebote/Rechnungen als PDF (braucht Nikolas Firmendaten: Adresse, Steuernummer, Kleinunternehmer ja/nein, IBAN),
  Server-Dienst bei Absturz melden, Dateien (PDF, Charts) in den Chat senden, ESP32 zum Aufwecken des PCs.

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
