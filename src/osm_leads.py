"""
Klaus - Lead-Suche ueber OpenStreetMap (kostenlos, ohne API-Schluessel)

Findet Betriebe ohne eingetragene Website, ergaenzt fehlende Adressen (Nominatim) und laesst
Claude per Websuche gegenpruefen, ob es wirklich keine Website gibt. Bestaetigte Treffer
landen in data/leads.csv - dieselbe Liste, aus der src/briefe.py die Briefe macht.

Nutzung:
    .venv/Scripts/python src/osm_leads.py --branchen "schreiner, maler, bar" --ort Göppingen --radius 12
    .venv/Scripts/python src/osm_leads.py --branchen handwerk --ohne-pruefung      # ohne Claude-Gegenpruefung

Datenquelle: (c) OpenStreetMap-Mitwirkende, ODbL. Fair-Use: wenige Abfragen, Nominatim max. 1 pro Sekunde.
"""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
LEADS_PATH = BASE_DIR / "data" / "leads.csv"
SPALTEN = ["name", "adresse", "telefon", "bewertung", "anzahl_bewertungen", "maps_link", "branche_suchbegriff", "quelle"]
UA = {"User-Agent": f"Klaus-Leadsuche/1.0 ({os.getenv('KLESRO_ABSENDER_MAIL', 'kontakt@example.com')})"}
# Oeffentliche Overpass-Server sind manchmal ueberlastet (504) -> der Reihe nach probieren
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]

# Gesprochenes Wort -> OpenStreetMap-Filter
BRANCHEN = {
    "handwerk": '["craft"]',
    "schreiner": '["craft"~"^(carpenter|joiner|cabinet_maker)$"]', "tischler": '["craft"~"^(carpenter|joiner|cabinet_maker)$"]',
    "maler": '["craft"~"^(painter|plasterer)$"]', "elektriker": '["craft"="electrician"]',
    "sanitaer": '["craft"~"^(plumber|hvac|heating_engineer)$"]', "installateur": '["craft"~"^(plumber|hvac|heating_engineer)$"]',
    "dachdecker": '["craft"="roofer"]', "metallbau": '["craft"~"^(metal_construction|blacksmith)$"]',
    "garten": '["craft"="gardener"]', "fliesen": '["craft"="tiler"]', "schlosser": '["craft"="locksmith"]',
    "bar": '["amenity"~"^(bar|pub)$"]', "kneipe": '["amenity"~"^(bar|pub)$"]', "cafe": '["amenity"="cafe"]',
    "restaurant": '["amenity"="restaurant"]', "imbiss": '["amenity"="fast_food"]',
    "friseur": '["shop"="hairdresser"]', "kosmetik": '["shop"~"^(beauty|cosmetics)$"]', "nagelstudio": '["shop"="beauty"]',
    "fahrrad": '["shop"="bicycle"]', "metzgerei": '["shop"="butcher"]', "baeckerei": '["shop"="bakery"]',
    "autowerkstatt": '["shop"="car_repair"]', "blumen": '["shop"="florist"]', "physio": '["healthcare"="physiotherapist"]',
    "fitness": '["leisure"="fitness_centre"]', "fotograf": '["craft"="photographer"]', "tattoo": '["shop"="tattoo"]',
}
OHNE_WEBSITE = ("website", "contact:website", "url", "brand:website")
# OpenStreetMap-Art -> deutsches Wort (der Brief-Generator waehlt daran Farben und Leistungen)
ART_DE = {"carpenter": "Schreiner", "joiner": "Schreiner", "cabinet_maker": "Schreiner", "painter": "Maler",
          "plasterer": "Maler", "electrician": "Elektriker", "plumber": "Sanitär", "hvac": "Heizung & Sanitär",
          "heating_engineer": "Heizung & Sanitär", "roofer": "Dachdecker", "metal_construction": "Metallbau",
          "blacksmith": "Schmiede", "gardener": "Garten- und Landschaftsbau", "tiler": "Fliesenleger",
          "locksmith": "Schlüsseldienst", "photographer": "Fotograf", "bar": "Bar", "pub": "Kneipe", "cafe": "Café",
          "restaurant": "Restaurant", "fast_food": "Imbiss", "hairdresser": "Friseur", "beauty": "Kosmetikstudio",
          "cosmetics": "Kosmetik", "bicycle": "Fahrradladen", "butcher": "Metzgerei", "bakery": "Bäckerei",
          "car_repair": "Autowerkstatt", "florist": "Blumenladen", "physiotherapist": "Physiotherapie",
          "fitness_centre": "Fitnessstudio", "tattoo": "Tattoostudio"}


def _norm(text: str) -> str:
    return text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss").strip()


def filter_fuer(wort: str) -> tuple[str, str] | None:
    """"Schreinereien" -> ("schreiner", OSM-Filter)"""
    w = _norm(wort)
    for schluessel, osm in BRANCHEN.items():
        if w.startswith(schluessel) or schluessel.startswith(w[:5]):
            return schluessel, osm
    return None


def koordinaten(ort: str) -> tuple[float, float, str]:
    r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                     params={"name": ort, "count": 1, "language": "de", "countryCode": "DE"}, timeout=15)
    r.raise_for_status()
    treffer = (r.json().get("results") or [None])[0]
    if not treffer:
        raise ValueError(f"Ort nicht gefunden: {ort}")
    return treffer["latitude"], treffer["longitude"], treffer["name"]


def _adresse(tags: dict) -> str:
    strasse = f"{tags.get('addr:street', '')} {tags.get('addr:housenumber', '')}".strip()
    ort = f"{tags.get('addr:postcode', '')} {tags.get('addr:city', '')}".strip()
    return ", ".join(t for t in (strasse, ort) if t)


def _adresse_nachschlagen(lat: float, lon: float) -> str:
    """Nominatim (OpenStreetMap): Koordinaten -> Anschrift. Hoechstens 1 Anfrage pro Sekunde."""
    time.sleep(1.1)
    r = requests.get("https://nominatim.openstreetmap.org/reverse",
                     params={"lat": lat, "lon": lon, "format": "jsonv2", "addressdetails": 1}, headers=UA, timeout=15)
    if r.status_code != 200:
        return ""
    a = r.json().get("address", {})
    strasse = f"{a.get('road', '')} {a.get('house_number', '')}".strip()
    ort = f"{a.get('postcode', '')} {a.get('city') or a.get('town') or a.get('village') or ''}".strip()
    return ", ".join(t for t in (strasse, ort) if t) if a.get("house_number") else ""


def _overpass(abfrage: str) -> list[dict]:
    fehler = None
    for versuch in range(2):
        for server in OVERPASS:
            try:
                r = requests.post(server, data={"data": abfrage}, headers=UA, timeout=120)
                if r.status_code == 200:
                    return r.json()["elements"]
                fehler = f"{server}: {r.status_code}"
            except requests.RequestException as e:
                fehler = f"{server}: {e}"
        time.sleep(5)
    raise RuntimeError(f"OpenStreetMap gerade nicht erreichbar ({fehler})")


def suche(branchen: list[str], ort: str, radius_km: float = 12, max_adressen: int = 40) -> list[dict]:
    lat, lon, ortname = koordinaten(ort)
    filter_ = [f for f in (filter_fuer(b) for b in branchen) if f]
    if not filter_:
        raise ValueError(f"Keine bekannte Branche in: {', '.join(branchen)}")
    teile = "".join(f'nwr{osm}["name"](around:{int(radius_km * 1000)},{lat},{lon});' for _, osm in filter_)
    elemente = _overpass(f"[out:json][timeout:90];({teile});out center tags;")
    leads, nachgeschlagen = [], 0
    for e in elemente:
        tags = e.get("tags", {})
        if any(k in tags for k in OHNE_WEBSITE):
            continue
        adresse = _adresse(tags)
        if not adresse.count(",") and nachgeschlagen < max_adressen:  # Strasse oder Ort fehlt
            mitte = e.get("center") or e
            adresse = _adresse_nachschlagen(mitte["lat"], mitte["lon"]) or adresse
            nachgeschlagen += 1
        if not re.search(r"\d{5}", adresse):
            continue  # ohne vollstaendige Anschrift kein Brief moeglich
        art = tags.get("craft") or tags.get("amenity") or tags.get("shop") or tags.get("healthcare") or tags.get("leisure", "")
        leads.append({
            "name": tags["name"], "adresse": adresse, "telefon": tags.get("phone") or tags.get("contact:phone", ""),
            "bewertung": "", "anzahl_bewertungen": "",
            "maps_link": f"https://www.openstreetmap.org/{e['type']}/{e['id']}",
            "branche_suchbegriff": f"{ART_DE.get(art, art.replace('_', ' ').title())} {ortname}".strip(), "quelle": "osm",
        })
    print(f"OpenStreetMap: {len(leads)} Betriebe ohne eingetragene Website mit vollstaendiger Adresse ({nachgeschlagen} Adressen nachgeschlagen)")
    return leads


def websites_pruefen(leads: list[dict], gruppe: int = 10, claude: bool = False) -> list[dict]:
    """Bleiben nur Betriebe ohne eigene Website. Kostenlos (Domains raten + Tavily/Gemini).
    Was ohne Websuche unklar bleibt, prueft Claude nur mit claude=True - sonst bleibt es mit Hinweis drin."""
    import recherche
    ohne, unklar = [], []
    for lead in leads:
        website, sicher = recherche.hat_website(lead["name"], lead["adresse"])
        if website:
            print(f"  - {lead['name']}: hat eine Website ({website})")
        elif sicher:
            ohne.append(lead)
        else:
            unklar.append(lead)
    if unklar and claude:
        print(f"  {len(unklar)} ohne Websuche nicht pruefbar - frage Claude.")
        ohne += _claude_pruefen(unklar, gruppe)
    elif unklar:
        print(f"  {len(unklar)} nicht pruefbar (Websuche ging nicht) - vor dem Versand kurz googeln.")
        ohne += unklar
    return ohne


def _claude_pruefen(leads: list[dict], gruppe: int = 10) -> list[dict]:
    """Claude sucht fuer je 10 Betriebe im Web nach Website und korrigiert die Adresse."""
    claude = shutil.which("claude")
    if not claude:
        print("  Claude nicht gefunden - unklare Betriebe verworfen (TAVILY_API_KEY in die .env eintragen).")
        return []
    ohne = []
    for i in range(0, len(leads), gruppe):
        stueck = leads[i : i + gruppe]
        liste = "\n".join(f"{n + 1}. {l['name']}, {l['adresse']}" for n, l in enumerate(stueck))
        auftrag = (f"Pruefe per Websuche fuer jeden dieser Betriebe, ob er eine EIGENE Website hat (nicht Facebook, "
                   f"Instagram, Branchenbuecher oder Bewertungsportale), und nenne seine echte Postadresse:\n{liste}\n\n"
                   'Antworte NUR mit JSON: [{"nr": 1, "website": "https://... oder null", '
                   '"adresse": "Strasse Nr, PLZ Ort oder null"}, ...]')
        ergebnis = subprocess.run([claude, "-p", auftrag, "--model", "sonnet", "--allowedTools", "WebSearch"],
                                  capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        treffer = re.search(r"\[.*\]", ergebnis.stdout, re.S)
        try:
            antworten = {a["nr"]: a for a in json.loads(treffer.group(0))} if treffer else {}
        except (json.JSONDecodeError, KeyError, TypeError):
            antworten = {}
        for n, lead in enumerate(stueck, 1):
            antwort = antworten.get(n)
            if not antwort:
                print(f"  ? {lead['name']}: keine Antwort - sicherheitshalber verworfen")
            elif antwort.get("website"):
                print(f"  - {lead['name']}: hat doch eine Website ({antwort['website']})")
            else:
                neu = antwort.get("adresse") or ""
                if re.search(r"\b\d{5}\b", neu) and _norm(neu) != _norm(lead["adresse"]):
                    print(f"  ~ {lead['name']}: Adresse korrigiert ({lead['adresse']} -> {neu})")
                    lead["adresse"] = neu
                ohne.append(lead)
        print(f"  Gruppe {i // gruppe + 1}: {len(ohne)} bestaetigt bisher")
    return ohne


def speichern(leads: list[dict]) -> int:
    """Haengt neue Leads an data/leads.csv an (keine Doppelten). Gibt die Zahl neuer Eintraege zurueck."""
    vorhanden = []
    if LEADS_PATH.exists():
        with open(LEADS_PATH, newline="", encoding="utf-8") as f:
            vorhanden = list(csv.DictReader(f))
    bekannt = {(_norm(l["name"]), _norm(l.get("adresse", ""))[:20]) for l in vorhanden}
    neu = [l for l in leads if (_norm(l["name"]), _norm(l["adresse"])[:20]) not in bekannt]
    with open(LEADS_PATH, "w", newline="", encoding="utf-8") as f:
        schreiber = csv.DictWriter(f, fieldnames=SPALTEN, extrasaction="ignore")
        schreiber.writeheader()
        for zeile in vorhanden + neu:
            schreiber.writerow({k: zeile.get(k, "") for k in SPALTEN})
    return len(neu)


def suchen_und_speichern(branchen: list[str], ort: str, radius_km: float = 12, pruefen: bool = True) -> str:
    """Fuer Klaus: alles in einem Schritt, Rueckgabe ist ein Satz zum Vorlesen."""
    leads = suche(branchen, ort, radius_km)
    if pruefen and leads:
        leads = websites_pruefen(leads)
    neu = speichern(leads)
    namen = ", ".join(l["name"] for l in leads[:5])
    return (f"{len(leads)} Betriebe ohne Website gefunden, {neu} davon neu in der Lead-Liste."
            + (f" Zum Beispiel: {namen}." if namen else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branchen", default="handwerk", help='kommagetrennt, z. B. "schreiner, maler, bar"')
    ap.add_argument("--ort", default=os.getenv("KLAUS_ORT", "Göppingen").split(",")[0])
    ap.add_argument("--radius", type=float, default=12, help="Umkreis in km")
    ap.add_argument("--ohne-pruefung", action="store_true", help="Claude-Gegenpruefung auslassen")
    args = ap.parse_args()
    print(suchen_und_speichern([b.strip() for b in args.branchen.split(",") if b.strip()], args.ort, args.radius,
                               pruefen=not args.ohne_pruefung))


if __name__ == "__main__":
    main()
