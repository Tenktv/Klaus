"""
Klaus - automatisches Update auf dem PC (Code aus GitHub, Tenktv/Klaus, Zweig main).

Alle 30 Minuten (erstes Mal 3 Minuten nach dem Start): neue Commits auf origin/main? Wenn Klaus gerade ruhig ist
(kein Gespraech in den letzten 10 Minuten, keine offene Freigabe, kein laufendes Meeting-Protokoll):
    holen (nur fast-forward) -> requirements.txt geaendert? pip install -> Test (alles kompilieren, assistent laden)
    -> Erfolg: Neustart der App, danach Meldung "Update ... laeuft"   |   Fehler: zurueck auf die alte Version + Meldung.
Lokale Aenderungen am Code verhindern das Update (es wird nichts ueberschrieben). Aus: KLAUS_AUTO_UPDATE=0 in der .env.

Installiert ueber Klaus-Setup.exe (kein .git-Ordner): stattdessen neueste Version aus dem oeffentlichen Repo
KLAUS_UPDATE_REPO (Standard Tenktv/Klaus; privat -> KLAUS_UPDATE_TOKEN) - Setup.exe laden, SHA256 pruefen, still installieren (/UPDATE=1);
der Installer beendet Klaus, behaelt .env/data und startet ihn danach neu.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
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
# Undefinierte Namen (z. B. vergessener Import in main) - laden allein findet das nicht; ohne pyflakes wird es uebersprungen
FLAKES = ("\ntry:\n    import io, pyflakes.api as pf, pyflakes.reporter as pr\nexcept ImportError:\n    pf = None\n"
          "if pf:\n    out = io.StringIO()\n    for f in glob.glob('src/*.py'):\n        pf.checkPath(f, pr.Reporter(out, out))\n"
          "    fehler = [z for z in out.getvalue().splitlines() if 'undefined name' in z]\n"
          "    if fehler:\n        raise SystemExit('pyflakes: ' + fehler[0])\n")
TEST = ("import glob, py_compile, sys; sys.path.insert(0, 'src'); "
        "[py_compile.compile(f, doraise=True) for f in glob.glob('src/*.py')]; ")
TEST = TEST + FLAKES + "import assistent; print('TEST_OK')"
_OHNE_FENSTER = getattr(subprocess, "CREATE_NO_WINDOW", 0)
UPDATE_REPO = os.getenv("KLAUS_UPDATE_REPO", "Tenktv/Klaus").strip()
UPDATE_TOKEN = os.getenv("KLAUS_UPDATE_TOKEN", "").strip()   # nur noetig, solange das Repo privat ist (Lesezugriff reicht)


def _kopf(datei: bool = False) -> dict:
    k = {"Accept": "application/octet-stream" if datei else "application/vnd.github+json"}
    if UPDATE_TOKEN:
        k["Authorization"] = f"Bearer {UPDATE_TOKEN}"
    return k


# ------------------------------------------------------------------ Installierte Version (Klaus-Setup.exe, ohne git)
def installiert() -> bool:
    return not (BASE_DIR / ".git").exists()


def version() -> str:
    try:
        return (BASE_DIR / "VERSION").read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def _zahlen(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", text)[:3]) or (0,)


def release_pruefen() -> tuple[dict | None, str]:
    """Neuere Klaus-Setup.exe im Download-Repo? -> ({tag, url, sha256} oder None, Grund zum Anzeigen)."""
    import requests

    r = requests.get(f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest", timeout=15, headers=_kopf())
    if r.status_code in (401, 403, 404):
        return None, ("GitHub lässt mich nicht an die Updates: Das Repo ist privat und der Update-Token fehlt oder ist "
                      "abgelaufen (KLAUS_UPDATE_TOKEN in den Einstellungen)." if r.status_code != 403 or not UPDATE_TOKEN
                      else "Der Update-Token hat keine Leserechte auf das Repo.")
    if r.status_code != 200:
        return None, f"GitHub antwortet gerade nicht ({r.status_code}) – später nochmal."
    d = r.json()
    tag = str(d.get("tag_name") or "")
    if _zahlen(tag) <= _zahlen(version()):
        return None, f"Du hast schon die neueste Version ({version()})."
    datei = next((a for a in d.get("assets") or [] if str(a.get("name", "")).lower() == "klaus-setup.exe"), None)
    pruef = re.search(r"SHA256:\s*([0-9a-f]{64})", str(d.get("body") or ""), re.I)
    if not datei or not pruef:   # ohne Pruefsumme installiere ich nichts
        return None, f"Version {tag} ist noch nicht fertig hochgeladen – gleich nochmal versuchen."
    # privates Repo: ueber die API-Adresse der Datei laden (mit Token), oeffentlich: direkter Download-Link
    return ({"tag": tag, "url": datei["url"] if UPDATE_TOKEN else datei["browser_download_url"],
             "sha256": pruef.group(1).lower()}, "")


def neues_release() -> dict | None:
    rel, grund = release_pruefen()
    if not rel:
        print(f"[Update] {grund}", flush=True)
    return rel


def jetzt_pruefen(assistent) -> str:
    """Taskleisten-Menue "Nach Updates suchen": sofort pruefen und installieren (ohne Warten auf ruhige Momente)."""
    if installiert():
        rel, grund = release_pruefen()
        if not rel:
            return grund
        gestartet, text = release_einspielen(rel)
        if gestartet:
            threading.Timer(3, lambda: os._exit(0)).start()
        return text
    neu = neue_commits()
    if not neu:
        return f"Du hast schon den neuesten Stand ({version()})."
    neu_starten, text = einspielen()
    if neu_starten:
        threading.Timer(3, neustart).start()
    return text or "Update eingespielt."


def release_einspielen(rel: dict) -> tuple[bool, str]:
    import tempfile

    import requests

    ziel = Path(tempfile.gettempdir()) / f"Klaus-Setup-{re.sub(r'[^0-9A-Za-z.]', '', rel['tag'])}.exe"
    summe = hashlib.sha256()
    with requests.get(rel["url"], stream=True, timeout=(15, 300), headers=_kopf(datei=True) if UPDATE_TOKEN else None) as r:
        r.raise_for_status()
        with open(ziel, "wb") as f:
            for stueck in r.iter_content(1 << 20):
                summe.update(stueck)
                f.write(stueck)
    if summe.hexdigest() != rel["sha256"]:
        ziel.unlink(missing_ok=True)
        return False, f"Update {rel['tag']} abgebrochen: die heruntergeladene Datei ist beschädigt (Prüfsumme falsch)."
    MARKER.parent.mkdir(exist_ok=True)
    MARKER.write_text(json.dumps({"alt": version(), "neu": rel["tag"], "art": "release"}), encoding="utf-8")
    subprocess.Popen([str(ziel), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/UPDATE=1"], cwd=str(ziel.parent),
                     creationflags=_OHNE_FENSTER | getattr(subprocess, "DETACHED_PROCESS", 0))
    return True, f"Update {version()} → {rel['tag']} wird installiert, Klaus startet gleich neu."


def release_schritt(assistent) -> bool:
    rel = neues_release()
    if not rel or not ruhig(assistent):
        return False
    if os.getenv("KLAUS_UPDATE_FREIGABE", "0").strip() == "1" and rel["tag"] != _gefragt["stand"]:
        import freigabe

        _gefragt["stand"] = rel["tag"]
        token = freigabe.anfragen("pc_update", f"Klaus auf Version {rel['tag']} aktualisieren", an="Klaus am PC (Download)")
        if not token:
            return False
        freigabe.pruefe(token, "pc_update")
    elif os.getenv("KLAUS_UPDATE_FREIGABE", "0").strip() == "1":
        return False
    gestartet, text = release_einspielen(rel)
    _melden(assistent, text)
    if gestartet:
        threading.Timer(3, lambda: os._exit(0)).start()   # der Installer beendet Klaus ohnehin und startet ihn neu
    return gestartet


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


SPIELE = ("robloxplayerbeta", "league of legends", "valorant-win64-shipping", "cs2", "skyrimse", "tesv",
          "minecraft", "javaw", "fortniteclient-win64-shipping", "gta5", "rocketleague")


def spiel_laeuft() -> bool:
    """Laeuft gerade ein Spiel? Dann nie neu starten (Ruckler/Absturz mitten im Spiel)."""
    try:
        import psutil
        return any((p.info["name"] or "").lower().removesuffix(".exe") in SPIELE for p in psutil.process_iter(["name"]))
    except Exception:
        return False


def ruhig(assistent) -> bool:
    """Nur updaten, wenn Klaus gerade nichts fuer Nikola tut - und niemand spielt."""
    import freigabe

    if spiel_laeuft():
        return False

    aktiv = max(getattr(assistent, "letzte_aktivitaet", 0.0), getattr(getattr(assistent, "gemini", None), "letzte_aktivitaet", 0.0) or 0.0)
    protokoll = getattr(assistent, "protokoll", None)
    return (time.time() - aktiv > RUHE_S and not freigabe.offen() and not (protokoll and getattr(protokoll, "laeuft", False)))


def einspielen() -> tuple[bool, str]:
    """Holt origin/main, testet, rollt bei Fehlern zurueck. -> (neu_starten, Meldung)"""
    if _git("status", "--porcelain", "--untracked-files=no", "--", ".", ":(exclude)data"):   # Laufzeitdaten zaehlen nicht
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
    if d.get("art") == "release":
        return f"✅ Klaus ist aktualisiert: Version {d['alt']} → {d['neu'].lstrip('v')}."
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


_gefragt = {"stand": ""}   # fuer diesen GitHub-Stand schon gefragt (nicht alle 30 Minuten neu nerven)


def freigegeben(neu: list[str]) -> bool:
    """Standard (Wunsch Nikola, 17.10.2026): immer automatisch, ohne PIN. Mit KLAUS_UPDATE_FREIGABE=1 in der .env fragt Klaus
    vorher (Knopf + PIN) - einmal je neuem GitHub-Stand; abgelehnt/keine Antwort -> erst bei weiteren Commits wieder."""
    import freigabe

    if os.getenv("KLAUS_UPDATE_FREIGABE", "0").strip() != "1":
        return True
    stand = _git("rev-parse", "--short", "origin/main")
    if stand == _gefragt["stand"]:
        return False
    _gefragt["stand"] = stand
    liste = "; ".join(z.split(" ", 1)[-1] for z in neu[:5])
    token = freigabe.anfragen("pc_update", f"Klaus am PC aktualisieren ({len(neu)} Änderung{'en' if len(neu) != 1 else ''}: {liste[:300]})",
                              an="Klaus am PC (Code aus GitHub)")
    if not token:
        return False
    freigabe.pruefe(token, "pc_update")
    return True


def schritt(assistent) -> bool:
    """Ein Durchlauf. -> True, wenn neu gestartet wird (testbar ohne Schleife)."""
    if not an():
        return False
    if installiert():
        return release_schritt(assistent)
    neu = neue_commits()
    if not neu or not ruhig(assistent) or not freigegeben(neu):
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
