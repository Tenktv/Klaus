"""
Klaus - Tester-Profile auf Nikolas Server: ein gemeinsamer Tester-Bot, fuer jedes Profil ein eigener Klaus.

Laeuft als systemd-Dienst `klaus-profile` (server/klaus-profile.service) neben Nikolas `klaus-gehirn`.
    - liest den Tester-Bot (TESTER_BOT_TOKEN in Nikolas .env) per getUpdates
    - neues Profil nur mit Einladung (Nikola: /einladen) -> der Tester waehlt Profilname + Passwort
    - Anmelden mit /login <profil> <passwort> (auch von einem anderen Telegram-Konto), /logout, /passwort <alt> <neu>
      Passwoerter nur als scrypt-Hash; Nachrichten mit Passwort werden sofort geloescht; 5 Fehlversuche -> 15 min Sperre
    - je Profil ~/profile/<name>/ mit eigener .env (eigene Schluessel), data/ und HOME (Claude-Anmeldung) und ein eigener
      Prozess (src/server_gehirn.py, KLAUS_PROFIL=1); Nachrichten als JSON-Zeilen ueber stdin; geantwortet wird an das
      Telegram-Konto, das gerade angemeldet ist (TELEGRAM_NUTZER in der Profil-.env)
    - Code aus Nikolas Installation (bei jedem Start kopiert; neuer Git-Stand -> Profile neu starten)
Trennung: eigene Prozesse, Ordner, Schluessel. Noch derselbe Unix-Benutzer (Testphase).
"""
from __future__ import annotations

import hashlib
import hmac
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

import whatsapp_kunden

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

ORDNER = Path(os.getenv("KLAUS_PROFILE_ORDNER", "").strip() or Path.home() / "profile")
EINLADUNGEN = ORDNER / "einladungen.json"
REGISTER = ORDNER / "profile.json"
CODE_GUELTIG_S = 7 * 24 * 3600
MAX_PROFILE = int(os.getenv("KLAUS_MAX_PROFILE", "10"))
MAX_FEHLVERSUCHE, SPERRE_S = 5, 15 * 60
NAME_MUSTER = re.compile(r"[a-z0-9_]{3,20}")
_sperre = threading.Lock()


def token() -> str:
    return os.getenv("TESTER_BOT_TOKEN", "").strip()


def _api(methode: str, frist: float = 30, **daten):
    r = requests.post(f"https://api.telegram.org/bot{token()}/{methode}", json=daten, timeout=frist)
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"Telegram {methode}: {j.get('description', r.status_code)}")
    return j["result"]


def _senden(chat: int, text: str) -> None:
    try:
        _api("sendMessage", chat_id=chat, text=text)
    except Exception as e:
        print(f"[Profile] senden: {str(e)[:100]}", flush=True)


def _loeschen(n: dict) -> None:
    try:
        _api("deleteMessage", chat_id=n["chat"]["id"], message_id=n["message_id"])
    except Exception:
        pass


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


# ------------------------------------------------------------------ Passwoerter
def _hash(passwort: str, salz: str) -> str:
    return hashlib.scrypt(passwort.encode(), salt=bytes.fromhex(salz), n=2 ** 14, r=8, p=1).hex()


def passwort_setzen(eintrag: dict, passwort: str) -> None:
    eintrag["salz"] = secrets.token_hex(16)
    eintrag["hash"] = _hash(passwort, eintrag["salz"])


def passwort_ok(eintrag: dict, passwort: str) -> bool:
    return bool(eintrag.get("hash")) and hmac.compare_digest(_hash(passwort, eintrag["salz"]), eintrag["hash"])


def passwort_fehler(passwort: str) -> str:
    if len(passwort) < 8:
        return "Das Passwort braucht mindestens 8 Zeichen."
    if passwort.isdigit() or passwort.lower() == passwort and passwort.isalpha():
        return "Bitte ein stärkeres Passwort (z. B. mit Zahlen und Großbuchstaben)."
    return ""


# ------------------------------------------------------------------ Verwaltung (Nikolas Befehle im Haupt-Klaus)
def einladen(name: str = "") -> str:
    """/einladen [Name] -> Einladungslink (7 Tage gueltig, einmal benutzbar)."""
    if not token():
        return "Für Tester fehlt TESTER_BOT_TOKEN in der .env des Servers (neuen Bot bei @BotFather anlegen)."
    with _sperre:
        if len(_lesen(REGISTER)) >= MAX_PROFILE:
            return f"Es gibt schon {MAX_PROFILE} Tester-Profile (KLAUS_MAX_PROFILE)."
        d = {c: e for c, e in _lesen(EINLADUNGEN).items() if time.time() - e.get("erstellt", 0) < CODE_GUELTIG_S}
        code = secrets.token_urlsafe(9).replace("-", "x").replace("_", "y")
        d[code] = {"erstellt": time.time(), "name": name.strip()[:40]}
        _schreiben(EINLADUNGEN, d)
    try:
        link = f"https://t.me/{_api('getMe')['username']}?start={code}"
    except Exception:
        link = f"/start {code}"
    return (f"🎟 Einladung{' für ' + name.strip() if name.strip() else ''} (7 Tage, einmalig):\n{link}\n"
            "Der Tester wählt dort einen Profilnamen und ein Passwort und trägt dann seine eigenen Schlüssel ein.")


def liste() -> str:
    r = _lesen(REGISTER)
    if not r:
        return "Noch keine Tester. Einladen mit /einladen <Name>."
    zeilen = ["👥 Tester-Profile:"]
    for name, p in r.items():
        zeilen.append(f"• {name} ({p.get('anzeige') or '–'}) seit {p.get('seit', '?')} · "
                      f"{'angemeldet' if p.get('telegram') else 'abgemeldet'}")
    return "\n".join(zeilen) + "\nSperren: /tester_entfernen <profil>"


def entfernen(name: str) -> str:
    name = name.strip().lower()
    with _sperre:
        r = _lesen(REGISTER)
        if name not in r:
            return f"Kein Tester-Profil „{name}“."
        r.pop(name)
        _schreiben(REGISTER, r)
    return f"Profil „{name}“ ist gesperrt. Der Ordner {ORDNER / name} bleibt erhalten, bis du ihn löschst."


# ------------------------------------------------------------------ Profile
def profil_ordner(name: str) -> Path:
    if not NAME_MUSTER.fullmatch(name):
        raise ValueError(f"ungueltiger Profilname: {name!r}")
    return ORDNER / name


def code_synchronisieren(ziel: Path) -> None:
    """Nikolas aktuellen Code ins Profil kopieren (nur src/ und VERSION - nie .env oder data/)."""
    if (ziel / "src").exists():
        shutil.rmtree(ziel / "src")
    shutil.copytree(BASE_DIR / "src", ziel / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if (BASE_DIR / "VERSION").exists():
        shutil.copy2(BASE_DIR / "VERSION", ziel / "VERSION")


def env_setzen(datei: Path, schluessel: str, wert: str) -> None:
    zeilen = datei.read_text(encoding="utf-8").splitlines() if datei.exists() else []
    neu = [f"{schluessel}={wert}" if z.startswith(f"{schluessel}=") else z for z in zeilen]
    if f"{schluessel}={wert}" not in neu:
        neu.append(f"{schluessel}={wert}")
    datei.write_text("\n".join(neu) + "\n", encoding="utf-8")
    os.chmod(datei, 0o600)


def profil_anlegen(name: str, telegram: int, anzeige: str) -> Path:
    p = profil_ordner(name)
    (p / "data").mkdir(parents=True, exist_ok=True)
    os.chmod(p, 0o700)
    env = p / ".env"
    if not env.exists():
        env.write_text("\n".join([
            "# Klaus-Tester-Profil (vom Verteiler angelegt). Schluessel per Telegram: /schluessel <anbieter> <schluessel>",
            f"TELEGRAM_TOKEN={token()}", f"TELEGRAM_NUTZER={int(telegram)}", "TELEGRAM_PIN=",
            "KLAUS_PROFIL=1", "KLAUS_NAME=Klaus", f"KLAUS_NUTZER={re.sub(r'[^0-9A-Za-zÄÖÜäöüß -]', '', anzeige)[:40]}",
            "KLAUS_PC_PORT=9", "KLAUS_SERVER_PORT=9", "",
        ]), encoding="utf-8")
        os.chmod(env, 0o600)
    return p


class Arbeiter:
    """Ein Prozess je Profil. Nachrichten (Telegram-Updates) als JSON-Zeilen ueber stdin."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.ordner = profil_ordner(name)
        self.proc: subprocess.Popen | None = None
        self.starts: list[float] = []

    def laeuft(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def umgebung(self) -> dict:
        """Nur das Noetigste - keine Schluessel aus Nikolas .env (die liest das Profil aus seiner eigenen .env)."""
        import site

        # Programme (claude) aus Nikolas ~/.local/bin finden - die Anmeldung liegt aber im eigenen HOME des Profils
        pfad = os.pathsep.join([str(Path.home() / ".local" / "bin"), os.environ.get("PATH", "/usr/bin:/bin")])
        return {"PATH": pfad, "HOME": str(self.ordner), "LANG": "C.UTF-8", "PYTHONUSERBASE": site.getuserbase(),
                "TZ": os.environ.get("TZ", "Europe/Berlin"), "PYTHONUNBUFFERED": "1", "KLAUS_PROFIL": "1"}

    def starten(self) -> None:
        self.stoppen()
        jetzt = time.time()
        self.starts = [t for t in self.starts if jetzt - t < 600] + [jetzt]
        if len(self.starts) > 5:   # stuerzt dauernd ab -> nicht im Kreis starten
            raise RuntimeError(f"Profil {self.name} startet staendig neu - pausiert (Log: {self.ordner / 'data' / 'klaus.log'})")
        code_synchronisieren(self.ordner)
        log = open(self.ordner / "data" / "klaus.log", "ab")
        self.proc = subprocess.Popen([sys.executable, "-u", str(self.ordner / "src" / "server_gehirn.py")], cwd=self.ordner,
                                     env=self.umgebung(), stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT)
        print(f"[Profile] {self.name} gestartet (PID {self.proc.pid})", flush=True)

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
        self.arbeiter: dict[str, Arbeiter] = {}
        self.offset = 0
        self.stand = ""
        self.wartet: dict[int, str] = {}                 # Telegram-ID -> eingeloester Code (waehlt Profilname + Passwort)
        self.fehler: dict[str, list[float]] = {}         # Telegram-ID bzw. Profil -> Zeitpunkte falscher Passwoerter

    # ---------------------------------------------------------------- Hilfen
    @staticmethod
    def angemeldet(telegram: int) -> str | None:
        return next((n for n, p in _lesen(REGISTER).items() if p.get("telegram") == telegram), None)

    def _gesperrt(self, *schluessel: str) -> bool:
        jetzt = time.time()
        for s in schluessel:
            self.fehler[s] = [t for t in self.fehler.get(s, []) if jetzt - t < SPERRE_S]
            if len(self.fehler[s]) >= MAX_FEHLVERSUCHE:
                return True
        return False

    def _fehlversuch(self, *schluessel: str) -> None:
        for s in schluessel:
            self.fehler.setdefault(s, []).append(time.time())

    def arbeiter_fuer(self, name: str) -> Arbeiter:
        return self.arbeiter.setdefault(name, Arbeiter(name))

    def binden(self, name: str, telegram: int | None) -> None:
        """Profil an ein Telegram-Konto haengen (oder loesen) - der Profil-Klaus antwortet dorthin."""
        with _sperre:
            r = _lesen(REGISTER)
            for p in r.values():   # ein Telegram-Konto immer nur in einem Profil
                if telegram is not None and p.get("telegram") == telegram:
                    p["telegram"] = None
            r[name]["telegram"] = telegram
            _schreiben(REGISTER, r)
        env_setzen(profil_ordner(name) / ".env", "TELEGRAM_NUTZER", str(telegram or 0))
        a = self.arbeiter_fuer(name)
        a.starts = []    # gewollter Neustart zaehlt nicht als Absturz
        a.starten()      # neu starten, damit das Profil an das neue Konto schreibt

    # ---------------------------------------------------------------- Nachrichten
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
        text = ((n or {}).get("text") or "").strip()
        befehl = text.split()[0].lower() if text.startswith("/") else ""
        if n and uid in self.wartet and not befehl:
            return self.profil_waehlen(n, text)
        if befehl == "/start" and len(text.split()) > 1:
            return self.einloesen(n, text)
        if befehl == "/login":
            return self.login(n, text)
        name = self.angemeldet(uid)
        if befehl == "/logout" and name:
            self.binden(name, None)
            return _senden(uid, f"Abgemeldet von „{name}“. Dein Klaus läuft weiter (Strategien, Alarme), schreibt dir aber "
                                "nicht mehr. Wieder anmelden: /login <profil> <passwort>")
        if befehl == "/passwort" and name:
            return self.passwort_aendern(n, name, text)
        if name:
            if whatsapp_kunden.telegram_update(u, "tester"):   # WhatsApp-Knoepfe/Befehle des Inhabers (/unterricht, Senden ...)
                return
            return self.arbeiter_fuer(name).senden(u)
        if n:
            _senden(uid, "Hallo! Bitte melde dich an: /login <profil> <passwort>\n"
                         "Noch kein Profil? Dann brauchst du einen Einladungslink von Nikola.")

    def einloesen(self, n: dict, text: str) -> None:
        uid = int(n["from"]["id"])
        code = text.split()[1]
        e = _lesen(EINLADUNGEN).get(code)
        if not e or time.time() - e.get("erstellt", 0) > CODE_GUELTIG_S:
            print(f"[Profile] ungueltiger Code von {uid}", flush=True)
            return _senden(uid, "Der Einladungscode ist ungültig oder abgelaufen. Frag Nikola nach einem neuen.")
        self.wartet[uid] = code
        _senden(uid, "Willkommen! 👋 Wähl jetzt deinen Profilnamen und ein Passwort – in EINER Nachricht, z. B.:\n"
                     "tim MeinPasswort7\n\nProfilname: 3–20 Zeichen (a–z, 0–9, _). Passwort: mindestens 8 Zeichen. "
                     "Ich lösche die Nachricht sofort. Damit meldest du dich später an: /login <profil> <passwort>")

    def profil_waehlen(self, n: dict, text: str) -> None:
        uid = int(n["from"]["id"])
        _loeschen(n)
        teile = text.split()
        if len(teile) != 2:
            return _senden(uid, "Bitte so: <profilname> <passwort> (zwei Wörter, durch ein Leerzeichen getrennt).")
        name, passwort = teile[0].lower(), teile[1]
        if not NAME_MUSTER.fullmatch(name):
            return _senden(uid, "Der Profilname darf nur a–z, 0–9 und _ enthalten (3–20 Zeichen). Nochmal?")
        if (grund := passwort_fehler(passwort)):
            return _senden(uid, grund + " Nochmal?")
        with _sperre:
            d, r = _lesen(EINLADUNGEN), _lesen(REGISTER)
            code = self.wartet.get(uid)
            if code not in d:
                self.wartet.pop(uid, None)
                return _senden(uid, "Die Einladung wurde inzwischen schon benutzt oder ist abgelaufen.")
            if name in r:
                return _senden(uid, f"„{name}“ ist schon vergeben – nimm einen anderen Namen.")
            anzeige = d[code].get("name") or n["from"].get("first_name", "")
            d.pop(code)
            _schreiben(EINLADUNGEN, d)
            eintrag = {"anzeige": anzeige, "seit": time.strftime("%d.%m.%Y"), "telegram": None}
            passwort_setzen(eintrag, passwort)
            r[name] = eintrag
            _schreiben(REGISTER, r)
        self.wartet.pop(uid, None)
        profil_anlegen(name, uid, anzeige)
        self.binden(name, uid)
        _senden(uid, f"✅ Profil „{name}“ ist angelegt und du bist angemeldet – dein eigener Klaus mit eigenem Gedächtnis, "
                     "eigenen Einstellungen und deinen eigenen Schlüsseln.\n\n"
                     "1. Wähl eine PIN (4–8 Ziffern) für Freigaben und schick sie mir.\n"
                     "2. Dann deine KI-Schlüssel, je eine Nachricht (ich lösche sie sofort):\n"
                     "/schluessel gemini <Schlüssel>  (kostenlos: aistudio.google.com/apikey)\n"
                     "/schluessel groq <Schlüssel>  (kostenlos: console.groq.com/keys)\n"
                     "Optional: openrouter, fish, anthropic (Claude); Börse: /alpaca_schluessel.\n"
                     "/profil zeigt, was eingerichtet ist · /logout meldet dich ab.")

    def login(self, n: dict | None, text: str) -> None:
        if not n:
            return
        uid = int(n["from"]["id"])
        _loeschen(n)
        teile = text.split()
        if len(teile) != 3:
            return _senden(uid, "So: /login <profil> <passwort> (ich lösche die Nachricht sofort).")
        name, passwort = teile[1].lower(), teile[2]
        if self._gesperrt(str(uid), name):
            return _senden(uid, "Zu viele falsche Versuche – die Anmeldung ist 15 Minuten gesperrt.")
        p = _lesen(REGISTER).get(name)
        if not p or not passwort_ok(p, passwort):
            self._fehlversuch(str(uid), name)
            print(f"[Profile] falsches Passwort fuer {name!r} von {uid}", flush=True)
            return _senden(uid, "Profilname oder Passwort stimmt nicht.")
        vorher = p.get("telegram")
        self.binden(name, uid)
        if vorher and vorher != uid:
            _senden(vorher, f"🔐 Dein Profil „{name}“ wurde gerade auf einem anderen Telegram-Konto angemeldet. "
                            "Warst du das nicht? Melde dich an und ändere sofort das Passwort: /passwort <alt> <neu>")
        _senden(uid, f"✅ Angemeldet als „{name}“. Schreib einfach los.")

    def passwort_aendern(self, n: dict, name: str, text: str) -> None:
        uid = int(n["from"]["id"])
        _loeschen(n)
        teile = text.split()
        if len(teile) != 3:
            return _senden(uid, "So: /passwort <altes> <neues>")
        if self._gesperrt(str(uid), name):
            return _senden(uid, "Zu viele falsche Versuche – bitte 15 Minuten warten.")
        with _sperre:
            r = _lesen(REGISTER)
            if not passwort_ok(r[name], teile[1]):
                self._fehlversuch(str(uid), name)
                return _senden(uid, "Das alte Passwort stimmt nicht.")
            if (grund := passwort_fehler(teile[2])):
                return _senden(uid, grund)
            passwort_setzen(r[name], teile[2])
            _schreiben(REGISTER, r)
        _senden(uid, "🔑 Passwort geändert.")

    # ---------------------------------------------------------------- Betrieb
    def abgleich(self) -> None:
        """Gesperrte Profile beenden; neuer Code-Stand bei Nikola -> Profile neu starten (holen den neuen Code)."""
        r = _lesen(REGISTER)
        for name in [n for n in self.arbeiter if n not in r]:
            self.arbeiter.pop(name).stoppen()
        for name in r:   # alle Profile laufen (Strategien, Alarme), auch abgemeldete
            if name not in self.arbeiter or not self.arbeiter[name].laeuft():
                try:
                    self.arbeiter_fuer(name).starten()
                except Exception as e:
                    print(f"[Profile] {name}: {str(e)[:150]}", flush=True)
        try:
            stand = subprocess.run(["git", "rev-parse", "HEAD"], cwd=BASE_DIR, capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            stand = ""
        if stand and self.stand and stand != self.stand:
            print(f"[Profile] neuer Code-Stand {stand[:7]} - starte Profile neu", flush=True)
            for a in self.arbeiter.values():
                a.starten()
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
