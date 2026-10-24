"""
Klaus - Tester-Profile auf Nikolas Server: ein gemeinsamer Tester-Bot, fuer jeden Tester ein eigener Klaus.

Laeuft als systemd-Dienst `klaus-profile` (server/klaus-profile.service) neben Nikolas `klaus-gehirn`.
    - liest den Tester-Bot (TESTER_BOT_TOKEN in Nikolas .env) per getUpdates
    - Tester mit Einladungscode (/start <code>, Code von Nikola per /einladen) bekommt ein Profil:
      ~/profile/<telegram-id>/  mit eigener .env (eigene Schluessel), eigenem data/ und eigener Claude-Anmeldung (HOME)
    - je Profil ein eigener Prozess (src/server_gehirn.py mit KLAUS_PROFIL=1); Nachrichten gehen als JSON-Zeilen ueber stdin
    - Code kommt aus Nikolas Installation (wird bei jedem Start ins Profil kopiert, neuer Git-Stand -> Profile neu starten)
Trennung: eigene Prozesse, Ordner, Schluessel und Telegram-Konten. Noch derselbe Unix-Benutzer (Testphase).
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

ORDNER = Path(os.getenv("KLAUS_PROFILE_ORDNER", "").strip() or Path.home() / "profile")
EINLADUNGEN = ORDNER / "einladungen.json"
REGISTER = ORDNER / "profile.json"
CODE_GUELTIG_S = 7 * 24 * 3600
MAX_PROFILE = int(os.getenv("KLAUS_MAX_PROFILE", "10"))
_sperre = threading.Lock()


def token() -> str:
    return os.getenv("TESTER_BOT_TOKEN", "").strip()


def _api(methode: str, frist: float = 30, **daten):
    r = requests.post(f"https://api.telegram.org/bot{token()}/{methode}", json=daten, timeout=frist)
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"Telegram {methode}: {j.get('description', r.status_code)}")
    return j["result"]


def _lesen(datei: Path) -> dict:
    try:
        return json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _schreiben(datei: Path, d: dict) -> None:
    datei.parent.mkdir(parents=True, exist_ok=True)
    tmp = datei.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(datei)


# ------------------------------------------------------------------ Verwaltung (Nikolas Befehle im Haupt-Klaus)
def einladen(name: str = "") -> str:
    """/einladen [Name] -> Einladungslink fuer einen Tester (7 Tage gueltig, einmal benutzbar)."""
    if not token():
        return "Für Tester fehlt TESTER_BOT_TOKEN in der .env des Servers (neuen Bot bei @BotFather anlegen)."
    with _sperre:
        if len(_lesen(REGISTER)) >= MAX_PROFILE:
            return f"Es gibt schon {MAX_PROFILE} Tester-Profile (KLAUS_MAX_PROFILE)."
        d = _lesen(EINLADUNGEN)
        jetzt = time.time()
        d = {c: e for c, e in d.items() if jetzt - e.get("erstellt", 0) < CODE_GUELTIG_S}
        code = secrets.token_urlsafe(9).replace("-", "x").replace("_", "y")
        d[code] = {"erstellt": jetzt, "name": name.strip()[:40]}
        _schreiben(EINLADUNGEN, d)
    try:
        bot = _api("getMe")["username"]
        link = f"https://t.me/{bot}?start={code}"
    except Exception:
        link = f"/start {code}"
    return (f"🎟 Einladung{' für ' + name.strip() if name.strip() else ''} (7 Tage, einmalig):\n{link}\n"
            "Der Tester öffnet den Link, wählt eine PIN und trägt dann seine eigenen Schlüssel ein (/schluessel).")


def liste() -> str:
    r = _lesen(REGISTER)
    if not r:
        return "Noch keine Tester. Einladen mit /einladen <Name>."
    zeilen = ["👥 Tester-Profile:"]
    for uid, p in r.items():
        zeilen.append(f"• {p.get('name') or 'ohne Namen'} (ID {uid}) seit {p.get('seit', '?')}")
    return "\n".join(zeilen) + "\nEntfernen: /tester_entfernen <ID>"


def entfernen(uid: str) -> str:
    uid = uid.strip()
    with _sperre:
        r = _lesen(REGISTER)
        if uid not in r:
            return f"Kein Tester mit der ID {uid}."
        r.pop(uid)
        _schreiben(REGISTER, r)
    # Prozess beendet der Verteiler beim naechsten Abgleich; Ordner bleibt (Daten nicht still loeschen)
    return f"Tester {uid} ist gesperrt. Sein Ordner {ORDNER / uid} bleibt erhalten, bis du ihn löschst."


# ------------------------------------------------------------------ Profile
def profil_ordner(uid: int | str) -> Path:
    return ORDNER / str(int(uid))


def code_synchronisieren(ziel: Path) -> None:
    """Nikolas aktuellen Code ins Profil kopieren (nur src/ und VERSION - nie .env oder data/)."""
    if (ziel / "src").exists():
        shutil.rmtree(ziel / "src")
    shutil.copytree(BASE_DIR / "src", ziel / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if (BASE_DIR / "VERSION").exists():
        shutil.copy2(BASE_DIR / "VERSION", ziel / "VERSION")


def profil_anlegen(uid: int, vorname: str) -> Path:
    p = profil_ordner(uid)
    (p / "data").mkdir(parents=True, exist_ok=True)
    os.chmod(p, 0o700)
    env = p / ".env"
    if not env.exists():
        name = re.sub(r"[\r\n=]", "", vorname)[:40]
        env.write_text("\n".join([
            "# Klaus-Tester-Profil (vom Verteiler angelegt). Schluessel per Telegram: /schluessel <anbieter> <schluessel>",
            f"TELEGRAM_TOKEN={token()}", f"TELEGRAM_NUTZER={int(uid)}", "TELEGRAM_PIN=",
            "KLAUS_PROFIL=1", "KLAUS_NAME=Klaus", f"KLAUS_NUTZER={name}",
            "KLAUS_PC_PORT=9", "KLAUS_SERVER_PORT=9", "",
        ]), encoding="utf-8")
        os.chmod(env, 0o600)
    return p


class Arbeiter:
    """Ein Prozess je Profil. Nachrichten (Telegram-Updates) als JSON-Zeilen ueber stdin."""

    def __init__(self, uid: int) -> None:
        self.uid = uid
        self.ordner = profil_ordner(uid)
        self.proc: subprocess.Popen | None = None
        self.starts: list[float] = []

    def laeuft(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def umgebung(self) -> dict:
        """Nur das Noetigste - keine Schluessel aus Nikolas .env (die liest das Profil aus seiner eigenen .env)."""
        # Programme (claude) aus Nikolas ~/.local/bin finden - die Anmeldung liegt aber im eigenen HOME des Profils
        pfad = os.pathsep.join([str(Path.home() / ".local" / "bin"), os.environ.get("PATH", "/usr/bin:/bin")])
        import site

        return {"PATH": pfad, "HOME": str(self.ordner), "LANG": "C.UTF-8", "PYTHONUSERBASE": site.getuserbase(),   # Pakete bleiben sichtbar
                "TZ": os.environ.get("TZ", "Europe/Berlin"), "PYTHONUNBUFFERED": "1", "KLAUS_PROFIL": "1"}

    def starten(self) -> None:
        jetzt = time.time()
        self.starts = [t for t in self.starts if jetzt - t < 600] + [jetzt]
        if len(self.starts) > 5:   # stuerzt dauernd ab -> nicht im Kreis starten
            raise RuntimeError(f"Profil {self.uid} startet staendig neu - pausiert (Log: {self.ordner / 'data' / 'klaus.log'})")
        code_synchronisieren(self.ordner)
        log = open(self.ordner / "data" / "klaus.log", "ab")
        self.proc = subprocess.Popen([sys.executable, "-u", str(self.ordner / "src" / "server_gehirn.py")], cwd=self.ordner,
                                     env=self.umgebung(), stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT)
        print(f"[Profile] {self.uid} gestartet (PID {self.proc.pid})", flush=True)

    def senden(self, update: dict) -> None:
        if not self.laeuft():
            self.starten()
        try:
            self.proc.stdin.write((json.dumps(update) + "\n").encode())
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            self.starten()
            self.proc.stdin.write((json.dumps(update) + "\n").encode())
            self.proc.stdin.flush()

    def stoppen(self) -> None:
        if self.laeuft():
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class Verteiler:
    def __init__(self) -> None:
        self.arbeiter: dict[int, Arbeiter] = {}
        self.offset = 0
        self.stand = ""

    @staticmethod
    def _absender(u: dict) -> tuple[int | None, dict | None]:
        if "callback_query" in u:
            return u["callback_query"]["from"]["id"], None
        n = u.get("message")
        if not n or n.get("chat", {}).get("type") != "private":
            return None, None
        return n["from"]["id"], n

    def update(self, u: dict) -> None:
        uid, n = self._absender(u)
        if uid is None:
            return
        if str(uid) in _lesen(REGISTER):
            self.arbeiter.setdefault(uid, Arbeiter(uid)).senden(u)
            return
        text = (n or {}).get("text") or ""
        if n and text.startswith("/start"):
            self.einloesen(n, text)
        elif n:
            _api("sendMessage", chat_id=uid, text="Hallo! Dieser Klaus ist gerade nur für eingeladene Tester. "
                                                  "Frag Nikola nach einem Einladungslink.")

    def einloesen(self, n: dict, text: str) -> None:
        uid = int(n["from"]["id"])
        teile = text.split()
        with _sperre:
            d = _lesen(EINLADUNGEN)
            code = teile[1] if len(teile) > 1 else ""
            e = d.get(code)
            if not e or time.time() - e.get("erstellt", 0) > CODE_GUELTIG_S:
                gueltig = False
            else:
                gueltig = True
                d.pop(code)
                _schreiben(EINLADUNGEN, d)
                r = _lesen(REGISTER)
                r[str(uid)] = {"name": e.get("name") or n["from"].get("first_name", ""), "seit": time.strftime("%d.%m.%Y")}
                _schreiben(REGISTER, r)
        if not gueltig:
            _api("sendMessage", chat_id=uid, text="Der Einladungscode ist ungültig oder abgelaufen. Frag Nikola nach einem neuen.")
            print(f"[Profile] ungueltiger Code von {uid}", flush=True)
            return
        profil_anlegen(uid, n["from"].get("first_name", ""))
        self.arbeiter.setdefault(uid, Arbeiter(uid)).starten()
        _api("sendMessage", chat_id=uid, text=(
            f"Hallo {n['from'].get('first_name', '')}! 👋 Dein eigener Klaus ist eingerichtet – mit eigenem Gedächtnis, eigenen "
            "Einstellungen und deinen eigenen Schlüsseln.\n\n1. Wähl jetzt eine PIN (4–8 Ziffern) für Freigaben und schick sie mir.\n"
            "2. Dann deine KI-Schlüssel, je eine Nachricht (ich lösche sie sofort):\n"
            "/schluessel gemini <Schlüssel>  (kostenlos: aistudio.google.com/apikey)\n"
            "/schluessel groq <Schlüssel>  (kostenlos: console.groq.com/keys)\n"
            "Optional: openrouter, fish, anthropic (für Claude), alpaca mit /alpaca_schluessel.\n"
            "/profil zeigt, was eingerichtet ist."))

    def abgleich(self) -> None:
        """Gesperrte Profile beenden; neuer Code-Stand bei Nikola -> Profile neu starten (holen den neuen Code)."""
        r = _lesen(REGISTER)
        for uid in [u for u in self.arbeiter if str(u) not in r]:
            self.arbeiter.pop(uid).stoppen()
        try:
            stand = subprocess.run(["git", "rev-parse", "HEAD"], cwd=BASE_DIR, capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            stand = ""
        if stand and self.stand and stand != self.stand:
            print(f"[Profile] neuer Code-Stand {stand[:7]} - starte Profile neu", flush=True)
            for a in self.arbeiter.values():
                a.stoppen()
        self.stand = stand or self.stand

    def run(self) -> None:
        if not token():
            sys.exit("TESTER_BOT_TOKEN fehlt in der .env")
        ORDNER.mkdir(parents=True, exist_ok=True)
        os.chmod(ORDNER, 0o700)
        print(f"[Profile] Verteiler laeuft ({len(_lesen(REGISTER))} Profile)", flush=True)
        naechster_abgleich = 0.0
        while True:
            try:
                if time.time() > naechster_abgleich:
                    self.abgleich()
                    naechster_abgleich = time.time() + 300
                for u in _api("getUpdates", frist=60, offset=self.offset, timeout=50):
                    self.offset = u["update_id"] + 1
                    try:
                        self.update(u)
                    except Exception as e:
                        print(f"[Profile] Update: {str(e)[:150]}", flush=True)
            except Exception as e:
                print(f"[Profile] {str(e)[:150]}", flush=True)
                time.sleep(10)


if __name__ == "__main__":
    Verteiler().run()
