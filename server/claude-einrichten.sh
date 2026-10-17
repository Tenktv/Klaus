#!/bin/bash
# Einmalig als root: Claude Code fuer Klaus abgeschottet einrichten (eigener Benutzer claudebau, kein Zugriff auf /home/klaus).
#   sudo bash /home/klaus/klaus/server/claude-einrichten.sh
# Danach am PC `claude setup-token` ausfuehren und den Token per Telegram `/claude_token <token>` an Klaus schicken.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "bitte als root"; exit 1; }
HIER="$(cd "$(dirname "$0")" && pwd)"

id claudebau >/dev/null 2>&1 || useradd --create-home --shell /usr/sbin/nologin claudebau
chmod 750 /home/klaus /home/claudebau             # gegenseitig nicht lesbar

install -d -o claudebau -g klaus -m 2750 /srv/klaus-claude /srv/klaus-claude/arbeit /srv/klaus-claude/projekte
install -o root -g root -m 755 "$HIER/klaus-claude" /usr/local/bin/klaus-claude

cat > /etc/sudoers.d/klaus-claude <<'EOF'
# Klaus darf Claude Code nur ueber das feste Startskript als claudebau starten
klaus ALL=(claudebau) NOPASSWD: /usr/local/bin/klaus-claude
EOF
chmod 440 /etc/sudoers.d/klaus-claude
visudo -cf /etc/sudoers.d/klaus-claude

if [ ! -x /home/claudebau/.local/bin/claude ]; then   # offizieller Installer von Anthropic, nur fuer claudebau
  sudo -H -u claudebau bash -c 'curl -fsSL https://claude.ai/install.sh | bash'
fi
sudo -H -u claudebau /usr/local/bin/klaus-claude --status || true
echo "fertig. Pruefen: sudo -u klaus cat /home/claudebau/.bashrc  -> muss 'Permission denied' sein"
