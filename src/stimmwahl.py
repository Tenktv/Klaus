"""
Klaus - mehrere Stimmen, umschaltbar, eigene dazu (data/stimmen/stimmen.json).

Arten:
    gemini   Geminis eigene Stimmen (Charon, Puck, Kore ...) - wirkt ab dem naechsten Gespraech
    edge     Microsoft-Neural-Stimmen, auch mit Tonhoehe/Tempo verstellt (Anime-Stil) - kostenlos, online
    piper    lokale .onnx-Stimmen aus data/stimmen/ (offline) - werden automatisch gefunden
    fish     Fish Audio (FISH_API_KEY): eigene Stimme beschreiben, Sprachprobe hochladen oder fertige Stimme
             von fish.audio per Link uebernehmen (z. B. Anime-Figuren aus der Community)

    stimmwahl.liste_text()                      alle Stimmen
    stimmwahl.waehlen("Anime-Mädchen")          umschalten
    stimmwahl.fish_uebernehmen("Gojo", "https://fish.audio/m/<id>")
    stimmwahl.klonen("Meine Stimme", pfad)      Sprachprobe (10-60 s, mp3/wav) -> eigene Fish-Stimme
    stimmwahl.entwerfen("Luna", "helle, verspielte Anime-Maedchenstimme")
    stimmwahl.pcm_strom(text)                   aktive Stimme als int16-PCM, 24 kHz (wie Gemini Live)

Fremde Stimmen (echte Menschen, Synchronsprecher) nur mit deren Erlaubnis bzw. nach den Regeln von Fish Audio nutzen.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
ORDNER = BASE_DIR / "data" / "stimmen"
DATEI = ORDNER / "stimmen.json"
EIGENE_PROBEN = ORDNER / "eigene"          # hier eigene Sprachproben ablegen: <Name>.mp3/.wav
RATE = 24000
_sperre = threading.Lock()

EINGEBAUT = [
    # Gemini (Stimme direkt vom Modell, niedrigste Verzoegerung)
    {"name": "Charon", "art": "gemini", "id": "Charon", "info": "tief, ruhig (Standard)"},
    {"name": "Puck", "art": "gemini", "id": "Puck", "info": "heiter, jung"},
    {"name": "Fenrir", "art": "gemini", "id": "Fenrir", "info": "energisch"},
    {"name": "Orus", "art": "gemini", "id": "Orus", "info": "fest, maennlich"},
    {"name": "Kore", "art": "gemini", "id": "Kore", "info": "klar, weiblich"},
    {"name": "Aoede", "art": "gemini", "id": "Aoede", "info": "hell, weiblich"},
    {"name": "Leda", "art": "gemini", "id": "Leda", "info": "jung, weiblich"},
    {"name": "Zephyr", "art": "gemini", "id": "Zephyr", "info": "hell, freundlich"},
    {"name": "Sulafat", "art": "gemini", "id": "Sulafat", "info": "warm"},
    {"name": "Achird", "art": "gemini", "id": "Achird", "info": "freundlich"},
    {"name": "Gacrux", "art": "gemini", "id": "Gacrux", "info": "reif, erfahren"},
    {"name": "Algenib", "art": "gemini", "id": "Algenib", "info": "rau, kratzig"},
    {"name": "Enceladus", "art": "gemini", "id": "Enceladus", "info": "hauchig, leise"},
    {"name": "Laomedeia", "art": "gemini", "id": "Laomedeia", "info": "beschwingt"},
    {"name": "Sadachbia", "art": "gemini", "id": "Sadachbia", "info": "lebhaft"},
    {"name": "Vindemiatrix", "art": "gemini", "id": "Vindemiatrix", "info": "sanft"},
    {"name": "Zubenelgenubi", "art": "gemini", "id": "Zubenelgenubi", "info": "lässig"},
    {"name": "Rasalgethi", "art": "gemini", "id": "Rasalgethi", "info": "sachlich, erklärend"},
    {"name": "Schedar", "art": "gemini", "id": "Schedar", "info": "ausgeglichen"},
    {"name": "Despina", "art": "gemini", "id": "Despina", "info": "weich, glatt"},
    # Microsoft (natuerlich, kostenlos)
    {"name": "Florian", "art": "edge", "id": "de-DE-FlorianMultilingualNeural", "info": "maennlich, natuerlich"},
    {"name": "Seraphina", "art": "edge", "id": "de-DE-SeraphinaMultilingualNeural", "info": "weiblich, natuerlich"},
    {"name": "Conrad", "art": "edge", "id": "de-DE-ConradNeural", "info": "maennlich, sachlich"},
    {"name": "Katja", "art": "edge", "id": "de-DE-KatjaNeural", "info": "weiblich, sachlich"},
    {"name": "Killian", "art": "edge", "id": "de-DE-KillianNeural", "info": "maennlich, jung"},
    {"name": "Amala", "art": "edge", "id": "de-DE-AmalaNeural", "info": "weiblich, jung"},
    # Anime-Stil (verstellte Tonhoehe und Tempo - keine Kopie einer echten Person)
    {"name": "Anime-Mädchen", "art": "edge", "id": "de-DE-SeraphinaMultilingualNeural", "tonhoehe": "+38Hz", "tempo": "+12%",
     "info": "hell, aufgedreht"},
    {"name": "Anime-Junge", "art": "edge", "id": "de-DE-FlorianMultilingualNeural", "tonhoehe": "+22Hz", "tempo": "+10%",
     "info": "jung, frech"},
    {"name": "Anime-Held", "art": "edge", "id": "de-DE-KillianNeural", "tonhoehe": "+8Hz", "tempo": "+8%",
     "info": "entschlossen"},
    {"name": "Anime-Bösewicht", "art": "edge", "id": "de-DE-ConradNeural", "tonhoehe": "-16Hz", "tempo": "-8%",
     "info": "tief, kuehl"},
    {"name": "Sensei", "art": "edge", "id": "de-DE-ConradNeural", "tonhoehe": "-6Hz", "tempo": "-12%",
     "info": "ruhig, weise"},
    {"name": "Chibi", "art": "edge", "id": "de-DE-AmalaNeural", "tonhoehe": "+55Hz", "tempo": "+18%",
     "info": "sehr hoch, niedlich"},
    # Microsoft: Oesterreich und Schweiz (kostenlos, ohne Schluessel)
    {"name": "Ingrid", "art": "edge", "id": "de-AT-IngridNeural", "info": "weiblich, österreichisch"},
    {"name": "Jonas", "art": "edge", "id": "de-AT-JonasNeural", "info": "männlich, österreichisch"},
    {"name": "Leni", "art": "edge", "id": "de-CH-LeniNeural", "info": "weiblich, schweizerisch"},
    {"name": "Jan", "art": "edge", "id": "de-CH-JanNeural", "info": "männlich, schweizerisch"},
    # Microsoft "Multilingual": sprechen Deutsch mit Akzent
    {"name": "Andrew", "art": "edge", "id": "en-US-AndrewMultilingualNeural", "info": "warm, amerikanischer Akzent"},
    {"name": "Ava", "art": "edge", "id": "en-US-AvaMultilingualNeural", "info": "freundlich, amerikanischer Akzent"},
    {"name": "Brian", "art": "edge", "id": "en-US-BrianMultilingualNeural", "info": "locker, amerikanischer Akzent"},
    {"name": "Emma", "art": "edge", "id": "en-US-EmmaMultilingualNeural", "info": "fröhlich, amerikanischer Akzent"},
    {"name": "Vivienne", "art": "edge", "id": "fr-FR-VivienneMultilingualNeural", "info": "französischer Akzent"},
    {"name": "Rémy", "art": "edge", "id": "fr-FR-RemyMultilingualNeural", "info": "französischer Akzent, männlich"},
    {"name": "Giuseppe", "art": "edge", "id": "it-IT-GiuseppeMultilingualNeural", "info": "italienischer Akzent"},
    # Figuren (verstellte Microsoft-Stimmen)
    {"name": "Erzähler", "art": "edge", "id": "de-DE-FlorianMultilingualNeural", "tonhoehe": "-4Hz", "tempo": "-10%",
     "info": "ruhig, wie ein Hörbuch"},
    {"name": "Opa", "art": "edge", "id": "de-DE-ConradNeural", "tonhoehe": "-22Hz", "tempo": "-18%", "info": "alt, gemütlich"},
    {"name": "Kind", "art": "edge", "id": "de-DE-KillianNeural", "tonhoehe": "+40Hz", "tempo": "+6%", "info": "jung, hell"},
    {"name": "Moderator", "art": "edge", "id": "de-DE-KillianNeural", "tonhoehe": "+4Hz", "tempo": "+20%",
     "info": "schnell, wie im Radio"},
    {"name": "Kriegerin", "art": "edge", "id": "de-DE-KatjaNeural", "tonhoehe": "-10Hz", "tempo": "+4%", "info": "fest, mutig"},
    {"name": "Magierin", "art": "edge", "id": "de-DE-SeraphinaMultilingualNeural", "tonhoehe": "+12Hz", "tempo": "-8%",
     "info": "sanft, geheimnisvoll"},
    {"name": "Riese", "art": "edge", "id": "de-DE-ConradNeural", "tonhoehe": "-35Hz", "tempo": "-12%", "info": "sehr tief"},
    # Lokal (Piper): laufen ohne Internet; beim ersten Auswaehlen automatisch heruntergeladen (~20-110 MB)
    {"name": "Thorsten", "art": "piper", "id": "data/stimmen/de_DE-thorsten-high.onnx", "laden": "de_DE-thorsten-high",
     "info": "männlich, offline, beste Qualität"},
    {"name": "Kerstin", "art": "piper", "id": "data/stimmen/de_DE-kerstin-low.onnx", "laden": "de_DE-kerstin-low",
     "info": "weiblich, offline"},
    {"name": "Ramona", "art": "piper", "id": "data/stimmen/de_DE-ramona-low.onnx", "laden": "de_DE-ramona-low",
     "info": "weiblich, offline"},
    {"name": "Eva", "art": "piper", "id": "data/stimmen/de_DE-eva_k-x_low.onnx", "laden": "de_DE-eva_k-x_low",
     "info": "weiblich, offline, sehr schnell"},
    {"name": "Karlsson", "art": "piper", "id": "data/stimmen/de_DE-karlsson-low.onnx", "laden": "de_DE-karlsson-low",
     "info": "männlich, offline"},
    {"name": "Pavoque", "art": "piper", "id": "data/stimmen/de_DE-pavoque-low.onnx", "laden": "de_DE-pavoque-low",
     "info": "männlich, offline"},
]


class StimmFehler(Exception):
    """Verstaendliche Meldung."""


# ------------------------------------------------------------------ Speicher
def _laden() -> dict:
    try:
        d = json.loads(DATEI.read_text(encoding="utf-8"))
        return {"aktiv": d.get("aktiv", ""), "eigene": d.get("eigene", [])}
    except (OSError, ValueError):
        return {"aktiv": "", "eigene": []}


def _speichern(d: dict) -> None:
    ORDNER.mkdir(parents=True, exist_ok=True)
    tmp = DATEI.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DATEI)


def _piper() -> list[dict]:
    """Weitere .onnx-Stimmen, die jemand selbst in data/stimmen/ gelegt hat (die eingebauten nicht doppelt)."""
    bekannt = {Path(s["id"]).name for s in EINGEBAUT if s["art"] == "piper"}
    return [{"name": p.stem.replace("de_DE-", "").replace("-", " ").title(), "art": "piper",
             "id": p.relative_to(BASE_DIR).as_posix(), "info": "lokal, offline"}
            for p in sorted(ORDNER.glob("*.onnx")) if p.name not in bekannt] if ORDNER.exists() else []


def geladen(s: dict) -> bool:
    return s["art"] != "piper" or (BASE_DIR / s["id"]).exists()


def piper_laden(s: dict) -> None:
    """Offline-Stimme von Piper herunterladen (huggingface.co/rhasspy/piper-voices) nach data/stimmen/."""
    from piper.download_voices import download_voice

    ORDNER.mkdir(parents=True, exist_ok=True)
    download_voice(s["laden"], ORDNER)
    if not geladen(s):
        raise StimmFehler(f"Die Stimme {s['name']} kam nicht vollständig an.")


def alle() -> list[dict]:
    return EINGEBAUT + _piper() + [{**s, "eigen": True} for s in _laden()["eigene"]]


def _normal(name: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]", "", name.lower())


def finden(name: str) -> dict:
    n = _normal(name)
    if not n:
        raise StimmFehler("Welche Stimme? Mit /stimmen siehst du alle.")
    liste = alle()
    treffer = [s for s in liste if _normal(s["name"]) == n] or [s for s in liste if n in _normal(s["name"])]
    if not treffer:
        raise StimmFehler(f"Die Stimme „{name}“ kenne ich nicht. Mit /stimmen siehst du alle.")
    return treffer[0]


def _standard() -> dict:
    """Ohne Auswahl: wie bisher (Fish, wenn eingerichtet, sonst Geminis GEMINI_STIMME)."""
    import fish

    if fish.bereit() and os.getenv("KLAUS_STIMME_ANBIETER", "fish").strip().lower() == "fish":
        return {"name": "Fish (Klaus)", "art": "fish", "id": fish.STIMME}
    g = os.getenv("GEMINI_STIMME", "Charon").strip() or "Charon"
    return next((s for s in EINGEBAUT if s["art"] == "gemini" and s["id"].lower() == g.lower()),
                {"name": g, "art": "gemini", "id": g})


def aktiv() -> dict:
    name = _laden()["aktiv"]
    if name:
        try:
            return finden(name)
        except StimmFehler:
            pass
    return _standard()


_ausfall = {"bis": 0.0, "grund": ""}   # externe Stimme (Fish, Microsoft ...) ging nicht -> eine Weile Gemini-Stimme


def extern_sperren(grund: str, minuten: float = 30) -> None:
    import time
    _ausfall.update(bis=time.time() + minuten * 60, grund=grund)


def extern_gesperrt() -> bool:
    import time
    return time.time() < _ausfall["bis"]


def extern_aktiv() -> bool:
    """Spricht eine andere Stimme als Gemini selbst? (dann: Gemini denkt, diese Stimme spricht)"""
    return aktiv()["art"] != "gemini"


def gemini_stimme() -> str:
    s = aktiv()
    return s["id"] if s["art"] == "gemini" else (os.getenv("GEMINI_STIMME", "Charon").strip() or "Charon")


def lokale_kennung(s: dict | None = None) -> str | None:
    """Kennung fuer stimme.py (lokale Kette ohne Gemini)."""
    s = s or aktiv()
    if s["art"] == "edge":
        return "edge:" + "@".join([s["id"], s.get("tonhoehe", ""), s.get("tempo", "")]).rstrip("@")
    if s["art"] == "piper":
        return s["id"]
    if s["art"] == "fish":
        return f"fish:{s['id']}"
    return None


# ------------------------------------------------------------------ Umschalten / Verwalten
def waehlen(name: str) -> str:
    s = finden(name)
    if s["art"] == "fish" and not os.getenv("FISH_API_KEY", "").strip():
        raise StimmFehler("Für Fish-Stimmen fehlt FISH_API_KEY in der .env.")
    if not geladen(s):
        if not s.get("laden"):
            raise StimmFehler(f"Die Datei für {s['name']} fehlt ({s['id']}).")

        def los() -> None:
            try:
                piper_laden(s)
                print(f"[Stimme] {s['name']} heruntergeladen", flush=True)
                _aktiv_setzen(s)
            except Exception as e:
                print(f"[Stimme] {s['name']} laden ging nicht: {str(e)[:120]}", flush=True)
        threading.Thread(target=los, daemon=True, name="stimme-laden").start()
        return (f"Ich lade die Offline-Stimme „{s['name']}“ herunter (einmalig, etwa eine Minute). "
                "Danach spreche ich mit ihr – auch ganz ohne Internet.")
    return _aktiv_setzen(s)


def _aktiv_setzen(s: dict) -> str:
    vorher = aktiv()
    _ausfall["bis"] = 0.0   # neue Stimme -> wieder probieren
    with _sperre:
        d = _laden()
        d["aktiv"] = s["name"]
        _speichern(d)
    # Wechsel von/zu einer Gemini-Stimme braucht eine neue Gemini-Sitzung, andere Stimmen gelten ab dem naechsten Satz
    wann = " – gilt ab dem nächsten Gespräch" if "gemini" in (s["art"], vorher["art"]) and s["name"] != vorher["name"] else ""
    return f"🎙 Ich spreche jetzt mit der Stimme „{s['name']}“{wann}."


def _eigene_speichern(eintrag: dict) -> str:
    if any(_normal(s["name"]) == _normal(eintrag["name"]) for s in EINGEBAUT + _piper()):
        raise StimmFehler(f"„{eintrag['name']}“ gibt es schon als eingebaute Stimme – nimm einen anderen Namen.")
    with _sperre:
        d = _laden()
        d["eigene"] = [s for s in d["eigene"] if _normal(s["name"]) != _normal(eintrag["name"])] + [eintrag]
        _speichern(d)
    return f"➕ Stimme „{eintrag['name']}“ hinzugefügt. Umschalten: „nimm die Stimme {eintrag['name']}“."


def edge_hinzufuegen(name: str, basis: str, tonhoehe: str = "", tempo: str = "") -> str:
    """Eigene Variante einer Microsoft-Stimme, z. B. ("Kitsune", "Seraphina", "+30Hz", "+15%")."""
    b = finden(basis)
    if b["art"] != "edge":
        raise StimmFehler("Verstellen geht nur mit Microsoft-Stimmen (z. B. Seraphina, Florian, Conrad).")
    for wert, einheit in ((tonhoehe, "Hz"), (tempo, "%")):
        if wert and not re.fullmatch(rf"[+-]\d{{1,3}}{einheit}", wert):
            raise StimmFehler(f"Tonhöhe z. B. +20Hz, Tempo z. B. +10% (bekommen: {wert}).")
    return _eigene_speichern({"name": name.strip()[:30], "art": "edge", "id": b["id"],
                              "tonhoehe": tonhoehe or b.get("tonhoehe", ""), "tempo": tempo or b.get("tempo", ""),
                              "info": f"eigene Variante von {b['name']}"})


def fish_uebernehmen(name: str, quelle: str) -> str:
    """Fertige Stimme von fish.audio (Link https://fish.audio/m/<id> oder die 32-stellige ID)."""
    m = re.search(r"([0-9a-f]{32})", quelle or "")
    if not m:
        raise StimmFehler("Ich brauche den Link der Stimme von fish.audio (…/m/<id>) oder ihre 32-stellige ID.")
    if not os.getenv("FISH_API_KEY", "").strip():
        raise StimmFehler("Für Fish-Stimmen fehlt FISH_API_KEY in der .env (fish.audio → API).")
    return _eigene_speichern({"name": name.strip()[:30], "art": "fish", "id": m.group(1), "info": "von fish.audio"})


def _fish_modell(datei: Path, titel: str, text: str = "", signatur: str = "") -> str:
    import requests

    import fish

    felder = {"type": "tts", "title": titel, "train_mode": "fast", "visibility": "private",
              "description": f"{titel} - eigene Stimme fuer Klaus"[:500]}
    if text:
        felder["texts"] = text
    if signatur:
        felder["voice_design_signatures"] = signatur
    art = "audio/wav" if datei.suffix.lower() == ".wav" else "audio/mpeg"
    with open(datei, "rb") as f:
        r = requests.post(f"{fish.API}/model", headers=fish._kopf(json_body=False), data=felder,
                          files={"voices": (datei.name, f, art)}, timeout=180)
    if r.status_code not in (200, 201):
        raise StimmFehler(str(fish._fehler(r)))
    return r.json()["_id"]


def klonen(name: str, pfad: str | Path | None = None) -> str:
    """Eigene Sprachprobe -> Fish-Stimme. Ohne Pfad: data/stimmen/eigene/<Name>.mp3|wav|m4a|ogg.
    Nur die eigene Stimme oder mit Erlaubnis der Person."""
    if pfad:
        datei = Path(pfad)
    else:
        kandidaten = [p for p in EIGENE_PROBEN.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")
                      and _normal(p.stem) == _normal(name)] if EIGENE_PROBEN.exists() else []
        if not kandidaten:
            EIGENE_PROBEN.mkdir(parents=True, exist_ok=True)
            raise StimmFehler(f"Leg eine Sprachprobe (10–60 Sekunden, mp3 oder wav) als „{name}.mp3“ in den Ordner "
                              f"{EIGENE_PROBEN} und sag dann nochmal Bescheid.")
        datei = kandidaten[0]
    if not datei.exists():
        raise StimmFehler(f"Die Datei {datei} gibt es nicht.")
    if not os.getenv("FISH_API_KEY", "").strip():
        raise StimmFehler("Für eigene Stimmen fehlt FISH_API_KEY in der .env (fish.audio → API).")
    modell = _fish_modell(datei, name)
    return _eigene_speichern({"name": name.strip()[:30], "art": "fish", "id": modell, "info": f"aus {datei.name}"})


def entwerfen(name: str, beschreibung: str) -> str:
    """Neue Stimme nach Beschreibung (Fish Voice Design), z. B. "helle, verspielte Anime-Maedchenstimme"."""
    import fish

    if not os.getenv("FISH_API_KEY", "").strip():
        raise StimmFehler("Für entworfene Stimmen fehlt FISH_API_KEY in der .env (fish.audio → API).")
    try:
        pfade = fish.entwerfen(beschreibung, n=1)
    except fish.FishFehler as e:
        raise StimmFehler(str(e)) from e
    if not pfade:
        raise StimmFehler("Fish hat keine Stimme geliefert – andere Beschreibung probieren.")
    meta = json.loads((fish.ORDNER / "kandidaten.json").read_text(encoding="utf-8"))["kandidaten"][0]
    modell = _fish_modell(pfade[0], name, meta.get("text", ""), meta.get("id") or "")
    return _eigene_speichern({"name": name.strip()[:30], "art": "fish", "id": modell, "info": beschreibung[:60]})


def loeschen(name: str) -> str:
    s = finden(name)
    if not s.get("eigen"):
        raise StimmFehler("Eingebaute Stimmen kann ich nicht löschen, nur eigene.")
    with _sperre:
        d = _laden()
        d["eigene"] = [x for x in d["eigene"] if x["name"] != s["name"]]
        if d["aktiv"] == s["name"]:
            d["aktiv"] = ""
        _speichern(d)
    return f"🗑 Stimme „{s['name']}“ gelöscht."


def liste_text() -> str:
    jetzt = aktiv()["name"]
    gruppen = {"gemini": "Gemini (direkt, schnellste)", "edge": "Microsoft & Anime-Stil", "piper": "Lokal (offline)",
               "fish": "Eigene & Fish Audio"}
    z = [f"🎙 Stimmen – aktiv: {jetzt}"]
    for art, titel in gruppen.items():
        liste = [s for s in alle() if s["art"] == art]
        if liste:
            z.append(f"{titel}:")
            z += [f"{'▶' if s['name'] == jetzt else '•'} {s['name']} – {s.get('info', '')}"
                  + ("" if geladen(s) else " (wird beim Auswählen geladen)") for s in liste]
    z.append("Umschalten: „nimm die Stimme Anime-Mädchen“ · Eigene: Stimme beschreiben, Sprachprobe oder fish.audio-Link.")
    return "\n".join(z)


# ------------------------------------------------------------------ Audio
def _resample(x: np.ndarray, rate: int) -> np.ndarray:
    if rate == RATE or not len(x):
        return x
    n = int(len(x) * RATE / rate)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def _int16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()


def pcm_strom(text: str, s: dict | None = None):
    """Aktive (oder gegebene) Stimme -> PCM-Stuecke (bytes, int16, 24 kHz, mono) fuer die Gemini-Live-Wiedergabe."""
    s = s or aktiv()
    if s["art"] == "fish":
        import fish

        yield from fish.pcm_strom(text, s["id"])
        return
    if s["art"] == "gemini":
        raise StimmFehler("Gemini-Stimmen spricht Gemini selbst.")
    import stimme

    for audio, rate in stimme.saetze(lokale_kennung(s), text):
        daten = _int16(_resample(np.asarray(audio, dtype=np.float32), rate))
        for i in range(0, len(daten), 9600):   # 0,2 s je Stueck
            yield daten[i:i + 9600]


def befehl(eingabe: str) -> str:
    """/stimmen oder /stimme <Name> (Telegram, ohne KI)."""
    teile = eingabe.strip().split(maxsplit=1)
    try:
        return waehlen(teile[1]) if len(teile) > 1 and teile[0].lower() == "/stimme" else liste_text()
    except StimmFehler as e:
        return str(e)
