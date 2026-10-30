"""
Klaus - Einstellungen zum Selbst-Eintragen (Fenster "Einstellungen", verbindungen_fenster.EinstellungenFenster).

Statt die .env im Editor zu suchen: Name, wie er dich nennt, KI-Schluessel, Stimme, Mikrofon, Updates und Fehlerberichte -
jeweils mit Anleitung und "Testen". Gleiche Schnittstelle wie verbindungen.py (PLATTFORMEN, zustand, speichern, testen ...).
"""
from __future__ import annotations

import os
import re
import urllib.parse

from verbindungen import Feld, Plattform, env_setzen

PLATTFORMEN: dict[str, Plattform] = {p.id: p for p in [
    Plattform(
        "allgemein", "Name",
        "Wie dein Assistent heißt (darauf hört er auch: „Lumine, wie spät ist es?“) und wie er dich nennt.",
        ["Name des Assistenten: ein Wort, das sonst selten vorkommt – kurze Alltagswörter wecken ihn aus Versehen.",
         "Dein Name: so spricht er dich an und so steht es in der Oberfläche.",
         "Speichern, dann „Neu starten“."],
        "https://github.com/Tenktv/Klaus#readme",
        [Feld("KLAUS_NAME", "Name des Assistenten", hinweis="z. B. Klaus, Lumine, Jarvis"),
         Feld("KLAUS_NUTZER", "Dein Name", hinweis="z. B. Tim")],
        ("KLAUS_NAME",)),
    Plattform(
        "gemini", "Gemini (Sprache)",
        "Die natürlichen Sprachgespräche. Kostenlos mit einem Google-Konto – ohne Gemini antwortet nur die Ersatz-KI.",
        ["aistudio.google.com/apikey öffnen und mit deinem Google-Konto anmelden.",
         "„API-Schlüssel erstellen“, kopieren, hier einfügen, speichern."],
        "https://aistudio.google.com/apikey",
        [Feld("GEMINI_API_KEY", "Gemini-API-Schlüssel", geheim=True)],
        ("GEMINI_API_KEY",)),
    Plattform(
        "ersatz", "Ersatz-KI",
        "Antwortet, wenn Gemini ausfällt oder sein Tageslimit erreicht ist. Groq und OpenRouter sind kostenlos.",
        ["Groq: console.groq.com/keys → „Create API Key“.",
         "OpenRouter: openrouter.ai/keys → „Create Key“ (Gratis-Modelle).",
         "Einer reicht, beide sind besser."],
        "https://console.groq.com/keys",
        [Feld("GROQ_API_KEY", "Groq-Schlüssel", geheim=True), Feld("OPENROUTER_API_KEY", "OpenRouter-Schlüssel", geheim=True)],
        ("GROQ_API_KEY",)),
    Plattform(
        "eigene_ki", "Eigene KI",
        "Jeder Anbieter im OpenAI-Format: OpenAI, Mistral, DeepSeek – oder LM Studio auf deinem PC.",
        ["Adresse der API eintragen, z. B. https://api.openai.com/v1 oder für LM Studio http://localhost:1234/v1.",
         "Schlüssel (bei LM Studio leer lassen) und Modell(e), kommagetrennt."],
        "https://platform.openai.com/api-keys",
        [Feld("ERSATZ_KI_URL", "API-Adresse", hinweis="https://…/v1"), Feld("ERSATZ_KI_KEY", "API-Schlüssel", geheim=True),
         Feld("ERSATZ_KI_MODELLE", "Modell(e)", hinweis="z. B. gpt-4o-mini")],
        ("ERSATZ_KI_URL",)),
    Plattform(
        "fish", "Fish Audio (Stimmen)",
        "Eigene Stimmen und Figuren-Stimmen (z. B. Anime). Kostet Guthaben auf fish.audio – ohne Guthaben spricht "
        "automatisch die Gemini-Stimme.",
        ["fish.audio öffnen, anmelden, unter „API“ einen Schlüssel erstellen.",
         "Guthaben aufladen (sonst „402 kein Guthaben“).",
         "Stimme wählen: sag „nimm die Stimme von …“ oder schick einen fish.audio-Link."],
        "https://fish.audio/app/api-keys/",
        [Feld("FISH_API_KEY", "Fish-Audio-Schlüssel", geheim=True)],
        ("FISH_API_KEY",)),
    Plattform(
        "mikrofon", "Mikrofon",
        "Welches Mikrofon er benutzt. Leer = das Windows-Standardmikrofon.",
        ["„Testen“ zeigt alle Mikrofone an diesem PC.",
         "Einen Teil des Namens eintragen (z. B. „Yeti“ oder „Headset“), speichern, neu starten."],
        "ms-settings:sound",
        [Feld("KLAUS_MIC", "Mikrofon (Teil des Namens)", hinweis="leer = Windows-Standard")],
        ()),
    Plattform(
        "leistung", "Leistung (Lite)",
        "Für schwächere PCs: Lite zeigt nur Sprache und ein kleines Chatfenster, ohne Panel, Orb, Designs, Twitch und Spielmodus. "
        "Spart viel Arbeitsspeicher und Prozessor. Sprachgespräche, Termine, Telegram und WhatsApp bleiben gleich.",
        ["Lite: an, um die schlanke Version zu nutzen (leer oder aus = volle Oberfläche).",
         "Spracherkennung fürs Weckwort: tiny (schnellste), base (empfohlen für Lite), small (genauer), medium (nur mit guter Grafikkarte).",
         "Danach „Neu starten“. Von Lite zurück zur vollen Oberfläche geht nur, wenn die volle Version installiert wurde (sonst Setup.exe neu)."],
        "https://github.com/Tenktv/Klaus/releases/latest",
        [Feld("KLAUS_LITE", "Lite", hinweis="an / aus"), Feld("WHISPER_MODEL", "Spracherkennung", hinweis="tiny, base, small oder medium")],
        ()),
    Plattform(
        "updates", "Updates & Hilfe",
        "Update-Token (nur solange das Repo privat ist) und Melde-Code: damit kommen Fehler automatisch bei Nikola an.",
        ["Beides bekommst du von Nikola.",
         "„Testen“ prüft, ob ein Update da ist, und schickt einen Probe-Bericht an Nikola."],
        "https://github.com/Tenktv/Klaus/releases/latest",
        [Feld("KLAUS_UPDATE_TOKEN", "Update-Token (optional)", geheim=True),
         Feld("KLAUS_MELDE_CODE", "Melde-Code (optional)", geheim=True)],
        ()),
]}
for _p in PLATTFORMEN.values():
    _p.trennbar = _p.id in ("gemini", "ersatz", "eigene_ki", "fish")

NEUSTART = {"allgemein", "gemini", "ersatz", "eigene_ki", "fish", "mikrofon", "leistung", "updates"}


def _wert(name: str) -> str:
    return os.getenv(name, "").strip()


def webhooks() -> dict:
    return {}


def finde(eingabe: str) -> str:
    e = (eingabe or "").strip().lower()
    if e in PLATTFORMEN:
        return e
    for pid, p in PLATTFORMEN.items():
        if e and (e in p.name.lower() or e in pid):
            return pid
    return ""


def zustand(pid: str) -> str:
    p = PLATTFORMEN[pid]
    if not p.pflicht:
        return "ja" if any(_wert(f.env) for f in p.felder) else "nein"
    if all(_wert(e) for e in p.pflicht):
        return "ja"
    return "teilweise" if any(_wert(f.env) for f in p.felder) else "nein"


def neustart_noetig(pid: str) -> bool:
    return pid in NEUSTART


def zusatz(pid: str) -> str:
    if pid == "allgemein":
        return f"Jetzt: {_wert('KLAUS_NAME') or 'Klaus'}, er nennt dich {_wert('KLAUS_NUTZER') or '(noch nichts eingetragen)'}."
    return ""


def _web_oberflaeche_da() -> bool:
    """Ist PySide6 mit WebEngine (volle Oberflaeche) installiert? Lite-Installationen haben nur PySide6-Essentials."""
    import importlib.util
    try:
        return importlib.util.find_spec("PySide6.QtWebEngineWidgets") is not None
    except (ImportError, ValueError):
        return False


def normalisieren(env: str, wert: str) -> str:
    w = re.sub(r"[\r\n\t]", "", wert).strip()
    if not w:
        return ""
    if env == "KLAUS_NAME":
        if not re.fullmatch(r"[A-Za-zÄÖÜäöüß-]{2,20}", w):
            raise ValueError("Der Name des Assistenten ist ein Wort aus 2–20 Buchstaben (ohne Leerzeichen).")
    elif env == "KLAUS_NUTZER":
        if not re.fullmatch(r"[\wÄÖÜäöüß .-]{1,30}", w):
            raise ValueError("Dein Name darf bis zu 30 Zeichen haben (Buchstaben, Leerzeichen, Bindestrich).")
    elif env == "ERSATZ_KI_URL":
        teile = urllib.parse.urlparse(w)
        if teile.scheme not in ("http", "https") or not teile.hostname:
            raise ValueError("Die API-Adresse beginnt mit https:// (oder http://localhost für LM Studio).")
        w = w.rstrip("/")
    elif env == "KLAUS_LITE":
        a = w.lower()
        if a in ("1", "an", "ja", "ein", "lite", "true"):
            return "1"
        if a in ("0", "aus", "nein", "false", "voll"):
            if os.getenv("KLAUS_LITE", "").strip() == "1" and not _web_oberflaeche_da():
                raise ValueError("Die volle Oberfläche ist in dieser Installation nicht dabei (Lite hat sie weggelassen). "
                                 "Dafür die Setup.exe noch einmal ausführen und „Lite“ abwählen.")
            return "0"
        raise ValueError("Lite: „an“ oder „aus“.")
    elif env == "WHISPER_MODEL":
        if w.lower() not in ("tiny", "base", "small", "medium"):
            raise ValueError("Spracherkennung: tiny, base, small oder medium.")
        w = w.lower()
    elif env in ("KLAUS_MIC", "ERSATZ_KI_MODELLE"):
        w = w[:120]
    elif " " in w:
        raise ValueError("Schlüssel enthalten keine Leerzeichen – beim Kopieren ist wohl etwas dazugekommen.")
    return w


def speichern(pid: str, werte: dict[str, str]) -> str:
    """Leeres Feld = bisherigen Wert behalten (Ausnahme: Mikrofon - leer heisst Windows-Standard)."""
    p = PLATTFORMEN[pid]
    sauber = {f.env: normalisieren(f.env, werte.get(f.env, "")) for f in p.felder}
    for env, w in sauber.items():
        if w or (env == "KLAUS_MIC" and env in werte):
            env_setzen(env, w)
    fehlt = [f.label for f in p.felder if f.env in p.pflicht and not _wert(f.env)]
    if fehlt:
        return f"Gespeichert. Es fehlt noch: {', '.join(fehlt)}."
    return "Gespeichert. Mit „Testen“ prüfe ich, ob es klappt" + (" – wirksam nach „Neu starten“." if pid in NEUSTART else ".")


def trennen(pid: str) -> str:
    for f in PLATTFORMEN[pid].felder:
        env_setzen(f.env, "")
    return f"{PLATTFORMEN[pid].name}: Schlüssel gelöscht (nach „Neu starten“ wirksam)."


def _kurz(r) -> str:
    try:
        d = r.json()
        fehler = d.get("error")
        text = (fehler.get("message") if isinstance(fehler, dict) else fehler) or d.get("message") or str(d)
    except ValueError:
        text = r.text
    return re.sub(r"\s+", " ", str(text))[:140]


def _bearer(url: str, schluessel: str, name: str) -> str:
    import requests

    r = requests.get(url, timeout=10, headers={"Authorization": f"Bearer {schluessel}"} if schluessel else {})
    if r.status_code == 200:
        return f"{name}: ✓ Schlüssel funktioniert."
    if r.status_code in (401, 403):
        return f"{name}: ✗ Schlüssel wird abgelehnt ({r.status_code})."
    return f"{name}: ✗ antwortet mit {r.status_code}: {_kurz(r)}"


def _mikrofone() -> str:
    try:
        import sounddevice as sd
        standard = sd.query_devices(kind="input").get("name", "?")
        namen = list(dict.fromkeys(d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0))
    except Exception as e:
        return f"Ich finde keine Mikrofone ({str(e)[:80]}). Ist eins angeschlossen und in Windows erlaubt?"
    gewaehlt = _wert("KLAUS_MIC")
    treffer = [n for n in namen if gewaehlt and gewaehlt.lower() in n.lower()]
    zeile = (f"Eingestellt: „{gewaehlt}“ → {treffer[0]}" if treffer else
             f"„{gewaehlt}“ passt zu keinem Mikrofon – ich nehme den Standard." if gewaehlt else f"Standard: {standard}")
    return zeile + "\nMikrofone an diesem PC: " + "; ".join(namen[:12])


def testen(pid: str) -> str:
    import requests

    try:
        if pid == "allgemein":
            return zusatz(pid) + " (Weckwort testen: Namen sagen, dann zum Beispiel „wie spät ist es?“)"
        if pid == "gemini":
            if not _wert("GEMINI_API_KEY"):
                return "Noch kein Gemini-Schlüssel eingetragen."
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", timeout=10,
                             params={"key": _wert("GEMINI_API_KEY"), "pageSize": 1})
            if r.status_code == 200:
                return "Gemini: ✓ Schlüssel funktioniert."
            return f"Gemini: ✗ {r.status_code} – {_kurz(r)}"
        if pid == "ersatz":
            teile = []
            if _wert("GROQ_API_KEY"):
                teile.append(_bearer("https://api.groq.com/openai/v1/models", _wert("GROQ_API_KEY"), "Groq"))
            if _wert("OPENROUTER_API_KEY"):
                teile.append(_bearer("https://openrouter.ai/api/v1/auth/key", _wert("OPENROUTER_API_KEY"), "OpenRouter"))
            return "\n".join(teile) or "Noch kein Groq- oder OpenRouter-Schlüssel eingetragen."
        if pid == "eigene_ki":
            if not _wert("ERSATZ_KI_URL"):
                return "Noch keine API-Adresse eingetragen."
            schluessel = _wert("ERSATZ_KI_KEY")
            return _bearer(_wert("ERSATZ_KI_URL") + "/models", "" if schluessel == "lokal" else schluessel, "Eigene KI")
        if pid == "fish":
            if not _wert("FISH_API_KEY"):
                return "Noch kein Fish-Audio-Schlüssel eingetragen."
            return (_bearer("https://api.fish.audio/model?page_size=1&self=true", _wert("FISH_API_KEY"), "Fish Audio")
                    + " Guthaben siehst du auf fish.audio – ohne Guthaben spricht die Gemini-Stimme.")
        if pid == "mikrofon":
            return _mikrofone()
        if pid == "leistung":
            lite = _wert("KLAUS_LITE") == "1"
            return (f"Gerade: {'Lite (nur Sprache und Chat)' if lite else 'volle Oberfläche'}, Spracherkennung {_wert('WHISPER_MODEL') or 'small (Standard)'}. "
                    f"Volle Oberfläche in dieser Installation: {'vorhanden' if _web_oberflaeche_da() else 'nicht vorhanden'}.")
        if pid == "updates":
            import fehlerbericht
            import pc_update

            rel, grund = pc_update.release_pruefen()
            teile = [f"Updates: {'Version ' + rel['tag'] + ' ist da – Taskleiste → „Nach Updates suchen“.' if rel else grund}"]
            teile.append("Fehlerberichte: " + (fehlerbericht.senden("Test aus den Einstellungen") if fehlerbericht.code()
                                               else "kein Melde-Code eingetragen (dann bekommt Nikola keine Fehler)."))
            return "\n".join(teile)
    except requests.RequestException as e:
        return f"Keine Verbindung: {str(e)[:120]}"
    return ""
