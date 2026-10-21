"""
Klaus - Spielerkennung fuer den Spielmodus: Laeuft ein Spiel? Dann blendet klaus_app das Panel aus und zeigt nur den
Mini-Orb (fenster.MiniOrb). Ohne Qt, laeuft in einem eigenen Thread (die Prozessliste kostet ein paar Millisekunden).

    spiel_name()  -> "league of legends" / "" (bekannter Spielprozess oder Vollbild-Programm aus einem Spiele-Ordner)
"""
from __future__ import annotations

import ctypes
import os
import threading
from typing import Callable

import pc_update

SPIELE = set(pc_update.SPIELE) | {
    "genshinimpact", "yuanshen", "zenlesszonezero", "starrail", "r5apex", "overwatch", "eldenring", "cyberpunk2077",
    "bg3", "bg3_dx11", "witcher3", "rdr2", "destiny2", "pubg-win64-shipping", "tslgame", "deadbydaylight-win64-shipping",
    "fallguys_client_game", "dota2", "wow", "hearthstone", "palworld-win64-shipping", "helldivers2", "marvel-win64-shipping",
}
# Programme aus diesen Ordnern im Vollbild zaehlen auch (Steam-/Epic-/Riot-Spiele, die nicht in der Liste stehen)
SPIEL_ORDNER = ("steamapps", "riot games", "epic games", "\\games\\", "hoyoplay", "battle.net", "ubisoft game launcher",
                "ea games", "gog galaxy", "xboxgames")
TAKT_S = 5
_entdeckt: set[str] = set()   # ueber den Spiele-Ordner erkannt -> ab dann wie ein bekanntes Spiel (auch beim Alt+Tab)


def _vorne_vollbild_aus_spieleordner() -> str:
    try:
        import psutil
        import win32api
        import win32gui
        import win32process

        h = win32gui.GetForegroundWindow()
        if not h:
            return ""
        pid = win32process.GetWindowThreadProcessId(h)[1]
        if pid == os.getpid():
            return ""
        pfad = psutil.Process(pid).exe().lower()
        if not any(o in pfad for o in SPIEL_ORDNER):
            return ""
        monitor = win32api.GetMonitorInfo(win32api.MonitorFromWindow(h, 2))["Monitor"]
        if tuple(win32gui.GetWindowRect(h)) != tuple(monitor) or ctypes.windll.user32.IsZoomed(h):
            return ""   # Launcher/Fenstermodus -> kein Spielmodus
        return os.path.basename(pfad).removesuffix(".exe")
    except Exception:
        return ""


def spiel_name() -> str:
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            name = (p.info["name"] or "").lower().removesuffix(".exe")
            if name in SPIELE or name in _entdeckt:
                return name
    except Exception:
        pass
    name = _vorne_vollbild_aus_spieleordner()
    if name:
        _entdeckt.add(name)
    return name


def beobachten(melden: Callable[[str], None], halt: threading.Event) -> None:
    """Meldet jede Aenderung (Spielname oder ""). Aufrufer sorgt fuer den Wechsel in den GUI-Thread (Qt-Signal)."""
    zuletzt = None
    while not halt.is_set():
        jetzt = spiel_name()
        if jetzt != zuletzt:
            zuletzt = jetzt
            melden(jetzt)
        halt.wait(TAKT_S)
