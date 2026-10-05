"""
Klaus - Fish Audio (bezahlte, sehr natuerliche Stimme).

    fish.bereit()                         FISH_API_KEY und FISH_STIMME gesetzt?
    fish.pcm_strom(text)                  Stimme als 16-bit-PCM-Stuecke (24 kHz mono), gestreamt
    fish.sprich(text, on_pegel)           direkt abspielen (lokale Kette ohne Gemini)

Eigene Stimme entwerfen (keine Nachbildung einer echten Person -> auch fuers Produkt sauber):
    .venv\\Scripts\\python.exe src\\fish.py entwerfen "tiefe, ruhige maennliche Stimme, Mitte 30, freundlich, leicht rauchig"
    .venv\\Scripts\\python.exe src\\fish.py anlegen 2          (Kandidat 2 wird Klaus' Stimme, FISH_STIMME in .env)
    .venv\\Scripts\\python.exe src\\fish.py test "Guten Morgen, Nikola. Drei Termine heute."

Kosten (Stand 2026): Sprache ca. 15 $ pro 1 Mio. Zeichen (UTF-8-Bytes); kommerzielle Nutzung nur mit Plus/Pro-Abo.
API: POST https://api.fish.audio/v1/tts  (Bearer-Schluessel, Header "model", JSON mit text/reference_id/format)
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

API = "https://api.fish.audio"
SCHLUESSEL = os.getenv("FISH_API_KEY", "").strip()
STIMME = os.getenv("FISH_STIMME", "").strip()            # reference_id des Stimm-Modells
MODELL = os.getenv("FISH_MODELL", "s2.1-pro").strip()     # s1 | s2-pro | s2.1-pro
RATE = 24000                                               # wie Gemini Live -> gleiche Wiedergabe
ORDNER = BASE_DIR / "data" / "fish"


class FishFehler(RuntimeError):
    pass


def bereit() -> bool:
    return bool(SCHLUESSEL and STIMME)


def _kopf(json_body: bool = True) -> dict:
    if not SCHLUESSEL:
        raise FishFehler("FISH_API_KEY fehlt in der .env")
    k = {"Authorization": f"Bearer {SCHLUESSEL}"}
    if json_body:
        k["Content-Type"] = "application/json"
    return k


def _fehler(r: requests.Response) -> FishFehler:
    try:
        text = r.json().get("message", "")
    except ValueError:
        text = r.text[:120]
    grund = {401: "Schlüssel ungültig", 402: "kein Guthaben", 429: "zu viele Anfragen", 503: "Dienst überlastet"}.get(r.status_code, "")
    return FishFehler(f"Fish Audio {r.status_code} {grund} {text}".strip())


def pcm_strom(text: str, stimme: str | None = None, latenz: str = "balanced"):
    """Liefert PCM-Stuecke (bytes, int16, 24 kHz, mono), sobald Fish sie erzeugt."""
    text = text.strip()
    if not text:
        return
    r = requests.post(f"{API}/v1/tts", headers={**_kopf(), "model": MODELL}, stream=True, timeout=(8, 60),
                      data=json.dumps({"text": text, "reference_id": stimme or STIMME, "format": "pcm", "sample_rate": RATE,
                                       "latency": latenz, "normalize": False}))
    if r.status_code != 200:
        raise _fehler(r)
    rest = b""
    for stueck in r.iter_content(chunk_size=4800):   # 0,1 s Audio
        if not stueck:
            continue
        stueck = rest + stueck
        gerade = len(stueck) - len(stueck) % 2          # int16 = 2 Bytes: nie ein halbes Sample weitergeben
        rest = stueck[gerade:]
        if gerade:
            yield stueck[:gerade]


def audio(text: str, stimme: str | None = None) -> tuple[np.ndarray, int]:
    """Ganzer Text als float32-Array (fuer stimme.py)."""
    pcm = b"".join(pcm_strom(text, stimme, latenz="normal"))
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768, RATE


def sprich(text: str, on_pegel=None, stimme: str | None = None) -> None:
    import sounddevice as sd

    with sd.RawOutputStream(samplerate=RATE, channels=1, dtype="int16") as aus:
        for stueck in pcm_strom(text, stimme):
            if on_pegel:
                w = np.frombuffer(stueck, dtype=np.int16).astype(np.float32) / 32768
                on_pegel(min(1.0, float(np.sqrt((w ** 2).mean())) * 6))
            aus.write(stueck)
    if on_pegel:
        on_pegel(0.0)


# ------------------------------------------------------------------ Saetze fuer gestreamtes Sprechen
SATZENDE = re.compile(r"(.+?[.!?…:;])(\s+|$)", re.S)


def saetze_abtrennen(puffer: str, alles: bool = False) -> tuple[list[str], str]:
    """Aus einem wachsenden Text fertige Saetze herausloesen. -> (saetze, rest). alles=True gibt auch den Rest aus."""
    saetze, pos = [], 0
    for m in SATZENDE.finditer(puffer):
        if len(m.group(1).strip()) >= 2:
            saetze.append(m.group(1).strip())
        pos = m.end()
    rest = puffer[pos:]
    if alles and rest.strip():
        saetze.append(rest.strip())
        rest = ""
    return saetze, rest


# ------------------------------------------------------------------ Eigene Stimme entwerfen
def entwerfen(beschreibung: str, n: int = 3, probe: str = "Hallo, ich bin Klaus. Ich habe deine Termine für heute "
              "geprüft: Um zehn Uhr kommt ein Kunde, danach ist der Nachmittag frei.") -> list[Path]:
    """Voice Design: n neue Stimmen nach Beschreibung -> data/fish/kandidat_<i>.wav (+ Signaturen fuers Anlegen)."""
    r = requests.post(f"{API}/v1/voice-design", headers=_kopf(), timeout=180,
                      data=json.dumps({"instruction": beschreibung, "reference_text": probe, "language": "de", "n": n}))
    if r.status_code != 200:
        raise _fehler(r)
    ORDNER.mkdir(parents=True, exist_ok=True)
    pfade, meta = [], []
    for k in r.json().get("candidates", []):
        nr = int(k.get("index", len(pfade))) + 1
        pfad = ORDNER / f"kandidat_{nr}.wav"
        roh = base64.b64decode(k["audio_base64"])
        if not roh[:4] == b"RIFF":   # reines PCM -> WAV-Kopf ergaenzen
            import wave

            with wave.open(str(pfad), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(k.get("sample_rate") or 24000)); w.writeframes(roh)
        else:
            pfad.write_bytes(roh)
        pfade.append(pfad)
        meta.append({"nr": nr, "datei": pfad.name, "id": k.get("id"), "text": k.get("text") or probe})
    (ORDNER / "kandidaten.json").write_text(json.dumps({"beschreibung": beschreibung, "kandidaten": meta}, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    return pfade


def anlegen(nr: int, titel: str = "Klaus") -> str:
    """Kandidat nr als eigenes, privates Stimm-Modell anlegen und als FISH_STIMME in die .env schreiben. -> Modell-ID"""
    meta = json.loads((ORDNER / "kandidaten.json").read_text(encoding="utf-8"))
    k = next(x for x in meta["kandidaten"] if x["nr"] == nr)
    with open(ORDNER / k["datei"], "rb") as f:
        felder = {"type": "tts", "title": titel, "train_mode": "fast", "visibility": "private",
                  "description": f"Klaus - entworfen: {meta['beschreibung']}"[:500], "texts": k["text"]}
        if k.get("id"):
            felder["voice_design_signatures"] = k["id"]
        r = requests.post(f"{API}/model", headers=_kopf(json_body=False), data=felder, files={"voices": (k["datei"], f, "audio/wav")},
                          timeout=120)
    if r.status_code not in (200, 201):
        raise _fehler(r)
    modell_id = r.json()["_id"]
    _env_setzen("FISH_STIMME", modell_id)
    return modell_id


def _env_setzen(name: str, wert: str) -> None:
    """Einen Wert in der .env setzen (UTF-8 ohne BOM, Dateirechte bleiben, andere Zeilen unveraendert)."""
    datei = BASE_DIR / ".env"
    zeilen = datei.read_text(encoding="utf-8").splitlines() if datei.exists() else []
    neu = [f"{name}={wert}" if z.startswith(f"{name}=") else z for z in zeilen]   # an Ort und Stelle ersetzen
    if f"{name}={wert}" not in neu:
        neu.append(f"{name}={wert}")
    with open(datei, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(neu) + "\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    befehl = sys.argv[1] if len(sys.argv) > 1 else ""
    if befehl == "entwerfen":
        for p in entwerfen(" ".join(sys.argv[2:]) or "tiefe, ruhige männliche Stimme, Mitte 30, freundlich und souverän"):
            print("Kandidat:", p)
            os.startfile(p)   # zum Anhoeren
            input("  Enter fuer den naechsten Kandidaten ...")
    elif befehl == "anlegen":
        print("Neue Klaus-Stimme:", anlegen(int(sys.argv[2])))
    elif befehl == "test":
        sprich(" ".join(sys.argv[2:]) or "Hallo Nikola, hier ist Klaus mit meiner neuen Stimme.")
    else:
        print(__doc__)
