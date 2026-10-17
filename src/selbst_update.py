"""
Klaus - Selbst-Update auf dem Server (Code aus GitHub, Tenktv/Klaus, Zweig main).

    pruefen()            -> Liste neuer Commits (leer = aktuell)
    einspielen(token)    -> holt den neuen Stand, testet ihn, uebernimmt ihn nur bei Erfolg (sonst zurueck auf alt)
    nach_neustart()      -> Text fuer "wieder da", wenn gerade ein Update lief (sonst None)

Per Telegram "Update einspielen" mit Freigabe (Knopf + PIN) - und automatisch alle 30 Minuten (starte_auto, ohne PIN). Der Test kompiliert alle Module und laedt server_gehirn einmal komplett.
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
# Undefinierte Namen (z. B. vergessener Import in main) - laden allein findet das nicht; ohne pyflakes wird es uebersprungen
FLAKES = ("\ntry:\n    import io, pyflakes.api as pf, pyflakes.reporter as pr\nexcept ImportError:\n    pf = None\n"
          "if pf:\n    out = io.StringIO()\n    for f in glob.glob('src/*.py'):\n        pf.checkPath(f, pr.Reporter(out, out))\n"
          "    fehler = [z for z in out.getvalue().splitlines() if 'undefined name' in z]\n"
          "    if fehler:\n        raise SystemExit('pyflakes: ' + fehler[0])\n")
TEST = ("import glob, py_compile, sys; sys.path.insert(0, 'src'); "
        "[py_compile.compile(f, doraise=True) for f in glob.glob('src/*.py')]; ")
TEST = TEST + FLAKES + "import server_gehirn; print('TEST_OK')"


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
    return _uebernehmen()


def _uebernehmen() -> str:
    alt = _git("rev-parse", "--short", "HEAD")
    if _git("status", "--porcelain", "--untracked-files=no", "--", ".", ":(exclude)data"):   # Laufzeitdaten zaehlen nicht
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


# ---------------------------------------------------------------- automatisch (Wunsch Nikola, 17.10.2026: ohne PIN)
TAKT_S = 30 * 60
_gemeldet = {"text": ""}


def auto_schritt(beschaeftigt, senden) -> bool:
    """Ein Durchlauf: neue Commits und Klaus gerade ruhig -> uebernehmen (getestet, sonst bleibt der alte Stand).
    -> True, wenn neu gestartet wird. Aus: KLAUS_AUTO_UPDATE=0; mit Knopf + PIN statt automatisch: KLAUS_UPDATE_FREIGABE=1."""
    if os.getenv("KLAUS_AUTO_UPDATE", "1").strip() == "0" or os.getenv("KLAUS_UPDATE_FREIGABE", "0").strip() == "1":
        return False
    if not pruefen() or beschaeftigt():
        return False
    text = _uebernehmen()
    neustart = "getestet und übernommen" in text
    if neustart or text != _gemeldet["text"]:   # gleiche Fehlermeldung nicht alle 30 Minuten
        _gemeldet["text"] = text
        senden(("🔄 Automatisches Update: " if neustart else "⚠️ ") + text)
    return neustart


def starte_auto(beschaeftigt, senden) -> None:
    def schleife() -> None:
        import time
        time.sleep(5 * 60)
        while True:
            try:
                if auto_schritt(beschaeftigt, senden):
                    return
            except Exception as e:   # kein Netz o. ae.: naechstes Mal
                print(f"[Update] {str(e)[:150]}", flush=True)
            time.sleep(TAKT_S)
    threading.Thread(target=schleife, daemon=True, name="klaus-auto-update").start()
