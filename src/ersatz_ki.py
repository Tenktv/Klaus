"""
Klaus - Ersatz-KI, wenn Gemini ausfaellt (Ueberlastung 503/504, Kontingent 429).

Spricht jede Schnittstelle im weit verbreiteten "OpenAI-Format" (Chat Completions mit Werkzeug-Aufrufen): Standard ist Groq
(kostenloser Schluessel unter console.groq.com), austauschbar ueber die .env:

    GROQ_API_KEY      Schluessel (oder ERSATZ_KI_KEY)
    ERSATZ_KI_URL     Standard https://api.groq.com/openai/v1   (z. B. OpenRouter: https://openrouter.ai/api/v1)
    ERSATZ_KI_MODELLE kommagetrennt, sonst waehlt Klaus selbst aus der Modell-Liste des Anbieters

    bereit()                         -> ist ein Schluessel da?
    chat(nachrichten, tools)         -> Antwort-Nachricht (dict mit content / tool_calls), probiert Modelle der Reihe nach
    text(prompt, system)             -> einfacher Text
    bild_json(bild, mime, auftrag)   -> Text zu einem Bild (Foto-Erkennung)
    tools_umwandeln(deklarationen)   -> Gemini-Werkzeugbeschreibung in OpenAI-Format
"""
from __future__ import annotations

import base64
import os
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

URL = os.getenv("ERSATZ_KI_URL", "https://api.groq.com/openai/v1").rstrip("/")
KEY = (os.getenv("ERSATZ_KI_KEY", "") or os.getenv("GROQ_API_KEY", "")).strip()
FESTE_MODELLE = [m.strip() for m in os.getenv("ERSATZ_KI_MODELLE", "").split(",") if m.strip()]
# Reihenfolge der Vorlieben (Teilstrings der Modell-Namen): gross und werkzeugfaehig zuerst
VORLIEBE_CHAT = ["gpt-oss-120b", "llama-3.3-70b", "llama-4-maverick", "qwen3-32b", "llama-4-scout", "llama-3.1-70b", "gpt-oss-20b", "llama-3.1-8b"]
VORLIEBE_BILD = ["llama-4-maverick", "llama-4-scout", "vision"]
KEIN_CHAT = re.compile(r"whisper|guard|tts|orpheus|embed|moderat|safeguard|transcribe|speech|image-gen|dall", re.I)
_modelle: dict = {"zeit": 0.0, "ids": []}


def bereit() -> bool:
    return bool(KEY)


def _kopf() -> dict:
    return {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}


def modelle() -> list[str]:
    """Chat-Modelle des Anbieters (eine Stunde zwischengespeichert)."""
    if FESTE_MODELLE:
        return FESTE_MODELLE
    if time.time() - _modelle["zeit"] > 3600 or not _modelle["ids"]:
        r = requests.get(f"{URL}/models", headers=_kopf(), timeout=20)
        r.raise_for_status()
        _modelle.update(zeit=time.time(), ids=[m["id"] for m in r.json().get("data", []) if m.get("id") and not KEIN_CHAT.search(m["id"])])
    return _modelle["ids"]


def reihenfolge(vorlieben: list[str]) -> list[str]:
    ids = modelle()
    gewaehlt = [m for v in vorlieben for m in ids if v in m.lower()]
    return list(dict.fromkeys(gewaehlt + ids))   # Vorlieben zuerst, danach alle uebrigen (jedes Modell hat sein eigenes Minutenlimit)


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


def chat(nachrichten: list[dict], tools: list[dict] | None = None, modelle_liste: list[str] | None = None, timeout: float = 45) -> dict:
    """Probiert die Modelle der Reihe nach (429/5xx/404/kaputter Werkzeugaufruf -> naechstes). -> {"message": {...}, "modell": str}"""
    if not KEY:
        raise ErsatzFehler("Kein Schluessel fuer die Ersatz-KI (GROQ_API_KEY)")
    letzter = ""
    for modell in (modelle_liste or reihenfolge(VORLIEBE_CHAT))[:5]:
        body = {"model": modell, "messages": nachrichten, "temperature": 0.4}
        if tools:
            body.update(tools=tools, tool_choice="auto")
        try:
            r = requests.post(f"{URL}/chat/completions", json=body, headers=_kopf(), timeout=timeout)
        except requests.RequestException as e:
            letzter = f"{modell}: {type(e).__name__}"
            continue
        if r.status_code == 200:
            try:
                return {"message": r.json()["choices"][0]["message"], "modell": modell}
            except (KeyError, IndexError, ValueError):
                letzter = f"{modell}: leere Antwort"
                continue
        letzter = f"{modell}: {r.status_code} {r.text[:80]}"   # 429, 5xx, 404, 400 tool_use_failed -> naechstes Modell
    raise ErsatzFehler(f"Ersatz-KI antwortet nicht ({letzter})")


def text(prompt: str, system: str = "") -> str:
    nachrichten = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    return (chat(nachrichten)["message"].get("content") or "").strip()


def bild_json(bild: bytes, mime: str, auftrag: str) -> str:
    daten = f"data:{mime};base64,{base64.b64encode(bild).decode()}"
    nachrichten = [{"role": "user", "content": [{"type": "text", "text": auftrag}, {"type": "image_url", "image_url": {"url": daten}}]}]
    return (chat(nachrichten, modelle_liste=reihenfolge(VORLIEBE_BILD), timeout=90)["message"].get("content") or "").strip()
