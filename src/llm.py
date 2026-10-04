"""
Klaus - lokales Gehirn (Ollama)
Duenner Client fuer die lokale Ollama-API. Kein Cloud-Dienst, keine Kosten.

Konfiguration ueber .env:
    OLLAMA_URL    (Standard: http://localhost:11434)
    OLLAMA_MODEL  (Standard: gemma2:9b)
"""

import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:9b")


def ist_verfuegbar() -> bool:
    """True, wenn Ollama laeuft und das gewaehlte Modell installiert ist."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        r.raise_for_status()
        namen = {m["name"] for m in r.json().get("models", [])}
        return OLLAMA_MODEL in namen or f"{OLLAMA_MODEL}:latest" in namen
    except requests.RequestException:
        return False


def frage(prompt: str, system: str = "", als_json: bool = False, temperatur: float = 0.4):
    """Schickt eine Anfrage ans lokale Modell. Gibt Text zurueck (oder dict bei als_json)."""
    nachrichten = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    return chat(nachrichten, als_json=als_json, temperatur=temperatur)


def chat(nachrichten: list[dict], als_json: bool = False, temperatur: float = 0.4):
    """Wie frage(), aber mit ganzem Gespraechsverlauf (role/content-Liste)."""
    body = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "keep_alive": "2m",  # Grafikspeicher bald wieder freigeben
        "options": {"temperature": temperatur},
        "messages": nachrichten,
    }
    if als_json:
        body["format"] = "json"
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=300)
    r.raise_for_status()
    text = r.json()["message"]["content"].strip()
    return json.loads(text) if als_json else text
