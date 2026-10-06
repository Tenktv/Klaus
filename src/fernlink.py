"""
Klaus - Verbindung PC <-> Server (der Server ist das "Gehirn", der PC der "Koerper").

Der PC waehlt sich selbst per SSH beim Server ein (kein offener Port zuhause) und baut dabei zwei Tunnel auf:
    Server 127.0.0.1:7701  ->  PC 127.0.0.1:7700   der Server bittet den PC, ein Werkzeug auszufuehren
    PC     127.0.0.1:7702  ->  Server 127.0.0.1:7702  der PC meldet dem Server Freigaben/Nachrichten (fuer Telegram)
Beide Seiten sprechen nur ueber diese Tunnel, jede Anfrage braucht den geheimen KLAUS_LINK_TOKEN.
Der Tunnel-Schluessel darf auf dem Server nichts anderes (keine Shell, nur diese beiden Weiterleitungen).

.env (PC):
    KLAUS_LINK_TOKEN         gemeinsames Geheimnis mit dem Server (ohne Token ist alles aus)
    TELEGRAM_AUF_SERVER=1    Telegram laeuft auf dem Server (der PC startet dann keinen eigenen Bot)
    KLAUS_SERVER             Adresse des Servers
"""
from __future__ import annotations

import hmac
import json
import os
import shutil
import subprocess
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import requests
from dotenv import load_dotenv

import freigabe

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

TOKEN = os.getenv("KLAUS_LINK_TOKEN", "").strip()
SERVER = os.getenv("KLAUS_SERVER", "217.154.85.0").strip()
SERVER_BENUTZER = os.getenv("KLAUS_SERVER_BENUTZER", "klaus").strip()
SCHLUESSEL = Path(os.getenv("KLAUS_TUNNEL_SCHLUESSEL", "").strip() or Path.home() / ".ssh" / "klaus_tunnel")
PC_PORT, RUECK_PORT, SERVER_PORT = 7700, 7701, 7702
AKTIV_MIN = 15


def konfiguriert() -> bool:
    return bool(TOKEN) and SCHLUESSEL.exists()


def telegram_auf_server() -> bool:
    return os.getenv("TELEGRAM_AUF_SERVER", "").strip() == "1"


def server_senden(pfad: str, daten: dict, frist: float = 8) -> dict | None:
    """Meldung an den Server (ueber den Tunnel). None = Server gerade nicht erreichbar."""
    try:
        r = requests.post(f"http://127.0.0.1:{SERVER_PORT}{pfad}", json=daten, headers={"X-Token": TOKEN}, timeout=frist)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


# ------------------------------------------------------------------ PC: Werkzeug-Server
def _handler(assistent):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _antwort(self, code: int, daten: dict) -> None:
            roh = json.dumps(daten, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(roh)))
            self.end_headers()
            self.wfile.write(roh)

        def do_POST(self):
            if not hmac.compare_digest(self.headers.get("X-Token", ""), TOKEN):
                return self._antwort(403, {"fehler": "Token"})
            try:
                laenge = int(self.headers.get("Content-Length", "0"))
                if laenge > 1_000_000:
                    return self._antwort(413, {"fehler": "zu gross"})
                d = json.loads(self.rfile.read(laenge) or b"{}")
                if self.path == "/tool":
                    return self._antwort(200, {"ergebnis": _werkzeug(assistent, d.get("name", ""), d.get("args") or {})})
                if self.path == "/gedaechtnis":
                    import gehirn
                    return self._antwort(200, {"text": gehirn.gedaechtnis_text()})
                if self.path == "/entscheide":
                    ok = freigabe.entscheide(d.get("id"), bool(d.get("ok")), str(d.get("wie", "Server"))[:60])
                    return self._antwort(200, {"ok": ok})
                if self.path == "/ereignis":
                    art, text = d.get("art", "info"), str(d.get("text", ""))[:2000]
                    if art == "log":
                        assistent.log(text)
                    else:
                        assistent.b.nachricht.emit(art, text)
                    return self._antwort(200, {"ok": True})
                self._antwort(404, {"fehler": "unbekannt"})
            except Exception as e:
                traceback.print_exc()
                self._antwort(500, {"fehler": str(e)[:200]})

        def do_GET(self):
            self._antwort(200, {"ok": True, "pc": True})

    return H


def _werkzeug(assistent, name: str, args: dict) -> str:
    """Fuehrt ein Werkzeug auf dem PC aus - dieselben wie in Gemini Live, inkl. Freigabe-Gate."""
    if assistent.gemini is None:
        return "Auf dem PC ist Gemini nicht eingerichtet."
    if isinstance(assistent.fern, FernProxy):
        assistent.fern.zuletzt = time.time()   # Antworten dieses Auftrags gehen aufs Handy, nicht in den Lautsprecher
    print(f"[Link] Werkzeug vom Server: {name}")
    assistent.log(f"link/{name}")
    return assistent.gemini._werkzeug(name, dict(args))


# ------------------------------------------------------------------ PC: meldet dem Server (Telegram laeuft dort)
class FernProxy:
    """Steht auf dem PC anstelle des Telegram-Bots, wenn der Bot auf dem Server laeuft."""
    nutzer = 1

    def __init__(self, assistent) -> None:
        self.a = assistent
        self.zuletzt = 0.0

    def aktiv(self) -> bool:
        return time.time() - self.zuletzt < AKTIV_MIN * 60

    def senden(self, text: str, **extra) -> None:
        server_senden("/senden", {"text": text})

    def hinweis(self, text: str) -> None:
        pass   # Erinnerungen schickt der Server selbst, sonst kaemen sie doppelt

    def freigabe_melden(self, ereignis: str, a) -> None:
        import telegram_bot

        if ereignis == "auf" and not (self.aktiv() or telegram_bot.abwesend_min() >= telegram_bot.ABWESEND_MIN):
            return   # du sitzt am PC: Freigabe im Panel/per Stimme, nicht auf dem Handy
        server_senden("/freigabe", {"ereignis": ereignis, "id": a.id, "art": a.art, "was": a.was, "an": a.an,
                                    "anzahl": a.anzahl, "ok": a.ok, "wie": a.wie})


# ------------------------------------------------------------------ PC: SSH-Tunnel
def _job_mit_autoende():
    """Windows-Job: alles darin wird beendet, sobald Klaus endet (auch bei hartem Abschuss) - kein verwaister ssh.exe."""
    import ctypes
    from ctypes import wintypes

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("a", "b", "c", "d", "e", "f")]

    class EXT(ctypes.Structure):
        _fields_ = [("Basic", BASIC), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k = ctypes.windll.kernel32
    k.CreateJobObjectW.restype = wintypes.HANDLE
    job = k.CreateJobObjectW(None, None)
    info = EXT()
    info.Basic.LimitFlags = 0x2000   # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    k.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info))
    return job


def _alte_tunnel_beenden() -> None:
    """Reste eines frueheren Klaus-Laufs (ssh.exe mit unserem Tunnel-Schluessel) beenden."""
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-CimInstance Win32_Process -Filter \"Name='ssh.exe'\" | Where-Object CommandLine -like '*klaus_tunnel*' "
                        "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                       capture_output=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        pass


class Tunnel(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True, name="klaus-tunnel")
        self.verbunden = False
        self.proc: subprocess.Popen | None = None

    def run(self) -> None:
        ssh = shutil.which("ssh") or r"C:\Windows\System32\OpenSSH\ssh.exe"
        _alte_tunnel_beenden()
        try:
            job = _job_mit_autoende()
        except Exception as e:
            job = None
            print(f"[Link] Job-Objekt nicht moeglich ({e}) - Tunnel endet evtl. nicht mit Klaus")
        bekannt = BASE_DIR / "data" / "server_known_hosts"
        warte = 10
        while True:
            cmd = [ssh, "-N", "-T", "-i", str(SCHLUESSEL), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
                   "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3",
                   "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={bekannt}",
                   "-R", f"127.0.0.1:{RUECK_PORT}:127.0.0.1:{PC_PORT}", "-L", f"127.0.0.1:{SERVER_PORT}:127.0.0.1:{SERVER_PORT}",
                   f"{SERVER_BENUTZER}@{SERVER}"]
            start = time.time()
            try:
                self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if job:
                    import ctypes
                    from ctypes import wintypes
                    ctypes.windll.kernel32.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(int(self.proc._handle)))
                self.verbunden = True
                print("[Link] Tunnel zum Server gestartet")
                _, err = self.proc.communicate()
                self.verbunden = False
                print(f"[Link] Tunnel beendet ({(err or b'').decode('utf-8', 'replace').strip()[:120]})")
            except Exception as e:
                self.verbunden = False
                print(f"[Link] Tunnel-Fehler: {e}")
            warte = 10 if time.time() - start > 120 else min(warte * 2, 120)   # lief er lange, gleich neu; sonst langsamer
            time.sleep(warte)


def starte(assistent) -> Tunnel:
    """Werkzeug-Server (nur 127.0.0.1) + Tunnel im Hintergrund."""
    server = ThreadingHTTPServer(("127.0.0.1", PC_PORT), _handler(assistent))
    threading.Thread(target=server.serve_forever, daemon=True, name="klaus-link-server").start()
    tunnel = Tunnel()
    tunnel.start()
    print(f"[Link] bereit (Werkzeug-Server :{PC_PORT}, Telegram {'auf dem Server' if telegram_auf_server() else 'lokal'})")
    return tunnel
