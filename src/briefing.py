"""
Klaus - Morgen-Briefing per Telegram (laeuft auf dem Server).

Jeden Morgen zur eingestellten Uhrzeit: Wetter, Termine von heute, wichtigste Nachrichten.
    /briefing          sofort schicken
    /briefing 7:30     Uhrzeit aendern
    /briefing aus|an   abschalten / wieder einschalten
Einstellung in data/briefing.json. Die Uhrzeit ist deutsche Zeit (Dienst laeuft mit TZ=Europe/Berlin).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATEI = BASE_DIR / "data" / "briefing.json"
WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def einstellung() -> dict:
    try:
        return {"zeit": "07:00", "an": True, "zuletzt": "", **json.loads(DATEI.read_text(encoding="utf-8"))}
    except Exception:
        return {"zeit": "07:00", "an": True, "zuletzt": ""}


def _speichern(e: dict) -> None:
    DATEI.parent.mkdir(exist_ok=True)
    DATEI.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")


def text() -> str:
    import daten
    import kalender

    heute = dt.date.today()
    stunde = dt.datetime.now().hour
    gruss = "☀️ Guten Morgen" if stunde < 11 else "👋 Hallo" if stunde < 18 else "🌙 Guten Abend"
    import identitaet
    teile = [identitaet.anpassen(f"{gruss}, Nikola! {WOCHENTAGE[heute.weekday()]}, {heute:%d.%m.}")]   # Tester: eigener Name
    w = daten.wetter()
    if "fehler" not in w and w.get("tage"):
        t = w["tage"][0]
        teile.append(f"{w['symbol']} {w['ort']}: jetzt {w['temp']}°, heute {t['tief']}–{t['hoch']}°, {w['text'].lower()}")
    if kalender.eingerichtet():
        try:
            _, termine = kalender.tag("heute")
            if termine:
                zeilen = [f"  {'ganztägig' if x['ganztag'] else x['start'].strftime('%H:%M')}  {x['titel']}" for x in termine[:10]]
                teile.append(f"📅 Heute ({len(termine)}):\n" + "\n".join(zeilen))
            else:
                teile.append("📅 Heute keine Termine.")
        except Exception as e:
            teile.append(f"📅 Kalender gerade nicht lesbar ({str(e)[:60]}).")
    try:
        import watchlist
        zeile = watchlist.briefing_block()
        if zeile:
            teile.append(zeile)
    except Exception as e:
        print(f"[Briefing] Watchlist: {e}", flush=True)
    try:
        # Sendungsnamen ("tagesthemen") sind keine Meldung: nur echte Schlagzeilen mit mindestens 4 Woertern
        meldungen = [m for m in daten.nachrichten(12)["liste"] if len(m["titel"].split()) >= 4][:5]
        if meldungen:
            teile.append("📰 Nachrichten:\n" + "\n".join(f"  • {m['titel']}" for m in meldungen))
    except Exception:
        pass
    return "\n\n".join(teile)


def befehl(eingabe: str) -> str:
    """/briefing [HH:MM | aus | an]"""
    e = einstellung()
    arg = eingabe.strip().split(maxsplit=1)[1].strip().lower() if len(eingabe.split()) > 1 else ""
    if not arg:
        return text()
    if arg in ("aus", "an"):
        e["an"] = arg == "an"
        _speichern(e)
        return f"Morgen-Briefing ist {'an, täglich um ' + e['zeit'] if e['an'] else 'aus'}."
    m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?(?:\s*uhr)?", arg)
    if not m or int(m.group(1)) > 23 or int(m.group(2) or 0) > 59:
        return "So geht's: /briefing (jetzt), /briefing 7:30 (Uhrzeit), /briefing aus oder /briefing an."
    e.update(zeit=f"{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}", an=True)
    _speichern(e)
    return f"Alles klar, das Morgen-Briefing kommt ab jetzt täglich um {e['zeit']} Uhr."


def schleife(senden) -> None:
    """Hintergrund: einmal pro Tag zur eingestellten Zeit (holt auch nach, wenn der Dienst um diese Zeit kurz neu startete)."""
    while True:
        try:
            e = einstellung()
            jetzt = dt.datetime.now()
            heute = jetzt.date().isoformat()
            stunde, minute = map(int, e["zeit"].split(":"))
            faellig = jetzt.replace(hour=stunde, minute=minute, second=0, microsecond=0)
            if e["an"] and e["zuletzt"] != heute and faellig <= jetzt < faellig + dt.timedelta(hours=2):
                senden(text())
                e["zuletzt"] = heute
                _speichern(e)
        except Exception as ex:
            print(f"[Briefing] {ex}", flush=True)
        time.sleep(30)


def starte(senden) -> None:
    threading.Thread(target=schleife, args=(senden,), daemon=True, name="klaus-briefing").start()
