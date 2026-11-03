"""Kalorien-App - Fitness-Social-Media: Profile, Folgen, Feed mit Fotos, Likes, Kommentare, Training, Wasser, Gewicht,
Serien (Streaks) und Rangliste. Funktionen bekommen (Verbindung c, Nutzerzeile z, ...) wie in server.py."""
from __future__ import annotations

import base64
import json
import re
import secrets
from datetime import date, timedelta

from . import db

ARTEN = ("text", "training", "mahlzeit", "fortschritt")
# MET-Werte (Energieverbrauch je kg und Stunde) - grobe Richtwerte
MET = {"laufen": 9.8, "gehen": 3.5, "radfahren": 7.5, "schwimmen": 7.0, "krafttraining": 5.0, "yoga": 2.5, "hiit": 8.0,
       "fussball": 7.0, "wandern": 6.0, "tanzen": 5.0, "sonstiges": 5.0}
TRAININGSNAMEN = {"laufen": "Laufen", "gehen": "Gehen", "radfahren": "Radfahren", "schwimmen": "Schwimmen", "krafttraining": "Krafttraining",
                  "yoga": "Yoga", "hiit": "HIIT", "fussball": "Fußball", "wandern": "Wandern", "tanzen": "Tanzen", "sonstiges": "Sonstiges"}
WASSER_ZIEL = 2500
MAX_BILD = 900 * 1024


class SozialFehler(Exception):
    def __init__(self, status: int, text: str) -> None:
        super().__init__(text)
        self.status, self.text = status, text


def jpeg_bereinigen(b: bytes) -> bytes:
    """Wirft EXIF/GPS und alle Zusatzdaten weg (APP1-APP15, Kommentare) und prueft, dass es wirklich ein JPEG ist."""
    if b[:3] != b"\xff\xd8\xff":
        raise SozialFehler(400, "Bitte ein JPEG-Foto senden.")
    out, i = bytearray(b"\xff\xd8"), 2
    while i + 4 <= len(b):
        if b[i] != 0xFF:
            raise SozialFehler(400, "Das Foto ist beschädigt.")
        m = b[i + 1]
        if m == 0xFF:
            i += 1
            continue
        if m == 0xD9:
            break
        if m == 0xDA:   # ab hier nur noch Bilddaten
            out += b[i:]
            return bytes(out)
        if 0xD0 <= m <= 0xD7 or m == 0x01:
            out += b[i:i + 2]
            i += 2
            continue
        ln = int.from_bytes(b[i + 2:i + 4], "big")
        if ln < 2:
            raise SozialFehler(400, "Das Foto ist beschädigt.")
        if not (0xE1 <= m <= 0xEF or m == 0xFE):
            out += b[i:i + 2 + ln]
        i += 2 + ln
    raise SozialFehler(400, "Das Foto ist unvollständig.")


def bild_speichern(daten_b64: str) -> str:
    try:
        roh = base64.b64decode(daten_b64, validate=False)
    except ValueError:
        raise SozialFehler(400, "Das Foto war nicht lesbar.")
    if not 500 < len(roh) <= MAX_BILD:
        raise SozialFehler(400, "Das Foto ist leer oder zu groß (max. 900 KB – die App verkleinert automatisch).")
    sauber = jpeg_bereinigen(roh)
    db.BILDER.mkdir(parents=True, exist_ok=True)
    name = secrets.token_hex(12) + ".jpg"
    (db.BILDER / name).write_bytes(sauber)
    return name


def bild_loeschen(name: str) -> None:
    if name and re.fullmatch(r"[0-9a-f]{24}\.jpg", name):
        (db.BILDER / name).unlink(missing_ok=True)


def bild_lesen(name: str) -> bytes | None:
    if not re.fullmatch(r"[0-9a-f]{24}\.jpg", name or ""):
        return None
    try:
        return (db.BILDER / name).read_bytes()
    except OSError:
        return None


# ------------------------------------------------------------------ Training, Wasser, Gewicht
def gewicht_aktuell(c, z) -> float:
    r = c.execute("SELECT kg FROM gewicht WHERE nutzer=? ORDER BY datum DESC LIMIT 1", (z["id"],)).fetchone()
    if r:
        return r["kg"]
    try:
        return float(json.loads(z["profil"] or "{}").get("gewicht") or 75)
    except (TypeError, ValueError):
        return 75.0


def training_eintragen(c, z, d: dict, datum: str, text, zahl) -> dict:
    art = d.get("art") if d.get("art") in MET else "sonstiges"
    minuten = int(zahl(d.get("minuten"), "Minuten", 600))
    if minuten < 1:
        raise SozialFehler(400, "Mindestens 1 Minute.")
    kcal = int(zahl(d["kcal"], "Kalorien", 6000)) if str(d.get("kcal") or "").strip() else round(MET[art] * gewicht_aktuell(c, z) * minuten / 60)
    notiz = text(d.get("notiz"), "Notiz", 0, 200) if str(d.get("notiz") or "").strip() else ""
    cur = c.execute("INSERT INTO training(nutzer, datum, art, minuten, kcal, notiz, erstellt) VALUES (?,?,?,?,?,?,?)",
                    (z["id"], datum, art, minuten, kcal, notiz, db.jetzt()))
    return {"id": cur.lastrowid, "kcal": kcal, "art": art, "minuten": minuten}


def tag_zusatz(c, z, datum: str) -> dict:
    tr = [dict(r) for r in c.execute("SELECT id, art, minuten, kcal, notiz FROM training WHERE nutzer=? AND datum=? ORDER BY id", (z["id"], datum))]
    w = c.execute("SELECT ml FROM wasser WHERE nutzer=? AND datum=?", (z["id"], datum)).fetchone()
    return {"training": tr, "verbrannt": sum(t["kcal"] for t in tr), "wasser_ml": w["ml"] if w else 0, "ziel_wasser": WASSER_ZIEL}


def wasser_addieren(c, z, datum: str, ml: int) -> dict:
    if not -2000 <= ml <= 2000 or ml == 0:
        raise SozialFehler(400, "Menge bitte zwischen -2000 und 2000 ml.")
    c.execute("INSERT OR IGNORE INTO wasser(nutzer, datum, ml) VALUES (?,?,0)", (z["id"], datum))
    c.execute("UPDATE wasser SET ml=MAX(0, MIN(10000, ml+?)) WHERE nutzer=? AND datum=?", (ml, z["id"], datum))
    return {"ml": c.execute("SELECT ml FROM wasser WHERE nutzer=? AND datum=?", (z["id"], datum)).fetchone()["ml"]}


def gewicht_setzen(c, z, datum: str, kg: float) -> dict:
    if not 25 <= kg <= 400:
        raise SozialFehler(400, "Gewicht bitte zwischen 25 und 400 kg.")
    c.execute("INSERT INTO gewicht(nutzer, datum, kg) VALUES (?,?,?) ON CONFLICT(nutzer, datum) DO UPDATE SET kg=excluded.kg", (z["id"], datum, kg))
    return {"kg": kg}


def gewicht_verlauf(c, z) -> list[dict]:
    return [dict(r) for r in c.execute("SELECT datum, kg FROM gewicht WHERE nutzer=? ORDER BY datum DESC LIMIT 60", (z["id"],))][::-1]


# ------------------------------------------------------------------ Serien, Abzeichen, Rangliste
def aktive_tage(c, nutzer: int) -> set[str]:
    a = {r[0] for r in c.execute("SELECT DISTINCT datum FROM eintrag WHERE nutzer=?", (nutzer,))}
    return a | {r[0] for r in c.execute("SELECT DISTINCT datum FROM training WHERE nutzer=?", (nutzer,))}


def serie(tage: set[str], heute: date | None = None) -> int:
    """Aufeinanderfolgende aktive Tage; gilt auch, wenn heute noch nichts war, aber gestern (Serie ist noch zu retten)."""
    t = heute or date.today()
    if t.isoformat() not in tage:
        t -= timedelta(days=1)
    n = 0
    while t.isoformat() in tage:
        n += 1
        t -= timedelta(days=1)
    return n


def abzeichen(serie_tage: int, trainings: int, beitraege: int, folger: int) -> list[dict]:
    kandidaten = [(serie_tage >= 3, "🔥", "3 Tage in Folge"), (serie_tage >= 7, "🔥", "7-Tage-Serie"), (serie_tage >= 30, "🏆", "30-Tage-Serie"),
                  (trainings >= 1, "💪", "Erstes Training"), (trainings >= 10, "💪", "10 Trainings"), (trainings >= 50, "🥇", "50 Trainings"),
                  (beitraege >= 1, "📣", "Erster Beitrag"), (folger >= 10, "⭐", "10 Folgende")]
    return [{"icon": i, "name": n} for ok, i, n in kandidaten if ok]


def rangliste(c, z) -> list[dict]:
    """Aktive Minuten der letzten 7 Tage. Nur wer mitmacht (in_rangliste), am Tag hoechstens 240 Minuten gezaehlt (gegen Schummeln)."""
    seit = (date.today() - timedelta(days=6)).isoformat()
    zeilen = c.execute(
        "SELECT n.id, n.name, SUM(MIN(t.tag_min, 240)) AS minuten, COUNT(*) AS tage FROM "
        "(SELECT nutzer, datum, SUM(minuten) AS tag_min FROM training WHERE datum>=? GROUP BY nutzer, datum) t "
        "JOIN nutzer n ON n.id=t.nutzer WHERE n.in_rangliste=1 AND n.gesperrt=0 GROUP BY n.id ORDER BY minuten DESC LIMIT 20", (seit,)).fetchall()
    weg = {r["ziel"] for r in c.execute("SELECT ziel FROM blockiert WHERE nutzer=?", (z["id"],))}
    return [{"name": r["name"], "minuten": r["minuten"], "tage": r["tage"], "ich": r["id"] == z["id"]} for r in zeilen if r["id"] not in weg]


# ------------------------------------------------------------------ Profile und Folgen
def profil(c, z, name: str) -> dict:
    p = c.execute("SELECT id, name, bio, erstellt FROM nutzer WHERE name=? AND gesperrt=0", (name,)).fetchone()
    if not p:
        raise SozialFehler(404, "Profil nicht gefunden.")
    tage = aktive_tage(c, p["id"])
    zahl = lambda sql, *a: c.execute(sql, a).fetchone()[0]
    trainings = zahl("SELECT COUNT(*) FROM training WHERE nutzer=?", p["id"])
    beitraege = zahl("SELECT COUNT(*) FROM beitrag WHERE nutzer=? AND versteckt=0", p["id"])
    folger = zahl("SELECT COUNT(*) FROM folgen WHERE ziel=?", p["id"])
    seit = (date.today() - timedelta(days=6)).isoformat()
    return {"name": p["name"], "bio": p["bio"] or "", "seit": p["erstellt"], "ich": p["id"] == z["id"], "folgt_ihm": bool(zahl(
        "SELECT COUNT(*) FROM folgen WHERE von=? AND ziel=?", z["id"], p["id"])), "folger": folger,
        "folgt": zahl("SELECT COUNT(*) FROM folgen WHERE von=?", p["id"]), "beitraege": beitraege, "trainings": trainings,
        "serie": serie(tage), "woche_min": zahl("SELECT COALESCE(SUM(minuten),0) FROM training WHERE nutzer=? AND datum>=?", p["id"], seit),
        "abzeichen": abzeichen(serie(tage), trainings, beitraege, folger)}


def folgen(c, z, name: str, an: bool) -> dict:
    ziel = c.execute("SELECT id FROM nutzer WHERE name=? AND gesperrt=0", (name,)).fetchone()
    if not ziel or ziel["id"] == z["id"]:
        raise SozialFehler(404, "Nutzer nicht gefunden.")
    if an:
        c.execute("INSERT OR IGNORE INTO folgen(von, ziel, erstellt) VALUES (?,?,?)", (z["id"], ziel["id"], db.jetzt()))
    else:
        c.execute("DELETE FROM folgen WHERE von=? AND ziel=?", (z["id"], ziel["id"]))
    return {"folgt": an}


def suche(c, z, q: str) -> list[dict]:
    q = re.sub(r"[%_\\]", "", q.strip())[:24]
    if len(q) < 2:
        return []
    return [{"name": r["name"]} for r in c.execute("SELECT name FROM nutzer WHERE name LIKE ? AND gesperrt=0 AND id!=? ORDER BY name LIMIT 15",
                                                    (q + "%", z["id"]))]


# ------------------------------------------------------------------ Feed
def _weg(c, z) -> set[int]:
    return {r["ziel"] for r in c.execute("SELECT ziel FROM blockiert WHERE nutzer=?", (z["id"],))} | \
           {r["nutzer"] for r in c.execute("SELECT nutzer FROM blockiert WHERE ziel=?", (z["id"],))}


def _beitrag_dict(r, z) -> dict:
    d = {"id": r["id"], "name": r["name"], "art": r["art"], "text": r["text"], "bild": ("/bild/" + r["bild"]) if r["bild"] else "",
         "erstellt": r["erstellt"], "likes": r["likes"], "kommentare": r["kommentare"], "geliked": bool(r["geliked"]), "eigen": r["nutzer"] == z["id"]}
    if r["art"] == "reel":
        d.update(video=("/video/" + r["video"]) if r["video"] else "", poster=("/bild/" + r["poster"]) if r["poster"] else "",
                 dauer=r["dauer"], status=r["status"], folgt=bool(r["folgt"]))
    return d


_SEL = ("SELECT b.id, b.nutzer, n.name, b.art, b.text, b.bild, b.erstellt, b.video, b.poster, b.status, b.dauer, "
        "(SELECT COUNT(*) FROM folgen f WHERE f.von=? AND f.ziel=b.nutzer) AS folgt, "
        "(SELECT COUNT(*) FROM gefaellt g WHERE g.beitrag=b.id) AS likes, "
        "(SELECT COUNT(*) FROM kommentar k WHERE k.beitrag=b.id AND k.versteckt=0) AS kommentare, "
        "(SELECT COUNT(*) FROM gefaellt g WHERE g.beitrag=b.id AND g.nutzer=?) AS geliked "
        "FROM beitrag b JOIN nutzer n ON n.id=b.nutzer WHERE b.versteckt=0 AND n.gesperrt=0")


def feed(c, z, nur_folge: bool, vor: int, von_name: str = "") -> list[dict]:
    sql, arg = _SEL + " AND b.art!='reel'", [z["id"], z["id"]]
    if nur_folge:
        sql += " AND (b.nutzer=? OR b.nutzer IN (SELECT ziel FROM folgen WHERE von=?))"
        arg += [z["id"], z["id"]]
    if von_name:
        sql += " AND n.name=?"
        arg.append(von_name)
    if vor > 0:
        sql += " AND b.id<?"
        arg.append(vor)
    weg = _weg(c, z)
    zeilen = c.execute(sql + " ORDER BY b.id DESC LIMIT 60", arg).fetchall()
    return [_beitrag_dict(r, z) for r in zeilen if r["nutzer"] not in weg][:20]


def beitrag_lesen(c, z, bid: int) -> dict:
    r = c.execute(_SEL + " AND b.id=?", (z["id"], z["id"], bid)).fetchone()
    if not r or r["nutzer"] in _weg(c, z):
        raise SozialFehler(404, "Beitrag nicht gefunden.")
    weg = _weg(c, z)
    k = c.execute("SELECT k.id, k.nutzer, n.name, k.text, k.erstellt FROM kommentar k JOIN nutzer n ON n.id=k.nutzer "
                  "WHERE k.beitrag=? AND k.versteckt=0 ORDER BY k.id", (bid,)).fetchall()
    d = _beitrag_dict(r, z)
    d["kommentar_liste"] = [{"id": x["id"], "name": x["name"], "text": x["text"], "erstellt": x["erstellt"], "eigen": x["nutzer"] == z["id"]}
                            for x in k if x["nutzer"] not in weg]
    return d


def beitrag_neu(c, z, d: dict, text) -> dict:
    art = d.get("art") if d.get("art") in ARTEN else "text"
    inhalt = text(d.get("text"), "Text", 0, 1000) if str(d.get("text") or "").strip() else ""
    bild = bild_speichern(str(d["bild"])) if d.get("bild") else ""
    if not inhalt and not bild:
        raise SozialFehler(400, "Schreib etwas oder hänge ein Foto an.")
    cur = c.execute("INSERT INTO beitrag(nutzer, art, text, bild, erstellt) VALUES (?,?,?,?,?)", (z["id"], art, inhalt, bild, db.jetzt()))
    return {"id": cur.lastrowid}


def gefaellt_wechseln(c, z, bid: int) -> dict:
    if not c.execute("SELECT 1 FROM beitrag WHERE id=? AND versteckt=0", (bid,)).fetchone():
        raise SozialFehler(404, "Beitrag nicht gefunden.")
    if c.execute("SELECT 1 FROM gefaellt WHERE beitrag=? AND nutzer=?", (bid, z["id"])).fetchone():
        c.execute("DELETE FROM gefaellt WHERE beitrag=? AND nutzer=?", (bid, z["id"]))
        an = False
    else:
        c.execute("INSERT INTO gefaellt(beitrag, nutzer) VALUES (?,?)", (bid, z["id"]))
        an = True
    return {"geliked": an, "likes": c.execute("SELECT COUNT(*) FROM gefaellt WHERE beitrag=?", (bid,)).fetchone()[0]}


def kommentar_neu(c, z, bid: int, d: dict, text) -> dict:
    if not c.execute("SELECT 1 FROM beitrag WHERE id=? AND versteckt=0", (bid,)).fetchone():
        raise SozialFehler(404, "Beitrag nicht gefunden.")
    cur = c.execute("INSERT INTO kommentar(beitrag, nutzer, text, erstellt) VALUES (?,?,?,?)", (bid, z["id"], text(d.get("text"), "Kommentar", 1, 500), db.jetzt()))
    return {"id": cur.lastrowid}


def konto_bilder(c, nutzer: int) -> list[str]:
    return [r["bild"] for r in c.execute("SELECT bild FROM beitrag WHERE nutzer=? AND bild!=''", (nutzer,))]
