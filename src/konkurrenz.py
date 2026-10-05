"""
Klaus - Konkurrenz-Check fuer einen Lead: Mitbewerber -> Reibungspunkte -> Strategie (kostenlos, ohne KI, OpenStreetMap).

    konkurrenz.analyse(lead)   lead = Zeile aus data/leads.csv (name, branche_suchbegriff, lat, lon, maps_link)

Ergebnis fliesst in den Brief (briefe.py: belegbarer Satz "x von y Betrieben im Umkreis sind online") und ins Panel
(Holo-Fenster "strategie": Kreis fuellt sich Stufe fuer Stufe).
"""
from __future__ import annotations

import math
import re

import osm_leads

RADIUS_KM = 5
WEB = osm_leads.OHNE_WEBSITE + ("facebook", "contact:facebook", "contact:instagram")


def _osm_id(lead: dict) -> str:
    m = re.search(r"openstreetmap\.org/(node|way|relation)/(\d+)", lead.get("maps_link", ""))
    return f"{m.group(1)}/{m.group(2)}" if m else ""


def _filter(lead: dict) -> tuple[str, str] | None:
    for wort in re.findall(r"[A-Za-zÄÖÜäöüß]+", lead.get("branche_suchbegriff", "")):
        f = osm_leads.filter_fuer(wort)
        if f:
            return f
    return None


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    dy = (a[0] - b[0]) * 110.57
    dx = (a[1] - b[1]) * 111.32 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def analyse(lead: dict, radius_km: float = RADIUS_KM) -> dict:
    """-> {branche, radius_km, mitbewerber: [...], online, gesamt, reibung: [...], strategie: [...], briefsatz}"""
    try:
        lat, lon = float(lead["lat"]), float(lead["lon"])
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"Für {lead.get('name')} fehlen Koordinaten.")
    f = _filter(lead)
    if not f:
        raise ValueError(f"Branche von {lead.get('name')} unbekannt ({lead.get('branche_suchbegriff', '')}).")
    branche, osm = f
    # Rechteck statt around: fuer die (oft ueberlasteten) Overpass-Server viel billiger; den Kreis schneiden wir selbst
    dlat, dlon = radius_km / 110.57, radius_km / (111.32 * math.cos(math.radians(lat)))
    elemente = osm_leads._overpass(f'[out:json][timeout:40];nwr{osm}["name"]({lat - dlat:.5f},{lon - dlon:.5f},{lat + dlat:.5f},'
                                  f'{lon + dlon:.5f});out center tags;', timeout=45, runden=1)  # im Gespraech nicht minutenlang warten
    eigene_id, eigener_name = _osm_id(lead), osm_leads._norm(lead.get("name", ""))
    selbst, andere = {}, []
    for e in elemente:
        tags = e.get("tags", {})
        if f"{e['type']}/{e['id']}" == eigene_id or osm_leads._norm(tags.get("name", "")) == eigener_name:
            selbst = tags
            continue
        p = (e.get("lat") or e.get("center", {}).get("lat"), e.get("lon") or e.get("center", {}).get("lon"))
        if None in p or _km((lat, lon), p) > radius_km:
            continue
        andere.append({"name": tags["name"], "lat": p[0], "lon": p[1], "km": round(_km((lat, lon), p), 1),
                       "website": next((tags[k] for k in WEB if tags.get(k)), ""),
                       "zeiten": bool(tags.get("opening_hours"))})
    andere.sort(key=lambda m: m["km"])
    online = [m for m in andere if m["website"]]
    art = osm_leads.ART_DE.get(next(iter(re.findall(r'"([a-z_]+)"', osm)[-1:]), ""), branche.capitalize())

    reibung = []
    if andere:
        reibung.append(f"Keine eigene Website – {len(online)} von {len(andere)} Mitbewerbern im Umkreis von {radius_km:g} km sind online.")
    else:
        reibung.append(f"Keine eigene Website – im Umkreis von {radius_km:g} km gibt es kaum Konkurrenz, die Kunden suchen trotzdem online.")
    if not selbst.get("opening_hours"):
        reibung.append("Öffnungszeiten sind online nirgends hinterlegt.")
    if not (selbst.get("phone") or selbst.get("contact:phone")):
        reibung.append("Keine Telefonnummer öffentlich auffindbar.")
    naechste = online[:2]
    if naechste:
        reibung.append("Wer online sucht, landet zuerst bei " + " und ".join(f"{m['name']} ({m['km']:g} km)".replace('.', ',') for m in naechste) + ".")

    strategie = ["Eigene Website mit Leistungen, Referenzen und direktem Kontakt (mobil zuerst)."]
    ort = (re.search(r"\d{5}\s+(.+)$", lead.get("adresse", "")) or [None, ""])[1].strip()
    if naechste:
        suche = f"{art} {ort}".strip()
        strategie.append(f"Mit {naechste[0]['name']} gleichziehen: bei der Suche „{suche}“ selbst ganz oben stehen.")
    strategie.append("Google-Unternehmensprofil mit Öffnungszeiten, Fotos und Bewertungen pflegen.")
    if len(strategie) < 3:
        strategie.append("Lokale Suchbegriffe abdecken: Leistungen + Ort auf jeder Seite.")

    if andere and online:
        briefsatz = (f"Im Umkreis von {radius_km:g} km sind bereits {len(online)} von {len(andere)} vergleichbaren Betrieben "
                     f"mit einer eigenen Website online.")
    else:
        briefsatz = ""
    return {"name": lead.get("name", ""), "branche": art, "radius_km": radius_km, "mitte": [lat, lon], "mitbewerber": andere[:12],
            "online": len(online), "gesamt": len(andere), "reibung": reibung, "strategie": strategie[:4], "briefsatz": briefsatz}


if __name__ == "__main__":
    import csv
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    with open(osm_leads.LEADS_PATH, newline="", encoding="utf-8") as f:
        leads = [r for r in csv.DictReader(f)]
    ziel = next((l for l in leads if sys.argv[1:] and sys.argv[1].lower() in l["name"].lower()), leads[0])
    d = analyse(ziel)
    print(d["name"], "·", d["branche"], "·", d["online"], "/", d["gesamt"], "online")
    for r in d["reibung"]:
        print("  ✗", r)
    for s in d["strategie"]:
        print("  →", s)
    print("  Brief:", d["briefsatz"])
