# K.L.A.U.S.

Sprachgesteuerter Desktop-Assistent für Windows. Klaus ersetzt den Windows-Desktop durch ein Holo-Panel im
„Stark Holo-Tech“-Stil, hört auf seinen Namen und erledigt Dinge am PC. Dazu gehören Apps öffnen, recherchieren,
Pläne bauen, Weltnachrichten auf einem Globus zeigen und den PC auf Sicherheitsprobleme prüfen. Außerdem
betreibt er die Kundengewinnung von Klesro Web: Er findet Betriebe ohne Website, prüft die Konkurrenz und
schreibt Briefe mit einem persönlichen Website-Entwurf.

> Status: persönliches Projekt, läuft täglich auf einem Windows-11-PC. Eine verkaufbare Version ist geplant
> (siehe [HANDOFF.md](HANDOFF.md), Phase K).

## Was Klaus kann

Experimenteller [Genshin-Modus](GENSHIN.md): lokales Bildmodell, begrenzte
Spieleingaben, F9-Not-Aus und Windows-Rechtediagnose. Noch kein nachgewiesener
autonomer Questabschluss. Der bestehende Spiele-Coach bleibt ebenfalls verfügbar.

| Bereich | Beispiele (einfach sprechen: „Klaus, …“) |
|---|---|
| **Gespräch** | Gemini Live mit eigener Stimme, man kann ihm ins Wort fallen. Ohne Schlüssel läuft eine lokale Kette (Whisper → Ollama → Stimme). |
| **PC steuern** | „öffne Steam“, „Fenster nach links“, „Lautstärke 30“, „Bluetooth aus“, „mach ein Bildschirmfoto“, „installier 7-Zip“ |
| **Panel** | Widgets frei verschieben und skalieren, eigene Widgets auf Zuruf („erstell ein Widget für meine Einkaufsliste“), 6 Farbpaletten („Design rot“) |
| **Pläne** | „lass uns die Website für die Bäckerei planen“: Ein Plan-Board aus Boxen (Schritte, Zeitplan, Budget, Risiken …) baut sich auf und lässt sich als Widgets anheften. |
| **Weltlage** | „Lagebericht“: Welt (3D-Globus mit Animation je Art der Meldung) → Deutschland → Region → Märkte → Kennzahlen. „Was ist in der Welt los?“ zeigt die Meldungen auf dem Globus. |
| **Wissen** | Recherche mit kostenloser Websuche + Gemini; Gedächtnis in einem Obsidian-Vault; „zeig dein Gedächtnis als Graph“; Code-Projekte als Graph (graphify) |
| **Leads** | Betriebe ohne Website über OpenStreetMap finden, Website-Check, Konkurrenz-Check, Briefe (DIN 5008, QR-Code zum Entwurf), Hochladen und Drucken nur mit Freigabe |
| **Sicherheit** | „scan den PC“ (Windows Defender), Wächter für neue Autostarts, Admin-Konten, offene Ports und unsignierte Programme |
| **Börse** | „analysier Nvidia“: Kurs-Chart mit SMA 20/50, RSI, MACD und Nachrichtenlage. **Papier-Depot** mit 10.000 € Spielgeld („kauf für 1000 Euro Nvidia im Papierdepot“). Keine echten Orders, keine Anlageberatung. |
| **Termine & Meetings** | Apple-Kalender (iCloud): „Was steht morgen an?“, Termine eintragen mit Freigabe. **Meeting-Protokoll** („starte ein Protokoll“): nur mit Freigabe und laut angesagt; lokal mitgeschrieben, Ton wird nie gespeichert, am Ende Zusammenfassung + Aufgaben im Vault. |
| **Telegram** | Von unterwegs mit Klaus chatten oder Sprachnachrichten schicken (er antwortet als Sprachnachricht). Erinnerungen und Meldungen kommen aufs Handy, wenn du nicht am PC bist. Nur dein Konto, Freigaben per Knopf + PIN. |
| **Zwei Monitore** | Große Ansichten (Lagebericht, Globus, Graph, Plan, Markt) wandern auf den zweiten Bildschirm, wenn er frei ist. |

Klaus fragt **Claude nur**, wenn man es ausdrücklich sagt („frag Claude …“). Standard ist Gemini mit kostenloser Recherche.

## Sicherheit: das Freigabe-Gate

Alles mit Wirkung nach außen läuft nur mit einem **Einmal-Token**. Dazu gehören Hochladen, Drucken, Löschen,
Verschieben, Programme installieren, Bluetooth aus, Fenster schließen, Termine eintragen, Gespräche aufzeichnen
und Admin-Befehle. Das Token entsteht
ausschließlich durch einen Klick auf „Freigeben“ im Panel oder wenn **du** „Freigeben“ sagst. Gezählt wird
dabei die Mitschrift deines Mikrofons, nie eine Entscheidung der KI. Die ausführenden Funktionen prüfen das
Token selbst (`src/freigabe.py`). Von unterwegs geht das nur per Telegram-Knopf **und** PIN; „Freigeben“ als
Chat-Text zählt bewusst nicht.

Klaus läuft nie dauerhaft als Admin. Einzelne, fest hinterlegte Befehle (Defender, Firewall) startet
`src/admin.py` per UAC. Webinhalte gelten für die KI als Daten, nicht als Anweisungen. Schlüssel werden im Log
geschwärzt. Jede Aktion am PC landet im Vault unter `Aktionen/<Datum>.md`.

## Installation

Voraussetzungen: Windows 10/11, Python 3.11, optional eine NVIDIA-Grafikkarte (Spracherkennung auf der GPU),
optional [Ollama](https://ollama.com) als lokales Rückfall-Modell.

```bat
git clone https://github.com/Tenktv/Klaus.git
cd Klaus
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env      &rem dann .env ausfüllen (mindestens GEMINI_API_KEY)
```

Starten (ohne Konsolenfenster, ersetzt den Desktop):

```bat
.venv\Scripts\pythonw.exe src\klaus_app.py
```

Klaus startet danach automatisch mit Windows (abschaltbar im Tray-Menü). Tastenkürzel: **Strg+Alt+K** schaltet
stumm, **Strg+Shift+M** schaltet das Mikrofon aus, **Strg+Alt+D** öffnet das Debug-Panel.

Piper-Stimmen (nur Rückfall ohne Gemini/edge-tts) sind nicht im Repo, weil sie zu groß sind. `Klaus.bat` lädt
bei Bedarf `de_DE-thorsten-high` nach `data/stimmen/`.

## Aufbau

```
src/
  pc_update.py        Auto-Update am PC aus GitHub (alle 30 min, in ruhigen Momenten, mit Test + Rueckfall)
  klaus_app.py        App: Panel, Bildschirm 2, Tray, Hotkeys, Autostart, Anwesenheit/Briefing
  assistent.py        Sprach-Schleife, Absichten, alle Abläufe (Leads, Briefe, Lagebericht, Pläne, Sicherheit …)
  gemini_live.py      Gemini-Live-Gespräch mit ~40 Werkzeugen
  gehirn.py           Persona, Gedächtnis (Obsidian-Vault), Claude nur auf Zuruf
  recherche.py        Websuche (Tavily -> ddgs, kostenlos) + Zusammenfassung (Gemini -> Ollama)
  freigabe.py         Freigabe-Gate (Einmal-Tokens)      admin.py   einzelne Admin-Befehle per UAC
  rechte.py           Fenster, Dateien, winget, Lautstärke, Bluetooth, Bildschirmfoto, Zwischenablage
  sicherheit.py       Defender, Firewall, Wächter mit Basislinie
  lage.py             Lagebericht-Daten     graphen.py  Gedächtnis-/Code-Graph     planer.py  Pläne
  markt.py            Markt-Analyse + Papier-Depot   kalender.py  Apple-Kalender   protokoll.py  Meeting-Protokoll
  fish.py             Fish-Audio-Stimme (optional)      telegram_bot.py  Chat von unterwegs
  osm_leads.py        Lead-Suche (OpenStreetMap)   konkurrenz.py  Konkurrenz-Check   briefe.py  Briefe   hochladen.py
  daten.py            Wetter, Nachrichten, Kurse, System, Projekte, Layout
  voice.py, stimme.py, llm.py   Whisper, Stimmen, Ollama
  web/                Panel (dashboard.html) + Module: klaus.js (Reaktor), core.js (Zustände, Denk-Graph),
                      holo.js (Fenster), popups.js (Pop-ups, Bildschirm 2), lage.js, globus.js, graph.js, plan.js
designs/              Design-Mockups (gewählt: hud_v1_stark)
```

Daten, die nur lokal bleiben (siehe `.gitignore`): `.env`, `data/leads.csv`, `data/briefe/`, `data/plaene/`,
Layout und Einstellungen, Logs, Browser-Profil und Sprachmodelle.

## Rechtliches für die Kundengewinnung

Werbe-E-Mails und automatische KI-Anrufe an Firmen brauchen in Deutschland eine Einwilligung (UWG §7).
Klaus nutzt deshalb **Briefe**. `src/generate_outreach.py` (Mail-Entwürfe) ist nur für bestehende Kontakte
gedacht. Eine KI am Telefon muss sich als KI zu erkennen geben (EU AI Act).

## Lizenzen von Fremdbestandteilen

- Schriften Chakra Petch, Barlow Semi Condensed, JetBrains Mono, Orbitron, Rajdhani: SIL Open Font License 1.1
- Weltkarten-Raster (`src/web/vendor/weltkarte.js`): erzeugt aus [world.geo.json](https://github.com/johan/world.geo.json)
- Vor einem Verkauf zu ersetzen: edge-tts (inoffizieller Endpunkt), Piper-Stimmen (teils GPL), Marvel-Bezüge
  (Details in [HANDOFF.md](HANDOFF.md))


## Installer, Name, Stimmen
- **Klaus-Setup.exe**: gebaut von `.github/workflows/installer.yml` (Inno Setup, `installer/klaus.iss` + `installer/einrichten.ps1`).
  Fragt den Namen des Assistenten (Weckwort), deinen Namen und optional Gemini-/Fish-Schluessel ab, installiert ohne
  Admin-Rechte nach `%LOCALAPPDATA%\Programs\Klaus`, richtet Python und Pakete ein.
  Release: Tag `vX.Y.Z` pushen -> Setup.exe erscheint im oeffentlichen Repo `Tenktv/Klaus-Download`
  (Secret `KLAUS_DOWNLOAD_TOKEN` noetig). Installierte Versionen holen sich Updates von dort (`pc_update.py`, SHA256-geprueft).
- **Stimmen** (`stimmwahl.py`): Gemini-Stimmen, Microsoft-Stimmen, Anime-Stil (Anime-Maedchen, Anime-Junge, Anime-Held,
  Anime-Boesewicht, Sensei, Chibi), lokale Piper-Stimmen (`data/stimmen/*.onnx`) und eigene: Variante mit Tonhoehe/Tempo,
  fertige Stimme von fish.audio per Link, Stimme beschreiben (Fish Voice Design), Sprachprobe in `data/stimmen/eigene/<Name>.mp3`.
  Umschalten per Sprache oder `/stimme <Name>`, Liste mit `/stimmen`.
