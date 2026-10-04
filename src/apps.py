"""
Klaus - Apps, Webseiten und Ordner oeffnen
Kennt alle Apps aus dem Startmenue (klassische Programme und Store-Apps),
dazu gaengige Webseiten, Windows-Werkzeuge und Ordner.

    apps.oeffne("spotify")   -> "Spotify"   (oder None, wenn nichts passt)
    apps.suche("wetter goeppingen")
"""

import difflib
import json
import os
import re
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path

WEBSEITEN = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.de",
    "gmail": "https://mail.google.com",
    "google mail": "https://mail.google.com",
    "google maps": "https://maps.google.de",
    "maps": "https://maps.google.de",
    "google drive": "https://drive.google.com",
    "github": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "amazon": "https://www.amazon.de",
    "netflix": "https://www.netflix.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "linkedin": "https://www.linkedin.com",
    "twitter": "https://x.com",
    "whatsapp web": "https://web.whatsapp.com",
}

WERKZEUGE = {
    "rechner": ["calc"],
    "taschenrechner": ["calc"],
    "editor": ["notepad"],
    "notepad": ["notepad"],
    "explorer": ["explorer"],
    "datei explorer": ["explorer"],
    "einstellungen": ["explorer", "ms-settings:"],
    "task manager": ["taskmgr"],
    "terminal": ["wt"],
    "eingabeaufforderung": ["cmd", "/c", "start", "cmd"],
    "systemsteuerung": ["control"],
    "paint": ["mspaint"],
}

HOME = Path.home()
ORDNER = {
    "downloads": HOME / "Downloads",
    "dokumente": HOME / "Documents",
    "desktop": HOME / "Desktop",
    "bilder": HOME / "Pictures",
    "musik": HOME / "Music",
    "videos": HOME / "Videos",
    "klaus projekte": Path(__file__).resolve().parent.parent / "data" / "projekte",
    "projekte": Path(__file__).resolve().parent.parent / "data" / "projekte",
}

# Was man sagt -> wie die App wirklich heisst (nach _norm, also klein, ohne Umlaute)
ALIASE = {
    "tft": "teamfight tactics",
    "teamfight": "teamfight tactics",
    "cs": "counter strike 2",
    "cs2": "counter strike 2",
    "cs 2": "counter strike 2",
    "counter strike": "counter strike 2",
    "counterstrike": "counter strike 2",
    "lol": "league of legends",
    "league": "league of legends",
    "riot": "riot client",
    "vs code": "visual studio code",
    "vscode": "visual studio code",
    "edge": "microsoft edge",
    "browser": "microsoft edge",
    "internet": "microsoft edge",
}
ZAHLWOERTER = {"eins": "1", "zwei": "2", "drei": "3", "vier": "4", "fuenf": "5"}

# Startmenue-Eintraege, die man nie oeffnen will
RAUSCHEN = re.compile(r"uninstall|deinstall|readme|liesmich|help|hilfe|im internet|website|release notes", re.I)
FUELLWOERTER = {"die", "den", "das", "der", "mir", "mal", "bitte", "app", "programm", "anwendung", "kurz", "mein", "meine", "ordner", "spiel", "game"}

_apps: dict[str, str] | None = None


def _norm(text: str) -> str:
    text = text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    woerter = [ZAHLWOERTER.get(w, w) for w in re.findall(r"[a-z0-9]+", text) if w not in FUELLWOERTER]
    text = " ".join(woerter)
    # Buchstabiertes zusammenziehen: "t f t" -> "tft", "c s 2" -> "cs 2"
    text = re.sub(r"\b([a-z])(?: ([a-z])\b)+", lambda m: m.group(0).replace(" ", ""), text)
    return text


def lade_apps() -> dict[str, str]:
    """Name -> AppID aller Startmenue-Apps (einmalig per PowerShell geladen)."""
    global _apps
    if _apps is None:
        befehl = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"
        roh = subprocess.run(
            ["powershell", "-NoProfile", "-Command", befehl],
            capture_output=True, text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout
        eintraege = json.loads(roh or "[]")
        if isinstance(eintraege, dict):
            eintraege = [eintraege]
        _apps = {e["Name"]: e["AppID"] for e in eintraege if not RAUSCHEN.search(e["Name"])}
    return _apps


def _beste_app(ziel: str) -> str | None:
    apps = lade_apps()
    normiert = {_norm(n): n for n in apps}
    if ziel in normiert:
        return normiert[ziel]
    # "code" -> "Visual Studio Code", "word" -> "Word": Ziel als ganzes Wort im Namen
    treffer = [n for k, n in normiert.items() if re.search(rf"\b{re.escape(ziel)}\b", k)]
    if treffer:
        return min(treffer, key=len)
    nah = difflib.get_close_matches(ziel, list(normiert), n=1, cutoff=0.72)
    return normiert[nah[0]] if nah else None


def _starte(befehl: list[str]) -> None:
    subprocess.Popen(befehl, creationflags=subprocess.CREATE_NO_WINDOW)


def _app_starter(app: str):
    return lambda: _starte(["explorer.exe", "shell:AppsFolder\\" + lade_apps()[app]])


def finde(was: str):
    """Sucht App/Webseite/Ordner, ohne zu oeffnen. -> (Anzeigename, starten) oder None."""
    ziel = _norm(was)
    if not ziel:
        return None
    ziel = ALIASE.get(ziel, ALIASE.get(ziel.replace(" ", ""), ziel))
    anzeige = ziel.capitalize()

    if ziel in ORDNER:
        pfad = ORDNER[ziel]
        return anzeige, lambda: (pfad.mkdir(parents=True, exist_ok=True), os.startfile(pfad))

    if ziel in WERKZEUGE:
        return anzeige, lambda: _starte(WERKZEUGE[ziel])

    app = _beste_app(ziel)
    if app and _norm(app) == ziel:  # exakter App-Treffer schlaegt Webseite
        return app, _app_starter(app)

    if ziel in WEBSEITEN:
        return anzeige, lambda: webbrowser.open(WEBSEITEN[ziel])

    # "klesro web punkt de" / "example.com"
    domain = re.sub(r"\s*punkt\s*", ".", ziel).replace(" ", "")
    if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)*\.(de|com|net|org|io|ai|eu|at|ch)", domain):
        return domain, lambda: webbrowser.open(f"https://{domain}")

    if app:
        return app, _app_starter(app)
    return None


def oeffne(was: str) -> str | None:
    """Oeffnet App/Webseite/Ordner. Gibt den Anzeigenamen zurueck oder None."""
    treffer = finde(was)
    if not treffer:
        return None
    name, starten = treffer
    starten()
    return name


def suche(begriff: str) -> None:
    webbrowser.open("https://www.google.de/search?q=" + urllib.parse.quote(begriff))
