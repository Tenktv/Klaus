"""
Klaus-Server - nimmt Fehlerberichte von Tester-PCs an und schickt sie Nikola per Telegram.

    Tester-PC (fehlerbericht.py)  --POST /bericht, Kopf X-Melde-Code-->  Server :7720  --Telegram-->  Nikola

Melde-Codes (in Telegram, nur Nikola):
    /melde_code Tim        neuen Code fuer Tim anlegen (wird einmal angezeigt, kommt beim Tester in die .env)
    /melde_codes           wer hat einen Code, wie viele Berichte
    /melde_code_weg Tim    Code sperren

Sicherheit: Ein Melde-Code kann NUR Berichte schicken (nichts lesen, nichts ausfuehren). Gespeichert wird nur sein
SHA-256. Pro Code hoechstens 1 Bericht pro Minute und 20 am Tag, insgesamt 100 am Tag, je Bericht max. 64 KB.
Unbekannte Codes bekommen 403 und erzeugen keine Telegram-Nachricht. Berichte enthalten das (schon geschwaerzte)
Klaus-Log - keine Schluessel. Die Verbindung ist HTTP ohne TLS (der Server hat keine Domain): Lauscher im Netz koennten
einen Bericht mitlesen, aber nichts damit tun.

Einmal auf dem Server: Port freigeben  ->  sudo ufw allow 7720/tcp
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

BASE_DIR = Path(__file__).resolve().parent.parent
CODES = BASE_DIR / "data" / "melde_codes.json"
PORT = int(os.getenv("FEHLERBERICHT_PORT", "7720") or 7720)
MAX_BYTES = 64 * 1024
PRO_CODE_MINUTE, PRO_CODE_TAG, GESAMT_TAG = 1, 20, 100

_sperre = threading.Lock()
_zaehler: dict = {"tag": "", "gesamt": 0, "codes": {}}   # code_hash -> [zeitpunkte heute]


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().encode()).hexdigest()


def _laden() -> dict:
    try:
        return json.loads(CODES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _speichern(d: dict) -> None:
    CODES.parent.mkdir(parents=True, exist_ok=True)
    CODES.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        os.chmod(CODES, 0o600)
    except OSError:
        pass


def code_anlegen(name: str) -> str:
    name = re.sub(r"[^\wÄÖÜäöüß .-]", "", name).strip()[:30]
    if not name:
        raise ValueError("Bitte einen Namen angeben: /melde_code Tim")
    code = "km_" + secrets.token_urlsafe(18)
    with _sperre:
        d = {h: v for h, v in _laden().items() if v.get("name", "").lower() != name.lower()}   # alter Code ist ungueltig
        d[_hash(code)] = {"name": name, "erstellt": time.strftime("%Y-%m-%d"), "berichte": 0}
        _speichern(d)
    return code


def code_weg(name: str) -> bool:
    with _sperre:
        d = _laden()
        neu = {h: v for h, v in d.items() if v.get("name", "").lower() != name.strip().lower()}
        if len(neu) == len(d):
            return False
        _speichern(neu)
    return True


def pruefen(code: str) -> tuple[int, str, str]:
    """-> (HTTP-Status, Fehlertext, Name des Testers). Zaehlt den Bericht, wenn er durchgeht."""
    h = _hash(code or "")
    eintrag = _laden().get(h) if code else None
    if not eintrag:
        return 403, "Melde-Code unbekannt", ""
    jetzt = time.time()
    with _sperre:
        tag = time.strftime("%Y-%m-%d")
        if _zaehler["tag"] != tag:
            _zaehler.update(tag=tag, gesamt=0, codes={})
        liste = _zaehler["codes"].setdefault(h, [])
        if _zaehler["gesamt"] >= GESAMT_TAG or len(liste) >= PRO_CODE_TAG:
            return 429, "Heute schon genug Berichte", eintrag["name"]
        if liste and jetzt - liste[-1] < 60 / PRO_CODE_MINUTE:
            return 429, "Bitte eine Minute warten", eintrag["name"]
        liste.append(jetzt)
        _zaehler["gesamt"] += 1
    return 200, "", eintrag["name"]


def _zaehle(name: str) -> None:
    with _sperre:
        d = _laden()
        for v in d.values():
            if v.get("name") == name:
                v["berichte"] = int(v.get("berichte", 0)) + 1
                v["zuletzt"] = time.strftime("%Y-%m-%d %H:%M")
        _speichern(d)


def weiterleiten(name: str, daten: dict, senden: Callable[[str], object], datei: Callable[[bytes, str, str], object]) -> None:
    kurz = str(daten.get("kurz") or "")[:600]
    anlass = str(daten.get("anlass") or "Bericht")[:120]
    text = str(daten.get("text") or "")
    senden(f"🧯 Fehlerbericht von {name}\nAnlass: {anlass}\n\n{kurz}"[:3900])
    if text:
        datei(text.encode("utf-8", "replace"), f"fehlerbericht-{re.sub(r'[^A-Za-z0-9]', '', name) or 'tester'}-"
                                                f"{time.strftime('%Y%m%d-%H%M')}.txt", f"Ganzer Bericht von {name}")
    _zaehle(name)


class _Empfang(BaseHTTPRequestHandler):
    senden: Callable = print
    datei: Callable = lambda *a: None
    timeout = 15
    server_version = "Klaus"
    sys_version = ""

    def log_message(self, *args) -> None:   # kein Zugriffslog voller fremder Adressen
        pass

    def _antwort(self, status: int, text: str) -> None:
        roh = json.dumps({"ok": status == 200, "text": text}, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(roh)))
        self.end_headers()
        self.wfile.write(roh)

    def do_GET(self) -> None:
        self._antwort(404, "")

    def do_POST(self) -> None:
        if self.path != "/bericht":
            return self._antwort(404, "")
        try:
            laenge = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            laenge = 0
        if not 0 < laenge <= MAX_BYTES:
            return self._antwort(413, "Bericht zu gross")
        status, fehler, name = pruefen(self.headers.get("X-Melde-Code", ""))
        if status != 200:
            return self._antwort(status, fehler)
        try:
            daten = json.loads(self.rfile.read(laenge).decode("utf-8", "replace"))
            if not isinstance(daten, dict):
                raise ValueError
        except ValueError:
            return self._antwort(400, "Kein gueltiger Bericht")
        threading.Thread(target=weiterleiten, args=(name, daten, type(self).senden, type(self).datei), daemon=True).start()
        self._antwort(200, "Bericht ist angekommen.")


def starten(senden: Callable[[str], object], datei: Callable[[bytes, str, str], object]) -> ThreadingHTTPServer | None:
    _Empfang.senden = staticmethod(senden)
    _Empfang.datei = staticmethod(datei)
    try:
        server = ThreadingHTTPServer(("0.0.0.0", PORT), _Empfang)
    except OSError as e:
        print(f"[Fehlerberichte] Port {PORT} nicht frei: {e}", flush=True)
        return None
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name="fehlerberichte").start()
    print(f"[Fehlerberichte] Empfang auf Port {PORT}", flush=True)
    return server


def befehle_einrichten(tg) -> None:
    """Telegram-Befehle fuer Nikola (nur im Haupt-Prozess, nie in Tester-Profilen)."""
    def anlegen(text: str) -> str:
        teile = text.split(maxsplit=1)
        try:
            code = code_anlegen(teile[1] if len(teile) > 1 else "")
        except ValueError as e:
            return str(e)
        return (f"Melde-Code für {teile[1].strip()}:\n\n{code}\n\nBeim Tester in die .env (Startmenü → Klaus → Einstellungen):\n"
                f"KLAUS_MELDE_CODE={code}\n\nDanach Klaus neu starten. Fehler kommen dann automatisch hier an. "
                "Ein neuer Code für denselben Namen macht den alten ungültig.\n"
                f"Einmalig auf dem Server nötig: sudo ufw allow {PORT}/tcp")

    def liste(_t: str) -> str:
        d = _laden()
        if not d:
            return "Noch keine Melde-Codes. Neuer Code: /melde_code Tim"
        return "Melde-Codes:\n" + "\n".join(f"• {v['name']} (seit {v.get('erstellt', '?')}, {v.get('berichte', 0)} Berichte"
                                            + (f", zuletzt {v['zuletzt']}" if v.get("zuletzt") else "") + ")"
                                            for v in d.values())

    def weg(text: str) -> str:
        teile = text.split(maxsplit=1)
        if len(teile) < 2:
            return "Wessen Code? /melde_code_weg Tim"
        return f"Code von {teile[1].strip()} ist gesperrt." if code_weg(teile[1]) else f"{teile[1].strip()} hat keinen Code."

    tg.befehle["/melde_code"] = anlegen
    tg.befehle["/melde_codes"] = liste
    tg.befehle["/melde_code_weg"] = weg
