"""
Klaus - Stimme (Text -> Audio)
Unterstuetzt zwei Arten von Stimmen, gewaehlt ueber KLAUS_STIMME in .env:
    fish  bzw.  fish:<modell-id>                 Fish Audio (bezahlt, eigene Klaus-Stimme, siehe fish.py)
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
    """name: Stimme, optional mit Tonhoehe/Tempo: "de-DE-SeraphinaMultilingualNeural@+38Hz@+12%" (Anime-Stil, stimmwahl.py)."""
    import edge_tts
    import miniaudio

    stimme, _, rest = name.partition("@")
    tonhoehe, _, tempo = rest.partition("@")
    extra = {k: v for k, v in (("pitch", tonhoehe), ("rate", tempo)) if v}

    async def laden() -> bytes:
        mp3 = b""
        async for teil in edge_tts.Communicate(text, stimme, **extra).stream():
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
    if kennung == "fish" or kennung.startswith("fish:"):
        import fish

        yield fish.audio(text, kennung[5:] or None)
        return
    if kennung.startswith("edge:"):
        yield _edge(kennung[5:], text)
        return
    pfad = Path(kennung)
    if not pfad.is_absolute():
        pfad = BASE_DIR / pfad
    if not pfad.exists():
        raise FileNotFoundError(f"Stimme nicht gefunden: {pfad}")
    yield from _piper_saetze(pfad, text)


def sprich(kennung: str, text: str, on_pegel=None, abbruch=None) -> None:
    """Spielt den Text ab. on_pegel bekommt waehrenddessen die Lautstaerke 0..1."""
    import time

    import sounddevice as sd

    if abbruch is None:
        import betrieb
        abbruch = betrieb.ruhe

    for audio, rate in saetze(kennung, text):
        import betrieb
        if betrieb.ruhe() or (abbruch and abbruch()):
            raise InterruptedError('Sprachausgabe gestoppt.')
        sd.play(audio, rate)
        if on_pegel or abbruch:
            schritt = int(rate * 0.03)
            start = time.perf_counter()
            while True:
                if betrieb.ruhe() or (abbruch and abbruch()):
                    sd.stop()
                    raise InterruptedError('Sprachausgabe gestoppt.')
                i = int((time.perf_counter() - start) * rate)
                if i >= len(audio):
                    break
                stueck = audio[i : i + schritt]
                if on_pegel:
                    on_pegel(min(1.0, float(np.sqrt((stueck ** 2).mean())) * 6))
                time.sleep(0.03)
            if on_pegel:
                on_pegel(0.0)
        sd.wait()


def name(kennung: str) -> str:
    if kennung == "fish" or kennung.startswith("fish:"):
        return "Fish Audio"
    return kennung[5:] if kennung.startswith("edge:") else Path(kennung).stem
