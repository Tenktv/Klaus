"""
Klaus am PC - Fehlerbericht an Nikolas Server (fehlerberichte.py), der ihn per Telegram an Nikola schickt.

.env (beim Tester):
    KLAUS_MELDE_CODE=km_...        bekommt der Tester von Nikola (/melde_code Name). Ohne Code wird nichts gesendet.
    KLAUS_BERICHT_URL=             Standard: http://<KLAUS_SERVER>:7720/bericht

Automatisch bei: Klaus startet nicht, Fehler im Gespraech (hoechstens alle 10 Minuten, gleicher Fehler nur einmal).
Von Hand: Taskleisten-Menue "Fehlerbericht senden".
Im Bericht: Version, Windows, Grafikkarte, Mikrofon, welche Dienste eingerichtet sind (nur ja/nein), Stimme, Update-Stand
und die letzten Log-Zeilen - Schluessel, Tokens und Passwoerter werden vorher geschwaerzt.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG = BASE_DIR / "data" / "klaus.log"
ABSTAND_S = 10 * 60
_z = {"zuletzt": 0.0, "gesendet": set()}
_OHNE_FENSTER = getattr(subprocess, "CREATE_NO_WINDOW", 0)
GEHEIM_MUSTER = re.compile(r"AIza[0-9A-Za-z_\-]{30,}|AQ\.[0-9A-Za-z_\-]{20,}|tvly-[0-9A-Za-z_\-]{20,}|sk-[0-9A-Za-z_\-]{20,}|"
                           r"gsk_[0-9A-Za-z]{20,}|gh[pousr]_[0-9A-Za-z]{30,}|github_pat_\w{30,}|km_[\w-]{20,}|"
                           r"\d{8,10}:AA[\w-]{30,}|PK[A-Z0-9]{16,}")


def code() -> str:
    return os.getenv("KLAUS_MELDE_CODE", "").strip()


def ziel() -> str:
    eigen = os.getenv("KLAUS_BERICHT_URL", "").strip()
    if eigen:
        return eigen
    return f"http://{os.getenv('KLAUS_SERVER', '217.154.85.0').strip()}:7720/bericht"


def schwaerzen(text: str) -> str:
    """Werte aus der .env (*KEY, *PASS*, *TOKEN, *SECRET, *CODE, *WEBHOOK) und typische Schluessel-Muster -> ***."""
    for name, wert in os.environ.items():
        if re.search(r"KEY|PASS|TOKEN|SECRET|CODE|WEBHOOK|PIN", name.upper()) and len(wert.strip()) >= 6:
            text = text.replace(wert.strip(), "***")
    return GEHEIM_MUSTER.sub("***", text)


def _befehl(*args: str) -> str:
    try:
        r = subprocess.run(list(args), capture_output=True, text=True, timeout=8, creationflags=_OHNE_FENSTER,
                           encoding="utf-8", errors="replace")
        return r.stdout.strip()
    except Exception:
        return ""


def _grafik() -> str:
    if os.name != "nt":
        return "?"
    roh = _befehl("powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name -join ', '")
    return roh or "?"


def _mikro() -> str:
    try:
        import sounddevice as sd
        d = sd.query_devices(kind="input")
        return d.get("name", "?")
    except Exception as e:
        return f"keins gefunden ({str(e)[:60]})"


def _log_ende(zeilen: int = 150) -> str:
    try:
        with open(LOG, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 200_000))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        return "(kein Log gefunden)"
    return "\n".join(text.splitlines()[-zeilen:])


def letzter_fehler(log: str) -> str:
    """Letzter Traceback aus dem Log (Kopfzeile + letzte Zeile) - fuer die Kurzfassung."""
    stuecke = log.split("Traceback (most recent call last):")
    if len(stuecke) < 2:
        return ""
    zeilen = [z for z in stuecke[-1].splitlines() if z.strip()]
    fehler = next((z for z in zeilen if re.match(r"^\w+(\.\w+)*(Error|Exception|Fehler)\b", z.strip())), zeilen[-1] if zeilen else "")
    ort = next((z.strip() for z in reversed(zeilen) if z.strip().startswith('File "')), "")
    return f"{fehler.strip()}\n{ort}"[:500]


def erstellen(anlass: str) -> dict:
    import identitaet

    def ja(name: str) -> str:
        return "ja" if os.getenv(name, "").strip() else "nein"

    try:
        import pc_update
        stand = pc_update.version()
        rel, grund = pc_update.release_pruefen()
        update = f"Update auf {rel['tag']} verfügbar" if rel else grund
    except Exception as e:
        stand, update = "?", f"Update-Prüfung ging nicht: {str(e)[:80]}"
    try:
        import stimmwahl
        stimme = stimmwahl.aktiv()["name"] + (f" (gerade aus: {stimmwahl._ausfall['grund'][:80]})"
                                               if stimmwahl.extern_gesperrt() else "")
    except Exception:
        stimme = "?"
    log = schwaerzen(_log_ende())
    kopf = [f"Assistent: {identitaet.NAME} · Nutzer: {identitaet.NUTZER or '-'}",
            f"Version: {stand} · {platform.platform()}",
            f"Grafik: {_grafik()} · Mikrofon: {_mikro()}",
            f"Gemini: {ja('GEMINI_API_KEY')} · Groq: {ja('GROQ_API_KEY')} · OpenRouter: {ja('OPENROUTER_API_KEY')} · "
            f"Fish: {ja('FISH_API_KEY')} · Stimme: {stimme}",
            f"Update: {update}"]
    fehler = letzter_fehler(log)
    kurz = "\n".join(kopf) + (f"\n\nLetzter Fehler:\n{fehler}" if fehler else "")
    return {"anlass": anlass, "kurz": schwaerzen(kurz), "text": schwaerzen("\n".join(kopf)) + f"\n\nAnlass: {anlass}\n\n"
            + "--- letzte Log-Zeilen ---\n" + log}


def senden(anlass: str) -> str:
    """Bericht schicken. -> Text fuers Anzeigen."""
    import requests

    if not code():
        return ("Fehlerbericht geht noch nicht: Es fehlt der Melde-Code. Den bekommst du von Nikola "
                "(Einstellungen: KLAUS_MELDE_CODE=...).")
    daten = erstellen(anlass)
    roh = json.dumps(daten, ensure_ascii=False).encode("utf-8")
    if len(roh) > 60_000:   # Server nimmt hoechstens 64 KB
        daten["text"] = daten["text"][-50_000:]
        roh = json.dumps(daten, ensure_ascii=False).encode("utf-8")
    try:
        r = requests.post(ziel(), data=roh, timeout=15, headers={"Content-Type": "application/json", "X-Melde-Code": code()})
    except requests.RequestException as e:
        return f"Fehlerbericht ging nicht raus (Server nicht erreichbar): {str(e)[:100]}"
    try:
        text = r.json().get("text", "")
    except ValueError:
        text = ""
    if r.status_code == 200:
        return "Fehlerbericht ist an Nikola geschickt."
    if r.status_code == 403:
        return "Fehlerbericht abgelehnt: Der Melde-Code stimmt nicht (neuen bei Nikola holen)."
    return f"Fehlerbericht ging nicht ({r.status_code}): {text}"


def automatisch(anlass: str, fehler_text: str = "") -> None:
    """Bei Abstuerzen/Startfehlern: im Hintergrund senden, hoechstens alle 10 Minuten, denselben Fehler nur einmal."""
    if not code():
        return
    kennung = hashlib.sha1((anlass + fehler_text[-300:]).encode("utf-8", "replace")).hexdigest()
    jetzt = time.time()
    if kennung in _z["gesendet"] or jetzt - _z["zuletzt"] < ABSTAND_S:
        return
    _z["gesendet"].add(kennung)
    _z["zuletzt"] = jetzt

    def los() -> None:
        time.sleep(2)   # Traceback erst ins Log schreiben lassen
        try:
            print(f"[Fehlerbericht] {senden(anlass)}", flush=True)
        except Exception as e:
            print(f"[Fehlerbericht] ging nicht: {str(e)[:120]}", flush=True)
    threading.Thread(target=los, daemon=True, name="fehlerbericht").start()
