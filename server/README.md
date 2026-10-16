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
(Standard 1000). Echtgeld nur mit `ALPACA_LIVE=1` plus Live-Schluessel - bewusst von Hand, Klaus aendert das nicht.
Jede Order und jedes Storno laeuft ueber das Freigabe-Gate (Art `handeln`: Telegram-Knopf + PIN, 90 s); kein Leerverkauf.
Ohne SSH: in Telegram `/alpaca_schluessel <Key> <Secret>` - nur Paper-Schluessel (PK...), Klaus loescht die Nachricht
sofort, prueft die Schluessel bei Alpaca und schreibt sie erst dann in die `.env` (geht nicht an die KI).
Danach in Telegram `/alpaca` schicken.
