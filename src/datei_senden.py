"""
Klaus - Dateien per Telegram schicken ("schick mir das Protokoll von heute", "schick mir die PDF vom Brief").

    senden("letztes protokoll")        neueste Notiz in Meetings/
    senden("letztes bildschirmfoto")   neuestes Bild in Bilder/Klaus
    senden(r"C:\\...\\datei.pdf", gefunden)   ein Pfad aus datei_suchen

Nur Dateien aus deinen eigenen Ordnern (Vault, Dokumente, Desktop, Downloads, Bilder, Klaus-Daten). Geheimnisse (.env,
Schluessel, Passwort-Datenbanken, Browser-Profile) gehen nie raus. Telegram-Grenze fuer Bots: 50 MB. Jede Sendung im Log.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import gehirn

MAX_BYTES = 45 * 1024 * 1024
BASE = Path(__file__).resolve().parent.parent
HOME = Path.home()
WURZELN = [gehirn.VAULT, HOME / "Documents", HOME / "Desktop", HOME / "Downloads", HOME / "Pictures", HOME / "Videos",
           HOME / "Music", BASE / "data" / "briefe", BASE / "data" / "projekte", BASE / "data" / "plaene"]
GEHEIM = re.compile(r"(^|[\\/])\.env|\.ssh|id_rsa|id_ed25519|klaus_tunnel|klaus_server|\.kdbx|\.pem$|\.key$|\.pfx$|"
                    r"backup-schluessel|klaus_edge|[\\/]browser[\\/]|login data|cookies|wallet", re.I)

datei_melder: Callable[[bytes, str, str], None] | None = None   # (inhalt, dateiname, text) -> Telegram; setzt assistent.py


def _neueste(ordner: Path, muster: str) -> Path | None:
    dateien = [p for p in ordner.glob(muster) if p.is_file()] if ordner.is_dir() else []
    return max(dateien, key=lambda p: p.stat().st_mtime) if dateien else None


def _innerhalb(pfad: Path) -> bool:
    for w in WURZELN:
        try:
            pfad.relative_to(w.resolve())
            return True
        except ValueError:
            continue
    return False


def senden(was: str, gefunden: set[str] | None = None) -> str:
    was = (was or "").strip().strip('"')
    w = was.lower()
    if re.search(r"protokoll|meeting|besprechung|mitschrift", w) and not re.search(r"[\\/]", was):
        pfad = _neueste(gehirn.VAULT / "Meetings", "*.md")
    elif re.search(r"bildschirmfoto|screenshot", w) and not re.search(r"[\\/]", was):
        pfad = _neueste(HOME / "Pictures" / "Klaus", "*.*")
    else:
        if gefunden is not None and was not in gefunden:
            return "Abgelehnt: erst mit datei_suchen finden, dann den Pfad zum Senden nehmen."
        pfad = Path(was)
    if not pfad or not pfad.exists():
        return "Die Datei habe ich nicht gefunden."
    pfad = pfad.resolve()
    if pfad.is_dir():
        return "Das ist ein Ordner – ich kann nur einzelne Dateien schicken."
    if GEHEIM.search(str(pfad)):
        return "Abgelehnt: Das sieht nach einer geheimen Datei aus (Schlüssel/Passwörter), die schicke ich nie."
    if not _innerhalb(pfad):
        return "Abgelehnt: Ich schicke nur Dateien aus deinen Ordnern (Dokumente, Desktop, Downloads, Bilder, Gedächtnis, Klaus-Daten)."
    groesse = pfad.stat().st_size
    if groesse > MAX_BYTES:
        return f"Die Datei ist zu groß für Telegram ({groesse // (1024 * 1024)} MB, Grenze 45 MB)."
    if not datei_melder:
        return "Telegram ist auf diesem PC nicht eingerichtet."
    datei_melder(pfad.read_bytes(), pfad.name, f"📎 {pfad.name}")
    try:
        import rechte
        rechte.protokoll(f"Datei an Telegram geschickt: {pfad} ({groesse // 1024} KB)")
    except Exception:
        pass
    return f"Ich habe dir „{pfad.name}“ ({max(1, groesse // 1024)} KB) auf Telegram geschickt."
