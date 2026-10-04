"""
Klaus - Stimmen-Probe
Spielt Stimmen mit einem Beispielsatz vor und speichert sie als WAV in
data/stimmen/proben/. Am Ende Nummer eingeben -> wird in .env als KLAUS_STIMME
eingetragen.

Nutzung:
    .venv/Scripts/python src/stimmen_test.py           # Microsoft-Stimmen (online)
    .venv/Scripts/python src/stimmen_test.py --piper   # lokale Piper-Stimmen
"""

import re
import sys
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

import stimme

BASE_DIR = Path(__file__).resolve().parent.parent
STIMMEN_DIR = BASE_DIR / "data" / "stimmen"
PROBEN_DIR = STIMMEN_DIR / "proben"
ENV_PATH = BASE_DIR / ".env"

SATZ = (
    "Stimme {nr}. Hallo Nikola, hier ist Klaus. "
    "Ich habe drei neue Firmen ohne Website in Göppingen gefunden. Sollen wir anfangen?"
)


def setze_env(wert: str) -> None:
    text = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    zeile = f"KLAUS_STIMME={wert}"
    if re.search(r"^KLAUS_STIMME=.*$", text, re.M):
        text = re.sub(r"^KLAUS_STIMME=.*$", zeile, text, flags=re.M)
    else:
        text = text.rstrip("\n") + f"\n\n# Stimme fuer Klaus (edge:<Name> oder Pfad zu Piper-.onnx)\n{zeile}\n"
    ENV_PATH.write_text(text, encoding="utf-8")


def speichere_wav(pfad: Path, audio: np.ndarray, rate: int) -> None:
    with wave.open(str(pfad), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())


def main() -> None:
    if "--piper" in sys.argv:
        kennungen = [f"data/stimmen/{p.name}" for p in sorted(STIMMEN_DIR.glob("*.onnx"))]
    else:
        kennungen = [f"edge:{n}" for n in stimme.EDGE_STIMMEN]
    if not kennungen:
        print("Keine Stimmen gefunden.")
        return
    PROBEN_DIR.mkdir(parents=True, exist_ok=True)

    for nr, kennung in enumerate(kennungen, 1):
        print(f"  {nr}. {stimme.name(kennung)}")
        try:
            teile = list(stimme.saetze(kennung, SATZ.format(nr=nr)))
        except Exception as e:
            print(f"     ! fehlgeschlagen: {str(e)[:80]}")
            continue
        audio = np.concatenate([a for a, _ in teile])
        rate = teile[0][1]
        speichere_wav(PROBEN_DIR / f"{nr}-{stimme.name(kennung)}.wav", audio, rate)
        sd.play(audio, rate)
        sd.wait()

    print(f"\nProben gespeichert in {PROBEN_DIR} (zum nochmal Anhoeren).")
    wahl = input("Welche Stimme soll Klaus nehmen? Nummer (Enter = nichts aendern): ").strip()
    if wahl.isdigit() and 1 <= int(wahl) <= len(kennungen):
        gewaehlt = kennungen[int(wahl) - 1]
        setze_env(gewaehlt)
        print(f"Eingetragen: {stimme.name(gewaehlt)}. Klaus neu starten.")
    else:
        print("Nichts geaendert.")


if __name__ == "__main__":
    main()
