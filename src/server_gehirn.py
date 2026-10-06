"""
Klaus - Gehirn auf dem Server (ohne Fenster, Mikro und Lautsprecher). Laeuft als systemd-Dienst `klaus-gehirn`.

- Telegram-Bot rund um die Uhr (Gemini + Werkzeuge), auch wenn der PC aus ist.
- Werkzeuge, die nur Daten im Netz brauchen (Kalender, Recherche, Markt-Analyse), laufen hier.
- Alles andere (Apps, Dateien, Drucken, Gedaechtnis, Panel ...) bittet den PC ueber den Tunnel (fernlink.py);
  ist der PC nicht erreichbar, sagt Klaus das ehrlich und fuehrt nichts aus.
- Freigaben fuer PC-Aktionen kommen vom PC (Knopf in Telegram + PIN) und gehen auch dorthin zurueck.
"""
import hmac
import json
import os
import sys
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

# --- Attrappe fuer PySide6 (assistent.py nutzt nur QObject/Signal; hier gibt es kein Fenster) ---
_pyside, _qtcore = types.ModuleType("PySide6"), types.ModuleType("PySide6.QtCore")


class _QObject:
    def __init__(self, *a, **k):
        pass


class _Signal:
    def __init__(self, *a):
        pass

    def emit(self, *a):
        pass

    def connect(self, *a):
        pass


_qtcore.QObject, _qtcore.Signal = _QObject, lambda *a, **k: _Signal()
_pyside.QtCore = _qtcore
sys.modules["PySide6"], sys.modules["PySide6.QtCore"] = _pyside, _qtcore

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.chdir(BASE_DIR)

import requests
from dotenv import load_dotenv

load_dotenv(BASE_DIR / ".env")

import assistent as A
import freigabe
import telegram_bot as TB

TOKEN = os.getenv("KLAUS_LINK_TOKEN", "").strip()
RUECK_PORT, SERVER_PORT = 7701, 7702
LOKAL = {"kalender_lesen", "termin_eintragen", "zeit_frei", "recherche", "markt_analyse"}
GEDAECHTNIS = BASE_DIR / "data" / "gedaechtnis_cache.txt"


def pc_post(pfad: str, daten: dict, frist: float = 6):
    r = requests.post(f"http://127.0.0.1:{RUECK_PORT}{pfad}", json=daten, headers={"X-Token": TOKEN}, timeout=frist)
    r.raise_for_status()
    return r.json()


class LazyOhr:
    """Whisper erst laden, wenn die erste Sprachnachricht kommt (spart Arbeitsspeicher)."""
    _modell = None
    geraet = None
    schwelle = 0.0002

    @property
    def model(self):
        if self._modell is None:
            from faster_whisper import WhisperModel
            self._modell = WhisperModel(os.getenv("WHISPER_MODEL_SERVER", "small"), device="cpu", compute_type="int8")
        return self._modell


class ServerAssistent(A.Assistent):
    """Der Assistent ohne Fenster: Antworten gehen immer an Telegram."""

    erinnerungen_aus = False   # der Server erinnert aufs Handy

    def __init__(self) -> None:
        self.telegram = None
        super().__init__(A.Bruecke(), dry_run=False)
        self.ohr = LazyOhr()

    def sage(self, text: str, zustand: str = "sprechen") -> None:
        if self.telegram:
            self.telegram.senden(text)

    def zeige(self, zustand, text=None) -> None:
        pass

    def verschwinde(self, nach: float = 0.0) -> None:
        pass

    def log(self, text: str) -> None:
        print(f"[log] {text}")

    def setze_mikro_aus(self, aus: bool) -> None:
        pc_werkzeug("mikrofon", {"an": not aus})


def pc_werkzeug(name: str, args: dict) -> str:
    try:
        return pc_post("/tool", {"name": name, "args": args}, frist=240)["ergebnis"]
    except Exception:
        return ("Dein PC ist gerade nicht erreichbar (aus oder nicht verbunden). Ich habe nichts ausgeführt – "
                "sag Nikola, dass diese Funktion den PC braucht.")


def bauen(innen: bool = True):
    """Verdrahtet Assistent + Telegram + Tunnel-Gegenstellen. innen=False: ohne den Server fuer Meldungen vom PC (Tests)."""
    if not TOKEN:
        sys.exit("KLAUS_LINK_TOKEN fehlt")
    a = ServerAssistent()
    tg = TB.TelegramKlaus(a)
    a.telegram = tg
    remote_ids: set[str] = set()

    # Werkzeuge: Daten-Werkzeuge hier, Rest auf dem PC
    tg.werkzeug_aufruf = lambda name, args: a.gemini._werkzeug(name, args) if name in LOKAL else pc_werkzeug(name, args)

    # Gedaechtnis kommt vom PC (zuletzt bekannter Stand, wenn der PC aus ist)
    def gedaechtnis() -> str:
        try:
            text = pc_post("/gedaechtnis", {}, frist=4)["text"]
            GEDAECHTNIS.parent.mkdir(exist_ok=True)
            GEDAECHTNIS.write_text(text, encoding="utf-8")
            return text
        except Exception:
            return GEDAECHTNIS.read_text(encoding="utf-8") if GEDAECHTNIS.exists() else ""
    tg.gedaechtnis_fn = gedaechtnis

    # Freigaben: PC-Anfragen werden auf dem PC entschieden, eigene (Kalender) hier
    def entscheider(fid, ok, wie):
        if fid in remote_ids:
            try:
                return bool(pc_post("/entscheide", {"id": fid, "ok": ok, "wie": wie}, frist=8)["ok"])
            except Exception:
                return False
        return freigabe.entscheide(fid, ok, wie)
    tg.entscheider = entscheider

    # Chat-Zeilen ans Panel des PCs (best effort, blockiert nie)
    tg.ereignis_fn = lambda art, text: threading.Thread(
        target=lambda: _versuche(lambda: pc_post("/ereignis", {"art": art, "text": text}, frist=3)), daemon=True).start()

    freigabe.melden = lambda ereignis, anfrage: tg.freigabe_melden(ereignis, anfrage)

    class Innen(BaseHTTPRequestHandler):
        """Nimmt Meldungen vom PC an (nur 127.0.0.1, ueber den Tunnel)."""
        def log_message(self, *x):
            pass

        def do_POST(self):
            if not hmac.compare_digest(self.headers.get("X-Token", ""), TOKEN):
                self.send_response(403); self.end_headers(); return
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
            if self.path == "/senden":
                tg.senden(str(d.get("text", ""))[:4000])
            elif self.path == "/freigabe":
                if d["ereignis"] == "auf":
                    remote_ids.add(d["id"])
                tg.freigabe_melden(d["ereignis"], SimpleNamespace(**{k: d.get(k) for k in ("id", "art", "was", "an", "anzahl", "ok", "wie")}))
                if d["ereignis"] != "auf":
                    remote_ids.discard(d["id"])
            roh = b'{"ok": true}'
            self.send_response(200); self.send_header("Content-Length", str(len(roh))); self.end_headers(); self.wfile.write(roh)

    if innen:
        threading.Thread(target=ThreadingHTTPServer(("127.0.0.1", SERVER_PORT), Innen).serve_forever, daemon=True).start()
    return a, tg


def main() -> None:
    a, tg = bauen()
    print(f"[Server] Klaus-Gehirn laeuft (Telegram, Werkzeuge lokal: {sorted(LOKAL)})", flush=True)
    tg.run()   # blockiert


def _versuche(f):
    try:
        f()
    except Exception:
        pass


if __name__ == "__main__":
    main()
