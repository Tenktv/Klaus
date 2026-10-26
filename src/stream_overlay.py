"""
Klaus - Stream-Overlay fuer OBS (Browserquelle): http://127.0.0.1:7710/overlay

Zeigt Klaus' Reaktor-Orb (derselbe wie im Panel, web/klaus.js), seine Untertitel, wenn er spricht, den Twitch-Chat,
Willkommens-Karten fuer neue Leute, Clip-Blitz und Banner, die Nikola per Stimme setzt ("Klaus, zeig im Stream ...").
Teilansichten fuer eigene Platzierung in OBS: /overlay?nur=orb, ?nur=chat, ?nur=hinweise.

Nur 127.0.0.1, nur lesend: Die Seite bekommt Ereignisse per Server-Sent Events (/ereignisse), sie kann nichts an Klaus
senden. Chat-Text wird im Browser nur als Text gesetzt (nie als HTML).
"""
from __future__ import annotations

import json
import mimetypes
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

WEB_DIR = Path(__file__).resolve().parent / "web"
PORT = 7710
URL = f"http://127.0.0.1:{PORT}/overlay"

_hoerer: list[queue.Queue] = []
_sperre = threading.Lock()
_zuletzt = {"pegel": 0.0}
_zustand = {"zustand": "aus", "banner": "", "kamera": None, "pause": {"an": False}}   # fuer neu verbundene Seiten (OBS laedt die Quelle oft neu)


def senden(art: str, daten=None) -> None:
    """Ereignis an alle offenen Overlays. Thread-sicher, blockiert nie."""
    if art == "pegel":   # kommt sehr oft -> hoechstens ~15/s, 0 immer
        jetzt = time.monotonic()
        if daten and jetzt - _zuletzt["pegel"] < 0.066:
            return
        _zuletzt["pegel"] = jetzt
    if art in ("zustand", "banner", "kamera", "pause"):
        _zustand[art] = daten
    roh = f"event: {art}\ndata: {json.dumps(daten, ensure_ascii=False)}\n\n".encode("utf-8")
    with _sperre:
        for q in list(_hoerer):
            try:
                q.put_nowait(roh)
            except queue.Full:
                pass   # Seite haengt -> Ereignis verwerfen statt Klaus aufzuhalten


def _thema() -> str:
    try:
        import daten
        return daten.lade_einstellungen().get("thema", "jarvis")
    except Exception:
        return "gold"


class _Anfrage(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass

    def do_GET(self) -> None:
        pfad = urlparse(self.path).path
        if pfad in ("/", "/overlay"):
            return self._datei(WEB_DIR / "stream_overlay.html")
        if pfad == "/pause":   # Pause-Bildschirm (Szene "Pause")
            return self._datei(WEB_DIR / "stream_pause.html")
        if pfad == "/ereignisse":
            return self._ereignisse()
        ziel = (WEB_DIR / pfad.lstrip("/")).resolve()
        if WEB_DIR.resolve() not in ziel.parents or not ziel.is_file():   # nur Dateien aus src/web
            self.send_error(404)
            return
        self._datei(ziel)

    def _datei(self, ziel: Path) -> None:
        inhalt = ziel.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(ziel.name)[0] or "application/octet-stream")
                         + ("; charset=utf-8" if ziel.suffix in (".html", ".js", ".css") else ""))
        self.send_header("Content-Length", str(len(inhalt)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(inhalt)

    def _ereignisse(self) -> None:
        q: queue.Queue = queue.Queue(maxsize=200)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        with _sperre:   # zuerst anmelden: Ereignisse waehrend der (langsamen) OBS-Abfrage unten gehen sonst verloren
            _hoerer.append(q)
        import stream
        import identitaet
        import stream_chatbot
        start = [("name", {"name": identitaet.NAME, "befehl": stream_chatbot.befehl_name()}),   # Tester: eigener Name
                 ("thema", _thema()), ("zustand", _zustand["zustand"]), ("banner", _zustand["banner"])]
        if stream.KANAL:
            start.append(("kanal", stream.KANAL))
        _zustand["kamera"] = stream.kamera_zustand()   # immer frisch aus OBS (Nikola schaltet sie auch dort selbst)
        start.append(("kamera", _zustand["kamera"]))
        start.append(("pause", _zustand["pause"]))
        try:
            for art, d in start:
                self.wfile.write(f"event: {art}\ndata: {json.dumps(d, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()
            while True:
                try:
                    self.wfile.write(q.get(timeout=15))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")   # haelt die Verbindung offen, merkt geschlossene Seiten
                self.wfile.flush()
        except (OSError, ValueError):
            pass
        finally:
            with _sperre:
                if q in _hoerer:
                    _hoerer.remove(q)


def starten(wache: bool = True) -> bool:
    """wache=False nur fuer Tests (die sollen das echte OBS nicht anfassen)."""
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), _Anfrage)
    except OSError as e:
        print(f"[Overlay] Port {PORT} belegt: {e}")
        return False
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name="stream-overlay").start()
    if wache:
        threading.Thread(target=_wache, daemon=True, name="overlay-wache").start()
    print(f"[Overlay] {URL}")
    return True


QUELLEN = ("Klaus Overlay", "Klaus Pause")


def _wache() -> None:
    """1) Kurz nach dem Start die Browserquellen in OBS neu laden: hat OBS sie geladen, waehrend Klaus neu startete,
    bleiben sie sonst leer (OBS versucht es nie von selbst nochmal).
    2) Alle 3 s, solange ein Overlay verbunden ist: Webcam an/aus und Pause-Szene aus OBS nachziehen - auch wenn
    Nikola in OBS selbst klickt."""
    import stream

    time.sleep(3)
    try:
        for q in QUELLEN:
            stream.obs_anfrage("PressInputPropertiesButton", {"inputName": q, "propertyName": "refreshnocache"})
        print("[Overlay] OBS-Quellen neu geladen")
    except RuntimeError:
        pass   # OBS laeuft nicht oder Quelle gibt es (noch) nicht
    bild, gleich, neu_gestartet = "", 0, 0.0
    while True:
        time.sleep(3)
        if not _hoerer:
            continue
        try:
            szene = stream.obs_anfrage("GetCurrentProgramScene").get("currentProgramSceneName", "")
        except RuntimeError:
            continue
        kamera = stream.kamera_zustand()
        if kamera != _zustand["kamera"]:
            senden("kamera", kamera)
        # 3) Eingefrorene Webcam: 12 s exakt dasselbe Bild -> neu starten (hoechstens einmal pro Minute)
        if kamera.get("an"):
            try:
                jetzt = stream.kamera_bild_kennung()
            except RuntimeError:
                jetzt = ""
            gleich = gleich + 1 if jetzt and jetzt == bild else 0
            bild = jetzt
            if gleich >= 4 and time.time() - neu_gestartet > 60:
                print("[Overlay] Webcam haengt (Bild unveraendert) - starte sie neu")
                try:
                    stream.kamera_neu_starten()
                except RuntimeError:
                    pass
                neu_gestartet, gleich = time.time(), 0
        in_pause = szene == stream.PAUSE_SZENE
        if in_pause != bool(_zustand["pause"].get("an")):
            senden("pause", {"an": True, "bis": None} if in_pause else {"an": False})


def in_obs_einrichten() -> str:
    """Legt die Browserquelle "Klaus Overlay" in allen OBS-Szenen an (einmalig, ueber obs-websocket)."""
    import stream

    a = stream.obs_anfrage
    szenen = [s["sceneName"] for s in a("GetSceneList").get("scenes", [])]
    if not szenen:
        return "In OBS gibt es keine Szenen."
    vorhanden = {i["inputName"] for i in a("GetInputList").get("inputs", [])}
    if "Klaus Overlay" not in vorhanden:
        a("CreateInput", {"sceneName": szenen[0], "inputName": "Klaus Overlay", "inputKind": "browser_source",
                          "inputSettings": {"url": URL, "width": 1920, "height": 1080, "fps": 30, "fps_custom": True,
                                            "reroute_audio": False, "shutdown": False}})
    for szene in szenen:
        elemente = a("GetSceneItemList", {"sceneName": szene}).get("sceneItems", [])
        if "Klaus Overlay" not in [i["sourceName"] for i in elemente]:
            a("CreateSceneItem", {"sceneName": szene, "sourceName": "Klaus Overlay"})
            elemente = a("GetSceneItemList", {"sceneName": szene}).get("sceneItems", [])
        eintrag = next(i for i in elemente if i["sourceName"] == "Klaus Overlay")
        a("SetSceneItemIndex", {"sceneName": szene, "sceneItemId": eintrag["sceneItemId"],   # ganz nach oben, sonst
                                "sceneItemIndex": len(elemente) - 1})                        # verdeckt ihn das Spiel
    return f"Klaus-Overlay ist in {len(szenen)} Szenen ({', '.join(szenen)})."
