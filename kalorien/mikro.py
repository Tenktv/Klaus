"""Kalorien-App - Mikronaehrstoffe: Ballaststoffe, Zucker, Salz, gesaettigte Fette, Vitamine und Mineralstoffe.

Quelle der Werte: grobe KI-Schaetzung (Foto/Text) oder Produktdaten von Open Food Facts (Barcode). Tagesziele sind vereinfachte
Richtwerte nach den EU-Naehrwertbezugswerten (Erwachsene) - keine medizinische Beratung. Gespeichert wird je Eintrag ein JSON {schluessel: menge}."""
from __future__ import annotations

import json
import math

# art "mind": Richtwert, den man erreichen soll | art "max": Obergrenze, die man nicht ueberschreiten soll
# off/faktor: Name bei Open Food Facts (Wert je 100 g, dort in Gramm) und Faktor in die Einheit hier (g -> mg: 1000, g -> ug: 1e6)
# max: Obergrenze fuer plausible Werte je Eintrag (Schutz vor Unsinn aus KI-Antworten)
KATALOG = [
    {"key": "ballaststoffe", "name": "Ballaststoffe", "einheit": "g", "ziel": 30, "art": "mind", "gruppe": "basis", "max": 300, "off": "fiber", "faktor": 1},
    {"key": "zucker", "name": "Zucker", "einheit": "g", "ziel": 50, "art": "max", "gruppe": "basis", "max": 1000, "off": "sugars", "faktor": 1},
    {"key": "salz", "name": "Salz", "einheit": "g", "ziel": 6, "art": "max", "gruppe": "basis", "max": 100, "off": "salt", "faktor": 1},
    {"key": "gesaettigt", "name": "Ges. Fettsäuren", "einheit": "g", "ziel": 20, "art": "max", "gruppe": "basis", "max": 300, "off": "saturated-fat", "faktor": 1},
    {"key": "vitamin_a", "name": "Vitamin A", "einheit": "µg", "ziel": 800, "art": "mind", "gruppe": "vitamin", "max": 60000, "off": "vitamin-a", "faktor": 1e6},
    {"key": "vitamin_d", "name": "Vitamin D", "einheit": "µg", "ziel": 5, "art": "mind", "gruppe": "vitamin", "max": 1000, "off": "vitamin-d", "faktor": 1e6},
    {"key": "vitamin_e", "name": "Vitamin E", "einheit": "mg", "ziel": 12, "art": "mind", "gruppe": "vitamin", "max": 500, "off": "vitamin-e", "faktor": 1000},
    {"key": "vitamin_k", "name": "Vitamin K", "einheit": "µg", "ziel": 75, "art": "mind", "gruppe": "vitamin", "max": 5000, "off": "vitamin-k", "faktor": 1e6},
    {"key": "vitamin_c", "name": "Vitamin C", "einheit": "mg", "ziel": 80, "art": "mind", "gruppe": "vitamin", "max": 5000, "off": "vitamin-c", "faktor": 1000},
    {"key": "vitamin_b1", "name": "Vitamin B1", "einheit": "mg", "ziel": 1.1, "art": "mind", "gruppe": "vitamin", "max": 100, "off": "vitamin-b1", "faktor": 1000},
    {"key": "vitamin_b2", "name": "Vitamin B2", "einheit": "mg", "ziel": 1.4, "art": "mind", "gruppe": "vitamin", "max": 100, "off": "vitamin-b2", "faktor": 1000},
    {"key": "niacin", "name": "Niacin (B3)", "einheit": "mg", "ziel": 16, "art": "mind", "gruppe": "vitamin", "max": 500, "off": "vitamin-pp", "faktor": 1000},
    {"key": "vitamin_b6", "name": "Vitamin B6", "einheit": "mg", "ziel": 1.4, "art": "mind", "gruppe": "vitamin", "max": 100, "off": "vitamin-b6", "faktor": 1000},
    {"key": "folat", "name": "Folat (B9)", "einheit": "µg", "ziel": 200, "art": "mind", "gruppe": "vitamin", "max": 5000, "off": "vitamin-b9", "faktor": 1e6},
    {"key": "vitamin_b12", "name": "Vitamin B12", "einheit": "µg", "ziel": 2.5, "art": "mind", "gruppe": "vitamin", "max": 1000, "off": "vitamin-b12", "faktor": 1e6},
    {"key": "calcium", "name": "Calcium", "einheit": "mg", "ziel": 800, "art": "mind", "gruppe": "mineral", "max": 6000, "off": "calcium", "faktor": 1000},
    {"key": "eisen", "name": "Eisen", "einheit": "mg", "ziel": 14, "art": "mind", "gruppe": "mineral", "max": 200, "off": "iron", "faktor": 1000},
    {"key": "magnesium", "name": "Magnesium", "einheit": "mg", "ziel": 375, "art": "mind", "gruppe": "mineral", "max": 3000, "off": "magnesium", "faktor": 1000},
    {"key": "kalium", "name": "Kalium", "einheit": "mg", "ziel": 2000, "art": "mind", "gruppe": "mineral", "max": 12000, "off": "potassium", "faktor": 1000},
    {"key": "zink", "name": "Zink", "einheit": "mg", "ziel": 10, "art": "mind", "gruppe": "mineral", "max": 200, "off": "zinc", "faktor": 1000},
]
_NACH_KEY = {k["key"]: k for k in KATALOG}


def katalog_oeffentlich() -> list[dict]:
    """Fuer die App: Name, Einheit, Tagesziel, Art, Gruppe (ohne die Umrechnungsdetails)."""
    return [{k: e[k] for k in ("key", "name", "einheit", "ziel", "art", "gruppe")} for e in KATALOG]


def fuer_ki() -> str:
    """Schluesselliste mit Einheiten fuer die KI-Anweisung."""
    return ", ".join(f"{e['key']} ({e['einheit']})" for e in KATALOG)


def _zahl(w):
    try:
        z = float(str(w).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return z if math.isfinite(z) else None


def bereinigen(d) -> dict:
    """Nur bekannte Schluessel, Zahlen im plausiblen Bereich (0 < Wert <= max), auf 2 Stellen gerundet. Alles andere faellt weg."""
    if not isinstance(d, dict):
        return {}
    aus = {}
    for key, e in _NACH_KEY.items():
        z = _zahl(d.get(key))
        if z is not None and 0 < z <= e["max"]:
            aus[key] = round(z, 2)
    return aus


def laden(text) -> dict:
    """JSON aus der Datenbank -> dict (kaputt oder leer -> {})."""
    if isinstance(text, dict):
        return bereinigen(text)
    try:
        return bereinigen(json.loads(text or "{}"))
    except (TypeError, ValueError):
        return {}


def summe(liste) -> dict:
    gesamt: dict = {}
    for m in liste:
        for k, v in bereinigen(m).items():
            gesamt[k] = round(gesamt.get(k, 0) + v, 2)
    return gesamt


def aus_off(nutriments: dict) -> dict:
    """Open Food Facts (Werte je 100 g, in Gramm) -> unsere Einheiten, je 100 g."""
    aus = {}
    for e in KATALOG:
        z = _zahl((nutriments or {}).get(e["off"] + "_100g"))
        if z is not None and z > 0:
            aus[e["key"]] = z * e["faktor"]
    return bereinigen({k: round(v, 3) for k, v in aus.items()})
