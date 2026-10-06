"""
Klaus - Selbst-Update auf dem Server (Code aus GitHub, Tenktv/Klaus, Zweig main).

    pruefen()            -> Liste neuer Commits (leer = aktuell)
    einspielen(token)    -> holt den neuen Stand, testet ihn, uebernimmt ihn nur bei Erfolg (sonst zurueck auf alt)
    nach_neustart()      -> Text fuer "wieder da", wenn gerade ein Update lief (sonst None)

Nur mit Freigabe (Art "update", Knopf + PIN). Der Test kompiliert alle Module und laedt server_gehirn einmal komplett.
Nach erfolgreichem Update beendet sich der Prozess; systemd (Restart=always) startet ihn mit dem neuen Code neu.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import freigabe

BASE_DIR = Path(__file__).resolve().parent.parent
MARKER = BASE_DIR / "data" / "update_marker.json"
TEST = ("import glob, py_compile, sys; sys.path.insert(0, 'src'); "
        "[py_compile.compile(f, doraise=True) for f in glob.glob('src/*.py')]; import server_gehirn; print('TEST_OK')")


def _git(*args: str, frist: float = 120) -> str:
    r = subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True, timeout=frist)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()[:200]}")
    return r.stdout.strip()


def pruefen() -> list[str]:
    _git("fetch", "-q", "origin", "main")
    neu = _git("log", "--oneline", "--no-decorate", "HEAD..origin/main")
    return [z for z in neu.splitlines() if z.strip()]


def einspielen(token: str | None) -> str:
    freigabe.pruefe(token, "update")
    alt = _git("rev-parse", "--short", "HEAD")
    if _git("status", "--porcelain", "--untracked-files=no"):
        return "Update abgebrochen: auf dem Server gibt es lokale Änderungen am Code."
    _git("merge", "--ff-only", "-q", "origin/main")
    neu = _git("rev-parse", "--short", "HEAD")
    if neu == alt:
        return "Klaus ist schon auf dem neuesten Stand."
    test = subprocess.run([sys.executable, "-c", TEST], cwd=BASE_DIR, capture_output=True, text=True, timeout=300)
    if "TEST_OK" not in test.stdout:
        _git("reset", "-q", "--hard", alt)
        fehler = (test.stderr or test.stdout).strip().splitlines()[-1:] or ["?"]
        return f"Update auf {neu} fehlgeschlagen ({fehler[0][:150]}). Ich bin auf der alten Version {alt} geblieben."
    MARKER.parent.mkdir(exist_ok=True)
    MARKER.write_text(json.dumps({"alt": alt, "neu": neu}), encoding="utf-8")
    threading.Timer(4, lambda: os._exit(0)).start()   # systemd startet mit dem neuen Code neu
    return f"Update {alt} → {neu} getestet und übernommen. Ich starte neu und melde mich gleich."


def nach_neustart() -> str | None:
    if not MARKER.exists():
        return None
    try:
        d = json.loads(MARKER.read_text(encoding="utf-8"))
    finally:
        MARKER.unlink(missing_ok=True)
    zeilen = _git("log", "--oneline", "--no-decorate", f"{d['alt']}..{d['neu']}").splitlines()
    return f"✅ Wieder da – Update {d['alt']} → {d['neu']} läuft.\n" + "\n".join(f"• {z.split(' ', 1)[-1]}" for z in zeilen[:8])
