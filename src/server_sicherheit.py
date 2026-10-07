"""
Klaus - Sicherheitsbericht des Servers (liest, was der Wächter /usr/local/sbin/klaus-waechter.py als root geschrieben hat).

    text()          -> Bericht fuer Telegram
    auftrag(wort)   -> "pruefen" | "scan" | "basis": legt das Wort in die Auftragsdatei; ein systemd-Pfad startet den Waechter als root.
                       Klaus (Benutzer klaus) kann nichts anderes ausloesen als diese drei festen Aktionen.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

DIR = Path("/var/lib/klaus-sicherheit")
REPORT, CLAM, AUFTRAG = DIR / "report.json", DIR / "clam.json", DIR / "auftrag"


def _lesen(pfad: Path) -> dict:
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _zahl(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def _wann(epoch) -> str:
    if not epoch:
        return "noch nie"
    d = dt.datetime.fromtimestamp(epoch)
    return "heute " + d.strftime("%H:%M") if d.date() == dt.date.today() else d.strftime("%d.%m. %H:%M")


def text() -> str:
    r = _lesen(REPORT)
    if not r:
        return "🛡️ Server: Es gibt noch keinen Bericht (der Wächter läuft täglich um 7 Uhr)."
    zeilen = [f"🛡️ Server – Stand {_wann(r.get('epoch'))}"]
    if r["aenderungen"]:
        zeilen.append("⚠️ Abweichungen vom Normalzustand:\n" + "\n".join(f"  • {a}" for a in r["aenderungen"][:8]))
    else:
        zeilen.append("✅ Keine Abweichungen vom Normalzustand")
    angriffe = f"🚪 Angriffe (24 h): {_zahl(r['fehlversuche_24h'])} Fehlversuche"
    if r.get("gesperrt_aktuell") is not None:
        angriffe += f", fail2ban sperrt gerade {r['gesperrt_aktuell']} Adressen (insgesamt {r['gesperrt_gesamt']})"
    zeilen.append(angriffe)
    if r.get("anmeldungen_24h"):
        zeilen.append("🔑 Anmeldungen (24 h): " + ", ".join(r["anmeldungen_24h"]))
    zeilen.append(f"📦 Updates: {r['updates_offen']} offen ({r['sicherheitsupdates']} Sicherheit)"
                  + (" · Neustart nötig" if r["neustart_noetig"] else ""))
    c = r.get("virenscan") or _lesen(CLAM)
    if c:
        funde = len(c.get("funde", []))
        zeilen.append(f"🦠 Virenscan: {_wann(c.get('epoch'))}, {_zahl(c['dateien'] or 0)} Dateien, "
                      + ("**{} FUNDE**".format(funde) if funde else "keine Funde")
                      + (f" · Datenbank {r['virendatenbank_alter_h']} h alt" if r.get("virendatenbank_alter_h") is not None else ""))
    else:
        zeilen.append("🦠 Virenscan: läuft sonntags automatisch (oder: /sicherheit scan)")
    zeilen.append(f"🧱 Firewall {r['firewall']} · Platte {r['platte_belegt']} belegt")
    return "\n".join(zeilen)


def auftrag(wort: str, warte_s: int = 0) -> str:
    """Wort in die Auftragsdatei schreiben (nur pruefen|scan|basis). Bei warte_s > 0 auf den neuen Bericht warten."""
    if wort not in ("pruefen", "scan", "basis"):
        raise ValueError(f"unbekannter Auftrag: {wort}")
    vorher = _lesen(REPORT).get("epoch", 0)
    AUFTRAG.write_text(wort, encoding="utf-8")
    ende = time.time() + warte_s
    while time.time() < ende:
        time.sleep(2)
        if _lesen(REPORT).get("epoch", 0) > vorher:
            return text()
    return ""
