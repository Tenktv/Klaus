"""
Kalorien-App - Server (nur Python-Standardbibliothek + SQLite). Laeuft allein, Klaus wird NICHT gebraucht.

    python -m kalorien.server            (aus dem Klaus-Ordner)   ->  http://127.0.0.1:7730

Die iPhone-App ist eine Web-App (PWA): in Safari die Adresse oeffnen -> Teilen -> "Zum Home-Bildschirm".
Kamera-Scanner braucht HTTPS (z.B. Caddy:  kalorien.deine-domain.de { reverse_proxy 127.0.0.1:7730 }).

Einstellungen (Umgebungsvariablen / .env):
    GEMINI_API_KEY        fuer Foto- und Text-Schaetzung (ohne Schluessel gehen Tagebuch, Barcode, Forum, Chat trotzdem)
    KALORIEN_PORT         Standard 7730
    KALORIEN_ADMINS       Namen mit Moderationsrechten, kommagetrennt
    KALORIEN_PROXY=1      Server steht hinter Caddy/nginx -> echte Adresse aus X-Forwarded-For (sonst NICHT setzen)
    KALORIEN_KI_PRO_TAG   KI-Schaetzungen pro Nutzer und Tag (Standard 30)
    KALORIEN_OFFEN=0      Registrierung schliessen (Standard 1)

Schnittstelle fuer Klaus, Telegram, Kurzbefehle: Zugangs-Schluessel ("kt_...") in der App unter Ich -> Schnittstelle
anlegen und als  Authorization: Bearer kt_...  mitschicken. Alles, was die App kann, geht auch darueber.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import secrets
import threading
import time
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import db, ki, nahrung

WEB = Path(__file__).resolve().parent / "web"
PORT = int(os.getenv("KALORIEN_PORT", "7730") or 7730)   # .env wird erst im Start geladen -> dort nochmal lesen
MAX_BODY = 4 * 1024 * 1024
MAHLZEITEN = ("fruehstueck", "mittag", "abend", "snack")
VERBOTEN = re.compile(r"(?i)\b(nazi|heil hitler|hurensohn|fotze|neger|kys|kill yourself|bring dich um)\b")
_sperre = threading.Lock()
_versuche: dict[str, list[float]] = {}


class Fehler(Exception):
    def __init__(self, status: int, text: str) -> None:
        super().__init__(text)
        self.status, self.text = status, text


def _admins() -> set[str]:
    return {a.strip().lower() for a in os.getenv("KALORIEN_ADMINS", "").split(",") if a.strip()}


def _bremse(schluessel: str, maximal: int, sekunden: int = 60) -> None:
    jetzt = time.time()
    with _sperre:
        liste = [t for t in _versuche.get(schluessel, []) if jetzt - t < sekunden]
        if len(liste) >= maximal:
            raise Fehler(429, "Zu viele Versuche. Bitte kurz warten.")
        liste.append(jetzt)
        _versuche[schluessel] = liste


def _text(w, name: str, minimal: int = 1, maximal: int = 2000) -> str:
    t = str(w or "").strip()
    if not minimal <= len(t) <= maximal:
        raise Fehler(400, f"{name}: {minimal}–{maximal} Zeichen.")
    if VERBOTEN.search(t):
        raise Fehler(400, "Dieser Text verstößt gegen die Regeln der Community.")
    return t


def _zahl(w, name: str, maximal: float) -> float:
    try:
        z = float(str(w).replace(",", "."))
    except (TypeError, ValueError):
        raise Fehler(400, f"{name} ist keine Zahl.")
    if not 0 <= z <= maximal:
        raise Fehler(400, f"{name} muss zwischen 0 und {maximal:g} liegen.")
    return round(z, 1)


def _datum(w) -> str:
    try:
        return datetime.strptime(str(w or date.today().isoformat()), "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise Fehler(400, "Datum bitte als JJJJ-MM-TT.")


# ------------------------------------------------------------------ Konten
def registrieren(c, name: str, passwort: str) -> dict:
    if os.getenv("KALORIEN_OFFEN", "1") == "0":
        raise Fehler(403, "Registrierung ist geschlossen.")
    name = name.strip()
    if not re.fullmatch(r"[\w .-]{3,24}", name):
        raise Fehler(400, "Name: 3–24 Zeichen (Buchstaben, Zahlen, Punkt, Strich, Leerzeichen).")
    if VERBOTEN.search(name):
        raise Fehler(400, "Dieser Name ist nicht erlaubt.")
    if len(passwort) < 8:
        raise Fehler(400, "Das Passwort braucht mindestens 8 Zeichen.")
    salz = db.neues_salz()
    try:
        cur = c.execute("INSERT INTO nutzer(name, pw_hash, salz, erstellt) VALUES (?,?,?,?)",
                        (name, db.pw_hash(passwort, salz), salz, db.jetzt()))
    except Exception:
        raise Fehler(409, "Diesen Namen gibt es schon.")
    return {"id": cur.lastrowid, "name": name}


def anmelden(c, name: str, passwort: str) -> dict:
    z = c.execute("SELECT * FROM nutzer WHERE name=?", (name.strip(),)).fetchone()
    if not z or not db.pw_stimmt(passwort, z["salz"], z["pw_hash"]):
        raise Fehler(401, "Name oder Passwort stimmt nicht.")
    if z["gesperrt"]:
        raise Fehler(403, "Dieses Konto ist gesperrt.")
    return {"id": z["id"], "name": z["name"]}


def zugang_anlegen(c, nutzer: int, art: str, name: str = "") -> str:
    token = ("kt_" if art == "api" else "ks_") + secrets.token_urlsafe(30)
    c.execute("INSERT INTO zugang(hash, nutzer, art, name, erstellt) VALUES (?,?,?,?,?)",
              (db.token_hash(token), nutzer, art, name[:40], db.jetzt()))
    return token


def nutzer_aus(c, kopf: str):
    if not kopf.lower().startswith("bearer "):
        raise Fehler(401, "Bitte anmelden.")
    h = db.token_hash(kopf[7:].strip())
    z = c.execute("SELECT n.*, a.art AS zugang_art FROM zugang a JOIN nutzer n ON n.id=a.nutzer WHERE a.hash=?", (h,)).fetchone()
    if not z or z["gesperrt"]:
        raise Fehler(401, "Bitte neu anmelden.")
    c.execute("UPDATE zugang SET zuletzt=? WHERE hash=?", (db.jetzt(), h))
    return z


def ich(z) -> dict:
    return {"name": z["name"], "admin": z["name"].lower() in _admins(), "ki": ki.verfuegbar(),
            "profil": json.loads(z["profil"] or "{}"),
            "ziele": {"kcal": z["ziel_kcal"], "eiweiss": z["ziel_eiweiss"], "kh": z["ziel_kh"], "fett": z["ziel_fett"]}}


def profil_speichern(c, z, d: dict) -> dict:
    ziele = {k: int(_zahl(d[k], k, 20000)) for k in ("kcal", "eiweiss", "kh", "fett") if d.get(k) not in (None, "")}
    profil = json.loads(z["profil"] or "{}")
    if d.get("berechnen"):
        b = d["berechnen"]
        try:
            erg = nahrung.ziele_berechnen(str(b.get("geschlecht", "m"))[:1], int(b["alter"]), float(b["groesse"]),
                                          float(b["gewicht"]), str(b.get("aktivitaet", "leicht")), str(b.get("ziel", "halten")))
        except (KeyError, TypeError, ValueError) as e:
            raise Fehler(400, str(e) if isinstance(e, ValueError) and str(e) else "Bitte alle Angaben ausfüllen.")
        ziele = {k[5:]: v for k, v in erg.items()}
        profil = {k: b.get(k) for k in ("geschlecht", "alter", "groesse", "gewicht", "aktivitaet", "ziel")}
    for k, spalte in (("kcal", "ziel_kcal"), ("eiweiss", "ziel_eiweiss"), ("kh", "ziel_kh"), ("fett", "ziel_fett")):
        if k in ziele:
            c.execute(f"UPDATE nutzer SET {spalte}=? WHERE id=?", (ziele[k], z["id"]))
    c.execute("UPDATE nutzer SET profil=? WHERE id=?", (json.dumps(profil), z["id"]))
    return {"ziele": ziele}


# ------------------------------------------------------------------ Tagebuch
def _summe(zeilen) -> dict:
    s = {"kcal": 0.0, "eiweiss": 0.0, "kh": 0.0, "fett": 0.0}
    for e in zeilen:
        for k in s:
            s[k] = round(s[k] + (e[k] or 0), 1)
    return s


def tag(c, z, datum: str) -> dict:
    zeilen = c.execute("SELECT * FROM eintrag WHERE nutzer=? AND datum=? ORDER BY id", (z["id"], datum)).fetchall()
    return {"datum": datum, "eintraege": [dict(e) for e in zeilen], "summe": _summe(zeilen), **{"ziele": ich(z)["ziele"]}}


def eintragen(c, z, d: dict) -> dict:
    mahlzeit = d.get("mahlzeit") if d.get("mahlzeit") in MAHLZEITEN else _mahlzeit_jetzt()
    cur = c.execute(
        "INSERT INTO eintrag(nutzer, datum, mahlzeit, name, menge, kcal, eiweiss, kh, fett, quelle, erstellt) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (z["id"], _datum(d.get("datum")), mahlzeit, _text(d.get("name"), "Name", 1, 120), str(d.get("menge") or "")[:40],
         _zahl(d.get("kcal"), "Kalorien", 10000), _zahl(d.get("eiweiss") or 0, "Eiweiß", 1000), _zahl(d.get("kh") or 0, "Kohlenhydrate", 2000),
         _zahl(d.get("fett") or 0, "Fett", 1000), str(d.get("quelle") or "hand")[:12], db.jetzt()))
    return {"id": cur.lastrowid}


def _mahlzeit_jetzt() -> str:
    h = datetime.now().hour
    return "fruehstueck" if h < 10 else "mittag" if h < 15 else "abend" if h < 21 else "snack"


def woche(c, z) -> list[dict]:
    zeilen = c.execute("SELECT datum, SUM(kcal) k, SUM(eiweiss) e FROM eintrag WHERE nutzer=? AND datum>=date('now','-6 day') "
                       "GROUP BY datum", (z["id"],)).fetchall()
    nach = {r["datum"]: r for r in zeilen}
    heute = date.today()
    out = []
    for i in range(6, -1, -1):
        t = date.fromordinal(heute.toordinal() - i).isoformat()
        out.append({"datum": t, "kcal": round(nach[t]["k"]) if t in nach else 0, "eiweiss": round(nach[t]["e"]) if t in nach else 0})
    return out


def ki_zaehlen(c, z) -> None:
    grenze = int(os.getenv("KALORIEN_KI_PRO_TAG", "30") or 30)
    t = date.today().isoformat()
    c.execute("INSERT OR IGNORE INTO ki_nutzung(nutzer, tag, n) VALUES (?,?,0)", (z["id"], t))
    if c.execute("SELECT n FROM ki_nutzung WHERE nutzer=? AND tag=?", (z["id"], t)).fetchone()["n"] >= grenze:
        raise Fehler(429, f"Heute sind {grenze} KI-Schätzungen aufgebraucht. Du kannst weiter von Hand eintragen.")
    c.execute("UPDATE ki_nutzung SET n=n+1 WHERE nutzer=? AND tag=?", (z["id"], t))


# ------------------------------------------------------------------ Community
def _blockiert(c, nutzer: int) -> set[int]:
    return {r["ziel"] for r in c.execute("SELECT ziel FROM blockiert WHERE nutzer=?", (nutzer,))}


def _frei(c, z, liste: list[dict]) -> list[dict]:
    weg = _blockiert(c, z["id"])
    return [x for x in liste if x["nutzer"] not in weg]


def themen(c, z, seite: int) -> list[dict]:
    zeilen = c.execute("SELECT t.id, t.nutzer, n.name, t.titel, t.erstellt, t.letzte, t.antworten FROM thema t JOIN nutzer n ON n.id=t.nutzer "
                       "WHERE t.versteckt=0 ORDER BY t.letzte DESC LIMIT 30 OFFSET ?", (max(0, seite) * 30,)).fetchall()
    return [{k: x[k] for k in ("id", "name", "titel", "erstellt", "letzte", "antworten")} for x in _frei(c, z, [dict(r) for r in zeilen])]


def thema_lesen(c, z, tid: int) -> dict:
    t = c.execute("SELECT t.*, n.name FROM thema t JOIN nutzer n ON n.id=t.nutzer WHERE t.id=? AND t.versteckt=0", (tid,)).fetchone()
    if not t:
        raise Fehler(404, "Beitrag nicht gefunden.")
    a = c.execute("SELECT a.id, a.nutzer, n.name, a.text, a.erstellt FROM antwort a JOIN nutzer n ON n.id=a.nutzer "
                  "WHERE a.thema=? AND a.versteckt=0 ORDER BY a.id", (tid,)).fetchall()
    return {"id": t["id"], "name": t["name"], "titel": t["titel"], "text": t["text"], "erstellt": t["erstellt"],
            "eigen": t["nutzer"] == z["id"],
            "antworten": [{"id": x["id"], "name": x["name"], "text": x["text"], "erstellt": x["erstellt"], "eigen": x["nutzer"] == z["id"]}
                          for x in _frei(c, z, [dict(r) for r in a])]}


def thema_neu(c, z, d: dict) -> dict:
    _bremse(f"thema:{z['id']}", 5, 600)
    titel, text = _text(d.get("titel"), "Titel", 3, 120), _text(d.get("text"), "Text", 3, 4000)
    t = db.jetzt()
    cur = c.execute("INSERT INTO thema(nutzer, titel, text, erstellt, letzte) VALUES (?,?,?,?,?)", (z["id"], titel, text, t, t))
    return {"id": cur.lastrowid}


def antwort_neu(c, z, tid: int, d: dict) -> dict:
    _bremse(f"antwort:{z['id']}", 12, 300)
    if not c.execute("SELECT 1 FROM thema WHERE id=? AND versteckt=0", (tid,)).fetchone():
        raise Fehler(404, "Beitrag nicht gefunden.")
    text = _text(d.get("text"), "Antwort", 1, 2000)
    t = db.jetzt()
    cur = c.execute("INSERT INTO antwort(thema, nutzer, text, erstellt) VALUES (?,?,?,?)", (tid, z["id"], text, t))
    c.execute("UPDATE thema SET antworten=antworten+1, letzte=? WHERE id=?", (t, tid))
    return {"id": cur.lastrowid}


def chat_lesen(c, z, nach: int) -> list[dict]:
    if nach > 0:
        zeilen = c.execute("SELECT c.id, c.nutzer, n.name, c.text, c.erstellt FROM chat c JOIN nutzer n ON n.id=c.nutzer "
                           "WHERE c.versteckt=0 AND c.id>? ORDER BY c.id LIMIT 100", (nach,)).fetchall()
    else:
        zeilen = list(reversed(c.execute("SELECT c.id, c.nutzer, n.name, c.text, c.erstellt FROM chat c JOIN nutzer n ON n.id=c.nutzer "
                                         "WHERE c.versteckt=0 ORDER BY c.id DESC LIMIT 50").fetchall()))
    return [{"id": x["id"], "name": x["name"], "text": x["text"], "erstellt": x["erstellt"], "eigen": x["nutzer"] == z["id"]}
            for x in _frei(c, z, [dict(r) for r in zeilen])]


def chat_schreiben(c, z, d: dict) -> dict:
    _bremse(f"chat:{z['id']}", 8, 20)
    cur = c.execute("INSERT INTO chat(nutzer, text, erstellt) VALUES (?,?,?)", (z["id"], _text(d.get("text"), "Nachricht", 1, 500), db.jetzt()))
    return {"id": cur.lastrowid}


def melden(c, z, d: dict) -> dict:
    art = d.get("art")
    if art not in ("thema", "antwort", "chat"):
        raise Fehler(400, "Unbekannte Art.")
    _bremse(f"melden:{z['id']}", 10, 600)
    c.execute("INSERT INTO meldung(von, art, ziel, grund, erstellt) VALUES (?,?,?,?,?)",
              (z["id"], art, int(d.get("id") or 0), str(d.get("grund") or "")[:300], db.jetzt()))
    return {"text": "Danke, wir schauen es uns an."}


def blockieren(c, z, name: str, an: bool = True) -> dict:
    ziel = c.execute("SELECT id FROM nutzer WHERE name=?", (name,)).fetchone()
    if not ziel or ziel["id"] == z["id"]:
        raise Fehler(404, "Nutzer nicht gefunden.")
    if an:
        c.execute("INSERT OR IGNORE INTO blockiert VALUES (?,?)", (z["id"], ziel["id"]))
    else:
        c.execute("DELETE FROM blockiert WHERE nutzer=? AND ziel=?", (z["id"], ziel["id"]))
    return {"text": f"{name} ist blockiert – du siehst nichts mehr von {name}." if an else f"{name} ist nicht mehr blockiert."}


def loeschen(c, z, art: str, oid: int) -> dict:
    tabelle = {"thema": "thema", "antwort": "antwort", "chat": "chat"}.get(art)
    if not tabelle:
        raise Fehler(400, "Unbekannte Art.")
    zeile = c.execute(f"SELECT nutzer FROM {tabelle} WHERE id=?", (oid,)).fetchone()
    if not zeile:
        raise Fehler(404, "Nicht gefunden.")
    if zeile["nutzer"] != z["id"] and z["name"].lower() not in _admins():
        raise Fehler(403, "Das darfst du nicht löschen.")
    c.execute(f"UPDATE {tabelle} SET versteckt=1 WHERE id=?", (oid,))
    return {"text": "Gelöscht."}


def konto_loeschen(c, z) -> dict:
    c.execute("DELETE FROM nutzer WHERE id=?", (z["id"],))   # Tagebuch, Beitraege, Zugaenge: ON DELETE CASCADE
    c.execute("DELETE FROM blockiert WHERE nutzer=? OR ziel=?", (z["id"], z["id"]))
    c.execute("DELETE FROM ki_nutzung WHERE nutzer=?", (z["id"],))
    return {"text": "Dein Konto und alle deine Daten sind gelöscht."}


def export(c, z) -> dict:
    return {"name": z["name"], "ziele": ich(z)["ziele"], "profil": json.loads(z["profil"] or "{}"),
            "tagebuch": [dict(r) for r in c.execute("SELECT datum, mahlzeit, name, menge, kcal, eiweiss, kh, fett FROM eintrag WHERE nutzer=? "
                                                    "ORDER BY datum, id", (z["id"],))],
            "beitraege": [dict(r) for r in c.execute("SELECT titel, text, erstellt FROM thema WHERE nutzer=?", (z["id"],))]}


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "Kalorien"
    sys_version = ""
    timeout = 30

    def log_message(self, *a) -> None:
        pass

    def _adresse(self) -> str:
        if os.getenv("KALORIEN_PROXY") == "1":
            return (self.headers.get("X-Forwarded-For") or "").split(",")[-1].strip() or self.client_address[0]
        return self.client_address[0]

    def _senden(self, status: int, daten, art: str = "application/json; charset=utf-8", extra: dict | None = None) -> None:
        roh = daten if isinstance(daten, bytes) else json.dumps(daten, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", art)
        self.send_header("Content-Length", str(len(roh)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
                         "style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(roh)

    def _datei(self, pfad: str) -> None:
        rel = unquote(pfad).lstrip("/") or "index.html"
        ziel = (WEB / rel).resolve()
        if WEB.resolve() not in ziel.parents and ziel != WEB.resolve() or not ziel.is_file():
            ziel = WEB / "index.html"
        art = mimetypes.guess_type(ziel.name)[0] or "application/octet-stream"
        if ziel.suffix == ".webmanifest":
            art = "application/manifest+json"
        cache = "no-cache" if ziel.suffix in (".html", ".js", ".webmanifest") or ziel.name == "sw.js" else "public, max-age=86400"
        self._senden(200, ziel.read_bytes(), art + ("; charset=utf-8" if art.startswith("text/") or art.endswith("javascript") else ""),
                     {"Cache-Control": cache})

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        self._antworten("GET")

    def do_POST(self) -> None:
        self._antworten("POST")

    def do_PUT(self) -> None:
        self._antworten("PUT")

    def do_DELETE(self) -> None:
        self._antworten("DELETE")

    def _antworten(self, methode: str) -> None:
        u = urlparse(self.path)
        if not u.path.startswith("/api/"):
            return self._datei(u.path) if methode in ("GET", "HEAD") else self._senden(405, {"fehler": "nicht erlaubt"})
        try:
            body = {}
            if methode in ("POST", "PUT"):
                laenge = int(self.headers.get("Content-Length") or 0)
                if laenge > MAX_BODY:
                    raise Fehler(413, "Zu groß.")
                try:
                    body = json.loads(self.rfile.read(laenge).decode("utf-8", "replace") or "{}")
                except ValueError:
                    raise Fehler(400, "Kein gültiges JSON.")
                if not isinstance(body, dict):
                    raise Fehler(400, "Kein gültiges JSON.")
            c = db.verbinden()
            try:
                antwort = self._route(c, methode, u.path[5:].strip("/"), {k: v[0] for k, v in parse_qs(u.query).items()}, body)
                c.commit()
            finally:
                c.close()
            self._senden(200, antwort)
        except Fehler as e:
            self._senden(e.status, {"fehler": e.text})
        except ki.KiFehler as e:
            self._senden(503, {"fehler": str(e)})
        except RuntimeError as e:
            self._senden(503, {"fehler": str(e)})
        except Exception as e:   # nie Interna nach aussen
            print(f"[Kalorien] {methode} {u.path}: {type(e).__name__}: {e}", flush=True)
            self._senden(500, {"fehler": "Da ist etwas schiefgegangen."})

    def _route(self, c, m: str, pfad: str, q: dict, d: dict):
        teile = pfad.split("/")
        t0 = teile[0]
        if m == "POST" and t0 in ("registrieren", "anmelden"):
            _bremse(f"login:{self._adresse()}", 10)
            n = (registrieren if t0 == "registrieren" else anmelden)(c, str(d.get("name") or ""), str(d.get("passwort") or ""))
            return {"token": zugang_anlegen(c, n["id"], "sitzung"), "name": n["name"]}
        if m == "GET" and t0 == "status":
            return {"ok": True, "ki": ki.verfuegbar()}
        z = nutzer_aus(c, self.headers.get("Authorization", ""))
        _bremse(f"api:{z['id']}", 240)
        if t0 == "ich":
            if m == "GET":
                return ich(z)
            if m == "PUT":
                return profil_speichern(c, z, d)
            if m == "DELETE":
                return konto_loeschen(c, z)
        if t0 == "export" and m == "GET":
            return export(c, z)
        if t0 == "tag" and m == "GET":
            return tag(c, z, _datum(q.get("datum")))
        if t0 == "woche" and m == "GET":
            return woche(c, z)
        if t0 == "eintrag":
            if m == "POST":
                return eintragen(c, z, d)
            if m == "DELETE" and len(teile) == 2:
                c.execute("DELETE FROM eintrag WHERE id=? AND nutzer=?", (int(teile[1]), z["id"]))
                return {"text": "Gelöscht."}
        if t0 == "schaetzen" and m == "POST" and len(teile) == 2:
            if not ki.verfuegbar():
                raise Fehler(503, "Die KI ist auf diesem Server nicht eingerichtet.")
            _bremse(f"ki:{z['id']}", 10)
            ki_zaehlen(c, z)
            if teile[1] == "text":
                return ki.aus_text(str(d.get("text") or ""))
            if teile[1] == "bild":
                try:
                    bild = base64.b64decode(str(d.get("bild") or ""), validate=False)
                except ValueError:
                    raise Fehler(400, "Das Foto war nicht lesbar.")
                if not 1000 < len(bild) <= 3 * 1024 * 1024:
                    raise Fehler(400, "Das Foto ist zu groß oder leer.")
                return ki.aus_bild(bild, str(d.get("mime") or "image/jpeg"), str(d.get("hinweis") or ""))
        if t0 == "barcode" and m == "GET" and len(teile) == 2:
            _bremse(f"bc:{z['id']}", 30)
            try:
                p = nahrung.barcode_suchen(teile[1])
            except ValueError as e:
                raise Fehler(400, str(e))
            if p is None:
                raise Fehler(404, "Dieses Produkt kenne ich nicht. Trag es von Hand ein oder beschreibe es.")
            return p
        if t0 == "zugang":
            if z["zugang_art"] != "sitzung":
                raise Fehler(403, "Schlüssel verwalten geht nur in der App selbst.")
            if m == "POST":
                _bremse(f"zugang:{z['id']}", 5, 600)
                name = _text(d.get("name"), "Name", 1, 40)
                return {"token": zugang_anlegen(c, z["id"], "api", name), "text": "Nur jetzt sichtbar – kopiere ihn."}
            if m == "GET":
                return [{"hash": r["hash"][:10], "name": r["name"], "erstellt": r["erstellt"], "zuletzt": r["zuletzt"]}
                        for r in c.execute("SELECT * FROM zugang WHERE nutzer=? AND art='api'", (z["id"],))]
            if m == "DELETE" and len(teile) == 2:
                c.execute("DELETE FROM zugang WHERE nutzer=? AND art='api' AND substr(hash,1,10)=?", (z["id"], teile[1][:10]))
                return {"text": "Schlüssel gelöscht."}
        if t0 == "forum":
            if m == "GET" and len(teile) == 1:
                return themen(c, z, int(q.get("seite") or 0))
            if m == "GET" and len(teile) == 2:
                return thema_lesen(c, z, int(teile[1]))
            if m == "POST" and len(teile) == 1:
                return thema_neu(c, z, d)
            if m == "POST" and len(teile) == 3 and teile[2] == "antwort":
                return antwort_neu(c, z, int(teile[1]), d)
        if t0 == "chat":
            if m == "GET":
                return chat_lesen(c, z, int(q.get("nach") or 0))
            if m == "POST":
                return chat_schreiben(c, z, d)
        if t0 == "melden" and m == "POST":
            return melden(c, z, d)
        if t0 == "blockieren" and m in ("POST", "DELETE"):
            return blockieren(c, z, str(d.get("name") or q.get("name") or ""), m == "POST")
        if t0 == "loeschen" and m == "POST":
            return loeschen(c, z, str(d.get("art")), int(d.get("id") or 0))
        if t0 == "meldungen" and m == "GET" and z["name"].lower() in _admins():
            return [dict(r) for r in c.execute("SELECT * FROM meldung ORDER BY id DESC LIMIT 100")]
        if t0 == "sperren" and m == "POST" and z["name"].lower() in _admins():
            c.execute("UPDATE nutzer SET gesperrt=1 WHERE name=? AND lower(name) NOT IN (%s)" % ",".join("?" * len(_admins() or {""})),
                      (str(d.get("name")), *(_admins() or {""})))
            return {"text": "Gesperrt."}
        raise Fehler(404, "Unbekannte Adresse.")


def starten(host: str = "127.0.0.1", port: int | None = None) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, PORT if port is None else port), Handler)
    server.daemon_threads = True
    return server


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except ImportError:
        pass
    s = starten(port=int(os.getenv("KALORIEN_PORT", "7730") or 7730))
    print(f"[Kalorien] läuft auf http://127.0.0.1:{s.server_address[1]}  (KI: {'an' if ki.verfuegbar() else 'aus – GEMINI_API_KEY fehlt'})", flush=True)
    s.serve_forever()
