"""
Klaus - Admin-Helfer: fuehrt EINEN fest hinterlegten Befehl mit Adminrechten aus (UAC-Nachfrage von Windows).
Klaus selbst laeuft nie als Admin. Jeder Aufruf braucht zusaetzlich ein Freigabe-Token (Art "admin").

    admin.ausfuehren("defender_update", token)
    admin.ausfuehren("defender_pfad", token, pfad=r"C:\\Users\\Nikola\\Downloads\\setup.exe")

Nur die Befehle in BEFEHLE sind moeglich - keine freien Kommandos.
"""
from __future__ import annotations

import ctypes
import json
import os
import secrets
import tempfile
import time
from pathlib import Path

import freigabe

# Name -> (PowerShell-Befehl, warten?) ; {pfad} wird vorher geprueft und sicher eingesetzt
BEFEHLE = {
    "defender_update": ("Update-MpSignature", True),
    "defender_schnellscan": ("Start-MpScan -ScanType QuickScan", True),
    "defender_vollscan": ("Start-MpScan -ScanType FullScan", False),   # dauert lange; das Admin-Fenster laeuft unsichtbar weiter
    "defender_pfad": ("Start-MpScan -ScanType CustomScan -ScanPath '{pfad}'", True),
    "firewall_an": ("Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled True", True),
}


def ausfuehren(name: str, token: str | None, pfad: str = "", timeout: float = 900) -> str:
    if name not in BEFEHLE:
        raise ValueError(f"Kein erlaubter Admin-Befehl: {name}")
    befehl, warten = BEFEHLE[name]
    if "{pfad}" in befehl:
        p = Path(pfad)
        if not p.exists() or "'" in pfad:
            raise ValueError(f"Pfad ungültig: {pfad}")
        befehl = befehl.replace("{pfad}", str(p))
    freigabe.pruefe(token, "admin")

    kennung = secrets.token_hex(6)
    ergebnis = Path(tempfile.gettempdir()) / f"klaus_admin_{kennung}.json"
    skript = Path(tempfile.gettempdir()) / f"klaus_admin_{kennung}.ps1"
    skript.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        f"try {{ $aus = ({befehl}) | Out-String; @{{ok=$true; text=$aus}} | ConvertTo-Json | Set-Content -Encoding UTF8 '{ergebnis}' }}\n"
        f"catch {{ @{{ok=$false; text=$_.Exception.Message}} | ConvertTo-Json | Set-Content -Encoding UTF8 '{ergebnis}' }}\n",
        encoding="utf-8")
    # runas = Windows fragt per UAC; SW_HIDE = kein Fenster
    code = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe",
                                               f'-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{skript}"', None, 0)
    if code <= 32:
        skript.unlink(missing_ok=True)
        return "Die Admin-Freigabe von Windows wurde abgelehnt." if code == 5 else f"Admin-Start fehlgeschlagen (Code {code})."
    if not warten:
        return "Läuft im Hintergrund."
    ende = time.time() + timeout
    while time.time() < ende and not ergebnis.exists():
        time.sleep(1)
    time.sleep(0.3)
    try:
        d = json.loads(ergebnis.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return "Keine Rückmeldung vom Admin-Befehl (abgelehnt oder Zeit abgelaufen)."
    finally:
        for f in (ergebnis, skript):
            try:
                os.remove(f)
            except OSError:
                pass
    return ("Erledigt. " if d.get("ok") else "Fehler: ") + str(d.get("text", "")).strip()[:200]
