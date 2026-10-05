"""
Klaus - Daten fuers Desktop-Panel
Jede Funktion liefert JSON-faehige Daten und faengt eigene Fehler ab, damit ein
ausgefallener Dienst nie das ganze Panel leer laesst.

.env (optional):
    KLAUS_AKTIEN      Kuerzel, kommagetrennt (Yahoo-Schreibweise)
    KLAUS_FAVORITEN   App-Namen fuer die Schnellstart-Kacheln
    KLAUS_ORT         "Name,Breite,Laenge" fuers Wetter
"""

import csv
import datetime as dt
import email.utils
import json
import os
import re
import subprocess
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from dotenv import load_dotenv

import apps

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
PROJEKTE_DIR = BASE_DIR / "data" / "projekte"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Klaus/1.0"}

AKTIEN = [s.strip() for s in os.getenv("KLAUS_AKTIEN", "^GDAXI,NVDA,AAPL,MSFT,BTC-EUR").split(",") if s.strip()]
AKTIEN_NAMEN = {"^GDAXI": "DAX", "BTC-EUR": "Bitcoin", "^GSPC": "S&P 500", "^IXIC": "Nasdaq", "ETH-EUR": "Ethereum",
                "SOL-EUR": "Solana", "GC=F": "Gold", "CL=F": "Öl", "SI=F": "Silber", "EURUSD=X": "Euro/Dollar"}
# Zum Vorlesen: "Tesla" statt "TSLA"
SPRECH_NAMEN = {"NVDA": "Nvidia", "AAPL": "Apple", "TSLA": "Tesla", "MSFT": "Microsoft", "AMZN": "Amazon",
                "GOOGL": "Google", "META": "Meta", "SAP.DE": "SAP", **AKTIEN_NAMEN}
# Dauerformate, die keine Nachricht sind
KEINE_MELDUNG = re.compile(r"in 100 Sekunden|^Ticker:|Liveblog|Livestream|^Podcast|^Video:", re.I)
# Was "Seit du weg warst" vergleicht: Indizes, Tech, Krypto, Rohstoffe (wie bei coinvest/liquid.trade)
MARKT_BRIEFING = [s.strip() for s in os.getenv(
    "KLAUS_MARKT_BRIEFING", "^GDAXI,^GSPC,^IXIC,NVDA,AAPL,TSLA,MSFT,BTC-EUR,ETH-EUR,SOL-EUR,GC=F,CL=F",
).split(",") if s.strip()]
FAVORITEN = [s.strip() for s in os.getenv(
    "KLAUS_FAVORITEN",
    "Steam,Teamfight Tactics,Counter-Strike 2,League of Legends,Microsoft Edge,Spotify,Discord,Visual Studio Code",
).split(",") if s.strip()]
ORT_NAME, ORT_LAT, ORT_LON = (os.getenv("KLAUS_ORT", "Göppingen,48.70,9.65").split(",") + ["", "", ""])[:3]

NACHRICHTEN_QUELLEN = [
    ("tagesschau", "https://www.tagesschau.de/index~rss2.xml"),
    ("heise", "https://www.heise.de/rss/heise-atom.xml"),
    # Google News buendelt Hunderte Medien; die Top-Meldungen sind also das, worueber gerade viele berichten
    ("google", "https://news.google.com/rss?hl=de&gl=DE&ceid=DE:de"),
]

WETTER_CODES = {
    0: ("Klar", "☀️"), 1: ("Überwiegend klar", "🌤️"), 2: ("Teils bewölkt", "⛅"), 3: ("Bedeckt", "☁️"),
    45: ("Nebel", "☁️"), 48: ("Nebel", "☁️"), 51: ("Nieselregen", "🌦️"), 53: ("Nieselregen", "🌦️"),
    55: ("Nieselregen", "🌦️"), 61: ("Leichter Regen", "🌧️"), 63: ("Regen", "🌧️"), 65: ("Starker Regen", "🌧️"),
    71: ("Leichter Schnee", "🌨️"), 73: ("Schnee", "🌨️"), 75: ("Starker Schnee", "❄️"), 80: ("Schauer", "🌦️"),
    81: ("Schauer", "🌦️"), 82: ("Starke Schauer", "⛈️"), 95: ("Gewitter", "⛈️"), 96: ("Gewitter", "⛈️"),
    99: ("Gewitter", "⛈️"),
}


def wetter() -> dict:
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": ORT_LAT, "longitude": ORT_LON, "timezone": "Europe/Berlin",
                "current": "temperature_2m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                "forecast_days": 4,
            },
            timeout=10,
        )
        r.raise_for_status()
        d = r.json()
        text, symbol = WETTER_CODES.get(d["current"]["weather_code"], ("", "🌡️"))
        tage = []
        for datum, hoch, tief, code in zip(d["daily"]["time"], d["daily"]["temperature_2m_max"],
                                           d["daily"]["temperature_2m_min"], d["daily"]["weather_code"]):
            tag = dt.date.fromisoformat(datum)
            tage.append({"tag": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][tag.weekday()],
                         "hoch": round(hoch), "tief": round(tief), "symbol": WETTER_CODES.get(code, ("", "🌡️"))[1]})
        return {"ort": ORT_NAME, "temp": round(d["current"]["temperature_2m"]), "text": text,
                "symbol": symbol, "tage": tage}
    except Exception as e:
        return {"fehler": str(e)[:100]}


def _zeit(text: str | None) -> dt.datetime:
    if not text:
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    try:
        return email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return dt.datetime.min.replace(tzinfo=dt.timezone.utc)


def _meldungen(google_max: int = 12) -> list[tuple]:
    """Alle Meldungen als (quelle, titel, link, zeit, rang). rang = Position im Feed (bei Google = Wichtigkeit)."""
    eintraege = []
    atom = "{http://www.w3.org/2005/Atom}"

    def holen(quelle_url):
        try:
            r = requests.get(quelle_url[1], headers=UA, timeout=10)
            r.raise_for_status()
            return quelle_url[0], r.content
        except Exception as e:
            print(f"Nachrichten {quelle_url[0]}: {e}")
            return quelle_url[0], None

    with ThreadPoolExecutor(max_workers=len(NACHRICHTEN_QUELLEN)) as pool:
        antworten = list(pool.map(holen, NACHRICHTEN_QUELLEN))
    for quelle, inhalt in antworten:
        if inhalt is None:
            continue
        try:
            wurzel = ET.fromstring(inhalt)
            items = list(wurzel.iter("item"))[: google_max if quelle == "google" else None]
            for rang, item in enumerate(items):
                titel = item.findtext("title", "")
                if quelle == "google":  # "Titel - Quelle" -> nur Titel
                    titel = titel.rsplit(" - ", 1)[0]
                eintraege.append((quelle, titel.strip(), item.findtext("link", ""), _zeit(item.findtext("pubDate")), rang))
            for rang, item in enumerate(wurzel.iter(f"{atom}entry")):
                link = item.find(f"{atom}link")
                eintraege.append((quelle, item.findtext(f"{atom}title", "").strip(),
                                  link.get("href", "") if link is not None else "",
                                  _zeit(item.findtext(f"{atom}updated") or item.findtext(f"{atom}published")), rang))
        except Exception as e:
            print(f"Nachrichten {quelle}: {e}")
    return eintraege


def _alter(zeit: dt.datetime) -> str:
    if zeit.year <= 1:
        return ""
    minuten = int((dt.datetime.now(dt.timezone.utc) - zeit).total_seconds() // 60)
    return f"{minuten} min" if minuten < 60 else f"{minuten // 60} h"


def nachrichten(anzahl: int = 14) -> dict:
    eintraege = sorted((m for m in _meldungen(google_max=6) if not KEINE_MELDUNG.search(m[1])),
                       key=lambda e: e[3], reverse=True)
    return {"liste": [{"quelle": q, "titel": t, "link": l, "alter": _alter(z)} for q, t, l, z, _ in eintraege[:anzahl]]}


def _kurs(symbol: str) -> dict:
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}",
            params={"range": "1d", "interval": "15m"}, headers=UA, timeout=10,
        )
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        meta = res["meta"]
        verlauf = [k for k in res["indicators"]["quote"][0].get("close", []) if k is not None]
        preis = meta.get("regularMarketPrice") or (verlauf[-1] if verlauf else None)
        vortag = meta.get("chartPreviousClose") or meta.get("previousClose")
        aenderung = (preis - vortag) / vortag * 100 if preis and vortag else 0.0
        return {
            "symbol": symbol,
            "name": AKTIEN_NAMEN.get(symbol, meta.get("shortName") or symbol),
            "preis": preis, "waehrung": meta.get("currency", ""),
            "aenderung": round(aenderung, 2), "verlauf": verlauf[-40:],
        }
    except Exception as e:
        return {"symbol": symbol, "name": AKTIEN_NAMEN.get(symbol, symbol), "fehler": str(e)[:80]}


def aktien(symbole: str = "") -> dict:
    liste = [s.strip() for s in symbole.split(",") if s.strip()] or AKTIEN
    with ThreadPoolExecutor(max_workers=8) as pool:  # parallel statt nacheinander
        return {"liste": list(pool.map(_kurs, liste))}


def _vscode_zuletzt(anzahl: int = 8) -> list[dict]:
    """Zuletzt in VS Code geoeffnete Ordner (jeder hat einen Eintrag in workspaceStorage)."""
    speicher = Path(os.environ.get("APPDATA", "")) / "Code" / "User" / "workspaceStorage"
    if not speicher.exists():
        return []
    eintraege = []
    for ordner in speicher.iterdir():
        info = ordner / "workspace.json"
        if not info.exists():
            continue
        try:
            uri = json.loads(info.read_text(encoding="utf-8")).get("folder", "")
        except (OSError, json.JSONDecodeError):
            continue
        if not uri.startswith("file:///"):
            continue
        pfad = Path(urllib.parse.unquote(uri[len("file:///"):]))
        if pfad.exists():
            eintraege.append((ordner.stat().st_mtime, pfad))
    ergebnis, gesehen = [], set()
    for zeit, pfad in sorted(eintraege, reverse=True):
        if str(pfad).lower() in gesehen:
            continue
        gesehen.add(str(pfad).lower())
        ergebnis.append({"name": pfad.name, "pfad": str(pfad), "art": "vscode",
                         "zuletzt": dt.datetime.fromtimestamp(zeit).strftime("%d.%m.")})
        if len(ergebnis) >= anzahl:
            break
    return ergebnis


def projekte() -> dict:
    klaus = []
    if PROJEKTE_DIR.exists():
        ordner = [p for p in PROJEKTE_DIR.iterdir() if p.is_dir() and not p.name.startswith("_")]
        for p in sorted(ordner, key=lambda p: p.stat().st_mtime, reverse=True)[:8]:
            index = next(p.rglob("index.html"), None)
            klaus.append({"name": p.name, "pfad": str(p), "art": "klaus",
                          "index": str(index) if index else "", "fertig": index is not None})
    return {"vscode": _vscode_zuletzt(), "klaus": klaus}


def favoriten(namen: str = "") -> dict:
    liste = []
    for name in [n.strip() for n in namen.split(",") if n.strip()] or FAVORITEN:
        treffer = apps.finde(name)
        if treffer:
            liste.append({"name": treffer[0], "befehl": name})
    return {"liste": liste}


def alle_apps() -> dict:
    return {"liste": sorted(apps.lade_apps())}


def leads() -> dict:
    datei = BASE_DIR / "data" / "leads.csv"
    anzahl = 0
    if datei.exists():
        with open(datei, newline="", encoding="utf-8") as f:
            anzahl = sum(1 for r in csv.DictReader(f) if r.get("name"))
    entwuerfe = len(list((BASE_DIR / "data" / "briefe").glob("*/brief.pdf")))  # fertige Briefe (statt Werbe-Mails)
    return {"leads": anzahl, "entwuerfe": entwuerfe}


def system() -> dict:
    import psutil

    werte = {
        "cpu": psutil.cpu_percent(interval=None),
        "ram": psutil.virtual_memory().percent,
        "ram_gb": round(psutil.virtual_memory().used / 1024**3, 1),
        "ram_gesamt": round(psutil.virtual_memory().total / 1024**3),
        "laufzeit_h": round((dt.datetime.now().timestamp() - psutil.boot_time()) / 3600, 1),
    }
    try:
        roh = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout.strip().split(", ")
        name, last, belegt, gesamt, temp = roh
        werte.update({"gpu_name": name.replace("NVIDIA GeForce ", ""), "gpu": float(last),
                      "vram": round(float(belegt) / float(gesamt) * 100),
                      "vram_gb": round(float(belegt) / 1024, 1), "vram_gesamt": round(float(gesamt) / 1024),
                      "gpu_temp": float(temp)})
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return werte


# ------------------------------------------------------------------ Seit du weg warst
ZULETZT_PATH = BASE_DIR / "data" / "zuletzt.json"


def kurse(symbole: list[str]) -> dict[str, float]:
    """Aktueller Preis je Symbol (fehlende werden ausgelassen)."""
    return {a["symbol"]: a["preis"] for a in aktien(",".join(symbole))["liste"] if a.get("preis")}


def merke_anwesenheit() -> None:
    """Regelmaessig aufgerufen, solange du am PC bist: Zeit + Kurse als Vergleichsbasis."""
    ZULETZT_PATH.write_text(json.dumps({"zeit": time.time(), "kurse": kurse(MARKT_BRIEFING)}), encoding="utf-8")


def lade_anwesenheit() -> dict | None:
    try:
        return json.loads(ZULETZT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def verpasst(basis: dict) -> dict:
    """Was seit basis["zeit"] passiert ist: Nachrichten, Kursbewegungen, fertige Klaus-Projekte."""
    seit = dt.datetime.fromtimestamp(basis["zeit"], dt.timezone.utc)
    dauer_min = int((time.time() - basis["zeit"]) // 60)

    # Nachrichten: Google-Top (= worueber viele berichten) zuerst, dann die neuesten der anderen Quellen
    neu = [m for m in _meldungen() if m[3] > seit and not KEINE_MELDUNG.search(m[1])]
    neu.sort(key=lambda m: (m[0] != "google", m[4] if m[0] == "google" else -m[3].timestamp()))
    gesehen, meldungen = set(), []
    for q, t, l, z, _ in neu:
        schluessel = re.sub(r"\W+", "", t.lower())[:40]
        if schluessel not in gesehen:
            gesehen.add(schluessel)
            meldungen.append({"quelle": q, "titel": t, "link": l, "alter": _alter(z)})
        if len(meldungen) >= 6:
            break

    # Maerkte: Veraenderung seit dem Schnappschuss, groesste Bewegung zuerst
    vorher = basis.get("kurse", {})
    jetzt = kurse(list(vorher) or MARKT_BRIEFING)
    bewegungen = [{"symbol": s, "name": SPRECH_NAMEN.get(s, s), "aenderung": round((jetzt[s] - p) / p * 100, 2)}
                  for s, p in vorher.items() if s in jetzt and p]
    bewegungen.sort(key=lambda b: abs(b["aenderung"]), reverse=True)

    fertig = []
    if PROJEKTE_DIR.exists():
        for p in PROJEKTE_DIR.iterdir():
            index = p / "index.html" if p.is_dir() else None
            if index and index.exists() and index.stat().st_mtime > basis["zeit"]:
                fertig.append(p.name.split("-", 3)[-1])
    return {"dauer_min": dauer_min, "nachrichten": meldungen, "maerkte": bewegungen, "projekte": fertig}


def verpasst_text(d: dict, einleitung: str = "") -> str:
    """Zum Vorlesen: kurz, ohne Listen-Zeichen."""
    h, m = divmod(d["dauer_min"], 60)
    stunden = "eine Stunde" if h == 1 else f"{h} Stunden"
    dauer = (f"{stunden} und {m} Minuten" if m else stunden) if h else f"{m} Minuten"
    teile = [einleitung or f"Du warst {dauer} weg."]
    if d["projekte"]:
        teile.append(f"Claude ist fertig mit {', '.join(d['projekte'])}.")
    starke = [b for b in d["maerkte"] if abs(b["aenderung"]) >= 0.5][:4]
    if starke:
        teile.append("An den Märkten: " + ", ".join(
            f"{b['name']} {'plus' if b['aenderung'] > 0 else 'minus'} {abs(b['aenderung']):.1f} Prozent".replace(".", ",")
            for b in starke) + ".")
    elif d["maerkte"]:
        teile.append("An den Märkten ist kaum was passiert.")
    if d["nachrichten"]:
        teile.append("Wichtig in den Nachrichten: " + " ... ".join(n["titel"] for n in d["nachrichten"][:3]) + ".")
    return " ".join(teile)


LAYOUT_PATH = BASE_DIR / "data" / "layout.json"
EINSTELLUNGEN_PATH = BASE_DIR / "data" / "einstellungen.json"


def lade_einstellungen() -> dict:
    try:
        return json.loads(EINSTELLUNGEN_PATH.read_text(encoding="utf-8-sig"))  # -sig: auch mit BOM lesbar
    except (OSError, json.JSONDecodeError):
        return {"panel": True}


def speichere_einstellung(schluessel: str, wert) -> None:
    werte = lade_einstellungen()
    werte[schluessel] = wert
    EINSTELLUNGEN_PATH.write_text(json.dumps(werte, indent=2), encoding="utf-8")


def lade_layout() -> str:
    return LAYOUT_PATH.read_text(encoding="utf-8") if LAYOUT_PATH.exists() else ""


def speichere_layout(text: str) -> None:
    json.loads(text)  # nur gueltiges JSON speichern
    LAYOUT_PATH.write_text(text, encoding="utf-8")


def gedaechtnis() -> dict:
    import gehirn

    return {"liste": list(reversed(gehirn.lade_gedaechtnis()))}


def sicherheit() -> dict:
    import sicherheit as s

    return s.lage()


QUELLEN = {
    "sicherheit": sicherheit,
    "wetter": wetter, "nachrichten": nachrichten, "aktien": aktien, "projekte": projekte,
    "favoriten": favoriten, "apps": alle_apps, "leads": leads, "system": system, "gedaechtnis": gedaechtnis,
}
