"""
Klaus - automatisches Update auf dem PC (Code aus GitHub, Tenktv/Klaus, Zweig main).

Alle 30 Minuten (erstes Mal 3 Minuten nach dem Start): neue Commits auf origin/main? Wenn Klaus gerade ruhig ist
(kein Gespraech in den letzten 10 Minuten, keine offene Freigabe, kein laufendes Meeting-Protokoll):
    holen (nur fast-forward) -> requirements.txt geaendert? pip install -> Test (alles kompilieren, assistent laden)
    -> Erfolg: Neustart der App, danach Meldung "Update ... laeuft"   |   Fehler: zurueck auf die alte Version + Meldung.
Lokale Aenderungen am Code verhindern das Update (es wird nichts ueberschrieben). Aus: KLAUS_AUTO_UPDATE=0 in der .env.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MARKER = BASE_DIR / "data" / "pc_update_marker.json"
TAKT_S = 30 * 60
ERSTE_PRUEFUNG_S = 3 * 60
RUHE_S = 10 * 60
TEST = ("import glob, py_compile, sys; sys.path.insert(0, 'src'); "
        "[py_compile.compile(f, doraise=True) for f in glob.glob('src/*.py')]; import assistent; print('TEST_OK')")
_OHNE_FENSTER = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def an() -> bool:
    return os.getenv("KLAUS_AUTO_UPDATE", "1").strip() != "0"


def _git(*args: str, frist: float = 120) -> str:
    r = subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=frist, creationflags=_OHNE_FENSTER)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()[:200]}")
    return r.stdout.strip()


def neue_commits() -> list[str]:
    _git("fetch", "-q", "origin", "main")
    return [z for z in _git("log", "--oneline", "--no-decorate", "HEAD..origin/main").splitlines() if z.strip()]


def ruhig(assistent) -> bool:
    """Nur updaten, wenn Klaus gerade nichts fuer Nikola tut."""
    import freigabe

    aktiv = max(getattr(assistent, "letzte_aktivitaet", 0.0), getattr(getattr(assistent, "gemini", None), "letzte_aktivitaet", 0.0) or 0.0)
    protokoll = getattr(assistent, "protokoll", None)
    return (time.time() - aktiv > RUHE_S and not freigabe.offen() and not (protokoll and getattr(protokoll, "laeuft", False)))


def einspielen() -> tuple[bool, str]:
    """Holt origin/main, testet, rollt bei Fehlern zurueck. -> (neu_starten, Meldung)"""
    if _git("status", "--porcelain", "--untracked-files=no"):
        return False, "Kein Auto-Update am PC: im Klaus-Ordner gibt es lokale Code-Änderungen (ich überschreibe nichts)."
    alt = _git("rev-parse", "--short", "HEAD")
    _git("merge", "--ff-only", "-q", "origin/main")
    neu = _git("rev-parse", "--short", "HEAD")
    if neu == alt:
        return False, ""
    try:
        if _git("diff", "--name-only", alt, neu, "--", "requirements.txt"):
            pip = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], cwd=BASE_DIR,
                                 capture_output=True, text=True, timeout=1800, creationflags=_OHNE_FENSTER)
            if pip.returncode != 0:
                raise RuntimeError("pip: " + (pip.stderr or pip.stdout).strip().splitlines()[-1][:150])
        test = subprocess.run([sys.executable, "-c", TEST], cwd=BASE_DIR, capture_output=True, text=True, timeout=300,
                              creationflags=_OHNE_FENSTER)
        if "TEST_OK" not in test.stdout:
            raise RuntimeError(((test.stderr or test.stdout).strip().splitlines() or ["?"])[-1][:150])
    except Exception as e:
        _git("reset", "-q", "--hard", alt)
        return False, f"PC-Update auf {neu} fehlgeschlagen ({e}). Klaus am PC bleibt auf der alten Version {alt}."
    MARKER.parent.mkdir(exist_ok=True)
    MARKER.write_text(json.dumps({"alt": alt, "neu": neu}), encoding="utf-8")
    return True, f"PC-Update {alt} → {neu} getestet, Klaus startet am PC neu."


def nach_neustart() -> str | None:
    if not MARKER.exists():
        return None
    try:
        d = json.loads(MARKER.read_text(encoding="utf-8"))
    finally:
        MARKER.unlink(missing_ok=True)
    try:
        zeilen = _git("log", "--oneline", "--no-decorate", f"{d['alt']}..{d['neu']}").splitlines()
    except Exception:
        zeilen = []
    return f"✅ Klaus am PC ist aktualisiert ({d['alt']} → {d['neu']}).\n" + "\n".join(f"• {z.split(' ', 1)[-1]}" for z in zeilen[:8])


def neustart() -> None:
    """Startet die App neu: neuer Prozess wartet kurz (bis dieser die Prozesssperre freigibt), dieser beendet sich."""
    pythonw = BASE_DIR / ".venv" / "Scripts" / "pythonw.exe"
    programm = pythonw if pythonw.exists() else Path(sys.executable)
    befehl = (f"Start-Sleep -Seconds 6; Start-Process -FilePath '{programm}' "
              f"-ArgumentList '\"{BASE_DIR / 'src' / 'klaus_app.py'}\"' -WorkingDirectory '{BASE_DIR}'")
    subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", befehl], cwd=BASE_DIR,
                     creationflags=_OHNE_FENSTER | getattr(subprocess, "DETACHED_PROCESS", 0))
    threading.Timer(1.5, lambda: os._exit(0)).start()


def _melden(assistent, text: str) -> None:
    print(f"[Update] {text}", flush=True)
    try:
        assistent.log(f"update: {text[:120]}")
        fern = getattr(assistent, "fern", None)
        if fern is not None:
            fern.senden(text)
    except Exception:
        pass


_zuletzt_gemeldet = {"text": ""}


def schritt(assistent) -> bool:
    """Ein Durchlauf. -> True, wenn neu gestartet wird (testbar ohne Schleife)."""
    if not an() or not neue_commits() or not ruhig(assistent):
        return False
    neu_starten, text = einspielen()
    if text and (neu_starten or text != _zuletzt_gemeldet["text"]):   # gleiche Warnung nicht alle 30 Minuten
        _zuletzt_gemeldet["text"] = text
        _melden(assistent, text)
    if neu_starten:
        neustart()
    return neu_starten


def schleife(assistent) -> None:
    time.sleep(ERSTE_PRUEFUNG_S)
    while True:
        try:
            if schritt(assistent):
                return
        except Exception as e:   # kein Netz, kein git ...: still weiter versuchen
            print(f"[Update] {str(e)[:150]}", flush=True)
        time.sleep(TAKT_S)


def starte(assistent) -> None:
    meldung = nach_neustart()
    if meldung:
        threading.Timer(20, lambda: _melden(assistent, meldung)).start()   # warten, bis Telegram/Tunnel stehen
    if an():
        threading.Thread(target=schleife, args=(assistent,), daemon=True, name="klaus-pc-update").start()
