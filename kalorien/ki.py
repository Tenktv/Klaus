"""Fit-App - KI ueber REST. Zwei Wege:

  * Server-KI: der GEMINI_API_KEY des Betreibers (mit Tageslimit je Nutzer, siehe server.ki_zaehlen)
  * Eigene KI (nur Pro): der Nutzer traegt seinen eigenen Schluessel ein - Gemini, OpenAI, Anthropic, Groq oder OpenRouter.
    Die Adressen der Anbieter sind FEST eingebaut: der Nutzer kann keine eigene URL angeben (sonst koennte er den Server
    auf interne Adressen schicken = SSRF). Der Schluessel verlaesst den Server nie in Richtung App.

Fotos werden NICHT gespeichert: sie gehen einmal an die KI, zurueck kommt nur die Schaetzung."""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request

MODELL = os.getenv("KALORIEN_MODELL", "gemini-3.5-flash")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{modell}:generateContent"

# Feste Anbieter. "bild": versteht das Standardmodell Fotos?
ANBIETER = {
    "gemini": {"name": "Google Gemini", "modell": "gemini-3.5-flash", "bild": True, "hilfe": "aistudio.google.com/apikey"},
    "openai": {"name": "OpenAI", "modell": "gpt-4o-mini", "bild": True, "url": "https://api.openai.com/v1/chat/completions",
               "hilfe": "platform.openai.com/api-keys"},
    "anthropic": {"name": "Anthropic (Claude)", "modell": "claude-haiku-4-5", "bild": True, "url": "https://api.anthropic.com/v1/messages",
                  "hilfe": "console.anthropic.com/settings/keys"},
    "groq": {"name": "Groq", "modell": "meta-llama/llama-4-scout-17b-16e-instruct", "bild": True,
             "url": "https://api.groq.com/openai/v1/chat/completions", "hilfe": "console.groq.com/keys"},
    "openrouter": {"name": "OpenRouter", "modell": "google/gemini-3.5-flash", "bild": True,
                   "url": "https://openrouter.ai/api/v1/chat/completions", "hilfe": "openrouter.ai/keys"},
}
MODELL_MUSTER = re.compile(r"^[\w./:@-]{2,80}$")
SCHLUESSEL_MUSTER = re.compile(r"^[\w.\-]{16,300}$")

FORMAT = ('Antworte NUR mit JSON: {"gerichte":[{"name":"deutscher Name","menge":"z.B. 150 g oder 1 Stück","kcal":Zahl,'
          '"eiweiss":Gramm,"kh":Gramm,"fett":Gramm}],"hinweis":"ein kurzer Satz zur Unsicherheit"}. '
          "Zahlen sind für die genannte Menge insgesamt, nicht pro 100 g. Schätze realistisch, lieber vorsichtig runden. "
          "Wenn nichts Essbares erkennbar ist: gerichte = [].")
BILD = "Du bist ein Ernährungs-Assistent. Erkenne jedes Lebensmittel auf dem Foto, schätze Portionsgrößen und Nährwerte. "
TEXT = "Du bist ein Ernährungs-Assistent. Schätze Menge und Nährwerte der beschriebenen Mahlzeit; Angaben des Nutzers haben Vorrang. "


class KiFehler(Exception):
    def __init__(self, text: str = "", code: int = 0) -> None:
        super().__init__(text)
        self.code = code   # HTTP-Status des Anbieters (0 = kein HTTP-Fehler)


# Wenn das Hauptmodell kurz ueberlastet ist (503 ...), erst nochmal, dann das Ersatzmodell (nur beim Server-Schluessel)
MODELL_ERSATZ = os.getenv("KALORIEN_MODELL_ERSATZ", "gemini-flash-latest")
WIEDERHOLBAR = (500, 502, 503, 504)


def schluessel() -> str:
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()


def verfuegbar() -> bool:
    return bool(schluessel())


def konfig_pruefen(anbieter: str, key: str, modell: str = "") -> dict:
    """Eingaben des Nutzers pruefen -> {anbieter, schluessel, modell}. Wirft KiFehler."""
    if anbieter not in ANBIETER:
        raise KiFehler("Unbekannter Anbieter.")
    key = (key or "").strip()
    if not SCHLUESSEL_MUSTER.match(key):
        raise KiFehler("Das sieht nicht wie ein API-Schlüssel aus (nur Buchstaben, Zahlen, - _ .).")
    modell = (modell or "").strip()
    if modell and not MODELL_MUSTER.match(modell):
        raise KiFehler("Der Modellname ist ungültig.")
    return {"anbieter": anbieter, "schluessel": key, "modell": modell or ANBIETER[anbieter]["modell"]}


def maskiert(key: str) -> str:
    return "••••" + key[-4:] if len(key) >= 8 else "••••"


def _post(url: str, kopf: dict, daten: dict, timeout: float) -> dict:
    anfrage = urllib.request.Request(url, data=json.dumps(daten).encode(), headers={"Content-Type": "application/json", **kopf})
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        # Nie den Schluessel oder Rohtext des Anbieters weitergeben - nur eine klare Ursache
        if e.code in (401, 403):
            raise KiFehler("Der Anbieter hat den API-Schlüssel abgelehnt. Stimmt er, und hat er Guthaben?")
        if e.code == 402:
            raise KiFehler("Dein Konto beim KI-Anbieter hat kein Guthaben mehr.")
        if e.code == 404:
            raise KiFehler("Das Modell gibt es beim Anbieter nicht. Prüfe den Modellnamen.", 404)
        if e.code == 429:
            raise KiFehler("Dein KI-Anbieter sagt: Limit erreicht. Bitte später nochmal.")
        try:
            grund = re.sub(r"\s+", " ", e.read().decode("utf-8", "replace"))[:240]
        except OSError:
            grund = ""
        print(f"[Kalorien-KI] HTTP {e.code} von {url.split('?')[0].split('/models/')[-1]}: {grund}", flush=True)
        raise KiFehler(f"Der KI-Anbieter antwortet gerade nicht ({e.code}).", e.code)
    except (OSError, ValueError) as e:
        raise KiFehler(f"Die KI antwortet gerade nicht ({type(e).__name__}).")


def chat(system: str, nutzer: str, bild: tuple[bytes, str] | None = None, konfig: dict | None = None,
         json_modus: bool = True, timeout: float = 60, max_token: int = 1800) -> str:
    """Eine Anfrage an die KI -> Text. bild = (Bytes, MIME). konfig = eigene KI des Nutzers, sonst der Server-Schluessel."""
    eigener_schluessel_nein = konfig is None   # Ersatzmodell nur bei unserem Server-Schluessel
    if konfig is None:
        if not schluessel():
            raise KiFehler("Die KI ist auf diesem Server nicht eingerichtet (GEMINI_API_KEY fehlt).")
        konfig = {"anbieter": "gemini", "schluessel": schluessel(), "modell": MODELL}
    anbieter, key, modell = konfig["anbieter"], konfig["schluessel"], konfig.get("modell") or ANBIETER[konfig["anbieter"]]["modell"]
    b64 = base64.b64encode(bild[0]).decode() if bild else ""
    if anbieter == "gemini":
        teile = [{"text": (system + "\n\n" + nutzer).strip()}]
        if bild:
            teile.append({"inline_data": {"mime_type": bild[1], "data": b64}})
        cfg = {"temperature": 0.3, "maxOutputTokens": max_token}
        if json_modus:
            cfg["responseMimeType"] = "application/json"
        versuche = [modell, modell] + ([MODELL_ERSATZ] if eigener_schluessel_nein and MODELL_ERSATZ and MODELL_ERSATZ != modell else [])
        n = 0
        while True:
            m = versuche[n]
            try:
                r = _post(URL.format(modell=m), {"x-goog-api-key": key}, {"contents": [{"parts": teile}], "generationConfig": cfg}, timeout)
                break
            except KiFehler as e:
                rest = versuche[n + 1:]
                if e.code == 404:
                    rest = [x for x in rest if x != m]   # Modell gibt es nicht: nicht nochmal dasselbe, gleich das Ersatzmodell
                elif e.code not in WIEDERHOLBAR:
                    raise
                if not rest:
                    if n > 0 and e.code in WIEDERHOLBAR:
                        raise KiFehler(f"Der KI-Anbieter antwortet gerade nicht ({e.code}, auch nach {n} Wiederholung(en)"
                                       f"{' und Ersatzmodell' if m != modell else ''}). Versuch es gleich nochmal.", e.code)
                    raise
                if e.code in WIEDERHOLBAR and rest[0] == m:
                    time.sleep(1.5)
                n = len(versuche) - len(rest)
        try:
            return r["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise KiFehler("Die KI hat nichts geantwortet (evtl. blockiert). Bitte anders formulieren.")
    if anbieter == "anthropic":
        inhalt = ([{"type": "image", "source": {"type": "base64", "media_type": bild[1], "data": b64}}] if bild else []) + [{"type": "text", "text": nutzer}]
        r = _post(ANBIETER["anthropic"]["url"], {"x-api-key": key, "anthropic-version": "2023-06-01"},
                  {"model": modell, "max_tokens": max_token, "system": system, "temperature": 0.3,
                   "messages": [{"role": "user", "content": inhalt}]}, timeout)
        try:
            return "".join(t.get("text", "") for t in r["content"] if t.get("type") == "text")
        except (KeyError, TypeError):
            raise KiFehler("Die KI hat nichts geantwortet.")
    # OpenAI-Format: OpenAI, Groq, OpenRouter
    inhalt = ([{"type": "text", "text": nutzer}] + ([{"type": "image_url", "image_url": {"url": f"data:{bild[1]};base64,{b64}"}}] if bild else []))
    daten = {"model": modell, "temperature": 0.3, "max_tokens": max_token,
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": inhalt if bild else nutzer}]}
    if json_modus and anbieter in ("openai", "groq"):
        daten["response_format"] = {"type": "json_object"}
    r = _post(ANBIETER[anbieter]["url"], {"Authorization": f"Bearer {key}"}, daten, timeout)
    try:
        return r["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise KiFehler("Die KI hat nichts geantwortet.")


def json_holen(text: str):
    """JSON aus einer KI-Antwort (tolerant gegenueber ```json-Zaeunen und Text drumherum)."""
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                pass
    raise KiFehler("Die KI-Antwort war nicht lesbar. Bitte nochmal versuchen.")


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


def _aufrufen(system: str, nutzer: str, bild: tuple[bytes, str] | None = None, konfig: dict | None = None) -> dict:
    """KI fragen und die Mahlzeiten-Antwort lesen (eigene Stelle, damit Tests die KI ersetzen koennen)."""
    return lesen(chat(system, nutzer, bild, konfig))


def aus_bild(bild: bytes, mime: str, hinweis: str = "", konfig: dict | None = None) -> dict:
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        raise KiFehler("Bitte ein JPEG-, PNG- oder WebP-Foto senden.")
    zusatz = f' Hinweis des Nutzers: "{hinweis[:300]}".' if hinweis.strip() else ""
    return _aufrufen(BILD + FORMAT, "Foto der Mahlzeit." + zusatz, (bild, mime), konfig)


def aus_text(beschreibung: str, konfig: dict | None = None) -> dict:
    if not beschreibung.strip():
        raise KiFehler("Bitte beschreibe, was du gegessen hast.")
    return _aufrufen(TEXT + FORMAT, f'Mahlzeit: "{beschreibung[:600]}"', None, konfig)


def testen(konfig: dict) -> str:
    """Kleine Probe-Anfrage mit dem Schluessel des Nutzers (verbraucht Centbruchteile)."""
    antwort = chat("Antworte nur mit dem JSON {\"ok\": true}.", "Test", None, konfig, True, 20, 30)
    return "ok" if "ok" in antwort.lower() else "antwortet"


def ANBIETER_LISTE() -> list[dict]:
    """Fuer die App (Auswahl beim Eintragen der eigenen KI)."""
    return [{"id": k, "name": v["name"], "modell": v["modell"], "hilfe": v["hilfe"]} for k, v in ANBIETER.items()]
