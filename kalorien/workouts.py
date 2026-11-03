"""Fit-App - Workout-Tracker: Training mit Uebungen und Saetzen (kg x Wiederholungen), Rekorde, Verlauf, Routinen.

Ein gespeichertes Workout legt ausserdem einen normalen Trainings-Eintrag (Krafttraining) an - damit zaehlen Serie,
Rangliste und Kalorienbilanz automatisch mit."""
from __future__ import annotations

import json

from . import db, sozial


class WorkoutFehler(Exception):
    def __init__(self, status: int, text: str) -> None:
        super().__init__(text)
        self.status, self.text = status, text


def einrm(kg: float, wdh: int) -> float:
    """Geschaetztes Maximalgewicht fuer eine Wiederholung (Epley). Bei 1 Wdh. = das Gewicht selbst."""
    return round(kg * (1 + wdh / 30), 1) if wdh > 1 else round(kg, 1)


def _saetze(w) -> list[dict]:
    if not isinstance(w, list) or not w:
        raise WorkoutFehler(400, "Trag mindestens einen Satz ein.")
    if len(w) > 300:
        raise WorkoutFehler(400, "Das sind zu viele Sätze (max. 300).")
    out, nr = [], {}
    for s in w:
        if not isinstance(s, dict):
            continue
        name = " ".join(str(s.get("uebung") or "").split())[:40]
        try:
            wdh, kg = int(float(str(s.get("wdh")).replace(",", "."))), float(str(s.get("kg") or 0).replace(",", "."))
        except ValueError:
            raise WorkoutFehler(400, "Wiederholungen und Gewicht müssen Zahlen sein.")
        if not name or not 1 <= wdh <= 100 or not 0 <= kg <= 1000:
            raise WorkoutFehler(400, "Satz ungültig: Übung, 1–100 Wiederholungen, 0–1000 kg.")
        nr[name.lower()] = nr.get(name.lower(), 0) + 1
        out.append({"uebung": name, "nr": nr[name.lower()], "wdh": wdh, "kg": round(kg, 2)})
    if not out:
        raise WorkoutFehler(400, "Trag mindestens einen Satz ein.")
    return out


def speichern(c, z, d: dict, datum: str, text, zahl) -> dict:
    saetze = _saetze(d.get("saetze"))
    name = text(d.get("name"), "Name", 1, 60) if str(d.get("name") or "").strip() else "Krafttraining"
    notiz = text(d.get("notiz"), "Notiz", 0, 300) if str(d.get("notiz") or "").strip() else ""
    try:
        minuten = int(float(str(d.get("minuten") or 0).replace(",", ".")))
    except ValueError:
        raise WorkoutFehler(400, "Minuten ist keine Zahl.")
    minuten = max(1, min(600, minuten)) if minuten > 0 else max(10, len(saetze) * 3)   # keine Angabe: ~3 Minuten je Satz (inkl. Pause)
    volumen = round(sum(s["kg"] * s["wdh"] for s in saetze), 1)

    # Rekorde: bester geschaetzter 1RM je Uebung gegen alles, was vorher gespeichert wurde
    rekorde = []
    for u in dict.fromkeys(s["uebung"].lower() for s in saetze):
        alt = c.execute("SELECT MAX(CASE WHEN wdh>1 THEN kg*(1+wdh/30.0) ELSE kg END) AS b FROM satz WHERE nutzer=? AND uebung=?", (z["id"], u)).fetchone()["b"]
        jetzt = max(einrm(s["kg"], s["wdh"]) for s in saetze if s["uebung"].lower() == u)
        if alt is not None and jetzt > alt + 0.05:   # der allererste Eintrag einer Uebung ist kein "Rekord"
            rekorde.append({"uebung": next(s["uebung"] for s in saetze if s["uebung"].lower() == u), "einrm": jetzt, "vorher": round(alt, 1)})

    tr = sozial.training_eintragen(c, z, {"art": "krafttraining", "minuten": minuten, "notiz": name}, datum, text, zahl)
    cur = c.execute("INSERT INTO workout(nutzer, datum, name, minuten, kcal, volumen, notiz, training_id, erstellt) VALUES (?,?,?,?,?,?,?,?,?)",
                    (z["id"], datum, name, minuten, tr["kcal"], volumen, notiz, tr["id"], db.jetzt()))
    wid = cur.lastrowid
    c.executemany("INSERT INTO satz(workout, nutzer, uebung, nr, wdh, kg) VALUES (?,?,?,?,?,?)",
                  [(wid, z["id"], s["uebung"], s["nr"], s["wdh"], s["kg"]) for s in saetze])
    return {"id": wid, "kcal": tr["kcal"], "minuten": minuten, "volumen": volumen, "saetze": len(saetze), "rekorde": rekorde}


def _zusammen(c, r) -> dict:
    ue = [x["uebung"] for x in c.execute("SELECT uebung FROM satz WHERE workout=? GROUP BY uebung ORDER BY MIN(id)", (r["id"],))]
    n = c.execute("SELECT COUNT(*) FROM satz WHERE workout=?", (r["id"],)).fetchone()[0]
    return {"id": r["id"], "datum": r["datum"], "name": r["name"], "minuten": r["minuten"], "kcal": r["kcal"], "volumen": r["volumen"],
            "saetze": n, "uebungen": ue, "notiz": r["notiz"]}


def verlauf(c, z, vor: int) -> list[dict]:
    sql, arg = "SELECT * FROM workout WHERE nutzer=?", [z["id"]]
    if vor > 0:
        sql += " AND id<?"
        arg.append(vor)
    return [_zusammen(c, r) for r in c.execute(sql + " ORDER BY datum DESC, id DESC LIMIT 20", arg)]


def lesen(c, z, wid: int) -> dict:
    r = c.execute("SELECT * FROM workout WHERE id=? AND nutzer=?", (wid, z["id"])).fetchone()
    if not r:
        raise WorkoutFehler(404, "Workout nicht gefunden.")
    d = _zusammen(c, r)
    d["saetze_liste"] = [dict(x) for x in c.execute("SELECT uebung, nr, wdh, kg FROM satz WHERE workout=? ORDER BY id", (wid,))]
    return d


def loeschen(c, z, wid: int) -> dict:
    r = c.execute("SELECT training_id FROM workout WHERE id=? AND nutzer=?", (wid, z["id"])).fetchone()
    if not r:
        raise WorkoutFehler(404, "Workout nicht gefunden.")
    c.execute("DELETE FROM workout WHERE id=?", (wid,))   # Saetze: ON DELETE CASCADE
    if r["training_id"]:
        c.execute("DELETE FROM training WHERE id=? AND nutzer=?", (r["training_id"], z["id"]))
    return {"text": "Workout gelöscht."}


def uebung_verlauf(c, z, name: str) -> dict:
    """Fortschritt einer Uebung: je Workout der beste Satz (geschaetztes Maximum) - fuers Diagramm."""
    name = " ".join(name.split())[:40]
    zeilen = c.execute("SELECT w.datum, s.kg, s.wdh FROM satz s JOIN workout w ON w.id=s.workout WHERE s.nutzer=? AND s.uebung=? "
                       "ORDER BY w.datum, s.id", (z["id"], name)).fetchall()
    je_tag: dict[str, dict] = {}
    for r in zeilen:
        e = einrm(r["kg"], r["wdh"])
        if r["datum"] not in je_tag or e > je_tag[r["datum"]]["einrm"]:
            je_tag[r["datum"]] = {"datum": r["datum"], "einrm": e, "kg": r["kg"], "wdh": r["wdh"]}
    punkte = list(je_tag.values())[-30:]
    return {"uebung": name, "punkte": punkte, "rekord": max((p["einrm"] for p in punkte), default=0)}


def letzte(c, z, name: str) -> list[dict]:
    """Saetze der letzten Einheit dieser Uebung - die App fuellt damit kg und Wdh. vor."""
    name = " ".join(name.split())[:40]
    w = c.execute("SELECT s.workout FROM satz s JOIN workout w ON w.id=s.workout WHERE s.nutzer=? AND s.uebung=? ORDER BY w.datum DESC, s.workout DESC LIMIT 1",
                  (z["id"], name)).fetchone()
    if not w:
        return []
    return [dict(r) for r in c.execute("SELECT nr, wdh, kg FROM satz WHERE workout=? AND uebung=? ORDER BY nr", (w["workout"], name))]


def statistik(c, z) -> dict:
    """Kennzahlen fuers Training-Tab: letzte 7 Tage und Gesamtsumme."""
    seit = c.execute("SELECT date('now','-6 day')").fetchone()[0]
    tage = {r["datum"]: r for r in c.execute("SELECT datum, SUM(minuten) m, SUM(kcal) k FROM training WHERE nutzer=? AND datum>=? GROUP BY datum", (z["id"], seit))}
    out = []
    from datetime import date, timedelta
    for i in range(6, -1, -1):
        t = (date.today() - timedelta(days=i)).isoformat()
        out.append({"datum": t, "minuten": tage[t]["m"] if t in tage else 0, "kcal": tage[t]["k"] if t in tage else 0})
    ges = c.execute("SELECT COUNT(*) n, COALESCE(SUM(volumen),0) v FROM workout WHERE nutzer=?", (z["id"],)).fetchone()
    return {"woche": out, "workouts": ges["n"], "volumen": round(ges["v"]),
            "bestleistungen": [{"uebung": r["uebung"], "einrm": round(r["b"], 1)} for r in c.execute(
                "SELECT uebung, MAX(CASE WHEN wdh>1 THEN kg*(1+wdh/30.0) ELSE kg END) AS b FROM satz WHERE nutzer=? GROUP BY uebung ORDER BY b DESC LIMIT 5", (z["id"],))]}


# ------------------------------------------------------------------ Routinen
def routinen(c, z) -> list[dict]:
    return [{"id": r["id"], "name": r["name"], "uebungen": json.loads(r["uebungen"])}
            for r in c.execute("SELECT * FROM routine WHERE nutzer=? ORDER BY id DESC", (z["id"],))]


def routine_neu(c, z, d: dict, text) -> dict:
    ue = [" ".join(str(u).split())[:40] for u in (d.get("uebungen") if isinstance(d.get("uebungen"), list) else []) if str(u).strip()]
    if not 1 <= len(ue) <= 30:
        raise WorkoutFehler(400, "Eine Routine braucht 1–30 Übungen.")
    if c.execute("SELECT COUNT(*) FROM routine WHERE nutzer=?", (z["id"],)).fetchone()[0] >= 30:
        raise WorkoutFehler(400, "Du hast schon 30 Routinen – lösche eine alte.")
    cur = c.execute("INSERT INTO routine(nutzer, name, uebungen, erstellt) VALUES (?,?,?,?)",
                    (z["id"], text(d.get("name"), "Name", 1, 50), json.dumps(ue, ensure_ascii=False), db.jetzt()))
    return {"id": cur.lastrowid}


def routine_loeschen(c, z, rid: int) -> dict:
    c.execute("DELETE FROM routine WHERE id=? AND nutzer=?", (rid, z["id"]))
    return {"text": "Routine gelöscht."}
