"""
Klaus - YouTube: Kanal-Statistik, Live-Status und Live-Chat mitlesen/vorlesen (wie beim Twitch-Chat).

.env (traegt man im Verbindungen-Fenster ein):
    YOUTUBE_KANAL=@deinkanal     Handle (oder Kanal-ID UC...)
    YOUTUBE_API_KEY=...          Google Cloud -> "YouTube Data API v3" aktivieren -> Anmeldedaten -> API-Schluessel

Nur lesen, Klaus schreibt nie in den YouTube-Chat. Kontingent: 10.000 Einheiten am Tag (kostenlos). Die Live-Suche
kostet 100, deshalb sucht Klaus nur auf Wunsch ("lies den YouTube-Chat") und nicht dauernd im Hintergrund.
"""
from __future__ import annotations

import os
import re
import threading

API = "https://www.googleapis.com/youtube/v3"
MIN_TAKT = 8          # Sekunden zwischen Chat-Abfragen (YouTube nennt oft weniger - schont das Kontingent)

_z = {"kanal": ("", ""), "chat": None}


def _log(text: str) -> None:
    print(f"[YouTube] {text}")


def kanal_eingabe() -> str:
    return os.getenv("YOUTUBE_KANAL", "").strip()


def eingerichtet() -> bool:
    return bool(kanal_eingabe() and os.getenv("YOUTUBE_API_KEY", "").strip())


def normalisieren(wert: str) -> str:
    """youtube.com/@name, @name, name oder Kanal-ID -> @name bzw. UC..."""
    w = wert.strip()
    m = re.search(r"youtube\.com/(?:channel/(UC[\w-]{22})|(@[\w.-]+))", w)
    if m:
        w = m.group(1) or m.group(2)
    if re.fullmatch(r"UC[\w-]{22}", w):
        return w
    w = w.lstrip("@")
    if not re.fullmatch(r"[\w.-]{3,30}", w):
        raise ValueError("Das sieht nicht nach einem YouTube-Kanal aus – nimm den Handle, z. B. @deinkanal.")
    return "@" + w


def _get(pfad: str, **params) -> dict:
    import requests

    key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("YouTube ist nicht verbunden: sag „verbinde YouTube“ und trag den API-Schlüssel ein.")
    r = requests.get(f"{API}/{pfad}", params={**params, "key": key}, timeout=10)
    if r.status_code != 200:
        try:
            fehler = r.json()["error"]
            grund = (fehler.get("errors") or [{}])[0].get("reason", "")
            text = fehler.get("message", "")
        except (ValueError, KeyError, TypeError):
            grund, text = "", r.text
        if grund == "quotaExceeded":
            raise RuntimeError("Das YouTube-Kontingent für heute ist aufgebraucht (morgen geht's wieder).")
        if grund in ("keyInvalid", "API_KEY_INVALID") or "API key not valid" in text:
            raise RuntimeError("Der YouTube-API-Schlüssel stimmt nicht.")
        if grund == "accessNotConfigured" or "has not been used" in text:
            raise RuntimeError("In Google Cloud ist die „YouTube Data API v3“ noch nicht aktiviert.")
        raise RuntimeError(f"YouTube sagt ({r.status_code}): {re.sub(r'<[^>]+>', '', text)[:140]}")
    return r.json()


def kanal_id() -> str:
    eingabe = kanal_eingabe()
    if not eingabe:
        raise RuntimeError("Kein YouTube-Kanal eingetragen.")
    if re.fullmatch(r"UC[\w-]{22}", eingabe):
        return eingabe
    if _z["kanal"][0] == eingabe:
        return _z["kanal"][1]
    items = _get("channels", part="id", forHandle=eingabe if eingabe.startswith("@") else "@" + eingabe).get("items") or []
    if not items:
        raise RuntimeError(f"Den YouTube-Kanal {eingabe} finde ich nicht.")
    _z["kanal"] = (eingabe, items[0]["id"])
    return items[0]["id"]


def _zahl(wert) -> str:
    return f"{int(wert or 0):,}".replace(",", ".")


def kanal_info() -> str:
    items = _get("channels", part="snippet,statistics", id=kanal_id()).get("items") or []
    if not items:
        raise RuntimeError("Kanal nicht gefunden.")
    k = items[0]
    s = k.get("statistics", {})
    abos = "versteckt" if s.get("hiddenSubscriberCount") else _zahl(s.get("subscriberCount"))
    return (f"YouTube-Kanal „{k['snippet']['title']}“: {abos} Abonnenten, {_zahl(s.get('videoCount'))} Videos, "
            f"{_zahl(s.get('viewCount'))} Aufrufe insgesamt.")


def live_video() -> str:
    """ID des laufenden Livestreams oder "" (kostet 100 Einheiten)."""
    items = _get("search", part="id", channelId=kanal_id(), eventType="live", type="video", maxResults=1).get("items") or []
    return items[0]["id"]["videoId"] if items else ""


def status() -> str:
    teile = [kanal_info()]
    vid = live_video()
    if vid:
        d = (_get("videos", part="liveStreamingDetails,snippet", id=vid).get("items") or [{}])[0]
        zuschauer = d.get("liveStreamingDetails", {}).get("concurrentViewers")
        teile.append(f"Du bist live: „{d.get('snippet', {}).get('title', '')}“"
                     + (f" mit {_zahl(zuschauer)} Zuschauern." if zuschauer else "."))
    else:
        teile.append("Gerade nicht live.")
    if chat_laeuft():
        teile.append("Den YouTube-Chat lese ich mit.")
    return " ".join(teile)


# ------------------------------------------------------------------ Live-Chat
def chat_laeuft() -> bool:
    return bool(_z["chat"] and _z["chat"].faden.is_alive())


class YouTubeChat:
    """Fragt den Live-Chat ab und gibt neue Nachrichten an stream.py weiter (gleiche Behandlung wie Twitch)."""

    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id
        self.halt = threading.Event()
        self.faden = threading.Thread(target=self._lauf, daemon=True, name="youtube-chat")

    def _lauf(self) -> None:
        import stream

        seite, erste, fehler = "", True, 0
        while not self.halt.is_set():
            try:
                params = {"liveChatId": self.chat_id, "part": "snippet,authorDetails", "maxResults": 200}
                if seite:
                    params["pageToken"] = seite
                d = _get("liveChat/messages", **params)
                fehler = 0
            except RuntimeError as e:
                fehler += 1
                text = str(e)
                if "Kontingent" in text or "liveChatEnded" in text or "403" in text or "404" in text or fehler >= 5:
                    _log(f"Chat beendet: {text[:120]}")
                    break
                self.halt.wait(30)
                continue
            except Exception as e:
                fehler += 1
                _log(f"Chat-Abfrage: {str(e)[:120]}")
                if fehler >= 5:
                    break
                self.halt.wait(30)
                continue
            seite = d.get("nextPageToken", "")
            if not erste:   # beim Start nicht den alten Verlauf vorlesen
                for n in d.get("items", []):
                    try:
                        verarbeite(n, stream)
                    except Exception as e:
                        _log(f"Nachricht uebersprungen: {e}")
            erste = False
            if d.get("offlineAt"):
                _log("Livestream ist vorbei.")
                break
            self.halt.wait(max(MIN_TAKT, int(d.get("pollingIntervalMillis") or 0) / 1000))
        _z["chat"] = None if _z["chat"] is self else _z["chat"]


def verarbeite(n: dict, stream) -> None:
    s, a = n.get("snippet", {}), n.get("authorDetails", {})
    name = a.get("displayName") or "Jemand"
    art = s.get("type")
    if art == "textMessageEvent":
        stream.fremde_nachricht("youtube", a.get("channelId", name), name, s.get("displayMessage", ""),
                                eigener=bool(a.get("isChatOwner")))
    elif art == "superChatEvent":
        stream.danke("superchat", name, c=s.get("superChatDetails", {}).get("amountDisplayString", "etwas"))
    elif art in ("newSponsorEvent", "membershipGiftingEvent"):
        stream.danke("mitglied", name)


def chat_starten() -> str:
    import stream

    if chat_laeuft():
        return "Den YouTube-Chat lese ich schon mit."
    vid = live_video()
    if not vid:
        return "Du bist auf YouTube gerade nicht live – sag es mir nochmal, wenn der Stream läuft."
    d = (_get("videos", part="liveStreamingDetails", id=vid).get("items") or [{}])[0]
    chat_id = d.get("liveStreamingDetails", {}).get("activeLiveChatId")
    if not chat_id:
        return "Dein Livestream hat keinen Live-Chat (ist er deaktiviert?)."
    _z["chat"] = YouTubeChat(chat_id)
    _z["chat"].faden.start()
    stream.vorleser_starten()
    return "Okay, ich lese den YouTube-Chat mit."


def chat_stoppen() -> str:
    if not chat_laeuft():
        return "Den YouTube-Chat lese ich gerade nicht mit."
    _z["chat"].halt.set()
    _z["chat"] = None
    return "Okay, YouTube-Chat aus."
