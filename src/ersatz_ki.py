"""
Klaus - Ersatz-KI, wenn Gemini ausfaellt (Ueberlastung 503/504, Tageslimit 429).

Mehrere Anbieter im "OpenAI-Format" (Chat Completions mit Werkzeug-Aufrufen), der Reihe nach - faellt einer aus oder ist
sein Tageslimit erreicht, kommt der naechste:

    GROQ_API_KEY            Groq (schnell, kostenlos, ~8000 Token/Min je Modell)
    OPENROUTER_API_KEY      OpenRouter, Gratis-Modelle; Premium nur explizit ueber data/ki_modelle.json mit Kostenrahmen
    OPENROUTER_API_KEY_2    zweiter OpenRouter-Schluessel (eigenes Tageslimit)
    ERSATZ_KI_URL/_KEY      beliebiger weiterer Anbieter im OpenAI-Format (kommt zuerst)
    ERSATZ_KI_MODELLE       feste Modelle fuer ERSATZ_KI_URL, kommagetrennt

    bereit()                         -> ist irgendein Schluessel da?
    chat(nachrichten, tools)         -> {"message": {...}, "modell": "anbieter/modell"}
    text(prompt, system)             -> einfacher Text
    bild_json(bild, mime, auftrag)   -> Text zu einem Bild (Foto-Erkennung)
    tools_umwandeln(deklarationen)   -> Gemini-Werkzeugbeschreibung in OpenAI-Format
"""
from __future__ import annotations

import base64
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests
import ki_kosten
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

KEIN_CHAT = re.compile(r"whisper|guard|tts|orpheus|embed|moderat|safeguard|content-safety|transcribe|speech|image-gen|dall|lyria|veo|"
                       r"-2\.6b|laguna-xs|mini-code", re.I)   # dazu: zu kleine Modelle fuer Klaus' Werkzeuge
MODELLE_JE_ANBIETER = 3
LIMIT_PAUSE = 15 * 60      # Tageslimit/Kontingent erreicht -> Anbieter so lange ueberspringen


@dataclass
class Anbieter:
    name: str
    url: str
    key: str
    vorliebe_chat: list[str]
    vorliebe_bild: list[str]
    nur_kostenlos: bool = False
    feste_modelle: list[str] = field(default_factory=list)
    _modelle: list[dict] = field(default_factory=list)
    _zeit: float = 0.0
    pause_bis: float = 0.0

    def kopf(self) -> dict:
        k = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        if "openrouter" in self.url:
            k.update({"HTTP-Referer": "https://klesro-web.de", "X-Title": "Klaus"})
        return k

    def modelle(self) -> list[dict]:
        """[{id, tools, bild}] (eine Stunde zwischengespeichert)."""
        if self.feste_modelle:
            return [{"id": m, "tools": True, "bild": True} for m in self.feste_modelle]
        if time.time() - self._zeit > 3600 or not self._modelle:
            r = requests.get(f"{self.url}/models", headers=self.kopf(), timeout=20)
            r.raise_for_status()
            liste = []
            for m in r.json().get("data", []):
                mid = m.get("id") or ""
                if not mid or KEIN_CHAT.search(mid):
                    continue
                param = m.get("supported_parameters")
                modal = (m.get("architecture") or {}).get("input_modalities")
                liste.append({"id": mid, "tools": param is None or "tools" in param,
                              "bild": modal is None or "image" in modal})
            self._modelle, self._zeit = liste, time.time()
        return self._modelle

    def reihenfolge(self, tools: bool, bild: bool) -> list[str]:
        erlaubt = ki_kosten.modelle(self.name)
        ids = [m["id"] for m in self.modelle() if (m["tools"] or not tools) and (m["bild"] or not bild)
               and (not self.name.startswith('openrouter') or m['id'].endswith(':free') or m['id'] in erlaubt)]
        vorlieben = self.vorliebe_bild if bild else self.vorliebe_chat
        gewaehlt = [m for v in vorlieben for m in ids if v in m.lower()]
        rest = [] if bild else ids   # Bilder nur mit bekannten Bild-Modellen
        premium = [m for m in ki_kosten.modelle(self.name) if m in ids] if not bild else []
        return list(dict.fromkeys(premium + gewaehlt + rest))


def _anbieter() -> list[Anbieter]:
    aus = []
    eigene_url = os.getenv("ERSATZ_KI_URL", "").strip().rstrip("/")
    eigener_key = os.getenv("ERSATZ_KI_KEY", "").strip()
    if eigene_url and eigener_key:
        aus.append(Anbieter("eigen", eigene_url, eigener_key, [], [],
                            feste_modelle=[m.strip() for m in os.getenv("ERSATZ_KI_MODELLE", "").split(",") if m.strip()]))
    groq = os.getenv("GROQ_API_KEY", "").strip() or ("" if eigene_url else eigener_key)
    if groq:
        aus.append(Anbieter("groq", "https://api.groq.com/openai/v1", groq,
                            ["gpt-oss-120b", "llama-3.3-70b", "llama-4-maverick", "qwen3-32b", "llama-4-scout", "gpt-oss-20b"],
                            ["llama-4-maverick", "llama-4-scout", "vision"]))
    openai = os.getenv('OPENAI_API_KEY', '').strip()
    if openai:
        aus.append(Anbieter('openai', 'https://api.openai.com/v1', openai, [], [],
                            feste_modelle=ki_kosten.modelle('openai')))
    bezahlt = os.getenv("OPENROUTER_BEZAHLT", "").strip() == "1"
    for nr, var in enumerate(("OPENROUTER_API_KEY", "OPENROUTER_API_KEY_2"), 1):
        key = os.getenv(var, "").strip()
        if key:
            aus.append(Anbieter(f"openrouter{nr}", "https://openrouter.ai/api/v1", key,
                                # Stand 14.10.2026 (Gratis-Modelle wechseln oft - unbekannte kommen nach diesen)
                                ["thinkingmachines/inkling:", "nemotron-3-ultra", "nemotron-3-super", "gemma-4-31b", "dots-3-note",
                                 "gpt-oss-120b", "deepseek", "llama-3.3-70b", "qwen3", "inkling-small"],
                                ["gemma-4-31b", "thinkingmachines/inkling:", "dots-3-note", "gemma-4-26b", "vl", "vision"],
                                nur_kostenlos=not bezahlt))
    return aus


ANBIETER = _anbieter()
# alt (andere Module lesen das noch): erster Anbieter
URL = ANBIETER[0].url if ANBIETER else ""
KEY = ANBIETER[0].key if ANBIETER else ""


def bereit() -> bool:
    return bool(ANBIETER)


def status() -> list[str]:
    return [f"{a.name}: {'Pause (Limit) bis ' + time.strftime('%H:%M', time.localtime(a.pause_bis)) if time.time() < a.pause_bis else 'bereit'}"
            for a in ANBIETER]


def tools_umwandeln(deklarationen: list[dict]) -> list[dict]:
    """Gemini: {"name", "description", "parameters": {"type": "OBJECT", ...}} -> OpenAI: {"type": "function", "function": {...}}
    Beschreibungen werden gekuerzt: Groq erlaubt im kostenlosen Tarif nur ~8000 Token pro Minute und Modell."""
    def klein(x):
        if isinstance(x, dict):
            return {k: (v.lower() if k == "type" and isinstance(v, str) else
                        (v[:90] if k == "description" and isinstance(v, str) else klein(v))) for k, v in x.items()}
        if isinstance(x, list):
            return [klein(i) for i in x]
        return x
    aus = []
    for d in deklarationen:
        p = klein(d.get("parameters") or {"type": "object", "properties": {}})
        p.setdefault("type", "object")
        p.setdefault("properties", {})
        aus.append({"type": "function", "function": {"name": d["name"], "description": d.get("description", "")[:200], "parameters": p}})
    return aus


class ErsatzFehler(RuntimeError):
    pass


def chat(nachrichten: list[dict], tools: list[dict] | None = None, bild: bool = False, timeout: float = 45,
         frist: float = 150) -> dict:
    """Anbieter der Reihe nach, je Anbieter bis zu 3 Modelle (429/5xx/404/kaputter Werkzeugaufruf -> naechstes).
    -> {"message": {...}, "modell": "anbieter/modell"}"""
    if not ANBIETER:
        raise ErsatzFehler("Kein Schluessel fuer die Ersatz-KI (GROQ_API_KEY / OPENROUTER_API_KEY)")
    ende = time.time() + frist
    fehler = []
    # Explizit freigegebene Premium-Anbieter zuerst; ohne Opt-in bleibt die alte Gratis-Reihenfolge.
    anbieter = sorted(ANBIETER, key=lambda a: 0 if ki_kosten.modelle(a.name) else 1)
    for a in anbieter:
        if a.name in ('eigen', 'openai') and not ki_kosten.modelle(a.name):
            continue
        if time.time() < a.pause_bis:
            fehler.append(f"{a.name}: Limit-Pause")
            continue
        try:
            modelle = a.reihenfolge(bool(tools), bild)[:MODELLE_JE_ANBIETER]
        except Exception as e:
            fehler.append(f"{a.name}: Modell-Liste {str(e)[:50]}")
            continue
        for modell in modelle:
            if time.time() > ende:
                raise ErsatzFehler(f"Ersatz-KI: Zeitlimit ({'; '.join(fehler)[-200:]})")
            body = {"model": modell, "messages": nachrichten, "temperature": 0.4}
            if tools:
                body.update(tools=tools, tool_choice="auto")
            ticket = None
            bezahlt = (a.name in ('eigen', 'openai') or
                       (a.name.startswith('openrouter') and not modell.endswith(':free')) or
                       modell in ki_kosten.modelle(a.name))
            if bezahlt:
                try:
                    ticket = ki_kosten.reservieren(a.name, modell, nachrichten, tools, bild)
                    body['max_tokens'] = ticket['max_tokens']
                    if a.name == 'openai':
                        body['max_completion_tokens'] = body.pop('max_tokens')
                        body.pop('temperature', None)
                except ki_kosten.BudgetFehler as e:
                    fehler.append(f'{a.name}/{modell}: {e}')
                    continue
            try:
                r = requests.post(f"{a.url}/chat/completions", json=body, headers=a.kopf(), timeout=min(timeout, max(5, ende - time.time())))
            except requests.RequestException as e:
                fehler.append(f"{a.name}/{modell}: {type(e).__name__}")
                continue
            if r.status_code == 200:
                try:
                    j = r.json()
                    if ticket:
                        ki_kosten.abrechnen(ticket, j.get('usage'))
                    nachricht = j["choices"][0]["message"]
                    if nachricht.get("content") or nachricht.get("tool_calls"):
                        return {"message": nachricht, "modell": f"{a.name}/{modell}"}
                    fehler.append(f"{a.name}/{modell}: leer")
                except (KeyError, IndexError, ValueError, ki_kosten.BudgetFehler):
                    fehler.append(f"{a.name}/{modell}: leere Antwort")
                continue
            fehler.append(f"{a.name}/{modell}: {r.status_code} {r.text[:60]}")
            # Tageslimit/Guthaben des ganzen Kontos (nicht nur dieses Modells) -> Anbieter eine Weile auslassen
            if r.status_code in (401, 402) or (r.status_code == 429 and re.search(r"per.day|free-models-per-day|credits|quota", r.text, re.I)):
                a.pause_bis = time.time() + LIMIT_PAUSE
                break
    raise ErsatzFehler(f"Ersatz-KI antwortet nicht ({'; '.join(fehler)[-300:]})")


def text(prompt: str, system: str = "") -> str:
    nachrichten = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    return (chat(nachrichten)["message"].get("content") or "").strip()


def bild_json(bild: bytes, mime: str, auftrag: str) -> str:
    daten = f"data:{mime};base64,{base64.b64encode(bild).decode()}"
    nachrichten = [{"role": "user", "content": [{"type": "text", "text": auftrag}, {"type": "image_url", "image_url": {"url": daten}}]}]
    return (chat(nachrichten, bild=True, timeout=90)["message"].get("content") or "").strip()
