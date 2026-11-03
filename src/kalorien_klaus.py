"""
Klaus <-> Kalorien-App (kalorien/, laeuft auch ohne Klaus). Klaus ist hier nur ein Kunde der App-Schnittstelle:

    Telegram /kalorien            Tageswerte (Rest-Kalorien, Eiweiss ...)
    Telegram /essen 2 Eier, Toast  schaetzt per KI der App und traegt ein
    Telegram /essen_weg           nimmt den letzten /essen-Eintrag wieder raus
    Telegram Foto + "Essen"       Foto schaetzen lassen und eintragen (Foto bleibt nicht gespeichert)

Einrichten: in der App unter Ich -> Schnittstelle einen Schluessel (kt_...) erstellen, dann in Klaus
Einstellungen -> Kalorien-App eintragen (KALORIEN_URL + KALORIEN_TOKEN). Der Schluessel wird nie an eine KI geschickt.
"""
from __future__ import annotations

import base64
import os
import re

import requests

MAHLZEITEN = {"fruehstueck": "Frühstück", "mittag": "Mittag", "abend": "Abend", "snack": "Snack"}
_letzte: list[int] = []


def adresse() -> str:
    return (os.getenv("KALORIEN_URL") or "http://127.0.0.1:7730").strip().rstrip("/")


def bereit() -> bool:
    return bool(os.getenv("KALORIEN_TOKEN", "").strip())


def _api(methode: str, pfad: str, daten: dict | None = None, timeout: float = 90):
    r = requests.request(methode, f"{adresse()}/api/{pfad}", json=daten, timeout=timeout,
                         headers={"Authorization": f"Bearer {os.environ.get('KALORIEN_TOKEN', '').strip()}"})
    try:
        d = r.json()
    except ValueError:
        d = {}
    if r.status_code == 401:
        raise RuntimeError("Der Schlüssel der Kalorien-App stimmt nicht (mehr). Neu erstellen: App → Ich → Schnittstelle.")
    if not r.ok:
        raise RuntimeError(d.get("fehler") or f"Kalorien-App antwortet mit {r.status_code}")
    return d


def _fehler(e: Exception) -> str:
    if isinstance(e, requests.RequestException):
        return "Die Kalorien-App ist gerade nicht erreichbar."
    return str(e)


def tag_text() -> str:
    t = _api("GET", "tag")
    s, z = t["summe"], t["ziele"]
    rest = round(z["kcal"] - s["kcal"])
    kopf = f"🥗 Heute: {round(s['kcal'])} von {z['kcal']} kcal – " + (f"noch {rest} übrig" if rest >= 0 else f"{-rest} drüber")
    zeilen = [kopf, f"Eiweiß {round(s['eiweiss'])}/{z['eiweiss']} g · Kohlenhydrate {round(s['kh'])}/{z['kh']} g · Fett {round(s['fett'])}/{z['fett']} g"]
    for e in t["eintraege"][-12:]:
        zeilen.append(f"• {e['name']} ({e['menge']}) {round(e['kcal'])} kcal" if e["menge"] else f"• {e['name']} {round(e['kcal'])} kcal")
    return "\n".join(zeilen)


def _eintragen(gerichte: list[dict], quelle: str) -> list[int]:
    ids = []
    for g in gerichte:
        ids.append(_api("POST", "eintrag", {**g, "quelle": quelle})["id"])
    return ids


def _bericht(gerichte: list[dict], hinweis: str) -> str:
    zeilen = ["✅ Eingetragen:"] + [f"• {g['name']} ({g['menge']}) – {round(g['kcal'])} kcal, E {round(g['eiweiss'])} · K {round(g['kh'])} · F {round(g['fett'])}" for g in gerichte]
    zeilen.append(f"Zusammen {round(sum(g['kcal'] for g in gerichte))} kcal." + (f" {hinweis}" if hinweis else ""))
    zeilen.append("Falsch geschätzt? /essen_weg nimmt es raus – dann schreib es genauer.")
    return "\n".join(zeilen) + "\n\n" + tag_text().split("\n")[0]


def essen(text: str) -> str:
    beschreibung = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
    if not beschreibung:
        return "Schreib dazu, was du gegessen hast: /essen 2 Eier mit Toast und Butter"
    try:
        r = _api("POST", "schaetzen/text", {"text": beschreibung})
        if not r["gerichte"]:
            return "Dazu konnte ich nichts schätzen. Schreib es etwas genauer."
        _letzte[:] = _eintragen(r["gerichte"], "klaus")
        return _bericht(r["gerichte"], r.get("hinweis", ""))
    except Exception as e:
        return "⚠️ " + _fehler(e)


def essen_weg(_text: str = "") -> str:
    if not _letzte:
        return "Es gibt nichts Frisches zum Zurücknehmen. Einzelne Einträge löschst du in der App (×)."
    try:
        for i in _letzte:
            _api("DELETE", f"eintrag/{i}")
        n, _letzte[:] = len(_letzte), []
        return f"↩️ {n} Eintrag/Einträge zurückgenommen.\n" + tag_text().split("\n")[0]
    except Exception as e:
        return "⚠️ " + _fehler(e)


def kalorien(_text: str = "") -> str:
    if not bereit():
        return ("Die Kalorien-App ist noch nicht verbunden. In der App unter Ich → Schnittstelle einen Schlüssel erstellen und in "
                "Klaus unter Einstellungen → Kalorien-App eintragen.")
    try:
        return tag_text()
    except Exception as e:
        return "⚠️ " + _fehler(e)


def ist_essensfoto(beschriftung: str) -> bool:
    return bereit() and bool(re.match(r"\s*(essen|kalorien|kcal|mahlzeit|food|mampf)\b", beschriftung or "", re.I))


def foto(bild: bytes, beschriftung: str) -> str:
    hinweis = re.sub(r"^\s*(essen|kalorien|kcal|mahlzeit|food|mampf)\b[:,\- ]*", "", beschriftung, flags=re.I).strip()
    try:
        r = _api("POST", "schaetzen/bild", {"bild": base64.b64encode(bild).decode(), "mime": "image/jpeg", "hinweis": hinweis})
        if not r["gerichte"]:
            return "Auf dem Foto erkenne ich nichts Essbares. Schick ein näheres Bild."
        _letzte[:] = _eintragen(r["gerichte"], "foto")
        return _bericht(r["gerichte"], r.get("hinweis", ""))
    except Exception as e:
        return "⚠️ " + _fehler(e)


def befehle_einrichten(tg) -> None:
    tg.befehle["/kalorien"] = kalorien
    tg.befehle["/essen"] = lambda t: essen(t) if bereit() else kalorien()
    tg.befehle["/essen_weg"] = essen_weg
    tg.befehle["/fit_registrierung"] = registrierung


def registrierung(text: str) -> str:
    """/fit_registrierung an|aus  (nur Nikola, nur im Haupt-Klaus; wirkt sofort, ohne Neustart der App)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from kalorien import schalter
    teile = text.split()
    wunsch = teile[1].lower() if len(teile) > 1 else ""
    if wunsch in ("an", "auf", "offen", "ein"):
        schalter.setzen(True)
    elif wunsch in ("aus", "zu", "geschlossen"):
        schalter.setzen(False)
    elif wunsch:
        return "Schreib: /fit_registrierung an  oder  /fit_registrierung aus"
    return (f"Registrierung der Kalorien-App ist jetzt {'🟢 OFFEN' if schalter.offen() else '🔴 GESCHLOSSEN'} "
            f"(gilt über: {schalter.quelle()}). Umschalten: /fit_registrierung an|aus")
