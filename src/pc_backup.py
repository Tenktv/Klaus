"""
Klaus - Backup der PC-Daten (Gedaechtnis/Vault, data/, .env) ueber den Server nach GitHub.

Der PC verschluesselt SELBST (age, nur mit dem oeffentlichen Schluessel), bevor etwas den Rechner verlaesst: Server und
GitHub sehen nie Klartext - auch nicht die Schluessel in der .env. Ohne den geheimen Schluessel (nur bei Nikola) ist
das Archiv unlesbar.

    pc_backup.sichern()  -> Text mit dem Ergebnis; schickt das Archiv ueber den Tunnel an den Server (/backup)
Der Server legt es ab, das naechtliche Server-Backup (klaus-backup.sh) nimmt es mit ins verschluesselte GitHub-Repo.

.env:  KLAUS_BACKUP_OEFFENTLICH=age1...   (oeffentlicher Teil, zum Verschluesseln)
"""
from __future__ import annotations

import datetime as dt
import io
import os
import tarfile
import threading
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

import fernlink
import gehirn

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

OEFFENTLICH = os.getenv("KLAUS_BACKUP_OEFFENTLICH", "").strip()
STAND = BASE_DIR / "data" / "pc_backup_zuletzt"
NICHT = {"stimmen", "browser", "klaus.log", "klaus.lock", "gehirn_cache"}   # gross oder ersetzbar
MAX_MB = 40


def _archiv() -> bytes:
    puffer = io.BytesIO()
    with tarfile.open(fileobj=puffer, mode="w:gz") as t:
        if gehirn.VAULT.exists():
            t.add(gehirn.VAULT, arcname="vault")
        daten = BASE_DIR / "data"
        for p in sorted(daten.iterdir()) if daten.exists() else []:
            if p.name not in NICHT:
                t.add(p, arcname=f"data/{p.name}")
        if (BASE_DIR / ".env").exists():
            t.add(BASE_DIR / ".env", arcname="env/.env")
    return puffer.getvalue()


def sichern() -> str:
    if not OEFFENTLICH:
        return "Backup nicht eingerichtet (KLAUS_BACKUP_OEFFENTLICH fehlt)."
    import pyrage

    roh = _archiv()
    verschluesselt = pyrage.encrypt(roh, [pyrage.x25519.Recipient.from_str(OEFFENTLICH)])
    if len(verschluesselt) > MAX_MB * 1024 * 1024:
        return f"Backup zu gross ({len(verschluesselt) // 1024 // 1024} MB) - nicht gesendet."
    try:
        r = requests.post(f"http://127.0.0.1:{fernlink.SERVER_PORT}/backup", data=verschluesselt,
                          headers={"X-Token": fernlink.TOKEN, "Content-Type": "application/octet-stream"}, timeout=180)
    except Exception as e:
        return f"Server nicht erreichbar ({str(e)[:60]})."
    if r.status_code != 200:
        return f"Server hat das Backup abgelehnt ({r.status_code})."
    STAND.write_text(str(time.time()))
    return f"PC-Backup gesendet: {len(roh) // 1024} KB, verschluesselt {len(verschluesselt) // 1024} KB."


def faellig() -> bool:
    try:
        return time.time() - float(STAND.read_text()) > 23 * 3600
    except Exception:
        return True


def loop(tunnel) -> None:
    """Hintergrund: 3 Minuten nach dem Start und dann alle 23 h (wenn der Tunnel steht)."""
    time.sleep(180)
    while True:
        if OEFFENTLICH and faellig() and getattr(tunnel, "verbunden", False):
            print("[Backup]", sichern())
        time.sleep(1800)


def starte(tunnel) -> None:
    threading.Thread(target=loop, args=(tunnel,), daemon=True, name="klaus-pc-backup").start()
