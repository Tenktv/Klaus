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
    # Groq: Text mit gpt-oss; Fotos mit einem Bildmodell (llama-4-scout wurde von Groq abgeschaltet, Stand Nov 2026: qwen/qwen3.8-27b in der Vorschau)
    "groq": {"name": "Groq", "modell": "openai/gpt-oss-120b", "bild_modell": "qwen/qwen3.8-27b", "bild": True,
             "url": "https://api.groq.com/openai/v1/chat/completions", "hilfe": "console.groq.com/keys"},
    "openrouter": {"name": "OpenRouter", "modell": "google/gemini-3.5-flash", "bild": True,
                   "url": "https://openrouter.ai/api/v1/chat/completions", "hilfe": "openrouter.ai/keys"},
}
# Vom Anbieter abgeschaltete Modelle: gespeicherte Eintraege damit werden automatisch durch den Standard ersetzt
ABGESCHALTET = {"groq": {"meta-llama/llama-4-scout-17b-16e-instruct", "meta-llama/llama-4-maverick-17b-128e-instruct"}}
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


def groq_schluessel() -> str:
    """Zweite KI fuer den Server (Groq, kostenlos): springt ein, wenn Gemini am Limit oder ausgefallen ist - oder fehlt."""
    return os.getenv("GROQ_API_KEY", "").strip()


def groq_konfig(mit_bild: bool = False) -> dict:
    env = "KALORIEN_GROQ_BILD_MODELL" if mit_bild else "KALORIEN_GROQ_MODELL"
    return {"anbieter": "groq", "schluessel": groq_schluessel(), "modell": os.getenv(env, "").strip()}   # leer = Standard je nach Foto/Text


def verfuegbar() -> bool:
    return bool(schluessel() or groq_schluessel())


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
    return {"anbieter": anbieter, "schluessel": key, "modell": modell}   # leer = Standard; wird erst beim Anfragen gewaehlt (Text oder Foto)


def modell_waehlen(anbieter: str, gespeichert: str, mit_bild: bool) -> str:
    """Welches Modell wirklich gefragt wird: das gespeicherte, sonst der Standard (bei Fotos der Bild-Standard); Abgeschaltetes wird ersetzt."""
    m = (gespeichert or "").strip()
    if m in ABGESCHALTET.get(anbieter, ()):
        m = ""
    if m:
        return m
    a = ANBIETER[anbieter]
    return a.get("bild_modell") if mit_bild and a.get("bild_modell") else a["modell"]


def maskiert(key: str) -> str:
    return "••••" + key[-4:] if len(key) >= 8 else "••••"


def _post(url: str, kopf: dict, daten: dict, timeout: float) -> dict:
    # Eigene Kennung: Anbieter hinter Cloudflare (z.B. Groq) blocken die Standard-Kennung "Python-urllib" mit 403 - sieht aus wie ein falscher Schluessel
    anfrage = urllib.request.Request(url, data=None if daten is None else json.dumps(daten).encode(),   # daten=None -> GET
                                     headers={"Content-Type": "application/json", "User-Agent": "KlesroFit/1.0", **kopf})
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        # Nie den Schluessel oder Rohtext des Anbieters an die App weitergeben - nur eine klare Ursache; Grund nur ins Server-Log
        try:
            grund = re.sub(r"\s+", " ", e.read().decode("utf-8", "replace"))[:240]
        except OSError:
            grund = ""
        print(f"[Kalorien-KI] HTTP {e.code} von {url.split('?')[0].split('/models/')[-1]}: {grund}", flush=True)
        if e.code == 403 and re.search(r"1010|1020|cloudflare|access denied|blocked", grund, re.I) and "api_key" not in grund.lower():
            raise KiFehler("Der KI-Anbieter blockiert Anfragen von diesem Server (Schutzdienst) – das liegt nicht an deinem Schlüssel.", 403)
        if e.code in (400, 404) and re.search(r"decommission|model_not_found|does not exist|no longer supported", grund, re.I):
            raise KiFehler("Dieses Modell gibt es beim Anbieter nicht mehr. Wähle ein anderes: Eigene KI → „Verfügbare Modelle anzeigen“.", 404)
        if e.code in (401, 403):
            raise KiFehler("Der Anbieter hat den API-Schlüssel abgelehnt. Stimmt er, und hat er Guthaben?")
        if e.code == 402:
            raise KiFehler("Dein Konto beim KI-Anbieter hat kein Guthaben mehr.")
        if e.code == 404:
            raise KiFehler("Das Modell gibt es beim Anbieter nicht. Prüfe den Modellnamen.", 404)
        if e.code == 429:
            raise KiFehler("Dein KI-Anbieter sagt: Limit erreicht. Bitte später nochmal.", 429)
        raise KiFehler(f"Der KI-Anbieter antwortet gerade nicht ({e.code}).", e.code)
    except (OSError, ValueError) as e:
        raise KiFehler(f"Die KI antwortet gerade nicht ({type(e).__name__}).")


def chat(system: str, nutzer: str, bild: tuple[bytes, str] | None = None, konfig: dict | None = None,
         json_modus: bool = True, timeout: float = 60, max_token: int = 1800) -> str:
    """Eine Anfrage an die KI -> Text. bild = (Bytes, MIME). konfig = eigene KI des Nutzers, sonst der Server-Schluessel."""
    eigener_schluessel_nein = konfig is None   # Ersatzmodell nur bei unserem Server-Schluessel
    if konfig is None:
        if not schluessel():
            if groq_schluessel():
                return chat(system, nutzer, bild, groq_konfig(bool(bild)), json_modus, timeout, max_token)
            raise KiFehler("Die KI ist auf diesem Server nicht eingerichtet (GEMINI_API_KEY fehlt).")
        konfig = {"anbieter": "gemini", "schluessel": schluessel(), "modell": MODELL}
    anbieter, key = konfig["anbieter"], konfig["schluessel"]
    modell = modell_waehlen(anbieter, konfig.get("modell") or "", bool(bild))
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
                if e.code in (404, 429):
                    rest = [x for x in rest if x != m]   # Modell fehlt oder Kontingent leer (gilt je Modell): gleich das Ersatzmodell
                elif e.code not in WIEDERHOLBAR:
                    raise
                if not rest and eigener_schluessel_nein and groq_schluessel() and e.code in (404, 429) + WIEDERHOLBAR:
                    print(f"[Kalorien-KI] Gemini nicht verfuegbar ({e.code}) - nehme Groq", flush=True)
                    try:
                        return chat(system, nutzer, bild, groq_konfig(bool(bild)), json_modus, timeout, max_token)
                    except KiFehler as g:
                        print(f"[Kalorien-KI] Groq auch nicht: {g}", flush=True)   # dann gilt die Meldung zu Gemini unten
                if not rest:
                    if e.code == 429 and eigener_schluessel_nein:
                        raise KiFehler("Die KI-Schätzung ist heute ausgelastet (gemeinsames Limit der App). Trag das Essen von Hand ein "
                                       "oder versuch es später nochmal.", 429)
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


def _retten(text: str):
    """Abgeschnittene oder mit Text umgebene KI-Antwort: Json aus dem Text holen, sonst die vollstaendigen Gerichte einsammeln."""
    dec = json.JSONDecoder()
    anfang = text.find("{")
    while anfang != -1:   # Json irgendwo im Text (z.B. "Hier ist die Schaetzung: {...}")
        try:
            obj, _ = dec.raw_decode(text[anfang:])
            if isinstance(obj, dict) and "gerichte" in obj:
                return obj
        except ValueError:
            pass
        anfang = text.find("{", anfang + 1)
    gerichte = []   # abgeschnitten: alle fertigen {"name": ...}-Objekte der Liste behalten
    for m in re.finditer(r'\{\s*"name"', text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
            gerichte.append(obj)
        except ValueError:
            break
    return {"gerichte": gerichte, "hinweis": "Die Antwort war unvollständig – prüfe die Werte."} if gerichte else None


def lesen(text: str) -> dict:
    """KI-Antwort -> {gerichte: [...], hinweis}. Tolerant gegenueber ```json-Zaeunen und Komma-Zahlen."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        roh = json.loads(text)
    except ValueError:
        roh = _retten(text)
        if roh is None:
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
    for versuch in (0, 1):   # unleserliche Antwort: einmal neu fragen (Platz fuers "Denken" der Modelle ist grosszuegig)
        try:
            return lesen(chat(system, nutzer, bild, konfig, max_token=4096))
        except KiFehler as e:
            if versuch or "nicht lesbar" not in str(e):
                raise


def aus_bild(bild: bytes, mime: str, hinweis: str = "", konfig: dict | None = None) -> dict:
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        raise KiFehler("Bitte ein JPEG-, PNG- oder WebP-Foto senden.")
    zusatz = f' Hinweis des Nutzers: "{hinweis[:300]}".' if hinweis.strip() else ""
    try:
        return _aufrufen(BILD + FORMAT, "Foto der Mahlzeit." + zusatz, (bild, mime), konfig)
    except KiFehler as e:
        if konfig is not None and e.code == 400:   # eigene KI: 400 beim Foto = fast immer ein Modell ohne Bildverstehen (z.B. gpt-oss, Llama 3.3)
            raise KiFehler("Dein gewähltes Modell versteht keine Fotos. Nimm ein Bildmodell (bei Groq: qwen/qwen3.8-27b – leer lassen wählt es, "
                           "bei Gemini/OpenAI/Claude das Standardmodell) oder entferne die eigene KI – dann nutzt die App die Server-KI.", 400)
        raise


def aus_text(beschreibung: str, konfig: dict | None = None) -> dict:
    if not beschreibung.strip():
        raise KiFehler("Bitte beschreibe, was du gegessen hast.")
    return _aufrufen(TEXT + FORMAT, f'Mahlzeit: "{beschreibung[:600]}"', None, konfig)


def testen(konfig: dict) -> str:
    """Kleine Probe-Anfrage mit dem Schluessel des Nutzers (verbraucht Centbruchteile)."""
    antwort = chat("Antworte nur mit dem JSON {\"ok\": true}.", "Test", None, konfig, True, 20, 30)
    return "ok" if "ok" in antwort.lower() else "antwortet"


NICHT_CHAT = re.compile(r"whisper|tts|guard|embed|orpheus|moderation|dall-e|image|audio|realtime|transcribe|speech|imagen|veo|aqa", re.I)
BILD_MODELL = re.compile(r"scout|maverick|vision|-vl|qwen3\.[5-9]|gpt-4o|gpt-4\.1|gpt-5|gemini|claude|pixtral|llava|qwen.*vl", re.I)


def modelle_liste(konfig: dict, timeout: float = 20) -> list[dict]:
    """Welche Modelle darf dieser Schluessel nutzen? -> [{id, bild}] (bild = Modell versteht vermutlich Fotos). Fuer die Auswahl in der App."""
    anbieter, key = konfig["anbieter"], konfig["schluessel"]
    if anbieter == "gemini":
        r = _post("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", {"x-goog-api-key": key}, None, timeout)
        ids = [m["name"].split("/", 1)[-1] for m in r.get("models", []) if "generateContent" in (m.get("supportedGenerationMethods") or [])]
    elif anbieter == "anthropic":
        r = _post("https://api.anthropic.com/v1/models?limit=100", {"x-api-key": key, "anthropic-version": "2023-06-01"}, None, timeout)
        ids = [m.get("id", "") for m in r.get("data", [])]
    else:
        r = _post(ANBIETER[anbieter]["url"].rsplit("/chat/completions", 1)[0] + "/models", {"Authorization": f"Bearer {key}"}, None, timeout)
        ids = [m.get("id", "") for m in r.get("data", [])]
    modelle = [{"id": i, "bild": bool(BILD_MODELL.search(i))} for i in sorted(set(ids)) if i and not NICHT_CHAT.search(i) and MODELL_MUSTER.match(i)]
    return sorted(modelle, key=lambda m: (not m["bild"], m["id"]))[:80]


def ANBIETER_LISTE() -> list[dict]:
    """Fuer die App (Auswahl beim Eintragen der eigenen KI)."""
    return [{"id": k, "name": v["name"], "modell": v["modell"], "hilfe": v["hilfe"]} for k, v in ANBIETER.items()]
