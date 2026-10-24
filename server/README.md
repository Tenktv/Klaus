# Server-Dateien (IONOS-VPS)

Kopien der Dateien, die auf dem Server liegen, damit er sich nachbauen laesst. Keine Geheimnisse hier.

| Datei | Ziel auf dem Server |
|---|---|
| `klaus-backup.sh` | `/usr/local/sbin/klaus-backup.sh` (root, 700) - verschluesseltes Backup nach GitHub, Alarm per Telegram |
| `klaus-backup.service`, `klaus-backup.timer` | `/etc/systemd/system/` - taeglich 03:30 |
| `klaus-gehirn.service` | `/etc/systemd/system/` - Telegram-Bot + Werkzeuge (`src/server_gehirn.py`) |
| `00-haertung.conf` | `/etc/ssh/sshd_config.d/` - Root nur per SSH-Schluessel |

Benutzer `klaus` (kein Passwort, keine Admin-Rechte), Code in `/home/klaus/klaus`, Python-Umgebung `.venv` dort.
Die `.env` des Servers (Gemini, Telegram, Apple-Kalender, Link-Token) liegt nur dort und im verschluesselten Backup.

## Sicherheit (07.10.2026)
| Datei | Ziel auf dem Server |
|---|---|
| `klaus-waechter.py` | `/usr/local/sbin/klaus-waechter.py` (root, 700) - Zustandsvergleich, ClamAV-Scan, Basis, Auftraege |
| `klaus-waechter.service/.timer` | taeglich 05:00 UTC |
| `klaus-scan.service/.timer` | sonntags 02:00 UTC (ClamAV, MemoryMax 2G) |
| `klaus-auftrag.service/.path` | startet den Waechter, wenn Klaus `pruefen`, `scan` oder `basis` in `/var/lib/klaus-sicherheit/auftrag` schreibt |
| `klaus-freshclam.service/.timer` | Virendatenbank taeglich 04:30 UTC (statt Dauerdienst) |

Einrichten: Verzeichnis `/var/lib/klaus-sicherheit` (root, 755), darin leere Datei `auftrag` (root:klaus, 664); fail2ban-Jail in
`/etc/fail2ban/jail.d/klaus.local` (`bantime 24h`, `maxretry 4`, `findtime 10m`, `backend systemd`, `[sshd] enabled`); Swapfile 2 GB.
Danach `systemctl enable --now klaus-waechter.timer klaus-scan.timer klaus-freshclam.timer klaus-auftrag.path` und einmal
`klaus-waechter.py pruefen` (legt die Basis an).

## Alpaca-Handel (16.10.2026)
`src/alpaca_handel.py`, verdrahtet in `src/server_gehirn.py` (Werkzeuge `alpaca_konto`, `alpaca_order`, Befehl `/alpaca`).
In die `.env` des Servers: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` (zuerst Paper-Schluessel), optional `ALPACA_MAX_ORDER_USD`
(Standard: keine Grenze). Echtgeld nur mit `ALPACA_LIVE=1` plus Live-Schluessel - bewusst von Hand, Klaus aendert das nicht.
Jede Order und jedes Storno laeuft ueber das Freigabe-Gate (Art `handeln`: Telegram-Knopf + PIN, 90 s); kein Leerverkauf.
Ohne SSH: in Telegram `/alpaca_schluessel <Key> <Secret>` - nur Paper-Schluessel (PK...), Klaus loescht die Nachricht
sofort, prueft die Schluessel bei Alpaca und schreibt sie erst dann in die `.env` (geht nicht an die KI).
Danach in Telegram `/alpaca` schicken.

## Eigene Strategien (16.10.2026)
`src/strategien.py`, Schleife alle 5 Minuten (startet mit `klaus-gehirn`), Daten in `data/strategien.json`.
Klaus entwirft und testet Strategien (trend, rsi, sparplan; 2 Jahre Tageskurse von Yahoo). Einschalten und Fortsetzen nur mit
Freigabe (Art `strategie`), danach handeln sie selbst - ausschliesslich auf dem Alpaca-Papier-Konto; bei `ALPACA_LIVE=1` ruhen sie.
Grenzen nur, wenn gesetzt: `STRATEGIE_GESAMT_USD`, `STRATEGIE_MAX_AKTIV`, `STRATEGIE_MAX_ORDERS_TAG`, `ALPACA_MAX_ORDER_USD`; immer die Kaufkraft (inkl. Margin-Hebel, `/hebel 1|2|4`). Notstopp: `/strategien stop`.

## Analysen (16.10.2026)
`src/analysen.py`, nur lesend: `/depotcheck` (Verteilung, Klumpenrisiko, Monat gegen S&P 500), `/scanner [art]`
(~50 US-Werte/ETFs/Krypto + Watchlist: RSI, SMA20/50-Kreuz, 52-Wochen-Hoch/Tief), `/wochenbericht` - kommt automatisch
freitags ab 22:30 Uhr (Zustand in `data/analysen.json`). Strategien merken sich ihre Trades (`historie`, `realisiert`).

## Claude in der Cloud (17.10.2026)
`src/server_claude.py`: Ist der PC aus (Ping auf den PC-Link), laufen `frage_claude` und `projekt_bauen` ueber Claude Code
auf dem Server (Projekte in `~/projekte/<name>`, Ergebnis als ZIP per Telegram). Einrichten als Benutzer klaus:
`curl -fsSL https://claude.ai/install.sh | bash`, dann am PC `claude setup-token` und den Token per Telegram
`/claude_token <token>` schicken (wird sofort geloescht). `/pc` zeigt PC- und Claude-Status, `/claude` nur Claude.

## Tester-Profile (24.10.2026)
`src/profile_verteiler.py` als Dienst `klaus-profile` (`server/klaus-profile.service` nach `/etc/systemd/system/`).
Ein gemeinsamer **Tester-Bot** (neu bei @BotFather, Token als `TESTER_BOT_TOKEN` in Nikolas `.env`). Nikola laedt im
eigenen Klaus mit `/einladen <Name>` ein (Link, 7 Tage, einmalig), `/tester` zeigt alle, `/tester_entfernen <ID>` sperrt.
Jeder Tester bekommt `~/profile/<telegram-id>/` mit eigener `.env`, eigenem `data/`, eigenem HOME (Claude-Anmeldung) und
einen eigenen Prozess (`server_gehirn.py` mit `KLAUS_PROFIL=1`, Nachrichten ueber stdin). Schluessel traegt der Tester
selbst ein: `/schluessel gemini|groq|openrouter|fish|anthropic|tavily|openai <schluessel>`, `/alpaca_schluessel`,
`/claude_token`, `/name <Name>`, `/profil`. Code: Nikolas Stand, bei neuem Git-Stand werden die Profile neu gestartet.
Noch nicht: Verbindung zum PC des Testers (Etappe 2). Alle Profile laufen als Benutzer klaus (Testphase).
Einrichten: `systemctl enable --now klaus-profile`, Log: `journalctl -u klaus-profile`, je Profil `~/profile/<id>/data/klaus.log`.
