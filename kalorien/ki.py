"""Kalorien-App - KI-Schaetzung aus Foto oder Text (Google Gemini ueber REST, Schluessel nur auf dem Server).

Fotos werden NICHT gespeichert: sie gehen einmal an die KI, zurueck kommt nur die Schaetzung."""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.request

MODELL = os.getenv("KALORIEN_MODELL", "gemini-2.5-flash")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{modell}:generateContent"
FORMAT = ('Antworte NUR mit JSON: {"gerichte":[{"name":"deutscher Name","menge":"z.B. 150 g oder 1 Stück","kcal":Zahl,'
          '"eiweiss":Gramm,"kh":Gramm,"fett":Gramm}],"hinweis":"ein kurzer Satz zur Unsicherheit"}. '
          "Zahlen sind für die genannte Menge insgesamt, nicht pro 100 g. Schätze realistisch, lieber vorsichtig runden. "
          "Wenn nichts Essbares erkennbar ist: gerichte = [].")
BILD = "Du bist ein Ernährungs-Assistent. Erkenne jedes Lebensmittel auf dem Foto, schätze Portionsgrößen und Nährwerte. "
TEXT = "Du bist ein Ernährungs-Assistent. Schätze Menge und Nährwerte der beschriebenen Mahlzeit; Angaben des Nutzers haben Vorrang. "


class KiFehler(Exception):
    pass


def schluessel() -> str:
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()


def verfuegbar() -> bool:
    return bool(schluessel())


def _aufrufen(teile: list[dict], timeout: float = 60) -> dict:
    if not schluessel():
        raise KiFehler("Die KI ist auf diesem Server nicht eingerichtet (GEMINI_API_KEY fehlt).")
    daten = {"contents": [{"parts": teile}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}
    anfrage = urllib.request.Request(URL.format(modell=MODELL), data=json.dumps(daten).encode(),
                                     headers={"Content-Type": "application/json", "x-goog-api-key": schluessel()})
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as r:
            antwort = json.loads(r.read().decode("utf-8", "replace"))
        text = antwort["candidates"][0]["content"]["parts"][0]["text"]
    except (OSError, KeyError, IndexError, ValueError) as e:
        raise KiFehler(f"Die KI antwortet gerade nicht ({type(e).__name__}).")
    return lesen(text)


def lesen(text: str) -> dict:
    """KI-Antwort -> {gerichte: [...], hinweis}. Tolerant gegenueber ```json-Zaeunen und Komma-Zahlen."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        roh = json.loads(text)
    except ValueError:
        raise KiFehler("Die KI-Antwort war nicht lesbar. Bitte nochmal versuchen.")
    liste = roh.get("gerichte") if isinstance(roh, dict) else roh

    def zahl(w, grenze: float) -> float:
        try:
            return round(max(0.0, min(float(str(w).replace(",", ".")), grenze)), 1)
        except (TypeError, ValueError):
            return 0.0
    gerichte = []
    for g in (liste if isinstance(liste, list) else [])[:12]:
        if isinstance(g, dict) and str(g.get("name") or "").strip():
            gerichte.append({"name": str(g["name"]).strip()[:120], "menge": str(g.get("menge") or "")[:40],
                             "kcal": zahl(g.get("kcal"), 5000), "eiweiss": zahl(g.get("eiweiss"), 500),
                             "kh": zahl(g.get("kh"), 800), "fett": zahl(g.get("fett"), 500)})
    return {"gerichte": gerichte, "hinweis": str(roh.get("hinweis") or "")[:200] if isinstance(roh, dict) else ""}


def aus_bild(bild: bytes, mime: str, hinweis: str = "") -> dict:
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        raise KiFehler("Bitte ein JPEG-, PNG- oder WebP-Foto senden.")
    zusatz = f' Hinweis des Nutzers: "{hinweis[:300]}".' if hinweis.strip() else ""
    return _aufrufen([{"text": BILD + FORMAT + zusatz},
                      {"inline_data": {"mime_type": mime, "data": base64.b64encode(bild).decode()}}])


def aus_text(beschreibung: str) -> dict:
    if not beschreibung.strip():
        raise KiFehler("Bitte beschreibe, was du gegessen hast.")
    return _aufrufen([{"text": TEXT + FORMAT + f'\nMahlzeit: "{beschreibung[:600]}"'}])
