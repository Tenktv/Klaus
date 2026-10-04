"""
Klaus - Dateien finden und (sicher) loeschen

Loeschen heisst hier immer: in den Papierkorb, also wiederherstellbar. Erlaubt sind nur
Dateien/Ordner unter Desktop, Dokumente, Downloads, Bilder, Videos, Musik und den
Klaus-Projekten. Windows, Programme, Klaus selbst und ganze Laufwerke sind tabu.
"""

import difflib
import os
import re
from pathlib import Path

from send2trash import send2trash

HOME = Path.home()
KLAUS_DIR = Path(__file__).resolve().parent.parent
PROJEKTE_DIR = KLAUS_DIR / "data" / "projekte"
SUCHORTE = [HOME / "Desktop", HOME / "Documents", HOME / "Downloads", HOME / "Pictures", HOME / "Videos",
            HOME / "Music", PROJEKTE_DIR]
MAX_TIEFE = 3


def _norm(text: str) -> str:
    text = text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return " ".join(re.findall(r"[a-z0-9]+", text))


def erlaubt(pfad: Path) -> bool:
    """Nur Dinge innerhalb der Suchorte - nie ein Suchort selbst und nie Klaus' eigener Ordner."""
    try:
        pfad = pfad.resolve()
    except OSError:
        return False
    if pfad in [o.resolve() for o in SUCHORTE] or pfad == HOME.resolve():
        return False
    if KLAUS_DIR.resolve() in [pfad, *pfad.parents] and PROJEKTE_DIR.resolve() not in pfad.parents:
        return False  # Klaus' eigener Code und Daten (Projekte darunter sind erlaubt)
    if pfad in KLAUS_DIR.resolve().parents:
        return False  # ein Ordner, in dem Klaus selbst liegt (z. B. "Neuer Ordner (5)" auf dem Desktop)
    return any(o.resolve() in pfad.parents for o in SUCHORTE if o.exists())


def suche(name: str, anzahl: int = 6) -> list[dict]:
    """Dateien und Ordner, deren Name zum Gesagten passt (unscharf, z. B. "schreinerei maier")."""
    ziel = _norm(name)
    if not ziel:
        return []
    treffer = []
    for ort in SUCHORTE:
        if not ort.exists():
            continue
        basis_tiefe = len(ort.parts)
        for wurzel, ordner, dateien in os.walk(ort):
            tiefe = len(Path(wurzel).parts) - basis_tiefe
            ordner[:] = [o for o in ordner if not o.startswith(".") and o not in ("node_modules", "__pycache__", ".venv")]
            if tiefe >= MAX_TIEFE:
                ordner[:] = []
            for eintrag in ordner + dateien:
                n = _norm(eintrag)
                passt = ziel in n or difflib.SequenceMatcher(None, ziel, n).ratio() > 0.75
                if passt:
                    pfad = Path(wurzel) / eintrag
                    treffer.append({"pfad": str(pfad), "art": "Ordner" if pfad.is_dir() else "Datei",
                                    "aehnlichkeit": difflib.SequenceMatcher(None, ziel, n).ratio()})
    treffer.sort(key=lambda t: t["aehnlichkeit"], reverse=True)
    return treffer[:anzahl]


def in_papierkorb(pfad: str) -> str:
    """Verschiebt in den Papierkorb (wiederherstellbar). Gibt eine Meldung fuer Klaus zurueck."""
    p = Path(pfad)
    if not p.exists():
        return f"Gibt es nicht: {pfad}"
    if not erlaubt(p):
        return f"Das darf ich nicht löschen (geschützter Ort): {pfad}"
    send2trash(str(p))
    return f"{p.name} liegt jetzt im Papierkorb (wiederherstellbar)."
