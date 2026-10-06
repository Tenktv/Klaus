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
