"""
Klaus - Stimme (Text -> Audio)
Unterstuetzt zwei Arten von Stimmen, gewaehlt ueber KLAUS_STIMME in .env:
    edge:de-DE-ConradNeural                      Microsoft-Neural-Stimme (online, sehr natuerlich)
    data/stimmen/de_DE-thorsten-high.onnx        Piper-Stimme (lokal, offline)
"""

import asyncio
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent

# Auswahl fuer die Stimmen-Probe (Microsoft, online)
EDGE_STIMMEN = [
    "de-DE-FlorianMultilingualNeural",
    "de-DE-SeraphinaMultilingualNeural",
    "de-DE-ConradNeural",
    "de-DE-KatjaNeural",
    "de-DE-KillianNeural",
    "de-DE-AmalaNeural",
    "de-AT-JonasNeural",
    "de-AT-IngridNeural",
    "en-US-AndrewMultilingualNeural",
    "en-US-AvaMultilingualNeural",
]

_piper_cache: dict = {}


def _edge(name: str, text: str) -> tuple[np.ndarray, int]:
    import edge_tts
    import miniaudio

    async def laden() -> bytes:
        mp3 = b""
        async for teil in edge_tts.Communicate(text, name).stream():
            if teil["type"] == "audio":
                mp3 += teil["data"]
        return mp3

    d = miniaudio.decode(asyncio.run(laden()), output_format=miniaudio.SampleFormat.FLOAT32, nchannels=1)
    return np.array(d.samples, dtype=np.float32), d.sample_rate


def _piper_saetze(pfad: Path, text: str):
    from piper import PiperVoice

    if pfad not in _piper_cache:
        _piper_cache[pfad] = PiperVoice.load(str(pfad))
    for teil in _piper_cache[pfad].synthesize(text):
        yield teil.audio_float_array, teil.sample_rate


def saetze(kennung: str, text: str):
    """Liefert (audio, rate)-Stuecke. Piper satzweise, Edge am Stueck."""
    if kennung.startswith("edge:"):
        yield _edge(kennung[5:], text)
        return
    pfad = Path(kennung)
    if not pfad.is_absolute():
        pfad = BASE_DIR / pfad
    if not pfad.exists():
        raise FileNotFoundError(f"Stimme nicht gefunden: {pfad}")
    yield from _piper_saetze(pfad, text)


def sprich(kennung: str, text: str, on_pegel=None) -> None:
    """Spielt den Text ab. on_pegel bekommt waehrenddessen die Lautstaerke 0..1."""
    import time

    import sounddevice as sd

    for audio, rate in saetze(kennung, text):
        sd.play(audio, rate)
        if on_pegel:
            schritt = int(rate * 0.03)
            start = time.perf_counter()
            while True:
                i = int((time.perf_counter() - start) * rate)
                if i >= len(audio):
                    break
                stueck = audio[i : i + schritt]
                on_pegel(min(1.0, float(np.sqrt((stueck ** 2).mean())) * 6))
                time.sleep(0.03)
            on_pegel(0.0)
        sd.wait()


def name(kennung: str) -> str:
    return kennung[5:] if kennung.startswith("edge:") else Path(kennung).stem
