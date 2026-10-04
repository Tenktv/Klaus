"""
Klaus - Lead-Recherche
Durchsucht Google Places (oder OpenWeb Ninja als Fallback) nach Firmen in
mehreren Branchen und Orten und speichert alle Treffer OHNE Website in
data/leads.csv.

Nutzung:
    python src/search_leads.py
"""

import csv
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

GOOGLE_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
NINJA_KEY = os.getenv("OPENWEB_NINJA_API_KEY", "").strip()

# Branchen, nach denen gesucht wird. Einfach ergänzen/kürzen.
BRANCHEN = [
    "Friseur",
    "Handwerker",
    "Restaurant",
    "Kfz Werkstatt",
    "Elektriker",
    "Sanitaer Heizung",
    "Baeckerei",
    "Metzgerei",
    "Kosmetikstudio",
    "Nagelstudio",
    "Gartenbau",
    "Malerbetrieb",
    "Schreiner",
    "Fitnessstudio",
    "Physiotherapie",
    "Zahnarzt",
    "Steuerberater",
    "Versicherungsmakler",
    "Tierarzt",
    "Fotograf",
    "Fahrradladen",
]

# Orte im Raum Göppingen. Einfach ergänzen/kürzen.
ORTE = [
    "Göppingen",
    "Eislingen/Fils",
    "Uhingen",
    "Geislingen an der Steige",
    "Süßen",
    "Salach",
    "Ebersbach an der Fils",
    "Rechberghausen",
    "Donzdorf",
    "Wangen bei Göppingen",
]

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "leads.csv"


def search_google_places(query: str) -> list[dict]:
    """Eine Textsuche gegen die Google Places API (New)."""
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.rating,places.userRatingCount,places.businessStatus,"
            "places.websiteUri,places.nationalPhoneNumber,places.googleMapsUri"
        ),
    }
    body = {"textQuery": query, "maxResultCount": 20}
    resp = requests.post(url, headers=headers, json=body, timeout=20)
    if resp.status_code != 200:
        print(f"  ! Fehler ({resp.status_code}) bei '{query}': {resp.text[:200]}")
        return []
    places = resp.json().get("places", [])
    rows = []
    for p in places:
        if p.get("businessStatus") not in (None, "OPERATIONAL"):
            continue
        if p.get("websiteUri"):
            continue  # hat schon eine Website -> kein Lead
        rows.append(
            {
                "name": p.get("displayName", {}).get("text", ""),
                "adresse": p.get("formattedAddress", ""),
                "telefon": p.get("nationalPhoneNumber", ""),
                "bewertung": p.get("rating", ""),
                "anzahl_bewertungen": p.get("userRatingCount", ""),
                "maps_link": p.get("googleMapsUri", ""),
                "branche_suchbegriff": query,
            }
        )
    return rows


def search_openweb_ninja(query: str) -> list[dict]:
    """Fallback über OpenWeb Ninja, falls kein Google-Key gesetzt ist."""
    url = "https://api.openwebninja.com/local-business-data/search"
    headers = {"X-API-Key": NINJA_KEY}
    params = {"query": query, "region": "de", "language": "de", "limit": "20"}
    for versuch in range(4):
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code != 429:
            break
        time.sleep(2 * (versuch + 1))  # Backoff bei Rate-Limit
    if resp.status_code != 200:
        print(f"  ! Fehler ({resp.status_code}) bei '{query}': {resp.text[:200]}")
        return []
    results = resp.json().get("data", [])
    rows = []
    for p in results:
        if p.get("website"):
            continue
        rows.append(
            {
                "name": p.get("name", ""),
                "adresse": p.get("full_address", ""),
                "telefon": p.get("phone_number", ""),
                "bewertung": p.get("rating", ""),
                "anzahl_bewertungen": p.get("review_count", ""),
                "maps_link": p.get("google_maps_link", ""),
                "branche_suchbegriff": query,
            }
        )
    return rows


def main() -> None:
    if not GOOGLE_KEY and not NINJA_KEY:
        print(
            "Kein API-Key gesetzt. Trage GOOGLE_PLACES_API_KEY oder "
            "OPENWEB_NINJA_API_KEY in .env ein (siehe .env.example)."
        )
        sys.exit(1)

    search_fn = search_google_places if GOOGLE_KEY else search_openweb_ninja
    anbieter = "Google Places" if GOOGLE_KEY else "OpenWeb Ninja"
    print(f"Nutze {anbieter} als Quelle.\n")

    alle_treffer: list[dict] = []
    gesehen: set[str] = set()

    for ort in ORTE:
        for branche in BRANCHEN:
            query = f"{branche} {ort}"
            print(f"Suche: {query}")
            treffer = search_fn(query)
            for row in treffer:
                schluessel = f"{row['name']}|{row['adresse']}"
                if schluessel in gesehen:
                    continue
                gesehen.add(schluessel)
                alle_treffer.append(row)
            time.sleep(1)  # Rate-Limit schonen

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "name",
                "adresse",
                "telefon",
                "bewertung",
                "anzahl_bewertungen",
                "maps_link",
                "branche_suchbegriff",
            ],
        )
        writer.writeheader()
        writer.writerows(alle_treffer)

    print(f"\nFertig: {len(alle_treffer)} Firmen ohne Website in {OUT_PATH} gespeichert.")


if __name__ == "__main__":
    main()
