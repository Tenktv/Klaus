#!/usr/bin/env python3
"""
Klaus-Waechter fuer den Server (laeuft als root per systemd, nur Python-Standardbibliothek).

    klaus-waechter.py pruefen   taeglich: Zustand mit der Basis vergleichen, Bericht schreiben, bei Abweichung Telegram
    klaus-waechter.py scan      woechentlich: ClamAV ueber Website-/Upload-Ordner, bei Fund sofort Telegram
    klaus-waechter.py basis     aktuellen Zustand als "normal" speichern
    klaus-waechter.py auftrag   fuehrt aus, was Klaus in /var/lib/klaus-sicherheit/auftrag hinterlegt hat (nur pruefen|scan|basis)

Klaus (Benutzer klaus) darf nur das Wort in die Auftragsdatei schreiben; ausgefuehrt wird ausschliesslich diese feste Liste.
Der Bericht /var/lib/klaus-sicherheit/report.json enthaelt keine Geheimnisse (Schluessel nur als Pruefsumme).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

DIR = Path("/var/lib/klaus-sicherheit")
BASIS, REPORT, CLAM, AUFTRAG, ALARM = (DIR / n for n in ("basis.json", "report.json", "clam.json", "auftrag", "alarm.json"))
ENV = Path("/home/klaus/klaus/.env")
SCAN_ZIELE = ["/var/www", "/opt/klesro", "/home/sftpuser", "/home/klaus/klaus/data", "/tmp", "/var/tmp"]
CODE = "/home/klaus/klaus"


def sh(cmd: str, frist: int = 60) -> str:
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=frist).stdout.strip()
    except subprocess.TimeoutExpired:
        return ""


def pruefsumme(pfad: str) -> str:
    try:
        return hashlib.sha256(Path(pfad).read_bytes()).hexdigest()[:16]
    except OSError:
        return "fehlt"


def telegram(text: str) -> None:
    try:
        werte = dict(z.split("=", 1) for z in ENV.read_text(encoding="utf-8").splitlines() if "=" in z and not z.startswith("#"))
        daten = urllib.parse.urlencode({"chat_id": werte["TELEGRAM_NUTZER"], "text": text[:3900]}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{werte['TELEGRAM_TOKEN']}/sendMessage", daten, timeout=20).read()
    except Exception as e:
        print(f"Telegram nicht erreichbar: {e}", file=sys.stderr)


def speichern(pfad: Path, daten: dict, modus: int = 0o644) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = pfad.with_suffix(".tmp")
    tmp.write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.chmod(modus)
    tmp.replace(pfad)


def laden(pfad: Path) -> dict:
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ------------------------------------------------------------------ Zustand
def anmeldungen_24h() -> list[str]:
    zeilen = sh("journalctl -u ssh --since '24 hours ago' --no-pager | grep 'Accepted'", 60).splitlines()
    return sorted({f"{m.group(1)} von {m.group(2)}" for z in zeilen if (m := re.search(r"for (\S+) from ([0-9a-fA-F.:]+)", z))})


def zustand() -> dict:
    passwd = [z.split(":") for z in Path("/etc/passwd").read_text().splitlines() if z and not z.startswith("#")]
    schluessel = {}
    for name, _, uid, _, _, heim, shell in passwd:
        datei = Path(heim) / ".ssh" / "authorized_keys"
        if datei.is_file():
            zeilen = [z.strip() for z in datei.read_text(errors="replace").splitlines() if z.strip() and not z.startswith("#")]
            schluessel[name] = sorted(hashlib.sha256(z.encode()).hexdigest()[:16] for z in zeilen)
    ports = sorted({f"{m.group(1)} {m.group(2) or ''}".strip() for z in sh("ss -tlnpH").splitlines()
                    if (m := re.match(r"\S+\s+\S+\s+\S+\s+(\S+)\s+\S+\s*(?:users:\(\(\"([^\"]+)\")?", z))
                    and not re.match(r"(127\.|\[::1\]|::1)", m.group(1))})
    dateien = {}
    for muster in ("/etc/sudoers", "/etc/sudoers.d/*", "/etc/ssh/sshd_config", "/etc/ssh/sshd_config.d/*", "/usr/local/sbin/*",
                   "/etc/systemd/system/klaus-*", "/etc/caddy/Caddyfile", "/opt/klesro/backend/docker-compose*.yml", "/etc/crontab",
                   "/etc/cron.d/*", "/etc/cron.daily/*", "/etc/cron.hourly/*", "/etc/cron.weekly/*", "/var/spool/cron/crontabs/*",
                   "/etc/fail2ban/jail.d/*", "/etc/ufw/user.rules"):
        for pfad in sorted(Path("/").glob(muster.lstrip("/"))):
            if pfad.is_file():
                dateien[str(pfad)] = pruefsumme(str(pfad))
    suid = sorted(f for f in sh("find / -xdev -type f -perm -4000 2>/dev/null", 120).splitlines() if f)
    return {
        "benutzer": sorted(f"{p[0]}:{p[2]}:{p[6]}" for p in passwd if not p[6].endswith(("nologin", "false"))),
        "uid0": sorted(p[0] for p in passwd if p[2] == "0"),
        "schluessel": schluessel,
        "ports": ports,
        "dienste": sorted(z.split()[0] for z in sh("systemctl list-unit-files --type=service --state=enabled --no-legend").splitlines() if z),
        "docker": sorted(sh("docker ps --format '{{.Names}} {{.Image}}'").splitlines()),
        "dateien": dateien,
        "suid": suid,
        "bekannte_anmeldungen": anmeldungen_24h(),
    }


def unterschiede(basis: dict, jetzt: dict) -> list[str]:
    aus = []
    for schluessel, titel in (("benutzer", "Benutzer"), ("ports", "Offene Ports"), ("dienste", "Aktivierte Dienste"), ("docker", "Container"),
                              ("suid", "Programme mit Sonderrechten (SUID)")):
        neu, weg = set(jetzt[schluessel]) - set(basis.get(schluessel, [])), set(basis.get(schluessel, [])) - set(jetzt[schluessel])
        if neu:
            aus.append(f"{titel} NEU: {', '.join(sorted(neu))[:200]}")
        if weg:
            aus.append(f"{titel} WEG: {', '.join(sorted(weg))[:200]}")
    if jetzt["uid0"] != basis.get("uid0", jetzt["uid0"]):
        aus.append(f"Konten mit Root-Rechten geändert: {jetzt['uid0']}")
    for name, liste in jetzt["schluessel"].items():
        alt = set(basis.get("schluessel", {}).get(name, []))
        if set(liste) - alt:
            aus.append(f"Neuer SSH-Schlüssel für {name}")
        if alt - set(liste):
            aus.append(f"SSH-Schlüssel von {name} entfernt")
    for pfad in sorted(set(jetzt["dateien"]) | set(basis.get("dateien", {}))):
        a, b = basis.get("dateien", {}).get(pfad), jetzt["dateien"].get(pfad)
        if a != b:
            aus.append(f"Datei {'NEU' if a is None else 'GELÖSCHT' if b is None else 'GEÄNDERT'}: {pfad}")
    return aus


# ------------------------------------------------------------------ Befehle
def pruefen(manuell: bool = False) -> None:
    jetzt = zustand()
    basis = laden(BASIS)
    if not basis:
        speichern(BASIS, jetzt)
        basis = jetzt
        telegram("🛡️ Server-Wächter: Ich habe den heutigen Zustand als Normalzustand gespeichert. Ab jetzt melde ich Abweichungen.")
    aenderungen = unterschiede(basis, jetzt)
    git = sh(f"git -C {CODE} status --porcelain --untracked-files=no").splitlines()
    if git:
        aenderungen.append(f"Klaus-Code auf dem Server lokal verändert: {', '.join(z[3:] for z in git)[:150]}")
    neu_anmeldungen = [a for a in jetzt["bekannte_anmeldungen"] if a not in basis.get("bekannte_anmeldungen", [])]
    if neu_anmeldungen:
        aenderungen.append(f"Anmeldung von neuer Adresse: {', '.join(neu_anmeldungen)}")
    f2b = sh("fail2ban-client status sshd")
    gesamt_gebannt = re.search(r"Total banned:\s+(\d+)", f2b)
    aktuell = re.search(r"Currently banned:\s+(\d+)", f2b)
    updates = sh("apt list --upgradable 2>/dev/null").splitlines()
    clam = laden(CLAM)
    db = Path("/var/lib/clamav/daily.cvd")
    db_alter_h = round((time.time() - db.stat().st_mtime) / 3600) if db.exists() else None
    bericht = {
        "zeit": time.strftime("%Y-%m-%d %H:%M"), "epoch": int(time.time()), "aenderungen": aenderungen,
        "fehlversuche_24h": int(sh("journalctl -u ssh --since '24 hours ago' --no-pager | grep -cE 'Failed password|Invalid user'") or 0),
        "gesperrt_aktuell": int(aktuell.group(1)) if aktuell else None, "gesperrt_gesamt": int(gesamt_gebannt.group(1)) if gesamt_gebannt else None,
        "anmeldungen_24h": jetzt["bekannte_anmeldungen"],
        "updates_offen": sum(1 for z in updates if "upgradable" in z), "sicherheitsupdates": sum(1 for z in updates if "security" in z.lower()),
        "neustart_noetig": Path("/var/run/reboot-required").exists(),
        "virenscan": clam, "virendatenbank_alter_h": db_alter_h,
        "platte_belegt": sh("df / --output=pcent | tail -1").strip(),
        "firewall": "aktiv" if "Status: active" in sh("ufw status") else "AUS",
    }
    if bericht["firewall"] != "aktiv":
        aenderungen.append("Firewall ist NICHT aktiv")
    if db_alter_h is not None and db_alter_h > 72:
        aenderungen.append(f"Virendatenbank ist {db_alter_h} Stunden alt (Updates laufen nicht?)")
    speichern(REPORT, bericht)
    alt = laden(ALARM).get("hash")
    kennung = hashlib.sha256("\n".join(aenderungen).encode()).hexdigest()[:16] if aenderungen else ""
    if aenderungen and kennung != alt:
        telegram("⚠️ Server-Wächter: Das hat sich gegenüber dem Normalzustand geändert:\n• " + "\n• ".join(aenderungen[:12])
                 + "\n\nWar das von dir (oder von mir bei Wartung)? Dann: /sicherheit basis. Wenn nicht: melde dich, ich prüfe es.")
    speichern(ALARM, {"hash": kennung})
    print(f"Pruefung fertig: {len(aenderungen)} Abweichungen")


def scan(manuell: bool = False) -> None:
    start = time.time()
    ziele = [z for z in SCAN_ZIELE if Path(z).exists()]
    aus = subprocess.run(["clamscan", "-r", "--infected", "--max-filesize=100M", "--max-scansize=300M", *ziele],
                         capture_output=True, text=True, timeout=3 * 3600).stdout
    funde = [z.rsplit(" FOUND", 1)[0] for z in aus.splitlines() if z.endswith(" FOUND")]
    geprueft = re.search(r"Scanned files:\s+(\d+)", aus)
    daten = {"zeit": time.strftime("%Y-%m-%d %H:%M"), "epoch": int(time.time()), "dateien": int(geprueft.group(1)) if geprueft else None, "funde": funde[:20],
             "dauer_s": round(time.time() - start), "ziele": ziele}
    speichern(CLAM, daten)
    if funde:
        telegram("🦠 ClamAV hat etwas gefunden!\n• " + "\n• ".join(funde[:10]) + "\n\nIch habe nichts gelöscht. Sag mir, was ich damit tun soll.")
    elif manuell:
        telegram(f"✅ Virenscan sauber: {daten['dateien']} Dateien in {daten['dauer_s']} s geprüft ({', '.join(Path(z).name or z for z in ziele)}).")
    pruefen()   # Bericht aktualisieren
    print(f"Scan fertig: {len(funde)} Funde")


def basis_neu() -> None:
    speichern(BASIS, zustand())
    speichern(ALARM, {"hash": ""})
    pruefen()
    telegram("✅ Server-Wächter: Den aktuellen Zustand habe ich als Normalzustand übernommen.")


def auftrag() -> None:
    try:
        wort = AUFTRAG.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return
    if not wort:
        return
    AUFTRAG.write_text("", encoding="utf-8")   # leeren (nicht loeschen), damit klaus weiter schreiben darf
    {"pruefen": lambda: pruefen(True), "scan": lambda: scan(True), "basis": basis_neu}.get(wort, lambda: print(f"unbekannter Auftrag: {wort[:20]}"))()


if __name__ == "__main__":
    {"pruefen": pruefen, "scan": scan, "basis": basis_neu, "auftrag": auftrag}.get(sys.argv[1] if len(sys.argv) > 1 else "pruefen", pruefen)()
