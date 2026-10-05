"""
Klaus - Apple Kalender (iCloud) ueber CalDAV.

Einrichtung: appleid.apple.com -> Anmeldung und Sicherheit -> App-spezifische Passwoerter -> neues Passwort
"Klaus". In die .env:  APPLE_ID=deine@icloud.com  APPLE_APP_PASSWORT=xxxx-xxxx-xxxx-xxxx
Optional: KLAUS_KALENDER=Privat,Arbeit (nur diese Kalender lesen; leer = alle), KLAUS_KALENDER_NEU=Privat (Ziel fuer neue Termine)

    kalender.termine(von, bis)        Termine als Liste (lokale Zeit, sortiert)
    kalender.tag_text("morgen")       zum Vorlesen: "Morgen hast du 2 Termine: ..."
    kalender.anlegen(..., token)      neuer Termin - nur mit Freigabe-Token (Art "kalender")
    kalender.bald(15)                 Termine, die in den naechsten 15 Minuten beginnen (Erinnerung)

Bibliotheken: caldav (Apache-2.0 / GPL, wir nutzen Apache-2.0), icalendar (BSD).
"""
from __future__ import annotations

import datetime as dt
import os
import threading
import uuid
from pathlib import Path

from dotenv import load_dotenv

import freigabe

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

URL = os.getenv("KALENDER_URL", "https://caldav.icloud.com").strip()
APPLE_ID = os.getenv("APPLE_ID", "").strip()
PASSWORT = os.getenv("APPLE_APP_PASSWORT", "").strip()
NUR = [k.strip().lower() for k in os.getenv("KLAUS_KALENDER", "").split(",") if k.strip()]
ZIEL = os.getenv("KLAUS_KALENDER_NEU", "").strip().lower()

_sperre = threading.Lock()
_kalender_cache: list | None = None
WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


class KalenderFehler(RuntimeError):
    pass


def eingerichtet() -> bool:
    return bool(APPLE_ID and PASSWORT)


def _termine_moeglich(k) -> bool:
    """iCloud liefert auch die Erinnerungen-Liste (nur VTODO) als Kalender - die kann keine Termine."""
    try:
        return "VEVENT" in k.get_supported_components()
    except Exception:
        return True


def _kalender() -> list:
    """Alle (bzw. die ausgewaehlten) iCloud-Kalender, einmal geladen."""
    global _kalender_cache
    if not eingerichtet():
        raise KalenderFehler("Apple Kalender ist nicht eingerichtet (APPLE_ID und APPLE_APP_PASSWORT in der .env).")
    with _sperre:
        if _kalender_cache is None:
            import caldav

            try:
                alle = caldav.DAVClient(url=URL, username=APPLE_ID, password=PASSWORT, timeout=20).principal().calendars()
            except Exception as e:
                raise KalenderFehler(f"iCloud-Anmeldung fehlgeschlagen ({str(e)[:80]}). App-spezifisches Passwort prüfen.")
            _kalender_cache = [k for k in alle if (not NUR or (k.get_display_name() or "").lower() in NUR) and _termine_moeglich(k)]
        return _kalender_cache


def _lokal(wert) -> tuple[dt.datetime, bool]:
    """iCalendar-Datum/-Zeit -> (lokale naive Zeit, ganztaegig?)"""
    if isinstance(wert, dt.datetime):
        if wert.tzinfo:
            wert = wert.astimezone().replace(tzinfo=None)
        return wert, False
    return dt.datetime.combine(wert, dt.time()), True


def _termin(komponente, kalender_name: str) -> dict:
    start, ganztag = _lokal(komponente.get("dtstart").dt)
    if komponente.get("dtend"):
        ende, _ = _lokal(komponente.get("dtend").dt)
    elif komponente.get("duration"):
        ende = start + komponente.get("duration").dt
    else:
        ende = start + (dt.timedelta(days=1) if ganztag else dt.timedelta(hours=1))
    return {"titel": str(komponente.get("summary") or "(ohne Titel)"), "start": start, "ende": ende, "ganztag": ganztag,
            "ort": str(komponente.get("location") or ""), "kalender": kalender_name, "uid": str(komponente.get("uid") or "")}


def termine(von: dt.datetime, bis: dt.datetime) -> list[dict]:
    """Termine im Zeitraum (wiederkehrende Termine aufgeloest), nach Beginn sortiert."""
    aus = []
    for k in _kalender():
        name = k.get_display_name() or "Kalender"
        try:
            treffer = k.search(start=von, end=bis, event=True, expand=True)
        except Exception as e:
            print(f"[Kalender] {name}: {str(e)[:80]}")
            continue
        for ev in treffer:
            try:
                aus.append(_termin(ev.icalendar_component, name))
            except Exception as e:
                print(f"[Kalender] Termin nicht lesbar: {str(e)[:80]}")
    return sorted(aus, key=lambda t: (not t["ganztag"], t["start"]))


def tag(wann: str = "heute") -> tuple[dt.date, list[dict]]:
    """wann: heute | morgen | uebermorgen | Wochentag | TT.MM. -> (Datum, Termine)"""
    heute = dt.date.today()
    w = wann.strip().lower()
    if w in ("", "heute"):
        d = heute
    elif w == "morgen":
        d = heute + dt.timedelta(days=1)
    elif w in ("übermorgen", "uebermorgen"):
        d = heute + dt.timedelta(days=2)
    elif w.capitalize() in WOCHENTAGE:
        d = heute + dt.timedelta(days=(WOCHENTAGE.index(w.capitalize()) - heute.weekday()) % 7 or 7)
    else:
        try:
            t, m = [int(x) for x in w.strip(".").split(".")[:2]]
            d = dt.date(heute.year, m, t)
        except (ValueError, IndexError):
            d = heute
    start = dt.datetime.combine(d, dt.time())
    return d, termine(start, start + dt.timedelta(days=1))


def _uhrzeit(t: dict) -> str:
    return "ganztägig" if t["ganztag"] else f"um {t['start']:%H:%M}".replace(":00", " Uhr").replace(":", " Uhr ")


def tag_text(wann: str = "heute") -> str:
    d, liste = tag(wann)
    name = {0: "Heute", 1: "Morgen", 2: "Übermorgen"}.get((d - dt.date.today()).days, f"Am {WOCHENTAGE[d.weekday()]}, {d:%d.%m.},")
    if not liste:
        return f"{name} hast du keine Termine."
    # Ort zum Vorlesen: nur die Stadt ("Hauptstr. 12, 73033 Göppingen" -> "Göppingen")
    stadt = lambda ort: ort.split(",")[-1].strip().lstrip("0123456789 ").strip()
    teile = [f"{t['titel']} {_uhrzeit(t)}" + (f" in {stadt(t['ort'])}" if t["ort"] else "") for t in liste[:6]]
    return f"{name} hast du {len(liste)} Termin{'e' if len(liste) != 1 else ''}: " + "; ".join(teile) + "."


def woche() -> list[dict]:
    """Naechste 7 Tage fuers Widget (JSON-tauglich)."""
    start = dt.datetime.combine(dt.date.today(), dt.time())
    return [{**t, "start": t["start"].isoformat(), "ende": t["ende"].isoformat()} for t in termine(start, start + dt.timedelta(days=7))]


def bald(minuten: int = 15) -> list[dict]:
    jetzt = dt.datetime.now()
    return [t for t in termine(jetzt, jetzt + dt.timedelta(minutes=minuten)) if not t["ganztag"] and t["start"] >= jetzt]


def frei(von: dt.datetime, bis: dt.datetime) -> bool:
    return not [t for t in termine(von, bis) if not t["ganztag"]]


def anlegen(titel: str, start: dt.datetime, ende: dt.datetime | None, ort: str, token: str | None) -> str:
    """Neuer Termin im Ziel-Kalender (KLAUS_KALENDER_NEU, sonst der erste). Nur mit Freigabe."""
    freigabe.pruefe(token, "kalender")
    ende = ende or start + dt.timedelta(hours=1)
    kalender = _kalender()
    if not kalender:
        raise KalenderFehler("Kein Kalender gefunden.")
    ziel = next((k for k in kalender if (k.get_display_name() or "").lower() == ZIEL), kalender[0])
    ziel.save_event(dtstart=start.astimezone(), dtend=ende.astimezone(), summary=titel, location=ort or None, uid=str(uuid.uuid4()))
    return f"Eingetragen in „{ziel.get_display_name()}“: {titel} am {start:%d.%m.} {_uhrzeit({'ganztag': False, 'start': start})}."


def loeschen(uid: str, token: str | None) -> str:
    freigabe.pruefe(token, "kalender")
    for k in _kalender():
        try:
            ev = k.event_by_uid(uid)
        except Exception:
            continue
        titel = str(ev.icalendar_component.get("summary") or "")
        ev.delete()
        return f"Gelöscht: {titel}."
    return "Den Termin finde ich nicht."


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    print("eingerichtet:", eingerichtet())
    if eingerichtet():
        print([k.get_display_name() for k in _kalender()])
        print(tag_text("heute"))
        print(tag_text("morgen"))
