#!/bin/bash
# Klaus-Backup: verschluesseltes Backup (age) nach GitHub (Tenktv/Klaus-back-up-). Taeglich per systemd-Timer, laeuft als root.
# NOPUSH=1 -> nur lokal erzeugen (Test). WWW=1 -> Website-Dateien erzwingen (sonst sonntags).
set -euo pipefail
# Bei jedem Fehler eine Nachricht aufs Handy (Telegram), damit ein Backup nie unbemerkt ausfaellt
meldung() {
  local T N; T=$(grep -m1 '^TELEGRAM_TOKEN=' /home/klaus/klaus/.env | cut -d= -f2-); N=$(grep -m1 '^TELEGRAM_NUTZER=' /home/klaus/klaus/.env | cut -d= -f2-)
  curl -s -m 15 "https://api.telegram.org/bot${T}/sendMessage" -d chat_id="$N" --data-urlencode "text=$1" > /dev/null || true
}
trap 'meldung "⚠️ Klaus-Backup fehlgeschlagen ($(date +%F)). Details: /var/log/klaus-backup.log auf dem Server"' ERR
REPO=/home/klaus/backup-repo
REC=$(cat /home/klaus/.config/klaus/backup.age.pub)
TAG=$(date +%F)
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
mkdir -p "$REPO"
echo "[$(date '+%F %T')] Backup $TAG startet"

# 1) taeglich: Datenbank + Konfiguration (klein)
docker exec backend-db-1 pg_dumpall -U postgres > "$WORK/postgres.sql"
[ -s "$WORK/postgres.sql" ] && tail -c 200 "$WORK/postgres.sql" | grep -q 'cluster dump complete' || { echo "FEHLER: Datenbank-Dump unvollstaendig"; exit 1; }
PFADE=""
for p in opt/klesro etc/caddy etc/letsencrypt var/lib/caddy etc/ssh/sshd_config.d home/klaus/.config; do [ -e "/$p" ] && PFADE="$PFADE $p"; done
# Klaus-Gehirn auf dem Server: nur Einstellungen und Daten, NICHT die Python-Umgebung (.venv, mehrere hundert MB)
for p in home/klaus/klaus/.env home/klaus/klaus/data; do [ -e "/$p" ] && PFADE="$PFADE $p"; done
tar -czf - --exclude='*/__pycache__' --exclude='*/.venv' --exclude='*/.cache' -C / $PFADE -C "$WORK" postgres.sql | age -r "$REC" > "$REPO/tag-$TAG.tar.gz.age"

# 2) woechentlich (Sonntag) oder erzwungen: Website-Dateien, in 45-MB-Stuecke (unter GitHubs 50-MB-Warnschwelle)
if [ "$(date +%u)" = 7 ] || [ "${WWW:-0}" = 1 ] || ! ls "$REPO"/www-*.age.teil-* >/dev/null 2>&1; then
  rm -f "$REPO"/www-"$TAG".age.teil-*
  tar -czf - -C / var/www | age -r "$REC" | split -b 45M - "$REPO/www-$TAG.age.teil-"
fi

# 2c) taeglich: Minecraft-Welt (Paper in /opt/minecraft, seit 23.10.2026) - nur Welten + Einstellungen, keine Programmdateien.
#     Laeuft der Server, vorher per RCON alles speichern und das Schreiben anhalten (sonst halb geschriebene Regionen).
mc_rcon() {
  python3 - "$@" <<'PY'
import socket, struct, sys
props = {}
for zeile in open("/opt/minecraft/server.properties", encoding="utf-8"):
    if "=" in zeile and not zeile.startswith("#"):
        k, v = zeile.split("=", 1)
        props[k.strip()] = v.strip()
def senden(s, nr, art, text):
    daten = struct.pack("<ii", nr, art) + text.encode() + b"\0\0"
    s.sendall(struct.pack("<i", len(daten)) + daten)
def lesen(s):
    laenge = struct.unpack("<i", s.recv(4))[0]
    daten = b""
    while len(daten) < laenge:
        daten += s.recv(laenge - len(daten))
    return daten
s = socket.create_connection(("127.0.0.1", int(props.get("rcon.port", "25575"))), timeout=60)
senden(s, 1, 3, props.get("rcon.password", ""))
if struct.unpack("<i", lesen(s)[:4])[0] == -1:
    sys.exit("RCON-Anmeldung abgelehnt")
for befehl in sys.argv[1:]:
    senden(s, 2, 2, befehl)
    print(lesen(s)[8:-2].decode(errors="replace").strip())
PY
}
if [ -d /opt/minecraft ]; then
  MC_LAEUFT=0; systemctl is-active -q minecraft && MC_LAEUFT=1
  [ "$MC_LAEUFT" = 1 ] && mc_rcon "save-off" "save-all flush" > /dev/null
  rm -f "$REPO"/mc-"$TAG".age.teil-*
  MC_FEHLER=0
  tar -czf - -C /opt --exclude='minecraft/libraries' --exclude='minecraft/cache' --exclude='minecraft/versions' \
      --exclude='minecraft/logs' --exclude='minecraft/.cache' --exclude='minecraft/*.jar' minecraft \
    | age -r "$REC" | split -b 45M - "$REPO/mc-$TAG.age.teil-" || MC_FEHLER=1
  [ "$MC_LAEUFT" = 1 ] && mc_rcon "save-on" > /dev/null   # immer wieder einschalten, auch wenn tar fehlschlug
  [ "$MC_FEHLER" = 0 ] || { echo "FEHLER: Minecraft-Sicherung"; exit 1; }
fi

# 2b) PC-Archive (vom PC selbst verschluesselt, der Server kann sie nicht lesen) mitnehmen, letzte 7 Tage
rm -f "$REPO"/pc-*.age
cp -f /home/klaus/backup-pc/pc-*.age "$REPO"/ 2>/dev/null || true

# 3) Aufraeumen: 14 Tagesstaende, 2 Website-Staende
ls -1 "$REPO"/tag-*.age 2>/dev/null | sort | head -n -14 | xargs -r rm -f
ls -1 "$REPO"/www-*.age.teil-* 2>/dev/null | sed -E 's/.*www-([0-9-]+)\.age.*/\1/' | sort -u | head -n -2 | while read d; do rm -f "$REPO"/www-"$d".age.teil-*; done
ls -1 "$REPO"/mc-*.age.teil-* 2>/dev/null | sed -E 's/.*mc-([0-9-]+)\.age.*/\1/' | sort -u | head -n -3 | while read d; do rm -f "$REPO"/mc-"$d".age.teil-*; done

cat > "$REPO/WIEDERHERSTELLEN.md" <<'EOF'
# Klaus-Backup wiederherstellen
Alles hier ist mit age verschluesselt. Den Schluessel hat nur Nikola (Datei KLAUS-BACKUP-SCHLUESSEL.txt, Passwortmanager).
Taeglich (Datenbank + Konfiguration):  age -d -i schluessel.txt tag-DATUM.tar.gz.age | tar xz -C /tmp/wiederherstellung
PC (Gedaechtnis, data, .env):          age -d -i schluessel.txt pc-DATUM.tar.gz.age | tar xz -C /tmp/wiederherstellung   (vault/, data/, env/.env)
Website (Teile zusammensetzen):         cat www-DATUM.age.teil-* | age -d -i schluessel.txt | tar xz -C /tmp/wiederherstellung
Minecraft-Welt (letzte 3 Tage):         cat mc-DATUM.age.teil-* | age -d -i schluessel.txt | tar xz -C /tmp/wiederherstellung
                                        (Server stoppen: systemctl stop minecraft; dann world*/ nach /opt/minecraft, chown minecraft)
Datenbank zurueck:                      docker exec -i backend-db-1 psql -U postgres < tmp/klaus_bk/postgres.sql   (postgres.sql liegt im Archiv)
EOF

# 4) Hochladen: Repo jedes Mal neu (nur die aktuellen Dateien, keine alte Historie -> bleibt klein)
chown -R klaus:klaus "$REPO"
if [ "${NOPUSH:-0}" = 1 ]; then echo "NOPUSH: nicht hochgeladen"; du -sh "$REPO"; exit 0; fi
sudo -u klaus bash -c "cd '$REPO' && rm -rf .git && git init -q -b main && git config user.name 'Klaus Server' && git config user.email 'klaus@klesro-web.de' \
  && git remote add origin github-backup:Tenktv/Klaus-back-up-.git && git add -A && git commit -q -m 'Backup $TAG' && git push -q -f origin main"
echo "[$(date '+%F %T')] Backup $TAG hochgeladen: $(du -sh "$REPO" | cut -f1)"
