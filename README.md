# Klaus – Lead-Recherche & Erstkontakt für Klesro Web

Klaus ist der Arbeitsname für dein Automatisierungsprojekt: lokale Firmen im
Raum Göppingen finden, die noch keine Website haben, und den Erstkontakt
vorbereiten. Dieses Verzeichnis ist das Grundgerüst dafür – kein fertiges
Produkt, sondern ein Startpunkt, den du (oder Claude Code auf deinem Rechner)
weiterbaust.

## Was schon drin ist

- `src/search_leads.py` – durchsucht die Google Places API nach mehreren
  Branchen/Orten, filtert Treffer ohne Website heraus und schreibt sie in
  `data/leads.csv`.
- `src/generate_outreach.py` – liest `data/leads.csv` und erzeugt für jede
  Firma einen personalisierten E-Mail-Entwurf in `data/outreach/`.
- `.env.example` – zeigt, welche Zugangsdaten du brauchst.

## Voraussetzungen

1. Python 3.10 oder neuer.
2. Ein Google-Places-API-Key (Google Cloud Console → "Places API" aktivieren,
   Abrechnung einrichten – der kostenlose Umfang reicht für lokale Suchen
   locker aus) **oder** ein OpenWeb-Ninja-Key als Alternative.
3. `pip install -r requirements.txt`

## Einrichtung

```bash
cp .env.example .env
# .env öffnen und deinen API-Key eintragen
pip install -r requirements.txt
```

## Benutzung

```bash
# 1. Leads suchen (Ergebnis: data/leads.csv)
python src/search_leads.py

# 2. Briefe mit Website-Entwurf erzeugen (Ergebnis: data/briefe/<firma>/brief.pdf)
.venv/Scripts/python src/briefe.py
```

Die generierten E-Mails sind bewusst einfach gehalten (Platzhalter-Vorlage,
keine KI-Anbindung nötig). Sobald das läuft, ist der nächste sinnvolle
Ausbauschritt laut Architekturplan:

1. Gmail-Anbindung, damit die Entwürfe direkt als Gmail-Draft landen statt
   als Textdatei.
2. Einen Scheduled Task, der `search_leads.py` wöchentlich automatisch
   laufen lässt.
3. Telefonie (Twilio/Vapi), wenn E-Mail allein nicht reicht.

Details und Hintergrund stehen im Dokument "Klaus-Architektur für Klesro Web".

## Branchen & Orte anpassen

Beide Listen stehen oben in `src/search_leads.py` (`BRANCHEN` und `ORTE`) –
einfach ergänzen oder kürzen.

## Lokale KI (Ollama)

Klaus nutzt ein lokales Modell über Ollama (Standard: `gemma2:9b`, änderbar mit
`OLLAMA_MODEL` in `.env`). Keine Cloud-Kosten.

```bash
# Leads bewerten lassen + KI-Mails schreiben
python src/generate_outreach.py --ai
python src/generate_outreach.py --ai --leads data/leads_sample.csv   # Testdaten
```

## Sprachmodus: mit Klaus planen, Claude baut

```bash
# einmalig: eigene Umgebung für Klaus
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt faster-whisper sounddevice pyttsx3

.venv/Scripts/python src/voice.py              # Mikrofon + Stimme
.venv/Scripts/python src/voice.py --text       # tippen statt sprechen
.venv/Scripts/python src/voice.py --dry-run    # Claude nicht starten, nur Auftrag speichern
```

Einfach sprechen: Klaus erkennt selbst, wann du anfängst und aufhörst
(Pause ~1,2 s). Mit `--ptt` stattdessen per Enter-Taste. Nennst du eine Firma aus der
Leadliste, lädt Klaus deren Daten automatisch. Sprachbefehle:

- **"an Claude geben"** / "bau das" – Klaus fasst den Plan als Auftrag zusammen,
  zeigt ihn an und fragt nach. Bei "ja" baut Claude Code das Projekt in
  `data/projekte/<datum>-<firma>/` (Auftrag in `AUFTRAG.md`).
- **"neu anfangen"** – Gespräch zurücksetzen
- **"beenden"** – Schluss

Spracherkennung (Whisper `medium`) läuft auf der Grafikkarte, die Stimme ist
Piper "Thorsten" (lokal, `data/stimmen/`). Fällt etwas aus, nimmt Klaus CPU bzw.
die Windows-Stimme.

Optionen in `.env`: `KLAUS_SCHWELLE` (Sprech-Empfindlichkeit, 0 = automatisch),
`KLAUS_PAUSE` (Sekunden Stille bis Satzende), `KLAUS_STIMME` (Piper-Stimme),
`WHISPER_MODEL` (tiny/base/small/medium), `KLAUS_MIC`
(Teil des Mikrofonnamens, z.B. `USB`), `CLAUDE_PERMISSION_MODE` (Standard
`acceptEdits`: Claude darf im Projektordner Dateien anlegen/ändern).

## Klaus im Hintergrund (Desktop-Icon „Klaus“)

```bash
.venv/Scripts/pythonw.exe src/klaus_app.py      # ohne Konsolenfenster
```

Klaus sitzt als Symbol unten rechts in der Taskleiste und hört auf seinen Namen.
Dann erscheint ein animierter Orb in der Bildschirmmitte (Farbe je nach Zustand).

- „Klaus, öffne Spotify“ – Apps aus dem Startmenü, Webseiten (YouTube, Gmail …),
  Ordner (Downloads, Projekte …), Windows-Werkzeuge (Rechner, Einstellungen …)
- „Klaus, such nach …“ – Google-Suche
- „Klaus, Website für die Schreinerei Maier“ – Planungsgespräch ohne Weckwort;
  „an Claude geben“ → Auftrag öffnet sich zur Kontrolle → „ja“ → Claude baut im
  Hintergrund, Klaus meldet sich, wenn es fertig ist, und öffnet das Ergebnis
- „Klaus, wie spät ist es?“ – kurze Antwort der lokalen KI
- „Klaus“ allein – „Ja?“, dann den Befehl sagen

Taskleisten-Menü: Zuhören pausieren, Mit Windows starten, Stimme wählen,
Projekte-Ordner, Log (`data/klaus.log`), Beenden. Die Konsolen-Version gibt es
weiterhin über `Klaus.bat`.

## Gespräch: Gemini Live + Claude-Gehirn

Mit `GEMINI_API_KEY` in `.env` führt **Gemini Live** (automatisch das neueste reguläre
Live-Modell, Okt. 2026: `gemini-3.8-live`, erster Ton nach ~0,7 s) das Gespräch: zuhören,
verstehen, sprechen, unterbrechbar. Die Verbindung steht nur nach dem lokal erkannten
„Klaus“ und wird nach 20 s Stille geschlossen. Gemini handelt über Werkzeuge
(`src/gemini_live.py`: oeffne, widget, design, merken, was_verpasst, frage_claude,
projekt_bauen …). Code/Recherche gehen an **Claude** (`src/gehirn.py`, `claude -p` mit
Sitzung). Ohne Gemini-Schlüssel oder bei Ausfall: lokale Kette (Whisper → Ollama/Claude → Stimme).

## Gedächtnis

„Klaus, merk dir …“ / „was weißt du über mich?“ / „vergiss …“ → `data/gedaechtnis.json`,
fließt in jeden System-Prompt ein. Widget „Gedächtnis“ im Panel (Rechtsklick = löschen).

## Seit du weg warst

Klaus sichert alle 5 Minuten Zeit + Kurse (`data/zuletzt.json`). Nach ≥ 15 Minuten ohne
Maus/Tastatur/Gespräch – oder beim Start am Morgen – zeigt er im Klaus-Widget, was
passiert ist: wichtigste Nachrichten (Google News, Tagesschau, heise), Kursbewegungen
(`KLAUS_MARKT_BRIEFING`: Indizes, Tech, Krypto, Gold, Öl) und fertige Claude-Projekte.
„Klaus, was hab ich verpasst?“ liest es vor.

## Leistung

Liegt ein Vollbild-Fenster (Spiel, maximierte App) über dem Panel, pausieren alle
Panel-Animationen. Mit Gemini reicht `WHISPER_MODEL=small` fürs Weckwort.

## Briefe statt Werbe-Mails (Neukunden legal ansprechen)

Werbe-Mails an Firmen brauchen in Deutschland eine ausdrückliche Einwilligung (UWG § 7),
automatische KI-Anrufe ebenfalls. Briefe per Post sind erlaubt. `generate_outreach.py`
(Mail-Entwürfe) deshalb nicht mehr für Erstkontakte verwenden.

```bash
.venv/Scripts/python src/briefe.py                       # alle Leads, Standardtext
.venv/Scripts/python src/briefe.py --ki claude --nur 5   # Text individuell von Claude
```

Pro Firma: `data/briefe/<firma>/brief.pdf` (DIN 5008, Fensterkuvert), `entwurf.html` + `.png`
(Website-Entwurf nur für diese Firma, `noindex`). Den Ordner `data/briefe/_hochladen/` auf den
Webspace kopieren → der QR-Code im Brief öffnet `<KLESRO_WEBSITE>/entwurf/<firma>/`.
Absender in `.env`: `KLESRO_ADRESSE`, `KLESRO_TELEFON`, `KLESRO_WEBSITE` (fehlt etwas, steht
ein roter Platzhalter im Brief). Per Stimme: „Klaus, mach Briefe für die neuen Leads“.
