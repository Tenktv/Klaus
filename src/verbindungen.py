"""
Klaus - Verbindungen zu Plattformen: Twitch, YouTube, X, Instagram, Discord und jede andere ueber einen Webhook.

Jeder traegt seine EIGENEN Zugaenge ein - im Fenster "Verbindungen" (Taskleisten-Menue oder "Klaus, verbinde Twitch").
Die Werte landen nur in der .env auf diesem PC: nie bei Gemini, nie im Chat-Verlauf, nie in Telegram.

    twitch     Chat mitlesen/vorlesen (nur Kanalname); mit eigener App + Anmeldung auch Clips, Zuschauerzahl, Follower-Dank
    youtube    Kanal-Statistik, Live-Status, Live-Chat mitlesen/vorlesen (youtube.py)
    x          Posts veroeffentlichen (eigene App im X-Entwicklerportal, Lesen+Schreiben)
    instagram  Follower/Beitraege ansehen, Bild mit Text posten (Business- oder Creator-Konto)
    discord    Nachrichten in einen Kanal schicken (Webhook des Kanals)
    webhook    jede andere Plattform (TikTok, LinkedIn, Facebook, ...) ueber Zapier, Make, IFTTT oder n8n:
               Klaus schickt {"text": ..., "bild_url": ...} an die Webhook-Adresse, der Dienst postet weiter

Sicherheit: Alles, was oeffentlich wird (Post, Nachricht), laeuft ueber das Freigabe-Gate (Art "posten").
Klaus legt keine Konten an und meldet sich nirgends mit Passwort an - nur offizielle Schnittstellen mit deinen Schluesseln.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_DATEI = BASE_DIR / ".env"

try:
    from dotenv import load_dotenv
    load_dotenv(ENV_DATEI)
except ImportError:
    pass


@dataclass
class Feld:
    env: str
    label: str
    geheim: bool = False
    hinweis: str = ""


@dataclass
class Plattform:
    id: str
    name: str
    kann: str
    anleitung: list[str]
    link: str
    felder: list[Feld] = field(default_factory=list)
    pflicht: tuple[str, ...] = ()
    posten: bool = False


PLATTFORMEN: dict[str, Plattform] = {p.id: p for p in [
    Plattform(
        "twitch", "Twitch",
        "Chat mitlesen und vorlesen, neue Leute begrüßen, Chat-Befehle (!klaus). Mit eigener App zusätzlich: "
        "Clips, Zuschauerzahl, Danke für Follows.",
        ["Für den Chat reicht dein Kanalname – fertig.",
         "Für Clips: auf dev.twitch.tv/console → „Anwendung registrieren“, Kategorie „Application Integration“, "
         "Client-Typ „Öffentlich“, Weiterleitung http://localhost.",
         "Client-ID hier eintragen, speichern, dann „Bei Twitch anmelden“ und den Code im Browser bestätigen."],
        "https://dev.twitch.tv/console/apps",
        [Feld("TWITCH_KANAL", "Kanalname", hinweis="z. B. deinkanal (ohne twitch.tv/)"),
         Feld("TWITCH_CLIENT_ID", "Client-ID (optional)", hinweis="nur für Clips / Zuschauerzahl / Follower-Dank"),
         Feld("TWITCH_CLIENT_SECRET", "Client-Geheimnis (optional)", geheim=True, hinweis="nur bei Client-Typ „Vertraulich“")],
        ("TWITCH_KANAL",)),
    Plattform(
        "youtube", "YouTube",
        "Abos und Aufrufe, ob du live bist, Live-Chat mitlesen und vorlesen, Danke für Super Chats und Mitglieder.",
        ["Auf console.cloud.google.com ein Projekt anlegen (kostenlos).",
         "„YouTube Data API v3“ suchen und aktivieren.",
         "Anmeldedaten → „Anmeldedaten erstellen“ → „API-Schlüssel“, kopieren und hier eintragen.",
         "Dazu deinen Kanal-Handle, z. B. @deinkanal."],
        "https://console.cloud.google.com/apis/library/youtube.googleapis.com",
        [Feld("YOUTUBE_KANAL", "Kanal", hinweis="@deinkanal oder Link zum Kanal"),
         Feld("YOUTUBE_API_KEY", "API-Schlüssel", geheim=True)],
        ("YOUTUBE_KANAL", "YOUTUBE_API_KEY")),
    Plattform(
        "x", "X (Twitter)",
        "Posts veröffentlichen („poste auf X: Stream startet gleich“) – immer erst nach deiner Freigabe.",
        ["Auf developer.x.com anmelden (Free-Zugang reicht zum Posten) und im Dashboard eine App öffnen.",
         "Bei „User authentication settings“: App-Rechte „Read and write“ wählen, speichern.",
         "Unter „Keys and tokens“: API Key + Secret und danach Access Token + Secret erzeugen "
         "(erst NACH dem Umstellen auf „Read and write“, sonst darf er nicht posten).",
         "Alle vier hier eintragen."],
        "https://developer.x.com/en/portal/dashboard",
        [Feld("X_API_KEY", "API Key", geheim=True), Feld("X_API_SECRET", "API Key Secret", geheim=True),
         Feld("X_ACCESS_TOKEN", "Access Token", geheim=True), Feld("X_ACCESS_SECRET", "Access Token Secret", geheim=True)],
        ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"), posten=True),
    Plattform(
        "instagram", "Instagram",
        "Follower und letzte Beiträge ansehen, Bild mit Text posten – immer erst nach deiner Freigabe. "
        "Braucht ein Business- oder Creator-Konto.",
        ["In der Instagram-App: Einstellungen → Kontotyp → zu „Professionell“ (Creator oder Business) wechseln.",
         "Auf developers.facebook.com eine App vom Typ „Business“ anlegen und das Produkt „Instagram“ hinzufügen.",
         "Dort „API-Einrichtung mit Instagram-Login“: dein Konto hinzufügen und einen Zugriffstoken erzeugen.",
         "Token und die angezeigte Instagram-Konto-ID hier eintragen."],
        "https://developers.facebook.com/apps",
        [Feld("INSTAGRAM_KONTO_ID", "Instagram-Konto-ID", hinweis="Zahl, steht neben dem Token"),
         Feld("INSTAGRAM_TOKEN", "Zugriffstoken", geheim=True)],
        ("INSTAGRAM_KONTO_ID", "INSTAGRAM_TOKEN"), posten=True),
    Plattform(
        "discord", "Discord",
        "Nachrichten in einen Kanal deines Servers schicken („sag auf Discord: ich bin live“) – nach deiner Freigabe.",
        ["In Discord: Servereinstellungen → Integrationen → Webhooks → „Neuer Webhook“.",
         "Kanal wählen, „Webhook-URL kopieren“ und hier eintragen."],
        "https://support.discord.com/hc/de/articles/228383668",
        [Feld("DISCORD_WEBHOOK", "Webhook-URL", geheim=True)],
        ("DISCORD_WEBHOOK",), posten=True),
    Plattform(
        "webhook", "Andere Plattform",
        "Jede andere Plattform (TikTok, LinkedIn, Facebook, Threads, Bluesky, Slack …) über Zapier, Make, IFTTT oder n8n: "
        "Klaus schickt den Text an deine Webhook-Adresse, der Dienst postet ihn weiter – nach deiner Freigabe.",
        ["Bei Zapier/Make/IFTTT/n8n einen Ablauf mit Auslöser „Webhook“ (Catch Hook) anlegen.",
         "Als Aktion z. B. „Post auf LinkedIn erstellen“ und das Feld „text“ einsetzen.",
         "Die Webhook-Adresse hier eintragen und einen Namen geben (so sagst du es Klaus: „poste auf LinkedIn …“).",
         "Klaus schickt: {\"text\": \"…\", \"bild_url\": \"…\", \"von\": \"Klaus\"}."],
        "https://zapier.com/apps/webhook/integrations",
        [Feld("_NAME", "Name der Plattform", hinweis="z. B. LinkedIn, TikTok"),
         Feld("_URL", "Webhook-Adresse", geheim=True, hinweis="https://…")],
        ("_NAME", "_URL"), posten=True),
]}

ALIASE = {"twitter": "x", "insta": "instagram", "ig": "instagram", "yt": "youtube", "you tube": "youtube",
          "discord": "discord", "andere": "webhook", "eigene": "webhook"}


# ------------------------------------------------------------------ .env
def env_setzen(name: str, wert: str) -> None:
    """Wert in der .env setzen (UTF-8, andere Zeilen unveraendert) und sofort fuer diesen Prozess gueltig machen."""
    zeilen = ENV_DATEI.read_text(encoding="utf-8").splitlines() if ENV_DATEI.exists() else []
    neu, gesetzt = [], False
    for z in zeilen:
        if z.lstrip("﻿").startswith(f"{name}="):
            if not gesetzt:
                neu.append(f"{name}={wert}")
            gesetzt = True
        else:
            neu.append(z)
    if not gesetzt:
        neu.append(f"{name}={wert}")
    ENV_DATEI.parent.mkdir(parents=True, exist_ok=True)
    with open(ENV_DATEI, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(neu) + "\n")
    os.environ[name] = wert


def _wert(name: str) -> str:
    return os.getenv(name, "").strip()


def webhooks() -> dict[str, str]:
    """Eigene Plattformen: Name -> Adresse (WEBHOOK_LINKEDIN=... in der .env)."""
    return {k[len("WEBHOOK_"):].replace("_", " ").title(): v.strip() for k, v in os.environ.items()
            if k.startswith("WEBHOOK_") and v.strip()}


def webhook_schluessel(name: str) -> str:
    return "WEBHOOK_" + re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")


def finde(eingabe: str) -> str:
    """'Twitter', 'insta', 'LinkedIn' -> Plattform-ID (eigene Webhooks: 'webhook:Linkedin') oder ''."""
    e = (eingabe or "").strip().lower()
    if e in PLATTFORMEN:
        return e
    if e in ALIASE:
        return ALIASE[e]
    for pid, p in PLATTFORMEN.items():
        if e and (e == p.name.lower() or e.startswith(pid) and pid != "x"):
            return pid
    for name in webhooks():
        if e == name.lower():
            return f"webhook:{name}"
    return ""


def anzeige_name(pid: str) -> str:
    if pid.startswith("webhook:"):
        return pid.split(":", 1)[1]
    p = PLATTFORMEN.get(pid)
    return p.name if p else pid


# ------------------------------------------------------------------ Eingaben pruefen
def normalisieren(env: str, wert: str) -> str:
    w = re.sub(r"[\r\n\t]", "", wert).strip()
    if not w:
        return ""
    if env == "TWITCH_KANAL":
        w = re.sub(r"^(?:https?://)?(?:www\.)?twitch\.tv/", "", w, flags=re.I).strip("/#@ ").lower()
        if not re.fullmatch(r"[a-z0-9_]{3,25}", w):
            raise ValueError("Der Twitch-Kanalname hat 3–25 Zeichen: Buchstaben, Ziffern, Unterstrich.")
    elif env == "YOUTUBE_KANAL":
        import youtube
        w = youtube.normalisieren(w)
    elif env == "INSTAGRAM_KONTO_ID":
        if not w.isdigit():
            raise ValueError("Die Instagram-Konto-ID ist eine Zahl (steht in der Meta-App neben dem Token).")
    elif env == "DISCORD_WEBHOOK":
        if not re.fullmatch(r"https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+", w):
            raise ValueError("Das ist keine Discord-Webhook-URL (sie beginnt mit https://discord.com/api/webhooks/).")
    elif env == "_URL":
        teile = urllib.parse.urlparse(w)
        lokal = teile.hostname in ("localhost", "127.0.0.1")
        if not (teile.scheme == "https" or (teile.scheme == "http" and lokal)) or not teile.hostname:
            raise ValueError("Die Webhook-Adresse muss mit https:// beginnen.")
    elif env == "_NAME":
        if not re.fullmatch(r"[A-Za-zÄÖÜäöüß0-9 .-]{2,24}", w):
            raise ValueError("Der Name darf 2–24 Zeichen haben (Buchstaben, Ziffern, Leerzeichen).")
    elif " " in w:
        raise ValueError("Schlüssel enthalten keine Leerzeichen – beim Kopieren ist wohl etwas dazugekommen.")
    return w


def zustand(pid: str) -> str:
    """'ja' / 'teilweise' / 'nein'."""
    if pid == "webhook":
        return "ja" if webhooks() else "nein"
    p = PLATTFORMEN[pid]
    da = [f.env for f in p.felder if _wert(f.env)]
    if all(_wert(e) for e in p.pflicht):
        if pid == "twitch" and _wert("TWITCH_CLIENT_ID") and not _twitch_angemeldet():
            return "teilweise"
        return "ja"
    return "teilweise" if da else "nein"


def _twitch_angemeldet() -> bool:
    import stream
    return stream.TOKEN_DATEI.exists()


def speichern(pid: str, werte: dict[str, str]) -> str:
    """Werte aus dem Fenster speichern. Leeres Feld = bisherigen Wert behalten."""
    p = PLATTFORMEN[pid]
    sauber = {f.env: normalisieren(f.env, werte.get(f.env, "")) for f in p.felder}
    if pid == "webhook":
        if not (sauber["_NAME"] and sauber["_URL"]):
            raise ValueError("Bitte Name und Webhook-Adresse eintragen.")
        name = sauber["_NAME"]
        if finde(name) in PLATTFORMEN and PLATTFORMEN[finde(name)].posten and finde(name) != "webhook":
            raise ValueError(f"Für {name} gibt es eine eigene Verbindung – nimm die.")
        env_setzen(webhook_schluessel(name), sauber["_URL"])
        return f"{name} ist verbunden. Sag z. B. „poste auf {name}: …“ – ich frage vorher immer um Freigabe."
    for env, w in sauber.items():
        if w:
            env_setzen(env, w)
    fehlt = [f.label for f in p.felder if f.env in p.pflicht and not _wert(f.env)]
    _neu_laden(pid)
    if fehlt:
        return f"Gespeichert. Es fehlt noch: {', '.join(fehlt)}."
    if pid == "twitch" and _wert("TWITCH_CLIENT_ID") and not _twitch_angemeldet():
        return "Gespeichert – der Chat läuft. Für Clips jetzt noch „Bei Twitch anmelden“."
    return f"{p.name} ist gespeichert. Mit „Testen“ prüfe ich, ob alles stimmt."


def trennen(pid: str) -> str:
    if pid.startswith("webhook:"):
        env_setzen(webhook_schluessel(pid.split(":", 1)[1]), "")
        return f"{anzeige_name(pid)} ist getrennt."
    p = PLATTFORMEN[pid]
    for f in p.felder:
        if not f.env.startswith("_"):
            env_setzen(f.env, "")
    if pid == "twitch":
        import stream
        stream.TOKEN_DATEI.unlink(missing_ok=True)
    _neu_laden(pid)
    return f"{p.name} ist getrennt – die Schlüssel sind aus der .env gelöscht."


def _neu_laden(pid: str) -> None:
    try:
        if pid == "twitch":
            import stream
            stream.neu_laden()
        elif pid == "youtube":
            import youtube
            youtube._z["kanal"] = ("", "")
    except Exception as e:
        print(f"[Verbindungen] {pid} neu laden: {e}")


def status_text() -> str:
    zeilen = []
    for pid, p in PLATTFORMEN.items():
        z = zustand(pid)
        if pid == "webhook":
            namen = ", ".join(webhooks())
            zeilen.append(f"Andere Plattformen: {namen}" if namen else "Andere Plattformen (Webhook): nicht verbunden")
            continue
        extra = ""
        if pid == "twitch" and _wert("TWITCH_KANAL"):
            extra = f" (#{_wert('TWITCH_KANAL')}" + ("" if z == "ja" else ", für Clips fehlt die Anmeldung") + ")"
        elif pid == "youtube" and _wert("YOUTUBE_KANAL"):
            extra = f" ({_wert('YOUTUBE_KANAL')})"
        zeilen.append(f"{p.name}: " + {"ja": "verbunden", "teilweise": "halb eingerichtet", "nein": "nicht verbunden"}[z] + extra)
    return "Verbindungen – " + "; ".join(zeilen) + ". Einrichten: „verbinde …“ öffnet das Fenster."


# ------------------------------------------------------------------ Testen / Status
def testen(pid: str) -> str:
    import requests

    if pid.startswith("webhook:") or pid == "webhook":
        namen = [pid.split(":", 1)[1]] if ":" in pid else list(webhooks())
        if not namen:
            return "Noch keine andere Plattform verbunden."
        return " ".join(f"{n}: Adresse ist eingetragen (getestet wird beim ersten Posten)." for n in namen)
    if zustand(pid) == "nein":
        return f"{anzeige_name(pid)} ist noch nicht verbunden."
    try:
        if pid == "twitch":
            import stream
            chat = stream._z["chat"]
            text = f"Twitch-Chat #{stream.KANAL}: " + ("verbunden." if chat and chat.verbunden else "verbindet gerade …")
            if stream.CLIENT_ID and _twitch_angemeldet():
                text += " " + stream.twitch_status()
            return text
        if pid == "youtube":
            import youtube
            return youtube.status()
        if pid == "x":
            r = requests.get("https://api.x.com/2/users/me", timeout=10,
                             headers={"Authorization": _x_kopf("GET", "https://api.x.com/2/users/me")})
            if r.status_code == 200:
                return f"X ist verbunden als @{r.json()['data']['username']}."
            return f"X sagt ({r.status_code}): {_kurz(r)}"
        if pid == "instagram":
            return instagram_info()
        if pid == "discord":
            r = requests.get(_wert("DISCORD_WEBHOOK"), timeout=10)
            if r.status_code == 200:
                return f"Discord ist verbunden: Webhook „{r.json().get('name', '?')}“."
            return f"Discord sagt ({r.status_code}): der Webhook stimmt nicht (gelöscht?)."
    except (RuntimeError, requests.RequestException) as e:
        return str(e)[:200]
    return "Unbekannte Plattform."


def _kurz(r) -> str:
    try:
        d = r.json()
        text = d.get("detail") or d.get("title") or (d.get("error") or {}).get("message") or d.get("message") or str(d)
    except ValueError:
        text = r.text
    return re.sub(r"\s+", " ", str(text))[:160]


def _graph() -> str:
    """Token aus "Instagram-Login" (IGAA...) -> graph.instagram.com, aus "Facebook-Login" (EAA...) -> graph.facebook.com."""
    return "https://graph.instagram.com/v21.0" if _wert("INSTAGRAM_TOKEN").startswith("IG") else "https://graph.facebook.com/v21.0"


def instagram_info() -> str:
    import requests

    r = requests.get(f"{_graph()}/{_wert('INSTAGRAM_KONTO_ID')}", timeout=10, params={
        "fields": "username,followers_count,media_count,media.limit(3){caption,like_count,comments_count,timestamp}",
        "access_token": _wert("INSTAGRAM_TOKEN")})
    if r.status_code != 200:
        raise RuntimeError(f"Instagram sagt ({r.status_code}): {_kurz(r)}")
    d = r.json()
    text = (f"Instagram @{d.get('username', '?')}: {d.get('followers_count', '?')} Follower, "
            f"{d.get('media_count', '?')} Beiträge.")
    posts = (d.get("media") or {}).get("data") or []
    if posts:
        text += " Letzte: " + "; ".join(f"„{(m.get('caption') or 'ohne Text')[:40]}“ {m.get('like_count', 0)} Likes, "
                                        f"{m.get('comments_count', 0)} Kommentare" for m in posts) + "."
    return text


# ------------------------------------------------------------------ Posten (nur mit Freigabe-Token)
MAX_ZEICHEN = {"x": 280, "discord": 2000, "instagram": 2200}


def kann_posten() -> list[str]:
    namen = [p.name for pid, p in PLATTFORMEN.items() if p.posten and pid != "webhook" and zustand(pid) == "ja"]
    return namen + list(webhooks())


def posten_pruefen(pid: str, text: str, bild_url: str = "") -> str:
    """Vor der Freigabe-Frage: "" wenn ok, sonst warum nicht."""
    if not pid:
        moeglich = ", ".join(kann_posten()) or "noch keine"
        return f"Wo soll ich posten? Verbunden: {moeglich}."
    if not pid.startswith("webhook:"):
        p = PLATTFORMEN.get(pid)
        if not p or not p.posten:
            return f"Auf {anzeige_name(pid)} kann ich nicht posten."
        if zustand(pid) != "ja":
            return f"{p.name} ist noch nicht verbunden – sag „verbinde {p.name}“."
    if not text.strip():
        return "Was soll ich posten?"
    grenze = MAX_ZEICHEN.get(pid)
    if grenze and len(text) > grenze:
        return f"Der Text ist {len(text)} Zeichen lang, {anzeige_name(pid)} erlaubt {grenze}. Kürzer, bitte."
    if pid == "instagram" and not re.match(r"https://\S+\.(?:jpe?g)(?:\?\S*)?$", bild_url or "", re.I):
        return "Instagram braucht ein Bild: eine öffentliche https-Adresse zu einem JPG."
    return ""


def posten(pid: str, text: str, token: str, bild_url: str = "") -> str:
    import requests

    import freigabe

    freigabe.pruefe(token, "posten")
    fehler = posten_pruefen(pid, text, bild_url)
    if fehler:
        return fehler
    if pid == "x":
        url = "https://api.x.com/2/tweets"
        r = requests.post(url, json={"text": text}, timeout=15, headers={"Authorization": _x_kopf("POST", url)})
        if r.status_code in (200, 201):
            return f"Ist auf X gepostet: x.com/i/status/{r.json()['data']['id']}"
        if r.status_code == 403:
            return ("X lässt den Post nicht zu (403): Stehen die App-Rechte auf „Read and write“ und hast du die Access "
                    "Tokens danach neu erzeugt? " + _kurz(r))
        return f"X sagt ({r.status_code}): {_kurz(r)}"
    if pid == "discord":
        r = requests.post(_wert("DISCORD_WEBHOOK"), timeout=15, params={"wait": "true"},
                          json={"content": text, "allowed_mentions": {"parse": []}})   # kein @everyone aus Versehen
        return "Ist auf Discord geschickt." if r.status_code in (200, 204) else f"Discord sagt ({r.status_code}): {_kurz(r)}"
    if pid == "instagram":
        konto, tok = _wert("INSTAGRAM_KONTO_ID"), _wert("INSTAGRAM_TOKEN")
        r = requests.post(f"{_graph()}/{konto}/media", timeout=30,
                          data={"image_url": bild_url, "caption": text, "access_token": tok})
        if r.status_code != 200:
            return f"Instagram nimmt das Bild nicht ({r.status_code}): {_kurz(r)}"
        behaelter = r.json()["id"]
        for _ in range(10):   # Instagram laedt das Bild erst herunter
            r = requests.post(f"{_graph()}/{konto}/media_publish", timeout=30,
                              data={"creation_id": behaelter, "access_token": tok})
            if r.status_code == 200:
                return "Ist auf Instagram gepostet."
            time.sleep(3)
        return f"Instagram sagt ({r.status_code}): {_kurz(r)}"
    if pid.startswith("webhook:"):
        import identitaet

        name = pid.split(":", 1)[1]
        url = webhooks().get(name)
        if not url:
            return f"{name} ist nicht verbunden."
        r = requests.post(url, timeout=15, json={"text": text, "bild_url": bild_url, "plattform": name, "von": identitaet.NAME})
        if r.status_code < 300:
            return f"Ist an {name} geschickt."
        return f"{name} (Webhook) sagt ({r.status_code}): {_kurz(r)}"
    return "Unbekannte Plattform."


# ------------------------------------------------------------------ OAuth 1.0a fuer X (ohne Zusatzpaket)
def _q(s) -> str:
    return urllib.parse.quote(str(s), safe="~")


def oauth1_kopf(methode: str, url: str, key: str, geheimnis: str, token: str, token_geheimnis: str,
                params: dict | None = None, nonce: str = "", zeit: str = "") -> str:
    """Authorization-Kopf nach RFC 5849 (HMAC-SHA1). JSON-Bodies gehen nicht in die Signatur ein."""
    oauth = {"oauth_consumer_key": key, "oauth_nonce": nonce or secrets.token_hex(16),
             "oauth_signature_method": "HMAC-SHA1", "oauth_timestamp": zeit or str(int(time.time())),
             "oauth_token": token, "oauth_version": "1.0"}
    paare = sorted((_q(k), _q(v)) for k, v in {**(params or {}), **oauth}.items())
    basis = "&".join([methode.upper(), _q(url), _q("&".join(f"{k}={v}" for k, v in paare))])
    signatur = hmac.new(f"{_q(geheimnis)}&{_q(token_geheimnis)}".encode(), basis.encode(), hashlib.sha1).digest()
    oauth["oauth_signature"] = base64.b64encode(signatur).decode()
    return "OAuth " + ", ".join(f'{_q(k)}="{_q(v)}"' for k, v in sorted(oauth.items()))


def _x_kopf(methode: str, url: str) -> str:
    return oauth1_kopf(methode, url, _wert("X_API_KEY"), _wert("X_API_SECRET"), _wert("X_ACCESS_TOKEN"), _wert("X_ACCESS_SECRET"))
