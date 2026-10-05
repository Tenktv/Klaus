"""
Klaus - Lagebericht: Welt -> Deutschland -> Region Goeppingen -> Maerkte -> Kennzahlen (siehe web/lage.js).

Nachrichten werden ohne KI verortet: Orts- und Laendernamen in der Schlagzeile -> Koordinaten (Liste unten).
Region: Google-News-Suche nach dem Heimatort + deine Leads aus data/leads.csv.
Kennzahlen: Leads, Briefe, gedruckt, Projekte - "neu" = seit dem letzten Lagebericht (data/lage_stand.json).
"""
from __future__ import annotations

import csv
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import requests

import daten

STAND = daten.BASE_DIR / "data" / "lage_stand.json"

# Name in der Schlagzeile -> (lat, lon, ebene). Laengere Namen zuerst pruefen (z. B. "Bad Boll" vor "Boll").
WELT = {
    "USA": (39.8, -98.6), "US-": (39.8, -98.6), "Washington": (38.9, -77.0), "New York": (40.7, -74.0), "Kalifornien": (36.8, -119.4),
    "Kanada": (56.1, -106.3), "Mexiko": (23.6, -102.6), "Brasilien": (-14.2, -51.9), "Argentinien": (-38.4, -63.6), "Venezuela": (6.4, -66.6),
    "Kolumbien": (4.6, -74.3), "Chile": (-35.7, -71.5), "Peru": (-9.2, -75.0), "Kuba": (21.5, -77.8),
    "Großbritannien": (55.4, -3.4), "Grossbritannien": (55.4, -3.4), "London": (51.5, -0.1), "Irland": (53.1, -7.7),
    "Frankreich": (46.2, 2.2), "Paris": (48.9, 2.35), "Spanien": (40.5, -3.7), "Madrid": (40.4, -3.7), "Portugal": (39.4, -8.2),
    "Italien": (41.9, 12.6), "Rom": (41.9, 12.5), "Vatikan": (41.9, 12.45), "Schweiz": (46.8, 8.2), "Österreich": (47.5, 14.6),
    "Wien": (48.2, 16.4), "Niederlande": (52.1, 5.3), "Belgien": (50.5, 4.5), "Brüssel": (50.85, 4.35), "Dänemark": (56.3, 9.5),
    "Schweden": (60.1, 18.6), "Norwegen": (60.5, 8.5), "Finnland": (61.9, 25.7), "Polen": (51.9, 19.1), "Warschau": (52.2, 21.0),
    "Tschechien": (49.8, 15.5), "Ungarn": (47.2, 19.5), "Rumänien": (45.9, 24.97), "Griechenland": (39.1, 21.8), "Türkei": (38.96, 35.2),
    "Ukraine": (48.4, 31.2), "Kiew": (50.45, 30.5), "Russland": (61.5, 105.3), "Moskau": (55.75, 37.6), "Belarus": (53.7, 27.95),
    "Serbien": (44.0, 21.0), "Israel": (31.0, 34.85), "Gaza": (31.4, 34.4), "Libanon": (33.85, 35.9), "Syrien": (34.8, 38.99),
    "Iran": (32.4, 53.7), "Irak": (33.2, 43.7), "Saudi-Arabien": (23.9, 45.1), "Jemen": (15.55, 48.5), "Katar": (25.35, 51.2),
    "Ägypten": (26.8, 30.8), "Dubai": (25.2, 55.3), "Afghanistan": (33.9, 67.7), "Pakistan": (30.4, 69.3), "Indien": (20.6, 78.96),
    "China": (35.9, 104.2), "Peking": (39.9, 116.4), "Taiwan": (23.7, 121.0), "Hongkong": (22.3, 114.2), "Japan": (36.2, 138.3),
    "Tokio": (35.7, 139.7), "Korea": (36.5, 127.9), "Nordkorea": (40.3, 127.5), "Vietnam": (14.1, 108.3), "Thailand": (15.9, 100.99),
    "Indonesien": (-0.8, 113.9), "Philippinen": (12.9, 121.8), "Australien": (-25.3, 133.8), "Neuseeland": (-40.9, 174.9),
    "Südafrika": (-30.6, 22.9), "Nigeria": (9.1, 8.7), "Kenia": (-0.02, 37.9), "Äthiopien": (9.1, 40.5), "Sudan": (12.9, 30.2),
    "Mali": (17.6, -4.0), "Marokko": (31.8, -7.1), "Libyen": (26.3, 17.2), "Grönland": (71.7, -42.6), "Nahost": (31.5, 35.0),
    "Europa": (50.1, 9.7), "EU-": (50.85, 4.35), "Nato": (50.88, 4.42), "Kreml": (55.75, 37.6), "Weißes Haus": (38.9, -77.04),
}
DEUTSCHLAND = {
    "Berlin": (52.52, 13.4), "Hamburg": (53.55, 9.99), "München": (48.14, 11.58), "Köln": (50.94, 6.96), "Frankfurt": (50.11, 8.68),
    "Stuttgart": (48.78, 9.18), "Düsseldorf": (51.23, 6.77), "Leipzig": (51.34, 12.37), "Dresden": (51.05, 13.74), "Hannover": (52.37, 9.73),
    "Nürnberg": (49.45, 11.08), "Bremen": (53.08, 8.8), "Dortmund": (51.51, 7.47), "Essen": (51.46, 7.01), "Mannheim": (49.49, 8.47),
    "Karlsruhe": (49.01, 8.4), "Freiburg": (47.99, 7.84), "Ulm": (48.4, 9.99), "Augsburg": (48.37, 10.9), "Mainz": (49.99, 8.25),
    "Kiel": (54.32, 10.12), "Rostock": (54.09, 12.14), "Magdeburg": (52.12, 11.63), "Erfurt": (50.98, 11.03), "Potsdam": (52.39, 13.06),
    "Saarbrücken": (49.24, 7.0), "Wiesbaden": (50.08, 8.24), "Bonn": (50.74, 7.1), "Heidelberg": (49.4, 8.67), "Tübingen": (48.52, 9.06),
    "Bayern": (48.79, 11.5), "Sachsen-Anhalt": (51.95, 11.69), "Sachsen": (51.1, 13.2), "Thüringen": (50.9, 11.0), "Brandenburg": (52.4, 12.5),
    "Hessen": (50.65, 9.16), "Niedersachsen": (52.64, 9.85), "Nordrhein-Westfalen": (51.43, 7.66), "NRW": (51.43, 7.66),
    "Baden-Württemberg": (48.66, 9.35), "Rheinland-Pfalz": (50.12, 7.31), "Schleswig-Holstein": (54.22, 9.7),
    "Mecklenburg-Vorpommern": (53.61, 12.43), "Saarland": (49.4, 6.95),
}
# Schwache Hinweise auf Deutschland (Personen/Institutionen): erst nach den Laendern pruefen ("Ukraine ... Merz-Besuch" = Welt)
DEUTSCHLAND_SCHWACH = {
    "Bundestag": (52.52, 13.38), "Bundesregierung": (52.52, 13.37), "Merz": (52.52, 13.37), "Kanzler": (52.52, 13.37),
    "Bundeswehr": (52.51, 13.36), "Deutschland": (51.17, 10.45), "Bundes": (52.52, 13.38),
}
REGION = {
    "Göppingen": (48.7035, 9.6524), "Eislingen": (48.695, 9.7043), "Uhingen": (48.705, 9.59), "Salach": (48.6917, 9.735),
    "Süßen": (48.6797, 9.7586), "Donzdorf": (48.6856, 9.8108), "Geislingen": (48.6244, 9.8306), "Ebersbach": (48.7156, 9.5236),
    "Bad Boll": (48.6436, 9.6122), "Heiningen": (48.6639, 9.6497), "Deggingen": (48.5978, 9.7186), "Schorndorf": (48.8053, 9.5275),
    "Schwäbisch Gmünd": (48.7997, 9.7983), "Kirchheim": (48.6481, 9.4511), "Wäschenbeuren": (48.7594, 9.6886), "Esslingen": (48.74, 9.31),
    "Filstal": (48.69, 9.68), "Landkreis Göppingen": (48.7, 9.65), "Rechberghausen": (48.73, 9.64), "Faurndau": (48.71, 9.62),
}


def _finde(titel: str) -> tuple[float, float, str] | None:
    for ebene, tabelle in (("region", REGION), ("de", DEUTSCHLAND), ("welt", WELT), ("de", DEUTSCHLAND_SCHWACH)):
        for name in sorted(tabelle, key=len, reverse=True):
            if re.search(r"(?<![\wÄÖÜäöüß])" + re.escape(name), titel):
                lat, lon = tabelle[name]
                return lat, lon, ebene
    return None


def _google_suche(begriff: str, anzahl: int = 8) -> list[dict]:
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(begriff)}&hl=de&gl=DE&ceid=DE:de"
    try:
        r = requests.get(url, headers=daten.UA, timeout=10)
        r.raise_for_status()
        items = list(ET.fromstring(r.content).iter("item"))[:anzahl]
        return [{"titel": i.findtext("title", "").rsplit(" - ", 1)[0].strip(), "link": i.findtext("link", ""),
                 "alter": daten._alter(daten._zeit(i.findtext("pubDate")))} for i in items]
    except Exception as e:
        print(f"Lagebericht {begriff}: {e}")
        return []


def _leads() -> list[dict]:
    datei = daten.BASE_DIR / "data" / "leads.csv"
    if not datei.exists():
        return []
    with open(datei, newline="", encoding="utf-8") as f:
        aus = []
        for r in csv.DictReader(f):
            try:
                aus.append({"name": r["name"], "lat": float(r["lat"]), "lon": float(r["lon"])})
            except (KeyError, TypeError, ValueError):
                continue
        return aus


def _zahlen() -> dict:
    briefe = daten.BASE_DIR / "data" / "briefe"
    pdfs = list(briefe.glob("*/brief.pdf"))
    jetzt = {"leads": daten.leads()["leads"], "briefe": len(pdfs),
             "gedruckt": sum(1 for p in pdfs if (p.parent / ".gedruckt").exists()),
             "projekte": len(daten.projekte()["klaus"])}
    try:
        vorher = json.loads(STAND.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        vorher = jetzt
    STAND.write_text(json.dumps(jetzt), encoding="utf-8")
    return {**jetzt, "neu": {k: max(0, jetzt[k] - vorher.get(k, jetzt[k])) for k in jetzt}, "zu_drucken": len(pdfs) - jetzt["gedruckt"]}


def lagebericht() -> dict:
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_meld = pool.submit(daten._meldungen, 15)
        f_region = pool.submit(_google_suche, daten.ORT_NAME or "Göppingen")
        f_markt = pool.submit(daten.aktien, ",".join(daten.MARKT_BRIEFING[:6]))
        f_wetter = pool.submit(daten.wetter)
    meldungen = [m for m in f_meld.result() if not daten.KEINE_MELDUNG.search(m[1])]
    meldungen.sort(key=lambda m: m[3], reverse=True)
    punkte = {"welt": [], "de": [], "region": []}
    gesehen = set()
    for quelle, titel, link, zeit, _ in meldungen:
        if titel in gesehen:
            continue
        gesehen.add(titel)
        ort = _finde(titel)
        if ort:
            punkte[ort[2]].append({"titel": titel, "lat": ort[0], "lon": ort[1], "quelle": quelle, "link": link, "alter": daten._alter(zeit)})
    region_news = f_region.result()
    for n in region_news:
        ort = _finde(n["titel"]) or (48.7035, 9.6524, "region")
        punkte["region"].append({**n, "lat": ort[0], "lon": ort[1], "quelle": "google"})
    maerkte = [m for m in f_markt.result()["liste"] if not m.get("fehler")]
    zahlen = _zahlen()
    wetter = f_wetter.result()
    return {"welt": punkte["welt"][:12], "de": punkte["de"][:10], "region": punkte["region"][:8], "leads": _leads()[:120],
            "mitte": [float(daten.ORT_LAT or 48.7), float(daten.ORT_LON or 9.65)], "ort": daten.ORT_NAME or "Göppingen",
            "maerkte": maerkte, "zahlen": zahlen, "wetter": wetter, "text": sprechtext(punkte, maerkte, zahlen, wetter)}


def sprechtext(punkte: dict, maerkte: list, zahlen: dict, wetter: dict) -> dict:
    """Ein Satz pro Station - lage.js zeigt die Station, Klaus spricht dazu."""
    kurz = lambda t: t if len(t) < 110 else t[:107].rsplit(" ", 1)[0] + " …"
    welt = punkte["welt"][:2]
    t = {"welt": "Lagebericht. Weltweit: " + (" … ".join(kurz(p["titel"]) for p in welt) if welt else "nichts Auffälliges in den Schlagzeilen.")}
    de = punkte["de"][:2]
    t["de"] = "Deutschland: " + (" … ".join(kurz(p["titel"]) for p in de) if de else "keine großen Schlagzeilen.")
    reg = punkte["region"][:1]
    w = f" {wetter['temp']} Grad, {wetter['text']}." if wetter and not wetter.get("fehler") else ""
    t["region"] = f"Region {daten.ORT_NAME or 'Göppingen'}:{w} " + (kurz(reg[0]["titel"]) if reg else "keine Lokalmeldungen.")
    bewegt = sorted(maerkte, key=lambda m: abs(m.get("aenderung", 0)), reverse=True)[:3]
    t["maerkte"] = "Märkte: " + (", ".join(f"{daten.SPRECH_NAMEN.get(m['symbol'], m['name'])} {'plus' if m['aenderung'] >= 0 else 'minus'} "
                                          f"{abs(m['aenderung']):.1f} Prozent".replace(".", ",") for m in bewegt) if bewegt else "keine Kurse.")
    neu = zahlen["neu"]
    t["zahlen"] = (f"Bei dir: {zahlen['leads']} Leads" + (f", {neu['leads']} neu" if neu["leads"] else "")
                   + f", {zahlen['briefe']} Briefe, davon {zahlen['zu_drucken']} noch nicht gedruckt.")
    return t


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    d = lagebericht()
    print({k: len(v) if isinstance(v, list) else "" for k, v in d.items()})
    for k, v in d["text"].items():
        print(k, "->", v)
    for p in d["welt"][:5]:
        print("  welt:", p["titel"][:70])
    for p in d["de"][:5]:
        print("  de:", p["titel"][:70])
