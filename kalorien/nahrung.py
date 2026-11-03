"""Kalorien-App - Rechnen (Tagesziel) und Barcode-Suche (Open Food Facts, frei, ohne Schluessel)."""
from __future__ import annotations

import json
import re
import urllib.request

OFF = "https://world.openfoodfacts.org/api/v2/product/{code}.json?fields=product_name,brands,quantity,serving_size,nutriments"
AKTIV = {"wenig": 1.2, "leicht": 1.375, "mittel": 1.55, "viel": 1.725}
ZIEL = {"abnehmen": -400, "halten": 0, "zunehmen": 300}


def ziele_berechnen(geschlecht: str, alter: int, groesse_cm: float, gewicht_kg: float, aktivitaet: str = "leicht",
                    ziel: str = "halten") -> dict:
    """Mifflin-St-Jeor. Gibt Kalorien und Naehrstoff-Ziele zurueck (Richtwert, kein Ersatz fuer Beratung)."""
    if not (10 <= alter <= 100 and 120 <= groesse_cm <= 230 and 30 <= gewicht_kg <= 300):
        raise ValueError("Bitte Alter, Größe und Gewicht prüfen.")
    grund = 10 * gewicht_kg + 6.25 * groesse_cm - 5 * alter + (5 if geschlecht == "m" else -161)
    kcal = max(1200, round(grund * AKTIV.get(aktivitaet, 1.375) + ZIEL.get(ziel, 0)))
    eiweiss = round(gewicht_kg * (1.8 if ziel == "abnehmen" else 1.6 if ziel == "zunehmen" else 1.4))
    fett = round(kcal * 0.28 / 9)
    kh = max(0, round((kcal - eiweiss * 4 - fett * 9) / 4))
    return {"ziel_kcal": kcal, "ziel_eiweiss": eiweiss, "ziel_kh": kh, "ziel_fett": fett}


def barcode_suchen(code: str, timeout: float = 10) -> dict | None:
    """-> {name, marke, menge, pro100: {kcal, eiweiss, kh, fett}, portion_g} oder None, wenn unbekannt."""
    code = re.sub(r"\D", "", code or "")
    if not 6 <= len(code) <= 14:
        raise ValueError("Das ist kein gültiger Barcode.")
    anfrage = urllib.request.Request(OFF.format(code=code), headers={"User-Agent": "KalorienApp/1.0 (kontakt: siehe Betreiber)"})
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as r:
            daten = json.loads(r.read().decode("utf-8", "replace"))
    except (OSError, ValueError):
        raise RuntimeError("Die Produktdatenbank antwortet gerade nicht.")
    p = daten.get("product") if daten.get("status") == 1 else None
    if not p:
        return None
    n = p.get("nutriments") or {}

    def zahl(k: str) -> float:
        try:
            return round(float(n.get(k) or 0), 1)
        except (TypeError, ValueError):
            return 0.0
    kcal = zahl("energy-kcal_100g") or round(zahl("energy_100g") / 4.184, 1)
    portion = re.search(r"(\d+(?:[.,]\d+)?)\s*g", p.get("serving_size") or "")
    return {"code": code, "name": (p.get("product_name") or "Unbekanntes Produkt").strip()[:120],
            "marke": (p.get("brands") or "").split(",")[0].strip()[:60], "menge": (p.get("quantity") or "")[:40],
            "pro100": {"kcal": kcal, "eiweiss": zahl("proteins_100g"), "kh": zahl("carbohydrates_100g"), "fett": zahl("fat_100g")},
            "portion_g": float(portion.group(1).replace(",", ".")) if portion else None}
